---
phase: 14
fixed_at: 2026-04-25
review_path: .planning/phases/14-trade-journal-mutation-endpoints/14-REVIEW.md
iteration: 1
findings_in_scope: 4
fixed: 4
skipped: 0
status: all_fixed
---

# Phase 14: Code Review Fix Report

**Fixed at:** 2026-04-25
**Source review:** `.planning/phases/14-trade-journal-mutation-endpoints/14-REVIEW.md`
**Iteration:** 1
**Scope:** CRITICAL + HIGH (workflow default — MEDIUM/LOW deferred)

**Summary:**
- Findings in scope: 4 (1 CRITICAL + 3 HIGH)
- Fixed: 4
- Skipped: 0
- MEDIUM/LOW (13 items): out of scope this pass

**Test status after all fixes:**
- 1074 passed (baseline 1062 + 12 new regression tests)
- 16 pre-existing `test_main.py` weekend-skip failures unchanged (documented baseline)
- Zero new regressions

## Fixed Issues

### CR-01: HTMX forms send form-encoded; FastAPI handlers expect JSON

**Files modified:** `dashboard.py`, `web/routes/trades.py`, `tests/test_dashboard.py`, `tests/test_web_trades.py`, `tests/fixtures/dashboard/golden.html`, `tests/fixtures/dashboard/golden_empty.html`
**Commit:** 26c1537
**Applied fix:**
- Added `_HTMX_JSON_ENC_URL` + `_HTMX_JSON_ENC_SRI` constants to `dashboard.py` (SRI verified via `curl … | openssl dgst -sha384`).
- Added `<script src="…json-enc.js" integrity="sha384-nRnAvEUI7N/XvvowiMiq7oEI04gOXMCqD3Bidvedw+YNbj7zTQACPlRI3Jt3vYM4" crossorigin="anonymous">` after the core HTMX script in `<head>`.
- Added `hx-ext="json-enc"` to:
  - the open form (`dashboard.py::_render_open_form`)
  - the Confirm-close button (`web/routes/trades.py::_render_close_form_partial`)
  - the Save button (`web/routes/trades.py::_render_modify_form_partial`)
- Inline `REVIEW CR-01:` comments at each call-site reference back to this finding.
- Updated `test_chart_payload_escapes_script_close` expected `</script>` count from 4 → 5 (one extra CDN script tag).
- Regenerated `tests/fixtures/dashboard/golden.html` + `golden_empty.html` via `tests/regenerate_dashboard_golden.py`.

**Regression tests added (5):**
- `TestRenderDashboardHTMXVendorPin::test_json_enc_extension_script_present`
- `TestRenderDashboardHTMXVendorPin::test_open_form_has_json_enc_attribute`
- `TestJsonEncExtension::test_close_form_partial_has_json_enc_attribute`
- `TestJsonEncExtension::test_modify_form_partial_has_json_enc_attribute`
- `TestJsonEncExtension::test_open_form_encoded_post_returns_400_with_field_errors` (defense-in-depth: form-encoded body returns 400, not 500/422)

### HR-01: Pydantic models silently drop unknown fields

**Files modified:** `web/routes/trades.py`, `tests/test_web_trades.py`
**Commit:** 1698be5
**Applied fix:**
- Added `from pydantic import … ConfigDict, …` import.
- Added `model_config = ConfigDict(extra='forbid')` to `OpenTradeRequest`, `CloseTradeRequest`, `ModifyTradeRequest`.
- Added explanatory docstring lines on each model citing the REVIEW HR-01 rationale (with the `new_top` typo example for `ModifyTradeRequest`).

**Regression tests added (3):**
- `TestExtraFieldsForbidden::test_open_unknown_field_returns_400`
- `TestExtraFieldsForbidden::test_close_unknown_field_returns_400`
- `TestExtraFieldsForbidden::test_modify_typoed_new_stop_returns_400` (the exact `new_top` typo from the review; also asserts no save occurs on 400)

### HR-02: Lockstep parity broken when peak/trough = 0.0

**Files modified:** `dashboard.py`, `tests/test_dashboard.py`
**Commit:** 4517dc9
**Applied fix:**
- Replaced `position.get('peak_price') or position['entry_price']` (truthiness — drops 0.0) with explicit `peak = position.get('peak_price'); if peak is None: peak = position['entry_price']`, matching `sizing_engine.py:247-254` semantics.
- Same change for `trough` on the SHORT branch.
- Inline `REVIEW HR-02:` comment cross-references the sizing_engine line numbers.

**Regression tests added (2):**
- `TestRenderManualStopBadge::test_compute_trail_stop_display_lockstep_parity_with_zero_peak_long` — peak=0.0 case
- `TestRenderManualStopBadge::test_compute_trail_stop_display_lockstep_parity_with_zero_trough_short` — trough=0.0 case
Both assert dashboard helper and `sizing_engine.get_trailing_stop` return identical values for the 0.0 edge case.

### HR-03: sizing_engine.step() builds positions without manual_stop

**Files modified:** `sizing_engine.py`, `tests/test_sizing_engine.py`
**Commit:** bb1ad1a
**Applied fix:**
- Added `'manual_stop': None,` to the position-build dict literal at `sizing_engine.py:571-583` (covers both fresh-open and reversal-open code paths — same dict literal serves both).
- Inline `REVIEW HR-03 / Phase 14 D-09:` comment cites the v3 schema requirement.

**Regression tests added (2):**
- `TestStepProducesV3Schema::test_step_open_position_includes_manual_stop_key` — uses `transition_none_to_long` fixture
- `TestStepProducesV3Schema::test_step_reversal_open_position_includes_manual_stop_key` — hand-built reversal scenario (the committed `transition_long_to_short` fixture has rvol=0.15 → contracts=0, so it doesn't actually exercise the position-build branch; replaced with atr=20/rvol=0.10 → contracts=3 to exercise it)

## Skipped Issues

None — all 4 in-scope findings fixed.

## Out of Scope (deferred to next pass or Phase 16)

- **MEDIUM (7):** MR-01..MR-07 — partial response bytes, regex fragility, modify-success topology, missing D-15 divergence test, env-var double read, position-row column count, stub semantics gap
- **LOW (6):** LR-01..LR-06 — Literal validation on URL params, 404 UX, min mismatches, validator import location, error UX edge case, copywriting duplication
- **INFO (10):** not enumerated in this fix pass

These will be triaged in a follow-up `/gsd-code-review-fix --all 14` pass or rolled into Phase 16 hardening per the REVIEW.md recommendation.

---

_Fixed: 2026-04-25_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
