# Phase 13: Auth + Read Endpoints — Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-25
**Phase:** 13-auth-read-endpoints
**Areas discussed:** Auth enforcement mechanism, GET / render strategy, GET /api/state output shape, WEB_AUTH_SECRET missing-env behavior

---

## Auth enforcement mechanism

### Q1 — How should auth be enforced across protected endpoints?

| Option | Description | Selected |
|--------|-------------|----------|
| Middleware (Recommended) | Single ASGI middleware checks X-Trading-Signals-Auth on every request. Cleanest chokepoint, zero per-route boilerplate, Phase 14 POST routes get auth for free. | ✓ |
| Route dependency | Depends(verify_auth) on each protected route. Miss one and it silently opens. | |
| Hybrid | Middleware records identity, route deps enforce. Overkill for single-secret auth. | |

**User's choice:** Middleware
**Notes:** Aligned with recommendation.

### Q2 — How should /healthz be exempted from auth?

| Option | Description | Selected |
|--------|-------------|----------|
| Path allowlist in middleware (Recommended) | Check request.url.path against a frozenset. Centralized, auditable. | ✓ |
| Router-level mount | Mount healthz on a separate APIRouter that middleware ignores. Splits public vs protected across files. | |
| Decorator marker | @public decorator + middleware inspects route metadata. Overkill. | |

**User's choice:** Path allowlist in middleware

### Q3 — How should the secret comparison be implemented?

| Option | Description | Selected |
|--------|-------------|----------|
| hmac.compare_digest (Recommended) | Constant-time. Stdlib. Removes timing-attack class. | ✓ |
| Plain == comparison | Shorter but timing-leaky. Fine given nginx rate-limit but cheap to upgrade. | |

**User's choice:** hmac.compare_digest

### Q4 — What should AUTH-03 log on auth failures?

| Option | Description | Selected |
|--------|-------------|----------|
| IP + UA(60ch) + path (Recommended) | Three fields, enough forensic value, single log line. | ✓ |
| IP + UA(60ch) only | Simpler, gives up path forensics. | |
| IP only | Minimal. | |

**User's choice:** IP + UA(60ch) + path

---

## GET / render strategy (WEB-05)

### Q1 — How should GET / serve the dashboard?

| Option | Description | Selected |
|--------|-------------|----------|
| Serve on-disk dashboard.html, regen on staleness (Recommended) | Read mtime, regen if state is newer, FileResponse the file. Mostly zero-work in steady state. | ✓ |
| Always re-render on request | Call render_dashboard() every hit. Simpler but wasteful. | |
| Serve on-disk verbatim, no regen check | Trust signal loop. Cheapest but breaks WEB-05. | |

**User's choice:** Serve on-disk dashboard.html, regen on staleness

### Q2 — What does "state changed since last render" mean (WEB-05)?

| Option | Description | Selected |
|--------|-------------|----------|
| state.json mtime > dashboard.html mtime (Recommended) | Filesystem mtime. O(µs), catches all writes including Phase 14 mutations. | ✓ |
| state.last_run differs from rendered last_run | Parse JSON, compare last_run. Misses intra-day Phase 14 writes. | |
| Hash of state.json differs from last render hash | SHA compare. Overkill. | |

**User's choice:** state.json mtime > dashboard.html mtime

### Q3 — Where does the cached dashboard.html live?

| Option | Description | Selected |
|--------|-------------|----------|
| Repo root (Recommended) | Same path dashboard.py already writes to. Zero new config. | ✓ |
| Dedicated cache dir | Separate generated/source. Not worth it for one file. | |

**User's choice:** Repo root

### Q4 — If render_dashboard() fails during GET /?

| Option | Description | Selected |
|--------|-------------|----------|
| Serve stale disk copy + WARN log (Recommended) | Matches Phase 11 D-19 "never non-200" spirit. | ✓ |
| Return 500 with error page | Fail loud. Honest but breaks pattern. | |
| Return empty placeholder + WARN | Middle ground but creates third render path. | |

**User's choice:** Serve stale disk copy + WARN log

---

## GET /api/state output shape (WEB-06)

### Q1 — What should GET /api/state return?

| Option | Description | Selected |
|--------|-------------|----------|
| Filtered state (strip _-prefixed keys) (Recommended) | Honor Phase 8 D-14 underscore-prefix convention. Stable external schema. | ✓ |
| Raw state.json passthrough | Simplest. Leaks internal keys. | |
| Wrap with metadata envelope | {state, fetched_at, stale}. Adds schema frontend must parse. | |

**User's choice:** Filtered state (strip _-prefixed keys)

### Q2 — Content-Type and response headers?

| Option | Description | Selected |
|--------|-------------|----------|
| application/json + Cache-Control: no-store (Recommended) | Explicit no-store prevents stale caching after Phase 14 mutations. | ✓ |
| application/json only, default caching | Let nginx/browser decide. Risks stale state. | |

**User's choice:** application/json + Cache-Control: no-store

### Q3 — How to handle state.json read failure?

| Option | Description | Selected |
|--------|-------------|----------|
| Defer to load_state()'s recovery + return result (Recommended) | Trust Phase 3 corrupt-recovery. Matches /healthz D-19. | ✓ |
| Return 503 on load failure | More honest but load_state rarely raises. | |

**User's choice:** Defer to load_state()'s recovery + return result

### Q4 — Pretty-print JSON or compact?

| Option | Description | Selected |
|--------|-------------|----------|
| Compact (Recommended) | FastAPI default. Curl users use jq for pretty. Minimal wire bytes. | ✓ |
| Indented (pretty) | Human-readable over curl. Bloats bytes. | |

**User's choice:** Compact

---

## WEB_AUTH_SECRET missing-env behavior

### Q1 — What happens if WEB_AUTH_SECRET is missing/empty at process start?

| Option | Description | Selected |
|--------|-------------|----------|
| Refuse to start (Recommended) | create_app() raises RuntimeError. systemd retries, journalctl shows cause. | ✓ |
| Start in "locked" mode, 503 everything | Softer failure but masks misconfig. | |
| Start, WARN at startup, treat all requests as unauth | Matches Phase 12 pattern but "degrade access control" ≠ "degrade email". | |

**User's choice:** Refuse to start

### Q2 — Minimum secret length validation at startup?

| Option | Description | Selected |
|--------|-------------|----------|
| ≥ 32 chars, else refuse to start (Recommended) | ~128 bits entropy. Defensible round number. | ✓ |
| ≥ 16 chars | 64 bits. Fine but arbitrary threshold. | |
| No length check | Trust operator. Single-char secrets would pass silently. | |

**User's choice:** ≥ 32 chars, else refuse to start

### Q3 — Does SETUP-DROPLET.md get extended, or new SETUP-AUTH.md?

| Option | Description | Selected |
|--------|-------------|----------|
| Extend SETUP-DROPLET.md (Recommended) | One-time droplet setup doc; auth is part of that. 3-line procedure. | ✓ |
| New SETUP-AUTH.md in phase dir | Matches Phase 12 precedent but doesn't warrant its own doc. | |

**User's choice:** Extend SETUP-DROPLET.md

### Q4 — Secret rotation procedure documented where?

| Option | Description | Selected |
|--------|-------------|----------|
| In SETUP-DROPLET.md as a subsection | Capture the 3-line procedure now. | |
| Defer to v1.2 — note in deferred ideas | Operator figures it out ad-hoc when needed. | ✓ |

**User's choice:** Defer to v1.2 — note in deferred ideas

---

## Claude's Discretion

Captured in CONTEXT.md `<decisions>` §Claude's Discretion:

- Middleware class vs function style (`BaseHTTPMiddleware` subclass recommended)
- Exact media-type string for 401 body
- `FileResponse` vs `HTMLResponse` for GET /
- Rate-limit zone config for auth-protected routes (planner picks exact rate)

## Deferred Ideas

Captured in CONTEXT.md `<deferred>` section:

- WEB_AUTH_SECRET rotation tooling → v1.2
- Session cookies / OAuth / JWT → out of scope per PROJECT.md
- WWW-Authenticate challenge header → intentionally omitted per AUTH-02 spec
- Rate-limit on /api/state and / at nginx → planner to add, else Phase 16 hardening
- Brute-force lockout → not worth complexity for single-operator tool
- Dashboard asset versioning / ETag → FileResponse handles automatically
- GET /api/state pagination → state.json too small to warrant
- Request-ID middleware / structured logging → v1.2 observability
- Swagger/Redoc behind auth → D-21 locks: disabled outright
- Concurrent GET / regen double-work → harmless under workers=1
