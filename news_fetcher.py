'''Phase 38 NEWS-01 + NEWS-03: news I/O adapter.

Hex role: I/O adapter (peer of data_fetcher.py). Owns all yfinance.Ticker.news
calls. Normalises both pre-0.2.55 (uuid/title/link schema) and post-0.2.55
(content envelope schema) into a single TypedDict NewsItem that includes
`title_hash` for dismiss-by-hash and dedup (consumed by Plan 04).

Security posture:
  - market_id validated against _VALID_MARKETS allowlist before any Path
    construction (T-38-03-04 path-traversal closed).
  - URL scheme validated at fetch layer: javascript:/data:/relative rejected
    (T-38-03-03 defence-in-depth; Plan 04 also escapes the href at render time).
  - XSS: headline title preserved VERBATIM at fetch layer; html.escape is
    render-time-only (T-38-03-01 — Plan 04 responsibility).
  - SSRF: zero server-side HTTP calls to headline URLs anywhere in this module
    (T-38-03-02). AST gate test_no_server_side_url_prefetch enforces this.
  - Cache TTL: JSON envelope `date` field is the SOLE TTL authority; filesystem
    mtime is NEVER consulted (T-38-03-09).
  - Concurrent write safety: tempfile + os.replace atomic write (T-38-03-08).

AST hex boundary (FORBIDDEN_MODULES_NEWS_FETCHER in test_signal_engine.py):
  must not import signal_engine, sizing_engine, state_manager, notifier,
  dashboard, main, numpy, schedule, dotenv, pytz.
'''
import hashlib
import json
import logging
import os
import re
import tempfile
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal, TypedDict

import requests.exceptions

from system_params import HTTP_TIMEOUT_S

_LOGGER = logging.getLogger(__name__)

# =========================================================================
# NewsItem TypedDict — canonical shape for all downstream consumers.
# title_hash: sha256 of normalised title, hex-truncated to 16 chars.
# =========================================================================

class NewsItem(TypedDict):
  title: str
  url: str
  publisher: str
  pub_date: str
  title_hash: str


# =========================================================================
# NewsResult — structured return type for fetch_news (D-02 fail-closed gate).
# error is None on success; one of the typed reason strings on failure.
# fetched_at is always populated so callers can log timing.
# =========================================================================

@dataclass(frozen=True)
class NewsResult:
  '''Structured result for fetch_news — NEVER a bare list (D-02 fail-closed).

  Typed error reasons (T-43-05: no raw exception text surfaced to dashboard):
    "timeout"             — ReadTimeout after retries exhausted
    "http_error"          — Non-2xx HTTP response
    "parse_error"         — JSON / schema parse failure
    "network_unreachable" — ConnectionError after retries exhausted
  '''
  items: list = field(default_factory=list)
  error: 'str | None' = None
  fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))

  def __post_init__(self):
    # Validate typed error reasons (prevents raw exception strings leaking).
    _VALID_ERRORS = frozenset({
      'timeout', 'http_error', 'parse_error', 'network_unreachable', None,
    })
    if self.error not in _VALID_ERRORS:
      # Coerce unknown errors to parse_error to avoid leaking raw text.
      object.__setattr__(self, 'error', 'parse_error')


# =========================================================================
# Valid markets allowlist (path-traversal gate).
# Single source of truth: system_params.KNOWN_MARKET_IDS (T-38-03-04).
# =========================================================================

from system_params import KNOWN_MARKET_IDS as _VALID_MARKETS


# =========================================================================
# Retry exceptions (narrow-catch discipline — mirrors data_fetcher.py)
# =========================================================================

_RETRY_EXCEPTIONS = (
  requests.exceptions.ReadTimeout,
  requests.exceptions.ConnectionError,
)


# =========================================================================
# Lazy yfinance accessor (Phase 27 #14 pattern — mirrors data_fetcher.py)
# =========================================================================

_yf = None  # memoized yfinance module reference; populated by _get_yf()


def _get_yf():
  '''Lazy-import accessor for the yfinance module.

  Returns the imported yfinance module. Memoized — first call pays the
  import cost; subsequent calls are O(1). Monkeypatch-friendly: tests
  patch news_fetcher._get_yf directly.
  '''
  global _yf
  if _yf is None:
    import yfinance as yf_  # local import — first call only
    _yf = yf_
  return _yf


# =========================================================================
# Title normalisation and hashing
# =========================================================================

_TITLE_WS_RE = re.compile(r'\s+')


def _normalise_title_for_hash(title: str) -> str:
  '''Stable normalisation for hashing: strip + lowercase + collapse whitespace.

  Stable across: leading/trailing whitespace, internal whitespace collapsing,
  and case differences. This is the ONLY transformation applied before hashing;
  the title field in NewsItem stays verbatim (no escape, no normalisation).
  '''
  return _TITLE_WS_RE.sub(' ', title.strip().lower())


def _compute_title_hash(title: str) -> str:
  '''sha256 of normalised title, hex-truncated to 16 chars.

  Used for dedup (same headline from multiple calls) and Plan 04
  dismiss-by-hash. Stable across whitespace and case variations.
  '''
  normalised = _normalise_title_for_hash(title)
  return hashlib.sha256(normalised.encode('utf-8')).hexdigest()[:16]


# =========================================================================
# URL scheme validation (defence-in-depth — T-38-03-03)
# =========================================================================

_ALLOWED_URL_SCHEMES = ('https://', 'http://')


def _validate_url_scheme(url: str) -> str:
  '''Accept https:// and http:// URLs; reject everything else.

  Rejects javascript:, data:, mailto:, relative paths, empty strings.
  Defence-in-depth: Plan 04 also html.escapes the href at render time.
  '''
  if not isinstance(url, str) or not url:
    return ''
  if url.startswith(_ALLOWED_URL_SCHEMES):
    return url
  return ''


# =========================================================================
# market_id allowlist gate
# =========================================================================

_MARKET_ID_RE = re.compile(r'^[A-Z0-9_]{2,16}$')


def _is_valid_market_id(market_id: str) -> bool:
  '''Return True iff market_id is in _VALID_MARKETS AND matches safe regex.

  Belt-and-braces: allowlist membership PLUS regex that excludes path
  separators, relative-path chars, dots, and spaces. Prevents path
  traversal even if _VALID_MARKETS is extended to contain a bad entry.
  '''
  if not isinstance(market_id, str):
    return False
  return market_id in _VALID_MARKETS and bool(_MARKET_ID_RE.fullmatch(market_id))


def _cache_path(market_id: str) -> Path:
  '''Return the sidecar cache path for the given market_id.

  Raises ValueError if market_id is not in the allowlist or contains
  traversal characters. Must be called BEFORE any Path construction.
  '''
  if not _is_valid_market_id(market_id):
    raise ValueError(f'invalid market_id: {market_id!r}')
  return Path(f'news_cache_{market_id}.json')


# =========================================================================
# Schema normalisation — post-0.2.55 (content envelope) schema
# =========================================================================

def _normalise_post_055(raw: dict) -> 'NewsItem | None':
  '''Normalise a post-0.2.55 yfinance news item (content envelope schema).

  Dispatch: called when 'content' key is present in raw.
  URL priority: clickThroughUrl → canonicalUrl → '' (both scheme-validated).
  Title is preserved VERBATIM (no html.escape at fetch layer).
  '''
  c = raw.get('content', {})
  title = c.get('title', '').strip()
  if not title:
    return None
  url_obj = c.get('clickThroughUrl') or c.get('canonicalUrl') or {}
  if isinstance(url_obj, dict):
    raw_url = url_obj.get('url', '')
  elif isinstance(url_obj, str):
    raw_url = url_obj
  else:
    raw_url = ''
  url = _validate_url_scheme(raw_url)
  publisher = c.get('provider', {}).get('displayName', '')
  pub_date = c.get('pubDate', '')
  title_hash = _compute_title_hash(title)
  return NewsItem(
    title=title,
    url=url,
    publisher=publisher,
    pub_date=pub_date,
    title_hash=title_hash,
  )


# =========================================================================
# Schema normalisation — pre-0.2.55 (flat uuid schema)
# =========================================================================

def _normalise_pre_055(raw: dict) -> 'NewsItem | None':
  '''Normalise a pre-0.2.55 yfinance news item (flat uuid schema).

  Dispatch: called when 'uuid' key is present in raw (and 'content' absent).
  pub_date derived from providerPublishTime (unix timestamp → ISO 8601 UTC).
  Title is preserved VERBATIM.
  '''
  title = raw.get('title', '').strip()
  if not title:
    return None
  url = _validate_url_scheme(raw.get('link', ''))
  publisher = raw.get('publisher', '')
  ts = raw.get('providerPublishTime', 0)
  pub_date = (
    datetime.fromtimestamp(ts, UTC).strftime('%Y-%m-%dT%H:%M:%SZ') if ts else ''
  )
  title_hash = _compute_title_hash(title)
  return NewsItem(
    title=title,
    url=url,
    publisher=publisher,
    pub_date=pub_date,
    title_hash=title_hash,
  )


# =========================================================================
# Dispatcher
# =========================================================================

def _normalise_item(raw: dict) -> 'NewsItem | None':
  '''Dispatch to post-0.2.55 or pre-0.2.55 normaliser based on schema shape.

  post-0.2.55: 'content' key present.
  pre-0.2.55: 'uuid' key present (and no 'content').
  Unknown shape: return None.
  '''
  if not isinstance(raw, dict):
    return None
  if 'content' in raw:
    return _normalise_post_055(raw)
  if 'uuid' in raw:
    return _normalise_pre_055(raw)
  return None


# =========================================================================
# Cache — load and write
# =========================================================================

def _load_cache(path: Path) -> 'list[NewsItem] | None':
  '''Load sidecar cache file and validate JSON-date-field TTL.

  The JSON envelope `date` field is the SOLE TTL authority. Filesystem
  mtime is NEVER consulted (T-38-03-09 — avoids timezone/restart drift).

  Returns the headlines list if the cache date matches today; None otherwise
  (caller must refetch). Also returns None on any parse/IO error.
  '''
  try:
    with open(path, encoding='utf-8') as f:
      envelope = json.load(f)
    if not isinstance(envelope, dict):
      return None
    if envelope.get('date') != date.today().isoformat():
      return None
    headlines = envelope.get('headlines')
    if not isinstance(headlines, list):
      return None
    return headlines
  except (FileNotFoundError, json.JSONDecodeError, OSError, KeyError, TypeError):
    return None


def _write_cache(path: Path, data: dict) -> None:
  '''Atomically write cache envelope to path.

  Pattern mirrors state_manager/io.py::_atomic_write_unlocked:
    tempfile in same directory → flush + fsync → close → os.replace
  Tempfile is cleaned up in finally if any step before os.replace raises.

  `data` must already be the full envelope dict:
    {'date': 'YYYY-MM-DD', 'headlines': [...]}
  '''
  parent = path.parent
  tmp_path_str = None
  try:
    with tempfile.NamedTemporaryFile(
      dir=parent, delete=False, mode='w', suffix='.tmp', encoding='utf-8',
    ) as tmp:
      tmp_path_str = tmp.name
      json.dump(data, tmp, ensure_ascii=False)
      tmp.flush()
      os.fsync(tmp.fileno())
    os.replace(tmp_path_str, path)
    tmp_path_str = None  # success: do not delete in finally
  finally:
    if tmp_path_str is not None:
      try:
        os.unlink(tmp_path_str)
      except FileNotFoundError:
        pass


# =========================================================================
# Public API
# =========================================================================

def fetch_news(
  market_id: str,
  symbol: str,
  max_items: int = 5,
  retries: int = 3,
  backoff_s: float = 5.0,
) -> NewsResult:
  '''Fetch top-N deduplicated news items for the given market symbol.

  Returns a NewsResult — NEVER a bare list (D-02 fail-closed gate).
  NEVER raises; all exceptions are converted to NewsResult(error=<typed_reason>).

  1. Validates market_id against allowlist (error='parse_error' on miss — no yfinance call).
  2. Checks sidecar cache (JSON date field TTL — one fetch per market per day).
  3. On cache miss: calls yfinance.Ticker(symbol).news, normalises both schema
     shapes, deduplicates by title_hash, writes cache atomically.
  4. Retries on transient network errors (ReadTimeout, ConnectionError).
  5. Returns NewsResult(items=[], error=<reason>, ...) after retries exhausted.

  No server-side HTTP calls to headline URLs (SSRF closed — T-38-03-02).

  Typed error reasons (T-43-05: no raw exception text surfaced to dashboard):
    "timeout"             — ReadTimeout after retries exhausted
    "http_error"          — Non-2xx HTTP response
    "parse_error"         — JSON / schema parse failure
    "network_unreachable" — ConnectionError after retries exhausted
  '''
  import requests.exceptions as _req_exc
  now = datetime.now(UTC)

  if not _is_valid_market_id(market_id):
    _LOGGER.warning('fetch_news rejected unknown market_id=%r', market_id)
    return NewsResult(items=[], error='parse_error', fetched_at=now)

  cache_path = _cache_path(market_id)
  cached = _load_cache(cache_path)
  if cached is not None:
    return NewsResult(items=cached[:max_items], error=None, fetched_at=now)

  # Cache miss — fetch from yfinance with retry loop
  last_exc: Exception | None = None
  last_error_reason: 'Literal["timeout","http_error","parse_error","network_unreachable"]' = 'parse_error'

  for attempt in range(retries):
    try:
      yf_mod = _get_yf()
      ticker = yf_mod.Ticker(symbol)
      raw_items = ticker.news or []

      # Normalise both schemas
      normalised: list[NewsItem] = []
      for r in raw_items:
        item = _normalise_item(r)
        if item is not None:
          normalised.append(item)

      # Dedup by title_hash (preserve first occurrence)
      seen: set[str] = set()
      deduped: list[NewsItem] = []
      for item in normalised:
        h = item['title_hash']
        if h not in seen:
          seen.add(h)
          deduped.append(item)

      items = deduped[:max_items]

      envelope = {'date': date.today().isoformat(), 'headlines': items}
      try:
        _write_cache(cache_path, envelope)
      except Exception as write_exc:
        _LOGGER.warning(
          'fetch_news cache write failed for market_id=%r: %s',
          market_id,
          write_exc,
        )

      return NewsResult(items=items, error=None, fetched_at=datetime.now(UTC))

    except _req_exc.ReadTimeout as exc:
      last_exc = exc
      last_error_reason = 'timeout'
      _LOGGER.warning(
        'fetch_news timeout (attempt %d/%d) market_id=%r: %s',
        attempt + 1,
        retries,
        market_id,
        exc,
      )
      if attempt < retries - 1:
        time.sleep(backoff_s)

    except _req_exc.ConnectionError as exc:
      last_exc = exc
      last_error_reason = 'network_unreachable'
      _LOGGER.warning(
        'fetch_news connection error (attempt %d/%d) market_id=%r: %s',
        attempt + 1,
        retries,
        market_id,
        exc,
      )
      if attempt < retries - 1:
        time.sleep(backoff_s)

    except Exception as exc:
      last_exc = exc
      last_error_reason = 'parse_error'
      _LOGGER.warning(
        'fetch_news unexpected error (attempt %d/%d) market_id=%r: %s',
        attempt + 1,
        retries,
        market_id,
        exc,
      )
      if attempt < retries - 1:
        time.sleep(backoff_s)

  _LOGGER.error(
    'fetch_news failed after %d retries for market_id=%r error=%r: %s',
    retries,
    market_id,
    last_error_reason,
    last_exc,
  )
  return NewsResult(items=[], error=last_error_reason, fetched_at=datetime.now(UTC))
