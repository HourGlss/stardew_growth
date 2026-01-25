from __future__ import annotations

from dataclasses import dataclass

from sim.config import EconomyConfig, Fertilizer
from sim.animals import AnimalYearResult
from sim.bees import BeeYearResult
from sim.pipeline import CropYearResult

EGG_PRICE = 50
LARGE_EGG_PRICE = 95
DUCK_EGG_PRICE = 95
VOID_EGG_PRICE = 65
MILK_PRICE = 125
LARGE_MILK_PRICE = 190
GOAT_MILK_PRICE = 225
LARGE_GOAT_MILK_PRICE = 345
WOOL_PRICE = 340
RABBIT_FOOT_PRICE = 565

MAYO_PRICE = 190
GOLD_MAYO_PRICE = 285
DUCK_MAYO_PRICE = 375
VOID_MAYO_PRICE = 275
CHEESE_PRICE = 230
GOLD_CHEESE_PRICE = 345
GOAT_CHEESE_PRICE = 400
GOLD_GOAT_CHEESE_PRICE = 600
CLOTH_PRICE = 470

TRUFFLE_PRICE = 625
TRUFFLE_IRIDIUM_PRICE = 1250
TRUFFLE_OIL_PRICE = 1065


@dataclass(frozen=True)
class ProfitBreakdown:
    crop_id: str
    base_wine_revenue: int
    aged_wine_revenue: int
    jelly_revenue: int
    dried_fruit_revenue: int
    fruit_revenue: int
    seed_cost: int
    fertilizer_cost: int
    net_profit: int


@dataclass(frozen=True)
class ProfitSummary:
    per_crop: dict[str, ProfitBreakdown]
    total_revenue: int
    total_seed_cost: int
    total_fertilizer_cost: int
    total_profit: int


@dataclass(frozen=True)
class AnimalProfit:
    cheese_revenue: int
    mayo_revenue: int
    cloth_revenue: int
    truffle_oil_revenue: int
    raw_truffle_revenue: int
    raw_animal_revenue: int
    total_revenue: int


@dataclass(frozen=True)
class HoneyProfit:
    honey_revenue: int
    total_revenue: int


def wine_price_for_crop(crop_id: str, economy: EconomyConfig) -> int:
    """Return wine price for a crop, falling back to fruit_price * 3."""
    fruit_price = economy.fruit_price.get(crop_id, 0)
    wine_price = economy.wine_price.get(crop_id)
    if wine_price is None and fruit_price:
        wine_price = fruit_price * 3
    return int(wine_price or 0)


def per_fruit_processing_values(
    fruit_price: int,
    wine_price: int,
    economy: EconomyConfig,
) -> dict[str, int]:
    """Return per-fruit revenue for raw, wine, jelly, and dried fruit."""
    fruit_unit = fruit_price * economy.fruit_quality_multiplier
    if economy.tiller:
        fruit_unit *= 1.1
    wine_unit = wine_price * economy.wine_quality_multiplier
    jelly_unit = (fruit_price * 2) + 50 if fruit_price > 0 else 0
    dried_unit = (fruit_price * 1.5) + 5 if fruit_price > 0 else 0
    if economy.artisan:
        wine_unit *= 1.4
        jelly_unit *= 1.4
        dried_unit *= 1.4
    return {
        "raw": int(fruit_unit),
        "wine": int(wine_unit),
        "jelly": int(jelly_unit),
        "dried": int(dried_unit),
    }


def compute_profit(
    per_crop: dict[str, CropYearResult],
    economy: EconomyConfig,
    fertilizer: Fertilizer,
) -> ProfitSummary:
    """Compute profit totals from per-crop production results."""
    per_crop_profit: dict[str, ProfitBreakdown] = {}
    total_revenue = 0
    total_seed_cost = 0
    total_fertilizer_cost = 0
    for crop_id, result in per_crop.items():
        fruit_price = economy.fruit_price.get(crop_id, 0)
        wine_price = economy.wine_price.get(crop_id)
        if wine_price is None and fruit_price:
            wine_price = fruit_price * 3
        wine_price = wine_price or 0
        wine_unit = wine_price * economy.wine_quality_multiplier
        fruit_unit = fruit_price * economy.fruit_quality_multiplier
        if fruit_price > 0:
            jelly_unit = (fruit_price * 2) + 50
            dried_unit = int((fruit_price * 7.5) + 25)
        else:
            jelly_unit = 0
            dried_unit = 0
        if economy.artisan:
            wine_unit *= 1.4
            jelly_unit *= 1.4
            dried_unit *= 1.4
        if economy.tiller:
            fruit_unit *= 1.1
        wine_unit = int(wine_unit)
        fruit_unit = int(fruit_unit)
        jelly_unit = int(jelly_unit)
        dried_unit = int(dried_unit)
        base_revenue = result.base_wine_sold * wine_unit
        aged_revenue = int(result.aged_wine_produced * wine_unit * economy.aged_wine_multiplier)
        fruit_revenue = result.fruit_sold * fruit_unit
        jelly_revenue = result.jelly_produced * jelly_unit
        dried_revenue = result.dried_fruit_produced * dried_unit
        seed_cost = result.seed_units_used * economy.seed_cost.get(crop_id, 0)
        fertilizer_cost = result.fertilizer_units_used * economy.fertilizer_cost.get(fertilizer, 0)
        net = base_revenue + aged_revenue + fruit_revenue + jelly_revenue + dried_revenue - seed_cost - fertilizer_cost
        per_crop_profit[crop_id] = ProfitBreakdown(
            crop_id=crop_id,
            base_wine_revenue=base_revenue,
            aged_wine_revenue=aged_revenue,
            jelly_revenue=jelly_revenue,
            dried_fruit_revenue=dried_revenue,
            fruit_revenue=fruit_revenue,
            seed_cost=seed_cost,
            fertilizer_cost=fertilizer_cost,
            net_profit=net,
        )
        total_revenue += base_revenue + aged_revenue + fruit_revenue + jelly_revenue + dried_revenue
        total_seed_cost += seed_cost
        total_fertilizer_cost += fertilizer_cost
    total_profit = total_revenue - total_seed_cost - total_fertilizer_cost
    return ProfitSummary(
        per_crop=per_crop_profit,
        total_revenue=total_revenue,
        total_seed_cost=total_seed_cost,
        total_fertilizer_cost=total_fertilizer_cost,
        total_profit=total_profit,
    )


def compute_animal_profit(
    result: AnimalYearResult,
    economy: EconomyConfig,
    botanist: bool = False,
    rancher: bool = False,
) -> AnimalProfit:
    """Compute revenue from animal products, accounting for artisan and rancher."""
    cheese_revenue = (
        result.cheese * CHEESE_PRICE
        + result.gold_cheese * GOLD_CHEESE_PRICE
        + result.goat_cheese * GOAT_CHEESE_PRICE
        + result.gold_goat_cheese * GOLD_GOAT_CHEESE_PRICE
    )
    mayo_revenue = (
        result.mayo * MAYO_PRICE
        + result.gold_mayo * GOLD_MAYO_PRICE
        + result.duck_mayo * DUCK_MAYO_PRICE
        + result.void_mayo * VOID_MAYO_PRICE
    )
    cloth_revenue = result.cloth * CLOTH_PRICE
    truffle_oil_revenue = result.truffle_oil * TRUFFLE_OIL_PRICE
    raw_truffle_unit = TRUFFLE_IRIDIUM_PRICE if botanist else TRUFFLE_PRICE
    raw_truffle_revenue = result.raw_truffles * raw_truffle_unit

    raw_eggs = max(0, result.eggs - result.mayo)
    raw_large_eggs = max(0, result.large_eggs - result.gold_mayo)
    raw_duck_eggs = max(0, result.duck_eggs - result.duck_mayo)
    raw_void_eggs = max(0, result.void_eggs - result.void_mayo)
    raw_milk = max(0, result.milk - result.cheese)
    raw_large_milk = max(0, result.large_milk - result.gold_cheese)
    raw_goat_milk = max(0, result.goat_milk - result.goat_cheese)
    raw_large_goat_milk = max(0, result.large_goat_milk - result.gold_goat_cheese)
    raw_wool = max(0, result.wool - result.cloth)

    raw_animal_revenue = (
        raw_eggs * EGG_PRICE
        + raw_large_eggs * LARGE_EGG_PRICE
        + raw_duck_eggs * DUCK_EGG_PRICE
        + raw_void_eggs * VOID_EGG_PRICE
        + raw_milk * MILK_PRICE
        + raw_large_milk * LARGE_MILK_PRICE
        + raw_goat_milk * GOAT_MILK_PRICE
        + raw_large_goat_milk * LARGE_GOAT_MILK_PRICE
        + raw_wool * WOOL_PRICE
        + result.rabbit_feet * RABBIT_FOOT_PRICE
    )

    if economy.artisan:
        cheese_revenue = int(cheese_revenue * 1.4)
        mayo_revenue = int(mayo_revenue * 1.4)
        cloth_revenue = int(cloth_revenue * 1.4)
        truffle_oil_revenue = int(truffle_oil_revenue * 1.4)

    if rancher:
        raw_animal_revenue = int(raw_animal_revenue * 1.2)

    total_revenue = (
        cheese_revenue
        + mayo_revenue
        + cloth_revenue
        + truffle_oil_revenue
        + raw_truffle_revenue
        + raw_animal_revenue
    )
    return AnimalProfit(
        cheese_revenue=cheese_revenue,
        mayo_revenue=mayo_revenue,
        cloth_revenue=cloth_revenue,
        truffle_oil_revenue=truffle_oil_revenue,
        raw_truffle_revenue=raw_truffle_revenue,
        raw_animal_revenue=raw_animal_revenue,
        total_revenue=total_revenue,
    )


def compute_honey_profit(result: BeeYearResult, economy: EconomyConfig, flower_base_price: int) -> HoneyProfit:
    """Compute honey revenue using the base price formula."""
    honey_revenue = 0
    if result.honey_by_flower_price:
        for flower_price, count in result.honey_by_flower_price.items():
            base_price = 100 + (2 * max(0, int(flower_price)))
            if economy.artisan:
                base_price = int(base_price * 1.4)
            honey_revenue += base_price * int(count)
    else:
        base_price = 100 + (2 * max(0, flower_base_price))
        if economy.artisan:
            base_price = int(base_price * 1.4)
        honey_revenue = result.honey_total * base_price
    return HoneyProfit(honey_revenue=honey_revenue, total_revenue=honey_revenue)


def build_category_totals(
    crop_profit: ProfitSummary,
    animal_profit: AnimalProfit,
    honey_profit: HoneyProfit,
) -> dict[str, int]:
    """Return revenue totals grouped by category for pie charting."""
    aged_wine = sum(p.aged_wine_revenue for p in crop_profit.per_crop.values())
    base_wine = sum(p.base_wine_revenue for p in crop_profit.per_crop.values())
    jelly = sum(p.jelly_revenue for p in crop_profit.per_crop.values())
    dried = sum(p.dried_fruit_revenue for p in crop_profit.per_crop.values())
    raw_fruit = sum(p.fruit_revenue for p in crop_profit.per_crop.values())
    return {
        "cheese": animal_profit.cheese_revenue,
        "mayo": animal_profit.mayo_revenue,
        "cloth": animal_profit.cloth_revenue,
        "truffle_oil": animal_profit.truffle_oil_revenue,
        "raw_truffles": animal_profit.raw_truffle_revenue,
        "raw_animal_products": animal_profit.raw_animal_revenue,
        "aged_wine": aged_wine,
        "non_aged_wine": base_wine,
        "jarred_fruit": jelly,
        "honey": honey_profit.honey_revenue,
        "dehydrators": dried,
        "raw_fruit": raw_fruit,
    }
