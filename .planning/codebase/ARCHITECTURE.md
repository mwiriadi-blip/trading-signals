<!-- refreshed: 2026-05-15 -->
# Architecture

**Analysis Date:** 2026-05-15

## System Overview

Trading Signals is a hexagonal-lite pure-math trading platform built on atomic state persistence and strict import boundaries. The architecture separates pure computational engines (signal, sizing, PnL) from I/O adapters (state_manager, data_fetcher, notifier, web) via a disciplined import model enforced by AST-level regressions.

```text
┌──────────────────────────────────────────────────────────────────────┐
│              CLI Entrypoint & Orchestration                           │
│         main.py ← cli_parser, interactive, scheduler_driver          │
└──────────────────────────────────────────────┬───────────────────────┘
                                                │
                ┌───────────────────────────────┼───────────────────────┐
                │                               │                       │
┌───────────────┴──────────────┐   ┌───────────┴──────────┐   ┌────────┴──────┐
│   Daily Run Orchestration    │   │   Web Adapter        │   │   Dashboard   │
│   daily_loop.py              │   │   FastAPI + HTMX     │   │   Renderer    │
│   daily_run.py (9-step)      │   │   web/app.py         │   │   dashboard.  │
│   └─ crash_boundary.py       │   │   web/routes/*       │   │   py (async)  │
│   └─ daily_run_helpers.py    │   │                      │   │               │
│   └─ paper_trade_alerts.py   │   │   ├─ POST /trades/*  │   └───────────────┘
│   └─ scheduler_driver.py     │   │   ├─ POST /totp/*    │
└───────────────┬──────────────┘   │   ├─ GET /dashboard  │
                │                  │   ├─ POST /reset     │
                │                  │   └─ POST /invite    │
                │                  └──────────────────────┘
                │
    ┌───────────┴────────────────────────────────┐
    │    Pure-Math Hex (stdlib + numpy/pandas)    │
    │                                              │
    │  ├─ signal_engine.py (ATR/ADX/Mom/RVol)    │
    │  ├─ sizing_engine/ (Position sizing)        │
    │  ├─ pnl_engine.py (P&L, Decimal-based)     │
    │  ├─ alert_engine.py (Stop-loss alerts)     │
    │  ├─ system_params.py (All constants)        │
    │  └─ backtest/ (Historical simulator)        │
    └───────────────┬────────────────────────────┘
                    │
        ┌───────────┼──────────────┬────────────────┐
        │           │              │                │
┌───────┴────┐  ┌──┴─────────┐  ┌┴────────┐  ┌─────┴──────┐
│   State    │  │   Data     │  │Notifier │  │Auth Store  │
│  Manager   │  │  Fetcher   │  │(Resend) │  │ (TOTP)     │
│            │  │(yfinance)  │  │         │  │            │
│ state.json │  │ OHLCV      │  │Email    │  │Shared-key  │
│ fcntl lock │  │ fetch w/   │  │dispatch │  │+ Tokens    │
│ migrations │  │ retry loop │  │         │  │            │
└────────────┘  └────────────┘  └─────────┘  └────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| **Orchestrator** | CLI parsing, mode dispatch, exception boundary, logging setup | `main.py` |
| **Daily Run** | 9-step per-instrument loop: fetch, indicators, signal, size, persist, equity, warnings, alerts, dashboard | `daily_run.py` |
| **Signal Engine** | Pure-math: ATR(14), ADX(20), Mom(21/63/252), RVol(20), 2-of-3 vote | `signal_engine.py` |
| **Sizing Engine** | Position sizing: contracts, pyramid, stops, exit scalars | `sizing_engine/__init__.py` |
| **PnL Engine** | Decimal-based P&L: unrealised, realised, cost splitting | `pnl_engine.py` |
| **Alert Engine** | Stop-loss state: HIT/APPROACHING/CLEAR, ATR distance | `alert_engine.py` |
| **State Manager** | Atomic JSON I/O, fcntl locks, schema migration (v1→v12), corruption recovery | `state_manager/__init__.py` |
| **Data Fetcher** | yfinance OHLCV fetch with retries, rate-limit handling, timeout guards | `data_fetcher.py` |
| **Notifier** | Email dispatch via Resend API, daily/crash templates, redaction | `notifier/dispatch.py` |
| **Web Layer** | FastAPI + HTMX dashboard, auth middleware, trades/totp/invite routes, fcntl coordination | `web/app.py` |
| **Auth Store** | Shared-secret auth + TOTP device tokens + magic-link invites | `auth_store/_users.py` |
| **Backtest** | Historical simulator: replay 300-bar OHLCV, compute signals, size, measure P&L | `backtest/simulator.py` |

## Pattern Overview

**Overall:** Hexagonal-lite with strict import boundaries enforced by AST regressions.

**Key Characteristics:**
- **Pure-math hex:** Signal/sizing/PnL engines import stdlib + numpy/pandas only. No I/O, network, or state imports.
- **I/O adapters:** state_manager, data_fetcher, notifier are the only modules allowed to touch filesystem / network / database.
- **Atomic state:** All mutations via `state_manager.mutate_state()` which holds an fcntl.LOCK_EX advisory lock to coordinate with the web layer.
- **Service facades:** Daily run orchestration is composed via injected DailyRunService, SignalEvaluationService, PostRunService (SOLID pattern).
- **Never-crash wrappers:** Dashboard render, email dispatch, and scheduler ticks use bare `except Exception:` to survive failures gracefully.
- **Decimal for money:** All AUD amounts flow through `Decimal(str(x))` at the pnl_engine boundary; quantized to 2dp with ROUND_HALF_UP.

## Layers

**Pure-Math Layer (Hex):**
- Purpose: Compute indicators, evaluate signals, size positions, calculate P&L, evaluate alerts.
- Location: `signal_engine.py`, `sizing_engine/`, `pnl_engine.py`, `alert_engine.py`, `system_params.py`, `backtest/`
- Contains: Numpy/pandas logic, formula implementations, indicator caches
- Depends on: stdlib only (no state_manager, notifier, or requests imports)
- Used by: daily_run.py, backtest CLI

**Orchestration Layer:**
- Purpose: Coordinate 9-step daily sequence, dispatch email, render dashboard, push state to git.
- Location: `main.py`, `daily_loop.py`, `daily_run.py`, `crash_boundary.py`, `daily_run_helpers.py`, `scheduler_driver.py`, `paper_trade_alerts.py`, `state_actions.py`
- Contains: CLI parsing, logging, exception boundaries, service wiring
- Depends on: Pure-math hex + state_manager + notifier + data_fetcher
- Used by: Entry point `main()`, scheduler daemon

**I/O Adapters:**
- **State Manager** (`state_manager/`): Atomic JSON with fcntl locks, migration chain, corruption recovery.
- **Data Fetcher** (`data_fetcher.py`): yfinance OHLCV with retries, rate-limit handling, timeout guards.
- **Notifier** (`notifier/`): Email templates, Resend API dispatch, redaction.
- **Auth Store** (`auth_store/`): Shared-secret, TOTP, magic-link invites, session tokens.

**Web Adapter:**
- Purpose: FastAPI server exposing dashboard, trades mutations, auth flows, admin panels.
- Location: `web/app.py`, `web/routes/`, `web/services/`
- Contains: HTTP endpoints, HTMX templates, JSON payloads, session middleware
- Depends on: fastapi, starlette, state_manager (read via `load_state`, mutate via `mutate_state`), sizing_engine + system_params (for trade validation)
- Used by: Browser clients, HTMX-over-HTTP

**Dashboard Renderer:**
- Purpose: Async HTML file generation for `dashboard.html`, `dashboard-signals.html`, etc.
- Location: `dashboard_renderer/`, `dashboard.py`
- Contains: Jinja2 templates, file I/O, async rendering
- Depends on: state_manager, system_params
- Used by: `daily_run_helpers._render_dashboard_never_crash()`

## Data Flow

### Primary Request Path: Daily Run (9-Step Sequence)

1. **Entry** (`main.py:72-162`) — Parse CLI, validate flags, setup logging, dispatch to mode handler (--reset, --force-email, --once, or default+scheduler).
2. **Check weekday** (`daily_run.py:114-119`) — Skip if Saturday/Sunday, return early.
3. **Load state** (`daily_run.py:135`) — Deserialize `state.json` via `state_manager.load_state()`.
4. **For each enabled market** (`daily_run.py:143-149`):
   a. **Fetch OHLCV** (`daily_run.py:~165`) — Call `data_fetcher.fetch_ohlcv(symbol)` with 300-bar history.
   b. **Compute indicators** (`daily_run.py:~170`) — `signal_engine.compute_indicators(df)` → ATR, ADX, Mom, RVol.
   c. **Evaluate signal** (`daily_run.py:~175`) — `signal_engine.vote(atr, adx, mom_list, rvol)` → LONG (1) / SHORT (-1) / FLAT (0).
   d. **Size position** (`daily_run.py:~180`) — `sizing_engine.compute_next_position(signal, ...)` → contracts, stop, pyramid.
   e. **Record trade** (`daily_run.py:~185`) — If position changed, call `state_manager.record_trade(symbol, old_pos, new_pos)`.
   f. **Update equity** (`daily_run.py:~190`) — `pnl_engine.compute_unrealised_pnl(...)` → add to equity_history.
5. **Flush warnings** (`daily_run.py:~195`) — `state_manager.clear_warnings()` (unless --test).
6. **Recompute drift** (`daily_run.py:~200`) — Check if signals drifted since last update; mark stale if >3 days.
7. **Save state** (`daily_run.py:~205`) — `state_manager.mutate_state(callback)` → atomic write to `state.json` with fcntl lock.
8. **Render dashboard** (`daily_run_helpers.py:~40`) — Async HTML generation via `dashboard.render_dashboard_files()`.
9. **Dispatch email** (`crash_boundary.py:~30`) — `notifier.send_daily_email(state, old_signals, run_date)`.
10. **Push state to git** (`daily_run_helpers.py:~50`) — Deploy-key-backed git push of `state.json` to remote.

**Return tuple:** `(rc, state, old_signals, run_date)` — captured by `main()` for disposition (save on success, crash-email on exception).

### Web Request Path: Trade Mutation

1. **HTTP POST** (e.g. `/trades/open`) → `FastAPI` routes handler (`web/routes/trades/__init__.py:~50`).
2. **Auth middleware** (`web/middleware/auth.py`) — Validate session cookie, bind user to request context.
3. **Pydantic validation** — Request body deserialization; 422 errors remapped to 400 with `{"errors": [...]}` format.
4. **Trades service** (`web/services/trades_service.py`) — Stateless validation wrapper.
5. **Hex boundary:** Call `sizing_engine.compute_next_position(...)` to validate size against risk.
6. **Mutate state** (`state_manager.mutate_state(callback)`) — Inside callback: fetch current position, compute new position, call `record_trade()`, assign `state['signals'][symbol].position_after`.
7. **fcntl lock** — `state_manager.io._atomic_write()` acquires LOCK_EX during write; daily run blocks if already held.
8. **Response** — Return 200 + HTML fragment for HTMX to swap into the DOM.

### Alert Evaluation Path

1. **Post-save** (`daily_loop.py:~60`) — After `save_state`, call `_evaluate_paper_trade_alerts(state, dashboard_url)`.
2. **Per-position analysis** (`paper_trade_alerts.py:~50`) — For each open position:
   - Get today's OHLCV candle (from the earlier fetch in step 4b).
   - Call `alert_engine.compute_alert_state(side, low, high, close, stop, atr)` → HIT/APPROACHING/CLEAR.
3. **Email if changed** — If state changed from previous run (e.g., CLEAR → APPROACHING), trigger email via `notifier.send_alert_email()`.

**State Management:**
- All state mutations flow through `state_manager.mutate_state(callback)` which holds an advisory fcntl.LOCK_EX lock.
- Intra-process reentrancy is prevented by storing the lock FD in a module-level variable and checking it before re-locking.
- Inter-process (web + daily run) coordination is also via fcntl; the OS enforces mutual exclusion.
- All state reads are via `state_manager.load_state()` which deserializes fresh from `state.json`.

## Key Abstractions

**Position (TypedDict):**
- Purpose: Represent an open trade with entry, stop, pyramid state.
- Examples: `state['signals']['SPI200']['position']`
- Pattern: Nested dict with `side`, `entry_price`, `contracts`, `stop_price`, `pyramid_tier`, `open_date`.

**Signal (dict or int):**
- Purpose: Encode the vote result for a market.
- Examples: `state['signals']['SPI200']['signal']` → 1 (LONG), -1 (SHORT), 0 (FLAT).
- Pattern: Read tolerates int OR dict (legacy shape); always writes nested dict with `signal`, `last_scalars`, `indicator_scalars`, `ohlc_window`.

**Equity History (list[dict]):**
- Purpose: Daily P&L ledger.
- Examples: `state['equity_history']` → `[{"date": "2026-05-15", "unrealised": "1234.56", "realised": "-12.34"}, ...]`
- Pattern: Appended by `pnl_engine.update_equity_history()` after every daily run.

**Trade Record (dict):**
- Purpose: Ledger entry for a single round-trip (entry + close or partial close).
- Examples: `state['trade_log']['SPI200']` → list of `{"entry_date": ..., "close_date": ..., "entry_price": ..., "exit_price": ..., "realised_pnl": ...}`
- Pattern: Created by `sizing_engine.ClosedTrade` and appended via `state_manager.record_trade()`.

**Indicator Scalars (dict):**
- Purpose: Store the most recent ATR, ADX, Mom values for display.
- Examples: `state['signals']['SPI200']['indicator_scalars']` → `{"atr": 45.67, "adx": 32.1, "mom_21": 0.98, ...}`
- Pattern: Written every run to cache latest for email/dashboard rendering.

## Entry Points

**`main.py:183`** — Command-line entry point:
- Triggers: `python main.py [flags]`
- Responsibilities: CLI arg parsing, exception boundary, dispatch to mode handler (--reset, --force-email, --once, or default+scheduler).

**`daily_loop.py:53-57` (`run_daily_check`)**:
- Triggers: Called by scheduler via `scheduler_driver._run_schedule_loop()`, or by main() for --once/--force-email.
- Responsibilities: Wraps the service facade which delegates to `daily_run._run_daily_check_impl()`.

**`web/app.py:~200` (FastAPI app factory)**:
- Triggers: `uvicorn web.app:app --port 8080`
- Responsibilities: Instantiate FastAPI, register middleware, register routes, validate WEB_AUTH_SECRET.

**`backtest/cli.py:~50` (`main`)**:
- Triggers: `python -m backtest [--symbol SPI200] [--from 2025-01-01] [--to 2026-01-01]`
- Responsibilities: Backtest entry point; fetch historical OHLCV, replay, compute signals, render report.

## Architectural Constraints

- **Threading:** Single-threaded sync core. Web layer is async-IO (Starlette event loop) but never calls sync Python engines directly — only reads state via `load_state()`.
- **Global state:** Module-level singletons include:
  - `main._LAST_LOADED_STATE` — cached state for crash-email summary (tests reset it).
  - `data_fetcher._yf` — memoized yfinance module (lazy import to avoid cold-start cost).
  - `state_manager.io._lock_fd` — fcntl lock file descriptor (intra-process reentrancy guard).
  - `services.orchestration._daily_run_service`, etc. — injected service facades.
- **Circular imports:** Prevented by late-binding discipline:
  - Orchestration modules (`daily_run`, `crash_boundary`, `scheduler_driver`) re-resolve `main` module names at call time, not import time.
  - Web routes avoid importing pure-math engines at module top; imports are local or deferred.
  - Never-crash wrappers (`_send_email_never_crash`, `_render_dashboard_never_crash`) import notifier / dashboard inside the try block (C-2 pattern).
- **AST enforcement:** AST regression tests block forbidden imports:
  - `tests/test_signal_engine.py::FORBIDDEN_MODULES_STDLIB_ONLY` — signal_engine, sizing_engine, pnl_engine, alert_engine must not import I/O modules.
  - `tests/test_data_fetcher.py` — data_fetcher must not import signal_engine, sizing_engine.
  - `tests/test_web_healthz.py::TestWebHexBoundary` — web routes must not import signal_engine, sizing_engine (except trades.py which is allowed).
- **Fcntl lock:** All `state_manager` writes acquire an advisory lock. Web POST handlers and daily run both respect the lock; OS enforces mutual exclusion.

## Anti-Patterns

### Missing Error Recovery on Stale Data

**What happens:** If `data_fetcher.fetch_ohlcv()` succeeds but returns a DataFrame with NaN in the final bar (e.g., due to a delayed market data feed), the signal logic propagates NaN and produces FLAT incorrectly. The codebase does NOT pre-fetch to refill NaN bars.

**Why it's wrong:** Positions don't close when they should; trades drift silently. Operator discovers the problem hours later in the daily email (if signal drifted) or not at all.

**Do this instead:** After `fetch_ohlcv()` returns, check `df.iloc[-1].isna().any()` before calling `compute_indicators()`. If detected, add a DEBUG log line and optionally retry the fetch with a backoff. Example: `data_fetcher.py:~200` should include a candle-validation step before returning to `daily_run._run_daily_check_impl()`.

### Bare `except Exception:` in Critical Paths

**What happens:** Three modules use bare `except Exception:` to survive failures gracefully:
- `daily_run_helpers._render_dashboard_never_crash()` — dashboard HTML render failure doesn't crash the run.
- `crash_boundary._send_email_never_crash()` — email dispatch failure doesn't crash the run.
- `scheduler_driver._run_daily_check_caught()` — one bad run doesn't stop the scheduler loop.

**Why it's allowed here:** Dashboard and email are cosmetic/communication artefacts. State is already persisted; the core trading logic is safe. Scheduler must survive transient failures to retry next cycle.

**Do NOT copy this pattern elsewhere:** It's only correct in those three locations. Anywhere else is a code smell that the real error should be caught and handled explicitly.

### State Mutation Without Fcntl Lock

**What happens:** `state_manager.save_state(state)` exists for backward compat but should never be called directly inside a callback. It would hold the lock across user code and risk deadlock if that code tries to call `mutate_state()` again (reentrancy).

**Why it's wrong:** Deadlock between web handler and daily run if either tries to write state at the same time.

**Do this instead:** Always use `state_manager.mutate_state(callback)` which holds the lock only during the callback. The callback can call `append_warning()`, `record_trade()`, etc., which internally call `save_state()` UNLOCKED. Example: `main.py:144-144` shows the correct pattern.

## Error Handling

**Strategy:** Typed-exception boundary at `main()` with fallthrough to crash-email dispatch.

**Patterns:**
- `DataFetchError`, `ShortFrameError` → Log WARNING, return rc=2 (data-layer issue, retry advised).
- Unexpected `Exception` → Log ERROR, call `_send_crash_email()` in a nested try/except, return rc=1.
- Never-crash wrappers catch `Exception` ONLY (dashboard, email, scheduler tick) to prevent cosmetic failures from aborting the run.

## Cross-Cutting Concerns

**Logging:**
- Structured logging with module-level `logger = logging.getLogger(__name__)`.
- Prefixed log lines: `[Daily]` (daily run), `[Sched]` (scheduler), `[Web]` (web requests), `[Email]` (notifier), `[Fetch]` (data_fetcher).
- Secret redaction via `system_params.redact_secret()` for all logs that might contain API keys / session tokens.

**Validation:**
- Pydantic for web request bodies (trades, invite links, device names).
- Hand-rolled validation in `state_manager.validation._validate_loaded_state()` for schema checks.
- Signal-engine formula guards against NaN inputs (per Phase 17 D-06).

**Authentication:**
- Shared-secret HTTP basic auth check in middleware (Phase 13).
- TOTP device registration + TOTP code validation on login (Phase 15).
- Magic-link invite tokens with 24-hour expiry (Phase 36).
- Session cookies (signed, HttpOnly, Secure=True in production).

---

*Architecture analysis: 2026-05-15*
