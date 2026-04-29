'''Web application factory — Phase 11 D-02 + Phase 13 D-01..D-21+.

Architecture (CLAUDE.md hex-lite + Phase 10 D-15):
  web/ is an adapter hex (peer of notifier.py, dashboard.py).
  Allowed web imports: fastapi, starlette, stdlib, read-only state access via
                       routes/healthz.py, routes/state.py, and routes/dashboard.py
                       (the latter calls dashboard.render_dashboard per D-07).
  Forbidden imports: signal_engine, sizing_engine, system_params,
                     data_fetcher, notifier, main.
  Enforced by tests/test_web_healthz.py::TestWebHexBoundary.

Phase 13 changes (D-01..D-22):
  - WEB_AUTH_SECRET validated at boot — fail-closed via RuntimeError (D-16/D-17).
  - FastAPI(docs_url=None, redoc_url=None, openapi_url=None) — D-21 + research
    extension D-22 (openapi_url=None is REQUIRED to fully suppress schema —
    docs_url + redoc_url alone leave /openapi.json publicly exposed).
  - AuthMiddleware registered LAST so it runs FIRST (D-06).
  - Three routes registered: /healthz (Phase 11) + / (Phase 13) + /api/state (Phase 13).

Phase 14 changes (D-13/D-14):
  - Phase 10 D-15 ("web is read-only on state.json") is AMENDED:
    web/routes/trades.py introduces /trades/{open,close,modify} POST
    endpoints that mutate state.json. Cross-process coordination via
    fcntl.LOCK_EX in state_manager.mutate_state (Plan 14-02).
  - 422 -> 400 remap installed via add_exception_handler — Pydantic
    validation errors return JSONResponse with body
    {"errors": [{"field": ..., "reason": ...}]} per TRADE-02.
  - Hex-boundary inheritance: sizing_engine + system_params now allowed
    for web/routes/trades.py per Plan 14-01 FORBIDDEN_FOR_WEB update.

Log prefix: [Web] for all web-process log lines.
'''
import logging
import os

from fastapi import FastAPI

from web.middleware.auth import AuthMiddleware
from web.routes import dashboard as dashboard_route
from web.routes import healthz as healthz_route
from web.routes import state as state_route
from web.routes import trades as trades_route

logger = logging.getLogger(__name__)

_MIN_SECRET_LEN = 32  # D-17: ≈128 bits entropy via openssl rand -hex 16


def _read_auth_credentials() -> tuple[str, str]:
  '''Phase 16.1 D-08 + Phase 13 D-16/D-17: fail-closed username + secret read.

  Validates username FIRST (D-08): non-empty, no ':' character (legacy Basic
  Auth field separator — even with E-01 killing the Basic Auth path, ':' in
  username is rejected to defend against operators typing literal user:pw).
  Then validates secret (Phase 13 D-16/D-17 message strings preserved
  byte-exact — Phase 13 grep tests depend on them).

  Returns (username, secret) tuple. systemd's Restart=on-failure surfaces
  the RuntimeError in journald so the operator sees the cause immediately.
  '''
  username = os.environ.get('WEB_AUTH_USERNAME', '').strip()
  if not username:
    raise RuntimeError(
      'WEB_AUTH_USERNAME env var is missing or empty — refusing to start. '
      'Add WEB_AUTH_USERNAME=<your-name> to /home/trader/trading-signals/.env'
    )
  if ':' in username:
    raise RuntimeError(
      "WEB_AUTH_USERNAME must not contain ':' (legacy Basic Auth field "
      'separator). Pick a colon-free username and restart the service.'
    )

  secret = os.environ.get('WEB_AUTH_SECRET', '').strip()
  if not secret:
    raise RuntimeError(
      'WEB_AUTH_SECRET env var is missing or empty — refusing to start. '
      'Add WEB_AUTH_SECRET=<32+ chars> to /home/trader/trading-signals/.env'
    )
  if len(secret) < _MIN_SECRET_LEN:
    raise RuntimeError(
      f'WEB_AUTH_SECRET must be at least {_MIN_SECRET_LEN} characters. '
      'Generate with: openssl rand -hex 16'
    )
  return username, secret


def create_app() -> FastAPI:
  '''Factory — returns a configured FastAPI app (D-02 + D-16..D-22).

  Order is significant:
    1. Validate the secret BEFORE FastAPI() instantiation (fail-closed at boot).
    2. Construct FastAPI with all THREE schema-suppression kwargs (D-21+D-22).
    3. Register routes (healthz, dashboard, state).
    4. Register AuthMiddleware LAST so it runs FIRST (D-06 — Starlette
       executes middleware in REVERSE of registration order).

  Future middleware (request-id, compression, etc.) MUST be registered BEFORE
  the AuthMiddleware line below — otherwise they will run AFTER auth, which
  defeats the security gate.
  '''
  username, secret = _read_auth_credentials()  # Phase 16.1 D-08 + Phase 13 D-16/D-17

  application = FastAPI(
    title='Trading Signals',
    description='SPI 200 & AUD/USD mechanical trading signal system',
    version='1.1.0',
    docs_url=None,      # D-21
    redoc_url=None,     # D-21
    openapi_url=None,   # D-22 (research extension to D-21): without this,
                        # /openapi.json keeps serving the full schema.
  )

  # Register routes first (they become the inner-most layer of the dispatch).
  healthz_route.register(application)
  dashboard_route.register(application)
  state_route.register(application)
  trades_route.register(application)

  # Phase 14 D-04 / TRADE-02: 422 -> 400 remap with field-level error JSON.
  # Single global handler covers all routes (Plan 14-04).
  from fastapi.exceptions import RequestValidationError
  application.add_exception_handler(
    RequestValidationError, trades_route._validation_exception_handler,
  )

  # D-06: AuthMiddleware MUST be registered LAST — Starlette runs middleware
  # in REVERSE of registration, so 'last registered' = 'first to dispatch'.
  # Future middleware (request-id, compression) goes ABOVE this line.
  application.add_middleware(AuthMiddleware, secret=secret, username=username)

  logger.info('[Web] FastAPI app created (Phase 16.1 — cookie+TOTP+header auth; auth=on)')
  return application


# Module-level app — uvicorn entry point: `uvicorn web.app:app`
app = create_app()
