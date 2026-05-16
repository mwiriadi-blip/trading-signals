# Codebase Structure

**Analysis Date:** 2026-05-16

## Directory Layout

```
trading-signals/
├── main.py                    # CLI entry point + re-export shim
├── daily_run.py               # 9-step daily orchestration
├── daily_loop.py              # Service-backed wrappers (run_daily_check etc.)
├── daily_run_helpers.py       # Dashboard render + trade-record helpers
├── scheduler_driver.py        # APScheduler loop
├── cli_parser.py              # Argument parsing seam
├── interactive.py             # TTY/reset prompt helpers
├── crash_boundary.py          # Crash-email safety net
├── state_actions.py           # Accessors for _LAST_LOADED_STATE
├── signal_engine.py           # Pure-math: ATR/ADX/Mom/RVol + signal vote
├── pnl_engine.py              # Pure-math: P&L, entry side cost
├── alert_engine.py            # Pure-math: stop-loss and alert evaluation
├── system_params.py           # ALL constants — single source of truth
├── data_fetcher.py            # yfinance OHLCV fetch adapter
├── news_fetcher.py            # News API fetch adapter
├── news_filter.py             # News relevance filtering
├── paper_trade_alerts.py      # Paper trade alert evaluation seam
├── per_user_fanout.py         # Per-user email dispatch orchestrator
├── dashboard.py               # Legacy dashboard shim (thin wrapper)
├── state.json                 # Global runtime state (flock-protected)
│
├── sizing_engine/             # Pure-math: position sizing package
│   ├── __init__.py
│   ├── _models.py             # Shared dataclasses
│   ├── sizing.py              # Entry sizing
│   ├── stops.py               # Stop-loss logic
│   ├── pyramid.py             # Pyramid add-on logic
│   └── close.py               # Position close logic
│
├── state_manager/             # I/O adapter: atomic JSON persistence
│   ├── __init__.py            # Public API orchestrator
│   ├── io.py                  # Atomic write kernel, flock, backup
│   ├── migrations.py          # Schema migration registry
│   ├── validation.py          # Datetime guards, trade validators
│   └── trades.py              # Record helpers (append_warning etc.)
│
├── auth_store/                # Auth: user registry, TOTP, devices
│   ├── __init__.py
│   ├── _io.py                 # JSON read/write for auth data
│   ├── _schema.py             # User/device schema constants
│   ├── _users.py              # User CRUD
│   ├── _devices.py            # Trusted device tokens
│   └── _magic_links.py        # Magic link generation/validation
│
├── notifier/                  # Email adapter (Resend HTTPS API)
│   ├── __init__.py
│   ├── transport.py           # HTTP transport to Resend
│   ├── dispatch.py            # Dispatch orchestration
│   ├── formatters.py          # Data formatting helpers
│   ├── templates.py           # Email HTML templates
│   ├── templates_alerts.py    # Alert-specific email templates
│   ├── templates_sections.py  # Reusable template sections
│   └── warnings_fifo.py       # Warning carry-over queue
│
├── dashboard_renderer/        # HTML dashboard rendering
│   ├── __init__.py
│   ├── api.py                 # Public render API
│   ├── pages.py               # Per-page renderers
│   ├── context.py             # Context assembly
│   ├── formatters.py          # Value formatters
│   ├── stats.py               # Stats calculations
│   ├── assets.py              # Inline asset helpers
│   ├── shell.py               # Page shell/layout
│   ├── io.py                  # File write helpers
│   └── components/            # Reusable HTML components
│
├── web/                       # FastAPI+HTMX web adapter
│   ├── __init__.py
│   ├── app.py                 # App factory (create_app)
│   ├── dependencies.py        # FastAPI dependency providers
│   ├── middleware/
│   │   └── auth.py            # Session cookie + TOTP auth middleware
│   ├── routes/
│   │   ├── healthz.py         # GET /healthz
│   │   ├── state.py           # GET /api/state
│   │   ├── reset.py           # POST /reset
│   │   ├── markets.py         # GET /markets
│   │   ├── devices.py         # Device token routes
│   │   ├── news.py            # GET /news
│   │   ├── backtest.py        # GET /backtest
│   │   ├── dashboard/         # Dashboard page routes
│   │   ├── login/             # Login page routes
│   │   ├── totp/              # TOTP verification routes
│   │   ├── trades/            # Trade mutation routes (POST)
│   │   ├── paper_trades/      # Paper trade routes
│   │   ├── invite/            # Invite token routes
│   │   └── admin/             # Admin panel routes
│   └── services/
│       ├── dashboard_service.py
│       ├── trades_service.py
│       ├── paper_trades_service.py
│       └── totp_service.py
│
├── backtest/                  # Historical simulation package
│   ├── __init__.py
│   ├── __main__.py            # python -m backtest entry
│   ├── cli.py                 # Argument parsing + dispatch
│   ├── data_fetcher.py        # Historical OHLCV fetch
│   ├── simulator.py           # Bar-by-bar replay engine
│   ├── metrics.py             # Sharpe, drawdown, win-rate
│   └── render.py              # HTML report renderer
│
├── services/                  # Orchestration service objects
│   ├── __init__.py
│   └── orchestration.py       # DailyRunService, SignalEvaluationService etc.
│
├── state/                     # Runtime state directory
│   └── users/                 # Per-user state shards
│       └── <uid>/
│           └── state.json     # Per-user signals + preferences
│
├── systemd/                   # Systemd unit files
│   ├── trading-signals-web.service
│   ├── trading-signals-backup.service
│   └── trading-signals-backup.timer
│
├── nginx/                     # nginx config snippets
├── docs/                      # Operator documentation
├── scripts/                   # Utility scripts
│
├── tests/                     # Pytest test suite
│   ├── conftest.py
│   ├── fixtures/              # Static test fixtures (JSON, HTML)
│   ├── oracle/                # Determinism oracle + golden files
│   ├── determinism/           # Determinism test helpers
│   └── uat/                   # Playwright UAT tests
│
├── .planning/                 # GSD workflow planning docs
│   ├── codebase/              # Codebase maps (this file)
│   ├── phases/                # Phase plans and reviews
│   ├── milestones/            # Milestone archives
│   ├── debug/                 # Debug investigations
│   └── research/              # Research notes
│
├── dashboard_legacy/          # Retired legacy dashboard (stub only)
├── pyproject.toml             # Project metadata + ruff config
├── requirements.txt           # Production dependencies
├── requirements-dev.txt       # Dev dependencies
├── deploy.sh                  # Deployment script
└── CLAUDE.md                  # Project rules for Claude
```

## Directory Purposes

**`sizing_engine/`:**
- Purpose: pure-math position sizing — no I/O, no state
- Contains: entry sizing, stop-loss, pyramid add-on, close logic, shared models
- Key files: `sizing_engine/sizing.py`, `sizing_engine/stops.py`

**`state_manager/`:**
- Purpose: the ONE module allowed to do filesystem I/O on `state.json`
- Contains: atomic write kernel, schema migrations, validation, trade record helpers
- Key files: `state_manager/__init__.py` (public API), `state_manager/io.py` (flock kernel)

**`auth_store/`:**
- Purpose: user registry, session state, device trust, TOTP, magic links
- Contains: JSON-backed user/device records under `state/users/`
- Key files: `auth_store/__init__.py`, `auth_store/_users.py`

**`notifier/`:**
- Purpose: email output adapter — formats and sends via Resend HTTPS API only
- Contains: transport, dispatch, HTML email templates, warnings FIFO
- Key files: `notifier/transport.py`, `notifier/dispatch.py`

**`dashboard_renderer/`:**
- Purpose: renders `dashboard.html` static files from state dict
- Contains: page renderers, context assembly, formatters, HTML components
- Key files: `dashboard_renderer/api.py`, `dashboard_renderer/pages.py`

**`web/`:**
- Purpose: FastAPI+HTMX web server — read-only state views + mutation endpoints
- Contains: app factory, auth middleware, route packages, service objects
- Key files: `web/app.py`, `web/middleware/auth.py`, `web/routes/dashboard/`

**`backtest/`:**
- Purpose: standalone historical simulation, run via `python -m backtest`
- Contains: data fetch, bar replay through signal+sizing engines, metrics, HTML report
- Key files: `backtest/simulator.py`, `backtest/metrics.py`

**`tests/`:**
- Purpose: full pytest suite covering hex boundaries, state, web, UAT
- Contains: unit tests, integration tests, oracle golden files, Playwright UAT
- Key files: `tests/conftest.py`, `tests/uat/`, `tests/oracle/`

**`state/users/`:**
- Purpose: per-user state shards written by `per_user_fanout.py` and `auth_store`
- Contains: per-user `state.json` with signals copy + market preferences
- Generated: Yes (at runtime)

**`systemd/`:**
- Purpose: service unit files for production deployment
- Contains: web service, backup timer/service
- Committed: Yes

## Key File Locations

**Entry Points:**
- `main.py`: CLI scheduler entry point
- `web/app.py`: FastAPI app factory (`create_app()`)
- `backtest/__main__.py`: Backtest CLI entry

**Configuration:**
- `system_params.py`: ALL strategy constants and thresholds
- `pyproject.toml`: Project metadata, ruff lint config
- `requirements.txt`: Production dependencies

**Core Logic:**
- `signal_engine.py`: ATR/ADX/Mom/RVol + 2-of-3 vote
- `daily_run.py`: 9-step daily orchestration sequence
- `state_manager/__init__.py`: Public state API (`mutate_state`, `load_state`)
- `per_user_fanout.py`: Per-user email fan-out orchestrator

**Testing:**
- `tests/conftest.py`: Shared fixtures
- `tests/oracle/`: Golden-file determinism tests
- `tests/uat/`: Playwright end-to-end tests

## Naming Conventions

**Files:**
- Seam modules at root: `daily_run.py`, `crash_boundary.py`, `cli_parser.py` (verb-noun)
- Private submodule files prefixed with `_`: `_models.py`, `_io.py`, `_users.py`
- Route packages: noun directories matching resource (`trades/`, `dashboard/`, `totp/`)
- Renderers: `_renderers.py` within route packages
- Models: `_models.py` within route packages

**Directories:**
- Engine packages: `<noun>_engine/` (e.g., `sizing_engine/`, `signal_engine` is a flat file)
- Adapter packages: noun (e.g., `notifier/`, `auth_store/`, `web/`)
- Web routes: `web/routes/<resource>/`

## Where to Add New Code

**New signal indicator:**
- Implementation: `signal_engine.py` (pure math only)
- Constants: `system_params.py`
- Tests: `tests/test_signal_engine_*.py`

**New web route:**
- Route package: `web/routes/<resource>/__init__.py`
- Renderers: `web/routes/<resource>/_renderers.py`
- Models: `web/routes/<resource>/_models.py`
- Service: `web/services/<resource>_service.py`
- Register in: `web/app.py`

**New email template:**
- Template: `notifier/templates.py` or `notifier/templates_alerts.py`
- Dispatch: `notifier/dispatch.py`

**New state field:**
- Add migration in: `state_manager/migrations.py`
- Update validation in: `state_manager/validation.py`

**New utility/helper:**
- Shared helpers: root-level `.py` file if orchestration seam
- Pure math: appropriate `*_engine/` package
- Web-specific: `web/services/` or `web/dependencies.py`

## Special Directories

**`.planning/`:**
- Purpose: GSD workflow planning, phase plans, codebase maps
- Generated: Partially (codebase maps auto-generated)
- Committed: Yes

**`state/`:**
- Purpose: runtime persistence directory
- Generated: Yes (at runtime by state_manager and auth_store)
- Committed: Partially (directory committed, `state/users/` gitignored)

**`dashboard_legacy/`:**
- Purpose: retired legacy dashboard package (stub `__init__.py` only)
- Generated: No
- Committed: Yes (stub preserved to avoid import errors during transition)

---

*Structure analysis: 2026-05-16*
