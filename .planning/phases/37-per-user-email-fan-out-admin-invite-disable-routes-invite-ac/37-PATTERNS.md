# Phase 37: Per-User Email Fan-Out + Admin Invite/Disable Routes + Invite-Acceptance Flow - Pattern Map

**Mapped:** 2026-05-14
**Files analyzed:** 12 new/modified files
**Analogs found:** 12 / 12

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `per_user_fanout.py` | orchestrator | batch + event-driven | `daily_loop.py` + `crash_boundary.py` | role-match |
| `notifier/dispatch.py` | service | request-response | `notifier/dispatch.py` itself (extend) | exact |
| `auth_store/_schema.py` | model | transform | `auth_store/_schema.py` itself (extend) | exact |
| `auth_store/_users.py` | service | CRUD | `auth_store/_users.py` itself (extend) | exact |
| `web/routes/admin/__init__.py` | controller | request-response | `web/routes/admin/__init__.py` itself (extend) | exact |
| `web/routes/invite/__init__.py` | controller | request-response | `web/routes/totp/__init__.py` | exact |
| `web/routes/invite/_renderers.py` | utility | transform | `web/routes/totp/_renderers.py` (sibling pattern) | role-match |
| `web/routes/dashboard/__init__.py` | controller | request-response | `web/routes/dashboard/__init__.py` itself (extend) | exact |
| `web/middleware/auth.py` | middleware | request-response | `web/middleware/auth.py` itself (extend) | exact |
| `web/app.py` | config | request-response | `web/app.py` itself (extend) | exact |
| `state_manager/migrations.py` | utility | transform | `state_manager/migrations.py` itself (extend, if bump needed) | exact |
| `system_params.py` | config | — | `system_params.py` itself (extend) | exact |

---

## Pattern Assignments

### `per_user_fanout.py` (orchestrator, batch)

**Analog:** `daily_loop.py` (orchestration seam), `crash_boundary.py` (never-crash dispatch)

**Imports pattern** — mirror `daily_loop.py` top-of-file:
```python
# per_user_fanout.py — top-level orchestrator, peer of daily_run.py
import asyncio
import logging
from datetime import date
from zoneinfo import ZoneInfo

from state_manager import mutate_state, load_user_state
from notifier.dispatch import send_per_user_email, send_cycle_summary_email
from system_params import FANOUT_SEMAPHORE_LIMIT  # add to system_params.py

logger = logging.getLogger(__name__)
_AWST = ZoneInfo('Australia/Perth')
```

**Core async fan-out pattern** (from RESEARCH.md Pattern 1 + `crash_boundary.py` never-crash):
```python
async def _send_one(sem: asyncio.Semaphore, uid: str, user_row: dict,
                    shared_signals: dict, run_date: str) -> dict:
  '''Per-user crash boundary + semaphore throttle. NEVER raises.'''
  try:
    async with sem:
      # email_enabled / pause_until skip check (D-13)
      email_enabled = user_row.get('email_enabled', True)
      pause_until = user_row.get('pause_until')
      today = date.today()           # AWST date from run_date arg preferred
      if not email_enabled:
        return {'uid': uid, 'ok': True, 'reason': 'skipped:disabled'}
      if pause_until is not None and today <= date.fromisoformat(pause_until):
        return {'uid': uid, 'ok': True, 'reason': 'skipped:paused'}
      user_state = load_user_state(uid)
      # Construct shared_signals from state["signals"] before passing (Pitfall 4)
      result = await asyncio.to_thread(
        send_per_user_email, uid, user_state, shared_signals, run_date,
      )
    return {'uid': uid, 'ok': result.ok, 'reason': result.reason}
  except Exception as exc:  # noqa: BLE001 — never-crash per-user boundary
    return {'uid': uid, 'ok': False, 'reason': f'{type(exc).__name__}: {exc}'[:200]}


async def _fan_out_all(users: list[dict], shared_signals: dict, run_date: str) -> list[dict]:
  sem = asyncio.Semaphore(FANOUT_SEMAPHORE_LIMIT)
  tasks = [
    _send_one(sem, u['uid'], u, shared_signals, run_date)
    for u in users
  ]
  return await asyncio.gather(*tasks, return_exceptions=False)


def run(state: dict, run_date: str) -> list[dict]:
  '''Synchronous entry point called from main.py after daily_run returns.

  W3 invariant: ONE terminal mutate_state call here is the W3 #2 write.
  Do NOT call mutate_state inside asyncio tasks (Pitfall: anti-pattern note
  in RESEARCH.md — flock deadlock from thread context).
  '''
  from auth_store import list_users
  # Build per-user list from auth.json; filter active + role==ff
  all_users = list_users()
  users_map = state.get('users', {})
  active_ff = [
    {**u, **users_map.get(u['uid'], {})}
    for u in all_users
    if u.get('role') == 'ff' and not u.get('disabled')
  ]
  shared_signals = {k: v for k, v in state.get('signals', {}).items()}

  outcomes = asyncio.run(_fan_out_all(active_ff, shared_signals, run_date))

  # W3 #2: batch ALL state mutations in a single mutate_state call
  def _batch_write(s: dict) -> None:
    s['last_cycle'] = {'date': run_date, 'users': outcomes}
  mutate_state(_batch_write)

  # Admin cycle summary — AFTER mutate_state, NOT inside it
  send_cycle_summary_email(outcomes, run_date)
  return outcomes
```

**Call site in `main.py`** (after `_dispatch_email_and_maintain_warnings`):
```python
# Add AFTER daily_run imports at top of main.py re-export block:
import per_user_fanout  # noqa: F401 — main.per_user_fanout monkeypatch path

# In the --force-email / default dispatch ladder, after:
#   _dispatch_email_and_maintain_warnings(state, old_signals, run_date, ...)
# add:
if rc == 0 and state is not None and run_date is not None:
    per_user_fanout.run(state, run_date.strftime('%Y-%m-%d'))
```

**Anti-patterns flagged in RESEARCH.md:**
- Do NOT call `mutate_state` inside `asyncio.gather` tasks.
- Do NOT call `per_user_fanout.run()` from a FastAPI route (asyncio.run inside event loop → RuntimeError).
- Do NOT pass full `state` dict to `send_per_user_email` — construct `shared_signals` slice first.

---

### `notifier/dispatch.py` — add `send_per_user_email`, `send_invite_email`, `send_cycle_summary_email`

**Analog:** `notifier/dispatch.py` lines 77–180 (`send_daily_email`), lines 286–360 (`send_magic_link_email`)

**Never-raise dispatch function template** (lines 77–180):
```python
def send_per_user_email(
  uid: str,
  user_state: dict,
  shared_signals: dict,
  run_date: str,
) -> SendStatus:
  '''NEVER raises. Returns SendStatus on every path.

  RFC 8058: List-Unsubscribe + List-Unsubscribe-Post headers on every call.
  Only pass uid, user_state, shared_signals — never the full state dict (Pitfall 4).
  '''
  from_addr = os.environ.get('SIGNALS_EMAIL_FROM', '').strip()
  if not from_addr:
    logger.error('[Email] SIGNALS_EMAIL_FROM not set — per-user email skipped uid=%s', uid)
    return SendStatus(ok=False, reason='missing_sender')
  api_key = os.environ.get('RESEND_API_KEY')
  if not api_key:
    logger.warning('[Email] WARN per-user: RESEND_API_KEY missing uid=%s', uid)
    return SendStatus(ok=True, reason='no_api_key')
  to_addr = user_state.get('email') or ''        # user_state carries email field
  if not to_addr:
    return SendStatus(ok=False, reason='missing_recipient')
  try:
    subject = f'Trading Signals — {run_date}'
    html_body = _render_per_user_email_html(uid, user_state, shared_signals, run_date)
    base_url = os.environ.get('BASE_URL', '').strip()
    extra_headers = {
      'List-Unsubscribe': f'<{base_url}/settings>',          # authenticated settings page
      'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click', # RFC 8058 literal
    }
    _post_to_resend(
      api_key, from_addr, to_addr, subject, html_body,
      extra_headers=extra_headers,              # see transport.py note below
    )
    logger.info('[Email] per-user sent uid=%s to=%s', uid, to_addr)
    return SendStatus(ok=True, reason=None)
  except ResendError as e:
    logger.warning('[Email] WARN per-user failed uid=%s: %s', uid, e)
    return SendStatus(ok=False, reason=str(e)[:200])
  except Exception as e:   # noqa: BLE001 — CLAUDE.md never-crash
    logger.warning('[Email] WARN per-user unexpected uid=%s: %s: %s', uid, type(e).__name__, e)
    return SendStatus(ok=False, reason=f'{type(e).__name__}: {e}'[:200])
```

**`send_invite_email` pattern** (mirrors `send_magic_link_email`, lines 286–360):
```python
def send_invite_email(to_email: str, invite_url: str) -> SendStatus:
  '''Send invite URL to invitee. NEVER raises.

  BASE_URL env var pattern: confirmed at web/routes/login/__init__.py line 210.
  Returns SendStatus(ok=False, reason='missing_base_url') if BASE_URL unset.
  '''
  from_addr = os.environ.get('SIGNALS_EMAIL_FROM', '').strip()
  if not from_addr:
    logger.error('[Email] SIGNALS_EMAIL_FROM not set — invite email skipped')
    return SendStatus(ok=False, reason='missing_sender')
  api_key = os.environ.get('RESEND_API_KEY')
  if not api_key:
    logger.warning('[Email] WARN invite: RESEND_API_KEY missing')
    return SendStatus(ok=False, reason='no_api_key')
  subject = "You're invited to Trading Signals"
  html_body = _render_invite_email_html(invite_url)
  try:
    _post_to_resend(api_key, from_addr, to_email, subject, html_body)
    logger.info('[Email] invite sent to=%s', to_email)
    return SendStatus(ok=True, reason=None)
  except ResendError as e:
    logger.warning('[Email] WARN invite failed: %s', e)
    return SendStatus(ok=False, reason=str(e)[:200])
  except Exception as e:   # noqa: BLE001
    logger.warning('[Email] WARN invite unexpected: %s: %s', type(e).__name__, e)
    return SendStatus(ok=False, reason=f'{type(e).__name__}: {e}'[:200])
```

**`send_cycle_summary_email` pattern** (mirrors `send_crash_email`, text/plain body):
```python
def send_cycle_summary_email(outcomes: list[dict], run_date: str) -> SendStatus:
  '''Admin end-of-cycle summary. Sent EVERY cycle (D-03). NEVER raises.'''
  from_addr = os.environ.get('SIGNALS_EMAIL_FROM', '').strip()
  if not from_addr:
    return SendStatus(ok=False, reason='missing_sender')
  to_addr = _resolve_email_to_or_skip(state=None, context='send_cycle_summary_email')
  if to_addr is None:
    return SendStatus(ok=False, reason='missing_recipient')
  api_key = os.environ.get('RESEND_API_KEY')
  if not api_key:
    return SendStatus(ok=False, reason='no_api_key')
  ok_count = sum(1 for o in outcomes if o.get('ok'))
  total = len(outcomes)
  failed = [o for o in outcomes if not o.get('ok')]
  subject = f'[Cycle {run_date}] {ok_count}/{total} OK'
  lines = [f'Cycle {run_date}: {ok_count}/{total} users OK']
  for o in failed:
    lines.append(f"  FAILED uid={o['uid']}: {o.get('reason', 'unknown')}")
  text_body = '\n'.join(lines) + '\n'
  try:
    _post_to_resend(api_key, from_addr, to_addr, subject,
                    html_body=None, text_body=text_body)
    return SendStatus(ok=True, reason=None)
  except ResendError as e:
    logger.warning('[Email] WARN cycle-summary failed: %s', e)
    return SendStatus(ok=False, reason=str(e)[:200])
  except Exception as e:   # noqa: BLE001
    logger.warning('[Email] WARN cycle-summary unexpected: %s: %s', type(e).__name__, e)
    return SendStatus(ok=False, reason=f'{type(e).__name__}: {e}'[:200])
```

**RFC 8058 header injection note:** `_post_to_resend` (transport.py lines 177–278) builds `payload` dict then POSTs. To pass extra headers, either:
- Add `extra_headers: dict | None = None` param to `_post_to_resend` and merge into `payload['headers']`
- OR build the `payload['headers']` key inside `send_per_user_email` and pass the full extended payload (requires a separate `_post_to_resend_with_payload` helper, less preferred)

The simpler approach: add `email_headers: dict | None = None` kwarg to `_post_to_resend` (transport.py line 177) and set `payload['headers'] = email_headers` when provided. All existing callers pass nothing — no regression.

**Monkeypatch parity:** new dispatch functions must use the late-bound `_post_to_resend` proxy pattern (lines 51–54 of dispatch.py), NOT `from .transport import _post_to_resend` directly:
```python
# Copy this pattern for every new function in dispatch.py:
def _post_to_resend(*args, **kwargs):
  import notifier as _pkg  # noqa: PLC0415
  return _pkg._post_to_resend(*args, **kwargs)
```
The proxy already exists at lines 51–54 — all new functions share it.

**Re-export:** Add new names to `notifier/__init__.py` re-export list.

---

### `auth_store/_schema.py` — add `password_hash` to `User` TypedDict

**Analog:** `auth_store/_schema.py` lines 49–57 (current `User` TypedDict)

**Current User TypedDict** (lines 49–57):
```python
class User(TypedDict):
  uid: str
  email: str
  role: str
  created_at: str
  disabled: bool
```

**Phase 37 extension** — add `password_hash`:
```python
class User(TypedDict):
  uid: str
  email: str
  role: str
  created_at: str
  disabled: bool
  password_hash: str | None   # Phase 37 D-06; None for admin (bypasses pw auth)
```

**Critical:** Every read of `user["password_hash"]` must use `.get("password_hash")` (not `user["password_hash"]`) because existing admin row has no key. Pitfall 5 in RESEARCH.md.

**Schema version:** No bump to v3 required — use `.get()` with `None` default everywhere (RESEARCH.md §State Schema Impact recommendation). `_normalize_v2` in `_schema.py` does NOT need updating.

---

### `auth_store/_users.py` — extend `consume_and_create_user` to store `password_hash`

**Analog:** `auth_store/_users.py` lines 201–281 (full `consume_and_create_user`)

**Current new_user construction** (lines 266–273):
```python
new_user = {
  'uid': uuid.uuid4().hex,
  'email': email,
  'role': role,
  'created_at': datetime.now(timezone.utc).isoformat(),
  'disabled': False,
}
```

**Phase 37 extension** — add `password_hash` param and store:
```python
def consume_and_create_user(
  unhashed_token: str,
  new_user_fields: dict,
  password_hash: str | None = None,   # Phase 37 D-06; None preserves backward compat
  path: Path | None = None,
) -> dict:
  ...
  # Inside the flock window, after matched_row is found and validated:
  new_user = {
    'uid': uuid.uuid4().hex,
    'email': email,
    'role': role,
    'created_at': datetime.now(timezone.utc).isoformat(),
    'disabled': False,
    'password_hash': password_hash,  # None for legacy callers; str for invite wizard
  }
```

**Add bcrypt helpers** (new module-private functions in `_users.py`):
```python
# Phase 37 D-06: password hashing helpers
# bcrypt must be installed: .venv/bin/pip install bcrypt==5.0.0
import bcrypt as _bcrypt

def hash_password(plaintext: str) -> str:
  '''Returns $2b$12$... stored hash. OWASP minimum rounds=12.'''
  return _bcrypt.hashpw(plaintext.encode('utf-8'), _bcrypt.gensalt(rounds=12)).decode('utf-8')

def verify_password(plaintext: str, stored_hash: str) -> bool:
  '''Timing-safe check. Fail-closed on any exception.'''
  try:
    return _bcrypt.checkpw(plaintext.encode('utf-8'), stored_hash.encode('utf-8'))
  except Exception:
    return False
```

**Re-export from `auth_store/__init__.py`:**
```python
from auth_store._users import hash_password, verify_password  # add to __init__.py
```

---

### `web/routes/admin/__init__.py` — add HTML /admin/users, invite routes, /admin/last-cycle

**Analog:** `web/routes/admin/__init__.py` lines 1–72 (existing router)

**Existing router pattern** (lines 14–19):
```python
from fastapi import APIRouter, Depends, HTTPException
from web.dependencies import require_admin
from web.routes.admin._models import PublicUserSummary

router = APIRouter(prefix='/admin', dependencies=[Depends(require_admin)])
```

**All new routes inherit `require_admin` automatically** — register on `router`, not `application`.

**Accept-header negotiation for GET /admin/users** (RESEARCH.md Pattern 5):
```python
@router.get('/users')
def admin_list_users(request: Request):
  '''Phase 36 JSON + Phase 37 HTML via Accept-header negotiation.

  text/html → HTMLResponse with admin-users.html template
  application/json → list[PublicUserSummary] (existing Phase 36 behaviour)
  '''
  from auth_store import list_users
  from state_manager import load_state
  state = load_state()
  users_map = state.get('users', {})
  # ... build summaries (same as existing lines 42-55) ...
  if 'text/html' in request.headers.get('accept', ''):
    from auth_store import list_pending_invites  # new helper needed in _users.py
    pending = list_pending_invites()
    html = _render_admin_users_page(summaries, pending)
    return HTMLResponse(content=html)
  return summaries  # FastAPI serialises list[PublicUserSummary] as JSON
```

**POST /admin/invites** (HTMX — inline invite URL display + send email):
```python
@router.post('/invites')
def admin_issue_invite(
  request: Request,
  email: str = Form(...),
  admin_uid: str = Depends(require_admin),
):
  from auth_store import mint_invite_token
  from notifier.dispatch import send_invite_email
  import os
  base_url = os.environ.get('BASE_URL', '').strip()
  if not base_url:
    raise HTTPException(status_code=500, detail='BASE_URL not configured')
  raw_token, expires_at = mint_invite_token(invited_by_uid=admin_uid, email=email)
  invite_url = f'{base_url}/accept-invite?token={raw_token}'
  send_invite_email(to_email=email, invite_url=invite_url)  # never-raise
  # HTMX response: inline code block with URL (D-09)
  return HTMLResponse(content=_render_invite_url_fragment(invite_url, email, expires_at))
```

**DELETE /admin/invites/{token_hash}** (revoke):
```python
@router.delete('/invites/{token_hash}')
def admin_revoke_invite(token_hash: str):
  from auth_store import revoke_invite  # new helper needed
  found = revoke_invite(token_hash)
  if not found:
    raise HTTPException(status_code=404, detail='invite not found')
  return {'ok': True, 'token_hash': token_hash}
```

**GET /admin/last-cycle** (D-15):
```python
@router.get('/last-cycle')
def admin_last_cycle():
  from state_manager import load_state
  state = load_state()
  lc = state.get('last_cycle')
  if lc is None:
    return {'status': 'ok', 'cycle_date': None, 'users': []}
  return {'status': 'ok', 'cycle_date': lc.get('date'), 'users': lc.get('users', [])}
```

**Import additions for the file:**
```python
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from web.dependencies import require_admin
from web.routes.admin._models import PublicUserSummary
```

---

### `web/routes/invite/__init__.py` (NEW — multi-step acceptance wizard)

**Analog:** `web/routes/totp/__init__.py` lines 1–292 (itsdangerous cookie wizard pattern)

**Structure — mirror totp exactly:**
```python
'''Phase 37 D-04/D-05 — invite acceptance wizard (public route).

3-step flow: GET /accept-invite?token=<raw> → password → TOTP enroll → trust device → /
Must be registered on `application` (not admin_router) and added to PUBLIC_PATHS.
'''
import logging
import os
import time

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, Response
from itsdangerous import BadSignature, SignatureExpired
from itsdangerous.url_safe import URLSafeTimedSerializer

logger = logging.getLogger(__name__)

INVITE_WIZARD_SALT = 'tsi-invite-wizard'
_WIZARD_COOKIE_MAX_AGE = 3600  # 1 hour to complete all steps (Pitfall 3 TTL)
_COOKIE_ATTRS_WIZARD = '; Path=/; Secure; HttpOnly; SameSite=Strict'
_COOKIE_ATTRS_DELETE = '; Max-Age=0; Path=/; Secure; HttpOnly; SameSite=Strict'


def register(app: FastAPI) -> None:
  secret = os.environ.get('WEB_AUTH_SECRET', '').strip()
  wizard_serializer = URLSafeTimedSerializer(secret, salt=INVITE_WIZARD_SALT)

  def _validate_wizard_cookie(request: Request) -> dict | None:
    '''Mirror of _validate_enroll_cookie in totp/__init__.py lines 55-66.'''
    token = request.cookies.get('tsi_invite_wizard')
    if not token:
      return None
    try:
      return wizard_serializer.loads(token, max_age=_WIZARD_COOKIE_MAX_AGE)
    except (SignatureExpired, BadSignature):
      return None

  @app.get('/accept-invite')
  def get_accept_invite(request: Request, token: str = '') -> Response:
    '''D-05: validate raw token → consume → create user → set wizard cookie step 1.
    D-07: expired/consumed → 200 error page (not redirect).
    '''
    if not token:
      return HTMLResponse(content=_render_invite_error_page(), status_code=200)
    from auth_store import consume_and_create_user, InviteAlreadyConsumed, InviteExpired
    # Check if wizard cookie already at step >=2 (Pitfall 3: resume path)
    wizard_payload = _validate_wizard_cookie(request)
    if wizard_payload and wizard_payload.get('step') in ('totp', 'device'):
      # Resume wizard at current step
      return _redirect_to_wizard_step(wizard_payload['step'])
    try:
      # Step 1: validate + consume + create user (no password_hash yet — stored at POST)
      # Actually: consume_and_create_user called at POST step 1 when pw is known.
      # GET only validates token is valid (peek) — consume at POST.
      # Per D-04: GET validates, sets step='password' cookie, renders form.
      from auth_store import _peek_invite_token  # new helper: validate without consuming
      email = _peek_invite_token(token)  # raises InviteAlreadyConsumed / InviteExpired
    except (InviteAlreadyConsumed, InviteExpired):
      return HTMLResponse(content=_render_invite_error_page(), status_code=200)
    payload = {'step': 'password', 'raw_token': token, 'email': email}
    cookie_val = wizard_serializer.dumps(payload)
    resp = HTMLResponse(content=_render_step1_password_page(email))
    resp.raw_headers.append((
      b'set-cookie',
      f'tsi_invite_wizard={cookie_val}; Max-Age={_WIZARD_COOKIE_MAX_AGE}{_COOKIE_ATTRS_WIZARD}'.encode('latin-1'),
    ))
    return resp

  @app.post('/accept-invite')
  def post_accept_invite(
    request: Request,
    password: str = Form(...),
    password_confirm: str = Form(...),
  ) -> Response:
    '''Step 1 POST: validate password → bcrypt hash → consume token → create user → step 2.'''
    wizard_payload = _validate_wizard_cookie(request)
    if wizard_payload is None or wizard_payload.get('step') != 'password':
      return Response(status_code=302, headers={'Location': '/login'})
    if password != password_confirm or len(password) < 12:
      email = wizard_payload.get('email', '')
      return HTMLResponse(content=_render_step1_password_page(
        email, error='Passwords must match and be at least 12 characters.',
      ))
    from auth_store import consume_and_create_user, hash_password, InviteAlreadyConsumed, InviteExpired
    raw_token = wizard_payload.get('raw_token', '')
    email = wizard_payload.get('email', '')
    pw_hash = hash_password(password)
    try:
      new_user = consume_and_create_user(
        raw_token, {'email': email, 'role': 'ff'}, password_hash=pw_hash,
      )
    except (InviteAlreadyConsumed, InviteExpired):
      return HTMLResponse(content=_render_invite_error_page(), status_code=200)
    uid = new_user['uid']
    # Step 2 cookie: TOTP enroll — reuse existing enroll path
    new_payload = {'step': 'totp', 'uid': uid, 'email': email}
    cookie_val = wizard_serializer.dumps(new_payload)
    # Issue tsi_enroll cookie so /enroll-totp route accepts this user
    # (enroll_serializer lives in totp/__init__.py — alternative: duplicate logic here)
    resp = Response(status_code=302, headers={'Location': '/enroll-totp'})
    for sc in [
      f'tsi_invite_wizard={cookie_val}; Max-Age={_WIZARD_COOKIE_MAX_AGE}{_COOKIE_ATTRS_WIZARD}',
      f'tsi_enroll=...{_COOKIE_ATTRS_WIZARD}',  # issue enroll cookie for totp route
    ]:
      resp.raw_headers.append((b'set-cookie', sc.encode('latin-1')))
    return resp

  @app.post('/accept-invite/device')
  def post_invite_device(
    request: Request,
    trust_device: str = Form(default=''),
  ) -> Response:
    '''Step 3: trust device confirmation → clear wizard cookie → redirect to /.'''
    wizard_payload = _validate_wizard_cookie(request)
    if wizard_payload is None or wizard_payload.get('step') != 'device':
      return Response(status_code=302, headers={'Location': '/login'})
    # TODO: issue tsi_trusted cookie if trust_device == 'on' (mirror post_verify lines 261-281 in totp/__init__.py)
    resp = Response(status_code=302, headers={'Location': '/'})
    resp.raw_headers.append((
      b'set-cookie',
      f'tsi_invite_wizard={_COOKIE_ATTRS_DELETE}'.encode('latin-1'),
    ))
    return resp

__all__ = ['register']
```

**Open question from RESEARCH.md Q2:** Whether step 2 reuses `/enroll-totp` or is inlined. Recommended: inspect `_render_enroll_page` in `web/routes/totp/_renderers.py` — if it is a pure render helper, call it from the invite wizard route with a separate `tsi_enroll` cookie issued at step 1 POST. This is consistent with the existing pattern where `post_enroll` in totp/__init__.py issues a fresh enroll cookie for the `?reset=1` flow (lines 170–179).

---

### `web/routes/dashboard/__init__.py` — add PATCH /settings/email-prefs

**Analog:** `web/routes/dashboard/__init__.py` — existing HTMX handlers registered via `register(app)` closure

**Pattern:** Register new HTMX endpoint inside `register(app)` closure, same as existing handlers:
```python
@app.patch('/settings/email-prefs')
def patch_email_prefs(
  request: Request,
  email_enabled: str = Form(default='on'),   # checkbox: 'on' or absent
  pause_until: str = Form(default=''),
  uid: str = Depends(current_user_id),
) -> Response:
  '''UMAIL-04: persist email_enabled + pause_until to state["users"][uid].

  Uses mutate_user_state (per-user flock outer + state.json inner) per Phase 36 pattern.
  Returns HTMX-compatible fragment for swap.
  '''
  from state_manager import mutate_user_state
  enabled_bool = (email_enabled == 'on')
  pause_date = pause_until.strip() or None
  # Validate pause_until is a valid ISO date if provided
  if pause_date:
    try:
      from datetime import date
      date.fromisoformat(pause_date)
    except ValueError:
      pause_date = None

  def _apply(state: dict) -> None:
    users = state.setdefault('users', {})
    bucket = users.setdefault(uid, {})
    bucket['email_enabled'] = enabled_bool
    bucket['pause_until'] = pause_date

  mutate_user_state(uid, _apply)
  return HTMLResponse(content='<p>Email preferences saved.</p>')
```

**Import additions inside register()** (local import pattern per Phase 11 C-2):
```python
from web.dependencies import current_user_id
# ^ Add to imports at top of file (it's already used in the dependency pattern)
```

---

### `web/middleware/auth.py` — add `/accept-invite` to `PUBLIC_PATHS`

**Analog:** `web/middleware/auth.py` lines 66–69 (`PUBLIC_PATHS` frozenset)

**Current PUBLIC_PATHS** (lines 66–69):
```python
PUBLIC_PATHS = frozenset({
  '/login', '/logout', '/enroll-totp', '/verify-totp',
  '/forgot-2fa', '/reset-totp',
})
```

**Phase 37 extension:**
```python
PUBLIC_PATHS = frozenset({
  '/login', '/logout', '/enroll-totp', '/verify-totp',
  '/forgot-2fa', '/reset-totp',
  '/accept-invite',          # Phase 37 D-04: unauthenticated invitee wizard
})
```

Note: `/accept-invite/device` (POST step 3) is gated by `tsi_invite_wizard` cookie validated inside the handler — it is correctly added to PUBLIC_PATHS too (the wizard cookie is the auth mechanism). The middleware's PUBLIC_PATHS check is path-prefix or exact-match — verify the middleware comparison logic to ensure `/accept-invite/device` is also covered or add it explicitly.

---

### `web/app.py` — register invite route + admin nav

**Analog:** `web/app.py` lines 131–229 (`create_app()`)

**Route registration pattern** (lines 188–213):
```python
# Add to imports at top of web/app.py:
from web.routes import invite as invite_route  # Phase 37

# Inside create_app(), BEFORE add_middleware (line 218), AFTER login_route:
invite_route.register(application)   # Phase 37 D-04: /accept-invite wizard (public)
```

**Registration order constraint:** `/accept-invite` must be registered BEFORE `add_middleware(AuthMiddleware, ...)` — same rule as all other PUBLIC_PATHS routes (e.g., login_route at line 190, reset_route at line 198).

---

### `auth_store/_schema.py` + `auth_store/_users.py` — `list_pending_invites`, `revoke_invite`, `_peek_invite_token`

New helpers needed by admin routes and invite wizard (not yet in codebase):

**`list_pending_invites`** (in `_users.py`, follow `list_users` at line 150):
```python
def list_pending_invites(path: Path | None = None) -> list:
  '''Return all PendingInvite rows (consumed + active).'''
  return load_auth(path=path).get('pending_invites', [])
```

**`revoke_invite`** (in `_users.py`, no flock per D-01):
```python
def revoke_invite(token_hash: str, path: Path | None = None) -> bool:
  '''Mark a pending invite as consumed. Returns False if not found.'''
  data = load_auth(path=path)
  for row in data.get('pending_invites', []):
    if row.get('token_hash') == token_hash and not row.get('consumed'):
      row['consumed'] = True
      row['consumed_at'] = datetime.now(timezone.utc).isoformat()
      save_auth(data, path=path)
      return True
  return False
```

**`_peek_invite_token`** (in `_users.py` — validate without consuming, for GET /accept-invite):
```python
def _peek_invite_token(unhashed_token: str, path: Path | None = None) -> str:
  '''Validate invite token and return email WITHOUT consuming.
  Raises InviteAlreadyConsumed or InviteExpired.
  '''
  data = load_auth(path=path)
  data = _normalize_v2(data)
  for row in data.get('pending_invites', []):
    if _verify_token(unhashed_token, row.get('token_hash', '')):
      if row.get('consumed'):
        raise InviteAlreadyConsumed('already consumed')
      try:
        expires_dt = _ensure_aware(datetime.fromisoformat(row['expires_at']))
      except (TypeError, ValueError):
        raise InviteExpired('unparseable expiry')
      if datetime.now(timezone.utc) > expires_dt:
        raise InviteExpired('expired')
      return row.get('email', '')
  raise InviteAlreadyConsumed('not found or invalid token')
```

---

### `system_params.py` — add `FANOUT_SEMAPHORE_LIMIT`

**Analog:** `system_params.py` lines 1–40 (existing constants pattern)

**Pattern — add near HTTP_TIMEOUT_S:**
```python
# Phase 37 UMAIL-03: Resend rate-limit throttle for per-user fan-out.
# Conservative 2 req/sec default (can bump to 5 for newer Resend accounts).
# Operator bumps this constant; per_user_fanout.py reads it at asyncio.run time.
FANOUT_SEMAPHORE_LIMIT: int = 2
```

---

### `web/routes/admin/_models.py` — add `PendingInviteSummary`, extend `PublicUserSummary`

**Analog:** `web/routes/admin/_models.py` lines 1–38 (`PublicUserSummary`)

**Add `last_seen_date` population logic** (from RESEARCH.md Q3 — populate from trusted devices):
```python
# Phase 37: last_seen_date populated from most-recent TrustedDevice.last_seen
# Call auth_store.list_trusted_devices(uid) or scan list_users() trusted_devices field.
# No schema change needed.
```

**New `PendingInviteSummary` model:**
```python
class PendingInviteSummary(BaseModel):
  '''Minimal view of a pending invite for admin display.'''
  token_hash: str      # sha256: prefix hash — used as revoke key
  email: str
  invited_by: str      # uid of admin who issued
  created_at: str
  expires_at: str
  consumed: bool
```

---

## Shared Patterns

### Authentication / Dependency Gate
**Source:** `web/dependencies.py` lines 22–49
**Apply to:** All new admin routes, all new dashboard routes
```python
from web.dependencies import current_user_id, require_admin

# Admin routes: injected at router level (inherited by all admin routes)
router = APIRouter(prefix='/admin', dependencies=[Depends(require_admin)])

# Per-user routes: injected at handler level
def patch_email_prefs(..., uid: str = Depends(current_user_id)) -> Response:
    ...
```

### Never-Raise Email Dispatch
**Source:** `notifier/dispatch.py` lines 77–179 (`send_daily_email`)
**Apply to:** All new dispatch functions in `notifier/dispatch.py`
```python
# Template: from_addr check → api_key check → to_addr check → try _post_to_resend
# → except ResendError → except Exception (BLE001) → always return SendStatus
```

### itsdangerous Cookie — Wizard Step State
**Source:** `web/routes/totp/__init__.py` lines 49–66 (serializer construction + `_validate_enroll_cookie`)
**Apply to:** `web/routes/invite/__init__.py`
```python
# At register()-time:
wizard_serializer = URLSafeTimedSerializer(secret, salt='tsi-invite-wizard')

# Validate pattern (copy from _validate_enroll_cookie):
def _validate_wizard_cookie(request: Request) -> dict | None:
    token = request.cookies.get('tsi_invite_wizard')
    if not token:
        return None
    try:
        return wizard_serializer.loads(token, max_age=_WIZARD_COOKIE_MAX_AGE)
    except (SignatureExpired, BadSignature):
        return None
```

### Multi-Cookie Response
**Source:** `web/routes/totp/__init__.py` lines 210–219 (raw_headers append pattern)
**Apply to:** `web/routes/invite/__init__.py` — every step that issues/clears cookies
```python
# FastAPI Response only carries one Set-Cookie via headers dict.
# Use raw_headers for multiple Set-Cookie headers:
resp = Response(status_code=302, headers={'Location': target_url})
for sc in [cookie1_str, cookie2_str]:
    resp.raw_headers.append((b'set-cookie', sc.encode('latin-1')))
return resp
```

### mutate_user_state for HTMX Mutations
**Source:** `state_manager/__init__.py` lines 385–411 (`mutate_user_state`)
**Apply to:** `PATCH /settings/email-prefs` in dashboard routes
```python
from state_manager import mutate_user_state

def _apply(state: dict) -> None:
    state['users'][uid]['email_enabled'] = enabled_bool
    state['users'][uid]['pause_until'] = pause_date

mutate_user_state(uid, _apply)
```

### flock-guarded auth_store Write
**Source:** `auth_store/_users.py` lines 201–281 (`consume_and_create_user`)
**Apply to:** `revoke_invite` does NOT need a flock per D-01 (concurrent revoke has safe outcome). `consume_and_create_user` extension already has flock — add `password_hash` param inside existing lock window.

### BASE_URL env var pattern
**Source:** `web/routes/login/__init__.py` line 210 (confirmed)
**Apply to:** `send_invite_email`, `send_per_user_email` (RFC 8058 List-Unsubscribe URL)
```python
base_url = os.environ.get('BASE_URL', '').strip()
if not base_url:
    logger.error('[Email] BASE_URL not set — invite email skipped')
    return SendStatus(ok=False, reason='missing_base_url')
invite_url = f'{base_url}/accept-invite?token={raw_token}'
```

### W3 Invariant — Single Terminal mutate_state
**Source:** `state_manager/__init__.py` lines 345–382 (`mutate_state`)
**Apply to:** `per_user_fanout.py::run()` — exactly ONE `mutate_state` call, after `asyncio.run()` completes
```python
# W3 #2: ONE call, after gather completes
def _batch_write(s: dict) -> None:
    s['last_cycle'] = {'date': run_date, 'users': outcomes}
mutate_state(_batch_write)
# Cycle summary email AFTER mutate_state (not inside it)
send_cycle_summary_email(outcomes, run_date)
```

### 2-space indent
**Source:** `CLAUDE.md` project instructions
**Apply to:** ALL new files — do NOT run `ruff format` (reflows to 4-space).

---

## No Analog Found

All files have close analogs in the codebase. No entries.

---

## Metadata

**Analog search scope:** Root, `notifier/`, `auth_store/`, `web/routes/`, `web/middleware/`, `state_manager/`, `web/`
**Files scanned:** 16
**Pattern extraction date:** 2026-05-14
