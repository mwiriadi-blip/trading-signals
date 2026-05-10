---
phase: 25
plan: "09b"
subsystem: dashboard_renderer
tags: [a11y, css, mobile, aria, responsive, forms, label-for]
dependency_graph:
  requires: [25-09]
  provides: [signal-class-wiring, status-dot-glyphs, table-scroll-wiring, aria-expanded-sync, label-for-audit]
  affects: [25-10]
tech_stack:
  added: []
  patterns: [css-class-over-inline-style, aria-expanded-sync, label-for-explicit-pairing, table-scroll-region]
key_files:
  created: []
  modified:
    - dashboard_renderer/components/signals.py
    - dashboard_renderer/components/positions.py
    - dashboard_renderer/components/trades.py
    - dashboard_renderer/components/settings.py
    - dashboard_renderer/formatters.py
    - dashboard_renderer/assets.py
    - dashboard_renderer/shell.py
    - dashboard.py
    - tests/test_dashboard.py
    - tests/fixtures/dashboard/golden.html
    - tests/fixtures/dashboard/golden_empty.html
decisions:
  - "Removed _render_market_selector call from signals tab — D-19 #4 N/A per Plan 25-03 two-axis nav"
  - "fmt_pnl_with_colour uses pnl-positive/pnl-negative/pnl-zero CSS classes (no inline style)"
  - "Total return key stat uses pnl-* classes (no inline style)"
  - "_DETAILS_ARIA_SYNC_JS wired into both dashboard_renderer/shell.py::render_html_shell AND dashboard.py::_render_html_shell (active shell) via import"
  - "Implicit label-wrap pattern replaced with explicit for/id pairs in paper trades form and settings forms"
metrics:
  duration: "~45min"
  completed: "2026-05-06"
  tasks_completed: 2
  tasks_total: 2
  files_changed: 11
---

# Phase 25 Plan 09b: Component A11y Wiring Summary

Wave 4 component-level accessibility wiring. Implements the D-19 / D-20 class catalog at the renderer level — semantic CSS classes replace all inline `style="color:..."`, wide tables wrapped in scrollable focusable regions with `data-label` per cell, FLAT/LONG/SHORT status-dot glyphs added, `aria-expanded` sync JS shipped, and D-19 #6 label-for pairing audit codified as a regression test.

## Tasks Completed

| Task | Description | Commit |
|------|-------------|--------|
| 1 | Replace inline color styles, add status-dot glyphs, wrap tables in table-scroll + data-label | fc2e23c |
| 2 | Add _DETAILS_ARIA_SYNC_JS to shell, D-19 #6 label-for audit, fix orphan inputs | 064dcd5 |

## What Was Shipped

### D-19 #3 — Status-dot glyph beside FLAT/LONG/SHORT

`signals.py` big-label now emits:
```html
<p class="big-label signal-flat">
  <span class="status-dot status-dot--flat" aria-hidden="true"></span>FLAT
</p>
```
Signal int (0/1/-1) maps to class suffix via `_STATE_CLASS` dict — avoids the em-dash label case polluting the class name.

### D-19 #5 — Zero inline style="color:..."

All six inline color style occurrences removed:
- `signals.py` — big-label → `signal-{state}` class
- `trades.py` — direction span → `signal-long/signal-short` class
- `formatters.py::fmt_pnl_with_colour` — → `pnl-positive/pnl-negative/pnl-zero` class
- `dashboard.py::_render_single_position_row` — direction → `signal-long/signal-short`
- `dashboard.py::_render_entry_target_row` — direction → `signal-long/signal-short`
- `dashboard.py::_render_key_stats` — total return → `pnl-positive/pnl-negative/pnl-zero`

CSS comment in `assets.py` that contained `style="color:"` substring also updated (would have caused test false-positive on substring search).

### D-20 Component Side — Wide table-scroll wrapping

| Table | aria-label |
|-------|-----------|
| Open Positions | "Open positions (scrollable)" |
| Closed Trades | "Closed trades (scrollable)" |
| Open Paper Trades (empty + populated) | "Open paper trades (scrollable)" |
| Closed Paper Trades (empty + populated) | "Closed paper trades (scrollable)" |

Every `<td>` in these tables carries `data-label="{column header}"` consumed by the stacked-row `@media (max-width: 600px)` CSS from Plan 25-09.

### D-19 #1 — aria-expanded sync JS

`_DETAILS_ARIA_SYNC_JS` defined in `shell.py` and emitted via both:
- `dashboard_renderer/shell.py::render_html_shell` (future-facing)
- `dashboard.py::_render_html_shell` (currently active shell, imported as `_DETAILS_ARIA_SYNC_INLINE_JS`)

Binds on `DOMContentLoaded` and `htmx:afterSwap`. Uses `dataset.ariaSyncBound` marker to prevent duplicate listeners after re-bind.

### D-19 #4 — Market `<select>` N/A confirmed

`_render_market_selector` was still being called from the signals tab render despite Plan 25-03 shipping the two-axis nav tab strip. The call was removed — the market tab strip in `render_two_axis_nav` is the sole market-selection surface. `test_market_select_surface_removed` regression-locks this.

### D-19 #6 — Label-for pairing audit (forms audited)

| Form | Surface | Status before | Fix applied |
|------|---------|--------------|-------------|
| Add-market chip | `nav.py::render_add_market_chip` | Already paired (Plan 25-05) | None needed |
| Settings | `settings.py::render_settings_tab` | Already paired (Plan 25-08) | None needed |
| Market Test | `settings.py::render_market_test_tab` | Orphan inputs | Added `for`/`id` to all 8 inputs |
| Add-market form | `settings.py::render_add_market_form` | Orphan inputs | Added `for`/`id` to all 6 inputs |
| Account balance | `dashboard.py::_render_account_balance_form` | Orphan inputs | Added `for`/`id` to both inputs |
| Paper trades open | `dashboard.py::_render_paper_trades_open_form` | Implicit wrap (no `for`) | Replaced with explicit `for`/`id` pairs |
| Open Position | `dashboard.py::_render_open_form` | Already paired | None needed |

## Test Results

| Test class | Tests | Result |
|------------|-------|--------|
| TestPhase25NoInlineColor | 2 | PASS (xfail removed) |
| TestPhase25WideTable | 2 | PASS (xfail removed) |
| TestPhase25LabelForAudit | 3 | PASS (new, green) |
| TestFormatters::pnl_with_colour_* | 3 | PASS (updated for CSS class assertions) |
| TestRenderBlocks::signal_card_colours | 1 | PASS (updated) |
| TestRenderBlocks::key_stats_total_return | 1 | PASS (updated) |
| TestGoldenSnapshot | 1 | PASS (golden regenerated) |

Pre-existing failures (unchanged from 25-09):
- `test_chart_payload_escapes_script_close` — empty equity_history prevents chart render
- `test_equity_chart_empty_state_placeholder` — placeholder text mismatch
- `TestEmptyState::test_empty_state_matches_committed` — empty_state fixture vs reset_state() mismatch
- 3 deploy.sh tests

7 xfails remain for Plan 25-10 work.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] _render_market_selector still called after Plan 25-03**
- **Found during:** Task 2 (D-19 #4 regression test writing)
- **Issue:** `_render_market_selector` was still called in the signals tab body lambda despite Plan 25-03 shipping the two-axis market tab strip. The old `<select aria-label="Market selection">` was being rendered into every dashboard page, causing `test_market_select_surface_removed` to fail.
- **Fix:** Removed `_render_market_selector(state)` call from the signals page body lambda in `dashboard.py::_render_page_body`. The two-axis nav handles market selection.
- **Files modified:** dashboard.py
- **Commit:** 064dcd5

**2. [Rule 2 - Missing] Implicit label-wrap pattern doesn't satisfy explicit for/id audit**
- **Found during:** Task 2 when running `Collector` scan against rendered HTML
- **Issue:** `_render_paper_trades_open_form` used implicit wrap pattern (`<label>...<input>...</label>`) with no `for` attribute. The `Collector` test only checks `label[for]`, `aria-label`, `aria-labelledby` — implicit wrapping produces orphan inputs per the test.
- **Fix:** Replaced implicit wrap labels with explicit `for`/`id` pairs on all 6 inputs.
- **Files modified:** dashboard.py
- **Commit:** 064dcd5

**3. [Rule 2 - Missing] fmt_pnl_with_colour inline style not on task scope list but caught by test**
- **Found during:** Task 1 when test_rendered_html_has_no_inline_color_styles still failed after fixing signals.py
- **Issue:** `formatters.py::fmt_pnl_with_colour` emitted `style="color: {hex}"` which appeared in any rendered page with P&L values.
- **Fix:** Replaced with `class="pnl-positive/pnl-negative/pnl-zero"` CSS classes (already defined in Plan 25-09 _INLINE_CSS).
- **Files modified:** dashboard_renderer/formatters.py
- **Commit:** fc2e23c

**4. [Rule 1 - Bug] CSS comment in assets.py contained style="color:" substring**
- **Found during:** Task 1 verification — assertion fired on the comment inside `<style>` block
- **Issue:** `/* Signal color classes (D-19 #5) — 25-09b will replace inline style="color:…" */` was emitted inside `<style>` in the rendered HTML, triggering the substring check.
- **Fix:** Updated comment text to not contain the literal `style="color:` string.
- **Files modified:** dashboard_renderer/assets.py
- **Commit:** fc2e23c

**5. [Rule 1 - Bug] _DETAILS_ARIA_SYNC_JS wired to shell.py but active shell is dashboard.py**
- **Found during:** Task 2 when `test_details_aria_sync_js_in_shell` failed
- **Issue:** `dashboard_renderer/shell.py::render_html_shell` is defined but NOT called — `api.py` calls `d._render_html_shell` which is `dashboard.py::_render_html_shell` (the old shell). Plan 25-09b's action to wire into shell.py's function had no effect on the rendered HTML.
- **Fix:** Imported `_DETAILS_ARIA_SYNC_JS` from shell.py into dashboard.py as `_DETAILS_ARIA_SYNC_INLINE_JS` and emitted it from `dashboard.py::_render_html_shell`.
- **Files modified:** dashboard.py
- **Commit:** 064dcd5

## Known Stubs

None — all wiring is complete. Data flows from renderer state to HTML attributes. CSS classes exist in `_INLINE_CSS` (Plan 25-09).

## Threat Flags

None. All class-name additions use server-controlled static strings (no user input). `data-label` values are module-level constant tuples.

## Self-Check: PASSED

- `dashboard_renderer/components/signals.py` — `signal-flat` present: FOUND
- `dashboard_renderer/components/positions.py` — `table-scroll` present: FOUND
- `dashboard_renderer/components/trades.py` — `table-scroll` + `data-label` present: FOUND
- `dashboard_renderer/shell.py` — `_DETAILS_ARIA_SYNC_JS` present: FOUND
- `tests/test_dashboard.py` — `TestPhase25LabelForAudit` present: FOUND
- Commit fc2e23c: FOUND
- Commit 064dcd5: FOUND
- TestPhase25NoInlineColor: 2 PASSED
- TestPhase25WideTable: 2 PASSED
- TestPhase25LabelForAudit: 3 PASSED
- Zero inline `style="color:` in rendered HTML: CONFIRMED
