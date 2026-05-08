# Dashboard split manifest — Plan 27-14 Task 2

**Source file:** `dashboard.py` (2221 LOC at HEAD `579d835`)
**Strategy chosen:** **B — `dashboard_legacy/` package** (review-fix agreed-10 default)
**Test golden:** `tests/fixtures/dashboard_canonical.html` (captured Task 1 at HEAD `579d835` after 27-08 + 27-11 land)

---

## Strategy rationale

`dashboard_renderer/` is the modern component package (`signals.py`, `header.py`,
`positions.py`, `settings.py`, `trades.py`, `nav.py`, `paper_trades.py`, etc.).
It owns **per-component** rendering with `RenderContext`-shaped input.

`dashboard.py` is a different shape: ~62 top-level `def`s, ~1200 LOC of which is
**unique local logic** that doesn't fit the dashboard_renderer component model:

- **Page-level orchestration:** `_render_page_body`, `_render_tabbed_dashboard`,
  `_render_single_page_dashboard`, `_render_html_shell`. These compose components
  and own the `<!DOCTYPE>...<body>` shell — they are **above** the component
  layer, not part of it.
- **Operator-only renderers:** `_render_open_form`, `_render_single_position_row`
  (90 LOC), `_render_calc_row` (188 LOC inline display-math), `_render_entry_target_row`,
  `_render_drift_banner`, `_render_trailing_stop_guidance`, `_render_positions_table`,
  `_render_paper_trades_open` (115 LOC), `_render_paper_trades_closed` (70 LOC),
  `_render_paper_trades_region`, `_render_paper_trades_stats`,
  `_render_paper_trades_open_form`, `_render_alert_badge`,
  `_render_close_form_section`. These are **legacy**, page-body-coupled, and
  use module-level constants (`_TRACE_FORMULAS`, `_INDICATOR_DISPLAY_ORDER`,
  `_SEED_LENGTHS`, `_VALID_TRACE_INSTRUMENT_KEYS`, `_TRACE_OPEN_PLACEHOLDER`,
  `_EXIT_REASON_DISPLAY`, `_DEFAULT_STRATEGY_VERSION`, `_SIGNAL_LABEL`,
  `_SIGNAL_COLOUR`, `_INSTRUMENT_DISPLAY_NAMES`, `_CONTRACT_SPECS`).
- **Trace panels (Phase 17):** `_render_trace_inputs`, `_render_trace_indicators`,
  `_render_trace_vote`, `_render_trace_panels`. ~200 LOC of inline indicator
  display logic — explicitly *not* a `dashboard_renderer` component (Phase 17
  D-04 design choice).
- **Account region:** `_render_key_stats`, `_compute_account_stat_values`,
  `_render_account_stats`, `_render_account_balance_form`,
  `_render_account_management_region`. ~140 LOC.
- **Equity chart (DASH-04):** `_render_equity_chart_container`,
  `_distinct_equity_tuples`. ~110 LOC of Chart.js JSON-payload assembly.
- **I/O entry-points:** `_atomic_write_html`, `render_dashboard_files`,
  `render_dashboard_page`, `render_dashboard` alias.

Folding all of this into `dashboard_renderer/` would muddy that package's
responsibility (component-level rendering ↔ page-level orchestration + legacy
forms). Strategy B (dedicated `dashboard_legacy/` package) gives locality:
component package stays component-shaped, legacy package owns page-body
orchestration + operator forms.

> **Most eloquent:** Strategy B — locality wins over LOC reduction. Migrating
> page-level orchestration into the component package would force every future
> reviewer to mentally separate "is this a component or an orchestrator?" —
> exactly the muddied-responsibility outcome Strategy B avoids.

This matches the plan's default recommendation (review-fix agreed-10).

---

## Inventory — line-range to target file mapping

```
dashboard.py (2221 LOC)
├─ Lines 1-127   Module docstring + imports + dashboard_renderer re-exports     → STAY in dashboard.py (shim)
├─ Lines 128-153 Module logger + assets re-exports                              → STAY in dashboard.py (shim)
├─ Lines 156-211 Display-name dicts + market registry helpers + CSS re-export   → dashboard_legacy/render_helpers.py
├─ Lines 213-303 Formatters + stats helpers (all already wrap dr_*)             → dashboard_legacy/render_helpers.py
├─ Lines 306-365 Display-math helpers (_compute_trail_stop_display, _compute_unrealised_pnl_display) → dashboard_legacy/render_helpers.py
├─ Lines 368-490 Module-level constants (_DEFAULT_STRATEGY_VERSION, _TRACE_FORMULAS, _SEED_LENGTHS, _VALID_TRACE_INSTRUMENT_KEYS, _TRACE_OPEN_PLACEHOLDER, _SIGNAL_LABEL, _SIGNAL_COLOUR, _EXIT_REASON_DISPLAY) + _resolve_strategy_version + _resolve_trace_open_keys + _TRACE_TOGGLE_JS re-export → dashboard_legacy/render_helpers.py
├─ Lines 493-560 _render_signout_button + _render_session_note + _render_header + _render_header_ctx (all thin wrappers around dr_*) → dashboard_legacy/section_renderers.py
├─ Lines 563-757 Trace panel renderers (_render_trace_inputs, _render_trace_indicators, _render_trace_vote, _render_trace_panels) → dashboard_legacy/section_renderers.py
├─ Lines 760-768 _render_signal_cards (thin wrap)                               → dashboard_legacy/section_renderers.py
├─ Lines 771-859 _render_open_form (90 LOC; uses _display_names)                → dashboard_legacy/section_renderers.py
├─ Lines 862-948 _render_single_position_row (88 LOC; rich row HTML w/ HTMX)    → dashboard_legacy/section_renderers.py
├─ Lines 951-1136 _render_calc_row (185 LOC; inline display-math + edit form)   → dashboard_legacy/section_renderers.py
├─ Lines 1139-1221 _render_entry_target_row (82 LOC; FLAT-state row)            → dashboard_legacy/section_renderers.py
├─ Lines 1223-1265 _render_drift_banner (43 LOC; warning surface)               → dashboard_legacy/section_renderers.py
├─ Lines 1267-1326 _render_trailing_stop_guidance (60 LOC)                      → dashboard_legacy/section_renderers.py
├─ Lines 1328-1364 _render_positions_table (37 LOC)                             → dashboard_legacy/section_renderers.py
├─ Lines 1366-1373 _render_trades_table (8 LOC; thin wrap)                      → dashboard_legacy/section_renderers.py
├─ Lines 1375-1652 Paper-trade renderers (_render_paper_trades_stats, _render_paper_trades_open_form, _render_alert_badge, _render_paper_trades_open, _render_paper_trades_closed) → dashboard_legacy/section_renderers.py
├─ Lines 1654-1672 _render_close_form_section + _render_paper_trades_region    → dashboard_legacy/section_renderers.py
├─ Lines 1674-1821 Account region (_render_key_stats, _compute_account_stat_values, _render_account_stats, _render_account_balance_form, _render_account_management_region) → dashboard_legacy/section_renderers.py
├─ Lines 1823-1845 Settings/market-test/footer thin wrappers                    → dashboard_legacy/section_renderers.py
├─ Lines 1848-1953 _distinct_equity_tuples + _render_equity_chart_container (105 LOC) → dashboard_legacy/section_renderers.py
├─ Lines 1956-2078 _render_page_body + _render_tabbed_dashboard + _render_single_page_dashboard (page composition) → dashboard_legacy/page_body.py
├─ Lines 2081-2130 _render_html_shell                                            → dashboard_legacy/page_body.py
├─ Lines 2133-2155 _atomic_write_html                                            → dashboard_legacy/page_body.py
└─ Lines 2158-2221 Public API (render_dashboard_files, render_dashboard_page, render_dashboard alias, __main__ block) → STAY in dashboard.py (shim)
```

### Sub-split decision (cohesion-driven)

`section_renderers.py` would be ~1080 LOC if all section renderers landed there
together, breaching the <500 LOC budget (truth #1). Sub-split applied — same
shape Plan 27-12 used to land notifier.py at 9 files instead of the planned 5:

- **`render_helpers.py`** (~280 LOC) — formatters, stats wrappers, display-math
  helpers, module-level lookup dicts (`_TRACE_FORMULAS`, `_SEED_LENGTHS`, etc.),
  `_resolve_strategy_version`, `_resolve_trace_open_keys`,
  `_market_registry`, `_enabled_market_registry`, `_display_names`,
  `_strategy_settings_for`, `_INSTRUMENT_DISPLAY_NAMES`, `_CONTRACT_SPECS`,
  `_DEFAULT_STRATEGY_VERSION`, `_SIGNAL_LABEL`, `_SIGNAL_COLOUR`,
  `_EXIT_REASON_DISPLAY`, `_VALID_TRACE_INSTRUMENT_KEYS`,
  `_TRACE_OPEN_PLACEHOLDER`, `_TRACE_TOGGLE_JS` re-export, `_INLINE_CSS` re-export.
- **`trace_panels.py`** (~200 LOC) — `_render_trace_inputs`,
  `_render_trace_indicators`, `_render_trace_vote`, `_render_trace_panels`,
  `_INDICATOR_DISPLAY_ORDER`, `_INDICATOR_DISPLAY_NAMES`.
- **`positions_section.py`** (~430 LOC) — `_render_open_form`,
  `_render_single_position_row`, `_render_calc_row`, `_render_entry_target_row`,
  `_render_drift_banner`, `_render_trailing_stop_guidance`,
  `_render_positions_table`, `_render_trades_table`.
- **`paper_trades_section.py`** (~290 LOC) — `_render_paper_trades_stats`,
  `_render_paper_trades_open_form`, `_render_alert_badge`,
  `_render_paper_trades_open`, `_render_paper_trades_closed`,
  `_render_close_form_section`, `_render_paper_trades_region`.
- **`account_section.py`** (~150 LOC) — `_render_key_stats`,
  `_compute_account_stat_values`, `_render_account_stats`,
  `_render_account_balance_form`, `_render_account_management_region`.
- **`section_renderers.py`** (~150 LOC) — small section wrappers:
  `_render_signout_button`, `_render_session_note`, `_render_header`,
  `_render_header_ctx`, `_render_signal_cards`, `_render_settings_tab`,
  `_render_add_market_form`, `_render_market_test_tab`, `_render_footer`,
  `_distinct_equity_tuples`, `_render_equity_chart_container`.
- **`page_body.py`** (~280 LOC) — `_render_page_body`,
  `_render_tabbed_dashboard`, `_render_single_page_dashboard`,
  `_render_html_shell`, `_atomic_write_html`.
- **`__init__.py`** (~80 LOC) — re-export everything that dashboard.py shim
  needs to re-export to its callers (web/routes/dashboard.py,
  web/routes/paper_trades.py, web/routes/markets.py, tests).

**Plan §truths #1** says "every file <500 LOC". Split widened from the plan's
3-file list (`page_body.py` / `render_helpers.py` / `section_renderers.py`) to
8 files because cohesively-grouped code segments would otherwise breach the
budget. Same precedent as Plan 27-12 (5 files → 9 files) and Plan 27-13
(7 files → 10 files). Documented as Rule 3 (blocking) deviation.

---

## Re-exports needed in dashboard.py shim

`dashboard.py` will become a thin shim (~150 LOC) that:

1. Keeps the module docstring (canonical CONTEXT D-01 hex documentation).
2. Imports + re-exports every public-and-private name that callers reach via
   `dashboard.X`. Surveyed call sites (Task 2 `<read_first>`):

### From web/routes (production code paths)

| File:line | `from dashboard import …` |
|-----------|---------------------------|
| `web/routes/dashboard.py:403` | `import dashboard` (full module — accesses `dashboard._render_*`, `dashboard.render_dashboard_files`, etc.) |
| `web/routes/dashboard.py:456` | `import dashboard` (same) |
| `web/routes/dashboard.py:493` | `from dashboard import _fmt_currency, _fmt_em_dash` |
| `web/routes/dashboard.py:579` | `from dashboard import _render_session_note, _render_signout_button` |
| `web/routes/paper_trades.py:244, 301, 355, 384, 451` | `from dashboard import _render_paper_trades_region` |
| `web/routes/markets.py:218` | `from dashboard import _render_account_management_region` |

### From main + helpers

| File:line | Form |
|-----------|------|
| `main.py:54` | `import dashboard` |
| `daily_run_helpers.py:53` | `import dashboard` (local — inside helper body per C-2) |

### From tests

| File:line | Form |
|-----------|------|
| `tests/test_html_xss_audit.py:27` | `from dashboard import (...)` |
| `tests/test_notifier.py:2309` | `from dashboard import _render_drift_banner` |
| `tests/regenerate_dashboard_golden.py:31` | `from dashboard import render_dashboard_files` |
| `tests/test_dashboard.py:42-46` | `import dashboard; from dashboard import _fmt_em_dash, render_dashboard` |
| `tests/test_main.py:934` | `import dashboard as _dashboard_module_for_patch` |

### Required re-export list in `dashboard.py` shim (one-time)

```
# Public API
from dashboard_legacy.page_body import render_dashboard_files, render_dashboard_page
from dashboard_legacy.page_body import _atomic_write_html
from dashboard_legacy.page_body import (
  _render_page_body, _render_tabbed_dashboard,
  _render_single_page_dashboard, _render_html_shell,
)
# Section + helper renderers
from dashboard_legacy.section_renderers import (
  _render_signout_button, _render_session_note,
  _render_header, _render_header_ctx,
  _render_signal_cards, _render_settings_tab,
  _render_add_market_form, _render_market_test_tab,
  _render_footer, _render_equity_chart_container,
  _distinct_equity_tuples,
)
from dashboard_legacy.positions_section import (
  _render_open_form, _render_single_position_row, _render_calc_row,
  _render_entry_target_row, _render_drift_banner,
  _render_trailing_stop_guidance, _render_positions_table,
  _render_trades_table,
)
from dashboard_legacy.paper_trades_section import (
  _render_paper_trades_stats, _render_paper_trades_open_form,
  _render_alert_badge, _render_paper_trades_open,
  _render_paper_trades_closed, _render_close_form_section,
  _render_paper_trades_region,
)
from dashboard_legacy.account_section import (
  _render_key_stats, _compute_account_stat_values,
  _render_account_stats, _render_account_balance_form,
  _render_account_management_region,
)
from dashboard_legacy.trace_panels import (
  _render_trace_inputs, _render_trace_indicators,
  _render_trace_vote, _render_trace_panels,
)
from dashboard_legacy.render_helpers import (
  _fmt_em_dash, _fmt_currency, _fmt_percent_signed, _fmt_percent_unsigned,
  _fmt_pnl_with_colour, _fmt_last_updated, _format_indicator_value,
  _compute_sharpe, _compute_max_drawdown, _compute_win_rate,
  _compute_total_return, _compute_aggregate_stats,
  _compute_trail_stop_display, _compute_unrealised_pnl_display,
  _resolve_strategy_version, _resolve_trace_open_keys,
  _market_registry, _enabled_market_registry, _display_names,
  _strategy_settings_for,
)
# Module-level constants (test introspection)
from dashboard_legacy.render_helpers import (
  _DEFAULT_STRATEGY_VERSION, _SIGNAL_LABEL, _SIGNAL_COLOUR,
  _EXIT_REASON_DISPLAY, _VALID_TRACE_INSTRUMENT_KEYS,
  _TRACE_OPEN_PLACEHOLDER, _TRACE_FORMULAS, _SEED_LENGTHS,
  _INSTRUMENT_DISPLAY_NAMES, _CONTRACT_SPECS,
)
# Re-export render_dashboard alias
render_dashboard = render_dashboard_files
# Re-export logger + os module (tests monkeypatch dashboard.os.replace)
import logging, os
logger = logging.getLogger('dashboard')
```

`dashboard.os` is a critical re-export — `tests/test_dashboard.py::TestAtomicWrite::test_crash_on_os_replace_leaves_original_intact` does `patch('dashboard.os.replace', ...)`. The shim's top-level `import os` makes `dashboard.os` resolve to the os module.

---

## Byte-identical-HTML test plan

Uses the Task 1 golden at `tests/fixtures/dashboard_canonical.html`:

```python
def test_dashboard_html_output_byte_identical():
  # Re-render sample_state.json with FROZEN_NOW post-split
  state = json.loads(SAMPLE_STATE_PATH.read_text())
  out = tmp_path / 'd.html'
  dashboard.render_dashboard(state, out_path=out, now=FROZEN_NOW)
  rendered = out.read_bytes()
  golden_full = pathlib.Path('tests/fixtures/dashboard_canonical.html').read_bytes()
  # Strip the SHA-header comment line for comparison
  golden_body = golden_full.split(b'\n', 1)[1]
  assert rendered == golden_body, 'HTML output drifted across split'
```

Existing `tests/test_dashboard.py::TestGoldenSnapshot::test_golden_snapshot_matches_committed`
already locks `render_dashboard(sample_state, FROZEN_NOW)` byte-for-byte
against `tests/fixtures/dashboard/golden.html`. The Task 1 fixture is the
SAME bytes (just with a SHA header). Both tests must stay green.

Post-split decision tree:
- All existing tests pass unchanged → split successful.
- Any byte-diff → STOP, debug. Most-likely failure mode: missed re-export
  causes module-attribute drift.

---

## FastAPI route smoke-test plan (review-fix agreed-10)

Beyond renderer unit tests, hit the FastAPI app directly to verify the
route layer still works post-split:

```python
def test_fastapi_dashboard_route_smoke():
  '''review-fix agreed-10: route-level test post-split.'''
  from web.app import app
  client = TestClient(app)
  # Use auth-bypass header (X-Trading-Signals-Auth) per existing route patterns.
  # See tests/test_web_routes_dashboard.py for the established pattern.
  ...
```

Existing `tests/test_web_routes_dashboard.py` already provides FastAPI route
tests against the production app. The Task 4 smoke test will add ONE
additional structural assertion: response body contains `<!DOCTYPE html>`
and the heading id markers from the post-split render.

---

## File budget summary (predicted)

| File | Predicted LOC | Budget |
|------|--------------:|--------|
| `dashboard.py` (shim) | ~150 | <500 ✓ |
| `dashboard_legacy/__init__.py` | ~80 | <500 ✓ |
| `dashboard_legacy/render_helpers.py` | ~280 | <500 ✓ |
| `dashboard_legacy/trace_panels.py` | ~200 | <500 ✓ |
| `dashboard_legacy/section_renderers.py` | ~150 | <500 ✓ |
| `dashboard_legacy/positions_section.py` | ~430 | <500 ✓ (within ±10% tolerance) |
| `dashboard_legacy/paper_trades_section.py` | ~290 | <500 ✓ |
| `dashboard_legacy/account_section.py` | ~150 | <500 ✓ |
| `dashboard_legacy/page_body.py` | ~280 | <500 ✓ |

Largest predicted: `positions_section.py` at ~430 LOC. Comfortably under the
hard ceiling and the ±10% tolerance (550 LOC).

---

## Risk register

1. **Module-attribute monkeypatch surface.** Tests do `patch('dashboard.os.replace', ...)`
   — the shim must keep a top-level `import os`. Mitigated by including
   `import os` + `import logging` in the shim (same shape Plan 27-12 used
   for `notifier.requests`).
2. **Late-bind through main package not needed here.** Unlike notifier (Plan 27-12)
   and main (Plan 27-13), `dashboard` is NOT a monkeypatch surface for
   functions inside `dashboard_legacy/` modules — tests only monkeypatch
   `dashboard.os.replace` (which is a module attribute, not a function).
   Direct `from dashboard_legacy.X import Y` re-exports are fine; no late-bind
   proxies needed.
3. **`dashboard_renderer/` package is unchanged.** The component package is
   imported BY the legacy shim — no new circular dependency. Hex boundary
   preserved (dashboard_renderer never imports dashboard or dashboard_legacy).
4. **`render_dashboard` alias is an assignment, not a def.** Shim must keep
   the `render_dashboard = render_dashboard_files` assignment AFTER the
   import line. Tests reference `dashboard.render_dashboard` — broken if
   the alias goes missing.
5. **`logger = logging.getLogger('dashboard')` is a module attribute test
   logs go through.** Multiple tests monkeypatch `dashboard.logger` or
   spy on log records. Shim must define this name explicitly (NOT just
   re-export from a daughter module) so the logger name stays
   `'dashboard'` rather than `'dashboard_legacy.X'`.

---

## Manifest revision history

- 2026-05-08 — initial manifest, Strategy B confirmed, 8-file sub-split adopted.
