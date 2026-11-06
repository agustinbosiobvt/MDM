import uuid

from sqlalchemy import CHAR, ForeignKey, ForeignKeyConstraint, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.models import SCHEMA, Audited, Base, uuid_pk
from app.parties.models import Party


class Customer(Audited, Base):
    __tablename__ = "customer"
    __table_args__ = (
        ForeignKeyConstraint(
            ["party_id", "party_type"],
            [f"{SCHEMA}.party.id", f"{SCHEMA}.party.party_type"],
            ondelete="CASCADE",
        ),
    )

    party_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    party_type: Mapped[str] = mapped_column(String(20), server_default=text("'customer'"))
    status: Mapped[str] = mapped_column(String(20), server_default=text("'active'"))
    default_currency: Mapped[str] = mapped_column(CHAR(3), ForeignKey(f"{SCHEMA}.currency.code"))
    payment_term_code: Mapped[str | None] = mapped_column(
        String(20), ForeignKey(f"{SCHEMA}.payment_term.code")
    )
    incoterm_code: Mapped[str | None] = mapped_column(
        CHAR(3), ForeignKey(f"{SCHEMA}.incoterm.code")
    )

    party: Mapped[Party] = relationship(lazy="joined", innerjoin=True)
    vendor_codes: Mapped[list["CustomerVendorCode"]] = relationship(
        order_by="CustomerVendorCode.created_at", passive_deletes=True
    )


class CustomerVendorCode(Audited, Base):
    """An Amazon (or other retailer) parent/child vendor code pair assigned to this customer."""

    __tablename__ = "customer_vendor_code"

    id: Mapped[uuid.UUID] = uuid_pk()
    customer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(f"{SCHEMA}.customer.party_id", ondelete="CASCADE")
    )
    parent_code: Mapped[str] = mapped_column(String(20))
    child_code: Mapped[str] = mapped_column(String(20))
    destination_country: Mapped[str | None] = mapped_column(
        CHAR(2), ForeignKey(f"{SCHEMA}.country.code")
    )
