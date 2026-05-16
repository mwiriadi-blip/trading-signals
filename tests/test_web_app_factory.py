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


# ---------------------------------------------------------------------------
# Phase 25 — Wave 1 test scaffolding: routing, cookie, status-strip endpoint
# Every xfail(strict=True) method fails today and turns green when the
# corresponding implementation plan (Wave 2/3) lands.
# ---------------------------------------------------------------------------

class TestPhase25MarketRoutes:
  """D-01..D-05: GET /markets/{market_id}/{function} routes registered correctly."""

  def test_market_signals_route_registered(self, monkeypatch):
    monkeypatch.setenv('WEB_AUTH_SECRET', VALID_SECRET)
    monkeypatch.setenv('WEB_AUTH_USERNAME', 'marc')
    from web.app import create_app
    app = create_app()
    paths = {r.path for r in app.routes if hasattr(r, 'path')}
    assert '/markets/{market_id}/signals' in paths

  def test_market_settings_get_route_registered(self, monkeypatch, tmp_path):
    """Phase 25 adds a GET handler for /markets/{market_id}/settings (full settings page).
    A PATCH handler already exists but GET (full-page render) is new in Phase 25.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('WEB_AUTH_SECRET', VALID_SECRET)
    monkeypatch.setenv('WEB_AUTH_USERNAME', 'marc')
    from web.app import create_app
    from web.dependencies import current_user_id
    app = create_app()
    # Phase 38: market routes use Depends(current_user_id); override for header-auth tests.
    app.dependency_overrides[current_user_id] = lambda: 'admin'
    client = TestClient(app)
    resp = client.get(
      '/markets/SPI200/settings',
      headers={AUTH_HEADER_NAME: VALID_SECRET},
    )
    assert resp.status_code == 200

  def test_market_market_test_route_registered(self, monkeypatch):
    monkeypatch.setenv('WEB_AUTH_SECRET', VALID_SECRET)
    monkeypatch.setenv('WEB_AUTH_USERNAME', 'marc')
    from web.app import create_app
    app = create_app()
    paths = {r.path for r in app.routes if hasattr(r, 'path')}
    assert '/markets/{market_id}/market-test' in paths

  def test_get_market_signals_returns_200_with_auth(self, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('WEB_AUTH_SECRET', VALID_SECRET)
    monkeypatch.setenv('WEB_AUTH_USERNAME', 'marc')
    from web.app import create_app
    from web.dependencies import current_user_id
    app = create_app()
    # Phase 38: market routes now use Depends(current_user_id) for per-user news.
    app.dependency_overrides[current_user_id] = lambda: 'admin'
    client = TestClient(app)
    resp = client.get(
      '/markets/SPI200/signals',
      headers={AUTH_HEADER_NAME: VALID_SECRET},
    )
    assert resp.status_code == 200

  def test_unknown_market_returns_404(self, monkeypatch, tmp_path):
    """Once /markets/{market_id}/signals is registered, an unknown market_id
    must return 404 (market-not-found) not 405 or 200.
    Prerequisite: /markets/{market_id}/signals route must exist (Phase 25 P25-02).
    Two-part assertion: route registered AND unknown market is 404.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('WEB_AUTH_SECRET', VALID_SECRET)
    monkeypatch.setenv('WEB_AUTH_USERNAME', 'marc')
    from web.app import create_app
    from web.dependencies import current_user_id
    app = create_app()
    app.dependency_overrides[current_user_id] = lambda: 'admin'
    paths = {r.path for r in app.routes if hasattr(r, 'path')}
    # Gate: only meaningful once the route exists; if not registered, fail the xfail
    assert '/markets/{market_id}/signals' in paths, 'Phase 25 route not yet registered'
    client = TestClient(app)
    resp = client.get(
      '/markets/NOPE/signals',
      headers={AUTH_HEADER_NAME: VALID_SECRET},
    )
    assert resp.status_code == 404

  def test_existing_route_shadowing_regression_still_passes(self, monkeypatch):
    """REGRESSION GUARD — must remain green throughout Phase 25.
    Asserts the literal /markets/settings PATCH path is registered
    BEFORE /markets/{market_id} in the route list (registration-order check).
    """
    monkeypatch.setenv('WEB_AUTH_SECRET', VALID_SECRET)
    monkeypatch.setenv('WEB_AUTH_USERNAME', 'marc')
    from web.app import create_app
    app = create_app()
    ordered_patch_paths = [r.path for r in app.routes if hasattr(r, 'path') and 'PATCH' in getattr(r, 'methods', set())]
    if '/markets/settings' in ordered_patch_paths and '/markets/{market_id}' in ordered_patch_paths:
      assert ordered_patch_paths.index('/markets/settings') < ordered_patch_paths.index('/markets/{market_id}'), \
        'Route shadowing regression — /markets/settings literal must come before /markets/{market_id}'


class TestPhase25SelectedMarketCookie:
  """D-05: GET /markets/{m}/{fn} sets cookie selected_market with HttpOnly=false; SameSite=Lax."""

  def test_market_route_sets_selected_market_cookie(self, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('WEB_AUTH_SECRET', VALID_SECRET)
    monkeypatch.setenv('WEB_AUTH_USERNAME', 'marc')
    from web.app import create_app
    from web.dependencies import current_user_id
    app = create_app()
    app.dependency_overrides[current_user_id] = lambda: 'admin'
    client = TestClient(app)
    resp = client.get(
      '/markets/AUDUSD/signals',
      headers={AUTH_HEADER_NAME: VALID_SECRET},
    )
    # Look for Set-Cookie header containing selected_market=AUDUSD
    set_cookies = [v for k, v in resp.headers.items() if k.lower() == 'set-cookie']
    # At minimum one Set-Cookie must contain selected_market=AUDUSD
    assert any('selected_market=AUDUSD' in sc for sc in set_cookies)

  def test_selected_market_cookie_has_lax_samesite_no_httponly(self, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('WEB_AUTH_SECRET', VALID_SECRET)
    monkeypatch.setenv('WEB_AUTH_USERNAME', 'marc')
    from web.app import create_app
    from web.dependencies import current_user_id
    app = create_app()
    app.dependency_overrides[current_user_id] = lambda: 'admin'
    client = TestClient(app)
    resp = client.get(
      '/markets/SPI200/signals',
      headers={AUTH_HEADER_NAME: VALID_SECRET},
    )
    set_cookies = [v for k, v in resp.headers.items() if k.lower() == 'set-cookie']
    market_cookie = next((sc for sc in set_cookies if 'selected_market=' in sc), None)
    assert market_cookie is not None
    assert 'SameSite=Lax' in market_cookie
    # D-05: NOT HttpOnly — JS must be able to read the cookie
    assert 'HttpOnly' not in market_cookie
    assert 'Path=/' in market_cookie
    assert 'Secure' in market_cookie  # production HTTPS-only requirement


class TestPhase25AddMarketHXTrigger:
  """Phase 25 P25-09: POST /markets must emit HX-Trigger: markets-changed so the strip refreshes."""

  def test_post_markets_emits_hx_trigger_markets_changed(self, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('WEB_AUTH_SECRET', VALID_SECRET)
    monkeypatch.setenv('WEB_AUTH_USERNAME', 'marc')
    from web.app import create_app
    client = TestClient(create_app())
    resp = client.post(
      '/markets',
      json={
        'market_id': 'TEST01',
        'display_name': 'Test Market',
        'symbol': 'TEST',
        'multiplier': 1.0,
        'cost_aud': 0.0,
      },
      headers={AUTH_HEADER_NAME: VALID_SECRET},
    )
    # Must succeed (201 or 200).
    assert 200 <= resp.status_code < 300, (
      f'POST /markets returned {resp.status_code}: {resp.text}'
    )
    # Starlette lowercases header names.
    hx_trigger = resp.headers.get('hx-trigger', '')
    assert 'markets-changed' in hx_trigger, (
      f'HX-Trigger missing or wrong: {hx_trigger!r}'
    )


# ---------------------------------------------------------------------------
# Phase 26 — Wave 1 test scaffolding: B1 (per-market eyebrow scoping)
# Every xfail(strict=True) method fails today and turns green when Plan 26-05
# threads ctx.active_market into _render_signal_cards / render_settings_tab /
# render_market_test_tab so each market-scoped GET only renders that market's
# panels.
# ---------------------------------------------------------------------------


def _phase26_three_market_state() -> dict:
  '''Three-market state fixture (SPI200, AUDUSD, ESM) for Phase 26 B1 tests.

  Display names mirror system_params.DEFAULT_MARKETS exactly:
    - SPI200 -> 'SPI 200'
    - AUDUSD -> 'AUD / USD'
  ESM is a synthetic third market with display_name 'ES Mini' that
  Phase 25 added via /markets POST in production.
  '''
  return {
    'schema_version': 7,
    'account': 100_000.0,
    'last_run': '2026-04-23',
    'markets': {
      'SPI200': {
        'display_name': 'SPI 200', 'symbol': '^AXJO', 'currency': 'AUD',
        'multiplier': 5.0, 'cost_aud': 6.0, 'enabled': True, 'sort_order': 10,
        'contract_type': 'mini', 'financing_rate_annual_pct': 0.0,
      },
      'AUDUSD': {
        'display_name': 'AUD / USD', 'symbol': 'AUDUSD=X', 'currency': 'AUD',
        'multiplier': 10000.0, 'cost_aud': 5.0, 'enabled': True, 'sort_order': 20,
        'contract_type': 'mini', 'financing_rate_annual_pct': 0.0,
      },
      'ESM': {
        'display_name': 'ES Mini', 'symbol': 'ES=F', 'currency': 'USD',
        'multiplier': 50.0, 'cost_aud': 4.0, 'enabled': True, 'sort_order': 30,
        'contract_type': 'mini', 'financing_rate_annual_pct': 0.0,
      },
    },
    'positions': {'SPI200': None, 'AUDUSD': None, 'ESM': None},
    'signals': {
      'SPI200': {'last_close': 7820.0, 'last_scalars': {'atr': 50.0}},
      'AUDUSD': {'last_close': 0.6520, 'last_scalars': {'atr': 0.005}},
      'ESM': {'last_close': 5200.0, 'last_scalars': {'atr': 30.0}},
    },
    'strategy_settings': {'SPI200': {}, 'AUDUSD': {}, 'ESM': {}},
    'trade_log': [], 'equity_history': [], 'warnings': [],
    'paper_trades': [], 'closed_trades': [],
    'initial_account': 100_000.0,
    'contracts': {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-mini', 'ESM': 'es-mini'},
    '_resolved_contracts': {
      'SPI200': {'multiplier': 5.0, 'cost_aud': 6.0},
      'AUDUSD': {'multiplier': 10000.0, 'cost_aud': 5.0},
      'ESM': {'multiplier': 50.0, 'cost_aud': 4.0},
    },
  }


def _phase26_setup(monkeypatch, tmp_path):
  '''Common Phase 26 setup: chdir tmp_path, set env, stub state_manager.load_state,
  write minimal dashboard.html shell so the route doesn't 503.
  '''
  monkeypatch.chdir(tmp_path)
  monkeypatch.setenv('WEB_AUTH_SECRET', VALID_SECRET)
  monkeypatch.setenv('WEB_AUTH_USERNAME', 'marc')
  import state_manager
  state = _phase26_three_market_state()
  monkeypatch.setattr(state_manager, 'load_state', lambda *_a, **_kw: state)
  # Minimal shell so any code path that reads dashboard.html succeeds.
  (tmp_path / 'dashboard.html').write_text(
    '<html><body data-auth="{{WEB_AUTH_SECRET}}">shell</body></html>',
    encoding='utf-8',
  )
  import sys
  sys.modules.pop('web.app', None)
  from web.app import create_app
  from web.dependencies import current_user_id
  app = create_app()
  # Phase 38: market routes use Depends(current_user_id); override for tests
  # that use header-only auth (middleware doesn't set request.state.user_id
  # for header auth paths, so FastAPI Depends resolution would 403).
  app.dependency_overrides[current_user_id] = lambda: 'admin'
  return TestClient(app)


class TestPhase26MarketScoping:
  '''B1: each /markets/{M}/{fn} GET must render only M's panels.

  Phase 25 shipped multi-tab market URLs but _render_page_body ignores
  ctx.active_market — every market URL renders every market's panels stacked.
  Reviewer Playwright pass on 2026-05-07 confirmed eyebrows like
  ['SPI 200 SETTINGS', 'AUD / USD SETTINGS', 'ES Mini SETTINGS'] all appear
  on /markets/ESM/settings.

  Eyebrow text format from settings.py:24 is f'{display.upper()} SETTINGS':
    SPI 200 -> 'SPI 200 SETTINGS'
    AUD / USD -> 'AUD / USD SETTINGS'
    ES Mini -> 'ES MINI SETTINGS'

  Tests fail today (Plan 26-05 implementation pending) and flip green
  when active_market threading lands.
  '''

  def test_spi200_settings_eyebrow_only_active_market(self, monkeypatch, tmp_path):
    client = _phase26_setup(monkeypatch, tmp_path)
    resp = client.get(
      '/markets/SPI200/settings',
      headers={AUTH_HEADER_NAME: VALID_SECRET},
    )
    assert resp.status_code == 200, f'unexpected status: {resp.status_code} body={resp.text[:200]}'
    # v11: eyebrow now includes contract_type tag — '<display> [<TYPE>] SETTINGS'.
    assert 'SPI 200 [MINI] SETTINGS' in resp.text, 'active-market eyebrow missing'
    assert 'AUD / USD [MINI] SETTINGS' not in resp.text, 'leak: AUDUSD eyebrow on SPI200 page'
    assert 'ES MINI' not in resp.text or 'ES MINI [' not in resp.text, 'leak: ESM eyebrow on SPI200 page'

  def test_audusd_settings_eyebrow_only_active_market(self, monkeypatch, tmp_path):
    client = _phase26_setup(monkeypatch, tmp_path)
    resp = client.get(
      '/markets/AUDUSD/settings',
      headers={AUTH_HEADER_NAME: VALID_SECRET},
    )
    assert resp.status_code == 200, f'unexpected status: {resp.status_code} body={resp.text[:200]}'
    # v11: eyebrow now includes contract_type tag — '<display> [<TYPE>] SETTINGS'.
    assert 'AUD / USD [MINI] SETTINGS' in resp.text, 'active-market eyebrow missing'
    assert 'SPI 200 [MINI] SETTINGS' not in resp.text, 'leak: SPI200 eyebrow on AUDUSD page'
    assert 'ES MINI [' not in resp.text, 'leak: ESM eyebrow on AUDUSD page'

  def test_esm_market_test_eyebrow_only_active_market(self, monkeypatch, tmp_path):
    '''Plan 26-05 must thread active_market into render_market_test_tab so the
    eyebrow names the active market (e.g. 'ES MINI MARKET TEST'). Today the
    eyebrow is the market-agnostic literal 'MARKET TEST'.

    Lock the contract: active-market display name appears in the page, and
    other markets' display names do not.
    '''
    client = _phase26_setup(monkeypatch, tmp_path)
    resp = client.get(
      '/markets/ESM/market-test',
      headers={AUTH_HEADER_NAME: VALID_SECRET},
    )
    assert resp.status_code == 200, f'unexpected status: {resp.status_code} body={resp.text[:200]}'
    # Active market name appears in the rendered market-test panel.
    assert 'ES Mini' in resp.text or 'ES MINI' in resp.text, (
      'active-market display name missing from /markets/ESM/market-test'
    )
    # Other markets' display names must not appear (B1: scoping).
    assert 'SPI 200' not in resp.text, 'leak: SPI200 display on ESM market-test page'
    assert 'AUD / USD' not in resp.text, 'leak: AUDUSD display on ESM market-test page'

  def test_spi200_signals_card_only_active_market(self, monkeypatch, tmp_path):
    '''Signal-card region on /markets/SPI200/signals must render the SPI 200
    eyebrow once and not contain other markets' display names.
    '''
    client = _phase26_setup(monkeypatch, tmp_path)
    resp = client.get(
      '/markets/SPI200/signals',
      headers={AUTH_HEADER_NAME: VALID_SECRET},
    )
    assert resp.status_code == 200, f'unexpected status: {resp.status_code} body={resp.text[:200]}'
    assert 'SPI 200' in resp.text, 'active-market eyebrow missing on signals page'
    # Other-market display names must not leak into the signal-card region.
    assert 'AUD / USD' not in resp.text, 'leak: AUDUSD display on SPI200 signals page'
    assert 'ES Mini' not in resp.text, 'leak: ESM display on SPI200 signals page'
