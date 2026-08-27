# Capstone compliance matrix

Traceability from the capstone brief to this repository. Every row maps a brief requirement to its current status and to the evidence that proves it. `EVIDENCE.md` holds the pasted proofs; this file exists so no requirement can be silently skipped.

Status values:

- `DONE` — implemented and proven by pasted evidence.
- `PARTIAL` — implemented in part; the gap is stated.
- `TODO` — not started.

## Section 11 — required submission pack

| File | Status | Note |
|---|---|---|
| `README.md` | PARTIAL | Architecture sketch, run steps, and API docs present; seed step and limitations section pending. |
| `capstone.yaml` | PARTIAL | `run`, `test`, `base_url`, and endpoints declared; `seed` is `NOT_IMPLEMENTED_YET` until the seed command exists. |
| `EVIDENCE.md` | PARTIAL | Filled per completed slice. |
| `BUILDLOG.md` | PARTIAL | Maintained per slice. |
| `.env.example` | DONE | Placeholder values only; no secrets. |
| `LICENSE` | DONE | MIT. |
| `.gitignore` | DONE | Excludes `.env`, virtualenv, caches, and private learning material. |
| Public repo, incremental history | DONE | Nine commits, one per working slice, no force-push. |

## Section 4 — the five moving parts

| # | Part | Status | Gap |
|---|---|---|---|
| 1 | Widget management API (tenant-isolated CRUD + auth) | DONE | Create, read, list, patch, delete all tenant-scoped and proven. |
| 2 | Embed snippet generation | TODO | Per-widget `<script>` line not yet returned. |
| 3 | Fast cached widget delivery | TODO | No config endpoint, no versioned bundle, no cache headers. |
| 4 | Public submission endpoint | DONE | CORS + preflight, boundary validation, 413 guard, tenant-linked storage, all proven. |
| 5 | Protection, enrichment, safe side effects | PARTIAL | Rate limiting and honeypot done and proven; geo chain and safe side effect still TODO. |
| 6 | Owner dashboard API | TODO | No submission list or analytics. |

## Section 6 — definition of done

### Widget management

| Box | Status | Evidence |
|---|---|---|
| Authenticated CRUD; unauthenticated rejected | DONE | `EVIDENCE.md` widget lifecycle; 401 without token. |
| Tenant A cannot read or modify tenant B's widgets | DONE | Foreign GET/PATCH/DELETE all return 404. |
| Tenant isolation for **submissions** | TODO | Submissions do not exist yet. |
| Embed snippet generated per widget | TODO | — |

### Widget delivery

| Box | Status |
|---|---|
| Public config endpoint with correct cache headers | TODO |
| Versioned JavaScript bundle (new version = new URL) | TODO |
| Widget renders on a page from a different origin | TODO |

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
| Provider A down → provider B enriches | TODO |
| All providers down → submission still succeeds without geo | TODO |
| Failing confirmation email/webhook does not prevent storage | TODO |

### Tests and documentation

| Box | Status | Note |
|---|---|---|
| Tests cover CORS preflight, invalid payload, oversized payload, rate limiting, spam control, provider fallback, widget rendering | TODO | 29 tests exist but none of these seven cases yet. |
| README with architecture diagram, setup, API docs | PARTIAL | Diagram and API docs present; seed and limitations pending. |
| Five submission-pack files present | PARTIAL | `LICENSE` missing; `capstone.yaml` seed pending. |

## Section 12 — acceptance probes

| Probe | What it checks | Status |
|---|---|---|
| 1 | Valid submission from second-origin page → stored, 2xx, visible in dashboard | TODO |
| 2 | Malformed and oversized payload → clean 4xx JSON, never 500 | DONE |
| 3 | Burst → 429s appear, normal request right after still succeeds | DONE |
| 4 | Geo A down → B enriches; both down → stored without geo | TODO |
| 5 | Email/webhook side effect throws → submission still succeeds and is stored | TODO |
| 6 | Honeypot filled → submission silently dropped or rejected | DONE |

## Section 12 — eight shared requirements

| # | Requirement | Status | Note |
|---|---|---|---|
| 1 | Layered architecture (data / logic / HTTP separated) | DONE | Routes, repositories, core, models are distinct; core auth holds no HTTP or storage wiring. |
| 2 | Validation at the boundary → clean 4xx, never 500 | PARTIAL | Proven on owner routes; public path pending. |
| 3 | ≥1 background job, off the request path, retries + failure alert | TODO | Largest unstarted requirement. Needed for the email/webhook side effect. |
| 4 | Real persistence: migrations, right indexes, isolated tenants | DONE | Three Alembic migrations; composite indexes; tenant predicates in SQL. |
| 5 | Idempotency where it matters — retried action happens once | TODO | Needed so a retried submission or notification does not duplicate. |
| 6 | Secrets clean — env only, never logged | DONE | `.env` ignored, `.env.example` placeholders, production rejects the development key. |
| 7 | Cost tracked if AI is used | N/A | No AI feature in this system. |
| 8 | Tests that matter — the scary cases, deterministic | PARTIAL | Auth/tenant/CORS/oversized/abuse cases covered with an injected clock; dependency-failure cases pending. |

## Known defects found during compliance review

| Defect | Impact | Status |
|---|---|---|
| `BACKEND_CORS_ORIGINS` declared in `.env.example` with no settings field and no middleware, silently discarded by `extra="ignore"` | Implied a security control that did not exist | Fixed — settings field + `CORSMiddleware` added, proven by preflight transcript |
| Compose passed no `BACKEND_CORS_ORIGINS`, so CORS was absent in the container even though tests passed via `conftest.py` | Tests green while the shipped artifact had no CORS at all — caught only by runtime proof | Fixed — compose now sets the variable; re-verified in-container |
| Test fixtures used the reserved `.test` TLD, which `email-validator` rejects | Tests would fail for the wrong reason | Fixed — fixtures use `example.com` |
| `EVIDENCE.md` "Widget management" section listed login, memberships, and update/delete/list as PENDING although implemented | Stale evidence contradicted itself and understated completed work | Fixed — cross-referenced to the proving sections |
| `capstone.yaml` declared a `seed:` command that does not exist | An evaluator running it would hit an error | Fixed — now `NOT_IMPLEMENTED_YET` |
| Composite widget index exists but plan shows a sequential scan at six rows | Index usage unproven | Open — re-measure on realistic data |

## Remaining build order

1. Public submission core: CORS settings + middleware, boundary validation, size guard, storage, tenant linkage.
2. Abuse protection: per-IP and per-widget rate limiting, honeypot.
3. Geo enrichment with provider fallback chain, mocked deterministically in tests.
4. Background job + idempotency for the safe side effect.
5. Widget delivery: config endpoint with cache headers, versioned bundle, second-origin test page.
6. Embed snippet generation.
7. Dashboard API with aggregation queries.
8. Seed command, `LICENSE`, README limitations, full evidence pass.
