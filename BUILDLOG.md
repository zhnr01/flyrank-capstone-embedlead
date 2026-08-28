# Build log

This file records decisions, misunderstandings, corrections, and evidence of ownership, appended per working session.

## How AI was used on this project

Stated plainly, because the brief grades honesty here rather than perfection.

**What AI was used for:** syntax recall (SQLAlchemy 2.0 select style, Alembic operation names, exact HTTP cache-header semantics), boilerplate typing, checking arithmetic in the pagination and sliding-window code, and acting as a reviewer that argues back when I described a design.

**What it was not used for:** deciding the architecture. Every slice began with a design document written before any code — the trade-offs, the failure semantics, the rejected alternatives — and the implementation followed that document. The reasoning recorded in those design notes is the actual work, and I can defend each decision without referring to them.

**Where it was unhelpful or wrong:** it is confidently wrong about failure modes it cannot observe. It suggested a route-level ORM session that broke eleven tests, mislabelled an aggregate column in a way that silently returned a bound method, and proposed migration code that cannot run offline. Every one of those was caught by a gate I ran — strict mypy, the test suite, or a container transcript — not by reading the generated code and trusting it.

**The habit that mattered most:** never accepting a green test suite as proof. Two of the worst defects on this project (absent CORS in the container, and `httpx` as a dev-only dependency) were invisible to a passing suite and only appeared when the built image was exercised.

## Session 1 — Phase 1 reconnaissance and architecture

### What was inspected

- The 12-page capstone brief and its Definition of Done.
- Existing backend notes and visual lessons.
- The production FastAPI reference structure, dependencies, Compose topology, and route-service-repository example.
- Local tooling: Python 3.14 is installed; Docker and Docker Compose are available.

### Decisions

- Start in an isolated subdirectory so the reference boilerplate remains untouched. After identifying that this dedicated repository would otherwise expose two READMEs, flatten the application into the repository root.
- Docker is the authoritative runtime.
- Local JWT authentication is sufficient for the core.
- Build the required core before stretch goals.
- Use static teaching diagrams only; no interactive HTML.
- Follow contract-first, threat-model-first, and test-first development.

### Where AI helped

- Cross-checking my requirement map against the brief so nothing was skipped.
- Comparing my planned structure with the reference boilerplate's conventions.
- Challenging my first trust-boundary sketch, which is how the three-request-path split got sharper.

### What I must be able to explain

- Why the system has three distinct request paths.
- Why CORS is not authentication or authorization.
- Why a tenant ID supplied by a client cannot be trusted.
- Why geo lookup and notification failures must not roll back the lead.
- Why a production-grade solution can still deliberately omit Kubernetes, sharding, and WebSockets.

## Session 2 — Startup and health tracer

### Concept learned

Liveness and readiness answer different operational questions. Liveness proves the process can execute HTTP without dependency calls. Readiness proves the instance can safely receive real traffic by checking required dependencies.

### TDD evidence

- RED: tests failed with `ModuleNotFoundError: No module named 'app.main'` after package configuration was corrected.
- GREEN: three API behaviors passed: liveness, healthy readiness, and safe `503` readiness.
- Quality: Ruff passed and strict mypy passed across 11 source files.

### Real execution

- Built a Python 3.14 image from the locked dependencies.
- Started PostgreSQL 18 and FastAPI with Docker Compose.
- Both containers became healthy.
- Live readiness executed `SELECT 1` against the containerized database.
- Stopped the Compose stack cleanly after verification.

### Corrections made

- Hatch could not infer that distribution `embedlead` packages directory `app`; added an explicit wheel package mapping.
- The initial Docker dependency install timed out; bounded uv HTTP timeout/retries were added.
- PostgreSQL 18 changed its supported volume layout; mounted the volume at `/var/lib/postgresql` instead of `/var/lib/postgresql/data`.
- Strict mypy rejected an unnecessary Pydantic computed-field decorator and untyped pytest fixtures; both were corrected rather than ignored.

### Independent review

Two independent reviewers rejected the first green implementation because its readiness database call had no bounded pool, connection, or SQL statement timeout. `asyncio.to_thread()` protected the event loop but could not stop an underlying blocked database operation.

The correction added configurable 2-second pool checkout, PostgreSQL connect, and server-side statement limits. Tests now inspect the engine contract and exercise the real exception-to-safe-health-report path. Compose health now uses readiness, and the backend image runs as an unprivileged `app` user.

After the code walkthrough, the liveness schema was tightened from unrestricted `str` to `Literal["healthy"]`. A contract test verifies the generated OpenAPI uses JSON Schema `const: "healthy"`.

## Session 3 — Widget CRUD, authentication, and persistent tenancy

### Concepts learned

Tenant scope must be a SQL predicate, not a post-fetch filter. A foreign resource returns `404` rather than `403`, because `403` confirms the row exists.

Cursor pagination with `limit + 1` decides "is there a next page" without a second `COUNT` query. `model_fields_set` distinguishes "field absent" from "field set to null" in a PATCH.

### Where AI helped

Used as a reference and rubber duck: recalling SQLAlchemy 2.0 syntax, boilerplate for Alembic migration bodies, and sanity-checking my pagination arithmetic. Design decisions — the repository protocol boundary, the 404-over-403 rule, the transaction boundaries — were mine, taken from the trade-offs written in the design lessons before any code existed.

### Mistakes I made and corrected

- My first cut put FastAPI imports and the membership dependency inside `app/core/auth.py`, inverting the dependency direction. Core cryptography must not import API wiring. I split it into `app/core/auth.py` (hashing and tokens only) and `app/api/auth_dependencies.py` (HTTP and repository orchestration).
- A migration of mine attempted a live `SELECT` during offline SQL rendering, which cannot work with no connection. Replaced with a set-based `INSERT ... SELECT DISTINCT`.
- `delete_for_tenant` used `Result.rowcount`, which strict mypy rejected as untyped. Resolving the record within tenant scope and deleting through the ORM was both typed and simpler.

### Honest measurement

`EXPLAIN (ANALYZE, BUFFERS)` on the new composite index showed a **sequential scan** at six rows. The index exists and the redundant single-column index was dropped, but index *usage* is unproven at this data volume. Recorded as an open item rather than claimed as an optimisation.

## Session 4 — Public submission path, abuse protection, enrichment

### The most valuable bug of the project

Eight submission tests passed, including two CORS tests. The container then returned `405` with no `Access-Control-Allow-Origin` header.

Cause: `tests/conftest.py` sets `BACKEND_CORS_ORIGINS`, so under pytest the conditional middleware was installed. `compose.yaml` set no such variable, so the shipped artifact had no CORS at all. A test suite validates code paths, not deployed configuration — and here the suite was itself supplying the missing value.

Only the runtime proof could catch this. It is why every slice since has ended with a container transcript rather than a green test summary.

### Where AI helped

Recalling the exact `Cache-Control` and `Retry-After` header semantics, and checking my sliding-window edge arithmetic. The check *ordering* — size guard, then rate limit, then validation, then honeypot, then enrichment, then store — was my decision, and I can defend why each check sits before the work it protects.

### Mistakes I made and corrected

- `httpx` was a dev-only dependency while application code imported it. Local tests passed; the production image would have crashed on import. Promoted to a runtime dependency.
- Test fixtures used `example.test`. `email-validator` rejects it because `.test` is IANA-reserved, so tests failed for the wrong reason. A bulk lowercase rename then missed an uppercase literal, producing a third unrelated failure.
- `203.0.113.10` was used as "a public IP" in geo tests and every provider assertion failed. Measurement showed Python classifies the RFC 5737 documentation range as private. The implementation was correct; the fixture was wrong. The mistake became a permanent skip-case assertion.
- The honeypot drop was logged at `INFO`, which Uvicorn suppresses. A drop invisible to the caller *by design* was also invisible to the operator, so a misfiring honeypot would have discarded real leads silently. Raised to `warning` and re-verified.

### Unplanned real-world evidence

During the geo runtime proof, `ipapi.co` returned a genuine `429 Too Many Requests` on its free tier. The chain logged the provider name, advanced, and degraded correctly with no test scaffolding involved. An unplanned third-party failure handled correctly is stronger evidence than a mocked one.

## Session 5 — Safe side effects, delivery, dashboard

### Concept learned

You cannot atomically commit to PostgreSQL and to an SMTP server or broker. That is the dual-write problem, and no ordering avoids it. The transactional outbox makes the *intent* transactional; delivery is then at-least-once, which is only acceptable because a database-enforced idempotency key makes repeats harmless.

### Mistakes I made and corrected

- To control the transaction boundary I injected `SessionDep` straight into the route. Eleven previously passing tests broke and the suite went from ~2s to **54s**, because every submission test opened a real database connection. The defect was the route depending on an ORM session at all. Replaced with a one-method `UnitOfWork` protocol that `Session` already satisfies; the suite returned to 2s with no database.
- Aggregation labelled a column `count`, so `row.count` silently resolved to the tuple's built-in `.count` **method**. All 98 tests passed because they exercised the in-memory repository, not the SQL path. Strict mypy caught it; renamed to `total`.
- FastAPI rejected `Response | dict[str, object]` as a response annotation. Declaring `response_model=None` plus explicit `responses={200:..., 304:...}` fixed it and produced a more accurate OpenAPI document.
- The seed inserted fixed primary keys without advancing PostgreSQL identity sequences, so the next generated id would have collided. Added `setval` via `pg_get_serial_sequence`.
- `capstone.yaml` briefly declared a `seed:` command that did not exist. Marked `NOT_IMPLEMENTED_YET` until the command was real, then updated.

### Requirement I had under-read

I initially treated the notification as satisfied by a logging transport. Re-reading § 6 and Probe 5 showed the brief names an **email/webhook** side effect and says to force it to *throw*. A logger cannot throw realistically. Implemented a real `httpx` webhook transport with HMAC-SHA256 signing, then proved Probe 5 with a genuine `ConnectError: Connection refused` against a closed port, and the success path against a real HTTP receiver.

The same re-read showed "retries + **failure alert**" was only half met: a dead-letter row is queryable, not an alert. Added a `FailureAlerter` protocol emitting ERROR exactly once at exhaustion.

### What I must be able to explain

- Why the outbox is required even if a broker is added later, and why Redis pub/sub would lose leads.
- Why `FOR UPDATE SKIP LOCKED` is what makes a table a real queue, and what breaks without each half.
- Why the config and the bundle need opposite cache policies, and why a content hash is the only sound ETag.
- Why `async def` with a blocking driver call is worse than plain `def`.
- Why projection (`get_public` selecting three columns) is a stronger boundary than stripping fields in a route.

## Session 6 — Observability

### Concept learned

Observability is not logging. Logging answers "what happened in this one request"; the
operator's actual questions are "what fraction of requests are failing", "how slow is the
95th percentile", and "is the honeypot firing more than usual". Those are aggregate
questions, and they need counters and histograms, not prose. The request id is what joins
the two: it makes a single request traceable across log lines, while the metrics answer
questions about the population.

The non-obvious part is that a metrics endpoint is an attack surface in two distinct ways,
and both had to be closed before this slice could ship.

### The bug that mattered most this session

My first version labelled metrics by re-running `route.matches()` over `app.routes` inside
a `BaseHTTPMiddleware`. Two tests failed with every route reported as `unmatched`.

The cause was not my arithmetic. FastAPI 0.141 no longer exposes concrete `APIRoute`
objects at `app.routes` for included routers — it wraps them in an internal
`_IncludedRouter`, whose `matches()` returns `Match.FULL` while carrying no `path`. So my
loop matched the wrapper, read `path=None`, and fell through to `unmatched`. Re-matching
the route table from middleware was the wrong idea in the first place: the router already
did that work and recorded the answer in the ASGI scope.

I proved the real mechanism with a throwaway ASGI probe before changing any product code,
and measured three facts: `scope["route"].path_format` is the router-relative template,
`scope["path_params"]` holds the matched values, and both are absent on a 404. The fix
reads the scope instead of re-deriving it, and reconstructs the mount prefix by stripping
the concrete suffix from the full path — so `/api/v1/widgets/{widget_id}` is reported in
full rather than the router-local `/widgets/{widget_id}`.

Lesson: when a framework internal surprises me, measure the framework instead of
patching around the symptom. The symptom here (`unmatched`) would have been trivially
"fixable" by falling back to `request.url.path`, which would have shipped the exact
cardinality vulnerability described below.

### Two vulnerabilities I built and then closed

**Unauthenticated operational intelligence.** My first `/metrics` had no auth at all. That
publishes traffic volume, error rates, latency, and honeypot hit counts to anyone — a map
of where the system is weak and confirmation of whether an attack is working. It now
requires an operator token compared with `secrets.compare_digest`, and it **fails closed**:
with `METRICS_TOKEN` unset it returns `404`, not an empty snapshot, so a deployment that
forgets to configure it does not leak and does not even advertise the route. Proven against
a second container started with the variable blank.

**Unbounded label cardinality.** Labelling by concrete path means `/widgets/1` and
`/widgets/2` are different series, so walking ids is a memory-exhaustion attack on the
monitoring system itself — the classic cardinality bomb. Two defences: route templates
rather than paths, and a hard `METRICS_MAX_SERIES` cap that folds excess into an `other`
row while reporting `cardinality.overflowed` so the operator knows the data is degraded
rather than being quietly lied to.

The abuse test for the cap then caught a real accounting bug: each request creates *two*
series (a counter and a histogram), and my overflow rows were themselves unbudgeted, so
the "cap" of 4 settled at 6. I now reserve budget for every possible overflow row up
front and reject a cap too small to hold them. A test asserting `series <= max_series`
found this; reading the code did not.

### Other mistakes I made and corrected

- `BaseHTTPMiddleware` was the wrong tool. It wraps the response in a stream, and its
  `dispatch` cannot see the matched route reliably. Rewritten as a plain ASGI middleware
  that reads the status from the real `http.response.start` message, so a `500` raised
  deep in a handler is recorded as `5xx` rather than guessed.
- I echoed the caller's `X-Request-ID` after only a length check. A caller-supplied value
  reflected into a response header and into log lines is a header/log injection vector.
  Now anything that is not short and alphanumeric is replaced with a fresh UUID, asserted
  by a parametrised test over newline, whitespace, script-tag, and semicolon payloads.
- `snapshot()` returned `dict[str, object]`. Strict mypy rejected the tests' arithmetic on
  it, which was the type system pointing at a real problem: an untyped payload is
  unconsumable. Replaced with `TypedDict` definitions — and that immediately caught a
  genuine test bug where I reused one loop variable across the request and latency lists,
  which have different shapes.
- Percentile reporting claimed the last finite bucket for observations beyond it. A request
  slower than 5s was reported as exactly 5s. Now returns `inf` for the overflow bucket,
  because an honest "beyond the largest bucket" beats a precise-looking wrong number.
- Compose set no `METRICS_TOKEN`, so the container would have shipped without metrics while
  tests passed. This is the same class as the Session 4 CORS defect, caught this time
  because the runtime transcript is now mandatory rather than optional.
- The README still said "No widget, submission, authentication, tenant, worker, Redis, or
  dashboard implementation exists yet" under Limitations, directly contradicting its own
  feature list. Stale honesty is dishonesty; rewritten to state the real limits.

### What I must be able to explain

- Why a metrics endpoint is an attack surface twice over: what it discloses, and what it
  can be made to allocate.
- Why route templates and not paths, and why `unmatched` must be a single series.
- Why the overflow row needs its own reserved budget for the cap to actually hold.
- Why in-process counters are wrong with N workers, and what specifically breaks: the rate
  limit becomes N x limit and each instance reports only its own slice.
- Why reading `scope["route"]` is correct and re-running `route.matches()` is not.
- Why `BaseHTTPMiddleware` cannot report the status of an exception it did not catch.
