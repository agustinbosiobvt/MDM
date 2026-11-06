"""Addresses and contacts of any party (company now; customers and vendors in Phase 5)."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, update
from sqlalchemy.orm import Session

from app.audit.service import record
from app.auth.deps import Principal, RequireEditor
from app.core.errors import STALE_MESSAGE
from app.core.net import client_ip
from app.db import get_db
from app.lookups.router import require_known_codes
from app.parties.models import Address, Contact, Party
from app.parties.schemas import (
    AddressIn,
    AddressOut,
    AddressUpdate,
    ContactIn,
    ContactOut,
    ContactUpdate,
)

router = APIRouter(tags=["parties"])

DbDep = Annotated[Session, Depends(get_db)]
VersionQ = Annotated[int, Query(ge=1)]

# Which address types each kind of party uses.
ADDRESS_TYPES = {
    "company": {"registered", "billing", "warehouse"},
    "customer": {"billing", "shipping"},  # shipping = ship-to
    "vendor": {"billing", "pickup", "factory"},
}
ADDRESS_FIELDS = ("address_type", "line1", "line2", "postal_code", "city", "region", "country_code")
CONTACT_FIELDS = ("name", "role_title", "contact_role", "email", "phone", "is_primary")


def _check_contact_role(party: Party, role: str | None) -> None:
    if role is not None and party.party_type != "vendor":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Contact roles are used for vendor contacts only"
        )


def _active_party(db: Session, party_id: uuid.UUID) -> Party:
    party = db.get(Party, party_id)
    if party is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Record not found")
    if not party.is_active:
        raise HTTPException(status.HTTP_409_CONFLICT, "Reactivate this record before changing it")
    return party


def _check_version(current: int, sent: int) -> None:
    if current != sent:
        raise HTTPException(status.HTTP_409_CONFLICT, STALE_MESSAGE)


def _snap(obj: object, fields: tuple[str, ...]) -> dict[str, Any]:
    return {f: getattr(obj, f) for f in fields}


def _audit(
    db: Session,
    who: Principal,
    request: Request,
    entity: str,
    obj_id: uuid.UUID,
    action: str,
    old: dict[str, Any] | None,
    new: dict[str, Any] | None,
) -> None:
    record(
        db,
        entity=entity,
        entity_id=obj_id,
        action=action,
        user_id=who.user_id,
        user_email=who.email,
        old=old,
        new=new,
        ip=client_ip(request),
    )


def _check_address_type(party: Party, address_type: str) -> None:
    allowed = ADDRESS_TYPES[party.party_type]
    if address_type not in allowed:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"A {party.party_type} address must be one of: {', '.join(sorted(allowed))}",
        )


# --- Addresses -------------------------------------------------------------------


@router.post("/api/parties/{party_id}/addresses", status_code=status.HTTP_201_CREATED)
def add_address(
    who: RequireEditor, db: DbDep, party_id: uuid.UUID, body: AddressIn, request: Request
) -> AddressOut:
    party = _active_party(db, party_id)
    _check_address_type(party, body.address_type)
    require_known_codes(db, country=body.country_code)
    addr = Address(
        party_id=party.id, created_by=who.user_id, updated_by=who.user_id, **body.model_dump()
    )
    db.add(addr)
    db.flush()
    _audit(db, who, request, "address", addr.id, "create", None, _snap(addr, ADDRESS_FIELDS))
    db.commit()
    db.refresh(addr)
    return AddressOut.model_validate(addr)


def _get_address(db: Session, address_id: uuid.UUID) -> Address:
    addr = db.get(Address, address_id)
    if addr is None or not addr.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Address not found")
    return addr


@router.patch("/api/addresses/{address_id}")
def update_address(
    who: RequireEditor, db: DbDep, address_id: uuid.UUID, body: AddressUpdate, request: Request
) -> AddressOut:
    addr = _get_address(db, address_id)
    party = _active_party(db, addr.party_id)
    _check_version(addr.version, body.version)
    _check_address_type(party, body.address_type)
    require_known_codes(db, country=body.country_code)
    old = _snap(addr, ADDRESS_FIELDS)
    for field, value in body.model_dump(exclude={"version"}).items():
        setattr(addr, field, value)
    addr.updated_by = who.user_id
    db.flush()
    _audit(db, who, request, "address", addr.id, "update", old, _snap(addr, ADDRESS_FIELDS))
    db.commit()
    db.refresh(addr)
    return AddressOut.model_validate(addr)


@router.delete("/api/addresses/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_address(
    who: RequireEditor, db: DbDep, address_id: uuid.UUID, version: VersionQ, request: Request
) -> None:
    addr = _get_address(db, address_id)
    _active_party(db, addr.party_id)
    _check_version(addr.version, version)
    addr.is_active = False
    addr.updated_by = who.user_id
    db.flush()
    _audit(db, who, request, "address", addr.id, "remove", _snap(addr, ADDRESS_FIELDS), None)
    db.commit()


# --- Contacts --------------------------------------------------------------------


def _clear_other_primaries(
    db: Session, who: Principal, party_id: uuid.UUID, keep: uuid.UUID
) -> None:
    """Only one primary contact per party: demote the others (and bump their version)."""
    db.execute(
        update(Contact)
        .where(Contact.party_id == party_id, Contact.id != keep, Contact.is_primary)
        .values(
            is_primary=False,
            version=Contact.version + 1,
            updated_by=who.user_id,
            updated_at=func.now(),
        )
        .execution_options(synchronize_session=False)
    )


def _has_primary(db: Session, party_id: uuid.UUID) -> bool:
    return bool(
        db.scalar(
            func.count(Contact.id)
            .select()
            .where(Contact.party_id == party_id, Contact.is_primary, Contact.is_active)
        )
    )


@router.post("/api/parties/{party_id}/contacts", status_code=status.HTTP_201_CREATED)
def add_contact(
    who: RequireEditor, db: DbDep, party_id: uuid.UUID, body: ContactIn, request: Request
) -> ContactOut:
    party = _active_party(db, party_id)
    _check_contact_role(party, body.contact_role)
    data = body.model_dump()
    # The first contact becomes the primary one automatically.
    data["is_primary"] = body.is_primary or not _has_primary(db, party.id)
    contact = Contact(party_id=party.id, created_by=who.user_id, updated_by=who.user_id, **data)
    contact.id = uuid.uuid4()
    if contact.is_primary:
        _clear_other_primaries(db, who, party.id, keep=contact.id)
    db.add(contact)
    db.flush()
    _audit(db, who, request, "contact", contact.id, "create", None, _snap(contact, CONTACT_FIELDS))
    db.commit()
    db.refresh(contact)
    return ContactOut.model_validate(contact)


def _get_contact(db: Session, contact_id: uuid.UUID) -> Contact:
    contact = db.get(Contact, contact_id)
    if contact is None or not contact.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Contact not found")
    return contact


@router.patch("/api/contacts/{contact_id}")
def update_contact(
    who: RequireEditor, db: DbDep, contact_id: uuid.UUID, body: ContactUpdate, request: Request
) -> ContactOut:
    contact = _get_contact(db, contact_id)
    _check_contact_role(_active_party(db, contact.party_id), body.contact_role)
    _check_version(contact.version, body.version)
    old = _snap(contact, CONTACT_FIELDS)
    if body.is_primary and not contact.is_primary:
        _clear_other_primaries(db, who, contact.party_id, keep=contact.id)
    for field, value in body.model_dump(exclude={"version"}).items():
        setattr(contact, field, value)
    contact.updated_by = who.user_id
    db.flush()
    _audit(db, who, request, "contact", contact.id, "update", old, _snap(contact, CONTACT_FIELDS))
    db.commit()
    db.refresh(contact)
    return ContactOut.model_validate(contact)


@router.delete("/api/contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_contact(
    who: RequireEditor, db: DbDep, contact_id: uuid.UUID, version: VersionQ, request: Request
) -> None:
    contact = _get_contact(db, contact_id)
    _active_party(db, contact.party_id)
    _check_version(contact.version, version)
    contact.is_active = False
    contact.is_primary = False
    contact.updated_by = who.user_id
    db.flush()
    _audit(db, who, request, "contact", contact.id, "remove", _snap(contact, CONTACT_FIELDS), None)
    db.commit()
