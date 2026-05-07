---
status: partial
phase: 26-phase-25-followup-multi-tab-scoping-fixes
source:
  - 26-01-SUMMARY.md
  - 26-02-SUMMARY.md
  - 26-03-SUMMARY.md
  - 26-04-SUMMARY.md
  - 26-05-SUMMARY.md
  - 26-06-SUMMARY.md
  - 26-07-SUMMARY.md
  - 26-08-SUMMARY.md
started: 2026-05-07
updated: 2026-05-07
---

## Current Test

[testing complete — operator skipped browser-based UAT; coverage carried by xfail tests + audit greps]

## Tests

### 1. Cold Start Smoke Test
expected: |
  Kill running trading-signals-web service. Clear dashboard*.html.
  Start fresh. Server boots; GET / returns 503 (no state) or 200 (state present).
  No tracebacks.
result: skipped
blocked_by: physical-server
reason: Operator deferred to deploy-time smoke. Auto-coverage via 1794-passing pytest suite.

### 2. Multi-tab market scoping — /markets/{M}/signals
expected: |
  Each /markets/{M}/signals renders only that market's signal-card eyebrow.
result: skipped
blocked_by: physical-server
reason: |
  Auto-coverage via TestPhase26MarketScoping in tests/test_web_app_factory.py.
  4/4 xfail tests flipped green in Plan 26-05 (signals + settings + market-test
  + multi-eyebrow-absence per active market).

### 3. Multi-tab market scoping — /markets/{M}/settings
expected: |
  /markets/SPI200/settings shows only SPI 200 fieldset; same per market.
result: skipped
blocked_by: physical-server
reason: Auto-coverage via TestPhase26MarketScoping (same suite as Test 2).

### 4. Multi-tab market scoping — /markets/{M}/market-test
expected: |
  /markets/{M}/market-test shows only that market's override form.
result: skipped
blocked_by: physical-server
reason: Auto-coverage via TestPhase26MarketScoping (same suite as Test 2).

### 5. PATCH from panel-swapped form succeeds (no 401)
expected: |
  PATCH from a market-scoped panel-swap form returns 200 (or 4xx-validation),
  never 401-from-{{WEB_AUTH_SECRET}} placeholder.
result: skipped
blocked_by: physical-server
reason: |
  Auto-coverage via TestPhase26PanelPatchSurvives in tests/test_web_dashboard.py
  (xfail flipped green in Plan 26-04). Plus TestAuthSecretPlaceholderSubstitution
  remains green (no regression on canonical path).

### 6. Header session widget renders correctly
expected: |
  Header shows signout button OR session note, never literal placeholders.
result: skipped
blocked_by: physical-server
reason: |
  Auto-coverage via TestPhase26HeaderSessionWidget + TestPhase26PlaceholderLeak
  (3 xfail flipped green in Plan 26-04). _substitute helper resolves all 5
  placeholder kinds for both _serve_dashboard_content and _serve_market_scoped_page.

### 7. Markets-strip works without Referer
expected: |
  Markets tab strip refresh on markets-changed uses ?active_function=
  query param, not Referer.
result: skipped
blocked_by: physical-server
reason: |
  Code-level audit confirms: nav.py:103-110 emits hx-get with
  ?active_function={fn_q}; markets-strip handler reads
  request.query_params.get('active_function', 'signals') with allowlist
  {signals, account, settings, market-test}. Referer-derived fallback
  removed (web/routes/dashboard.py). Full suite green post-change.

### 8. New market shows "Signal as of: never"
expected: |
  POST /markets adds market; render shows "Signal as of: never" via dict-shape branch.
result: skipped
blocked_by: physical-server
reason: |
  Code-level: add_market now writes 7-key dict matching main.run_daily_check
  (web/routes/markets.py:158). Renderer's defensive isinstance(int) branch
  retained for legacy test fixtures (see 26-DEBT.md). 1794-passing suite
  includes TestPhase25AddMarketHXTrigger.

### 9. pytest full suite green
expected: |
  `.venv/bin/pytest -q` exits 0 with 1794 passed.
result: pass
auto: true
note: Verified at end of Plan 08 — 1794 passed in 110.25s.

### 10. Audit greps clean
expected: |
  - `grep '{{[A-Z_]\+}}'` in served HTML paths → only docstring/comment refs.
  - `_render_market_selector|_render_dashboard_page_nav` (excl test_/26-/25-) → 0.
  - `signals\[.*\] = 0\b` (excl test_) → 0.
  - `git check-ignore -v` → Phase 26 patterns active.
result: pass
auto: true
note: All four audit greps confirmed clean during Plan 07 + Plan 08.

## Summary

total: 10
passed: 2
issues: 0
pending: 0
skipped: 8

## Gaps

[none — all skipped tests have automated coverage via pytest xfail-flipped-green tests + audit greps; deferred to operator deploy-time smoke]
