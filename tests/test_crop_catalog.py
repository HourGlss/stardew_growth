import json

from sim.crop_catalog import load_crop_catalog, seed_availability, ShopAccess


def test_load_crop_catalog_and_seed_availability(tmp_path):
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

    catalog = load_crop_catalog(data_dir=tmp_path)
    crop = catalog.by_harvest_id["100"]
    assert crop.name == "Parsnip"
    assert crop.base_price == 35
    assert crop.seed_price == 20
    assert crop.category == "vegetable"

    availability = seed_availability(crop, ShopAccess(pierre=True, joja=False, oasis=False, traveling_cart=False))
    assert availability.purchasable is True
    assert availability.price == 20
