---
phase: 11
plan: 02
subsystem: web
tags: [systemd, uvicorn, fastapi, hardening, security]
dependency_graph:
  requires:
    - "11-01 (web/app.py factory — web.app:app module path)"
  provides:
    - "systemd/trading-signals-web.service (WEB-01, WEB-02)"
    - "tests/test_web_systemd_unit.py (32 tests, D-06..D-12 guards)"
  affects:
    - "Plan 11-03 (deploy.sh uses trading-signals-web as restart target)"
    - "Plan 11-04 (SETUP-DROPLET.md references this unit file)"
tech_stack:
  added: []
  patterns:
    - "configparser with interpolation=None + optionxform=str for systemd INI parsing"
    - "Raw unit_text grep for security-critical negative assertions (0.0.0.0 absent)"
    - "Module-scoped pytest fixtures for expensive file I/O (unit_text + unit_cfg)"
key_files:
  created:
    - systemd/trading-signals-web.service
    - tests/test_web_systemd_unit.py
  modified: []
decisions:
  - "EnvironmentFile=- (leading dash) — REVIEWS MEDIUM #5 — .env optional in Phase 11 (no web env vars consumed until Phase 13)"
  - "web.app:app exact module reference — REVIEWS LOW #8 — cross-integration guard catches Plan 01 factory rename drift"
  - "configparser used for section/key parsing; raw unit_text used for negative assertions (0.0.0.0 absent, no-dash EnvironmentFile form absent)"
metrics:
  duration: "~5 minutes"
  completed: "2026-04-24T11:42:00Z"
  tasks_completed: 2
  files_created: 2
  files_modified: 0
  tests_added: 32
  tests_total: 729
---

# Phase 11 Plan 02: systemd Unit File + Tests Summary

**One-liner:** systemd unit for uvicorn on 127.0.0.1:8000 with 5-directive hardening, optional EnvironmentFile, and 32 configparser-based tests asserting every D-06..D-12 invariant.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create systemd/trading-signals-web.service | 47f6277 | systemd/trading-signals-web.service |
| 2 | Write tests/test_web_systemd_unit.py | 78001d7 | tests/test_web_systemd_unit.py |

## Artifacts

### systemd/trading-signals-web.service

Complete unit file with all D-06..D-12 invariants:

- `User=trader`, `Group=trader` (D-07)
- `ExecStart=.../.venv/bin/uvicorn web.app:app --host 127.0.0.1 --port 8000 --workers 1 --log-level info` (D-11)
- `WorkingDirectory=/home/trader/trading-signals`
- `EnvironmentFile=-/home/trader/trading-signals/.env` (leading dash — REVIEWS MEDIUM #5)
- `Restart=on-failure`, `RestartSec=10s` (D-08)
- `After=network.target`, `Wants=trading-signals.service` (D-09, soft dep)
- `StandardOutput=journal`, `StandardError=journal`, `SyslogIdentifier=trading-signals-web` (D-12)
- `NoNewPrivileges=true`, `PrivateTmp=true`, `ProtectSystem=strict`, `ReadWritePaths=/home/trader/trading-signals`, `ProtectHome=read-only` (D-10)
- `WantedBy=multi-user.target`
- No `0.0.0.0` anywhere; no `Requires=`

### tests/test_web_systemd_unit.py (32 tests, 6 classes)

| Class | Tests | Coverage |
|-------|-------|----------|
| TestSystemdUnitSections | 3 | [Unit], [Service], [Install] sections present |
| TestSystemdUnitMetadata | 4 | Description, After, Wants, no Requires |
| TestSystemdServiceCore | 11 | Type, User, Group, WorkingDir, EnvironmentFile=- (REVIEWS MEDIUM #5), Restart, RestartSec, SyslogIdentifier, StandardOutput/Error |
| TestSystemdExecStartBinding | 8 | venv path, web.app:app exact (REVIEWS LOW #8), 127.0.0.1 bind, 0.0.0.0 absent (T-11-01), port 8000, workers 1, log-level info, no --reload |
| TestSystemdHardening | 5 | All 5 D-10 directives (NoNewPrivileges, PrivateTmp, ProtectSystem, ReadWritePaths, ProtectHome) |
| TestSystemdInstall | 1 | WantedBy=multi-user.target |

## Decisions Made

1. **EnvironmentFile=- (optional prefix)** — REVIEWS MEDIUM #5. Phase 11 consumes no env vars from the web process. Without the dash, systemd would fail to start the unit on droplets where `.env` hasn't been created yet. The dash makes the file optional with no security downside. When Phase 13 introduces `WEB_AUTH_SECRET`, the operator will be required to create `.env` (per SETUP-DROPLET.md).

2. **web.app:app exact reference** — REVIEWS LOW #8. ExecStart references the exact module path from Plan 11-01's factory. Two tests (`test_execstart_references_web_app_module_exactly` in configparser + raw text) form a cross-integration guard that would catch if the Plan 01 factory were renamed.

3. **configparser + raw text dual approach** — Used `configparser` for section/key value assertions; used raw `unit_text` string for negative security assertions (0.0.0.0 absence, non-dash EnvironmentFile absence). This is more robust than regex for positive assertions and catches multiline ExecStart values correctly via configparser's continuation-line handling.

## Deviations from Plan

None — plan executed exactly as written. The unit file content and test file content match the plan spec verbatim. The worktree required a fast-forward merge from main to bring in the Phase 10 + 11-01 work (web/ directory, .planning/ files) before execution; this is normal worktree initialization, not a deviation.

## Cross-Reference for Plan 11-03

Plan 11-03 (deploy.sh) restarts this unit by name:
```bash
sudo -n systemctl restart trading-signals-web
```
The unit name `trading-signals-web` is tested in `test_syslog_identifier` (which verifies the SyslogIdentifier directive) and the full suite's `test_wanted_by_multi_user_target` confirms enablement target. Plan 11-04 (SETUP-DROPLET.md) should reference the file path `systemd/trading-signals-web.service` and the install command `sudo cp ... /etc/systemd/system/`.

## Known Stubs

None — the unit file is complete. No placeholder values or TODOs present.

## Threat Surface Scan

No new threat surface beyond what the plan's threat model specifies:
- T-11-01 (uvicorn port exposure) — mitigated by `--host 127.0.0.1` hard-coded; `test_execstart_does_not_bind_all_interfaces` asserts 0.0.0.0 absent
- T-11-06 (filesystem EoP) — mitigated by all 5 D-10 hardening directives; `TestSystemdHardening` asserts each one

## Self-Check

### Files exist:

- `systemd/trading-signals-web.service` — FOUND
- `tests/test_web_systemd_unit.py` — FOUND

### Commits exist:

- `47f6277` — FOUND (feat(11-02): create systemd/trading-signals-web.service)
- `78001d7` — FOUND (feat(11-02): add tests/test_web_systemd_unit.py)

## Self-Check: PASSED
