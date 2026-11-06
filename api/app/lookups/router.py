"""Lookups for form dropdowns (seeded by migration 0001)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import RequireViewer
from app.db import get_db
from app.lookups.models import Country, Currency, Incoterm, PaymentTerm, PriceType

router = APIRouter(prefix="/api/lookups", tags=["lookups"])

DbDep = Annotated[Session, Depends(get_db)]


class CodeName(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str


@router.get("/countries")
def countries(_: RequireViewer, db: DbDep) -> list[CodeName]:
    rows = db.scalars(select(Country).where(Country.is_active).order_by(Country.name)).all()
    return [CodeName.model_validate(r) for r in rows]


@router.get("/currencies")
def currencies(_: RequireViewer, db: DbDep) -> list[CodeName]:
    rows = db.scalars(select(Currency).where(Currency.is_active).order_by(Currency.code)).all()
    return [CodeName.model_validate(r) for r in rows]


@router.get("/payment-terms")
def payment_terms(_: RequireViewer, db: DbDep) -> list[CodeName]:
    rows = db.scalars(
        select(PaymentTerm)
        .where(PaymentTerm.is_active)
        .order_by(PaymentTerm.days.nulls_last(), PaymentTerm.code)
    ).all()
    return [CodeName.model_validate(r) for r in rows]


@router.get("/incoterms")
def incoterms(_: RequireViewer, db: DbDep) -> list[CodeName]:
    rows = db.scalars(select(Incoterm).where(Incoterm.is_active).order_by(Incoterm.code)).all()
    return [CodeName.model_validate(r) for r in rows]


@router.get("/price-types")
def price_types(_: RequireViewer, db: DbDep) -> list[CodeName]:
    rows = db.scalars(
        select(PriceType).where(PriceType.is_active).order_by(PriceType.sort_order, PriceType.code)
    ).all()
    return [CodeName.model_validate(r) for r in rows]


LookupModel = type[Country] | type[Currency] | type[PaymentTerm] | type[Incoterm]


def require_known_codes(
    db: Session,
    *,
    country: str | None = None,
    currency: str | None = None,
    payment_term: str | None = None,
    incoterm: str | None = None,
) -> None:
    """Clear 422s for unknown lookup codes (instead of a foreign-key error)."""
    checks: list[tuple[str | None, LookupModel, str]] = [
        (country, Country, "country code"),
        (currency, Currency, "currency code"),
        (payment_term, PaymentTerm, "payment term"),
        (incoterm, Incoterm, "Incoterm"),
    ]
    for value, model, label in checks:
        if value is not None and db.get(model, value) is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown {label} {value}")
