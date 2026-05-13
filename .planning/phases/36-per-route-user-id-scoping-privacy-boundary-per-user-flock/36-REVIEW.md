---
phase: 36-per-route-user-id-scoping-privacy-boundary-per-user-flock
reviewed: 2026-05-14T00:00:00Z
depth: standard
files_reviewed: 12
files_reviewed_list:
  - state_manager/__init__.py
  - state_manager/trades.py
  - tests/conftest.py
  - tests/test_state_manager_per_user.py
  - tests/test_tenant_isolation.py
  - tests/test_web_admin_users.py
  - tests/test_web_paper_trades_ownership.py
  - tests/test_web_trades_ownership.py
  - web/routes/admin/__init__.py
  - web/routes/admin/_models.py
  - web/routes/paper_trades/__init__.py
  - web/routes/trades/__init__.py
findings:
  critical: 2
  warning: 3
  info: 3
  total: 8
status: issues_found
---

# Phase 36: Code Review Report

**Reviewed:** 2026-05-14T00:00:00Z
**Depth:** standard
**Files Reviewed:** 12
**Status:** issues_found

## Summary

Phase 36 adds per-user flock locking (`mutate_user_state`), a `load_user_state` slice helper,
per-route uid scoping in trades and paper-trades routes, and the `GET /admin/users` +
`PATCH /admin/users/{uid}/disable` admin endpoints. The overall structure is sound and the
tenant-isolation pattern (routes navigate `state['users'][user_id]` so another user's data
is simply not found) is correct.

Two blockers found: a missing disabled-user enforcement in `current_user_id` that lets a
freshly-disabled user keep operating within their session window, and an unguarded `KeyError`
in `load_user_state` when the uid is not present in `state['users']` (routes call
`load_user_state(uid)['positions']` with no exception handler, producing a 500).

Three warnings found: a falsy-dict bug in `record_trade`'s uid fallback, a missing
`last_alert_state` field on newly-opened paper trades, and test isolation stubs that
do not forward the `uid` argument to the mutator (tests pass correctly today but would
not catch a future regression where the route reads the wrong user bucket).

---

## Critical Issues

### CR-01: Disabled user can still access all normal routes within session window

**File:** `web/dependencies.py:22-31`
**Issue:** `current_user_id()` only checks `uid is None`; it does not call `get_user(uid)` to
verify `user.disabled`. `require_admin()` (line 42) does check `row.get('disabled')`, so admin
routes are gated, but every non-admin route (`/trades/*`, `/paper-trade/*`, etc.) that uses
`Depends(current_user_id)` will accept requests from a disabled user as long as their
`tsi_session` cookie has not expired (12-hour window). An operator who disables a user
via `PATCH /admin/users/{uid}/disable` will not have that take effect on non-admin routes
until the user's session expires.

**Fix:**
```python
def current_user_id(request: Request) -> str:
  uid = getattr(request.state, 'user_id', None)
  if uid is None:
    raise HTTPException(status_code=403, detail=_DETAIL_NOT_AUTHENTICATED)
  from auth_store import get_user
  row = get_user(uid)
  if row is None or row.get('disabled'):
    raise HTTPException(status_code=403, detail=_DETAIL_NOT_AUTHENTICATED)
  return uid
```

---

### CR-02: `load_user_state` raises unhandled `KeyError` for unknown uid → 500

**File:** `state_manager/__init__.py:421`
**Issue:** `load_user_state` does a raw `['users'][uid]` subscript:
```python
return load_state(path=path)['users'][uid]
```
If `uid` is not present in `state['users']` (e.g., a new user who has never been seeded,
or a stale cookie referencing a deleted user), this raises `KeyError`. The GET handlers in
`web/routes/trades/__init__.py` (lines 282, 300, 315) call `load_user_state(user_id)['positions']`
with no `except KeyError` — FastAPI converts the unhandled exception to a 500, leaking a
stack trace to the client and potentially exposing internal state structure.

**Fix:**
```python
def load_user_state(uid: str, path: Path = Path(STATE_FILE)) -> dict:
  state = load_state(path=path)
  user = state.get('users', {}).get(uid)
  if user is None:
    raise KeyError(f'user {uid!r} not in state[\"users\"]')
  return user
```
And in each route GET handler wrap with:
```python
from fastapi import HTTPException
try:
    positions = load_user_state(user_id)['positions']
except KeyError:
    raise HTTPException(status_code=403, detail=_DETAIL_NOT_AUTHENTICATED)
```

---

## Warnings

### WR-01: `record_trade` uses falsy-dict `or` fallback — silently writes to admin bucket

**File:** `state_manager/trades.py:149`
**Issue:**
```python
user = users_map.get(uid) or _admin_user(state)
```
`dict.get()` returns `None` when the key is absent, but an *empty* dict `{}` when the key
exists with an empty value. Python evaluates `{}` as falsy, so if a user bucket exists but
is an empty dict, `or _admin_user(state)` silently redirects the trade write to the admin
bucket instead of raising an error. This is a correctness bug: the intent is "fall back to
admin only when uid is not in users_map at all", not "fall back when the bucket is falsy".

**Fix:**
```python
user = users_map.get(uid)
if user is None:
    user = _admin_user(state)
```

---

### WR-02: `open_paper_trade` does not set `last_alert_state` on new rows

**File:** `web/routes/paper_trades/__init__.py:116-130`
**Issue:** The dict appended in `open_paper_trade` lacks the `last_alert_state` key:
```python
rows.append({
    'id': trade_id,
    ...
    'strategy_version': STRATEGY_VERSION,
    # last_alert_state is absent
})
```
`edit_paper_trade` (line 195) resets `row['last_alert_state'] = None` and existing fixtures
always include the field. `paper_trade_alerts.py` uses `.get('last_alert_state')` so there is
no immediate crash. However, the row schema is inconsistent: a freshly opened trade is missing
a field that all other code paths set. Any future direct access (`row['last_alert_state']`)
will raise `KeyError` on trades opened via this route.

**Fix:** Add the field to the appended dict:
```python
rows.append({
    ...
    'strategy_version': STRATEGY_VERSION,
    'last_alert_state': None,   # Phase 20 D-09: set on open; reset on edit
})
```

---

### WR-03: Test mutate stubs ignore `uid` argument — isolation assertions are structurally weak

**File:** `tests/test_web_paper_trades_ownership.py:112-113`, `tests/test_web_trades_ownership.py:111-112`
**Issue:** Both ownership-test fixtures stub `mutate_user_state` as:
```python
def _mutate_stub(uid, mutator, *_a, **_kw):
    mutator(seeded_state)   # uid is silently ignored
    return seeded_state
```
The stubs pass the full `seeded_state` to `mutator`. Route `_apply` closures then navigate
`state['users'][user_id]` using the `user_id` captured from `Depends(current_user_id)`.
Today this is correct because `user_id == uid_b` (from the signed cookie) and
`seeded_state['users'][uid_b]` has empty buckets.

However, the stub would also pass if a route mistakenly read `state['users'][uid_a]`
(e.g., using a wrong captured variable), because the isolation proof relies entirely
on the empty-bucket content, not on the route actually using `uid_b`. A regression
where the route ignores the uid from `Depends()` and uses a hardcoded admin uid would
not be caught by these tests.

**Fix:** Forward `uid` to the mutator so the stub exercises the real dispatch path:
```python
def _mutate_stub(uid, mutator, *_a, **_kw):
    # Build a state view scoped to uid so the test fails if the route
    # navigates the wrong bucket.
    scoped = {**seeded_state, '_stub_uid': uid}
    mutator(scoped)
    return scoped
```
Or, alternatively, assert inside the stub that `uid == uid_b` to catch regressions
where the route resolves the wrong user.

---

## Info

### IN-01: `OPERATOR_RECOVERY_EMAIL` hardcoded in `two_user_client` fixture instead of using `VALID_RECOVERY_EMAIL`

**File:** `tests/test_tenant_isolation.py:50`
**Issue:**
```python
monkeypatch.setenv('OPERATOR_RECOVERY_EMAIL', 'mwiriadi@gmail.com')
```
`conftest.py` already defines `VALID_RECOVERY_EMAIL = 'mwiriadi@gmail.com'` as a single source
of truth (conftest.py line 41). The fixture duplicates the literal string instead of importing
and reusing the constant. If the canonical value changes, this fixture will drift silently.

**Fix:**
```python
from tests.conftest import VALID_RECOVERY_EMAIL
monkeypatch.setenv('OPERATOR_RECOVERY_EMAIL', VALID_RECOVERY_EMAIL)
```

---

### IN-02: Admin can self-disable with no guard — no recovery path without direct state edit

**File:** `web/routes/admin/__init__.py:59-69`
**Issue:** `admin_disable_user` accepts `uid` from the URL path with no check that
`uid != current_admin_uid`. An admin who disables their own account is immediately locked
out of all admin routes (`require_admin` checks `row.get('disabled')`). Recovery requires
either a second admin account or manual editing of `auth.json`. This is a usability trap
that could lock operators out of the system.

**Fix:** Add a self-disable guard:
```python
@router.patch('/users/{uid}/disable')
def admin_disable_user(uid: str, disabled: bool = True, caller_uid: str = Depends(require_admin)):
  if disabled and uid == caller_uid:
    raise HTTPException(status_code=400, detail='cannot disable your own account')
  ...
```

---

### IN-03: No test for the `disabled=false` re-enable path in `TestAdminDisable`

**File:** `tests/test_web_admin_users.py:119-149`
**Issue:** `TestAdminDisable` only tests `disabled=true`. The `PATCH /admin/users/{uid}/disable`
endpoint accepts `disabled: bool = True` as a query param, meaning `disabled=false` should
re-enable a user. There is no test asserting that `PATCH /admin/users/{uid}/disable?disabled=false`
returns 200 with `disabled: false`. Without a test, a future refactor breaking the re-enable
path would go undetected.

**Fix:** Add a test:
```python
@pytest.mark.xfail(strict=False, reason='Wave 1: re-enable path not yet tested')
def test_reenable_returns_ok(self, admin_client):
    client, uid = admin_client
    cookie = _build_session_cookie(uid)
    resp = client.patch(
        f'/admin/users/{uid}/disable',
        params={'disabled': 'false'},
        cookies={'tsi_session': cookie},
    )
    assert resp.status_code == 200
    assert resp.json().get('disabled') is False
```

---

_Reviewed: 2026-05-14T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
