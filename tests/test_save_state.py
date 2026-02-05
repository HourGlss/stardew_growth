import json

from sim.crop_catalog import load_crop_catalog
from sim.save_state import parse_save_state


def _write_min_data(tmp_path):
    crops = {
        "472": {
            "Seasons": ["Spring"],
            "DaysInPhase": [1, 1, 1, 1],
            "RegrowDays": -1,
            "IsRaised": False,
            "IsPaddyCrop": False,
            "NeedsWatering": True,
            "HarvestItemId": "100",
            "HarvestMinStack": 1,
            "HarvestMaxStack": 1,
            "HarvestMaxIncreasePerFarmingLevel": 0.0,
            "ExtraHarvestChance": 0.0,
        }
    }
    objects = {
        "100": {
            "Name": "Parsnip",
            "DisplayName": "Parsnip",
            "Category": -75,
            "Price": 35,
            "ContextTags": ["item_vegetable"],
        },
        "472": {
            "Name": "Parsnip Seeds",
            "DisplayName": "Parsnip Seeds",
            "Category": -74,
            "Price": 10,
            "ContextTags": ["item_seed"],
        },
    }
    wiki_rows = [
        {
            "name": "Parsnip",
            "seed_name": "Parsnip Seeds",
            "seed_price": 20,
            "seed_sources": {"pierre": 20},
        }
    ]
    (tmp_path / "Crops.json").write_text(json.dumps(crops), encoding="utf-8")
    (tmp_path / "Objects.json").write_text(json.dumps(objects), encoding="utf-8")
    (tmp_path / "wiki_crops.json").write_text(json.dumps(wiki_rows), encoding="utf-8")


def test_parse_save_state_basic(tmp_path):
    _write_min_data(tmp_path)
    catalog = load_crop_catalog(data_dir=tmp_path)

    save_path = tmp_path / "save.xml"
    save_path.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<SaveGame xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <currentSeason>spring</currentSeason>
  <dayOfMonth>5</dayOfMonth>
  <year>2</year>
  <player>
    <farmingLevel>5</farmingLevel>
    <professions>
      <int>1</int>
      <int>4</int>
    </professions>
    <mailReceived>
      <string>ccVault</string>
    </mailReceived>
    <items>
      <Item>
        <itemId>472</itemId>
        <category>-74</category>
        <stack>5</stack>
      </Item>
    </items>
  </player>
  <locations>
    <GameLocation>
      <name>Farm</name>
      <objects>
        <item>
          <key><Vector2><X>0</X><Y>0</Y></Vector2></key>
          <value><Object><name>Quality Sprinkler</name><parentSheetIndex>621</parentSheetIndex></Object></value>
        </item>
        <item>
          <key><Vector2><X>2</X><Y>0</Y></Vector2></key>
          <value><Object><name>Keg</name></Object></value>
        </item>
        <item>
          <key><Vector2><X>3</X><Y>0</Y></Vector2></key>
          <value><Object><name>Seed Maker</name></Object></value>
        </item>
      </objects>
      <terrainFeatures>
        <item>
          <key><Vector2><X>1</X><Y>0</Y></Vector2></key>
          <value>
            <TerrainFeature xsi:type="HoeDirt">
              <fertilizer>(O)465</fertilizer>
              <crop>
                <phaseDays><int>1</int><int>1</int><int>1</int><int>1</int><int>99999</int></phaseDays>
                <currentPhase>0</currentPhase>
                <dayOfCurrentPhase>0</dayOfCurrentPhase>
                <indexOfHarvest>100</indexOfHarvest>
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

    farm = parse_save_state(save_path, catalog)
    assert farm.season == "spring"
    assert farm.day_of_month == 5
    assert farm.year == 2
    assert farm.machines.kegs == 1
    assert farm.machines.seed_makers == 1
    assert farm.shop_access.oasis is True
    assert farm.seed_inventory["472"] == 5
    assert len(farm.tiles) == 1
    tile = farm.tiles[0]
    assert tile.watered is True
    assert tile.fertilizer == "speed_gro"
    assert tile.crop is not None
    assert tile.crop.days_until_harvest == 4
