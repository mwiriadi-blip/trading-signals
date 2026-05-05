'''Render context primitives for phased migration.'''

from dataclasses import dataclass
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
  ) -> 'RenderContext':
    return cls(
      state=state,
      now=now,
      strategy_version=strategy_version,
      trace_open_keys=tuple(trace_open_keys or ()),
      active_function=active_function,
      active_market=active_market,
    )
