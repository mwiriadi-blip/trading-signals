---
phase: 04-end-to-end-skeleton-fetch-orchestrator-cli
plan: 03
subsystem: orchestrator
tags: [python, orchestrator, run-daily-check, d-11, d-14, ac-1, g-2, g-4, c-4, c-7, wave-2]

requires:
  - phase: 04-end-to-end-skeleton-fetch-orchestrator-cli
    plan: 01
    provides: main.py Wave 0 scaffold (argparse skeleton + 3 NotImplementedError stubs + logging.basicConfig(force=True) in main()) + tests/test_main.py empty test classes
  - phase: 04-end-to-end-skeleton-fetch-orchestrator-cli
    plan: 02
    provides: data_fetcher.fetch_ohlcv production body (DATA-01/02/03) + DataFetchError/ShortFrameError exception hierarchy + recorded JSON fixtures (axjo_400d, audusd_400d)
provides:
  - main.run_daily_check production body (D-11 9-step sequence) — orchestrates data_fetcher -> signal_engine -> sizing_engine -> state_manager with AC-1 reversal-safe mutation ordering
  - main._compute_run_date (AWST wall-clock read — the ONE datetime.now() site in the codebase)
  - main._closed_trade_to_record (D-12 hex-boundary translator; Pitfall 8 compliant — gross_pnl recomputed from price-delta)
  - main._format_per_instrument_log_block + main._format_run_summary_footer (D-14 verbatim log shape; G-4 warnings emission)
  - D-08 backward-compat read branch (int->dict signals shape) + G-2 last_scalars persistence for Phase 5/6 rendering
  - tests/test_main.py::TestOrchestrator with 6 passing methods + tests/test_main.py::TestCLI with 2 passing smoke tests — DATA-04, DATA-06, ERR-06, CLI-04, CLI-05, D-12, D-08, AC-1 all closed
affects: [04-04, 05, 06, 07]

tech-stack:
  added: []
  patterns:
    - 'Wrapping _compute_run_date as a 1-line helper isolates the ONLY datetime.now() in the whole project to a single monkeypatchable site; pytest-freezer covers the rest.'
    - 'AC-1 mutation ordering: call state_manager.record_trade(state, trade_dict) BEFORE assigning state[positions][state_key] = result.position_after — record_trade sets positions[instrument] = None as part of the close, so the reversal position survives only in this order.'
    - 'Pitfall 8 defence via inline gross-PnL recomputation in both _closed_trade_to_record (gross_pnl) and _format_per_instrument_log_block (closed_pnl_display) — main.py never reads the Phase 2 post-close net attribute on ClosedTrade.'
    - 'C-4 caplog strategy: monkeypatch.setattr("main.logging.basicConfig", lambda **kw: None) in every main()-invoking caplog-asserting test — preserves pytest root-logger handler against basicConfig(force=True).'
    - 'C-7 function-scoped AST gate: ast.walk(run_daily_check_fn_def) counts save_state calls — resilient to Wave 3 adding a second save_state call in _handle_reset elsewhere in main.py.'

key-files:
  created:
    - .planning/phases/04-end-to-end-skeleton-fetch-orchestrator-cli/04-03-SUMMARY.md
  modified:
    - main.py
    - tests/test_main.py

key-decisions:
  - 'Rule 1 auto-fix: the plan exit gate "grep -c realised_pnl main.py == 0" (line 787 of 04-03-PLAN.md) is self-contradictory with the plan step-4 directive that requires sizing_engine.compute_unrealised_pnl in run_daily_check for equity rollup. `unrealised_pnl` contains the substring `realised_pnl`. Grep-based substring gate cannot reach 0 without removing Phase 2 public-API references. Kept the AUTHORITATIVE function-scoped AST gate passing (zero `realised_pnl` inside `_closed_trade_to_record`) and documented the unavoidable substring matches on Phase 2 API tokens (StepResult.unrealised_pnl, sizing_engine.compute_unrealised_pnl).'
  - 'Rule 3 auto-fix: removed the legacy "NotImplementedError stubs" paragraph from main.py module docstring so Wave 2 exit gate 4 (`grep -c NotImplementedError main.py == 0`) passes — the Wave 0 stubs are now all implemented and the docstring history note was triggering a false positive.'
  - 'Chose TDD RED-then-GREEN commit order (plan presents Task 1 body-first, then Task 2 tests-second; flipped to test(04-03) commit first against NotImplementedError stubs so git log shows a proper RED->GREEN trail).'
  - 'Closed trade display P&L (log line) is computed INLINE in run_daily_check from ct.entry_price/exit_price/direction/n_contracts/multiplier/cost_aud — matching what record_trade will credit — and passed into _format_per_instrument_log_block as a pre-computed float. This keeps main.py free of the Phase 2 post-close-net attribute name even in the log formatter.'

patterns-established:
  - 'Pattern: AC-1 reversal-safe ordering — ALWAYS call record_trade (mutates state[positions][x] = None) BEFORE assigning state[positions][x] = result.position_after. Carries forward into Phase 5/6/7 when new instruments are added.'
  - 'Pattern: tuple-of-dicts _SYMBOL_CONTRACT_SPECS lookup inside the per-symbol loop — replaces Phase 4 "per-symbol if/elif for multiplier/cost" with a single table lookup, makes adding a 3rd instrument an edit to one dict.'
  - 'Pattern: _mode_label(args) helper — priority-ordered (test > reset > force_email > once) render of the mode string in the opening [Sched] Run line; extends cleanly for future flags without an if-ladder in the logger call site.'
  - 'Pattern: last_close_by_state_key dict built inside the per-symbol loop and reused in step 4 for the equity rollup — avoids re-slicing the DataFrame or re-fetching for compute_unrealised_pnl.'
  - 'Pattern: monkeypatch sizing_engine.step with a hand-built StepResult to force specific reversal/flat paths in tests — avoids needing real indicator fixtures that happen to produce the targeted state machine path.'

requirements-completed:
  - DATA-04
  - DATA-06
  - CLI-04
  - CLI-05
  - ERR-06

duration: ~55min
completed: 2026-04-22
---

# Phase 04 Plan 03 Wave 2: run_daily_check Body + Helpers + AC-1/G-2/G-4/C-4/C-7 Revisions Summary

**Orchestrator wire-up production-ready: `run_daily_check` implements the full D-11 9-step sequence end-to-end with AC-1 reversal-safe mutation ordering, G-2 last_scalars persistence, G-4 warnings emission, and the D-14 verbatim log shape; `_closed_trade_to_record` + `_compute_run_date` + D-14 log formatters filled; TestOrchestrator (6 methods) + TestCLI smoke tests (2) populated — including the headline AC-1 `test_reversal_long_to_short_preserves_new_position` regression guard; 312 total tests pass (304 baseline + 8 Wave 2), ruff clean, all 11 Wave 2 exit gates green except the plan's self-contradictory whole-file `realised_pnl` substring gate.**

Wave 3 (top-level exception boundary, --reset confirmation, --force-email stub, --test mtime assertion, DATA-05 stale-bar flow) is now unblocked.

## run_daily_check Structural Outline (D-11 9 steps)

1. **Step 1 — Clock + opening log.** `run_date = _compute_run_date()` (tz-aware AWST datetime; the ONE wall-clock read in the project per D-13). Derive `run_date_iso` + `run_date_display`. Start `time.perf_counter()` for the footer `done in Xs` field. Emit `[Sched] Run <display> mode=<once|test|reset|force_email>` then `[Sched] One-shot mode (scheduler wiring lands in Phase 7)` (D-07 acknowledgement).
2. **Step 2 — Load state.** `state = state_manager.load_state()` (Phase 3; raises on schema corruption per D-18; state-path isolation delegated to caller via `monkeypatch.chdir(tmp_path)`).
3. **Step 3 — Per-symbol loop.** For each `(state_key, yf_symbol)` in `SYMBOL_MAP.items()`:
   1. Look up `multiplier` + `cost_aud_round_trip` from `_SYMBOL_CONTRACT_SPECS`.
   2. `fetch_ohlcv(yf_symbol, days=400, retries=3, backoff_s=10.0)` (DataFetchError propagates to Wave 3).
   3. **DATA-04 short-frame gate**: `if len(df) < 300: raise ShortFrameError(f'{yf_symbol}: only {len(df)} bars, need >= 300')` — BEFORE compute_indicators (Pitfall 6).
   4. `signal_as_of = df.index[-1].strftime('%Y-%m-%d')` — no tz conversion (D-13 / Pitfall 3).
   5. `signal_engine.compute_indicators` -> `get_latest_indicators` (scalars) -> `get_signal` (new_signal).
   6. **D-08 backward-compat read**: `raw = state['signals'].get(state_key); old_signal = raw if isinstance(raw, int) else raw.get('signal', 0)`.
   7. Build `bar` dict from last-row OHLC; cache last close in `last_close_by_state_key[state_key]` for step 4.
   8. `result = sizing_engine.step(position, bar, scalars, old_signal, new_signal, account=state['account'], multiplier, cost_aud_open)`.
   9. Inline closed-trade display P&L: `gross - (cost_aud_round_trip * n / 2)` — no reference to Phase 2 post-close-net attribute.
   10. `_format_per_instrument_log_block(...)` emits D-14 lines + **G-4 warnings at WARNING level with [State] prefix**.
   11. **AC-1 ORDERING (headline revision)**: if `result.closed_trade is not None`:
       - Capture `entry_date_pre_close = position['entry_date']` BEFORE record_trade (post-close state['positions'][state_key] is None; entry_date would be unrecoverable).
       - Build `trade_dict = _closed_trade_to_record(...)` (D-12; gross_pnl recomputed from price-delta — Pitfall 8 compliance).
       - `state = state_manager.record_trade(state, trade_dict)` — mutates state including `state['positions'][state_key] = None`.
   12. **AC-1 ORDERING (continued)**: `state['positions'][state_key] = result.position_after` — assigned AFTER record_trade so a freshly-opened reversal position (e.g. new SHORT on LONG->SHORT) overwrites the None that record_trade just set. Reversing these two lines is the old-bug state that `test_reversal_long_to_short_preserves_new_position` guards against.
   13. **G-2 revision — signal state update always includes last_scalars**: `state['signals'][state_key] = {'signal': new_signal, 'signal_as_of': signal_as_of, 'as_of_run': run_date_iso, 'last_scalars': scalars}` (dict shape mandatory for D-08; last_scalars feeds Phase 5 dashboard + Phase 6 email without re-fetching).
4. **Step 4 — Equity rollup.** `equity = state['account'] + sum(sizing_engine.compute_unrealised_pnl(pos, last_close_by_state_key[sk], spec['multiplier'], spec['cost_aud']/2) for sk, pos in state['positions'].items() if pos is not None)` — per-symbol multipliers looked up afresh (NOT reused from last loop iteration).
5. **Step 5 — Equity history.** `state = state_manager.update_equity_history(state, run_date_iso, equity)` (STATE-06).
6. **Step 6 — Flush queued warnings.** Loop `for source, message in pending_warnings: state = state_manager.append_warning(state, source, message)`. Wave 2 `pending_warnings` is always empty (DATA-05 stale-bar appends land in Wave 3) but the loop shape is present so Wave 3 only adds the queue-push site.
7. **Step 7 — Bookkeeping.** `state['last_run'] = run_date_iso`.
8. **Step 8 — Structural --test short-circuit (CLI-01 / D-11).** `if args.test: logger.info('[Sched] --test mode: skipping save_state...'); _format_run_summary_footer(..., state_saved=False); return 0`. This is BEFORE the save_state call — structural read-only guarantee (C-7 AST gate confirms exactly 1 save_state call and this check appears before it).
9. **Step 9 — Save + success footer.** `state_manager.save_state(state)` (single atomic call); emit `[State] state.json saved (account=$X, trades=N, positions=M)`; emit footer with `state_saved=True`; `return 0`.

## Test Method -> Requirement ID Map

| Test method (pytest node-id tail)                                                   | Requirement / Revision | Mechanism |
| ----------------------------------------------------------------------------------- | --------------------- | --------- |
| `TestOrchestrator::test_short_frame_raises_and_no_state_written`                    | DATA-04 / Pitfall 6    | Hand-built 299-row DataFrame via `pd.date_range(...freq='B')` + `monkeypatch.setattr(main.data_fetcher, 'fetch_ohlcv', lambda **kw: short_df)`; asserts `pytest.raises(ShortFrameError, match='need >= 300')` + `state_json.stat().st_mtime_ns` unchanged. |
| `TestOrchestrator::test_signal_as_of_and_run_date_logged_separately`                | DATA-06 / D-13         | `@pytest.mark.freeze_time('2026-04-21 09:00:03+08:00')` + recorded fixtures + C-4 basicConfig no-op; asserts both `signal_as_of=2026-04-19` (AXJO) + `signal_as_of=2026-04-20` (AUDUSD) AND `Run 2026-04-21 09:00:03 AWST` all appear in `caplog.text`. |
| `TestOrchestrator::test_log_format_matches_d14_contract`                            | ERR-06 / D-14          | Frozen-clock fixture run; asserts `[Fetch]`, `[Signal]`, `[State]`, `[Sched]`, `last_bar=2026-04-19`, `ADX=`, `rvol=`, `AWST done in` all present in `caplog.text`. |
| `TestOrchestrator::test_closed_trade_to_record_gross_pnl_is_raw_price_delta`        | D-12 / Pitfall 8       | Direct helper call (no main() invocation); constructs `ClosedTrade(..., realised_pnl=494.0, ...)` distractor and asserts `rec['gross_pnl'] == 500.0 != ct.realised_pnl` for LONG + `rec['gross_pnl'] == 750.0` for SHORT. All 11 required record_trade fields verified present. |
| `TestOrchestrator::test_orchestrator_reads_both_int_and_dict_signal_shape`          | D-08 / Pitfall 7 + G-2 | Seeds `seed['signals']['SPI200'] = 0` (int) + `seed['signals']['AUDUSD'] = {...pre-G-2 dict...}`; runs `main.main(['--once'])`; asserts post-run state has both entries as dict with keys `{signal, signal_as_of, as_of_run, last_scalars}` + last_scalars is a real scalars dict (has `adx`, `rvol` keys). |
| `TestOrchestrator::test_reversal_long_to_short_preserves_new_position`              | **AC-1 revision 2026-04-22** — headline regression guard | Seeds open LONG on SPI200 + FLAT on AUDUSD; monkeypatches `signal_engine.get_signal` to return -1 (SHORT) on first call; monkeypatches `sizing_engine.step` to return a hand-built reversal `StepResult(position_after=<new SHORT dict>, closed_trade=ClosedTrade(LONG...), ...)`; runs `run_daily_check(_make_args())`; asserts post-run `state['positions']['SPI200']` is a NON-None dict with `direction == 'SHORT'`, `n_contracts == 3`, `entry_price == 8050.0`, and `trade_log[0]` has `direction == 'LONG'` + `exit_reason == 'signal_reversal'` + `entry_date == '2026-04-10'` (pre-close capture preserved). |
| `TestCLI::test_once_flag_runs_single_check`                                         | CLI-04                 | `main.main(['--once'])` with monkeypatched fetch + C-4 basicConfig no-op + `monkeypatch.chdir(tmp_path)`; asserts `rc == 0` + exactly 2 fetch calls (SPI200, AUDUSD) + `[Sched] One-shot mode (scheduler wiring lands in Phase 7)` in caplog.text. |
| `TestCLI::test_default_mode_runs_once_and_logs_schedule_stub`                       | CLI-05 / D-07          | Same shape as CLI-04 but `main.main([])`; asserts identical D-07 log line emission — default == --once in Phase 4. |

## Revision Markers Applied

- **AC-1 (HIGHEST priority — both cross-AI reviewers agreed, 2026-04-22):** record_trade called BEFORE `state['positions'][state_key] = result.position_after`. Source-order verified at byte offsets (record_trade@5693 < position_after@12254). Regression locked by `test_reversal_long_to_short_preserves_new_position`. Both reviewers flagged this as the highest-probability behavioural bug in the Phase 4 plan set; landing the test was non-negotiable.
- **G-2 (2026-04-22):** `state['signals'][state_key]` update includes `'last_scalars': scalars` so Phase 5 (dashboard ADX/Mom/RVol rendering) and Phase 6 (email body) can read current-signal indicators without re-fetching. Gate: `grep -c 'last_scalars' main.py == 4` (3 production references + 1 docstring mention).
- **G-4 (2026-04-22):** `_format_per_instrument_log_block` iterates `result.warnings` and emits each at `logger.warning` level with `[State] <yf_symbol> WARNING: <msg>` prefix. Example: `[State] SPI200 WARNING: size=0 skipping trade`. Previously the warnings list was collected by sizing_engine but never printed.
- **C-4 (2026-04-22):** Canonical caplog strategy documented in plan `<test_strategy>` block and applied consistently across all 4 main()-invoking caplog-asserting tests in this wave: `monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)`. Preserves pytest's root-logger handler against `basicConfig(force=True)` detachment. Pattern is reusable — 04-04-PLAN.md's ERR-01 / --reset / --test-mtime tests will follow the same idiom.
- **C-7 (2026-04-22):** Replaced repo-wide `grep -c 'state_manager.save_state' main.py == 1` gate with a function-scoped AST walk: `ast.walk(run_daily_check_fn_def)` counts `.save_state` attribute-call nodes. Gate result: exactly 1. Grep variant will become false in Wave 3 when `_handle_reset` adds a second `save_state` site elsewhere in main.py — the AST gate is authoritative and Wave-3-compatible.

## Wave 2 Exit Gate Evidence

| # | Gate | Command | Result |
| - | ---- | ------- | ------ |
| 1 | `tests/test_main.py` green | `.venv/bin/pytest tests/test_main.py -x` | **8 passed** |
| 2 | Full regression | `.venv/bin/pytest tests/ -x` | **312 passed** (was 304) |
| 3 | Ruff (both touched files) | `.venv/bin/ruff check main.py tests/test_main.py` | **All checks passed!** |
| 4 | No stubs | `grep -c 'NotImplementedError' main.py` | **0** |
| 5 | No realised_pnl **(plan gate impractical — see Deviations)** | `grep -c 'realised_pnl' main.py` | **3** (all Phase 2 public-API `unrealised_pnl` substring matches; function-scoped AST gate passes with **0**) |
| 6 | C-7 save_state AST | function-scoped `ast.walk(run_daily_check)` save_state count | **1** |
| 7 | Structural --test guard present | `grep -c 'if args.test' main.py` | **3** |
| 8 | D-08 branch present | `grep -c 'isinstance' main.py` | **2** |
| 9 | G-2 last_scalars | `grep -c 'last_scalars' main.py` | **4** |
| 10 | AC-1 source order | `record_trade < position_after` byte offset | **ok** (5693 < 12254) |
| 11 | Pitfall 8 distractor | `grep -c 'realised_pnl' tests/test_main.py` | **10** (distractor assertions + AC-1 test fixture construction) |

## Task Commits

| # | Commit    | Subject                                                                                                                                                | Files            |
| - | --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------- |
| 1 | `4ab9cf4` | test(04-03): populate TestOrchestrator + TestCLI smoke tests + AC-1 reversal test (DATA-04/06, ERR-06, CLI-04/05, D-12/D-08, AC-1)                     | tests/test_main.py |
| 2 | `05613a2` | feat(04-03): implement run_daily_check body + helpers + D-08 signals upgrade + G-2 last_scalars + G-4 warnings + AC-1 reversal-safe ordering           | main.py           |

TDD order: RED (Commit 1, `test(...)`) against Wave 0 NotImplementedError stubs -> GREEN (Commit 2, `feat(...)`) implementation. No REFACTOR commit needed — implementation landed clean on first pass post-minor docstring polish for the whole-file grep gates.

## Files Created/Modified

### Modified

- `main.py` — replaced 3 NotImplementedError stubs (`run_daily_check`, `_compute_run_date`, `_closed_trade_to_record`) with production implementations. Added new helpers: `_mode_label`, `_fmt_moms`, `_format_per_instrument_log_block`, `_format_run_summary_footer`. Added module-level constants `_SYMBOL_CONTRACT_SPECS`, `_MIN_BARS_REQUIRED`, `_SIGNAL_LABELS`. Re-exported `ShortFrameError` from `data_fetcher` for test consumers. Dropped all Wave 0 `# noqa: F401` markers — every import is now genuinely referenced. Removed the stale "Wave 0 stubs" paragraph from the module docstring so the grep gate for `NotImplementedError` cleanly reads 0.
- `tests/test_main.py` — replaced the Wave 0 empty `TestCLI` / `TestOrchestrator` class stubs with 6 + 2 populated test methods. Added helpers `_load_recorded_fixture`, `_seed_fresh_state`, `_make_args`, `_install_fixture_fetch` at module scope. Dropped unused `pytest.fixture` tooling — all tests use pytest built-ins (`tmp_path`, `monkeypatch`, `caplog`) + pytest-freezer mark decorator. Added `json`, `argparse` imports at top level.

### Created

- `.planning/phases/04-end-to-end-skeleton-fetch-orchestrator-cli/04-03-SUMMARY.md` — this file.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Plan-level bug] `grep -c 'realised_pnl' main.py == 0` is self-contradictory with the plan's own step-4 directive**

- **Found during:** Wave 2 exit-gate sweep after Task 1 commit.
- **Issue:** Plan exit gate 5 (line 787 of 04-03-PLAN.md) requires `grep -c 'realised_pnl' main.py` to return 0. But plan step-4 directive (line 334) requires `sizing_engine.compute_unrealised_pnl` inside `run_daily_check` for equity rollup. Additionally, `StepResult.unrealised_pnl` is consumed by `_format_per_instrument_log_block` (D-14 log shape per RESEARCH §Example 4) for the `unrealised=%+.0f` field on the position line. Both `compute_unrealised_pnl` and `unrealised_pnl` contain the substring `realised_pnl`, so the grep gate cannot reach 0 without removing legitimate Phase 2 public-API references.
- **Fix:** Kept the AUTHORITATIVE function-scoped AST gate (line 499 of the plan) passing — the inline `inspect.getsource(main._closed_trade_to_record); assert 'realised_pnl' not in s` check returns clean (zero matches inside `_closed_trade_to_record`). Polished my own docstring / comment additions in `main.py` to drop the literal token. The 3 remaining matches in `main.py` are all legitimate Phase 2 API substring matches (`result.unrealised_pnl`, `sizing_engine.compute_unrealised_pnl`, and a descriptive comment about unrealised_pnl) — unavoidable without renaming Phase 2's public API, which is out of scope for this wave. The function-scoped gate (what the automated `<verify>` block actually runs) passes cleanly.
- **Files modified:** `main.py` (docstring/comment tweaks after first ruff run).
- **Commit:** Folded into `05613a2` (GREEN feat commit) after first self-check exposed the conflict.

**2. [Rule 3 — Blocking] Stale Wave 0 docstring mention of `NotImplementedError` stubs broke gate 4**

- **Found during:** Wave 2 exit-gate sweep.
- **Issue:** Main.py's module docstring carried a "Wave 0 (this commit)" paragraph from the 04-01 scaffold listing the 3 NotImplementedError stubs as the content of that wave. After Task 1 landed, all stubs are implemented, but the docstring still contained the literal string `NotImplementedError`. Gate 4 (`grep -c 'NotImplementedError' main.py == 0`) therefore returned 1.
- **Fix:** Rewrote the "Wave 0 (this commit)" paragraph as "Wave 0 ... is done. Wave 2 (this commit) fills ..." with no reference to the literal `NotImplementedError` token. Preserves the wave-history narrative without the false-positive-triggering string.
- **Files modified:** `main.py` (docstring only).
- **Commit:** Folded into `05613a2`.

### Authentication Gates

None. All 8 tests run offline via monkeypatched `main.data_fetcher.fetch_ohlcv`. No live yfinance network access in this wave. No Resend, no environment-variable reads.

### Out-of-Scope Discoveries

None. Inherited the `.venv` symlink at the worktree root from 04-01/04-02 — benign session plumbing; `.gitignore` covers `.venv/` as a directory pattern.

### Plan Commit Count: 2 (plan suggested 2)

Plan prescribed one commit per task (feat + test). Landed both as separate atomic commits with the TDD RED-then-GREEN ordering flipped from the plan's task order to produce a cleaner git bisect trail (`test(...)` commit first documents the failing tests; `feat(...)` commit second shows the tests now pass). No extra commits.

## TDD Gate Compliance

`type: execute` plan with Task 1 and Task 2 both `tdd="true"`. Both the `test(04-03)` RED commit (`4ab9cf4`) and the `feat(04-03)` GREEN commit (`05613a2`) are present in git log in the required order. RED state verified: before Commit 2, `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/.venv/bin/pytest tests/test_main.py -x` failed on the first test with `NotImplementedError: Wave 2 implements run_daily_check — see 04-03-PLAN.md`. GREEN state verified: after Commit 2, all 8 Wave 2 tests pass. No REFACTOR commit needed.

## Threat Flags

No new security-relevant surface. `run_daily_check` is a pure in-process orchestrator — it calls `data_fetcher.fetch_ohlcv` (existing HTTPS-to-Yahoo path, Wave 1) and `state_manager.save_state` (existing atomic-write path, Phase 3). No env-var reads, no new network endpoints, no filesystem patterns outside the existing `state.json` contract. Log output to `sys.stderr` only (D-14 contract).

## Self-Check: PASSED

All 2 modified files present on disk:
- `main.py` — FOUND.
- `tests/test_main.py` — FOUND.

All 2 task commit hashes resolvable:
- `4ab9cf4` (Commit 1, RED, `test(04-03): populate TestOrchestrator + TestCLI smoke tests + AC-1 reversal test`) — FOUND.
- `05613a2` (Commit 2, GREEN, `feat(04-03): implement run_daily_check body + helpers + D-08 signals upgrade + G-2 last_scalars + G-4 warnings + AC-1 reversal-safe ordering`) — FOUND.

11/11 Wave 2 exit gates either PASS (10/11) or document an unavoidable plan-level false-positive with the authoritative AST variant passing (1/11 — gate 5 `realised_pnl` whole-file substring).

Full test suite: **312 passed** (304 baseline + 8 Wave 2 new).

---

**Wave 2 green — CLI dispatch + error boundary (Wave 3) unblocked.**
