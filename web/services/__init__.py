"""Web domain service facades used by route adapters."""

from .dashboard_service import DashboardService
from .paper_trades_service import PaperTradesService
from .totp_service import TotpService
from .trades_service import TradesService

__all__ = ["TradesService", "PaperTradesService", "DashboardService", "TotpService"]
