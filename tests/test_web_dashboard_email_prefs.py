'''Phase 37 Plan 05 Task 2 — UMAIL-04 email-prefs route tests.

TestPatchEmailPrefs — PATCH /settings/email-prefs persists email_enabled + pause_until

Uses monkeypatched mutate_user_state to capture writes without real state.json.
Mirrors the pattern used by test_web_admin.py for load_state.
'''
import sys
import pytest


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_prefs_client(monkeypatch, uid='u1-test'):
  '''Build a TestClient with current_user_id overridden to uid.

  Monkeypatches state_manager.mutate_user_state to a capturing stub so tests
  never touch the real state.json. The stub writes to a shared dict that
  the test can inspect after the call.
  '''
  from fastapi.testclient import TestClient
  sys.modules.pop('web.app', None)
  from web.app import create_app
  import state_manager
  from web.dependencies import current_user_id

  # Capture writes: spy['calls'] collects each (uid, callback_result) pair.
  # The stub runs the mutator against a minimal in-memory user state.
  captured_users: dict = {}

  def _fake_mutate_user_state(u, mutator, path=None):
    fake_state = {
      'users': {u: captured_users.setdefault(u, {})},
    }
    mutator(fake_state)
    captured_users[u].update(fake_state['users'][u])

  monkeypatch.setattr(state_manager, 'mutate_user_state', _fake_mutate_user_state)

  # Also stub load_user_state to read from captured dict.
  def _fake_load_user_state(u, path=None):
    return captured_users.get(u, {})

  monkeypatch.setattr(state_manager, 'load_user_state', _fake_load_user_state)

  app = create_app()
  app.dependency_overrides[current_user_id] = lambda: uid

  client = TestClient(app, raise_server_exceptions=False)
  return client, captured_users


# ---------------------------------------------------------------------------
# TestPatchEmailPrefs
# ---------------------------------------------------------------------------

class TestPatchEmailPrefs:
  '''UMAIL-04: PATCH /settings/email-prefs persists email_enabled + pause_until.'''

  def test_patch_persists_email_enabled_true(self, monkeypatch):
    '''PATCH with email_enabled=on → captured_users[uid][email_enabled] == True.'''
    uid = 'u1-test'
    client, captured = _make_prefs_client(monkeypatch, uid)
    resp = client.patch(
      '/settings/email-prefs',
      data={'email_enabled': 'on', 'pause_until': ''},
      headers={'X-Trading-Signals-Auth': 'a' * 32},
    )
    assert resp.status_code == 200
    assert captured[uid]['email_enabled'] is True

  def test_patch_persists_email_enabled_false(self, monkeypatch):
    '''PATCH with no email_enabled checkbox → email_enabled=False.'''
    uid = 'u2-test'
    client, captured = _make_prefs_client(monkeypatch, uid)
    resp = client.patch(
      '/settings/email-prefs',
      data={'pause_until': ''},
      headers={'X-Trading-Signals-Auth': 'a' * 32},
    )
    assert resp.status_code == 200
    assert captured[uid]['email_enabled'] is False

  def test_patch_persists_pause_until_iso_date(self, monkeypatch):
    '''PATCH with pause_until=2026-06-01 persists ISO date string.'''
    uid = 'u3-test'
    client, captured = _make_prefs_client(monkeypatch, uid)
    resp = client.patch(
      '/settings/email-prefs',
      data={'email_enabled': 'on', 'pause_until': '2026-06-01'},
      headers={'X-Trading-Signals-Auth': 'a' * 32},
    )
    assert resp.status_code == 200
    assert captured[uid]['pause_until'] == '2026-06-01'

  def test_patch_rejects_invalid_pause_date(self, monkeypatch):
    '''PATCH with invalid pause_until silently coerces to None.'''
    uid = 'u4-test'
    client, captured = _make_prefs_client(monkeypatch, uid)
    resp = client.patch(
      '/settings/email-prefs',
      data={'email_enabled': 'on', 'pause_until': 'not-a-date'},
      headers={'X-Trading-Signals-Auth': 'a' * 32},
    )
    assert resp.status_code == 200
    assert captured[uid].get('pause_until') is None

  def test_patch_requires_authenticated_uid(self, monkeypatch):
    '''PATCH without auth → 401 (no current_user_id override).'''
    from fastapi.testclient import TestClient
    sys.modules.pop('web.app', None)
    from web.app import create_app
    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.patch(
      '/settings/email-prefs',
      data={'email_enabled': 'on', 'pause_until': ''},
    )
    assert resp.status_code in (401, 403)
