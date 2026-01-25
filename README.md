# Stardew Growth Simulator

TLDR (setup + run)
1) If you have a save file, run the simulator directly on it:
   `python -m sim.main path/to/SaveGame.xml [overrides.json]`
2) If you don't have a save file, use a full JSON config:
   `python -m sim.main path/to/config.json`
3) Save files populate your real farm counts (machines, animals, professions, greenhouse crops).
   JSON is only used for fields not present in the save (economy/prices, flower plans, etc).
4) Each run simulates exactly one Stardew year (112 days) starting on Spring 1,
   and reports production, keg sufficiency, cask usage, and profit.

---

## Graph app (what-if scenarios)

The graph app generates multiple 3D surfaces + a pie chart so you can see
what changes move you toward 10M/year.

Run with a save file (preferred):
```
python -m sim.graph_app saved_game/YourSave.xml configs/overrides.json output.png --target 10000000
```

Run with a full JSON config:
```
python -m sim.graph_app configs/example.json output.png --target 10000000
```

Outputs (when you pass `output.png`):
- `output.png`: kegs vs outdoor tiles (3 crop-mix scenarios)
- `output_professions.png`: 16 valid farming/foraging profession combinations
- `output_expansion.png`: kegs vs jars/dehydrators/bee houses/casks
- `output_pie.png`: revenue breakdown for the base config

Important notes:
- If the save has no outdoor crop plots, the graph app derives outdoor tiles
  from **stored Quality/Iridium Sprinklers** (8 tiles per Quality, 24 per Iridium)
  and assumes a 50/50 starfruit/ancient split for the base mix when `crop` is `"both"`.
- To control the exact outdoor mix or seasons, run the graph with a full JSON
  config instead of a save file (see `configs/example.json`).
- Each 3D chart annotates the max (x,y,z) value in a text box.
- The CLI prints "ways to reach your target" for all scenario grids that hit the goal.
- Use `--target` to change the goal amount (defaults to 10,000,000).
- Long scans print a simple progress indicator in the terminal.

---

## Config vs overrides (how to use the JSONs well)

Use **one** of these approaches:

1) **Save file + overrides (recommended):**
   - Save file supplies: machine counts, animals, professions, greenhouse crops,
     fruit trees, and outdoor crop tiles (if planted).
   - `overrides.json` supplies: prices, fertilizer cost, flower plans, starting inventory,
     and any assumptions not stored in the save.
   - Example: `python -m sim.main saved_game/YourSave.xml configs/overrides.json`

2) **Full JSON config (no save file):**
   - `config.json` supplies everything (machines, plots, crops, professions, prices, etc).
   - Example: `python -m sim.main configs/example.json`

If you don’t want the save file to dictate your outdoor layout, use a full JSON config.

---

## JSON config reference (config.json)

Top-level fields (JSON config):
- `kegs` (int): number of kegs you have.
- `casks` (int): number of casks available for aging (assumed 2 uses per year).
- `preserves_jars` (int): number of preserves jars (optional, default 0).
- `dehydrators` (int): number of dehydrators (optional, default 0).
- `oil_makers` (int): number of oil makers for truffle oil (optional, default 0).
- `mayo_machines` (int): number of mayonnaise machines (optional, default 0).
- `cheese_presses` (int): number of cheese presses (optional, default 0).
- `looms` (int): number of looms for cloth (optional, default 0).
- `economy` (object): prices, multipliers, and cask rules.
- `starting_inventory` (object): starting fruit/base wine at Spring 1.
- `animals` (object): optional animal buildings and assumptions.
- `bees` (object): optional bee house settings.
- `fruit_trees` (object): optional fruit tree counts (greenhouse/outdoors/island).
- `professions` (object): player profession toggles (all skills).
- `crop` (string, optional): `"starfruit"`, `"ancient"`, or `"both"` (default).
- `tiles` (int): total tiles. Optional if you use `plots` (it will sum plot tiles).
- `plots` (list): optional; lets you model greenhouse/outdoor calendars and tiles.
- `growth` (object): fertilizer + paddy bonus.
- `simulation` (object): run length and starting day-of-year.

Save file inputs:
- When you pass a save XML, the simulator derives machine counts, animals, bee houses,
  professions, greenhouse crop tiles, and fruit trees from the save (placed objects only; chests ignored).
- Casks are counted from the main `Cellar` only (extra cellars like `Cellar2..8` are ignored).
  Cask IDs `163` and `108094` are recognized.
- Oil Makers are matched by name (`Oil Maker`) and by IDs `19` and `108017` in the save.
- Outdoor tiles are only included if the save contains outdoor **starfruit** or **ancient fruit**
  tiles; otherwise outdoor plots are omitted.
- For graphing, if no outdoor plots exist in the save, the graph app counts **stored**
  Quality/Iridium Sprinklers and converts them into outdoor tile capacity.
- Fruit trees are read from `terrainFeatures` FruitTree entries (mature, non-stump only).
  Greenhouse and Island trees produce year-round; Farm trees follow seasonal fruit rules.
- Use `overrides.json` to supply pricing and other assumptions not available in saves.
- Invalid saves (e.g., over-capacity coops or truffles in HoeDirt) will error early.

`plots` and calendars:
- Use `plots` to split your tiles into named chunks (e.g., greenhouse vs outdoors).
- Each plot has a `name` (string). The graph app treats any plot with "outdoor" in the name as outdoor.
- Each plot can define `tiles` as:
  - an int (applies to any crop), or
  - a per-crop map like `{ "ANCIENT_FRUIT": 50, "STARFRUIT": 54 }`.
- Crop keys are case-insensitive; `"ancient"`, `"ancient_fruit"`, and `"ANCIENT_FRUIT"`
  all work (same for `"starfruit"`).
- Each plot can be `always` (greenhouse) or `seasons` with a list like `["summer"]`.
- If a plot omits `calendar`, it defaults to `{ "type": "always" }`.
- Growth/harvest only happens on active plot days. Kegs keep working every day.
- When `plots` are present, per-plot tiles drive the simulation; top-level `tiles`
  is only used for the header summary.
- All plots feed the same shared kegs and casks.
- If `crop` is `"both"`, use per-crop tiles so the simulator knows your split.

`simulation`:
- `max_days` (int): ignored; the simulator always runs exactly 112 days.
- `start_day_of_year` (int, 1..112): parsed but the CLI always starts at Spring 1.
- `calendar` (object): legacy way to set the start day (see below).
- `assume_year_round` (bool, optional): currently informational only (used in output).
- `calendar.current_season` / `calendar.day`: legacy way to derive `start_day_of_year`.

`economy` (optional):
- `wine_price`: per-crop wine sell prices, e.g. `{ "STARFRUIT": 0 }`.
- `fruit_price`: per-crop fruit sell prices, e.g. `{ "STARFRUIT": 0 }`.
- `seed_cost`: per-crop seed costs, e.g. `{ "STARFRUIT": 0 }`.
- `fertilizer_cost`: per-fertilizer costs, e.g. `{ "deluxe_speed_gro": 0 }`.
- `aged_wine_multiplier`: multiplier for aged wine vs base wine (default `2.0`).
- `wine_quality_multiplier` / `fruit_quality_multiplier`: quality multipliers (default `1.0`).
- `artisan` / `tiller`: legacy flags (prefer `professions.farming`).
- `cask_full_batch_required`: if `true`, you only get full cask capacity when
  you can fill all casks on each batch day (Spring 1 and Fall 1 for a 112-day year).
- `casks_with_walkways`: fallback cask count if full batch is not met.
- Artisan/Tiller bonuses are configured under `professions.farming`.
- If `wine_price` is missing but `fruit_price` is provided, wine uses the in-game base
  formula of `3 * fruit_price`. If both are missing, revenue is `0`.
  Crop keys are case-insensitive here as well (applies to fruit trees too).
- Preserves jar and dehydrator prices are derived from `fruit_price` using in-game formulas
  and then the Artisan bonus (if enabled). If `fruit_price` is missing, jelly/dried revenue is `0`.

`starting_inventory` (optional):
- `fruit`: per-crop fruit on hand at Spring 1.
- `base_wine`: per-crop base wine on hand at Spring 1.
- Base wine here is available for the Spring 1 cask batch fill.

`animals` (optional):
- `coops`: list of coops with per-animal counts (each coop has `name`, `chickens`, `ducks`, `rabbits`, `void_chickens`).
- `barns`: list of barns with per-animal counts (each barn has `name`, `cows`, `goats`, `pigs`, `sheep`).
- `large_egg_rate` / `large_milk_rate` / `large_goat_milk_rate`: 0..1 share that become large products.
- `rabbit_foot_rate`: 0..1 share of rabbit products that become rabbit's feet (rest are wool).
- Machine-limited processing (lazy assumption: reload once per day):
  - `mayo_machines` / `cheese_presses` / `looms` each process up to 1 item per machine per day.
  - `oil_makers` process up to 1 truffle per maker per day (actual in-game time is 6 hours).
  - Leftover eggs/milk/wool are sold raw.
- Production cadence (wiki): chickens/void chickens daily, ducks every 2 days, cows daily,
  goats every 2 days, sheep every 3 days (daily with Shepherd), rabbits every 4 days
  (rabbit foot replaces wool), pigs find truffles on non-winter days.
- Truffles are treated as foraged items: Gatherer adds an expected +20% yield; Botanist
  makes raw truffles use iridium price. Truffles are not animal products, so Rancher
  does not apply.
- Pricing uses wiki values: egg 50, large egg 95, duck egg 95, void egg 65, milk 125,
  large milk 190, goat milk 225, large goat milk 345, wool 340, rabbit's foot 565,
  mayonnaise 190/285, duck mayo 375, void mayo 275, cheese 230/345, goat cheese 400/600,
  cloth 470, truffle 625, truffle oil 1065 (Artisan applies to cheese/mayo/cloth/truffle oil,
  Rancher applies to raw animal products only).

`bees` (optional):
- `bee_houses`: number of bee houses.
- `flower_base_price`: base price of the flower used for honey (0 for wild honey).
- `seasons`: seasons when honey is produced (defaults to spring/summer/fall).
- `flower_plan`: optional per-season flower strategy:
  - `spring` / `summer` / `fall` keys, each with:
    - `fast`: `{ "name": "...", "growth_days": 0, "base_price": 0 }`
    - `expensive`: `{ "name": "...", "growth_days": 0, "base_price": 0 }`
- Honey uses the wiki formula: `100 + 2 * flower_base_price`, produced every 4 days (Artisan applies).
- If `flower_plan` is present, honey price changes by season day:
  - Fast flower is planted day 1.
  - Expensive flower is planted day 1.
  - Fast flower is removed once the expensive flower is ready.
  - Honey before any flower blooms is wild honey (base price 100).

`fruit_trees` (optional):
- `greenhouse` / `outdoors` / `always`: per-fruit tree counts.
- Valid fruit keys: `apple`, `apricot`, `cherry`, `orange`, `peach`, `pomegranate`,
  `banana`, `mango` (case-insensitive).
- `greenhouse` and `always` are treated as year-round production.
- `outdoors` uses seasonal production: spring (apricot/cherry), summer (orange/peach/banana/mango),
  fall (apple/pomegranate). Winter has no fruit tree production.
- Fruit tree fruit enters the same pipeline as crops: kegs first, then jars, then dehydrators.

`professions`:
- `farming`: `rancher`, `tiller`, `coopmaster`, `shepherd`, `artisan`, `agriculturist`.
- `foraging`: `forester`, `gatherer`, `lumberjack`, `tapper`, `botanist`, `tracker`.
- `fishing`: `fisher`, `trapper`, `angler`, `pirate`, `mariner`, `luremaster`.
- `mining`: `miner`, `geologist`, `blacksmith`, `prospector`, `excavator`, `gemologist`.
- `combat`: `fighter`, `scout`, `brute`, `defender`, `acrobat`, `desperado`.
- Effects currently modeled:
  - `agriculturist`: +10% crop growth speed.
  - `tiller`: +10% crop sell value.
  - `artisan`: +40% artisan goods value (wine, jelly, dried fruit, cheese, mayo, cloth, honey, truffle oil).
  - `rancher`: +20% raw animal product sell value (eggs, milk, wool, rabbit's foot).
  - `shepherd`: sheep produce wool daily (instead of every 3 days).
  - `gatherer`: expected +20% truffle yield (deterministic floor).
  - `botanist`: raw truffles use iridium price.
- Other professions are recorded but currently have no effect in the sim.
- Legacy compatibility: if `professions` is omitted, `growth.agriculturist` and
  `economy.artisan`/`economy.tiller` are still accepted.
- Validation: inputs are checked for logical errors (e.g., >12 animals in a coop,
  truffles appearing as planted crops, invalid animal rates, invalid seasons for crops,
  negative machine counts, or `casks_with_walkways` > `casks`).

`growth`:
- `fertilizer`: `"none"`, `"speed_gro"`, `"deluxe_speed_gro"`, `"hyper_speed_gro"`.
- `paddy_bonus`: included for completeness (not used by these crops).
- `agriculturist`: legacy flag (prefer `professions.farming.agriculturist`).

---

## How to run

From the repo root:
```
python -m sim.main configs/example.json
```

From a save file (preferred when available):
```
python -m sim.main saved_game/YourSave.xml configs/overrides.json
```
Example overrides file: `configs/overrides_example.json`

You can point to any JSON file:
```
python -m sim.main path/to/your_config.json
```

Graph app (3D what-if scenarios + pie):
```
python -m sim.graph_app saved_game/YourSave.xml configs/overrides.json output.png --target 10000000
```
This writes:
- `output.png`: kegs vs outdoor tiles (3 crop-mix scenarios)
- `output_professions.png`: 16 valid farming/foraging profession combinations
- `output_expansion.png`: kegs vs jars/dehydrators/bee houses
- `output_pie.png`: revenue breakdown for the base config
It also prints suggested focus points for reaching 10M.

---

## What the output means

The header line echoes your setup:
```
tiles=... kegs=... casks=... preserves_jars=... dehydrators=... oil_makers=... mayo_machines=... cheese_presses=... looms=... fertilizer=... agriculturist=...
year_days=... start_day_of_year=... (year-round assumed=...)
```

Then you will see one block per crop:
- `fruit harvested (year)`: total fruit harvested in the year.
- `base wine produced (year)`: base wine completed by kegs in the year.
- `aged wine produced (year)`: wine aged via the two batch fills (up to `2 * casks` per year).
- `base wine sold (year)`: base wine left after the batch fills.
- `unprocessed fruit (year end)`: fruit left over at year end (not kegged).
- `wine in kegs (year end)`: kegs still running at year end.
- `jelly produced (year)`: preserves jar output completed in the year.
- `dried fruit produced (year)`: dehydrator output completed in the year.
- `jelly in jars (year end)`: preserves jars still running at year end.
- `dried fruit in dehydrators (year end)`: dehydrators still running at year end.
- `seed units used`: total seeds planted for the crop (starfruit replants every harvest).
- Seed units for Ancient Fruit are counted once per plot (initial planting only).
- `fertilizer units used`: fertilizer applications (per harvest for starfruit, per season for regrow crops).
- `base wine revenue / aged wine revenue / jelly revenue / dried fruit revenue / seed cost / net profit`: profit breakdown.
  Fruit revenue and fertilizer cost are included in the totals.

If animals or bees are configured, a short revenue summary is printed for:
- `cheese revenue`
- `mayo revenue`
- `cloth revenue`
- `truffle oil revenue`
- `raw truffles revenue`
- `raw animal products revenue`
- `honey revenue`

If fruit trees are configured, a summary block shows per-scope counts and a
per-fruit "best use" estimate based on current prices (kegs vs jars vs dehydrators vs raw).

Summary lines:
- `kegs sufficient for full conversion`: `true` if all fruit is fully processed by year end.
- `full cask batch met`: `true` if you can fill all casks on each batch day (Spring 1 and Fall 1).
- `casks used for aging`: effective casks after applying the full-batch rule.
- `cask uses per cask (max 2.00)`: how many full uses each cask got in the year.
- `total base wine sold`: total base wine sold after aging allocation.
- `total aged wine produced`: total wine aged in casks.
- `total jelly produced`: total preserves jar output.
- `total dried fruit produced`: total dehydrator output.
- `total fruit unprocessed (year end)`: total raw fruit remaining.
- `total wine in kegs (year end)`: total wine still in kegs.
- `total jelly in jars (year end)`: total preserves jars still running.
- `total dried fruit in dehydrators (year end)`: total dehydrators still running.
- `total revenue (year)`: gross revenue from all products and fruit sales.
- `total seed cost (year)`: total seed spend.
- `total fertilizer cost (year)`: total fertilizer spend.
- `TOTAL PROFIT (year)`: final profit number.
- `quick wins`: simple bottleneck hints (kegs/casks/machines/flowers) when applicable.

Cask allocation priority is Starfruit first, then Ancient Fruit. Keg input is also
prioritized the same way when fruit inventories compete. Aging is modeled as
two batch fills per year (day 1 and day 57 in a 112-day year). Wine produced
after the last batch day cannot be aged that year and is sold as base wine.
Unprocessed fruit is sold at year end using `economy.fruit_price`.
Preserves jars and dehydrators are filled after kegs each day using remaining fruit.
Animal and honey revenues are added on top of crop revenues (animal/bait costs are not modeled).

---

## Example configs (194 casks)

Note: With full-batch casks enabled, you need `casks` base wine ready on
Spring 1 and Fall 1, or set `casks_with_walkways` to a smaller layout.

Overrides example for save files (minimal JSON):
```
{
  "economy": {
    "wine_price": { "STARFRUIT": 2250, "ANCIENT_FRUIT": 1650 },
    "fruit_price": { "STARFRUIT": 750, "ANCIENT_FRUIT": 550 },
    "seed_cost": { "STARFRUIT": 400, "ANCIENT_FRUIT": 0 },
    "fertilizer_cost": { "deluxe_speed_gro": 150 },
    "aged_wine_multiplier": 2.0,
    "wine_quality_multiplier": 1.0,
    "fruit_quality_multiplier": 1.0,
    "cask_full_batch_required": true,
    "casks_with_walkways": 0
  },
  "growth": { "fertilizer": "deluxe_speed_gro" },
  "bees": {
    "flower_base_price": 0,
    "seasons": ["spring", "summer", "fall"]
  },
  "starting_inventory": {
    "base_wine": { "STARFRUIT": 0, "ANCIENT_FRUIT": 0 }
  }
}
```

Example A: Greenhouse + Summer outdoor Starfruit (per-crop tiles)
(Replace the `0` values in `economy` with your in-game prices.)
```
{
  "kegs": 194,
  "casks": 194,
  "crop": "starfruit",
  "growth": {
    "fertilizer": "deluxe_speed_gro"
  },
  "simulation": {},
  "economy": {
    "wine_price": { "STARFRUIT": 0 },
    "fruit_price": { "STARFRUIT": 0 },
    "seed_cost": { "STARFRUIT": 0 },
    "fertilizer_cost": { "deluxe_speed_gro": 0 },
    "aged_wine_multiplier": 2.0,
    "wine_quality_multiplier": 1.0,
    "fruit_quality_multiplier": 1.0,
    "cask_full_batch_required": true,
    "casks_with_walkways": 0
  },
  "professions": {
    "farming": {
      "rancher": false,
      "tiller": false,
      "coopmaster": false,
      "shepherd": false,
      "artisan": true,
      "agriculturist": false
    },
    "foraging": {
      "forester": false,
      "gatherer": false,
      "lumberjack": false,
      "tapper": false,
      "botanist": false,
      "tracker": false
    },
    "fishing": {
      "fisher": false,
      "trapper": false,
      "angler": false,
      "pirate": false,
      "mariner": false,
      "luremaster": false
    },
    "mining": {
      "miner": false,
      "geologist": false,
      "blacksmith": false,
      "prospector": false,
      "excavator": false,
      "gemologist": false
    },
    "combat": {
      "fighter": false,
      "scout": false,
      "brute": false,
      "defender": false,
      "acrobat": false,
      "desperado": false
    }
  },
  "starting_inventory": {
    "fruit": { "STARFRUIT": 0 },
    "base_wine": { "STARFRUIT": 0 }
  },
  "bees": {
    "bee_houses": 25,
    "flower_base_price": 0,
    "seasons": ["spring", "summer", "fall"],
    "flower_plan": {
      "spring": {
        "fast": { "name": "Tulip", "growth_days": 6, "base_price": 30 },
        "expensive": { "name": "Blue Jazz", "growth_days": 7, "base_price": 50 }
      },
      "summer": {
        "fast": { "name": "Poppy", "growth_days": 7, "base_price": 140 },
        "expensive": { "name": "Poppy", "growth_days": 7, "base_price": 140 }
      },
      "fall": {
        "fast": { "name": "Sunflower", "growth_days": 8, "base_price": 80 },
        "expensive": { "name": "Fairy Rose", "growth_days": 12, "base_price": 290 }
      }
    }
  },
  "plots": [
    { "name": "greenhouse", "tiles": { "STARFRUIT": 120 }, "calendar": { "type": "always" } },
    { "name": "outdoors", "tiles": { "STARFRUIT": 400 }, "calendar": { "type": "seasons", "seasons": ["summer"] } }
  ]
}
```

Example B: Greenhouse Ancient Fruit only (year-round)
(Replace the `0` values in `economy` with your in-game prices.)
```
{
  "kegs": 194,
  "casks": 194,
  "crop": "ancient",
  "growth": {
    "fertilizer": "none"
  },
  "simulation": {},
  "economy": {
    "wine_price": { "ANCIENT_FRUIT": 0 },
    "fruit_price": { "ANCIENT_FRUIT": 0 },
    "seed_cost": { "ANCIENT_FRUIT": 0 },
    "fertilizer_cost": { "none": 0 },
    "aged_wine_multiplier": 2.0,
    "wine_quality_multiplier": 1.0,
    "fruit_quality_multiplier": 1.0,
    "cask_full_batch_required": true,
    "casks_with_walkways": 0
  },
  "professions": {
    "farming": {
      "rancher": false,
      "tiller": false,
      "coopmaster": false,
      "shepherd": false,
      "artisan": true,
      "agriculturist": false
    },
    "foraging": {
      "forester": false,
      "gatherer": false,
      "lumberjack": false,
      "tapper": false,
      "botanist": false,
      "tracker": false
    },
    "fishing": {
      "fisher": false,
      "trapper": false,
      "angler": false,
      "pirate": false,
      "mariner": false,
      "luremaster": false
    },
    "mining": {
      "miner": false,
      "geologist": false,
      "blacksmith": false,
      "prospector": false,
      "excavator": false,
      "gemologist": false
    },
    "combat": {
      "fighter": false,
      "scout": false,
      "brute": false,
      "defender": false,
      "acrobat": false,
      "desperado": false
    }
  },
  "starting_inventory": {
    "fruit": { "ANCIENT_FRUIT": 0 },
    "base_wine": { "ANCIENT_FRUIT": 0 }
  },
  "plots": [
    { "name": "greenhouse", "tiles": { "ANCIENT_FRUIT": 120 }, "calendar": { "type": "always" } }
  ]
}
```

Tip: If you skip `plots`, set `tiles` directly:
```
{
  "tiles": 194,
  "kegs": 194,
  "casks": 194,
  "crop": "both"
}
```

---

## Strategy notes (1.6)

These are optional heuristics reflected in the simulator outputs:
- Starfruit is a high-value summer crop; Ancient Fruit is high-value and low-replant (greenhouse or spring-fall).
- Pigs generate truffles on non-winter days; truffle oil is an artisan good if you have oil makers.
- Bee houses gain value from flowers (e.g., Fairy Rose in fall, Poppy in summer, Blue Jazz in spring).
- Rancher boosts raw animal product value; Shepherd makes sheep wool daily; Artisan boosts artisan goods.
- Fruit tree fruit usually yields the most gold per fruit via kegs (wine), then preserves jars.
  Dehydrators are typically the lowest per-fruit option but can be used when kegs/jars are saturated.

## File map (what each file does)

- `sim/main.py`: CLI entry point. Loads JSON config and prints per-plot results.
- `sim/graph_app.py`: 3D profit graph tool (kegs vs outdoor tiles).
- `sim/config.py`: Config parsing and dataclasses, including season/day and per-crop tiles.
- `sim/crops.py`: Crop definitions (starfruit, ancient fruit) and base phase lengths.
- `sim/growth.py`: Growth speed math and phase-day reductions for fertilizer/profession.
- `sim/pipeline.py`: Core simulation of fruit → kegs → wine + calendar-aware plot simulations.
- `sim/economy.py`: Profit calculations from production totals.
- `sim/animals.py`: Animal production simulation (eggs/milk → mayo/cheese).
- `sim/bees.py`: Bee house honey production simulation.
- `sim/fruit_trees.py`: Fruit tree parsing + daily fruit output builder.
- `sim/save_loader.py`: Save-game XML parsing + JSON override merging.
- `sim/plots.py`: Plot calendars, per-crop tile helpers, and day-of-year helpers.
- `configs/example.json`: Example configuration.
- `configs/example_starfruit.json`: Example A config (starfruit, summer).
- `configs/example_ancient.json`: Example B config (ancient, greenhouse).
- `configs/overrides_example.json`: Minimal overrides for save files (economy + growth).
- `tests/test_growth.py`: Growth-stage reduction tests.
- `tests/test_pipeline.py`: Pipeline timing tests (including calendar handling).
- `tests/test_config.py`: Config parsing tests.
- `tests/test_plots.py`: Plot/calendar helper tests.
- `tests/test_economy.py`: Profit calculation tests.
- `tests/test_main.py`: CLI smoke test.
- `tests/conftest.py`: Adds repo root to `sys.path` so tests can import `sim`.
- `pyproject.toml`: Project metadata and test configuration.
