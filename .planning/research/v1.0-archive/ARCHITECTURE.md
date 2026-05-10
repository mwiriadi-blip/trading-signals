# Architecture Research

**Domain:** Single-operator mechanical trading signal generator (Python, file-backed state, email-delivered)
**Researched:** 2026-04-20
**Confidence:** HIGH — stack, file layout, and workflow are fully pinned by SPEC.md; architectural recommendations are drawn from standard Python patterns for small scheduled jobs and verified against the constraints in PROJECT.md.

## Standard Architecture

### System Overview

```
┌───────────────────────────────────────────────────────────────────────┐
│                          ENTRY POINT LAYER                             │
│  ┌──────────────────────────────────────────────────────────────┐     │
│  │  main.py                                                      │     │
│  │  - CLI parsing (--test, --reset, --force-email)               │     │
│  │  - dotenv loading                                             │     │
│  │  - Scheduler loop OR one-shot execution                       │     │
│  │  - Orchestrates the daily run workflow                        │     │
│  │  - Top-level try/except error boundary                        │     │
│  └──────────────────────────────────────────────────────────────┘     │
├───────────────────────────────────────────────────────────────────────┤
│                       ORCHESTRATION LAYER                              │
│  ┌──────────────────────────────────────────────────────────────┐     │
│  │  run_daily_check()  (lives in main.py)                        │     │
│  │  Pulls from I/O adapters, calls pure logic, writes results    │     │
│  └──────────────────────────────────────────────────────────────┘     │
├───────────────────────────────────────────────────────────────────────┤
│                    PURE DOMAIN LOGIC (no I/O)                          │
│  ┌───────────────────────┐  ┌──────────────────────────────────┐      │
│  │  signal_engine.py     │  │  (internal helpers)              │      │
│  │  - compute_indicators │  │  - position sizing               │      │
│  │  - get_signal         │  │  - stop calc                     │      │
│  │  - check_stop_hit     │  │  - pyramid check                 │      │
│  │  - calc_position_size │  │  - unrealised P&L                │      │
│  └───────────────────────┘  └──────────────────────────────────┘      │
├───────────────────────────────────────────────────────────────────────┤
│                        I/O ADAPTER LAYER                               │
│  ┌────────────────┐ ┌──────────────────┐ ┌──────────────────────┐     │
│  │ signal_engine  │ │ state_manager.py │ │    notifier.py       │     │
│  │   .fetch_data  │ │  load_state      │ │  send_signal_email   │     │
│  │  (yfinance)    │ │  save_state      │ │  (Resend HTTPS API)  │     │
│  │                │ │  atomic write    │ │                      │     │
│  └────────────────┘ └──────────────────┘ └──────────────────────┘     │
│  ┌────────────────────────────────────────────────────────────┐       │
│  │  dashboard.py  —  generate_dashboard → write dashboard.html │       │
│  └────────────────────────────────────────────────────────────┘       │
├───────────────────────────────────────────────────────────────────────┤
│                      PERSISTENCE / OUTPUT                              │
│  ┌──────────────┐  ┌────────────────┐  ┌───────────────────────┐      │
│  │  state.json  │  │ dashboard.html │  │ Resend API (outbound) │      │
│  │  (on disk)   │  │ (on disk)      │  │ Yahoo Finance (in)    │      │
│  └──────────────┘  └────────────────┘  └───────────────────────┘      │
└───────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | What does NOT belong here |
|-----------|----------------|---------------------------|
| `main.py` | CLI parsing, env loading, scheduler vs. one-shot dispatch, orchestration of the daily workflow, top-level error boundary, console summary printing | No indicator math, no Resend request, no yfinance call inline, no JSON parsing of state |
| `signal_engine.py` | Pure math on DataFrames + the one yfinance I/O call (kept here for cohesion with the data contract). Indicators, signal vote, position sizing, stop math, pyramid math, unrealised P&L, stop-hit check | No state I/O, no email, no dashboard rendering, no scheduler, no `datetime.now()` for business dates (pass `as_of` in) |
| `state_manager.py` | Load/save/migrate `state.json`, atomic write, corruption recovery (backup + reinit), schema invariants, helpers: `record_trade`, `update_equity_history`, `reset_state`, `get_position`, `set_position` | No signal computation, no email, no network I/O |
| `notifier.py` | Render HTML email body (inline CSS), build subject line, POST to Resend, handle 429/5xx, degrade to test mode when `RESEND_API_KEY` is missing | No state mutations, no signal computation, no file writes other than maybe a debug dump of HTML |
| `dashboard.py` | Render `dashboard.html` from state + today's indicator snapshot, embed state JSON for Chart.js, write file atomically | No network I/O, no email, no mutation of state |
| `state.json` | Single source of truth for account, open positions, last signal per instrument, trade log, equity history, last_run timestamp, schema_version | Never hand-edited during normal operation; only written by `state_manager.save_state` |
| `dashboard.html` | Static output artefact — regenerated every run, never read back by the app | N/A |

**Where position sizing and stop calcs live — answer:** both belong in `signal_engine.py` as pure functions. They are deterministic math over `(account, signal, atr, rvol, multiplier)` and `(position, price, atr)`. Keeping them in `signal_engine` means `main.py` stays thin and tests can cover sizing/stops without any I/O.

**Key separation rule:** every function in `signal_engine.py` takes plain arguments (floats, dicts, DataFrames) and returns plain values. The only exception is `fetch_data`, which is the one network call — we keep it in `signal_engine` because the DataFrame contract it produces is the input shape the rest of the module expects. Consider splitting it into `signal_engine_io.py` if testing pressure grows, but for a file-count-minimal app it's acceptable.

## Recommended Project Structure

The SPEC has already fixed the top-level layout. The recommendation is to keep it flat and resist creating packages:

```
trading-signals/
├── main.py                  # Entry point — CLI + scheduler + orchestration
├── signal_engine.py         # Pure math + yfinance fetch
├── state_manager.py         # state.json persistence + recovery
├── notifier.py              # Resend HTML email
├── dashboard.py             # dashboard.html renderer
├── requirements.txt
├── .env.example
├── .env                     # gitignored
├── .gitignore               # state.json (local), .env, __pycache__/, dashboard.html
├── state.json               # auto-created; committed only in GitHub Actions mode
├── dashboard.html           # auto-generated
├── tests/                   # pytest — pure functions only
│   ├── test_signal_engine.py
│   ├── test_state_manager.py
│   └── fixtures/
│       └── sample_ohlcv.csv
└── .github/
    └── workflows/
        └── daily.yml        # cron: "0 0 * * 1-5" (08:00 AWST weekdays)
```

### Structure Rationale

- **Flat layout (no `src/` package):** this is a 5-file app with no reuse surface. A package adds import ceremony for zero benefit. Python's `sys.path` behaviour on Replit and GitHub Actions is simpler when `main.py` lives at the repo root.
- **`tests/` present from day one:** the pure-function core (indicators, signal vote, sizing, stop-hit) is exactly the kind of code that benefits from unit tests, and the deterministic nature of the system (same inputs → same outputs) makes testing cheap. Feed fixed CSV fixtures in, assert on indicator values.
- **`.github/workflows/daily.yml` is first-class:** the SPEC explicitly names GitHub Actions as the free fallback. Ship the workflow file alongside the code — not as an afterthought — because deployment topology drives entry-point behaviour (see below).
- **`state.json` gitignored locally, committed in Actions:** the `.gitignore` should list `state.json`, and the Actions workflow uses `git add -f state.json && git commit && git push` after the run. The local dev loop stays clean; the Actions loop has durable state.
- **No `utils.py` / `helpers.py`:** put helpers next to their callers. Cross-module helpers (date formatting, AWST now) can live at the top of whichever module uses them most; if they start being imported from three places, extract to a `util.py` at that point, not before.

## Architectural Patterns

### Pattern 1: Ports-and-Adapters at a Single-File Scale (Hexagonal-lite)

**What:** Keep one file with pure functions that take data and return data. Keep another file that does I/O. The orchestrator (`main.py`) wires them together.

**When to use:** always, even for 500-LOC apps. The payoff is test speed and the ability to reason about the signal output as a pure function of market data + prior state.

**Trade-offs:** forces `main.py` to do the "messy glue" work. That's fine — it's a small file dedicated to that job.

**Example:**

```python
# signal_engine.py — pure
def get_signal(df: pd.DataFrame) -> int:
    """Returns 1, -1, or 0 from the latest row of an indicator-enriched df."""
    row = df.iloc[-1]
    if row["ADX"] < 25:
        return 0
    up = sum(row[c] > 0.02 for c in ("Mom1", "Mom3", "Mom12"))
    dn = sum(row[c] < -0.02 for c in ("Mom1", "Mom3", "Mom12"))
    if up >= 2: return 1
    if dn >= 2: return -1
    return 0

# main.py — impure glue
def run_daily_check():
    state = state_manager.load_state()
    for sym, ticker in INSTRUMENTS.items():
        df = signal_engine.fetch_data(ticker)          # I/O
        df = signal_engine.compute_indicators(df)      # pure
        new_signal = signal_engine.get_signal(df)      # pure
        state = apply_signal(state, sym, new_signal, df)  # pure reducer
    state_manager.save_state(state)                    # I/O
    notifier.send_signal_email(build_report(state))    # I/O
```

### Pattern 2: Single Orchestrator Function as the Workflow Spine

**What:** `run_daily_check()` in `main.py` is the canonical, step-by-step expression of the daily workflow. Every step is a line of code at the same indentation level. No callbacks, no middleware, no "pipeline" abstraction.

**When to use:** when the workflow is linear, one-user, and you want the flow to be readable top-to-bottom without tracing through abstractions.

**Trade-offs:** if the workflow grows many branches, this becomes unwieldy. For this app it won't — the spec freezes the step list.

**Example:**

```python
def run_daily_check(args):
    state = state_manager.load_state()
    report = {"date": today_awst(), "instruments": {}, "warnings": []}

    for sym, ticker in INSTRUMENTS.items():
        df = safe_fetch(ticker, report)                        # step 1
        if df is None: continue
        df = signal_engine.compute_indicators(df)              # step 2
        new_signal = signal_engine.get_signal(df)              # step 3
        state = resolve_stop_hits(state, sym, df)              # step 4
        state = apply_signal_change(state, sym, new_signal, df)# step 5
        state = apply_pyramid(state, sym, df)                  # step 6
        state = update_unrealised_pnl(state, sym, df)          # step 7
        report["instruments"][sym] = build_instrument_report(state, sym, df)

    state = state_manager.update_equity_history(state, today_str())  # step 8
    if not args.test:
        state_manager.save_state(state)                              # step 9
    dashboard.write_dashboard(state, report)                         # step 10
    notifier.send_signal_email(report)                               # step 11
    print_console_summary(report)                                    # step 12
```

Each "step N" is a named function that takes the state and returns a new state (or mutates and returns the same dict). Readable top-to-bottom; each step is individually unit-testable.

### Pattern 3: State-as-Reducer with Atomic Write

**What:** `state_manager` exposes `load_state` and `save_state`. All in-run mutations happen in memory on the loaded dict. At the end of the run, `save_state` writes atomically (write to `state.json.tmp`, then `os.replace` to `state.json`). Readers never see a partial file.

**When to use:** whenever you have one-writer, many-readers against a JSON file (here: dashboard embeds the JSON, external tools may scrape it).

**Trade-offs:** a crash mid-run loses all intra-run mutations — which is exactly what you want, because a crash mid-workflow leaves the state in an inconsistent intermediate shape. Atomic write = crash-safe "all-or-nothing" semantics.

**Example:**

```python
# state_manager.py
import json, os, shutil, tempfile

def save_state(state: dict, path: str = "state.json") -> None:
    state["schema_version"] = SCHEMA_VERSION
    state["last_saved_utc"] = datetime.utcnow().isoformat()
    dirpath = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp = tempfile.mkstemp(dir=dirpath, prefix=".state.", suffix=".json.tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(state, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp): os.remove(tmp)
        raise

def load_state(path: str = "state.json") -> dict:
    if not os.path.exists(path):
        return _initial_state()
    try:
        with open(path) as f:
            state = json.load(f)
        _validate_schema(state)
        return _migrate_if_needed(state)
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        _backup_corrupt_file(path, reason=str(e))
        print(f"[state] CORRUPT state.json: {e} — backed up and reinitialised")
        return _initial_state(warning=f"state.json was corrupt: {e}")
```

### Pattern 4: Graceful Degradation for Optional Collaborators

**What:** `notifier.py` checks for `RESEND_API_KEY` at send time. If it's missing or empty, it does not raise — it logs "test mode: email not sent" and returns `False`. The orchestrator treats email-send failure as a warning in next-run's report, not a workflow-killer.

**When to use:** when the collaborator is important-but-not-critical. The signal must be computed and persisted even if email fails.

**Trade-offs:** risk of silent failure — mitigated by (a) console log always saying whether email was sent, (b) a `warnings` list in `state.json` that the next email surfaces, (c) a health check that flags `last_run` age.

**Example:**

```python
# notifier.py
def send_signal_email(report: dict) -> bool:
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        print("[notifier] RESEND_API_KEY missing — skipping email (test mode)")
        report.setdefault("warnings", []).append("email not sent: no API key")
        return False
    try:
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json"},
            json={"from": FROM_EMAIL, "to": [TO_EMAIL],
                  "subject": build_subject(report),
                  "html":    build_email_html(report)},
            timeout=15,
        )
        if 200 <= resp.status_code < 300:
            return True
        print(f"[notifier] Resend {resp.status_code}: {resp.text[:200]}")
        report.setdefault("warnings", []).append(f"email failed: HTTP {resp.status_code}")
        return False
    except requests.RequestException as e:
        print(f"[notifier] Resend network error: {e}")
        report.setdefault("warnings", []).append(f"email failed: {type(e).__name__}")
        return False
```

### Pattern 5: Dual Entry Paths, Single Workflow

**What:** the same `run_daily_check()` function is called two different ways depending on deployment:

- **Replit Always On:** `main()` uses `schedule.every().day.at("00:00").do(run_daily_check)` and sits in a `while True` loop. Process lives forever, scheduler wakes it up.
- **GitHub Actions:** `main()` detects a CLI flag (e.g. `--once` or env var `CI=true`), calls `run_daily_check()` exactly once, and exits with code 0 or non-zero.

**When to use:** when the SPEC mandates multiple hosts with different lifecycle models but you don't want the business logic duplicated.

**Trade-offs:** `main()` has two branches. That's fine — both branches call the same `run_daily_check()`.

**Example:**

```python
def main():
    args = parse_args()
    load_dotenv()

    if args.reset:
        state_manager.reset_state(); return

    if args.once or os.environ.get("GITHUB_ACTIONS") == "true":
        run_daily_check(args); return

    # Replit / local dev: scheduler mode
    run_daily_check(args)  # first-run-on-start
    schedule.every().day.at("00:00").do(lambda: run_daily_check(args))
    print("[main] Scheduler running; 08:00 AWST daily.")
    while True:
        schedule.run_pending()
        time.sleep(60)
```

## Data Flow

### Daily Run Flow (the canonical workflow)

```
[Scheduler / GH Actions trigger]
        ↓
main.py: parse_args, load_dotenv
        ↓
state_manager.load_state()   →  state: dict (from state.json, or fresh, or recovered)
        ↓
FOR EACH instrument (SPI200, AUDUSD):
  │
  ├─ signal_engine.fetch_data(ticker, 400)      ← yfinance (retry 3x)
  ├─ signal_engine.compute_indicators(df)        ← pure
  ├─ new_signal = signal_engine.get_signal(df)   ← pure
  │
  ├─ IF state.positions[sym].active:
  │     stop_hit = check_stop_hit(pos, today_high, today_low, atr)   ← pure
  │     IF stop_hit OR adx < 20 OR signal_reversed:
  │         trade = close_position(state, sym, reason, fill_price)
  │         state_manager.record_trade(state, trade)
  │
  ├─ IF new_signal != 0 AND no active pos in that direction:
  │     open_position(state, sym, new_signal, size, atr, price)
  │
  ├─ IF state.positions[sym].active:  # pyramid check AFTER open
  │     n_add = signal_engine.check_pyramid(pos, price, atr_entry)
  │     IF n_add > 0: add_contracts(state, sym, n_add)
  │
  └─ pos.unrealised_pnl = signal_engine.compute_unrealised_pnl(pos, price, mult)
  
END FOR
        ↓
state_manager.update_equity_history(state, today_str)
        ↓
state_manager.save_state(state)          ← atomic write to state.json
        ↓
dashboard.generate_dashboard(state, ind_data) → write dashboard.html
        ↓
notifier.send_signal_email(report)       ← Resend HTTPS POST (degrades if no key)
        ↓
print_console_summary(report)
        ↓
[return to scheduler loop OR exit (GH Actions)]
```

### State Mutation Ordering — when each field gets updated

Relative to one daily run, fields in `state.json` change in this order. Nothing changes until the end (atomic save), but the in-memory `state` dict mutates as follows:

| Step | Field | Change |
|------|-------|--------|
| 1 | `state.last_run` | set to today's AWST date string (set early so error paths still persist it) |
| 2 | `state.positions[sym].unrealised_pnl` | recomputed from today's close (even before stop checks — so stop-hit emails carry accurate numbers) |
| 3 | `state.positions[sym].peak_price` | updated to today's intra-bar high/low if it exceeds the current peak (required before stop calc) |
| 4 | `state.positions[sym].trail_stop` | recomputed from new peak |
| 5 | `state.positions[sym]` | set to `{"active": false}` if stop hit / reversal / ADX drop-out |
| 6 | `state.trade_log` | append trade record on close |
| 7 | `state.account` | decremented by round-trip cost, credited with realised P&L |
| 8 | `state.positions[sym]` | set to new active position if a new entry fires (after close) |
| 9 | `state.positions[sym].n_contracts`, `pyramid_level` | incremented if pyramid threshold hit |
| 10 | `state.signals[sym]` | replaced with today's signal (kept even when FLAT so next-run change detection works) |
| 11 | `state.equity_history` | append `{date, equity}` — equity = account + sum of unrealised P&L |
| 12 | `state.last_saved_utc`, `state.schema_version` | stamped by `save_state` |

**Invariant 1:** `state.signals[sym]` reflects the latest computed signal, regardless of whether it matches the current position. This is what allows "signal change" detection on the next run.

**Invariant 2:** `state.positions[sym].active == false` ⇒ all other fields under that position are either absent or stale; downstream code must never read them when `active == false`.

**Invariant 3:** `state.trade_log` entries are append-only. Never mutate a historical entry.

**Invariant 4:** `state.equity_history` has one entry per run (idempotent if run twice on same date — replace rather than append to prevent drift).

**Invariant 5:** `state.account` represents closed-trade equity only. Unrealised P&L is never folded into `account` — it lives on `positions[sym].unrealised_pnl`. Dashboard/email "equity" = `account + sum(unrealised_pnl)`.

### Config / Env-Var Loading

- **Single point of load:** `main.py` calls `load_dotenv()` once at startup, before any other imports that read env vars. Other modules read `os.environ.get(...)` at call time, never at import time. That way test fixtures can monkeypatch `os.environ` between tests.
- **Required vs optional:**
  - **Required in production:** `TO_EMAIL` — without a recipient, the app is useless. Fail fast with a clear error if missing at startup.
  - **Required for email:** `RESEND_API_KEY` — missing triggers graceful degradation (email skipped, warning logged, workflow continues).
  - **Optional with defaults:** `FROM_EMAIL` (default `signals@carbonbookkeeping.com.au`), `ACCOUNT_START` (default `100000`), `SEND_TEST_ON_START` (default `false`).
- **Defaults for test mode:** if `--test` is passed OR if `RESEND_API_KEY` is absent, the notifier writes the HTML email to `last_email.html` in the working directory instead of calling Resend. This gives the operator something to eyeball when debugging locally.
- **Starting account:** loaded once at `_initial_state()` from `ACCOUNT_START`. After that, `state.account` is the source of truth and the env var is ignored — otherwise restarting with a different env would silently overwrite equity.

### Error Boundary Design

| Failure | Caught in | Behaviour |
|---------|-----------|-----------|
| yfinance timeout / 429 / empty frame | `signal_engine.fetch_data` (retry loop) → bubbles `DataFetchError` to `main.run_daily_check` | retry 3x with 10s delay; if still failing, skip that instrument for this run, add to `report.warnings`, continue with the other instrument, state still saves |
| Both instruments fail to fetch | `main.run_daily_check` | still save state (just with warnings), still send email explaining the outage, exit non-zero in GH Actions mode so the cron shows red |
| Resend 4xx/5xx or network | `notifier.send_signal_email` | log, append to `report.warnings`, return `False`; workflow continues, state still saves. Next run's email will surface "previous email failed" via `warnings` from state |
| `state.json` corrupt (invalid JSON / schema mismatch) | `state_manager.load_state` | copy to `state.json.corrupt.<timestamp>`, reinitialise with `_initial_state(warning=...)`, continue. Next email flags "state was reinitialised — review trade history manually" |
| `state.json` missing | `state_manager.load_state` | silently initialise (first-run case) |
| Schema version drift | `state_manager._migrate_if_needed` | run forward migrations; if unknown version, refuse to overwrite and raise `StateSchemaError` that `main` catches and turns into a loud email |
| Indicator NaN (insufficient history) | `signal_engine.get_signal` | return `0` (FLAT) and add a per-instrument warning; don't crash |
| Missing `TO_EMAIL` at startup | `main.main()` | log clear error, exit 1 — this is a configuration error, not a runtime one |
| Any uncaught exception | `main.main()` top-level `try/except` | print full traceback, attempt a "crash email" if Resend creds are available, exit 1 (so GH Actions goes red, Replit logs the traceback) |

The golden rule from the SPEC: **"App must never crash silently. All errors caught, logged, and surfaced in the next email as a warning."** Our boundary design achieves this by keeping `warnings` as a first-class field in both `report` (current run) and `state` (for next run to surface).

## State.json Schema Invariants

Beyond the mutation ordering above, these structural invariants hold:

- **`schema_version`** is always present. Default `1`. Bump on breaking changes; migrations live in `state_manager._migrate_if_needed`.
- **`account`** is always a float >= 0. A negative account implies a blown-up hypothetical — don't silently clamp; surface as a warning.
- **`positions`** always contains keys `"SPI200"` and `"AUDUSD"`, even when both are inactive (`{"active": false}`). Absence of a key means first-run hasn't completed; presence with `active: false` is the normal "flat" state.
- **`signals`** always contains keys `"SPI200"` and `"AUDUSD"`, values in `{-1, 0, 1}`. This is the "previous signal" used for change detection next run.
- **`trade_log`** is an array, append-only, unbounded (dashboard truncates to last 20; emails to last 5). At scale, if this ever exceeds ~10k entries, add a rotation helper — but that's ~40 years away.
- **`equity_history`** is an array of `{date, equity}`, one entry per run date. If the same date is written twice, the later entry replaces the earlier (idempotency under same-day re-runs).
- **`last_run`** is an AWST date string (`YYYY-MM-DD`). Used by the "stale state" health check (warn if > 2 days old).
- **`last_saved_utc`** is an ISO timestamp. Used by dashboard "last updated" and debugging.
- **`warnings`** (optional) is a list of strings carried over from the previous run — cleared at the start of each successful run, repopulated as new warnings occur.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 1 user, 2 instruments, daily (current) | Current architecture — flat Python, JSON file, single process |
| 1 user, 5–10 instruments | Still fine. `INSTRUMENTS` dict grows; the `for` loop handles more items. Email template becomes a scroll-able table. `state.json` grows but remains < 1MB. |
| Multiple users OR intraday | This is a different product. Move to a real DB (SQLite → Postgres), put the scheduler behind a queue, split the signal engine into a service. Explicitly out of scope per PROJECT.md. |

### Scaling Priorities

1. **First bottleneck (if instruments grow):** the yfinance fetch is serial and sometimes slow. If you add more instruments, parallelise `fetch_data` calls with `concurrent.futures.ThreadPoolExecutor(max_workers=4)` — but keep the rest of the workflow serial. There is no meaningful second bottleneck until you hit 50+ instruments.
2. **Second bottleneck (trade log growth):** dashboard rendering will slow once `trade_log` exceeds a few thousand entries because it's embedded in the HTML. At that point, only embed the last 200 in the dashboard and keep the full log in a separate `trade_log.jsonl` file. Not a concern in year 1.

**Explicit non-concerns:** concurrent writers, rate limits (daily cadence is well under Yahoo's and Resend's limits), memory, CPU. This is a 30-second Python script that runs once a day.

## Anti-Patterns

### Anti-Pattern 1: Computing signals inside a route/CLI handler

**What people do:** put indicator math, state mutation, and email sending all inside `run_daily_check()` as one 300-line function.

**Why it's wrong:** impossible to unit-test. One change to the email template forces a run through the full workflow. Bugs in indicator math can only be caught by observation on live data.

**Do this instead:** `signal_engine` has pure functions. `run_daily_check` is glue. Tests cover `signal_engine.get_signal(fixture_df) == 1` without any network.

### Anti-Pattern 2: Reading env vars at import time

**What people do:** `RESEND_API_KEY = os.environ["RESEND_API_KEY"]` at the top of `notifier.py`.

**Why it's wrong:** the import fails hard at startup if the key is missing (breaks test mode). Tests can't monkeypatch because the value is baked in at import.

**Do this instead:** read env vars at call time inside `send_signal_email()`. Keep the top of `notifier.py` clean of side effects.

### Anti-Pattern 3: Non-atomic state writes

**What people do:** `open("state.json", "w").write(json.dumps(state))`.

**Why it's wrong:** a crash mid-write (power loss, Replit redeploy) leaves a truncated JSON file, which crashes the next run.

**Do this instead:** write to `state.json.tmp`, `fsync`, `os.replace` → `state.json`. This is what `save_state` does. On POSIX `os.replace` is atomic.

### Anti-Pattern 4: Catching exceptions too narrowly at the top level

**What people do:** `except requests.RequestException` at the top of `run_daily_check`.

**Why it's wrong:** the workflow has many failure modes (KeyError on state schema, pandas IndexError on empty df, ValueError in indicator math). Narrow catches let crashes escape.

**Do this instead:** narrow catches inside each I/O helper (`fetch_data`, `send_signal_email`, `load_state`), a broad `except Exception` at `main()` top level that logs traceback + attempts a crash email + exits non-zero.

### Anti-Pattern 5: Using `datetime.now()` without a timezone inside pure functions

**What people do:** sprinkle `datetime.now()` calls throughout `signal_engine` to timestamp computations.

**Why it's wrong:** makes the function impure (different output every call), breaks testing, and on Replit (UTC server) produces a different "today" than the operator in Perth.

**Do this instead:** compute `today_awst = datetime.now(pytz.timezone("Australia/Perth")).date()` once in `main.py` and pass it down as `as_of_date` to any function that needs it. Pure functions stay pure.

### Anti-Pattern 6: Folding unrealised P&L into `account`

**What people do:** update `state.account += unrealised_pnl_today` at each run.

**Why it's wrong:** double-counts when the trade closes; produces a drifting, incorrect equity figure; makes "closed-trade equity" impossible to reconstruct.

**Do this instead:** `account` = closed-trade cash only. `equity_today = account + sum(positions[sym].unrealised_pnl)`. Compute this in the view layer (dashboard, email) on the fly.

### Anti-Pattern 7: Hiding the deployment differences across GHA and Replit

**What people do:** try to make `main.py` auto-detect which environment it's in and behave magically.

**Why it's wrong:** obscures bugs (Replit scheduler silently runs in Actions; Actions re-exits while Replit idles). Hard to test the Actions path locally.

**Do this instead:** an explicit `--once` flag. Actions workflow passes `--once`. Replit omits it. Auto-detection via `GITHUB_ACTIONS=true` is fine as a fallback but `--once` is the primary signal.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Yahoo Finance (via yfinance) | Library call, unauthenticated, cache-poor, occasionally flaky | Wrap in retry-with-backoff (3 attempts, 10s delay). Validate DataFrame shape before returning (non-empty, has `Close`, has >= 252 rows for Mom12). yfinance has changed behaviour between versions — pin `>=0.2.40`. |
| Resend HTTPS API | `requests.post` with bearer auth, JSON body | Timeout 15s. 429 means slow down — for a once-per-day app this should never happen, but handle it anyway by logging and not retrying. `from` must be a verified sender (`signals@carbonbookkeeping.com.au` already is per PROJECT.md). |
| Replit filesystem | Direct file I/O | Persistent with Always On; ephemeral without. Design assumes persistence but degrades safely if state is lost (first-run reinit). |
| GitHub Actions runner | Shell invocation of `python main.py --once`, then `git commit state.json` | Runner filesystem is ephemeral per run — state persistence relies on the git push step. If push fails (concurrent runs, auth), next run rebuilds from the last committed state, losing one day of trade log. Acceptable. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| `main` ↔ `signal_engine` | Function calls with `(ticker, as_of_date, config)` in, `pd.DataFrame` or scalar out | `main` owns time; `signal_engine` never looks at the clock |
| `main` ↔ `state_manager` | `load_state() -> dict`, mutate dict, `save_state(dict)` | State is a plain dict everywhere — no custom class — so dashboard/email can JSON-serialise trivially |
| `main` ↔ `notifier` | `send_signal_email(report) -> bool` where `report` is a plain dict | `report` ≠ `state` — `report` is a view-model built from state + today's indicators, shaped for email rendering |
| `main` ↔ `dashboard` | `generate_dashboard(state, indicator_data) -> html_str` (or writes file directly) | Reads state, does not mutate. Takes today's indicator snapshot as a second argument so it doesn't have to re-fetch |
| `signal_engine` ↔ `state_manager` | **No direct link.** Deliberate. | If they imported each other, testing becomes tangled. All interaction goes through `main` |
| `notifier` ↔ `dashboard` | **No direct link.** | Both are output-only views over state |

## Recommended Build Order

Order chosen so (a) each phase produces something testable on its own, (b) downstream phases depend only on stable upstream contracts, and (c) the end-to-end "skeleton" ships in the first milestone so deployment can be validated early.

### Phase 1 — Stable core with deterministic signal from fixture data
Goal: prove the math, no network, no state, no email.

- `signal_engine.py`: `compute_indicators`, `get_signal`, `calc_position_size`, `get_trailing_stop`, `check_stop_hit`, `compute_unrealised_pnl`, `check_pyramid`
- `tests/test_signal_engine.py` with one CSV fixture per instrument
- No `main.py` yet; drive from pytest

**Ships:** a pure-function library whose outputs match the backtest.

### Phase 2 — State persistence with recovery
Goal: round-trip state reliably.

- `state_manager.py`: `load_state`, `save_state` (atomic), `_initial_state`, `_migrate_if_needed`, `_backup_corrupt_file`, `record_trade`, `update_equity_history`, `reset_state`
- `tests/test_state_manager.py`: tests for atomic write, corrupt-recovery, schema migration, idempotent equity history

**Ships:** a storage layer with known invariants.

### Phase 3 — End-to-end skeleton (no scheduler, no email)
Goal: wire everything together with `--once` semantics. This is the first point where the app actually runs against live data.

- `signal_engine.fetch_data` (yfinance, with retry)
- `main.py`: `run_daily_check`, CLI parsing for `--test`, `--reset`, `--once`, env loading via `python-dotenv`
- Console summary output
- Error boundary at `main()` top level

**Ships:** `python main.py --once` reads Yahoo, computes signals, updates state.json, prints summary. No email yet. No dashboard yet.

**Why this order:** after phase 3 you can verify the core behaviour daily-by-hand for a week before adding outputs. If the signal logic is wrong, you'd rather discover it before it's buried under email formatting.

### Phase 4 — Dashboard output
Goal: visual verification.

- `dashboard.py`: HTML template with inline CSS, Chart.js from CDN, equity curve, positions table, recent trades, key stats
- Called from the orchestrator after `save_state`

**Ships:** `dashboard.html` regenerates every run; open in browser to confirm state looks right.

### Phase 5 — Email notification
Goal: the one-user-facing output.

- `notifier.py`: `build_subject`, `build_email_html` (inline CSS, mobile-responsive, ACTION REQUIRED block on signal change), `send_signal_email` with Resend, graceful degradation when API key missing
- `--force-email` flag support
- "Test mode" writes `last_email.html` to disk instead of sending

**Ships:** every run sends an email (or skips cleanly in test mode). Signal-change detection drives the ACTION block.

### Phase 6 — Scheduler + deployment paths
Goal: lights-out operation.

- Scheduler loop in `main.main()` for Replit Always On
- `--once` branch for GitHub Actions
- `.github/workflows/daily.yml` with cron `0 0 * * 1-5`, checkout, setup-python, install, run, `git commit state.json && git push` (with `GITHUB_TOKEN` perms set appropriately)
- `.env.example` finalised
- Replit setup notes in `main.py` module docstring
- First-run-on-start behaviour verified

**Ships:** live deployment on at least one of the two targets (Replit preferred for first live email; GitHub Actions as redundancy).

### Phase 7 — Hardening
Goal: handle the long tail of real-world failures.

- Observed-in-production retry tuning (yfinance occasionally 200s with empty frame)
- Warning carry-over from state `warnings` into the email header
- Stale-state health check ("last run > 2 days ago" warning)
- Schema migration path exercised with at least one version bump (even a no-op migration) so the code path is real, not theoretical
- Crash-email path tested by deliberately breaking something
- Optional: lightweight log file (`signals.log`) rolled daily, to complement stdout on GH Actions

**Ships:** a system that survives yfinance outages, Resend outages, corrupt state, and schema drift without operator intervention.

---

**Build-order rationale summary:**

| Phase | Depends on | Unblocks |
|-------|-----------|----------|
| 1 Signal engine (pure) | nothing | tests, then 3 |
| 2 State manager | nothing | 3 |
| 3 E2E skeleton | 1, 2 | 4, 5, 6 |
| 4 Dashboard | 2, 3 | visual QA |
| 5 Email | 2, 3 | operator consumption |
| 6 Scheduler + deploy | 3 (4, 5 optional to deploy) | live runs |
| 7 Hardening | all | production-readiness |

Phases 4 and 5 can run in parallel after phase 3; they share no code.

## Sources

- SPEC.md in this repository (lines 1–513) — module signatures, file layout, workflow steps, deployment targets, env vars, error handling requirements
- PROJECT.md in this repository — constraints (Python 3.11+, no Flask, single `state.json`, signal-only), deployment targets, Perth AWST schedule
- Standard Python patterns for scheduled jobs: `schedule` library docs (readthedocs), dotenv loading best practices, atomic file write idiom (`os.replace` + `fsync`) — these are stable, training-data confidence HIGH
- Hexagonal / ports-and-adapters pattern at single-file scale — standard Python architectural pattern, widely documented
- Resend API reference (https://resend.com/docs/api-reference/emails/send-email) — bearer auth, JSON body, 200/2xx success response shape
- yfinance behaviour notes — library known to return empty DataFrames on rate-limiting rather than raising; retry-with-validation pattern addresses this

---
*Architecture research for: single-operator mechanical trading signal generator (Python, yfinance, JSON state, Resend email)*
*Researched: 2026-04-20*
