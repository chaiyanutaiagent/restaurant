from __future__ import annotations

from dataclasses import dataclass
import unittest
import uuid

from pydantic import ValidationError

from app.business_context import CanonicalBusinessContext
from app.schemas.staff_assignment import StaffRoleAssignmentCreate, StaffRoleAssignmentRevoke
from app.schemas.user_mgmt import RoleCreateFull, RoleUpdateFull
from app.services.staff_scope_policy import (
    assignment_applies_to_context,
    assignment_scope_key,
    normalized_station_key,
)
from app.utils.security import create_access_token, create_refresh_token, decode_token


@dataclass
class AssignmentStub:
    scope_type: str
    brand_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None
    station_key: str | None = None


class StaffScopePolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = CanonicalBusinessContext(
            company_id=uuid.uuid4(),
            brand_id=uuid.uuid4(),
            branch_id=uuid.uuid4(),
            business_type="restaurant",
            target_database="restaurant",
        )

    def test_company_brand_branch_and_station_boundaries(self) -> None:
        self.assertTrue(
            assignment_applies_to_context(AssignmentStub(scope_type="company"), self.context, None)
        )
        self.assertTrue(
            assignment_applies_to_context(
                AssignmentStub(scope_type="brand", brand_id=self.context.brand_id),
                self.context,
                None,
            )
        )
        self.assertFalse(
            assignment_applies_to_context(
                AssignmentStub(scope_type="brand", brand_id=uuid.uuid4()),
                self.context,
                None,
            )
        )
        self.assertTrue(
            assignment_applies_to_context(
                AssignmentStub(scope_type="branch", branch_id=self.context.branch_id),
                self.context,
                None,
            )
        )
        station = AssignmentStub(
            scope_type="station",
            branch_id=self.context.branch_id,
            station_key=" ครัวหลัก ",
        )
        self.assertTrue(assignment_applies_to_context(station, self.context, "ครัวหลัก"))
        self.assertFalse(assignment_applies_to_context(station, self.context, "Bar"))
        self.assertFalse(assignment_applies_to_context(station, self.context, None))

    def test_station_scope_key_is_casefolded_and_branch_bound(self) -> None:
        key = assignment_scope_key(
            company_id=self.context.company_id,
            scope_type="station",
            brand_id=self.context.brand_id,
            branch_id=self.context.branch_id,
            station_key="  BAR  ",
        )
        self.assertEqual(key, f"{self.context.branch_id}:bar")
        self.assertEqual(normalized_station_key("  ครัวหลัก  "), "ครัวหลัก")


class StaffAssignmentSchemaTests(unittest.TestCase):
    def test_scope_target_shapes_are_server_safe(self) -> None:
        role_id = uuid.uuid4()
        branch_id = uuid.uuid4()
        brand_id = uuid.uuid4()
        self.assertEqual(
            StaffRoleAssignmentCreate(
                role_id=role_id,
                scope_type="company",
                reason=" owner ",
            ).reason,
            "owner",
        )
        self.assertEqual(
            StaffRoleAssignmentCreate(
                role_id=role_id,
                scope_type="brand",
                brand_id=brand_id,
                reason="brand lead",
            ).brand_id,
            brand_id,
        )
        station = StaffRoleAssignmentCreate(
            role_id=role_id,
            scope_type="station",
            branch_id=branch_id,
            station_key=" ครัวหลัก ",
            reason="kitchen",
        )
        self.assertEqual(station.station_key, "ครัวหลัก")

        invalid_payloads = (
            {"scope_type": "company", "branch_id": branch_id},
            {"scope_type": "brand"},
            {"scope_type": "branch", "branch_id": branch_id, "brand_id": brand_id},
            {"scope_type": "station", "branch_id": branch_id},
        )
        for payload in invalid_payloads:
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                StaffRoleAssignmentCreate(role_id=role_id, reason="test", **payload)

    def test_assignment_and_revocation_reasons_cannot_be_blank(self) -> None:
        with self.assertRaises(ValidationError):
            StaffRoleAssignmentCreate(
                role_id=uuid.uuid4(),
                scope_type="company",
                reason="   ",
            )
        with self.assertRaises(ValidationError):
            StaffRoleAssignmentRevoke(reason="   ")

    def test_role_allowed_scopes_are_nonempty_and_unique(self) -> None:
        role = RoleCreateFull(
            name="Cashier",
            permission_ids=[],
            allowed_scope_types=["branch", "station"],
        )
        self.assertEqual(role.allowed_scope_types, ["branch", "station"])
        with self.assertRaises(ValidationError):
            RoleCreateFull(name="Broken", permission_ids=[], allowed_scope_types=[])
        with self.assertRaises(ValidationError):
            RoleUpdateFull(allowed_scope_types=["branch", "branch"])


class StaffScopeTokenTests(unittest.TestCase):
    def test_access_and_refresh_tokens_carry_server_scope_context(self) -> None:
        user_id = uuid.uuid4()
        company_id = uuid.uuid4()
        branch_id = uuid.uuid4()
        assignment_id = uuid.uuid4()
        access = decode_token(
            create_access_token(
                subject=str(user_id),
                company_id=str(company_id),
                branch_id=str(branch_id),
                permissions=["fb.kitchen.ticket.manage"],
                station_key="ครัวหลัก",
                assignment_ids=[str(assignment_id)],
                scope_types=["station"],
            )
        )
        self.assertEqual(access["station_key"], "ครัวหลัก")
        self.assertEqual(access["assignment_ids"], [str(assignment_id)])
        self.assertEqual(access["scope_types"], ["station"])

        refresh = decode_token(
            create_refresh_token(
                str(user_id),
                str(company_id),
                branch_id=str(branch_id),
                station_key="ครัวหลัก",
            )
        )
        self.assertEqual(refresh["branch_id"], str(branch_id))
        self.assertEqual(refresh["station_key"], "ครัวหลัก")


if __name__ == "__main__":
    unittest.main()
