---
phase: 29
plan: 12
plan_id: 29-12-UAT-17-2-IOS-SAFARI-DETAILS-OPEN
status: complete
created: 2026-05-10
---

# Phase 29 Plan 12: iOS Safari <details open> Server-Side Fix

## One-liner

Fixed two Phase-17 static allowlists that silently dropped tsi_trace_open cookie values for all dynamically-added markets, preventing server-side `<details open>` from firing on iOS Safari reload.

## Root cause

Two hardcoded static structures from Phase 17 froze the trace-panel open-state to only SPI200 and AUDUSD:

1. `_resolve_trace_open` in `web/routes/dashboard.py` filtered cookie values against `frozenset{'SPI200', 'AUDUSD'}`. Any market added via the Phase 25+ multi-market API was silently discarded — cookie value present, but `_resolve_trace_open` returned empty frozenset, so `_trace_open_repl` always emitted `b''`.

2. `_TRACE_OPEN_PLACEHOLDER` in `dashboard_legacy/render_helpers.py` was a static 2-entry dict. `.get(state_key, '')` returned `''` for any market not in `{'SPI200', 'AUDUSD'}` — meaning no placeholder was emitted into the rendered HTML, so `_substitute()` had nothing to find and replace, and the `<details>` element always rendered closed for those markets.

For SPI200 and AUDUSD specifically, the server-side path was technically correct, but the iOS Safari failure was also compounded by:

3. Cookie `Max-Age=7776000` (90 days) — per T-29-12-02, extended to `31536000` (1 year) to survive iOS Safari tab-discard-reload cycles.

## What was fixed

| File | Change |
|------|--------|
| `web/routes/dashboard.py` | `_resolve_trace_open` now validates cookie keys via `_MARKET_ID_RE.fullmatch` (format allowlist using the canonical `^[A-Z0-9_]{2,20}$` pattern) instead of a static frozenset. Security preserved: `_trace_open_repl` can only emit `b' open'` or `b''`. |
| `dashboard_legacy/render_helpers.py` | `_TRACE_OPEN_PLACEHOLDER` replaced with `_TraceOpenPlaceholderMap` — a `.get(key, default)`-compatible shim that generates `{{TRACE_OPEN_<KEY>}}` for any market ID matching the regex, instead of returning `''` for unknown markets. |
| `dashboard_renderer/assets.py` | Cookie `Max-Age` bumped from `7776000` to `31536000` (90 days → 1 year) per T-29-12-02. |
| `tests/test_dashboard.py` | Updated `test_dashboard_emits_trace_toggle_js_with_domcontentloaded` assertion from `Max-Age=7776000` to `Max-Age=31536000`. |
| `tests/fixtures/dashboard/golden.html` | Regenerated (Max-Age change). |
| `tests/fixtures/dashboard/golden_empty.html` | Regenerated (Max-Age change). |
| `tests/fixtures/dashboard_canonical.html` | Regenerated (Max-Age change). |

## Tests added

`tests/test_trace_details_open_serverside.py` — 7 tests in 2 classes:

**TestTraceDetailsOpenServerSide** (root `GET /` path, synthetic HTML):
- `test_details_open_when_cookie_includes_instrument` — cookie SPI200 → `<details open>` for SPI200, not AUDUSD; no placeholder leak.
- `test_details_closed_when_cookie_excludes_instrument` — empty cookie → both panels closed; no placeholder leak.
- `test_no_cookie_renders_closed` — no cookie → all panels closed.
- `test_unknown_instrument_in_cookie_ignored` — cookie EVIL_INJECT → no crash, no open attribute, no injection leak.

**TestTraceDetailsOpenMarketScoped** (market-scoped `GET /markets/SPI200/signals` path, full render):
- `test_details_open_when_cookie_includes_instrument` — the exact iOS Safari reload path: full render + substitute.
- `test_details_closed_without_cookie` — no cookie → panel closed.
- `test_dynamic_market_gets_placeholder_in_html` — ESM market (dynamic, not in legacy dict) gets placeholder emitted and substituted correctly (validates the `_TraceOpenPlaceholderMap` fix).

## Self-check

- [x] Root cause identified and documented
- [x] Source files modified with clear behavioural changes (3 files)
- [x] `grep -q "tsi_trace_open" web/routes/dashboard.py` succeeds
- [x] `test -f tests/test_trace_details_open_serverside.py` succeeds
- [x] `grep -q "test_details_open_when_cookie_includes_instrument" tests/test_trace_details_open_serverside.py` succeeds
- [x] `grep -q "tsi_trace_open" tests/test_trace_details_open_serverside.py` succeeds
- [x] `pytest tests/test_trace_details_open_serverside.py -x -q` rc=0 (7 passed)
- [x] `.venv/bin/pytest -q` rc=0 (2059 passed, 0 failed)
- [x] File LOC ≤ 500: test file is 371 lines
- [x] LEARNINGS.md entry appended
- [x] Commit message documents actual root cause
