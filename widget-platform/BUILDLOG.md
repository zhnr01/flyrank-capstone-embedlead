# Build log

This file records decisions, misunderstandings, AI assistance, corrections, and evidence of ownership. Entries are appended per working session.

## Session 1 — Phase 1 reconnaissance and architecture

### What was inspected

- The 12-page capstone brief and its Definition of Done.
- Existing backend notes and visual lessons.
- The production FastAPI reference structure, dependencies, Compose topology, and route-service-repository example.
- Local tooling: Python 3.14 is installed; Docker and Docker Compose are available.

### Decisions

- Build in `widget-platform/`; do not edit the reference boilerplate.
- Docker is the authoritative runtime.
- Local JWT authentication is sufficient for the core.
- Build the required core before stretch goals.
- Use static teaching diagrams only; no interactive HTML.
- Follow contract-first, threat-model-first, and test-first development.

### Where AI helped

- Extracted and mapped capstone requirements to backend concepts.
- Compared the capstone needs with the reference boilerplate's existing patterns.
- Drafted the initial request-path and trust-boundary model.

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
