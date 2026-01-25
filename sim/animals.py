from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


DUCK_EGG_DAYS = 2
GOAT_MILK_DAYS = 2
RABBIT_WOOL_DAYS = 4
SHEEP_WOOL_DAYS = 3


@dataclass(frozen=True)
class CoopConfig:
    name: str
    chickens: int = 0
    ducks: int = 0
    rabbits: int = 0
    void_chickens: int = 0


@dataclass(frozen=True)
class BarnConfig:
    name: str
    cows: int = 0
    goats: int = 0
    pigs: int = 0
    sheep: int = 0


@dataclass(frozen=True)
class AnimalsConfig:
    coops: Sequence[CoopConfig] = ()
    barns: Sequence[BarnConfig] = ()
    large_egg_rate: float = 0.0
    large_milk_rate: float = 0.0
    large_goat_milk_rate: float = 0.0
    rabbit_foot_rate: float = 0.0


@dataclass(frozen=True)
class AnimalYearResult:
    eggs: int
    large_eggs: int
    void_eggs: int
    duck_eggs: int
    milk: int
    large_milk: int
    goat_milk: int
    large_goat_milk: int
    wool: int
    rabbit_feet: int
    mayo: int
    gold_mayo: int
    void_mayo: int
    duck_mayo: int
    cheese: int
    gold_cheese: int
    goat_cheese: int
    gold_goat_cheese: int
    cloth: int
    truffles: int
    truffle_oil: int
    raw_truffles: int


def _split_with_rate(total: int, rate: float) -> tuple[int, int]:
    """Split a total into (normal, large) counts using a floor-based rate."""
    large = int(total * max(0.0, min(rate, 1.0)))
    normal = max(0, total - large)
    return normal, large


def _non_winter_days(days: int) -> int:
    """Return the number of non-winter days in a span (3 seasons per year)."""
    if days <= 0:
        return 0
    full_years, remainder = divmod(days, 112)
    return (full_years * 84) + min(remainder, 84)


def _allocate_by_priority(
    inventory: dict[str, int],
    capacity: int,
    priority: Sequence[str],
) -> tuple[dict[str, int], dict[str, int]]:
    """Allocate up to capacity items from inventory by priority."""
    remaining = {key: max(0, int(value)) for key, value in inventory.items()}
    taken = {key: 0 for key in inventory}
    capacity = max(0, int(capacity))
    for key in priority:
        if capacity <= 0:
            break
        available = remaining.get(key, 0)
        if available <= 0:
            continue
        use = min(available, capacity)
        taken[key] = use
        remaining[key] = available - use
        capacity -= use
    return taken, remaining


def simulate_animals(
    config: AnimalsConfig,
    days: int,
    oil_makers: int = 0,
    mayo_machines: int = 0,
    cheese_presses: int = 0,
    looms: int = 0,
    gatherer: bool = False,
    shepherd: bool = False,
) -> AnimalYearResult:
    """
    Simulate yearly animal product totals, assuming animals are fed every day.
    Production rates are based on Stardew Valley Wiki:
    - Chickens lay eggs daily.
    - Void chickens lay void eggs daily.
    - Ducks lay eggs every 2 days.
    - Rabbits produce wool every 4 days (rabbit foot replaces wool at a configured rate).
    - Cows produce milk daily.
    - Goats produce milk every 2 days.
    - Sheep produce wool every 3 days (daily with Shepherd).
    - Pigs find truffles on non-winter days (modeled as one per pig per day).
    - Oil makers can process one truffle per day each (lazy, once-per-day assumption).
    - Mayo/cheese/looms process one item per machine per day (lazy, once-per-day assumption).
    - Gatherer adds an expected +20% truffle yield (deterministic floor).
    """
    days = max(0, int(days))
    total_chickens = sum(c.chickens for c in config.coops)
    total_void_chickens = sum(c.void_chickens for c in config.coops)
    total_ducks = sum(c.ducks for c in config.coops)
    total_rabbits = sum(c.rabbits for c in config.coops)
    total_cows = sum(b.cows for b in config.barns)
    total_goats = sum(b.goats for b in config.barns)
    total_pigs = sum(b.pigs for b in config.barns)
    total_sheep = sum(b.sheep for b in config.barns)

    eggs_total = total_chickens * days
    eggs, large_eggs = _split_with_rate(eggs_total, config.large_egg_rate)
    void_eggs = total_void_chickens * days

    duck_eggs = total_ducks * (days // DUCK_EGG_DAYS)

    milk_total = total_cows * days
    milk, large_milk = _split_with_rate(milk_total, config.large_milk_rate)

    goat_milk_total = total_goats * (days // GOAT_MILK_DAYS)
    goat_milk, large_goat_milk = _split_with_rate(goat_milk_total, config.large_goat_milk_rate)

    rabbit_products = total_rabbits * (days // RABBIT_WOOL_DAYS)
    rabbit_feet = int(rabbit_products * max(0.0, min(config.rabbit_foot_rate, 1.0)))
    rabbit_wool = max(0, rabbit_products - rabbit_feet)

    sheep_interval = 1 if shepherd else SHEEP_WOOL_DAYS
    sheep_wool = total_sheep * (days // max(1, sheep_interval))
    wool = rabbit_wool + sheep_wool

    non_winter_days = _non_winter_days(days)
    truffles = total_pigs * non_winter_days
    if gatherer and truffles > 0:
        truffles += int(truffles * 0.2)
    oil_makers = max(0, int(oil_makers))
    truffle_oil = min(truffles, oil_makers * days)
    raw_truffles = max(0, truffles - truffle_oil)

    mayo_capacity = max(0, int(mayo_machines)) * days
    egg_inventory = {
        "duck_eggs": duck_eggs,
        "void_eggs": void_eggs,
        "large_eggs": large_eggs,
        "eggs": eggs,
    }
    egg_priority = ("duck_eggs", "void_eggs", "large_eggs", "eggs")
    eggs_used, _ = _allocate_by_priority(egg_inventory, mayo_capacity, egg_priority)

    cheese_capacity = max(0, int(cheese_presses)) * days
    milk_inventory = {
        "large_goat_milk": large_goat_milk,
        "goat_milk": goat_milk,
        "large_milk": large_milk,
        "milk": milk,
    }
    milk_priority = ("large_goat_milk", "goat_milk", "large_milk", "milk")
    milk_used, _ = _allocate_by_priority(milk_inventory, cheese_capacity, milk_priority)

    loom_capacity = max(0, int(looms)) * days
    cloth = min(wool, loom_capacity)

    return AnimalYearResult(
        eggs=eggs,
        large_eggs=large_eggs,
        void_eggs=void_eggs,
        duck_eggs=duck_eggs,
        milk=milk,
        large_milk=large_milk,
        goat_milk=goat_milk,
        large_goat_milk=large_goat_milk,
        wool=wool,
        rabbit_feet=rabbit_feet,
        mayo=eggs_used["eggs"],
        gold_mayo=eggs_used["large_eggs"],
        void_mayo=eggs_used["void_eggs"],
        duck_mayo=eggs_used["duck_eggs"],
        cheese=milk_used["milk"],
        gold_cheese=milk_used["large_milk"],
        goat_cheese=milk_used["goat_milk"],
        gold_goat_cheese=milk_used["large_goat_milk"],
        cloth=cloth,
        truffles=truffles,
        truffle_oil=truffle_oil,
        raw_truffles=raw_truffles,
    )
