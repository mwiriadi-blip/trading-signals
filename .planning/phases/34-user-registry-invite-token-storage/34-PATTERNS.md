# Phase 34: User Registry + Invite-Token Storage - Pattern Map

**Mapped:** 2026-05-13
**Files analyzed:** 7 (5 new package files + 1 modified test file + 1 deleted flat module)
**Analogs found:** 7 / 7

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `auth_store/__init__.py` | package re-export | — | `state_manager/__init__.py` (re-export surface) + `sizing_engine/__init__.py` | exact |
| `auth_store/_io.py` | I/O adapter | CRUD + file-I/O | `auth_store.py` lines 122–229 (atomic write kernel, load/save, resolve/quarantine) | exact (split from) |
| `auth_store/_schema.py` | model | — | `auth_store.py` lines 64–114 (TypedDicts, `_default_auth_data`, `_ensure_aware`) | exact (split from) |
| `auth_store/_devices.py` | I/O adapter | CRUD | `auth_store.py` lines 266–382 (trusted-device helpers) | exact (move verbatim) |
| `auth_store/_magic_links.py` | I/O adapter | CRUD | `auth_store.py` lines 385–520 (magic-link helpers) | exact (move verbatim) |
| `auth_store/_users.py` | I/O adapter | CRUD + flock | `auth_store.py` (load→mutate→save pattern) + `state_manager/__init__.py::mutate_state` (flock window) | role-match + flock-exact |
| `tests/test_auth_store.py` | test | — | `tests/test_auth_store.py` lines 587–621 (`TestForbiddenImports` update only) | exact (patch path) |
| `tests/test_auth_store_users.py` | test | — | `tests/test_auth_store.py` (test class structure, `isolated_auth_json` fixture, `tmp_auth_path` fixture) | role-match |

---

## Pattern Assignments

### `auth_store/__init__.py` (package re-export, zero logic)

**Analog:** `sizing_engine/__init__.py` (re-export pattern) + `state_manager/__init__.py` (docstring style)

**Re-export pattern** (`sizing_engine/__init__.py` lines 20–30 style):
```python
from auth_store._io import load_auth, save_auth
from auth_store._devices import (
  add_trusted_device, revoke_device, revoke_all_other_devices,
  get_trusted_device, update_last_seen, is_uuid_active,
)
from auth_store._magic_links import (
  add_magic_link, consume_magic_link, count_recent_magic_links,
  purge_expired_magic_links,
)
from auth_store._users import (
  create_user, mint_invite_token, consume_and_create_user,
  get_user, list_users, set_user_disabled,
)
from auth_store._schema import (
  AuthData, User, PendingInvite, TrustedDevice, PendingMagicLink,
  SCHEMA_VERSION,
)
```

**DEFAULT_AUTH_PATH ownership** (`auth_store.py` line 59 — stays in `__init__.py` per RESEARCH Pitfall 6):
```python
# Keep here (NOT in _io.py) so monkeypatch.setattr(auth_store, 'DEFAULT_AUTH_PATH', ...)
# in conftest.py::isolated_auth_json continues to work unchanged.
DEFAULT_AUTH_PATH = Path('auth.json')
```

---

### `auth_store/_schema.py` (TypedDicts + constants)

**Analog:** `auth_store.py` lines 32–114

**Imports pattern** (`auth_store.py` lines 32–42):
```python
import hashlib
import json
import logging
import os
import tempfile
import time
import uuid as _uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TypedDict
```
For `_schema.py` keep only: `from typing import TypedDict` (no I/O imports).

**_ensure_aware pattern** (`auth_store.py` lines 49–55):
```python
def _ensure_aware(dt: datetime) -> datetime:
  if dt.tzinfo is None:
    return dt.replace(tzinfo=timezone.utc)
  return dt
```

**SCHEMA_VERSION bump** (`auth_store.py` line 47 — bump to 2):
```python
SCHEMA_VERSION = 2
```

**TrustedDevice TypedDict** (`auth_store.py` lines 67–77 — copy verbatim):
```python
class TrustedDevice(TypedDict):
  uuid: str
  label: str
  granted_at: str
  last_seen: str
  revoked: bool
  revoked_at: str | None
```

**PendingMagicLink TypedDict** (`auth_store.py` lines 80–91 — copy verbatim):
```python
class PendingMagicLink(TypedDict):
  token_hash: str
  email: str
  action: str
  created_at: str
  expires_at: str
  consumed: bool
  consumed_at: str | None
```

**New TypedDicts** (D-05 User, D-08 PendingInvite):
```python
class User(TypedDict):
  uid: str            # uuid4().hex — see add_trusted_device pattern
  email: str
  role: str           # "admin" | "ff"
  created_at: str     # datetime.now(timezone.utc).isoformat()
  disabled: bool      # default False

class PendingInvite(TypedDict):
  token_hash: str     # "sha256:<hex>" prefix-tagged
  email: str
  invited_by: str     # uid of issuing admin
  created_at: str
  expires_at: str     # created_at + timedelta(days=7)
  consumed: bool
  consumed_at: str | None
```

**AuthData TypedDict v2 extension** (extend `auth_store.py` lines 94–103):
```python
class AuthData(TypedDict):
  schema_version: int
  totp_secret: str | None
  totp_enrolled: bool
  totp_enrolled_at: str | None
  trusted_devices: list[TrustedDevice]
  pending_magic_links: list[PendingMagicLink]
  users: list[User]                   # NEW v2
  pending_invites: list[PendingInvite]  # NEW v2
```

**_default_auth_data v2** (`auth_store.py` lines 105–114 — add new keys):
```python
def _default_auth_data() -> AuthData:
  return {
    'schema_version': SCHEMA_VERSION,
    'totp_secret': None,
    'totp_enrolled': False,
    'totp_enrolled_at': None,
    'trusted_devices': [],
    'pending_magic_links': [],
    'users': [],             # NEW v2
    'pending_invites': [],   # NEW v2
  }
```

---

### `auth_store/_io.py` (atomic write kernel, load/save, migration)

**Analog:** `auth_store.py` lines 119–229 + `state_manager/io.py` lines 118–201

**_atomic_write pattern** (`auth_store.py` lines 122–161 — copy verbatim, rename to match):
```python
def _atomic_write(data: str, path: Path) -> None:
  parent = path.parent
  tmp_path_str = None
  try:
    with tempfile.NamedTemporaryFile(
      dir=parent, delete=False, mode='w', suffix='.tmp', encoding='utf-8',
    ) as tmp:
      tmp_path_str = tmp.name
      tmp.write(data)
      tmp.flush()
      os.fsync(tmp.fileno())
    os.replace(tmp_path_str, path)
    if os.name == 'posix':
      dir_fd = os.open(str(parent), os.O_RDONLY)
      try:
        os.fsync(dir_fd)
      finally:
        os.close(dir_fd)
    tmp_path_str = None
  finally:
    if tmp_path_str is not None:
      try:
        os.unlink(tmp_path_str)
      except FileNotFoundError:
        pass
```

**_atomic_write_unlocked pattern** (copy of the above with no lock; mirrors `state_manager/io.py` lines 118–169; needed by `consume_and_create_user` to avoid deadlock):
```python
def _atomic_write_unlocked(data: str, path: Path) -> None:
  # identical body to _atomic_write above — caller holds LOCK_EX externally
  ...
```

**_resolve_path pattern** (`auth_store.py` lines 169–178):
```python
def _resolve_path(path: Path | None) -> Path:
  # Import from package __init__ to pick up monkeypatched DEFAULT_AUTH_PATH
  from auth_store import DEFAULT_AUTH_PATH
  return path if path is not None else DEFAULT_AUTH_PATH
```
NOTE: `_io.py` must import `DEFAULT_AUTH_PATH` from `auth_store` (the package), NOT define it locally, so `monkeypatch.setattr(auth_store, 'DEFAULT_AUTH_PATH', ...)` in `conftest.py` is respected. See RESEARCH Pitfall 6.

**_quarantine_corrupt_auth_file pattern** (`auth_store.py` lines 181–200 — copy verbatim).

**load_auth with v1→v2 migration** (`auth_store.py` lines 203–223, extended per D-09):
```python
def load_auth(path: Path | None = None) -> AuthData:
  resolved = _resolve_path(path)
  if not resolved.exists():
    return _default_auth_data()
  try:
    payload = json.loads(resolved.read_text(encoding='utf-8'))
  except (json.JSONDecodeError, UnicodeDecodeError) as exc:
    logger.warning('[Auth] corrupt auth store %s: %s', resolved, exc)
    _quarantine_corrupt_auth_file(resolved)
    return _default_auth_data()
  if not isinstance(payload, dict):
    logger.warning('[Auth] invalid auth store shape in %s: expected object', resolved)
    _quarantine_corrupt_auth_file(resolved)
    return _default_auth_data()
  # D-09: v1 → v2 migration — backfill new arrays, bump schema, persist immediately
  if payload.get('schema_version') == 1:
    payload['users'] = payload.get('users', [])
    payload['pending_invites'] = payload.get('pending_invites', [])
    payload['schema_version'] = 2
    save_auth(payload, path=path)
  return payload
```

**save_auth pattern** (`auth_store.py` lines 226–229 — copy verbatim):
```python
def save_auth(data: AuthData, path: Path | None = None) -> None:
  payload = json.dumps(data, indent=2, ensure_ascii=False) + '\n'
  _atomic_write(payload, _resolve_path(path))
```

---

### `auth_store/_devices.py` (trusted-device helpers — verbatim move)

**Analog:** `auth_store.py` lines 266–382

Move verbatim. Update imports to pull from `auth_store._io` and `auth_store._schema`. Add module-level `logger = logging.getLogger(__name__)`.

**Import block to add at top**:
```python
import logging
import uuid as _uuid
from datetime import datetime, timezone
from pathlib import Path

from auth_store._io import load_auth, save_auth, _resolve_path
from auth_store._schema import TrustedDevice

logger = logging.getLogger(__name__)
```

**load→mutate→save pattern** (`auth_store.py` lines 279–298 — representative):
```python
def add_trusted_device(label: str, path: Path | None = None) -> str:
  new_uuid = _uuid.uuid4().hex
  now_iso = datetime.now(timezone.utc).isoformat()
  data = load_auth(path=path)
  data['trusted_devices'].append({...})
  save_auth(data, path=path)
  logger.info('[Auth] trusted_device added: uuid=%s label=%s', new_uuid, label)
  return new_uuid
```

---

### `auth_store/_magic_links.py` (magic-link helpers — verbatim move)

**Analog:** `auth_store.py` lines 385–520

Move verbatim. Update imports identically to `_devices.py`.

**Import block to add at top**:
```python
import hashlib
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from auth_store._io import load_auth, save_auth, _resolve_path
from auth_store._schema import PendingMagicLink, _ensure_aware

logger = logging.getLogger(__name__)
```

**Token hash pattern used in consume_magic_link** (`auth_store.py` lines 448–450):
```python
token_hash = hashlib.sha256(
  unhashed_token.encode('utf-8'),
).hexdigest()
```
NOTE: `consume_magic_link` stores bare hexdigest (no prefix). `_users.py` stores `"sha256:<hex>"` prefix-tagged per D-08. Do NOT unify — they are separate fields with separate precedents.

---

### `auth_store/_users.py` (new user + invite helpers)

**Analog (load→mutate→save):** `auth_store.py` lines 279–298 (`add_trusted_device`)
**Analog (flock window):** `state_manager/__init__.py` lines 371–382 (`mutate_state`)

**Import block**:
```python
import fcntl
import hashlib
import hmac
import json
import logging
import os
import secrets
import uuid as _uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from auth_store._io import (
  load_auth, save_auth, _resolve_path, _atomic_write_unlocked,
)
from auth_store._schema import AuthData, User, PendingInvite, _ensure_aware

logger = logging.getLogger(__name__)
```

**uid generation pattern** (`auth_store.py` line 286 — reuse verbatim):
```python
uid = _uuid.uuid4().hex
```

**ISO timestamp pattern** (`auth_store.py` line 287 — reuse verbatim):
```python
now_iso = datetime.now(timezone.utc).isoformat()
```

**create_user pattern** (D-03 — no flock; mirrors `add_trusted_device` at `auth_store.py` lines 279–298):
```python
def create_user(fields: dict, path: Path | None = None) -> User:
  uid = _uuid.uuid4().hex
  now_iso = datetime.now(timezone.utc).isoformat()
  user: User = {
    'uid': uid,
    'email': fields['email'],
    'role': fields.get('role', 'ff'),
    'created_at': now_iso,
    'disabled': False,
  }
  data = load_auth(path=path)
  data.setdefault('users', []).append(user)
  save_auth(data, path=path)
  logger.info('[Auth] user created: uid=%s email=%s role=%s', uid, user['email'], user['role'])
  return user
```

**mint_invite_token pattern** (D-03 — no flock; mirrors load→mutate→save):
```python
def mint_invite_token(invited_by_uid: str, email: str, path: Path | None = None) -> tuple[str, str]:
  raw = secrets.token_urlsafe(32)
  token_hash = 'sha256:' + hashlib.sha256(raw.encode()).hexdigest()
  now = datetime.now(timezone.utc)
  expires = now + timedelta(days=7)
  invite: PendingInvite = {
    'token_hash': token_hash,
    'email': email,
    'invited_by': invited_by_uid,
    'created_at': now.isoformat(),
    'expires_at': expires.isoformat(),
    'consumed': False,
    'consumed_at': None,
  }
  data = load_auth(path=path)
  data.setdefault('pending_invites', []).append(invite)
  save_auth(data, path=path)
  logger.info('[Auth] invite minted: email=%s expires=%s', email, expires.isoformat())
  return raw, expires.isoformat()
```

**consume_and_create_user flock pattern** (D-01/D-02/D-04 — mirrors `state_manager/__init__.py` lines 371–382 exactly):
```python
# state_manager/__init__.py lines 371–382 — the canonical flock window to copy:
#   fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
#   try:
#     fcntl.flock(fd, fcntl.LOCK_EX)
#     try:
#       state = load_state(path=path, _under_lock=True)
#       mutator(state)
#       io._save_state_unlocked(state, path=path)   # <-- unlocked write, avoids deadlock
#       return state
#     finally:
#       fcntl.flock(fd, fcntl.LOCK_UN)
#   finally:
#     os.close(fd)

def consume_and_create_user(
  unhashed_token: str, new_user_fields: dict, path: Path | None = None,
) -> User:
  resolved = _resolve_path(path)
  lock_fd = os.open(str(resolved), os.O_RDWR | os.O_CREAT, 0o600)
  try:
    fcntl.flock(lock_fd, fcntl.LOCK_EX)
    try:
      data = _load_auth_raw(resolved)   # raw JSON load, no flock (avoids deadlock)
      computed = 'sha256:' + hashlib.sha256(unhashed_token.encode()).hexdigest()
      invite = None
      for row in data.get('pending_invites', []):
        if hmac.compare_digest(row['token_hash'], computed):
          invite = row
          break
      if invite is None or invite['consumed']:
        raise ValueError('invalid or already consumed invite token')
      now = datetime.now(timezone.utc)
      expires = _ensure_aware(datetime.fromisoformat(invite['expires_at']))
      if expires < now:
        raise ValueError('invite token expired')
      invite['consumed'] = True
      invite['consumed_at'] = now.isoformat()
      user: User = {
        'uid': _uuid.uuid4().hex,
        'email': new_user_fields['email'],
        'role': new_user_fields.get('role', 'ff'),
        'created_at': now.isoformat(),
        'disabled': False,
      }
      data.setdefault('users', []).append(user)
      payload = json.dumps(data, indent=2, ensure_ascii=False) + '\n'
      _atomic_write_unlocked(payload, resolved)   # MUST use unlocked — we hold LOCK_EX
      return user
    finally:
      fcntl.flock(lock_fd, fcntl.LOCK_UN)
  finally:
    os.close(lock_fd)
```

**CRITICAL:** Inside the flock window, call `_atomic_write_unlocked` directly — NEVER `save_auth()` or `_atomic_write()`. `save_auth()` calls `_atomic_write()` which tries to acquire LOCK_EX again from a different fd — POSIX flock deadlocks. This is the same reason `state_manager.mutate_state` calls `io._save_state_unlocked` rather than `save_state`. See `state_manager/io.py` lines 172–201 docstring.

**_load_auth_raw helper** (needed inside flock window — raw file read, no flock recursion):
```python
def _load_auth_raw(resolved: Path) -> dict:
  '''Load auth.json without acquiring any lock. Only called from within an
  already-held LOCK_EX window (consume_and_create_user). Mirrors the pattern
  in state_manager.__init__::mutate_state which calls load_state(_under_lock=True).
  '''
  if not resolved.exists():
    from auth_store._schema import _default_auth_data
    return _default_auth_data()
  return json.loads(resolved.read_text(encoding='utf-8'))
```

**get_user, list_users, set_user_disabled** (load-only or load→mutate→save; mirror `get_trusted_device` / `revoke_device` patterns from `auth_store.py` lines 343–382):
```python
def get_user(uid: str, path: Path | None = None) -> User | None:
  data = load_auth(path=path)
  for row in data.get('users', []):
    if row['uid'] == uid:
      return row
  return None

def list_users(path: Path | None = None) -> list[User]:
  return load_auth(path=path).get('users', [])

def set_user_disabled(uid: str, disabled: bool, path: Path | None = None) -> None:
  data = load_auth(path=path)
  changed = False
  for row in data.get('users', []):
    if row['uid'] == uid:
      row['disabled'] = disabled
      changed = True
      break
  if changed:
    save_auth(data, path=path)
    logger.info('[Auth] user %s disabled=%s', uid, disabled)
```

---

### `tests/test_auth_store.py` (modify: TestForbiddenImports only)

**Analog:** `tests/test_auth_store.py` lines 27–27 and 587–621

**Line 27 — path constant update** (RESEARCH Pitfall 2):
```python
# Before:
AUTH_STORE_PATH = Path('auth_store.py')

# After:
AUTH_STORE_PACKAGE = Path('auth_store')
```

**TestForbiddenImports update** (lines 587–621 — swap single-file read for package walk):
```python
class TestForbiddenImports:
  FORBIDDEN_ROOTS = frozenset({
    'web', 'signal_engine', 'sizing_engine', 'notifier', 'dashboard', 'main',
  })

  def test_auth_store_does_not_import_web_or_signal_layers(self):
    violations = []
    for py_file in AUTH_STORE_PACKAGE.glob('*.py'):
      src = py_file.read_text()
      tree = ast.parse(src)
      for node in ast.walk(tree):
        if isinstance(node, ast.Import):
          for alias in node.names:
            root = alias.name.split('.', 1)[0]
            if root in self.FORBIDDEN_ROOTS:
              violations.append(f'{py_file}:{node.lineno}: import {alias.name}')
        elif isinstance(node, ast.ImportFrom):
          if node.module is None:
            continue
          root = node.module.split('.', 1)[0]
          if root in self.FORBIDDEN_ROOTS:
            violations.append(f'{py_file}:{node.lineno}: from {node.module} import ...')
    assert violations == [], (
      f'auth_store package must not import from web/signal/sizing layers: {violations}'
    )
```

---

### `tests/test_auth_store_users.py` (new file — Phase 34 user/invite tests)

**Analog:** `tests/test_auth_store.py` overall structure — fixtures, class grouping, `isolated_auth_json`, `tmp_auth_path`

**Import + fixture block** (`tests/test_auth_store.py` lines 1–37):
```python
import json
import re
from pathlib import Path

import pytest

ISO_8601_RE = re.compile(
  r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(\+\d{2}:\d{2}|Z)?$',
)

@pytest.fixture
def tmp_auth_path(tmp_path) -> Path:
  return tmp_path / 'auth.json'
```

**Fixture reuse from conftest** (`tests/conftest.py` lines 138–159):
```python
# isolated_auth_json is defined in conftest — just declare it as a parameter:
def test_something(self, isolated_auth_json):
  import auth_store
  # auth_store.DEFAULT_AUTH_PATH is monkeypatched to isolated_auth_json
  ...
```

**Test class structure** (mirrors `TestTrustedDevices` and `TestMagicLinks` patterns in `test_auth_store.py`):
```python
class TestSchemaV2Migration:
  def test_v1_to_v2_backfills_users_and_pending_invites(self, tmp_auth_path): ...
  def test_v2_load_does_not_auto_insert_admin(self, tmp_auth_path): ...

class TestUserRegistry:
  def test_create_user_appends_row(self, isolated_auth_json): ...
  def test_get_user_returns_row(self, isolated_auth_json): ...
  def test_list_users_empty(self, isolated_auth_json): ...
  def test_set_user_disabled_flips_flag(self, isolated_auth_json): ...
  def test_set_user_disabled_preserves_record(self, isolated_auth_json): ...

class TestInviteConsume:
  def test_mint_invite_token_stores_hash_not_raw(self, isolated_auth_json): ...
  def test_consume_and_create_user_single_use(self, isolated_auth_json): ...
  def test_consume_expired_invite_raises(self, isolated_auth_json): ...
  def test_consume_already_consumed_raises(self, isolated_auth_json): ...
  def test_timing_safe_compare(self, isolated_auth_json): ...
```

---

## Shared Patterns

### `[Auth]` log prefix
**Source:** `auth_store.py` lines 251, 298, 319, 339, 431, 467, 519
**Apply to:** All new helpers in `_users.py`, `_devices.py`, `_magic_links.py`
```python
logger.info('[Auth] user created: uid=%s email=%s role=%s', uid, user['email'], user['role'])
```

### load→mutate→save (non-flock path)
**Source:** `auth_store.py` lines 279–298 (`add_trusted_device`)
**Apply to:** `create_user`, `mint_invite_token`, `get_user`, `list_users`, `set_user_disabled`
```python
data = load_auth(path=path)
data['<key>'].append({...})   # or mutate
save_auth(data, path=path)
```

### `path: Path | None = None` kwarg + `_resolve_path`
**Source:** `auth_store.py` lines 169–178
**Apply to:** Every public helper in every daughter module
```python
def _resolve_path(path: Path | None) -> Path:
  from auth_store import DEFAULT_AUTH_PATH
  return path if path is not None else DEFAULT_AUTH_PATH
```

### Idempotent mutations (no-op on unknown id)
**Source:** `auth_store.py` lines 302–318 (`revoke_device`), lines 354–369 (`update_last_seen`)
**Apply to:** `set_user_disabled` — unknown uid is a no-op
```python
changed = False
for row in data.get('users', []):
  if row['uid'] == uid:
    row['disabled'] = disabled
    changed = True
    break
if changed:
  save_auth(data, path=path)
```

### Atomic write (no lock) — public save path
**Source:** `auth_store.py` lines 122–161
**Apply to:** `save_auth` in `_io.py` (via `_atomic_write`)

### Atomic write (caller holds LOCK_EX) — flock path
**Source:** `state_manager/io.py` lines 118–169 (`_atomic_write_unlocked`)
**Apply to:** `consume_and_create_user` inner write in `_users.py` (via `_atomic_write_unlocked`)

### flock window structure
**Source:** `state_manager/__init__.py` lines 371–382 (`mutate_state`)
**Apply to:** `consume_and_create_user` outer lock acquisition
```python
fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
try:
  fcntl.flock(fd, fcntl.LOCK_EX)
  try:
    ...
    _atomic_write_unlocked(payload, resolved)  # never save_auth() inside here
  finally:
    fcntl.flock(fd, fcntl.LOCK_UN)
finally:
  os.close(fd)
```

### ISO 8601 UTC timestamp
**Source:** `auth_store.py` line 287, 419
**Apply to:** All `created_at`, `expires_at`, `consumed_at` fields
```python
datetime.now(timezone.utc).isoformat()
```

### Expiry calculation
**Source:** `auth_store.py` lines 504–505 (`purge_expired_magic_links` cutoff)
**Apply to:** `expires_at` in `mint_invite_token`
```python
expires = datetime.now(timezone.utc) + timedelta(days=7)
```

### Token hash prefix-tagged
**Apply to:** `pending_invites[].token_hash` in `_users.py` only
```python
token_hash = 'sha256:' + hashlib.sha256(raw.encode()).hexdigest()
```
NOTE: `consume_magic_link` uses bare hexdigest (no prefix). Do NOT change it.

---

## No Analog Found

None. All files have direct analogs in the codebase.

---

## Metadata

**Analog search scope:** repo root, `auth_store.py`, `state_manager/`, `tests/`
**Files scanned:** 6 source files + 2 test files
**Pattern extraction date:** 2026-05-13
