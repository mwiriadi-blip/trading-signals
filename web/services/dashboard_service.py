"""Dashboard domain service facade for route registration."""

from dataclasses import dataclass

from fastapi import FastAPI

from web.routes import dashboard as dashboard_route


@dataclass
class DashboardService:
  """Facade preserving dashboard route API while isolating registration."""

  def register_routes(self, app: FastAPI) -> None:
    dashboard_route.register(app)
