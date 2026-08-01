from __future__ import annotations

from typing import Any
import uuid

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, Request, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db, get_identity_db, get_restaurant_service_db
from app.dependencies import TokenData, get_current_user, require_any_permission, require_permission
from app.models.role import Permission
from app.schemas.role import PermissionRead
from app.schemas.product import BranchProductReplacementRuleCreate
from app.schemas.user_mgmt import (
    AcceptInvitationRequest,
    AssignBranchRequest,
    BranchCreateFull,
    BranchSettingsRead,
    BranchSettingsUpdate,
    BranchUpdateFull,
    ChangePasswordRequest,
    InviteUserRequest,
    InviteUserResponse,
    RemoveBranchRequest,
    RoleCreateFull,
    RoleUpdateFull,
    UserCreateFull,
    UserUpdateFull,
)
from app.schemas.user_access import (
    BranchAssignableRoleRead,
    UserAccessApprovalResult,
    UserAccessApproveRequest,
    UserAccessCancelRequest,
    UserAccessRejectRequest,
    UserAccessRequestCreate,
)
from app.schemas.staff_assignment import (
    StaffRoleAssignmentCreate,
    StaffRoleAssignmentRevoke,
)
from app.schemas.entitlement import BrandModuleEntitlementUpdate
from app.services.admin_service import AdminService
from app.services.role_preset_service import RolePresetService
from app.services.staff_scope_service import StaffScopeService
from app.services.upload_service import UploadService
from app.services.user_access_service import UserAccessService
from app.services.entitlement_service import CENTRAL_PRODUCTION_MODULE, EntitlementService
from app.services.tenant_control_policy import TenantControlPolicy
from app.utils.health_check import get_system_health
from app.utils.rate_limiter import check_rate_limit

router = APIRouter(prefix="/api/v1/system", tags=["system"])


def ok(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"data": data, "meta": {"version": settings.app_version, **(meta or {})}, "error": None}


async def _require_branch_access(
    service: AdminService,
    current: TokenData,
    branch_id: uuid.UUID,
) -> None:
    if "*" in current.permissions:
        return
    if current.branch_id == branch_id:
        return
    if await service.can_access_branch(current.company_id, current.user_id, branch_id):
        return
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found")


def _require_company_assignment_admin(current: TokenData) -> None:
    if "*" in current.permissions or "company" in current.scope_types:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Company scope is required to manage staff assignments",
    )


@router.get("/permissions")
async def get_permissions(
    _: TokenData = Depends(require_permission("system.role.view")),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    rows = await db.scalars(select(Permission).order_by(Permission.module, Permission.code))
    data = [PermissionRead.model_validate(permission).model_dump() for permission in rows.all()]
    return ok(data)


@router.get("/me/branches")
async def my_branches(
    current: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    data = await StaffScopeService(db).list_accessible_branches(
        current.company_id,
        current.user_id,
        is_superuser="*" in current.permissions,
    )
    return ok(data)


@router.get("/staff-assignment-options")
async def get_staff_assignment_options(
    current: TokenData = Depends(require_permission("system.user.edit")),
    db: AsyncSession = Depends(get_identity_db),
    restaurant_db: AsyncSession = Depends(get_restaurant_service_db),
) -> dict[str, Any]:
    _require_company_assignment_admin(current)
    data = await StaffScopeService(db, restaurant_db=restaurant_db).list_options(current.company_id)
    return ok(data.model_dump())


@router.get("/users/{user_id}/role-assignments")
async def get_user_role_assignments(
    user_id: uuid.UUID,
    current: TokenData = Depends(require_permission("system.user.edit")),
    db: AsyncSession = Depends(get_identity_db),
    include_revoked: bool = Query(default=False),
) -> dict[str, Any]:
    _require_company_assignment_admin(current)
    rows = await StaffScopeService(db).list_assignments(
        current.company_id,
        user_id,
        include_revoked=include_revoked,
    )
    return ok([row.model_dump() for row in rows])


@router.post("/users/{user_id}/role-assignments", status_code=status.HTTP_201_CREATED)
async def create_user_role_assignment(
    user_id: uuid.UUID,
    payload: StaffRoleAssignmentCreate,
    current: TokenData = Depends(require_permission("system.user.edit")),
    db: AsyncSession = Depends(get_identity_db),
    restaurant_db: AsyncSession = Depends(get_restaurant_service_db),
) -> dict[str, Any]:
    _require_company_assignment_admin(current)
    row = await StaffScopeService(db, restaurant_db=restaurant_db).create_assignment(
        current.company_id,
        user_id,
        current.user_id,
        payload,
    )
    return ok(row.model_dump())


@router.post("/users/{user_id}/role-assignments/{assignment_id}/revoke")
async def revoke_user_role_assignment(
    user_id: uuid.UUID,
    assignment_id: uuid.UUID,
    payload: StaffRoleAssignmentRevoke,
    current: TokenData = Depends(require_permission("system.user.edit")),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    _require_company_assignment_admin(current)
    row = await StaffScopeService(db).revoke_assignment(
        current.company_id,
        user_id,
        assignment_id,
        current.user_id,
        payload.reason,
    )
    return ok(row.model_dump())


@router.get("/brands/{brand_id}/modules/central-production")
async def get_central_production_entitlement(
    brand_id: uuid.UUID,
    current: TokenData = Depends(require_permission("system.company.view")),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    _require_company_assignment_admin(current)
    row = await EntitlementService(db).get_brand_module(
        current.company_id,
        brand_id,
        CENTRAL_PRODUCTION_MODULE,
    )
    return ok(row.model_dump(mode="json"))


@router.put("/brands/{brand_id}/modules/central-production")
async def update_central_production_entitlement(
    brand_id: uuid.UUID,
    payload: BrandModuleEntitlementUpdate,
    current: TokenData = Depends(require_permission("system.company.edit")),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    _require_company_assignment_admin(current)
    row = await EntitlementService(db).set_brand_module(
        current.company_id,
        brand_id,
        CENTRAL_PRODUCTION_MODULE,
        is_enabled=payload.is_enabled,
        config=payload.config,
        actor_id=current.user_id,
    )
    return ok(row.model_dump(mode="json"))


@router.get("/users")
async def get_users(
    current: TokenData = Depends(require_permission("system.user.view")),
    db: AsyncSession = Depends(get_db),
    branch_id: uuid.UUID | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    service = AdminService(db)
    effective_branch_id = branch_id
    if "*" not in current.permissions and "company" not in current.scope_types:
        if branch_id and branch_id != current.branch_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Branch access denied")
        effective_branch_id = current.branch_id

    users, total = await service.list_users(
        company_id=current.company_id,
        branch_id=effective_branch_id,
        is_active=is_active,
        search=search,
        page=page,
        limit=limit,
    )
    data = [item.model_dump() for item in await service.serialize_users(users)]
    return ok(data, meta={"total": total, "page": page, "limit": limit})


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreateFull,
    current: TokenData = Depends(require_permission("system.user.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await TenantControlPolicy(db).require_capacity(current.company_id, "users")
    service = AdminService(db)
    user = await service.create_user(current.company_id, current.user_id, payload)
    detail = await service.get_user_detail(user.id, current.company_id)
    return ok(detail.model_dump())


@router.get("/users/{user_id}")
async def get_user_detail(
    user_id: uuid.UUID,
    current: TokenData = Depends(require_permission("system.user.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = AdminService(db)
    detail = await service.get_user_detail(user_id, current.company_id)
    if (
        "*" not in current.permissions
        and "company" not in current.scope_types
        and current.branch_id not in {item.branch_id for item in detail.branches}
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return ok(detail.model_dump())


@router.patch("/users/{user_id}")
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdateFull,
    current: TokenData = Depends(require_permission("system.user.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = AdminService(db)
    if "*" not in current.permissions and "company" not in current.scope_types:
        detail = await service.get_user_detail(user_id, current.company_id)
        if current.branch_id not in {item.branch_id for item in detail.branches}:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    await service.update_user(user_id, current.company_id, payload)
    detail = await service.get_user_detail(user_id, current.company_id)
    return ok(detail.model_dump())


@router.post("/users/{user_id}/deactivate")
async def deactivate_user(
    user_id: uuid.UUID,
    current: TokenData = Depends(require_permission("system.user.delete")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = AdminService(db)
    await service.deactivate_user(user_id, current.company_id, current.user_id)
    detail = await service.get_user_detail(user_id, current.company_id)
    return ok(detail.model_dump())


@router.post("/users/{user_id}/change-password")
async def change_user_password(
    user_id: uuid.UUID,
    payload: ChangePasswordRequest,
    current: TokenData = Depends(require_permission("system.user.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = AdminService(db)
    await service.change_user_password(user_id, current.company_id, current.user_id, payload)
    return ok({"message": "Password changed"})


@router.post("/users/{user_id}/branches")
async def assign_user_branch(
    user_id: uuid.UUID,
    payload: AssignBranchRequest,
    current: TokenData = Depends(require_permission("system.user.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = AdminService(db)
    await service.assign_branch(user_id, current.company_id, payload)
    detail = await service.get_user_detail(user_id, current.company_id)
    return ok(detail.model_dump())


@router.delete("/users/{user_id}/branches/{branch_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_user_branch(
    user_id: uuid.UUID,
    branch_id: uuid.UUID,
    current: TokenData = Depends(require_permission("system.user.edit")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    service = AdminService(db)
    await service.remove_branch(user_id, current.company_id, RemoveBranchRequest(branch_id=branch_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/roles")
async def get_roles(
    current: TokenData = Depends(require_permission("system.role.view")),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    service = AdminService(db)
    data = [role.model_dump() for role in await service.list_roles(current.company_id)]
    return ok(data)


@router.get("/role-presets")
async def get_role_presets(
    _: TokenData = Depends(require_permission("system.role.view")),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    data = [preset.model_dump() for preset in await RolePresetService(db).list_presets()]
    return ok(data)


@router.post("/roles", status_code=status.HTTP_201_CREATED)
async def create_role(
    payload: RoleCreateFull,
    current: TokenData = Depends(require_permission("system.role.create")),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    service = AdminService(db)
    role = await service.create_role(current.company_id, payload)
    detail = await service.get_role_detail(role.id, current.company_id)
    return ok(detail.model_dump())


@router.patch("/roles/{role_id}")
async def update_role(
    role_id: uuid.UUID,
    payload: RoleUpdateFull,
    current: TokenData = Depends(require_permission("system.role.edit")),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    service = AdminService(db)
    role = await service.update_role(role_id, current.company_id, payload)
    detail = await service.get_role_detail(role.id, current.company_id)
    return ok(detail.model_dump())


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: uuid.UUID,
    current: TokenData = Depends(require_permission("system.role.delete")),
    db: AsyncSession = Depends(get_identity_db),
) -> Response:
    service = AdminService(db)
    await service.delete_role(role_id, current.company_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/branches")
async def get_branches(
    current: TokenData = Depends(require_permission("system.branch.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = AdminService(db)
    data = [branch.model_dump() for branch in await service.list_branches(current.company_id, current)]
    return ok(data)


@router.post("/branches", status_code=status.HTTP_201_CREATED)
async def create_branch(
    payload: BranchCreateFull,
    current: TokenData = Depends(require_permission("system.branch.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await TenantControlPolicy(db).require_capacity(current.company_id, "branches")
    service = AdminService(db)
    branch = await service.create_branch(current.company_id, payload)
    detail = await service.get_branch_detail(branch.id, current.company_id)
    return ok(detail.model_dump())


@router.get("/branches/{branch_id}")
async def get_branch_detail(
    branch_id: uuid.UUID,
    current: TokenData = Depends(require_permission("system.branch.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = AdminService(db)
    await _require_branch_access(service, current, branch_id)
    detail = await service.get_branch_detail(branch_id, current.company_id)
    return ok(detail.model_dump())


@router.patch("/branches/{branch_id}")
async def update_branch(
    branch_id: uuid.UUID,
    payload: BranchUpdateFull,
    current: TokenData = Depends(require_permission("system.branch.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = AdminService(db)
    await _require_branch_access(service, current, branch_id)
    branch = await service.update_branch(branch_id, current.company_id, payload)
    detail = await service.get_branch_detail(branch.id, current.company_id)
    return ok(detail.model_dump())


@router.get("/branches/{branch_id}/settings")
async def get_branch_settings(
    branch_id: uuid.UUID,
    current: TokenData = Depends(require_permission("system.branch.view")),
    db: AsyncSession = Depends(get_restaurant_service_db),
    identity_db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    service = AdminService(db)
    await _require_branch_access(AdminService(identity_db), current, branch_id)
    settings_row = await service.get_branch_settings(branch_id, current.company_id)
    settings_data: BranchSettingsRead = service.serialize_branch_settings(settings_row)
    return ok(
        settings_data.model_dump(),
        {"restaurant_service_database": settings.restaurant_service_database},
    )


@router.patch("/branches/{branch_id}/settings")
async def update_branch_settings(
    branch_id: uuid.UUID,
    payload: BranchSettingsUpdate,
    current: TokenData = Depends(require_permission("system.branch.edit")),
    db: AsyncSession = Depends(get_restaurant_service_db),
    identity_db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    service = AdminService(db)
    await _require_branch_access(AdminService(identity_db), current, branch_id)
    settings_row = await service.update_branch_settings(branch_id, current.company_id, payload)
    settings_data: BranchSettingsRead = service.serialize_branch_settings(settings_row)
    return ok(
        settings_data.model_dump(),
        {"restaurant_service_database": settings.restaurant_service_database},
    )


@router.post("/branches/{branch_id}/settings/promptpay-qr")
async def upload_branch_promptpay_qr(
    branch_id: uuid.UUID,
    qr: UploadFile = File(...),
    current: TokenData = Depends(require_permission("system.branch.edit")),
    db: AsyncSession = Depends(get_restaurant_service_db),
    identity_db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    service = AdminService(db)
    await _require_branch_access(AdminService(identity_db), current, branch_id)
    current_settings = await service.get_branch_settings(branch_id, current.company_id)
    previous_url = current_settings.promptpay_qr_url
    upload_service = UploadService()
    qr_url = await upload_service.save_image(qr, "promptpay-qr", str(current.company_id))
    try:
        settings_row = await service.update_branch_settings(
            branch_id,
            current.company_id,
            BranchSettingsUpdate(promptpay_qr_url=qr_url),
        )
    except Exception:
        await upload_service.delete_image(qr_url)
        raise
    if previous_url and previous_url != qr_url:
        await upload_service.delete_image(previous_url)
    return ok(
        service.serialize_branch_settings(settings_row).model_dump(),
        {"restaurant_service_database": settings.restaurant_service_database},
    )


@router.delete("/branches/{branch_id}/settings/promptpay-qr")
async def delete_branch_promptpay_qr(
    branch_id: uuid.UUID,
    current: TokenData = Depends(require_permission("system.branch.edit")),
    db: AsyncSession = Depends(get_restaurant_service_db),
    identity_db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    service = AdminService(db)
    await _require_branch_access(AdminService(identity_db), current, branch_id)
    current_settings = await service.get_branch_settings(branch_id, current.company_id)
    previous_url = current_settings.promptpay_qr_url
    settings_row = await service.update_branch_settings(
        branch_id,
        current.company_id,
        BranchSettingsUpdate(promptpay_qr_url=None),
    )
    if previous_url:
        await UploadService().delete_image(previous_url)
    return ok(
        service.serialize_branch_settings(settings_row).model_dump(),
        {"restaurant_service_database": settings.restaurant_service_database},
    )


@router.post("/branches/{branch_id}/settings/receipt-logo")
async def upload_branch_receipt_logo(
    branch_id: uuid.UUID,
    logo: UploadFile = File(...),
    current: TokenData = Depends(require_permission("system.branch.edit")),
    db: AsyncSession = Depends(get_restaurant_service_db),
    identity_db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    service = AdminService(db)
    await _require_branch_access(AdminService(identity_db), current, branch_id)
    current_settings = await service.get_branch_settings(branch_id, current.company_id)
    previous_url = current_settings.receipt_logo_url
    upload_service = UploadService()
    logo_url = await upload_service.save_image(logo, "receipt-logo", str(current.company_id))
    try:
        settings_row = await service.update_branch_settings(
            branch_id,
            current.company_id,
            BranchSettingsUpdate(receipt_logo_url=logo_url, receipt_show_logo=True),
        )
    except Exception:
        await upload_service.delete_image(logo_url)
        raise
    if previous_url and previous_url != logo_url:
        await upload_service.delete_image(previous_url)
    return ok(
        service.serialize_branch_settings(settings_row).model_dump(),
        {"restaurant_service_database": settings.restaurant_service_database},
    )


@router.delete("/branches/{branch_id}/settings/receipt-logo")
async def delete_branch_receipt_logo(
    branch_id: uuid.UUID,
    current: TokenData = Depends(require_permission("system.branch.edit")),
    db: AsyncSession = Depends(get_restaurant_service_db),
    identity_db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    service = AdminService(db)
    await _require_branch_access(AdminService(identity_db), current, branch_id)
    current_settings = await service.get_branch_settings(branch_id, current.company_id)
    previous_url = current_settings.receipt_logo_url
    settings_row = await service.update_branch_settings(
        branch_id,
        current.company_id,
        BranchSettingsUpdate(receipt_logo_url=None, receipt_show_logo=False),
    )
    if previous_url:
        await UploadService().delete_image(previous_url)
    return ok(
        service.serialize_branch_settings(settings_row).model_dump(),
        {"restaurant_service_database": settings.restaurant_service_database},
    )


@router.get("/branches/{branch_id}/replacement-rules")
async def get_branch_replacement_rules(
    branch_id: uuid.UUID,
    current: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = AdminService(db)
    await _require_branch_access(service, current, branch_id)
    data = [item.model_dump() for item in await service.list_branch_replacement_rules(branch_id, current.company_id)]
    return ok(data)


@router.post("/branches/{branch_id}/replacement-rules", status_code=status.HTTP_201_CREATED)
async def upsert_branch_replacement_rule(
    branch_id: uuid.UUID,
    payload: BranchProductReplacementRuleCreate,
    current: TokenData = Depends(require_permission("system.branch.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = AdminService(db)
    await _require_branch_access(service, current, branch_id)
    row = await service.upsert_branch_replacement_rule(branch_id, current.company_id, current.user_id, payload)
    detail = await service.list_branch_replacement_rules(branch_id, current.company_id)
    current_row = next(item for item in detail if item.id == row.id)
    return ok(current_row.model_dump())


@router.delete("/branches/{branch_id}/replacement-rules/{source_product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_branch_replacement_rule(
    branch_id: uuid.UUID,
    source_product_id: uuid.UUID,
    current: TokenData = Depends(require_permission("system.branch.edit")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    service = AdminService(db)
    await _require_branch_access(service, current, branch_id)
    await service.delete_branch_replacement_rule(branch_id, current.company_id, current.user_id, source_product_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/branch-assignable-roles")
async def get_branch_assignable_roles(
    current: TokenData = Depends(
        require_any_permission("system.user.request", "system.user.approve")
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    roles = await UserAccessService(db).list_branch_assignable_roles(current.company_id)
    return ok(
        [
            BranchAssignableRoleRead(
                id=role.id,
                name=role.name,
                description=role.description,
            ).model_dump()
            for role in roles
        ]
    )


@router.post("/user-access-requests", status_code=status.HTTP_201_CREATED)
async def create_user_access_request(
    payload: UserAccessRequestCreate,
    current: TokenData = Depends(require_permission("system.user.request")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if current.branch_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch context is required")
    row = await UserAccessService(db).create_request(
        current.company_id,
        current.branch_id,
        current.user_id,
        payload,
    )
    return ok(row.model_dump())


@router.get("/user-access-requests/mine")
async def get_my_branch_user_access_requests(
    current: TokenData = Depends(require_permission("system.user.request")),
    db: AsyncSession = Depends(get_db),
    brand_slug: str = Query(min_length=1, max_length=80),
    request_status: str | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    if current.branch_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch context is required")
    service = UserAccessService(db)
    brand = await service.get_brand_for_branch_access(
        current.company_id,
        current.branch_id,
        brand_slug,
    )
    rows, total = await service.list_requests(
        current.company_id,
        branch_id=current.branch_id,
        brand_id=brand.id,
        request_status=request_status,
        search=search,
        page=page,
        limit=limit,
    )
    return ok(
        [row.model_dump() for row in rows],
        meta={"total": total, "page": page, "limit": limit},
    )


@router.get("/user-access-requests")
async def get_company_user_access_requests(
    current: TokenData = Depends(require_permission("system.user.approve")),
    db: AsyncSession = Depends(get_db),
    brand_slug: str | None = Query(default=None, min_length=1, max_length=80),
    branch_id: uuid.UUID | None = Query(default=None),
    request_status: str | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    service = UserAccessService(db)
    is_superuser = "*" in current.permissions
    brand_id: uuid.UUID | None = None
    if brand_slug:
        brand = await service.get_brand_for_central_access(
            current.company_id,
            brand_slug,
            current.branch_id,
            is_superuser=is_superuser,
        )
        brand_id = brand.id
    elif not is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Company-wide request access requires superuser",
        )
    rows, total = await service.list_requests(
        current.company_id,
        branch_id=branch_id,
        brand_id=brand_id,
        request_status=request_status,
        search=search,
        page=page,
        limit=limit,
    )
    return ok(
        [row.model_dump() for row in rows],
        meta={"total": total, "page": page, "limit": limit},
    )


@router.get("/user-access-requests/{request_id}")
async def get_user_access_request(
    request_id: uuid.UUID,
    current: TokenData = Depends(
        require_any_permission("system.user.request", "system.user.approve")
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await UserAccessService(db).get_request_read(request_id, current.company_id)
    if "*" not in current.permissions and "system.user.approve" in current.permissions:
        await UserAccessService(db).ensure_request_review_access(
            request_id,
            current.company_id,
            current.branch_id,
            is_superuser=False,
        )
    elif "*" not in current.permissions:
        if current.branch_id is None or row.branch_id != current.branch_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    return ok(row.model_dump())


@router.post("/user-access-requests/{request_id}/approve")
async def approve_user_access_request(
    request_id: uuid.UUID,
    payload: UserAccessApproveRequest,
    current: TokenData = Depends(require_permission("system.user.approve")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row, invitation, plain_otp = await UserAccessService(db).approve_request(
        request_id,
        current.company_id,
        current.user_id,
        payload,
        allow_self_approval="*" in current.permissions,
        reviewer_branch_id=current.branch_id,
        is_superuser="*" in current.permissions,
    )
    result = UserAccessApprovalResult(
        request=row,
        activation_mode="invitation" if invitation else "activated",
        created_username=row.activated_username,
        invitation_id=invitation.id if invitation else None,
        company_id=current.company_id,
        otp_code=plain_otp,
        expires_at=invitation.expires_at if invitation else None,
    )
    return ok(result.model_dump())


@router.post("/user-access-requests/{request_id}/reject")
async def reject_user_access_request(
    request_id: uuid.UUID,
    payload: UserAccessRejectRequest,
    current: TokenData = Depends(require_permission("system.user.approve")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await UserAccessService(db).reject_request(
        request_id,
        current.company_id,
        current.user_id,
        payload.reason,
        reviewer_branch_id=current.branch_id,
        is_superuser="*" in current.permissions,
    )
    return ok(row.model_dump())


@router.post("/user-access-requests/{request_id}/cancel")
async def cancel_user_access_request(
    request_id: uuid.UUID,
    payload: UserAccessCancelRequest,
    current: TokenData = Depends(require_permission("system.user.request")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if current.branch_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch context is required")
    row = await UserAccessService(db).cancel_request(
        request_id,
        current.company_id,
        current.branch_id,
        current.user_id,
        payload.brand_slug,
        payload.reason,
    )
    return ok(row.model_dump())


@router.post("/user-access-requests/{request_id}/resend-invitation")
async def resend_user_access_invitation(
    request_id: uuid.UUID,
    current: TokenData = Depends(require_permission("system.user.approve")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row, invitation, plain_otp = await UserAccessService(db).resend_invitation(
        request_id,
        current.company_id,
        current.user_id,
        reviewer_branch_id=current.branch_id,
        is_superuser="*" in current.permissions,
    )
    result = UserAccessApprovalResult(
        request=row,
        activation_mode="invitation",
        created_username=None,
        invitation_id=invitation.id,
        company_id=current.company_id,
        otp_code=plain_otp,
        expires_at=invitation.expires_at,
    )
    return ok(result.model_dump())


@router.post("/invitations", status_code=status.HTTP_201_CREATED)
async def create_invitation(
    payload: InviteUserRequest,
    current: TokenData = Depends(require_permission("system.user.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = AdminService(db)
    invitation, plain_otp = await service.create_invitation(current.company_id, current.user_id, payload)
    response = InviteUserResponse(
        invitation_id=invitation.id,
        otp_code=plain_otp,
        expires_at=invitation.expires_at,
        message="Invitation created successfully",
    )
    return ok(response.model_dump())


@router.post("/invitations/accept")
async def accept_invitation(
    payload: AcceptInvitationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_company_id: str | None = Header(default=None, alias="X-Company-ID"),
) -> dict[str, Any]:
    if not x_company_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Company ID is required")
    try:
        company_id = uuid.UUID(x_company_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Company ID") from exc
    client_ip = request.client.host if request.client else "unknown"
    rate_key = payload.invitation_id or company_id
    try:
        allowed, _, _ = await check_rate_limit(
            f"invitation:{rate_key}:{client_ip}",
            limit=10,
            window_seconds=300,
        )
    except Exception:
        allowed = True
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="ลองรหัสคำเชิญเกินกำหนด กรุณารอ 5 นาที",
        )
    await UserAccessService(db).accept_invitation(company_id, payload)
    return ok({"message": "บัญชีสร้างแล้ว กรุณาเข้าสู่ระบบ"})


@router.get("/health-detail")
async def health_detail(
    current: TokenData = Depends(require_permission("system.company.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    data = await get_system_health(db, current.company_id)
    return ok(data)
