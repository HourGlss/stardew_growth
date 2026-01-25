from sim.config import EconomyConfig
from sim.animals import AnimalYearResult
from sim.bees import BeeYearResult
from sim.economy import compute_animal_profit, compute_honey_profit, compute_profit, per_fruit_processing_values
from sim.pipeline import CropYearResult


def test_compute_profit_with_aged_multiplier():
    """Profit should include aged wine multiplier and seed costs."""
    per_crop = {
        "starfruit": CropYearResult(
            crop_id="starfruit",
            fruit_harvested=0,
            fruit_unprocessed=0,
            fruit_sold=0,
            base_wine_produced=12,
            base_wine_sold=10,
            aged_wine_produced=2,
            wine_in_kegs_end=0,
            seed_units_used=3,
            fertilizer_units_used=0,
        )
    }
    economy = EconomyConfig(
        wine_price={"starfruit": 100},
        seed_cost={"starfruit": 10},
        aged_wine_multiplier=2.0,
    )
    profit = compute_profit(per_crop, economy, "none")
    breakdown = profit.per_crop["starfruit"]
    assert breakdown.base_wine_revenue == 1000
    assert breakdown.aged_wine_revenue == 400
    assert breakdown.jelly_revenue == 0
    assert breakdown.dried_fruit_revenue == 0
    assert breakdown.seed_cost == 30
    assert breakdown.net_profit == 1370
    assert profit.total_profit == 1370
    assert profit.total_fertilizer_cost == 0


def test_compute_profit_with_modifiers_and_fruit():
    """Profit should include artisan/tiller and quality multipliers."""
    per_crop = {
        "ancient": CropYearResult(
            crop_id="ancient",
            fruit_harvested=0,
            fruit_unprocessed=5,
            fruit_sold=5,
            base_wine_produced=0,
            base_wine_sold=0,
            aged_wine_produced=1,
            wine_in_kegs_end=0,
            seed_units_used=2,
            fertilizer_units_used=4,
        )
    }
    economy = EconomyConfig(
        wine_price={"ancient": 100},
        fruit_price={"ancient": 50},
        seed_cost={"ancient": 10},
        fertilizer_cost={"deluxe_speed_gro": 3},
        aged_wine_multiplier=2.0,
        wine_quality_multiplier=1.1,
        fruit_quality_multiplier=1.2,
        artisan=True,
        tiller=True,
    )
    profit = compute_profit(per_crop, economy, "deluxe_speed_gro")
    breakdown = profit.per_crop["ancient"]
    assert breakdown.fruit_revenue == int(50 * 1.2 * 1.1) * 5
    assert breakdown.aged_wine_revenue == int(100 * 1.1 * 1.4) * 2
    assert breakdown.jelly_revenue == 0
    assert breakdown.dried_fruit_revenue == 0
    assert breakdown.fertilizer_cost == 12
    assert breakdown.seed_cost == 20


def test_compute_profit_with_jelly_and_dried():
    """Preserves jar and dehydrator revenues should use fruit price formulas."""
    per_crop = {
        "starfruit": CropYearResult(
            crop_id="starfruit",
            fruit_harvested=0,
            fruit_unprocessed=0,
            fruit_sold=0,
            base_wine_produced=0,
            base_wine_sold=0,
            aged_wine_produced=0,
            wine_in_kegs_end=0,
            seed_units_used=0,
            fertilizer_units_used=0,
            jelly_produced=2,
            dried_fruit_produced=1,
        )
    }
    economy = EconomyConfig(
        fruit_price={"starfruit": 750},
        artisan=True,
    )
    profit = compute_profit(per_crop, economy, "none")
    breakdown = profit.per_crop["starfruit"]
    assert breakdown.jelly_revenue == int((750 * 2 + 50) * 1.4) * 2
    assert breakdown.dried_fruit_revenue == int((750 * 7.5 + 25) * 1.4)


def test_compute_animal_profit_with_artisan():
    """Animal artisan goods should use wiki prices and artisan bonus."""
    result = AnimalYearResult(
        eggs=2,
        large_eggs=1,
        void_eggs=1,
        duck_eggs=1,
        milk=1,
        large_milk=1,
        goat_milk=1,
        large_goat_milk=1,
        wool=2,
        rabbit_feet=1,
        mayo=1,
        gold_mayo=1,
        void_mayo=0,
        duck_mayo=1,
        cheese=1,
        gold_cheese=0,
        goat_cheese=1,
        gold_goat_cheese=1,
        cloth=1,
        truffles=2,
        truffle_oil=1,
        raw_truffles=1,
    )
    economy = EconomyConfig(artisan=True)
    profit = compute_animal_profit(result, economy, botanist=True, rancher=True)
    base_cheese = 230 + 400 + 600
    base_mayo = 190 + 285 + 375
    base_truffle_oil = 1065
    base_raw_truffle = 1250
    base_raw_animals = 50 + 65 + 190 + 340 + 565
    assert profit.cheese_revenue == int(base_cheese * 1.4)
    assert profit.mayo_revenue == int(base_mayo * 1.4)
    assert profit.cloth_revenue == int(470 * 1.4)
    assert profit.truffle_oil_revenue == int(base_truffle_oil * 1.4)
    assert profit.raw_truffle_revenue == base_raw_truffle
    assert profit.raw_animal_revenue == int(base_raw_animals * 1.2)


def test_compute_honey_profit_wild_honey():
    """Wild honey should use the wiki base price and artisan bonus."""
    result = BeeYearResult(honey_by_flower_price={}, honey_total=2)
    economy = EconomyConfig(artisan=True)
    profit = compute_honey_profit(result, economy, flower_base_price=0)
    assert profit.honey_revenue == int(100 * 1.4) * 2


def test_compute_honey_profit_with_flower_mix():
    """Honey revenue should sum over flower price buckets."""
    result = BeeYearResult(honey_by_flower_price={0: 1, 80: 2}, honey_total=3)
    economy = EconomyConfig(artisan=False)
    profit = compute_honey_profit(result, economy, flower_base_price=0)
    assert profit.honey_revenue == (100 * 1) + ((100 + 160) * 2)


def test_per_fruit_processing_values():
    """Per-fruit processing values should use dehydrator per-fruit pricing."""
    economy = EconomyConfig()
    values = per_fruit_processing_values(fruit_price=100, wine_price=300, economy=economy)
    assert values["raw"] == 100
    assert values["wine"] == 300
    assert values["jelly"] == 250
    assert values["dried"] == 155
