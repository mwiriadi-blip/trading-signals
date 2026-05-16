'''web/routes/dashboard/_helpers.py — HTML rendering helpers for the dashboard route.

Contains functions extracted from the monolithic register() closure:
  _substitute, _serve_dashboard_content, _serve_dashboard_page,
  _serve_dashboard_root, _serve_account_page_scoped,
  _serve_market_scoped_page.

Security note: _substitute receives is_cookie_session as an explicit callable
parameter (instead of closure capture) so the function can live at module-level
while still being called with the register-time session serializer. This
preserves the T-30-03-01 mitigation — the callable is always created inside
register() where _session_serializer is in scope.

No imports from _routes to avoid circular imports. May import from _cache,
_renderers (both are pure-constant/pure-function modules).
'''
import logging
import os
import re
from pathlib import Path
from typing import Callable

from fastapi import Request
from fastapi.responses import PlainTextResponse, Response

from web.routes.dashboard._cache import (
  _ALLOWED_FUNCTIONS,
  _PAGE_OUTPUTS,
  _PLACEHOLDER,
  _SESSION_NOTE_PLACEHOLDER,
  _SIGNOUT_PLACEHOLDER,
  _TRACE_OPEN_RE,
)
from web.routes.dashboard._renderers import (
  _forward_stop_fragment_response,
  _is_htmx_request,
  _is_stale_for,
  _resolve_trace_open,
)

# Use the package logger name so tests filtering on 'web.routes.dashboard'
# (the original module name) continue to capture WARN lines from this module.
logger = logging.getLogger('web.routes.dashboard')


def _substitute(content: bytes, request: Request, *, is_cookie_session: Callable) -> bytes:
  '''Phase 26 Plan 26-04 (B2/B3): single substitution helper resolving every
  placeholder kind that flows through the web layer.

  Called from BOTH _serve_dashboard_content (file-on-disk dashboard.html
  path) and _serve_market_scoped_page (in-memory render_dashboard_as_str
  path). Locality of substitution discipline lives here.

  Resolves:
    `{{WEB_AUTH_SECRET}}`  -> os.environ.get('WEB_AUTH_SECRET', '')
    `{{SIGNOUT_BUTTON}}`   -> _render_signout_button() if cookie session valid
    `{{SESSION_NOTE}}`     -> _render_session_note() if no cookie session
    `{{TRACE_OPEN_<M>}}`   -> ' open' if <M> in tsi_trace_open cookie set

  is_cookie_session: callable accepting a Request, returning bool. Injected
  from register() to preserve the T-30-03-01 session-cookie validation chain.
  '''
  # Phase 16.1: per-request auth widget.
  from dashboard_renderer.components.header import _render_session_note, _render_signout_button

  if is_cookie_session(request):
    # Cookie sessions: browser sends tsi_session automatically on same-origin
    # HTMX requests — embedding the raw secret in HTML is unnecessary and
    # leaks it into the browser cache.
    content = content.replace(_PLACEHOLDER, b'')
    content = content.replace(_SIGNOUT_PLACEHOLDER, _render_signout_button().encode('utf-8'))
    content = content.replace(_SESSION_NOTE_PLACEHOLDER, b'')
  else:
    # Header sessions and unauthenticated fetches (which won't reach here):
    # embed the real secret so HTMX hx-headers can carry it.
    secret = os.environ.get('WEB_AUTH_SECRET', '').encode('utf-8')
    content = content.replace(_PLACEHOLDER, secret)
    content = content.replace(_SIGNOUT_PLACEHOLDER, b'')
    content = content.replace(
      _SESSION_NOTE_PLACEHOLDER,
      _render_session_note().encode('utf-8'),
    )

  # Phase 17 Plan 17-01 + Phase 26 Plan 26-04: substitute TRACE_OPEN placeholders.
  trace_open = _resolve_trace_open(request)

  def _trace_open_repl(match: re.Match) -> bytes:
    market_id = match.group(1).decode('ascii')
    return b' open' if market_id in trace_open else b''

  content = _TRACE_OPEN_RE.sub(_trace_open_repl, content)
  return content


def _serve_dashboard_content(
  request: Request,
  content: bytes,
  fragment: str | None,
  *,
  is_cookie_session: Callable,
) -> Response:
  '''Phase 26 Plan 26-04: apply substitution then serve bytes or fragment.'''
  content = _substitute(content, request, is_cookie_session=is_cookie_session)

  if fragment is not None:
    m = re.search(
      rb'<tbody id="' + re.escape(fragment.encode('utf-8')) + rb'">(.*?)</tbody>',
      content, re.DOTALL,
    )
    if not m:
      return Response(content=b'', status_code=404, media_type='text/html; charset=utf-8')
    return Response(content=m.group(1), media_type='text/html; charset=utf-8')

  return Response(content=content, media_type='text/html; charset=utf-8')


def _serve_dashboard_page(
  request: Request,
  page: str,
  fragment: str | None,
  *,
  is_cookie_session: Callable,
) -> Response:
  '''Serve a pre-rendered page HTML (signals / settings / market-test).'''
  fwd = _forward_stop_fragment_response(request, fragment)
  if fwd is not None:
    return fwd

  from dashboard_renderer.api import render_dashboard_page as _render_page
  from state_manager import load_state

  page_output = _PAGE_OUTPUTS.get(page, _PAGE_OUTPUTS['signals'])
  page_path = Path(page_output)
  try:
    if _is_stale_for(page_path) or not page_path.exists():
      _render_page(load_state(), page=page, out_path=page_path)
  except Exception as exc:  # noqa: BLE001 — D-10 never-crash
    logger.warning(
      '[Web] dashboard regen failed for page=%s, serving stale: %s: %s',
      page, type(exc).__name__, exc,
    )

  if not page_path.exists():
    return PlainTextResponse(
      content='dashboard not ready', status_code=503, media_type='text/plain; charset=utf-8',
    )
  return _serve_dashboard_content(
    request=request,
    content=page_path.read_bytes(),
    fragment=fragment,
    is_cookie_session=is_cookie_session,
  )


def _serve_dashboard_root(
  request: Request,
  fragment: str | None,
  dashboard_path: str,
  *,
  is_cookie_session: Callable,
) -> Response:
  '''Phase 13 GET / + Phase 14 REVIEWS HIGH #4.'''
  fwd = _forward_stop_fragment_response(request, fragment)
  if fwd is not None:
    return fwd

  from dashboard_renderer.api import render_dashboard_files as _render_files
  from state_manager import load_state

  try:
    if _is_stale_for(Path(dashboard_path)):
      _render_files(load_state())
  except Exception as exc:  # noqa: BLE001 — D-10 never-crash
    logger.warning(
      '[Web] dashboard regen failed, serving stale: %s: %s',
      type(exc).__name__, exc,
    )

  if not os.path.exists(dashboard_path):
    return PlainTextResponse(
      content='dashboard not ready', status_code=503, media_type='text/plain; charset=utf-8',
    )
  return _serve_dashboard_content(
    request=request,
    content=Path(dashboard_path).read_bytes(),
    fragment=fragment,
    is_cookie_session=is_cookie_session,
  )


def _serve_account_page_scoped(
  request: Request,
  uid: str,
  fragment: str | None,
  *,
  is_cookie_session: Callable,
) -> Response:
  '''SC-5 (D-16, D-17, D-18): serve /account with per-user state scoping.'''
  fwd = _forward_stop_fragment_response(request, fragment)
  if fwd is not None:
    return fwd

  import state_manager
  from dashboard_renderer.api import render_dashboard_as_str

  full_state = state_manager.load_state()
  user_bucket = full_state.get('users', {}).get(uid, {}) or {}
  is_admin = (uid == full_state.get('admin_user_id'))
  scoped_state = {
    **full_state,
    'positions': user_bucket.get('positions', {}),
    'trade_log': user_bucket.get('trade_log', []),
    'paper_trades': user_bucket.get('paper_trades', []),
    'equity_history': user_bucket.get('equity_history', []),
    '_account_include_open_form': is_admin,
  }
  body = render_dashboard_as_str(scoped_state, now=None, active_function='account')
  body_bytes = _substitute(body.encode('utf-8'), request, is_cookie_session=is_cookie_session)
  response = Response(
    content=body_bytes, media_type='text/html; charset=utf-8', status_code=200,
  )
  response.headers['Cache-Control'] = 'no-store, private'
  return response


async def _serve_market_scoped_page(
  request: Request,
  market_id: str,
  function: str,
  uid: str,
  set_market_cookie: Callable,
  *,
  is_cookie_session: Callable,
) -> Response:
  '''Phase 25 D-01..D-05: serve a market-scoped page.

  set_market_cookie: callable(response, market_id) injected from register().
  is_cookie_session: callable(request) injected from register().
  '''
  import state_manager

  state = state_manager.load_state()
  markets = state.get('markets', {}) or {}
  if market_id not in markets:
    return Response(
      content=f'Market not found: {market_id}'.encode(),
      status_code=404,
      media_type='text/plain; charset=utf-8',
    )

  users_bucket = state.get('users', {}) or {}
  user_bucket = users_bucket.get(uid, {}) or {}
  news_dismissed = user_bucket.get('news_dismissed', {}) or {}
  news_panel_collapsed = user_bucket.get('news_panel_collapsed', {}) or {}

  htmx = _is_htmx_request(request)

  if htmx:
    from dashboard_renderer.api import render_panel_html
    body = render_panel_html(
      state, now=None, active_function=function, active_market=market_id,
      uid=uid, news_dismissed=news_dismissed, news_panel_collapsed=news_panel_collapsed,
    )
  else:
    from dashboard_renderer.api import render_dashboard_as_str
    body = render_dashboard_as_str(
      state, now=None, active_function=function, active_market=market_id,
      uid=uid, news_dismissed=news_dismissed, news_panel_collapsed=news_panel_collapsed,
    )

  body_bytes = _substitute(body.encode('utf-8'), request, is_cookie_session=is_cookie_session)
  response = Response(content=body_bytes, media_type='text/html; charset=utf-8', status_code=200)
  set_market_cookie(response, market_id)
  response.headers['Cache-Control'] = 'no-store, private'
  if htmx:
    response.headers['HX-Trigger'] = 'market-selected'
  return response
