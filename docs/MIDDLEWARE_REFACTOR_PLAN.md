MIDDLEWARE_REFACTOR_PLAN.md

Project: Velro Backend (FastAPI on Railway)
Goal: Make the middleware stack stable, modular, and testable so router endpoints work reliably (projects, credits, generations, models) and CORS headers are always present—even on errors.

⸻

1) Why we’re doing this

Pain points observed
	•	Router endpoints 500 before handlers are reached (middleware crash).
	•	Browser shows CORS errors (because error responses lack CORS headers).
	•	Auth middleware previously missing methods → cascade failures in rate limiter/access control.
	•	Production deploys hard to validate; failures only visible after shipping.

Objectives
	•	Guarantee CORS headers on every response (success/errors).
	•	Make middleware optional & toggled by env, not code edits.
	•	Ensure any single middleware failure degrades gracefully (no global outage).
	•	Add diagnostics, logs, and tests per middleware.

⸻

2) Design principles
	1.	Fail open for CORS: CORS must be the outermost and cannot be skipped by exceptions below.
	2.	Small surface, layered: Critical → Optional → Heavy.
	3.	Idempotent registration: Guarded imports and clear startup logs.
	4.	Feature flags: Each middleware toggled via env var with sane defaults.
	5.	Observability-by-default: Each layer logs enter/exit, duration, and errors with a request_id.

⸻

3) Target middleware order (outermost → innermost)
	1.	CORS (always on; outermost)
	2.	TrustedHost (prod only; reject obviously bad hosts early)
	3.	Minimal Request Logger (low-cost; attaches X-Request-ID, timing)
	4.	Auth (JWT parse/verify; must return 401 cleanly)
	5.	Access Control (RBAC / route policy; fast-lane bypass for public routes)
	6.	CSRF (if cookies; off for token-only flows)
	7.	SSRF Protection (validates outgoing URL usage for proxying features)
	8.	Rate Limiter (Redis-backed; must degrade to in-memory or noop)
	9.	GZip (cheap, but run later so we compress final body)

Note: “Last added runs first on request path” in Starlette. Ensure CORS is added last in code so it’s outermost at runtime.

⸻

4) Env flags & defaults


Variable
Values
Default
Notes
BYPASS_MIDDLEWARE
true/false
false
Emergency mode: only CORS + minimal logger.
CORS_ORIGINS
JSON array or CSV
prod origins
Accepts ["https://foo","http://localhost:3000"] or https://foo,http://localhost:3000.
ALLOW_CREDENTIALS
true/false
true
Cookies/future support; safe with explicit origins.
ENABLE_TRUSTED_HOSTS
true/false
true (prod), false (dev)
Use ALLOWED_HOSTS for list.
ALLOWED_HOSTS
CSV
(prod list)
e.g. api.velro.ai,velro.ai,*.railway.app
ENABLE_AUTH
true/false
true
Turns auth middleware on/off.
ENABLE_ACL
true/false
true
AccessControl toggler.
ENABLE_CSRF
true/false
false
Enable only for cookie flows.
ENABLE_SSRF_PROTECT
true/false
true
ENABLE_RATE_LIMIT
true/false
true
Auto-fallback to memory/disabled if Redis not ready.
REDIS_URL
URL
(unset)
If unset or failing → fallback.
FASTLANE_PATHS
CSV
/api/v1/auth/*,/health,/__version
Bypass heavy layers.
LOG_LEVEL
INFO/DEBUG/WARN
INFO
Increase for diagnostics.


5) Bootstrap sequence (pseudocode)

# main.py (excerpt)
from fastapi import FastAPI
from config import settings  # loads env safely

app = FastAPI(...)

# 1) ROUTES THAT MUST WORK EVEN IN BYPASS (health, version, ping)
register_core_minimal_routes(app)

# 2) MIDDLEWARE BOOTSTRAP
if settings.BYPASS_MIDDLEWARE:
    add_minimal_logger(app)
    add_cors_outermost(app, settings)  # must be last added
else:
    if settings.ENABLE_TRUSTED_HOSTS: add_trusted_host(app, settings)
    add_minimal_logger(app)
    if settings.ENABLE_AUTH: add_auth_middleware(app, settings)
    if settings.ENABLE_ACL: add_access_control(app, settings)
    if settings.ENABLE_CSRF: add_csrf(app, settings)
    if settings.ENABLE_SSRF_PROTECT: add_ssrf(app, settings)
    if settings.ENABLE_RATE_LIMIT: add_rate_limiter_with_fallback(app, settings)
    add_gzip(app)
    add_cors_outermost(app, settings)  # <-- ALWAYS LAST

# 3) ROUTERS (guarded)
register_application_routers_guarded(app)

# 4) STARTUP SELF-CHECKS
run_middleware_and_routes_sanity_check(app)


Guarded router registration: wrap each include_router() in try/except, log failures with route name and import error.

⸻

6) Error handling guarantees
	•	Global exception handler returns JSON with:
	•	request_id, path, method, status, error_code, message
	•	CORS headers added to error responses since CORS is outermost.
	•	Auth errors return 401 (never 500).
	•	Downstream dependency failures (Redis, Supabase) → return 503/502 as appropriate with CORS.

⸻

7) Minimal, optional, and heavy middleware definitions

Minimal Logger (always on)
	•	Injects/propagates X-Request-ID
	•	Logs: entering path, status, duration, user_id (if present), fastlane flag.

Auth
	•	Verifies JWT with AsyncAuthService.verify_token_http.
	•	Attaches request.state.user (never throws raw exception—translate to 401).

Access Control
	•	Fastlane bypass (e.g., /api/v1/auth/*, /health).
	•	Uses request.state.user + route policy; returns 403 on deny.

CSRF (optional)
	•	Only if cookies/session are enabled; skip for Bearer-token APIs.

SSRF Protection
	•	Validates external fetch/proxy targets for features that accept URLs.

Rate Limiter (heavy)
	•	Redis with exponential backoff and in-memory noop fallback.
	•	If Redis init fails, log + continue (do not break request path).

GZip
	•	Enabled after functional layers, before CORS (since CORS is outermost).

⸻

8) Diagnostics & health

Add/keep zero-dependency routes that must work even in bypass:
	•	GET /__health – shallow health
	•	GET /__version – service build/env
	•	GET /__config – which middleware enabled (mask secrets)
	•	GET /__diag/request – echoes headers, shows middleware list & order
	•	GET /__diag/routes – lists registered routes
	•	GET /__diag/rate-limit – shows RL backend status (redis/memory/noop)
	•	GET /__diag/auth – verifies auth layer loaded and mode (fastlane on/off)

All of these return fast, no heavy deps.

⸻

9) Test harness

A. Per-middleware isolation tests (local)
	•	Spin a minimal app and add only one middleware under test.
	•	pytest + httpx client:
	•	happy-path
	•	error-path
	•	fastlane path (if applicable)
	•	verify headers (CORS, request-id)
	•	timing/log presence

B. Canary script (CI)

scripts/test-middleware-canary.sh:
	•	/__health → 200
	•	/__diag/request → has CORS headers
	•	/api/v1/models/supported → 200 or meaningful 4xx (no CORS error)
	•	/api/v1/projects → 401 (if no token), not 500, with CORS headers
	•	/api/v1/credits/balance → 401 with CORS headers

Exit non-zero on any failure.

C. Binary search rollout
	•	Deploy BYPASS_MIDDLEWARE=true to production:
	•	Verify UI loads, CORS ok, diagnostics ok.
	•	Enable auth only → test.
	•	Enable ACL → test.
	•	Enable SSRF → test.
	•	Enable rate limiter → test.
	•	Stop when break occurs, pinpoint culprit.

⸻

10) CI/CD gates
	•	Build gate: python -m compileall succeeds (no syntax errors).
	•	Unit gate: per-middleware tests pass.
	•	Sanity gate: canary script passes against staging.
	•	Promotion gate: prod deploy only if staging canary passes.

⸻

11) Railway deployment checklist
	1.	Variables
	•	Set all ENABLE_* flags per environment (prod/staging/dev).
	•	CORS_ORIGINS includes:
	•	https://velro-frontend-production.up.railway.app
	•	https://velro-kong-gateway-production.up.railway.app
	•	http://localhost:3000 (dev)
	2.	Health checks
	•	Path: /__health
	3.	Redis
	•	REDIS_URL present (prod), if not → RL fallback triggers.
	4.	Logs
	•	LOG_LEVEL=INFO (prod), DEBUG (staging if needed)
	5.	Rollback
	•	Keep previous known-good image
	•	BYPASS_MIDDLEWARE=true safe mode available

⸻

12) Kong / Edge notes (if in path)
	•	If Kong fronts the backend, ensure it doesn’t strip Access-Control-* or Origin.
	•	Prefer letting backend set CORS; disable Kong CORS plugin or mirror backend’s config exactly.
	•	If using Kong rate limit too, don’t double-limit; stagger scope (per-IP on edge, per-user in app).

⸻

13) Supabase/Auth notes
	•	Never use service key for user reads/writes; per-user Supabase client only.
	•	Auth middleware sets request.state.user.
	•	Repositories use per-user client (RLS enforced).
	•	401/403 must be returned cleanly with CORS headers—no 500 on auth errors.

⸻

14) Acceptance criteria
	•	CORS headers are present on every response (2xx/4xx/5xx).
	•	/api/v1/projects w/out token → 401 JSON (no browser CORS error).
	•	/api/v1/models/supported → 200 JSON or a clear 5xx with CORS if dependency down.
	•	Enabling/disabling any single middleware does not break the app.
	•	__diag/routes lists all critical routes.
	•	Canary passes in staging and prod after each toggle step.

⸻

15) Risk register & mitigations
	•	Redis down → rate limit fallback (noop/memory), logs warn, app continues.
	•	JWT library mismatch → auth returns 401 with CORS, diagnostics page shows auth mode.
	•	Wrong CORS_ORIGINS → diagnostics endpoint returns parsed origins, can be fixed via env change.
	•	Import errors in routers → guarded registration logs which router failed; core routes continue.

⸻

16) Work plan (tasks)
	•	Create middleware/ modules (cors, logger, auth, acl, csrf, ssrf, rate_limit).
	•	Implement config/settings.py with robust env parsing (JSON/CSV origins).
	•	Update main.py bootstrap per sequence above, with guarded router registration.
	•	Add diagnostics routes and ensure they’re zero-dep.
	•	Write per-middleware tests + canary script.
	•	Wire CI gates (compile, unit, canary).
	•	Stage deploy with bypass → incremental toggle & verify.
	•	Document final state and lock config.

⸻

17) Quick verification commands

# CORS preflight (should be 200 with allow headers)
curl -i -X OPTIONS \
  -H "Origin: https://velro-frontend-production.up.railway.app" \
  -H "Access-Control-Request-Method: GET" \
  https://<backend>/api/v1/models/supported

# Unauthed projects (should be 401 JSON, not CORS error)
curl -i -H "Origin: https://velro-frontend-production.up.railway.app" \
  https://<backend>/api/v1/projects

# Diag endpoints
curl -s https://<backend>/__diag/request | jq
curl -s https://<backend>/__diag/routes | jq
curl -s https://<backend>/__config | jq

18) Appendix: minimal app for isolation

# main_minimal.py
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

app = FastAPI()
@app.get("/__health") async def health(): return {"ok": True}
@app.get("/ping") async def ping(): return {"pong": True}

# Add CORS LAST so it’s outermost
app.add_middleware(
  CORSMiddleware,
  allow_origins=["https://velro-frontend-production.up.railway.app","http://localhost:3000"],
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
  expose_headers=["X-Request-ID","Server-Timing"],
  max_age=86400
)

Use this to verify CORS/headers independently, then add one middleware at a time to spot regressions.

⸻

Owner: Senior Backend Engineer
Outcome: A resilient, observable, and toggleable middleware layer that unblocks router endpoints, restores the UI, and prevents future “CORS + 500 loop” incidents.

