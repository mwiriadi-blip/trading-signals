---
phase: 36-per-route-user-id-scoping-privacy-boundary-per-user-flock
verified: 2026-05-14T00:00:00Z
status: passed
score: 5/7 must-haves verified (2 deferred to Phase 37 per D-12)
overrides_applied: 2
override_reason: "Both gaps are documented deferrals to Phase 37 via CONTEXT.md D-12 + plan deferred_sc frontmatter. SC-5 (RedactStateFilter) and SC-2 partial (crash-email + user-B-dashboard TestTenantIsolation) require Phase 37 fan-out orchestrator. User accepted 2026-05-14."
gaps:
  - truth: "RedactStateFilter installed at app startup (ROADMAP SC-5)"
    status: failed
    reason: "RedactStateFilter does not exist anywhere in the codebase. Phase 36 deferred it to Phase 37 via CONTEXT.md D-12, but Phase 37 ROADMAP success criteria do not explicitly include it. No later phase has a matching SC."
    artifacts:
      - path: "web/app.py"
        issue: "No RedactStateFilter import or installation found"
    missing:
      - "Implement RedactStateFilter log filter and install at app startup (or add it explicitly to Phase 37 ROADMAP SC)"
  - truth: "TestTenantIsolation fully green: zero TRADE_CONTENT_RE matches in log lines, crash-email body, and user B's served dashboard (ROADMAP SC-2)"
    status: failed
    reason: "Two of three TestTenantIsolation tests are skipped. test_crash_email_body_has_no_trade_content and test_other_user_dashboard_has_no_user_a_trade_content are skipped with 'Phase 37' reasons. ROADMAP SC-2 requires all four surfaces (admin-list HTML, log lines, crash-email body, user B dashboard) to be zero-match. Only the admin-list surface is verified in Phase 36."
    artifacts:
      - path: "tests/test_tenant_isolation.py"
        issue: "Lines 152-176: test_crash_email_body_has_no_trade_content and test_other_user_dashboard_has_no_user_a_trade_content are skipped, not passing"
    missing:
      - "Either defer SC-2 to Phase 37 explicitly in ROADMAP, or accept the current partial coverage as intentional and add an override"
deferred:
  - truth: "RedactStateFilter and crash-email/user-B-dashboard TestTenantIsolation assertions"
    addressed_in: "Phase 37"
    evidence: "CONTEXT.md D-12 explicitly defers RedactStateFilter and fan-out log redaction to Phase 37; test_crash_email_body skipped with 'Phase 37: fan-out not yet implemented'; test_other_user_dashboard skipped with 'Phase 37: user B dashboard not yet scoped to per-user state'"
---

# Phase 36: Per-Route User-ID Scoping + Privacy Boundary + Per-User Flock Verification Report

**Phase Goal:** Every paper_trades and trades route handler scoped to the authenticated user's state bucket; admin /users and /users/{uid}/disable endpoints added; per-user flock wrapper in state_manager; TestTenantIsolation isolation assertion passing.
**Verified:** 2026-05-14
**Status:** passed (2 gaps deferred to Phase 37 per D-12)
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | mutate_user_state(uid, fn) acquires state/users/{uid}.lock (LOCK_EX) then delegates to mutate_state(fn) | VERIFIED | state_manager/__init__.py lines 385-411: open(lock_path, 'a+') + fcntl.flock(fileno, LOCK_EX) + return mutate_state(mutator, path=path); both in __all__ |
| 2 | paper_trades and trades route handlers scoped to state['users'][user_id] via Depends(current_user_id) | VERIFIED | paper_trades/__init__.py: 4 mutate_user_state(user_id, _apply) calls; every _apply begins with user = state['users'][user_id]; trades/__init__.py: 3 mutate_user_state calls + record_trade(state, trade, uid=user_id) |
| 3 | GET /admin/users returns list[PublicUserSummary]; PATCH /admin/users/{uid}/disable toggles flag | VERIFIED | admin/__init__.py line 28: @router.get('/users', response_model=list[PublicUserSummary]); line 58: @router.patch('/users/{uid}/disable'); set_user_disabled wired; 404 on unknown uid |
| 4 | TestTenantIsolation::test_admin_users_response_has_no_trade_content passes (TENANT-03 partial) | VERIFIED | Test passes: TRADE_CONTENT_RE.findall(str(response.json())) returns []; FastAPI response_model=list[PublicUserSummary] strips all trade fields at serialization time |
| 5 | TestMutateUserState 3/3 passing; entity-ID 404-for-other-users tests green (TENANT-02) | VERIFIED | TestMutateUserState 3 passed; TestEntityIdOwnership 4 passed (paper_trades); TestTradeOwnership 5 passed (trades) |
| 6 | RedactStateFilter installed at app startup (ROADMAP SC-5) | FAILED | No RedactStateFilter class or installation exists anywhere in the codebase. Deferred by CONTEXT.md D-12 to Phase 37 but not formally captured in Phase 37 ROADMAP SC. |
| 7 | TestTenantIsolation fully green across all four surfaces: admin-list, log lines, crash-email, user B dashboard (ROADMAP SC-2) | FAILED | test_crash_email_body_has_no_trade_content: SKIPPED (Phase 37); test_other_user_dashboard_has_no_user_a_trade_content: SKIPPED (Phase 37); only admin-list surface verified. |

**Score:** 5/7 truths verified

---

### Deferred Items

Items not yet met but addressed by explicit deferral decisions.

| # | Item | Addressed In | Evidence |
|---|------|-------------|----------|
| 1 | RedactStateFilter log-record filter at app startup | Phase 37 (implicit) | CONTEXT.md D-12: "Explicit filter for crash-email/logs deferred to Phase 37"; fan-out orchestrator triggers the need |
| 2 | TestTenantIsolation crash-email + user B dashboard assertions | Phase 37 | test skips say "Phase 37: fan-out not yet implemented" and "Phase 37: user B dashboard not yet scoped to per-user state" |

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `state_manager/__init__.py` | mutate_user_state + load_user_state + both in __all__ | VERIFIED | Lines 385-427: both functions defined, both in __all__ |
| `state_manager/trades.py` | record_trade with uid: str = _ADMIN_UID | VERIFIED | Line 123: def record_trade(state: dict, trade: dict, uid: str = _ADMIN_UID) |
| `web/routes/admin/_models.py` | PublicUserSummary with 5 fields | VERIFIED | class PublicUserSummary(BaseModel) with user_id, display_name, status, last_seen_date, has_active_position |
| `web/routes/paper_trades/__init__.py` | 4 mutate_user_state(user_id, _apply) calls; user-bucket navigation | VERIFIED | grep count = 4; state['users'][user_id] in every _apply |
| `web/routes/trades/__init__.py` | 3 mutate_user_state calls + record_trade uid=user_id + 404 on None position | VERIFIED | grep confirmed; close_form/modify_form/cancel_row raise HTTPException(404) when position is None |
| `web/routes/admin/__init__.py` | GET /admin/users + PATCH /admin/users/{uid}/disable | VERIFIED | response_model=list[PublicUserSummary] at line 28; set_user_disabled at line 65 |
| `tests/conftest.py` | v12-shaped state; mutate_user_state stub; dependency_overrides | VERIFIED | schema_version: 12 in both fixtures; _mutate_user_state_stub monkeypatched; app.dependency_overrides[current_user_id] = lambda: _ADMIN_UID |
| `tests/test_state_manager_per_user.py` | TestMutateUserState 3 passing tests | VERIFIED | 3/3 passed |
| `tests/test_web_admin_users.py` | TestAdminUsers + TestAdminDisable | VERIFIED | 4 xpassed (routes green, xfail markers have strict=False) |
| `tests/test_web_paper_trades_ownership.py` | 4 paired 404-for-other-users tests | VERIFIED | TestEntityIdOwnership 4 passed |
| `tests/test_web_trades_ownership.py` | 5 paired 404-for-other-users tests | VERIFIED | TestTradeOwnership 5 passed |
| `tests/test_tenant_isolation.py` | TestTenantIsolation with TRADE_CONTENT_RE | PARTIAL | test_admin_users_response_has_no_trade_content PASSED; 2 tests SKIPPED (Phase 37) |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| state_manager/__init__.py::mutate_user_state | state/users/{uid}.lock | fcntl.flock(lock_file.fileno(), LOCK_EX) | WIRED | Lines 405-408: lock_dir.mkdir + open('a+') + flock(LOCK_EX) confirmed |
| state_manager/__init__.py::mutate_user_state | state_manager/__init__.py::mutate_state | return mutate_state(mutator, path=path) | WIRED | Line 409: confirmed |
| state_manager/trades.py::record_trade | state['users'][uid] | uid parameter selects user bucket | WIRED | Line 149: users_map = state.get('users', {}); user = users_map.get(uid) or _admin_user(state) |
| web/routes/paper_trades/__init__.py | state['users'][user_id] | user = state['users'][user_id] in _apply closure | WIRED | Confirmed 4 _apply closures navigate user bucket |
| web/routes/trades/__init__.py::close_trade | state_manager.record_trade | record_trade(state, trade_record, uid=user_id) | WIRED | Line 201 confirmed |
| web/routes/admin/__init__.py::admin_list_users | web/routes/admin/_models.py::PublicUserSummary | response_model=list[PublicUserSummary] | WIRED | Line 28 confirmed |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|-------------------|--------|
| web/routes/admin/__init__.py::admin_list_users | summaries (list[PublicUserSummary]) | list_users() from auth_store + load_state()['users'] | Yes — iterates auth store users and live state | FLOWING |
| web/routes/paper_trades/__init__.py | user['paper_trades'] | state['users'][user_id] from mutate_user_state | Yes — real user bucket, not top-level | FLOWING |
| web/routes/trades/__init__.py | user['positions'] | state['users'][user_id] from mutate_user_state / load_user_state | Yes — user bucket | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| from state_manager import mutate_user_state, load_user_state | python -c "from state_manager import mutate_user_state, load_user_state; print('OK')" | OK | PASS |
| TestMutateUserState 3/3 | pytest tests/test_state_manager_per_user.py::TestMutateUserState | 3 passed | PASS |
| TestTenantIsolation admin isolation | pytest tests/test_tenant_isolation.py::TestTenantIsolation::test_admin_users_response_has_no_trade_content | 1 passed | PASS |
| Ownership 404 tests | pytest tests/test_web_paper_trades_ownership.py tests/test_web_trades_ownership.py | 9 passed | PASS |
| Full suite | pytest --tb=short -q | 2212 passed, 2 skipped, 4 xpassed, 0 failures | PASS |

---

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| TENANT-02 | 36-01, 36-02, 36-03 | Per-user isolation with mutate_user_state per-user flock | SATISFIED (partial) | mutate_user_state implemented + tested; paper_trades/trades scoped to user bucket; BUT REQUIREMENTS.md checkbox still unchecked; traceability table still maps to Phase 34 |
| TENANT-03 | 36-01, 36-02, 36-03 | TestTenantIsolation quality gate green | PARTIALLY SATISFIED | Admin-list surface passes; crash-email and user B dashboard deferred to Phase 37; REQUIREMENTS.md checkbox unchecked |
| RBAC-04 | 36-01, 36-02 | Admin /users list + disable | SATISFIED | GET /admin/users with response_model=list[PublicUserSummary] + PATCH /users/{uid}/disable implemented; REQUIREMENTS.md checkbox checked [x] |

**Orphaned requirement note:** REQUIREMENTS.md traceability table maps TENANT-02, TENANT-03, and RBAC-04 to Phase 34 (stale — they were delivered in Phase 36). Table needs update.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| tests/test_web_admin_users.py | all TestAdminUsers/TestAdminDisable tests | xfail(strict=False) markers stale — routes are now green (xpassed) | INFO | Tests work correctly; xfail markers are cosmetically stale — no behavioral impact since strict=False |
| web/routes/admin/__init__.py | ~48 | last_seen_date=None hardcoded | INFO | Documented stub per D-08: "Phase 37: device-lookup not yet wired"; not a blocker |

No TBD/FIXME/XXX debt markers found in phase-modified files.

---

### Human Verification Required

None. All critical behaviors are verifiable programmatically.

---

### Gaps Summary

Two gaps block full ROADMAP SC compliance:

**Gap 1 — RedactStateFilter missing (ROADMAP SC-5):** Phase 36 ROADMAP success criterion #5 requires `RedactStateFilter` installed at app startup to replace sensitive field names with `<redacted>` in log records. The implementation deferred this to Phase 37 via CONTEXT.md D-12, but Phase 37's ROADMAP success criteria do not explicitly list it. The gap is documented and intentional — D-12 in CONTEXT.md is the authoritative deferral record. However, no later phase ROADMAP SC explicitly picks it up.

**Gap 2 — TestTenantIsolation partial (ROADMAP SC-2):** Two of three TestTenantIsolation assertions are skipped: crash-email body (requires Phase 37 fan-out) and user B dashboard (requires Phase 37 per-user dashboard scoping). ROADMAP SC-2 requires all four surfaces. The admin-list surface (the only surface that exists in Phase 36) passes cleanly.

**Root cause of both gaps:** Both deferred items require the Phase 37 fan-out orchestrator (`per_user_fanout.py`) to exist before they can be tested or implemented. The deferral is architecturally correct. However the ROADMAP success criteria for Phase 36 were written without distinguishing which surfaces were Phase 37 dependencies.

**Recommended resolution:** Add explicit Phase 37 ROADMAP SC entries for RedactStateFilter and the two skipped TestTenantIsolation assertions, or add overrides to this VERIFICATION.md acknowledging the D-12 deferral decision.

---

_Verified: 2026-05-14_
_Verifier: Claude (gsd-verifier)_
