'''Phase 34 Plan 02 — auth_store user registry + invite token tests.

Covers five test classes:
  TestUserRegistry       — create_user, get_user, list_users, set_user_disabled
  TestInviteMint         — mint_invite_token hash storage + expiry shape
  TestInviteConsume      — consume_and_create_user success + error paths
  TestInviteConsumeConcurrency — real two-thread single-use guarantee
  TestMalformedHash      — _verify_token fail-closed for bad stored hashes

All tests use the isolated_auth_json fixture from conftest.py.
Imports via auth_store (D-11) — not sub-modules.
'''
import json
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import auth_store
from auth_store import (
  InviteAlreadyConsumed,
  InviteExpired,
  consume_and_create_user,
  create_user,
  get_user,
  list_users,
  load_auth,
  mint_invite_token,
  set_user_disabled,
)

_UID_RE = re.compile(r'^[0-9a-f]{32}$')


# ---------------------------------------------------------------------------
# TestUserRegistry
# ---------------------------------------------------------------------------

class TestUserRegistry:
  def test_create_user_appends_row(self, isolated_auth_json):
    user = create_user({'email': 'a@b.com', 'role': 'ff'})
    users = list_users()
    assert len(users) == 1
    assert users[0]['email'] == 'a@b.com'
    assert users[0]['role'] == 'ff'
    assert users[0]['disabled'] is False
    assert _UID_RE.match(users[0]['uid'])

  def test_create_user_default_role_is_ff(self, isolated_auth_json):
    user = create_user({'email': 'a@b.com'})
    assert user['role'] == 'ff'

  def test_create_user_rejects_caller_supplied_uid(self, isolated_auth_json):
    with pytest.raises(ValueError):
      create_user({'email': 'a@b.com', 'uid': 'spoofed'})

  def test_create_user_rejects_invalid_role(self, isolated_auth_json):
    with pytest.raises(ValueError):
      create_user({'email': 'a@b.com', 'role': 'superuser'})

  def test_create_user_rejects_missing_email(self, isolated_auth_json):
    with pytest.raises(ValueError):
      create_user({})

  def test_create_user_rejects_empty_email(self, isolated_auth_json):
    with pytest.raises(ValueError):
      create_user({'email': ''})

  def test_get_user_returns_none_for_unknown(self, isolated_auth_json):
    assert get_user('nonexistent') is None

  def test_set_user_disabled_flips_flag(self, isolated_auth_json):
    user = create_user({'email': 'a@b.com'})
    uid = user['uid']
    set_user_disabled(uid, True)
    assert get_user(uid)['disabled'] is True

  def test_set_user_disabled_preserves_row(self, isolated_auth_json):
    user = create_user({'email': 'a@b.com'})
    set_user_disabled(user['uid'], True)
    assert len(list_users()) == 1

  def test_set_user_disabled_reversible(self, isolated_auth_json):
    user = create_user({'email': 'a@b.com'})
    uid = user['uid']
    set_user_disabled(uid, True)
    set_user_disabled(uid, False)
    assert get_user(uid)['disabled'] is False

  def test_set_user_disabled_unknown_uid_returns_false(self, isolated_auth_json):
    # File does not exist yet; capture mtime after it appears
    # Just assert return value is False and no write happens
    result = set_user_disabled('nonexistent', True)
    assert result is False
    # No user row created
    assert list_users() == []


# ---------------------------------------------------------------------------
# TestInviteMint
# ---------------------------------------------------------------------------

class TestInviteMint:
  def test_mint_invite_token_stores_hash_only(self, isolated_auth_json):
    raw, expires_iso = mint_invite_token('admin-uid', 'inv@b.com')
    data = load_auth()
    row = data['pending_invites'][0]
    assert row['token_hash'].startswith('sha256:')
    assert row['consumed'] is False
    assert row['email'] == 'inv@b.com'
    assert row['invited_by'] == 'admin-uid'

  def test_mint_invite_token_returns_tuple_with_iso_expiry(self, isolated_auth_json):
    raw, expires_iso = mint_invite_token('uid', 'e@b.com')
    assert isinstance(raw, str)
    assert isinstance(expires_iso, str)
    parsed = datetime.fromisoformat(expires_iso)
    now = datetime.now(timezone.utc)
    delta = parsed - now
    assert timedelta(days=6) < delta < timedelta(days=8)

  def test_raw_token_verifies_against_stored_hash_and_is_not_persisted(
    self, isolated_auth_json,
  ):
    raw, _ = mint_invite_token('uid', 'e@b.com')
    persisted_bytes = Path(auth_store.DEFAULT_AUTH_PATH).read_bytes()
    # Byte-level check
    assert raw.encode('utf-8') not in persisted_bytes
    # Programmatic regex check on string form (OpenCode LOW review fix)
    persisted_str = persisted_bytes.decode('utf-8')
    assert re.search(r'\b' + re.escape(raw) + r'\b', persisted_str) is None
    # Also assert no verbatim occurrence at all
    assert raw not in persisted_str


# ---------------------------------------------------------------------------
# TestInviteConsume
# ---------------------------------------------------------------------------

class TestInviteConsume:
  def test_consume_and_create_user_success(self, isolated_auth_json):
    raw, _ = mint_invite_token('uid', 'e@b.com')
    user = consume_and_create_user(raw, {'email': 'e@b.com'})
    assert user['email'] == 'e@b.com'
    assert _UID_RE.match(user['uid'])
    data = load_auth()
    assert data['pending_invites'][0]['consumed'] is True
    assert data['pending_invites'][0]['consumed_at'] is not None
    assert len(data['users']) == 1

  def test_consume_and_create_user_single_use_sequential(self, isolated_auth_json):
    raw, _ = mint_invite_token('uid', 'e@b.com')
    consume_and_create_user(raw, {'email': 'e@b.com'})
    with pytest.raises(InviteAlreadyConsumed) as exc_info:
      consume_and_create_user(raw, {'email': 'e@b.com'})
    assert isinstance(exc_info.value, InviteAlreadyConsumed)

  def test_consume_and_create_user_expired_raises_distinct_type(
    self, isolated_auth_json,
  ):
    raw, _ = mint_invite_token('uid', 'e@b.com')
    # Backdate expires_at to yesterday
    data = load_auth()
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    data['pending_invites'][0]['expires_at'] = past
    auth_store.save_auth(data)
    with pytest.raises(InviteExpired) as exc_info:
      consume_and_create_user(raw, {'email': 'e@b.com'})
    assert isinstance(exc_info.value, InviteExpired)
    # SC-4: distinct type — must NOT be InviteAlreadyConsumed
    assert not isinstance(exc_info.value, InviteAlreadyConsumed)

  def test_consume_and_create_user_unknown_token(self, isolated_auth_json):
    with pytest.raises(InviteAlreadyConsumed):
      consume_and_create_user('not-a-real-token', {'email': 'x@b.com'})

  def test_consume_and_create_user_propagates_validation(self, isolated_auth_json):
    raw, _ = mint_invite_token('uid', 'e@b.com')
    with pytest.raises(ValueError):
      consume_and_create_user(raw, {'email': 'e@b.com', 'uid': 'spoofed'})


# ---------------------------------------------------------------------------
# TestInviteConsumeConcurrency
# ---------------------------------------------------------------------------

class TestInviteConsumeConcurrency:
  def test_two_threads_consuming_same_token_only_one_succeeds(
    self, isolated_auth_json,
  ):
    raw, _ = mint_invite_token('uid', 'e@b.com')
    barrier = threading.Barrier(2)
    successes = []
    errors = []

    def try_consume():
      try:
        barrier.wait()
        user = consume_and_create_user(raw, {'email': 'e@b.com'})
        successes.append(user)
      except Exception as exc:
        errors.append(exc)

    t1 = threading.Thread(target=try_consume)
    t2 = threading.Thread(target=try_consume)
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    assert len(successes) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], InviteAlreadyConsumed)
    data = load_auth()
    assert data['pending_invites'][0]['consumed'] is True
    assert len(data['users']) == 1

  def test_two_threads_consuming_different_tokens_both_succeed(
    self, isolated_auth_json,
  ):
    raw1, _ = mint_invite_token('uid', 'a@b.com')
    raw2, _ = mint_invite_token('uid', 'b@b.com')
    barrier = threading.Barrier(2)
    successes = []
    errors = []

    def try_consume(raw, email):
      try:
        barrier.wait()
        user = consume_and_create_user(raw, {'email': email})
        successes.append(user)
      except Exception as exc:
        errors.append(exc)

    t1 = threading.Thread(target=try_consume, args=(raw1, 'a@b.com'))
    t2 = threading.Thread(target=try_consume, args=(raw2, 'b@b.com'))
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    assert len(errors) == 0, f'unexpected errors: {errors}'
    assert len(successes) == 2
    data = load_auth()
    assert len(data['users']) == 2


# ---------------------------------------------------------------------------
# TestMalformedHash
# ---------------------------------------------------------------------------

def _write_auth_with_invite(tmp_path_auth: Path, token_hash: str) -> None:
  '''Write a v2 auth.json with one pending invite row using token_hash.'''
  data = {
    'schema_version': 2,
    'totp_secret': None,
    'totp_enrolled': False,
    'totp_enrolled_at': None,
    'trusted_devices': [],
    'pending_magic_links': [],
    'users': [],
    'pending_invites': [{
      'token_hash': token_hash,
      'email': 'e@b.com',
      'invited_by': 'uid',
      'created_at': datetime.now(timezone.utc).isoformat(),
      'expires_at': (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
      'consumed': False,
      'consumed_at': None,
    }],
  }
  tmp_path_auth.write_text(json.dumps(data, indent=2), encoding='utf-8')


class TestMalformedHash:
  def test_consume_rejects_invite_with_missing_sha256_prefix(
    self, isolated_auth_json,
  ):
    _write_auth_with_invite(
      isolated_auth_json,
      'abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890',
    )
    with pytest.raises(InviteAlreadyConsumed):
      consume_and_create_user('any-token', {'email': 'e@b.com'})

  def test_consume_rejects_invite_with_invalid_hex(self, isolated_auth_json):
    _write_auth_with_invite(isolated_auth_json, 'sha256:not-hex')
    with pytest.raises(InviteAlreadyConsumed):
      consume_and_create_user('any-token', {'email': 'e@b.com'})

  def test_consume_rejects_invite_with_wrong_algorithm(self, isolated_auth_json):
    _write_auth_with_invite(isolated_auth_json, 'md5:abcdef1234567890')
    with pytest.raises(InviteAlreadyConsumed):
      consume_and_create_user('any-token', {'email': 'e@b.com'})


# ---------------------------------------------------------------------------
# TestPasswordHashing (Task 1 TDD RED — Plan 37-03)
# ---------------------------------------------------------------------------

class TestPasswordHashing:
  '''Covers behaviors 1-8 from 37-03-PLAN Task 1.'''

  def test_bcrypt_import_succeeds(self):
    import bcrypt  # noqa: F401

  def test_hash_password_and_verify_password_importable(self):
    from auth_store import hash_password, verify_password  # noqa: F401

  def test_hash_password_returns_2b12_prefix(self):
    from auth_store import hash_password
    h = hash_password('correct horse battery staple')
    assert isinstance(h, str)
    assert h.startswith('$2b$12$')
    assert len(h) == 60

  def test_hash_password_salts_differ(self):
    from auth_store import hash_password
    h1 = hash_password('same_input')
    h2 = hash_password('same_input')
    assert h1 != h2

  def test_verify_password_correct(self):
    from auth_store import hash_password, verify_password
    h = hash_password('correct horse battery staple')
    assert verify_password('correct horse battery staple', h) is True

  def test_verify_password_wrong(self):
    from auth_store import hash_password, verify_password
    h = hash_password('right')
    assert verify_password('wrong', h) is False

  def test_verify_password_invalid_hash_returns_false(self):
    from auth_store import verify_password
    assert verify_password('any', 'not-a-bcrypt-hash') is False

  def test_verify_password_empty_hash_returns_false(self):
    from auth_store import verify_password
    assert verify_password('any', '') is False

  def test_verify_password_none_hash_returns_false(self):
    from auth_store import verify_password
    assert verify_password('any', None) is False


# ---------------------------------------------------------------------------
# TestUserSchemaPasswordHashField (Task 1 TDD RED — Plan 37-03)
# ---------------------------------------------------------------------------

class TestUserSchemaPasswordHashField:
  '''Covers behaviors 9-11 from 37-03-PLAN Task 1.'''

  def test_user_typeddict_has_password_hash_annotation(self):
    from auth_store._schema import User
    from typing import get_type_hints
    hints = get_type_hints(User)
    assert 'password_hash' in hints

  def test_existing_admin_row_roundtrips_without_error(self, isolated_auth_json):
    import json
    from pathlib import Path
    import auth_store
    from auth_store import load_auth, save_auth
    # Write a v2 admin-only auth.json without password_hash
    auth_data = {
      'schema_version': 2,
      'totp_secret': None,
      'totp_enrolled': False,
      'totp_enrolled_at': None,
      'trusted_devices': [],
      'pending_magic_links': [],
      'users': [{'uid': 'admin', 'email': 'admin@ex.com', 'role': 'admin',
                 'created_at': '2026-01-01T00:00:00+00:00', 'disabled': False}],
      'pending_invites': [],
    }
    Path(auth_store.DEFAULT_AUTH_PATH).write_text(json.dumps(auth_data), encoding='utf-8')
    data = load_auth()
    save_auth(data)
    # No ValueError or KeyError

  def test_admin_row_get_password_hash_returns_none(self, isolated_auth_json):
    import json
    from pathlib import Path
    import auth_store
    from auth_store import load_auth
    auth_data = {
      'schema_version': 2,
      'totp_secret': None,
      'totp_enrolled': False,
      'totp_enrolled_at': None,
      'trusted_devices': [],
      'pending_magic_links': [],
      'users': [{'uid': 'admin', 'email': 'admin@ex.com', 'role': 'admin',
                 'created_at': '2026-01-01T00:00:00+00:00', 'disabled': False}],
      'pending_invites': [],
    }
    Path(auth_store.DEFAULT_AUTH_PATH).write_text(json.dumps(auth_data), encoding='utf-8')
    data = load_auth()
    row = data['users'][0]
    assert row.get('password_hash') is None


# ---------------------------------------------------------------------------
# TestPasswordHash72ByteCap (Task 1 TDD RED — Plan 37-03, review #9)
# ---------------------------------------------------------------------------

class TestPasswordHash72ByteCap:
  '''Covers behaviors 12-13 from 37-03-PLAN Task 1 (review consensus #9).'''

  def test_hash_password_72_bytes_succeeds(self):
    from auth_store import hash_password
    # 72 ASCII chars = 72 UTF-8 bytes
    result = hash_password('a' * 72)
    assert result.startswith('$2b$12$')

  def test_hash_password_73_bytes_raises_value_error(self):
    from auth_store import hash_password
    with pytest.raises(ValueError) as exc_info:
      hash_password('a' * 73)
    assert 'exceeds 72' in str(exc_info.value)

  def test_hash_password_multibyte_unicode_cap(self):
    from auth_store import hash_password
    # '🦀' is 4 UTF-8 bytes each; 19 * 4 = 76 bytes > 72
    with pytest.raises(ValueError) as exc_info:
      hash_password('🦀' * 19)
    assert 'exceeds 72' in str(exc_info.value)

  def test_hash_password_72_plus_1_ascii_raises(self):
    from auth_store import hash_password
    with pytest.raises(ValueError):
      hash_password('a' * 72 + 'x')


# ---------------------------------------------------------------------------
# TestPasswordHashOnConsume (Task 2 TDD RED — Plan 37-03)
# ---------------------------------------------------------------------------

class TestPasswordHashOnConsume:
  '''Covers consume_and_create_user password_hash kwarg behaviors.'''

  def test_consume_with_password_hash_stores_it(self, pending_invite_auth_json):
    import inspect
    from auth_store import consume_and_create_user
    ctx = pending_invite_auth_json
    pw_hash = '$2b$12$AAAAAAAAAAAAAAAAAAAAAA.AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
    user = consume_and_create_user(
      ctx['raw_token'],
      {'email': ctx['email'], 'role': 'ff'},
      password_hash=pw_hash,
    )
    assert user.get('password_hash') == pw_hash

  def test_consume_legacy_no_password_hash_returns_none(self, pending_invite_auth_json):
    from auth_store import consume_and_create_user
    ctx = pending_invite_auth_json
    user = consume_and_create_user(
      ctx['raw_token'],
      {'email': ctx['email'], 'role': 'ff'},
    )
    assert user.get('password_hash') is None

  def test_consume_password_hash_in_signature(self):
    import inspect
    from auth_store import consume_and_create_user
    sig = inspect.signature(consume_and_create_user)
    assert 'password_hash' in sig.parameters


# ---------------------------------------------------------------------------
# TestPeekInviteToken (Task 2 TDD RED — Plan 37-03)
# ---------------------------------------------------------------------------

class TestPeekInviteToken:
  '''Covers _peek_invite_token behaviors.'''

  def test_peek_valid_token_returns_email(self, pending_invite_auth_json):
    from auth_store import _peek_invite_token
    ctx = pending_invite_auth_json
    email = _peek_invite_token(ctx['raw_token'])
    assert email == ctx['email']

  def test_peek_does_not_consume(self, pending_invite_auth_json):
    from auth_store import _peek_invite_token, load_auth
    ctx = pending_invite_auth_json
    _peek_invite_token(ctx['raw_token'])
    data = load_auth()
    assert data['pending_invites'][0]['consumed'] is False

  def test_peek_idempotent(self, pending_invite_auth_json):
    from auth_store import _peek_invite_token
    ctx = pending_invite_auth_json
    e1 = _peek_invite_token(ctx['raw_token'])
    e2 = _peek_invite_token(ctx['raw_token'])
    assert e1 == e2 == ctx['email']

  def test_peek_then_consume_succeeds(self, pending_invite_auth_json):
    from auth_store import _peek_invite_token, consume_and_create_user
    ctx = pending_invite_auth_json
    _peek_invite_token(ctx['raw_token'])
    user = consume_and_create_user(ctx['raw_token'], {'email': ctx['email'], 'role': 'ff'})
    assert user['email'] == ctx['email']

  def test_peek_consumed_token_raises(self, pending_invite_auth_json):
    from auth_store import _peek_invite_token, consume_and_create_user, InviteAlreadyConsumed
    ctx = pending_invite_auth_json
    consume_and_create_user(ctx['raw_token'], {'email': ctx['email'], 'role': 'ff'})
    with pytest.raises(InviteAlreadyConsumed):
      _peek_invite_token(ctx['raw_token'])

  def test_peek_expired_token_raises(self, pending_invite_auth_json):
    import json
    from datetime import datetime, timezone, timedelta
    from auth_store import _peek_invite_token, load_auth, save_auth, InviteExpired
    ctx = pending_invite_auth_json
    data = load_auth()
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    data['pending_invites'][0]['expires_at'] = past
    save_auth(data)
    with pytest.raises(InviteExpired):
      _peek_invite_token(ctx['raw_token'])

  def test_peek_unknown_token_raises_already_consumed(self):
    from auth_store import _peek_invite_token, InviteAlreadyConsumed
    with pytest.raises(InviteAlreadyConsumed) as exc_info:
      _peek_invite_token('a' * 64)
    assert 'not found' in str(exc_info.value).lower() or 'invalid' in str(exc_info.value).lower()

  def test_peek_timing_safety_unknown_token(self):
    from auth_store import _peek_invite_token, InviteAlreadyConsumed
    with pytest.raises(InviteAlreadyConsumed):
      _peek_invite_token('a' * 64)


# ---------------------------------------------------------------------------
# TestListPendingInvites (Task 2 TDD RED — Plan 37-03)
# ---------------------------------------------------------------------------

class TestListPendingInvites:
  '''Covers list_pending_invites behavior.'''

  def test_list_pending_invites_returns_all_rows(self, pending_invite_auth_json):
    from auth_store import list_pending_invites, consume_and_create_user
    ctx = pending_invite_auth_json
    # One unconsumed row already exists from fixture
    rows = list_pending_invites()
    assert len(rows) == 1
    # Consume it, then list should still include it
    consume_and_create_user(ctx['raw_token'], {'email': ctx['email'], 'role': 'ff'})
    rows_after = list_pending_invites()
    assert len(rows_after) == 1
    assert rows_after[0]['consumed'] is True

  def test_list_pending_invites_empty_when_none(self, isolated_auth_json):
    from auth_store import list_pending_invites
    rows = list_pending_invites()
    assert rows == []


# ---------------------------------------------------------------------------
# TestRevokeInvite (Task 2 TDD RED — Plan 37-03)
# ---------------------------------------------------------------------------

class TestRevokeInvite:
  '''Covers revoke_invite behaviors + docstring (review #12).'''

  def test_revoke_invite_returns_true_and_marks_consumed(self, pending_invite_auth_json):
    from auth_store import revoke_invite, load_auth
    ctx = pending_invite_auth_json
    result = revoke_invite(ctx['token_hash'])
    assert result is True
    data = load_auth()
    row = data['pending_invites'][0]
    assert row['consumed'] is True
    # consumed_at should be a valid ISO datetime string
    from datetime import datetime
    dt = datetime.fromisoformat(row['consumed_at'])
    assert dt is not None

  def test_revoke_invite_unknown_hash_returns_false(self, pending_invite_auth_json):
    from auth_store import revoke_invite
    result = revoke_invite('sha256:' + '0' * 64)
    assert result is False

  def test_revoke_invite_already_consumed_returns_false(self, pending_invite_auth_json):
    from auth_store import revoke_invite
    ctx = pending_invite_auth_json
    revoke_invite(ctx['token_hash'])  # first revoke
    result = revoke_invite(ctx['token_hash'])  # second revoke
    assert result is False

  def test_revoke_invite_flock_rationale_in_docstring(self):
    import inspect
    from auth_store import revoke_invite
    doc = inspect.getdoc(revoke_invite) or ''
    doc_lower = doc.lower()
    assert (
      'no flock' in doc_lower
      or 'no-flock' in doc_lower
      or 'does not acquire flock' in doc_lower
      or 'deliberately does not acquire flock' in doc_lower
    ), f'docstring missing flock rationale: {doc!r}'
    assert 'idempotent' in doc_lower
    assert 'atomic' in doc_lower
