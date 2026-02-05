from __future__ import annotations

from dataclasses import dataclass

from sim.config import EconomyConfig
from sim.crop_catalog import CropDef


@dataclass(frozen=True)
class ProcessedPrices:
    raw: int
    keg: int | None
    jar: int | None
    dried_batch: int | None


def raw_price(base_price: int, economy: EconomyConfig) -> int:
    price = base_price * economy.fruit_quality_multiplier
    if economy.tiller:
        price *= 1.1
    return int(price)


def keg_price(crop: CropDef, economy: EconomyConfig) -> int | None:
    if crop.base_price is None:
        return None
    if crop.category == "fruit":
        price = crop.base_price * 3
    elif crop.category == "vegetable":
        price = crop.base_price * 2.25
    else:
        return None
    price *= economy.wine_quality_multiplier
    if economy.artisan:
        price *= 1.4
    return int(price)


def jar_price(crop: CropDef, economy: EconomyConfig) -> int | None:
    if crop.base_price is None:
        return None
    if crop.category not in ("fruit", "vegetable"):
        return None
    price = (crop.base_price * 2) + 50
    if economy.artisan:
        price *= 1.4
    return int(price)


def dried_batch_price(crop: CropDef, economy: EconomyConfig) -> int | None:
    if crop.base_price is None:
        return None
    if crop.category != "fruit":
        return None
    price = (crop.base_price * 7.5) + 25
    if economy.artisan:
        price *= 1.4
    return int(price)


def processed_prices(crop: CropDef, economy: EconomyConfig) -> ProcessedPrices:
    if crop.base_price is None:
        return ProcessedPrices(raw=0, keg=None, jar=None, dried_batch=None)
    return ProcessedPrices(
        raw=raw_price(crop.base_price, economy),
        keg=keg_price(crop, economy),
        jar=jar_price(crop, economy),
        dried_batch=dried_batch_price(crop, economy),
    )
