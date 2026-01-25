import json
import sys

from sim.main import main


def test_main_outputs_profit(tmp_path, capsys, monkeypatch):
    """Main should run and print a total profit line."""
    cfg = {
        "kegs": 1,
        "casks": 1,
        "crop": "starfruit",
        "growth": {"fertilizer": "none", "agriculturist": False},
        "economy": {"wine_price": {"STARFRUIT": 100}, "seed_cost": {"STARFRUIT": 10}},
        "plots": [{"name": "plot", "tiles": {"STARFRUIT": 1}, "calendar": {"type": "always"}}],
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["sim.main", str(path)])
    code = main()
    out = capsys.readouterr().out
    assert code == 0
    assert "TOTAL PROFIT" in out
