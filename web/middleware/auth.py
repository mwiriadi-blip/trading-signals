'''AuthMiddleware — Phase 13 header path + Phase 16.1 cookie path; no Basic Auth.

Phase 13 baseline (AUTH-01..AUTH-03 + D-01..D-06):
  D-01: ASGI middleware via app.add_middleware() — sole enforcement chokepoint.
  D-02: /healthz exempt via EXEMPT_PATHS frozenset allowlist.
  D-03: hmac.compare_digest on UTF-8-encoded bytes; never `==`.
  D-04: 401 response body literal `unauthorized`, Content-Type text/plain.
  D-05: WARN log shape `[Web] auth failure: ip=%s ua=%r path=%s`. IP from
        X-Forwarded-For first entry; UA truncated to 120 chars; %r escapes.
  D-06: AuthMiddleware registered LAST in create_app() so it runs FIRST.

Phase 16.1 changes (D-04..D-07 + E-01 + E-02 — TOTP fold-in 2026-04-29):
  E-01 / AUTH-12: Basic Auth path REMOVED. The middleware does NOT decode
        Authorization: Basic. Operator URL-bar `https://user:pw@host/` form
        gets the same 302/401 branching as a no-auth request.
  E-02 (3-step sniff, supersedes Phase 13 single-path):
        Step 1: validate signed cookie (tsi_session) — grant on success.
        Step 2: validate X-Trading-Signals-Auth header — grant on success.
        Step 3: log failure ONCE, then branch on Sec-Fetch:
                browser navigation → 302 Location: /login?next=<path>
                non-browser        → 401 plain-text "unauthorized"
        The browser-Basic-Auth dialog header is NEVER sent (LEARNING 2026-04-27
        + AUTH-02 spirit — no leaked info, no hints).
  D-04: Browser-conditional behavior — Sec-Fetch-Mode=navigate AND
        Sec-Fetch-Dest=document → 302; OR Accept: text/html (when Sec-Fetch
        absent) → 302; everything else → 401 plain-text (Phase 13 contract
        verbatim per AUTH-07).
  PUBLIC_PATHS: /login, /enroll-totp, /verify-totp are publicly reachable
        for the auth-bootstrap flow. Plan 16.1-03 will EXTEND this with
        /forgot-2fa and /reset-totp.

Architecture (CLAUDE.md hex-lite + Phase 10 D-15):
  web/middleware/ is an adapter hex (peer of web/routes/, notifier.py).
  Allowed imports: fastapi, starlette, stdlib, itsdangerous (D-10).
  Forbidden imports: signal_engine, sizing_engine, system_params,
                     data_fetcher, notifier, dashboard, main, state_manager.
  Enforced by tests/test_web_healthz.py::TestWebHexBoundary.

Log prefix: [Web] — Phase 11 convention.
'''
import hmac
import logging
from urllib.parse import quote

from itsdangerous import BadSignature, SignatureExpired
from itsdangerous.url_safe import URLSafeTimedSerializer
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

# Phase 13 D-02 — exempt-from-auth allowlist.
EXEMPT_PATHS = frozenset({'/healthz'})

# Phase 16.1 — auth-bootstrap routes (publicly reachable; sub-routes still
# validated by their handlers via tsi_enroll/tsi_pending cookies).
# Plan 16.1-03 will EXTEND PUBLIC_PATHS with /forgot-2fa and /reset-totp.
PUBLIC_PATHS = frozenset({'/login', '/enroll-totp', '/verify-totp'})

AUTH_HEADER = 'X-Trading-Signals-Auth'  # AUTH-01
UA_TRUNCATE = 120  # D-05 / SC-5

# Phase 16.1 D-04 — browser navigation 302 target. Named constant for
# grep-friendliness.
BROWSER_REDIRECT_TARGET = '/login'

# Phase 16.1 D-10 / D-11 — cookie session config. Salt aligned with system_params
# .TSI_SESSION_SALT for grep-discoverability (LEARNING 2026-04-27); the literal
# string is the contract — DO NOT import system_params (hex boundary).
_SESSION_COOKIE_NAME = 'tsi_session'
_SESSION_SALT = 'tsi-session-cookie'
_SESSION_MAX_AGE_SECONDS = 43200  # 12 hours (D-11)


class AuthMiddleware(BaseHTTPMiddleware):
  '''Phase 13 + Phase 16.1: cookie → header → unauth-branch (E-02).'''

  def __init__(self, app: ASGIApp, *, secret: str, username: str):
    super().__init__(app)
    self._secret_bytes = secret.encode('utf-8')  # D-03: bytes-typed
    self._username_bytes = username.encode('utf-8')  # D-08
    # Pre-build the serializer ONCE so per-request validation is just a
    # signature check (URLSafeTimedSerializer constructor is non-trivial).
    self._session_serializer = URLSafeTimedSerializer(secret, salt=_SESSION_SALT)

  async def dispatch(self, request: Request, call_next):
    # D-02: path-allowlist exemption FIRST.
    if request.url.path in EXEMPT_PATHS:
      return await call_next(request)

    # Phase 16.1: auth-bootstrap routes (public so the operator can reach
    # /login and the TOTP flow without auth). Sub-handlers still validate
    # tsi_enroll/tsi_pending cookies.
    if request.url.path in PUBLIC_PATHS:
      return await call_next(request)

    # E-02 step 1: signed cookie (Phase 16.1 D-10).
    if self._try_cookie(request):
      return await call_next(request)

    # E-02 step 2: legacy header path (Phase 13 D-03 — preserved per AUTH-05).
    if self._try_header(request):
      return await call_next(request)

    # E-02 step 3: log failure ONCE, then branch on Sec-Fetch.
    self._log_failure(request)
    if self._is_browser_navigation(request):
      next_path = quote(request.url.path)
      return Response(
        status_code=302,
        headers={'Location': f'{BROWSER_REDIRECT_TARGET}?next={next_path}'},
      )
    return Response(
      content='unauthorized',
      status_code=401,
      media_type='text/plain; charset=utf-8',
    )  # D-04

  def _try_cookie(self, request: Request) -> bool:
    '''Validate tsi_session cookie via itsdangerous (Phase 16.1 D-10).

    Returns True iff the cookie is present, signed correctly with the secret
    we know, AND not expired (max_age=43200s). Does NOT log on failure —
    step 3 of dispatch is the single audit-log site (sampling pyramid 1).

    LEGB rule: SignatureExpired is a subclass of BadSignature, so the
    expired branch MUST come first.
    '''
    token = request.cookies.get(_SESSION_COOKIE_NAME)
    if not token:
      return False
    try:
      self._session_serializer.loads(token, max_age=_SESSION_MAX_AGE_SECONDS)
      return True
    except SignatureExpired:
      return False
    except BadSignature:
      return False

  def _try_header(self, request: Request) -> bool:
    '''Phase 13 D-03 path preserved — AUTH-05 regression-locked.

    Single call site for hmac.compare_digest in this module (helper-shadowing
    absent per LEARNING 2026-04-25).
    '''
    presented = request.headers.get(AUTH_HEADER, '').encode('utf-8')
    return hmac.compare_digest(presented, self._secret_bytes)

  @staticmethod
  def _is_browser_navigation(request: Request) -> bool:
    '''D-04: detect a browser navigation request (vs script/HTMX/curl).

    Modern browsers (Safari iOS 16.4+, Chrome 76+, Firefox 90+) send
    Sec-Fetch-Mode=navigate + Sec-Fetch-Dest=document on top-level navigations.
    Older clients without Sec-Fetch fall back to Accept: text/html sniff.

    Per project LEARNING 2026-04-27: Sec-Fetch is not universal — must keep
    the Accept fallback for older iOS Safari.
    '''
    mode = request.headers.get('sec-fetch-mode', '').lower()
    dest = request.headers.get('sec-fetch-dest', '').lower()
    if mode == 'navigate' and dest == 'document':
      return True
    # Fallback: Accept: text/html when Sec-Fetch headers are absent.
    has_secfetch = any(
      h.lower().startswith('sec-fetch-') for h in request.headers
    )
    if has_secfetch:
      # Sec-Fetch was sent but did not match navigate/document — explicit
      # not-a-navigation signal (HTMX XHR carries Sec-Fetch-Mode=cors etc.).
      return False
    accept = request.headers.get('accept', '').lower()
    return 'text/html' in accept

  @staticmethod
  def _log_failure(
    request: Request, reason: str = 'all_paths_failed',
  ) -> None:
    '''D-05: WARN log line with reason. Single audit-log site per
    sampling-pyramid 1 — _try_* helpers do NOT log; only step 3 logs once.

    Phase 16.1: added optional `reason` kwarg (default 'all_paths_failed' —
    accurate for the 3-path world; route handlers may pass 'wrong_username',
    'wrong_secret', 'wrong_code' etc. for finer-grained audit).
    '''
    xff = request.headers.get('x-forwarded-for', '')
    client_ip = (
      xff.split(',')[0].strip()
      if xff
      else (request.client.host if request.client else '-')
    )
    ua = (request.headers.get('user-agent') or '')[:UA_TRUNCATE]
    logger.warning(
      '[Web] auth failure: ip=%s ua=%r path=%s reason=%s',
      client_ip,
      ua,
      request.url.path,
      reason,
    )
