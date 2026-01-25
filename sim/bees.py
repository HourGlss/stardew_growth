from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from sim.plots import Season


@dataclass(frozen=True)
class FlowerSpec:
    name: str
    growth_days: int
    base_price: int


@dataclass(frozen=True)
class FlowerPlan:
    fast: FlowerSpec
    expensive: FlowerSpec


@dataclass(frozen=True)
class BeeConfig:
    bee_houses: int = 0
    flower_base_price: int = 0
    seasons: Sequence[Season] = ("spring", "summer", "fall")
    flower_plan: dict[Season, FlowerPlan] = field(default_factory=dict)


@dataclass(frozen=True)
class BeeYearResult:
    honey_by_flower_price: dict[int, int]
    honey_total: int


def simulate_bees(config: BeeConfig, days_per_season: int = 28) -> BeeYearResult:
    """
    Simulate yearly honey output.
    Bee houses produce one honey every 4 days in season (no winter production).
    """
    seasons = tuple(config.seasons)
    bee_houses = max(0, int(config.bee_houses))
    honey_by_price: dict[int, int] = {}
    if bee_houses <= 0 or not seasons or days_per_season <= 0:
        return BeeYearResult(honey_by_flower_price={}, honey_total=0)

    for season in seasons:
        plan = config.flower_plan.get(season)
        for day in range(4, days_per_season + 1, 4):
            flower_price = config.flower_base_price
            if plan is not None:
                fast_ready = max(0, int(plan.fast.growth_days)) + 1
                expensive_ready = max(0, int(plan.expensive.growth_days)) + 1
                if day >= expensive_ready:
                    flower_price = int(plan.expensive.base_price)
                elif day >= fast_ready:
                    flower_price = int(plan.fast.base_price)
                else:
                    flower_price = 0
            honey_by_price[flower_price] = honey_by_price.get(flower_price, 0) + bee_houses

    honey_total = sum(honey_by_price.values())
    return BeeYearResult(honey_by_flower_price=honey_by_price, honey_total=honey_total)
