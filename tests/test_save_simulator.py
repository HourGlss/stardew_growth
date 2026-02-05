from sim.config import EconomyConfig, ProfessionsConfig
from sim.crop_catalog import CropCatalog, CropDef, ShopAccess
from sim.save_simulator import SimulationOptions, simulate_save
from sim.save_state import CropInstance, FarmState, MachineCounts, TileState


def test_simulate_save_basic_processing():
    crop = CropDef(
        harvest_item_id="100",
        seed_item_id="200",
        name="Test Fruit",
        seasons=("spring",),
        days_in_phase=(1, 1),
        regrow_days=2,
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
        category="fruit",
    )
    catalog = CropCatalog(
        by_harvest_id={crop.harvest_item_id: crop},
        by_seed_id={crop.seed_item_id: crop},
        by_name={"testfruit": crop},
    )
    farm = FarmState(
        start_day_of_year=1,
        season="spring",
        day_of_month=1,
        year=1,
        farming_level=0,
        professions=ProfessionsConfig(),
        machines=MachineCounts(kegs=1),
        shop_access=ShopAccess(),
        tiles=[
            TileState(
                location="Farm",
                x=0,
                y=0,
                fertilizer="none",
                watered=True,
                crop=CropInstance(crop=crop, days_until_harvest=1, is_regrowing=False),
            )
        ],
        seed_inventory={},
    )

    options = SimulationOptions(window_days=4, sprinkler_only=True, allow_seed_purchases=False)
    economy = EconomyConfig()

    result = simulate_save(farm, catalog, economy, options)
    crop_result = result.per_crop[crop.harvest_item_id]
    assert crop_result.harvested == 2
    assert crop_result.raw_sold == 1
    assert crop_result.wine_in_kegs_end == 1
    assert crop_result.base_wine == 0
    assert result.total_revenue == 100
    assert result.total_profit == 100
