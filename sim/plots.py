from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

CalendarType = Literal["always", "seasons"]
Season = Literal["spring", "summer", "fall", "winter"]


def season_for_day_of_year(day_of_year: int) -> Season:
    """Return the season for a 1-based day-of-year."""
    # Stardew seasons are 28 days each, 1-indexed day_of_year.
    #  1..28  = spring
    # 29..56  = summer
    # 57..84  = fall
    # 85..112 = winter
    if day_of_year < 1:
        raise ValueError("day_of_year must be >= 1")
    idx = (day_of_year - 1) // 28
    return ("spring", "summer", "fall", "winter")[idx % 4]  # wrap years


def day_of_year_from_season_day(season: Season, day: int) -> int:
    """Convert a season/day pair (1..28) to day-of-year (1..112)."""
    if day < 1 or day > 28:
        raise ValueError("day must be in 1..28")
    offsets = {"spring": 0, "summer": 28, "fall": 56, "winter": 84}
    return offsets[season] + day


@dataclass(frozen=True)
class PlotCalendar:
    type: CalendarType
    seasons: Sequence[Season] = ()

    def is_active(self, day_of_year: int) -> bool:
        """Return True if this plot calendar is active on the given day-of-year."""
        if self.type == "always":
            return True
        if self.type == "seasons":
            return season_for_day_of_year(day_of_year) in set(self.seasons)
        raise ValueError(f"Unknown calendar type: {self.type}")


@dataclass(frozen=True)
class Plot:
    name: str
    tiles_by_crop: dict[str, int]
    calendar: PlotCalendar

    def tiles_for_crop(self, crop_id: str) -> int:
        """Return tile count for a crop, falling back to a shared 'all' bucket."""
        if crop_id in self.tiles_by_crop:
            return self.tiles_by_crop[crop_id]
        return self.tiles_by_crop.get("all", 0)

    @property
    def tiles_total(self) -> int:
        """Return total tiles for this plot across all configured crops."""
        if "all" in self.tiles_by_crop and len(self.tiles_by_crop) == 1:
            return self.tiles_by_crop["all"]
        return sum(self.tiles_by_crop.values())
