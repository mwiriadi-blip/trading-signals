"""TOTP domain service facade for route registration."""

from dataclasses import dataclass

from fastapi import FastAPI

from web.routes import totp as totp_route


@dataclass
class TotpService:
  """Facade preserving TOTP route API while isolating registration."""

  def register_routes(self, app: FastAPI) -> None:
    totp_route.register(app)
