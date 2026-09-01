# EmbedLead

A multi-tenant embeddable widget and lead-capture platform built with FastAPI, PostgreSQL, Redis, and Docker Compose.

EmbedLead lets a tenant configure a lead-capture widget, install a versioned JavaScript bundle on another origin, accept untrusted browser submissions, enrich leads with best-effort geolocation, persist them transactionally, and deliver notifications asynchronously.

> Status: capstone core complete and verified end to end. The remaining items are optional deployment and operational hardening; they are listed under [Limitations](#limitations).

## Delivered capabilities

- Authenticated, tenant-scoped widget CRUD with cursor pagination.
- Signed, expiring JWT access tokens backed by Argon2 password hashes and tenant memberships.
- Per-IP login throttling to bound credential guessing and Argon2 CPU abuse.
- Public, versioned widget bundle and cacheable widget configuration.
- Content-hash ETags and `304 Not Modified` configuration revalidation.
- Cross-origin submission API with CORS preflight handling and an 8 KiB body limit.
- Per-IP and per-widget moving-window submission limits with `Retry-After` responses.
- Honeypot spam control with silent drop semantics.
- Ordered `ip-api` → `ipapi.co` geolocation fallback with bounded provider timeouts.
- Transactional outbox: the lead and notification intent commit together.
- Supervised notification worker with bounded attempts, idempotency, and dead-letter state.
- Tenant-scoped dashboard submission listing and aggregate statistics.
- JSON request logs, request-id propagation, sensitive-field redaction, and token-protected Prometheus exposition.
- PostgreSQL migrations, deterministic seed data, a second-origin demo page, and a self-verifying rehearsal script.

## Architecture

The application is a modular monolith. HTTP concerns, application orchestration, tenant-scoped persistence, and infrastructure adapters have separate ownership.

```text
Widget owner
    │ JWT + membership
    ▼
FastAPI owner API ───────────────┐
    │                            │
    ▼                            ▼
Tenant-scoped services       PostgreSQL
    │                            ▲
    └──────── repositories ──────┘

Customer website                         Website visitor
    │                                     │
    ▼                                     ▼
Versioned widget bundle              Public submission API
    │                                     │
    ▼                                     ▼
Cached public config                validation → abuse controls
                                          │
                              geo A → geo B → no geo
                                          │
                                          ▼
                              PostgreSQL + transactional outbox
                                                        │
                                                        ▼
                                         supervised notification worker
```

### Request paths

1. **Owner administration** — the token subject identifies a user; the membership repository resolves tenant authority; every widget and dashboard query is tenant-scoped.
2. **Public delivery** — the versioned bundle and minimal widget configuration are public; private tenant and ownership fields do not cross this boundary.
3. **Public submission** — CORS is a browser policy only. Server-side validation, body limits, rate limits, spam control, persistence, and failure semantics protect the endpoint independently of the caller's origin.

### Component ownership

| Concern | Implementation |
|---|---|
| HTTP routes and response mapping | `app/api/routes/` |
| Request identity and dependency wiring | `app/api/*_dependencies.py` |
| Authentication and token verification | `app/core/auth.py` |
| Typed settings and environment contract | `app/core/config.py` |
| Tenant-scoped persistence | `app/repositories/` |
| Domain and infrastructure policy | `app/core/`, `app/services/` |
| PostgreSQL schema evolution | `app/alembic/versions/` |
| Notification dispatch | `app/services/outbox_worker.py`, `app/worker.py` |
| Browser bundle and demo page | `app/static/widget-v2.js`, `demo/index.html` |

## Runtime

### Requirements

- Docker Desktop with Docker Compose.
- Python 3.14 and `uv` for local quality gates.

No cloud account, paid service, real CDN, or external hosting is required.

### Start the stack

```bash
docker compose up --build --wait
```

The stack contains four services: `db`, `redis`, `backend`, and the supervised `worker`. Compose healthchecks wait for PostgreSQL availability and backend process liveness. Readiness is the traffic-gating check and additionally verifies the database dependency.

Seed deterministic demo data:

```bash
docker compose exec backend python -m app.seed
```

The seed command provisions the demo tenant, membership, owner, and widgets. Account registration, email verification, password recovery, and tenant onboarding are outside this capstone's public API.

Demo credentials printed by the seed command are for local development only. Do not reuse them outside the local stack.

OpenAPI and operational endpoints:

- Swagger UI: `http://localhost:8000/docs`
- OpenAPI JSON: `http://localhost:8000/api/v1/openapi.json`
- Liveness: `http://localhost:8000/api/v1/system/health/live`
- Readiness: `http://localhost:8000/api/v1/system/health/ready`
- Metrics: `http://localhost:8000/api/v1/system/metrics`

Stop the stack while preserving PostgreSQL data:

```bash
docker compose down
```

Delete the local database volume only when intentionally resetting the environment:

```bash
docker compose down --volumes
```

### Local verification

```bash
uv sync --python 3.14 --group dev
uv run pytest
uv run ruff check app tests
uv run mypy app tests
docker compose config --quiet
```

The repository also provides a complete acceptance rehearsal:

```bash
docker compose down --volumes
uv run python scripts/rehearsal.py
```

The rehearsal resets the volume, replays migrations, seeds the stack, exercises the authenticated and public paths, simulates Redis and geo-provider failures, verifies the outbox worker, restarts the backend, and checks persistence. It runs 21 steps with 60 assertions and is intended to produce a terminal transcript for `EVIDENCE.md`; it is not a video requirement.

## API contract

All routes use the `/api/v1` prefix. Exact schemas are available through OpenAPI at `/docs`.

### Authentication

`POST /api/v1/auth/token`

Issues a short-lived bearer token for a seeded user with an active tenant membership.

```json
{
  "email": "owner@acme.example",
  "password": "<local-password>"
}
```

The endpoint returns `401` for both unknown credentials and wrong passwords, `403` for a user without tenant membership, and `429` after the per-IP login budget is exhausted. The dummy Argon2 hash in `app/api/routes/auth.py` keeps the unknown-user path comparable to the known-user path and reduces account-enumeration through timing.

There is intentionally no public registration endpoint. User and tenant provisioning is performed by the seed path for this capstone.

### Owner API

All owner routes require `Authorization: Bearer <token>` and derive tenant authority from the authenticated membership. The request body cannot select `tenant_id`.

| Method | Path | Success | Purpose |
|---|---|---:|---|
| `POST` | `/api/v1/widgets` | `201` | Create a widget in the caller's tenant |
| `GET` | `/api/v1/widgets` | `200` | Cursor-paginated widget list |
| `GET` | `/api/v1/widgets/{widget_id}` | `200` | Read a tenant widget |
| `PATCH` | `/api/v1/widgets/{widget_id}` | `200` | Partially update a tenant widget |
| `DELETE` | `/api/v1/widgets/{widget_id}` | `204` | Delete a tenant widget |
| `GET` | `/api/v1/widgets/{widget_id}/embed` | `200` | Generate the embed script snippet |
| `GET` | `/api/v1/dashboard/submissions` | `200` | Cursor-paginated tenant submissions |
| `GET` | `/api/v1/dashboard/stats` | `200` | Time, widget, and geographic aggregates |

Cross-tenant object access returns `404` rather than revealing that the object exists.

### Public widget delivery

| Method | Path | Success | Purpose |
|---|---|---:|---|
| `GET` | `/api/v1/public/widgets/bundle/v2/widget.js` | `200` | Immutable versioned widget bundle |
| `GET` | `/api/v1/public/widgets/{widget_id}/config` | `200` / `304` | Minimal cacheable widget configuration |

The bundle is served with long-lived immutable caching. Configuration uses a short-lived cache policy and an ETag derived from the response content.

### Public submission

`POST /api/v1/public/widgets/{widget_id}/submissions`

The endpoint accepts cross-origin JSON submissions and returns `202` after the submission and outbox intent are durably committed.

```json
{
  "email": "visitor@example.com",
  "name": "Visitor",
  "message": "Hello",
  "website": ""
}
```

| Condition | Response |
|---|---|
| Valid submission | `202 {"status":"accepted"}` |
| Malformed JSON or invalid fields | `422` JSON error |
| Body over `MAX_SUBMISSION_BYTES` | `413` JSON error |
| Unknown widget | `404` |
| Submission rate exceeded | `429` with `Retry-After` |
| Filled honeypot | Ordinary `202`; no submission row is created |
| Allowed CORS preflight | `200` with CORS headers |
| Disallowed CORS preflight | No allow-origin grant |

`tenant_id` is taken from the stored widget, not the request body. Unknown fields are rejected. The response does not expose an internal submission identifier.

CORS controls browser access to the response; it is not endpoint authorization. Direct non-browser callers are controlled by server-side validation and abuse protection.

### Health and metrics

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/system/health/live` | Process liveness; independent of PostgreSQL |
| `GET` | `/api/v1/system/health/ready` | Database readiness plus dependency details |
| `GET` | `/api/v1/system/metrics` | Token-protected Prometheus text exposition |

Readiness returns `200` for a usable database. Redis may be reported as `degraded` without failing aggregate readiness because the application has an in-process limiter fallback. The liveness healthcheck is used by Compose so a dependency outage does not restart a healthy process.

Metrics expose request counters, latency histograms, and named event counters. The endpoint requires `X-Metrics-Token`; it returns `404` when no metrics token is configured and `401` for a missing or invalid token. Route, method, and status labels are bounded to prevent uncontrolled cardinality.

## Reliability and security invariants

- Tenant authority is resolved from authenticated membership, never trusted from client input.
- SQLAlchemy queries include tenant scope at the repository boundary.
- JWT signature, algorithm, expiry, and subject are validated server-side.
- Unknown-user authentication still performs Argon2 work through `DUMMY_PASSWORD_HASH`.
- Login and public submissions have separate per-IP budgets.
- Redis-backed limiter state is shared across backend replicas when configured.
- Redis failure degrades to a bounded local limiter; leads are not rejected solely because the optional limiter store is unavailable.
- PostgreSQL is the durable source of truth and outbox queue; Redis holds disposable rate-limit state only.
- A submission and its notification intent commit in one database transaction.
- Notification delivery is outside the request path and cannot roll back a stored lead.
- Webhook delivery is at-least-once and keyed by an idempotency key.
- Geo enrichment is advisory; provider failure results in a stored row with nullable location.
- User-controlled widget text is rendered with DOM text APIs rather than `innerHTML`.
- Error responses expose stable categories, not SQL, connection strings, credentials, or provider details.
- Logs use request IDs for correlation and redact password, secret, token, authorization, signature, and API-key fields.

## Notification delivery

The worker consumes transactional outbox rows and supports a logging transport by default. Set `NOTIFICATION_WEBHOOK_URL` to use the webhook transport and `NOTIFICATION_WEBHOOK_SECRET` to sign the idempotency key with HMAC-SHA256.

The worker runs automatically as the Compose `worker` service:

```bash
docker compose logs -f worker
```

For a one-shot manual drain:

```bash
docker compose exec worker python -m app.worker --once
```

Delivery outcomes are `sent`, retryable `pending`, or terminal `failed` after `OUTBOX_MAX_ATTEMPTS`. Failed messages retain the last error and trigger the failure-alerter seam. Consumers must deduplicate using the idempotency key.

## Limitations

These are explicit operating boundaries, not missing core requirements.

- **No public account provisioning.** The capstone uses deterministic seed data. Registration, verification, recovery, and tenant onboarding require a separate product and security design.
- **Webhook delivery is minimal.** The worker has a fixed attempt budget and no exponential backoff or automatic dead-letter replay. There is no SMTP transport.
- **No distributed tracing.** Request IDs correlate logs within this service; there is no span tree or W3C `traceparent` propagation.
- **Metrics are per process and pull-only.** No Prometheus server, scrape configuration, recording rules, alert rules, or Grafana dashboard is shipped. Counters reset on restart. The Compose topology runs one Uvicorn worker per backend container; multiprocess Prometheus mode is not enabled.
- **Redis is disposable.** Persistence is disabled intentionally because limiter/task state is not durable business data. During Redis failure, the fallback limiter is per process again.
- **Origin allow-listing is browser-level only.** CORS prevents an unlisted browser origin from receiving a readable response; it does not stop direct HTTP clients. Per-widget origin authorization is not implemented.
- **PostgreSQL migrations run from the backend image command.** This is suitable for the documented single-backend Compose topology. A multi-replica deployment should run migrations as a separate deployment step.
- **Index evidence is workload-specific.** The dashboard time-series index was verified at 50,000 rows; the widget lookup index is not claimed as an optimization at demo-scale data volumes.
- **Deployment is local-only.** Compose credentials and the metrics token are development placeholders. TLS termination, cloud deployment, backups, log shipping, and CI are not configured.

## Repository layout

```text
app/
├── api/routes/              HTTP adapters and route contracts
├── core/                    settings, auth, persistence policy, metrics, limits
├── repositories/            tenant-scoped persistence implementations
├── services/                health and outbox application services
├── alembic/versions/        PostgreSQL schema migrations
└── static/widget-v2.js      versioned browser bundle

demo/index.html               second-origin integration page
tests/                        unit, API, security, resilience, and contract tests
scripts/rehearsal.py          self-verifying 21-step demo rehearsal
compose.yaml                  db, redis, backend, and worker topology
capstone.yaml                 evaluator commands and endpoint manifest
EVIDENCE.md                   pasted proof for Definition-of-Done requirements
BUILDLOG.md                   engineering decisions, tool usage, mistakes, and corrections
docs/DESIGN.md                architecture contract and explicit non-goals
```

## Verification evidence

Latest repository gates:

```text
pytest: 267 passed
Ruff: all checks passed
mypy: no issues found in 101 source files
Definition-of-Done live sweep: 26/26 checks passed
Adversarial sweep: 17/17 probes safe
Demo rehearsal: 60/60 assertions passed across 21 steps
Harness: HARNESS VERIFIED
```

The detailed command transcripts are in [`EVIDENCE.md`](EVIDENCE.md). Engineering decisions, corrections, and tool usage are recorded in [`BUILDLOG.md`](BUILDLOG.md).

## Project documents

- [`capstone.yaml`](capstone.yaml) — evaluator run, seed, test, endpoint, and demo commands.
- [`docs/DESIGN.md`](docs/DESIGN.md) — architecture, trust boundaries, data model, contracts, and non-goals.
- [`EVIDENCE.md`](EVIDENCE.md) — reproducible proof and acceptance transcripts.
- [`BUILDLOG.md`](BUILDLOG.md) — decisions, corrections, and tool usage.
