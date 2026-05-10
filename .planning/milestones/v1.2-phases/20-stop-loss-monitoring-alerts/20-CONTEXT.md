---
phase: 20
phase_name: Stop-loss monitoring & alerts
milestone: v1.2
created: 2026-04-30
status: locked
requirements: [ALERT-01, ALERT-02, ALERT-03, ALERT-04]
source: ROADMAP.md v1.2 Phase 20 Success Criteria + REQUIREMENTS.md ALERT namespace + operator discuss-phase 2026-04-30
---

# Phase 20 — Stop-Loss Monitoring & Alerts (CONTEXT)

## Goal

On every daily run (08:00 AWST scheduler tick), evaluate each open paper trade's stop. Detect three states per trade — CLEAR, APPROACHING, HIT — using today's price action and the live ATR(14) the signal engine just computed. On a real state transition, send a single batched `[!stop]` email summarising every transitioning trade. Render the current alert state next to each open trade on the dashboard with a colored badge. Deduplicate via `paper_trades[].last_alert_state` so the same APPROACHING trade isn't emailed every day.

## Scope

**In:**
- New pure-math module `alert_engine.py` — `compute_alert_state(side, today_low, today_high, today_close, stop_price, atr) -> str` returns `'CLEAR'`/`'APPROACHING'`/`'HIT'`
- Schema bump 6→7 with `_migrate_v6_to_v7` adding `last_alert_state: None` to every existing `paper_trades[]` row
- Daily-run integration: `main.py` invokes `_evaluate_paper_trade_alerts(state)` after signal computation, builds a transitions list, fires one batched email
- Notifier extension: `notifier.send_stop_alert_email(transitions, dashboard_url) -> bool` (never-crash; logs on failure)
- Dashboard "Alert" column in the existing Phase 19 open trades table — colored badge per row
- Web-layer wiring: PATCH `/paper-trade/<id>` resets `last_alert_state` to None on every successful edit
- One batched email per daily run (across all transitioning trades)

**Out (deferred to v1.3+):**
- Per-trade snooze / mute (operator silencing a noisy alert without closing the trade)
- Multi-channel notifications (SMS, push, Slack)
- Per-instrument or per-side alert preferences
- Alert log / audit trail (history of every alert ever sent — currently only the last state is persisted)
- Re-send reminder for stale HIT trades (rejected — see D-07)

**Out (different phases):**
- Live-fetched price between daily runs (Phase 23+ if at all)
- Phone push alerts (out of v1.x scope; signal-only product)
- Position alerts on the existing `state.positions[]` array (those are signal-engine-driven; Phase 20 is paper-trade-only per REQ-01)

## Locked decisions

### D-01 — Email batching strategy

**One batched email per daily run.** All trades that transitioned state in a given daily evaluation are grouped into a single `[!stop]` email. The body holds an HTML table with one row per transitioning trade.

Rejected: one email per transition (inbox noise; harder to triage a busy week); split-by-severity (HIT individual + APPROACHING batched — too many code paths for marginal UX gain on a single-operator product).

### D-02 — Email recipient and body format

**Recipient:** `SIGNALS_EMAIL_TO` (the same inbox as the daily signal email). One channel, one place to look. Reuses the env var Phase 6 already set; no new config.

**Subject:** `[!stop] N transition(s) in today's paper trades` where `N` is the count of rows in the email body. If `N == 1`, subject becomes `[!stop] <INSTRUMENT> <SIDE> <STATE> — <id>` for grep-friendliness.

**Body (HTML):**

```html
<h2>Stop-loss alert (N transition(s))</h2>
<table>
  <thead><tr><th>Trade</th><th>Side</th><th>Entry</th><th>Stop</th><th>Today's close</th><th>Distance</th><th>State</th></tr></thead>
  <tbody>
    <tr><td>SPI200-20260430-001</td><td>LONG</td><td>$4250.00</td><td>$4200.00</td><td>$4205.50</td><td>0.31 ATR (within trigger)</td><td>HIT</td></tr>
    <tr>...</tr>
  </tbody>
</table>
<p>Dashboard: <a href="https://signals.mwiriadi.me/">signals.mwiriadi.me</a></p>
```

**Plain-text fallback:** identical structure rendered as a fixed-width text table (matches the v1.0 Resend plain-text convention from Phase 6).

**Distance format:** `<float>.2f ATR (within trigger | beyond stop)` — `within trigger` for APPROACHING, `beyond stop` for HIT. Distance always positive.

Rejected: short paragraph body (less scannable when 3+ trades transition); OPERATOR_RECOVERY_EMAIL recipient (counter to single-channel principle from Phase 6).

### D-03 — Dashboard "Alert" column placement

**New "Alert" column in the existing Phase 19 open trades table.** Render via a new helper `_render_alert_badge(state: str | None) -> str` returning a colored `<span class="alert-badge alert-{lower}">CLEAR | APPROACHING | HIT | —</span>`. Color contract:

- `CLEAR` — green (`.alert-clear`)
- `APPROACHING` — amber (`.alert-approaching`)
- `HIT` — red (`.alert-hit`)
- `None` (never evaluated yet) or no `stop_price` — neutral grey (`.alert-none`) with text `—` and tooltip `no stop set` or `awaiting next daily run`

Mobile layout: the column collapses to a tiny pill below the trade ID cell at viewport widths < 640px (CSS `@media` rule in the existing inline style block).

Rejected: separate Alerts pane above the open trades table (duplicates info, vertical scroll cost on mobile); inline badge inside an existing cell (poor scannability + colorblind UX).

### D-04 — Reset on edit / close

**On edit:** any successful PATCH `/paper-trade/<id>` (Phase 19 D-12) resets `last_alert_state = None` regardless of which field changed. Rationale: the alert state was computed against the pre-edit row; any change (price, stop, contracts, side) invalidates the prior eval. Forcing a fresh eval next daily run is safer than per-field reasoning. Toast UX surfaces the reset: `Trade edited; alert state will refresh after the next 08:00 AWST run.`

**On close:** closed rows are excluded from alert evaluation per REQ-01 (`status=open` filter). The `last_alert_state` field stays at whatever value it held at close time — historically interesting in a future audit phase, no email risk.

Rejected: edit-conditional reset (only reset if `stop_price` changed) — adds branching for marginal benefit; never-reset (loses alerts when operator tightens a stop).

### D-05 — Initial state for newly-entered trade

**`last_alert_state = None` at row write time.** First daily-run eval treats `None → X` as a real transition:

- `None → CLEAR` — no email (no actionable change)
- `None → APPROACHING` — email (operator entered with stop already inside trigger range — they want to know)
- `None → HIT` — email (operator entered a position the market has already moved against)

This is symmetric with the edit-reset behavior (D-04) and the migration default (D-08).

Rejected: default `'CLEAR'` (loses the `None → CLEAR` no-email distinction; would require a separate "first run after entry" flag); compute initial state at entry time (couples the route handler to the indicator-scalar lookup, complicates the validator path).

### D-06 — Email send failure dedup behavior

**Leave `last_alert_state` unchanged on send failure.** If `notifier.send_stop_alert_email` returns `False` (Resend API error, network blip, quota exceeded), the daily-run alert evaluator does NOT update `last_alert_state` for the affected trades. Next daily run re-detects the transition and retries.

Failure is logged with `[Alert] WARN stop alert email failed; will retry next run` per the existing `[Tag] level message` log convention from CLAUDE.md.

Rejected: update-anyway (loses the alert entirely if Resend has an outage); split-by-severity (over-engineered for a single-operator product).

### D-07 — HIT terminal state policy

**Continue evaluating, no resend.** Each daily run re-evaluates every open trade including those in `HIT` state. State stays `HIT` (close still beyond stop), no transition, no email. Dashboard badge stays red.

If close moves back inside the CLEAR range somehow (operator hasn't closed and price recovered), `HIT → CLEAR` IS a transition and emails (operator wants to know the trade has recovered). This is the only realistic non-edit way to leave HIT.

Operator can manually unwind the alert by editing `stop_price` (D-04 resets `last_alert_state` to None and re-evals fresh).

Rejected: stop-evaluating after HIT (extra state machinery, dashboard badge frozen); reminder-resend after N days (counter to dedup principle).

### D-08 — Schema bump 6 → 7

`STATE_SCHEMA_VERSION` bumps `6` (Phase 19) → `7`. New migration `_migrate_v6_to_v7` registered in `MIGRATIONS[7]` (between key 6 and the close of the dispatch table). Body:

```python
def _migrate_v6_to_v7(s: dict) -> dict:
  '''Phase 20 (v1.2): introduce last_alert_state field on paper_trades rows.

  Existing rows on first v1.2.x post-deploy load have no last_alert_state.
  Stamp None — the next daily-run alert evaluator treats None as a fresh
  state and emails on first transition (D-05).

  Idempotent: never overwrite an existing populated last_alert_state value.
  Defensive: only touches dict-shaped rows (skips any malformed entries).
  D-15 silent migration (matches Phase 22 D-15 + Phase 17/19 precedent):
  no append_warning, no log line.
  '''
  for row in s.get('paper_trades', []):
    if isinstance(row, dict) and 'last_alert_state' not in row:
      row['last_alert_state'] = None
  return s
```

Test pattern mirrors Phase 17/19 §D-08 (idempotent, preserves-other-fields, full-walk v0→v7).

### D-09 — Extended `paper_trades[]` row shape

New field `last_alert_state` added. Updated full key set:

| Field | Type | Phase | Notes |
|-------|------|-------|-------|
| `id` | str | 19 | composite per Phase 19 D-01 |
| `instrument` | str | 19 | `'SPI200'` or `'AUDUSD'` |
| `side` | str | 19 | `'LONG'` or `'SHORT'` |
| `entry_dt` | str | 19 | ISO8601 AWST |
| `entry_price` | float | 19 | > 0 |
| `contracts` | int / float | 19 | >0 |
| `stop_price` | float \| None | 19 | optional |
| `entry_cost_aud` | float | 19 | half of round-trip per Phase 19 D-02 |
| `status` | str | 19 | `'open'` or `'closed'` |
| `exit_dt` | str \| None | 19 | populated on close |
| `exit_price` | float \| None | 19 | populated on close |
| `realised_pnl` | float \| None | 19 | populated on close |
| `strategy_version` | str | 22 | from `system_params.STRATEGY_VERSION` at write/edit |
| `last_alert_state` | str \| None | **20** | `'CLEAR'` / `'APPROACHING'` / `'HIT'` / `None` |

Validator extended: `_validate_open_form` (Phase 19) now also enforces strict-key set including `last_alert_state` per the open-row strict-keys test.

### D-10 — `alert_engine.py` (new pure-math module)

Two pure functions, no I/O, no env vars:

```python
def compute_alert_state(
  side: str,                  # 'LONG' or 'SHORT'
  today_low: float,
  today_high: float,
  today_close: float,
  stop_price: float,
  atr: float,
) -> str:
  '''Returns 'HIT', 'APPROACHING', or 'CLEAR'.

  HIT (precedence — REQ-01 ordering):
    LONG: today_low <= stop_price
    SHORT: today_high >= stop_price

  APPROACHING:
    abs(today_close - stop_price) <= 0.5 * atr

  CLEAR otherwise.

  NaN handling: any NaN input (atr=NaN, prices=NaN) returns 'CLEAR' as
  the safe default (no email fires; defensive — matches Phase 1 NaN
  policy from project LEARNINGS).
  '''


def compute_atr_distance(today_close: float, stop_price: float, atr: float) -> float:
  '''Returns abs(today_close - stop_price) / atr.

  Used for email body distance text. Returns NaN if atr <= 0 or NaN
  (no division by zero; render path treats NaN as 'distance unknown').
  '''
```

Forbidden imports for `alert_engine.py`: same list as `pnl_engine.py` / `sizing_engine.py` / `signal_engine.py` (`FORBIDDEN_MODULES_STDLIB_ONLY` in `tests/test_signal_engine.py:556`). Allowed: `math`, `typing`, `system_params` (none of these introduce I/O).

### D-11 — Hex-boundary preservation

`dashboard.py` adds `from alert_engine import compute_alert_state` only — `alert_engine` is NOT in `FORBIDDEN_MODULES_DASHBOARD` (mirrors Phase 19's `pnl_engine` precedent). Plan extends `FORBIDDEN_MODULES_STDLIB_ONLY` AST guard to walk `alert_engine.py`.

Render path (`_render_alert_badge`) reads `last_alert_state` directly off the `paper_trades` row dict — no live computation in render. The daily-run path is the only computation site (state is persisted per row).

`main.py` already imports `system_params`, `state_manager`, `notifier`, `signal_engine` — adding `alert_engine` is consistent with its adapter / orchestrator role.

`notifier.py` extension: new function `send_stop_alert_email(transitions, dashboard_url)` lives alongside the existing `send_signal_email`. Same Resend HTTPS shape, same never-crash posture, same env-var conventions.

`web/routes/paper_trades.py` PATCH handler is the only web-layer touch — sets `last_alert_state = None` inside the existing `mutate_state` closure on every successful edit.

### D-12 — Daily-run integration

New function `_evaluate_paper_trade_alerts(state: dict, dashboard_url: str) -> dict` lives in `main.py` near the existing signal-row writer. Signature (orchestrator-level adapter; not a pure-math fn):

```python
def _evaluate_paper_trade_alerts(state: dict, dashboard_url: str) -> dict:
  '''Phase 20 — evaluate alert state for every open paper trade.

  For each row in state['paper_trades'] with status='open' and stop_price is not None:
    - Read instrument's atr + today_low/high/close from state['signals'][<inst>]
    - Compute new alert state via alert_engine.compute_alert_state
    - Compare to row['last_alert_state']
    - If transition (CLEAR -> APPROACHING, * -> HIT, HIT -> CLEAR), append to
      transitions list with full email body data
    - Always update row['last_alert_state'] to the new state (ALSO updates on no-transition
      from None -> CLEAR to record the eval; D-05)

  After the loop, if transitions is non-empty:
    - Call notifier.send_stop_alert_email(transitions, dashboard_url)
    - On success (returns True): persist updated last_alert_state values via mutate_state
    - On failure (returns False): rollback last_alert_state for transitioning trades only
      to leave them eligible for retry next run (D-06). Non-transitioning trades' states
      ARE persisted (None -> CLEAR no-op writes are idempotent and safe).

  Returns {'transitions': [...], 'emailed': bool}.
  '''
```

Ordering in `_apply_daily_run`:
1. Fetch OHLCV + compute indicators (existing)
2. Persist signal rows + indicator_scalars (existing — Phase 17 ohlc_window + scalars)
3. **NEW: Evaluate paper-trade alerts** (this function)
4. Render dashboard.html (existing)
5. Send daily signal email (existing)
6. atomic save state (existing)

Step 3 sits between persistence and rendering so the dashboard render reads the freshly-updated `last_alert_state` values.

### D-13 — Notifier extension

`notifier.py` gets one new function:

```python
def send_stop_alert_email(transitions: list[dict], dashboard_url: str) -> bool:
  '''Phase 20 D-02 — send batched stop-alert email via Resend.

  transitions: list of dicts with keys (id, instrument, side, entry_price,
    stop_price, today_close, atr_distance, new_state).

  Returns True on Resend 200, False on failure (network, API error,
  quota). NEVER crashes the caller (Phase 6 invariant).

  Subject: '[!stop] {N} transition(s) in today\\'s paper trades' (or per-trade
    when N == 1).

  Body: HTML table per D-02 + identical plain-text fallback.
  '''
```

XSS defense: every `transitions[i]` field is `html.escape(value, quote=True)` before HTML body interpolation. ID values are validated by Phase 19 D-01 regex-shape, but defense-in-depth.

### D-14 — Dashboard render

`_render_paper_trades_open` (Phase 19) gains an "Alert" column. Helper `_render_alert_badge(state: str | None, has_stop: bool) -> str` returns:

```python
def _render_alert_badge(state: str | None, has_stop: bool) -> str:
  '''Phase 20 D-03 — render colored alert badge.'''
  if not has_stop:
    return '<span class="alert-badge alert-none" title="no stop set">—</span>'
  if state is None:
    return '<span class="alert-badge alert-none" title="awaiting next daily run">—</span>'
  return f'<span class="alert-badge alert-{state.lower()}">{html.escape(state)}</span>'
```

Inline CSS additions:
- `.alert-badge { padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 0.85em; }`
- `.alert-clear { background: #d4edda; color: #155724; }`
- `.alert-approaching { background: #fff3cd; color: #856404; }`
- `.alert-hit { background: #f8d7da; color: #721c24; }`
- `.alert-none { background: #e9ecef; color: #6c757d; }`
- `@media (max-width: 640px) { .alert-badge { display: block; margin-top: 4px; } }`

### D-15 — Edit-reset wiring

`web/routes/paper_trades.py` PATCH handler (Phase 19 D-12) extends its mutate_state closure to set `row['last_alert_state'] = None` after applying the validated edits. Test in `tests/test_web_paper_trades.py::TestEditPaperTrade` asserts the field is reset on every successful edit (parametrize: edit stop_price, edit entry_price, edit contracts, edit entry_dt — every variant resets).

### D-16 — No new env vars

`SIGNALS_EMAIL_TO`, `RESEND_API_KEY`, `SIGNALS_EMAIL_FROM` are already set (Phase 6). No new config.

`DASHBOARD_URL` is already used by the daily signal email body (Phase 17 trace footer). Reuse — same source.

## Files to modify

- `system_params.py` — bump `STATE_SCHEMA_VERSION` 6 → 7
- `state_manager.py` — add `_migrate_v6_to_v7` + register in `MIGRATIONS[7]`
- **NEW:** `alert_engine.py` — pure-math `compute_alert_state` + `compute_atr_distance`
- `notifier.py` — add `send_stop_alert_email(transitions, dashboard_url) -> bool`
- `main.py` — add `_evaluate_paper_trade_alerts(state, dashboard_url) -> dict`; call inside `_apply_daily_run` after step 2 (signal-row persistence) and before step 4 (dashboard render)
- `dashboard.py` — extend `_render_paper_trades_open` with the new Alert column; add `_render_alert_badge` helper; add inline CSS for `.alert-badge` colors + mobile breakpoint
- `web/routes/paper_trades.py` — PATCH handler closure resets `last_alert_state = None`
- `tests/test_state_manager.py` — extend with `TestMigrateV6ToV7` (mirror Phase 19 idempotent / preserves-other / full-walk pattern)
- `tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent` — extend the AST walker to walk `alert_engine.py` against `FORBIDDEN_MODULES_STDLIB_ONLY`
- **NEW:** `tests/test_alert_engine.py` — `TestComputeAlertState` (HIT precedence, APPROACHING threshold, CLEAR default, LONG/SHORT × today_low/high asymmetry, NaN-safe) + `TestComputeAtrDistance` (correct distance, NaN on zero/NaN ATR)
- **NEW:** `tests/test_notifier_stop_alert.py` — covers `send_stop_alert_email` happy path (Resend 200), failure path (Resend 5xx → False, no crash), batched body shape with N=1 / N=3 / N=0 (no email if N=0), HTML body XSS defense
- **NEW:** `tests/test_main_alerts.py` — covers `_evaluate_paper_trade_alerts` integration: state-transition detection, dedup (no email when no transition), edit-reset interaction, send-failure rollback, ordering inside `_apply_daily_run`
- `tests/test_dashboard.py` — extend `TestRenderPaperTrades` with `TestRenderAlertBadge` (every state × has_stop variant; CSS class assertions; mobile breakpoint substring)
- `tests/test_web_paper_trades.py` — extend `TestEditPaperTrade` with `test_edit_resets_last_alert_state` (parametrized over field edits)
- `tests/fixtures/state_v7_with_alerts.json` — NEW fixture with 4 paper trades covering each state × instrument

## Out of scope (don't modify)

- `signal_engine.py` — no change (alert engine is downstream of signal compute)
- `sizing_engine.py` — no change (alerts are paper-trade-only; positions array unaffected)
- `pnl_engine.py` — no change
- `web/middleware/` — no change (existing cookie-session auth covers the PATCH handler)
- `data_fetcher.py` — no change

## Risk register

| Risk | Mitigation |
|------|-----------|
| Email-send failure leaves operator silently un-alerted forever | D-06 explicit retry-next-run; never updates `last_alert_state` on failure. Test covers this rollback path. Logged via `[Alert] WARN ...`. |
| Resend quota exceeded → repeated retries | Worst case: one extra send attempt per daily run = 1 extra send/day. Resend free tier is 3,000/month = 100/day; well under. |
| Stale `state.signals[<inst>].indicator_scalars` causes wrong APPROACHING calculation | The alert evaluator runs AFTER the signal-row persistence step in `_apply_daily_run` (D-12 ordering). Always reads fresh ATR. Test in `tests/test_main_alerts.py` covers ordering. |
| Race between PATCH edit and daily-run alert eval | `mutate_state` lock kernel handles. Daily-run alert eval reads-eval-writes inside one closure (atomic). |
| Operator edits stop while alert email is mid-send | Send is synchronous within the daily-run closure → no in-flight state. PATCH after the closure releases reads the post-eval state with last_alert_state already updated; resets to None per D-15 — next run re-evaluates. |
| HTML email XSS via paper_trade fields | `html.escape(value, quote=True)` on every interpolated field in `notifier.send_stop_alert_email` body. Test covers an entry with HTML-special chars. |
| Daily-run timing: trade entered AT 08:00:00 AWST same as scheduler tick | Phase 7 scheduler runs at 08:00 server-tz AWST. Trade entry is operator-driven and asynchronous; the lock kernel serialises. If entry lands before alert eval, alert eval includes the new trade with `last_alert_state=None`. If entry lands after, next-day run picks it up. Both paths are correct. |
| ATR missing on a brand-new instrument signal row (`indicator_scalars: {}` after migration) | `compute_alert_state` returns `'CLEAR'` for any NaN input (D-10). Logs `[Alert] WARN no ATR for <inst>; treating as CLEAR`. No false positive. |
| Email batches grow large (many trades transition same day) | HTML body scales linearly. Resend supports 5MB body limit; even 100 transitions × 200 bytes = 20KB. No risk. |
| Plain-text fallback drift from HTML body | Both rendered from same `transitions` data via parallel render helpers `_render_alert_email_html` and `_render_alert_email_text`. Test asserts both contain every transition's id + state. |

## Verification (what proves the phase shipped)

1. `python3 -c "import system_params; print(system_params.STATE_SCHEMA_VERSION)"` prints `7`.
2. Loading a v6 state.json walks forward to v7 and stamps `last_alert_state: None` on every existing paper_trades row.
3. Open a paper trade on SPI200 with stop_price set to a level inside 0.5×ATR of yesterday's close. After daily run, row's `last_alert_state == 'APPROACHING'`. AND `[!stop]` email arrives in `SIGNALS_EMAIL_TO` inbox with the trade id + state.
4. Same trade re-evaluated next daily run: still APPROACHING, NO new email (dedup).
5. Operator edits the stop_price (PATCH route): `last_alert_state` immediately resets to None.
6. Trade with stop on the wrong side of today's price (LONG with today_low <= stop): `last_alert_state == 'HIT'`. Email body distance text reads "0.XX ATR (beyond stop)".
7. Trade with no stop_price: `last_alert_state` stays None forever. Dashboard renders `—` with grey badge.
8. Resend API failure (mock 503): `_evaluate_paper_trade_alerts` returns `{'transitions': [...], 'emailed': False}`. The transitioning trades retain their *prior* `last_alert_state` (rollback). Next daily run re-emits.
9. Three trades transition in one daily run: 1 email, body has 3 rows in the table, all 3 trades' `last_alert_state` updated.
10. Dashboard HTML at `/` contains `.alert-badge` CSS substring AND every open-trade row contains an `<span class="alert-badge alert-...">` element with the correct color class.
11. Hex-boundary: `grep -E "^import alert_engine|^from alert_engine" dashboard.py` shows the import; AST guard for `alert_engine.py` passes (only `math`, `typing`, `system_params` allowed).
12. `pytest tests/test_alert_engine.py tests/test_notifier_stop_alert.py tests/test_main_alerts.py tests/test_state_manager.py::TestMigrateV6ToV7 tests/test_dashboard.py::TestRenderAlertBadge tests/test_web_paper_trades.py::TestEditPaperTrade::test_edit_resets_last_alert_state tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent` — all pass.
13. ATR-NaN safety: brand-new instrument with `indicator_scalars: {}` in state, paper trade has stop_price set. `compute_alert_state` returns `'CLEAR'`. Log line `[Alert] WARN no ATR for <inst>; treating as CLEAR` emitted. No email, no crash.

## Deferred ideas (out of v1.2 scope)

- **Per-trade snooze / mute** — operator silences a noisy trade without closing it. Adds a `alert_snoozed_until` timestamp field. v1.3+.
- **Multi-channel delivery** — SMS, push, Slack, Telegram. Out of v1.x scope; signal-only product per CLAUDE.md.
- **Alert history audit log** — every email ever sent persisted as a `state.alert_log[]` array for backtesting alert latency. v1.3+.
- **Stale-HIT reminder** — re-send HIT alert every N days as reminder if operator doesn't close. Rejected per D-07.
- **Per-instrument alert preferences** — different ATR multiplier (e.g. 0.7× for AUDUSD vs 0.5× for SPI200), different recipients per instrument. v1.3+.
- **Live intraday HIT detection** — fetch intraday data, fire alert mid-day. Counter to daily-cadence-only product invariant from CLAUDE.md.

## Canonical refs

- `.planning/ROADMAP.md` §Phase 20 (success criteria 1-7)
- `.planning/REQUIREMENTS.md` §ALERT-01..04
- `.planning/PROJECT.md` (operator + stack context)
- `SPEC.md` §v1.2+ Long-Term Roadmap
- `CLAUDE.md` — log prefix `[Alert]` (new tag), email never-crash from §Architecture, daily-cadence invariant
- `.planning/phases/19-paper-trade-ledger/19-CONTEXT.md` (paper_trades row shape, mutate_state lock pattern, Phase 19 D-15 atomicity)
- `.planning/phases/22-strategy-versioning-audit-trail/22-CONTEXT.md` D-04, D-05, D-09, D-10 (schema bump pattern, idempotent migration, hex-boundary precedent)
- `.planning/phases/17-per-signal-calculation-transparency/17-CONTEXT.md` D-08 / D-09 (state shape + scalars persistence — alert engine reads from indicator_scalars)
- `.planning/phases/14-trade-journal-mutation-endpoints/14-CONTEXT.md` (mutate_state lock kernel)
- `.planning/phases/6-resend-email-integration/...-CONTEXT.md` (existing notifier.py never-crash invariant — REUSE pattern)
- `system_params.py` lines 19, 121 (constants block, `STATE_SCHEMA_VERSION` site)
- `state_manager.py` `_migrate_v5_to_v6` + `MIGRATIONS` dispatch (Phase 19 precedent)
- `state_manager.py` `mutate_state` (Phase 14 D-14 lock kernel)
- `main.py` `_apply_daily_run` (existing daily orchestrator)
- `notifier.py` `send_signal_email` (existing Resend wrapper — mirror for new fn)
- `web/routes/paper_trades.py` PATCH handler closure (Phase 19 D-12 site)
- `dashboard.py` `_render_paper_trades_open` (Phase 19 D-14 — extend with Alert column)
- `tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent` (forbidden-imports AST guard)
- `tests/test_state_manager.py::TestMigrateV5ToV6` (Phase 19 — mirror exactly for V6→V7)
- `~/.claude/LEARNINGS.md` 2026-04-29 entry on kwarg-default capture trap (apply to STRATEGY_VERSION access in alert email body, if any)
- `.claude/LEARNINGS.md` 2026-04-27 entry on hex-boundary primitives-only contract
