# Phase 37: Per-User Email Fan-Out + Admin Invite/Disable Routes + Invite-Acceptance Flow - Research

**Researched:** 2026-05-14
**Domain:** Email fan-out orchestration, invite acceptance wizard, admin HTMX routes, password hashing
**Confidence:** HIGH (codebase verified) / MEDIUM (Resend rate limit, RFC 8058 format)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** F&F daily email has personal section (stop-loss alerts + paper P&L) + shared signal block.
- **D-02:** Admin existing daily email unchanged. Admin gets a separate end-of-cycle summary email.
- **D-03:** Admin end-of-cycle summary sent every cycle (not only on failure).
- **D-04:** Multi-step flow: GET /accept-invite?token=<raw> → (1) set password → (2) TOTP enrollment → (3) trusted device → (4) redirect to dashboard. Each step on its own page. No step skippable.
- **D-05:** Invite URL: /accept-invite?token=<raw_token>. hmac.compare_digest validation via Phase 34 consume_and_create_user flock path.
- **D-06:** password_hash field added to User TypedDict, stored in auth.json users[] row. Deferred from Phase 34 D-05.
- **D-07:** Expired/consumed token → dedicated error page (200 status, NOT redirect). Message: "This invite link has expired or has already been used. Contact the administrator for a new invite."
- **D-08:** GET /admin/users HTML page (HTMX-backed). Lists users + pending invites + issue-invite form.
- **D-09:** After admin issues invite: raw URL displayed inline + system emails invitee automatically via send_invite_email.
- **D-10:** Admin dashboard nav gets "Users" link (admin role only, matches require_admin gate).
- **D-11:** Email prefs (enable/disable toggle + pause-until date) in Settings section on dashboard (dashboard-settings.html anchor).
- **D-12:** Pause-until: HTML `<input type="date">` native picker. Fan-out checks pause_until field from per-user state.
- **D-13:** Per-user state fields: email_enabled (bool, default True), pause_until (ISO YYYY-MM-DD or null). Stored in state["users"][uid]. Fan-out skips if not email_enabled OR (pause_until is not None and today <= pause_until).
- **D-14:** per_user_fanout.py is top-level orchestrator (I/O layer, peer of daily_run.py). Called from main.py AFTER daily_run.run_daily_check() returns. All per-user alert updates batched in one terminal mutate_state call.
- **D-15:** /healthz/last-cycle: JSON {"status":"ok","cycle_date":"YYYY-MM-DD"|null,"users":[{"uid":...,"ok":bool,"reason":str|null}]}. Admin-gated. Added to admin router.

### Claude's Discretion

- Exact send_invite_email template content and subject line.
- Whether /admin/users HTML and existing JSON endpoint coexist at same path (Accept header) or JSON renamed to /admin/users/json.
- Where cycle outcomes persisted for /healthz/last-cycle (last_cycle key in state.json OR sidecar file).
- Password hashing algorithm (bcrypt or argon2 — research recommends bcrypt 5.0.0, see below).
- Exact UX of per-user error boundary in per_user_fanout.py (fail-fast per user per CONTEXT deferred section).
- How send_invite_email sends BASE_URL for invite link (BASE_URL env var — confirmed used in login/__init__.py).

### Deferred Ideas (OUT OF SCOPE)

- Public signup (explicitly out of scope).
- Bulk invite via CSV.
- Terminal user delete (deferred to v1.3.x per RBAC-04).
- Per-domain email loaders.
- Retry logic in fan-out per-user boundary (fail-fast per user is acceptable).
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RBAC-03 | Invite acceptance flow: set password, enrol TOTP, confirm trusted device | Session-backed wizard via itsdangerous URLSafeTimedSerializer (already in requirements.txt); consume_and_create_user (Phase 34) wires to /accept-invite route |
| UMAIL-01 | F&F user receives own 08:00 Sydney email with stop-loss alerts, paper P&L, shared signal block | per_user_fanout.py orchestrator; load_user_state(uid) + per-user crash boundary |
| UMAIL-02 | Per-user crash boundary; admin receives end-of-cycle summary; /healthz/last-cycle | try/except per user in asyncio.gather; last-cycle state in state.json["last_cycle"] key or sidecar |
| UMAIL-03 | asyncio.Semaphore(2) throttle; RFC 8058 List-Unsubscribe + List-Unsubscribe-Post headers | Semaphore wraps asyncio.to_thread(_post_to_resend); headers kwarg in Resend API payload |
| UMAIL-04 | User enable/disable email + pause-until-YYYY-MM-DD from dashboard; fan-out skips | email_enabled + pause_until in state["users"][uid]; PATCH /settings/email-prefs via mutate_user_state |
</phase_requirements>

---

## Summary

Phase 37 wires three connected capabilities on top of the Phases 34–36 foundation. The daily fan-out (`per_user_fanout.py`) calls `load_user_state(uid)` per user, builds a personalized email (personal section + shared signal block), and dispatches via `asyncio.Semaphore(2)` to throttle Resend calls below the 2 req/sec default rate limit — with each `_post_to_resend` call offloaded to a thread via `asyncio.to_thread` since the transport is synchronous. The W3 invariant (exactly two `mutate_state` saves per cycle) is preserved by batching all per-user alert-state updates into a single terminal `mutate_state` call after `asyncio.gather` completes.

The invite acceptance flow is a 3-step server-side wizard using `itsdangerous.URLSafeTimedSerializer` cookies (same library already in requirements.txt at 2.2.0) to carry step-state across full-page HTTP POSTs — no HTMX partials across steps. Password hashing uses `bcrypt` (v5.0.0, available in PyPI, not yet installed) rather than stdlib `hashlib.scrypt` because bcrypt's stored hash format (`$2b$...`) is self-describing with embedded cost factor, enabling future cost-factor migration without a schema change. The `consume_and_create_user` flock path from Phase 34 is extended to store `password_hash` in the User row.

The admin HTML page at `/admin/users` serves two concerns: JSON (existing Phase 36 endpoint) and HTML (new Phase 37). The recommended approach is Accept-header negotiation on the same path — FastAPI can inspect `request.headers.get("accept")` and return either `list[PublicUserSummary]` JSON or an HTMLResponse, keeping the URL stable for the startup invariant test.

**Primary recommendation:** Use `asyncio.to_thread(_post_to_resend, ...)` wrapped in `asyncio.Semaphore(2)` inside an `async` fan-out function called via `asyncio.run()` from the synchronous orchestrator; use bcrypt for password hashing; persist `/healthz/last-cycle` data as `state["last_cycle"]` in state.json (no sidecar).

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Per-user email fan-out | Orchestration (per_user_fanout.py) | Notifier (new dispatch functions) | Fan-out is I/O orchestration; email construction is notifier's domain |
| Admin invite HTML page | Web adapter (web/routes/admin/) | Auth store (mint_invite_token) | Route is a view; token minting is storage logic |
| Invite acceptance wizard | Web adapter (new web/routes/invite/) | Auth store (consume_and_create_user) | HTTP session tracking in web layer; atomic consume in auth store |
| Password hashing | Auth store (auth_store/_users.py) | — | Auth concerns belong in auth_store; no web import in auth_store |
| Email prefs HTMX endpoint | Web adapter (web/routes/dashboard/) | State manager (mutate_user_state) | HTMX mutation routes in dashboard routes; state write via mutate_user_state |
| /healthz/last-cycle | Web adapter (web/routes/admin/) | State manager (state["last_cycle"]) | Admin-gated monitoring endpoint on admin router |
| RFC 8058 headers | Notifier (transport or dispatch) | — | Email headers are notifier's transport concern |
| asyncio.Semaphore throttle | per_user_fanout.py | — | Throttle lives in the orchestrator, not in notifier (notifier is sync) |

---

## Standard Stack

### Core (already installed)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| itsdangerous | 2.2.0 [VERIFIED: requirements.txt] | Session-backed wizard cookies via URLSafeTimedSerializer | Already used for tsi_session, tsi_pending, tsi_enroll, tsi_trusted cookies in TOTP routes |
| FastAPI | 0.136.1 [VERIFIED: requirements.txt] | Route registration for /accept-invite, /admin/invites, PATCH /settings/email-prefs | Existing framework |
| pyotp | 2.9.0 [VERIFIED: requirements.txt] | TOTP enrollment step in invite wizard | Existing TOTP infrastructure |
| asyncio | stdlib [VERIFIED: .venv Python 3.13.13] | Semaphore + gather for fan-out throttle | stdlib — no new dep |
| hashlib | stdlib [VERIFIED: Python 3.13] | pbkdf2_hmac + scrypt available; bcrypt preferred (see below) | stdlib fallback available |

### New Dependencies to Install

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| bcrypt | 5.0.0 [VERIFIED: pip index versions] | Password hashing for invite acceptance | Self-describing stored format ($2b$12$...) with embedded cost factor; industry standard for 25+ years; allows cost-factor migration at login time without schema changes |

**Installation:**
```bash
.venv/bin/pip install bcrypt==5.0.0
```

Then add to `requirements.txt`:
```
bcrypt==5.0.0
```

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| bcrypt | hashlib.scrypt (stdlib) | scrypt is available (Python 3.13 verified, 35ms at n=16384,r=8,p=1) but stored format must be hand-crafted (no self-describing hash string); OWASP 2024 recommends Argon2id > scrypt > bcrypt for new systems, but bcrypt 5.0.0 has the same ubiquity + self-describing format advantage for a small-scale F&F app |
| bcrypt | argon2-cffi 25.1.0 | Argon2id is OWASP's 2024 top recommendation (memory-hard, GPU-resistant) but adds a new C-extension dep; at single-operator F&F scale the security difference vs bcrypt cost=12 is immaterial; bcrypt is simpler |
| Accept-header negotiation on /admin/users | Rename JSON endpoint to /admin/users/json | Accept negotiation keeps URL stable for startup invariant test and matches REST convention; renaming breaks existing test paths that hit /admin/users and assert JSON |
| state["last_cycle"] key | Sidecar file (e.g. last_cycle.json) | state.json key participates in the existing atomic write and migration chain; sidecar adds a second file that could go stale independently. State key is simpler and consistent with existing patterns (state["last_run"], etc.) |
| asyncio.to_thread(_post_to_resend) | Rewrite _post_to_resend as async | to_thread wraps the existing sync transport without any change to notifier; rewriting the transport is a separate concern that would touch tests, monkeypatches, and the never-raise contract |

---

## Architecture Patterns

### System Architecture Diagram

```
main.py
  └── daily_run.run_daily_check(state) → (rc, state, old_signals, run_date)
        [W3 mutate_state #1: daily run write]
  └── per_user_fanout.run(state, run_date)   ← NEW
        ├── load active F&F users from state["users"]
        ├── asyncio.run(_fan_out_all(users, state, run_date))
        │     asyncio.Semaphore(2)
        │     ┌── per user (asyncio.gather, return_exceptions=True):
        │     │     try:
        │     │       user_state = load_user_state(uid)
        │     │       check email_enabled + pause_until → skip if paused
        │     │       build personal section (alerts + paper P&L from user_state)
        │     │       build shared signal block (from state["signals"])
        │     │       asyncio.to_thread(send_per_user_email, uid, ...) [Semaphore(2)]
        │     │       record outcome: {uid, ok:True}
        │     │     except:
        │     │       record outcome: {uid, ok:False, reason:...}
        │     └── collect outcomes list
        ├── mutate_state: batch-write all per-user alert updates + state["last_cycle"]
        │     [W3 mutate_state #2: per-user fan-out terminal write]
        └── send_cycle_summary_email(admin_email, outcomes)  [NOT inside mutate_state]

Web routes (admin):
  GET  /admin/users        → HTML (Accept:text/html) OR JSON (Accept:application/json)
  POST /admin/invites      → mint_invite_token + send_invite_email; HTMX swap invite URL block
  DELETE /admin/invites/{token_hash} → revoke (mark consumed) pending invite
  PATCH /admin/users/{uid}/disable   → existing Phase 36 route (unchanged)
  GET  /admin/last-cycle   → {"status","cycle_date","users":[...]} from state["last_cycle"]

Web routes (accept-invite wizard — PUBLIC_PATHS):
  GET  /accept-invite?token=<raw>  → validate token; set tsi_invite_step cookie; render step 1
  POST /accept-invite              → validate password; bcrypt hash; extend cookie to step 2; render step 2 (enroll-totp)
  [reuse existing TOTP enroll + verify paths for step 2]
  POST /accept-invite/device       → set trust_device; clear invite cookie; redirect → /

Web routes (dashboard):
  PATCH /settings/email-prefs  → mutate_user_state(uid, set email_enabled + pause_until)
```

### Recommended Project Structure — New Files

```
per_user_fanout.py            # new top-level orchestrator (I/O layer peer of daily_run.py)
web/routes/invite/
  __init__.py                 # GET+POST /accept-invite, POST /accept-invite/device
  _renderers.py               # HTML render helpers for wizard steps 1, 3, error page
notifier/dispatch.py          # extend: send_per_user_email, send_invite_email, send_cycle_summary_email
notifier/__init__.py          # add new dispatch functions to re-export list
auth_store/_schema.py         # add password_hash: str | None to User TypedDict
auth_store/_users.py          # extend consume_and_create_user to store password_hash
web/routes/admin/__init__.py  # extend: HTML /admin/users, POST /admin/invites, DELETE /admin/invites/{hash}, GET /admin/last-cycle
web/routes/admin/_models.py   # add PendingInviteSummary; extend PublicUserSummary with last_seen_date
web/middleware/auth.py        # add /accept-invite to PUBLIC_PATHS
web/app.py                    # register invite route; ensure /accept-invite in PUBLIC_PATHS
state_manager/migrations.py   # v12→v13 if state schema bumps (email_enabled, pause_until, last_cycle)
system_params.py              # add FANOUT_SEMAPHORE_LIMIT = 2 constant
```

### Pattern 1: asyncio.Semaphore(2) with to_thread for sync transport

**What:** Fan-out wraps each synchronous `_post_to_resend` call in `asyncio.to_thread` so the semaphore gates actual thread creation, throttling to ≤2 concurrent Resend HTTPS calls.

**When to use:** Any point where a sync blocking function (requests.post with time.sleep retry) must be throttled in an async context.

**Example:**
```python
# Source: asyncio stdlib docs + verified locally (Python 3.13.13)
import asyncio

FANOUT_SEMAPHORE_LIMIT = 2  # from system_params — Resend default 2 req/sec

async def _send_one(sem: asyncio.Semaphore, uid: str, send_fn, *args) -> dict:
  '''Per-user crash boundary + semaphore throttle.'''
  try:
    async with sem:
      result = await asyncio.to_thread(send_fn, *args)
    return {'uid': uid, 'ok': result.ok, 'reason': result.reason}
  except Exception as exc:  # noqa: BLE001 — never-crash, per-user boundary
    return {'uid': uid, 'ok': False, 'reason': f'{type(exc).__name__}: {exc}'[:200]}

async def _fan_out_all(users: list, state: dict, run_date: str) -> list[dict]:
  sem = asyncio.Semaphore(FANOUT_SEMAPHORE_LIMIT)
  tasks = [_send_one(sem, uid, send_per_user_email, uid, ...) for uid in users]
  return await asyncio.gather(*tasks, return_exceptions=False)
  # return_exceptions=False: each task catches its own exceptions internally
  # so gather never sees an exception; all outcomes are dicts

def run(state: dict, run_date: str) -> list[dict]:
  '''Synchronous entry point called from main.py.'''
  outcomes = asyncio.run(_fan_out_all(active_users, state, run_date))
  # W3 invariant: batch-write all per-user alert updates + last_cycle in ONE mutate_state
  def _batch_write(s):
    for outcome in outcomes:
      # apply per-user alert state updates...
      pass
    s['last_cycle'] = {'date': run_date, 'users': outcomes}
  mutate_state(_batch_write)
  return outcomes
```

### Pattern 2: bcrypt password hash storage

**What:** Store `bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12))` result as a `str` in `User["password_hash"]`. Verify with `bcrypt.checkpw(candidate.encode(), stored_hash.encode())`.

**When to use:** `consume_and_create_user` (invite acceptance step 1 POST handler stores hash); login verification (out of scope for Phase 37 — admin still uses WEB_AUTH_SECRET+TOTP).

**Example:**
```python
# Source: bcrypt 5.0.0 PyPI docs [VERIFIED: pip index versions bcrypt -> 5.0.0]
import bcrypt

def hash_password(plaintext: str) -> str:
  '''Returns a str suitable for storage in auth.json User["password_hash"].
  $2b$12$ prefix: algorithm=bcrypt, version=2b, rounds=12 (OWASP minimum).
  '''
  return bcrypt.hashpw(plaintext.encode('utf-8'), bcrypt.gensalt(rounds=12)).decode('utf-8')

def verify_password(plaintext: str, stored_hash: str) -> bool:
  '''Timing-safe check. Returns False on any exception (fail-closed).'''
  try:
    return bcrypt.checkpw(plaintext.encode('utf-8'), stored_hash.encode('utf-8'))
  except Exception:
    return False
```

### Pattern 3: RFC 8058 List-Unsubscribe headers in Resend payload

**What:** Add `headers` dict to the Resend JSON payload. Two headers required: `List-Unsubscribe` (HTTPS URL) and `List-Unsubscribe-Post` (literal value `List-Unsubscribe=One-Click`).

**When to use:** Every per-user F&F email via `send_per_user_email`. NOT required on admin daily email, crash email, magic link email (those are transactional, not bulk).

**Exact format** [CITED: datatracker.ietf.org/doc/html/rfc8058]:
```python
# Source: RFC 8058 + Resend API docs (headers field confirmed supported)
headers_for_resend = {
  'List-Unsubscribe': f'<{BASE_URL}/settings/email-prefs?uid={uid}&token={unsubscribe_token}>',
  'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click',
}
# Add to Resend payload:
payload['headers'] = headers_for_resend
```

**Note on unsubscribe URL:** UMAIL-03 requires "no session token, no invite token, and no other secret appears in the email body or URLs." The unsubscribe URL may include a UID-scoped HMAC token (not a session token). Simplest acceptable approach: route the user to `/settings` (authenticated settings page) with no token in URL — clicking the unsubscribe link takes them to the settings page where they can disable email. The `List-Unsubscribe` header just needs an HTTPS URL; it does NOT need to be a one-click endpoint (the `List-Unsubscribe-Post` header makes Google/Apple try POST to the URL, but if the endpoint is the authenticated settings page it will redirect to login — acceptable for F&F scale).

### Pattern 4: Session-backed invite wizard with itsdangerous

**What:** Carry wizard step state in a signed cookie (not server-side session store). Each wizard step reads the cookie, validates it, then sets a new cookie with updated state. Full-page HTTP redirects between steps (no HTMX partials).

**When to use:** Multi-step flows where step N must verify step N-1 completed; no database session store available; existing cookie pattern (tsi_enroll, tsi_pending) already demonstrates this in the TOTP flow.

**Example:**
```python
# Source: existing web/routes/totp/__init__.py pattern (itsdangerous 2.2.0)
# Mirror the tsi_enroll cookie pattern for the invite wizard cookie
INVITE_WIZARD_SALT = 'tsi-invite-wizard'
WIZARD_COOKIE_MAX_AGE = 3600  # 1 hour to complete all 3 steps

invite_wizard_serializer = URLSafeTimedSerializer(secret, salt=INVITE_WIZARD_SALT)

# Step 1 GET: validate token, set cookie with step='password'
payload = {'step': 'password', 'uid': new_uid, 'email': email}
cookie_val = invite_wizard_serializer.dumps(payload)
response.set_cookie('tsi_invite_wizard', cookie_val, max_age=WIZARD_COOKIE_MAX_AGE,
                    httponly=True, secure=True, samesite='Strict')

# Step 2 POST (password submit): read cookie, verify step=='password', hash pw,
# update cookie to step='totp', redirect to TOTP enroll
payload = invite_wizard_serializer.loads(cookie_val, max_age=WIZARD_COOKIE_MAX_AGE)
assert payload['step'] == 'password'
# ... store password_hash in auth.json via consume_and_create_user_with_password ...
# set new cookie with step='totp'
```

### Pattern 5: Accept-header negotiation for /admin/users (HTML vs JSON)

**What:** Single FastAPI route handler inspects `request.headers.get("accept", "")` and returns HTMLResponse or JSON based on content type.

**When to use:** When the same URL must serve both HTMX page loads (Accept: text/html) and existing API consumers (Accept: application/json).

**Example:**
```python
# Source: FastAPI Request docs [ASSUMED — pattern consistent with FastAPI design]
from fastapi import Request
from fastapi.responses import HTMLResponse

@router.get('/users')
def admin_list_users(request: Request):
  users = _build_summaries()  # same logic as before
  if 'text/html' in request.headers.get('accept', ''):
    return HTMLResponse(_render_admin_users_page(users, pending_invites))
  return users  # FastAPI serializes list[PublicUserSummary] as JSON
```

### Anti-Patterns to Avoid

- **Calling mutate_state inside asyncio.gather tasks:** Each task runs in a thread via to_thread; calling mutate_state from a thread while another thread holds the flock causes non-reentrant deadlock. Batch ALL state writes into a single post-gather mutate_state call in the synchronous `run()` entry point.
- **Calling per_user_fanout.run() before daily_run.run_daily_check() saves state:** The W3 #1 mutate_state must complete first so fan-out reads the post-run state. Order in main.py: `run_daily_check()` → `_dispatch_email_and_maintain_warnings()` → `per_user_fanout.run()`.
- **Storing raw invite token in the email body:** Only the BASE_URL + raw token should appear in the invite email body. The raw token is not a session token, but log it carefully. After consume_and_create_user runs, the token is single-use.
- **Adding /accept-invite to the admin router:** The invite acceptance wizard must be reachable by unauthenticated invitees. It belongs on the application root (not admin_router), registered before add_middleware, and added to PUBLIC_PATHS.
- **Using asyncio.Semaphore outside asyncio context:** asyncio.Semaphore must be created and used within an async function (inside asyncio.run). Creating it at module level and using it from sync code will raise RuntimeError.
- **Writing last_cycle to state.json via save_state directly:** Use mutate_state (flock-guarded). Direct save_state bypasses the lock and can corrupt state.json under concurrent web writes.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Password hashing | Custom salting + SHA-256 | bcrypt 5.0.0 | Timing attacks, GPU cracking, work-factor tuning, stored-hash format |
| Timing-safe token comparison | `==` string comparison | hmac.compare_digest (already in auth_store/_users.py) | Timing oracle allows token enumeration |
| Multi-step wizard state | localStorage or URL params | itsdangerous URLSafeTimedSerializer cookie (already used in TOTP flow) | Signed cookies prevent client-side tampering; already installed |
| Async HTTP throttling | sleep(1/N) between calls | asyncio.Semaphore(2) + asyncio.gather | Semaphore correctly limits concurrency, not throughput; sleep is a bottleneck |
| RFC 8058 unsubscribe endpoint | Custom unsubscribe handler | Redirect to /settings (authenticated settings page) | UMAIL-03 disallows secrets in URL; settings page handles toggle; Gmail/Apple accept redirects to login |
| Invite URL construction | Manual f-string with url parts | os.environ.get('BASE_URL') (same pattern as magic-link in login/__init__.py) | BASE_URL already established env var; login route uses the same pattern |

**Key insight:** The project already has 80% of this infrastructure — itsdangerous cookies (TOTP flow), hmac.compare_digest (auth_store), BASE_URL env var (magic link), flock-guarded atomic writes (state_manager + auth_store). Phase 37 wires these together rather than building new primitives.

---

## Common Pitfalls

### Pitfall 1: W3 invariant broken by per-user mutate_state calls

**What goes wrong:** Per-user alert state updates written inside individual asyncio tasks (one mutate_state per user) result in N+2 mutate_state calls instead of exactly 2 (W3 invariant).

**Why it happens:** It seems natural to update each user's state as their email is sent. But the W3 invariant requires exactly two mutate_state calls per cycle.

**How to avoid:** Collect all per-user state mutations into a closure inside `_fan_out_all` and apply them in a single `mutate_state` call in the synchronous `run()` function after `asyncio.run(_fan_out_all(...))` returns.

**Warning signs:** W3 regression test (`test_mutate_state_call_count`) fails; or `grep -n "mutate_state"` in per_user_fanout.py shows more than one call site.

### Pitfall 2: Resend 429 from Semaphore(2) at retry time

**What goes wrong:** `asyncio.Semaphore(2)` limits to 2 concurrent calls, but `_post_to_resend` has a 10s flat backoff on retry. If 2 tasks both hit 429 simultaneously, they retry in parallel — still within the semaphore limit — potentially re-429ing.

**Why it happens:** Semaphore controls concurrency, not rate over time. A burst of 2 calls in the same millisecond fires 2 req at once (fine for 2 req/sec). But the retry backoff is `time.sleep(10)` in a thread (via to_thread), so the semaphore slot is held for 10s during the sleep — which actually helps because it prevents other tasks from acquiring the slot during backoff.

**How to avoid:** The existing `_post_to_resend` retry+backoff is already 429-safe when wrapped in to_thread (the thread sleep holds the semaphore slot, preventing new concurrent sends during backoff). Verify that `Semaphore(2)` is acquired BEFORE `to_thread()` call (not inside the coroutine that calls to_thread — the slot must be held for the full thread duration including backoff).

**Warning signs:** 429 errors in the admin cycle summary email listing multiple users with the same timestamp.

### Pitfall 3: Cookie not cleared after wizard abandonment

**What goes wrong:** An invitee starts the wizard, closes the browser at step 2, then clicks the invite link again. The old `tsi_invite_wizard` cookie from their browser persists and puts them at step 2 (TOTP), but `consume_and_create_user` already ran (at step 1 POST). The token is consumed and the user row exists, but they're stuck at step 2 with no way to restart.

**Why it happens:** The invite token is consumed in step 1 (when password is set), but the wizard cookie persists across browser sessions.

**How to avoid:** Step 1 POST creates the user row with `password_hash` but marks the TOTP as NOT yet enrolled (existing `mark_enrolled` pattern). If the invitee returns to `/accept-invite?token=<same_raw>`, they get the "already consumed" error page (D-07). But if they return to `/accept-invite` (no token, just have the step-2 cookie) — the route should detect the cookie at step 2 and resume from there. Cookie max_age=3600 is the abandonment TTL.

**Warning signs:** InviteAlreadyConsumed raised on second visit to the invite URL.

### Pitfall 4: Per-user email content leaks shared admin data

**What goes wrong:** `send_per_user_email` accidentally includes admin-only fields from the shared state dict (e.g. admin's open positions, admin's account balance).

**Why it happens:** The personal section renders from `user_state = load_user_state(uid)` — this is correct. The risk is if the template passes the full `state` dict and a template bug renders `state["users"][admin_uid]` fields.

**How to avoid:** `send_per_user_email` must accept ONLY `(uid, user_state: dict, shared_signals: dict, run_date: str)`. The shared_signals dict is constructed from `state["signals"]` before passing — never pass the full state dict into per-user email dispatch.

**Warning signs:** TestTenantIsolation fails; admin account balance appears in F&F email body.

### Pitfall 5: password_hash on User TypedDict breaks existing auth.json reads

**What goes wrong:** Adding `password_hash: str | None` to the `User` TypedDict and to `consume_and_create_user` without backfilling the existing admin user row causes a KeyError in code that reads `user["password_hash"]`.

**Why it happens:** The admin user was bootstrapped without `password_hash` (Phase 34 D-05 deferred it).

**How to avoid:** Use `.get("password_hash")` everywhere password_hash is read. The TypedDict declares `str | None` — the existing admin row simply has no key (reads as `None` via `.get`). Do NOT add a migration that writes `password_hash: null` to the admin row (admin login bypasses password).

**Warning signs:** KeyError on `user["password_hash"]` in any code path that reads User rows (especially admin login check).

### Pitfall 6: asyncio.run() inside an existing event loop

**What goes wrong:** If `per_user_fanout.run()` is ever called from a context that already has a running event loop (e.g. a FastAPI route or test with pytest-asyncio), `asyncio.run()` raises `RuntimeError: This event loop is already running`.

**Why it happens:** `asyncio.run()` creates a new event loop; calling it inside an existing loop is illegal.

**How to avoid:** `per_user_fanout.run()` is called only from `main.py` in the synchronous orchestration context — never from a FastAPI route. Document this constraint. For tests, call `asyncio.run(_fan_out_all(...))` directly in sync test functions (no pytest-asyncio needed).

**Warning signs:** `RuntimeError: This event loop is already running` in logs.

---

## Code Examples

### RFC 8058 exact header format

```python
# Source: RFC 8058 §3 [CITED: datatracker.ietf.org/doc/html/rfc8058]
# Source: Resend API docs — headers field [CITED: resend.com/docs/api-reference/emails/send-batch-emails]
payload['headers'] = {
  'List-Unsubscribe': '<https://signals.mwiriadi.me/settings>',
  'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click',
}
# Note: 'List-Unsubscribe=One-Click' is a LITERAL string value — exact casing required.
# The HTTPS URL must be an absolute URL (not relative).
# DKIM must cover these headers — Resend handles DKIM signing automatically.
```

### email.utils.formataddr for Unicode display names

```python
# Source: Python stdlib email.utils docs [ASSUMED — stdlib since Python 2.x]
from email.utils import formataddr
# Correct RFC 2047 encoding for Unicode names:
from_field = formataddr(('Trading Signals', 'signals@domain.com'))
# → 'Trading Signals <signals@domain.com>'

# Unicode name (e.g. F&F user "Müller"):
to_field = formataddr(('Müller', 'muller@example.com'))
# → '=?utf-8?q?M=C3=BCller?= <muller@example.com>'
# This is what Resend expects in the 'from' display name field.
# Pass the formatted string to the 'from' key in Resend payload.
```

### bcrypt password hash + verify

```python
# Source: bcrypt 5.0.0 PyPI [ASSUMED — standard bcrypt API, stable across versions]
import bcrypt

def hash_password(plaintext: str) -> str:
  salt = bcrypt.gensalt(rounds=12)  # $2b$12$ prefix — OWASP minimum rounds
  return bcrypt.hashpw(plaintext.encode('utf-8'), salt).decode('utf-8')

def verify_password(plaintext: str, stored: str) -> bool:
  try:
    return bcrypt.checkpw(plaintext.encode('utf-8'), stored.encode('utf-8'))
  except Exception:
    return False  # fail-closed
```

### Resend batch API (alternative to per-call for N users)

```python
# Source: resend.com/docs/api-reference/emails/send-batch-emails [CITED]
# POST https://api.resend.com/emails/batch
# Accepts array of up to 100 email objects. Each object is identical to single send.
# Does NOT guarantee rate limit relief — counts as N requests toward rate limit.
# Attachment and scheduled_at fields NOT supported in batch.
# For Phase 37: batch API is NOT recommended — Semaphore(2) per-call provides
# better per-user crash isolation and honors the 2 req/sec limit naturally.
```

### W3 invariant batch write pattern

```python
# Source: state_manager/__init__.py mutate_state pattern [VERIFIED: codebase]
def _batch_apply(state: dict) -> None:
  '''Collect ALL per-user alert updates + last_cycle in one mutate_state.'''
  for outcome in outcomes:
    uid = outcome['uid']
    if uid in state.get('users', {}):
      user = state['users'][uid]
      # apply alert state changes accumulated during fan-out
      user['email_prefs_last_result'] = outcome.get('ok')
  state['last_cycle'] = {
    'date': run_date,
    'users': outcomes,
  }

mutate_state(_batch_apply)  # W3 mutate_state #2 — exactly one call
```

---

## State Schema Impact

### Does Phase 37 require a schema version bump?

**Analysis:** Phase 37 adds `email_enabled` and `pause_until` to `state["users"][uid]`, and adds `state["last_cycle"]`. The current schema is v12 [VERIFIED: system_params.py line 280].

**Recommendation:** Bump to v13 with `_migrate_v12_to_v13` that:
1. For each existing user in `state["users"]`, adds `email_enabled: True` and `pause_until: null` (idempotent backfill).
2. Adds `state["last_cycle"] = None` at top level.

**Migration contiguity guard:** `_assert_migration_chain_contiguous()` fires at every `load_state()` call — the v13 key MUST be in MIGRATIONS dict before any test or production run after the bump.

**Alternative (no bump):** Use `.get("email_enabled", True)` and `.get("pause_until")` everywhere — no migration needed. Simpler, avoids the contiguity gate risk. **Recommended** for Phase 37 since the fields have safe defaults (True = send email, None = no pause). This is consistent with how Phase 33 v12 fields work with `.get()` in the fan-out code.

**Decision for planner:** The no-bump approach (`.get()` with defaults) is recommended to avoid migration complexity and the contiguity gate chain. The `state["last_cycle"]` field also does not require a migration — it starts as absent (None when `.get("last_cycle")` is called) and is written by the first fan-out run.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.13 | All | ✓ | 3.13.13 [VERIFIED: .venv/bin/python --version] | — |
| itsdangerous | Invite wizard cookies | ✓ | 2.2.0 [VERIFIED: requirements.txt] | — |
| bcrypt | Password hashing | ✗ (not installed) | 5.0.0 available [VERIFIED: pip index] | hashlib.scrypt (stdlib, but no self-describing format) |
| asyncio | Fan-out semaphore | ✓ | stdlib (Python 3.13) | — |
| hashlib.pbkdf2_hmac | Alt password hash | ✓ | stdlib [VERIFIED: .venv python -c] | — |
| hashlib.scrypt | Alt password hash | ✓ | stdlib [VERIFIED: .venv python -c, 35ms at n=16384] | — |
| BASE_URL env var | Invite email URL | Pattern confirmed [VERIFIED: web/routes/login/__init__.py line 210] | — | No fallback — skip invite email if BASE_URL unset (same pattern as magic-link) |
| Resend API | Email dispatch | ✓ (existing) | — | last_email.html fallback (existing pattern) |

**Missing dependencies with no fallback:**
- bcrypt must be installed (`pip install bcrypt==5.0.0`) before Wave 0 tests can pass.

**Missing dependencies with fallback:**
- BASE_URL not set → skip invite email dispatch (log ERROR, return SendStatus(ok=False, reason='missing_base_url')), same as magic-link pattern.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.3.3 [VERIFIED: requirements.txt] |
| Config file | none — inferred from conftest.py |
| Quick run command | `.venv/bin/pytest -x --tb=short tests/test_per_user_fanout.py tests/test_web_admin.py tests/test_web_invite.py tests/test_auth_store_users.py` |
| Full suite command | `.venv/bin/pytest -x --tb=short` |
| Current test count | 2218 collected [VERIFIED: pytest --collect-only] |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| UMAIL-01 | F&F email dispatched with personal section + shared signal block | unit | `pytest tests/test_per_user_fanout.py::TestFanOutEmail -x` | ❌ Wave 0 |
| UMAIL-02 | Per-user crash boundary: one failure doesn't abort others | unit | `pytest tests/test_per_user_fanout.py::TestCrashBoundary -x` | ❌ Wave 0 |
| UMAIL-02 | W3 invariant: exactly 2 mutate_state calls per cycle | unit | `pytest tests/test_per_user_fanout.py::TestW3Invariant -x` | ❌ Wave 0 |
| UMAIL-02 | /healthz/last-cycle returns per-user outcomes | unit | `pytest tests/test_web_admin.py::TestLastCycle -x` | Partial (file exists, test class needed) |
| UMAIL-03 | asyncio.Semaphore(2) throttle: 50-user mock ≤ 30s, no 429 | performance | `pytest tests/test_per_user_fanout.py::TestSemaphoreThrottle -x` | ❌ Wave 0 |
| UMAIL-03 | RFC 8058 List-Unsubscribe + List-Unsubscribe-Post headers present | unit | `pytest tests/test_per_user_fanout.py::TestRFC8058Headers -x` | ❌ Wave 0 |
| UMAIL-04 | Fan-out skips paused/disabled users | unit | `pytest tests/test_per_user_fanout.py::TestEmailPrefsSkip -x` | ❌ Wave 0 |
| UMAIL-04 | PATCH /settings/email-prefs persists email_enabled + pause_until | unit | `pytest tests/test_web_dashboard_email_prefs.py -x` | ❌ Wave 0 |
| RBAC-03 | Invite acceptance step 1: password validated + hashed | unit | `pytest tests/test_web_invite.py::TestStep1Password -x` | ❌ Wave 0 |
| RBAC-03 | Invite acceptance step 2: TOTP enrollment (reuse existing TOTP tests) | unit | `pytest tests/test_web_totp.py -x` | ✅ exists |
| RBAC-03 | Invite acceptance step 3: trusted device cookie set | unit | `pytest tests/test_web_invite.py::TestStep3Device -x` | ❌ Wave 0 |
| RBAC-03 | Expired/consumed token → error page (200 status, no redirect) | unit | `pytest tests/test_web_invite.py::TestExpiredToken -x` | ❌ Wave 0 |
| RBAC-04 (ext) | POST /admin/invites mints token + sends email | unit | `pytest tests/test_web_admin.py::TestAdminInviteIssue -x` | Partial |
| RBAC-04 (ext) | DELETE /admin/invites/{hash} revokes invite | unit | `pytest tests/test_web_admin.py::TestAdminInviteRevoke -x` | Partial |

### Key Test Patterns

**W3 invariant test:**
```python
# tests/test_per_user_fanout.py
def test_w3_invariant_exactly_two_mutate_state_calls(monkeypatch, tmp_path):
  call_count = []
  def _counting_mutate_state(fn, path=None):
    call_count.append(1)
    state = {}
    fn(state)
    return state
  monkeypatch.setattr('per_user_fanout.mutate_state', _counting_mutate_state)
  # also patch daily_run's mutate_state to count
  per_user_fanout.run(state={'users': {'u1': {}}}, run_date='2026-05-14')
  assert len(call_count) == 1  # only per_user_fanout.run's terminal call
  # W3 #1 (daily_run) is counted separately in test_main.py::TestW3Invariant
```

**Semaphore throttle performance test (50 users, ≤30s):**
```python
# tests/test_per_user_fanout.py::TestSemaphoreThrottle
import time, asyncio
def test_50_user_mock_completes_within_30s(monkeypatch):
  sent = []
  def _mock_send(uid, *args, **kwargs):
    sent.append(uid)
    time.sleep(0.01)  # 10ms simulated Resend latency
    from notifier.transport import SendStatus
    return SendStatus(ok=True, reason=None)
  monkeypatch.setattr('per_user_fanout.send_per_user_email', _mock_send)
  users = [{'uid': f'u{i}', 'email_enabled': True, 'pause_until': None} for i in range(50)]
  start = time.time()
  outcomes = asyncio.run(per_user_fanout._fan_out_all(users, {}, '2026-05-14'))
  elapsed = time.time() - start
  assert elapsed < 30, f'fan-out too slow: {elapsed:.1f}s'
  assert len([o for o in outcomes if o['ok']]) == 50
```

**RFC 8058 headers presence test:**
```python
# tests/test_per_user_fanout.py::TestRFC8058Headers
def test_per_user_email_includes_rfc8058_headers(monkeypatch):
  captured = {}
  def _mock_post(api_key, from_addr, to_addr, subject, html_body=None, **kwargs):
    captured['payload'] = kwargs.get('headers', {})
  monkeypatch.setattr('notifier.transport._post_to_resend', _mock_post)
  # ... call send_per_user_email ...
  assert 'List-Unsubscribe' in captured['payload']
  assert captured['payload']['List-Unsubscribe-Post'] == 'List-Unsubscribe=One-Click'
```

**Email prefs skip test:**
```python
# tests/test_per_user_fanout.py::TestEmailPrefsSkip
def test_fan_out_skips_disabled_user(monkeypatch):
  sent_uids = []
  def _mock_send(uid, *args): sent_uids.append(uid)
  monkeypatch.setattr('per_user_fanout.send_per_user_email', _mock_send)
  users = [
    {'uid': 'active', 'email': 'a@x.com', 'email_enabled': True, 'pause_until': None},
    {'uid': 'disabled', 'email': 'b@x.com', 'email_enabled': False, 'pause_until': None},
    {'uid': 'paused', 'email': 'c@x.com', 'email_enabled': True, 'pause_until': '2099-12-31'},
  ]
  asyncio.run(per_user_fanout._fan_out_all(users, {}, '2026-05-14'))
  assert 'active' in sent_uids
  assert 'disabled' not in sent_uids
  assert 'paused' not in sent_uids
```

### Sampling Rate

- **Per task commit:** `.venv/bin/pytest -x --tb=short tests/test_per_user_fanout.py tests/test_web_admin.py tests/test_web_invite.py`
- **Per wave merge:** `.venv/bin/pytest -x --tb=short`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_per_user_fanout.py` — covers UMAIL-01, UMAIL-02, UMAIL-03, UMAIL-04 (W3 invariant, crash boundary, RFC 8058, semaphore perf, skip logic)
- [ ] `tests/test_web_invite.py` — covers RBAC-03 (all 3 wizard steps, expired token, password validation, bcrypt verify)
- [ ] `tests/test_web_dashboard_email_prefs.py` — covers UMAIL-04 (PATCH /settings/email-prefs, mutate_user_state wiring)
- [ ] `bcrypt==5.0.0` install: `.venv/bin/pip install bcrypt==5.0.0` + add to requirements.txt

*(If no gaps: "None — existing test infrastructure covers all phase requirements")*

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | bcrypt (password hashing, invite acceptance); existing TOTP/cookie for ongoing sessions |
| V3 Session Management | yes | itsdangerous URLSafeTimedSerializer cookies for wizard steps; max_age=3600; HttpOnly; Secure; SameSite=Strict |
| V4 Access Control | yes | require_admin gate on all admin routes; per-user uid scoping on email prefs route |
| V5 Input Validation | yes | password minlength=12 (server-side); date field validated as ISO string; email validated before invite mint |
| V6 Cryptography | yes | bcrypt for passwords; hmac.compare_digest for token verify (Phase 34); secrets.token_urlsafe(32) for invite tokens |

### Known Threat Patterns for This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Invite token brute force | Tampering | secrets.token_urlsafe(32) = 256 bits entropy; single-use flock guarantee (Phase 34) |
| Password weak hash (MD5/SHA-1) | Information Disclosure | bcrypt cost=12 — 150ms per verify, impractical for GPU cracking |
| Session fixation in wizard | Elevation of Privilege | Set new cookie on every step transition (don't reuse step 1 cookie at step 3) |
| Secret in invite email body | Information Disclosure | UMAIL-03: only raw token in URL (not session token); token consumed on first use |
| /accept-invite auth bypass | Elevation of Privilege | /accept-invite in PUBLIC_PATHS is intentional (invitee has no session); token itself is the auth |
| Email prefs CSRF | Tampering | hx-headers with WEB_AUTH_SECRET on all HTMX mutations (existing dashboard pattern) |
| Admin invite revoke race | Tampering | hmac.compare_digest on token_hash lookup; revoke sets consumed=True via save_auth (no flock needed for revoke — concurrent revoke has same safe outcome) |
| Unicode display name injection in email | Tampering | email.utils.formataddr handles RFC 2047 encoding; html.escape on all values in HTML email body |

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| 2 req/sec Resend rate limit | 5 req/sec (per newer changelog) but 2 req/sec per rate-limit page | As of Resend changelog 2024 [CITED: resend.com/changelog/api-rate-limit] | Use 2 req/sec as conservative Semaphore(2) default; can bump if account is newer |
| Batch email send not in Resend | Batch endpoint available: POST /emails/batch, up to 100 per call | Announced by Resend [CITED: resend.com/blog/introducing-the-batch-emails-api] | Batch is NOT recommended for Phase 37 — per-call Semaphore gives better crash isolation |
| bcrypt as sole OWASP recommendation | Argon2id now top OWASP 2024 recommendation | OWASP 2024 | Argon2id is the modern standard; bcrypt is still OWASP-approved for existing systems; either is acceptable |

**Deprecated/outdated:**
- `time.sleep(N)` for Resend rate limiting: do not use as a substitute for Semaphore — sleep blocks the calling thread and doesn't limit concurrency.

---

## Claude's Discretion Recommendations

### Where to persist /healthz/last-cycle data

**Recommendation: `state["last_cycle"]` key in state.json** (not a sidecar file).

Rationale: state.json already participates in atomic writes and is the single source of truth. A sidecar `last_cycle.json` would require a second atomic write path and could go stale independently. The `last_cycle` key is written once per cycle inside the W3 #2 `mutate_state` call. The admin endpoint reads it via `load_state()["last_cycle"]`.

### /admin/users HTML vs JSON coexistence

**Recommendation: Accept-header negotiation on same path.**

Rationale: The startup invariant test (`test_admin_routes_have_require_admin_dependency`) walks `app.routes` and checks `/admin/*` paths — having two paths (`/admin/users` and `/admin/users/json`) means updating the test. Single-path negotiation keeps the route count stable. FastAPI's `response_class` parameter can be omitted; the handler returns either HTMLResponse or the list depending on Accept header.

### Password hashing algorithm

**Recommendation: bcrypt 5.0.0** (not argon2-cffi).

Rationale: bcrypt is already the industry standard for this type of app (small, infrequent logins). The self-describing `$2b$12$...` stored hash format means future cost-factor bumps happen at verify time without a schema migration. argon2-cffi is better for high-frequency login systems under GPU attack; at F&F scale (≤dozens of users, infrequent login) the difference is immaterial.

### Retry logic in per-user fanout error boundary

**Recommendation: fail-fast per user** (no retry within a cycle, consistent with CONTEXT.md deferred items).

Rationale: Admin receives the cycle summary email listing which users failed. Operator can trigger a manual re-run for failed users. Retry within the cycle risks exceeding the 2 req/sec rate limit and extends cycle duration.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Accept-header negotiation FastAPI pattern inspects `request.headers.get("accept", "")` — returns HTMLResponse for text/html, JSON for application/json | Architecture Patterns §5 | Low: FastAPI supports this natively; worst case is a simple content-type check adjustment |
| A2 | Resend rate limit is 2 req/sec for this account (older account) | Standard Stack note, Semaphore(2) | If 5 req/sec, Semaphore(2) is more conservative than needed — safe, not broken |
| A3 | bcrypt 5.0.0 API (`hashpw`, `checkpw`, `gensalt`) is stable (same as bcrypt 4.x) | Code Examples | Low: bcrypt API has been stable for 10+ years; 5.0.0 changelog doesn't change these |
| A4 | `state["last_cycle"]` key does not require a schema version bump (uses .get() with None default) | State Schema Impact | Low: if a validator enforces strict schema shape, a bump to v13 is needed — planner decides |
| A5 | email.utils.formataddr correctly MIME-encodes Unicode display names for Resend payload | Code Examples | Low: stdlib behavior since Python 2.x; Resend accepts RFC 2047 names in `from` field |

---

## Open Questions (RESOLVED)

1. **Resend rate limit: 2 or 5 req/sec for this account?** — **RESOLVED**
   - What we know: Resend changelog says 2 req/sec default; rate-limit docs page says 5 req/sec. Discrepancy is likely account age (changelog was from when Resend first introduced limits at 2 req/sec; newer accounts may be 5 req/sec).
   - What's unclear: Which applies to `signals.mwiriadi.me` account.
   - **Resolution:** Use 2 req/sec — `FANOUT_SEMAPHORE_LIMIT = 2` is locked in `system_params.py` (Plan 02 Task 1). Operator may bump to 5 after verifying live behavior on the current Resend account. Semaphore(2) is safe in both cases. See Plan 02 §interfaces.

2. **Should the wizard step 2 reuse the existing `/enroll-totp` route or duplicate it?** — **RESOLVED**
   - What we know: The existing `/enroll-totp` route requires a `tsi_pending` cookie (set by login). The invite wizard needs a different cookie (`tsi_invite_wizard`).
   - What's unclear: Whether `_render_enroll_page` can be called standalone or requires the pending cookie.
   - **Resolution:** Reuse the existing `/enroll-totp` route via a `tsi_enroll` cookie handoff — no duplicate route. Plan 04 Task 1 Step 5 issues a freshly-signed `tsi_enroll` cookie at step-1 POST (alongside the wizard cookie transition to `step='totp'`) and 302-redirects to `/enroll-totp`. The existing TOTP enroll flow proceeds unchanged. Plan 04 Task 1 Step 10 wires the TOTP success boundary back to the wizard (`step='totp'` → `step='device'`).

3. **last_seen_date population for PublicUserSummary (deferred from Phase 36)** — **RESOLVED**
   - What we know: `update_last_seen` is called in `web/middleware/auth.py` on `tsi_trusted` cookie path only (line 287). The `TrustedDevice` row has a `last_seen: str` field.
   - What's unclear: Whether `last_seen_date` on PublicUserSummary should reflect the trusted device's last_seen (requires scanning all devices for the user) or a dedicated `last_login` field on the User row.
   - **Resolution:** Populate `last_seen_date` from `trusted_devices[-1].last_seen` per user row (or `max(d.last_seen for d in user.trusted_devices)`), or `None` if the user has no trusted devices. Date-only (YYYY-MM-DD) granularity. No schema change. Implemented in Plan 05 Task 1 Step 2 via `_compute_last_seen_date(uid, trusted_devices_for_user)` helper.

---

## Sources

### Primary (HIGH confidence)

- `notifier/dispatch.py` — send_daily_email, send_crash_email patterns (never-raise, SendStatus)
- `notifier/transport.py` — _post_to_resend, Semaphore wrapping target, RFC 8058 header injection point
- `auth_store/_users.py` — consume_and_create_user flock window, User TypedDict extension point
- `auth_store/_schema.py` — current User TypedDict, SCHEMA_VERSION=2, PendingInvite TypedDict
- `web/routes/totp/__init__.py` — itsdangerous URLSafeTimedSerializer cookie pattern for wizard
- `web/routes/admin/__init__.py` — admin router mount, existing /admin/users JSON endpoint
- `web/middleware/auth.py` — PUBLIC_PATHS, update_last_seen location, tsi_trusted cookie path
- `web/app.py` — create_app() registration order, BASE_URL env var pattern confirmed
- `state_manager/__init__.py` — mutate_state, mutate_user_state, W3 invariant pattern, load_user_state
- `state_manager/migrations.py` — v12 user bucket shape, migration chain, contiguity guard
- `system_params.py` — INVITE_TOKEN_TTL_DAYS=7, STATE_SCHEMA_VERSION=12
- [VERIFIED: .venv/bin/python --version] — Python 3.13.13
- [VERIFIED: requirements.txt] — itsdangerous 2.2.0, bcrypt NOT present, fastapi 0.136.1
- [VERIFIED: pip index versions bcrypt] — bcrypt 5.0.0 available
- [VERIFIED: .venv python -c hashlib] — hashlib.scrypt + hashlib.pbkdf2_hmac available in stdlib
- [VERIFIED: asyncio.run test] — asyncio.Semaphore(2) + gather pattern works in Python 3.13

### Secondary (MEDIUM confidence)

- [CITED: resend.com/docs/api-reference/rate-limit] — "5 requests per second per team" (current page)
- [CITED: resend.com/changelog/api-rate-limit] — "2 requests per second" (original announcement)
- [CITED: datatracker.ietf.org/doc/html/rfc8058] — RFC 8058 exact header format + List-Unsubscribe-Post literal value
- [CITED: resend.com/docs/api-reference/emails/send-batch-emails] — Batch API exists, headers field supported, up to 100 per call

### Tertiary (LOW confidence — assumptions flagged)

- [ASSUMED] — Accept-header negotiation FastAPI pattern (A1)
- [ASSUMED] — email.utils.formataddr behavior for Unicode names in Resend from field (A5)

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries verified against codebase + pip registry
- Architecture: HIGH — derived directly from existing code patterns (TOTP flow, mutate_state, admin router)
- Pitfalls: HIGH — derived from actual codebase patterns (W3 invariant, flock semantics, tenant isolation)
- Resend rate limit: MEDIUM — two conflicting official Resend pages; conservative 2 req/sec is safe

**Research date:** 2026-05-14
**Valid until:** 2026-06-14 (Resend rate limit claim may change — verify before locking Semaphore constant)
