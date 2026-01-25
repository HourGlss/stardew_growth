from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from sim.plots import season_for_day_of_year


FRUIT_TREE_ID_TO_FRUIT = {
    "628": "cherry",
    "629": "apricot",
    "630": "orange",
    "631": "peach",
    "632": "pomegranate",
    "633": "apple",
    "69": "banana",
    "835": "mango",
}

FRUIT_TREE_SEASONS = {
    "apricot": ("spring",),
    "cherry": ("spring",),
    "orange": ("summer",),
    "peach": ("summer",),
    "banana": ("summer",),
    "mango": ("summer",),
    "apple": ("fall",),
    "pomegranate": ("fall",),
}


@dataclass(frozen=True)
class FruitTreesConfig:
    greenhouse: dict[str, int] = field(default_factory=dict)
    outdoors: dict[str, int] = field(default_factory=dict)
    always: dict[str, int] = field(default_factory=dict)


def normalize_fruit_tree_name(raw: str) -> str | None:
    """Normalize a fruit tree name to its canonical id."""
    if raw is None:
        return None
    key = str(raw).strip().lower()
    norm = key.replace(" ", "").replace("_", "").replace("-", "")
    mapping = {
        "apple": "apple",
        "apricot": "apricot",
        "cherry": "cherry",
        "orange": "orange",
        "peach": "peach",
        "pomegranate": "pomegranate",
        "banana": "banana",
        "mango": "mango",
    }
    return mapping.get(norm)


def build_daily_fruit(
    config: FruitTreesConfig,
    start_day_of_year: int,
    max_days: int,
) -> dict[str, list[int]]:
    """Return daily fruit totals per fruit tree for the simulation window."""
    max_days = max(0, int(max_days))
    start_day_of_year = max(1, int(start_day_of_year))
    counts: dict[str, int] = {}
    for scope in (config.greenhouse, config.outdoors, config.always):
        for fruit_id, count in scope.items():
            if count <= 0:
                continue
            counts[fruit_id] = counts.get(fruit_id, 0) + int(count)

    if not counts or max_days == 0:
        return {}

    daily = {fruit_id: [0] * max_days for fruit_id in counts}
    always_counts = _aggregate(config.greenhouse, config.always)
    outdoor_counts = dict(config.outdoors)

    for day_index in range(max_days):
        day_of_year = ((start_day_of_year - 1 + day_index) % 112) + 1
        season = season_for_day_of_year(day_of_year)
        for fruit_id, count in always_counts.items():
            daily[fruit_id][day_index] += count
        for fruit_id, count in outdoor_counts.items():
            if count <= 0:
                continue
            seasons = FRUIT_TREE_SEASONS.get(fruit_id, ())
            if season in seasons:
                daily[fruit_id][day_index] += count

    return daily


def summarize_tree_counts(config: FruitTreesConfig) -> dict[str, dict[str, int]]:
    """Return a mapping of scope -> counts for display."""
    return {
        "greenhouse": dict(config.greenhouse),
        "outdoors": dict(config.outdoors),
        "always": dict(config.always),
    }


def total_tree_counts(config: FruitTreesConfig) -> dict[str, int]:
    """Return total counts per fruit across all scopes."""
    total: dict[str, int] = {}
    for scope in (config.greenhouse, config.outdoors, config.always):
        for fruit_id, count in scope.items():
            if count <= 0:
                continue
            total[fruit_id] = total.get(fruit_id, 0) + int(count)
    return total


def tree_ids_from_config(config: FruitTreesConfig) -> list[str]:
    """Return fruit ids present in the config."""
    return list(total_tree_counts(config).keys())


def _aggregate(*scopes: dict[str, int]) -> dict[str, int]:
    out: dict[str, int] = {}
    for scope in scopes:
        for fruit_id, count in scope.items():
            if count <= 0:
                continue
            out[fruit_id] = out.get(fruit_id, 0) + int(count)
    return out
