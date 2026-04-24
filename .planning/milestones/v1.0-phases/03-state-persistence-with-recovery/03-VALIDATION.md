---
phase: 3
slug: state-persistence-with-recovery
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-04-21
plans_created: 2026-04-21
updated: 2026-04-21
revision_pass: 2026-04-21
revision_source: 03-REVIEWS.md (Codex MEDIUM · Gemini LOW; D-17..D-20 + B-1..B-5)
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> **Refreshed 2026-04-21:** Per-Task Verification Map now reflects the
> D-17..D-20 + B-1..B-5 amendments from the cross-AI review revision pass
> (see 03-CONTEXT.md and 03-REVIEWS.md).

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
> **2026-04-21 reviews-revision pass:** new threat refs T-03-08b (D-17 ordering), T-03-11b (D-18 missing-keys raise), T-03-12b (B-1 path-derived backup name), T-03-18b (D-19 extended validation), T-03-19b (D-20 no-mutation), T-03-20b (B-4 equity boundary).

| Task ID | Plan | Wave | Requirement(s) | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|----------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 0 | STATE-07, STATE-04 | T-03-02 | constants are read-only Python module attrs | infra | `pyenv exec python3 -c "from system_params import INITIAL_ACCOUNT, MAX_WARNINGS, STATE_SCHEMA_VERSION, STATE_FILE"` | system_params.py (modified) | ⬜ pending |
| 03-01-02 | 01 | 0 | STATE-01 | T-03-04 | NotImplementedError stubs prevent accidental import-time I/O; D-18 `_validate_loaded_state` stub + `_REQUIRED_STATE_KEYS` constant present | infra | `pyenv exec python3 -c "from state_manager import load_state, save_state, record_trade, update_equity_history, reset_state, append_warning, MIGRATIONS; import state_manager; assert hasattr(state_manager, '_validate_loaded_state'); assert hasattr(state_manager, '_REQUIRED_STATE_KEYS')"` | state_manager.py | ⬜ pending |
| 03-01-03 | 01 | 0 | (Wave 0 stubs) | — | test scaffold collects without error | infra | `pyenv exec python3 -m pytest tests/test_state_manager.py --collect-only -q` | tests/test_state_manager.py | ⬜ pending |
| 03-01-04 | 01 | 0 | (hex-guard) | T-03-01 | AST blocklist enforces I/O-hex allowed/forbidden imports (math intentionally not in forbidden — stdlib allowed for D-19/B-4) | arch | `pyenv exec python3 -m pytest 'tests/test_signal_engine.py::TestDeterminism::test_state_manager_no_forbidden_imports' -x -q` | tests/test_signal_engine.py (extended) | ⬜ pending |
| 03-02-01 | 02 | 1 | STATE-02, STATE-04 | T-03-05, T-03-06, T-03-07, T-03-08, T-03-08b, T-03-09 | atomic write (D-17 post-replace fsync ordering) + tempfile cleanup + NaN guard + OSError re-raise + schema migration; load_state(missing) docstring documents B-3 no-persist contract | unit | `pyenv exec python3 -m pytest tests/test_state_manager.py::TestLoadSave tests/test_state_manager.py::TestAtomicity tests/test_state_manager.py::TestSchemaVersion -x -q` | state_manager.py (Wave 1) | ⬜ pending |
| 03-02-02 | 02 | 1 | STATE-01, STATE-02, STATE-04 | T-03-05..T-03-09 + T-03-08b | 12 tests prove atomic write + round-trip + NaN guard + crash + schema + **D-17 ordering proof** + **B-3 no-persist contract** | unit | `pyenv exec python3 -m pytest tests/test_state_manager.py -x -q` (expects 12 passed) | tests/test_state_manager.py (Wave 1) | ⬜ pending |
| 03-03-01 | 03 | 2 | STATE-01, STATE-03, STATE-07 | T-03-10, T-03-11, T-03-11b, T-03-12, T-03-12b, T-03-13, T-03-14, T-03-15 | corruption recovery + Pitfall 4 narrow catch + AWST date + FIFO bound + **D-18 _validate_loaded_state** + **B-1 path-derived backup name** + **B-2 microsecond timestamp** + **B-5 MAX_WARNINGS rationale** | unit | `pyenv exec python3 -m pytest tests/test_state_manager.py::TestReset tests/test_state_manager.py::TestCorruptionRecovery tests/test_state_manager.py::TestWarnings -x -q` | state_manager.py (Wave 2) | ⬜ pending |
| 03-03-02 | 03 | 2 | STATE-01, STATE-03, STATE-07 | T-03-10..T-03-15 + T-03-11b + T-03-12b | 12 tests prove reset shape + corruption flow (incl. **B-1 + B-2** hardening) + warning shape/bound + **D-18 missing-keys raises without spurious backup** | unit | `pyenv exec python3 -m pytest tests/test_state_manager.py -x -q` (expects 24 passed) | tests/test_state_manager.py (Wave 2) | ⬜ pending |
| 03-04-01 | 04 | 3 | STATE-05, STATE-06 | T-03-16, T-03-17, T-03-18, T-03-18b, T-03-19, T-03-19b, T-03-20, T-03-20b | D-15 + **D-19 extended validation** + D-14 cost split + **D-20 non-mutating trade_log append** + D-13 atomic close + Phase 4 boundary documented + **B-4 equity boundary validation** | unit | `pyenv exec python3 -m pytest tests/test_state_manager.py::TestRecordTrade tests/test_state_manager.py::TestEquityHistory -x -q` | state_manager.py (Wave 3) | ⬜ pending |
| 03-04-02 | 04 | 3 | STATE-05, STATE-06 | T-03-19 (CRITICAL) + T-03-18b + T-03-19b + T-03-20b | named test test_record_trade_phase_4_boundary_gross_pnl_not_realised_pnl proves both CORRECT (account=100_994.0) and BUG (account=100_988.0) paths; **6 D-19 type-check tests** prove field-by-field validation; **D-20 no-mutation test** proves caller's dict unchanged; **3 B-4 tests** prove update_equity_history boundary validation | unit | `pyenv exec python3 -m pytest 'tests/test_state_manager.py::TestRecordTrade::test_record_trade_phase_4_boundary_gross_pnl_not_realised_pnl' -x -v` | tests/test_state_manager.py (Wave 3) | ⬜ pending |
| 03-04-PHASE-GATE | — | — | STATE-01..07 (all) | — | Phase 3 ships: ~45 tests, 0 NotImplementedError, hexagonal-lite intact, full suite green | gate | `pyenv exec python3 -m pytest tests/ -q && ! grep -F 'NotImplementedError' state_manager.py` | all Phase 3 artifacts | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

**Source mapping (refreshed 2026-04-21 per D-17..D-20 + B-1..B-5):**

| Req ID / Decision | Behavior | Test Class | Test Method | Plan |
|-------------------|----------|------------|-------------|------|
| STATE-01 | reset_state has 8 top-level keys | TestReset | test_reset_state_has_all_8_top_level_keys | 03 |
| STATE-01 | load_state on missing file returns 8-key shape AND does NOT create file (B-3) | TestLoadSave | test_load_state_missing_file_returns_fresh_shape | 02 |
| STATE-01 + D-18 | load_state on valid JSON missing required keys raises ValueError WITHOUT spurious backup | TestCorruptionRecovery | test_load_state_valid_json_missing_keys_raises_value_error | 03 |
| STATE-02 | Atomic write — crash on os.replace leaves original intact | TestAtomicity | test_crash_on_os_replace_leaves_original_intact | 02 |
| STATE-02 | Atomic write — tempfile cleaned up on failure | TestAtomicity | test_tempfile_cleaned_up_on_failure | 02 |
| STATE-02 | Atomic write — clean disk leaves no tempfile | TestAtomicity | test_save_state_on_clean_disk_leaves_no_tempfile | 02 |
| STATE-02 + D-17 | Atomic write — parent-dir fsync called AFTER os.replace (durability ordering) | TestAtomicity | test_atomic_write_fsyncs_parent_dir_after_os_replace | 02 |
| STATE-02 | save → load round-trip preserves state | TestLoadSave | test_save_load_round_trip_preserves_state | 02 |
| STATE-02 | save_state writes readable JSON | TestLoadSave | test_save_state_creates_readable_file | 02 |
| STATE-02 | save_state byte-deterministic (sort_keys + indent) | TestLoadSave | test_save_state_is_deterministic_byte_identical | 02 |
| STATE-02 | save_state raises on NaN | TestLoadSave | test_save_state_raises_on_nan | 02 |
| STATE-03 | Corrupt state.json → backup + reset + warning (B-2 microsecond suffix) | TestCorruptionRecovery | test_corrupt_file_triggers_backup_and_reset | 03 |
| STATE-03 | Pitfall 4: ValueError that is NOT JSONDecodeError propagates | TestCorruptionRecovery | test_corruption_recovery_does_not_catch_non_json_value_error | 03 |
| STATE-03 | Recovery warning has AWST date + state_manager source | TestCorruptionRecovery | test_corrupt_state_returns_new_state_with_corruption_warning | 03 |
| STATE-03 + B-1 | Backup filename derived from path.name (not hardcoded) | TestCorruptionRecovery | test_backup_uses_path_derived_name_not_hardcoded | 03 |
| STATE-04 | Schema v1 → v1 no-op migration | TestSchemaVersion | test_schema_v1_no_op_migration | 02 |
| STATE-04 | State without schema_version migrates to current | TestSchemaVersion | test_load_state_without_schema_version_key_migrates_to_current | 02 |
| STATE-04 | MIGRATIONS[1] is the identity (no-op) | TestSchemaVersion | test_migrations_dict_has_v1_no_op | 02 |
| STATE-05 | record_trade adjusts account by net_pnl | TestRecordTrade | test_record_trade_adjusts_account_by_net_pnl | 04 |
| STATE-05 | record_trade appends to trade_log with net_pnl | TestRecordTrade | test_record_trade_appends_to_trade_log_with_net_pnl | 04 |
| STATE-05 | record_trade sets positions[instrument] = None | TestRecordTrade | test_record_trade_sets_position_to_none | 04 |
| STATE-05 (D-15) | record_trade raises on missing field | TestRecordTrade | test_record_trade_raises_on_missing_field | 04 |
| STATE-05 (D-15) | record_trade raises on invalid instrument | TestRecordTrade | test_record_trade_raises_on_invalid_instrument | 04 |
| STATE-05 (D-15) | record_trade raises on invalid direction | TestRecordTrade | test_record_trade_raises_on_invalid_direction | 04 |
| STATE-05 (D-15) | record_trade raises on zero/negative/non-int n_contracts | TestRecordTrade | test_record_trade_raises_on_zero_or_negative_contracts | 04 |
| STATE-05 + D-19 | record_trade raises on non-string entry_date | TestRecordTrade | test_record_trade_raises_on_non_string_entry_date | 04 |
| STATE-05 + D-19 | record_trade raises on empty-string exit_reason | TestRecordTrade | test_record_trade_raises_on_empty_string_exit_reason | 04 |
| STATE-05 + D-19 | record_trade raises on bool for numeric field (Python isinstance quirk) | TestRecordTrade | test_record_trade_raises_on_bool_for_numeric_field | 04 |
| STATE-05 + D-19 | record_trade raises on NaN gross_pnl | TestRecordTrade | test_record_trade_raises_on_nan_gross_pnl | 04 |
| STATE-05 + D-19 | record_trade raises on inf cost_aud | TestRecordTrade | test_record_trade_raises_on_inf_cost_aud | 04 |
| STATE-05 + D-19 | record_trade raises on string entry_price | TestRecordTrade | test_record_trade_raises_on_string_entry_price | 04 |
| STATE-05 + D-20 | record_trade does NOT mutate caller's trade dict; trade_log entry is a separate copy | TestRecordTrade | test_record_trade_does_not_mutate_caller_trade_dict | 04 |
| STATE-05 (CRITICAL) | Phase 4 boundary: gross_pnl raw, NOT realised_pnl (worked CORRECT vs BUG arithmetic) | TestRecordTrade | test_record_trade_phase_4_boundary_gross_pnl_not_realised_pnl | 04 |
| STATE-06 | update_equity_history appends {date, equity} | TestEquityHistory | test_update_equity_history_appends_entry | 04 |
| STATE-06 | Multiple appends preserve order | TestEquityHistory | test_update_equity_history_appends_multiple_entries_in_order | 04 |
| STATE-06 | Returns mutated state for chaining | TestEquityHistory | test_update_equity_history_returns_mutated_state | 04 |
| STATE-06 + B-4 | update_equity_history raises on non-string date | TestEquityHistory | test_update_equity_history_raises_on_non_string_date | 04 |
| STATE-06 + B-4 | update_equity_history raises on short date string (len != 10) | TestEquityHistory | test_update_equity_history_raises_on_short_date_string | 04 |
| STATE-06 + B-4 | update_equity_history raises on non-finite equity (NaN/inf/bool) | TestEquityHistory | test_update_equity_history_raises_on_non_finite_equity | 04 |
| STATE-07 | reset_state account == 100_000.0 + canonical defaults | TestReset | test_reset_state_canonical_default_values | 03 |
| STATE-07 | reset_state returns independent dicts | TestReset | test_reset_state_returns_independent_dicts | 03 |
| Hex guard | state_manager.py imports only stdlib + system_params (math allowed for D-19/B-4) | TestDeterminism (extended) | test_state_manager_no_forbidden_imports | 01 |
| Warnings | append_warning shape (D-09) | TestWarnings | test_append_warning_basic_shape | 03 |
| Warnings | AWST date (A1) | TestWarnings | test_append_warning_date_uses_awst | 03 |
| Warnings | FIFO bound (D-11; B-5 rationale documented) | TestWarnings | test_append_warning_fifo_trims_oldest_entries | 03 |
| Warnings | Returns mutated state | TestWarnings | test_append_warning_returns_mutated_state | 03 |

**Per-decision new-test attribution (reviews-revision pass):**

| Decision | New tests/ACs | Plan(s) |
|----------|---------------|---------|
| **D-17** (atomic write durability ordering — corrects D-08) | TestAtomicity::test_atomic_write_fsyncs_parent_dir_after_os_replace (mock-call-sequence proof); 02-PLAN AC line-order grep on os.replace vs os.fsync(dir_fd); state_manager.py D-17 docstring reference | 02 |
| **D-18** (post-parse semantic validation; extends D-05) | _validate_loaded_state private helper + _REQUIRED_STATE_KEYS frozenset; TestCorruptionRecovery::test_load_state_valid_json_missing_keys_raises_value_error (raise + no spurious backup); 03-PLAN AC enforces validator runs OUTSIDE JSONDecodeError except block via line-order grep | 01 (stub), 03 (impl + test) |
| **D-19** (record_trade validation extends to all 11 fields; extends D-15) | _validate_trade body extended with string-non-empty + finite-numeric-rejecting-bool loops; 6 representative TestRecordTrade tests (test_record_trade_raises_on_non_string_entry_date, _empty_string_exit_reason, _bool_for_numeric_field, _nan_gross_pnl, _inf_cost_aud, _string_entry_price); import math added | 04 |
| **D-20** (record_trade does not mutate caller's trade dict) | record_trade uses dict(trade, net_pnl=net_pnl) instead of mutation; new TestRecordTrade::test_record_trade_does_not_mutate_caller_trade_dict | 04 |
| **B-1** (_backup_corrupt derives name from path.name) | _backup_corrupt body uses f'{path.name}.corrupt.{ts}'; new TestCorruptionRecovery::test_backup_uses_path_derived_name_not_hardcoded (uses non-canonical custom-state.json path) | 03 |
| **B-2** (microsecond-precision backup timestamp) | _backup_corrupt uses '%Y%m%dT%H%M%S_%fZ'; TestCorruptionRecovery::test_corrupt_file_triggers_backup_and_reset asserts microsecond suffix via glob pattern | 03 |
| **B-3** (load_state missing-file no-persist contract) | load_state docstring documents the contract; TestLoadSave::test_load_state_missing_file_returns_fresh_shape adds `assert not path.exists()` after load_state | 02 |
| **B-4** (update_equity_history boundary validation) | update_equity_history validates date + equity; 3 new TestEquityHistory tests (test_update_equity_history_raises_on_non_string_date, _short_date_string, _non_finite_equity) | 04 |
| **B-5** (MAX_WARNINGS rationale) | append_warning docstring includes rationale comment; no new test (documentation-only) | 03 |

---

## Wave 0 Requirements (Plan 01)

- [ ] `tests/test_state_manager.py` — Phase 3 test module skeleton (TestLoadSave, TestAtomicity, TestCorruptionRecovery, TestRecordTrade, TestEquityHistory, TestReset, TestWarnings, TestSchemaVersion classes — `pass` bodies; `_make_trade` helper populated; imports + module-level path constants populated)
- [ ] `state_manager.py` — public API stubs (load_state, save_state, record_trade, update_equity_history, reset_state, append_warning) + **5 private helpers (_atomic_write, _migrate, _backup_corrupt, _validate_trade, _validate_loaded_state — D-18 added)** — all NotImplementedError; module-level constants (_AWST, _REQUIRED_TRADE_FIELDS, **_REQUIRED_STATE_KEYS — D-18**, MIGRATIONS) fully populated; module docstring documents D-01..D-20 + CRITICAL Phase 4 boundary
- [ ] `system_params.py` — add `INITIAL_ACCOUNT = 100_000.0`, `MAX_WARNINGS = 100`, `STATE_SCHEMA_VERSION = 1`, `STATE_FILE = 'state.json'` as a Phase 3 constants block
- [ ] Extend `tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent` to cover `state_manager.py` with appropriate allow-list (allows json/os/tempfile/datetime/pathlib/typing/zoneinfo/sys/math + system_params; blocks signal_engine, sizing_engine, notifier, dashboard, main, requests, schedule, numpy, pandas, pytz)

**Note:** Wave 0 produces 11 NotImplementedError stubs (5 private helpers + 6 public functions). Wave 1 fills 4 of those (_atomic_write, _migrate, save_state, load_state happy path) AND adds 1 inline NotImplementedError in load_state's corruption-branch placeholder → net 8 stubs after Wave 1. Wave 2 fills 4 (reset_state, append_warning, _backup_corrupt, _validate_loaded_state — D-18) plus replaces load_state's corruption-branch NotImplementedError with the full implementation → net 3 stubs after Wave 2. Wave 3 fills the remaining 3 (_validate_trade, record_trade, update_equity_history) → net 0 stubs. Phase ships.

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
- [x] Wave 0 covers all MISSING references (test_state_manager.py, state_manager.py, system_params constants, AST blocklist extension, **D-18 _validate_loaded_state stub + _REQUIRED_STATE_KEYS constant**)
- [x] No watch-mode flags
- [x] Feedback latency < 8s (full suite ~3-8s)
- [x] `nyquist_compliant: true` set in frontmatter (planner sets after Per-Task Verification Map is filled)
- [x] **Reviews-revision tests added to map (D-17 ordering proof, D-18 missing-keys raise, D-19 extended-validation, D-20 no-mutation, B-1 path-derived backup, B-2 microsecond timestamp, B-3 no-persist proof, B-4 equity boundary, B-5 rationale)**

**Approval:** planner-approved (planning complete; reviews-revision pass folded in 2026-04-21; awaiting execution)
