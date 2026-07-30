from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP


def _parse_time(value: str) -> time:
    hour, minute = value.split(":", maxsplit=1)
    return time(hour=int(hour), minute=int(minute))


def _quantize_money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def is_working_day(date: date, work_days: list[int], holiday_dates: set[date]) -> bool:
    return date.isoweekday() in work_days and date not in holiday_dates


def count_leave_days(start_date: date, end_date: date, work_days: list[int], holiday_dates: set[date]) -> Decimal:
    count = Decimal("0")
    current = start_date
    while current <= end_date:
        if is_working_day(current, work_days, holiday_dates):
            count += Decimal("1")
        current += timedelta(days=1)
    return count


def calc_ot(
    clock_in: datetime,
    clock_out: datetime,
    schedule_start: str,
    schedule_end: str,
    break_minutes: int,
    is_holiday: bool,
    hourly_rate: Decimal,
) -> tuple[int, Decimal, Decimal]:
    ot_rate = Decimal("2.0") if is_holiday else Decimal("1.5")
    work_start = datetime.combine(clock_in.date(), _parse_time(schedule_start), tzinfo=clock_in.tzinfo)
    work_end = datetime.combine(clock_in.date(), _parse_time(schedule_end), tzinfo=clock_in.tzinfo)

    if is_holiday:
        worked_minutes = max(int((clock_out - clock_in).total_seconds() // 60) - break_minutes, 0)
        ot_minutes = worked_minutes
    else:
        ot_minutes = max(int((clock_out - work_end).total_seconds() // 60), 0)
        if clock_in > work_end:
            ot_minutes = max(int((clock_out - clock_in).total_seconds() // 60), 0)
        if clock_out <= work_end or clock_out <= work_start:
            ot_minutes = 0

    ot_hours = Decimal(ot_minutes) / Decimal("60")
    ot_amount = _quantize_money(ot_hours * hourly_rate * ot_rate)
    return ot_minutes, ot_rate, ot_amount


def calc_hourly_rate(monthly_salary: Decimal) -> Decimal:
    return _quantize_money(monthly_salary / Decimal("26") / Decimal("8"))


def is_late(clock_in: datetime, schedule_start: str, grace_minutes: int = 5) -> tuple[bool, int]:
    scheduled = datetime.combine(clock_in.date(), _parse_time(schedule_start), tzinfo=clock_in.tzinfo)
    late_minutes = max(int((clock_in - scheduled).total_seconds() // 60), 0)
    return late_minutes > grace_minutes, late_minutes
