"""Inspect a Stardew save XML and summarize its structure."""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import xml.etree.ElementTree as ET


def inspect_xml(path: Path) -> int:
    size_bytes = path.stat().st_size
    with path.open("rb") as f:
        line_count = sum(1 for _ in f)

    tag_counts: Counter[str] = Counter()
    depth_counts: Counter[int] = Counter()
    fold_candidates = 0
    total_elements = 0
    max_depth = 0
    root_tag = None
    top_level_counts: Counter[str] = Counter()

    stack: list[tuple[str, int]] = []  # (tag, child_count)

    for event, elem in ET.iterparse(path, events=("start", "end")):
        if event == "start":
            tag = elem.tag
            if root_tag is None:
                root_tag = tag
            tag_counts[tag] += 1
            total_elements += 1
            stack.append((tag, 0))
            depth = len(stack)
            depth_counts[depth] += 1
            if depth > max_depth:
                max_depth = depth
            # track top-level children (depth==2 means child of root)
            if depth == 2:
                top_level_counts[tag] += 1
        else:
            # pop and mark fold candidate if it had children
            tag, child_count = stack.pop()
            if child_count > 0:
                fold_candidates += 1
            # increment parent child count
            if stack:
                parent_tag, parent_children = stack[-1]
                stack[-1] = (parent_tag, parent_children + 1)

    unique_tags = len(tag_counts)
    outline_symbols = unique_tags  # proxy: unique tag names

    print(f"File: {path}")
    print(f"Size: {size_bytes:,} bytes")
    print(f"Lines: {line_count:,}")
    print(f"Root tag: {root_tag}")
    print(f"Total elements: {total_elements:,}")
    print(f"Unique tags (outline symbols proxy): {unique_tags:,}")
    print(f"Max depth: {max_depth}")
    print(f"Fold candidates (elements with children): {fold_candidates:,}")

    print("\nTop-level children (root direct children):")
    for tag, count in top_level_counts.most_common():
        print(f"  {tag}: {count}")

    print("\nTop 20 tags by count:")
    for tag, count in tag_counts.most_common(20):
        print(f"  {tag}: {count}")

    print("\nDepth histogram (first 12 levels):")
    for depth in range(1, 13):
        if depth in depth_counts:
            print(f"  depth {depth}: {depth_counts[depth]:,}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize a Stardew save XML structure.")
    parser.add_argument("save", help="Path to the save XML file")
    args = parser.parse_args()
    return inspect_xml(Path(args.save))


if __name__ == "__main__":
    raise SystemExit(main())
