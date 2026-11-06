"""A party is any business partner: BVT's own companies, customers and vendors.
Addresses and contacts hang off the party, so all three modules share them."""

import uuid

from sqlalchemy import CHAR, Boolean, ForeignKey, String, Uuid, text
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.models import SCHEMA, Audited, Base, uuid_pk


class Party(Audited, Base):
    __tablename__ = "party"

    id: Mapped[uuid.UUID] = uuid_pk()
    party_type: Mapped[str] = mapped_column(String(20))
    code: Mapped[str] = mapped_column(String(20))
    legal_name: Mapped[str] = mapped_column(String(200))
    trade_name: Mapped[str | None] = mapped_column(String(200))
    eori: Mapped[str | None] = mapped_column(String(17))
    country_code: Mapped[str] = mapped_column(CHAR(2), ForeignKey(f"{SCHEMA}.country.code"))

    addresses: Mapped[list["Address"]] = relationship(
        back_populates="party", order_by="Address.created_at", passive_deletes=True
    )
    contacts: Mapped[list["Contact"]] = relationship(
        back_populates="party", order_by="Contact.created_at", passive_deletes=True
    )


class Address(Audited, Base):
    __tablename__ = "address"

    id: Mapped[uuid.UUID] = uuid_pk()
    party_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(f"{SCHEMA}.party.id", ondelete="CASCADE")
    )
    address_type: Mapped[str] = mapped_column(String(20))
    line1: Mapped[str] = mapped_column(String(200))
    line2: Mapped[str | None] = mapped_column(String(200))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    city: Mapped[str] = mapped_column(String(100))
    region: Mapped[str | None] = mapped_column(String(100))
    country_code: Mapped[str] = mapped_column(CHAR(2), ForeignKey(f"{SCHEMA}.country.code"))

    party: Mapped[Party] = relationship(back_populates="addresses")


class Contact(Audited, Base):
    __tablename__ = "contact"

    id: Mapped[uuid.UUID] = uuid_pk()
    party_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(f"{SCHEMA}.party.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(200))
    role_title: Mapped[str | None] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(CITEXT)
    phone: Mapped[str | None] = mapped_column(String(40))
    is_primary: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    contact_role: Mapped[str | None] = mapped_column(String(20))

    party: Mapped[Party] = relationship(back_populates="contacts")
