from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.branch import Branch
from app.models.company import Company
from app.models.tax_settings import BranchTaxProfile, CompanyTaxProfile, TaxRateRule
from app.schemas.tax_settings import (
    BranchTaxProfileRead,
    BranchTaxProfileUpdate,
    CompanyTaxProfileRead,
    CompanyTaxProfileUpdate,
    TaxRateRuleCreate,
    TaxRateRuleRead,
    TaxRateRuleUpdate,
    TaxSettingsRead,
    validate_tax_rule_values,
)


def tax_periods_overlap(
    start_a: date,
    end_a: date | None,
    start_b: date,
    end_b: date | None,
) -> bool:
    return (end_a is None or start_b <= end_a) and (end_b is None or start_a <= end_b)


def _json_value(value: Any) -> Any:
    if isinstance(value, (date, Decimal, uuid.UUID)):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return value


class TaxSettingsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_settings(self, company_id: uuid.UUID) -> TaxSettingsRead:
        company = await self._get_company(company_id)
        profile = await self.db.scalar(
            select(CompanyTaxProfile).where(CompanyTaxProfile.company_id == company_id)
        )
        branches = (
            await self.db.scalars(
                select(Branch)
                .where(Branch.company_id == company_id, Branch.deleted_at.is_(None))
                .order_by(Branch.sort_order.asc(), Branch.name.asc())
            )
        ).all()
        branch_profiles = (
            await self.db.scalars(
                select(BranchTaxProfile).where(BranchTaxProfile.company_id == company_id)
            )
        ).all()
        branch_profile_by_id = {item.branch_id: item for item in branch_profiles}
        rates = (
            await self.db.scalars(
                select(TaxRateRule)
                .where(TaxRateRule.company_id == company_id)
                .order_by(TaxRateRule.effective_from.desc(), TaxRateRule.code.asc())
            )
        ).all()
        return TaxSettingsRead(
            company=self._company_read(company, profile),
            branches=[self._branch_read(branch, branch_profile_by_id.get(branch.id)) for branch in branches],
            rates=[TaxRateRuleRead.model_validate(item) for item in rates],
        )

    async def update_company_profile(
        self,
        company_id: uuid.UUID,
        actor_id: uuid.UUID,
        data: CompanyTaxProfileUpdate,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> CompanyTaxProfileRead:
        company = await self._get_company(company_id)
        profile = await self.db.scalar(
            select(CompanyTaxProfile)
            .where(CompanyTaxProfile.company_id == company_id)
            .with_for_update()
        )
        old_value = self._company_snapshot(company, profile)
        if profile is None:
            profile = CompanyTaxProfile(company_id=company_id)
            self.db.add(profile)
            await self.db.flush()

        for field in (
            "legal_name",
            "tax_id",
            "vat_registered",
            "vat_registration_date",
            "registered_address",
            "default_price_vat_type",
            "default_vat_rate",
            "vat_filing_mode",
            "consolidated_filing_approved",
        ):
            setattr(profile, field, getattr(data, field))

        # Existing POS/accounting flows still read these compatibility fields.
        company.tax_id = data.tax_id
        company.vat_registered = data.vat_registered
        if data.registered_address:
            company.address = data.registered_address

        await self._seed_rates_if_empty(company_id, data)
        new_value = self._company_snapshot(company, profile)
        self._audit(
            company_id,
            None,
            actor_id,
            "tax.settings.company.updated",
            "CompanyTaxProfile",
            profile.id,
            old_value,
            {**new_value, "reason": data.reason},
            ip_address,
            user_agent,
        )
        await self.db.commit()
        await self.db.refresh(profile)
        return self._company_read(company, profile)

    async def update_branch_profile(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID,
        actor_id: uuid.UUID,
        data: BranchTaxProfileUpdate,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> BranchTaxProfileRead:
        branch = await self._get_branch(company_id, branch_id)
        company_profile = await self.db.scalar(
            select(CompanyTaxProfile.id).where(CompanyTaxProfile.company_id == company_id)
        )
        if company_profile is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="ตั้งค่าภาษีบริษัทก่อนตั้งค่าภาษีสาขา",
            )
        profile = await self.db.scalar(
            select(BranchTaxProfile)
            .where(BranchTaxProfile.company_id == company_id, BranchTaxProfile.branch_id == branch_id)
            .with_for_update()
        )
        if data.is_head_office:
            existing_head = await self.db.scalar(
                select(BranchTaxProfile.id).where(
                    BranchTaxProfile.company_id == company_id,
                    BranchTaxProfile.is_head_office.is_(True),
                    BranchTaxProfile.branch_id != branch_id,
                )
            )
            if existing_head is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="บริษัทมีสำนักงานใหญ่ทางภาษีแล้ว",
                )
        duplicate_code = await self.db.scalar(
            select(BranchTaxProfile.id).where(
                BranchTaxProfile.company_id == company_id,
                BranchTaxProfile.tax_branch_code == data.tax_branch_code,
                BranchTaxProfile.branch_id != branch_id,
            )
        )
        if duplicate_code is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="รหัสสาขาภาษีนี้ถูกใช้โดยสาขาอื่นแล้ว",
            )
        old_value = self._branch_snapshot(branch, profile)
        if profile is None:
            profile = BranchTaxProfile(company_id=company_id, branch_id=branch_id)
            self.db.add(profile)
        for field in (
            "tax_branch_code",
            "is_head_office",
            "legal_name",
            "registered_address",
            "vat_registration_date",
            "filing_enabled",
            "effective_from",
            "effective_to",
        ):
            setattr(profile, field, getattr(data, field))
        await self.db.flush()
        new_value = self._branch_snapshot(branch, profile)
        self._audit(
            company_id,
            branch_id,
            actor_id,
            "tax.settings.branch.updated",
            "BranchTaxProfile",
            profile.id,
            old_value,
            {**new_value, "reason": data.reason},
            ip_address,
            user_agent,
        )
        await self.db.commit()
        await self.db.refresh(profile)
        return self._branch_read(branch, profile)

    async def create_rate(
        self,
        company_id: uuid.UUID,
        actor_id: uuid.UUID,
        data: TaxRateRuleCreate,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> TaxRateRuleRead:
        await self._get_company(company_id)
        await self._validate_rate_period(
            company_id,
            data.code,
            data.effective_from,
            data.effective_to,
            data.is_default,
        )
        rule = TaxRateRule(
            company_id=company_id,
            **data.model_dump(exclude={"reason"}),
        )
        self.db.add(rule)
        await self.db.flush()
        self._audit(
            company_id,
            None,
            actor_id,
            "tax.settings.rate.created",
            "TaxRateRule",
            rule.id,
            None,
            {**self._rate_snapshot(rule), "reason": data.reason},
            ip_address,
            user_agent,
        )
        await self.db.commit()
        await self.db.refresh(rule)
        return TaxRateRuleRead.model_validate(rule)

    async def update_rate(
        self,
        company_id: uuid.UUID,
        rule_id: uuid.UUID,
        actor_id: uuid.UUID,
        data: TaxRateRuleUpdate,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> TaxRateRuleRead:
        rule = await self.db.scalar(
            select(TaxRateRule)
            .where(TaxRateRule.id == rule_id, TaxRateRule.company_id == company_id)
            .with_for_update()
        )
        if rule is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ไม่พบอัตราภาษี")
        changes = data.model_dump(exclude_unset=True, exclude={"reason"})
        if changes.get("is_active") is False:
            changes["is_default"] = False
        merged = {
            "tax_category": changes.get("tax_category", rule.tax_category),
            "rate": Decimal(changes.get("rate", rule.rate)),
            "price_vat_type": changes.get("price_vat_type", rule.price_vat_type),
            "effective_from": changes.get("effective_from", rule.effective_from),
            "effective_to": changes.get("effective_to", rule.effective_to),
            "is_default": changes.get("is_default", rule.is_default),
            "is_active": changes.get("is_active", rule.is_active),
        }
        try:
            validate_tax_rule_values(
                merged["tax_category"],
                merged["rate"],
                merged["price_vat_type"],
                merged["effective_from"],
                merged["effective_to"],
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        if merged["is_active"]:
            await self._validate_rate_period(
                company_id,
                rule.code,
                merged["effective_from"],
                merged["effective_to"],
                merged["is_default"],
                exclude_id=rule.id,
            )
        old_value = self._rate_snapshot(rule)
        for field, value in changes.items():
            setattr(rule, field, value)
        self._audit(
            company_id,
            None,
            actor_id,
            "tax.settings.rate.updated",
            "TaxRateRule",
            rule.id,
            old_value,
            {**self._rate_snapshot(rule), "reason": data.reason},
            ip_address,
            user_agent,
        )
        await self.db.commit()
        await self.db.refresh(rule)
        return TaxRateRuleRead.model_validate(rule)

    async def _seed_rates_if_empty(
        self, company_id: uuid.UUID, data: CompanyTaxProfileUpdate
    ) -> None:
        existing = await self.db.scalar(
            select(TaxRateRule.id).where(TaxRateRule.company_id == company_id).limit(1)
        )
        if existing is not None:
            return
        rules: list[TaxRateRule] = []
        if data.default_price_vat_type != "exempt":
            rules.append(
                TaxRateRule(
                    company_id=company_id,
                    code="VAT_STANDARD",
                    name="VAT มาตรฐาน",
                    tax_category="standard",
                    rate=data.default_vat_rate,
                    price_vat_type=data.default_price_vat_type,
                    effective_from=data.effective_from,
                    is_default=True,
                    is_active=True,
                )
            )
        rules.extend(
            [
                TaxRateRule(
                    company_id=company_id,
                    code="VAT_ZERO",
                    name="VAT 0%",
                    tax_category="zero",
                    rate=Decimal("0"),
                    price_vat_type="excluded",
                    effective_from=data.effective_from,
                    is_default=False,
                    is_active=True,
                ),
                TaxRateRule(
                    company_id=company_id,
                    code="VAT_EXEMPT",
                    name="ยกเว้น VAT",
                    tax_category="exempt",
                    rate=Decimal("0"),
                    price_vat_type="exempt",
                    effective_from=data.effective_from,
                    is_default=data.default_price_vat_type == "exempt",
                    is_active=True,
                ),
            ]
        )
        self.db.add_all(rules)

    async def _validate_rate_period(
        self,
        company_id: uuid.UUID,
        code: str,
        effective_from: date,
        effective_to: date | None,
        is_default: bool,
        *,
        exclude_id: uuid.UUID | None = None,
    ) -> None:
        rows = (
            await self.db.scalars(
                select(TaxRateRule).where(
                    TaxRateRule.company_id == company_id,
                    TaxRateRule.is_active.is_(True),
                )
            )
        ).all()
        for row in rows:
            if row.id == exclude_id:
                continue
            overlaps = tax_periods_overlap(
                effective_from,
                effective_to,
                row.effective_from,
                row.effective_to,
            )
            if overlaps and row.code == code:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"ช่วงวันที่ของ {code} ซ้อนกับอัตราที่มีอยู่",
                )
            if overlaps and is_default and row.is_default:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="ช่วงวันที่นี้มีอัตราภาษีเริ่มต้นอยู่แล้ว",
                )

    async def _get_company(self, company_id: uuid.UUID) -> Company:
        company = await self.db.get(Company, company_id)
        if company is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ไม่พบบริษัท")
        return company

    async def _get_branch(self, company_id: uuid.UUID, branch_id: uuid.UUID) -> Branch:
        branch = await self.db.scalar(
            select(Branch).where(
                Branch.id == branch_id,
                Branch.company_id == company_id,
                Branch.deleted_at.is_(None),
            )
        )
        if branch is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ไม่พบสาขา")
        return branch

    @staticmethod
    def _company_read(company: Company, profile: CompanyTaxProfile | None) -> CompanyTaxProfileRead:
        return CompanyTaxProfileRead(
            id=profile.id if profile else None,
            configured=profile is not None,
            company_id=company.id,
            legal_name=(profile.legal_name if profile else None) or company.name,
            tax_id=(profile.tax_id if profile else None) or company.tax_id,
            vat_registered=profile.vat_registered if profile else company.vat_registered,
            vat_registration_date=profile.vat_registration_date if profile else None,
            registered_address=(profile.registered_address if profile else None) or company.address,
            default_price_vat_type=profile.default_price_vat_type if profile else "included",
            default_vat_rate=profile.default_vat_rate if profile else Decimal("7.00"),
            vat_filing_mode=profile.vat_filing_mode if profile else "separate",
            consolidated_filing_approved=profile.consolidated_filing_approved if profile else False,
            updated_at=profile.updated_at if profile else None,
        )

    @staticmethod
    def _branch_read(branch: Branch, profile: BranchTaxProfile | None) -> BranchTaxProfileRead:
        return BranchTaxProfileRead(
            id=profile.id if profile else None,
            configured=profile is not None,
            company_id=branch.company_id,
            branch_id=branch.id,
            branch_code=branch.code,
            branch_name=branch.name,
            tax_branch_code=profile.tax_branch_code if profile else None,
            is_head_office=profile.is_head_office if profile else False,
            legal_name=profile.legal_name if profile else None,
            registered_address=(profile.registered_address if profile else None) or branch.address,
            vat_registration_date=profile.vat_registration_date if profile else None,
            filing_enabled=profile.filing_enabled if profile else True,
            effective_from=profile.effective_from if profile else None,
            effective_to=profile.effective_to if profile else None,
            updated_at=profile.updated_at if profile else None,
        )

    @staticmethod
    def _company_snapshot(company: Company, profile: CompanyTaxProfile | None) -> dict[str, Any]:
        # A flush can expire server-managed timestamps. Audit snapshots must not
        # trigger implicit database I/O through a synchronous attribute access in
        # an AsyncSession, so snapshot only fields already loaded or assigned.
        return _json_value(
            {
                "id": profile.id if profile else None,
                "configured": profile is not None,
                "company_id": company.id,
                "legal_name": (profile.legal_name if profile else None) or company.name,
                "tax_id": (profile.tax_id if profile else None) or company.tax_id,
                "vat_registered": profile.vat_registered if profile else company.vat_registered,
                "vat_registration_date": profile.vat_registration_date if profile else None,
                "registered_address": (profile.registered_address if profile else None)
                or company.address,
                "default_price_vat_type": (
                    profile.default_price_vat_type if profile else "included"
                ),
                "default_vat_rate": profile.default_vat_rate if profile else Decimal("7.00"),
                "vat_filing_mode": profile.vat_filing_mode if profile else "separate",
                "consolidated_filing_approved": (
                    profile.consolidated_filing_approved if profile else False
                ),
            }
        )

    @staticmethod
    def _branch_snapshot(branch: Branch, profile: BranchTaxProfile | None) -> dict[str, Any]:
        return _json_value(
            {
                "id": profile.id if profile else None,
                "configured": profile is not None,
                "company_id": branch.company_id,
                "branch_id": branch.id,
                "branch_code": branch.code,
                "branch_name": branch.name,
                "tax_branch_code": profile.tax_branch_code if profile else None,
                "is_head_office": profile.is_head_office if profile else False,
                "legal_name": profile.legal_name if profile else None,
                "registered_address": (profile.registered_address if profile else None)
                or branch.address,
                "vat_registration_date": profile.vat_registration_date if profile else None,
                "filing_enabled": profile.filing_enabled if profile else True,
                "effective_from": profile.effective_from if profile else None,
                "effective_to": profile.effective_to if profile else None,
            }
        )

    @staticmethod
    def _rate_snapshot(rule: TaxRateRule) -> dict[str, Any]:
        return _json_value(
            {
                "code": rule.code,
                "name": rule.name,
                "tax_category": rule.tax_category,
                "rate": rule.rate,
                "price_vat_type": rule.price_vat_type,
                "effective_from": rule.effective_from,
                "effective_to": rule.effective_to,
                "is_default": rule.is_default,
                "is_active": rule.is_active,
            }
        )

    def _audit(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID | None,
        actor_id: uuid.UUID,
        action: str,
        resource: str,
        resource_id: uuid.UUID,
        old_value: dict[str, Any] | None,
        new_value: dict[str, Any],
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        self.db.add(
            AuditLog(
                company_id=company_id,
                branch_id=branch_id,
                user_id=actor_id,
                action=action,
                resource=resource,
                resource_id=str(resource_id),
                old_value=old_value,
                new_value=new_value,
                ip_address=ip_address,
                user_agent=user_agent,
            )
        )
