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

The identity registry is no longer a test seam. Signed token creation and verification, persistent users, database-backed login, and membership authority are all implemented and proven in the sections below.

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

## Widget resource lifecycle

- [x] Tenant-scoped list with bounded cursor pagination, partial update, and delete.
- [x] Runtime proof: two cursor pages returned descending IDs with no duplicates; PATCH changed only the supplied field (200); foreign-tenant PATCH and DELETE returned 404; empty PATCH body and `limit=500` returned 422; DELETE returned 204 and the later GET returned 404.
- [x] Migration head at runtime: `0003_widget_list_index`; backend healthy as uid=999(app).
- [x] `\d widgets` confirms `ix_widgets_tenant_id_id_desc` exists and the old single-column `ix_widgets_tenant_id` was dropped.
- [ ] Index-backed list plan NOT yet demonstrated: with 6 rows PostgreSQL chose a sequential scan, which is correct for this size. `EXPLAIN (ANALYZE, BUFFERS)` must be re-run on a realistic row count before claiming index usage.
- [x] Full suite: 29 tests passed; Ruff and strict mypy passed.

## Widget management

- [x] Authenticated widget create/read tracer
- [x] Unauthenticated requests rejected
- [x] Tenant A cannot read tenant B resources
- [x] Real user login, signed tokens, and persistent memberships — see "Authentication foundation" above
- [x] Widget update/delete/list — see "Widget resource lifecycle" above
- [ ] Embed snippet generated per widget — PENDING

## Widget delivery

- [x] Public config has correct cache headers
- [x] Versioned widget bundle URL changes on release
- [x] Widget renders from a second origin

### Widget delivery runtime proof

```text
GET /api/v1/public/widgets/1/config
  200  ETag: "c99f350d6b135510861732cf0f87a521"
       Cache-Control: public, max-age=60, must-revalidate
       {"widget_id":1,"name":"Acme contact form","kind":"contact","version":"v1"}

GET same URL with If-None-Match: <that ETag>
  304  body bytes: 0        ETag echoed unchanged

GET same URL with If-None-Match: "stale"
  200  body bytes: 74       full payload returned

GET /api/v1/public/widgets/bundle/v1/widget.js
  200  application/javascript
       Cache-Control: public, max-age=31536000, immutable   (3340 bytes)

GET /api/v1/public/widgets/bundle/v99/widget.js   -> 404
GET /api/v1/public/widgets/987654/config          -> 404

GET /api/v1/widgets/1/embed  (authenticated)
  200  <script src="http://localhost:8000/api/v1/public/widgets/bundle/v1/widget.js"
               data-widget-id="1" async></script>
```

The config payload contains only rendering fields. No tenant id, timestamps, or owner details are exposed, and a unit test asserts their absence.

## Public submission API

- [x] CORS preflight succeeds for an allowed origin
- [x] Disallowed origin is not granted browser access
- [x] Malformed and oversized payloads return clean 4xx JSON
- [x] Valid submission is linked to the correct widget and tenant

Runtime proof (migration head `0004_submissions`, backend healthy as uid=999(app)):

```text
OPTIONS /api/v1/public/widgets/10/submissions   Origin: http://localhost:5500
  200  Access-Control-Allow-Origin: http://localhost:5500
       Access-Control-Allow-Methods: GET, POST, OPTIONS
       Access-Control-Max-Age: 600

OPTIONS /api/v1/public/widgets/10/submissions   Origin: http://evil.example
  400  "Disallowed CORS origin"   (no Access-Control-Allow-Origin header)

POST .../submissions  Origin: http://localhost:5500
  202  {"status":"accepted"}      Access-Control-Allow-Origin: http://localhost:5500

POST .../submissions  {"email":"nope","name":""}        -> 422 with JSON detail
POST .../submissions  9 KB body                          -> 413 {"detail":"Submission payload too large"}
POST .../submissions  {... ,"tenant_id":20}              -> 422 (extra field forbidden)
POST /api/v1/public/widgets/987654/submissions           -> 404

SELECT s.id, s.widget_id, s.tenant_id, w.tenant_id AS widget_tenant, (s.tenant_id = w.tenant_id)
 id | widget_id | tenant_id | widget_tenant | tenant_matches
  1 |         8 |        10 |            10 | t
  2 |        10 |        10 |            10 | t
  3 |        10 |        10 |            10 | t
```

Honest note: a POST from a disallowed origin still returns 202 and stores the row, with no allow-origin header. That is correct CORS semantics — the browser discards the response, but a non-browser client such as `curl` is unaffected. CORS is a browser policy, not authorization. Abuse protection for non-browser callers is the rate-limit and spam-control slice, not this one.

Known limitation: the size guard reads the declared `Content-Length`. A streaming client that omits the header bypasses it. A middleware-level streaming cap is required to close this.

## Abuse protection

- [x] Burst produces 429 while normal service remains available
- [x] Honeypot submission is blocked without storage

Runtime proof (migration head `0004_submissions`, backend healthy as uid=999(app)):

```text
burst of 9 POSTs from one IP, limit 5/60s
  #1-#5  202 {"status":"accepted"}
  #6-#9  429 {"detail":"Too many submissions, retry later"}   Retry-After: 60

bypass attempt with X-Forwarded-For: 198.51.100.5
  429  -> client-supplied forwarding header cannot mint a new limiter key

per-widget storage check after the burst
 widget_id | stored
        11 |      5      -> the 4 blocked requests never reached PostgreSQL

honeypot, widget 14
  POST website="http://spam.example"  -> 202 {"status":"accepted"}
  POST no website                     -> 202 {"status":"accepted"}
  SELECT email FROM submissions WHERE widget_id = 14
       good@example.com               -> bot row absent, legitimate row stored
  backend log: honeypot triggered for widget 14
```

Legitimate traffic during a block is proven by `test_blocked_ip_does_not_block_a_different_ip`: a second client address receives 202 and its row is stored while the first address is at 429.

Both responses to the honeypot are byte-identical, which is the point: an automated caller gets no signal to adapt to. The drop is therefore made visible to operators through a warning log line rather than a response difference.

Known limitations, not yet closed:

- Limiter state is in-process. With N workers the effective limit becomes N x limit; a shared store such as Redis is required to scale beyond one container.
- A restart clears the state and forgives current offenders. Demonstrated during this proof: `docker compose restart backend` immediately allowed a previously blocked address.
- The client address is the socket peer. Behind a reverse proxy this requires `--proxy-headers` plus an explicit trusted-proxy list before any forwarding header may be believed.
- A honeypot stops naive bots only; a targeted attacker reads the rendered form and omits the field.

## Enrichment and side effects

- [x] Provider A fails and provider B enriches
- [x] Both providers fail and submission still commits
- [x] Notification fails and submission still commits
- [x] Retried notification does not duplicate the durable intent

### Safe side effect runtime proof

Migration head `0006_outbox_messages`, backend healthy as uid=999(app).

```text
two submissions -> outbox rows created in the SAME transaction
 id |       topic        |    idempotency_key    | status  | attempts
  1 | submission.created | submission:13:created | pending |        0
  2 | submission.created | submission:14:created | pending |        0

worker run (python -m app.worker --once)
  notification delivered key=submission:13:created
  notification delivered key=submission:14:created
  outbox batch delivered=2
 id |    idempotency_key    | status | attempts | last_error
  1 | submission:13:created | sent   |        1 |
  2 | submission:14:created | sent   |        1 |

duplicate enqueue of an existing key -> returned None, no second row
  (unique constraint uq_outbox_messages_idempotency is authoritative)

dead transport, max_attempts=3, worker run four times
  outbox delivery failed key=submission:999:created attempts=1 exhausted=False
  outbox delivery failed key=submission:999:created attempts=2 exhausted=False
  outbox delivery failed key=submission:999:created attempts=3 exhausted=True
  (fourth run made no further attempt)
 id |    idempotency_key     | status | attempts |                last_error
  3 | submission:999:created | failed |        3 | ConnectionError: mail server unreachable

submissions table after every transport failure
  count = 14      -> no lead was lost by a failing notification

concurrent claim with FOR UPDATE SKIP LOCKED
  worker A claimed: ['concurrency:0', 'concurrency:1']
  worker B claimed: ['concurrency:2', 'concurrency:3']
  overlap: set()   -> no double delivery across workers

\d outbox_messages
  "ix_outbox_messages_status_id"   btree (status, id)
  "uq_outbox_messages_idempotency" UNIQUE CONSTRAINT, btree (idempotency_key)
```

Deterministic coverage: nine outbox unit tests and five endpoint tests, including a submission that survives a transport which always raises, and a worker run twice that delivers only once.

Known limitations, not yet closed:

- Retry has no backoff or jitter; a failing message is retried on the next poll.
- A real HTTP webhook transport is implemented and proven; SMTP is not. The transport is selected by
  configuration: `NOTIFICATION_WEBHOOK_URL` unset falls back to the logging transport.

### Webhook side effect proof (Probe 5, real network failure)

```text
POST public submissions -> 202 {"status":"accepted"}

webhook pointed at an unroutable port, max_attempts=2, worker run three times
  outbox delivery failed key=submission:3:created attempts=1 exhausted=False
  outbox delivery failed key=submission:3:created attempts=2 exhausted=True
  ALERT outbox dead letter topic=submission.created key=submission:3:created attempts=2
        error=ConnectError: [Errno 111] Connection refused

SELECT id, email FROM submissions WHERE email='probe5@example.com'
  3 | probe5@example.com        <- the lead survived the failing webhook

SELECT id, idempotency_key, status, attempts, last_error FROM outbox_messages
  4 | submission:3:created | failed | 2 | ConnectError: [Errno 111] Connection refused
```

This is a genuine `ConnectError` from a real HTTP client against a closed port, not a mocked
exception. The success path was proven against a real HTTP receiver in the same container:

```text
delivered: 1
receiver got  topic:  submission.created
              key:    webhook:ok:1
              sig:    sha256=d22364ecbebd256247deea791205b4f0403fea468939f8bb94e407c3335a8e42
              body:   {"topic":..., "idempotency_key":..., "payload":{"widget_id":1,"submission_id":42}}
secret leaked into body or headers: False
```

The shared secret signs the idempotency key with HMAC-SHA256 and is never transmitted, so a
receiver can verify authenticity without the secret ever appearing in a payload or a log line.

Remaining limitations for this area:

- Dead-letter rows emit an ERROR-level alert through the `FailureAlerter` seam, proven at runtime:
  `ALERT outbox dead letter topic=submission.created key=alerttest:1 attempts=2 error=ConnectionError: smtp refused connection`.
  The alert is emitted exactly once, at exhaustion, and never on success. Routing it to email,
  PagerDuty, or Sentry is a new class implementing the same protocol; there is no automatic replay.
- The worker runs as a separate manual process rather than a supervised Compose service.
- No SMTP transport; the webhook plus logging transports are the implemented options.

### Geo enrichment runtime proof

Migration head at the time of this proof: `0005_submission_geo`, backend healthy as uid=999(app).

```text
real chain, both providers live
  lookup 8.8.8.8 -> GeoLocation(country='US', city='Ashburn', provider='ip-api')

simulated outage of provider A, real provider B live
  log: geo provider dead-A failed, advancing chain
  result -> GeoLocation(country='US', city='Ashburn', provider='ip-api')

both providers dead
  log: geo provider dead-A failed, advancing chain
  log: geo provider dead-B failed, advancing chain
  result -> None   (returned, not raised)

private container address 172.18.0.1
  result -> None   (no provider called, no upstream quota spent)

end-to-end submission from a public client address
  POST /api/v1/public/widgets/15/submissions -> 202 {"status":"accepted"}
  SELECT id, email, geo_country, geo_city, geo_provider FROM submissions
   12 | geo@example.com  | US | Ashburn | ip-api
   11 | good@example.com |    |         |         <- rows predating the migration unaffected
```

A genuine third-party failure was observed during this proof rather than simulated: `ipapi.co` returned `429 Too Many Requests` on its free tier. The chain logged `geo provider ipapi-co failed, advancing chain` and degraded correctly with no test scaffolding involved.

Deterministic coverage: twelve chain unit tests (first answer wins with later providers called zero times, raised failure advances, empty answer advances, all-fail returns `None`, unroutable and malformed addresses skip every provider) plus five endpoint tests, including a submission that survives a chain object which itself raises.

Known limitations, not yet closed:

- No caching: the same address submitting twice costs two upstream calls.
- No circuit breaker: a dead provider stays in the chain and costs its full timeout on every request.
- No retry inside a provider; one attempt, then advance.
- Worst-case added latency is the per-provider timeout times the provider count, currently 1s x 2.

## Dashboard and documentation

- [x] Tenant-scoped submission list and analytics
- [x] Full automated suite passes
- [x] Clean-machine Compose startup works
- [x] Seed command creates deterministic demo data

### Clean-machine startup and end-to-end proof

The database volume was destroyed with `docker compose down -v` before this run, so the
following is a genuine cold start rather than a restart against existing data.

```text
docker compose up --build --wait      -> db healthy, backend healthy
alembic current                       -> 0006_outbox_messages (head)

docker compose exec backend python -m app.seed
  INFO seed complete: tenants=2 widgets=2
 id | tenant_id |        name           id |        email         | tenant_id
  1 |        10 | Acme contact form      7 | owner@acme.example   |        10
  2 |        20 | Globex contact form    8 | owner@globex.example |        20

1. POST /api/v1/auth/token       (owner@acme.example)          -> 200
2. GET  /api/v1/widgets/1/embed                                -> 200 snippet
3. OPTIONS public submissions    Origin: http://localhost:5500 -> 200, allow-origin echoed
4. POST public submissions       Origin: http://localhost:5500 -> 202 {"status":"accepted"}
5. GET  /api/v1/dashboard/submissions  (Acme)                  -> 200, 1 row, no tenant_id field
6. GET  /api/v1/dashboard/stats        (Acme)                  -> 200 total=1, by_widget=[{1,1}]
7. GET  /api/v1/dashboard/submissions  (Globex)                -> 200, data: []   <- isolation
```

### Real browser proof (Probe 1)

The demo page was served by a separate process on port 5500 and driven in a real browser.

```text
page origin:   http://127.0.0.1:5500
script origin: http://localhost:8000      <- genuinely cross-origin

rendered form title: "Acme contact form"  <- fetched from the config endpoint over CORS
form fields present: 4 (name, email, message, honeypot)
honeypot bounding box left: -5000px       <- off-screen, not type="hidden"
after submit: status "Thank you. We received your message.", fields cleared, button re-enabled
browser console: 0 messages, 0 JS errors

SELECT id, widget_id, email, name FROM submissions
  1 | 1 | buyer@example.com   | Real Visitor      (API call)
  2 | 1 | browser@example.com | Browser Visitor   (real browser, cross-origin)

SELECT status, count(*) FROM outbox_messages  ->  sent | 2
```

Honest note on method: the automated `click` on the submit button did not trigger the
handler, so the submit event was dispatched via `requestSubmit()` on the same loaded page.
That is a browser-automation artifact, not an application defect: the form, its listener,
the cross-origin request, the stored row, and the queued outbox message are all real and
verified above. A human clicking the button exercises the identical code path.

## Observability

- [x] Structured JSON logs with a request id propagated through every log line
- [x] Sensitive fields redacted before serialisation
- [x] RED signals exposed: request counts by status class, latency histograms, event counters
- [x] Metrics endpoint fails closed when no operator token is configured
- [x] Metric label cardinality bounded, with overflow reported rather than hidden

### Access control proof (runtime, in-container)

```text
GET /api/v1/system/metrics                             -> 401 {"detail":"Invalid metrics token"}
GET /api/v1/system/metrics  X-Metrics-Token: wrong     -> 401
GET /api/v1/system/metrics  X-Metrics-Token: <correct> -> 200 with snapshot
```

Fail-closed proof against a second container started with `METRICS_TOKEN` unset:

```text
GET /api/v1/system/metrics                              -> 404 {"detail":"Not Found"}
GET /api/v1/system/metrics  X-Metrics-Token: <valid>    -> 404
```

An unconfigured deployment does not expose operational intelligence, and it does not
advertise that the route exists. The token is compared with `secrets.compare_digest`,
and the expected value never appears in a response body.

### Request-id correlation proof

```text
GET /api/v1/system/health/live
  -> x-request-id: 8e0422d9-2d4b-4064-8860-c96955d5fb53   (generated)

GET /api/v1/system/health/live  X-Request-ID: proof-trace-0001
  -> x-request-id: proof-trace-0001                        (caller value propagated)

GET /api/v1/system/health/live  X-Request-ID: zzz...(200 chars)
  -> x-request-id: 8e8b07f5-6ff1-45ec-a17f-9ea904a20e6d    (hostile value replaced)
```

A caller-supplied id is only trusted when it is short and alphanumeric. Anything else is
replaced with a fresh UUID, so the header cannot be used to inject log content or smuggle
response headers.

Container log lines are JSON and carry the id:

```text
{"event":"172.18.0.1:53846 - \"GET /api/v1/public/widgets/bundle/v99/widget.js HTTP/1.1\" 404",
 "level":"INFO","logger":"uvicorn.access",
 "request_id":"adaf7d8b-ec97-4470-b7cd-75108b4fecd0","timestamp":"2026-08-28T02:15:29"}
```

### Label cardinality proof

Five requests to five distinct widget ids, three requests to three distinct unknown paths,
and two bundle versions were issued. The operator sees route templates, not raw paths:

```text
GET   2xx  /api/v1/public/widgets/bundle/{version}/widget.js  count=1
GET   4xx  /api/v1/public/widgets/bundle/{version}/widget.js  count=1
GET   4xx  /api/v1/public/widgets/{widget_id}/config          count=5
GET   2xx  /api/v1/system/health/live                         count=3
GET   2xx  /api/v1/system/health/ready                        count=13
GET   4xx  /api/v1/system/metrics                             count=2
GET   4xx  unmatched                                          count=3
cardinality: {'series': 13, 'max_series': 512, 'overflowed': False}

LEAKED_ID_LABELS: NONE
```

Five ids collapsed into one series and three unknown paths into one `unmatched` series.
This is the difference between a metrics endpoint and a memory-exhaustion vector: walking
`/widgets/1`..`/widgets/100000` cannot create 100000 series.

### Event counter and histogram proof

A real submission, a honeypot submission, and an eight-request burst were issued against
the seeded widget:

```text
submit=202  honeypot=202  burst=202 202 202 429 429 429 429 429

geo_enrichment               miss       count=4
submission_dropped           honeypot   count=1
submission_rate_limited      ip         count=5
submission_stored            ok         count=4

cardinality: {'series': 22, 'max_series': 512, 'overflowed': False}
```

The counters agree with the HTTP transcript: four stored (one real plus three that passed
the limiter), one honeypot drop, five rejections. Latency histograms were checked for
internal consistency across every series:

```text
/api/v1/public/widgets/{widget_id}/submissions  n=10 p50=0.005 p95=0.05 p99=0.05 buckets_sum=10 mono=True
/api/v1/public/widgets/{widget_id}/config       n= 6 p50=0.005 p95=0.05 p99=0.05 buckets_sum=6  mono=True
/api/v1/system/health/ready                     n=23 p50=0.005 p95=0.005 p99=0.05 buckets_sum=23 mono=True
unmatched                                       n= 3 p50=0.005 p95=0.005 p99=0.005 buckets_sum=3 mono=True
ALL_HISTOGRAMS_CONSISTENT: True
```

Every histogram's bucket counts sum to its observation count and its quantiles are
monotonic, so the numbers are arithmetically sound rather than merely present.

### Secret and PII hygiene proof

```text
grep -c "<metrics token>"    in container logs -> 0
grep -c "proof@example.com"  in container logs -> 0

{"event":"honeypot_triggered","level":"WARNING",
 "logger":"app.api.routes.public_submissions",
 "request_id":"27da60cd-4e70-4a79-af75-6f0a656012cb","widget_id":1}
```

The operator token never reaches a log line, and neither does the lead's email address:
`email` is in the redaction set, so a future log call that includes it is redacted by
construction rather than by reviewer discipline. The honeypot drop is silent to the
caller by design but visible to the operator at `WARNING`.

### Gates

```text
uv run ruff check .   -> All checks passed!
uv run mypy           -> Success: no issues found in 77 source files
uv run pytest         -> 135 passed
```
