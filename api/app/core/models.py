"""Declarative base and the common columns every business table carries."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, MetaData, Uuid, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

SCHEMA = "mdm"


class Base(DeclarativeBase):
    metadata = MetaData(schema=SCHEMA)


class Audited:
    """created/updated metadata, soft delete and optimistic locking.

    `version` is SQLAlchemy's version_id_col: every UPDATE carries
    `WHERE version = :old`, and a stale write raises StaleDataError (→ 409).
    """

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))

    @declared_attr
    def created_by(cls) -> Mapped[uuid.UUID | None]:
        return mapped_column(Uuid, ForeignKey(f"{SCHEMA}.app_user.id"), nullable=True)

    @declared_attr
    def updated_by(cls) -> Mapped[uuid.UUID | None]:
        return mapped_column(Uuid, ForeignKey(f"{SCHEMA}.app_user.id"), nullable=True)

    @declared_attr.directive
    def __mapper_args__(cls) -> dict[str, object]:  # noqa: N805 (SQLAlchemy directive)
        return {"version_id_col": cls.version}


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, server_default=text("gen_random_uuid()"))
