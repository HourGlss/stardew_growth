"""Scan a Stardew save for placed objects and summarize counts."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path
import xml.etree.ElementTree as ET


DEFAULT_TARGET_NAMES = [
    "Cask",
    "Keg",
    "Preserves Jar",
    "Dehydrator",
    "Bee House",
    "Cheese Press",
    "Mayonnaise Machine",
    "Oil Maker",
    "Loom",
]


def _iter_locations(root: ET.Element) -> list[tuple[str, ET.Element]]:
    """Return all GameLocations plus building interiors under Farm."""
    locations: list[tuple[str, ET.Element]] = []
    for loc in root.findall("locations/GameLocation"):
        name = loc.findtext("name") or "(unknown)"
        locations.append((name, loc))

    farm = next((loc for name, loc in locations if name == "Farm"), None)
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


def _iter_objects(location: ET.Element) -> list[ET.Element]:
    """Return placed Object nodes for a location."""
    objects = location.find("objects")
    if objects is None:
        return []
    out: list[ET.Element] = []
    for item in objects.findall("item"):
        value = item.find("value")
        if value is None:
            continue
        obj = value.find("Object")
        if obj is None:
            continue
        out.append(obj)
    return out


def _matches(obj: ET.Element, names: set[str], ids: set[str]) -> bool:
    name = (obj.findtext("name") or "").strip().lower()
    parent_sheet = (obj.findtext("parentSheetIndex") or "").strip()
    item_id = (obj.findtext("itemId") or "").strip()
    if names and name in names:
        return True
    if ids and (parent_sheet in ids or item_id in ids):
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan a Stardew save for placed objects.")
    parser.add_argument("save", help="Path to the save file (XML)")
    parser.add_argument("--name", action="append", default=[], help="Object name to match (case-insensitive)")
    parser.add_argument("--id", action="append", default=[], help="Object itemId or parentSheetIndex to match")
    parser.add_argument("--list", action="store_true", help="List total counts for all placed object names")
    parser.add_argument(
        "--top",
        type=int,
        default=25,
        help="Number of top objects to show when using --list (default 25)",
    )
    parser.add_argument("--show-locations", action="store_true", help="Show per-location counts for matches")
    args = parser.parse_args()

    save_path = Path(args.save)
    root = ET.fromstring(save_path.read_text(encoding="utf-8"))

    locations = _iter_locations(root)

    names = {n.strip().lower() for n in args.name if n.strip()}
    ids = {str(i).strip() for i in args.id if str(i).strip()}

    all_counts = Counter()
    match_counts = Counter()
    match_by_location: dict[str, Counter] = defaultdict(Counter)

    for loc_name, loc in locations:
        for obj in _iter_objects(loc):
            obj_name = obj.findtext("name") or "(unnamed)"
            all_counts[obj_name] += 1
            if names or ids:
                if _matches(obj, names, ids):
                    match_counts[obj_name] += 1
                    match_by_location[loc_name][obj_name] += 1

    if args.list:
        print("Top placed objects:")
        for name, count in all_counts.most_common(args.top):
            print(f"{name}: {count}")

    if names or ids:
        print("\nMatches:")
        if not match_counts:
            print("(none)")
        else:
            for name, count in match_counts.most_common():
                print(f"{name}: {count}")

        if args.show_locations:
            print("\nPer-location:")
            for loc_name, counts in sorted(match_by_location.items()):
                summary = ", ".join(f"{name}={cnt}" for name, cnt in counts.items())
                print(f"{loc_name}: {summary}")

    if not args.list and not (names or ids):
        print("No output. Use --list or --name/--id to match objects.")
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
