# Phase 32: Dashboard Legacy Retirement - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-12
**Phase:** 32-dashboard-legacy-retirement
**Areas discussed:** Absorption structure, Legacy retirement form, Byte-identity gate

---

## Absorption Structure

### Q1 — Module placement strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Mirror legacy structure | Move each dashboard_legacy/X.py as dashboard_renderer/X.py. Minimal refactor, predictable. | |
| Redistribute by domain | Merge legacy helpers into existing dashboard_renderer/ files by semantic fit. Cleaner long-term. | ✓ |

**User's choice:** Redistribute by domain
**Notes:** Semantic fit over structural mirroring — positions_section → components/positions.py, render_helpers formatters → formatters.py, page_body HTML shell → shell.py, etc.

---

### Q2 — 500 LOC overflow handling

| Option | Description | Selected |
|--------|-------------|----------|
| Split receiving file further | If overflow, split at a natural seam (planner picks names). Stays under cap. | ✓ |
| Allow up to 600 LOC one-time exception | Cap relaxation only for legacy-absorbing files in this phase. | |
| You decide | Planner decides per-module with no pre-commitment. | |

**User's choice:** Split receiving file further
**Notes:** Planner decides seam names (e.g., positions_table.py + positions_forms.py). Hard 500 LOC cap preserved.

---

### Q3 — Overlap handling between legacy and existing dashboard_renderer/

| Option | Description | Selected |
|--------|-------------|----------|
| Audit first, port only gaps | Check existing dashboard_renderer/ coverage first; port only uncovered functions. | ✓ |
| Port everything, deduplicate after | Move all legacy functions, then identify and remove duplicates. | |

**User's choice:** Audit first, port only gaps
**Notes:** Prevents bloat and duplicate code from landing in the codebase.

---

## Legacy Retirement Form

### Q1 — dashboard_legacy/ fate after porting

| Option | Description | Selected |
|--------|-------------|----------|
| ImportError stub | Single __init__.py raising ImportError. Catches accidental re-introduction. | ✓ |
| Delete entirely | Remove the entire directory. Clean, no safety net. | |

**User's choice:** ImportError stub
**Notes:** Preferred for safety during Phase 33+ multi-tenant work where accidental legacy imports could go unnoticed.

---

### Q2 — Caller import updates

| Option | Description | Selected |
|--------|-------------|----------|
| Update callers to import from dashboard_renderer.* | Tests + prod code updated to new homes. Clean. | ✓ |
| Keep thin re-exports in dashboard.py | dashboard.py keeps a subset re-export surface for compatibility. | |

**User's choice:** Update callers to import from dashboard_renderer.* directly
**Notes:** 100 LOC limit makes backward-compat layer infeasible. Clean cut preferred.

---

## Byte-Identity Gate

### Q1 — Baseline strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Golden snapshots are sufficient | tests/test_dashboard.py golden tests already lock rendered HTML. | ✓ |
| Capture explicit HTML baseline first | Render fixture state to 32-BASELINE.html before any changes. | |

**User's choice:** Golden snapshots are sufficient
**Notes:** Existing golden tests are the regression signal. No extra baseline artifact needed.

---

## Claude's Discretion

- Exact seam names when a receiving file overflows (e.g., positions_table.py vs positions_grid.py)
- Import ordering within absorbed files
- `__all__` vs `# noqa: F401` on re-exports in dashboard_renderer/__init__.py
- Logger placement in thinned dashboard.py

## Deferred Ideas

None — discussion stayed within phase scope.
