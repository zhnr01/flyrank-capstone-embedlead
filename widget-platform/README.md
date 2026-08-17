# EmbedLead Widget Platform

Production-minded backend capstone for creating embeddable lead-capture widgets, accepting hostile public submissions safely, and exposing tenant-isolated owner analytics.

Status: Phase 1 — first infrastructure tracer complete. The API and real PostgreSQL container now expose distinct liveness and readiness contracts. Product features remain gated by their API contract, data ownership, failure behavior, and first failing test.

## Run the verified tracer

```bash
uv sync --python 3.14 --group dev
uv run pytest
uv run ruff check app tests
uv run mypy app tests
docker compose up --build
```

Then open:

- API docs: `http://localhost:8000/docs`
- Liveness: `http://localhost:8000/api/v1/system/health/live`
- Readiness: `http://localhost:8000/api/v1/system/health/ready`

Stop with `docker compose down`.

## Product promise

A widget owner creates a widget and receives one script tag. A visitor can load and submit that widget from another origin. The platform validates, protects, enriches, stores, and reports the lead even when non-critical dependencies fail.

## Request paths

```text
OWNER (trusted only after authentication)
  -> widget management API
  -> service authorization
  -> tenant-scoped repository
  -> PostgreSQL

CUSTOMER WEBSITE (untrusted public browser)
  -> versioned widget script
  -> public cached configuration
  -> safe DOM rendering

VISITOR (untrusted internet input)
  -> CORS + payload boundary
  -> rate limit + spam check
  -> geo provider A -> provider B -> no geo
  -> PostgreSQL commit
  -> durable non-critical notification
```

## Engineering contract

- Contract-first APIs with typed requests and responses.
- Tenant scope is derived from authenticated identity, never accepted from an owner request body.
- Public submissions are validated and size-bounded before business logic.
- PostgreSQL is the source of truth; Redis is disposable infrastructure.
- Non-critical geo and notification failures cannot undo an accepted submission.
- Every feature starts with one failing behavioral test.
- Security, lint, types, tests, and independent review gate meaningful commits.
- No speculative services, abstractions, or stretch features before the core probes pass.

## Planned local stack

- Python 3.14 and FastAPI
- SQLModel, PostgreSQL, and Alembic
- Redis for distributed rate-limit counters
- Celery only for durable notification work
- Docker Compose as the authoritative runtime
- Pytest, Ruff, and mypy for quality gates

## Documentation

- `docs/DESIGN.md` — actors, trust boundaries, data model, API contracts, failures, and non-goals
- `docs/learning/01-three-request-paths.md` — the first capstone-specific lesson
- `EVIDENCE.md` — real proof for each Definition-of-Done item
- `BUILDLOG.md` — honest engineering and AI-assistance log
- `capstone.yaml` — evaluator command manifest, finalized when commands exist

## Current non-goals

WebSockets, targeting rules, CAPTCHA, GDPR export/delete, Kubernetes, sharding, read replicas, and a full visual form builder. They remain out until the mandatory acceptance probes pass.
