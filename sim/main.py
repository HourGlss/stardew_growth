from __future__ import annotations

import sys
from sim.save_loader import load_config
from sim.crops import STARFRUIT, ANCIENT_FRUIT
from sim.animals import simulate_animals
from sim.bees import simulate_bees
from sim.growth import GrowthModifiers
from sim.pipeline import simulate_year_multi_crop
from sim.plots import Plot, PlotCalendar
from sim.economy import compute_animal_profit, compute_honey_profit, compute_profit, per_fruit_processing_values, wine_price_for_crop
from sim.fruit_trees import build_daily_fruit, summarize_tree_counts, total_tree_counts, tree_ids_from_config


def main() -> int:
    """Run the CLI simulation from a JSON config path."""
    if len(sys.argv) not in (2, 3):
        print("Usage: python -m sim.main path/to/config.json")
        print("   or: python -m sim.main path/to/save.xml [overrides.json]")
        return 2

    config_path = sys.argv[1]
    overrides_path = sys.argv[2] if len(sys.argv) == 3 else None
    cfg = load_config(config_path, overrides_path)
    mods = GrowthModifiers(
        fertilizer=cfg.growth.fertilizer,
        agriculturist=cfg.professions.farming.agriculturist,
        paddy_bonus=cfg.growth.paddy_bonus,
    )

    crops = []
    if cfg.crop in ("starfruit", "both"):
        crops.append(STARFRUIT)
    if cfg.crop in ("ancient", "both"):
        crops.append(ANCIENT_FRUIT)

    start_day_of_year = 1
    if cfg.simulation.start_day_of_year != 1:
        print("note: start_day_of_year overridden to 1 (spring 1)")

    plots = list(cfg.plots)
    if not plots:
        plots = [Plot(name="plot", tiles_by_crop={"all": cfg.tiles}, calendar=PlotCalendar(type="always"))]

    print(
        f"tiles={cfg.tiles} kegs={cfg.kegs} casks={cfg.casks} preserves_jars={cfg.preserves_jars} "
        f"dehydrators={cfg.dehydrators} oil_makers={cfg.oil_makers} mayo_machines={cfg.mayo_machines} "
        f"cheese_presses={cfg.cheese_presses} looms={cfg.looms} fertilizer={mods.fertilizer} "
        f"agriculturist={mods.agriculturist}"
    )
    print(f"year_days={cfg.simulation.max_days} start_day_of_year={start_day_of_year} (year-round assumed={cfg.simulation.assume_year_round})")
    print("cask priority: starfruit -> ancient (two batch fills per year)\n")

    if cfg.starting_inventory.fruit or cfg.starting_inventory.base_wine:
        fruit_summary = ", ".join(f"{k}={v}" for k, v in cfg.starting_inventory.fruit.items())
        wine_summary = ", ".join(f"{k}={v}" for k, v in cfg.starting_inventory.base_wine.items())
        print(f"starting fruit: {fruit_summary or 'none'}")
        print(f"starting base wine: {wine_summary or 'none'}\n")

    fruit_tree_daily = build_daily_fruit(
        cfg.fruit_trees,
        start_day_of_year=start_day_of_year,
        max_days=cfg.simulation.max_days,
    )
    fruit_tree_ids = tree_ids_from_config(cfg.fruit_trees)
    fruit_tree_ids_sorted = sorted(
        fruit_tree_ids,
        key=lambda fruit_id: wine_price_for_crop(fruit_id, cfg.economy),
        reverse=True,
    )

    result = simulate_year_multi_crop(
        crops=crops,
        mods=mods,
        plots=plots,
        kegs=cfg.kegs,
        casks=cfg.casks,
        max_days=cfg.simulation.max_days,
        start_day_of_year=start_day_of_year,
        starting_fruit=cfg.starting_inventory.fruit,
        starting_base_wine=cfg.starting_inventory.base_wine,
        cask_full_batch_required=cfg.economy.cask_full_batch_required,
        casks_with_walkways=cfg.economy.casks_with_walkways,
        preserves_jars=cfg.preserves_jars,
        dehydrators=cfg.dehydrators,
        external_daily_fruit=fruit_tree_daily,
        external_priority=fruit_tree_ids_sorted,
    )
    crop_profit = compute_profit(result.per_crop, cfg.economy, cfg.growth.fertilizer)
    animal_result = simulate_animals(
        cfg.animals,
        cfg.simulation.max_days,
        oil_makers=cfg.oil_makers,
        mayo_machines=cfg.mayo_machines,
        cheese_presses=cfg.cheese_presses,
        looms=cfg.looms,
        gatherer=cfg.professions.foraging.gatherer,
        shepherd=cfg.professions.farming.shepherd,
    )
    animal_profit = compute_animal_profit(
        animal_result,
        cfg.economy,
        botanist=cfg.professions.foraging.botanist,
        rancher=cfg.professions.farming.rancher,
    )
    honey_result = simulate_bees(cfg.bees)
    honey_profit = compute_honey_profit(honey_result, cfg.economy, cfg.bees.flower_base_price)
    total_revenue = crop_profit.total_revenue + animal_profit.total_revenue + honey_profit.total_revenue
    total_profit = crop_profit.total_profit + animal_profit.total_revenue + honey_profit.total_revenue

    for crop in crops:
        r = result.per_crop[crop.crop_id]
        p = crop_profit.per_crop[crop.crop_id]
        print(f"{crop.crop_id}:")
        print(f"  fruit harvested (year): {r.fruit_harvested}")
        print(f"  base wine produced (year): {r.base_wine_produced}")
        print(f"  aged wine produced (year): {r.aged_wine_produced}")
        print(f"  base wine sold (year): {r.base_wine_sold}")
        print(f"  unprocessed fruit (year end): {r.fruit_unprocessed}")
        print(f"  wine in kegs (year end): {r.wine_in_kegs_end}")
        print(f"  jelly produced (year): {r.jelly_produced}")
        print(f"  dried fruit produced (year): {r.dried_fruit_produced}")
        print(f"  jelly in jars (year end): {r.jelly_in_jars_end}")
        print(f"  dried fruit in dehydrators (year end): {r.dried_fruit_in_dehydrators_end}")
        print(f"  seed units used: {r.seed_units_used}")
        print(f"  fertilizer units used: {r.fertilizer_units_used}")
        print(f"  fruit revenue: {p.fruit_revenue}")
        print(f"  base wine revenue: {p.base_wine_revenue}")
        print(f"  aged wine revenue: {p.aged_wine_revenue}")
        print(f"  jelly revenue: {p.jelly_revenue}")
        print(f"  dried fruit revenue: {p.dried_fruit_revenue}")
        print(f"  seed cost: {p.seed_cost}")
        print(f"  fertilizer cost: {p.fertilizer_cost}")
        print(f"  net profit: {p.net_profit}\n")

    if cfg.animals.coops or cfg.animals.barns:
        print("animals:")
        print(f"  cheese revenue: {animal_profit.cheese_revenue}")
        print(f"  mayo revenue: {animal_profit.mayo_revenue}")
        print(f"  cloth revenue: {animal_profit.cloth_revenue}")
        print(f"  truffle oil revenue: {animal_profit.truffle_oil_revenue}")
        print(f"  raw truffles revenue: {animal_profit.raw_truffle_revenue}")
        print(f"  raw animal products revenue: {animal_profit.raw_animal_revenue}\n")

    if cfg.bees.bee_houses > 0:
        print("bees:")
        print(f"  honey revenue: {honey_profit.honey_revenue}\n")

    tree_totals = total_tree_counts(cfg.fruit_trees)
    if tree_totals:
        print("fruit trees:")
        tree_scopes = summarize_tree_counts(cfg.fruit_trees)
        for scope, counts in tree_scopes.items():
            if not counts:
                continue
            summary = ", ".join(f"{fruit}={count}" for fruit, count in counts.items())
            print(f"  {scope}: {summary}")
        print("  per-fruit best use (per fruit, using current prices):")
        for fruit_id, count in sorted(tree_totals.items()):
            fruit_price = cfg.economy.fruit_price.get(fruit_id, 0)
            wine_price = wine_price_for_crop(fruit_id, cfg.economy)
            values = per_fruit_processing_values(fruit_price, wine_price, cfg.economy)
            order = sorted(values.items(), key=lambda item: item[1], reverse=True)
            best = order[0][0]
            next_best = order[1][0] if len(order) > 1 else "raw"
            print(
                f"    {fruit_id} ({count} trees): best={best} ({values[best]}), "
                f"next={next_best} ({values[next_best]}), raw={values['raw']}"
            )
        print()

    print(f"kegs sufficient for full conversion: {result.kegs_sufficient}")
    if cfg.economy.cask_full_batch_required:
        print(f"full cask batch met (need {cfg.casks} on each batch day): {result.full_cask_batch_met}")
        if not result.full_cask_batch_met and cfg.economy.casks_with_walkways is None:
            print("note: set economy.casks_with_walkways to model walkway losses")
    print(f"casks used for aging: {result.casks_effective}")
    print(f"cask uses per cask (max 2.00): {result.cask_uses_per_cask:.2f}")
    print(f"total base wine sold: {result.total_base_wine_sold}")
    print(f"total aged wine produced: {result.total_aged_wine}")
    print(f"total jelly produced: {result.total_jelly}")
    print(f"total dried fruit produced: {result.total_dried_fruit}")
    print(f"total fruit unprocessed (year end): {result.total_fruit_unprocessed}")
    print(f"total wine in kegs (year end): {result.total_wine_in_kegs_end}")
    print(f"total jelly in jars (year end): {result.total_jelly_in_jars_end}")
    print(f"total dried fruit in dehydrators (year end): {result.total_dried_fruit_in_dehydrators_end}")
    print(f"total revenue (year): {total_revenue}")
    print(f"total seed cost (year): {crop_profit.total_seed_cost}")
    print(f"total fertilizer cost (year): {crop_profit.total_fertilizer_cost}")
    print(f"TOTAL PROFIT (year): {total_profit}")

    tips = []
    if not result.kegs_sufficient:
        tips.append("Kegs are a bottleneck (fruit or wine left unprocessed). Add kegs or reduce tiles.")
    if result.cask_uses_per_cask < 2.0:
        tips.append("Casks are underused. Stockpile base wine for Spring 1/Fall 1 or lower cask count.")
    if result.total_jelly_in_jars_end > 0:
        tips.append("Preserves jars are still running at year end. Add jars or reduce jar input.")
    if result.total_dried_fruit_in_dehydrators_end > 0:
        tips.append("Dehydrators are still running at year end. Add dehydrators or reduce dehydrator input.")
    if animal_profit.raw_animal_revenue > 0:
        tips.append("Raw animal products sold. Add mayo machines/cheese presses/looms to increase value.")
    if animal_result.raw_truffles > 0 and cfg.oil_makers > 0:
        tips.append("Truffles exceeded oil maker capacity. Add oil makers if you prefer truffle oil.")
    if cfg.bees.bee_houses > 0 and not cfg.bees.flower_plan and cfg.bees.flower_base_price <= 0:
        tips.append("Bee houses set to wild honey. Plant flowers or set a flower_plan for higher honey value.")

    if tips:
        print("\nquick wins:")
        for tip in tips:
            print(f"  - {tip}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
