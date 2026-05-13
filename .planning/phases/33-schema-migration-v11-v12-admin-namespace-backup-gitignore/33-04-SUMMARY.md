---
plan: 33-04
phase: 33-schema-migration-v11-v12-admin-namespace-backup-gitignore
status: complete
completed: 2026-05-13
executor: orchestrator-inline
tasks_completed: 2
tasks_total: 2
---

## Summary

Built the off-droplet rclone-to-B2 backup pipeline: notifier email function, age-check script, shell wrapper, two systemd units, and SETUP-DROPLET.md operator docs. Satisfies TENANT-04 backup requirement.

## What Was Built

**Task 1: send_backup_stale_email in notifier + unit tests**

- `notifier/dispatch.py` — Added `send_backup_stale_email(last_backup_iso, *, now=None) -> SendStatus`:
  - Never-crash posture: `try/except Exception`, logs `[Email]` prefix, returns `SendStatus(ok=False)`
  - Subject: `[trading-signals] BACKUP STALE — last backup {last_backup_iso}`
  - Body uses `html.escape()` on dynamic values
  - `now` param swallowed (testability shim, unused in send path)
- `notifier/__init__.py` — Added `send_backup_stale_email` to dispatch import block
- `scripts/check_backup_age.py` — New I/O script:
  - `parse_rclone_lsl_line(line) -> datetime | None`: parses `rclone lsl` output
  - `get_last_backup_time(remote, bucket, path) -> datetime | None`: subprocess rclone call
  - `check_backup_age(threshold_hours=48, now=None, ...) -> None`: calls `send_backup_stale_email` if stale or no backup found
  - `if __name__ == '__main__'`: reads `B2_BUCKET` from env, `sys.exit(1)` if missing
- `tests/test_backup_age.py` — 8 unit tests (mocked subprocess + notifier):
  - `TestParseRcloneLslLine`: valid line, empty line, short line, bad date
  - `TestCheckBackupAge`: not stale, stale, exactly 48h (not stale), None triggers alert

**Task 2: Scripts, systemd units, SETUP-DROPLET.md**

- `scripts/backup_state.sh`:
  - `set -euo pipefail`
  - Reads `RCLONE_REMOTE` (default `b2`), `B2_BUCKET` (required), `STATE_FILE` (default `state.json`)
  - Runs `rclone copy "${STATE_FILE}" "${RCLONE_REMOTE}:${B2_BUCKET}/trading-signals/" --log-level INFO`
- `systemd/trading-signals-backup.service`:
  - `Type=oneshot`, `User=trader`, `WorkingDirectory=/home/trader/trading-signals`
  - `EnvironmentFile=-/home/trader/trading-signals/.env`
  - Security hardening matching web.service: `NoNewPrivileges`, `PrivateTmp`, `ProtectSystem=strict`
- `systemd/trading-signals-backup.timer`:
  - `OnCalendar=daily`, `Persistent=true`, links to `trading-signals-backup.service`
- `SETUP-DROPLET.md` — Appended "Backup Setup (Phase 33)" section:
  - rclone install, B2 bucket creation, rclone config wizard
  - `.env` additions (`B2_BUCKET`, `RCLONE_REMOTE`)
  - systemd copy + enable + verify steps
  - Manual test: `sudo systemctl start trading-signals-backup.service`

## Test Results

All 8 tests pass: `tests/test_backup_age.py` — `TestParseRcloneLslLine` (4), `TestCheckBackupAge` (4)

## Key Files

| File | Change |
|------|--------|
| `notifier/dispatch.py` | +`send_backup_stale_email` function |
| `notifier/__init__.py` | +`send_backup_stale_email` export |
| `scripts/check_backup_age.py` | New (age-check script, 2-space indent) |
| `scripts/backup_state.sh` | New (rclone copy wrapper) |
| `systemd/trading-signals-backup.service` | New (oneshot systemd unit) |
| `systemd/trading-signals-backup.timer` | New (daily timer unit) |
| `SETUP-DROPLET.md` | +Backup Setup section |
| `tests/test_backup_age.py` | New (8 unit tests) |

## Self-Check: PASSED

- ✅ `scripts/backup_state.sh` valid shell (`bash -n`)
- ✅ `scripts/check_backup_age.py` valid Python (ast.parse)
- ✅ Both systemd units exist with correct directives
- ✅ `send_backup_stale_email` importable from `notifier`
- ✅ All 8 `test_backup_age.py` tests pass
- ✅ `SETUP-DROPLET.md` has full operator backup setup section
- ✅ No modifications to STATE.md or ROADMAP.md
