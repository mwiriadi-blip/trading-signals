'''Phase 16.1 Plan 01 Task 1 — auth_store.py atomic-write + schema tests.

auth_store.py is a hex-lite peer of state_manager.py — it owns auth.json
(atomic JSON load/save mirroring state_manager._atomic_write_unlocked).

This file covers:
  - TestAtomicWriteCrash — partial tempfile does not corrupt target on
    fsync mid-write failure
  - TestSchemaV1Init — load_auth() returns the schema-v1 default when
    auth.json is missing; round-trips an existing file by exact dict equality
  - TestTotpSecretRoundTrip — set_totp_secret writes to disk; get_totp_secret
    reads it back
  - TestMarkEnrolled — flips totp_enrolled=True and stamps an ISO 8601 datetime
  - TestForbiddenImports — AST-walks auth_store.py and asserts the hex-boundary
    blocklist (no imports of web/, signal_engine, sizing_engine, notifier,
    dashboard, main)

Reference: 16.1-01-PLAN.md Task 1 (RED-first); 16.1-CONTEXT.md F-01 schema.
'''
import ast
import json
import re
from pathlib import Path

import pytest

AUTH_STORE_PATH = Path('auth_store.py')
ISO_8601_RE = re.compile(
  r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(\+\d{2}:\d{2}|Z)?$',
)


@pytest.fixture
def tmp_auth_path(tmp_path) -> Path:
  '''Fresh per-test path so atomic writes don't collide across tests.'''
  return tmp_path / 'auth.json'


class TestAtomicWriteCrash:
  '''F-01 atomic-write contract: tempfile + fsync + os.replace.

  Mirrors state_manager._atomic_write_unlocked durability semantics. If
  fsync raises mid-write, the target file must remain unchanged AND the
  tempfile must be cleaned up.
  '''

  def test_partial_tempfile_does_not_corrupt_target(
    self, tmp_auth_path, monkeypatch,
  ):
    '''F-01: simulate an fsync failure during save_auth — target file
    on disk must be unchanged AND no .tmp file leaks into the directory.
    '''
    import auth_store
    import os

    # Pre-seed an existing auth.json so we can verify it stays unchanged.
    pre_state = {
      'schema_version': 1, 'totp_secret': 'PRE_EXISTING', 'totp_enrolled': True,
      'totp_enrolled_at': '2026-04-29T08:00:00+00:00',
      'trusted_devices': [], 'pending_magic_links': [],
    }
    tmp_auth_path.write_text(json.dumps(pre_state))
    pre_bytes = tmp_auth_path.read_bytes()

    # Patch os.fsync to raise on its first invocation (mid-write).
    real_fsync = os.fsync
    calls = {'n': 0}

    def boom_fsync(fd):
      calls['n'] += 1
      if calls['n'] == 1:
        raise OSError('simulated fsync failure')
      return real_fsync(fd)

    monkeypatch.setattr(auth_store.os, 'fsync', boom_fsync)

    # Attempt save — expect OSError to propagate (re-raise per F-01 contract;
    # silent save-failures cause data loss, mirroring state_manager).
    with pytest.raises(OSError, match='simulated fsync failure'):
      auth_store.save_auth(
        {**pre_state, 'totp_secret': 'NEW'},
        path=tmp_auth_path,
      )

    # Target unchanged
    assert tmp_auth_path.read_bytes() == pre_bytes, (
      'auth.json must be unchanged when save_auth raises mid-write'
    )

    # No .tmp files leaked
    leftover = list(tmp_auth_path.parent.glob('*.tmp'))
    assert leftover == [], f'Tempfile leaked: {leftover}'


class TestSchemaV1Init:
  '''F-01 schema: load_auth() returns the default v1 dict when no file exists,
  and round-trips an existing file by exact dict equality.
  '''

  def test_load_auth_creates_default_when_missing(self, tmp_auth_path):
    '''F-01: missing file → returns the default schema v1 dict.'''
    import auth_store
    assert not tmp_auth_path.exists()

    data = auth_store.load_auth(path=tmp_auth_path)
    assert data == {
      'schema_version': 1,
      'totp_secret': None,
      'totp_enrolled': False,
      'totp_enrolled_at': None,
      'trusted_devices': [],
      'pending_magic_links': [],
    }, f'Unexpected default shape: {data}'

  def test_load_auth_round_trips_existing_file(self, tmp_auth_path):
    '''F-01: write a valid auth.json, load, assert dict equality.'''
    import auth_store
    payload = {
      'schema_version': 1,
      'totp_secret': 'JBSWY3DPEHPK3PXP',
      'totp_enrolled': True,
      'totp_enrolled_at': '2026-04-29T08:00:00+00:00',
      'trusted_devices': [],
      'pending_magic_links': [],
    }
    tmp_auth_path.write_text(json.dumps(payload))
    assert auth_store.load_auth(path=tmp_auth_path) == payload


class TestTotpSecretRoundTrip:
  '''F-01: set_totp_secret persists via atomic write; get_totp_secret reads it.'''

  def test_set_then_get_totp_secret(self, tmp_auth_path):
    import auth_store
    auth_store.set_totp_secret('JBSWY3DPEHPK3PXP', path=tmp_auth_path)
    assert auth_store.get_totp_secret(path=tmp_auth_path) == 'JBSWY3DPEHPK3PXP'
    on_disk = json.loads(tmp_auth_path.read_text())
    assert on_disk['totp_secret'] == 'JBSWY3DPEHPK3PXP'
    # set_totp_secret resets enrolled=False (in case of re-enrollment)
    assert on_disk['totp_enrolled'] is False


class TestMarkEnrolled:
  '''F-01: mark_enrolled flips the flag and stamps an ISO 8601 datetime.'''

  def test_mark_enrolled_flips_flag_and_stamps_iso8601(self, tmp_auth_path):
    import auth_store
    auth_store.set_totp_secret('JBSWY3DPEHPK3PXP', path=tmp_auth_path)
    pre = auth_store.load_auth(path=tmp_auth_path)
    assert pre['totp_enrolled'] is False
    assert pre['totp_enrolled_at'] is None

    auth_store.mark_enrolled(path=tmp_auth_path)
    post = auth_store.load_auth(path=tmp_auth_path)
    assert post['totp_enrolled'] is True
    assert post['totp_enrolled_at'] is not None
    assert ISO_8601_RE.match(post['totp_enrolled_at']), (
      f'Expected ISO 8601 timestamp, got {post["totp_enrolled_at"]!r}'
    )


class TestTrustedDevices:
  '''Phase 16.1 Plan 02 Task 1 — trusted-device CRUD helpers.

  All tests opt into the shared `isolated_auth_json` fixture (tests/conftest.py)
  which redirects `auth_store.DEFAULT_AUTH_PATH` to a per-test tmp file via
  monkeypatch.setattr. This avoids clobbering the real repo-root auth.json
  AND lets tests use the no-kwarg call shape (mirrors production callers
  which omit the `path` kwarg).
  '''

  def test_add_trusted_device_appends_row_with_correct_shape(
    self, isolated_auth_json,
  ):
    '''F-01: add_trusted_device appends a row with all 6 keys, returns uuid,
    granted_at == last_seen, both ISO 8601 UTC.'''
    import auth_store
    new_uuid = auth_store.add_trusted_device(
      label='iPhone Safari · 203.0.113.x · 2026-04-29',
    )
    assert isinstance(new_uuid, str) and len(new_uuid) == 32  # uuid4().hex

    data = auth_store.load_auth()
    assert len(data['trusted_devices']) == 1
    row = data['trusted_devices'][0]
    assert set(row.keys()) == {
      'uuid', 'label', 'granted_at', 'last_seen', 'revoked', 'revoked_at',
    }
    assert row['uuid'] == new_uuid
    assert row['label'] == 'iPhone Safari · 203.0.113.x · 2026-04-29'
    assert row['revoked'] is False
    assert row['revoked_at'] is None
    assert row['granted_at'] == row['last_seen']
    assert ISO_8601_RE.match(row['granted_at']), (
      f'granted_at not ISO 8601: {row["granted_at"]!r}'
    )

  def test_add_trusted_device_returns_unique_uuid_per_call(
    self, isolated_auth_json,
  ):
    '''Three back-to-back calls produce three distinct uuids; auth.json holds 3 rows.'''
    import auth_store
    u1 = auth_store.add_trusted_device(label='A')
    u2 = auth_store.add_trusted_device(label='B')
    u3 = auth_store.add_trusted_device(label='C')
    assert len({u1, u2, u3}) == 3
    data = auth_store.load_auth()
    assert len(data['trusted_devices']) == 3
    assert {r['uuid'] for r in data['trusted_devices']} == {u1, u2, u3}

  def test_revoke_device_flips_flag_and_stamps_revoked_at(
    self, isolated_auth_json,
  ):
    '''Revoke flips revoked=True, stamps revoked_at ISO 8601, retains the row.'''
    import auth_store
    uid = auth_store.add_trusted_device(label='D')
    auth_store.revoke_device(uid)

    data = auth_store.load_auth()
    assert len(data['trusted_devices']) == 1  # row retained for audit
    row = data['trusted_devices'][0]
    assert row['uuid'] == uid
    assert row['revoked'] is True
    assert row['revoked_at'] is not None
    assert ISO_8601_RE.match(row['revoked_at']), (
      f'revoked_at not ISO 8601: {row["revoked_at"]!r}'
    )

  def test_revoke_device_unknown_uuid_is_no_op(self, isolated_auth_json):
    '''Calling revoke_device with a uuid not in auth.json is a silent no-op.'''
    import auth_store
    uid = auth_store.add_trusted_device(label='E')
    pre = auth_store.load_auth()
    auth_store.revoke_device('does-not-exist')  # no-op
    post = auth_store.load_auth()
    assert pre == post
    # The actual row is untouched
    row = post['trusted_devices'][0]
    assert row['uuid'] == uid and row['revoked'] is False

  def test_revoke_device_already_revoked_is_no_op(self, isolated_auth_json):
    '''Calling revoke_device twice on the same uuid is idempotent.'''
    import auth_store
    uid = auth_store.add_trusted_device(label='F')
    auth_store.revoke_device(uid)
    pre = auth_store.load_auth()
    auth_store.revoke_device(uid)  # second call — no-op
    post = auth_store.load_auth()
    # revoked_at must NOT be re-stamped (preserve original revocation time)
    assert pre == post

  def test_revoke_all_other_devices_flips_all_except_named(
    self, isolated_auth_json,
  ):
    '''Add 3 devices; revoke_all_other_devices(except_uuid=B) flips A and C only.'''
    import auth_store
    uid_a = auth_store.add_trusted_device(label='A')
    uid_b = auth_store.add_trusted_device(label='B')
    uid_c = auth_store.add_trusted_device(label='C')
    n = auth_store.revoke_all_other_devices(except_uuid=uid_b)
    assert n == 2

    data = auth_store.load_auth()
    rows = {r['uuid']: r for r in data['trusted_devices']}
    assert rows[uid_a]['revoked'] is True
    assert rows[uid_b]['revoked'] is False
    assert rows[uid_c]['revoked'] is True
    # All 3 rows still present (audit trail)
    assert len(data['trusted_devices']) == 3

  def test_get_trusted_device_returns_row_or_none(self, isolated_auth_json):
    import auth_store
    uid = auth_store.add_trusted_device(label='G')
    row = auth_store.get_trusted_device(uid)
    assert row is not None
    assert row['uuid'] == uid
    assert row['label'] == 'G'
    assert auth_store.get_trusted_device('not-in-store') is None

  def test_update_last_seen_only_updates_last_seen_field(
    self, isolated_auth_json,
  ):
    '''freeze at T0 to add; freeze at T0+1h to update; assert only last_seen advances.'''
    import auth_store
    from freezegun import freeze_time
    with freeze_time('2026-04-29T00:00:00+00:00'):
      uid = auth_store.add_trusted_device(label='H')
    pre = auth_store.get_trusted_device(uid)
    granted_at_before = pre['granted_at']
    last_seen_before = pre['last_seen']

    with freeze_time('2026-04-29T01:00:00+00:00'):
      auth_store.update_last_seen(uid)

    post = auth_store.get_trusted_device(uid)
    assert post['granted_at'] == granted_at_before  # unchanged
    assert post['last_seen'] != last_seen_before    # advanced
    assert post['last_seen'].startswith('2026-04-29T01:00:00')
    assert post['revoked'] is False

  def test_update_last_seen_unknown_uuid_is_no_op(self, isolated_auth_json):
    import auth_store
    uid = auth_store.add_trusted_device(label='I')
    pre = auth_store.load_auth()
    auth_store.update_last_seen('not-in-store')
    post = auth_store.load_auth()
    assert pre == post
    # The real row is unchanged
    assert auth_store.get_trusted_device(uid)['last_seen'] == pre['trusted_devices'][0]['last_seen']

  def test_is_uuid_active_returns_True_for_unrevoked(self, isolated_auth_json):
    import auth_store
    uid = auth_store.add_trusted_device(label='J')
    assert auth_store.is_uuid_active(uid) is True

  def test_is_uuid_active_returns_False_for_revoked(self, isolated_auth_json):
    import auth_store
    uid = auth_store.add_trusted_device(label='K')
    auth_store.revoke_device(uid)
    assert auth_store.is_uuid_active(uid) is False

  def test_is_uuid_active_returns_False_for_unknown_uuid(
    self, isolated_auth_json,
  ):
    import auth_store
    auth_store.add_trusted_device(label='L')  # noise row
    assert auth_store.is_uuid_active('not-in-store') is False

  def test_concurrent_add_does_not_lose_rows(self, isolated_auth_json):
    '''Sanity: tight-loop add_trusted_device doesn't drop rows via load->save races.

    Single-operator tool — there is no real concurrency. This test guards
    the load->mutate->save pattern against accidental list-replacement bugs.
    '''
    import auth_store
    uids = [auth_store.add_trusted_device(label=f'D{i}') for i in range(5)]
    data = auth_store.load_auth()
    assert {r['uuid'] for r in data['trusted_devices']} == set(uids)

  def test_revoked_devices_are_kept_in_auth_json(self, isolated_auth_json):
    '''E-06: revoked rows must be retained for audit, not deleted.'''
    import auth_store
    uid = auth_store.add_trusted_device(label='M')
    auth_store.revoke_device(uid)
    data = auth_store.load_auth()
    # Row remains, just with revoked=True
    assert len(data['trusted_devices']) == 1
    assert data['trusted_devices'][0]['uuid'] == uid
    assert data['trusted_devices'][0]['revoked'] is True


class TestForbiddenImports:
  '''Hex-boundary AST guard: auth_store.py is a peer of state_manager.py
  (NOT inside web/), so it MUST NOT import from web/, signal/sizing engines,
  notifier, dashboard, or main.
  '''

  FORBIDDEN_ROOTS = frozenset({
    'web', 'signal_engine', 'sizing_engine', 'notifier', 'dashboard', 'main',
  })

  def test_auth_store_does_not_import_web_or_signal_layers(self):
    src = AUTH_STORE_PATH.read_text()
    tree = ast.parse(src)
    violations = []
    for node in ast.walk(tree):
      if isinstance(node, ast.Import):
        for alias in node.names:
          root = alias.name.split('.', 1)[0]
          if root in self.FORBIDDEN_ROOTS:
            violations.append(
              f'Line {node.lineno}: import {alias.name}'
            )
      elif isinstance(node, ast.ImportFrom):
        if node.module is None:
          continue
        root = node.module.split('.', 1)[0]
        if root in self.FORBIDDEN_ROOTS:
          violations.append(
            f'Line {node.lineno}: from {node.module} import …'
          )
    assert violations == [], (
      f'auth_store.py must not import from web/signal/sizing layers: '
      f'{violations}'
    )
