# Phase 13: Auth + Read Endpoints — Context

**Gathered:** 2026-04-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Layer shared-secret auth on top of the Phase 11 web skeleton, then expose the dashboard (`GET /`) and JSON state (`GET /api/state`) behind that auth wall. After Phase 13 the site serves its two protected read endpoints over HTTPS (Phase 12) with a single `X-Trading-Signals-Auth` header gating all non-`/healthz` traffic.

**Phase 13 requirements (5):** AUTH-01 (shared-secret header), AUTH-02 (401 unauthorized body), AUTH-03 (audit log at WARN), WEB-05 (`GET /` dashboard with regen-on-staleness), WEB-06 (`GET /api/state` JSON).

**Explicitly out of scope (deferred to later phases):**
- Any mutation endpoint (`POST /trades/*`) — Phase 14
- Per-instrument calculator / sentinel banners — Phase 15
- Multi-user, OAuth, session cookies — hard boundary; single-secret only per PROJECT.md constraint

**Parallelizable with Phase 12?** No — Phase 13 depends on Phase 12 nginx posture (HTTPS + rate-limit live) for realistic end-to-end testing. Planner and researcher can draft in parallel with Phase 12 operational work, but execution waits for Phase 12 SETUP-HTTPS.md to complete on the droplet.

</domain>

<decisions>
## Implementation Decisions

### Area 1 — Auth enforcement mechanism

- **D-01: ASGI middleware is the sole enforcement chokepoint.** A single `AuthMiddleware` registered via `app.add_middleware(...)` in `create_app()` inspects `X-Trading-Signals-Auth` on every request and short-circuits to 401 on mismatch. No per-route `Depends(verify_auth)` boilerplate. Phase 14 `POST /trades/*` and Phase 15 additions inherit auth automatically — zero chance of forgetting to annotate a new route. Middleware lives at `web/middleware/auth.py` (the directory was established in Phase 11 D-03 for exactly this purpose).

- **D-02: `/healthz` exemption via explicit path allowlist inside the middleware.** First line of `dispatch()`:
  ```python
  EXEMPT_PATHS = frozenset({'/healthz'})
  if request.url.path in EXEMPT_PATHS:
    return await call_next(request)
  ```
  Centralized, auditable, grep-able. Future exemptions (e.g., `/metrics` in v1.2) add to the set. Do NOT use FastAPI router mount tricks or decorator markers — splits the "what's public" answer across files.

- **D-03: Constant-time secret comparison via `hmac.compare_digest`.** Never `==`. Rationale: even though nginx rate-limits at 10r/m (Phase 12 D-10) so a timing attack would take decades, `compare_digest` costs nothing, is stdlib, and removes an entire class of reviewer concern. Compare on UTF-8-encoded bytes:
  ```python
  import hmac
  presented = request.headers.get('X-Trading-Signals-Auth', '').encode('utf-8')
  expected = _WEB_AUTH_SECRET.encode('utf-8')
  if not hmac.compare_digest(presented, expected):
    # 401 path
  ```

- **D-04: AUTH-02 response on failure — 401 with plain-text body `unauthorized`.** Matches REQUIREMENTS.md AUTH-02 verbatim. No hints about header name, no WWW-Authenticate challenge (that implies browser Basic/Digest flow which is not what this is). Content-Type: `text/plain; charset=utf-8`. No body metadata, no JSON — the spec says plain text.

- **D-05: AUTH-03 audit log — WARN with IP (from `X-Forwarded-For`) + user-agent(truncated to 120 chars) + path.**
  Reconciled with ROADMAP.md Phase 13 SC-5 (post-discuss, 2026-04-25): SC-5 mandates 120-char UA truncation and `X-Forwarded-For` as the IP source. Original discuss-phase options locked 60 chars and `request.client.host` — both superseded by SC-5 authority. Client IP must come from `X-Forwarded-For` because Phase 12 put nginx in front; `request.client.host` resolves to 127.0.0.1 (nginx) behind the reverse proxy.
  ```python
  xff = request.headers.get('x-forwarded-for', '')
  # X-Forwarded-For may be a comma-separated chain "client, proxy1, proxy2" — take the first
  client_ip = xff.split(',')[0].strip() if xff else (request.client.host if request.client else '-')
  logger.warning(
    '[Web] auth failure: ip=%s ua=%r path=%s',
    client_ip,
    (request.headers.get('user-agent') or '')[:120],
    request.url.path,
  )
  ```
  Three fields are enough to pattern-match probes, distinguish bot scans from real misconfig, and line up with journald's natural single-line format. `%r` on UA so control chars are escaped. Falls back to `request.client.host` if `X-Forwarded-For` is absent (shouldn't happen through nginx, but defensive).

- **D-06: Middleware order — AuthMiddleware is declared LAST in `create_app()` so it runs FIRST.** FastAPI/Starlette middleware execution order is reverse of registration. Any future middleware (request-id injection, response compression) should be registered BEFORE auth so they wrap it. Planner: include a comment in `create_app()` noting this for future phases.

### Area 2 — GET / render strategy (WEB-05)

- **D-07: `GET /` serves `dashboard.html` from disk, regenerating only when stale.** The signal loop (main.py) already calls `dashboard.render_dashboard(state, out_path='dashboard.html')` after each run — dashboard.html is almost always current. `GET /` does:
  1. Read `dashboard.html` mtime + `state.json` mtime
  2. If `state_mtime > html_mtime`, call `render_dashboard(load_state())` to refresh the file
  3. Return `FileResponse('dashboard.html', media_type='text/html; charset=utf-8')`

  Rationale: avoids re-rendering on every hit (the default render is ~50ms + churn on dashboard.html mtime) while still satisfying WEB-05's "regenerate if state changed since last render" clause. Single operator using HTMX refreshes won't notice the file-IO overhead.

- **D-08: Staleness = `state.json` mtime > `dashboard.html` mtime.** Cheap `os.stat(...).st_mtime_ns` comparison. O(µs), zero parsing. Covers ALL write paths: the signal loop's atomic replace (Phase 3 pattern), Phase 14's `POST /trades/*` mutations, manual operator edits. Using `state['last_run']` instead would miss Phase 14 intra-day trade writes (same last_run, different positions).

- **D-09: Cached dashboard.html lives at repo root** (same path dashboard.py already writes to). No new cache directory, no systemd `ReadWritePaths` change. Phase 14 HTMX fragments, if needed, can be siblings.

- **D-10: If `render_dashboard()` raises during GET /, serve the stale on-disk copy + log WARN.**
  ```python
  try:
    if _is_stale():
      dashboard.render_dashboard(state_manager.load_state())
  except Exception as exc:
    logger.warning('[Web] dashboard regen failed, serving stale: %s: %s', type(exc).__name__, exc)
  return FileResponse('dashboard.html', ...)
  ```
  Preserves Phase 11 D-19 "/healthz never returns non-200" spirit. If `dashboard.html` itself is missing (first-run before any signal run), return 503 with plain-text `dashboard not ready`.

- **D-11: Concurrency posture for regen-during-GET.** `workers=1` (Phase 11 D-11) + FastAPI's single-threaded default means two concurrent `GET /` requests could both notice staleness and double-render. This is harmless (render is idempotent, state.json read is stable within the window) and only wastes a few ms. No file locking needed. If Phase 14 exposes a `POST /trades/*` that fires during an in-flight GET, the atomic tempfile+replace in dashboard.py prevents torn reads.

### Area 3 — GET /api/state output shape (WEB-06)

- **D-12: Response body is state.json with underscore-prefixed runtime keys stripped.** Filter at the TOP LEVEL ONLY — nested dicts keep their keys intact (in case v1.2 adds a legitimate `_comment` or similar inside a position dict). Implementation:
  ```python
  state = state_manager.load_state()
  clean = {k: v for k, v in state.items() if not k.startswith('_')}
  return JSONResponse(clean, headers={'Cache-Control': 'no-store'})
  ```
  Matches the Phase 8 D-14 convention: `_resolved_contracts`, `_stale_info`, `_LAST_LOADED_STATE`-style cached values are INTERNAL. They change across phases and leak implementation detail. External consumers (CLI, mobile, future scripts) get a stable schema.

- **D-13: Response headers — `Content-Type: application/json` (FastAPI default) + `Cache-Control: no-store`.** Explicit `no-store` prevents nginx (Phase 12 has no cache directive but future caching layer might), browser back-button, or any intermediate proxy from serving a stale snapshot. State is mutation-capable starting Phase 14; stale cache would mislead.

- **D-14: On `load_state()` failure, trust Phase 3 recovery — return whatever `load_state()` gives.** No extra try/except around the call. `load_state()` recovers corrupt state, handles missing file (returns fresh `{last_run: None, ...}`), and never raises in normal operation. Matches `/healthz` D-19 philosophy. If `load_state()` ever does raise (defensive), the middleware already returns the uncaught exception as 500 — acceptable because it indicates a real bug, not an expected failure.

- **D-15: Compact JSON (FastAPI default, no `indent=2`).** Humans using `curl | jq` for pretty-printing is a superior separation of concerns. Keeps response bytes minimal — state.json can grow to ~50KB over months of trade history.

### Area 4 — WEB_AUTH_SECRET missing-env behavior

- **D-16: `create_app()` raises `RuntimeError` if `WEB_AUTH_SECRET` is missing or empty.** Fail-closed at process start. systemd Restart=on-failure (Phase 11 D-08) will retry, but each retry will ALSO fail — `journalctl -u trading-signals-web` shows the exact cause. Operator MUST set the secret. Does NOT follow Phase 12 D-14's "log + degrade + continue" pattern because AUTH is categorically different from email: "continue without auth" = "no auth". Categorically unacceptable.
  ```python
  _WEB_AUTH_SECRET = os.environ.get('WEB_AUTH_SECRET', '').strip()
  if not _WEB_AUTH_SECRET:
    raise RuntimeError(
      'WEB_AUTH_SECRET env var is missing or empty — refusing to start. '
      'Add WEB_AUTH_SECRET=<32+ chars> to /home/trader/trading-signals/.env'
    )
  ```

- **D-17: Minimum length check — `len(WEB_AUTH_SECRET) < 32` also raises at startup.** Catches common misconfigs (accidental truncation, placeholder values). 32 chars ≈ 128 bits of entropy from `openssl rand -hex 16`. Defensible round number given nginx rate-limiting (Phase 12 D-10 — 10r/m on /healthz; Phase 13 planner should add equivalent rate-limit on auth-protected routes; track this as a follow-up if not already in WEB-03 scope).
  ```python
  if len(_WEB_AUTH_SECRET) < 32:
    raise RuntimeError(
      'WEB_AUTH_SECRET must be at least 32 characters. '
      'Generate with: openssl rand -hex 16'
    )
  ```

- **D-18: Secret is read ONCE at module load inside `create_app()` — not per-request.** Unlike `SIGNALS_EMAIL_FROM` (Phase 12 D-15 reads per-send for test isolation), the auth secret is checked against every request hot-path. Per-request `os.environ.get` is wasteful. Tests use `monkeypatch.setenv('WEB_AUTH_SECRET', ...)` BEFORE calling `create_app()` in a fixture. `AuthMiddleware.__init__` captures the secret from the factory.

- **D-19: SETUP-DROPLET.md gets a new "Configure auth secret" section in Phase 13's plan.** Appended to the existing runbook; not a new file. Three-step procedure:
  1. `openssl rand -hex 16`  (generate 32-char secret)
  2. Append `WEB_AUTH_SECRET=<output>` to `~/trading-signals/.env`, `chmod 600` already applied
  3. `sudo systemctl restart trading-signals-web` + `journalctl -u trading-signals-web -n 20` to confirm no startup error

- **D-20: Secret rotation procedure is explicitly DEFERRED to v1.2.** Single-operator + no grace-period requirement means rotation is three commands (regen, edit .env, restart) — operator figures it out when they need it. Captured in deferred ideas below.

### Claude's Discretion

- **Middleware class vs function style (`BaseHTTPMiddleware` subclass vs `@app.middleware('http')` decorator).** Planner picks. Recommend `BaseHTTPMiddleware` subclass in `web/middleware/auth.py` for testability and clean factory injection of the secret.
- **Exact media-type string for the 401 response body** (`text/plain; charset=utf-8` vs `text/plain`). Planner decides.
- **Whether `FileResponse` vs `HTMLResponse(Path(...).read_text())` for `GET /`.** Recommend `FileResponse` (handles ETag, conditional GETs, chunked transfer automatically).
- **Swagger `/docs` and Redoc `/redoc` post-auth.** Phase 11 D-Claude's-Discretion left these at FastAPI defaults. They're currently exposed and public. Phase 13 planner must decide: put them behind auth (treat as protected routes) OR disable in production (`docs_url=None, redoc_url=None` in `FastAPI()`). Recommend DISABLE — there's no legitimate reason to expose OpenAPI schema on a single-operator tool. Single operator + HTMX + no external consumers = no `/docs` needed. Locked as D-21 below.
- **Rate-limit on auth-protected routes** — Phase 12 only rate-limited `/healthz`. Phase 13 planner should add `limit_req zone=auth burst=20 nodelay` (or similar) on the `/` and `/api/state` nginx blocks. Exact zone config is planner discretion; the principle is "defense-in-depth for brute-forcing the secret".

### Additional locked decisions (follow-ups from discussion)

- **D-21: Disable Swagger `/docs` and Redoc `/redoc` in production.** `FastAPI(docs_url=None, redoc_url=None)` in `create_app()`. Single-operator tool has no external API consumers; OpenAPI schema exposure is unnecessary surface area. Phase 11 deliberately left this open pending Phase 13 auth decision — locked here.

### Folded Todos

None — `gsd-sdk query todo.match-phase 13` returned zero matches.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents (researcher, planner, executor) MUST read these before implementing.**

### Phase spec + scope
- `.planning/ROADMAP.md` §Phase 13 — phase goal, success criteria, dependency on Phase 12
- `.planning/REQUIREMENTS.md` — AUTH-01 (shared-secret header spec), AUTH-02 (401 plain-text body), AUTH-03 (WARN audit log spec), WEB-05 (`GET /` dashboard regen), WEB-06 (`GET /api/state` JSON)
- `.planning/PROJECT.md` §Current Milestone — shared-secret header auth is LOCKED (no OAuth, no sessions); HTMX or vanilla JS frontend (no React); single-operator tool

### Prior-phase decisions that constrain Phase 13
- `.planning/phases/11-web-skeleton-fastapi-uvicorn-systemd/11-CONTEXT.md`:
  - D-03 — `web/middleware/` directory established in Phase 11 specifically for this phase's auth middleware
  - D-11 — `workers=1` preserved (D-11 concurrency posture applies)
  - D-17 — `/healthz` is exempt from auth; this phase's middleware MUST honor (implemented via D-02)
  - D-18 — state reads are NOT cached; Phase 13 follows same posture for GET /api/state and GET /
  - D-19 — `/healthz` never returns non-200; Phase 13 extends the spirit to `GET /` (serve stale on render failure per D-10)
  - Claude's Discretion §Swagger — left open for Phase 13 to decide; D-21 locks disabled
- `.planning/phases/12-https-domain-wiring/12-CONTEXT.md`:
  - D-10 — nginx `/healthz` rate-limit (10r/m burst 10); Phase 13 planner should add equivalent on `/` and `/api/state`
  - D-11 — HSTS header set at nginx; Phase 13 doesn't re-set at FastAPI layer
  - D-14 — Phase 12's "log + degrade + continue" env-var pattern for SIGNALS_EMAIL_FROM; Phase 13 D-16 EXPLICITLY diverges for WEB_AUTH_SECRET (fail-closed) because auth is categorically different from email
- `.planning/phases/10-foundation-v1-0-cleanup-deploy-key/10-CONTEXT.md`:
  - D-15 — web unit is READ-ONLY on state.json; Phase 13 enforces (GET /api/state uses load_state only; no save_state calls)

### Architectural invariants (do not break)
- `CLAUDE.md` §Architecture — hex-lite: `web/` adapter imports `state_manager` (read-only per Phase 10 D-15) and `dashboard` (for `render_dashboard()` in D-07). NOT allowed: `signal_engine`, `sizing_engine`, `system_params`, `notifier`, `main`. Tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent enforces. Phase 13 adds `dashboard` to the allowlist for `web/routes/dashboard.py`.
- `CLAUDE.md` §Conventions — 2-space indent, single quotes, snake_case, `[Web]` log prefix for ALL web-process log lines (established Phase 11)
- CLAUDE.md §Conventions underscore-prefix rule — Phase 8 D-14 established `_*` keys as runtime-only; Phase 13 D-12 leverages this convention to strip them from `/api/state`

### Source files touched by Phase 13
- `web/app.py` — add middleware registration + secret validation at `create_app()`; add `docs_url=None, redoc_url=None` per D-21
- `web/middleware/__init__.py` (new) — module marker
- `web/middleware/auth.py` (new) — `AuthMiddleware(BaseHTTPMiddleware)` implementing D-01..D-06
- `web/routes/dashboard.py` (new) — `GET /` handler implementing D-07..D-11
- `web/routes/state.py` (new) — `GET /api/state` handler implementing D-12..D-15
- `web/routes/__init__.py` — register new routes alongside existing healthz
- `tests/test_web_auth_middleware.py` (new) — middleware tests (valid, missing header, wrong header, exempt path, constant-time compare)
- `tests/test_web_dashboard.py` (new) — GET / tests (auth required, fresh render, stale mtime triggers regen, render-failure fallback, missing dashboard.html → 503)
- `tests/test_web_state.py` (new) — GET /api/state tests (auth required, underscore keys stripped, Cache-Control header, compact JSON)
- `tests/test_web_app_factory.py` (new) — startup validation (missing secret raises, short secret raises, valid secret boots)
- `SETUP-DROPLET.md` — extend with "Configure auth secret" section per D-19
- `requirements.txt` — no new deps; `hmac` is stdlib, FastAPI middleware APIs already present

### Environment variables
- **NEW: `WEB_AUTH_SECRET`** (required, ≥32 chars) — read by `create_app()` at import per D-18
- Existing: `SIGNALS_EMAIL_FROM`, `SIGNALS_EMAIL_TO`, `RESEND_API_KEY` (signal loop — Phase 12)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable assets
- `web/app.py::create_app()` — Phase 11 factory. Phase 13 extends: add middleware, add env-var validation, set `docs_url=None, redoc_url=None`, register new routes.
- `web/routes/healthz.register(app)` pattern — Phase 13 `routes/dashboard.py` and `routes/state.py` follow the same `register(app: FastAPI)` function signature.
- `state_manager.load_state()` — already called from `routes/healthz.py`; Phase 13 routes use the same fresh-read pattern (no caching per Phase 11 D-18).
- `dashboard.render_dashboard(state, out_path, now)` — existing v1.0 function; Phase 13 D-07 calls it from `GET /` regen path. Signature is stable.
- `hmac.compare_digest` — stdlib; zero new deps.

### Established patterns
- **Local imports inside handlers** — matches Phase 11 D-15 convention (`from state_manager import load_state` inside the handler function, not at module top). Preserves hex boundary; simplifies `monkeypatch.setattr(state_manager, 'load_state', ...)` in tests per Phase 11 REVIEWS HIGH #2.
- **`[Web]` log prefix** — established Phase 11; Phase 13 reuses for all new log lines (auth failures, dashboard regen failures, state-read failures).
- **Test file naming `tests/test_web_<route>.py`** — Phase 11 established `test_web_healthz.py`; Phase 13 adds `test_web_auth_middleware.py`, `test_web_dashboard.py`, `test_web_state.py`, `test_web_app_factory.py`.
- **Factory pattern for testability** — `create_app()` accepts no args but reads env vars; tests `monkeypatch.setenv(...)` BEFORE calling `create_app()` in a fixture (per D-18).

### Integration points
- `AuthMiddleware.dispatch()` — single chokepoint for all request-path auth decisions; `/healthz` exemption here is the ONLY place where a URL is declared public.
- `create_app()` — secret validation happens here BEFORE `FastAPI(...)` is instantiated; a missing secret means uvicorn never binds the port. systemd's Restart=on-failure loops on this until operator fixes.
- `os.stat(path).st_mtime_ns` — mtime comparison for D-08 staleness check; works identically for `dashboard.html` and `state.json` (both use atomic tempfile+replace, preserving mtime semantics).

</code_context>

<specifics>
## Specific Ideas

- **AUTH-02 body is literally the ASCII string `unauthorized`** — lowercase, no punctuation, no JSON. Matches REQUIREMENTS.md exact wording. No WWW-Authenticate header.
- **`/healthz` remains EXACTLY as Phase 11 left it.** Phase 13 does not modify the healthz route or its tests. The middleware path-allowlist ensures healthz traffic bypasses auth without touching handler code.
- **Dashboard caching strategy deliberately mirrors signal-loop behavior.** The signal loop regenerates `dashboard.html` after each daily run; Phase 13's regen-on-staleness is a safety net for when the signal loop is down OR when Phase 14 mutations happen intra-day. In steady-state, the disk cache is always fresh and `GET /` does zero extra work.
- **`Cache-Control: no-store` on `/api/state`** is necessary because state is mutation-capable starting Phase 14. Without `no-store`, a browser back-navigate after a trade-open would show stale state.
- **No secret rotation tooling.** Rotation is: `openssl rand -hex 16` → edit `.env` → `sudo systemctl restart trading-signals-web`. Documenting a procedure in a v1.2 phase is fine; building tooling for it is not in v1.1 scope.
- **`hmac.compare_digest` accepts bytes OR str but mixing types raises.** Implementation must encode BOTH sides to bytes (or both to str) — not one of each. UTF-8 encoding is standard.
- **Middleware registration order matters.** Per D-06, AuthMiddleware must be registered LAST in create_app() so it runs FIRST (Starlette reverses registration order). Planner: add a comment pinning this.

</specifics>

<deferred>
## Deferred Ideas

- **WEB_AUTH_SECRET rotation procedure / grace-period dual-secret support.** v1.2 candidate. Single-operator + 3-command rotation means not worth the complexity now. When rotation becomes frequent (team growth, incident response tooling), revisit.
- **Session cookies / OAuth / JWT.** Out of scope per PROJECT.md v1.1 hard constraint. If the tool ever becomes multi-user, this is a full redesign, not an addition.
- **`WWW-Authenticate` challenge header on 401.** HTTP spec says include; AUTH-02 spec says "no leaked info; no hints". Going with AUTH-02 since this is a single-operator tool with no browser-prompt UX to support.
- **Rate-limit on /api/state and / at nginx layer.** Phase 12 only added rate-limit to `/healthz`. Phase 13 planner should add equivalent zones for the new routes (defense-in-depth against brute-forcing WEB_AUTH_SECRET). If planner misses it, mark as a follow-up for Phase 16 hardening.
- **Brute-force lockout / IP blacklisting after N auth failures.** Rate-limit + constant-time compare + ≥128-bit entropy makes brute-force impractical; adding lockout is complexity without real benefit for a single-operator tool. If audit log (AUTH-03) ever shows sustained attack patterns, revisit.
- **Dashboard asset versioning / ETag support.** FastAPI's `FileResponse` sets ETag automatically; that's enough. Explicit asset versioning (query-string cache-busters) is overkill.
- **GET /api/state pagination / filtering.** state.json is <50KB; pagination is unneeded. If state.trade_log grows past 10MB in v1.2+, add a `?since=<date>` filter.
- **Request-ID middleware / structured logging.** Audit log (AUTH-03) + journald single-line format is enough for v1.1. Request IDs + JSON logs are a v1.2 observability addition.
- **Swagger/Redoc behind auth (vs disabled per D-21).** Decided: disable outright. If API consumers appear (post-v1.1), re-enable behind auth.
- **Concurrent `GET /` regen double-work.** Covered in D-11 — harmless under `workers=1`, revisit only if workers>1 is explored in v1.2.

### Reviewed Todos (not folded)
None — `gsd-sdk query todo.match-phase 13` returned zero matches.

</deferred>

---

*Phase: 13-auth-read-endpoints*
*Context gathered: 2026-04-25*
