---
phase: 27
plan: 01
type: execute
wave: 1B
parallel: false
depends_on:
  - 27-07-naive-datetime-and-migration-contiguity-PLAN.md  # <!-- review-fix: agreed-1 -->
files_modified:
  - pnl_engine.py
  - sizing_engine.py  # <!-- review-fix: agreed-7 — sizing_engine compute_unrealised_pnl + _close_position now in scope -->
  - state_manager.py
  - system_params.py
  - dashboard.py  # <!-- review-fix: agreed-7 — verify JSON paths use str(Decimal) not raw Decimal -->
  - dashboard_renderer/components/*.py  # <!-- review-fix: agreed-7 — same JSON-serialisation audit -->
  - tests/test_pnl_engine.py
  - tests/test_decimal_money_math.py
  - tests/test_dashboard_decimal_serialization.py  # <!-- review-fix: agreed-7 -->
autonomous: true
requirements: []
must_haves:
  truths:
    - "compute_unrealised_pnl + compute_realised_pnl in pnl_engine.py return Decimal (not float)."
    - "sizing_engine.compute_unrealised_pnl delegates to pnl_engine after Decimal conversion (duplicate eliminated)."
    - "sizing_engine._close_position close_cost arithmetic is Decimal."
    - "All money fields persisted to state.json (account_aud, equity_history rows, paper_trades realised_pnl_aud / unrealised, positions cost_aud_open) round-trip through Decimal without precision drift."
    - "Indicator math (signal_engine.compute_indicators / sizing_engine ATR/ADX/Mom/RVol math) STAYS float64 (hex-boundary preserved — no Decimal in numpy/pandas paths)."
    - "Project-wide quantize policy lives in system_params.AUD_QUANTIZE = Decimal('0.01') with ROUND_HALF_UP rounding mode (chosen over ROUND_HALF_EVEN — see rationale)."
    - "Dashboard JSON serialization paths use str(Decimal) or float(Decimal) explicitly — raw Decimal objects are NEVER passed to json.dumps without an encoder."
  artifacts:
    - path: system_params.py
      provides: "AUD_QUANTIZE Decimal constant + helper to_aud(x) -> Decimal + AUD_ROUND mode"
      contains: "AUD_QUANTIZE"
    - path: pnl_engine.py
      provides: "compute_unrealised_pnl / compute_realised_pnl returning Decimal"
      contains: "Decimal"
    - path: sizing_engine.py
      provides: "compute_unrealised_pnl delegates to pnl_engine; _close_position uses Decimal"
      contains: "from pnl_engine import compute_unrealised_pnl"
    - path: tests/test_decimal_money_math.py
      provides: "round-trip + precision regression tests"
      contains: "Decimal"
    - path: tests/test_dashboard_decimal_serialization.py
      provides: "regression that dashboard JSON paths handle Decimal correctly"
      contains: "json.dumps"
  key_links:
    - from: "pnl_engine.compute_unrealised_pnl"
      to: "system_params.AUD_QUANTIZE"
      via: "quantize call at return"
      pattern: "\\.quantize\\(AUD_QUANTIZE"
    - from: "sizing_engine.compute_unrealised_pnl"
      to: "pnl_engine.compute_unrealised_pnl"
      via: "import + delegate"
      pattern: "from pnl_engine import"
    - from: "state_manager._migrate_v8_to_v9 (or in-place coercion at load)"
      to: "Decimal(...) on persisted money strings"
      via: "Decimal(str(v))"
      pattern: "Decimal\\(str\\("
---

## Review fixes applied

- [x] agreed-1 (wave/dependency rebuild) — wave changed `1` → `1B`; depends_on=[27-07] retained; documented as Wave 1B (after 1A) per Codex sequencing matrix.
- [x] agreed-7 (Decimal scope incomplete) — added `sizing_engine.py` (`compute_unrealised_pnl`, `_close_position`) to file inventory and added Task 3 to delegate sizing_engine's compute_unrealised_pnl to pnl_engine after Decimal conversion (most-eloquent fix per OpenCode).
- [x] agreed-7 (rounding mode) — pinned `AUD_ROUND = ROUND_HALF_UP` (chosen over banker's rounding ROUND_HALF_EVEN) for trading PnL display consistency; documented in plan rationale below.
- [x] agreed-7 (dashboard JSON serialization) — added explicit task to audit dashboard JSON paths for raw Decimal usage; new test file `tests/test_dashboard_decimal_serialization.py`.
- [x] agreed-7 (PnL-first split decision) — kept as a single plan (NOT split into 27-01a/27-01b). Rationale: file inventory is small (5 prod files), risk is contained by the round-trip test + hex-boundary AST guard. Splitting adds wave-coordination overhead without reducing blast radius.
- [x] M1 (brittle implementation tests) — kept Decimal-exact assertions (these ARE behavior-level: "result equals Decimal('-12.50') exactly" is a behavior contract, not a literal-string check).
- [x] M2 (doc rule) — SUMMARY artifact stays inside `.planning/phases/27-.../` (planning folder, allowed).

<objective>
Convert money-denominated arithmetic in pnl_engine.py + sizing_engine.py (BOTH `compute_unrealised_pnl` AND `_close_position`) + state_manager.py persisted money fields to Python decimal.Decimal end-to-end. Indicator math stays float64. Dashboard JSON paths must explicitly handle Decimal (no raw Decimal into json.dumps).

Purpose: financial-data integrity (review item #1). Float arithmetic on AUD with cumulative sums + cost subtractions accumulates ULP-level drift; Decimal with explicit quantize gives bit-exact AUD-cent semantics.

**Rounding choice (per Codex MEDIUM, agreed-concern #7):** AUD_ROUND = `decimal.ROUND_HALF_UP`. Rationale: HALF_UP matches consumer-finance/trading PnL display intuition ("$2.005 rounds to $2.01"). ROUND_HALF_EVEN (banker's rounding, Python default) is for accumulating large datasets where statistical bias matters; trading PnL display is ~hundreds of money ops/day, so display intuition wins.

Output: Decimal-typed money math, AUD_QUANTIZE constant, sizing_engine delegate, dashboard JSON audit, round-trip regression test.
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
@dashboard.py
@dashboard_renderer/components/

<interfaces>
# pnl_engine.py current signatures (float-typed):
#   compute_unrealised_pnl(side, last_close, entry_price, contracts, multiplier, entry_cost_aud) -> float
#   compute_realised_pnl(side, exit_price, entry_price, contracts, multiplier, round_trip_cost_aud) -> float

# sizing_engine.py — touches money in TWO places (review-fix agreed-7):
#   line 493: def compute_unrealised_pnl(cost_aud_open: float, ...) -> float
#             does cost_aud_open * n_contracts at line 525
#   line 789: def _close_position(...) does close_cost = cost_aud_open * position['n_contracts']
# Indicator math (ATR/ADX/Mom/RVol) stays float64.
# Decimal boundary: ONLY money slice — sizing_engine.compute_unrealised_pnl now delegates to
# pnl_engine.compute_unrealised_pnl (after coercing args via to_aud); _close_position uses Decimal arithmetic.

# state_manager.py current schema (v8):
#   state['account_aud'] : float
#   state['paper_trades'][i]['realised_pnl_aud'] : float | None
#   state['equity_history'] : list[{'date': str, 'equity_aud': float}]
#   state['positions'][k]['cost_aud_open'] : float
# Bump schema 8 -> 9; _migrate_v8_to_v9 coerces all four fields via Decimal(str(v)).quantize(AUD_QUANTIZE).

# JSON serialisation strategy: Decimal -> str via custom encoder
#   default=lambda o: str(o) if isinstance(o, Decimal) else raise TypeError
# Read path: Decimal(str(loaded_value)) — never float(loaded_value).

# Dashboard JSON audit (agreed-7): every dashboard.py + dashboard_renderer/components/*.py site
# that calls json.dumps OR builds an AJAX/JSON response containing money values must EITHER:
#   (a) pass default=_decimal_default, OR
#   (b) explicitly coerce via str(decimal) or float(decimal) before passing.
# Raw Decimal objects in json.dumps without an encoder will raise TypeError at runtime.

# AUD_QUANTIZE config:
#   from decimal import Decimal, ROUND_HALF_UP
#   AUD_QUANTIZE: Decimal = Decimal('0.01')
#   AUD_ROUND = ROUND_HALF_UP                         # <!-- review-fix: agreed-7 explicit choice -->
#   def to_aud(x) -> Decimal:
#     return Decimal(str(x)).quantize(AUD_QUANTIZE, rounding=AUD_ROUND)

# Hex-boundary: signal_engine.py untouched; sizing_engine indicator math untouched.
# decimal is stdlib — does NOT violate FORBIDDEN_MODULES_STDLIB_ONLY blocklist.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add AUD_QUANTIZE + AUD_ROUND + Decimal-typed pnl_engine + state_manager round-trip</name>
  <read_first>
    - system_params.py (full file — locate constants block)
    - pnl_engine.py (all 55 lines)
    - state_manager.py lines 60-310 (schema version + _MIGRATIONS dict + load_state)
    - state_manager.py lines 580-710 (save_state + serialisation)
    - tests/test_pnl_engine.py
  </read_first>
  <behavior>
    - test_compute_unrealised_pnl_returns_decimal: result is Decimal instance, equals Decimal('-12.50') exactly.
    - test_compute_realised_pnl_returns_decimal: same.
    - test_aud_quantize_constant_is_two_dp: system_params.AUD_QUANTIZE == Decimal('0.01').
    - test_aud_round_is_half_up: system_params.AUD_ROUND == ROUND_HALF_UP — pin the choice.  <!-- review-fix: agreed-7 -->
    - test_to_aud_rounds_half_up: to_aud('2.005') == Decimal('2.01') (HALF_UP) — distinguishes from HALF_EVEN which would yield 2.00.
    - test_state_round_trip_preserves_aud_cents: save_state with account_aud=Decimal('1234.56'), load_state, assert loaded value == Decimal('1234.56').
    - test_indicator_math_unchanged: signal_engine.compute_indicators on canonical fixture — all-float64 dtype.
    - test_v8_to_v9_migration_coerces_money: float money fields promoted to Decimal-quantized.
  </behavior>
  <action>
1. **system_params.py:** add at end of constants block:
   ```python
   from decimal import Decimal, ROUND_HALF_UP
   AUD_QUANTIZE: Decimal = Decimal('0.01')  # Phase 27 #1: AUD cents precision boundary
   AUD_ROUND = ROUND_HALF_UP                 # Phase 27 #1 (review-fix agreed-7): chosen over HALF_EVEN
   def to_aud(x) -> Decimal:
     '''Coerce x to Decimal quantized to AUD_QUANTIZE using HALF_UP rounding.'''
     return Decimal(str(x)).quantize(AUD_QUANTIZE, rounding=AUD_ROUND)
   ```

2. **pnl_engine.py:** retype both signatures.
   - compute_unrealised_pnl: coerce all float params via `to_aud(...)` at function entry; arithmetic stays in Decimal; return `result.quantize(AUD_QUANTIZE, rounding=AUD_ROUND)`.
   - compute_realised_pnl: same pattern.
   - Update docstring D-11 line to "Decimal AUD-quantized (HALF_UP)".
   - Price-domain coercion: `Decimal(str(last_close)) - Decimal(str(entry_price))`.

3. **state_manager.py:** bump STATE_SCHEMA_VERSION to 9.
   - Add `_migrate_v8_to_v9(s: dict) -> dict` near the v7→v8 migrator. Body: for each money field, `s[field] = str(Decimal(str(s[field])).quantize(AUD_QUANTIZE, rounding=AUD_ROUND))` if present (idempotent). For paper_trades, equity_history, positions: iterate per row.
   - Register in `_MIGRATIONS` dict: `9: _migrate_v8_to_v9`.
   - **Save path:** add `_decimal_default(o) = str(o) if isinstance(o, Decimal) else raise TypeError`; pass `default=_decimal_default` to json.dumps in _atomic_write.
   - **Load path:** after json.load, walk money-field list and coerce each via `Decimal(str(v))`. Never `float(...)`.

4. **tests/test_decimal_money_math.py (NEW):** 8 tests per behavior block.

5. **tests/test_pnl_engine.py:** flip `pytest.approx(-12.5, abs=1e-9)` to `Decimal('-12.50')` exact. Grep all sites.

6. Run `pytest -x` and fix any cascade.
  </action>
  <verify>
    <automated>pytest tests/test_decimal_money_math.py tests/test_pnl_engine.py tests/test_state_manager.py -x -v</automated>
  </verify>
  <done>
    - 8 new tests in test_decimal_money_math.py pass (HALF_UP rounding pinned).
    - Existing test_pnl_engine + test_state_manager pass.
    - `grep -n 'AUD_QUANTIZE\|AUD_ROUND' system_params.py` shows both constants.
    - `grep -c 'Decimal' pnl_engine.py | grep -v '^#'` >= 4.
    - signal_engine indicator math untouched.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: sizing_engine — delegate compute_unrealised_pnl + Decimalize _close_position</name>
  <!-- review-fix: agreed-7 — sizing_engine duplicate compute_unrealised_pnl + _close_position were missed in original plan -->
  <read_first>
    - sizing_engine.py lines 480-540 (compute_unrealised_pnl)
    - sizing_engine.py lines 770-820 (_close_position)
    - pnl_engine.py (post-Task-1, with Decimal signatures)
  </read_first>
  <behavior>
    - test_sizing_compute_unrealised_pnl_delegates: sizing_engine.compute_unrealised_pnl(...) returns the SAME Decimal value as pnl_engine.compute_unrealised_pnl(...) for identical inputs — proves delegation.
    - test_sizing_close_position_returns_decimal_close_cost: _close_position called with Decimal cost_aud_open returns position dict where close_cost-derived fields are Decimal.
    - test_no_duplicate_pnl_logic_in_sizing: AST/grep — `cost_aud_open * n_contracts` does NOT appear inside sizing_engine.compute_unrealised_pnl body (must be a delegation call instead).
  </behavior>
  <action>
1. **sizing_engine.py compute_unrealised_pnl (line 493):** rewrite body to delegate:
   ```python
   def compute_unrealised_pnl(cost_aud_open, last_close, entry_price, n_contracts, multiplier, side):
     '''Phase 27 #1 (review-fix agreed-7): delegate to pnl_engine to eliminate duplicate logic.'''
     from pnl_engine import compute_unrealised_pnl as _pnl_unrealised
     # Adapt arg names if pnl_engine signature differs — coerce via to_aud at boundary.
     return _pnl_unrealised(side, last_close, entry_price, n_contracts, multiplier,
                            entry_cost_aud=cost_aud_open)
   ```
   If signatures don't align cleanly, define a thin adapter — but the body MUST end up calling pnl_engine, not duplicating the math.

2. **sizing_engine.py _close_position (line 789):** replace
   ```python
   close_cost = cost_aud_open * position['n_contracts']
   ```
   with
   ```python
   from system_params import to_aud
   close_cost = to_aud(cost_aud_open) * to_aud(position['n_contracts'])
   ```
   Any subsequent arithmetic on `close_cost` keeps Decimal semantics. Final write to position dict serializes via str(Decimal) per state_manager save path.

3. **tests/test_decimal_money_math.py (extend):** 3 sizing_engine tests per behavior block.

4. **Hex-boundary check:** sizing_engine still on FORBIDDEN_MODULES_STDLIB_ONLY hex; decimal is stdlib — safe. Confirm via existing AST guard test.

5. Run `pytest tests/test_sizing_engine.py tests/test_decimal_money_math.py -x -v`.
  </action>
  <verify>
    <automated>pytest tests/test_sizing_engine.py tests/test_decimal_money_math.py -x -v</automated>
  </verify>
  <done>
    - sizing_engine.compute_unrealised_pnl delegates (no duplicate cost_aud_open*n_contracts logic).
    - sizing_engine._close_position uses Decimal arithmetic.
    - 3 sizing tests green.
    - Hex-boundary AST guard still green.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Dashboard JSON Decimal-serialization audit</name>
  <!-- review-fix: agreed-7 — Codex MEDIUM concern: persisted-Decimal-as-string + Decimal-on-load may break dashboard JSON serialization -->
  <read_first>
    - dashboard.py — grep for `json.dumps`
    - dashboard_renderer/components/*.py — grep for `json.dumps`
    - web/routes/dashboard.py — grep for `JSONResponse` and dict-returning routes
  </read_first>
  <behavior>
    - test_dashboard_json_dumps_handles_decimal: any code path that builds an HTTP JSON response containing state['account_aud'] (now Decimal) does NOT raise `TypeError: Object of type Decimal is not JSON serializable`.
    - test_dashboard_money_in_json_is_string_or_float: when dashboard returns money in JSON, the wire format is `"1234.56"` (string) OR `1234.56` (float) — NEVER `Decimal('1234.56')` raw.
    - test_no_raw_decimal_in_json_dumps: AST/grep — every `json.dumps(...)` site that touches state-money values either uses `default=_decimal_default` OR pre-coerces money values via `str(...)` / `float(...)`.
  </behavior>
  <action>
1. Grep audit:
   ```bash
   grep -rn 'json\.dumps\|JSONResponse' dashboard.py dashboard_renderer/ web/routes/dashboard.py
   ```
   For each match:
   - If the dict being dumped touches money fields (account_aud, equity, paper_trades, positions cost) → ensure `default=_decimal_default` OR explicit pre-coercion.
   - Document the chosen approach (encoder vs pre-coerce) in 27-01-SUMMARY.md.

2. **Most eloquent option:** define `_decimal_default` ONCE in system_params.py and import everywhere it's needed. Locality: rounding/coercion policy for money already lives in system_params; the JSON serializer for money belongs there too.
   ```python
   # system_params.py
   def _decimal_default(o):
     if isinstance(o, Decimal): return str(o)
     raise TypeError(f'Object of type {type(o).__name__} is not JSON serializable')
   ```

3. **tests/test_dashboard_decimal_serialization.py (NEW):** 3 tests per behavior block. Construct a state with `account_aud = Decimal('1234.56')`, exercise every dashboard JSON path, assert no TypeError.

4. Run `pytest tests/test_dashboard_decimal_serialization.py -x -v`.
  </action>
  <verify>
    <automated>pytest tests/test_dashboard_decimal_serialization.py -x -v</automated>
  </verify>
  <done>
    - Every dashboard json.dumps site handles Decimal.
    - 3 new tests green.
    - No raw Decimal reaches json.dumps without an encoder.
  </done>
</task>

<task type="auto">
  <name>Task 4: Cascade fix — verify full suite green and indicator math untouched</name>
  <read_first>
    - tests/test_signal_engine.py::TestDeterminism (the AST-blocklist guard)
    - tests/test_main.py
  </read_first>
  <action>
1. Run `pytest -x 2>&1 | tail -50`.
2. Classify each failing test:
   - **Float-comparison drift**: convert pytest.approx → Decimal exact equality.
   - **Type leak into hex**: bug — coerce back to float at orchestration boundary with `float(...)`.
   - **JSON-serialisation crash**: missing `default=_decimal_default` — add it.
3. Re-run until green.
4. Final invariants:
   - `pytest tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent -x` — green.
   - `python -c "from signal_engine import compute_indicators; ..."` shows only float64 dtypes.
   - `wc -l tests/test_decimal_money_math.py` >= 8 test functions.
   - `grep -c 'STATE_SCHEMA_VERSION = 9' state_manager.py` == 1.
  </action>
  <verify>
    <automated>pytest -x 2>&1 | tail -5 | grep -E "passed|failed"</automated>
  </verify>
  <done>Full suite green. Hex-boundary untouched. Decimal lives only at money-math boundary. Dashboard JSON paths handle Decimal.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| state.json (disk) → in-memory dict | Persisted money values must round-trip without precision loss |
| pnl_engine ↔ sizing_engine indicator math | Decimal must NOT leak into numpy/pandas hex |
| state.json money → dashboard JSON wire | Decimal must serialize via str/float, never raw |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation |
|-----------|----------|-----------|-------------|------------|
| T-27-01-01 | Tampering | Money values silently drift via float ULP accumulation across saves | mitigate | All money fields are Decimal in-memory + str-on-disk; round-trip test asserts exact equality. |
| T-27-01-02 | DoS | Decimal arithmetic ~10× slower than float | accept | Daily run does ~hundreds of money ops; <1ms total impact. Indicator math (millions of ops) stays float64. |
| T-27-01-03 | DoS | Dashboard JSON serialization crashes on raw Decimal → 500 error → operator can't view dashboard | mitigate | Task 3 audits every json.dumps; encoder or pre-coercion in place; regression test asserts no TypeError. |
</threat_model>

<verification>
```
pytest tests/test_decimal_money_math.py tests/test_pnl_engine.py tests/test_state_manager.py tests/test_sizing_engine.py tests/test_dashboard_decimal_serialization.py tests/test_signal_engine.py -x -v
grep -n 'AUD_QUANTIZE\|AUD_ROUND\|to_aud' system_params.py
grep -c 'Decimal' pnl_engine.py sizing_engine.py
pytest -x   # full suite
```
</verification>

<success_criteria>
- AUD_QUANTIZE = Decimal('0.01'), AUD_ROUND = ROUND_HALF_UP in system_params.py.
- pnl_engine compute_*_pnl signatures + bodies use Decimal end-to-end.
- sizing_engine.compute_unrealised_pnl delegates to pnl_engine (no duplicate logic).
- sizing_engine._close_position uses Decimal arithmetic.
- state_manager schema 8→9 with money coercion migration.
- Dashboard JSON paths handle Decimal (encoder OR pre-coercion).
- Hex-boundary unchanged.
- 14+ new tests across test_decimal_money_math.py + test_dashboard_decimal_serialization.py.
</success_criteria>

<output>
Create `.planning/phases/27-code-quality-correctness-sweep-apply-2026-05-07-code-review-/27-01-SUMMARY.md` listing: AUD_QUANTIZE+AUD_ROUND constants, schema bump 8→9, sizing_engine delegation pattern, dashboard JSON audit results (encoder vs pre-coerce per site), files modified line counts, cascade-fix list, hex-boundary AST-guard green confirmation.
</output>
