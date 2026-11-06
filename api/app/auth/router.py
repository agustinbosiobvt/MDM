"""/auth/login → Google → /auth/callback → session cookie → SPA.  /auth/logout ends it."""

import logging
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.audit.service import record
from app.auth import sessions
from app.auth.deps import Principal, RequireViewer, get_oidc_client, get_principal
from app.auth.models import OAuthLoginState
from app.auth.oidc import OIDCClient, OIDCError
from app.config import Settings, get_settings
from app.core.net import client_ip
from app.db import get_db
from app.security.ratelimit import auth_limit, limiter
from app.users.models import AppUser

log = logging.getLogger("app.auth")

router = APIRouter(tags=["auth"])

DbDep = Annotated[Session, Depends(get_db)]
OIDCDep = Annotated[OIDCClient, Depends(get_oidc_client)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def _set_cookie(resp: Response, name: str, value: str, max_age: int, *, http_only: bool) -> None:
    # __Host- prefix: Secure, Path=/ and no Domain are mandatory. Browsers treat
    # http://localhost as a secure context, so this works locally too.
    resp.set_cookie(
        name, value, max_age=max_age, path="/", secure=True, httponly=http_only, samesite="lax"
    )


def _clear_cookie(resp: Response, name: str, *, http_only: bool = True) -> None:
    resp.delete_cookie(name, path="/", secure=True, httponly=http_only, samesite="lax")


def _deny(reason: str) -> RedirectResponse:
    resp = RedirectResponse(f"/no-access?reason={reason}", status.HTTP_303_SEE_OTHER)
    _clear_cookie(resp, sessions.LOGIN_COOKIE)
    return resp


@router.get("/auth/login")
@limiter.limit(auth_limit)
def login(request: Request, db: DbDep, oidc: OIDCDep, settings: SettingsDep) -> Response:
    if not oidc.configured:
        log.error("sign-in attempted but GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET are not set")
        return _deny("not_configured")
    state, nonce, browser = sessions.new_token(), sessions.new_token(), sessions.new_token()
    code_verifier = sessions.new_token() + sessions.new_token()  # 86 chars (43..128 allowed)
    ttl = timedelta(minutes=settings.login_state_minutes)

    sessions.purge_expired(db, settings)
    db.add(
        OAuthLoginState(
            state_hash=sessions.digest(state),
            browser_hash=sessions.digest(browser),
            nonce=nonce,
            code_verifier=code_verifier,
            expires_at=sessions.now() + ttl,
        )
    )
    db.commit()

    url = oidc.authorization_url(state=state, nonce=nonce, code_verifier=code_verifier)
    resp = RedirectResponse(url, status.HTTP_303_SEE_OTHER)
    # Binds the login to this browser: a callback URL replayed elsewhere is useless.
    _set_cookie(resp, sessions.LOGIN_COOKIE, browser, int(ttl.total_seconds()), http_only=True)
    return resp


@router.get("/auth/callback")
@limiter.limit(auth_limit)
def callback(
    request: Request,
    db: DbDep,
    oidc: OIDCDep,
    settings: SettingsDep,
    code: Annotated[str | None, Query(max_length=2048)] = None,
    state: Annotated[str | None, Query(max_length=200)] = None,
    error: Annotated[str | None, Query(max_length=200)] = None,
) -> Response:
    ip = client_ip(request)
    if error:  # e.g. the user closed Google's account picker
        return _deny("cancelled")
    if not code or not state or len(code) > 2048 or len(state) > 256:
        return _deny("error")

    # Consume the login state (single use) whatever happens next.
    pending = db.scalars(
        select(OAuthLoginState).where(OAuthLoginState.state_hash == sessions.digest(state))
    ).one_or_none()
    if pending is not None:
        db.execute(delete(OAuthLoginState).where(OAuthLoginState.id == pending.id))
        db.commit()
    browser = request.cookies.get(sessions.LOGIN_COOKIE, "")
    if (
        pending is None
        or pending.expires_at <= sessions.now()
        or not browser
        or sessions.digest(browser) != pending.browser_hash
    ):
        log.warning("login rejected: invalid or expired state ip=%s", ip)
        return _deny("error")

    try:
        id_token = oidc.exchange_code(code=code, code_verifier=pending.code_verifier)
        identity = oidc.verify_id_token(id_token, nonce=pending.nonce)
    except OIDCError as exc:
        log.warning("login rejected: %s ip=%s", exc.reason, ip)
        record(db, entity="auth", action="login_denied", new={"reason": exc.reason}, ip=ip)
        db.commit()
        return _deny(
            "not_allowed" if exc.reason in {"wrong_domain", "email_not_verified"} else "error"
        )

    user = db.scalars(select(AppUser).where(AppUser.email == identity.email)).one_or_none()
    if user is None or not user.is_active:
        reason = "not_in_allowlist" if user is None else "user_inactive"
        log.warning("login rejected: %s email=%s ip=%s", reason, identity.email, ip)
        record(
            db,
            entity="auth",
            action="login_denied",
            user_email=identity.email,
            new={"reason": reason},
            ip=ip,
        )
        db.commit()
        return _deny("not_allowed")

    # Session rotation: whatever session this browser had is dropped.
    old_token = request.cookies.get(sessions.SESSION_COOKIE)
    if old_token:
        sessions.revoke(db, old_token)
    issued = sessions.create(
        db, user, settings, ip=ip, user_agent=request.headers.get("user-agent")
    )
    # Login bookkeeping is not an edit: a plain UPDATE that leaves `version` alone,
    # so an admin who has this user open doesn't get a false "someone else changed it".
    db.execute(
        update(AppUser)
        .where(AppUser.id == user.id)
        .values(
            last_login_at=sessions.now(),
            display_name=func.coalesce(AppUser.display_name, (identity.name or "")[:200] or None),
        )
        .execution_options(synchronize_session=False)
    )
    record(db, entity="auth", action="login", user_id=user.id, user_email=user.email, ip=ip)
    db.commit()

    resp = RedirectResponse("/", status.HTTP_303_SEE_OTHER)
    _set_cookie(resp, sessions.SESSION_COOKIE, issued.token, issued.max_age, http_only=True)
    _set_cookie(resp, sessions.CSRF_COOKIE, issued.csrf, issued.max_age, http_only=False)
    _clear_cookie(resp, sessions.LOGIN_COOKIE)
    return resp


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request, db: DbDep, principal: Annotated[Principal, Depends(get_principal)]
) -> Response:
    token = request.cookies.get(sessions.SESSION_COOKIE, "")
    sessions.revoke(db, token)
    record(
        db,
        entity="auth",
        action="logout",
        user_id=principal.user_id,
        user_email=principal.email,
        ip=client_ip(request),
    )
    db.commit()
    resp = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_cookie(resp, sessions.SESSION_COOKIE)
    _clear_cookie(resp, sessions.CSRF_COOKIE, http_only=False)
    return resp


class Me(BaseModel):
    id: str
    email: str
    display_name: str | None
    role: str


@router.get("/api/me")
def me(principal: RequireViewer, db: DbDep) -> Me:
    user = db.get(AppUser, principal.user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    return Me(id=str(user.id), email=user.email, display_name=user.display_name, role=user.role)
