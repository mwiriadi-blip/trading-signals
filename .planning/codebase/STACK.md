# Technology Stack

**Analysis Date:** 2026-05-16

## Languages

**Primary:**
- Python 3.13 (required: `>=3.13,<3.14`) — all core trading engine, signal logic, state management, web API
- HTML5 — dashboard templates rendered server-side via `dashboard_renderer/` + HTMX interactivity

**Secondary:**
- JavaScript/HTMX — client-side interactivity in web dashboard (minimal; server-driven)
- Bash — deployment and systemd automation (`deploy.sh`, service files)

## Runtime

**Environment:**
- CPython 3.13.x (pinned; enforced by `pyproject.toml` and `deploy.sh`)
- Runs in `.venv` (virtualenv; created at deploy time by `deploy.sh`)
- Deployment OS: Ubuntu 22.04/24.04 on DigitalOcean droplet

**Package Manager:**
- pip (via `.venv/bin/pip`)
- Lockfile: `requirements.txt` (compiled production deps), `requirements-dev.txt` (test tooling only)

## Frameworks

**Web:**
- FastAPI 0.136.1 — ASGI web framework; HTMX-only, no SPA
- uvicorn[standard] 0.46.0 — ASGI server (single worker on `127.0.0.1:8000`, systemd managed)

**Scheduling:**
- schedule 1.2.2 — in-process daily job scheduler (`scheduler_driver.py`), runs market-open checks in UTC

**Data / Numerics:**
- pandas 2.3.3 — OHLCV timeseries processing
- numpy 2.2.6 — indicator math (ADX, RSI, momentum in `signal_engine.py`)
- pyarrow 24.0.0 — Parquet engine for backtest cache serialization (`backtest/`)

## Testing

**Runner:**
- pytest 8.3.3 — unit/integration suite (config: `pyproject.toml`)
- pytest-freezer 0.4.9 — deterministic datetime freezing
- pytest-playwright 0.5.2 (dev only) — Chromium browser UAT against live production droplet

**UAT:**
- Gated with `@pytest.mark.uat`; excluded from default `pytest` invocation
- Run: `pytest -m uat`
- Targets production droplet `signals.mwiriadi.me` (no staging env)

## Build / Dev Tools

**Linter/Formatter:**
- ruff 0.6.9 — lint (`E,F,W,I,B,UP`) + isort; line-length 100, target py313
- **CRITICAL: `ruff format` is PROHIBITED** — reflows to 4-space indent; project requires 2-space

**Config files:**
- `pyproject.toml` — project metadata, pytest options, ruff config
- `.env` / `python-dotenv 1.0.1` — runtime secrets (loaded in `main.py` only via local import)

## Key Dependencies

**Auth / Security:**
- bcrypt 5.0.0 — password hashing
- pyotp 2.9.0 — TOTP (RFC 6238) generation and verification
- itsdangerous 2.2.0 — signed session tokens (URLSafeTimedSerializer)
- python-multipart 0.0.27 — form data parsing for FastAPI login POSTs

**HTTP Client:**
- httpx 0.28.1 — outbound HTTP (Resend email API via `notifier/transport.py`)

**Market Data:**
- yfinance 1.2.0 — Yahoo Finance OHLC + news fetch (lazy-imported via `_get_yf()` accessor)

**QR / Image:**
- qrcode 8.2 — TOTP provisioning URI → QR image for device enrollment
- pillow 11.3.0 — image rendering backend for qrcode

**Serialisation:**
- PyYAML 6.0.2 — config/fixture loading

## Infrastructure

**Reverse Proxy:** nginx 1.24 (`nginx/signals.conf`) — TLS termination → uvicorn on 127.0.0.1:8000
**TLS:** Let's Encrypt via certbot (`certonly --standalone`), auto-renewed via certbot systemd timer
**Process Management:** systemd — `trading-signals-web.service`, `trading-signals-backup.service/.timer`
**State Storage:** JSON file (`state.json`) with fcntl flock atomic writes (`state_manager/`)

## Platform Requirements

**Development:**
- Python 3.13.x (exact minor; pyenv/asdf/brew)
- `.venv` virtualenv
- Playwright Chromium (`playwright install chromium`) for UAT only

**Production:**
- DigitalOcean droplet, Ubuntu 22.04/24.04
- nginx 1.24+, systemd, certbot
- Domain: `signals.mwiriadi.me` (Cloudflare DNS; grey-cloud during cert issuance)
- Deploy: `deploy.sh` (idempotent; branch-checked; health-verified)
- No Docker/containers — direct venv on droplet

---

*Stack analysis: 2026-05-16*
