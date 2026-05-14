'''Phase 37 Plan 05 Task 2 — UMAIL-04 email-prefs route tests.

TestPatchEmailPrefs — PATCH /settings/email-prefs persists email_enabled + pause_until
TestAdminNavLink   — admin nav shows /admin/users link only for admin role
TestSettingsRender — GET /settings includes email-prefs form
'''
import sys
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_client_with_uid(monkeypatch, tmp_path, uid, role='ff'):
  '''Build a TestClient with current_user_id overridden to uid.

  Monkeypatches state_manager load/mutate to use tmp_path state dir so
  tests never touch the real state.json.
  '''
  from fastapi.testclient import TestClient
  sys.modules.pop('web.app', None)
  from web.app import create_app
  import state_manager

  # Redirect state writes to tmp_path
  monkeypatch.chdir(tmp_path)
  # Seed minimal state with the user present
  state_file = tmp_path / 'state.json'
  import json
  state_file.write_text(json.dumps({
    'schema_version': 12,
    'users': {
      uid: {
        'account': 100000.0,
        'email_enabled': True,
        'pause_until': None,
      },
    },
    'signals': {},
    'markets': {},
    'strategy_settings': {},
    'warnings': [],
  }))

  app = create_app()
  from web.dependencies import current_user_id, require_admin
  app.dependency_overrides[current_user_id] = lambda: uid

  client = TestClient(app, raise_server_exceptions=False)
  return client


def _make_admin_client_with_uid(monkeypatch, tmp_path, uid):
  '''Build a TestClient with admin role override.'''
  from fastapi.testclient import TestClient
  sys.modules.pop('web.app', None)
  from web.app import create_app
  import json

  monkeypatch.chdir(tmp_path)
  state_file = tmp_path / 'state.json'
  state_file.write_text(json.dumps({
    'schema_version': 12,
    'users': {uid: {'account': 100000.0, 'email_enabled': True}},
    'signals': {},
    'markets': {},
    'strategy_settings': {},
    'warnings': [],
  }))

  app = create_app()
  from web.dependencies import current_user_id, require_admin
  app.dependency_overrides[current_user_id] = lambda: uid
  app.dependency_overrides[require_admin] = lambda: uid
  return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# TestPatchEmailPrefs
# ---------------------------------------------------------------------------

class TestPatchEmailPrefs:
  '''UMAIL-04: PATCH /settings/email-prefs persists email_enabled + pause_until.'''

  def test_patch_persists_email_enabled_true(self, monkeypatch, tmp_path):
    '''PATCH with email_enabled=on → load_user_state returns email_enabled=True.'''
    uid = 'u1-test'
    client = _make_client_with_uid(monkeypatch, tmp_path, uid)
    resp = client.patch(
      '/settings/email-prefs',
      data={'email_enabled': 'on', 'pause_until': ''},
      headers={'X-Trading-Signals-Auth': 'a' * 32},
    )
    assert resp.status_code == 200
    from state_manager import load_user_state
    user = load_user_state(uid)
    assert user.get('email_enabled') is True

  def test_patch_persists_email_enabled_false(self, monkeypatch, tmp_path):
    '''PATCH with no email_enabled checkbox → email_enabled=False.'''
    uid = 'u2-test'
    client = _make_client_with_uid(monkeypatch, tmp_path, uid)
    resp = client.patch(
      '/settings/email-prefs',
      data={'pause_until': ''},
      headers={'X-Trading-Signals-Auth': 'a' * 32},
    )
    assert resp.status_code == 200
    from state_manager import load_user_state
    user = load_user_state(uid)
    assert user.get('email_enabled') is False

  def test_patch_persists_pause_until_iso_date(self, monkeypatch, tmp_path):
    '''PATCH with pause_until=2026-06-01 persists ISO date string.'''
    uid = 'u3-test'
    client = _make_client_with_uid(monkeypatch, tmp_path, uid)
    resp = client.patch(
      '/settings/email-prefs',
      data={'email_enabled': 'on', 'pause_until': '2026-06-01'},
      headers={'X-Trading-Signals-Auth': 'a' * 32},
    )
    assert resp.status_code == 200
    from state_manager import load_user_state
    user = load_user_state(uid)
    assert user.get('pause_until') == '2026-06-01'

  def test_patch_rejects_invalid_pause_date(self, monkeypatch, tmp_path):
    '''PATCH with invalid pause_until silently coerces to None.'''
    uid = 'u4-test'
    client = _make_client_with_uid(monkeypatch, tmp_path, uid)
    resp = client.patch(
      '/settings/email-prefs',
      data={'email_enabled': 'on', 'pause_until': 'not-a-date'},
      headers={'X-Trading-Signals-Auth': 'a' * 32},
    )
    assert resp.status_code == 200
    from state_manager import load_user_state
    user = load_user_state(uid)
    assert user.get('pause_until') is None

  def test_patch_requires_authenticated_uid(self, monkeypatch, tmp_path):
    '''PATCH without auth → 401 (no current_user_id override).'''
    from fastapi.testclient import TestClient
    sys.modules.pop('web.app', None)
    from web.app import create_app
    import json

    monkeypatch.chdir(tmp_path)
    (tmp_path / 'state.json').write_text(json.dumps({
      'schema_version': 12,
      'users': {},
      'signals': {},
      'markets': {},
      'strategy_settings': {},
      'warnings': [],
    }))

    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.patch(
      '/settings/email-prefs',
      data={'email_enabled': 'on', 'pause_until': ''},
    )
    assert resp.status_code in (401, 403)
