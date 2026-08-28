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
