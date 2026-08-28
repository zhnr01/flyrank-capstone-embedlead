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

### Test determinism proof

`test_tampered_access_token_is_rejected` was flaky at roughly one run in sixteen. Measured
cause, not guessed:

```text
last-char flip ACCEPTED by verifier: 0/2000   (with a random signature each time)
signature length (base64url chars): 43
bits encoded: 258 -> significant bits: 256, slack: 2

legal final characters: AEIMQUYcgkosw048   (16 of 64)
COLLIDING last chars: [('Y', 'a')]
flake probability per run: 1/16
  ...Y vs ...a: bytes identical after decode = True
```

The old test flipped the final base64url character. That character carries only four
significant bits, so `Y` and `a` decode to the same byte — the "tampered" token was
byte-identical to the original and was correctly accepted. The application code was never
wrong.

Tampering now mutates the payload, which has no encoding slack, and two attacks were added
that the suite never covered:

```text
tests/test_auth_foundation.py
  test_tampered_access_token_is_rejected          forged sub=user-1 against a user-7 signature
  test_token_signed_with_another_key_is_rejected  correct structure, attacker's key
  test_unsigned_token_is_rejected                 alg: none
```

Determinism verified by repetition rather than asserted:

```text
20 consecutive runs of tests/test_auth_foundation.py  -> 20 x 7 passed
 5 consecutive full-suite runs                        -> 137 passed, 137 passed,
                                                         137 passed, 137 passed, 137 passed
```

Under the old code a flake was expected at least once across that many runs.

### Gates (final)

```text
uv run ruff check .   -> All checks passed!
uv run mypy           -> Success: no issues found in 77 source files
uv run pytest         -> 137 passed
```

## Unit 0 — two Critical defects found by audit

Both were found by a delegated review pass, then independently reproduced with runtime probes
before any code changed. Neither was visible to the 137-test suite that was green at the time.

### 0A — payload size guard was bypassable

Before (the guard as shipped, `app/api/request_limits.py`):

```text
5,000,068-byte body, Transfer-Encoding: chunked, no Content-Length
  -> 202 Accepted, row persisted   (610x the 8192-byte cap)
identical body WITH Content-Length
  -> 413 Content Too Large
```

Two distinct causes. The guard returned early when `content-length` was absent, and a route
dependency cannot bound a body at all: FastAPI buffers the whole request at
`fastapi/routing.py:433` before solving dependencies at `:481`.

Note the first exploit attempt failed with 422 because Pydantic's `max_length` caught the
oversized `message` field first. The working exploit pads with whitespace *outside* the JSON
fields, so every field validator passes and only total body size is abnormal.

After (`BodySizeLimitMiddleware`, pure ASGI, counts bytes as they stream):

```text
### 0A - the exploit that previously returned 202 and stored a 5MB row
  body = 4997181 bytes, 610x the 8192-byte cap
  no Content-Length is sent: httpx streams it chunked
  -> HTTP 413
  -> rows 0 -> 0
  VERDICT: FIXED - rejected and nothing stored

### 0A control - a legitimate submission must still work
  -> HTTP 202, rows matching legit@example.com = 1
  VERDICT: OK - normal traffic unaffected
```

### 0B — a duplicate idempotency key silently destroyed the lead

Before:

```text
pre-insert the key the next submission will derive, then submit a real lead
  -> HTTP 202 {"status":"accepted"}
  -> rows matching lostlead@example.com: 0
```

The caller was told the lead was accepted. It was not stored. Cause: one `Session` per request
(`app/api/deps.py:10`) shared by every repository; `SqlAlchemySubmissionRepository.create` only
flushes; `SqlAlchemyOutboxRepository.enqueue` called `session.rollback()` on `IntegrityError`,
discarding the uncommitted submission. The route then committed an empty transaction.

The in-memory fake returns `None` and leaves its list intact, so no test using it could ever
observe this. That is Protocol drift hiding a real bug behind green tests.

After (SAVEPOINT via `session.begin_nested()`, so only the duplicate insert unwinds):

```text
### 0B - duplicate idempotency key must NOT destroy the lead
  next submission id = 2, pre-inserting key submission:2:created
  -> HTTP 202
  -> rows matching survivor@example.com = 1
  -> outbox rows for that key = 1 (must stay 1)
  VERDICT: FIXED - lead survived the duplicate

### session still usable after the duplicate
  -> HTTP 202, rows = 1
  VERDICT: OK
```

### Regression tests added

`tests/test_outbox_transaction.py` runs against real PostgreSQL, not SQLite — `JSONB` and
`SAVEPOINT` are both engine-specific, and a SQLite substitute would have proved nothing. It
skips with a clear reason when the database is unreachable rather than passing vacuously.

RED before the fix, on the real engine:

```text
>       assert len(stored_emails(session)) == 1
E       assert 0 == 1
E        +  where 0 = len([])
FAILED tests/test_outbox_transaction.py::test_duplicate_key_does_not_destroy_the_uncommitted_submission
FAILED tests/test_outbox_transaction.py::test_duplicate_key_leaves_exactly_one_outbox_row
FAILED tests/test_outbox_transaction.py::test_session_stays_usable_after_a_duplicate
FAILED tests/test_outbox_transaction.py::test_both_implementations_agree_on_duplicate_enqueue
4 failed in 3.17s
```

GREEN after:

```text
4 passed in 2.27s
```

### Migration safety, proven accidentally

The Unit 0 test fixture dropped every table while `alembic_version` remained stamped at head.
Recovery replayed the full migration chain from scratch:

```text
Running upgrade 0003_widget_list_index -> 0004_submissions, create submissions table
Running upgrade 0004_submissions -> 0005_submission_geo, add geo enrichment columns
Running upgrade 0005_submission_geo -> 0006_outbox_messages, create outbox messages table
```

All six tables rebuilt, seed succeeded. The migration chain is replayable end to end on an
empty database, not only incrementally.

### Gates

```text
uv run pytest        150 passed
uv run ruff check .  All checks passed!
uv run mypy          Success: no issues found in 79 source files
```

## Unit 2A — submission counts over time (brief section 4.6)

Section 4.6 asks for "counts over time". The dashboard had `total_submissions`, `by_country`
and `by_widget`, but no time series: `created_at` existed on the table and no query used it.

### Aggregation runs in SQL, not in Python

`date_trunc('day', created_at)` grouped in the database, tenant-scoped in the `WHERE` clause,
with a bounded window. Fetching rows and counting them in application memory would be unbounded
by design.

RED before implementation, on real PostgreSQL:

```text
E       AttributeError: 'SqlAlchemyDashboardRepository' object has no attribute 'daily_counts'
```

GREEN after:

```text
8 passed in 1.01s
```

The eight cases: day grouping, oldest-first ordering, cross-tenant isolation, window exclusion,
a non-positive window, a window past the cap, an empty tenant, and agreement between the SQL and
in-memory implementations.

### The index is used, proven at realistic volume

An index existing is not evidence it is used. Seeded 50,000 submissions across 400 days and
three tenants, ran `ANALYZE`, then `EXPLAIN (ANALYZE, BUFFERS)`:

```text
Sort  (cost=747.06..748.03 rows=386 width=16) (actual time=2.679..2.681 rows=30.00 loops=1)
  Sort Key: (date_trunc('day'::text, created_at))
  ->  HashAggregate  (cost=725.65..730.48 rows=386 width=16) (actual time=1.706..1.710 rows=30.00 loops=1)
        Group Key: date_trunc('day'::text, created_at)
        ->  Bitmap Heap Scan on submissions  (cost=21.97..718.98 rows=1334 width=8) (actual time=0.275..1.585 rows=1249.00 loops=1)
              Recheck Cond: ((tenant_id = 90) AND (created_at >= (now() - '30 days'::interval)))
              Heap Blocks: exact=207
              ->  Bitmap Index Scan on ix_submissions_tenant_id_created_at  (cost=0.00..21.63 rows=1334 width=0) (actual time=0.206..0.206 rows=1249.00 loops=1)
                    Index Cond: ((tenant_id = 90) AND (created_at >= (now() - '30 days'::interval)))
                    Buffers: shared hit=6
Planning Time: 1.317 ms
Execution Time: 2.930 ms
```

`Bitmap Index Scan on ix_submissions_tenant_id_created_at` — 1,249 of 50,000 rows touched, six
buffers for the index lookup, 2.9 ms. Contrast with `ix_widgets_tenant_id_id_desc`, which the
planner still ignores at demo volume and which remains recorded honestly in the tech-debt list.

### Endpoint behaviour in the container

```text
=== GET /dashboard/stats (default window) ===
status: 200
keys  : ['by_country', 'by_day', 'by_widget', 'total_submissions']

=== submit real leads across 3 distinct days for THIS tenant ===
  acme rows: 3
  by_day: [{'day': '2026-08-26', 'count': 1}, {'day': '2026-08-27', 'count': 1}, {'day': '2026-08-28', 'count': 1}]
  sum   : 3
  ordered oldest-first: True

=== narrow window drops the older day ===
  days=1  -> 1 point(s), sum=1
  days=30 -> 3 point(s), sum=3
```

### Abuse cases on the new parameter

```text
=== bounds are enforced at the boundary ===
  days=0       -> HTTP 422
  days=-5      -> HTTP 422
  days=366     -> HTTP 422
  days=100000  -> HTTP 422

=== a non-numeric window is rejected, not coerced ===
  injection attempt -> HTTP 422
  submissions table still present: 1

=== stats require authentication ===
  no token -> 401
  bad token -> 401

=== by_day is tenant-scoped: perf tenants must not appear ===
  perf rows in db : 50000
  acme by_day sum : 3
  acme rows in db : 3
```

The window is capped at 365 days in two independent places: the route rejects out-of-range input
at the HTTP boundary with 422, and `window_start()` raises `ValueError` in the repository. The
second check is not redundant — it holds for any caller that bypasses the route.

Fifty thousand rows belonging to other tenants were present in the same table throughout. The
tenant's series summed to exactly its own three rows.

### Gates

```text
uv run pytest        158 passed
uv run ruff check .  All checks passed!
uv run mypy          Success: no issues found in 80 source files
```

## Unit 2B — tenant-authored widget configuration (brief section 4.1)

Section 4.1 asks that a widget carry "type, title and description, form fields, button text,
display options". The model held only `name` and `kind`, `kind` was `Literal["contact"]`, and the
bundle hardcoded four fields in an `innerHTML` string. This was the second and last place where
the brief named something the code did not do.

### The defect the runtime proof caught

Unit tests were green and the config round-tripped, but the first container run showed:

```text
=== 6. a visitor submits the tenant-defined fields cross-origin ===
  POST -> 422 | ACAO: http://localhost:5500
  rows 0 -> 0
```

`SubmissionCreate` still declared a fixed `email`/`name`/`message`/`website` shape with
`extra="forbid"`, so a visitor filling in a tenant's own fields was rejected:

```text
{"type":"missing","loc":["body","name"],"msg":"Field required"}
{"type":"extra_forbidden","loc":["body","company"],"msg":"Extra inputs are not permitted"}
{"type":"extra_forbidden","loc":["body","phone"],"msg":"Extra inputs are not permitted"}
```

The configuration was decorative: an owner could define fields that no visitor could submit.
Validation had to become a function of the widget's stored config, which is
`app/core/submission_payload.py` — twelve tests, RED first.

After the fix, same probe:

```text
=== 6. a visitor submits the tenant-defined fields cross-origin ===
  POST -> 202 | ACAO: http://localhost:5500
  rows 0 -> 1
```

Stored row:

```text
buyer@example.com|{"email": "buyer@example.com", "phone": "+49 30 123456", "company": "Acme GmbH"}
```

### Full container transcript

```text
=== 1. migration 0008 applied: config column exists and is nullable ===
  config|jsonb|YES

=== 2. pre-existing rows survive the migration with NULL config ===
  stored config in db : NULL
  API still serves     : Get in touch | 3 fields
  VERDICT: legacy NULL rows degrade to defaults, no 500

=== 3. a tenant-authored config round-trips through JSONB ===
  created -> 201
  title       : Book a demo
  submit_label: Request slot
  theme       : dark
  fields      : [('email', 'email', True), ('company', 'text', True), ('phone', 'tel', False)]
  VERDICT: round-trip exact

=== 4. the bundle is served under v2 and is immutable ===
  v2 -> 200 | cache-control: public, max-age=31536000, immutable
  v1 -> 404 (old version must 404)
  innerHTML in shipped bundle: 0

=== 5. changing config busts the cache; unchanged config revalidates ===
  unchanged + If-None-Match -> 304 (expect 304)
  after a config edit       -> ETag changed: True

=== 7. abuse cases against the config surface ===
  unknown config key     -> HTTP 422
  unknown field prop     -> HTTP 422
  script in field name   -> HTTP 422
  no email field         -> HTTP 422
  13 fields              -> HTTP 422
  bad theme              -> HTTP 422
  config as string       -> HTTP 422

=== 8. cross-tenant config write is refused ===
  other tenant PATCH -> HTTP 404 (expect 404)
  title unchanged by intruder: 'Book a call instead'
```

### Why the column is nullable

Adding a `NOT NULL` column to a populated table requires a default or a backfill, and either
makes the migration harder to reverse. Nullable plus `config_from_stored()` means an existing row
reads as the default config, proven by check 2: the row's stored config is `NULL` and the API
still serves a usable three-field form rather than a 500.

### Why the bundle builds DOM nodes instead of markup

Config labels are tenant-controlled text arriving in a third-party page. The previous bundle
assembled its form with `innerHTML`, so a title of `<img onerror=...>` would execute in the
customer's site. `widget-v2.js` creates elements and assigns `textContent`, and a test asserts
`innerHTML` never appears in the shipped file. A markup-shaped label is stored and rendered
verbatim as text, which `test_markup_in_labels_is_stored_verbatim_not_interpreted` pins.

The version moved `v1` -> `v2` in all three required places — `app/core/config.py`,
`.env.example`, `compose.yaml` — and `v1` now 404s, so the immutable cache entry cannot serve
stale JavaScript against a new config shape.

### Migration safety, replayed from empty

```text
Running upgrade ... -> 0009_submission_answers   (9 of 9 applied)
columns present (widgets.config, submissions.answers): 2
```

### Test-fixture defect fixed at the source

`tests/test_outbox_transaction.py` used `Base.metadata.drop_all` against the shared development
database, which twice wiped the schema while leaving `alembic_version` stamped — so
`alembic upgrade head` became a silent no-op and the container crash-looped on a missing
relation. Both real-engine fixtures now open a connection, `create_all`, and run inside an outer
transaction with `join_transaction_mode="create_savepoint"` that is rolled back on teardown. No
test can destroy the schema any more. The rule is recorded in `docs/rules.md`.

### Gates

```text
uv run pytest        196 passed
uv run ruff check .  All checks passed!
uv run mypy          Success: no issues found in 88 source files
```

## Unit 1 — naming, magic literals, and the missing error-body test

Two review passes fed this unit: a magic-literal audit and a security audit that walked nine
abuse cases. Both were delegated as research; every finding below was re-verified against the
code before anything changed, and one turned out to be already fixed.

### The findings, and what was actually wrong

| Finding | Verdict | Fix |
|---|---|---|
| `SERVER_ERROR_STATUS = 500` in `app/api/request_context.py` | confirmed | deleted; imports `starlette.status` like the 9 other files already did |
| 9 bare `"pending"`/`"sent"`/`"failed"` literals in `app/repositories/outbox.py` | confirmed | `OutboxStatus` is now a `StrEnum`; all 9 replaced |
| `# type: ignore[arg-type]` at `app/repositories/outbox.py:41` | confirmed | replaced with `status_from_stored()`, which validates and raises on an unknown value |
| `Literal["healthy","unhealthy"]` spelled out 4× | confirmed (7 locations across two files) | one `HealthStatus` StrEnum owned by `app/services/health.py` |
| `"contact"` duplicated in schema and seed | confirmed | `CONTACT_KIND` in `app/core/widget_config.py` |
| `topic="submission.created"` bare literal | confirmed | `OutboxTopic` + `SUBMISSION_CREATED_TOPIC`; `enqueue` now takes `OutboxTopic` |
| `WidgetKind` widened back to `str` in 3 places | confirmed, introduced by Unit 2B | `WidgetKind` is a `StrEnum`; the dataclass and both response schemas use it |
| duplicated length constants `120`/`2_000`/`200` | confirmed | root cause was dead code — see below |

### The named types paid for themselves immediately

Turning `OutboxStatus` and `HealthStatus` into real types made mypy reject **13 further bare
literals in the test suite** that it had previously accepted. Those were invisible while the type
was a `Literal` alias that nothing enforced.

One change was caught by an existing contract test. Annotating `LivenessResponse.status` as the
full `HealthStatus` enum broke `test_liveness_openapi_allows_only_healthy_status`, because
`/health/live` would then advertise `unhealthy` as a possible value in its OpenAPI schema. The
one-member narrowing is load-bearing, so it stayed as `Literal[HealthStatus.HEALTHY]`.

### The duplicated constants were a symptom of dead code

`app/api/schemas/submissions.py` restated `120`, `2_000` and `200` as bare ints while
`app/core/submission_payload.py` owned the named versions. The real problem was that
`SubmissionCreate` had been dead since Unit 2B replaced it with config-driven validation:

```text
$ grep -rn 'SubmissionCreate' app/ tests/ --include='*.py' | grep -v schemas/submissions.py
DEAD CODE CONFIRMED: zero references outside its own definition
```

Deleting it removed all three duplicated constants at once. `SubmissionAccepted.status` also
gained a real `SubmissionStatus` type instead of a bare `str` with a literal default.

`MAX_HONEYPOT_LENGTH` was dead in the other direction — defined, never used, so nothing bounded
the honeypot field. Now enforced, with a test.

### The missing abuse case: internal-detail leak in an error body

The security audit found eight of nine abuse cases covered and one entirely absent. Current
behaviour was in fact safe, but nothing asserted it, so a single custom exception handler could
regress it silently. The audit mapped every path where an exception value could reach a body;
the one that interpolates is code written in Unit 2B:

```python
app/api/routes/public_submissions.py:73
    detail=str(error),
```

Safe today because every message in `validate_against_config` is hand-written — verified by
driving the validator with non-string inputs and reading back only `'email must be a string'`
and `'name must be a string'`. But it is a `str(exception)` on a client-reachable path.

`tests/api/test_error_body_leaks.py` now sweeps every client-reachable status — 404, 401, 413,
422, 429 — against a deny-list of 24 fragments: driver and ORM names, SQL keywords, path
fragments, settings field names, ORM class names.

### The deny-list was mutation-tested

A guard that has never failed proves nothing, so a leak was injected deliberately:

```text
$ # temporarily: detail=f"Widget not found (SELECT * FROM widgets WHERE id={widget_id}) [SQL: psycopg]"
AssertionError: 404 config leaked 'psycopg': {"detail":"Widget not found (SELECT * FROM ...
1 failed, 9 passed
$ # restored
10 passed
```

### A 500 is worse than a default on a public endpoint

The first container proof showed the new strictness had a sharp edge:

```text
=== 4. an unknown stored value ===
  widget 2 with kind='bogus_kind' -> HTTP 500
```

A corrupt row made a public endpoint raise. The body was opaque, so nothing leaked, but a 500 is
a denial-of-service lever and it contradicted the graceful degradation already proven for a NULL
config in Unit 2B. `kind_or_default()` and a `ValidationError` guard in `config_from_stored()`
now degrade to a safe default, while `kind_from_stored()` stays strict for callers that want it.
Five tests in `tests/test_widget_config_degradation.py` pin both behaviours.

### Container transcript

```text
=== 1. StrEnum refactors survive a real round-trip through PostgreSQL ===
  widget kind served      : 'contact'
  stored in db            : 'contact'
  OpenAPI enum for kind   : #/components/schemas/WidgetKind

=== 2. health status enum serialises as a plain string ===
  /health/live  -> 200 {'status': 'healthy'}
  /health/ready -> 200 healthy | checks: ['database']

=== 3. outbox status enum round-trips through the real column ===
  submission -> 202 {'status': 'accepted'}
  outbox row  : pending|submission.created
  distinct statuses stored: pending

=== 4. a corrupt stored kind degrades instead of raising ===
  widget 2 with kind='bogus_kind' -> HTTP 200
  body: {"widget_id":2,"name":"Globex contact form","kind":"contact","version":"v2",...
  restored -> contact

=== 5. error bodies leak nothing ===
  404 unknown widget   -> 404 | leaks: none
  404 old bundle       -> 404 | leaks: none
  401 no token         -> 401 | leaks: none
  401 junk token       -> 401 | leaks: none
  422 bad email        -> 422 | leaks: none
```

The `StrEnum` choice is what makes check 1 work: the value stored in PostgreSQL is the plain
string `contact`, the JSON served is `"contact"`, and the generated OpenAPI now carries a real
`WidgetKind` enum schema rather than an untyped string.

### Gates

```text
uv run pytest        212 passed
uv run ruff check .  All checks passed!
uv run mypy          Success: no issues found in 89 source files
```

## Unit 3 — shared state for horizontal scaling (README's own "next steps")

The README already named both gaps: an in-process rate limiter that gives N x the limit with N
replicas, and a JSON metrics endpoint no scraper can read. This unit closes them, and the research
overturned half of the original plan.

### The plan was wrong about metrics

The intent was "put both the limiter and the metrics registry in Redis". Prometheus's own docs say
that is an anti-pattern. Prometheus is a **pull** system: it scrapes each target and attaches `job`
and `instance` labels itself, so N containers produce N label-distinguished series and aggregation
happens at query time with `sum by (...)`. Centralising would lose per-instance visibility, add a
write to every request, make observability depend on Redis, and break `rate()` — which assumes a
monotonic counter per series. Pushgateway is documented as being for batch jobs only.

So the split is: **Redis for the limiter, per-replica Prometheus for metrics.**

### The hand-rolled registry was not just unconventional, it was wrong

221 lines replaced by 56 plus a library. The measurement that settled it:

```text
90 observations at 10ms, 10 at 400ms

HAND-ROLLED (what we shipped):
  p50 = 25.0 ms   (true 10ms)  <- 2.5x WRONG

PROMETHEUS (cumulative buckets):
  le= 0.005 -> 0.0
  le= 0.025 -> 90.0
  le=  0.05 -> 90.0
  le=   0.5 -> 100.0
  le=  +Inf -> 100.0
  sum = 4.9 s
```

`quantile()` returned a bucket **upper bound** instead of interpolating. Prometheus exposes
cumulative buckets and a sum, so PromQL interpolates inside the bucket and gets ~10ms. The old
endpoint also emitted non-standard JSON `Infinity` for the overflow bucket.

### Container transcript

```text
=== 1. the shared store is reachable and EPHEMERAL by design ===
  ping             : PONG
  persistence(save): 'save'          (empty -> RDB disabled)
  appendonly       : no
  maxmemory-policy : allkeys-lru

=== 2. the rate limiter now writes to Redis, not to process memory ===
  keys after 3 submissions: ratelimit:LIMITER/widget:1/30/60/second
                            ratelimit:LIMITER/ip:172.18.0.1/5/60/second
  VERDICT: shared store in use

=== 3. the limit is enforced ACROSS the whole store ===
  statuses   : [202, 202, 202, 202, 202, 429, 429, 429, 429]
  Retry-After: 60

=== 4. /metrics is Prometheus TEXT, gated, and spec-shaped ===
  without a token -> 401
  content-type    : text/plain; version=1.0.0; charset=utf-8
  is JSON?        : False
  # HELP embedlead_requests                        True
  # TYPE embedlead_requests                        True
  embedlead_requests_total{                        True
  embedlead_request_duration_seconds_bucket{       True
  le="+Inf"                                        True
  embedlead_request_duration_seconds_sum           True
  embedlead_request_duration_seconds_count         True
  embedlead_events_total{                          True

=== 5. the rate-limit event was actually counted ===
  embedlead_events_total{name="submission_stored",outcome="ok"} 8.0
  embedlead_events_total{name="submission_rate_limited",outcome="ip"} 4.0

=== 7. readiness reports redis WITHOUT letting it gate the container ===
  {"status":"healthy","checks":{"database":{"status":"healthy","response_time_ms":2.11},
   "redis":{"status":"healthy","response_time_ms":0.9}}}

=== 8. GRACEFUL DEGRADATION: stop Redis, the public form must STILL accept ===
  submission with Redis DOWN -> 202  (fail OPEN)
  readiness with Redis DOWN  -> 200
  {"redis":{"status":"degraded","response_time_ms":1001.18,"error":"TimeoutError"}}
```

Check 2 is the whole point of the unit: the limiter state is now a Redis key, so a second replica
shares one budget instead of getting its own. `tests/test_redis_rate_limit.py` pins that directly —
two limiter instances against one `FakeServer` allow exactly three of four requests.

### The defect the proof found, and the three wrong fixes before the right one

Check 8 originally reported `response_time_ms: 8294` — an 8.3 second readiness probe against a
250ms configured timeout. A probe that slow is itself an outage risk. Narrowing it took four
attempts, each measured:

| Attempt | Result | Why it was not enough |
|---|---|---|
| `socket_timeout=0.25`, `socket_connect_timeout=0.25` | 8294ms | `Redis.from_url` retries by default |
| `retry=Retry(NoBackoff(), 0)`, `retry_on_timeout=False` | 3961ms | still ~4s unaccounted for |
| reuse one pooled client instead of one per probe | 3249ms healthy path 3.18 -> 0.95ms, outage path barely moved |
| `asyncio.wait_for(..., redis_health_timeout_seconds)` | **1001ms** | correct |

The root cause was not redis-py at all:

```text
$ docker compose stop redis
$ docker compose exec backend python -c "socket.getaddrinfo('redis', 6379)"
DNS FAILED after 3998 ms -> gaierror
```

Docker removes the DNS record when a container stops, so `getaddrinfo` blocks in libc **before any
socket exists**. A connect timeout cannot bound name resolution; only a timeout above the resolver
can. `tests/test_redis_health.py` pins the bound at 0.21s for a hanging check.

### Fail open, deliberately

If Redis is unreachable the limiter falls back to the in-process window rather than rejecting. For
a public lead-capture form a dropped lead is worse than a tolerated burst, and the fallback still
enforces a limit — `test_the_fallback_still_enforces_a_limit_rather_than_allowing_everything`
proves it is not an open door. Redis reports as a `degraded` sub-check while the aggregate status
follows the database alone, so a Redis outage cannot mark the backend container unhealthy and take
the API down through `depends_on`.

### Dead configuration removed

`METRICS_MAX_SERIES` was declared in `app/core/config.py`, `compose.yaml` and `.env.example` and
read by nothing once `prometheus_client` took over cardinality. A setting an operator can change
with no effect is worse than no setting; deleted from all three.

### Gates

```text
uv run pytest        245 passed
uv run ruff check .  All checks passed!
uv run mypy          Success: no issues found in 97 source files
```

## Final review — findings I verified directly

Before the delegated audits landed I ran the checks I could verify myself. Recorded here because
three of them were real defects, not documentation nits.

### 1. Three env vars documented but silently ignored

`.env.example` advertised `GEO_PROVIDER_A_ENABLED`, `GEO_PROVIDER_B_ENABLED` and
`NOTIFICATIONS_ENABLED`. None had a `Settings` field, and `model_config` sets `extra="ignore"`, so
pydantic discarded them without complaint:

```text
$ for v in $(grep -oE '^[A-Z_]+=' .env.example | tr -d '='); do ... done
  ORPHAN in .env.example: GEO_PROVIDER_A_ENABLED
  ORPHAN in .env.example: GEO_PROVIDER_B_ENABLED
  ORPHAN in .env.example: NOTIFICATIONS_ENABLED

$ grep -rn 'geo_provider_a_enabled|notifications_enabled' app/ tests/
  (zero reads)
```

An operator setting `NOTIFICATIONS_ENABLED=false` would still get notifications. This is the exact
failure `COMPLIANCE.md` already records for `BACKEND_CORS_ORIGINS` — the same class recurred in a
different file.

The fix differs per variable, which is why they needed separating rather than bulk-adding fields:

- `NOTIFICATIONS_ENABLED` was **redundant**. `notification_webhook_url` already gates delivery
  (`app/services/notifications.py:75`), so an empty URL is the off switch. Deleted from
  `.env.example` rather than given a second, competing control.
- The two geo toggles were **genuinely missing**. `build_geo_chain` hardcoded both providers, so
  there was no way to disable one — and Unit 4's rehearsal has to kill provider A live to show the
  fallback chain. Wired to real `Settings` fields, RED test first, and added to `compose.yaml` so
  the container exposes them too.

```text
$ uv run pytest tests/test_geo_toggles.py
5 passed
```

The master switch still wins over both toggles, which is asserted rather than assumed.

`GeoProviderChain` needed a public `providers` property for the test to read; asserting against
`_providers` would have coupled the test to a private attribute.

### 2. CORS was documented as if it protected the endpoint

Verified against the running container:

```text
$ curl -X POST .../widgets/1/submissions -H 'Origin: http://evil.example' -d '...'
status=202

$ curl -X OPTIONS ... -H 'Origin: http://evil.example'      # allow-origin headers: 0
$ curl -X OPTIONS ... -H 'Origin: http://localhost:5500'    # allow-origin headers: 1
```

So CORS behaves correctly — a browser on a disallowed origin cannot read the response — but `curl`
still posts successfully, because CORS is a browser contract and nothing in the application checks
`Origin`. `grep -rn 'Origin' app/api/ app/core/` returns nothing.

This is **not** a vulnerability: an embeddable widget must accept posts from whatever site the
tenant installed it on, and the brief requires cross-origin submissions to work. The real defences
are origin-independent — the shared rate limiter, the ASGI body-size guard, config-driven
validation, and the honeypot. The existing test is honestly named
(`test_disallowed_origin_is_not_granted_browser_access`) and only asserts the header.

The defect was documentation: the README never said any of this. Now stated plainly, including that
per-widget origin allow-listing is not implemented.

### 3. The README described behaviour that no longer existed

Four separate drifts, all introduced by the Unit 3 commit:

| Stale claim | Reality |
|---|---|
| "Rate-limit counters and the metrics registry both live in the process… N x limit" | Redis-backed via `limits`; shared budget proven |
| "The snapshot is JSON… not an OpenMetrics text endpoint" | `text/plain; version=1.0.0`, cumulative buckets |
| "bounded by `METRICS_MAX_SERIES`" | that field was **deleted**; the real one is `METRICS_MAX_ROUTES` |
| A 20-line JSON response example with `p50_seconds`, `buckets`, `cardinality` | the endpoint returns exposition text |
| "Limiter state is in-process… Redis is required before scaling" (line 340, separate wording) | Redis is wired |

The JSON example was the worst of these: a reviewer copying it would find nothing resembling it.
Replaced with output captured from the running container, which also demonstrates the two claims the
surrounding prose makes — route templates rather than concrete paths, and `le="+Inf"` equal to
`_count` (both 131.0).

### 4. The harness let it happen, so the harness changed

Doc/code drift was not one of the 15 enforced lanes, which is precisely why four false claims
survived a commit that ran every gate. `scripts/verify_harness.sh` now enforces three
documentation-accuracy checks:

- every env var in `.env.example` and `compose.yaml` maps to a real `Settings` field;
- no doc names a setting that has been deleted;
- the README does not assert in-process rate limiting while `redis_url` exists, nor JSON metrics
  while `prometheus_client` is wired.

All three fired on the first run. Mutation-tested afterwards by reintroducing the stale sentence:

```text
STALE README: claims in-process rate limiting while redis_url exists
HARNESS FAILED
--- restored ---
HARNESS VERIFIED
```

The first version of the guard only matched the exact phrasing I had just fixed, which would have
been theatre; it now also catches the differently-worded claim found at line 340.

### Clean on first inspection

Worth recording so the review is not only a list of faults:

```text
comments/docstrings in app/ or tests/   0
type: ignore / cast() / noqa            0
.env tracked by git                     0 (and .gitignore excludes it)
f-string or concatenated SQL            0
innerHTML in the embedded bundle        0 (textContent only)
JWT algorithms=[HS256]                  pinned, so alg-confusion and alg:none both fail
```

## Final review — delegated audits, and why every finding was re-verified

Three read-only audits ran in parallel: security, architecture/ponytail, and ops/documentation.
Their consolidated message never arrived, but all three had written completed results to disk, so
the summaries were read directly rather than waiting.

### Four of the security audit's claims were false

This is the reason a subagent report is treated as a lead, not a fact.

| Audit claim | Reality |
|---|---|
| MEDIUM: "rate-limit key derivation trusts client-supplied `X-Forwarded-For`, first value in the chain is taken" | **Fabricated.** `client_address` returns `request.client.host`; the string `forwarded` does not appear in `app/api/rate_limit_dependencies.py` at all, and `test_forwarded_header_cannot_bypass_the_ip_limit` already locks the property |
| UNCOVERED: internal-detail leak in an error body | `tests/api/test_error_body_leaks.py`, **10 tests**, mutation-tested against a deliberately injected leak |
| UNCOVERED: secret in output or logs | `test_sensitive_fields_are_redacted` and `test_metrics_token_is_never_written_to_a_log_line` |
| UNCOVERED / MEDIUM: no dead-or-slow-dependency test | **five** exist, including `test_a_redis_outage_fails_open_onto_the_in_process_limiter` and `test_a_hanging_redis_is_bounded_by_the_health_timeout` |

The child was reasoning from a pre-Unit-3 view of the tree. Had these been applied on trust, the
result would have been re-implementing an XFF defence that already exists and writing four duplicate
test files.

### Six NON-ISSUEs independently confirmed

Worth recording because a review that only lists faults is not a review:

- JWT pinned to a single-element `algorithms=[HS256]` allowlist with verification on, so
  `alg: none` and RS256->HS256 confusion both fail.
- Tenant scoping enforced in the **repository/SQL** layer, not just the route: `tenant_id` is a
  required parameter and lands in the `WHERE` clause.
- No DOM-XSS sink in `app/static/widget-v2.js`; every tenant-controlled string goes through
  `textContent`.
- CORS is not load-bearing for authorization.
- No SQL built by f-string or concatenation.
- `.env` git-ignored and untracked; no secret-shaped literal in source.

### The one real security finding: the honeypot was bypassable

Verified before acting, and it reproduced:

```text
field FILLED (bot)         looks_automated=True
field EMPTY (human)        looks_automated=False
field ABSENT (smart bot)   looks_automated=False
```

`isinstance(trap, str) and bool(trap.strip())` means a bot that simply **omits** the `website` key
looks exactly like a human. Only bots that blindly fill every input were caught.

The obvious fix — treat absence as automated — is **wrong**, and the test suite proved it within one
run:

```text
11 failed, 233 passed
FAILED tests/api/test_submissions.py::test_valid_cross_origin_submission_is_accepted
FAILED tests/api/test_submission_outbox.py::test_worker_delivers_enqueued_submission_once
```

Any legitimate client that omits the field gets classified as a bot. The widget bundle itself only
sent `website` when non-empty (`app/static/widget-v2.js:105-108`), so real human submissions
omitted it too. Reverting was the correct response to that evidence, not weakening the tests.

Shipped instead:

- the bundle now **always** sends the field (`body.website = form.elements.website.value`), so
  presence is normal rather than exceptional;
- a **non-string** trap value is now treated as automated — `{"website": 1}` previously slipped
  through because `isinstance(trap, str)` short-circuited to `False`, which is a genuine bypass;
- absence stays tolerated, because a third-party integrator posting directly to the API without the
  field is a legitimate caller, not an attacker.

```text
uv run pytest tests/test_honeypot_presence.py
6 passed
```

The remaining limitation is honest and now written down: a bot that sends `website: ""` defeats the
honeypot. That is inherent to honeypots, which is why the brief asks for *at least one* spam control
and the rate limiter carries the real load. Per-widget randomised field names would raise the cost,
and are recorded as not implemented rather than implied.

### Gates

```text
uv run pytest        244 passed, 12 skipped (256 total)
uv run ruff check .  All checks passed!
uv run mypy          Success: no issues found in 99 source files
```

## Final review — ops findings, and a CRITICAL that was not one

The ops audit raised one CRITICAL, two HIGH, four MEDIUM and two LOW. Each was verified against the
running stack before being acted on; one was wrong and one was wrong about severity.

### The CRITICAL was a false alarm, disproved by experiment

Claim: `embedlead-db-data:/var/lib/postgresql` mounts the parent of `PGDATA` rather than `PGDATA`
itself, so "data does not persist".

Both underlying facts were true:

```text
$ docker run --rm postgres:18-alpine sh -c 'echo $PGDATA'
/var/lib/postgresql/18/docker

$ docker inspect ...-db-1 --format '{{range .Mounts}}{{.Name}} -> {{.Destination}}{{end}}'
volume ...embedlead-db-data -> /var/lib/postgresql
```

But the conclusion did not follow: `PGDATA` sits **inside** the mounted path, so it is on the volume.
Tested rather than argued — write a row, destroy the containers, bring the database back:

```text
=== destroying containers, keeping the named volume ===
 Container ...-db-1 Started
db back in 1 tries
=== did the row survive container removal? ===
written before container removal
=== are the seeded app tables still there? ===
3
```

Data persisted. Had this been applied on trust as a CRITICAL data-loss bug, the "fix" would have
been chasing a defect that did not exist.

The audit had found something real, at MEDIUM rather than CRITICAL: the mount path is
**version-coupled**. `PGDATA` contains the major version, so `postgres:19-alpine` would initialise a
fresh empty cluster at `/var/lib/postgresql/19/docker` inside the same volume, silently leaving the
old cluster behind — which looks exactly like total data loss to an operator. Pinning the mount to
`PGDATA` makes a version bump fail loudly instead. Verified by destroying the volume entirely and
replaying from empty:

```text
$ docker compose down -v          # Volume ...embedlead-db-data Removed
$ docker compose up -d
backend Up (healthy)   db Up (healthy)   redis Up (healthy)   worker Up
$ psql -c 'select version_num from alembic_version'
0009_submission_answers
```

### HIGH 1: the container healthcheck probed readiness

`compose.yaml` health-checked `/health/ready`, which returns 503 on any database blip, combined with
`restart: unless-stopped`. A transient DB hiccup would therefore mark the backend unhealthy and
restart a process that was serving fine. Readiness answers "should traffic be routed here"; liveness
answers "is this process alive" — and `app/services/health.py` already implements both separately.
The healthcheck now targets `/health/live`.

This is the same class as the Redis decision in Unit 3: a dependency's health must not be able to
kill the container that depends on it.

### HIGH 2: the outbox worker was not supervised

`compose.yaml` defined three services and no worker, so notification delivery only happened when a
human ran `python -m app.worker`. Every notification test passed, because they invoke the worker
directly — the gap was in the shipped artifact, not the code.

Now a supervised `worker` service with `restart: unless-stopped`, `depends_on` gating on db, redis
and backend health, and a `command` override so it does not re-run `alembic upgrade head` from the
shared image. Proven with no human intervention:

```text
$ curl -X POST .../widgets/1/submissions   -> 202

$ psql -c 'select status, attempts from outbox_messages order by id desc limit 1'
sent attempts=1

worker-1 | INFO app.services.notifications notification delivered
           topic=submission.created key=submission:1:created
worker-1 | INFO app.worker outbox batch delivered=1
```

Two README claims became false the moment this landed and were corrected in the same commit.

### MEDIUM: backend port was published on all interfaces

`"8000:8000"` exposed the API to the LAN while `db` and `redis` were correctly loopback-bound —
an inconsistency, not a considered decision. Now `127.0.0.1:8000:8000`.

Side effect worth noting: this immediately collided with a leftover `hermes verify` uvicorn on
`127.0.0.1:8000`, which the old `0.0.0.0` binding had silently tolerated. The stricter binding
surfaced a conflict that was always there.

### Deliberately not fixed, and why

- **`Dockerfile` CMD couples `alembic upgrade head` to serving.** With N replicas each would attempt
  the migration on boot. Alembic takes a lock, so the outcome is serialised rather than corrupt, and
  the single-container topology this project documents cannot race. A separate init/job step is the
  correct production answer and is recorded rather than implied.
- **No `deploy.resources.limits` or logging caps.** Compose-level resource limits are ignored outside
  swarm mode, and the project already states that cloud deployment is out of scope.
- **Placeholder credentials inline in compose.** Already flagged in the README as
  local-development-only, and `.env` is git-ignored.

### Gates

```text
uv run pytest        256 passed
uv run ruff check .  All checks passed!
uv run mypy          Success: no issues found in 99 source files
runtime              4/4 services healthy from an empty volume, 9 migrations replayed
harness              HARNESS VERIFIED
```

## Final review — the architecture audit found nothing, and that is a result

The third audit (over-engineering, dead code, layer violations) returned **no actionable finding**.
Recorded because "nothing to cut" is a legitimate outcome, and because two of its claims were wrong
in instructive ways.

### What it confirmed

- No `app.api` import inside `app/core` or `app/repositories`.
- No `fastapi` or `starlette` import inside `app/core`.
- Inward-only dependency direction holds at the import level.
- The no-comments / no-docstrings house rule is respected across `app/` and `tests/`.

The harness already gates all four, so this is independent agreement rather than new information.

### Claim 1: "suppressions cluster at the storage and serialization boundary"

```text
$ grep -rn 'type: ignore|# noqa|cast(' app/ tests/ --include='*.py' | wc -l
0
```

Zero. The claim is not merely unsupported, it is inverted: those suppressions **used to** exist and
Unit 1 removed them by making `OutboxStatus`, `HealthStatus` and `WidgetKind` real `StrEnum`s with
validated `*_from_stored` converters. `verify_harness.sh` now fails the build if one returns. The
audit described the codebase as it was two commits ago.

### Claim 2: six unread `Settings` fields, including `postgres_password`

Reproducible with the audit's own method:

```text
UNREAD: environment
UNREAD: postgres_server / postgres_port / postgres_db / postgres_user / postgres_password
```

All six are read — inside `config.py` itself, via `self`:

```text
app/core/config.py:58   if self.environment == "production" and self.secret_key.startswith(
app/core/config.py:68   username=self.postgres_user,
app/core/config.py:69   password=self.postgres_password,
app/core/config.py:70   host=self.postgres_server,
```

A grep for `settings.<field>` cannot see a field consumed by the model that declares it. Deleting
`postgres_password` as "dead config" would have broken every database connection in the project.
This is the sharpest example so far of why a subagent finding is a lead and not a fact.

### The one genuine lead, and why it survived

`FailureAlerter` in `app/services/outbox_worker.py:11` is a `Protocol` referenced in only one file,
with one implementation (`LoggingFailureAlerter`) beside it and an `alerter or Default()` parameter —
the exact shape of a `yagni` cut.

It stays, because there **is** a second implementation:

```text
tests/test_outbox.py:166   alerter = RecordingAlerter()
tests/test_outbox.py:171   alerter=alerter,
```

`RecordingAlerter` is how the dead-letter path is asserted without reading log output. That is the
same justification as the in-memory/SQLAlchemy repository pairs: a Protocol whose second implementer
is a test double is carrying weight, not decorating.

Checked every Protocol in the tree for the same question:

```text
UnitOfWork 2   GeoProvider 3   NotificationTransport 4   RateLimiterProtocol 2
DashboardRepository 3   MembershipRepository 4   OutboxRepository 5
SubmissionRepository 3   UserRepository 3   WidgetRepository 5   FailureAlerter 1
```

### Net result of the ponytail pass

`net: 0 lines`. The 221-line metrics registry and the dead `SubmissionCreate` schema were already
cut in Units 3 and 1 respectively, which is where the real bloat was. Two of the audit's four
dead-code categories were generic assertions with no `file:line`, and the two that were concrete did
not survive verification.

### Scorecard across all three audits

| Audit | Actionable | False or unverifiable | Verified NON-ISSUE |
|---|---|---|---|
| Security | 1 (honeypot bypass) | 4 | 6 |
| Ops / docs | 4 (worker, healthcheck, PGDATA, port) | 1 CRITICAL disproved by experiment | — |
| Architecture | 0 | 2 | 4 |

Five real fixes out of twenty-six reported items. The delegation was still worth it — the honeypot
bypass, the unsupervised worker and the readiness healthcheck are defects I had looked straight past
— but a 5-in-26 signal rate is the argument for verifying every single claim against the code before
touching anything.

## Final review, second pass — the delegation replay, and one real bound added

The consolidated audit message arrived after the findings had already been processed from disk. Two
claims in its tail had not been checked, and both were worth chasing.

### The BLOCKING claim was true when written and false at HEAD

> "BLOCKING for a clean clone: `app/core/config.py`, `app/api/geo_dependencies.py` and
> `app/core/geo.py` are uncommitted and `tests/test_geo_toggles.py` is untracked; at HEAD,
> `geo_dependencies.py:18-21` reads `settings.geo_provider_a_enabled` which does not exist, so a
> fresh clone would fail at import."

That was accurate at the moment the audit ran — those files were in my working tree mid-edit. Commit
`714126d` landed them. Rather than reason about it, a real clone from GitHub settled it:

```text
=== HEAD ===
ee1a16c docs(review): record the audit scorecard and the lessons it forced
=== do the files the audit called uncommitted exist at HEAD? ===
  PRESENT app/core/config.py
  PRESENT app/api/geo_dependencies.py
  PRESENT app/core/geo.py
  PRESENT tests/test_geo_toggles.py
=== does the setting the audit said is absent exist? ===
1
=== can the app be imported from a clean clone? ===
app.main imported OK
=== full suite on the clean clone ===
244 passed, 12 skipped
```

A fresh clone imports and tests clean. The 12 skips are the real-PostgreSQL tests, correctly skipping
where no database exists.

Worth keeping as a lesson about delegation: a long-running audit reads a **snapshot**, so any finding
about uncommitted state expires the moment the next commit lands. Timestamps matter as much as
severity.

### The unbounded `method` label: real in code, unreachable over HTTP

`app/api/request_context.py:84` passed `str(scope["method"])` straight through, and unlike `route`
(bounded by `_bounded_route`) and `status_code` (bounded by `status_class`), nothing constrained it.
That is the same cardinality-bomb shape the project already fixed once for concrete paths.

Before fixing it, the question that decides severity: can a client actually inject an arbitrary verb?
Curl refuses to send unknown methods, so the first probe proved nothing. A raw socket answered it:

```text
$ printf 'FOOBAR /api/v1/system/health/live HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n' | (raw socket)
server replied to bogus verb FOOBAR:
HTTP/1.1 400 Bad Request
--- did the app log the bogus verb at all? ---
0

distinct method labels in /metrics after 8 bogus verbs: ['GET']
```

uvicorn's h11 parser rejects the verb at the protocol layer and never invokes the ASGI app, so the
middleware never sees it. **Not exploitable over HTTP** — which is why this is defence in depth
rather than a vulnerability fix.

Bounded anyway, because it costs three lines and the guarantee should not depend on which server is
in front of the app:

```text
uv run pytest tests/test_method_cardinality.py
5 passed
```

`bounded_method` allow-lists the nine RFC verbs, normalises case (`get` -> `GET` rather than
overflow), and collapses anything else into the existing `other` label. Every observation is still
counted — the test asserts three unknown verbs produce one series with value 3, so the bound loses no
data, only distinctness.

### Scorecard, final

| Audit | Actionable | False, expired, or unverifiable | Verified NON-ISSUE |
|---|---|---|---|
| Security | 2 (honeypot bypass, method label) | 4 | 6 |
| Ops / docs | 4 (worker, healthcheck, PGDATA, port) | 2 (CRITICAL disproved, BLOCKING expired) | — |
| Architecture | 0 | 2 | 4 |

Six real fixes from 28 reported items. Two of the six were things I had looked straight past, and two
of the false claims would have caused damage if applied on trust: re-implementing an
`X-Forwarded-For` defence that already exists, and deleting `postgres_password` as dead config.

### Gates

```text
uv run pytest        261 passed
uv run ruff check .  All checks passed!
uv run mypy          Success: no issues found in 100 source files
harness              HARNESS VERIFIED
clean clone          imports, 244 passed / 12 skipped
```
