from sim.config import EconomyConfig
from sim.crop_catalog import CropDef
from sim.pricing import processed_prices, raw_price, keg_price, jar_price, dried_batch_price


def _make_crop(category: str) -> CropDef:
    return CropDef(
        harvest_item_id="100",
        seed_item_id="200",
        name="Test",
        seasons=("spring",),
        days_in_phase=(1,),
        regrow_days=None,
        harvest_min_stack=1,
        harvest_max_stack=1,
        harvest_max_increase_per_level=0.0,
        extra_harvest_chance=0.0,
        needs_watering=True,
        is_paddy=False,
        is_raised=False,
        base_price=100,
        seed_price=10,
        seed_sources={},
        category=category,
    )


def test_pricing_fruit_with_professions():
    crop = _make_crop("fruit")
    economy = EconomyConfig(artisan=True, tiller=True, fruit_quality_multiplier=1.0, wine_quality_multiplier=1.0)
    assert raw_price(crop.base_price, economy) == 110
    assert keg_price(crop, economy) == 420
    assert jar_price(crop, economy) == 350
    assert dried_batch_price(crop, economy) == 1085
    prices = processed_prices(crop, economy)
    assert prices.raw == 110
    assert prices.keg == 420
    assert prices.jar == 350
    assert prices.dried_batch == 1085


def test_pricing_vegetable_processing():
    crop = _make_crop("vegetable")
    economy = EconomyConfig(artisan=False, tiller=False)
    assert raw_price(crop.base_price, economy) == 100
    assert keg_price(crop, economy) == 225
    assert jar_price(crop, economy) == 250
    assert dried_batch_price(crop, economy) is None
    prices = processed_prices(crop, economy)
    assert prices.keg == 225
    assert prices.jar == 250
    assert prices.dried_batch is None
