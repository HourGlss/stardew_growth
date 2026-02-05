from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt

from sim.ancient_seeds import (
    SEED_AVG,
    SEED_MAX,
    SEED_MIN,
    format_day,
    parse_ancient_plants_from_save,
    parse_current_day_from_save,
    simulate_seed_timeline,
    summarize_plants,
    threshold_days,
)
from sim.save_loader import load_config


TARGETS = [10, 20, 30, 50, 100, 150, 200, 250, 300, 350, 400]
DEFAULT_OUTPUT = "ancient_seed_timeline.png"


def main() -> int:
    if len(sys.argv) not in (2, 3):
        print("Usage: python -m sim.ancient_seed_app path/to/save.xml [output.png]")
        return 2

    save_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) == 3 else DEFAULT_OUTPUT

    season, day_of_month, start_day_of_year = parse_current_day_from_save(save_path)
    plants = parse_ancient_plants_from_save(save_path)
    counts = summarize_plants(plants)

    try:
        cfg = load_config(save_path)
        agriculturist = cfg.professions.farming.agriculturist
    except Exception:
        agriculturist = False

    print(f"start date: {season.capitalize()} {day_of_month} (day {start_day_of_year})")
    print(f"ancient plants: greenhouse={counts['greenhouse']} outdoors={counts['outdoors']} always={counts['always']}")
    print(f"agriculturist: {agriculturist}")
    print(f"seed maker per-fruit assumptions: min={SEED_MIN}, avg={SEED_AVG}, max={SEED_MAX}")

    if not plants:
        print("no ancient fruit plants found in the save file.")
        return 0

    max_days = 112 * 20
    timeline = simulate_seed_timeline(plants, start_day_of_year, max_days)
    thresholds = threshold_days(timeline, TARGETS)

    print("\nseed timeline (days since today):")
    for target in TARGETS:
        entry = thresholds[target]
        min_day = entry["min"]
        avg_day = entry["avg"]
        max_day = entry["max"]
        min_label = f"{min_day} ({format_day(start_day_of_year, min_day)})" if min_day is not None else "not reached"
        avg_label = f"{avg_day} ({format_day(start_day_of_year, avg_day)})" if avg_day is not None else "not reached"
        max_label = f"{max_day} ({format_day(start_day_of_year, max_day)})" if max_day is not None else "not reached"
        print(f"  {target} seeds: min {min_label}, avg {avg_label}, max {max_label}")

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(timeline.days, timeline.min_seeds, label="min seeds", linewidth=2)
    ax.plot(timeline.days, timeline.avg_seeds, label="avg seeds", linewidth=2)
    ax.plot(timeline.days, timeline.max_seeds, label="max seeds", linewidth=2)
    ax.set_title("Ancient Seed Timeline (all fruit into seed makers)")
    ax.set_xlabel("Days since today")
    ax.set_ylabel("Ancient seeds accumulated")
    ax.legend()
    ax.grid(True, alpha=0.2)

    for target in TARGETS:
        day_hit = thresholds[target]["avg"]
        if day_hit is None:
            continue
        ax.scatter(day_hit, timeline.avg_seeds[day_hit], s=30)

    output_path = str(Path(output_path))
    fig.tight_layout()
    fig.savefig(output_path, dpi=200)
    print(f"\nchart saved to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
