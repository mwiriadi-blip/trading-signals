---
phase: 3
slug: state-persistence-with-recovery
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-21
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.3.3 |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`, testpaths=["tests"]) |
| **Quick run command** | `.venv/bin/python -m pytest tests/test_state_manager.py -x -q` |
| **Full suite command** | `.venv/bin/python -m pytest tests/ -q` |
| **Estimated runtime** | ~3 seconds (quick) / ~8 seconds (full) |

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/python -m pytest tests/test_state_manager.py -x -q`
- **After every plan wave:** Run `.venv/bin/python -m pytest tests/ -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 8 seconds

---

## Per-Task Verification Map

> Filled in by planner. Each plan task gets a row mapping to its REQ-ID(s) and the automated command that proves it.

| Task ID | Plan | Wave | Requirement(s) | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|----------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 0 | (Wave 0 stubs) | T-03-01 | N/A — pure I/O hex | infra | `test -f tests/test_state_manager.py && test -f state_manager.py` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

**Source mapping (from RESEARCH.md §Validation Architecture):**

| Req ID | Behavior | Test Type | Automated Command |
|--------|----------|-----------|-------------------|
| STATE-01 | reset_state() returns dict with all 8 required top-level keys | unit | `pytest tests/test_state_manager.py::TestReset -x -q` |
| STATE-01 | load_state() on fresh state has all 8 keys + correct types | unit | `pytest tests/test_state_manager.py::TestLoadSave -x -q` |
| STATE-02 | Atomic write: crash on os.replace leaves original intact | unit | `pytest tests/test_state_manager.py::TestAtomicity -x -q` |
| STATE-02 | Atomic write: tempfile cleaned up on failure | unit | `pytest tests/test_state_manager.py::TestAtomicity -x -q` |
| STATE-02 | Successful save: state.json readable and matches input | unit | `pytest tests/test_state_manager.py::TestLoadSave -x -q` |
| STATE-03 | Corrupt state.json triggers JSONDecodeError recovery | unit | `pytest tests/test_state_manager.py::TestCorruptionRecovery -x -q` |
| STATE-03 | Backup file `state.json.corrupt.<ts>` created in same dir | unit | `pytest tests/test_state_manager.py::TestCorruptionRecovery -x -q` |
| STATE-03 | Fresh state returned with corruption warning entry | unit | `pytest tests/test_state_manager.py::TestCorruptionRecovery -x -q` |
| STATE-04 | Schema v1 → no-op migration preserves all fields | unit | `pytest tests/test_state_manager.py::TestSchemaVersion -x -q` |
| STATE-04 | State without schema_version key migrates to current | unit | `pytest tests/test_state_manager.py::TestSchemaVersion -x -q` |
| STATE-05 | record_trade appends to trade_log with net_pnl | unit | `pytest tests/test_state_manager.py::TestRecordTrade -x -q` |
| STATE-05 | record_trade adjusts account by net_pnl (closing-cost deducted) | unit | `pytest tests/test_state_manager.py::TestRecordTrade -x -q` |
| STATE-05 | record_trade sets positions[instrument] = None | unit | `pytest tests/test_state_manager.py::TestRecordTrade -x -q` |
| STATE-05 | record_trade raises ValueError on missing/invalid fields | unit | `pytest tests/test_state_manager.py::TestRecordTrade -x -q` |
| STATE-06 | update_equity_history appends {date, equity} entry | unit | `pytest tests/test_state_manager.py::TestEquityHistory -x -q` |
| STATE-07 | reset_state() account == 100_000.0 | unit | `pytest tests/test_state_manager.py::TestReset -x -q` |
| STATE-07 | reset_state() positions all None, trade_log/history/warnings empty | unit | `pytest tests/test_state_manager.py::TestReset -x -q` |
| Hex guard | state_manager.py imports only stdlib + system_params | arch | `pytest tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent -x -q` |
| Warnings | append_warning FIFO bound: 105 entries → 100 | unit | `pytest tests/test_state_manager.py::TestWarnings -x -q` |
| Warnings | append_warning date uses AWST format | unit | `pytest tests/test_state_manager.py::TestWarnings -x -q` |

---

## Wave 0 Requirements

- [ ] `tests/test_state_manager.py` — Phase 3 test module (TestLoadSave, TestAtomicity, TestCorruptionRecovery, TestRecordTrade, TestEquityHistory, TestReset, TestWarnings, TestSchemaVersion)
- [ ] `state_manager.py` — public API stubs (load_state, save_state, record_trade, update_equity_history, reset_state, append_warning) + private helpers (_atomic_write, _migrate, _backup_corrupt, _validate_trade)
- [ ] `system_params.py` — add `INITIAL_ACCOUNT = 100_000.0`, `MAX_WARNINGS = 100`, `STATE_SCHEMA_VERSION = 1`, `STATE_FILE = 'state.json'`
- [ ] Extend `tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent` to cover `state_manager.py` with appropriate allow-list (allows json/os/tempfile/datetime/pathlib/typing/zoneinfo + system_params; blocks signal_engine, sizing_engine, notifier, dashboard, main, requests, schedule, numpy, pandas)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| — | — | — | All Phase 3 behaviors have automated verification via stdlib mocking + tmp_path fixture isolation |

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (test_state_manager.py, state_manager.py, system_params constants, AST blocklist extension)
- [ ] No watch-mode flags
- [ ] Feedback latency < 8s
- [ ] `nyquist_compliant: true` set in frontmatter (planner sets after Per-Task Verification Map is filled)

**Approval:** pending
