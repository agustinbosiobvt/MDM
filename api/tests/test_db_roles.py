"""The DB privilege policy (alembic_helpers.apply_grants) holds in the real database."""

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError


def _denied(engine: Engine, sql: str) -> None:
    with engine.connect() as conn, pytest.raises(DBAPIError) as exc:
        conn.execute(text(sql))
    assert "permission denied" in str(exc.value) or "must be owner" in str(exc.value)


def test_app_can_read_lookups(app_engine: Engine) -> None:
    with app_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM mdm.country")).scalar_one() == 249
        eur = conn.execute(text("SELECT minor_units FROM mdm.currency WHERE code = 'EUR'"))
        assert eur.scalar_one() == 2


def test_audit_log_is_insert_only_for_app(app_engine: Engine) -> None:
    with app_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO mdm.audit_log (entity, action, new_values) "
                "VALUES ('test', 'probe', '{}')"
            )
        )
    _denied(app_engine, "SELECT * FROM mdm.audit_log")
    _denied(app_engine, "UPDATE mdm.audit_log SET action = 'x'")
    _denied(app_engine, "DELETE FROM mdm.audit_log")
    _denied(app_engine, "TRUNCATE mdm.audit_log")


def test_app_cannot_delete_by_default(app_engine: Engine) -> None:
    _denied(app_engine, "DELETE FROM mdm.country WHERE code = 'ZZ'")


@pytest.mark.parametrize(
    "ddl",
    [
        "CREATE TABLE mdm.evil (id int)",
        "CREATE TABLE public.evil (id int)",
        "DROP TABLE mdm.country",
        "ALTER TABLE mdm.country ADD COLUMN x int",
    ],
)
def test_app_has_no_ddl(app_engine: Engine, ddl: str) -> None:
    _denied(app_engine, ddl)


def test_app_cannot_touch_migration_state(app_engine: Engine) -> None:
    _denied(app_engine, "SELECT * FROM mdm.alembic_version")


def test_app_role_is_not_privileged(app_engine: Engine) -> None:
    with app_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT rolsuper, rolcreaterole, rolcreatedb, rolbypassrls "
                "FROM pg_roles WHERE rolname = current_user"
            )
        ).one()
    assert tuple(row) == (False, False, False, False)


def test_readonly_cannot_write(readonly_engine: Engine) -> None:
    with readonly_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM mdm.currency")).scalar_one() > 100
    with readonly_engine.connect() as conn, pytest.raises(DBAPIError, match="read-only"):
        conn.execute(text("INSERT INTO mdm.payment_term (code, name) VALUES ('X1', 'x')"))
