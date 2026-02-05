from __future__ import annotations

import sys
import json
from copy import deepcopy
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable
import xml.etree.ElementTree as ET
import re

import matplotlib.pyplot as plt
from matplotlib import cm, colors, colormaps
import numpy as np

from sim.save_loader import load_config, is_save_file, sprinkler_tiles_from_save
from sim.animals import simulate_animals
from sim.bees import simulate_bees
from sim.crops import ANCIENT_FRUIT, STARFRUIT
from sim.economy import build_category_totals, compute_animal_profit, compute_honey_profit, compute_profit, wine_price_for_crop
from sim.growth import GrowthModifiers
from sim.pipeline import simulate_year_multi_crop
from sim.plots import Plot, PlotCalendar
from sim.config import AppConfig, FarmingProfessions, ForagingProfessions
from sim.fruit_trees import build_daily_fruit, tree_ids_from_config


def _iter_range(start: int, end: int, step: int) -> list[int]:
    """Return an inclusive integer range with a positive step."""
    if step <= 0:
        raise ValueError("step must be > 0")
    return list(range(start, end + 1, step))


def _range_from_base(base: int, step: int, min_value: int, extra: int, min_end: int) -> list[int]:
    """Build a range that includes base and extends upward by extra."""
    start = max(min_value, base - (step * 2))
    end = max(base + extra, min_end)
    return _iter_range(start, end, step)


@dataclass(frozen=True)
class GraphLimits:
    max_total_kegs: int | None = None
    max_total_casks: int | None = None
    max_total_jars: int | None = None
    max_total_dehydrators: int | None = None
    max_total_bee_houses: int | None = None
    max_outdoor_tiles: int | None = None


def _limit_from_raw(raw: dict, base: int, total_key: str, new_key: str) -> int | None:
    if total_key in raw:
        return int(raw[total_key])
    if new_key in raw:
        return int(base + int(raw[new_key]))
    return None


def _parse_graph_limits(raw: dict, cfg: AppConfig) -> GraphLimits:
    return GraphLimits(
        max_total_kegs=_limit_from_raw(raw, cfg.kegs, "max_total_kegs", "max_new_kegs"),
        max_total_casks=_limit_from_raw(raw, cfg.casks, "max_total_casks", "max_new_casks"),
        max_total_jars=_limit_from_raw(raw, cfg.preserves_jars, "max_total_jars", "max_new_jars"),
        max_total_dehydrators=_limit_from_raw(raw, cfg.dehydrators, "max_total_dehydrators", "max_new_dehydrators"),
        max_total_bee_houses=_limit_from_raw(raw, cfg.bees.bee_houses, "max_total_bee_houses", "max_new_bee_houses"),
        max_outdoor_tiles=_limit_from_raw(raw, 0, "max_outdoor_tiles", "max_new_outdoor_tiles"),
    )


def _merge_limits(base: GraphLimits, override: GraphLimits) -> GraphLimits:
    return GraphLimits(
        max_total_kegs=override.max_total_kegs if override.max_total_kegs is not None else base.max_total_kegs,
        max_total_casks=override.max_total_casks if override.max_total_casks is not None else base.max_total_casks,
        max_total_jars=override.max_total_jars if override.max_total_jars is not None else base.max_total_jars,
        max_total_dehydrators=(
            override.max_total_dehydrators if override.max_total_dehydrators is not None else base.max_total_dehydrators
        ),
        max_total_bee_houses=(
            override.max_total_bee_houses if override.max_total_bee_houses is not None else base.max_total_bee_houses
        ),
        max_outdoor_tiles=override.max_outdoor_tiles if override.max_outdoor_tiles is not None else base.max_outdoor_tiles,
    )


def _apply_limit(values: list[int], base: int, max_total: int | None) -> list[int]:
    if max_total is None:
        return values
    limit = max(int(max_total), int(base))
    limited = [value for value in values if value <= limit]
    if base not in limited:
        limited.append(int(base))
    limited = sorted(set(limited))
    return limited or [int(base)]


def _extract_numeric_id(raw: str | None) -> str | None:
    if not raw:
        return None
    match = re.search(r"(\d+)", raw)
    if not match:
        return None
    return match.group(1)


def _iter_locations(root: ET.Element) -> list[tuple[str, ET.Element]]:
    locations: list[tuple[str, ET.Element]] = []
    for loc in root.findall("locations/GameLocation"):
        name = loc.findtext("name") or "(unknown)"
        locations.append((name, loc))
    farm = root.find("locations/GameLocation[name='Farm']")
    if farm is None:
        return locations
    buildings = farm.find("buildings")
    if buildings is None:
        return locations
    for b in buildings:
        indoors = b.find("indoors")
        if indoors is None:
            continue
        in_name = indoors.findtext("name") or b.findtext("buildingType") or "(indoor)"
        locations.append((in_name, indoors))
    return locations


def _iter_items(root: ET.Element) -> Iterable[ET.Element]:
    player = root.find("player")
    if player is not None:
        items = player.find("items")
        if items is not None:
            for item in items.findall("Item"):
                if item.attrib.get("{http://www.w3.org/2001/XMLSchema-instance}nil") == "true":
                    continue
                yield item
    for _, loc in _iter_locations(root):
        objects = loc.find("objects")
        if objects is None:
            continue
        for item in objects.findall("item"):
            value = item.find("value")
            if value is None:
                continue
            obj = value.find("Object")
            if obj is None:
                continue
            items_node = obj.find("items")
            if items_node is None:
                continue
            for child in items_node.findall("Item"):
                if child.attrib.get("{http://www.w3.org/2001/XMLSchema-instance}nil") == "true":
                    continue
                item_node = child.find("Object") or child
                yield item_node


def _count_inventory_item(root: ET.Element, item_id: str) -> int:
    total = 0
    for item in _iter_items(root):
        raw_id = item.findtext("itemId") or item.findtext("parentSheetIndex")
        numeric = _extract_numeric_id(raw_id)
        if numeric != item_id:
            continue
        try:
            stack = int(item.findtext("stack") or 1)
        except ValueError:
            stack = 1
        total += max(0, stack)
    return total


def _load_tree_tap_days() -> dict[str, tuple[str, int]]:
    path = Path(__file__).resolve().parents[1] / "data" / "WildTrees.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    tap_info: dict[str, tuple[str, int]] = {}
    for tree_id, entry in raw.items():
        tap_items = entry.get("TapItems") or []
        for tap in tap_items:
            item_id = _extract_numeric_id(tap.get("ItemId") or tap.get("Id"))
            days = tap.get("DaysUntilReady")
            if item_id and days:
                tap_info[str(tree_id)] = (item_id, int(days))
                break
    return tap_info


def _estimate_graph_limits_from_save(save_path: str, cfg: AppConfig) -> GraphLimits:
    try:
        root = ET.fromstring(Path(save_path).read_text(encoding="utf-8"))
    except Exception:
        return GraphLimits()

    tap_info = _load_tree_tap_days()
    trees: dict[tuple[str, int, int], str] = {}
    for loc_name, loc in _iter_locations(root):
        terrain = loc.find("terrainFeatures")
        if terrain is None:
            continue
        for item in terrain.findall("item"):
            key = item.find("key/Vector2")
            if key is None:
                continue
            x_text = key.findtext("X")
            y_text = key.findtext("Y")
            if x_text is None or y_text is None:
                continue
            x = int(float(x_text))
            y = int(float(y_text))
            tf = item.find("value/TerrainFeature")
            if tf is None:
                continue
            tf_type = tf.attrib.get("{http://www.w3.org/2001/XMLSchema-instance}type")
            if tf_type != "Tree":
                continue
            tree_type = tf.findtext("treeType")
            if tree_type is None:
                continue
            trees[(loc_name, x, y)] = tree_type

    oak_tappers = 0
    oak_tap_days = None
    for loc_name, loc in _iter_locations(root):
        objects = loc.find("objects")
        if objects is None:
            continue
        for item in objects.findall("item"):
            key = item.find("key/Vector2")
            obj = item.find("value/Object")
            if key is None or obj is None:
                continue
            name = (obj.findtext("name") or "").strip()
            if name not in ("Tapper", "Heavy Tapper"):
                continue
            x_text = key.findtext("X")
            y_text = key.findtext("Y")
            if x_text is None or y_text is None:
                continue
            x = int(float(x_text))
            y = int(float(y_text))
            tree_type = trees.get((loc_name, x, y))
            if not tree_type:
                continue
            tap_item, tap_days = tap_info.get(str(tree_type), (None, None))
            if tap_item != "725":
                continue
            oak_tappers += 1
            oak_tap_days = tap_days

    resin_inventory = _count_inventory_item(root, "725")
    hardwood_inventory = _count_inventory_item(root, "709")
    resin_production = 0
    if oak_tappers > 0 and oak_tap_days and oak_tap_days > 0:
        resin_production = oak_tappers * (cfg.simulation.max_days // oak_tap_days)

    max_kegs = cfg.kegs + resin_inventory + resin_production
    max_casks = cfg.casks + hardwood_inventory

    return GraphLimits(
        max_total_kegs=max_kegs,
        max_total_casks=max_casks,
    )


def _load_graph_limits(
    config_path: str,
    overrides_path: str | None,
    cfg: AppConfig,
) -> GraphLimits | None:
    override_limits = None
    if overrides_path is not None:
        raw = json.loads(Path(overrides_path).read_text(encoding="utf-8"))
        limits_raw = raw.get("graph_limits")
        if isinstance(limits_raw, dict):
            if limits_raw.get("enabled", True) is False:
                return None
            override_limits = _parse_graph_limits(limits_raw, cfg)

    if is_save_file(config_path):
        base_limits = _estimate_graph_limits_from_save(config_path, cfg)
    else:
        base_limits = GraphLimits()

    if override_limits is not None:
        return _merge_limits(base_limits, override_limits)
    if any(value is not None for value in base_limits.__dict__.values()):
        return base_limits
    return None


def _parse_args(argv: list[str]) -> tuple[str, str | None, str, int]:
    """Parse CLI args into (config_path, overrides_path, output_path, target_profit)."""
    target_profit = 10_000_000
    args: list[str] = []
    idx = 1
    while idx < len(argv):
        arg = argv[idx]
        if arg == "--target":
            if idx + 1 >= len(argv):
                raise ValueError("missing value for --target")
            target_profit = int(argv[idx + 1].replace(",", ""))
            idx += 2
            continue
        if arg.startswith("--target="):
            target_profit = int(arg.split("=", 1)[1].replace(",", ""))
            idx += 1
            continue
        args.append(arg)
        idx += 1

    if not args:
        raise ValueError("missing config path")

    config_path = args[0]
    overrides_path = None
    output_path = ""
    if is_save_file(config_path):
        if len(args) >= 2 and args[1].lower().endswith(".json"):
            overrides_path = args[1]
            output_path = args[2] if len(args) > 2 else ""
        else:
            output_path = args[1] if len(args) > 1 else ""
    else:
        output_path = args[1] if len(args) > 1 else ""
    return config_path, overrides_path, output_path, target_profit


class _Progress:
    """Minimal progress indicator for long-running grid simulations."""

    def __init__(self, total: int) -> None:
        self.total = max(0, int(total))
        self.current = 0
        self.last_percent = -1

    def update(self, step: int = 1) -> None:
        if self.total <= 0:
            return
        self.current += step
        percent = int((self.current / self.total) * 100)
        if percent == self.last_percent:
            return
        if percent >= 100 or percent % 2 == 0:
            print(f"\rprogress: {percent}% ({self.current}/{self.total})", end="", flush=True)
            self.last_percent = percent
        if self.current >= self.total:
            print()


def _grid_max(z_grid: np.ndarray, x_vals: list[int], y_vals: list[int]) -> tuple[int, int, int]:
    """Return max z and its x/y coordinates."""
    idx = np.unravel_index(int(np.argmax(z_grid)), z_grid.shape)
    y_idx, x_idx = int(idx[0]), int(idx[1])
    return int(z_grid[y_idx, x_idx]), int(x_vals[x_idx]), int(y_vals[y_idx])


def _solutions_for_target(
    x_vals: list[int],
    y_vals: list[int],
    z_grid: np.ndarray,
    target: int,
) -> list[tuple[int, int, int]]:
    """Return all (x,y,z) combos meeting target."""
    solutions: list[tuple[int, int, int]] = []
    for yi, y in enumerate(y_vals):
        for xi, x in enumerate(x_vals):
            z_val = int(z_grid[yi, xi])
            if z_val >= target:
                solutions.append((int(x), int(y), z_val))
    return solutions


def _pareto_minimal(solutions: list[tuple[int, int, int]]) -> list[tuple[int, int, int]]:
    """Return non-dominated solutions (minimize x,y while meeting target)."""
    best: dict[tuple[int, int], int] = {}
    for x, y, z in solutions:
        key = (x, y)
        if key not in best or z > best[key]:
            best[key] = z
    unique = [(x, y, z) for (x, y), z in best.items()]
    unique.sort(key=lambda item: (item[0], item[1], -item[2]))
    pareto: list[tuple[int, int, int]] = []
    for x, y, z in unique:
        dominated = False
        for ox, oy, _ in pareto:
            if (ox <= x and oy <= y) and (ox < x or oy < y):
                dominated = True
                break
        if not dominated:
            pareto.append((x, y, z))
    return pareto


def _outdoor_plots(plots: Iterable[Plot]) -> list[Plot]:
    """Return plots whose name contains 'outdoor' (case-insensitive)."""
    out: list[Plot] = []
    for plot in plots:
        if "outdoor" in plot.name.strip().lower():
            out.append(plot)
    return out


def _scale_tiles(tiles_by_crop: dict[str, int], scale: float) -> dict[str, int]:
    """Scale a tiles map by a factor, rounding to integers."""
    return {crop_id: max(0, int(round(count * scale))) for crop_id, count in tiles_by_crop.items()}


def _clone_plots_with_outdoor_total(
    plots: list[Plot],
    outdoor_plots: set[str],
    outdoor_total: int,
    outdoor_base_total: int,
) -> list[Plot]:
    """Clone plots, scaling outdoor plots to match a new total tile count."""
    updated: list[Plot] = []
    scale = 0.0 if outdoor_base_total <= 0 else outdoor_total / outdoor_base_total
    for plot in plots:
        name_key = plot.name.strip().lower()
        if name_key in outdoor_plots:
            tiles_by_crop = _scale_tiles(deepcopy(plot.tiles_by_crop), scale)
            updated.append(Plot(name=plot.name, tiles_by_crop=tiles_by_crop, calendar=plot.calendar))
        else:
            updated.append(plot)
    return updated


def _replace_outdoors_with_single_crop(
    plots: list[Plot],
    outdoor_plots: set[str],
    outdoor_total: int,
    crop_id: str,
    seasons: list[str],
) -> list[Plot]:
    """Replace outdoor plots with a single-crop outdoor plot."""
    updated: list[Plot] = []
    for plot in plots:
        if plot.name.strip().lower() not in outdoor_plots:
            updated.append(plot)
    updated.append(
        Plot(
            name=f"outdoors_{crop_id}",
            tiles_by_crop={crop_id: max(0, int(outdoor_total))},
            calendar=PlotCalendar(type="seasons", seasons=seasons),
        )
    )
    return updated


def _add_sprinkler_outdoor_plots(
    cfg: AppConfig,
    plots: list[Plot],
    outdoor_tiles: int,
) -> list[Plot]:
    """Create outdoor plots from sprinkler-derived tile capacity."""
    if outdoor_tiles <= 0:
        return plots
    updated = list(plots)
    if cfg.crop == "starfruit":
        updated.append(
            Plot(
                name="outdoors_starfruit",
                tiles_by_crop={"starfruit": outdoor_tiles},
                calendar=PlotCalendar(type="seasons", seasons=["summer"]),
            )
        )
    elif cfg.crop == "ancient":
        updated.append(
            Plot(
                name="outdoors_ancient",
                tiles_by_crop={"ancient": outdoor_tiles},
                calendar=PlotCalendar(type="seasons", seasons=["spring", "summer", "fall"]),
            )
        )
    else:
        star_tiles = outdoor_tiles // 2
        ancient_tiles = outdoor_tiles - star_tiles
        if star_tiles > 0:
            updated.append(
                Plot(
                    name="outdoors_starfruit",
                    tiles_by_crop={"starfruit": star_tiles},
                    calendar=PlotCalendar(type="seasons", seasons=["summer"]),
                )
            )
        if ancient_tiles > 0:
            updated.append(
                Plot(
                    name="outdoors_ancient",
                    tiles_by_crop={"ancient": ancient_tiles},
                    calendar=PlotCalendar(type="seasons", seasons=["spring", "summer", "fall"]),
                )
            )
    return updated


def _select_crops(cfg: AppConfig):
    """Return crop specs based on config selection."""
    crops = []
    if cfg.crop in ("starfruit", "both"):
        crops.append(STARFRUIT)
    if cfg.crop in ("ancient", "both"):
        crops.append(ANCIENT_FRUIT)
    return crops


def _apply_professions(
    cfg: AppConfig,
    farming: FarmingProfessions,
    foraging: ForagingProfessions,
) -> AppConfig:
    """Return a config with updated professions and derived economy/growth flags."""
    professions = replace(cfg.professions, farming=farming, foraging=foraging)
    growth = replace(cfg.growth, agriculturist=farming.agriculturist)
    economy = replace(cfg.economy, artisan=farming.artisan, tiller=farming.tiller)
    return replace(cfg, professions=professions, growth=growth, economy=economy)


def _cfg_with_counts(
    cfg: AppConfig,
    kegs: int | None = None,
    preserves_jars: int | None = None,
    dehydrators: int | None = None,
    bee_houses: int | None = None,
) -> AppConfig:
    """Return a config with updated machine counts."""
    updated = replace(
        cfg,
        kegs=int(kegs if kegs is not None else cfg.kegs),
        preserves_jars=int(preserves_jars if preserves_jars is not None else cfg.preserves_jars),
        dehydrators=int(dehydrators if dehydrators is not None else cfg.dehydrators),
    )
    if bee_houses is not None:
        updated = replace(updated, bees=replace(updated.bees, bee_houses=int(bee_houses)))
    return updated


def _compute_total_profit(
    cfg: AppConfig,
    plots: list[Plot],
    fruit_tree_daily: dict[str, list[int]] | None = None,
    fruit_tree_priority: list[str] | None = None,
) -> int:
    """Run the sim and return total profit for a config."""
    if fruit_tree_daily is None:
        fruit_tree_daily = build_daily_fruit(
            cfg.fruit_trees,
            start_day_of_year=1,
            max_days=cfg.simulation.max_days,
        )
    if fruit_tree_priority is None:
        fruit_tree_ids = tree_ids_from_config(cfg.fruit_trees)
        fruit_tree_priority = sorted(
            fruit_tree_ids,
            key=lambda fruit_id: wine_price_for_crop(fruit_id, cfg.economy),
            reverse=True,
        )
    mods = GrowthModifiers(
        fertilizer=cfg.growth.fertilizer,
        agriculturist=cfg.professions.farming.agriculturist,
        paddy_bonus=cfg.growth.paddy_bonus,
    )
    crops = _select_crops(cfg)
    result = simulate_year_multi_crop(
        crops=crops,
        mods=mods,
        plots=plots,
        kegs=cfg.kegs,
        casks=cfg.casks,
        max_days=cfg.simulation.max_days,
        start_day_of_year=1,
        starting_fruit=cfg.starting_inventory.fruit,
        starting_base_wine=cfg.starting_inventory.base_wine,
        cask_full_batch_required=cfg.economy.cask_full_batch_required,
        casks_with_walkways=cfg.economy.casks_with_walkways,
        preserves_jars=cfg.preserves_jars,
        dehydrators=cfg.dehydrators,
        external_daily_fruit=fruit_tree_daily,
        external_priority=fruit_tree_priority,
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
    return crop_profit.total_profit + animal_profit.total_revenue + honey_profit.total_revenue


def _suggest_min_expansion(
    name: str,
    x_vals: list[int],
    y_vals: list[int],
    z_grid: np.ndarray,
    base_x: int,
    base_y: int,
    target: int,
) -> str:
    """Find the smallest x/y increase that reaches the target."""
    best = None
    for yi, y in enumerate(y_vals):
        if y < base_y:
            continue
        for xi, x in enumerate(x_vals):
            if x < base_x:
                continue
            if z_grid[yi, xi] < target:
                continue
            delta = (x - base_x) + (y - base_y)
            if best is None or delta < best[0]:
                best = (delta, x, y, int(z_grid[yi, xi]))
    if best is None:
        return f"{name}: no combination in range hits {target:,}"
    _, x, y, profit = best
    return f"{name}: k={x} y={y} profit={profit:,} (delta k={x - base_x}, delta y={y - base_y})"


def _plot_surface(ax, x_grid, y_grid, z_grid, norm, cmap, target_profit: int) -> None:
    """Plot a single 3D surface with a shared color scale."""
    facecolors = cmap(norm(z_grid))
    ax.plot_surface(
        x_grid,
        y_grid,
        z_grid,
        facecolors=facecolors,
        rstride=1,
        cstride=1,
        linewidth=0,
        antialiased=True,
        shade=False,
        alpha=0.95,
    )
    if norm.vmin <= target_profit <= norm.vmax:
        ax.contour(
            x_grid,
            y_grid,
            z_grid,
            levels=[target_profit],
            zdir="z",
            offset=norm.vmin,
            colors="white",
            linewidths=1.5,
        )
    ax.view_init(elev=28, azim=235)


def _annotate_max(ax, x_vals: list[int], y_vals: list[int], z_grid: np.ndarray, fontsize: int = 8) -> None:
    """Annotate max x/y/z on a subplot."""
    z_max, x_max, y_max = _grid_max(z_grid, x_vals, y_vals)
    ax.text2D(
        0.03,
        0.95,
        f"max x={x_max}\nmax y={y_max}\nmax z={z_max:,}",
        transform=ax.transAxes,
        va="top",
        ha="left",
        fontsize=fontsize,
        bbox={"boxstyle": "round", "facecolor": "white", "alpha": 0.85},
    )


def main() -> int:
    """Run a series of 3D profit graphs for keg count and outdoor tiles."""
    if len(sys.argv) < 2:
        print("Usage: python -m sim.graph_app path/to/config.json [output.png]")
        print("   or: python -m sim.graph_app path/to/save.xml [overrides.json] [output.png]")
        print("Optional: --target 10000000")
        return 2
    try:
        config_path, overrides_path, output_path, target_profit = _parse_args(sys.argv)
    except ValueError as exc:
        print(f"Error: {exc}")
        return 2

    cfg = load_config(config_path, overrides_path)
    graph_limits = _load_graph_limits(config_path, overrides_path, cfg)
    if graph_limits is not None:
        notes = []
        if graph_limits.max_total_kegs is not None:
            notes.append(f"kegs<= {graph_limits.max_total_kegs}")
        if graph_limits.max_total_casks is not None:
            notes.append(f"casks<= {graph_limits.max_total_casks}")
        if graph_limits.max_total_jars is not None:
            notes.append(f"jars<= {graph_limits.max_total_jars}")
        if graph_limits.max_total_dehydrators is not None:
            notes.append(f"dehydrators<= {graph_limits.max_total_dehydrators}")
        if graph_limits.max_total_bee_houses is not None:
            notes.append(f"bee_houses<= {graph_limits.max_total_bee_houses}")
        if graph_limits.max_outdoor_tiles is not None:
            notes.append(f"outdoor_tiles<= {graph_limits.max_outdoor_tiles}")
        if notes:
            print("note: graph limits enabled (" + ", ".join(notes) + ")")
    plots = list(cfg.plots)
    if not plots:
        print("Error: config must define plots.")
        return 2

    outdoor_plots = _outdoor_plots(plots)
    if not outdoor_plots and is_save_file(config_path):
        sprinkler_tiles, sprinkler_counts = sprinkler_tiles_from_save(config_path)
        if sprinkler_tiles > 0:
            plots = _add_sprinkler_outdoor_plots(cfg, plots, sprinkler_tiles)
            outdoor_plots = _outdoor_plots(plots)
            print(
                "note: no outdoor plots in save; derived outdoor tiles from sprinklers "
                f"(placed_quality={sprinkler_counts['placed_quality']}, "
                f"placed_iridium={sprinkler_counts['placed_iridium']}, "
                f"storage_quality={sprinkler_counts['storage_quality']}, "
                f"storage_iridium={sprinkler_counts['storage_iridium']}, "
                f"tiles={sprinkler_tiles})"
            )
            if cfg.crop == "both":
                print("note: sprinkler-derived outdoor tiles split 50/50 starfruit vs ancient for the base mix")
    if not outdoor_plots:
        print("Error: no plot name contains 'outdoor' in config.")
        return 2

    outdoor_base_total = sum(plot.tiles_total for plot in outdoor_plots)
    if outdoor_base_total <= 0:
        print("Error: outdoor plots must include tiles to vary.")
        return 2

    fruit_tree_daily = build_daily_fruit(
        cfg.fruit_trees,
        start_day_of_year=1,
        max_days=cfg.simulation.max_days,
    )
    fruit_tree_priority = sorted(
        tree_ids_from_config(cfg.fruit_trees),
        key=lambda fruit_id: wine_price_for_crop(fruit_id, cfg.economy),
        reverse=True,
    )
    base_profit = _compute_total_profit(cfg, plots, fruit_tree_daily, fruit_tree_priority)
    print(f"base profit (current save/config): {base_profit:,}")
    print(f"target profit: {target_profit:,}\n")

    kegs_values = _range_from_base(cfg.kegs, step=10, min_value=0, extra=400, min_end=400)
    if graph_limits is not None:
        kegs_values = _apply_limit(kegs_values, cfg.kegs, graph_limits.max_total_kegs)
    tiles_max = outdoor_base_total + 600
    if graph_limits is not None and graph_limits.max_outdoor_tiles is not None:
        tiles_max = min(tiles_max, graph_limits.max_outdoor_tiles)
    tiles_values = _iter_range(0, tiles_max, 10)

    outdoor_names = {plot.name.strip().lower() for plot in outdoor_plots}
    scenarios = [
        (
            "Config Mix",
            lambda total: _clone_plots_with_outdoor_total(
                plots=plots,
                outdoor_plots=outdoor_names,
                outdoor_total=total,
                outdoor_base_total=outdoor_base_total,
            ),
        ),
        (
            "Outdoor Starfruit (Summer)",
            lambda total: _replace_outdoors_with_single_crop(
                plots=plots,
                outdoor_plots=outdoor_names,
                outdoor_total=total,
                crop_id="starfruit",
                seasons=["summer"],
            ),
        ),
        (
            "Outdoor Ancient (Spring-Fall)",
            lambda total: _replace_outdoors_with_single_crop(
                plots=plots,
                outdoor_plots=outdoor_names,
                outdoor_total=total,
                crop_id="ancient",
                seasons=["spring", "summer", "fall"],
            ),
        ),
    ]

    jar_values = _range_from_base(cfg.preserves_jars, 10, 0, 200, 200)
    dehydrator_values = _range_from_base(cfg.dehydrators, 5, 0, 60, 60)
    bee_values = _range_from_base(cfg.bees.bee_houses, 10, 0, 200, 200)
    cask_values = _range_from_base(cfg.casks, 10, 0, 200, 200)
    if graph_limits is not None:
        jar_values = _apply_limit(jar_values, cfg.preserves_jars, graph_limits.max_total_jars)
        dehydrator_values = _apply_limit(dehydrator_values, cfg.dehydrators, graph_limits.max_total_dehydrators)
        bee_values = _apply_limit(bee_values, cfg.bees.bee_houses, graph_limits.max_total_bee_houses)
        cask_values = _apply_limit(cask_values, cfg.casks, graph_limits.max_total_casks)

    expansion_specs = [
        ("Kegs vs Preserves Jars", "Kegs", "Preserves Jars", kegs_values, jar_values, "jars"),
        ("Kegs vs Dehydrators", "Kegs", "Dehydrators", kegs_values, dehydrator_values, "dehydrators"),
        ("Kegs vs Bee Houses", "Kegs", "Bee Houses", kegs_values, bee_values, "bees"),
        ("Kegs vs Casks", "Kegs", "Casks", kegs_values, cask_values, "casks"),
    ]

    prof_kegs = _range_from_base(cfg.kegs, step=20, min_value=0, extra=200, min_end=200)
    if graph_limits is not None:
        prof_kegs = _apply_limit(prof_kegs, cfg.kegs, graph_limits.max_total_kegs)
    prof_tiles_max = outdoor_base_total + 400
    if graph_limits is not None and graph_limits.max_outdoor_tiles is not None:
        prof_tiles_max = min(prof_tiles_max, graph_limits.max_outdoor_tiles)
    prof_tiles = _iter_range(0, prof_tiles_max, 20)

    total_points = 0
    total_points += len(kegs_values) * len(tiles_values) * len(scenarios)
    total_points += len(prof_kegs) * len(prof_tiles) * 16
    for _, _, _, x_vals_list, y_vals_list, _ in expansion_specs:
        total_points += len(x_vals_list) * len(y_vals_list)
    progress = _Progress(total_points)

    # Land vs kegs scenarios (existing) -----------------------------------------------------------
    x_vals = np.array(kegs_values, dtype=float)
    y_vals = np.array(tiles_values, dtype=float)
    x_grid, y_grid = np.meshgrid(x_vals, y_vals)

    scenario_grids: list[tuple[str, np.ndarray]] = []
    for name, builder in scenarios:
        z_values: list[list[int]] = []
        for tiles in tiles_values:
            row: list[int] = []
            for kegs in kegs_values:
                sim_plots = builder(tiles)
                variant = _cfg_with_counts(cfg, kegs=kegs)
                total_profit = _compute_total_profit(variant, sim_plots, fruit_tree_daily, fruit_tree_priority)
                row.append(total_profit)
                progress.update()
            z_values.append(row)
        scenario_grids.append((name, np.array(z_values, dtype=float)))

    z_min = float(min(np.min(grid) for _, grid in scenario_grids))
    z_max = float(max(np.max(grid) for _, grid in scenario_grids))
    norm = colors.Normalize(vmin=z_min, vmax=z_max)
    cmap = colormaps.get_cmap("viridis")
    fig = plt.figure(figsize=(6.5 * len(scenarios), 7.5))
    for idx, (name, z_grid) in enumerate(scenario_grids, start=1):
        ax = fig.add_subplot(1, len(scenarios), idx, projection="3d")
        ax.set_title(name, pad=12)
        ax.set_xlabel("Kegs")
        ax.set_ylabel("Outdoor Tiles")
        ax.set_zlabel("Total Profit")
        _plot_surface(ax, x_grid, y_grid, z_grid, norm, cmap, target_profit)
        _annotate_max(ax, kegs_values, tiles_values, z_grid)

    mappable = cm.ScalarMappable(norm=norm, cmap=cmap)
    mappable.set_array([])
    fig.colorbar(mappable, ax=fig.get_axes(), shrink=0.6, pad=0.06, label="Total Profit")
    fig.suptitle("Yearly Profit vs Kegs and Outdoor Tiles (10M contour in white)", y=0.98)
    fig.tight_layout()
    land_path = output_path
    if output_path:
        fig.savefig(land_path, dpi=200)


    # Professions grid (valid combinations) -------------------------------------------------------
    farming_variants = [
        ("Rancher+Coopmaster", FarmingProfessions(rancher=True, coopmaster=True)),
        ("Rancher+Shepherd", FarmingProfessions(rancher=True, shepherd=True)),
        ("Tiller+Artisan", FarmingProfessions(tiller=True, artisan=True)),
        ("Tiller+Agriculturist", FarmingProfessions(tiller=True, agriculturist=True)),
    ]
    foraging_variants = [
        ("Forester+Tapper", ForagingProfessions(forester=True, tapper=True)),
        ("Forester+Lumberjack", ForagingProfessions(forester=True, lumberjack=True)),
        ("Gatherer+Botanist", ForagingProfessions(gatherer=True, botanist=True)),
        ("Gatherer+Tracker", ForagingProfessions(gatherer=True, tracker=True)),
    ]
    prof_x = np.array(prof_kegs, dtype=float)
    prof_y = np.array(prof_tiles, dtype=float)
    prof_xg, prof_yg = np.meshgrid(prof_x, prof_y)
    prof_grids: list[tuple[str, np.ndarray]] = []
    prof_labels: list[tuple[str, str]] = []
    for farm_name, farm_prof in farming_variants:
        for for_name, for_prof in foraging_variants:
            label = f"{farm_name}\n{for_name}"
            prof_labels.append((farm_name, for_name))
            z_values: list[list[int]] = []
            cfg_prof = _apply_professions(cfg, farm_prof, for_prof)
            for tiles in prof_tiles:
                row: list[int] = []
                for kegs in prof_kegs:
                    sim_plots = _clone_plots_with_outdoor_total(
                        plots=plots,
                        outdoor_plots=outdoor_names,
                        outdoor_total=tiles,
                        outdoor_base_total=outdoor_base_total,
                    )
                    variant = _cfg_with_counts(cfg_prof, kegs=kegs)
                    row.append(_compute_total_profit(variant, sim_plots, fruit_tree_daily, fruit_tree_priority))
                    progress.update()
                z_values.append(row)
            prof_grids.append((label, np.array(z_values, dtype=float)))

    prof_min = float(min(np.min(grid) for _, grid in prof_grids))
    prof_max = float(max(np.max(grid) for _, grid in prof_grids))
    prof_norm = colors.Normalize(vmin=prof_min, vmax=prof_max)
    prof_cmap = colormaps.get_cmap("viridis")
    prof_fig = plt.figure(figsize=(16, 12))
    idx = 1
    for label, z_grid in prof_grids:
        ax = prof_fig.add_subplot(4, 4, idx, projection="3d")
        ax.set_title(label, pad=6, fontsize=8)
        ax.set_xlabel("Kegs")
        ax.set_ylabel("Outdoor Tiles")
        ax.set_zlabel("Profit")
        _plot_surface(ax, prof_xg, prof_yg, z_grid, prof_norm, prof_cmap, target_profit)
        _annotate_max(ax, prof_kegs, prof_tiles, z_grid, fontsize=6)
        idx += 1
    mappable = cm.ScalarMappable(norm=prof_norm, cmap=prof_cmap)
    mappable.set_array([])
    prof_fig.colorbar(mappable, ax=prof_fig.get_axes(), shrink=0.6, pad=0.02, label="Total Profit")
    prof_fig.suptitle("Profession Combinations (10M contour in white)", y=0.98)
    prof_fig.tight_layout()

    prof_scores: list[tuple[int, str]] = []
    for farm_name, farm_prof in farming_variants:
        for for_name, for_prof in foraging_variants:
            cfg_prof = _apply_professions(cfg, farm_prof, for_prof)
            prof_scores.append((_compute_total_profit(cfg_prof, plots), f"{farm_name} / {for_name}"))
    prof_scores.sort(reverse=True, key=lambda item: item[0])
    print("\nprofession impact (base layout):")
    for profit, label in prof_scores:
        print(f"  {label}: {profit:,}")

    # Expansion scenarios -------------------------------------------------------------------------
    expansion_grids: list[tuple[str, list[int], list[int], np.ndarray, str, str, str]] = []
    for title, x_label, y_label, x_vals_list, y_vals_list, kind in expansion_specs:
        z_values: list[list[int]] = []
        for y in y_vals_list:
            row: list[int] = []
            for x in x_vals_list:
                if kind == "jars":
                    variant = _cfg_with_counts(cfg, kegs=x, preserves_jars=y)
                elif kind == "dehydrators":
                    variant = _cfg_with_counts(cfg, kegs=x, dehydrators=y)
                elif kind == "casks":
                    variant = _cfg_with_counts(cfg, kegs=x)
                    variant = replace(variant, casks=int(y))
                else:
                    variant = _cfg_with_counts(cfg, kegs=x, bee_houses=y)
                row.append(_compute_total_profit(variant, plots, fruit_tree_daily, fruit_tree_priority))
                progress.update()
            z_values.append(row)
        expansion_grids.append(
            (title, x_vals_list, y_vals_list, np.array(z_values, dtype=float), x_label, y_label, kind)
        )

    exp_min = float(min(np.min(grid) for _, _, _, grid, _, _, _ in expansion_grids))
    exp_max = float(max(np.max(grid) for _, _, _, grid, _, _, _ in expansion_grids))
    exp_norm = colors.Normalize(vmin=exp_min, vmax=exp_max)
    exp_cmap = colormaps.get_cmap("viridis")
    exp_fig = plt.figure(figsize=(18, 6))
    for idx, (title, x_vals_list, y_vals_list, z_grid, x_label, y_label, _) in enumerate(expansion_grids, start=1):
        ax = exp_fig.add_subplot(1, len(expansion_grids), idx, projection="3d")
        ax.set_title(title, pad=10)
        ax.set_xlabel(x_label)
        ax.set_ylabel(y_label)
        ax.set_zlabel("Total Profit")
        exp_x = np.array(x_vals_list, dtype=float)
        exp_y = np.array(y_vals_list, dtype=float)
        exp_xg, exp_yg = np.meshgrid(exp_x, exp_y)
        _plot_surface(ax, exp_xg, exp_yg, z_grid, exp_norm, exp_cmap, target_profit)
        _annotate_max(ax, x_vals_list, y_vals_list, z_grid)
    mappable = cm.ScalarMappable(norm=exp_norm, cmap=exp_cmap)
    mappable.set_array([])
    exp_fig.colorbar(mappable, ax=exp_fig.get_axes(), shrink=0.6, pad=0.08, label="Total Profit")
    exp_fig.suptitle("Processing & Honey Expansion (10M contour in white)", y=0.98)
    exp_fig.tight_layout()

    # Suggestions based on ranges -----------------------------------------------------------------
    print(f"I found these ways to hit your goal of {target_profit:,} (within scanned ranges):")
    printed_any = False
    for name, z_grid in scenario_grids:
        solutions = _solutions_for_target(kegs_values, tiles_values, z_grid, target_profit)
        if not solutions:
            continue
        printed_any = True
        pareto = _pareto_minimal(solutions)
        print(f"  {name}: {len(pareto)} option(s)")
        for x, y, z in pareto:
            print(f"    kegs={x} outdoor_tiles={y} profit={z:,}")

    for title, x_vals_list, y_vals_list, z_grid, x_label, y_label, _ in expansion_grids:
        solutions = _solutions_for_target(x_vals_list, y_vals_list, z_grid, target_profit)
        if not solutions:
            continue
        printed_any = True
        pareto = _pareto_minimal(solutions)
        print(f"  {title}: {len(pareto)} option(s)")
        for x, y, z in pareto:
            print(f"    {x_label.lower().replace(' ', '_')}={x} {y_label.lower().replace(' ', '_')}={y} profit={z:,}")

    prof_hits: list[tuple[int, str]] = []
    for profit, label in prof_scores:
        if profit >= target_profit:
            prof_hits.append((profit, label))
    if prof_hits:
        printed_any = True
        print("  professions (base layout):")
        for profit, label in prof_hits:
            print(f"    {label}: {profit:,}")

    if not printed_any:
        print("  no combinations in scanned ranges hit the target.")
        print("  try increasing the scan ranges or adjusting crop layouts.")

    # Pie chart for revenue breakdown at the base config.
    base_result = simulate_year_multi_crop(
        crops=_select_crops(cfg),
        mods=GrowthModifiers(
            fertilizer=cfg.growth.fertilizer,
            agriculturist=cfg.professions.farming.agriculturist,
            paddy_bonus=cfg.growth.paddy_bonus,
        ),
        plots=plots,
        kegs=cfg.kegs,
        casks=cfg.casks,
        max_days=cfg.simulation.max_days,
        start_day_of_year=1,
        starting_fruit=cfg.starting_inventory.fruit,
        starting_base_wine=cfg.starting_inventory.base_wine,
        cask_full_batch_required=cfg.economy.cask_full_batch_required,
        casks_with_walkways=cfg.economy.casks_with_walkways,
        preserves_jars=cfg.preserves_jars,
        dehydrators=cfg.dehydrators,
        external_daily_fruit=fruit_tree_daily,
        external_priority=fruit_tree_priority,
    )
    crop_profit = compute_profit(base_result.per_crop, cfg.economy, cfg.growth.fertilizer)
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
    categories = build_category_totals(crop_profit, animal_profit, honey_profit)
    labels = [
        "cheese",
        "mayo",
        "cloth",
        "truffle_oil",
        "raw_truffles",
        "raw_animal_products",
        "aged_wine",
        "non_aged_wine",
        "jarred_fruit",
        "honey",
        "dehydrators",
        "raw_fruit",
    ]
    values = [categories.get(label, 0) for label in labels]
    pie_labels = [label if value > 0 else "" for label, value in zip(labels, values)]
    pie_fig, pie_ax = plt.subplots(figsize=(7.5, 7.5))
    pie_ax.set_title("Revenue Breakdown (Base Config)")
    pie_ax.pie(
        values,
        labels=pie_labels,
        autopct=lambda pct: f"{pct:.1f}%" if pct > 0 else "",
        startangle=90,
    )
    pie_ax.axis("equal")
    total_value = sum(values)
    lines = [f"{label}: {value:,}" for label, value in zip(labels, values)]
    lines.append(f"total: {total_value:,}")
    pie_ax.text(
        1.05,
        0.5,
        "\n".join(lines),
        transform=pie_ax.transAxes,
        va="center",
        ha="left",
        fontsize=9,
        bbox={"boxstyle": "round", "facecolor": "white", "alpha": 0.85},
    )
    pie_fig.tight_layout()

    def _suffix_path(path: str, suffix: str) -> str:
        if not path:
            return ""
        if path.lower().endswith(".png"):
            return path[:-4] + f"_{suffix}.png"
        return path + f"_{suffix}.png"

    if output_path:
        prof_fig.savefig(_suffix_path(output_path, "professions"), dpi=200)
        exp_fig.savefig(_suffix_path(output_path, "expansion"), dpi=200)
        pie_fig.savefig(_suffix_path(output_path, "pie"), dpi=200)
    else:
        plt.show()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
