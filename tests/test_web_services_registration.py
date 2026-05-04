from fastapi import FastAPI

from web.services import DashboardService, PaperTradesService, TotpService, TradesService


def test_dashboard_service_registers_dashboard_routes(monkeypatch) -> None:
  calls: list[FastAPI] = []
  app = FastAPI()

  def _fake_register(target: FastAPI) -> None:
    calls.append(target)

  monkeypatch.setattr("web.routes.dashboard.register", _fake_register)
  DashboardService().register_routes(app)
  assert calls == [app]


def test_trades_service_registers_trade_routes(monkeypatch) -> None:
  calls: list[FastAPI] = []
  app = FastAPI()

  def _fake_register(target: FastAPI) -> None:
    calls.append(target)

  monkeypatch.setattr("web.routes.trades.register", _fake_register)
  TradesService().register_routes(app)
  assert calls == [app]


def test_paper_trades_service_registers_routes(monkeypatch) -> None:
  calls: list[FastAPI] = []
  app = FastAPI()

  def _fake_register(target: FastAPI) -> None:
    calls.append(target)

  monkeypatch.setattr("web.routes.paper_trades.register", _fake_register)
  PaperTradesService().register_routes(app)
  assert calls == [app]


def test_totp_service_registers_totp_routes(monkeypatch) -> None:
  calls: list[FastAPI] = []
  app = FastAPI()

  def _fake_register(target: FastAPI) -> None:
    calls.append(target)

  monkeypatch.setattr("web.routes.totp.register", _fake_register)
  TotpService().register_routes(app)
  assert calls == [app]
