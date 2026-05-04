"""Service facades for daily orchestration flow.

These classes keep orchestration composition outside entrypoint wiring and make
`main.py` an explicit composition boundary.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime


@dataclass
class DailyRunService:
  """Coordinates the daily-run workflow through an injected implementation."""

  run_impl: Callable

  def run_daily_check(self, args):
    return self.run_impl(args)


@dataclass
class SignalEvaluationService:
  """Coordinates post-save signal/alert evaluation through injected callables."""

  evaluate_impl: Callable[[dict, str], dict]

  def evaluate_paper_trade_alerts(self, state: dict, dashboard_url: str) -> dict:
    return self.evaluate_impl(state, dashboard_url)


@dataclass
class PostRunService:
  """Coordinates post-run side effects through injected callables."""

  dispatch_impl: Callable[[dict, dict, datetime, bool, bool], None]
  push_impl: Callable[[dict, datetime], None]

  def dispatch_email_and_maintain_warnings(
    self,
    state: dict,
    old_signals: dict,
    now: datetime,
    is_test: bool,
    persist: bool,
  ) -> None:
    self.dispatch_impl(state, old_signals, now, is_test, persist)

  def push_state_to_git(self, state: dict, now: datetime) -> None:
    self.push_impl(state, now)
