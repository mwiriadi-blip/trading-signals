---
phase: 32
plan: "phase-summary"
subsystem: dashboard
tags: [dashboard, legacy-retirement, refactor, import-guard]
dependency_graph:
  requires: []
  provides: [dashboard-legacy-retirement-complete]
  affects: [dashboard.py, dashboard_legacy/, dashboard_renderer/, tests/, web/routes/]
tech_stack:
  patterns: [hexagonal-lite I/O shim, ImportError retirement stub, sys.meta_path hook, C-2 local imports, LOC cap enforcement]
key_files:
  created:
    - dashboard_renderer/components/trace.py
    - dashboard_renderer/components/calc_rows.py
    - dashboard_renderer/components/account.py
  modified:
    - dashboard_renderer/formatters.py
    - dashboard_renderer/stats.py
    - dashboard_renderer/shell.py
    - dashboard_renderer/components/header.py
    - dashboard_renderer/components/positions.py
    - dashboard_renderer/components/paper_trades.py
    - dashboard_renderer/api.py
    - dashboard_renderer/pages.py
    - dashboard_renderer/__init__.py
    - dashboard.py
    - dashboard_legacy/__init__.py
    - tests/test_dashboard.py
    - tests/test_dashboard_split_seam.py
    - tests/test_web_dashboard.py
    - tests/test_html_xss_audit.py
    - tests/test_notifier.py
    - tests/test_trace_atr_seed.py
    - tests/test_trace_vote_params.py
    - web/routes/dashboard/__init__.py
    - web/routes/dashboard/_renderers.py
    - web/routes/markets.py
    - web/routes/paper_trades/__init__.py
    - web/app.py
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
  - "sys.meta_path hook (_RetiredSubmoduleFinder) used in dashboard_legacy/__init__.py because Python 3.13 raises ModuleNotFoundError (not ImportError) for submodule imports when __path__=[] alone — the meta_path hook intercepts before the module finder"
  - "Wave-2 component imports (account, calc_rows, trace) in shell.py are lazy (function-body), not module-top — ensures import dashboard_renderer.shell succeeds before Wave 2 runs"
  - "logger = logging.getLogger('dashboard') preserved as literal string in dashboard.py for journalctl tag continuity — NOT __name__"
  - "render_paper_trades_region is PUBLIC (no underscore) in dashboard_renderer.components.paper_trades — legacy callers using _render_paper_trades_region (underscore) retargeted to the public name"
metrics:
  completed: "2026-05-12"
  plans: 4
  tests_passed: 2084
  tests_failed: 0
---

# Phase 32: Dashboard Legacy Retirement — Phase Summary

**One-liner:** Retired `dashboard_legacy/` by porting all unique render functions into canonical `dashboard_renderer/` homes, eliminating circular imports, thinning `dashboard.py` to a 74-LOC I/O shim, and replacing 8 legacy submodule files with a `sys.meta_path` ImportError guard. 2084 tests green; golden HTML byte-identical.

## Plans Completed

| Plan | What it built | Key outcome |
|------|---------------|-------------|
| 32-01 | Port render_helpers, section_renderers, page_body | 14+ symbols in formatters.py; active shell in shell.py; MANIFEST produced |
| 32-02 | Create trace.py, calc_rows.py, account.py; grow positions.py, paper_trades.py | 5 component files with all unique legacy fns; C-2 local imports preserved |
| 32-03 | Eliminate `import dashboard as d` from dashboard_renderer/ | Zero dashboard imports in dashboard_renderer/; acyclic gate passes |
| 32-04 | Retarget callers, thin shim, delete 8 legacy files | 74-LOC shim; ImportError stub; 2084 tests green |

## Phase 32 ROADMAP Success Criteria

1. **✅ No live code path imports from `dashboard_legacy/`** — `git grep "dashboard_legacy" -- '*.py'` returns hits only inside `dashboard_legacy/__init__.py` and `tests/test_dashboard_split_seam.py` (the test asserting the stub).

2. **✅ `dashboard_legacy/` replaced by ImportError stub** — `dashboard_legacy/__init__.py` uses `_RetiredSubmoduleFinder` + `__getattr__` pattern; every attribute access or submodule import raises `ImportError("dashboard_legacy retired — use dashboard_renderer")` — NOT ModuleNotFoundError.

3. **✅ `dashboard.py` ≤100 LOC shim** — 74 LOC, 10-line docstring; only public API (render_dashboard_files, render_dashboard_page, render_dashboard alias) + logger + CLI.

4. **✅ Full test suite green; golden HTML byte-identical** — 2084 passed; golden snapshot tests byte-identical; XSS gate and hex boundary gate green.

5. **✅ assets.py LOC exemption** — `dashboard_renderer/assets.py` is a data file (CSS/JS constants); explicitly excluded from 500 LOC cap enforcement.

## Key Technical Decisions

### Python 3.13 ImportError Stub Fix
The plan specified `__path__ = []` + `__getattr__` to make submodule imports raise `ImportError`. Python 3.13 changed file-based package loading: `__path__ = []` causes submodule imports to raise `ModuleNotFoundError` (not `ImportError`) because the standard module finder exhausts path search before __getattr__ is consulted. Fix: a `_RetiredSubmoduleFinder` registered in `sys.meta_path` intercepts the import before the standard finder and raises `ImportError` with the locked message.

### Wave-2 Lazy Import Rule (H-02)
shell.py imports Wave-2 components (account, calc_rows, trace) as LOCAL imports inside callable bodies — not at module top. This ensures `import dashboard_renderer.shell` succeeds immediately after Wave 1 merges (before Wave 2 creates those files).

### Canonical Name Locks
- All formatters helpers preserve underscore prefix: `_fmt_currency`, `_fmt_em_dash`, `_format_indicator_value`, etc.
- `render_paper_trades_region` is PUBLIC (no underscore) in paper_trades.py
- `logger = logging.getLogger('dashboard')` literal string preserved in dashboard.py (NOT `__name__`)

## Self-Check: PASSED
