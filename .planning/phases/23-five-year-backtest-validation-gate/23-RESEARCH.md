# Phase 23: 5-Year Backtest Validation Gate — Research

**Researched:** 2026-05-01
**Domain:** Python backtest module — parquet cache, bar-by-bar replay, metrics, Chart.js multi-tab UI, FastAPI POST route
**Confidence:** HIGH (all critical items verified against codebase source, pip registry, or runtime benchmarks)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- D-01: Parquet cache 24h staleness; pandas.to_parquet / read_parquet (pyarrow engine); no binary serialization (security); no CSV; cache at `.planning/backtests/data/<symbol>-<from>-<to>.parquet`
- D-02: Initial account AUD $10,000; full-on-exit cost model ($6 SPI / $5 AUDUSD); NOT half/half (Phase 19 paper-trade contrast)
- D-03: End-date = today AWST, start = today minus 5 years; dateutil.relativedelta for leap-year correctness
- D-04: Three Chart.js charts (SPI200 / AUDUSD / combined) in tab layout; default tab = combined; hash state `#tab=spi200`
- D-05: Full JSON schema — metadata + metrics (6 metrics per instrument) + equity_curve (all trading days) + trades (closed only)
- D-06: History view = table + overlay chart (10 most recent runs); table sorted desc
- D-07: Render layer = `backtest/render.py` called from `web/routes/backtest.py`; dashboard.py untouched
- D-08: Module structure: `backtest/__init__.py`, `data_fetcher.py`, `simulator.py`, `metrics.py`, `render.py`, `cli.py`, `__main__.py`
- D-09: Hex-boundary extensions; `simulator.py`/`metrics.py`/`render.py` STDLIB_ONLY + pandas/numpy/signal_engine/sizing_engine; data_fetcher.py is the ONE I/O exception
- D-10: Reuse `signal_engine.compute_indicators`, `signal_engine.get_signal`, `sizing_engine.step` verbatim
- D-11: CLI surface with --years/--end-date/--initial-account/--cost-spi/--cost-audusd/--refresh/--output; log prefix `[Backtest]`
- D-12: Four web routes; `GET /backtest`, `GET /backtest?history=true`, `GET /backtest?run=<filename>`, `POST /backtest/run`
- D-13: `STRATEGY_VERSION` via fresh attribute access (anti kwarg-default-capture)
- D-14: Operator override form on /backtest page; POSTs to /backtest/run; synchronous execution; CSS-only loading spinner
- D-15: Cookie-session auth on all /backtest* routes (Phase 16.1 middleware reuse)
- D-16: Pass criterion: `cumulative_return_pct > 100.0` (strict); combined is the gating metric
- D-17: Empty-state copy defined; `< 5y` data -> bail at fetch time
- D-18: Performance budget: <60s for 5y x 2 instruments

### Claude's Discretion
- Tab UI pattern: first introduction in this codebase; researcher recommends vanilla JS + ARIA role="tab"/role="tabpanel" + URL hash
- Chart.js multi-instance: destroy vs toggle-visibility on tab switch
- Golden report fixture: hand-authored vs generated
- Sharpe formula: daily-naked (`mean/std`) vs annualized (`x sqrt(252)`) -- needs pinning
- Max drawdown: canonical pandas idiom to surface

### Deferred Ideas (OUT OF SCOPE)
- True walk-forward with parameter optimization
- CI gating on PASS criterion
- Backtest email notification
- Sortino / Calmar / Information Ratio
- Per-trade attribution
- Multi-strategy comparison overlay
- CSV export of trade log
- Async job pattern for POST /backtest/run
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| BACKTEST-01 | 5-year daily OHLCV backtest using live signal_engine + sizing_engine constants | step() signature confirmed; compute_indicators + get_signal public API confirmed |
| BACKTEST-02 | JSON report: metadata + metrics + equity_curve + trades | D-05 schema locked; json.dumps XSS-safety pattern identified |
| BACKTEST-03 | `/backtest` web route with Chart.js equity curve per instrument | Chart.js IIFE pattern from dashboard.py confirmed; multi-instance pattern researched |
| BACKTEST-04 | CLI entry `python -m backtest`; pass criterion `cum_return > 100%` | argparse pattern confirmed; exit-code convention documented |
</phase_requirements>

---

## Summary

Phase 23 is the final v1.2 phase. It introduces a new `backtest/` hex module that is entirely self-contained: it fetches 5 years of OHLCV via yfinance, caches in parquet, replays the live signal/sizing engines bar-by-bar, computes 6 metrics, and writes a JSON report to `.planning/backtests/`. A new `/backtest` web route renders the report with three Chart.js tabs (SPI200 / AUDUSD / combined) and a POST override form.

Two critical facts established by this research: (1) `pyarrow` is NOT in requirements.txt and NOT installed — it must be added as `pyarrow==24.0.0`; (2) `sizing_engine.step()` exists with a different signature than CONTEXT D-10 implies — it takes `(position, bar, indicators, old_signal, new_signal, account, multiplier, cost_aud_open)`, returning a `StepResult` dataclass, not just an updated position. The simulator must compose these primitives correctly.

The performance budget is comfortable: dev-machine benchmarks show the full simulation (both instruments) completes in ~120ms vectorized. Even allowing for a 10-15x slowdown on the 1-vCPU droplet with yfinance fetch overhead, total runtime should be well under the 60s budget.

**Primary recommendation:** Add `pyarrow==24.0.0` to requirements.txt; implement the simulator using `compute_indicators` vectorized on the full df first, then extract per-bar signals by replicating `get_signal` logic inline (avoids O(n^2) slice overhead), then loop `sizing_engine.step()` bar-by-bar.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| OHLCV fetch + parquet cache | backtest/data_fetcher.py | -- | I/O adapter; only file in backtest/ allowed to touch disk/network |
| Bar-by-bar simulation | backtest/simulator.py | signal_engine, sizing_engine | Pure math; delegates to existing engines via function calls |
| Metrics aggregation | backtest/metrics.py | -- | Pure math; no I/O, no engine dependencies beyond pandas/numpy |
| HTML report rendering | backtest/render.py | -- | Pure string construction; html.escape + json.dumps for XSS safety |
| CLI entry point | backtest/cli.py | backtest/data_fetcher, simulator, metrics | Adapter; owns argparse + JSON write + stdout logging |
| Web routes | web/routes/backtest.py | backtest/render, backtest/simulator, backtest/data_fetcher | Thin adapter; calls render, redirects, validates path |
| Cookie auth | web/middleware/auth.py | -- | Phase 16.1 reuse; no per-route auth code in backtest routes |
| Chart.js rendering | backtest/render.py (server) | Client JS (tab switching) | Server emits chart data via json.dumps; client-side JS handles tab visibility |

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pyarrow | 24.0.0 | Parquet read/write engine for pandas | Only viable engine (fastparquet not installed); pandas 2.3.3 requires it for to_parquet |
| pandas | 2.3.3 (pinned) | DataFrame OHLCV compute + parquet I/O | Already in requirements.txt |
| numpy | 2.0.2 (pinned) | Numeric operations inside signal_engine | Already in requirements.txt |
| python-dateutil | 2.9.0.post0 | relativedelta for leap-year safe 5-year offset | Installed as transitive dep of pandas; NOT currently in requirements.txt -- add pin |

### Supporting (already installed, no new dep required)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| json (stdlib) | -- | JSON report serialisation; json.dumps for Chart.js data injection safety | Always -- json.dumps not html.escape for JS data blocks |
| html (stdlib) | -- | html.escape for operator-visible strings in HTML | Attribute values, table cells, form defaults |
| pathlib (stdlib) | -- | Path construction for cache files, JSON output | data_fetcher.py + cli.py |
| argparse (stdlib) | -- | CLI surface (D-11) | cli.py |
| re (stdlib) | -- | Filename validation for path traversal guard | web/routes/backtest.py |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pyarrow | fastparquet | fastparquet not installed, no wheel verified for Python 3.11 on this machine; pyarrow is the pandas default |
| pyarrow | CSV with explicit dtype | Slower load, messy DatetimeIndex round-trip, no columnar compression |
| pyarrow | feather (Arrow IPC) | Also requires pyarrow; same install cost, less familiar format |

**Installation -- only new dep:**
```bash
pip install pyarrow==24.0.0
```
Add to `requirements.txt`:
```
pyarrow==24.0.0
python-dateutil==2.9.0.post0  # transitive but should be pinned per STATE.md policy
```

**Version verification:** [VERIFIED: pip index versions pyarrow] -- latest stable is `24.0.0`; Python 3.11 wheel available (`cp311-cp311-macosx_12_0_arm64.whl`). `python-dateutil==2.9.0.post0` already installed as pandas transitive dep.

---

## Architecture Patterns

### System Architecture Diagram

```
CLI: python -m backtest
        |
        v
backtest/cli.py  --(argparse)--> validate params
        |
        +--> backtest/data_fetcher.py  --> yfinance API
        |         |                          |
        |         |<-- .planning/backtests/data/*.parquet (24h cache)
        |         |
        |         +--> returns pd.DataFrame (OHLCV, DatetimeIndex)
        |
        +--> backtest/simulator.py
        |         |   +-- signal_engine.compute_indicators(df) --> df_with_indicators
        |         |   +-- per-bar signal extraction loop
        |         |   +-- sizing_engine.step() loop --> trades[], equity_curve[]
        |         +--> returns SimResult(trades, equity_curve, per_instrument_accounts)
        |
        +--> backtest/metrics.py
        |         |   metrics(trades, equity_curve) --> {sharpe, max_dd, win_rate, ...}
        |         +--> returns MetricsResult per instrument + combined
        |
        +--> json.dumps --> .planning/backtests/<sv>-<ts>.json

Web: GET /backtest
        |
        +-- web/routes/backtest.py  (thin adapter)
        |         +-- reads latest .planning/backtests/*.json
        |         +-- path traversal guard (validate filename)
        |         +-- calls backtest/render.py
        |
        +--> backtest/render.py --> HTML string --> HTMLResponse

POST /backtest/run
        |
        +-- parse Form(initial_account_aud, cost_spi_aud, cost_audusd_aud)
        +-- validate (all > 0)
        +-- backtest/data_fetcher.py (cache hit expected)
        +-- backtest/simulator.py + backtest/metrics.py
        +-- json.dumps --> new .json file
        +--> RedirectResponse --> GET /backtest
```

### Recommended Project Structure
```
backtest/
+-- __init__.py         # constants: BACKTEST_INITIAL_ACCOUNT_AUD, BACKTEST_COST_SPI_AUD, BACKTEST_COST_AUDUSD_AUD
+-- data_fetcher.py     # yfinance + parquet cache; I/O adapter
+-- simulator.py        # pure bar-by-bar replay; reuses signal_engine + sizing_engine
+-- metrics.py          # Sharpe / max_dd / win_rate / expectancy / cum_return; pure
+-- render.py           # HTML + plain-text render; pure (html.escape + json.dumps ok)
+-- cli.py              # argparse entry; calls data_fetcher + simulator + metrics + persist
+-- __main__.py         # dispatch: from backtest.cli import main; main()
web/routes/
+-- backtest.py         # four route handlers; thin adapter
tests/
+-- test_backtest_data_fetcher.py
+-- test_backtest_simulator.py
+-- test_backtest_metrics.py
+-- test_backtest_render.py
+-- test_backtest_cli.py
+-- test_web_backtest.py
+-- fixtures/backtest/
    +-- golden_report.json  # hand-authored; ~3KB; covers all D-05 fields
```

### Pattern 1: sizing_engine.step() -- Actual Signature

**CRITICAL: CONTEXT D-10 describes `step(prev_position, current_signal, today_bar)` as a 3-arg call but the ACTUAL signature is different.** [VERIFIED: read sizing_engine.py lines 515-561]

```python
# ACTUAL signature (sizing_engine.py:515)
def step(
  position: Position | None,    # current open position or None (flat)
  bar: dict,                    # {'open': f, 'high': f, 'low': f, 'close': f, 'date': str}
  indicators: dict,             # {'atr': f, 'adx': f, 'pdi': f, 'ndi': f, 'rvol': f}
  old_signal: int,              # yesterday's signal (LONG/SHORT/FLAT)
  new_signal: int,              # today's signal (LONG/SHORT/FLAT)
  account: float,               # current account equity in AUD
  multiplier: float,            # instrument point value (SPI=5.0, AUDUSD=10000.0)
  cost_aud_open: float,         # per-contract OPENING cost (= round_trip / 2)
) -> StepResult:
```

```python
# StepResult fields (sizing_engine.py:77-94)
@dataclasses.dataclass(frozen=True)
class StepResult:
  position_after: Position | None
  closed_trade: ClosedTrade | None   # populated when a position was closed
  sizing_decision: SizingDecision | None
  pyramid_decision: PyramidDecision | None
  unrealised_pnl: float
  warnings: list[str]
```

```python
# ClosedTrade fields (what the simulator needs for the trade log)
@dataclasses.dataclass(frozen=True)
class ClosedTrade:
  direction: str       # 'LONG' or 'SHORT'
  entry_price: float
  exit_price: float
  n_contracts: int
  realised_pnl: float  # gross minus closing-half cost (D-13 SPLIT model)
  exit_reason: str     # 'flat_signal' | 'signal_reversal' | 'stop_hit' | 'adx_exit'
```

**IMPORTANT COST-MODEL NOTE:** `sizing_engine.step()` uses the half/half split cost model (D-13 from Phase 2). The `cost_aud_open` parameter is half the round-trip cost. `ClosedTrade.realised_pnl` has the closing half already deducted; the opening half was charged against unrealised P&L during the open period.

CONTEXT D-02 says "full-on-exit" for the backtest. The economic net effect IS the full round-trip (open-half + close-half = full round-trip), just split across two accounting entries. The planner must reconstruct D-05 trade schema fields:
- `cost_aud` in JSON = `round_trip_cost` (= `cost_aud_open * 2`, e.g. 6.0 for SPI200)
- `net_pnl_aud` = `closed_trade.realised_pnl` (already includes close-half deduction)
- `gross_pnl_aud` = `closed_trade.realised_pnl + cost_aud_open * n_contracts` (add back close-half)

This is bookkeeping reconstruction, NOT a reimplementation. Pass `cost_aud_open = round_trip / 2` to step().

### Pattern 2: Simulator Optimal Loop

[VERIFIED: benchmark on 1260 bars, Python 3.11.15, dev machine]

**DO NOT call `get_signal(df[:i+1])` per bar** -- that is O(n^2) and slow. Instead: `compute_indicators` vectorized ONCE, then extract signals inline.

```python
from signal_engine import compute_indicators, LONG, SHORT, FLAT, ADX_GATE
from system_params import MOM_THRESHOLD
import pandas as pd

def _compute_signals_vectorized(df_with_indicators):
  '''Extract LONG/SHORT/FLAT per bar without O(n^2) slicing.
  Source: replicates get_signal() logic inline (signal_engine.py:219-231).
  '''
  signals = []
  for i in range(len(df_with_indicators)):
    row = df_with_indicators.iloc[i]
    adx = row['ADX']
    if pd.isna(adx) or adx < ADX_GATE:
      signals.append(FLAT)
      continue
    moms = [row['Mom1'], row['Mom3'], row['Mom12']]
    valid = [m for m in moms if not pd.isna(m)]
    votes_up = sum(1 for m in valid if m > MOM_THRESHOLD)
    votes_dn = sum(1 for m in valid if m < -MOM_THRESHOLD)
    if votes_up >= 2:
      signals.append(LONG)
    elif votes_dn >= 2:
      signals.append(SHORT)
    else:
      signals.append(FLAT)
  return signals
```

**Benchmark results (verified on dev machine, Python 3.11.15, numpy 2.0.2, pandas 2.3.3):**
- `compute_indicators` (1260 bars): 15-18ms
- Signal extraction loop (1260 bars): 40-45ms
- `step()` loop (1260 bars): 27ms
- **Total per instrument: ~60ms | 2 instruments: ~120ms**
- Worst-case 10x droplet penalty: ~1.2s simulator time
- yfinance fetch (cache miss): 10-30s (first run only)
- yfinance fetch (cache hit): sub-second

### Pattern 3: Chart.js Multi-Instance

[VERIFIED: dashboard.py lines 2611-2688 -- existing IIFE pattern]

The existing dashboard uses a single `<canvas id="equityChart">` with an IIFE. For three tabs, use three canvases with distinct IDs.

**Rules:**
1. All three `<canvas>` elements MUST be in the DOM when the page loads.
2. Use the `hidden` attribute on tab panels (not CSS `visibility:hidden`).
3. **Do NOT destroy and re-create charts on tab switch** -- this causes flicker. Render all three on page load (inside IIFEs), toggle `hidden` attribute with JS.
4. Canvas ID uniqueness: `equityChartSpi200`, `equityChartAudusd`, `equityChartCombined`. History overlay chart: `equityChartHistory`.
5. The IIFE pattern `(function() { new Chart(...); })();` is established in this codebase -- reuse verbatim.

```html
<!-- Tab container pattern for backtest page -->
<div role="tablist" aria-label="Instrument results">
  <button role="tab" aria-selected="true" aria-controls="panel-combined" id="tab-combined">Combined</button>
  <button role="tab" aria-selected="false" aria-controls="panel-spi200" id="tab-spi200">SPI 200</button>
  <button role="tab" aria-selected="false" aria-controls="panel-audusd" id="tab-audusd">AUD/USD</button>
</div>
<div id="panel-combined" role="tabpanel" aria-labelledby="tab-combined">
  <canvas id="equityChartCombined" aria-label="Combined equity curve" role="img"></canvas>
</div>
<div id="panel-spi200" role="tabpanel" aria-labelledby="tab-spi200" hidden>
  <canvas id="equityChartSpi200" aria-label="SPI 200 equity curve" role="img"></canvas>
</div>
<div id="panel-audusd" role="tabpanel" aria-labelledby="tab-audusd" hidden>
  <canvas id="equityChartAudusd" aria-label="AUD/USD equity curve" role="img"></canvas>
</div>
```

Tab switching JS (inline `<script>` in body, after the chart IIFEs):
```javascript
(function() {
  var tabs = document.querySelectorAll('[role="tab"]');
  var panels = document.querySelectorAll('[role="tabpanel"]');

  function activateTab(tabId) {
    tabs.forEach(function(t) {
      t.setAttribute('aria-selected', t.id === tabId ? 'true' : 'false');
    });
    panels.forEach(function(p) {
      p.hidden = p.getAttribute('aria-labelledby') !== tabId;
    });
    var slug = tabId.replace('tab-', '');
    history.replaceState(null, '', '#tab=' + slug);
  }

  tabs.forEach(function(tab) {
    tab.addEventListener('click', function() { activateTab(tab.id); });
  });

  var hash = window.location.hash.match(/^#tab=(\w+)$/);
  if (hash) { activateTab('tab-' + hash[1]); }
})();
```

**Chart.js 4.4.6 UMD CDN + SRI -- copy from dashboard.py verbatim:**
```python
# Source: dashboard.py:113-116 [VERIFIED]
_CHARTJS_URL = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.js'
_CHARTJS_SRI = 'sha384-MH1axGwz/uQzfIcjFdjEfsM0xlf5mmWfAwwggaOh5IPFvgKFGbJ2PZ4VBbgSYBQN'
```
The backtest page's HTML shell needs the same `<script src=... integrity=... crossorigin="anonymous">` tag. `backtest/render.py` owns these constants (per D-07) -- copy the strings, do NOT import dashboard.py.

### Pattern 4: JSON-Safe Chart.js Data Injection

[VERIFIED: dashboard.py:2635-2641 -- existing pattern]

```python
# Source: dashboard.py:2635-2641 [VERIFIED: read source]
payload = json.dumps(
  {'labels': labels, 'data': data},
  ensure_ascii=False,
  sort_keys=True,       # byte-stable dict order
  allow_nan=False,      # stray NaN must fail loudly (not produce invalid JSON)
).replace('</', '<\\/')  # </script> injection defence
```

**RULE: Never use `html.escape()` for Chart.js data blocks.** `html.escape` produces `&lt;` inside `<script>` tags -- that is valid HTML but invalid JavaScript. `json.dumps` produces valid JSON (a subset of valid JS literal syntax). The `<\/` replacement handles the `</script>` close-tag injection vector.

### Pattern 5: Path Traversal Defence for `?run=<filename>`

[VERIFIED: CONTEXT D-12 risk register + confirmed FastAPI has NO built-in path-traversal helper]

```python
import re, os
from pathlib import Path

_BACKTEST_DIR = Path('.planning/backtests')
_SAFE_FILENAME_RE = re.compile(r'^[a-zA-Z0-9._-]+\.json$')

def _resolve_safe_backtest_path(filename: str) -> Path:
  '''Two-layer defence: regex gate + directory-listing whitelist.
  FastAPI has no built-in path-traversal protection -- this is manual.
  '''
  if not _SAFE_FILENAME_RE.match(filename):
    raise ValueError(f'invalid backtest filename: {filename!r}')
  available = set(os.listdir(_BACKTEST_DIR))
  if filename not in available:
    raise ValueError(f'backtest file not found: {filename!r}')
  return _BACKTEST_DIR / filename
```

Reject: `../../etc/passwd`, `../state.json`, `v1.0.0.json.bak`, any string containing `..` or `/`. The regex gate is the first filter; the whitelist check catches any residual edge cases.

### Pattern 6: Sharpe Formula Convention

[ASSUMED -- see Assumptions Log A1]

CONTEXT D-05 labels the metric `sharpe_daily`. Two conventions exist:

| Convention | Formula | Typical range |
|------------|---------|---------------|
| Daily (non-annualized) | `mean(daily_returns) / std(daily_returns)` | 0.03-0.10 for good systems |
| Annualized | `mean(daily_returns) / std(daily_returns) * sqrt(252)` | 0.5-2.0 for good systems |

CONTEXT D-05 shows the example value `sharpe_daily: 0.84`. This value is only plausible as an annualized Sharpe. A non-annualized Sharpe of 0.84 would require a daily mean/std ratio of 0.84, which is extraordinarily high.

**Recommendation:** Compute annualized Sharpe (`mean/std * sqrt(252)`); name it `sharpe_daily` as locked per D-05. The name is non-standard but the value in the example matches annualized convention. **Planner must surface this to user for confirmation before execution.**

### Pattern 7: Max Drawdown Canonical Pandas Idiom

[VERIFIED: standard pandas idiom]

```python
def max_drawdown_pct(equity_curve: list[float]) -> float:
  '''Peak-to-trough percentage drawdown. Returns a negative percentage.'''
  import pandas as pd
  equity = pd.Series(equity_curve, dtype='float64')
  if len(equity) < 2:
    return 0.0
  rolling_max = equity.cummax()
  drawdown = (equity / rolling_max) - 1.0
  return float(drawdown.min()) * 100.0  # negative, e.g. -23.10
```

Pitfall: `equity.min() / equity.max() - 1` gives worst-point vs global-max, NOT peak-to-trough path. The `cummax()` idiom is correct.

### Pattern 8: POST /backtest/run -- Cookie Auth on POST Routes

[VERIFIED: read web/routes/paper_trades.py + tests/conftest.py + web/middleware/auth.py]

POST `/backtest/run` follows the exact same pattern as POST `/paper-trade/open`. Auth is handled by `AuthMiddleware.dispatch` for ALL paths not in `EXEMPT_PATHS` or `PUBLIC_PATHS`. The middleware handles POST the same as GET -- no special handling needed.

```python
# Source: mirrors web/routes/paper_trades.py pattern [VERIFIED]
from fastapi import Form, Request
from fastapi.responses import RedirectResponse

@app.post('/backtest/run')
async def run_backtest(
  request: Request,
  initial_account_aud: float = Form(...),
  cost_spi_aud: float = Form(...),
  cost_audusd_aud: float = Form(...),
) -> RedirectResponse:
  # validate > 0, run sim, write JSON
  return RedirectResponse(url='/backtest', status_code=303)
```

**Use HTTP 303 (See Other) for POST-redirect-GET**, not 302 or the default. FastAPI's `RedirectResponse` defaults to 307 (which re-POSTs). Set `status_code=303` explicitly. [ASSUMED A2 -- verify with FastAPI docs]

### Pattern 9: Walk-Forward vs In-Sample Replay -- Terminology Clarification

[VERIFIED: CONTEXT.md Scope section, operator brainstorm quote]

**The phase goal says "walk-forward backtest" but the scope explicitly says this is NOT walk-forward.** This is in-sample replay with fixed constants.

| Term | Definition | This Phase |
|------|-----------|-----------|
| Walk-forward | Rolling train/test windows; parameters re-optimized per window | NOT this phase |
| In-sample replay | Fixed constants applied to all historical data | THIS is what Phase 23 implements |
| Out-of-sample test | Separate held-out period | NOT this phase |

The simulator applies the same `ADX_GATE`, `TRAIL_MULT_LONG`, `RISK_PCT_LONG` etc. to all 5 years. No parameter search. No train/test split. "Walk-forward" in ROADMAP is loose terminology meaning "step through bars in time order." The planner must NOT implement rolling-window train/test splits.

### Anti-Patterns to Avoid
- **O(n^2) signal computation:** calling `get_signal(df[:i+1])` per bar. Use inline signal extraction.
- **`html.escape` on Chart.js data:** produces `&lt;` inside `<script>` tags -- invalid JS. Use `json.dumps(...).replace('</', '<\\/')`.
- **`cost_aud_open = FULL_ROUND_TRIP` passed to step():** charges the open-half twice (once via unrealised PnL, once as the close-half). Pass half the round-trip.
- **Multi-instance Chart.js destroy/recreate on tab switch:** causes flicker and resets zoom. Toggle `hidden` attribute instead.
- **Binary serialization for cache:** security risk on tampered files. Parquet only.
- **`datetime.date.today()` without timezone:** returns local machine date (server may be UTC). Use `datetime.datetime.now(AWST).date()`.
- **`pathlib.Path(user_input)` without validation:** `..` traversal bypasses naive checks. Regex gate first.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Sharpe ratio | Custom loop | `mean/std * sqrt(252)` on pandas Series | Three lines; pandas handles ddof, edge cases |
| Max drawdown | Manual peak tracking | `equity.cummax()` idiom | Canonical; handles non-monotonic peak tracking |
| Parquet read/write | CSV with dtype annotations | `df.to_parquet()` / `pd.read_parquet()` | Columnar, typed, fast; DatetimeIndex round-trips correctly |
| Date arithmetic | `today.year - 5` | `dateutil.relativedelta(years=-5)` | Handles Feb 29 leap year edge case correctly |
| Tab UI | Custom JS framework | Vanilla `role="tab"/"tabpanel"` + ARIA | First tab implementation; 15 lines of JS |
| Path traversal guard | Regex only | Regex + `os.listdir()` whitelist | Belt and suspenders; regex alone can miss edge cases |
| Per-bar signal extraction | Re-run compute_indicators per bar | Inline `get_signal` logic on pre-computed indicators | Avoids O(n^2) |
| JSON injection in `<script>` | `html.escape` on data | `json.dumps(...).replace('</', '<\\/')` | Established pattern from dashboard.py; html.escape produces invalid JS |
| Bar-by-bar simulation exit/pyramid | Custom logic | `sizing_engine.step()` verbatim | Phase 2 D-12 invariant guarantees stateless correctness; tested |

**Key insight:** The signal and sizing engines ARE the computation. The simulator's only job is to plumb their inputs and accumulate their outputs.

---

## Common Pitfalls

### Pitfall 1: sizing_engine.step() Cost Model Mismatch
**What goes wrong:** step() uses the half/half split cost model internally. Passing `cost_aud_open = FULL_ROUND_TRIP` would charge double. `ClosedTrade.realised_pnl` already has close-half deducted; the open-half was charged against unrealised_pnl during the open period.
**Why it happens:** CONTEXT D-02 says "full-on-exit" but step() was designed for the live system where open/close halves are tracked separately.
**How to avoid:** Pass `cost_aud_open = round_trip / 2` to step(). Reconstruct `cost_aud = round_trip` in the JSON trade log for display.
**Warning signs:** Per-trade P&L is half of expected -- close-half being double-charged.

### Pitfall 2: O(n^2) Signal Computation
**What goes wrong:** Calling `get_signal(df_ind.iloc[:i+1])` inside the bar loop re-scans all previous bars for every bar -- O(n^2).
**Why it happens:** get_signal(df) reads `df.iloc[-1]`, so naively you'd pass a growing slice.
**How to avoid:** `compute_indicators` once on the full df (vectorized), then extract the signal from each row directly by replicating the `get_signal` logic inline.
**Warning signs:** Simulator takes >5 seconds on a 5-year dataset (should be <500ms).

### Pitfall 3: Chart.js Destroy/Recreate on Tab Switch
**What goes wrong:** Destroying and recreating `Chart()` instances on each tab switch causes flicker, resets zoom state, and wastes compute.
**Why it happens:** Intuitive approach when the chart isn't visible.
**How to avoid:** Instantiate all three charts at page load (IIFEs). Toggle `hidden` attribute on the `<div role="tabpanel">` wrapper.
**Warning signs:** Visual flicker; chart animation replays on every tab activation.

### Pitfall 4: `datetime.date.today()` Without Timezone
**What goes wrong:** On a server running UTC, `datetime.date.today()` returns UTC date, which may be one day behind AWST before 08:00 AWST.
**Why it happens:** Python `datetime.date.today()` uses the local machine timezone.
**How to avoid:** Use `datetime.datetime.now(AWST).date()` where `AWST = zoneinfo.ZoneInfo('Australia/Perth')`.
**Warning signs:** Backtest end-date appears as yesterday when run early morning AWST.

### Pitfall 5: pyarrow Not Installed (CONFIRMED)
**What goes wrong:** `df.to_parquet()` raises `ImportError: Unable to find a usable engine; tried using: 'pyarrow', 'fastparquet'`.
**Why it happens:** pyarrow is an OPTIONAL pandas dependency. NOT installed in this project's `.venv`.
**How to avoid:** Add `pyarrow==24.0.0` to requirements.txt in Wave 0.
**Warning signs:** `ImportError` on first `to_parquet()` call.

### Pitfall 6: JSON Report Serialisation of numpy/pandas Types
**What goes wrong:** `json.dumps({'value': np.float64(1.5)})` raises `TypeError: Object of type float64 is not JSON serializable`.
**Why it happens:** pandas/numpy scalars are not Python floats.
**How to avoid:** Wrap all numeric outputs with `float(x)` or `int(x)` before JSON serialisation. The existing `get_latest_indicators` in signal_engine.py does this with `float(row['ATR'])` -- follow the same pattern.
**Warning signs:** `TypeError: Object of type float64 is not JSON serializable` when writing the report file.

### Pitfall 7: Missing `entry_date` in ClosedTrade
**What goes wrong:** The `ClosedTrade` dataclass has no `entry_date` or `exit_date`. D-05 JSON schema requires `open_dt` and `close_dt`.
**Why it happens:** step() captures `entry_date` in `position_after['entry_date']` (set at open), not in ClosedTrade.
**How to avoid:** The simulator must carry `position_after['entry_date']` alongside position state and include it when writing the trade log entry from `closed_trade`.
**Warning signs:** JSON trade log missing `open_dt`; `KeyError: 'entry_date'` when building the trade dict.

### Pitfall 8: Parquet DatetimeIndex Round-Trip
**What goes wrong:** CSV loses timezone info from DatetimeIndex. Binary formats with no schema (like the insecure serialization format) execute arbitrary code on tampered files.
**Why it happens:** yfinance returns TZ-aware DatetimeIndex; naive formats lose this.
**How to avoid:** `df.to_parquet(path, engine='pyarrow')` and `pd.read_parquet(path, engine='pyarrow')` handle TZ-aware DatetimeIndex correctly in pyarrow >= 3.0 (24.0.0 satisfies).
**Warning signs:** Date misalignment between cached and fresh-fetched data.

---

## Code Examples

Verified patterns from official sources:

### Parquet cache hit/miss check
```python
# Source: standard pathlib + os.path.getmtime pattern [ASSUMED: standard Python idiom]
from pathlib import Path
import os, time

def _is_cache_fresh(path: Path, max_age_seconds: int = 86400) -> bool:
  if not path.exists():
    return False
  age = time.time() - os.path.getmtime(path)
  return age < max_age_seconds

cache_path = Path('.planning/backtests/data') / f'{symbol}-{start}-{end}.parquet'
if not _is_cache_fresh(cache_path) or force_refresh:
  df = _fetch_yfinance(symbol, start, end)
  cache_path.parent.mkdir(parents=True, exist_ok=True)
  df.to_parquet(cache_path, engine='pyarrow')
else:
  df = pd.read_parquet(cache_path, engine='pyarrow')
```

### STRATEGY_VERSION fresh attribute access (anti kwarg-default-capture)
```python
# Source: LEARNINGS.md 2026-04-29 + web/routes/paper_trades.py pattern [VERIFIED]
# WRONG: def run(sv=system_params.STRATEGY_VERSION) -- captures at import time
# CORRECT: read inside function body
def _write_report(report: dict, output_path: Path) -> None:
  import system_params  # fresh read on every call
  report['metadata']['strategy_version'] = system_params.STRATEGY_VERSION
  with open(output_path, 'w') as f:
    json.dump(report, f, indent=2, allow_nan=False)
```

### Simulator account tracking with sizing_engine.step()
```python
# Source: sized from sizing_engine.py API [VERIFIED: read sizing_engine.py]
from sizing_engine import step
from system_params import SPI_MULT, SPI_COST_AUD
from signal_engine import FLAT

COST_OPEN = SPI_COST_AUD / 2.0  # half of round-trip for cost_aud_open param

account = BACKTEST_INITIAL_ACCOUNT_AUD
position = None
old_signal = FLAT
equity = [account]
trades = []

for i in range(len(df_ind)):
  bar_row = df_ind.iloc[i]
  new_signal = signals[i]
  bar = {
    'open': float(bar_row['Open']),
    'high': float(bar_row['High']),
    'low': float(bar_row['Low']),
    'close': float(bar_row['Close']),
    'date': bar_row.name.date().isoformat(),  # DatetimeIndex
  }
  inds = {
    'atr':  float(bar_row['ATR'])  if not pd.isna(bar_row['ATR'])  else float('nan'),
    'adx':  float(bar_row['ADX'])  if not pd.isna(bar_row['ADX'])  else float('nan'),
    'pdi':  float(bar_row['PDI'])  if not pd.isna(bar_row['PDI'])  else float('nan'),
    'ndi':  float(bar_row['NDI'])  if not pd.isna(bar_row['NDI'])  else float('nan'),
    'rvol': float(bar_row['RVol']) if not pd.isna(bar_row['RVol']) else float('nan'),
  }
  result = step(position, bar, inds, old_signal, new_signal, account, SPI_MULT, COST_OPEN)

  if result.closed_trade is not None:
    ct = result.closed_trade
    account += ct.realised_pnl  # close-half already deducted
    entry_date = (position or {}).get('entry_date', bar['date'])
    trades.append({
      'open_dt': entry_date,
      'close_dt': bar['date'],
      'instrument': 'SPI200',
      'side': ct.direction,
      'entry_price': float(ct.entry_price),
      'exit_price': float(ct.exit_price),
      'contracts': int(ct.n_contracts),
      'exit_reason': ct.exit_reason,
      'gross_pnl_aud': float(ct.realised_pnl + COST_OPEN * ct.n_contracts),
      'cost_aud': float(SPI_COST_AUD),  # full round-trip for D-05 display
      'net_pnl_aud': float(ct.realised_pnl),
      'balance_after_aud': float(account),
    })

  position = result.position_after
  old_signal = new_signal
  equity.append(account)
```

### Metrics computation
```python
# Source: standard quant idiom [ASSUMED A1: annualized Sharpe]
import math, statistics

def compute_metrics(equity_curve: list[float], trades: list[dict]) -> dict:
  returns = [
    equity_curve[i] / equity_curve[i-1] - 1.0
    for i in range(1, len(equity_curve))
    if equity_curve[i-1] > 0
  ]
  if len(returns) >= 2:
    mean_r = statistics.mean(returns)
    std_r = statistics.stdev(returns)  # ddof=1
    sharpe = (mean_r / std_r * math.sqrt(252)) if std_r > 0 else 0.0
  else:
    sharpe = 0.0

  import pandas as pd
  eq = pd.Series(equity_curve, dtype='float64')
  rolling_max = eq.cummax()
  max_dd = float(((eq / rolling_max) - 1.0).min()) * 100.0

  closed = [t for t in trades if t.get('net_pnl_aud') is not None]
  n = len(closed)
  win_rate = sum(1 for t in closed if t['net_pnl_aud'] > 0) / n if n > 0 else 0.0
  expectancy = sum(t['net_pnl_aud'] for t in closed) / n if n > 0 else 0.0
  cum_return = (equity_curve[-1] / equity_curve[0] - 1.0) * 100.0 if equity_curve[0] > 0 else 0.0

  return {
    'cumulative_return_pct': round(cum_return, 4),
    'sharpe_daily': round(sharpe, 4),   # name per D-05; value is annualized per A1
    'max_drawdown_pct': round(max_dd, 4),
    'win_rate': round(win_rate, 4),
    'expectancy_aud': round(expectancy, 4),
    'total_trades': n,
    'pass': cum_return > 100.0,  # D-16 strict greater-than
  }
```

### Golden report fixture -- hand-authored recommendation
```python
# tests/fixtures/backtest/golden_report.json -- hand-authored, ~3KB
# Why hand-authored: generating via yfinance makes fixture network-dependent
# and non-deterministic (yfinance data revisions). Hand-authored fixtures
# test render logic, not simulator correctness (separate test domain).
```

Minimal valid report matching D-05 schema (2 equity points, 1 trade). Planner creates this file in Wave 0 with the fields from D-05 schema. Render tests load this file and assert HTML structure without running the simulator.

### Web route test pattern (cookie auth on POST)
```python
# Source: tests/conftest.py + tests/test_web_paper_trades.py [VERIFIED]
from fastapi.testclient import TestClient

def test_post_backtest_run_redirects(client, valid_cookie_token):
  # valid_cookie_token fixture from conftest.py
  r = client.post(
    '/backtest/run',
    data={'initial_account_aud': '10000', 'cost_spi_aud': '6.0', 'cost_audusd_aud': '5.0'},
    cookies={'tsi_session': valid_cookie_token},
    follow_redirects=False,
  )
  assert r.status_code == 303
  assert r.headers['location'] == '/backtest'

def test_post_backtest_run_unauthenticated(client):
  r = client.post(
    '/backtest/run',
    data={'initial_account_aud': '10000', 'cost_spi_aud': '6.0', 'cost_audusd_aud': '5.0'},
    follow_redirects=False,
  )
  assert r.status_code == 401  # non-browser curl path
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Phase 19 half/half ledger cost | Phase 23 full-on-exit for closed-trade display | Phase 23 D-02 | step() still uses half/half internally; reconstruct full cost in JSON |
| `datetime.date.today()` | `datetime.datetime.now(AWST).date()` | Phase 7 convention | Correct AWST date on UTC server |
| `html.escape` for all dynamic content | `json.dumps` for Chart.js data blocks | Phase 5 dashboard.py | XSS-safe AND JS-valid |

**Deprecated/outdated:**
- The CONTEXT D-10 description `step(prev_position, current_signal, today_bar)` -- this 3-arg signature does NOT exist in sizing_engine.py. Actual signature requires 8 positional args. D-10 is an approximation of intent, not the API spec.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Sharpe formula: CONTEXT D-05 `sharpe_daily: 0.84` implies annualized (`mean/std * sqrt(252)`), not raw daily ratio | Pattern 6 | If user intended raw daily mean/std, output is ~16x smaller than example; mislabeled metric |
| A2 | HTTP 303 needed for POST-redirect-GET (FastAPI `RedirectResponse` defaults to 307) | Pattern 8 | If wrong: browser re-POSTs to /backtest on redirect, triggering another simulation run |
| A3 | All three Chart.js canvases should be rendered at page load (not lazily); toggle `hidden` attribute | Pattern 3 | If wrong and lazy: canvas has zero size when mounted on a hidden tab -- Chart.js may not render correctly |
| A4 | python-dateutil should be added to requirements.txt as a pinned direct dep | Standard Stack | Already a transitive dep via pandas; risk is low but explicit pin is per project policy |

---

## Open Questions

1. **Sharpe formula: annualized vs daily**
   - What we know: CONTEXT D-05 labels it `sharpe_daily` with example value 0.84
   - What's unclear: 0.84 is plausible only as annualized; raw daily Sharpe of 0.84 would be extraordinary
   - Recommendation: Implement as annualized (`mean/std * sqrt(252)`); surface to user for confirmation. Name is non-standard but locked per D-05.

2. **sizing_engine.step() cost model vs D-02 "full-on-exit"**
   - What we know: step() uses half/half split (Phase 2 D-13); D-02 says "full-on-exit"
   - What's unclear: Does user want JSON to show cost split or attributed entirely to close?
   - Recommendation: Use step() as-is (half/half internally); reconstruct `cost_aud = round_trip` in JSON display. This is the correct economic representation and matches D-05 schema.

3. **`entry_atr` and `level` fields in D-05 trade schema**
   - What we know: D-05 shows `entry_atr` and `level` in the trade object; ClosedTrade does NOT have these fields
   - What's unclear: `entry_atr` comes from `position['atr_entry']`; `level` comes from `position['pyramid_level']`
   - Recommendation: Simulator carries these from the `position_after` dict at the time of opening and includes them when building the trade log entry from `closed_trade`.

4. **`exit_reason` mapping: sizing_engine values vs D-05 schema**
   - What we know: D-05 shows `"signal_change"` as exit_reason; ClosedTrade.exit_reason uses `'flat_signal'` and `'signal_reversal'`
   - Recommendation: Either (a) map `flat_signal`/`signal_reversal` -> `signal_change`, `stop_hit` -> `trailing_stop`, `adx_exit` -> `adx_drop`; or (b) keep sizing_engine values verbatim (more precise, but diverges from D-05). Planner must choose.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| pyarrow | backtest/data_fetcher.py (parquet) | NO | -- | None -- MUST be added to requirements.txt |
| python-dateutil | backtest/data_fetcher.py (relativedelta) | YES | 2.9.0.post0 | `today.replace(year=today.year-5)` with Feb 29 guard |
| Chart.js 4.4.6 UMD | backtest/render.py (CDN script tag) | CDN-dependent | 4.4.6 | Graceful degradation -- chart areas blank but page loads |
| pytest | tests/ | YES | 8.3.3 (pinned) | -- |

**Missing dependencies with no fallback:**
- `pyarrow==24.0.0` -- blocks `backtest/data_fetcher.py` entirely. MUST be added to `requirements.txt` in Wave 0.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.3.3 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `.venv/bin/pytest tests/test_backtest_*.py tests/test_web_backtest.py -x -q` |
| Full suite command | `.venv/bin/pytest -x -q` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| BACKTEST-01 | simulator produces deterministic output from fixed fixture | unit | `pytest tests/test_backtest_simulator.py -x` | No -- Wave 0 |
| BACKTEST-01 | step() cost model reconstruction (gross/net/cost fields) | unit | `pytest tests/test_backtest_simulator.py::TestCostModel -x` | No -- Wave 0 |
| BACKTEST-01 | data_fetcher cache hit/miss/refresh | unit | `pytest tests/test_backtest_data_fetcher.py -x` | No -- Wave 0 |
| BACKTEST-02 | JSON report schema completeness (all D-05 fields) | unit | `pytest tests/test_backtest_cli.py::TestJsonSchema -x` | No -- Wave 0 |
| BACKTEST-02 | metrics formulas (Sharpe, max_dd, win_rate, expectancy, cum_return) | unit | `pytest tests/test_backtest_metrics.py -x` | No -- Wave 0 |
| BACKTEST-03 | render_report() HTML contains 3 tab containers + metrics rows | unit | `pytest tests/test_backtest_render.py -x` | No -- Wave 0 |
| BACKTEST-03 | Chart.js script tag with SRI in render output | unit | `pytest tests/test_backtest_render.py::TestChartJsSri -x` | No -- Wave 0 |
| BACKTEST-03 | GET /backtest 200 with cookie auth | integration | `pytest tests/test_web_backtest.py::TestGetBacktest -x` | No -- Wave 0 |
| BACKTEST-03 | GET /backtest?run=../../etc/passwd returns 400 | integration | `pytest tests/test_web_backtest.py::TestPathTraversal -x` | No -- Wave 0 |
| BACKTEST-04 | CLI exit code 0 on PASS / 1 on FAIL | unit | `pytest tests/test_backtest_cli.py::TestExitCode -x` | No -- Wave 0 |
| BACKTEST-04 | POST /backtest/run redirects to /backtest (303) | integration | `pytest tests/test_web_backtest.py::TestPostRun -x` | No -- Wave 0 |
| D-09 (hex) | AST guard -- simulator.py/metrics.py/render.py have no forbidden imports | unit | `pytest tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent -x` | YES (extended) |

### Sampling Rate
- **Per task commit:** `.venv/bin/pytest tests/test_backtest_*.py tests/test_web_backtest.py -x -q`
- **Per wave merge:** `.venv/bin/pytest -x -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_backtest_data_fetcher.py` -- BACKTEST-01 data layer
- [ ] `tests/test_backtest_simulator.py` -- BACKTEST-01 simulation + determinism
- [ ] `tests/test_backtest_metrics.py` -- BACKTEST-02 metrics formulas
- [ ] `tests/test_backtest_render.py` -- BACKTEST-03 HTML + Chart.js
- [ ] `tests/test_backtest_cli.py` -- BACKTEST-04 CLI surface
- [ ] `tests/test_web_backtest.py` -- BACKTEST-03/04 web routes
- [ ] `tests/fixtures/backtest/golden_report.json` -- hand-authored reference report
- [ ] `pyarrow==24.0.0` install: add to requirements.txt (`pip install pyarrow==24.0.0`)
- [ ] `backtest/` directory creation with `__init__.py` placeholder

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Phase 16.1 AuthMiddleware -- covers all /backtest* routes |
| V3 Session Management | yes | Phase 16.1 itsdangerous signed cookie -- reused unchanged |
| V4 Access Control | no | Single operator; no roles |
| V5 Input Validation | yes | Pydantic Field(gt=0) for override form; regex + whitelist for filename |
| V6 Cryptography | no | No new crypto; cookies handled by Phase 16.1 |

### Known Threat Patterns for This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Path traversal via `?run=<filename>` | Information Disclosure | Regex `^[a-zA-Z0-9._-]+\.json$` + `os.listdir()` whitelist |
| JSON injection in `<script>` tag | Tampering | `json.dumps(...).replace('</', '<\\/')` -- dashboard.py established pattern |
| Tampered parquet cache file | Tampering | Parquet format (binary, typed schema -- no eval path); `--refresh` is recovery |
| Negative/zero operator override values | Tampering | Server-side: `initial_account_aud > 0`, `cost >= 0` |
| POST /backtest/run double-submit | Availability | Disable submit button on `submit` event (CSS-only, D-14) |

---

## Sources

### Primary (HIGH confidence)
- `sizing_engine.py` lines 515-730 -- step() exact signature, StepResult, ClosedTrade dataclasses [VERIFIED: read source]
- `signal_engine.py` lines 171-253 -- compute_indicators + get_signal public API, ADX_GATE, MOM_THRESHOLD [VERIFIED: read source]
- `requirements.txt` -- confirmed pyarrow NOT present [VERIFIED: read source]
- `dashboard.py` lines 2611-2688 -- Chart.js IIFE pattern, json.dumps injection defence [VERIFIED: read source]
- `tests/test_signal_engine.py` lines 488-600 -- FORBIDDEN_MODULES sets for hex boundary extension [VERIFIED: read source]
- `tests/conftest.py` -- valid_cookie_token fixture, client fixture pattern [VERIFIED: read source]
- `web/routes/paper_trades.py` -- POST form-encoded handler pattern, 303 redirect [VERIFIED: read source]
- `web/middleware/auth.py` -- AuthMiddleware gates all routes uniformly [VERIFIED: read source]
- Benchmark: `.venv/bin/python` timing on 1260-bar simulation [VERIFIED: measured]
- pip registry: `pyarrow==24.0.0` latest; `python-dateutil==2.9.0.post0` installed [VERIFIED: pip index]

### Secondary (MEDIUM confidence)
- `.planning/phases/23-five-year-backtest-validation-gate/23-CONTEXT.md` -- all 18 locked decisions [VERIFIED: read source]
- Standard pandas `cummax()` idiom for max drawdown -- well-established; not source-cited

### Tertiary (LOW confidence)
- Sharpe annualized convention (A1) -- assumed from D-05 example value; planner must confirm with user
- HTTP 303 for POST-redirect-GET in FastAPI (A2) -- assumed from HTTP spec; planner should verify with FastAPI docs

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- pyarrow version verified against pip registry; not-installed status confirmed at runtime
- sizing_engine.step() signature: HIGH -- read actual source code
- Architecture: HIGH -- derived from existing codebase patterns
- Performance budget: HIGH -- measured on dev machine with conservative extrapolation
- Sharpe formula: LOW -- example value implies annualized but label says `sharpe_daily`; requires user confirmation

**Research date:** 2026-05-01
**Valid until:** 2026-06-01 (pyarrow version; pandas API stable)
