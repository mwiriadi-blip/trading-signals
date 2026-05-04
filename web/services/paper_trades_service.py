"""Paper-trade domain service facade for route registration."""

from dataclasses import dataclass

from fastapi import FastAPI

from web.routes import paper_trades as paper_trades_route


@dataclass
class PaperTradesService:
  """Facade preserving paper-trade route API while isolating registration."""

  def register_routes(self, app: FastAPI) -> None:
    paper_trades_route.register(app)
