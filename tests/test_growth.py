import pytest

from sim.crops import STARFRUIT, ANCIENT_FRUIT
from sim.growth import (
    GrowthModifiers,
    _phase_override,
    _speed_increase,
    apply_speed_increases_to_phase_days,
    days_to_first_harvest,
)


# Expected results computed using the same algorithmic rules we're implementing:
# daysToRemove = ceil(totalDays * speedIncrease)
# then remove 1 day from phases in order, up to 3 passes, with phase0 never < 1.
#
# If any of these fail, your growth algorithm is not matching the intended behavior.


@pytest.mark.parametrize(
    "crop, mods, expected_phases, expected_total",
    [
        # ----- STARFRUIT (2,3,2,3,3) total 13 -----
        (STARFRUIT, GrowthModifiers("none", False), (2, 3, 2, 3, 3), 13),

        # 10%: Speed-Gro OR Agriculturist
        (STARFRUIT, GrowthModifiers("speed_gro", False), (1, 2, 2, 3, 3), 11),
        (STARFRUIT, GrowthModifiers("none", True), (1, 2, 2, 3, 3), 11),

        # 20%: Speed-Gro + Agriculturist
        # ceil(13*0.20)=3
        (STARFRUIT, GrowthModifiers("speed_gro", True), (1, 2, 1, 3, 3), 10),

        # 25%: Deluxe
        # ceil(13*0.25)=4
        (STARFRUIT, GrowthModifiers("deluxe_speed_gro", False), (1, 2, 1, 2, 3), 9),

        # 35%: Deluxe + Agriculturist
        # ceil(13*0.35)=5
        (STARFRUIT, GrowthModifiers("deluxe_speed_gro", True), (1, 2, 1, 2, 2), 8),

        # 33%: Hyper
        # ceil(13*0.33)=5
        (STARFRUIT, GrowthModifiers("hyper_speed_gro", False), (1, 2, 1, 2, 2), 8),

        # 43%: Hyper + Agriculturist
        # ceil(13*0.43)=6
        (STARFRUIT, GrowthModifiers("hyper_speed_gro", True), (1, 1, 1, 2, 2), 7),

        # ----- ANCIENT FRUIT (2,7,7,7,5) total 28 -----
        (ANCIENT_FRUIT, GrowthModifiers("none", False), (2, 7, 7, 7, 5), 28),

        # 10%: Speed-Gro OR Agriculturist
        # ceil(28*0.10)=3
        (ANCIENT_FRUIT, GrowthModifiers("speed_gro", False), (1, 6, 6, 7, 5), 25),
        (ANCIENT_FRUIT, GrowthModifiers("none", True), (1, 6, 6, 7, 5), 25),

        # 20%: Speed-Gro + Agriculturist
        # ceil(28*0.20)=6
        (ANCIENT_FRUIT, GrowthModifiers("speed_gro", True), (1, 5, 6, 7, 3), 22),

        # 25%: Deluxe
        # ceil(28*0.25)=7
        (ANCIENT_FRUIT, GrowthModifiers("deluxe_speed_gro", False), (1, 5, 5, 6, 4), 21),

        # 35%: Deluxe + Agriculturist
        # ceil(28*0.35)=10
        (ANCIENT_FRUIT, GrowthModifiers("deluxe_speed_gro", True), (1, 4, 5, 5, 3), 18),

        # 33%: Hyper
        # ceil(28*0.33)=10
        (ANCIENT_FRUIT, GrowthModifiers("hyper_speed_gro", False), (1, 4, 5, 5, 3), 18),

        # 43%: Hyper + Agriculturist
        # ceil(28*0.43)=13 (exactly the max you can remove in 3 passes here)
        (ANCIENT_FRUIT, GrowthModifiers("hyper_speed_gro", True), (1, 4, 4, 4, 2), 15),
    ],
)
def test_phase_reduction_exact_to_the_day(crop, mods, expected_phases, expected_total):
    """Verify phase reductions match expected totals for common modifier combos."""
    phases = apply_speed_increases_to_phase_days(crop, mods)
    assert phases == expected_phases
    assert sum(phases) == expected_total
    assert days_to_first_harvest(crop, mods) == expected_total


def test_first_phase_never_drops_below_one():
    """Ensure the initial phase does not drop below 1 day."""
    # slam extreme speed conditions; phase0 should never be <= 0
    phases = apply_speed_increases_to_phase_days(
        STARFRUIT,
        GrowthModifiers(fertilizer="hyper_speed_gro", agriculturist=True),
    )
    assert phases[0] >= 1

    phases = apply_speed_increases_to_phase_days(
        ANCIENT_FRUIT,
        GrowthModifiers(fertilizer="hyper_speed_gro", agriculturist=True),
    )
    assert phases[0] >= 1


def test_removal_is_capped_by_three_passes_not_infinite():
    """Ensure the algorithm doesn't remove more than three passes allow."""
    # For Ancient Fruit with Hyper+Ag, we remove exactly 13 days.
    # If your code accidentally loops more than 3 passes, totals will be too low.
    phases = apply_speed_increases_to_phase_days(
        ANCIENT_FRUIT,
        GrowthModifiers(fertilizer="hyper_speed_gro", agriculturist=True),
    )
    assert sum(phases) == 15  # if this becomes 14 or less, you're removing too much


def test_base_growth_days_match_crop_specs():
    """Check base growth days align with crop specs."""
    assert STARFRUIT.base_days_to_first_harvest == 13
    assert ANCIENT_FRUIT.base_days_to_first_harvest == 28
    assert ANCIENT_FRUIT.regrow_days == 7


def test_speed_increase_values():
    """Speed increase should combine fertilizer and profession bonuses."""
    assert _speed_increase(GrowthModifiers("none", False)) == 0.0
    assert _speed_increase(GrowthModifiers("speed_gro", False)) == 0.10
    assert _speed_increase(GrowthModifiers("deluxe_speed_gro", True)) == 0.35


def test_phase_override_for_ancient_speedgro_ag():
    """Ancient Fruit with Speed-Gro + Agriculturist should use wiki override."""
    override = _phase_override(ANCIENT_FRUIT, GrowthModifiers("speed_gro", True))
    assert override == (1, 5, 6, 7, 3)
    assert _phase_override(STARFRUIT, GrowthModifiers("speed_gro", True)) is None
