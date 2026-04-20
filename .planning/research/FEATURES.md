# Feature Research

**Domain:** Mechanical trading signal apps (personal/operator tools — daily signals, email notification, lightweight dashboard)
**Researched:** 2026-04-20
**Confidence:** HIGH (scope is narrow, SPEC.md is already thorough, and the target user is a single operator with a defined backtested system)

## Feature Landscape

### Table Stakes (Operator Expects These)

Features the operator will assume exist. Missing these = the operator stops trusting the output, ignores the email, or can't reproduce a trade decision.

| Feature | Why Expected | Complexity | In SPEC? | Notes |
|---------|--------------|------------|----------|-------|
| Accurate daily signal computation (ATR/ADX/Mom, 2-of-3 gate) | Core product — wrong signals = worthless app | MEDIUM | Yes | SPEC.md lines 15-41. Wilder smoothing is the main correctness trap; pin indicator formulas to backtest reference values. |
| Yahoo Finance data fetch with retry | yfinance is flaky; single-fetch failure cannot kill the daily run | SMALL | Yes | SPEC 19, 440. 3x retry w/ 10s delay. Must detect stale data (last bar not = yesterday's close). |
| Persistent state (`state.json`) across runs | Account, open positions, trade log, equity history all must survive restarts or the app is useless | MEDIUM | Yes | SPEC 119-163. Schema is fixed. Atomic writes (temp+rename), backup on corruption, schema version field is a must-add. |
| Deterministic signal output for a given date + state | Operator must be able to reproduce yesterday's decision to audit it | MEDIUM | Yes | Listed in Constraints. Requires no RNG, no clock-dependence inside compute, and snapshotting the OHLCV row used. |
| Daily email via Resend (HTML, mobile-safe, inline CSS) | Daily email IS the product — it's how the operator gets the signal | MEDIUM | Yes | SPEC 174-226. Verified sender already set up. Inline CSS only; test in Gmail iOS, Gmail web, Outlook. |
| Clear ACTION REQUIRED block on signal change | A signal change = a manual trade. If that's buried, the operator misses it | SMALL | Yes | SPEC 393-408. Red border, bold header, explicit CLOSE/OPEN instructions with size + stop. |
| Unchanged-signal "no action" email | If email stops arriving, operator can't tell "no change" from "app broken" — must confirm heartbeat daily | SMALL | Yes | SPEC line 382. Send every weekday regardless of signal change. |
| Position sizing (ATR + vol target) | Sizing is part of the signal — without it, the operator has to compute n_contracts manually and will get it wrong | MEDIUM | Yes | SPEC 44-52. Vol scale clipped [0.3, 2.0]. Must match backtest. |
| Exit rules (reversal, ADX<20, trailing stop) | Entries without exits = open trades never close = fake equity curve | MEDIUM | Yes | SPEC 58-62. Stop checked against high/low of today's candle, not close. |
| Trade history / trade log | Operator needs audit trail, P&L reconciliation vs broker statement, tax records | SMALL | Yes | SPEC 146-157. Append-only list in state.json. Include exit_reason. |
| Equity history & running P&L | Trust — operator needs to see equity curve match expectation | SMALL | Yes | SPEC 159-163. One point per run. |
| Error handling that never crashes silently | Silent failure = operator makes decisions on stale data and loses real money | MEDIUM | Yes | SPEC 438-444. Catch all exceptions, email warning on next run, never exit with unhandled error. |
| Test mode (`--test` flag) | Operator needs to verify the wiring without touching state or sending real-looking emails | SMALL | Yes | SPEC 414-421. `[TEST]` subject prefix, read-only state, prints signal report. |
| Force email (`--force-email`) | When things look wrong, operator needs to trigger a send without waiting for the scheduler | SMALL | Yes | SPEC 432-434. Single flag — runs compute + sends immediately. |
| State reset (`--reset`) | After a big bug, operator needs a clean slate without hand-editing JSON | SMALL | Yes | SPEC 424-428. Backs up existing file before reset (add this — not in SPEC). |
| Structured console logs | Replit/GHA logs are the only visibility when running unattended | SMALL | Yes | SPEC 449-476. Prefix tags, timestamps, ✓/✗ status per step. |
| Scheduled daily run at 08:00 AWST | The whole point is "every weekday morning" — missing the schedule = missing the product | SMALL | Yes | SPEC 64. `schedule.every().day.at("00:00")` UTC. GHA cron `0 0 * * 1-5` is the free path. |
| Subject line that tells the whole story | Operator reads the subject in the notification bar — if it doesn't surface signal + action flag, they'll miss changes | SMALL | Yes | SPEC 359-360. Must include 🔴 emoji on action days, plain 📊 on no-change days. |
| Weekday-only execution | Markets closed on weekends — signals on weekends are meaningless and create duplicate stop alerts | SMALL | Partial | Cron handles this on GHA. In `schedule`-based loop, must check `datetime.weekday() < 5` before running. |
| Dashboard HTML file | Operator wants to look at the equity curve without opening email | SMALL | Yes | SPEC 230-249. Self-contained, Chart.js CDN, auto-refresh. |

### Differentiators (Quality-of-Life / Trust-Building)

Features that are not strictly required but elevate the app from "a script" to "a tool the operator actually trusts for years."

| Feature | Value Proposition | Complexity | In SPEC? | Notes |
|---------|-------------------|------------|----------|-------|
| Pyramiding (add at +1×ATR and +2×ATR) | Core part of the backtested edge — without it, live system under-performs the backtest | MEDIUM | Yes | SPEC 64-67. State has `pyramid_level`. Edge case: don't pyramid on the same bar as entry. |
| Volatility-targeted sizing (vol_scale clip 0.3-2.0) | Keeps risk constant when markets change regime — differentiates from naive "fixed contracts" signal apps | SMALL | Yes | SPEC 50. Already specified. |
| Trailing stop (3×ATR long / 2×ATR short) with peak tracking | Lets winners run but locks in gains. Most amateur signal apps use fixed % stops. | MEDIUM | Yes | SPEC 61. Must update peak_price daily, re-check stop against daily high/low. |
| Dashboard equity curve (Chart.js) | Visual P&L lets the operator eyeball regime changes faster than a table | SMALL | Yes | SPEC 234-238. |
| Signal-change highlighting in email (red border) | Reduces the chance of missing an actionable day | SMALL | Yes | Part of ACTION REQUIRED block. |
| CLI flags for test/reset/force-email | Enables debug-by-flag without editing code | SMALL | Yes | SPEC 414-434. Use `argparse`. |
| Deterministic replay (same state + same OHLCV → same signal) | Operator can audit "why did I go short on 12 April?" by replaying | MEDIUM | Yes | Constraint already. Achieved by pinning indicator formulas + avoiding now()-based logic in compute. |
| Health-check warning if last_run > 2 days old | Catches silent scheduler failure — email includes "⚠ stale run" banner | SMALL | Yes | SPEC line 444. Compare `state.last_run` to today; flag in next email. |
| Stats block in dashboard (total return, Sharpe, max DD, win rate) | One-glance performance vs backtest | SMALL | Yes | SPEC 235. Computed from equity_history + trade_log. |
| Mobile-responsive email with dark theme matching backtests | Operator reads email on phone; consistent aesthetic = less context-switch | SMALL | Yes | SPEC 222-225. Inline CSS, max-width 600px, colour tokens `#22c55e / #ef4444 / #eab308 / #0f1117`. |
| Last-5-trades table in email | Reinforces equity number with recent history — builds trust | SMALL | Yes | SPEC 386. |
| Last-20-trades table in dashboard | Deeper audit trail without opening state.json | SMALL | Yes | SPEC 234. |
| Per-instrument signal card (price, ATR, ADX, Mom breakdown) | Shows the *why* behind the signal, not just the verdict | SMALL | Yes | Console + email already show this. |
| Explicit "signal checked Friday, execute Monday" weekly cadence option | Matches backtested cadence exactly — daily checks give slightly different entries | MEDIUM | Yes (partial) | SPEC 43. Daily version is spec'd as primary; weekly-only mode could be a v1.x switch. |
| State schema versioning | Lets the app migrate `state.json` when the schema changes instead of breaking on load | SMALL | No — ADD | Recommend adding a `schema_version: 1` field to state.json from day one. Cheap insurance. |
| Atomic `state.json` writes (temp + rename) | Prevents half-written state if process killed mid-write | SMALL | No — ADD | Write to `state.json.tmp`, `os.replace()` to target. Standard pattern. |
| State backup on corruption | SPEC says "backup the file, reinitialise from scratch" — differentiator is restoring from backup, not silently reinitialising | SMALL | Partial | SPEC 442. Recommend timestamped backup (e.g. `state.json.bak-2026-04-20`) and a `--restore` flag to pick one. |
| `--dry-run` flag (compute + print, no email, no state write) | Faster than `--test` for local iteration — no network send at all | SMALL | No — ADD | Trivial addition; overlaps partially with `--test`. Useful for CI smoke tests. |
| Slack/Discord webhook as alternative channel | Operator might prefer push over email for action-required days | SMALL | No — DEFER | Resend + email is already the primary. Second channel is v2 territory. |

### Anti-Features (Things This App Deliberately Does NOT Do)

Features that sound like progress but add risk, scope, or regulatory exposure. Document them to resist scope creep.

| Anti-Feature | Why Requested | Why Problematic | Alternative |
|--------------|---------------|-----------------|-------------|
| Live order execution / broker API | "Why make me place the trade manually?" | Turns a signal tool into a trading system with order-management bugs, reconciliation failures, regulatory obligations, and real money at risk. Hard constraint in PROJECT.md. | Keep ACTION REQUIRED block explicit; operator places the trade. |
| Intraday / tick-level signals | More data = better signals, right? | The backtested system is daily-close-only. Intraday signals require different infra (data feed, minute-level state), a different signal rule, and a re-validated edge. Different product. | Daily close only. If intraday ever becomes interesting, it's a new project. |
| Multi-user accounts / auth | "What if my partner wants to see it too?" | Adds login, password reset, session management, multi-tenant data separation — all for one extra reader. Operator can forward the email. | Single-operator, Resend API key and Replit Secrets are the only gate. Share via email forward. |
| Backtesting UI | "Let me tune the params in the browser" | Backtests were already done in a separate notebook. A UI invites re-optimising the strategy on fresh data, which is how most operators overfit. | Backtest code stays external; any re-parameterisation is a deliberate, logged change to the signal module. |
| Chart overlays (MA, Bollinger, candlesticks) in dashboard | "I want to see what the market is doing" | Dashboard is for P&L monitoring, not chart analysis. Adding charting pulls in a full TA chart library and tempts discretion. | Dashboard shows equity curve only. For market charts, open TradingView/Yahoo in a browser. |
| News / sentiment / social signals | "What if Twitter is saying something?" | Mechanical system; adding sentiment breaks determinism and the backtested edge. Invites discretionary overrides. | No news. If the signal says FLAT and the news says otherwise, the system says FLAT. |
| Additional instruments beyond SPI 200 & AUD/USD | "Add oil, gold, S&P" | Each new instrument needs its own contract specs, backtested params, and nexus in the state schema. Out of scope per PROJECT.md. | New instrument = new milestone with fresh backtest + validation. |
| SPA dashboard (React/Vue/Svelte) | "A static HTML file feels dated" | Build step, bundler, npm dependencies — all for a single-page read-only dashboard. Zero user value. | Vanilla HTML + Chart.js CDN, matches existing backtest aesthetic. |
| Database (SQLite / Postgres) | "What if `state.json` gets big?" | `state.json` at 10 years of daily runs + a few thousand trades = <5MB. SQLite adds a dependency and deployment complexity for zero gain. | Single `state.json`; atomic writes + schema versioning are enough. |
| Push notifications (APNs / FCM) | "Email is slow" | Requires app store registration, device tokens, push-service credentials. Operator reads email within minutes anyway. | Resend email + subject-line urgency on action days. Slack webhook is the fallback if needed. |
| SMS alerts | "I want it on my phone" | Twilio costs per message, requires phone-number verification, international AU SMS is expensive. Email push notifications give same latency for free. | Email with mobile-responsive design. |
| "Train on my data" / auto-tuning params | "Maybe the thresholds should adapt" | Walk-forward optimisation is a research problem, not a daily-run feature. Auto-tuning breaks determinism and edge. | Params are code constants. Re-tuning is a deliberate, versioned change. |
| Financial advice disclaimers beyond footer note | "Is this legal?" | Over-disclaiming signals "this is a product" when it's a personal tool. Single-line footer is sufficient. | Footer: "Automated signal — not financial advice." Nothing more. |
| Regulatory / audit trails for external parties | "What if someone asks?" | This is a personal signal tool for one operator; no external consumers = no audit-report feature needed. | State.json + trade_log is the audit trail. Export-to-CSV is a v2 if ever needed. |
| Real-time price ticker in dashboard | "I want to see prices updating live" | Requires a websocket feed, breaks the daily-close-only model, pulls dashboard into a different product category. | Dashboard shows last-close prices with timestamp. Refresh on reload. |
| Multiple simultaneous strategies / signal ensembles | "What if we ran another rule alongside?" | Increases state complexity, email layout complexity, and tempts cherry-picking whichever strategy looks good. | One system, one set of signals, one email. |

## Feature Dependencies

```
Yahoo Finance fetch
    └──feeds──> Indicator computation (ATR/ADX/Mom/RVol)
                    └──feeds──> Signal generation (2-of-3 + ADX gate)
                                    ├──feeds──> Position sizing (vol-target)
                                    │               └──feeds──> Pyramiding logic
                                    └──feeds──> Exit rules (reversal / ADX drop / stop)
                                                    └──feeds──> Trade log append

State load ──> Compute step ──> State save ──> Dashboard render
                                            └──> Email send

CLI flags (--test / --reset / --force-email / --dry-run)
    └──gate──> State writes / email send / scheduler

Schedule loop ──> run_daily_check (= above pipeline)
Error handling ──wraps──> every external call (yfinance, Resend, file I/O)
Health check ──reads──> state.last_run ──injects──> next email
```

### Dependency Notes

- **Indicators require 400-day history:** if yfinance returns <252 bars, Mom12 is NaN and the signal will be FLAT by default. Flag this condition explicitly in the email rather than silently defaulting.
- **Pyramiding requires position sizing + state (`pyramid_level`, `atr_entry`):** pyramid check must compare `(current_price - entry_price) / atr_entry` against thresholds that use the ATR at entry, not today's ATR.
- **Exit rules require trailing stop → requires `peak_price` tracking in state:** peak_price must be updated on every run before the stop check, or the stop is stale.
- **Email send depends on state save (for reproducibility):** if email sends before state saves and state save fails, the next run re-sends the same email. Save state first, then email.
- **Dashboard conflicts with real-time price** (anti-feature): dashboard must always be generated from `state.json` snapshot + today's fetched bar only — no live feed.
- **`--test` conflicts with state writes:** test mode must load state in read-only mode; any accidental `save_state()` call under `--test` is a bug.
- **Weekday-only execution depends on schedule:** cron `* * * * 1-5` handles weekdays on GHA; in-process `schedule` loop needs an explicit `if today.weekday() < 5` gate inside `run_daily_check`, or it will fire on weekends when Always-On reboots the process.

## MVP Definition

### Launch With (v1) — the ship-to-validate set

Everything needed for the operator to actually use it as their morning signal. Matches the 13 SPEC.md Active Requirements.

- [x] Fetch daily OHLCV via yfinance with retry — **why essential:** no data = no signal
- [x] Compute ATR(14), ADX(20), Mom1/3/12, RVol(20) with Wilder smoothing — **why essential:** core signal
- [x] 2-of-3 momentum vote + ADX≥25 gate → LONG/SHORT/FLAT — **why essential:** the product IS the signal
- [x] ATR-based position sizing with vol targeting (risk 1.0% LONG / 0.5% SHORT) — **why essential:** sizing is part of the actionable output
- [x] Contract specs honoured (SPI $25/pt $30 RT; AUD/USD $10k notional $5 RT) — **why essential:** P&L is wrong without this
- [x] Exit rules: signal reversal / ADX<20 / trailing stop (3×/2× ATR) — **why essential:** entries without exits = fake P&L
- [x] Pyramiding to 3 contracts at +1×/+2×ATR — **why essential:** part of the backtested edge
- [x] `state.json` persistence (account, positions, signals, trade_log, equity_history) — **why essential:** next run can't function without it
- [x] Resend HTML email with ACTION REQUIRED block on signal change — **why essential:** email is the delivery channel
- [x] `dashboard.html` with equity curve, positions, last 20 trades, stats — **why essential:** spec'd as part of the daily output
- [x] Daily weekday schedule at 08:00 AWST — **why essential:** "every weekday morning" is the cadence
- [x] `--test`, `--reset`, `--force-email` CLI flags — **why essential:** ops and debugging
- [x] Graceful handling of yfinance / Resend / corrupt-state failures — **why essential:** "never crash silently" is a hard constraint
- [x] Structured console logs — **why essential:** only visibility in Replit/GHA unattended mode
- [x] Footer disclaimer on emails — **why essential:** minimal legal hygiene
- [x] **ADD: `state.json` schema_version field + atomic writes (temp+rename)** — **why essential:** prevents data loss on crash mid-write; v1 cost is ~10 lines
- [x] **ADD: Stale-run banner in email if `last_run` > 2 days old** — **why essential:** SPEC already calls for it; operator's only signal that the scheduler died
- [x] **ADD: Weekday gate inside `run_daily_check` (even when using `schedule`)** — **why essential:** Always-On restarts can land on a weekend and fire duplicate runs

### Add After Validation (v1.x) — post-shipping polish

Add these only after the daily email is landing reliably for ~4 weeks.

- [ ] **Timestamped state backups before each run** — trigger: first time state gets corrupted or a bug causes a bad write
- [ ] **`--restore` flag to pick a backup** — trigger: after the first backup saves an ops headache
- [ ] **`--dry-run` flag (compute + print, no write, no email)** — trigger: when CI smoke tests or local iteration feel slow
- [ ] **Signal history panel in dashboard (last N signals per instrument with dates)** — trigger: first time operator asks "when did I last flip to short?"
- [ ] **Per-instrument ADX/Mom chart in dashboard** — trigger: operator wants to see *why* the signal is where it is without reading the email
- [ ] **Export trade_log to CSV via `--export-trades`** — trigger: tax time
- [ ] **Weekly-cadence mode toggle (Friday-close check, Monday-open execution only)** — trigger: if daily-cadence results diverge noticeably from backtest
- [ ] **Slack webhook as secondary channel for action-required days** — trigger: if an action-day email ever gets missed

### Future Consideration (v2+) — only if the core is validated and stable

- [ ] **More instruments (oil, gold, S&P)** — defer because: each needs a fresh backtest and contract-spec block. New instrument is a milestone.
- [ ] **PostgreSQL/SQLite storage** — defer because: state.json is fine until it genuinely isn't. Likely never.
- [ ] **A proper web dashboard (auth + multi-session)** — defer because: contradicts single-operator design; anti-feature unless the product changes.
- [ ] **Broker integration / live execution** — defer because: explicitly out of scope (hard constraint).
- [ ] **Strategy ensemble / alternative signal rules** — defer because: anti-feature per "one system, one signal" principle.

## Feature Prioritization Matrix

Operator-facing value, not technical complexity.

| Feature | Operator Value | Implementation Cost | Priority |
|---------|----------------|---------------------|----------|
| Accurate signals (indicators + gate) | HIGH | MEDIUM | P1 |
| Daily email with ACTION REQUIRED block | HIGH | MEDIUM | P1 |
| Persistent `state.json` | HIGH | LOW | P1 |
| Retry logic on yfinance failure | HIGH | LOW | P1 |
| Position sizing + pyramiding | HIGH | MEDIUM | P1 |
| Exit rules (reversal / ADX / stop) | HIGH | MEDIUM | P1 |
| Scheduler (weekday 08:00 AWST) | HIGH | LOW | P1 |
| Graceful error handling + warning email | HIGH | LOW | P1 |
| Structured console logs | MEDIUM | LOW | P1 |
| CLI `--test` / `--reset` / `--force-email` | MEDIUM | LOW | P1 |
| Dashboard with equity curve | MEDIUM | LOW | P1 |
| Atomic state writes + schema_version | MEDIUM | LOW | P1 |
| Stale-run warning banner | HIGH | LOW | P1 |
| Weekday gate in schedule loop | HIGH | LOW | P1 |
| Timestamped state backups | MEDIUM | LOW | P2 |
| `--dry-run` flag | LOW | LOW | P2 |
| `--restore` backup picker | MEDIUM | LOW | P2 |
| CSV trade export | LOW | LOW | P2 |
| Slack webhook fallback | LOW | LOW | P2 |
| Weekly-cadence mode switch | LOW | MEDIUM | P2 |
| Per-instrument chart in dashboard | LOW | MEDIUM | P3 |
| Signal history panel | LOW | LOW | P3 |
| More instruments | LOW (big later) | HIGH | P3 |
| SQLite/Postgres migration | NONE | HIGH | never |
| Live execution | NEGATIVE | HIGH | never |

**Priority key:**
- **P1** — must ship in v1; operator can't use the tool without it
- **P2** — ship in v1.x after the core runs reliably for a few weeks
- **P3** — defer to v2; only if there's a concrete trigger
- **never** — explicit anti-features / out-of-scope

## Competitor Feature Analysis

There is no direct competitor — this is a personal operator tool, not a product. But for orientation, here's how the design choices compare to adjacent tools the operator might have seen.

| Feature | TradingView alerts | Commercial signal services (e.g. Trade Ideas) | QuantConnect live paper trading | **This app** |
|---------|---------------------|-------------------------------------------------|----------------------------------|--------------|
| Delivery channel | In-app + email/SMS + webhook | In-app dashboard | Web dashboard | **Daily email + static HTML dashboard** |
| Signal determinism | Depends on Pine script + server time | Proprietary, not reproducible | Reproducible with replay | **Fully deterministic from state + OHLCV** |
| Position sizing | None (alert only) | Some offer % risk sizing | Yes (in algo) | **ATR + vol-target sizing baked in** |
| P&L tracking | None | Paper account | Full equity curve | **State.json + dashboard equity curve** |
| Customisability | High (Pine script) | Low | High (C#/Python) | **Code-owned — anything goes** |
| Cost | ~$15-60/mo | $100-200+/mo | Free tier + paid | **Resend free tier + Replit or GHA free** |
| Scope | General purpose | General purpose | General purpose | **Two instruments, one edge, one operator** |
| Anti-features avoided | — | — | — | **No live exec, no intraday, no auth, no news, no backtest UI** |

The app's entire differentiation is being *narrow on purpose*: one system, two instruments, one operator, daily cadence, signal-only. Every feature decision leans into that.

## Sources

- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/.planning/PROJECT.md` — validated requirements, constraints, and key decisions
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/SPEC.md` — full functional spec (signal rules, email format, CLI flags, error handling)
- Prior backtest work referenced in PROJECT.md (dark aesthetic, Chart.js, colour palette) — establishes dashboard design language
- Global patterns (`~/.claude/CLAUDE.md`) — async/await discipline, atomic file writes, error-never-silent convention

---
*Feature research for: mechanical trading signal apps (personal/operator tooling)*
*Researched: 2026-04-20*
