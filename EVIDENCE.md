# Evidence

Claims without reproducible evidence count as not done. Replace each `PENDING` entry with the exact test name, command, output excerpt, or HTTP transcript produced while building.

## Infrastructure tracer

- [x] Python 3.14 application image builds from the committed `uv.lock`.
- [x] Liveness proves the process can answer without dependency calls and exposes `status` as the single OpenAPI literal `"healthy"`.
- [x] Readiness executes a time-bounded `SELECT 1` against real PostgreSQL 18.
- [x] Pool checkout, database connection, and SQL statement waits are each bounded to 2 seconds.
- [x] Backend and PostgreSQL containers become healthy under Compose.
- [x] Backend container runs as an unprivileged `app` user.

Proof captured 2026-08-17:

```text
$ uv run pytest
6 passed

$ uv run ruff check app tests
All checks passed!

$ uv run mypy app tests
Success: no issues found in 11 source files

$ curl http://localhost:8000/api/v1/system/health/live
{"status":"healthy"}

$ curl http://localhost:8000/api/v1/system/health/ready
{"status":"healthy","checks":{"database":{"status":"healthy","response_time_ms":164.72,"error":null}}}

$ docker compose ps
widget-platform-backend-1  Up (healthy)
widget-platform-db-1       Up (healthy)
```

## Tenant/widget tracer

- [x] Local demo bearer credentials resolve to server-owned identities; callers cannot encode tenant authority in the credential.
- [x] Authenticated owner can create and read a widget.
- [x] Widget rows persist in PostgreSQL through SQLAlchemy and the `0001_widgets` Alembic migration.
- [x] A second tenant receives 404 when requesting the first tenant's widget.
- [x] Container startup applies `alembic upgrade head` before Uvicorn serves HTTP, including from a freshly recreated empty PostgreSQL volume.

Proof captured after the tenant/widget implementation:

```text
uv run pytest: 11 passed
uv run ruff check app tests: All checks passed!
uv run mypy app tests: Success: no issues found in 23 source files
alembic current: 0001_widgets (head)
PostgreSQL tables: alembic_version, widgets
owner-alpha POST /api/v1/widgets: 201
owner-alpha GET /api/v1/widgets/1: 200
owner-beta GET /api/v1/widgets/1: 404 {"detail":"Widget not found"}
```

The identity registry remains a local test seam rather than production membership. Signed token creation and verification are now implemented; persistent users, login, and membership tables remain pending.

## Authentication foundation

- [x] Argon2 hashes verify the original password, reject a different password, and do not equal the original password.
- [x] Signed access tokens require subject and expiry claims and an explicit HS256 algorithm allowlist.
- [x] Tampered and expired tokens are rejected.
- [x] Protected widget routes accept signed token subjects and reject the earlier unsigned demo credential format.
- [x] Runtime proof: a signed token created a widget with HTTP 201; the old unsigned demo credential returned HTTP 401; the token was not printed.
- [x] Full suite: 20 tests passed; Ruff and strict mypy passed.
- [x] Persistent membership runtime proof: signed user without membership returned 403; after server-side membership fixtures were inserted, the same user created a widget with 201; another member received 404 for that widget.
- [x] Migration head at runtime: `0002_memberships`; backend remained healthy as uid=999(app).
- [x] Persistent users, tenants, and membership authority schema
- [x] Server-side membership lookup for signed token subjects
- [x] Login token endpoint: valid credential 200, generic unknown/wrong-password 401, no-membership 403
- [x] Runtime login proof: normalized valid credentials returned a bearer token with HTTP 200; wrong password and unknown email returned identical HTTP 401 bodies; the token created a protected widget with HTTP 201; credentials were not printed.
- [x] Full suite: 24 tests passed; Ruff and strict mypy passed.
- [ ] Registration, password reset, refresh/session lifecycle — PENDING

## Widget management

- [x] Authenticated widget create/read tracer
- [x] Unauthenticated requests rejected
- [x] Tenant A cannot read tenant B resources
- [ ] Real user login, signed tokens, and persistent memberships — PENDING
- [ ] Widget update/delete/list — PENDING
- [ ] Embed snippet generated per widget — PENDING

## Widget delivery

- [ ] Public config has correct cache headers — PENDING
- [ ] Versioned widget bundle URL changes on release — PENDING
- [ ] Widget renders from a second origin — PENDING

## Public submission API

- [ ] CORS preflight succeeds for an allowed origin — PENDING
- [ ] Disallowed origin is not granted browser access — PENDING
- [ ] Malformed and oversized payloads return clean 4xx JSON — PENDING
- [ ] Valid submission is linked to the correct widget and tenant — PENDING

## Abuse protection

- [ ] Burst produces 429 while normal service remains available — PENDING
- [ ] Honeypot submission is blocked without storage — PENDING

## Enrichment and side effects

- [ ] Provider A fails and provider B enriches — PENDING
- [ ] Both providers fail and submission still commits — PENDING
- [ ] Notification fails and submission still commits — PENDING
- [ ] Retried notification does not duplicate the durable intent — PENDING

## Dashboard and documentation

- [ ] Tenant-scoped submission list and analytics — PENDING
- [ ] Full automated suite passes — PENDING
- [ ] Clean-machine Compose startup works — PENDING
- [ ] Seed command creates deterministic demo data — PENDING
