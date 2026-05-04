'''Phase 13 D-16/D-17/D-21+/D-22 — create_app() factory contract tests.

Reference: 13-CONTEXT.md D-16..D-21, 13-RESEARCH.md §Pitfall 1
(openapi_url=None research extension D-22), 13-VALIDATION.md test-class
enumeration (lines 798-805).

Fixture strategy: tests use monkeypatch.setenv directly (not the shared
app_instance fixture) because TestSecretValidation needs to control the
env var BEFORE create_app() is called — the whole point of the test class
is asserting the failure modes.
'''
import pytest
from fastapi.testclient import TestClient

# Mirror conftest.py constants (single-source defined there for the autouse
# fixture; pytest's rootdir does NOT put tests/ on sys.path so we cannot
# `from conftest import ...`. The autouse fixture in conftest.py still runs
# before every test in this file because filename matches `test_web_*`).
VALID_SECRET = 'a' * 32  # mirror tests/conftest.py:VALID_SECRET (D-17 minimum)
AUTH_HEADER_NAME = 'X-Trading-Signals-Auth'  # mirror tests/conftest.py:AUTH_HEADER_NAME


class TestSecretValidation:
  '''D-16/D-17: missing, empty, or <32-char WEB_AUTH_SECRET → RuntimeError at boot.'''

  def test_missing_secret_raises(self, monkeypatch):
    '''D-16: env var absent → RuntimeError mentioning WEB_AUTH_SECRET.'''
    monkeypatch.delenv('WEB_AUTH_SECRET', raising=False)
    # Reload web.app to retrigger create_app() at import — but factory tests
    # use direct create_app() invocation to avoid module-cache interference.
    import sys
    # Ensure web.app is freshly evaluated each call.
    sys.modules.pop('web.app', None)
    with pytest.raises(RuntimeError, match='WEB_AUTH_SECRET'):
      from web.app import create_app
      create_app()

  def test_empty_secret_raises(self, monkeypatch):
    '''D-16: env var present but empty string → RuntimeError "missing or empty".'''
    monkeypatch.setenv('WEB_AUTH_SECRET', '')
    import sys
    sys.modules.pop('web.app', None)
    with pytest.raises(RuntimeError, match='missing or empty'):
      from web.app import create_app
      create_app()

  def test_short_secret_raises(self, monkeypatch):
    '''D-17: env var shorter than 32 chars → RuntimeError mentioning 32.'''
    monkeypatch.setenv('WEB_AUTH_SECRET', 'a' * 31)  # one char short of 32
    import sys
    sys.modules.pop('web.app', None)
    with pytest.raises(RuntimeError, match='at least 32 characters'):
      from web.app import create_app
      create_app()

  def test_32_char_secret_accepted(self, monkeypatch):
    '''D-17: exactly 32 chars boots the app cleanly.'''
    monkeypatch.setenv('WEB_AUTH_SECRET', 'a' * 32)
    import sys
    sys.modules.pop('web.app', None)
    from web.app import create_app
    app = create_app()
    assert app is not None
    # FastAPI exposes routes on .routes attribute — confirm the 3 we registered.
    paths = {r.path for r in app.routes if hasattr(r, 'path')}
    assert '/healthz' in paths
    assert '/' in paths
    assert '/api/state' in paths


class TestDocsDisabled:
  '''D-21 + D-22: /docs, /redoc, /openapi.json all suppressed.'''

  @pytest.fixture
  def client(self, monkeypatch):
    '''Local fixture (TestDocsDisabled-scoped) with valid secret pre-set.'''
    monkeypatch.setenv('WEB_AUTH_SECRET', VALID_SECRET)
    import sys
    sys.modules.pop('web.app', None)
    from web.app import create_app
    return TestClient(create_app())

  @pytest.fixture
  def auth_headers(self):
    return {AUTH_HEADER_NAME: VALID_SECRET}

  def test_docs_url_returns_404_with_auth(self, client, auth_headers):
    '''D-21: /docs is suppressed — even with valid auth, returns 404.'''
    r = client.get('/docs', headers=auth_headers)
    assert r.status_code == 404, (
      f'/docs should be 404 (D-21 suppression), got {r.status_code}'
    )

  def test_redoc_url_returns_404_with_auth(self, client, auth_headers):
    '''D-21: /redoc is suppressed — even with valid auth, returns 404.'''
    r = client.get('/redoc', headers=auth_headers)
    assert r.status_code == 404, (
      f'/redoc should be 404 (D-21 suppression), got {r.status_code}'
    )

  def test_openapi_json_returns_404_with_auth(self, client, auth_headers):
    '''D-22 (research extension to D-21): /openapi.json must be 404, not 200.

    Critical: docs_url=None + redoc_url=None alone DO NOT suppress
    /openapi.json — FastAPI keeps serving the schema there. The fix is
    openapi_url=None (passed at FastAPI() construction).
    '''
    r = client.get('/openapi.json', headers=auth_headers)
    assert r.status_code == 404, (
      f'/openapi.json should be 404 (D-22 suppression), got {r.status_code}. '
      'Without openapi_url=None, FastAPI keeps serving the full schema even '
      'when docs_url and redoc_url are disabled.'
    )

  def test_openapi_json_blocked_by_auth_when_unauthenticated(self, client):
    '''AuthMiddleware reaches /openapi.json BEFORE the 404 logic — proves order.

    Without auth header, the request gets 401 (from AuthMiddleware) rather
    than 404 (from FastAPI's missing-route). Confirms the middleware is
    registered correctly per D-06 (last-registered = first-dispatched).
    '''
    r = client.get('/openapi.json')  # no auth header
    assert r.status_code == 401, (
      f'/openapi.json without auth should be 401 (AuthMiddleware blocks first), '
      f'got {r.status_code}. If 404, the middleware is not reaching this path '
      f'(D-06 registration order issue).'
    )


class TestUsernameValidation:
  '''Phase 16.1 D-08: missing/empty/colon-containing WEB_AUTH_USERNAME →
  RuntimeError at boot. Mirrors TestSecretValidation shape verbatim.
  '''

  def test_missing_username_raises(self, monkeypatch):
    '''D-08: env var absent → RuntimeError mentioning WEB_AUTH_USERNAME.'''
    monkeypatch.setenv('WEB_AUTH_SECRET', 'a' * 32)
    monkeypatch.delenv('WEB_AUTH_USERNAME', raising=False)
    import sys
    sys.modules.pop('web.app', None)
    with pytest.raises(RuntimeError, match='WEB_AUTH_USERNAME'):
      from web.app import create_app
      create_app()

  def test_empty_username_raises(self, monkeypatch):
    '''D-08: env var present but empty → RuntimeError "missing or empty".'''
    monkeypatch.setenv('WEB_AUTH_SECRET', 'a' * 32)
    monkeypatch.setenv('WEB_AUTH_USERNAME', '')
    import sys
    sys.modules.pop('web.app', None)
    with pytest.raises(RuntimeError, match='missing or empty'):
      from web.app import create_app
      create_app()

  def test_username_with_colon_raises(self, monkeypatch):
    '''D-08: ':' in username → RuntimeError (legacy Basic Auth field separator).'''
    monkeypatch.setenv('WEB_AUTH_SECRET', 'a' * 32)
    monkeypatch.setenv('WEB_AUTH_USERNAME', 'bad:user')
    import sys
    sys.modules.pop('web.app', None)
    with pytest.raises(RuntimeError, match=r"must not contain ':'"):
      from web.app import create_app
      create_app()

  def test_valid_username_accepted(self, monkeypatch):
    '''D-08: 'marc' boots the app cleanly. /login route registration is
    asserted in TestLoginRouteRegistered below (Task 3a sets that up).
    '''
    monkeypatch.setenv('WEB_AUTH_SECRET', 'a' * 32)
    monkeypatch.setenv('WEB_AUTH_USERNAME', 'marc')
    import sys
    sys.modules.pop('web.app', None)
    from web.app import create_app
    app = create_app()
    assert app is not None
    # Phase 13 baseline routes still present
    paths = {r.path for r in app.routes if hasattr(r, 'path')}
    assert '/healthz' in paths
    assert '/' in paths
    assert '/api/state' in paths


class TestRecoveryEmailValidation:
  '''Phase 16.1 Plan 03 F-06: OPERATOR_RECOVERY_EMAIL boot validation.

  Mirrors TestUsernameValidation shape verbatim. Default is mwiriadi@gmail.com.
  Malformed → RuntimeError; valid → app.state.operator_recovery_email set.
  '''

  def test_recovery_email_default_is_mwiriadi_at_gmail(self, monkeypatch):
    '''F-06: env var absent → default 'mwiriadi@gmail.com' (literal).'''
    monkeypatch.setenv('WEB_AUTH_SECRET', 'a' * 32)
    monkeypatch.setenv('WEB_AUTH_USERNAME', 'marc')
    monkeypatch.delenv('OPERATOR_RECOVERY_EMAIL', raising=False)
    import sys
    sys.modules.pop('web.app', None)
    from web.app import create_app
    app = create_app()
    assert app.state.operator_recovery_email == 'mwiriadi@gmail.com'

  def test_malformed_email_raises_runtime_error(self, monkeypatch):
    '''F-06: 'not-an-email' → RuntimeError with malformed-email message.'''
    monkeypatch.setenv('WEB_AUTH_SECRET', 'a' * 32)
    monkeypatch.setenv('WEB_AUTH_USERNAME', 'marc')
    monkeypatch.setenv('OPERATOR_RECOVERY_EMAIL', 'not-an-email')
    import sys
    sys.modules.pop('web.app', None)
    with pytest.raises(RuntimeError, match='OPERATOR_RECOVERY_EMAIL is malformed'):
      from web.app import create_app
      create_app()

  def test_email_with_no_tld_raises(self, monkeypatch):
    '''F-06: 'foo@bar' (no .tld) → RuntimeError.'''
    monkeypatch.setenv('WEB_AUTH_SECRET', 'a' * 32)
    monkeypatch.setenv('WEB_AUTH_USERNAME', 'marc')
    monkeypatch.setenv('OPERATOR_RECOVERY_EMAIL', 'foo@bar')
    import sys
    sys.modules.pop('web.app', None)
    with pytest.raises(RuntimeError, match='OPERATOR_RECOVERY_EMAIL is malformed'):
      from web.app import create_app
      create_app()

  def test_email_with_at_at_raises(self, monkeypatch):
    '''F-06: 'a@b@c.com' rejected by ^[^@]+@[^@]+\\.[^@]+$ regex.'''
    monkeypatch.setenv('WEB_AUTH_SECRET', 'a' * 32)
    monkeypatch.setenv('WEB_AUTH_USERNAME', 'marc')
    monkeypatch.setenv('OPERATOR_RECOVERY_EMAIL', 'a@b@c.com')
    import sys
    sys.modules.pop('web.app', None)
    with pytest.raises(RuntimeError, match='OPERATOR_RECOVERY_EMAIL is malformed'):
      from web.app import create_app
      create_app()

  def test_valid_recovery_email_overrides_default(self, monkeypatch):
    '''F-06: 'ops@example.com' boots; app.state surfaces the override.'''
    monkeypatch.setenv('WEB_AUTH_SECRET', 'a' * 32)
    monkeypatch.setenv('WEB_AUTH_USERNAME', 'marc')
    monkeypatch.setenv('OPERATOR_RECOVERY_EMAIL', 'ops@example.com')
    import sys
    sys.modules.pop('web.app', None)
    from web.app import create_app
    app = create_app()
    assert app.state.operator_recovery_email == 'ops@example.com'


class TestMarketRoutesRegistered:
  def test_market_routes_are_registered(self, monkeypatch):
    monkeypatch.setenv('WEB_AUTH_SECRET', 'a' * 32)
    monkeypatch.setenv('WEB_AUTH_USERNAME', 'marc')
    import sys
    sys.modules.pop('web.app', None)
    from web.app import create_app
    app = create_app()
    paths = {r.path for r in app.routes if hasattr(r, 'path')}
    assert '/markets' in paths
    assert '/markets/{market_id}' in paths
    assert '/markets/settings' in paths
    assert '/markets/{market_id}/settings' in paths
    assert '/account/balance' in paths
    assert '/market-test/run' in paths

  def test_patch_account_balance_updates_initial_and_current(self, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('WEB_AUTH_SECRET', VALID_SECRET)
    monkeypatch.setenv('WEB_AUTH_USERNAME', 'marc')
    from state_manager import load_state, reset_state, save_state
    from web.app import create_app

    state = reset_state(initial_account=100000.0)
    state['account'] = 105000.0
    save_state(state)

    client = TestClient(create_app())
    response = client.patch(
      '/account/balance',
      json={'initial_account': 120000.0, 'account': 123456.78},
      headers={AUTH_HEADER_NAME: VALID_SECRET},
    )

    assert response.status_code == 200
    updated = load_state()
    assert updated['initial_account'] == 120000.0
    assert updated['account'] == 123456.78
    assert 'Starting Balance' in response.text

  def test_patch_market_metadata_updates_existing_market(self, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('WEB_AUTH_SECRET', VALID_SECRET)
    monkeypatch.setenv('WEB_AUTH_USERNAME', 'marc')
    from state_manager import load_state, reset_state, save_state
    from web.app import create_app

    save_state(reset_state())
    client = TestClient(create_app())
    response = client.patch(
      '/markets/SPI200',
      json={'display_name': 'Australia 200', 'enabled': False, 'sort_order': 99},
      headers={AUTH_HEADER_NAME: VALID_SECRET},
    )

    assert response.status_code == 200
    state = load_state()
    assert state['markets']['SPI200']['display_name'] == 'Australia 200'
    assert state['markets']['SPI200']['enabled'] is False
    assert state['markets']['SPI200']['sort_order'] == 99

  def test_patch_market_settings_path_alias_updates_settings(self, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('WEB_AUTH_SECRET', VALID_SECRET)
    monkeypatch.setenv('WEB_AUTH_USERNAME', 'marc')
    from state_manager import load_state, reset_state, save_state
    from web.app import create_app

    save_state(reset_state())
    client = TestClient(create_app())
    payload = {
      'market_id': 'AUDUSD',
      'adx_gate': 17.5,
      'momentum_votes_required': 3,
      'trail_mult_long': 2.5,
      'trail_mult_short': 1.5,
      'risk_pct_long': 5.0,
      'risk_pct_short': 2.5,
      'one_contract_floor': True,
      'contract_cap': 4,
      'direction_mode': 'long_only',
    }
    response = client.patch(
      '/markets/AUDUSD/settings',
      json=payload,
      headers={AUTH_HEADER_NAME: VALID_SECRET},
    )

    assert response.status_code == 200
    settings = load_state()['strategy_settings']['AUDUSD']
    assert settings['adx_gate'] == 17.5
    assert settings['momentum_votes_required'] == 3
    assert settings['risk_pct_long'] == 0.05
    assert settings['risk_pct_short'] == 0.025
    assert settings['one_contract_floor'] is True
    assert settings['contract_cap'] == 4
    assert settings['direction_mode'] == 'long_only'

  def test_patch_market_settings_literal_path_updates_settings(self, monkeypatch, tmp_path):
    '''Regression: /markets/settings must not be shadowed by /markets/{market_id}.'''
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('WEB_AUTH_SECRET', VALID_SECRET)
    monkeypatch.setenv('WEB_AUTH_USERNAME', 'marc')
    from state_manager import load_state, reset_state, save_state
    from web.app import create_app

    save_state(reset_state())
    client = TestClient(create_app())
    payload = {
      'market_id': 'SPI200',
      'adx_gate': 20.0,
      'momentum_votes_required': 1,
      'trail_mult_long': 2.5,
      'trail_mult_short': 2.0,
      'risk_pct_long': 5.0,
      'risk_pct_short': 0.5,
      'one_contract_floor': True,
      'contract_cap': None,
      'direction_mode': 'long_only',
    }
    response = client.patch(
      '/markets/settings',
      json=payload,
      headers={AUTH_HEADER_NAME: VALID_SECRET},
    )

    assert response.status_code == 200
    settings = load_state()['strategy_settings']['SPI200']
    assert settings['adx_gate'] == 20.0
    assert settings['momentum_votes_required'] == 1
    assert settings['risk_pct_long'] == 0.05
    assert settings['risk_pct_short'] == 0.005
    assert settings['one_contract_floor'] is True
    assert settings['contract_cap'] is None
    assert settings['direction_mode'] == 'long_only'
