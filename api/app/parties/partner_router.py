"""One router factory for customers and vendors: same rules as Company, plus a business
status and trading terms. List / view / add / edit / remove (soft) / reactivate /
permanent delete (Admin, removed records only, code typed to confirm)."""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.audit.service import record
from app.auth.deps import Principal, RequireAdmin, RequireEditor, RequireViewer
from app.core.errors import STALE_MESSAGE
from app.core.models import Base
from app.core.net import client_ip
from app.core.pagination import Page, PageNo, PageSize, SearchText
from app.db import get_db
from app.lookups.router import require_known_codes
from app.parties.models import Party
from app.parties.partner_schemas import PartnerCreate, PartnerUpdate
from app.parties.schemas import AddressOut, ContactOut, PartnerStatus
from app.pricelists.models import PriceList

DbDep = Annotated[Session, Depends(get_db)]
PARTY_FIELDS = ("code", "legal_name", "trade_name", "eori", "country_code")
REQUIRED = ("code", "legal_name", "country_code", "default_currency", "status", "is_active")


@dataclass(frozen=True)
class PartnerConfig:
    kind: Literal["customer", "vendor"]
    label: str  # "Customer"
    prefix: str  # "/api/customers"
    model: type[Base]  # Customer | Vendor: party_id, party, status, trading terms
    create_schema: type[PartnerCreate]
    update_schema: type[PartnerUpdate]
    out_schema: type[BaseModel]
    detail_schema: type[BaseModel]
    ext_fields: tuple[str, ...]  # stored on the customer/vendor row
    detail_extra: Callable[[Any], dict[str, Any]] = lambda _: {}


def build_router(cfg: PartnerConfig) -> APIRouter:
    router = APIRouter(prefix=cfg.prefix, tags=[cfg.kind])
    model: Any = cfg.model
    entity = cfg.kind
    not_found = f"{cfg.label} not found"
    party_fields = tuple(f for f in PARTY_FIELDS if f in cfg.create_schema.model_fields)
    sortable = {
        "code": Party.code,
        "legal_name": Party.legal_name,
        "trade_name": Party.trade_name,
        "country_code": Party.country_code,
        "default_currency": model.default_currency,
        "status": model.status,
        "updated_at": Party.updated_at,
    }

    def out_dict(ext: Any) -> dict[str, Any]:
        p: Party = ext.party
        return {
            "id": p.id,
            **{f: getattr(p, f) for f in party_fields},
            **{f: getattr(ext, f) for f in cfg.ext_fields},
            "is_active": p.is_active,
            "version": p.version,
            "created_at": p.created_at,
            "updated_at": p.updated_at,
        }

    def detail(ext: Any) -> BaseModel:
        p: Party = ext.party
        return cfg.detail_schema.model_validate(
            {
                **out_dict(ext),
                "addresses": [AddressOut.model_validate(a) for a in p.addresses if a.is_active],
                "contacts": [ContactOut.model_validate(c) for c in p.contacts if c.is_active],
                **cfg.detail_extra(ext),
            }
        )

    def snap(ext: Any) -> dict[str, Any]:
        d = out_dict(ext)
        return {k: d[k] for k in (*party_fields, *cfg.ext_fields, "is_active")}

    def get(db: Session, party_id: uuid.UUID) -> Any:
        ext = db.get(model, party_id)
        if ext is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, not_found)
        return ext

    def check_version(ext: Any, version: int) -> None:
        if ext.party.version != version:
            raise HTTPException(status.HTTP_409_CONFLICT, STALE_MESSAGE)

    def audit(
        db: Session, who: Principal, request: Request, obj_id: uuid.UUID, action: str,
        old: dict[str, Any] | None, new: dict[str, Any] | None,
    ) -> None:  # fmt: skip
        record(
            db, entity=entity, entity_id=obj_id, action=action, user_id=who.user_id,
            user_email=who.email, old=old, new=new, ip=client_ip(request),
        )  # fmt: skip

    def check_codes(db: Session, values: dict[str, Any]) -> None:
        require_known_codes(
            db,
            country=values.get("country_code"),
            currency=values.get("default_currency"),
            payment_term=values.get("payment_term_code"),
            incoterm=values.get("incoterm_code"),
        )

    # --- Read ----------------------------------------------------------------------

    @router.get("")
    def list_partners(
        _: RequireViewer,
        db: DbDep,
        q: SearchText = None,
        active: bool | None = True,
        partner_status: Annotated[PartnerStatus | None, Query(alias="status")] = None,
        sort: Annotated[Literal[tuple(sortable)], Query()] = "legal_name",  # type: ignore[valid-type]
        order: Literal["asc", "desc"] = "asc",
        page: PageNo = 1,
        page_size: PageSize = 25,
    ) -> Page[cfg.out_schema]:  # type: ignore[name-defined]
        stmt = select(model).join(model.party)
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
        if partner_status is not None:
            stmt = stmt.where(model.status == partner_status)
        total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        column = sortable[sort]
        ordering = column.desc().nulls_last() if order == "desc" else column.asc().nulls_last()
        rows = db.scalars(
            stmt.order_by(ordering, Party.id).offset((page - 1) * page_size).limit(page_size)
        ).all()
        return Page(
            items=[cfg.out_schema.model_validate(out_dict(r)) for r in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    @router.get("/{party_id}")
    def get_partner(_: RequireViewer, db: DbDep, party_id: uuid.UUID) -> cfg.detail_schema:  # type: ignore[name-defined]
        return detail(get(db, party_id))

    # --- Write ---------------------------------------------------------------------

    @router.post("", status_code=status.HTTP_201_CREATED)
    def create_partner(
        who: RequireEditor,
        db: DbDep,
        body: cfg.create_schema,  # type: ignore[name-defined]
        request: Request,
    ) -> cfg.detail_schema:  # type: ignore[name-defined]
        values = body.model_dump()
        check_codes(db, values)
        party = Party(
            party_type=cfg.kind,
            **{f: values[f] for f in party_fields},
            created_by=who.user_id,
            updated_by=who.user_id,
        )
        db.add(party)
        db.flush()
        ext = model(
            party_id=party.id,
            **{f: values[f] for f in cfg.ext_fields},
            created_by=who.user_id,
            updated_by=who.user_id,
        )
        db.add(ext)
        db.flush()
        audit(db, who, request, party.id, "create", None, snap(ext))
        db.commit()
        return detail(get(db, party.id))

    @router.patch("/{party_id}")
    def update_partner(
        who: RequireEditor,
        db: DbDep,
        party_id: uuid.UUID,
        body: cfg.update_schema,  # type: ignore[name-defined]
        request: Request,
    ) -> cfg.detail_schema:  # type: ignore[name-defined]
        ext = get(db, party_id)
        check_version(ext, body.version)
        changes: dict[str, Any] = body.model_dump(exclude_unset=True, exclude={"version"})
        for field in REQUIRED:
            if field in changes and changes[field] is None:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT, f"{field} can't be empty"
                )
        check_codes(db, changes)
        old = snap(ext)
        party: Party = ext.party
        for field, value in changes.items():
            if field == "is_active":
                party.is_active = value
                ext.is_active = value
            elif field in party_fields:
                setattr(party, field, value)
            else:
                setattr(ext, field, value)
        # Every change bumps the party's version (the record version the UI holds).
        party.updated_by = who.user_id
        party.updated_at = func.now()
        ext.updated_by = who.user_id
        db.flush()
        audit(db, who, request, party_id, "update", old, snap(ext))
        db.commit()
        return detail(get(db, party_id))

    @router.delete("/{party_id}")
    def remove_partner(
        who: RequireEditor,
        db: DbDep,
        party_id: uuid.UUID,
        version: Annotated[int, Query(ge=1)],
        request: Request,
    ) -> cfg.out_schema:  # type: ignore[name-defined]
        """Remove = soft delete; addresses, contacts and codes stay, hidden with it."""
        ext = get(db, party_id)
        check_version(ext, version)
        old = snap(ext)
        ext.party.is_active = False
        ext.party.updated_by = who.user_id
        ext.is_active = False
        db.flush()
        audit(db, who, request, party_id, "remove", old, snap(ext))
        db.commit()
        return cfg.out_schema.model_validate(out_dict(get(db, party_id)))

    @router.delete("/{party_id}/permanent", status_code=status.HTTP_204_NO_CONTENT)
    def delete_partner_permanently(
        who: RequireAdmin,
        db: DbDep,
        party_id: uuid.UUID,
        confirm: Annotated[str, Query(max_length=20)],
        request: Request,
    ) -> None:
        ext = get(db, party_id)
        if ext.party.is_active:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Remove the {cfg.kind} before deleting it permanently",
            )
        if db.scalar(select(func.count()).where(PriceList.party_id == party_id)):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"This {cfg.kind} has price lists, which are kept as history: "
                "it can't be deleted permanently.",
            )
        if confirm.strip().upper() != ext.party.code:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, f"Type the {cfg.kind} code to confirm"
            )
        old = detail(ext).model_dump(mode="json")
        db.execute(delete(Party).where(Party.id == party_id))  # cascades to everything below
        audit(db, who, request, party_id, "delete_permanently", old, None)
        db.commit()

    return router
