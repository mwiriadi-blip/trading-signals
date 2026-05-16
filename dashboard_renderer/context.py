'''Render context primitives for phased migration.'''

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable


@dataclass(slots=True)
class RenderContext:
  state: dict
  now: datetime
  strategy_version: str
  trace_open_keys: tuple[str, ...] = ()
  active_function: str = 'signals'   # Phase 25 D-01: one of 'signals'|'account'|'settings'|'market-test'
  active_market: str | None = None   # Phase 25 D-03/D-04: None on /account; market_id otherwise
  # Phase 38: per-user news state (dicts keyed by market_id)
  uid: str | None = None
  news_dismissed: dict = field(default_factory=dict)       # market_id → {'date': ..., 'hashes': [...]}
  news_panel_collapsed: dict = field(default_factory=dict) # market_id → bool

  @classmethod
  def build(
    cls,
    *,
    state: dict,
    now: datetime,
    strategy_version: str,
    trace_open_keys: Iterable[str] | None = None,
    active_function: str = 'signals',
    active_market: str | None = None,
    uid: str | None = None,
    news_dismissed: dict | None = None,
    news_panel_collapsed: dict | None = None,
  ) -> 'RenderContext':
    return cls(
      state=state,
      now=now,
      strategy_version=strategy_version,
      trace_open_keys=tuple(trace_open_keys or ()),
      active_function=active_function,
      active_market=active_market,
      uid=uid,
      news_dismissed=news_dismissed if news_dismissed is not None else {},
      news_panel_collapsed=news_panel_collapsed if news_panel_collapsed is not None else {},
    )
