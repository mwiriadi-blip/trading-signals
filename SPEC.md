# Claude Code Prompt — SPI + AUD/USD Mechanical Signal App on Replit

Paste this entire prompt into Claude Code to build and deploy the app.

---

## PROJECT BRIEF

Build a production-ready Python trading signal application that implements a mechanical trend-following system for two instruments: **SPI 200 (ASX 200 index, ticker `^AXJO` on Yahoo Finance)** and **AUD/USD (ticker `AUDUSD=X` on Yahoo Finance)**. The app runs daily on Replit, computes signals, updates a dashboard, and sends an email notification every weekday morning Australian time.

This is a **signal-only** app — it does NOT place live trades. It tells me what the system says I should be doing and tracks hypothetical P&L against a $100,000 starting account.

---

## SYSTEM LOGIC (implement exactly as specified)

### Signal Rules (check every weekday, generate action on signal change)

**For each instrument independently:**

1. **Fetch daily OHLCV data** via `yfinance` — use `^AXJO` for SPI, `AUDUSD=X` for AUD/USD. Download 400 days of history each run.

2. **Compute these indicators on the daily close:**
   - `ATR(14)` using Wilder's exponential smoothing
   - `ADX(20)` using Wilder's method (also compute +DI and -DI)
   - `Mom1` = 21-day price return
   - `Mom3` = 63-day price return
   - `Mom12` = 252-day price return
   - `RVol` = 20-day realised volatility annualised (`daily_returns.rolling(20).std() * sqrt(252)`)

3. **Signal generation (2-of-3 multi-timeframe + ADX gate):**
   ```
   IF ADX < 25:
       signal = FLAT (0)
   ELSE:
       votes_up = count of [Mom1, Mom3, Mom12] that are > +0.02
       votes_dn = count of [Mom1, Mom3, Mom12] that are < -0.02
       IF votes_up >= 2: signal = LONG (1)
       IF votes_dn >= 2: signal = SHORT (-1)
       ELSE: signal = FLAT (0)
   ```

4. **Signal checked on Friday close, executed Monday open** (for weekly cadence). In the daily version, check every day but only generate an ACTION notification when the signal **changes** from the previous day's signal.

5. **Position sizing (ATR-based with vol targeting):**
   ```
   risk_pct  = 1.0% for LONG, 0.5% for SHORT
   trail_mult = 3.0 for LONG, 2.0 for SHORT
   vol_scale = clip(0.12 / RVol, 0.3, 2.0)
   stop_dist  = trail_mult × ATR × multiplier
   n_contracts = max(1, int((account × risk_pct / stop_dist) × vol_scale))
   ```

6. **Contract specs:** (per Phase 2 D-11 — operator confirmed at /gsd-discuss-phase 2)
   - SPI 200 mini: multiplier = $5/point, cost = $6 AUD round-trip ($3 on open + $3 on close per D-13), min 1 contract
   - AUD/USD: multiplier = $10,000 (mini lot notional), P&L = price_delta × 10000 × n_contracts, cost = $5 AUD round-trip ($2.50 on open + $2.50 on close per D-13)
   - Cost-timing convention: half on open (deducted in `compute_unrealised_pnl`), half on close (deducted in Phase 3 `record_trade`).

7. **Exit rules (check daily):**
   - Signal reversal (new signal ≠ current position direction) → close and reverse/go flat
   - ADX drops below 20 while in trade → close immediately
   - Trailing stop hit: long stop = peak_price − (3 × ATR); short stop = peak_price + (2 × ATR). Update peak daily.

8. **Pyramiding:**
   - When unrealised profit ≥ 1×ATR from entry → add 1 contract (if total < 3)
   - When unrealised profit ≥ 2×ATR from entry → add another (if total < 3)
   - Track pyramid level in state

---

## FILE STRUCTURE TO CREATE

```
/
├── main.py                  # Entry point — Replit runs this
├── signal_engine.py         # Core signal computation
├── state_manager.py         # JSON state persistence
├── notifier.py              # Email notification via Resend API
├── dashboard.py             # HTML dashboard generator
├── requirements.txt         # Python dependencies
├── .env.example             # Environment variable template
├── state.json               # Auto-created on first run (gitignore this)
└── dashboard.html           # Auto-generated dashboard output
```

---

## DETAILED MODULE SPECIFICATIONS

### `signal_engine.py`

> **Phase 2 module split (D-07):** Per Phase 2 plan, sizing/exit/pyramid functions (`get_trailing_stop`, `check_stop_hit`, `calc_position_size`, `compute_unrealised_pnl`, `check_pyramid`) and the `step()` orchestrator wrapper live in a sibling pure-math module `sizing_engine.py`, NOT inside `signal_engine.py`. Per Phase 2 D-17 (reviews-revision pass), the actual implemented signatures are `compute_unrealised_pnl(position, current_price, multiplier, cost_aud_open) -> float` and `step(position, bar, indicators, old_signal, new_signal, account, multiplier, cost_aud_open) -> StepResult` — the function-list signatures below remain authoritative for the OTHER callables; the file location moves and these two signatures expand. Policy constants (RISK_PCT, TRAIL_MULT, VOL_SCALE_*, PYRAMID_TRIGGERS, MAX_PYRAMID_LEVEL, ADX_EXIT_GATE, SPI_MULT, SPI_COST_AUD, AUDUSD_NOTIONAL, AUDUSD_COST_AUD) and the `Position` TypedDict live in `system_params.py` (D-01, D-08).

Functions to implement:
```python
def fetch_data(ticker: str, days: int = 400) -> pd.DataFrame
    # Downloads OHLCV via yfinance, returns clean DataFrame

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame
    # Adds ATR, ADX, PDI, NDI, Mom1, Mom3, Mom12, RVol columns

def get_signal(df: pd.DataFrame) -> int
    # Returns 1, -1, or 0 based on latest row

def get_trailing_stop(position: dict, current_price: float, atr: float) -> float
    # Computes current trailing stop price given position state

def check_stop_hit(position: dict, high: float, low: float, atr: float) -> bool
    # Returns True if stop was hit on today's candle

def calc_position_size(account: float, signal: int, atr: float, rvol: float, multiplier: float) -> int
    # Returns number of contracts using ATR + vol targeting

def compute_unrealised_pnl(position: dict, current_price: float, multiplier: float) -> float
    # Returns unrealised P&L in AUD for open position

def check_pyramid(position: dict, current_price: float, atr_entry: float) -> int
    # Returns number of new contracts to add (0, 1, or 2 minus already added)
```

### `state_manager.py`

Manage a `state.json` file with this exact structure:
```json
{
  "account": 100000.0,
  "last_run": "2025-04-12",
  "positions": {
    "SPI200": {
      "active": true,
      "direction": "LONG",
      "entry_price": 7800.0,
      "entry_date": "2025-03-01",
      "n_contracts": 2,
      "pyramid_level": 1,
      "trail_stop": 7650.0,
      "peak_price": 7950.0,
      "atr_entry": 85.0,
      "unrealised_pnl": 3750.0
    },
    "AUDUSD": {
      "active": false
    }
  },
  "signals": {
    "SPI200": 1,
    "AUDUSD": 0
  },
  "trade_log": [
    {
      "instrument": "SPI200",
      "direction": "LONG",
      "entry_date": "2025-03-01",
      "exit_date": "2025-03-15",
      "entry_price": 7600.0,
      "exit_price": 7800.0,
      "n_contracts": 1,
      "net_pnl": 4970.0,
      "exit_reason": "Trailing stop"
    }
  ],
  "equity_history": [
    {"date": "2025-03-01", "equity": 100000.0},
    {"date": "2025-03-15", "equity": 104970.0}
  ]
}
```

Functions:
```python
def load_state() -> dict
def save_state(state: dict) -> None
def record_trade(state: dict, trade: dict) -> dict
def update_equity_history(state: dict, date: str) -> dict
```

### `notifier.py`

Use the **Resend API** (https://resend.com) to send HTML emails. Resend is already set up for Carbon Bookkeeping and has a working API key.

```python
import os, requests

RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
FROM_EMAIL     = os.environ.get("FROM_EMAIL", "signals@carbonbookkeeping.com.au")
TO_EMAIL       = os.environ.get("TO_EMAIL")

def send_signal_email(report: dict) -> bool:
    """
    Send HTML email with signal report.
    report dict contains: date, signals, actions, positions, account, pnl_today
    Returns True if sent successfully.
    """
    html = build_email_html(report)
    response = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
        json={
            "from":    FROM_EMAIL,
            "to":      [TO_EMAIL],
            "subject": build_subject(report),
            "html":    html,
        }
    )
    return response.status_code == 200

def build_subject(report: dict) -> str:
    """
    Format: "📊 SPI Signal: LONG | AUD/USD: FLAT | P&L Today: +$1,250 — 12 Apr"
    Include 🔴 if any signal CHANGED today, 📊 if no change.
    """

def build_email_html(report: dict) -> str:
    """
    Build a clean, professional HTML email with:
    - Header with date and account value
    - Signal status table (instrument, signal, direction, entry price, stop, unrealised P&L)
    - ACTION REQUIRED section (bold, red border) if any signal changed today
    - Position details (entry, stop, contracts, pyramid level)
    - Today's P&L (realised + unrealised)
    - Running account equity
    - Last 5 closed trades table
    - Footer: "This is an automated signal — not financial advice"
    
    Style: dark background (#0f1117), green for LONG (#22c55e), 
    red for SHORT (#ef4444), gold for FLAT (#eab308).
    Mobile-responsive with inline CSS (email clients strip stylesheets).
    """
```

### `dashboard.py`

Generate a self-contained HTML file (`dashboard.html`) that:
- Shows current signal status for both instruments
- Shows account equity over time (use Chart.js from CDN)
- Shows open positions with real-time P&L calculation
- Shows last 20 closed trades in a table
- Shows key stats: total return, Sharpe, max drawdown, win rate
- Auto-refreshes every 60 seconds via `<meta http-equiv="refresh" content="60">`
- Reads from `state.json` directly (embed the JSON in the HTML)
- Same dark aesthetic as the backtests we built earlier

```python
def generate_dashboard(state: dict, instrument_data: dict) -> str:
    """
    Returns full HTML string.
    instrument_data = {
        "SPI200": {"price": 7850, "atr": 82, "adx": 28.5, "mom1": 0.021, ...},
        "AUDUSD": {"price": 0.632, "atr": 0.006, "adx": 22.1, ...}
    }
    """
```

### `main.py`

```python
"""
Main entry point — Replit runs this on schedule.
Workflow:
1. Load state
2. For each instrument: fetch data, compute indicators, get signal
3. Check for stop hits on open positions
4. Check for signal changes → generate actions
5. Check for pyramiding opportunities
6. Update unrealised P&L
7. Save state
8. Generate dashboard HTML
9. Send email notification (always daily, with ACTION REQUIRED if signal changed)
10. Print summary to console log
"""

import schedule, time

def run_daily_check():
    """Main daily job."""
    print(f"[{datetime.now()}] Running daily signal check...")
    # ... full workflow

def main():
    # Run immediately on start
    run_daily_check()
    
    # Then schedule for 8:00 AM AEST daily (UTC+10/11)
    # Replit runs in UTC, so 8am AEST = 22:00 UTC (or 21:00 UTC in AEDT)
    schedule.every().day.at("22:00").do(run_daily_check)  # 8am AEST
    
    print("Scheduler running. Press Ctrl+C to stop.")
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    main()
```

---

## REQUIREMENTS.TXT

```
yfinance>=0.2.40
pandas>=2.0.0
numpy>=1.24.0
requests>=2.31.0
schedule>=1.2.0
python-dotenv>=1.0.0
```

---

## ENVIRONMENT VARIABLES

Create a `.env.example` file:
```
# Resend API (already configured for Carbon Bookkeeping)
RESEND_API_KEY=re_xxxxxxxxxxxxxxxxxxxx

# Email settings
FROM_EMAIL=signals@carbonbookkeeping.com.au
TO_EMAIL=marc@carbonbookkeeping.com.au

# Optional: override starting account value
ACCOUNT_START=100000

# Optional: set to "true" to send test email on startup
SEND_TEST_ON_START=false
```

On Replit, add these in the **Secrets** tab (not in code).

---

## REPLIT SETUP INSTRUCTIONS (include as comments in main.py)

```
# REPLIT SETUP:
# 1. Create new Replit project → choose "Python" template
# 2. Upload all files from this project
# 3. In Replit Secrets tab, add:
#    - RESEND_API_KEY = your Resend API key
#    - TO_EMAIL = your email address
#    - FROM_EMAIL = your verified sender email
# 4. In pyproject.toml or replit.nix, ensure Python 3.11+
# 5. Click Run — app starts, runs immediately, then schedules daily at 8am AEST
# 6. Enable "Always On" in Replit settings (requires Replit Core plan ~$20/mo)
#    OR use Replit Deployments (Autoscale) for free cold-start runs
# 7. To keep free: use GitHub Actions instead (see alternative below)
#
# ALTERNATIVE (free, no Always On needed):
# Use GitHub Actions with a cron schedule:
# Schedule: "0 22 * * 1-5"  (8am AEST, weekdays only)
# The action checks out the repo, runs main.py, commits updated state.json
```

---

## EMAIL FORMAT SPECIFICATION

The daily email must look like this (build with inline CSS):

```
Subject (no action): 📊 SPI: LONG +$1,250 | FX: FLAT | Account: $156,420 — Mon 12 Apr
Subject (action):    🔴 ACTION: SPI Signal Changed → SHORT | Account: $156,420 — Mon 12 Apr

Body sections:
┌─────────────────────────────────────────┐
│  CARBON BOOKKEEPING — TRADING SIGNALS   │
│  Monday 12 April 2025  •  8:03 AM AEST  │
├─────────────────────────────────────────┤
│  ACCOUNT EQUITY                         │
│  $156,420  (+$56,420 / +56.4% total)    │
│  Today: +$1,250 unrealised              │
├─────────────────────────────────────────┤
│  🟢 SPI 200 — LONG (Active)             │
│  Entry: 7,650  |  Current: 7,850        │
│  Contracts: 2  |  Pyramid: Level 1      │
│  Trail Stop: 7,598  |  ATR: 82 pts      │
│  Unrealised P&L: +$5,000               │
│  ADX: 31.2  |  Mom(1/3/12m): +/+/+     │
├─────────────────────────────────────────┤
│  ⚪ AUD/USD — FLAT                      │
│  Price: 0.6312  |  ADX: 18.4 (< 25)    │
│  No active position                     │
├─────────────────────────────────────────┤
│  ⚠️  NO ACTION REQUIRED TODAY           │
│  (Signals unchanged from yesterday)     │
├─────────────────────────────────────────┤
│  RECENT CLOSED TRADES (last 5)          │
│  [table with dates, instrument, P&L]    │
├─────────────────────────────────────────┤
│  This is automated signal output.       │
│  Not financial advice. Always verify.   │
└─────────────────────────────────────────┘
```

When ACTION REQUIRED (signal changed):
```
┌──────────────────────────────────────────┐
│  🔴 ACTION REQUIRED                      │
│  SPI 200: Signal changed LONG → SHORT    │
│                                          │
│  CLOSE: Exit LONG position               │
│  Price at signal: 7,650                  │
│  Estimated P&L on close: +$3,750        │
│                                          │
│  OPEN: Enter SHORT position              │
│  Suggested entry: market open Monday     │
│  Size: 1 contract (0.5% risk)            │
│  Trail stop: 7,700 (+2×ATR from entry)   │
└──────────────────────────────────────────┘
```

---

## TESTING REQUIREMENTS

Add a `--test` flag to main.py:
```bash
python main.py --test
```
This should:
1. Run the full signal check
2. Print signal report to console (formatted clearly)
3. Send a test email with `[TEST]` prefix in subject
4. NOT update state.json (read-only test mode)

Add a `--reset` flag:
```bash
python main.py --reset
```
This resets state.json to initial values ($100,000, no positions, empty trade log).

Add a `--force-email` flag:
```bash
python main.py --force-email
```
Sends today's email immediately regardless of schedule.

---

## ERROR HANDLING REQUIREMENTS

- If Yahoo Finance fetch fails: retry 3 times with 10-second delays, then send error email and exit gracefully
- If Resend API fails: log error, write signal to console, continue (don't crash)
- If state.json is corrupted: backup the file, reinitialise from scratch, log warning in email
- All errors should be caught and logged — never let the app crash silently
- Add a health check: if last_run in state.json is more than 2 days old, include a warning in the next email

---

## CONSOLE OUTPUT FORMAT

Every run should print clearly to console (important for Replit logs):

```
================================================
 CARBON BOOKKEEPING — SIGNAL CHECK
 Date: Monday 12 April 2025  08:02 AEST
================================================
 Fetching SPI200 (^AXJO)...       ✓ 7,850 pts
 Fetching AUDUSD (AUDUSD=X)...    ✓ 0.6312

 SPI200:  ADX=31.2 | Mom(1m=+2.1% 3m=+4.8% 12m=+9.2%)
          Signal: LONG ✓ (unchanged)
          Position: LONG 2 contracts since 2025-03-01
          Unrealised P&L: +$5,000
          Trail Stop: 7,598

 AUDUSD:  ADX=18.4 (below 25 — FLAT gate active)
          Signal: FLAT (unchanged)
          No position.

 Account:  $156,420 (+56.4%)
 No actions required today.

 Email sent to marc@carbonbookkeeping.com.au ✓
 State saved ✓
================================================
```

---

## ADDITIONAL NOTES FOR CLAUDE CODE

- Use `python-dotenv` to load `.env` file locally, but on Replit the Secrets tab sets env vars directly
- The `state.json` file is the only persistent storage — Replit's filesystem persists between runs when "Always On" is active
- If using GitHub Actions instead of Always On, commit `state.json` back to the repo after each run
- Keep the dashboard.html generation fast — it runs every day alongside the signal check
- All dollar amounts should be formatted as Australian dollars (AUD)
- Dates/times should be in AEST/AEDT (UTC+10/+11) — use the `pytz` library: `timezone = pytz.timezone("Australia/Perth")` since Marc is in Perth (AWST, UTC+8)
- Perth is UTC+8 year-round (no daylight saving) — schedule email at "00:00" UTC for 8am AWST

---

## DEPLOYMENT CHECKLIST (create as a comment block in main.py)

```python
"""
DEPLOYMENT CHECKLIST:
 □ 1. Create Replit account at replit.com
 □ 2. New Repl → Import from GitHub (or upload files directly)
 □ 3. Add Secrets:
       RESEND_API_KEY  = re_...
       TO_EMAIL        = your@email.com
       FROM_EMAIL      = signals@yourdomain.com  (must be verified in Resend)
 □ 4. Run once: python main.py --test
       Check console output and email arrives
 □ 5. Run: python main.py --reset (if starting fresh)
 □ 6. Click "Run" button — scheduler starts
 □ 7. Enable Always On (Replit Core plan) OR
       Set up GitHub Actions cron (free alternative)
 □ 8. Verify first automated email arrives next morning (8am AWST)
 □ 9. Check state.json has updated after first automated run
 □ 10. Monitor: check Replit logs after first 3 runs
"""
```

---

## v1.2+ Long-Term Roadmap (Reference)

> **Captured:** 2026-04-29 from operator brainstorm (handwritten notes + chat)
> **Status:** Reference only — formal requirements deferred to `/gsd-new-milestone v1.2` (after v1.1 closes)
> **v1.1 status when captured:** mid-flight (Phases 14, 15, 16, 16.1 open) — v1.2 work does NOT begin until v1.1 ships

### Vision

Transform v1.1's single-operator hosted dashboard into a **friends-and-family multi-user paper-trade platform** with per-signal calculation transparency, manual trade journaling, stop-loss alerting, news integration, and a formal 5-year backtest validation gate. Top-of-volume market expansion stays out of scope until v2.0.

### Locked decisions (operator-confirmed 2026-04-29)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Trade execution | Paper-ledger only, never broker API | Operator places real trades manually; app journals + alerts only |
| Multi-user model | Friends-and-family (small N), super-admin = operator | Not SaaS; not for resale |
| 2FA method | TOTP (Authenticator app) | Free, offline, no SMS cost |
| Trade entry UX | Web form on dashboard | Structured fields, validates on submit |
| Stop-loss alert timing | BOTH: approaching (within 0.5×ATR) AND hit | Daily strategy, no intraday — alerts fire on next daily run |
| News source | `yfinance.Ticker(symbol).news` | Already in stack, free, instrument-specific |
| Stale data policy | Label only, no fail-loud | Daily strategy tolerates day-old data; surface staleness, don't block |
| Backtest validation | >100% cumulative return over 5y + report | Pass/fail gate; report viewable on dashboard |
| Calc transparency | Per-signal breakdown reproducible from displayed inputs | User can plug numbers into Excel/Bloomberg/IG and verify by hand |
| Instruments | SPI 200 + AUD/USD locked through v1.x | Top-10-volume expansion deferred to v2.0 |
| Language | Python (locked) | Already 16 phases in |

### Planned phase sequence (v1.2 — Multi-user paper-trade platform)

Numbering continues from v1.1 last phase (16.1 → 17). Subject to refinement at `/gsd-new-milestone`.

1. **Phase 17 — Per-signal calculation transparency.** Every signal exposes inputs (OHLC, prior values), intermediate indicators (TR, ATR, +DI, -DI, ADX, Mom1/3/12, RVol), formulas, and vote breakdown. Reproducible from displayed values alone. Hover-definitions for acronyms. Read-only dashboard feature; no schema change.
2. **Phase 18 — Multi-user data model.** `users` table (or JSON-file equivalent), RBAC roles `super_admin` / `user`, per-user data scoping, replaces shared-secret header auth from v1.1 with session-based login.
3. **Phase 19 — Paper-trade ledger.** Web form for manual trade entry (instrument, side, qty, entry price, stop). Per-user history view, P&L calculation, every row stamped with `STRATEGY_VERSION`.
4. **Phase 20 — Stop-loss monitoring & alerts.** On daily run: detect approaching (within 0.5×ATR of stop) AND hit conditions for each open paper trade. Email alert per event, deduplicated (one alert per stop event, not repeated daily).
5. **Phase 21 — News integration.** Top 5 articles per instrument from `yfinance.Ticker.news`, dedup by article URL, surfaced in daily email and on dashboard. Snapshot + business news fallback when no positions open or market closed.
6. **Phase 22 — Strategy versioning & audit trail.** `STRATEGY_VERSION` constant in `system_params.py`, bumped on any signal-logic change. Every signal output and trade row tagged with version so historical signals stay interpretable.
7. **Phase 23 — 5-year backtest validation gate.** Walk-forward backtest over 5y of yfinance data; pass criterion = >100% cumulative return. Report rendered on `/backtest` route on the dashboard. Sharpe, max drawdown, win rate, expectancy displayed but not gating.
8. **Phase 23.5 — Hygiene cleanup.** state.json + ledger backups (DO Spaces or git-backed nightly dump), per-user timezone preference, SPF/DKIM/DMARC verification on `mwiriadi.me`, email deliverability hygiene.

### Architecture additions (v1.2)

- New modules: `auth/` (TOTP via `pyotp`, session management), `ledger/` (paper-trade ledger, P&L), `news/` (yfinance.news adapter), `backtest/` (5y walk-forward).
- Hex-boundary rule extends: `auth/`, `ledger/`, `news/`, `backtest/` are own modules; cannot import `signal_engine` / `state_manager` directly — go through `main.py`.
- `STRATEGY_VERSION` constant lives in `system_params.py`. Every signal row in state and every trade row in ledger persists this version.
- Stack additions (pinned at phase implementation time): `pyotp` for TOTP, `qrcode` for TOTP setup QR, possibly `passlib` for password hashing.
- Storage: state.json grows or splits — likely move users + ledger to SQLite (single-file, no infra) once multi-user lands. Decision deferred to Phase 18 discuss.

### Hard constraints (preserved from v1.0/v1.1)

- **Signal-only.** No broker API, ever. Paper-ledger journals real trades the operator placed manually; the app never sends an order.
- **Daily cadence only.** No intraday data. Stop-loss alerts fire on the next daily run, not in real-time.
- **Python.** Locked.
- **DO droplet hosting.** No serverless, no container orchestration.

### Out of scope through v1.x

- Top-10-volume market expansion (deferred to v2.0)
- Broker API integration (hard constraint, never)
- Intraday / tick data
- SaaS multi-tenant (friends-and-family scale only)
- Real-time websocket dashboards
- Mobile native apps (responsive web is enough)

### Open questions to resolve at `/gsd-new-milestone v1.2`

1. SQLite vs JSON for users + ledger — depends on read/write patterns at Phase 18.
2. Per-user timezone display logic — affects email send time for non-Perth users.
3. Backup target — DO Spaces ($) vs git deploy-key push ($0) vs both.
4. Recovery codes for TOTP — generate-once-show-once vs printable PDF vs email.
5. Backtest data window — pure 5y, or rolling 5y window with quarterly retraining?

