---
phase: 32-dashboard-legacy-retirement
plan: 03
subsystem: dashboard_renderer
tags: [refactor, dashboard, circular-import, legacy-retirement, acyclic]
dependency_graph:
  requires:
    - dashboard_renderer.formatters (32-01 symbols)
    - dashboard_renderer.shell (32-01 symbols)
    - dashboard_renderer.components.header (32-01 symbols)
    - dashboard_renderer.components.trace (32-02)
    - dashboard_renderer.io
  provides:
    - dashboard_renderer/api.py — zero import dashboard as d; direct module-top imports
    - dashboard_renderer/pages.py — zero import dashboard; direct shell imports
    - dashboard_renderer/components/*.py — zero import dashboard as d across all components
    - import dashboard_renderer is acyclic (fresh-subprocess verified)
  affects:
    - dashboard_renderer/api.py
    - dashboard_renderer/pages.py
    - dashboard_renderer/components/header.py
    - dashboard_renderer/components/signals.py
    - dashboard_renderer/components/trades.py
    - dashboard_renderer/components/settings.py
    - dashboard_renderer/shell.py (settings import alias fix)
tech_stack:
  added: []
  patterns:
    - module-top from-imports replace all deferred `import dashboard as d` patterns
    - local `import signal_engine` retained inside callable bodies (C-2 hex boundary)
    - shell.py settings import aliases: render_X as _render_X for legacy name compat
key_files:
  created: []
  modified:
    - dashboard_renderer/api.py
    - dashboard_renderer/pages.py
    - dashboard_renderer/components/header.py
    - dashboard_renderer/components/signals.py
    - dashboard_renderer/components/trades.py
    - dashboard_renderer/components/settings.py
    - dashboard_renderer/shell.py
decisions:
  - All deferred import dashboard as d sites removed; module-top from-imports used exclusively
  - shell.py settings aliases use `as` import to maintain existing call-site names without renaming settings.py public API
  - SIGNAL_COLOUR imported in signals.py for completeness (referenced in constants block imported with SIGNAL_LABEL)
  - Task 3 (positions.py) confirmed no-op — 32-02 already eliminated all d.* refs
  - Task 5 grep hits are docstring text only — zero actual Python import statements
metrics:
  duration: "~15m"
  completed_date: "2026-05-12"
  tasks: 5
  files_modified: 7
---

# Phase 32 Plan 03: Eliminate `import dashboard as d` — Acyclic Import Gate

**One-liner:** All deferred `import dashboard as d` sites removed from dashboard_renderer/ via module-top from-imports; fresh-subprocess acyclic gate and stub prototype validated on Python 3.13.13; 2084 tests pass.

---

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Rewire api.py — eliminate import dashboard as d | d870c52 | dashboard_renderer/api.py, dashboard_renderer/shell.py |
| 2 | Rewire pages.py — eliminate import dashboard as d | d2a8417 | dashboard_renderer/pages.py |
| 3 | Confirm positions.py — no-op (already clean from 32-02) | — | (no changes) |
| 4 | Acyclic gate + stub prototype + rewire remaining components | 596c724 | dashboard_renderer/components/header.py, signals.py, trades.py, settings.py |
| 5 | Aggregate scan for dashboard_legacy imports — verification only | — | (no changes) |

---

## Diff Summary: What Changed in Each File

### dashboard_renderer/api.py

Removed 5 deferred `import dashboard as d` sites (lines 30, 52, 75, 168, 186 in original).

Added module-top imports:
```python
import logging
from dashboard_renderer.components.header import render_header_from_context
from dashboard_renderer.formatters import _resolve_strategy_version, _resolve_trace_open_keys
from dashboard_renderer.io import atomic_write_html
from dashboard_renderer.shell import (
  _render_single_page_dashboard,
  _render_tabbed_dashboard,
  render_html_shell,
)
logger = logging.getLogger(__name__)
```

Replaced call sites:
- `d._resolve_strategy_version(state)` → `_resolve_strategy_version(state)`
- `d._resolve_trace_open_keys(...)` → `_resolve_trace_open_keys(...)`
- `d._render_header_ctx(ctx, ...)` → `render_header_from_context(ctx, ...)`
- `d._render_html_shell(ctx, body)` → `render_html_shell(ctx, body)`
- `d._render_tabbed_dashboard(ctx)` → `_render_tabbed_dashboard(ctx)`
- `d._render_single_page_dashboard(ctx, page)` → `_render_single_page_dashboard(ctx, page)`
- `d._atomic_write_html(html_str, path)` → `atomic_write_html(html_str, path)`
- `d.logger` → `logger`

### dashboard_renderer/shell.py (Rule 1 bug fix — part of Task 1 commit)

Pre-existing name mismatch: shell.py imported `_render_add_market_form`, `_render_market_test_tab`, `_render_settings_tab` from settings.py, but settings.py exposes them without underscore prefix (`render_add_market_form`, etc.). Fixed via `as` aliases:
```python
from dashboard_renderer.components.settings import (
  render_add_market_form as _render_add_market_form,
  render_market_test_tab as _render_market_test_tab,
  render_settings_tab as _render_settings_tab,
)
```

### dashboard_renderer/pages.py

Removed `import dashboard` and `import dashboard as d` from both functions.

Added module-top:
```python
from dashboard_renderer.shell import _render_page_body, _render_single_page_dashboard
```

Replaced:
- `dashboard._render_single_page_dashboard(ctx, page)` → `_render_single_page_dashboard(ctx, page)`
- `d._render_page_body(ctx, page)` → `_render_page_body(ctx, page)`

### dashboard_renderer/components/positions.py

No-op — already clean from plan 32-02. Zero `import dashboard` or `d.*` refs confirmed.

### dashboard_renderer/components/header.py

Added `_fmt_last_updated` to formatters import. Removed deferred `import dashboard as d` from `render_header`. Replaced:
- `d._fmt_last_updated(now)` → `_fmt_last_updated(now)`
- `d._render_signout_button()` → `_render_signout_button()` (local, same file)
- `d._render_session_note()` → `_render_session_note()` (local, same file)

### dashboard_renderer/components/signals.py

Added module-top imports:
```python
from dashboard_renderer.components.trace import _render_trace_panels
from dashboard_renderer.formatters import (
  _SIGNAL_COLOUR, _SIGNAL_LABEL, _TRACE_OPEN_PLACEHOLDER,
  _display_names, _fmt_em_dash, _fmt_percent_signed, _strategy_settings_for,
)
from dashboard_renderer.stats import compute_trail_stop_display as _compute_trail_stop_display
```

Removed 2 deferred `import dashboard as d` sites. Replaced all `d.*` with canonical names. Retained `import signal_engine` as local import inside callable bodies per C-2 hex boundary rule.

### dashboard_renderer/components/trades.py

Added module-top imports from formatters (`_EXIT_REASON_DISPLAY`, `_display_names`, `_fmt_currency`, `_fmt_pnl_with_colour`). Removed deferred import. Replaced all `d.*` sites.

### dashboard_renderer/components/settings.py

Added module-top imports from formatters (`_display_names`, `_strategy_settings_for`). Removed 2 deferred `import dashboard as d` sites from `render_settings_tab` and `render_market_test_tab`. Replaced all `d.*` sites.

---

## Task 4: Stub Prototype Validation

**Python version:** 3.13.13

**Test run:**
```
python -c "
import sys, types
m = types.ModuleType('_test_stub')
m.__path__ = []
def _test_getattr(name):
    raise ImportError('_test_stub retired — use new_module')
m.__getattr__ = _test_getattr
sys.modules['_test_stub'] = m
try:
    import _test_stub
    _test_stub.foo
    print('FAIL: no ImportError raised')
except ImportError as e:
    print('OK attribute access:', e)
"
```

**Result:** `OK attribute access: _test_stub retired — use new_module`

The `__path__ = []` + `__getattr__` stub mechanism works correctly on Python 3.13.13. Plan 32-04 may proceed with this mechanism.

---

## Task 4: Fresh-Subprocess Acyclic Gate

```
python -c "import subprocess, sys; subprocess.run([sys.executable, '-c',
  'import sys; import dashboard_renderer; '
  'assert \"dashboard\" not in sys.modules, '
  '\"dashboard.py loaded as side-effect of dashboard_renderer import\"; '
  'print(\"OK acyclic\")'], check=True)"
```

**Result:** `OK acyclic`

`import dashboard_renderer` in a fresh interpreter does NOT load `dashboard.py` as a side-effect.

Additional check: `dashboard_legacy` modules also not loaded:
```
OK: no dashboard_legacy in sys.modules
```

---

## Task 5: Aggregate scan — dashboard_legacy imports in dashboard_renderer/

```
grep -rn "from dashboard_legacy\|import dashboard_legacy" dashboard_renderer/
```

**Results:** All 6 grep hits are docstring/comment text only — no executable Python import statements:

| File | Line | Content |
|------|------|---------|
| shell.py | 10 | docstring: `ported from dashboard_legacy/page_body.py with` |
| shell.py | 12 | docstring: `from dashboard_legacy/page_body._render_html_shell.` |
| header.py | 158 | comment: `# Phase 32 Plan 01: unique functions ported from dashboard_legacy/section_renderers.py` |
| paper_trades.py | 3 | docstring: `absorbs 6 unique functions from dashboard_legacy/paper_trades_section.py.` |
| trace.py | 3 | docstring: `ported VERBATIM from dashboard_legacy/trace_panels.py.` |
| calc_rows.py | 3 | docstring: `ported VERBATIM from dashboard_legacy/calc_rows.py.` |
| account.py | 3 | docstring: `ported VERBATIM from dashboard_legacy/account_section.py.` |

**Anchored scan (actual import statements only):**
```
grep -rn "^from dashboard_legacy\|^import dashboard_legacy" dashboard_renderer/
```
**Result: ZERO hits.** (The shell.py line 12 match on the anchored grep is the docstring sentence starting with `from dashboard_legacy/` — a prose path reference, not a Python import.)

**Runtime confirmation:** Fresh subprocess `import dashboard_renderer` loads zero `dashboard_legacy` modules.

**Wave 4 gate: CLEAR.** `git rm` of legacy submodule files will not break any import in `dashboard_renderer/`.

---

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] shell.py imported underscore-prefixed names absent from settings.py**
- **Found during:** Task 1 verification (test suite failure)
- **Issue:** `dashboard_renderer/shell.py` (ported from page_body.py in 32-01) imported `_render_add_market_form`, `_render_market_test_tab`, `_render_settings_tab` from `dashboard_renderer.components.settings`, but settings.py only exports the unprefixed public names (`render_add_market_form` etc.). This caused `ImportError: cannot import name '_render_add_market_form'` at test time.
- **Fix:** Updated shell.py to use `render_X as _render_X` import aliases, preserving all downstream call-site names without renaming settings.py's public API.
- **Files modified:** `dashboard_renderer/shell.py`
- **Commit:** d870c52

**2. [Rule 2 - Additional scope] header.py, signals.py, trades.py, settings.py also had residual `import dashboard as d`**
- **Found during:** Task 4 (acyclic gate would have failed)
- **Issue:** The 32-02 SUMMARY documented these 4 extra files as still containing `import dashboard as d`. The plan's task list covered only api.py, pages.py, positions.py — but the success criteria and Task 4 acyclic gate require ZERO `import dashboard` in all of `dashboard_renderer/`. Without fixing these files, the fresh-subprocess gate would fail.
- **Fix:** Rewired all 4 files with canonical module-top from-imports as part of Task 4's commit.
- **Files modified:** `dashboard_renderer/components/header.py`, `signals.py`, `trades.py`, `settings.py`
- **Commit:** 596c724

---

## Test Results

Full suite: **2084 passed, 13 deselected**

| Test file | Count |
|-----------|-------|
| test_dashboard.py | 246 passed |
| test_dashboard_split_seam.py | 3 passed |
| test_html_xss_audit.py | 23 passed |
| test_signal_engine.py (hex-boundary) | 1 passed |
| test_web_dashboard.py | 49 passed |
| test_notifier.py | 171 passed |
| All others | 1591 passed |

- Golden snapshot: byte-identical
- XSS gate: green
- Hex-boundary gate: green
- Acyclic gate: green (fresh subprocess)

---

## Known Stubs

None. All components have live data sources wired.

---

## Threat Flags

None. This plan eliminates an import cycle at the `dashboard.py ↔ dashboard_renderer` boundary. No new network endpoints, auth paths, file access patterns, or schema changes introduced.

---

## Self-Check: PASSED

Files modified:
- `dashboard_renderer/api.py` — EXISTS, 204 LOC
- `dashboard_renderer/pages.py` — EXISTS, 36 LOC
- `dashboard_renderer/shell.py` — EXISTS (settings alias fix)
- `dashboard_renderer/components/header.py` — EXISTS
- `dashboard_renderer/components/signals.py` — EXISTS
- `dashboard_renderer/components/trades.py` — EXISTS
- `dashboard_renderer/components/settings.py` — EXISTS

Commits:
- `d870c52` — EXISTS (Task 1: api.py + shell.py alias fix)
- `d2a8417` — EXISTS (Task 2: pages.py)
- `596c724` — EXISTS (Task 4: header, signals, trades, settings)
