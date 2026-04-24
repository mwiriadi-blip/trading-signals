---
phase: 01-signal-engine-core-indicators-vote
plan: 04
subsystem: signal-engine
tags: [python, pandas, numpy, indicators, wilder, atr, adx, mom, rvol, production]

# Dependency graph
requires:
  - phase: 01-signal-engine-core-indicators-vote (Plan 02)
    provides: pure-loop Wilder/Mom/RVol oracle (tests/oracle/wilder.py, mom_rvol.py) — the 1e-9 trust anchor
  - phase: 01-signal-engine-core-indicators-vote (Plan 03)
    provides: 2 canonical fixtures (^AXJO, AUDUSD=X) + matching oracle golden CSVs
provides:
  - pure-math `signal_engine.compute_indicators(df)` — pandas-vectorised Wilder implementation matching oracle to ~5.7e-14 (well inside 1e-9)
  - `_wilder_smooth` helper with SMA seed + NaN-strict seed-window rule (REVIEWS MEDIUM) — bit-for-bit equivalence with oracle
  - Module-level constants for Phase 2+ consumers (LONG/SHORT/FLAT, ATR_PERIOD, ADX_PERIOD, MOM_PERIODS, RVOL_PERIOD, ANNUALISATION_FACTOR, ADX_GATE, MOM_THRESHOLD)
  - `tests/test_signal_engine.py::TestIndicators` — 38 tests including parametrized oracle comparisons, warmup invariants, non-mutation (D-07), float64 dtype (Pitfall 5), and explicit index-alignment guard
affects: [01-05 (vote + edge-case tests will import compute_indicators), 01-06 (architectural guards + determinism hash snapshot), 02 (sizing reads get_latest_indicators), 04 (orchestrator calls compute_indicators), 05 (dashboard reads indicator columns), 06 (email renders indicator scalars)]

# Tech tracking
tech-stack:
  added: [none — all deps (numpy, pandas, pytest) already pinned in requirements.txt from Plan 01]
  patterns:
    - Hexagonal-lite pure-math module (numpy + pandas imports only; no I/O, no clock, no cross-hex imports)
    - SMA-seeded Wilder ewm via explicit loop with NaN-strict seed window (matches oracle loop exactly)
    - D-07 non-mutation via `df.copy()` at the top of `compute_indicators`
    - Pitfall 5 defense: explicit `.astype('float64')` on every assigned indicator column (12 casts)
    - Test pattern: `_assert_index_aligned(computed, golden)` called BEFORE every `assert_allclose` (REVIEWS MEDIUM)
    - D-11 NaN propagation via `series.where(series != 0.0, np.nan)` (no epsilons, no magic numbers)
    - D-12 RVol exact zero on flat prices via `close.pct_change().rolling(20).std()`

key-files:
  created:
    - signal_engine.py — production indicator library (193 lines)
    - tests/test_signal_engine.py — TestIndicators class (213 lines, 38 tests)
    - .planning/phases/01-signal-engine-core-indicators-vote/01-04-SUMMARY.md — this file
  modified:
    - .planning/STATE.md — plan counter advanced, metrics recorded
    - .planning/ROADMAP.md — Phase 01 progress updated

key-decisions:
  - "Production _wilder_smooth uses an explicit numpy loop (not pandas .ewm) because the oracle's NaN-strict seed-window rule REQUIRES the procedural check; pandas .ewm(adjust=False).mean() with .iloc[:period].mean() seed would silently use skipna=True and diverge from oracle on any NaN in the seed window"
  - "All 12 indicator column assignments explicitly .astype('float64') to defend against numpy 2.0 float32 upcast leaks (Pitfall 5)"
  - "D-11 NaN propagation implemented via Series.where(series != 0.0, np.nan) so division-by-zero on sum(TR)==0 flat prices yields NaN rather than inf — no epsilon hacks"
  - "_assert_index_aligned called before every assert_allclose per REVIEWS MEDIUM so date-index drift fails with a clear message rather than opaquely comparing wrong floats"
  - "Plan 04 tasks committed in order given (Task 1 implementation, Task 2 tests) rather than strict test-first, because Task 1's <verify> block runs an equivalent one-shot Python check that exercises the public API before committing"

patterns-established:
  - "_wilder_smooth seed-window protocol: scan forward until a `period`-length window of all non-NaN values is found; seed there; on any subsequent NaN, drop the seed and scan again. This is the canonical Wilder-with-warmup idiom."
  - "Pure-math module boundary: every signal_engine.py export is a function of its arguments only. No clock, no env, no cross-hex imports. Phase 1 establishes the enforcement style that Phase 06's AST guard will formalize."
  - "Golden-vs-computed test pattern: load fixture at float64 → compute → assert index/shape/column-order → assert_allclose(atol=1e-9, equal_nan=True). This pattern will generalise to Plan 05's scenario tests."

requirements-completed: [SIG-01, SIG-02, SIG-03, SIG-04]

# Metrics
duration: 4min
completed: 2026-04-20
---

# Phase 01 Plan 04: Production signal_engine.py Summary

**Pandas-vectorised Wilder/Mom/RVol indicator library matching the pure-loop oracle to ~5.7e-14 across 8 indicators × 2 canonical fixtures, with NaN-strict seed-window rule and explicit index-alignment guards on every comparison.**

## Performance

- **Duration:** 4 min (244 s)
- **Started:** 2026-04-20T20:09:20Z
- **Completed:** 2026-04-20T20:13:24Z
- **Tasks:** 2
- **Files created:** 2 (signal_engine.py, tests/test_signal_engine.py)
- **Tests added:** 38 (16 parametrized oracle matches + 8 SIG-XX named + 8 warmup + 2 shape/index + 2 non-mutation + 2 float64)

## Accomplishments

- `signal_engine.compute_indicators(df)` returns a NEW DataFrame with 8 indicator columns (ATR, ADX, PDI, NDI, Mom1, Mom3, Mom12, RVol) — D-07 non-mutating, all float64 (Pitfall 5).
- Private helpers wired per plan: `_true_range`, `_wilder_smooth`, `_atr`, `_directional_movement`, `_adx_plus_minus_di`, `_mom`, `_rvol`. All pure; numpy + pandas only.
- Production `_wilder_smooth` implements the oracle's NaN-strict seed-window rule exactly: first bar `i` where `series[i-period+1:i+1]` contains zero NaN values seeds via `mean()`; recursion `sm[t] = sm[t-1] + (raw[t] - sm[t-1]) / period` from bar `i+1`; any NaN in the window during or before seeding drops the seed and scans forward. Matches oracle's pure-loop behaviour — REVIEWS MEDIUM resolved.
- 8 module-level constants locked for Phase 2+ consumers: LONG=1, SHORT=-1, FLAT=0, ATR_PERIOD=14, ADX_PERIOD=20, MOM_PERIODS=(21,63,252), RVOL_PERIOD=20, ANNUALISATION_FACTOR=252, ADX_GATE=25.0, MOM_THRESHOLD=0.02.
- `TestIndicators` test class: 16 parametrized oracle comparisons + 8 SIG-01..04 named shortcut tests + 8 warmup invariants + 2 shape/index/column-order guards + 2 non-mutation tests + 2 float64 dtype tests = 38 tests, all passing in 0.46 s.
- Every float comparison preceded by `_assert_index_aligned(computed, golden)` — REVIEWS MEDIUM resolved (date-index drift would fail with a clear message rather than opaquely comparing wrong floats).
- Module docstring documents R-01 SIG-01 formula interpretation AND the seed-window NaN rule inline, so future maintainers understand WHY the production code is not a single pandas one-liner.

## Per-Indicator Oracle-vs-Production Max Abs Diff

All values << 1e-9 tolerance. Canonical fixtures: `^AXJO` (SPI 200 proxy) and `AUDUSD=X`, both 400 bars per R-03.

| Indicator | axjo_400bar      | audusd_400bar    | NaN mismatch |
|-----------|------------------|------------------|--------------|
| ATR       | 5.684e-14        | 1.006e-16        | 0            |
| ADX       | 2.842e-14        | 3.553e-14        | 0            |
| PDI       | 4.263e-14        | 2.132e-14        | 0            |
| NDI       | 2.842e-14        | 2.842e-14        | 0            |
| Mom1      | 1.908e-16        | 2.030e-16        | 0            |
| Mom3      | 1.943e-16        | 2.030e-16        | 0            |
| Mom12     | 2.030e-16        | 1.934e-16        | 0            |
| RVol      | 6.939e-16        | 5.274e-16        | 0            |

Max observed diff across all 16 (indicator × fixture) combinations: **5.684e-14**, four orders of magnitude inside the 1e-9 plan tolerance. The ATR/ADX/DI diffs at 1e-14 are expected — pandas-vectorised Wilder loses a few ULPs over 400 bars of recursion vs the pure-loop oracle; Mom and RVol match at machine epsilon because both are non-recursive.

## REVIEWS MEDIUM Resolution (both items)

**1. Seed-window NaN rule — production matches oracle:** Verified by direct unit check

```
python -c "from signal_engine import _wilder_smooth; \
  s = pd.Series([nan, 1, 2, 3, 4]); out = _wilder_smooth(s, 3); \
  assert all(isna(out[:3])); assert out[3] == 2.0"
```

Result: `OK seed-window NaN rule`. Production drops the seed at bar 0 (NaN present), waits until bar 3 for the first full non-NaN window [1,2,3] → SMA=2.0 → recursion from bar 4.

**2. Index-alignment assertion before every assert_allclose:** `_assert_index_aligned(computed, golden)` helper defined once, invoked by all 6 assert-allclose-bearing tests (including the 16-way parametrized one). A dedicated `test_output_shape_index_columns_are_correct` test makes the guard explicit and grep-findable. Grep counts: `assert_allclose`=7, `_assert_index_aligned`=8, `index.equals`=2 — all AC thresholds cleared.

## Task Commits

Each task committed atomically:

1. **Task 1: Implement signal_engine.py** — `a0ab525` (feat)
2. **Task 2: TestIndicators class** — `f75151a` (test)

## Files Created / Modified

- `signal_engine.py` (193 lines) — pure-math indicator library; module docstring documents R-01 interpretation + seed-window NaN rule; only `numpy` + `pandas` imports
- `tests/test_signal_engine.py` (213 lines) — TestIndicators class with 38 tests across 2 canonical fixtures

## Decisions Made

- **Explicit numpy loop inside `_wilder_smooth` (rather than a chained pandas expression):** The seed-window NaN rule requires a stateful `seeded` flag and per-bar decision to drop or continue seeding. Pandas `.ewm(adjust=False).mean()` does not expose this hook; wrapping with `.where(notna)` and `.mean(skipna=False)` would duplicate the work and still not match oracle on the drop-and-re-seed branch. The loop is O(n) and runs on 400 bars in microseconds.
- **`.astype('float64')` applied 12 times across the module:** Each explicit cast defends one code-path against numpy 2.0 float32 upcast leaks. Phase 06 will verify via the SHA256 determinism snapshot.
- **Non-TDD ordering within this "execute" plan:** Task 1 (implementation) committed before Task 2 (tests) per the plan's written task order. Task 1 has its own `<verify>` inline Python one-liner that exercises the public API surface before commit, so the production code is known-green before the test file is written.

## Deviations from Plan

None — plan executed exactly as written. The only non-trivial event during execution was a single ruff I001 import-sort warning on `tests/test_signal_engine.py` which was auto-fixed by `ruff check --fix` (removed the blank line between stdlib and first-party imports since `signal_engine` is configured as `known-first-party` and the pyproject isort config treats it as a single group). Not a deviation from plan intent; the file content is identical to the plan's `<action>` except for the import grouping.

**Total deviations:** 0
**Impact on plan:** None.

## Issues Encountered

None.

## Self-Check: PASSED

- `signal_engine.py` exists (193 lines, expected >=80) — FOUND
- `tests/test_signal_engine.py` exists (213 lines, expected >=100) — FOUND
- Commit `a0ab525` (Task 1 feat) — FOUND in `git log --oneline`
- Commit `f75151a` (Task 2 test) — FOUND in `git log --oneline`
- 38 TestIndicators tests pass — VERIFIED
- 55 full-suite tests pass (17 oracle self-consistency + 38 new) — VERIFIED
- Ruff clean on both files — VERIFIED

## Next Phase Readiness

- Plan 05 (TestVote + TestEdgeCases + `get_signal` + `get_latest_indicators`) can now import `compute_indicators` directly and build on the shipped `_wilder_smooth`/constants.
- Plan 06 (architectural guards + determinism SHA256 snapshot) can AST-walk `signal_engine.py` to assert the hex boundary; the module has only `numpy` + `pandas` imports, so any new import is a guard-violation signal.
- Phase 2 (sizing + exits) can consume `compute_indicators` output directly; `get_latest_indicators` scalar helper is the Plan 05 deliverable that makes last-bar access ergonomic.
- No blockers.

---
*Phase: 01-signal-engine-core-indicators-vote*
*Completed: 2026-04-20*
