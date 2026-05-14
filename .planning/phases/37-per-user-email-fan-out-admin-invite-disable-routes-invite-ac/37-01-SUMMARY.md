---
phase: 37
plan: "01"
subsystem: test-scaffolding
tags: [wave-0, test-stubs, phase-37, fanout, invite, email-prefs]
dependency_graph:
  requires: []
  provides:
    - tests/test_per_user_fanout.py (7 Wave 0 stub classes for UMAIL-01..04)
    - tests/test_web_invite.py (3 Wave 0 stub classes for RBAC-03)
    - tests/test_web_dashboard_email_prefs.py (1 Wave 0 stub class for UMAIL-04)
    - tests/test_web_admin_invite.py (3 Wave 0 stub classes for RBAC-03 admin)
    - tests/conftest.py::pending_invite_auth_json (shared fixture)
    - tests/conftest.py::multi_user_state_json (shared fixture)
  affects:
    - tests/test_main.py (2 stub classes appended: TestFetchCountInvariant, TestW3InvariantEndToEnd)
tech_stack:
  added: []
  patterns:
    - pytest.skip Wave 0 stub pattern (all test bodies call pytest.skip before production imports)
    - Fixture synthesis from schema docs (no production-module import at fixture setup time)
key_files:
  created:
    - tests/test_per_user_fanout.py
    - tests/test_web_invite.py
    - tests/test_web_dashboard_email_prefs.py
    - tests/test_web_admin_invite.py
  modified:
    - tests/test_main.py (appended 2 classes, +39 lines)
    - tests/conftest.py (appended 2 fixtures, +145 lines)
decisions:
  - "Fixtures synthesise auth.json + state.json rows directly from schema docs rather than importing mint_invite_token — keeps fixtures stable across Plan 03 refactors"
  - "auth.json field is pending_magic_links (not magic_links) per _schema.py AuthData TypedDict"
metrics:
  duration: "~6 minutes"
  completed: "2026-05-14T04:47:25Z"
  tasks: 5
  files_modified: 6
---

# Phase 37 Plan 01: Wave 0 Test Scaffolding Summary

**One-liner:** pytest.skip stub scaffolding for all Phase 37 test classes — locks collection surface so Plans 02-05 can target specific node IDs and turn stubs GREEN incrementally.

---

## Tasks Completed

| # | Name | Commit | Files |
|---|------|--------|-------|
| 1 | Create tests/test_per_user_fanout.py (7 classes) | `6cad9a8` | tests/test_per_user_fanout.py |
| 2 | Create tests/test_web_invite.py (3 classes) | `14d86e8` | tests/test_web_invite.py |
| 3 | Create test_web_dashboard_email_prefs.py + test_web_admin_invite.py | `2f4eabe` | tests/test_web_dashboard_email_prefs.py, tests/test_web_admin_invite.py |
| 4 | Append TestFetchCountInvariant + TestW3InvariantEndToEnd to test_main.py | `04c0c51` | tests/test_main.py |
| 5 | Add pending_invite_auth_json + multi_user_state_json to conftest.py | `ca050d3` | tests/conftest.py |

---

## Artifacts Created

### tests/test_per_user_fanout.py

7 Wave 0 stub classes for UMAIL-01..04:

| Class | Requirement | Description |
|-------|-------------|-------------|
| TestFanOutEmail | UMAIL-01 | Per-user email with personal section + shared signals |
| TestCrashBoundary | UMAIL-02 | One user failure does not abort cycle |
| TestW3Invariant | UMAIL-02 | per_user_fanout.run() calls mutate_state exactly once |
| TestSemaphoreThrottle | UMAIL-03 | 50-user mock < 30s under Semaphore(2) |
| TestRFC8058Headers | UMAIL-03 | List-Unsubscribe + List-Unsubscribe-Post headers |
| TestEmailPrefsSkip | UMAIL-04 | Skips disabled + paused users |
| TestUnicodeDisplayName | UMAIL-01 | email.utils.formataddr Unicode round-trip |

### tests/test_web_invite.py

3 Wave 0 stub classes for RBAC-03:

| Class | Methods | Description |
|-------|---------|-------------|
| TestStep1Password | 5 (incl. test_password_over_72_bytes_returns_400, review #9) | Password validation + bcrypt hash |
| TestStep3Device | 3 | Trust cookie + redirect-only paths |
| TestExpiredToken | 3 | Error page (200) for expired/consumed tokens |

### tests/test_web_dashboard_email_prefs.py

| Class | Methods | Requirement |
|-------|---------|-------------|
| TestPatchEmailPrefs | 5 | UMAIL-04: PATCH /settings/email-prefs |

### tests/test_web_admin_invite.py

| Class | Methods | Description |
|-------|---------|-------------|
| TestAdminInviteIssue | 4 | POST /admin/invites (RBAC-03) |
| TestAdminInviteRevoke | 3 | DELETE /admin/invites/{hash} (RBAC-03) |
| TestLastCycle | 4 (incl. crash_field per review #5) | GET /healthz/last-cycle (UMAIL-02 + D-15) |

### tests/test_main.py additions

| Class | Methods | Description |
|-------|---------|-------------|
| TestFetchCountInvariant | 1 | UMAIL-01 SC-1: fetch_ohlcv called exactly twice per cycle |
| TestW3InvariantEndToEnd | 3 | review #3: cross-module W3 invariant (main → daily_run → per_user_fanout) |

### tests/conftest.py additions

**pending_invite_auth_json** (review consensus #11):
- Synthesises auth.json v2 schema with admin row + one unconsumed PendingInvite
- Deterministic raw_token = 'a' * 43; token_hash = 'sha256:' + sha256(raw_token).hexdigest()
- Yields dict: `{auth_path, raw_token, token_hash, email, admin_uid}`
- No mint_invite_token import — stable across Plan 03 refactors

**multi_user_state_json** (review consensus #11):
- state.json with 3 F&F users: u_active, u_paused (pause_until=today+7d), u_disabled
- Reads STATE_SCHEMA_VERSION dynamically (falls back to 12)
- Redirects STATE_FILE env var + state_manager.STATE_FILE attribute
- Yields dict: `{state_path, uids}`

---

## pytest Collection Delta

| Metric | Value |
|--------|-------|
| Before this plan | 2218 collected |
| After this plan | 2224 collected |
| Delta | +6 tests (new Wave 0 stubs) |

Full worktree collection: 2224/2237 tests collected (13 deselected), 0 errors.

---

## Production Import Gate

All new test files pass the module-top import check:

```
grep -E "^(import|from) (per_user_fanout|web\.routes\.invite|auth_store|notifier\.dispatch)" tests/test_per_user_fanout.py tests/test_web_invite.py tests/test_web_dashboard_email_prefs.py tests/test_web_admin_invite.py
```

Returns empty — no forbidden production imports at module top. All imports inside skipped test bodies (unreachable).

---

## Deviations from Plan

**1. [Rule 2 - Schema field correction] pending_magic_links vs magic_links**
- **Found during:** Task 5
- **Issue:** Plan specified `'magic_links': []` in the auth_data fixture dict, but `auth_store/_schema.py` AuthData TypedDict uses `pending_magic_links`
- **Fix:** Used `pending_magic_links` per the actual schema definition
- **Files modified:** tests/conftest.py (fixture body only)
- **Commit:** ca050d3

None beyond the above schema field alignment.

---

## Pointer to GREEN Implementations

| Stub Location | Plan that turns it GREEN |
|---------------|--------------------------|
| tests/test_per_user_fanout.py (all 7 classes) | Plan 37-02 |
| tests/test_web_invite.py (all 3 classes) | Plan 37-04 |
| tests/test_web_dashboard_email_prefs.py | Plan 37-05 |
| tests/test_web_admin_invite.py | Plan 37-05 |
| tests/test_main.py::TestFetchCountInvariant | Plan 37-05 Task 3 |
| tests/test_main.py::TestW3InvariantEndToEnd | Plan 37-05 Task 3 |

---

## Known Stubs

All stubs are intentional Wave 0 scaffolding. No stubs flow to UI rendering or data sources. Each stub calls `pytest.skip('Wave 0 stub — implementation lands in Plan 37-0X')` so pytest reports SKIPPED (not PASSED). Plans 02-05 replace skips with real assertions.

---

## Threat Flags

None. Plan 01 creates test-only files. No new network endpoints, auth paths, file access patterns, or schema changes introduced.

---

## Self-Check: PASSED

| Check | Result |
|-------|--------|
| tests/test_per_user_fanout.py exists | FOUND |
| tests/test_web_invite.py exists | FOUND |
| tests/test_web_dashboard_email_prefs.py exists | FOUND |
| tests/test_web_admin_invite.py exists | FOUND |
| Commit 6cad9a8 exists | FOUND |
| Commit 14d86e8 exists | FOUND |
| Commit 2f4eabe exists | FOUND |
| Commit 04c0c51 exists | FOUND |
| Commit ca050d3 exists | FOUND |
| SUMMARY.md exists | FOUND |
