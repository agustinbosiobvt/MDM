import uuid

from sqlalchemy import CHAR, ForeignKey, ForeignKeyConstraint, Integer, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.models import SCHEMA, Audited, Base
from app.parties.models import Party


class Vendor(Audited, Base):
    __tablename__ = "vendor"
    __table_args__ = (
        ForeignKeyConstraint(
            ["party_id", "party_type"],
            [f"{SCHEMA}.party.id", f"{SCHEMA}.party.party_type"],
            ondelete="CASCADE",
        ),
    )

    party_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    party_type: Mapped[str] = mapped_column(String(20), server_default=text("'vendor'"))
    status: Mapped[str] = mapped_column(String(20), server_default=text("'active'"))
    default_currency: Mapped[str] = mapped_column(CHAR(3), ForeignKey(f"{SCHEMA}.currency.code"))
    payment_term_code: Mapped[str | None] = mapped_column(
        String(20), ForeignKey(f"{SCHEMA}.payment_term.code")
    )
    incoterm_code: Mapped[str | None] = mapped_column(
        CHAR(3), ForeignKey(f"{SCHEMA}.incoterm.code")
    )
    lead_time_days: Mapped[int | None] = mapped_column(Integer)
    moq: Mapped[int | None] = mapped_column(Integer)

    party: Mapped[Party] = relationship(lazy="joined", innerjoin=True)
