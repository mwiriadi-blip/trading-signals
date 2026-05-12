# Phase 31: Core Module Split - Context

**Gathered:** 2026-05-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Behaviour-preserving package conversion of `state_manager.py` (1,293 LOC) and `sizing_engine.py` (820 LOC) into focused sub-module packages before any v1.3 `user_id` injection touches their semantics. No functional changes — public API identical after split; internal re-organisation only.

Two packages delivered:
- `state_manager/` — `__init__.py`, `migrations.py`, `validation.py`, `io.py`, `trades.py`
- `sizing_engine/` — `__init__.py`, `_models.py`, `sizing.py`, `stops.py`, `pyramid.py`, `close.py`

Every daughter file ≤500 LOC. Full test suite green. All existing import paths resolve without change via `__init__.py` re-exports.

</domain>

<decisions>
## Implementation Decisions

### state_manager/ — public API layer

- **D-01:** `__init__.py` owns the public API: `load_state`, `save_state`, `reset_state`, `mutate_state`. These compose `io` + `migrations` + `validation` submodules. `__init__.py` is the orchestrator (~300 LOC estimated).
- **D-02:** `io.py` = kernel only: `_atomic_write_unlocked`, `_atomic_write`, `_backup_corrupt`, `_save_state_unlocked`. No domain logic. `mutate_state` (in `__init__`) calls `io._save_state_unlocked` directly to avoid intra-process flock re-acquisition deadlock — this call pattern is preserved exactly.
- **D-03:** `validation.py` = `_assert_tz_aware` + `_coerce_legacy_naive_iso` (datetime-correctness guards, as specified by roadmap) alongside `_validate_trade` + `_validate_loaded_state`. All four are called from `__init__.py` (`load_state`, `append_warning`).
- **D-04:** `migrations.py` = all `_migrate_vX_to_vY` functions + `MIGRATIONS` dict + `_default_market_registry` + `_default_strategy_settings` + `_assert_migration_chain_contiguous` (including the module-level call) + `_read_signal_strategy_version` + `_migrate` orchestrator. **⚠ Size risk:** this content approaches 500 LOC — planner must verify and may need to move `_read_signal_strategy_version` to `validation.py` if migrations.py exceeds the cap.

### state_manager/ — record helpers (trades.py)

- **D-05:** `trades.py` = `record_trade` + `append_warning` + `clear_warnings` + `clear_warnings_by_source` + `update_equity_history`. All five follow the same pattern: take a `state` dict, append/mutate a list, return updated state. Name kept as `trades.py` per roadmap (not renamed to `mutations.py`) — ~165 LOC estimated.

### sizing_engine/ — dataclasses and orphaned functions

- **D-06:** `_models.py` = all 5 dataclasses: `SizingDecision`, `PyramidDecision`, `ClosedTrade`, `StepResult`, `DriftEvent`. Phase 30 precedent (Phase 30 D-04/D-05/D-08 used `_models.py` for shared data shapes). All submodules import from `_models`. `__init__.py` re-exports them. ~75 LOC.
- **D-07:** `__init__.py` = `step()` (221 LOC orchestrator) + re-exports from all submodules. Callers already do `from sizing_engine import step` which resolves to `__init__`. Total `__init__` ~260 LOC.
- **D-08:** `sizing.py` = `_vol_scale` + `calc_position_size` + `compute_unrealised_pnl`. `compute_unrealised_pnl` is position-value calculation — sizing domain. ~140 LOC estimated.
- **D-09:** `stops.py` = `get_trailing_stop` + `check_stop_hit`. ~160 LOC estimated.
- **D-10:** `pyramid.py` = `check_pyramid` + `detect_drift`. `detect_drift` checks whether position vs signal has diverged — a pyramid/exit decision trigger. ~135 LOC estimated.
- **D-11:** `close.py` = `_close_position`. ~55 LOC estimated.

### Claude's Discretion

- Import ordering within each daughter file (stdlib → third-party → local).
- Whether to add `# noqa: F401` on re-exports in `__init__.py` files or use `__all__` instead — planner's call.
- Exact placement of shared constants/imports (e.g., `STATE_SCHEMA_VERSION`, `STATE_FILE`) — these live at the top of `__init__.py` or in a `_constants.py` if they're needed by multiple daughters without circularity.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Roadmap and requirements
- `.planning/ROADMAP.md` — Phase 31 goal, success criteria, exact submodule names (§Phase 31: Core Module Split)
- `.planning/REQUIREMENTS.md` — OPS-05 (file splits); acceptance criteria

### Prior split precedent (Phase 30)
- `.planning/phases/30-file-size-pre-split/30-CONTEXT.md` — D-01 through D-09: package-per-file pattern, `register()` in `__init__`, `_models.py` for shared data shapes, `_renderers.py` for helpers. Phase 31 follows the same structural conventions.

### Files to split (read before planning split boundaries)
- `state_manager.py` — 1,293 LOC; function index: `_migrate_v*` (lines 195–601), `_assert_migration_chain_contiguous` (602), `_read_signal_strategy_version` (637), `_atomic_write_unlocked` (658), `_atomic_write` (712), `_migrate` (751), `_backup_corrupt` (764), `_validate_trade` (790), `_validate_loaded_state` (864), `reset_state` (900), `load_state` (950), `save_state` (1038), `_save_state_unlocked` (1074), `mutate_state` (1090), `append_warning` (1131), `clear_warnings` (1165), `clear_warnings_by_source` (1190), `record_trade` (1212), `update_equity_history` (1248)
- `sizing_engine.py` — 820 LOC; function index: dataclasses (41–115), `detect_drift` (116), `_vol_scale` (194), `calc_position_size` (211), `get_trailing_stop` (280), `check_stop_hit` (361), `check_pyramid` (439), `compute_unrealised_pnl` (493), `step` (545), `_close_position` (766)

### Caller import surface (must remain unchanged after split)
- `daily_run.py` — `import sizing_engine`, `import state_manager`
- `daily_run_helpers.py` — `import sizing_engine`, `import state_manager`, `from sizing_engine import ClosedTrade`
- `main.py` — `import sizing_engine`, `import state_manager`
- `backtest/simulator.py` — `from sizing_engine import step`
- `web/routes/trades/__init__.py` — `from sizing_engine import check_pyramid`, `detect_drift`; `from state_manager import mutate_state`, `append_warning`, `clear_warnings_by_source`, `load_state`, `record_trade`
- `web/routes/dashboard/_renderers.py` — `from sizing_engine import get_trailing_stop`; `from state_manager import load_state`
- `web/routes/paper_trades/__init__.py` — `from state_manager import load_state`, `mutate_state`
- `web/routes/markets.py` — `from state_manager import mutate_state`, `load_state`
- `dashboard.py`, `crash_boundary.py`, `interactive.py`, `paper_trade_alerts.py`, `notifier/transport.py` — various `state_manager` imports

### AST boundary test (must stay green)
- `tests/test_signal_engine.py` — `FORBIDDEN_MODULES` frozenset (line 493); `test_forbidden_imports_absent` (line 787); AST-walks hex modules to enforce `signal_engine`, `data_fetcher`, `web/*` cannot import `sizing_engine` internals directly.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- Phase 30 package conversion completed: `web/routes/trades/`, `web/routes/login/`, `web/routes/totp/`, `web/routes/dashboard/`, `web/routes/paper_trades/` — all use identical `__init__.py` + private-module pattern. Exact same approach applies here.
- `auth_store.py` — copied `_atomic_write_unlocked` verbatim from `state_manager`. After split, `io.py` is the canonical home; `auth_store.py` is NOT changed in this phase (out of scope).
- `state_actions.py` — owns `_LAST_LOADED_STATE` singleton. Not touched in this phase; `main.py` attribute continues to be the proxy reference.

### Established Patterns
- `__init__.py` re-exports all public symbols — callers never import submodule paths directly (D-03 from Phase 30 context).
- `_private` underscore prefix for internal submodule helpers — maintained across all daughter files.
- `from sizing_engine import ClosedTrade` in `daily_run_helpers.py` — `ClosedTrade` moves to `sizing_engine/_models.py` but is re-exported from `sizing_engine/__init__.py`, so this import path is unchanged.
- `fcntl.flock` intra-process deadlock avoidance: `mutate_state` calls `_save_state_unlocked` (not `save_state`) — this call path must be preserved in the split. `mutate_state` in `__init__.py` calls `io._save_state_unlocked` directly.

### Integration Points
- `tests/test_signal_engine.py::test_forbidden_imports_absent` — AST-walks hex modules. After split, the package `__init__.py` re-exports create no new forbidden import paths (internal submodule imports within `sizing_engine/` are not visible to hex callers). Gate must stay green.
- `_assert_migration_chain_contiguous()` is called at module-load time (bottom of current `state_manager.py`). After split, this call must be at the bottom of `migrations.py` (so it fires when `state_manager` is imported and `migrations` is loaded).

</code_context>

<specifics>
## Specific Ideas

No specific references — straightforward mechanical split following Phase 30 conventions.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 31-Core-Module-Split*
*Context gathered: 2026-05-12*
