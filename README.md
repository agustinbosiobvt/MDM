# BVT MDM

Master Data Management for Buena Vida Trading: company, customers, vendors and price lists.
Version 1 runs locally, with standard Postgres and Docker only, so it can move to GCP, AWS or Azure without a rewrite.

The design is in [`docs/plan.md`](docs/plan.md) and the working conventions are in [`CLAUDE.md`](CLAUDE.md#conventions).

| Phase | Status |
| --- | --- |
| 1 Plan | done |
| 2 Skeleton | done |
| 3 Auth | done |
| 4 Company | done |
| 5 Customers + Vendors | done |
| 6 Price lists + import | done |
| 7 Hardening | done |

## Requirements

- Docker Desktop
- [uv](https://docs.astral.sh/uv/) (it installs Python 3.12 itself)
- Node 22+
- GNU make (on Windows, run it from Git Bash)

## First-time setup

```bash
cp .env.example .env
make secrets            # paste the printed values into .env (and into the two *DATABASE_URL lines)
make install            # uv sync, npm ci (web + e2e), Playwright Chromium, git hooks
make db-up              # Postgres 16 on 127.0.0.1:54330; first start creates roles + databases
make migrate            # schema mdm, lookups, seeds
# Google sign-in: follow "Google OAuth client" below, then fill GOOGLE_CLIENT_ID,
# GOOGLE_CLIENT_SECRET and BOOTSTRAP_ADMIN_EMAIL (your own address) in .env
make up                 # build + run everything → http://localhost:8080
make check              # lint, typecheck, unit/API tests, security scans, Playwright e2e
```

## Google OAuth client (one-time)

The consent screen is **Internal**: only accounts in the buenavidatrading.com Google Workspace can even reach the consent step. The API also checks `hd` and the allow-list on every login.

1. Go to <https://console.cloud.google.com/> and sign in with a **buenavidatrading.com** admin account.
2. Pick or create a project **inside the buenavidatrading.com organization** (project picker → *New project* → Organization: `buenavidatrading.com`), e.g. `bvt-mdm`. "Internal" is only offered for projects that belong to the Workspace organization.
3. Open **Google Auth Platform** (or *APIs & Services → OAuth consent screen*) and click **Get started**:
   - App name: `BVT MDM`. User support email: your address.
   - **Audience: Internal.**
   - Contact information: your address. Accept the policy, then **Create**.
4. **Data access:** no extra scopes are needed. The app only requests `openid`, `email` and `profile`, which are non-sensitive defaults.
5. **Clients → Create client:**
   - Application type: **Web application**. Name: `BVT MDM local`.
   - Authorized JavaScript origins: leave empty (the whole flow runs server-side).
   - **Authorized redirect URIs:** `http://localhost:8080/auth/callback` (exactly this; Google allows `http` for `localhost`).
   - **Create**, then copy the **Client ID** and **Client secret**. Newer consoles show the secret only once, so download the JSON if offered and keep it outside the repo.
6. In `.env`, set:
   ```
   GOOGLE_CLIENT_ID=<client id>.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=<client secret>
   BOOTSTRAP_ADMIN_EMAIL=<you>@buenavidatrading.com
   ```
7. Run `make up`, open **http://localhost:8080** and click **Sign in with Google**. You'll arrive as Admin; add colleagues under **Users**.

For production, add a second redirect URI with the real HTTPS host (e.g. `https://mdm.buenavidatrading.com/auth/callback`) and set `OIDC_REDIRECT_URI` and `WEB_ORIGIN` to match.

## Running

```bash
make up                 # builds images, runs migrations, starts api + web
make down               # stops everything (data volume kept)
```

Open **http://localhost:8080**. Always use `localhost`, not `127.0.0.1`: the session cookie and the OAuth redirect are bound to that exact origin. nginx in the `web` container serves the UI and proxies `/api` and `/auth` to the API, which has no host port of its own.

## Tests

| Command | What runs |
| --- | --- |
| `make test` | pytest against the `mdm_test` DB (schema rebuilt each run). Google is replaced by an in-process fake IdP (`api/tests/fake_idp.py`) plugged into the **real** OIDC client, so signature, claim, PKCE, state and session checks all run for real. |
| `make e2e` | Playwright, headless Chromium, against the real Docker stack at http://localhost:8080. A mock Google (`e2e/mock_oidc/`, Compose overlay `docker-compose.e2e.yml`) stands in for accounts.google.com, and the API uses a separate `mdm_e2e` database that is reset each run. Afterwards the normal stack is restored. Report: `e2e/playwright-report/`. |
| `make check` | lint, typecheck, test, audit, e2e: the definition of done for every phase |

## Services

| Service | Image | Port (host, loopback only) | Notes |
| --- | --- | --- | --- |
| `db` | postgres:16 | 54330 | profile `db`, volume `mdm_pg_data` |
| `migrate` | api image | – | profile `tools`, one-shot `alembic upgrade head` as `mdm_migrator` |
| `api` | python:3.12-slim | none (internal only) | non-root, read-only FS, all capabilities dropped |
| `web` | nginx-unprivileged | 8080 | **the only browser origin**: serves the SPA and proxies `/api` and `/auth` |
| `mock-oidc` | api image | 8090 | **e2e only** (`docker-compose.e2e.yml`): fake Google for Playwright |

## Database roles

| Role | Used by | Rights |
| --- | --- | --- |
| `mdm_migrator` | Alembic only | owns schema `mdm` (DDL) |
| `mdm_app` | the API | SELECT/INSERT/UPDATE on business tables, **INSERT only** on `audit_log`, no DDL, no DELETE unless listed in `APP_DELETE_TABLES` |
| `mdm_readonly` | future reporting | SELECT, read-only transactions |

The roles and databases are created by [`db/bootstrap.sql`](db/bootstrap.sql). Grants are re-applied by every migration from one policy (`api/alembic/alembic_helpers.py`), and `api/tests/test_db_roles.py` proves the policy holds.

## Security checklist

Every point of the security spec (CLAUDE.md §7) and how it is covered. Phase 7 re-checked all of them against the code and the running stack, ran every scan (`make audit`: pip-audit, bandit, npm audit for web and e2e, gitleaks over the tree and history, built-image scan; all clean) and fixed the findings listed under [Phase 7 findings](#phase-7-findings).

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
| Google OIDC, Authorization Code + PKCE, server-side (BFF) | ✅ Phase 3 | `app/auth/oidc.py`: the API builds the S256 challenge, exchanges the code with the client secret (Authlib) and validates the ID token (joserfc): RS256 signature against Google's JWKS (cached, refetched on key rotation), `iss`, `aud`, `exp`, `iat`, `nonce`. The browser never receives a token. Tested: wrong key, `alg: none`, wrong aud/iss/nonce, expired, missing iat, PKCE mismatch. |
| Domain + allow-list | ✅ Phase 3 | requires `hd = buenavidatrading.com`, an email in that domain and `email_verified = true`, **and** an active `mdm.app_user` row. Refusals go to `/no-access` and are written to `audit_log` (`login_denied` + reason). Tested in pytest and in the browser. |
| Login state / login CSRF | ✅ Phase 3 | `state` is single-use and expires after 10 min, stored server-side (hash), and bound to the starting browser by a `__Host-mdm_login` cookie, so a callback replayed in another browser is refused. |
| Sessions | ✅ Phase 3 | opaque 256-bit token in `__Host-mdm_session` (HttpOnly, Secure, SameSite=Lax, Path=/, no Domain). The DB stores only its SHA-256. Idle 30 min, absolute 8 h, new ID at every login, logout deletes it server-side, and deactivating a user ends their sessions. Tested, including replaying an old cookie. |
| First admin | ✅ Phase 3 | `BOOTSTRAP_ADMIN_EMAIL` is inserted at startup if missing; it never modifies an existing user |
| CSRF protection | ✅ Phase 3 | three layers: SameSite=Lax; an Origin/Referer check on every POST/PUT/PATCH/DELETE (`app/security/csrf.py`); and a double-submit token (`__Host-mdm_csrf` cookie → `X-CSRF-Token` header, compared with the session's hash). Tested per route. |
| Role checks on every endpoint | ✅ Phase 3 | every `/api` route depends on `RequireViewer/Editor/Admin`. `test_authz.py` fails if a route has none, and runs the full matrix (anonymous → 401, lower role → 403, allowed role → not 401/403). Roles are re-read from the DB on every request, so a role change applies immediately. |
| Optimistic locking | ✅ Phase 3 | `version` column, checked on every update; a stale write → 409 "Someone else changed this record". Tested in pytest and with two browsers. |
| Rate limiting (login, import) | ✅ Phase 3, 6, 7 | `/auth/login` and `/auth/callback`: 20/min per client IP (`AUTH_RATE_LIMIT`); upload / validate / commit of imports: 30/min (`IMPORT_RATE_LIMIT`). Both tested. The client IP can't be forged: nginx replaces any `X-Forwarded-For` the client sends with the real peer address (tested on the config, and checked against the running stack: 23 logins with 23 forged IPs → 429 from the 21st). |
| No tokens or cookies in logs | ✅ Phase 3, 7 | the app logs only reason codes, emails and IPs; session/CSRF values exist only as hashes. Access logs (nginx and uvicorn) drop the query string, so Google's one-time `code` and the login `state` from `/auth/callback` are never written; nginx logs no Referer or cookies, and its error log for the callback is limited to `crit`. `test_log_safety.py` runs a full login plus three rejected ones with every logger at DEBUG and asserts that no code, state, access token, ID token, session or CSRF value appears. |
| Mock Google can't leak out of e2e | ✅ Phase 4 | the API refuses to start if any OIDC setting differs from Google's unless `APP_ENV=e2e` (`app/config.py`; tested in-process and by starting a real API process). The mock and its settings live only in `docker-compose.e2e.yml`; `test_mock_isolation.py` checks the compose files, the Makefile and the image build inputs, and `make audit` scans the built images (`scripts/check_images.sh`). |
| Soft delete; hard delete Admin-only with confirmation | ✅ Phase 4 | Remove = `is_active = false` (Editor). Permanent delete (`DELETE /api/companies/{id}/permanent`) is Admin-only, only for an already-removed company, and requires the company code typed again; the audit log keeps the full deleted record. `mdm_app` has DELETE only on the tables listed in `APP_DELETE_TABLES`. |
| Duplicates blocked | ✅ Phase 4–5 | unique `party.code` across company/customers/vendors (inactive rows included); an active Amazon parent/child vendor-code pair belongs to one customer. Database constraints, with clear 409 messages. |
| Tests and scripts can't write to real data | ✅ Phase 5 (corrections) | pytest refuses to start unless `TEST_DATABASE_NAME` ends in `_test`/`_e2e` (`api/tests/safety.py`, checked before connecting); `scripts/reset_schema.py` refuses any other database; the API refuses `APP_ENV=e2e` unless its database ends in `_e2e`/`_test`; Playwright's global setup refuses to run unless sign-in goes to the e2e mock. All proven by `test_safety.py` (and the Playwright refusal was checked against the normal stack). |
| Input validation | ✅ Phase 4, 7 | Pydantic on every field (length limits, ISO 3166/4217 codes checked against the lookup tables, EORI/phone/email formats, unknown fields rejected), mirrored by Zod in the forms. Database CHECK constraints as the last line. `test_input_limits.py` walks the request side of the OpenAPI schema (bodies, query and path parameters, nested models) and fails if any accepted string has no length limit; the only exemption is the uploaded file itself, capped at 20 MB while streaming. |
| Upload checks | ✅ Phase 6 | `app/imports/storage.py`: only `.xlsx`/`.csv` (`.xlsm`/`.xls` refused with a clear message); max 20 MB enforced while streaming; content must match the extension (real workbook zip, no `vbaProject.bin`, unpacked-size cap against zip bombs; CSV without NUL bytes); declared MIME type checked; stored outside the web root as `<random>.upload` with mode 0600, the client's file name is never used as a path; deleted after commit, cancel or expiry (4 h). Workbooks are read with openpyxl `read_only=True, data_only=True` (formulas never run). An import belongs to the user who started it (others get 404; Admin can see it). All tested. |
| Price list history | ✅ Phase 6, 7 | prices are never edited or overwritten (a re-import is a new version); `mdm_app` has no DELETE on any price list table (tested). A version can be deleted only while it is **Draft**, by an Editor or Admin, after a confirmation; that is a soft delete, written to the audit log, and refused with 409 for Active or Expired lists (tested, including the role matrix). |
| Excel formula-injection neutralisation | n/a in v1 | No Excel export exists. Imported text is stored and shown as text (React escapes it); add the `= + - @` prefix rule if an export is built. |

### Phase 7 findings

| # | Finding | Fix | Test |
| --- | --- | --- | --- |
| 1 | nginx's default access log wrote the full `/auth/callback?code=…&state=…` URL, so Google's one-time authorization code reached the logs (uvicorn's access log would have done the same). | Own nginx `log_format` with `$uri` (no query string, no Referer); a uvicorn access-log filter that strips the query string (`app/core/logsafety.py`); `crit`-only error log for the callback. | `test_log_safety.py`; checked live: no `code` value in either container's log. |
| 2 | nginx appended to a client-sent `X-Forwarded-For`, and uvicorn (trusting the proxy) takes the first entry, so a client could pick its own IP: a rate-limit bypass and a forged IP in the audit log. | nginx sets `X-Forwarded-For $remote_addr` (overwrites). | `test_nginx_overwrites_x_forwarded_for`; checked live (429 despite rotating forged IPs). |
| 3 | Some inputs were bounded only by a regex, not a declared length (codes, country/currency/Incoterm/payment-term codes, EORI, phone, vendor codes, import currencies and price types, OAuth callback parameters). | An explicit `max_length` on each, and constraints declared before the upper-casing step so the limit also appears in the schema. | `test_input_limits.py` |
| 4 | The `web` container kept nginx's default Linux capabilities. | `cap_drop: [ALL]` (the unprivileged image needs none). | `make up` + the e2e suite run on it |
| 5 | bandit printed "Test in comment" warnings because the reasons were written after `# nosec`. | Reasons moved to the line above. | `make audit` output is clean |

## Decisions to revisit before cloud deployment

| Decision (2026-10-16) | Why it is fine for now | Revisit |
| --- | --- | --- |
| Google consent screen is **Internal**, and the authorization request sends `hd=buenavidatrading.com` as a hint | Google itself blocks accounts outside the Workspace before they reach the app, and the API still enforces `hd`, `email_verified` and the allow-list on every login | Before cloud deployment: confirm the GCP project stays in the Workspace organization, add the production redirect URI, and decide whether outside collaborators (e.g. an accountant) ever need access. That would mean switching to External + test users, with the server-side checks unchanged. |

## Troubleshooting

- **DB connection hangs on Windows:** use `127.0.0.1` in the `*DATABASE_URL` lines, not `localhost`. Windows tries IPv6 `::1` first, and the container only listens on IPv4.
- **"An Application Control policy has blocked this file"** for a Python tool: run it as `uv run python -m <tool>`.
- **Port 8000 is busy:** that's expected, because the PL&CI app uses it. MDM uses 8080 only.
- **"Google sign-in isn't configured on this server yet":** set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `.env`, then `make up`.
- **Google says `redirect_uri_mismatch`:** the client must list exactly `http://localhost:8080/auth/callback`, and you must browse `http://localhost:8080` (not `127.0.0.1`).
- **"No access" with your own account:** check that `BOOTSTRAP_ADMIN_EMAIL` matches it exactly, then restart the API (`make up`). An existing row is never changed; fix it under Users or in the DB.

## Before going to the cloud

Nothing here needs a rewrite. These are configuration steps:

1. `APP_ENV=production`: hides the API docs and turns on HSTS in the API. Uncomment the `Strict-Transport-Security` line in `web/nginx.conf` once the site is served over HTTPS.
2. Set `WEB_ORIGIN` and `OIDC_REDIRECT_URI` to the HTTPS host, and add that redirect URI to the Google client.
3. Use a managed Postgres 16 with `sslmode=require` (or `verify-full`) in the URLs; the API and Alembic refuse a remote URL without it. Run `db/bootstrap.sql` once as the admin user to create the three roles.
4. If a cloud load balancer sits in front of nginx, `$remote_addr` becomes the load balancer. Then use nginx's `real_ip` module with the load balancer's address range as `set_real_ip_from`, so the client IP stays trustworthy (finding 2).
5. Put secrets (`GOOGLE_CLIENT_SECRET`, DB passwords) in the platform's secret manager instead of `.env`.

## Known limitations

- Rate limiting is in-process (slowapi): it's correct for one API instance only. Behind several instances, move it to the load balancer/WAF or a shared store.
- The Playwright suite signs in through a mock Google (headless browsers can't use real Google accounts). The real Google path is covered by the manual checklist for each phase.
- An abandoned import's temporary file (never committed or cancelled) is deleted when its job expires (4 h), but the sweep runs on the next upload, not on a timer. Until then the file sits in the `mdm_uploads` volume, readable only by the API user.
- A deleted draft keeps its revision number (the history can show Rev 1, Rev 3), and its rows stay in the database. So a customer/vendor that ever had a price list, even only deleted drafts, can't be deleted permanently (Remove still works).
- Login-state rows from abandoned sign-ins expire after 10 minutes and are cleaned up by the app on later logins.
