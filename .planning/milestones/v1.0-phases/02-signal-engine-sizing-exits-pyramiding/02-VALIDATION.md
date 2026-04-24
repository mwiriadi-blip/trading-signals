---
phase: 2
slug: signal-engine-sizing-exits-pyramiding
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-04-21
updated: 2026-04-21 (reviews-revision pass)
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

> Filled in by planner. Each plan task gets a row mapping to its REQ-IDs and the automated command that proves it.

| Task ID  | Plan | Wave | Requirement(s)                                     | Threat Ref | Secure Behavior            | Test Type | Automated Command | File Exists | Status |
|----------|------|------|----------------------------------------------------|------------|----------------------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01   | 0    | (D-11, D-07, D-17 doc amendments)                  | T-02-01    | N/A — pure doc edit        | infra     | `grep -F 'SPI 200 mini' SPEC.md && grep -F '$5/point' CLAUDE.md && grep -F 'D-17' SPEC.md` | ❌ W0 | ⬜ pending |
| 02-01-02 | 01   | 0    | (scaffolding; B-3 — enables-SIZE/EXIT/PYRA via tags only, no requirements claimed in frontmatter) | T-02-01    | AST-blocked stdlib-only; D-17 stub signatures present | infra     | `pytest tests/test_signal_engine.py -q` no failures + import smoke + `inspect.signature(compute_unrealised_pnl)` shows cost_aud_open | ❌ W0 | ⬜ pending |
| 02-01-03 | 01   | 0    | (architectural — extends Phase 1 AST guard; D-17 surface contract) | T-02-01    | numpy/pandas blocked for Phase 2 hex; D-17 sig spot-check | unit | `pytest tests/test_signal_engine.py::TestDeterminism -k "phase2_hex_stdlib_only or sizing_engine_has_core_public_surface" -v` | ❌ W0 | ⬜ pending |
| 02-02-01 | 02   | 1    | SIZE-01..06; D-17 (compute_unrealised_pnl signature) | T-02-02    | NaN-guard via math.isfinite; D-17 explicit cost_aud_open | unit     | `pytest tests/test_sizing_engine.py::TestSizing -v` | ❌ W0 | ⬜ pending |
| 02-02-02 | 02   | 1    | SIZE-01..06; D-17                                  | T-02-02    | exact-equality unit asserts; B-2 scope-explicit | unit     | `pytest tests/test_sizing_engine.py::TestSizing -v` no failures, no skips | ❌ W0 | ⬜ pending |
| 02-03-01 | 03   | 2    | EXIT-06..09; PYRA-01..05; D-15 anchor; B-1 NaN     | T-02-03    | Pitfall 3 None-fallback; D-12 stateless; D-15 entry-ATR; B-1 NaN policy | unit | `pytest tests/test_sizing_engine.py -k "Exits or Pyramid" -v` | ❌ W0 | ⬜ pending |
| 02-03-02 | 03   | 2    | EXIT-06..09; PYRA-01..05; B-1 NaN                  | T-02-03    | inclusive boundary; gap-day cap; B-1 NaN tests | unit | `pytest tests/test_sizing_engine.py::TestExits tests/test_sizing_engine.py::TestPyramid -v` no failures, no skips + `pytest -k nan` covers ≥6 NaN tests | ❌ W0 | ⬜ pending |
| 02-04-01 | 04   | 3    | (fixture infrastructure — covers all SIZE/EXIT/PYRA via scenarios; D-15 in helpers; B-1 NaN; B-4 keep-with-justification) | T-02-04a/b | allow_nan=False; sizing_engine-free recipes; D-15 anchored helpers | infra | `python tests/regenerate_phase2_fixtures.py && ls tests/fixtures/phase2/*.json | wc -l = 15` | ❌ W0 | ⬜ pending |
| 02-04-02 | 04   | 3    | EXIT-01..09; PYRA-05; SIZE-05                      | T-02-04a   | per-fixture exact assertions | scenario | `pytest tests/test_sizing_engine.py::TestTransitions tests/test_sizing_engine.py::TestEdgeCases -v` no failures, no skips | ❌ W0 | ⬜ pending |
| 02-05-01 | 05   | 4    | EXIT-01..05 (step composition); PYRA-05; D-16/D-17/D-18/D-19/B-5 | T-02-05b   | RESEARCH A2 forced_exit guard; D-16 peak-on-copy; D-18 pyramid-applied; D-19 input-account; B-5 stop-fill | unit | `pytest tests/test_sizing_engine.py -q + D-16/D-18/B-5 smoke` | ❌ W0 | ⬜ pending |
| 02-05-02 | 05   | 4    | (D-06 fixture goldens populated; D-16/D-18/B-5 reflected in fixtures) | T-02-05a   | SHA256 lock; idempotency proof; pyramid-fixture position_after.n_contracts=3 level=1 (D-18); stop-hit fixtures realised_pnl uses stop level (B-5) | infra | `python tests/regenerate_phase2_fixtures.py` (twice; zero git diff) | ❌ W0 | ⬜ pending |
| 02-05-03 | 05   | 4    | EXIT-01..05; PYRA-05; SIZE-05; D-16/D-18/D-19/B-5 named tests | T-02-05a/b | SHA256 stability + step integration + reviews-revision named tests | scenario+regression | `pytest tests/test_sizing_engine.py::TestStep tests/test_signal_engine.py::TestDeterminism::test_phase2_snapshot_hash_stable -v` + `pytest tests/test_sizing_engine.py::TestStep -k "d16 or d18 or d19 or b5" -v` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

**Source mapping (from RESEARCH.md §Validation Architecture):**

| Req ID  | Behavior                                            | Test Type | Automated Command (final, post-Phase 2) |
|---------|-----------------------------------------------------|-----------|------------------------------------------|
| SIZE-01 | risk_pct=1.0% LONG, 0.5% SHORT                      | unit      | `pytest tests/test_sizing_engine.py::TestSizing::test_risk_pct_long_is_1pct -x` |
| SIZE-01 | risk_pct=0.5% SHORT (mirror)                        | unit      | `pytest tests/test_sizing_engine.py::TestSizing::test_risk_pct_short_is_half_pct -x` |
| SIZE-02 | trail_mult=3.0 LONG, 2.0 SHORT                      | unit      | `pytest tests/test_sizing_engine.py::TestSizing::test_trail_mult_by_direction -x` |
| SIZE-03 | vol_scale clip ceiling (rvol=0.05 → vol_scale=2.0)  | unit      | `pytest tests/test_sizing_engine.py::TestSizing::test_vol_scale_clip_ceiling -x` |
| SIZE-03 | vol_scale clip floor (rvol=0.50 → vol_scale=0.3)    | unit      | `pytest tests/test_sizing_engine.py::TestSizing::test_vol_scale_clip_floor -x` |
| SIZE-03 | vol_scale NaN guard (D-03)                          | unit      | `pytest tests/test_sizing_engine.py::TestSizing::test_vol_scale_nan_guard -x` |
| SIZE-03 | vol_scale zero/tiny rvol guard                      | unit      | `pytest tests/test_sizing_engine.py::TestSizing::test_vol_scale_zero_guard -x` |
| SIZE-04 | n_contracts=int(n_raw); NO max(1) floor             | unit      | `pytest tests/test_sizing_engine.py::TestSizing::test_no_max_one_floor_when_undersized -x` |
| SIZE-05 | n_contracts==0 → SizingDecision warning             | unit      | `pytest tests/test_sizing_engine.py::TestSizing::test_zero_contracts_warning_format -x` |
| SIZE-05 | size=0 warning surfaces in StepResult.warnings (E2E) | scenario | `pytest tests/test_sizing_engine.py::TestStep::test_step_size_zero_warning_propagates -x` |
| SIZE-05 | n_contracts_zero_skip_warning fixture               | scenario  | `pytest tests/test_sizing_engine.py::TestEdgeCases::test_n_contracts_zero_skip_warning -x` |
| SIZE-06 | SPI mini multiplier $5/pt (D-11)                    | unit      | `pytest tests/test_sizing_engine.py::TestSizing::test_contract_specs_spi_mini -x` |
| SIZE-06 | AUDUSD multiplier $10000 notional                   | unit      | `pytest tests/test_sizing_engine.py::TestSizing::test_contract_specs_audusd -x` |
| EXIT-01 | LONG→FLAT closes LONG (named scenario fixture)      | scenario  | `pytest tests/test_sizing_engine.py::TestTransitions::test_transition_long_to_flat -x` |
| EXIT-01 | LONG→FLAT closes via step() with reason='flat_signal' | scenario | `pytest tests/test_sizing_engine.py::TestStep::test_step_long_to_flat_closes_with_flat_signal_reason -x` |
| EXIT-02 | SHORT→FLAT closes SHORT (named scenario fixture)    | scenario  | `pytest tests/test_sizing_engine.py::TestTransitions::test_transition_short_to_flat -x` |
| EXIT-03 | LONG→SHORT two-phase close+open                     | scenario  | `pytest tests/test_sizing_engine.py::TestTransitions::test_transition_long_to_short -x` |
| EXIT-03 | LONG→SHORT step() integration                       | scenario  | `pytest tests/test_sizing_engine.py::TestStep::test_step_reversal_long_to_short_opens_new_short -x` |
| EXIT-04 | SHORT→LONG two-phase close+open                     | scenario  | `pytest tests/test_sizing_engine.py::TestTransitions::test_transition_short_to_long -x` |
| EXIT-04 | SHORT→LONG step() integration                       | scenario  | `pytest tests/test_sizing_engine.py::TestStep::test_step_reversal_short_to_long_opens_new_long -x` |
| EXIT-05 | ADX<20 closes position regardless of new_signal     | scenario  | `pytest tests/test_sizing_engine.py::TestEdgeCases::test_adx_drop_below_20_while_in_trade -x` |
| EXIT-05 | EXIT-05 step() integration + RESEARCH A2 (no new entry) | scenario | `pytest tests/test_sizing_engine.py::TestStep::test_step_no_entry_on_adx_exit_day -x` |
| EXIT-06 | LONG trail stop = peak - 3*ATR; peak via HIGH       | unit      | `pytest tests/test_sizing_engine.py::TestExits::test_long_trailing_stop_peak_update -x` |
| EXIT-06 | LONG peak=None falls back to entry_price (Pitfall 3) | unit     | `pytest tests/test_sizing_engine.py::TestExits::test_long_trailing_stop_peak_none_falls_back_to_entry -x` |
| EXIT-07 | SHORT trail stop = trough + 2*ATR; trough via LOW   | unit      | `pytest tests/test_sizing_engine.py::TestExits::test_short_trailing_stop_trough_update -x` |
| EXIT-07 | SHORT trough=None fallback                          | unit      | `pytest tests/test_sizing_engine.py::TestExits::test_short_trailing_stop_trough_none_falls_back_to_entry -x` |
| EXIT-08 | LONG stop hit if low <= stop (boundary inclusive)   | unit      | `pytest tests/test_sizing_engine.py::TestExits::test_long_stop_hit_intraday_low_at_boundary -x` |
| EXIT-08 | LONG stop hit fixture                               | scenario  | `pytest tests/test_sizing_engine.py::TestEdgeCases::test_long_trail_stop_hit_intraday_low -x` |
| EXIT-08 | LONG gap-through-stop (Pitfall 2: detection only)   | scenario  | `pytest tests/test_sizing_engine.py::TestEdgeCases::test_long_gap_through_stop_detection_only -x` |
| EXIT-08 | LONG stop-hit step()+RESEARCH A2 no new entry       | scenario  | `pytest tests/test_sizing_engine.py::TestStep::test_step_no_entry_on_long_stop_hit -x` |
| EXIT-09 | SHORT stop hit if high >= stop (boundary inclusive) | unit      | `pytest tests/test_sizing_engine.py::TestExits::test_short_stop_hit_intraday_high_at_boundary -x` |
| EXIT-09 | SHORT stop hit fixture                              | scenario  | `pytest tests/test_sizing_engine.py::TestEdgeCases::test_short_trail_stop_hit_intraday_high -x` |
| EXIT-09 | SHORT stop-hit step()+RESEARCH A2 no new entry      | scenario  | `pytest tests/test_sizing_engine.py::TestStep::test_step_no_entry_on_short_stop_hit -x` |
| PYRA-01 | pyramid_level persists in Position TypedDict        | unit      | `pytest tests/test_sizing_engine.py::TestPyramid::test_position_carries_pyramid_level -x` |
| PYRA-02 | Level 0→1 at 1*ATR (LONG)                           | unit      | `pytest tests/test_sizing_engine.py::TestPyramid::test_pyramid_level_0_to_1_long -x` |
| PYRA-02 | Level 0→1 at 1*ATR (SHORT mirror)                   | unit      | `pytest tests/test_sizing_engine.py::TestPyramid::test_pyramid_level_0_to_1_short -x` |
| PYRA-03 | Level 1→2 at 2*ATR (LONG)                           | unit      | `pytest tests/test_sizing_engine.py::TestPyramid::test_pyramid_level_1_to_2_long -x` |
| PYRA-03 | Level 1→2 at 2*ATR (SHORT mirror)                   | unit      | `pytest tests/test_sizing_engine.py::TestPyramid::test_pyramid_level_1_to_2_short -x` |
| PYRA-04 | Cap at level 2 (3 total contracts)                  | unit      | `pytest tests/test_sizing_engine.py::TestPyramid::test_pyramid_capped_at_level_2 -x` |
| PYRA-05 | Stateless single-step (LONG gap day)                | unit      | `pytest tests/test_sizing_engine.py::TestPyramid::test_pyramid_gap_day_caps_at_one_add_long -x` |
| PYRA-05 | Stateless single-step (SHORT gap day)               | unit      | `pytest tests/test_sizing_engine.py::TestPyramid::test_pyramid_gap_day_caps_at_one_add_short -x` |
| PYRA-05 | D-12 fixture (gap crosses both levels caps at 1)    | scenario  | `pytest tests/test_sizing_engine.py::TestEdgeCases::test_pyramid_gap_crosses_both_levels_caps_at_1 -x` |
| (D-06)  | SHA256 fixture goldens stable                       | regression | `pytest tests/test_signal_engine.py::TestDeterminism::test_phase2_snapshot_hash_stable -v` (15 parametrized) |
| (arch)  | sizing_engine.py + system_params.py stdlib-only     | regression | `pytest tests/test_signal_engine.py::TestDeterminism::test_phase2_hex_stdlib_only -v` |
| (arch)  | sizing_engine public surface contract + D-17 sigs   | regression | `pytest tests/test_signal_engine.py::TestDeterminism::test_sizing_engine_has_core_public_surface -v` |
| (D-15)  | get_trailing_stop ignores atr arg, uses position[atr_entry] | unit | `pytest tests/test_sizing_engine.py::TestExits::test_long_trailing_stop_d15_anchor_explicit -x` |
| (D-16)  | step() updates peak/trough on shallow copy, never mutates input | unit | `pytest tests/test_sizing_engine.py::TestStep::test_step_d16_updates_peak_on_copy_not_input -x` |
| (D-17)  | compute_unrealised_pnl signature has cost_aud_open  | unit | `pytest tests/test_sizing_engine.py::TestSizing::test_unrealised_pnl_signature_has_cost_aud_open -x` |
| (D-18)  | step() applies pyramid add to position_after        | unit | `pytest tests/test_sizing_engine.py::TestStep::test_step_d18_pyramid_add_applied_to_position_after -x` |
| (D-19)  | reversal sizing uses input account (no internal account adjustment) | unit | `pytest tests/test_sizing_engine.py::TestStep::test_step_d19_reversal_uses_input_account -x` |
| (B-1)   | NaN policy: get_trailing_stop nan atr -> nan        | unit | `pytest tests/test_sizing_engine.py::TestExits::test_get_trailing_stop_nan_atr_returns_nan -x` |
| (B-1)   | NaN policy: check_stop_hit nan high/low -> False    | unit | `pytest tests/test_sizing_engine.py::TestExits -k "nan" -v` |
| (B-1)   | NaN policy: check_pyramid nan -> no add             | unit | `pytest tests/test_sizing_engine.py::TestPyramid -k "nan" -v` |
| (B-5)   | stop-hit close uses stop level as exit_price (LONG) | unit | `pytest tests/test_sizing_engine.py::TestStep::test_step_b5_long_stop_hit_uses_stop_level_as_exit_price -x` |
| (B-5)   | stop-hit close uses stop level as exit_price (SHORT)| unit | `pytest tests/test_sizing_engine.py::TestStep::test_step_b5_short_stop_hit_uses_stop_level_as_exit_price -x` |
| (B-5)   | non-stop closes still use bar.close                 | unit | `pytest tests/test_sizing_engine.py::TestStep::test_step_b5_flat_signal_close_still_uses_bar_close -x` |

---

## Wave 0 Requirements

- [ ] `tests/test_sizing_engine.py` — Phase 2 test module (TestSizing, TestExits, TestPyramid, TestTransitions, TestEdgeCases, TestStep classes)
- [ ] `tests/fixtures/phase2/` — directory holding 15 JSON fixture files (9 transitions + 6 edge cases per D-14)
- [ ] `tests/regenerate_phase2_fixtures.py` — offline regenerator mirroring `tests/regenerate_scenarios.py` shape
- [ ] `tests/determinism/phase2_snapshot.json` — SHA256 oracle hashes per D-06 (populated by plan 02-05)
- [ ] `system_params.py` — constants + `Position` TypedDict (per D-01, D-08, D-11)
- [ ] `sizing_engine.py` — public API stubs (functions + dataclasses per D-07, D-09)
- [ ] `SPEC.md` §6 amendment — SPI mini $5/pt $6 RT (per D-11)
- [ ] `SPEC.md` §signal_engine.py — module-split note (per D-07)
- [ ] `CLAUDE.md` §Stack amendment — SPI mini contract specs (per D-11)
- [ ] `CLAUDE.md` §Architecture amendment — sizing_engine.py mention (per D-07)
- [ ] Extend `tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent` to cover `sizing_engine.py` and `system_params.py` via the new `test_phase2_hex_stdlib_only` parametrized test (numpy/pandas blocked for Phase 2 hex)
- [ ] Add `test_sizing_engine_has_core_public_surface` to TestDeterminism (Position TypedDict keys + D-11 contract specs spot-check)
- [ ] Extend `test_no_four_space_indent` files-checked list to include sizing_engine.py + system_params.py + tests/test_sizing_engine.py

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| — | — | — | All Phase 2 behaviors have automated verification via fixture-driven scenario tests |

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (test_sizing_engine.py, fixtures dir, regenerator, snapshot, system_params, sizing_engine, SPEC/CLAUDE amendments)
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter (planner sets after Per-Task Verification Map is filled)

**Approval:** approved (planner)
