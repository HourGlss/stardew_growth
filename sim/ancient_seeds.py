from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import xml.etree.ElementTree as ET

from sim.plots import PlotCalendar, season_for_day_of_year, day_of_year_from_season_day


ANCIENT_FRUIT_ID = "454"
ANCIENT_REGROW_DAYS = 7
SEED_MIN = 1
SEED_MAX = 3
SEED_AVG = 2.0


@dataclass
class AncientPlant:
    location: str
    days_until_harvest: int
    calendar: PlotCalendar


@dataclass
class SeedTimeline:
    days: list[int]
    min_seeds: list[int]
    avg_seeds: list[float]
    max_seeds: list[int]


def parse_current_day_from_save(path: str | Path) -> tuple[str, int, int]:
    """Return (season, day_of_month, day_of_year) from a save file."""
    root = ET.fromstring(Path(path).read_text(encoding="utf-8"))
    season = (root.findtext("currentSeason") or "").strip().lower()
    if not season:
        raise ValueError("save file missing currentSeason")
    day_raw = root.findtext("dayOfMonth")
    if day_raw is None:
        raise ValueError("save file missing dayOfMonth")
    day_of_month = int(day_raw)
    day_of_year = day_of_year_from_season_day(season, day_of_month)
    return season, day_of_month, day_of_year


def parse_ancient_plants_from_save(path: str | Path) -> list[AncientPlant]:
    """Return ancient fruit plants found in the save with their harvest timers."""
    root = ET.fromstring(Path(path).read_text(encoding="utf-8"))
    plants: list[AncientPlant] = []
    for loc in root.findall("locations/GameLocation"):
        loc_name = (loc.findtext("name") or "").strip()
        terrain = loc.find("terrainFeatures")
        if terrain is None:
            continue
        for item in terrain.findall("item"):
            tf = item.find("value/TerrainFeature")
            if tf is None:
                continue
            tf_type = tf.attrib.get("{http://www.w3.org/2001/XMLSchema-instance}type")
            if tf_type and tf_type != "HoeDirt":
                continue
            crop = tf.find("crop")
            if crop is None:
                continue
            if (crop.findtext("dead") or "").lower() == "true":
                continue
            harvest = crop.findtext("indexOfHarvest")
            if harvest != ANCIENT_FRUIT_ID:
                continue
            days_until = _days_until_next_harvest(crop)
            if loc_name == "Greenhouse":
                calendar = PlotCalendar(type="always")
                plants.append(AncientPlant(location="greenhouse", days_until_harvest=days_until, calendar=calendar))
            elif loc_name.lower().startswith("island"):
                calendar = PlotCalendar(type="always")
                plants.append(AncientPlant(location="always", days_until_harvest=days_until, calendar=calendar))
            else:
                calendar = PlotCalendar(type="seasons", seasons=("spring", "summer", "fall"))
                plants.append(AncientPlant(location="outdoors", days_until_harvest=days_until, calendar=calendar))
    return plants


def simulate_seed_timeline(
    plants: list[AncientPlant],
    start_day_of_year: int,
    max_days: int,
) -> SeedTimeline:
    """Simulate seed accumulation over time from ancient fruit plants."""
    days = list(range(max_days + 1))
    min_seeds = [0]
    avg_seeds = [0.0]
    max_seeds = [0]

    states = [AncientPlant(p.location, p.days_until_harvest, p.calendar) for p in plants]
    for day in range(max_days):
        day_of_year = _day_of_year(start_day_of_year, day)
        harvested = 0
        for plant in states:
            if not plant.calendar.is_active(day_of_year):
                continue
            if plant.days_until_harvest <= 0:
                harvested += 1
                plant.days_until_harvest = ANCIENT_REGROW_DAYS
                continue
            plant.days_until_harvest -= 1
            if plant.days_until_harvest <= 0:
                harvested += 1
                plant.days_until_harvest = ANCIENT_REGROW_DAYS
        min_seeds.append(min_seeds[-1] + harvested * SEED_MIN)
        avg_seeds.append(avg_seeds[-1] + harvested * SEED_AVG)
        max_seeds.append(max_seeds[-1] + harvested * SEED_MAX)
    return SeedTimeline(days=days, min_seeds=min_seeds, avg_seeds=avg_seeds, max_seeds=max_seeds)


def threshold_days(
    timeline: SeedTimeline,
    targets: list[int],
) -> dict[int, dict[str, int | None]]:
    """Return first day index reaching each target for min/avg/max curves."""
    out: dict[int, dict[str, int | None]] = {}
    for target in targets:
        out[target] = {
            "min": _first_day(timeline.min_seeds, target),
            "avg": _first_day(timeline.avg_seeds, target),
            "max": _first_day(timeline.max_seeds, target),
        }
    return out


def format_day(start_day_of_year: int, day_index: int) -> str:
    """Return a human-readable season/day string for a day offset."""
    day_of_year = _day_of_year(start_day_of_year, day_index)
    season = season_for_day_of_year(day_of_year)
    day_of_season = ((day_of_year - 1) % 28) + 1
    return f"{season.capitalize()} {day_of_season}"


def summarize_plants(plants: list[AncientPlant]) -> dict[str, int]:
    """Return counts of plants by location."""
    counts = {"greenhouse": 0, "outdoors": 0, "always": 0}
    for plant in plants:
        if plant.location in counts:
            counts[plant.location] += 1
    return counts


def _first_day(values: list[float | int], target: int) -> int | None:
    for idx, value in enumerate(values):
        if value >= target:
            return idx
    return None


def _day_of_year(start_day_of_year: int, day_index: int) -> int:
    return ((start_day_of_year - 1 + day_index) % 112) + 1


def _days_until_next_harvest(crop: ET.Element) -> int:
    phase_days = [int(node.text or 0) for node in crop.findall("phaseDays/int")]
    while phase_days and phase_days[-1] >= 99999:
        phase_days.pop()
    current_phase = int(crop.findtext("currentPhase") or 0)
    day_of_phase = int(crop.findtext("dayOfCurrentPhase") or 0)
    full_grown = (crop.findtext("fullGrown") or "").lower() == "true"
    fully_grown = (crop.findtext("fullyGrown") or "").lower() == "true"
    if full_grown or fully_grown:
        return max(0, ANCIENT_REGROW_DAYS - day_of_phase)
    if current_phase < 0:
        current_phase = 0
    if current_phase >= len(phase_days):
        return 0
    remaining = sum(phase_days[current_phase:]) - day_of_phase
    return max(0, remaining)
