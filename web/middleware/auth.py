'''AuthMiddleware — shared-secret X-Trading-Signals-Auth gate.

Phase 13 AUTH-01..AUTH-03 + D-01..D-06.

Architecture (CLAUDE.md hex-lite + Phase 10 D-15):
  web/middleware/ is an adapter hex (peer of web/routes/, notifier.py, dashboard.py).
  Allowed web/middleware imports: fastapi, starlette, stdlib.
  Forbidden imports: signal_engine, sizing_engine, system_params,
                     data_fetcher, notifier, dashboard, main, state_manager.
  Enforced by tests/test_web_healthz.py::TestWebHexBoundary.

Contract (CONTEXT.md 2026-04-25):
  D-01: ASGI middleware via app.add_middleware() — sole enforcement chokepoint.
  D-02: /healthz exempt via EXEMPT_PATHS frozenset allowlist (first line of dispatch).
  D-03: hmac.compare_digest on UTF-8-encoded bytes; never `==`.
  D-04: 401 response body literal `unauthorized`, Content-Type text/plain; charset=utf-8.
  D-05: WARN log shape `[Web] auth failure: ip=%s ua=%r path=%s`. IP from
        X-Forwarded-For first entry (split by comma); fallback request.client.host.
        UA truncated to 120 chars; %r escapes control chars.
  D-06: AuthMiddleware registered LAST in create_app() so it runs FIRST
        (Starlette reverses registration order).

NOTE (Phase 14 forward warning): this middleware does NOT propagate contextvars
set in downstream handlers back up the middleware chain (BaseHTTPMiddleware
limitation). Phase 13 does not use contextvars or BackgroundTasks. If Phase 14+
introduces BackgroundTasks from auth-gated routes, migrate to pure ASGI
middleware. Refs: github.com/Kludex/starlette/issues/2093, discussions/1729.

Log prefix: [Web] — Phase 11 convention.
'''
import hmac
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

EXEMPT_PATHS = frozenset({'/healthz'})  # D-02
AUTH_HEADER = 'X-Trading-Signals-Auth'  # AUTH-01
UA_TRUNCATE = 120  # D-05 / SC-5


class AuthMiddleware(BaseHTTPMiddleware):
  '''Shared-secret header auth (D-01..D-06).'''

  def __init__(self, app: ASGIApp, *, secret: str):
    super().__init__(app)
    self._secret_bytes = secret.encode('utf-8')  # D-03: bytes-typed

  async def dispatch(self, request: Request, call_next):
    # D-02: path-allowlist exemption FIRST
    if request.url.path in EXEMPT_PATHS:
      return await call_next(request)

    presented = request.headers.get(AUTH_HEADER, '').encode('utf-8')
    if not hmac.compare_digest(presented, self._secret_bytes):  # D-03
      self._log_failure(request)  # D-05
      return Response(
        content='unauthorized',
        status_code=401,
        media_type='text/plain; charset=utf-8',
      )  # D-04

    return await call_next(request)

  @staticmethod
  def _log_failure(request: Request) -> None:
    xff = request.headers.get('x-forwarded-for', '')
    # D-05: XFF may be 'client, proxy1, proxy2' — first entry is real client
    client_ip = (
      xff.split(',')[0].strip()
      if xff
      else (request.client.host if request.client else '-')
    )
    ua = (request.headers.get('user-agent') or '')[:UA_TRUNCATE]
    logger.warning(
      '[Web] auth failure: ip=%s ua=%r path=%s',
      client_ip,
      ua,
      request.url.path,
    )
