import json

import pytest

from sim.config import (
    AppConfig,
    _normalize_crop_name,
    _normalize_fertilizer_name,
    _normalize_season,
    _normalize_seasons,
    _parse_fertilizer_cost_map,
    _parse_crop_int_map,
    _parse_plot_tiles,
)
from sim.plots import day_of_year_from_season_day


def test_normalize_crop_name_variants():
    """Crop name normalization should accept common variants."""
    assert _normalize_crop_name("STARFRUIT") == "starfruit"
    assert _normalize_crop_name("star_fruit") == "starfruit"
    assert _normalize_crop_name("ancient fruit") == "ancient"
    assert _normalize_crop_name("both") == "both"
    with pytest.raises(ValueError):
        _normalize_crop_name("unknown")


def test_normalize_season():
    """Season normalization should enforce valid values."""
    assert _normalize_season("Winter") == "winter"
    with pytest.raises(ValueError):
        _normalize_season("monsoon")


def test_normalize_seasons():
    """Season list normalization should accept scalars and lists."""
    assert _normalize_seasons("spring") == ("spring",)
    assert _normalize_seasons(["spring", "summer"]) == ("spring", "summer")


def test_normalize_fertilizer_name():
    """Fertilizer normalization should accept common variants."""
    assert _normalize_fertilizer_name("Speed Gro") == "speed_gro"
    assert _normalize_fertilizer_name("DeluxeSpeedGro") == "deluxe_speed_gro"
    with pytest.raises(ValueError):
        _normalize_fertilizer_name("mystery")


def test_parse_plot_tiles():
    """Plot tile parsing should handle ints and per-crop maps."""
    assert _parse_plot_tiles(5) == {"all": 5}
    parsed = _parse_plot_tiles({"STARFRUIT": 3, "ancient": 2})
    assert parsed == {"starfruit": 3, "ancient": 2}
    with pytest.raises(ValueError):
        _parse_plot_tiles({"both": 1})


def test_parse_crop_int_map():
    """Per-crop mappings should accept 'both' for convenience."""
    parsed = _parse_crop_int_map({"both": 10})
    assert parsed == {"ancient": 10, "starfruit": 10}
    parsed = _parse_crop_int_map({"Apple": 5})
    assert parsed == {"apple": 5}


def test_parse_fertilizer_cost_map():
    """Fertilizer cost mapping should normalize fertilizer keys."""
    parsed = _parse_fertilizer_cost_map({"Speed Gro": 5})
    assert parsed == {"speed_gro": 5}


def test_from_json_file_parses_calendar_and_economy(tmp_path):
    """JSON config should parse calendar start day and economy settings."""
    raw = {
        "kegs": 1,
        "casks": 2,
        "preserves_jars": 3,
        "dehydrators": 4,
        "oil_makers": 5,
        "mayo_machines": 6,
        "cheese_presses": 7,
        "looms": 8,
        "crop": "starfruit",
        "simulation": {"calendar": {"current_season": "winter", "day": 4}, "max_days": 999},
        "economy": {
            "wine_price": {"STARFRUIT": 100},
            "aged_wine_multiplier": 2.0,
            "fertilizer_cost": {"speed_gro": 3},
            "artisan": False,
            "tiller": True,
        },
        "starting_inventory": {"fruit": {"STARFRUIT": 2}, "base_wine": {"STARFRUIT": 1}},
        "professions": {
            "farming": {"artisan": True, "tiller": False, "agriculturist": True, "rancher": True},
            "foraging": {"gatherer": True, "botanist": True},
            "fishing": {"fisher": True},
            "mining": {"miner": True},
            "combat": {"fighter": True},
        },
        "animals": {
            "coops": [{"name": "coop1", "chickens": 6, "ducks": 2, "rabbits": 1, "void_chickens": 1}],
            "barns": [{"name": "barn1", "cows": 3, "goats": 1, "pigs": 2, "sheep": 1}],
            "large_egg_rate": 0.5,
            "large_milk_rate": 0.25,
            "large_goat_milk_rate": 0.75,
            "rabbit_foot_rate": 0.1,
        },
        "bees": {
            "bee_houses": 5,
            "flower_base_price": 80,
            "seasons": ["spring", "summer"],
            "flower_plan": {
                "spring": {
                    "fast": {"name": "Tulip", "growth_days": 6, "base_price": 30},
                    "expensive": {"name": "Blue Jazz", "growth_days": 7, "base_price": 50}
                }
            }
        },
        "plots": [{"name": "plot", "tiles": 1, "calendar": {"type": "always"}}],
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    cfg = AppConfig.from_json_file(str(path))
    assert cfg.simulation.start_day_of_year == day_of_year_from_season_day("winter", 4)
    assert cfg.simulation.max_days == 112
    assert cfg.preserves_jars == 3
    assert cfg.dehydrators == 4
    assert cfg.oil_makers == 5
    assert cfg.mayo_machines == 6
    assert cfg.cheese_presses == 7
    assert cfg.looms == 8
    assert cfg.economy.wine_price["starfruit"] == 100
    assert cfg.economy.fertilizer_cost["speed_gro"] == 3
    assert cfg.economy.artisan is True
    assert cfg.economy.tiller is False
    assert cfg.growth.agriculturist is True
    assert cfg.starting_inventory.fruit["starfruit"] == 2
    assert cfg.starting_inventory.base_wine["starfruit"] == 1
    assert cfg.economy.aged_wine_multiplier == 2.0
    assert cfg.animals.coops[0].chickens == 6
    assert cfg.animals.coops[0].rabbits == 1
    assert cfg.animals.barns[0].goats == 1
    assert cfg.animals.barns[0].pigs == 2
    assert cfg.animals.barns[0].sheep == 1
    assert cfg.animals.large_egg_rate == 0.5
    assert cfg.animals.rabbit_foot_rate == 0.1
    assert cfg.professions.farming.rancher is True
    assert cfg.professions.foraging.gatherer is True
    assert cfg.professions.foraging.botanist is True
    assert cfg.professions.fishing.fisher is True
    assert cfg.professions.mining.miner is True
    assert cfg.professions.combat.fighter is True
    assert cfg.bees.bee_houses == 5
    assert cfg.bees.flower_base_price == 80
    assert tuple(cfg.bees.seasons) == ("spring", "summer")
    assert cfg.bees.flower_plan["spring"].fast.base_price == 30


def test_professions_fallback_from_legacy_fields():
    """Legacy economy/growth flags should populate professions when missing."""
    raw = {
        "kegs": 1,
        "casks": 1,
        "growth": {"fertilizer": "none", "agriculturist": True},
        "economy": {"artisan": True, "tiller": False},
        "plots": [{"name": "plot", "tiles": 1, "calendar": {"type": "always"}}],
    }
    cfg = AppConfig.from_dict(raw)
    assert cfg.professions.farming.agriculturist is True
    assert cfg.professions.farming.artisan is True
    assert cfg.professions.farming.tiller is False
