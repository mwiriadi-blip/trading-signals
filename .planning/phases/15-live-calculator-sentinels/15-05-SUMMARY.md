---
plan: 15-05
phase: 15
status: complete
completed_at: 2026-04-26
---

# Plan 15-05 Summary

Dashboard renderer extension — calc-row + entry-target + drift banner + side-by-side stop cell + Phase 15 CSS extension.

## What was delivered

### Task 1 — `dashboard.py` production code

Added 3 new render helpers and extended 2 existing ones:

- **`_render_calc_row(state, state_key, pos)`** — per-instrument calculator sub-row rendered as a second `<tr class="calc-row">` inside the existing per-instrument `<tbody>`. Cells: `STOP`, `DIST` (REVIEWS M-3 baseline = `current_close`), `NEXT ADD`, `LEVEL`, `NEW STOP` (REVIEWS H-1 — projected stop after pyramid add via `get_trailing_stop` on synthesized position with peak/trough = `next_add_price`), and `IF HIGH` (forward-look input + W placeholder + L-3 hint span with stable id).
- **`_render_entry_target_row(state, state_key)`** — `Entry target` row when position is FLAT and signal is LONG/SHORT. Shows next-close threshold, suggested contracts via `calc_position_size`, and initial trailing stop. Returns `''` when signal is FLAT.
- **`_render_drift_banner(state)`** — reads `state['warnings']` filtered by `source == 'drift'`. Returns `<div class="sentinel-banner sentinel-drift">` (amber) by default; switches to `sentinel-reversal` (red) when ANY drift message contains `'reversal recommended'` (D-11 merged severity). Returns `''` when no drift warnings.
- **`_render_single_position_row`** — extended with side-by-side `manual: $X | computed: $Y (will close)` stop cell when `manual_stop` is set (D-10).
- **`_render_positions_table`** — extended to call `_render_calc_row` as the second tbody row per instrument.
- **`render_dashboard()`** body composition — `_render_drift_banner(state)` inserted at the top-level slot BETWEEN equity-chart container and `_render_positions_table` (REVIEWS H-2). Drift banner is NOT injected into `_render_positions_table` itself.

CSS: ~60 lines appended to `_INLINE_CSS` (`.calc-row`, `.calc-cell`, `.calc-label`, `.calc-value`, `.calc-input`, `.entry-target`, `.trail-stop-split`, `.sentinel-banner`, `.sentinel-drift`, `.sentinel-reversal`). All using existing `:root` tokens from v1.0; zero new design tokens.

LOCAL imports: `from sizing_engine import get_trailing_stop, check_pyramid, calc_position_size` are inside function bodies only (C-2 hex discipline). Wave 0 M-2 AST guard `test_dashboard_no_module_top_sizing_engine_import` stays green.

### Task 2 — `tests/test_dashboard.py::TestRenderCalculatorRow` + `TestRenderDriftBanner`

Replaced all 15 `pytest.skip` skeletons with real bodies. All pass.

Notable tests:
- `test_pyramid_section_includes_new_stop_after_add` (REVIEWS H-1) — asserts both NEXT ADD price ($7,850) AND projected new stop (computed via `get_trailing_stop` on synthesized position) appear in rendered HTML.
- `test_distance_dollar_and_percent_formatting` (REVIEWS M-3) — fixture pins `current_close (7860) ≠ entry_price (7800)` so the test distinguishes current-baseline distance ($210, 2.7%) from entry-baseline ($150, 1.9%); asserts only the current-baseline values appear in the DIST cell.
- `test_pyramid_section_level_1` — verifies Pitfall 6 next-add formula (LONG: `entry + (level+1)*atr_entry = 7800 + 2*50 = 7900`) and ATR step annotation `(+2×ATR)`.
- `test_pyramid_section_at_max` — `'fully pyramided'` literal at `MAX_PYRAMID_LEVEL`.
- `test_amber_drift_banner` / `test_red_reversal_banner` / `test_mixed_drift_reversal_uses_reversal_color` — D-11 merged severity (any reversal → red).

### Task 3 — `tests/test_dashboard.py::TestBannerStackOrder` (REVIEWS H-2)

Replaced 3 `pytest.skip` skeletons with real bodies. All pass.

- `test_dashboard_banner_hierarchy_corruption_beats_drift` — full `render_dashboard()` round-trip with both corruption + drift warnings; asserts `idx_equity_chart < idx_drift_banner < idx_positions_section_heading` via string-position lookup.
- `test_dashboard_banner_hierarchy_stale_beats_drift` — same shape with `_stale_info` instead of corruption.
- `test_drift_banner_renders_before_positions_heading` — direct H-2 enforcement: drift banner DOM position < `aria-labelledby="heading-positions"` DOM position.

These three tests are the structural proof that `_render_drift_banner` is called from `render_dashboard()` body composition, NOT from inside `_render_positions_table`.

## Test results

```
pytest tests/test_dashboard.py::TestRenderCalculatorRow tests/test_dashboard.py::TestRenderDriftBanner tests/test_dashboard.py::TestBannerStackOrder -v
==> 18 passed in 0.38s
```

## REVIEWS coverage

| Finding | Severity | How addressed |
|---------|----------|--------------|
| H-1 — CALC-04 incomplete (`new stop after add` missing) | HIGH | `_render_calc_row` NEW STOP cell + `(+N×ATR)` annotation; `test_pyramid_section_includes_new_stop_after_add` asserts both NEXT ADD price and projected S |
| H-2 — Dashboard banner stack hierarchy | HIGH | `_render_drift_banner` moved OUT of `_render_positions_table` and INTO `render_dashboard()` body composition; 3 ordering tests verify via string-position assertions |
| M-3 — Distance-to-stop baseline ambiguous | MED | Locked to `current_close` (current-price baseline); fixture in `test_distance_dollar_and_percent_formatting` pins `current_close ≠ entry_price` to prove the semantic |
| L-3 — Forward-look hint conditional | LOW | Hint cell carries explicit `id="forward-stop-{X}-hint"` so Plan 06 can swap via `hx-swap-oob` |

## Execution notes (deviation from standard executor flow)

This plan was completed by the orchestrator inline rather than by a worktree-isolated executor agent. Two consecutive executor-in-worktree attempts stalled because the sandbox blocked `Bash` tool access:

1. **First attempt** (`agent-ad87c846b0fdd71e1`) — agent edited `dashboard.py` via Edit tool but couldn't run pytest, ruff, or git commit. Returned without commits.
2. **Second attempt** (`agent-ab175b0d84196ed9b`) — same behavior. Returned without commits. Production code from this attempt was salvaged from the main working tree (where the agent's edits had landed).

The orchestrator then:
- Committed Task 1 production code in main (commit `cc86418d`)
- Wrote Tasks 2+3 test bodies inline via Edit
- Ran pytest in main — all 18 new tests passed on first try
- Committed Tasks 2+3 (commit `b643d0f1`)

Subsequent waves (3 + 4) will switch to sequential inline execution to avoid the worktree sandbox bash issue.

## Acceptance criteria — all met

- [x] All 3 tasks executed
- [x] Production code committed (`cc86418d`)
- [x] Test bodies committed (`b643d0f1`)
- [x] SUMMARY.md created (this file)
- [x] No modifications to STATE.md or ROADMAP.md
- [x] `pytest tests/test_dashboard.py::TestRenderCalculatorRow tests/test_dashboard.py::TestRenderDriftBanner tests/test_dashboard.py::TestBannerStackOrder` exits 0 with 18 passed (no skips)
- [x] M-2 AST guard `test_dashboard_no_module_top_sizing_engine_import` still green (no module-top sizing_engine import in dashboard.py)
- [x] `grep -E "^from sizing_engine" dashboard.py | wc -l` returns 0
- [x] `grep -A 5 "def _render_positions_table" dashboard.py | grep -c "_render_drift_banner"` returns 0
- [x] `grep -E "new stop|NEW STOP" dashboard.py` returns ≥ 1
- [x] `grep -c "current_close" dashboard.py` returns ≥ 1
