---
phase: 27
plan: 01
type: execute
wave: 1
parallel: false
depends_on:
  - 27-07-naive-datetime-and-migration-contiguity-PLAN.md
files_modified:
  - pnl_engine.py
  - sizing_engine.py
  - state_manager.py
  - system_params.py
  - tests/test_pnl_engine.py
  - tests/test_decimal_money_math.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "compute_unrealised_pnl + compute_realised_pnl return Decimal (not float)."
    - "All money fields persisted to state.json (account_aud, equity_history rows, paper_trades realised_pnl_aud / unrealised, positions cost_aud_open) round-trip through Decimal without precision drift."
    - "Indicator math (signal_engine.compute_indicators / sizing_engine ATR/ADX/Mom/RVol math) STAYS float64 (hex-boundary preserved — no Decimal in numpy/pandas paths)."
    - "Project-wide quantize policy lives in system_params.AUD_QUANTIZE = Decimal('0.01')."
  artifacts:
    - path: system_params.py
      provides: "AUD_QUANTIZE Decimal constant + helper to_aud(x) -> Decimal"
      contains: "AUD_QUANTIZE"
    - path: pnl_engine.py
      provides: "compute_unrealised_pnl / compute_realised_pnl returning Decimal"
      contains: "Decimal"
    - path: tests/test_decimal_money_math.py
      provides: "round-trip + precision regression tests"
      contains: "Decimal"
  key_links:
    - from: "pnl_engine.compute_unrealised_pnl"
      to: "system_params.AUD_QUANTIZE"
      via: "quantize call at return"
      pattern: "\\.quantize\\(AUD_QUANTIZE"
    - from: "state_manager._migrate_v8_to_v9 (or in-place coercion at load)"
      to: "Decimal(...) on persisted money strings"
      via: "Decimal(str(v))"
      pattern: "Decimal\\(str\\("
---

<objective>
Convert money-denominated arithmetic in pnl_engine.py + sizing_engine.py cost helpers + state_manager.py persisted money fields to Python decimal.Decimal end-to-end. Indicator math stays float64.

Purpose: financial-data integrity (review item #1). Float arithmetic on AUD with cumulative sums + cost subtractions accumulates ULP-level drift; Decimal with explicit quantize gives bit-exact AUD-cent semantics.
Output: Decimal-typed money math, AUD_QUANTIZE constant, round-trip regression test.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/ROADMAP.md
@pnl_engine.py
@sizing_engine.py
@state_manager.py
@system_params.py

<interfaces>
# pnl_engine.py current signatures (float-typed):
#   compute_unrealised_pnl(side, last_close, entry_price, contracts, multiplier, entry_cost_aud) -> float
#   compute_realised_pnl(side, exit_price, entry_price, contracts, multiplier, round_trip_cost_aud) -> float

# sizing_engine.py — touches money via cost_aud_open arg (lines 517, 575). Indicator math (ATR/ADX/Mom/RVol)
# stays float64. Decimal boundary: ONLY the cost-allocation arithmetic (cost_aud_open = cost_aud / 2, applied
# inside step()) becomes Decimal.

# state_manager.py current schema (v8):
#   state['account_aud'] : float
#   state['paper_trades'][i]['realised_pnl_aud'] : float | None
#   state['equity_history'] : list[{'date': str, 'equity_aud': float}]
#   state['positions'][k]['cost_aud_open'] : float
# Bump schema 8 -> 9; _migrate_v8_to_v9 coerces all four fields via Decimal(str(v)).quantize(AUD_QUANTIZE).

# JSON serialisation strategy: Decimal -> str via custom encoder (json.dumps default=lambda o: str(o) if isinstance(o, Decimal)).
# Read path: Decimal(str(loaded_value)) — never float(loaded_value) because that re-enters float arithmetic.

# Hex-boundary: signal_engine.py untouched; sizing_engine indicator math untouched. Only the money slice of
# sizing_engine (cost_aud_open argument flow + step() return cost arithmetic) becomes Decimal.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add AUD_QUANTIZE + Decimal-typed pnl_engine + state_manager round-trip</name>
  <read_first>
    - system_params.py (full file — locate constants block)
    - pnl_engine.py (all 55 lines)
    - state_manager.py lines 60-310 (schema version + _MIGRATIONS dict + load_state)
    - state_manager.py lines 580-710 (save_state + serialisation)
    - tests/test_pnl_engine.py (current float-based assertions; will need allclose -> exact equality on Decimal)
  </read_first>
  <behavior>
    - test_compute_unrealised_pnl_returns_decimal: result is Decimal instance, equals Decimal('-12.50') exactly (not 1e-9 close).
    - test_compute_realised_pnl_returns_decimal: same — Decimal exactness for known oracle case.
    - test_aud_quantize_constant_is_two_dp: system_params.AUD_QUANTIZE == Decimal('0.01').
    - test_state_round_trip_preserves_aud_cents: save_state with account_aud=Decimal('1234.56'), load_state, assert loaded value == Decimal('1234.56') (not 1234.5599999...).
    - test_indicator_math_unchanged: import signal_engine.compute_indicators, run on canonical fixture, assert all-float64 dtype on every indicator column (no accidental Decimal leak into numpy hex).
    - test_v8_to_v9_migration_coerces_money: feed dict with float money fields, _migrate_v8_to_v9 promotes them to Decimal-quantized.
  </behavior>
  <action>
1. **system_params.py:** add at end of constants block (locate `STRATEGY_VERSION` line 27; add new section below it):
   ```python
   from decimal import Decimal
   AUD_QUANTIZE: Decimal = Decimal('0.01')  # Phase 27 #1: AUD cents precision boundary
   def to_aud(x) -> Decimal:
     '''Coerce x (float | int | str | Decimal) to Decimal quantized to AUD_QUANTIZE.'''
     return Decimal(str(x)).quantize(AUD_QUANTIZE)
   ```
   FORBIDDEN_MODULES_STDLIB_ONLY check: `decimal` is stdlib — does not violate hex-boundary blocklist (verify the AST guard list does NOT include 'decimal'; if it does, this is a Rule-1 plan-bug — escalate).

2. **pnl_engine.py:** retype both signatures.
   - compute_unrealised_pnl: change all float params to be coerced via `to_aud(...)` at function entry; arithmetic stays in Decimal; return `result.quantize(AUD_QUANTIZE)`.
   - compute_realised_pnl: same pattern.
   - Update docstring D-11 line to say "Decimal AUD-quantized" instead of "float".
   - Indicator-math math (price * contracts) — `last_close - entry_price` etc. — IS price-domain not money-domain, so coerce to Decimal at the boundary: `Decimal(str(last_close)) - Decimal(str(entry_price))`. The result `gross` becomes Decimal. Multiplier is `Decimal(str(multiplier))`.

3. **state_manager.py:** bump STATE_SCHEMA_VERSION to 9 (locate the constant).
   - Add `_migrate_v8_to_v9(s: dict) -> dict` near the v7→v8 migrator (around line 262). Body: for each float money field listed in <interfaces>, `s[field] = str(Decimal(str(s[field])).quantize(AUD_QUANTIZE))` if present (idempotent — string passes through to_aud unchanged). For paper_trades, equity_history, positions: iterate and coerce per row.
   - Register in `_MIGRATIONS` dict: `9: _migrate_v8_to_v9,` keeping the existing key=N pattern (key is the *target* version).
   - **Save path:** add a custom JSON encoder. Find the `_atomic_write` body and the `json.dumps(...)` call inside; pass `default=_decimal_default` where `_decimal_default(o) = str(o) if isinstance(o, Decimal) else raise TypeError`.
   - **Load path:** after `json.load(...)` returns the dict, walk the same money-field list and coerce each via `Decimal(str(v))`. Do NOT call `float(...)` on these fields anywhere downstream.

4. **sizing_engine.py:** locate `cost_aud_open: per-contract opening cost in AUD (instrument_cost_aud / 2)` (lines 517, 575). The `cost_aud_open` argument flowing INTO sizing functions becomes `Decimal` (typed); arithmetic involving it stays in Decimal. Indicator math ABOVE this point stays float64. The existing `del atr in get_trailing_stop` D-15 invariant unchanged.
   - Hex-boundary check: sizing_engine.py is on the FORBIDDEN_MODULES_STDLIB_ONLY hex (per system_params.py line 163 / Phase 1 D-14 AST guard). `decimal` is stdlib — does not violate the existing blocklist. Confirm via `python -c 'import sizing_engine' && pytest tests/test_signal_engine.py::TestDeterminism -k forbidden -x` after edits.

5. **tests/test_decimal_money_math.py (NEW):** 6 tests per behavior block above.

6. **tests/test_pnl_engine.py:** existing assertions like `assert result == pytest.approx(-12.5, abs=1e-9)` flip to `assert result == Decimal('-12.50')`. ANY existing test calling these helpers and downstream-asserting `float` types may need updating — grep all sites.

7. Run `pytest -x` and fix any cascade. Expected cascade: test_state_manager (round-trip), test_main (run_daily_check uses pnl helpers), test_notifier (cost_aud/2 strings in email body — formatter accepts Decimal via `f'{v:.2f}'`). Document each cascade fix in SUMMARY.

  </action>
  <verify>
    <automated>pytest tests/test_decimal_money_math.py tests/test_pnl_engine.py tests/test_state_manager.py -x -v</automated>
  </verify>
  <done>
    - 6 new tests in test_decimal_money_math.py pass.
    - Existing test_pnl_engine + test_state_manager pass after Decimal flip.
    - `grep -n 'AUD_QUANTIZE' system_params.py` shows the constant defined.
    - `grep -n 'Decimal' pnl_engine.py | grep -v '^#' | wc -l` >= 4 (signature + at least 2 quantize sites + import).
    - signal_engine indicator math untouched: `pytest tests/test_signal_engine.py::TestDeterminism -x` green.
    - `python -c 'import json, decimal; from state_manager import _decimal_default; print(_decimal_default(decimal.Decimal("1.23")))'` prints `1.23`.
  </done>
</task>

<task type="auto">
  <name>Task 2: Cascade fix — verify full suite green and indicator math untouched</name>
  <read_first>
    - tests/test_signal_engine.py::TestDeterminism (the AST-blocklist guard)
    - tests/test_main.py (run_daily_check downstream of pnl_engine)
  </read_first>
  <action>
1. Run `pytest -x 2>&1 | tail -50` — capture every failing test.
2. For each failing test, classify:
   - **Floating-point comparison drift** (test asserted `float` and now sees `Decimal`): convert `pytest.approx(...)` → `Decimal('...')` exact equality. NOT a behavioural change — just a type tightening.
   - **Type leak into hex** (signal_engine sees Decimal): bug — coerce back to float at the orchestration boundary (e.g. main.py reads `state['account_aud']` as Decimal, but if it passes to a sizing-math call expecting float, wrap with `float(...)` at the call site).
   - **JSON-serialisation crash** (Decimal not JSON-serialisable): proves the `default=_decimal_default` hook is missing on a save_state path — add it.
3. Re-run `pytest -x` after every fix. Loop until green.
4. Final invariants check (run all four; each must hold):
   - `pytest tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent -x` — green (hex-boundary unbroken).
   - `python -c "from signal_engine import compute_indicators; import pandas as pd; df = pd.read_csv('tests/fixtures/spi200_canonical.csv', parse_dates=['Date']).set_index('Date'); out = compute_indicators(df); print(out.dtypes.unique())"` shows only `float64` dtypes.
   - `wc -l tests/test_decimal_money_math.py` >= 6 test functions.
   - `grep -c 'STATE_SCHEMA_VERSION = 9' state_manager.py` == 1.
  </action>
  <verify>
    <automated>pytest -x 2>&1 | tail -5 | grep -E "passed|failed"</automated>
  </verify>
  <done>Full suite green. Hex-boundary untouched. Decimal lives only at money-math boundary.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| state.json (disk) → in-memory dict | Persisted money values must round-trip without precision loss |
| pnl_engine ↔ sizing_engine indicator math | Decimal must NOT leak into numpy/pandas hex |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation |
|-----------|----------|-----------|-------------|------------|
| T-27-01-01 | Tampering | Money values silently drift via float ULP accumulation across saves | mitigate | All money fields are Decimal in-memory + str-on-disk; round-trip test asserts exact equality (not approx). |
| T-27-01-02 | Information disclosure | N/A — no external data exposure change | accept | Local file system, single-operator droplet. |
| T-27-01-03 | DoS | Decimal arithmetic ~10× slower than float | accept | Daily run does ~hundreds of money ops; <1ms total budget impact. Indicator math (millions of ops) stays float64. |
</threat_model>

<verification>
```
pytest tests/test_decimal_money_math.py tests/test_pnl_engine.py tests/test_state_manager.py tests/test_signal_engine.py -x -v
grep -n 'AUD_QUANTIZE\|to_aud' system_params.py
grep -c 'Decimal' pnl_engine.py
pytest -x   # full suite
```
</verification>

<success_criteria>
- AUD_QUANTIZE = Decimal('0.01') in system_params.py.
- pnl_engine.py compute_*_pnl signatures + bodies use Decimal end-to-end.
- state_manager schema 8→9 with money coercion migration; save/load round-trips Decimal exactly.
- Hex-boundary unchanged: signal_engine + sizing_engine indicator math stays float64; AST blocklist guard green.
- 6+ new tests in tests/test_decimal_money_math.py.
</success_criteria>

<output>
Create `.planning/phases/27-code-quality-correctness-sweep-apply-2026-05-07-code-review-/27-01-SUMMARY.md` listing: AUD_QUANTIZE constant, schema bump 8→9, files modified line counts, cascade-fix list with 1-line per cascading test, hex-boundary AST-guard green confirmation.
</output>
