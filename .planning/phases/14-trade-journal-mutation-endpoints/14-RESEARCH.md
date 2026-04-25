# Phase 14: Trade Journal — Mutation Endpoints — Research

**Researched:** 2026-04-25
**Domain:** FastAPI mutation endpoints + Pydantic v2 PATCH semantics + cross-process state.json coordination + HTMX 1.9.12 partials + schema migration v2→v3
**Confidence:** HIGH (stack + patterns), MEDIUM (HTMX 2-stage destructive UX is composed from primitives — no canonical "best practice" surfaced in search)

## Summary

Phase 14 introduces three POST endpoints (`/trades/open`, `/trades/close`, `/trades/modify`) plus two HTMX-glue GET endpoints (`/trades/close-form`, `/trades/modify-form`) that record operator-executed trades through HTMX-driven forms in the existing dashboard. Six cross-cutting changes coordinate cleanly: (1) `Position` TypedDict gains `manual_stop: float | None`; (2) schema migration v2→v3 backfills `manual_stop=None` on all existing positions; (3) `state_manager.save_state` acquires an `fcntl.LOCK_EX` advisory lock so the daily signal loop and FastAPI process never write concurrently; (4) `sizing_engine.get_trailing_stop` honors `manual_stop` when set; (5) `web/routes/trades.py` (new) implements POSTs with Pydantic v2 models and a 422→400 remap; (6) `dashboard.py::render_dashboard` adds three HTMX surfaces per UI-SPEC.

The stack is fully present in `requirements.txt` (FastAPI 0.136.1, uvicorn 0.46.0, httpx 0.28.1) — Pydantic v2 arrives as a transitive dependency of FastAPI 0.136.1 (which requires `pydantic>=2.9.0`). `fcntl` and `hmac` are stdlib. HTMX 1.9.12 (the last 1.9.x release, published 2024-04-25) ships via SRI-pinned `<script>` tag mirroring the v1.0 Chart.js precedent. The single notable correction to the orchestrator brief: `STATE_SCHEMA_VERSION` is currently **2**, so the new migration is **v2→v3** (not v3→v4 as the brief assumed).

**Primary recommendation:** Adopt the established Phase 13 patterns verbatim — `register(app)` per route module, local hex-boundary imports inside handlers, `[Web]` log prefix, `monkeypatch.setenv('WEB_AUTH_SECRET', ...)` autouse fixture in `tests/conftest.py`. Use Pydantic v2 `model_fields_set` for "absent vs null" PATCH semantics in `/trades/modify`. Wrap `state_manager._atomic_write` (not `save_state`'s caller) with `fcntl.flock(fd, fcntl.LOCK_EX)` on the parent-directory or persisted-file descriptor, and rely on close-on-exit semantics of `with open(...) as f` for release.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Pydantic request validation (open/close/modify) | API / Backend (`web/routes/trades.py`) | — | Schema validation belongs in the adapter; engine modules are pure-math |
| 422→400 remap exception handler | API / Backend (`web/app.py::create_app`) | — | One handler at the FastAPI app-level applies to all `/trades/*` POSTs |
| Pyramid gate evaluation (`check_pyramid`) | API / Backend handler delegates to pure-math (`sizing_engine`) | Pure-math hex (`sizing_engine`) | Web tier reads `state['signals'][instrument]['atr']`, calls `sizing_engine.check_pyramid` (pure-math owns the rule) |
| `gross_pnl` computation in close handler | API / Backend (`web/routes/trades.py`) | — | Inlined per D-05 to avoid the `compute_unrealised_pnl` realised-vs-gross trap |
| Atomic state.json write | I/O hex (`state_manager.save_state`) | — | Existing single-chokepoint preserved; `fcntl.flock` added INSIDE this function |
| Cross-process write coordination | OS / kernel (`fcntl.flock` advisory lock) | — | Both web (FastAPI) and signal-loop (main.py systemd unit) compete for the same OS-level lock |
| `manual_stop` precedence | Pure-math hex (`sizing_engine.get_trailing_stop`) | Render hex (`dashboard._compute_trail_stop_display` mirrors) | Per CLAUDE.md hex-lite, both paths must be updated in lockstep with bit-identical math (existing parity test locks this) |
| Schema migration v2→v3 | I/O hex (`state_manager._migrate_v2_to_v3`) | — | Existing `MIGRATIONS` dict walks forward; new function added |
| HTMX form rendering | Render hex (`dashboard.py::render_dashboard`) | — | Phase 14 modifies `_render_positions_table` and adds `_render_open_form`, `_render_confirmation_banner` per UI-SPEC |
| HTMX partial response shape | API / Backend (`web/routes/trades.py`) | Render hex (small partial helpers in `dashboard.py`) | Web returns an HTMX-style fragment; reuses `dashboard._render_positions_table` row math via narrow helper extraction |
| HTMX 1.9.12 vendoring | Render hex (inline `<script>` in HTML shell) | — | Mirrors Chart.js precedent; SRI-pinned, no build step |
| 2-stage destructive close confirmation | API / Backend (GET `/trades/close-form` returns confirm panel; POST `/trades/close` commits) | Render hex (confirmation panel HTML) | Two endpoints — one returns the panel, one mutates — keeps each handler single-purpose |

## User Constraints (from CONTEXT.md)

### Locked Decisions

**Area 1 — POST /trades/open:**

- **D-01 Position-already-exists handling.** Same direction → pyramid-up via `sizing_engine.check_pyramid` (D-02). Opposite direction → 409 Conflict with body `'instrument {X} already has an open {DIRECTION} position; close it first via POST /trades/close before opening a {NEW_DIRECTION}'`. Replace/overwrite is NEVER allowed.
- **D-02 Pyramid gate uses `sizing_engine.check_pyramid`.** ATR comes from `state['signals'][instrument]['atr']` (last computed value). If `should_add: true` → increment n_contracts and pyramid_level (capped at MAX_PYRAMID_LEVEL=2). If `should_add: false` → 409 Conflict with reason from check_pyramid output.
- **D-03 Client may override peak_price / trough_price / pyramid_level with strict coherence checks.** LONG: `peak_price >= entry_price`; `trough_price` MUST be absent or null. SHORT: `trough_price <= entry_price`; `peak_price` MUST be absent or null. `pyramid_level` MUST be int in `[0, MAX_PYRAMID_LEVEL=2]`.
- **D-04 Pydantic v2 model with field-level constraints; 422→400 remap; executed_at? optional.** `executed_at` defaults to `datetime.now(zoneinfo.ZoneInfo('Australia/Perth')).date()` when absent.

**Area 2 — POST /trades/close:**

- **D-05 `gross_pnl` computed INLINE — raw price-delta formula.** `record_trade` D-14 deducts the closing-half cost; passing `realised_pnl` (which already has half deducted by `sizing_engine.compute_unrealised_pnl`) would double-count. Inline math only — no call to `sizing_engine.compute_unrealised_pnl`.
- **D-06 `exit_reason = 'operator_close'`.** Distinct literal value, hardcoded in close handler.
- **D-07 `multiplier` and `cost_aud` from `state['_resolved_contracts'][instrument]`.** Honors operator's tier choice without re-deriving.
- **D-08 `executed_at?` optional → default today AWST date.** Allows back-dating an exit.

**Area 3 — POST /trades/modify:**

- **D-09 New `manual_stop: float | None` field added to `Position` TypedDict.** Schema migration required (v2→v3 in `state_manager._migrate_*`). When `manual_stop` is set, `sizing_engine.get_trailing_stop` returns it instead of computing from peak/trough.
- **D-10 `new_contracts` mutable up/down; `pyramid_level` resets to 0 on any modify.** Validation: `new_contracts >= 1` (else 400). No upper bound.
- **D-11 Atomic single save_state.** Apply both new_stop and new_contracts updates in-memory, validate, then `save_state(state)` exactly once.
- **D-12 At-least-one-field required.** Pydantic validator: at least one of `new_stop` / `new_contracts` MUST be present (or non-null). Empty modify body returns 400.

**Area 4 — Write coordination:**

- **D-13 `state_manager.save_state` acquires fcntl exclusive lock on state.json before atomic write.** POSIX (Linux/macOS). Lock timeout: NONE — block indefinitely. Daily save ~50ms; web POST ~10–100ms. Worst case overlap is sub-second.
- **D-14 Phase 10 D-15 ("web is read-only on state.json") is explicitly amended by Phase 14 D-13.** Web becomes a second writer; cross-writer coordination via fcntl. Sole-writer invariant for `state['warnings']` (TRADE-06) remains intact — only `state_manager.append_warning` writes there, and no Phase 14 endpoint calls it.

### Claude's Discretion

- **HTMX partial response shape.** Recommend per-row `outerHTML` swap for close/modify; full-`tbody` `innerHTML` swap for open (UI-SPEC §Decision 3 already locked this).
- **CSRF posture.** `X-Trading-Signals-Auth` header doubles as CSRF token equivalent — third-party origins can't supply it; same-origin browser POSTs include it via HTMX `hx-headers`. No additional CSRF machinery needed for v1.1 single-operator.
- **Pydantic v1 vs v2 import path.** FastAPI 0.136.1 requires `pydantic>=2.9.0` [VERIFIED: pypi.org/pypi/fastapi/0.136.1/json] — Pydantic v2 idioms are the only option.
- **NotProvided sentinel for distinguishing "absent" vs "null"** in modify request. Recommend `model_fields_set` introspection (see Pattern 5 below).
- **HTMX form HTML structure** — UI-SPEC §Decision 1, 2, 7 already locked the layout.
- **Partial-close support.** Out of scope for Phase 14 — operator wanting partial close uses full-close + new-open.

### Deferred Ideas (OUT OF SCOPE)

- **Partial-close support.** v1.2 candidate.
- **Live calculator banners and drift sentinels.** CALC-01..04 + SENTINEL-01..03 → Phase 15.
- **Rate-limit on /trades/* at nginx layer.** Phase 16 hardening if planner doesn't include here.
- **Audit log of mutations.** Out of scope for v1.1.
- **Multi-position per instrument.** v2.0 schema change.
- **Operator-supplied exit_reason.** v1.2 enrichment.
- **WebSocket broadcast of state changes.** v1.2+.
- **HTMX form HTML structure decisions.** Locked in UI-SPEC.
- **NotProvided sentinel selection.** Recommended pattern below.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TRADE-01 | `POST /trades/open` accepts `{instrument, direction, entry_price, contracts, executed_at?}` and appends an open position to `state.positions` | Pattern 1 (POST handler scaffold), Pattern 4 (Pydantic v2 schema) |
| TRADE-02 | Request validation (instrument enum, direction enum, entry_price > 0 finite, contracts ≥ 1); returns 400 with field-level errors | Pattern 4 (Pydantic v2 + Field constraints), Pattern 6 (422→400 remap exception handler) |
| TRADE-03 | `POST /trades/close` accepts `{instrument, exit_price, executed_at?}` → `state_manager.record_trade()` | Pattern 2 (close handler with inline gross_pnl per D-05), §Don't Hand-Roll (record_trade is the existing primitive) |
| TRADE-04 | `POST /trades/modify` accepts `{instrument, new_stop?, new_contracts?}` for trail-stop and size mutation | Pattern 3 (modify handler), Pattern 5 (Pydantic v2 PATCH semantics via `model_fields_set`) |
| TRADE-05 | Dashboard `GET /` includes HTMX-powered forms for open/close/modify | Pattern 7 (HTMX 1.9.12 vendoring), Pattern 8 (HTMX response shapes), UI-SPEC §Decision 1–7 |
| TRADE-06 | Every mutation endpoint goes through `state_manager.save_state()`; endpoints never touch `state['warnings']` directly | Pattern 9 (fcntl lock around `_atomic_write`), Pattern 10 (AST guard against `state['warnings']` mutation in web/) |

## Project Constraints (from CLAUDE.md)

| # | Directive | How Phase 14 honors |
|---|-----------|---------------------|
| C-1 | 2-space indent | All new files (`web/routes/trades.py`, modified `state_manager.py`, etc.) |
| C-2 | Single quotes | Per `tests/test_signal_engine.py::TestDeterminism::test_no_four_space_indent` parity |
| C-3 | snake_case functions, UPPER_SNAKE constants | `open_trade`, `close_trade`, `modify_trade`; `EXEMPT_PATHS`, `MAX_PYRAMID_LEVEL` |
| C-4 | Instrument keys `SPI200`, `AUDUSD`; Signal `LONG=1, SHORT=-1, FLAT=0`; ISO `YYYY-MM-DD` dates; AWST in user-facing output | Pydantic `Literal['SPI200', 'AUDUSD']`, `Literal['LONG', 'SHORT']`; `executed_at` defaults to AWST today |
| C-5 | `[Web]` log prefix | All Phase 14 web log lines |
| C-6 | Hex-lite — `web/` may NOT import `signal_engine`, `notifier`, `main`; Phase 14 ADDS `sizing_engine` to allowed adapter imports | New AST guard test `test_sizing_engine_is_allowed_for_web_phase_14_D02` (mirrors Phase 13 D-07's `dashboard` promotion); confirm `sizing_engine` is NOT in `FORBIDDEN_FOR_WEB` set |
| C-7 | `state.json` writes are atomic | Existing `_atomic_write` preserved; fcntl wrapping doesn't break atomicity |
| C-8 | Email sends NEVER crash workflow | Not applicable (Phase 14 doesn't email) |
| C-9 | `signal_engine ↔ state_manager` must not import each other | Preserved (Phase 14 doesn't touch this boundary) |
| C-10 | `sizing_engine` and `system_params` are pure-math/constants modules | Phase 14 only ADDS a field to `system_params.Position` (no I/O); only reads `manual_stop` in `sizing_engine.get_trailing_stop` (pure dict-lookup) |
| C-11 | No `max(1, ...)` floor on contract sizing | TRADE-02 validation enforces `contracts >= 1` (caller-supplied); no floor logic |
| C-12 | LONG→FLAT closes the LONG; SHORT→FLAT closes the SHORT | Not applicable (Phase 14 endpoints take explicit direction; FLAT semantics only apply to signal evaluation) |
| C-13 | Sole-writer invariant for `state['warnings']` — only `state_manager.append_warning` writes there | TRADE-06 — AST guard test in `tests/test_web_trades.py` walks `web/routes/trades.py` and asserts no expression matches `state['warnings'] =` or `state['warnings'].append` |
| C-14 | GSD workflow enforcement | This RESEARCH.md is part of `/gsd-plan-phase 14` |
| C-15 | Codemoot review at milestone close | Phase 16 closes v1.1; Phase 14 leaves no debt |

## Standard Stack

### Core (already pinned in `requirements.txt`)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `fastapi` | 0.136.1 (pinned) | Routing, dependency injection, exception handlers, JSONResponse | Existing project standard; Phase 13 already uses [VERIFIED: requirements.txt:10] |
| `pydantic` | >=2.9.0 (transitive via fastapi==0.136.1) | Request body schema, field-level constraints, model_validator, `model_fields_set` for PATCH semantics | FastAPI 0.136 declares `pydantic>=2.9.0` as runtime dep [VERIFIED: pypi.org/pypi/fastapi/0.136.1/json] |
| `starlette` | >=0.46.0 (transitive) | `BaseHTTPMiddleware`, `Request`, `Response` types | Phase 13 `AuthMiddleware` already uses [VERIFIED: web/middleware/auth.py:34-37] |
| `uvicorn[standard]` | 0.46.0 | ASGI server | Phase 11 systemd unit pins; `workers=1` per Phase 11 D-11 [VERIFIED: requirements.txt:11] |
| `httpx` | 0.28.1 | TestClient transport for `tests/test_web_*.py` | Phase 13 already uses [VERIFIED: requirements.txt:12] |

### Supporting (stdlib — no new pins)

| Module | Purpose | When to Use |
|--------|---------|-------------|
| `fcntl` | Advisory file lock for cross-process state.json coordination | D-13: wrap `_atomic_write` with `fcntl.LOCK_EX` |
| `hmac` | Already used by Phase 13 `AuthMiddleware`; not re-used in Phase 14 (handlers run AFTER auth) | n/a |
| `zoneinfo` | AWST default for `executed_at` | `datetime.now(zoneinfo.ZoneInfo('Australia/Perth')).date()` |
| `math` | `math.isfinite` for entry_price/exit_price/new_stop NaN+inf rejection | All numeric Pydantic field validators |
| `ast` | Hex-boundary AST guard regression tests | New tests/extensions in `tests/test_web_trades.py` and `tests/test_web_healthz.py::TestWebHexBoundary` |

### HTMX vendoring (CDN, no pip pin)

| Property | Value | Source |
|----------|-------|--------|
| Library | HTMX | [VERIFIED: registry.npmjs.org/htmx.org] |
| Version | **1.9.12** (last 1.9.x release; published 2024-04-25) | UI-SPEC §HTMX vendor pin (locked); npm registry confirms 1.9.12 is final 1.9.x [VERIFIED: registry.npmjs.org] |
| URL (unpkg) | `https://unpkg.com/htmx.org@1.9.12/dist/htmx.min.js` (48,101 bytes) | [VERIFIED: curl, openssl dgst -sha384] |
| URL (jsDelivr alt) | `https://cdn.jsdelivr.net/npm/htmx.org@1.9.12/dist/htmx.min.js` (byte-identical) | [VERIFIED: diff -q against unpkg] |
| SRI hash | **`sha384-ujb1lZYygJmzgSwoxRggbCHcjc0rB2XoQrxeTUQyRjrOnlCoYta87iKBWq3EsdM2`** | [VERIFIED: openssl dgst -sha384 -binary | base64 produced this exact value against both unpkg and jsdelivr] |
| crossorigin | `anonymous` | UI-SPEC pattern; matches Chart.js precedent at `dashboard.py:115-116` |

**Recommended `<script>` block for `dashboard.py`:**
```python
# Append next to existing _CHARTJS_URL / _CHARTJS_SRI block (dashboard.py:115-116)
_HTMX_URL = 'https://cdn.jsdelivr.net/npm/htmx.org@1.9.12/dist/htmx.min.js'
_HTMX_SRI = 'sha384-ujb1lZYygJmzgSwoxRggbCHcjc0rB2XoQrxeTUQyRjrOnlCoYta87iKBWq3EsdM2'
```

**Why 1.9.12, not 2.x:** UI-SPEC §HTMX vendor pin explicitly locks 1.9.12. HTMX 2.0.x exists (2.0.10 latest as of 2026-04-25 per [VERIFIED: github.com/bigskysoftware/htmx releases]) but introduces breaking changes around `hx-on::*` event listeners that UI-SPEC §Decision 4's inline `hx-on::after-request` handler depends on. 1.9.12 is byte-stable, security-patched, and fully sufficient for Phase 14's surface area.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `fcntl.flock` (advisory) | `fcntl.lockf` / `fcntl.fcntl(fd, F_SETLKW, ...)` (POSIX byte-range advisory) | `fcntl()` byte-range locks belong to (pid, inode) and release when ANY fd closes — insidious gotcha for context managers [CITED: chris.improbable.org/everything-you-never-wanted-to-know-about-file-locking]. `flock()` belongs to (open file description) — release semantics are simpler. `flock()` non-portable to Solaris/HP-UX but project targets Linux droplet + macOS dev only. ✅ Use `flock()`. |
| `fcntl.flock` blocking | Non-blocking with timeout (`LOCK_EX | LOCK_NB` + retry loop) | D-13 explicitly chose blocking-indefinite; daily save ~50ms, web POST ~10–100ms, sub-second worst case. ✅ Honor D-13. |
| Pydantic v2 `Optional[X]` annotation | `X | None` (PEP 604) | Identical semantics in Pydantic v2; project convention is PEP 604 syntax (`float | None`). ✅ Use `X | None`. |
| `model_fields_set` for absent-vs-null | `__pydantic_fields_set__` (private) | `model_fields_set` is the public Pydantic v2 API [CITED: docs.pydantic.dev — Pydantic v2 migration guide]. Private name `__pydantic_fields_set__` is identical attribute but private — don't use it. ✅ `model_fields_set`. |
| `model_fields_set` for absent-vs-null | Sentinel value (`_NOT_PROVIDED = object()` as Field default) | More boilerplate; slightly less ergonomic in tests. Pydantic 2.12 ships an experimental `MISSING` sentinel based on draft PEP 661 [CITED: pydantic.dev/articles/pydantic-v2-12-release] but it's experimental and not in the currently-resolved `pydantic>=2.9.0` floor. ✅ `model_fields_set`. |
| `HTMLResponse` | `Response(content=..., media_type='text/html')` | `HTMLResponse` is the FastAPI-recommended idiom; auto-generates OpenAPI media type [CITED: fastapi.tiangolo.com/advanced/custom-response/]. ✅ Use `HTMLResponse` for HTMX partials, `JSONResponse` for 400 error bodies. |
| Inline gross_pnl per D-05 | Call `sizing_engine.compute_unrealised_pnl` | D-05 explicitly forbids — see anti-pitfall comment requirement. `compute_unrealised_pnl` deducts opening-half cost; `record_trade` deducts closing-half. Passing the former as `gross_pnl` double-deducts the closing cost. ✅ Honor D-05. |

**Installation:** No new pip dependencies. `requirements.txt` is unchanged. The HTMX library loads from CDN (SRI-pinned), mirroring the v1.0 Chart.js pattern.

**Version verification:**
```bash
# FastAPI dependency declaration confirms Pydantic v2 floor
curl -sL https://pypi.org/pypi/fastapi/0.136.1/json | python3 -c "..."
# Output: starlette>=0.46.0; pydantic>=2.9.0
# (verified 2026-04-25 via this research session)
```

## Architecture Patterns

### System Architecture Diagram

```
                       ┌─────────────────┐
HTTP POST/GET ───────► │   nginx :443    │
(operator browser)     │ (Phase 12 TLS)  │
                       └────────┬────────┘
                                │ proxy_pass http://127.0.0.1:8000
                                ▼
                  ┌─────────────────────────────┐
                  │  uvicorn web.app:app (PID A)│
                  │  workers=1 (Phase 11 D-11)  │
                  └──────────────┬──────────────┘
                                 │
                                 ▼
                  ┌──────────────────────────────────┐
                  │  AuthMiddleware (Phase 13 D-01)  │
                  │  X-Trading-Signals-Auth gate     │
                  │  /healthz EXEMPT, all else 401   │
                  └──────────────┬───────────────────┘
                                 │ pass-through if auth OK
                                 ▼
                  ┌────────────────────────────────────────────────┐
                  │  Custom RequestValidationError handler         │
                  │  (Phase 14 NEW — 422→400 remap, Pattern 6)     │
                  │  emits {errors: [{field, reason}]} JSON        │
                  └──────────────┬─────────────────────────────────┘
                                 │
              ┌──────────────────┼──────────────────────────────┐
              ▼                  ▼                              ▼
   ┌──────────────────┐ ┌──────────────────┐  ┌──────────────────────────┐
   │ web.routes.      │ │ web.routes.      │  │ web.routes.trades        │
   │   healthz        │ │   dashboard      │  │ (Phase 14 NEW)           │
   │   (Phase 11)     │ │   (Phase 13 GET) │  │ POST /trades/open        │
   │ GET /healthz     │ │ GET /            │  │ POST /trades/close       │
   └──────────────────┘ └──────────────────┘  │ POST /trades/modify      │
                                              │ GET /trades/close-form   │
                                              │ GET /trades/modify-form  │
                                              │ GET /trades/cancel-row   │
                                              └──────────────┬───────────┘
                                                             │
                              local imports (Phase 11 C-2 hex-boundary):
                              from state_manager import load_state, save_state, record_trade
                              from sizing_engine import check_pyramid
                              from system_params import MAX_PYRAMID_LEVEL
                                                             │
                                                             ▼
                                              ┌─────────────────────────────┐
                                              │ state_manager.save_state    │
                                              │ (MODIFIED Phase 14 D-13)    │
                                              │  + fcntl.LOCK_EX wrapper    │
                                              └──────────────┬──────────────┘
                                                             │ fcntl.flock (POSIX advisory)
                                                             ▼
                                              ┌─────────────────────────────┐
                                              │  state.json (repo root)     │
                                              └──────────────▲──────────────┘
                                                             │ same flock
                                              ┌──────────────┴──────────────┐
                                              │  main.py daily run (PID B)  │
                                              │  systemd: trading-signals   │
                                              │  (Phase 11 systemd unit)    │
                                              │  also calls save_state      │
                                              └─────────────────────────────┘

HTMX response paths:
  - 2xx open success    → outerHTML swap of #positions-tbody (server returns full <tbody>)
  - 2xx close success   → outerHTML swap of #position-row-{instrument} (empty + HX-Trigger:positions-changed)
  - 2xx modify success  → outerHTML swap of #position-row-{instrument} (re-rendered <tr>)
  - 2xx open/close/modify also OOB-swap success banner into #confirmation-banner (UI-SPEC §Decision 3)
  - 4xx (any)           → JSON {errors: [{field, reason}]} (HTMX won't swap; hx-on::after-request handler populates .error region)
```

### Recommended Project Structure

```
web/
├── __init__.py                 # existing
├── app.py                      # MODIFIED: register trades route + RequestValidationError handler
├── middleware/
│   ├── __init__.py
│   └── auth.py                 # unchanged (Phase 13)
└── routes/
    ├── __init__.py
    ├── healthz.py              # unchanged (Phase 11)
    ├── dashboard.py            # unchanged (Phase 13 GET /)
    ├── state.py                # unchanged (Phase 13 GET /api/state)
    └── trades.py               # NEW (Phase 14)

dashboard.py                    # MODIFIED: add HTMX 1.9.12 SRI block, _render_open_form,
                                #   _render_confirmation_banner, _render_positions_table changes
                                #   (new Actions column, id="positions-tbody", id="position-row-{instrument}")
state_manager.py                # MODIFIED: _atomic_write wrapped with fcntl.LOCK_EX (D-13);
                                #   _migrate_v2_to_v3 added to MIGRATIONS dict (D-09)
system_params.py                # MODIFIED: STATE_SCHEMA_VERSION 2 → 3;
                                #   Position TypedDict gains manual_stop: float | None
sizing_engine.py                # MODIFIED: get_trailing_stop honors manual_stop override (D-09)

tests/
├── test_web_trades.py          # NEW (Phase 14): 6 test classes (open/close/modify happy +
│                               #   validation + conflict + pyramid + lock contention + AST guard)
├── test_state_manager.py       # EXTENDED: TestFcntlLock, Test_v2_to_v3_Migration regression
├── test_sizing_engine.py       # EXTENDED: TestManualStopOverride
├── test_signal_engine.py       # POTENTIALLY EXTENDED: FORBIDDEN_FOR_WEB consistency
└── test_web_healthz.py         # EXTENDED: TestWebHexBoundary regression for sizing_engine
```

### Pattern 1: POST /trades/open handler scaffold

**What:** FastAPI endpoint with Pydantic v2 body, hex-boundary local imports, AWST default, conflict 409 path, pyramid-up via `sizing_engine.check_pyramid`.

**When to use:** Any operator-initiated state.json mutation that creates a new position (or pyramids an existing one).

**Example:**
```python
# Source: composed from FastAPI 0.136 docs + Phase 13 router pattern
# Local imports inside handler preserve hex boundary (Phase 11 C-2 + Phase 14 D-09)
from datetime import date as _date
from typing import Literal

import logging
import zoneinfo

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger(__name__)

_AWST = zoneinfo.ZoneInfo('Australia/Perth')


class OpenTradeRequest(BaseModel):
  instrument: Literal['SPI200', 'AUDUSD']
  direction: Literal['LONG', 'SHORT']
  entry_price: float = Field(gt=0)
  contracts: int = Field(ge=1)
  executed_at: _date | None = None
  peak_price: float | None = None
  trough_price: float | None = None
  pyramid_level: int | None = None

  @model_validator(mode='after')
  def _coherence(self):
    import math
    # math.isfinite check rejects NaN, ±inf
    for name, val in (('entry_price', self.entry_price),
                      ('peak_price', self.peak_price),
                      ('trough_price', self.trough_price)):
      if val is not None and not math.isfinite(val):
        raise ValueError(f'{name}: must be finite (not NaN/±inf)')
    # D-03 direction-coherence checks
    if self.direction == 'LONG':
      if self.peak_price is not None and self.peak_price < self.entry_price:
        raise ValueError('peak_price: must be >= entry_price for LONG')
      if self.trough_price is not None:
        raise ValueError('trough_price: must be absent or null for LONG')
    else:  # SHORT
      if self.trough_price is not None and self.trough_price > self.entry_price:
        raise ValueError('trough_price: must be <= entry_price for SHORT')
      if self.peak_price is not None:
        raise ValueError('peak_price: must be absent or null for SHORT')
    if self.pyramid_level is not None:
      from system_params import MAX_PYRAMID_LEVEL  # local import (hex)
      if self.pyramid_level < 0 or self.pyramid_level > MAX_PYRAMID_LEVEL:
        raise ValueError(
          f'pyramid_level: must be in [0, {MAX_PYRAMID_LEVEL}]'
        )
    return self


def register(app: FastAPI) -> None:
  '''Register POST /trades/open + sibling routes.'''

  @app.post('/trades/open')
  def open_trade(req: OpenTradeRequest):
    # Phase 11 C-2: local imports preserve hex boundary
    from state_manager import load_state, save_state
    from sizing_engine import check_pyramid

    state = load_state()
    existing = state['positions'].get(req.instrument)

    if existing is not None and existing['direction'] != req.direction:
      # D-01: opposite direction is a hard conflict
      msg = (
        f'instrument {req.instrument} already has an open '
        f'{existing["direction"]} position; close it first via POST /trades/close '
        f'before opening a {req.direction}'
      )
      logger.warning('[Web] /trades/open conflict: %s', msg)
      return Response(content=msg, status_code=409, media_type='text/plain; charset=utf-8')

    if existing is not None and existing['direction'] == req.direction:
      # D-02: pyramid-up via sizing_engine.check_pyramid
      atr_entry = state['signals'].get(req.instrument, {}).get('atr')
      if atr_entry is None:
        return Response(
          content='pyramid blocked: no ATR available in state.signals',
          status_code=409, media_type='text/plain; charset=utf-8',
        )
      decision = check_pyramid(existing, current_price=req.entry_price, atr_entry=atr_entry)
      if decision.add_contracts == 0:
        msg = f'Pyramid blocked: gate not met or already at MAX_PYRAMID_LEVEL'
        return Response(content=msg, status_code=409, media_type='text/plain; charset=utf-8')
      # Apply pyramid-up
      existing['n_contracts'] += decision.add_contracts
      existing['pyramid_level'] = decision.new_level
    else:
      # Fresh open
      executed_at = req.executed_at or _now_awst().date()
      state['positions'][req.instrument] = _build_position_dict(req, executed_at, state)

    save_state(state)
    return _render_open_success_partial(state)  # HTML; UI-SPEC §Decision 3


def _now_awst():
  from datetime import datetime
  return datetime.now(_AWST)
```

### Pattern 2: POST /trades/close handler with inline gross_pnl per D-05

**What:** Close handler that builds the 11-field trade dict and calls `record_trade`. CRITICAL: `gross_pnl` is computed inline as raw price-delta — NEVER via `sizing_engine.compute_unrealised_pnl`.

**When to use:** Any operator-initiated full close of a position.

**Example:**
```python
# Source: composed from state_manager.record_trade contract (Phase 3 D-13/D-14/D-19)
class CloseTradeRequest(BaseModel):
  instrument: Literal['SPI200', 'AUDUSD']
  exit_price: float = Field(gt=0)
  executed_at: _date | None = None

  @model_validator(mode='after')
  def _exit_finite(self):
    import math
    if not math.isfinite(self.exit_price):
      raise ValueError('exit_price: must be finite (not NaN/±inf)')
    return self


@app.post('/trades/close')
def close_trade(req: CloseTradeRequest):
  from state_manager import load_state, save_state, record_trade

  state = load_state()
  pos = state['positions'].get(req.instrument)
  if pos is None:
    msg = f'no open position for instrument {req.instrument}'
    return Response(content=msg, status_code=409, media_type='text/plain; charset=utf-8')

  # D-07: read multiplier and cost_aud from _resolved_contracts (load_state rematerializes per Phase 8 D-14)
  resolved = state['_resolved_contracts'][req.instrument]
  multiplier = resolved['multiplier']
  cost_aud = resolved['cost_aud']

  # D-05 ANTI-PITFALL — DO NOT USE sizing_engine.compute_unrealised_pnl HERE.
  # record_trade D-14 deducts the closing-half cost. compute_unrealised_pnl
  # already deducts the opening-half cost. Passing realised_pnl as gross_pnl
  # would double-count the closing cost. See state_manager.py:499-506,
  # Phase 4 D-15/D-19 anti-pitfall.
  if pos['direction'] == 'LONG':
    gross_pnl = (req.exit_price - pos['entry_price']) * pos['n_contracts'] * multiplier
  else:  # SHORT
    gross_pnl = (pos['entry_price'] - req.exit_price) * pos['n_contracts'] * multiplier

  exit_date = (req.executed_at or _now_awst().date()).isoformat()
  trade = {
    'instrument': pos['instrument'] if 'instrument' in pos else req.instrument,
    'direction': pos['direction'],
    'n_contracts': pos['n_contracts'],
    'entry_date': pos['entry_date'],
    'exit_date': exit_date,
    'exit_reason': 'operator_close',  # D-06 literal
    'entry_price': pos['entry_price'],
    'exit_price': req.exit_price,
    'gross_pnl': gross_pnl,            # D-05 inline raw price-delta
    'multiplier': multiplier,           # D-07
    'cost_aud': cost_aud,               # D-07
  }
  state = record_trade(state, trade)   # _validate_trade gates (Phase 3 D-15/D-19)
  save_state(state)
  return _render_close_success_partial(state, req.instrument, gross_pnl, cost_aud, pos['n_contracts'])
```

### Pattern 3: POST /trades/modify handler (PATCH-style with absent-vs-null)

**What:** Modify handler that distinguishes "absent" (no change) from `null` (clear-override) per D-12 / Pattern 5.

**When to use:** Operator wants to override the trailing stop or change contract count without closing the position.

**Example:**
```python
class ModifyTradeRequest(BaseModel):
  instrument: Literal['SPI200', 'AUDUSD']
  new_stop: float | None = None      # null = clear override; absent = no change
  new_contracts: int | None = None   # absent = no change

  @model_validator(mode='after')
  def _at_least_one(self):
    # D-12: at least one field must be PRESENT (not just non-null)
    # Use model_fields_set to distinguish absent from null
    if not (self.model_fields_set & {'new_stop', 'new_contracts'}):
      raise ValueError(
        'at least one of new_stop, new_contracts must be present'
      )
    return self

  @model_validator(mode='after')
  def _new_contracts_floor(self):
    if 'new_contracts' in self.model_fields_set and self.new_contracts is not None:
      if self.new_contracts < 1:
        raise ValueError('new_contracts: must be >= 1')
    return self


@app.post('/trades/modify')
def modify_trade(req: ModifyTradeRequest):
  from state_manager import load_state, save_state

  state = load_state()
  pos = state['positions'].get(req.instrument)
  if pos is None:
    msg = f'no open position for instrument {req.instrument}'
    return Response(content=msg, status_code=409, media_type='text/plain; charset=utf-8')

  # Apply mutations IN-MEMORY first (D-11 atomic single save)
  if 'new_stop' in req.model_fields_set:
    # PRESENT: explicit set or null
    pos['manual_stop'] = req.new_stop  # may be None (clear-override)
  if 'new_contracts' in req.model_fields_set and req.new_contracts is not None:
    pos['n_contracts'] = req.new_contracts
    pos['pyramid_level'] = 0  # D-10: reset pyramid_level on any modify

  # D-11: single save_state — both updates land atomically or neither
  save_state(state)
  return _render_modify_success_partial(state, req.instrument)
```

### Pattern 4: Pydantic v2 schema with Literal + Field constraints + model_validator

**What:** Pydantic v2 idioms for declarative request validation.

**When to use:** Every Phase 14 request body.

**Example:** See Patterns 1, 2, 3 above. Reference: [CITED: docs.pydantic.dev — Fields concept page; Pydantic v2 migration guide].

### Pattern 5: Pydantic v2 PATCH semantics — `model_fields_set` for "absent vs null"

**What:** D-12's "null = clear override; absent = no change" semantics.

**When to use:** `/trades/modify` and any future PATCH-style endpoint.

**The discipline:**
- `field absent in JSON` → NOT in `model.model_fields_set`; `model.field` returns the declared default (`None`)
- `field present as null` → IS in `model.model_fields_set`; `model.field` is `None`
- `field present with value` → IS in `model.model_fields_set`; `model.field` is the value

**Idiom:**
```python
# Source: roman.pt/posts/handling-unset-values-in-fastapi-with-pydantic [CITED]
# Also: pythontutorials.net/blog/pydantic-detect-if-a-field-value-is-missing-or-given-as-null
if 'new_stop' in req.model_fields_set:
  # Field was explicitly sent (either as a number or as null)
  pos['manual_stop'] = req.new_stop  # may be None for clear-override
# else: field was absent — leave pos['manual_stop'] unchanged
```

**Test fixture for the three cases:**
```python
# Case A: field absent (no change)
ModifyTradeRequest(instrument='SPI200', new_contracts=2).model_fields_set
# → {'instrument', 'new_contracts'}  — 'new_stop' NOT present

# Case B: field present as null (clear override)
ModifyTradeRequest.model_validate({'instrument': 'SPI200', 'new_stop': None}).model_fields_set
# → {'instrument', 'new_stop'}  — 'new_stop' IS present, value None

# Case C: field present with value (set override)
ModifyTradeRequest.model_validate({'instrument': 'SPI200', 'new_stop': 7700.0}).model_fields_set
# → {'instrument', 'new_stop'}  — 'new_stop' IS present, value 7700.0
```

[ASSUMED] Pydantic 2.12+ ships an experimental `MISSING` sentinel based on draft PEP 661 [CITED: pydantic.dev/articles/pydantic-v2-12-release]. Phase 14 should NOT depend on it — `pydantic>=2.9.0` floor doesn't guarantee 2.12. Stick with `model_fields_set`.

### Pattern 6: 422→400 remap exception handler

**What:** FastAPI default for invalid request body is 422 Unprocessable Entity. SC-2 / TRADE-02 / D-04 require **HTTP 400** with body `{"errors": [{"field": "...", "reason": "..."}]}`.

**When to use:** Once, at app-factory level.

**Example:**
```python
# Source: fastapi.tiangolo.com/tutorial/handling-errors/ [CITED]
# Add to web/app.py::create_app() AFTER routes are registered, BEFORE add_middleware

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def _format_pydantic_errors(exc: RequestValidationError) -> list[dict]:
  '''Convert Pydantic v2 errors to {field, reason} shape per D-04.

  exc.errors() returns a list of dicts like:
    {'type': 'greater_than', 'loc': ('body', 'entry_price'),
     'msg': 'Input should be greater than 0', 'input': -1, 'ctx': {'gt': 0}}
  We extract the LAST element of 'loc' as the field name (skipping the 'body' prefix).
  '''
  out = []
  for err in exc.errors():
    loc = err.get('loc', ())
    # 'loc' is ('body', 'field_name') for body errors; pick the last str/int leaf
    leaf = next((str(p) for p in reversed(loc) if isinstance(p, str | int) and p != 'body'), '<root>')
    out.append({'field': leaf, 'reason': err.get('msg', 'invalid')})
  return out


async def _validation_exception_handler(request, exc: RequestValidationError):
  return JSONResponse(
    status_code=400,
    content={'errors': _format_pydantic_errors(exc)},
  )


# Inside create_app():
application.add_exception_handler(RequestValidationError, _validation_exception_handler)
```

**Verification:** Test that POST `/trades/open` with `{contracts: 0}` returns 400 with body containing `{"field": "contracts", "reason": "Input should be greater than or equal to 1"}`.

### Pattern 7: HTMX 1.9.12 vendoring with SRI

**What:** Drop-in `<script>` tag mirroring v1.0 Chart.js precedent.

**When to use:** Once, in `dashboard.py::_render_html_shell` (or the equivalent helper that emits the `<head>`).

**Example:**
```python
# Source: dashboard.py:115-116 Chart.js pattern; SRI verified in this research session
# Place adjacent to existing _CHARTJS_URL / _CHARTJS_SRI constants

_HTMX_URL = 'https://cdn.jsdelivr.net/npm/htmx.org@1.9.12/dist/htmx.min.js'
_HTMX_SRI = 'sha384-ujb1lZYygJmzgSwoxRggbCHcjc0rB2XoQrxeTUQyRjrOnlCoYta87iKBWq3EsdM2'

# In the <head>-emitting helper:
script_tag = (
  f'  <script src="{_HTMX_URL}" '
  f'integrity="{_HTMX_SRI}" crossorigin="anonymous"></script>\n'
)
# Place AFTER Chart.js (UI-SPEC §HTMX vendor pin: "<head> after Chart.js, before inline <style>")
```

### Pattern 8: HTMX response shapes (per UI-SPEC §Decision 3)

**What:** Return raw HTML for 2xx, JSON for 4xx — HTMX swaps on 2xx only by default.

**When to use:** Every Phase 14 POST.

| Endpoint | 2xx response | 4xx response |
|----------|-------------|--------------|
| `POST /trades/open` | `HTMLResponse(content=<full re-rendered <tbody>>)` + OOB swap div for confirmation banner | `JSONResponse(status_code=400, content={errors: [...]})` (or 409 plain text from D-01) |
| `POST /trades/close` | `HTMLResponse(content='')` + `HX-Trigger: positions-changed` header (UI-SPEC §Decision 3 option a) + OOB confirmation banner | `JSONResponse(...)` or 409 plain text |
| `POST /trades/modify` | `HTMLResponse(content=<single re-rendered <tr>>)` + OOB confirmation banner | `JSONResponse(...)` or 409 plain text |
| `GET /trades/close-form` | `HTMLResponse(content=<2-row block: original <tr> + confirmation panel <tr>>)` | (auth gate — never reaches handler unauth'd) |
| `GET /trades/modify-form` | `HTMLResponse(content=<2-row block: original <tr> + modify form <tr>>)` | (auth gate) |
| `GET /trades/cancel-row?instrument=...` | `HTMLResponse(content=<original <tr> re-rendered>)` | (auth gate) |

**Implementation pattern:**
```python
# Source: fastapi.tiangolo.com/advanced/custom-response/ [CITED]
from fastapi.responses import HTMLResponse

# Success: return the partial HTML
return HTMLResponse(
  content=_render_position_row_html(state, instrument),
  status_code=200,
  headers={'HX-Trigger': 'positions-changed'},  # OOB swap signal
)
```

**OOB confirmation banner (per UI-SPEC §Decision 3):**
```html
<!-- Append to the HTMLResponse body for any 2xx success -->
<div hx-swap-oob="innerHTML:#confirmation-banner">
  <p class="banner-success">Opened LONG SPI 200 at 7800.50, 2 contracts.</p>
</div>
```

### Pattern 9: fcntl exclusive lock around `_atomic_write` (D-13)

**What:** Wrap the existing `state_manager._atomic_write` so cross-process writes serialize.

**When to use:** Inside `state_manager.save_state` (Phase 14 modification — single chokepoint).

**Discipline (post-research correction):** Lock the **destination file** (`state.json`), NOT the tempfile. Reason:
- `os.replace(tmp, dest)` only updates the directory entry — the lock on `dest`'s descriptor must be held across the rename
- Both processes must lock the SAME file (the destination) — locking different tempfiles is meaningless
- The lock is advisory (cooperative): both writers must agree to acquire before writing. main.py's daily save and Phase 14 web POSTs both call `save_state`, which is the SOLE entry point — guaranteed cooperative.

**Cross-platform note (POSIX advisory):** `fcntl.flock` is supported on Linux + macOS. The droplet is Ubuntu (Linux); developer machine is macOS. NOT supported on Windows (no Windows target). No NFS in scope (state.json is local filesystem on droplet). [CITED: man7.org/linux/man-pages/man2/flock.2 — `flock()` is BSD-derived, supported on Linux; macOS supports via XNU implementation.]

**Lock-release on close:** `with open(...) as f:` exits → file descriptor closes → kernel releases the `flock`. The post-fsync, post-os.replace sequence MUST occur inside the `with` block. [CITED: docs.python.org/3/library/fcntl.html — `flock()` lock is released when the underlying file descriptor is closed].

**Example:**
```python
# Source: composed from state_manager.py:113 _atomic_write + fcntl docs
# Modification target: state_manager._atomic_write (or a new save_state wrapper)
import fcntl

def _atomic_write(data: str, path: Path) -> None:
  '''STATE-02 / D-08 + D-17 + Phase 14 D-13: tempfile + fsync + os.replace + dir fsync,
  serialized cross-process via fcntl.LOCK_EX advisory lock on the destination file.

  Lock semantics:
    - flock() advisory lock on the DESTINATION file's open file description
    - Held across the entire critical section (write tempfile -> fsync -> rename -> dir fsync)
    - Released automatically when the lock-holder file descriptor closes (with-statement exit)
    - Blocking-indefinite per D-13 (no timeout); daily save ~50ms, web POST ~10-100ms
  '''
  parent = path.parent
  tmp_path_str = None

  # D-13: open destination for lock; create empty if missing (so first run can lock)
  # Open with O_RDWR|O_CREAT — does NOT truncate; idempotent on existing file.
  lock_fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o644)
  try:
    fcntl.flock(lock_fd, fcntl.LOCK_EX)  # blocks until exclusive lock acquired
    try:
      with tempfile.NamedTemporaryFile(
        dir=parent, delete=False, mode='w', suffix='.tmp', encoding='utf-8',
      ) as tmp:
        tmp_path_str = tmp.name
        tmp.write(data)
        tmp.flush()
        os.fsync(tmp.fileno())
      # tempfile closed; D-17: os.replace BEFORE parent-dir fsync
      os.replace(tmp_path_str, path)
      if os.name == 'posix':
        dir_fd = os.open(str(parent), os.O_RDONLY)
        try:
          os.fsync(dir_fd)
        finally:
          os.close(dir_fd)
      tmp_path_str = None
    finally:
      if tmp_path_str is not None:
        try:
          os.unlink(tmp_path_str)
        except FileNotFoundError:
          pass
  finally:
    fcntl.flock(lock_fd, fcntl.LOCK_UN)  # explicit unlock (close also releases)
    os.close(lock_fd)
```

**Why open the destination file (not the parent dir or a separate `.lock` file):**
- Locking `state.json` directly: easy to reason about; `os.replace(tmp, state.json)` swaps the inode but the LOCK is on the open file description that points to the OLD inode. After `os.replace`, the lock is still held on the now-orphaned inode (which is unlinked on close). This is fine — the critical section is "tempfile → fsync → rename → dir fsync", and the next writer will lock the NEW inode (the renamed-in tempfile).
- Locking a sidecar `state.json.lock`: avoids the orphaned-inode subtlety but adds a file. NOT needed — the orphan-on-rename behavior is well-defined.
- Locking the parent directory: would block anything trying to add files to the directory; overkill.

**Test pattern:** A pytest fixture that opens a separate `multiprocessing.Process` holding `fcntl.LOCK_EX` on `state.json` for 0.5s; main test thread calls `save_state` and asserts it blocks until the holder releases, with elapsed time within an expected window (`>= 0.4s` and `< 1.0s`).

### Pattern 10: AST guard for sole-writer invariant (TRADE-06)

**What:** Static check that `web/routes/trades.py` does not write to `state['warnings']`.

**When to use:** Add to `tests/test_web_trades.py` (or extend `tests/test_web_healthz.py::TestWebHexBoundary`).

**Example:**
```python
# Source: composed from CONTEXT.md TRADE-06 + Phase 13 AST guard pattern
# tests/test_web_trades.py
import ast
from pathlib import Path

class TestSoleWriterInvariant:
  '''TRADE-06: web/routes/trades.py must NOT write to state['warnings'].'''

  def test_no_warnings_subscript_assignment(self):
    src = Path('web/routes/trades.py').read_text()
    tree = ast.parse(src)
    violations = []
    for node in ast.walk(tree):
      # Detect: state['warnings'] = ...   or   foo['warnings'] = ...
      if isinstance(node, ast.Assign):
        for tgt in node.targets:
          if (isinstance(tgt, ast.Subscript)
              and isinstance(tgt.slice, ast.Constant)
              and tgt.slice.value == 'warnings'):
            violations.append(f'line {node.lineno}: assigns to <expr>["warnings"]')
      # Detect: state['warnings'].append(...)
      if (isinstance(node, ast.Call)
          and isinstance(node.func, ast.Attribute)
          and node.func.attr in ('append', 'extend', 'insert')):
        attr_obj = node.func.value
        if (isinstance(attr_obj, ast.Subscript)
            and isinstance(attr_obj.slice, ast.Constant)
            and attr_obj.slice.value == 'warnings'):
          violations.append(f'line {node.lineno}: mutates <expr>["warnings"]')
    assert violations == [], '\n'.join(violations)
```

### Pattern 11: Schema migration v2→v3 (D-09)

**What:** Walk-forward migration that adds `manual_stop: None` to every Position dict in `state['positions']`.

**When to use:** Once, in `state_manager._migrate_v2_to_v3`. Existing v2 droplet state.json files migrate automatically on next `load_state`.

**Example:**
```python
# Source: composed from state_manager.MIGRATIONS dict pattern (state_manager.py:104-107)
def _migrate_v2_to_v3(s: dict) -> dict:
  '''Phase 14 D-09: backfill manual_stop=None on every existing Position dict.

  Position TypedDict gained manual_stop in Phase 14. Existing v2 state files
  have positions like {SPI200: None, AUDUSD: {direction:..., entry_price:...}}
  — the dict-valued positions need manual_stop=None added; None positions
  stay None (no position to migrate).

  Idempotent: running on already-v3 data is a no-op (manual_stop already None
  or float). load_state passes the result through _validate_loaded_state which
  validates KEY PRESENCE only — manual_stop value type is enforced by
  sizing_engine.get_trailing_stop NaN guards (which already accept None).
  '''
  positions = s.get('positions', {})
  new_positions = {}
  for instrument, pos in positions.items():
    if pos is None:
      new_positions[instrument] = None
    else:
      # Set manual_stop=None if absent; preserve existing value if already migrated
      new_positions[instrument] = {**pos, 'manual_stop': pos.get('manual_stop')}
  return {**s, 'positions': new_positions}


# In MIGRATIONS dict (state_manager.py:104):
MIGRATIONS: dict = {
  1: lambda s: s,
  2: _migrate_v1_to_v2,
  3: _migrate_v2_to_v3,  # Phase 14 D-09
}

# In system_params.py:
STATE_SCHEMA_VERSION: int = 3       # was 2; bumped Phase 14 D-09
```

**Forward/backward compatibility:**
- **v2 → v3 (forward):** Existing droplet state.json with schema_version=2 loads cleanly; `_migrate` walks v2→v3 silently; on next `save_state` the file is rewritten with `schema_version: 3` and `manual_stop: null` on each Position dict.
- **v3 saved, code rolled back to pre-Phase-14 (backward):** Save_state's underscore-strip filter (`{k: v for k, v in state.items() if not k.startswith('_')}`) only filters TOP-LEVEL keys [VERIFIED: state_manager.py:427]. The `manual_stop` field inside a position dict is NOT stripped on save. If pre-Phase-14 code reads a v3 state file:
  - `_validate_loaded_state` checks key presence only [VERIFIED: state_manager.py:296-298]; the schema version mismatch would NOT trigger a validation error UNLESS `STATE_SCHEMA_VERSION` is bumped in pre-Phase-14 code (it isn't)
  - Pre-Phase-14 `_migrate` reads `schema_version: 3`; the loop `while version < STATE_SCHEMA_VERSION` (where `STATE_SCHEMA_VERSION=2` in pre-Phase-14 code) is a no-op
  - The `manual_stop` extra field is silently retained in the dict — no code reads it pre-Phase-14
  - **Risk:** If pre-Phase-14 code rewrites the state via `save_state`, the `manual_stop` field is preserved (because save_state doesn't filter nested keys). No data loss.
  - **Safer rollback:** Operator runs a `python -c "from state_manager import reset_state, save_state; save_state(reset_state())"` to write a clean v2 state. Documented in deferred-items.md.

**Test fixtures required:**
- `tests/fixtures/state_v2.json` — a v2 state.json with one open position (no `manual_stop` field)
- Round-trip test: `load_state(v2.json)` → assert `positions['SPI200']['manual_stop'] is None`; `save_state(state)` → re-`load_state` → still works
- Idempotency: migrate twice → identical output

### Anti-Patterns to Avoid

- **NEVER call `sizing_engine.compute_unrealised_pnl` in `/trades/close`.** Anti-pitfall comment in D-05 is mandatory. `record_trade` deducts the closing-half cost; `compute_unrealised_pnl` already deducts the opening-half. Passing `realised_pnl` as `gross_pnl` double-counts. The inline raw price-delta formula is the ONLY correct approach. Documented in CONTEXT.md D-05 + state_manager.py:499-506 + this research §Code Examples.
- **NEVER lock the tempfile.** It's about to be unlinked. Lock the destination file (Pattern 9).
- **NEVER use `Optional[X]` for fields where "absent vs null" matters in Pydantic v2.** Both `Optional[X]` and `X | None` produce the same schema (the field default is used when key is absent). The distinguishing signal is `model.model_fields_set` — not the type annotation.
- **NEVER write `state['warnings'] = ...` or `.append(...)` from a Phase 14 handler.** Sole-writer invariant is enforced by Pattern 10 AST test.
- **NEVER assume `state['_resolved_contracts']` is present without `load_state`.** It's a runtime-only key materialized by `load_state` (Phase 8 D-14 / state_manager.py:398-401). If a test builds a state dict manually, `_resolved_contracts` won't be there. All Phase 14 handlers call `load_state()` first → safe.
- **NEVER hand-write a 422 response.** Use Pattern 6 — single global `RequestValidationError` exception handler at app-factory level.
- **NEVER skip the 409 path for opposite-direction positions.** D-01 forbids overwrite. The 409 message string is locked in D-01 and quoted in UI-SPEC §Decision 3 conflict copy.
- **NEVER include `_csrf_token`, sessions, or cookies.** v1.1 single-operator. The shared-secret header is the auth + CSRF substitute (third-party origins can't supply it).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Request body validation | Custom argparse-style field checker | Pydantic v2 `BaseModel` + `Field(gt=0, ge=1)` + `model_validator` | Pydantic generates clean error messages, integrates with FastAPI's `RequestValidationError`, supports field-level `Literal` enums, handles JSON parsing |
| 422→400 status remap | Per-route `try/except RequestValidationError` | Single `app.add_exception_handler(RequestValidationError, ...)` | One handler covers all `/trades/*` POSTs; no per-route boilerplate |
| HTML escaping in HTMX partials | Manual `s.replace('<', '&lt;')...` | `html.escape(value, quote=True)` (stdlib) — already used by `dashboard.py` per the leaf-render rule (dashboard.py:42) | Stdlib coverage is correct; project already does this; CLAUDE.md global pattern explicitly warns against innerHTML without escape |
| File locking | Custom lock-file (`*.lock`) sentinel pattern | `fcntl.flock(fd, fcntl.LOCK_EX)` on the destination file | OS-level advisory lock; cross-process safe; release-on-close is automatic; stdlib only |
| `gross_pnl` math | Reusing `sizing_engine.compute_unrealised_pnl` | Inline raw price-delta formula (Pattern 2) | Avoids closing-half cost double-deduction (D-05) |
| Position close primitive | Custom inline mutation of `state['positions']` and `state['trade_log']` | `state_manager.record_trade(state, trade)` | Existing `_validate_trade` checks all 11 fields; `record_trade` handles atomic position-zero-out + trade_log append + account update + closing-half cost deduction (Phase 3 D-13/D-14) |
| Pyramid rule | Custom price-delta-vs-ATR check | `sizing_engine.check_pyramid(position, current_price, atr_entry)` | D-12 stateless invariant; pure-math hex; reuses v1.0 risk discipline (Phase 2 PYRA-01..05) |
| Date defaults | `datetime.utcnow().date()` | `datetime.now(zoneinfo.ZoneInfo('Australia/Perth')).date()` | CLAUDE.md: "Times always AWST in user-facing output"; existing `state_manager._AWST` precedent |
| HTMX response shape switching | Conditional content-type per status code | FastAPI `HTMLResponse` for 2xx, `JSONResponse` for 4xx | HTMX's default behavior is "swap on 2xx only"; mismatched content types cause silent no-op swaps |
| AST hex-boundary check | Per-file ad-hoc grep | Existing `tests/test_web_healthz.py::TestWebHexBoundary` pattern | Already enforces `web/` doesn't import forbidden hex modules; Phase 14 ADDS one assertion that `sizing_engine` is now allowed (mirroring Phase 13 D-07's `dashboard` promotion) |

**Key insight:** Every "deceptively simple" piece of Phase 14 has an existing pure-math or pure-stdlib primitive. Hand-rolling is a sign of misunderstanding the boundary.

## Runtime State Inventory

> Phase 14 is a code-feature phase, not a rename/refactor. Most categories are NOT applicable, but the schema migration v2→v3 introduces a stored-data effect that warrants explicit documentation here.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `state.json` on droplet currently has `schema_version: 2` (or `1` if pre-Phase-8) and Position dicts WITHOUT `manual_stop` field. Phase 14 migration v2→v3 backfills `manual_stop=None` on every Position dict on first `load_state` after deploy. | Plan: include `_migrate_v2_to_v3` (Pattern 11) + bump `STATE_SCHEMA_VERSION 2 → 3` in system_params.py. Migration runs automatically on next `load_state` — operator does NOT need to run a script. Test: load `tests/fixtures/state_v2.json` → assert v3 result. |
| Live service config | None — Phase 14 introduces no new external service configuration. `WEB_AUTH_SECRET` (already required by Phase 13) is unchanged; no new env vars added by Phase 14. | None |
| OS-registered state | None — Phase 14 doesn't register systemd units, Task Scheduler entries, or pm2 processes. Existing `trading-signals.service` and `trading-signals-web.service` are unchanged (Phase 11). | None |
| Secrets/env vars | None — Phase 14 reads `WEB_AUTH_SECRET` only via the existing Phase 13 AuthMiddleware which gates `/trades/*` automatically. No new secrets. | None |
| Build artifacts | None — Phase 14 introduces no new pip dependencies (FastAPI 0.136.1, Pydantic 2.x, fcntl stdlib all already in scope). HTMX 1.9.12 loads via CDN with SRI; no `node_modules`, no compiled assets. | None |

**The canonical question:** *After every file in the repo is updated, what runtime systems still have the old string cached, stored, or registered?* — **Only state.json on the droplet has the old (v2) schema. The migration handles it transparently on next `load_state`. No operator action required beyond the deploy.**

## Common Pitfalls

### Pitfall 1: `compute_unrealised_pnl` for `gross_pnl` (D-05 anti-pitfall)
**What goes wrong:** `record_trade` D-14 deducts the closing-half cost. `compute_unrealised_pnl` already deducted the opening-half. Passing the latter as the former double-counts the closing cost.
**Why it happens:** Both functions return "P&L"; the variable name `gross_pnl` is ambiguous to a reader.
**How to avoid:** D-05 mandates an INLINE raw price-delta formula with a comment block citing state_manager.py:499-506 and Phase 4 D-15/D-19.
**Warning signs:** A handler that imports `sizing_engine.compute_unrealised_pnl`. The hex AST guard test extension should consider FORBIDDING `compute_unrealised_pnl` as an importable name in `web/routes/trades.py` to make this defensive at the static layer.

### Pitfall 2: Pydantic `Optional[X]` ≠ "absent allowed"
**What goes wrong:** A reader thinks `peak_price: Optional[float] = None` means "must be present, can be null". It actually means "absent OR null gives None default".
**Why it happens:** Optional in static-typing land means "could be None"; Pydantic's runtime model uses the default-value mechanism for absence.
**How to avoid:** Use `model_fields_set` (Pattern 5) for any "absent vs null" distinction. Annotate as `X | None = None` (PEP 604 style, project convention).
**Warning signs:** A test that passes `{}` to a Pydantic model and the model accepts it where it shouldn't.

### Pitfall 3: `os.replace` invalidates the locked inode
**What goes wrong:** Naively, you might think "lock state.json, then `os.replace` the new tempfile, then unlock". After `os.replace`, the original inode you locked is unlinked. The lock you hold is on the orphaned inode. The next process that opens `state.json` is opening the NEW inode (the renamed-in tempfile) and acquires a fresh lock.
**Why it happens:** Confusion between "file path" (a directory entry) and "file" (an inode + open file description).
**How to avoid:** This actually WORKS correctly under `fcntl.flock`. The semantics are:
1. Process A opens state.json (inode 100), `flock(LOCK_EX)`
2. Process A writes tempfile, fsync, `os.replace(tempfile, state.json)` — directory entry now points to inode 200; inode 100 is now orphan-but-still-open
3. Process A `close(fd)` — releases lock on inode 100; inode 100 is unlinked from filesystem
4. Process B was waiting on `flock(LOCK_EX)` on its own open of state.json → which is inode 200 (the new file) — Process B acquires the fresh lock on inode 200
5. Two processes both opened `state.json` at step 1 → both got inode 100 → only one acquires the lock (the OS serializes); the other waits. After A releases (step 3), B's open is still on inode 100 (orphan) — B's lock attempt SUCCEEDS on inode 100 trivially because no other holder. B then writes-and-replaces, but its `os.replace` acts on the directory entry (now pointing to A's inode 200) — B's tempfile becomes inode 300, replacing inode 200. **Sequencing: A then B writes are correctly serialized via the lock on the original inode.**

**Edge case:** If A and B both `os.open(state.json)` at the EXACT same moment, both might end up on the same inode 100 and the lock serializes them as documented. But if A `os.replace` happens BETWEEN B's `open` and B's `flock`, B is on inode 200 (no contention with A). **This is fine** — B is the second writer; A already finished.

**Warning signs:** A pytest that runs two threads concurrently calling `save_state` and observes torn JSON. (Won't happen — atomicity is preserved by `os.replace` regardless of locking.)

**Test pattern:** Run two `multiprocessing.Process`-based writers, both call `save_state(state_with_unique_marker)` 10 times each in a loop. Assert that final `state.json` is parseable JSON and contains one of the markers (NOT a torn mix).

### Pitfall 4: HTMX `hx-target` ID drift between dashboard.py render and route response
**What goes wrong:** UI-SPEC §Decision 3 mandates `hx-target="#position-row-SPI200"`. If `dashboard.py::_render_positions_table` emits `<tr>` without `id="position-row-SPI200"`, the HTMX swap silently no-ops (HTMX logs a warning to console, but the operator sees no change in the table).
**Why it happens:** UI markup and HTMX glue live in different files; renaming or restructuring drifts.
**How to avoid:** Pattern 12 (below) — a regression test that grep-checks the rendered HTML for the IDs documented in UI-SPEC.
**Warning signs:** "I clicked Modify and nothing happened in the table" — usually a missing or mistyped target ID.

### Pitfall 5: First-time positions don't have `manual_stop` after migration
**What goes wrong:** `_migrate_v2_to_v3` backfills `manual_stop=None` on existing Position dicts. But a NEW position opened via Phase 14 must explicitly set `manual_stop=None` in its dict-construction path — otherwise `_validate_loaded_state` won't catch it (KEY PRESENCE only) but `sizing_engine.get_trailing_stop` may KeyError.
**Why it happens:** Position TypedDict adds the field, but TypedDict is structural — a dict missing the key still passes `isinstance(d, dict)`.
**How to avoid:** The position-construction path in `web/routes/trades.py::open_trade` MUST include `manual_stop=None`. Equally important: `sizing_engine.get_trailing_stop` should use `.get('manual_stop')` (returning None on absence) rather than `position['manual_stop']` (KeyError on absence).
**Warning signs:** Pyramid-up of an existing position that hasn't been migrated yet (older state file) raises KeyError on next render.

### Pitfall 6: `state['_resolved_contracts']` missing in test-built state dicts
**What goes wrong:** A test builds `state = {'positions': {...}, ...}` directly (not via `load_state`). Phase 14 handlers do `state['_resolved_contracts'][instrument]` and KeyError.
**Why it happens:** `_resolved_contracts` is rematerialized only in `load_state` (state_manager.py:398-401).
**How to avoid:** Tests should call `load_state` (with a fixture path) rather than building state dicts inline. If inline construction is needed, manually set `_resolved_contracts` to match.
**Warning signs:** "KeyError: '_resolved_contracts'" in a Phase 14 test.

## Code Examples

(All examples consolidated in §Architecture Patterns above. Each example block names its source.)

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Pydantic v1 `Optional[X]` + `Field(...)` | Pydantic v2 `X | None` + `Field(gt=0)` + `@model_validator(mode='after')` | Pydantic v2 GA (2023-06-30); FastAPI 0.100+ requires v2 | Phase 14 uses v2 idioms only; v1 syntax (e.g., `@validator`) is removed in v2 |
| Pydantic v1 `__fields_set__` | Pydantic v2 `model_fields_set` (public API) | Pydantic v2 (2023-06-30) | Use the public name; `__pydantic_fields_set__` exists but is private |
| FastAPI 422 (default) | Custom 400 via `app.add_exception_handler(RequestValidationError, ...)` | Project decision per D-04 / TRADE-02 | One global handler covers all routes |
| HTMX 1.9.x | HTMX 2.0.x available (latest 2.0.10 at 2026-04-25) | HTMX 2.0.0 released 2024-06-17 | Phase 14 sticks with 1.9.12 — UI-SPEC pin; `hx-on::*` event listener semantics differ in 2.x |
| `_EMAIL_FROM` hardcoded | `SIGNALS_EMAIL_FROM` env var | Phase 12 D-15 | Not Phase 14 scope; precedent confirms env-var pattern for operator-configurable values |
| Phase 10 D-15 "web is read-only on state.json" | Phase 14 D-13/D-14: web is a peer writer; coordination via fcntl | Phase 14 (this phase) | Documented amendment in CONTEXT.md `<canonical_refs>` block |

**Deprecated/outdated:**
- Pydantic v1: replaced by v2 (no backward compat layer in Phase 14)
- Pydantic `__fields_set__` private name: prefer `model_fields_set`
- HTMX 1.x for new projects: HTMX 2.x is current. **Phase 14 deliberately stays on 1.9.12** per UI-SPEC pin (event listener ABI differences and the existing `hx-on::after-request` pattern in UI-SPEC §Decision 4).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Pydantic 2.12 `MISSING` sentinel is experimental and not in the `pydantic>=2.9.0` floor that FastAPI 0.136 declares | §Standard Stack — Alternatives Considered | Low — Phase 14 doesn't depend on it; using `model_fields_set` (stable since v2.0) is the recommendation regardless |
| A2 | Phase 14 deploys to a droplet with v2 state.json (not v1). | §Runtime State Inventory | Low — `_migrate` walks forward from any version; v1 state files would migrate v1→v2→v3 transparently. If droplet has v1 (pre-Phase-8), it migrates fine. |
| A3 | `state.json` is on a local POSIX filesystem (ext4/APFS), not NFS. | Pattern 9 + §Common Pitfalls | Medium — `fcntl.flock` is unreliable on NFS. Project description confirms droplet=Ubuntu (local disk) and dev=macOS (local APFS). NOT validated for NFS. If operator ever moves state.json to NFS, fcntl behavior is undefined. |
| A4 | The HTMX 1.9.12 UMD bundle from unpkg/jsdelivr is byte-stable across CDN reads. | §Standard Stack — HTMX vendoring | Low — verified byte-identical between unpkg and jsdelivr in this session; SRI hash also independently re-verified. CDNs cache immutable npm tarballs; 1.9.12 won't change. |
| A5 | The 2-stage destructive close confirmation pattern (Stage 1: Close → confirm panel; Stage 2: Confirm close → POST) is the right UX shape. | §Architecture Patterns — Pattern 8 / UI-SPEC §Decision 5 | Low — UI-SPEC §Decision 5 already locked this. Confirmation panels with inline exit-price input are a documented HTMX idiom. No canonical "best practice" surfaced in search; pattern is composed from HTMX primitives. |
| A6 | Locking the destination file (state.json) and relying on `os.replace` semantics is correct under `fcntl.flock`. | Pattern 9 + §Pitfall 3 | Medium — argument is sound (advisory lock; first writer holds inode-100 lock; subsequent open after replace is on inode-200 fresh lock; serialization preserved). Verified mentally; should be confirmed via the multi-process test fixture in Phase 14 plan. |

**If this table is not empty:** Confirm assumptions A3 (NFS posture) and A6 (lock semantics on os.replace) at planning kickoff. A1, A2, A4, A5 are low-risk and proceed.

## Open Questions

1. **Should `web/routes/trades.py` import `sizing_engine.check_pyramid` at module top or LOCAL inside the handler?**
   - What we know: Phase 11 C-2 mandates LOCAL imports for `state_manager` and `dashboard` adapters. Phase 13 D-07 promoted `dashboard` to "allowed adapter import" but kept the local-import discipline.
   - What's unclear: `sizing_engine` is pure-math (not an adapter). The C-2 rationale was "monkeypatch.setattr surface". For pure-math modules, monkeypatching is rare.
   - Recommendation: Keep LOCAL inside the handler for consistency with the established pattern. The cost is negligible (one extra import resolution per request). Avoids an exception in the hex-boundary AST guard.

2. **Should the `_atomic_write` lock be acquired per `save_state` call OR held across `load_state → mutate → save_state`?**
   - What we know: D-13 specifies `save_state` acquires the lock. The "load + mutate + save" sequence in handler is non-atomic at the application level.
   - What's unclear: A two-process race is possible: Process A loads state, Process B loads state, both mutate, both save. Process B's save overwrites Process A's mutation (lost update).
   - Recommendation: Phase 14 v1 accepts this (per D-13). The single-operator + workers=1 + single droplet posture means concurrent web POSTs are queued by uvicorn (single thread per worker). Cross-process race (web vs main.py daily save) is bounded by the daily save's narrow timing window (00:00 UTC = 08:00 AWST). Operator is unlikely to POST during that ~50ms window. **If lost-update becomes a concern in v1.2:** wrap each handler in a "load → mutate → save under lock" critical section that holds the flock across the read-modify-write. Documented as deferred risk.

3. **HTMX 2.x migration timeline — should Phase 14 land on 2.x to avoid future churn?**
   - What we know: HTMX 2.0.10 is current as of 2026-04-25. UI-SPEC pins 1.9.12.
   - What's unclear: HTMX 1.9.12 is the FINAL 1.9.x release (2024-04-25 — 2 years old). Maintenance posture is "fixes only".
   - Recommendation: UI-SPEC's pin is the contract; Phase 14 honors it. Phase 16 hardening (or v1.2) can re-evaluate. Migration cost is low (HTMX 2.x has a documented diff page; the Phase 14 surface uses simple primitives that map cleanly).

## Environment Availability

> Phase 14 has no new external dependencies. All required components are stdlib (fcntl, hmac, math, zoneinfo, ast) or already pinned in `requirements.txt`. Skipping detailed availability audit.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11 | All Phase 14 code | ✓ | 3.11.x (project pin) | — |
| `fastapi` | `web/routes/trades.py`, exception handler | ✓ (pinned in requirements.txt) | 0.136.1 | — |
| `pydantic` | All request models | ✓ (transitive via fastapi==0.136.1; floor 2.9.0) | >=2.9.0 | — |
| `fcntl` (stdlib) | `state_manager._atomic_write` lock | ✓ | stdlib | — (Windows would have to use msvcrt, but Windows is not a target) |
| HTMX 1.9.12 (CDN) | dashboard.py SRI script tag | ✓ (verified via unpkg + jsdelivr; SRI hash computed) | 1.9.12 | jsdelivr ↔ unpkg interchangeable (byte-identical files) |
| `hmac` (stdlib) | n/a (Phase 13 already uses) | ✓ | stdlib | — |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** None.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.3.3 + pytest-freezer 0.4.9 (pinned in `requirements.txt`) |
| Config file | (none — pytest auto-discovers `tests/` via `testpaths` convention; project has zero pytest.ini) |
| Quick run command | `pytest tests/test_web_trades.py -x` |
| Full suite command | `pytest -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TRADE-01 | POST /trades/open creates a new position | unit | `pytest tests/test_web_trades.py::TestOpenTrade::test_fresh_open_creates_position -x` | ❌ Wave 0 |
| TRADE-01 | POST /trades/open with same direction triggers pyramid-up | unit | `pytest tests/test_web_trades.py::TestOpenTrade::test_same_direction_pyramids_via_check_pyramid -x` | ❌ Wave 0 |
| TRADE-01 | POST /trades/open with opposite direction returns 409 | unit | `pytest tests/test_web_trades.py::TestOpenTrade::test_opposite_direction_returns_409 -x` | ❌ Wave 0 |
| TRADE-01 | Pyramid-gate-rejected returns 409 with check_pyramid reason | unit | `pytest tests/test_web_trades.py::TestOpenTrade::test_pyramid_gate_blocked_returns_409 -x` | ❌ Wave 0 |
| TRADE-02 | POST /trades/open with `instrument='BTC'` returns 400 with field-level error | unit | `pytest tests/test_web_trades.py::TestOpenValidation::test_invalid_instrument_returns_400 -x` | ❌ Wave 0 |
| TRADE-02 | POST /trades/open with `entry_price=-1` returns 400 | unit | `pytest tests/test_web_trades.py::TestOpenValidation::test_negative_entry_price_returns_400 -x` | ❌ Wave 0 |
| TRADE-02 | POST /trades/open with `entry_price=NaN` returns 400 | unit | `pytest tests/test_web_trades.py::TestOpenValidation::test_nan_entry_price_returns_400 -x` | ❌ Wave 0 |
| TRADE-02 | POST /trades/open with `contracts=0` returns 400 | unit | `pytest tests/test_web_trades.py::TestOpenValidation::test_zero_contracts_returns_400 -x` | ❌ Wave 0 |
| TRADE-02 | 400 body has shape `{errors: [{field, reason}]}` | unit | `pytest tests/test_web_trades.py::TestOpenValidation::test_400_body_shape -x` | ❌ Wave 0 |
| TRADE-02 | 400 errors enumerate ALL invalid fields, not just first | unit | `pytest tests/test_web_trades.py::TestOpenValidation::test_400_lists_all_invalid_fields -x` | ❌ Wave 0 |
| TRADE-03 | POST /trades/close records via record_trade; account updates | unit | `pytest tests/test_web_trades.py::TestCloseTrade::test_close_long_updates_account -x` | ❌ Wave 0 |
| TRADE-03 | LONG close P&L math = (exit - entry) * n * mult - cost (closing-half) | unit | `pytest tests/test_web_trades.py::TestCloseTrade::test_close_long_pnl_math_matches_inline_formula -x` | ❌ Wave 0 |
| TRADE-03 | SHORT close P&L math = (entry - exit) * n * mult - cost (closing-half) | unit | `pytest tests/test_web_trades.py::TestCloseTrade::test_close_short_pnl_math_matches_inline_formula -x` | ❌ Wave 0 |
| TRADE-03 | exit_reason on closed trade equals `'operator_close'` literal | unit | `pytest tests/test_web_trades.py::TestCloseTrade::test_exit_reason_is_operator_close -x` | ❌ Wave 0 |
| TRADE-03 | Closing-half cost is NOT double-deducted (anti-pitfall regression) | unit | `pytest tests/test_web_trades.py::TestCloseTrade::test_no_double_deduction_of_closing_cost -x` | ❌ Wave 0 |
| TRADE-04 | POST /trades/modify with `new_stop=7700.0` sets manual_stop | unit | `pytest tests/test_web_trades.py::TestModifyTrade::test_modify_sets_manual_stop -x` | ❌ Wave 0 |
| TRADE-04 | POST /trades/modify with `new_stop=null` (PRESENT) clears manual_stop | unit | `pytest tests/test_web_trades.py::TestModifyTrade::test_modify_null_stop_clears_override -x` | ❌ Wave 0 |
| TRADE-04 | POST /trades/modify with new_stop ABSENT leaves manual_stop unchanged | unit | `pytest tests/test_web_trades.py::TestModifyTrade::test_modify_absent_stop_no_change -x` | ❌ Wave 0 |
| TRADE-04 | POST /trades/modify with `new_contracts=5` updates n_contracts; pyramid_level resets to 0 | unit | `pytest tests/test_web_trades.py::TestModifyTrade::test_modify_new_contracts_resets_pyramid_level -x` | ❌ Wave 0 |
| TRADE-04 | POST /trades/modify with both fields applies both atomically | unit | `pytest tests/test_web_trades.py::TestModifyTrade::test_modify_both_fields_atomic_save -x` | ❌ Wave 0 |
| TRADE-04 | POST /trades/modify with empty body returns 400 | unit | `pytest tests/test_web_trades.py::TestModifyTrade::test_modify_empty_body_returns_400 -x` | ❌ Wave 0 |
| TRADE-04 | POST /trades/modify with `new_contracts=0` returns 400 | unit | `pytest tests/test_web_trades.py::TestModifyTrade::test_modify_zero_contracts_returns_400 -x` | ❌ Wave 0 |
| TRADE-04 | POST /trades/modify with `new_stop=NaN` returns 400 | unit | `pytest tests/test_web_trades.py::TestModifyTrade::test_modify_nan_stop_returns_400 -x` | ❌ Wave 0 |
| TRADE-05 | dashboard.py renders HTMX 1.9.12 SRI script tag in head | unit | `pytest tests/test_web_dashboard.py::TestHTMXVendor::test_htmx_sri_script_present -x` | ❌ Wave 0 (extension) |
| TRADE-05 | _render_positions_table emits id="positions-tbody" | unit | `pytest tests/test_web_dashboard.py::TestHTMXMarkup::test_tbody_has_target_id -x` | ❌ Wave 0 |
| TRADE-05 | Each position <tr> emits id="position-row-{instrument}" | unit | `pytest tests/test_web_dashboard.py::TestHTMXMarkup::test_position_row_ids -x` | ❌ Wave 0 |
| TRADE-05 | Open form emits hx-post="/trades/open" + hx-target="#positions-tbody" | unit | `pytest tests/test_web_dashboard.py::TestHTMXMarkup::test_open_form_hx_attrs -x` | ❌ Wave 0 |
| TRADE-05 | Each row has Close button with hx-get="/trades/close-form?instrument=..." | unit | `pytest tests/test_web_dashboard.py::TestHTMXMarkup::test_close_button_hx_attrs -x` | ❌ Wave 0 |
| TRADE-05 | Each row has Modify button with hx-get="/trades/modify-form?instrument=..." | unit | `pytest tests/test_web_dashboard.py::TestHTMXMarkup::test_modify_button_hx_attrs -x` | ❌ Wave 0 |
| TRADE-05 | manual_stop=None → no manual badge in cell | unit | `pytest tests/test_web_dashboard.py::TestManualStopBadge::test_no_badge_when_manual_stop_is_none -x` | ❌ Wave 0 |
| TRADE-05 | manual_stop=float → manual badge present | unit | `pytest tests/test_web_dashboard.py::TestManualStopBadge::test_badge_when_manual_stop_set -x` | ❌ Wave 0 |
| TRADE-05 | _compute_trail_stop_display returns manual_stop when set | unit | `pytest tests/test_web_dashboard.py::TestManualStopMath::test_manual_stop_takes_precedence -x` | ❌ Wave 0 |
| TRADE-05 | sizing_engine.get_trailing_stop honors manual_stop | unit | `pytest tests/test_sizing_engine.py::TestManualStopOverride::test_manual_stop_overrides_computed -x` | ❌ Wave 0 |
| TRADE-05 | sizing_engine.get_trailing_stop falls back to computed when manual_stop=None | unit | `pytest tests/test_sizing_engine.py::TestManualStopOverride::test_none_manual_stop_falls_back_to_computed -x` | ❌ Wave 0 |
| TRADE-06 | web/routes/trades.py does NOT mutate state['warnings'] | unit | `pytest tests/test_web_trades.py::TestSoleWriterInvariant::test_no_warnings_subscript_assignment -x` | ❌ Wave 0 |
| TRADE-06 | All mutation handlers call save_state exactly once | integration | `pytest tests/test_web_trades.py::TestSaveStateInvariant::test_open_calls_save_state_once -x` | ❌ Wave 0 |
| TRADE-06 | fcntl lock contention test: writer blocks until holder releases | integration | `pytest tests/test_state_manager.py::TestFcntlLock::test_save_state_blocks_under_contention -x` | ❌ Wave 0 |
| TRADE-06 | fcntl lock released on normal save | unit | `pytest tests/test_state_manager.py::TestFcntlLock::test_save_state_releases_lock -x` | ❌ Wave 0 |
| TRADE-06 | fcntl lock released on exception during write | unit | `pytest tests/test_state_manager.py::TestFcntlLock::test_save_state_releases_lock_on_exception -x` | ❌ Wave 0 |
| TRADE-06 | Schema migration v2→v3 backfills manual_stop=None on existing positions | unit | `pytest tests/test_state_manager.py::TestMigrationV2ToV3::test_backfills_manual_stop_none -x` | ❌ Wave 0 |
| TRADE-06 | Schema migration is idempotent | unit | `pytest tests/test_state_manager.py::TestMigrationV2ToV3::test_idempotent -x` | ❌ Wave 0 |
| TRADE-06 | Schema migration preserves all v2 fields verbatim | unit | `pytest tests/test_state_manager.py::TestMigrationV2ToV3::test_preserves_v2_fields -x` | ❌ Wave 0 |
| TRADE-06 | None positions stay None after migration | unit | `pytest tests/test_state_manager.py::TestMigrationV2ToV3::test_none_position_unchanged -x` | ❌ Wave 0 |
| (hex) | sizing_engine is allowed for web/ adapter (Phase 14 D-02 promotion) | unit | `pytest tests/test_web_healthz.py::TestWebHexBoundary::test_sizing_engine_is_allowed_for_web_phase_14 -x` | ❌ Wave 0 (extension) |
| (hex) | system_params is allowed for web/ adapter | unit | `pytest tests/test_web_healthz.py::TestWebHexBoundary::test_system_params_is_allowed_for_web -x` | ❌ Wave 0 (extension; mostly already true) |
| (rt) | full integration: TestClient → POST /trades/open → state.json mutated → dashboard re-renders | integration | `pytest tests/test_web_trades.py::TestEndToEnd::test_open_to_dashboard_round_trip -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest tests/test_web_trades.py tests/test_state_manager.py tests/test_sizing_engine.py tests/test_web_dashboard.py -x` (touched files)
- **Per wave merge:** `pytest -x` (full suite — currently 662 tests + ~45 new = ~707)
- **Phase gate:** Full suite green before `/gsd-verify-work`; ruff clean; AST hex-boundary tests all green; cross-platform fcntl behavior verified on Linux droplet (operator manual UAT step in SETUP-DROPLET.md addendum if needed)

### Wave 0 Gaps

- [ ] `tests/test_web_trades.py` — covers TRADE-01..06 (NEW)
- [ ] `tests/test_state_manager.py::TestFcntlLock` — covers D-13 lock behavior (EXTENSION)
- [ ] `tests/test_state_manager.py::TestMigrationV2ToV3` — covers D-09 migration (EXTENSION)
- [ ] `tests/test_sizing_engine.py::TestManualStopOverride` — covers D-09 precedence (EXTENSION)
- [ ] `tests/test_web_dashboard.py::TestHTMXVendor`, `TestHTMXMarkup`, `TestManualStopBadge`, `TestManualStopMath` — covers TRADE-05 (EXTENSION)
- [ ] `tests/test_web_healthz.py::TestWebHexBoundary::test_sizing_engine_is_allowed_for_web_phase_14` — D-02 hex-boundary promotion regression (EXTENSION)
- [ ] `tests/fixtures/state_v2.json` — sample v2 state file for migration round-trip test (NEW)
- [ ] (Optional) `tests/conftest.py` — autouse `WEB_AUTH_SECRET` fixture is ALREADY in place from Phase 13; Phase 14 reuses unchanged

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Phase 13 `AuthMiddleware` (X-Trading-Signals-Auth shared-secret); Phase 14 inherits via D-01 / Phase 13 D-01 single chokepoint |
| V3 Session Management | no | No sessions — single-operator shared-secret auth (Phase 13 deferred ideas explicitly forbids cookies/OAuth) |
| V4 Access Control | yes | Single-tenant; auth gate is the only access control |
| V5 Input Validation | yes | Pydantic v2 `Field(gt=0, ge=1)`, `Literal` enums, `model_validator` for cross-field; `math.isfinite` for NaN/inf rejection; 422→400 remap |
| V6 Cryptography | no | No crypto in Phase 14 (TLS termination at nginx — Phase 12; HMAC compare in Phase 13 AuthMiddleware) |
| V7 Error Handling | yes | 401 plain-text `unauthorized` (Phase 13 AUTH-02); 400 JSON `{errors: [...]}` (Phase 14 D-04); 409 plain-text conflict bodies (Phase 14 D-01); never leaks stack traces |
| V12 Files | yes | `state.json` writes are atomic (existing `_atomic_write`); fcntl exclusive lock prevents cross-process torn writes (Phase 14 D-13) |
| V13 API & Web Service | yes | RESTful POST endpoints; CSRF substitute = shared-secret header (third-party origins can't supply); `Cache-Control: no-store` already set on /api/state (Phase 13 D-13) — Phase 14 partials similarly should set `Cache-Control: no-store` |
| V14 Configuration | yes | All Phase 14 secrets via env vars (`WEB_AUTH_SECRET` from Phase 13; no new vars in Phase 14); SRI on HTMX vendor script |

### Known Threat Patterns for FastAPI + Pydantic + state.json

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Injection via JSON body field | Tampering | Pydantic v2 `Literal[...]` and `Field(gt=0)` reject malformed types/values BEFORE handler runs; `math.isfinite` blocks NaN/inf |
| XSS via reflected error message in HTMX partial | Tampering / Information Disclosure | Pydantic error messages are server-controlled (no user-supplied text in `reason`); UI-SPEC §Decision 4 inline JS uses `innerHTML` with server-controlled content; CLAUDE.md §Frontend rule says "switch to textContent if any future REQ allows operator-supplied free-text" — captured as Phase 14 deferred risk |
| CSRF | Spoofing | Shared-secret `X-Trading-Signals-Auth` header — third-party origins can't supply (browser CORS+Cookie semantics make this implausible). Documented as v1.1 hard constraint per PROJECT.md |
| Race condition between web POST and signal-loop save | Tampering | `fcntl.LOCK_EX` advisory lock around `_atomic_write` (D-13). Plus uvicorn `workers=1` serializes intra-process |
| Lost update (load + mutate + save races between web POSTs) | Tampering | Phase 14 v1 accepts (per Open Question 2); workers=1 means same-process POSTs queue. Cross-process race with daily save bounded by ~50ms window. v1.2 candidate to extend lock across read-modify-write |
| Stack trace leak on 5xx | Information Disclosure | FastAPI default 500 returns generic error; AuthMiddleware never logs auth failures with stack |
| State file corruption from crash mid-write | Tampering | Existing tempfile + fsync + os.replace + dir-fsync (D-08 + D-17) — atomic rename means torn writes are impossible. Phase 14 doesn't change this |
| Open file descriptor leak from failed locks | DoS | `with` statement / try/finally on `os.close(lock_fd)` — Pattern 9 |
| Missing `WEB_AUTH_SECRET` at boot | DoS / Spoofing | Phase 13 D-16 fail-closed; uvicorn doesn't bind port; systemd Restart=on-failure surfaces in journald |
| HTMX library tampering (CDN compromise) | Tampering | SRI hash `sha384-ujb1lZYygJmzgSwoxRggbCHcjc0rB2XoQrxeTUQyRjrOnlCoYta87iKBWq3EsdM2` on every load; browser refuses to execute on hash mismatch |
| `state['warnings']` corruption from Phase 14 handler | Tampering | TRADE-06 / Pattern 10 AST guard test asserts no `state['warnings']` writes from `web/routes/trades.py` |

## Sources

### Primary (HIGH confidence)
- **HTMX 1.9.12 SRI hash** — verified in this session via `curl https://unpkg.com/htmx.org@1.9.12/dist/htmx.min.js | openssl dgst -sha384 -binary | openssl base64 -A` → `ujb1lZYygJmzgSwoxRggbCHcjc0rB2XoQrxeTUQyRjrOnlCoYta87iKBWq3EsdM2` (file: 48,101 bytes; jsdelivr identical). HTMX 1.9.12 published 2024-04-25 [VERIFIED: api.github.com/repos/bigskysoftware/htmx/releases/tags/v1.9.12]
- **FastAPI 0.136.1 dependency declaration** — `pydantic>=2.9.0`, `starlette>=0.46.0` [VERIFIED: pypi.org/pypi/fastapi/0.136.1/json]
- **HTMX npm registry version list** — 1.9.12 is final 1.9.x; 2.0.10 is current [VERIFIED: registry.npmjs.org/htmx.org]
- **Project source files** — read in this session: `web/app.py`, `web/middleware/auth.py`, `web/routes/{healthz,state,dashboard}.py`, `state_manager.py`, `system_params.py`, `sizing_engine.py`, `dashboard.py`, `tests/test_web_healthz.py`, `tests/test_signal_engine.py`, `requirements.txt`, `.planning/config.json`, `.planning/STATE.md`
- **CONTEXT.md and UI-SPEC.md** — read in full; D-01..D-14 + UI-SPEC §Decision 1..7 are user-locked

### Secondary (MEDIUM confidence — official docs verified by web fetch)
- [FastAPI custom response (HTMLResponse vs Response)](https://fastapi.tiangolo.com/advanced/custom-response/) — HTMLResponse recommended idiom
- [FastAPI handling errors](https://fastapi.tiangolo.com/tutorial/handling-errors/) — `app.add_exception_handler(RequestValidationError, ...)` pattern
- [Pydantic v2 fields concept](https://pydantic.dev/docs/validation/latest/concepts/fields/) — `Field(gt=0)`, `Literal[...]`, `model_validator(mode='after')`
- [Pydantic v2.12 release announcement](https://pydantic.dev/articles/pydantic-v2-12-release) — experimental MISSING sentinel (NOT relied on)
- [Roman Imankulov: Handling Unset Values in FastAPI with Pydantic](https://roman.pt/posts/handling-unset-values-in-fastapi-with-pydantic/) — `model_fields_set` PATCH pattern
- [pythontutorials.net: Pydantic detect missing vs null](https://www.pythontutorials.net/blog/pydantic-detect-if-a-field-value-is-missing-or-given-as-null/) — `model_fields_set` and sentinel alternative
- [docs.python.org fcntl docs](https://docs.python.org/3/library/fcntl.html) — `flock()` lock-release-on-fd-close semantics
- [man7.org flock(2) Linux manual](https://man7.org/linux/man-pages/man2/flock.2.html) — flock advisory lock semantics
- [HTMX hx-swap-oob attribute](https://htmx.org/attributes/hx-swap-oob/) — out-of-band swap for confirmation banners

### Tertiary (LOW confidence — single source, marked for validation)
- [chris.improbable.org: Everything you never wanted to know about file locking](https://chris.improbable.org/2010/12/16/everything-you-never-wanted-to-know-about-file-locking/) — fcntl POSIX byte-range lock gotchas (informs Pattern 9 choice of flock over lockf)
- 2-stage destructive close confirmation pattern — composed from HTMX primitives in this session; NO canonical "best practice" surfaced in search. UI-SPEC §Decision 5 already locks the markup contract.

## Metadata

**Confidence breakdown:**
- Standard stack: **HIGH** — every dep version verified against pypi/registry; SRI hash computed in-session; project source confirms existing pins
- Architecture (hex-boundary, route module shape, AST guards): **HIGH** — Phase 13 precedent is concrete and reusable
- Pydantic v2 PATCH semantics (`model_fields_set`): **HIGH** — multiple authoritative sources agree; existing project pin floor (>=2.9.0) supports it
- 422→400 remap: **HIGH** — official FastAPI docs cover the exact pattern
- HTMX response shapes: **HIGH** — UI-SPEC already locked the contract; HTMX docs confirm the primitives
- 2-stage destructive close UX: **MEDIUM** — composed from primitives; no canonical reference; UI-SPEC contract is internally consistent
- fcntl lock around os.replace: **MEDIUM** — argument in §Pitfall 3 is sound but not externally validated; multiprocess test fixture is the proof
- Schema migration v2→v3: **HIGH** — existing migration framework (`MIGRATIONS` dict, `_migrate` walk-forward) is well-understood and tested

**Research date:** 2026-04-25
**Valid until:** 2026-05-25 (30 days for stable web stack; SRI hash for HTMX 1.9.12 will not change — file is immutable in npm cache)

## RESEARCH COMPLETE

**Phase:** 14 - Trade Journal — Mutation Endpoints
**Confidence:** HIGH (stack + architecture); MEDIUM (composed UX patterns)

### Key Findings

- **Schema version is currently 2, not 3** — Phase 14 migration is **v2→v3** (orchestrator brief assumed v3→v4). `STATE_SCHEMA_VERSION` bumps from `2` to `3` in `system_params.py`. Migration backfills `manual_stop=None` on every existing Position dict.
- **HTMX 1.9.12 SRI hash verified in-session:** `sha384-ujb1lZYygJmzgSwoxRggbCHcjc0rB2XoQrxeTUQyRjrOnlCoYta87iKBWq3EsdM2`. unpkg and jsdelivr both serve byte-identical 48,101-byte file. Either CDN URL is acceptable; pattern mirrors Chart.js 4.4.6 precedent at dashboard.py:115-116.
- **Pydantic v2 `model_fields_set` is the recommended absent-vs-null mechanism for D-12.** FastAPI 0.136.1 declares `pydantic>=2.9.0`; `model_fields_set` is stable public API since 2.0.0. Pydantic 2.12's experimental MISSING sentinel is NOT in the project's pinned floor and should NOT be relied on.
- **`fcntl.flock` on the destination state.json file is correct under `os.replace` semantics** — the inode-orphan-on-rename behavior preserves serialization (Pattern 9 + Pitfall 3 argument). Multi-process test is the proof obligation. Cross-platform: Linux + macOS supported; NFS NOT supported (project doesn't use NFS).
- **422→400 remap via `app.add_exception_handler(RequestValidationError, ...)`** is the FastAPI-canonical pattern; one global handler covers all `/trades/*` routes — no per-route boilerplate.
- **Hex-boundary AST guard extension** — Phase 14 ADDS `sizing_engine` to allowed adapter imports for `web/` (mirrors Phase 13 D-07's `dashboard` promotion). One-line update to `tests/test_web_healthz.py::TestWebHexBoundary.FORBIDDEN_FOR_WEB`.

### File Created

`.planning/phases/14-trade-journal-mutation-endpoints/14-RESEARCH.md`

### Confidence Assessment

| Area | Level | Reason |
|------|-------|--------|
| Standard Stack | HIGH | Versions verified against pypi/npm in-session; SRI hash computed; `requirements.txt` already complete |
| Architecture | HIGH | Phase 13 patterns concrete and directly reusable; UI-SPEC already locks contracts |
| Pitfalls | HIGH (D-05 anti-pitfall + Pydantic absent-vs-null) / MEDIUM (fcntl + os.replace) | Anti-pitfall and Pydantic patterns are deeply documented; fcntl behavior is sound but the multi-process test is the proof |
| Validation Architecture | HIGH | 6 test classes; ~45 new test methods; all REQs map cleanly to specific test names |
| Security | HIGH | All ASVS categories applicable identified; STRIDE patterns documented; mitigations align with Phase 13 precedent |

### Open Questions

1. Should `sizing_engine.check_pyramid` import in `web/routes/trades.py` be module-top OR local? Recommendation: LOCAL for consistency with Phase 11 C-2.
2. Should `_atomic_write` lock be held across `load_state → mutate → save_state` (full critical section) OR per-call? Phase 14 v1 accepts per-call (D-13); lost-update is bounded by `workers=1` + narrow daily-save window.
3. HTMX 2.x migration timing — UI-SPEC pins 1.9.12; revisit in Phase 16 or v1.2.

### Ready for Planning

Research complete. Planner can now create PLAN.md files. The CONTEXT.md `<canonical_refs>` block and the source-file inventory in §Architecture Patterns map directly to the executor's file-touch list.
