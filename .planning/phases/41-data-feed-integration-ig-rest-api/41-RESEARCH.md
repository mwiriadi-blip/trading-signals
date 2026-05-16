# Phase 41: data feed integration - IG REST API - Research

**Researched:** 2026-05-16
**Domain:** IG REST API v2 — session auth + historical OHLCV ingestion
**Confidence:** MEDIUM (auth/endpoint shape VERIFIED via source inspection; epic codes ASSUMED; volume=0 MEDIUM; rate limits MEDIUM)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** IG is the primary data source; yfinance is the silent fallback. IG fetch fails → retry 3x → fall back to yfinance.
- **D-02:** When fallback is used: WARNING log + `state_manager.append_warning()` dashboard warning.
- **D-03:** Data source is NOT persisted in state.json — log only.
- **D-04:** Credentials via env vars: `IG_API_KEY`, `IG_USERNAME`, `IG_PASSWORD`, `IG_ACCOUNT_TYPE` (`demo`|`live`).
- **D-05:** IG session tokens in-memory only — no persistence. Re-auth on every run.
- **D-06:** Missing `IG_API_KEY` → emit WARNING log, proceed via yfinance. Never RuntimeError.
- **D-07:** Historical EOD OHLCV only — 300 bars, `system_params.HISTORY_BARS` window. No streaming.
- **D-08:** History window uses existing `system_params.HISTORY_BARS` (300). No new config param.
- **D-09:** Default env is IG demo. Live via `IG_ACCOUNT_TYPE=live`.
- **D-10:** IG fetch lives inside `data_fetcher.py` as a new branch — no separate module.
- **D-11:** IG EPIC codes stored in `system_params.DEFAULT_MARKETS` dict as `ig_epic` field per market.
- **D-12:** Bid/ask candles → mid price `(bid + ask) / 2` for all OHLCV fields.

### Claude's Discretion
- Exact IG REST endpoint(s) for historical daily candles
- IG session creation endpoint and request body shape
- Whether IG retry policy mirrors `_retry_with_backoff` or needs session-refresh retry
- Volume field handling (IG may return 0 for spread-bet instruments)

### Deferred Ideas (OUT OF SCOPE)
- Live spot price for dashboard P&L
- Intraday candles / live streaming
- Roadmap numbering conflict resolution
</user_constraints>

---

## Summary

IG provides a versioned REST API at `https://api.ig.com/gateway/deal` (live) and `https://demo-api.ig.com/gateway/deal` (demo). Session creation via `POST /session` returns two short-lived tokens (`CST` and `X-SECURITY-TOKEN`) in response headers; these must be passed on every subsequent request. Historical OHLCV data is fetched from `GET /prices/{epic}/{resolution}/{numPoints}` — path parameters, not query string. The endpoint returns a JSON array where each candle has nested bid/ask objects (`openPrice`, `highPrice`, `lowPrice`, `closePrice`) and a `lastTradedVolume` field. For spread-bet instruments (which SPI200 and AUD/USD are on IG), `lastTradedVolume` is consistently reported as `0` — this is a known API characteristic, not an error. The planner should wire `Volume = 0` for both markets (consistent with how yfinance handles FX volume).

The critical implementation constraint: the `data_fetcher.py` IG branch must preserve the existing function signature `fetch_ohlcv(symbol, days, retries, backoff_s) -> pd.DataFrame` with `[Open, High, Low, Close, Volume]` columns and a `DatetimeIndex`. The current file is 239 LOC; adding the IG branch + credential check must stay under 500 LOC (CLAUDE.md hard cap).

**Primary recommendation:** Implement IG auth + fetch as two private functions `_ig_create_session()` and `_ig_fetch_ohlcv_raw()` called from a new `_fetch_via_ig()` branch inside `fetch_ohlcv`. Re-use the existing `_retry_with_backoff`-equivalent loop structure (the current loop is inline, not a named helper — replicate the same 3-attempt / 10s-backoff pattern). Add a one-shot re-auth on 403/session-expired before counting as a retry failure.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| IG session auth | I/O adapter (`data_fetcher.py`) | — | Session is per-fetch-run; no persistence; lives at the network boundary |
| OHLCV normalisation (bid+ask → mid) | I/O adapter (`data_fetcher.py`) | — | Normalisation is part of the data contract at the hex boundary |
| EPIC code constants | `system_params.py` | — | Single source of truth for all market config (D-11) |
| Credential presence check | I/O adapter (`data_fetcher.py`) | — | Checked at fetch time, not at import time; consistent with D-06 |
| Fallback dashboard warning | `state_manager.append_warning()` | — | Called from `data_fetcher.py` — same pattern as other I/O-layer warnings |
| yfinance fallback fetch | I/O adapter (`data_fetcher.py`) | — | Existing path; unchanged |

---

## Standard Stack

### Core (no new dependencies)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `requests` | already installed | IG REST HTTP calls | Already in data_fetcher.py; no new dep |
| `pandas` | already installed | DataFrame normalisation | Already used for yfinance path |
| `system_params` | project module | `HTTP_TIMEOUT_S`, `HISTORY_BARS` constants | Single source of truth per CLAUDE.md |

No new `pip install` required. The IG branch uses only `requests` (already imported at data_fetcher module level) and stdlib (`os`, `logging`, `time`).

**Version verification:** `requests` and `pandas` already in project venv. `os` is stdlib. [VERIFIED: data_fetcher.py line imports]

---

## Architecture Patterns

### System Architecture Diagram

```
daily_run.py
  └─ fetch_ohlcv(symbol, days=400)           ← unchanged signature
        │
        ├─ [IG_API_KEY set?]
        │     YES → _fetch_via_ig(epic, days)
        │               ├─ _ig_create_session()   POST /session
        │               │     → {cst, x_security_token}
        │               └─ _ig_fetch_ohlcv_raw(epic, numPoints, session_headers)
        │                     GET /prices/{epic}/D/{numPoints}
        │                     → prices[] JSON
        │                     → _ig_normalise(prices[]) → pd.DataFrame
        │                         (snapshotTimeUTC → DatetimeIndex)
        │                         (mid=(bid+ask)/2 for O/H/L/C)
        │                         (lastTradedVolume → Volume, 0 for spread bets)
        │         success → return df
        │         failure (3 retries) → fall through to yfinance
        │
        └─ [IG missing or all retries failed]
              → WARNING log + append_warning(state, ...)
              → _fetch_via_yfinance(symbol, days)   ← existing path
```

### Recommended File Structure (changes only)

```
data_fetcher.py        # +~80 LOC: _ig_create_session, _ig_fetch_ohlcv_raw,
                       #           _ig_normalise, _fetch_via_ig branch
                       # Final LOC: ~319 (well under 500 cap)
system_params.py       # +2 fields: ig_epic in DEFAULT_MARKETS for SPI200 + AUDUSD
.env.example           # +4 lines: IG_API_KEY, IG_USERNAME, IG_PASSWORD, IG_ACCOUNT_TYPE
tests/test_data_fetcher.py  # +~60 LOC: TestIGFetch class (session mock, price mock,
                             #           fallback trigger, volume=0, mid-price math)
```

### Pattern 1: IG Session Creation

**What:** One-shot `POST /session` at the start of each fetch. Returns two response headers that must be forwarded on price requests.

**When to use:** Called once per `_fetch_via_ig()` invocation. Tokens are in-memory only (D-05).

```python
# Source: [VERIFIED: trading-ig rest.py source inspection + IG Labs guide]
import os
import requests

_IG_BASE_URLS = {
  'live': 'https://api.ig.com/gateway/deal',
  'demo': 'https://demo-api.ig.com/gateway/deal',
}

def _ig_create_session() -> dict:
  '''Returns session headers dict: {X-IG-API-KEY, CST, X-SECURITY-TOKEN}.
  Raises requests.exceptions.HTTPError on auth failure.
  '''
  account_type = os.environ.get('IG_ACCOUNT_TYPE', 'demo').lower()
  base_url = _IG_BASE_URLS.get(account_type, _IG_BASE_URLS['demo'])
  api_key = os.environ['IG_API_KEY']  # caller validates presence before this
  resp = requests.post(
    f'{base_url}/session',
    json={
      'identifier': os.environ['IG_USERNAME'],
      'password': os.environ['IG_PASSWORD'],
      'encryptedPassword': False,
    },
    headers={
      'X-IG-API-KEY': api_key,
      'Content-Type': 'application/json',
      'Accept': 'application/json; charset=UTF-8',
      'VERSION': '2',
    },
    timeout=HTTP_TIMEOUT_S,
  )
  resp.raise_for_status()
  return {
    'X-IG-API-KEY': api_key,
    'CST': resp.headers['CST'],
    'X-SECURITY-TOKEN': resp.headers['X-SECURITY-TOKEN'],
    'Content-Type': 'application/json',
    'Accept': 'application/json; charset=UTF-8',
  }
```

### Pattern 2: Historical Price Fetch

**What:** `GET /prices/{epic}/{resolution}/{numPoints}` — path parameters, not query string.

**When to use:** After session creation. Resolution `D` for daily candles.

```python
# Source: [VERIFIED: trading-ig rest.py source inspection]
def _ig_fetch_ohlcv_raw(epic: str, num_points: int, session_headers: dict) -> list:
  '''Returns raw prices list from IG response. Raises on HTTP error.'''
  account_type = os.environ.get('IG_ACCOUNT_TYPE', 'demo').lower()
  base_url = _IG_BASE_URLS.get(account_type, _IG_BASE_URLS['demo'])
  resp = requests.get(
    f'{base_url}/prices/{epic}/D/{num_points}',
    headers={**session_headers, 'VERSION': '1'},
    timeout=HTTP_TIMEOUT_S,
  )
  resp.raise_for_status()
  data = resp.json()
  return data['prices']  # list of candle dicts
```

### Pattern 3: Normalise to DataFrame

**What:** Convert IG's nested bid/ask candle format to the project's standard `[Open, High, Low, Close, Volume]` DataFrame with DatetimeIndex.

**When to use:** Always after `_ig_fetch_ohlcv_raw`.

```python
# Source: [VERIFIED: IG response JSON shape confirmed via multiple sources]
import pandas as pd

def _ig_normalise(prices: list) -> pd.DataFrame:
  '''Convert IG prices array to standard OHLCV DataFrame.
  Mid price = (bid + ask) / 2 per D-12.
  Volume = lastTradedVolume (0 for spread bets — expected, not an error).
  '''
  rows = []
  for p in prices:
    def mid(field):
      return (p[field]['bid'] + p[field]['ask']) / 2
    rows.append({
      'Open':   mid('openPrice'),
      'High':   mid('highPrice'),
      'Low':    mid('lowPrice'),
      'Close':  mid('closePrice'),
      'Volume': p.get('lastTradedVolume', 0),
      '_ts':    p['snapshotTimeUTC'],
    })
  df = pd.DataFrame(rows)
  df.index = pd.to_datetime(df.pop('_ts'), utc=True)
  return df[['Open', 'High', 'Low', 'Close', 'Volume']]
```

### Pattern 4: Credential Gate + Fallback Branch

**What:** D-06 eager validation; D-01 retry-then-fallback structure.

```python
# Source: [ASSUMED] — pattern mirrors existing _resolve_email_to_or_skip
def fetch_ohlcv(symbol, days=400, retries=3, backoff_s=10.0):
  ig_key = os.environ.get('IG_API_KEY', '')
  if ig_key:
    ig_epic = _epic_for_symbol(symbol)
    if ig_epic:
      df, used_ig = _fetch_via_ig(ig_epic, days, retries, backoff_s)
      if df is not None:
        return df
      # IG exhausted — fall through to yfinance
      logger.warning('[Fetch] IG fetch failed for %s — falling back to yfinance', symbol)
      # D-02: dashboard warning (state not available here; caller must pass state
      # OR fetch_ohlcv emits log only and daily_run.py calls append_warning after)
  else:
    logger.warning('[Fetch] IG credentials not configured — falling back to yfinance')
  # existing yfinance path unchanged
  ...
```

**Note on D-02 (dashboard warning):** `fetch_ohlcv` has no `state` parameter. Two implementation options for the planner to decide:
- **Option A (simplest):** `fetch_ohlcv` logs only; `daily_run.py` checks which source was used via a boolean return value or exception flag and calls `append_warning` there.
- **Option B:** Add an optional `state` kwarg to `fetch_ohlcv` and call `append_warning` directly. Slightly cleaner but changes the function signature.

**Most eloquent:** Option A — preserves the existing zero-state-side-effect contract of `fetch_ohlcv`, no signature change, locality of state mutations stays in `daily_run.py`. [ASSUMED]

### Anti-Patterns to Avoid

- **Persisting tokens to disk:** D-05 is absolute — no token file, no env-var caching between runs.
- **Catching bare `Exception` on auth failure:** IG auth 403 is not transient — should NOT be retried like network timeouts. Only `requests.exceptions.ReadTimeout` and `ConnectionError` are retry-eligible on the price fetch. A 403 on session creation means bad credentials and should fall through to yfinance immediately (not waste retries).
- **Using the SDK library `trading-ig`:** D-10 says no new SDK dependencies — use `requests` directly.
- **Path parameter vs query string confusion:** IG historical prices uses PATH params (`/prices/{epic}/D/300`), not query string (`?resolution=D&max=300`). The query-string variant is a different endpoint.
- **Mutating the existing retry loop:** Do not refactor the yfinance retry loop. Add the IG branch before it, with its own retry logic. Keeps the diff reviewable and reversal clean.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP session tokens | Custom token manager | Standard dict headers passed per-request | IG v2 tokens are stateless per-request; no SDK needed |
| Mid-price calculation | Custom bid/ask library | Plain `(bid + ask) / 2` float arithmetic | Simple, no rounding required (signal engine uses float64) |
| Rate limit back-off | Custom bucket tracker | Reuse existing backoff loop (10s, 3 attempts) | Allowance is weekly (10,000 pts), not per-minute for daily data |

---

## Runtime State Inventory

Not applicable. This phase adds a new I/O path — it is not a rename/refactor/migration phase. No stored state references `IG_API_KEY` or IG epic codes today.

**Step 2.6 (Environment Availability):** Checked below.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `requests` (Python) | IG HTTP calls | Already in venv | project dep | — |
| `pandas` | DataFrame normalisation | Already in venv | project dep | — |
| IG demo API (`demo-api.ig.com`) | Integration tests | ✗ (no live calls in CI) | — | Monkeypatched in tests |
| IG credentials (`IG_API_KEY`) | Production runs | Operator-supplied | — | yfinance fallback |

**Missing dependencies with no fallback:** None — all code paths work without IG credentials (yfinance fallback).

**Missing dependencies with fallback:** IG credentials absent → yfinance used; D-06 confirmed.

---

## Common Pitfalls

### Pitfall 1: VERSION header mismatch between session and prices endpoints
**What goes wrong:** Session is created with `VERSION: 2`; the prices endpoint requires `VERSION: 1`. Using VERSION 2 on the prices endpoint returns a 400 or a different JSON shape.
**Why it happens:** IG has separately versioned endpoints; the version header is per-endpoint, not global.
**How to avoid:** Set `VERSION: 2` only for `POST /session`. Set `VERSION: 1` for `GET /prices/{epic}/D/{numPoints}`.
**Warning signs:** HTTP 400 on the prices call even though session creation succeeded.

### Pitfall 2: lastTradedVolume = 0 treated as an error
**What goes wrong:** Code raises `DataFetchError` or substitutes NaN thinking volume is missing.
**Why it happens:** IG spread-bet instruments (SPI200, AUDUSD) do not report exchange volume — `lastTradedVolume` is always 0. This is expected API behaviour, not a data defect.
**How to avoid:** Accept 0 as a valid Volume value. The existing yfinance path also returns 0 for FX (AUDUSD=X has no exchange volume). `_REQUIRED_COLUMNS` validation still passes — Volume column is present, just zero.
**Warning signs:** Test fixtures for IG path should assert `Volume == 0`, not `Volume > 0`.

### Pitfall 3: snapshotTime vs snapshotTimeUTC
**What goes wrong:** Using `snapshotTime` (exchange local, format `YYYY/MM/DD HH:MM:SS`) instead of `snapshotTimeUTC` (ISO 8601 UTC) for the DatetimeIndex.
**Why it happens:** Both fields exist in the response; `snapshotTime` looks more readable.
**How to avoid:** Always use `snapshotTimeUTC` and parse with `pd.to_datetime(..., utc=True)`. This gives a UTC-aware DatetimeIndex consistent with what signal_engine expects.
**Warning signs:** DatetimeIndex timezone is `None` instead of `UTC` after normalisation.

### Pitfall 4: session re-auth on 403 mid-fetch
**What goes wrong:** The IG session token expires during a multi-market run (tokens last 6h, typically fine for a daily run, but demo tokens may be shorter). Price fetch returns 403. Code retries the price fetch with the stale token — all 3 retries fail.
**Why it happens:** Retry loop retries the price fetch only, not the session creation.
**How to avoid:** On 403 from the prices endpoint (not from session creation), attempt one re-auth before counting the attempt as a failure. Structure: `try price fetch → on 403 → re-auth once → retry price fetch → if still 403 → count as exhausted attempt`.
**Warning signs:** All 3 retries fail with 403 on the price endpoint.

### Pitfall 5: Epic lookup for yfinance symbol
**What goes wrong:** `fetch_ohlcv` receives the yfinance symbol (`^AXJO`, `AUDUSD=X`) as `symbol`. IG needs the epic (`IX.D.ASX.IFM.IP`). The lookup must be clean — if no epic mapping exists, fall through to yfinance gracefully.
**Why it happens:** The call site in `daily_run.py` passes the yfinance symbol; the function signature must not change.
**How to avoid:** Add an internal `_epic_for_symbol(symbol: str) -> str | None` helper that reads `system_params.DEFAULT_MARKETS` and finds the market whose `symbol` field matches, returning its `ig_epic`. If not found, return `None` and skip IG fetch. [ASSUMED implementation approach]

### Pitfall 6: data_fetcher.py 500 LOC cap
**What goes wrong:** Adding IG branch without counting lines causes a CLAUDE.md violation.
**Why it happens:** data_fetcher.py is currently 239 LOC.
**How to avoid:** Keep the IG addition to ~80–100 LOC net. The planner should include a LOC verification step.
**Warning signs:** Final file > 500 LOC.

---

## Code Examples

### IG Response JSON Shape (prices array element)
```json
{
  "snapshotTime": "2024/05/15 00:00:00",
  "snapshotTimeUTC": "2024-05-14T14:00:00",
  "openPrice":  {"bid": 7845.2, "ask": 7847.5, "lastTraded": null},
  "highPrice":  {"bid": 7890.1, "ask": 7892.4, "lastTraded": null},
  "lowPrice":   {"bid": 7820.0, "ask": 7822.3, "lastTraded": null},
  "closePrice": {"bid": 7878.9, "ask": 7881.2, "lastTraded": null},
  "lastTradedVolume": 0
}
```
Source: [VERIFIED via WebSearch cross-referencing multiple IG API community posts and trading-ig source code inspection]

### Append-warning call signature (state_manager)
```python
# Source: [VERIFIED: state_manager/trades.py line 40]
# Signature: append_warning(state: dict, source: str, message: str, now=None) -> dict
state = append_warning(
  state,
  source='data_fetcher',
  message='IG fetch failed — yfinance fallback used for SPI200',
)
```

### .env.example additions
```bash
# Phase 41: IG REST API credentials (primary data source; yfinance is silent fallback)
# Obtain from My IG Account → API credentials (requires live or demo account)
# IG_ACCOUNT_TYPE: 'demo' (default) or 'live'
IG_API_KEY=
IG_USERNAME=
IG_PASSWORD=
IG_ACCOUNT_TYPE=demo
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| IG v1 session (single token) | IG v2 session (CST + X-SECURITY-TOKEN pair) | IG API v2 | Must use VERSION: 2 header on POST /session |
| IG v3 OAuth session | Not used — tokens expire in 60s, requires refresh loop | Still available | Too complex for a re-auth-once-per-run pattern; v2 is correct |

**Deprecated/outdated:**
- IG v3 sessions: OAuth access token valid only 60 seconds; overkill for daily EOD fetch. Stick with v2.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | SPI200 epic is `IX.D.ASX.IFM.IP` | Standard Stack / system_params | Wrong epic → 404 on price fetch; operator must supply correct code |
| A2 | AUDUSD epic is `CS.D.AUDUSD.MINI.IP` | Standard Stack / system_params | Wrong epic → 404; fallback to yfinance until corrected |
| A3 | Option A (log-only in fetch_ohlcv, append_warning in daily_run) is the right D-02 implementation | Architecture Patterns | If wrong, would need D-02 approach change — low impact, easy to revise at plan time |
| A4 | `snapshotTimeUTC` field is present in all IG responses for daily resolution | Code Examples | If field absent, DatetimeIndex construction fails; fallback to parsing `snapshotTime` |
| A5 | Prices endpoint VERSION header should be `1` | Pitfall 1 | If wrong, HTTP 400 or malformed response on price fetch |
| A6 | 403 on prices endpoint signals session expiry (re-auth) | Pitfall 4 | If 403 means bad credentials (not expiry), re-auth loop would be futile — detect by re-auth failure and fall through |

**Items needing operator confirmation before execution:**
- A1 and A2 (EPIC codes): operator should verify by logging into IG demo and searching for markets via the REST API Companion or `GET /markets?searchTerm=Australia+200`. Can be done in Wave 0 of the plan.

---

## Open Questions

1. **Exact EPIC codes for SPI200 and AUDUSD**
   - What we know: `IX.D.ASX.IFM.IP` for SPI200 and `CS.D.AUDUSD.MINI.IP` for AUDUSD are cited in multiple IG API community examples [MEDIUM confidence]
   - What's unclear: Whether these epics are the correct IG AU offering (cash vs futures, mini vs standard)
   - Recommendation: Wave 0 task — operator runs `GET /markets?searchTerm=Australia+200` against demo API and confirms the epic before coding; add confirmed value to `system_params.DEFAULT_MARKETS`

2. **D-02: where does append_warning get called?**
   - What we know: `fetch_ohlcv` has no `state` parameter; `daily_run.py` calls `fetch_ohlcv` and has access to `state`
   - What's unclear: Whether the planner prefers adding `state` to the signature or handling it in `daily_run.py`
   - Recommendation: Use Option A (log-only in fetch_ohlcv, daily_run.py calls append_warning). No signature change.

3. **snapshotTimeUTC field presence**
   - What we know: Multiple sources show `snapshotTimeUTC` in the response [MEDIUM confidence]
   - What's unclear: Whether it's always present for all resolution types and account types
   - Recommendation: Normalisation should defensively fall back to parsing `snapshotTime` if `snapshotTimeUTC` is absent

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (existing) |
| Config file | `pyproject.toml` |
| Quick run | `.venv/bin/pytest tests/test_data_fetcher.py -x --tb=short` |
| Full suite | `.venv/bin/pytest -x --tb=short` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DATA-01 | IG happy path returns correct DataFrame shape | unit | `pytest tests/test_data_fetcher.py::TestIGFetch::test_ig_happy_path_spi200` | ❌ Wave 0 |
| DATA-02 | IG happy path AUDUSD returns correct shape | unit | `pytest tests/test_data_fetcher.py::TestIGFetch::test_ig_happy_path_audusd` | ❌ Wave 0 |
| DATA-03 | IG retries on network error then succeeds | unit | `pytest tests/test_data_fetcher.py::TestIGFetch::test_ig_retry_on_timeout` | ❌ Wave 0 |
| D-01 | IG exhausted → yfinance fallback triggered | unit | `pytest tests/test_data_fetcher.py::TestIGFetch::test_ig_fallback_to_yfinance` | ❌ Wave 0 |
| D-02 | WARNING log emitted on fallback | unit | `pytest tests/test_data_fetcher.py::TestIGFetch::test_fallback_emits_warning` | ❌ Wave 0 |
| D-06 | Missing IG_API_KEY → WARNING, yfinance used | unit | `pytest tests/test_data_fetcher.py::TestIGFetch::test_missing_credentials_uses_yfinance` | ❌ Wave 0 |
| D-12 | Mid price = (bid+ask)/2 applied to all OHLCV | unit | `pytest tests/test_data_fetcher.py::TestIGNormalise::test_mid_price_calculation` | ❌ Wave 0 |
| Pitfall 2 | Volume=0 accepted as valid, no DataFetchError | unit | `pytest tests/test_data_fetcher.py::TestIGNormalise::test_volume_zero_accepted` | ❌ Wave 0 |

### Wave 0 Gaps
- [ ] `tests/test_data_fetcher.py::TestIGFetch` class — new class alongside existing `TestFetch`
- [ ] `tests/test_data_fetcher.py::TestIGNormalise` class — normalisation unit tests
- [ ] Fixture: `tests/fixtures/fetch/ig_spi200_prices.json` — recorded IG response fixture (can be hand-crafted from the documented shape)
- [ ] Fixture: `tests/fixtures/fetch/ig_audusd_prices.json` — same

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Env-var credential injection; `redact_secret()` before any log line |
| V3 Session Management | yes | In-memory tokens only (D-05); no persistence; 6h TTL acceptable |
| V4 Access Control | no | No new routes or endpoints |
| V5 Input Validation | yes | `IG_ACCOUNT_TYPE` sanitised to `lower()`, gated to known values |
| V6 Cryptography | no | No new crypto; passwords passed plaintext to IG (HTTPS transport) |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| API key in log lines | Information Disclosure | `redact_secret(api_key)` before any `logger.*` interpolation (T-27-03-01 pattern already in codebase) |
| Password in log lines | Information Disclosure | `redact_secret(password)` — same |
| SSRF via user-controlled base URL | Tampering | `IG_ACCOUNT_TYPE` gated to `{'demo', 'live'}` only; unknown values fall back to demo |
| Token reuse across processes | Elevation of Privilege | In-memory only per D-05; not a risk |

---

## Sources

### Primary (HIGH confidence)
- trading-ig `rest.py` (raw GitHub) — session creation body, header names (`X-IG-API-KEY`, `CST`, `X-SECURITY-TOKEN`), base URLs, prices URL path format `/prices/{epic}/{resolution}/{numPoints}`
- [IG REST API guide](https://labs.ig.com/rest-trading-api-guide.html) — v2 session token lifetime (6h, extendable to 72h), VERSION header semantics
- `data_fetcher.py` (current codebase) — existing retry loop structure, `_REQUIRED_COLUMNS`, `DataFetchError` hierarchy, `HTTP_TIMEOUT_S` usage [VERIFIED: local file]
- `state_manager/trades.py` — `append_warning(state, source, message)` signature [VERIFIED: local file]

### Secondary (MEDIUM confidence)
- [trading-ig FAQ](https://trading-ig.readthedocs.io/en/latest/faq.html) — historical data allowance (10,000 pts/week), rate limit error codes, token lifetime details
- Multiple WebSearch results cross-confirming IG response JSON shape (`snapshotTimeUTC`, `openPrice.bid`, `openPrice.ask`, `lastTradedVolume`)
- WebSearch confirming `lastTradedVolume = 0` for spread-bet instruments (IG Labs community thread)
- Epic codes `IX.D.ASX.IFM.IP` (SPI200) and `CS.D.AUDUSD.MINI.IP` (AUDUSD) cited in multiple community examples

### Tertiary (LOW confidence)
- Epic code confirmation: requires operator to verify via IG demo API before execution (flagged in Assumptions Log A1, A2)

---

## Metadata

**Confidence breakdown:**
- Auth endpoint shape: HIGH — verified from trading-ig source code (raw GitHub) and IG Labs guide
- Prices endpoint shape: HIGH — verified from trading-ig source code
- Response JSON fields: MEDIUM — cross-verified across 3+ community sources, not from official docs directly
- Volume = 0 for spread bets: MEDIUM — confirmed by community reports on IG Labs forum
- Epic codes: LOW/ASSUMED — cited but not verified against IG AU live API

**Research date:** 2026-05-16
**Valid until:** 2026-06-16 (IG API versioning is stable; epic codes change less frequently)
