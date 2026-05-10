# Trading Signals

Python signal-only trading app. Computes daily ATR/ADX/momentum signals for
SPI 200 (`^AXJO`) and AUD/USD (`AUDUSD=X`), persists state, renders a
self-contained dashboard, and emails a weekday report at 08:00 Sydney
(AEST/AEDT — handles DST; pre-ASX-open).
**Never places live trades.**

## Quickstart

```bash
.venv/bin/python --version  # should report Python 3.13.x
# If .venv does not exist yet:
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt

.venv/bin/python main.py --once      # one-shot run (CI/cron mode)
.venv/bin/python main.py             # run once, then enter schedule loop (requires TZ=UTC locally)
.venv/bin/python main.py --test      # dry run — no state mutation; email marked [TEST]
.venv/bin/python main.py --reset     # reinitialise state.json to fresh $100k
```

See `docs/DEPLOY.md` → "Local development" for notes on `TZ=UTC` when
running the default (loop) mode on a non-UTC workstation.

## Documentation

- [SPEC.md](SPEC.md) — full functional specification (archival brief).
- [SETUP-DROPLET.md](SETUP-DROPLET.md) — one-time droplet bring-up runbook.
- [docs/DEPLOY.md](docs/DEPLOY.md) — **operator runbook** (droplet runbook, env vars, troubleshooting).
- [CLAUDE.md](CLAUDE.md) — conventions, architecture, stack lock.
- [.planning/ROADMAP.md](.planning/ROADMAP.md) — phase breakdown.

## Architecture

Hexagonal-lite. Pure math in `signal_engine.py` + `sizing_engine.py`; I/O
adapters in `state_manager.py`, `notifier/`, `dashboard.py`,
`data_fetcher.py`; `main.py` is the thin orchestrator. See
[CLAUDE.md](CLAUDE.md) for boundary rules.

## Deployment

- **Primary:** DigitalOcean droplet + systemd. See [SETUP-DROPLET.md](SETUP-DROPLET.md) for the one-time bring-up runbook (web unit + sudoers + auth secrets + nginx wiring per Phase 11–13).
- **Routine deploys:** SSH to the droplet and run `bash deploy.sh` — fast-forward pull from `origin/main`, refresh deps, restart `trading-signals` + `trading-signals-web` units, healthz-gated.
- **Operator runbook:** [docs/DEPLOY.md](docs/DEPLOY.md) — env vars, daily-run schedule, troubleshooting.

## Claude Code Setup

```bash
claude mcp add claude-flow -- npx -y @claude-flow/cli@latest
npx @claude-flow/cli@latest daemon start
npx @claude-flow/cli@latest doctor --fix
```

26 commands, 140+ subcommands. Run `--help` on any command for details.
