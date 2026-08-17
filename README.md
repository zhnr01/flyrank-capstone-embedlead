# EmbedLead Widget Platform

A backend capstone for serving embeddable lead-capture widgets and safely accepting submissions from websites the platform does not control.

> Project status: foundation in progress. The health and startup tracer is implemented and verified. Widget management, public submission, abuse protection, enrichment, delivery, and dashboard features are planned but not yet implemented.

## Implemented now

- FastAPI application running on Python 3.14.
- Separate liveness and readiness endpoints.
- PostgreSQL readiness probe using `SELECT 1`.
- Bounded database pool checkout, connection establishment, and statement execution.
- Typed health responses and an OpenAPI contract for the liveness state.
- PostgreSQL 18 and the API running through Docker Compose.
- Backend container running as an unprivileged user.
- Automated API and failure-path tests, Ruff linting, and strict mypy checks.

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

Only the process and database health path is implemented today. The remaining paths are documented design targets, not completed features.

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

1. Tenant model, local authentication, and tenant-isolated widget CRUD.
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
