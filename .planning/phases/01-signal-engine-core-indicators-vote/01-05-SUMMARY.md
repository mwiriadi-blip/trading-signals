---
phase: 01-signal-engine-core-indicators-vote
plan: 05
subsystem: signal-engine
tags: [python, pandas, numpy, signal, vote, edge-cases, scenarios, tdd]

# Dependency graph
requires:
  - phase: 01-signal-engine-core-indicators-vote (Plan 03)
    provides: 9 named scenario fixtures (CSVs) + matching oracle golden JSONs with expected_signal per D-16
  - phase: 01-signal-engine-core-indicators-vote (Plan 04)
    provides: compute_indicators + module constants (LONG/SHORT/FLAT, ADX_GATE, MOM_THRESHOLD) + TestIndicators class + _load_fixture/_assert_index_aligned helpers
provides:
  - Public API `signal_engine.get_signal(df) -> int` returning bare int in {-1, 0, 1} per D-06, gated by ADX >= 25 with 2-of-3 momentum vote (NaN-abstaining per D-10)
  - Public API `signal_engine.get_latest_indicators(df) -> dict` returning 8-key lowercase dict of last-row indicator scalars per D-08; every value explicitly cast to Python float (REVIEWS POLISH) so numpy.float64 never leaks to JSON downstream
  - `tests/test_signal_engine.py::TestVote` — 15 tests: 9 parametrized scenario truth-table + 6 SIG-05..08 named shortcut tests
  - `tests/test_signal_engine.py::TestEdgeCases` — 10 tests: 4 D-09..D-12 edge cases + 3 threshold-equality boundary tests (REVIEWS STRONGLY RECOMMENDED) + 3 get_latest_indicators contract tests (shape, Python float, NaN preserved)
affects: [01-06 (architectural guards + determinism SHA256 snapshot consume get_signal), 02 (sizing reads get_latest_indicators), 04 (orchestrator calls get_signal/get_latest_indicators), 05 (dashboard reads last-row scalars), 06 (email renders indicator + signal scalars)]

# Tech tracking
tech-stack:
  added: [none — numpy/pandas/pytest already pinned from Plan 01]
  patterns:
    - "`get_signal` uses early-return for D-09 (NaN ADX) + SIG-05 (ADX<gate), then list comprehension for NaN-abstaining vote counting — matches RESEARCH.md §Example 4 idiom exactly"
    - "Threshold-equality semantics documented in docstring: `adx < ADX_GATE` for FLAT means equality (25.0) opens the gate; `m > +MOM_THRESHOLD` / `m < -MOM_THRESHOLD` means equality at ±0.02 abstains"
    - "`get_latest_indicators` explicit `float(row['COL'])` on every field — strips numpy.float64 wrapper; `float(np.float64(nan))` preserves NaN bit pattern as Python `float('nan')`"
    - "Scenario test pattern: load fixture CSV → load expected_signal JSON → compute_indicators → get_signal → assert int equality with named failure message"
    - "Synthetic 1-bar DataFrame via `_make_single_bar_df` helper for threshold-equality tests — bypasses compute_indicators so the test isolates the vote logic (not indicator math)"

key-files:
  created:
    - .planning/phases/01-signal-engine-core-indicators-vote/01-05-SUMMARY.md — this file
  modified:
    - signal_engine.py — appended 61 lines (get_signal + get_latest_indicators after compute_indicators); existing Plan 04 content unchanged
    - tests/test_signal_engine.py — appended 196 lines (SCENARIOS list, _load_scenario_expected helper, _make_single_bar_df helper, TestVote class, TestEdgeCases class); Plan 04 TestIndicators intact
    - .planning/STATE.md — plan counter advanced, metrics recorded
    - .planning/ROADMAP.md — Phase 01 progress updated
    - .planning/REQUIREMENTS.md — SIG-05..SIG-08 marked complete

key-decisions:
  - "Used per-function imports inside every TestVote/TestEdgeCases test (rather than a single module-level import of LONG/SHORT/FLAT) to mirror Plan 04's import style and keep each test self-contained for grep/test-filter workflows — ruff I001 autofix sorted the imports exactly as Plan 04 did"
  - "`_make_single_bar_df` helper fabricates a 1-bar DataFrame with all 8 indicator columns so threshold-equality tests (ADX==25, Mom==±0.02) can exercise `get_signal` in isolation without running `compute_indicators` — no indicator-math coupling"
  - "`get_signal` docstring enumerates both the ordinary rules AND the boundary semantics explicitly (REVIEWS STRONGLY RECOMMENDED) — any future off-by-one on `<` vs `<=` would fail the dedicated boundary tests immediately"
  - "Broke overlong `_load_scenario_expected('scenario_warmup_mom12_nan_two_mom_agreement')` line via a `stem` local to satisfy ruff E501 without sacrificing readability"

patterns-established:
  - "Hexagonal-lite extended: `get_signal` is pure (reads only `df.iloc[-1]`), no clock, no env — same boundary as compute_indicators"
  - "`get_latest_indicators` float-cast contract: any public function that emits scalar indicator values MUST use explicit `float()` to strip numpy wrappers. Future JSON serialisation in Phases 3/5/6 relies on this."
  - "Scenario-fixture truth-table testing: filename encodes the expected behaviour; JSON golden stores expected_signal; test parametrizes over the SCENARIOS tuple. Extending the truth table = add fixture + golden JSON + one line in SCENARIOS."

requirements-completed: [SIG-05, SIG-06, SIG-07, SIG-08]

# Metrics
duration: 4m18s
completed: 2026-04-20
---

# Phase 01 Plan 05: get_signal + get_latest_indicators + TestVote/TestEdgeCases Summary

**Shipped the public `get_signal` and `get_latest_indicators` API with full SIG-05..08 + D-09..D-12 coverage; 9-scenario truth table, 3 threshold-equality boundary tests, and 3 float-type contract tests — 63/63 tests in `tests/test_signal_engine.py` pass (38 Plan 04 TestIndicators + 15 TestVote + 10 TestEdgeCases).**

## Performance

- **Duration:** 4m 18s (258s)
- **Started:** 2026-04-20T20:18:28Z
- **Completed:** 2026-04-20T20:22:46Z
- **Tasks:** 2
- **Files modified:** 2 (signal_engine.py +61 lines, tests/test_signal_engine.py +196 lines)
- **Tests added:** 25 (9 parametrized scenario + 6 SIG-05..08 named shortcut + 4 D-09..12 + 3 threshold-equality + 3 get_latest_indicators contract)
- **Full file state:** signal_engine.py 254 lines (was 193); tests/test_signal_engine.py 409 lines (was 213)
- **Full-suite test count:** 80/80 passing in 0.60s (17 oracle self-consistency + 38 TestIndicators + 15 TestVote + 10 TestEdgeCases)

## Accomplishments

- `get_signal(df) -> int`: bare-int return per D-06 in {LONG=1, SHORT=-1, FLAT=0}. 2-of-3 momentum vote on last bar gated by ADX >= 25, NaN-abstaining on each momentum column. Docstring documents SIG-05..08 rules AND boundary semantics (ADX==25.0 opens gate; Mom==±0.02 abstains) inline.
- `get_latest_indicators(df) -> dict`: 8-key lowercase dict (`atr`, `adx`, `pdi`, `ndi`, `mom1`, `mom3`, `mom12`, `rvol`) per D-08. Every value goes through `float(row['COL'])` so numpy.float64 is stripped (REVIEWS POLISH). `float(np.float64(nan))` preserves NaN bit pattern, so callers get `float('nan')`, NOT `None`.
- `TestVote.test_scenario_produces_expected_signal` parametrized across all 9 D-16 scenario stems — each fixture produces exactly the `expected_signal` encoded in its golden JSON. Per-scenario breakdown:

| Scenario stem | Bars | expected_signal | actual | Last-bar ADX | Last-bar (Mom1, Mom3, Mom12) |
|---------------|-----:|:----------------|:-------|:-------------|:-----------------------------|
| scenario_adx_below_25_flat                  |  80 | 0 (FLAT)  | 0 ✓ | 17.48 | (0.0000, 0.0000, NaN)       |
| scenario_adx_above_25_long_3_votes          | 280 | 1 (LONG)  | 1 ✓ | 92.64 | (0.3594, 0.3028, 0.1000)    |
| scenario_adx_above_25_long_2_votes          | 280 | 1 (LONG)  | 1 ✓ | 84.92 | (0.2313, 0.1960, 0.0046)    |
| scenario_adx_above_25_short_3_votes         | 280 | -1 (SHORT)| -1 ✓| 92.51 | (-0.2935, -0.2675, -0.1250) |
| scenario_adx_above_25_short_2_votes         | 280 | -1 (SHORT)| -1 ✓| 84.71 | (-0.1573, -0.1401, -0.0045) |
| scenario_adx_above_25_split_vote_flat       | 280 | 0 (FLAT)  | 0 ✓ | 52.48 | (0.0579, -0.0429, -0.0030)  |
| scenario_warmup_nan_adx_flat                |  30 | 0 (FLAT)  | 0 ✓ | NaN   | (0.0170, NaN, NaN)          |
| scenario_warmup_mom12_nan_two_mom_agreement |  80 | 1 (LONG)  | 1 ✓ | 65.66 | (0.1622, 0.0500, NaN)       |
| scenario_flat_prices_divide_by_zero         |  40 | 0 (FLAT)  | 0 ✓ | NaN   | (0.0000, NaN, NaN)          |

- The split-vote scenario (`scenario_adx_above_25_split_vote_flat`) produces FLAT end-to-end per REVIEWS MUST FIX — the last-bar vote profile (+0.0579, -0.0429, -0.0030) has exactly 1 up vote, 1 down vote, 1 abstain → neither direction reaches 2 → FLAT. Confirms the Plan 03 fixture regeneration fixed the MUST-FIX ambiguity.
- TestEdgeCases covers D-09 (NaN ADX → FLAT), D-10 (Mom12 NaN with Mom1+Mom3 agreement → non-FLAT via 2-of-2), D-11 (flat-price +DI/-DI/ADX all NaN → FLAT via D-09), D-12 (flat-price RVol bit-exact 0.0).
- REVIEWS STRONGLY RECOMMENDED threshold-equality tests use `_make_single_bar_df` synthetic 1-bar DataFrames:
  - `test_adx_exactly_25_opens_gate`: ADX==25.0 + 3 up-votes → LONG
  - `test_mom_exactly_plus_threshold_abstains`: ADX=30 + all three moms==+0.02 → FLAT (0 votes)
  - `test_mom_exactly_minus_threshold_abstains`: ADX=30 + all three moms==-0.02 → FLAT (0 votes)
- REVIEWS POLISH `get_latest_indicators` contract tests:
  - Keys exactly `{atr, adx, pdi, ndi, mom1, mom3, mom12, rvol}` (D-08)
  - `type(v) is float` for every value on the axjo_400bar fixture (no numpy.float64 leak)
  - NaN preserved: on the warmup_nan_adx_flat fixture, `latest['adx']` is `float('nan')` (verified via `math.isnan` AND `isinstance(..., float)` AND `is not None`)

## REVIEWS Items Resolution

**STRONGLY RECOMMENDED — threshold-equality:** Three dedicated boundary tests pin ADX==25.0 (gate opens) and Mom==±0.02 (abstains). Any off-by-one on `<`/`>` vs `<=`/`>=` in `get_signal` would flip at least one of these three tests AND several scenario fixtures (the 2-vote scenarios sit just inside the threshold).

**POLISH — explicit float() cast:** Every `get_latest_indicators` return value uses `float(row['COL'])`. Enforced by `test_get_latest_indicators_values_are_python_float` with `type(v) is float` (strict identity, not isinstance — because numpy.float64 IS a subclass of Python float on some installs, so isinstance is insufficient). Verified on 400-bar axjo fixture: all 8 keys return `type == float`.

**POLISH — NaN preservation:** `float(np.float64(nan))` returns a Python `float` whose `math.isnan()` is True. `test_get_latest_indicators_preserves_nan_as_float_nan` uses the warmup_nan_adx_flat fixture (30 bars, not enough for ADX seed) and asserts `latest['adx']` is `float('nan')` (NOT None).

**MUST FIX (Plan 03 origin) — split-vote scenario:** Confirmed end-to-end in this plan. The split-vote fixture produces last-bar (+0.058, -0.043, -0.003) which is 1 up / 1 down / 1 abstain — neither direction reaches 2 votes — returns FLAT. Test `test_adx_above_25_split_vote_flat` passes cleanly.

## Fixture Construction Issues Discovered

None. All 9 Plan 03 scenario fixtures produced their filename-implied expected_signal on first try. No fixture regeneration needed.

## Task Commits

Each task committed atomically:

1. **Task 1: Append get_signal + get_latest_indicators to signal_engine.py** — `b0ebeb3` (feat)
2. **Task 2: TestVote + TestEdgeCases classes** — `675b713` (test)

## Files Created / Modified

- `signal_engine.py` (193 → 254 lines; +61) — appended `get_signal` + `get_latest_indicators` after `compute_indicators`. Zero changes to Plan 04 content; same module docstring; same 8 module-level constants; still numpy + pandas only imports (hexagonal-lite intact).
- `tests/test_signal_engine.py` (213 → 409 lines; +196) — appended `SCENARIOS` module constant, `_load_scenario_expected` helper, `_make_single_bar_df` helper, `TestVote` class, `TestEdgeCases` class. `TestIndicators` (Plan 04) and all its helpers untouched.
- `.planning/phases/01-signal-engine-core-indicators-vote/01-05-SUMMARY.md` — this file.

## Decisions Made

- **Per-function imports (mirror Plan 04 style):** Each TestVote/TestEdgeCases test method imports its needed constants locally (`from signal_engine import get_signal, LONG`) rather than a single module-level import. This matches Plan 04's TestIndicators idiom and lets each test be grepped/run in isolation. Ruff I001 autofix sorted each import block — exactly the same autofix Plan 04 documented.
- **`_make_single_bar_df` helper for threshold-equality tests:** Bypasses `compute_indicators` so the vote-logic test doesn't couple to indicator math. A 1-bar DataFrame with the 8 indicator columns already populated is sufficient — `get_signal` only reads `df.iloc[-1]`. This isolates the boundary semantics cleanly.
- **`stem` local variable to resolve E501:** `_load_scenario_expected('scenario_warmup_mom12_nan_two_mom_agreement')['expected_signal']` is 104 chars. Introduced `stem = 'scenario_warmup_mom12_nan_two_mom_agreement'` local then reused for both the expected JSON lookup AND `_load_fixture(stem)` call — reads cleaner too.

## Deviations from Plan

**1. [Rule 3 - Blocking issue] Ruff I001 + E501 autofix on tests/test_signal_engine.py**
- **Found during:** Task 2 post-edit ruff check
- **Issue:** 12 I001 import-sort warnings (ruff wants `LONG` / `SHORT` / `FLAT` constants sorted before `compute_indicators` in each per-function import) and 1 E501 long-line warning on `_load_scenario_expected(...)` call.
- **Fix:** `ruff check tests/test_signal_engine.py --fix` autofixed the 12 I001s (identical to Plan 04's documented autofix). The remaining E501 was refactored manually via a local `stem` variable.
- **Files modified:** `tests/test_signal_engine.py` only
- **Commit:** `675b713` (includes both the new content AND the ruff autofix)
- **Impact:** Zero — ruff autofix is formatting-only, no test semantics changed. Identical pattern to Plan 04's `--fix` deviation note.

**Total deviations:** 1 (same Rule-3 category as Plan 04; formatting-only)
**Impact on plan:** None.

## Issues Encountered

None.

## Self-Check: PASSED

- `signal_engine.py` exists (254 lines, expected >=200) — FOUND
- `tests/test_signal_engine.py` exists (409 lines, expected >=300) — FOUND
- Commit `b0ebeb3` (Task 1 feat) — FOUND in `git log --oneline`
- Commit `675b713` (Task 2 test) — FOUND in `git log --oneline`
- 9 TestVote scenario tests pass — VERIFIED
- 6 TestVote named SIG-05..08 shortcut tests pass — VERIFIED
- 4 TestEdgeCases D-09..D-12 tests pass — VERIFIED
- 3 TestEdgeCases threshold-equality tests pass — VERIFIED
- 3 TestEdgeCases get_latest_indicators contract tests pass — VERIFIED
- 63/63 tests in tests/test_signal_engine.py pass — VERIFIED
- 80/80 tests in tests/ pass (full phase regression) — VERIFIED
- Ruff clean on signal_engine.py + tests/ — VERIFIED
- `compute_indicators` count still 1 (not duplicated, not removed) — VERIFIED
- Zero banned imports in signal_engine.py (no datetime/os/requests/state_manager/notifier/dashboard) — VERIFIED

## Next Phase Readiness

- Plan 06 (architectural guards + determinism SHA256 snapshot) can now AST-walk the full `signal_engine.py` surface: `compute_indicators`, `get_signal`, `get_latest_indicators` + 8 module constants. No new imports introduced this plan.
- Phase 2 (sizing + exits) can call `get_latest_indicators(compute_indicators(df))['atr']` directly — float-typed, JSON-safe.
- Phase 4 (orchestrator) will call `get_signal(compute_indicators(df))` to pick daily signal; `get_signal` is pure and fast (last-row only), no I/O, no clock.
- No blockers.

---
*Phase: 01-signal-engine-core-indicators-vote*
*Completed: 2026-04-20*
