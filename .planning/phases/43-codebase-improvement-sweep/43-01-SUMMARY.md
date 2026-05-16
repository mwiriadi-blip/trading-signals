---
phase: 43-codebase-improvement-sweep
plan: 01
subsystem: notifier/security
tags: [security, tenant-isolation, crash-email, allowlist, information-disclosure]
dependency_graph:
  requires: []
  provides: [crash-email-allowlist-redaction, test-crash-email-redacts-users]
  affects: [notifier/templates.py, crash_boundary.py, tests/test_tenant_isolation.py, tests/test_main.py]
tech_stack:
  added: []
  patterns: [allowlist-default-deny, sentinel-value-absence-assertion]
key_files:
  created: []
  modified:
    - notifier/templates.py
    - crash_boundary.py
    - tests/test_tenant_isolation.py
    - tests/test_main.py
decisions:
  - "ALLOWLIST semantics over BLOCKLIST: new state schema keys are denied by default — no maintenance required when schema grows (T-43-02)"
  - "JSON output for crash state summary replaces hand-rolled text format — simpler, auditable, grep-able"
  - "_redact_state_for_crash_email placed in notifier/templates.py so it lives alongside email template logic and is testable independently of crash_boundary"
metrics:
  duration: "~8 minutes"
  completed: "2026-05-16"
  tasks: 1
  files: 4
---

# Phase 43 Plan 01: Crash-Email Allowlist Redaction Summary

**One-liner:** Allowlist-based crash-email state redaction replacing hand-rolled text summary — only 5 system-metadata keys pass through; all per-user data excluded by default.

## What Was Built

### `notifier/templates.py` — Allowlist constant + redaction helper

Added module-level `CRASH_EMAIL_STATE_ALLOWLIST: frozenset[str]` containing exactly:
- `schema_version`, `last_run`, `markets`, `strategy_settings`, `signals`

Added `_redact_state_for_crash_email(state: dict) -> dict` that:
- Returns a NEW dict with ONLY allowlisted keys
- Collects excluded key names and adds a `_redacted_keys: "[REDACTED]: ..."` marker
- Excluded keys produce the marker rather than being silently absent (T-43-03 accept)

### `crash_boundary.py` — `_build_crash_state_summary` updated

Replaced the hand-rolled text format (signals/account/positions lines) with:
- Import `_redact_state_for_crash_email` from `notifier.templates` inside the function (C-2 local-import pattern)
- Belt-and-suspenders catch: if notifier import fails during crash, produces a minimal safe dict with only `schema_version`
- `json.dumps(safe_state, indent=2, default=str)` — clean auditable JSON output

### `tests/test_tenant_isolation.py` — unskipped test with sentinel assertions

`test_crash_email_body_redacts_other_users` (was `@pytest.mark.skip`):
- Seeds state with 2 users, each with 6 unique sentinel strings across: `trade_log`, `positions`, `pnl`, `email`, `totp_secret`, `magic_link_hash`
- 12 ABSENCE assertions (`assert "SENTINEL_USER_X_Y" not in body`)
- 1 PRESENCE assertion (`assert "12" in body` — schema_version is allowlisted)

## Acceptance Criteria Verified

- `grep -n "CRASH_EMAIL_STATE_ALLOWLIST" notifier/templates.py` → 3 lines
- `grep -nE "(trade_log|positions|pnl)\s*=" notifier/templates.py` → 0 lines (no blocklist)
- `test_crash_email_body_redacts_other_users` passes
- Full suite: 2414 passed, 13 deselected, 0 failures

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Pre-existing tests asserted old text format of `_build_crash_state_summary`**
- **Found during:** Task 1, full suite run
- **Issue:** `tests/test_main.py::TestCrashEmailBoundary` had 3 assertions checking old format: `assert 'signals:' in s`, `assert 'account:' in s`, `assert 'positions:' in s`, `assert 'SPI200: LONG 2@7200' in s`. New JSON output uses `"signals"` (quoted), excludes `account` and `positions` (per-user data).
- **Fix:** Updated assertions to match new JSON format (`'"signals"' in s`, `'"schema_version"' in s`, `'[REDACTED]' in s`). Renamed `test_build_crash_state_summary_renders_open_positions` to `test_build_crash_state_summary_renders_signals_not_positions` to reflect that positions are now excluded.
- **Files modified:** `tests/test_main.py`
- **Commit:** 662521d

**2. [Rule 3 - Blocking] E402 ruff error from import ordering**
- **Found during:** Task 1, full suite run (ruff gate test)
- **Issue:** New constant `CRASH_EMAIL_STATE_ALLOWLIST` and `_redact_state_for_crash_email` function were placed between docstring and existing `from system_params import...` block, making the existing imports appear after module-level code (E402).
- **Fix:** Moved all imports to the top (after docstring), constants and helper function after imports.
- **Files modified:** `notifier/templates.py`
- **Commit:** 662521d (same commit, fixed before committing)

## Known Stubs

None.

## Threat Flags

No new threat surface introduced. This plan MITIGATES T-43-01 (Information Disclosure via crash email) and T-43-02 (future schema key auto-denial).

## Self-Check: PASSED

- notifier/templates.py: FOUND
- crash_boundary.py: FOUND (modified)
- tests/test_tenant_isolation.py: FOUND (modified)
- tests/test_main.py: FOUND (modified)
- Commit 662521d: FOUND
