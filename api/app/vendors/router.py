"""Vendors: brands and manufacturers (e.g. Nobby)."""

from app.parties.partner_router import PartnerConfig, build_router
from app.parties.partner_schemas import VendorCreate, VendorDetail, VendorOut, VendorUpdate
from app.vendors.models import Vendor

router = build_router(
    PartnerConfig(
        kind="vendor",
        label="Vendor",
        prefix="/api/vendors",
        model=Vendor,
        create_schema=VendorCreate,
        update_schema=VendorUpdate,
        out_schema=VendorOut,
        detail_schema=VendorDetail,
        ext_fields=(
            "status",
            "default_currency",
            "payment_term_code",
            "incoterm_code",
            "lead_time_days",
            "moq",
        ),
    )
)
