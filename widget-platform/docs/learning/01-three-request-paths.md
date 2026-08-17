# Lesson 01 — One product, three different request paths

Do not begin with FastAPI decorators. Begin with the system before this product exists.

## 1. The system before

A company has a normal contact form on its own website:

```text
Browser on company.test
        |
        | POST /contact
        v
Backend on company.test
        |
        v
Database
```

One team controls the page, backend, deployment, and origin. The browser talks back to the same system that served the page. This is the comfort zone.

## 2. The wall

Now we sell the same form to 500 customers. Their pages run on 500 unrelated origins:

```text
acme.com ------\
globex.net -----+--> api.embedlead.local
shop.example ---/
```

Three failures appear immediately:

1. The browser can stop cross-origin JavaScript before the POST reaches our route. That is the CORS/preflight wall.
2. Even when the request arrives, its body and claimed identity come from the public internet. That is the trust-boundary wall.
3. If Acme changes a widget ID and receives Globex's data, authentication succeeded but authorization failed. That is the tenant-isolation wall.

## 3. The naive fix that is not enough

“Set CORS to `*`” only changes a browser permission decision. It does not:

- authenticate a widget owner;
- stop curl, scripts, or bots;
- validate fields;
- limit traffic;
- prove who owns a widget;
- stop cross-tenant database queries.

CORS is one guard at one boundary. It is not a security system.

## 4. The resolution: separate the three paths

### Architecture altitude

```text
PATH A — OWNER ADMINISTRATION
owner -> JWT -> tenant context -> widget service -> tenant-scoped SQL

PATH B — PUBLIC DELIVERY
customer page -> versioned script -> public config -> safe renderer

PATH C — PUBLIC SUBMISSION
visitor -> CORS/validation -> abuse controls -> enrichment -> durable lead
```

These paths have different trust levels, cache behavior, and failure semantics. Combining them into one “widget controller” would hide those differences.

### Flow altitude: a concrete visitor submission

```text
1. Browser page:       http://localhost:5500/customer.html
2. API origin:         http://localhost:8000
3. Browser preflight:  OPTIONS /api/v1/public/widgets/7f.../submissions
4. API policy reply:   this origin/method/header set is allowed
5. Browser sends:      POST JSON {email, name, message, website: ""}
6. Pydantic checks:    types, lengths, required fields
7. Service checks:     widget active, honeypot empty, traffic allowed
8. Geo adapter:        provider A -> provider B -> empty geo
9. Database commits:   submission + notification outbox event
10. API returns:       202 Accepted
11. Worker later:      attempts notification independently
```

Step 9 is the product promise. Step 11 is optional work. If step 11 fails, undoing step 9 would lose a valid lead because an email provider was down.

### Code altitude: responsibility map

```python
# Route: HTTP boundary only
@router.post("/{public_id}/submissions", status_code=202)
def submit(public_id: UUID, body: SubmissionCreate, service: SubmissionServiceDep):
    return service.accept(public_id=public_id, body=body)

# Service: business outcome and ordering
class SubmissionService:
    def accept(self, *, public_id: UUID, body: SubmissionCreate):
        # widget lookup -> abuse decision -> enrichment -> durable transaction
        ...

# Repository: tenant/widget-scoped persistence only
class SubmissionRepository:
    def add_with_outbox(self, *, submission: Submission, event: OutboxEvent):
        # both rows commit together or neither does
        ...
```

The final code will be written through tests, not copied from this shape. This map tells us where decisions belong.

## 5. What this unlocks

- Owner endpoints can require identity and tenant authorization.
- Public config can be aggressively minimized and cached.
- Public submission can be hardened without slowing authenticated CRUD unnecessarily.
- Tests can attack each boundary independently.
- Optional providers can be replaced without changing HTTP or SQL policy.

## 6. The new wall

Separating the paths creates distributed failure boundaries:

- a Redis outage affects rate limiting;
- a geo provider can hang;
- a broker can be unavailable after the lead commits;
- a worker may run a notification twice;
- cached public config can become stale.

Those are not reasons to merge the paths again. They tell us the next mechanisms we need: timeouts, fallback, transactional outbox, idempotent tasks, and explicit cache policy.

## 7. Rebuild it from memory

Do not reopen the explanation until you answer these.

1. Draw the original same-origin contact form, then draw the 500-customer version. Name the three new walls.
2. Explain why permissive CORS does not stop a bot using curl.
3. Draw the owner, delivery, and submission paths. Mark where identity becomes trusted.
4. A geo provider times out after the visitor submits valid data. What must happen and why?
5. Write the two database facts that should commit together when accepting a lead.
6. Explain why `tenant_id` in an owner's JSON body cannot be authoritative.

<details>
<summary>Check your reconstruction</summary>

- The walls are browser cross-origin policy, hostile public input/abuse, and tenant authorization.
- CORS is enforced by browsers; a direct HTTP client is not constrained by it.
- Only the owner path establishes authenticated tenant identity. Delivery and submission remain public.
- Geo failure degrades to missing geo; the valid lead remains accepted.
- Submission and durable outbox intent commit in one transaction.
- Tenant authority comes from the verified token plus server-side membership, not client-controlled data.

</details>
