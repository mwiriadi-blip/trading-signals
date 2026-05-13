# Phase 32: Dashboard Legacy Retirement - Context

**Gathered:** 2026-05-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Retire `dashboard_legacy/` as an active rendering path. All rendering logic currently split across `dashboard_legacy/` (8 modules) and `dashboard_renderer/` (2641 total LOC) is consolidated into `dashboard_renderer/` only. The circular import between `dashboard_renderer/api.py` (which currently does `import dashboard as d` inside function bodies to access legacy functions) and `dashboard.py` is eliminated. `dashboard.py` is thinned to a ≤100 LOC pass-through shim exposing only the public API (`render_dashboard_files`, `render_dashboard_page`, `render_dashboard` alias, logger, CLI entrypoint). No functional changes — rendered HTML byte-identical before and after.

</domain>

<decisions>
## Implementation Decisions

### Absorption structure

- **D-01:** Redistribute by domain — legacy functions merge into existing `dashboard_renderer/` modules by semantic fit, NOT a mirror of legacy file structure. Examples: `render_helpers.py` format helpers → `dashboard_renderer/formatters.py`; `positions_section.py` → `dashboard_renderer/components/positions.py`; `section_renderers.py` header/footer → `dashboard_renderer/components/header.py` + `footer.py`; `page_body.py` HTML shell / atomic write → `dashboard_renderer/shell.py` + `dashboard_renderer/io.py`.

- **D-02:** 500 LOC cap enforced. When a receiving file would overflow the 500 LOC cap after absorbing legacy content, split the receiving file further at a natural seam (planner picks seam names). Example: if `components/positions.py` overflows → split into `components/positions_table.py` + `components/positions_forms.py`. No blanket cap relaxation.

- **D-03:** Audit-first approach. For each `dashboard_legacy/` module, the plan starts with an audit step: check what counterpart functions already exist in the target `dashboard_renderer/` file. Port only functions NOT yet covered. Delete duplicates from the legacy side rather than merging them.

### Legacy retirement

- **D-04:** `dashboard_legacy/` → ImportError stub. After all functions are ported: delete all 7 submodule files (`render_helpers.py`, `section_renderers.py`, `page_body.py`, `positions_section.py`, `calc_rows.py`, `paper_trades_section.py`, `account_section.py`, `trace_panels.py`) and replace with a single `__init__.py` raising `ImportError("dashboard_legacy retired — use dashboard_renderer")`. Catches accidental re-introduction in Phase 33+ multi-tenant code.

- **D-05:** Update all callers to import from `dashboard_renderer.*` directly. Tests (`tests/test_dashboard.py`, `tests/test_web_dashboard.py`) and production code (`web/routes/dashboard/_renderers.py`) that currently do `from dashboard import _fmt_currency`, `from dashboard import _render_single_position_row`, etc., are updated to import from the new home in `dashboard_renderer.*`. No backward-compat re-export layer in `dashboard.py`.

### Byte-identity gate

- **D-06:** Golden snapshot tests in `tests/test_dashboard.py` are the sufficient byte-identity gate. No explicit pre-refactor HTML baseline file needed. If rendered HTML changes at all after the port, the existing golden tests will fail — that is the regression signal.

### Claude's Discretion

- Exact seam names when a receiving file overflows (e.g., `positions_table.py` vs `positions_grid.py`).
- Import ordering within absorbed files (stdlib → third-party → local).
- Whether to add `__all__` or `# noqa: F401` on re-exports in `dashboard_renderer/__init__.py` after the circular import is resolved.
- Exact placement of `logger = logging.getLogger('dashboard')` after the shim thinning — stays in `dashboard.py` for journalctl name continuity.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Roadmap and requirements
- `.planning/ROADMAP.md` — Phase 32 goal, success criteria (§Phase 32: Dashboard Legacy Retirement)
- `.planning/REQUIREMENTS.md` — OPS-06 (legacy retirement requirement)

### Architecture constraint
- `CLAUDE.md` — hexagonal-lite boundary rules; `dashboard.py` is an I/O hex peer; must NOT import `signal_engine`, `sizing_engine`, `data_fetcher`, `notifier`, `main`, numpy, pandas, yfinance, or requests at module top
- `tests/test_signal_engine.py` — `FORBIDDEN_MODULES_DASHBOARD` frozenset + `test_forbidden_imports_absent`; AST hex boundary gate must stay green after the port

### Current module layout (read before planning split boundaries)
- `dashboard.py` — current 8237-byte shim; all re-exports to be removed; only public API + logger + CLI to survive
- `dashboard_legacy/__init__.py` — docstring-only; 7 active submodule files to be ported and deleted
- `dashboard_legacy/render_helpers.py` — format helpers, strategy/trace utils (~15KB source)
- `dashboard_legacy/section_renderers.py` — header, footer, equity chart, nav, session note, settings tab (~9920 bytes)
- `dashboard_legacy/page_body.py` — HTML shell, tabbed/single-page layout, `_atomic_write_html` (~9888 bytes)
- `dashboard_legacy/positions_section.py` — positions table, trailing-stop guidance, drift banner, open/close forms (~16320 bytes)
- `dashboard_legacy/calc_rows.py` — calculator row renderers (~12383 bytes)
- `dashboard_legacy/paper_trades_section.py` — paper-trades region + stats (~13096 bytes)
- `dashboard_legacy/account_section.py` — account balance form + stats (~6345 bytes)
- `dashboard_legacy/trace_panels.py` — trace indicators/inputs/vote panels (~9920 bytes)
- `dashboard_renderer/__init__.py` — current 3-function public re-export
- `dashboard_renderer/api.py` — circular import via `import dashboard as d` (to be eliminated)
- `dashboard_renderer/pages.py` — also does `import dashboard as d` (to be eliminated)
- `dashboard_renderer/formatters.py` (163 LOC) — target for render_helpers format functions
- `dashboard_renderer/shell.py` (204 LOC) — target for page_body HTML shell
- `dashboard_renderer/components/header.py` (148 LOC) — target for section_renderers header functions
- `dashboard_renderer/components/positions.py` (73 LOC) — target for positions_section (likely overflows → split)

### XSS gate (must stay green)
- `tests/test_html_xss_audit.py` — AST gate: every dynamic value must flow through `html.escape(value, quote=True)` at leaf render sites; `quote=True` is the codebase contract

### Prior split precedent
- `.planning/phases/30-file-size-pre-split/30-CONTEXT.md` — D-01 through D-09: package-per-file pattern used in Phase 30; same 500 LOC cap + audit-first approach
- `.planning/phases/31-core-module-split/31-CONTEXT.md` — Phase 31 conventions for `__init__.py` re-exports, `_models.py` placement

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `dashboard_renderer/formatters.py` (163 LOC) — already has format utilities; `render_helpers.py` helpers absorb here; audit first for overlaps
- `dashboard_renderer/shell.py` (204 LOC) — already owns HTML shell structure; `_atomic_write_html` + `_render_html_shell` from `page_body.py` likely land here
- `dashboard_renderer/io.py` (33 LOC) — small I/O helpers; `_atomic_write_html` may fit here if `shell.py` would overflow
- `dashboard_renderer/stats.py` (170 LOC) — aggregate stats; overlaps possible with `render_helpers._compute_*` functions
- `dashboard_renderer/components/` — 9 component files (header, nav, footer, positions, paper_trades, settings, signals, trades, 2-line `__init__`)

### Established Patterns
- `dashboard_renderer/api.py` deferred import `import dashboard as d` — anti-pattern being eliminated; replaced with direct imports from `dashboard_renderer.*` after port
- `html.escape(value, quote=True)` at every dynamic leaf site — mandatory; AST gate enforces
- `_private` underscore prefix for internal helpers — preserved in all daughter files
- `from dashboard_renderer.api import render_dashboard_files, render_dashboard_page, render_panel_html` is the public contract that `dashboard_renderer/__init__.py` re-exports; this surface is unchanged

### Integration Points
- `web/routes/dashboard/_renderers.py` — `from dashboard import _fmt_currency, _fmt_em_dash` (inside function body, C-2 pattern) → update to import from `dashboard_renderer.formatters`
- `tests/test_dashboard.py` — imports `dashboard` and ~10 private helpers; update to `dashboard_renderer.*` after port
- `tests/test_web_dashboard.py` — same; `from dashboard import _fmt_currency`, `_render_single_position_row`
- `tests/test_html_xss_audit.py` — XSS AST gate; must still find `html.escape` in the new file locations
- `main.py` — `import dashboard` for `main.dashboard` attribute; this `dashboard` reference stays (shim covers it)
- `web/app.py` comment references `dashboard_legacy/` as peer — update the docstring after retirement

</code_context>

<specifics>
## Specific Ideas

No specific references — redistribution by domain is the pattern, planner determines exact seams.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 32-dashboard-legacy-retirement*
*Context gathered: 2026-05-12*
