from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
import xml.etree.ElementTree as ET

from sim.crop_catalog import CropCatalog, CropDef, ShopAccess
from sim.save_loader import (
    _parse_professions,
    _parse_animals,
    _parse_fruit_trees,
    _extract_numeric_id,
)
from sim.config import ProfessionsConfig


_FERTILIZER_MAP = {
    "465": "speed_gro",
    "466": "deluxe_speed_gro",
    "918": "hyper_speed_gro",
}

_CASK_IDS = {"163", "108094"}
_OIL_MAKER_IDS = {"19", "108017"}
_SEED_MAKER_NAMES = {"Seed Maker"}
_QUALITY_SPRINKLER_IDS = {"621"}
_IRIDIUM_SPRINKLER_IDS = {"645"}
_QUALITY_SPRINKLER_NAMES = {"Quality Sprinkler"}
_IRIDIUM_SPRINKLER_NAMES = {"Iridium Sprinkler"}
_QUALITY_SPRINKLER_TILES = 8
_IRIDIUM_SPRINKLER_TILES = 24


@dataclass(frozen=True)
class MachineCounts:
    kegs: int = 0
    casks: int = 0
    preserves_jars: int = 0
    dehydrators: int = 0
    oil_makers: int = 0
    mayo_machines: int = 0
    cheese_presses: int = 0
    looms: int = 0
    bee_houses: int = 0
    seed_makers: int = 0


@dataclass
class CropInstance:
    crop: CropDef
    days_until_harvest: int
    is_regrowing: bool
    extra_buffer: float = 0.0


@dataclass
class TileState:
    location: str
    x: int
    y: int
    fertilizer: str
    watered: bool
    crop: CropInstance | None = None


@dataclass(frozen=True)
class FarmState:
    start_day_of_year: int
    season: str
    day_of_month: int
    year: int
    farming_level: int
    professions: ProfessionsConfig
    machines: MachineCounts
    shop_access: ShopAccess
    tiles: list[TileState] = field(default_factory=list)
    seed_inventory: dict[str, int] = field(default_factory=dict)
    animals: object = None
    fruit_trees: object = None
    bees: object = None


@dataclass(frozen=True)
class SprinklerCoverage:
    by_location: dict[str, set[tuple[int, int]]]


def parse_save_state(path: str | Path, catalog: CropCatalog, seed_category_ids: set[int] | None = None) -> FarmState:
    root = ET.fromstring(Path(path).read_text(encoding="utf-8"))

    season = (root.findtext("currentSeason") or "").strip().lower()
    if not season:
        raise ValueError("save file missing currentSeason")
    day_raw = root.findtext("dayOfMonth")
    if day_raw is None:
        raise ValueError("save file missing dayOfMonth")
    day_of_month = int(day_raw)
    year = int(root.findtext("year") or 1)

    start_day_of_year = _day_of_year_from_season_day(season, day_of_month)

    player = root.find("player")
    farming_level = 0
    if player is not None:
        try:
            farming_level = int(player.findtext("farmingLevel") or 0)
        except ValueError:
            farming_level = 0

    professions = _parse_professions(root)
    animals = _parse_animals(root)
    fruit_trees = _parse_fruit_trees(root)

    locations = _iter_locations(root)
    machines = _count_machines(locations)
    sprinklers = _sprinkler_coverage(locations)

    seed_inventory = _collect_seed_inventory(root, seed_category_ids=seed_category_ids)

    tiles: list[TileState] = []
    for loc_name, loc in locations:
        terrain = loc.find("terrainFeatures")
        if terrain is None:
            continue
        watered_tiles = sprinklers.by_location.get(loc_name, set())
        for item in terrain.findall("item"):
            key = item.find("key/Vector2")
            if key is None:
                continue
            x_text = key.findtext("X")
            y_text = key.findtext("Y")
            if x_text is None or y_text is None:
                continue
            x = int(float(x_text))
            y = int(float(y_text))

            tf = item.find("value/TerrainFeature")
            if tf is None:
                continue
            tf_type = tf.attrib.get("{http://www.w3.org/2001/XMLSchema-instance}type")
            if tf_type and tf_type != "HoeDirt":
                continue

            fertilizer = _fertilizer_from_hoedirt(tf)
            watered = (x, y) in watered_tiles

            crop_node = tf.find("crop")
            crop_instance: CropInstance | None = None
            if crop_node is not None:
                if (crop_node.findtext("dead") or "").lower() == "true":
                    crop_node = None
                else:
                    harvest_id = str(crop_node.findtext("indexOfHarvest") or "")
                    crop_def = catalog.by_harvest_id.get(harvest_id)
                    if crop_def is None:
                        continue
                    days_until = _days_until_next_harvest(crop_node, crop_def)
                    is_regrowing = _crop_is_regrowing(crop_node)
                    crop_instance = CropInstance(
                        crop=crop_def,
                        days_until_harvest=days_until,
                        is_regrowing=is_regrowing,
                    )

            tiles.append(
                TileState(
                    location=loc_name,
                    x=x,
                    y=y,
                    fertilizer=fertilizer,
                    watered=watered,
                    crop=crop_instance,
                )
            )

    shop_access = _shop_access(root)

    return FarmState(
        start_day_of_year=start_day_of_year,
        season=season,
        day_of_month=day_of_month,
        year=year,
        farming_level=farming_level,
        professions=professions,
        machines=machines,
        shop_access=shop_access,
        tiles=tiles,
        seed_inventory=seed_inventory,
        animals=animals,
        fruit_trees=fruit_trees,
        bees=None,
    )


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


def _find_location(root: ET.Element, name: str) -> ET.Element | None:
    for loc in root.findall("locations/GameLocation"):
        if loc.findtext("name") == name:
            return loc
    return None


def _count_machines(locations: list[tuple[str, ET.Element]]) -> MachineCounts:
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
        "seed_makers": 0,
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
            elif name in _SEED_MAKER_NAMES:
                counts["seed_makers"] += 1
            elif name == "Oil Maker" or parent_sheet in _OIL_MAKER_IDS or item_id in _OIL_MAKER_IDS:
                counts["oil_makers"] += 1
            elif name == "Cask" or parent_sheet in _CASK_IDS or item_id in _CASK_IDS:
                if loc_name == "Cellar":
                    counts["casks"] += 1
    return MachineCounts(**counts)


def _sprinkler_coverage(locations: list[tuple[str, ET.Element]]) -> SprinklerCoverage:
    coverage: dict[str, set[tuple[int, int]]] = {}
    for loc_name, loc in locations:
        objects = loc.find("objects")
        if objects is None:
            continue
        for item in objects.findall("item"):
            key = item.find("key/Vector2")
            value = item.find("value")
            if key is None or value is None:
                continue
            obj = value.find("Object")
            if obj is None:
                continue
            name = (obj.findtext("name") or "").strip()
            parent_sheet = (obj.findtext("parentSheetIndex") or "").strip()
            item_id = (obj.findtext("itemId") or "").strip()
            x_text = key.findtext("X")
            y_text = key.findtext("Y")
            if x_text is None or y_text is None:
                continue
            x = int(float(x_text))
            y = int(float(y_text))

            is_quality = name in _QUALITY_SPRINKLER_NAMES or parent_sheet in _QUALITY_SPRINKLER_IDS or item_id in _QUALITY_SPRINKLER_IDS
            is_iridium = name in _IRIDIUM_SPRINKLER_NAMES or parent_sheet in _IRIDIUM_SPRINKLER_IDS or item_id in _IRIDIUM_SPRINKLER_IDS
            if not (is_quality or is_iridium):
                continue
            tiles = coverage.setdefault(loc_name, set())
            radius = 1 if is_quality else 2
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    if dx == 0 and dy == 0:
                        continue
                    tiles.add((x + dx, y + dy))
    return SprinklerCoverage(by_location=coverage)


def _fertilizer_from_hoedirt(tf: ET.Element) -> str:
    fert = tf.findtext("fertilizer")
    if not fert:
        return "none"
    fert_id = _extract_numeric_id(fert)
    if not fert_id:
        return "none"
    return _FERTILIZER_MAP.get(fert_id, "none")


def _day_of_year_from_season_day(season: str, day_of_month: int) -> int:
    season = season.lower()
    season_index = {"spring": 0, "summer": 1, "fall": 2, "winter": 3}.get(season)
    if season_index is None:
        raise ValueError(f"Unknown season: {season}")
    return season_index * 28 + day_of_month


def _days_until_next_harvest(crop_node: ET.Element, crop_def: CropDef) -> int:
    phase_days = [int(node.text or 0) for node in crop_node.findall("phaseDays/int")]
    phase_days = [d for d in phase_days if d < 99999]
    current_phase = int(crop_node.findtext("currentPhase") or 0)
    day_of_phase = int(crop_node.findtext("dayOfCurrentPhase") or 0)
    full_grown = _crop_is_regrowing(crop_node)
    if full_grown and crop_def.regrow_days:
        return max(0, crop_def.regrow_days - day_of_phase)
    if current_phase < 0:
        current_phase = 0
    if current_phase >= len(phase_days):
        return 0
    remaining = sum(phase_days[current_phase:]) - day_of_phase
    return max(0, remaining)


def _crop_is_regrowing(crop_node: ET.Element) -> bool:
    full_grown = (crop_node.findtext("fullGrown") or "").lower() == "true"
    if full_grown:
        return True
    fully_grown = (crop_node.findtext("fullyGrown") or "").lower() == "true"
    return fully_grown


def _collect_seed_inventory(root: ET.Element, seed_category_ids: set[int] | None = None) -> dict[str, int]:
    seed_category_ids = seed_category_ids or {-74}
    seeds: dict[str, int] = {}

    for item in _iter_items(root):
        item_id = item.findtext("itemId")
        if not item_id:
            continue
        cat = item.findtext("category")
        if cat is None:
            continue
        try:
            cat_int = int(cat)
        except ValueError:
            continue
        if cat_int not in seed_category_ids:
            continue
        stack = int(item.findtext("stack") or 1)
        if stack <= 0:
            continue
        seeds[item_id] = seeds.get(item_id, 0) + stack

    return seeds


def _shop_access(root: ET.Element) -> ShopAccess:
    player = root.find("player")
    mails: set[str] = set()
    if player is not None:
        mail = player.find("mailReceived")
        if mail is not None:
            mails = {m.text for m in mail.findall("string") if m.text}
    oasis = any(key in mails for key in ("ccVault", "ccVaultComplete", "ccVaultDone"))
    island = any("Island" in (key or "") for key in mails)
    return ShopAccess(pierre=True, joja=True, oasis=oasis, traveling_cart=False)


def _iter_items(root: ET.Element) -> Iterable[ET.Element]:
    # Player inventory items
    player = root.find("player")
    if player is not None:
        items = player.find("items")
        if items is not None:
            for item in items.findall("Item"):
                if item.attrib.get("{http://www.w3.org/2001/XMLSchema-instance}nil") == "true":
                    continue
                yield item

    # Items inside storage objects
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
                yield item_node
