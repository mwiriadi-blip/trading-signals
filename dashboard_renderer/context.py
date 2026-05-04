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

  @classmethod
  def build(
    cls,
    *,
    state: dict,
    now: datetime,
    strategy_version: str,
    trace_open_keys: Iterable[str] | None = None,
  ) -> 'RenderContext':
    return cls(
      state=state,
      now=now,
      strategy_version=strategy_version,
      trace_open_keys=tuple(trace_open_keys or ()),
    )
