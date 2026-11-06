"""Customers and vendors ("partners"): the identity + trading terms they share."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from app.parties.schemas import (
    AddressOut,
    Blank,
    Code,
    ContactOut,
    CountryCode,
    CurrencyCode,
    Eori,
    IncotermCode,
    Opt200,
    PartnerStatus,
    PaymentTermCode,
    Strict,
    Text200,
    UpperCompact,
)

OptPaymentTerm = Annotated[PaymentTermCode | None, Blank]
OptIncoterm = Annotated[IncotermCode | None, Blank]


# --- Shared ---------------------------------------------------------------------------


class PartnerCreate(Strict):
    code: Code
    legal_name: Text200
    trade_name: Opt200 = None
    country_code: CountryCode
    default_currency: CurrencyCode = "EUR"
    status: PartnerStatus = "active"
    payment_term_code: OptPaymentTerm = None
    incoterm_code: OptIncoterm = None


class PartnerUpdate(Strict):
    version: int = Field(ge=1)
    code: Code | None = None
    legal_name: Text200 | None = None
    trade_name: Opt200 = None
    country_code: CountryCode | None = None
    default_currency: CurrencyCode | None = None
    status: PartnerStatus | None = None
    payment_term_code: OptPaymentTerm = None
    incoterm_code: OptIncoterm = None
    is_active: bool | None = None


class PartnerOut(BaseModel):
    id: uuid.UUID
    code: str
    legal_name: str
    trade_name: str | None
    country_code: str
    default_currency: str
    status: PartnerStatus
    payment_term_code: str | None
    incoterm_code: str | None
    is_active: bool
    version: int
    created_at: datetime
    updated_at: datetime


# --- Customers ------------------------------------------------------------------------

VendorCodePart = Annotated[
    str, StringConstraints(max_length=20, pattern=r"^[A-Z0-9_-]{2,20}$"), UpperCompact
]


class VendorCodeIn(Strict):
    parent_code: VendorCodePart
    child_code: VendorCodePart
    destination_country: Annotated[CountryCode | None, Blank] = None


class VendorCodeUpdate(VendorCodeIn):
    version: int = Field(ge=1)


class VendorCodeOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    customer_id: uuid.UUID
    parent_code: str
    child_code: str
    destination_country: str | None
    version: int


class CustomerCreate(PartnerCreate):
    pass


class CustomerUpdate(PartnerUpdate):
    pass


class CustomerOut(PartnerOut):
    pass


class CustomerDetail(CustomerOut):
    addresses: list[AddressOut]
    contacts: list[ContactOut]
    vendor_codes: list[VendorCodeOut]


# --- Vendors --------------------------------------------------------------------------

LeadTime = Annotated[int, Field(ge=0, le=730)]
Moq = Annotated[int, Field(ge=1, le=10_000_000)]


class VendorCreate(PartnerCreate):
    eori: Eori = None
    lead_time_days: LeadTime | None = None
    moq: Moq | None = None


class VendorUpdate(PartnerUpdate):
    eori: Eori = None
    lead_time_days: LeadTime | None = None
    moq: Moq | None = None


class VendorOut(PartnerOut):
    eori: str | None
    lead_time_days: int | None
    moq: int | None


class VendorDetail(VendorOut):
    addresses: list[AddressOut]
    contacts: list[ContactOut]
