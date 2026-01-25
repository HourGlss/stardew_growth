from __future__ import annotations

from dataclasses import fields

from sim.animals import AnimalsConfig
from sim.config import AppConfig


class ValidationError(ValueError):
    """Raised when input data is logically invalid."""


def validate_app_config(cfg: AppConfig) -> None:
    """Validate configuration invariants for both save and JSON inputs."""
    _ensure_non_negative(cfg.kegs, "kegs")
    _ensure_non_negative(cfg.casks, "casks")
    _ensure_non_negative(cfg.preserves_jars, "preserves_jars")
    _ensure_non_negative(cfg.dehydrators, "dehydrators")
    _ensure_non_negative(cfg.oil_makers, "oil_makers")
    _ensure_non_negative(cfg.mayo_machines, "mayo_machines")
    _ensure_non_negative(cfg.cheese_presses, "cheese_presses")
    _ensure_non_negative(cfg.looms, "looms")
    _ensure_non_negative(cfg.bees.bee_houses, "bee_houses")
    _ensure_non_negative(cfg.tiles, "tiles")

    _validate_animals(cfg.animals)
    _validate_plots(cfg)
    _validate_rates(cfg.animals)
    _validate_economy(cfg)
    _validate_inventory(cfg)
    _validate_bees(cfg)
    _validate_fruit_trees(cfg)


def _ensure_non_negative(value: int, name: str) -> None:
    if value < 0:
        raise ValidationError(f"{name} must be >= 0 (got {value})")


def _validate_animals(animals: AnimalsConfig) -> None:
    coop_capacity = 12
    barn_capacity = 12
    for coop in animals.coops:
        total = coop.chickens + coop.ducks + coop.rabbits + coop.void_chickens
        if total > coop_capacity:
            raise ValidationError(
                f"coop '{coop.name}' has {total} animals, exceeds capacity {coop_capacity}"
            )
        if total < 0:
            raise ValidationError(f"coop '{coop.name}' has negative animal counts")
    for barn in animals.barns:
        total = barn.cows + barn.goats + barn.pigs + barn.sheep
        if total > barn_capacity:
            raise ValidationError(
                f"barn '{barn.name}' has {total} animals, exceeds capacity {barn_capacity}"
            )
        if total < 0:
            raise ValidationError(f"barn '{barn.name}' has negative animal counts")


def _validate_plots(cfg: AppConfig) -> None:
    for plot in cfg.plots:
        if plot.calendar.type not in ("always", "seasons"):
            raise ValidationError(f"plot '{plot.name}' has unknown calendar type '{plot.calendar.type}'")
        if plot.calendar.type == "seasons" and not plot.calendar.seasons:
            raise ValidationError(f"plot '{plot.name}' uses seasons calendar with no seasons")
        for crop_id, tiles in plot.tiles_by_crop.items():
            if tiles < 0:
                raise ValidationError(
                    f"plot '{plot.name}' has negative tiles for {crop_id}: {tiles}"
                )
            if tiles == 0:
                continue
            if cfg.crop in ("starfruit", "ancient") and crop_id not in ("all", cfg.crop):
                raise ValidationError(
                    f"plot '{plot.name}' defines tiles for {crop_id}, but crop selection is '{cfg.crop}'"
                )
            if plot.calendar.type == "seasons":
                _validate_plot_seasons(plot.name, crop_id, cfg.crop, plot.calendar.seasons)


def _validate_plot_seasons(
    plot_name: str, crop_id: str, crop_mode: str, seasons: object
) -> None:
    allowed = {
        "starfruit": {"summer"},
        "ancient": {"spring", "summer", "fall"},
    }
    if crop_id == "all":
        if crop_mode in allowed and not set(seasons).issubset(allowed[crop_mode]):
            raise ValidationError(
                f"plot '{plot_name}' seasons {tuple(seasons)} invalid for crop '{crop_mode}'"
            )
        return
    if crop_id in allowed and not set(seasons).issubset(allowed[crop_id]):
        raise ValidationError(
            f"plot '{plot_name}' seasons {tuple(seasons)} invalid for crop '{crop_id}'"
        )


def _validate_rates(animals: AnimalsConfig) -> None:
    for field_name in ("large_egg_rate", "large_milk_rate", "large_goat_milk_rate", "rabbit_foot_rate"):
        value = getattr(animals, field_name)
        if value < 0.0 or value > 1.0:
            raise ValidationError(f"{field_name} must be between 0 and 1 (got {value})")


def _validate_economy(cfg: AppConfig) -> None:
    economy = cfg.economy
    for name in ("aged_wine_multiplier", "wine_quality_multiplier", "fruit_quality_multiplier"):
        value = getattr(economy, name)
        if value <= 0:
            raise ValidationError(f"{name} must be > 0 (got {value})")
    if economy.casks_with_walkways is not None:
        if economy.casks_with_walkways < 0:
            raise ValidationError("casks_with_walkways must be >= 0")
        if economy.casks_with_walkways > cfg.casks:
            raise ValidationError("casks_with_walkways cannot exceed casks")
    for label, mapping in (
        ("wine_price", economy.wine_price),
        ("fruit_price", economy.fruit_price),
        ("seed_cost", economy.seed_cost),
        ("fertilizer_cost", economy.fertilizer_cost),
    ):
        for key, value in mapping.items():
            if value < 0:
                raise ValidationError(f"{label}.{key} must be >= 0 (got {value})")


def _validate_inventory(cfg: AppConfig) -> None:
    for key, value in cfg.starting_inventory.fruit.items():
        if value < 0:
            raise ValidationError(f"starting_inventory.fruit.{key} must be >= 0 (got {value})")
    for key, value in cfg.starting_inventory.base_wine.items():
        if value < 0:
            raise ValidationError(f"starting_inventory.base_wine.{key} must be >= 0 (got {value})")


def _validate_bees(cfg: AppConfig) -> None:
    bees = cfg.bees
    if bees.bee_houses <= 0:
        return
    if not bees.seasons:
        raise ValidationError("bees.seasons must include at least one season when bee_houses > 0")
    for season, plan in bees.flower_plan.items():
        if season not in bees.seasons:
            raise ValidationError(f"bees.flower_plan contains season '{season}' not in bees.seasons")
        for label, spec in (("fast", plan.fast), ("expensive", plan.expensive)):
            if spec.growth_days < 0:
                raise ValidationError(f"bees.flower_plan.{season}.{label}.growth_days must be >= 0")
            if spec.base_price < 0:
                raise ValidationError(f"bees.flower_plan.{season}.{label}.base_price must be >= 0")


def _validate_fruit_trees(cfg: AppConfig) -> None:
    trees = cfg.fruit_trees
    for scope_name, scope in (
        ("fruit_trees.greenhouse", trees.greenhouse),
        ("fruit_trees.outdoors", trees.outdoors),
        ("fruit_trees.always", trees.always),
    ):
        for key, value in scope.items():
            if value < 0:
                raise ValidationError(f"{scope_name}.{key} must be >= 0 (got {value})")
