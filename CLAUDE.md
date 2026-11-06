# BVT MDM, version 1: project spec

You are building **version 1 of BVT's MDM (Master Data Management) web app** for Buena Vida Trading, a distributor selling mainly to Amazon (Direct Import model). It runs locally for now, and has to be ready to move to GCP, AWS or Azure later without a rewrite. **Security is a hard requirement, not a later add-on.**

Work in the phases at the end of this prompt. **Start in plan mode:** inspect the environment, propose the plan and the DB schema, and wait for my approval before writing code. Stop and ask me whenever something here is ambiguous or conflicts with what you find.

## 1. Scope of v1

Three modules. Each one has a list (search, filter, sort, paginate), a detail view, add, edit and remove:

1. **Company**: BVT's own data. Identity (code, legal name, trade name, EORI, country, **tax registration number**: free text, optional, e.g. `TRN 104965266000001`, printed on BVT's commercial invoices; Company only, not on customers or vendors), several addresses (registered, billing, warehouse), contacts/responsible people (name, job title, email, phone, primary). Several companies are allowed; one is marked as the default. **No Tax ID and no currency.**
2. **Customers** (e.g. Amazon MX, Amazon US): code, legal name, trade name, country, business status (Active / On hold / Blocked), default currency, payment terms, Incoterm, addresses (billing / ship-to, several), contacts, Amazon vendor codes (several parent/child pairs per customer, with optional destination country), and their **price list** (see below). **No Tax ID.**
3. **Vendors** (brands/manufacturers, e.g. Nobby): code, legal name, trade name, EORI, country, business status (Active / On hold / Blocked), default currency, payment terms, Incoterm, lead time in days, MOQ, addresses (billing / pick-up / factory), contacts (contact role Sales / Logistics / Quality / Other, plus job title), and their **price list** (see below). **No Tax ID.**

**Where price lists live:** there is **no separate "Price lists" menu**. Price lists live inside the customer or vendor: open a customer → its data at the top, then a **Price list** section for that customer (same for vendors). The section has the **"Import price list"** button, the **lines table**, **filters** (category, brand, and a search box for EAN / ASIN / description), the **last update and who made it**, the **status**, and the **version history**.

Out of scope for v1: price and margin comparison, FX conversion, product master, POs and shipments. The v1 data model must not block any of them.

## 2. Stack (use exactly this unless you find a blocker; if you do, tell me)

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2, Authlib (Google OIDC), openpyxl (Excel), pytest
- **Frontend:** React, TypeScript and Vite, TanStack Query + TanStack Table, React Hook Form + Zod. Keep the UI clean and simple.
- **DB:** PostgreSQL 16. I already run Postgres in Docker Desktop: connect via `DATABASE_URL` in `.env`. Docker Compose also gets an optional `db` service for a clean local setup.
- **Packaging:** Docker Compose (api, web, optional db). Standard Postgres only: no cloud-specific features.

## 3. Existing database draft (do this first)

There is already a first draft of the schema in my local Postgres. Before you design anything:
- Connect read-only, list the schemas, tables, columns and constraints, and show me a summary.
- Compare that draft with section 5 and propose what to keep, change or add.
- **Never drop or alter existing tables without my explicit OK.** Put the new tables in a dedicated schema `mdm`, managed only by Alembic migrations.

## 4. Common rules for all tables and screens

- Primary keys are UUIDs. Every table has `created_at`, `created_by`, `updated_at`, `updated_by`, `is_active`, and `version` (an integer used for optimistic locking: an edit on a stale version returns 409, and the UI shows "someone else changed this record").
- **Remove = soft delete** (`is_active = false`). Only an Admin can hard delete, and only after a confirmation.
- **Audit log table** `mdm.audit_log`: who, when, entity, entity_id, action, old values and new values (JSONB). The app's DB role has INSERT-only permission on it.
- Standards: ISO 3166-1 alpha-2 countries, ISO 4217 currency codes (lookup tables, seeded), ISO 8601 dates. **Money is `NUMERIC(18,4)`, never float.**
- Duplicates are blocked: a unique code (across company, customers and vendors), and an active Amazon parent/child vendor-code pair belongs to one customer only.

## 5. Price lists: the critical part

The same model serves customers and vendors (`owner_type` = customer | vendor + `owner_id`, or two FK columns with a CHECK constraint; propose one).

**price_list (header):** name, owner, default currency, valid_from, valid_to, status (Draft / Active / Expired), source file name, source file SHA-256, imported_at, imported_by, notes.

**price_list_line:** one row per product: `ean` (text), `asin` (text), `vendor_sku` (text), description, **category**, brand, case pack qty, MOQ, unit of measure, country of origin, HS code, raw source row (JSONB, kept for traceability). **Category and brand** are filled from the file during import mapping when the file has them, and the user can edit them later on the line (they are the only editable line fields; prices are never edited).

**price_list_line_price:** a line can carry **several prices, each with its own currency**: `price_type` (purchase, domestic_cost, import_cost, rrp, rrp_ex_vat, retailer_cost, …, as a lookup table), `amount NUMERIC(18,4)`, `currency CHAR(3)` (required, never inferred silently).

Rules:
- A line needs at least one product key (EAN or ASIN). ASIN is often blank.
- **EAN/GTIN is stored as text.** Excel gives `4033766024122.0`, so strip the `.0`, keep leading zeros, and validate the GTIN check digit (8/12/13/14 digits). Invalid values are flagged, not silently fixed. ASIN must match `^[A-Z0-9]{10}$` after trimming. Values like `' '` or `#N/A` count as empty.
- Only one Active price list per owner + currency + overlapping period. Activating a new list expires the previous one.
- Prices are never overwritten in place. A re-import creates a new price list version, so history is kept for future margin analysis.
- **Do not store converted prices.** Create an empty `mdm.exchange_rate` table (date, from_ccy, to_ccy, rate, source) for later use, and don't import any rates.

## 6. Excel import (the real files are in `./samples/`)

The formats differ, so build an **import wizard with column mapping**, not a fixed parser:

1. Upload (.xlsx/.csv only; reject .xlsm/.xls; max 20 MB; read with openpyxl `read_only=True, data_only=True`, so formulas are never executed and only cached values are read).
2. Pick the sheet and the **header row** (auto-detect it, and let the user change it). Show a preview of 20 rows.
3. Map columns to fields (including category and brand when the file has them). For every price column, choose its price_type and **its currency**, either (a) a fixed value, (b) another column, or (c) auto-suggested from the header (`(USD)`, `€`, `(MXN)`). The user always confirms.
4. Validate. Show a report: rows OK, rows with warnings (invalid EAN, missing currency, duplicate key in the file), rows rejected. Then the user confirms the import.
5. **Save the mapping as a template** per customer/vendor, so next month's file imports in one click.

Brand is mapped from the file when present (Amazon: `Brand Name`). Neither sample file has a category column, so after importing them category stays empty and is edited per line.

**Performance targets** (per sample file, about 7,500 rows, measured in the Docker stack and asserted by an automated test): preview + header detection < 5 s; validation report < 15 s; commit import < 30 s. In the Price list section, the first page of lines and each filter/search < 1 s.

What the two sample files look like (use them as test fixtures; don't commit them, add `samples/` to `.gitignore`):

**`Client_prices_AmzMx.xlsx`**: the Amazon "Quote Sheet Template – Direct Imports Parity". Sheet `ALL` has about 7,500 rows: row 1 is the title, rows 2–3 are flags and column numbers, **row 4 is the header**, rows 5–6 are "Mandatory/Recommended" and instructions, and **data starts at row 7**. Sheets `Acc` (empty template) and `Forecast` (different structure) are not price lists. Key columns: `ASIN`, `Destination country`, `Import Parent/Child Vendor Code`, `Shipping Port`, `EAN`, `UPC`, `Brand Name`, `Item Name`, `Incoterm`, `Domestic Cost (USD)`, `Import Cost (USD)`, `MOQ`, `Case Pack Quantity`, `Cubic Meters (CBM)`, `Recommended Retail Price Currency` (e.g. MXN) + `Recommended Retail Price (In local currency)`. So the currency sometimes lives in the header and sometimes in another column. ASIN is often `' '`.

**`NOBBY_PLS_GEN_Pl-0-2025-…xlsx`**: the vendor price list, sheet `Tabelle1`, about 7,500 rows. Rows 1–5 are a metadata block (vendor name, "valid from 15.08.2025", VAT, FX rates such as EUR to MX 21.43); **row 7 is the header**, and data starts at row 8. Header names are **duplicated** (`ASIN` appears 4 times, `barcode` 3 times), so map by column letter/index, not by name. Prices: `PRICE €` (purchase, EUR), `RSP €` (EUR), `MX RRP No VAT (MXN)`, `MX RRP (MXN)`, `Retailers Cost (MXN)`, `Retailer Cost (USD)`. There are also derived columns (`Margin…`, `OUR MARGIN`), which should **not** be imported as prices. Also: HS code (`customs`), `Country of origin`, outer carton dims/weights (some stored as text).

Write pytest tests that import both samples through the saved mappings and check: row counts, EAN normalisation, blank-ASIN handling, the currency of every price, and that no float ends up in a money column.

## 7. Security (follow all of it, and explain in the README how each point is covered)

**Authentication: Google only**
- Google OIDC, Authorization Code flow + PKCE, handled **server-side by the API** (backend-for-frontend). The browser never sees or stores tokens: no tokens in localStorage.
- Validate the ID token (signature via Google JWKS, `aud`, `iss`, `exp`, `nonce`). Accept only `hd = buenavidatrading.com` with `email_verified = true`, **and** the email must be in the `mdm.app_user` allow-list (active). Unknown users get a "no access" page and are logged.
- Session: a server-side session table and an opaque random session ID in a cookie with `HttpOnly; Secure; SameSite=Lax`. Idle timeout 30 min, absolute timeout 8 h. Rotate the ID at login. Logout invalidates the session server-side.
- The first Admin is seeded from `.env` (`BOOTSTRAP_ADMIN_EMAIL`).
- Give me step-by-step instructions to create the OAuth client in Google Cloud Console (consent screen "Internal"; redirect URI `http://localhost:8080/auth/callback` for local use).

**Authorization: roles, checked on the server for every endpoint**
| Role | Rights |
| --- | --- |
| Admin | everything + user/role management + hard delete |
| Editor | view/add/edit/soft-delete, imports |
| Viewer | read-only |

Hiding a button in the UI is not security: write tests proving each role gets 403 where it should.

**Application (OWASP Top 10)**
- ORM / parameterised queries only; no SQL built from strings.
- Pydantic validation on every input, with length limits on strings. CSRF protection (double-submit token or `SameSite` + Origin check) on all state-changing requests.
- Security headers: CSP (no inline scripts), HSTS (when on HTTPS), X-Content-Type-Options, X-Frame-Options DENY, Referrer-Policy. CORS limited to the web origin.
- Rate-limit the login and import endpoints. Generic error messages to the client; full details only in the server logs. Never log tokens or cookies.
- Excel export (if added) must neutralise formula injection (prefix values starting with `= + - @`).
- Uploaded files: check size, extension and MIME type, store outside the web root with a random name, and delete the temp file after the import.

**Database**
- Three DB roles: `mdm_migrator` (DDL, used only by Alembic), `mdm_app` (SELECT/INSERT/UPDATE on business tables, INSERT-only on audit_log, no DDL, no superuser), and `mdm_readonly` (for future reporting).
- Connections use `sslmode=require` when not on localhost.

**Secrets and repo**
- `.env` is never committed; ship a `.env.example`. No secrets in code or Docker images.
- Add `pip-audit`, `npm audit`, `bandit` and a secrets scan (e.g. gitleaks) as make/npm scripts, and run them before you declare a phase done.

## 8. Phases (stop after each one, show me what works, and wait for my OK)

1. **Plan:** inspect the existing DB, then propose the schema (an ER diagram in Mermaid), folder structure and anything you would change in this prompt.
2. **Skeleton:** Docker Compose, FastAPI, React, Alembic, the DB roles, `.env.example`, health check. **Update** this `CLAUDE.md` by adding a `## Conventions` section at the end (commands, folder layout, coding rules); never rewrite or remove the existing content.
3. **Auth:** Google login end to end, allow-list, roles, sessions, audit log, plus the security tests.
4. **Company module:** full CRUD; this validates the pattern for the rest.
5. **Customers + Vendors:** CRUD with addresses and contacts.
6. **Price lists + import wizard:** the Price list section on the customer/vendor page (line filters: category, brand, EAN/ASIN/description search), the "Import price list" button and wizard, mapping templates, validation report, versioning, tested on both samples.
7. **Hardening:** run all scans, fix the findings, and write a README with setup steps, a security checklist and known limitations.

Definition of done for every phase: tests pass, lint and type-check pass (ruff, mypy, eslint, tsc), no secrets in the repo, and the README is updated.

## Progress

Keep this list updated at the end of each phase (tick it off and add one line on what was done).

- [x] Phase 1 – Plan: no existing draft; party-supertype schema, roles and layout approved with D1–D4 additions (see docs/plan.md).
- [x] Phase 2 – Skeleton: Compose (db/migrate/api/web), FastAPI + health, React shell, Alembic 0001 (lookups, app_user, audit_log), DB roles + privilege tests, make check green.
- [x] Phase 3 – Auth: server-side Google OIDC (PKCE, JWKS, hd/allow-list), hashed server sessions (30 min idle/8 h), 3-layer CSRF, role matrix on every route, Users admin UI; 105 API tests + 13 Playwright e2e (mock Google).
- [x] Phase 4 – Company module: party supertype + company/address/contact (migration 0003), one default company, soft remove + Admin permanent delete, shared address/contact UI; mock-IdP isolation proven; 246 API tests + 20 Playwright e2e.
- [x] Phase 5 – Customers + Vendors: one router factory for both (business status, payment terms, Incoterm; vendor lead time/MOQ/EORI), Amazon vendor codes, vendor contact roles, international Tax IDs (migration 0004); 387 API tests + 26 Playwright e2e. Corrected 2026-10-16 (migration 0005): Tax ID removed everywhere, Company has no currency, no separate Price lists menu.
- [x] Phase 6 – Price lists + import wizard: Price list section inside customer/vendor pages (versions, filters category/brand/search, line edits, activation with D4 rule), 4-step import wizard (xlsx/csv, header detection, column mapping by index, per-price currency, report, saved templates); both samples import exactly (Amazon 7,515 lines/15,030 prices; Nobby 7,515/45,061); migrations 0006-0007; 555 API tests + 34 Playwright e2e; timings well under targets.
- [x] Phase 7 – Hardening: Draft price list deletion (soft, Editor/Admin, audited; approved 2026-10-19); all scans clean; fixed OAuth code in access logs, forgeable X-Forwarded-For, undeclared input length limits, web caps; README security checklist + findings + cloud steps + limitations; 569 API tests + 35 Playwright e2e.

## Conventions

Added in Phase 2. The approved design lives in `docs/plan.md`; change it there first.

### Commands (repo root, `make help` lists all)
| Command | What it does |
| --- | --- |
| `make db-up` | Start the MDM Postgres container (`bvt-mdm-db-1`, host port 54330, volume `mdm_pg_data`). First start runs `db/bootstrap.sql` (roles + `mdm`/`mdm_test` DBs). |
| `make migrate` | `alembic upgrade head` as `mdm_migrator`. |
| `make up` / `make down` | Full Docker stack at **http://localhost:8080**, the only browser origin (nginx proxies `/api` and `/auth`; the API has no host port). |
| `make test` | pytest against the `mdm_test` DB (schema dropped and re-migrated each run). |
| `make lint` / `make typecheck` | ruff (+ format check) and eslint / mypy strict and tsc. |
| `make audit` | pip-audit, bandit, npm audit, gitleaks. |
| `make e2e` | Playwright (headless Chromium) against the running Docker stack, with a mock OIDC provider instead of Google. |
| `make check` | lint + typecheck + test + audit + e2e. **Must pass before a phase is declared done.** |

### Layout
- `api/app/<module>/`: one package per module (`router.py`, `schemas.py`, `models.py`, `service.py`). Cross-cutting code lives in `core/`, `security/`, `auth/` and `audit/`.
- `api/alembic/versions/NNNN_slug.py`: hand-written, sequential numeric revision IDs. `api/alembic/alembic_helpers.py` holds `audit_columns()`, `uuid_pk()` and the privilege policy `apply_grants()`.
- `api/alembic/seed/*.csv`: committed ISO seeds, regenerated by `api/scripts/gen_iso_seeds.py`.
- `web/src/api/client.ts` is the only place that calls `fetch`. Features live in `web/src/features/<module>/`, shared UI in `web/src/components/`.
- `db/bootstrap.sql`: cluster-level only (roles, databases). Everything inside the DB belongs to Alembic.

### Definition of done for a phase (in addition to §8)
1. `make up`, then `make check` is green, **including the Playwright e2e suite** (`e2e/`). It covers, in a real browser: log in, list, view, add, edit and remove for every module of the phase, and for price lists, importing both files in `samples/`.
2. If something doesn't work, fix it before moving on. Never ship it as a "known issue".
3. Report the phase with a **5-minute manual test checklist** (what to click, what you should see) for the user to confirm.

### Rules
- **Do not add fields, menus or features that are not in this CLAUDE.md.** If something seems missing, ask the user first. Technical necessities (keys, audit columns, version, indexes) are fine; anything a user would see or type is not, unless it's specified here.
- **Never run `git commit`, `git push`, or any other git command that changes history or the remote** (amend, rebase, reset, merge, tag, stash drop, …). The user makes all commits. Read-only git (`status`, `diff`, `log`, `ls-files`, `check-ignore`) is fine.
- Browser URL is always `http://localhost:8080` (never `127.0.0.1`); the OAuth redirect URI is `http://localhost:8080/auth/callback`.
- **Never write to the real `mdm` database from tests, scripts or ad-hoc commands** (no `psql` INSERT/UPDATE/DELETE against `mdm`). Experiments go to `mdm_test`/`mdm_e2e`. Guards: `api/tests/safety.py` (pytest), `scripts/reset_schema.py`, the API's e2e-mode check, and `e2e/global-setup.ts`.
- A gitleaks pre-commit hook (`.githooks/pre-commit`, enabled by `make hooks`/`make install`) must stay on.
- **Schema changes only via a new Alembic migration** that ends with `apply_grants()`. To give `mdm_app` DELETE on a table, add it to `APP_DELETE_TABLES`; never on `audit_log` or price list tables. Never edit an applied migration.
- All tables live in schema `mdm`. UUID PKs (`gen_random_uuid()`) plus `audit_columns()`; lookups use natural code PKs.
- Money: `NUMERIC(18,4)` ↔ `Decimal`. A float never touches a money value (parse Excel cells straight to `Decimal(str(v))`).
- Host-side DB URLs use `127.0.0.1`, not `localhost` (on Windows, localhost tries IPv6 first and hangs).
- The API connects only as `mdm_app`; only Alembic/`migrate` sees `mdm_migrator`. The `api` Compose service gets an explicit env list, never the whole `.env`.
- Errors to the client are generic. Details go to logs, which must never contain tokens or cookies.
- Python: ruff (line length 100), mypy strict, type hints everywhere, sync SQLAlchemy 2.x style (`select()`), Pydantic v2 schemas with length limits on every string.
- TypeScript: strict, eslint `strictTypeChecked`. No `localStorage`/`sessionStorage`, no `dangerouslySetInnerHTML`, no inline scripts/styles (the CSP forbids them).
- Every security rule gets a test (role matrix → 403, DB privileges, headers).
- On Windows, run Python tools as `uv run python -m <tool>` if App Control blocks a `.exe` launcher (as it does for bandit).
- `samples/` holds real customer files: test fixtures only, never committed.
