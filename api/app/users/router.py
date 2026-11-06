"""User allow-list and roles. Admin only."""

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.audit.service import record
from app.auth import sessions
from app.auth.deps import Principal, RequireAdmin
from app.config import get_settings
from app.core.errors import STALE_MESSAGE
from app.core.net import client_ip
from app.core.pagination import Page, PageNo, PageSize, SearchText
from app.db import get_db
from app.users.models import AppUser, Role
from app.users.schemas import UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/api/users", tags=["users"])

DbDep = Annotated[Session, Depends(get_db)]

SORTABLE = {
    "email": AppUser.email,
    "display_name": AppUser.display_name,
    "role": AppUser.role,
    "last_login_at": AppUser.last_login_at,
    "created_at": AppUser.created_at,
}
AUDIT_FIELDS = ("email", "display_name", "role", "is_active")


def _snapshot(user: AppUser) -> dict[str, Any]:
    return {f: getattr(user, f) for f in AUDIT_FIELDS}


def _get(db: Session, user_id: uuid.UUID) -> AppUser:
    user = db.get(AppUser, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return user


@router.get("")
def list_users(
    _: RequireAdmin,
    db: DbDep,
    q: SearchText = None,
    role: Role | None = None,
    active: bool | None = None,
    sort: Annotated[Literal[tuple(SORTABLE)], Query()] = "email",  # type: ignore[valid-type]
    order: Literal["asc", "desc"] = "asc",
    page: PageNo = 1,
    page_size: PageSize = 25,
) -> Page[UserOut]:
    stmt = select(AppUser)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(AppUser.email.ilike(like), AppUser.display_name.ilike(like)))
    if role is not None:
        stmt = stmt.where(AppUser.role == role.value)
    if active is not None:
        stmt = stmt.where(AppUser.is_active.is_(active))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    column = SORTABLE[sort]
    ordering = column.desc().nulls_last() if order == "desc" else column.asc().nulls_last()
    rows = db.scalars(
        stmt.order_by(ordering, AppUser.id).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return Page(
        items=[UserOut.model_validate(u) for u in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{user_id}")
def get_user(_: RequireAdmin, db: DbDep, user_id: uuid.UUID) -> UserOut:
    return UserOut.model_validate(_get(db, user_id))


@router.post("", status_code=status.HTTP_201_CREATED)
def create_user(admin: RequireAdmin, db: DbDep, body: UserCreate, request: Request) -> UserOut:
    domain = get_settings().allowed_hosted_domain
    if not body.email.endswith("@" + domain):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Only @{domain} addresses can sign in"
        )
    if db.scalar(select(AppUser.id).where(AppUser.email == body.email)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "A user with this email already exists")
    user = AppUser(
        email=body.email,
        display_name=body.display_name,
        role=body.role.value,
        created_by=admin.user_id,
        updated_by=admin.user_id,
    )
    db.add(user)
    db.flush()
    record(
        db,
        entity="app_user",
        entity_id=user.id,
        action="create",
        user_id=admin.user_id,
        user_email=admin.email,
        new=_snapshot(user),
        ip=client_ip(request),
    )
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.patch("/{user_id}")
def update_user(
    admin: RequireAdmin, db: DbDep, user_id: uuid.UUID, body: UserUpdate, request: Request
) -> UserOut:
    user = _get(db, user_id)
    _check_version(user, body.version)
    old = _snapshot(user)
    changes = body.model_dump(exclude_unset=True, exclude={"version"})
    if "role" in changes and changes["role"] is not None:
        changes["role"] = changes["role"].value
    _guard_self(admin, user, changes)
    for field, value in changes.items():
        if field in {"role", "is_active"} and value is None:
            continue
        setattr(user, field, value)
    user.updated_by = admin.user_id
    if changes.get("is_active") is False:
        sessions.revoke_all_for_user(db, user.id)
    _audit_and_commit(db, admin, user, "update", old, request)
    return UserOut.model_validate(user)


@router.delete("/{user_id}")
def deactivate_user(
    admin: RequireAdmin,
    db: DbDep,
    user_id: uuid.UUID,
    request: Request,
    version: Annotated[int, Query(ge=1)],
) -> UserOut:
    """Remove = soft delete: the user can no longer sign in. History is kept."""
    user = _get(db, user_id)
    _check_version(user, version)
    _guard_self(admin, user, {"is_active": False})
    old = _snapshot(user)
    user.is_active = False
    user.updated_by = admin.user_id
    sessions.revoke_all_for_user(db, user.id)
    _audit_and_commit(db, admin, user, "deactivate", old, request)
    return UserOut.model_validate(user)


def _check_version(user: AppUser, version: int) -> None:
    if user.version != version:
        raise HTTPException(status.HTTP_409_CONFLICT, STALE_MESSAGE)


def _guard_self(admin: Principal, user: AppUser, changes: dict[str, Any]) -> None:
    """An admin can't lock themselves out (there must always be one who can fix things)."""
    if user.id != admin.user_id:
        return
    if changes.get("is_active") is False or changes.get("role") not in (None, Role.ADMIN.value):
        raise HTTPException(status.HTTP_409_CONFLICT, "You can't remove your own admin access")


def _audit_and_commit(
    db: Session,
    admin: Principal,
    user: AppUser,
    action: str,
    old: dict[str, Any],
    request: Request,
) -> None:
    db.flush()  # runs the versioned UPDATE; a concurrent change raises StaleDataError → 409
    record(
        db,
        entity="app_user",
        entity_id=user.id,
        action=action,
        user_id=admin.user_id,
        user_email=admin.email,
        old=old,
        new=_snapshot(user),
        ip=client_ip(request),
    )
    db.commit()
    db.refresh(user)
