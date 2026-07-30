from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
import uuid

from app.models.hr import SalaryComponent

TWOPLACES = Decimal("0.01")
SSO_RATE = Decimal("0.05")
SSO_CEILING = Decimal("15000")
SSO_MAX = Decimal("750")


def q2(value: Decimal | int | float | str | None) -> Decimal:
    return Decimal(value or 0).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def calc_sso(monthly_gross: Decimal) -> Decimal:
    base = min(monthly_gross, SSO_CEILING)
    return min(q2(base * SSO_RATE), SSO_MAX)


def calc_annual_pit(
    annual_taxable_income: Decimal,
    personal_allowance: Decimal = Decimal("60000"),
    employment_allowance_rate: Decimal = Decimal("0.50"),
    employment_allowance_max: Decimal = Decimal("100000"),
) -> Decimal:
    employment_al = min(annual_taxable_income * employment_allowance_rate, employment_allowance_max)
    net = max(Decimal("0"), annual_taxable_income - employment_al - personal_allowance)

    brackets: list[tuple[Decimal | None, Decimal]] = [
        (Decimal("150000"), Decimal("0")),
        (Decimal("150000"), Decimal("0.05")),
        (Decimal("200000"), Decimal("0.10")),
        (Decimal("250000"), Decimal("0.15")),
        (Decimal("250000"), Decimal("0.20")),
        (Decimal("1000000"), Decimal("0.25")),
        (Decimal("3000000"), Decimal("0.30")),
        (None, Decimal("0.35")),
    ]

    tax = Decimal("0")
    for band, rate in brackets:
        if net <= 0:
            break
        taxable = net if band is None else min(net, band)
        tax += taxable * rate
        net -= taxable
    return q2(tax)


def calc_monthly_pit_withholding(
    month: int,
    monthly_taxable: Decimal,
    ytd_taxable: Decimal,
    ytd_pit_paid: Decimal,
    personal_allowance: Decimal = Decimal("60000"),
) -> Decimal:
    projected_annual = (ytd_taxable + monthly_taxable) / Decimal(month) * Decimal("12")
    annual_pit = calc_annual_pit(projected_annual, personal_allowance)
    remaining = Decimal(13 - month)
    monthly = max(Decimal("0"), (annual_pit - ytd_pit_paid) / remaining)
    return q2(monthly)


@dataclass
class PayrollCalculation:
    employee_id: uuid.UUID
    base_salary: Decimal
    earnings: dict[str, Decimal]
    gross_taxable: Decimal
    gross_sso_base: Decimal
    sso_employee: Decimal
    sso_employer: Decimal
    pit_withheld: Decimal
    other_deductions: dict[str, Decimal]
    total_deductions: Decimal
    net_pay: Decimal


def calculate_payroll_item(
    employee_id: uuid.UUID,
    base_salary: Decimal,
    variable_earnings: dict[str, Decimal],
    variable_deductions: dict[str, Decimal],
    components: list[SalaryComponent],
    month: int,
    ytd_taxable: Decimal,
    ytd_pit_paid: Decimal,
    personal_allowance: Decimal = Decimal("60000"),
) -> PayrollCalculation:
    component_map = {component.code: component for component in components}
    earnings: dict[str, Decimal] = {"BASE": q2(base_salary)}
    earnings.update({code: q2(amount) for code, amount in variable_earnings.items() if q2(amount) != Decimal("0")})
    deductions = {code: q2(amount) for code, amount in variable_deductions.items() if q2(amount) != Decimal("0")}

    gross_taxable = Decimal("0")
    gross_sso_base = Decimal("0")
    for code, amount in earnings.items():
        component = component_map.get(code)
        if code == "BASE":
            gross_taxable += amount
            gross_sso_base += amount
            continue
        if component is None or component.component_type != "earning":
            continue
        if component.is_taxable:
            gross_taxable += amount
        if component.is_sso_base:
            gross_sso_base += amount

    sso_employee = calc_sso(gross_sso_base)
    sso_employer = calc_sso(gross_sso_base)
    pit_withheld = calc_monthly_pit_withholding(
        month=month,
        monthly_taxable=q2(gross_taxable),
        ytd_taxable=q2(ytd_taxable),
        ytd_pit_paid=q2(ytd_pit_paid),
        personal_allowance=q2(personal_allowance),
    )

    other_deductions = {code: amount for code, amount in deductions.items()}
    total_deductions = q2(sum(other_deductions.values(), Decimal("0")) + sso_employee + pit_withheld)
    gross_total = q2(sum(earnings.values(), Decimal("0")))
    net_pay = q2(gross_total - total_deductions)

    return PayrollCalculation(
        employee_id=employee_id,
        base_salary=q2(base_salary),
        earnings=earnings,
        gross_taxable=q2(gross_taxable),
        gross_sso_base=q2(gross_sso_base),
        sso_employee=sso_employee,
        sso_employer=sso_employer,
        pit_withheld=pit_withheld,
        other_deductions=other_deductions,
        total_deductions=total_deductions,
        net_pay=net_pay,
    )
