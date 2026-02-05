import pytest

from sim.ancient_seeds import (
    AncientPlant,
    SeedTimeline,
    format_day,
    parse_ancient_plants_from_save,
    parse_current_day_from_save,
    simulate_seed_timeline,
    summarize_plants,
    threshold_days,
)
from sim.plots import PlotCalendar, day_of_year_from_season_day


def test_parse_current_day_from_save(tmp_path):
    save_path = tmp_path / "save.xml"
    save_path.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<SaveGame>
  <currentSeason>summer</currentSeason>
  <dayOfMonth>7</dayOfMonth>
</SaveGame>
""",
        encoding="utf-8",
    )
    season, day, doy = parse_current_day_from_save(save_path)
    assert season == "summer"
    assert day == 7
    assert doy == day_of_year_from_season_day("summer", 7)


def test_parse_current_day_missing_fields(tmp_path):
    save_path = tmp_path / "bad.xml"
    save_path.write_text("<SaveGame></SaveGame>", encoding="utf-8")
    with pytest.raises(ValueError, match="currentSeason"):
        parse_current_day_from_save(save_path)


def test_parse_ancient_plants_from_save(tmp_path):
    save_path = tmp_path / "ancient.xml"
    save_path.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<SaveGame xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <locations>
    <GameLocation>
      <name>Greenhouse</name>
      <terrainFeatures>
        <item>
          <key><Vector2><X>0</X><Y>0</Y></Vector2></key>
          <value>
            <TerrainFeature xsi:type="HoeDirt">
              <crop>
                <phaseDays><int>1</int><int>6</int><int>6</int><int>7</int><int>5</int><int>99999</int></phaseDays>
                <currentPhase>4</currentPhase>
                <dayOfCurrentPhase>3</dayOfCurrentPhase>
                <indexOfHarvest>454</indexOfHarvest>
                <fullyGrown>false</fullyGrown>
                <dead>false</dead>
              </crop>
            </TerrainFeature>
          </value>
        </item>
      </terrainFeatures>
    </GameLocation>
    <GameLocation>
      <name>Farm</name>
      <terrainFeatures>
        <item>
          <key><Vector2><X>1</X><Y>0</Y></Vector2></key>
          <value>
            <TerrainFeature xsi:type="HoeDirt">
              <crop>
                <phaseDays><int>1</int><int>6</int><int>6</int><int>7</int><int>5</int><int>99999</int></phaseDays>
                <currentPhase>0</currentPhase>
                <dayOfCurrentPhase>0</dayOfCurrentPhase>
                <indexOfHarvest>454</indexOfHarvest>
                <fullyGrown>false</fullyGrown>
                <dead>false</dead>
              </crop>
            </TerrainFeature>
          </value>
        </item>
      </terrainFeatures>
    </GameLocation>
  </locations>
</SaveGame>
""",
        encoding="utf-8",
    )
    plants = parse_ancient_plants_from_save(save_path)
    counts = summarize_plants(plants)
    assert counts["greenhouse"] == 1
    assert counts["outdoors"] == 1
    greenhouse = next(p for p in plants if p.location == "greenhouse")
    assert greenhouse.days_until_harvest == 2


def test_parse_ancient_plants_none(tmp_path):
    save_path = tmp_path / "empty.xml"
    save_path.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<SaveGame xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <locations>
    <GameLocation>
      <name>Farm</name>
      <terrainFeatures />
    </GameLocation>
  </locations>
</SaveGame>
""",
        encoding="utf-8",
    )
    plants = parse_ancient_plants_from_save(save_path)
    assert plants == []


def test_simulate_seed_timeline_greenhouse_harvests():
    plant = AncientPlant(
        location="greenhouse",
        days_until_harvest=0,
        calendar=PlotCalendar(type="always"),
    )
    timeline = simulate_seed_timeline([plant], start_day_of_year=1, max_days=7)
    assert timeline.min_seeds[0] == 0
    assert timeline.min_seeds[1] == 1
    assert timeline.max_seeds[1] == 3
    assert timeline.min_seeds[7] == 1


def test_simulate_seed_timeline_no_plants():
    timeline = simulate_seed_timeline([], start_day_of_year=1, max_days=5)
    assert all(value == 0 for value in timeline.min_seeds)
    assert all(value == 0 for value in timeline.max_seeds)


def test_simulate_seed_timeline_outdoor_pauses_in_winter():
    plant = AncientPlant(
        location="outdoors",
        days_until_harvest=1,
        calendar=PlotCalendar(type="seasons", seasons=("spring", "summer", "fall")),
    )
    start_day = day_of_year_from_season_day("winter", 15)
    timeline = simulate_seed_timeline([plant], start_day_of_year=start_day, max_days=5)
    assert timeline.max_seeds[-1] == 0


def test_threshold_days():
    timeline = SeedTimeline(days=list(range(4)), min_seeds=[0, 1, 2, 3], avg_seeds=[0, 2, 4, 6], max_seeds=[0, 3, 6, 9])
    targets = threshold_days(timeline, [2, 5])
    assert targets[2]["min"] == 2
    assert targets[2]["avg"] == 1
    assert targets[2]["max"] == 1
    assert targets[5]["min"] is None
    assert targets[5]["avg"] == 3
    assert targets[5]["max"] == 2


def test_format_day():
    assert format_day(day_of_year_from_season_day("spring", 1), 0) == "Spring 1"
