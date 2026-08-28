# Capstone compliance matrix

Traceability from the capstone brief to this repository. Every row maps a brief requirement to its current status and to the evidence that proves it. `EVIDENCE.md` holds the pasted proofs; this file exists so no requirement can be silently skipped.

Status values:

- `DONE` — implemented and proven by pasted evidence.
- `PARTIAL` — implemented in part; the gap is stated.
- `TODO` — not started.

## Section 11 — required submission pack

| File | Status | Note |
|---|---|---|
| `README.md` | DONE | Architecture sketch, run steps, seed step, per-endpoint API docs, and an honest limitations section. |
| `capstone.yaml` | DONE | `run`, `seed`, `test`, `base_url`, worker command, demo page, and endpoints all declared and real. |
| `EVIDENCE.md` | DONE | Pasted runtime proof per slice, including the acceptance probes. |
| `BUILDLOG.md` | DONE | Maintained per slice, including mistakes and corrections. |
| `.env.example` | DONE | Placeholder values only; no secrets. |
| `LICENSE` | DONE | MIT. |
| `.gitignore` | DONE | Excludes `.env`, virtualenv, caches, and private learning material. |
| Public repo, incremental history | DONE | One commit per working slice, no force-push. |

## Section 4 — the five moving parts

| # | Part | Status | Gap |
|---|---|---|---|
| 1 | Widget management API (tenant-isolated CRUD + auth) | DONE | Create, read, list, patch, delete all tenant-scoped and proven. |
| 2 | Embed snippet generation | DONE | `GET /api/v1/widgets/{id}/embed` returns the tenant-scoped `<script>` line. |
| 3 | Fast cached widget delivery | DONE | Config with content-hash ETag and 304 revalidation; versioned bundle with a one-year immutable policy. |
| 4 | Public submission endpoint | DONE | CORS + preflight, boundary validation, 413 guard, tenant-linked storage, all proven. |
| 5 | Protection, enrichment, safe side effects | DONE | Rate limiting, honeypot, geo fallback chain, and transactional-outbox side effect all proven. |
| 6 | Owner dashboard API | DONE | Tenant-scoped submission list with cursor pagination plus aggregation stats. |

## Section 6 — definition of done

### Widget management

| Box | Status | Evidence |
|---|---|---|
| Authenticated CRUD; unauthenticated rejected | DONE | `EVIDENCE.md` widget lifecycle; 401 without token. |
| Tenant A cannot read or modify tenant B's widgets | DONE | Foreign GET/PATCH/DELETE all return 404. |
| Tenant isolation for **submissions** | DONE | `tenant_id` derived from the addressed widget row; verified in SQL that every submission's tenant matches its widget's tenant. |
| Embed snippet generated per widget | DONE | Absolute configured URL, `data-widget-id`, `async`; foreign widget returns 404. |

### Widget delivery

| Box | Status |
|---|---|
| Public config endpoint with correct cache headers | DONE |
| Versioned JavaScript bundle (new version = new URL) | DONE |
| Widget renders on a page from a different origin | DONE |

### Public submission API

| Box | Status |
|---|---|
| Cross-origin submissions work; preflight handled | DONE |
| All input validated; malformed and oversized rejected with 4xx JSON, never 500 | DONE |
| Valid submissions stored, linked to the right widget and tenant | DONE |

### Abuse protection

| Box | Status |
|---|---|
| Rate limiting returns 429 under burst; legitimate traffic still served | DONE |
| At least one spam control demonstrably blocks a spam submission | DONE |

### Enrichment and safe side effects

| Box | Status |
|---|---|
| Provider A down → provider B enriches | DONE |
| All providers down → submission still succeeds without geo | DONE |
| Failing confirmation email/webhook does not prevent storage | DONE |

### Tests and documentation

| Box | Status | Note |
|---|---|---|
| Tests cover CORS preflight, invalid payload, oversized payload, rate limiting, spam control, provider fallback, widget rendering | DONE | All seven cases covered across 135 tests; the rendering case is proven by the second-origin browser transcript in `EVIDENCE.md`. |
| README with architecture diagram, setup, API docs | DONE | Diagram, run steps, seed step, per-endpoint docs, and an honest limitations section. |
| Five submission-pack files present | DONE | `README.md`, `capstone.yaml`, `EVIDENCE.md`, `BUILDLOG.md`, `.env.example`, plus `LICENSE`. |

## Section 12 — acceptance probes

| Probe | What it checks | Status |
|---|---|---|
| 1 | Valid submission from second-origin page → stored, 2xx, visible in dashboard | DONE |
| 2 | Malformed and oversized payload → clean 4xx JSON, never 500 | DONE |
| 3 | Burst → 429s appear, normal request right after still succeeds | DONE |
| 4 | Geo A down → B enriches; both down → stored without geo | DONE |
| 5 | Email/webhook side effect throws → submission still succeeds and is stored | DONE |
| 6 | Honeypot filled → submission silently dropped or rejected | DONE |

## Section 12 — eight shared requirements

| # | Requirement | Status | Note |
|---|---|---|---|
| 1 | Layered architecture (data / logic / HTTP separated) | DONE | Routes, repositories, core, models are distinct; core auth holds no HTTP or storage wiring. |
| 2 | Validation at the boundary → clean 4xx, never 500 | DONE | Owner and public paths both return 4xx JSON for malformed, oversized, unknown-field, and unknown-resource cases. |
| 3 | ≥1 background job, off the request path, retries + failure alert | DONE | Transactional outbox plus `python -m app.worker`; bounded attempts, dead-letter status with `last_error` recorded. |
| 4 | Real persistence: migrations, right indexes, isolated tenants | DONE | Six Alembic migrations; composite indexes; tenant predicates in SQL. |
| 5 | Idempotency where it matters — retried action happens once | DONE | Derived idempotency key with a database unique constraint; duplicate enqueue is a no-op, proven at runtime. |
| 6 | Secrets clean — env only, never logged | DONE | `.env` ignored, `.env.example` placeholders, production rejects the development key. Webhook secret signs via HMAC and is never transmitted or logged, asserted by test. |
| 7 | Cost tracked if AI is used | N/A | No AI feature in this system. |
| 8 | Tests that matter — the scary cases, deterministic | DONE | 212 tests: auth, tenant isolation, CORS, oversized, abuse with an injected clock, provider failure, real webhook failure, caching/304, dashboard scoping, metrics auth and cardinality bounds. Determinism verified by repeated full-suite runs, not assumed. |

## Observability (shared requirement: operators can see it working)

| Requirement | Status | Evidence |
|---|---|---|
| Structured logs with a correlation id | DONE | JSON formatter; `request_id` on every line including `uvicorn.access`; container transcript in `EVIDENCE.md`. |
| Caller-supplied correlation id is propagated but not trusted | DONE | Short alphanumeric ids echoed; hostile values replaced with a UUID, proven for newline, whitespace, script-tag, and over-long payloads. |
| Sensitive values never logged | DONE | Redaction set covers password, secret, token, authorization, signature, email, api_key; container `grep` for the operator token and the lead email both return 0. |
| RED signals available to an operator | DONE | Request counts by status class, latency histograms with p50/p95/p99, and named event counters for rate limiting, honeypot, geo, and outbox. |
| Monitoring endpoint is access-controlled and fails closed | DONE | `404` with no token configured, `401` on missing/wrong token, constant-time comparison. |
| Metric label cardinality is bounded | DONE | Route templates not paths; single `unmatched` series; `METRICS_MAX_ROUTES` cap with reserved overflow budget and reported `overflowed`. |

## Known defects found during compliance review

| Defect | Impact | Status |
|---|---|---|
| Payload size guard bypassable by omitting `Content-Length`; a route dependency also runs after FastAPI has already buffered the body | Remote unauthenticated memory pressure; a 610x oversized body was accepted and stored | FIXED — `BodySizeLimitMiddleware` bounds bytes as they stream; runtime proof in `EVIDENCE.md` |
| `SqlAlchemyOutboxRepository.enqueue` called `session.rollback()` on a duplicate idempotency key, discarding the uncommitted submission sharing that session | **Silent data loss** — API returned `202 Accepted` and the lead was never stored | FIXED — SAVEPOINT isolates the duplicate insert; RED/GREEN + runtime proof in `EVIDENCE.md` |
| `BACKEND_CORS_ORIGINS` declared in `.env.example` with no settings field and no middleware, silently discarded by `extra="ignore"` | Implied a security control that did not exist | Fixed — settings field + `CORSMiddleware` added, proven by preflight transcript |
| Compose passed no `BACKEND_CORS_ORIGINS`, so CORS was absent in the container even though tests passed via `conftest.py` | Tests green while the shipped artifact had no CORS at all — caught only by runtime proof | Fixed — compose now sets the variable; re-verified in-container |
| Test fixtures used the reserved `.test` TLD, which `email-validator` rejects | Tests would fail for the wrong reason | Fixed — fixtures use `example.com` |
| `EVIDENCE.md` "Widget management" section listed login, memberships, and update/delete/list as PENDING although implemented | Stale evidence contradicted itself and understated completed work | Fixed — cross-referenced to the proving sections |
| `capstone.yaml` declared a `seed:` command that does not exist | An evaluator running it would hit an error | Fixed — seed command implemented and verified |
| `/metrics` was initially unauthenticated | Published error rates, latency, and honeypot hit counts to anyone — a map of where the system is weak | Fixed — operator token with `compare_digest`, and `404` when unconfigured, proven against a token-less container |
| Metric labels initially came from the concrete request path | Cardinality bomb: walking `/widgets/{id}` would allocate one series per id | Fixed — route templates plus a reserved-budget `METRICS_MAX_ROUTES` cap with reported overflow |
| The series cap did not budget for its own overflow rows | A cap of 4 actually settled at 6, so the bound did not hold | Fixed — overflow budget reserved up front; caught by an abuse test, not by review |
| `X-Request-ID` was echoed after only a length check | Header and log injection via a caller-controlled value | Fixed — non-alphanumeric or long values replaced with a fresh UUID |
| README `Limitations` still claimed no widget, submission, auth, tenant, worker, or dashboard implementation existed | Directly contradicted the feature list in the same file | Fixed — rewritten to state the real operational limits |
| Composite widget index exists but plan shows a sequential scan at six rows | Index usage unproven | Open — re-measure on realistic data |
| Rate-limit counters and the metrics registry are in-process | Incorrect under horizontal scaling: limit becomes N x limit, metrics are per-instance | Open and documented — Redis required before multi-container |
| `test_tampered_access_token_is_rejected` flipped a token's last base64url character | Flaky ~1 run in 16: a 43-char signature has 2 bits of encoding slack, so `Y`→`a` decodes byte-identically and the token was never actually tampered with | Fixed — tampering now mutates the payload (forged `sub`), plus new wrong-key and `alg: none` cases; determinism proven by 20 auth runs and 5 full-suite runs |

## Remaining build order

The required core is complete and proven. Remaining items are scale and deployment work:

1. Shared state (Redis) for rate limiting and metrics so horizontal scaling is correct.
2. OpenMetrics exposition plus alert rules on the RED signals.
3. Supervised outbox worker with exponential backoff and dead-letter replay.
4. Re-measure the composite widget index on realistic row counts.
5. CI running ruff, strict mypy, and pytest; then a deployed environment with TLS and backups.
