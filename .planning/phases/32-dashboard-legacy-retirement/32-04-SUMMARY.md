---
phase: 32
plan: "04"
subsystem: dashboard
tags: [dashboard, legacy-retirement, import-guard, refactor, test-gate]
dependency_graph:
  requires: [32-01, 32-02, 32-03]
  provides: [dashboard-legacy-retirement-complete]
  affects: [dashboard.py, dashboard_legacy/, tests/test_dashboard.py, tests/test_dashboard_split_seam.py]
tech_stack:
  added: [sys.meta_path hook pattern for ImportError retirement guards]
  patterns: [hexagonal-lite I/O shim, ImportError retirement stub, LOC cap enforcement]
key_files:
  created: []
  modified:
    - dashboard.py
    - dashboard_legacy/__init__.py
    - tests/test_dashboard.py
    - tests/test_dashboard_split_seam.py
    - web/routes/dashboard/__init__.py
    - web/routes/dashboard/_renderers.py
    - web/routes/markets.py
    - web/routes/paper_trades/__init__.py
    - web/app.py
    - dashboard_renderer/components/header.py
    - tests/test_web_dashboard.py
    - tests/test_html_xss_audit.py
    - tests/test_notifier.py
    - tests/test_trace_atr_seed.py
    - tests/test_trace_vote_params.py
  deleted:
    - dashboard_legacy/account_section.py
    - dashboard_legacy/calc_rows.py
    - dashboard_legacy/page_body.py
    - dashboard_legacy/paper_trades_section.py
    - dashboard_legacy/positions_section.py
    - dashboard_legacy/render_helpers.py
    - dashboard_legacy/section_renderers.py
    - dashboard_legacy/trace_panels.py
decisions:
  - "sys.meta_path hook (_RetiredSubmoduleFinder) used over __path__=[] alone because Python 3.13 file-based packages raise ModuleNotFoundError (not ImportError) for submodule imports when __path__=[] is set — the meta_path hook intercepts before the module finder and raises ImportError with the locked message"
  - "dashboard.py thinned to 74 LOC pass-through shim; only public API (render_dashboard_files, render_dashboard_page, render_dashboard alias) retained; logger preserved as logging.getLogger('dashboard') for journalctl continuity"
  - "caplog logger target corrected from 'dashboard' to 'dashboard_renderer.stats' in test_dashboard.py — logs now emit from the canonical module, not the shim"
  - "_compute_unrealised_pnl_display (4-arg adapter) from dashboard_renderer.components.positions used in tests to bridge legacy 4-arg call sites to the canonical 5-arg stats version"
metrics:
  duration: "approx 4 hours (context across 2 sessions)"
  completed: "2026-05-12T13:22:23Z"
  tasks_completed: 5
  tasks_total: 5
  tests_passed: 1741
  tests_failed: 0
  pre_existing_failures: 1  # test_tampered_tsi_trusted_does_NOT_grant — unrelated auth test
---

# Phase 32 Plan 04: Dashboard Legacy Retirement Close-out Summary

**One-liner:** Thinned dashboard.py to 74-LOC I/O shim, replaced 8 dashboard_legacy submodule files with a single sys.meta_path ImportError guard, and retargeted all production + test callers to dashboard_renderer.* canonical paths.

## Tasks Completed

| Task | Description | Commit |
|------|-------------|--------|
| 1 | Retarget production callers to dashboard_renderer.* | d1b1eee |
| 2 | Retarget test callers; fix os.replace patch target | de334d0 |
| 3 | Update test_dashboard_split_seam.py for ImportError stub semantics | 3bfed55 |
| 4 | Thin dashboard.py shim; write ImportError stub; delete 7 legacy files | 60a0839 |
| 5 | Run 11 integration gate checks — all pass | (no separate commit; verification task) |

## What Changed

### Task 1 — Production caller retargeting

Five production files retargeted away from `from dashboard import _X`:

- `web/routes/dashboard/__init__.py` line 484: `_render_session_note`, `_render_signout_button` → `dashboard_renderer.components.header`
- `web/routes/dashboard/_renderers.py` line 94: `_fmt_currency`, `_fmt_em_dash` → `dashboard_renderer.formatters`
- `web/routes/markets.py`: `_render_account_management_region` → `dashboard_renderer.components.account`
- `web/routes/paper_trades/__init__.py` (5 sites): `_render_paper_trades_region` → `dashboard_renderer.components.paper_trades.render_paper_trades_region` (public name, no underscore)
- `web/app.py`: docstring updated

`dashboard_renderer/components/header.py` extended with `_render_signout_button()` and `_render_session_note()` ported from the retired `dashboard_legacy/section_renderers.py`.

### Task 2 — Test caller retargeting

`tests/test_dashboard.py`:
- Added comprehensive module-level imports from `dashboard_renderer.*` for all 122 occurrences of `dashboard._X` attribute access
- `patch('dashboard.os.replace', ...)` → `patch('dashboard_renderer.io.os.replace', ...)` (2 occurrences)
- `monkeypatch.setattr(dashboard, '_render_settings_tab', ...)` → `monkeypatch.setattr(_dr_settings, 'render_settings_tab', ...)`
- `caplog.at_level(logging.DEBUG, logger='dashboard')` → `logger='dashboard_renderer.stats'`
- `_render_to_str` helper: `d._render_tabbed_dashboard(ctx)` → `from dashboard_renderer.shell import _render_tabbed_dashboard`
- `_compute_unrealised_pnl_display` aliased from `dashboard_renderer.components.positions` (4-arg adapter)

`tests/test_web_dashboard.py`, `tests/test_html_xss_audit.py`, `tests/test_notifier.py`, `tests/test_trace_atr_seed.py`, `tests/test_trace_vote_params.py`: all `from dashboard import _X` imports retargeted to canonical `dashboard_renderer.*` paths.

### Task 3 — Split-seam test update

`tests/test_dashboard_split_seam.py::test_dashboard_files_under_500_loc` rewritten to assert:
- (a) Only `__init__.py` in `dashboard_legacy/`
- (b) Attribute access raises `ImportError` matching 'dashboard_legacy retired'
- (c) Subprocess submodule import raises `ImportError` (NOT `ModuleNotFoundError`)
- (d) dashboard.py ≤ 100 LOC
- (e) dashboard_renderer/*.py ≤ 500 LOC (assets.py exempt)

### Task 4 — Shim + stub + deletions

`dashboard.py`: rewritten from ~600 LOC rendering module to 74 LOC pass-through shim.

`dashboard_legacy/__init__.py`: single retirement stub with `sys.meta_path` hook:
```python
class _RetiredSubmoduleFinder:
  def find_spec(self, fullname, path, target=None):
    if fullname.startswith('dashboard_legacy.'):
      raise ImportError("dashboard_legacy retired — use dashboard_renderer")
    return None
```

8 legacy submodule files deleted: `account_section.py`, `calc_rows.py`, `page_body.py`, `paper_trades_section.py`, `positions_section.py`, `render_helpers.py`, `section_renderers.py`, `trace_panels.py`.

### Task 5 — Integration gate verification

All 11 gate checks passed (495 dashboard-related tests, 1741 total suite):
- `test_dashboard_split_seam.py` (3/3): LOC caps, byte-identical HTML, FastAPI route smoke
- `test_trace_vote_params.py` (5/5): vote_params locality gates
- `test_trace_atr_seed.py` (4/4): ATR seed exposure
- `test_trace_details_open_serverside.py` (7/7): trace detail server-side state
- `test_html_xss_audit.py`: XSS audit clean
- `test_web_dashboard.py` (93/93): full web dashboard suite

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocker] Worktree behind main — missing 32-01/02/03 content**
- **Found during:** Task 1 start
- **Issue:** Worktree HEAD was at pre-32-01 state; `dashboard_renderer/formatters.py` had 164 LOC (pre-migration), missing all underscore-prefixed symbols; `header.py` still had `import dashboard as d`
- **Fix:** `git stash && git merge main && git stash pop` to pull 32-01/02/03 commits into worktree
- **Files modified:** All dashboard_renderer/* files (via merge)

**2. [Rule 1 - Bug] Duplicate function definitions in header.py after merge**
- **Found during:** Task 1
- **Issue:** `_render_signout_button` and `_render_session_note` defined twice after stash-pop (short pre-stash version + full 32-01 version)
- **Fix:** Removed the shorter pre-merge stubs, kept the canonical 32-01 versions
- **Files modified:** `dashboard_renderer/components/header.py`

**3. [Rule 1 - Bug] Python 3.13 raises ModuleNotFoundError (not ImportError) for submodule imports when __path__=[]**
- **Found during:** Task 3/4
- **Issue:** `__path__ = []` on a file-based package doesn't route submodule imports to `__getattr__` in Python 3.13; Python raises `ModuleNotFoundError` before calling the package's `__getattr__`
- **Fix:** Added `_RetiredSubmoduleFinder` meta-path hook that intercepts `dashboard_legacy.*` import attempts and raises `ImportError` with the locked message before the standard module finder runs
- **Files modified:** `dashboard_legacy/__init__.py`

**4. [Rule 1 - Bug] caplog logger mismatch — logs moved from 'dashboard' to 'dashboard_renderer.stats'**
- **Found during:** Task 2
- **Issue:** `caplog.at_level(logging.DEBUG, logger='dashboard')` captured no logs after shim-thinning moved the logging to `dashboard_renderer.stats`
- **Fix:** Changed logger name to `'dashboard_renderer.stats'` in the test assertion
- **Files modified:** `tests/test_dashboard.py`

**5. [Rule 1 - Bug] compute_unrealised_pnl_display() signature mismatch**
- **Found during:** Task 2
- **Issue:** Canonical `stats.compute_unrealised_pnl_display` takes 5 args; legacy call sites passed 3-4 args
- **Fix:** Used `_compute_unrealised_pnl_display` (4-arg adapter) from `dashboard_renderer.components.positions` and aliased it as `compute_unrealised_pnl_display` in test imports
- **Files modified:** `tests/test_dashboard.py`

## Known Stubs

None — all data paths are wired to canonical `dashboard_renderer.*` implementations.

## Threat Flags

None — no new network endpoints, auth paths, or schema changes introduced.

## Self-Check: PASSED

- dashboard.py: 74 LOC (cap 100) — FOUND
- dashboard_legacy/__init__.py: ImportError stub — FOUND
- dashboard_legacy/: only __init__.py — CONFIRMED
- All dashboard_renderer/*.py ≤ 393 LOC (cap 500) — CONFIRMED
- Commits d1b1eee, de334d0, 3bfed55, 60a0839 — FOUND in git log
- 1741 tests passed — CONFIRMED
