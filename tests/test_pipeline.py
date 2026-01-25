from sim.crops import ANCIENT_FRUIT, STARFRUIT, CropSpec
from sim.growth import GrowthModifiers
from sim.pipeline import (
    CASK_USES_PER_YEAR,
    DEHYDRATOR_DAYS,
    DEHYDRATOR_INPUT,
    PRESERVES_JAR_DAYS,
    _allocate_from_inventory,
    _allocate_aged_wine,
    _cask_fill_days,
    _crop_priority,
    _day_of_year,
    _pick_crop_by_priority,
    _pick_crop_with_min,
    _simulate_cask_batches,
    simulate_days_to_fill_casks_once,
    simulate_days_to_fill_casks_once_multi_plot,
    simulate_days_to_fill_casks_once_with_calendar,
    simulate_year_multi_crop,
)
from sim.plots import Plot, PlotCalendar


def test_day_of_year_wraps():
    """Day-of-year should wrap at 112 days."""
    assert _day_of_year(1, 0) == 1
    assert _day_of_year(1, 111) == 112
    assert _day_of_year(1, 112) == 1
    assert _day_of_year(5, 0) == 5


def test_crop_priority_starfruit_first():
    """Starfruit should be prioritized when present."""
    assert _crop_priority([ANCIENT_FRUIT, STARFRUIT]) == ["starfruit", "ancient"]
    assert _crop_priority([ANCIENT_FRUIT, STARFRUIT], ["apple"]) == ["starfruit", "ancient", "apple"]


def test_pick_crop_by_priority():
    """Pick the first crop with inventory in priority order."""
    inv = {"starfruit": 0, "ancient": 2}
    assert _pick_crop_by_priority(inv, ["starfruit", "ancient"]) == "ancient"
    inv["starfruit"] = 1
    assert _pick_crop_by_priority(inv, ["starfruit", "ancient"]) == "starfruit"


def test_pick_crop_with_min():
    """Pick the first crop with at least the requested inventory."""
    inv = {"starfruit": 4, "ancient": 5}
    assert _pick_crop_with_min(inv, ["starfruit", "ancient"], 5) == "ancient"
    inv["starfruit"] = 5
    assert _pick_crop_with_min(inv, ["starfruit", "ancient"], 5) == "starfruit"


def test_allocate_aged_wine_prioritizes_starfruit():
    """Aged wine allocation should prioritize starfruit within capacity."""
    base_wine = {"starfruit": 5, "ancient": 5}
    aged, remaining = _allocate_aged_wine(base_wine, casks=3, priority=["starfruit", "ancient"])
    assert CASK_USES_PER_YEAR == 2
    assert aged["starfruit"] == 5
    assert aged["ancient"] == 1
    assert remaining["starfruit"] == 0
    assert remaining["ancient"] == 4


def test_allocate_from_inventory_prioritizes_starfruit():
    """Inventory allocation should respect priority order."""
    inventory = {"starfruit": 3, "ancient": 2}
    taken, remaining = _allocate_from_inventory(inventory, capacity=4, priority=["starfruit", "ancient"])
    assert taken["starfruit"] == 3
    assert taken["ancient"] == 1
    assert remaining["starfruit"] == 0
    assert remaining["ancient"] == 1


def test_cask_fill_days_splits_year():
    """Cask batch days should split the year into two halves."""
    assert _cask_fill_days(112) == [0, 56]
    assert _cask_fill_days(1) == [0]


def test_simulate_cask_batches_prioritizes_starfruit():
    """Cask batch simulation should allocate wine by priority."""
    daily_base_wine = {"starfruit": [0, 1, 0, 0], "ancient": [0, 0, 1, 0]}
    starting = {"starfruit": 1, "ancient": 0}
    aged, remaining, fills = _simulate_cask_batches(
        daily_base_wine=daily_base_wine,
        starting_base_wine=starting,
        casks=1,
        batch_days=[0, 2],
        priority=["starfruit", "ancient"],
        max_days=4,
    )
    assert fills == [1, 1]
    assert aged["starfruit"] == 2
    assert aged["ancient"] == 0
    assert remaining["ancient"] == 1


def test_simulate_year_multi_crop_basic_counts():
    """A fast crop should yield predictable harvest totals."""
    fast_starfruit = CropSpec("starfruit", (1,), regrow_days=None)
    plot = Plot(name="plot", tiles_by_crop={"starfruit": 1}, calendar=PlotCalendar(type="always"))
    result = simulate_year_multi_crop(
        crops=[fast_starfruit],
        mods=GrowthModifiers(),
        plots=[plot],
        kegs=1,
        casks=0,
        max_days=9,
        start_day_of_year=1,
    )
    r = result.per_crop["starfruit"]
    assert r.fruit_harvested == 8
    assert r.base_wine_produced == 1
    assert r.wine_in_kegs_end == 1
    assert r.fruit_sold == r.fruit_unprocessed


def test_external_daily_fruit_processed():
    """External daily fruit should enter the processing pipeline."""
    plot = Plot(name="plot", tiles_by_crop={"starfruit": 0}, calendar=PlotCalendar(type="always"))
    result = simulate_year_multi_crop(
        crops=[],
        mods=GrowthModifiers(),
        plots=[plot],
        kegs=1,
        casks=0,
        max_days=8,
        start_day_of_year=1,
        external_daily_fruit={"apple": [1] * 7},
        external_priority=["apple"],
    )
    assert result.per_crop["apple"].fruit_harvested == 7
    assert result.per_crop["apple"].base_wine_produced == 1


def test_preserves_jars_produce_output():
    """Preserves jars should produce jelly after their cycle."""
    fast_starfruit = CropSpec("starfruit", (1,), regrow_days=None)
    plot = Plot(name="plot", tiles_by_crop={"starfruit": 0}, calendar=PlotCalendar(type="always"))
    result = simulate_year_multi_crop(
        crops=[fast_starfruit],
        mods=GrowthModifiers(),
        plots=[plot],
        kegs=0,
        casks=0,
        preserves_jars=1,
        dehydrators=0,
        max_days=PRESERVES_JAR_DAYS + 1,
        start_day_of_year=1,
        starting_fruit={"starfruit": 1},
    )
    r = result.per_crop["starfruit"]
    assert r.jelly_produced == 1


def test_dehydrators_require_batch_size():
    """Dehydrators should consume 5 fruit per batch."""
    fast_starfruit = CropSpec("starfruit", (1,), regrow_days=None)
    plot = Plot(name="plot", tiles_by_crop={"starfruit": 0}, calendar=PlotCalendar(type="always"))
    result = simulate_year_multi_crop(
        crops=[fast_starfruit],
        mods=GrowthModifiers(),
        plots=[plot],
        kegs=0,
        casks=0,
        preserves_jars=0,
        dehydrators=1,
        max_days=DEHYDRATOR_DAYS + 1,
        start_day_of_year=1,
        starting_fruit={"starfruit": DEHYDRATOR_INPUT},
    )
    r = result.per_crop["starfruit"]
    assert r.dried_fruit_produced == 1


def test_full_batch_requirement_reduces_casks():
    """Full batch rule should reduce effective casks when not met."""
    fast_starfruit = CropSpec("starfruit", (1,), regrow_days=None)
    plot = Plot(name="plot", tiles_by_crop={"starfruit": 1}, calendar=PlotCalendar(type="always"))
    result = simulate_year_multi_crop(
        crops=[fast_starfruit],
        mods=GrowthModifiers(),
        plots=[plot],
        kegs=1,
        casks=10,
        max_days=1,
        start_day_of_year=1,
        cask_full_batch_required=True,
        casks_with_walkways=4,
    )
    assert result.full_cask_batch_met is False
    assert result.casks_effective == 4


def test_full_batch_requires_each_batch_day():
    """Full batch check should require each batch day to be filled."""
    fast_starfruit = CropSpec("starfruit", (1,), regrow_days=None)
    plot = Plot(name="plot", tiles_by_crop={"starfruit": 0}, calendar=PlotCalendar(type="always"))
    result = simulate_year_multi_crop(
        crops=[fast_starfruit],
        mods=GrowthModifiers(),
        plots=[plot],
        kegs=0,
        casks=1,
        max_days=10,
        start_day_of_year=1,
        starting_base_wine={"starfruit": 1},
        cask_full_batch_required=True,
        casks_with_walkways=0,
    )
    assert result.full_cask_batch_met is False
    assert result.casks_effective == 0


def test_starting_inventory_used_by_kegs():
    """Starting fruit should be processed by kegs immediately."""
    fast_starfruit = CropSpec("starfruit", (1,), regrow_days=None)
    plot = Plot(name="plot", tiles_by_crop={"starfruit": 0}, calendar=PlotCalendar(type="always"))
    result = simulate_year_multi_crop(
        crops=[fast_starfruit],
        mods=GrowthModifiers(),
        plots=[plot],
        kegs=1,
        casks=0,
        max_days=7,
        start_day_of_year=1,
        starting_fruit={"starfruit": 1},
    )
    r = result.per_crop["starfruit"]
    assert r.wine_in_kegs_end == 1


def test_fertilizer_units_starfruit_per_harvest():
    """Fertilizer units should match seed units for single-harvest crops."""
    fast_starfruit = CropSpec("starfruit", (1,), regrow_days=None)
    plot = Plot(name="plot", tiles_by_crop={"starfruit": 1}, calendar=PlotCalendar(type="always"))
    result = simulate_year_multi_crop(
        crops=[fast_starfruit],
        mods=GrowthModifiers(fertilizer="speed_gro"),
        plots=[plot],
        kegs=1,
        casks=0,
        max_days=9,
        start_day_of_year=1,
    )
    r = result.per_crop["starfruit"]
    assert r.fertilizer_units_used == r.seed_units_used


def test_fertilizer_units_regrow_per_season():
    """Regrow crops should pay fertilizer per active season."""
    plot = Plot(name="plot", tiles_by_crop={"ancient": 2}, calendar=PlotCalendar(type="seasons", seasons=["spring", "summer"]))
    result = simulate_year_multi_crop(
        crops=[ANCIENT_FRUIT],
        mods=GrowthModifiers(fertilizer="deluxe_speed_gro"),
        plots=[plot],
        kegs=0,
        casks=0,
        max_days=1,
        start_day_of_year=1,
    )
    r = result.per_crop["ancient"]
    assert r.fertilizer_units_used == 4


def test_wrappers_match_multi_crop():
    """Wrapper functions should align with the multi-crop simulation."""
    fast_starfruit = CropSpec("starfruit", (1,), regrow_days=None)
    plot = Plot(name="plot", tiles_by_crop={"starfruit": 1}, calendar=PlotCalendar(type="always"))
    multi = simulate_year_multi_crop(
        crops=[fast_starfruit],
        mods=GrowthModifiers(),
        plots=[plot],
        kegs=1,
        casks=0,
        max_days=9,
        start_day_of_year=1,
    ).per_crop["starfruit"]

    single = simulate_days_to_fill_casks_once_with_calendar(
        crop=fast_starfruit,
        mods=GrowthModifiers(),
        tiles=1,
        kegs=1,
        casks=0,
        max_days=9,
        start_day_of_year=1,
        calendar=PlotCalendar(type="always"),
    )
    assert single.base_wine_produced == multi.base_wine_produced
    assert single.fruit_harvested == multi.fruit_harvested

    multi_plot = simulate_days_to_fill_casks_once_multi_plot(
        crop=fast_starfruit,
        mods=GrowthModifiers(),
        plots=[plot],
        kegs=1,
        casks=0,
        max_days=9,
        start_day_of_year=1,
    )
    assert multi_plot.base_wine_produced == multi.base_wine_produced

    direct = simulate_days_to_fill_casks_once(
        crop=fast_starfruit,
        mods=GrowthModifiers(),
        tiles=1,
        kegs=1,
        casks=0,
        max_days=9,
    )
    assert direct.base_wine_produced == multi.base_wine_produced
