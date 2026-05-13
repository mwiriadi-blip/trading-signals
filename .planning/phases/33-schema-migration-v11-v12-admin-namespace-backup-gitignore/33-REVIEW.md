---
phase: 33-schema-migration-v11-v12-admin-namespace-backup-gitignore
reviewed: 2026-05-13T00:00:00Z
depth: deep
files_reviewed: 15
files_reviewed_list:
  - state_manager/migrations.py
  - state_manager/validation.py
  - state_manager/__init__.py
  - state_manager/trades.py
  - notifier/dispatch.py
  - notifier/__init__.py
  - scripts/check_backup_age.py
  - scripts/backup_state.sh
  - systemd/trading-signals-backup.service
  - systemd/trading-signals-backup.timer
  - daily_run.py
  - paper_trade_alerts.py
  - tests/test_state_migration_v12.py
  - tests/test_backup_age.py
  - tests/test_gitignore_gate.py
findings:
  critical: 2
  warning: 3
  info: 1
  total: 6
status: issues_found
---

# Phase 33: Code Review Report

**Reviewed:** 2026-05-13
**Depth:** deep
**Files Reviewed:** 15
**Status:** issues_found

## Summary

Phase 33 adds the v11→v12 user-namespace migration, auto-backup on migration, and the rclone/B2 stale-backup alerting pipeline. The migration logic itself is correct and idempotent. Two CRITICAL findings: an unguarded `KeyError` path in `load_state` after `StateV12` passes validation (corrupted/manually edited `users` dict), and the `send_backup_stale_email` `now` parameter is silently discarded — the testability hook the signature promises is dead code. Three WARNINGs cover: the rclone `returncode` never checked (silent false-negative stale reads), an `html.escape`-escaped timestamp leaking into a plain-text email subject, and the `[Install]` section on the `.service` unit (will create an unwanted non-timer enable path). One INFO item: the docstring promise that `daily_run.py` calls `check_backup_age()` does not match production wiring.

---

## Critical Issues

### CR-01: Unguarded `KeyError` on `state['users'][_ADMIN_UID]['contracts']` in `load_state`

**File:** `state_manager/__init__.py:303`

**Issue:** After `StateV12.model_validate(state)` passes (the Pydantic model declares `users: dict` with no substructure constraint), `load_state` does a bare subscript chain:

```python
_user_contracts = state['users'][_ADMIN_UID]['contracts']
```

`StateV12` only guarantees `users` is a `dict`. If the dict is empty, or `_ADMIN_UID` is present but the nested user bucket has no `contracts` key (e.g. a manually edited `state.json`, or a future migration bug), this raises an unhandled `KeyError`. The `KeyError` propagates straight to the caller — it is not a `json.JSONDecodeError`, so the corruption-recovery path (`D-05 narrow catch`) never fires. The operator sees a crash instead of graceful recovery. `_validate_loaded_state` also does not catch this because it only checks top-level key presence.

**Fix:** Add an explicit guard before the bare-subscript access, or expand `StateV12` to validate the user bucket shape:

```python
# Option A — guard in load_state (targeted, no schema bump needed)
_admin_bucket = state.get('users', {}).get(_ADMIN_UID)
if not isinstance(_admin_bucket, dict) or 'contracts' not in _admin_bucket:
    raise ValueError(
        f"state['users'][{_ADMIN_UID!r}] missing or has no 'contracts' key"
    )
_user_contracts = _admin_bucket['contracts']
```

```python
# Option B — extend StateV12 (preferred; catches the gap at validation time)
from pydantic import BaseModel
class UserBucketV12(BaseModel):
    model_config = ConfigDict(extra='allow')
    account: float
    initial_account: float
    contracts: dict
    positions: dict
    trade_log: list
    equity_history: list
    paper_trades: list

class StateV12(BaseModel):
    model_config = ConfigDict(extra='allow')
    schema_version: int
    admin_user_id: str
    last_run: str | None
    signals: dict
    markets: dict
    strategy_settings: dict
    warnings: list
    users: dict[str, UserBucketV12]
```

---

### CR-02: `now` parameter in `send_backup_stale_email` is immediately deleted — testability contract broken

**File:** `notifier/dispatch.py:427`

**Issue:** The function signature advertises `now=None` as a testability hook (matching the project-wide convention), but the parameter is immediately discarded:

```python
def send_backup_stale_email(last_backup_iso: str, *, now=None) -> SendStatus:
    del now  # testability hook; not used in email body
```

The function does not use `now` anywhere — not in the email body, not in the subject, not in any log line. The `del now` means any test that passes a controlled `now` value to verify time-dependent behaviour gets silent no-op semantics. Worse, `check_backup_age.py:83` calls `notifier.send_backup_stale_email(last_iso, now=now)` specifically to propagate the controlled clock — that `now` is thrown away, so any future use of `now` inside the function (e.g. formatting the "alert sent at" timestamp) would require rediscovering this bug.

The real problem: the email body timestamps are hardcoded-absent (there is no "alert sent at" line). If a future developer adds a timestamp to the body, they will assume `now` works and will not notice `del now` on line 427.

**Fix:** Remove `del now` and keep the parameter live even if it is currently unused. If the body intentionally has no timestamp, document that explicitly rather than silently discarding the value:

```python
def send_backup_stale_email(last_backup_iso: str, *, now=None) -> SendStatus:
    # `now` reserved for future use (e.g. "alert sent at" line in body).
    # Do NOT del — callers (check_backup_age) pass it for forward-compat.
    ...
```

---

## Warnings

### WR-01: `rclone` exit code never checked — failed backup read silently treated as empty output

**File:** `scripts/check_backup_age.py:51-58`

**Issue:** `subprocess.run` is called without `check=True` and without inspecting `result.returncode`:

```python
result = subprocess.run(
    ['rclone', 'lsl', f'{remote}:{bucket}/{path}'],
    capture_output=True, text=True,
)
for line in result.stdout.splitlines():
    ...
```

If rclone exits non-zero (bucket not found, auth failure, network error), `result.stdout` is empty and `result.stderr` contains the diagnostic. The caller silently gets `None` from `get_last_backup_time`, which `check_backup_age` treats as "backup is stale" — **a rclone auth misconfiguration will fire a stale-backup alert email every day indefinitely, with no indication of the actual failure**.

**Fix:** Check `result.returncode` and log stderr on non-zero exit:

```python
result = subprocess.run(
    ['rclone', 'lsl', f'{remote}:{bucket}/{path}'],
    capture_output=True, text=True,
)
if result.returncode != 0:
    logger.error(
        '[Backup] rclone lsl failed (rc=%d): %s',
        result.returncode, result.stderr.strip(),
    )
    return None
for line in result.stdout.splitlines():
    ...
```

---

### WR-02: HTML-escaped timestamp in plain-text email subject

**File:** `notifier/dispatch.py:440-441`

**Issue:** `html.escape(last_backup_iso, quote=True)` is applied to produce `safe_ts`, which is then used **in the email subject line** (not in an HTML body):

```python
safe_ts = html.escape(last_backup_iso, quote=True)
subject = f'[trading-signals] BACKUP STALE — last backup {safe_ts}'
```

The email is sent as text/plain (`html_body=None`). Email subjects are always plain text. An ISO timestamp like `2026-05-10T14:30:00+00:00` contains no HTML-special characters so this is harmless in practice — but if `last_backup_iso` were ever `unknown` or contained an `&` or `<` (e.g. from a malformed rclone output line), the subject would contain literal `&amp;` or `&lt;` strings, which is wrong for a plain-text channel.

The unescaped `last_backup_iso` is used correctly in the text body (`Last successful backup: {last_backup_iso}`). The `html.escape` call should be removed from the subject-line construction, not moved to the body.

**Fix:**

```python
subject = f'[trading-signals] BACKUP STALE — last backup {last_backup_iso}'
text_body = (
    f'The off-droplet backup of state.json is overdue.\n\n'
    f'Last successful backup: {last_backup_iso}\n\n'
    ...
)
```

---

### WR-03: `[Install] WantedBy=multi-user.target` on the `.service` unit creates an unintended direct-enable path

**File:** `systemd/trading-signals-backup.service:23-24`

**Issue:** The service is a `Type=oneshot` unit intended to be driven exclusively by `trading-signals-backup.timer`. The `[Install]` section with `WantedBy=multi-user.target` means `systemctl enable trading-signals-backup.service` will also work and will start the backup **on every boot** independently of the timer. An operator following generic "enable the service" instructions (or a deploy script that runs `systemctl enable` on all units in the systemd/ directory) will end up running the backup at boot AND on the timer cadence, with no connection between them.

The `[Install]` section on a timer-driven oneshot service should either be absent entirely (the timer's `[Install]` is sufficient) or explicitly target `trading-signals-backup.timer` rather than `multi-user.target`.

**Fix:** Remove the `[Install]` section from the `.service` file:

```ini
# trading-signals-backup.service — no [Install] section needed;
# the timer unit's [Install] WantedBy=timers.target is sufficient.
```

If the service must remain directly enableable for manual/emergency runs, change to:

```ini
[Install]
WantedBy=trading-signals-backup.timer
```

---

## Info

### IN-01: Docstring in `check_backup_age.py` claims `daily_run.py` calls it — not wired

**File:** `scripts/check_backup_age.py:6`

**Issue:** The module docstring says:

```
Or import and call check_backup_age() from daily_run.py.
```

`daily_run.py` does not import or call `check_backup_age`. The function is only triggered via the systemd timer. The docstring creates a false expectation that the stale-backup check runs as part of the daily orchestration loop, when in fact it only runs on the timer's daily cadence — which is a separate, independently-failing process. If the timer is not installed or fails silently, there is no fallback from the daily run.

**Fix:** Either remove the inaccurate docstring line, or wire `check_backup_age` into the daily run (noting the latter would add a subprocess dependency to the orchestration path, which has its own tradeoffs).

---

_Reviewed: 2026-05-13_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
