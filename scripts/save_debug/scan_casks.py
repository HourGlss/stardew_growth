"""Specialized scan for casks and oil makers by name or id."""
from __future__ import annotations

import argparse
from pathlib import Path
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict

CASK_IDS = {"163", "108094"}
OIL_MAKER_IDS = {"19", "108017"}


def _iter_locations(root: ET.Element) -> list[tuple[str, ET.Element]]:
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


def _iter_objects(location: ET.Element):
    objects = location.find("objects")
    if objects is None:
        return []
    out = []
    for item in objects.findall("item"):
        value = item.find("value")
        if value is None:
            continue
        obj = value.find("Object")
        if obj is None:
            continue
        out.append(obj)
    return out


def _is_match(obj: ET.Element, names: set[str], ids: set[str]) -> bool:
    name = (obj.findtext("name") or "").strip().lower()
    parent_sheet = (obj.findtext("parentSheetIndex") or "").strip()
    item_id = (obj.findtext("itemId") or "").strip()
    if names and name in names:
        return True
    if ids and (parent_sheet in ids or item_id in ids):
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan a Stardew save for casks/oil makers.")
    parser.add_argument("save", help="Path to the save file (XML)")
    parser.add_argument("--cask-id", action="append", default=list(CASK_IDS), help="Cask itemId or parentSheetIndex")
    parser.add_argument("--oil-id", action="append", default=list(OIL_MAKER_IDS), help="Oil Maker itemId or parentSheetIndex")
    parser.add_argument("--show-all", action="store_true", help="Also list any object names containing 'cask' or 'oil'")
    args = parser.parse_args()

    save_path = Path(args.save)
    root = ET.fromstring(save_path.read_text(encoding="utf-8"))

    cask_names = {"cask"}
    oil_names = {"oil maker"}
    cask_ids = {str(v).strip() for v in args.cask_id}
    oil_ids = {str(v).strip() for v in args.oil_id}

    locations = _iter_locations(root)

    cask_by_loc: dict[str, Counter] = defaultdict(Counter)
    oil_by_loc: dict[str, Counter] = defaultdict(Counter)
    cask_ids_seen = set()
    oil_ids_seen = set()
    name_hits: Counter = Counter()

    for loc_name, loc in locations:
        for obj in _iter_objects(loc):
            name = (obj.findtext("name") or "(unnamed)")
            if _is_match(obj, cask_names, cask_ids):
                cask_by_loc[loc_name][name] += 1
                parent_sheet = (obj.findtext("parentSheetIndex") or "").strip()
                item_id = (obj.findtext("itemId") or "").strip()
                if parent_sheet:
                    cask_ids_seen.add(parent_sheet)
                if item_id:
                    cask_ids_seen.add(item_id)
            if _is_match(obj, oil_names, oil_ids):
                oil_by_loc[loc_name][name] += 1
                parent_sheet = (obj.findtext("parentSheetIndex") or "").strip()
                item_id = (obj.findtext("itemId") or "").strip()
                if parent_sheet:
                    oil_ids_seen.add(parent_sheet)
                if item_id:
                    oil_ids_seen.add(item_id)
            if args.show_all:
                lower = name.lower()
                if "cask" in lower or "oil" in lower:
                    name_hits[name] += 1

    def _print_section(title: str, data: dict[str, Counter]):
        print(title)
        total = 0
        for loc, counts in sorted(data.items()):
            loc_total = sum(counts.values())
            total += loc_total
            summary = ", ".join(f"{name}={cnt}" for name, cnt in counts.items())
            print(f"  {loc}: {summary}")
        print(f"  total: {total}\n")

    _print_section("Casks", cask_by_loc)
    if cask_by_loc:
        total_all = sum(sum(c.values()) for c in cask_by_loc.values())
        total_main = sum(cask_by_loc.get("Cellar", Counter()).values())
        print(f"All cellars total: {total_all}")
        print(f"Main Cellar only: {total_main}\n")
    if cask_ids_seen:
        print(f"Cask IDs seen: {sorted(cask_ids_seen)}\n")
    _print_section("Oil Makers", oil_by_loc)
    if oil_ids_seen:
        print(f"Oil Maker IDs seen: {sorted(oil_ids_seen)}\n")

    if args.show_all:
        print("Name hits containing 'cask' or 'oil':")
        for name, count in name_hits.most_common():
            print(f"  {name}: {count}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
