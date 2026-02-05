from __future__ import annotations

from dataclasses import dataclass, field

from sim.crop_catalog import CropCatalog, CropDef, ShopAccess, seed_availability
from sim.growth import GrowthModifiers, days_to_first_harvest_from_phases
from sim.pricing import processed_prices, raw_price, keg_price, jar_price, dried_batch_price
from sim.plots import season_for_day_of_year
from sim.save_state import FarmState, TileState, CropInstance
from sim.config import EconomyConfig

KEG_DAYS = 7
JAR_DAYS = 3
DEHYDRATOR_DAYS = 1
DEHYDRATOR_INPUT = 5
CASK_DAYS = 56


@dataclass(frozen=True)
class SimulationOptions:
    window_days: int = 113
    sprinkler_only: bool = True
    allow_seed_purchases: bool = True
    replant_strategy: str = "optimal"
    ancient_seed_conservative: bool = True


@dataclass
class MachineSlot:
    crop_id: str | None
    days_remaining: int


@dataclass
class CropResult:
    crop_id: str
    name: str | None
    harvested: int = 0
    raw_sold: int = 0
    base_wine: int = 0
    aged_wine: int = 0
    juice: int = 0
    jelly: int = 0
    pickles: int = 0
    dried: int = 0
    seed_used: int = 0
    seed_purchased: int = 0
    seed_cost: int = 0
    wine_in_kegs_end: int = 0
    wine_in_casks_end: int = 0
    jelly_in_jars_end: int = 0
    dried_in_dehydrators_end: int = 0


@dataclass
class SimulationResult:
    per_crop: dict[str, CropResult]
    total_revenue: int
    total_profit: int
    total_seed_cost: int
    total_raw_sold: int
    total_base_wine: int
    total_aged_wine: int
    total_juice: int
    total_jelly: int
    total_pickles: int
    total_dried: int


def simulate_save(
    farm: FarmState,
    catalog: CropCatalog,
    economy: EconomyConfig,
    options: SimulationOptions,
) -> SimulationResult:
    window_days = max(1, int(options.window_days))
    fruit_inventory: dict[str, int] = {}
    base_wine_inventory: dict[str, int] = {}
    seed_inventory = dict(farm.seed_inventory)

    results: dict[str, CropResult] = {}

    kegs = [MachineSlot(None, 0) for _ in range(max(0, farm.machines.kegs))]
    jars = [MachineSlot(None, 0) for _ in range(max(0, farm.machines.preserves_jars))]
    dehydrators = [MachineSlot(None, 0) for _ in range(max(0, farm.machines.dehydrators))]
    casks = [MachineSlot(None, 0) for _ in range(max(0, farm.machines.casks))]

    for day in range(window_days):
        day_of_year = ((farm.start_day_of_year - 1 + day) % 112) + 1
        season = season_for_day_of_year(day_of_year)

        _advance_kegs(kegs, catalog, results, base_wine_inventory)
        _advance_jars(jars, catalog, results)
        _advance_dehydrators(dehydrators, catalog, results)
        _advance_casks(casks, catalog, results)

        # Fill casks from base wine inventory
        _fill_casks(casks, base_wine_inventory, catalog, economy)

        # Grow and harvest crops
        for tile in farm.tiles:
            if tile.crop is None:
                continue
            crop_inst = tile.crop
            if not _is_crop_active(tile.location, crop_inst.crop, season):
                tile.crop = None
                continue
            if crop_inst.crop.needs_watering and options.sprinkler_only and not tile.watered:
                continue
            crop_inst.days_until_harvest -= 1
            if crop_inst.days_until_harvest > 0:
                continue

            yield_amount = _harvest_yield(crop_inst, farm.farming_level)
            if yield_amount > 0:
                _add_inventory(fruit_inventory, crop_inst.crop.harvest_item_id, yield_amount)
                result = _ensure_result(results, crop_inst.crop)
                result.harvested += yield_amount

            if crop_inst.crop.regrow_days:
                crop_inst.days_until_harvest = crop_inst.crop.regrow_days
                crop_inst.is_regrowing = True
            else:
                tile.crop = None

        # Conservative ancient seed makers
        if farm.machines.seed_makers > 0:
            _run_ancient_seed_makers(
                fruit_inventory,
                seed_inventory,
                catalog,
                farm.machines.seed_makers,
                conservative=options.ancient_seed_conservative,
            )

        # Replant empty tiles
        processing_capacity = _processing_capacity(farm)
        current_expected = _current_expected_daily_yield(
            farm,
            season,
            sprinkler_only=options.sprinkler_only,
        )
        for tile in farm.tiles:
            if tile.crop is not None:
                continue
            if options.sprinkler_only and not tile.watered:
                continue
            crop_def = _select_crop_for_tile(
                tile=tile,
                day_of_year=day_of_year,
                season=season,
                window_days=window_days - day - 1,
                catalog=catalog,
                economy=economy,
                shop_access=farm.shop_access,
                seed_inventory=seed_inventory,
                allow_purchases=options.allow_seed_purchases,
                farming_level=farm.farming_level,
                agriculturist=farm.professions.farming.agriculturist,
                processing_capacity=processing_capacity,
                current_expected=current_expected,
            )
            if crop_def is None:
                continue
            planted = _plant_crop(
                tile,
                crop_def,
                farm.professions,
                seed_inventory,
                farm.shop_access,
                options.allow_seed_purchases,
                results,
            )
            if planted:
                mods = GrowthModifiers(fertilizer=tile.fertilizer, agriculturist=farm.professions.farming.agriculturist)
                current_expected += _expected_daily_yield(crop_def, farm.farming_level, mods)
                continue

        # Fill machines from inventory
        _fill_kegs(kegs, fruit_inventory, catalog, economy)
        _fill_jars(jars, fruit_inventory, catalog, economy)
        _fill_dehydrators(dehydrators, fruit_inventory, catalog, economy)

    # End of window: sell remaining raw fruit and base wine
    total_seed_cost = 0
    total_revenue = 0
    totals = {
        "raw": 0,
        "base_wine": 0,
        "aged_wine": 0,
        "juice": 0,
        "jelly": 0,
        "pickles": 0,
        "dried": 0,
    }

    for crop_id, count in fruit_inventory.items():
        if count <= 0:
            continue
        crop = catalog.by_harvest_id.get(crop_id)
        if crop is None or crop.base_price is None:
            continue
        result = _ensure_result(results, crop)
        result.raw_sold += count

    for crop_id, count in base_wine_inventory.items():
        if count <= 0:
            continue
        crop = catalog.by_harvest_id.get(crop_id)
        if crop is None:
            continue
        result = _ensure_result(results, crop)
        result.base_wine += count

    for slot in kegs:
        if slot.days_remaining > 0 and slot.crop_id is not None:
            result = _ensure_result(results, catalog.by_harvest_id[slot.crop_id])
            result.wine_in_kegs_end += 1

    for slot in casks:
        if slot.days_remaining > 0 and slot.crop_id is not None:
            result = _ensure_result(results, catalog.by_harvest_id[slot.crop_id])
            result.wine_in_casks_end += 1

    for slot in jars:
        if slot.days_remaining > 0 and slot.crop_id is not None:
            result = _ensure_result(results, catalog.by_harvest_id[slot.crop_id])
            result.jelly_in_jars_end += 1

    for slot in dehydrators:
        if slot.days_remaining > 0 and slot.crop_id is not None:
            result = _ensure_result(results, catalog.by_harvest_id[slot.crop_id])
            result.dried_in_dehydrators_end += 1

    for crop_id, result in results.items():
        crop = catalog.by_harvest_id.get(crop_id)
        if crop is None or crop.base_price is None:
            continue
        prices = processed_prices(crop, economy)
        raw_value = prices.raw
        total_seed_cost += result.seed_cost

        totals["raw"] += result.raw_sold
        totals["base_wine"] += result.base_wine
        totals["aged_wine"] += result.aged_wine
        totals["juice"] += result.juice
        totals["jelly"] += result.jelly
        totals["pickles"] += result.pickles
        totals["dried"] += result.dried

        revenue = 0
        revenue += result.raw_sold * raw_value
        if crop.category == "fruit":
            wine_price = keg_price(crop, economy) or 0
            revenue += result.base_wine * wine_price
            revenue += int(result.aged_wine * wine_price * economy.aged_wine_multiplier)
            revenue += result.jelly * (jar_price(crop, economy) or 0)
            revenue += result.dried * (dried_batch_price(crop, economy) or 0)
        elif crop.category == "vegetable":
            revenue += result.juice * (keg_price(crop, economy) or 0)
            revenue += result.pickles * (jar_price(crop, economy) or 0)
        else:
            # flowers and others only count raw sales
            pass

        total_revenue += revenue

    total_profit = total_revenue - total_seed_cost
    return SimulationResult(
        per_crop=results,
        total_revenue=total_revenue,
        total_profit=total_profit,
        total_seed_cost=total_seed_cost,
        total_raw_sold=totals["raw"],
        total_base_wine=totals["base_wine"],
        total_aged_wine=totals["aged_wine"],
        total_juice=totals["juice"],
        total_jelly=totals["jelly"],
        total_pickles=totals["pickles"],
        total_dried=totals["dried"],
    )


def _ensure_result(results: dict[str, CropResult], crop: CropDef) -> CropResult:
    existing = results.get(crop.harvest_item_id)
    if existing is not None:
        return existing
    results[crop.harvest_item_id] = CropResult(crop_id=crop.harvest_item_id, name=crop.name)
    return results[crop.harvest_item_id]


def _add_inventory(inv: dict[str, int], crop_id: str, amount: int) -> None:
    inv[crop_id] = inv.get(crop_id, 0) + int(amount)


def _advance_kegs(
    kegs: list[MachineSlot],
    catalog: CropCatalog,
    results: dict[str, CropResult],
    base_wine_inventory: dict[str, int],
) -> None:
    for slot in kegs:
        if slot.days_remaining <= 0 or slot.crop_id is None:
            continue
        slot.days_remaining -= 1
        if slot.days_remaining == 0:
            crop = catalog.by_harvest_id.get(slot.crop_id)
            if crop is None:
                slot.crop_id = None
                continue
            result = _ensure_result(results, crop)
            if crop.category == "fruit":
                base_wine_inventory[crop.harvest_item_id] = base_wine_inventory.get(crop.harvest_item_id, 0) + 1
            elif crop.category == "vegetable":
                result.juice += 1
            slot.crop_id = None


def _advance_jars(jars: list[MachineSlot], catalog: CropCatalog, results: dict[str, CropResult]) -> None:
    for slot in jars:
        if slot.days_remaining <= 0 or slot.crop_id is None:
            continue
        slot.days_remaining -= 1
        if slot.days_remaining == 0:
            crop = catalog.by_harvest_id.get(slot.crop_id)
            if crop is None:
                slot.crop_id = None
                continue
            result = _ensure_result(results, crop)
            if crop.category == "fruit":
                result.jelly += 1
            elif crop.category == "vegetable":
                result.pickles += 1
            slot.crop_id = None


def _advance_dehydrators(dehydrators: list[MachineSlot], catalog: CropCatalog, results: dict[str, CropResult]) -> None:
    for slot in dehydrators:
        if slot.days_remaining <= 0 or slot.crop_id is None:
            continue
        slot.days_remaining -= 1
        if slot.days_remaining == 0:
            crop = catalog.by_harvest_id.get(slot.crop_id)
            if crop is None:
                slot.crop_id = None
                continue
            result = _ensure_result(results, crop)
            result.dried += 1
            slot.crop_id = None


def _advance_casks(casks: list[MachineSlot], catalog: CropCatalog, results: dict[str, CropResult]) -> None:
    for slot in casks:
        if slot.days_remaining <= 0 or slot.crop_id is None:
            continue
        slot.days_remaining -= 1
        if slot.days_remaining == 0:
            crop = catalog.by_harvest_id.get(slot.crop_id)
            if crop is None:
                slot.crop_id = None
                continue
            result = _ensure_result(results, crop)
            result.aged_wine += 1
            slot.crop_id = None


def _fill_casks(casks: list[MachineSlot], base_wine_inventory: dict[str, int], catalog: CropCatalog, economy: EconomyConfig) -> None:
    # Prioritize higher base wine price
    priorities = sorted(
        (crop_id for crop_id, count in base_wine_inventory.items() if count > 0),
        key=lambda cid: (keg_price(catalog.by_harvest_id[cid], economy) or 0),
        reverse=True,
    )
    for slot in casks:
        if slot.days_remaining != 0 or slot.crop_id is not None:
            continue
        crop_id = _pick_first_with_inventory(base_wine_inventory, priorities)
        if crop_id is None:
            break
        base_wine_inventory[crop_id] -= 1
        slot.crop_id = crop_id
        slot.days_remaining = CASK_DAYS


def _fill_kegs(kegs: list[MachineSlot], fruit_inventory: dict[str, int], catalog: CropCatalog, economy: EconomyConfig) -> None:
    priorities = _inventory_priority(fruit_inventory, catalog, economy, machine="keg")
    for slot in kegs:
        if slot.days_remaining != 0 or slot.crop_id is not None:
            continue
        crop_id = _pick_first_with_inventory(fruit_inventory, priorities)
        if crop_id is None:
            break
        fruit_inventory[crop_id] -= 1
        slot.crop_id = crop_id
        slot.days_remaining = KEG_DAYS


def _fill_jars(jars: list[MachineSlot], fruit_inventory: dict[str, int], catalog: CropCatalog, economy: EconomyConfig) -> None:
    priorities = _inventory_priority(fruit_inventory, catalog, economy, machine="jar")
    for slot in jars:
        if slot.days_remaining != 0 or slot.crop_id is not None:
            continue
        crop_id = _pick_first_with_inventory(fruit_inventory, priorities)
        if crop_id is None:
            break
        fruit_inventory[crop_id] -= 1
        slot.crop_id = crop_id
        slot.days_remaining = JAR_DAYS


def _fill_dehydrators(dehydrators: list[MachineSlot], fruit_inventory: dict[str, int], catalog: CropCatalog, economy: EconomyConfig) -> None:
    priorities = _inventory_priority(fruit_inventory, catalog, economy, machine="dried")
    for slot in dehydrators:
        if slot.days_remaining != 0 or slot.crop_id is not None:
            continue
        crop_id = _pick_first_with_inventory(fruit_inventory, priorities, minimum=DEHYDRATOR_INPUT)
        if crop_id is None:
            break
        fruit_inventory[crop_id] -= DEHYDRATOR_INPUT
        slot.crop_id = crop_id
        slot.days_remaining = DEHYDRATOR_DAYS


def _inventory_priority(
    inventory: dict[str, int],
    catalog: CropCatalog,
    economy: EconomyConfig,
    machine: str,
) -> list[str]:
    scored: list[tuple[str, float]] = []
    for crop_id, count in inventory.items():
        if count <= 0:
            continue
        crop = catalog.by_harvest_id.get(crop_id)
        if crop is None or crop.base_price is None:
            continue
        raw = raw_price(crop.base_price, economy)
        if machine == "keg":
            value = keg_price(crop, economy)
        elif machine == "jar":
            value = jar_price(crop, economy)
        else:
            value = dried_batch_price(crop, economy)
            if value is not None:
                value = value / DEHYDRATOR_INPUT
        if value is None or value <= raw:
            continue
        scored.append((crop_id, value - raw))

    scored.sort(key=lambda entry: entry[1], reverse=True)
    return [crop_id for crop_id, _ in scored]


def _pick_first_with_inventory(inventory: dict[str, int], priority: list[str], minimum: int = 1) -> str | None:
    for crop_id in priority:
        if inventory.get(crop_id, 0) >= minimum:
            return crop_id
    return None


def _is_crop_active(location: str, crop: CropDef, season: str) -> bool:
    if _is_year_round_location(location):
        return True
    if not crop.seasons:
        return False
    return season in crop.seasons


def _is_year_round_location(location: str) -> bool:
    name = location.lower()
    if name == "greenhouse":
        return True
    if name.startswith("island"):
        return True
    return False


def _harvest_yield(crop_inst: CropInstance, farming_level: int) -> int:
    crop = crop_inst.crop
    base = crop.harvest_min_stack + int(crop.harvest_max_increase_per_level * farming_level)
    extra_unit = crop.harvest_max_stack if crop.extra_harvest_chance > 0 else 0
    crop_inst.extra_buffer += crop.extra_harvest_chance * extra_unit
    extra = int(crop_inst.extra_buffer)
    crop_inst.extra_buffer -= extra
    return max(0, base + extra)


def _processing_capacity(farm: FarmState) -> float:
    return (
        (farm.machines.kegs / KEG_DAYS)
        + (farm.machines.preserves_jars / JAR_DAYS)
        + (farm.machines.dehydrators * DEHYDRATOR_INPUT / DEHYDRATOR_DAYS)
    )


def _current_expected_daily_yield(
    farm: FarmState,
    season: str,
    sprinkler_only: bool,
) -> float:
    expected = 0.0
    for tile in farm.tiles:
        if tile.crop is None:
            continue
        crop = tile.crop.crop
        if not _is_crop_active(tile.location, crop, season):
            continue
        if sprinkler_only and crop.needs_watering and not tile.watered:
            continue
        mods = GrowthModifiers(fertilizer=tile.fertilizer, agriculturist=farm.professions.farming.agriculturist)
        expected += _expected_daily_yield(crop, farm.farming_level, mods)
    return expected


def _expected_yield_per_harvest(crop: CropDef, farming_level: int) -> float:
    base = crop.harvest_min_stack + (crop.harvest_max_increase_per_level * farming_level)
    extra_unit = crop.harvest_max_stack if crop.extra_harvest_chance > 0 else 0
    return base + (crop.extra_harvest_chance * extra_unit)


def _expected_daily_yield(crop: CropDef, farming_level: int, mods: GrowthModifiers | None = None) -> float:
    expected = _expected_yield_per_harvest(crop, farming_level)
    if crop.regrow_days:
        return expected / max(1, crop.regrow_days)
    if mods is None:
        days = max(1, sum(crop.days_in_phase))
    else:
        days = max(1, days_to_first_harvest_from_phases(crop.days_in_phase, mods, crop_id=crop.harvest_item_id))
    return expected / days


def _select_crop_for_tile(
    tile: TileState,
    day_of_year: int,
    season: str,
    window_days: int,
    catalog: CropCatalog,
    economy: EconomyConfig,
    shop_access: ShopAccess,
    seed_inventory: dict[str, int],
    allow_purchases: bool,
    farming_level: int,
    agriculturist: bool,
    processing_capacity: float,
    current_expected: float,
) -> CropDef | None:
    best_crop = None
    best_score = 0.0

    for crop in catalog.by_harvest_id.values():
        if not _is_crop_active(tile.location, crop, season):
            continue
        if crop.needs_watering and not tile.watered:
            continue
        availability = seed_availability(crop, shop_access)
        has_seed = seed_inventory.get(crop.seed_item_id, 0) > 0
        if not has_seed and not (allow_purchases and availability.purchasable):
            continue
        score = _crop_score(
            crop,
            day_of_year,
            window_days,
            farming_level,
            tile.fertilizer,
            economy,
            agriculturist,
            processing_capacity,
            current_expected,
            tile.location,
        )
        if score > best_score:
            best_score = score
            best_crop = crop

    return best_crop


def _crop_score(
    crop: CropDef,
    day_of_year: int,
    window_days: int,
    farming_level: int,
    fertilizer: str,
    economy: EconomyConfig,
    agriculturist: bool,
    processing_capacity: float,
    current_expected: float,
    location: str,
) -> float:
    if crop.base_price is None:
        return 0.0
    mods = GrowthModifiers(fertilizer=fertilizer, agriculturist=agriculturist)
    days_to_first = days_to_first_harvest_from_phases(crop.days_in_phase, mods, crop_id=crop.harvest_item_id)

    harvests = _estimate_harvests(crop, day_of_year, window_days, days_to_first, location)
    if harvests <= 0:
        return 0.0
    yield_per = _expected_yield_per_harvest(crop, farming_level)
    total_yield = harvests * yield_per

    prices = processed_prices(crop, economy)
    candidates = [prices.raw]
    if prices.keg is not None:
        candidates.append(prices.keg)
    if prices.jar is not None:
        candidates.append(prices.jar)
    if prices.dried_batch is not None:
        candidates.append(prices.dried_batch / DEHYDRATOR_INPUT)
    per_fruit_best = max(candidates)
    expected_total = current_expected + _expected_daily_yield(crop, farming_level, mods)
    if processing_capacity <= 0:
        processing_fraction = 0.0
    elif expected_total <= 0:
        processing_fraction = 1.0
    else:
        processing_fraction = min(1.0, processing_capacity / expected_total)
    per_fruit_value = (processing_fraction * per_fruit_best) + ((1 - processing_fraction) * prices.raw)

    revenue = total_yield * per_fruit_value
    seed_cost = 0
    if crop.seed_price is not None:
        if crop.regrow_days:
            seed_cost = crop.seed_price
        else:
            seed_cost = crop.seed_price * harvests
    profit = revenue - seed_cost
    return profit / max(1, window_days)


def _estimate_harvests(crop: CropDef, day_of_year: int, window_days: int, days_to_first: int, location: str) -> int:
    if window_days <= 0:
        return 0
    if not _is_crop_active(location, crop, season_for_day_of_year(day_of_year)):
        return 0
    day = 0
    days_remaining = max(0, days_to_first)
    harvests = 0
    while day < window_days:
        season = season_for_day_of_year(((day_of_year - 1 + day) % 112) + 1)
        if not _is_crop_active(location, crop, season):
            break
        if days_remaining > 0:
            days_remaining -= 1
        if days_remaining == 0:
            harvests += 1
            if crop.regrow_days:
                days_remaining = crop.regrow_days
            else:
                days_remaining = days_to_first
        day += 1
    return harvests


def _plant_crop(
    tile: TileState,
    crop: CropDef,
    professions,
    seed_inventory: dict[str, int],
    shop_access: ShopAccess,
    allow_purchases: bool,
    results: dict[str, CropResult],
) -> bool:
    if crop.seed_item_id:
        if seed_inventory.get(crop.seed_item_id, 0) > 0:
            seed_inventory[crop.seed_item_id] -= 1
            result = _ensure_result(results, crop)
            result.seed_used += 1
        else:
            availability = seed_availability(crop, shop_access)
            if not (allow_purchases and availability.purchasable and availability.price is not None):
                return False
            result = _ensure_result(results, crop)
            result.seed_used += 1
            result.seed_purchased += 1
            result.seed_cost += int(availability.price)

    mods = GrowthModifiers(fertilizer=tile.fertilizer, agriculturist=professions.farming.agriculturist)
    days_to_first = days_to_first_harvest_from_phases(crop.days_in_phase, mods, crop_id=crop.harvest_item_id)
    tile.crop = CropInstance(crop=crop, days_until_harvest=max(1, days_to_first), is_regrowing=False)
    return True


def _run_ancient_seed_makers(
    fruit_inventory: dict[str, int],
    seed_inventory: dict[str, int],
    catalog: CropCatalog,
    seed_makers: int,
    conservative: bool = True,
) -> None:
    # Ancient Fruit harvest -> Ancient Seeds
    ancient_crop = catalog.by_harvest_id.get("454")
    if ancient_crop is None:
        return
    seed_id = ancient_crop.seed_item_id
    available = fruit_inventory.get(ancient_crop.harvest_item_id, 0)
    if available <= 0:
        return
    to_process = min(seed_makers, available)
    fruit_inventory[ancient_crop.harvest_item_id] -= to_process
    seeds_per = 1 if conservative else 2
    seed_inventory[seed_id] = seed_inventory.get(seed_id, 0) + (to_process * seeds_per)
