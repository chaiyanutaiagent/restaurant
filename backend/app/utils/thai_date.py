from __future__ import annotations

from datetime import datetime

MONTHS_TH = [
    "",
    "มกราคม",
    "กุมภาพันธ์",
    "มีนาคม",
    "เมษายน",
    "พฤษภาคม",
    "มิถุนายน",
    "กรกฎาคม",
    "สิงหาคม",
    "กันยายน",
    "ตุลาคม",
    "พฤศจิกายน",
    "ธันวาคม",
]

DAYS_TH = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"]


def to_thai_year(dt: datetime) -> int:
    return dt.year + 543


def format_thai_date(dt: datetime, fmt: str = "short") -> str:
    thai_year = to_thai_year(dt)
    if fmt == "short":
        return f"{dt.day:02d}/{dt.month:02d}/{thai_year}"
    if fmt == "long":
        return f"{dt.day} {MONTHS_TH[dt.month]} {thai_year}"
    if fmt == "full":
        return (
            f"วัน{DAYS_TH[dt.weekday()]}ที่ {dt.day} {MONTHS_TH[dt.month]} "
            f"พ.ศ. {thai_year} เวลา {dt:%H:%M} น."
        )
    raise ValueError("Unsupported Thai date format")
