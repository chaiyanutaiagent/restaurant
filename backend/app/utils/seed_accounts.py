from __future__ import annotations

from collections.abc import Sequence
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.accounting import Account

ACCOUNTS: list[dict[str, object]] = [
    {"code": "1000", "name": "สินทรัพย์", "account_type": "asset", "account_subtype": "current_asset", "is_header": True, "is_system": True, "parent_code": None},
    {"code": "1100", "name": "สินทรัพย์หมุนเวียน", "account_type": "asset", "account_subtype": "current_asset", "is_header": True, "is_system": True, "parent_code": "1000"},
    {"code": "1101", "name": "เงินสด", "account_type": "asset", "account_subtype": "current_asset", "is_header": False, "is_system": True, "parent_code": "1100"},
    {"code": "1102", "name": "เงินฝากธนาคาร", "account_type": "asset", "account_subtype": "current_asset", "is_header": False, "is_system": True, "parent_code": "1100"},
    {"code": "1103", "name": "ลูกหนี้การค้า", "account_type": "asset", "account_subtype": "current_asset", "is_header": False, "is_system": True, "parent_code": "1100"},
    {"code": "1104", "name": "ภาษีซื้อ (Input VAT)", "account_type": "asset", "account_subtype": "current_asset", "is_header": False, "is_system": True, "parent_code": "1100"},
    {"code": "1105", "name": "สินค้าคงเหลือ", "account_type": "asset", "account_subtype": "current_asset", "is_header": False, "is_system": True, "parent_code": "1100"},
    {"code": "1106", "name": "รายได้ค้างรับ", "account_type": "asset", "account_subtype": "current_asset", "is_header": False, "is_system": False, "parent_code": "1100"},
    {"code": "1200", "name": "สินทรัพย์ไม่หมุนเวียน", "account_type": "asset", "account_subtype": "fixed_asset", "is_header": True, "is_system": False, "parent_code": "1000"},
    {"code": "1201", "name": "ที่ดิน", "account_type": "asset", "account_subtype": "fixed_asset", "is_header": False, "is_system": False, "parent_code": "1200"},
    {"code": "1202", "name": "อาคารและอุปกรณ์", "account_type": "asset", "account_subtype": "fixed_asset", "is_header": False, "is_system": False, "parent_code": "1200"},
    {"code": "1203", "name": "ค่าเสื่อมราคาสะสม", "account_type": "asset", "account_subtype": "fixed_asset", "is_header": False, "is_system": False, "parent_code": "1200"},
    {"code": "2000", "name": "หนี้สิน", "account_type": "liability", "account_subtype": "current_liability", "is_header": True, "is_system": True, "parent_code": None},
    {"code": "2100", "name": "หนี้สินหมุนเวียน", "account_type": "liability", "account_subtype": "current_liability", "is_header": True, "is_system": True, "parent_code": "2000"},
    {"code": "2101", "name": "เจ้าหนี้การค้า", "account_type": "liability", "account_subtype": "current_liability", "is_header": False, "is_system": True, "parent_code": "2100"},
    {"code": "2102", "name": "ภาษีขาย (Output VAT)", "account_type": "liability", "account_subtype": "current_liability", "is_header": False, "is_system": True, "parent_code": "2100"},
    {"code": "2103", "name": "ภาษีหัก ณ ที่จ่ายค้างจ่าย", "account_type": "liability", "account_subtype": "current_liability", "is_header": False, "is_system": True, "parent_code": "2100"},
    {"code": "2104", "name": "ค่าใช้จ่ายค้างจ่าย", "account_type": "liability", "account_subtype": "current_liability", "is_header": False, "is_system": False, "parent_code": "2100"},
    {"code": "2105", "name": "เงินกู้ระยะสั้น", "account_type": "liability", "account_subtype": "current_liability", "is_header": False, "is_system": False, "parent_code": "2100"},
    {"code": "2200", "name": "หนี้สินระยะยาว", "account_type": "liability", "account_subtype": "long_term_liability", "is_header": True, "is_system": False, "parent_code": "2000"},
    {"code": "2201", "name": "เงินกู้ระยะยาว", "account_type": "liability", "account_subtype": "long_term_liability", "is_header": False, "is_system": False, "parent_code": "2200"},
    {"code": "3000", "name": "ส่วนของผู้ถือหุ้น", "account_type": "equity", "account_subtype": "capital", "is_header": True, "is_system": True, "parent_code": None},
    {"code": "3001", "name": "ทุนจดทะเบียน", "account_type": "equity", "account_subtype": "capital", "is_header": False, "is_system": True, "parent_code": "3000"},
    {"code": "3002", "name": "กำไรสะสม", "account_type": "equity", "account_subtype": "retained_earnings", "is_header": False, "is_system": True, "parent_code": "3000"},
    {"code": "3003", "name": "กำไร(ขาดทุน) ปีปัจจุบัน", "account_type": "equity", "account_subtype": "retained_earnings", "is_header": False, "is_system": True, "parent_code": "3000"},
    {"code": "4000", "name": "รายได้", "account_type": "revenue", "account_subtype": "sales", "is_header": True, "is_system": True, "parent_code": None},
    {"code": "4001", "name": "รายได้จากการขายสินค้า", "account_type": "revenue", "account_subtype": "sales", "is_header": False, "is_system": True, "parent_code": "4000"},
    {"code": "4002", "name": "รายได้จากการขายบริการ", "account_type": "revenue", "account_subtype": "sales", "is_header": False, "is_system": False, "parent_code": "4000"},
    {"code": "4003", "name": "ส่วนลดรับ", "account_type": "revenue", "account_subtype": "other_revenue", "is_header": False, "is_system": False, "parent_code": "4000"},
    {"code": "4004", "name": "รายได้อื่น", "account_type": "revenue", "account_subtype": "other_revenue", "is_header": False, "is_system": False, "parent_code": "4000"},
    {"code": "5000", "name": "ต้นทุนขาย", "account_type": "expense", "account_subtype": "cost_of_goods", "is_header": True, "is_system": True, "parent_code": None},
    {"code": "5001", "name": "ต้นทุนสินค้าขาย", "account_type": "expense", "account_subtype": "cost_of_goods", "is_header": False, "is_system": True, "parent_code": "5000"},
    {"code": "5002", "name": "ต้นทุนการผลิต", "account_type": "expense", "account_subtype": "cost_of_goods", "is_header": False, "is_system": False, "parent_code": "5000"},
    {"code": "6000", "name": "ค่าใช้จ่ายดำเนินงาน", "account_type": "expense", "account_subtype": "operating", "is_header": True, "is_system": False, "parent_code": None},
    {"code": "6001", "name": "เงินเดือนและค่าแรง", "account_type": "expense", "account_subtype": "operating", "is_header": False, "is_system": False, "parent_code": "6000"},
    {"code": "6002", "name": "ค่าเช่า", "account_type": "expense", "account_subtype": "operating", "is_header": False, "is_system": False, "parent_code": "6000"},
    {"code": "6003", "name": "ค่าสาธารณูปโภค", "account_type": "expense", "account_subtype": "operating", "is_header": False, "is_system": False, "parent_code": "6000"},
    {"code": "6004", "name": "ค่าวัสดุสำนักงาน", "account_type": "expense", "account_subtype": "operating", "is_header": False, "is_system": False, "parent_code": "6000"},
    {"code": "6005", "name": "ค่าเสื่อมราคา", "account_type": "expense", "account_subtype": "operating", "is_header": False, "is_system": False, "parent_code": "6000"},
    {"code": "6006", "name": "ค่าใช้จ่ายอื่น", "account_type": "expense", "account_subtype": "other_expense", "is_header": False, "is_system": False, "parent_code": "6000"},
]


def _normal_balance(account_type: str) -> str:
    return "debit" if account_type in {"asset", "expense"} else "credit"


async def _existing_accounts_by_code(db: AsyncSession, company_id: uuid.UUID) -> dict[str, Account]:
    rows = (
        await db.scalars(
            select(Account).where(Account.company_id == company_id, Account.deleted_at.is_(None))
        )
    ).all()
    return {account.code: account for account in rows}


async def seed_default_accounts(db: AsyncSession, company_id: uuid.UUID) -> None:
    existing_accounts = await _existing_accounts_by_code(db, company_id)
    sorted_accounts: Sequence[dict[str, object]] = sorted(ACCOUNTS, key=lambda item: str(item["code"]))

    for item in sorted_accounts:
        code = str(item["code"])
        parent_code = item.get("parent_code")
        parent_id = existing_accounts[parent_code].id if parent_code else None
        stmt = (
            insert(Account)
            .values(
                company_id=company_id,
                parent_id=parent_id,
                code=code,
                name=str(item["name"]),
                account_type=str(item["account_type"]),
                account_subtype=str(item["account_subtype"]) if item.get("account_subtype") else None,
                normal_balance=_normal_balance(str(item["account_type"])),
                is_header=bool(item["is_header"]),
                is_active=True,
                is_system=bool(item["is_system"]),
                sort_order=int(code),
            )
            .on_conflict_do_nothing(constraint="uq_accounts_company_id_code")
        )
        await db.execute(stmt)
        existing_accounts = await _existing_accounts_by_code(db, company_id)
