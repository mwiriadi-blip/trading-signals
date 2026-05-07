# Phase 26 — Deferred Items

## C5 — Lazy-regen siblings on page-route hit

**Status:** Deferred to v1.3.

**Problem:** `dashboard_renderer.api.render_dashboard_files` writes 4 sibling HTMLs (signals, account, settings, market-test) on every state mutation. ~5x I/O per run vs lazy regen on first page hit.

**Why deferred:** Optional polish; current behaviour is correct (just wasteful). Phase 26's BROKEN/RISKY backlog is the priority. Lazy-regen path is half-implemented in `_serve_dashboard_page` already (`web/routes/dashboard.py`).

**Picking up in v1.3:** Move sibling regen from `render_dashboard_files` into `_serve_dashboard_page`'s 404-or-stale path. `_is_stale_for` (Plan 26-07 R1) is the unlock — each sibling can now self-gate on its own marker.

## R5 — Renderer defensive `isinstance(int)` branch retained

**Status:** Live (not deferred — explicit decision).

**Context:** Plan 26-07 R5 fixed `add_market` to write the same dict shape as `main.run_daily_check` for `state['signals'][market_id]`. Plan asked to also delete the renderer's defensive `isinstance(record, int)` branch in `dashboard_renderer/components/signals.py:35-39` since it would be unreachable from prod write paths.

**Why kept:** 38 test sites across `test_state_manager.py`, `test_main.py`, `test_notifier.py`, `test_dashboard.py` still seed `state['signals']['SPI200'] = 0` int sentinels for fixture convenience. Deleting the branch would force a 38-site refactor across unrelated test files.

**Future cleanup:** When the next renderer-touching phase needs to refactor signal-state fixtures, fold the int-sentinel removal into that phase as a side cleanup. Until then the defensive branch is benign.
