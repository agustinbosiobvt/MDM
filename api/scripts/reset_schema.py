"""Drop schema mdm in a throwaway database (e2e/test only) so migrations start clean.

Refuses to run unless the database name ends in _e2e or _test.
Usage: python scripts/reset_schema.py   (reads MIGRATION_DATABASE_URL)
"""

import os
import sys

from sqlalchemy import create_engine, make_url, text


def main() -> int:
    url = make_url(os.environ["MIGRATION_DATABASE_URL"])
    if not (url.database or "").endswith(("_e2e", "_test")):
        print(f"refusing to reset database {url.database!r}", file=sys.stderr)
        return 1
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS mdm CASCADE"))
    engine.dispose()
    print(f"schema mdm dropped in {url.database}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
