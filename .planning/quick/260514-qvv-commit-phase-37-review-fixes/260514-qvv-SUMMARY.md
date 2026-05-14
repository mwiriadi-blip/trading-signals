---
quick_id: 260514-qvv
slug: commit-phase-37-review-fixes
description: commit phase-37 review fixes
date: 2026-05-14
commit: 5575f21
status: complete
---

# Quick Task 260514-qvv: commit phase-37 review fixes

**Completed:** 2026-05-14
**Commit:** 5575f21

## What was done

Committed 12 code-review findings from 37-REVIEW.md (all fixed per 37-REVIEW-FIX.md):

- **CR-01** — Raw invite token removed from admin HTML response; confirmation banner shows email + expiry only
- **CR-02** — Invite token no longer stored raw in wizard cookie; SHA-256 hash in cookie, raw token in hidden form field, POST validates hash before proceeding
- **CR-03** — `create_user` now always writes `password_hash` key (None for admin rows, bcrypt hash for invite-path callers)
- **CR-04** — `PATCH /admin/users/{uid}/disable` reads `disabled` from form body only, not query-string
- **WR-01** — Email validation regex added to `POST /admin/invites` before minting token
- **WR-02** through **WR-05** + **IN-01** through **IN-03** — additional warning and info findings resolved

**Tests:** 2325 passed, 0 failures.

**Files committed:**
- `auth_store/_users.py`
- `system_params.py`
- `tests/test_web_admin_invite.py`
- `tests/test_web_invite.py`
- `web/routes/admin/__init__.py`
- `web/routes/admin/_renderers.py`
- `web/routes/invite/__init__.py`
- `web/routes/invite/_renderers.py`
- `.planning/phases/37-.../37-01..37-05-PLAN.md` (planning docs)
