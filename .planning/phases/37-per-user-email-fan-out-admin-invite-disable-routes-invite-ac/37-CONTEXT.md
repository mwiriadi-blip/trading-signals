# Phase 37: Per-User Email Fan-Out + Admin Invite/Disable Routes + Invite-Acceptance Flow - Context

**Gathered:** 2026-05-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Two connected capabilities:

1. **Daily fan-out** — `per_user_fanout.py` top-level orchestrator (NOT inside `daily_run.py`) fans out a personalized email to each active F&F user after the daily cycle completes; per-user crash boundary so one user can't abort others; admin gets an end-of-cycle summary email every cycle; `/healthz/last-cycle` reports per-user outcomes; `asyncio.Semaphore(2)` throttles Resend calls; RFC 8058 `List-Unsubscribe` headers on every per-user email; W3 invariant (exactly two `mutate_state` saves per cycle) preserved by batching all per-user alert updates into a single terminal call.

2. **Invite + acceptance flow** — admin issues invites from `/admin/users` HTML page (HTMX); invite URL displayed inline + emailed to invitee automatically; invitee accepts via multi-step flow (`/accept-invite?token=<raw>` → password → TOTP → trusted device → dashboard); admin can revoke unaccepted invites; `password_hash` added to User row.

3. **Email prefs** — user toggles daily email on/off and sets `pause-until-YYYY-MM-DD` from a Settings section on the dashboard; fan-out skips paused/disabled users without burning Resend quota.

</domain>

<decisions>
## Implementation Decisions

### F&F email content

- **D-01:** F&F user daily email has two sections: (1) **personal section** — their stop-loss alerts + paper P&L summary; (2) **shared signal block** — same market signal content the admin sees. Clean separation between per-user and market-shared data.

- **D-02:** Admin's existing daily email format is **unchanged** in Phase 37. Admin receives their existing daily email as before, PLUS a separate end-of-cycle summary email.

- **D-03:** Admin end-of-cycle summary email is sent **every cycle** (not only on failure). Content: count of successes + per-user failures with uid listed. Makes anomalies visible without log-diving.

### Invite acceptance flow

- **D-04:** Multi-step flow: `GET /accept-invite?token=<raw>` validates + consumes token, then starts a session-backed multi-step wizard: (1) set password → (2) TOTP enrollment → (3) trusted device confirmation → (4) redirect to dashboard. Each step on its own page. No step can be skipped.

- **D-05:** Invite URL scheme: `/accept-invite?token=<raw_token>` — token in query string. Route validates via `hmac.compare_digest` (Phase 34 `consume_and_create_user` flock path), consumes the invite, and creates the user row with `password_hash`.

- **D-06:** `password_hash` field added to User TypedDict and stored in `auth.json` `users[]` row. This is the field deferred from Phase 34 D-05.

- **D-07:** Expired or already-consumed invite token → render a dedicated error page (not a redirect to /login). Message: "This invite link has expired or has already been used. Contact the administrator for a new invite."

### Admin invite UI

- **D-08:** Phase 37 adds an HTML page at `GET /admin/users` (currently returns JSON `list[PublicUserSummary]`). The page lists users + pending invites + has a form to issue a new invite. HTMX-backed mutations (issue invite, revoke invite, disable user).

- **D-09:** After admin issues an invite: the raw invite URL is displayed inline on the admin page for copy-paste AND the system emails the invitee automatically (a new `send_invite_email` dispatch function in notifier).

- **D-10:** Admin dashboard nav gets a link to `/admin/users`. Link visible only to admin role (consistent with `require_admin` gate).

### Email prefs (dashboard)

- **D-11:** Email preferences (enable/disable toggle + pause-until date) live in a **Settings section on the user's dashboard**. The `dashboard-settings.html` file in repo is the template anchor.

- **D-12:** Pause-until date picker: HTML `<input type="date">` — native browser picker, no JS library. User selects date, form submits via HTMX. Fan-out checks `pause_until` field from per-user state; skips user if `today < pause_until_date`.

- **D-13:** Per-user state fields for email prefs: `email_enabled` (bool, default `True`) and `pause_until` (ISO date string `"YYYY-MM-DD"` or `null`). Stored in `state["users"][uid]` sub-dict. Fan-out skips user if `not email_enabled` OR `(pause_until is not None and today <= pause_until)`. No Resend call is made for skipped users.

### Fan-out architecture

- **D-14:** `per_user_fanout.py` is a top-level orchestrator module (I/O layer peer of `daily_run.py`). Called from `main.py` AFTER `daily_run.run_daily_check()` returns. Receives the post-cycle state dict and `run_date`. All per-user alert state updates are batched and applied in a single terminal `mutate_state` call to preserve the W3 invariant.

- **D-15:** `/healthz/last-cycle` endpoint: JSON response `{"status": "ok", "cycle_date": "YYYY-MM-DD"|null, "users": [{"uid": ..., "ok": bool, "reason": str|null}]}`. Admin-gated (requires explicit `require_admin` Depends). Registered as a standalone route in `web/routes/healthz.py` following the existing `register(app)` pattern — NOT on the admin router prefix.

### Claude's Discretion

- Exact `send_invite_email` template content and subject line.
- Whether `/admin/users` HTML and the existing JSON endpoint coexist at the same path with content-type negotiation, or the JSON endpoint is renamed to `/admin/users/json`.
- Where cycle outcomes are persisted for `/healthz/last-cycle` (e.g., a `last_cycle` key in `state.json` or a sidecar file).
- Password hashing algorithm (bcrypt or argon2 — both are stdlib-adjacent; researcher should verify best current practice for Python 3.13).
- Exact UX of the per-user error boundary in `per_user_fanout.py` (retry logic or fail-fast per user).
- How the `send_invite_email` notifier function sends the BASE_URL for the invite link (env var `BASE_URL` or `APP_URL` most likely).

### SC-5 Gap Closure — Dashboard Per-User State Scoping

- **D-16:** The `/account` (and `/dashboard-account.html` alias) route handler **bypasses the shared disk cache entirely**. Instead of calling `dashboard.render_dashboard_page(load_state(), ...)` which writes to `dashboard-account.html`, the handler calls `render_dashboard_as_str()` directly and returns bytes in the response. The shared `dashboard-account.html` on disk is NOT written from the request path for this fix — cache written by `main.py`/`daily_run.py` is ignored for the per-user account page.

- **D-17:** State scoping is done **at the route layer**, not the renderer layer. The `get_account_page` handler adds `uid: str = Depends(_get_current_user_id)` and builds a scoped state dict before rendering:
  ```python
  user_bucket = full_state.get('users', {}).get(uid, {})
  scoped_state = {
    **full_state,
    'paper_trades': user_bucket.get('paper_trades', []),
    'equity_history': user_bucket.get('equity_history', []),
  }
  ```
  The renderer (`render_dashboard_as_str`, `RenderContext`) is **unchanged** — no uid param added to renderer API.

- **D-18:** Only `paper_trades` and `equity_history` are promoted from `state['users'][uid]` to top-level keys. These are the fields `TRADE_CONTENT_RE` tests for (`entry_price`, `n_contracts`, `direction`). Other per-user fields (`account`, `initial_account`, `contracts`, `positions`) are left as-is (renderer reads these from top-level; defaults to empty/None if missing in new schema).

- **D-19:** `test_other_user_dashboard_has_no_user_a_trade_content` — update test URL from `client.get('/dashboard', ...)` to `client.get('/account', ...)`. Phase 32 retired the `/dashboard` route; `/account` is where `render_paper_trades_region` renders. Remove the `@pytest.mark.skip`. The test body already has real assertions (TRADE_CONTENT_RE match check against user B's response).

- **D-20:** `test_crash_email_body_has_no_trade_content` (line 156) — skip reason is stale ("Phase 37: fan-out not yet implemented") but the test body is **empty** (no assertions). Leave it skipped but update the skip reason to: `'SC-5 deferred: crash-email body assertions not yet written'`. Do NOT un-skip an empty test. This is **out of scope** for the SC-5 dashboard fix.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase goal + requirements
- `.planning/ROADMAP.md` — Phase 37 goal, success criteria, §Phase 37 (all 6 SCs + plan-time verification note on Resend rate limit)
- `.planning/REQUIREMENTS.md` — RBAC-03 (acceptance flow), UMAIL-01, UMAIL-02, UMAIL-03, UMAIL-04

### Prior phase decisions (carry-forward foundations)
- `.planning/phases/36-per-route-user-id-scoping-privacy-boundary-per-user-flock/36-CONTEXT.md` — D-01..D-14: `mutate_user_state`, `load_user_state`, per-user flock, `PublicUserSummary`, `TestTenantIsolation`
- `.planning/phases/35-cookie-depends-current-user-sub-router-admin-gate/35-CONTEXT.md` — D-01..D-10: `current_user_id` Depends, admin sub-router gate, session payload `{u, uid, iat}`
- `.planning/phases/34-user-registry-invite-token-storage/34-CONTEXT.md` — D-01..D-12: `mint_invite_token`, `consume_and_create_user` (flock), `PendingInvite` TypedDict, `User` TypedDict (password_hash deferred to Phase 37), auth schema v2

### Notifier (email dispatch)
- `notifier/dispatch.py` — `send_daily_email` signature + SendStatus pattern; new `send_per_user_email` and `send_invite_email` and `send_cycle_summary_email` follow the same never-raise discipline
- `notifier/transport.py` — `SendStatus`, `_post_to_resend`, `_resolve_email_to_or_skip`; RFC 8058 headers added to per-user dispatch path
- `notifier/__init__.py` — re-export list; new dispatch functions must be added here

### State manager (fan-out + W3 invariant)
- `state_manager/__init__.py` — `mutate_state`, `mutate_user_state`, `load_user_state`, `load_state`; W3 invariant: exactly two `mutate_state` calls per cycle
- `state_manager/io.py` — `_atomic_write` flock pattern; non-reentrant lock warning

### Auth store (invite + user management)
- `auth_store/_users.py` — `mint_invite_token`, `consume_and_create_user`, `list_users`, `set_user_disabled`, `get_user`; `password_hash` field to add in Phase 37
- `auth_store/__init__.py` — re-export surface; `send_invite_email` needs the BASE_URL env var
- `auth_store/_schema.py` — `User` TypedDict; `PendingInvite` TypedDict

### Web routes (admin + invite acceptance)
- `web/routes/admin/__init__.py` — existing admin router; Phase 37 adds HTML `/admin/users` page + `POST /admin/invites` + `DELETE /admin/invites/{token_hash}` + `GET /admin/last-cycle`
- `web/routes/admin/_models.py` — `PublicUserSummary`; Phase 37 may add `PendingInviteSummary`
- `web/routes/healthz.py` — `register(app)` pattern; `/healthz/last-cycle` follows same pattern
- `web/dependencies.py` — `current_user_id`, `require_admin`
- `web/app.py` — `create_app()` route registration order

### Dashboard (email prefs + admin nav + SC-5 per-user scoping)
- `dashboard-settings.html` — Settings section anchor for email prefs UI
- `web/routes/dashboard/__init__.py` — dashboard route handlers; `get_account_page` handler needs uid Depends + dynamic render path (D-16, D-17)
- `dashboard_renderer/api.py` — `render_dashboard_as_str()` is the dynamic render entrypoint (no disk write); same function used by market-scoped pages
- `dashboard_renderer/components/paper_trades.py` — `render_paper_trades_region(state)` reads `state.get('paper_trades', [])` from top-level (D-18 scoping targets this key)
- `dashboard_renderer/stats.py` — `compute_*` functions read `state.get('equity_history', [])` from top-level (D-18 scoping targets this key)

### SC-5 Verification
- `.planning/phases/37-per-user-email-fan-out-admin-invite-disable-routes-invite-ac/37-VERIFICATION.md` — SC-5 gap definition; exactly what must be implemented and tested
- `tests/test_tenant_isolation.py` — `TestTenantIsolation.test_other_user_dashboard_has_no_user_a_trade_content` (line 164); fix targets `/account` URL (D-19); `two_user_client` fixture monkeypatches `load_state` with seeded state including `state['users'][uid_a]['paper_trades']`

### Daily orchestration
- `daily_run.py` — `run_daily_check(state)` return value shape; `per_user_fanout.run(state, run_date)` called from `main.py` after this
- `main.py` — call sequence; `per_user_fanout` called after `daily_run.run_daily_check` returns

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `notifier/dispatch.py::send_daily_email` — template for per-user email dispatch; `send_per_user_email(uid, user_state, shared_signals, now)` follows same SendStatus + never-raise pattern
- `notifier/transport.py::_post_to_resend` — reused for all Resend calls; `asyncio.Semaphore(2)` wraps each call in `per_user_fanout.py` to throttle
- `auth_store/_users.py::mint_invite_token` + `consume_and_create_user` — flock-guarded helpers already built in Phase 34; Phase 37 wires them to routes
- `web/routes/admin/__init__.py` — admin router already mounted with `require_admin` gate; new routes register on the same `router` instance and inherit the gate
- `web/routes/healthz.py::register(app)` — pattern for standalone health endpoint registration; `/healthz/last-cycle` follows this
- `web/routes/totp/__init__.py` — TOTP enrollment flow to reuse/mirror for the TOTP step of invite acceptance

### Established Patterns
- `SendStatus(ok, reason)` — all notifier dispatch functions return this; never raise
- `mutate_user_state(uid, fn)` — for persisting email pref changes from dashboard HTMX routes
- HTMX-only UI: no SPA, HTMX partials; forms submit via `hx-post`/`hx-patch`; admin page follows same HTMX pattern as dashboard
- `<input type="date">` is consistent with the existing date/date-range inputs in the dashboard
- `last_seen_date=None` on `PublicUserSummary` was deferred to Phase 37 — now populate from `auth_store` last-login field or session tracking

### Integration Points
- `main.py` — add `per_user_fanout.run(state, run_date)` call after `daily_run.run_daily_check()` returns
- `web/app.py::create_app()` — register new `/accept-invite` route (unauthenticated); add admin nav link
- `dashboard-settings.html` — insert email prefs section (toggle + date picker)
- `state["users"][uid]` — add `email_enabled` and `pause_until` fields (state schema version bump if needed)

### SC-5 Account Page Pattern (D-16/D-17)

The account page handler follows the same dynamic render pattern as `_serve_market_scoped_page` (lines 215–279 in `web/routes/dashboard/__init__.py`):
- `uid: str = Depends(_get_current_user_id)` on the route handler
- `full_state = state_manager.load_state()`
- Pre-filter: `scoped_state = {**full_state, 'paper_trades': ..., 'equity_history': ...}` from `full_state['users'][uid]`
- `render_dashboard_as_str(scoped_state, now=None, active_function='account')`
- Apply `_substitute()` for placeholder swap
- `Cache-Control: no-store, private` on response
- The `/dashboard-account.html` file alias route also needs the same treatment

</code_context>

<specifics>
## Specific Ideas

- **Admin summary email always fires** — send every cycle, not just on failure. Short format: "Cycle YYYY-MM-DD: 3/3 OK" or "Cycle YYYY-MM-DD: 2/3 OK — failed: uid=abc123 (KeyError in email prefs)". Makes anomalies visible passively without requiring log access.
- **Invite URL inline display** — after admin POSTs to issue invite, HTMX swap shows the full invite URL in a copy-able `<code>` block on the admin page. URL format: `https://{BASE_URL}/accept-invite?token={raw_token}`. Also emails the invitee via `send_invite_email`.
- **Error page for bad tokens** — dedicated simple HTML page, not a redirect to /login. Message includes admin contact info so invitee knows what to do.
- **`password_hash` deferred from Phase 34** — Phase 34 D-05 explicitly deferred this field. Phase 37 adds it to the `User` TypedDict and stores it during `consume_and_create_user` or the invite acceptance POST.
- **Pause-until semantics** — `today <= pause_until` means: paused on the pause-until date itself. Resume happens the day after. Fan-out checks `date.today()` in AWST (Sydney time) for consistency with the run schedule.
- **last_seen_date on PublicUserSummary** — was `None` in Phase 36. Phase 37 populates this from wherever last-login tracking lands (either `last_login` field on User row, or deferred again).

</specifics>

<deferred>
## Deferred Ideas

- **Public signup** — explicitly out of scope per REQUIREMENTS.md §Out-of-scope. Admin is sole invite issuer.
- **Bulk invite via CSV** — REQUIREMENTS.md §Out-of-scope for ≤dozens of users.
- **Terminal user delete** — deferred to v1.3.x per RBAC-04.
- **Per-domain email loaders** — not needed; `load_user_state(uid)` is sufficient.
- **Retry logic in fan-out per-user boundary** — fail-fast per user is acceptable; retry policy deferred to post-v1.3 ops hardening.

</deferred>

---

*Phase: 37-per-user-email-fan-out-admin-invite-disable-routes-invite-ac*
*Context gathered: 2026-05-14*
*SC-5 gap closure decisions added: 2026-05-14*
