import json
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _load_json(name: str):
    path = DATA_DIR / name
    assert path.exists(), f"missing data file: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def test_crops_objects_core_ids():
    crops = _load_json("Crops.json")
    objects = _load_json("Objects.json")

    assert isinstance(crops, dict) and len(crops) > 0
    assert isinstance(objects, dict) and len(objects) > 0

    # Parsnip seeds -> Parsnip
    assert crops["472"]["HarvestItemId"] == "24"
    # Starfruit seeds -> Starfruit
    assert crops["486"]["HarvestItemId"] == "268"
    # Ancient seeds -> Ancient Fruit
    assert crops["499"]["HarvestItemId"] == "454"

    assert objects["454"]["Name"] == "Ancient Fruit"
    assert objects["454"]["Category"] == -79
    assert isinstance(objects["454"]["Price"], int)

    assert objects["725"]["Name"] == "Oak Resin"
    assert objects["709"]["Name"] == "Hardwood"


def test_supporting_data_files():
    farm_animals = _load_json("FarmAnimals.json")
    fish = _load_json("Fish.json")
    fish_pond = _load_json("FishPondData.json")
    fruit_trees = _load_json("FruitTrees.json")
    powers = _load_json("Powers.json")
    wild_trees = _load_json("WildTrees.json")
    wiki_crops = _load_json("wiki_crops.json")

    assert "White Chicken" in farm_animals
    assert "Pig" in farm_animals

    assert "128" in fish
    assert isinstance(fish["128"], str)

    assert isinstance(fish_pond, list) and fish_pond
    assert "Id" in fish_pond[0]
    assert "ProducedItems" in fish_pond[0]

    assert "628" in fruit_trees
    assert "Seasons" in fruit_trees["628"]

    assert "RustyKey" in powers

    assert "1" in wild_trees
    assert "TapItems" in wild_trees["1"]

    assert isinstance(wiki_crops, list) and wiki_crops
    assert any(row.get("name") == "Ancient Fruit" for row in wiki_crops)
