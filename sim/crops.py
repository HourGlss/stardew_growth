from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CropId = Literal["ancient", "starfruit"]


@dataclass(frozen=True)
class CropSpec:
    crop_id: CropId
    # Phase days excluding the terminal "99999" element used in the game data.
    phase_days: tuple[int, ...]
    regrow_days: int | None  # None = single-harvest

    @property
    def base_days_to_first_harvest(self) -> int:
        """Return base days to first harvest without speed modifiers."""
        return sum(self.phase_days)


# From wiki stage tables:
# Starfruit: 2,3,2,3,3 = 13 days. :contentReference[oaicite:6]{index=6}
STARFRUIT = CropSpec("starfruit", (2, 3, 2, 3, 3), regrow_days=None)

# Ancient Fruit: 2,7,7,7,5 = 28 days; regrowth 7. :contentReference[oaicite:7]{index=7}
ANCIENT_FRUIT = CropSpec("ancient", (2, 7, 7, 7, 5), regrow_days=7)
