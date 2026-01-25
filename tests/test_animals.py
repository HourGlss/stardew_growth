from sim.animals import AnimalsConfig, BarnConfig, CoopConfig, simulate_animals


def test_animal_production_counts():
    """Animal production counts should match daily/every-other-day rates."""
    config = AnimalsConfig(
        coops=[CoopConfig(name="coop", chickens=2, ducks=2)],
        barns=[BarnConfig(name="barn", cows=1, goats=1)],
        large_egg_rate=0.0,
        large_milk_rate=0.0,
        large_goat_milk_rate=0.0,
    )
    result = simulate_animals(config, days=112)
    assert result.eggs == 224  # 2 chickens * 112 days
    assert result.duck_eggs == 112  # 2 ducks * 56 days
    assert result.milk == 112  # 1 cow * 112 days
    assert result.goat_milk == 56  # 1 goat * 56 days
    assert result.mayo == 0  # no mayo machines


def test_large_product_rates():
    """Large product rates should split totals deterministically."""
    config = AnimalsConfig(
        coops=[CoopConfig(name="coop", chickens=1, ducks=0)],
        barns=[BarnConfig(name="barn", cows=1, goats=1)],
        large_egg_rate=1.0,
        large_milk_rate=0.5,
        large_goat_milk_rate=1.0,
    )
    result = simulate_animals(config, days=10)
    assert result.large_eggs == 10
    assert result.eggs == 0
    assert result.large_milk == 5
    assert result.milk == 5
    assert result.large_goat_milk == 5
    assert result.goat_milk == 0


def test_pig_truffles_and_oil_makers():
    """Pig truffles should only appear on non-winter days and use oil maker capacity."""
    config = AnimalsConfig(
        barns=[BarnConfig(name="barn", pigs=2)],
    )
    result = simulate_animals(config, days=112, oil_makers=1, gatherer=False)
    assert result.truffles == 168  # 2 pigs * 84 non-winter days
    assert result.truffle_oil == 112  # 1 oil maker * 112 days
    assert result.raw_truffles == 56


def test_pig_truffles_with_gatherer_bonus():
    """Gatherer should increase expected truffle yield by 20% (floored)."""
    config = AnimalsConfig(
        barns=[BarnConfig(name="barn", pigs=2)],
    )
    result = simulate_animals(config, days=112, oil_makers=0, gatherer=True)
    assert result.truffles == 201  # 168 + floor(168 * 0.2)


def test_mayo_machine_capacity_limits_processing():
    """Mayo machines should cap processed eggs based on machine-days."""
    config = AnimalsConfig(
        coops=[CoopConfig(name="coop", chickens=2)],
    )
    result = simulate_animals(config, days=10, mayo_machines=1)
    assert result.eggs == 20
    assert result.mayo == 10  # 1 machine * 10 days


def test_rabbit_and_sheep_wool_rates():
    """Rabbits and sheep should produce wool on their cadence, with rabbit feet split."""
    config = AnimalsConfig(
        coops=[CoopConfig(name="coop", rabbits=1)],
        barns=[BarnConfig(name="barn", sheep=1)],
        rabbit_foot_rate=0.5,
    )
    result = simulate_animals(config, days=8, looms=0, shepherd=False)
    assert result.rabbit_feet == 1  # 2 rabbit products * 0.5
    assert result.wool == 3  # 1 rabbit wool + 2 sheep wool


def test_shepherd_makes_sheep_daily():
    """Shepherd should make sheep produce wool daily."""
    config = AnimalsConfig(barns=[BarnConfig(name="barn", sheep=1)])
    result = simulate_animals(config, days=4, shepherd=True)
    assert result.wool == 4
