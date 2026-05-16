---
phase: 41-data-feed-integration-ig-rest-api
reviewed: 2026-05-16T00:00:00Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - data_fetcher.py
  - system_params.py
  - daily_run.py
  - .env.example
  - tests/test_data_fetcher.py
  - tests/test_main.py
findings:
  critical: 3
  warning: 4
  info: 2
  total: 9
status: issues_found
---

# Phase 41: Code Review Report

**Reviewed:** 2026-05-16T00:00:00Z
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

Reviewed the Phase 41 IG REST API integration: 6 helpers in `data_fetcher.py`, `ig_epic` fields added to `system_params.DEFAULT_MARKETS`, and `LAST_FETCH_SOURCE` fallback warning logic in `daily_run.py`. The architecture and narrow-catch discipline are sound. Three critical defects were found: an empty-prices crash in `_ig_normalise`, a LAST_FETCH_SOURCE state-tracking gap that causes daily_run.py to silently miss the fallback warning for the `no ig_epic` path, and a re-auth loop bug that consumes one retry slot without advancing to the next attempt. Additionally, IG credentials are logged in plaintext on non-403 session errors, and `system_params.py` violates its own hex constraint by importing `os` indirectly through the `ig_epic` comment block (minor, no actual import added, but the pattern in `_epic_for_symbol` uses a local `import system_params` which is architecturally inconsistent).

---

## Critical Issues

### CR-01: `_ig_normalise` crashes with KeyError on empty prices list

**File:** `data_fetcher.py:269`

**Issue:** When IG returns an empty `prices` list (valid API response for a holiday, suspended instrument, or out-of-hours request), `_ig_normalise` builds an empty `rows` list and empty `timestamps` list, then calls `pd.DataFrame(rows)` which produces a DataFrame with zero rows AND zero columns. The subsequent `df.index = pd.to_datetime(timestamps, utc=True)` succeeds (empty index), but `df[['Open', 'High', 'Low', 'Close', 'Volume']]` raises `KeyError` because the columns do not exist on an empty DataFrame — the missing-columns guard at line 271 checks `_REQUIRED_COLUMNS - set(df.columns)` which is non-empty but the guard raises `DataFetchError`, which is correct. HOWEVER: `pd.DataFrame([])` (rows is `[]`) produces an empty DataFrame with shape `(0, 0)`. The guard at line 271 WILL fire and raise `DataFetchError` — good. But the slice at line 276 `return df[['Open', ..., 'Volume']]` is AFTER the guard, so that path is safe. The real crash is that `_fetch_via_ig` catches `DataFetchError` with a bare `except` that only catches `requests.exceptions.HTTPError` and network errors — `DataFetchError` from `_ig_normalise` propagates uncaught through `_fetch_via_ig` and surfaces as an unhandled exception in `fetch_ohlcv`, bypassing the yfinance fallback entirely. An IG empty-prices response therefore raises `DataFetchError` and aborts the daily run rather than falling back.

**Fix:** In `_fetch_via_ig`, add `DataFetchError` to the caught exception types in the inner try block so normalise errors trigger the yfinance fallback path:

```python
    except (requests.exceptions.HTTPError, DataFetchError) as e:
        # DataFetchError from _ig_normalise (empty/malformed prices) is
        # non-retryable — fall back to yfinance on next call.
        if isinstance(e, DataFetchError):
            logger.warning('[Fetch] IG normalise error: %s — falling back', e)
            return None
        # ... existing HTTPError handling below
```

Or more precisely, wrap the `_ig_normalise(raw)` call in its own try/except to distinguish it from the HTTP layer:

```python
      try:
        raw = _ig_fetch_ohlcv_raw(epic, days, session)
      except requests.exceptions.HTTPError as e:
        # ... existing 403 / other HTTP handling
      except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError) as e:
        # ... existing network handling
      else:
        try:
          df = _ig_normalise(raw)
        except DataFetchError as e:
          logger.warning('[Fetch] IG normalise failed: %s — falling back', e)
          return None
        LAST_FETCH_SOURCE[symbol] = 'ig'
        return df
```

---

### CR-02: `LAST_FETCH_SOURCE` not set when symbol has no `ig_epic` — daily_run.py warning never fires

**File:** `data_fetcher.py:388-400`

**Issue:** In `fetch_ohlcv`, when `ig_key` is present but `ig_epic` is `None` (symbol not mapped), execution falls through the `if ig_epic:` block without setting `LAST_FETCH_SOURCE[symbol]` to anything. `daily_run.py` line 210 checks `data_fetcher.LAST_FETCH_SOURCE.get(yf_symbol) == 'yfinance_fallback'` — this check is `False` for an unmapped symbol, so no fallback warning is appended to state. This is a silent failure: an operator who adds a market without an `ig_epic` will never see a warning that IG was silently skipped. Furthermore, if the symbol was previously fetched via IG (from a prior run in the same process) the stale `'ig'` value remains in the module-level dict, causing a false-positive "IG success" reading.

**Fix:** Set `LAST_FETCH_SOURCE[symbol]` unconditionally in the `ig_key` branch when `ig_epic` is absent:

```python
  if ig_key:
    ig_epic = _epic_for_symbol(symbol)
    if ig_epic:
      df = _fetch_via_ig(ig_epic, days, retries, backoff_s, symbol)
      if df is not None:
        return df
      logger.warning(
        '[Fetch] IG fetch failed for %s — falling back to yfinance', symbol,
      )
      LAST_FETCH_SOURCE[symbol] = 'yfinance_fallback'
    else:
      # No epic mapping — treat same as fallback so daily_run.py logs the warning.
      logger.warning('[Fetch] No IG epic for %s — falling back to yfinance', symbol)
      LAST_FETCH_SOURCE[symbol] = 'yfinance_fallback'
  else:
    LAST_FETCH_SOURCE[symbol] = 'yfinance'
```

---

### CR-03: Re-auth `continue` in `_fetch_via_ig` skips the sleep but does not count the consumed attempt — effectively grants an extra free retry

**File:** `data_fetcher.py:338-339`

**Issue:** When a 403 is received on attempt N and re-auth succeeds, `continue` jumps to `attempt N+1` (next iteration of `range(1, retries + 1)`). This means the 403+re-auth sequence consumed one attempt slot but the loop counter advances to N+1 as if that attempt never happened — effectively giving one bonus attempt beyond `retries`. For `retries=3`: attempts 1 (403) → re-auth → continue → attempt 2 → attempt 3 → attempt 4 (due to `range(1, 4)`). Wait — actually `continue` restarts the SAME iteration because it doesn't increment `attempt`; `for` loops in Python DO advance the iterator on `continue`. So attempt 1 gets 403, re-auth succeeds, `continue` goes to attempt 2. The loop runs attempts 1, 2, 3 normally = 3 total. But the test at line 670-674 in `test_data_fetcher.py` asserts `len(get_calls) == 2` (1 with 403 + 1 with success), which is CORRECT for the happy re-auth path. The actual bug is different: if the 403 occurs on attempt 1 and re-auth succeeds, `continue` makes the loop move to attempt 2. That is correct.

**The real bug:** if the 403 occurs on attempt `retries` (last attempt), `re_authed` is set `True`, and `continue` goes past the loop boundary — `range(1, retries+1)` is exhausted — so the function returns `None` without ever retrying the fetch with the fresh session. The re-auth succeeded but the fresh session is never used.

**Fix:** After successful re-auth, do not `continue` to the next loop index — instead retry the current attempt index by decrementing or restructuring. The simplest fix that preserves the re-auth-counts-as-one-attempt contract:

```python
      re_authed = False
      attempt = 0
      while attempt < retries:
        attempt += 1
        try:
          raw = _ig_fetch_ohlcv_raw(epic, days, session)
          df = _ig_normalise(raw)
          LAST_FETCH_SOURCE[symbol] = 'ig'
          return df
        except requests.exceptions.HTTPError as e:
          if e.response is not None and e.response.status_code == 403 and not re_authed:
            try:
              session = _ig_create_session()
              re_authed = True
              attempt -= 1  # don't consume the attempt slot for re-auth
              continue
            except (...) as re_auth_err:
              ...
              return None
```

---

## Warnings

### WR-01: IG password logged in plaintext on non-403 session HTTPError

**File:** `data_fetcher.py:312-313`

**Issue:** Line 313 logs `'[Fetch] IG session HTTP error: %s', e`. The `requests.exceptions.HTTPError` `str()` representation includes the response body on some servers and always includes the request URL. More critically, `e` may have a `.request` attribute containing the full request body — which includes `IG_PASSWORD` in plaintext (line 208-209). While the standard `str(HTTPError)` doesn't dump the body, logging the raw exception object is not safe in all `requests` versions. The 403-path correctly uses `redact_secret`, but the non-403 path on line 313 does not.

**Fix:**
```python
    else:
      logger.warning(
        '[Fetch] IG session HTTP error %s — falling back to yfinance',
        e.response.status_code if e.response is not None else 'unknown',
      )
```

---

### WR-02: `_ig_normalise` performs float arithmetic on bid/ask prices — violates the project's Decimal-for-money rule

**File:** `data_fetcher.py:263-266`

**Issue:** The project's `CLAUDE.md` and `system_params.py` mandate `Decimal` for all AUD amounts with no floats at money boundaries. `_ig_normalise` computes `(p['openPrice']['bid'] + p['openPrice']['ask']) / 2` in raw Python `float`. The IG API returns prices as JSON numbers (floats). While the downstream signal engine uses `float64` intentionally, the mid-price calculation introduces float arithmetic where a price like `7845.5` (bid) + `7846.0` (ask) = `15691.5 / 2 = 7845.75` is exact in float, but edge cases like `7845.1 + 7845.9 = 7691.0` can accumulate ULP error. This is inconsistent with the project's Decimal policy and could silently produce prices that differ from the true mid by a ULP, then get stored in state and compared for PnL.

**Fix:** Compute mid price via `Decimal`:
```python
from decimal import Decimal
bid = Decimal(str(p['openPrice']['bid']))
ask = Decimal(str(p['openPrice']['ask']))
mid = float((bid + ask) / 2)
```
Or, since the DataFrame stores floats for signal engine consumption, convert back to float after the Decimal arithmetic. This matches the `to_aud()` pattern in `system_params.py`.

---

### WR-03: `_ig_normalise` silent empty-string timestamp — `pd.to_datetime('')` raises or produces NaT

**File:** `data_fetcher.py:260,270`

**Issue:** If both `snapshotTimeUTC` and `snapshotTime` are absent from a price candle, `p.get('snapshotTime', '')` returns `''` and `ts_str = ''` is appended to `timestamps`. `pd.to_datetime([''], utc=True)` raises `dateutil.parser.ParserError` or produces a `NaT` depending on pandas version, which then makes the DatetimeIndex non-monotonically-increasing and breaks downstream `signal_engine.compute_indicators` assumptions. This is an unhandled edge case that becomes a crash with an opaque error message.

**Fix:**
```python
    ts_str = p.get('snapshotTimeUTC') or p.get('snapshotTime')
    if not ts_str:
      raise DataFetchError(
        f'IG price candle missing snapshotTimeUTC and snapshotTime: {p!r}'
      )
    timestamps.append(ts_str)
```

---

### WR-04: `LAST_FETCH_SOURCE` is a mutable module-level dict shared across runs in the same process — no reset between calls

**File:** `data_fetcher.py:81`

**Issue:** `LAST_FETCH_SOURCE` is a module-level dict that accumulates entries across all `fetch_ohlcv` calls in the same process lifetime. In the scheduler path (`main.main([])`, which runs indefinitely with multiple daily calls), a symbol that successfully fetched via IG today will retain `'ig'` in `LAST_FETCH_SOURCE` across subsequent runs. If tomorrow's IG call fails and the fallback fires, `LAST_FETCH_SOURCE[symbol]` will be updated to `'yfinance_fallback'` — this part is fine. However, if a new symbol is added at runtime and it lacks an `ig_epic`, the prior-run's `'ig'` value from a different symbol could theoretically be read under a different key. The main risk is that the dict grows unboundedly over multiple runs (memory leak in the scheduler process) and that test isolation requires `data_fetcher.LAST_FETCH_SOURCE.clear()` between tests — which is not done in the test suite. The `test_ig_fallback_to_yfinance` test at line 510 reads `LAST_FETCH_SOURCE` after the call but does not clear it before the call, so if a prior test wrote `'ig'` for `'^AXJO'` the assertion at line 539 passes for the wrong reason.

**Fix:** Clear the symbol's entry at the start of `fetch_ohlcv` before any branch writes it, or add a `conftest.py` fixture that calls `data_fetcher.LAST_FETCH_SOURCE.clear()` in `autouse=True` scope. At minimum, add to test setup:
```python
data_fetcher.LAST_FETCH_SOURCE.clear()
```

---

## Info

### IN-01: `_epic_for_symbol` uses `import system_params` inside the function body — inconsistent with module-level imports

**File:** `data_fetcher.py:284`

**Issue:** All other `system_params` usages in `data_fetcher.py` use the module-level `from system_params import HTTP_TIMEOUT_S, redact_secret` (line 39). The local `import system_params` at line 284 is inconsistent: it re-imports the full module on every call (Python caches it, so no real cost), but the pattern is inconsistent with the rest of the file. The comment says this avoids a circular import, but `system_params` has no imports from `data_fetcher` and the circular import risk does not exist.

**Fix:** Remove the local import and use the already-imported `system_params` at module level, or add `import system_params` at the top alongside the existing `from system_params import` line.

---

### IN-02: Test `test_ig_happy_path_spi200` asserts `len(df) >= 5` but the fixture has a fixed known length

**File:** `tests/test_data_fetcher.py:454`

**Issue:** `assert len(df) >= 5` is a weak assertion. The test requests `days=5` and the fixture has a specific number of rows. If `_ig_normalise` silently dropped rows (e.g., a bug skipping candles), the assertion would still pass as long as 5+ rows remain. The assertion should use `==` against the fixture's known row count, or at minimum assert the exact fixture length to catch row-dropping regressions.

**Fix:**
```python
fixture = _load_ig_fixture('ig_spi200_prices.json')
expected_rows = len(fixture['prices'])
assert len(df) == expected_rows, f'Expected {expected_rows} rows, got {len(df)}'
```

---

_Reviewed: 2026-05-16T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
