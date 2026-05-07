---
phase: 27
plan: 01
subsystem: pnl_engine + sizing_engine + state_manager money-math + dashboard JSON
tags:
  - phase-27
  - decimal-money-math
  - aud-cents
  - schema-migration
  - hex-boundary-preserved
  - delegation-deduplication
  - json-encoder
dependency_graph:
  requires:
    - 27-07-naive-datetime-and-migration-contiguity-PLAN.md  # contiguity check validates v9 registration
  provides:
    - "system_params.AUD_QUANTIZE / AUD_ROUND / to_aud / _decimal_default"
    - "pnl_engine.compute_*_pnl returning Decimal AUD-quantized HALF_UP"
    - "sizing_engine.compute_unrealised_pnl delegating to pnl_engine (no duplicate)"
    - "state_manager schema 8→9 with quantize-on-save migrator"
  affects:
    - "Future plans persisting AUD money fields can rely on v9 quantize policy"
    - "Future dashboard work should use system_params._decimal_default for json.dumps"
tech_stack:
  added:
    - "stdlib `decimal` (Decimal, ROUND_HALF_UP) at the money-math boundary"
  patterns:
    - "Delegation-over-duplication: sizing_engine.compute_unrealised_pnl delegates to pnl_engine"
    - "Boundary float() coercion: pnl_engine returns Decimal; consumers float() at display sites"
    - "Quantize-on-save: state_manager.save_state runs v8→v9 migrator on every persist"
    - "Single-source JSON encoder: system_params._decimal_default reused by save_state + dashboard"
    - "Dual-tier Decimal: in-memory state stays float; on-disk JSON is canonical AUD-cent string"
key_files:
  created:
    - tests/test_decimal_money_math.py
    - tests/test_dashboard_decimal_serialization.py
  modified:
    - system_params.py
    - pnl_engine.py
    - sizing_engine.py
    - state_manager.py
    - dashboard.py
    - dashboard_renderer/stats.py
    - web/routes/paper_trades.py
    - tests/test_pnl_engine.py
    - tests/test_state_manager.py
    - tests/test_system_params.py
decisions:
  - "AUD_ROUND = ROUND_HALF_UP (NOT banker's rounding ROUND_HALF_EVEN). Trading PnL display intuition wins ($2.005 → $2.01). Banker's rounding is for accumulating large datasets where statistical bias matters; trading PnL display is hundreds of money ops/day."
  - "pnl_engine returns Decimal (AUTHORITY); all other money-touching modules use float internally and float() the result at the consumption boundary. Avoids the Decimal-vs-float type-mismatch blast radius across 40+ call sites while preserving cent-precision at the persistence boundary."
  - "State.json wire format stays JSON-numeric (not string). v8→v9 migrator quantizes via Decimal then float()s back. Subsequent saves of the same float yield bit-exact output (AUD-cent canonical form) — no ULP drift across cycles. Decimal serialization is the encoder fallback for any stray Decimal values, not the primary wire form."
  - "Hex boundary preserved: signal_engine + sizing_engine indicator math (ATR/ADX/Mom/RVol) stays float64. Decimal lives ONLY at money-math boundary (pnl_engine return + state.json quantize-on-save). Indicator math operates on numpy/pandas with millions of ops/year — Decimal would impose ~10× perf cost without precision benefit."
  - "_decimal_default lives in system_params (single source of truth) — same module that owns AUD_QUANTIZE and to_aud. Locality of behaviour: rounding/coercion policy and the JSON serializer for money belong together."
  - "sizing_engine.compute_unrealised_pnl delegates via inline import (`from pnl_engine import compute_unrealised_pnl`). Inline avoids module-top circular-import risk and keeps the delegation contract grep-discoverable inside the function body."
metrics:
  duration: ~75min
  tasks: 4
  files_modified: 7
  files_created: 2
  tests_added: 21 (18 in test_decimal_money_math.py + 3 in test_dashboard_decimal_serialization.py)
  tests_passing: 1863/1863 (full suite, +21 net new)
  completed: 2026-05-08
---

# Phase 27 Plan 01: Decimal Money Math — Summary

Money-denominated arithmetic in `pnl_engine.py`, `sizing_engine.py`, and `state_manager.py` persisted fields now flows through Python's stdlib `Decimal` with `AUD_QUANTIZE = Decimal('0.01')` and `AUD_ROUND = ROUND_HALF_UP`. State schema bumped 8 → 9; the new `_migrate_v8_to_v9` migrator runs at every `save_state` to canonicalise on-disk AUD-cent precision so repeated save/load cycles cannot accumulate float ULP drift. Indicator math (ATR/ADX/Mom/RVol on numpy/pandas) stays bit-for-bit float64 — the hex boundary is preserved.

## What shipped

### `system_params.py` — money-math precision boundary

| Symbol | Type | Purpose |
|---|---|---|
| `AUD_QUANTIZE` | `Decimal('0.01')` | AUD-cent precision pin |
| `AUD_ROUND` | `ROUND_HALF_UP` | display-intuition rounding (NOT banker's) |
| `to_aud(x)` | `Decimal` | canonical coerce: `Decimal(str(x)).quantize(...)` |
| `_decimal_default(o)` | encoder hook | `json.dumps(default=...)` for stray Decimal |

`to_aud` routes through `Decimal(str(x))` first to strip float-binary repr noise (`0.1 + 0.2 == 0.30000000000000004`) before quantize. `_decimal_default` raises `TypeError` on non-Decimal unknown types so genuine serialization bugs still surface.

### `pnl_engine.py` — Decimal end-to-end

Both public functions now return `Decimal` AUD-quantized HALF_UP:

```python
def compute_unrealised_pnl(side, entry_price, last_close, contracts, multiplier, entry_cost_aud) -> Decimal
def compute_realised_pnl(side, entry_price, exit_price, contracts, multiplier, round_trip_cost_aud) -> Decimal
```

Inputs are coerced via `Decimal(str(x))` at the function boundary. NaN propagation: `Decimal('NaN').is_nan()` is the canonical detect; arithmetic flows like float NaN. Local `_AUD_QUANTIZE` / `_AUD_ROUND` constants mirror system_params (the AST hex-boundary test forbids `system_params` import in pnl_engine — locks pinned by `tests/test_decimal_money_math.py::TestAudQuantizeConstants`).

AST allow-list extended: pnl_engine may now import `decimal` in addition to `math` and `typing`.

### `sizing_engine.py` — delegation + Decimal close_cost

`compute_unrealised_pnl` rewritten to delegate to pnl_engine (eliminates the duplicate-money-math bug class flagged by review-fix agreed-7):

```python
def compute_unrealised_pnl(position, current_price, multiplier, cost_aud_open) -> float:
  from pnl_engine import compute_unrealised_pnl as _pnl_engine_unrealised
  n = position['n_contracts']
  total_entry_cost_aud = cost_aud_open * n           # per-contract → total adapter
  result_decimal = _pnl_engine_unrealised(
    position['direction'], position['entry_price'], current_price,
    n, multiplier, total_entry_cost_aud,
  )
  return float(result_decimal)                        # float at boundary
```

`_close_position` close_cost now arithmetic-Decimal:

```python
from system_params import to_aud
close_cost_decimal = to_aud(cost_aud_open) * to_aud(position['n_contracts'])
realised_pnl = gross - float(close_cost_decimal)
```

Both wrappers `float()` at the return boundary so `ClosedTrade.realised_pnl` stays `float` (downstream consumers — `record_trade`, dashboard formatters, equity sums — already expect float).

### `state_manager.py` — v9 schema + quantize-on-save

```
STATE_SCHEMA_VERSION: 8 → 9
MIGRATIONS keys      : {1,2,3,4,5,6,7,8} → {1,2,3,4,5,6,7,8,9}
```

`_migrate_v8_to_v9(s)` quantizes every AUD-money field via `Decimal(str(v)).quantize(AUD_QUANTIZE, ROUND_HALF_UP)` then float()-coerces back so wire format stays JSON-numeric:

| Container | Fields touched |
|---|---|
| top-level | `account`, `initial_account` |
| `equity_history[i]` | `equity` |
| `paper_trades[i]` | `realised_pnl`, `unrealised_pnl`, `entry_cost_aud`, `entry_price`, `exit_price` |
| `trade_log[i]` | `gross_pnl`, `net_pnl`, `cost_aud` |

Idempotent (quantizing an already-quantized value is a no-op). Defensive (only touches dict-shaped rows; missing fields skipped). Silent (no warnings, no log line).

`save_state` and `_save_state_unlocked` both:
1. Filter underscore-prefixed runtime-only keys (existing D-14 contract)
2. Run `_migrate_v8_to_v9` to canonicalise money fields
3. Pass `default=_decimal_default` to `json.dumps` (defense-in-depth for any stray Decimal that survives the migrator)

### `dashboard.py` + `dashboard_renderer/stats.py`

Single existing `json.dumps` site (`_render_equity_chart_container`, line 1891) already pre-coerces equity values via `float(row['equity'])` — kept that, added `default=_decimal_default` as belt-and-suspenders.

`get_open_paper_trades_section` and `compute_aggregate_stats`: `float()` coerce on `compute_unrealised_pnl` / `compute_realised_pnl` Decimal returns at the display boundary so f-string formatting and `>` / `<` comparisons work uniformly.

### `web/routes/paper_trades.py`

`close_paper_trade` route: `row['realised_pnl'] = float(realised)` at the persistence boundary so in-memory paper_trades rows stay float-typed (downstream readers — dashboard rendering, save_state v9 migrator, accumulators — all consume float). AUD-cent precision is preserved by the v9 quantize-on-save migrator.

### Tests

| File | Tests | Focus |
|---|---|---|
| `tests/test_decimal_money_math.py` | 18 | AUD_QUANTIZE/AUD_ROUND constants, pnl_engine Decimal return, state round-trip preservation, v9 migration registration + idempotence, sizing_engine delegation + Decimal close_cost, indicator math float64 invariant, _decimal_default encoder |
| `tests/test_dashboard_decimal_serialization.py` | 3 | json.dumps handles Decimal, wire format is str/float (never raw Decimal repr), AST/source scan for naked json.dumps without default= or pre-coercion |

Updated tests:
- `tests/test_pnl_engine.py`: assertions now `abs(float(result) - expected) < 1e-9`; `decimal` added to AST allow-list.
- `tests/test_state_manager.py`: 4 chain-end assertions cascaded v8 → v9.
- `tests/test_system_params.py::test_state_schema_version_is_8`: assertion updated to `== 9` with explanatory comment.

## TDD Gate Compliance

Tasks 1, 2, 3 followed RED → GREEN cycle (test commit before feat commit). Task 4 was a pure cascade-fix task (assertion updates + boundary float()s for previously-passing tests broken by the schema bump and Decimal returns) — committed as `fix(...)` because every change reacts to a now-failing assertion in the existing suite.

| Hash | Type | Description |
|---|---|---|
| `3a08958` | test | RED — Decimal money math + dashboard JSON serialization (21 failing tests) |
| `8f030cd` | feat | GREEN Task 1 — AUD_QUANTIZE + Decimal pnl_engine + v9 schema |
| `961ac3b` | feat | GREEN Task 2 — sizing_engine delegates + Decimal close_cost |
| `ab2e65e` | feat | GREEN Task 3 — Dashboard JSON Decimal-serialization audit |
| `1d1c8e0` | fix  | GREEN Task 4 — cascade-fix Decimal float boundaries |

Plan-level gate: PASSED. RED commit precedes GREEN commits; sequence is verifiable in git log.

## Verification

```
$ .venv/bin/python -m pytest tests/test_decimal_money_math.py tests/test_pnl_engine.py \
    tests/test_state_manager.py tests/test_sizing_engine.py \
    tests/test_dashboard_decimal_serialization.py tests/test_signal_engine.py -x -v
  → 369 passed in 1.93s

$ grep -n 'AUD_QUANTIZE\|AUD_ROUND\|to_aud' system_params.py
  system_params.py:18:from decimal import ROUND_HALF_UP, Decimal
  system_params.py:97:AUD_QUANTIZE: Decimal = Decimal('0.01')
  system_params.py:98:AUD_ROUND = ROUND_HALF_UP
  system_params.py:101:def to_aud(x) -> Decimal:

$ grep -c 'Decimal' pnl_engine.py
  10

$ .venv/bin/python -m pytest --tb=line
  → 1863 passed in 110.85s (full suite, +21 net new from 1842)
```

## Deviations from Plan

### Auto-fixed issues (Rule 1 — cascade fixes from schema bump)

**1. [Rule 1 — Test cascade] STATE_SCHEMA_VERSION hardcoded literals.**
- **Found during:** Task 1 GREEN suite run.
- **Issue:** Four test assertions in `tests/test_state_manager.py` and one in `tests/test_system_params.py` hardcoded `== 8` (or `'must end at 8'` / `'walk v6→v8'`) — pre-existed before this plan, broke when STATE_SCHEMA_VERSION bumped to 9.
- **Fix:** Updated assertions to `== 9` with comments referencing Phase 27 #1 schema bump rationale. Test names retained for git-history continuity.
- **Files modified:** `tests/test_state_manager.py`, `tests/test_system_params.py`.
- **Commits:** folded into `8f030cd` (Task 1 GREEN) and `1d1c8e0` (Task 4) so the v9 schema bump diff stayed coherent.

**2. [Rule 1 — Decimal-vs-float type mismatch] Display-side accumulators.**
- **Found during:** Task 4 full-suite run.
- **Issue:** `dashboard_renderer/stats.py::compute_aggregate_stats` had `realised += pnl` where `pnl = row.get('realised_pnl') or 0.0` — `row['realised_pnl']` could now be Decimal (set via `compute_realised_pnl` route before save_state quantizes it). Same surface in dashboard.py open-trades render path.
- **Fix:** `float()` coerce at the consumption boundary. The Decimal authority lives in pnl_engine; downstream display sites consume as float.
- **Files modified:** `dashboard_renderer/stats.py`, `dashboard.py`.
- **Commits:** `ab2e65e` (Task 3) + `1d1c8e0` (Task 4).

**3. [Rule 1 — Persistence boundary type leak] paper_trade close.**
- **Found during:** Task 4 full-suite run.
- **Issue:** `web/routes/paper_trades.py::close_paper_trade` persisted `compute_realised_pnl(...)` directly into `row['realised_pnl']` — Decimal value flowed into in-memory state which downstream readers expect float-typed.
- **Fix:** `row['realised_pnl'] = float(realised)` at the persistence boundary. AUD-cent precision is preserved by the v9 quantize-on-save migrator.
- **Files modified:** `web/routes/paper_trades.py`.
- **Commit:** `1d1c8e0` (Task 4).

### Plan-spec adjustments

**1. Plan called for "Decimal end-to-end" but in-memory state stays float.** The plan's truth #1 explicitly requires `pnl_engine` returns Decimal; truth #4 requires "round-trip through Decimal without precision drift". Both satisfied. The wider scope (every state['account'] += pnl is Decimal) was deemed too high blast-radius for a single plan — 40+ call sites in main.py / notifier.py / dashboard.py / web/routes/. Eloquent compromise: pnl_engine is the Decimal authority; state_manager.save_state quantizes via Decimal at the persistence boundary; consumers float() at the display boundary. This satisfies truths #1, #4, #5, #6, #7 and preserves the hex boundary (truth #5 explicit) without requiring a multi-plan refactor of the orchestrator + UI layer.

**2. Local Decimal mirrors in pnl_engine.** Plan suggests `pnl_engine` import system_params for AUD_QUANTIZE. The existing AST hex-boundary test (`test_pnl_engine_module_imports_only_math_and_typing`) explicitly forbids that import — pnl_engine is on the stdlib-only hex tier. Solution: local `_AUD_QUANTIZE` / `_AUD_ROUND` constants in pnl_engine that mirror system_params; the project-wide regression `test_aud_quantize_constant_is_two_dp` pins them to the same values. AST allow-list extended to permit `decimal` (stdlib).

**3. State.json wire format stays JSON-numeric (not JSON-string).** Plan suggests "Decimal → str via custom encoder". We do that as the fallback (`default=_decimal_default`) but the primary path is `_migrate_v8_to_v9` quantizing values via Decimal then float()-coercing back. Result: disk format is canonical AUD-cent JSON numbers (e.g., `1234.56`), not strings (e.g., `"1234.56"`). Backward-compatible with existing readers (every dashboard route, web JSON response, manual operator inspection of state.json). Encoder is defense-in-depth for any stray Decimal that survived the migrator.

### Authentication gates

None — no auth surface touched.

## Threat surface scan

Plan threat register:

| Threat ID | Disposition | Status |
|---|---|---|
| T-27-01-01 (money values silently drift via float ULP accumulation) | mitigate | **MITIGATED** via Decimal-typed pnl_engine returns + `_migrate_v8_to_v9` quantize-on-save. `tests/test_decimal_money_math.py::test_state_no_drift_on_repeated_save_load_cycle` exercises 5 round-trips and asserts cent-exact preservation. |
| T-27-01-02 (Decimal arithmetic ~10× slower than float) | accept | **ACCEPTED** — Decimal slice is bounded to pnl_engine + state_manager save path. Indicator math (millions of ops/year on numpy/pandas) untouched. Daily run does ~hundreds of money ops; <1ms total impact. |
| T-27-01-03 (dashboard JSON serialization crashes on raw Decimal) | mitigate | **MITIGATED** — `_decimal_default` encoder added to existing dashboard json.dumps site as belt-and-suspenders; pre-coercion at line 1890 already handles the canonical case. Regression `tests/test_dashboard_decimal_serialization.py::test_dashboard_json_dumps_handles_decimal` asserts no TypeError. |

No new network endpoints, auth paths, file-access patterns, or trust-boundary schema changes. No new threat flags.

## Self-Check: PASSED

- [x] `system_params.py` contains `AUD_QUANTIZE`, `AUD_ROUND`, `to_aud`, `_decimal_default`
- [x] `pnl_engine.py` returns Decimal from both compute_*_pnl functions
- [x] `sizing_engine.compute_unrealised_pnl` body delegates via `from pnl_engine import` (no duplicate `cost_aud_open * position['n_contracts']` arithmetic)
- [x] `sizing_engine._close_position` uses `to_aud(...) * to_aud(...)` for close_cost
- [x] `state_manager.STATE_SCHEMA_VERSION == 9`; `MIGRATIONS[9] == _migrate_v8_to_v9` registered
- [x] `tests/test_decimal_money_math.py` exists (18 tests, all green)
- [x] `tests/test_dashboard_decimal_serialization.py` exists (3 tests, all green)
- [x] All 5 commits (`3a08958`, `8f030cd`, `961ac3b`, `ab2e65e`, `1d1c8e0`) reachable from HEAD
- [x] Full suite green: 1863/1863 (+21 net new tests from 1842 baseline)
- [x] Hex-boundary AST guards still green (`tests/test_signal_engine.py::TestDeterminism` 55/55)
- [x] Indicator math dtypes still all float64 (verified by `test_compute_indicators_dtypes_all_float64`)
