"""Seed the first Admin from BOOTSTRAP_ADMIN_EMAIL (idempotent; never modifies an existing user)."""

import logging

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.audit.service import record
from app.users.models import AppUser, Role

log = logging.getLogger("app.bootstrap")


def ensure_bootstrap_admin(db: Session, email: str, allowed_domain: str) -> None:
    if not email:
        return
    if not email.endswith("@" + allowed_domain):
        log.error("BOOTSTRAP_ADMIN_EMAIL must be an @%s address; ignored", allowed_domain)
        return
    result = db.execute(
        insert(AppUser)
        .values(email=email, role=Role.ADMIN.value, display_name=None)
        .on_conflict_do_nothing(index_elements=["email"])
    )
    if result.rowcount:  # type: ignore[attr-defined]
        record(
            db, entity="app_user", action="bootstrap_admin", new={"email": email, "role": "admin"}
        )
        log.info("bootstrap admin created: %s", email)
    db.commit()
