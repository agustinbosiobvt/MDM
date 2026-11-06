"""Price lists inside a customer's or vendor's page: version history, one list's lines with
filters (category, brand, EAN/ASIN/description search), editing category/brand per line,
activation (one Active list per owner + currency + period; D4 duplicates block it) and
deleting a draft (soft delete: the rows stay, hidden, like every other remove)."""

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.audit.service import record
from app.auth.deps import RequireEditor, RequireViewer
from app.core.errors import STALE_MESSAGE
from app.core.net import client_ip
from app.core.pagination import Page, PageNo
from app.db import get_db
from app.pricelists.models import PriceList, PriceListLine, PriceListLinePrice
from app.users.models import AppUser

router = APIRouter(tags=["price lists"])
DbDep = Annotated[Session, Depends(get_db)]
NONE = "__none__"  # filter value for "no category" / "no brand"


def _today() -> date:
    return datetime.now(UTC).date()


def effective_status(pl: PriceList, today: date | None = None) -> str:
    """Stored status, except that an active list past its end date shows as expired."""
    t = today or _today()
    if pl.status == "active" and pl.valid_to is not None and pl.valid_to < t:
        return "expired"
    return pl.status


def _get(db: Session, price_list_id: uuid.UUID) -> PriceList:
    pl = db.get(PriceList, price_list_id)
    if pl is None or not pl.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Price list not found")
    return pl


def _emails(db: Session, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    rows = db.execute(select(AppUser.id, AppUser.email).where(AppUser.id.in_(wanted))).all()
    return {user_id: email for user_id, email in rows}


def _unresolved_duplicates(db: Session, price_list_id: uuid.UUID) -> int:
    groups = (
        select(PriceListLine.dup_key)
        .where(PriceListLine.price_list_id == price_list_id, PriceListLine.is_active)
        .group_by(PriceListLine.dup_key)
        .having(func.count() > 1)
        .subquery()
    )
    return db.scalar(select(func.count()).select_from(groups)) or 0


# --- Versions --------------------------------------------------------------------------


class PriceListOut(BaseModel):
    id: uuid.UUID
    party_id: uuid.UUID
    name: str
    currency: str
    valid_from: date
    valid_to: date | None
    status: str  # stored: draft | active | expired
    effective_status: str  # what the user sees today
    revision: int
    supersedes_id: uuid.UUID | None
    source_file_name: str
    source_file_sha256: str
    source_sheet: str | None
    source_metadata: Any
    imported_at: datetime
    imported_by_email: str | None
    updated_at: datetime
    updated_by_email: str | None
    notes: str | None
    line_count: int
    version: int


def _out(pl: PriceList, emails: dict[uuid.UUID, str]) -> PriceListOut:
    return PriceListOut(
        id=pl.id,
        party_id=pl.party_id,
        name=pl.name,
        currency=pl.currency,
        valid_from=pl.valid_from,
        valid_to=pl.valid_to,
        status=pl.status,
        effective_status=effective_status(pl),
        revision=pl.revision,
        supersedes_id=pl.supersedes_id,
        source_file_name=pl.source_file_name,
        source_file_sha256=pl.source_file_sha256,
        source_sheet=pl.source_sheet,
        source_metadata=pl.source_metadata,
        imported_at=pl.imported_at,
        imported_by_email=emails.get(pl.imported_by) if pl.imported_by else None,
        updated_at=pl.updated_at,
        updated_by_email=emails.get(pl.updated_by) if pl.updated_by else None,
        notes=pl.notes,
        line_count=pl.line_count,
        version=pl.version,
    )


@router.get("/api/parties/{party_id}/price-lists")
def versions(_: RequireViewer, db: DbDep, party_id: uuid.UUID) -> list[PriceListOut]:
    """Version history, newest first."""
    lists = db.scalars(
        select(PriceList)
        .where(PriceList.party_id == party_id, PriceList.is_active)
        .order_by(PriceList.revision.desc())
    ).all()
    emails = _emails(db, {x for pl in lists for x in (pl.imported_by, pl.updated_by)})
    return [_out(pl, emails) for pl in lists]


class Facet(BaseModel):
    value: str | None
    count: int


class PriceColumnOut(BaseModel):
    price_type: str
    currency: str
    count: int


class PriceListDetail(PriceListOut):
    lines_with_warnings: int
    excluded_lines: int
    duplicate_groups: int  # unresolved (D4): activation is refused while > 0
    brands: list[Facet]
    categories: list[Facet]
    price_columns: list[PriceColumnOut]


def _facet(db: Session, pl_id: uuid.UUID, column: Any) -> list[Facet]:
    rows = db.execute(
        select(column, func.count())
        .where(PriceListLine.price_list_id == pl_id, PriceListLine.is_active)
        .group_by(column)
        .order_by(column.asc().nulls_last())
    ).all()
    return [Facet(value=v, count=c) for v, c in rows]


@router.get("/api/price-lists/{price_list_id}")
def get_price_list(_: RequireViewer, db: DbDep, price_list_id: uuid.UUID) -> PriceListDetail:
    pl = _get(db, price_list_id)
    emails = _emails(db, {pl.imported_by, pl.updated_by})
    base = select(func.count()).where(PriceListLine.price_list_id == pl.id)
    warned = db.scalar(
        base.where(PriceListLine.is_active, func.jsonb_array_length(PriceListLine.issues) > 0)
    )
    excluded = db.scalar(base.where(PriceListLine.is_active.is_(False)))
    cols = db.execute(
        select(PriceListLinePrice.price_type, PriceListLinePrice.currency, func.count())
        .join(PriceListLine, PriceListLine.id == PriceListLinePrice.line_id)
        .where(PriceListLine.price_list_id == pl.id, PriceListLine.is_active)
        .group_by(PriceListLinePrice.price_type, PriceListLinePrice.currency)
        .order_by(PriceListLinePrice.price_type, PriceListLinePrice.currency)
    ).all()
    return PriceListDetail(
        **_out(pl, emails).model_dump(),
        lines_with_warnings=warned or 0,
        excluded_lines=excluded or 0,
        duplicate_groups=_unresolved_duplicates(db, pl.id),
        brands=_facet(db, pl.id, PriceListLine.brand),
        categories=_facet(db, pl.id, PriceListLine.category),
        price_columns=[PriceColumnOut(price_type=t, currency=c, count=n) for t, c, n in cols],
    )


# --- Lines -------------------------------------------------------------------------------


class PriceOut(BaseModel):
    price_type: str
    currency: str
    amount: str  # decimal as text: money never travels as a float


class LineOut(BaseModel):
    id: uuid.UUID
    source_row: int
    ean: str | None
    upc: str | None
    asin: str | None
    vendor_sku: str | None
    description: str | None
    observations: str | None
    category: str | None
    brand: str | None
    case_pack_qty: int | None
    moq: int | None
    uom: str | None
    country_of_origin: str | None
    hs_code: str | None
    dimensions: dict[str, Any] | None
    issues: list[str]
    duplicate: bool
    is_active: bool
    version: int
    prices: list[PriceOut]


SORTABLE = {
    "source_row": PriceListLine.source_row,
    "ean": PriceListLine.ean,
    "asin": PriceListLine.asin,
    "description": PriceListLine.description,
    "brand": PriceListLine.brand,
    "category": PriceListLine.category,
}
SearchQ = Annotated[str | None, Query(max_length=100)]
FacetQ = Annotated[str | None, Query(max_length=100)]


@router.get("/api/price-lists/{price_list_id}/lines")
def lines(
    _: RequireViewer,
    db: DbDep,
    price_list_id: uuid.UUID,
    q: SearchQ = None,
    brand: FacetQ = None,
    category: FacetQ = None,
    only: Literal["duplicates", "warnings", "excluded"] | None = None,
    sort: Annotated[Literal[tuple(SORTABLE)], Query()] = "source_row",  # type: ignore[valid-type]
    order: Literal["asc", "desc"] = "asc",
    page: PageNo = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> Page[LineOut]:
    pl = _get(db, price_list_id)
    stmt = select(PriceListLine).where(PriceListLine.price_list_id == pl.id)
    if only == "excluded":
        stmt = stmt.where(PriceListLine.is_active.is_(False))
    elif only != "duplicates":
        stmt = stmt.where(PriceListLine.is_active)
    if q:
        term = q.strip()
        like = f"%{term}%"
        stmt = stmt.where(
            or_(
                PriceListLine.ean.ilike(like),
                PriceListLine.asin.ilike(like),
                PriceListLine.upc.ilike(like),
                PriceListLine.description.ilike(like),
            )
        )
    for value, facet_col in ((brand, PriceListLine.brand), (category, PriceListLine.category)):
        if value == NONE:
            stmt = stmt.where(facet_col.is_(None))
        elif value:
            stmt = stmt.where(facet_col == value)
    dup_keys = (
        select(PriceListLine.dup_key)
        .where(PriceListLine.price_list_id == pl.id)
        .group_by(PriceListLine.dup_key)
        .having(func.count() > 1)
    )
    if only == "duplicates":
        stmt = stmt.where(PriceListLine.dup_key.in_(dup_keys))
    elif only == "warnings":
        stmt = stmt.where(func.jsonb_array_length(PriceListLine.issues) > 0)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    column = SORTABLE[sort]
    ordering = column.desc().nulls_last() if order == "desc" else column.asc().nulls_last()
    rows = db.scalars(
        stmt.order_by(ordering, PriceListLine.source_row)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    ids = [r.id for r in rows]
    prices: dict[uuid.UUID, list[PriceOut]] = {i: [] for i in ids}
    if ids:
        for p in db.scalars(
            select(PriceListLinePrice)
            .where(PriceListLinePrice.line_id.in_(ids))
            .order_by(PriceListLinePrice.price_type, PriceListLinePrice.currency)
        ):
            prices[p.line_id].append(
                PriceOut(price_type=p.price_type, currency=p.currency, amount=format(p.amount, "f"))
            )
    duplicated = (
        set(db.scalars(dup_keys.where(PriceListLine.dup_key.in_([r.dup_key for r in rows]))).all())
        if rows
        else set()
    )
    return Page(
        items=[_line_out(r, prices[r.id], r.dup_key in duplicated) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


def _line_out(r: PriceListLine, prices: list[PriceOut], duplicate: bool) -> LineOut:
    return LineOut(
        id=r.id,
        source_row=r.source_row,
        ean=r.ean,
        upc=r.upc,
        asin=r.asin,
        vendor_sku=r.vendor_sku,
        description=r.description,
        observations=r.observations,
        category=r.category,
        brand=r.brand,
        case_pack_qty=r.case_pack_qty,
        moq=r.moq,
        uom=r.uom,
        country_of_origin=r.country_of_origin,
        hs_code=r.hs_code,
        dimensions=r.dimensions,
        issues=list(r.issues or []),
        duplicate=duplicate,
        is_active=r.is_active,
        version=r.version,
        prices=prices,
    )


Label = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]


class LineUpdate(BaseModel):
    """Category, brand and observations can always be edited; prices never.
    Excluding/including a line
    (to resolve duplicates, D4) is only possible while the list is a draft."""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    category: Label | None = None
    brand: Label | None = None
    observations: Annotated[
        str | None, StringConstraints(strip_whitespace=True, max_length=2000)
    ] = None
    is_active: bool | None = None


@router.patch("/api/price-list-lines/{line_id}")
def update_line(
    who: RequireEditor, db: DbDep, line_id: uuid.UUID, body: LineUpdate, request: Request
) -> LineOut:
    line = db.get(PriceListLine, line_id)
    if line is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Line not found")
    if line.version != body.version:
        raise HTTPException(status.HTTP_409_CONFLICT, STALE_MESSAGE)
    pl = _get(db, line.price_list_id)
    changes = body.model_dump(exclude_unset=True, exclude={"version"})
    if "is_active" in changes:
        if changes["is_active"] is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "is_active can't be empty")
        if pl.status != "draft":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Lines can only be excluded while the price list is a draft",
            )
    old = {k: getattr(line, k) for k in changes}
    for field, value in changes.items():
        setattr(
            line, field, value or None if field in ("category", "brand", "observations") else value
        )
    line.updated_by = who.user_id
    # The list's "last update + who" reflects line edits too.
    db.execute(
        update(PriceList)
        .where(PriceList.id == pl.id)
        .values(updated_at=func.now(), updated_by=who.user_id)
        .execution_options(synchronize_session=False)
    )
    db.flush()
    record(
        db,
        entity="price_list_line",
        entity_id=line.id,
        action="update",
        user_id=who.user_id,
        user_email=who.email,
        old=old,
        new={k: getattr(line, k) for k in changes},
        ip=client_ip(request),
    )
    db.commit()
    db.refresh(line)
    line_prices = [
        PriceOut(price_type=p.price_type, currency=p.currency, amount=format(p.amount, "f"))
        for p in line.prices
    ]
    dup = (
        db.scalar(
            select(func.count()).where(
                PriceListLine.price_list_id == pl.id, PriceListLine.dup_key == line.dup_key
            )
        )
        or 0
    ) > 1
    return _line_out(line, line_prices, dup)


# --- Activation ------------------------------------------------------------------------


class ActivateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)


@router.post("/api/price-lists/{price_list_id}/activate")
def activate(
    who: RequireEditor, db: DbDep, price_list_id: uuid.UUID, body: ActivateIn, request: Request
) -> PriceListOut:
    pl = _get(db, price_list_id)
    if pl.version != body.version:
        raise HTTPException(status.HTTP_409_CONFLICT, STALE_MESSAGE)
    if pl.status != "draft":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a draft price list can be activated")
    dups = _unresolved_duplicates(db, pl.id)
    if dups:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{dups} duplicate group(s) still have more than one line. "
            "Exclude the extra lines before activating.",
        )
    # Lock this owner's lists, then expire the active list(s) this one replaces:
    # same currency and an overlapping period.
    db.execute(select(PriceList.id).where(PriceList.party_id == pl.party_id).with_for_update())
    new_end = pl.valid_to or date.max
    replaced = db.scalars(
        select(PriceList).where(
            PriceList.party_id == pl.party_id,
            PriceList.currency == pl.currency,
            PriceList.status == "active",
            PriceList.id != pl.id,
            PriceList.valid_from <= new_end,
            or_(PriceList.valid_to.is_(None), PriceList.valid_to >= pl.valid_from),
        )
    ).all()
    for old in replaced:
        before = {"status": old.status, "valid_to": str(old.valid_to) if old.valid_to else None}
        if old.valid_from < pl.valid_from:
            old.valid_to = pl.valid_from - timedelta(
                days=1
            )  # it was valid until the new one starts
        old.status = "expired"
        old.updated_by = who.user_id
        record(
            db,
            entity="price_list",
            entity_id=old.id,
            action="expire",
            user_id=who.user_id,
            user_email=who.email,
            old=before,
            new={
                "status": "expired",
                "valid_to": str(old.valid_to) if old.valid_to else None,
                "replaced_by": str(pl.id),
            },
            ip=client_ip(request),
        )
    db.flush()
    pl.status = "active"
    pl.updated_by = who.user_id
    db.flush()
    record(
        db,
        entity="price_list",
        entity_id=pl.id,
        action="activate",
        user_id=who.user_id,
        user_email=who.email,
        old={"status": "draft"},
        new={"status": "active", "replaced": [str(o.id) for o in replaced]},
        ip=client_ip(request),
    )
    db.commit()
    db.refresh(pl)
    return _out(pl, _emails(db, {pl.imported_by, pl.updated_by}))


# --- Draft deletion ----------------------------------------------------------------------


@router.delete("/api/price-lists/{price_list_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_draft(
    who: RequireEditor,
    db: DbDep,
    price_list_id: uuid.UUID,
    version: Annotated[int, Query(ge=1)],
    request: Request,
) -> None:
    """Only a draft can be deleted; Active and Expired lists are history and stay."""
    pl = _get(db, price_list_id)
    if pl.version != version:
        raise HTTPException(status.HTTP_409_CONFLICT, STALE_MESSAGE)
    if pl.status != "draft":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a draft price list can be deleted")
    pl.is_active = False
    pl.updated_by = who.user_id
    db.flush()
    record(
        db,
        entity="price_list",
        entity_id=pl.id,
        action="delete",
        user_id=who.user_id,
        user_email=who.email,
        old={
            "name": pl.name,
            "status": pl.status,
            "revision": pl.revision,
            "currency": pl.currency,
            "line_count": pl.line_count,
            "source_file_name": pl.source_file_name,
            "is_active": True,
        },
        new={"is_active": False},
        ip=client_ip(request),
    )
    db.commit()
