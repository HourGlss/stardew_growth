from sim.fruit_trees import FruitTreesConfig, build_daily_fruit, normalize_fruit_tree_name, total_tree_counts


def test_normalize_fruit_tree_name():
    """Fruit tree normalization should accept common variants."""
    assert normalize_fruit_tree_name("Cherry") == "cherry"
    assert normalize_fruit_tree_name("pomegranate") == "pomegranate"
    assert normalize_fruit_tree_name("Mango") == "mango"
    assert normalize_fruit_tree_name("unknown") is None


def test_build_daily_fruit_respects_seasons_and_greenhouse():
    """Greenhouse/always fruit should be daily; outdoor should be seasonal."""
    cfg = FruitTreesConfig(
        greenhouse={"apple": 2},
        outdoors={"apricot": 1, "orange": 1},
        always={"banana": 1},
    )
    daily = build_daily_fruit(cfg, start_day_of_year=1, max_days=56)

    assert daily["apple"] == [2] * 56
    assert daily["banana"] == [1] * 56

    assert sum(daily["apricot"][:28]) == 28
    assert sum(daily["apricot"][28:]) == 0
    assert sum(daily["orange"][:28]) == 0
    assert sum(daily["orange"][28:]) == 28


def test_total_tree_counts_sums_scopes():
    """Totals should include all scopes."""
    cfg = FruitTreesConfig(greenhouse={"apple": 2}, outdoors={"apple": 1}, always={"cherry": 3})
    assert total_tree_counts(cfg) == {"apple": 3, "cherry": 3}
