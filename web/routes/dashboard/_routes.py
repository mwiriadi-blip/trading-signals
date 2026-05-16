'''web/routes/dashboard/_routes.py — FastAPI route handlers for the dashboard.

Contains the register() function that wires all dashboard routes onto the app.
Closure-bound helpers (_is_cookie_session, _set_market_cookie) live here
because they capture register()-local state (_session_serializer, _session_secret,
_MARKET_COOKIE_ATTRS).

Architecture (CLAUDE.md hex-lite):
  Allowed: fastapi, starlette, stdlib, dashboard (Phase 13 D-07), state_manager,
           sizing_engine, system_params.
  Forbidden: signal_engine, data_fetcher, main, notifier.
  Enforced by tests/test_web_healthz.py::TestWebHexBoundary.

Log prefix: [Web].
'''
import os

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from itsdangerous import BadSignature, SignatureExpired
from itsdangerous.url_safe import URLSafeTimedSerializer

from system_params import INSTRUMENT_ID_RE as _MARKET_ID_RE

from web.routes.dashboard._cache import (
  _ALLOWED_FUNCTIONS,
  _DASHBOARD_PATH,
)
from web.routes.dashboard._helpers import (
  _serve_account_page_scoped,
  _serve_dashboard_page,
  _serve_dashboard_root,
  _serve_market_scoped_page,
)
from web.routes.dashboard._renderers import _is_stale_for


def register(app: FastAPI) -> None:
  '''Register all dashboard routes on the given FastAPI instance.'''

  from web.dependencies import current_user_id as _get_current_user_id

  _session_secret = os.environ.get('WEB_AUTH_SECRET', '')
  _session_serializer = URLSafeTimedSerializer(_session_secret, salt='tsi-session-cookie')

  def _is_cookie_session(request: Request) -> bool:
    token = request.cookies.get('tsi_session')
    if not token:
      return False
    try:
      _session_serializer.loads(token, max_age=43200)
      return True
    except SignatureExpired:
      return False
    except BadSignature:
      return False

  _MARKET_COOKIE_ATTRS = '; Max-Age=2592000; Path=/; Secure; SameSite=Lax'

  def _set_market_cookie(response: Response, market_id: str) -> None:
    '''Phase 25 D-05 + Phase 26 Plan 26-07 (R7): set selected_market cookie.'''
    if not _MARKET_ID_RE.fullmatch(market_id or ''):
      return
    response.headers['Set-Cookie'] = f'selected_market={market_id}{_MARKET_COOKIE_ATTRS}'

  @app.get('/')
  def get_dashboard(request: Request, fragment: str | None = None):
    return _serve_dashboard_root(
      request, fragment, _DASHBOARD_PATH, is_cookie_session=_is_cookie_session,
    )

  @app.get('/signals')
  def get_signals_page(request: Request, fragment: str | None = None):
    return _serve_dashboard_page(request, 'signals', fragment, is_cookie_session=_is_cookie_session)

  @app.get('/dashboard-signals.html')
  def get_signals_page_file_alias(request: Request, fragment: str | None = None):
    return _serve_dashboard_page(request, 'signals', fragment, is_cookie_session=_is_cookie_session)

  @app.get('/dashboard.html')
  def get_signals_legacy_dashboard_alias(request: Request, fragment: str | None = None):
    return _serve_dashboard_page(request, 'signals', fragment, is_cookie_session=_is_cookie_session)

  @app.get('/account')
  def get_account_page(
    request: Request,
    fragment: str | None = None,
    uid: str = Depends(_get_current_user_id),
  ):
    return _serve_account_page_scoped(
      request, uid, fragment, is_cookie_session=_is_cookie_session,
    )

  @app.get('/dashboard-account.html')
  def get_account_page_file_alias(
    request: Request,
    fragment: str | None = None,
    uid: str = Depends(_get_current_user_id),
  ):
    return _serve_account_page_scoped(
      request, uid, fragment, is_cookie_session=_is_cookie_session,
    )

  @app.get('/settings')
  def get_settings_page(request: Request, fragment: str | None = None):
    return _serve_dashboard_page(
      request, 'settings', fragment, is_cookie_session=_is_cookie_session,
    )

  @app.get('/dashboard-settings.html')
  def get_settings_page_file_alias(request: Request, fragment: str | None = None):
    return _serve_dashboard_page(
      request, 'settings', fragment, is_cookie_session=_is_cookie_session,
    )

  @app.get('/market-test')
  def get_market_test_page(request: Request, fragment: str | None = None):
    return _serve_dashboard_page(
      request, 'market-test', fragment, is_cookie_session=_is_cookie_session,
    )

  @app.get('/dashboard-market-test.html')
  def get_market_test_page_file_alias(request: Request, fragment: str | None = None):
    return _serve_dashboard_page(
      request, 'market-test', fragment, is_cookie_session=_is_cookie_session,
    )

  @app.get('/markets/{market_id}/signals', response_class=Response)
  async def get_market_signals(
    request: Request, market_id: str, uid: str = Depends(_get_current_user_id),
  ):
    return await _serve_market_scoped_page(
      request, market_id, 'signals', uid, _set_market_cookie,
      is_cookie_session=_is_cookie_session,
    )

  @app.get('/markets/{market_id}/settings', response_class=Response)
  async def get_market_settings(
    request: Request, market_id: str, uid: str = Depends(_get_current_user_id),
  ):
    return await _serve_market_scoped_page(
      request, market_id, 'settings', uid, _set_market_cookie,
      is_cookie_session=_is_cookie_session,
    )

  @app.get('/markets/{market_id}/market-test', response_class=Response)
  async def get_market_market_test(
    request: Request, market_id: str, uid: str = Depends(_get_current_user_id),
  ):
    return await _serve_market_scoped_page(
      request, market_id, 'market-test', uid, _set_market_cookie,
      is_cookie_session=_is_cookie_session,
    )

  @app.get('/status-strip', response_class=Response)
  async def get_status_strip(request: Request):
    '''Phase 25 D-06/D-07 Plan 06: status strip fragment endpoint.'''
    from datetime import datetime
    import pytz
    import state_manager as _sm
    from dashboard_renderer.components.header import render_status_strip
    sydney = pytz.timezone('Australia/Sydney')
    now_awst = datetime.now(sydney)
    state = _sm.load_state()
    body = render_status_strip(state, now_awst)
    return Response(
      content=body.encode('utf-8'),
      media_type='text/html; charset=utf-8',
      status_code=200,
      headers={'Cache-Control': 'no-store, private'},
    )

  @app.get('/markets-strip', response_class=Response)
  async def get_markets_strip(request: Request):
    '''Phase 25 Plan 05 D-16: return the market tab strip fragment.'''
    import state_manager
    from dashboard_renderer.components.nav import render_market_strip
    state = state_manager.load_state()
    raw_cookie = request.cookies.get('selected_market', '') or ''
    active_market = raw_cookie if _MARKET_ID_RE.fullmatch(raw_cookie) else ''
    markets = state.get('markets', {}) or {}
    if not active_market or active_market not in markets:
      active_market = next(iter(markets), '')
    active_function = request.query_params.get('active_function', 'signals')
    if active_function not in _ALLOWED_FUNCTIONS:
      active_function = 'signals'
    body = render_market_strip(state, active_market, active_function)
    return Response(
      content=body.encode('utf-8'),
      media_type='text/html; charset=utf-8',
      status_code=200,
      headers={'Cache-Control': 'no-store, private'},
    )

  @app.patch('/settings/email-prefs')
  def patch_email_prefs(
    request: Request,
    email_enabled: str = Form(default=''),
    pause_until: str = Form(default=''),
    uid: str = Depends(_get_current_user_id),
  ) -> Response:
    '''Phase 37 UMAIL-04: persist email_enabled + pause_until to per-user state.'''
    from datetime import date as _date
    from state_manager import mutate_user_state

    enabled_bool = email_enabled in ('on', '1', 'true')
    pause_until_str = pause_until.strip() if pause_until else ''
    pause_date: str | None = None
    if pause_until_str:
      try:
        _date.fromisoformat(pause_until_str)
        pause_date = pause_until_str
      except (TypeError, ValueError):
        pause_date = None

    def _apply(state: dict) -> None:
      users = state.setdefault('users', {})
      user_bucket = users.setdefault(uid, {})
      user_bucket['email_enabled'] = enabled_bool
      user_bucket['pause_until'] = pause_date

    mutate_user_state(uid, _apply)
    return HTMLResponse('<p>Email preferences saved.</p>')
