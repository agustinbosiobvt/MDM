"""Server-side sessions.

The cookie holds an opaque random token; the DB stores only its SHA-256.
Idle timeout and absolute timeout come from settings; the ID is new at every login.
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from app.auth.models import OAuthLoginState, UserSession
from app.config import Settings
from app.users.models import AppUser

SESSION_COOKIE = "__Host-mdm_session"
CSRF_COOKIE = "__Host-mdm_csrf"
LOGIN_COOKIE = "__Host-mdm_login"

# Don't write last_seen_at on every request; this precision is plenty for a 30-min idle window.
TOUCH_INTERVAL = timedelta(seconds=60)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def digest(value: str) -> bytes:
    return hashlib.sha256(value.encode()).digest()


def now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class IssuedSession:
    token: str
    csrf: str
    max_age: int  # seconds, for the cookies


@dataclass(frozen=True)
class ActiveSession:
    session_id: uuid.UUID
    csrf_hash: bytes
    user: AppUser


def create(
    db: Session, user: AppUser, settings: Settings, *, ip: str | None, user_agent: str | None
) -> IssuedSession:
    token, csrf = new_token(), new_token()
    absolute = timedelta(hours=settings.session_absolute_hours)
    db.add(
        UserSession(
            token_hash=digest(token),
            csrf_hash=digest(csrf),
            user_id=user.id,
            last_seen_at=now(),
            expires_at=now() + absolute,
            ip=ip,
            user_agent=(user_agent or "")[:400] or None,
            created_by=user.id,
            updated_by=user.id,
        )
    )
    return IssuedSession(token=token, csrf=csrf, max_age=int(absolute.total_seconds()))


def resolve(db: Session, token: str, settings: Settings) -> ActiveSession | None:
    """Return the live session for this cookie value, or None (and drop it if expired)."""
    row = db.execute(
        select(UserSession, AppUser)
        .join(AppUser, AppUser.id == UserSession.user_id)
        .where(UserSession.token_hash == digest(token))
    ).one_or_none()
    if row is None:
        return None
    sess, user = row
    t = now()
    idle_deadline = sess.last_seen_at + timedelta(minutes=settings.session_idle_minutes)
    if not user.is_active or sess.expires_at <= t or idle_deadline <= t:
        db.execute(delete(UserSession).where(UserSession.id == sess.id))
        db.commit()
        return None
    if t - sess.last_seen_at > TOUCH_INTERVAL:
        # Plain UPDATE (no version check): parallel requests may all touch it.
        db.execute(
            update(UserSession)
            .where(UserSession.id == sess.id)
            .values(last_seen_at=t)
            .execution_options(synchronize_session=False)
        )
        db.commit()
    return ActiveSession(session_id=sess.id, csrf_hash=sess.csrf_hash, user=user)


def revoke(db: Session, token: str) -> None:
    db.execute(delete(UserSession).where(UserSession.token_hash == digest(token)))


def revoke_all_for_user(db: Session, user_id: uuid.UUID) -> None:
    db.execute(delete(UserSession).where(UserSession.user_id == user_id))


def purge_expired(db: Session, settings: Settings) -> None:
    t = now()
    idle = timedelta(minutes=settings.session_idle_minutes)
    db.execute(
        delete(UserSession).where(
            or_(UserSession.expires_at <= t, UserSession.last_seen_at <= t - idle)
        )
    )
    db.execute(delete(OAuthLoginState).where(OAuthLoginState.expires_at <= t))
