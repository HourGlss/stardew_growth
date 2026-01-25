from sim.bees import BeeConfig, FlowerPlan, FlowerSpec, simulate_bees


def test_bee_house_honey_output():
    """Bee houses should produce honey every 4 days in active seasons."""
    config = BeeConfig(bee_houses=1, seasons=("spring", "summer", "fall"))
    result = simulate_bees(config)
    assert result.honey_total == 21  # 84 active days / 4


def test_bee_house_flower_plan_switching():
    """Honey should switch from fast to expensive flower once available."""
    plan = FlowerPlan(
        fast=FlowerSpec(name="Sunflower", growth_days=8, base_price=80),
        expensive=FlowerSpec(name="Fairy Rose", growth_days=12, base_price=290),
    )
    config = BeeConfig(bee_houses=1, seasons=("fall",), flower_plan={"fall": plan})
    result = simulate_bees(config)
    # Honey on days 4, 8, 12, 16, 20, 24, 28.
    # Fast flower ready day 9, expensive day 13.
    assert result.honey_by_flower_price[0] == 2  # days 4,8 -> wild honey
    assert result.honey_by_flower_price[80] == 1  # day 12 -> sunflower honey
    assert result.honey_by_flower_price[290] == 4  # days 16,20,24,28 -> fairy rose
