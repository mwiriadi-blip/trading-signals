---
phase: 25
plan: 25-11
title: Gap closure — D-14 placeholders + 3 D-11 test repairs
type: execution
autonomous: true
gap_closure: true
wave: 5
depends_on:
  - 25-08-settings-fieldsets
  - 25-07-empty-state-collapse
files_modified:
  - dashboard_renderer/components/settings.py
  - dashboard_renderer/api.py
  - tests/test_dashboard.py
  - tests/golden_empty.html
---

<objective>
Close the 4 gaps surfaced by 25-VERIFICATION.md so Phase 25 reaches PASS:

1. **D-14** — wire per-market Settings into `render_market_test_tab()` so override fields emit `placeholder="<inherited default>"` (currently absent — Plan 25-08 SUMMARY claimed shipped but code shows static inputs).
2. **D-11 fix #1 (security regression)** — `test_chart_payload_escapes_script_close` is non-functional because Plan 25-07 hides the equity chart until ≥5 distinct (date, equity) points; the XSS defense branch never fires. Test must seed ≥5 distinct equity points so the chart renders and `replace('</', '<\\/')` is exercised.
3. **D-11 fix #2 (copy drift)** — `test_equity_chart_empty_state_placeholder` asserts pre-D-11 copy "No equity history yet — first full run needed" but D-11 changed it to "Chart appears once 5 daily equity points have been recorded." Update the assertion to the post-D-11 string.
4. **D-11 fix #3 (golden snapshot)** — `tests/golden_empty.html` (48,413 bytes) lags the live render (49,057 bytes) after Phase 25 changes. Regenerate via the project's existing snapshot-update mechanism.
</objective>

<context>
- 25-VERIFICATION.md (`gaps_found`, score 19/22) — D-14 MISSING + 3 test failures
- D-14 spec (CONTEXT.md): "Market Test override fields render inherited defaults as placeholder, so blanks fall back to the defaulted value on submit"
- D-11 spec (CONTEXT.md): equity chart hidden until ≥5 distinct (date, equity) tuples in `state['equity_history']`
- Plan 25-07 SUMMARY documents the `_distinct_equity_tuples` helper added to dashboard.py
</context>

<tasks>

### Task 1 — Wire D-14 Market Test placeholders + regression test
type: implementation

**Implementation:**
1. Update `dashboard_renderer/components/settings.py::render_market_test_tab()` (or its caller in `api.py`) to accept the per-market `Settings` object.
2. For each override field (ADX gate, momentum votes, long/short risk %, long/short ATR multiple, contract cap), emit `placeholder="<inherited value>"` reflecting the current Settings value. `value=""` (blank) on initial render so blanks fall back server-side.
3. Server-side: when an override field is blank on submit, use the inherited Settings value (verify the existing route already does this; if not, add the fallback).
4. Add `TestPhase25MarketTestPlaceholders` to `tests/test_dashboard.py` with 2 methods:
   - `test_market_test_renders_inherited_placeholders` — assert each override `<input>` has `placeholder=` attr matching the seeded Settings value
   - `test_market_test_blank_submit_inherits_default` — POST blank override → server uses inherited default (skip if route-test out of scope; cover with a settings.py unit test instead)

**Verification commands:**
```bash
.venv/bin/pytest tests/test_dashboard.py::TestPhase25MarketTestPlaceholders -q --no-header
# Manual grep — every override field must have placeholder=
grep -c 'placeholder=' dashboard_renderer/components/settings.py
```

**Acceptance:** All `TestPhase25MarketTestPlaceholders` methods pass; grep for `placeholder=` in `settings.py::render_market_test_tab` returns ≥7 matches (one per override input).

### Task 2 — Repair `test_chart_payload_escapes_script_close` security test
type: bugfix

**Implementation:**
1. Open `tests/test_dashboard.py::TestRenderBlocks::test_chart_payload_escapes_script_close`.
2. Modify the test fixture so `state['equity_history']` has ≥5 distinct `(date, equity)` tuples (the threshold from Plan 25-07's `_distinct_equity_tuples` helper). This forces the equity chart to render — without the chart, the XSS payload is never injected and `</script>` never appears in the chart payload.
3. Inject the XSS payload into one of the seeded entries (e.g., a date string with `</script>`).
4. Re-run — `replace('</', '<\\/')` defense must fire, payload must be escaped to `<\/script>` in rendered HTML.

**Verification commands:**
```bash
.venv/bin/pytest tests/test_dashboard.py::TestRenderBlocks::test_chart_payload_escapes_script_close -q --no-header
```

**Acceptance:** Test passes AND the chart-payload escape branch is actually exercised (verify by `grep -c '<\\\\/' tests/test_dashboard.py` showing the assertion still asserts the escaped form).

### Task 3 — Update `test_equity_chart_empty_state_placeholder` to post-D-11 copy
type: bugfix

**Implementation:**
1. Open `tests/test_dashboard.py::TestRenderBlocks::test_equity_chart_empty_state_placeholder`.
2. Find the live placeholder string in `dashboard.py::_render_equity_chart_container` (D-11 copy — something like "Chart appears once 5 daily equity points have been recorded.").
3. Update the assertion to match the live string verbatim.

**Verification commands:**
```bash
.venv/bin/pytest tests/test_dashboard.py::TestRenderBlocks::test_equity_chart_empty_state_placeholder -q --no-header
```

**Acceptance:** Test passes.

### Task 4 — Regenerate `tests/golden_empty.html` snapshot
type: bugfix

**Implementation:**
1. Locate the project's snapshot-regeneration script (commonly `scripts/regen_golden.py` or `tests/regen_golden.sh` — check git history of `tests/golden_*.html` for the regen invocation).
2. Run it to produce the current `tests/golden_empty.html` from `_empty_state()` + `render_dashboard`.
3. Inspect the diff — confirm only the expected Phase 25 additions are present (status strip, two-axis nav, fieldsets, helper text, etc.). No accidental personal data, no environment-dependent strings (timestamps, hostnames).
4. Commit the regenerated fixture.

**Verification commands:**
```bash
.venv/bin/pytest tests/test_dashboard.py::TestEmptyState::test_empty_state_matches_committed -q --no-header
wc -c tests/golden_empty.html  # Should be ~49,057 bytes (was 48,413 before regen)
```

**Acceptance:** Test passes. Diff is reviewable (no junk).

</tasks>

<success_criteria>
- All 4 tasks committed atomically
- `.venv/bin/pytest tests/test_dashboard.py tests/test_web_app_factory.py tests/test_web_dashboard.py -q` reports 0 failed (modulo unrelated `test_deploy_sh.py`)
- Re-run verifier (or grep VERIFICATION.md) confirms D-14 MISSING and 3 D-11 test failures are resolved
- SUMMARY.md created
</success_criteria>
