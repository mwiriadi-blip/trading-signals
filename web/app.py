'''Web application factory — Phase 11 D-02.

Architecture (CLAUDE.md hex-lite + Phase 10 D-15):
  web/ is an adapter hex (peer of notifier.py, dashboard.py).
  Allowed web imports: fastapi, stdlib, read-only state access via healthz handler.
  Forbidden imports: signal_engine, sizing_engine, system_params,
                     data_fetcher, notifier, dashboard, main.
  Enforced by tests/test_web_healthz.py::TestWebHexBoundary.

Log prefix: [Web] for all web-process log lines.
'''
import logging

from fastapi import FastAPI

from web.routes import healthz as healthz_route

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
  '''Factory — returns a configured FastAPI app (D-02).

  Swagger UI (/docs) and Redoc (/redoc) are LEFT AT FASTAPI DEFAULTS
  for Phase 11 (REVIEWS MEDIUM #6). No external HTTPS yet (Phase 12);
  disabling them is extra policy beyond locked Phase 11 decisions.
  '''
  application = FastAPI(
    title='Trading Signals',
    description='SPI 200 & AUD/USD mechanical trading signal system',
    version='1.1.0',
  )
  healthz_route.register(application)
  logger.info('[Web] FastAPI app created (Phase 11 — /healthz only)')
  return application


# Module-level app — uvicorn entry point: `uvicorn web.app:app`
app = create_app()
