import json
from pathlib import Path

import pytest

from sim.save_loader import load_config, sprinkler_tiles_from_storage


def test_load_config_from_save_uses_cellar_only(tmp_path):
    save_path = Path('tests/save_fixture.xml')
    overrides = {
        "economy": {"wine_price": {"STARFRUIT": 100}},
        "growth": {"fertilizer": "deluxe_speed_gro"},
    }
    overrides_path = tmp_path / "overrides.json"
    overrides_path.write_text(json.dumps(overrides), encoding="utf-8")

    cfg = load_config(save_path, overrides_path)

    assert cfg.casks == 2  # Cellar2 cask ignored
    assert cfg.kegs == 1
    assert cfg.preserves_jars == 1
    assert cfg.oil_makers == 1
    assert cfg.mayo_machines == 1
    assert cfg.cheese_presses == 1
    assert cfg.looms == 1
    assert cfg.bees.bee_houses == 1
    assert cfg.fruit_trees.outdoors["cherry"] == 1
    assert cfg.fruit_trees.greenhouse["apple"] == 1

    # Greenhouse crop tiles
    greenhouse = next(p for p in cfg.plots if p.name == "greenhouse")
    assert greenhouse.tiles_by_crop["starfruit"] == 1
    assert greenhouse.tiles_by_crop["ancient"] == 1

    # Animals parsed from building interiors
    assert cfg.animals.coops[0].chickens == 1
    assert cfg.animals.coops[0].ducks == 1
    assert cfg.animals.coops[0].void_chickens == 1
    assert cfg.animals.coops[0].rabbits == 1
    assert cfg.animals.barns[0].cows == 1
    assert cfg.animals.barns[0].goats == 1
    assert cfg.animals.barns[0].pigs == 1
    assert cfg.animals.barns[0].sheep == 1

    # Professions from save
    assert cfg.professions.farming.tiller is True
    assert cfg.professions.farming.artisan is True
    assert cfg.professions.foraging.gatherer is True
    assert cfg.professions.foraging.botanist is True

    # Economy override applied
    assert cfg.economy.wine_price["starfruit"] == 100


def test_rejects_over_capacity_coop_from_json(tmp_path):
    raw = {
        "kegs": 1,
        "casks": 1,
        "animals": {
            "coops": [{"name": "coop1", "chickens": 20, "ducks": 0}],
            "barns": [],
        },
        "plots": [{"name": "plot", "tiles": {"STARFRUIT": 1}, "calendar": {"type": "always"}}],
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="coop"):
        load_config(path)


def test_rejects_truffle_crop_in_hoedirt(tmp_path):
    save_path = tmp_path / "bad_save.xml"
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
                <indexOfHarvest>430</indexOfHarvest>
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
    with pytest.raises(ValueError, match="truffle"):  # truffles are not crops
        load_config(save_path)


def test_rejects_invalid_animal_rate(tmp_path):
    raw = {
        "kegs": 1,
        "casks": 1,
        "animals": {"large_egg_rate": 1.5},
        "plots": [{"name": "plot", "tiles": {"STARFRUIT": 1}, "calendar": {"type": "always"}}],
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="large_egg_rate"):
        load_config(path)


def test_rejects_invalid_plot_season_for_starfruit(tmp_path):
    raw = {
        "kegs": 1,
        "casks": 1,
        "crop": "starfruit",
        "plots": [
            {"name": "outdoors", "tiles": {"STARFRUIT": 1}, "calendar": {"type": "seasons", "seasons": ["winter"]}}
        ],
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="seasons"):
        load_config(path)


def test_rejects_casks_with_walkways_overflow(tmp_path):
    raw = {
        "kegs": 1,
        "casks": 5,
        "economy": {"casks_with_walkways": 6},
        "plots": [{"name": "plot", "tiles": {"STARFRUIT": 1}, "calendar": {"type": "always"}}],
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="casks_with_walkways"):
        load_config(path)


def test_rejects_negative_fruit_tree_counts(tmp_path):
    raw = {
        "kegs": 1,
        "casks": 1,
        "fruit_trees": {"greenhouse": {"Apple": -1}},
        "plots": [{"name": "plot", "tiles": {"STARFRUIT": 1}, "calendar": {"type": "always"}}],
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="fruit_trees.greenhouse.apple"):
        load_config(path)


def test_sprinkler_tiles_from_storage(tmp_path):
    save_path = tmp_path / "sprinklers.xml"
    save_path.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<SaveGame xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <locations>
    <GameLocation>
      <name>Farm</name>
      <objects>
        <item>
          <key><Vector2><X>0</X><Y>0</Y></Vector2></key>
          <value>
            <Object>
              <name>Chest</name>
              <items>
                <Item xsi:type="Object">
                  <name>Quality Sprinkler</name>
                  <parentSheetIndex>621</parentSheetIndex>
                  <itemId>621</itemId>
                  <stack>2</stack>
                </Item>
                <Item xsi:type="Object">
                  <name>Iridium Sprinkler</name>
                  <parentSheetIndex>645</parentSheetIndex>
                  <itemId>645</itemId>
                  <stack>1</stack>
                </Item>
                <Item xsi:type="Object">
                  <name>Sprinkler</name>
                  <parentSheetIndex>599</parentSheetIndex>
                  <itemId>599</itemId>
                  <stack>5</stack>
                </Item>
              </items>
            </Object>
          </value>
        </item>
      </objects>
    </GameLocation>
  </locations>
</SaveGame>
""",
        encoding="utf-8",
    )
    tiles, counts = sprinkler_tiles_from_storage(save_path)
    assert counts["quality"] == 2
    assert counts["iridium"] == 1
    assert tiles == (2 * 8) + (1 * 24)
