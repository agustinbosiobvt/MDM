import uuid

from sqlalchemy import Boolean, ForeignKeyConstraint, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.models import SCHEMA, Audited, Base
from app.parties.models import Party


class Company(Audited, Base):
    __tablename__ = "company"
    __table_args__ = (
        ForeignKeyConstraint(
            ["party_id", "party_type"],
            [f"{SCHEMA}.party.id", f"{SCHEMA}.party.party_type"],
            ondelete="CASCADE",
        ),
    )

    party_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    party_type: Mapped[str] = mapped_column(String(20), server_default=text("'company'"))
    is_default: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    # Printed on BVT's commercial invoices (e.g. TRN 104965266000001). Company only.
    tax_registration_number: Mapped[str | None] = mapped_column(String(50))

    party: Mapped[Party] = relationship(lazy="joined", innerjoin=True)
