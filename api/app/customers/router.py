"""Customers (e.g. Amazon MX, Amazon US) and their Amazon vendor codes."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.audit.service import record
from app.auth.deps import RequireEditor
from app.core.errors import STALE_MESSAGE
from app.core.net import client_ip
from app.customers.models import Customer, CustomerVendorCode
from app.db import get_db
from app.lookups.router import require_known_codes
from app.parties.partner_router import PartnerConfig, build_router
from app.parties.partner_schemas import (
    CustomerCreate,
    CustomerDetail,
    CustomerOut,
    CustomerUpdate,
    VendorCodeIn,
    VendorCodeOut,
    VendorCodeUpdate,
)

CODE_FIELDS = ("parent_code", "child_code", "destination_country")


def _vendor_codes(c: Customer) -> dict[str, Any]:
    return {
        "vendor_codes": [VendorCodeOut.model_validate(v) for v in c.vendor_codes if v.is_active]
    }


router = build_router(
    PartnerConfig(
        kind="customer",
        label="Customer",
        prefix="/api/customers",
        model=Customer,
        create_schema=CustomerCreate,
        update_schema=CustomerUpdate,
        out_schema=CustomerOut,
        detail_schema=CustomerDetail,
        ext_fields=("status", "default_currency", "payment_term_code", "incoterm_code"),
        detail_extra=_vendor_codes,
    )
)

codes_router = APIRouter(tags=["customer"])
DbDep = Annotated[Session, Depends(get_db)]


def _active_customer(db: Session, customer_id: uuid.UUID) -> Customer:
    c = db.get(Customer, customer_id)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    if not c.party.is_active:
        raise HTTPException(status.HTTP_409_CONFLICT, "Reactivate this record before changing it")
    return c


def _get_code(db: Session, code_id: uuid.UUID) -> CustomerVendorCode:
    v = db.get(CustomerVendorCode, code_id)
    if v is None or not v.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vendor code not found")
    return v


def _snap(v: CustomerVendorCode) -> dict[str, Any]:
    return {f: getattr(v, f) for f in CODE_FIELDS}


def _audit(
    db: Session,
    request: Request,
    who: Any,
    v: CustomerVendorCode,
    action: str,
    old: dict[str, Any] | None,
    new: dict[str, Any] | None,
) -> None:
    record(
        db,
        entity="customer_vendor_code",
        entity_id=v.id,
        action=action,
        user_id=who.user_id,
        user_email=who.email,
        old=old,
        new=new,
        ip=client_ip(request),
    )


@codes_router.post("/api/customers/{customer_id}/vendor-codes", status_code=201)
def add_vendor_code(
    who: RequireEditor, db: DbDep, customer_id: uuid.UUID, body: VendorCodeIn, request: Request
) -> VendorCodeOut:
    customer = _active_customer(db, customer_id)
    require_known_codes(db, country=body.destination_country)
    v = CustomerVendorCode(
        customer_id=customer.party_id,
        created_by=who.user_id,
        updated_by=who.user_id,
        **body.model_dump(),
    )
    db.add(v)
    db.flush()
    _audit(db, request, who, v, "create", None, _snap(v))
    db.commit()
    db.refresh(v)
    return VendorCodeOut.model_validate(v)


@codes_router.patch("/api/vendor-codes/{code_id}")
def update_vendor_code(
    who: RequireEditor, db: DbDep, code_id: uuid.UUID, body: VendorCodeUpdate, request: Request
) -> VendorCodeOut:
    v = _get_code(db, code_id)
    _active_customer(db, v.customer_id)
    if v.version != body.version:
        raise HTTPException(status.HTTP_409_CONFLICT, STALE_MESSAGE)
    require_known_codes(db, country=body.destination_country)
    old = _snap(v)
    for field, value in body.model_dump(exclude={"version"}).items():
        setattr(v, field, value)
    v.updated_by = who.user_id
    db.flush()
    _audit(db, request, who, v, "update", old, _snap(v))
    db.commit()
    db.refresh(v)
    return VendorCodeOut.model_validate(v)


@codes_router.delete("/api/vendor-codes/{code_id}", status_code=204)
def remove_vendor_code(
    who: RequireEditor,
    db: DbDep,
    code_id: uuid.UUID,
    version: Annotated[int, Query(ge=1)],
    request: Request,
) -> None:
    v = _get_code(db, code_id)
    _active_customer(db, v.customer_id)
    if v.version != version:
        raise HTTPException(status.HTTP_409_CONFLICT, STALE_MESSAGE)
    v.is_active = False
    v.updated_by = who.user_id
    db.flush()
    _audit(db, request, who, v, "remove", _snap(v), None)
    db.commit()
