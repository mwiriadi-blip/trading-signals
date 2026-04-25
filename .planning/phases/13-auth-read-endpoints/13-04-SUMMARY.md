---
phase: 13
plan: 04
subsystem: web/state-endpoint
tags: [api, json, state, cache-control, wave-2]
requires:
  - "Plan 13-02 web/routes/state.py stub (returning 503)"
  - "Plan 13-02 AuthMiddleware wired in create_app() so 401 inheritance works"
  - "Plan 13-01 autouse WEB_AUTH_SECRET fixture (tests/conftest.py)"
provides:
  - "GET /api/state real handler — D-12 strip + D-13 no-store + D-14 trust-load + D-15 compact JSON"
  - "8 contract tests in TestStateResponse covering WEB-06 + D-12..D-15 + AUTH-01 inheritance"
  - "SC-3 verbatim key-set lock test (REVIEWS MEDIUM #2): test_full_top_level_key_set_preserved_except_runtime_keys"
affects:
  - web/routes/state.py
  - tests/test_web_state.py
tech-stack:
  added: []
  patterns:
    - "Top-level dict comprehension `{k: v for k, v in state.items() if not k.startswith('_')}` for runtime-key strip at network boundary"
    - "JSONResponse with explicit `Cache-Control: no-store` headers kwarg"
    - "Trust-load posture (no try/except wrapper) — diverges deliberately from healthz D-19 because /api/state can let exceptions propagate to middleware 500"
    - "Local `from state_manager import load_state` inside handler body — preserves Phase 11 C-2 hex boundary"
    - "Set-equality assertion (`set(r.json().keys()) == {…}`) for verbatim contract locking — REVIEWS MEDIUM #2 pattern"
key-files:
  created: []
  modified:
    - web/routes/state.py
    - tests/test_web_state.py
decisions:
  - "Plan-as-written `from conftest import VALID_SECRET, AUTH_HEADER_NAME` fails because pytest's testpaths=['tests'] does not put tests/ on sys.path; inlined the constants in tests/test_web_state.py with comments referencing tests/conftest.py as the conceptual single-source. Mirrors the Plan 13-02 Rule 1 deviation pattern. The autouse WEB_AUTH_SECRET fixture from conftest.py still runs (auto-discovered)."
  - "/api/state has NO try/except around load_state() per D-14 — diverges from /healthz which DOES wrap. Different posture: /healthz must always return 200 (D-19); /api/state can let an exception propagate to the middleware which returns 500. If load_state ever raises, that's a real bug to surface, not to mask."
  - "REVIEWS MEDIUM #2 fix landed: test_full_top_level_key_set_preserved_except_runtime_keys asserts `set(keys) == {schema_version, account, last_run, positions, signals, trade_log, equity_history, warnings, contracts}` verbatim. A regression dropping warnings/contracts/equity_history fires immediately."
  - "Acceptance-criteria grep counts of `Cache-Control no-store: 2` and `indent appearances: 2` (vs plan's expected 1/0) are documentation-quality bonus — both extra hits are inside the module docstring and code comments explaining the negative constraint, not actual functional code. Plan body already includes those docstring references verbatim."
metrics:
  duration: "~10m"
  tasks: 2
  files_created: 0
  files_modified: 2
  tests_added: 8
  completed: 2026-04-25
---

# Phase 13 Plan 04: GET /api/state Implementation + Tests Summary

Wave 2 read-endpoint backbone — replaces the Plan 13-02 503 stub with the full `GET /api/state` handler and locks WEB-06 + D-12..D-15 + SC-3 verbatim with 8 passing tests.

## What Was Done

### Task 1 — `web/routes/state.py` rewrite (commit c1eef71)

Replaced the 28-line Plan 13-02 stub with the real ~45-line handler:

- **D-12 strip** — `clean = {k: v for k, v in state.items() if not k.startswith('_')}` filters TOP LEVEL only. Nested dicts (e.g. `positions['SPI200']`) keep their `_*` keys intact in case v1.2 introduces a legitimate nested marker.
- **D-13 headers** — `JSONResponse(content=clean, headers={'Cache-Control': 'no-store'})`. Content-Type `application/json` comes from FastAPI default. The `no-store` directive is necessary because state becomes mutation-capable in Phase 14; stale browser/proxy cache would mislead.
- **D-14 trust-load** — NO try/except around `load_state()`. This is a deliberate divergence from `/healthz` (which DOES wrap and degrades to a default body on exception): healthz must always return 200 per D-19; `/api/state` lets an exception propagate to the middleware 500 because that's a real bug to surface.
- **D-15 compact JSON** — FastAPI's JSONResponse default is compact (no indent). No `indent=` kwarg passed. Humans use `curl | jq` for pretty-printing; wire bytes stay minimal as state.json grows over months.
- **Hex boundary** — `from state_manager import load_state` is INSIDE the handler function (Phase 11 C-2 local-import rule). Module-top imports are limited to `logging`, `fastapi.FastAPI`, `fastapi.responses.JSONResponse`. AST guard `tests/test_web_healthz.py::TestWebHexBoundary` stays green.

### Task 2 — `tests/test_web_state.py` populated (commit b477242)

Replaced the empty Wave 0 `class TestStateResponse: pass` skeleton with the full 8-method test class plus a `client_with_state` fixture:

**Fixture pattern** — `client_with_state(monkeypatch)` returns `(client, set_state_fn)`. Each test calls `set_state(payload)` to control what the handler's local `load_state` import returns. The autouse `WEB_AUTH_SECRET` fixture from `tests/conftest.py` runs first (file matches `test_web_*.py`), so `create_app()` never trips the D-16 fail-closed path.

**8 tests, all passing:**

| # | Method | Asserts |
|---|--------|---------|
| 1 | `test_returns_200_with_auth` | WEB-06 happy path with valid auth → 200 |
| 2 | `test_content_type_is_json` | D-13 Content-Type starts with `application/json` |
| 3 | `test_strips_underscore_prefixed_top_level_keys` | D-12: `_resolved_contracts`, `_LAST_LOADED_STATE_HINT` absent; non-underscore keys present |
| 4 | `test_full_top_level_key_set_preserved_except_runtime_keys` | **REVIEWS MEDIUM #2 SC-3 lock** — `set(r.json().keys()) == {schema_version, account, last_run, positions, signals, trade_log, equity_history, warnings, contracts}` verbatim |
| 5 | `test_preserves_nested_underscore_keys` | D-12 top-level only — nested `_internal_marker` survives |
| 6 | `test_cache_control_no_store` | D-13 explicit `Cache-Control: no-store` header |
| 7 | `test_response_is_compact_json` | D-15 compact — no `\n  ` indent, no newlines |
| 8 | `test_unauthenticated_returns_401_not_state` | AUTH-01 inheritance — middleware blocks `/api/state`; body does not leak `schema_version` |

All 8 PASS via `pytest tests/test_web_state.py -x -v`. Phase 11 + 13 web suite green: `pytest tests/test_web_*.py -x -q` → 65 passed.

## Why This Matters

`GET /api/state` is the single read-only JSON snapshot for mobile, CLI, and external scripts. The D-12 underscore strip enforces the v1.0 Phase 8 D-14 convention (`_*` keys are runtime-only) at the network boundary, so external consumers never see internal cache values like `_resolved_contracts`. The D-13 `Cache-Control: no-store` is the browser/proxy guardrail that makes Phase 14's mutation endpoints safe — without it, a back-navigate after `POST /trades/open` would show stale state.

The new SC-3 verbatim key-set test (REVIEWS MEDIUM #2) closes a gap Codex flagged: the original 7-test baseline would have passed even if a regression silently dropped `warnings`, `contracts`, or `equity_history` from the response. Now any future change that narrows the top-level key set fires red in CI immediately.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Inline VALID_SECRET / AUTH_HEADER_NAME instead of `from conftest import …`**

- **Found during:** Task 2 first run (collection error)
- **Issue:** Plan body's `from conftest import AUTH_HEADER_NAME, VALID_SECRET` raised `ModuleNotFoundError: No module named 'conftest'`. Pytest's `testpaths=['tests']` does NOT add `tests/` to `sys.path` despite `tests/__init__.py` existing — `conftest.py`'s autouse fixtures are auto-discovered, but its module-level constants are not auto-importable.
- **Fix:** Inlined the two constants at the top of `tests/test_web_state.py` with a comment referencing `tests/conftest.py` as the conceptual single-source. Matches Plan 13-02's Rule 1 deviation pattern (also inlined in `tests/test_web_app_factory.py`). The autouse `_set_web_auth_secret_for_web_tests` fixture from `tests/conftest.py` still runs because pytest's conftest discovery is independent of import path.
- **Files modified:** `tests/test_web_state.py`
- **Commit:** b477242 (Task 2)

### Acceptance-criteria nits (no fix needed — documentation-quality bonus)

- `grep -c "Cache-Control.*no-store" web/routes/state.py` → 2 (plan expected 1). Reason: docstring also describes the contract. The functional `headers={'Cache-Control': 'no-store'}` line is unique.
- `grep -c "indent" web/routes/state.py` → 2 (plan expected 0). Reason: docstring + code comment both reference "no indent=2" / "no indent" as the negative constraint. No actual `indent=` kwarg is passed to JSONResponse.

Both extra hits are inside the verbatim plan-body docstring/comments. Substantive contract is satisfied.

## Deferred Issues

**`tests/test_main.py::TestCLI::test_force_email_sends_live_email` and 14 sibling test_main tests fail** — pre-existing, date-dependent. Today (2026-04-25) is a Saturday and `--force-email` hits `main.py:1043` weekend-skip branch, so `send_daily_email` is never called. Confirmed pre-existing on plan base c7f5c76 by stashing Task 1+2 changes and re-running the test — same failure. Out of scope for Phase 13 (web/routes only). Logged to `.planning/phases/13-auth-read-endpoints/deferred-items.md`.

## Verification Results

| Check | Command | Result |
|-------|---------|--------|
| Task 1 acceptance | `python -c "from pathlib import Path; ...assert all required tokens"` | PASS |
| Task 2 — 8 tests | `pytest tests/test_web_state.py -x -v` | 8 passed |
| SC-3 lock test | `pytest tests/test_web_state.py::TestStateResponse::test_full_top_level_key_set_preserved_except_runtime_keys -x -q` | 1 passed |
| Hex-boundary AST | `pytest tests/test_web_healthz.py::TestWebHexBoundary -x -q` | 3 passed |
| Phase 11 + 13 web suite | `pytest tests/test_web_*.py -x -q` | 65 passed |
| Pure-math hex (TestDeterminism) | `pytest tests/test_signal_engine.py::TestDeterminism -x -q` | 44 passed |
| `state_manager` not at module top | AST scan of `web/routes/state.py` | OK (local-only) |
| Module imports cleanly | `python -c "from web.routes.state import register; print('OK')"` | OK |

## Self-Check: PASSED

- File `web/routes/state.py` exists and contains `def get_state` + `k.startswith('_')` + `Cache-Control` + `no-store` + `JSONResponse(`.
- File `tests/test_web_state.py` exists and contains all 8 method names including `test_full_top_level_key_set_preserved_except_runtime_keys`.
- Commit c1eef71 (Task 1 — feat) found in `git log`.
- Commit b477242 (Task 2 — test) found in `git log`.
