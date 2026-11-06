"""Validation shared by company, customer and vendor screens.

Optional fields are `Annotated[<constrained str> | None, BeforeValidator(_blank_to_none)]`:
blank strings become None first, and the constraints apply only to real strings.
(Constraints placed directly on `str | None` would be applied to None and crash.)
"""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints


def _blank_to_none(v: object) -> object:
    if isinstance(v, str) and not v.strip():
        return None
    return v


def _upper_compact(v: object) -> object:
    if isinstance(v, str):
        return "".join(v.split()).upper()
    return v


Blank = BeforeValidator(_blank_to_none)
UpperCompact = BeforeValidator(_upper_compact)

Text100 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Text200 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Opt20 = Annotated[
    Annotated[str, StringConstraints(strip_whitespace=True, max_length=20)] | None, Blank
]
Opt50 = Annotated[
    Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)] | None, Blank
]
Opt100 = Annotated[
    Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] | None, Blank
]
Opt200 = Annotated[
    Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None, Blank
]

# Constraints first, then UpperCompact: the input is compacted/upper-cased, then checked
# (and the limits show in the OpenAPI schema).
Code = Annotated[
    str, StringConstraints(max_length=20, pattern=r"^[A-Z0-9][A-Z0-9_-]{1,19}$"), UpperCompact
]
CountryCode = Annotated[str, StringConstraints(max_length=2, pattern=r"^[A-Z]{2}$"), UpperCompact]
CurrencyCode = Annotated[str, StringConstraints(max_length=3, pattern=r"^[A-Z]{3}$"), UpperCompact]
Eori = Annotated[
    Annotated[
        str, StringConstraints(max_length=17, pattern=r"^[A-Z]{2}[A-Z0-9]{1,15}$"), UpperCompact
    ]
    | None,
    Blank,
]
Email = Annotated[
    Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            to_lower=True,
            max_length=254,
            pattern=r"(?i)^[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}$",  # checked before to_lower
        ),
    ]
    | None,
    Blank,
]
Phone = Annotated[
    Annotated[
        str,
        StringConstraints(strip_whitespace=True, max_length=40, pattern=r"^[0-9+() ./x-]{3,40}$"),
    ]
    | None,
    Blank,
]
AddressType = Literal["registered", "billing", "warehouse", "shipping", "pickup", "factory"]
ContactRole = Literal["sales", "logistics", "quality", "other"]
PartnerStatus = Literal["active", "on_hold", "blocked"]
PaymentTermCode = Annotated[
    str, StringConstraints(max_length=20, pattern=r"^[A-Z0-9_]{2,20}$"), UpperCompact
]
IncotermCode = Annotated[str, StringConstraints(max_length=3, pattern=r"^[A-Z]{3}$"), UpperCompact]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Addresses -------------------------------------------------------------------


class AddressIn(Strict):
    address_type: AddressType
    line1: Text200
    line2: Opt200 = None
    postal_code: Opt20 = None
    city: Text100
    region: Opt100 = None
    country_code: CountryCode


class AddressUpdate(AddressIn):
    version: int = Field(ge=1)


class AddressOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    party_id: uuid.UUID
    address_type: AddressType
    line1: str
    line2: str | None
    postal_code: str | None
    city: str
    region: str | None
    country_code: str
    version: int
    updated_at: datetime


# --- Contacts --------------------------------------------------------------------


class ContactIn(Strict):
    name: Text200
    role_title: Opt100 = None
    email: Email = None
    phone: Phone = None
    is_primary: bool = False
    contact_role: ContactRole | None = None  # vendors only


class ContactUpdate(ContactIn):
    version: int = Field(ge=1)


class ContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    party_id: uuid.UUID
    name: str
    role_title: str | None
    email: str | None
    phone: str | None
    is_primary: bool
    contact_role: ContactRole | None
    version: int
    updated_at: datetime
