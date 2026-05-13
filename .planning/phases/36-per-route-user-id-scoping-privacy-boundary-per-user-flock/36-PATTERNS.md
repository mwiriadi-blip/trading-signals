# Phase 36: Per-Route User-ID Scoping + Privacy Boundary + Per-User Flock - Pattern Map

**Mapped:** 2026-05-14
**Files analyzed:** 10
**Analogs found:** 9 / 10

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `state_manager/__init__.py` | service | CRUD (mutation wrapper) | `state_manager/__init__.py::mutate_state` (lines 345–382) | exact — extend same file |
| `state_manager/io.py` | utility | file-I/O | `state_manager/io.py::_atomic_write` (lines 172–201) | exact — flock discipline |
| `web/routes/admin/_models.py` | model | request-response | `web/routes/trades/_models.py` | role-match — Pydantic BaseModel file |
| `web/routes/admin/__init__.py` | controller | request-response | `web/routes/admin/__init__.py` (existing ping route) | exact — extend same file |
| `web/routes/paper_trades/__init__.py` | controller | CRUD | `web/routes/paper_trades/__init__.py` (existing) | exact — migrate same file |
| `web/routes/trades/__init__.py` | controller | CRUD | `web/routes/trades/__init__.py` (existing) | exact — migrate same file |
| `tests/test_tenant_isolation.py` | test | request-response | `tests/test_web_admin.py::TestAdminPing` | role-match — FastAPI TestClient test class |
| `tests/test_state_manager.py` | test | file-I/O | `tests/test_state_manager.py::TestLoadSave` (existing) | exact — extend same file |
| `tests/test_web_admin.py` | test | request-response | `tests/test_web_admin.py::TestRequireAdmin` (existing) | exact — extend same file |
| `tests/conftest.py` | config | CRUD | `tests/conftest.py::client_with_state_v6` (existing) | exact — update same file |

---

## Pattern Assignments

### `state_manager/__init__.py` — add `mutate_user_state` + `load_user_state`

**Analog:** `state_manager/__init__.py::mutate_state` lines 345–382

**Imports pattern** (lines 39–49 of `state_manager/__init__.py`):
```python
import fcntl
import os
from pathlib import Path
from typing import Callable
```
All already present. No new imports needed — `fcntl`, `os`, `Path`, `Callable` are in scope.

**Core mutate_state pattern** (lines 345–382 — copy lock discipline exactly):
```python
def mutate_state(
  mutator: Callable[[dict], None],
  path: Path = Path(STATE_FILE),
) -> dict:
  fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
  try:
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
      state = load_state(path=path, _under_lock=True)
      mutator(state)
      io._save_state_unlocked(state, path=path)
      return state
    finally:
      fcntl.flock(fd, fcntl.LOCK_UN)
  finally:
    os.close(fd)
```

**New `mutate_user_state` — outer flock wraps mutate_state call:**
```python
def mutate_user_state(
  uid: str,
  mutator: Callable[[dict], None],
  path: Path = Path(STATE_FILE),
) -> dict:
  '''Outer per-user flock (state/users/{uid}.lock) + inner mutate_state.

  Acquisition order: state/users/{uid}.lock (OUTER) -> state.json (INNER).
  All callers acquire in this order — no deadlock possible.
  D-01/D-02/D-03/D-04 (CONTEXT.md).
  '''
  lock_dir = Path('state/users')
  lock_dir.mkdir(parents=True, exist_ok=True)
  lock_path = lock_dir / f'{uid}.lock'
  with open(lock_path, 'a+') as lock_file:
    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
    try:
      return mutate_state(mutator, path=path)
    finally:
      fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
```
Note: `open('a+')` creates the lock file if absent (D-03). The `with` block closes the fd on exit.

**New `load_user_state` — thin slice of load_state:**
```python
def load_user_state(uid: str, path: Path = Path(STATE_FILE)) -> dict:
  '''Return state["users"][uid] slice. D-05.'''
  return load_state(path=path)['users'][uid]
```

**`__all__` extension** (line 385 of `state_manager/__init__.py`):
```python
__all__ = [
  'load_state', 'save_state', 'reset_state', 'mutate_state',
  'mutate_user_state', 'load_user_state',   # Phase 36 additions
  ...
]
```

---

### `state_manager/io.py` — flock pattern reference only (no changes needed)

**Analog:** `state_manager/io.py::_atomic_write` lines 172–201

**Key discipline** — lock fd opened via `os.open(O_RDWR|O_CREAT)`, flock acquired, inner work done, `LOCK_UN` in finally, `os.close` in outer finally:
```python
lock_fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
try:
  fcntl.flock(lock_fd, fcntl.LOCK_EX)
  try:
    _atomic_write_unlocked(data, path)
  finally:
    fcntl.flock(lock_fd, fcntl.LOCK_UN)
finally:
  os.close(lock_fd)
```
`mutate_user_state` uses `open('a+')` + `fileno()` instead of `os.open` for the per-user lock because the lock file carries no content — the `a+` mode creates-if-absent cleanly. The inner `mutate_state` uses the `os.open` pattern unchanged.

**Intra-process reentrancy note** (lines 11–16 of `state_manager/io.py`):
> flock locks the open-file-description, NOT the inode/path. Two fds in the SAME process do NOT share lock ownership. mutate_state calls _save_state_unlocked directly rather than routing through save_state -> _atomic_write.

The per-user `uid.lock` is a DIFFERENT file from `state.json` — no second acquire on the same fd. Safe.

---

### `web/routes/admin/_models.py` — new file, Pydantic BaseModel

**Analog:** `web/routes/trades/_models.py` lines 1–12 (module docstring + imports)

**Module docstring + imports pattern** (copy from `web/routes/trades/_models.py` lines 1–22):
```python
'''Pydantic request/response models for web/routes/admin package.

PublicUserSummary — D-07..D-11 (CONTEXT.md Phase 36).
FastAPI response_model on GET /admin/users strips all non-listed fields
automatically — no custom serializer needed.
'''
from pydantic import BaseModel
```

**Core model pattern** (from `web/routes/trades/_models.py` lines 46–58):
```python
class OpenTradeRequest(BaseModel):
  model_config = ConfigDict(extra='forbid')
  instrument: str = Field(pattern=r'^[A-Z0-9_]{2,20}$')
  ...
```

**New PublicUserSummary — no extra='forbid', response model (output only):**
```python
class PublicUserSummary(BaseModel):
  '''Phase 36 D-07: admin-facing user summary. Output model only.

  FastAPI strips all fields not listed here when response_model is set.
  Trade content (paper_trades, equity_history, entry_price, etc.) cannot
  leak — those fields simply don't exist on this model.
  '''
  user_id: str
  display_name: str
  status: str          # "active" or "disabled" (D-09)
  last_seen_date: str | None
  has_active_position: bool
```
No `model_config` needed — this is an output-only model, not a request validator.

---

### `web/routes/admin/__init__.py` — add `GET /admin/users` + `PATCH /admin/users/{uid}/disable`

**Analog:** `web/routes/admin/__init__.py` lines 1–24 (existing file)

**Module-level structure** (lines 1–15 of existing file):
```python
from fastapi import APIRouter, Depends
from web.dependencies import require_admin

router = APIRouter(prefix='/admin', dependencies=[Depends(require_admin)])

@router.get('/ping')
def ping():
  return {'ok': True}
```

**New GET /admin/users — response_model enforces privacy boundary:**
```python
from web.routes.admin._models import PublicUserSummary
from auth_store import list_users
from state_manager import load_state

@router.get('/users', response_model=list[PublicUserSummary])
def admin_list_users():
  '''RBAC-04 / D-11: list all users. FastAPI response_model strips all
  non-PublicUserSummary fields — trade content cannot appear in response.
  '''
  users = list_users()
  state = load_state()  # load once; avoid N+1 reads
  result = []
  for user in users:
    uid = user['uid']
    user_bucket = state.get('users', {}).get(uid, {})
    positions = user_bucket.get('positions', {})
    has_active = any(v is not None for v in positions.values())
    result.append(PublicUserSummary(
      user_id=uid,
      display_name=user['email'],
      status='disabled' if user.get('disabled') else 'active',
      last_seen_date=None,  # Phase 36: device-lookup deferred (A1)
      has_active_position=has_active,
    ))
  return result
```

**New PATCH /admin/users/{uid}/disable:**
```python
from fastapi import HTTPException

@router.patch('/users/{uid}/disable')
def admin_disable_user(uid: str, disabled: bool = True):
  '''RBAC-04: toggle disabled flag. Reversible. set_user_disabled already
  exists in auth_store with flock semantics.
  '''
  from auth_store import set_user_disabled
  found = set_user_disabled(uid, disabled)
  if not found:
    raise HTTPException(status_code=404, detail=f'user {uid!r} not found')
  return {'ok': True, 'uid': uid, 'disabled': disabled}
```

---

### `web/routes/paper_trades/__init__.py` — migrate mutate_state calls

**Analog:** existing handlers in this file (lines 54–321)

**Current pattern** (e.g. line 119–120):
```python
from state_manager import mutate_state
state = mutate_state(_apply)
```

**Migrated pattern — three changes per handler:**

1. Add `user_id: str = Depends(current_user_id)` to handler signature.
2. Inside `_apply`, navigate via `state['users'][user_id]` before accessing `paper_trades`.
3. Rename call to `mutate_user_state(user_id, _apply)`.

**Concrete before/after for `open_paper_trade` (lines 77–131):**
```python
# BEFORE
@app.post('/paper-trade/open', response_class=HTMLResponse)
async def open_paper_trade(request: Request) -> HTMLResponse:
  req = await _parse_form(request, OpenPaperTradeRequest)
  def _apply(state: dict) -> None:
    rows = state.setdefault('paper_trades', [])
    ...
  from state_manager import mutate_state
  state = mutate_state(_apply)

# AFTER
@app.post('/paper-trade/open', response_class=HTMLResponse)
async def open_paper_trade(
  request: Request,
  user_id: str = Depends(current_user_id),
) -> HTMLResponse:
  req = await _parse_form(request, OpenPaperTradeRequest)
  def _apply(state: dict) -> None:
    user = state['users'][user_id]        # navigate to user bucket
    rows = user.setdefault('paper_trades', [])
    ...
  from state_manager import mutate_user_state
  state = mutate_user_state(user_id, _apply)
  # render: user bucket has paper_trades; signals are top-level
  user_state = state['users'][user_id]
  merged = {**user_state, 'signals': state.get('signals', {})}
  from dashboard_renderer.components.paper_trades import render_paper_trades_region
  return HTMLResponse(content=render_paper_trades_region(merged))
```

**Depends import** (add at top of file alongside existing imports):
```python
from fastapi import Depends
from web.dependencies import current_user_id
```

**Entity-ID 404 ownership check pattern** (for edit/delete/close/get_close_form):
```python
# Inside _apply or read handler: ownership check before action
matches = [r for r in user['paper_trades'] if r['id'] == trade_id]
if not matches:
  raise _PaperTradeNotFound(trade_id)  # 404 — not found for THIS user
```
The existing `_PaperTradeNotFound` → 404 path is unchanged; because `_apply` now only looks in `state['users'][user_id]['paper_trades']`, a trade that exists for user A but not user B naturally raises `_PaperTradeNotFound` for user B without any explicit cross-user check.

For `get_close_form` (read path, lines 286–320) — use `load_user_state`:
```python
from state_manager import load_user_state
user_state = load_user_state(user_id)
rows = user_state.get('paper_trades', [])
```

---

### `web/routes/trades/__init__.py` — migrate mutate_state calls + record_trade uid

**Analog:** existing handlers in this file (lines 41–end)

**Same three-change migration as paper_trades.** Additionally, `record_trade` hardcodes `_ADMIN_UID` — must pass `uid`.

**record_trade call site** (line ~217 in `close_trade`):
```python
# BEFORE (in _apply):
from state_manager import record_trade
record_trade(state, trade_record)  # writes to _ADMIN_UID bucket

# AFTER:
from state_manager import record_trade
record_trade(state, trade_record, uid=user_id)  # D-03 RESEARCH: add uid param
```
The `state_manager/trades.py::record_trade` function must gain a `uid: str = _ADMIN_UID` parameter. Existing callers (daily_run.py etc.) pass no uid — backward compatible default.

**Read paths (`close_form`, `modify_form`, `cancel_row`) — use `load_user_state`:**
```python
from state_manager import load_user_state
user_state = load_user_state(user_id)
position = user_state['positions'].get(req.instrument)
if position is None:
  raise _OpenConflict(f'no open position for {req.instrument}')
```

**404 vs 409 ownership check** (trades 404-for-other-users, D-14):
```python
# In close_trade / modify_trade _apply:
# 409 = no position at all for this user (existing behavior)
# 404 = would require knowing another user has it — not checked here
# Since _apply navigates state['users'][user_id]['positions'], a position
# that exists for another user is simply not found → existing 409 behavior.
# For form reads, the check should be: if position is None → 404 explicitly.
if position is None:
  from fastapi import HTTPException
  raise HTTPException(status_code=404, detail=f'no position for {req.instrument}')
```

---

### `tests/test_tenant_isolation.py` — new file, TestTenantIsolation

**Analog:** `tests/test_web_admin.py` lines 56–68 (`_build_session_cookie`), lines 86–100 (`TestCurrentUserId` class structure)

**File header + imports pattern** (copy from `tests/test_web_admin.py` lines 1–41):
```python
'''Phase 36 — TestTenantIsolation quality gate.

TENANT-03: user A's trade content must be absent from:
  (a) GET /admin/users response
  (b) user B's served dashboard (future)
  (c) crash-email simulation (stubbed until Phase 37)

D-13 (CONTEXT.md Phase 36).
'''
import re
import sys
import time

import pytest
from fastapi.testclient import TestClient
from itsdangerous.url_safe import URLSafeTimedSerializer

from tests.conftest import VALID_SECRET, VALID_USERNAME
```

**Fixture pattern — seed state + two-user setup** (based on `client_with_state_v6` in conftest.py lines 311–362):
```python
@pytest.fixture
def two_user_client(monkeypatch, isolated_auth_json):
  '''Seed: user_a has 5 paper trades; user_b has none.
  Both users registered in auth.json.
  '''
  from fastapi.testclient import TestClient
  import sys, state_manager
  from state_manager.migrations import _ADMIN_UID
  sys.modules.pop('web.app', None)
  from web.app import create_app

  uid_a = 'aaaa' * 8  # 32-char hex
  uid_b = 'bbbb' * 8

  paper_trades_a = [
    {'id': f'SPI200-20260501-00{i}', 'entry_price': 8000.0 + i,
     'n_contracts': 2, 'direction': 'LONG', 'status': 'open'}
    for i in range(1, 6)
  ]
  state = {
    'schema_version': 12,
    'admin_user_id': _ADMIN_UID,
    'signals': {}, 'markets': {}, 'warnings': [], 'last_run': None,
    '_resolved_contracts': {},
    'users': {
      uid_a: {'paper_trades': paper_trades_a, 'positions': {}, 'trade_log': [],
               'equity_history': [], 'account': 100_000.0, 'initial_account': 100_000.0,
               'contracts': {}, 'ui_prefs': {'tour_completed': True}},
      uid_b: {'paper_trades': [], 'positions': {}, 'trade_log': [],
               'equity_history': [], 'account': 100_000.0, 'initial_account': 100_000.0,
               'contracts': {}, 'ui_prefs': {'tour_completed': True}},
    }
  }
  monkeypatch.setattr(state_manager, 'load_state', lambda *_a, **_kw: state)
  client = TestClient(create_app())
  return client, uid_a, uid_b
```

**Test body pattern** (`test_admin_users_response_has_no_trade_content`):
```python
TRADE_CONTENT_RE = re.compile(
  r'(entry_price|n_contracts|"direction":\s*"(LONG|SHORT)"|paper_trades)',
  re.IGNORECASE,
)

class TestTenantIsolation:
  def test_admin_users_response_has_no_trade_content(self, two_user_client, isolated_auth_json):
    client, uid_a, uid_b = two_user_client
    # seed auth.json with both users (admin role for uid_a)
    ...
    cookie = _build_session_cookie(uid_a)  # admin
    response = client.get('/admin/users', cookies={'tsi_session': cookie})
    assert response.status_code == 200
    body = response.text
    assert not TRADE_CONTENT_RE.search(body), (
      f'Trade content leaked into /admin/users response: {body[:200]}'
    )
```

---

### `tests/test_state_manager.py` — add TestMutateUserState class

**Analog:** existing `TestLoadSave` class structure in `tests/test_state_manager.py`

**Imports** (already present in file lines 24–45 — add new exports):
```python
from state_manager import (
  ...
  mutate_user_state,   # Phase 36 addition
  load_user_state,     # Phase 36 addition
)
```

**Class pattern** (mirrors `TestLoadSave` skeleton):
```python
class TestMutateUserState:
  '''Phase 36 TENANT-02: per-user flock wrapper correctness + isolation.'''

  def test_mutate_user_state_writes_to_user_bucket(self, tmp_path):
    '''mutator navigates state["users"][uid] — write lands in correct bucket.'''
    from state_manager.migrations import _ADMIN_UID
    path = tmp_path / 'state.json'
    uid = _ADMIN_UID

    def mutator(state):
      state['users'][uid]['account'] = 99_999.0

    mutate_user_state(uid, mutator, path=path)
    loaded = load_state(path=path)
    assert loaded['users'][uid]['account'] == 99_999.0

  def test_mutate_user_state_creates_lock_dir(self, tmp_path, monkeypatch):
    '''state/users/ dir auto-created on first call (D-03).'''
    # monkeypatch 'state/users' to tmp_path subdir to avoid repo root side-effects
    ...

  def test_load_user_state_returns_user_slice(self, tmp_path):
    '''load_user_state(uid) returns state["users"][uid].'''
    ...
```

---

### `tests/test_web_admin.py` — add TestAdminUsers + TestAdminDisable

**Analog:** `tests/test_web_admin.py::TestAdminPing` (existing class ~line 400)

**TestAdminPing class pattern** (for TestAdminUsers):
```python
class TestAdminPing:
  def test_ping_returns_200_ok(self, ...):
    # build session cookie as admin, GET /admin/ping
    ...
    assert response.status_code == 200
    assert response.json() == {'ok': True}
```

**TestAdminUsers pattern:**
```python
class TestAdminUsers:
  '''RBAC-04: GET /admin/users returns PublicUserSummary list; no trade content.'''

  def test_returns_200_with_public_summary_shape(self, client_admin, isolated_auth_json):
    response = client_admin.get('/admin/users')
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    for row in data:
      assert set(row.keys()) == {'user_id', 'display_name', 'status',
                                  'last_seen_date', 'has_active_position'}

  def test_returns_403_for_non_admin(self, client_ff_user):
    response = client_ff_user.get('/admin/users')
    assert response.status_code == 403

class TestAdminDisable:
  '''RBAC-04: PATCH /admin/users/{uid}/disable toggles flag.'''

  def test_disable_returns_ok(self, client_admin, isolated_auth_json):
    uid = '...'  # seed a user
    response = client_admin.patch(f'/admin/users/{uid}/disable?disabled=true')
    assert response.status_code == 200
    assert response.json()['disabled'] is True

  def test_disable_unknown_uid_returns_404(self, client_admin, isolated_auth_json):
    response = client_admin.patch('/admin/users/nonexistent/disable')
    assert response.status_code == 404
```

---

### `tests/conftest.py` — update fixtures to v12 state shape

**Analog:** `tests/conftest.py::client_with_state_v6` lines 311–362

**v12 default_state shape** (replace the `default_state` dict in both `client_with_state_v3` and `client_with_state_v6`):
```python
from state_manager.migrations import _ADMIN_UID

default_state = {
  'schema_version': 12,
  'admin_user_id': _ADMIN_UID,
  'last_run': '2026-04-25',
  'signals': {
    'SPI200': {'last_scalars': {'atr': 50.0}, 'last_close': 7820.0},
    'AUDUSD': {'last_close': 0.6520, 'last_scalars': {'atr': 0.005}},
  },
  'markets': {},
  'strategy_settings': {},
  'warnings': [],
  '_resolved_contracts': {
    'SPI200': {'multiplier': 5.0, 'cost_aud': 6.0},
    'AUDUSD': {'multiplier': 10000.0, 'cost_aud': 5.0},
  },
  'users': {
    _ADMIN_UID: {
      'account': 100_000.0,
      'initial_account': 100_000.0,
      'contracts': {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-mini'},
      'positions': {
        'SPI200': {
          'direction': 'LONG', 'entry_price': 7800.0, 'entry_date': '2026-04-20',
          'n_contracts': 2, 'pyramid_level': 0,
          'peak_price': 7850.0, 'trough_price': None, 'atr_entry': 50.0,
          'manual_stop': None,
        },
        'AUDUSD': None,
      },
      'trade_log': [],
      'equity_history': [],
      'paper_trades': [],
      'ui_prefs': {'tour_completed': True},
    }
  },
}
```

**`mutate_user_state` stub** (add alongside `mutate_state` stub in both fixtures):
```python
def _mutate_user_state_stub(uid, mutator, *_a, **_kw):
  state = state_box['value']
  mutator(state)  # mutator navigates state['users'][uid] itself
  captured_saves.append(dict(state))
  return state

monkeypatch.setattr(state_manager, 'mutate_state', _mutate_state_stub)
monkeypatch.setattr(state_manager, 'mutate_user_state', _mutate_user_state_stub)
```

The `mutate_state` stub is still needed for any routes not yet migrated to `mutate_user_state`.

---

## Shared Patterns

### FastAPI Depends — current_user_id injection
**Source:** `web/dependencies.py` lines 22–31
**Apply to:** All per-user route handlers in `paper_trades/__init__.py` and `trades/__init__.py`
```python
from fastapi import Depends
from web.dependencies import current_user_id

@app.post('/paper-trade/open')
async def open_paper_trade(
  request: Request,
  user_id: str = Depends(current_user_id),  # inject uid before any business logic
) -> HTMLResponse:
```

### State user-bucket navigation
**Source:** `state_manager/__init__.py::reset_state` lines 199–218 (v12 shape)
**Apply to:** All `_apply` mutator closures in paper_trades and trades routes
```python
def _apply(state: dict) -> None:
  user = state['users'][user_id]   # always navigate first
  rows = user.setdefault('paper_trades', [])  # then access user-scoped keys
  # state.get('signals') — shared top-level keys still accessed at top level
```

### Merged render dict (signals + user bucket)
**Source:** `state_manager/__init__.py::reset_state` v12 shape + research Q3
**Apply to:** All `render_paper_trades_region(state)` call sites after migration
```python
user_state = state['users'][user_id]
merged = {**user_state, 'signals': state.get('signals', {})}
return HTMLResponse(content=render_paper_trades_region(merged))
```

### FastAPI response_model privacy boundary
**Source:** `web/routes/admin/__init__.py` (new `GET /admin/users`)
**Apply to:** Admin routes that could expose per-user data
```python
@router.get('/users', response_model=list[PublicUserSummary])
def admin_list_users():
  # FastAPI strips all fields not in PublicUserSummary at serialization time
```

### Error handling — HTTPException re-raise
**Source:** `web/routes/paper_trades/__init__.py` lines 270–278
**Apply to:** All route handlers that have `_apply` closures raising HTTPException
```python
try:
  from state_manager import mutate_user_state
  state = mutate_user_state(user_id, _apply)
except _PaperTradeNotFound:
  raise HTTPException(status_code=404, detail=f'paper trade {trade_id!r} not found') from None
except _PaperTradeImmutable:
  return _method_not_allowed_405('GET')
except HTTPException:
  raise  # re-raise HTTPException originating inside _apply
```

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| (none) | — | — | All files have close analogs in the codebase |

---

## Metadata

**Analog search scope:** `state_manager/`, `web/routes/`, `web/dependencies.py`, `tests/`, `auth_store/`
**Files scanned:** 12
**Pattern extraction date:** 2026-05-14
