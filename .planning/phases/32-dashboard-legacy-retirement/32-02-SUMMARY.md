---
phase: 32-dashboard-legacy-retirement
plan: 02
subsystem: dashboard_renderer
tags: [refactor, dashboard, legacy-retirement, components, positions, paper-trades, trace, calc-rows, account]
dependency_graph:
  requires:
    - dashboard_renderer.formatters (32-01 symbols: _fmt_*, _display_names, _strategy_settings_for, _CONTRACT_SPECS, _TRACE_FORMULAS, _SEED_LENGTHS, _format_indicator_value, _TraceOpenPlaceholderMap, _TRACE_OPEN_PLACEHOLDER)
    - dashboard_renderer.stats (compute_aggregate_stats, compute_trail_stop_display, compute_unrealised_pnl_display, compute_max_drawdown, compute_sharpe, compute_win_rate, compute_total_return)
    - dashboard_renderer.components.calc_rows (new in this plan — consumed by positions.py)
  provides:
    - dashboard_renderer.components.trace._render_trace_panels
    - dashboard_renderer.components.trace._render_trace_inputs
    - dashboard_renderer.components.trace._render_trace_indicators
    - dashboard_renderer.components.trace._render_trace_vote
    - dashboard_renderer.components.calc_rows._render_calc_row
    - dashboard_renderer.components.calc_rows._render_entry_target_row
    - dashboard_renderer.components.account._render_account_management_region
    - dashboard_renderer.components.account._render_account_balance_form
    - dashboard_renderer.components.account._render_account_stats
    - dashboard_renderer.components.account._render_key_stats
    - dashboard_renderer.components.account._compute_account_stat_values
    - dashboard_renderer.components.positions._render_open_form
    - dashboard_renderer.components.positions._render_single_position_row
    - dashboard_renderer.components.positions._render_drift_banner
    - dashboard_renderer.components.positions._render_trailing_stop_guidance
    - dashboard_renderer.components.paper_trades.render_paper_trades_region
    - dashboard_renderer.components.paper_trades._render_alert_badge
    - dashboard_renderer.components.paper_trades._render_close_form_section
    - dashboard_renderer.components.paper_trades._render_paper_trades_closed
    - dashboard_renderer.components.paper_trades._render_paper_trades_open
    - dashboard_renderer.components.paper_trades._render_paper_trades_open_form
    - dashboard_renderer.components.paper_trades._render_paper_trades_stats
  affects:
    - dashboard_legacy/trace_panels.py (unchanged — retires in 32-04)
    - dashboard_legacy/calc_rows.py (unchanged — retires in 32-04)
    - dashboard_legacy/account_section.py (unchanged — retires in 32-04)
    - dashboard_legacy/positions_section.py (unchanged — retires in 32-04)
    - dashboard_legacy/paper_trades_section.py (unchanged — retires in 32-04)
tech_stack:
  added: []
  patterns:
    - C-2 local sizing_engine imports preserved in calc_rows.py and positions.py
    - 4-arg _compute_unrealised_pnl_display adapter in account.py and positions.py bridges legacy signature to canonical 5-arg stats version
    - render_paper_trades_region public (no underscore) preserved as canonical entrypoint
    - All ported functions use logging.getLogger(__name__)
key_files:
  created:
    - dashboard_renderer/components/trace.py
    - dashboard_renderer/components/calc_rows.py
    - dashboard_renderer/components/account.py
  modified:
    - dashboard_renderer/components/positions.py
    - dashboard_renderer/components/paper_trades.py
    - dashboard_renderer/formatters.py
decisions:
  - 4-arg to 5-arg _compute_unrealised_pnl_display adapter added in account.py and positions.py (legacy signature has 4 args; canonical stats.compute_unrealised_pnl_display takes 5; thin wrapper bridges without changing call sites)
  - formatters.py updated to full 32-01 content in this worktree (32-01 commits were on main branch; this worktree forked from pre-32-01 main; prerequisite symbols added as part of 32-02 execution)
  - No seam split required — all five component files within 500 LOC budget
metrics:
  duration: "~20m"
  completed_date: "2026-05-12"
  tasks: 5
  files_modified: 6
---

# Phase 32 Plan 02: Port Remaining Legacy Render Modules

**One-liner:** Three new component files (trace, calc_rows, account) created and two existing components (positions, paper_trades) grown with verbatim ports of all unique legacy functions, C-2 sizing_engine pattern preserved, canonical imports throughout.

---

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create dashboard_renderer/components/trace.py | d4341d8 | dashboard_renderer/components/trace.py, dashboard_renderer/formatters.py |
| 2 | Create dashboard_renderer/components/calc_rows.py | 060ffeb | dashboard_renderer/components/calc_rows.py |
| 3 | Create dashboard_renderer/components/account.py | c9b1411 | dashboard_renderer/components/account.py |
| 4 | Absorb positions_section.py unique content into components/positions.py | faebe12 | dashboard_renderer/components/positions.py |
| 5 | Absorb paper_trades_section.py unique content into components/paper_trades.py | 3e37e2a | dashboard_renderer/components/paper_trades.py |

---

## Per-Component LOC Counts Post-Absorption

| File | LOC | Budget | Status |
|------|-----|--------|--------|
| `dashboard_renderer/components/trace.py` | 252 | 500 | OK |
| `dashboard_renderer/components/calc_rows.py` | 291 | 500 | OK |
| `dashboard_renderer/components/account.py` | 195 | 500 | OK |
| `dashboard_renderer/components/positions.py` | 393 | 500 | OK |
| `dashboard_renderer/components/paper_trades.py` | 342 | 500 | OK |
| `dashboard_renderer/formatters.py` | 373 | 500 | OK |

No seam split required. All files within budget.

---

## Seam Splits

None. Projected LOC estimates from RESEARCH.md were accurate — no file exceeded 500 LOC.

---

## Remaining `import dashboard as d` in dashboard_renderer/

These are pre-existing (not introduced by 32-02) and will be eliminated in plan 32-03:

| File | Lines |
|------|-------|
| `dashboard_renderer/api.py` | 30, 52, 75, 168, 186 |
| `dashboard_renderer/pages.py` | 32 |
| `dashboard_renderer/components/signals.py` | 79, 133 |
| `dashboard_renderer/components/trades.py` | 7 |
| `dashboard_renderer/components/settings.py` | 7 |

The five files created/modified by this plan contain zero `import dashboard as d` lines.

---

## Canonical Entrypoint Confirmation

`render_paper_trades_region` (PUBLIC, no underscore prefix) is preserved as the canonical entrypoint in `dashboard_renderer/components/paper_trades.py`. The six ported helpers from `dashboard_legacy/paper_trades_section.py` keep their underscore prefixes:

- `_render_alert_badge`
- `_render_close_form_section`
- `_render_paper_trades_closed`
- `_render_paper_trades_open`
- `_render_paper_trades_open_form`
- `_render_paper_trades_stats`

The legacy `_render_paper_trades_region` (with underscore) is a 1-line delegation in `dashboard_legacy/paper_trades_section.py` and was NOT ported — the renderer-side public entrypoint already exists and supersedes it.

---

## Aggregate Boundary Check

```
grep -rn "^from dashboard_legacy|^import dashboard_legacy" dashboard_renderer/components/
```

**Result: ZERO hits.** No Wave 2 component file imports from dashboard_legacy.

---

## Deviations from Plan

### Deviation 1: formatters.py prerequisite applied in this worktree

**Found during:** Task 1 (trace.py creation)

**Issue:** This worktree was forked from `main` at `3e9e7fa` (pre-32-01). The 32-01 commits (`df1b776`, `41a332e`, `e8e476b`) were merged into main but not into this worktree. The underscore-prefixed symbols (`_fmt_currency`, `_TRACE_FORMULAS`, `_TraceOpenPlaceholderMap`, etc.) did not exist in `dashboard_renderer/formatters.py`.

**Fix:** Applied the full 32-01 formatters.py content (373 LOC) to this worktree as part of Task 1's commit. This is the canonical post-32-01 content — identical to what the main repo has.

**Impact:** Task 1 commit (`d4341d8`) includes both `trace.py` and the updated `formatters.py`. No functional deviation from plan intent.

### Deviation 2: _compute_unrealised_pnl_display adapter

**Found during:** Tasks 3 and 4 (account.py and positions.py)

**Issue:** `dashboard_legacy/account_section.py` and `dashboard_legacy/positions_section.py` call `_compute_unrealised_pnl_display(pos, market_id, last_close, state)` — a 4-arg signature. The canonical `dashboard_renderer.stats.compute_unrealised_pnl_display` takes 5 args (adds `contract_specs`).

**Fix:** Added a thin `_compute_unrealised_pnl_display` adapter function in both `account.py` and `positions.py` that accepts the 4-arg legacy signature and forwards to the canonical 5-arg version with `_CONTRACT_SPECS` from formatters. This is the same bridge pattern used in `dashboard_legacy/render_helpers.py`.

**Impact:** Call sites within the ported functions are byte-identical to the legacy source. No behavioral change.

---

## Known Stubs

None. All ported functions have live data sources wired.

---

## Test Results

All tests pass:

```
tests/test_dashboard.py            — 246 passed
tests/test_web_dashboard.py        — 42 passed, 1 skipped (no dashboard.html in repo)
tests/test_html_xss_audit.py       — 23 passed
tests/test_notifier.py             — 171 passed
tests/test_trace_atr_seed.py       — 4 passed
tests/test_trace_vote_params.py    — 5 passed
Total: 491 passed, 1 skipped
```

- Golden snapshot: byte-identical
- XSS gate: green (all `html.escape(value, quote=True)` call sites preserved verbatim)
- C-2 boundary: no module-top sizing_engine imports in any Wave 2 file
- Legacy boundary: zero `from dashboard_legacy` imports in dashboard_renderer/components/

---

## Threat Flags

None. All five files are pure render-layer HTML generation. No new network endpoints, auth paths, file access patterns, or schema changes introduced. XSS gate confirms all dynamic leaf sites retain `html.escape(value, quote=True)`.

---

## Self-Check: PASSED

Files created/modified:
- `dashboard_renderer/components/trace.py` — EXISTS, 252 LOC
- `dashboard_renderer/components/calc_rows.py` — EXISTS, 291 LOC
- `dashboard_renderer/components/account.py` — EXISTS, 195 LOC
- `dashboard_renderer/components/positions.py` — EXISTS, 393 LOC
- `dashboard_renderer/components/paper_trades.py` — EXISTS, 342 LOC

Commits:
- `d4341d8` — EXISTS (Task 1: trace.py + formatters.py prerequisite)
- `060ffeb` — EXISTS (Task 2: calc_rows.py)
- `c9b1411` — EXISTS (Task 3: account.py)
- `faebe12` — EXISTS (Task 4: positions.py absorption)
- `3e37e2a` — EXISTS (Task 5: paper_trades.py absorption)
