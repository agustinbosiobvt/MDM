import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CHAR, Date, DateTime, ForeignKey, Integer, Numeric, String, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.models import SCHEMA, Audited, Base, uuid_pk


class PriceList(Audited, Base):
    """One imported version of a customer's or vendor's price list."""

    __tablename__ = "price_list"

    id: Mapped[uuid.UUID] = uuid_pk()
    party_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    party_type: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(200))
    currency: Mapped[str] = mapped_column(CHAR(3), ForeignKey(f"{SCHEMA}.currency.code"))
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), server_default=text("'draft'"))
    revision: Mapped[int] = mapped_column(Integer)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey(f"{SCHEMA}.price_list.id")
    )
    source_file_name: Mapped[str] = mapped_column(String(255))
    source_file_sha256: Mapped[str] = mapped_column(CHAR(64))
    source_sheet: Mapped[str | None] = mapped_column(String(100))
    source_metadata: Mapped[Any] = mapped_column(JSONB)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    imported_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey(f"{SCHEMA}.app_user.id"))
    notes: Mapped[str | None] = mapped_column(String(1000))
    line_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))


class PriceListLine(Audited, Base):
    __tablename__ = "price_list_line"

    id: Mapped[uuid.UUID] = uuid_pk()
    price_list_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(f"{SCHEMA}.price_list.id", ondelete="CASCADE")
    )
    source_row: Mapped[int] = mapped_column(Integer)
    ean: Mapped[str | None] = mapped_column(String(20))
    upc: Mapped[str | None] = mapped_column(String(20))
    asin: Mapped[str | None] = mapped_column(String(20))
    vendor_sku: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(1000))
    observations: Mapped[str | None] = mapped_column(String(2000))
    category: Mapped[str | None] = mapped_column(String(100))
    brand: Mapped[str | None] = mapped_column(String(100))
    case_pack_qty: Mapped[int | None] = mapped_column(Integer)
    moq: Mapped[int | None] = mapped_column(Integer)
    uom: Mapped[str | None] = mapped_column(String(20))
    country_of_origin: Mapped[str | None] = mapped_column(
        CHAR(2), ForeignKey(f"{SCHEMA}.country.code")
    )
    hs_code: Mapped[str | None] = mapped_column(String(20))
    dimensions: Mapped[Any] = mapped_column(JSONB)
    dup_key: Mapped[str] = mapped_column(CHAR(64))
    issues: Mapped[Any] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    raw_row: Mapped[Any] = mapped_column(JSONB)

    prices: Mapped[list["PriceListLinePrice"]] = relationship(
        order_by="PriceListLinePrice.price_type", passive_deletes=True
    )


class PriceListLinePrice(Audited, Base):
    __tablename__ = "price_list_line_price"

    id: Mapped[uuid.UUID] = uuid_pk()
    line_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(f"{SCHEMA}.price_list_line.id", ondelete="CASCADE")
    )
    price_type: Mapped[str] = mapped_column(String(40), ForeignKey(f"{SCHEMA}.price_type.code"))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4, asdecimal=True))
    currency: Mapped[str] = mapped_column(CHAR(3), ForeignKey(f"{SCHEMA}.currency.code"))
    source_column: Mapped[str | None] = mapped_column(String(10))
