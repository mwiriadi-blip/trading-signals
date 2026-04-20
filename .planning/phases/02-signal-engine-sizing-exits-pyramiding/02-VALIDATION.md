---
phase: 2
slug: signal-engine-sizing-exits-pyramiding
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-21
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.3.3 |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`, testpaths=["tests"]) |
| **Quick run command** | `.venv/bin/python -m pytest tests/test_sizing_engine.py -x -q` |
| **Full suite command** | `.venv/bin/python -m pytest tests/ -q` |
| **Estimated runtime** | ~5 seconds (quick) / ~15 seconds (full) |

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/python -m pytest tests/test_sizing_engine.py -x -q`
- **After every plan wave:** Run `.venv/bin/python -m pytest tests/ -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

> Filled in by planner. Each plan task gets a row mapping to its REQ-ID and the automated command that proves it.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 0 | (Wave 0 stub) | — | N/A (pure math) | infra | `test -f tests/test_sizing_engine.py` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

**Source mapping (from RESEARCH.md §Validation Architecture):**

| Req ID | Behavior | Test Type | Automated Command |
|--------|----------|-----------|-------------------|
| SIZE-01 | risk_pct=1.0% LONG, 0.5% SHORT | unit | `pytest tests/test_sizing_engine.py::TestSizing::test_risk_pct_long_is_1pct -x` |
| SIZE-02 | trail_mult=3.0 LONG, 2.0 SHORT | unit | `pytest tests/test_sizing_engine.py::TestSizing::test_trail_mult_by_direction -x` |
| SIZE-03 | vol_scale clip + NaN guard | unit | `pytest tests/test_sizing_engine.py::TestSizing::test_vol_scale_nan_guard -x` |
| SIZE-04 | n_contracts formula, no floor | unit | `pytest tests/test_sizing_engine.py::TestSizing::test_calc_position_size_formula -x` |
| SIZE-05 | n_contracts=0 → warning | unit | `pytest tests/test_sizing_engine.py::TestSizing::test_zero_contracts_warning -x` |
| SIZE-06 | SPI mini multiplier $5/pt; AUDUSD $10k notional | unit | `pytest tests/test_sizing_engine.py::TestSizing::test_contract_specs -x` |
| EXIT-01 | LONG→FLAT closes LONG | scenario | `pytest tests/test_sizing_engine.py::TestTransitions::test_transition_long_to_flat -x` |
| EXIT-02 | SHORT→FLAT closes SHORT | scenario | `pytest tests/test_sizing_engine.py::TestTransitions::test_transition_short_to_flat -x` |
| EXIT-03 | LONG→SHORT two-phase | scenario | `pytest tests/test_sizing_engine.py::TestTransitions::test_transition_long_to_short -x` |
| EXIT-04 | SHORT→LONG two-phase | scenario | `pytest tests/test_sizing_engine.py::TestTransitions::test_transition_short_to_long -x` |
| EXIT-05 | ADX<20 closes position | scenario | `pytest tests/test_sizing_engine.py::TestEdgeCases::test_adx_drop_below_20_while_in_trade -x` |
| EXIT-06 | LONG trail stop, peak via HIGH | unit | `pytest tests/test_sizing_engine.py::TestExits::test_long_trailing_stop_peak_update -x` |
| EXIT-07 | SHORT trail stop, trough via LOW | unit | `pytest tests/test_sizing_engine.py::TestExits::test_short_trailing_stop_trough_update -x` |
| EXIT-08 | LONG stop hit LOW<=stop | unit | `pytest tests/test_sizing_engine.py::TestExits::test_long_stop_hit_intraday_low -x` |
| EXIT-09 | SHORT stop hit HIGH>=stop | unit | `pytest tests/test_sizing_engine.py::TestExits::test_short_stop_hit_intraday_high -x` |
| PYRA-01 | pyramid_level persists in Position TypedDict | unit | `pytest tests/test_sizing_engine.py::TestPyramid::test_position_carries_pyramid_level -x` |
| PYRA-02 | Level 0→1 at 1×ATR | unit | `pytest tests/test_sizing_engine.py::TestPyramid::test_pyramid_level_0_to_1 -x` |
| PYRA-03 | Level 1→2 at 2×ATR | unit | `pytest tests/test_sizing_engine.py::TestPyramid::test_pyramid_level_1_to_2 -x` |
| PYRA-04 | Cap at level 2 | unit | `pytest tests/test_sizing_engine.py::TestPyramid::test_pyramid_capped_at_level_2 -x` |
| PYRA-05 | Max 1 step per call (gap fixture) | scenario | `pytest tests/test_sizing_engine.py::TestEdgeCases::test_pyramid_gap_crosses_both_levels_caps_at_1 -x` |

---

## Wave 0 Requirements

- [ ] `tests/test_sizing_engine.py` — Phase 2 test module (TestSizing, TestExits, TestTransitions, TestPyramid, TestEdgeCases, TestDeterminism classes)
- [ ] `tests/fixtures/phase2/` — directory holding 15 JSON fixture files (9 transitions + 6 edge cases per D-14)
- [ ] `tests/regenerate_phase2_fixtures.py` — offline regenerator mirroring `tests/regenerate_scenarios.py` shape
- [ ] `tests/determinism/phase2_snapshot.json` — SHA256 oracle hashes per D-06
- [ ] `system_params.py` — constants + `Position` TypedDict (per D-01, D-08, D-11)
- [ ] `sizing_engine.py` — public API stubs (functions + dataclasses per D-07, D-09)
- [ ] `SPEC.md` §6 amendment — SPI mini $5/pt $6 RT (per D-11)
- [ ] `CLAUDE.md` §Stack amendment — sizing_engine.py module location + SPI mini contract specs (per D-07, D-11)
- [ ] Extend `tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent` to cover `sizing_engine.py` and `system_params.py`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| — | — | — | All Phase 2 behaviors have automated verification via fixture-driven scenario tests |

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (test_sizing_engine.py, fixtures dir, regenerator, snapshot, system_params, sizing_engine, SPEC/CLAUDE amendments)
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter (planner sets after Per-Task Verification Map is filled)

**Approval:** pending
