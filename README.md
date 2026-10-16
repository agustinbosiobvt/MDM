# BVT MDM

Master Data Management for Buena Vida Trading: company, customers, vendors and price lists.
Version 1 runs locally, with standard Postgres and Docker only, so it can move to GCP, AWS or Azure without a rewrite.

The design is in [`docs/plan.md`](docs/plan.md) and the working conventions are in [`CLAUDE.md`](CLAUDE.md#conventions).

| Phase | Status |
| --- | --- |
| 1 Plan | done |
| 2 Skeleton | done |
| 3 Auth | – |
| 4 Company | – |
| 5 Customers + Vendors | – |
| 6 Price lists + import | – |
| 7 Hardening | – |

## Requirements

- Docker Desktop
- [uv](https://docs.astral.sh/uv/) (it installs Python 3.12 itself)
- Node 22+
- GNU make (on Windows, run it from Git Bash)

## First-time setup

```bash
cp .env.example .env
make secrets            # paste the printed values into .env (and into the two *DATABASE_URL lines)
make install            # uv sync + npm ci + git hooks
make db-up              # Postgres 16 on 127.0.0.1:54330; first start creates roles + databases
make migrate            # schema mdm, lookups, seeds
make up                 # build + run everything → http://localhost:8080
make check              # lint, typecheck, tests, security scans
```

## Running

```bash
make up                 # builds images, runs migrations, starts api + web
make down               # stops everything (data volume kept)
```

Open **http://localhost:8080**. Always use `localhost`, not `127.0.0.1`: the session cookie and the OAuth redirect are bound to that exact origin. nginx in the `web` container serves the UI and proxies `/api` and `/auth` to the API, which has no host port of its own.

## Services

| Service | Image | Port (host, loopback only) | Notes |
| --- | --- | --- | --- |
| `db` | postgres:16 | 54330 | profile `db`, volume `mdm_pg_data` |
| `migrate` | api image | – | profile `tools`, one-shot `alembic upgrade head` as `mdm_migrator` |
| `api` | python:3.12-slim | none (internal only) | non-root, read-only FS, all capabilities dropped |
| `web` | nginx-unprivileged | 8080 | **the only browser origin**: serves the SPA and proxies `/api` and `/auth` |

## Database roles

| Role | Used by | Rights |
| --- | --- | --- |
| `mdm_migrator` | Alembic only | owns schema `mdm` (DDL) |
| `mdm_app` | the API | SELECT/INSERT/UPDATE on business tables, **INSERT only** on `audit_log`, no DDL, no DELETE unless listed in `APP_DELETE_TABLES` |
| `mdm_readonly` | future reporting | SELECT, read-only transactions |

The roles and databases are created by [`db/bootstrap.sql`](db/bootstrap.sql). Grants are re-applied by every migration from one policy (`api/alembic/alembic_helpers.py`), and `api/tests/test_db_roles.py` proves the policy holds.

## Security checklist

This list fills up phase by phase. Phase 7 completes it.

| Requirement | Status | How |
| --- | --- | --- |
| No SQL built from strings | ✅ Phase 2 | SQLAlchemy ORM / bound parameters only |
| Least-privilege DB roles | ✅ Phase 2 | three roles; tested in `test_db_roles.py` |
| Append-only audit log | ✅ Phase 2 | `mdm_app` has INSERT only (no SELECT/UPDATE/DELETE/TRUNCATE), tested |
| TLS to remote DBs | ✅ Phase 2 | the API and Alembic refuse non-local URLs without `sslmode=require`/`verify-*` (`app/config.py`), tested |
| Security headers | ✅ Phase 2 | API: CSP `default-src 'none'`, nosniff, X-Frame-Options DENY, Referrer-Policy, no-store. nginx: SPA CSP without inline scripts. HSTS in production. Tested. |
| CORS limited to the web origin | ✅ Phase 2 | `WEB_ORIGIN` only, tested |
| Generic error messages | ✅ Phase 2 | `app/core/errors.py`: 500s return an error id, and details go only to the log |
| No secrets in repo or images | ✅ Phase 2 | `.env` ignored, `.env.example` shipped, `.dockerignore` excludes env files, the `api` container gets an explicit env list (no superuser/migrator passwords), gitleaks in `make audit` |
| Dependency and code scans | ✅ Phase 2 | `make audit`: pip-audit, bandit, npm audit, gitleaks |
| Containers hardened | ✅ Phase 2 | non-root, read-only root FS, `no-new-privileges`, capabilities dropped, ports bound to 127.0.0.1 |
| No tokens in browser storage | ✅ Phase 2 | eslint bans `localStorage`/`sessionStorage`/`dangerouslySetInnerHTML` |
| Google OIDC + PKCE, allow-list, sessions | Phase 3 | |
| CSRF protection | Phase 3 | |
| Role checks on every endpoint (403 tests) | Phase 3 | |
| Rate limiting (login, import) | Phase 3 / 6 | |
| Upload checks (size/ext/MIME, random name, temp deletion) | Phase 6 | |
| Excel formula-injection neutralisation | Phase 6 | |

## Troubleshooting

- **DB connection hangs on Windows:** use `127.0.0.1` in the `*DATABASE_URL` lines, not `localhost`. Windows tries IPv6 `::1` first, and the container only listens on IPv4.
- **"An Application Control policy has blocked this file"** for a Python tool: run it as `uv run python -m <tool>`.
- **Port 8000 is busy:** that's expected, because the PL&CI app uses it. MDM uses 8080 only.

## Known limitations

- Rate limiting is in-process (slowapi): it's correct for one API instance only. Behind several instances, move it to the load balancer/WAF or a shared store.
