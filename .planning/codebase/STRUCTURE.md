# Codebase Structure

**Analysis Date:** 2026-05-15

## Directory Layout

```
trading-signals/
├── main.py                      # Entrypoint: CLI parsing, dispatch, exception boundary
├── daily_loop.py                # Service-wired daily run orchestrator (Phase 27 split)
├── daily_run.py                 # 9-step daily sequence implementation
├── daily_run_helpers.py         # Dashboard + git-push helpers
├── signal_engine.py             # Pure-math: ATR, ADX, Mom, RVol, 2-of-3 vote
├── sizing_engine/               # Position sizing subpackage
│   ├── __init__.py              # Core sizing logic
│   ├── _models.py               # ClosedTrade, Position TypedDicts
│   ├── sizing.py                # compute_next_position(), size_contracts()
│   ├── pyramid.py               # Pyramid tier logic
│   ├── close.py                 # Exit logic
│   └── stops.py                 # Stop-loss + ATR-based stops
├── pnl_engine.py                # Pure-math: Decimal P&L (unrealised, realised)
├── alert_engine.py              # Pure-math: stop-loss alert state (HIT/APPROACHING)
├── system_params.py             # Shared constants: periods, thresholds, Decimal precision
├── data_fetcher.py              # yfinance OHLCV fetch + retries + rate-limit handling
├── scheduler_driver.py          # schedule library wiring + tick loop
├── crash_boundary.py            # Never-crash wrappers: email dispatch, state summary
├── state_actions.py             # _LAST_LOADED_STATE accessor contract
├── paper_trade_alerts.py        # Post-save alert evaluation
├── per_user_fanout.py           # Phase 37: per-user cycle dispatch
├── cli_parser.py                # Argument parser + flag validation
├── interactive.py               # --reset mode + input prompts
├── state_manager/               # Atomic JSON persistence (fcntl locks)
│   ├── __init__.py              # Public API orchestrator (load_state, save_state, mutate_state)
│   ├── io.py                    # _atomic_write, tempfile + fsync, corruption recovery
│   ├── migrations.py            # Schema migration chain v1→v12
│   ├── validation.py            # StateV12 TypedDict, _validate_loaded_state()
│   └── trades.py                # record_trade(), append_warning(), clear_warnings()
├── notifier/                    # Email dispatch via Resend
│   ├── __init__.py              # Module API
│   ├── dispatch.py              # send_daily_email(), send_crash_email()
│   ├── transport.py             # Resend HTTP client with timeout guards
│   ├── templates.py             # Email body templates (Jinja2)
│   ├── templates_alerts.py      # Alert-specific templates
│   ├── templates_sections.py    # Reusable email sections
│   ├── formatters.py            # PnL, trade, position formatters
│   ├── crash_path.py            # Crash-email body builder
│   └── warnings_fifo.py         # Warning deduplication (FIFO 10-entry ring)
├── auth_store/                  # User auth + TOTP + invites
│   ├── __init__.py              # Public API
│   ├── _users.py                # User model, session, TOTP devices
│   ├── _io.py                   # Persist auth_store.json
│   ├── _devices.py              # TOTP device registration
│   ├── _magic_links.py          # Invite token generation + expiry
│   └── _schema.py               # User TypedDict definitions
├── web/                         # FastAPI + HTMX dashboard
│   ├── app.py                   # FastAPI factory, middleware, routes
│   ├── dependencies.py          # Dependency injectors (request state)
│   ├── middleware/
│   │   └── auth.py              # Auth cookie validation, session binding
│   ├── services/                # Web-layer services (stateless facades)
│   │   ├── __init__.py
│   │   ├── dashboard_service.py
│   │   ├── trades_service.py
│   │   ├── paper_trades_service.py
│   │   └── totp_service.py
│   └── routes/                  # HTTP endpoint handlers
│       ├── __init__.py
│       ├── healthz.py           # GET /healthz
│       ├── state.py             # GET /api/state
│       ├── dashboard/           # GET /, dashboard HTML + HTMX
│       │   ├── __init__.py
│       │   └── _renderers.py    # Jinja2 dashboard templates
│       ├── trades/              # POST /trades/{open,close,modify}
│       │   ├── __init__.py
│       │   ├── _models.py       # Pydantic request/response schemas
│       │   └── _renderers.py    # HTML fragments for HTMX swaps
│       ├── paper_trades/        # POST /paper-trades/{enter,exit}
│       │   ├── __init__.py
│       │   ├── _models.py
│       │   └── _renderers.py
│       ├── login/               # POST /login (shared-secret auth)
│       │   ├── __init__.py
│       │   └── _renderers.py
│       ├── totp/                # POST /totp/{setup,verify}
│       │   ├── __init__.py
│       │   └── _renderers.py
│       ├── invite/              # POST /invite/{create,accept}
│       │   ├── __init__.py
│       │   └── _renderers.py
│       ├── admin/               # GET /admin/{users,settings}
│       │   ├── __init__.py
│       │   ├── _models.py
│       │   └── _renderers.py
│       ├── devices.py           # GET /devices, POST /devices/revoke
│       ├── markets.py           # POST /markets/{enable,disable}
│       ├── reset.py             # POST /reset (dangerous: wipe all trades)
│       └── backtest.py          # POST /backtest/run (async backtest)
├── dashboard_renderer/          # Async HTML generation
│   ├── __init__.py              # render_dashboard_files()
│   ├── api.py                   # Dashboard data aggregation
│   ├── context.py               # Template context building
│   ├── pages.py                 # Page-specific rendering
│   ├── formatters.py            # Value/chart formatters
│   ├── io.py                    # File write + safety checks
│   ├── assets.py                # CSS/JS bundling
│   ├── stats.py                 # Statistical summaries
│   └── shell.py                 # Shell-script rendering (dashboard updates)
├── dashboard.py                 # Async entry point to dashboard_renderer
├── dashboard_legacy/            # (Deprecated: old dashboard code)
├── backtest/                    # Historical simulator
│   ├── __init__.py
│   ├── cli.py                   # Backtest CLI (entry point)
│   ├── simulator.py             # Replay engine: fetch history, compute signals
│   ├── render.py                # Backtest report HTML generation
│   ├── metrics.py               # Sharpe, max-drawdown, win-rate calcs
│   ├── data_fetcher.py          # Historical OHLCV fetch (mock for tests)
│   └── __main__.py              # `python -m backtest`
├── services/                    # Service orchestration layer
│   ├── __init__.py
│   └── orchestration.py         # DailyRunService, SignalEvaluationService, PostRunService
├── tests/                       # Test suite (~100+ test files)
│   ├── test_signal_engine.py    # Signal engine + AST import boundary checks
│   ├── test_sizing_engine.py    # Position sizing logic
│   ├── test_pnl_engine.py       # P&L calculations
│   ├── test_alert_engine.py     # Stop-loss alerts
│   ├── test_data_fetcher.py     # yfinance mocking + retry behavior
│   ├── test_state_manager.py    # State I/O + migrations
│   ├── test_web_*.py            # Web routes + middleware
│   ├── test_backtest_*.py       # Backtest simulator + metrics
│   ├── test_auth_*.py           # Auth store + TOTP
│   ├── oracle/                  # Reference implementations (Wilder smoothing, etc.)
│   │   └── wilder.py            # Pure-Python ATR oracle for cross-check
│   └── subprocess_helpers_v12.py# Subprocess test utilities
├── .planning/                   # Planning + retrospectives
│   ├── codebase/                # (THIS DIRECTORY)
│   │   ├── ARCHITECTURE.md
│   │   ├── STRUCTURE.md
│   │   ├── CONVENTIONS.md
│   │   ├── TESTING.md
│   │   ├── STACK.md
│   │   ├── INTEGRATIONS.md
│   │   └── CONCERNS.md
│   ├── phases/                  # Phase retrospectives (Phase 1–37)
│   ├── milestones/              # Milestone gate reviews
│   ├── ROADMAP.md               # Quarterly plan
│   └── STATE.md                 # Current state summary
├── .claude/                     # Claude Code configuration
│   ├── CLAUDE.md                # Project rules (2-space indent, Decimal, etc.)
│   ├── LEARNINGS.md             # Bugs + patterns discovered
│   └── skills/                  # (Project-specific agent skills, if any)
├── .github/                     # CI/CD config
│   └── workflows/               # GitHub Actions
├── systemd/                     # Systemd service files
├── nginx/                       # Nginx reverse-proxy config
├── scripts/                     # Utility scripts
├── deploy.sh                    # Deployment script
├── SETUP-DROPLET.md             # Server setup guide
├── SPEC.md                      # Requirements specification (Phase 0)
├── README.md                    # Quick start
├── AGENTS.md                    # Agent definitions (for Claude orchestration)
├── pyproject.toml               # Python project config
├── requirements.txt             # Python dependencies
├── requirements-dev.txt         # Dev-only dependencies
├── .env.example                 # Environment variable template
└── state.json                   # (Runtime: atomic state file, git-tracked)
```

## Directory Purposes

**`main.py`:**
- Purpose: CLI entrypoint with mode dispatch (--reset, --once, --force-email, or default+scheduler)
- Contains: `main(argv)` function, module re-exports for tests
- Key functions: `main()`, sys.exit() handler

**`daily_run.py`:**
- Purpose: 9-step daily orchestration sequence implementation
- Contains: `_run_daily_check_impl()` which owns per-instrument loop, state mutation, logging
- Key functions: `_compute_run_date()`, `_run_daily_check_impl()`

**`signal_engine.py`:**
- Purpose: Pure-math indicator computation
- Contains: ATR, ADX, Mom, RVol calculation; 2-of-3 vote; Wilder smoothing
- Key functions: `compute_indicators()`, `vote()`

**`sizing_engine/`:**
- Purpose: Position sizing, pyramid logic, stop-loss computation
- Contains: `ClosedTrade` TypedDict, `compute_next_position()`, pyramid tiers
- Key files: `__init__.py` (core), `_models.py` (Position TypedDict), `pyramid.py`, `stops.py`

**`state_manager/`:**
- Purpose: Atomic JSON persistence with fcntl locks and schema migration
- Contains: `load_state()`, `save_state()`, `mutate_state()`, corruption recovery, migrations v1→v12
- Key files: `__init__.py` (orchestrator), `io.py` (atomic writes), `migrations.py` (schema chain)

**`data_fetcher.py`:**
- Purpose: yfinance OHLCV fetch with retries, rate-limit handling, timeout guards
- Contains: `fetch_ohlcv(symbol, retries=3, backoff_s=10.0)`, retry loop, exception narrowing
- Key functions: `fetch_ohlcv()`, `_get_yf()` (lazy import)

**`notifier/`:**
- Purpose: Email dispatch via Resend API
- Contains: Daily email templates, crash email templates, formatters, redaction
- Key files: `dispatch.py` (entry point), `templates.py` (body templates), `transport.py` (HTTP)

**`auth_store/`:**
- Purpose: User authentication (shared-secret + TOTP) and invite tokens
- Contains: User model, session persistence, TOTP device registration, magic-link tokens
- Key files: `_users.py` (core), `_io.py` (JSON persistence), `_devices.py` (TOTP)

**`web/`:**
- Purpose: FastAPI web server with HTMX dashboard and mutations
- Contains: Routes for dashboard, trades, TOTP, invites, admin; middleware for auth
- Key files: `app.py` (factory), `routes/dashboard/` (GET /), `routes/trades/` (POST /trades/*)

**`dashboard_renderer/`:**
- Purpose: Async HTML file generation for static dashboard HTML
- Contains: Jinja2 templates, async rendering, CSS/JS bundling
- Key files: `__init__.py` (render_dashboard_files), `api.py` (data aggregation), `pages.py` (per-page)

**`backtest/`:**
- Purpose: Historical simulator for testing strategies
- Contains: Replay engine, P&L calculation, report generation
- Key files: `cli.py` (entry point), `simulator.py` (replay logic), `render.py` (report HTML)

**`tests/`:**
- Purpose: Comprehensive test suite with import boundary checks
- Contains: Unit tests, integration tests, AST regression tests, fixtures, test oracles
- Key files: `test_signal_engine.py` (AST boundary enforcement), `test_web_*.py` (web layer), `oracle/wilder.py` (reference implementation)

## Key File Locations

**Entry Points:**
- `main.py`: Main CLI entry point (ENTRYPOINT in systemd service)
- `web/app.py`: Web server factory (uvicorn entry point)
- `backtest/cli.py`: Backtest CLI (`python -m backtest`)

**Configuration:**
- `system_params.py`: All constants (indicator periods, thresholds, money precision)
- `.env.example`: Environment variable template (copy to `.env` for local setup)
- `CLAUDE.md`: Project-specific rules (2-space indent, Decimal, etc.)

**Core Logic:**
- `signal_engine.py`: Indicator computation
- `sizing_engine/__init__.py`: Position sizing
- `daily_run.py`: Daily orchestration
- `state_manager/__init__.py`: State mutations

**Testing:**
- `tests/test_signal_engine.py`: Signal engine + AST import boundaries
- `tests/test_web_*.py`: Web routes
- `tests/test_state_manager.py`: State persistence
- `tests/oracle/wilder.py`: Reference indicator oracle

## Naming Conventions

**Files:**
- Modules: `lowercase_with_underscores.py` (e.g., `signal_engine.py`, `data_fetcher.py`)
- Packages: `lowercase_with_underscores/` (e.g., `sizing_engine/`, `state_manager/`, `auth_store/`)
- Private modules (module-internal): `_leading_underscore.py` (e.g., `_models.py`, `_renderers.py`)

**Directories:**
- Core modules: Root level (e.g., `signal_engine.py`, `data_fetcher.py`)
- Subpackages: `module_name/` with `__init__.py` exporting public API (e.g., `sizing_engine/__init__.py`, `state_manager/__init__.py`)
- Route handlers: `web/routes/feature_name/` with `__init__.py`, `_models.py`, `_renderers.py` (e.g., `web/routes/trades/`, `web/routes/admin/`)

**Test Files:**
- Unit tests: `test_module_name.py` (e.g., `test_signal_engine.py`, `test_data_fetcher.py`)
- Test subdirectories: `tests/` (all tests in a single directory, not nested by module)
- Fixtures: `conftest.py` (pytest fixture definitions)
- Test oracles/references: `oracle/` (pure implementations for cross-check)

**Naming Patterns:**
- Private functions: `_leading_underscore()` (e.g., `_wilder_smooth()`, `_compute_run_date()`)
- Service classes: `*Service` (e.g., `DailyRunService`, `TradesService`)
- HTTP routes: `/api/resource` or `/resource/{action}` (e.g., `/trades/open`, `/totp/verify`)
- TypedDicts: `PascalCase` (e.g., `Position`, `StateV12`, `ClosedTrade`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `ADX_GATE`, `ATR_PERIOD`, `HTTP_TIMEOUT_S`)

## Where to Add New Code

**New Feature (e.g., new trading signal):**
- Implementation: `signal_engine.py` (add indicator function + formula)
- Integration: `daily_run.py` (add to per-instrument loop)
- Tests: `tests/test_signal_engine.py` (add unit test for new indicator)
- System params: `system_params.py` (add period constant if needed)

**New Web Endpoint (e.g., new dashboard section):**
- Route handler: `web/routes/new_feature/__init__.py`
- Models: `web/routes/new_feature/_models.py` (Pydantic request/response schemas)
- Templates: `web/routes/new_feature/_renderers.py` (Jinja2 HTML fragments)
- Service: `web/services/new_feature_service.py` (stateless business logic)
- Tests: `tests/test_web_new_feature.py`

**New Position-Sizing Rule:**
- Implementation: `sizing_engine/new_rule.py` (pure-math logic)
- Integration: `sizing_engine/__init__.py` (call in `compute_next_position()`)
- Tests: `tests/test_sizing_engine.py`

**Utilities/Helpers (not tied to a specific domain):**
- Shared helpers: Create under `state_manager/` (if state-related) or `notifier/` (if email-related), or root level as a standalone module
- File location: Root-level module (e.g., `helper_name.py`) for cross-cutting concerns; subdirectory modules for domain-specific helpers

**New Test:**
- All tests go into `tests/` directory (not nested by feature)
- Naming: `test_focus_area.py` (e.g., `test_new_feature.py`)
- Fixtures: Add to `tests/conftest.py` if reusable; otherwise inline in the test file

## Special Directories

**`.planning/codebase/`:**
- Purpose: Generated architecture/structure/conventions documents
- Generated: Yes (by `/gsd-map-codebase`)
- Committed: Yes (committed to git for future reference)
- Contents: ARCHITECTURE.md, STRUCTURE.md, CONVENTIONS.md, TESTING.md, STACK.md, INTEGRATIONS.md, CONCERNS.md

**`.planning/phases/`:**
- Purpose: Phase retrospectives and implementation notes
- Generated: No (hand-authored)
- Committed: Yes
- Contents: Phase 1–37 decision logs, research notes, trade-offs

**`.pytest_cache/` and `__pycache__/`:**
- Purpose: Cache files generated by pytest and Python bytecode
- Generated: Yes (runtime)
- Committed: No (in .gitignore)

**`state.json`:**
- Purpose: Single source of truth for trading state (positions, equity, trades, warnings)
- Generated: Yes (by `state_manager`)
- Committed: Yes (git-tracked for operator visibility and crash recovery)
- Format: JSON with atomic writes via fcntl lock + tempfile + fsync

**`.env`:**
- Purpose: Environment variables for secrets (API keys, session secret, usernames)
- Generated: No (operator creates from `.env.example`)
- Committed: No (in .gitignore; secrets should never be committed)
- Contents: WEB_AUTH_USERNAME, WEB_AUTH_SECRET, RESEND_API_KEY, TOTP_ISSUER, OPERATOR_RECOVERY_EMAIL

---

*Structure analysis: 2026-05-15*
