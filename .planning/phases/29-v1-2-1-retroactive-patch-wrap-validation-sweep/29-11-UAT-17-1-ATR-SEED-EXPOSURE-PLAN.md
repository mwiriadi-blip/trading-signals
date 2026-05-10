---
phase: 29
plan_id: 29-11-UAT-17-1-ATR-SEED-EXPOSURE
plan: 11
type: execute
wave: 3
depends_on: []
requirements: []
files_modified:
  - signal_engine.py
  - dashboard_legacy/trace_panels.py
  - daily_run.py
  - tests/test_trace_atr_seed.py
autonomous: true
must_haves:
  truths:
    - "Trace panel surfaces the engine's persisted Wilder ATR seed at the start of the displayed OHLC window."
    - "Hand-recalc reads the seed at window-start and converges to the displayed ATR within 1e-6 tolerance."
    - "Regression test: synthetic OHLC fixture asserts `abs(hand_recalc - displayed_atr) < 1e-6` using the persisted seed."
  artifacts:
    - path: "signal_engine.py"
      provides: "ATR seed extraction at window-start (function exposing the engine's Wilder seed for the displayed window)"
      contains: "atr_seed"
    - path: "dashboard_legacy/trace_panels.py"
      provides: "Trace Indicators panel renders ATR seed value alongside the displayed window"
      contains: "atr_seed"
    - path: "daily_run.py"
      provides: "Persists ATR seed alongside `vote_params` + `indicator_scalars` on every signal-row write"
      contains: "atr_seed"
    - path: "tests/test_trace_atr_seed.py"
      provides: "Hand-recalc convergence test against persisted seed"
      contains: "abs(hand_recalc - displayed_atr) < 1e-6"
  key_links:
    - from: "signal_engine.compute_atr (full-history Wilder)"
      to: "persisted signal row at daily_run write site"
      via: "atr_seed field in sig dict"
      pattern: "atr_seed"
    - from: "persisted atr_seed"
      to: "trace panel render"
      via: "_render_trace_indicators reads sig_dict['atr_seed']"
      pattern: "sig_dict.*atr_seed|sig\\.get\\(.atr_seed."
---

<objective>
Resolve Phase 28 FAIL UAT-17-1 per D-03: expose the engine's persisted Wilder ATR seed in the trace panel so a hand-recalc starting from the displayed window's first bar converges to the displayed ATR within 1e-6 tolerance. Honours project LEARNING 2026-05-10 (read engine-resolved persisted values; never re-derive from defaults). Locality discipline matches Phase 17 polish commit `587b6f0`.

Purpose: 28-VERIFICATION.md UAT-17-1 evidence: ATR drift 1.22730353 — displayed=88.888811 vs 40-bar-window-recalc=87.66... — because the engine's ATR is computed over FULL history but the trace shows a 40-bar window without the seed. Solution: surface the engine's seed at window-start so the recalc has a deterministic anchor.
Output: signal_engine seed surface + persistence in daily_run + trace render of seed + convergence test.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-CONTEXT.md
@.planning/phases/28-v1-2-uat-closure/28-VERIFICATION.md
@.claude/LEARNINGS.md

<read_first>
- `signal_engine.py` — `_wilder_smooth`, `_true_range`, `compute_atr` (around lines 58-100); `resolve_vote_params` (precedent for engine-resolved value persistence per commit 587b6f0)
- `dashboard_legacy/trace_panels.py:65-150` (`_render_trace_indicators`) and `:184-217` (`_render_trace_panels`) — where the seed must be surfaced
- `daily_run.py` — find the signal-row write path that persists `vote_params` + `indicator_scalars` (`grep -n "vote_params\\|indicator_scalars" daily_run.py`); the seed gets persisted alongside them
- `28-VERIFICATION.md` UAT-17-1 row (full evidence + repro: `pytest -m uat tests/uat/test_uat_17_atr_handcalc.py`)
- `tests/uat/test_uat_17_atr_handcalc.py` (existing UAT test; the FAIL is locked here — passing it post-fix verifies the closure)
- 29-CONTEXT.md §D-03 (the contract: expose seed, NOT widen window, NOT loosen tolerance)
- Project-local LEARNING 2026-05-10 trace-panel-drift entry (the locality model)
- `tests/oracle/wilder.py` (the pure-loop reference oracle)
</read_first>

<interfaces>
The Wilder ATR convergence is deterministic from a known seed. Given:
- `seed_value` = engine's smoothed ATR at the bar immediately BEFORE the displayed window's first bar
- `seed_index` = bar position relative to the displayed window (always -1, since seed is "the bar before window[0]")
- TR series for the 40 displayed bars

The Wilder smoothing recurrence `atr[i] = (atr[i-1] * (period-1) + tr[i]) / period` (with `period=14`), starting from `atr[-1] = seed_value`, walks forward through the 40 bars and produces the displayed ATR at `atr[39]`. This MUST equal the engine's full-history ATR within float ULP (the engine is doing the same recurrence over full history).

API shape (planner's recommendation; executor adjusts to actual codebase):
1. New helper `signal_engine.atr_seed_for_window(history_df, window_start_index, period=14) -> float` returns the Wilder ATR value at `history_df.iloc[window_start_index - 1]` (or NaN if window starts within seed-warmup). Uses the same `_wilder_smooth` so the value is bit-identical to what `compute_atr` produced.
2. `daily_run.py` calls this when writing the signal row; stores result as `sig['atr_seed']` next to `sig['indicator_scalars']` and `sig['vote_params']`.
3. `_render_trace_indicators(indicator_scalars, bars_available, atr_seed=None)` accepts the seed; renders an extra row "ATR seed (bar -1)" with the persisted value, immediately above the ATR(14) row, with a tooltip explaining "Wilder seed at bar -1 — hand-recalc starts here".
4. `_render_trace_panels` extracts `sig_dict.get('atr_seed')` and threads it through.
5. Defensive fallback: if `atr_seed` is missing (legacy state.json rows), render the seed cell as "(stale row — refresh after next 08:00 cycle)" — same backfill discipline as `bb780af`.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Expose ATR seed in signal_engine + persist in daily_run</name>
  <files>signal_engine.py, daily_run.py</files>
  <read_first>
    - signal_engine.py (full file or at least lines 1-150) — `_wilder_smooth`, `_true_range`, `compute_atr`
    - daily_run.py — the signal-row write site; grep for `'vote_params'` and `'indicator_scalars'` to locate it
    - tests/oracle/wilder.py (reference oracle — the contract `_wilder_smooth` matches bit-for-bit)
    - 29-CONTEXT.md §D-03 (locality model)
    - Project-local LEARNING 2026-05-10 trace-panel-drift (the failure mode being locked out)
  </read_first>
  <action>
    Per D-03:

    1. **In `signal_engine.py`**: add a new helper `atr_seed_for_window(history_df: pd.DataFrame, window_start_index: int, period: int = 14) -> float`. Implementation:
       - Compute `tr_full = _true_range(history_df)`.
       - Compute `atr_full = _wilder_smooth(tr_full, period)`.
       - If `window_start_index - 1 < 0` or `atr_full.iloc[window_start_index - 1]` is NaN → return float('nan').
       - Otherwise return `float(atr_full.iloc[window_start_index - 1])`.
       This walks the same code path `compute_atr` uses, guaranteeing bit-identical seed.

    2. **In `daily_run.py`**: at the signal-row construction site (where `sig['indicator_scalars']` and `sig['vote_params']` are written), also write `sig['atr_seed'] = signal_engine.atr_seed_for_window(history_df, window_start_index)`. The `window_start_index` corresponds to the start of the displayed `ohlc_window` (40 bars). Trace through the existing logic to find this index — it's typically `len(history_df) - len(ohlc_window)`.

    3. The hex-boundary contract: `daily_run.py` already imports from `signal_engine`, no new violations. `_HEX_PATHS_STDLIB_ONLY` is unchanged.

    File-size cap: both files ≤500 LOC (or the existing limit if signal_engine.py is already over due to retro inheritance — preserve current size, do not regress). If `signal_engine.py` is already at the cap, the seed helper is small (≤15 LOC) — confirm no overage at write time.
  </action>
  <acceptance_criteria>
    - `grep -q "def atr_seed_for_window" signal_engine.py` succeeds.
    - `grep -q "atr_seed" daily_run.py` succeeds (the assignment site).
    - `python -c "import signal_engine; import inspect; assert 'atr_seed_for_window' in dir(signal_engine); sig = inspect.signature(signal_engine.atr_seed_for_window); assert 'history_df' in sig.parameters and 'window_start_index' in sig.parameters and 'period' in sig.parameters"` rc=0.
    - `python -c "import signal_engine, pandas as pd, numpy as np; df = pd.DataFrame({'high': np.linspace(100,110,30), 'low': np.linspace(99,109,30), 'close': np.linspace(99.5,109.5,30)}); s = signal_engine.atr_seed_for_window(df, 20); assert isinstance(s, float)"` rc=0 and prints (no exception).
    - Full default suite green: `.venv/bin/pytest -q` rc=0.
    - `wc -l signal_engine.py daily_run.py` ≤500 each (or unchanged if already over).
  </acceptance_criteria>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && grep -q "def atr_seed_for_window" signal_engine.py && grep -q "atr_seed" daily_run.py && .venv/bin/python -c "import signal_engine, pandas as pd, numpy as np; df = pd.DataFrame({'high': np.linspace(100,110,30), 'low': np.linspace(99,109,30), 'close': np.linspace(99.5,109.5,30)}); s = signal_engine.atr_seed_for_window(df, 20); assert isinstance(s, float); print('OK seed', s)"</automated>
  </verify>
  <done>Engine exposes seed via `atr_seed_for_window`; daily_run persists it in the signal row alongside vote_params + indicator_scalars.</done>
</task>

<task type="auto">
  <name>Task 2: Render ATR seed in trace panel + hand-recalc convergence test</name>
  <files>dashboard_legacy/trace_panels.py, tests/test_trace_atr_seed.py</files>
  <read_first>
    - dashboard_legacy/trace_panels.py:65-217 (`_render_trace_indicators` + `_render_trace_panels`)
    - signal_engine.py (the `_wilder_smooth` recurrence — the test mirrors it for hand-recalc)
    - tests/oracle/wilder.py (reference oracle the test can use as a sanity backstop)
    - 28-VERIFICATION.md UAT-17-1 evidence cell (1e-6 tolerance, the hand-recalc shape)
    - 29-CONTEXT.md §D-03
  </read_first>
  <action>
    1. **In `dashboard_legacy/trace_panels.py`**: extend `_render_trace_panels` to extract `atr_seed = sig_dict.get('atr_seed')`. Pass `atr_seed` into `_render_trace_indicators` as a new keyword argument. Default is `None` (legacy rows).

    2. In `_render_trace_indicators`, before the ATR(14) row, render an "ATR seed (bar -1)" row showing the persisted seed (formatted to 6 decimals) with a tooltip-attribute that explains "Wilder seed at bar before window — hand-recalc starts here". If `atr_seed is None` or `math.isnan(atr_seed)`, render the cell as `<em>(stale row — refresh after next 08:00 cycle)</em>` (same backfill UX shape as `bb780af` did for vote_params). All values pass through `html.escape` (T-17-03 XSS defence-in-depth).

    3. **Create `tests/test_trace_atr_seed.py`** with `TestAtrSeedExposure`:
       - `test_atr_seed_persisted_in_signal_row` — build a 50-bar synthetic OHLC fixture; call the daily-run signal-row construction path (or `signal_engine.atr_seed_for_window` directly with `window_start_index=10` for a 40-bar window into 50 bars); assert returned value is a finite float.
       - `test_handcalc_converges_to_displayed_atr_within_1e-6` — synthetic OHLC fixture (50 bars, deterministic numeric ramp); call `compute_atr` to get the engine's full-history ATR at bar 49; call `atr_seed_for_window` to get the seed at bar 9 (start of last 40); manually run the Wilder recurrence forward from the seed through bars 10..49 using `atr[i] = (atr[i-1]*13 + tr[i]) / 14`; assert `abs(hand_recalc - engine_atr) < 1e-6`.
       - `test_legacy_signal_row_renders_stale_message` — render `_render_trace_panels` with `sig_dict` that has no `atr_seed` key; assert rendered HTML contains "stale row" or equivalent backfill copy AND does NOT crash.
       - `test_trace_panel_renders_seed_value` — `sig_dict` with `atr_seed=42.123456`; render; assert HTML contains `42.123456` (formatted to 6dp) AND a row label like "ATR seed".

    4. The full-loop reproducibility: a Phase 28 `tests/uat/test_uat_17_atr_handcalc.py` ALREADY EXISTS — once the seed is exposed and rendered, that test should now PASS. Plan 29-14 (closure) verifies this.

    Both files ≤500 LOC. Test file estimated ~80 LOC.
  </action>
  <acceptance_criteria>
    - `grep -q "atr_seed" dashboard_legacy/trace_panels.py` succeeds.
    - `grep -q "ATR seed" dashboard_legacy/trace_panels.py` succeeds (the row label).
    - `test -f tests/test_trace_atr_seed.py` succeeds.
    - `grep -q "test_handcalc_converges_to_displayed_atr_within_1e-6" tests/test_trace_atr_seed.py` succeeds.
    - `grep -q "abs(hand_recalc - " tests/test_trace_atr_seed.py` succeeds (or equivalent comparison).
    - `grep -q "1e-6\\|0.000001" tests/test_trace_atr_seed.py` succeeds (the tolerance).
    - `pytest tests/test_trace_atr_seed.py -x -q` rc=0.
    - Full default suite green: `.venv/bin/pytest -q` rc=0.
    - `wc -l dashboard_legacy/trace_panels.py tests/test_trace_atr_seed.py` ≤500 each.
  </acceptance_criteria>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && .venv/bin/pytest tests/test_trace_atr_seed.py -x -q && grep -q "atr_seed" dashboard_legacy/trace_panels.py && grep -q "ATR seed" dashboard_legacy/trace_panels.py</automated>
  </verify>
  <done>Trace panel renders persisted ATR seed; hand-recalc test asserts <1e-6 convergence against synthetic fixture; legacy-row fallback renders without crash.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| persisted signal row ↔ trace renderer | seed must be engine-recorded, never re-derived |
| OHLC scalar fields ↔ HTML render | XSS defence-in-depth at render |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-29-11-01 | Tampering (drift) | Future commit re-derives seed from defaults instead of reading persisted value | mitigate | `test_handcalc_converges_to_displayed_atr_within_1e-6` + project LEARNING reference in module docstring |
| T-29-11-02 | Tampering (XSS) | atr_seed numeric field renders as raw HTML | mitigate | `html.escape` defence-in-depth on render (matches existing T-17-03 pattern) |
| T-29-11-03 | DoS (compute) | atr_seed_for_window doubles full-history Wilder smoothing per signal cycle | accept | One extra ~O(N) pass per market per day, <1ms total impact |
</threat_model>

<verification>
- `pytest tests/test_trace_atr_seed.py -q` rc=0.
- Full suite green: `.venv/bin/pytest -q` rc=0.
- Phase 28 UAT regression: `pytest -m uat tests/uat/test_uat_17_atr_handcalc.py -q` PASSES (this is the closure check Plan 29-14 verifies).
</verification>

<success_criteria>
Phase 28 FAIL UAT-17-1 has a passing automated regression. ATR(14) hand-recalc converges within 1e-6 against persisted seed. Plan 29-14 appends PASS row to 28-VERIFICATION.md citing this plan.
</success_criteria>

<output>
After completion, create `.planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-11-SUMMARY.md`.
</output>