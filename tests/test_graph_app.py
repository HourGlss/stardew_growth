import numpy as np

from sim.config import AppConfig
from sim.graph_app import _grid_max, _pareto_minimal, _solutions_for_target, _parse_args, _apply_limit, _parse_graph_limits


def test_grid_max():
    z = np.array([[1, 2], [5, 4]], dtype=float)
    z_max, x_max, y_max = _grid_max(z, [10, 20], [100, 200])
    assert z_max == 5
    assert x_max == 10
    assert y_max == 200


def test_solutions_and_pareto():
    z = np.array([[5, 9], [10, 11]], dtype=float)
    solutions = _solutions_for_target([0, 1], [0, 1], z, 10)
    assert sorted(solutions) == [(0, 1, 10), (1, 1, 11)]
    pareto = _pareto_minimal(solutions)
    assert pareto == [(0, 1, 10)]


def test_parse_args_with_target():
    config, overrides, output, target = _parse_args(
        ["graph_app.py", "save.xml", "overrides.json", "out.png", "--target", "12,000,000"]
    )
    assert config == "save.xml"
    assert overrides == "overrides.json"
    assert output == "out.png"
    assert target == 12000000


def test_apply_limit_clamps_and_keeps_base():
    values = [0, 10, 20, 30]
    assert _apply_limit(values, base=10, max_total=18) == [0, 10]
    assert _apply_limit(values, base=5, max_total=7) == [0, 5]


def test_parse_graph_limits_new_vs_total():
    cfg = AppConfig(tiles=0, kegs=10, casks=5)
    limits = _parse_graph_limits({"max_new_kegs": 5, "max_total_casks": 20}, cfg)
    assert limits.max_total_kegs == 15
    assert limits.max_total_casks == 20
