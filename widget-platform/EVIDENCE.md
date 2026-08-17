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

## Widget management

- [ ] Authenticated widget CRUD — PENDING
- [ ] Unauthenticated requests rejected — PENDING
- [ ] Tenant A cannot read or modify tenant B resources — PENDING
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
