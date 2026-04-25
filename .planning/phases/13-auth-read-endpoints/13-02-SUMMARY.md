---
phase: 13
plan: 02
subsystem: web/factory
tags: [auth, fastapi, factory, openapi, middleware, wave-1]
requires:
  - "Plan 13-01 autouse WEB_AUTH_SECRET fixture (tests/conftest.py)"
  - "Plan 13-01 hex-boundary update (FORBIDDEN_FOR_WEB minus 'dashboard')"
  - "Plan 13-01 4 skeleton test files (auth_middleware, dashboard, state, app_factory)"
provides:
  - "create_app() with fail-closed WEB_AUTH_SECRET validation (D-16/D-17)"
  - "FastAPI(docs_url=None, redoc_url=None, openapi_url=None) — full schema suppression (D-21+D-22)"
  - "AuthMiddleware registered LAST in create_app() so it runs FIRST (D-06)"
  - "web/middleware/auth.py — full Pattern 1 BaseHTTPMiddleware body (D-01..D-06)"
  - "web/routes/dashboard.py stub returning 503 (Plan 13-05 fills body)"
  - "web/routes/state.py stub returning 503 + Cache-Control: no-store (Plan 13-04 fills body)"
  - "8 factory tests (4 secret validation + 4 docs suppression) — TestSecretValidation + TestDocsDisabled"
affects:
  - web/app.py
  - web/middleware/__init__.py
  - web/middleware/auth.py
  - web/routes/dashboard.py
  - web/routes/state.py
  - tests/test_web_app_factory.py
tech-stack:
  added: []
  patterns:
    - "BaseHTTPMiddleware subclass with secret captured at __init__ via factory injection"
    - "hmac.compare_digest on UTF-8-encoded bytes for constant-time secret check"
    - "Frozenset path-allowlist (EXEMPT_PATHS) checked first in dispatch()"
    - "FastAPI factory with secret validation BEFORE FastAPI() instantiation"
    - "openapi_url=None as third schema-suppression kwarg (research extension D-22)"
    - "Middleware-last registration to leverage Starlette reverse-of-registration ordering"
key-files:
  created:
    - web/middleware/__init__.py
    - web/middleware/auth.py
    - web/routes/dashboard.py
    - web/routes/state.py
  modified:
    - web/app.py
    - tests/test_web_app_factory.py
decisions:
  - "Plan-as-written `from conftest import VALID_SECRET, AUTH_HEADER_NAME` fails because pytest's testpaths=['tests'] does not put tests/ on sys.path; inlined the constants in tests/test_web_app_factory.py with comments referencing tests/conftest.py as the conceptual single-source. The autouse fixture from conftest.py still runs (filename match works via pytest's standard conftest discovery, which is independent of import path)."
  - "AuthMiddleware ships full Pattern 1 body in Plan 13-02 (not a stub) so the openapi_url=401-without-auth contract test (D-06 ordering proof) can pass in this plan rather than waiting for Plan 13-03. Plan 13-03 owns the middleware test methods that prove every D-01..D-06 behavior; Plan 13-02 only provides a single ordering-proof test in TestDocsDisabled."
  - "Route stubs (dashboard.py + state.py) return 503 with deterministic content rather than raising NotImplementedError — keeps the import graph functional end-to-end and gives Wave 2 (Plans 13-04/05) clean reference points."
  - "Acceptance-criteria grep counts of 1 for `docs_url=None`, `redoc_url=None`, `openapi_url=None` produce values 2/2/3 in practice because the strings appear in both code and module docstring; the FastAPI() kwargs are unique. This is documentation-quality bonus, not a violation."
metrics:
  duration: "~5m37s"
  tasks: 2
  files_created: 4
  files_modified: 2
  tests_added: 8
  completed: 2026-04-25
---

# Phase 13 Plan 02: Factory Wiring + AuthMiddleware + Route Stubs Summary

Wave 1 wiring backbone — `create_app()` now refuses to start without a 32+ char `WEB_AUTH_SECRET`, suppresses Swagger/Redoc/OpenAPI schema, registers AuthMiddleware as the dispatch entry, and stubs out `/` and `/api/state` for Wave 2.

## What Was Done

### Task 1 — Source files (commit 550015a)

**Five files touched:**

1. **`web/middleware/__init__.py`** — empty 0-byte package marker (mirrors `web/routes/__init__.py` from Phase 11 D-03).
2. **`web/middleware/auth.py` (NEW)** — full RESEARCH §Pattern 1 implementation:
   - `BaseHTTPMiddleware` subclass with `__init__(app, *, secret)` capturing the secret as bytes
   - `dispatch()`: path-allowlist exemption (`EXEMPT_PATHS = frozenset({'/healthz'})`) checked first
   - `hmac.compare_digest` on UTF-8 bytes (D-03 constant-time)
   - 401 response with `media_type='text/plain; charset=utf-8'` and body literal `unauthorized` (D-04)
   - `_log_failure()` static helper: IP from `X-Forwarded-For` first entry (D-05 reconciled), 120-char UA truncation, `[Web]` log prefix
   - Module docstring includes Phase 14 forward warning about `BaseHTTPMiddleware` + `BackgroundTasks` interaction
3. **`web/routes/dashboard.py` (NEW STUB)** — `register(app)` registers `GET /` returning 503 plain-text `dashboard not ready` until Plan 13-05.
4. **`web/routes/state.py` (NEW STUB)** — `register(app)` registers `GET /api/state` returning 503 JSON with `Cache-Control: no-store` until Plan 13-04.
5. **`web/app.py` (REWRITTEN)** — full `create_app()` overhaul:
   - `_read_auth_secret()` helper raises `RuntimeError` on missing/empty/<32-char `WEB_AUTH_SECRET` (D-16/D-17 fail-closed)
   - `FastAPI(docs_url=None, redoc_url=None, openapi_url=None, ...)` — all THREE kwargs (D-21 + D-22 research extension)
   - Registers all 3 routes (healthz, dashboard, state) before middleware
   - `add_middleware(AuthMiddleware, secret=secret)` is the LAST line before `return application` — Starlette runs it FIRST (D-06)
   - Source comments pin "future middleware MUST be registered above this line" for Phase 14+ contributors

### Task 2 — Test population (commit 1626e71)

**`tests/test_web_app_factory.py`** populated with 8 tests:

**TestSecretValidation (4 tests):**
- `test_missing_secret_raises` — `delenv` then expect `RuntimeError` matching `'WEB_AUTH_SECRET'`
- `test_empty_secret_raises` — `setenv('','')` then expect `'missing or empty'`
- `test_short_secret_raises` — `setenv('a' * 31)` then expect `'at least 32 characters'`
- `test_32_char_secret_accepted` — `setenv('a' * 32)`, instantiate, assert all 3 routes registered

**TestDocsDisabled (4 tests):**
- `test_docs_url_returns_404_with_auth` — `/docs` returns 404 with valid auth (D-21)
- `test_redoc_url_returns_404_with_auth` — `/redoc` returns 404 with valid auth (D-21)
- `test_openapi_json_returns_404_with_auth` — `/openapi.json` returns 404 with valid auth (D-22 — proves the schema is fully suppressed, not just docs UI)
- `test_openapi_json_blocked_by_auth_when_unauthenticated` — `/openapi.json` returns 401 WITHOUT auth header (D-06 — proves middleware reaches the path before FastAPI's 404 logic)

## Why This Matters

Plan 13-02 is the wiring backbone for Phase 13. With this plan landed:

1. The factory now refuses to boot in a fail-open posture. A missing `WEB_AUTH_SECRET` produces `RuntimeError` BEFORE `FastAPI()` is instantiated — systemd's `Restart=on-failure` will loop until the operator fixes the env var. systemd's journald shows the exact cause.
2. `/openapi.json` no longer leaks the API surface to unauthenticated probers — even if Phase 14+ accidentally introduces sensitive route metadata.
3. The middleware-last registration pattern is set in stone with a source comment, so Phase 14 contributors don't accidentally register new middleware AFTER auth (which would defeat the gate).
4. Plans 13-03 (auth middleware tests), 13-04 (state route impl), 13-05 (dashboard route impl) can now run **in parallel** against this stable factory contract — they don't need to coordinate file creation order, fixture wiring, or import graph changes.

## Verification Results

- `pytest tests/test_web_app_factory.py -x -v` → **8 passed in 0.15s** (4 TestSecretValidation + 4 TestDocsDisabled)
- `pytest tests/test_web_healthz.py -x -q` → **17 passed** (Phase 11 healthz tests untouched — the autouse fixture from Plan 13-01 keeps them green under the new fail-closed factory)
- `pytest tests/test_web_*.py -q` → **57 passed in 0.20s** (full Phase 11+13 web suite green; Plan 13-01 skeletons collect with 0 tests, Plan 13-02 adds 8)
- `pytest tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent` → **3 passed** (hex boundary on pure-math hexes preserved — no regression from web layer touch)
- `pytest tests/test_web_healthz.py::TestWebHexBoundary -v` → **3 passed** (`test_web_modules_do_not_import_hex_core`, `test_dashboard_is_not_forbidden_for_web_phase_13_D07`, `test_web_adapter_imports_are_local_not_module_top` — last test's absent-file skip-guard now succeeds because all 5 web/ files exist; `dashboard` and `state_manager` confirmed NOT module-top imported anywhere in web/)
- `pytest tests/ -q` → **906 passed, 16 failed** — the 16 failures are all in `tests/test_main.py` and match exactly the pre-existing failures documented in `.planning/phases/13-auth-read-endpoints/deferred-items.md` (verified pre-existing on `b1f9b8f`). **Net change vs Plan 13-01 baseline: +8 passing tests (the new factory tests), 0 new failures.**
- Boot smoke test: `WEB_AUTH_SECRET=$(yes a | head -32 | tr -d '\n') python -c "from web.app import create_app; app = create_app()"` produces 3 routes (`/healthz`, `/`, `/api/state`).
- Missing-secret smoke test: `python -c "from web.app import create_app; create_app()"` raises `RuntimeError` mentioning `WEB_AUTH_SECRET`.
- Short-secret smoke test: `WEB_AUTH_SECRET=short python -c "..."` raises `RuntimeError` mentioning `at least 32 characters`.
- Grep checks: all required strings present (`hmac.compare_digest`, `EXEMPT_PATHS = frozenset({'/healthz'})`, `UA_TRUNCATE = 120`, `AUTH_HEADER = 'X-Trading-Signals-Auth'`, `add_middleware(AuthMiddleware`, `_MIN_SECRET_LEN = 32`, two `raise RuntimeError`).
- Middleware-last invariant verified: `grep -n "register(application)\|add_middleware(AuthMiddleware" web/app.py` shows lines 87/88/89 (route registers) BEFORE line 94 (add_middleware).

## Decisions Made

1. **Inlined `VALID_SECRET` + `AUTH_HEADER_NAME` constants in tests/test_web_app_factory.py** instead of `from conftest import` (Rule 1 deviation — see below). Both constants are defined ONCE in `tests/conftest.py` for the autouse fixture and `auth_headers` fixture; the test file mirrors them with comments pointing back to the single source. The REVIEWS LOW #6 single-source spirit is preserved (conftest.py remains canonical for the fixture wiring); the test-file mirroring is a workaround for pytest's `testpaths=['tests']` not putting the tests/ directory on sys.path.
2. **AuthMiddleware ships the full Pattern 1 body in this plan** (not a TODO stub) because the `test_openapi_json_blocked_by_auth_when_unauthenticated` test (D-06 ordering proof) needs functional middleware to pass. Plan 13-03 owns the comprehensive middleware test classes (`TestAuthRequired`, `TestUnauthorizedResponse`, `TestAuditLog`, etc.); Plan 13-02 only proves the registration-order invariant.
3. **Route handlers ship as 503 stubs** rather than raising `NotImplementedError`, so any caller (test, smoke check, manual curl) gets a deterministic response rather than a 500. Wave 2 plans (13-04, 13-05) replace the stubs with full implementations.
4. **`logger.info` line in `create_app()` says "auth=on"** to make the middleware posture grep-able in journald — the operator can confirm "the running unit has auth on" by `journalctl -u trading-signals-web | grep 'auth=on'`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `from conftest import` fails at test collection**
- **Found during:** Task 2 first `pytest` run (immediately after writing test bodies as plan-specified)
- **Issue:** Plan specified `from conftest import AUTH_HEADER_NAME, VALID_SECRET` with the rationale that pytest auto-adds tests/ to sys.path. In this project, `pyproject.toml` has `testpaths = ['tests']` but does not configure `pythonpath` or `rootdir` to expose tests/ as an importable package. Result: `ModuleNotFoundError: No module named 'conftest'` at collection, blocking all 8 tests.
- **Fix:** Inlined `VALID_SECRET = 'a' * 32` and `AUTH_HEADER_NAME = 'X-Trading-Signals-Auth'` directly in `tests/test_web_app_factory.py` with comments referencing `tests/conftest.py` as the single-source definition. The autouse fixture from conftest.py still runs (pytest's conftest discovery is path-walk based, not import-based), so the WEB_AUTH_SECRET is still set before each test in this file.
- **Files modified:** `tests/test_web_app_factory.py` (replaced `from conftest import ...` with mirror constants + commentary)
- **Commit:** `1626e71`

### Authentication Gates

None. No external auth required for this plan (no API keys, no Resend calls, no GitHub deploy key interaction).

### Architectural Changes (Rule 4)

None. The plan-defined Pattern 1 middleware body and factory amendments are fully scoped — no new tables, services, libraries, or auth approaches.

## Threat Surface

Three threats from `13-02-PLAN.md::<threat_model>` mitigated by this plan:

| Threat ID | Mitigation Acceptance |
|-----------|-----------------------|
| T-13-06 (Spoofing/Elevation: fail-open if secret missing) | `test_missing_secret_raises` + `test_empty_secret_raises` PASS |
| T-13-07 (Tampering: weak/short secret) | `test_short_secret_raises` PASS (31-char boundary explicitly tested) |
| T-13-08 (Information Disclosure: /openapi.json schema leak) | `test_openapi_json_returns_404_with_auth` + `test_openapi_json_blocked_by_auth_when_unauthenticated` PASS |
| T-13-08b (secret leaked via journald) | implicit — `_read_auth_secret()` does not log; only `[Web] FastAPI app created (...; auth=on)` line emitted |
| T-13-08c (future middleware bypass) | source comment pins D-06 invariant |

No new threat-flag findings. No new security surface introduced beyond what was scoped by `13-02-PLAN.md`.

## What Comes Next

Wave 2 plans (13-03, 13-04, 13-05) can now run **in parallel**:

- **Plan 13-03** — populate `tests/test_web_auth_middleware.py` (6 test classes) against the AuthMiddleware body shipped in 13-02. No production code changes (the middleware is already complete).
- **Plan 13-04** — replace the `web/routes/state.py` stub with the full body (D-12 underscore-key strip + D-13 Cache-Control + D-14 trust load_state + D-15 compact JSON) and populate `tests/test_web_state.py` (1 test class).
- **Plan 13-05** — replace the `web/routes/dashboard.py` stub with the full body (D-07 mtime-staleness regen + D-08 atomic mtime compare + D-10 stale fallback + D-11 single-worker concurrency posture) and populate `tests/test_web_dashboard.py` (4 test classes).

The factory contract from this plan is locked: Plans 13-03/04/05 do NOT modify `web/app.py`.

## Self-Check: PASSED

**Files created (verified exist):**
- web/middleware/__init__.py — exists, 0 bytes (empty package marker)
- web/middleware/auth.py — exists, 84 lines (full Pattern 1 body)
- web/routes/dashboard.py — exists, 33 lines (503 stub)
- web/routes/state.py — exists, 33 lines (503 stub)

**Files modified (verified content):**
- web/app.py — 101 lines (was 39); has all 3 schema-suppression kwargs, both RuntimeError raises, AuthMiddleware import, add_middleware as last line
- tests/test_web_app_factory.py — 8 test methods populated, all passing

**Commits (verified in `git log --oneline`):**
- 550015a feat(13-02): wire AuthMiddleware + factory secret validation + route stubs
- 1626e71 test(13-02): populate factory tests — secret validation + OpenAPI suppression
