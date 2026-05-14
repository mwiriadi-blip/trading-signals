---
phase: 37-per-user-email-fan-out-admin-invite-disable-routes-invite-ac
verified: 2026-05-15T06:00:00Z
status: human_needed
score: 6/6 success criteria verified
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 5/6
  gaps_closed:
    - "SC-5: /account page now renders per-user scoped state via _serve_account_page_scoped; test_other_user_dashboard_has_no_user_a_trade_content is un-skipped and PASSED"
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "Seed a production-like state.json where top-level 'trade_log' and 'positions' keys exist (admin path writes these). Authenticate as an F&F user, GET /account, and verify TRADE_CONTENT_RE returns zero matches."
    expected: "Zero matches. The scoped_state construction in _serve_account_page_scoped uses {**full_state, 'paper_trades': ..., 'equity_history': ...} which spreads top-level trade_log and positions into scoped_state if they exist at that level. render_trades_table(scoped_state) would then render that data for F&F users."
    why_human: "The test fixture seeds trade_log and positions only under state['users'][uid], never at the top level. A production state.json written by the admin path may have these at top level. Programmatic verification requires knowing whether real state.json has these top-level keys — which depends on the admin's historical write paths. This is an architectural gap that cannot be confirmed without checking actual production state or the admin write path exhaustively."
  - test: "Authenticate as a new F&F user invited via the wizard. Complete all 3 steps (password, TOTP, device trust). Confirm the dashboard at /account shows zero trade content from any other user."
    expected: "Wizard completes; /account renders with the user's own (empty) paper_trades and equity_history; no TRADE_CONTENT_RE matches."
    why_human: "End-to-end browser flow through the 3-step wizard and subsequent /account page load requires a real browser session. The invite email URL, TOTP scanner, and device trust checkbox cannot be exercised programmatically in the current test setup."
  - test: "Send a per-user email for an F&F user (by triggering the daily cycle or directly via per_user_fanout.run). Open the email and verify it contains signal content. Note whether stop-loss alerts and paper-trade P&L appear."
    expected: "Email arrives. The body currently renders only uid, date, and shared_signals dict (placeholder per _render_per_user_email_html docstring). UMAIL-01 full requirement includes stop-loss alerts and paper-trade P&L — these are NOT in the current email body."
    why_human: "Email delivery requires a real Resend API key. The content placeholder is intentional per plan design but represents partial fulfillment of UMAIL-01 (orchestration correct, content deferred). Human must verify whether the partial fulfillment is acceptable for this milestone or whether full content is required."
---

# Phase 37: Per-User Email Fan-Out + Admin Invite + Email Prefs + Accept-Invite Wizard — Verification Report (Re-verification)

**Phase Goal:** F&F users receive personalised daily emails; admin can mint/revoke invites; new users complete 3-step password+TOTP+device enrollment; per-user email preferences respected.
**Verified:** 2026-05-15T06:00:00Z
**Status:** human_needed
**Re-verification:** Yes — after SC-5 gap closure (Plan 06)

## Goal Achievement

### Observable Truths (from ROADMAP.md Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC-1 | per_user_fanout.py is top-level orchestrator; W3 invariant (exactly 2 mutate_state per cycle) holds; yfinance fetch count == 2 regardless of user count | VERIFIED | per_user_fanout.py exists; single terminal mutate_state call; TestW3InvariantEndToEnd (3 tests) + TestFetchCountInvariant GREEN; TestW3Invariant GREEN |
| SC-2 | Per-user crash boundary; admin receives end-of-cycle summary email; /healthz/last-cycle reports per-user outcomes | VERIFIED | _send_one BLE001 boundary; send_cycle_summary_email co-located in per_user_fanout.py; GET /healthz/last-cycle line 76 web/routes/healthz.py with require_admin; TestCrashBoundary + TestLastCycle + TestCycleCrashHandling GREEN |
| SC-3 | asyncio.Semaphore(2) throttles Resend; RFC 8058 List-Unsubscribe + List-Unsubscribe-Post on every per-user email; no secrets in email body/URLs | VERIFIED | FANOUT_SEMAPHORE_LIMIT=2 in system_params.py; Semaphore(FANOUT_SEMAPHORE_LIMIT) in _fan_out_all; 'List-Unsubscribe' and 'List-Unsubscribe-Post' in email_headers kwarg; TestRFC8058Headers + TestSemaphoreThrottle GREEN |
| SC-4 | User can toggle email enable/disable + set pause-until from dashboard; fan-out skips paused/disabled; admin email unaffected | VERIFIED | PATCH /settings/email-prefs at line 412 web/routes/dashboard/__init__.py; email_enabled + pause_until skip logic in _send_one; role=='ff' filter in run() ensures admin email unaffected; TestEmailPrefsSkip + TestPatchEmailPrefs GREEN |
| SC-5 | Admin can issue/revoke invites; invitee completes wizard (password+TOTP+device); lands on dashboard scoped to their per-user state | VERIFIED | POST/DELETE /admin/invites working; 22+ invite wizard tests GREEN; _serve_account_page_scoped added to web/routes/dashboard/__init__.py lines 184-232; uid Depends(_get_current_user_id) on both /account handlers; scoped_state promotes paper_trades + equity_history from state['users'][uid]; _account_include_open_form=False for F&F users suppresses entry_price/LONG/SHORT form; test_other_user_dashboard_has_no_user_a_trade_content PASSED (was previously SKIPPED) |
| SC-6 | 50-user test < 30s with throttle; Muller-style Unicode display name round-trips via email.utils.formataddr | VERIFIED | TestSemaphoreThrottle confirms 50-user mock < 30s, max_active <= 2; TestUnicodeDisplayName GREEN |

**Score: 6/6 success criteria verified**

### SC-5 Deep Verification (CR-01 and CR-02)

**CR-01: Does test_other_user_dashboard_has_no_user_a_trade_content pass genuinely or vacuously?**

The test is NOT vacuous. On the `/account` page (`active_function='account'`), the render path goes through `_account_body()` → `_render_account_management_region(scoped_state)`, which renders:
1. `_render_account_balance_form` — no TRADE_CONTENT_RE fields
2. `_render_account_stats` — reads `state.get('trade_log', [])` and `state.get('positions', {})` — both empty/None in scoped_state for this fixture
3. `render_positions_table(state, include_open_form=include_open_form)` — with `include_open_form=False` for F&F users (set via `_account_include_open_form=False`), the static open form with `name="entry_price"`, `LONG`, `SHORT` options is SUPPRESSED. Without this suppression, `entry_price` in the form HTML would match TRADE_CONTENT_RE regardless of any data scoping.
4. `render_trades_table(state)` — reads `state.get('trade_log', [])` which is None at top level of scoped_state in the test fixture.

The `render_paper_trades_region` (which renders paper_trades) is ONLY called on the 'signals' tab (dashboard_renderer/shell.py line 290), NOT on the 'account' tab. So paper_trades scoping in scoped_state does not prevent data leakage on the account page — but it doesn't need to because paper_trades never renders on /account.

The real isolation mechanism is `_account_include_open_form=False`, which suppresses the positions open form containing `entry_price` + `LONG`/`SHORT` options that would otherwise match TRADE_CONTENT_RE for every user including those with no data.

**CR-02: Do trade_log and positions from full_state bleed into scoped_state for non-admin users?**

In the test fixture, `trade_log` and `positions` are only nested under `state['users'][uid_a]` and `state['users'][uid_b]` — NOT at the top level of `seeded_state`. Therefore `scoped_state = {**full_state, 'paper_trades': ..., 'equity_history': ...}` does not include top-level `trade_log` or `positions` keys, and `render_trades_table` / `render_positions_table` render empty content for user B.

However, this is a WARNING-level architectural concern: if real production state.json were written with top-level `trade_log` or `positions` (possible if admin code paths write to top-level state), those keys WOULD bleed into F&F user renders via the `**full_state` spread. The scoping only overrides `paper_trades` and `equity_history`. `trade_log` and `positions` are NOT promoted from `state['users'][uid]` to scoped_state, so if they exist at top-level in real state, they render for all users. Human verification of real production state structure is needed (see Human Verification Required section).

### Required Artifacts (Gap Closed Items)

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `web/routes/dashboard/__init__.py` | _serve_account_page_scoped helper; uid Depends on /account handlers; scoped_state with per-user paper_trades + equity_history; Cache-Control: no-store, private | VERIFIED | Lines 184-248; uid: str = Depends(_get_current_user_id) on both /account and /dashboard-account.html; scoped_state at line 214-219; Cache-Control header at line 231 |
| `dashboard_renderer/components/account.py` | _account_include_open_form flag suppresses F&F open-position form | VERIFIED | Line 190: state.get('_account_include_open_form', True); render_positions_table passes include_open_form=include_open_form |
| `tests/test_tenant_isolation.py` | test_other_user_dashboard_has_no_user_a_trade_content NOT skipped; uses /account URL; test_crash_email_body_has_no_trade_content skip reason updated | VERIFIED | Line 164: no @pytest.mark.skip decorator; line 177: client.get('/account'); line 156: skip reason = 'SC-5 deferred: crash-email body assertions not yet written' |

### Key Link Verification (All Plans)

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| get_account_page handler | _serve_account_page_scoped | Depends(_get_current_user_id) uid param | VERIFIED | Line 238 web/routes/dashboard/__init__.py |
| _serve_account_page_scoped | render_dashboard_as_str(scoped_state) | scoped_state with paper_trades + equity_history from state['users'][uid] | VERIFIED | Lines 204-224 |
| _render_account_management_region | render_positions_table(include_open_form=False) | _account_include_open_form flag in scoped_state | VERIFIED | account.py line 190-195 |
| per_user_fanout.run | mutate_state | single terminal call after asyncio.run | VERIFIED | TestW3Invariant GREEN; grep confirms <=2 mutate_state occurrences |
| main.py | per_user_fanout.run | call after _dispatch_email_and_maintain_warnings; wrapped in try/except; 4 call sites (2 run + 2 record_cycle_crash) | VERIFIED | grep -c confirmed |
| scheduler_driver.py | per_user_fanout.run | _main_pkg.per_user_fanout.run in _run_daily_check_caught | VERIFIED | 1 call site + 1 record_cycle_crash confirmed |
| per_user_fanout.run | idempotency guard | existing.get('date') == run_date early return | VERIFIED | TestCycleDateIdempotency GREEN |
| web/app.py | invite_route.register | registered BEFORE add_middleware (review #1) | VERIFIED | position check: reg[0] < mw[0] confirmed |
| web/routes/invite/__init__.py | tsi_enroll cookie with next='/accept-invite/device' | ZERO TOTP coupling review #6 | VERIFIED | grep confirmed |
| web/routes/admin/__init__.py | per_user_fanout.send_invite_email | imported from per_user_fanout NOT notifier (review #10) | VERIFIED | line 155 confirmed |
| /healthz/last-cycle | require_admin Depends | admin-gated 7-key schema | VERIFIED | line 76 + grep -c require_admin >= 7 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| _serve_account_page_scoped | paper_trades, equity_history | state['users'][uid] via .get() chains | Yes — scoped to authenticated uid | FLOWING |
| _serve_account_page_scoped | _account_include_open_form | uid == state['admin_user_id'] | Yes — boolean gate | FLOWING |
| per_user_fanout._send_one | email_enabled, pause_until | state['users'][uid] merged in run() | Yes — merged from auth_store + per-user state | FLOWING |
| per_user_fanout.send_per_user_email | html_body | _render_per_user_email_html (placeholder) | Partial — signals dict included; stop-loss alerts and paper P&L NOT rendered | STATIC (content deferred) |
| web/routes/healthz.py healthz_last_cycle | lc | load_state()['last_cycle'] | Yes — written by per_user_fanout.run mutate_state | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| SC-5 tenant isolation test | pytest test_tenant_isolation.py::...test_other_user_dashboard_has_no_user_a_trade_content | PASSED | PASS |
| Full tenant isolation suite | pytest tests/test_tenant_isolation.py | 2 passed, 1 skipped | PASS |
| All Phase 37 tests | pytest tests/test_per_user_fanout.py tests/test_web_invite.py tests/test_web_admin_invite.py tests/test_web_dashboard_email_prefs.py tests/test_auth_store_users.py | 124 passed | PASS |
| W3 invariant + idempotency + crash handling | pytest tests/test_main.py::TestFetchCountInvariant tests/test_main.py::TestW3InvariantEndToEnd tests/test_main.py::TestCycleDateIdempotency tests/test_main.py::TestCycleCrashHandling | 8 passed | PASS |
| Full test suite | pytest --tb=short -q | 2326 passed, 1 skipped, 0 failures | PASS |
| include_open_form=False for F&F | grep _account_include_open_form in account.py | line 190 present | PASS |
| invite_route.register BEFORE AuthMiddleware | regex position check on web/app.py | reg[0] < mw[0] | PASS |
| per_user_fanout.run wired in main.py | grep -c per_user_fanout.run main.py | 4 | PASS |
| record_cycle_crash wired on all paths | grep -c per_user_fanout.record_cycle_crash main.py scheduler_driver.py | 3 total | PASS |
| idempotency guard in per_user_fanout.run | grep existing.get('date') == run_date | found | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| RBAC-03 | 37-03, 37-04, 37-05 | Admin issues invite; invitee accepts 3-step wizard; joins as F&F user | SATISFIED | All invite/wizard tests GREEN; admin invite POST/DELETE working; dashboard scoped to per-user state |
| UMAIL-01 | 37-02, 37-05 | F&F user receives daily email; fetch count == 2; signal compute once per day | SATISFIED (partial) | per_user_fanout.run wired; fetch count invariant GREEN; email dispatched but content is placeholder (stop-loss/P&L deferred per module docstring — human verification item #3) |
| UMAIL-02 | 37-02, 37-05 | Crash boundary; admin summary; /healthz/last-cycle | SATISFIED | TestCrashBoundary + TestCycleCrashHandling GREEN; /healthz/last-cycle 7-key schema |
| UMAIL-03 | 37-02 | Semaphore(2); RFC 8058 headers; no secrets in email | SATISFIED | TestRFC8058Headers + TestSemaphoreThrottle GREEN; FANOUT_SEMAPHORE_LIMIT=2 |
| UMAIL-04 | 37-02, 37-05 | Email enable/disable + pause-until; fan-out skips; admin unaffected | SATISFIED | PATCH /settings/email-prefs; role=='ff' filter; TestEmailPrefsSkip + TestPatchEmailPrefs GREEN |

Note: REQUIREMENTS.md marks UMAIL-01 through UMAIL-04 as unchecked and maps them to Phase 35 — this is stale documentation. Phase 37 implements them. RBAC-03 is correctly marked checked.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `per_user_fanout.py` | 52-55 | "Minimal placeholder HTML... Full template wired in a future plan." | WARNING | Email body lacks stop-loss alerts and paper P&L from UMAIL-01 full text; orchestration and delivery correct; content deferred. Human verification item #3 covers this. |
| `web/routes/dashboard/__init__.py` | 214 | scoped_state = {**full_state, 'paper_trades': ..., 'equity_history': ...} does NOT override top-level trade_log or positions if they exist | WARNING | If production state.json has top-level trade_log/positions (from admin write paths), these keys are NOT scoped per-user. Test fixture never seeds these at top level so the test cannot catch this bleed path. Human verification item #1 covers this. |

### Human Verification Required

#### 1. CR-02: trade_log and positions bleed in real production state

**Test:** Inspect production `state.json` for presence of top-level `trade_log` and `positions` keys (outside the `users` namespace). Alternatively: authenticate as an F&F user and GET `/account`; confirm zero TRADE_CONTENT_RE matches in the rendered HTML when the admin user has open live positions or a closed trade history at the top level.

**Expected:** Zero matches. If real state.json has top-level `trade_log`/`positions`, they will bleed into F&F user renders because `scoped_state = {**full_state, ...}` spreads them unscoped.

**Why human:** The test fixture only seeds `trade_log` and `positions` inside `state['users'][uid]`, never at top level. Whether production state.json has these top-level keys depends on admin write paths that cannot be confirmed without inspecting the live state file.

#### 2. End-to-end invite wizard browser flow

**Test:** Mint an invite via POST /admin/invites; open the invite URL in a browser; complete step 1 (password), step 2 (TOTP enrollment), step 3 (device trust); confirm redirect to /account dashboard.

**Expected:** All 3 steps complete without error; dashboard renders with no trade content from other users.

**Why human:** TOTP enrollment requires a QR code scanner or TOTP app interaction that cannot be automated in the current test setup.

#### 3. Per-user email content completeness

**Test:** Trigger the daily cycle with an F&F user registered. Open the email received by that user and verify it contains their stop-loss alerts, paper-trade P&L, and the shared signal block.

**Expected:** Email contains personalised content per UMAIL-01 full requirement. Currently `_render_per_user_email_html` is a placeholder producing uid, date, and raw signals dict only.

**Why human:** Email delivery requires a real Resend API key; email content evaluation requires opening the email. The docstring explicitly defers full template to a future plan — this human check decides whether the placeholder is acceptable for milestone completion.

### Gaps Summary

No programmatic BLOCKERS remain. The single previous gap (SC-5) is closed: `test_other_user_dashboard_has_no_user_a_trade_content` is un-skipped and PASSED. Full suite is GREEN (2326 passed, 1 skipped as expected).

Three human verification items remain:
1. CR-02 architectural concern: top-level trade_log/positions bleed if present in real state (WARNING — test fixture masks this path)
2. End-to-end wizard browser flow (cannot automate TOTP enrollment)
3. Per-user email content completeness (placeholder body acknowledged in plan design; requires operator decision on milestone acceptability)

---

_Verified: 2026-05-15T06:00:00Z_
_Verifier: Claude (gsd-verifier)_
