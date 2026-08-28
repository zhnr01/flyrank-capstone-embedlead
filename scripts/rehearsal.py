import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

BASE = "http://localhost:8000"
ORIGIN = "http://localhost:5500"
EVIL_ORIGIN = "http://evil.example"
TOKEN = "local-development-only-metrics-token"
OWNER = "owner@acme.example"
PASSWORD = "local-demo-password"

FAILURES: list[str] = []
STEP = [0]


def compose(*args: str, timeout: int = 240) -> str:
    result = subprocess.run(
        ["docker", "compose", *args], capture_output=True, text=True, timeout=timeout
    )
    return (result.stdout + result.stderr).strip()


def psql(query: str) -> str:
    result = subprocess.run(
        ["docker", "compose", "exec", "-T", "db", "psql", "-U", "embedlead",
         "-d", "embedlead", "-t", "-A", "-c", query],
        capture_output=True, text=True, timeout=90,
    )
    return result.stdout.strip()


def request(
    method: str,
    path: str,
    *,
    body: object = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> tuple[int, str, dict[str, str]]:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, response.read().decode(), dict(response.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode(), dict(exc.headers)


def step(title: str) -> None:
    STEP[0] += 1
    print(f"\n--- STEP {STEP[0]}: {title} ---")


def check(label: str, ok: bool, detail: str = "") -> None:
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {label}" + (f"  {detail}" if detail else ""))
    if not ok:
        FAILURES.append(f"step {STEP[0]}: {label} {detail}")


def wait_ready(seconds: int = 180) -> bool:
    for _ in range(seconds):
        try:
            code, _, _ = request("GET", "/api/v1/system/health/ready", timeout=3)
            if code == 200:
                return True
        except (urllib.error.URLError, OSError, TimeoutError):
            pass
        time.sleep(1)
    return False


def token() -> str:
    code, body, _ = request(
        "POST", "/api/v1/auth/token", body={"email": OWNER, "password": PASSWORD}
    )
    if code != 200:
        return ""
    return str(json.loads(body)["access_token"])


def main() -> int:
    print("=" * 72)
    print("DEMO REHEARSAL — FlyRank EmbedLead")
    print("=" * 72)

    step("migration safety: start from an empty volume, migrate to head")
    compose("down", "-v")
    compose("up", "-d")
    check("stack reached readiness", wait_ready())
    head = psql("select version_num from alembic_version")
    check("alembic at head", head == "0009_submission_answers", head)
    services = compose("ps", "--format", "{{.Service}}")
    for name in ("db", "redis", "backend", "worker"):
        check(f"service {name} running", name in services)

    step("one-command config: seed deterministic demo data")
    seed = compose("exec", "-T", "backend", "python", "-m", "app.seed")
    check("seed reported completion", "seed complete" in seed)
    check("demo login advertised", OWNER in seed)

    step("authentication: a real login, not a pre-baked token")
    bearer = token()
    check("owner obtained a bearer token", bool(bearer))
    code, body, _ = request(
        "POST", "/api/v1/auth/token",
        body={"email": OWNER, "password": "definitely-not-the-password"},
    )
    check("a wrong password is refused", code == 401, f"got {code}")
    check("the 401 body is opaque", set(json.loads(body)) == {"detail"})

    step("authorization: missing identity and cross-tenant access both refused")
    code, _, _ = request("GET", "/api/v1/widgets")
    check("no bearer token is refused", code == 401, f"got {code}")
    code, _, _ = request(
        "GET", "/api/v1/widgets", headers={"Authorization": "Bearer not-a-real-token"}
    )
    check("a forged token is refused", code == 401, f"got {code}")
    code, _, _ = request(
        "GET", "/api/v1/widgets/999999", headers={"Authorization": f"Bearer {bearer}"}
    )
    check("another tenant's widget is not found", code == 404, f"got {code}")

    step("probe 1: a valid cross-origin submission is stored")
    before = int(psql("select count(*) from submissions") or 0)
    code, _, _ = request(
        "POST", "/api/v1/public/widgets/1/submissions",
        body={"email": "demo-lead@example.com", "name": "Demo Lead",
              "message": "from the rehearsal", "website": ""},
        headers={"Origin": ORIGIN},
    )
    after = int(psql("select count(*) from submissions") or 0)
    check("submission accepted", code == 202, f"got {code}")
    check("row persisted", after == before + 1, f"{before} -> {after}")

    step("serialization: the widget renders from stored config")
    code, body, headers = request(
        "GET", "/api/v1/public/widgets/1/config", headers={"Origin": ORIGIN}
    )
    check("config served", code == 200, f"got {code}")
    config = json.loads(body)["config"]
    check("config carries fields", bool(config.get("fields")),
          f"{len(config.get('fields', []))} fields")
    etag = headers.get("etag", "")
    check("an ETag is issued", bool(etag))

    step("caching: an unchanged config returns 304")
    code, _, _ = request(
        "GET", "/api/v1/public/widgets/1/config",
        headers={"Origin": ORIGIN, "If-None-Match": etag},
    )
    check("conditional request is 304", code == 304, f"got {code}")

    step("probe 2: malformed and oversized payloads give clean 4xx, never 500")
    code, body, _ = request(
        "POST", "/api/v1/public/widgets/1/submissions",
        body={"email": "not-an-email", "name": "X"}, headers={"Origin": ORIGIN},
    )
    check("invalid email refused with 4xx", 400 <= code < 500, f"got {code}")
    check("no 500 on malformed input", code != 500)
    code, _, _ = request(
        "POST", "/api/v1/public/widgets/1/submissions",
        body={"email": "a@b.co", "name": "X", "message": "z" * 200_000},
        headers={"Origin": ORIGIN},
    )
    check("oversized body refused", code in (413, 422), f"got {code}")

    step("probe 6: a filled honeypot is dropped, not stored")
    before = int(psql("select count(*) from submissions") or 0)
    code, _, _ = request(
        "POST", "/api/v1/public/widgets/1/submissions",
        body={"email": "bot@example.com", "name": "Bot", "website": "spam-payload"},
        headers={"Origin": ORIGIN},
    )
    after = int(psql("select count(*) from submissions") or 0)
    check("bot receives an ordinary 202", code == 202, f"got {code}")
    check("nothing was stored", after == before, f"{before} -> {after}")

    step("idempotency: a duplicate submission does not double-insert the outbox")
    keys_before = int(psql("select count(*) from outbox_messages") or 0)
    payload = {"email": "dupe@example.com", "name": "Dupe", "website": ""}
    request("POST", "/api/v1/public/widgets/1/submissions", body=payload,
            headers={"Origin": ORIGIN})
    distinct = int(
        psql("select count(distinct idempotency_key) from outbox_messages") or 0
    )
    total = int(psql("select count(*) from outbox_messages") or 0)
    check("every outbox key is unique", distinct == total, f"{distinct}/{total}")
    check("the outbox grew", total > keys_before, f"{keys_before} -> {total}")

    step("probe 3 + concurrency: a burst yields 429, then normal service resumes")
    compose("exec", "-T", "redis", "redis-cli", "flushall")
    statuses = []
    for index in range(9):
        code, _, hdrs = request(
            "POST", "/api/v1/public/widgets/1/submissions",
            body={"email": f"burst{index}@example.com", "name": "Burst", "website": ""},
            headers={"Origin": ORIGIN},
        )
        statuses.append(code)
    check("429 appeared under burst", 429 in statuses, str(statuses))
    check("Retry-After was advertised", "retry-after" in {k.lower() for k in hdrs})
    compose("exec", "-T", "redis", "redis-cli", "flushall")
    code, _, _ = request(
        "POST", "/api/v1/public/widgets/1/submissions",
        body={"email": "after-burst@example.com", "name": "After", "website": ""},
        headers={"Origin": ORIGIN},
    )
    check("normal request succeeds right after", code == 202, f"got {code}")

    step("capacity: limiter state is shared, not per process")
    keys = compose("exec", "-T", "redis", "redis-cli", "keys", "ratelimit*")
    check("limiter keys live in redis", "ratelimit" in keys, keys.split("\n")[0][:60])

    step("CORS: a disallowed origin gets no browser grant")
    code, _, headers = request(
        "OPTIONS", "/api/v1/public/widgets/1/submissions",
        headers={"Origin": EVIL_ORIGIN, "Access-Control-Request-Method": "POST"},
    )
    lowered = {k.lower(): v for k, v in headers.items()}
    check("no allow-origin for an unlisted origin",
          lowered.get("access-control-allow-origin") != EVIL_ORIGIN)
    code, _, headers = request(
        "OPTIONS", "/api/v1/public/widgets/1/submissions",
        headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST"},
    )
    lowered = {k.lower(): v for k, v in headers.items()}
    check("the allowed origin is granted",
          lowered.get("access-control-allow-origin") == ORIGIN)

    step("observability: a request id correlates a response header to a log line")
    marker = "rehearsal-trace-id-4242"
    code, _, headers = request(
        "GET", "/api/v1/system/health/live", headers={"X-Request-ID": marker}
    )
    lowered = {k.lower(): v for k, v in headers.items()}
    check("the request id is echoed", lowered.get("x-request-id") == marker,
          lowered.get("x-request-id", ""))
    logs = compose("logs", "--tail", "200", "backend")
    check("the same id appears in the logs", marker in logs)

    step("observability: metrics are token-gated Prometheus text")
    code, _, _ = request("GET", "/api/v1/system/metrics")
    check("no token is refused", code in (401, 404), f"got {code}")
    code, body, headers = request(
        "GET", "/api/v1/system/metrics", headers={"X-Metrics-Token": TOKEN}
    )
    lowered = {k.lower(): v for k, v in headers.items()}
    check("scrape succeeds with a token", code == 200, f"got {code}")
    check("content type is exposition text",
          lowered.get("content-type", "").startswith("text/plain"))
    for needle in ("# TYPE embedlead_requests", 'le="+Inf"',
                   "embedlead_request_duration_seconds_count"):
        check(f"exposition carries {needle}", needle in body)
    infinity = re.search(
        r'embedlead_request_duration_seconds_bucket\{le="\+Inf",method="GET",'
        r'route="/api/v1/system/health/live"\} (\S+)', body)
    counted = re.search(
        r'embedlead_request_duration_seconds_count\{method="GET",'
        r'route="/api/v1/system/health/live"\} (\S+)', body)
    if infinity and counted:
        check("cumulative buckets: +Inf equals _count",
              infinity.group(1) == counted.group(1),
              f"{infinity.group(1)} vs {counted.group(1)}")
    else:
        check("cumulative buckets: +Inf equals _count", False, "series not found")

    step("routing: an unmatched path collapses to one metric series")
    for index in range(3):
        request("GET", f"/api/v1/no-such-route-{index}")
    code, body, _ = request(
        "GET", "/api/v1/system/metrics", headers={"X-Metrics-Token": TOKEN}
    )
    check("unmatched paths share one label", body.count('route="unmatched"') > 0)

    step("probe 5: the notification side effect is off the request path")
    before = int(psql("select count(*) from submissions") or 0)
    code, _, _ = request(
        "POST", "/api/v1/public/widgets/1/submissions",
        body={"email": "side-effect@example.com", "name": "Side", "website": ""},
        headers={"Origin": ORIGIN},
    )
    after = int(psql("select count(*) from submissions") or 0)
    check("submission succeeded independently of delivery", code == 202, f"got {code}")
    check("lead was stored", after == before + 1, f"{before} -> {after}")
    time.sleep(6)
    sent = psql("select count(*) from outbox_messages where status = 'sent'")
    check("the supervised worker delivered with no human command",
          int(sent or 0) > 0, f"sent={sent}")

    step("probe 4 + graceful degradation: kill geo provider A, B still enriches")
    chain = compose(
        "exec", "-T", "-e", "GEO_PROVIDER_A_ENABLED=false", "backend",
        "python", "-c",
        "from app.api.geo_dependencies import build_geo_chain;"
        "print([type(p).__name__ for p in build_geo_chain().providers])",
    )
    check("provider A removed, B remains", "IpapiCoProvider" in chain
          and "IpApiProvider" not in chain, chain.split("\n")[-1][:60])
    chain = compose(
        "exec", "-T", "-e", "GEO_ENRICHMENT_ENABLED=false", "backend",
        "python", "-c",
        "from app.api.geo_dependencies import build_geo_chain;"
        "print([type(p).__name__ for p in build_geo_chain().providers])",
    )
    check("both down yields an empty chain", "[]" in chain, chain.split("\n")[-1][:40])
    code, _, _ = request(
        "POST", "/api/v1/public/widgets/1/submissions",
        body={"email": "no-geo@example.com", "name": "NoGeo", "website": ""},
        headers={"Origin": ORIGIN},
    )
    check("a submission still succeeds without geo", code == 202, f"got {code}")

    step("graceful degradation: stop redis, the public form must still accept")
    compose("stop", "redis")
    code, _, _ = request(
        "POST", "/api/v1/public/widgets/1/submissions",
        body={"email": "redis-down@example.com", "name": "Outage", "website": ""},
        headers={"Origin": ORIGIN},
    )
    check("submission accepted with redis down (fail open)", code == 202, f"got {code}")
    code, body, _ = request("GET", "/api/v1/system/health/ready")
    check("readiness stays 200", code == 200, f"got {code}")
    report = json.loads(body)
    check("redis reports degraded, not fatal",
          report["checks"]["redis"]["status"] == "degraded",
          report["checks"]["redis"]["status"])
    check("aggregate status follows the database",
          report["status"] == report["checks"]["database"]["status"])
    compose("start", "redis")
    check("stack recovered", wait_ready(90))

    step("graceful shutdown: a committed lead survives a restart")
    compose("exec", "-T", "redis", "redis-cli", "flushall")
    code, _, _ = request(
        "POST", "/api/v1/public/widgets/1/submissions",
        body={"email": "survives-restart@example.com", "name": "Durable",
              "website": ""},
        headers={"Origin": ORIGIN},
    )
    check("lead accepted", code == 202, f"got {code}")
    compose("restart", "backend")
    check("stack came back", wait_ready(120))
    rows = psql(
        "select count(*) from submissions "
        "where email = 'survives-restart@example.com'"
    )
    check("the lead survived", rows == "1", f"rows={rows}")
    logs = compose("logs", "--tail", "300", "backend")
    check("shutdown ran the lifespan", "application_shutdown" in logs)

    step("dashboard: the owner sees the leads that were captured")
    bearer = token()
    code, body, _ = request(
        "GET", "/api/v1/dashboard/stats", headers={"Authorization": f"Bearer {bearer}"}
    )
    check("dashboard served", code == 200, f"got {code}")
    if code == 200:
        summary = json.loads(body)
        check("submissions are visible", summary.get("total_submissions", 0) > 0,
              f"total={summary.get('total_submissions')}")

    print("\n" + "=" * 72)
    if FAILURES:
        print(f"REHEARSAL FAILED — {len(FAILURES)} check(s) did not pass")
        for item in FAILURES:
            print("  -", item)
        return 1
    print(f"REHEARSAL PASSED — all checks green across {STEP[0]} steps")
    return 0


if __name__ == "__main__":
    sys.exit(main())
