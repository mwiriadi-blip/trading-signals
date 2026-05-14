---
phase: 37
slug: per-user-email-fan-out-admin-invite-disable-routes-invite-ac
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-14
---

# Phase 37 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.3.3 |
| **Config file** | none — inferred from conftest.py |
| **Quick run command** | `.venv/bin/pytest -x --tb=short tests/test_per_user_fanout.py tests/test_web_admin.py tests/test_web_invite.py tests/test_auth_store_users.py` |
| **Full suite command** | `.venv/bin/pytest -x --tb=short` |
| **Estimated runtime** | ~30 seconds (50-user performance test uses 10ms mocked latency) |

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/pytest -x --tb=short tests/test_per_user_fanout.py tests/test_web_admin.py tests/test_web_invite.py tests/test_auth_store_users.py`
- **After every plan wave:** Run `.venv/bin/pytest -x --tb=short`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 37-01-01 | 01 | 1 | UMAIL-01 | — | No per-user secrets in email body or URL | unit | `pytest tests/test_per_user_fanout.py::TestFanOutEmail -x` | ❌ Wave 0 | ⬜ pending |
| 37-01-02 | 01 | 1 | UMAIL-02 | — | Per-user crash boundary isolates failures | unit | `pytest tests/test_per_user_fanout.py::TestCrashBoundary -x` | ❌ Wave 0 | ⬜ pending |
| 37-01-03 | 01 | 1 | UMAIL-02 | — | W3 invariant: exactly 2 mutate_state per cycle | unit | `pytest tests/test_per_user_fanout.py::TestW3Invariant -x` | ❌ Wave 0 | ⬜ pending |
| 37-01-04 | 01 | 1 | UMAIL-03 | — | asyncio.Semaphore(2) throttle; no 429s in 50-user test | performance | `pytest tests/test_per_user_fanout.py::TestSemaphoreThrottle -x` | ❌ Wave 0 | ⬜ pending |
| 37-01-05 | 01 | 1 | UMAIL-03 | — | RFC 8058 List-Unsubscribe + List-Unsubscribe-Post headers present | unit | `pytest tests/test_per_user_fanout.py::TestRFC8058Headers -x` | ❌ Wave 0 | ⬜ pending |
| 37-01-06 | 01 | 1 | UMAIL-04 | — | Fan-out skips paused/disabled users | unit | `pytest tests/test_per_user_fanout.py::TestEmailPrefsSkip -x` | ❌ Wave 0 | ⬜ pending |
| 37-02-01 | 02 | 1 | UMAIL-04 | — | PATCH /settings/email-prefs persists email_enabled + pause_until | unit | `pytest tests/test_web_dashboard_email_prefs.py -x` | ❌ Wave 0 | ⬜ pending |
| 37-02-02 | 02 | 1 | UMAIL-02 | — | /healthz/last-cycle returns per-user outcomes (admin-gated) | unit | `pytest tests/test_web_admin_invite.py::TestLastCycle -x` | ❌ Wave 0 | ⬜ pending |
| 37-03-01 | 03 | 2 | RBAC-03 | — | Invite token consumed + user row created with password_hash | unit | `pytest tests/test_auth_store_users.py -x` | partial | ⬜ pending |
| 37-03-02 | 03 | 2 | RBAC-03 | — | Step 1: password validated + bcrypt hash stored | unit | `pytest tests/test_web_invite.py::TestStep1Password -x` | ❌ Wave 0 | ⬜ pending |
| 37-03-03 | 03 | 2 | RBAC-03 | — | Step 2: TOTP enrollment reuses existing TOTP flow | unit | `pytest tests/test_web_totp.py -x` | ✅ exists | ⬜ pending |
| 37-03-04 | 03 | 2 | RBAC-03 | — | Step 3: trusted device cookie set | unit | `pytest tests/test_web_invite.py::TestStep3Device -x` | ❌ Wave 0 | ⬜ pending |
| 37-03-05 | 03 | 2 | RBAC-03 | — | Expired/consumed token → error page (not redirect) | unit | `pytest tests/test_web_invite.py::TestExpiredToken -x` | ❌ Wave 0 | ⬜ pending |
| 37-04-01 | 04 | 2 | RBAC-03 | — | POST /admin/invites mints token + sends email | unit | `pytest tests/test_web_admin_invite.py::TestAdminInviteIssue -x` | ❌ Wave 0 | ⬜ pending |
| 37-04-02 | 04 | 2 | RBAC-03 | — | DELETE /admin/invites/{hash} revokes invite | unit | `pytest tests/test_web_admin_invite.py::TestAdminInviteRevoke -x` | ❌ Wave 0 | ⬜ pending |
| 37-04-03 | 04 | 2 | UMAIL-01 | — | Unicode display name round-trips via email.utils.formataddr | unit | `pytest tests/test_per_user_fanout.py::TestUnicodeDisplayName -x` | ❌ Wave 0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_per_user_fanout.py` — stubs for UMAIL-01..04 (fanout, crash boundary, W3 invariant, semaphore, RFC 8058, email prefs skip, unicode)
- [ ] `tests/test_web_invite.py` — stubs for RBAC-03 (step 1 password, step 3 device, expired token)
- [ ] `tests/test_web_dashboard_email_prefs.py` — stubs for UMAIL-04 (PATCH /settings/email-prefs)
- [ ] `tests/conftest.py` — extend with `tmp_state_dir` fixture for per-user state isolation (if not already present)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Admin sees inline invite URL after POST /admin/invites | RBAC-03 | HTMX swap response must be visually confirmed | Issue invite from /admin/users; verify URL appears in `<code>` block on page |
| Invitee email arrives with correct invite link | RBAC-03 | Requires live Resend in staging | Send invite to test address; click link; confirm wizard starts |
| Resend rate limit live verification | UMAIL-03 | Rate limit value may differ per account | Run 5-req burst; confirm no 429; bump FANOUT_SEMAPHORE_LIMIT if safe |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
