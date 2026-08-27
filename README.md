# EmbedLead Widget Platform

A backend capstone for serving embeddable lead-capture widgets and safely accepting submissions from websites the platform does not control.

> Project status: foundation in progress. The health/startup tracer and the first tenant-scoped widget create/read tracer are implemented and verified. Real login, public submission, abuse protection, enrichment, delivery, and dashboard features are not yet implemented.

## Implemented now

- FastAPI application running on Python 3.14.
- Separate liveness and readiness endpoints.
- PostgreSQL readiness probe using `SELECT 1`.
- Bounded database pool checkout, connection establishment, and statement execution.
- Typed health responses and an OpenAPI contract for the liveness state.
- PostgreSQL 18 and the API running through Docker Compose.
- Backend container running as an unprivileged user.
- Automated API and failure-path tests, Ruff linting, and strict mypy checks.
- Tenant-scoped widget create/read endpoints backed by a PostgreSQL migration.
- A signed-authentication foundation proving authorization behavior before a login endpoint exists.
- Argon2 password hashing and signed, expiring access-token verification.
- Persistent tenant, user, and membership authority tables.
- Login token endpoint with generic credential failures and membership gating.
- Complete tenant-scoped widget lifecycle: create, read, cursor-paginated list, partial update, delete.
- Public cross-origin submission endpoint with CORS preflight, boundary validation, and a payload size guard.

## Why this system exists

An embedded form runs in a browser on someone else's website. That changes the backend boundary: the browser origin is external, submissions are untrusted, traffic can be abusive, and optional providers can fail.

The finished platform will separate three request paths:

```text
Widget owner
  -> authenticated widget management
  -> tenant-scoped data

Customer website
  -> versioned public widget script
  -> cacheable public configuration

Website visitor
  -> cross-origin submission
  -> validation and abuse controls
  -> optional geo enrichment
  -> durable lead storage
  -> non-critical notification work
```

The process/database health path and the first tenant/widget ownership path are implemented today. The remaining paths are documented design targets, not completed features.

## Architecture

The current tracer keeps HTTP behavior, health decisions, and database infrastructure separate:

```text
HTTP request
    |
    v
FastAPI system route
    |
    v
health service
    |
    v
SQLAlchemy engine and connection pool
    |
    v
PostgreSQL 18
```

- `app/api/routes/system.py` owns paths, status codes, and response serialization.
- `app/services/health.py` owns dependency checks and readiness decisions.
- `app/core/db.py` owns the SQLAlchemy engine and database timeout configuration.
- `app/core/config.py` owns typed environment configuration.
- `app/api/routes/widgets.py` owns widget HTTP contracts and status mapping.
- `app/repositories/widgets.py` owns tenant-scoped widget persistence.
- `app/alembic/versions/0001_create_widgets.py` owns the first product schema migration.

See [`docs/DESIGN.md`](docs/DESIGN.md) for the complete planned architecture, trust boundaries, data model, API surface, and explicit non-goals.

## Requirements

- Docker Desktop with Docker Compose, or
- Python 3.14 and [`uv`](https://docs.astral.sh/uv/) for local checks.

No paid service or cloud account is required.

## Run with Docker

```bash
docker compose up --build --wait
```

The `--wait` flag returns only after PostgreSQL and the backend readiness check report healthy.

Open:

- API documentation: `http://localhost:8000/docs`
- Liveness: `http://localhost:8000/api/v1/system/health/live`
- Readiness: `http://localhost:8000/api/v1/system/health/ready`
- OpenAPI document: `http://localhost:8000/api/v1/openapi.json`

Stop the stack:

```bash
docker compose down
```

The PostgreSQL volume is preserved. Use `docker compose down --volumes` only when you intentionally want to delete local database data.

## Local quality checks

Install the locked development environment:

```bash
uv sync --python 3.14 --group dev
```

Run the verification gates:

```bash
uv run pytest
uv run ruff check app tests
uv run mypy app tests
docker compose config --quiet
```

Current verified result:

```text
pytest: 6 passed
Ruff: all checks passed
mypy: no issues found
Docker Compose: backend healthy, PostgreSQL healthy
```

The FastAPI test client currently emits a non-blocking upstream deprecation warning about `httpx`. It does not change the six passing test results.

## Current API

### `POST /api/v1/auth/token`

Exchanges a normalized email/password credential for a short-lived signed bearer token. Unknown email and wrong password return the same HTTP `401` response; a valid user without tenant membership receives HTTP `403`.

```json
{
  "email": "owner@example.test",
  "password": "<password>"
}
```

```json
{
  "access_token": "<signed-access-token>",
  "token_type": "bearer"
}
```

### `GET /api/v1/system/health/live`

Checks whether the application process can answer HTTP. It deliberately does not call PostgreSQL.

```json
{
  "status": "healthy"
}
```

### `GET /api/v1/system/health/ready`

Checks whether this instance can execute a minimal statement against PostgreSQL.

Healthy response: HTTP `200`

```json
{
  "status": "healthy",
  "checks": {
    "database": {
      "status": "healthy",
      "response_time_ms": 2.22,
      "error": null
    }
  }
}
```

Unavailable database: HTTP `503`

```json
{
  "status": "unhealthy",
  "checks": {
    "database": {
      "status": "unhealthy",
      "response_time_ms": 4.5,
      "error": "OperationalError"
    }
  }
}
```

The public response exposes an error category, not the raw database exception message, connection string, SQL text, or credentials.

### `POST /api/v1/widgets`

Callers obtain the token from `POST /api/v1/auth/token`. Tenant scope comes from the caller's persistent membership row.

```text
Authorization: Bearer <signed-access-token>
```

Request:

```json
{"name":"Contact form","kind":"contact"}
```

Response: HTTP `201`

```json
{"id":1,"name":"Contact form","kind":"contact"}
```

The server verifies token signature, algorithm, expiry, and subject before resolving tenant scope from a PostgreSQL membership row. The request body cannot choose `tenant_id`.

### `GET /api/v1/widgets/{id}`

The authenticated owner receives HTTP `200`. A different tenant receives HTTP `404` so the API does not reveal whether the foreign widget exists.

### `GET /api/v1/widgets`

Returns the caller's widgets, newest identifier first, using bounded cursor pagination.

```text
GET /api/v1/widgets?limit=20&after_id=125
```

```json
{"data":[{"id":124,"name":"Contact form","kind":"contact"}],"next_after_id":124}
```

`limit` accepts 1 to 100 and defaults to 20; larger values return HTTP `422`. `next_after_id` is `null` on the final page.

### `PATCH /api/v1/widgets/{id}`

Updates only the supplied fields.

```json
{"name":"Updated form"}
```

An empty object returns HTTP `422`. A widget owned by another tenant returns HTTP `404`.

### `DELETE /api/v1/widgets/{id}`

Returns HTTP `204` with no body for the owner, and HTTP `404` for a missing or foreign widget.

### `POST /api/v1/public/widgets/{widget_id}/submissions`

Public, unauthenticated, cross-origin. A website visitor submits the widget's form.

```json
{"email":"visitor@example.com","name":"Visitor","message":"Hello"}
```

Response: HTTP `202`

```json
{"status":"accepted"}
```

Behaviour:

| Case | Response |
|---|---|
| valid submission | `202 {"status":"accepted"}` |
| malformed field, bad email, or unknown field | `422` with JSON detail |
| declared body over `MAX_SUBMISSION_BYTES` | `413` with JSON detail |
| unknown widget | `404` |
| preflight from an allowed origin | `200` with `Access-Control-Allow-*` headers |
| preflight from a disallowed origin | `400`, no allow-origin header |

`tenant_id` is derived from the stored widget row; the payload cannot choose it, and unknown fields are rejected outright. The response deliberately contains no submission identifier so an anonymous caller learns nothing about internal state.

Allowed origins come from `BACKEND_CORS_ORIGINS`. CORS is a browser policy, not authorization: a disallowed origin is denied a *readable response*, not denied the action. Abuse control for non-browser callers is rate limiting and spam control, which are not yet implemented.

## Reliability and security decisions

- Liveness remains independent of external dependencies.
- Readiness checks the database required for real traffic.
- Pool checkout, PostgreSQL connection, and SQL execution each have a two-second bound at the layer that controls that wait.
- Synchronous SQLAlchemy work runs off the asyncio event-loop thread.
- PostgreSQL remains the durable source of truth.
- The backend image uses an unprivileged `app` user.
- Local secrets belong in ignored environment files; `.env.example` contains placeholders only.
- Docker installs from the committed `uv.lock` with a frozen dependency resolution.

Reproducible command output and pending acceptance criteria are tracked in [`EVIDENCE.md`](EVIDENCE.md). Engineering decisions and corrections are recorded in [`BUILDLOG.md`](BUILDLOG.md).

## Repository structure

```text
.
|-- app/
|   |-- api/routes/       # HTTP endpoints
|   |-- core/             # typed configuration and database infrastructure
|   `-- services/         # application health decisions
|-- tests/api/            # API and failure-path tests
|-- docs/DESIGN.md        # planned architecture and contracts
|-- alembic.ini           # migration runner configuration
|-- app/alembic/          # versioned product schema
|-- Dockerfile
|-- compose.yaml
|-- pyproject.toml
|-- uv.lock
|-- EVIDENCE.md
|-- BUILDLOG.md
`-- capstone.yaml
```

## Planned core work

The next vertical slices are:

1. Login/user lifecycle and complete tenant-isolated widget CRUD.
2. Public submission with validation and cross-origin behavior.
3. Payload limits, per-IP/per-widget rate limits, and honeypot spam control.
4. Geo-provider fallback with graceful degradation.
5. Durable notification intent and retryable background delivery.
6. Versioned widget script, cacheable public configuration, and a second-origin test page.
7. Tenant-scoped lead listing and aggregate dashboard queries.
8. Complete evaluator evidence and demo data.

Stretch features remain out of scope until the required acceptance probes pass.

## Limitations

- No widget, submission, authentication, tenant, worker, Redis, or dashboard implementation exists yet.
- No product database tables or Alembic migrations exist yet.
- The current Compose credentials are local-development placeholders, not production secrets.
- Cloud deployment, TLS, backups, monitoring, and CI are not configured yet.

## Public project documents

- [`docs/DESIGN.md`](docs/DESIGN.md): planned architecture and contracts.
- [`EVIDENCE.md`](EVIDENCE.md): implemented proofs and pending acceptance criteria.
- [`BUILDLOG.md`](BUILDLOG.md): development decisions, AI assistance, mistakes, and corrections.
- [`capstone.yaml`](capstone.yaml): evaluator command and endpoint manifest.
