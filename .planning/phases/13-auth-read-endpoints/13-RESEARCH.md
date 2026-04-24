# Phase 13: Auth + Read Endpoints — Research

**Researched:** 2026-04-25
**Domain:** FastAPI/Starlette ASGI middleware + shared-secret auth + FileResponse caching + stdlib crypto primitives
**Confidence:** HIGH

## Summary

Phase 13 layers a shared-secret `X-Trading-Signals-Auth` header check on the existing Phase 11 FastAPI skeleton, then exposes `GET /` (regenerate-on-stale dashboard) and `GET /api/state` (JSON snapshot) behind that gate. The CONTEXT.md decisions D-01..D-21 are already comprehensive — this research confirms them, flags three execution-time pitfalls the planner MUST account for, and documents test strategy.

**Three findings that MUST shape the plan:**

1. **`/openapi.json` is NOT disabled by `docs_url=None, redoc_url=None` alone.** FastAPI keeps serving the schema at `/openapi.json`. To fully suppress OpenAPI exposure per D-21 intent, `create_app()` MUST also pass `openapi_url=None`. D-21 as written only names docs_url and redoc_url; planner must extend.
2. **`BaseHTTPMiddleware` has known bugs with BackgroundTasks and contextvars.** Phase 13 doesn't use either today — so it's safe — but the planner should add a comment in `web/middleware/auth.py` pinning "no BackgroundTasks from auth-gated routes" so Phase 14 doesn't accidentally trip this.
3. **`X-Forwarded-For` parsing must happen in app code (D-05) even though uvicorn has `--forwarded-allow-ips`.** Uvicorn's ProxyHeaders middleware rewrites `request.client.host`, but only if explicitly enabled. The `systemd/trading-signals-web.service` unit from Phase 11 does NOT pass `--forwarded-allow-ips=127.0.0.1`. D-05 compensates by reading `X-Forwarded-For` header directly from app layer — correct approach, but the researcher flags the ALTERNATIVE (add the flag and use `request.client.host`) for planner awareness.

**Primary recommendation:** Implement per CONTEXT.md D-01..D-21 with the `openapi_url=None` extension (see §Project Constraints). Use `BaseHTTPMiddleware` subclass with factory-injected secret; register via `app.add_middleware()` LAST so it runs FIRST; read `X-Forwarded-For` from the request header not `request.client.host`; use `hmac.compare_digest` on UTF-8 encoded bytes; `FileResponse` for `GET /`; strip `_*` keys on `GET /api/state`; fail-closed on missing `WEB_AUTH_SECRET` at `create_app()` boot.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Area 1 — Auth enforcement mechanism**
- **D-01:** Single `AuthMiddleware` registered via `app.add_middleware(...)` in `create_app()` is the sole enforcement chokepoint. Lives at `web/middleware/auth.py`. No per-route `Depends(verify_auth)`.
- **D-02:** `/healthz` exemption via explicit `EXEMPT_PATHS = frozenset({'/healthz'})` allowlist as first line of `dispatch()`. Do NOT use router mount tricks.
- **D-03:** `hmac.compare_digest` constant-time comparison on UTF-8-encoded bytes. Never `==`.
- **D-04:** 401 response is plain-text body `unauthorized`. Content-Type `text/plain; charset=utf-8`. No WWW-Authenticate, no JSON, no hints.
- **D-05:** AUTH-03 WARN log format: `[Web] auth failure: ip=%s ua=%r path=%s`. IP from `X-Forwarded-For` first entry (split by comma), fallback to `request.client.host`. UA truncated to 120 chars (SC-5 authority superseded earlier 60-char option). `%r` on UA escapes control chars.
- **D-06:** AuthMiddleware registered LAST in `create_app()` so it runs FIRST (Starlette reverses registration). Planner adds inline comment.

**Area 2 — GET / render strategy (WEB-05)**
- **D-07:** `GET /` serves `dashboard.html` from disk; regenerates only when `state.json` mtime > `dashboard.html` mtime. Returns `FileResponse('dashboard.html', media_type='text/html; charset=utf-8')`.
- **D-08:** Staleness = `os.stat(state.json).st_mtime_ns > os.stat(dashboard.html).st_mtime_ns`.
- **D-09:** Cached `dashboard.html` lives at repo root (same path `dashboard.py` already writes to).
- **D-10:** If `render_dashboard()` raises during `GET /`, log WARN and serve stale on-disk copy. If `dashboard.html` itself missing → 503 plain-text `dashboard not ready`.
- **D-11:** Concurrent regen under `workers=1` is harmless; no file locking.

**Area 3 — GET /api/state output shape (WEB-06)**
- **D-12:** Response body = `state.json` with top-level underscore-prefixed keys stripped. Nested dicts keep their keys. Implementation: `{k: v for k, v in state.items() if not k.startswith('_')}`.
- **D-13:** `Content-Type: application/json` (FastAPI default) + explicit `Cache-Control: no-store`.
- **D-14:** Trust Phase 3 `load_state()` recovery; no extra try/except.
- **D-15:** Compact JSON (FastAPI default; no `indent=2`).

**Area 4 — WEB_AUTH_SECRET missing-env behavior**
- **D-16:** `create_app()` raises `RuntimeError` if `WEB_AUTH_SECRET` missing or empty. Fail-closed at process start. Categorically diverges from Phase 12 D-14 email "log + degrade + continue" pattern.
- **D-17:** Minimum length: `len(WEB_AUTH_SECRET) < 32` also raises `RuntimeError` at startup. 32 chars ≈ 128 bits entropy via `openssl rand -hex 16`.
- **D-18:** Secret read ONCE at module load inside `create_app()` — not per-request. Tests `monkeypatch.setenv` BEFORE calling `create_app()` in fixture. `AuthMiddleware.__init__` captures secret from factory.
- **D-19:** SETUP-DROPLET.md extended with "Configure auth secret" section (3 steps: `openssl rand -hex 16` → append to `.env` → `systemctl restart`).
- **D-20:** Secret rotation explicitly DEFERRED to v1.2.

**Area 5 — Swagger/OpenAPI**
- **D-21:** `FastAPI(docs_url=None, redoc_url=None)` in `create_app()`. Single-operator tool, no external consumers. Swagger/Redoc disabled in production. *(Research note: this decision is incomplete as written — see §Project Constraints pitfall.)*

### Claude's Discretion
- Middleware class vs function style → recommend `BaseHTTPMiddleware` subclass in `web/middleware/auth.py` for testability and factory injection.
- Exact 401 media-type string (`text/plain; charset=utf-8` vs `text/plain`) → planner decides; recommend explicit charset.
- `FileResponse` vs `HTMLResponse(Path(...).read_text())` for `GET /` → recommend `FileResponse` (automatic ETag + Last-Modified + conditional GET).
- Rate-limit at nginx for `/` and `/api/state` → recommend planner adds `limit_req zone=auth` equivalent; exact config is planner discretion. Track as follow-up if not done.

### Deferred Ideas (OUT OF SCOPE)
- WEB_AUTH_SECRET rotation tooling / grace-period dual-secret → v1.2
- Session cookies / OAuth / JWT → hard PROJECT.md boundary
- WWW-Authenticate header on 401 → AUTH-02 explicitly says "no hints"
- Rate-limit on `/` and `/api/state` → follow-up (Phase 16 hardening if planner misses)
- Brute-force lockout / IP blacklisting → rate-limit + compare_digest + 128-bit entropy is sufficient
- Dashboard asset versioning / ETag query-string cache-busters → FileResponse handles ETag
- GET /api/state pagination → state.json <50KB
- Request-ID middleware / structured JSON logs → v1.2
- Swagger behind auth (rejected in favor of disabled per D-21)
- Concurrent `GET /` regen locking → harmless under workers=1
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| AUTH-01 | All non-/healthz endpoints require `X-Trading-Signals-Auth` header; value in `.env` as `WEB_AUTH_SECRET` | `BaseHTTPMiddleware.dispatch()` with path-allowlist exemption (D-02) + `hmac.compare_digest` on UTF-8 bytes (D-03). Verified: Starlette docs Context7 + Python stdlib docs. |
| AUTH-02 | Missing/wrong auth returns 401 with plain-text `unauthorized` body; no leaked info | `Response(content='unauthorized', status_code=401, media_type='text/plain; charset=utf-8')` inside dispatch. Verified: Starlette Response API. |
| AUTH-03 | Auth failures log at WARN with source IP + truncated UA to journald | `logger.warning('[Web] auth failure: ip=%s ua=%r path=%s', ...)` — `X-Forwarded-For` first-entry IP (SC-5 mandates XFF); UA `[:120]`; `%r` escapes control chars. Verified: D-05 reconciliation vs SC-5. |
| WEB-05 | `GET /` returns current `dashboard.html`; regenerates if state changed since last render | `os.stat` mtime comparison (state.json vs dashboard.html) + `dashboard.render_dashboard(state)` on stale + `FileResponse(...)`. Empirically verified: `os.replace` preserves source mtime_ns → `_atomic_write` in state_manager/dashboard produces correct "newer than" semantics for mtime comparison. |
| WEB-06 | `GET /api/state` returns `state.json` as `application/json` | `state_manager.load_state()` + strip `_*` keys at top level + `JSONResponse(clean, headers={'Cache-Control': 'no-store'})`. Verified: FastAPI JSONResponse default Content-Type. |
</phase_requirements>

## Project Constraints (from CLAUDE.md + Phase 11/12 CONTEXT)

The plan MUST honor these — they have the same authority as locked decisions:

1. **Hex-lite boundary (CLAUDE.md §Architecture, enforced by `tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent`):** `web/` imports allowed = `state_manager` (read-only per Phase 10 D-15), `dashboard` (new for Phase 13, for `render_dashboard()`), stdlib, fastapi, starlette. FORBIDDEN: `signal_engine`, `sizing_engine`, `system_params`, `data_fetcher`, `notifier`, `main`. Phase 13 plan MUST add `dashboard` to the permitted-adjacent set in `TestWebHexBoundary.FORBIDDEN_FOR_WEB` (currently forbids `dashboard` — see tests/test_web_healthz.py:186). Without this, `web/routes/dashboard.py` importing `dashboard.render_dashboard` fails the boundary test.
2. **Local imports inside handlers (Phase 11 C-2 / D-15 convention):** `from state_manager import load_state` and `from dashboard import render_dashboard` happen INSIDE the handler function body, not at module top. The hex-boundary test has a dedicated guard for module-top imports (see tests/test_web_healthz.py:208 `test_web_app_does_not_import_state_manager_at_module_top`) — extend to cover `dashboard` too.
3. **2-space indent, single quotes, snake_case** — PEP 8 via ruff.
4. **`[Web]` log prefix** on every new log line from the web process — Phase 11 established this convention.
5. **Exact version pins in requirements.txt** (no `>=`, no `~=`). Phase 13 adds zero new deps; `hmac` is stdlib, `starlette.middleware.base.BaseHTTPMiddleware` ships with FastAPI 0.136.1.
6. **`docs_url=None, redoc_url=None` is INSUFFICIENT for D-21 intent — add `openapi_url=None`.** CONTEXT D-21 literally specifies only the first two; this research elevates `openapi_url=None` from discretionary to REQUIRED. See §Common Pitfalls #5.
7. **GSD workflow gate (CLAUDE.md §GSD Workflow Enforcement):** No direct repo edits outside a GSD workflow. Phase 13 execution uses `/gsd:execute-phase` path.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Header validation (AUTH-01) | ASGI middleware | — | Single chokepoint per D-01; runs before any route handler. Using `Depends()` would require per-route annotation (fragile for Phase 14+). |
| Exemption routing (`/healthz` bypass) | ASGI middleware | — | D-02: explicit path allowlist inside middleware is auditable and grep-able; router mount tricks split the "what's public" answer across files. |
| Constant-time comparison | Python stdlib (`hmac.compare_digest`) | — | Never hand-roll; D-03 mandates stdlib. |
| 401 response body | ASGI middleware | — | Starlette `Response` returned directly from `dispatch()` before `call_next`. |
| Audit logging | ASGI middleware | Python stdlib `logging` | journald captures via systemd's `StandardOutput=journal` (Phase 11 D-12). No rotation config needed — journald handles. |
| Dashboard staleness detection | Route handler (`web/routes/dashboard.py`) | Python stdlib `os.stat` | Cheap mtime comparison. Pure-math adapter boundary — handler calls `state_manager.load_state()` + `dashboard.render_dashboard()` as I/O dependencies, but owns the staleness decision logic locally. |
| Dashboard file serving | Starlette `FileResponse` | — | Automatic `Content-Length`, `Last-Modified`, `ETag` per FastAPI docs; chunked transfer for large files; conditional GET support. |
| State JSON serialization | Starlette `JSONResponse` | Python stdlib `json` | FastAPI default; `Cache-Control: no-store` via `headers=` kwarg. |
| Secret validation at boot | `create_app()` factory | Python stdlib `os.environ` | Fail-closed pattern (D-16) = `raise RuntimeError` before `FastAPI()` is instantiated → uvicorn never binds port → systemd Restart=on-failure reports the error. |
| Secret storage at runtime | `AuthMiddleware.__init__` attribute (module-captured via factory) | — | D-18: secret captured ONCE; not per-request `os.environ.get`. |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `fastapi` | 0.136.1 | Web framework [VERIFIED: already pinned in requirements.txt, confirmed latest via `pip index versions fastapi` 2026-04-25] | Phase 11 baseline; current stable as of research date |
| `starlette` | transitive (shipped by fastapi 0.136.1) | ASGI middleware/response primitives | Ships with FastAPI; no separate pin needed |
| Python stdlib `hmac` | 3.11 | Constant-time comparison | D-03 mandate; zero-dep crypto |
| Python stdlib `os` | 3.11 | `os.stat(...).st_mtime_ns` for staleness check (D-08) | Empirically verified: `os.replace()` on POSIX preserves source mtime_ns to destination, so atomic tempfile+replace produces correct "newer than" semantics |
| Python stdlib `logging` | 3.11 | Audit WARN logs (AUTH-03) | Phase 11 established `[Web]` prefix convention |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `fastapi.responses.FileResponse` | 0.136.1 | Serve `dashboard.html` | `GET /` handler per D-07 |
| `fastapi.responses.JSONResponse` | 0.136.1 | Custom headers on state response | `GET /api/state` for `Cache-Control: no-store` (D-13) |
| `starlette.middleware.base.BaseHTTPMiddleware` | transitive | Request/response middleware abstraction | `web/middleware/auth.py` per D-01 + Claude's Discretion recommendation |
| `starlette.responses.Response` | transitive | 401 plain-text response | Returned directly from middleware `dispatch()` (AUTH-02) |
| `fastapi.testclient.TestClient` | 0.136.1 | Middleware + route tests | Already used in Phase 11 `tests/test_web_healthz.py` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `BaseHTTPMiddleware` subclass | Pure ASGI middleware (raw `async def __call__(scope, receive, send)`) | Pure ASGI avoids the known BackgroundTasks/contextvars bugs [CITED: github.com/Kludex/starlette/issues/2093, discussions/1729]. Phase 13 doesn't use BackgroundTasks or contextvars, so BaseHTTPMiddleware is safe AND simpler. Revisit only if Phase 14+ introduces BackgroundTasks. |
| `BaseHTTPMiddleware` | `@app.middleware('http')` function decorator | Functionally equivalent [CITED: fastapi.tiangolo.com/tutorial/middleware]. Subclass wins for testability (can construct with explicit secret) + clean factory injection. Decorator would force secret-via-closure reading from module globals. |
| `X-Forwarded-For` from header | Uvicorn `--forwarded-allow-ips=127.0.0.1` + `request.client.host` | Uvicorn's ProxyHeaders middleware rewrites `request.client.host` from XFF — requires systemd unit edit to add `--forwarded-allow-ips=127.0.0.1` flag [CITED: uvicorn.dev/deployment, github.com/Kludex/uvicorn/issues/589]. D-05 chose app-layer read, which is simpler and self-contained. Trade-off: app sees raw header (needs explicit first-entry parse); tradeoff is ~3 lines of code for zero systemd churn. |
| `FileResponse` | `HTMLResponse(Path(...).read_text())` | `FileResponse` adds ETag + Last-Modified + Content-Length + conditional GET automatically [CITED: fastapi.tiangolo.com/advanced/custom-response#fileresponse]. `HTMLResponse` would need manual ETag handling for conditional GETs. No reason to hand-roll. |
| Stripping underscore keys via dict-comp | Pydantic model with response_model_exclude | Dict comprehension is 1 line and handles dynamic keys from state.json schema evolution. Pydantic model would require schema-version coupling. |

**Installation:**
```bash
# No new deps — all stdlib or already pinned
# requirements.txt unchanged for Phase 13
```

**Version verification** (performed 2026-04-25):
- `fastapi`: 0.136.1 is the latest stable (pinned in `requirements.txt`; 136 versions available on PyPI).
- `starlette`: transitive from fastapi 0.136.1; no direct pin.
- `hmac` / `os` / `logging` / `http`: Python 3.11 stdlib.

## Architecture Patterns

### System Architecture Diagram

```
                     (public internet via Phase 12 nginx:443)
                                        │
                                        ▼
                              ┌──────────────────┐
                              │ nginx (Phase 12) │  adds X-Forwarded-For
                              │  port 443 (TLS)  │  proxies → 127.0.0.1:8000
                              └────────┬─────────┘
                                       │ HTTP on localhost
                                       ▼
                         ┌─────────────────────────┐
                         │ uvicorn (Phase 11)      │  workers=1, --host 127.0.0.1
                         │   --workers 1           │
                         └────────┬────────────────┘
                                  │ ASGI
                                  ▼
                         ┌─────────────────────────────────────────┐
                         │  FastAPI(docs_url=None, redoc_url=None, │
                         │          openapi_url=None)   # D-21+    │
                         │          created by create_app()        │
                         └────────┬────────────────────────────────┘
                                  │ request arrives
                                  ▼
                  ┌───────────────────────────────┐
                  │  AuthMiddleware.dispatch      │  ← runs FIRST (D-06)
                  │  1. path in EXEMPT_PATHS?     │
                  │     yes → call_next(request)  │──────► /healthz (Phase 11)
                  │  2. hmac.compare_digest       │
                  │     (presented_header, secret)│
                  │  3. mismatch → return Response│──────► 401 unauthorized
                  │     (plain-text, WARN log)    │         (journald via systemd)
                  │  4. match → call_next(request)│
                  └────────┬──────────────────────┘
                           │
                           ▼
              ┌────────────────────────────────────────┐
              │  Router dispatch                       │
              ├────────────────────────────────────────┤
              │  GET /          → routes.dashboard     │
              │  GET /api/state → routes.state         │
              │  GET /healthz   → routes.healthz       │
              │  GET /openapi.json → 404 (openapi_url=None) ← D-21 FIX
              └────┬───────────────┬───────────────────┘
                   │               │
                   ▼               ▼
          ┌────────────────┐  ┌────────────────────────┐
          │ GET /          │  │ GET /api/state         │
          │ 1. load_state  │  │ 1. load_state          │
          │    (stat X)    │  │ 2. strip _* top-level  │
          │ 2. stat        │  │ 3. JSONResponse +      │
          │    dashboard   │  │    Cache-Control:      │
          │    .html       │  │    no-store            │
          │ 3. stale? ──Y→ │  └────────────────────────┘
          │    render_     │
          │    dashboard   │
          │    (catch exc) │
          │ 4. FileResponse│
          │    (or 503 if  │
          │    missing)    │
          └────────┬───────┘
                   │ reads/writes
                   ▼
          ┌────────────────────────────┐
          │  filesystem                │
          │  - state.json (read-only)  │
          │  - dashboard.html (rw)     │
          └────────────────────────────┘
```

**Data flow trace (authorized GET /):**
1. TLS termination at nginx:443 → HTTP to 127.0.0.1:8000 with `X-Forwarded-For: <real client>` header.
2. uvicorn receives → FastAPI ASGI dispatch.
3. AuthMiddleware.dispatch sees `/` not in `EXEMPT_PATHS`, compares header bytes → match → `call_next`.
4. Router → `web/routes/dashboard.py` handler.
5. Handler: local-import `state_manager`, `dashboard`; `os.stat` on both files; if stale, call `render_dashboard(load_state())` inside try/except; return `FileResponse('dashboard.html')`.
6. Starlette's `FileResponse` adds `Content-Length`, `Last-Modified`, `ETag` automatically.
7. Response bubbles back through middleware stack (no mutations by AuthMiddleware on success).

### Recommended Project Structure
```
trading-signals/
├── web/
│   ├── __init__.py                 # unchanged (Phase 11)
│   ├── app.py                      # MODIFIED: extend create_app() w/ middleware, secret validation, openapi_url=None
│   ├── middleware/
│   │   ├── __init__.py             # NEW: empty module marker (dir reserved in Phase 11 D-03)
│   │   └── auth.py                 # NEW: AuthMiddleware(BaseHTTPMiddleware)
│   └── routes/
│       ├── __init__.py             # MODIFIED: register new routes alongside healthz
│       ├── healthz.py              # UNCHANGED (Phase 11)
│       ├── dashboard.py            # NEW: GET / handler
│       └── state.py                # NEW: GET /api/state handler
├── tests/
│   ├── test_web_healthz.py         # MODIFIED: extend FORBIDDEN_FOR_WEB to NOT forbid 'dashboard'; keep forbidding signal_engine/sizing_engine/system_params/notifier/main/data_fetcher
│   ├── test_web_auth_middleware.py # NEW: D-01..D-06 tests
│   ├── test_web_dashboard.py       # NEW: D-07..D-11 tests
│   ├── test_web_state.py           # NEW: D-12..D-15 tests
│   └── test_web_app_factory.py     # NEW: D-16..D-18 startup validation tests
├── SETUP-DROPLET.md                # MODIFIED: append "Configure auth secret" section (D-19)
└── requirements.txt                # UNCHANGED: no new deps
```

### Pattern 1: BaseHTTPMiddleware subclass with factory-injected secret

**What:** Middleware class captures secret from `create_app()` factory closure, not from `os.environ` at dispatch time.
**When to use:** Hot-path auth check where per-request env-var reads are wasteful AND where test fixtures need deterministic control over the secret value.

**Example:**
```python
# web/middleware/auth.py
# Source: https://starlette.dev/middleware/ + D-01..D-06
'''AuthMiddleware — shared-secret X-Trading-Signals-Auth gate.

Architecture (CLAUDE.md hex-lite + Phase 10 D-15):
  web/middleware/ is an adapter hex (no pure-math imports).
  Allowed: fastapi, starlette, stdlib. No signal_engine/sizing/etc.

Log prefix: [Web] — Phase 11 convention.
'''
import hmac
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

EXEMPT_PATHS = frozenset({'/healthz'})  # D-02
AUTH_HEADER = 'X-Trading-Signals-Auth'  # AUTH-01
UA_TRUNCATE = 120  # D-05 / SC-5


class AuthMiddleware(BaseHTTPMiddleware):
  '''Shared-secret header auth (D-01..D-06).

  NOTE: this middleware does NOT propagate contextvars set in downstream
  handlers back up the middleware chain, due to a known BaseHTTPMiddleware
  limitation. Phase 13 does not use contextvars; if Phase 14+ introduces
  BackgroundTasks from auth-gated routes, migrate to pure ASGI middleware.
  Refs: github.com/Kludex/starlette/issues/2093, discussions/1729.
  '''

  def __init__(self, app: ASGIApp, *, secret: str):
    super().__init__(app)
    self._secret_bytes = secret.encode('utf-8')  # D-03: bytes-typed

  async def dispatch(self, request: Request, call_next):
    # D-02: path-allowlist exemption FIRST
    if request.url.path in EXEMPT_PATHS:
      return await call_next(request)

    presented = request.headers.get(AUTH_HEADER, '').encode('utf-8')
    if not hmac.compare_digest(presented, self._secret_bytes):  # D-03
      self._log_failure(request)  # D-05
      return Response(
        content='unauthorized',
        status_code=401,
        media_type='text/plain; charset=utf-8',
      )  # D-04

    return await call_next(request)

  @staticmethod
  def _log_failure(request: Request) -> None:
    xff = request.headers.get('x-forwarded-for', '')
    # D-05: XFF may be "client, proxy1, proxy2" — first entry is real client
    client_ip = (
      xff.split(',')[0].strip()
      if xff
      else (request.client.host if request.client else '-')
    )
    ua = (request.headers.get('user-agent') or '')[:UA_TRUNCATE]
    logger.warning(
      '[Web] auth failure: ip=%s ua=%r path=%s',
      client_ip,
      ua,
      request.url.path,
    )
```

### Pattern 2: Factory-time secret validation + middleware injection

**What:** `create_app()` validates `WEB_AUTH_SECRET` from env once, then passes secret as kwarg to `add_middleware()`.
**When to use:** Any module-load-time invariant that systemd's Restart=on-failure should surface on startup.

**Example:**
```python
# web/app.py — Phase 13 amendment
import logging
import os

from fastapi import FastAPI

from web.middleware.auth import AuthMiddleware
from web.routes import dashboard as dashboard_route
from web.routes import healthz as healthz_route
from web.routes import state as state_route

logger = logging.getLogger(__name__)

_MIN_SECRET_LEN = 32  # D-17: ≈128 bits entropy via `openssl rand -hex 16`


def _read_auth_secret() -> str:
  '''D-16/D-17: fail-closed if secret missing or too short.'''
  secret = os.environ.get('WEB_AUTH_SECRET', '').strip()
  if not secret:
    raise RuntimeError(
      'WEB_AUTH_SECRET env var is missing or empty — refusing to start. '
      'Add WEB_AUTH_SECRET=<32+ chars> to /home/trader/trading-signals/.env'
    )
  if len(secret) < _MIN_SECRET_LEN:
    raise RuntimeError(
      f'WEB_AUTH_SECRET must be at least {_MIN_SECRET_LEN} characters. '
      'Generate with: openssl rand -hex 16'
    )
  return secret


def create_app() -> FastAPI:
  '''D-16/D-17/D-21: validate secret BEFORE FastAPI() instantiation.'''
  secret = _read_auth_secret()  # raises RuntimeError on missing/short

  application = FastAPI(
    title='Trading Signals',
    description='SPI 200 & AUD/USD mechanical trading signal system',
    version='1.1.0',
    docs_url=None,     # D-21
    redoc_url=None,    # D-21
    openapi_url=None,  # CRITICAL: researcher extension to D-21 — without
                       # this, /openapi.json still leaks the schema.
  )

  # D-06: middleware registration order. Starlette runs in REVERSE of
  # registration, so AuthMiddleware must be LAST (= runs FIRST).
  # Any future middleware (e.g., request-id, compression) MUST be
  # registered BEFORE this line so they wrap around auth.
  healthz_route.register(application)
  dashboard_route.register(application)
  state_route.register(application)

  application.add_middleware(AuthMiddleware, secret=secret)  # D-06 last

  logger.info('[Web] FastAPI app created (Phase 13 — /, /api/state, /healthz; auth=on)')
  return application


app = create_app()
```

### Pattern 3: mtime-based staleness + FileResponse

**What:** Handler compares `os.stat(state.json).st_mtime_ns > os.stat(dashboard.html).st_mtime_ns`; regenerates only on stale; delegates all HTTP caching to `FileResponse`.
**When to use:** Any endpoint that serves a precomputed disk artifact derived from another file.

**Example:**
```python
# web/routes/dashboard.py
# Source: FastAPI docs (custom-response), Phase 13 D-07..D-11
'''GET / — dashboard read endpoint (WEB-05 + D-07..D-11).'''
import logging
import os

from fastapi import FastAPI
from fastapi.responses import FileResponse, PlainTextResponse

logger = logging.getLogger(__name__)

_DASHBOARD_PATH = 'dashboard.html'
_STATE_PATH = 'state.json'


def _is_stale() -> bool:
  '''D-08: state.json mtime > dashboard.html mtime means regen needed.

  Returns True if dashboard.html is missing (caller must handle).
  Returns True if state.json is newer than dashboard.html.
  Returns False if dashboard.html is fresh relative to state.json.
  '''
  try:
    html_mtime = os.stat(_DASHBOARD_PATH).st_mtime_ns
  except FileNotFoundError:
    return True  # caller handles
  try:
    state_mtime = os.stat(_STATE_PATH).st_mtime_ns
  except FileNotFoundError:
    return False  # no state file yet — serve whatever dashboard.html is
  return state_mtime > html_mtime


def register(app: FastAPI) -> None:
  '''Register GET / on the given FastAPI instance.'''

  @app.get('/')
  def get_dashboard():
    from dashboard import render_dashboard  # local import — hex boundary
    from state_manager import load_state

    try:
      if _is_stale():
        render_dashboard(load_state())
    except Exception as exc:  # noqa: BLE001 — D-10: never-crash
      logger.warning(
        '[Web] dashboard regen failed, serving stale: %s: %s',
        type(exc).__name__,
        exc,
      )

    if not os.path.exists(_DASHBOARD_PATH):  # D-10: first-run case
      return PlainTextResponse(
        content='dashboard not ready',
        status_code=503,
        media_type='text/plain; charset=utf-8',
      )

    return FileResponse(
      _DASHBOARD_PATH,
      media_type='text/html; charset=utf-8',
    )
```

### Anti-Patterns to Avoid

- **Using `==` to compare the presented secret to the expected secret.** Timing side-channel even if nginx rate-limits. D-03 mandates `hmac.compare_digest`. Constant time; zero cost.
- **Reading `WEB_AUTH_SECRET` from `os.environ` inside `dispatch()`.** D-18: wasteful on hot path, and breaks test isolation (tests `monkeypatch.setenv` before `create_app()`). Capture once in `__init__`.
- **Reading client IP from `request.client.host` behind nginx.** Returns `127.0.0.1` — useless for audit. D-05: use `X-Forwarded-For` first entry.
- **`docs_url=None, redoc_url=None` alone — forgetting `openapi_url=None`.** `/openapi.json` still leaks the schema. Multiple GitHub discussions confirm this gotcha.
- **Registering `AuthMiddleware` FIRST in `create_app()`.** Starlette executes middleware in REVERSE of registration. D-06: AuthMiddleware LAST so it runs FIRST.
- **Catching the exception from `render_dashboard()` and crashing the handler.** D-10: log WARN, serve stale copy. Only return non-200 if `dashboard.html` itself is absent (and even then, 503 plain text, not 500).
- **Using `HTMLResponse(Path('dashboard.html').read_text())` instead of `FileResponse`.** Loses automatic ETag/Last-Modified; no conditional GET; blocks event loop on read.
- **Writing `dashboard.html` outside `_atomic_write`.** Non-atomic writes can produce torn reads where `FileResponse` streams a half-written file. The existing `dashboard.py` uses atomic tempfile+replace — Phase 13 just calls the existing function.
- **Hand-rolled 401 response without plain-text body.** AUTH-02 explicitly mandates `unauthorized` — no JSON, no WWW-Authenticate.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Constant-time string comparison | `def ct_compare(a, b): ...` | `hmac.compare_digest` (stdlib) | Subtle to get right; stdlib handles length-mismatch dummy-compare to avoid length leak [CITED: docs.python.org/3/library/hmac.html]. |
| File serving with caching headers | Manual ETag calculation + `If-None-Match` handling | `fastapi.responses.FileResponse` | Automatic `Content-Length`, `Last-Modified`, `ETag`, conditional GET [CITED: fastapi.tiangolo.com/advanced/custom-response/#fileresponse]. |
| Client IP extraction from proxy chain | Full XFF parse + RFC 7239 Forwarded handling | First-entry split (D-05) OR uvicorn `--forwarded-allow-ips` | D-03 locked direct-DNS no-CDN (single proxy hop), so first-entry parse is sufficient and simpler than uvicorn ProxyHeaders middleware config churn. |
| Atomic file writes for `state.json` / `dashboard.html` | Manual tempfile + rename sequence | Existing `state_manager._atomic_write` / `dashboard._atomic_write` | Phase 3/5 already verified. Phase 13 only READS; no new write path introduced. |
| JSON serialization for `GET /api/state` | `json.dumps(...)` | `fastapi.responses.JSONResponse` | FastAPI default; supports `headers=` kwarg for `Cache-Control: no-store`. |
| Rate limiting auth brute-force | Python in-process counter / IP blacklist | nginx `limit_req_zone` (deferred — see D-21 Claude's Discretion + deferred ideas) | 128-bit secret + constant-time compare makes brute-force implausible; rate-limit is defense-in-depth at nginx layer. In-process state doesn't survive restarts anyway (see ~/.claude/CLAUDE.md §In-memory state). |

**Key insight:** Phase 13 is 95% composition of stdlib + FastAPI/Starlette primitives. The only original logic is: (1) 12-line middleware `dispatch()`, (2) 5-line mtime staleness helper, (3) 1-line underscore-key strip. Everything else is already written and tested upstream.

## Runtime State Inventory

> Phase 13 is NOT a rename/refactor/migration phase — this section is informational only (one entry: the new env var).

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — state.json is read-only from web tier per Phase 10 D-15. No new writes introduced. | None |
| Live service config | None — no external services configured in this phase (nginx/certbot are Phase 12 scope). | None |
| OS-registered state | None — systemd unit file unchanged by Phase 13 (Phase 11 `trading-signals-web.service` already has `EnvironmentFile=-/etc/trading-signals/.env` which will read the new var). | None — verified by cross-referencing Phase 12 D-18 (`SIGNALS_EMAIL_FROM` added to `.env` with no unit-file changes). |
| Secrets/env vars | **NEW: `WEB_AUTH_SECRET`** (required, ≥32 chars, read by `create_app()` per D-18) | Operator runs `openssl rand -hex 16`, appends to `/home/trader/trading-signals/.env`, `systemctl restart trading-signals-web` per D-19. Documented in SETUP-DROPLET.md plan task. |
| Build artifacts | None — no installed packages change; `hmac` is stdlib. | None |

## Common Pitfalls

### Pitfall 1: `openapi_url` not disabled when `docs_url` + `redoc_url` are
**What goes wrong:** Setting `FastAPI(docs_url=None, redoc_url=None)` hides `/docs` and `/redoc` UI pages — but `/openapi.json` keeps serving the full API schema publicly, defeating D-21 intent.
**Why it happens:** FastAPI treats the three URLs independently. `docs_url` and `redoc_url` are UI HTML endpoints; `openapi_url` is the schema JSON endpoint that both UIs consume [CITED: fastapi.tiangolo.com/how-to/conditional-openapi, GitHub discussions #13249, #4211, #6449, #8169].
**How to avoid:** `create_app()` MUST set all three: `FastAPI(docs_url=None, redoc_url=None, openapi_url=None)`. Plan must include a test: `client.get('/openapi.json').status_code == 404` AND `client.get('/docs').status_code == 404` AND `client.get('/redoc').status_code == 404` — but also note that with auth middleware installed, an unauthenticated request to `/openapi.json` would return 401 before reaching the 404 logic. So the test must either send the valid auth header OR call the factory with auth disabled. Recommend: test with valid header to prove the 404 path, AND a separate test asserting `/openapi.json` gets 401 without auth (proves middleware reaches it).
**Warning signs:** `curl https://.../openapi.json` with auth returns a full JSON schema instead of 404.

### Pitfall 2: `BaseHTTPMiddleware` breaks BackgroundTasks + contextvars propagation
**What goes wrong:** Any `BackgroundTasks` scheduled from a route wrapped by `BaseHTTPMiddleware` may execute with stale contextvars, or after middleware context has been reset. Changes to `contextvars.ContextVar` in the endpoint do not propagate back up the middleware chain.
**Why it happens:** `BaseHTTPMiddleware` runs the downstream app in a separate task via `anyio.TaskGroup`; contextvars are task-scoped in Python and don't propagate upward across task boundaries [CITED: github.com/Kludex/starlette/issues/919, /issues/2093, discussions/1729; starlette PR #1640 "Document BaseHTTPMiddleware bugs"].
**How to avoid:** Phase 13 currently uses NEITHER `BackgroundTasks` NOR `contextvars`. Plan adds a warning comment in `web/middleware/auth.py` so Phase 14+ doesn't accidentally trip it. If Phase 14 introduces BackgroundTasks from `POST /trades/*`, migrate `AuthMiddleware` to pure ASGI middleware (signature `async def __call__(self, scope, receive, send)` with direct message manipulation instead of BaseHTTPMiddleware's Request/Response wrapper).
**Warning signs:** Logs missing that should have fired from BackgroundTasks; contextvars values observed as empty/default in handlers that expected middleware-set values.

### Pitfall 3: `X-Forwarded-For` spoofing without proxy trust chain
**What goes wrong:** An attacker sends a request directly to the origin (bypassing nginx) with a forged `X-Forwarded-For: <victim-ip>` header. The audit log then attributes the failed auth attempt to the victim's IP, potentially poisoning incident investigation.
**Why it happens:** Any HTTP header is client-controlled unless a trusted proxy strips/replaces it. nginx's `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for` APPENDS the real client IP to whatever the client sent — so XFF becomes `<attacker-forged-ip>, <real-client-ip>` [CITED: MDN XFF docs, howhttpworks.com/headers/x-forwarded-for].
**How to avoid in Phase 13 context:**
- Phase 11 binds uvicorn to `127.0.0.1:8000` only. An external attacker CANNOT reach the origin directly — they must go through nginx. So XFF spoofing via direct-to-origin is not a threat in Phase 13.
- However, if Phase 11's binding is ever relaxed (e.g., `--host 0.0.0.0` in a debug config), XFF becomes spoofable. Document this coupling in a plan Pitfall note.
- D-05 takes the FIRST entry of XFF. With Phase 12 nginx direct-proxy (no Cloudflare, no CDN — Phase 12 D-03), the header has exactly one entry (the real client). nginx does NOT append to the chain because there's no pre-existing XFF from a client request (client→nginx→origin, so nginx is the first and only proxy). First entry is correct.
- An alternative is uvicorn's `--forwarded-allow-ips=127.0.0.1` flag, which would let `request.client.host` reflect the real client IP. This requires editing the systemd unit file — outside Phase 13 scope (Phase 11 unit file is fixed). D-05's app-layer read is simpler; remain with it.
**Warning signs:** Audit log shows IPs outside expected geographic range with valid-looking traffic patterns; first-entry IP doesn't match nginx's `$remote_addr` in access logs (run parallel correlation check).

### Pitfall 4: `hmac.compare_digest` type mismatch raises TypeError
**What goes wrong:** Passing `str` and `bytes` mixed (e.g., `hmac.compare_digest(request.headers.get(...), SECRET)` where `SECRET` is a module-level `str`) raises `TypeError: a bytes-like object is required, not 'str'` (or vice versa) — middleware returns 500 instead of 401.
**Why it happens:** `hmac.compare_digest` requires both args to be the SAME type: both `str` OR both `bytes-like` [CITED: docs.python.org/3/library/hmac.html#hmac.compare_digest]. Python 3 is strict about this.
**How to avoid:** Normalize to `bytes` once in `AuthMiddleware.__init__`: `self._secret_bytes = secret.encode('utf-8')`. At compare time: `presented = request.headers.get(AUTH_HEADER, '').encode('utf-8')`. Both sides are `bytes`. If the header is missing, `headers.get(..., '')` returns empty `str` which encodes to empty `bytes` — compare_digest returns False (different length from secret) which triggers 401. Correct behavior.
**Warning signs:** Integration tests raise `TypeError` on any request without the header; middleware never returns 401 — always 500.

### Pitfall 5: `hmac.compare_digest` length mismatch — still constant-time enough
**What goes wrong:** Assuming that lengths-differ comparison leaks the expected secret's length, because "short-circuit on length" is a classic side-channel.
**Why it happens (actually doesn't):** `hmac.compare_digest` DOES return False immediately on length mismatch — but still performs a dummy compare across the shorter length to minimize information leakage [CITED: docs.python.org/3/library/hmac.html: "If a and b are of different lengths, or if an error occurs, a timing attack could theoretically reveal information about the types and lengths of a and b — but not their values"]. Length IS leaked, but value is not, and 128-bit entropy + nginx rate-limit makes the attack infeasible regardless.
**How to avoid:** Don't over-engineer. The stdlib is the right tool. Don't add a `len(presented) == len(secret)` pre-check — that would add a DIFFERENT timing signal. Just call compare_digest directly.
**Warning signs:** None — this is the "solved" path. The pitfall is over-engineering away from stdlib.

### Pitfall 6: Stale `dashboard.html` serves after a failed regen
**What goes wrong:** `render_dashboard()` raises (e.g., state schema mismatch, disk-full); handler catches → serves last good copy. Operator sees yesterday's data without realizing today's signal ran but rendered-broke.
**Why it happens:** D-10 explicitly trades "crash the endpoint" for "serve stale + WARN log". Single-operator tool; operator checks `journalctl -u trading-signals-web | grep 'regen failed'` to notice.
**How to avoid:** Document the trade-off in SETUP-DROPLET.md §Monitoring. Optionally, add a `Last-Rendered: <iso-datetime>` header on the response so the operator can eyeball the header. NOT locked in D-10 — raise as a follow-up if operator experience reveals the blind spot.
**Warning signs:** Dashboard "Last updated" timestamp (rendered by `dashboard.py::_render_header`) hasn't changed in >24h despite state.json showing a recent `last_run`.

### Pitfall 7: Tests that instantiate `create_app()` without `monkeypatch.setenv('WEB_AUTH_SECRET', ...)` first
**What goes wrong:** Test collection or setup calls `create_app()` → `RuntimeError: WEB_AUTH_SECRET env var is missing or empty` → entire test module fails to import.
**Why it happens:** D-18 locks secret-reading at `create_app()` time; the existing Phase 11 pytest fixture `app_instance` at tests/test_web_healthz.py:22 calls `create_app()` without pre-setting the env var. Phase 13 must fix this fixture.
**How to avoid:** Add a `conftest.py` autouse fixture (or per-test-module fixture) that sets a sentinel `WEB_AUTH_SECRET` BEFORE the `create_app()` import/call:
```python
# tests/conftest.py or tests/test_web_auth_middleware.py
@pytest.fixture
def auth_secret(monkeypatch):
  secret = 'a' * 32  # 32 chars per D-17
  monkeypatch.setenv('WEB_AUTH_SECRET', secret)
  return secret

@pytest.fixture
def app_instance(auth_secret):  # depends on auth_secret
  from web.app import create_app
  return create_app()
```
Note: the Phase 11 `test_web_healthz.py::app_instance` fixture MUST be updated in the same commit as Phase 13 — otherwise Phase 11 tests break after `create_app()` starts requiring the secret. Plan task: "Update Phase 11 healthz fixtures to setenv WEB_AUTH_SECRET before create_app()."
**Warning signs:** `pytest tests/test_web_*.py` fails at collection with `RuntimeError` traceback referencing `_read_auth_secret`.

### Pitfall 8: `mtime_ns` precision on non-ext4 filesystems
**What goes wrong:** On some filesystems (older ext3, some FUSE mounts), `st_mtime_ns` has second- or millisecond-granularity. A regen + fetch that happens inside the same granularity window shows `state_mtime == html_mtime` → `is_stale()` returns False even though state was just updated.
**Why it happens:** Filesystem-dependent. Linux ext4 has nanosecond mtime by default; Windows NTFS has 100ns; older filesystems were 1-second.
**How to avoid in Phase 13 context:**
- Production droplet is Ubuntu 22.04+ on DigitalOcean (Phase 11 baseline) — ext4 with nanosecond mtime. Verified: `stat -c %y` on any file shows sub-second precision.
- Comparison in D-08 is strict `>` not `>=`. If both mtimes are identical, the handler does NOT regenerate. That's a non-issue because:
  1. If state.json was just written, dashboard.html may still be older (from last signal run) → strict `>` still triggers regen. Correct.
  2. If both are written in the same call (signal loop writes state.json then dashboard.html), dashboard.html mtime is LATER → strict `>` says "not stale". Correct.
  3. Pathological case: identical mtime_ns from two separate writes within the same second on a coarse filesystem — handler doesn't regen. On next request 1+s later, new write arrives, regen triggers. Acceptable lag.
- Empirical verification: `os.replace` preserves source mtime_ns to destination on POSIX (tested 2026-04-25 on darwin; documented to work the same on Linux).
**Warning signs:** Operator sees dashboard content that doesn't reflect a recent trade-record write, but the file timestamps show state.json was indeed newer — in that case, `touch dashboard.html -d @0` to force staleness and confirm regen path works.

### Pitfall 9: Middleware registration order — declared LAST means runs FIRST
**What goes wrong:** Developer adds AuthMiddleware EARLY in `create_app()` (intuitive "setup auth first"), but Starlette executes in REVERSE of registration order — so a later-registered middleware (e.g., compression) wraps AuthMiddleware and runs first, delivering compressed 401 responses that may confuse clients.
**Why it happens:** Starlette `add_middleware()` prepends to the stack; the outermost (most recently added) runs first [CITED: starlette.dev/middleware, fastapi.tiangolo.com/advanced/middleware]. Counter-intuitive but consistent.
**How to avoid:** D-06 locks "AuthMiddleware registered LAST". Plan includes a comment in `create_app()` explicitly stating this invariant. If Phase 14+ adds a `RequestIDMiddleware` or `CompressionMiddleware`, they MUST go BEFORE the AuthMiddleware line in `create_app()`.
**Warning signs:** Responses include a middleware's custom header on 401 responses — indicates that middleware ran before auth and should have been registered later.

## Code Examples

Verified patterns from official sources:

### Middleware with custom __init__ for config injection
```python
# Source: https://starlette.dev/middleware/#basehttpmiddleware
# D-18: secret captured in __init__, not read per-request
from starlette.middleware.base import BaseHTTPMiddleware

class AuthMiddleware(BaseHTTPMiddleware):
  def __init__(self, app, *, secret: str):
    super().__init__(app)
    self._secret_bytes = secret.encode('utf-8')

  async def dispatch(self, request, call_next):
    # ... use self._secret_bytes
    ...
```

### Registering middleware with kwargs
```python
# Source: https://www.starlette.io/middleware/
# D-06: registration order + kwargs pass-through
app.add_middleware(AuthMiddleware, secret=the_secret)
# Starlette forwards `secret=` to AuthMiddleware.__init__ alongside `app`
```

### FileResponse with explicit media type
```python
# Source: https://fastapi.tiangolo.com/advanced/custom-response/#fileresponse
from fastapi.responses import FileResponse

@app.get('/')
def get_dashboard():
  return FileResponse(
    'dashboard.html',
    media_type='text/html; charset=utf-8',
  )
# Automatically sets Content-Length, Last-Modified, ETag.
# Supports conditional GET (If-None-Match / If-Modified-Since → 304).
```

### JSONResponse with custom headers
```python
# Source: https://fastapi.tiangolo.com/advanced/custom-response/#jsonresponse
# D-13: Cache-Control: no-store prevents browser/proxy caching
from fastapi.responses import JSONResponse

@app.get('/api/state')
def get_state():
  from state_manager import load_state
  state = load_state()
  clean = {k: v for k, v in state.items() if not k.startswith('_')}  # D-12
  return JSONResponse(
    content=clean,
    headers={'Cache-Control': 'no-store'},
  )
```

### hmac.compare_digest with both-bytes invariant
```python
# Source: https://docs.python.org/3/library/hmac.html#hmac.compare_digest
import hmac

# Both args must be SAME TYPE (both str or both bytes). Encode once.
secret_bytes = secret.encode('utf-8')
presented_bytes = request.headers.get('X-Auth', '').encode('utf-8')

if not hmac.compare_digest(presented_bytes, secret_bytes):
  # 401 path
  ...
```

### TestClient with factory-injected app
```python
# Source: https://fastapi.tiangolo.com/reference/testclient/
# Pitfall 7: monkeypatch.setenv BEFORE create_app()
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def valid_secret():
  return 'a' * 32  # meets D-17 minimum

@pytest.fixture
def client(monkeypatch, valid_secret):
  monkeypatch.setenv('WEB_AUTH_SECRET', valid_secret)
  from web.app import create_app
  return TestClient(create_app())

def test_auth_missing_returns_401(client):
  r = client.get('/')
  assert r.status_code == 401
  assert r.text == 'unauthorized'
  assert r.headers['content-type'].startswith('text/plain')

def test_auth_valid_returns_200(client, valid_secret, monkeypatch):
  # dashboard.html must exist for 200 — monkeypatch os.path.exists
  monkeypatch.setattr('os.path.exists', lambda p: True)
  # ... plus monkeypatch FileResponse to bypass actual file read, or
  # use a tmp dashboard.html fixture
  ...
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `@app.middleware('http')` function decorator | `BaseHTTPMiddleware` subclass (for testability) | Always recommended for stateful middleware; decorator still fine for stateless | Phase 13 picks subclass per CONTEXT Claude's Discretion — cleaner factory injection of secret. |
| Trust `request.client.host` blindly | Explicit `X-Forwarded-For` parse (app layer) OR uvicorn `--forwarded-allow-ips` (infra layer) | FastAPI 0.90+ / uvicorn 0.15+ documented best practice | Phase 13 chooses app-layer parse (D-05) — no systemd changes. |
| Writing HTML files to the filesystem | Still the standard approach for single-operator/small-scale | unchanged | `dashboard.py` established this pattern Phase 5; Phase 13 preserves. |
| Plain `==` for secret comparison | `hmac.compare_digest` | PEP 466 (Python 3.3+) | Mandated by D-03. |
| Docs URLs enabled by default | Explicit disable via `docs_url=None, redoc_url=None, openapi_url=None` | All three needed since FastAPI 0.52+ | D-21 + researcher extension. |

**Deprecated/outdated:**
- FastAPI `@app.on_event('startup')` / `@app.on_event('shutdown')` — deprecated in favor of `lifespan` context manager. Phase 13 doesn't use either; factory validates secret synchronously before `FastAPI()` is instantiated.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `os.replace()` on Ubuntu ext4 preserves source mtime_ns to destination (empirical test was on darwin HFS/APFS) | Pitfall 8 | LOW — POSIX `rename(2)` semantics specify metadata transfer with the inode; Linux ext4 behavior is consistent with darwin. If wrong, staleness check gives false positives/negatives; operator workaround is `touch dashboard.html`. |
| A2 | Operator's production droplet filesystem has nanosecond mtime (ext4 default) | Pitfall 8 | LOW — DigitalOcean standard Ubuntu 22.04 droplets ship with ext4. |
| A3 | nginx from Phase 12 sends exactly one `X-Forwarded-For` entry (no Cloudflare in front) | D-05, Pitfall 3 | LOW — Phase 12 D-03 explicitly locks "no Cloudflare / CDN". If operator adds Cloudflare later, XFF parsing must switch to "second-to-last entry" (last is Cloudflare's IP). Flag as follow-up if Cloudflare ever proposed. |
| A4 | `fastapi==0.136.1` still ships Starlette with `BaseHTTPMiddleware` (not removed) | Pattern 1 | NONE — verified via fastapi/starlette release-notes; still present. BaseHTTPMiddleware "deprecation" discussions are ongoing on github but no removal planned. |
| A5 | `render_dashboard()` completes in ~50ms typical under `workers=1` (operator won't notice double-regen race per D-11) | D-11 | LOW — Phase 5 dashboard benchmarks showed <100ms render times. Even 500ms double-work is imperceptible to a single operator. |

## Open Questions

1. **Should the planner add a test that asserts `/openapi.json` returns 404 after the `openapi_url=None` fix?**
   - What we know: CONTEXT D-21 as written only names `docs_url` and `redoc_url`. Research shows `openapi_url` must also be None.
   - What's unclear: Does the planner want this captured as an amendment to D-21, or as a new D-22?
   - Recommendation: Add as a plan-level decision in the first plan, label it "D-22 extension to D-21: set `openapi_url=None` too; test asserts GET /openapi.json → 404 with valid auth". Phase 13 CONTEXT says "Folded Todos: None", so no prior decision to contradict — this is a new finding from research.

2. **Should the `AuthMiddleware` include an inline comment about the BackgroundTasks/contextvars quirks even though Phase 13 doesn't use them?**
   - What we know: The quirk is well-documented; Phase 13 is safe; Phase 14 adds `POST /trades/*` which may use BackgroundTasks.
   - What's unclear: Is a forward-reference comment useful or noise?
   - Recommendation: Include it. It's 4 lines and catches a future-phase foot-gun preemptively.

3. **Is the Phase 11 `test_web_healthz.py::app_instance` fixture update a Phase 13 task or should it be a Phase 11 follow-up?**
   - What we know: After D-16 locks fail-closed on missing secret, `create_app()` raises on any call that doesn't first set `WEB_AUTH_SECRET`. All Phase 11 healthz tests break.
   - What's unclear: Scope ownership.
   - Recommendation: Phase 13 owns it. Plan task explicitly updates `tests/test_web_healthz.py` to setenv the secret before `create_app()` — and extends `TestWebHexBoundary.FORBIDDEN_FOR_WEB` to no longer forbid `dashboard` (new allowed import per Phase 13 hex-boundary extension). Add a regression assertion that `dashboard` is NOT in the forbidden set.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11 | All web code | ✓ | 3.11.8 (pinned in `.python-version`) | — |
| `fastapi==0.136.1` | `create_app()` | ✓ | 0.136.1 (requirements.txt) | — |
| `uvicorn[standard]==0.46.0` | systemd ExecStart | ✓ | Phase 11 already installed | — |
| `httpx==0.28.1` | Tests (TestClient dep) | ✓ | Phase 11 already installed | — |
| Python stdlib `hmac` | `AuthMiddleware.dispatch` | ✓ | 3.11 stdlib | — |
| Python stdlib `os.stat` | `_is_stale` helper | ✓ | 3.11 stdlib | — |
| `openssl` CLI | Operator runbook secret generation (D-19) | ✓ (expected on any Ubuntu droplet) | system | Fallback: `python3 -c "import secrets; print(secrets.token_hex(16))"` produces equivalent 32-char hex |
| nginx (Phase 12) | End-to-end HTTPS testing | Assumed ✓ after Phase 12 droplet setup | — | Not needed for pytest suite (TestClient bypasses nginx) |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** Only `openssl` — fallback `python3 -c "import secrets"` is documented in the SETUP-DROPLET.md plan task.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.3.3 + pytest-freezer 0.4.9 |
| Config file | none (pytest discovers `tests/` by default) |
| Quick run command | `pytest tests/test_web_auth_middleware.py tests/test_web_dashboard.py tests/test_web_state.py tests/test_web_app_factory.py -x` |
| Full suite command | `pytest -x` |
| Existing infra | `tests/conftest.py`, TestClient fixtures established in Phase 11 `test_web_healthz.py`; pattern re-used for Phase 13 |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AUTH-01 | GET / without header → 401 | unit (TestClient) | `pytest tests/test_web_auth_middleware.py::TestAuthRequired::test_missing_header_returns_401 -x` | ❌ Wave 0 (new file) |
| AUTH-01 | GET /api/state with wrong header → 401 | unit | `pytest tests/test_web_auth_middleware.py::TestAuthRequired::test_wrong_header_returns_401 -x` | ❌ Wave 0 |
| AUTH-01 | GET / with correct header → 200 (or 503 if dashboard missing) | unit | `pytest tests/test_web_auth_middleware.py::TestAuthPasses::test_correct_header_passes_through -x` | ❌ Wave 0 |
| AUTH-01 | Uses `hmac.compare_digest` (AST guard against `==`) | static | `pytest tests/test_web_auth_middleware.py::TestConstantTimeCompare::test_uses_compare_digest_not_equality -x` | ❌ Wave 0 |
| AUTH-01 | `/healthz` exempt — 200 without header | unit | `pytest tests/test_web_auth_middleware.py::TestExemption::test_healthz_bypasses_auth -x` | ❌ Wave 0 |
| AUTH-02 | 401 body is literal `unauthorized` text | unit | `pytest tests/test_web_auth_middleware.py::TestUnauthorizedResponse::test_body_is_plain_text_unauthorized -x` | ❌ Wave 0 |
| AUTH-02 | 401 Content-Type is `text/plain; charset=utf-8` | unit | `pytest tests/test_web_auth_middleware.py::TestUnauthorizedResponse::test_content_type -x` | ❌ Wave 0 |
| AUTH-02 | No `WWW-Authenticate` header | unit | `pytest tests/test_web_auth_middleware.py::TestUnauthorizedResponse::test_no_www_authenticate_header -x` | ❌ Wave 0 |
| AUTH-03 | WARN log on failure contains IP + UA + path | unit (caplog) | `pytest tests/test_web_auth_middleware.py::TestAuditLog::test_warn_log_emitted_on_failure -x` | ❌ Wave 0 |
| AUTH-03 | IP extracted from `X-Forwarded-For` first entry | unit | `pytest tests/test_web_auth_middleware.py::TestAuditLog::test_ip_from_xff_first_entry -x` | ❌ Wave 0 |
| AUTH-03 | UA truncated to 120 chars | unit | `pytest tests/test_web_auth_middleware.py::TestAuditLog::test_ua_truncated_to_120 -x` | ❌ Wave 0 |
| AUTH-03 | UA escaped with `%r` (control chars don't break journald line) | unit | `pytest tests/test_web_auth_middleware.py::TestAuditLog::test_ua_repr_escapes_control_chars -x` | ❌ Wave 0 |
| AUTH-03 | Falls back to `request.client.host` when XFF absent | unit | `pytest tests/test_web_auth_middleware.py::TestAuditLog::test_ip_fallback_when_no_xff -x` | ❌ Wave 0 |
| WEB-05 | GET / serves dashboard.html with text/html Content-Type | unit | `pytest tests/test_web_dashboard.py::TestDashboardResponse::test_content_type_is_html -x` | ❌ Wave 0 |
| WEB-05 | Fresh dashboard.html (html mtime > state mtime) is NOT regenerated | unit | `pytest tests/test_web_dashboard.py::TestStaleness::test_fresh_dashboard_not_regenerated -x` | ❌ Wave 0 |
| WEB-05 | Stale dashboard.html (state mtime > html mtime) triggers regen | unit | `pytest tests/test_web_dashboard.py::TestStaleness::test_stale_dashboard_triggers_regen -x` | ❌ Wave 0 |
| WEB-05 | Render-failure → serve stale + WARN log | unit | `pytest tests/test_web_dashboard.py::TestRenderFailure::test_exception_serves_stale_with_warn -x` | ❌ Wave 0 |
| WEB-05 | Missing dashboard.html → 503 `dashboard not ready` | unit | `pytest tests/test_web_dashboard.py::TestFirstRun::test_missing_dashboard_returns_503 -x` | ❌ Wave 0 |
| WEB-05 | FileResponse sets Last-Modified header | unit | `pytest tests/test_web_dashboard.py::TestDashboardResponse::test_last_modified_header_present -x` | ❌ Wave 0 |
| WEB-06 | GET /api/state Content-Type is application/json | unit | `pytest tests/test_web_state.py::TestStateResponse::test_content_type_is_json -x` | ❌ Wave 0 |
| WEB-06 | Response body excludes top-level underscore-prefixed keys | unit | `pytest tests/test_web_state.py::TestStateResponse::test_strips_underscore_prefixed_top_level_keys -x` | ❌ Wave 0 |
| WEB-06 | Nested dicts keep underscore-prefixed keys (only top-level stripped) | unit | `pytest tests/test_web_state.py::TestStateResponse::test_preserves_nested_underscore_keys -x` | ❌ Wave 0 |
| WEB-06 | Cache-Control: no-store header present | unit | `pytest tests/test_web_state.py::TestStateResponse::test_cache_control_no_store -x` | ❌ Wave 0 |
| WEB-06 | Compact JSON (no indent) | unit | `pytest tests/test_web_state.py::TestStateResponse::test_response_is_compact_json -x` | ❌ Wave 0 |
| D-16 | `create_app()` raises RuntimeError when WEB_AUTH_SECRET absent | unit | `pytest tests/test_web_app_factory.py::TestSecretValidation::test_missing_secret_raises -x` | ❌ Wave 0 |
| D-16 | `create_app()` raises RuntimeError when WEB_AUTH_SECRET empty string | unit | `pytest tests/test_web_app_factory.py::TestSecretValidation::test_empty_secret_raises -x` | ❌ Wave 0 |
| D-17 | `create_app()` raises RuntimeError when secret < 32 chars | unit | `pytest tests/test_web_app_factory.py::TestSecretValidation::test_short_secret_raises -x` | ❌ Wave 0 |
| D-17 | `create_app()` accepts secret of exactly 32 chars | unit | `pytest tests/test_web_app_factory.py::TestSecretValidation::test_32_char_secret_accepted -x` | ❌ Wave 0 |
| D-21+ | /docs returns 404 (with valid auth) | unit | `pytest tests/test_web_app_factory.py::TestDocsDisabled::test_docs_url_disabled -x` | ❌ Wave 0 |
| D-21+ | /redoc returns 404 (with valid auth) | unit | `pytest tests/test_web_app_factory.py::TestDocsDisabled::test_redoc_url_disabled -x` | ❌ Wave 0 |
| D-21+ | **/openapi.json returns 404 (with valid auth) — RESEARCH EXTENSION** | unit | `pytest tests/test_web_app_factory.py::TestDocsDisabled::test_openapi_url_disabled -x` | ❌ Wave 0 |
| D-21+ | /openapi.json returns 401 (without auth — proves middleware blocks before 404) | unit | `pytest tests/test_web_app_factory.py::TestDocsDisabled::test_openapi_blocked_by_auth_when_unauthenticated -x` | ❌ Wave 0 |
| Hex boundary | `web/middleware/auth.py` does NOT import signal_engine/sizing/main/notifier | static AST | `pytest tests/test_web_healthz.py::TestWebHexBoundary::test_web_modules_do_not_import_hex_core -x` | ✅ (existing, MODIFIED) |
| Hex boundary | `web/routes/dashboard.py` import of `dashboard.render_dashboard` is ALLOWED (not in forbidden set) | static AST | `pytest tests/test_web_healthz.py::TestWebHexBoundary::test_web_modules_do_not_import_hex_core -x` | ✅ (existing, FORBIDDEN_FOR_WEB constant updated) |
| Hex boundary | `state_manager` and `dashboard` imports are LOCAL (not module-top) | static AST | `pytest tests/test_web_healthz.py::TestWebHexBoundary::test_web_app_does_not_import_state_manager_at_module_top -x` | ✅ (existing, expanded to check `dashboard` too) |

### Sampling Rate
- **Per task commit:** `pytest tests/test_web_auth_middleware.py tests/test_web_dashboard.py tests/test_web_state.py tests/test_web_app_factory.py -x` (should be <5 seconds)
- **Per wave merge:** `pytest tests/test_web*.py -x` (Phase 11 + Phase 13 web tests — expect ~10 seconds)
- **Phase gate:** `pytest -x` (full suite — Phase 1-13; expect ~20 seconds baseline)

### External Test Surfaces (not in the automated suite)
These are verified by the operator during SETUP-DROPLET.md execution, not by pytest:
- **nginx X-Forwarded-For passthrough** — Phase 12 SETUP-HTTPS.md already verifies nginx sets `X-Forwarded-For $proxy_add_x_forwarded_for` in its `proxy_set_header` directive. Phase 13 audit-log tests mock XFF at the TestClient level; real XFF propagation is verified end-to-end by operator running `curl -H "X-Forgery: fake" https://signals.<domain>/` and then `journalctl -u trading-signals-web | grep 'auth failure'` to confirm IP was extracted correctly.
- **systemd Restart=on-failure on missing secret** — operator removes `WEB_AUTH_SECRET` from `.env`, `systemctl restart trading-signals-web`, confirms `journalctl` shows `RuntimeError: WEB_AUTH_SECRET env var is missing or empty — refusing to start` and the unit is in `failed` state. Documented in SETUP-DROPLET.md §Troubleshooting.
- **Curl against real HTTPS endpoint** — post-deploy operator runs: `curl -sI https://signals.<domain>/` returns 401; `curl -sI -H "X-Trading-Signals-Auth: <secret>" https://signals.<domain>/` returns 200. This is the SC-1 verification step from ROADMAP §Phase 13.

### Wave 0 Gaps
- [ ] `tests/test_web_auth_middleware.py` — covers AUTH-01..AUTH-03 (5 test classes: TestAuthRequired, TestAuthPasses, TestExemption, TestUnauthorizedResponse, TestAuditLog, TestConstantTimeCompare)
- [ ] `tests/test_web_dashboard.py` — covers WEB-05 (4 test classes: TestDashboardResponse, TestStaleness, TestRenderFailure, TestFirstRun)
- [ ] `tests/test_web_state.py` — covers WEB-06 (1 test class: TestStateResponse)
- [ ] `tests/test_web_app_factory.py` — covers D-16/D-17/D-21+ (2 test classes: TestSecretValidation, TestDocsDisabled)
- [ ] `tests/test_web_healthz.py` — MODIFY: update `app_instance` fixture to setenv `WEB_AUTH_SECRET` (Pitfall 7); update `TestWebHexBoundary.FORBIDDEN_FOR_WEB` to remove `dashboard` from forbidden set (dashboard is now an allowed adapter import per D-07); extend `test_web_app_does_not_import_state_manager_at_module_top` to also check `dashboard` stays local-import
- [ ] Framework install — no install needed (pytest and TestClient already in Phase 11 baseline)

### Test Fixture Architecture
A recommended conftest or shared fixture pattern for Phase 13:
```python
# tests/test_web_auth_middleware.py (or a shared conftest)
import pytest
from fastapi.testclient import TestClient

VALID_SECRET = 'a' * 32  # meets D-17 minimum of 32 chars

@pytest.fixture
def valid_secret():
  return VALID_SECRET

@pytest.fixture
def client_with_auth(monkeypatch, valid_secret):
  '''App instance with secret preset; tests use c.get(..., headers={'X-Trading-Signals-Auth': VALID_SECRET}).'''
  monkeypatch.setenv('WEB_AUTH_SECRET', valid_secret)
  # also stub state_manager.load_state to a benign value (see test_web_healthz.py::_stub_load_state)
  import state_manager
  def _stub(*_a, **_kw):
    from state_manager import reset_state
    return reset_state()
  monkeypatch.setattr(state_manager, 'load_state', _stub)
  from web.app import create_app
  return TestClient(create_app())

@pytest.fixture
def auth_headers(valid_secret):
  return {'X-Trading-Signals-Auth': valid_secret}
```

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V1 Architecture | yes | Hex-lite boundary already enforced; Phase 13 adds no new cross-boundary I/O sites. |
| V2 Authentication | yes (central to phase) | Shared-secret header with constant-time compare — `hmac.compare_digest` (Python stdlib). No password storage, no multi-factor (single-operator tool, explicit PROJECT.md constraint). |
| V3 Session Management | no | Stateless auth per request; no cookies, no sessions. Hard constraint from PROJECT.md. |
| V4 Access Control | partial | Single role (authenticated vs not). `/healthz` explicit exemption is the only access-control decision. No RBAC. |
| V5 Input Validation | partial | GET endpoints have no body input. Header presence is the only input, validated by middleware. Path-based dispatch via FastAPI router. Phase 14 (TRADE POSTs) is where input validation becomes critical. |
| V6 Cryptography | yes | `hmac.compare_digest` (NEVER hand-roll). 128-bit entropy secret. No key derivation — the shared secret IS the auth credential. |
| V7 Error Handling | yes | 401 body is minimal (`unauthorized`) — no stack traces, no header hints. Fail-closed on missing secret (RuntimeError at boot). Exception in render → log + serve stale (D-10). |
| V8 Data Protection | partial | TLS at nginx (Phase 12); no at-rest encryption of `state.json` or `dashboard.html` (single-operator, trusted filesystem). `Cache-Control: no-store` on /api/state prevents intermediary caching. |
| V9 Communications | yes | HTTPS enforced via HSTS at nginx (Phase 12 D-11). HSTS `max-age=31536000; includeSubDomains`. Phase 13 inherits; doesn't re-set. |
| V10 Malicious Code | no | No user-supplied code executed; no file uploads. |
| V11 Business Logic | no | Read-only endpoints in Phase 13; no state mutation. |
| V12 Files and Resources | partial | `FileResponse('dashboard.html')` — path is HARDCODED (not user-controlled), so no path traversal risk. Dashboard file is trusted content written by the same repo's `dashboard.render_dashboard`. |
| V13 API | partial | `GET /api/state` returns structured JSON with stable schema; CORS is not set (default: no Access-Control-Allow-Origin, which is secure-by-default for a single-operator tool). `docs_url=None, redoc_url=None, openapi_url=None` removes schema introspection. |
| V14 Configuration | yes | `WEB_AUTH_SECRET` required, validated at boot (D-16/D-17). Fail-closed pattern. Systemd `EnvironmentFile=-/etc/trading-signals/.env` with optional prefix (Phase 11 D-11). Operator runbook documents secret generation. |

### Known Threat Patterns for FastAPI + Shared-Secret Header Behind nginx

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Timing attack on secret compare | Information Disclosure | `hmac.compare_digest` (D-03) — constant-time; nginx rate-limit as defense-in-depth |
| Secret brute-force | Tampering | 128-bit entropy (D-17 enforces via 32-char minimum) + nginx rate-limit (D-10 of Phase 12; extend to `/` and `/api/state` as follow-up per Claude's Discretion) |
| Secret exfiltration via logs | Information Disclosure | Never log `WEB_AUTH_SECRET` or presented auth header value; D-05 log format is `ip=%s ua=%r path=%s` — no auth-value field |
| OpenAPI schema leak | Information Disclosure | `openapi_url=None` + `docs_url=None` + `redoc_url=None` (D-21 + research extension) |
| Stale dashboard serving outdated position data | Repudiation / Information Disclosure | Cache-Control: no-store on /api/state (D-13); dashboard mtime regen (D-07/D-08); WARN log on regen failure (D-10) |
| X-Forwarded-For spoofing for audit log poisoning | Repudiation | Phase 11 binds uvicorn to `127.0.0.1:8000` — direct-to-origin unreachable; only nginx's single XFF entry arrives (D-05 first-entry parse is safe) |
| Secret in git history | Information Disclosure | `WEB_AUTH_SECRET` lives in `.env` (gitignored); SETUP-DROPLET.md D-19 generates on the droplet; never committed |
| Crash info in 401 response | Information Disclosure | 401 body is literal string `unauthorized`; no stack trace; FastAPI default exception handler is bypassed because middleware returns `Response` directly (not raises HTTPException) |
| CSRF via authenticated GETs | Tampering | Phase 13 has no mutation endpoints (Phase 14 scope); GET semantics are safe per HTTP spec |
| XSS via dashboard HTML | Cross-site (STRIDE: Tampering) | `dashboard.py::_render_*` already escapes via `html.escape()` (Phase 5 convention) — Phase 13 `FileResponse` serves pre-rendered HTML; no new user input in Phase 13 means no new XSS surface |

### Additional Notes
- **Shared secret vs OAuth tradeoff:** Accepted per PROJECT.md v1.1 hard constraint. OAuth would require session storage, token rotation, redirect URLs — massively overkill for single-operator. Shared secret is auditable (`grep WEB_AUTH_SECRET`), testable (no mock OAuth server needed), and fits the threat model (single trusted operator, nginx HTTPS, rate-limited).
- **Rotation posture:** Operator-manual; 3 commands (generate, edit .env, restart). Documented but not tooled. Acceptable for v1.1; revisit if team grows.

## Sources

### Primary (HIGH confidence)
- Context7 `/kludex/starlette` — BaseHTTPMiddleware definition, middleware registration order, add_middleware signature [VERIFIED: Context7 query 2026-04-25]
- Context7 `/fastapi/fastapi` — FileResponse (automatic ETag/Last-Modified/Content-Length), docs_url/redoc_url/openapi_url disabling, middleware decorator [VERIFIED: Context7 query 2026-04-25]
- Python stdlib docs — `hmac.compare_digest` semantics (bytes/str type requirement, length-mismatch dummy compare) [CITED: docs.python.org/3/library/hmac.html#hmac.compare_digest]
- PyPI registry — `fastapi==0.136.1` confirmed latest [VERIFIED: pip index versions fastapi 2026-04-25; 136 versions available]
- Empirical test — `os.replace()` preserves source mtime_ns to destination [VERIFIED: tested on darwin 25.4.0 2026-04-25; POSIX rename(2) semantics]

### Secondary (MEDIUM confidence — WebSearch verified with official source)
- FastAPI tutorial: middleware (`@app.middleware('http')` decorator pattern) [CITED: fastapi.tiangolo.com/tutorial/middleware]
- FastAPI tutorial: conditional OpenAPI (`openapi_url=None` disables schema) [CITED: fastapi.tiangolo.com/how-to/conditional-openapi]
- Uvicorn deployment: `--forwarded-allow-ips` flag for X-Forwarded-For trust [CITED: uvicorn.dev/deployment]
- GitHub issues/discussions: BaseHTTPMiddleware BackgroundTasks bug [CITED: github.com/Kludex/starlette/issues/919, /issues/2093, /discussions/1729, encode/starlette#1640]
- MDN X-Forwarded-For docs [CITED: developer.mozilla.org/en-US/docs/Web/HTTP/Headers/X-Forwarded-For]
- FastAPI GitHub discussion #13249: `docs_url=None` behavior [CITED: github.com/fastapi/fastapi/discussions/13249]
- FastAPI GitHub discussion #4211, #6449, #8169: openapi.json leakage when only docs_url disabled [CITED]

### Tertiary (LOW confidence — WebSearch only, unverified against primary)
- None — every finding in this document is backed by either Context7, official docs, or empirical test.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — Context7 + pip index cross-verified; all versions pinned already
- Architecture: HIGH — every pattern sourced from FastAPI/Starlette official docs; 3 code examples copied verbatim from docs
- Pitfalls: HIGH — each pitfall has an authoritative source; Pitfall 1 (openapi_url) is a known gotcha with multiple GitHub confirmations; Pitfall 2 (BaseHTTPMiddleware) is documented in Starlette source PR #1640
- Security domain: HIGH — ASVS categorization is deductive from the phase scope (no auth, no sessions per PROJECT.md; single-secret, TLS at nginx)
- Runtime state: HIGH — only one new env var; no data migrations

**Research date:** 2026-04-25
**Valid until:** 2026-05-25 (30 days — FastAPI/Starlette are mature and stable; re-verify pinned versions if execution slips past this)

---

## RESEARCH COMPLETE

### Key Findings (for orchestrator)

1. CONTEXT.md D-01..D-21 are comprehensive and correct. Research adds ONE material extension: **D-21 must also include `openapi_url=None`** (research shows `docs_url=None, redoc_url=None` alone leaves `/openapi.json` publicly accessible).
2. `BaseHTTPMiddleware` is safe for Phase 13 (no BackgroundTasks, no contextvars), but planner should add a forward-warning comment for Phase 14.
3. `X-Forwarded-For` first-entry parse (D-05) is correct behind Phase 12 nginx (no Cloudflare per D-03). Direct-to-origin XFF spoofing is blocked because uvicorn binds `127.0.0.1:8000` only.
4. Phase 11 test fixture `app_instance` MUST be updated in Phase 13 scope to setenv `WEB_AUTH_SECRET` before `create_app()` — otherwise Phase 11 tests break after D-16 fail-closed lock.
5. `TestWebHexBoundary.FORBIDDEN_FOR_WEB` MUST be updated to remove `dashboard` from forbidden imports (new allowed adapter-to-adapter import per D-07).
