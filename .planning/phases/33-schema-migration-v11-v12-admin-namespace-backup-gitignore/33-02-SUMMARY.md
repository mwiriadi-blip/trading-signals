---
phase: 33-schema-migration-v11-v12-admin-namespace-backup-gitignore
plan: "02"
subsystem: state_manager
tags: [migration, schema, tenant, v12, pydantic, tdd, fixtures]
dependency_graph:
  requires: [33-01]
  provides: [v11-fixtures, test_state_migration_v12]
  affects: [state_manager, tests]
tech_stack:
  added: []
  patterns: [parametrized pytest, TDD RED-GREEN, forward-only lossless round-trip assertion]
key_files:
  created:
    - tests/test_state_migration_v12.py
    - tests/fixtures/state_v11_empty.json
    - tests/fixtures/state_v11_max_trade_log.json
    - tests/fixtures/state_v11_mid_pyramid.json
    - tests/fixtures/state_v11_mid_alert_approaching.json
    - tests/fixtures/state_v11_naive_datetime.json
  modified: []
decisions:
  - "Parametrized test_round_trip with 5 fixture names keeps 10 invariants DRY — no per-case duplicate"
  - "TestStateV12Schema calls _migrate (full chain) not _migrate_v11_to_v12 directly — exercises schema_version bump to 12"
  - "TestV12AutoBackup uses tmp_path fixture + glob pattern to assert backup file presence"
  - "Fixtures use v11 fully-migrated markets/strategy_settings (contract_type + financing_rate_annual_pct) to avoid false-fail on v10->v11 idempotency"
metrics:
  duration: "~5 minutes"
  completed: "2026-05-13"
  tasks_completed: 2
  files_changed: 6
---

# Phase 33 Plan 02: v11->v12 Round-Trip + Validation Test Suite Summary

**One-liner:** TDD test suite (4 classes, 12 tests) with 5 v11 fixture files covering forward-only lossless round-trip, Pydantic StateV12 validation, pre-migration backup behavior, and MIGRATIONS chain contiguity.

## Tasks Completed

| Task | Description | Commit |
|------|-------------|--------|
| RED | Write tests/test_state_migration_v12.py with all 4 test classes | 6bb2f18 |
| GREEN | Create 5 v11 fixture JSON files in tests/fixtures/ | adcdceb |

## What Was Built

**Test module (`tests/test_state_migration_v12.py`):**
- `TestV12RoundTrip`: 5 parametrized cases × 10 invariants — verifies forward-only lossless migration from v11 to v12 via `_migrate_v11_to_v12` directly; asserts `schema_version==11` (migrator doesn't bump), all 7 per-user keys moved to user bucket, `admin_user_id` set, top-level `account`/`trade_log` absent
- `TestStateV12Schema`: 5 parametrized cases — calls full `_migrate` chain (v11→v12 + version bump to 12) then `StateV12.model_validate`; DeprecationWarnings suppressed for naive_datetime fixture
- `TestV12AutoBackup`: 2 tests — v11 state triggers `shutil.copy2` backup matching `*.v11-backup-*` glob; v12 state produces no new backup
- `TestV12Contiguity`: 3 tests — `_assert_migration_chain_contiguous()` does not raise; `STATE_SCHEMA_VERSION == 12`; MIGRATIONS keys == {1..12}

**Fixture files (5):**
- `state_v11_empty.json` — account=10000.0, all collections empty, `paper_trades: []`
- `state_v11_max_trade_log.json` — 3 closed trades with all 11 `_REQUIRED_TRADE_FIELDS`
- `state_v11_mid_pyramid.json` — SPI200 LONG open, `pyramid_level=1`, `manual_stop=null`
- `state_v11_mid_alert_approaching.json` — paper_trade with `last_alert_state="APPROACHING"`
- `state_v11_naive_datetime.json` — `equity_history[0].date = "2026-04-30T08:00:00"` (naive ISO, no tz offset)

All fixtures: `schema_version=11`, full v11 shape with `contract_type` + `financing_rate_annual_pct` on markets (v11 fields).

## Deviations from Plan

None — plan executed exactly as written.

## Pre-execution Note

This worktree was spawned before Plan 33-01 merged to main. The branch was fast-forward merged from local `main` (which had the 33-01 commits) before execution to bring in the `state_manager/` package, v12 migrations, and downstream test updates.

## Known Stubs

None — all test logic wired to real production imports. No mock data that bypasses actual migration code.

## Threat Flags

None — this plan only adds test files and JSON fixtures. No new network endpoints, auth paths, file access patterns, or schema changes at trust boundaries.

## TDD Gate Compliance

| Gate | Commit | Status |
|------|--------|--------|
| RED (`test(...)`) | 6bb2f18 | PRESENT |
| GREEN (`feat(...)`) | adcdceb | PRESENT |

## Self-Check: PASSED

| Item | Status |
|------|--------|
| tests/test_state_migration_v12.py | FOUND |
| tests/fixtures/state_v11_empty.json | FOUND |
| tests/fixtures/state_v11_max_trade_log.json | FOUND |
| tests/fixtures/state_v11_mid_pyramid.json | FOUND |
| tests/fixtures/state_v11_mid_alert_approaching.json | FOUND |
| tests/fixtures/state_v11_naive_datetime.json | FOUND |
| Commit 6bb2f18 (RED) | FOUND |
| Commit adcdceb (GREEN) | FOUND |
