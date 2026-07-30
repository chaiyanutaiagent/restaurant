from __future__ import annotations

from datetime import date
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.hr import LeaveType, PublicHoliday, SalaryComponent, WorkSchedule

DEFAULT_COMPONENTS: list[dict[str, object]] = [
    {"code": "BASE", "name": "เงินเดือน", "component_type": "earning", "is_taxable": True, "is_sso_base": True, "is_fixed": False, "is_system": False, "sort_order": 1},
    {"code": "POS_AL", "name": "ค่าตำแหน่ง", "component_type": "earning", "is_taxable": True, "is_sso_base": False, "is_fixed": False, "is_system": False, "sort_order": 2},
    {"code": "OT", "name": "ค่าล่วงเวลา", "component_type": "earning", "is_taxable": True, "is_sso_base": True, "is_fixed": False, "is_system": False, "sort_order": 3},
    {"code": "BONUS", "name": "โบนัส", "component_type": "earning", "is_taxable": True, "is_sso_base": False, "is_fixed": False, "is_system": False, "sort_order": 4},
    {"code": "TRANS", "name": "ค่าเดินทาง", "component_type": "earning", "is_taxable": False, "is_sso_base": False, "is_fixed": False, "is_system": False, "sort_order": 5},
    {"code": "MEAL", "name": "ค่าอาหาร", "component_type": "earning", "is_taxable": False, "is_sso_base": False, "is_fixed": False, "is_system": False, "sort_order": 6},
    {"code": "SSO_EE", "name": "ประกันสังคม (พนักงาน)", "component_type": "deduction", "is_taxable": False, "is_sso_base": False, "is_fixed": False, "is_system": True, "sort_order": 10},
    {"code": "PIT", "name": "ภาษีเงินได้ (หัก ณ ที่จ่าย)", "component_type": "deduction", "is_taxable": False, "is_sso_base": False, "is_fixed": False, "is_system": True, "sort_order": 11},
    {"code": "ABSENT", "name": "หักขาดงาน", "component_type": "deduction", "is_taxable": False, "is_sso_base": False, "is_fixed": False, "is_system": False, "sort_order": 12},
    {"code": "LOAN", "name": "หักเงินกู้", "component_type": "deduction", "is_taxable": False, "is_sso_base": False, "is_fixed": False, "is_system": False, "sort_order": 13},
]

DEFAULT_LEAVE_TYPES: list[dict[str, object]] = [
    {"code": "SICK", "name": "ลาป่วย", "name_en": "Sick Leave", "days_per_year": 30, "is_paid": True, "carry_over": False, "requires_doc": True, "gender_restrict": None, "is_system": True},
    {"code": "ANNUAL", "name": "ลาพักร้อน", "name_en": "Annual Leave", "days_per_year": 6, "is_paid": True, "carry_over": True, "max_carry_over": 6, "gender_restrict": None, "is_system": True},
    {"code": "PERSONAL", "name": "ลากิจ", "name_en": "Personal Leave", "days_per_year": 3, "is_paid": True, "carry_over": False, "gender_restrict": None, "is_system": True},
    {"code": "MATERNITY", "name": "ลาคลอด", "name_en": "Maternity Leave", "days_per_year": 98, "is_paid": True, "carry_over": False, "gender_restrict": "female", "is_system": True},
    {"code": "ORDINATION", "name": "ลาบวช", "name_en": "Ordination Leave", "days_per_year": 15, "is_paid": True, "carry_over": False, "gender_restrict": "male", "is_system": True},
    {"code": "UNPAID", "name": "ลาไม่รับค่าจ้าง", "name_en": "Unpaid Leave", "days_per_year": 0, "is_paid": False, "carry_over": False, "gender_restrict": None, "is_system": False},
]

THAI_PUBLIC_HOLIDAYS_2026: list[tuple[str, str, str]] = [
    ("2026-01-01", "วันขึ้นปีใหม่", "New Year's Day"),
    ("2026-02-06", "วันมาฆบูชา", "Makha Bucha Day"),
    ("2026-04-06", "วันจักรี", "Chakri Memorial Day"),
    ("2026-04-13", "วันสงกรานต์", "Songkran Festival"),
    ("2026-04-14", "วันสงกรานต์", "Songkran Festival"),
    ("2026-04-15", "วันสงกรานต์", "Songkran Festival"),
    ("2026-05-01", "วันแรงงานแห่งชาติ", "Labour Day"),
    ("2026-05-04", "วันฉัตรมงคล", "Coronation Day"),
    ("2026-05-05", "วันวิสาขบูชา", "Visakha Bucha Day"),
    ("2026-06-03", "วันเฉลิมพระชนมพรรษา สมเด็จพระราชินี", "Queen's Birthday"),
    ("2026-07-28", "วันเฉลิมพระชนมพรรษา รัชกาลที่ 10", "King's Birthday"),
    ("2026-08-12", "วันแม่แห่งชาติ", "Mother's Day"),
    ("2026-10-13", "วันนวมินทรมหาราช", "Navamindra Maharaj Day"),
    ("2026-10-23", "วันปิยมหาราช", "Chulalongkorn Day"),
    ("2026-12-05", "วันพ่อแห่งชาติ", "Father's Day"),
    ("2026-12-10", "วันรัฐธรรมนูญ", "Constitution Day"),
    ("2026-12-31", "วันสิ้นปี", "New Year's Eve"),
]


async def seed_default_hr_components(db: AsyncSession, company_id: uuid.UUID) -> None:
    values = [{"company_id": company_id, "is_active": True, **component} for component in DEFAULT_COMPONENTS]
    statement = insert(SalaryComponent).values(values)
    statement = statement.on_conflict_do_nothing(index_elements=["company_id", "code"])
    await db.execute(statement)


async def seed_default_leave_types(db: AsyncSession, company_id: uuid.UUID) -> None:
    values = [
        {
            "company_id": company_id,
            "is_active": True,
            "max_carry_over": 0,
            "requires_doc": False,
            **leave_type,
        }
        for leave_type in DEFAULT_LEAVE_TYPES
    ]
    statement = insert(LeaveType).values(values)
    statement = statement.on_conflict_do_nothing(index_elements=["company_id", "code"])
    await db.execute(statement)


async def seed_default_work_schedule(db: AsyncSession, company_id: uuid.UUID, branch_id: uuid.UUID) -> WorkSchedule:
    existing = await db.scalar(
        select(WorkSchedule).where(
            WorkSchedule.company_id == company_id,
            WorkSchedule.name == "ปกติ 08:00-17:00",
        )
    )
    if existing is not None:
        return existing

    del branch_id
    schedule = WorkSchedule(
        company_id=company_id,
        name="ปกติ 08:00-17:00",
        work_days=[1, 2, 3, 4, 5],
        start_time="08:00",
        end_time="17:00",
        break_minutes=60,
        is_default=True,
        is_active=True,
    )
    db.add(schedule)
    return schedule


async def seed_public_holidays_2026(db: AsyncSession, company_id: uuid.UUID) -> None:
    values = [
        {
            "company_id": company_id,
            "holiday_date": date.fromisoformat(holiday_date),
            "name": name,
            "name_en": name_en,
            "is_recurring": True,
        }
        for holiday_date, name, name_en in THAI_PUBLIC_HOLIDAYS_2026
    ]
    statement = insert(PublicHoliday).values(values)
    statement = statement.on_conflict_do_nothing(index_elements=["company_id", "holiday_date"])
    await db.execute(statement)
