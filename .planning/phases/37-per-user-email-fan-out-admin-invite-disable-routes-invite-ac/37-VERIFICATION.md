---
phase: 37-per-user-email-fan-out-admin-invite-disable-routes-invite-ac
verified: 2026-05-14T11:02:23Z
status: gaps_found
score: 5/6 success criteria verified
overrides_applied: 0
gaps:
  - truth: "Invitee completes wizard and lands on a dashboard scoped to their per-user state (SC-5)"
    status: failed
    reason: "test_other_user_dashboard_has_no_user_a_trade_content is still SKIPped in tests/test_tenant_isolation.py with reason 'Phase 37: user B dashboard not yet scoped to per-user state'. The dashboard route uses load_state() (shared global state) not load_user_state(uid). Paper trades, equity history, and other per-user data are NOT scoped to the authenticated user's namespace when rendering the dashboard — another user's data can appear. This stub was deferred from Phase 36 to Phase 37 and was not turned GREEN."
    artifacts:
      - path: "tests/test_tenant_isolation.py"
        issue: "test_other_user_dashboard_has_no_user_a_trade_content still skipped at line 164 with 'Phase 37: user B dashboard not yet scoped to per-user state'"
      - path: "web/routes/dashboard/__init__.py"
        issue: "render calls use load_state() (full shared state); no per-uid scoping on dashboard/market page rendering"
    missing:
      - "Un-skip and turn GREEN test_other_user_dashboard_has_no_user_a_trade_content — requires dashboard to serve paper_trades/equity_history/alerts only from state['users'][uid] for the authenticated user"
      - "Update test_tenant_isolation.py skip reason to reflect current state or remove skip"
---

# Phase 37: Per-User Email Fan-Out + Admin Invite + Email Prefs + Accept-Invite Wizard — Verification Report

**Phase Goal:** F&F users receive personalised daily emails; admin can mint/revoke invites; new users complete 3-step password+TOTP+device enrollment; per-user email preferences respected.
**Verified:** 2026-05-14T11:02:23Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (from ROADMAP.md Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC-1 | per_user_fanout.py is top-level orchestrator; W3 invariant (exactly 2 mutate_state per cycle) holds; yfinance fetch count == 2 regardless of user count | VERIFIED | per_user_fanout.py exists at repo root (385+ lines); single terminal mutate_state call in run(); TestW3Invariant + TestFetchCountInvariant GREEN (8 tests in test_main.py) |
| SC-2 | Per-user crash boundary; admin receives end-of-cycle summary email; /healthz/last-cycle reports per-user outcomes | VERIFIED | _send_one has BLE001 try/except; send_cycle_summary_email co-located in per_user_fanout.py; GET /healthz/last-cycle registered in web/routes/healthz.py with require_admin Depends; TestCrashBoundary + TestLastCycle GREEN |
| SC-3 | asyncio.Semaphore(2) throttles Resend; RFC 8058 List-Unsubscribe + List-Unsubscribe-Post on every per-user email; no secrets in email body/URLs | VERIFIED | FANOUT_SEMAPHORE_LIMIT=2 in system_params.py; Semaphore(FANOUT_SEMAPHORE_LIMIT) in _fan_out_all; 'List-Unsubscribe' and 'List-Unsubscribe-Post' injected via email_headers kwarg; TestRFC8058Headers + TestSemaphoreThrottle GREEN |
| SC-4 | User can toggle email enable/disable + set pause-until from dashboard; fan-out skips paused/disabled; admin email unaffected | VERIFIED | PATCH /settings/email-prefs in web/routes/dashboard/__init__.py; email_enabled and pause_until skip logic in per_user_fanout._send_one; TestEmailPrefsSkip + TestPatchEmailPrefs GREEN |
| SC-5 | Admin can issue/revoke invites; invitee completes wizard (password+TOTP+device); lands on dashboard scoped to their per-user state | FAILED | Invite issue/revoke VERIFIED (POST/DELETE /admin/invites); wizard VERIFIED (22 tests GREEN in test_web_invite.py); BUT "dashboard scoped to per-user state" NOT implemented — test_other_user_dashboard_has_no_user_a_trade_content still SKIPped in test_tenant_isolation.py line 164 |
| SC-6 | 50-user test < 30s with throttle; Muller-style Unicode display name round-trips via email.utils.formataddr | VERIFIED | TestSemaphoreThrottle confirms 50-user mock < 30s, max_active <= 2; TestUnicodeDisplayName GREEN |

**Score: 5/6 success criteria verified**

### Deferred Items

None identified — the SC-5 gap is not addressed in any later phase roadmap entry (Phases 38–40 do not reference dashboard per-user scoping).

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `per_user_fanout.py` | Top-level orchestrator with run, dispatch helpers, crash handler | VERIFIED | 385+ lines; run, send_per_user_email, send_invite_email, send_cycle_summary_email, record_cycle_crash all callable; _fan_out_all and _send_one are coroutines |
| `system_params.py` | FANOUT_SEMAPHORE_LIMIT = 2 | VERIFIED | grep + python import confirmed |
| `notifier/transport.py` | _post_to_resend with email_headers kwarg | VERIFIED | inspect.signature confirms parameter present |
| `auth_store/_schema.py` | User TypedDict with password_hash: str | None | VERIFIED | line 57 confirmed |
| `auth_store/_users.py` | hash_password, verify_password, _peek_invite_token, list_pending_invites, revoke_invite | VERIFIED | All 5 functions at lines 54, 76, 333, 355, 360 |
| `auth_store/__init__.py` | Re-exports all 5 new functions | VERIFIED | python import OK |
| `requirements.txt` | bcrypt==5.0.0 | VERIFIED | grep confirmed |
| `web/routes/invite/__init__.py` | register(app) with GET/POST /accept-invite + /device | VERIFIED | 320 lines; 4 handlers; min_lines requirement met |
| `web/routes/invite/_renderers.py` | Step-1 password page, step-3 device page, error page | VERIFIED | 257 lines |
| `web/middleware/auth.py` | PUBLIC_PATHS includes /accept-invite and /accept-invite/device | VERIFIED | lines 69-70 confirmed |
| `web/app.py` | invite_route.register before add_middleware | VERIFIED | register pos 9291 < add_middleware pos 10281 |
| `web/routes/admin/__init__.py` | HX-Request-aware GET /admin/users; POST/DELETE /admin/invites | VERIFIED | HX-Request, /admin/invites in source |
| `web/routes/healthz.py` | GET /healthz/last-cycle with require_admin, 7-key schema | VERIFIED | line 76 confirmed; require_admin wired |
| `web/routes/admin/_renderers.py` | _render_admin_users_page, _render_invite_url_fragment | VERIFIED | Created in Plan 05 |
| `web/routes/admin/_models.py` | PendingInviteSummary + last_seen_date populated | VERIFIED | confirmed |
| `web/routes/dashboard/__init__.py` | PATCH /settings/email-prefs with mutate_user_state | VERIFIED | line 354 confirmed; mutate_user_state line 389 |
| `main.py` | per_user_fanout.run on force/test + once paths; crash wrapper | VERIFIED | lines 125, 149; record_cycle_crash at lines 132, 155 |
| `scheduler_driver.py` | per_user_fanout.run on scheduler-loop path; crash wrapper | VERIFIED | lines 102, 108 confirmed |
| `per_user_fanout.py` | record_cycle_crash helper + cycle-date idempotency guard | VERIFIED | record_cycle_crash at line 403; idempotency at line 340 |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| per_user_fanout.run | mutate_state | single terminal call after asyncio.run | VERIFIED | line 394-395; TestW3Invariant confirms exactly 1 call |
| main.py | per_user_fanout.run | call after _dispatch_email_and_maintain_warnings; wrapped in try/except | VERIFIED | force path line 125, once path line 149 |
| scheduler_driver.py | per_user_fanout.run | _main_pkg.per_user_fanout.run in _run_daily_check_caught | VERIFIED | line 102 |
| per_user_fanout.run | state idempotency guard | existing.get('date') == run_date at run() entry | VERIFIED | line 340; TestCycleDateIdempotency GREEN |
| main.py | per_user_fanout.record_cycle_crash | catch Exception → record_cycle_crash on crash | VERIFIED | lines 132, 155 |
| web/routes/invite/__init__.py | auth_store._peek_invite_token | validate-without-consume on GET /accept-invite | VERIFIED | line 104 |
| web/routes/invite/__init__.py | auth_store.consume_and_create_user(password_hash=...) | POST /accept-invite after bcrypt hash | VERIFIED | line 192-195 |
| web/routes/invite/__init__.py | tsi_enroll cookie with next='/accept-invite/device' | zero TOTP coupling per review #6 | VERIFIED | line 221 |
| web/app.py | invite_route.register | registered BEFORE add_middleware (review #1) | VERIFIED | pos check confirmed |
| web/routes/admin/__init__.py | per_user_fanout.send_invite_email | imported from per_user_fanout NOT notifier (review #10) | VERIFIED | line 154 |
| web/routes/admin.__init__.py | HX-Request header | explicit precedence: HX-Request > json > html (review #8) | VERIFIED | line 107 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| per_user_fanout._send_one | user_row.email_enabled, pause_until | state['users'][uid] merged in run() | Yes — merged from auth_store list_users + state.get('users') | FLOWING |
| per_user_fanout.send_per_user_email | to_addr | user_state.get('email') | Yes — from auth_store user row | FLOWING |
| web/routes/healthz.py healthz_last_cycle | lc | load_state()['last_cycle'] | Yes — written by per_user_fanout.run mutate_state | FLOWING |
| per_user_fanout._render_per_user_email_html | shared_signals | state.get('signals', {}) slice | Partial — signals dict included but stop-loss alerts and paper P&L are NOT rendered (placeholder HTML per module docstring: "Full template wired in a future plan") | STATIC (email content only; orchestration flow correct) |

Note on email content placeholder: The ROADMAP goal states "stop-loss alerts, paper P&L, and the shared signal block" but SC-1 only requires the W3 invariant and fetch count (not email content). The placeholder is explicitly documented and acknowledged as "contract-stable" per plan spec. This is an intentional deferral per plan design, not a hidden stub.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| per_user_fanout public surface callable | .venv/bin/python import check | OK | PASS |
| FANOUT_SEMAPHORE_LIMIT == 2 | .venv/bin/python import check | 2 | PASS |
| _post_to_resend has email_headers kwarg | inspect.signature check | True | PASS |
| hash_password 72-byte cap | hash_password('a'*73) raises ValueError | ValueError: ...exceeds 72... | PASS |
| auth_store public surface importable | python -c "from auth_store import hash_password..." | OK | PASS |
| invite_route.register BEFORE add_middleware | regex position check on web/app.py | reg[0]=9291 < mw[0]=10281 | PASS |
| PUBLIC_PATHS includes /accept-invite paths | grep web/middleware/auth.py | lines 69-70 found | PASS |
| per_user_fanout.run wired in main.py | grep main.py | 2 call sites + crash handlers | PASS |
| per_user_fanout.run wired in scheduler_driver.py | grep scheduler_driver.py | line 102 found | PASS |

### Probe Execution

Step 7c: SKIPPED — no probe-*.sh files declared in PLAN files; no conventional probes found for this phase type.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| UMAIL-01 | 37-02, 37-05 | F&F user receives daily email; fetch count == 2 | SATISFIED (partial) | per_user_fanout.run wired; fetch count test GREEN; email sent but content is placeholder (stop-loss/P&L deferred to future plan per module docstring) |
| UMAIL-02 | 37-02, 37-05 | Crash boundary; admin summary; /healthz/last-cycle | SATISFIED | TestCrashBoundary GREEN; send_cycle_summary_email implemented; healthz_last_cycle with 7-key schema |
| UMAIL-03 | 37-02 | Semaphore(2); RFC 8058 headers; no secrets in email | SATISFIED | TestRFC8058Headers + TestSemaphoreThrottle GREEN |
| UMAIL-04 | 37-02, 37-05 | Email enable/disable + pause-until; fan-out skips | SATISFIED | PATCH /settings/email-prefs; TestEmailPrefsSkip GREEN |
| RBAC-03 | 37-03, 37-04, 37-05 | Admin issues invite; invitee accepts wizard; joins as F&F user | SATISFIED (partial) | All invite/wizard tests GREEN; but dashboard not scoped to per-user state per SC-5 |

Note: REQUIREMENTS.md marks UMAIL-01 through UMAIL-04 as `[ ]` (unchecked) and maps them to Phase 35 in the traceability table — this is stale documentation. The ROADMAP.md correctly maps all UMAIL requirements to Phase 37 and the code implements them. REQUIREMENTS.md should be updated to `[x]` and traceability corrected to Phase 37.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `per_user_fanout.py` | 52-55 | "Minimal placeholder HTML for per-user email body. Full template wired in a future plan." | WARNING | Email content does not include stop-loss alerts or paper P&L per UMAIL-01 goal; acceptable per plan design (SC-1 only requires orchestration) |
| `tests/test_tenant_isolation.py` | 156 | @pytest.mark.skip(reason='Phase 37: fan-out not yet implemented') | BLOCKER | Fan-out IS now implemented. The skip reason is stale. The underlying test (crash email privacy) has an empty body — it would trivially pass if un-skipped. Should be un-skipped or body + assertion added. |
| `tests/test_tenant_isolation.py` | 164 | @pytest.mark.skip(reason='Phase 37: user B dashboard not yet scoped to per-user state') | BLOCKER | Phase 37 is now complete but dashboard is still NOT scoped to per-user state. SC-5 requires this. The test body has real assertions (TRADE_CONTENT_RE match check) that would fail against the current dashboard implementation. |

### Human Verification Required

None — all critical checks were verifiable programmatically.

### Gaps Summary

One gap blocks phase goal achievement:

**SC-5: Dashboard not scoped to per-user state**

The invite wizard (GET/POST /accept-invite, /device) is fully implemented and all 22 tests pass. Admin invite issue and revoke are implemented. However, the final clause of SC-5 — "lands on a dashboard scoped to their per-user state" — is not met.

Evidence: `tests/test_tenant_isolation.py:164` has `@pytest.mark.skip(reason='Phase 37: user B dashboard not yet scoped to per-user state')`. This test checks that User B's dashboard contains zero matches for User A's trade content (entry_price, n_contracts, direction). The dashboard renders via `load_state()` which returns the full shared state including all users' data. The per-user namespace (`state['users'][uid]`) exists, but the dashboard render path does not filter/scope to only the authenticated user's sub-dict.

The Phase 36 tenant isolation test was explicitly deferred to Phase 37 in the test comment "Deferred to Phase 37 when per-user state scoping lands on dashboard routes." Phase 37 did not complete this deferral.

This gap is not addressed in any later roadmap phase (38–40 cover News, Guide UI, and Codemoot — none reference dashboard per-user scoping).

---

_Verified: 2026-05-14T11:02:23Z_
_Verifier: Claude (gsd-verifier)_
