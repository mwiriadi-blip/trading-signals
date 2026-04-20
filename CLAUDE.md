# Trading Signals — SPI 200 & AUD/USD Mechanical System

**Python signal-only trading app.** Computes daily ATR/ADX/momentum signals for `^AXJO` (SPI 200) and `AUDUSD=X`, persists state, renders a dashboard, and emails a weekday report at 08:00 AWST. Never places live trades.

See [.planning/PROJECT.md](.planning/PROJECT.md) for full context and [SPEC.md](SPEC.md) for the complete functional specification.

## Stack

- **Python 3.11** with CommonJS-style flat module layout
- **yfinance** `>=0.2.65,<0.3` — data source
- **pandas 2.2** / **numpy 1.26+** — DataFrame math
- **requests** — Resend HTTPS calls (no SDK)
- **schedule** — in-process daily loop for Replit path
- **python-dotenv** — local `.env` only
- **pytz** — `Australia/Perth` timezone
- **Chart.js 4.4.6 UMD** (CDN, pinned) — dashboard equity curve
- **pytest** + **pytest-freezer** — fixture-driven signal tests

**Hand-roll** ATR(14), ADX(20), +DI, -DI, Mom, RVol — no pandas-ta or TA-Lib.

## Conventions

- 2-space indent, single quotes, PEP 8 via `ruff`
- Snake_case for functions, UPPER_SNAKE for constants
- Instrument keys: `SPI200`, `AUDUSD` (matches state.json)
- Signal integers: `LONG=1`, `SHORT=-1`, `FLAT=0`
- Dates: ISO `YYYY-MM-DD`; times always AWST in user-facing output
- Log prefixes: `[Signal]`, `[State]`, `[Email]`, `[Sched]`, `[Fetch]`

## Architecture

Hexagonal-lite. Pure math in `signal_engine.py`, I/O adapters in `state_manager.py`, `notifier.py`, `dashboard.py`. `main.py` is the thin orchestrator with one `run_daily_check()` function.

- `signal_engine.py ↔ state_manager.py` must not import each other — all interaction through `main.py`
- All pure functions take plain args, return plain values — no `datetime.now()`, no env-var reads inside them
- `state.json` writes are atomic: tempfile + fsync + `os.replace`
- `--test` is structurally read-only (enforced by splitting compute and persist)
- Email sends NEVER crash the workflow — Resend failure is logged and skipped

## Operator Decisions (locked in during project init)

- **Deployment:** GitHub Actions is the primary path (cron `0 0 * * 1-5` UTC = 08:00 AWST Mon-Fri); Replit Always On is alternative
- **Sizing:** No `max(1, …)` floor — if sized contracts = 0, skip the trade and warn
- **FLAT close:** LONG→FLAT closes the LONG; SHORT→FLAT closes the SHORT
- **Trailing stop:** Intraday HIGH/LOW drives both peak updates and hit detection

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd:quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd:debug` for investigation and bug fixing
- `/gsd:execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.

## Next Steps

Roadmap has **8 phases** covering **78 v1 requirements** (see [.planning/ROADMAP.md](.planning/ROADMAP.md)). Start with:

```
/gsd-discuss-phase 1   # Signal Engine Core — Indicators & Vote
```

Phases 1 and 3 share no code and can be planned in parallel if capacity allows.
