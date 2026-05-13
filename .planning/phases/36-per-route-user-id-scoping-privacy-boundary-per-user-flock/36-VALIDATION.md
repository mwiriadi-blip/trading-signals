---
phase: 36
slug: per-route-user-id-scoping-privacy-boundary-per-user-flock
status: draft
nyquist_compliant: false
wave_0_complete: true
created: 2026-05-14
---

# Phase 36 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (Python 3.13) |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `.venv/bin/pytest -x --tb=short tests/test_tenant_isolation.py tests/test_web_admin.py tests/test_web_paper_trades.py tests/test_web_trades.py tests/test_state_manager.py` |
| **Full suite command** | `.venv/bin/pytest -x --tb=short` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/pytest -x --tb=short tests/test_tenant_isolation.py tests/test_web_admin.py tests/test_web_paper_trades.py tests/test_web_trades.py`
- **After every plan wave:** Run `.venv/bin/pytest -x --tb=short`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| conftest-v12-fixture | W0 | 0 | TENANT-02 | — | `client_with_state_v3/v6` inject state with `users[uid]` sub-dict | fixture | `.venv/bin/pytest -x --tb=short tests/test_web_paper_trades.py` | ✅ (update) | ⬜ pending |
| mutate-user-state-unit | W0 | 0 | TENANT-02 | — | per-user flock serializes concurrent writes | unit | `.venv/bin/pytest -x --tb=short tests/test_state_manager.py::TestMutateUserState` | ❌ W0 | ⬜ pending |
| tenant-isolation-class | W0 | 0 | TENANT-03 | T-36-01 | user A's trades not visible in admin/user-B response | integration | `.venv/bin/pytest -x --tb=short tests/test_tenant_isolation.py::TestTenantIsolation` | ❌ W0 | ⬜ pending |
| admin-users-endpoint | W0 | 0 | RBAC-04 | T-36-02 | GET /admin/users returns PublicUserSummary shape only | integration | `.venv/bin/pytest -x --tb=short tests/test_web_admin_users.py::TestAdminUsers` | ❌ W0 | ⬜ pending |
| admin-disable-user | W0 | 0 | RBAC-04 | T-36-02 | PATCH /admin/users/{uid}/disable sets disabled flag | integration | `.venv/bin/pytest -x --tb=short tests/test_web_admin_users.py::TestAdminDisable` | ❌ W0 | ⬜ pending |
| paper-trades-migrate | 1+ | 1 | TENANT-02 | T-36-01 | paper_trade routes write to state['users'][uid] bucket | integration | `.venv/bin/pytest -x --tb=short tests/test_web_paper_trades.py` | ✅ (update) | ⬜ pending |
| trades-migrate | 1+ | 1 | TENANT-02 | T-36-01 | trade routes write to state['users'][uid] bucket | integration | `.venv/bin/pytest -x --tb=short tests/test_web_trades.py` | ✅ (update) | ⬜ pending |
| 404-cross-user-paper | 1+ | 1 | TENANT-03 | T-36-01 | entity-ID routes return 404 for other user's entity | integration | `.venv/bin/pytest -x --tb=short tests/test_web_paper_trades.py -k 404_for_other` | ❌ W0 | ⬜ pending |
| 404-cross-user-trades | 1+ | 1 | TENANT-03 | T-36-01 | trade entity routes return 404 for other user's entity | integration | `.venv/bin/pytest -x --tb=short tests/test_web_trades.py -k 404_for_other` | ❌ W0 | ⬜ pending |
| hex-boundary-guard | all | all | — | — | state_manager exports stay I/O hex, no web imports | AST | `.venv/bin/pytest -x --tb=short tests/test_web_healthz.py::TestWebHexBoundary` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/test_tenant_isolation.py` — `TestTenantIsolation` class covering TENANT-03 admin-list + cross-user-entity assertions (Wave 1 makes green)
- [x] `tests/test_state_manager_per_user.py::TestMutateUserState` — unit tests for `mutate_user_state` flock wrapper
- [x] `tests/test_web_admin_users.py::TestAdminUsers` + `TestAdminDisable` — RBAC-04 admin route tests (xfail; Wave 1 makes green)
- [x] `tests/conftest.py` — updated `client_with_state_v3` + `client_with_state_v6` to v12 shape (`state['users'][uid]` sub-dict)
- [x] `tests/test_web_paper_trades_ownership.py` — 404-for-other-users stubs (D-14; xfail; Wave 2)
- [x] `tests/test_web_trades_ownership.py` — 404-for-other-users stubs (D-14; xfail; Wave 2)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| All phase behaviors have automated verification. | — | — | — |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
