---
phase: 30
plan: "30-03"
subsystem: web/routes/dashboard
tags: [file-split, refactor, phase-30, dashboard]
dependency_graph:
  requires: []
  provides: [web.routes.dashboard package with register() in __init__.py and _is_stale_for in _renderers.py]
  affects: [web/app.py import surface (unchanged), web/services/dashboard_service.py (unchanged)]
tech_stack:
  added: []
  patterns: [Python package split, closure-capture audit, D-07 boundary]
key_files:
  created:
    - web/routes/dashboard/__init__.py
    - web/routes/dashboard/_renderers.py
  modified: []
  deleted:
    - web/routes/dashboard.py
decisions:
  - "_is_htmx_request, _resolve_trace_open, _forward_stop_fragment_response moved to _renderers.py (all closure-free, no deps on register()-scoped vars)"
  - "_is_cookie_session, _set_market_cookie, _substitute, _serve_dashboard_content kept inside register() per T-30-03-01 (capture _session_serializer/_MARKET_COOKIE_ATTRS)"
  - "Contingency (a) invoked: __init__.py is 548 LOC (>500, <=550 cap) — documented below"
metrics:
  duration: "~12 minutes"
  completed_date: "2026-05-11"
  tasks_completed: 1
  files_changed: 3
---

# Phase 30 Plan 03: Dashboard Route Package Split Summary

**One-liner:** Behaviour-preserving split of 650-LOC `web/routes/dashboard.py` into `web/routes/dashboard/__init__.py` (548 LOC, contingency a) and `web/routes/dashboard/_renderers.py` (143 LOC) per D-07 boundary.

## Tasks

| # | Name | Commit | Files |
|---|------|--------|-------|
| 1 | Split web/routes/dashboard.py into 2-file package (D-07 boundary) | 2a6627e | web/routes/dashboard/__init__.py, web/routes/dashboard/_renderers.py (created); web/routes/dashboard.py (deleted) |

## What Was Built

Converted `web/routes/dashboard.py` (650 LOC) into a Python package with two daughter files.

**Closure-capture audit results (Step A):**

| Helper | Closure Deps | Destination |
|--------|-------------|-------------|
| `_is_stale_for` | None | `_renderers.py` (D-07) |
| `_is_htmx_request` | None | `_renderers.py` |
| `_resolve_trace_open` | Uses `_MARKET_ID_RE` (module-level) | `_renderers.py` |
| `_forward_stop_fragment_response` | None (local imports only) | `_renderers.py` |
| `_is_cookie_session` | Captures `_session_serializer` | Stays in `register()` |
| `_set_market_cookie` | Captures `_MARKET_COOKIE_ATTRS` | Stays in `register()` |
| `_substitute` | Calls `_is_cookie_session` → `_session_serializer` | Stays in `register()` |
| `_serve_dashboard_content` | Calls `_substitute` (closure chain) | Stays in `register()` |
| `_serve_dashboard_page` | Calls `_serve_dashboard_content` | Stays in `register()` |
| `_serve_dashboard_root` | Calls `_serve_dashboard_content` | Stays in `register()` |
| `_serve_market_scoped_page` | Calls `_substitute`, `_set_market_cookie` | Stays in `register()` |

**Import surface preserved:** `from web.routes import dashboard as dashboard_route` + `.register(app)` pattern unchanged in `web/app.py` and `web/services/dashboard_service.py`. No `from web.routes.dashboard import X` callers existed.

## D-09 Cap Exception

**D-09 cap exception: `dashboard/__init__.py` is 548 LOC (cap raised to 550 for this file only per pre-approved contingency (a)).**

Root cause: `register()` body alone is 501 LOC (the FastAPI route-registration function contains 20+ nested helpers that capture `_session_serializer` and `_MARKET_COOKIE_ATTRS` closure variables and cannot be moved out without changing the call signature). After extracting all closure-free helpers (`_is_stale_for`, `_is_htmx_request`, `_resolve_trace_open`, `_forward_stop_fragment_response`) to `_renderers.py`, the remaining `__init__.py` is 548 LOC — within the 550 overflow contingency (a) cap.

No contingency (b) (`_handlers.py` parameter injection) was required.

## Deviations from Plan

None - plan executed exactly as written, including the pre-approved contingency (a) path.

## Known Stubs

None. All functions are real implementations copied verbatim from the original `dashboard.py`.

## Threat Flags

None. The split introduces no new network endpoints, auth paths, file access patterns, or schema changes. T-30-03-01 (session serializer leak) mitigated: `_is_cookie_session` stays inside `register()`, preserving the closure chain.

## Self-Check: PASSED

- web/routes/dashboard/__init__.py: FOUND
- web/routes/dashboard/_renderers.py: FOUND
- web/routes/dashboard.py: CONFIRMED REMOVED
- Commit 2a6627e: FOUND
