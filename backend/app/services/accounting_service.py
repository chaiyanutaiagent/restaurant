from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.accounting import Account, AccountBalance, JournalEntry, JournalLine
from app.models.audit import AuditLog
from app.models.company import Company
from app.models.pos import SaleOrder
from app.models.purchase import PurchaseOrder
from app.models.stock import StockMovement
from app.schemas.accounting import AccountCreate, AccountLedgerResponse, AccountUpdate, CreateJournalEntryRequest
from app.utils.posting_rules import PostingLine, get_payment_posting, get_purchase_posting, get_sale_posting, get_stock_adjustment_posting
from app.utils.thai_date import MONTHS_TH

TWOPLACES = Decimal("0.01")


def q2(value: Decimal | int | float | str | None) -> Decimal:
    return Decimal(value or 0).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


class AccountingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_accounts(
        self,
        company_id: uuid.UUID,
        account_type: str | None = None,
        tree: bool = False,
    ) -> list[Account]:
        filters = [Account.company_id == company_id, Account.deleted_at.is_(None)]
        if account_type:
            filters.append(Account.account_type == account_type)
        accounts = (
            await self.db.scalars(select(Account).where(*filters).order_by(Account.code.asc(), Account.sort_order.asc()))
        ).all()
        if not tree:
            return accounts
        return self._build_account_tree(accounts)

    async def get_account(self, account_id: uuid.UUID, company_id: uuid.UUID) -> Account:
        account = await self.db.scalar(
            select(Account).where(
                Account.id == account_id,
                Account.company_id == company_id,
                Account.deleted_at.is_(None),
            )
        )
        if account is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
        return account

    async def create_account(self, company_id: uuid.UUID, data: AccountCreate) -> Account:
        existing = await self.db.scalar(
            select(Account.id).where(
                Account.company_id == company_id,
                Account.code == data.code,
                Account.deleted_at.is_(None),
            )
        )
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Account code already exists")

        parent = None
        account_type = data.account_type
        if data.parent_id is not None:
            parent = await self.get_account(data.parent_id, company_id)
            if not parent.is_header:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Parent account must be a header account")
            account_type = parent.account_type
            if data.account_type != parent.account_type:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Child account type must match parent")

        account = Account(
            company_id=company_id,
            parent_id=parent.id if parent else None,
            code=data.code,
            name=data.name,
            name_en=data.name_en,
            account_type=account_type,
            account_subtype=data.account_subtype,
            normal_balance=data.normal_balance,
            is_header=data.is_header,
            is_active=data.is_active,
            description=data.description,
            sort_order=data.sort_order,
        )
        self.db.add(account)
        await self.db.commit()
        return await self.get_account(account.id, company_id)

    async def update_account(self, account_id: uuid.UUID, company_id: uuid.UUID, data: AccountUpdate) -> Account:
        account = await self.get_account(account_id, company_id)
        if account.is_system and data.code is not None and data.code != account.code:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="System account code cannot be changed")

        if data.parent_id is not None:
            parent = await self.get_account(data.parent_id, company_id)
            if not parent.is_header:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Parent account must be a header account")
            if parent.id == account.id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Account cannot be its own parent")
            account.parent_id = parent.id
            account.account_type = parent.account_type

        if data.is_active is False:
            has_lines = await self.db.scalar(select(JournalLine.id).where(JournalLine.account_id == account.id))
            if has_lines is not None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Account with journal entries cannot be deactivated")

        for field, value in data.model_dump(exclude_unset=True, exclude={"parent_id"}).items():
            setattr(account, field, value)
        await self.db.commit()
        return await self.get_account(account.id, company_id)

    async def _get_account_by_code(self, code: str, company_id: uuid.UUID) -> Account:
        account = await self.db.scalar(
            select(Account).where(
                Account.company_id == company_id,
                Account.code == code,
                Account.deleted_at.is_(None),
            )
        )
        if account is None:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"System account not found: {code}")
        return account

    async def _post_entry(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID | None,
        user_id: uuid.UUID,
        entry_date: date,
        entry_type: str,
        description: str,
        lines: list[PostingLine],
        reference_type: str | None = None,
        reference_id: str | None = None,
    ) -> JournalEntry:
        if not lines:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Journal entry requires lines")
        debit_total = q2(sum((Decimal(line.debit_amount) for line in lines), Decimal("0")))
        credit_total = q2(sum((Decimal(line.credit_amount) for line in lines), Decimal("0")))
        if debit_total != credit_total:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Posting lines are not balanced")

        entry_prefix = f"JE{entry_date:%Y%m%d}-"
        existing_count = await self.db.scalar(
            select(func.count(JournalEntry.id)).where(
                JournalEntry.company_id == company_id,
                JournalEntry.entry_number.like(f"{entry_prefix}%"),
            )
        ) or 0
        entry_number = f"{entry_prefix}{int(existing_count) + 1:04d}"
        period_year = entry_date.year + 543
        period_month = entry_date.month
        posted_at = datetime.now(timezone.utc)
        entry = JournalEntry(
            company_id=company_id,
            branch_id=branch_id,
            entry_number=entry_number,
            entry_date=entry_date,
            period_year=period_year,
            period_month=period_month,
            entry_type=entry_type,
            reference_type=reference_type,
            reference_id=reference_id,
            description=description,
            is_posted=True,
            created_by=user_id,
            posted_at=posted_at,
        )
        self.db.add(entry)
        await self.db.flush()

        for index, line in enumerate(lines, start=1):
            account = await self._get_account_by_code(line.account_code, company_id)
            self.db.add(
                JournalLine(
                    entry_id=entry.id,
                    company_id=company_id,
                    account_id=account.id,
                    line_number=index,
                    description=line.description,
                    debit_amount=q2(line.debit_amount),
                    credit_amount=q2(line.credit_amount),
                )
            )
            balance = await self._get_or_create_account_balance(company_id, account, period_year, period_month)
            balance.debit_total = q2(Decimal(balance.debit_total) + Decimal(line.debit_amount))
            balance.credit_total = q2(Decimal(balance.credit_total) + Decimal(line.credit_amount))
            if account.normal_balance == "debit":
                balance.closing_balance = q2(
                    Decimal(balance.opening_balance) + Decimal(balance.debit_total) - Decimal(balance.credit_total)
                )
            else:
                balance.closing_balance = q2(
                    Decimal(balance.opening_balance) + Decimal(balance.credit_total) - Decimal(balance.debit_total)
                )

        await self.db.flush()
        return await self.get_entry(entry.id, company_id)

    async def post_sale(self, sale_order: SaleOrder, company_id: uuid.UUID, user_id: uuid.UUID) -> JournalEntry:
        if not sale_order.payments:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sale order payment is required")
        lines = get_sale_posting(
            subtotal=Decimal(sale_order.subtotal or 0) - Decimal(sale_order.vat_amount or 0),
            vat_amount=Decimal(sale_order.vat_amount or 0),
            total_amount=Decimal(sale_order.total_amount or 0),
            payment_method=sale_order.payments[0].payment_method,
            discount_amount=Decimal(sale_order.discount_amount or 0),
        )
        return await self._post_entry(
            company_id=company_id,
            branch_id=sale_order.branch_id,
            user_id=user_id,
            entry_date=sale_order.created_at.date(),
            entry_type="sale",
            description=f"ขายสินค้า {sale_order.order_number}",
            lines=lines,
            reference_type="SaleOrder",
            reference_id=str(sale_order.id),
        )

    async def post_purchase(self, po: PurchaseOrder, company_id: uuid.UUID, user_id: uuid.UUID) -> JournalEntry:
        lines = get_purchase_posting(
            subtotal=Decimal(po.subtotal or 0),
            vat_amount=Decimal(po.vat_amount or 0),
            wht_amount=Decimal(po.wht_amount or 0),
            total_amount=Decimal(po.total_amount or 0),
        )
        return await self._post_entry(
            company_id=company_id,
            branch_id=po.branch_id,
            user_id=user_id,
            entry_date=po.order_date,
            entry_type="purchase",
            description=f"ซื้อสินค้า {po.po_number}",
            lines=lines,
            reference_type="PurchaseOrder",
            reference_id=str(po.id),
        )

    async def post_stock_adjustment(
        self,
        movement: StockMovement,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> JournalEntry | None:
        if movement.movement_type not in {"adjust", "stock"}:
            return None
        lines = get_stock_adjustment_posting(
            qty_delta=Decimal(movement.qty or 0),
            cost_per_unit=Decimal(movement.cost_per_unit or 0),
        )
        if not lines:
            return None
        return await self._post_entry(
            company_id=company_id,
            branch_id=movement.branch_id,
            user_id=user_id,
            entry_date=movement.created_at.date(),
            entry_type="adjustment",
            description=f"ปรับสต็อก {movement.id}",
            lines=lines,
            reference_type="StockMovement",
            reference_id=str(movement.id),
        )

    async def create_manual_entry(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID | None,
        user_id: uuid.UUID,
        data: CreateJournalEntryRequest,
    ) -> JournalEntry:
        self._ensure_balanced_request(data)
        account_map = await self._load_manual_accounts(company_id, [line.account_id for line in data.lines])
        entry = await self._post_entry(
            company_id=company_id,
            branch_id=branch_id or data.branch_id,
            user_id=user_id,
            entry_date=data.entry_date,
            entry_type="manual",
            description=data.description,
            lines=[
                PostingLine(
                    account_code=account_map[line.account_id].code,
                    debit_amount=q2(line.debit_amount),
                    credit_amount=q2(line.credit_amount),
                    description=line.description or data.description,
                )
                for line in data.lines
            ],
        )
        self.db.add(
            AuditLog(
                company_id=company_id,
                branch_id=branch_id or data.branch_id,
                user_id=user_id,
                action="accounting.journal.create",
                resource="JournalEntry",
                resource_id=str(entry.id),
            )
        )
        await self.db.commit()
        return await self.get_entry(entry.id, company_id)

    async def reverse_entry(self, entry_id: uuid.UUID, company_id: uuid.UUID, user_id: uuid.UUID) -> JournalEntry:
        entry = await self.get_entry(entry_id, company_id)
        if entry.is_reversed:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Journal entry already reversed")
        reversed_entry = await self._post_entry(
            company_id=company_id,
            branch_id=entry.branch_id,
            user_id=user_id,
            entry_date=entry.entry_date,
            entry_type="manual",
            description=f"Reversal of {entry.entry_number}",
            lines=[
                PostingLine(
                    account_code=line.account.code,
                    debit_amount=q2(line.credit_amount),
                    credit_amount=q2(line.debit_amount),
                    description=line.description or f"Reversal of line {line.line_number}",
                )
                for line in entry.lines
            ],
            reference_type="JournalEntry",
            reference_id=str(entry.id),
        )
        entry.is_reversed = True
        entry.reversed_by = reversed_entry.id
        self.db.add(
            AuditLog(
                company_id=company_id,
                branch_id=entry.branch_id,
                user_id=user_id,
                action="accounting.journal.reverse",
                resource="JournalEntry",
                resource_id=str(entry.id),
            )
        )
        await self.db.commit()
        return await self.get_entry(reversed_entry.id, company_id)

    async def list_entries(
        self,
        company_id: uuid.UUID,
        entry_type: str | None = None,
        period_year: int | None = None,
        period_month: int | None = None,
        account_id: uuid.UUID | None = None,
        reference_type: str | None = None,
        page: int = 1,
        limit: int = 50,
    ) -> tuple[list[JournalEntry], int]:
        filters = [JournalEntry.company_id == company_id]
        if entry_type:
            filters.append(JournalEntry.entry_type == entry_type)
        if period_year is not None:
            filters.append(JournalEntry.period_year == period_year)
        if period_month is not None:
            filters.append(JournalEntry.period_month == period_month)
        if reference_type:
            filters.append(JournalEntry.reference_type == reference_type)

        statement = select(JournalEntry).where(*filters)
        total_statement = select(func.count(JournalEntry.id)).where(*filters)
        if account_id is not None:
            statement = statement.join(JournalLine, JournalLine.entry_id == JournalEntry.id).where(JournalLine.account_id == account_id)
            total_statement = (
                select(func.count(func.distinct(JournalEntry.id)))
                .select_from(JournalEntry)
                .join(JournalLine, JournalLine.entry_id == JournalEntry.id)
                .where(*filters, JournalLine.account_id == account_id)
            )

        total = int((await self.db.scalar(total_statement)) or 0)
        rows = await self.db.scalars(
            statement
            .options(selectinload(JournalEntry.lines).selectinload(JournalLine.account))
            .order_by(JournalEntry.entry_date.desc(), JournalEntry.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        return rows.unique().all(), total

    async def get_entry(self, entry_id: uuid.UUID, company_id: uuid.UUID) -> JournalEntry:
        entry = await self.db.scalar(
            select(JournalEntry)
            .where(JournalEntry.id == entry_id, JournalEntry.company_id == company_id)
            .options(selectinload(JournalEntry.lines).selectinload(JournalLine.account))
        )
        if entry is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Journal entry not found")
        return entry

    async def get_trial_balance(
        self,
        company_id: uuid.UUID,
        period_year: int,
        period_month: int,
    ) -> dict[str, object]:
        leaf_accounts = (
            await self.db.scalars(
                select(Account).where(
                    Account.company_id == company_id,
                    Account.is_header.is_(False),
                    Account.deleted_at.is_(None),
                ).order_by(Account.code.asc())
            )
        ).all()
        balances = (
            await self.db.scalars(
                select(AccountBalance).where(
                    AccountBalance.company_id == company_id,
                    AccountBalance.period_year == period_year,
                    AccountBalance.period_month == period_month,
                )
            )
        ).all()
        balance_map = {item.account_id: item for item in balances}
        rows: list[dict[str, object]] = []
        total_debit = Decimal("0")
        total_credit = Decimal("0")
        for account in leaf_accounts:
            closing = q2(balance_map.get(account.id).closing_balance if account.id in balance_map else 0)
            debit_balance = Decimal("0")
            credit_balance = Decimal("0")
            if account.normal_balance == "debit":
                if closing >= 0:
                    debit_balance = closing
                else:
                    credit_balance = abs(closing)
            else:
                if closing >= 0:
                    credit_balance = closing
                else:
                    debit_balance = abs(closing)
            total_debit += debit_balance
            total_credit += credit_balance
            rows.append(
                {
                    "account_code": account.code,
                    "account_name": account.name,
                    "account_type": account.account_type,
                    "debit_balance": q2(debit_balance),
                    "credit_balance": q2(credit_balance),
                }
            )
        return {
            "period_year": period_year,
            "period_month": period_month,
            "period_label": f"{MONTHS_TH[period_month]} {period_year}",
            "rows": rows,
            "total_debit": q2(total_debit),
            "total_credit": q2(total_credit),
            "is_balanced": q2(total_debit) == q2(total_credit),
        }

    async def get_profit_loss(
        self,
        company_id: uuid.UUID,
        period_year: int,
        period_month: int,
        cumulative: bool = False,
    ) -> dict[str, object]:
        company = await self.db.get(Company, company_id)
        fiscal_year_start = int(company.fiscal_year_start if company else 1)
        target_periods = self._periods_for_report(period_year, period_month, fiscal_year_start, cumulative)
        balances = (
            await self.db.scalars(
                select(AccountBalance)
                .join(Account, Account.id == AccountBalance.account_id)
                .where(
                    AccountBalance.company_id == company_id,
                    Account.deleted_at.is_(None),
                    or_(
                        *[
                            (
                                (AccountBalance.period_year == target_year)
                                & (AccountBalance.period_month == target_month)
                            )
                            for target_year, target_month in target_periods
                        ]
                    ),
                )
            )
        ).all()
        account_map = {
            account.id: account
            for account in (
                await self.db.scalars(
                    select(Account).where(Account.company_id == company_id, Account.deleted_at.is_(None))
                )
            ).all()
        }
        totals: dict[uuid.UUID, Decimal] = {}
        for balance in balances:
            account = account_map.get(balance.account_id)
            if account is None or account.is_header:
                continue
            period_value = self._profit_loss_value(account.normal_balance, balance.debit_total, balance.credit_total)
            totals[account.id] = q2(Decimal(totals.get(account.id, 0)) + period_value)

        revenue_rows = self._build_profit_rows(account_map, totals, "revenue")
        cogs_rows = self._build_profit_rows(account_map, totals, "expense", "cost_of_goods")
        expense_rows = self._build_profit_rows(account_map, totals, "expense", exclude_subtype="cost_of_goods")

        total_revenue = q2(sum((row["credit_balance"] for row in revenue_rows), Decimal("0")))
        total_cogs = q2(sum((row["debit_balance"] for row in cogs_rows), Decimal("0")))
        total_operating_expense = q2(sum((row["debit_balance"] for row in expense_rows), Decimal("0")))
        gross_profit = q2(total_revenue - total_cogs)
        net_profit = q2(gross_profit - total_operating_expense)
        gross_margin_pct = q2((gross_profit / total_revenue * Decimal("100")) if total_revenue else 0)
        net_margin_pct = q2((net_profit / total_revenue * Decimal("100")) if total_revenue else 0)

        return {
            "period_year": period_year,
            "period_month": period_month,
            "period_label": f"{MONTHS_TH[period_month]} {period_year}",
            "total_revenue": total_revenue,
            "total_cogs": total_cogs,
            "gross_profit": gross_profit,
            "gross_margin_pct": gross_margin_pct,
            "total_operating_expense": total_operating_expense,
            "net_profit": net_profit,
            "net_margin_pct": net_margin_pct,
            "revenue_rows": revenue_rows,
            "cogs_rows": cogs_rows,
            "expense_rows": expense_rows,
        }

    async def get_account_ledger(
        self,
        account_id: uuid.UUID,
        company_id: uuid.UUID,
        period_year: int,
        period_month: int,
    ) -> AccountLedgerResponse:
        account = await self.get_account(account_id, company_id)
        balance = await self.db.scalar(
            select(AccountBalance).where(
                AccountBalance.company_id == company_id,
                AccountBalance.account_id == account_id,
                AccountBalance.period_year == period_year,
                AccountBalance.period_month == period_month,
            )
        )
        lines = (
            await self.db.scalars(
                select(JournalLine)
                .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
                .where(
                    JournalLine.company_id == company_id,
                    JournalLine.account_id == account_id,
                    JournalEntry.period_year == period_year,
                    JournalEntry.period_month == period_month,
                )
                .options(selectinload(JournalLine.entry))
                .order_by(JournalEntry.entry_date.asc(), JournalLine.line_number.asc())
            )
        ).all()
        opening_balance = q2(balance.opening_balance if balance else 0)
        running = opening_balance
        ledger_lines: list[dict[str, object]] = []
        for line in lines:
            if account.normal_balance == "debit":
                running = q2(running + Decimal(line.debit_amount) - Decimal(line.credit_amount))
            else:
                running = q2(running + Decimal(line.credit_amount) - Decimal(line.debit_amount))
            ledger_lines.append(
                {
                    "entry_id": line.entry_id,
                    "entry_number": line.entry.entry_number,
                    "entry_date": line.entry.entry_date,
                    "line_number": line.line_number,
                    "description": line.description,
                    "debit_amount": q2(line.debit_amount),
                    "credit_amount": q2(line.credit_amount),
                    "running_balance": running,
                    "reference_type": line.entry.reference_type,
                    "reference_id": line.entry.reference_id,
                }
            )

        return AccountLedgerResponse(
            account_id=account.id,
            account_code=account.code,
            account_name=account.name,
            period_year=period_year,
            period_month=period_month,
            opening_balance=opening_balance,
            closing_balance=q2(balance.closing_balance if balance else running),
            lines=ledger_lines,
            meta={"normal_balance": account.normal_balance},
        )

    async def _get_or_create_account_balance(
        self,
        company_id: uuid.UUID,
        account: Account,
        period_year: int,
        period_month: int,
    ) -> AccountBalance:
        balance = await self.db.scalar(
            select(AccountBalance).where(
                AccountBalance.company_id == company_id,
                AccountBalance.account_id == account.id,
                AccountBalance.period_year == period_year,
                AccountBalance.period_month == period_month,
            )
        )
        if balance is not None:
            return balance
        prev_year, prev_month = self._previous_period(period_year, period_month)
        previous = await self.db.scalar(
            select(AccountBalance).where(
                AccountBalance.company_id == company_id,
                AccountBalance.account_id == account.id,
                AccountBalance.period_year == prev_year,
                AccountBalance.period_month == prev_month,
            )
        )
        opening_balance = q2(previous.closing_balance if previous else 0)
        balance = AccountBalance(
            company_id=company_id,
            account_id=account.id,
            period_year=period_year,
            period_month=period_month,
            opening_balance=opening_balance,
            debit_total=Decimal("0.00"),
            credit_total=Decimal("0.00"),
            closing_balance=opening_balance,
        )
        self.db.add(balance)
        await self.db.flush()
        return balance

    async def _load_manual_accounts(self, company_id: uuid.UUID, account_ids: list[uuid.UUID]) -> dict[uuid.UUID, Account]:
        rows = (
            await self.db.scalars(
                select(Account).where(
                    Account.company_id == company_id,
                    Account.id.in_(account_ids),
                    Account.deleted_at.is_(None),
                )
            )
        ).all()
        if len(rows) != len(set(account_ids)):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Account not found")
        account_map = {account.id: account for account in rows}
        for account in rows:
            if account.is_header:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Header account cannot receive direct entries")
        return account_map

    def _ensure_balanced_request(self, data: CreateJournalEntryRequest) -> None:
        if len(data.lines) < 2:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="journal entry not balanced")
        debit_total = q2(sum((Decimal(line.debit_amount) for line in data.lines), Decimal("0")))
        credit_total = q2(sum((Decimal(line.credit_amount) for line in data.lines), Decimal("0")))
        if debit_total != credit_total:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="journal entry not balanced")
        if debit_total <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="journal entry not balanced")

    @staticmethod
    def _build_account_tree(accounts: list[Account]) -> list[Account]:
        account_map = {account.id: account for account in accounts}
        for account in accounts:
            # FIX S4-A-verify: avoid async lazy-loading on relationship access during tree serialization
            account.__dict__["tree_children"] = []
        roots: list[Account] = []
        for account in accounts:
            if account.parent_id and account.parent_id in account_map:
                account_map[account.parent_id].__dict__["tree_children"].append(account)
            else:
                roots.append(account)
        for account in account_map.values():
            account.__dict__["tree_children"].sort(key=lambda child: child.code)
        roots.sort(key=lambda account: account.code)
        return roots

    @staticmethod
    def serialize_account(account: Account) -> dict[str, object]:
        return {
            "id": account.id,
            "company_id": account.company_id,
            "parent_id": account.parent_id,
            "code": account.code,
            "name": account.name,
            "name_en": account.name_en,
            "account_type": account.account_type,
            "account_subtype": account.account_subtype,
            "normal_balance": account.normal_balance,
            "is_header": account.is_header,
            "is_active": account.is_active,
            "is_system": account.is_system,
            "description": account.description,
            "sort_order": account.sort_order,
            "created_at": account.created_at,
            "children": [
                AccountingService.serialize_account(child)
                for child in account.__dict__.get("tree_children", [])
            ],
        }

    @staticmethod
    def serialize_entry(entry: JournalEntry) -> dict[str, object]:
        return {
            "id": entry.id,
            "entry_number": entry.entry_number,
            "entry_date": entry.entry_date,
            "period_year": entry.period_year,
            "period_month": entry.period_month,
            "entry_type": entry.entry_type,
            "reference_type": entry.reference_type,
            "reference_id": entry.reference_id,
            "description": entry.description,
            "is_posted": entry.is_posted,
            "is_reversed": entry.is_reversed,
            "created_by": entry.created_by,
            "created_at": entry.created_at,
            "posted_at": entry.posted_at,
            "lines": [
                {
                    "id": line.id,
                    "entry_id": line.entry_id,
                    "account_id": line.account_id,
                    "line_number": line.line_number,
                    "description": line.description,
                    "debit_amount": q2(line.debit_amount),
                    "credit_amount": q2(line.credit_amount),
                    "account_code": line.account.code,
                    "account_name": line.account.name,
                }
                for line in entry.lines
            ],
            "total_debit": q2(sum((Decimal(line.debit_amount) for line in entry.lines), Decimal("0"))),
        }

    @staticmethod
    def serialize_entry_list_item(entry: JournalEntry) -> dict[str, object]:
        return {
            "id": entry.id,
            "entry_number": entry.entry_number,
            "entry_date": entry.entry_date,
            "entry_type": entry.entry_type,
            "description": entry.description,
            "is_posted": entry.is_posted,
            "total_debit": q2(sum((Decimal(line.debit_amount) for line in entry.lines), Decimal("0"))),
            "reference_type": entry.reference_type,
            "reference_id": entry.reference_id,
            "created_at": entry.created_at,
        }

    @staticmethod
    def _previous_period(period_year: int, period_month: int) -> tuple[int, int]:
        if period_month == 1:
            return period_year - 1, 12
        return period_year, period_month - 1

    @staticmethod
    def _periods_for_report(period_year: int, period_month: int, fiscal_year_start: int, cumulative: bool) -> list[tuple[int, int]]:
        if not cumulative:
            return [(period_year, period_month)]
        periods: list[tuple[int, int]] = []
        if period_month >= fiscal_year_start:
            for month in range(fiscal_year_start, period_month + 1):
                periods.append((period_year, month))
            return periods
        for month in range(fiscal_year_start, 13):
            periods.append((period_year - 1, month))
        for month in range(1, period_month + 1):
            periods.append((period_year, month))
        return periods

    @staticmethod
    def _profit_loss_value(normal_balance: str, debit_total: Decimal, credit_total: Decimal) -> Decimal:
        if normal_balance == "credit":
            return q2(Decimal(credit_total) - Decimal(debit_total))
        return q2(Decimal(debit_total) - Decimal(credit_total))

    @staticmethod
    def _build_profit_rows(
        account_map: dict[uuid.UUID, Account],
        totals: dict[uuid.UUID, Decimal],
        account_type: str,
        subtype: str | None = None,
        exclude_subtype: str | None = None,
    ) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for account_id, amount in totals.items():
            account = account_map[account_id]
            if account.account_type != account_type:
                continue
            if subtype is not None and account.account_subtype != subtype:
                continue
            if exclude_subtype is not None and account.account_subtype == exclude_subtype:
                continue
            if amount == 0:
                continue
            rows.append(
                {
                    "account_code": account.code,
                    "account_name": account.name,
                    "account_type": account.account_type,
                    "debit_balance": q2(amount if account.normal_balance == "debit" else 0),
                    "credit_balance": q2(amount if account.normal_balance == "credit" else 0),
                }
            )
        rows.sort(key=lambda row: str(row["account_code"]))
        return rows
