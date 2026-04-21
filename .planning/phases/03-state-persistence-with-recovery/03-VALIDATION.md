---
phase: 3
slug: state-persistence-with-recovery
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-04-21
plans_created: 2026-04-21
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.3.3 |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`, testpaths=["tests"]) |
| **Quick run command** | `pyenv exec python3 -m pytest tests/test_state_manager.py -x -q` |
| **Full suite command** | `pyenv exec python3 -m pytest tests/ -q` |
| **Estimated runtime** | ~3 seconds (quick) / ~8 seconds (full) |

---

## Sampling Rate

- **After every task commit:** Run `pyenv exec python3 -m pytest tests/test_state_manager.py -x -q`
- **After every plan wave:** Run `pyenv exec python3 -m pytest tests/ -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 8 seconds

---

## Per-Task Verification Map

> Per-plan task → REQ-ID(s) → automated command. Each task has at least one automated check; tasks 03-01-* establish files Wave 1+ depends on.

| Task ID | Plan | Wave | Requirement(s) | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|----------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 0 | STATE-07, STATE-04 | T-03-02 | constants are read-only Python module attrs | infra | `pyenv exec python3 -c "from system_params import INITIAL_ACCOUNT, MAX_WARNINGS, STATE_SCHEMA_VERSION, STATE_FILE"` | system_params.py (modified) | ⬜ pending |
| 03-01-02 | 01 | 0 | STATE-01 | T-03-04 | NotImplementedError stubs prevent accidental import-time I/O | infra | `pyenv exec python3 -c "from state_manager import load_state, save_state, record_trade, update_equity_history, reset_state, append_warning, MIGRATIONS"` | state_manager.py | ⬜ pending |
| 03-01-03 | 01 | 0 | (Wave 0 stubs) | — | test scaffold collects without error | infra | `pyenv exec python3 -m pytest tests/test_state_manager.py --collect-only -q` | tests/test_state_manager.py | ⬜ pending |
| 03-01-04 | 01 | 0 | (hex-guard) | T-03-01 | AST blocklist enforces I/O-hex allowed/forbidden imports | arch | `pyenv exec python3 -m pytest 'tests/test_signal_engine.py::TestDeterminism::test_state_manager_no_forbidden_imports' -x -q` | tests/test_signal_engine.py (extended) | ⬜ pending |
| 03-02-01 | 02 | 1 | STATE-02, STATE-04 | T-03-05, T-03-06, T-03-07, T-03-08, T-03-09 | atomic write + tempfile cleanup + NaN guard + OSError re-raise + schema migration | unit | `pyenv exec python3 -m pytest tests/test_state_manager.py::TestLoadSave tests/test_state_manager.py::TestAtomicity tests/test_state_manager.py::TestSchemaVersion -x -q` | state_manager.py (Wave 1) | ⬜ pending |
| 03-02-02 | 02 | 1 | STATE-01, STATE-02, STATE-04 | T-03-05..T-03-09 | 11 tests prove atomic write + round-trip + NaN guard + crash + schema | unit | `pyenv exec python3 -m pytest tests/test_state_manager.py -x -q` (expects 11 passed) | tests/test_state_manager.py (Wave 1) | ⬜ pending |
| 03-03-01 | 03 | 2 | STATE-01, STATE-03, STATE-07 | T-03-10, T-03-11, T-03-13, T-03-14, T-03-15 | corruption recovery + Pitfall 4 narrow catch + AWST date + FIFO bound | unit | `pyenv exec python3 -m pytest tests/test_state_manager.py::TestReset tests/test_state_manager.py::TestCorruptionRecovery tests/test_state_manager.py::TestWarnings -x -q` | state_manager.py (Wave 2) | ⬜ pending |
| 03-03-02 | 03 | 2 | STATE-01, STATE-03, STATE-07 | T-03-10..T-03-15 | 10 tests prove reset shape + corruption flow + warning shape/bound | unit | `pyenv exec python3 -m pytest tests/test_state_manager.py -x -q` (expects 21 passed) | tests/test_state_manager.py (Wave 2) | ⬜ pending |
| 03-04-01 | 04 | 3 | STATE-05, STATE-06 | T-03-16, T-03-17, T-03-18, T-03-19, T-03-20 | D-15 validation + D-14 cost split + D-13 atomic close + Phase 4 boundary documented | unit | `pyenv exec python3 -m pytest tests/test_state_manager.py::TestRecordTrade tests/test_state_manager.py::TestEquityHistory -x -q` | state_manager.py (Wave 3) | ⬜ pending |
| 03-04-02 | 04 | 3 | STATE-05, STATE-06 | T-03-19 (CRITICAL) | named test test_record_trade_phase_4_boundary_gross_pnl_not_realised_pnl proves both CORRECT (account=100_994.0) and BUG (account=100_988.0) paths | unit | `pyenv exec python3 -m pytest 'tests/test_state_manager.py::TestRecordTrade::test_record_trade_phase_4_boundary_gross_pnl_not_realised_pnl' -x -v` | tests/test_state_manager.py (Wave 3) | ⬜ pending |
| 03-04-PHASE-GATE | — | — | STATE-01..07 (all) | — | Phase 3 ships: 32 tests, 0 NotImplementedError, hexagonal-lite intact, full suite green | gate | `pyenv exec python3 -m pytest tests/ -q && ! grep -F 'NotImplementedError' state_manager.py` | all Phase 3 artifacts | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

**Source mapping (from RESEARCH.md §Validation Architecture):**

| Req ID | Behavior | Test Class | Test Method | Plan |
|--------|----------|------------|-------------|------|
| STATE-01 | reset_state has 8 top-level keys | TestReset | test_reset_state_has_all_8_top_level_keys | 03 |
| STATE-01 | load_state on missing file returns 8-key shape | TestLoadSave | test_load_state_missing_file_returns_fresh_shape | 02 |
| STATE-02 | Atomic write — crash on os.replace leaves original intact | TestAtomicity | test_crash_on_os_replace_leaves_original_intact | 02 |
| STATE-02 | Atomic write — tempfile cleaned up on failure | TestAtomicity | test_tempfile_cleaned_up_on_failure | 02 |
| STATE-02 | save → load round-trip preserves state | TestLoadSave | test_save_load_round_trip_preserves_state | 02 |
| STATE-03 | Corrupt state.json → backup + reset + warning | TestCorruptionRecovery | test_corrupt_file_triggers_backup_and_reset | 03 |
| STATE-03 | Pitfall 4: ValueError that is NOT JSONDecodeError propagates | TestCorruptionRecovery | test_corruption_recovery_does_not_catch_non_json_value_error | 03 |
| STATE-03 | Recovery warning has AWST date + state_manager source | TestCorruptionRecovery | test_corrupt_state_returns_new_state_with_corruption_warning | 03 |
| STATE-04 | Schema v1 → v1 no-op migration | TestSchemaVersion | test_schema_v1_no_op_migration | 02 |
| STATE-04 | State without schema_version migrates to current | TestSchemaVersion | test_load_state_without_schema_version_key_migrates_to_current | 02 |
| STATE-04 | MIGRATIONS[1] is the identity (no-op) | TestSchemaVersion | test_migrations_dict_has_v1_no_op | 02 |
| STATE-05 | record_trade adjusts account by net_pnl | TestRecordTrade | test_record_trade_adjusts_account_by_net_pnl | 04 |
| STATE-05 | record_trade appends to trade_log with net_pnl | TestRecordTrade | test_record_trade_appends_to_trade_log_with_net_pnl | 04 |
| STATE-05 | record_trade sets positions[instrument] = None | TestRecordTrade | test_record_trade_sets_position_to_none | 04 |
| STATE-05 | record_trade raises on missing/invalid fields | TestRecordTrade | test_record_trade_raises_on_missing_field, test_record_trade_raises_on_invalid_instrument, test_record_trade_raises_on_invalid_direction, test_record_trade_raises_on_zero_or_negative_contracts | 04 |
| STATE-05 | CRITICAL Phase 4 boundary: gross_pnl raw, NOT realised_pnl | TestRecordTrade | test_record_trade_phase_4_boundary_gross_pnl_not_realised_pnl | 04 |
| STATE-06 | update_equity_history appends {date, equity} | TestEquityHistory | test_update_equity_history_appends_entry | 04 |
| STATE-06 | Multiple appends preserve order | TestEquityHistory | test_update_equity_history_appends_multiple_entries_in_order | 04 |
| STATE-07 | reset_state account == 100_000.0 + canonical defaults | TestReset | test_reset_state_canonical_default_values | 03 |
| STATE-07 | reset_state returns independent dicts | TestReset | test_reset_state_returns_independent_dicts | 03 |
| Hex guard | state_manager.py imports only stdlib + system_params | TestDeterminism (extended) | test_state_manager_no_forbidden_imports | 01 |
| Warnings | append_warning shape (D-09) | TestWarnings | test_append_warning_basic_shape | 03 |
| Warnings | AWST date (A1) | TestWarnings | test_append_warning_date_uses_awst | 03 |
| Warnings | FIFO bound (D-11) | TestWarnings | test_append_warning_fifo_trims_oldest_entries | 03 |
| Warnings | Returns mutated state | TestWarnings | test_append_warning_returns_mutated_state | 03 |

---

## Wave 0 Requirements (Plan 01)

- [ ] `tests/test_state_manager.py` — Phase 3 test module skeleton (TestLoadSave, TestAtomicity, TestCorruptionRecovery, TestRecordTrade, TestEquityHistory, TestReset, TestWarnings, TestSchemaVersion classes — `pass` bodies; `_make_trade` helper populated; imports + module-level path constants populated)
- [ ] `state_manager.py` — public API stubs (load_state, save_state, record_trade, update_equity_history, reset_state, append_warning) + private helpers (_atomic_write, _migrate, _backup_corrupt, _validate_trade) — all NotImplementedError; module-level constants (_AWST, _REQUIRED_TRADE_FIELDS, MIGRATIONS) fully populated; module docstring documents D-01..D-16 + CRITICAL Phase 4 boundary
- [ ] `system_params.py` — add `INITIAL_ACCOUNT = 100_000.0`, `MAX_WARNINGS = 100`, `STATE_SCHEMA_VERSION = 1`, `STATE_FILE = 'state.json'` as a Phase 3 constants block
- [ ] Extend `tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent` to cover `state_manager.py` with appropriate allow-list (allows json/os/tempfile/datetime/pathlib/typing/zoneinfo/sys + system_params; blocks signal_engine, sizing_engine, notifier, dashboard, main, requests, schedule, numpy, pandas, pytz)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| — | — | — | All Phase 3 behaviors have automated verification via stdlib mocking + tmp_path fixture isolation |

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (10 tasks across 4 plans)
- [x] Sampling continuity: every Wave's first task is followed immediately by a test-populating task that runs the full Phase 3 suite — no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (test_state_manager.py, state_manager.py, system_params constants, AST blocklist extension)
- [x] No watch-mode flags
- [x] Feedback latency < 8s (full suite ~3-8s)
- [x] `nyquist_compliant: true` set in frontmatter (planner sets after Per-Task Verification Map is filled)

**Approval:** planner-approved (planning complete; awaiting execution)
