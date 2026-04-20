---
phase: 01-signal-engine-core-indicators-vote
plan: 03
subsystem: signal-engine-fixtures-goldens
tags: [python, yfinance, fixtures, goldens, determinism, sha256, regenerate, wave-1]
dependency_graph:
  requires:
    - "tests/oracle/wilder.py + tests/oracle/mom_rvol.py (Plan 01-02) — pure-loop oracle"
    - ".venv with yfinance 1.2.0, pandas 2.3.3, numpy 2.0.2 (Plan 01-01)"
    - "Network access for one-time yfinance pull (manual/offline — D-04 says never in CI)"
  provides:
    - "Two canonical yfinance snapshots: ^AXJO and AUDUSD=X (400 bars each) per R-03"
    - "Nine deterministic scenario fixtures covering every branch of the signal vote truth table per D-16"
    - "Offline regeneration script tests/regenerate_goldens.py (NOT run in CI per D-04)"
    - "Two canonical golden CSVs with full %.17g indicator series"
    - "Nine scenario golden JSONs with expected_signal + last_row"
    - "Determinism snapshot (SHA256 per indicator series × 2 canonical fixtures) per D-14"
  affects:
    - "Plan 01-04 (production signal_engine.py) — will be tested against oracle goldens at 1e-9 tolerance"
    - "Plan 01-05 (vote / signal tests) — will load scenario JSONs and assert expected_signal"
    - "Plan 01-06 (determinism verification) — will recompute SHA256 and compare to snapshot"
tech_stack:
  added:
    - "No new runtime libraries (reused yfinance 1.2.0, pandas 2.3.3, numpy 2.0.2 from Plan 01-01)"
    - "hashlib (stdlib) for SHA256 of float64 bytes"
    - "json (stdlib) for goldens + snapshot persistence"
  patterns:
    - "Canonical fixture CSVs written with float_format='%.17g' (Pitfall 4) — never default %g"
    - "Fixture loads explicit astype('float64') on OHLCV (Pitfall 5) — prevent numpy 2.0 float32 leaks"
    - "yfinance MultiIndex columns normalised via droplevel(1) + explicit OHLC reorder (Pitfall 2)"
    - "Flat-prices scenario uses bit-identical 100.0 floats so RVol = 0.0 bit-exact (Pitfall 6)"
    - "Scenario JSONs use allow_nan=False (NaN => null) for portable format, sort_keys=True for idempotency"
    - "Deterministic segment-endpoint scenario recipes (per REVIEWS POLISH 7) — no qualitative recipes"
    - "Split-vote scenario uses 1 up / 1 down / 1 abstain (per REVIEWS MUST FIX) — NOT 2 up / 1 down"
key_files:
  created:
    - "tests/fixtures/axjo_400bar.csv (401 lines: 400 data + header)"
    - "tests/fixtures/axjo_400bar.README.md"
    - "tests/fixtures/audusd_400bar.csv (401 lines)"
    - "tests/fixtures/audusd_400bar.README.md"
    - "tests/fixtures/scenario_adx_below_25_flat.csv (80 bars)"
    - "tests/fixtures/scenario_adx_above_25_long_3_votes.csv (280 bars)"
    - "tests/fixtures/scenario_adx_above_25_long_2_votes.csv (280 bars)"
    - "tests/fixtures/scenario_adx_above_25_short_3_votes.csv (280 bars)"
    - "tests/fixtures/scenario_adx_above_25_short_2_votes.csv (280 bars)"
    - "tests/fixtures/scenario_adx_above_25_split_vote_flat.csv (280 bars)"
    - "tests/fixtures/scenario_warmup_nan_adx_flat.csv (30 bars)"
    - "tests/fixtures/scenario_warmup_mom12_nan_two_mom_agreement.csv (80 bars)"
    - "tests/fixtures/scenario_flat_prices_divide_by_zero.csv (40 bars, bit-identical)"
    - "tests/fixtures/scenarios.README.md (191 lines)"
    - "tests/regenerate_goldens.py (189 lines)"
    - "tests/oracle/goldens/axjo_400bar_indicators.csv (401 lines)"
    - "tests/oracle/goldens/audusd_400bar_indicators.csv (401 lines)"
    - "tests/oracle/goldens/scenario_adx_below_25_flat.json"
    - "tests/oracle/goldens/scenario_adx_above_25_long_3_votes.json"
    - "tests/oracle/goldens/scenario_adx_above_25_long_2_votes.json"
    - "tests/oracle/goldens/scenario_adx_above_25_short_3_votes.json"
    - "tests/oracle/goldens/scenario_adx_above_25_short_2_votes.json"
    - "tests/oracle/goldens/scenario_adx_above_25_split_vote_flat.json"
    - "tests/oracle/goldens/scenario_warmup_nan_adx_flat.json"
    - "tests/oracle/goldens/scenario_warmup_mom12_nan_two_mom_agreement.json"
    - "tests/oracle/goldens/scenario_flat_prices_divide_by_zero.json"
    - "tests/determinism/snapshot.json"
  modified: []
decisions:
  - "Scenario fixtures authored via an inline throwaway Python snippet (not committed as a script) per plan §D-04; the scenarios.README.md documents the exact segment-endpoint recipes so they are reproducible without the snippet"
  - "%.17g formats `100.0` as the string `100` (C %g behaviour) — the scenario 9 AC grep pattern `^100\\.0,100\\.0,...` is inherently incompatible with Pitfall 4's %.17g directive; we prioritised Pitfall 4 (bit-roundtrip correctness: verified `closes[0].hex() == '0x1.9000000000000p+6'` bit-identical 100.0 after read back) over the literal AC text (Rule 1 plan-bug deviation)"
  - "Scenario 3 (long_2_votes) used the definitive plan recipe — Mom12 abstained at +0.0046, no re-tune needed"
  - "Scenario 5 (short_2_votes) used the mirror recipe — Mom12 abstained at -0.0045, no re-tune needed"
  - "Scenario 6 (split_vote_flat) used the definitive plan recipe with segment endpoints (close[27]=100.80, close[216]=105.0, close[258]=95.0, close[279]=100.5); computed Mom1=+0.0579, Mom3=-0.0429, Mom12=-0.00301 — all within target bands, no re-tune needed"
  - "Scenario 8 (warmup_mom12_nan) used the plan recipe with flat-at-100 for 30 bars, downtrend 100->90 for 30 bars, uptrend 90->105 for 20 bars; computed Mom1=+0.162, Mom3=+0.05, Mom12=NaN, ADX=65.66 — all targets met, no re-tune needed"
  - "ruff I001 (isort) flagged the `tests.oracle` imports as unsorted because they sit after `sys.path.insert`; added `# noqa: E402, I001` to both import lines (Rule 3 blocking — without this suppression ruff check tests/ fails at the full-plan verification gate)"
metrics:
  duration_minutes: 10
  completed_date: "2026-04-20"
  tasks_completed: 2
  files_created: 28
  files_modified: 0
  commits: 2
  canonical_fixture_bars: 400
  canonical_fixture_instruments: 2
  scenario_fixture_count: 9
  golden_csv_count: 2
  golden_json_count: 9
  determinism_snapshot_entries: 16  # 2 fixtures × 8 indicators
  idempotency_verified: true
requirements: [SIG-01, SIG-02, SIG-03, SIG-04, SIG-05, SIG-06, SIG-07, SIG-08]
---

# Phase 01 Plan 03: Fixtures + Goldens + Determinism Snapshot Summary

**One-liner:** Two 400-bar yfinance canonical fixtures (`^AXJO` + `AUDUSD=X` per R-03) plus nine deterministic-endpoint scenario fixtures committed alongside an offline regenerate_goldens.py pipeline that produced the oracle goldens (2 canonical CSVs + 9 per-scenario JSONs) and a SHA256 determinism snapshot keyed by fixture × indicator — split-vote scenario verified to use 1 up / 1 down / 1 abstain per REVIEWS MUST FIX.

## Performance

- **Duration:** ~10 min
- **Started:** 2026-04-20T19:51:00Z
- **Completed:** 2026-04-20T20:01:00Z
- **Tasks:** 2/2 (both `type="auto"`, no checkpoints)
- **Files created:** 28 (14 fixture files + 1 script + 11 goldens + 1 snapshot + 1 SUMMARY)
- **Files modified:** 0
- **Commits:** 2 per-task + 1 metadata

## Accomplishments

- **yfinance canonical snapshots** for both signal instruments (R-03: ^AXJO and AUDUSD=X), 400 bars each, with provenance READMEs documenting Pitfall 2 (MultiIndex normalisation), Pitfall 3 (retroactive adjustments), and Pitfall 4 (`%.17g` precision).
- **9 deterministic scenario fixtures** covering every branch of the signal vote truth table per D-16; each built with exact segment-endpoint recipes (per REVIEWS POLISH 7), not qualitative prose.
- **Split-vote scenario corrected** per REVIEWS MUST FIX: uses 1 up / 1 down / 1 abstain (Mom1 > +0.02, Mom3 < -0.02, Mom12 ∈ [-0.02, +0.02]) producing FLAT per SIG-08, NOT the self-contradictory 2 up / 1 down of the original plan draft.
- **Offline regenerate_goldens.py pipeline** (D-04: never in CI) reads fixtures, runs the Plan 01-02 pure-loop oracle, emits per-instrument golden CSVs with `%.17g` precision, per-scenario JSONs with `allow_nan=False` (NaN → null), and a SHA256 float64-bytes snapshot per D-14.
- **Idempotency verified:** re-running `tests/regenerate_goldens.py` produces byte-identical outputs (`git diff --stat` = 0 lines).
- **All 9 scenarios' expected_signal values match their filename semantics** — verified at generation time and at the full-plan verification gate.

## yfinance Pull Provenance

| Item | Value |
|---|---|
| yfinance version | 1.2.0 |
| pandas version | 2.3.3 |
| numpy version | 2.0.2 |
| Python version | 3.11.8 |
| Pull date | 2026-04-20 |
| ^AXJO date range | 2024-09-17 → 2026-04-17 (400 bars) |
| AUDUSD=X date range | 2024-10-01 → 2026-04-20 (400 bars) |
| auto_adjust | True (modern default) |
| CSV precision | `float_format='%.17g'` (Pitfall 4) |

## Scenario Fixtures — Bar Counts + Expected Signals + Last-Row Indicators

| Scenario | Bars | Expected | ADX | Mom1 | Mom3 | Mom12 | RVol |
|---|---:|---:|---:|---:|---:|---:|---:|
| `adx_below_25_flat` | 80 | 0 (FLAT) | 17.48 | 0.00000 | 0.00001 | null | 0.00351 |
| `adx_above_25_long_3_votes` | 280 | 1 (LONG) | 92.64 | 0.35936 | 0.30278 | 0.10000 | 0.30180 |
| `adx_above_25_long_2_votes` | 280 | 1 (LONG) | 84.92 | 0.23129 | 0.19600 | 0.00460 | 0.07945 |
| `adx_above_25_short_3_votes` | 280 | -1 (SHORT) | 92.51 | -0.29350 | -0.26751 | -0.12500 | 0.32379 |
| `adx_above_25_short_2_votes` | 280 | -1 (SHORT) | 84.71 | -0.15734 | -0.14008 | -0.00453 | 0.07147 |
| `adx_above_25_split_vote_flat` | 280 | 0 (FLAT) | 52.48 | 0.05789 | -0.04286 | -0.00301 | 0.04646 |
| `warmup_nan_adx_flat` | 30 | 0 (FLAT) | null | 0.01705 | null | null | 0.05314 |
| `warmup_mom12_nan_two_mom_agreement` | 80 | 1 (LONG) | 65.66 | 0.16221 | 0.05000 | null | 0.02949 |
| `flat_prices_divide_by_zero` | 40 | 0 (FLAT) | null | 0.00000 | null | null | 0.00000 |

### Scenario 6 (Split-Vote) — MUST FIX Verification

Split-vote produces FLAT via 1 up / 1 down / 1 abstain:

- **Mom1 = +0.05789** > +0.02 ⇒ **UP vote** ✓
- **Mom3 = -0.04286** < -0.02 ⇒ **DOWN vote** ✓
- **Mom12 = -0.00301** ∈ [-0.02, +0.02] ⇒ **ABSTAINS** ✓
- **ADX = 52.48** ≥ 25 ⇒ gate open ✓
- **Result:** 1 up / 1 down / 0 net majority ⇒ **FLAT (0)** per SIG-08 ✓

### Final Close Values at Segment Endpoints (Scenarios 3, 5, 6, 8)

No re-tuning was required. The definitive recipes in the plan produced valid indicator values on first pass:

**Scenario 3 (`long_2_votes`):**
- Bars 0–17: flat 100.0; 18–256: linear down 100→80; 257–275: linear up 80→97.5; 276–278: flat 97.5; 279: **99.7** ✓

**Scenario 5 (`short_2_votes`):**
- Bars 0–17: flat 100.0; 18–256: linear up 100→120; 257–275: linear down 120→102.5; 276–278: flat 102.5; 279: **100.3** ✓

**Scenario 6 (`split_vote_flat`):**
- Bars 0–17: flat 100.0; 18–130: linear up 100→110; 131–216: linear down ≈109.94→**105.0**; 217–258: linear down ≈104.76→**95.0**; 259–278: linear up ≈95.2→99.0; 279: **100.5** ✓
- Computed close[27] = 100.804 (on uptrend); Mom12 anchor = 100.804; close[258] = 95.0 exactly; close[216] = 105.0 exactly.

**Scenario 8 (`warmup_mom12_nan_two_mom_agreement`):**
- Bars 0–29: flat 100.0; 30–59: linear down 100→90; 60–79: linear up 90→**105.0** ✓
- Computed close[16] = 100.0 (flat), close[58] = 90.345 (end of downtrend); Mom1 = +0.162, Mom3 = +0.05, Mom12 = NaN (only 80 bars < 253).

## SHA256 Determinism Snapshot (first 12 chars)

For Plan 06 to sanity-check against. Full 64-char hexdigests live at `tests/determinism/snapshot.json`.

### `^AXJO` (axjo_400bar)

| Indicator | SHA256 (first 12) |
|---|---|
| ATR | `2bdbf18971e7` |
| ADX | `dc9e0f82746e` |
| PDI | `78dd04646039` |
| NDI | `9a619dfc3858` |
| Mom1 | `18e83f7f05e5` |
| Mom3 | `9ce195ebb1a0` |
| Mom12 | `a8c122f76c7e` |
| RVol | `d226eb53a206` |

### `AUDUSD=X` (audusd_400bar)

| Indicator | SHA256 (first 12) |
|---|---|
| ATR | `75a8af006657` |
| ADX | `40b83b7225d5` |
| PDI | `ca4441df61e8` |
| NDI | `0a6c342e9616` |
| Mom1 | `9b4b7343f2ff` |
| Mom3 | `e06e59572428` |
| Mom12 | `9628f2301742` |
| RVol | `09c850f014b5` |

## Task Commits

Each task committed atomically:

1. **Task 1: Pull canonical fixtures + author scenario fixtures** — `d0975f1` (feat)
2. **Task 2: Write regenerate_goldens.py + emit goldens + snapshot** — `746302b` (feat)

**Plan metadata commit:** will follow this SUMMARY + STATE/ROADMAP updates.

## Verification Results

All 7 full-plan verification gates pass:

| Gate | Expected | Actual |
|---|---|---|
| 1. Fixture CSV count | 11 (2 canonical + 9 scenarios) | 11 ✓ |
| 2. Canonical golden CSV count | 2 | 2 ✓ |
| 3. Scenario golden JSON count | 9 | 9 ✓ |
| 4. Determinism snapshot exists | yes | yes ✓ |
| 5. Regenerate is idempotent | byte-identical on re-run | git diff = 0 ✓ |
| 6. `ruff check tests/` | exit 0 | exit 0 ✓ |
| 7. Split-vote MUST FIX verification | FLAT via Mom1>+0.02, Mom3<-0.02, Mom12∈[-0.02,+0.02] | verified ✓ |

Additionally: 17/17 oracle self-consistency tests (Plan 01-02) still pass with no regression.

## Decisions Made

- **Scenario generator NOT committed as a script.** The generator logic is inline in the Task 1 execution block and fully documented in `tests/fixtures/scenarios.README.md` (191 lines with exact segment endpoints). Rationale: per D-04 the only committed "regenerator" is `tests/regenerate_goldens.py` which consumes committed fixtures. Committing a fixture-creation script would create a second supply-chain surface (random-seed drift, bar-count drift) for no benefit — the 9 fixture CSVs ARE the trust anchor.
- **Prioritised Pitfall 4 (`%.17g`) over the literal AC grep pattern.** Plan Task 1 AC #9 specified `grep -c '^100\.0,100\.0,100\.0,100\.0,0$' ... >= 30`, which is inherently incompatible with `%.17g` (C `%g` renders `100.0` as the string `100`). We chose bit-roundtrip correctness (verified: `float(100) == 100.0` bit-identical after CSV round-trip, closes[0].hex() == `0x1.9000000000000p+6`) over the literal AC text. All 40 bars of `scenario_flat_prices_divide_by_zero.csv` are bit-identical 100.0 floats; RVol returns exactly 0.0 as required by Pitfall 6.
- **scenario_6 re-tune not needed.** The plan's long-winded re-tune math for the split-vote scenario (self-consistency-check on close[27]/close[216]/close[258]/close[279]) turned out to be correct on first pass with the definitive recipe.
- **`I001` (isort) ruff-noqa on `tests.oracle` imports.** The `sys.path.insert` + post-hoc `from tests.oracle...` pattern triggers I001 because ruff isort treats those as third-party imports that should come before. Since we CAN'T move them above `sys.path.insert`, the `# noqa: E402, I001` suppression is the correct fix.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Task 1 AC #9 incompatible with Pitfall 4 (`%.17g` precision)**

- **Found during:** Task 1 verification (AC grep).
- **Issue:** Plan AC asserts `grep -c '^100\.0,100\.0,100\.0,100\.0,0$' scenario_flat_prices_divide_by_zero.csv >= 30`. But the plan also mandates `float_format='%.17g'` per Pitfall 4, which renders the float `100.0` as the string `100` (not `100.0`) because C `%g` strips trailing zeros. The AC as literally written returns 0 (zero matches) when `%.17g` is honoured.
- **Fix:** Honour Pitfall 4 (the primary instruction). Verified Pitfall 6 compliance via round-trip bit check: `closes[0] == 100.0` exactly, `closes[0].hex() == '0x1.9000000000000p+6'`, all 40 bars bit-identical ⇒ RVol = 0.0 exactly. 40 rows match the relaxed pattern `^2[0-9][0-9][0-9]-...,100,100,100,100,0$`.
- **Files modified:** no file changes — this is an AC-text-vs-code-behaviour reconciliation.
- **Committed in:** `d0975f1` (Task 1 commit — fixture content is correct).

**2. [Rule 3 - Blocking] ruff I001 (isort) violation in `tests/regenerate_goldens.py`**

- **Found during:** Task 2 full-plan verification gate (`ruff check tests/`).
- **Issue:** ruff isort flagged `from tests.oracle.wilder import ...` and `from tests.oracle.mom_rvol import ...` as unsorted because they appear after `sys.path.insert(0, str(ROOT))` with an intervening blank line, and ruff treats them as third-party imports needing to sort up. But they MUST stay below the `sys.path.insert` because the path needs to be on `sys.path` before the import resolves.
- **Fix:** Added `I001` to the existing `# noqa: E402` comments on both lines (`# noqa: E402, I001`). ruff now clean.
- **Files modified:** `tests/regenerate_goldens.py` (noqa comments only).
- **Committed in:** `746302b` (Task 2 commit).

---

**Total deviations:** 2 auto-fixed (1 Rule 1 plan-bug, 1 Rule 3 blocking ruff).
**Impact on plan:** Both fixes are cosmetic — neither affects numerical outputs, fixture correctness, scenario signal semantics, or determinism snapshot stability. No scope creep.

## Issues Encountered

None. Network was available for the yfinance pull; all 9 scenarios' computed indicators matched their target bands on first pass (no re-tuning of segment endpoints required).

## User Setup Required

None. The plan introduced no external service configuration.

## Known Stubs

None. All fixtures are real data (either pulled from yfinance or constructed per exact deterministic recipes) and all goldens are computed from the Plan 01-02 oracle. No TODO placeholders, no mock data.

## TDD Gate Compliance

This plan is not `type: tdd`. Both tasks are `type="auto"`. The regenerate_goldens.py script is exercised at plan-execution time (Task 2 runs it and verifies outputs) — production signal_engine.py tests against these goldens will be added in Plan 01-04 + 01-05.

## Threat Flags

None. Plan's threat register (T-01-03-01/02/03) addressed as documented:
- Fixture tampering: mitigated by determinism snapshot + git diff surface.
- yfinance supply chain: manual regen only (D-04), pinned versions, public market data.
- Regenerate hang: developer-local manual operation.

No new threat surface introduced beyond the plan's own register.

## Self-Check

### Created Files

```
FOUND: tests/fixtures/axjo_400bar.csv
FOUND: tests/fixtures/axjo_400bar.README.md
FOUND: tests/fixtures/audusd_400bar.csv
FOUND: tests/fixtures/audusd_400bar.README.md
FOUND: tests/fixtures/scenario_adx_below_25_flat.csv
FOUND: tests/fixtures/scenario_adx_above_25_long_3_votes.csv
FOUND: tests/fixtures/scenario_adx_above_25_long_2_votes.csv
FOUND: tests/fixtures/scenario_adx_above_25_short_3_votes.csv
FOUND: tests/fixtures/scenario_adx_above_25_short_2_votes.csv
FOUND: tests/fixtures/scenario_adx_above_25_split_vote_flat.csv
FOUND: tests/fixtures/scenario_warmup_nan_adx_flat.csv
FOUND: tests/fixtures/scenario_warmup_mom12_nan_two_mom_agreement.csv
FOUND: tests/fixtures/scenario_flat_prices_divide_by_zero.csv
FOUND: tests/fixtures/scenarios.README.md
FOUND: tests/regenerate_goldens.py
FOUND: tests/oracle/goldens/axjo_400bar_indicators.csv
FOUND: tests/oracle/goldens/audusd_400bar_indicators.csv
FOUND: tests/oracle/goldens/scenario_adx_below_25_flat.json
FOUND: tests/oracle/goldens/scenario_adx_above_25_long_3_votes.json
FOUND: tests/oracle/goldens/scenario_adx_above_25_long_2_votes.json
FOUND: tests/oracle/goldens/scenario_adx_above_25_short_3_votes.json
FOUND: tests/oracle/goldens/scenario_adx_above_25_short_2_votes.json
FOUND: tests/oracle/goldens/scenario_adx_above_25_split_vote_flat.json
FOUND: tests/oracle/goldens/scenario_warmup_nan_adx_flat.json
FOUND: tests/oracle/goldens/scenario_warmup_mom12_nan_two_mom_agreement.json
FOUND: tests/oracle/goldens/scenario_flat_prices_divide_by_zero.json
FOUND: tests/determinism/snapshot.json
```

### Commits

```
FOUND: d0975f1 feat(01-03): add canonical + scenario fixtures for oracle goldens
FOUND: 746302b feat(01-03): add regenerate_goldens.py + oracle goldens + determinism snapshot
```

## Next Phase Readiness

- Fixtures + goldens + snapshot ready for Plan 01-04 (production `signal_engine.py` — will test production outputs against oracle goldens at 1e-9 tolerance).
- Scenario JSONs ready for Plan 01-05 (vote truth-table tests — load JSON, assert `expected_signal == get_signal(df)` for each fixture).
- Determinism snapshot ready for Plan 01-06 (rehash and assert equality; any numpy/pandas upgrade that shifts float bits fails loudly).
- No blockers.

## Self-Check: PASSED

---

*Phase: 01-signal-engine-core-indicators-vote*
*Completed: 2026-04-20*
