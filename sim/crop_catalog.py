from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class DataError(RuntimeError):
    pass


DATA_DIR = Path(os.getenv("SIM_DATA_DIR", Path(__file__).resolve().parents[1] / "data"))


def _load_json(path: Path) -> Any:
    if not path.exists():
        raise DataError(f"Missing data file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class ObjectDef:
    item_id: str
    name: str | None
    display_name: str | None
    category: int | None
    price: int | None
    context_tags: tuple[str, ...]


@dataclass(frozen=True)
class CropDef:
    harvest_item_id: str
    seed_item_id: str
    name: str | None
    seasons: tuple[str, ...]
    days_in_phase: tuple[int, ...]
    regrow_days: int | None
    harvest_min_stack: int
    harvest_max_stack: int
    harvest_max_increase_per_level: float
    extra_harvest_chance: float
    needs_watering: bool
    is_paddy: bool
    is_raised: bool
    base_price: int | None
    seed_price: int | None
    seed_sources: dict[str, int | None]
    category: str


@dataclass(frozen=True)
class CropCatalog:
    by_harvest_id: dict[str, CropDef]
    by_seed_id: dict[str, CropDef]
    by_name: dict[str, CropDef]


@dataclass(frozen=True)
class ShopAccess:
    pierre: bool = True
    joja: bool = True
    oasis: bool = False
    traveling_cart: bool = False


@dataclass(frozen=True)
class SeedAvailability:
    purchasable: bool
    price: int | None
    sources: dict[str, int | None]


def load_objects_data(data_dir: Path = DATA_DIR, filename: str = "Objects.json") -> dict[str, ObjectDef]:
    override = os.getenv("SIM_OBJECTS_PATH")
    path = Path(override) if override else (data_dir / filename)
    if not path.exists():
        raise DataError(
            f"Missing data file: {path}. "
            "Copy Stardew Valley Content/Data/Objects.json into data/ or set SIM_OBJECTS_PATH."
        )
    raw = _load_json(path)
    objects: dict[str, ObjectDef] = {}
    for key, value in raw.items():
        item_id = str(key)
        if isinstance(value, str):
            # Legacy format: name/price/edibility/type/category/displayName/...
            parts = value.split("/")
            name = parts[0] if len(parts) > 0 else None
            try:
                price = int(parts[1]) if len(parts) > 1 else None
            except ValueError:
                price = None
            category = None
            if len(parts) > 3:
                try:
                    category = int(parts[3])
                except ValueError:
                    category = None
            display_name = parts[4] if len(parts) > 4 else name
            objects[item_id] = ObjectDef(
                item_id=item_id,
                name=name,
                display_name=display_name,
                category=category,
                price=price,
                context_tags=(),
            )
            continue

        if not isinstance(value, dict):
            continue
        name = value.get("Name") or value.get("InternalName")
        display_name = value.get("DisplayName") or name
        category_raw = value.get("Category")
        category = None
        if category_raw is not None:
            try:
                category = int(category_raw)
            except (TypeError, ValueError):
                category = None
        price_raw = value.get("Price") or value.get("SellPrice") or value.get("SalePrice")
        price = None
        if price_raw is not None:
            try:
                price = int(price_raw)
            except (TypeError, ValueError):
                price = None
        tags_raw = value.get("ContextTags") or []
        if isinstance(tags_raw, list):
            tags = tuple(str(t) for t in tags_raw)
        else:
            tags = ()
        objects[item_id] = ObjectDef(
            item_id=item_id,
            name=name,
            display_name=display_name,
            category=category,
            price=price,
            context_tags=tags,
        )
    return objects


def load_wiki_crop_rows(data_dir: Path = DATA_DIR, filename: str = "wiki_crops.json") -> list[dict[str, Any]]:
    path = data_dir / filename
    if not path.exists():
        return []
    return _load_json(path)


def _normalize_name(raw: str) -> str:
    return "".join(ch for ch in raw.lower() if ch.isalnum())


def _category_from_object(obj: ObjectDef | None) -> str:
    if obj is None:
        return "other"
    # Category codes: -79 fruit, -75 vegetable, -80 flower, -74 seed
    if obj.category == -79:
        return "fruit"
    if obj.category == -75:
        return "vegetable"
    if obj.category == -80:
        return "flower"
    if obj.context_tags:
        tags = " ".join(obj.context_tags).lower()
        if "fruit" in tags:
            return "fruit"
        if "vegetable" in tags:
            return "vegetable"
        if "flower" in tags:
            return "flower"
    return "other"


def seed_availability(
    crop: CropDef,
    access: ShopAccess,
) -> SeedAvailability:
    sources = crop.seed_sources or {}
    purchasable = False
    price = crop.seed_price
    if price is None:
        return SeedAvailability(purchasable=False, price=None, sources=sources)

    if access.pierre and sources.get("pierre"):
        purchasable = True
    if access.joja and sources.get("joja"):
        purchasable = True
    if access.oasis and sources.get("oasis"):
        purchasable = True
    if access.traveling_cart and sources.get("traveling_cart"):
        purchasable = True

    return SeedAvailability(purchasable=purchasable, price=price, sources=sources)


def load_crop_catalog(data_dir: Path = DATA_DIR) -> CropCatalog:
    crops_raw = _load_json(data_dir / "Crops.json")
    objects = load_objects_data(data_dir)
    wiki_rows = load_wiki_crop_rows(data_dir)
    wiki_by_name = {_normalize_name(row["name"]): row for row in wiki_rows if row.get("name")}
    wiki_by_seed = {_normalize_name(row["seed_name"]): row for row in wiki_rows if row.get("seed_name")}

    by_harvest: dict[str, CropDef] = {}
    by_seed: dict[str, CropDef] = {}
    by_name: dict[str, CropDef] = {}

    for seed_id, data in crops_raw.items():
        seed_item_id = str(seed_id)
        harvest_item_id = str(data.get("HarvestItemId") or "")
        if not harvest_item_id:
            continue
        seasons = tuple(s.lower() for s in data.get("Seasons", []) if s)
        days_in_phase = tuple(int(x) for x in data.get("DaysInPhase", []) if isinstance(x, (int, float)))
        regrow_days = data.get("RegrowDays")
        if regrow_days is None or int(regrow_days) <= 0:
            regrow = None
        else:
            regrow = int(regrow_days)

        harvest_min = int(data.get("HarvestMinStack", 1) or 1)
        harvest_max = int(data.get("HarvestMaxStack", harvest_min) or harvest_min)
        extra_chance = float(data.get("ExtraHarvestChance", 0.0) or 0.0)
        harvest_max_increase = float(data.get("HarvestMaxIncreasePerFarmingLevel", 0.0) or 0.0)

        needs_watering = bool(data.get("NeedsWatering", True))
        is_paddy = bool(data.get("IsPaddyCrop", False))
        is_raised = bool(data.get("IsRaised", False))

        harvest_obj = objects.get(harvest_item_id)
        seed_obj = objects.get(seed_item_id)
        name = (harvest_obj.display_name if harvest_obj and harvest_obj.display_name else None) or (
            seed_obj.display_name if seed_obj and seed_obj.display_name else None
        )
        wiki_row = wiki_by_name.get(_normalize_name(name)) if name else None
        if wiki_row is None and seed_obj and seed_obj.display_name:
            wiki_row = wiki_by_seed.get(_normalize_name(seed_obj.display_name))
        if wiki_row is None and seed_obj and seed_obj.name:
            wiki_row = wiki_by_seed.get(_normalize_name(seed_obj.name))

        base_price = harvest_obj.price if harvest_obj else None
        if base_price is None and wiki_row is not None:
            base_price = wiki_row.get("base_price")

        seed_price = None
        seed_sources: dict[str, int | None] = {}
        if wiki_row is not None:
            seed_price = wiki_row.get("seed_price")
            seed_sources = dict(wiki_row.get("seed_sources") or {})

        category = _category_from_object(harvest_obj)

        crop_def = CropDef(
            harvest_item_id=harvest_item_id,
            seed_item_id=seed_item_id,
            name=name,
            seasons=seasons,
            days_in_phase=days_in_phase,
            regrow_days=regrow,
            harvest_min_stack=harvest_min,
            harvest_max_stack=harvest_max,
            harvest_max_increase_per_level=harvest_max_increase,
            extra_harvest_chance=extra_chance,
            needs_watering=needs_watering,
            is_paddy=is_paddy,
            is_raised=is_raised,
            base_price=int(base_price) if base_price is not None else None,
            seed_price=int(seed_price) if seed_price is not None else None,
            seed_sources=seed_sources,
            category=category,
        )

        by_harvest[harvest_item_id] = crop_def
        by_seed[seed_item_id] = crop_def
        if name:
            by_name[_normalize_name(name)] = crop_def

    return CropCatalog(by_harvest_id=by_harvest, by_seed_id=by_seed, by_name=by_name)
