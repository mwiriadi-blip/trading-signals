# Phase 41: data feed integration - IG REST API - Pattern Map

**Mapped:** 2026-05-16
**Files analyzed:** 4
**Analogs found:** 4 / 4

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `data_fetcher.py` | service (I/O adapter) | request-response | `data_fetcher.py` (existing body) | exact — extend in place |
| `system_params.py` | config | CRUD | `system_params.py` `DEFAULT_MARKETS` dict (lines 314–337) | exact |
| `.env.example` | config | — | `.env.example` (existing env var blocks) | exact |
| `tests/test_data_fetcher.py` | test | request-response | `tests/test_data_fetcher.py` `TestFetch` class (lines 107–212) | exact |

---

## Pattern Assignments

### `data_fetcher.py` — IG branch additions

**Analog:** `data_fetcher.py` (current file, 239 LOC)

**Imports pattern** (lines 28–38):
```python
import logging
import time

import pandas as pd
import requests
import requests.exceptions

from system_params import HTTP_TIMEOUT_S, redact_secret  # noqa: F401
```
Add `import os` at the top alongside `import logging` — it is not currently imported.

**Lazy-import pattern for future SDK guard** (lines 70–83):
```python
_yf = None

def _get_yf():
  global _yf
  if _yf is None:
    import yfinance as yf_
    _yf = yf_
  return _yf
```
No new SDK — IG uses `requests` directly. This pattern is documented as the model if any future dep is needed (D-10 forbids `trading-ig` SDK).

**Retry loop pattern** (lines 200–238):
```python
for attempt in range(1, retries + 1):
  try:
    # ... call ...
  except (*retry_exceptions, ValueError) as e:
    last_err = e
    logger.warning(
      '[Fetch] %s attempt %d/%d failed: %s: %s',
      symbol, attempt, retries, type(e).__name__, e,
    )
    if attempt < retries:
      time.sleep(backoff_s)
raise DataFetchError(
  f'{symbol}: retries exhausted after {retries} attempts; '
  f'last error: {type(last_err).__name__}: {last_err}',
) from last_err
```
Replicate this loop structure inside `_fetch_via_ig()`. Only `requests.exceptions.ReadTimeout` and `requests.exceptions.ConnectionError` are retry-eligible for IG (narrow-catch — no bare `Exception`). A 403 from session creation is NOT retry-eligible; a 403 from the prices endpoint triggers one re-auth then one more price attempt before counting as a failed attempt.

**Column validation pattern** (lines 221–227):
```python
missing = _REQUIRED_COLUMNS - set(df.columns)
if missing:
  raise DataFetchError(
    f'{symbol}: missing required columns: {sorted(missing)} ...',
  )
return df[['Open', 'High', 'Low', 'Close', 'Volume']]
```
Apply after `_ig_normalise()` to guarantee contract to callers.

**Warning log pattern** (lines 231–235):
```python
logger.warning(
  '[Fetch] %s attempt %d/%d failed: %s: %s',
  symbol, attempt, retries, type(e).__name__, e,
)
```
For the credential-missing fallback (D-06):
```python
logger.warning('[Fetch] IG credentials not configured — falling back to yfinance')
```
For the retry-exhausted fallback (D-01/D-02):
```python
logger.warning('[Fetch] IG fetch failed for %s — falling back to yfinance', symbol)
```

**Secret redaction pattern** — already imported (`redact_secret` from `system_params`). Apply before any log line that interpolates `IG_API_KEY` or `IG_PASSWORD`:
```python
logger.warning('[Fetch] IG auth failed: key=%s', redact_secret(api_key))
```

**New private functions to add** (follow the `_get_yf` / `_get_yf_rate_limit_error` naming convention — underscore prefix, verb-noun):

```python
_IG_BASE_URLS = {
  'live': 'https://api.ig.com/gateway/deal',
  'demo': 'https://demo-api.ig.com/gateway/deal',
}

def _ig_base_url() -> str:
  account_type = os.environ.get('IG_ACCOUNT_TYPE', 'demo').lower()
  if account_type not in _IG_BASE_URLS:
    account_type = 'demo'  # SSRF guard — gate to known values only
  return _IG_BASE_URLS[account_type]

def _ig_create_session() -> dict:
  # POST /session with VERSION: 2
  # Returns dict of headers: {X-IG-API-KEY, CST, X-SECURITY-TOKEN, ...}

def _ig_fetch_ohlcv_raw(epic: str, num_points: int, session_headers: dict) -> list:
  # GET /prices/{epic}/D/{num_points} with VERSION: 1 (NOT 2 — Pitfall 1)
  # Returns data['prices'] list

def _ig_normalise(prices: list) -> pd.DataFrame:
  # mid = (bid + ask) / 2 for O/H/L/C; Volume = lastTradedVolume (0 OK)
  # Index: pd.to_datetime(snapshotTimeUTC, utc=True)

def _epic_for_symbol(symbol: str) -> str | None:
  # Read system_params.DEFAULT_MARKETS, find entry where ['symbol'] == symbol
  # Return entry['ig_epic'] or None

def _fetch_via_ig(epic: str, days: int, retries: int, backoff_s: float) -> pd.DataFrame | None:
  # Wraps session + fetch + normalise + retry loop
  # Returns DataFrame or None (caller falls back to yfinance)
```

**fetch_ohlcv credential gate** — insert before existing yfinance path (pattern mirrors the env-var check from `system_params._resolve_email_to_or_skip` referenced in CONTEXT.md):
```python
def fetch_ohlcv(symbol, days=400, retries=3, backoff_s=10.0):
  ig_key = os.environ.get('IG_API_KEY', '')
  if ig_key:
    ig_epic = _epic_for_symbol(symbol)
    if ig_epic:
      df = _fetch_via_ig(ig_epic, days, retries, backoff_s)
      if df is not None:
        return df
      logger.warning('[Fetch] IG fetch failed for %s — falling back to yfinance', symbol)
  else:
    logger.warning('[Fetch] IG credentials not configured — falling back to yfinance')
  # existing yfinance retry loop below — UNCHANGED
  ...
```

---

### `system_params.py` — `DEFAULT_MARKETS` extension

**Analog:** `system_params.py` lines 314–337

**Current dict pattern:**
```python
DEFAULT_MARKETS: dict[str, dict] = {
  'SPI200': {
    'display_name': 'SPI 200',
    'symbol': '^AXJO',
    'currency': 'AUD',
    'multiplier': SPI_MULT,
    'cost_aud': SPI_COST_AUD,
    'enabled': True,
    'sort_order': 10,
    'contract_type': 'mini',
    'financing_rate_annual_pct': 0.0,
  },
  'AUDUSD': {
    'display_name': 'AUD / USD',
    'symbol': 'AUDUSD=X',
    ...
  },
}
```

**Addition pattern** — append `ig_epic` key to each market entry (D-11):
```python
'SPI200': {
  ...existing keys...,
  'ig_epic': 'IX.D.ASX.IFM.IP',   # ASSUMED — operator must verify via GET /markets?searchTerm=Australia+200
},
'AUDUSD': {
  ...existing keys...,
  'ig_epic': 'CS.D.AUDUSD.MINI.IP',  # ASSUMED — operator must verify
},
```

Add after existing Phase 38 constants block, with a phase header comment matching the file's convention:
```python
# =========================================================================
# Phase 41 constants — IG REST API base URLs
# =========================================================================
# Consumed only by data_fetcher.py _ig_base_url(). Centralised here so
# any URL change is a single-source edit. hex-boundary safe: stdlib-only.
```
Note: `_IG_BASE_URLS` dict may live in `data_fetcher.py` directly (no import needed from system_params) since `system_params` must stay stdlib-only (no `requests` or network imports). Only `ig_epic` string constants go in `system_params`.

---

### `.env.example` — IG credential block

**Analog:** existing env var blocks in `.env.example`

**Pattern to copy** (follow the grouped block style with a phase comment header):
```bash
# Phase 41: IG REST API credentials (primary data source; yfinance is silent fallback)
# Obtain from My IG Account -> API credentials (requires live or demo account)
# IG_ACCOUNT_TYPE: 'demo' (default) or 'live'
IG_API_KEY=
IG_USERNAME=
IG_PASSWORD=
IG_ACCOUNT_TYPE=demo
```

---

### `tests/test_data_fetcher.py` — `TestIGFetch` + `TestIGNormalise` classes

**Analog:** `tests/test_data_fetcher.py` `TestFetch` class (lines 107–212)

**Monkeypatch pattern** (lines 121–123, 149–150):
```python
monkeypatch.setattr(
  'data_fetcher.requests.post',   # patch target for IG session POST
  fake_post,
)
monkeypatch.setattr(
  'data_fetcher.requests.get',    # patch target for IG prices GET
  fake_get,
)
monkeypatch.setattr('data_fetcher.time.sleep', lambda *_a, **_k: None)
```
Patch `data_fetcher.requests.post` / `.get` (NOT `requests.post` globally) — same import-site patch discipline as `data_fetcher.yf.Ticker`.

**Fixture loader pattern** (lines 45–54):
```python
FETCH_FIXTURE_DIR = Path(__file__).parent / 'fixtures' / 'fetch'

def _load_recorded_fixture(name: str) -> pd.DataFrame:
  path = FETCH_FIXTURE_DIR / name
  df = pd.read_json(path, orient='split')
  return df
```
IG fixtures are JSON (not pd.DataFrame orient='split') — use `json.loads` or `json.load` for raw IG response fixture files. Create:
- `tests/fixtures/fetch/ig_spi200_prices.json` — hand-crafted from RESEARCH.md §Code Examples JSON shape
- `tests/fixtures/fetch/ig_audusd_prices.json` — same

**FakeTicker model → FakeResponse model** (lines 63–100):
```python
class _FakeTicker:
  def __init__(self, symbol, behaviour, call_count):
    ...
  def history(self, **kwargs):
    self._call_count.append(1)
    ...
```
Adapt to a `FakeResponse` that mimics `requests.Response`:
```python
class _FakeResponse:
  def __init__(self, json_data=None, headers=None, status_code=200):
    self._json = json_data or {}
    self.headers = headers or {}
    self.status_code = status_code
  def raise_for_status(self):
    if self.status_code >= 400:
      raise requests.exceptions.HTTPError(response=self)
  def json(self):
    return self._json
```

**Test class structure** (mirror `TestFetch` / `TestColumnShape` naming):
```python
class TestIGFetch:
  '''DATA-01/02/03 + D-01/D-02/D-06: IG happy path, retry, fallback.'''

  def test_ig_happy_path_spi200(self, monkeypatch): ...
  def test_ig_happy_path_audusd(self, monkeypatch): ...
  def test_ig_retry_on_timeout(self, monkeypatch): ...
  def test_ig_fallback_to_yfinance(self, monkeypatch): ...
  def test_fallback_emits_warning(self, monkeypatch, caplog): ...
  def test_missing_credentials_uses_yfinance(self, monkeypatch): ...

class TestIGNormalise:
  '''D-12 / Pitfall 2 / Pitfall 3: mid-price math, Volume=0, UTC DatetimeIndex.'''

  def test_mid_price_calculation(self): ...
  def test_volume_zero_accepted(self): ...
  def test_index_is_utc_datetimeindex(self): ...
```

**env-var injection for tests** (D-06 tests need `IG_API_KEY` unset or set):
```python
monkeypatch.delenv('IG_API_KEY', raising=False)   # test missing-creds path
monkeypatch.setenv('IG_API_KEY', 'test-key-123')  # test IG active path
monkeypatch.setenv('IG_USERNAME', 'testuser')
monkeypatch.setenv('IG_PASSWORD', 'testpass')
monkeypatch.setenv('IG_ACCOUNT_TYPE', 'demo')
```

**Warning assertion pattern** (use `caplog` fixture, mirroring project conventions):
```python
def test_fallback_emits_warning(self, monkeypatch, caplog):
  ...
  with caplog.at_level(logging.WARNING, logger='data_fetcher'):
    fetch_ohlcv('^AXJO', days=400, retries=3, backoff_s=0.0)
  assert any('falling back to yfinance' in r.message for r in caplog.records)
```

---

## Shared Patterns

### Secret Redaction
**Source:** `system_params.redact_secret` (lines 65–77)
**Apply to:** Any `logger.*` call in `data_fetcher.py` that interpolates `IG_API_KEY` or `IG_PASSWORD`
```python
from system_params import HTTP_TIMEOUT_S, redact_secret
# ...
logger.warning('[Fetch] IG auth error: key=%s', redact_secret(os.environ.get('IG_API_KEY', '')))
```

### Error Typing
**Source:** `data_fetcher.py` lines 151–164
**Apply to:** All IG failure paths
```python
class DataFetchError(Exception):
  '''Raised when a symbol's fetch fails after all retries exhaust.'''
```
IG failures that exhaust retries must raise `DataFetchError` — same as yfinance path. Callers in `daily_run.py` catch `DataFetchError` → `rc=2`. Do NOT introduce a new `IGFetchError` subclass.

### HTTP Timeout
**Source:** `system_params.HTTP_TIMEOUT_S` (line 44) = `30`
**Apply to:** All `requests.post` and `requests.get` calls in the IG branch
```python
resp = requests.post(url, ..., timeout=HTTP_TIMEOUT_S)
resp = requests.get(url, ..., timeout=HTTP_TIMEOUT_S)
```

### append_warning call signature
**Source:** `state_manager/trades.py` line 40
```python
def append_warning(state: dict, source: str, message: str, now=None) -> dict:
```
Per Decision A3 (Option A): `fetch_ohlcv` does NOT call `append_warning` — it logs only. `daily_run.py` detects the fallback and calls `append_warning` there (no signature change to `fetch_ohlcv`).

### Narrow-catch discipline
**Source:** `data_fetcher.py` lines 128–141, module docstring lines 13–16
**Apply to:** IG retry loop — only retry on:
- `requests.exceptions.ReadTimeout`
- `requests.exceptions.ConnectionError`

Never catch bare `Exception`. A 403 from `_ig_create_session` is non-transient (bad credentials) — fall through to yfinance immediately, do not retry. A 403 from the prices endpoint triggers one re-auth attempt; if the re-auth-then-fetch also 403s, fall through.

### LOC cap
**Source:** `CLAUDE.md` §Rules — "Keep files under 500 lines"
**Apply to:** `data_fetcher.py` — currently 239 LOC; IG addition must stay ≤ ~100 net LOC. Final file ≤ 339 LOC (well under 500). Planner to include a LOC verification step.

---

## No Analog Found

All files have close analogs in the codebase.

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| — | — | — | — |

---

## Metadata

**Analog search scope:** `data_fetcher.py`, `system_params.py`, `tests/test_data_fetcher.py`, `state_manager/trades.py`
**Files scanned:** 4 source files + CONTEXT.md + RESEARCH.md
**Pattern extraction date:** 2026-05-16
