import pytest

from sim.plots import Plot, PlotCalendar, day_of_year_from_season_day, season_for_day_of_year


def test_season_for_day_of_year():
    """Season mapping should match Stardew's 28-day seasons."""
    assert season_for_day_of_year(1) == "spring"
    assert season_for_day_of_year(28) == "spring"
    assert season_for_day_of_year(29) == "summer"
    assert season_for_day_of_year(56) == "summer"
    assert season_for_day_of_year(57) == "fall"
    assert season_for_day_of_year(84) == "fall"
    assert season_for_day_of_year(85) == "winter"
    assert season_for_day_of_year(112) == "winter"
    with pytest.raises(ValueError):
        season_for_day_of_year(0)


def test_day_of_year_from_season_day():
    """Season/day conversion should align with season boundaries."""
    assert day_of_year_from_season_day("spring", 1) == 1
    assert day_of_year_from_season_day("summer", 1) == 29
    assert day_of_year_from_season_day("fall", 1) == 57
    assert day_of_year_from_season_day("winter", 1) == 85


def test_plot_calendar_is_active():
    """Plot calendars should report activity correctly."""
    always = PlotCalendar(type="always")
    assert always.is_active(1)
    summer_only = PlotCalendar(type="seasons", seasons=["summer"])
    assert summer_only.is_active(30)
    assert not summer_only.is_active(1)


def test_plot_tiles_helpers():
    """Plot tile helpers should handle per-crop and all-crop mappings."""
    plot = Plot(name="plot", tiles_by_crop={"starfruit": 3, "ancient": 2}, calendar=PlotCalendar(type="always"))
    assert plot.tiles_for_crop("starfruit") == 3
    assert plot.tiles_for_crop("ancient") == 2
    assert plot.tiles_total == 5

    shared = Plot(name="plot", tiles_by_crop={"all": 5}, calendar=PlotCalendar(type="always"))
    assert shared.tiles_for_crop("starfruit") == 5
    assert shared.tiles_total == 5
