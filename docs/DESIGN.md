# Design — EmbedLead Widget Platform

Status: draft for Phase 1 review. This document is the contract we will implement, not a description written after implementation.

## 1. Problem

A widget owner needs to configure a small lead-capture widget, paste one script tag into an unrelated website, and receive submissions safely. The backend accepts requests from browsers and visitors it does not control. It must preserve tenant isolation, survive invalid or abusive traffic, and continue accepting valid leads when optional dependencies fail.

## 2. Actors and trust boundaries

| Actor/system | What it may do | What the server trusts |
|---|---|---|
| Widget owner | Manage widgets and inspect leads | Only identity proven by a valid server-verified token |
| Customer website | Load public widget code/config | Nothing about ownership; its origin is policy input only |
| Visitor/browser | Submit public lead data | Nothing until boundary validation and abuse checks pass |
| Geo providers | Return location guesses | Nothing until response shape is validated; availability is optional |
| Notification provider | Deliver email/webhook | Delivery result only; it cannot decide whether a lead exists |
| PostgreSQL | Hold durable source-of-truth state | Constraints and committed transaction results |
| Redis | Counters and task transport | Disposable; never the only copy of a lead |

Critical distinction: CORS controls whether browser JavaScript may read/call across origins. It does not authenticate the visitor, prove widget ownership, or stop curl/bots.

## 3. The three request paths

### 3.1 Owner administration

```text
Bearer token -> authentication -> tenant context -> route validation
             -> service authorization -> tenant-scoped repository -> PostgreSQL
```

A client never chooses the authoritative tenant ID. It is derived from authenticated membership and carried through every widget/submission query.

### 3.2 Public delivery

```text
<script src="/widget.v1.js?id=PUBLIC_ID">
  -> long-lived immutable JavaScript asset
  -> GET public widget config by opaque public ID
  -> short-lived cacheable JSON
  -> render with DOM APIs
```

Only publishable fields cross this boundary. Internal IDs, tenant IDs, provider configuration, and owner data must not appear in public config.

### 3.3 Public submission

```text
OPTIONS preflight (when browser requires it)
  -> POST bounded JSON
  -> Pydantic shape validation
  -> widget lookup
  -> per-IP and per-widget rate limits
  -> honeypot spam decision
  -> geo A -> geo B -> empty geo
  -> transaction: insert submission + durable notification intent
  -> success response
  -> worker performs notification and retries independently
```

## 4. Core data model

### Tenant

- `id UUID PRIMARY KEY`
- `name VARCHAR(120) NOT NULL`
- `created_at TIMESTAMPTZ NOT NULL`

### Membership

- `tenant_id UUID NOT NULL REFERENCES tenant(id)`
- `user_id UUID NOT NULL REFERENCES user(id)`
- `role VARCHAR(30) NOT NULL`
- primary key `(tenant_id, user_id)`

The membership connects identity to tenant authority. A global `user.tenant_id` would make future multi-organization membership unnecessarily difficult.

### Widget

- `id UUID PRIMARY KEY` — internal identity
- `public_id UUID UNIQUE NOT NULL` — safe public lookup identifier
- `tenant_id UUID NOT NULL REFERENCES tenant(id)`
- `name VARCHAR(120) NOT NULL`
- `kind VARCHAR(30) NOT NULL`
- `title VARCHAR(160) NOT NULL`
- `description VARCHAR(500)`
- `button_text VARCHAR(80) NOT NULL`
- `fields JSONB NOT NULL`
- `is_active BOOLEAN NOT NULL DEFAULT true`
- `created_at`, `updated_at TIMESTAMPTZ NOT NULL`

Indexes/constraints:

- index `(tenant_id, created_at DESC, id DESC)` for owner lists
- unique `(tenant_id, name)` to prevent ambiguous dashboard names
- check that `kind` is one of the implemented widget kinds

### Submission

- `id UUID PRIMARY KEY`
- `widget_id UUID NOT NULL REFERENCES widget(id)`
- `tenant_id UUID NOT NULL REFERENCES tenant(id)` — deliberately duplicated for direct tenant-scoped analytics and defence in depth
- `payload JSONB NOT NULL`
- `country_code VARCHAR(2)`
- `city VARCHAR(120)`
- `ip_hash VARCHAR(64)` — avoid retaining the raw address after enrichment unless the final policy requires it
- `user_agent VARCHAR(512)`
- `created_at TIMESTAMPTZ NOT NULL`

Indexes:

- `(tenant_id, created_at DESC, id DESC)` for dashboard pagination
- `(tenant_id, widget_id, created_at DESC)` for per-widget analytics

### OutboxEvent

- one row in the same transaction as an accepted submission
- event type `submission.notification.requested`
- payload references IDs, not secrets
- status/attempt fields support worker retries and evidence

The outbox closes the failure gap where PostgreSQL commits the lead but the process crashes before enqueueing the notification.

## 5. API contract

Prefix: `/api/v1`.

### Authenticated owner API

| Method/path | Success | Purpose |
|---|---:|---|
| `POST /widgets` | 201 | Create widget in authenticated tenant |
| `GET /widgets` | 200 | Cursor-paginated tenant widget list |
| `GET /widgets/{id}` | 200 | Read tenant widget |
| `PATCH /widgets/{id}` | 200 | Partial update |
| `DELETE /widgets/{id}` | 204 | Delete/deactivate according to final retention decision |
| `GET /widgets/{id}/embed` | 200 | Return script snippet |
| `GET /dashboard/submissions` | 200 | Cursor-paginated tenant lead list |
| `GET /dashboard/stats` | 200 | Counts over time, per-widget, and geo breakdown |

### Public API

| Method/path | Success | Purpose |
|---|---:|---|
| `GET /public/widgets/{public_id}/config` | 200 | Publish minimal cacheable config |
| `POST /public/widgets/{public_id}/submissions` | 202 | Accept a valid submission |
| `OPTIONS /public/widgets/{public_id}/submissions` | 200/204 | Browser preflight handled by CORS middleware |
| `GET /assets/widget.v1.js` | 200 | Immutable versioned loader/bundle |

`202 Accepted` means the lead is durably stored and the non-critical notification is pending; it does not claim the email/webhook was delivered.

### Error envelope

```json
{
  "detail": "Request validation failed",
  "code": "VALIDATION_ERROR",
  "errors": [],
  "request_id": "..."
}
```

Stable mappings:

- 400 malformed protocol-level input
- 401 missing/invalid identity
- 403 authenticated but not authorized
- 404 absent resource, including cross-tenant object access where hiding existence is appropriate
- 413 body too large
- 422 valid JSON with invalid fields
- 429 rate limited, with `Retry-After`
- 500 generic internal error; details remain in correlated logs

## 6. Security and abuse cases

| Abuse case | Design response | Required proof |
|---|---|---|
| Owner changes ID to another tenant's widget | tenant-scoped query/service authorization | two-tenant negative test |
| Bot bypasses browser/CORS | server-side rate limit, validation, honeypot | direct HTTP burst/spam tests |
| Oversized JSON exhausts memory | proxy/ASGI body limit before parsing | 413 test |
| Fake forwarded IP evades limiter | trust proxy headers only from configured proxy; otherwise socket peer | forged-header test |
| Script renders attacker-controlled HTML | fixed DOM construction with `textContent`, not `innerHTML` | XSS payload rendering test |
| Provider hangs | strict connect/read timeouts and bounded fallback | timeout/fallback test |
| Notification throws | outbox worker failure cannot roll back lead | failure test plus stored row |
| Error leaks internals | global stable error boundary | forced exception test |
| Cache leaks tenant/private fields | dedicated public response schema | contract test for field allowlist |

## 7. Failure semantics

- PostgreSQL unavailable: submission fails safely; never claim acceptance without durable storage.
- Redis limiter unavailable: local development may fail open; production must make the policy explicit. Core design preference is fail closed for the hostile public submission endpoint once production mode is used.
- Geo A unavailable/invalid/slow: attempt B.
- Geo A and B unavailable: store without geo and return acceptance.
- Broker unavailable after commit: outbox remains pending and a dispatcher retries.
- Notification provider unavailable: worker retries with bounded exponential backoff and records terminal failure.

## 8. Architecture boundaries

```text
API route
  owns HTTP parsing, response schemas, dependencies, status/headers
      -> service
         owns authorization, orchestration, business outcomes
             -> repository
                owns tenant-scoped SQL and transaction primitives

Infrastructure adapters
  own Redis, geo HTTP clients, notification provider, and queue details
```

We will not create an interface for every class. A boundary earns an abstraction when tests need a deterministic external dependency or when multiple implementations exist (geo A/B is a real example).

## 9. Definition-of-Done mapping

The implementation order is vertical rather than layer-by-layer:

1. Health/startup tracer — Compose, app, Postgres migration, stable errors.
2. Tenant/widget tracer — authenticate, create, read, and prove cross-tenant denial.
3. Submission tracer — valid cross-origin lead stored with no optional integrations.
4. Abuse tracer — size limit, rate limit, honeypot.
5. Enrichment tracer — A, fallback B, both down.
6. Notification tracer — transactional outbox, worker success/failure/retry.
7. Delivery tracer — versioned script, cacheable public config, second-origin page.
8. Dashboard tracer — tenant list and aggregate statistics.
9. Submission pack and six-minute demo rehearsal.

Each tracer uses RED -> GREEN -> REFACTOR and adds its real output to `EVIDENCE.md`.

## 10. Explicit non-goals

Until the core acceptance probes are green:

- no Kubernetes, cloud deployment, real CDN, or custom domain
- no microservices
- no sharding/read replicas
- no WebSockets/SSE
- no CAPTCHA or proof-of-work
- no form-builder UI
- no arbitrary customer webhook URLs (avoids an unnecessary SSRF surface)
- no stored raw geo-provider response
- no advanced RBAC beyond tenant owner/member needs

These omissions are senior scope control, not missing ambition. Additions require a failing requirement, measured bottleneck, or accepted stretch-goal decision.
