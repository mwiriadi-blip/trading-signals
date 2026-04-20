# Pitfalls Research

**Domain:** Python mechanical trading signal app (daily-close, single-user, signal-only)
**Researched:** 2026-04-20
**Confidence:** HIGH — all pitfalls listed are either documented upstream issues (yfinance, Resend, GitHub Actions) or direct consequences of the SPEC.md logic. A handful of "silent risk breach" style items are MEDIUM because they depend on market regime to surface.

---

## Critical Pitfalls

These are the ones that make the app silently wrong, silently unsafe, or silently useless. In a signal-only app, a silently wrong signal is worse than a crash — the operator places real trades from it.

---

### Pitfall 1: yfinance silent partial / empty downloads

**What goes wrong:**
`yfinance.download(ticker, period="400d")` returns an empty DataFrame, a DataFrame missing the most recent bar, or one where only one of several tickers succeeded — with no exception raised. Downstream, `df.iloc[-1]` then reads a bar that is days old (weekend, holiday, Yahoo outage) and the app computes signals off stale data. This is by far the most common failure mode for any yfinance-based system.

**Why it happens:**
yfinance is a scraper, not an API. It absorbs HTTP errors, JSON-schema changes, and 429 rate limits into empty results rather than raising. Since late 2023 it has had repeated breakages (HTTP 429 "Too Many Requests", auth-token changes, curl_cffi dependency quirks). The library's own `progress=False, auto_adjust=...` defaults have also flipped between versions.

**How to avoid:**
- Explicitly assert on every fetch: `assert not df.empty`, `assert len(df) >= 250`, `assert df.index[-1].date() >= expected_last_business_day`.
- Pin `yfinance` to an exact version in `requirements.txt` (not `>=0.2.40`) and pin `curl_cffi` if installed. Bump deliberately, not on every deploy.
- Retry 3× with 10s backoff (already in SPEC) but treat "empty after retries" as a hard fail — send the error email, do NOT compute signals on stale data, do NOT write state.
- Always pass `auto_adjust=True` explicitly (the default changed in 0.2.51) and `progress=False` — silences log noise and locks behaviour.
- For indices, prefer `yf.Ticker("^AXJO").history(period="400d")` over `yf.download` — more stable for single-ticker pulls.
- Record `df.index[-1]` (the actual last bar date) in state.json every run. If it doesn't advance between two weekday runs, something is wrong.

**Warning signs:**
- `df.shape[0] < 300` when asking for 400 days.
- `df.index[-1]` is more than 3 calendar days behind `today` on a weekday.
- Indicators return `NaN` for the last row (insufficient history).
- Console log shows `YFPricesMissingError` or "No data found for this date range".

**Phase to address:**
Phase 2 (data fetch) — add `fetch_data_or_raise()` that validates shape, last-bar date, and NaN-freeness before returning.

---

### Pitfall 2: `^AXJO` vs Perth calendar date off-by-one

**What goes wrong:**
`^AXJO` closes at 16:00 AEST = 06:00 UTC. The job fires at 00:00 UTC (08:00 AWST). At that moment, yfinance's "latest bar" is YESTERDAY's ASX close (which is what we want). But if the run drifts (GitHub Actions cron slip) or if the app uses `datetime.now()` in the user's local zone to label the bar, the email can say "Signal for Mon 12 Apr" with Friday 9 Apr's close data, or vice versa. The operator then trades on a day-old signal believing it's current.

**Why it happens:**
Perth is UTC+8, Sydney is UTC+10/+11 (DST), ASX runs on Sydney time, yfinance returns UTC-aware but naive-in-practice indices, GitHub Actions schedules in UTC, Replit runs in UTC. Mixing these silently yields a one-day offset depending on which leg you trust.

**How to avoid:**
- Pick one canonical "as-of date" per run: **the date of the last completed ASX trading session** = `df.index[-1].date()` (after the assertions from Pitfall 1).
- Separate "signal-as-of date" (from df) from "run date" (from `datetime.now(Australia/Perth)`). Log both. Never substitute one for the other.
- If `signal_as_of < run_date - 1 business day`, abort with a loud warning — the market data is stale.
- Subject line and email header must quote the signal-as-of date, not the run date.
- Never use `datetime.today()` anywhere — always `datetime.now(pytz.timezone("Australia/Perth"))`.

**Warning signs:**
- Email subject date and in-body "as of" date disagree.
- state.json `last_run` advances but `signal_as_of` does not.
- Signal flips back and forth on consecutive days for no market reason (reading yesterday's and today's data alternately).

**Phase to address:**
Phase 2 (data fetch) and Phase 6 (email) — define and log the two dates separately from day one.

---

### Pitfall 3: Wilder ATR vs simple-moving-average ATR

**What goes wrong:**
Developer implements ATR(14) as a 14-period SMA of True Range instead of Wilder's exponential smoothing (alpha = 1/14). The numbers look plausible but diverge materially after 30+ bars, especially after volatility spikes. Position sizing, trailing stops, and pyramid thresholds are all ATR-based, so every downstream number is off. Backtest results no longer reconcile to live signals.

**Why it happens:**
Stack Overflow answers and most quick tutorials show SMA-based ATR — it's simpler. `pandas.ewm(alpha=1/14, adjust=False)` is the correct Wilder form, but it's easy to write `ewm(span=14)` (which implies alpha=2/15 ≈ Wilder-like but not identical) or `.rolling(14).mean()`.

**How to avoid:**
- Implement Wilder explicitly: `tr.ewm(alpha=1/period, adjust=False, min_periods=period).mean()`.
- Same rule for ADX — Wilder's +DM/-DM smoothing uses `alpha=1/period`, not `span=period`.
- Golden-file test: hand-calculate ATR for a known 30-bar fixture (or use pandas-ta / TA-Lib as a reference ONLY for the test, not runtime) and assert `abs(our_atr[-1] - reference_atr[-1]) < 1e-6`.
- Never use a library's default `.ewm(span=N)` without confirming the alpha.

**Warning signs:**
- ATR for `^AXJO` on a recent date diverges from Yahoo's own ATR or from TradingView's by more than ~5%.
- Trailing stops are hit suspiciously often (SMA-ATR is more reactive than Wilder).
- Backtest and live P&L diverge within the first few weeks.

**Phase to address:**
Phase 3 (indicators) — unit tests with golden files before any signal logic is written.

---

### Pitfall 4: ADX warm-up / garbage leading bars

**What goes wrong:**
ADX(20) needs roughly 2× the period (~40 bars) to converge to sensible values because Wilder smoothing is applied twice (once to +DM/-DM, once to DX). The first 40 bars after a fresh fetch return ADX values that wander between 0 and 100 meaninglessly. If the app computes a signal on a window that doesn't have enough history (e.g., a brand-new ticker, or after a yfinance partial fetch), it reads garbage ADX as "real" and either gates everything to FLAT or punches through the 25 threshold on noise.

**Why it happens:**
The spec fetches 400 days, which is plenty — but a partial fetch, a new listing, or a logic change to "just fetch 100 days for faster dev" breaks this silently. `min_periods` on pandas `ewm` defaults to 1, so a value IS returned even when it's meaningless.

**How to avoid:**
- Enforce `min_periods=period` on every Wilder `ewm` call so leading bars are NaN, not garbage.
- Require `len(df) >= 2 * max(period)` before reading `df.iloc[-1]`. The spec uses periods up to 252 (Mom12), so `len(df) >= 300` is the real minimum.
- If the last row has NaN in any of ATR / ADX / Mom1 / Mom3 / Mom12 / RVol, abort with warning — do NOT default-to-FLAT silently.

**Warning signs:**
- ADX values near 100 on calm markets, or near 0 on trending markets — both suggest warm-up is bad.
- `df.iloc[-1][["atr", "adx", "mom12"]].isna().any()` returns True.
- Signal flips between LONG and FLAT every day without market movement.

**Phase to address:**
Phase 3 (indicators) — NaN-safety assertions on the final row.

---

### Pitfall 5: Look-ahead bias (using today's close for today's signal)

**What goes wrong:**
Signal is computed from `df.iloc[-1]` which is today's daily bar. The operator reads the 08:00 AWST email and tries to act on it — but today's ASX close hasn't happened yet (market opens 10:00 AEST = 08:00 AWST). For `^AXJO`, `df.iloc[-1]` at 00:00 UTC is actually yesterday's Sydney close (which is fine). For `AUDUSD=X`, FX trades 24/5 — `df.iloc[-1]` may be a mid-session snapshot depending on when Yahoo rolls the daily bar. The operator thinks they're acting on a fresh signal, but they're either acting on yesterday's close (SPI, correctly) or a half-formed bar (FX, incorrectly).

**Why it happens:**
The two instruments have different "what does the latest daily bar mean" semantics. Yahoo's FX bars roll at 21:00 UTC (NY 5pm, end of the "trading day"). So at 00:00 UTC run time, `AUDUSD=X` latest bar is the bar that just closed 3 hours ago — good. But during NY DST changes, or if Yahoo is slow, the last bar may be 24 hours older.

**How to avoid:**
- For each instrument, define the expected "last bar staleness" and assert it: SPI last bar should be today-in-Sydney's close (≤ 8 hours old at 00:00 UTC). FX last bar should be ≤ 30 hours old at 00:00 UTC.
- Always use `df.iloc[-1]` for the signal, but log the bar's timestamp prominently.
- Backtests must use `signal[t] → trade at open[t+1]` convention. Live must match: "signal computed tonight → act at tomorrow's open". Email wording must say "act at next session open", not "act now".

**Warning signs:**
- AUD/USD last bar timestamp is suspiciously recent (<1h old) — might be an intraday snapshot.
- Operator reports trades filling far from the price shown in the email.

**Phase to address:**
Phase 2 + Phase 6 — make "act at next open, not now" explicit in the email copy and in bar-age assertions.

---

### Pitfall 6: Signal FLAT + active position — position never closes

**What goes wrong:**
Spec says "signal = FLAT when ADX<25". If the operator is in a LONG, and ADX drops below 25, the signal becomes FLAT. Does the app close the position? The SPEC has two separate exit rules: "signal reversal" (LONG→SHORT or SHORT→LONG) and "ADX<20 drop-out". Neither covers LONG→FLAT. The position sits open indefinitely with a stale signal, and the trailing stop is the only remaining exit.

**Why it happens:**
FLAT is semantically ambiguous — "no new entry" vs "close existing". Spec language in line 59 says "Signal reversal (new signal ≠ current position direction) → close and reverse/go flat" — "go flat" is listed, so LONG→FLAT should close. But implementer might read "reversal" narrowly as LONG↔SHORT only.

**How to avoid:**
- Implement exit check as: `if new_signal != current_direction and position.active: close`. FLAT (0) is a valid new_signal, so LONG (1) → 0 closes.
- Write a truth table test: all 9 combinations of {current: LONG/SHORT/none} × {signal: LONG/SHORT/FLAT} with expected action.
- Distinguish ADX<25 (signal gate — no entry, but existing trade ok unless ADX<20) from ADX<20 (active drop-out — close).

**Warning signs:**
- Position open with `signal == 0` and `adx < 25` persisting for days.
- Trade log shows no "signal reversal" exits, only "trailing stop" / "ADX drop-out".

**Phase to address:**
Phase 4 (signal + exit logic) — truth table test is mandatory.

---

### Pitfall 7: LONG→SHORT flip in one run — close + open same candle

**What goes wrong:**
Signal flips from LONG to SHORT in one run. The code closes the LONG, but forgets to open the SHORT in the same run — because the "open new position" block is gated on `if not position.active` at the top of the function, and it still sees the old state. Operator gets an "ACTION REQUIRED: close LONG" email but no "open SHORT" — misses half the trade.

**Why it happens:**
Single-pass logic: read state → compute → write state. The close step mutates `position.active = False`, but the open-new-position check was already skipped because at the top of the function the position was active. Order-of-operations bug.

**How to avoid:**
- Two-phase logic: (1) evaluate and apply exits (stop, reversal, ADX drop-out), (2) evaluate and apply entries on the updated state.
- Write a test for LONG→SHORT in one day — assert a close and an open are both present in the trade log.
- Email must list both actions clearly: "CLOSE: exit LONG" AND "OPEN: enter SHORT" (the SPEC email mock already shows this — don't let the code diverge).

**Warning signs:**
- Signal history shows a LONG→SHORT flip but trade log only has one event that day.
- state.json has `direction: "SHORT"` but no corresponding entry in trade_log.

**Phase to address:**
Phase 4 (signal + exit logic) — two-phase eval with explicit test.

---

### Pitfall 8: `vol_scale = clip(0.12 / RVol, 0.3, 2.0)` — RVol near zero explodes

**What goes wrong:**
On an extremely quiet 20-day window (holiday stretch, summer doldrums in FX), `RVol` can be 0.02–0.04 annualised. `0.12 / 0.03 = 4.0`, which clips to 2.0 — the cap works. But if `RVol == 0` exactly (every day's return was zero — rare but possible on a stale data window, or when Yahoo returns duplicate closes), it's `ZeroDivisionError` or `inf`, and the `clip` with `inf` yields 2.0 silently. Sizing maxes out on what is actually garbage data.

**Why it happens:**
The clip at 2.0 masks all upside blow-ups. Division by near-zero isn't visible unless you log the raw ratio. Duplicate closes from yfinance (weekend misfills, holidays reported as trading days) cause exact zero daily returns.

**How to avoid:**
- `rvol = max(rvol, 0.01)` before the division — floor at 1% annualised is physically sensible.
- Log the raw `0.12 / rvol` value before clipping, and warn if clipped at either bound.
- If more than 5 of the last 20 daily returns are exactly zero, abort — data is bad.

**Warning signs:**
- `vol_scale == 2.0` consistently over multiple runs (always hitting the cap).
- `rvol < 0.05` in logs.
- Duplicate Close values on consecutive days in raw df.

**Phase to address:**
Phase 3 (indicators) and Phase 5 (sizing) — rvol floor + data-quality assertion.

---

### Pitfall 9: `n_contracts = max(1, int(...))` — silent risk breach on small accounts

**What goes wrong:**
If the risk-budget math yields 0.3 contracts, `max(1, int(0.3)) = 1`. The operator is now risking MORE than the intended 1.0% of account on the trade because one full SPI contract ($25/pt × trail × ATR) exceeds the risk budget. No error, no warning — the risk rule is silently violated every time the account is too small.

**Why it happens:**
The `max(1, ...)` floor is a convenience for "never accept a no-trade outcome", but it overrides the risk-control intent. At $100k starting account with SPI ATR = 85, stop = 3×85 = 255 pts, one contract = $6,375 notional stop. 1.0% of $100k = $1,000. Already breached by 6×.

**How to avoid:**
- Replace `max(1, int(...))` with: `n = int(raw)`; `if n == 0: skip trade with warning ("position too small to honour risk budget")`.
- Alternative: keep the floor but surface it loudly in the email — "WARNING: 1 contract exceeds 1.0% risk — actual risk = 6.4%".
- Document the effective risk per contract per instrument in the dashboard so the breach is always visible.

**Warning signs:**
- Trade log shows 1-contract trades with P&L swings far larger than 1% of account.
- Dashboard "risk used" metric consistently above stated risk_pct.

**Phase to address:**
Phase 5 (sizing) — decide floor policy explicitly (accept the breach with warning, or skip).

---

### Pitfall 10: Pyramiding double-adds on the same day

**What goes wrong:**
Price gaps up from entry and on one candle, unrealised profit jumps from 0 to +2.3×ATR. The check `if unrealised >= 1×ATR: add 1` fires, then `if unrealised >= 2×ATR: add another` fires in the same run. Operator gets 2 new contracts on the same day, contrary to the intent of one-contract-per-level. Or, without state tracking, the +1×ATR rule fires every single day the profit remains above 1×ATR, adding a contract daily.

**Why it happens:**
Pyramid level must be persisted (SPEC line 66: "Track pyramid level in state" — good). But the check-next-level logic needs to look at `pyramid_level` (0/1/2) not "current unrealised vs threshold". If unrealised is +2.3×ATR and `pyramid_level == 0`, do we add 1 (to level 1) or 2 (jump to level 2)?

**How to avoid:**
- Lock to "one pyramid add per run": check `pyramid_level`, evaluate the next threshold only, increment by 1 max.
  ```
  if pyramid_level == 0 and unrealised >= 1 * atr_entry: add 1, level = 1
  elif pyramid_level == 1 and unrealised >= 2 * atr_entry: add 1, level = 2
  ```
- Thresholds measure from entry price (SPEC line 65), NOT from peak. Store `atr_entry` on entry and never update it (already in state schema — good).
- Add-contract price is the current close (today's), not entry — log it in the trade log.

**Warning signs:**
- Trade log on same date has two pyramid-add events.
- `pyramid_level` jumps from 0 to 2 in one day.
- Contract count exceeds 3.

**Phase to address:**
Phase 5 (sizing + pyramiding) — state-machine test with gap-up fixture.

---

### Pitfall 11: Trailing stop uses close only, ignores intraday high/low

**What goes wrong:**
For a LONG, the trailing stop is `peak_price - 3×ATR`. If `peak_price` only updates from close (not from high), a day where intraday high was 8,050 but close was 7,900 never raises the peak. Conversely, if the check-stop-hit logic only compares `today.close < stop`, a day where intraday low was 7,500 (below stop) but close recovered to 7,700 never triggers the stop. SPEC line 61 says "Update peak daily" but is silent on intraday.

**Why it happens:**
Using close-only is simpler and avoids "ghost stops" where a flash-dip triggers an exit. But backtests and the operator's real behaviour are inconsistent — the operator's actual broker stop fires on low, not close.

**How to avoid:**
- Decide and document the convention. For a DAILY signal app that is decision-driven (not bracket-order driven), the consistent choice is:
  - Update peak from `today.high` (LONG) / trough from `today.low` (SHORT).
  - Check stop hit against `today.low` (LONG) / `today.high` (SHORT). If `low <= stop` → exit at stop price on that day.
- If stop was hit intraday but close recovered, the SPEC says "check on candle" — exit is deemed hit. Log "exit price = stop price" not "close price".
- This matches the backtest convention for a "trailing stop on the candle" system.

**Warning signs:**
- Trailing stop never moves up during a trending run (because close never made a new high even though high did).
- Exit P&L in trade log matches close, not stop (suggests close-only logic is in use).

**Phase to address:**
Phase 4 (exit rules) — test with a fixture where intraday high > yesterday high but close < yesterday close.

---

### Pitfall 12: Contract math off-by-multiplier (SPI vs FX)

**What goes wrong:**
SPI pnl = `(exit - entry) × 25 × n`. AUD/USD pnl = `(exit - entry) × 10000 × n`. A single hardcoded `25` or `10000` in the wrong place yields wrong P&L (either 400× too small or 400× too large). Dashboard shows account at $156,420 but it should be $101,400 or $2.4M.

**Why it happens:**
Multiplier is instrument-specific, but one common `compute_pnl(entry, exit, n)` function in `signal_engine.py` is tempting.

**How to avoid:**
- Pass `multiplier` as an explicit parameter to every P&L function — never hardcode.
- Define instrument specs in one constants dict at the top of `signal_engine.py`:
  ```
  INSTRUMENTS = {
    "SPI200": {"ticker": "^AXJO", "multiplier": 25,    "round_trip_cost": 30, "risk_long": 0.010, "risk_short": 0.005, ...},
    "AUDUSD": {"ticker": "AUDUSD=X", "multiplier": 10000, "round_trip_cost": 5,  ... },
  }
  ```
- Unit test every P&L calc for both instruments against a worked example with known numbers.

**Warning signs:**
- Equity curve moves by implausible daily amounts (single-day swings > 5% of account).
- Unrealised P&L displayed doesn't match `(current - entry) × multiplier × n`.

**Phase to address:**
Phase 5 (sizing + P&L) — constants dict + unit tests for both instruments.

---

### Pitfall 13: state.json crash mid-write corrupts state

**What goes wrong:**
Python process is killed mid-`json.dump` (Replit redeploy, GHA job timeout, SIGKILL). The file on disk is half-written, no-valid-JSON. Next run: `json.load` raises, the recovery code re-initialises to $100,000 — weeks of trade history and current positions are GONE.

**Why it happens:**
Default `open(path, 'w')` + `json.dump` does not atomically replace — the file is truncated, then progressively written. Any crash in between is fatal.

**How to avoid:**
Atomic write pattern:
```python
import os, tempfile, json
def save_state(state, path="state.json"):
    dir_ = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp = tempfile.mkstemp(prefix=".state.", suffix=".tmp", dir=dir_)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(state, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)  # atomic on POSIX
    except Exception:
        try: os.unlink(tmp)
        except: pass
        raise
```
Keep an N-day rolling backup: before write, copy `state.json` to `state.json.bak` (and optionally `state.YYYY-MM-DD.json`). Commit these in GHA mode so recovery is one git revert.

Add a `schema_version` field to state.json from day one (SPEC doesn't include one). Every load checks version and migrates.

**Warning signs:**
- `JSONDecodeError` in logs.
- state.json `last_run` in the past by more than a day.
- Trade log empty on a system that has been running.

**Phase to address:**
Phase 7 (state persistence) — atomic write + backup + schema_version.

---

### Pitfall 14: Resend sender-domain / email deliverability

**What goes wrong:**
First email never arrives. Resend returns 200 OK with `{"id": "..."}` but the message is silently rejected by the recipient's MX because the From domain isn't verified on Resend, or SPF/DKIM/DMARC isn't set up. From then on, the app "works" by its own logic but no emails land.

**Why it happens:**
Resend requires domain verification via DNS records (SPF, DKIM, DMARC CNAMEs). Without them, major providers (Gmail, Outlook, Apple) drop or spam-box. A 200 response from Resend's API means "accepted by Resend", not "delivered to recipient".

**How to avoid:**
- Verify `carbonbookkeeping.com.au` on Resend — SPF, DKIM (both CNAMEs), DMARC record. MEMORY.md says Resend is already configured for Carbon Bookkeeping, so this is likely done — but verify `signals@` specifically is allowed.
- On first deploy, send a `--test` email and confirm receipt in inbox (not spam) before scheduling anything.
- Store Resend's returned `id` in state.json or logs so bounces can be correlated.
- Escape HTML in anything user-visible (subject, date strings, instrument names — the spec is pretty safe here but don't inject raw `dict` values into HTML without escaping).
- Inline CSS only — no `<style>` blocks, no `<link rel="stylesheet">` (SPEC already says this).
- Subject line ≤ ~78 chars for Outlook single-line rendering; the ACTION subject mock is ~60 chars which is fine.

**Warning signs:**
- Resend API returns 200 but email not in inbox (check Resend dashboard "Emails" tab — delivered/bounced/complained).
- Gmail puts the email in spam even on first send.
- SPF/DKIM fail tags in raw email headers.

**Phase to address:**
Phase 6 (email) — include Resend dashboard check in the deploy checklist.

---

### Pitfall 15: `<meta refresh>` on dashboard hammers the filesystem

**What goes wrong:**
Dashboard uses `<meta http-equiv="refresh" content="60">`. This reloads the static HTML from disk every 60s per open tab. On Replit Autoscale, file reads wake the container; on GHA mode the file doesn't change between runs anyway. If Marc leaves the dashboard open in a browser tab for days, it fetches the same HTML forever. Minor waste, but more importantly the data shown only updates once per day — auto-refresh creates false expectation of intraday updates.

**Why it happens:**
Auto-refresh is a 1990s pattern carried over by habit. For a daily-updated app, it's pointless.

**How to avoid:**
- Either drop the `<meta refresh>` entirely (dashboard is daily, not real-time — show "Last updated: Mon 12 Apr 08:02 AWST" prominently instead), or set it to a generous interval (e.g. 3600 = 1 hour) to reduce noise.
- Better: show a big "Last signal: Mon 12 Apr" timestamp and trust the user to reload manually.

**Warning signs:**
- Replit metrics show thousands of GET /dashboard.html per day (if served via HTTP).
- Dashboard shows "Last updated" timestamps that aren't actually newer after refresh.

**Phase to address:**
Phase 8 (dashboard) — replace with manual reload pattern.

---

### Pitfall 16: Chart.js CDN goes down or changes URL

**What goes wrong:**
Dashboard references `https://cdn.jsdelivr.net/npm/chart.js@latest`. One day the CDN is blocked by the operator's network, or `@latest` serves a new major version that breaks the config API, and the equity chart vanishes.

**Why it happens:**
`@latest` is a floating tag. CDNs go down. Corporate Wi-Fi blocks `jsdelivr`.

**How to avoid:**
- Pin an exact version: `chart.js@4.4.0` (or whatever is current at build time).
- Use `integrity="sha384-..." crossorigin="anonymous"` for SRI to fail loudly on tampering.
- For extra safety, vendor Chart.js into the repo (~70KB minified) and reference it locally — zero runtime CDN dependency.

**Warning signs:**
- Dashboard shows empty div where chart should be.
- Browser console shows CORS/SRI/404 on chart.js.

**Phase to address:**
Phase 8 (dashboard) — pinned version + SRI, optionally vendored.

---

### Pitfall 17: Replit Autoscale loses file writes / no Always On

**What goes wrong:**
Without Always On (paid), Replit sleeps the container. The `schedule` library's daily 00:00 UTC tick never fires because the process isn't running. Or, on Replit Deployments (Autoscale), each request spawns a fresh container with a fresh filesystem — state.json writes from one request vanish by the next. App appears to run fine on first test but never sends automated emails, and positions never persist.

**Why it happens:**
Replit's Autoscale was built for stateless web servers, not stateful cron jobs. The `schedule` library requires a long-running process. Replit's free tier aggressively sleeps after inactivity.

**How to avoid:**
- For production, GitHub Actions with `cron: "0 0 * * 1-5"` is the free, correct primary — it's stateless-by-design and commits state back. The SPEC calls it a "fallback" but realistically it should be primary.
- If sticking with Replit, require Replit Core and Always On. Document this explicitly in the deploy guide.
- Never rely on Replit Deployments (Autoscale) for this app — wrong tool.

**Warning signs:**
- Emails stop arriving after the first manual run.
- state.json on disk doesn't advance `last_run` across days.
- Replit console shows "App is sleeping" or no recent log output.

**Phase to address:**
Phase 9 (deployment) — GitHub Actions is the documented primary path; Replit Always On is optional.

---

### Pitfall 18: GitHub Actions — state.json commit-back race / permissions

**What goes wrong:**
Cron fires twice in quick succession (rare but possible under GHA load). Two jobs run `git pull`, each commits a different state.json, one push fails with non-fast-forward. Or, the workflow lacks `permissions: contents: write` and the push silently fails with 403. state.json stops updating, silent.

**Why it happens:**
GitHub Actions default token permissions were tightened in 2022 — `contents: write` must be explicit. `git push` failures don't fail the workflow unless `set -e` and proper exit-code handling are in place. Cron can drift 30+ minutes under GHA load, making "once daily" less reliable than it seems.

**How to avoid:**
- Set `permissions: contents: write` at workflow level.
- Use `concurrency: { group: trading-signals, cancel-in-progress: false }` so overlapping runs queue rather than race.
- After commit+push, re-verify: `git log -1` shows the expected message. Exit non-zero if push fails.
- Never echo secrets in workflow logs — quote env usage: `env.RESEND_API_KEY: ${{ secrets.RESEND_API_KEY }}` (not `echo`).
- Use `actions/checkout@v4` with `persist-credentials: true` and the default GITHUB_TOKEN — no PAT needed.
- Expect up to ~30 min cron drift; the 00:00 UTC trigger may actually fire at 00:05–00:30 UTC. Fine for daily signals, but document it.

**Warning signs:**
- GHA workflow "succeeded" but state.json on main branch is unchanged.
- Two workflow runs in the same day.
- `git push` errors in logs.

**Phase to address:**
Phase 9 (deployment — GHA path) — explicit permissions, concurrency group, push verification.

---

### Pitfall 19: `--test` flag writes state anyway

**What goes wrong:**
SPEC explicitly says `--test` must NOT update state.json. A straightforward implementation has `save_state(state)` at the end of `run_daily_check()` regardless of flags — `--test` runs, sends the test email, but also writes state. Now every test run corrupts production state: pyramid levels change, equity history grows, last_run advances.

**Why it happens:**
Test-mode flag is plumbed to the email prefix only, not to the state writer.

**How to avoid:**
- Pass `read_only=True` through the pipeline and guard every write: `save_state`, `update_equity_history`, `record_trade`.
- Better: structure main flow as `computed = compute_everything(state)` → `if not args.test: state = apply(state, computed); save_state(state)`. Never mutate state in the compute path.
- Write a test: run `main.py --test`, assert `state.json` mtime and content are unchanged.

**Warning signs:**
- state.json changes after a `--test` run.
- Trade log contains entries from test runs.
- `equity_history` has unexpected entries with round-number test prices.

**Phase to address:**
Phase 10 (CLI flags + testing) — structural separation of compute and persist.

---

### Pitfall 20: Tests run against live yfinance, not fixtures

**What goes wrong:**
Indicator unit tests call `yf.download()` directly. CI runs every push, yfinance rate-limits the GitHub Actions runner IP, tests go red on 429, or pass flakily because the market data changed. Worse: tests use today's data as expected values, so they never actually detect regressions — they just compute the same numbers both sides.

**Why it happens:**
Quick-start tutorials write live-API tests. Developers don't want to maintain fixtures.

**How to avoid:**
- Commit 2–3 CSV fixtures of OHLCV data (e.g., `fixtures/axjo_2024.csv`, `fixtures/audusd_2024.csv`) with 400+ bars.
- Compute golden-file indicator outputs once, commit them, and assert exact equality (or 1e-9 tolerance).
- Every indicator test reads from fixture CSV via `pd.read_csv` — no network.
- A separate `integration_test.py` that hits live yfinance — run manually, not in CI.
- Deterministic: all random-seeded operations (none in this app, but principle holds) and no `datetime.now()` in compute paths (pass `as_of` explicitly).

**Warning signs:**
- CI red due to network flake.
- Tests "pass" after a bug was introduced because they recompute expected values live.

**Phase to address:**
Phase 3 (indicators) and Phase 10 (tests) — fixture-driven from day one.

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| `max(1, int(raw))` in sizing | Always get a trade | Silent risk breach on small accounts (Pitfall 9) | Only if clearly flagged in email every time |
| `@latest` on Chart.js CDN | No version bumps to maintain | One day it breaks with no warning (Pitfall 16) | Dev-time only — pin for prod |
| Close-only trailing stops | Simpler code | Mismatch with operator's broker stop behaviour (Pitfall 11) | Only if explicit "daily decision system" is documented — still risky |
| `save_state` regardless of `--test` | One code path | Test runs corrupt prod state (Pitfall 19) | Never |
| Live-API tests | No fixture maintenance | Flaky CI, non-deterministic regressions (Pitfall 20) | Integration suite only, not unit |
| No `schema_version` in state.json | Faster initial build | Every future schema change risks data loss | Only if the app is truly throwaway |
| `yfinance>=0.2.40` unpinned | Auto-pick up bug fixes | Auto-pick up breakages (yfinance churns constantly) | Never in prod |
| Skip SRI on CDN scripts | Less HTML to write | CDN compromise = XSS on your dashboard | Only for local dev |
| Replit Autoscale deploy | Free tier | No persistence, no scheduler, emails never send (Pitfall 17) | Never for this app |
| Single-file `main.py` | Fast first ship | Hard to test any one piece in isolation | Until first bug — then split |

---

## Integration Gotchas

Common mistakes when connecting to external services.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| yfinance | Trust return value without shape/date checks | Assert non-empty, assert `len >= 300`, assert `last_bar.date()` is recent (Pitfall 1) |
| yfinance | `yf.download(auto_adjust=...)` default flipped — using default without setting it explicitly | Always pass `auto_adjust=True` explicitly |
| yfinance | Treat `^AXJO` and `AUDUSD=X` identically for "last bar freshness" | Different markets close at different UTC times — set per-instrument staleness budget (Pitfall 2, 5) |
| Resend API | 200 response = delivered | 200 = accepted. Check Resend dashboard for delivered/bounced (Pitfall 14) |
| Resend API | Unverified sender domain | Set up SPF/DKIM/DMARC on `carbonbookkeeping.com.au` — MEMORY says done, re-verify |
| Resend API | `<style>` block in HTML email | Inline CSS only — clients strip head styles |
| Resend API | Missing `TO_EMAIL` env var → send to empty array | Validate env on startup, fail loud |
| GitHub Actions | Default token can't push | Set `permissions: contents: write` at workflow level (Pitfall 18) |
| GitHub Actions | Cron "0 0 * * 1-5" is exact | Drift up to 30 min is normal — don't schedule-critical |
| GitHub Actions | `echo $RESEND_API_KEY` for debug | Secrets are masked in logs but not foolproof — never echo |
| GitHub Actions | Two concurrent runs racing on state.json | Use `concurrency:` block to serialise |
| Replit Secrets | Code reads from `os.environ` before Secrets tab populated | Always validate env on startup; fail with a clear error |
| Replit filesystem | Assume Autoscale persists files | It doesn't — use Always On (paid) OR GHA with commit-back |
| Chart.js CDN | `@latest` tag | Pin exact version + SRI hash (Pitfall 16) |
| pytz | `pytz.timezone("Australia/Perth")` combined with `datetime.now()` | Use `datetime.now(pytz.timezone("Australia/Perth"))` — the naive-localize pattern is error-prone |

---

## Performance Traps

Patterns that work at small scale but fail as usage grows. (This app is single-user, so scale concerns are minimal — but a few still bite.)

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Unbounded `trade_log` and `equity_history` in state.json | state.json grows ~2KB/week; dashboard HTML grows; email HTML grows | Cap `equity_history` at 365 entries; keep full trade_log but render only last 20 in email/dashboard | After ~5 years of running, state.json would be >1MB and noticeably slow to read/write |
| Embedding full JSON state in `dashboard.html` | Dashboard page size balloons with history | Embed only last 20 trades + last 180 equity points; keep full state separate | After 1+ year of history, dashboard HTML exceeds 500KB |
| yfinance cold-cache on every run | Each run downloads 400 bars × 2 tickers | Fine — it's once a day. No caching needed | Never for this app (but would matter at 1-min cadence) |
| Re-fetching 400 days every run when last 2 days would do | Bandwidth / rate limit | Acceptable for daily cadence | Never for this app |

---

## Security Mistakes

Domain-specific issues beyond standard web-app concerns. Signal-only + single-user means most OWASP doesn't apply, but these do.

| Mistake | Risk | Prevention |
|---------|------|------------|
| Committing `state.json` with real positions or any API key | Leaking trading activity to anyone with repo read access | `.gitignore` state.json locally; in GHA mode, use a PRIVATE repo only; never commit `.env` |
| `RESEND_API_KEY` printed in error output | Rotated key, Resend abuse | Wrap all exception logging to redact env values; never `print(os.environ)` |
| Any code path that could place a real order | Spec hard-constraint violation: "signal-only" | Grep for `place_order`, `buy`, `sell`, `submit`, `execute`, broker SDK imports before every release; explicit test asserts no broker libs in `requirements.txt` |
| `eval()` or `exec()` on Yahoo data (unlikely but tempting for dynamic indicator config) | RCE via crafted ticker response (improbable but compounds) | Never eval anything; indicators are fixed in code |
| Email HTML injects unescaped strings (e.g. instrument name from future config) | HTML injection in the user's own inbox — mostly cosmetic but could hide phishing | `html.escape()` on every interpolated string in email HTML |
| `--reset` without confirmation | Operator fat-finger wipes weeks of history | Require `--reset --yes-i-mean-it`, back up current state.json to `state.backup.YYYY-MM-DD.json` before reset |
| `--force-email` in automation | Could spam the inbox if left in a loop | Only a CLI flag, never an env trigger; log every `--force-email` invocation |
| GitHub Actions workflow echoing env in debug | Secret leak to anyone with actions log read | Never `run: echo $FOO`; use step-level `env:` |

---

## UX Pitfalls

Common user experience mistakes in this domain.

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Email says "ACTION REQUIRED: enter SHORT" at 08:00 AWST when ASX is closed | Operator tries to enter, gets confused about fills | Email copy says "at next session open" (Pitfall 5); dashboard shows "Next session: Mon 10:00 AEST" |
| P&L shown in mix of realised and unrealised without labels | Operator thinks a number is booked when it isn't | Separate sections in email and dashboard. Never show a single "P&L" total that blurs the two |
| Email subject line truncated by Outlook at ~78 chars | Key info hidden | Put the most critical info (ACTION vs no-action, account value) first in subject |
| Dark-mode email rendering breaks dark-on-dark (e.g., dark-bg email in dark-mode client inverts text and backgrounds independently) | Unreadable email | Test in Gmail dark mode, Apple Mail dark mode. Use `@media (prefers-color-scheme: dark)` isn't supported in most clients — inline explicit colours always |
| Dashboard "Today's P&L" rolls over at UTC midnight not Perth midnight | "Today" numbers change at the wrong moment | All date labels in AWST using `datetime.now(pytz.timezone("Australia/Perth"))` |
| Signal changes mid-week are noisy (whipsaw) — many emails with ACTION REQUIRED that get reversed days later | Alert fatigue, missed real signals | ADX gate (already in spec) mitigates but not fully; add a "this is the Nth reversal in 14 days" note to the email when churn is high |
| "1 contract" implied as "definitely tradable" but SPI mini contract is the actual retail instrument | Operator confused whether "1 SPI contract" at $25/pt is realistic for their broker | Dashboard/email clarifies: "SPI = $25/pt multiplier (full ASX 200 futures contract, ~A$200k notional)". If operator actually trades SPI mini, multiplier is $5/pt |
| `--test` email looks identical to real email → operator acts on it | Fake signal acted on | `[TEST]` prefix in subject (SPEC says so); also watermark in email body: big yellow "TEST — DO NOT TRADE" banner |

---

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces. Use during verification at each phase.

- [ ] **Data fetch:** App runs, console shows prices — verify `df.index[-1].date()` is today-in-Sydney close, not a 3-day-old stale bar (Pitfall 1, 2).
- [ ] **Indicators:** Numbers print — verify ATR/ADX match a golden file to 1e-9 tolerance, not just "look reasonable" (Pitfall 3, 4).
- [ ] **Signal logic:** LONG/SHORT/FLAT shown — verify all 9 cells of the {current × new-signal} truth table with actual tests (Pitfall 6, 7).
- [ ] **Position sizing:** n_contracts printed — verify the effective risk per contract is logged AND that n=0 cases are handled (Pitfall 9).
- [ ] **Pyramiding:** `pyramid_level` advances — verify a same-day gap-up test case does NOT double-add (Pitfall 10).
- [ ] **Trailing stop:** Stop price moves — verify it moves based on intraday HIGH (not close) and that stop-hit logic uses intraday LOW (Pitfall 11).
- [ ] **Contract P&L:** Numbers look right — verify worked examples for BOTH instruments with explicit multiplier constants, not just "the test passes" (Pitfall 12).
- [ ] **State persistence:** state.json is written — verify (1) atomic write (kill -9 mid-write leaves old file intact), (2) schema_version field present, (3) backup file exists (Pitfall 13).
- [ ] **Email delivery:** Resend returns 200 — verify email actually in INBOX, not spam; Resend dashboard says "delivered", not just "sent" (Pitfall 14).
- [ ] **Email HTML:** Renders in Gmail — verify in Apple Mail, Outlook, Gmail dark mode, iPhone Mail. All four. Screenshots in the PR.
- [ ] **`--test` flag:** Sends test email — verify state.json mtime and content UNCHANGED after the run (Pitfall 19).
- [ ] **`--reset` flag:** Resets state — verify a backup was written first and a confirmation flag was required.
- [ ] **Scheduler:** App "runs daily" — verify the SECOND day actually fires (leave it overnight; check Replit/GHA logs for the 00:00 UTC run).
- [ ] **GitHub Actions:** Workflow green — verify state.json on `main` branch advanced after the run (Pitfall 18).
- [ ] **Dashboard:** HTML renders — verify Chart.js loaded (not a blank div), and timestamps are in AWST (Pitfall 15, 16).
- [ ] **Error paths:** "Handled gracefully" — verify with actual fault injection: delete state.json, corrupt it, kill network mid-fetch, invalid Resend key. Each should produce a readable error and not crash silently.
- [ ] **Timezones:** Dates "look right" — verify at AWST 00:30 (just after midnight Perth) that dashboard/email still show yesterday's signal, not tomorrow's (Pitfall 2).
- [ ] **Signal-only constraint:** Grep `requirements.txt` and all source for broker SDK imports (`ib_insync`, `ccxt`, `alpaca`, etc.). Zero results required.
- [ ] **Secrets:** Not in repo — `git log -p | grep -iE "re_[a-z0-9]{20,}"` returns nothing; `.env` is gitignored; state.json containing no secrets.

---

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Corrupted state.json (Pitfall 13) | LOW if backups exist | Restore `state.json.bak`. If none, reconstruct from trade log in last email + current market prices. Re-compute equity_history from trade_log. |
| Wrong indicator math deployed (Pitfall 3, 4) | MEDIUM | Fix the math. Replay last N days against fixtures to confirm golden files now match. Flag any open position opened on wrong-math signal — operator decides whether to close. |
| Silent yfinance stale data (Pitfall 1, 2) | LOW | Abort run, email "DATA STALE — no signal generated today". Operator checks manually. No state mutation. |
| LONG→SHORT flip missed half (Pitfall 7) | HIGH | Manually patch state.json: close the LONG with today's close, open the SHORT with today's close. Log a manual-intervention entry in trade_log. Add regression test. |
| Pyramid double-add (Pitfall 10) | MEDIUM | Reverse the extra add in state.json: `n_contracts -= 1`, `pyramid_level -= 1`. Note in trade log. Operator knows to close one contract in their actual book. |
| Risk breach from `max(1, int(...))` (Pitfall 9) | LOW if caught same day | Close the trade, accept the loss, document. Add the "skip trade" alternative. |
| Email didn't send / didn't deliver (Pitfall 14) | LOW | Check Resend dashboard. If delivery failed: fix domain verification, then `--force-email` to resend today's report. State unaffected. |
| GHA stopped committing state (Pitfall 18) | MEDIUM | Find the divergence point in git log. Fast-forward from last-good state.json. Manually replay missing days using saved emails as source-of-truth. |
| Chart.js CDN down (Pitfall 16) | LOW | Vendor Chart.js locally, redeploy. Dashboard back in 5 minutes. |
| `--test` corrupted state (Pitfall 19) | HIGH if not detected | Restore from backup. Fix the code. Add the "mtime unchanged after --test" assertion. |
| yfinance version breakage | MEDIUM | Pin to previous working version in `requirements.txt`, redeploy. File an issue upstream. |
| Replit went down / didn't wake | LOW | Switch to GHA primary (should already be the primary). |
| Operator acted on test email (UX Pitfalls) | Depends on trade outcome | Make `[TEST]` watermark impossible to miss. |

---

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls. (Phase numbers are suggested — roadmap will finalise.)

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 1. yfinance silent partial | Phase 2 (fetch) | Assertions on df shape + last-bar date; logged per run |
| 2. AXJO / Perth date off-by-one | Phase 2 + Phase 6 | Log both `signal_as_of` and `run_date`; test at AWST 00:30 rollover |
| 3. Wilder ATR wrong | Phase 3 (indicators) | Golden-file test with 1e-9 tolerance |
| 4. ADX warm-up garbage | Phase 3 (indicators) | `min_periods=period` on ewm; assert no NaN on last row |
| 5. Look-ahead bias | Phase 2 + Phase 6 | Email copy says "act at next open"; bar-age assertion |
| 6. FLAT doesn't close position | Phase 4 (signal/exit) | 9-cell truth table test |
| 7. LONG→SHORT one-run flip | Phase 4 (signal/exit) | Two-phase eval + explicit test |
| 8. RVol near zero | Phase 3 + Phase 5 | Floor `rvol = max(rvol, 0.01)`; data-quality assert |
| 9. `max(1,int(...))` silent breach | Phase 5 (sizing) | Decide policy (skip or warn); log effective risk per run |
| 10. Pyramid double-add | Phase 5 (pyramiding) | State-machine test with gap-up fixture |
| 11. Trailing stop close-only | Phase 4 (exit) | Intraday high/low test fixture |
| 12. Contract math off-by-multiplier | Phase 5 (sizing + P&L) | `INSTRUMENTS` constants dict; worked-example unit tests |
| 13. state.json crash mid-write | Phase 7 (persistence) | Atomic write via tempfile + os.replace; kill-9 test |
| 14. Email deliverability | Phase 6 (email) | First `--test` email confirmed in inbox; Resend dashboard check |
| 15. Meta-refresh hammering | Phase 8 (dashboard) | Remove or set to 3600s |
| 16. Chart.js CDN | Phase 8 (dashboard) | Pinned version + SRI; optionally vendored |
| 17. Replit Autoscale loses writes | Phase 9 (deployment) | GHA is primary; Replit path requires Always On |
| 18. GHA state.json race / perms | Phase 9 (deployment) | `contents: write` + `concurrency:` + post-push verify |
| 19. `--test` mutates state | Phase 10 (CLI/tests) | Assert state.json unchanged after `--test` |
| 20. Live-API tests | Phase 3 + Phase 10 | Fixture CSVs + golden files committed; CI offline |

---

## Sources

- **SPEC.md** and **PROJECT.md** — primary source for required behaviour and constraints.
- **MEMORY.md** — user's prior bug patterns, Resend config status, Perth UTC+8 timezone note, hosting setup.
- **yfinance issue tracker** (github.com/ranaroussi/yfinance/issues) — recurring "empty download" and 429 rate-limit reports through 2024–2026; `auto_adjust` default change noted in release notes.
- **Wilder, J. Welles — "New Concepts in Technical Trading Systems" (1978)** — canonical definition of ATR and ADX smoothing, used to specify `alpha = 1/period`.
- **Resend documentation** (resend.com/docs) — domain verification, inline CSS requirement, API response semantics.
- **GitHub Actions documentation** — workflow permissions (`contents: write`), `concurrency` block, cron drift behaviour.
- **Replit documentation** — Always On requirement for long-running processes; Autoscale is stateless.
- **Python stdlib** — `tempfile.mkstemp` + `os.replace` as the atomic-write pattern on POSIX.
- **Global CLAUDE.md patterns** — atomic state file writes, secrets handling, fire-and-forget async considered harmful (parallels the email path), HTML escaping on dynamic data.
- **Personal experience** — patterns 6, 7, 9, 10, 11, 19 are the ones that bite every backtested-to-live trading system I've seen ported; they're logic failures that tests catch but demos don't.

---
*Pitfalls research for: Python mechanical trading signal app (SPI 200 + AUD/USD, daily close, signal-only)*
*Researched: 2026-04-20*
