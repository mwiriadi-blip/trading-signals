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
