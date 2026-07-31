"""archive default BKK-02 branch

Revision ID: 6b7c8d9e0f12
Revises: 5a6b7c8d9e01
Create Date: 2026-07-31 23:50:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "6b7c8d9e0f12"
down_revision: Union[str, None] = "5a6b7c8d9e01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DEFAULT_COMPANY_ID = "1b8a1818-44d6-4d5f-9d22-e5e17b23c081"


def upgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM branches AS branch
                JOIN sale_orders AS sale_order ON sale_order.branch_id = branch.id
                WHERE branch.company_id = '{DEFAULT_COMPANY_ID}'::uuid
                  AND branch.code = 'BKK-02'
            ) OR EXISTS (
                SELECT 1
                FROM branches AS branch
                JOIN dining_sessions AS dining_session ON dining_session.branch_id = branch.id
                WHERE branch.company_id = '{DEFAULT_COMPANY_ID}'::uuid
                  AND branch.code = 'BKK-02'
            ) OR EXISTS (
                SELECT 1
                FROM branches AS branch
                JOIN stock_movements AS movement ON movement.branch_id = branch.id
                WHERE branch.company_id = '{DEFAULT_COMPANY_ID}'::uuid
                  AND branch.code = 'BKK-02'
            ) OR EXISTS (
                SELECT 1
                FROM branches AS branch
                JOIN stock_balances AS balance ON balance.branch_id = branch.id
                WHERE branch.company_id = '{DEFAULT_COMPANY_ID}'::uuid
                  AND branch.code = 'BKK-02'
                  AND (balance.qty_on_hand <> 0 OR balance.qty_reserved <> 0)
            ) THEN
                RAISE EXCEPTION
                    'P1-BRANCH-CLEANUP-02 refuses to archive BKK-02 with operational data';
            END IF;

            IF EXISTS (
                SELECT 1
                FROM branches AS branch
                JOIN user_branches AS assignment ON assignment.branch_id = branch.id
                JOIN users AS app_user ON app_user.id = assignment.user_id
                WHERE branch.company_id = '{DEFAULT_COMPANY_ID}'::uuid
                  AND branch.code = 'BKK-02'
                  AND assignment.deleted_at IS NULL
                  AND app_user.username <> 'admin'
            ) THEN
                RAISE EXCEPTION
                    'P1-BRANCH-CLEANUP-02 found a non-admin active assignment at BKK-02';
            END IF;
        END
        $$
        """
    )
    op.execute(
        f"""
        UPDATE user_branches AS assignment
        SET deleted_at = now(),
            is_default = false
        FROM users AS app_user, branches AS branch
        WHERE assignment.user_id = app_user.id
          AND assignment.branch_id = branch.id
          AND branch.company_id = '{DEFAULT_COMPANY_ID}'::uuid
          AND branch.code = 'BKK-02'
          AND app_user.company_id = branch.company_id
          AND app_user.username = 'admin'
          AND assignment.deleted_at IS NULL
        """
    )
    op.execute(
        f"""
        UPDATE stock_locations AS location
        SET is_active = false,
            updated_at = now()
        FROM branches AS branch
        WHERE location.branch_id = branch.id
          AND branch.company_id = '{DEFAULT_COMPANY_ID}'::uuid
          AND branch.code = 'BKK-02'
          AND location.deleted_at IS NULL
        """
    )
    op.execute(
        f"""
        UPDATE branches
        SET is_active = false,
            updated_at = now()
        WHERE company_id = '{DEFAULT_COMPANY_ID}'::uuid
          AND code = 'BKK-02'
          AND deleted_at IS NULL
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        UPDATE branches
        SET is_active = true,
            updated_at = now()
        WHERE company_id = '{DEFAULT_COMPANY_ID}'::uuid
          AND code = 'BKK-02'
          AND deleted_at IS NULL
        """
    )
    op.execute(
        f"""
        UPDATE stock_locations AS location
        SET is_active = true,
            updated_at = now()
        FROM branches AS branch
        WHERE location.branch_id = branch.id
          AND branch.company_id = '{DEFAULT_COMPANY_ID}'::uuid
          AND branch.code = 'BKK-02'
          AND location.deleted_at IS NULL
        """
    )
    op.execute(
        f"""
        UPDATE user_branches AS assignment
        SET deleted_at = NULL,
            is_default = false
        FROM users AS app_user, branches AS branch
        WHERE assignment.user_id = app_user.id
          AND assignment.branch_id = branch.id
          AND branch.company_id = '{DEFAULT_COMPANY_ID}'::uuid
          AND branch.code = 'BKK-02'
          AND app_user.company_id = branch.company_id
          AND app_user.username = 'admin'
        """
    )
