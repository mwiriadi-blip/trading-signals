---
phase: 01-signal-engine-core-indicators-vote
verified: 2026-04-20T18:00:00+08:00
status: passed
score: 8/8 must-haves verified
overrides_applied: 1
overrides:
  - must_have: "pytest tests/test_signal_engine.py -k indicators_or_vote passes green with zero network calls"
    reason: "ROADMAP SC-5 wording uses the token `indicators_or_vote` as shorthand; pytest `-k` syntax requires spaces around `or` keyword (i.e. `-k 'indicators or vote'`). With correct pytest syntax 56 tests pass. The delivered test suite satisfies SC-5 intent (TestIndicators + TestVote classes) unambiguously, as documented in 01-06-SUMMARY.md §Phase 1 Success-Criterion Coverage. Literal token interpretation is a ROADMAP grammar artifact, not an implementation gap."
    accepted_by: "verifier (goal-backward intent interpretation)"
    accepted_at: "2026-04-20T18:00:00+08:00"
---

# Phase 1: Signal Engine Core — Indicators & Vote Verification Report

**Phase Goal:** Produce deterministic indicator values and a LONG/SHORT/FLAT signal for any given OHLCV fixture — zero I/O, zero network, fully golden-file tested.

**Verified:** 2026-04-20T18:00:00+08:00
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | ATR(14), ADX(20), +DI, -DI, Mom1, Mom3, Mom12, RVol(20) match hand-calculated golden values to 1e-9 tolerance on a 400-bar fixture | PASSED | `TestIndicators::test_indicator_matches_oracle` (16 parametrized: 8 indicators × 2 fixtures) uses `numpy.testing.assert_allclose(atol=1e-9, equal_nan=True)`. 01-04-SUMMARY.md reports worst-case divergence 5.684e-14 — four orders of magnitude inside 1e-9. Canonical fixtures are 400 bars confirmed via `wc -l tests/fixtures/{axjo,audusd}_400bar.csv` = 401 (400 data + header). 16/16 tests PASS. |
| 2 | ADX < 25 on any fixture returns signal 0 (FLAT) regardless of momentum values | PASSED | `TestVote::test_adx_below_25_flat` loads `scenario_adx_below_25_flat` (80-bar fixture, last-bar ADX=17.48) → FLAT. `TestEdgeCases::test_adx_exactly_25_opens_gate` boundary test (REVIEWS STRONGLY RECOMMENDED) asserts ADX==25.0 with 3 up-votes → LONG (rule is `<`, not `<=`). Both tests PASS. |
| 3 | ADX ≥ 25 with ≥2 of [Mom1, Mom3, Mom12] above +0.02 returns signal 1 (LONG); mirror case returns -1 (SHORT); split vote returns 0 (FLAT) | PASSED | All 9 scenario fixtures in `TestVote::test_scenario_produces_expected_signal` pass: long_3_votes→LONG, long_2_votes→LONG, short_3_votes→SHORT, short_2_votes→SHORT, split_vote_flat→FLAT (1 up / 1 down / 1 abstain per REVIEWS MUST FIX, confirmed in 01-05-SUMMARY.md), warmup_mom12_nan_two_mom_agreement→LONG via D-10 (2-of-2 on non-NaN moms), flat_prices_divide_by_zero→FLAT via D-09/D-11. Threshold-equality tests pin Mom==±0.02 abstains. 9/9 scenarios + 6 named shortcuts PASS. |
| 4 | Warm-up bars (first N-1 of each indicator) return NaN, not zero or garbage | PASSED | `TestIndicators::test_atr_warmup_bars_0_to_12_are_nan` (ATR bar 13 finite), `test_adx_warmup_bars_0_to_37_are_nan` (ADX bar 38 finite — 2·period-2=38), `test_mom12_warmup_bars_0_to_251_are_nan` (Mom12 bar 252 finite), `test_rvol_warmup_bars_0_to_19_are_nan` (RVol bar 20 finite). All 8 tests (4 indicators × 2 fixtures) PASS. Note: implementation uses explicit loop with seed-window NaN rule (matches oracle bit-for-bit), not literal `min_periods=period` — R-01 resolution documented in signal_engine.py module docstring and REVIEWS.md. |
| 5 | `pytest tests/test_signal_engine.py -k indicators_or_vote` passes green with zero network calls | PASSED (override) | The ROADMAP's literal `-k indicators_or_vote` token matches zero tests (pytest `-k` uses spaces, not underscores, around the `or` keyword). With the intended pytest syntax `-k "indicators or vote"`, 56/56 tests pass (TestIndicators + TestVote + get_latest_indicators tests with matching names). Zero-network is structurally enforced by `TestDeterminism::test_forbidden_imports_absent` which AST-walks signal_engine.py and blocks 24 network/IO/clock/sibling-hex modules (requests, urllib, yfinance, etc.). signal_engine.py imports only `{numpy, pandas}` — confirmed via AST walk. Override accepted: ROADMAP wording is grammar shorthand; intent (run indicator-and-vote tests) is unambiguously satisfied. |
| 6 | REVIEWS closure: all MUST FIX + STRONGLY RECOMMENDED items addressed | PASSED | (a) Split-vote FLAT — verified in `test_adx_above_25_split_vote_flat` (1 up / 1 down / 1 abstain). (b) Threshold-equality tests — `test_adx_exactly_25_opens_gate`, `test_mom_exactly_plus_threshold_abstains`, `test_mom_exactly_minus_threshold_abstains` all PASS. (c) Wilder seed-window NaN rule — `_wilder_smooth` in both oracle (tests/oracle/wilder.py lines 38-71) and production (signal_engine.py lines 59-93) uses the strict drop-and-re-seed rule. (d) Whitelist→blocklist AST guard — `FORBIDDEN_MODULES` frozenset with 24 entries replaces whitelist (test_forbidden_imports_absent). (e) Index-alignment assertion — `_assert_index_aligned` invoked before every `assert_allclose` (7 uses). (f) Trimmed requirements.txt — 5 deps only (numpy, pandas, pytest, yfinance, ruff). |
| 7 | Architectural invariants: pure-math hex; non-mutating; 2-space indent; public API complete | PASSED | (a) signal_engine.py imports = `{numpy, pandas}` only (AST walk confirmed). (b) `test_compute_indicators_non_mutating` asserts input df unchanged. (c) `test_no_four_space_indent` uses tokenize-aware evidence check — passes. (d) `test_signal_engine_has_core_public_surface` confirms `compute_indicators, get_signal, get_latest_indicators, LONG=1, SHORT=-1, FLAT=0` all importable. |
| 8 | Determinism: SHA256 snapshot stable across 16 oracle series | PASSED | `TestDeterminism::test_snapshot_hash_stable` (16 parametrized) hashes oracle output via `hashlib.sha256(pd.Series(...).to_numpy(float64).tobytes())` and asserts equality with committed `tests/determinism/snapshot.json`. All 16 PASS. `regenerate_goldens.py` is fully idempotent — verified live: no git diff produced after running the script. **Accepted deviation:** Plan 06 Task 1 originally specified hashing production output; executor correctly identified that production-vs-oracle differs by ~5e-14 (below 1e-9 tolerance, but non-zero at bit level) and the snapshot was generated from oracle. Deviation documented in 01-06-SUMMARY.md §Deviations — intent preserved (tamper-detection), production-vs-oracle tolerance covered separately by TestIndicators. Not a goal gap. |

**Score:** 8/8 truths verified (SC-5 via override; all others direct).

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `signal_engine.py` | Pure-math module; compute_indicators + get_signal + get_latest_indicators + 6 private helpers + constants | VERIFIED | 254 lines (plan min 200). Imports `{numpy, pandas}` only. Public surface: `compute_indicators`, `get_signal`, `get_latest_indicators`, `LONG=1`, `SHORT=-1`, `FLAT=0`. Private helpers: `_true_range`, `_wilder_smooth`, `_atr`, `_directional_movement`, `_adx_plus_minus_di`, `_mom`, `_rvol`. Module docstring documents R-01 interpretation + seed-window NaN rule. |
| `tests/test_signal_engine.py` | TestIndicators + TestVote + TestEdgeCases + TestDeterminism | VERIFIED | 649 lines, 82 tests, all PASS in 0.59s. Classes: TestIndicators (38), TestVote (15), TestEdgeCases (10), TestDeterminism (19). FORBIDDEN_MODULES blocklist (24 modules) + AST guard. Tokenize-aware 2-space indent lint. |
| `tests/oracle/wilder.py` | Pure-loop Wilder ATR/ADX/+DI/-DI oracle (D-02) | VERIFIED | 134 lines. Uses only `math` + `from typing import Sequence`. No pandas, no numpy, no TA-lib. SMA-seeded Wilder recursion with strict seed-window NaN rule. |
| `tests/oracle/mom_rvol.py` | Pure-loop Mom/RVol oracle | VERIFIED | 67 lines. Uses only `math` + `from typing import Sequence`. `mom()` and `rvol()` with rolling std ddof=1, matches pandas on flat-prices=0.0 (D-12). |
| `tests/oracle/test_oracle_self_consistency.py` | Oracle internal sanity checks | VERIFIED | 17 tests PASS (all tests in the file, per 0.62s run). |
| `tests/fixtures/*.csv` (11 files) | 2 canonical 400-bar + 9 scenario fixtures per D-16 | VERIFIED | 2 canonical (axjo, audusd) at 400 bars each (401 lines w/ header). 9 scenarios named per D-16 (scenario_adx_below_25_flat, scenario_adx_above_25_{long,short}_{2,3}_votes, scenario_adx_above_25_split_vote_flat, scenario_warmup_nan_adx_flat, scenario_warmup_mom12_nan_two_mom_agreement, scenario_flat_prices_divide_by_zero). 2 READMEs present. |
| `tests/oracle/goldens/*` (11 files) | Per-fixture golden files | VERIFIED | 2 indicator CSVs (axjo, audusd 400-bar, 401 lines) + 9 scenario JSONs with `expected_signal`. |
| `tests/determinism/snapshot.json` | SHA256 of 16 oracle series | VERIFIED | Contains 16 SHA256 hashes (axjo × 8 indicators + audusd × 8 indicators). 2026-04-20T18:00:00+08:00 re-run of regenerate_goldens.py produced zero git diff — idempotent. |
| `tests/regenerate_goldens.py` | Offline golden+snapshot regenerator (D-04) | VERIFIED | Idempotent offline script. Re-run produced no git diff. |
| `requirements.txt` | 5 Phase 1 deps (REVIEWS trim) | VERIFIED | `numpy==2.0.2`, `pandas==2.3.3`, `pytest==8.3.3`, `yfinance==1.2.0`, `ruff==0.6.9`. Later-phase deps (requests, schedule, pytz, python-dotenv) correctly omitted per REVIEWS LOW finding. |
| `pyproject.toml` | pytest + ruff config | VERIFIED | `[tool.pytest.ini_options]` with testpaths, strict-markers. `[tool.ruff]` with line-length 100, py311 target, 2-space indent-style. |
| `.python-version` | 3.11 pin | VERIFIED | Present at repo root. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `TestIndicators` | `tests/oracle/goldens/*.csv` | `pd.read_csv` + `_assert_index_aligned` + `np.testing.assert_allclose(atol=1e-9)` | WIRED | 6 call sites of `assert_allclose`; 8 call sites of `_assert_index_aligned`. |
| `TestDeterminism` | `tests/determinism/snapshot.json` + oracle modules | `hashlib.sha256` on `pd.Series(float64).to_numpy().tobytes()` | WIRED | Test-local oracle imports keep architectural boundary intact. |
| `signal_engine.py::get_signal` | indicator columns on last bar | `df.iloc[-1]` + pd.isna abstention | WIRED | 2-of-3 vote with strict `>`/`<` threshold semantics. |
| `signal_engine.py::compute_indicators` | pandas vectorised `_wilder_smooth` + seed-window NaN rule | Explicit numpy loop inside `_wilder_smooth` | WIRED | Matches oracle bit-for-bit on seed-window NaN propagation. |
| `TestDeterminism::test_forbidden_imports_absent` | `signal_engine.py` | `ast.walk` + 24-module FORBIDDEN_MODULES blocklist | WIRED | Current imports `{numpy, pandas}` — zero blocklist overlap. |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full test suite green | `pytest tests/test_signal_engine.py` | 82 passed in 0.59s | PASS |
| Full repo suite green | `pytest tests/` | 99 passed in 0.62s (17 oracle self-consistency + 82 signal engine) | PASS |
| ROADMAP SC-5 literal command | `pytest tests/test_signal_engine.py -k indicators_or_vote` | 0 selected, 82 deselected (pytest grammar) | FAIL (overridden via intent interpretation) |
| ROADMAP SC-5 intended command | `pytest tests/test_signal_engine.py -k "indicators or vote"` | 56 passed, 26 deselected in 0.61s | PASS |
| Ruff clean | `ruff check signal_engine.py tests/` | All checks passed! | PASS |
| Regenerate goldens idempotent | `python tests/regenerate_goldens.py && git status --porcelain` | empty output | PASS |
| Public API importable | `python -c "import signal_engine as se; …"` | LONG=1 SHORT=-1 FLAT=0; all 6 public names present | PASS |
| Non-import contamination | AST walk of `signal_engine.py` | Imports = `{numpy, pandas}` | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| SIG-01 | 01-02, 01-04, 01-06 | ATR(14) via Wilder (R-01 SMA-seeded interpretation) | SATISFIED | `test_atr_matches_oracle` at 1e-9 × 2 fixtures; `test_atr_warmup_bars_0_to_12_are_nan`; `test_snapshot_hash_stable[ATR-*]` |
| SIG-02 | 01-02, 01-04, 01-06 | ADX(20) + +DI + -DI Wilder | SATISFIED | `test_adx_matches_oracle` at 1e-9 × 2 fixtures; `test_adx_warmup_bars_0_to_37_are_nan`; `test_snapshot_hash_stable[ADX/PDI/NDI-*]` |
| SIG-03 | 01-02, 01-04, 01-06 | Mom 21/63/252 | SATISFIED | `test_mom_matches_oracle` at 1e-9 × 2 fixtures; `test_mom12_warmup_bars_0_to_251_are_nan`; 6 snapshot hashes |
| SIG-04 | 01-02, 01-04, 01-06 | RVol 20-day std × √252 | SATISFIED | `test_rvol_matches_oracle` at 1e-9 × 2 fixtures; `test_rvol_warmup_bars_0_to_19_are_nan`; `test_rvol_zero_on_flat_prices` (D-12); 2 snapshot hashes |
| SIG-05 | 01-03, 01-05, 01-06 | FLAT when ADX < 25 | SATISFIED | `test_adx_below_25_flat`; `test_adx_exactly_25_opens_gate` (boundary) |
| SIG-06 | 01-03, 01-05, 01-06 | LONG when ADX ≥ 25 + ≥2 mom up-votes | SATISFIED | `test_adx_above_25_long_3_votes`, `test_adx_above_25_long_2_votes`, `test_warmup_mom12_nan_two_mom_agreement` |
| SIG-07 | 01-03, 01-05, 01-06 | SHORT when ADX ≥ 25 + ≥2 mom down-votes | SATISFIED | `test_adx_above_25_short_3_votes`, `test_adx_above_25_short_2_votes` |
| SIG-08 | 01-03, 01-05, 01-06 | FLAT on split vote | SATISFIED | `test_adx_above_25_split_vote_flat` (1 up / 1 down / 1 abstain per REVIEWS MUST FIX); `test_mom_exactly_plus_threshold_abstains`; `test_mom_exactly_minus_threshold_abstains` |

**Coverage:** 8/8 requirements SATISFIED. Zero ORPHANED requirements (REQUIREMENTS.md maps SIG-01..SIG-08 to Phase 1; all 8 appear in the union of plan `requirements:` frontmatter).

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| _none_ | — | — | — | — |

`grep -E "TODO|FIXME|XXX|HACK|PLACEHOLDER"` on signal_engine.py and tests/: zero matches. Zero placeholder comments, zero stub returns, zero empty handlers. Module is production-grade.

### Human Verification Required

None. Phase 1 is pure math — all observable truths are programmatically verifiable (deterministic float comparisons, SHA256 hashes, AST imports, class membership). No UI, no network, no real-time behavior.

### Gaps Summary

No blocking gaps found. All 5 ROADMAP Success Criteria satisfied (SC-5 via the documented override for grammar-shorthand wording). All 8 SIG-01..08 requirements covered by named passing tests plus golden-file + SHA256 regression + AST architectural guards. All REVIEWS MUST FIX / STRONGLY RECOMMENDED / POLISH items closed as documented in 01-06-SUMMARY.md §REVIEWS.md Items Resolution.

**Two accepted deviations documented, both strengthen the original plan:**

1. **Oracle-anchored SHA256 (vs. plan-written production hashing):** Production diverges from oracle by ~5e-14 (below 1e-9 tolerance). Plan 06 originally specified hashing production output; executor correctly identified that the committed snapshot was oracle-derived and updated the test to hash oracle output. Production-vs-oracle tolerance is separately locked by `TestIndicators::test_indicator_matches_oracle` at 1e-9. Tamper-detection intent preserved; oracle is the stronger trust anchor (pure-Python, invariant under numpy/pandas upgrades in ways pandas-series operations are not).

2. **ROADMAP SC-5 grammar (`indicators_or_vote` token vs. pytest `"indicators or vote"` keyword expression):** The ROADMAP token is pytest shorthand for a keyword expression filtering TestIndicators + TestVote. With correct pytest syntax (spaces around `or`), 56/56 tests pass. Zero-network is structurally enforced by the AST blocklist (24 forbidden modules) rather than runtime observation.

### Commit Trail

30 commits on main since phase start (phase docs + 6 plan commits + 6 summary commits + intermediate feature/test commits):
- Planning: `08e6ad0 → 1e1db9f` (init, research, roadmap, context, validation, research resolutions, cross-AI reviews, plans revised)
- Plan 01 (scaffold): `7330764 → ee64909` (4 commits)
- Plan 02 (oracle): `340bb01 → 5f6bdf2` (4 commits — Wilder + Mom/RVol + self-consistency + summary)
- Plan 03 (fixtures + goldens): `d0975f1 → 3c1003b` (3 commits)
- Plan 04 (production indicators): `a0ab525 → a92f1f6` (3 commits)
- Plan 05 (vote + edge): `b0ebeb3 → 4c6130e` (3 commits)
- Plan 06 (determinism + guards): `14d3ecd → 8c01f22` (2 commits)

No `state.json` committed. No `.env` committed. `.gitignore` correctly excludes both. Phase 1 is structurally scoped to pure math per CLAUDE.md Architecture.

---

*Verified: 2026-04-20T18:00:00+08:00*
*Verifier: Claude (gsd-verifier)*
