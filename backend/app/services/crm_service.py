from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
import uuid

from fastapi import HTTPException, status
from sqlalchemy import String, and_, cast, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.audit import AuditLog
from app.models.company import Company
from app.models.crm import Customer, CustomerTag, CustomerTagAssignment, CustomerTier, LoyaltySettings, PointsTransaction
from app.models.pos import SaleOrder
from app.models.user import User
from app.schemas.crm import (
    CustomerCreate,
    CustomerListItem,
    CustomerPurchaseHistory,
    CustomerSearchResult,
    CustomerTagCreate,
    CustomerUpdate,
    EarnPointsRequest,
    LoyaltySettingsUpdate,
    RedeemPointsRequest,
    RedeemPointsResponse,
)

TWOPLACES = Decimal("0.01")
FOURPLACES = Decimal("0.0001")


def q2(value: Decimal | int | float | str | None) -> Decimal:
    return Decimal(value or 0).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


class CRMService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_loyalty_settings(self, company_id: uuid.UUID) -> LoyaltySettings:
        settings = await self.db.scalar(select(LoyaltySettings).where(LoyaltySettings.company_id == company_id))
        if settings is not None:
            return settings
        settings = LoyaltySettings(
            company_id=company_id,
            earn_rate=Decimal("0.1"),
            earn_min_spend=Decimal("0"),
            redeem_rate=Decimal("0.1"),
            redeem_min_points=100,
            redeem_max_pct=Decimal("100"),
            points_expiry_months=12,
            enabled=True,
            require_phone=True,
        )
        self.db.add(settings)
        await self.db.flush()
        return settings

    async def update_loyalty_settings(self, company_id: uuid.UUID, data: LoyaltySettingsUpdate) -> LoyaltySettings:
        settings = await self.get_loyalty_settings(company_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(settings, field, value)
        await self.db.commit()
        return settings

    async def list_tiers(self, company_id: uuid.UUID) -> list[CustomerTier]:
        return (
            await self.db.scalars(
                select(CustomerTier)
                .where(CustomerTier.company_id == company_id, CustomerTier.is_active.is_(True))
                .order_by(CustomerTier.sort_order.asc(), CustomerTier.min_lifetime_spend.asc())
            )
        ).all()

    async def _update_customer_tier(self, customer: Customer, tiers: list[CustomerTier]) -> None:
        selected_tier: CustomerTier | None = None
        for tier in tiers:
            if customer.lifetime_spend >= tier.min_lifetime_spend:
                selected_tier = tier
        customer.tier_id = selected_tier.id if selected_tier else None
        customer.tier = selected_tier

    async def list_tags(self, company_id: uuid.UUID) -> list[CustomerTag]:
        return (
            await self.db.scalars(
                select(CustomerTag).where(CustomerTag.company_id == company_id).order_by(CustomerTag.name.asc())
            )
        ).all()

    async def create_tag(self, company_id: uuid.UUID, data: CustomerTagCreate) -> CustomerTag:
        existing = await self.db.scalar(
            select(CustomerTag.id).where(CustomerTag.company_id == company_id, CustomerTag.name == data.name)
        )
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Customer tag already exists")
        row = CustomerTag(company_id=company_id, **data.model_dump())
        self.db.add(row)
        await self.db.commit()
        return row

    async def search_customers(self, company_id: uuid.UUID, query: str, limit: int = 10) -> list[CustomerSearchResult]:
        keyword = query.strip()
        if len(keyword) < 3:
            return []
        pattern = f"%{keyword}%"
        rows = (
            await self.db.scalars(
                select(Customer)
                .where(
                    Customer.company_id == company_id,
                    Customer.deleted_at.is_(None),
                    or_(
                        Customer.phone.ilike(pattern),
                        Customer.customer_code.ilike(pattern),
                        Customer.display_name.ilike(pattern),
                        Customer.first_name.ilike(pattern),
                        Customer.last_name.ilike(pattern),
                    ),
                )
                .options(selectinload(Customer.tier))
                .order_by(
                    Customer.phone.ilike(f"{keyword}%").desc(),
                    Customer.last_purchase_at.desc().nullslast(),
                    Customer.created_at.desc(),
                )
                .limit(limit)
            )
        ).all()
        return [
            CustomerSearchResult(
                id=row.id,
                customer_code=row.customer_code,
                display_name=row.full_name,
                phone=row.phone,
                points_balance=row.points_balance,
                tier_name=row.tier.name if row.tier else None,
            )
            for row in rows
        ]

    async def list_customers(
        self,
        company_id: uuid.UUID,
        tier_id: uuid.UUID | None = None,
        tag_id: uuid.UUID | None = None,
        is_active: bool | None = None,
        search: str | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[Customer], int]:
        filters = [Customer.company_id == company_id, Customer.deleted_at.is_(None)]
        if tier_id is not None:
            filters.append(Customer.tier_id == tier_id)
        if is_active is not None:
            filters.append(Customer.is_active.is_(is_active))
        if search:
            pattern = f"%{search.strip()}%"
            filters.append(
                or_(
                    Customer.customer_code.ilike(pattern),
                    Customer.phone.ilike(pattern),
                    Customer.email.ilike(pattern),
                    Customer.display_name.ilike(pattern),
                    Customer.first_name.ilike(pattern),
                    Customer.last_name.ilike(pattern),
                )
            )
        query = select(Customer).where(*filters)
        count_query = select(func.count(Customer.id)).where(*filters)
        if tag_id is not None:
            query = query.join(CustomerTagAssignment, CustomerTagAssignment.customer_id == Customer.id).where(CustomerTagAssignment.tag_id == tag_id)
            count_query = count_query.join(CustomerTagAssignment, CustomerTagAssignment.customer_id == Customer.id).where(CustomerTagAssignment.tag_id == tag_id)
        total = int((await self.db.scalar(count_query)) or 0)
        rows = (
            await self.db.scalars(
                query.options(
                    selectinload(Customer.tier),
                    selectinload(Customer.tag_assignments).selectinload(CustomerTagAssignment.tag),
                )
                .order_by(Customer.created_at.desc())
                .offset((page - 1) * limit)
                .limit(limit)
            )
        ).all()
        for row in rows:
            self._hydrate_customer(row)
        return rows, total

    async def get_customer(self, customer_id: uuid.UUID, company_id: uuid.UUID) -> Customer:
        row = await self.db.scalar(
            select(Customer)
            .where(Customer.id == customer_id, Customer.company_id == company_id, Customer.deleted_at.is_(None))
            .options(
                selectinload(Customer.tier),
                selectinload(Customer.tag_assignments).selectinload(CustomerTagAssignment.tag),
            )
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
        self._hydrate_customer(row)
        return row

    async def create_customer(self, company_id: uuid.UUID, user_id: uuid.UUID, data: CustomerCreate) -> Customer:
        settings = await self.get_loyalty_settings(company_id)
        if settings.require_phone and not data.phone:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Phone is required for loyalty members")
        if data.phone:
            await self._ensure_phone_available(company_id, data.phone)
        customer_code = await self._generate_customer_code(company_id)
        tiers = await self.list_tiers(company_id)
        bronze = tiers[0] if tiers else None
        row = Customer(
            company_id=company_id,
            customer_code=customer_code,
            tier_id=bronze.id if bronze else None,
            **data.model_dump(exclude={"tag_ids"}),
        )
        self.db.add(row)
        await self.db.flush()
        await self._replace_customer_tags(row, company_id, data.tag_ids)
        self._audit(company_id, user_id, "crm.customer.created", "Customer", row.id)
        await self.db.commit()
        return await self.get_customer(row.id, company_id)

    async def update_customer(self, customer_id: uuid.UUID, company_id: uuid.UUID, data: CustomerUpdate) -> Customer:
        row = await self.get_customer(customer_id, company_id)
        payload = data.model_dump(exclude_unset=True, exclude={"tag_ids"})
        if "phone" in payload and payload["phone"] != row.phone and payload["phone"]:
            await self._ensure_phone_available(company_id, payload["phone"], exclude_id=row.id)
        for field, value in payload.items():
            setattr(row, field, value)
        if data.tag_ids is not None:
            await self._replace_customer_tags(row, company_id, data.tag_ids)
        self._audit(company_id, None, "crm.customer.updated", "Customer", row.id)
        await self.db.commit()
        return await self.get_customer(row.id, company_id)

    async def get_purchase_history(self, customer_id: uuid.UUID, company_id: uuid.UUID) -> CustomerPurchaseHistory:
        customer = await self.get_customer(customer_id, company_id)
        order_rows = (
            await self.db.scalars(
                select(SaleOrder)
                .where(
                    SaleOrder.company_id == company_id,
                    or_(
                        and_(customer.phone.is_not(None), SaleOrder.customer_phone == customer.phone),
                        cast(SaleOrder.id, String).in_(
                            select(PointsTransaction.reference_id)
                            .where(
                                PointsTransaction.company_id == company_id,
                                PointsTransaction.customer_id == customer.id,
                                PointsTransaction.reference_type == "SaleOrder",
                            )
                        ),
                    ),
                )
                .order_by(SaleOrder.created_at.desc())
            )
        ).all()
        total_orders = len(order_rows)
        total_spend = q2(sum((row.total_amount for row in order_rows), Decimal("0")))
        avg_order_value = q2(total_spend / Decimal(total_orders)) if total_orders else Decimal("0.00")
        first_purchase_at = order_rows[-1].created_at.isoformat() if order_rows else None
        last_purchase_at = order_rows[0].created_at.isoformat() if order_rows else None
        return CustomerPurchaseHistory(
            total_orders=total_orders,
            total_spend=total_spend,
            avg_order_value=avg_order_value,
            first_purchase_at=first_purchase_at,
            last_purchase_at=last_purchase_at,
            recent_orders=[
                {"id": str(row.id), "created_at": row.created_at.isoformat(), "total_amount": float(row.total_amount)}
                for row in order_rows[:10]
            ],
        )

    async def earn_points(self, company_id: uuid.UUID, user_id: uuid.UUID, data: EarnPointsRequest) -> PointsTransaction | None:
        settings = await self.get_loyalty_settings(company_id)
        if not settings.enabled:
            return None
        customer = await self.get_customer(data.customer_id, company_id)
        if settings.require_phone and not customer.phone:
            return None
        if q2(data.spend_amount) < q2(settings.earn_min_spend):
            return None
        existing = await self.db.scalar(
            select(PointsTransaction.id).where(
                PointsTransaction.company_id == company_id,
                PointsTransaction.customer_id == customer.id,
                PointsTransaction.transaction_type == "earn",
                PointsTransaction.reference_type == "SaleOrder",
                PointsTransaction.reference_id == data.sale_order_id,
            )
        )
        if existing is not None:
            return await self.db.get(PointsTransaction, existing)

        tiers = await self.list_tiers(company_id)
        projected_spend = q2(customer.lifetime_spend + q2(data.spend_amount))
        projected_tier = self._get_tier_for_spend(projected_spend, tiers)
        multiplier = Decimal(projected_tier.points_multiplier if projected_tier else Decimal("1.0"))
        raw_points = Decimal(data.spend_amount) * Decimal(settings.earn_rate) * multiplier
        points = int(raw_points.quantize(Decimal("1"), rounding=ROUND_DOWN))
        customer.lifetime_spend = projected_spend
        customer.total_orders = int(customer.total_orders or 0) + 1
        customer.last_purchase_at = datetime.now(timezone.utc)
        await self._update_customer_tier(customer, tiers)
        if points == 0:
            await self.db.commit()
            return None

        customer.points_balance = int(customer.points_balance or 0) + points
        customer.lifetime_points_earned = int(customer.lifetime_points_earned or 0) + points
        expires_at = None
        if settings.points_expiry_months > 0:
            expires_at = datetime.now(timezone.utc) + timedelta(days=30 * settings.points_expiry_months)
        tx = PointsTransaction(
            company_id=company_id,
            customer_id=customer.id,
            transaction_type="earn",
            points=points,
            balance_after=customer.points_balance,
            reference_type="SaleOrder",
            reference_id=data.sale_order_id,
            spend_amount=q2(data.spend_amount),
            note=data.note,
            expires_at=expires_at,
            created_by=await self._resolve_creator_id(user_id, company_id),
        )
        self.db.add(tx)
        await self.db.commit()
        await self.db.refresh(tx)
        return tx

    async def redeem_points(self, company_id: uuid.UUID, user_id: uuid.UUID, data: RedeemPointsRequest) -> RedeemPointsResponse:
        settings = await self.get_loyalty_settings(company_id)
        customer = await self.get_customer(data.customer_id, company_id)
        if data.points_to_redeem < settings.redeem_min_points:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Redeem points below minimum threshold")
        if customer.points_balance < data.points_to_redeem:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient points balance")
        discount_amount = q2(Decimal(data.points_to_redeem) * Decimal(settings.redeem_rate))
        customer.points_balance -= data.points_to_redeem
        customer.lifetime_points_redeemed = int(customer.lifetime_points_redeemed or 0) + data.points_to_redeem
        self.db.add(
            PointsTransaction(
                company_id=company_id,
                customer_id=customer.id,
                transaction_type="redeem",
                points=-data.points_to_redeem,
                balance_after=customer.points_balance,
                reference_type="SaleOrder" if data.sale_order_id else None,
                reference_id=data.sale_order_id,
                redeem_amount=discount_amount,
                created_by=await self._resolve_creator_id(user_id, company_id),
            )
        )
        await self.db.commit()
        return RedeemPointsResponse(
            points_redeemed=data.points_to_redeem,
            discount_amount=discount_amount,
            new_balance=customer.points_balance,
        )

    async def void_earn(self, company_id: uuid.UUID, user_id: uuid.UUID, sale_order_id: str) -> PointsTransaction | None:
        original = await self.db.scalar(
            select(PointsTransaction)
            .where(
                PointsTransaction.company_id == company_id,
                PointsTransaction.transaction_type == "earn",
                PointsTransaction.reference_type == "SaleOrder",
                PointsTransaction.reference_id == sale_order_id,
            )
            .options(selectinload(PointsTransaction.customer))
        )
        if original is None:
            return None
        existing_void = await self.db.scalar(
            select(PointsTransaction.id).where(
                PointsTransaction.company_id == company_id,
                PointsTransaction.customer_id == original.customer_id,
                PointsTransaction.transaction_type == "void_earn",
                PointsTransaction.reference_type == "SaleOrder",
                PointsTransaction.reference_id == sale_order_id,
            )
        )
        if existing_void is not None:
            return await self.db.get(PointsTransaction, existing_void)
        customer = await self.get_customer(original.customer_id, company_id)
        customer.points_balance = max(int(customer.points_balance or 0) - max(original.points, 0), 0)
        customer.lifetime_spend = q2(max(Decimal("0"), Decimal(customer.lifetime_spend or 0) - Decimal(original.spend_amount or 0)))
        customer.total_orders = max(int(customer.total_orders or 0) - 1, 0)
        await self._update_customer_tier(customer, await self.list_tiers(company_id))
        tx = PointsTransaction(
            company_id=company_id,
            customer_id=customer.id,
            transaction_type="void_earn",
            points=-max(original.points, 0),
            balance_after=customer.points_balance,
            reference_type="SaleOrder",
            reference_id=sale_order_id,
            spend_amount=q2(-(original.spend_amount or Decimal("0"))),
            note="Void sale loyalty reversal",
            created_by=await self._resolve_creator_id(user_id, company_id),
        )
        self.db.add(tx)
        await self.db.flush()
        return tx

    async def adjust_points(self, company_id: uuid.UUID, user_id: uuid.UUID, customer_id: uuid.UUID, points: int, note: str) -> PointsTransaction:
        customer = await self.get_customer(customer_id, company_id)
        new_balance = int(customer.points_balance or 0) + points
        if new_balance < 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Points balance cannot go negative")
        customer.points_balance = new_balance
        tx = PointsTransaction(
            company_id=company_id,
            customer_id=customer.id,
            transaction_type="adjust",
            points=points,
            balance_after=new_balance,
            reference_type="Adjustment",
            reference_id=str(uuid.uuid4()),
            note=note,
            created_by=await self._resolve_creator_id(user_id, company_id),
        )
        self.db.add(tx)
        self._audit(company_id, user_id, "crm.points.adjusted", "Customer", customer.id)
        await self.db.commit()
        return tx

    async def expire_points(self, company_id: uuid.UUID) -> int:
        now = datetime.now(timezone.utc)
        rows = (
            await self.db.scalars(
                select(PointsTransaction)
                .where(
                    PointsTransaction.company_id == company_id,
                    PointsTransaction.transaction_type == "earn",
                    PointsTransaction.expires_at.is_not(None),
                    PointsTransaction.expires_at < now,
                )
                .options(selectinload(PointsTransaction.customer))
            )
        ).all()
        expired_count = 0
        for row in rows:
            existing = await self.db.scalar(
                select(PointsTransaction.id).where(
                    PointsTransaction.company_id == company_id,
                    PointsTransaction.customer_id == row.customer_id,
                    PointsTransaction.reference_type == row.reference_type,
                    PointsTransaction.reference_id == row.reference_id,
                    PointsTransaction.transaction_type.in_(["expire", "void_earn"]),
                )
            )
            if existing is not None or row.points <= 0:
                continue
            customer = await self.get_customer(row.customer_id, company_id)
            deduct_points = min(customer.points_balance, row.points)
            if deduct_points <= 0:
                continue
            customer.points_balance -= deduct_points
            self.db.add(
                PointsTransaction(
                    company_id=company_id,
                    customer_id=customer.id,
                    transaction_type="expire",
                    points=-deduct_points,
                    balance_after=customer.points_balance,
                    reference_type=row.reference_type,
                    reference_id=row.reference_id,
                    note="Points expired",
                )
            )
            expired_count += 1
        await self.db.commit()
        return expired_count

    async def get_points_history(
        self,
        customer_id: uuid.UUID,
        company_id: uuid.UUID,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[PointsTransaction], int]:
        total = int(
            (
                await self.db.scalar(
                    select(func.count(PointsTransaction.id)).where(
                        PointsTransaction.company_id == company_id,
                        PointsTransaction.customer_id == customer_id,
                    )
                )
            )
            or 0
        )
        rows = (
            await self.db.scalars(
                select(PointsTransaction)
                .where(
                    PointsTransaction.company_id == company_id,
                    PointsTransaction.customer_id == customer_id,
                )
                .order_by(PointsTransaction.created_at.desc())
                .offset((page - 1) * limit)
                .limit(limit)
            )
        ).all()
        return rows, total

    async def _generate_customer_code(self, company_id: uuid.UUID) -> str:
        count = int((await self.db.scalar(select(func.count(Customer.id)).where(Customer.company_id == company_id))) or 0)
        return f"CUS-{count + 1:04d}"

    async def _ensure_phone_available(self, company_id: uuid.UUID, phone: str, exclude_id: uuid.UUID | None = None) -> None:
        query = select(Customer.id).where(
            Customer.company_id == company_id,
            Customer.phone == phone,
            Customer.deleted_at.is_(None),
        )
        if exclude_id is not None:
            query = query.where(Customer.id != exclude_id)
        if await self.db.scalar(query) is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Customer phone already exists")

    async def _replace_customer_tags(self, customer: Customer, company_id: uuid.UUID, tag_ids: list[uuid.UUID]) -> None:
        tags = []
        if tag_ids:
            tags = (
                await self.db.scalars(
                    select(CustomerTag).where(CustomerTag.company_id == company_id, CustomerTag.id.in_(tag_ids))
                )
            ).all()
            if len(tags) != len(set(tag_ids)):
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more customer tags not found")
        await self.db.execute(
            delete(CustomerTagAssignment).where(CustomerTagAssignment.customer_id == customer.id)
        )
        await self.db.flush()
        for tag in tags:
            self.db.add(CustomerTagAssignment(customer_id=customer.id, tag_id=tag.id))

    async def _resolve_creator_id(self, user_id: uuid.UUID | None, company_id: uuid.UUID) -> uuid.UUID | None:
        if user_id is None:
            return None
        exists = await self.db.scalar(select(User.id).where(User.id == user_id, User.company_id == company_id))
        return exists

    def _get_tier_for_spend(self, spend: Decimal, tiers: list[CustomerTier]) -> CustomerTier | None:
        selected_tier = None
        for tier in tiers:
            if spend >= tier.min_lifetime_spend:
                selected_tier = tier
        return selected_tier

    def _hydrate_customer(self, customer: Customer) -> None:
        customer.tags = [assignment.tag for assignment in customer.tag_assignments if assignment.tag is not None]
        customer.tier_name = customer.tier.name if customer.tier else None
        customer.display_name = customer.display_name or customer.full_name

    def _audit(self, company_id: uuid.UUID, user_id: uuid.UUID | None, action: str, resource: str, resource_id: uuid.UUID) -> None:
        self.db.add(
            AuditLog(
                company_id=company_id,
                user_id=user_id,
                action=action,
                resource=resource,
                resource_id=str(resource_id),
            )
        )


async def resolve_public_company_id(db: AsyncSession) -> uuid.UUID:
    company = await db.scalar(select(Company).where(Company.is_active.is_(True)).order_by(Company.created_at.asc()))
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return company.id
