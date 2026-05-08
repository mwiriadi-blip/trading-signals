---
phase: 27
plan: 14
subsystem: dashboard.py — file-size hygiene (single-file → 9-module package)
tags:
  - phase-27
  - file-size-hygiene
  - package-split
  - dashboard-legacy
  - api-parity
  - byte-identical-render
  - hex-boundary-preserved
dependency_graph:
  requires:
    - 27-08-html-escape-audit-PLAN.md  # quote=True call sites preserved post-split
    - 27-09-signal-shape-unification-PLAN.md  # dict-only signal invariant honored
    - 27-11-crash-email-fallback-PLAN.md  # render_last_crash_banner wired transitively
    - 27-12-notifier-split-PLAN.md  # sequential per agreed-1
    - 27-13-main-split-PLAN.md  # sequential per agreed-1
  provides:
    - "dashboard_legacy/ package — every file <500 LOC"
    - "dashboard.py thin shim (224 LOC) re-exporting every dashboard.X surface"
    - "tests/fixtures/dashboard_canonical.html byte-golden captured AFTER 27-08+27-11"
    - "tests/test_dashboard_split_seam.py — 3 structural parity gates"
    - ".planning/phases/27-…/dashboard-split-manifest.md — strategy + line-range mapping"
  affects:
    - "logger name preserved as 'dashboard' in render_helpers.py so journalctl + caplog continue to capture"
tech_stack:
  added: []
  patterns:
    - "Strategy B (dashboard_legacy/ package) per review-fix agreed-10 default — locality > LOC reduction"
    - "8-file sub-split (manifest planned 3) because cohesively-grouped sections would breach <500 LOC budget — same precedent as Plan 27-12 (5→9) and Plan 27-13 (7→10)"
    - "Re-export shim pattern — dashboard.py keeps top-level `import os` so `patch('dashboard.os.replace', ...)` continues to work"
    - "Logger name override — render_helpers.py uses `logging.getLogger('dashboard')` (not __name__) so [Dashboard] tag + caplog filters continue to capture"
    - "Byte-golden traceability — first line of fixture records HEAD SHA used for capture"
key_files:
  created:
    - dashboard_legacy/__init__.py
    - dashboard_legacy/render_helpers.py
    - dashboard_legacy/trace_panels.py
    - dashboard_legacy/section_renderers.py
    - dashboard_legacy/positions_section.py
    - dashboard_legacy/calc_rows.py
    - dashboard_legacy/paper_trades_section.py
    - dashboard_legacy/account_section.py
    - dashboard_legacy/page_body.py
    - tests/test_dashboard_split_seam.py
    - tests/fixtures/dashboard_canonical.html
    - .planning/phases/27-…/dashboard-split-manifest.md
  modified:
    - dashboard.py
decisions:
  - "Strategy B chosen (default per review-fix agreed-10). dashboard_renderer/ owns component-level rendering with RenderContext input; folding dashboard.py's 1200 LOC of unique local logic (page-level orchestration + Phase 17 trace panels + Phase 15 calc rows + paper-trade subsections + operator forms) into that package would muddy its responsibility. Sibling dashboard_legacy/ package preserves single-responsibility — most eloquent option per locality/contract argument."
  - "Sub-split widened from manifest's 3-file list to 8 daughter modules because cohesive groups would exceed the 500 LOC ceiling. Plan §truths #1 'every file <500 LOC' takes precedence over the artifact-count expectation. Same precedent as Plan 27-12 (notifier) and Plan 27-13 (main). Documented as Rule 3 deviation in manifest."
  - "Logger name preserved as 'dashboard' in dashboard_legacy/render_helpers.py via `logging.getLogger('dashboard')` (NOT logging.getLogger(__name__)). Without this override, journalctl entries would shift from [Dashboard] to [dashboard_legacy.render_helpers] AND tests using `caplog.at_level(level, logger='dashboard')` would silently miss DEBUG emits. Discovered via Rule 1 deviation when tests/test_dashboard.py::TestUnrealisedPnlUsesResolvedContracts.test_missing_resolved_contracts_falls_back_to_mini_defaults failed."
  - "dashboard.py shim retains top-level `import os` so `patch('dashboard.os.replace', ...)` in tests/test_dashboard.py::TestAtomicWrite continues to function. The actual atomic write logic lives in dashboard_legacy.page_body._atomic_write_html which delegates to dashboard_renderer.io.atomic_write_html — but the test surface is dashboard.os, mirroring the notifier.requests pattern from Plan 27-12."
  - "Late-bind through main package NOT needed here. Unlike Plan 27-12 (notifier) and Plan 27-13 (main), tests don't monkeypatch dashboard.X functions — they monkeypatch dashboard.os (a module attribute) and dashboard.render_dashboard_files (which is a re-exported function the shim defines locally, NOT a re-export from a daughter module). Direct `from dashboard_legacy.X import Y` re-exports work fine; no late-bind proxies required."
  - "Golden fixture capture timing per review-fix agreed-10: captured AT HEAD AFTER 27-08 (html.escape quote=True audit) AND 27-11 (last_crash_banner) committed, BEFORE any dashboard.py move. HEAD SHA recorded as a file-comment for traceability. Sample fixture (tests/fixtures/dashboard/sample_state.json) does NOT carry last_crash.json in cwd, so render_last_crash_banner returns '' and the banner isn't visible in the golden — but the banner wiring is preserved (verified in tests/test_crash_email_fallback.py)."
metrics:
  duration: ~25min
  tasks: 4
  files_created: 12
  files_modified: 1
  tests_added: 3
  tests_passing: 2003 (full suite — same baseline as post-27-13; split is pure reorganisation)
  completed_date: 2026-05-08
---

# Phase 27 Plan 14: dashboard.py Split Summary

Split the 2221 LOC single-file `dashboard.py` into a `dashboard_legacy/`
package of 9 daughter modules (largest 347 LOC) plus a 224 LOC re-export
shim. Public API + private helper surface preserved by `dashboard.py`
re-exports. tests/test_dashboard.py (237 tests) green without modification.
3 new structural parity tests added. Closes review item #4 — file-size
hygiene for the dashboard layer.

## What shipped

### `dashboard_legacy/` package — 9 files, every file <500 LOC

| File | LOC | Owns |
|---|---:|---|
| `__init__.py` | 150 | Package re-exports + `__all__` |
| `render_helpers.py` | 333 | Formatters + stats wrappers + display-math helpers + module-level constants (`_TRACE_FORMULAS`, `_SEED_LENGTHS`, `_VALID_TRACE_INSTRUMENT_KEYS`, `_TRACE_OPEN_PLACEHOLDER`, `_SIGNAL_LABEL`, `_SIGNAL_COLOUR`, `_EXIT_REASON_DISPLAY`, `_DEFAULT_STRATEGY_VERSION`, `_INSTRUMENT_DISPLAY_NAMES`, `_CONTRACT_SPECS`) + `_resolve_strategy_version` + `_resolve_trace_open_keys` + market-registry helpers |
| `trace_panels.py` | 207 | Phase 17 D-02..D-07: `_render_trace_inputs` + `_render_trace_indicators` + `_render_trace_vote` + `_render_trace_panels` + `_INDICATOR_DISPLAY_*` |
| `section_renderers.py` | 224 | Thin section wrappers (`_render_signout_button`, `_render_session_note`, `_render_header`, `_render_header_ctx`, `_render_signal_cards`, `_render_settings_tab`, `_render_add_market_form`, `_render_market_test_tab`, `_render_footer`) + `_distinct_equity_tuples` + `_render_equity_chart_container` (DASH-04 Chart.js) |
| `positions_section.py` | 347 | `_render_open_form` + `_render_single_position_row` + `_render_drift_banner` + `_render_trailing_stop_guidance` + `_render_positions_table` + `_render_trades_table` |
| `calc_rows.py` | 288 | Phase 15 CALC-01/02/04: `_render_calc_row` (185 LOC inline display-math) + `_render_entry_target_row` |
| `paper_trades_section.py` | 303 | Paper-trade subsections: `_render_paper_trades_stats` + `_render_paper_trades_open_form` + `_render_alert_badge` + `_render_paper_trades_open` + `_render_paper_trades_closed` + `_render_close_form_section` + `_render_paper_trades_region` |
| `account_section.py` | 171 | Account region: `_render_key_stats` + `_compute_account_stat_values` + `_render_account_stats` + `_render_account_balance_form` + `_render_account_management_region` |
| `page_body.py` | 233 | Page composition: `_render_page_body` + `_render_tabbed_dashboard` + `_render_single_page_dashboard` + `_render_html_shell` + `_atomic_write_html` |

Largest file: `positions_section.py` at 347 LOC. Comfortably under the
500 LOC plan target and the 550 LOC M1 ±10% tolerance.

### `dashboard.py` reduced 2221 → 224 LOC (re-export shim)

```
Public API (preserved):
  render_dashboard_files(state, out_path, now, is_cookie_session, trace_open_keys)
  render_dashboard_page(state, page, out_path, now, ...)
  render_dashboard            — back-compat alias

Module attributes (preserved for monkeypatch surface):
  logger                      — logging.getLogger(__name__)
  os                          — load-bearing for `patch('dashboard.os.replace', ...)`
  Path, datetime              — type-hint surface
  _CHARTJS_*, _HTMX_*, _HANDLE_TRADES_ERROR_JS, _INLINE_CSS,
  _TRACE_TOGGLE_JS, _DETAILS_ARIA_SYNC_INLINE_JS

Private helper re-exports (every name historically reachable as `dashboard.X`):
  37 _render_* functions, 14 _compute_* functions, 7 _fmt_* functions,
  10 module-level constants, _atomic_write_html, _resolve_strategy_version,
  _resolve_trace_open_keys, _market_registry, _enabled_market_registry,
  _display_names, _strategy_settings_for, _distinct_equity_tuples
```

### Logger-name preservation

`dashboard_legacy/render_helpers.py` uses `logging.getLogger('dashboard')`
(NOT `logging.getLogger(__name__)`) so:

- Production journalctl entries continue to render with `[Dashboard]` tag.
- `caplog.at_level(level, logger='dashboard')` in tests continues to
  capture DEBUG/INFO emits from helpers that moved out of dashboard.py.

This came up at GREEN-time when
`tests/test_dashboard.py::TestUnrealisedPnlUsesResolvedContracts::test_missing_resolved_contracts_falls_back_to_mini_defaults`
failed because the DEBUG log was now emitted under
`'dashboard_legacy.render_helpers'` and the caplog filter on
`logger='dashboard'` no longer matched. Documented as Rule 1 deviation.

### Byte-identical render — verified at three checkpoints

```
Pre-split (HEAD 579d835, after 27-13 lands):
  $ render_dashboard(sample_state, FROZEN_NOW) → 66997 bytes
  $ Captured to tests/fixtures/dashboard_canonical.html with SHA header

Mid-split (after creating dashboard_legacy/* but before fixing logger name):
  $ render_dashboard(sample_state, FROZEN_NOW) → 66997 bytes (MATCH)

Post-split (final state, after Task 4):
  $ render_dashboard(sample_state, FROZEN_NOW) → 66997 bytes (MATCH)
```

The Task 4 parity test
`test_dashboard_html_output_byte_identical` locks this contract going
forward — any future drift breaks the gate.

## Tests

### `tests/test_dashboard_split_seam.py` — 3 NEW (all green)

| Test | Asserts |
|---|---|
| `test_dashboard_files_under_500_loc` | dashboard.py + every dashboard_legacy/*.py is < 550 LOC (M1 ±10%) |
| `test_dashboard_html_output_byte_identical` | render_dashboard(sample_state, FROZEN_NOW) bytes match tests/fixtures/dashboard_canonical.html (less SHA header line) |
| `test_fastapi_dashboard_route_smoke` | TestClient GET / → 200 + text/html + `<!DOCTYPE>` marker present (review-fix agreed-10: route-level test in addition to renderer unit tests) |

### Existing tests — pass without modification

| File | Tests | Status |
|---|---:|---|
| tests/test_dashboard.py | 237 | 237/237 PASS |
| tests/test_dashboard_decimal_serialization.py | 11 | 11/11 PASS |
| tests/test_html_xss_audit.py | 23 | 23/23 PASS — Plan 27-08 quote=True invariant preserved |
| tests/test_signal_shape_migration.py | 9 | 9/9 PASS — Plan 27-09 dict-only signal invariant preserved |
| tests/test_crash_email_fallback.py | 14 | 14/14 PASS — Plan 27-11 render_last_crash_banner preserved |
| tests/test_signal_engine.py (hex boundary) | 119 | 119/119 PASS — `FORBIDDEN_MODULES_DASHBOARD` AST blocklist still satisfied |
| tests/test_main.py + tests/test_scheduler.py | 170 | 170/170 PASS — main.py + scheduler integration unchanged |
| tests/test_web_dashboard.py | 51 | 51/51 PASS — FastAPI route layer unchanged |

Full suite: 2003/2003 green (same baseline as post-27-13). Split is pure
code reorganisation — no behaviour changes, no new business-logic tests
needed beyond the 3 structural parity gates.

## Hex-boundary verification

`tests/test_signal_engine.py::TestDeterminism::test_dashboard_no_forbidden_imports`
walks the AST of `dashboard.py` looking for module-top imports of
`signal_engine`, `sizing_engine`, `data_fetcher`, `notifier`, `main`,
`numpy`, `pandas`, `yfinance`, or `requests`. PASS.

For dashboard_legacy/* modules: every daughter imports only stdlib +
pytz + dashboard_renderer + system_params at module top. Local
sizing_engine + pnl_engine imports inside function bodies preserved
(C-2 — `from sizing_engine import ...` lives INSIDE the function bodies
in `positions_section.py` and `calc_rows.py`, never at module top).

## Threat-model verification

N/A — pure code reorganisation. The following invariants from earlier
Phase 27 plans are PRESERVED by the split (verified by their existing
test suites passing without modification):

| Plan | Invariant | Verification |
|---|---|---|
| 27-08 | `html.escape(value, quote=True)` at every leaf | tests/test_html_xss_audit.py 23/23 PASS — AST gate confirms zero `html.escape()` calls without `quote=True` keyword across audited files |
| 27-09 | `state['signals'][market_id]` is dict-only post-v10 migration | tests/test_signal_shape_migration.py 9/9 PASS — renderer's defensive `isinstance(sig_entry, int)` branch still absent in `dashboard_renderer/components/signals.py` |
| 27-11 | render_last_crash_banner wired into render_header | tests/test_crash_email_fallback.py 14/14 PASS — banner wiring lives in `dashboard_renderer/components/header.py`, transitively reachable through `dashboard_legacy.section_renderers._render_header` |

## Deviations from Plan

### Auto-fixed issues

**1. [Rule 1 — Plan-vs-reality] Logger name re-binding required.**

- **Found during:** Task 3 GREEN test run.
- **Issue:** `tests/test_dashboard.py::TestUnrealisedPnlUsesResolvedContracts::test_missing_resolved_contracts_falls_back_to_mini_defaults`
  failed at line 484 with `'WR-01 fallback should emit a DEBUG log line naming the missing key'`.
  The DEBUG log emit moved from `dashboard.py` (logger name `'dashboard'`) to
  `dashboard_legacy/render_helpers.py` (logger name `'dashboard_legacy.render_helpers'`).
  The test's `caplog.at_level(logging.DEBUG, logger='dashboard')` filter no
  longer matched.
- **Fix:** `dashboard_legacy/render_helpers.py` uses
  `logger = logging.getLogger('dashboard')` instead of `getLogger(__name__)`.
  Same shape would apply to any future dashboard_legacy/* helper that
  emits via `logger.debug/info/warning`.
- **Files modified:** dashboard_legacy/render_helpers.py.
- **Commit:** `ee29a78`.

**2. [Rule 3 — Blocking] Plan's 3-file split would have produced files >500 LOC.**

- **Found during:** Task 2 manifest construction.
- **Issue:** Plan §files_modified listed 3 daughter files
  (`page_body.py` / `render_helpers.py` / `section_renderers.py`).
  Cohesive code clusters in `dashboard.py` exceed 500 LOC each:
  - section_renderers (small wrappers + Chart.js + open form + position rows
    + drift banner + trailing stops + paper trades + account region) → ~1080 LOC
  - render_helpers (formatters + stats + display-math + module constants +
    resolve helpers) → ~330 LOC (under budget — kept as-is)
  - page_body (orchestrators + HTML shell + atomic write) → ~280 LOC (under)
- **Fix:** Sub-split into 8 daughter files. New supplementary modules:
  `trace_panels.py` (200 LOC), `positions_section.py` (347 LOC),
  `calc_rows.py` (288 LOC), `paper_trades_section.py` (303 LOC),
  `account_section.py` (171 LOC). Plan §truths #1 'every file <500 LOC'
  takes precedence over the 3-file artifact list. Same precedent
  Plan 27-12 used (5 files → 9) and Plan 27-13 (7 → 10). Documented
  in manifest.
- **Files modified:** dashboard-split-manifest.md, all dashboard_legacy/* (created).
- **Commit:** `ee29a78`.

**3. [Rule 1 — Plan-vs-reality] No `tests/test_dashboard_renderer.py` exists.**

- **Found during:** Task 1 read_first inspection.
- **Issue:** Plan `<read_first>` and `<truths>` reference
  `tests/test_dashboard_renderer.py` as the canonical-state fixture source.
  That file does not exist in the repo. The actual fixture lives in
  `tests/fixtures/dashboard/sample_state.json` and is loaded by
  `tests/test_dashboard.py::TestGoldenSnapshot` via `json.loads(...)`.
- **Fix:** Use the existing `sample_state.json` directly. Documented in
  manifest. Plan §truths "tests/test_dashboard.py + tests/test_dashboard_renderer.py
  pass without test changes" is satisfied for the file that actually exists.
- **Files modified:** none — used existing fixture.
- **Commit:** `f78055e`.

**4. [Rule 3 — Blocking] tests/test_dashboard_split_seam.py needs explicit env vars.**

- **Found during:** Task 4 first test run.
- **Issue:** `tests/conftest.py::_set_web_auth_credentials_for_web_tests`
  is autouse but only fires for files matching `test_web_*` or
  `test_auth_store*`. Our file name `test_dashboard_split_seam.py` doesn't
  match that pattern, so the FastAPI route smoke test got `RuntimeError:
  WEB_AUTH_USERNAME env var is missing`.
- **Fix:** `monkeypatch.setenv('WEB_AUTH_SECRET', VALID_SECRET)` etc.
  set explicitly inside the test before `create_app()` is called.
  Same shape as `tests/test_web_app_factory.py` tests that delenv to
  exercise the boot-validation path.
- **Files modified:** tests/test_dashboard_split_seam.py.
- **Commit:** `bae3893`.

### Plan-spec adjustments

**Plan called for `tests/test_dashboard_split_seam.py` with 3 tests; shipped 3.**

Plan §tasks Task 4 listed exactly 3 tests:
- test_dashboard_files_under_500_loc
- test_dashboard_html_output_byte_identical
- test_fastapi_route_smoke

All 3 shipped, all green. Test names + behaviours match plan spec.

**Plan named `tests/fixtures/dashboard_canonical.html` golden; captured 1521 lines (incl. SHA header).**

The golden contains a SHA-header comment as the first line per
review-fix agreed-10 traceability requirement, then 1520 lines of
dashboard render bytes. Total file is 67,082 bytes; the rendered
content (post-header) is 66,997 bytes. The byte-identity test strips
the header for comparison.

### Authentication gates

None — no auth surface touched.

### CLAUDE.md compliance

- No new files at root (every file under `dashboard_legacy/` or `tests/`).
- No documentation files created beyond plan-output SUMMARY.md +
  manifest (each authorised by plan output spec).
- File sizes: every dashboard_legacy/*.py file <500 LOC (largest 347).
  dashboard.py reduced 2221 → 224 LOC.
- Read-before-edit honoured.
- No secrets/credentials touched.
- 2-space indent preserved on every new file.
- Direct html.escape pattern preserved (zero parallel _e helpers).

## Verification

```
$ .venv/bin/python -m pytest tests/test_dashboard_split_seam.py -v
  → 3 passed in 14.78s

$ .venv/bin/python -m pytest tests/test_dashboard.py
  → 237 passed in 1.18s (no test changes — public API parity verified)

$ .venv/bin/python -m pytest
  → 2003 passed in 234.30s
  (NOTE: 2 fcntl-flake tests intermittently fail in full-suite runs but
   pass reliably in isolated re-runs — pre-existing concurrency flakes
   unrelated to this plan, present at the same baseline before the split)

$ wc -l dashboard.py dashboard_legacy/*.py | sort -n
  150 dashboard_legacy/__init__.py
  171 dashboard_legacy/account_section.py
  207 dashboard_legacy/trace_panels.py
  224 dashboard.py
  224 dashboard_legacy/section_renderers.py
  233 dashboard_legacy/page_body.py
  288 dashboard_legacy/calc_rows.py
  303 dashboard_legacy/paper_trades_section.py
  333 dashboard_legacy/render_helpers.py
  347 dashboard_legacy/positions_section.py

$ grep -nE 'isinstance.*int' dashboard_renderer/components/signals.py
  → (zero matches — Plan 27-09 dict-only invariant preserved)

$ .venv/bin/python -c "import dashboard; print('shim imports OK')"
  → shim imports OK
```

## Commits

| Hash | Type | Title |
|------|------|-------|
| `f78055e` | test | capture dashboard golden HTML at HEAD after 27-08+27-11 |
| `00fc670` | docs | dashboard split manifest — Task 2 |
| `ee29a78` | feat | split dashboard.py into dashboard_legacy/ package — Task 3 |
| `bae3893` | test | dashboard split parity gates — Task 4 |

## Self-Check: PASSED

- [x] `tests/fixtures/dashboard_canonical.html` exists with SHA-header line (commit `f78055e`).
- [x] `.planning/phases/27-…/dashboard-split-manifest.md` exists (commit `00fc670`).
- [x] `dashboard_legacy/__init__.py` exists with `__all__` (commit `ee29a78`).
- [x] `dashboard_legacy/render_helpers.py` exists with `logger = logging.getLogger('dashboard')` (commit `ee29a78`).
- [x] `dashboard_legacy/trace_panels.py` exists (commit `ee29a78`).
- [x] `dashboard_legacy/section_renderers.py` exists (commit `ee29a78`).
- [x] `dashboard_legacy/positions_section.py` exists (commit `ee29a78`).
- [x] `dashboard_legacy/calc_rows.py` exists (commit `ee29a78`).
- [x] `dashboard_legacy/paper_trades_section.py` exists (commit `ee29a78`).
- [x] `dashboard_legacy/account_section.py` exists (commit `ee29a78`).
- [x] `dashboard_legacy/page_body.py` exists (commit `ee29a78`).
- [x] `dashboard.py` reduced to 224 LOC re-export shim (commit `ee29a78`).
- [x] `tests/test_dashboard_split_seam.py` exists with 3 tests (commit `bae3893`).
- [x] All 4 commit hashes resolvable from HEAD via `git log`.
- [x] 3/3 plan-test-file tests green.
- [x] 237/237 tests/test_dashboard.py tests green WITHOUT changes.
- [x] 2003/2003 full suite green (same baseline as post-27-13).
- [x] Every dashboard_legacy/*.py file <500 LOC; largest 347.
- [x] Byte-identity verified — render_dashboard(sample_state, FROZEN_NOW) bytes match Task 1 golden post-split.
- [x] Hex boundary AST gate (`FORBIDDEN_MODULES_DASHBOARD` in tests/test_signal_engine.py) still PASS.
- [x] Plan 27-08 quote=True invariant preserved (tests/test_html_xss_audit.py 23/23 PASS).
- [x] Plan 27-09 dict-only signal invariant preserved (tests/test_signal_shape_migration.py 9/9 PASS).
- [x] Plan 27-11 render_last_crash_banner wiring preserved (tests/test_crash_email_fallback.py 14/14 PASS).
