from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from collections import Counter
import re
import xml.etree.ElementTree as ET

from sim.animals import AnimalsConfig, BarnConfig, CoopConfig
from sim.bees import BeeConfig, FlowerPlan, FlowerSpec
from sim.fruit_trees import FruitTreesConfig, FRUIT_TREE_ID_TO_FRUIT
from sim.config import (
    AppConfig,
    EconomyConfig,
    GrowthConfig,
    SimulationConfig,
    StartingInventory,
    ProfessionsConfig,
    FarmingProfessions,
    ForagingProfessions,
    FishingProfessions,
    MiningProfessions,
    CombatProfessions,
    _normalize_crop_name,
    _normalize_fertilizer_name,
    _normalize_seasons,
    _parse_crop_int_map,
    _parse_fertilizer_cost_map,
)
from sim.validation import ValidationError, validate_app_config
from sim.plots import Plot, PlotCalendar


_PROFESSION_MAP = {
    0: ("farming", "rancher"),
    1: ("farming", "tiller"),
    2: ("farming", "coopmaster"),
    3: ("farming", "shepherd"),
    4: ("farming", "artisan"),
    5: ("farming", "agriculturist"),
    6: ("fishing", "fisher"),
    7: ("fishing", "trapper"),
    8: ("fishing", "angler"),
    9: ("fishing", "pirate"),
    10: ("fishing", "mariner"),
    11: ("fishing", "luremaster"),
    12: ("foraging", "forester"),
    13: ("foraging", "gatherer"),
    14: ("foraging", "lumberjack"),
    15: ("foraging", "tapper"),
    16: ("foraging", "botanist"),
    17: ("foraging", "tracker"),
    18: ("mining", "miner"),
    19: ("mining", "geologist"),
    20: ("mining", "blacksmith"),
    21: ("mining", "prospector"),
    22: ("mining", "excavator"),
    23: ("mining", "gemologist"),
    24: ("combat", "fighter"),
    25: ("combat", "scout"),
    26: ("combat", "brute"),
    27: ("combat", "defender"),
    28: ("combat", "acrobat"),
    29: ("combat", "desperado"),
}

_CHICKEN_TYPES = {"White Chicken", "Brown Chicken", "Blue Chicken"}
_VOID_CHICKEN_TYPES = {"Void Chicken"}
_GOLDEN_CHICKEN_TYPES = {"Golden Chicken"}
_COW_TYPES = {"White Cow", "Brown Cow"}
_GOAT_TYPES = {"Goat"}
_DUCK_TYPES = {"Duck"}
_PIG_TYPES = {"Pig"}
_RABBIT_TYPES = {"Rabbit"}
_SHEEP_TYPES = {"Sheep"}

_FERTILIZER_MAP = {
    "465": "speed_gro",
    "466": "deluxe_speed_gro",
    "918": "hyper_speed_gro",
}

_CASK_IDS = {"163", "108094"}
_OIL_MAKER_IDS = {"19", "108017"}
_QUALITY_SPRINKLER_IDS = {"621"}
_IRIDIUM_SPRINKLER_IDS = {"645"}
_QUALITY_SPRINKLER_NAMES = {"Quality Sprinkler"}
_IRIDIUM_SPRINKLER_NAMES = {"Iridium Sprinkler"}
_QUALITY_SPRINKLER_TILES = 8
_IRIDIUM_SPRINKLER_TILES = 24


def is_save_file(path: str | Path) -> bool:
    path = Path(path)
    if path.suffix.lower() in {".xml", ".sav"}:
        return True
    try:
        head = path.read_text(encoding="utf-8", errors="ignore")[:200]
    except FileNotFoundError:
        return False
    return "<SaveGame" in head


def load_config(path: str | Path, overrides_path: str | Path | None = None) -> AppConfig:
    """Load config from a save XML if provided, else JSON config."""
    if is_save_file(path):
        cfg = _load_from_save(path, overrides_path)
        validate_app_config(cfg)
        return cfg
    if overrides_path is not None:
        raise ValueError("Overrides are only supported when loading from a save file")
    cfg = AppConfig.from_json_file(path)
    validate_app_config(cfg)
    return cfg


def sprinkler_tiles_from_storage(path: str | Path) -> tuple[int, dict[str, int]]:
    """Return (tiles, counts) using sprinklers found in storage containers."""
    root = ET.fromstring(Path(path).read_text(encoding="utf-8"))
    counts = _count_sprinklers_in_storage(root)
    tiles = (counts["quality"] * _QUALITY_SPRINKLER_TILES) + (counts["iridium"] * _IRIDIUM_SPRINKLER_TILES)
    return tiles, counts


def sprinkler_tiles_from_save(path: str | Path) -> tuple[int, dict[str, int]]:
    """Return (tiles, counts) using placed + stored sprinklers."""
    root = ET.fromstring(Path(path).read_text(encoding="utf-8"))
    placed = _count_sprinklers_placed(root)
    storage = _count_sprinklers_in_storage(root)
    total_quality = placed["quality"] + storage["quality"]
    total_iridium = placed["iridium"] + storage["iridium"]
    tiles = (total_quality * _QUALITY_SPRINKLER_TILES) + (total_iridium * _IRIDIUM_SPRINKLER_TILES)
    return tiles, {
        "quality": total_quality,
        "iridium": total_iridium,
        "placed_quality": placed["quality"],
        "placed_iridium": placed["iridium"],
        "storage_quality": storage["quality"],
        "storage_iridium": storage["iridium"],
    }


def _load_from_save(path: str | Path, overrides_path: str | Path | None) -> AppConfig:
    root = ET.fromstring(Path(path).read_text(encoding="utf-8"))

    professions = _parse_professions(root)
    animals = _parse_animals(root)
    fruit_trees = _parse_fruit_trees(root)

    locations = _iter_locations(root)
    counts = _count_objects(locations)

    greenhouse_tiles, fertilizer = _parse_greenhouse(root)
    outdoor_tiles = _parse_outdoors(root)

    plots: list[Plot] = []
    if greenhouse_tiles:
        plots.append(
            Plot(
                name="greenhouse",
                tiles_by_crop=greenhouse_tiles,
                calendar=PlotCalendar(type="always"),
            )
        )
    if outdoor_tiles.get("starfruit", 0) > 0:
        plots.append(
            Plot(
                name="outdoors_starfruit",
                tiles_by_crop={"starfruit": outdoor_tiles["starfruit"]},
                calendar=PlotCalendar(type="seasons", seasons=("summer",)),
            )
        )
    if outdoor_tiles.get("ancient", 0) > 0:
        plots.append(
            Plot(
                name="outdoors_ancient",
                tiles_by_crop={"ancient": outdoor_tiles["ancient"]},
                calendar=PlotCalendar(type="seasons", seasons=("spring", "summer", "fall")),
            )
        )

    tiles = sum(p.tiles_total for p in plots)

    base_cfg = AppConfig(
        tiles=tiles,
        kegs=counts["kegs"],
        casks=counts["casks"],
        preserves_jars=counts["preserves_jars"],
        dehydrators=counts["dehydrators"],
        oil_makers=counts["oil_makers"],
        mayo_machines=counts["mayo_machines"],
        cheese_presses=counts["cheese_presses"],
        looms=counts["looms"],
        animals=animals,
        bees=BeeConfig(
            bee_houses=counts["bee_houses"],
            flower_base_price=0,
            seasons=("spring", "summer", "fall"),
            flower_plan={},
        ),
        fruit_trees=fruit_trees,
        professions=professions,
        crop="both",
        plots=plots,
        growth=GrowthConfig(
            fertilizer=fertilizer,
            agriculturist=professions.farming.agriculturist,
            paddy_bonus=False,
        ),
        simulation=SimulationConfig(),
        economy=EconomyConfig(),
        starting_inventory=StartingInventory(),
    )

    if overrides_path is None:
        return base_cfg

    overrides_raw = json.loads(Path(overrides_path).read_text(encoding="utf-8"))
    return _apply_overrides(base_cfg, overrides_raw)


def _parse_professions(root: ET.Element) -> ProfessionsConfig:
    player = root.find("player")
    if player is None:
        return ProfessionsConfig()
    profs = player.find("professions")
    if profs is None:
        return ProfessionsConfig()
    farming = {}
    foraging = {}
    fishing = {}
    mining = {}
    combat = {}
    for node in profs.findall("int"):
        try:
            pid = int(node.text or 0)
        except ValueError:
            continue
        entry = _PROFESSION_MAP.get(pid)
        if not entry:
            continue
        group, name = entry
        if group == "farming":
            farming[name] = True
        elif group == "foraging":
            foraging[name] = True
        elif group == "fishing":
            fishing[name] = True
        elif group == "mining":
            mining[name] = True
        elif group == "combat":
            combat[name] = True
    return ProfessionsConfig(
        farming=FarmingProfessions(**farming),
        foraging=ForagingProfessions(**foraging),
        fishing=FishingProfessions(**fishing),
        mining=MiningProfessions(**mining),
        combat=CombatProfessions(**combat),
    )


def _parse_animals(root: ET.Element) -> AnimalsConfig:
    farm = _find_location(root, "Farm")
    if farm is None:
        return AnimalsConfig()
    coops: list[CoopConfig] = []
    barns: list[BarnConfig] = []
    buildings = farm.find("buildings")
    if buildings is None:
        return AnimalsConfig()

    coop_idx = 1
    barn_idx = 1
    for b in buildings:
        building_type = (b.findtext("buildingType") or "").lower()
        indoors = b.find("indoors")
        if indoors is None:
            continue
        animals = indoors.find("animals")
        if animals is None:
            continue
        counts = Counter()
        for item in animals.findall("item"):
            val = item.find("value")
            if val is None:
                continue
            animal = val.find("FarmAnimal")
            if animal is None:
                continue
            animal_type = animal.findtext("type") or ""
            if animal_type in _CHICKEN_TYPES:
                counts["chickens"] += 1
            elif animal_type in _VOID_CHICKEN_TYPES:
                counts["void_chickens"] += 1
            elif animal_type in _GOLDEN_CHICKEN_TYPES:
                counts["chickens"] += 1
            elif animal_type in _DUCK_TYPES:
                counts["ducks"] += 1
            elif animal_type in _RABBIT_TYPES:
                counts["rabbits"] += 1
            elif animal_type in _COW_TYPES:
                counts["cows"] += 1
            elif animal_type in _GOAT_TYPES:
                counts["goats"] += 1
            elif animal_type in _PIG_TYPES:
                counts["pigs"] += 1
            elif animal_type in _SHEEP_TYPES:
                counts["sheep"] += 1
        if "coop" in building_type:
            capacity = _capacity_for_building(building_type, kind="coop")
            total = (
                counts.get("chickens", 0)
                + counts.get("void_chickens", 0)
                + counts.get("ducks", 0)
                + counts.get("rabbits", 0)
            )
            if total > capacity:
                raise ValidationError(
                    f"coop '{indoors.findtext('name')}' has {total} animals, exceeds capacity {capacity}"
                )
            coops.append(
                CoopConfig(
                    name=f"coop{coop_idx}",
                    chickens=counts.get("chickens", 0),
                    ducks=counts.get("ducks", 0),
                    rabbits=counts.get("rabbits", 0),
                    void_chickens=counts.get("void_chickens", 0),
                )
            )
            coop_idx += 1
        elif "barn" in building_type:
            capacity = _capacity_for_building(building_type, kind="barn")
            total = (
                counts.get("cows", 0)
                + counts.get("goats", 0)
                + counts.get("pigs", 0)
                + counts.get("sheep", 0)
            )
            if total > capacity:
                raise ValidationError(
                    f"barn '{indoors.findtext('name')}' has {total} animals, exceeds capacity {capacity}"
                )
            barns.append(
                BarnConfig(
                    name=f"barn{barn_idx}",
                    cows=counts.get("cows", 0),
                    goats=counts.get("goats", 0),
                    pigs=counts.get("pigs", 0),
                    sheep=counts.get("sheep", 0),
                )
            )
            barn_idx += 1

    return AnimalsConfig(coops=coops, barns=barns)


def _iter_locations(root: ET.Element) -> list[tuple[str, ET.Element]]:
    locations: list[tuple[str, ET.Element]] = []
    for loc in root.findall("locations/GameLocation"):
        name = loc.findtext("name") or "(unknown)"
        locations.append((name, loc))

    farm = _find_location(root, "Farm")
    if farm is None:
        return locations
    buildings = farm.find("buildings")
    if buildings is None:
        return locations
    for b in buildings:
        indoors = b.find("indoors")
        if indoors is None:
            continue
        in_name = indoors.findtext("name") or b.findtext("buildingType") or "(indoor)"
        locations.append((in_name, indoors))
    return locations


def _count_objects(locations: list[tuple[str, ET.Element]]) -> dict[str, int]:
    counts = {
        "kegs": 0,
        "casks": 0,
        "preserves_jars": 0,
        "dehydrators": 0,
        "oil_makers": 0,
        "mayo_machines": 0,
        "cheese_presses": 0,
        "looms": 0,
        "bee_houses": 0,
    }
    for loc_name, loc in locations:
        objects = loc.find("objects")
        if objects is None:
            continue
        for item in objects.findall("item"):
            value = item.find("value")
            if value is None:
                continue
            obj = value.find("Object")
            if obj is None:
                continue
            name = (obj.findtext("name") or "").strip()
            parent_sheet = (obj.findtext("parentSheetIndex") or "").strip()
            item_id = (obj.findtext("itemId") or "").strip()
            if name == "Keg":
                counts["kegs"] += 1
            elif name == "Preserves Jar":
                counts["preserves_jars"] += 1
            elif name == "Dehydrator":
                counts["dehydrators"] += 1
            elif name == "Mayonnaise Machine":
                counts["mayo_machines"] += 1
            elif name == "Cheese Press":
                counts["cheese_presses"] += 1
            elif name == "Loom":
                counts["looms"] += 1
            elif name == "Bee House":
                counts["bee_houses"] += 1
            elif name == "Oil Maker" or parent_sheet in _OIL_MAKER_IDS or item_id in _OIL_MAKER_IDS:
                counts["oil_makers"] += 1
            elif name == "Cask" or parent_sheet in _CASK_IDS or item_id in _CASK_IDS:
                if loc_name == "Cellar":
                    counts["casks"] += 1
    return counts


def _count_sprinklers_in_storage(root: ET.Element) -> dict[str, int]:
    """Count sprinklers found inside storage containers (not placed)."""
    counts = {"quality": 0, "iridium": 0}
    for _, loc in _iter_locations(root):
        objects = loc.find("objects")
        if objects is None:
            continue
        for item in objects.findall("item"):
            value = item.find("value")
            if value is None:
                continue
            obj = value.find("Object")
            if obj is None:
                continue
            items_node = obj.find("items")
            if items_node is None:
                continue
            for child in items_node.findall("Item"):
                if child.attrib.get("{http://www.w3.org/2001/XMLSchema-instance}nil") == "true":
                    continue
                item_node = child.find("Object") or child
                name = (item_node.findtext("name") or "").strip()
                parent_sheet = (item_node.findtext("parentSheetIndex") or "").strip()
                item_id = (item_node.findtext("itemId") or "").strip()
                stack = int(item_node.findtext("stack") or 1)
                if stack <= 0:
                    continue
                if _is_quality_sprinkler(name, parent_sheet, item_id):
                    counts["quality"] += stack
                elif _is_iridium_sprinkler(name, parent_sheet, item_id):
                    counts["iridium"] += stack
    return counts


def _count_sprinklers_placed(root: ET.Element) -> dict[str, int]:
    """Count sprinklers placed on the Farm (outdoors)."""
    counts = {"quality": 0, "iridium": 0}
    farm = _find_location(root, "Farm")
    if farm is None:
        return counts
    objects = farm.find("objects")
    if objects is None:
        return counts
    for item in objects.findall("item"):
        value = item.find("value")
        if value is None:
            continue
        obj = value.find("Object")
        if obj is None:
            continue
        name = (obj.findtext("name") or "").strip()
        parent_sheet = (obj.findtext("parentSheetIndex") or "").strip()
        item_id = (obj.findtext("itemId") or "").strip()
        if _is_quality_sprinkler(name, parent_sheet, item_id):
            counts["quality"] += 1
        elif _is_iridium_sprinkler(name, parent_sheet, item_id):
            counts["iridium"] += 1
    return counts


def _is_quality_sprinkler(name: str, parent_sheet: str, item_id: str) -> bool:
    if name in _QUALITY_SPRINKLER_NAMES:
        return True
    return parent_sheet in _QUALITY_SPRINKLER_IDS or item_id in _QUALITY_SPRINKLER_IDS


def _is_iridium_sprinkler(name: str, parent_sheet: str, item_id: str) -> bool:
    if name in _IRIDIUM_SPRINKLER_NAMES:
        return True
    return parent_sheet in _IRIDIUM_SPRINKLER_IDS or item_id in _IRIDIUM_SPRINKLER_IDS


def _parse_greenhouse(root: ET.Element) -> tuple[dict[str, int], str]:
    greenhouse = _find_location(root, "Greenhouse")
    if greenhouse is None:
        return {}, "none"
    terrain = greenhouse.find("terrainFeatures")
    if terrain is None:
        return {}, "none"
    crops: Counter[str] = Counter()
    fert_counts: Counter[str] = Counter()
    for item in terrain.findall("item"):
        tf = item.find("value/TerrainFeature")
        if tf is None:
            continue
        tf_type = tf.attrib.get("{http://www.w3.org/2001/XMLSchema-instance}type")
        if tf_type and tf_type != "HoeDirt":
            continue
        if tf_type is None and tf.tag != "TerrainFeature":
            continue
        fert = tf.findtext("fertilizer")
        if fert:
            fert_id = _extract_numeric_id(fert)
            if fert_id:
                fert_counts[fert_id] += 1
        crop = tf.find("crop")
        if crop is None:
            continue
        harvest = crop.findtext("indexOfHarvest")
        if harvest == "430":
            raise ValidationError("Found truffle crop in Greenhouse HoeDirt; truffles are not plantable crops.")
        if harvest == "268":
            crops["starfruit"] += 1
        elif harvest == "454":
            crops["ancient"] += 1

    fertilizer = "none"
    if fert_counts:
        fert_id, _ = fert_counts.most_common(1)[0]
        fertilizer = _FERTILIZER_MAP.get(fert_id, "none")

    return dict(crops), fertilizer


def _parse_outdoors(root: ET.Element) -> dict[str, int]:
    farm = _find_location(root, "Farm")
    if farm is None:
        return {"starfruit": 0, "ancient": 0}
    terrain = farm.find("terrainFeatures")
    if terrain is None:
        return {"starfruit": 0, "ancient": 0}
    crops: Counter[str] = Counter()
    for item in terrain.findall("item"):
        tf = item.find("value/TerrainFeature")
        if tf is None:
            continue
        tf_type = tf.attrib.get("{http://www.w3.org/2001/XMLSchema-instance}type")
        if tf_type and tf_type != "HoeDirt":
            continue
        crop = tf.find("crop")
        if crop is None:
            continue
        harvest = crop.findtext("indexOfHarvest")
        if harvest == "430":
            raise ValidationError("Found truffle crop in Farm HoeDirt; truffles are forage items, not crops.")
        if harvest == "268":
            crops["starfruit"] += 1
        elif harvest == "454":
            crops["ancient"] += 1
    return {"starfruit": crops.get("starfruit", 0), "ancient": crops.get("ancient", 0)}


def _parse_fruit_trees(root: ET.Element) -> FruitTreesConfig:
    """Parse mature fruit trees from the save file."""
    greenhouse: Counter[str] = Counter()
    outdoors: Counter[str] = Counter()
    always: Counter[str] = Counter()
    for loc in root.findall("locations/GameLocation"):
        loc_name = (loc.findtext("name") or "").strip()
        terrain = loc.find("terrainFeatures")
        if terrain is None:
            continue
        for item in terrain.findall("item"):
            tf = item.find("value/TerrainFeature")
            if tf is None:
                continue
            tf_type = tf.attrib.get("{http://www.w3.org/2001/XMLSchema-instance}type")
            if tf_type != "FruitTree":
                continue
            days_until_mature = int(tf.findtext("daysUntilMature") or 0)
            if days_until_mature > 0:
                continue
            if (tf.findtext("stump") or "").lower() == "true":
                continue
            tree_id = (tf.findtext("treeId") or "").strip()
            fruit_id = FRUIT_TREE_ID_TO_FRUIT.get(tree_id)
            if not fruit_id:
                continue
            greenhouse_flag = (tf.findtext("greenHouseTileTree") or "").lower() == "true"
            if loc_name == "Greenhouse" or greenhouse_flag:
                greenhouse[fruit_id] += 1
            elif loc_name.lower().startswith("island"):
                always[fruit_id] += 1
            else:
                outdoors[fruit_id] += 1

    return FruitTreesConfig(
        greenhouse=dict(greenhouse),
        outdoors=dict(outdoors),
        always=dict(always),
    )


def _find_location(root: ET.Element, name: str) -> ET.Element | None:
    for loc in root.findall("locations/GameLocation"):
        if loc.findtext("name") == name:
            return loc
    return None


def _extract_numeric_id(raw: str) -> str | None:
    match = re.search(r"(\d+)", raw)
    if not match:
        return None
    return match.group(1)


def _capacity_for_building(building_type: str, kind: str) -> int:
    name = building_type.lower()
    if kind == "coop":
        if "deluxe" in name:
            return 12
        if "big" in name:
            return 8
        return 4
    if kind == "barn":
        if "deluxe" in name:
            return 12
        if "big" in name:
            return 8
        return 4
    return 12


def _apply_overrides(base_cfg: AppConfig, raw: dict) -> AppConfig:
    growth_raw = raw.get("growth", {})
    economy_raw = raw.get("economy", {})
    sim_raw = raw.get("simulation", {})
    inventory_raw = raw.get("starting_inventory", {})
    bees_raw = raw.get("bees", {})
    fruit_tree_raw = raw.get("fruit_trees", {})

    growth = replace(
        base_cfg.growth,
        fertilizer=_normalize_fertilizer_name(growth_raw.get("fertilizer", base_cfg.growth.fertilizer)),
        paddy_bonus=bool(growth_raw.get("paddy_bonus", base_cfg.growth.paddy_bonus)),
        agriculturist=base_cfg.professions.farming.agriculturist,
    )

    economy = EconomyConfig(
        wine_price=_parse_crop_int_map(economy_raw.get("wine_price")),
        fruit_price=_parse_crop_int_map(economy_raw.get("fruit_price")),
        seed_cost=_parse_crop_int_map(economy_raw.get("seed_cost")),
        fertilizer_cost=_parse_fertilizer_cost_map(economy_raw.get("fertilizer_cost")),
        aged_wine_multiplier=float(economy_raw.get("aged_wine_multiplier", base_cfg.economy.aged_wine_multiplier)),
        wine_quality_multiplier=float(economy_raw.get("wine_quality_multiplier", base_cfg.economy.wine_quality_multiplier)),
        fruit_quality_multiplier=float(economy_raw.get("fruit_quality_multiplier", base_cfg.economy.fruit_quality_multiplier)),
        artisan=base_cfg.professions.farming.artisan,
        tiller=base_cfg.professions.farming.tiller,
        cask_full_batch_required=bool(economy_raw.get("cask_full_batch_required", base_cfg.economy.cask_full_batch_required)),
        casks_with_walkways=(
            int(economy_raw["casks_with_walkways"]) if "casks_with_walkways" in economy_raw else base_cfg.economy.casks_with_walkways
        ),
    )

    simulation = replace(
        base_cfg.simulation,
        max_days=int(sim_raw.get("max_days", base_cfg.simulation.max_days)),
        assume_year_round=bool(sim_raw.get("assume_year_round", base_cfg.simulation.assume_year_round)),
        start_day_of_year=int(sim_raw.get("start_day_of_year", base_cfg.simulation.start_day_of_year)),
    )

    starting_inventory = StartingInventory(
        fruit=_parse_crop_int_map(inventory_raw.get("fruit")),
        base_wine=_parse_crop_int_map(inventory_raw.get("base_wine")),
    )

    flower_plan_raw = bees_raw.get("flower_plan", {})
    flower_plan: dict[str, FlowerPlan] = {}
    if isinstance(flower_plan_raw, dict):
        for season_key, plan in flower_plan_raw.items():
            season = _normalize_seasons(season_key)[0]
            if not isinstance(plan, dict):
                raise ValueError("bees.flower_plan entries must be objects")
            fast = plan.get("fast", {})
            expensive = plan.get("expensive", {})
            flower_plan[season] = FlowerPlan(
                fast=FlowerSpec(
                    name=str(fast.get("name", "fast")),
                    growth_days=int(fast.get("growth_days", 0)),
                    base_price=int(fast.get("base_price", 0)),
                ),
                expensive=FlowerSpec(
                    name=str(expensive.get("name", "expensive")),
                    growth_days=int(expensive.get("growth_days", 0)),
                    base_price=int(expensive.get("base_price", 0)),
                ),
            )

    seasons_raw = bees_raw.get("seasons")
    if seasons_raw is None and flower_plan:
        seasons = tuple(flower_plan.keys())
    else:
        seasons = _normalize_seasons(seasons_raw or base_cfg.bees.seasons)

    bees = replace(
        base_cfg.bees,
        flower_base_price=int(bees_raw.get("flower_base_price", base_cfg.bees.flower_base_price)),
        seasons=seasons,
        flower_plan=flower_plan or base_cfg.bees.flower_plan,
    )

    fruit_trees = base_cfg.fruit_trees
    if fruit_tree_raw:
        fruit_trees = replace(
            fruit_trees,
            greenhouse=_parse_crop_int_map(fruit_tree_raw.get("greenhouse")) or fruit_trees.greenhouse,
            outdoors=_parse_crop_int_map(fruit_tree_raw.get("outdoors")) or fruit_trees.outdoors,
            always=_parse_crop_int_map(fruit_tree_raw.get("always")) or fruit_trees.always,
        )

    crop = base_cfg.crop
    if "crop" in raw:
        crop = _normalize_crop_name(raw.get("crop"))

    return replace(
        base_cfg,
        growth=growth,
        economy=economy,
        simulation=simulation,
        starting_inventory=starting_inventory,
        bees=bees,
        fruit_trees=fruit_trees,
        crop=crop,
    )
