"""Guard: tests and scripts may only write to throwaway databases (name ends in _test or _e2e).

Imported by conftest.py before anything connects, so a wrong TEST_DATABASE_NAME stops
pytest at start-up instead of touching the real `mdm` database.
"""

SAFE_SUFFIXES = ("_test", "_e2e")


class UnsafeDatabaseError(RuntimeError):
    pass


def require_throwaway_database(name: str | None) -> str:
    if not name or not name.endswith(SAFE_SUFFIXES):
        raise UnsafeDatabaseError(
            f"refusing to run against database {name!r}: "
            f"tests and scripts only use databases ending in {' or '.join(SAFE_SUFFIXES)}"
        )
    return name
