# Technology Stack

**Analysis Date:** 2026-05-15

## Languages

**Primary:**
- Python 3.13 - All core trading engine, signal logic, state management, and web API
- HTML5 - Dashboard templates rendered server-side via `dashboard_renderer/` + HTMX interactivity

**Secondary:**
- JavaScript/HTMX - Client-side interactivity in web dashboard (minimal; mostly server-driven)
- Bash - Deployment and systemd automation (`deploy.sh`, service files)

## Runtime

**Environment:**
- Python 3.13.x (pinned in `.python-version` and `pyproject.toml` — enforced by `deploy.sh`)
- CPython (standard interpreter)
- Runs in `venv` (created at deploy time by `deploy.sh`)

**Package Manager:**
- pip (implicit; via `.venv/bin/pip`)
- Lockfile: `requirements.txt` (compiled production deps), `requirements-dev.txt` (test tooling)

## Frameworks

**Core:**
- FastAPI 0.136.1 - REST API + server-side template rendering (hexagonal adapter layer)
- Uvicorn 0.46.0 - ASGI web server (runs on localhost:8000, reverse-proxied by nginx)

**Scheduling:**
- schedule 1.2.2 - In-process daily task scheduler (runs market-open checks in UTC)

**Testing:**
- pytest 8.3.3 - Test runner (config: `pyproject.toml`)
- pytest-freezer 0.4.9 - Clock mocking for deterministic datetime tests
- pytest-playwright 0.5.2 (dev only) - Browser automation for UAT on production droplet

**Build/Dev:**
- ruff 0.6.9 - Linter + formatter (config: `pyproject.toml`; 2-space indent enforced by `[tool.ruff.format]`)
- Python built-in: `json` (state persistence), `fcntl` (cross-process locking), `tempfile` (atomic writes)

## Key Dependencies

**Critical:**
- pandas 2.3.3 - OHLCV timeseries processing (Phase 23+ parquet cache I/O)
- numpy 2.2.6 - Indicator math (ADX, RSI, momentum calculations in signal_engine)
- yfinance 1.2.0 - Market data fetcher (lazy-imported via Phase 27 #14 deferred mechanism to avoid bloating cold-start)
- requests 2.28.1+ - HTTP client for yfinance + Resend API (see `notifier/transport.py`)
- pyarrow 24.0.0 - Parquet engine for backtest cache serialization (Phase 23)

**Authentication & Security:**
- bcrypt 5.0.0 - Password hashing (legacy; now replaced by itsdangerous + TOTP per Phase 16.1)
- itsdangerous 2.2.0 - Magic-link token serialization + validation (Phase 16.1 auth path)
- pyotp 2.9.0 - TOTP generation + verification (Phase 16.1 multi-factor)
- python-dotenv 1.0.1 - `.env` file loader for local dev (not used in production)

**Infrastructure:**
- PyYAML 6.0.2 - Config deserialization (minimal usage; mostly state/auth JSON)
- qrcode 8.2 - QR code generation for TOTP device enrollment (Phase 16.1)
- pillow 11.3.0 - Image processing for QR codes
- python-multipart 0.0.27 - Form data parsing for FastAPI multipart routes

## Configuration

**Environment:**
- `.env.example` documents required variables (not committed; template only)
- Actual secrets via environment variables at runtime (on droplet: `/home/trader/trading-signals/.env`, sourced by systemd)
- Key required env vars:
  - `WEB_AUTH_USERNAME` - Dashboard login username (validated fail-closed at boot)
  - `WEB_AUTH_SECRET` - FastAPI session secret (≥32 chars; validated at boot)
  - `SIGNALS_EMAIL_TO` - Recipient for daily alert emails
  - `SIGNALS_EMAIL_FROM` - Sender address for Resend (Phase 37 RFC 8058 List-Unsubscribe)
  - `RESEND_API_KEY` - Resend HTTPS API token (redacted in logs per Phase 27 #13)
  - `TZ` - Timezone (must be `UTC` per scheduler_driver.py assertions)
  - `BASE_URL` - Dashboard URL for email links + magic-link generation
  - `OPERATOR_RECOVERY_EMAIL` - Fallback recovery contact (defaults to `mwiriadi@gmail.com` per Phase 16.1)

**Build:**
- `pyproject.toml` - Project metadata + pytest/ruff config
- Ruff config: line-length=100, target-version=py313, 2-space indent, single quotes, isort with `signal_engine` as first-party module

## Platform Requirements

**Development:**
- Python 3.13.x (pyenv/asdf/brew)
- pip-installed venv
- Unix-like shell (bash/zsh) for dev scripts

**Production:**
- Debian-based Linux droplet (Ubuntu 22.04+ per SETUP-DROPLET.md)
- Python 3.13.x (installed via apt or source)
- nginx (reverse proxy; config: `nginx/signals.conf`)
- systemd (service files: `systemd/trading-signals-web.service`, `trading-signals-backup.service`, `trading-signals-backup.timer`)
- UTC timezone enforced at OS level

## Deployment

**Delivery:**
- Git repository (branch protection: must be on `main` per `deploy.sh`)
- Deployed via `deploy.sh` (idempotent bash script; runs `git pull --ff-only` + pip install + systemctl restart)
- No containerization (Docker not used; direct venv on droplet)

**Post-Deploy:**
- Health check via `curl /healthz` (Phase 11 D-25; 10 retries @ 1s intervals)
- State persisted to `state.json` (atomic writes + fsync; JSON format with Decimal handling)
- Auth data persisted to `auth.json` (Phase 16.1; user credentials, TOTP seeds, magic-link tokens)

---

*Stack analysis: 2026-05-15*
