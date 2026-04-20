# axjo_400bar.csv — Canonical ^AXJO 400-bar fixture

- **Ticker:** `^AXJO` (S&P/ASX 200 index — canonical SPI 200 signal proxy per R-03)
- **Bars:** 400 daily OHLCV (last 400 of a 450-day yfinance fetch)
- **Date range:** 2024-09-17 → 2026-04-17 (start/end bars listed in CSV; includes weekends
  naturally skipped by the exchange calendar)
- **yfinance version:** 1.2.0 (pinned in `requirements.txt`)
- **pandas version:** 2.3.3
- **numpy version:** 2.0.2
- **Python:** 3.11.8 (.venv)
- **Pull command (reproduction):**
  ```bash
  .venv/bin/python -c "
  import yfinance as yf, pandas as pd
  df = yf.download('^AXJO', period='450d', auto_adjust=True, progress=False)
  if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.droplevel(1)
  df = df[['Open', 'High', 'Low', 'Close', 'Volume']].tail(400)
  df.index.name = 'Date'
  df.to_csv('tests/fixtures/axjo_400bar.csv', float_format='%.17g', date_format='%Y-%m-%d')
  "
  ```
- **Pull date:** 2026-04-20 (today)
- **auto_adjust:** `True` (modern yfinance default — for indexes like `^AXJO` this is
  effectively a no-op since no splits/dividends apply, but the adjustment pipeline still
  runs the data through).
- **CSV precision:** written with `float_format='%.17g'` per RESEARCH Pitfall 4. The
  default pandas `to_csv` uses 6 significant digits (`%g`) which silently loses precision
  and breaks the 1e-9 tolerance gate. `%.17g` preserves full float64 bit-for-bit.
- **Column order:** `Date,Open,High,Low,Close,Volume` — normalised from the yfinance
  MultiIndex `(field, ticker)` shape via `df.columns.droplevel(1)` per RESEARCH Pitfall 2.
  The raw yfinance ordering is alphabetical (`Close, High, Low, Open, Volume`) — we
  reorder to canonical OHLC before writing.
- **NaN representation:** pandas default (empty field) on the rare missing bar.

## Provenance warning (Pitfall 3 — retroactive adjustments)

Regenerating this file against the same date range at a later pull date may produce
**different** historical bars if a split/dividend/corporate action occurred in the
interim. yfinance applies the adjustment factor retroactively to every historical bar
when `auto_adjust=True`. For `^AXJO` (an index) this is typically a no-op, but the
pipeline still runs.

**Do not regenerate casually.** If this CSV is ever updated, the goldens under
`tests/oracle/goldens/axjo_400bar_indicators.csv` and the SHA256 entries in
`tests/determinism/snapshot.json` MUST be regenerated in the same commit via:

```bash
.venv/bin/python tests/regenerate_goldens.py
```

Review the git diff line by line and reason about every bar that changed before
accepting the update.
