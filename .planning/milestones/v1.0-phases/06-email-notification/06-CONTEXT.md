# Phase 6 — CONTEXT

**Phase:** 06 — Email Notification
**Created:** 2026-04-22
**Discuss mode:** discuss
**Goal (from ROADMAP.md):** Send a daily Resend email with signal status, positions, P&L, and an ACTION REQUIRED block when any signal changes. Mobile-responsive, inline-CSS, escaped values, graceful degradation when Resend is unavailable. Also wires the Phase 4 `--test` and `--force-email` log-line stubs to real Resend dispatch (CLI-01 `[TEST]`-prefixed email + CLI-03 today's email).

**Requirements covered:** NOTF-01, NOTF-02, NOTF-03, NOTF-04, NOTF-05, NOTF-06, NOTF-07, NOTF-08, NOTF-09 (9 requirements) + Phase 6 completion slices of CLI-01 + CLI-03.
**Out of scope (later phases):**
- NOTF-10 warnings carry-over across runs (Phase 8 Hardening)
- Schedule loop wiring (Phase 7 — default-mode flip)
- ERR-02 Resend failure banner in NEXT email (Phase 8)
- ERR-04 top-level crash-email (Phase 8)
- ERR-05 stale-state banner (Phase 8)

<canonical_refs>

External specs, ADRs, and prior CONTEXT docs that downstream agents must consult:

- **.planning/PROJECT.md** — Palette; `signals@carbonbookkeeping.com.au` verified Resend sender; `requests` pinned (no SDK); "Email sends NEVER crash the workflow" invariant; `python-dotenv` for `.env` locally.
- **.planning/REQUIREMENTS.md** — NOTF-01..09 full text; CLI-01 + CLI-03 split-phase notes; cross-phase coverage map.
- **.planning/ROADMAP.md** — Phase 6 goal + 7 success criteria (note: SC-6 + SC-7 cover the `--force-email` and `--test` dispatch wiring).
- **CLAUDE.md** — `[Email]` log prefix locked; Resend HTTPS only (no SMTP); hex-lite rules.
- **SPEC.md** — Full functional spec (email sections, palette, mobile behavior).
- **.planning/phases/03-state-persistence-with-recovery/03-CONTEXT.md** + SUMMARY — `state_manager.load_state` public API + state schema (`account`, `positions`, `signals` (per-instrument dict per Phase 4 D-08), `trade_log`, `equity_history`, `warnings`, `last_run`).
- **.planning/phases/04-end-to-end-skeleton-fetch-orchestrator-cli/04-CONTEXT.md** — D-08 per-instrument signal shape; D-06 force-email stub (now replaced by real dispatch in this phase); Phase 4 CLI-01 structural read-only contract (must stay intact).
- **.planning/phases/04-end-to-end-skeleton-fetch-orchestrator-cli/04-03-SUMMARY.md** — `run_daily_check(args)` signature + AC-1 reversal ordering; trade_log 12-field shape (`instrument, direction, entry_date, exit_date, entry_price, exit_price, gross_pnl, n_contracts, exit_reason, multiplier, cost_aud, net_pnl`).
- **.planning/phases/05-dashboard/05-CONTEXT.md + UI-SPEC** — Palette + typography + signal-card semantics for visual consistency with email. Email is a separate hex (no dashboard.py imports) but visual language matches.
- **system_params.py** — Palette constants candidate home (see D-02 retrofit below); contract specs; `INITIAL_ACCOUNT`; `Position` TypedDict.
- **state_manager.py** — `load_state` only (Phase 6 is read-only on state).

</canonical_refs>

<prior_decisions>

Decisions from earlier phases that apply to Phase 6 without re-asking:

- **Hex-lite boundaries** (Phases 1-5): `notifier.py` is a new I/O hex (analog of `state_manager.py` / `data_fetcher.py` / `dashboard.py`). MUST NOT import `signal_engine`, `sizing_engine`, `data_fetcher`, `main`, `dashboard`, `notifier-self-cycles`, `numpy`, `pandas`. MAY import `state_manager` (for `load_state` in the convenience CLI path), `system_params` (palette + contract specs), `requests` (Resend HTTPS), stdlib (`html`, `json`, `datetime`, `os`, `time`, `tempfile`, `pathlib`, `logging`), `pytz`.
- **Tech stack** (PROJECT.md): `requests` for Resend HTTPS (no SDK); `python-dotenv` for `.env` local loading (Phase 7 formalises env contract, Phase 6 uses `os.environ.get(...)`). No new pip dependencies.
- **Palette locked** (PROJECT.md + Phase 5 CONTEXT D-04):
  - Background: `#0f1117`
  - Surface: `#161a24` (email content areas on top of bg)
  - Border: `#252a36`
  - Text: `#e5e7eb` (primary), `#cbd5e1` (muted), `#64748b` (dim)
  - LONG: `#22c55e` / SHORT: `#ef4444` / FLAT: `#eab308`
  - Email reuses these verbatim.
- **Resend sender verified** (PROJECT.md): `signals@carbonbookkeeping.com.au` is a verified Resend sender domain; no additional DKIM/SPF setup needed in Phase 6 (operator already configured via Carbon Bookkeeping).
- **Style** (CLAUDE.md): 2-space indent, single quotes, snake_case, UPPER_SNAKE constants.
- **Log prefixes** (CLAUDE.md): `[Email]` is locked.
- **Timezone** (CLAUDE.md / PROJECT.md / Phase 5 D-08): `PERTH = pytz.timezone('Australia/Perth'); PERTH.localize(datetime(...))`. NEVER `datetime(..., tzinfo=pytz.timezone(...))` (pytz localize misuse bug, caught in Phase 5 reviews-revision).
- **Phase 4 CLI-01 structural read-only** (locked via operator decision Option A in Phase 5 reviews): `--test` never mutates `state.json`. Phase 6 preserves this — `--test` email dispatch path calls `run_daily_check(args)` which structurally skips `save_state` (existing `if args.test: return 0` early-return), then sends `[TEST]`-prefixed email WITHOUT going through save_state.
- **Never-crash invariant** (CLAUDE.md + Phase 5 D-06 precedent): Email failures NEVER crash the run. Resend 4xx/5xx, missing API key, network timeout — all logged at WARNING and returned as success from the notifier's perspective (rc=0). Phase 8 will add the next-email warning carry-over.
- **html.escape discipline** (Phase 5 D-15): every state-derived text passes through `html.escape(value, quote=True)` at leaf interpolation. Phase 6 inherits the same posture.

</prior_decisions>

<folded_todos>

No pending todos matched Phase 6 scope (CONF-01/02 were folded into Phase 8 earlier; no email-specific backlog items).

</folded_todos>

<decisions>

## Notifier architecture & shared helpers

- **D-01: New module `notifier.py` at repo root. Fully isolated from `dashboard.py`.**
  Public API:
  - `compose_email_subject(state: dict, old_signals: dict[str, int | None], is_test: bool = False) -> str` — pure function producing the Subject line
  - `compose_email_body(state: dict, old_signals: dict[str, int | None], now: datetime) -> str` — pure function producing the HTML body (table-based layout, inline CSS, mobile-responsive per D-09)
  - `send_daily_email(state: dict, old_signals: dict[str, int | None], now: datetime, is_test: bool = False) -> int` — public dispatch; composes subject + body, handles Resend POST, returns 0 on success/graceful-degradation (NEVER raises)
  - `_post_to_resend(api_key, from_addr, to_addr, subject, html_body, timeout_s=30, retries=3, backoff_s=10) -> None` — HTTPS layer; raises `ResendError` after retries exhaust
  Imports: `requests`, `system_params`, `state_manager` (only in convenience CLI block), stdlib (`html`, `json`, `datetime`, `os`, `time`), `pytz`. Forbidden: `signal_engine`, `sizing_engine`, `data_fetcher`, `main`, `dashboard`, `numpy`, `pandas`.
  AST blocklist extension in Wave 0: `FORBIDDEN_MODULES_NOTIFIER = frozenset({'signal_engine', 'sizing_engine', 'data_fetcher', 'main', 'dashboard', 'numpy', 'pandas'})`.

- **D-02: Full local duplication of formatters in `notifier.py`.**
  `notifier.py` ships its own `_fmt_currency_email`, `_fmt_percent_signed_email`, `_fmt_percent_unsigned_email`, `_fmt_pnl_with_colour_email`, `_fmt_em_dash_email`, `_fmt_last_updated_email`, `_fmt_instrument_display_email`. These mirror the dashboard formatters' output semantics but may differ in implementation detail (email requires inline `style="..."` on every colored span — no external CSS class; email line-length is tighter; some email clients strip unrecognised tags). Rationale: each hex owns its concern; prevents dashboard.py from becoming an implicit formatter library; breakage in email rendering cannot propagate to dashboard tests and vice versa.
  **Small retrofit to Phase 5 dashboard:** the palette constants `_COLOR_BG`, `_COLOR_SURFACE`, `_COLOR_BORDER`, `_COLOR_TEXT`, `_COLOR_TEXT_MUTED`, `_COLOR_TEXT_DIM`, `_COLOR_LONG`, `_COLOR_SHORT`, `_COLOR_FLAT` move from `dashboard.py` module-level to `system_params.py` as shared constants. `dashboard.py` imports them from `system_params`; `notifier.py` imports them from `system_params`. Palette becomes the one shared thing; everything else stays in the owning hex.

- **D-03: Waves: 0 scaffold → 1 render+format → 2 dispatch+integration (PHASE GATE).**
  Mirror Phase 5 exactly:
  - **Wave 0 (06-01):** `notifier.py` stub with all public/private helpers raising NotImplementedError; AST blocklist + 2-space indent guard extension; `tests/test_notifier.py` class skeletons (TestComposeSubject, TestComposeBody, TestFormatters, TestSendDispatch, TestResendPost, TestDispatchIntegration); fixtures `tests/fixtures/notifier/sample_state_with_change.json` + `sample_state_no_change.json` + `empty_state.json`; palette retrofit to system_params.
  - **Wave 1 (06-02):** Fill `compose_email_subject`, `compose_email_body`, all formatters, signal-change detection helper. Populate TestComposeSubject, TestComposeBody, TestFormatters. No HTTP dispatch yet.
  - **Wave 2 (06-03) PHASE GATE:** Fill `_post_to_resend` + `send_daily_email` (retry loop + RESEND_API_KEY fallback + last_email.html write); main.py dispatch wiring for `--force-email` and `--test`; convenience CLI entrypoint; golden-HTML snapshot (same pattern as Phase 5). Populate TestSendDispatch, TestResendPost, TestDispatchIntegration.

## Subject + signal-change detection

- **D-04: Subject template: `{emoji} {YYYY-MM-DD} — SPI200 {SIG}, AUDUSD {SIG} — Equity ${X,XXX}`.**
  Examples:
  - Signal-change day: `🔴 2026-04-22 — SPI200 LONG, AUDUSD FLAT — Equity $101,234`
  - Unchanged day: `📊 2026-04-22 — SPI200 LONG, AUDUSD LONG — Equity $101,234`
  - `--test` runs: `[TEST] 🔴 2026-04-22 — SPI200 LONG, AUDUSD FLAT — Equity $101,234` (TEST prefix BEFORE emoji).
  - Date is `run_date.strftime('%Y-%m-%d')` (AWST calendar day from `_compute_run_date()`).
  - Signal labels are bare words: `LONG` / `SHORT` / `FLAT` (no emoji arrows in signal slots).
  - Equity is `_fmt_currency(account)` rounded to nearest dollar for subject brevity (body shows cents). Use `int(round(account))` then `f'${int(round(account)):,}'`.
  - Emoji choice: `🔴` (U+1F534 RED CIRCLE) when `any_signal_changed` is True; `📊` (U+1F4CA BAR CHART) otherwise.
  - First-run / no-previous-signal case: `📊` prefix (treated as no-change per D-06).

- **D-05: Previous-signal source: captured in `main.py` before `run_daily_check` updates state.**
  In `main.py`, immediately after `state = state_manager.load_state()` and before the per-symbol processing loop, capture:
  ```python
  old_signals = {
    sym: (
      state['signals'].get(state_key, {}).get('signal')
      if isinstance(state['signals'].get(state_key), dict)
      else state['signals'].get(state_key)  # legacy int shape
    )
    for sym, state_key in _SYMBOL_TO_STATE_KEY.items()
  }
  ```
  This dict `{'^AXJO': int_or_none, 'AUDUSD=X': int_or_none}` is passed to `notifier.send_daily_email(state, old_signals=old_signals, now=run_date, is_test=args.test)` on the dispatch path. First-run case: either key missing from `state['signals']` → `old_signals[sym] = None` → treated as "no change" per D-06. No schema change. Backward-compat with both Phase 4 D-08 dict shape AND legacy int shape.

- **D-06: First-run / no-previous-signal is treated as NO CHANGE.**
  If `old_signals[sym] is None` for any symbol, that symbol's signal is considered "unchanged" for the purpose of `any_signal_changed` computation. Rationale: there is no comparison baseline; emitting ACTION REQUIRED on the first email would be noise. Operator sees first email as "state initialised — here's today's snapshot". Once the second run lands, the freshly-written signal becomes the baseline, and real signal transitions trigger ACTION REQUIRED.
  Concretely: `any_signal_changed = any(old is not None and old != new for sym, (old, new) in zip_old_new.items())`.

## HTML/CSS email spec & mobile responsiveness

- **D-07: Table-based layout — one outer 600px-max wrapper `<table>`, inner `<table>` per section.**
  Structure:
  ```html
  <!DOCTYPE html>
  <html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Trading Signals — {date}</title>
  </head>
  <body style="margin:0;padding:0;background:#0f1117;color:#e5e7eb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" bgcolor="#0f1117" style="background:#0f1117;">
      <tr><td align="center" style="padding:16px 8px;">
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="max-width:600px;width:100%;background:#161a24;border:1px solid #252a36;">
          <!-- sections: header / ACTION REQUIRED (conditional) / signal table / positions / today's P&L + running equity / last 5 trades / footer -->
        </table>
      </td></tr>
    </table>
  </body>
  </html>
  ```
  Every layout `<table>` carries `role="presentation"` for accessibility. Body `bgcolor` attribute repeats the inline-style background for Outlook redundancy. No `<style>` block — EVERY color/font/padding is inline on the element. No CSS classes. Explicitly `role="presentation"` on layout tables. Images (if any — footer logo maybe?) use `max-width:100%;height:auto;display:block;` inline + `<img alt="...">`.

- **D-08: Mobile via max-width wrapper, no media query.**
  Fluid-hybrid pattern. The 600px-max wrapper scales from 600px down to the viewport width (375px on iPhone SE, 320px on ancient devices) with no breakpoint needed. All internal section tables are `width="100%"` so they fluidly inherit. Text sizes: 14-16px body, 12-13px footer, 18-20px section headings, 22-26px key numbers. Line-heights 1.4+ for readability. No `@media` query (Gmail web strips `<style>`-based media queries inconsistently; better to avoid the fragility).
  Viewport meta tag `<meta name="viewport" content="width=device-width, initial-scale=1">` is present for iOS Mail to render at native scale.

- **D-09: Target clients: Gmail web + iOS Mail (MUST render). Others nice-to-have.**
  Tests/manual-verify surface focuses on:
  - Gmail web (Chrome/Safari desktop)
  - iOS Mail (iPhone)
  MUST-render behaviors:
  - Subject with emoji prefix (no client-side stripping)
  - Body dark theme (`#0f1117` background) not overridden by client dark-mode normalization
  - ACTION REQUIRED red-border block visible when present
  - Signal table colors match palette
  - Numbers readable at 375px width (no horizontal scroll)
  Nice-to-have: Gmail Android app, Outlook desktop, Apple Mail macOS, ProtonMail. If any client inverts colors (force-light mode), the `<table bgcolor="#0f1117">` attribute acts as a belt-and-braces fallback; some clients (Gmail web on `color-scheme: only light`) still may invert. Document the limitation; don't engineer around it in v1.

- **D-10: Body sections (NOTF-04), in order:**
  1. **Header** — site title "Trading Signals", date (AWST), "Last updated" timestamp
  2. **ACTION REQUIRED block** (conditional — only when `any_signal_changed` is True) — red left-border (`border-left: 4px solid #ef4444`), bold headline, per-instrument diff (e.g. "SPI 200: LONG → SHORT — close existing LONG and open new SHORT")
  3. **Signal status table** — two rows (SPI200 / AUDUSD) with columns: Instrument / Signal (colored) / signal_as_of / ADX / Mom snapshot
  4. **Open positions table** — one row per active position: Instrument / Direction / Entry / Current / Contracts / Trail Stop / Unrealised P&L. Empty-state: single row "No open positions". Mirror Phase 5 dashboard columns (7 here, not 8 — pyramid level omitted from email for brevity; dashboard has the full 8).
  5. **Today's P&L + running equity** — two stat lines. "Today's change: +$234 (from yesterday's close)" + "Running equity: $101,234 (+1.23% since inception)". Today's change is `state.equity_history[-1].equity - state.equity_history[-2].equity` if ≥2 points exist, else "—".
  6. **Last 5 closed trades** — table mirroring dashboard trades table but capped at 5 instead of 20 (fits in mobile scroll budget). Columns: Closed / Instrument / Direction / Entry→Exit / P&L.
  7. **Footer** — disclaimer "Signal-only system. Not financial advice." + "Trading Signals — sent by signals@carbonbookkeeping.com.au" + run-date ISO.

- **D-11: ACTION REQUIRED block copy (NOTF-05):**
  ```
  ━━━ ACTION REQUIRED ━━━
  SPI 200: LONG → SHORT
  Close existing LONG position (2 contracts @ entry $8,204.50).
  Open new SHORT position.

  AUD/USD: FLAT → LONG
  Open new LONG position.
  ```
  Red left-border (`border-left: 4px solid #ef4444`), `padding: 12px 16px`, white text on surface bg, bold "ACTION REQUIRED" headline. Per-instrument paragraph only for instruments that actually changed. Direction arrows use plain ASCII `→` (U+2192) — already in Phase 5 glyph budget, cross-OS-safe. Numbers formatted via `_fmt_currency_email`.

## Error handling, config & dispatch semantics

- **D-12: Resend retry policy mirrors `data_fetcher.fetch_ohlcv` (3 retries, 10s backoff, 30s timeout).**
  ```python
  def _post_to_resend(api_key, from_addr, to_addr, subject, html_body,
                     timeout_s=30, retries=3, backoff_s=10):
    payload = {'from': from_addr, 'to': [to_addr], 'subject': subject, 'html': html_body}
    headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
    for attempt in range(1, retries + 1):
      try:
        resp = requests.post(
          'https://api.resend.com/emails',
          headers=headers, json=payload, timeout=timeout_s,
        )
        if 400 <= resp.status_code < 500:
          raise ResendError(f'4xx from Resend: {resp.status_code} {resp.text[:200]}')
        resp.raise_for_status()  # 5xx raises HTTPError
        return
      except (requests.exceptions.Timeout, requests.exceptions.ConnectionError,
              requests.exceptions.HTTPError) as e:
        if attempt == retries:
          raise ResendError(f'retries exhausted: {type(e).__name__}: {e}') from e
        time.sleep(backoff_s)
  ```
  4xx errors (bad auth, invalid payload) fail fast — no retry. 5xx + timeout + connection errors retry up to 3 times with flat 10s sleep. Total worst-case wait: 20s (2 sleeps). 30s per-attempt HTTP timeout.

- **D-13: Missing `RESEND_API_KEY` → write `last_email.html` + log WARN + return success (NOTF-08).**
  `send_daily_email` checks `api_key = os.environ.get('RESEND_API_KEY')` at the top. If empty or None:
  ```python
  if not api_key:
    last_email_path = Path('last_email.html')
    _atomic_write_html(last_email_path, html_body)
    logger.warning('[Email] WARN RESEND_API_KEY missing — wrote %s (fallback)', last_email_path)
    return 0
  ```
  `last_email.html` is at repo root, gitignored (already in .gitignore from Phase 5's `dashboard.html` pattern — verify + extend). Overwritten every run. Operator can open it in a browser to preview the email. `_atomic_write_html` borrowed from dashboard.py pattern (could duplicate in notifier.py to avoid cross-hex import, OR live in state_manager.py's `_atomic_write` helper if generalised) — **Claude's Discretion: planner picks**. Current recommendation: duplicate in notifier.py (zero coupling, ~20 lines).

- **D-14: Config: `_EMAIL_FROM` hardcoded, `SIGNALS_EMAIL_TO` env var with fallback.**
  ```python
  _EMAIL_FROM = 'signals@carbonbookkeeping.com.au'  # verified Resend sender per PROJECT.md
  _EMAIL_TO_FALLBACK = 'marc@carbonbookkeeping.com.au'  # TODO operator confirm

  def _resolve_recipient() -> str:
    return os.environ.get('SIGNALS_EMAIL_TO', _EMAIL_TO_FALLBACK)
  ```
  `_EMAIL_TO_FALLBACK` value is operator-confirmed-at-plan-time (placeholder above); planner should insert a Wave 0 task to read `.env.example` OR CLAUDE.md operator info to get the right fallback. Document in `.env.example` (new file in Wave 0 scaffold) that `SIGNALS_EMAIL_TO` is the recipient override.
  Sender stays hardcoded because it's the Resend-verified domain; changing it would require re-verification with Resend. Single-operator-single-sender is the invariant.

- **D-15: Dispatch wiring (CLI-01 + CLI-03 Phase 6 completion):**
  `main.py` replaces the Phase 4 log-line stubs with real dispatch. Structure:
  ```python
  # In main() after flag parsing + reset/validate:
  if args.reset:
    return _handle_reset()

  if args.force_email or args.test:
    # Shared path: fresh-compute-then-email
    rc = run_daily_check(args)  # --test structurally skips save_state via early-return
    if rc == 0:
      # Re-load state for email. --test didn't save, so load_state() returns
      # the pre-run state; for --force-email --test we need the in-memory
      # post-compute state. Planner: pass state dict through from run_daily_check.
      # Recommendation: refactor run_daily_check to return (rc, state, old_signals).
      _send_email_never_crash(state, old_signals, run_date, is_test=args.test)
    return rc

  # Default path (and --once): no email
  return run_daily_check(args)
  ```
  `_send_email_never_crash` mirrors Phase 5's `_render_dashboard_never_crash`:
  ```python
  def _send_email_never_crash(state, old_signals, run_date, is_test):
    try:
      import notifier  # local import per C-2 pattern — isolates import-time failures
      notifier.send_daily_email(state, old_signals, run_date, is_test=is_test)
    except Exception as e:
      logger.warning('[Email] WARN send failed: %s', e)
  ```
  **Key architectural note for planner:** `run_daily_check(args)` currently returns just `rc: int`. Phase 6 needs to surface the in-memory `state` dict + `old_signals` dict to the email path without re-loading (since --test didn't save). Planner should refactor `run_daily_check` to return `(rc, state, old_signals)` OR expose them via a module-level `_last_run_context` variable OR re-run the compute path in email-dispatch. The refactor is minor (touch ~3 lines + 2 tests) and cleaner than the alternatives.
  **--test preserves CLI-01 read-only contract:** the `if args.test: return 0` early-return inside `run_daily_check` still fires before save_state; Phase 6 sends a `[TEST]`-prefixed email AFTER compute but WITHOUT save_state. No state mutation. The dashboard render is ALREADY guarded (Phase 5 C-3 Option A: dashboard only on non-test path) so --test still writes nothing to disk except `last_email.html` if RESEND_API_KEY is missing — which the operator is already opting into by using --test with no key configured.

## Claude's Discretion

Left to researcher/planner/executor:

- Exact class hierarchy for exceptions (`ResendError` is surfaced; child classes like `ResendAuthError` / `ResendRetryExhaustedError` are nice-to-have but not required).
- Whether `_atomic_write_html` duplicates into notifier.py or extracts to state_manager.py (recommendation: duplicate for zero coupling).
- Exact test fixture shapes — planner/executor picks meaningful mid-campaign state for `sample_state_with_change.json` (SPI200 LONG→SHORT transition) and `sample_state_no_change.json` (both instruments unchanged).
- Whether `compose_email_body` signature accepts pre-computed "today's change" as a parameter OR derives from `equity_history`. Recommendation: derive inline (DRY).
- ACTION REQUIRED diff phrasing per-transition cell — the D-11 example covers the 4 dominant cases (LONG→SHORT, SHORT→LONG, FLAT→LONG/SHORT, LONG/SHORT→FLAT); planner writes the full truth table.
- `.env.example` exact contents — at minimum `RESEND_API_KEY=re_xxx` and `SIGNALS_EMAIL_TO=marc@...`; planner adds any other env vars that Phase 7 will need.
- Whether Wave 2 commits `last_email.html` as a fixture OR regenerates it in the test run (recommendation: regenerate; it's a fallback artifact, not a golden).

## Phase 6 Scope Boundaries (what NOT to do)

- No Resend SDK. `requests` only per CLAUDE.md.
- No warnings carry-over (NOTF-10 is Phase 8).
- No schedule loop (Phase 7).
- No top-level crash-email (ERR-04 is Phase 8).
- No stale-state banner (ERR-05 is Phase 8).
- No multi-recipient fan-out (single operator).
- No attachment support (inline HTML only per NOTF-03).
- No `@media` query in CSS — fluid-hybrid only per D-08.
- No template engine (Jinja2 etc.) — stick with Python f-strings per PROJECT.md stack lock.
- No new pip dependencies.
- No changes to Phase 4 CLI-01 structural read-only contract.

</decisions>

<deferred>

Ideas raised or implied but deferred:

- Signal-history sparkline embedded in email (per-instrument mini-chart) — deferred to v2.
- Email preview URL in Resend dashboard — operator can already view via Resend console; no need for the app to surface it.
- Multi-recipient distribution list — single-operator v1.
- Dark-mode-aware email (using `color-scheme: dark` meta) — deferred; Gmail web handles this inconsistently; belt-and-braces bgcolor attribute is enough for v1.
- Structured-data email (Gmail Markup for Actions) — deferred; too fragile for the benefit.
- PDF attachment of the dashboard snapshot — deferred to v2.
- Per-instrument email preference (mute one instrument) — deferred to v2 V2-DEL-02.
- Slack webhook fallback on Resend failure — deferred to v2 V2-DEL-01.

</deferred>

<downstream_notes>

For the researcher (gsd-phase-researcher):
- Verify Resend API shape: `POST https://api.resend.com/emails` with JSON body `{from, to: [str], subject, html}` and Bearer auth header. Confirm status codes (200/202 success, 400 bad request, 401 bad auth, 429 rate limit, 500 server error). Confirm whether `to` is array of strings or array of objects.
- Confirm Resend rate limits (1 req/s default? Document for operator).
- Research email-client quirks for the 2 MUST-render clients (Gmail web + iOS Mail): any known issues with table-based layout, emoji in subjects (UTF-8 encoding), dark backgrounds, button-style elements?
- Check whether `requests.post(..., json=payload)` correctly sets `Content-Type: application/json` automatically (yes — but confirm).
- Investigate golden-HTML snapshot stability for email (whitespace differences between Python runs? Base64-ish encoding of emoji? Determinism fixture for `datetime.now`).
- Confirm the Phase 5 state['signals'] shape (dict with `signal`, `signal_as_of`, `as_of_run`, `last_scalars`, `last_close`) is fully present — D-05 old_signals capture assumes this.
- Check `os.environ.get('RESEND_API_KEY')` — does it read from `.env` automatically, or does the orchestrator need to call `load_dotenv()` somewhere? Phase 7 likely owns the dotenv-loading site; Phase 6 can just use `os.environ` assuming the env is set OR fall through to NOTF-08 fallback.

For the planner (gsd-planner):
- Likely plan breakdown:
  - **Wave 0 (06-01 BLOCKING scaffold):** `notifier.py` stub + `_INLINE_CSS_EMAIL` + `_EMAIL_FROM` + palette retrofit to system_params.py; `tests/test_notifier.py` 6-class skeleton; `tests/fixtures/notifier/` with 3 JSON fixtures; `.env.example` file; AST blocklist extension (FORBIDDEN_MODULES_NOTIFIER); `.gitignore` adds `last_email.html`; verify Phase 5 dashboard tests still green after palette retrofit.
  - **Wave 1 (06-02):** Implement `compose_email_subject` (6 test cases covering all emoji + TEST + first-run + equity-rounding), `compose_email_body` (section-by-section tests + ACTION REQUIRED conditional test), all formatters, `_detect_signal_changes` helper. Populate TestComposeSubject, TestComposeBody, TestFormatters.
  - **Wave 2 (06-03) PHASE GATE:** Implement `_post_to_resend` (retry loop + 4xx-fail-fast + 5xx-retry tests via monkeypatch `requests.post`), `send_daily_email` (RESEND_API_KEY-missing path + HTTP success path + HTTP retry-exhausted path + graceful-degradation path); main.py dispatch wiring + `_send_email_never_crash` helper (import-inside-try per C-2 pattern); refactor `run_daily_check` return to `(rc, state, old_signals)` tuple; 3 new orchestrator tests (`test_force_email_sends_live_email`, `test_test_flag_sends_test_prefixed_email`, `test_test_flag_leaves_state_json_mtime_unchanged_even_with_email`); convenience CLI entrypoint `python -m notifier` (mirror Phase 5 dashboard entry). PHASE GATE.
- The golden-HTML snapshot pattern from Phase 5 applies: frozen clock via `PERTH.localize(datetime(2026, 4, 22, 9, 0))`, byte-stable regenerator script, double-run gate. One golden per fixture scenario (change, no-change, empty).
- pytz usage: always `PERTH.localize(datetime(...))`. Never `datetime(..., tzinfo=pytz.timezone(...))`. Phase 5 reviews caught this; planner enforces in Wave 0 + code review.
- Monkeypatch discipline for Resend: patch at the module boundary — `monkeypatch.setattr('notifier.requests.post', _mock)` for the library-level mock, OR `monkeypatch.setattr(notifier, '_post_to_resend', _mock)` for the notifier-internal-helper mock. Phase 5 AC-1 pattern applies: import-inside-helper means the import lives inside the try/except; tests patch the real module attribute (`monkeypatch.setattr(notifier, 'send_daily_email', _raise)` for never-crash tests).

For the reviewer (cross-AI after plans written — `/gsd-review 6`):
- Watch for `subject` string escape — emoji must pass through `requests.post(json=...)` as UTF-8 not `\u...` escape (check the `ensure_ascii=False` / default).
- Watch for recipient env-var leak if `_EMAIL_TO_FALLBACK` contains a real address in the committed code.
- Watch for dashboard.py regression after the palette retrofit (Phase 5 golden HTML byte-stable under the new import path).
- Watch for `--test` + email combo — tests must assert state.json mtime unchanged EVEN when email is sent (CLI-01 lock).
- Watch for `run_daily_check` signature refactor breaking Phase 4 tests — the tuple return needs careful migration.
- Watch for Resend rate-limit handling under the 3-retry policy (429 is a 4xx so fails fast — may need special case).

</downstream_notes>

## Next Step

Run `/gsd-plan-phase 6` to produce `06-RESEARCH.md` + `06-PATTERNS.md` + plan files.

Optional: `/gsd-ui-phase 6` first to produce an email UI-SPEC.md before planning. Email is visually dense and the 4 email-client compatibility axes (Gmail web + iOS Mail MUST-render; Outlook + Gmail Android nice-to-have) are worth locking in a contract. Recommended — especially after Phase 5 UI-SPEC caught the `last_close` wiring bug pre-execution.
