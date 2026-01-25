from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Any
import json
from pathlib import Path
from typing import Sequence
from .plots import Plot, PlotCalendar, day_of_year_from_season_day
from .animals import AnimalsConfig, CoopConfig, BarnConfig
from .bees import BeeConfig, FlowerPlan, FlowerSpec
from .fruit_trees import FruitTreesConfig, normalize_fruit_tree_name

Fertilizer = Literal["none", "speed_gro", "deluxe_speed_gro", "hyper_speed_gro"]
CropName = Literal["ancient", "starfruit", "both"]


@dataclass(frozen=True)
class GrowthConfig:
    fertilizer: Fertilizer = "none"
    agriculturist: bool = False
    # Included for completeness; not relevant to starfruit/ancient fruit.
    # (In-game it's a +25% speedIncrease when paddy-watered.)
    paddy_bonus: bool = False


@dataclass(frozen=True)
class FarmingProfessions:
    rancher: bool = False
    tiller: bool = False
    coopmaster: bool = False
    shepherd: bool = False
    artisan: bool = False
    agriculturist: bool = False


@dataclass(frozen=True)
class ForagingProfessions:
    forester: bool = False
    gatherer: bool = False
    lumberjack: bool = False
    tapper: bool = False
    botanist: bool = False
    tracker: bool = False


@dataclass(frozen=True)
class FishingProfessions:
    fisher: bool = False
    trapper: bool = False
    angler: bool = False
    pirate: bool = False
    mariner: bool = False
    luremaster: bool = False


@dataclass(frozen=True)
class MiningProfessions:
    miner: bool = False
    geologist: bool = False
    blacksmith: bool = False
    prospector: bool = False
    excavator: bool = False
    gemologist: bool = False


@dataclass(frozen=True)
class CombatProfessions:
    fighter: bool = False
    scout: bool = False
    brute: bool = False
    defender: bool = False
    acrobat: bool = False
    desperado: bool = False


@dataclass(frozen=True)
class ProfessionsConfig:
    farming: FarmingProfessions = FarmingProfessions()
    foraging: ForagingProfessions = ForagingProfessions()
    fishing: FishingProfessions = FishingProfessions()
    mining: MiningProfessions = MiningProfessions()
    combat: CombatProfessions = CombatProfessions()


@dataclass(frozen=True)
class SimulationConfig:
    max_days: int = 112
    assume_year_round: bool = True
    start_day_of_year: int = 1


@dataclass(frozen=True)
class EconomyConfig:
    """Economy settings for profit calculations."""

    wine_price: dict[str, int] = field(default_factory=dict)
    fruit_price: dict[str, int] = field(default_factory=dict)
    seed_cost: dict[str, int] = field(default_factory=dict)
    fertilizer_cost: dict[str, int] = field(default_factory=dict)
    aged_wine_multiplier: float = 2.0
    wine_quality_multiplier: float = 1.0
    fruit_quality_multiplier: float = 1.0
    artisan: bool = False
    tiller: bool = False
    cask_full_batch_required: bool = False
    casks_with_walkways: int | None = None


@dataclass(frozen=True)
class StartingInventory:
    """Starting inventories at Spring 1."""

    fruit: dict[str, int] = field(default_factory=dict)
    base_wine: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class AppConfig:
    tiles: int
    kegs: int
    casks: int
    preserves_jars: int = 0
    dehydrators: int = 0
    oil_makers: int = 0
    mayo_machines: int = 0
    cheese_presses: int = 0
    looms: int = 0
    animals: AnimalsConfig = AnimalsConfig()
    bees: BeeConfig = BeeConfig()
    fruit_trees: FruitTreesConfig = FruitTreesConfig()
    professions: ProfessionsConfig = ProfessionsConfig()
    crop: CropName = "both"
    plots: Sequence[Plot] = ()
    growth: GrowthConfig = GrowthConfig()
    simulation: SimulationConfig = SimulationConfig()
    economy: EconomyConfig = EconomyConfig()
    starting_inventory: StartingInventory = StartingInventory()

    @staticmethod
    def from_json_file(path: str | Path) -> "AppConfig":
        """Load config from a JSON file on disk."""
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return AppConfig.from_dict(raw)

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> "AppConfig":
        """Build config from a decoded JSON dict."""
        growth_raw = raw.get("growth", {})
        sim_raw = raw.get("simulation", {})
        economy_raw = raw.get("economy", {})
        inventory_raw = raw.get("starting_inventory", {})
        animals_raw = raw.get("animals", {})
        bees_raw = raw.get("bees", {})
        professions_raw = raw.get("professions")

        crop_raw = raw.get("crop", "both")
        crop = _normalize_crop_name(crop_raw)

        professions = _parse_professions_config(professions_raw, growth_raw, economy_raw)

        growth = GrowthConfig(
            fertilizer=_normalize_fertilizer_name(growth_raw.get("fertilizer", "none")),
            agriculturist=professions.farming.agriculturist,
            paddy_bonus=bool(growth_raw.get("paddy_bonus", False)),
        )
        start_day_raw = sim_raw.get("start_day_of_year")
        cal_raw = sim_raw.get("calendar", {})
        if start_day_raw is None and isinstance(cal_raw, dict) and cal_raw:
            season_raw = cal_raw.get("current_season")
            day_raw = cal_raw.get("day")
            if season_raw is not None and day_raw is not None:
                start_day_raw = day_of_year_from_season_day(
                    _normalize_season(season_raw),
                    int(day_raw),
                )
        sim = SimulationConfig(
            max_days=112,
            assume_year_round=bool(sim_raw.get("assume_year_round", True)),
            start_day_of_year=int(start_day_raw or 1),
        )
        economy = EconomyConfig(
            wine_price=_parse_crop_int_map(economy_raw.get("wine_price")),
            fruit_price=_parse_crop_int_map(economy_raw.get("fruit_price")),
            seed_cost=_parse_crop_int_map(economy_raw.get("seed_cost")),
            fertilizer_cost=_parse_fertilizer_cost_map(economy_raw.get("fertilizer_cost")),
            aged_wine_multiplier=float(economy_raw.get("aged_wine_multiplier", 2.0)),
            wine_quality_multiplier=float(economy_raw.get("wine_quality_multiplier", 1.0)),
            fruit_quality_multiplier=float(economy_raw.get("fruit_quality_multiplier", 1.0)),
            artisan=professions.farming.artisan,
            tiller=professions.farming.tiller,
            cask_full_batch_required=bool(economy_raw.get("cask_full_batch_required", False)),
            casks_with_walkways=(
                int(economy_raw["casks_with_walkways"]) if "casks_with_walkways" in economy_raw else None
            ),
        )
        starting_inventory = StartingInventory(
            fruit=_parse_crop_int_map(inventory_raw.get("fruit")),
            base_wine=_parse_crop_int_map(inventory_raw.get("base_wine")),
        )

        coops = []
        for c in animals_raw.get("coops", []):
            coops.append(
                CoopConfig(
                    name=str(c.get("name", "coop")),
                    chickens=int(c.get("chickens", 0)),
                    ducks=int(c.get("ducks", 0)),
                    rabbits=int(c.get("rabbits", 0)),
                    void_chickens=int(c.get("void_chickens", 0)),
                )
            )
        barns = []
        for b in animals_raw.get("barns", []):
            barns.append(
                BarnConfig(
                    name=str(b.get("name", "barn")),
                    cows=int(b.get("cows", 0)),
                    goats=int(b.get("goats", 0)),
                    pigs=int(b.get("pigs", 0)),
                    sheep=int(b.get("sheep", 0)),
                )
            )
        animals = AnimalsConfig(
            coops=coops,
            barns=barns,
            large_egg_rate=float(animals_raw.get("large_egg_rate", 0.0)),
            large_milk_rate=float(animals_raw.get("large_milk_rate", 0.0)),
            large_goat_milk_rate=float(animals_raw.get("large_goat_milk_rate", 0.0)),
            rabbit_foot_rate=float(animals_raw.get("rabbit_foot_rate", 0.0)),
        )
        flower_plan_raw = bees_raw.get("flower_plan", {})
        flower_plan: dict[str, FlowerPlan] = {}
        if isinstance(flower_plan_raw, dict):
            for season_key, plan in flower_plan_raw.items():
                season = _normalize_season(season_key)
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
            seasons = _normalize_seasons(seasons_raw or ("spring", "summer", "fall"))

        bees = BeeConfig(
            bee_houses=int(bees_raw.get("bee_houses", 0)),
            flower_base_price=int(bees_raw.get("flower_base_price", 0)),
            seasons=seasons,
            flower_plan=flower_plan,
        )

        plots_raw = raw.get("plots", [])
        plots = []
        for p in plots_raw:
            cal_raw = p.get("calendar", {"type": "always"})
            plots.append(
                Plot(
                    name=p.get("name", "plot"),
                    tiles_by_crop=_parse_plot_tiles(p.get("tiles")),
                    calendar=PlotCalendar(
                        type=cal_raw.get("type", "always"),
                        seasons=_normalize_seasons(cal_raw.get("seasons", ())),
                    ),
                )
            )
        tiles_raw = raw.get("tiles")
        if tiles_raw is None:
            if plots:
                tiles = sum(p.tiles_total for p in plots)
            else:
                raise KeyError("tiles")
        else:
            tiles = int(tiles_raw)
        fruit_tree_raw = raw.get("fruit_trees", {})
        fruit_trees = FruitTreesConfig(
            greenhouse=_parse_crop_int_map(fruit_tree_raw.get("greenhouse")),
            outdoors=_parse_crop_int_map(fruit_tree_raw.get("outdoors")),
            always=_parse_crop_int_map(fruit_tree_raw.get("always")),
        )
        return AppConfig(
            tiles=tiles,
            kegs=int(raw["kegs"]),
            casks=int(raw["casks"]),
            preserves_jars=int(raw.get("preserves_jars", 0)),
            dehydrators=int(raw.get("dehydrators", 0)),
            oil_makers=int(raw.get("oil_makers", 0)),
            mayo_machines=int(raw.get("mayo_machines", 0)),
            cheese_presses=int(raw.get("cheese_presses", 0)),
            looms=int(raw.get("looms", 0)),
            animals=animals,
            bees=bees,
            fruit_trees=fruit_trees,
            professions=professions,
            crop=crop,
            growth=growth,
            simulation=sim,
            plots=plots,
            economy=economy,
            starting_inventory=starting_inventory,
        )


def _normalize_crop_name(raw: Any) -> CropName:
    """Normalize crop identifiers to the supported config values."""
    if raw is None:
        return "both"
    key = str(raw).strip().lower()
    if key in ("both", "all"):
        return "both"
    norm = key.replace(" ", "").replace("_", "").replace("-", "")
    if norm in ("ancientfruit", "ancient"):
        return "ancient"
    if norm in ("starfruit", "star"):
        return "starfruit"
    raise ValueError(f"Unknown crop name: {raw}")


def _normalize_fertilizer_name(raw: Any) -> Fertilizer:
    """Normalize fertilizer identifiers to canonical values."""
    key = str(raw).strip().lower()
    if key in ("none", "no"):
        return "none"
    norm = key.replace(" ", "").replace("_", "").replace("-", "")
    if norm in ("speedgro",):
        return "speed_gro"
    if norm in ("deluxespeedgro", "deluxesg"):
        return "deluxe_speed_gro"
    if norm in ("hyperspeedgro", "hypersg"):
        return "hyper_speed_gro"
    raise ValueError(f"Unknown fertilizer: {raw}")


def _normalize_season(raw: Any) -> str:
    """Normalize season identifiers to lowercase canonical values."""
    key = str(raw).strip().lower()
    if key not in ("spring", "summer", "fall", "winter"):
        raise ValueError(f"Unknown season: {raw}")
    return key


def _normalize_seasons(raw: Any) -> tuple[str, ...]:
    """Normalize a season list or scalar into a tuple of seasons."""
    if raw is None:
        return ()
    if isinstance(raw, (list, tuple)):
        return tuple(_normalize_season(v) for v in raw)
    return (_normalize_season(raw),)


def _parse_plot_tiles(raw: Any) -> dict[str, int]:
    """Parse plot tiles as either an int or per-crop mapping."""
    if raw is None:
        raise KeyError("plots[].tiles")
    if isinstance(raw, dict):
        tiles_by_crop: dict[str, int] = {}
        for key, value in raw.items():
            crop_id = _normalize_crop_name(key)
            if crop_id == "both":
                raise ValueError("plots[].tiles cannot use 'both' as a key")
            tiles_by_crop[crop_id] = int(value)
        return tiles_by_crop
    return {"all": int(raw)}


def _parse_crop_int_map(raw: Any) -> dict[str, int]:
    """Parse a per-crop or fruit-tree integer mapping, optionally applying values to both crops."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("Expected a mapping for per-crop values")
    out: dict[str, int] = {}
    for key, value in raw.items():
        product_id = _normalize_product_name(key)
        if product_id == "both":
            out["ancient"] = int(value)
            out["starfruit"] = int(value)
        else:
            out[product_id] = int(value)
    return out


def _normalize_product_name(raw: Any) -> str:
    """Normalize a product identifier (crops or fruit tree fruit)."""
    if raw is None:
        raise ValueError("Unknown product name: None")
    key = str(raw).strip().lower()
    if key in ("both", "all"):
        return "both"
    norm = key.replace(" ", "").replace("_", "").replace("-", "")
    if norm in ("ancientfruit", "ancient"):
        return "ancient"
    if norm in ("starfruit", "star"):
        return "starfruit"
    tree = normalize_fruit_tree_name(norm)
    if tree:
        return tree
    raise ValueError(f"Unknown product name: {raw}")


def _parse_fertilizer_cost_map(raw: Any) -> dict[str, int]:
    """Parse a per-fertilizer integer mapping."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("Expected a mapping for fertilizer_cost")
    out: dict[str, int] = {}
    for key, value in raw.items():
        fert = _normalize_fertilizer_name(key)
        out[fert] = int(value)
    return out


_FARMING_KEYS = ("rancher", "tiller", "coopmaster", "shepherd", "artisan", "agriculturist")
_FORAGING_KEYS = ("forester", "gatherer", "lumberjack", "tapper", "botanist", "tracker")
_FISHING_KEYS = ("fisher", "trapper", "angler", "pirate", "mariner", "luremaster")
_MINING_KEYS = ("miner", "geologist", "blacksmith", "prospector", "excavator", "gemologist")
_COMBAT_KEYS = ("fighter", "scout", "brute", "defender", "acrobat", "desperado")


def _parse_profession_flags(raw: Any, valid_keys: Sequence[str]) -> dict[str, bool]:
    """Parse a profession group mapping into booleans."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("professions.* must be a mapping")
    out: dict[str, bool] = {}
    for key in valid_keys:
        if key in raw:
            out[key] = bool(raw[key])
    return out


def _parse_professions_config(
    raw: Any,
    growth_raw: dict[str, Any],
    economy_raw: dict[str, Any],
) -> ProfessionsConfig:
    """Parse professions from config, with legacy fallback for agriculturist/artisan/tiller."""
    if raw is None:
        return ProfessionsConfig(
            farming=FarmingProfessions(
                artisan=bool(economy_raw.get("artisan", False)),
                tiller=bool(economy_raw.get("tiller", False)),
                agriculturist=bool(growth_raw.get("agriculturist", False)),
            )
        )
    if not isinstance(raw, dict):
        raise ValueError("professions must be a mapping")
    farming = FarmingProfessions(**_parse_profession_flags(raw.get("farming"), _FARMING_KEYS))
    foraging = ForagingProfessions(**_parse_profession_flags(raw.get("foraging"), _FORAGING_KEYS))
    fishing = FishingProfessions(**_parse_profession_flags(raw.get("fishing"), _FISHING_KEYS))
    mining = MiningProfessions(**_parse_profession_flags(raw.get("mining"), _MINING_KEYS))
    combat = CombatProfessions(**_parse_profession_flags(raw.get("combat"), _COMBAT_KEYS))
    return ProfessionsConfig(
        farming=farming,
        foraging=foraging,
        fishing=fishing,
        mining=mining,
        combat=combat,
    )
