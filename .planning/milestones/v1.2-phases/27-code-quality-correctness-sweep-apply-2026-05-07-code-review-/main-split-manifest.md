# main.py split manifest — Phase 27 Plan 13

Date: 2026-05-08
Source: main.py (2037 LOC at HEAD `18ff6bf`)
Target: thin entry-point + 7 cohesive modules.

## Function-ownership table (validated against actual code)

| Source line range | Symbol | New module | LOC est. | Notes |
|---:|---|---|---:|---|
| 1–123 | shebang/docstring + imports + constants + AWST + SYMBOL_MAP + _MIN_BARS_REQUIRED + _STALE_THRESHOLD_DAYS + STALENESS_DAYS_THRESHOLD + `_LAST_LOADED_STATE` + logger + service singletons | (shared header — see split below) | — | imports re-distributed per module need |
| 109 | `_LAST_LOADED_STATE` global | `state_actions.py` | 1 | accessor pair `_get_last_loaded_state` / `_set_last_loaded_state` added |
| 113–122 | `_daily_run_service` / `_signal_eval_service` / `_post_run_service` | `daily_run.py` | 10 | services constructed adjacent to their `_*_impl` |
| 129–147 | `_render_dashboard_never_crash` | `daily_run.py` | 19 | called only from `_run_daily_check_impl` |
| 154–202 | `_send_email_never_crash` | `crash_boundary.py` | 49 | sibling of `_send_crash_email`; same import-failure-isolation pattern |
| 209–415 | `_push_state_to_git_impl` | `daily_run.py` | 207 | state I/O extension of daily run |
| 422–463 | `_build_crash_state_summary` | `crash_boundary.py` | 42 | |
| 466–486 | `_send_crash_email` | `crash_boundary.py` | 21 | |
| 493–514 | `_maybe_set_stale_info` | `daily_run.py` | 22 | called only from `_run_daily_check_impl` |
| 517–607 | `_dispatch_email_and_maintain_warnings_impl` | `crash_boundary.py` | 91 | per agreed-3, relocates here |
| 619–632 | `_get_process_tzname` | `scheduler_driver.py` | 14 | |
| 635–683 | `_run_daily_check_caught` | `scheduler_driver.py` | 49 | tight coupling with `_run_schedule_loop` |
| 686–735 | `_run_schedule_loop` | `scheduler_driver.py` | 50 | |
| 742–813 | `_build_parser` | `cli_parser.py` | 72 | |
| 816–837 | `_validate_flag_combo` | `cli_parser.py` | 22 | |
| 840–844 | `_stdin_isatty` | `interactive.py` | 5 | called only from `_handle_reset` |
| 851–859 | `_compute_run_date` | `daily_run.py` | 9 | |
| 862–873 | `_mode_label` | `cli_parser.py` | 12 | |
| 876–920 | `_closed_trade_to_record` | `daily_run.py` | 45 | helper for `_run_daily_check_impl` |
| 930–934 | `_fmt_moms` + `_SIGNAL_LABELS` | `daily_run.py` | 5 | |
| 937–1002 | `_format_per_instrument_log_block` | `daily_run.py` | 66 | |
| 1005–1030 | `_format_run_summary_footer` | `daily_run.py` | 26 | |
| 1037–1048 | `_is_email_worthy` | `daily_run.py` | 12 | helper for `_evaluate_paper_trade_alerts_impl` |
| 1051–1166 | `_evaluate_paper_trade_alerts_impl` | `daily_run.py` | 116 | called from `_run_daily_check_impl`; `main._evaluate_paper_trade_alerts` test surface |
| 1173–1655 | `_run_daily_check_impl` | `daily_run.py` | 483 | the orchestration body itself |
| 1658–1685 | `run_daily_check` / `_evaluate_paper_trade_alerts` / `_dispatch_email_and_maintain_warnings` / `_push_state_to_git` (service wrapper trio) | `daily_run.py` | 28 | service-backed public wrappers |
| 1692–1731 | `_prompt_or_default` | `interactive.py` | 40 | |
| 1734–1905 | `_handle_reset` | `interactive.py` | 172 | |
| 1912–2033 | `main(argv)` | `main.py` (kept thin) | 122 | dispatcher; consumes wrappers from sibling modules |
| 2036–2037 | `if __name__ == '__main__':` | `main.py` | 2 | |

LOC sums (estimated):
- `daily_run.py` ≈ 1010 LOC (orchestration body alone is 483; helpers add ~525). **EXCEEDS 500 LOC budget — split needed.**
- `crash_boundary.py` ≈ 203 LOC (within budget).
- `scheduler_driver.py` ≈ 113 LOC (within budget).
- `cli_parser.py` ≈ 106 LOC (within budget).
- `interactive.py` ≈ 217 LOC (within budget).
- `state_actions.py` ≈ 25 LOC (very small — just `_LAST_LOADED_STATE` + accessor pair).
- `daily_loop.py` ≈ 30 LOC (orchestration shim — re-exports across the new files).
- `main.py` ≈ 130 LOC final (entry + early --version + symbol re-exports + module re-exports + `__getattr__` proxy).

## daily_run.py overage — sub-split

Per Rule 3 (blocking discovery during manifest construction), `daily_run.py` would land at ~1010 LOC, breaching the <500 (±10% = 550) LOC budget defined in plan must_haves and §M1. Split applied:

| File | Owns | LOC est. |
|---|---|---:|
| `daily_run.py` | `_run_daily_check_impl` body + `_compute_run_date` + service wiring + public wrappers (run_daily_check, _evaluate_paper_trade_alerts, _dispatch_email_and_maintain_warnings, _push_state_to_git) | ~530 |
| `daily_run_helpers.py` | `_render_dashboard_never_crash` + `_push_state_to_git_impl` + `_maybe_set_stale_info` + `_closed_trade_to_record` + `_fmt_moms` + `_SIGNAL_LABELS` + `_format_per_instrument_log_block` + `_format_run_summary_footer` | ~415 |
| `paper_trade_alerts.py` | `_is_email_worthy` + `_evaluate_paper_trade_alerts_impl` | ~135 |

Each daughter module stays well under 500 LOC. `daily_run.py` body of 483 LOC for the orchestration loop alone fits (no extra helpers in same file).

NOTE — this is a deviation from the plan's `<function_ownership>` table (which placed all of these in one `daily_run.py`). Documented as Rule 3 in SUMMARY.md. Plan's "every new module <500 LOC" hard rule (§must_haves.truths) takes precedence over the artifact-list-as-single-file expectation.

## daily_loop.py role

Per plan §truths, `daily_loop.py` is **orchestration only** — pure re-export/import shim that gathers `daily_run` / `state_actions` / `crash_boundary` symbols under one alias. In our daughter-module layout, daily_loop.py imports from `daily_run`, `daily_run_helpers`, `paper_trade_alerts`, `state_actions`, and `crash_boundary`. Total ~30 LOC.

## main.py re-export surface (validated)

### Symbols (from grep `main\.[a-zA-Z_]+` across tests/)

| Name | Source after split |
|---|---|
| `main.main` | local (entry-point) |
| `main.run_daily_check` | re-export from daily_run |
| `main._build_parser` | re-export from cli_parser |
| `main._validate_flag_combo` | re-export from cli_parser |
| `main._mode_label` | re-export from cli_parser |
| `main._build_crash_state_summary` | re-export from crash_boundary |
| `main._send_crash_email` | re-export from crash_boundary |
| `main._dispatch_email_and_maintain_warnings` | re-export from daily_run (which calls into crash_boundary impl via service) |
| `main._handle_reset` | re-export from interactive |
| `main._stdin_isatty` | re-export from interactive |
| `main._closed_trade_to_record` | re-export from daily_run_helpers |
| `main._evaluate_paper_trade_alerts` | re-export from daily_run |
| `main._get_process_tzname` | re-export from scheduler_driver |
| `main._run_daily_check_caught` | re-export from scheduler_driver |
| `main._run_schedule_loop` | re-export from scheduler_driver |
| `main._push_state_to_git` | re-export from daily_run |
| `main._LAST_LOADED_STATE` | lazy via `__getattr__` → `state_actions._get_last_loaded_state()` |

### Modules (from grep `main\.<modulename>` patterns)

| Attribute | Reason | Re-export form |
|---|---|---|
| `main.data_fetcher` | `monkeypatch.setattr(main.data_fetcher, 'fetch_ohlcv', ...)` | `import data_fetcher` (rebinds at package-name) |
| `main.signal_engine` | `monkeypatch.setattr(main.signal_engine, 'get_signal', ...)` | `import signal_engine` |
| `main.sizing_engine` | `monkeypatch.setattr(main.sizing_engine, 'step', ...)` | `import sizing_engine` |
| `main.state_manager` | `monkeypatch.setattr('main.state_manager.append_warning', ...)` | `import state_manager` |
| `main.dashboard` | `main.dashboard.render_dashboard_files` referenced indirectly via `_render_dashboard_never_crash` patches; tests check existence after split | `import dashboard` (top-level — already lazy via local import inside helper) |
| `main.logging` | `monkeypatch.setattr('main.logging.basicConfig', ...)` | `import logging` |

### `_LAST_LOADED_STATE` accessor strategy

**Decision:** Module-level `__getattr__` proxy in `main.py`.

Implementation:

```python
def __getattr__(name):
  if name == '_LAST_LOADED_STATE':
    from state_actions import _get_last_loaded_state
    return _get_last_loaded_state()
  raise AttributeError(f"module 'main' has no attribute {name!r}")
```

Why: PEP 562 module-level `__getattr__` resolves on attribute access, NOT at import time. So `main._LAST_LOADED_STATE` always reflects the live singleton stored in `state_actions._LAST_LOADED_STATE`.

Writers — `_run_daily_check_impl` and friends — call `state_actions._set_last_loaded_state(state)`. The crash-email path in `main()` reads via `state_actions._get_last_loaded_state()` (or the `main._LAST_LOADED_STATE` proxy on the test path). Singleton is preserved end-to-end; only one storage location exists.

## Cross-module edges (acyclic check)

```
main.py ─┬─> cli_parser
         ├─> interactive
         ├─> scheduler_driver
         ├─> crash_boundary
         ├─> daily_loop ─> daily_run
         ├─> state_actions
         └─> {data_fetcher, signal_engine, sizing_engine, state_manager, system_params, dashboard, logging}  (re-exports only)

daily_run ──> {daily_run_helpers, paper_trade_alerts, state_actions, crash_boundary, services, system_params, state_manager, data_fetcher, signal_engine, sizing_engine, alert_engine, pnl_engine}
daily_run_helpers ──> {state_manager, sizing_engine, system_params, pnl_engine, dashboard (local), notifier (local)}
paper_trade_alerts ──> {alert_engine, state_manager, notifier (local)}
crash_boundary ──> {state_manager, notifier (local), system_params}
scheduler_driver ──> {schedule (local), system_params, daily_run (lazy via main re-export to avoid cycle)}
cli_parser ──> {argparse, system_params}
interactive ──> {state_manager, system_params}
state_actions ──> ()  (pure module-level cache)
daily_loop ──> {daily_run, daily_run_helpers, paper_trade_alerts, state_actions, crash_boundary}
```

**Cycle check:** scheduler_driver._run_schedule_loop's parameter `job` is `run_daily_check` passed by main.py at call time — no import-time edge from scheduler_driver to daily_run, so no cycle. Same for `_run_daily_check_caught(job, args)` — `job` is passed in.

## Hex-boundary preservation

main.py keeps the `FORBIDDEN_MODULES_MAIN` blocklist clean (numpy, yfinance, requests, pandas — none imported). Daughter modules inherit the same discipline:
- `daily_run.py` / `daily_run_helpers.py` / `paper_trade_alerts.py` work with pandas DataFrames returned from `data_fetcher.fetch_ohlcv` — they use pandas operations on those objects but DO NOT `import pandas`. This mirrors current main.py discipline.
- The AST blocklist test `test_main_no_forbidden_imports` continues to scan only main.py — green by construction since main.py becomes thin.
- Daughter modules are not currently in any blocklist; that hex discipline lives at code-review time. Future plan can extend the AST guard.

## Test-import-parity strategy (Option A confirmed)

main.py shim re-exports every symbol AND module attribute that tests reference via `main.X`. Tests do not need editing.

## Pre-split sanity (recorded)

```
$ wc -l main.py
2037 main.py

$ .venv/bin/python main.py --version
v1.2.0

$ .venv/bin/python -m pytest tests/test_main.py tests/test_scheduler.py -q
140 passed in 3.41s
```

## Manifest summary

7 plan-required new modules + 2 daughter modules from daily_run overage = 9 new files plus a thin main.py.
- main.py: ~130 LOC (target <150)
- cli_parser.py: ~106 LOC
- interactive.py: ~217 LOC
- scheduler_driver.py: ~113 LOC
- crash_boundary.py: ~203 LOC
- state_actions.py: ~25 LOC
- daily_loop.py: ~30 LOC (orchestration shim)
- daily_run.py: ~530 LOC (within ±10% of 500 = 550)
- daily_run_helpers.py: ~415 LOC
- paper_trade_alerts.py: ~135 LOC

All within plan §M1 (500 LOC ±10% = 550 ceiling).

## Execution sequence (per plan §revision-fix warning-2)

1. **Task 1** (this file): manifest validated.
2. **Task 2a:** create cli_parser.py + scheduler_driver.py (low-dependency seams). Add temp re-exports at top of main.py. Run `pytest -x`. Sanity `python main.py --version`.
3. **Task 2b:** create daily_run.py + daily_run_helpers.py + paper_trade_alerts.py + state_actions.py + crash_boundary.py + interactive.py + daily_loop.py + final main.py shim. Prune main.py. Run `pytest tests/test_main.py tests/test_scheduler.py -x`. Run full suite.
4. **Task 3:** create tests/test_main_split_seam.py with 7 parity tests. Plus an extra test asserting daily_run_helpers.py / paper_trade_alerts.py also stay under 500 LOC.
