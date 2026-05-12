---
phase: 34
slug: user-registry-invite-token-storage
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-13
---

# Phase 34 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing, in .venv) |
| **Config file** | pyproject.toml |
| **Quick run command** | `.venv/bin/pytest tests/test_auth_store.py -x --tb=short -q` |
| **Full suite command** | `.venv/bin/pytest -x --tb=short -q` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/pytest tests/test_auth_store.py -x --tb=short -q`
- **After every plan wave:** Run `.venv/bin/pytest -x --tb=short -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 34-01-01 | 01 | 1 | D-09, D-10, D-11 | — | Package split; v1→v2 migration; DEFAULT_AUTH_PATH in __init__.py; import surface unchanged | unit | `.venv/bin/pytest tests/test_auth_store.py::TestForbiddenImports -x --tb=short -q` | ❌ W0 | ⬜ pending |
| 34-01-02 | 01 | 1 | D-09 | — | v1 auth.json upgraded to v2 on first load_auth(); users=[] + pending_invites=[] backfilled; admin NOT auto-inserted | unit | `.venv/bin/pytest tests/test_auth_store.py::TestSchemaV2Migration -x --tb=short -q` | ❌ W0 | ⬜ pending |
| 34-02-01 | 02 | 2 | RBAC-03 | T-34-01 | mint_invite_token: raw token returned, only sha256:<hex> stored in auth.json; hmac.compare_digest verify; 7-day expiry; consume raises InviteExpired/InviteAlreadyConsumed (typed); single-use under LOCK_EX | unit | `.venv/bin/pytest tests/test_auth_store_users.py::TestInviteConsume -x --tb=short -q` | ❌ W0 | ⬜ pending |
| 34-02-02 | 02 | 2 | RBAC-04 | — | create_user; get_user; list_users; set_user_disabled flips disabled=True, data preserved | unit | `.venv/bin/pytest tests/test_auth_store_users.py::TestUserRegistry -x --tb=short -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_auth_store.py::TestForbiddenImports` — update to walk `auth_store/` package directory instead of `auth_store.py` file
- [ ] `tests/test_auth_store.py::TestSchemaV2Migration` — stubs for D-09 migration (v1→v2 backfill, no auto-admin)
- [ ] `tests/test_auth_store_users.py::TestUserRegistry` — stubs for create_user, get_user, list_users, set_user_disabled (RBAC-04)
- [ ] `tests/test_auth_store_users.py::TestInviteConsume` — stubs for mint_invite_token, consume_and_create_user, expiry, single-use, hmac compare (RBAC-03)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Two parallel consume(token) calls produce exactly one winner | RBAC-03 SC-3 | Threading/process-level race; hard to reproduce deterministically in unit test | Run two concurrent subprocesses against the same auth.json and assert exactly one succeeds and one raises InviteAlreadyConsumed |
| Raw token never appears in auth.json after mint + consume | RBAC-03 SC-2 | Filesystem grep after test run | After test_consume_and_create_user, `grep -r '<raw_token_value>' auth.json` must return zero matches |
