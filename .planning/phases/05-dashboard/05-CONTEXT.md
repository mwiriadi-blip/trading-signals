# Phase 5 — CONTEXT

**Phase:** 05 — Dashboard
**Created:** 2026-04-22
**Discuss mode:** discuss
**Goal (from ROADMAP.md):** Render a self-contained `dashboard.html` each run that lets the operator visually verify signal state, open positions, equity history, and recent trades — matching the backtest dark aesthetic.

**Requirements covered:** DASH-01, DASH-02, DASH-03, DASH-04, DASH-05, DASH-06, DASH-07, DASH-08, DASH-09 (9 requirements)
**Out of scope (later/other phases):**
- Email rendering (Phase 6 — different template, inline-CSS requirement + Resend dispatch)
- Interactive JS state / SPA behavior (static file; Chart.js only for the equity curve)
- Hosting / serving the HTML (file written to disk, operator opens locally; GHA commit-back is separate workflow concern)
- Schedule-loop wiring (Phase 7)
- Crash-email / Resend failure handling (Phase 8)

<canonical_refs>

External specs, ADRs, and prior CONTEXT docs that downstream agents must consult:

- **.planning/PROJECT.md** — Palette (`#0f1117` bg, green/red/gold signal colours), "single self-contained HTML with inline CSS and CDN Chart.js, no build step", stack allowlist.
- **.planning/REQUIREMENTS.md** — DASH-01..09 full text; cross-phase coverage map.
- **.planning/ROADMAP.md** — Phase 5 goal + 5 success criteria.
- **CLAUDE.md** — 2-space indent, single quotes, snake_case, hex-lite rules.
- **SPEC.md** — Full functional spec.
- **.planning/phases/03-state-persistence-with-recovery/03-CONTEXT.md** + 03-0N-SUMMARY.md — `state_manager.load_state` public API (signature `load_state(path=..., now=None) -> dict`); state schema: `account`, `positions`, `signals`, `trade_log`, `equity_history`, `warnings`, `last_run`, `schema_version`.
- **.planning/phases/04-end-to-end-skeleton-fetch-orchestrator-cli/04-CONTEXT.md** — D-08 per-instrument signal shape `state['signals'][symbol] = {'signal': int, 'signal_as_of': 'YYYY-MM-DD', 'as_of_run': iso, 'last_scalars': dict}` + D-11 orchestrator flow (dashboard renders downstream of `save_state`).
- **.planning/phases/04-end-to-end-skeleton-fetch-orchestrator-cli/04-03-SUMMARY.md** — `_closed_trade_to_record` produces trade dicts with fields `{symbol, entry_date, exit_date, direction, entry_price, exit_price, n_contracts, realised_pnl, gross_pnl, atr_entry, pyramid_level_at_close, exit_reason}` (D-12/D-19). `gross_pnl` is the raw price-delta × contracts × multiplier; `realised_pnl` is net of closing cost.
- **system_params.py** — `INITIAL_ACCOUNT = 100_000`, contract specs (SPI_MULT=5, SPI_COST_AUD=6.0, AUDUSD_NOTIONAL=10000, AUDUSD_COST_AUD=5.0), `Position` TypedDict.
- **state_manager.py** — `load_state` is the only function Phase 5 uses.

</canonical_refs>

<prior_decisions>

Decisions from earlier phases that apply without re-asking:

- **Hex-lite boundary** (Phase 1/2/3/4): `dashboard.py` is a new I/O hex (analog of `state_manager.py` / `data_fetcher.py`). Strictly forbidden to import `signal_engine`, `sizing_engine`, `data_fetcher`, `main`, `notifier`, `numpy`, or `pandas`. AST blocklist guard in `tests/test_signal_engine.py::TestDeterminism` extended in Wave 0.
- **Palette locked** (PROJECT.md):
  - Background: `#0f1117`
  - LONG: `#22c55e` (green)
  - SHORT: `#ef4444` (red)
  - FLAT: `#eab308` (gold)
  - Dashboard reuses these verbatim. Phase 6 email will reuse them too.
- **No build step** (PROJECT.md Constraints): single `dashboard.html` with inline CSS; Chart.js loaded from CDN with SRI hash.
- **Timezone** (CLAUDE.md / PROJECT.md): All user-facing timestamps use AWST via `pytz.timezone('Australia/Perth')`.
- **Style** (CLAUDE.md): 2-space indent, single quotes, snake_case for functions, UPPER_SNAKE for constants.
- **Log prefixes** (CLAUDE.md): `[Signal] [State] [Email] [Sched] [Fetch]`. Phase 5 adds its own prefix: `[Dashboard]` (new).
- **Tech stack** (PROJECT.md): Python 3.11, pinned deps (yfinance, pandas, numpy, requests, schedule, python-dotenv, pytz, pytest, ruff, pytest-freezer). Phase 5 adds no new deps — uses stdlib `html`, `datetime`, `json`, plus `pytz` already pinned.
- **No max(1, …) floor / skip-zero-size trade** (operator decision, Phase 2): trade_log may contain `n_contracts == 0` warnings from prior runs; dashboard should treat these as "skipped" rows in the trade history rendering.

</prior_decisions>

<folded_todos>

No pending todos matched Phase 5 scope.

</folded_todos>

<decisions>

## Render architecture & output location

- **D-01: New module `dashboard.py` at repo root owns all HTML rendering.**
  Public API: `render_dashboard(state: dict, out_path: Path = Path('dashboard.html'), now: datetime | None = None) -> None`. Reads a plain-dict `state` (caller-supplied) and writes `dashboard.html` atomically (tempfile + `os.replace`, mirroring `state_manager._atomic_write` pattern per Phase 3 D-04). Accepts an optional `now` for freezer-based tests to lock the "Last updated" timestamp deterministically.
  `dashboard.py` imports: `state_manager` (for `load_state` — convenience CLI path only; main.py passes state directly via `render_dashboard(state, out_path)` in production), `system_params` (for palette constants, `INITIAL_ACCOUNT`), stdlib (`datetime`, `json`, `html`, `os`, `tempfile`, `pathlib`, `statistics`, `math`), and `pytz`. MUST NOT import `signal_engine`, `sizing_engine`, `data_fetcher`, `main`, `notifier`, `numpy`, or `pandas`.
  AST blocklist extension in Wave 0: `FORBIDDEN_MODULES_DASHBOARD = frozenset({'signal_engine', 'sizing_engine', 'data_fetcher', 'main', 'notifier', 'numpy', 'pandas'})`.

- **D-02: Render strategy is pure Python block-builder helpers in `dashboard.py`.**
  One helper per logical block, each returning an HTML string:
  - `_render_header(state, run_date_iso) -> str` — app title + "Last updated" timestamp in AWST
  - `_render_signal_cards(state) -> str` — two cards (SPI200 + AUDUSD) with signal label + colour, signal_as_of, ADX/Mom values from `last_scalars`
  - `_render_positions_table(state) -> str` — open positions, one row per instrument (empty state: single placeholder row)
  - `_render_trades_table(state) -> str` — last 20 closed trades from `trade_log` (newest first)
  - `_render_equity_chart_container(state) -> str` — `<canvas>` + inline `<script>` that instantiates Chart.js with equity_history data
  - `_render_key_stats(state) -> str` — total return / Sharpe / max drawdown / win rate block
  - `_render_footer() -> str` — disclaimer line ("Signal-only system. Not financial advice.")
  - `_render_html_shell(body: str, run_date_iso: str) -> str` — wraps body in `<!DOCTYPE html><html><head>...<style>{inline_css}</style>...<script src="Chart.js CDN" integrity="sha384-..." crossorigin></script></head><body>{body}</body></html>`
  `render_dashboard(state, out_path, now)` concatenates the body blocks and invokes the shell.
  Rationale: aligns with "no build step" + "no new deps". Each helper is unit-testable in isolation. Jinja2 rejected (would need PROJECT.md stack amendment).

- **D-03: Output path is repo-root `dashboard.html`, gitignored.**
  Written atomically; overwritten every run. Added to `.gitignore` in Wave 0 scaffold. Consistent with `state.json` placement. GHA deploy workflow (Phase 7) may later commit it alongside state.json if the operator wants rendered history — not a Phase 5 concern.

- **D-04: Inline CSS lives as a module-level constant `_INLINE_CSS` in `dashboard.py`.**
  One single constant string containing the full stylesheet. Palette constants (`_COLOR_BG = '#0f1117'`, `_COLOR_LONG = '#22c55e'`, `_COLOR_SHORT = '#ef4444'`, `_COLOR_FLAT = '#eab308'`) interpolate into the CSS via f-string at module-load time. No build step, no external stylesheet, no CSS-in-JS. The CSS is designed-for-one-dark-theme; no light mode, no media-query colour shifts.

## Hex boundaries

- **D-05: Read-only consumer of state_manager.**
  `dashboard.py` may `from state_manager import load_state` and `import system_params` (for palette constants + INITIAL_ACCOUNT). No state_manager mutations (`save_state`, `reset_state`, `record_trade`, `append_warning`, `update_equity_history`) are called from `dashboard.py`.
  A convenience CLI `python -m dashboard` exists — calls `load_state()` and `render_dashboard(state)`. Production path is `main.run_daily_check()` which calls `dashboard.render_dashboard(state, ...)` after the main `save_state` call with the freshly-computed in-memory state.

- **D-06: Orchestrator integration point (Phase 5 amends main.py).**
  After the final `save_state(state)` in `run_daily_check()`, add `dashboard.render_dashboard(state, Path('dashboard.html'), now=run_date)` — this is a new import site for `dashboard` in main.py. The AST blocklist for main.py remains tight (C-5 revision keeps FORBIDDEN_MODULES_MAIN = {numpy, yfinance, requests, pandas}). main.py may import `dashboard` because dashboard is a sibling hex, same as state_manager.
  Dashboard render failures must NEVER crash the run. Wrap the call in `try/except Exception: logger.warning('[Dashboard] render failed: %s', e)`. State has already been saved; email will still go out in Phase 6. Matches the "never crash silently, never crash loudly on cosmetic failure" posture.

## Key stats math

- **D-07: Sharpe = daily log-returns, rf=0, annualised ×√252.**
  Formula:
  ```python
  equities = [row['equity'] for row in state['equity_history']]
  if len(equities) < 30:
    return '—'  # not enough samples
  log_returns = [math.log(equities[i] / equities[i-1]) for i in range(1, len(equities))]
  mean_r = statistics.mean(log_returns)
  std_r = statistics.stdev(log_returns)
  if std_r == 0:
    return '—'  # guard div-by-zero
  sharpe = (mean_r / std_r) * math.sqrt(252)
  ```
  Display: `f'{sharpe:.2f}'` (e.g. `1.23`, `-0.45`). Below 30 equity points → `—`.

- **D-08: Max drawdown = rolling peak-to-trough percentage.**
  Formula:
  ```python
  running_max = equities[0]
  max_dd = 0.0
  for eq in equities:
    running_max = max(running_max, eq)
    dd = (eq - running_max) / running_max  # ≤ 0
    max_dd = min(max_dd, dd)
  ```
  Display as `f'{max_dd*100:.1f}%'` (e.g. `-12.5%`). Always negative or zero. Empty equity_history → `—`.

- **D-09: Win rate = closed trades with `gross_pnl > 0` (not realised_pnl).**
  Formula:
  ```python
  closed = state['trade_log']
  if not closed:
    return '—'
  wins = sum(1 for t in closed if t['gross_pnl'] > 0)
  win_rate = wins / len(closed)
  ```
  Display as `f'{win_rate*100:.1f}%'`. Uses `gross_pnl` (price-delta × contracts × multiplier) NOT `realised_pnl` (which has closing cost deducted) — consistent with industry convention ("win before costs"). Empty trade_log → `—`.

- **D-10: Total return = `(current_equity - INITIAL_ACCOUNT) / INITIAL_ACCOUNT * 100`.**
  Formula:
  ```python
  current = state.get('equity_history', [{}])[-1].get('equity', state['account'])
  total_return = (current - INITIAL_ACCOUNT) / INITIAL_ACCOUNT
  ```
  Display as `f'{total_return*100:+.1f}%'` (signed: `+5.3%`, `-2.1%`). Always defined (INITIAL_ACCOUNT is a constant). Uses the most recent equity_history entry if present, else falls back to `state['account']` (which equals starting $100K on first run).

## Chart.js config & empty state

- **D-11: Category x-axis with ISO date labels; no date adapter.**
  Chart.js config:
  ```js
  new Chart(canvas, {
    type: 'line',
    data: {
      labels: [/* equity_history[i].date for all i */],
      datasets: [{
        label: 'Account equity',
        data: [/* equity_history[i].equity for all i */],
        borderColor: '#22c55e',
        backgroundColor: '#22c55e',  // used for point fill only, no area fill
        fill: false,
        tension: 0.1,
        borderWidth: 2,
        pointRadius: 0,              // clean line, no per-point markers
        pointHoverRadius: 4,
      }]
    },
    options: {
      scales: {
        x: { type: 'category', ticks: { color: '#cbd5e1', maxTicksLimit: 10 } },
        y: { ticks: { color: '#cbd5e1', callback: (v) => '$' + v.toLocaleString() } }
      },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (ctx) => '$' + ctx.parsed.y.toLocaleString() } }
      },
      maintainAspectRatio: false,
      responsive: true,
    }
  });
  ```
  Rationale: category axis needs zero adapter libs; chartjs-adapter-date-fns rejected to keep external-asset count minimal. `maxTicksLimit: 10` prevents overlapping date labels on long histories. Tooltip shows full dollar amount.

- **D-12: Chart.js 4.4.6 UMD loaded from pinned CDN with SRI.**
  Exact snippet rendered into `<head>`:
  ```html
  <script
    src="https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.js"
    integrity="sha384-C5GVzRkc2bvIeI4A/1dpJpBdFfJKydDPTGdcOKtKjIaCfHBqBjqfGyMEWFi3ExWn"
    crossorigin="anonymous"></script>
  ```
  The SRI hash is computed from the CDN response of v4.4.6 and committed into `dashboard.py` as a module constant `_CHARTJS_SRI`. Operator re-generates the SRI only on intentional Chart.js version bump.
  Research task for Wave 0: verify the SRI hash by downloading the UMD file and computing `openssl dgst -sha384 -binary chart.umd.js | base64`. If the hash above is wrong, Wave 0 must correct it — do NOT ship a mismatched SRI (browser refuses to execute the script).

- **D-13: Empty-state rendering.**
  All sections render on first run with meaningful placeholders:
  - **Signal cards:** always render. Pre-first-run `state['signals']` has no per-instrument entries → show signal label "—" with `_COLOR_FLAT` (gold), "signal_as_of: never" message.
  - **Equity chart:** if `equity_history` is empty → skip the `<canvas>` + `<script>`, render a `<div class="empty-state">No equity history yet — first full run needed</div>` placeholder in its place.
  - **Positions table:** always render header row. If `state['positions']` has no active positions (all values None or missing), render `<tr><td colspan="7">— No open positions —</td></tr>`.
  - **Trades table:** always render header row. If `trade_log` is empty → `<tr><td colspan="N">— No closed trades yet —</td></tr>`.
  - **Key stats:** individual values show `—` per D-07/D-08/D-09 when insufficient data.
  Rationale: dashboard is a visual verification tool; the "does this run work?" question must always have a dashboard answer, even before the first trade.

## Testing & numeric formatting

- **D-14: Test strategy is unit tests on helpers + a golden-HTML smoke test.**
  Test file: `tests/test_dashboard.py` with classes:
  - `TestStatsMath` — per-function tests for `_compute_sharpe`, `_compute_max_drawdown`, `_compute_win_rate`, `_compute_total_return` with hand-built `state` dicts (happy path, empty history, single-point history, all-losses, all-wins, flat equity).
  - `TestFormatters` — `_fmt_currency`, `_fmt_percent`, `_fmt_pnl_with_colour` unit tests covering positive / negative / zero / edge cases ($0.00, -$0.01, $100,000.00, +5.3%, -12.5%, exact zero).
  - `TestRenderBlocks` — each `_render_*` block called with a fixture state, output asserted via substring matches (e.g. `'#22c55e' in output`, `'SPI200' in output`, `'<table' in output`). BeautifulSoup is NOT required — string matching keeps tests stdlib-only.
  - `TestEmptyState` — `render_dashboard({'account': 100000, 'positions': {}, 'signals': {}, 'trade_log': [], 'equity_history': [], 'warnings': [], 'last_run': None, 'schema_version': 1})` must produce a complete well-formed HTML document with all placeholders present.
  - `TestGoldenSnapshot` — `render_dashboard(sample_state)` output is diffed against a committed `tests/fixtures/dashboard/golden.html`. Regenerated via `tests/regenerate_dashboard_golden.py` (mirrors Phase 1 `regenerate_goldens.py` pattern). Git-diff on the golden file IS the design review surface — any unintentional CSS/layout change surfaces in PR review.
  - `TestAtomicWrite` — `render_dashboard` writes via tempfile + `os.replace`; tested by asserting partial writes never land at the final path on simulated crash (analog of Phase 3 TestAtomicity).

- **D-15: XSS safety — always escape via `html.escape()` for state-derived text.**
  Every string field sourced from `state` that lands inside HTML (symbol names, exit_reason text, warning messages, dates as strings) passes through `html.escape(value, quote=True)` before interpolation. Numeric fields (account, equity, pnl) are formatted via D-16 format strings that produce already-safe output (no special chars). Ahead-of-time safety posture even though Marc is the only writer: trivial cost, avoids future multi-user retrofit, reduces review burden.

- **D-16: Numeric format conventions (all stdlib-only).**
  - Currency: `f'${value:,.2f}'` → `$100,994.00`, `-$500.50`. Negative formatted as `-$500.50` not `($500.50)`.
  - Percent: `f'{value*100:+.1f}%'` when signed (total return) → `+5.3%`, `-12.5%`. `f'{value*100:.1f}%'` when unsigned (win rate, max DD as percentage) → `58.3%`, `-12.5%`.
  - P&L with colour: `_fmt_pnl_with_colour(value)` returns HTML like `<span style="color: #22c55e">+$1,234.56</span>` for positive, `<span style="color: #ef4444">-$567.89</span>` for negative, `<span style="color: #cbd5e1">$0.00</span>` for zero.
  - Small values always keep `.00` (e.g. `$100,000.00` not `$100,000`) for visual consistency across the column.
  - No K/M/B suffixes (operator reads full numbers).
  - "—" (em-dash) used for missing/N/A values (Sharpe with <30 samples, win rate on empty log, empty positions table cells).

## Claude's Discretion

- Exact CSS layout (single-column mobile-first? grid? flex?). Designer-ish taste within palette and "matches backtest aesthetic" guardrail.
- Whether `_render_html_shell` uses a `<title>` like "Trading Signals — Dashboard" or just "Dashboard".
- Exact font stack (system font vs webfont — webfonts are OFF LIMITS per PROJECT.md "no external stylesheets" interpretation; system-ui/sans-serif is fine).
- Column order in positions table — DASH-05 lists the columns but order is cosmetic.
- Column order / count in trades table (DASH-06 says "rendered as an HTML table" — planner picks display fields).
- Whether the golden snapshot fixture includes 1 instrument or 2 (probably both — matches production).
- `[Dashboard]` log message content (planner phrases concrete strings).
- Whether `render_dashboard` logs on start/end or stays silent. (Recommendation: one INFO log at start, one at end, both with `[Dashboard]` prefix, matching the Phase 4 D-14 convention.)

## Phase 5 Scope Boundaries (what NOT to do)

- No email. Phase 6 reuses some render helpers (palette + `_fmt_currency` + `_fmt_pnl_with_colour`) but has its own `notifier.py` module with inline-CSS specifically shaped for email clients.
- No scheduler. Phase 7 owns the cron wiring.
- No live data reads. `dashboard.py` reads only `state.json` (via state_manager) — never calls yfinance.
- No new pip dependencies.
- No responsive "mobile vs desktop" variant — one layout, works at 375px+ viewport.
- No dark/light toggle. One dark theme, always.
- No interactive filters/controls on the dashboard. Static render.

</decisions>

<deferred>

Ideas raised in discussion that belong in later phases or future milestones:

- Jinja2 templating — rejected for Phase 5; would need stack amendment. Revisit only if render code grows beyond ~500 lines and Python string blocks become painful.
- Headless-browser smoke tests (Playwright / Selenium) — rejected; new heavy dependency. Golden-HTML snapshot tests cover 95% of the risk.
- Rolling N-day Calmar or Sortino ratios — out of scope. Plain Sharpe is sufficient for a single-operator mechanical system.
- Light-mode / theme toggle — deferred; current operator prefers dark-only.
- Per-instrument equity sub-chart — deferred; combined account equity is sufficient.
- Interactive hover-and-zoom on Chart.js — default hover tooltip only; zoom/pan plugins deferred.
- SVG-based sparkline alternative to Chart.js — deferred; Chart.js is locked per PROJECT.md and the operator already reads the backtest dashboards.
- Thousands-suffix (K/M) formatting — deferred; operator prefers full numbers.
- Mobile-responsive breakpoints below 375px — deferred; dashboard is a local tool the operator views on desktop.

</deferred>

<downstream_notes>

For the researcher (gsd-phase-researcher):
- Verify the Chart.js 4.4.6 CDN URL + SRI hash. Compute via `curl -sL https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.js | openssl dgst -sha384 -binary | base64`. Document the exact SRI string in RESEARCH.md for the planner to copy into `_CHARTJS_SRI`.
- Confirm `html.escape(value, quote=True)` is the right stdlib primitive — versus `markupsafe.escape`. Stdlib preferred.
- Research whether Chart.js 4.4.6 needs any Content-Security-Policy accommodations for the inline `<script>` that instantiates the chart. If the operator ever serves the HTML behind a strict CSP, the inline script would break — note this as a deferred concern.
- Check whether Python `statistics.stdev` matches numpy's `std(..., ddof=1)` for Sharpe — this project explicitly forbids numpy in dashboard.py, so the stdlib path must be exact for test portability.
- Investigate whether the golden-HTML snapshot needs a sample `state.json` fixture committed — and how to keep it stable across runs (frozen clock for "Last updated" timestamp).
- Confirm `dashboard.py` can be called from main.py without introducing any import cycles. main.py imports dashboard (new); dashboard imports state_manager + system_params (same as main.py). No cycle.

For the planner (gsd-planner):
- Likely plan shape (researcher confirms):
  - **Wave 0 BLOCKING scaffold (05-01):** `dashboard.py` stub with all 7 `_render_*` helpers raising NotImplementedError, `_CHARTJS_SRI` + palette constants, AST blocklist extension (FORBIDDEN_MODULES_DASHBOARD), `tests/test_dashboard.py` skeletons for the 6 test classes, `tests/regenerate_dashboard_golden.py` offline script, `tests/fixtures/dashboard/sample_state.json` + initial `golden.html` committed, `.gitignore` updated for `dashboard.html`.
  - **Wave 1 (05-02):** fill stats math helpers (`_compute_sharpe`, `_compute_max_drawdown`, `_compute_win_rate`, `_compute_total_return`) + formatters + per-block renderers (`_render_header`, `_render_signal_cards`, `_render_positions_table`, `_render_trades_table`, `_render_key_stats`, `_render_footer`). Populate TestStatsMath + TestFormatters + TestRenderBlocks.
  - **Wave 2 (05-03):** fill `_render_equity_chart_container` (Chart.js inline script) + `_render_html_shell` + `render_dashboard` (atomic write). Populate TestEmptyState + TestAtomicWrite + TestGoldenSnapshot. PHASE GATE.
  - **Wave 3 (05-04) if needed:** integration task — main.py amendment to call `dashboard.render_dashboard(state, out_path, now=run_date)` after save_state. Add a main-level test `test_run_daily_check_renders_dashboard_after_save`. OR fold into Wave 2 if task count allows.
- Golden HTML snapshot must be frozen-clock-friendly: pass `now=datetime(2026, 4, 22, 9, 0, tzinfo=pytz.timezone('Australia/Perth'))` in the regenerator so re-runs produce identical bytes.
- `sample_state.json` fixture should be a realistic mid-campaign state — not empty (so all render blocks have content) and not first-run (empty-state covered separately by TestEmptyState).
- The AST source-order gate used in Phase 4 (to verify the AC-1 record_trade-before-position-assignment ordering) is NOT needed here — no ordering hazards in dashboard.py.

For the reviewer (cross-AI review after plans written):
- Watch for: Chart.js SRI hash typos (copy-paste errors break the whole chart silently in the browser), any accidental import of signal_engine/sizing_engine (hex-lite violation), any unescaped state-value interpolation (XSS), Sharpe formula off-by-one on the log-return series (len N → N-1 returns), max drawdown formula inverting signs.
- Watch for the dashboard.render_dashboard failure-path in main.py (D-06) being too loose — must log + continue, never raise.
- Watch for the golden-HTML snapshot containing an unfrozen timestamp (timezone naive vs aware).

</downstream_notes>

## Next Step

Run `/gsd-plan-phase 5` to produce `05-RESEARCH.md` and plan files.

Optional: `/gsd-ui-phase 5` first if a visual design contract (UI-SPEC.md) is desired. The ROADMAP marks "UI hint: no" for this phase, but Phase 5 is visually the densest phase — a UI-SPEC.md would lock component hierarchy, typography scale, and spacing system before planning. The operator may choose to skip that step since the palette + aesthetic are already locked from the backtest prior work; in that case, plan-phase proceeds directly with research.
