<!-- refreshed: 2026-05-16 -->
# Architecture

**Analysis Date:** 2026-05-16

## System Overview

```text
┌───────────────────────────────────────────────────────────────────┐
│                     CLI Entry Point                               │
│  `main.py`  (thin shim: re-exports, dispatch ladder, crash net)  │
└───────┬──────────────┬───────────────────┬────────────────────────┘
        │              │                   │
        ▼              ▼                   ▼
┌──────────────┐ ┌───────────┐  ┌──────────────────────┐
│ daily_run.py │ │backtest/  │  │  web/ (FastAPI+HTMX)  │
│ (9-step orch)│ │cli.py     │  │  `web/app.py`         │
└──────┬───────┘ └───────────┘  └──────────┬───────────┘
       │                                    │
       ▼                                    ▼
┌──────────────────────────────────────────────────────────────────┐
│                   Pure-Math Hex Layer                            │
│  `signal_engine.py`  `sizing_engine/`  `pnl_engine.py`          │
│  `alert_engine.py`   `system_params.py` (single-source-of-truth)│
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                    I/O Adapter Layer                             │
│  `state_manager/`  `data_fetcher.py`  `auth_store/`             │
│  `notifier/`       `dashboard_renderer/`  `per_user_fanout.py`  │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│         Persistent Storage / External Services                   │
│  `state.json` (global)   `state/users/<uid>/state.json`         │
│  `auth_store/_io.py` (JSON)   Resend API (email)                │
│  yfinance (market data)   news APIs (`news_fetcher.py`)         │
└──────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| main.py | CLI dispatch, re-export shim, crash boundary | `main.py` |
| daily_run.py | 9-step daily orchestration sequence | `daily_run.py` |
| signal_engine.py | ATR/ADX/Mom/RVol indicators + 2-of-3 vote | `signal_engine.py` |
| sizing_engine | Position sizing, stops, pyramid, close logic | `sizing_engine/` |
| pnl_engine.py | P&L computation, entry side cost | `pnl_engine.py` |
| alert_engine.py | Stop-loss and paper trade alert evaluation | `alert_engine.py` |
| system_params.py | All constants — single source of truth | `system_params.py` |
| state_manager | Atomic JSON read/write, migrations, flock | `state_manager/` |
| data_fetcher.py | yfinance OHLCV fetch, error types | `data_fetcher.py` |
| notifier | Email formatting and transport via Resend | `notifier/` |
| dashboard_renderer | HTML dashboard page rendering | `dashboard_renderer/` |
| web | FastAPI+HTMX web adapter (no SPA) | `web/` |
| auth_store | User registry, devices, magic links, TOTP | `auth_store/` |
| backtest | Historical simulation CLI and metrics | `backtest/` |
| per_user_fanout.py | Per-user email dispatch after daily run | `per_user_fanout.py` |
| scheduler_driver.py | APScheduler loop wiring | `scheduler_driver.py` |
| crash_boundary.py | Crash-email and crash-state summary | `crash_boundary.py` |

## Pattern Overview

**Overall:** Hexagonal-lite (ports & adapters with hard boundary enforcement)

**Key Characteristics:**
- Pure-math hex modules (`signal_engine.py`, `sizing_engine/`, `pnl_engine.py`, `alert_engine.py`) contain zero I/O, network, or state imports — stdlib-only
- `system_params.py` is the single source of truth for all constants; never define constants inline in engine modules
- `state_manager/` is the only module permitted to do filesystem I/O; enforced by AST tests
- `web/` is an adapter peer of `notifier/` and `dashboard_renderer/` — forbidden from importing `signal_engine`, `sizing_engine`, `main`, etc.
- Hex boundary violations caught by test suite (`tests/test_web_app_factory.py`)

## Layers

**Pure-Math Hex:**
- Purpose: deterministic signal computation, no side effects
- Location: `signal_engine.py`, `sizing_engine/`, `pnl_engine.py`, `alert_engine.py`
- Contains: indicator math, position sizing formulas, P&L calculation
- Depends on: `system_params.py`, stdlib only
- Used by: `daily_run.py`, `backtest/simulator.py`

**State I/O:**
- Purpose: atomic JSON persistence with flock coordination
- Location: `state_manager/`
- Contains: `io.py` (atomic write kernel), `migrations.py`, `validation.py`, `trades.py`
- Depends on: stdlib only, `system_params.py`
- Used by: `daily_run.py`, `web/routes/trades/`, `web/routes/paper_trades/`

**Orchestration:**
- Purpose: wire hex + I/O, schedule daily run, CLI dispatch
- Location: `main.py`, `daily_run.py`, `daily_loop.py`, `daily_run_helpers.py`, `scheduler_driver.py`
- Contains: 9-step daily orchestration, scheduling loop, CLI parsing
- Depends on: hex layer + state_manager + data_fetcher + notifier
- Used by: systemd (via `python main.py`)

**Notifications:**
- Purpose: email formatting and transport
- Location: `notifier/`
- Contains: `transport.py` (Resend HTTPS), `formatters.py`, `templates.py`, `dispatch.py`, `warnings_fifo.py`
- Depends on: `system_params.py`, stdlib, Resend API
- Used by: `daily_loop.py`, `per_user_fanout.py`

**Web Adapter:**
- Purpose: HTMX dashboard and REST-ish API
- Location: `web/`
- Contains: `app.py` (factory), `middleware/auth.py`, `routes/`, `services/`, `dependencies.py`
- Depends on: FastAPI, `state_manager`, `auth_store`, `dashboard_renderer`
- Used by: uvicorn via systemd (`systemd/trading-signals-web.service`)

**Auth:**
- Purpose: user registry, session cookies, TOTP, device tokens, magic links
- Location: `auth_store/`
- Contains: `_io.py`, `_users.py`, `_devices.py`, `_magic_links.py`, `_schema.py`
- Depends on: stdlib JSON files under `state/users/`
- Used by: `web/middleware/auth.py`, `web/routes/`

## Data Flow

### Daily Run (Scheduled / CLI)

1. `main.py` parses CLI args, calls `run_daily_check(args)` (`daily_loop.py`)
2. `daily_run._run_daily_check_impl` fetches OHLCV via `data_fetcher.fetch_ohlcv` (yfinance)
3. `signal_engine.compute_indicators` computes ATR/ADX/Mom/RVol on OHLCV DataFrame
4. `signal_engine.evaluate_signal` derives LONG/SHORT/FLAT from 2-of-3 momentum vote
5. `sizing_engine` computes position size, stops, pyramid add-on
6. `state_manager.mutate_state` writes updated signals and trade state atomically to `state.json`
7. `alert_engine` evaluates stop-loss and paper trade alerts
8. `daily_loop._dispatch_email_and_maintain_warnings` calls `notifier/dispatch.py` -> Resend API
9. `per_user_fanout.run` dispatches per-user emails for all registered users
10. `dashboard_renderer` renders `dashboard.html` from state

### Web Request Path

1. Browser -> nginx (TLS termination) -> uvicorn -> `web/app.py` FastAPI
2. `AuthMiddleware` (`web/middleware/auth.py`) validates session cookie — 302 redirect on fail
3. Route handler (e.g., `web/routes/dashboard/__init__.py`) calls `web/services/dashboard_service.py`
4. Service reads `state_manager.load_state()` -> returns HTML via `dashboard_renderer`
5. Mutation routes (trades, paper_trades) call `state_manager.mutate_state()` with flock

### Backtest Path

1. `python -m backtest <args>` -> `backtest/cli.py`
2. `backtest/data_fetcher.py` fetches historical OHLCV
3. `backtest/simulator.py` replays bars through `signal_engine` + `sizing_engine`
4. `backtest/metrics.py` computes Sharpe, drawdown, win-rate
5. `backtest/render.py` writes HTML report

**State Management:**
- Single global state in `state.json` (flock-protected atomic writes via `state_manager.mutate_state`)
- Per-user state shards in `state/users/<uid>/state.json`
- All state mutation MUST use `mutate_state()` — direct `save_state()` inside a `mutate_state` callback causes flock deadlock

## Key Abstractions

**`system_params.py` constants:**
- Purpose: all strategy parameters, thresholds, version — never defined elsewhere
- Examples: `ADX_GATE`, `ATR_PERIOD`, `MOM_PERIODS`, `STRATEGY_VERSION`
- File: `system_params.py`

**`mutate_state(fn)` pattern:**
- Purpose: atomic read-modify-write under fcntl.LOCK_EX
- Pattern: caller passes a `fn(fresh_state) -> None` callback; mutate_state handles lock, load, call, save
- File: `state_manager/__init__.py`

**Service singletons:**
- Purpose: separate pure implementation from service wiring for testability
- Examples: `DailyRunService`, `web/services/dashboard_service.py`, `web/services/trades_service.py`
- Files: `services/orchestration.py`, `web/services/`

## Entry Points

**CLI Scheduler:**
- Location: `main.py` -> `main(argv)`
- Triggers: `python main.py` (systemd), cron, direct
- Responsibilities: parse args, dispatch to daily run or schedule loop

**Web Server:**
- Location: `web/app.py` -> `create_app()`
- Triggers: uvicorn via `systemd/trading-signals-web.service`
- Responsibilities: mount all routes, register AuthMiddleware, validate secrets at boot

**Backtest CLI:**
- Location: `backtest/__main__.py` -> `backtest/cli.py`
- Triggers: `python -m backtest`
- Responsibilities: fetch historical data, simulate strategy, render report

## Architectural Constraints

- **Threading:** Single-threaded; `per_user_fanout.run` uses `asyncio.run()` — must NOT be called from inside an existing event loop (FastAPI routes)
- **Global state:** `main._LAST_LOADED_STATE` module attribute (crash-email cache); `state_manager` module-level flock fd per process
- **Hex boundary enforcement:** AST blocklist in `tests/test_signal_engine.py::test_main_no_forbidden_imports` forbids numpy/yfinance/requests/pandas in orchestration modules
- **Decimal money:** All AUD amounts use `Decimal` — no floats; `from decimal import Decimal, ROUND_HALF_UP`
- **2-space indent:** Do NOT run `ruff format` (reflows to 4-space, breaks test gate)
- **File size:** Hard limit 500 lines per file (CLAUDE.md)

## Anti-Patterns

### Calling `save_state()` inside `mutate_state` callback

**What happens:** `save_state()` acquires fcntl.LOCK_EX on a new fd; `mutate_state` already holds the lock on its fd.
**Why it's wrong:** Linux fcntl locks are per-process per-fd; the second acquire on a different fd within the same process hangs.
**Do this instead:** Call `state_manager.mutate_state(fn)` where `fn` mutates the dict in-place. `mutate_state` calls `io._save_state_unlocked` directly.

### Defining constants inline in engine modules

**What happens:** Magic numbers appear directly in `signal_engine.py` or `sizing_engine/`.
**Why it's wrong:** `system_params.py` is the single source of truth — duplicate constants diverge silently.
**Do this instead:** Import from `system_params.py` only.

### Importing hex modules from web layer

**What happens:** `web/routes/*.py` imports `signal_engine` or `sizing_engine` directly.
**Why it's wrong:** Breaks hex isolation; web is a read-only adapter over state.
**Do this instead:** Web routes read from `state_manager.load_state()` and render via `dashboard_renderer`. Only `web/routes/trades/` is permitted to call `sizing_engine` for trade mutation (documented exception).

## Error Handling

**Strategy:** Fail-closed with typed exception hierarchy

**Patterns:**
- `DataFetchError` / `ShortFrameError` from `data_fetcher.py` — caught at orchestrator, exit code 2
- `crash_boundary._send_crash_email` — outer safety net in `main.main()` for unexpected exceptions
- `_render_dashboard_never_crash` in `daily_run_helpers.py` — isolates dashboard render failures
- Fan-out errors logged as warnings; never abort the cycle (T-37-05-10)
- Web: 422 -> 400 remap for Pydantic validation errors via `add_exception_handler`

## Cross-Cutting Concerns

**Logging:** `logging.getLogger(__name__)` in every module; `[Module]` prefix convention (e.g., `[Web]`, `[Fetch]`, `[Sched]`, `[FanOut]`)
**Validation:** `state_manager/validation.py` for state schema; `auth_store/_schema.py` for user schema; Pydantic models in `web/routes/*/` for request bodies
**Authentication:** Cookie-based session + TOTP (`web/middleware/auth.py`); shared-secret + TOTP (`auth_store/`)
**Time zones:** All scheduled times in AWST (`Australia/Perth`); all UTC datetimes are timezone-aware (`datetime.now(timezone.utc)`)

---

*Architecture analysis: 2026-05-16*
