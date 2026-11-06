import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.parties.schemas import (
    AddressOut,
    Code,
    ContactOut,
    CountryCode,
    Eori,
    Opt50,
    Opt200,
    Strict,
    Text200,
)


class CompanyCreate(Strict):
    code: Code
    legal_name: Text200
    trade_name: Opt200 = None
    eori: Eori = None
    country_code: CountryCode
    tax_registration_number: Opt50 = None
    is_default: bool = False


class CompanyUpdate(Strict):
    version: int = Field(ge=1)
    code: Code | None = None
    legal_name: Text200 | None = None
    trade_name: Opt200 = None
    eori: Eori = None
    country_code: CountryCode | None = None
    tax_registration_number: Opt50 = None
    is_active: bool | None = None


class CompanyOut(BaseModel):
    id: uuid.UUID
    code: str
    legal_name: str
    trade_name: str | None
    eori: str | None
    country_code: str
    tax_registration_number: str | None
    is_default: bool
    is_active: bool
    version: int
    created_at: datetime
    updated_at: datetime


class CompanyDetail(CompanyOut):
    addresses: list[AddressOut]
    contacts: list[ContactOut]
