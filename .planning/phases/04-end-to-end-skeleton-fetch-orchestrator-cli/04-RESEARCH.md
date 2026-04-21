# Phase 4: End-to-End Skeleton — Fetch + Orchestrator + CLI — Research

**Researched:** 2026-04-21
**Domain:** yfinance I/O integration, stdlib argparse orchestration, orchestrator wire-up of Phase 1 + Phase 2 + Phase 3
**Confidence:** HIGH (all stack claims verified against the installed yfinance 1.2.0 and the actual Phase 1/2/3 module source; a couple of argparse-ergonomics claims are MEDIUM and flagged inline)

## Summary

Phase 4 wires a real yfinance fetch through the already-complete pure-math engines (Phase 1 indicators, Phase 2 sizing/exits/pyramiding, Phase 3 state persistence) behind a stdlib argparse CLI. No email, no dashboard, no schedule loop — those land in Phases 5/6/7. The research reveals one non-trivial yfinance surprise: **v1.2.0 `yf.download()` returns a MultiIndex-columned DataFrame by default with alphabetised column order, even for single tickers**, and it does NOT raise on invalid/empty symbols — it silently returns an empty DataFrame and logs to stderr. `yf.Ticker(sym).history()` is the cleaner API: flat column index in the conventional OHLCV order, `actions=False` kwarg strips Dividends/Stock Splits, and it respects `timeout=10`. Using `Ticker.history()` plus a bespoke retry loop around a narrow set of exceptions (YFRateLimitError, ReadTimeout, ConnectionError, plus empty-frame-treated-as-failure) is the path the planner should pick.

Argparse mutex groups are too coarse for the locked D-05 semantics — a single post-parse `parser.error()` check is cleaner. `logging.basicConfig` MUST be called with `force=True` in Phase 4 or pytest-captured handlers will silently win. Test strategy: monkeypatch `data_fetcher.yf.Ticker` at the import site (NOT at the yfinance package — this matters because Phase 4 tests import `data_fetcher` which already bound the `yf` name at module-import time).

All three upstream module APIs (signal_engine, sizing_engine, state_manager) are stable and fully readable; there are no surprises at the boundary, but a handful of subtle contracts (`gross_pnl` must be raw price-delta not `ClosedTrade.realised_pnl`; `record_trade` does not take a symbol separately — it reads `trade['instrument']`; `append_warning` takes positional `source, message` NOT a dict) need to be respected by the orchestrator translator helper.

**Primary recommendation:** Build `data_fetcher.py` around `yfinance.Ticker(symbol).history(period=f'{days}d', interval='1d', auto_adjust=True, actions=False, timeout=10)` wrapped in a fixed 10-second-backoff retry loop over `(YFRateLimitError, requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError, ValueError-on-empty-frame)`. Orchestrator uses `Ticker.history` NOT `yf.download`. Save recorded fixtures via `df.to_json(orient='split', date_format='iso')` for lossless round-trips. CLI uses post-parse `parser.error()` for `--reset` exclusivity. `logging.basicConfig(..., force=True)` at the top of `main()`.

## User Constraints (from CONTEXT.md)

### Locked Decisions (D-01..D-15)

Copied verbatim from `04-CONTEXT.md <decisions>` block. All 15 decisions are locked; research investigates HOW to implement them, not WHETHER.

- **D-01:** New module `data_fetcher.py` at repo root owns all yfinance I/O. Public API: `fetch_ohlcv(symbol: str, days: int = 400, retries: int = 3, backoff_s: float = 10.0) -> pd.DataFrame`. Returns a DataFrame with columns `[Open, High, Low, Close, Volume]` and a DatetimeIndex in Australia/Perth. Raises `DataFetchError` (custom exception) after retries exhaust. `data_fetcher.py` is the new I/O hex (analogous to `state_manager.py`). It imports `yfinance`, `requests` (fallback), `time` (sleep), `pandas`, `system_params`. It MUST NOT import `signal_engine`, `sizing_engine`, `state_manager`, `main`, `notifier`. The `TestDeterminism::test_forbidden_imports_absent` AST guard gains a `FORBIDDEN_MODULES_DATA_FETCHER` entry.
- **D-02:** Hybrid test strategy — recorded JSON fixtures + hand-built DataFrames. Canonical happy-path fixture: one committed JSON per instrument at `tests/fixtures/fetch/{symbol_slug}_400d.json`, captured by `tests/regenerate_fetch_fixtures.py` (mirror of Phase 1's `regenerate_goldens.py`). Scenario/error tests use hand-built DataFrames or monkeypatch `yfinance`.
- **D-03:** Any instrument fetch failure after 3 retries hard-fails the whole run. Log `[Fetch] ERROR ...`, write NO state, exit 2.
- **D-04:** stdlib `argparse` for CLI parsing — no new dependency.
- **D-05:** Strict flag-combination validation. `--reset` is exclusive with all other flags (error, exit 2). `--test + --force-email` is ALLOWED. `--once` and default-mode are mutex by construction (default == --once in Phase 4).
- **D-06:** `--force-email` is parsed in Phase 4 but logs "not wired until Phase 6" and returns exit 0.
- **D-07:** Default `python main.py` in Phase 4 == single run + exit (same as `--once`). Schedule loop wired in Phase 7.
- **D-08:** `signal_as_of` stored per-instrument under `state['signals'][symbol]['signal_as_of']`. No schema bump (nested key under existing `signals` dict). Backward-compat: older state file without the key is treated as "stale unknown" — warning logged, run continues.
- **D-09:** Stale threshold = `>3 calendar days` for both instruments. `(today_awst - signal_as_of).days > 3` triggers DATA-05 warning.
- **D-10:** Stale warning path: console log + `state_manager.append_warning(...)`. Format: `[Fetch] WARN ^AXJO stale: signal_as_of=2026-04-15 is 6d old (threshold=3d)`.
- **D-11:** Single atomic `save_state` at end of `run_daily_check()`. `--test` path never calls it (structural guarantee).
- **D-12:** `main.py` translates `StepResult.closed_trade` → `record_trade` dict via local `_closed_trade_to_record` helper. Preserves hex-lite boundaries.
- **D-13:** `signal_as_of` = `df.index[-1].strftime('%Y-%m-%d')` — no timezone conversion. `run_date` = `datetime.now(Australia/Perth)` separately.
- **D-14:** Per-instrument log block + run-summary footer, plain text with `[Prefix]` convention per CLAUDE.md.
- **D-15:** Python stdlib `logging`, configured once in `main.py` via `basicConfig(level=INFO, format='%(message)s', stream=sys.stderr)`.

### Claude's Discretion

Copied verbatim from `04-CONTEXT.md <decisions> §Claude's Discretion`. These are the planner/executor's judgement calls:

- Exact exception class hierarchy in `data_fetcher.py` (one `DataFetchError` vs `DataFetchError`+`ShortFrameError`+`StaleFrameError`).
- Exact argparse subcommand vs flag structure (all-flags is the simpler baseline).
- Whether `data_fetcher.fetch_ohlcv` takes `start/end` or `days=400` (prefer `days` per roadmap; surface calendar-day vs trading-day ambiguity).
- Retry policy jitter (fixed 10s baseline per DATA-03; jitter may help avoid rate-limit synchronisation).
- How `run_daily_check()` is organised internally (one function vs class vs dispatch table). Name is locked.
- How `_closed_trade_to_record` handles `pyramid_level_at_close` (source from position at close, or from `StepResult`).
- Test file organisation (planner split or single file).
- Whether `regenerate_fetch_fixtures.py` is a single plan task or Wave 0 scaffold.
- Logging format whitespace + rounding.

### Deferred Ideas (OUT OF SCOPE)

Copied verbatim from `04-CONTEXT.md <deferred>`. Phase 4 must NOT implement any of these:

- `--email-preview` / `--dry-run-email` CLI flag (Phase 6).
- JSON-Lines structured logs (revisit Phase 7 if needed).
- Per-instrument stale thresholds.
- Schema v2 with explicit typed `signal_as_of` field.
- `vcrpy` / record-replay HTTP testing.
- Dedicated `logger.py` wrapper.
- Retry jitter / exponential backoff beyond flat 10s.
- Schedule-loop "already ran today" idempotency guard (Phase 7).

## Project Constraints (from CLAUDE.md)

Consolidated from `./CLAUDE.md` — these are non-negotiable project-wide rules Phase 4 must honour:

| Directive | Phase 4 implication |
|-----------|---------------------|
| 2-space indent, single quotes, PEP 8 via `ruff` | `data_fetcher.py` + `main.py` follow existing signal_engine.py / state_manager.py style |
| snake_case functions, UPPER_SNAKE constants | `fetch_ohlcv`, `run_daily_check`, `_closed_trade_to_record` |
| Log prefixes `[Signal] [State] [Email] [Sched] [Fetch]` | Must be used verbatim; `[Fetch]` is NEW in Phase 4 |
| Signal integers `LONG=1 SHORT=-1 FLAT=0` | Orchestrator imports from signal_engine |
| Dates ISO `YYYY-MM-DD`; times AWST in user-facing output | `signal_as_of` (market-local bar date), `run_date` (Perth wall-clock) — NEVER substitute |
| Instrument keys `SPI200`, `AUDUSD` | state.json keys; yfinance symbols `^AXJO`, `AUDUSD=X` need mapping |
| `signal_engine.py ↔ state_manager.py` MUST NOT import each other | `main.py` is the only cross-hex importer |
| `sizing_engine.py` / `system_params.py` MUST NOT import `state_manager`, `notifier`, `dashboard`, `main`, `requests`, `datetime`, `os` | Enforced by AST blocklist in `tests/test_signal_engine.py::TestDeterminism` |
| All pure functions take plain args, return plain values — no `datetime.now()`, no env-var reads inside them | Phase 4 `run_date` computed in `main.py`, passed as scalar downstream |
| `state.json` writes atomic via tempfile + fsync + `os.replace` | Phase 3 `save_state` handles; Phase 4 just calls it once |
| `--test` is structurally read-only | Phase 4 splits compute from persist so `--test` path cannot reach `save_state` |
| Email sends NEVER crash workflow | N/A in Phase 4; `--force-email` logs stub per D-06 |

## Phase Requirements

| ID | Description (REQUIREMENTS.md §Data / §CLI / §Error) | Research Support |
|----|-----------------------------------------------------|------------------|
| DATA-01 | Fetch 400d daily OHLCV for `^AXJO` via yfinance | `Ticker('^AXJO').history(period='400d', interval='1d')` verified — returns 400 bars, 5 clean columns with `actions=False` (§Standard Stack §yfinance call shape) |
| DATA-02 | Fetch 400d daily OHLCV for `AUDUSD=X` via yfinance | Same as DATA-01 with `AUDUSD=X` — columns identical, index tz differs (see §Common Pitfalls §Pitfall 1) |
| DATA-03 | Retry 3× with 10s backoff on failure | Wrap `Ticker.history()` in `for attempt in range(retries):` with `time.sleep(backoff_s)` on each caught exception (§Code Examples §Example 1) |
| DATA-04 | Empty/short frame (`len < 300`) hard-fails — no state written | Check `len(df) < 300` after fetch → raise `ShortFrameError` caught by top-level boundary → exit 2 without calling save_state (§Common Pitfalls §Pitfall 6) |
| DATA-05 | Stale last bar is flagged as warning (not fatal) | `(today_awst.date() - df.index[-1].date()).days > 3` → `append_warning(state, 'fetch', f'stale: ...')` + console log WARN (§Code Examples §Example 5) |
| DATA-06 | `signal_as_of` logged separately from `run_date` | `signal_as_of = df.index[-1].strftime('%Y-%m-%d')` (market-local); `run_date = datetime.now(pytz.timezone('Australia/Perth'))`; both in every per-instrument log block (§Code Examples §Example 4) |
| CLI-01 | `--test` runs full check + prints report + NO state mutation | Structural: `run_daily_check(args)` returns before step 8 (`save_state`) when `args.test` is True. Tested via `os.stat(state_json).st_mtime` unchanged across call (§Testing Patterns §§mtime assertion) |
| CLI-02 | `--reset` reinitialises after confirmation | `reset_state()` → `save_state()` → exit 0. Confirmation prompt via `input('Type YES to confirm reset: ')` on stdin (§Architecture §§Reset path) |
| CLI-03 | `--force-email` sends today's email immediately | Phase 4: stub `[Email] --force-email received; notifier wiring arrives in Phase 6`, exit 0 (D-06) |
| CLI-04 | `--once` runs one daily check and exits (GHA mode) | In Phase 4 this is an alias for default; log `[Sched] One-shot mode (scheduler wiring lands in Phase 7)` |
| CLI-05 | Default `python main.py` runs immediately then enters schedule loop | Phase 4 deferred to Phase 7. Default in Phase 4 = single run + exit (D-07). Log `[Sched] One-shot mode (scheduler wiring lands in Phase 7)` (D-07) |
| ERR-01 | yfinance failure after 3 retries sends error email + exits gracefully | Phase 4 scope: log `[Fetch] ERROR ...` + exit non-zero. Error email is Phase 6/8 scope (ERR-04 is Phase 8) |
| ERR-06 | Console logs use structured format readable in Replit/GHA | Per-instrument `[Prefix]` blocks separated by blank line + run-summary footer (D-14) |

## Architectural Responsibility Map

Phase 4 is Python stdlib/CLI; there is no browser/frontend/CDN tier. Still, the orchestrator crosses several architectural boundaries.

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| yfinance HTTPS fetch | I/O hex (`data_fetcher.py`) | — | New module; only module in Phase 4 that opens network sockets. Matches state_manager's "one-module-one-concern" posture. |
| CLI parsing + dispatch | Orchestrator (`main.py`) | — | `argparse` is stdlib; flag validation is pure dispatch, not business logic. |
| Structured logging | Orchestrator (`main.py`) | All callers via `logging.getLogger(__name__)` | `basicConfig` called once in `main()`; data_fetcher and future modules use module-level logger. |
| Signal computation | Pure-math hex (`signal_engine.py`) | Orchestrator calls | No change — Phase 4 consumes, does not modify. |
| Sizing / exit / pyramid | Pure-math hex (`sizing_engine.py`) | Orchestrator calls | No change — Phase 4 consumes `step()`. |
| State read / write / warn | I/O hex (`state_manager.py`) | Orchestrator calls | No change — Phase 4 is Phase 3's first real consumer. |
| ClosedTrade → trade dict translation | Orchestrator (`main.py`) | — | D-12 pins this: `_closed_trade_to_record` is the hex-boundary adapter. Neither engine knows the other's dataclass/dict shape. |
| Timezone handling | Orchestrator (`main.py`) | — | `run_date = datetime.now(Australia/Perth)`. Market-local bar date stays as yfinance-returned (D-13). |

## Standard Stack

### Core (all already pinned in requirements.txt)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `yfinance` | 1.2.0 (pinned) | OHLCV fetch from Yahoo Finance | `[VERIFIED: requirements.txt line 4, .venv inspection]` SPEC.md specifies yfinance as the data source; already pinned by Phase 1. v1.2.0 is the most recent stable per GitHub CHANGELOG.rst — no reason to bump. |
| `pandas` | 2.3.3 (pinned) | DataFrame return type | `[VERIFIED: requirements.txt line 2]` yfinance returns `pd.DataFrame`; signal_engine already imports pandas. |
| `numpy` | 2.0.2 (pinned) | Indirect via pandas; unused directly | `[VERIFIED: requirements.txt line 1]` No direct use in data_fetcher or main. |
| `pytest` | 8.3.3 (pinned) | Test runner | `[VERIFIED: requirements.txt line 3]` Already used by Phases 1/2/3. |

### Supporting (new additions for Phase 4)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest-freezer` | 0.4.9 (latest on PyPI as of 2026-04-21) | Freeze `datetime.now(Australia/Perth)` in orchestrator tests | `[VERIFIED: .venv/bin/pip install --dry-run]` Phase 1 D-15 noted pytest-freezer would land in Phase 4. Add to requirements.txt in Wave 0. `pytest-freezer` is a pytest plugin that wraps `freezegun` (which Phase 3 explicitly avoided by accepting `now=None` injection). Phase 4 orchestrator's `run_date = datetime.now(Australia/Perth)` is a bare `datetime.now()` call (per CLAUDE.md "no datetime.now() in pure layers, orchestrator only"), so we either (a) inject `now=None` through every call the way Phase 3 did, or (b) use `@pytest.mark.freeze_time('2026-04-21 09:00:03+08:00')`. Recommend (b) — less invasive for a thin orchestrator. |
| `pytz` | (already available via yfinance transitive dep; if needed explicitly, pin 2025.2) | `Australia/Perth` timezone | `[ASSUMED]` PROJECT.md stack lists pytz explicitly. If the planner wants to avoid a new pin, Python stdlib `zoneinfo` (used by state_manager.py per `import zoneinfo`) is equivalent and already in use. **Recommendation: use `zoneinfo.ZoneInfo('Australia/Perth')` matching state_manager.py, NOT pytz**, to stay consistent and avoid an import. This deviates from PROJECT.md but state_manager.py already set the precedent. |
| `requests` | (yfinance transitive; not pinned separately) | Source of `requests.exceptions.*` raised by yfinance internals | `[VERIFIED: yfinance 1.2.0 source]` Needed to catch `ReadTimeout`/`ConnectionError` in the retry loop. Already transitively installed via yfinance. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `argparse` | `click` or `typer` | `[CITED: PROJECT.md §Constraints]` PROJECT.md explicitly forbids adding frameworks. argparse meets all 5 CLI flag needs. Rejected. |
| `yf.download(sym, ...)` | `yf.Ticker(sym).history(...)` | `[VERIFIED: runtime inspection of yfinance 1.2.0]` `yf.download` returns a MultiIndex-column DataFrame by default (even single ticker), with columns alphabetised (`Close, High, Low, Open, Volume`). `Ticker.history()` returns a flat Index in the conventional `Open, High, Low, Close, Volume` order. Use **Ticker.history**. |
| `freezegun` directly | `pytest-freezer` | `[CITED: pytest-freezer README]` `pytest-freezer` is a thin pytest wrapper around freezegun adding the `@pytest.mark.freeze_time` marker + `freezer` fixture. Same dependency graph. Use pytest-freezer for pytest integration. |
| Recorded fixtures via `vcrpy` (HTTP cassettes) | Recorded DataFrames via `df.to_json(orient='split', date_format='iso')` | D-02 rejects vcrpy. JSON round-trip is lossless for float64 DataFrames with DatetimeIndex when `orient='split'` and `date_format='iso'` — no intermediate HTTP layer to mock. Simpler. |
| `pytz.timezone('Australia/Perth')` | `zoneinfo.ZoneInfo('Australia/Perth')` | `[VERIFIED: state_manager.py line 59]` state_manager.py already uses `zoneinfo`. Consistency > PROJECT.md's `pytz` mention. Both produce identical UTC+8 no-DST behavior for Perth. |

**Installation (Wave 0 scaffold):**

```bash
# pytest-freezer added to requirements.txt; pin to latest as of research date
pip install pytest-freezer==0.4.9
```

**Version verification** (performed 2026-04-21):

- `yfinance` — `[VERIFIED: .venv/bin/pip show yfinance → 1.2.0]` matches requirements.txt pin. Release notes (GitHub CHANGELOG.rst): 1.2.0 is "update exchange maps for equities and mutual funds" + "handle Pandas to_numpy() returning read-only". No breaking API changes since 0.2.47 when `multi_level_index` was added. `YFRateLimitError` added at 0.2.52.
- `pytest-freezer` — `[VERIFIED: pypi.org lookup via --dry-run]` 0.4.9 latest. Pulls in `freezegun>=1.1` (1.5.5) and `python-dateutil>=2.7` (2.9.0.post0) which are both already transitively installed.

## Architecture Patterns

### System Architecture Diagram

Data flow for a single `python main.py --once` invocation:

```
  OPERATOR                 FILESYSTEM                  YAHOO FINANCE
     │                         │                            │
     ▼                         │                            │
  python main.py --once        │                            │
     │                         │                            │
     ▼                         │                            │
  argparse.parse_args ──► post-parse flag validation ──► parser.error() (exit 2 on bad combo)
     │                         │                            │
     ▼                         │                            │
  logging.basicConfig(force=True)  [Sched] Run 2026-04-21 09:00:03 AWST mode=once
     │                         │                            │
     ▼                         │                            │
  run_daily_check(args)        │                            │
     │                         │                            │
     ├── state = load_state() ◄──── state.json              │
     │     (creates fresh dict if file missing per B-3)     │
     │                         │                            │
     ├── for symbol in [^AXJO, AUDUSD=X]:                   │
     │     │                   │                            │
     │     ├── df = data_fetcher.fetch_ohlcv(symbol, 400, 3, 10.0)
     │     │    │              │          │                 │
     │     │    └──retry loop──┼──► yf.Ticker(sym).history ─┘
     │     │                   │          │ (HTTPS + exchange tz, timeout=10)
     │     │                   │          ▼
     │     │                   │     DataFrame [Open,High,Low,Close,Volume]
     │     │                   │     DatetimeIndex in exchange-local tz
     │     │                   │
     │     ├── if len(df) < 300: raise ShortFrameError    (DATA-04)
     │     ├── signal_as_of = df.index[-1].strftime('%Y-%m-%d')      (D-13)
     │     ├── if (run_date.date() - signal_as_of).days > 3:
     │     │    log [Fetch] WARN + queue append_warning (D-09, D-10)
     │     │
     │     ├── df = signal_engine.compute_indicators(df)
     │     ├── scalars = signal_engine.get_latest_indicators(df)
     │     ├── new_signal = signal_engine.get_signal(df)
     │     ├── old_signal = state['signals'][symbol].get('signal', 0)  [D-08 nested]
     │     ├── position = state['positions'].get(symbol)
     │     │
     │     ├── result: StepResult = sizing_engine.step(
     │     │    position, bar, scalars, old_signal, new_signal,
     │     │    account=state['account'], multiplier=SPI_MULT or AUDUSD_NOTIONAL,
     │     │    cost_aud_open=SPI_COST_AUD/2 or AUDUSD_COST_AUD/2)
     │     │
     │     ├── state['positions'][symbol] = result.position_after   (None if flat)
     │     ├── state['signals'][symbol] = {'signal': new_signal,
     │     │    'signal_as_of': signal_as_of, 'as_of_run': run_date_iso}  (D-08 nested)
     │     │
     │     └── for ct in [result.closed_trade] if result.closed_trade else []:
     │            trade = _closed_trade_to_record(ct, symbol, mult, cost_aud)  (D-12)
     │            state = state_manager.record_trade(state, trade)
     │                         │
     │                         ▼
     │                    state.account adjusted
     │                    trade_log appended (copy with net_pnl — D-20)
     │                    positions[symbol] = None
     │
     ├── equity = state['account'] + sum(compute_unrealised_pnl(...) for active pos)
     ├── update_equity_history(state, run_date_iso, equity)
     ├── flush queued warnings: for (src, msg) in queue: append_warning(state, src, msg)
     ├── state['last_run'] = run_date_iso
     │
     ├── if args.test: print footer "state_saved=false (--test)"; RETURN    (CLI-01)
     │   (structural guarantee: --test path never reaches save_state)
     │
     └── save_state(state)  [State] state.json saved (account=$X, trades=N, positions=M)
                                 │
                                 ▼
                             state.json (atomic tempfile + fsync + replace + fsync parent)
     │
     └── print run-summary footer [Sched] Run 2026-04-21 09:00:03 AWST done ...
```

### Recommended Project Structure

```
trading-signals/
├── main.py                           # NEW — orchestrator + CLI (Phase 4)
├── data_fetcher.py                   # NEW — yfinance I/O hex (Phase 4)
├── signal_engine.py                  # Phase 1 (complete)
├── sizing_engine.py                  # Phase 2 (complete)
├── state_manager.py                  # Phase 3 (complete)
├── system_params.py                  # constants + Position TypedDict
├── requirements.txt                  # + pytest-freezer==0.4.9 in Wave 0
├── pyproject.toml                    # ruff/pytest config
├── tests/
│   ├── conftest.py                   # (currently empty; may grow)
│   ├── test_data_fetcher.py          # NEW — TestFetch (happy/retry/empty/stale)
│   ├── test_main.py                  # NEW — TestOrchestrator + TestCLI
│   ├── regenerate_fetch_fixtures.py  # NEW — offline record script
│   ├── fixtures/
│   │   └── fetch/
│   │       ├── axjo_400d.json        # committed recorded fixture (D-02)
│   │       └── audusd_400d.json      # committed recorded fixture (D-02)
│   ├── test_signal_engine.py         # Phase 1 — AST blocklist extended in Wave 0
│   ├── test_sizing_engine.py         # Phase 2
│   └── test_state_manager.py         # Phase 3
```

### Pattern 1: I/O hex module with retry + narrow exception catch

Mirrors `state_manager.py`'s hexagonal-lite discipline. The module does ONE thing (fetch), raises ONE domain exception, and has NO sibling-hex imports.

**What:** `data_fetcher.fetch_ohlcv` wraps `yfinance.Ticker.history` in a 3-retry / 10s-backoff loop, catching a *narrow* set of exceptions that represent transient failures.

**When to use:** Any external HTTPS call. Pattern reused from state_manager.py's atomic-write discipline.

**Example:**

```python
# data_fetcher.py — source: synthesised from yfinance 1.2.0 runtime inspection + CLAUDE.md hex rules
import logging
import time

import pandas as pd
import requests.exceptions
import yfinance as yf
from yfinance.exceptions import YFRateLimitError

from system_params import STATE_FILE  # noqa: F401 — illustrative; not actually needed

logger = logging.getLogger(__name__)

# Retry-eligible exceptions — narrow per CLAUDE.md Pitfall 4 (bare-catch anti-pattern)
_RETRY_EXCEPTIONS = (
  YFRateLimitError,
  requests.exceptions.ReadTimeout,
  requests.exceptions.ConnectionError,
)


class DataFetchError(Exception):
  '''Raised when a symbol's fetch fails after all retries exhaust.

  Caught at the top of run_daily_check; aborts the whole run (D-03).
  '''


def fetch_ohlcv(
  symbol: str, days: int = 400, retries: int = 3, backoff_s: float = 10.0,
) -> pd.DataFrame:
  '''DATA-01/02/03: fetch daily OHLCV for `symbol` via yfinance.

  Returns a DataFrame with exactly columns [Open, High, Low, Close, Volume]
  and a DatetimeIndex in exchange-local tz (NOT converted to Perth — D-13).

  Uses Ticker.history NOT yf.download per RESEARCH §Standard Stack. Passes
  actions=False to strip Dividends/Stock Splits columns. timeout=10 (matches
  yfinance's own default).

  Raises DataFetchError after `retries` attempts if yfinance keeps failing
  OR if the returned DataFrame is empty (invalid symbol case — yfinance
  does NOT raise on unknown symbols, it returns an empty frame + stderr log).
  '''
  last_err: Exception | None = None
  for attempt in range(1, retries + 1):
    try:
      ticker = yf.Ticker(symbol)
      df = ticker.history(
        period=f'{days}d', interval='1d',
        auto_adjust=True, actions=False, timeout=10,
      )
      if df.empty:
        # yfinance empty-frame convention (invalid symbol, no data): treat as
        # retry-eligible on first attempt; after retries exhaust, caller gets
        # DataFetchError and the orchestrator hard-fails (D-03).
        raise ValueError(f'yfinance returned empty DataFrame for {symbol}')
      # Strip to exactly the columns downstream expects — defensive against
      # yfinance adding new default columns in a future version.
      return df[['Open', 'High', 'Low', 'Close', 'Volume']]
    except (*_RETRY_EXCEPTIONS, ValueError) as e:
      last_err = e
      logger.warning(
        '[Fetch] %s attempt %d/%d failed: %s: %s',
        symbol, attempt, retries, type(e).__name__, e,
      )
      if attempt < retries:
        time.sleep(backoff_s)
  raise DataFetchError(
    f'{symbol}: retries exhausted after {retries} attempts; last error: '
    f'{type(last_err).__name__}: {last_err}',
  ) from last_err
```

### Pattern 2: Structural `--test` read-only guarantee

**What:** CLI-01 says `--test` must not mutate state.json. The CLAUDE.md directive is "enforced by structurally separating compute and persist" — not a runtime guard.

**How:** `run_daily_check(args)` mutates the in-memory `state` dict through all compute steps, then branches at the end:

```python
# main.py — the critical last 3 lines of run_daily_check
if args.test:
  logger.info('[Sched] --test mode: skipping save_state (state.json unchanged)')
  _print_run_summary(run_date, result_summary, state_saved=False)
  return 0
state_manager.save_state(state)
logger.info('[State] state.json saved (account=$%.2f, trades=%d, positions=%d)',
             state['account'], len(state['trade_log']),
             sum(1 for v in state['positions'].values() if v is not None))
_print_run_summary(run_date, result_summary, state_saved=True)
return 0
```

**Test pattern** (§Testing Patterns §Example mtime):

```python
# tests/test_main.py
def test_test_flag_leaves_state_json_mtime_unchanged(tmp_path, monkeypatch, freezer):
  # ... seed state.json with a fresh state ...
  state_json = tmp_path / 'state.json'
  state_manager.save_state(state_manager.reset_state(), path=state_json)
  mtime_before = state_json.stat().st_mtime_ns
  # monkeypatch data_fetcher.yf.Ticker to return a recorded DataFrame
  # run main.main(['--test'])
  mtime_after = state_json.stat().st_mtime_ns
  assert mtime_before == mtime_after, 'CLI-01: --test must NOT mutate state.json'
```

### Pattern 3: Timezone-aware `run_date` (D-13 separation)

```python
# main.py
from datetime import datetime
from zoneinfo import ZoneInfo

AWST = ZoneInfo('Australia/Perth')

def _compute_run_date() -> datetime:
  '''CLAUDE.md: run_date always in Australia/Perth. No DST in Perth.
  Orchestrator is the only module allowed to read the wall clock.
  '''
  return datetime.now(tz=AWST)

# Usage:
run_date = _compute_run_date()
run_date_iso = run_date.strftime('%Y-%m-%d')             # for state['last_run']
run_date_display = run_date.strftime('%Y-%m-%d %H:%M:%S AWST')  # for [Sched] log

# signal_as_of is SEPARATE and market-local (D-13):
signal_as_of = df.index[-1].strftime('%Y-%m-%d')         # NO timezone conversion
```

### Pattern 4: `_closed_trade_to_record` translator

```python
# main.py — the D-12 hex-boundary adapter
from sizing_engine import ClosedTrade

def _closed_trade_to_record(
  ct: ClosedTrade, symbol: str, multiplier: float, cost_aud: float,
  entry_date: str, run_date_iso: str,
) -> dict:
  '''D-12: translate Phase 2 ClosedTrade dataclass → Phase 3 record_trade dict.

  CRITICAL PITFALL (state_manager.py record_trade docstring):
    trade['gross_pnl'] MUST be raw price-delta P&L:
      (exit_price - entry_price) * n_contracts * multiplier  (LONG)
      (entry_price - exit_price) * n_contracts * multiplier  (SHORT)
    NOT ClosedTrade.realised_pnl (which already deducted the closing-half cost
    in sizing_engine._close_position). Passing realised_pnl as gross_pnl
    would double-count the close cost.

  record_trade validates all 11 fields per _validate_trade (D-15 + D-19):
    instrument, direction, entry_date, exit_date, entry_price, exit_price,
    gross_pnl, n_contracts, exit_reason, multiplier, cost_aud.
  '''
  direction_mult = 1.0 if ct.direction == 'LONG' else -1.0
  gross_pnl = direction_mult * (ct.exit_price - ct.entry_price) * ct.n_contracts * multiplier
  return {
    'instrument': symbol,                # 'SPI200' or 'AUDUSD' — NOT '^AXJO'
    'direction': ct.direction,           # 'LONG' or 'SHORT'
    'entry_date': entry_date,            # from the closing position's entry_date
    'exit_date': run_date_iso,           # today's AWST date
    'entry_price': ct.entry_price,
    'exit_price': ct.exit_price,
    'gross_pnl': gross_pnl,              # RAW price-delta, NOT ct.realised_pnl
    'n_contracts': ct.n_contracts,
    'exit_reason': ct.exit_reason,       # 'flat_signal'|'signal_reversal'|'stop_hit'|'adx_exit'
    'multiplier': multiplier,            # SPI_MULT or AUDUSD_NOTIONAL
    'cost_aud': cost_aud,                # SPI_COST_AUD or AUDUSD_COST_AUD (full round-trip)
  }
```

### Anti-Patterns to Avoid

- **`yf.download()` for single-ticker fetches:** returns MultiIndex columns by default even for one ticker; easily yields `df['Close']` → KeyError / tuple-key confusion. Use `yf.Ticker(sym).history()`.
- **Bare `except Exception` in retry loop:** masks real bugs (NameError in the fetch code, for example). Catch only the narrow `_RETRY_EXCEPTIONS` tuple + `ValueError` for empty-frame.
- **Retrying on invalid-symbol errors:** yfinance returns empty DataFrame (no raise) for invalid symbols. Retrying wastes 30s before failing. Current recommendation: treat empty as retry-eligible on first attempt (network hiccup possibility); hard-fail after all retries. Cheap insurance.
- **Calling `save_state` inside the for-instrument loop:** violates atomicity (D-11). Save exactly ONCE at end of `run_daily_check`.
- **Reading `state['signals'][symbol]` as bare int:** Phase 1–3 initialise `state['signals'] = {'SPI200': 0, 'AUDUSD': 0}` (flat int), but D-08 says Phase 4 nests it: `{'SPI200': {'signal': 0, 'signal_as_of': '...'}, ...}`. **Backward compat (D-08 explicit):** when reading, handle both int and dict; always write the nested dict. Warn if old format detected.
- **`logging.basicConfig` without `force=True`:** pytest and other plugins may have already added handlers; without `force=True`, the call is a silent no-op and your `format` + `stream` are ignored.
- **Using `df.index[-1]` tz-converted to AWST:** would shift some bar dates across the day boundary (e.g., `AUDUSD=X` bar at 17:00 Europe/London on a Friday maps to Saturday AWST). D-13 says use `df.index[-1].strftime('%Y-%m-%d')` directly — no tz conversion.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTPS fetch + cookie/CSRF/crumb dance for Yahoo | Custom `requests.get('https://query1.finance.yahoo.com/...')` | `yfinance.Ticker.history()` | yfinance handles Yahoo's undocumented crumb-cookie auth flow, retries it, and absorbs the frequent API shape changes. Hand-rolling broke twice in 2024 when Yahoo changed endpoints. |
| Timezone arithmetic (AWST, no DST) | `datetime.timedelta(hours=8)` | `zoneinfo.ZoneInfo('Australia/Perth')` (or pytz) | IANA tz database handles the (future, unlikely) case of Perth adopting DST. Already used by state_manager.py. |
| JSON atomic writes | `open('w').write(...)` | `state_manager.save_state()` | Phase 3 already owns this correctly — tempfile + fsync + os.replace + fsync(parent). Never re-implement in main.py. |
| Retry loop with exponential backoff | Hand-written while loop with time.sleep | Hand-written loop IS fine here — `tenacity` is overkill | D-04 forbids new deps. Flat 10s × 3 retries (DATA-03) is trivial; 8 lines of code. |
| CLI argument parsing | Hand-rolled `sys.argv` walker | `argparse` | stdlib. D-04 locks this. |
| CSV / JSON DataFrame round-trip for fixtures | Hand-rolled float32/64 serialiser | `pandas.DataFrame.to_json(orient='split', date_format='iso')` | `orient='split'` is the only orient that losslessly round-trips a DataFrame with DatetimeIndex. `to_csv` loses tz info; `to_parquet` adds a binary dep. Verified via:<br>```df_r = pd.read_json(path, orient='split'); pd.testing.assert_frame_equal(df, df_r)``` |
| Top-level exception-to-exit-code mapping | Custom sys.excepthook | `try: run_daily_check() ... except DataFetchError: exit(2); except ShortFrameError: exit(2); except Exception: log + exit(1)` in `main()` | Plain `try/except/sys.exit` at the top of `main()`. ERR-04 crash-email is explicitly Phase 8 scope. |

**Key insight:** Phase 4 is almost entirely an integration phase. Every building block already exists — the only truly new code is `data_fetcher.fetch_ohlcv`, the CLI parser, and the orchestrator. Over-engineering (retry libraries, DI frameworks, custom loggers) defeats the "thin orchestrator" discipline.

## Runtime State Inventory

Phase 4 is predominantly greenfield (`main.py` and `data_fetcher.py` are NEW) but does consume existing state. Mapped per category:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `state.json` at repo root. Current schema (post Phase 3): top-level `{schema_version, account, last_run, positions, signals, trade_log, equity_history, warnings}`. `signals` is currently `dict[str, int]`; D-08 changes it to `dict[str, dict]` with nested `{signal, signal_as_of, as_of_run}`. **No schema_version bump** (D-08). Backward-compat branch: orchestrator reads both shapes, writes new shape. | Code edit in `main.py` only — D-08 explicit. No data migration: a state.json with the old int-shape at `state['signals'][symbol]` is upgraded in-place on first Phase 4 run. Document the upgrade branch in a comment. |
| Live service config | None. No external service holds Phase 4 configuration. Resend (Phase 6) and GHA (Phase 7) are later. | None. |
| OS-registered state | None in Phase 4. `schedule` module state is in-process (Phase 7 concern). `GHA cron` is Phase 7. | None. |
| Secrets / env vars | None read by Phase 4 code paths. `.env` / python-dotenv stays dormant until Phase 6 (Resend). | None. Phase 4 adds NO env-var reads. Operator can pre-create `.env.example` in Wave 0 but not required. |
| Build artifacts / installed packages | `.venv/` already exists with Phase 1–3 pins. Wave 0 adds `pytest-freezer==0.4.9` to requirements.txt + re-`pip install -r`. | Re-install in Wave 0: `pip install -r requirements.txt`. No stale egg-info or compiled artifacts at this phase. |

**Verified by:** `ls /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/` (no .env, no node_modules, no stale build artifacts); `cat state_manager.py` lines 61–73 (state schema); `cat requirements.txt` (5 pins).

## Common Pitfalls

### Pitfall 1: yfinance column shape drift between `yf.download` and `Ticker.history`

**What goes wrong:** Happy path test with `yf.Ticker('^AXJO').history()` passes — columns are `[Open, High, Low, Close, Volume]`. Refactor swaps to `yf.download('^AXJO', ...)` "for consistency" — now columns are a MultiIndex `[('Close', '^AXJO'), ('High', '^AXJO'), ...]` and `df['Close']` returns a DataFrame not a Series. All downstream indicator math breaks.

**Why it happens:** `[VERIFIED: yfinance 1.2.0 runtime inspection]` `yf.download(multi_level_index=True)` is the default even for a single ticker (confirmed: `yf.download('AAPL', period='5d', multi_level_index=True).columns == MultiIndex([('Close', 'AAPL'), ('High', 'AAPL'), ('Low', 'AAPL'), ('Open', 'AAPL'), ('Volume', 'AAPL')])`). `yf.download` also returns columns in **alphabetical** order (`Close, High, Low, Open, Volume`), not the conventional OHLCV order.

**How to avoid:**
- Use `yf.Ticker(symbol).history(...)` exclusively in `data_fetcher.py`
- Defensive post-fetch slice: `df = df[['Open', 'High', 'Low', 'Close', 'Volume']]` normalises column order AND drops any yfinance-added columns (Dividends, Stock Splits) if `actions=False` is ever forgotten
- Add a test `test_fetch_ohlcv_returns_exact_columns` that asserts `list(df.columns) == ['Open', 'High', 'Low', 'Close', 'Volume']`

**Warning signs:** `KeyError: 'Close'` in compute_indicators; `TypeError: cannot convert the series to <class 'float'>` in get_latest_indicators (returning a multi-column slice).

### Pitfall 2: yfinance silent empty-frame on invalid symbol

**What goes wrong:** `python main.py --once` with a typoed env-var like `SPI_SYMBOL='AXJO'` (missing `^`) runs through the fetch — yfinance prints `$AXJO: possibly delisted; no price data found` to **stderr** and returns an empty DataFrame. With the fetch's empty-frame → `ValueError` guard (§Pattern 1), the retry loop burns 30s and then hard-fails — correct behaviour but slow.

**Why it happens:** `[VERIFIED: yfinance 1.2.0 runtime inspection with symbol='INVALID_SYMBOL_XXX_123']` yfinance `Ticker.history` returns `DataFrame(shape=(0, 6))`, does NOT raise. It logs to stderr via its own logger. The only way to catch this is post-fetch empty-check.

**How to avoid:**
- Defensive empty-check inside fetch_ohlcv (as shown in §Pattern 1)
- Short-circuit future: if the planner wants to distinguish "invalid symbol" from "transient network failure", inspect `df.empty` on the FIRST attempt and raise a different exception that skips retries. For Phase 4 scope (2 fixed symbols from system_params), a typo is a developer bug, not a runtime condition — flat retry + hard-fail is fine.
- Test: `test_fetch_ohlcv_empty_frame_exhausts_retries` monkeypatches `yf.Ticker(...).history` to return `pd.DataFrame()` and asserts `DataFetchError` raised + retry count == 3.

**Warning signs:** A run completes in ~30s+ when it usually takes <5s; stderr shows `$SYMBOL: possibly delisted; no price data found`.

### Pitfall 3: `df.index` timezone drift between instruments

**What goes wrong:** `^AXJO` comes back with `Australia/Sydney` tz on its DatetimeIndex; `AUDUSD=X` comes back with `Europe/London` tz. If the orchestrator naively does `df.index.tz_convert('Australia/Perth')`, the bar dates can shift by a day (e.g., a Friday close in London = Saturday in Perth). D-13 explicitly says "no timezone conversion".

**Why it happens:** `[VERIFIED: yfinance 1.2.0 runtime inspection]` yfinance sets `df.index.tz` from the exchange metadata (ASX → Sydney, AUDUSD=X → London). The date component of the last bar is the MARKET DAY, not a wall-clock timestamp.

**How to avoid:**
- Follow D-13 exactly: `signal_as_of = df.index[-1].strftime('%Y-%m-%d')` — `strftime('%Y-%m-%d')` uses the naive date component and silently drops the tz, which is what you want here.
- Do NOT call `.tz_convert(...)` in data_fetcher or main.
- For stale-check (D-09): compare `run_date.date()` (AWST) with `df.index[-1].date()` — both are naive dates now. The comparison is slightly asymmetric (Perth calendar vs market calendar) but D-09's 3-day slack absorbs the edge case. Document in the stale-check docstring.
- Test: `test_signal_as_of_does_not_tz_convert` builds a hand-made DataFrame with `DatetimeIndex(tz='Europe/London')`, asserts `signal_as_of` equals the London-local date string.

**Warning signs:** Stale warnings fire after a single weekend because `AUDUSD=X`'s Friday close in London becomes Saturday elsewhere; equity_history entries have unexpected off-by-one dates.

### Pitfall 4: `logging.basicConfig` silent no-op under pytest

**What goes wrong:** `main()` calls `logging.basicConfig(level=INFO, format='%(message)s', stream=sys.stderr)`. Under pytest, a previous test (or pytest itself, or the `caplog` fixture) has already added a handler to the root logger. `basicConfig` is `force=False` by default, so our call is a silent no-op. Log messages show up at a different level or with pytest's formatting.

**Why it happens:** `[VERIFIED: stdlib logging.basicConfig source; runtime demo above]` `logging.basicConfig` is a no-op if the root logger already has any handler attached and `force=False`.

**How to avoid:**
- Always use `logging.basicConfig(level=logging.INFO, format='%(message)s', stream=sys.stderr, force=True)` — `force=True` removes existing handlers first
- In tests, use pytest's `caplog` fixture to capture log output rather than relying on our formatter
- Test: `test_main_configures_logging_at_info_level` asserts `logging.getLogger().level == logging.INFO` after `main()` entry

**Warning signs:** Test output has double-logged messages (pytest's default + ours); log messages missing stream=stderr → appearing on stdout or swallowed.

### Pitfall 5: `--reset` without confirmation = data loss

**What goes wrong:** `python main.py --reset` reinitialises state.json to $100k, wiping all trade history and equity curve. Running it accidentally (fat-finger in a copy-paste) destroys months of state.

**Why it happens:** REQUIREMENTS.md CLI-02 explicitly says "reinitialises `state.json` after confirmation". A skeleton that wires `reset_state()` → `save_state()` without the confirmation prompt would satisfy the wire-up but miss the behaviour.

**How to avoid:**
- Prompt before writing: `if input('Type YES to confirm reset: ').strip() != 'YES': sys.exit(1)` — exits 1 (operator cancel), NOT 2 (argparse error), NOT 0 (success)
- Skip the prompt inside tests via an env-var escape hatch: `if os.getenv('RESET_CONFIRM') == 'YES' or input(...) == 'YES'`. Phase 4 tests use the env-var.
- Test: `test_reset_without_confirmation_does_not_write` monkeypatches `builtins.input` to return `'no'`, runs main with `--reset`, asserts state.json mtime unchanged.

**Warning signs:** Git log shows state.json reset to $100k without an accompanying operator commit/comment.

### Pitfall 6: `len(df) < 300` check at the wrong moment

**What goes wrong:** The short-frame check (DATA-04) happens in `fetch_ohlcv` (inside data_fetcher.py), but the retry loop treats `ShortFrameError` as retry-eligible → burns 30s then gives up. OR the check happens only after `compute_indicators` mutates df → bug in compute_indicators triggers ShortFrameError instead.

**Why it happens:** Order-of-operations. `len(df) < 300` is a permanent condition (Yahoo only has 200 days of AUD/USD data) — no amount of retrying will help. It must be outside the retry loop, AFTER a successful fetch, BEFORE compute_indicators.

**How to avoid:**
- Structure `fetch_ohlcv` to return a possibly-short DataFrame (just "did the network succeed"); orchestrator checks `if len(df) < 300: raise ShortFrameError` immediately after.
- OR structure `fetch_ohlcv` to raise `ShortFrameError` itself after the retry loop succeeds — but then it's a subclass of DataFetchError that shouldn't be retried. Cleaner: separate concerns.
- Recommended:
  ```python
  # main.py
  df = data_fetcher.fetch_ohlcv(symbol, days=400, retries=3)
  if len(df) < 300:
    raise ShortFrameError(f'{symbol}: only {len(df)} bars, need >= 300')
  ```
- `ShortFrameError` lives in `data_fetcher.py` as a sibling of `DataFetchError` (both subclass `Exception`). Top-level handler in `main()` catches both → exit 2 + log.

**Warning signs:** A legitimate retry path burns 30s on a consistent short-frame response; or tests for DATA-04 fail with a retry-count timeout rather than a clean ShortFrameError.

### Pitfall 7: `state['signals'][symbol]` schema upgrade from int to dict

**What goes wrong:** Phase 3's `reset_state()` initialises `state['signals'] = {'SPI200': 0, 'AUDUSD': 0}` (dict[str, int]). Phase 4 D-08 changes the shape to `{'SPI200': {'signal': 0, 'signal_as_of': '...', 'as_of_run': '...'}, 'AUDUSD': {...}}` without a schema_version bump. An existing state.json from Phase 3 testing has the int shape.

**Why it happens:** D-08 is explicitly "no schema bump" — it relies on `_validate_loaded_state` only checking top-level keys. But code that reads `state['signals'][symbol]` as `int` will fail with `TypeError` against the new shape, and vice versa.

**How to avoid:**
- Orchestrator wraps the read: `raw = state['signals'].get(symbol); old_signal = raw if isinstance(raw, int) else raw.get('signal', 0)`.
- After computing the new signal, ALWAYS write the nested dict: `state['signals'][symbol] = {'signal': new_signal, 'signal_as_of': signal_as_of, 'as_of_run': run_date_iso}`.
- `reset_state()` is NOT changed (Phase 3 stays as-is; `_validate_loaded_state` only checks top-level). A fresh reset gives int shape on first read; first run upgrades in place.
- Test: `test_orchestrator_reads_both_int_and_dict_signal_shape` writes a state.json with old int shape, runs one iteration, asserts subsequent state has dict shape.

**Warning signs:** `TypeError: 'int' object has no attribute 'get'` on the first run after upgrade; dashboard fails to render signal status.

### Pitfall 8: `gross_pnl` vs `ClosedTrade.realised_pnl` double-counting

**What goes wrong:** `_closed_trade_to_record` naively sets `trade['gross_pnl'] = ct.realised_pnl` — but Phase 2's `_close_position` already deducted the closing-half cost to compute `realised_pnl`. Phase 3's `record_trade` deducts it AGAIN. Each trade's P&L is understated by `cost_aud * n_contracts / 2`.

**Why it happens:** `[VERIFIED: state_manager.py line 415–422]` The `record_trade` docstring says literally:
> trade['gross_pnl'] MUST be raw price-delta P&L ... It MUST NOT be Phase 2's ClosedTrade.realised_pnl — that already has the closing cost deducted by Phase 2 _close_position. Passing realised_pnl as gross_pnl causes double-counting of the closing cost.

**How to avoid:**
- `_closed_trade_to_record` MUST recompute `gross_pnl` from `ct.entry_price`, `ct.exit_price`, `ct.n_contracts`, `ct.direction`, `multiplier`. See Pattern 4 code.
- Test: `test_closed_trade_to_record_gross_pnl_is_raw_price_delta` asserts `trade['gross_pnl'] != ct.realised_pnl` when `cost_aud > 0`, and equals `(exit - entry) * n * mult` for LONG.

**Warning signs:** Running balance in state.json drifts below expected by ~$3–$6 per trade (the closing half).

## Code Examples

### Example 1: Retry loop with narrow exception catch

Source: synthesised from `yfinance 1.2.0` runtime inspection + CLAUDE.md Pitfall 4 guidance + state_manager.py's "narrow catch" discipline (D-05 in Phase 3).

```python
# data_fetcher.py (full module)
'''Data Fetcher — yfinance I/O hex for daily OHLCV.

DATA-01/02/03 (REQUIREMENTS.md §Data Ingestion). Owns all yfinance calls.
Raises DataFetchError after retries exhaust. Caller (main.py) handles
short-frame and stale-bar checks (DATA-04/05) — this module just fetches.

Architecture (hexagonal-lite, CLAUDE.md): I/O hex. This is the ONE module
allowed to open HTTPS connections. Must NOT import signal_engine,
sizing_engine, state_manager, notifier, dashboard, main. AST blocklist
in tests/test_signal_engine.py::TestDeterminism enforces this structurally.

Retries catch ONLY transient failures (YFRateLimitError, ReadTimeout,
ConnectionError, empty-frame-on-invalid-symbol). Bugs / auth failures /
4xx errors propagate as-is. Pitfall 4 from state_manager.py (narrow catch)
is preserved.
'''
import logging
import time

import pandas as pd
import requests.exceptions
import yfinance as yf
from yfinance.exceptions import YFRateLimitError

logger = logging.getLogger(__name__)

_RETRY_EXCEPTIONS = (
  YFRateLimitError,
  requests.exceptions.ReadTimeout,
  requests.exceptions.ConnectionError,
)


class DataFetchError(Exception):
  '''Raised when a symbol's fetch fails after all retries exhaust (DATA-03).

  Caught at the top of run_daily_check; aborts the whole run (D-03).
  '''


class ShortFrameError(Exception):
  '''Raised when a successful fetch returned fewer than 300 bars (DATA-04).

  Distinct from DataFetchError because it represents a PERMANENT condition
  (Yahoo only has that much history for this symbol) — retrying won't help.
  Orchestrator catches it at top level and exits 2 with a clear message.
  '''


def fetch_ohlcv(
  symbol: str,
  days: int = 400,
  retries: int = 3,
  backoff_s: float = 10.0,
) -> pd.DataFrame:
  '''DATA-01/02/03: fetch `days` days of daily OHLCV for `symbol`.

  Uses yf.Ticker(symbol).history() NOT yf.download() (see RESEARCH
  §Standard Stack — yf.download returns MultiIndex columns by default).

  Returns:
    DataFrame with exactly columns [Open, High, Low, Close, Volume] and a
    DatetimeIndex in exchange-local tz (NOT converted to Perth per D-13).

  Raises:
    DataFetchError: after `retries` attempts all fail with retry-eligible
                    exceptions OR empty-frame response.
  '''
  last_err: Exception | None = None
  for attempt in range(1, retries + 1):
    try:
      ticker = yf.Ticker(symbol)
      df = ticker.history(
        period=f'{days}d',
        interval='1d',
        auto_adjust=True,
        actions=False,
        timeout=10,
      )
      if df.empty:
        raise ValueError(
          f'yfinance returned empty DataFrame for {symbol} '
          f'(likely invalid symbol or Yahoo outage)',
        )
      return df[['Open', 'High', 'Low', 'Close', 'Volume']]
    except (*_RETRY_EXCEPTIONS, ValueError) as e:
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

### Example 2: Argparse with post-parse mutex for `--reset`

Source: `[VERIFIED: argparse stdlib; runtime test above]`

```python
# main.py — CLI parsing snippet
import argparse

def _build_parser() -> argparse.ArgumentParser:
  p = argparse.ArgumentParser(
    prog='python main.py',
    description='Trading Signals — SPI 200 & AUD/USD mechanical system',
  )
  p.add_argument(
    '--test', action='store_true',
    help='Run full signal check, print report, do NOT mutate state.json (CLI-01)',
  )
  p.add_argument(
    '--reset', action='store_true',
    help='Reinitialise state.json to $100k after confirmation (CLI-02). '
         'Cannot be combined with other flags.',
  )
  p.add_argument(
    '--force-email', action='store_true',
    help='Send today\'s email immediately regardless of schedule (CLI-03). '
         'Phase 4: logs stub; wiring arrives in Phase 6.',
  )
  p.add_argument(
    '--once', action='store_true',
    help='Run one daily check and exit (CLI-04, GHA mode). '
         'Phase 4: alias for default; scheduler loop arrives in Phase 7.',
  )
  return p


def _validate_flag_combo(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
  '''D-05: --reset is strictly exclusive. --test + --force-email is allowed.

  Using post-parse parser.error() (exits with code 2, matching argparse convention)
  because argparse's mutually_exclusive_group would also block --test + --once etc.
  which D-05 allows.
  '''
  if args.reset and (args.test or args.force_email or args.once):
    parser.error('--reset cannot be combined with other flags')


def main(argv: list[str] | None = None) -> int:
  parser = _build_parser()
  args = parser.parse_args(argv)
  _validate_flag_combo(parser, args)
  # ... dispatch ...
```

### Example 3: Monkeypatch pattern for data_fetcher tests

Source: pytest built-in monkeypatch + D-02 hybrid strategy.

**CRITICAL:** The patch target is `data_fetcher.yf` NOT `yfinance`. When `data_fetcher.py` does `import yfinance as yf`, it binds `yf` as an attribute of `data_fetcher` at module-import time. Patching `yfinance.Ticker` AFTER import does not affect `data_fetcher.yf.Ticker`.

```python
# tests/test_data_fetcher.py
import pandas as pd
import pytest
from yfinance.exceptions import YFRateLimitError

import data_fetcher
from data_fetcher import DataFetchError, fetch_ohlcv


class _FakeTicker:
  '''Stand-in for yfinance.Ticker during tests.'''
  def __init__(self, symbol: str, fake_df: pd.DataFrame | None = None,
               raise_exc: Exception | None = None):
    self.symbol = symbol
    self._fake_df = fake_df
    self._raise = raise_exc

  def history(self, **kwargs) -> pd.DataFrame:
    if self._raise is not None:
      raise self._raise
    return self._fake_df if self._fake_df is not None else pd.DataFrame()


class TestFetch:

  def test_happy_path_returns_exact_columns(self, monkeypatch):
    '''DATA-01: happy path — columns are exactly [Open, High, Low, Close, Volume].'''
    idx = pd.date_range('2024-01-01', periods=400, freq='B')
    fake = pd.DataFrame({
      'Open': range(400), 'High': range(400), 'Low': range(400),
      'Close': range(400), 'Volume': range(400),
      'Dividends': 0.0,  # yfinance adds these when actions=True — must be stripped
      'Stock Splits': 0.0,
    }, index=idx)
    monkeypatch.setattr(
      data_fetcher, 'yf',
      type('MockYF', (), {'Ticker': lambda self, s: _FakeTicker(s, fake)})(),
    )
    df = fetch_ohlcv('^AXJO', days=400, retries=1, backoff_s=0.0)
    assert list(df.columns) == ['Open', 'High', 'Low', 'Close', 'Volume']
    assert len(df) == 400

  def test_retry_on_rate_limit_then_success(self, monkeypatch):
    '''DATA-03: retries 3x on YFRateLimitError; succeeds on attempt 3.'''
    calls = []
    idx = pd.date_range('2024-01-01', periods=400, freq='B')
    success_df = pd.DataFrame({c: range(400) for c in ['Open', 'High', 'Low', 'Close', 'Volume']}, index=idx)

    def make_ticker(sym):
      calls.append(sym)
      if len(calls) < 3:
        return _FakeTicker(sym, raise_exc=YFRateLimitError('rate limited'))
      return _FakeTicker(sym, fake_df=success_df)

    monkeypatch.setattr(data_fetcher, 'yf',
                        type('MockYF', (), {'Ticker': lambda self, s: make_ticker(s)})())
    monkeypatch.setattr(data_fetcher.time, 'sleep', lambda s: None)  # speed up test
    df = fetch_ohlcv('^AXJO', days=400, retries=3, backoff_s=0.0)
    assert len(df) == 400
    assert len(calls) == 3

  def test_empty_frame_exhausts_retries(self, monkeypatch):
    '''DATA-04 (fetch boundary): empty frame retries then DataFetchError.'''
    monkeypatch.setattr(data_fetcher, 'yf',
                        type('MockYF', (), {'Ticker': lambda self, s: _FakeTicker(s, fake_df=pd.DataFrame())})())
    monkeypatch.setattr(data_fetcher.time, 'sleep', lambda s: None)
    with pytest.raises(DataFetchError, match='retries exhausted'):
      fetch_ohlcv('INVALID', days=400, retries=3, backoff_s=0.0)
```

### Example 4: Per-instrument log block matching D-14

Source: D-14 contract verbatim.

```python
# main.py — inside run_daily_check, per instrument
logger.info(
  '[Fetch] %s ok: %d bars, last_bar=%s, fetched_in=%.1fs',
  symbol, len(df), signal_as_of, fetch_elapsed,
)
logger.info(
  '[Signal] %s signal=%s signal_as_of=%s (ADX=%.1f, moms=%s, rvol=%.2f)',
  symbol, {1: 'LONG', -1: 'SHORT', 0: 'FLAT'}[new_signal],
  signal_as_of, scalars['adx'], _fmt_moms(scalars), scalars['rvol'],
)
if result.position_after is not None:
  logger.info(
    '[State] %s position: %s %d contracts @ entry=%.1f, pyramid=%d, trail_stop=%.1f, unrealised=%+.0f',
    symbol, result.position_after['direction'], result.position_after['n_contracts'],
    result.position_after['entry_price'], result.position_after['pyramid_level'],
    get_trailing_stop(result.position_after, bar['close'], scalars['atr']),
    result.unrealised_pnl,
  )
else:
  logger.info('[State] %s no position', symbol)
if result.closed_trade is not None:
  logger.info(
    '[State] %s trade closed: %s exit=%.1f P&L=%+.2f reason=%s',
    symbol, result.closed_trade.direction, result.closed_trade.exit_price,
    result.closed_trade.realised_pnl, result.closed_trade.exit_reason,
  )
else:
  logger.info('[State] %s no trades closed this run', symbol)
logger.info('')  # blank line between instruments
```

### Example 5: Stale-bar detection + append_warning

Source: D-09 + D-10 + state_manager.append_warning signature (state_manager.py line 371).

```python
# main.py — inside the per-instrument block, AFTER fetch, BEFORE compute_indicators
_STALE_THRESHOLD_DAYS = 3  # D-09

last_bar_date = df.index[-1].date()         # naive date in market-local tz (D-13)
today_awst_date = run_date.date()            # naive date from Australia/Perth wall-clock
days_old = (today_awst_date - last_bar_date).days
if days_old > _STALE_THRESHOLD_DAYS:
  logger.warning(
    '[Fetch] WARN %s stale: signal_as_of=%s is %dd old (threshold=%dd)',
    symbol, signal_as_of, days_old, _STALE_THRESHOLD_DAYS,
  )
  # D-10: queue for end-of-run flush so warnings land in state.json even if
  # later steps fail. (Orchestrator maintains a list, flushes in step 5 of D-11.)
  pending_warnings.append((
    'fetch',
    f'{symbol} stale: signal_as_of={signal_as_of} is {days_old}d old '
    f'(threshold={_STALE_THRESHOLD_DAYS}d)',
  ))

# Later, in the run-summary flush step (D-11 step 5):
for source, msg in pending_warnings:
  state = state_manager.append_warning(state, source, msg)
```

**Important confirmation** (`[VERIFIED: state_manager.py line 371]`): `append_warning(state, source, message, now=None) -> dict`. Takes positional `source` and `message` strings — NOT a dict as D-10 prose suggests. The "{level, code, symbol, ...}" fields from D-10 should be serialised INTO the `message` string (e.g., `f'stale_bar:{symbol}:{signal_as_of}:{days_old}d:{detected_at_run_date}'`). D-10 prose is aspirational; the actual API is 3 positional args + optional `now`.

### Example 6: Recorded fixture save + load (D-02)

Source: pandas docs on `to_json(orient='split')` round-trip; Phase 1's `regenerate_goldens.py` offline-script pattern.

```python
# tests/regenerate_fetch_fixtures.py
'''Offline fixture regenerator — pulls from Yahoo, saves to tests/fixtures/fetch/.
Run manually: python tests/regenerate_fetch_fixtures.py
NEVER run in CI (mirrors Phase 1 regenerate_goldens.py discipline).
'''
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data_fetcher import fetch_ohlcv

FIXTURES_DIR = ROOT / 'tests' / 'fixtures' / 'fetch'
FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

SYMBOLS = {'^AXJO': 'axjo', 'AUDUSD=X': 'audusd'}

for symbol, slug in SYMBOLS.items():
  df = fetch_ohlcv(symbol, days=400, retries=3, backoff_s=10.0)
  path = FIXTURES_DIR / f'{slug}_400d.json'
  # orient='split' is the only lossless round-trip for DataFrames with
  # a DatetimeIndex (orient='records' loses the index dtype; orient='columns'
  # stringifies everything).
  df.to_json(path, orient='split', date_format='iso')
  print(f'wrote {path} ({len(df)} rows)')
```

```python
# tests/test_data_fetcher.py — loading the fixture
import pandas as pd
from pathlib import Path

def _load_recorded_fixture(slug: str) -> pd.DataFrame:
  path = Path(__file__).parent / 'fixtures' / 'fetch' / f'{slug}_400d.json'
  df = pd.read_json(path, orient='split')
  # read_json may restore naive DatetimeIndex; re-localise if needed.
  # For our purposes the exact tz doesn't matter — D-13 uses strftime which
  # drops tz anyway.
  return df
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `yf.download('AAPL', ...)` returning flat `[Open, High, Low, Close, Adj Close, Volume]` | Returns MultiIndex columns by default | yfinance 0.2.48 (late 2024) | Default behaviour change. Use `Ticker.history()` instead to preserve flat Index. |
| `auto_adjust=False` default in `yf.download` | `auto_adjust=True` warned about, then flipped to True default | yfinance 0.2.52 | No `Adj Close` column by default now (adjust is applied in-place). SPEC.md's mention of a separate `Adj Close` column is obsolete. |
| Silent retry-on-rate-limit | `YFRateLimitError` raised | yfinance 0.2.52 | Explicit exception makes retry logic cleaner — catch specifically rather than bare. |
| `ewm.adjust=True` default in pandas Wilder smoothing | `adjust=False` + `min_periods=period` required for correct Wilder | (not changed; Phase 1 already honours) | signal_engine already implements. |
| `pytz.timezone('...')` | `zoneinfo.ZoneInfo('...')` (stdlib in 3.9+) | Python 3.9 | state_manager.py already uses zoneinfo. Phase 4 should match. |

**Deprecated / outdated:**
- `yfinance.download(..., raise_errors=True)` — warns: `DeprecationWarning: 'raise_errors' deprecated, do: yf.config.debug.hide_exceptions = False`. Not used in our call, but flag if the planner sees it.
- `pytz.timezone(...)` — stdlib `zoneinfo` replaces; still works but not idiomatic for new code.
- `max(1, …)` floor on sizing — explicitly rejected by operator (STATE.md §Decisions; Phase 2 D-02 honours).

## Assumptions Log

All factual claims about yfinance behaviour, Python stdlib, and pytest plugins were verified via runtime introspection or web search during this research pass. Surviving `[ASSUMED]` entries:

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `zoneinfo.ZoneInfo('Australia/Perth')` is preferred over `pytz.timezone('Australia/Perth')` despite PROJECT.md listing `pytz` in the stack | §Standard Stack §Supporting | Low — Perth has no DST so both libraries produce identical results. state_manager.py already uses `zoneinfo`, so choosing it is consistent. If the planner prefers pytz for PROJECT.md compliance, swap the import; no behaviour change. |
| A2 | Recording fixtures via `df.to_json(orient='split', date_format='iso')` is lossless for our float64 DataFrames with DatetimeIndex | §Code Examples §Example 6 | Low — pandas documents this as the only lossless orient. If the planner discovers a tz-restoration quirk during regenerator run, fallback is `pickle` (binary, less git-friendly) or `to_parquet` (new dep). |
| A3 | `pytest-freezer` (0.4.9) works cleanly with `datetime.now(tz=AWST)` | §Standard Stack §Supporting | Low — freezegun is battle-tested. If not, fallback is the Phase 3 pattern: accept `now=None` injection in `run_daily_check` and orchestrator passes `now=datetime.now(tz=AWST)`. |
| A4 | Yahoo does not have a known CLI-level rate limit that would bite a 2-symbols-per-weekday schedule | §Common Pitfalls Pitfall 2 | Low — 2 requests per weekday is far below any public rate limit (yfinance issues #2411/#2567 are all about thousands-of-tickers scripts). Flat 10s backoff is more than enough. |
| A5 | D-08 backward-compat upgrade path (read int-or-dict, always write dict) is acceptable without a schema_version bump | §Common Pitfalls Pitfall 7 | Medium — if a future Phase 7/8 reviewer decides schema changes deserve version bumps even when nested, we'd need a migration entry in `state_manager.MIGRATIONS`. D-08 says "no bump" so we honour it, but flag for cross-AI review. |

## Open Questions

1. **Q: Should `data_fetcher` live in `tests/conftest.py` for a shared `frozen_awst` fixture, or should we use `pytest-freezer`'s `@pytest.mark.freeze_time` directly on each test?**
   - What we know: Phase 3 avoided freezegun entirely by accepting `now=None` injection. Phase 4 orchestrator reads the clock in `main()` itself, which makes injection awkward.
   - What's unclear: whether the planner prefers to thread `now` through `run_daily_check(args, now=None)` or use the pytest plugin.
   - Recommendation: use `pytest-freezer` markers directly on orchestrator tests. Add `pytest-freezer==0.4.9` to requirements.txt in Wave 0. Keep `run_daily_check(args)` signature clean without a `now` parameter. If future verification wants deterministic runs without the plugin, `--now 2026-04-21T09:00:03+08:00` CLI override can be added later (V2 scope).

2. **Q: How should the orchestrator surface `ShortFrameError` vs `DataFetchError` in the exit code?**
   - What we know: DATA-03 says "retries exhausted → hard-fail + exit non-zero". DATA-04 says "short/empty frame → hard-fail, no state written".
   - What's unclear: whether both should map to exit code 2, or differentiate (2 for argparse/fetch, 3 for short-frame, 4 for other).
   - Recommendation: use exit 2 for ALL fetch-layer failures (both DataFetchError and ShortFrameError). Exit 1 for operator-cancellation (e.g., `--reset` confirmation declined). Exit 0 for success. Exit 3+ reserved for Phase 8 (crash email failures etc). Operators running GHA care only about 0 vs non-zero; fine granularity can be added later.

3. **Q: Is a `--symbol SYMBOL` flag for targeted single-instrument fetch in scope?**
   - What we know: CONTEXT.md does not list such a flag. D-03 hard-fails the whole run if either instrument fails, which is annoying for debugging.
   - What's unclear: whether the operator wants a debug-mode single-instrument path.
   - Recommendation: out of scope for Phase 4. Add as deferred item. Phase 4 surface is the 5 flags from REQUIREMENTS.md + existing CONTEXT.md.

4. **Q: Where does `pending_warnings` (the local queue for stale-bar warnings) live in `run_daily_check`?**
   - What we know: D-11 step 5 says "Flush queued warnings". The orchestrator needs a local collection.
   - What's unclear: whether it's a simple `list[tuple[str, str]]` or a small dataclass.
   - Recommendation: `list[tuple[str, str]]` (source, message) — minimal. No dataclass needed; the shape is internal to `run_daily_check` and never serialised.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11 | All Phase 4 code | ✓ | 3.11.8 (pyenv) | — |
| `yfinance` | `data_fetcher.fetch_ohlcv` | ✓ | 1.2.0 | — |
| `pandas` | DataFrame return type | ✓ | 2.3.3 | — |
| `numpy` | pandas transitive | ✓ | 2.0.2 | — |
| `pytest` | test runner | ✓ | 8.3.3 | — |
| `pytest-freezer` | clock freezing in orchestrator tests | ✗ | (0.4.9 available on PyPI) | Accept `now=None` injection through `run_daily_check` signature (Phase 3's pattern). Recommend install rather than fallback. |
| Internet access for yfinance HTTPS | `regenerate_fetch_fixtures.py` only (manual, not CI) | ✓ | — | — |
| Internet access for CI | **None** — all CI tests use recorded fixtures + monkeypatch. `regenerate_fetch_fixtures.py` is manually invoked. | N/A | — | — |

**Missing dependencies with no fallback:** none.

**Missing dependencies with fallback:** `pytest-freezer` — install via Wave 0 (add to requirements.txt, `pip install -r`).

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.3.3 (+ pytest-freezer 0.4.9 Wave 0 add) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (`testpaths=['tests']`, `addopts='-ra --strict-markers'`) |
| Quick run command | `.venv/bin/pytest tests/test_data_fetcher.py tests/test_main.py -x` |
| Full suite command | `.venv/bin/pytest tests/ -x` (full suite; currently ~100 tests after Phases 1/2/3) |
| Phase-gate command | `.venv/bin/pytest tests/ -x && .venv/bin/ruff check .` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DATA-01 | Fetch 400d OHLCV for `^AXJO` | integration (recorded fixture) | `pytest tests/test_data_fetcher.py::TestFetch::test_happy_path_axjo_returns_400_bars -x` | ❌ Wave 0 |
| DATA-02 | Fetch 400d OHLCV for `AUDUSD=X` | integration (recorded fixture) | `pytest tests/test_data_fetcher.py::TestFetch::test_happy_path_audusd_returns_400_bars -x` | ❌ Wave 0 |
| DATA-03 | Retry 3× on failure | unit (monkeypatch) | `pytest tests/test_data_fetcher.py::TestFetch::test_retry_on_rate_limit_then_success -x` | ❌ Wave 1 |
| DATA-04 | Short frame (<300) hard-fails | unit (hand-built DataFrame) | `pytest tests/test_main.py::TestOrchestrator::test_short_frame_raises_and_no_state_written -x` | ❌ Wave 2 |
| DATA-05 | Stale last bar → warning (not fatal) | unit (frozen clock + hand-built DataFrame) | `pytest tests/test_main.py::TestOrchestrator::test_stale_bar_appends_warning -x` | ❌ Wave 3 |
| DATA-06 | `signal_as_of` vs `run_date` logged separately | unit (caplog + frozen clock) | `pytest tests/test_main.py::TestOrchestrator::test_signal_as_of_and_run_date_logged_separately -x` | ❌ Wave 2 |
| CLI-01 | `--test` does not mutate state.json | integration (mtime assertion) | `pytest tests/test_main.py::TestCLI::test_test_flag_leaves_state_json_mtime_unchanged -x` | ❌ Wave 3 |
| CLI-02 | `--reset` reinits after confirmation | unit (monkeypatch input) | `pytest tests/test_main.py::TestCLI::test_reset_with_confirmation_writes_fresh_state -x` | ❌ Wave 3 |
| CLI-03 | `--force-email` logs stub + exits 0 | unit (caplog) | `pytest tests/test_main.py::TestCLI::test_force_email_logs_stub_and_exits_zero -x` | ❌ Wave 3 |
| CLI-04 | `--once` runs single check | unit (smoke) | `pytest tests/test_main.py::TestCLI::test_once_flag_runs_single_check -x` | ❌ Wave 2 |
| CLI-05 | Default == `--once` in Phase 4 | unit (smoke) | `pytest tests/test_main.py::TestCLI::test_default_mode_runs_once_and_logs_schedule_stub -x` | ❌ Wave 2 |
| ERR-01 | yfinance failure → log + exit non-zero | unit (monkeypatch) | `pytest tests/test_main.py::TestOrchestrator::test_fetch_failure_exits_nonzero_no_save_state -x` | ❌ Wave 3 |
| ERR-06 | Structured per-instrument logs | unit (caplog + regex) | `pytest tests/test_main.py::TestOrchestrator::test_log_format_matches_d14_contract -x` | ❌ Wave 2 |

### Sampling Rate

- **Per task commit:** `.venv/bin/pytest tests/test_data_fetcher.py tests/test_main.py -x` (fast — new tests only)
- **Per wave merge:** `.venv/bin/pytest tests/ -x` (full suite incl Phases 1/2/3 regression)
- **Phase gate:** Full suite green + `.venv/bin/ruff check .` + `python tests/regenerate_goldens.py` produces zero diff (Phase 1 determinism snapshot preserved)

### Wave 0 Gaps

- [ ] `tests/test_data_fetcher.py` — TestFetch class (happy path × 2 instruments, retry on rate-limit, retry on timeout, retry on connection error, empty-frame exhausts retries, column shape assertion)
- [ ] `tests/test_main.py` — TestCLI (flag mutex, --test/--reset/--force-email/--once/default), TestOrchestrator (happy path, short-frame, stale-bar, fetch-failure, signal_as_of vs run_date, D-08 upgrade path, D-12 translator)
- [ ] `tests/regenerate_fetch_fixtures.py` — offline script (mirrors tests/regenerate_goldens.py)
- [ ] `tests/fixtures/fetch/axjo_400d.json`, `tests/fixtures/fetch/audusd_400d.json` — committed recorded fixtures
- [ ] Extend `tests/test_signal_engine.py::TestDeterminism` AST blocklist: add `DATA_FETCHER_PATH` + `FORBIDDEN_MODULES_DATA_FETCHER = frozenset({'signal_engine', 'sizing_engine', 'state_manager', 'notifier', 'dashboard', 'main', 'numpy'})` (data_fetcher imports pandas legitimately, so pandas is NOT in the forbidden set; numpy is because we don't need it and it creeps in via stray imports)
- [ ] Extend AST blocklist to cover `main.py` with a permissive allowlist (main is the ONLY module allowed to import both signal_engine+state_manager+sizing_engine+data_fetcher; but still forbid numpy)
- [ ] `requirements.txt` — add `pytest-freezer==0.4.9`

## Sources

### Primary (HIGH confidence)

- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/state_manager.py` (lines 1–483) — full public API, `append_warning(state, source, message, now=None)` signature, `_REQUIRED_TRADE_FIELDS`, `record_trade` gross_pnl semantics, `_validate_loaded_state` D-18
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/sizing_engine.py` (lines 1–659) — `step(position, bar, indicators, old_signal, new_signal, account, multiplier, cost_aud_open)` signature, `ClosedTrade` dataclass fields, `StepResult` fields, `_close_position` realised_pnl calculation
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/signal_engine.py` (lines 1–80) — `LONG`/`SHORT`/`FLAT` constants, `compute_indicators`, `get_signal`, `get_latest_indicators` public API
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/system_params.py` — `INITIAL_ACCOUNT`, `MAX_WARNINGS`, `STATE_SCHEMA_VERSION`, `STATE_FILE`, `SPI_MULT`, `SPI_COST_AUD`, `AUDUSD_NOTIONAL`, `AUDUSD_COST_AUD`, `Position` TypedDict
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/requirements.txt` — 5 pinned deps (yfinance 1.2.0, pandas 2.3.3, numpy 2.0.2, pytest 8.3.3, ruff 0.6.9)
- Runtime inspection of yfinance 1.2.0 (from installed .venv) — `Ticker.history()` signature with `raise_errors` deprecation; `yf.download` MultiIndex default; empty-frame-on-invalid-symbol behaviour; `^AXJO` tz = `Australia/Sydney`; `AUDUSD=X` tz = `Europe/London`; column set `[Open, High, Low, Close, Volume]` when `actions=False`; `yfinance.exceptions.YFRateLimitError` (and siblings)

### Secondary (MEDIUM confidence, verified against primary)

- `.planning/phases/04-end-to-end-skeleton-fetch-orchestrator-cli/04-CONTEXT.md` — 15 locked decisions D-01..D-15 (copied verbatim under §User Constraints)
- `.planning/REQUIREMENTS.md` lines 12–17 (DATA-01..06), 132–138 (CLI-01..05), 141–147 (ERR-01, ERR-06) — the 13 in-scope requirement IDs
- `.planning/phases/01-signal-engine-core-indicators-vote/01-CONTEXT.md` (D-05..D-12) — Phase 1 public API + NaN policies
- `.planning/phases/02-signal-engine-sizing-exits-pyramiding/02-CONTEXT.md` (D-02/D-07/D-10/D-11/D-13/D-17) — sizing_engine contracts
- `.planning/phases/03-state-persistence-with-recovery/03-CONTEXT.md` (D-01..D-20) — state_manager API decisions
- `CLAUDE.md` + `.planning/PROJECT.md` + `SPEC.md` + `.planning/ROADMAP.md` — project-wide conventions, stack constraints, Phase 4 success criteria
- `CLAUDE.md` globally — 2-space indent, single quotes, log prefix convention, hex-lite architecture

### Tertiary (cited web sources)

- `[WebSearch verified]` yfinance `YFRateLimitError` class behaviour — GitHub issues [#2411](https://github.com/ranaroussi/yfinance/issues/2411), [#2567](https://github.com/ranaroussi/yfinance/issues/2567), confirmed against runtime yfinance.exceptions module
- `[WebFetch verified]` yfinance [CHANGELOG.rst](https://github.com/ranaroussi/yfinance/blob/main/CHANGELOG.rst) — 1.2.0 notes, `multi_level_index` addition at 0.2.47, `YFRateLimitError` addition at 0.2.52, `auto_adjust=True` default at 0.2.52
- `[CITED: Python stdlib docs]` `logging.basicConfig(force=True)` semantic — Python 3.8+
- `[CITED: pypi.org]` `pytest-freezer==0.4.9` latest release as of 2026-04-21

## Metadata

**Confidence breakdown:**

- Standard stack: **HIGH** — every version pinned; runtime-inspected the installed yfinance to confirm Ticker.history signature + empty-frame behaviour + exception classes; validated CHANGELOG against GitHub.
- Architecture: **HIGH** — Phase 1/2/3 modules physically read (not inferred); all public API signatures confirmed at source level.
- Pitfalls: **HIGH** — 8 pitfalls all backed by either runtime reproduction (Pitfalls 1/2/3/4) or direct state_manager.py docstring quote (Pitfalls 7/8) or Phase 3 CONTEXT decisions (Pitfalls 5/6).
- Testing: **MEDIUM** — pytest-freezer integration is based on the standard pytest-freezer README patterns; not runtime-verified yet (A3). Monkeypatch pattern is standard pytest practice; Phase 1/2/3 already use the same pattern.
- Requirements → test map: **HIGH** — every in-scope requirement has an explicit test name proposal matching Phase 1/2/3 naming conventions.

**Research date:** 2026-04-21
**Valid until:** 2026-05-21 (30 days — yfinance is a fast-moving dep but we have 1.2.0 pinned; only re-research if operator chooses to bump the pin)
