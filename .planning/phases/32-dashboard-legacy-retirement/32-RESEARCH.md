# Phase 32: Dashboard Legacy Retirement - Research

**Researched:** 2026-05-12
**Domain:** Python refactor — dashboard rendering consolidation, circular import elimination
**Confidence:** HIGH

## Summary

`dashboard_legacy/` is already a thin delegation layer: six of its eight modules forward almost everything to `dashboard_renderer.*` components. The circular import (`dashboard_renderer/api.py`, `pages.py`, and two components doing `import dashboard as d`) exists because those files were written first and the legacy functions were never pulled forward. Eliminating the circle means moving the remaining unique logic from `dashboard_legacy/` into `dashboard_renderer/` and updating the `d.*` call sites to direct imports.

The critical structural finding is that `dashboard_renderer/shell.py::render_html_shell` is dead code — it is never called in any production or test path. The active HTML shell function is `dashboard_legacy/page_body._render_html_shell`, which the golden tests lock. After port, `page_body._render_html_shell` content must replace (not append to) `shell.render_html_shell`, and `api._render_header_and_body` must call `shell.render_html_shell` directly instead of `d._render_html_shell`. The test patching `dashboard.os.replace` must be updated to patch `dashboard_renderer.io.os.replace`.

Two new component files are needed: `components/trace.py` (trace panels, ~247 LOC, no existing target) and `components/calc_rows.py` (calculator rows, ~288 LOC — splitting from `components/positions.py` to stay under 500 LOC). One new file: `components/account.py` (~171 LOC). The `test_dashboard_split_seam.py::test_dashboard_files_under_500_loc` test asserts `dashboard_legacy/` is a directory with at least two files — it must be updated after the stub replacement.

**Primary recommendation:** Port in domain-first order — (1) formatters/stats absorb render_helpers wrappers, (2) new components/trace.py, components/calc_rows.py, components/account.py created, (3) page_body logic absorbed into shell.py + api.py page composition, (4) circular imports in api.py + pages.py + paper_trades.py + positions.py replaced with direct imports, (5) dashboard.py shim thinned, (6) dashboard_legacy/ replaced with ImportError stub, (7) callers and tests updated.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Redistribute by domain — legacy functions merge into existing `dashboard_renderer/` modules by semantic fit. Examples: `render_helpers.py` format helpers → `dashboard_renderer/formatters.py`; `positions_section.py` → `dashboard_renderer/components/positions.py`; `section_renderers.py` header/footer → `dashboard_renderer/components/header.py` + `footer.py`; `page_body.py` HTML shell / atomic write → `dashboard_renderer/shell.py` + `dashboard_renderer/io.py`.
- **D-02:** 500 LOC cap enforced. When a receiving file would overflow, split at a natural seam. No blanket cap relaxation.
- **D-03:** Audit-first. For each `dashboard_legacy/` module, check what counterpart functions already exist in the target file. Port only functions NOT yet covered. Delete duplicates.
- **D-04:** `dashboard_legacy/` → ImportError stub. After all functions are ported: delete all 7 submodule files and replace with a single `__init__.py` raising `ImportError("dashboard_legacy retired — use dashboard_renderer")`.
- **D-05:** Update all callers to import from `dashboard_renderer.*` directly. No backward-compat re-export layer in `dashboard.py`.
- **D-06:** Golden snapshot tests in `tests/test_dashboard.py` are the sufficient byte-identity gate. No explicit pre-refactor HTML baseline file needed.

### Claude's Discretion

- Exact seam names when a receiving file overflows (e.g., `positions_table.py` vs `positions_grid.py`).
- Import ordering within absorbed files (stdlib → third-party → local).
- Whether to add `__all__` or `# noqa: F401` on re-exports in `dashboard_renderer/__init__.py` after the circular import is resolved.
- Exact placement of `logger = logging.getLogger('dashboard')` after the shim thinning — stays in `dashboard.py` for journalctl name continuity.

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| OPS-06 | Dashboard legacy retirement — `dashboard_renderer/` as sole canonical renderer; `dashboard_legacy/` retired; `dashboard.py` shim ≤100 LOC | Module inventory (§Module Inventory), caller audit (§Caller Audit), test gate inventory (§Test Gate Inventory) confirm all unique functions have homes; LOC analysis confirms no overflow when absorbing. OPS-06 is a ROADMAP-only label — not in REQUIREMENTS.md as of 2026-05-10 (added with OPS-05 in the 2026-05-12 ROADMAP update). |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- 2-space indent throughout — do NOT run `ruff format`
- 500 LOC cap per file — enforced by `tests/test_signal_engine.py` + plan-time seam analysis
- `Decimal` for all AUD amounts
- `system_params.py` single source of truth for constants
- `mutate_state()` only for state writes
- Hex-lite boundary: `dashboard.py` and all `dashboard_renderer/` files must NOT import `signal_engine`, `sizing_engine` at module top (C-2 local imports only), `data_fetcher`, `notifier`, `main`, `numpy`, `pandas`, `yfinance`, `requests`
- `html.escape(value, quote=True)` at every dynamic leaf site — XSS gate enforces this

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| HTML rendering / composition | Web render I/O hex (`dashboard_renderer/`) | — | Peer of state_manager; no signal_engine or data_fetcher imports |
| Format helpers (currency, %) | `dashboard_renderer/formatters.py` | — | Pure presentation math; no I/O |
| Stats (sharpe, drawdown) | `dashboard_renderer/stats.py` | — | Pure math; reads state dict only |
| Page body composition | `dashboard_renderer/shell.py` + `api.py` | — | Orchestration logic; must stay in renderer |
| Atomic HTML write | `dashboard_renderer/io.py` | — | I/O adapter; already correct home |
| Trace panel rendering | New `dashboard_renderer/components/trace.py` | — | No existing home in renderer |
| Calculator rows | New `dashboard_renderer/components/calc_rows.py` | — | Split needed to honour 500 LOC cap |
| Account management region | New `dashboard_renderer/components/account.py` | — | No existing home in renderer |
| Public shim surface | `dashboard.py` (≤100 LOC) | — | Back-compat entry point only |

---

## Module Inventory

### dashboard_legacy/ — LOC, functions, overlap, and proposed targets

| File | LOC | Functions | Overlap with dashboard_renderer? | Target |
|------|-----|-----------|----------------------------------|--------|
| `__init__.py` | 18 | none (docstring) | — | Replace with ImportError stub |
| `render_helpers.py` | 353 | 21 total; 14 are single-line delegations to `dr_formatters.*` or `dr_stats.*` | 14 delegations are duplicates; 7 are unique | `formatters.py` (format wrappers + market registry + resolve helpers + constants); `stats.py` (stat compute wrappers + unrealised PnL) |
| `section_renderers.py` | 233 | 11 total; 8 are single-line delegations to dashboard_renderer components | `_render_equity_chart_container` (90 LOC, unique); `_distinct_equity_tuples` (20 LOC, unique); `_render_signout_button` + `_render_session_note` (unique) | `components/header.py` (signout + session note); new equity chart section in `components/header.py` or `shell.py` |
| `page_body.py` | 233 | 5 | `_atomic_write_html` already delegates to `dashboard_renderer.io.atomic_write_html`; `_render_html_shell` is the ACTIVE shell (shell.py's `render_html_shell` is dead code) | `shell.py` absorbs `_render_page_body` tuple function + `_render_tabbed_dashboard` + `_render_single_page_dashboard`; `_render_html_shell` content replaces dead `shell.render_html_shell`; `_atomic_write_html` wrapper is deleted (callers use `io.atomic_write_html` directly) |
| `positions_section.py` | 347 | 6 | `_render_positions_table` delegates to `dr_render_positions_table`; `_render_trades_table` delegates to `dr_render_trades_table` | `components/positions.py` absorbs `_render_open_form` (~90 LOC), `_render_single_position_row` (~90 LOC), `_render_drift_banner` (~45 LOC), `_render_trailing_stop_guidance` (~65 LOC) |
| `calc_rows.py` | 288 | 2 | None — `_render_calc_row` (190 LOC, C-2 sizing_engine) and `_render_entry_target_row` (80 LOC, C-2 sizing_engine) are unique | New `components/calc_rows.py` (required: positions.py + calc_rows content would overflow 500 LOC) |
| `paper_trades_section.py` | 310 | 7 | `_render_paper_trades_region` delegates to `dr_render_paper_trades_region` (single line) | `components/paper_trades.py` absorbs all 6 rendering functions (~280 unique LOC) |
| `account_section.py` | 171 | 5 | None — `_render_account_management_region`, `_render_account_balance_form`, `_render_account_stats`, `_render_key_stats`, `_compute_account_stat_values` are unique | New `components/account.py` (~171 LOC) |
| `trace_panels.py` | 247 | 4 | None — `_render_trace_inputs`, `_render_trace_indicators`, `_render_trace_vote`, `_render_trace_panels` are unique | New `components/trace.py` (~247 LOC) |

[VERIFIED: grep + wc -l across all files in this session]

### dashboard_renderer/ — current LOC and post-absorption projected LOC

| File | Current LOC | Expected absorption | Projected LOC | Overflow? |
|------|------------|---------------------|---------------|-----------|
| `formatters.py` | 163 | render_helpers wrappers + market registry fns + resolve helpers + constants (~211 LOC of unique content) | ~374 | No |
| `stats.py` | 170 | render_helpers stat wrappers + unrealised PnL wrapper (~66 LOC) | ~236 | No |
| `shell.py` | 204 | page_body composition fns: `_render_page_body` tuple fn, `_render_tabbed_dashboard`, `_render_single_page_dashboard`; also `_render_html_shell` body replaces dead `render_html_shell` | ~324 | No |
| `io.py` | 33 | Nothing new — `_atomic_write_html` wrapper is deleted; callers updated to call `io.atomic_write_html` directly | 33 | No |
| `api.py` | 202 | No new functions; circular `import dashboard as d` calls replaced with direct imports | ~202 | No |
| `pages.py` | 39 | No new functions; circular `import dashboard as d` replaced | ~39 | No |
| `components/header.py` | 148 | `_render_signout_button` (13), `_render_session_note` (12), `_render_equity_chart_container` (90), `_distinct_equity_tuples` (20) | ~283 | No |
| `components/positions.py` | 73 | `_render_open_form` (~90), `_render_single_position_row` (~90), `_render_drift_banner` (~45), `_render_trailing_stop_guidance` (~65) — delegating wrappers deleted | ~363 | No |
| `components/paper_trades.py` | 29 | All 6 unique rendering functions (~280 LOC) | ~309 | No |
| `components/calc_rows.py` | 0 (new) | `_render_calc_row` (~190), `_render_entry_target_row` (~80) | ~270 | No |
| `components/account.py` | 0 (new) | All 5 account functions (~171) | ~171 | No |
| `components/trace.py` | 0 (new) | All 4 trace functions (~247) | ~247 | No |

[VERIFIED: wc -l + function-body LOC estimates from reading source in this session]

---

## Circular Import Map

All `import dashboard as d` sites in `dashboard_renderer/`:

### `dashboard_renderer/api.py`

| Line | Call | Ultimate source | Post-port target |
|------|------|-----------------|------------------|
| 30 | `d._resolve_strategy_version(state)` | `render_helpers._resolve_strategy_version` | `from dashboard_renderer.formatters import _resolve_strategy_version` |
| 30 | `d._resolve_trace_open_keys(ctx.state, ...)` | `render_helpers._resolve_trace_open_keys` | `from dashboard_renderer.formatters import _resolve_trace_open_keys` |
| 52 | `d._render_header_ctx(ctx, ...)` | `section_renderers._render_header_ctx` → `header.render_header_from_context` | `from dashboard_renderer.components.header import render_header_from_context` (direct) |
| 52 | `d._render_html_shell(ctx, body)` | `page_body._render_html_shell` | `from dashboard_renderer.shell import render_html_shell` |
| 75, 168, 186 | `d.logger` | `dashboard.py` logger | `from dashboard_renderer import _logger` or import at module top |
| 75 | `d._render_tabbed_dashboard(ctx)` | `page_body._render_tabbed_dashboard` | `from dashboard_renderer.shell import _render_tabbed_dashboard` |
| 117 | `d._render_single_page_dashboard(ctx, page)` | `page_body._render_single_page_dashboard` | `from dashboard_renderer.shell import _render_single_page_dashboard` |
| 119, 201 | `d._atomic_write_html(html_str, path)` | `page_body._atomic_write_html` → `io.atomic_write_html` | `from dashboard_renderer.io import atomic_write_html` |

### `dashboard_renderer/pages.py`

| Line | Call | Ultimate source | Post-port target |
|------|------|-----------------|------------------|
| 16 | `dashboard._render_single_page_dashboard(ctx, page)` | `page_body._render_single_page_dashboard` | `from dashboard_renderer.shell import _render_single_page_dashboard` |
| 32, 38 | `d._render_page_body(ctx, page)` | `page_body._render_page_body` (returns 5-tuple) | `from dashboard_renderer.shell import _render_page_body` |

### `dashboard_renderer/components/paper_trades.py`

| Line | Call | Post-port target |
|------|------|-----------------|
| 5 | `d._compute_aggregate_stats(...)` | `from dashboard_renderer.stats import compute_aggregate_stats` |
| 9, 19, 24-27 | `d._render_paper_trades_*`, `d._render_close_form_section` | Direct calls within same file (after absorption) |

### `dashboard_renderer/components/positions.py`

| Line | Call | Post-port target |
|------|------|-----------------|
| 5 | `d._display_names(state)` | `from dashboard_renderer.formatters import _display_names` |
| 15 | `d._render_entry_target_row(...)` | `from dashboard_renderer.components.calc_rows import _render_entry_target_row` |
| 27, 28 | `d._render_single_position_row(...)`, `d._render_calc_row(...)` | local within positions.py + calc_rows import |
| 47 | `d._render_open_form(state)` | local within positions.py (after absorption) |

[VERIFIED: grep -n "import dashboard as d\|import dashboard" across all dashboard_renderer/*.py files in this session]

---

## Caller Audit

Every production file that imports from `dashboard` or `dashboard_legacy` and the proposed new import paths:

| File | Current import | Symbol(s) | New import path |
|------|---------------|-----------|-----------------|
| `web/routes/dashboard/__init__.py:363,416` | `import dashboard` | `dashboard.render_dashboard_page`, `dashboard.render_dashboard_files` | Keep `import dashboard` — these call the public API that the shim preserves |
| `web/routes/dashboard/__init__.py:484` | `from dashboard import _render_session_note, _render_signout_button` | `_render_session_note`, `_render_signout_button` | `from dashboard_renderer.components.header import _render_session_note, _render_signout_button` |
| `web/routes/dashboard/_renderers.py:94` | `from dashboard import _fmt_currency, _fmt_em_dash` | `_fmt_currency`, `_fmt_em_dash` | `from dashboard_renderer.formatters import fmt_currency, fmt_em_dash` (note: public names, not `_` prefixed in formatters) |
| `web/routes/markets.py:258` | `from dashboard import _render_account_management_region` | `_render_account_management_region` | `from dashboard_renderer.components.account import _render_account_management_region` |
| `web/routes/paper_trades/__init__.py:69,130,184,213,280` | `from dashboard import _render_paper_trades_region` | `_render_paper_trades_region` | `from dashboard_renderer.components.paper_trades import render_paper_trades_region` |
| `daily_run_helpers.py:53` | `import dashboard` (local, C-2) | `dashboard.render_dashboard_files` | Keep `import dashboard` — shim covers it |
| `main.py:54` | `import dashboard` (local, C-2) | `main.dashboard` attribute | Keep `import dashboard` — shim covers it |
| `tests/regenerate_dashboard_golden.py:31` | `from dashboard import render_dashboard_files` | `render_dashboard_files` | Keep — shim covers it |

[VERIFIED: grep -rn "import dashboard" production files in this session]

---

## Test Gate Inventory

### Symbols imported from `dashboard` in tests — new locations after port

| Test file | Symbol | New location |
|-----------|--------|-------------|
| `tests/test_dashboard.py` | `_compute_trail_stop_display` | `dashboard_renderer.stats.compute_trail_stop_display` |
| `tests/test_dashboard.py` | `_fmt_currency` | `dashboard_renderer.formatters.fmt_currency` |
| `tests/test_dashboard.py` | `_format_indicator_value` | `dashboard_renderer.formatters.format_indicator_value` |
| `tests/test_dashboard.py` | `_render_calc_row` | `dashboard_renderer.components.calc_rows._render_calc_row` |
| `tests/test_dashboard.py` | `_render_entry_target_row` | `dashboard_renderer.components.calc_rows._render_entry_target_row` |
| `tests/test_dashboard.py` | `_render_drift_banner` | `dashboard_renderer.components.positions._render_drift_banner` |
| `tests/test_dashboard.py` | `render_dashboard` | `dashboard.render_dashboard` (shim alias preserved) |
| `tests/test_web_dashboard.py` | `_fmt_currency` | `dashboard_renderer.formatters.fmt_currency` |
| `tests/test_web_dashboard.py` | `_render_single_position_row` | `dashboard_renderer.components.positions._render_single_position_row` |
| `tests/test_html_xss_audit.py` | `_render_drift_banner` | `dashboard_renderer.components.positions._render_drift_banner` |
| `tests/test_html_xss_audit.py` | `_render_paper_trades_closed` | `dashboard_renderer.components.paper_trades._render_paper_trades_closed` |
| `tests/test_html_xss_audit.py` | `_render_paper_trades_open` | `dashboard_renderer.components.paper_trades._render_paper_trades_open` |
| `tests/test_notifier.py` | `_render_drift_banner` | `dashboard_renderer.components.positions._render_drift_banner` |
| `tests/test_trace_atr_seed.py` | `_render_trace_panels` (from `dashboard_legacy.trace_panels`) | `dashboard_renderer.components.trace._render_trace_panels` |
| `tests/test_trace_vote_params.py` | `_render_trace_vote`, `_render_trace_panels` (from `dashboard_legacy.trace_panels`) | `dashboard_renderer.components.trace._render_trace_vote`, `._render_trace_panels` |
| `tests/test_dashboard.py:1126` | `patch('dashboard.os.replace', ...)` | Must change to `patch('dashboard_renderer.io.os.replace', ...)` |

### Tests that need structural updates (not just import path changes)

| Test | Issue | Required change |
|------|-------|-----------------|
| `tests/test_dashboard_split_seam.py::test_dashboard_files_under_500_loc` | Asserts `dashboard_legacy/` is a dir with `>=2` files | Update: after retirement, `dashboard_legacy/__init__.py` is the only file; test should assert stub exists and raises ImportError, not check file count |
| `tests/test_dashboard_split_seam.py::test_dashboard_html_output_byte_identical` | Tests against `tests/fixtures/dashboard_canonical.html` | Golden must be regenerated if HTML output changes (unlikely since `dashboard.render_dashboard` shim is preserved) |

[VERIFIED: grep across all test files in this session]

---

## AST / XSS Gate Analysis

### `FORBIDDEN_MODULES_DASHBOARD` (test_signal_engine.py:568)

Current frozenset: `{'signal_engine', 'data_fetcher', 'notifier', 'main', 'numpy', 'pandas', 'yfinance', 'requests', 'schedule', 'dotenv'}`

`DASHBOARD_PATH = Path('dashboard.py')` only — the AST gate currently scans only `dashboard.py`, NOT `dashboard_renderer/` files. [VERIFIED]

After Phase 32:
- The gate continues to scan `dashboard.py` (the shim). No changes needed to the gate itself.
- `dashboard_renderer/` files are not in the forbidden-imports test scope — they do not need to be added (they are I/O hex peers, not pure-math hex).
- However, new `dashboard_renderer/` files must not introduce forbidden imports at module top (hex boundary). The planner should add a verification step confirming new files comply.

### `test_forbidden_imports_absent` (test_signal_engine.py:932)

This test parametrizes only over `DASHBOARD_PATH` for dashboard-specific checks. It will continue to pass as long as the thinned `dashboard.py` shim does not introduce forbidden module-top imports.

Note: `dashboard.py` line 39 imports `os` explicitly as a monkeypatch surface. After thinning, `os` must be kept in the shim OR the test patching `dashboard.os.replace` must change to `dashboard_renderer.io.os.replace`. The research recommends removing `import os` from the shim and updating the two atomic-write tests in `TestAtomicWrite` to patch `dashboard_renderer.io.os.replace`.

### `tests/test_html_xss_audit.py`

Imports three symbols from `dashboard`: `_render_drift_banner`, `_render_paper_trades_closed`, `_render_paper_trades_open`. After port these move to `components/positions.py` and `components/paper_trades.py`. The XSS escape discipline (`html.escape(value, quote=True)`) must be preserved in the absorbed code — all three functions contain `html.escape(..., quote=True)` call sites. [VERIFIED: grep in session]

The AST gate in `test_html_xss_audit.py` scans by calling the render functions and asserting escaped output — it is NOT a file-path scan. No test path changes needed beyond the import line updates.

---

## Critical Finding: Dead `shell.render_html_shell`

`dashboard_renderer/shell.py::render_html_shell` (line 167, 204 LOC total in file) is **never called in any production or test path**. [VERIFIED: grep -rn "render_html_shell" all .py files]

The active HTML shell is `dashboard_legacy/page_body._render_html_shell`. The golden tests lock its output (which includes `_DETAILS_ARIA_SYNC_JS` but NOT `_AWST_COUNTDOWN_JS`, `_STATUS_STRIP_REFRESH_JS`, or `_TABS_KEYBOARD_JS`). [VERIFIED: grep of golden.html for `_awstNext0800Utc` → 0 matches]

After absorption:
- `shell.render_html_shell` body is **replaced** with the content of `page_body._render_html_shell`.
- `api._render_header_and_body` is updated: `d._render_html_shell(ctx, body)` → `from dashboard_renderer.shell import render_html_shell; render_html_shell(ctx, body)`.
- The existing `_AWST_COUNTDOWN_JS`, `_STATUS_STRIP_REFRESH_JS`, `_TABS_KEYBOARD_JS` constants stay in `shell.py` (they are used by the status strip and nav components) but are NOT included in the `render_html_shell` body. The function comment is updated to reflect this.

**Risk:** If `shell.render_html_shell` was intended to be the canonical implementation and the missing scripts are a bug, Phase 32 should NOT fix that — it is out of scope (no functional changes). The port must preserve byte-identical output.

---

## Wave Decomposition

Wave ordering based on dependency constraints:

### Wave 0: Scaffold new files + audit

Independent (no ordering constraint among Wave 0 tasks):
- Create `dashboard_renderer/components/trace.py` (empty scaffold with imports)
- Create `dashboard_renderer/components/calc_rows.py` (empty scaffold)
- Create `dashboard_renderer/components/account.py` (empty scaffold)
- Audit each `dashboard_legacy/` module against its target — document exact function-by-function coverage gaps

### Wave 1: Absorb leaf modules (no dependencies between tasks in Wave 1)

The leaf modules have no intra-legacy dependencies:
- `render_helpers.py` → `formatters.py` (unique helpers) + `stats.py` (stat wrappers) — **must land before Wave 2** because api.py + pages.py deferred imports call `d._resolve_strategy_version` etc.
- `trace_panels.py` → `components/trace.py` — independent
- `calc_rows.py` → `components/calc_rows.py` — independent
- `account_section.py` → `components/account.py` — independent

### Wave 2: Absorb compositor modules (depend on Wave 1 content existing)

Ordering within Wave 2:
1. `paper_trades_section.py` → `components/paper_trades.py` — depends on Wave 1 stats (compute_aggregate_stats must exist in stats.py)
2. `positions_section.py` → `components/positions.py` — depends on Wave 1 calc_rows (entry_target_row must exist)
3. `section_renderers.py` → `components/header.py` (signout, session_note, equity chart) — independent of Wave 2 order

### Wave 3: Eliminate circular imports

Must happen after Wave 1+2 content is in place:
- `dashboard_renderer/api.py`: replace all `import dashboard as d` deferred imports with direct module imports
- `dashboard_renderer/pages.py`: replace `import dashboard as d` with `from dashboard_renderer.shell import _render_page_body, _render_single_page_dashboard`
- `dashboard_renderer/components/paper_trades.py`: replace `import dashboard as d` with direct imports
- `dashboard_renderer/components/positions.py`: replace `import dashboard as d` with direct imports

### Wave 4: page_body absorption + shell replacement

Must happen after Wave 3 (circular imports eliminated):
- Absorb `_render_page_body` 5-tuple fn, `_render_tabbed_dashboard`, `_render_single_page_dashboard` into `shell.py`
- Replace `shell.render_html_shell` body with `page_body._render_html_shell` content
- Delete `_atomic_write_html` wrapper from page_body path (callers already use `io.atomic_write_html`)

### Wave 5: dashboard.py shim thinning

Must happen after Wave 3+4:
- Remove all `from dashboard_legacy.*` re-exports (lines 126-213)
- Remove `import os` (or keep with comment explaining monkeypatch surface — see test update)
- Remove `from dashboard_renderer.assets import _CHARTJS_SRI` etc. (only if no callers need these via `dashboard.*`)
- Shim retains: `render_dashboard_files`, `render_dashboard_page`, `render_dashboard` alias, `logger`, CLI `__main__` block — must reach ≤100 LOC

### Wave 6: Retire dashboard_legacy/ + update callers + update tests

Must happen after Wave 5:
- Delete `dashboard_legacy/render_helpers.py`, `section_renderers.py`, `page_body.py`, `positions_section.py`, `calc_rows.py`, `paper_trades_section.py`, `account_section.py`, `trace_panels.py`
- Replace `dashboard_legacy/__init__.py` with ImportError stub
- Update all test import paths (test_dashboard.py, test_web_dashboard.py, test_html_xss_audit.py, test_notifier.py, test_trace_atr_seed.py, test_trace_vote_params.py)
- Update web route imports: `web/routes/dashboard/__init__.py`, `web/routes/dashboard/_renderers.py`, `web/routes/markets.py`, `web/routes/paper_trades/__init__.py`
- Update `tests/test_dashboard_split_seam.py::test_dashboard_files_under_500_loc` to expect ImportError stub
- Update `tests/test_dashboard.py::TestAtomicWrite` patches from `dashboard.os.replace` to `dashboard_renderer.io.os.replace`
- Update `web/app.py` docstring reference to `dashboard_legacy/`

### Wave 7: Integration gate

- Full test suite green (`pytest -x --tb=short`)
- LOC audit: all new files ≤500 LOC
- `git grep "dashboard_legacy"` returns zero matches outside quarantine markers and ROADMAP
- `dashboard.py` is ≤100 LOC
- Golden snapshot unchanged

---

## Common Pitfalls

### Pitfall 1: Golden drift from shell replacement

**What goes wrong:** `shell.render_html_shell` has `_AWST_COUNTDOWN_JS`, `_STATUS_STRIP_REFRESH_JS`, `_TABS_KEYBOARD_JS` in its body. If the absorbed version includes these, golden tests fail because `golden.html` was captured with only `_DETAILS_ARIA_SYNC_JS`.
**Why it happens:** Two competing implementations existed; the dead one had more scripts.
**How to avoid:** Replace `render_html_shell` body verbatim with `page_body._render_html_shell` content. The extra JS constants stay in `shell.py` but are not emitted by the function.
**Warning signs:** `TestGoldenSnapshot::test_golden_snapshot_matches_committed` fails on first run.

### Pitfall 2: `_render_page_body` annotation lies

**What goes wrong:** `_render_page_body` is annotated `-> str` but actually returns a 5-tuple `(section_id, heading_id, heading_text, heading_cls, render_fn)`. If absorbed with the wrong return type annotation, type checkers and future readers are misled.
**How to avoid:** Fix the annotation to `-> tuple[str, str, str, str, Callable[[], str]]` when absorbing into `shell.py`.

### Pitfall 3: `dashboard.os.replace` monkeypatch breaks

**What goes wrong:** Tests `TestAtomicWrite::test_crash_on_os_replace_leaves_original_intact` and `test_tempfile_cleaned_up_on_failure` patch `dashboard.os.replace`. After `import os` is removed from `dashboard.py`, these patches have no effect and the tests silently pass without testing anything.
**Why it happens:** `patch('dashboard.os.replace')` patches the `os` module object via dashboard's namespace; when `import os` is gone from dashboard, the patch target doesn't exist.
**How to avoid:** Change patches to `patch('dashboard_renderer.io.os.replace', ...)` in Wave 6.
**Warning signs:** No test failure — the test passes but the assertion is vacuous. Add an assertion that the render call actually raises OSError to confirm the patch works.

### Pitfall 4: C-2 local imports in calc_rows and positions_section

**What goes wrong:** `calc_rows.py` and `positions_section.py` use `from sizing_engine import get_trailing_stop` and `from sizing_engine import calc_position_size` as LOCAL function-body imports (C-2 pattern). If absorbed as module-top imports, the AST gate `test_dashboard_no_module_top_sizing_engine_import` fails.
**How to avoid:** Preserve all sizing_engine imports as local (function-body) imports in the new component files. The `# LOCAL — C-2` comment must be preserved.

### Pitfall 5: `_render_page_body` call interface is a 5-tuple consumer chain

**What goes wrong:** Three files call `_render_page_body`: `page_body._render_tabbed_dashboard` (wave 4, same file), `page_body._render_single_page_dashboard` (wave 4, same file), and `dashboard_renderer/pages.py::render_panel_only` (line 38). If `_render_page_body` is absorbed into `shell.py` but `pages.py` is not updated simultaneously, `pages.py` will fail to import.
**How to avoid:** Wave 4 updates both `shell.py` (adds `_render_page_body`) and `pages.py` (updates import) in the same task.

### Pitfall 6: `_render_equity_chart_container` is unique and belongs in a component

**What goes wrong:** `_render_equity_chart_container` (section_renderers.py:140, ~90 LOC) has no home in `dashboard_renderer/`. It is called by `page_body._render_tabbed_dashboard` via `_render_signal_cards` composition. If omitted, the equity chart section disappears.
**How to avoid:** Port to `components/header.py` (fits within projected 283 LOC) together with `_distinct_equity_tuples`.

### Pitfall 7: `_SIGNAL_LABEL`, `_SIGNAL_COLOUR`, `_EXIT_REASON_DISPLAY`, `_TRACE_FORMULAS`, `_SEED_LENGTHS` constants

**What goes wrong:** These dicts are re-exported through `dashboard.py` and used by callers. They must land in `dashboard_renderer/formatters.py` and be importable from there.
**How to avoid:** Include constants (not just functions) in the formatters absorption step.

---

## Validation Architecture

### Gate 1: Byte-identity golden snapshots

**What it tests:** `dashboard.render_dashboard(state, now=FROZEN_NOW)` produces byte-identical HTML to committed baseline.

**Tests:**
- `tests/test_dashboard.py::TestEmptyState::test_empty_state_matches_golden_empty_html` — `golden_empty.html`
- `tests/test_dashboard.py::TestGoldenSnapshot::test_golden_snapshot_matches_committed` — `golden.html`
- `tests/test_dashboard_split_seam.py::test_dashboard_html_output_byte_identical` — `dashboard_canonical.html`

**Run command:** `.venv/bin/pytest tests/test_dashboard.py::TestEmptyState tests/test_dashboard.py::TestGoldenSnapshot tests/test_dashboard_split_seam.py::test_dashboard_html_output_byte_identical -x --tb=short`

**Gate status:** Must remain green throughout each wave. If they fail after a wave, do not proceed to next wave.

**Regeneration:** If output legitimately changes (it should NOT for this phase), run `python tests/regenerate_dashboard_golden.py` and commit updated golden files.

### Gate 2: AST hex boundary gate

**What it tests:** `dashboard.py` (and the pure-math hex files) do not import forbidden modules at module top.

**Test:** `tests/test_signal_engine.py::TestDeterminism::test_dashboard_no_forbidden_imports`

**Run command:** `.venv/bin/pytest tests/test_signal_engine.py::TestDeterminism::test_dashboard_no_forbidden_imports -x --tb=short`

**Additional check:** `tests/test_signal_engine.py::TestDeterminism::test_dashboard_no_module_top_sizing_engine_import` — verifies sizing_engine is only C-2 local in dashboard.py.

**Post-port:** The thinned `dashboard.py` shim must not introduce forbidden module-top imports. New `dashboard_renderer/` component files with C-2 local sizing_engine imports are not scanned by this gate (only `dashboard.py` is parametrized).

### Gate 3: XSS escape gate

**What it tests:** Dynamic values flowing through render functions use `html.escape(value, quote=True)`.

**Test file:** `tests/test_html_xss_audit.py`

**Run command:** `.venv/bin/pytest tests/test_html_xss_audit.py -x --tb=short`

**Post-port:** Three symbols imported from `dashboard` must be updated to new paths. The underlying functions must preserve all `html.escape(..., quote=True)` call sites verbatim.

### Gate 4: Import-chain gate (dashboard_legacy quarantine)

**What it tests:** No live code path imports from `dashboard_legacy/`.

**Command:** `git grep "from dashboard_legacy\|import dashboard_legacy" -- "*.py" | grep -v "dashboard_legacy/__init__.py"`

**Expected output after Wave 6:** Zero matches (the stub `__init__.py` itself is exempt).

**Supplementary test:** The `ImportError` stub in `dashboard_legacy/__init__.py` must be verified by adding a test that `import dashboard_legacy.render_helpers` raises `ImportError` with the expected message.

### Gate 5: dashboard.py shim LOC gate

**What it tests:** `dashboard.py` ≤100 LOC.

**Command:** `wc -l dashboard.py` — must print ≤100.

**Test:** `tests/test_signal_engine.py` 2-space indent check covers `dashboard.py` (line 1066). LOC gate is manual.

### Gate 6: Full suite green

**What it tests:** No regressions anywhere.

**Run command:** `.venv/bin/pytest -x --tb=short`

**When:** After each wave (not just at end).

---

## Environment Availability

Step 2.6: All required tools are present in the project venv. No external dependencies.

| Dependency | Required By | Available | Version |
|------------|------------|-----------|---------|
| pytest | Test gates | ✓ | 8.3.3 |
| Python | Runtime | ✓ | 3.13.13 |
| pytz | dashboard_renderer/api.py | ✓ (project dep) | — |

No missing dependencies.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `_render_equity_chart_container` has no counterpart in `dashboard_renderer/` | Module Inventory | Low — grep confirmed; if wrong, D-03 audit step catches overlap before porting |
| A2 | LOC estimates for unique content (e.g., "~90 LOC for `_render_open_form`") are approximate | LOC census table | Low — planner must re-measure before committing to file splits; D-02 cap is the hard constraint |
| A3 | `shell.render_html_shell` (with 4 scripts) was never the active path | Critical Finding section | MEDIUM — if it was called somewhere not found by grep, byte-identity gate surfaces it immediately |

---

## Open Questions

1. **`_render_page_body` return type annotation**
   - What we know: annotated `-> str` but returns a 5-tuple
   - What's unclear: whether fixing the annotation is in scope for Phase 32
   - Recommendation: fix it during absorption (zero behaviour change, improves correctness)

2. **`logger = logging.getLogger('dashboard')` placement after shim thinning**
   - What we know: CONTEXT.md marks this as Claude's discretion; must stay in `dashboard.py` for journalctl continuity
   - Recommendation: keep in `dashboard.py` shim; components that currently use `logging.getLogger('dashboard')` (render_helpers.py line 34) must be updated to use their own `__name__` logger in `dashboard_renderer.*`

3. **`_TraceOpenPlaceholderMap` class placement**
   - What we know: it lives in `render_helpers.py` and is used by `_TRACE_OPEN_PLACEHOLDER`; its `.get()` method is called in `trace_panels.py`
   - Recommendation: move to `formatters.py` alongside the other render helpers; `trace.py` imports it from there

---

## Sources

### Primary (HIGH confidence)
- Codebase: `dashboard_legacy/*.py`, `dashboard_renderer/*.py`, `dashboard.py` — read directly in this session
- Codebase: `tests/test_signal_engine.py` lines 568–590, 932–954 — AST gate frozenset + test parametrization
- Codebase: `tests/test_html_xss_audit.py` lines 1–40 — XSS gate structure
- Codebase: `tests/test_dashboard.py` — golden test classes + atomic write test patches
- Codebase: `tests/test_dashboard_split_seam.py` — split parity assertions
- Codebase: `tests/fixtures/dashboard/golden.html` — confirmed absence of `_awstNext0800Utc` (dead shell confirmed)
- Codebase: `dashboard_renderer/io.py` — `os.replace` actual location

### Secondary (MEDIUM confidence)
- `.planning/phases/32-dashboard-legacy-retirement/32-CONTEXT.md` — locked decisions D-01 through D-06

---

## Metadata

**Confidence breakdown:**
- Module inventory + LOC: HIGH — read directly from source
- Circular import map: HIGH — traced all `import dashboard as d` sites exhaustively
- Caller audit: HIGH — grep confirmed all production callers
- Test gate inventory: HIGH — grep confirmed all test symbol imports
- LOC projections: MEDIUM — estimates from function body reading; planner must re-measure before finalising splits
- Dead shell finding: HIGH — confirmed by golden.html grep + grep of all .py callers

**Research date:** 2026-05-12
**Valid until:** 2026-06-12 (stable codebase; refactor-only phase)
