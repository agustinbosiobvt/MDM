"""Append-only audit trail. mdm_app may only INSERT into audit_log (no SELECT),
so writes use a Core insert without RETURNING."""

import uuid
from typing import Any

from sqlalchemy import BigInteger, Column, DateTime, Identity, String, Table, Uuid, func, insert
from sqlalchemy.dialects.postgresql import CITEXT, INET, JSONB
from sqlalchemy.orm import Session

from app.core.models import Base

audit_log = Table(
    "audit_log",
    Base.metadata,
    # Not declared as PK here, so SQLAlchemy never tries to fetch it back
    # (that needs SELECT/RETURNING). The real PK is defined in migration 0001.
    Column("id", BigInteger, Identity(always=True)),
    Column("occurred_at", DateTime(timezone=True), server_default=func.now()),
    Column("user_id", Uuid),
    Column("user_email", CITEXT),
    Column("entity", String(60)),
    Column("entity_id", String(64)),
    Column("action", String(40)),
    Column("old_values", JSONB),
    Column("new_values", JSONB),
    Column("request_id", String(64)),
    Column("ip", INET),
    # No RETURNING: it would need SELECT, which mdm_app deliberately lacks here.
    implicit_returning=False,
)


def record(
    db: Session,
    *,
    entity: str,
    action: str,
    entity_id: uuid.UUID | str | None = None,
    user_id: uuid.UUID | None = None,
    user_email: str | None = None,
    old: dict[str, Any] | None = None,
    new: dict[str, Any] | None = None,
    ip: str | None = None,
) -> None:
    """Add an audit entry to the current transaction (committed with the change)."""
    db.execute(
        insert(audit_log).values(
            user_id=user_id,
            user_email=user_email,
            entity=entity,
            entity_id=str(entity_id) if entity_id is not None else None,
            action=action,
            old_values=old,
            new_values=new,
            ip=ip,
        )
    )
