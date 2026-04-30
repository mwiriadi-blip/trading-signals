---
phase: 23
phase_name: 5-year backtest validation gate
milestone: v1.2
created: 2026-05-01
status: locked
requirements: [BACKTEST-01, BACKTEST-02, BACKTEST-03, BACKTEST-04]
source: ROADMAP.md v1.2 Phase 23 Success Criteria + REQUIREMENTS.md BACKTEST namespace + operator discuss-phase 2026-05-01
---

# Phase 23 — 5-Year Backtest Validation Gate (CONTEXT)

## Goal

Every strategy ships with a 5-year walk-forward backtest report. The report aggregates equity curves and metrics per instrument and combined, applies the live signal engine bar-by-bar over the prior 5 years, and produces a single binary pass/fail on `cumulative_return_pct > 100.0`. Operator views the report on `/backtest`; failures gate the strategy change socially (operator expected to revert before deploying a regression). New module `backtest/` is hex-pure; data fetch + cache + simulator + metrics + HTML render all live there. The dashboard is untouched.

## Scope

**In:**
- New `backtest/` module structure: `backtest/__init__.py`, `backtest/data_fetcher.py` (yfinance + parquet cache), `backtest/simulator.py` (bar-by-bar replay), `backtest/metrics.py` (Sharpe / drawdown / win rate / expectancy), `backtest/render.py` (HTML + plain-text), `backtest/cli.py` (`python -m backtest` entry)
- New web routes in `web/routes/backtest.py`: `GET /backtest` (latest report), `GET /backtest?history=true` (table + overlay chart), `POST /backtest/run` (operator-supplied overrides)
- CLI: `python -m backtest [--years 5] [--end-date YYYY-MM-DD] [--initial-account 10000] [--cost-spi 6.0] [--cost-audusd 5.0] [--refresh]`
- JSON persistence to `.planning/backtests/<strategy_version>-<timestamp>.json` with full per-trade log + equity curve + 6 metrics + run metadata
- Parquet cache at `.planning/backtests/data/<symbol>-<from>-<to>.parquet` with 24h staleness
- Cookie-session auth on all `/backtest*` routes (Phase 16.1 reuse)
- **Operator-requested scope addition (D-14):** /backtest UI form to override `initial_account`, `cost_spi`, `cost_audusd` at run time, POSTs to `/backtest/run` which executes the simulation server-side and returns the new report
- Schema bump: NONE — backtests persist to `.planning/backtests/` JSON files, not `state.json`

**Out (deferred to v1.3+):**
- True walk-forward with parameter optimization (current scope is fixed-constants in-sample replay — operator brainstorm 2026-04-29 explicitly notes "not optimization, just historical validation of the live constants")
- Backtest gating in CI (auto-block deploy if PASS criterion fails)
- Multiple strategies side-by-side comparison on the same chart (current overlay is per-version of the same strategy)
- Risk metrics beyond Sharpe / DD / win rate / expectancy (Sortino, Calmar, Information Ratio)
- Per-trade attribution (which signal-vote conditions produced each P&L outcome)

**Out (different phases):**
- Real-time / intraday backtesting (Phase 23 is daily-cadence-only, matches the live signal engine)
- Multi-instrument expansion beyond SPI200 + AUDUSD (deferred to v2.0 horizon per SPEC.md)

## Locked decisions

### D-01 — Data source and caching strategy

**Parquet cache with 24h staleness.** First fetch writes `.planning/backtests/data/<symbol>-<from>-<to>.parquet`. Subsequent runs reuse if the file's mtime is within 24h. CLI flag `--refresh` forces re-fetch regardless. `.planning/backtests/data/` is `.gitignore`'d — cache is per-machine, not committed.

Implementation: `pandas.DataFrame.to_parquet` / `pandas.read_parquet` (uses `pyarrow` engine). RESEARCH should confirm whether `pyarrow` is already pulled in via existing deps; if not, add it to `requirements.txt` (binary wheel, ~30MB — acceptable cost for the cache speedup). Do NOT use `pickle` (security concern: pickle deserialisation can execute arbitrary code on a tampered cache file). Do NOT use raw CSV (datetime index round-trip is messy and slower for OHLCV at 5y scale).

Filename format: `<symbol>-<start>-<end>.parquet` where dates are ISO `YYYY-MM-DD`. Example: `^AXJO-2021-05-01-2026-05-01.parquet`. Operator can manually delete cache files to force re-fetch without `--refresh`.

Rejected: live yfinance every run (slow ~30-60s for 5y × 2 instruments, network-flaky); committed test fixtures (data goes stale, commits become noisy, reproducibility breaks operator's ability to refresh); pickle (arbitrary code execution risk).

### D-02 — Initial account + cost model

**Initial account:** AUD `$10,000` hardcoded as `BACKTEST_INITIAL_ACCOUNT_AUD = 10_000.0` constant in `backtest/__init__.py`. Tighter than the typical $100k retail account — operator's deliberate choice to surface position-sizing constraints (`n_contracts == 0` skip-and-warn rule from CLAUDE.md D-11/D-12).

**Cost model:** **Full-on-exit** matching `sizing_engine` v1.0 simulator semantics. Backtest closes trades on every signal change; opens are zero-cost; closes apply full `$6 AUD SPI200` / `$5 AUD AUDUSD` round-trip cost. **Different from Phase 19 D-02 paper-trade ledger half/half split** — backtest has no open-trade unrealised P&L view; closed-trades-only model is correct.

CLI flags `--initial-account 10000`, `--cost-spi 6.0`, `--cost-audusd 5.0` allow override; defaults match the constants.

**Operator-requested scope addition (D-14 below):** the `/backtest` page also has a UI form to override these at runtime via POST `/backtest/run`.

Rejected: $100k hardcoded (too forgiving for a $5/pt SPI mini system; doesn't surface sizing constraints); half/half cost split (matches Phase 19 paper-trade ledger but NOT the simulator's closed-trades-only semantics).

### D-03 — Date range / 5y window

**End-date = today, start-date = today − 5 years.** Each run uses the most recent 5y. Two runs on the same `STRATEGY_VERSION` with the same yfinance data state produce identical results; cross-day runs may differ slightly if yfinance has data revisions.

CLI flag `--end-date YYYY-MM-DD` allows reproducing a fixed window (operator records this explicitly for what-if scenarios). Default `--end-date` = today in AWST.

`--years` defaults to 5 per ROADMAP SC; CLI flag allows tuning.

Date arithmetic uses `datetime.date.today()` in AWST (matches Phase 7 `_get_process_tzname` convention) and `dateutil.relativedelta(years=-5)` for cross-leap-year correctness. If `dateutil` isn't pinned, use `today.replace(year=today.year - 5)` with a leap-year guard (Feb 29 → Feb 28 fallback).

Rejected: fixed end-date pinned per STRATEGY_VERSION bump (gets stale; awkward update workflow); end-date pinned at 2026-05-01 once and never updated (defeats the "re-runnable" requirement).

### D-04 — Equity curve display

**Three charts: per-instrument SPI200, per-instrument AUDUSD, combined as third tab.** Mobile-first tab layout in the existing dashboard CSS aesthetic. Each chart is Chart.js 4.4.6 UMD (Phase 5 precedent — pinned, CDN-loaded). Each tab shows:

- Equity curve (line chart, x = date, y = AUD account balance)
- Tab-local metrics row (cum return, Sharpe, max DD, win rate, expectancy, total trades)

Combined tab's equity curve = `balance_spi[i] + balance_audusd[i]` per timestamp. Combined cum return = `(combined_final − combined_initial) / combined_initial × 100`.

Default tab on page load = combined (operator's at-a-glance overview). Tab state preserved in URL hash (`#tab=spi200`) so operator can deep-link.

Rejected: three lines on one chart (overlay) — operator wanted separate per-instrument focus; combined-only — loses per-instrument attribution.

### D-05 — Output JSON schema

**Full per-trade log + equity curve + 6 metrics + metadata.** ~50KB per run. Enables future audit/replay without re-running yfinance. Schema:

```json
{
  "metadata": {
    "strategy_version": "v1.2.0",
    "run_dt": "2026-05-01T08:00:00+08:00",
    "years": 5,
    "end_date": "2026-05-01",
    "start_date": "2021-05-01",
    "initial_account_aud": 10000.0,
    "cost_spi_aud": 6.0,
    "cost_audusd_aud": 5.0,
    "instruments": ["SPI200", "AUDUSD"]
  },
  "metrics": {
    "combined": {
      "cumulative_return_pct": 127.45,
      "sharpe_daily": 0.84,
      "max_drawdown_pct": -23.10,
      "win_rate": 0.52,
      "expectancy_aud": 142.30,
      "total_trades": 178,
      "pass": true
    },
    "SPI200": { /* same shape, pass: bool against the >100% rule */ },
    "AUDUSD": { /* same shape */ }
  },
  "equity_curve": [
    {"date": "2021-05-01", "balance_spi": 10000.0, "balance_audusd": 10000.0, "balance_combined": 20000.0},
    /* one row per trading day, ascending */
  ],
  "trades": [
    {
      "open_dt": "2021-05-04",
      "close_dt": "2021-05-12",
      "instrument": "SPI200",
      "side": "LONG",
      "entry_price": 7012.5,
      "exit_price": 7089.0,
      "contracts": 1,
      "entry_atr": 35.2,
      "exit_reason": "signal_change",  /* or "trailing_stop", "adx_drop", "manual_stop" */
      "gross_pnl_aud": 382.50,
      "cost_aud": 6.0,
      "net_pnl_aud": 376.50,
      "balance_after_aud": 10376.50,
      "level": 1  /* pyramid level at exit */
    }
    /* one entry per closed trade */
  ]
}
```

Equity curve is ALL trading days (not just trade-event days) so the chart renders smoothly. Trade log is closed-trades-only.

Rejected: minimal schema (5KB) — drops audit/replay capability; CLI `--full-trace` flag — adds branching; default-full is acceptable at 50KB scale (~100 runs ≈ 5MB total over project lifetime).

### D-06 — History view layout (`/backtest?history=true`)

**Table + overlay chart stacked.** Table on top:

| Strategy version | Run date | End date | Cum return | Pass/Fail |
|---|---|---|---|---|
| v1.2.0 | 2026-05-01 | 2026-05-01 | +127.45% | ✓ PASS |
| v1.1.0 | 2026-04-30 | 2026-04-30 | +118.20% | ✓ PASS |

Sorted by run date desc. Each row is a link to a detail view at `/backtest?run=<filename>` showing that specific run's full report.

Below the table: Chart.js overlay with one line per historical run's combined equity curve. Distinct colors. Legend lists run IDs. **Caps at 10 most recent runs** to avoid clutter; older runs accessible via the table only.

Rejected: table-only (loses visual regression detection); overlay-only (loses pass/fail at-a-glance).

### D-07 — Render layer placement

**New module `backtest/render.py` called from `web/routes/backtest.py`.** Self-contained — `backtest/` owns its rendering. Rationale:

- Hex-pure principle: `backtest/render.py` is in the same hex domain as `backtest/simulator.py`. Same forbidden-imports rule.
- `dashboard.py` is untouched — already touched by Phases 5/16.1/17/19/20; further coupling becomes a maintenance burden.
- `web/routes/backtest.py` is a thin adapter: reads JSON files, calls `backtest.render.render_report(...)`, returns HTML.
- Same pattern as `pnl_engine` / `alert_engine` (both pure-math, neither in dashboard.py).

`backtest/render.py` exposes:

```python
def render_report(report: dict) -> str:
  '''Phase 23 — render a single backtest report as HTML.

  Reads from the canonical JSON schema (D-05). Returns full HTML body
  fragment (chart container + tabs + metrics + per-trade summary).

  Hex-pure: no I/O, no env vars, no clock injection.
  '''


def render_history(reports: list[dict]) -> str:
  '''Phase 23 — render the history view (D-06).

  reports: list of report dicts, sorted by run_dt desc, capped at 10.
  '''


def render_run_form(defaults: dict) -> str:
  '''Phase 23 D-14 — render the operator override form.'''
```

Rejected: extending dashboard.py (couples backtest UI to daily-signal dashboard layer); web route does HTML composition (web layer doing render-layer work; harder to test in isolation).

### D-08 — `backtest/` module structure

```
backtest/
├── __init__.py             # constants (BACKTEST_INITIAL_ACCOUNT_AUD, BACKTEST_COST_*) + version
├── data_fetcher.py         # yfinance + parquet cache; ONLY I/O-allowed module in backtest/
├── simulator.py            # bar-by-bar compute loop using signal_engine + sizing_engine; PURE
├── metrics.py              # Sharpe / DD / win rate / expectancy / cum return; PURE
├── render.py               # HTML report + history + override-form render; PURE (html.escape ok)
├── cli.py                  # `python -m backtest` entry; argparse; calls data_fetcher + simulator + persists JSON
└── __main__.py             # `python -m backtest` dispatch to cli.main()
```

`web/routes/backtest.py` imports `backtest.render` + `backtest.simulator` + `backtest.data_fetcher` (the latter only for the operator-override POST path) + `system_params.STRATEGY_VERSION`.

### D-09 — Hex-boundary preservation

**Forbidden imports per module (extends `tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent`):**

- `backtest/simulator.py`, `backtest/metrics.py` — `FORBIDDEN_MODULES_STDLIB_ONLY` (only `math`, `typing`, `system_params`, `signal_engine`, `sizing_engine`, `pandas`, `numpy` allowed). NO `state_manager`, `notifier`, `dashboard`, `main`, `requests`, `datetime`, `os`, `yfinance`, `pyarrow`.
- `backtest/render.py` — same as simulator + may import `html` (for escape) and `json` (stdlib, no I/O).
- `backtest/data_fetcher.py` — **adapter exception** (the ONLY I/O-allowed file in `backtest/`). May import `yfinance`, `pyarrow`, `pathlib`, `datetime`. Documented at module top with a comment block citing this CONTEXT D-09 rule.
- `backtest/cli.py` — adapter; imports argparse, json, all internal `backtest/*` modules. May import `sys`, `pathlib`. NO direct `state_manager` / `notifier` import.
- `web/routes/backtest.py` — adapter; imports `backtest/*`, FastAPI, system_params, web/middleware (cookie auth).

**Test extensions:**
- AST guard at `tests/test_signal_engine.py:480` adds `BACKTEST_PATHS_PURE = ['backtest/simulator.py', 'backtest/metrics.py', 'backtest/render.py']` and walks them against `_FORBIDDEN_MODULES_STDLIB_ONLY` plus the explicitly-allowed `signal_engine` / `sizing_engine` / `pandas` / `numpy`.
- `backtest/data_fetcher.py` is **explicitly excluded** from the AST guard with a documented comment — it's the I/O boundary.

### D-10 — Reuse signal_engine + sizing_engine directly

**No reimplementation.** The backtest simulator calls:
- `signal_engine.compute_indicators(df)` — same fn the live daily run uses
- `signal_engine.get_signal(df)` — same `LONG=1 / SHORT=-1 / FLAT=0` integer return
- `sizing_engine.step(prev_position, current_signal, today_bar)` — same trailing stop + pyramid replay

Phase 2 D-12 stateless invariant ("`check_pyramid` evaluates only `(level+1) * atr_entry` threshold") carries forward — `step()` is safe to call bar-by-bar in a loop with prior `position` carried in a local variable.

If `step()` doesn't currently expose the signature the simulator needs, **the simulator does NOT modify `sizing_engine.py`** — it composes existing primitives. Any helper-extraction in `sizing_engine` is a separate refactor phase, not Phase 23 scope.

### D-11 — CLI surface

```
python -m backtest \
  [--years 5]                      # default 5
  [--end-date YYYY-MM-DD]          # default today AWST
  [--initial-account 10000]        # default $10,000 AUD
  [--cost-spi 6.0]                 # default $6 AUD round-trip
  [--cost-audusd 5.0]              # default $5 AUD round-trip
  [--refresh]                      # force re-fetch yfinance, ignore cache
  [--output PATH]                  # default .planning/backtests/<sv>-<ts>.json
```

Always writes JSON to `.planning/backtests/<strategy_version>-<timestamp>.json` (timestamp = ISO compact `YYYYMMDDTHHMMSS`).

Prints summary to stdout per CLAUDE.md log-prefix convention:
```
[Backtest] Fetching SPI200 ^AXJO 2021-05-01..2026-05-01 (cache hit)
[Backtest] Fetching AUDUSD AUDUSD=X 2021-05-01..2026-05-01 (cache miss; pulling yfinance)
[Backtest] Simulating SPI200: 1257 bars, 89 trades
[Backtest] Simulating AUDUSD: 1257 bars, 89 trades
[Backtest] Combined cum_return=+127.45% sharpe=0.84 max_dd=-23.10% win_rate=52% trades=178
[Backtest] PASS (>100% threshold)
[Backtest] Wrote .planning/backtests/v1.2.0-20260501T080000.json
```

Exit code 0 on PASS, exit code 1 on FAIL — operator can wire this into local pre-commit hooks if desired (deferred suggestion, not in v1.2 scope).

### D-12 — Web routes

| Method | Path | Handler |
|---|---|---|
| GET | `/backtest` | Renders the most recent JSON report (sorted by mtime desc); falls back to "no runs yet" copy if `.planning/backtests/` is empty |
| GET | `/backtest?history=true` | Renders D-06 table + overlay chart of the last 10 runs |
| GET | `/backtest?run=<filename>` | Renders the specified run file (validates filename against directory listing — no path traversal) |
| POST | `/backtest/run` | Form-encoded body `{initial_account, cost_spi, cost_audusd}`; runs simulation server-side via `backtest.cli.run(...)`; writes JSON; redirects to `/backtest` |

All routes auth-gated by Phase 16.1 cookie-session middleware. POST `/backtest/run` is the operator-requested scope addition (D-14).

Form encoding follows G-44 lesson: standard `application/x-www-form-urlencoded`; routes parse via FastAPI `Form()` parameters.

### D-13 — STRATEGY_VERSION tagging

Every JSON file's `metadata.strategy_version` reads `system_params.STRATEGY_VERSION` at run time via fresh attribute access (Phase 22 LEARNINGS / G-45 kwarg-default capture trap). Test asserts that monkeypatching `STRATEGY_VERSION` AFTER import propagates to the JSON file.

CLI prints the strategy version in the summary line so operator sees it without opening the JSON.

### D-14 — Operator override form (scope addition)

**Beyond ROADMAP §SC; locked per operator request 2026-05-01.**

`/backtest` page renders a form near the top with three input fields:
- `initial_account_aud` (number, default 10000)
- `cost_spi_aud` (number, default 6.0)
- `cost_audusd_aud` (number, default 5.0)
- `[Run with overrides]` submit button

Submitting POSTs to `/backtest/run` form-encoded. Server runs the simulation synchronously (~30-60s on the droplet), persists JSON, redirects to `/backtest` showing the new run. The override values are recorded in the JSON `metadata` per D-05.

**Risk: long synchronous request.** uvicorn default request timeout is 60s per worker. Mitigation:
- Use parquet cache (D-01) so data fetch is sub-second after first run
- Simulator should run <30s for 5y × 2 instruments (Phase 1 indicators are vectorized via pandas)
- If timeout becomes an issue post-launch, defer to v1.3+ (async job + progress polling)

A loading spinner CSS-only (no JS dependency beyond standard browser form submission) covers the wait. The form sets `disabled` on the submit button on `submit` event to prevent double-submit.

### D-15 — Cookie-session auth

All `/backtest*` routes inherit the Phase 16.1 cookie-session middleware. Unauthenticated browser → 302 to `/login`; unauthenticated curl → 401 plain (Phase 16.1 D-04..D-07 reconciliation).

POST `/backtest/run` rejects unauthenticated requests with 401 (no CSRF token needed — SameSite=Lax cookie + same-origin POST is sufficient per global LEARNINGS).

### D-16 — Pass criterion strict

`cumulative_return_pct > 100.0` (strictly greater, not ≥). Both per-instrument and combined are independently evaluated. Combined PASS does NOT require both per-instrument PASS — combined is the gating metric per ROADMAP D-04 + SC-3.

JSON `metadata.pass` is `True` if combined PASSES, `False` otherwise. Rendered as ✓ PASS (green badge) / ✗ FAIL (red badge) in the report.

### D-17 — Empty-state copy

- `/backtest` with no runs yet: "No backtest runs yet. Use the form above or run `python -m backtest` from CLI."
- `/backtest?history=true` with no runs: same copy.
- POST `/backtest/run` with insufficient yfinance data (e.g. instrument not yet listed 5y ago): bail with 400 + reason text. Never partial-run.

### D-18 — Performance budget

Backtest run target: <60s for 5y × 2 instruments on droplet (1 vCPU). Profile target: <30s simulator (Phase 1 indicators are vectorized); <5s data fetch with cache hit; <5s JSON write + render.

If the budget breaks at execute time, the executor must NOT silently swallow it — log a Rule-1 deviation, surface to operator, and either (a) optimize the inner loop or (b) accept the longer runtime with explicit user check-in.

## Files to modify / create

- **NEW DIR:** `backtest/`
  - `__init__.py` — constants
  - `data_fetcher.py` — yfinance + parquet cache (the ONE I/O exception per D-09)
  - `simulator.py` — pure bar-by-bar replay
  - `metrics.py` — pure aggregation (Sharpe / DD / win rate / expectancy / cum return)
  - `render.py` — pure HTML render
  - `cli.py` — argparse entry
  - `__main__.py` — dispatch
- **NEW:** `web/routes/backtest.py` — four route handlers
- `web/app.py` — mount `app.use('/backtest', ...)` adjacent to existing routes
- `tests/test_signal_engine.py:480` — extend AST guard with `backtest/simulator.py`, `backtest/metrics.py`, `backtest/render.py`
- **NEW:** `tests/test_backtest_data_fetcher.py` — cache hit/miss, --refresh, parquet round-trip, `< 5y` data bail
- **NEW:** `tests/test_backtest_simulator.py` — replay determinism (same seed bars produce same trades), trailing stop + pyramid behavior reuses sizing_engine, signal-change exit reasons, NaN-safe
- **NEW:** `tests/test_backtest_metrics.py` — Sharpe formula, max DD computation, win rate, expectancy, cum return; parametrize edge cases (zero trades, all losses, all wins)
- **NEW:** `tests/test_backtest_render.py` — HTML structure, three-tab layout, Chart.js script tag presence, override form HTML, history table + overlay chart, empty-state copy
- **NEW:** `tests/test_backtest_cli.py` — argparse parsing, JSON write path, exit code 0 on PASS / 1 on FAIL, log line format
- **NEW:** `tests/test_web_backtest.py` — GET /backtest happy path, GET ?history=true, GET ?run=<filename> path-traversal guard, POST /backtest/run override form, cookie auth on all paths
- **NEW:** `tests/fixtures/backtest/golden_report.json` — small reference report for render tests
- `requirements.txt` — add `pyarrow` if not already pinned (research confirms)
- `.gitignore` — add `.planning/backtests/data/` (parquet cache)

## Out of scope (don't modify)

- `signal_engine.py` / `sizing_engine.py` — Phase 23 reuses them as-is per D-10
- `state_manager.py` — backtests don't touch state.json
- `notifier.py` — no email integration for backtests in v1.2 (deferred)
- `dashboard.py` — untouched per D-07
- `main.py` — daily run unaffected by backtest module

## Risk register

| Risk | Mitigation |
|------|-----------|
| `pyarrow` adds ~30MB to the install | RESEARCH confirms whether pyarrow is already pulled in via pandas or another existing dep. If not, add to requirements.txt; cost is acceptable for the cache speedup. |
| 5y × 2 × bar-by-bar compute exceeds 30s budget on droplet | Phase 1 indicators are vectorized via pandas; the simulator wraps existing helpers. RESEARCH benchmarks expected. If budget breaks: optimize inner loop OR document longer runtime with operator check-in. |
| POST /backtest/run timeout on uvicorn 60s default | D-14 calls out the risk; mitigation = parquet cache for sub-second data fetch + vectorized simulator. If still tight, defer async-job pattern to v1.3+. |
| Backtest history page slowness with 100+ JSON files | D-06 caps overlay chart at 10 most recent runs; table paginates server-side. Older runs accessible via `?run=<filename>` direct link. |
| Path traversal via `/backtest?run=<filename>` | Validate filename against `os.listdir('.planning/backtests/')` whitelist before reading. Reject any `..` / `/` / absolute paths. Test asserts. |
| Strategy version logic changes mid-run (operator bumps `STRATEGY_VERSION` while a backtest is running) | Read `system_params.STRATEGY_VERSION` ONCE at run start, embed in metadata. Any subsequent bump is recorded by the next run. |
| yfinance returns < 5y data for an instrument | Bail at fetch time with explicit error: `[Backtest] FAIL <symbol> only has N years of data; need 5`. Don't proceed with partial. |
| Concurrent POST /backtest/run from two browser tabs | Acceptable: each writes its own timestamped JSON file. Operator sees both runs in history. No state.json contention (backtests are isolated artifacts). |
| Operator overrides produce nonsensical values (e.g. negative cost) | Server-side validation: `initial_account_aud > 0`, `cost_spi_aud >= 0`, `cost_audusd_aud >= 0`. Reject with 400 per Phase 19 D-22 codebase convention (web/app.py:174-177 global handler). |
| Two simultaneous CLI runs collide on cache file | Cache filename includes from/to dates — different runs with different windows have different files. Same-window concurrent runs would race on the parquet write; tolerable since the second write wins and both reads are idempotent (same data). |
| Chart.js 4.4.6 CDN unavailable | Phase 5 already accepts this risk. Same `<script src=...>` pattern reused. If CDN fails, the page renders but chart areas are blank — not a crash. |
| Tampered cache file | Parquet is a binary columnar format with strict typed schema (no eval / code paths) — safer than CSV+pandas eval-on-read or pickle. Cache filename is operator-controlled; re-fetch via `--refresh` is the recovery path. |

## Verification (what proves the phase shipped)

1. `python -m backtest --years 5` runs to completion in <60s, prints `[Backtest] PASS` (or FAIL) summary, writes JSON to `.planning/backtests/v1.2.0-<timestamp>.json`.
2. JSON file contains `metadata`, `metrics`, `equity_curve`, `trades` per D-05 schema.
3. JSON `metadata.strategy_version` matches `system_params.STRATEGY_VERSION`.
4. CLI exit code = 0 on PASS, 1 on FAIL.
5. `--refresh` flag forces re-fetch despite a cached parquet file.
6. `GET /backtest` (with valid cookie session) returns 200 with HTML containing three tab containers (`<div data-tab="spi200">`, `<div data-tab="audusd">`, `<div data-tab="combined">`), a metrics table, and the operator override form.
7. `GET /backtest?history=true` returns 200 with a history table AND a Chart.js overlay container.
8. `GET /backtest?run=v1.2.0-XXX.json` returns the specified run; `GET /backtest?run=../../etc/passwd` returns 400 (path traversal guard).
9. `POST /backtest/run` form-encoded `{initial_account_aud: 5000, cost_spi_aud: 6.0, cost_audusd_aud: 5.0}` runs the simulation, writes a new JSON with the override values in metadata, redirects to `/backtest`.
10. Without auth cookie: `GET /backtest` redirects to `/login` (browser); `curl /backtest` returns 401 plain (Phase 16.1 D-04..D-07).
11. Hex-boundary: `grep -E "^import state_manager|^from state_manager|^import notifier|^from notifier|^import dashboard|^from dashboard|^import main\b|^from main" backtest/simulator.py backtest/metrics.py backtest/render.py` returns ZERO matches. AST guard test extends to walk these three files.
12. `pytest tests/test_backtest_*.py tests/test_web_backtest.py tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent` all pass.
13. Log lines on CLI run match the `[Backtest] ...` format per D-11.
14. Pass criterion: when JSON `metrics.combined.cumulative_return_pct > 100.0`, JSON `metadata.pass == true` and HTML renders ✓ PASS green badge.

## Deferred ideas (out of v1.2 scope)

- **True walk-forward with parameter optimization** — current scope is fixed-constants in-sample replay. Walk-forward would rolling-window train→test→advance. v2.0 quant-research scope per SPEC.md.
- **CI gating on PASS criterion** — auto-block deploy if backtest FAILs. Useful but adds CI surface area; defer to v1.3+ when v1.2 is stable.
- **Backtest email notification** — email operator when a re-run flips from PASS to FAIL. Useful for STRATEGY_VERSION bumps; defer to v1.3+.
- **Sortino / Calmar / Information Ratio** — additional risk metrics. v1.3+ when needed.
- **Per-trade attribution** — which signal-vote conditions produced each P&L outcome. v1.3+ research-mode feature.
- **Multi-strategy comparison overlay** — compare two STRATEGY_VERSIONS side-by-side on the same chart. v1.3+ when there are 3+ versions worth comparing.
- **CSV export of trade log** — one-click CSV download from /backtest. v1.3+ research workflow.
- **Async job pattern for POST /backtest/run** — if the synchronous approach times out at scale, swap for a job-queue + progress-poll pattern. Defer until measured.

## Canonical refs

- `.planning/ROADMAP.md` §Phase 23 (success criteria 1-6, operator pass criterion D-04)
- `.planning/REQUIREMENTS.md` §BACKTEST-01..04
- `.planning/PROJECT.md` (operator + stack context)
- `SPEC.md` §v1.2+ Long-Term Roadmap (operator brainstorm 2026-04-29 — backtest gate rationale)
- `CLAUDE.md` — log prefix `[Backtest]` (NEW for this phase), contract specs D-11/D-13
- `.planning/phases/22-strategy-versioning-audit-trail/22-CONTEXT.md` D-04, D-05 (STRATEGY_VERSION tagging precedent)
- `.planning/phases/19-paper-trade-ledger/19-CONTEXT.md` D-04, D-22 (cost model contrast — Phase 19 = half/half ledger; Phase 23 = full-on-exit simulator); D-22 (400 status code convention)
- `.planning/phases/17-per-signal-calculation-transparency/17-CONTEXT.md` D-08, D-09, D-10 (state shape, hex-boundary precedent)
- `.planning/phases/16.1-phone-friendly-auth-ux-for-dashboard-access/16.1-CONTEXT.md` D-04..D-07 (cookie-session auth on web routes)
- `.planning/phases/5-...-CONTEXT.md` (Chart.js 4.4.6 UMD precedent — first dashboard chart; mirror script-tag + container pattern)
- `.planning/phases/2-sizing-engine/...` (Phase 2 D-12 stateless pyramid invariant; D-13 cost model; D-15 entry-ATR anchor)
- `.planning/phases/1-...-CONTEXT.md` (Phase 1 indicator constants — backtest reuses verbatim per D-10)
- `signal_engine.py` `compute_indicators` + `get_signal` (Phase 1 — reuse verbatim)
- `sizing_engine.py` `step` (Phase 2 — reuse verbatim per D-10)
- `system_params.py` `STRATEGY_VERSION` constant (Phase 22 — embed in metadata per D-13)
- `web/routes/paper_trades.py` (Phase 19 — adapter pattern + Form-encoded route precedent + 400 status convention)
- `tests/test_signal_engine.py:480, 593, 595` (forbidden-imports AST guard — extend per D-09)
- `~/.claude/LEARNINGS.md` G-44 (HTMX form enctype trap — POST /backtest/run uses standard URL-encoded form)
- `~/.claude/LEARNINGS.md` G-45 (two-phase commit pattern — applies if any backtest path needs read-eval-write coordination, but unlikely in a write-once-per-run isolated artifact)
- `.claude/LEARNINGS.md` 2026-04-27 (hex-boundary primitives-only contract)
- `.claude/LEARNINGS.md` 2026-05-01 (`mutate_state` non-reentrancy — not applicable here since backtests don't touch state.json, but worth knowing)
