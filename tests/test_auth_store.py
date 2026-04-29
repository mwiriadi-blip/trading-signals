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
