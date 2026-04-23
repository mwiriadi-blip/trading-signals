# Trading Signals

[![Daily signal check](https://github.com/${{GITHUB_REPOSITORY}}/actions/workflows/daily.yml/badge.svg)](https://github.com/${{GITHUB_REPOSITORY}}/actions/workflows/daily.yml)

Python signal-only trading app. Computes daily ATR/ADX/momentum signals for
SPI 200 (`^AXJO`) and AUD/USD (`AUDUSD=X`), persists state, renders a
self-contained dashboard, and emails a weekday report at 08:00 AWST.
**Never places live trades.**

## Setup

Before first push: **replace the literal `${{GITHUB_REPOSITORY}}` in the badge
URL above with your own `owner/repo` slug** (e.g. `mwiriadi/trading-signals`).
This is a one-time edit; GitHub does not substitute the placeholder for you
in static files. See `docs/DEPLOY.md` Troubleshooting → "README badge not
rendering" for details.

## Quickstart

```bash
pip install -r requirements.txt

python main.py --once      # one-shot run (GitHub Actions / cron mode)
python main.py             # run once, then enter schedule loop (requires TZ=UTC locally)
python main.py --test      # dry run — no state mutation; email marked [TEST]
python main.py --reset     # reinitialise state.json to fresh $100k
```

See `docs/DEPLOY.md` → "Local development" for notes on `TZ=UTC` when
running the default (loop) mode on a non-UTC workstation.

## Documentation

- [SPEC.md](SPEC.md) — full functional specification (archival brief).
- [docs/DEPLOY.md](docs/DEPLOY.md) — **operator runbook** (GitHub Actions + Replit setup, env vars, troubleshooting).
- [CLAUDE.md](CLAUDE.md) — conventions, architecture, stack lock.
- [.planning/ROADMAP.md](.planning/ROADMAP.md) — phase breakdown.

## Architecture

Hexagonal-lite. Pure math in `signal_engine.py` + `sizing_engine.py`; I/O
adapters in `state_manager.py`, `notifier.py`, `dashboard.py`,
`data_fetcher.py`; `main.py` is the thin orchestrator. See
[CLAUDE.md](CLAUDE.md) for boundary rules.

## Deployment

- **Primary:** GitHub Actions — see [docs/DEPLOY.md](docs/DEPLOY.md).
- **Alternative:** Replit Reserved VM + Always On — see [docs/DEPLOY.md](docs/DEPLOY.md) §Alternative.
