# audusd_400bar.csv — Canonical AUDUSD=X 400-bar fixture

- **Ticker:** `AUDUSD=X` (AUD/USD spot FX — canonical AUD/USD signal proxy per R-03)
- **Bars:** 400 daily OHLCV (last 400 of a 450-day yfinance fetch)
- **Date range:** 2024-10-01 → 2026-04-20 (FX trades through more calendar days than
  equity indexes — weekends off only).
- **yfinance version:** 1.2.0 (pinned in `requirements.txt`)
- **pandas version:** 2.3.3
- **numpy version:** 2.0.2
- **Python:** 3.11.8 (.venv)
- **Pull command (reproduction):**
  ```bash
  .venv/bin/python -c "
  import yfinance as yf, pandas as pd
  df = yf.download('AUDUSD=X', period='450d', auto_adjust=True, progress=False)
  if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.droplevel(1)
  df = df[['Open', 'High', 'Low', 'Close', 'Volume']].tail(400)
  df.index.name = 'Date'
  df.to_csv('tests/fixtures/audusd_400bar.csv', float_format='%.17g', date_format='%Y-%m-%d')
  "
  ```
- **Pull date:** 2026-04-20 (today)
- **auto_adjust:** `True` (modern yfinance default — for FX pairs this is a no-op since
  currency pairs don't have splits/dividends, but the pipeline still runs).
- **CSV precision:** written with `float_format='%.17g'` per RESEARCH Pitfall 4. Critical
  for FX because quote values have many fractional digits (e.g. `0.71580016613006592`).
  The default `%g` would round to 6 digits and break the 1e-9 tolerance gate.
- **Column order:** `Date,Open,High,Low,Close,Volume` — normalised from the yfinance
  MultiIndex `(field, ticker)` shape via `df.columns.droplevel(1)` per RESEARCH Pitfall 2.
- **Volume column:** FX spot has no exchange volume; yfinance returns `0` for every bar.
  This is expected and must not trip any downstream check that assumes volume > 0.
- **NaN representation:** pandas default (empty field).

## Provenance warning (Pitfall 3 — retroactive adjustments)

FX pairs do not undergo splits or dividends, so `auto_adjust=True` retroactive rewriting
is less of a concern than for stocks. However, yfinance may still amend historical bars
due to data-vendor corrections (typos, late-arriving settlement data). **Do not regenerate
casually.** If this CSV is ever updated, the goldens under
`tests/oracle/goldens/audusd_400bar_indicators.csv` and the SHA256 entries in
`tests/determinism/snapshot.json` MUST be regenerated in the same commit via:

```bash
.venv/bin/python tests/regenerate_goldens.py
```

Review the git diff line by line and reason about every bar that changed before
accepting the update.
