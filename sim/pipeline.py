from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from sim.crops import CropSpec
from sim.growth import GrowthModifiers, days_to_first_harvest
from sim.plots import Plot, PlotCalendar

KEG_DAYS = 7
CASK_USES_PER_YEAR = 2
PRESERVES_JAR_DAYS = 3
DEHYDRATOR_DAYS = 1
DEHYDRATOR_INPUT = 5


@dataclass
class CropYearResult:
    crop_id: str
    fruit_harvested: int
    fruit_unprocessed: int
    fruit_sold: int
    base_wine_produced: int
    base_wine_sold: int
    aged_wine_produced: int
    wine_in_kegs_end: int
    seed_units_used: int
    fertilizer_units_used: int
    jelly_produced: int = 0
    dried_fruit_produced: int = 0
    jelly_in_jars_end: int = 0
    dried_fruit_in_dehydrators_end: int = 0


@dataclass
class YearSimulationResult:
    per_crop: dict[str, CropYearResult]
    kegs_sufficient: bool
    cask_uses_per_cask: float
    casks_effective: int
    full_cask_batch_met: bool
    total_base_wine_sold: int
    total_aged_wine: int
    total_fruit_unprocessed: int
    total_wine_in_kegs_end: int
    total_jelly: int
    total_dried_fruit: int
    total_jelly_in_jars_end: int
    total_dried_fruit_in_dehydrators_end: int


def simulate_days_to_fill_casks_once(
    crop: CropSpec,
    mods: GrowthModifiers,
    tiles: int,
    kegs: int,
    casks: int,
    max_days: int,
    preserves_jars: int = 0,
    dehydrators: int = 0,
) -> CropYearResult:
    """
    Simulates a full window of max_days days for a single crop on an always-on plot.
    Assumes:
    - You keep all kegs running whenever fruit exists.
    - Starfruit replants instantly (so each tile produces every 'growth days').
    - Ancient fruit regrows every 7 days after first harvest, and speed boosts
      affect only that first harvest (handled here by switching to regrow cadence).
      (Wiki: fertilizer affects only first harvest; regrowth fixed.) :contentReference[oaicite:10]{index=10}
    - Casks are filled in two batch days per year (two uses total).
    - Preserves jars and dehydrators process remaining fruit after kegs each day.
    """
    always_calendar = PlotCalendar(type="always")
    return simulate_days_to_fill_casks_once_with_calendar(
        crop=crop,
        mods=mods,
        tiles=tiles,
        kegs=kegs,
        casks=casks,
        max_days=max_days,
        start_day_of_year=1,
        calendar=always_calendar,
        preserves_jars=preserves_jars,
        dehydrators=dehydrators,
    )


def _day_of_year(start_day_of_year: int, day_index: int) -> int:
    """Convert a 0-based day index into a 1-based Stardew day-of-year."""
    # Stardew has 112-day years (4 seasons * 28 days). start_day_of_year is 1-based.
    return ((start_day_of_year - 1 + day_index) % 112) + 1


def _cask_fill_days(max_days: int) -> list[int]:
    """Return 0-based day indexes when cask batches are filled within the year."""
    if max_days <= 0:
        return []
    if CASK_USES_PER_YEAR <= 1:
        return [0]
    spacing = max_days // CASK_USES_PER_YEAR
    if spacing <= 0:
        return [0]
    days = {i * spacing for i in range(CASK_USES_PER_YEAR)}
    return sorted(day for day in days if 0 <= day < max_days)


def _crop_priority(crops: Sequence[CropSpec], extra_ids: Sequence[str] = ()) -> list[str]:
    """Return crop IDs in priority order (starfruit first when present)."""
    ids = [crop.crop_id for crop in crops]
    priority: list[str] = []
    if "starfruit" in ids:
        priority.append("starfruit")
    for crop_id in ids:
        if crop_id not in priority:
            priority.append(crop_id)
    for extra_id in extra_ids:
        if extra_id not in priority:
            priority.append(extra_id)
    return priority


def _pick_crop_by_priority(inventory: dict[str, int], priority: Sequence[str]) -> Optional[str]:
    """Pick the highest-priority crop with remaining inventory."""
    for crop_id in priority:
        if inventory.get(crop_id, 0) > 0:
            return crop_id
    return None


def _pick_crop_with_min(
    inventory: dict[str, int],
    priority: Sequence[str],
    minimum: int,
) -> Optional[str]:
    """Pick the highest-priority crop with at least a minimum inventory."""
    for crop_id in priority:
        if inventory.get(crop_id, 0) >= minimum:
            return crop_id
    return None


def _allocate_from_inventory(
    inventory: dict[str, int],
    capacity: int,
    priority: Sequence[str],
) -> tuple[dict[str, int], dict[str, int]]:
    """Allocate up to capacity items from inventory by priority."""
    remaining = inventory.copy()
    taken = {crop_id: 0 for crop_id in inventory}
    capacity = max(0, capacity)
    for crop_id in priority:
        if capacity <= 0:
            break
        available = remaining.get(crop_id, 0)
        if available <= 0:
            continue
        take = min(available, capacity)
        taken[crop_id] = take
        remaining[crop_id] = available - take
        capacity -= take
    return taken, remaining


def _allocate_aged_wine(
    base_wine: dict[str, int],
    casks: int,
    priority: Sequence[str],
) -> tuple[dict[str, int], dict[str, int]]:
    """Allocate base wine into annual cask capacity, returning (aged, remaining)."""
    capacity = max(0, casks) * CASK_USES_PER_YEAR
    return _allocate_from_inventory(base_wine, capacity, priority)


def _simulate_cask_batches(
    daily_base_wine: dict[str, list[int]],
    starting_base_wine: dict[str, int],
    casks: int,
    batch_days: Sequence[int],
    priority: Sequence[str],
    max_days: int,
) -> tuple[dict[str, int], dict[str, int], list[int]]:
    """Simulate batch cask fills and return (aged, remaining, batch_fills)."""
    inventory = {crop_id: int(starting_base_wine.get(crop_id, 0)) for crop_id in daily_base_wine}
    aged = {crop_id: 0 for crop_id in daily_base_wine}
    batch_days_set = set(batch_days)
    batch_fills: list[int] = []

    for day in range(max_days):
        for crop_id, daily in daily_base_wine.items():
            inventory[crop_id] += daily[day]
        if day in batch_days_set and casks > 0:
            capacity = casks
            taken, inventory = _allocate_from_inventory(inventory, capacity, priority)
            batch_fills.append(sum(taken.values()))
            for crop_id, amount in taken.items():
                aged[crop_id] += amount

    return aged, inventory, batch_fills


def simulate_days_to_fill_casks_once_with_calendar(
    crop: CropSpec,
    mods: GrowthModifiers,
    tiles: int,
    kegs: int,
    casks: int,
    max_days: int,
    start_day_of_year: int,
    calendar: PlotCalendar,
    preserves_jars: int = 0,
    dehydrators: int = 0,
) -> CropYearResult:
    """
    Like simulate_days_to_fill_casks_once, but only advances crop growth and
    harvesting on days when the plot is active in its calendar.
    """
    plot = Plot(name="plot", tiles_by_crop={crop.crop_id: tiles}, calendar=calendar)
    result = simulate_year_multi_crop(
        crops=[crop],
        mods=mods,
        plots=[plot],
        kegs=kegs,
        casks=casks,
        max_days=max_days,
        start_day_of_year=start_day_of_year,
        preserves_jars=preserves_jars,
        dehydrators=dehydrators,
    )
    return result.per_crop[crop.crop_id]


def simulate_days_to_fill_casks_once_multi_plot(
    crop: CropSpec,
    mods: GrowthModifiers,
    plots: list[Plot],
    kegs: int,
    casks: int,
    max_days: int,
    start_day_of_year: int,
    preserves_jars: int = 0,
    dehydrators: int = 0,
) -> CropYearResult:
    """
    Simulate multiple plots at once, sharing keg capacity and wine inventory.
    Each plot advances growth only on its active calendar days.
    """
    result = simulate_year_multi_crop(
        crops=[crop],
        mods=mods,
        plots=plots,
        kegs=kegs,
        casks=casks,
        max_days=max_days,
        start_day_of_year=start_day_of_year,
        preserves_jars=preserves_jars,
        dehydrators=dehydrators,
    )
    return result.per_crop[crop.crop_id]


def simulate_year_multi_crop(
    crops: Sequence[CropSpec],
    mods: GrowthModifiers,
    plots: Sequence[Plot],
    kegs: int,
    casks: int,
    max_days: int,
    start_day_of_year: int,
    starting_fruit: dict[str, int] | None = None,
    starting_base_wine: dict[str, int] | None = None,
    cask_full_batch_required: bool = False,
    casks_with_walkways: int | None = None,
    preserves_jars: int = 0,
    dehydrators: int = 0,
    external_daily_fruit: dict[str, list[int]] | None = None,
    external_priority: Sequence[str] | None = None,
) -> YearSimulationResult:
    """
    Simulate a full-year pipeline for multiple crops with shared kegs, jars, and dehydrators.
    Cask aging is modeled as batch fills on a fixed schedule (two uses per year).
    If full-batch casks are required, capacity can be reduced when unmet.
    """
    crop_ids = [crop.crop_id for crop in crops]
    extra_ids: list[str] = []
    if external_daily_fruit:
        extra_ids = [crop_id for crop_id in external_daily_fruit if crop_id not in crop_ids]
        crop_ids.extend(extra_ids)
    extra_priority = list(external_priority or extra_ids)
    for crop_id in extra_ids:
        if crop_id not in extra_priority:
            extra_priority.append(crop_id)
    priority = _crop_priority(crops, extra_priority)
    crop_by_id = {crop.crop_id: crop for crop in crops}
    first_by_crop = {crop.crop_id: days_to_first_harvest(crop, mods) for crop in crops}

    starting_fruit = starting_fruit or {}
    starting_base_wine = starting_base_wine or {}
    fruit_inv = {crop_id: int(starting_fruit.get(crop_id, 0)) for crop_id in crop_ids}
    fruit_total = {crop_id: 0 for crop_id in crop_ids}
    base_wine_from_kegs = {crop_id: 0 for crop_id in crop_ids}
    daily_base_wine = {crop_id: [0] * max_days for crop_id in crop_ids}
    jelly_total = {crop_id: 0 for crop_id in crop_ids}
    dried_total = {crop_id: 0 for crop_id in crop_ids}
    seed_units = {crop_id: 0 for crop_id in crop_ids}
    fertilizer_units = {crop_id: 0 for crop_id in crop_ids}

    plot_state = []
    for plot in plots:
        crop_states = {}
        for crop in crops:
            tiles = plot.tiles_for_crop(crop.crop_id)
            if tiles > 0:
                crop_states[crop.crop_id] = {
                    "tiles": tiles,
                    "active_day": 0,
                    "seeded": False,
                }
                if crop.regrow_days is not None and mods.fertilizer != "none":
                    seasons_count = 1
                    if plot.calendar.type == "seasons":
                        seasons_count = len(plot.calendar.seasons)
                    fertilizer_units[crop.crop_id] += tiles * seasons_count
        plot_state.append({"plot": plot, "crop_states": crop_states})

    kegs = max(0, kegs)
    keg_slots = [{"crop_id": None, "days_remaining": 0} for _ in range(kegs)]
    preserves_jars = max(0, preserves_jars)
    jar_slots = [{"crop_id": None, "days_remaining": 0} for _ in range(preserves_jars)]
    dehydrators = max(0, dehydrators)
    dehydrator_slots = [{"crop_id": None, "days_remaining": 0} for _ in range(dehydrators)]

    for day in range(max_days):
        # 1) advance kegs
        for slot in keg_slots:
            if slot["days_remaining"] > 0:
                slot["days_remaining"] -= 1
                if slot["days_remaining"] == 0 and slot["crop_id"] is not None:
                    crop_id = slot["crop_id"]
                    base_wine_from_kegs[crop_id] += 1
                    daily_base_wine[crop_id][day] += 1
                    slot["crop_id"] = None

        # 1b) advance preserves jars
        for slot in jar_slots:
            if slot["days_remaining"] > 0:
                slot["days_remaining"] -= 1
                if slot["days_remaining"] == 0 and slot["crop_id"] is not None:
                    crop_id = slot["crop_id"]
                    jelly_total[crop_id] += 1
                    slot["crop_id"] = None

        # 1c) advance dehydrators
        for slot in dehydrator_slots:
            if slot["days_remaining"] > 0:
                slot["days_remaining"] -= 1
                if slot["days_remaining"] == 0 and slot["crop_id"] is not None:
                    crop_id = slot["crop_id"]
                    dried_total[crop_id] += 1
                    slot["crop_id"] = None

        # 2) harvest per plot/crop on active days
        day_of_year = _day_of_year(start_day_of_year, day)
        for state in plot_state:
            plot = state["plot"]
            if not plot.calendar.is_active(day_of_year):
                continue
            for crop_id, crop_state in state["crop_states"].items():
                tiles = crop_state["tiles"]
                active_day = crop_state["active_day"]
                crop = crop_by_id[crop_id]
                first = first_by_crop[crop_id]
                if crop.regrow_days is None:
                    if active_day >= first and (active_day - first) % first == 0:
                        fruit_inv[crop_id] += tiles
                        fruit_total[crop_id] += tiles
                        seed_units[crop_id] += tiles
                        if mods.fertilizer != "none":
                            fertilizer_units[crop_id] += tiles
                else:
                    if not crop_state["seeded"]:
                        seed_units[crop_id] += tiles
                        crop_state["seeded"] = True
                    if active_day == first:
                        fruit_inv[crop_id] += tiles
                        fruit_total[crop_id] += tiles
                    elif active_day > first and (active_day - first) % crop.regrow_days == 0:
                        fruit_inv[crop_id] += tiles
                        fruit_total[crop_id] += tiles
                crop_state["active_day"] = active_day + 1

        # 2b) add external daily fruit (e.g., fruit trees)
        if external_daily_fruit:
            for crop_id, daily in external_daily_fruit.items():
                if day >= len(daily):
                    continue
                amount = int(daily[day])
                if amount <= 0:
                    continue
                if crop_id not in fruit_inv:
                    fruit_inv[crop_id] = 0
                    fruit_total[crop_id] = 0
                fruit_inv[crop_id] += amount
                fruit_total[crop_id] += amount

        # 3) start kegs after harvesting
        for slot in keg_slots:
            if slot["days_remaining"] != 0:
                continue
            crop_id = _pick_crop_by_priority(fruit_inv, priority)
            if crop_id is None:
                continue
            fruit_inv[crop_id] -= 1
            slot["crop_id"] = crop_id
            slot["days_remaining"] = KEG_DAYS

        # 4) start preserves jars
        for slot in jar_slots:
            if slot["days_remaining"] != 0:
                continue
            crop_id = _pick_crop_by_priority(fruit_inv, priority)
            if crop_id is None:
                continue
            fruit_inv[crop_id] -= 1
            slot["crop_id"] = crop_id
            slot["days_remaining"] = PRESERVES_JAR_DAYS

        # 5) start dehydrators (needs 5 fruit per batch)
        for slot in dehydrator_slots:
            if slot["days_remaining"] != 0:
                continue
            crop_id = _pick_crop_with_min(fruit_inv, priority, DEHYDRATOR_INPUT)
            if crop_id is None:
                continue
            fruit_inv[crop_id] -= DEHYDRATOR_INPUT
            slot["crop_id"] = crop_id
            slot["days_remaining"] = DEHYDRATOR_DAYS

    wine_in_kegs_end = {crop_id: 0 for crop_id in crop_ids}
    for slot in keg_slots:
        if slot["days_remaining"] > 0 and slot["crop_id"] is not None:
            wine_in_kegs_end[slot["crop_id"]] += 1

    jelly_in_jars_end = {crop_id: 0 for crop_id in crop_ids}
    for slot in jar_slots:
        if slot["days_remaining"] > 0 and slot["crop_id"] is not None:
            jelly_in_jars_end[slot["crop_id"]] += 1

    dried_in_dehydrators_end = {crop_id: 0 for crop_id in crop_ids}
    for slot in dehydrator_slots:
        if slot["days_remaining"] > 0 and slot["crop_id"] is not None:
            dried_in_dehydrators_end[slot["crop_id"]] += 1

    base_wine_total = base_wine_from_kegs.copy()
    batch_days = _cask_fill_days(max_days)
    casks_effective = max(0, casks)
    full_batch_met = True

    if cask_full_batch_required and casks_effective > 0:
        aged_full, base_sold_full, batch_fills = _simulate_cask_batches(
            daily_base_wine=daily_base_wine,
            starting_base_wine=starting_base_wine,
            casks=casks_effective,
            batch_days=batch_days,
            priority=priority,
            max_days=max_days,
        )
        full_batch_met = all(fill == casks_effective for fill in batch_fills)
        if full_batch_met:
            aged_wine = aged_full
            base_wine_sold = base_sold_full
        else:
            if casks_with_walkways is not None:
                casks_effective = min(casks_effective, max(0, casks_with_walkways))
            else:
                casks_effective = 0
            aged_wine, base_wine_sold, _ = _simulate_cask_batches(
                daily_base_wine=daily_base_wine,
                starting_base_wine=starting_base_wine,
                casks=casks_effective,
                batch_days=batch_days,
                priority=priority,
                max_days=max_days,
            )
    else:
        aged_wine, base_wine_sold, _ = _simulate_cask_batches(
            daily_base_wine=daily_base_wine,
            starting_base_wine=starting_base_wine,
            casks=casks_effective,
            batch_days=batch_days,
            priority=priority,
            max_days=max_days,
        )

    per_crop: dict[str, CropYearResult] = {}
    for crop_id in crop_ids:
        fruit_unprocessed = fruit_inv[crop_id]
        per_crop[crop_id] = CropYearResult(
            crop_id=crop_id,
            fruit_harvested=fruit_total[crop_id],
            fruit_unprocessed=fruit_unprocessed,
            fruit_sold=fruit_unprocessed,
            base_wine_produced=base_wine_total[crop_id],
            base_wine_sold=base_wine_sold[crop_id],
            aged_wine_produced=aged_wine[crop_id],
            wine_in_kegs_end=wine_in_kegs_end[crop_id],
            seed_units_used=seed_units[crop_id],
            fertilizer_units_used=fertilizer_units[crop_id],
            jelly_produced=jelly_total[crop_id],
            dried_fruit_produced=dried_total[crop_id],
            jelly_in_jars_end=jelly_in_jars_end[crop_id],
            dried_fruit_in_dehydrators_end=dried_in_dehydrators_end[crop_id],
        )

    total_fruit_unprocessed = sum(fruit_inv.values())
    total_wine_in_kegs_end = sum(wine_in_kegs_end.values())
    total_jelly = sum(jelly_total.values())
    total_dried_fruit = sum(dried_total.values())
    total_jelly_in_jars_end = sum(jelly_in_jars_end.values())
    total_dried_fruit_in_dehydrators_end = sum(dried_in_dehydrators_end.values())
    kegs_sufficient = total_fruit_unprocessed == 0 and total_wine_in_kegs_end == 0
    total_aged_wine = sum(aged_wine.values())
    total_base_wine_sold = sum(base_wine_sold.values())
    cask_uses = total_aged_wine / casks_effective if casks_effective > 0 else 0.0

    return YearSimulationResult(
        per_crop=per_crop,
        kegs_sufficient=kegs_sufficient,
        cask_uses_per_cask=cask_uses,
        casks_effective=casks_effective,
        full_cask_batch_met=full_batch_met,
        total_base_wine_sold=total_base_wine_sold,
        total_aged_wine=total_aged_wine,
        total_fruit_unprocessed=total_fruit_unprocessed,
        total_wine_in_kegs_end=total_wine_in_kegs_end,
        total_jelly=total_jelly,
        total_dried_fruit=total_dried_fruit,
        total_jelly_in_jars_end=total_jelly_in_jars_end,
        total_dried_fruit_in_dehydrators_end=total_dried_fruit_in_dehydrators_end,
    )
