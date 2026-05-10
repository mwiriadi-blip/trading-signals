'''GET / — Phase 13 WEB-05 + D-07..D-11 + Phase 14 REVIEWS HIGH #4.

Serves the v1.0 dashboard.html behind shared-secret auth. Regenerates the
file lazily when state.json has been written more recently than the cached
dashboard.html. Never crashes — render failure logs WARN and serves the
stale on-disk copy. First-run before any signal run has rendered → 503
plain-text "dashboard not ready".

Phase 14 Plan 14-04 Task 5 (REVIEWS HIGH #4):
  The on-disk dashboard.html (rendered by main.run_daily_check via Plan 14-05)
  emits hx-headers='{"X-Trading-Signals-Auth": "{{WEB_AUTH_SECRET}}"}' with a
  literal placeholder. This handler reads the bytes, substitutes the
  placeholder with the actual env-var value at request time, and returns
  the patched bytes. The disk file never carries the real secret.

  Threat T-14-15 (auth-secret leak via on-disk dashboard.html cache) is
  MITIGATED by this placeholder-substitution discipline. Tests in
  tests/test_web_dashboard.py::TestAuthSecretPlaceholderSubstitution lock
  the discipline via three assertions.

  ?fragment=position-group-{instrument} query param returns ONLY that
  tbody's inner HTML (used by the per-tbody listener wired in Plan 14-05
  for HX-Trigger refresh on positions-changed events).

Contract (CONTEXT.md 2026-04-25):
  D-07: GET / serves dashboard.html via Response (NOT FileResponse — we now
        modify content per request to substitute the auth-secret placeholder;
        FileResponse streams unmodified bytes). Conditional-GET semantics
        are sacrificed for auth-secret hygiene.
  D-08: Staleness = os.stat(state.json).st_mtime_ns > os.stat(dashboard.html).st_mtime_ns
        — strict greater-than. Both files use atomic tempfile+replace
        (Phase 3 + Phase 5), so mtime semantics are reliable.
  D-09: Cached dashboard.html lives at repo root (matches existing
        dashboard.render_dashboard default out_path).
  D-10: Never-crash. render_dashboard exception → log WARN + serve stale
        on-disk copy (200). Missing dashboard.html (first-run) → 503
        plain-text "dashboard not ready".
  D-11: Concurrency posture. workers=1 (Phase 11) means two concurrent
        GET /'s both noticing staleness double-render harmlessly. State
        read is stable within the window. No file locking needed.

SC-2 lock (REVIEWS MEDIUM #3):
  The handler regenerates BEFORE serving so the response streams the
  newly-written + secret-substituted bytes — not a pre-regen snapshot.

Architecture (CLAUDE.md hex-lite + Phase 10 D-15 + Phase 13 D-07 extension):
  web/routes/ is an adapter hex.
  Allowed: fastapi, starlette, stdlib, dashboard (Phase 13 D-07 promotion —
           render_dashboard is now an allowed adapter-to-adapter import),
           state_manager (Phase 11 D-15 read-only),
           sizing_engine + system_params (Phase 14 D-02 promotion — needed
           for MAX_PYRAMID_LEVEL + INSTRUMENT_ID_RE single-source-of-truth).
  Forbidden: signal_engine, data_fetcher, main, notifier.
  Enforced by tests/test_web_healthz.py::TestWebHexBoundary.

  Both state_manager AND dashboard imports are LOCAL (inside the handler)
  per Phase 11 C-2 / Phase 13 D-07. Module-top imports of either would
  fail tests/test_web_healthz.py::TestWebHexBoundary::test_web_adapter_imports_are_local_not_module_top.

Log prefix: [Web].
'''
import logging
import os
import re
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, Response
from itsdangerous import BadSignature, SignatureExpired
from itsdangerous.url_safe import URLSafeTimedSerializer

logger = logging.getLogger(__name__)

_DASHBOARD_PATH = 'dashboard.html'  # D-09: repo root, matches dashboard.py default
_STATE_PATH = 'state.json'
_REQUIRED_DASHBOARD_MARKER = b'class="tabs tabs-function"'  # Phase 25 D-01: forces regen of all 5 sibling HTMLs post-deploy

# Phase 26 Plan 26-07 (R7): mirror Pydantic write-side regex (web/routes/markets.py:20)
# on the cookie read+write paths for defense-in-depth. Bounded length, ASCII only.
# Phase 27 #8: now sourced from system_params.INSTRUMENT_ID_RE — single source of
# truth (review-fix agreed-8). The literal r'^[A-Z0-9_]{2,20}$' below documents
# the canonical pattern in-place so reviewers can grep it without import-chasing.
from system_params import INSTRUMENT_ID_RE as _MARKET_ID_RE  # r'^[A-Z0-9_]{2,20}$'

# Phase 26 Plan 26-07 (R6): allowlist for active_function query param.
_ALLOWED_FUNCTIONS = {'signals', 'account', 'settings', 'market-test'}

# Phase 14 Plan 14-04 Task 5 (REVIEWS HIGH #4): substitute placeholder with
# env secret at request time so on-disk dashboard.html never carries the
# real value. Plan 14-05 emits the literal placeholder in hx-headers.
_PLACEHOLDER = b'{{WEB_AUTH_SECRET}}'

# Phase 16.1 — placeholders for the per-request auth-widget swap (Sign Out
# button vs session note). Mirrors the Phase 14 {{WEB_AUTH_SECRET}} pattern.
_SIGNOUT_PLACEHOLDER = b'{{SIGNOUT_BUTTON}}'
_SESSION_NOTE_PLACEHOLDER = b'{{SESSION_NOTE}}'

# Phase 17 Plan 17-01 — trace-panel open-state cookie.
# The unsigned UI-preference cookie `tsi_trace_open` carries a comma-separated
# list of instrument keys whose <details> should be pre-expanded. The allowlist
# prevents arbitrary attribute injection into the substituted HTML.
_VALID_TRACE_INSTRUMENT_KEYS: frozenset = frozenset({'SPI200', 'AUDUSD'})
_TRACE_OPEN_PLACEHOLDER_SPI200 = b'{{TRACE_OPEN_SPI200}}'
_TRACE_OPEN_PLACEHOLDER_AUDUSD = b'{{TRACE_OPEN_AUDUSD}}'

# Phase 26 Plan 26-04 (B2/B3): generalised TRACE_OPEN placeholder regex matches
# `{{TRACE_OPEN_<MARKET>}}` for any market id satisfying ^[A-Z0-9_]{2,20}$.
# Mirrors the canonical market_id regex in web/routes/markets.py:20 (Pydantic
# Field pattern). Bytes regex is used because _substitute operates on bytes.
_TRACE_OPEN_RE = re.compile(rb'\{\{TRACE_OPEN_([A-Z0-9_]{2,20})\}\}')
_PAGE_OUTPUTS = {
  'signals': 'dashboard-signals.html',
  'account': 'dashboard-account.html',
  'settings': 'dashboard-settings.html',
  'market-test': 'dashboard-market-test.html',
}


def _is_stale_for(page_output: Path) -> bool:
  '''Phase 26 Plan 26-07 (R1): per-file staleness check.

  D-08 generalised: state.json mtime > page_output mtime means regen needed.
  Each sibling HTML (dashboard.html, dashboard-signals.html, ...) is now
  gated by its own marker presence + own mtime — previously only
  dashboard.html was checked, leaving siblings stale on disk after deploys
  that bumped the marker but already had a fresh dashboard.html.

  Returns True if page_output is missing (caller handles via .exists()).
  Returns True if state.json is newer than page_output (regen path).
  Returns True if cached page_output predates the tabbed dashboard marker.
  Returns False if page_output is fresh relative to state.json.
  Returns False if state.json itself is missing (no state to render from).
  '''
  try:
    html_mtime = os.stat(page_output).st_mtime_ns
  except FileNotFoundError:
    return True  # missing page output — caller handles 503
  try:
    state_mtime = os.stat(_STATE_PATH).st_mtime_ns
  except FileNotFoundError:
    return False  # no state.json — serve whatever page_output is
  try:
    if _REQUIRED_DASHBOARD_MARKER not in page_output.read_bytes():
      return True
  except OSError:
    return True
  return state_mtime > html_mtime


def register(app: FastAPI) -> None:
  '''Register GET / on the given FastAPI instance.'''

  # Phase 16.1: build a session serializer at register-time so the per-request
  # cookie validator is just a signature check (the constructor is non-trivial).
  _session_secret = os.environ.get('WEB_AUTH_SECRET', '')
  _session_serializer = URLSafeTimedSerializer(
    _session_secret, salt='tsi-session-cookie',
  )

  def _is_cookie_session(request: Request) -> bool:
    '''Validate tsi_session cookie via itsdangerous. Returns True iff the
    cookie is present and valid (not expired, signed correctly).
    '''
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

  def _resolve_trace_open(request: Request) -> frozenset:
    '''Read tsi_trace_open cookie and return allowlisted instrument keys.

    The cookie value is a comma-separated list of instrument keys
    (e.g. "SPI200,AUDUSD"). Only keys matching the canonical market-ID regex
    ^[A-Z0-9_]{2,20}$ (sourced from _MARKET_ID_RE) are accepted — all other
    values are discarded silently. Returns empty frozenset when cookie absent
    or contains no valid keys.

    Phase 29 Plan 12: widened from a static frozenset{'SPI200','AUDUSD'} to
    a regex-validated format allowlist so dynamically-added markets (Phase 25+
    multi-market API) are also covered. Security is preserved: _trace_open_repl
    can only emit b' open' or b'' — no injection surface regardless of market ID.
    '''
    raw = request.cookies.get('tsi_trace_open', '')
    if not raw:
      return frozenset()
    parts = {p.strip() for p in raw.split(',') if p.strip()}
    return frozenset(p for p in parts if _MARKET_ID_RE.fullmatch(p))

  @app.get('/')
  def get_dashboard(request: Request, fragment: str | None = None):
    return _serve_dashboard_root(request, fragment=fragment)

  @app.get('/signals')
  def get_signals_page(request: Request, fragment: str | None = None):
    return _serve_dashboard_page(request, 'signals', fragment=fragment)

  @app.get('/dashboard-signals.html')
  def get_signals_page_file_alias(request: Request, fragment: str | None = None):
    return _serve_dashboard_page(request, 'signals', fragment=fragment)

  @app.get('/dashboard.html')
  def get_signals_legacy_dashboard_alias(request: Request, fragment: str | None = None):
    # Legacy file-link alias kept for backwards compatibility with older
    # generated pages/bookmarks; canonical multi-page signals path is
    # /dashboard-signals.html (and /signals).
    return _serve_dashboard_page(request, 'signals', fragment=fragment)

  @app.get('/account')
  def get_account_page(request: Request, fragment: str | None = None):
    return _serve_dashboard_page(request, 'account', fragment=fragment)

  @app.get('/dashboard-account.html')
  def get_account_page_file_alias(request: Request, fragment: str | None = None):
    return _serve_dashboard_page(request, 'account', fragment=fragment)

  @app.get('/settings')
  def get_settings_page(request: Request, fragment: str | None = None):
    return _serve_dashboard_page(request, 'settings', fragment=fragment)

  @app.get('/dashboard-settings.html')
  def get_settings_page_file_alias(request: Request, fragment: str | None = None):
    return _serve_dashboard_page(request, 'settings', fragment=fragment)

  @app.get('/market-test')
  def get_market_test_page(request: Request, fragment: str | None = None):
    return _serve_dashboard_page(request, 'market-test', fragment=fragment)

  @app.get('/dashboard-market-test.html')
  def get_market_test_page_file_alias(request: Request, fragment: str | None = None):
    return _serve_dashboard_page(request, 'market-test', fragment=fragment)

  # Phase 25 Plan 04 D-01..D-05: GET /markets/{market_id}/{function} routes.
  # Two-segment paths (e.g. /markets/SPI200/signals) registered here; they do
  # NOT shadow the existing one-segment PATCH /markets/{market_id} in
  # markets.py because method differs (GET vs PATCH). Registration order:
  # markets.py is registered BEFORE dashboard.py in web/app.py, preserving
  # the 18ea2c5 literal-before-dynamic discipline.

  # Phase 25 D-05: selected_market cookie attrs. NO HttpOnly (JS-readable).
  # SameSite=Lax (UI-state cookie; not session). Secure required for HTTPS.
  _MARKET_COOKIE_ATTRS = '; Max-Age=2592000; Path=/; Secure; SameSite=Lax'

  def _is_htmx_request(request: Request) -> bool:
    '''Phase 25 Pitfall 6: HTMX swap requests carry HX-Request: true header.'''
    return request.headers.get('HX-Request', '').lower() == 'true'

  def _set_market_cookie(response: Response, market_id: str) -> None:
    '''Phase 25 D-05: set selected_market cookie on every market-scoped render.

    Cookie is JS-readable (no HttpOnly) so /account can route to last-selected market.

    Phase 26 Plan 26-07 (R7): write-path regex tightened to mirror Pydantic
    upstream (web/routes/markets.py:20). Replaces the permissive char-strip
    sanitiser with an allowlist fullmatch — anything outside ^[A-Z0-9_]{2,20}$
    is silently dropped.
    '''
    if not _MARKET_ID_RE.fullmatch(market_id or ''):
      return
    response.headers['Set-Cookie'] = f'selected_market={market_id}{_MARKET_COOKIE_ATTRS}'

  async def _serve_market_scoped_page(request: Request, market_id: str, function: str):
    '''Phase 25 D-01..D-05: serve a market-scoped page (signals/settings/market-test).

    Validates market_id against state['markets']; 404 on miss.
    Sets selected_market cookie on every successful response (D-05).
    HX-Request → render_panel_html() returns panel-only HTML (no shell, no nav);
    otherwise render_dashboard_as_str() returns the full document.
    Cache-Control: no-store, private (T-25-04-03 cache poisoning mitigation).
    '''
    import state_manager

    state = state_manager.load_state()
    markets = state.get('markets', {}) or {}
    if market_id not in markets:
      return Response(
        content=f'Market not found: {market_id}'.encode('utf-8'),
        status_code=404,
        media_type='text/plain; charset=utf-8',
      )

    htmx = _is_htmx_request(request)

    if htmx:
      # HTMX swap path — panel-only HTML (no shell, no nav).
      # Phase 26 Plan 06 (R2): render_panel_html replaces the legacy
      # mixed-return form that returned str when htmx_panel_only=True.
      from dashboard_renderer.api import render_panel_html
      body = render_panel_html(
        state,
        now=None,
        active_function=function,
        active_market=market_id,
      )
    else:
      # Full document path (browser navigation)
      from dashboard_renderer.api import render_dashboard_as_str
      body = render_dashboard_as_str(
        state,
        now=None,
        active_function=function,
        active_market=market_id,
      )

    # Phase 26 Plan 26-04 (B2/B3): apply the same placeholder-substitution
    # discipline used by the canonical dashboard.html serve path
    # (_serve_dashboard_content). Without this, market-scoped pages leak
    # {{WEB_AUTH_SECRET}}, {{SIGNOUT_BUTTON}}, {{SESSION_NOTE}}, and
    # {{TRACE_OPEN_<MARKET>}} placeholders, causing PATCH 401s on form submit
    # and visible placeholder text in the header. The helper is shared with
    # _serve_dashboard_content; locality of substitution rule lives there.
    body_bytes = _substitute(body.encode('utf-8'), request)
    response = Response(
      content=body_bytes,
      media_type='text/html; charset=utf-8',
      status_code=200,
    )
    _set_market_cookie(response, market_id)
    response.headers['Cache-Control'] = 'no-store, private'
    if htmx:
      # Panel-only swap leaves the tab strip stale (active underline stuck on
      # the previously-active market). Fire market-selected so the strip's
      # hx-trigger refetches /markets-strip and re-renders with active_market
      # resolved from the freshly-set selected_market cookie.
      response.headers['HX-Trigger'] = 'market-selected'
    return response

  @app.get('/markets/{market_id}/signals', response_class=Response)
  async def get_market_signals(request: Request, market_id: str):
    return await _serve_market_scoped_page(request, market_id, 'signals')

  @app.get('/markets/{market_id}/settings', response_class=Response)
  async def get_market_settings(request: Request, market_id: str):
    return await _serve_market_scoped_page(request, market_id, 'settings')

  @app.get('/markets/{market_id}/market-test', response_class=Response)
  async def get_market_market_test(request: Request, market_id: str):
    return await _serve_market_scoped_page(request, market_id, 'market-test')

  @app.get('/status-strip', response_class=Response)
  async def get_status_strip(request: Request):
    '''Phase 25 D-06/D-07 Plan 06: status strip fragment endpoint.

    Auth-gated by the existing AuthMiddleware (route NOT in PUBLIC_PATHS).
    Returns the rendered strip fragment for HTMX outerHTML swap.
    Cache-Control: no-store, private (T-25-06-03 cache poisoning mitigation).
    Warning text is NOT rendered (T-25-06-01: only state derivation emitted).
    '''
    import state_manager as _sm
    from dashboard_renderer.components.header import render_status_strip

    from datetime import datetime
    import pytz
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
    '''Phase 25 Plan 05 D-16: return the market tab strip fragment for HTMX swap.

    Called when HX-Trigger: markets-changed fires — refreshes the strip with the
    latest markets list including newly added markets.
    Cache-Control: no-store, private (T-25-04-03 pattern — user-specific content).
    '''
    import state_manager
    from dashboard_renderer.components.nav import render_market_strip

    state = state_manager.load_state()
    # Phase 26 Plan 26-07 (R7): regex-validate the cookie value before lookup.
    # Forged or malformed cookies (whitespace, non-uppercase, control chars)
    # are dropped → fallback to first-market.
    raw_cookie = request.cookies.get('selected_market', '') or ''
    active_market = raw_cookie if _MARKET_ID_RE.fullmatch(raw_cookie) else ''
    markets = state.get('markets', {}) or {}
    if not active_market or active_market not in markets:
      active_market = next(iter(markets), '')
    # Phase 26 Plan 26-07 (R6): read active_function from query param + allowlist
    # validate; replaces the Referer-based fallback (broken under privacy-mode
    # browsers that strip Referer).
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

  def _serve_dashboard_page(
    request: Request,
    page: str,
    fragment: str | None = None,
  ):
    # Page routes share the same forward-stop fragment handler.
    fwd = _forward_stop_fragment_response(request, fragment)
    if fwd is not None:
      return fwd

    import dashboard
    from state_manager import load_state

    page_output = _PAGE_OUTPUTS.get(page, _PAGE_OUTPUTS['signals'])
    page_path = Path(page_output)
    try:
      # Phase 26 Plan 26-07 (R1): each sibling checks its own marker + mtime,
      # so a marker bump or a stale-on-disk sibling triggers regen even when
      # dashboard.html happens to be fresh.
      if _is_stale_for(page_path) or not page_path.exists():
        dashboard.render_dashboard_page(load_state(), page=page, out_path=page_path)
    except Exception as exc:  # noqa: BLE001 — D-10 never-crash
      logger.warning(
        '[Web] dashboard regen failed for page=%s, serving stale: %s: %s',
        page,
        type(exc).__name__,
        exc,
      )

    if not page_path.exists():
      return PlainTextResponse(
        content='dashboard not ready',
        status_code=503,
        media_type='text/plain; charset=utf-8',
      )
    return _serve_dashboard_content(
      request=request,
      content=page_path.read_bytes(),
      fragment=fragment,
    )

  def _serve_dashboard_root(
    request: Request,
    fragment: str | None = None,
  ):
    '''Phase 13 GET / + Phase 14 REVIEWS HIGH #4 (placeholder substitution).

    The on-disk dashboard.html (rendered by main.run_daily_check via
    Plan 14-05) emits the literal placeholder {{WEB_AUTH_SECRET}} inside
    the form's hx-headers attribute. This handler reads the bytes,
    substitutes the placeholder with the actual env-var value at request
    time, and returns the patched bytes. The disk file never contains
    the real secret.

    ?fragment=position-group-{instrument}: returns ONLY that tbody's
    inner HTML (used by Plan 14-05's per-tbody listener for partial
    refresh on positions-changed events).
    '''
    fwd = _forward_stop_fragment_response(request, fragment)
    if fwd is not None:
      return fwd

    # D-07 / Phase 11 C-2: local imports preserve hex boundary.
    import dashboard
    from state_manager import load_state

    try:
      # Phase 26 Plan 26-07 (R1): _is_stale_for(dashboard.html) preserves the
      # original D-08 behaviour for the canonical dashboard.html serve path.
      if _is_stale_for(Path(_DASHBOARD_PATH)):
        dashboard.render_dashboard_files(load_state())
    except Exception as exc:  # noqa: BLE001 — D-10 never-crash
      logger.warning(
        '[Web] dashboard regen failed, serving stale: %s: %s',
        type(exc).__name__,
        exc,
      )

    if not os.path.exists(_DASHBOARD_PATH):  # D-10: first-run case
      return PlainTextResponse(
        content='dashboard not ready',
        status_code=503,
        media_type='text/plain; charset=utf-8',
      )
    return _serve_dashboard_content(
      request=request,
      content=Path(_DASHBOARD_PATH).read_bytes(),
      fragment=fragment,
    )

  def _forward_stop_fragment_response(request: Request, fragment: str | None):
    # Phase 15 CALC-03 + REVIEWS L-1: forward-stop fragment — EXACT match.
    # Handled BEFORE the dashboard.html file-read path because this fragment
    # does not need the on-disk dashboard.html to exist (it reads state.json
    # directly via load_state). Degenerate Z returns em-dash, never 4xx.
    if fragment != 'forward-stop':
      return None
    import html as _html
    import math as _math

    from dashboard import _fmt_currency, _fmt_em_dash  # LOCAL — C-2
    from sizing_engine import get_trailing_stop  # LOCAL — C-2
    from state_manager import load_state as _ls  # LOCAL — C-2

    instrument = request.query_params.get('instrument', '')
    z_raw = request.query_params.get('z', '')
    span_id_suffix = _html.escape(instrument, quote=True) if instrument else 'unknown'

    def _em_dash_response():
      body = f'<span id="forward-stop-{span_id_suffix}-w">{_fmt_em_dash()}</span>'
      return Response(content=body.encode('utf-8'), media_type='text/html; charset=utf-8')

    try:
      z = float(z_raw)
    except (ValueError, TypeError):
      return _em_dash_response()
    if not _math.isfinite(z) or z <= 0:
      return _em_dash_response()

    try:
      state = _ls()
    except (OSError, ValueError, TypeError):
      return _em_dash_response()

    pos = state.get('positions', {}).get(instrument)
    if pos is None:
      return _em_dash_response()

    synth = dict(pos)
    direction = synth.get('direction', 'LONG')
    if direction == 'LONG':
      peak = synth.get('peak_price') or synth.get('entry_price', 0.0)
      synth['peak_price'] = max(peak, z)
    else:
      trough = synth.get('trough_price') or synth.get('entry_price', 0.0)
      synth['trough_price'] = min(trough, z)

    try:
      w = get_trailing_stop(synth, 0.0, 0.0)
    except (ValueError, TypeError, KeyError):
      return _em_dash_response()

    if not _math.isfinite(w):
      w_html = _fmt_em_dash()
    else:
      w_html = _html.escape(_fmt_currency(w), quote=True)

    body = f'<span id="forward-stop-{span_id_suffix}-w">{w_html}</span>'
    return Response(content=body.encode('utf-8'), media_type='text/html; charset=utf-8')

  def _substitute(content: bytes, request: Request) -> bytes:
    '''Phase 26 Plan 26-04 (B2/B3): single substitution helper resolving every
    placeholder kind that flows through the web layer.

    Called from BOTH `_serve_dashboard_content` (file-on-disk dashboard.html
    path) and `_serve_market_scoped_page` (in-memory render_dashboard_as_str
    path). Locality of substitution discipline lives here so the market-scoped
    path cannot diverge from the canonical dashboard path.

    Resolves:
      `{{WEB_AUTH_SECRET}}`  -> os.environ.get('WEB_AUTH_SECRET', '')
                                 (Phase 14 Plan 14-04 Task 5; T-14-15)
      `{{SIGNOUT_BUTTON}}`   -> dashboard._render_signout_button() if cookie
                                 session is valid, else empty
                                 (Phase 16.1)
      `{{SESSION_NOTE}}`     -> dashboard._render_session_note() if no cookie
                                 session, else empty (Phase 16.1)
      `{{TRACE_OPEN_<M>}}`   -> ' open' if <M> is in the tsi_trace_open
                                 cookie's allowlisted set, else empty.
                                 Generalised over any market id matching
                                 ^[A-Z0-9_]{2,20}$ (Phase 17 + Plan 26-04).

    Hex-boundary: imports stay LOCAL inside this function (Phase 11 C-2;
    enforced by tests/test_web_healthz.py::TestWebHexBoundary). Pure
    bytes -> bytes, no Response coupling.
    '''
    # Phase 14 Plan 14-04 Task 5 (REVIEWS HIGH #4): substitute placeholder
    # with env secret at request time so on-disk dashboard.html never
    # carries the real value.
    secret = os.environ.get('WEB_AUTH_SECRET', '').encode('utf-8')
    content = content.replace(_PLACEHOLDER, secret)

    # Phase 16.1: per-request auth widget — Sign Out button (cookie session)
    # vs session note (header auth). LOCAL import preserves hex boundary
    # (Phase 11 C-2; web/routes/dashboard.py is allowed to import dashboard
    # per Phase 13 D-07).
    from dashboard import _render_session_note, _render_signout_button

    if _is_cookie_session(request):
      content = content.replace(
        _SIGNOUT_PLACEHOLDER,
        _render_signout_button().encode('utf-8'),
      )
      content = content.replace(_SESSION_NOTE_PLACEHOLDER, b'')
    else:
      content = content.replace(_SIGNOUT_PLACEHOLDER, b'')
      content = content.replace(
        _SESSION_NOTE_PLACEHOLDER,
        _render_session_note().encode('utf-8'),
      )

    # Phase 17 Plan 17-01 + Phase 26 Plan 26-04: substitute every
    # {{TRACE_OPEN_<MARKET>}} placeholder for any market id matching the
    # canonical ^[A-Z0-9_]{2,20}$ regex. Allowlist via _resolve_trace_open
    # (which itself filters cookie values against _VALID_TRACE_INSTRUMENT_KEYS),
    # so unknown market ids resolve to '' (closed <details>).
    trace_open = _resolve_trace_open(request)

    def _trace_open_repl(match: re.Match) -> bytes:
      market_id = match.group(1).decode('ascii')
      return b' open' if market_id in trace_open else b''

    content = _TRACE_OPEN_RE.sub(_trace_open_repl, content)
    return content

  def _serve_dashboard_content(request: Request, content: bytes, fragment: str | None):
    # Phase 26 Plan 26-04: substitution discipline lives in _substitute helper
    # which is shared with _serve_market_scoped_page (B2/B3). Resolves
    # {{WEB_AUTH_SECRET}}, {{SIGNOUT_BUTTON}}, {{SESSION_NOTE}}, and any
    # {{TRACE_OPEN_<MARKET>}} placeholders before the body reaches the response.
    content = _substitute(content, request)

    if fragment is not None:
      # Extract the tbody whose id matches `fragment`. Returns inner HTML only.
      # Quick-and-dirty regex (string-search) — dashboard markup is
      # server-controlled, not user input, so regex against rendered HTML
      # is safe (re.escape on the user-supplied fragment value blocks any
      # regex-injection attempt).
      m = re.search(
        rb'<tbody id="' + re.escape(fragment.encode('utf-8')) + rb'">(.*?)</tbody>',
        content, re.DOTALL,
      )
      if not m:
        return Response(
          content=b'', status_code=404,
          media_type='text/html; charset=utf-8',
        )
      return Response(
        content=m.group(1),
        media_type='text/html; charset=utf-8',
      )

    return Response(
      content=content,
      media_type='text/html; charset=utf-8',
    )
