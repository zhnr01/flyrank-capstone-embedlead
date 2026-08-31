# EmbedLead Widget Platform

A backend capstone for serving embeddable lead-capture widgets and safely accepting submissions from websites the platform does not control.

> Project status: the required capstone core is implemented and proven end to end — authentication, tenant-isolated widget CRUD, cached public delivery, cross-origin submissions, abuse protection, geo enrichment, transactional-outbox notifications, an owner dashboard, and request-scoped observability. Remaining work is deployment hardening, not missing features; see [Limitations](#limitations).

## System status

- FastAPI application running on Python 3.14.
- Separate liveness and readiness endpoints.
- PostgreSQL readiness probe using `SELECT 1`.
- Bounded database pool checkout, connection establishment, and statement execution.
- Typed health responses and an OpenAPI contract for the liveness state.
- PostgreSQL 18 and the API running through Docker Compose.
- Backend container running as an unprivileged user.
- Automated API and failure-path tests, Ruff linting, and strict mypy checks.
- Tenant-scoped widget create/read endpoints backed by a PostgreSQL migration.
- Signed authentication with Argon2 credentials, expiring JWTs, membership gating, and login abuse protection.
- Argon2 password hashing and signed, expiring access-token verification.
- Persistent tenant, user, and membership authority tables.
- Login token endpoint with generic credential failures and membership gating.
- Complete tenant-scoped widget lifecycle: create, read, cursor-paginated list, partial update, delete.
- Public cross-origin submission endpoint with CORS preflight, boundary validation, and a payload size guard.
- Abuse protection: per-IP and per-widget sliding-window rate limits with `Retry-After`, a separate per-IP budget on the login endpoint so credential guessing is bounded, plus a honeypot spam control.
- Advisory IP geo enrichment with an ordered provider fallback chain that degrades to a stored row with no location.
- Transactional outbox with a separate worker process: notifications are at-least-once, idempotent, and can never lose a lead.
- Cached widget delivery: content-hash ETag with `304` revalidation, an immutably versioned bundle, and a per-widget embed snippet.
- Owner dashboard: tenant-scoped submission list with cursor pagination plus aggregation stats.
- A second-origin demo page and a deterministic seed command, so the whole flow is reproducible in a browser.
- Operable observability: JSON logs with a propagated request id, redaction of sensitive fields, and a token-protected metrics endpoint with bounded label cardinality.

## System boundary

EmbedLead accepts untrusted browser traffic from tenant-controlled origins and persists tenant-scoped leads. The design separates authenticated owner operations, public cached delivery, and public submission processing. External geo and notification providers are non-critical dependencies.

The platform separates three request paths:

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

All three request paths are implemented and proven: authenticated widget management, public cached widget delivery, and protected cross-origin submission with persistence, enrichment, and asynchronous notification work.

## Architecture

The implementation keeps HTTP adapters, application services, domain policy, repositories, and infrastructure separate. The health path is representative:

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

See [`docs/DESIGN.md`](docs/DESIGN.md) for the architecture, trust boundaries, data model, API surface, implementation status, and explicit non-goals.

## Runtime requirements

- Docker Desktop with Docker Compose, or
- Python 3.14 and [`uv`](https://docs.astral.sh/uv/) for local checks.

No paid service or cloud account is required.

## Runbook

```bash
docker compose up --build --wait
```

`--wait` waits for the Compose healthchecks. PostgreSQL is checked with `pg_isready`; the backend healthcheck probes process liveness. Readiness is the traffic-gating endpoint and additionally checks database availability.

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

## Verification

Install the locked development environment and run the repository gates:

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

Latest verified result:

```text
pytest: 266 passed
Ruff: all checks passed
mypy: no issues found
Docker Compose: backend healthy, PostgreSQL healthy
```

The FastAPI test client currently emits a non-blocking upstream deprecation warning about `httpx`. It does not affect the verification result.

## API contract

### `POST /api/v1/auth/token`

Issues a short-lived signed bearer token for a seeded user with an active tenant membership. Email normalization is server-side. Unknown email and wrong password both return `401`; a valid user without membership returns `403`. The endpoint is independently rate-limited per source IP.

Account provisioning is intentionally outside this capstone's public API. The seed command creates the deterministic demo tenant, user, and membership; production registration, email verification, password recovery, and tenant onboarding are outside the documented scope.

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

### `GET /api/v1/system/metrics`

Operator-only RED signals for the running process: request counts by method, route template, and status class; latency histograms with p50/p95/p99; and named event counters for rate limiting, honeypot drops, geo outcomes, and outbox delivery.

Access is a shared operator token compared in constant time:

```text
X-Metrics-Token: <token>
```

The endpoint fails closed. With `METRICS_TOKEN` unset it returns `404`, so a deployment that forgets to configure it does not expose operational intelligence by default. A wrong or missing token returns `401`.

```text
# HELP embedlead_requests_total HTTP requests by method, route template and status class.
# TYPE embedlead_requests_total counter
embedlead_requests_total{method="GET",route="/api/v1/public/widgets/{widget_id}/config",status_class="2xx"} 1.0
embedlead_requests_total{method="POST",route="/api/v1/public/widgets/{widget_id}/submissions",status_class="2xx"} 1.0
# HELP embedlead_request_duration_seconds HTTP request duration in seconds by method and route template.
# TYPE embedlead_request_duration_seconds histogram
embedlead_request_duration_seconds_bucket{le="0.005",method="GET",route="/api/v1/system/health/ready"} 19.0
embedlead_request_duration_seconds_bucket{le="+Inf",method="GET",route="/api/v1/system/health/ready"} 131.0
embedlead_request_duration_seconds_count{method="GET",route="/api/v1/system/health/ready"} 131.0
embedlead_request_duration_seconds_sum{method="GET",route="/api/v1/system/health/ready"} 0.7947955816052854
# HELP embedlead_events_total Domain events by name and outcome.
# TYPE embedlead_events_total counter
embedlead_events_total{name="submission_stored",outcome="ok"} 1.0
```

Buckets are **cumulative**, as the exposition format requires: the `le="+Inf"` bucket equals
`_count`. Quantiles are not precomputed — Prometheus interpolates them at query time
(`histogram_quantile(0.95, sum by (le) (rate(embedlead_request_duration_seconds_bucket[5m])))`),
which is why a hand-rolled p95 read off a bucket boundary would be wrong.

Route labels are the **route template**, never the concrete path. `/widgets/91` and `/widgets/92` share one series, so an attacker cannot inflate memory by walking ids. Unmatched paths collapse into a single `unmatched` series for the same reason. Total series are capped by `METRICS_MAX_ROUTES`; past the cap, counts are folded into an `other` row and `cardinality.overflowed` reports it rather than silently dropping data.

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

Allowed origins come from `BACKEND_CORS_ORIGINS`. CORS is a browser policy, not authorization: a disallowed origin is denied a *readable response*, not denied the action. Abuse control for non-browser callers is the rate limiting and spam control described below.

#### Abuse protection on this endpoint

| Control | Behaviour |
|---|---|
| per-IP rate limit | `SUBMISSION_RATE_LIMIT_PER_IP` requests per window, keyed on the socket peer |
| per-widget rate limit | `SUBMISSION_RATE_LIMIT_PER_WIDGET` requests per window |
| per-IP login limit | `LOGIN_RATE_LIMIT_PER_IP` attempts per `LOGIN_RATE_LIMIT_WINDOW_SECONDS`, so credential guessing is bounded |
| over the limit | `429` with `Retry-After` in seconds; the body does not reveal which limit tripped |
| honeypot | a populated `website` field returns the ordinary `202` and stores nothing |

`X-Forwarded-For` is deliberately ignored, because a client-supplied header would let any caller mint a fresh limiter key. Running behind a reverse proxy therefore requires `--proxy-headers` plus an explicit trusted-proxy list before any forwarding header may be believed.

Limiter state lives in Redis when `REDIS_URL` is set, using `limits`' moving-window strategy, so every replica shares one budget instead of each getting its own. Without `REDIS_URL` the limiter falls back to an in-process window, which is correct for a single container and is also the fail-open path when Redis is unreachable — see [Limitations](#limitations).

#### Geo enrichment

Before storage the visitor's IP is resolved to a country and city through an ordered provider chain (`ip-api`, then `ipapi.co`). Enrichment is advisory:

| Situation | Outcome |
|---|---|
| first provider answers | row stores country, city, and the answering provider name |
| first fails or returns nothing usable | the next provider is tried |
| every provider fails | row is stored with `NULL` geo columns |
| unroutable address (loopback, private, documentation range) | no provider is called, geo stays `NULL` |

A failure anywhere in enrichment — including inside the chain itself — can never prevent a submission from being stored. The answering provider is recorded in `geo_provider`, so a fallback is verifiable in stored data rather than merely claimed. Each provider has a bounded timeout (`GEO_PROVIDER_TIMEOUT_SECONDS`), so worst-case added latency is that timeout times the number of providers.

There is no cache and no circuit breaker yet: a repeatedly failing provider is retried on every submission and pays its timeout each time.

#### Notification side effect

A submission must trigger a notification, but a mail or webhook failure must never lose a lead. The submission row and the delivery intent are written in one transaction:

```text
BEGIN
  INSERT INTO submissions ...
  INSERT INTO outbox_messages (status='pending', idempotency_key='submission:<id>:created')
COMMIT
```

A separate worker process delivers them:

```bash
docker compose exec backend python -m app.worker --once   # drain one batch
docker compose exec backend python -m app.worker          # poll continuously
```

| Situation | Outcome |
|---|---|
| delivery succeeds | `status='sent'`, attempts recorded |
| delivery fails | attempt counted, row stays `pending`, retried on the next poll |
| attempts exhausted (`OUTBOX_MAX_ATTEMPTS`) | `status='failed'` with `last_error`, a dead letter for inspection |
| duplicate enqueue of the same key | no second row; the unique constraint makes it a no-op |
| several workers running | `FOR UPDATE SKIP LOCKED` gives each a disjoint batch |

Delivery is at-least-once, so the idempotency key is what makes repeats harmless. Inspect undelivered work with:

```sql
SELECT id, idempotency_key, attempts, last_error FROM outbox_messages WHERE status = 'failed';
```

When a message exhausts its attempts the worker emits an ERROR-level failure alert through a
`FailureAlerter` seam, so a permanent failure is never silent:

```text
ALERT outbox dead letter topic=submission.created key=submission:9:created attempts=3 error=ConnectionError: ...
```

Swapping either the transport or the alerter means adding one class that implements `NotificationTransport` or `FailureAlerter`.

##### Webhook transport

Set `NOTIFICATION_WEBHOOK_URL` and the worker posts each message to that endpoint; leave it unset and it falls back to a logging transport, so the repository ships with no credentials.

```text
POST <NOTIFICATION_WEBHOOK_URL>
  X-Embedlead-Topic: submission.created
  X-Embedlead-Idempotency-Key: submission:42:created
  X-Embedlead-Signature: sha256=<hmac of the idempotency key>
  {"topic": "...", "idempotency_key": "...", "payload": {"submission_id": 42, ...}}
```

A non-2xx response raises, so the worker counts an attempt and retries. The receiver should treat `X-Embedlead-Idempotency-Key` as the deduplication key, because delivery is at-least-once.

When `NOTIFICATION_WEBHOOK_SECRET` is set, the signature is an HMAC-SHA256 of the idempotency key. The secret itself is never transmitted or logged, so a receiver can verify authenticity without it ever leaving either process.

There is no SMTP transport, no exponential backoff, and no automatic replay of dead letters. The worker runs as a supervised `worker` service in Compose with `restart: unless-stopped`, so delivery does not depend on a human running a command.

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
|-- docs/DESIGN.md        # architecture, contracts, and non-goals
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

## Remaining work

The required capstone core is complete. What remains is optional deployment and operational hardening, ordered by what a real operator would need first:

1. Add a Prometheus scrape configuration, recording rules, alert rules, and a Grafana dashboard.
2. Add exponential backoff and automatic dead-letter replay for webhook delivery.
3. Separate migration execution from application startup for multi-replica deployments.
4. Add CI running the same gates that run locally, then a deployed environment with TLS and backups.

Stretch features remain out of scope until the required acceptance probes pass.

## Limitations

Stated deliberately, because knowing what a system does not do is part of operating it.

**CORS restricts browsers, not the endpoint.** `BACKEND_CORS_ORIGINS` is enforced by
`CORSMiddleware`, so a page on a disallowed origin cannot read the response — a preflight from an
unlisted origin gets no `Access-Control-Allow-Origin` header at all. But CORS is a browser
contract: a direct `curl` from any origin still receives `202`, because an embeddable widget has to
accept posts from whatever site the tenant installed it on. The controls that actually defend the
public endpoint are origin-independent: the shared rate limiter, the ASGI body-size guard,
config-driven field validation, and the honeypot. Per-widget origin allow-listing is a real
hardening step and is not implemented.

**Metrics are per replica, which is correct, and there are no alert rules.**
`/api/v1/system/metrics` serves Prometheus text exposition (`text/plain; version=1.0.0`) behind a
token, with cumulative histogram buckets and `le="+Inf"` equal to `_count`. Prometheus's pull model
attaches `job` and `instance` labels per target, so N containers produce N label-distinguished
series and aggregation belongs in PromQL (`sum by (route) (...)`) rather than in the application.
What is missing is the operational layer around it: no scrape config or Prometheus server is
shipped, no recording or alerting rules, and no Grafana dashboard. Route-label cardinality is
bounded by `METRICS_MAX_ROUTES`, with overflow collapsed to a single `other` series rather than
hidden. Counters reset when a container restarts, which `rate()` handles by design.

**One process per container, so multiprocess metrics are not wired.** The image runs a single
uvicorn worker. Running `--workers > 1` behind one port would need
`prometheus_client`'s multiprocess mode and a per-container `PROMETHEUS_MULTIPROC_DIR`; that mode
also drops summary quantiles and custom collectors, so it is deliberately not enabled.

**The rate limiter fails open when Redis is unreachable.** With `REDIS_URL` set, limiter state
lives in Redis via `limits`' moving-window strategy, so replicas share one budget instead of each
getting its own. If Redis is down the request falls back to the in-process window rather than being
rejected: for a public lead-capture form a dropped lead is worse than a tolerated burst. The
fallback still enforces a limit, and Redis surfaces as a `degraded` sub-check in readiness without
gating the aggregate status, so a Redis outage cannot mark the container unhealthy. The trade-off is
explicit: during an outage the effective limit is per process again.

**Redis is deliberately not durable.** `--save ""`, `--appendonly no`, `maxmemory 256mb`,
`allkeys-lru`, and no volume. Restoring rate-limit counters older than the window is semantically
wrong, and fork/fsync latency would sit on the request path. Eviction under memory pressure fails
open, consistent with the outage policy above.

**No distributed tracing.** A request id is generated, propagated through logs via a `ContextVar`,
and echoed in `X-Request-ID`, which is enough to correlate one request across log lines in one
service. It is not a span tree, and there is no W3C `traceparent` propagation to the geo providers
or the notification webhook.

**Notification delivery is intentionally minimal.** Webhook only, fixed attempt budget, no
exponential backoff, no SMTP transport, and no automatic dead-letter replay. The worker
(`python -m app.worker`) runs as a supervised `worker` Compose service, so delivery is automatic; the command remains available for one-shot runs with `--once`.

**Index usage is unproven at demo data volume.** The composite widget index exists, and the
dashboard time-series index is proven with `EXPLAIN (ANALYZE, BUFFERS)` at 50,000 rows
(`Bitmap Index Scan`, 1,249 rows, 6 buffers). The widget lookup index still shows a sequential scan
at six rows, which is correct planner behaviour and is recorded as unverified rather than claimed as
an optimisation.

**Operational scope.** Compose credentials and the metrics token are local-development
placeholders. Cloud deployment, TLS termination, backups, log shipping, and CI are not configured.

## Public project documents

- [`docs/DESIGN.md`](docs/DESIGN.md): architecture, contracts, implementation status, and non-goals.
- [`EVIDENCE.md`](EVIDENCE.md): implemented proofs and pending acceptance criteria.
- [`BUILDLOG.md`](BUILDLOG.md): development decisions, tool usage, mistakes, and corrections.
- [`capstone.yaml`](capstone.yaml): evaluator command and endpoint manifest.
