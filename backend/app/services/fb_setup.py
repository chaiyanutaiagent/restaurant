from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlannedDiningTable:
    name: str
    zone: str
    capacity: int
    sort_order: int


@dataclass(frozen=True)
class DiningTableZonePlan:
    zone_name: str
    table_name_prefix: str
    table_count: int
    table_capacity: int


def service_mode_for(has_tables: bool) -> str:
    """Keep the legacy storage contract while exposing one unified F&B setup."""
    return "both" if has_tables else "quick_service"


def normalize_table_prefix(prefix: str) -> str:
    normalized = " ".join(prefix.split())
    return normalized or "โต๊ะ"


def normalize_table_zone(zone: str) -> str:
    normalized = " ".join(zone.split())
    return normalized or "โซนทั่วไป"


def plan_dining_tables(
    *,
    prefix: str,
    count: int,
    capacity: int,
    zone: str = "โซนทั่วไป",
    sort_order_start: int = 1,
) -> list[PlannedDiningTable]:
    normalized_prefix = normalize_table_prefix(prefix)
    normalized_zone = normalize_table_zone(zone)
    return [
        PlannedDiningTable(
            name=f"{normalized_prefix} {index}",
            zone=normalized_zone,
            capacity=capacity,
            sort_order=sort_order_start + index - 1,
        )
        for index in range(1, count + 1)
    ]


def plan_dining_table_zones(
    zones: list[DiningTableZonePlan],
    *,
    max_tables: int = 100,
) -> list[PlannedDiningTable]:
    if not zones:
        raise ValueError("ร้านที่มีโต๊ะต้องกำหนดอย่างน้อย 1 โซน")

    normalized_zone_names: set[str] = set()
    planned_names: set[str] = set()
    plan: list[PlannedDiningTable] = []

    for zone in zones:
        if zone.table_count < 1 or zone.table_count > max_tables:
            raise ValueError("แต่ละโซนต้องมีโต๊ะ 1 ถึง 100 โต๊ะ")
        if zone.table_capacity < 1 or zone.table_capacity > 100:
            raise ValueError("จำนวนที่นั่งต่อโต๊ะต้องอยู่ระหว่าง 1 ถึง 100")

        normalized_zone = normalize_table_zone(zone.zone_name)
        zone_key = normalized_zone.casefold()
        if zone_key in normalized_zone_names:
            raise ValueError(f'ชื่อโซน "{normalized_zone}" ซ้ำกัน')
        normalized_zone_names.add(zone_key)

        zone_plan = plan_dining_tables(
            prefix=zone.table_name_prefix,
            count=zone.table_count,
            capacity=zone.table_capacity,
            zone=normalized_zone,
            sort_order_start=len(plan) + 1,
        )
        for table in zone_plan:
            table_key = table.name.casefold()
            if table_key in planned_names:
                raise ValueError(
                    f'ชื่อโต๊ะ "{table.name}" ซ้ำกัน กรุณาเปลี่ยนคำนำหน้าชื่อโต๊ะ'
                )
            planned_names.add(table_key)
            plan.append(table)

    if len(plan) > max_tables:
        raise ValueError(f"สร้างโต๊ะได้รวมไม่เกิน {max_tables} โต๊ะ")
    return plan
