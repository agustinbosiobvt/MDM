import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, LargeBinary, String, Uuid, func
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import SCHEMA, Audited, Base, uuid_pk


class UserSession(Audited, Base):
    __tablename__ = "user_session"

    id: Mapped[uuid.UUID] = uuid_pk()
    token_hash: Mapped[bytes] = mapped_column(LargeBinary(32))
    csrf_hash: Mapped[bytes] = mapped_column(LargeBinary(32))
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey(f"{SCHEMA}.app_user.id"))
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(String(400))


class OAuthLoginState(Audited, Base):
    __tablename__ = "oauth_login_state"

    id: Mapped[uuid.UUID] = uuid_pk()
    state_hash: Mapped[bytes] = mapped_column(LargeBinary(32))
    browser_hash: Mapped[bytes] = mapped_column(LargeBinary(32))
    nonce: Mapped[str] = mapped_column(String(128))
    code_verifier: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
