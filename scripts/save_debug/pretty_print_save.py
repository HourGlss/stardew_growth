"""Pretty-print a Stardew save XML with indentation."""
from __future__ import annotations

import argparse
from pathlib import Path
import xml.dom.minidom as minidom


def pretty_print_xml(src: Path, dst: Path | None, indent: str) -> int:
    raw = src.read_text(encoding="utf-8")
    dom = minidom.parseString(raw)
    pretty = dom.toprettyxml(indent=indent)

    # Remove blank lines introduced by minidom.
    pretty = "\n".join(line for line in pretty.splitlines() if line.strip()) + "\n"

    if dst is None:
        print(pretty, end="")
    else:
        dst.write_text(pretty, encoding="utf-8")
        print(f"Wrote: {dst}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Pretty-print a Stardew save XML file.")
    parser.add_argument("save", help="Path to the save XML file")
    parser.add_argument("output", nargs="?", help="Optional output path")
    parser.add_argument("--indent", default="  ", help="Indent string (default: two spaces)")
    args = parser.parse_args()

    src = Path(args.save)
    dst = Path(args.output) if args.output else None
    return pretty_print_xml(src, dst, args.indent)


if __name__ == "__main__":
    raise SystemExit(main())
