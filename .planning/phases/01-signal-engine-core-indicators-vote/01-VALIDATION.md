---
phase: 1
slug: signal-engine-core-indicators-vote
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-20
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `01-RESEARCH.md` §Validation Architecture. Populated during planning.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x (no pytest-cov per D-16; no pytest-freezer per D-15) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` — created in Wave 0 |
| **Quick run command** | `pytest tests/test_signal_engine.py -x -q` |
| **Full suite command** | `pytest tests/` |
| **Estimated runtime** | <5 seconds (pure math, no I/O, no network) |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_signal_engine.py -x -q`
- **After every plan wave:** Run `pytest tests/`
- **Before `/gsd-verify-work`:** Full suite green + `ruff check signal_engine.py tests/` clean + SHA256 determinism snapshot committed
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

_Populated during planning. Research surfaced these minimum required assertions:_

| Req ID | Behavior | Test Type | Automated Command | File Exists |
|--------|----------|-----------|-------------------|-------------|
| SIG-01 | ATR(14) Wilder (SMA-seeded) matches oracle to 1e-9 on 400-bar fixture | unit | `pytest tests/test_signal_engine.py::TestIndicators::test_atr_matches_oracle -x` | ❌ Wave 0 |
| SIG-02 | ADX(20) + +DI + -DI match oracle to 1e-9 | unit | `pytest tests/test_signal_engine.py::TestIndicators::test_adx_matches_oracle -x` | ❌ Wave 0 |
| SIG-02 | ADX returns NaN for first 38 bars on 60-bar synthetic | unit | `pytest tests/test_signal_engine.py::TestIndicators::test_adx_warmup_bars_are_nan -x` | ❌ Wave 0 |
| SIG-03 | Mom1/Mom3/Mom12 = pct_change(21/63/252) | unit | `pytest tests/test_signal_engine.py::TestIndicators::test_mom_matches_oracle -x` | ❌ Wave 0 |
| SIG-04 | RVol = rolling(20).std × √252; flat prices → 0.0 | unit | `pytest tests/test_signal_engine.py::TestIndicators::test_rvol_matches_oracle -x` | ❌ Wave 0 |
| SIG-05 | ADX < 25 returns FLAT regardless of momentum | unit | `pytest tests/test_signal_engine.py::TestVote::test_adx_below_25_flat -x` | ❌ Wave 0 |
| SIG-06 | ADX ≥ 25 + 3-vote up → LONG | unit | `pytest tests/test_signal_engine.py::TestVote::test_adx_above_25_long_3_votes -x` | ❌ Wave 0 |
| SIG-06 | ADX ≥ 25 + 2-vote up → LONG | unit | `pytest tests/test_signal_engine.py::TestVote::test_adx_above_25_long_2_votes -x` | ❌ Wave 0 |
| SIG-07 | ADX ≥ 25 + 3-vote down → SHORT | unit | `pytest tests/test_signal_engine.py::TestVote::test_adx_above_25_short_3_votes -x` | ❌ Wave 0 |
| SIG-07 | ADX ≥ 25 + 2-vote down → SHORT | unit | `pytest tests/test_signal_engine.py::TestVote::test_adx_above_25_short_2_votes -x` | ❌ Wave 0 |
| SIG-08 | ADX ≥ 25 + split vote → FLAT | unit | `pytest tests/test_signal_engine.py::TestVote::test_adx_above_25_split_vote_flat -x` | ❌ Wave 0 |
| D-09 | NaN ADX → FLAT (warmup scenario) | unit | `pytest tests/test_signal_engine.py::TestEdgeCases::test_warmup_nan_adx_flat -x` | ❌ Wave 0 |
| D-10 | Mom12 NaN + Mom1+Mom3 agree → LONG/SHORT | unit | `pytest tests/test_signal_engine.py::TestEdgeCases::test_warmup_mom12_nan_two_mom_agreement -x` | ❌ Wave 0 |
| D-11 | Flat prices → +DI/-DI NaN → ADX NaN → FLAT | unit | `pytest tests/test_signal_engine.py::TestEdgeCases::test_flat_prices_divide_by_zero -x` | ❌ Wave 0 |
| D-12 | Flat prices → RVol = 0.0 exactly | unit | `pytest tests/test_signal_engine.py::TestEdgeCases::test_rvol_zero_on_flat_prices -x` | ❌ Wave 0 |
| D-07 | `compute_indicators(df)` returns new DataFrame, input unchanged | unit | `pytest tests/test_signal_engine.py::TestIndicators::test_compute_indicators_non_mutating -x` | ❌ Wave 0 |
| D-14 | SHA256 snapshot of 8 indicator series matches on 400-bar fixture | unit | `pytest tests/test_signal_engine.py::TestDeterminism::test_snapshot_hash_stable -x` | ❌ Wave 0 |
| arch | `signal_engine.py` contains no `import datetime` / `os` / `requests` | unit | `pytest tests/test_signal_engine.py::TestDeterminism::test_no_io_imports -x` | ❌ Wave 0 |
| arch | `signal_engine.py` does not import `state_manager` / `notifier` / `dashboard` | unit | `pytest tests/test_signal_engine.py::TestDeterminism::test_no_cross_hex_imports -x` | ❌ Wave 0 |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky* — populated by executor during Wave 1+.

---

## Wave 0 Requirements

- [ ] `pyproject.toml` — pytest ini, ruff config (2-space indent, single quotes), `requires-python = ">=3.11"`
- [ ] `requirements.txt` — pinned pandas 2.3.x, numpy 2.0.x, pytest 8.x, yfinance 1.2.x
- [ ] `.python-version` — pins Python 3.11
- [ ] Clean venv: `python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt`
- [ ] `tests/__init__.py`, `tests/conftest.py` — empty but present
- [ ] `tests/oracle/__init__.py`, `tests/oracle/wilder.py`, `tests/oracle/mom_rvol.py` — pure-loop oracle
- [ ] `tests/oracle/README.md` — oracle contract, golden format, regeneration instructions
- [ ] `tests/fixtures/axjo_400bar.csv` + `tests/fixtures/axjo_400bar.README.md` — provenance
- [ ] `tests/fixtures/audusd_400bar.csv` + `tests/fixtures/audusd_400bar.README.md` — second instrument
- [ ] `tests/fixtures/scenario_*.csv` × 9 — synthetic fixtures for vote truth table (D-16)
- [ ] `tests/oracle/goldens/axjo_400bar_indicators.csv` — oracle-generated goldens
- [ ] `tests/oracle/goldens/audusd_400bar_indicators.csv` — goldens for second instrument
- [ ] `tests/oracle/goldens/scenario_*.json` — per-scenario expected signal + last-row indicators
- [ ] `tests/determinism/snapshot.json` — SHA256 per series (D-14), both instruments
- [ ] `tests/regenerate_goldens.py` — offline script, never in CI (D-04)
- [ ] CLAUDE.md amendment: update stack pins to Python 3.11+, numpy 2.0+, pandas 2.3+

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Canonical 400-bar fixture has realistic OHLCV values that exercise trending + ranging + flat regimes | D-01 | Human judgement: a pulled ^AXJO snapshot should visually show real market behavior for oracle sanity. | Open `axjo_400bar.csv` in a spreadsheet; eyeball Close column for at least one trending-up run, one trending-down run, one sideways period. |
| Scenario fixtures produce the named vote outcomes when manually reasoned through | D-16 | Human sanity check that a synthetic 30-bar series labeled `scenario_adx_above_25_long_3_votes` actually exercises the 3-vote branch. | Oracle regeneration script prints last-row indicators + computed signal for each scenario fixture; human confirms the label matches. |

---

## What Is NOT Validated At This Layer

Deferred to later phases (see `01-RESEARCH.md` §Validation Architecture §What is NOT validated):

- Data fetching — yfinance retry, hard-fail on short frames → Phase 4
- Position sizing using the indicators → Phase 2
- State persistence of signals → Phase 3
- Orchestration / CLI / scheduling → Phase 4, Phase 7
- Email rendering / dashboard → Phase 5, Phase 6
- Cross-instrument iteration (Phase 1 signals one instrument at a time; callers iterate) → Phase 4
- Live determinism across numpy/pandas upgrades (SHA256 snapshot flags drift but doesn't auto-repair — regeneration is a deliberate task)

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending (populated after plan-checker passes)
