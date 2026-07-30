from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
import math
import random
import string
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.logistics import ShippingRate

TWOPLACES = Decimal("0.01")


def _q2(value: Decimal | int | float | str | None) -> Decimal:
    return Decimal(value or 0).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _match_rate(rates: list["ShippingRate"], weight_grams: int, zone: str) -> "ShippingRate | None":
    zone = (zone or "all").lower()
    zone_matches = [rate for rate in rates if (rate.zone or "all").lower() == zone]
    fallback_matches = [rate for rate in rates if (rate.zone or "all").lower() == "all"]
    candidates = zone_matches or fallback_matches
    for rate in sorted(candidates, key=lambda item: int(item.min_weight_g or 0), reverse=True):
        max_weight = item_max = rate.max_weight_g
        if weight_grams < int(rate.min_weight_g or 0):
            continue
        if max_weight is not None and weight_grams > max_weight:
            continue
        return rate
    return None


def calc_shipping_cost(
    rates: list["ShippingRate"],
    weight_grams: int,
    zone: str = "all",
    is_cod: bool = False,
) -> Decimal:
    rate = _match_rate(rates, weight_grams, zone)
    if rate is None:
        raise ValueError("No shipping rate found")

    total = Decimal(rate.base_rate or 0)
    per_kg_rate = Decimal(rate.per_kg_rate or 0)
    if per_kg_rate > 0 and weight_grams > 1000:
        extra_kg = math.ceil((weight_grams - 1000) / 1000)
        total += Decimal(extra_kg) * per_kg_rate
    if is_cod:
        total += Decimal(rate.cod_fee or 0)
    return _q2(total)


def estimate_all_carriers(
    all_rates: dict[str, list["ShippingRate"]],
    weight_grams: int,
    zone: str = "all",
    is_cod: bool = False,
) -> list[dict]:
    estimates: list[dict] = []
    for carrier_code, rates in all_rates.items():
        rate = _match_rate(rates, weight_grams, zone)
        if rate is None:
            continue
        estimates.append(
            {
                "carrier_code": carrier_code,
                "carrier_name": rate.carrier.name,
                "service_name": rate.service_name,
                "cost": calc_shipping_cost(rates, weight_grams, zone, is_cod),
                "cod_fee": _q2(rate.cod_fee if is_cod else 0),
            }
        )
    return sorted(estimates, key=lambda item: (Decimal(item["cost"]), item["carrier_code"]))


def generate_tracking_number(carrier_code: str) -> str:
    if carrier_code == "THPOST":
        return "EE" + "".join(random.choices(string.digits, k=9)) + "TH"
    if carrier_code == "FLASH":
        return "TH" + "".join(random.choices(string.digits, k=12))
    if carrier_code == "JT":
        return "JT" + "".join(random.choices(string.digits, k=12))
    if carrier_code == "KERRY":
        return "KR" + "".join(random.choices(string.digits, k=10))
    return "TRK" + "".join(random.choices(string.digits, k=10))
