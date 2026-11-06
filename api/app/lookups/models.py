from sqlalchemy import CHAR, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Audited, Base


class Country(Audited, Base):
    __tablename__ = "country"

    code: Mapped[str] = mapped_column(CHAR(2), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))


class PaymentTerm(Audited, Base):
    __tablename__ = "payment_term"

    code: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    days: Mapped[int | None] = mapped_column(SmallInteger)


class Incoterm(Audited, Base):
    __tablename__ = "incoterm"

    code: Mapped[str] = mapped_column(CHAR(3), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))


class PriceType(Audited, Base):
    __tablename__ = "price_type"

    code: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(500))
    sort_order: Mapped[int] = mapped_column(SmallInteger)


class Currency(Audited, Base):
    __tablename__ = "currency"

    code: Mapped[str] = mapped_column(CHAR(3), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    minor_units: Mapped[int] = mapped_column(SmallInteger)
