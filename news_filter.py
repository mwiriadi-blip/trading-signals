'''Phase 38 NEWS-02: pure-math hex keyword classifier for critical-event banners.

Hex-boundary: stdlib-only (re + logging + dataclasses + typing). Imports ONLY:
  - re
  - logging
  - dataclasses
  - typing
  - system_params (NEWS_KEYWORDS_SPI200, NEWS_KEYWORDS_AUDUSD, NEWS_DAMPENER_ALLOWLIST)

FORBIDDEN imports (would break _HEX_PATHS_STDLIB_ONLY AST guard):
  os, sys, json, datetime, pathlib, io, requests, urllib, http,
  yfinance, numpy, pandas, schedule, dotenv, pytz,
  signal_engine, sizing_engine, state_manager, notifier, dashboard,
  news_fetcher, auth_store, web.

Public API:
  classify_headline(text: str, market_id: str) -> bool
  has_critical_event(result: Any, market_id: str) -> CriticalEventResult
'''
import logging
import re
from dataclasses import dataclass
from typing import Any, Literal

from system_params import (
  NEWS_DAMPENER_ALLOWLIST,
  NEWS_KEYWORDS_AUDUSD,
  NEWS_KEYWORDS_SPI200,
)

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CriticalEventResult — structured return type for has_critical_event (D-02).
# gate_status drives the BLOCK_ON_FAILURE policy in daily_run.py.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CriticalEventResult:
  '''Structured result for has_critical_event.

  gate_status semantics (D-02 BLOCK_ON_FAILURE):
    "clear"   — fetch succeeded, no critical keyword matched → allow signals
    "blocked" — fetch succeeded, critical keyword matched → skip signals
    "unknown" — fetch failed (error is set) → skip signals (fail-closed)
  '''
  triggered: bool
  fetch_error: 'str | None'
  gate_status: 'Literal["clear", "blocked", "unknown"]'


# ---------------------------------------------------------------------------
# Module-level compiled artefacts (compiled once at import time)
# ---------------------------------------------------------------------------

_MARKET_KEYWORDS: dict[str, tuple[str, ...]] = {
  'SPI200': NEWS_KEYWORDS_SPI200,
  'AUDUSD': NEWS_KEYWORDS_AUDUSD,
}


def _build_pattern(keywords: tuple[str, ...]) -> re.Pattern:
  '''Compile keyword tuple into a word-boundary OR pattern (IGNORECASE).

  Each keyword is re.escape()'d before wrapping in \\b anchors so literal
  hyphens, spaces, and special chars in multi-word keywords match exactly.
  Compiling once at import time avoids per-call overhead.
  '''
  parts = [r'\b' + re.escape(kw) + r'\b' for kw in keywords]
  return re.compile('|'.join(parts), re.IGNORECASE)


_PATTERNS: dict[str, re.Pattern] = {
  market: _build_pattern(kws)
  for market, kws in _MARKET_KEYWORDS.items()
}

# Dampener: phrases that contain a keyword substring but are NOT critical-event
# signals (e.g. "first-rate" matches "rate" but is not a rate decision).
# Using simple |join; re.escape handles hyphens/spaces in multi-word entries.
# Guard: empty allowlist must compile to a never-matching pattern (r'(?!)'),
# not '|'.join([]) which would produce '' and match everything.
if NEWS_DAMPENER_ALLOWLIST:
  _DAMPENER_RE: re.Pattern = re.compile(
    '|'.join(re.escape(d) for d in NEWS_DAMPENER_ALLOWLIST),
    re.IGNORECASE,
  )
else:
  _DAMPENER_RE = re.compile(r'(?!)')

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def classify_headline(text: str, market_id: str) -> bool:
  '''Return True if text contains a critical-event keyword for market_id.

  Algorithm:
    1. Look up compiled pattern for market_id; unknown id logs WARNING, returns False.
    2. Fast path: no dampener match -> return keyword search result directly.
    3. Slow path: substitute all dampener spans with empty string, re-run keyword
       search on scrubbed text. This prevents "first-rate service" triggering on
       "rate" while "first-rate service after RBA rate cut" still fires on "rate cut".

  Args:
    text:      Raw headline string (may be any case; comparison is IGNORECASE).
    market_id: Known market identifier, e.g. 'SPI200' or 'AUDUSD'.

  Returns:
    True if text (post-dampener scrubbing) matches at least one keyword.
    False if no match, empty text, or unknown market_id.
  '''
  pat = _PATTERNS.get(market_id)
  if pat is None:
    _LOGGER.warning(
      'classify_headline received unknown market_id=%r; returning False',
      market_id,
    )
    return False

  if not text:
    return False

  text_lower = text.lower()

  # Fast path: no dampener phrase present — skip scrubbing overhead.
  if not _DAMPENER_RE.search(text_lower):
    return bool(pat.search(text_lower))

  # Slow path: remove dampener spans then re-run keyword search.
  scrubbed = _DAMPENER_RE.sub('', text_lower)
  return bool(pat.search(scrubbed))


def has_critical_event(result: Any, market_id: str) -> CriticalEventResult:
  '''Classify a NewsResult for critical market-moving events.

  D-02 BLOCK_ON_FAILURE mapping:
    - result.error is not None → gate_status="unknown" (fetch failed → fail-closed)
    - result.error is None and keyword matched → gate_status="blocked"
    - result.error is None and no match → gate_status="clear"

  Args:
    result:    NewsResult from news_fetcher.fetch_news.
    market_id: Known market identifier, e.g. 'SPI200' or 'AUDUSD'.

  Returns:
    CriticalEventResult with gate_status driving the BLOCK_ON_FAILURE policy.
  '''
  # Fail-closed: if fetch failed, gate_status='unknown' blocks signals.
  if result.error is not None:
    return CriticalEventResult(
      triggered=False,
      fetch_error=result.error,
      gate_status='unknown',
    )

  # Fetch succeeded — classify each headline.
  for item in result.items:
    title = item.get('title', '') if hasattr(item, 'get') else ''
    if classify_headline(title, market_id):
      return CriticalEventResult(
        triggered=True,
        fetch_error=None,
        gate_status='blocked',
      )

  return CriticalEventResult(
    triggered=False,
    fetch_error=None,
    gate_status='clear',
  )
