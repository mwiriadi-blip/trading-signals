---
phase: 35
slug: cookie-depends-current-user-sub-router-admin-gate
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-13
---

# Phase 35 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | `pytest.ini` / `pyproject.toml` (existing) |
| **Quick run command** | `.venv/bin/pytest -x --tb=short tests/test_web_admin.py tests/test_web_healthz.py` |
| **Full suite command** | `.venv/bin/pytest -x --tb=short` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/pytest -x --tb=short tests/test_web_admin.py tests/test_web_healthz.py`
- **After every plan wave:** Run `.venv/bin/pytest -x --tb=short`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 35-01-01 | 01 | 1 | RBAC-01 | — | `get_user_by_email` returns None for unknown email, dict for known | unit | `.venv/bin/pytest -x --tb=short tests/test_auth_store.py -k user_by_email` | ✅ | ⬜ pending |
| 35-01-02 | 01 | 1 | RBAC-01 | — | Cookie payload includes `uid`; old cookies without `uid` are accepted | integration | `.venv/bin/pytest -x --tb=short tests/test_web_admin.py -k cookie` | ❌ W0 | ⬜ pending |
| 35-01-03 | 01 | 1 | RBAC-01 | — | `request.state.user_id` set from cookie payload on happy path; None for missing uid + empty users[] | integration | `.venv/bin/pytest -x --tb=short tests/test_web_admin.py -k user_id` | ❌ W0 | ⬜ pending |
| 35-02-01 | 02 | 1 | RBAC-01 | — | `current_user_id` raises HTTP 403 when `request.state.user_id` is None | unit | `.venv/bin/pytest -x --tb=short tests/test_web_admin.py -k current_user_id` | ❌ W0 | ⬜ pending |
| 35-02-02 | 02 | 1 | RBAC-02 | — | `require_admin` raises HTTP 403 for non-admin uid; returns uid for admin uid | unit | `.venv/bin/pytest -x --tb=short tests/test_web_admin.py -k require_admin` | ❌ W0 | ⬜ pending |
| 35-03-01 | 03 | 2 | RBAC-02 | — | `GET /admin/ping` returns 200 for admin session; 403 for non-admin; 403 for header-auth | integration | `.venv/bin/pytest -x --tb=short tests/test_web_admin.py -k ping` | ❌ W0 | ⬜ pending |
| 35-03-02 | 03 | 2 | RBAC-02 | — | Startup invariant: every `/admin/*` route has `require_admin` in dependency chain | integration | `.venv/bin/pytest -x --tb=short tests/test_web_admin.py::TestAdminRouteInvariant` | ❌ W0 | ⬜ pending |
| 35-04-01 | 04 | 2 | RBAC-01 RBAC-02 | — | Hex boundary: `web/dependencies.py` imports only fastapi, starlette, stdlib, auth_store | unit | `.venv/bin/pytest -x --tb=short tests/test_web_healthz.py::TestWebHexBoundary` | ✅ | ⬜ pending |
| 35-04-02 | 04 | 2 | RBAC-01 RBAC-02 | — | Full suite green — no regressions in v1.2 routes | integration | `.venv/bin/pytest -x --tb=short` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_web_admin.py` — stub file with empty test classes: `TestCookieUidExtension`, `TestDependencies`, `TestAdminSubRouter`, `TestAdminRouteInvariant`
- [ ] Add `VALID_USERNAME = 'marc'` fixture to conftest if not already present — test_web_admin.py needs it for shim happy-path test

*Existing infrastructure (pytest, conftest.py, isolated_auth_json fixture) covers the remainder.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Admin can still log in after deploy (no re-login forced) | RBAC-01 | Requires real browser + live cookie round-trip | Log in as admin after deploy; confirm dashboard loads; check network tab that `tsi_session` cookie is set with extended payload |
| Old cookie (no `uid`) accepted during grace period | RBAC-01 | Requires manually crafted pre-35 cookie | Use devtools to set a `tsi_session` cookie without `uid`; navigate to dashboard; confirm no 403 |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
