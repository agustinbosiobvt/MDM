"""BVT's own companies. Several are allowed; exactly one active company is the default."""

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.audit.service import record
from app.auth.deps import Principal, RequireAdmin, RequireEditor, RequireViewer
from app.company.models import Company
from app.company.schemas import CompanyCreate, CompanyDetail, CompanyOut, CompanyUpdate
from app.core.errors import STALE_MESSAGE
from app.core.net import client_ip
from app.core.pagination import Page, PageNo, PageSize, SearchText
from app.db import get_db
from app.lookups.router import require_known_codes
from app.parties.models import Party
from app.parties.schemas import AddressOut, ContactOut

router = APIRouter(prefix="/api/companies", tags=["company"])

DbDep = Annotated[Session, Depends(get_db)]

SORTABLE = {
    "code": Party.code,
    "legal_name": Party.legal_name,
    "trade_name": Party.trade_name,
    "country_code": Party.country_code,
    "updated_at": Party.updated_at,
}
IDENTITY = ("code", "legal_name", "trade_name", "eori", "country_code")
DEFAULT_GUARD = "This is the default company. Make another company the default first."


def _out(c: Company) -> CompanyOut:
    p = c.party
    return CompanyOut(
        id=p.id,
        code=p.code,
        legal_name=p.legal_name,
        trade_name=p.trade_name,
        eori=p.eori,
        country_code=p.country_code,
        tax_registration_number=c.tax_registration_number,
        is_default=c.is_default,
        is_active=p.is_active,
        version=p.version,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


def _detail(c: Company) -> CompanyDetail:
    p = c.party
    return CompanyDetail(
        **_out(c).model_dump(),
        addresses=[AddressOut.model_validate(a) for a in p.addresses if a.is_active],
        contacts=[ContactOut.model_validate(x) for x in p.contacts if x.is_active],
    )


def _snap(c: Company) -> dict[str, Any]:
    p = c.party
    return {
        **{f: getattr(p, f) for f in IDENTITY},
        "tax_registration_number": c.tax_registration_number,
        "is_default": c.is_default,
        "is_active": p.is_active,
    }


def _get(db: Session, company_id: uuid.UUID) -> Company:
    c = db.get(Company, company_id)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")
    return c


def _check_version(c: Company, version: int) -> None:
    if c.party.version != version:
        raise HTTPException(status.HTTP_409_CONFLICT, STALE_MESSAGE)


def _audit(
    db: Session,
    who: Principal,
    request: Request,
    company_id: uuid.UUID,
    action: str,
    old: dict[str, Any] | None,
    new: dict[str, Any] | None,
) -> None:
    record(
        db,
        entity="company",
        entity_id=company_id,
        action=action,
        user_id=who.user_id,
        user_email=who.email,
        old=old,
        new=new,
        ip=client_ip(request),
    )


def _make_default(db: Session, who: Principal, company_id: uuid.UUID) -> None:
    """Move the default flag. Two statements, in this order, inside one transaction;
    the partial unique index guarantees there's never more than one default."""
    db.execute(
        update(Company)
        .where(Company.is_default, Company.party_id != company_id)
        .values(
            is_default=False,
            version=Company.version + 1,
            updated_by=who.user_id,
            updated_at=func.now(),
        )
        .execution_options(synchronize_session=False)
    )
    db.execute(
        update(Company)
        .where(Company.party_id == company_id)
        .values(
            is_default=True,
            version=Company.version + 1,
            updated_by=who.user_id,
            updated_at=func.now(),
        )
        .execution_options(synchronize_session=False)
    )


# --- Read ------------------------------------------------------------------------


@router.get("")
def list_companies(
    _: RequireViewer,
    db: DbDep,
    q: SearchText = None,
    active: bool | None = True,
    sort: Annotated[Literal[tuple(SORTABLE)], Query()] = "legal_name",  # type: ignore[valid-type]
    order: Literal["asc", "desc"] = "asc",
    page: PageNo = 1,
    page_size: PageSize = 25,
) -> Page[CompanyOut]:
    stmt = select(Company).join(Company.party)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Party.code.ilike(like),
                Party.legal_name.ilike(like),
                Party.trade_name.ilike(like),
            )
        )
    if active is not None:
        stmt = stmt.where(Party.is_active.is_(active))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    column = SORTABLE[sort]
    ordering = column.desc().nulls_last() if order == "desc" else column.asc().nulls_last()
    rows = db.scalars(
        stmt.order_by(ordering, Party.id).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return Page(items=[_out(c) for c in rows], total=total, page=page, page_size=page_size)


@router.get("/{company_id}")
def get_company(_: RequireViewer, db: DbDep, company_id: uuid.UUID) -> CompanyDetail:
    return _detail(_get(db, company_id))


# --- Write -----------------------------------------------------------------------


@router.post("", status_code=status.HTTP_201_CREATED)
def create_company(
    who: RequireEditor, db: DbDep, body: CompanyCreate, request: Request
) -> CompanyDetail:
    require_known_codes(db, country=body.country_code)
    party = Party(
        party_type="company",
        code=body.code,
        legal_name=body.legal_name,
        trade_name=body.trade_name,
        eori=body.eori,
        country_code=body.country_code,
        created_by=who.user_id,
        updated_by=who.user_id,
    )
    db.add(party)
    db.flush()
    company = Company(
        party_id=party.id,
        tax_registration_number=body.tax_registration_number,
        created_by=who.user_id,
        updated_by=who.user_id,
    )
    db.add(company)
    db.flush()
    has_default = db.scalar(select(func.count()).where(Company.is_default)) or 0
    if body.is_default or not has_default:  # the first company is the default
        _make_default(db, who, party.id)
    db.expire(company)
    _audit(db, who, request, party.id, "create", None, _snap(company))
    db.commit()
    return _detail(_get(db, party.id))


@router.patch("/{company_id}")
def update_company(
    who: RequireEditor, db: DbDep, company_id: uuid.UUID, body: CompanyUpdate, request: Request
) -> CompanyDetail:
    company = _get(db, company_id)
    _check_version(company, body.version)
    changes = body.model_dump(exclude_unset=True, exclude={"version"})
    if changes.get("is_active") is False and company.is_default:
        raise HTTPException(status.HTTP_409_CONFLICT, DEFAULT_GUARD)
    for required in ("code", "legal_name", "country_code", "is_active"):
        if required in changes and changes[required] is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{required} can't be empty")
    require_known_codes(db, country=changes.get("country_code"))

    old = _snap(company)
    party = company.party
    for field, value in changes.items():
        if field == "is_active":
            party.is_active = value
            company.is_active = value
        elif field == "tax_registration_number":
            company.tax_registration_number = value
        else:
            setattr(party, field, value)
    # The party row carries the version the UI holds, so touch it on every edit
    # (also when only a company-row field such as the tax registration number changed).
    party.updated_by = who.user_id
    party.updated_at = func.now()
    company.updated_by = who.user_id
    db.flush()  # versioned UPDATE: a concurrent edit raises StaleDataError → 409
    _audit(db, who, request, company_id, "update", old, _snap(company))
    db.commit()
    return _detail(_get(db, company_id))


@router.post("/{company_id}/default")
def make_default(
    who: RequireEditor, db: DbDep, company_id: uuid.UUID, request: Request
) -> CompanyDetail:
    company = _get(db, company_id)
    if not company.party.is_active:
        raise HTTPException(status.HTTP_409_CONFLICT, "A removed company can't be the default")
    if not company.is_default:
        old = _snap(company)
        _make_default(db, who, company_id)
        db.expire(company)
        _audit(db, who, request, company_id, "make_default", old, _snap(company))
        db.commit()
    return _detail(_get(db, company_id))


@router.delete("/{company_id}")
def remove_company(
    who: RequireEditor,
    db: DbDep,
    company_id: uuid.UUID,
    version: Annotated[int, Query(ge=1)],
    request: Request,
) -> CompanyOut:
    """Remove = soft delete. Addresses and contacts stay, hidden with the company."""
    company = _get(db, company_id)
    _check_version(company, version)
    if company.is_default:
        raise HTTPException(status.HTTP_409_CONFLICT, DEFAULT_GUARD)
    old = _snap(company)
    company.party.is_active = False
    company.party.updated_by = who.user_id
    company.is_active = False
    db.flush()
    _audit(db, who, request, company_id, "remove", old, _snap(company))
    db.commit()
    return _out(_get(db, company_id))


@router.delete("/{company_id}/permanent", status_code=status.HTTP_204_NO_CONTENT)
def delete_company_permanently(
    who: RequireAdmin,
    db: DbDep,
    company_id: uuid.UUID,
    confirm: Annotated[str, Query(max_length=20)],
    request: Request,
) -> None:
    """Admin only. The company must be removed first, and `confirm` must repeat its code."""
    company = _get(db, company_id)
    if company.party.is_active:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Remove the company before deleting it permanently"
        )
    if confirm.strip().upper() != company.party.code:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Type the company code to confirm"
        )
    old = _detail(company).model_dump(mode="json")
    db.execute(delete(Party).where(Party.id == company_id))  # cascades to company/address/contact
    _audit(db, who, request, company_id, "delete_permanently", old, None)
    db.commit()
