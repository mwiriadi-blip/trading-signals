"""Trade-domain service facade for route registration."""

from dataclasses import dataclass

from fastapi import FastAPI

from web.routes import trades as trades_route


@dataclass
class TradesService:
  """Facade preserving route public API while isolating registration."""

  def register_routes(self, app: FastAPI) -> None:
    trades_route.register(app)
