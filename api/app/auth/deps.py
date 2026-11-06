"""Authentication and authorization dependencies. Every /api route except
/api/health must depend on one of the Require* types (enforced by a test)."""

import hmac
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth import sessions
from app.auth.oidc import OIDCClient
from app.config import get_settings
from app.db import get_db
from app.users.models import Role

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
CSRF_HEADER = "X-CSRF-Token"

# Higher number = more rights. Admin ⊃ Editor ⊃ Viewer.
ROLE_RANK = {Role.VIEWER: 1, Role.EDITOR: 2, Role.ADMIN: 3}


@dataclass(frozen=True)
class Principal:
    user_id: uuid.UUID
    email: str
    role: Role
    session_id: uuid.UUID


@lru_cache
def get_oidc_client() -> OIDCClient:
    return OIDCClient(get_settings())


def get_principal(request: Request, db: Annotated[Session, Depends(get_db)]) -> Principal:
    token = request.cookies.get(sessions.SESSION_COOKIE)
    active = sessions.resolve(db, token, get_settings()) if token else None
    if active is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    if request.method in UNSAFE_METHODS:
        sent = request.headers.get(CSRF_HEADER, "")
        if not sent or not hmac.compare_digest(sessions.digest(sent), active.csrf_hash):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF check failed")
    user = active.user
    return Principal(
        user_id=user.id, email=user.email, role=Role(user.role), session_id=active.session_id
    )


def require_role(minimum: Role) -> Callable[[Principal], Principal]:
    def dependency(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
        if ROLE_RANK[principal.role] < ROLE_RANK[minimum]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not allowed")
        return principal

    dependency.min_role = minimum  # type: ignore[attr-defined]  # read by the route audit test
    return dependency


RequireViewer = Annotated[Principal, Depends(require_role(Role.VIEWER))]
RequireEditor = Annotated[Principal, Depends(require_role(Role.EDITOR))]
RequireAdmin = Annotated[Principal, Depends(require_role(Role.ADMIN))]
