from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API_URL = "https://stardewvalleywiki.com/mediawiki/api.php"
USER_AGENT = "Mozilla/5.0 (compatible; StardewGrowthBot/1.0)"
OUT_PATH = Path(__file__).resolve().parents[1] / "data" / "wiki_crops.json"


@dataclass
class SeedInfo:
    seed_name: str
    crop_name: str
    seed_sources: dict[str, int]
    seed_price: int | None


@dataclass
class CropInfo:
    name: str
    base_price: int | None


def fetch_text(url: str, params: dict[str, Any] | None = None) -> str:
    if params:
        url = f"{url}?{urlencode(params)}"
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def fetch_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    return json.loads(fetch_text(url, params=params))


def list_category_members(category: str, cmtype: str | None = None) -> list[str]:
    members: list[str] = []
    cont: str | None = None
    while True:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": category,
            "cmlimit": 500,
            "format": "json",
        }
        if cmtype:
            params["cmtype"] = cmtype
        if cont:
            params["cmcontinue"] = cont
        payload = fetch_json(API_URL, params)
        for entry in payload.get("query", {}).get("categorymembers", []):
            title = entry.get("title")
            if title:
                members.append(str(title))
        cont = payload.get("continue", {}).get("cmcontinue")
        if not cont:
            break
    return members


def parse_infobox(text: str, template: str) -> dict[str, str]:
    in_box = False
    info: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not in_box and stripped.lower().startswith(f"{{{{{template}".lower()):
            in_box = True
            continue
        if not in_box:
            continue
        if stripped.startswith("}}"):
            break
        if not stripped.startswith("|"):
            continue
        key, _, value = stripped[1:].partition("=")
        info[key.strip()] = value.strip()
    return info


def _strip_wiki_markup(raw: str) -> str:
    raw = re.sub(r"\{\{Name\|([^|}]+).*?\}\}", r"\1", raw)
    raw = re.sub(r"\[\[([^|\]]+)\|([^\]]+)\]\]", r"\2", raw)
    raw = re.sub(r"\[\[([^\]]+)\]\]", r"\1", raw)
    raw = re.sub(r"<.*?>", "", raw)
    return raw.strip()


def _parse_price(raw: str | None) -> int | None:
    if not raw:
        return None
    text = raw.lower()
    if "not sold" in text:
        return None
    match = re.search(r"(\d+)", raw)
    if not match:
        return None
    return int(match.group(1))


def parse_seed_page(seed_name: str) -> SeedInfo | None:
    page = seed_name.replace(" ", "_")
    text = fetch_text(f"https://stardewvalleywiki.com/{page}?action=raw")
    info = parse_infobox(text, "Infobox seed")
    crop_raw = info.get("crop")
    if not crop_raw:
        return None
    crop_name = _strip_wiki_markup(crop_raw)
    g_price = _parse_price(info.get("gPrice"))
    j_price = _parse_price(info.get("jPrice"))
    o_price = _parse_price(info.get("oPrice"))
    t_price = _parse_price(info.get("tPrice"))

    seed_sources: dict[str, int] = {}
    if g_price is not None:
        seed_sources["pierre"] = g_price
    if j_price is not None:
        seed_sources["joja"] = j_price
    if o_price is not None:
        seed_sources["oasis"] = o_price
    if t_price is not None:
        seed_sources["traveling_cart"] = t_price

    seed_price_candidates = [price for price in (g_price, j_price, o_price) if price is not None]
    seed_price = min(seed_price_candidates) if seed_price_candidates else None
    return SeedInfo(seed_name=seed_name, crop_name=crop_name, seed_sources=seed_sources, seed_price=seed_price)


def parse_crop_page(crop_name: str) -> CropInfo:
    page = crop_name.replace(" ", "_")
    try:
        text = fetch_text(f"https://stardewvalleywiki.com/{page}?action=raw")
    except Exception:
        return CropInfo(name=crop_name, base_price=None)
    info = parse_infobox(text, "Infobox")
    base_price = _parse_price(info.get("sellprice"))
    return CropInfo(name=crop_name, base_price=base_price)


def main() -> int:
    seed_pages = list_category_members("Category:Seeds", cmtype="page")
    seed_categories = list_category_members("Category:Seeds", cmtype="subcat")
    for category in seed_categories:
        seed_pages.extend(list_category_members(category, cmtype="page"))
    seeds: dict[str, SeedInfo] = {}
    crops: dict[str, CropInfo] = {}
    for title in seed_pages:
        seed_info = parse_seed_page(title)
        if seed_info is None:
            continue
        seeds[seed_info.crop_name] = seed_info
        if seed_info.crop_name not in crops:
            crops[seed_info.crop_name] = parse_crop_page(seed_info.crop_name)
        time.sleep(0.05)

    rows = []
    for crop_name, seed_info in sorted(seeds.items()):
        crop_info = crops.get(crop_name)
        rows.append(
            {
                "name": crop_name,
                "seed_name": seed_info.seed_name,
                "seed_price": seed_info.seed_price,
                "seed_sources": seed_info.seed_sources,
                "base_price": crop_info.base_price if crop_info else None,
            }
        )

    OUT_PATH.write_text(json.dumps(rows, indent=2, sort_keys=True), encoding="utf-8")
    print(f"wrote {OUT_PATH} ({len(rows)} crops)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
