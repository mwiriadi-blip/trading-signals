# Phase 5: Dashboard - Research

**Researched:** 2026-04-21
**Domain:** Static HTML dashboard rendering (Python stdlib string builder + Chart.js CDN + inline CSS)
**Confidence:** HIGH for toolchain + SRI (verified via direct curl); HIGH for stdlib primitives (tested in this session); MEDIUM for golden-snapshot byte-stability guidance (tested at float-ordering level, not cross-OS); HIGH for B-1 retrofit scope (grep + read of current main.py).

## Summary

Phase 5 ships `dashboard.py` - a pure Python I/O hex that reads `state.json` (through `state_manager.load_state`) and writes a single `dashboard.html` via atomic tempfile + `os.replace`, matching `state_manager._atomic_write` precedent. Rendering is a flat pipeline of 7 block-builder helpers returning HTML strings; Chart.js 4.4.6 UMD is loaded from jsdelivr with a locked SHA-384 SRI hash; inline CSS is a single module-level `_INLINE_CSS` constant with palette tokens f-string-interpolated. Every state-derived string goes through `html.escape(value, quote=True)`; every JSON payload injected into the inline `<script>` goes through `json.dumps(...)` then `.replace('</', '<\/')` to prevent `</script>` injection. Tests are class-organised with a golden-HTML snapshot as the headline gate, plus unit tests on stats math + formatters. Wave 0 carries a blocking `main.py` retrofit to emit `last_close` alongside `last_scalars` so the UI-SPEC "Current" column has a data source.

**Primary recommendation:** Ship exactly the plan shape CONTEXT D-14 + UI-SPEC §Component Hierarchy lock: one `dashboard.py` with 7 `_render_*` helpers + 5 format helpers + 4 stats helpers + `render_dashboard(state, out_path, now)`. Wave 0 retrofit is a ~2-line change in `main.py:514-519` plus assertion updates in exactly ONE existing test (`tests/test_main.py::TestOrchestrator::test_orchestrator_reads_both_int_and_dict_signal_shape`).

**SRI verified:** `sha384-MH1axGwz/uQzfIcjFdjEfsM0xlf5mmWfAwwggaOh5IPFvgKFGbJ2PZ4VBbgSYBQN` (jsdelivr + unpkg identical, 205,615 bytes, computed 2026-04-21). The placeholder hash in CONTEXT D-12 (`sha384-C5GVzRkc2bvIeI4A/1dpJpBdFfJKydDPTGdcOKtKjIaCfHBqBjqfGyMEWFi3ExWn`) is stale - the planner must use the verified hash.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions (verbatim from 05-CONTEXT.md)

**D-01: New module `dashboard.py` at repo root owns all HTML rendering.**
Public API: `render_dashboard(state: dict, out_path: Path = Path('dashboard.html'), now: datetime | None = None) -> None`. Reads a plain-dict `state` and writes `dashboard.html` atomically (tempfile + `os.replace`, mirroring `state_manager._atomic_write` per Phase 3 D-04). Accepts optional `now` for freezer-based tests. `dashboard.py` imports: `state_manager` (only for `load_state` - CLI-path convenience; main.py passes state directly in production), `system_params` (palette constants + `INITIAL_ACCOUNT`), stdlib (`datetime`, `json`, `html`, `os`, `tempfile`, `pathlib`, `statistics`, `math`), and `pytz`. MUST NOT import `signal_engine`, `sizing_engine`, `data_fetcher`, `main`, `notifier`, `numpy`, or `pandas`. AST blocklist extension in Wave 0: `FORBIDDEN_MODULES_DASHBOARD = frozenset({'signal_engine', 'sizing_engine', 'data_fetcher', 'main', 'notifier', 'numpy', 'pandas'})`.

**D-02: Render strategy is pure Python block-builder helpers.** One helper per logical block returning an HTML string: `_render_header`, `_render_signal_cards`, `_render_positions_table`, `_render_trades_table`, `_render_equity_chart_container`, `_render_key_stats`, `_render_footer`, `_render_html_shell`.

**D-03: Output path is repo-root `dashboard.html`, gitignored.** Atomic write, overwritten every run.

**D-04: Inline CSS lives as module-level `_INLINE_CSS`.** Palette constants (`_COLOR_BG`, `_COLOR_LONG`, `_COLOR_SHORT`, `_COLOR_FLAT`) interpolate via f-string at module-load time.

**D-05: Read-only consumer of state_manager.** `dashboard.py` may import `state_manager` (for `load_state` only) + `system_params`. No state_manager mutations.

**D-06: Orchestrator integration point in main.py.** After final `save_state(state)`, call `dashboard.render_dashboard(state, Path('dashboard.html'), now=run_date)` wrapped in try/except Exception; never crash the run.

**D-07: Sharpe formula.** daily log-returns, rf=0, annualised x sqrt(252); `—` when `len(equities) < 30` or `stdev == 0`.

**D-08: Max drawdown formula.** rolling peak-to-trough %; always <= 0; empty history -> `—`.

**D-09: Win rate formula.** closed trades with `gross_pnl > 0` / total closed; empty trade_log -> `—`.

**D-10: Total return formula.** `(current_equity - INITIAL_ACCOUNT) / INITIAL_ACCOUNT * 100`; `current_equity = state['equity_history'][-1]['equity']` if present else `state['account']`; signed format `+5.3% / -2.1%`.

**D-11: Chart.js config.** Category x-axis with ISO date labels, no date adapter; `maintainAspectRatio: false`, `responsive: true`, `pointRadius: 0`, `pointHoverRadius: 4`, `legend: { display: false }`; tooltip renders `$<value>` with commas; `maxTicksLimit: 10`.

**D-12: Chart.js 4.4.6 UMD loaded from pinned CDN with SRI.**

**D-13: Empty-state rendering.** All sections render on first run with meaningful placeholders (not suppressed).

**D-14: Unit tests on helpers + golden-HTML smoke test.** Classes: `TestStatsMath`, `TestFormatters`, `TestRenderBlocks`, `TestEmptyState`, `TestGoldenSnapshot`, `TestAtomicWrite`.

**D-15: XSS safety.** Every state-derived string passes through `html.escape(value, quote=True)` before interpolation.

**D-16: Numeric format conventions.** Currency `f'${value:,.2f}'`; percent signed `f'{value*100:+.1f}%'`; percent unsigned `f'{value*100:.1f}%'`; `_fmt_pnl_with_colour` wraps in `<span style="color: ...">`; `—` for missing values.

### Claude's Discretion

- Exact CSS layout (single-column mobile-first / grid / flex).
- Whether `_render_html_shell` uses `<title>` "Trading Signals - Dashboard" (UI-SPEC locks this) vs other.
- Exact system font stack (webfonts forbidden; system-ui/sans-serif fine - UI-SPEC locks the exact stack).
- Column order in positions / trades tables - UI-SPEC locks them.
- Golden snapshot fixture scenario (1 instrument or 2 - UI-SPEC suggests both).
- `[Dashboard]` log message content.
- Whether `render_dashboard` logs on start/end (recommendation: one INFO log at start, one at end).

### Deferred Ideas (OUT OF SCOPE)

- Jinja2 templating.
- Headless-browser smoke tests (Playwright / Selenium).
- Rolling Calmar / Sortino ratios.
- Light-mode / theme toggle.
- Per-instrument equity sub-chart.
- Interactive hover-and-zoom Chart.js plugins.
- SVG-based sparkline alternative to Chart.js.
- K/M/B thousands-suffix formatting.
- Mobile-responsive breakpoints below 375px.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DASH-01 | `dashboard.html` is a single self-contained file with inline CSS | `_INLINE_CSS` module constant (D-04); single-file write via `_atomic_write` analog; no external stylesheet links; palette interpolated at module-load time |
| DASH-02 | Chart.js 4.4.6 UMD loaded from pinned CDN with SRI hash | SRI verified `sha384-MH1axGwz/uQzfIcjFdjEfsM0xlf5mmWfAwwggaOh5IPFvgKFGbJ2PZ4VBbgSYBQN` (both jsdelivr + unpkg return byte-identical 205,615-byte file); `_CHARTJS_URL` + `_CHARTJS_SRI` module constants |
| DASH-03 | Page shows current signal for both instruments with status colour | `_render_signal_cards(state)`; UI-SPEC §Signal cards locks instrument display names + chip colouring via `--color-long`/`--color-short`/`--color-flat`; empty-state uses `—` in `--color-flat` (D-13) |
| DASH-04 | Account equity chart (Chart.js line) uses `equity_history` data | `_render_equity_chart_container(state)` emits `<canvas id="equityChart">` + inline `<script>` that instantiates `new Chart(...)` from D-11 config; data interpolated via `json.dumps(...).replace('</', '<\\/')` to prevent `</script>` injection; empty history renders placeholder `<div>` per D-13 |
| DASH-05 | Open positions table shows entry, current, contracts, pyramid level, trail stop, unrealised P&L | `_render_positions_table(state)`; UI-SPEC locks 8-column layout; "Current" column reads `state['signals'][key]['last_close']` (B-1 retrofit field); trail-stop + unrealised-pnl math re-implemented inline (no `sizing_engine` import per D-01) |
| DASH-06 | Last 20 closed trades rendered as HTML table | `_render_trades_table(state)`; slice pattern `state['trade_log'][-20:][::-1]` for newest-first; 7 columns per UI-SPEC; authoritative 12-field trade dict from `main._closed_trade_to_record` + `state_manager.record_trade` (D-20 appends `net_pnl`) |
| DASH-07 | Key stats block shows total return, Sharpe, max drawdown, win rate | `_compute_total_return`, `_compute_sharpe`, `_compute_max_drawdown`, `_compute_win_rate`; stdlib-only via `statistics.mean/stdev` + `math.log/sqrt` (NOT numpy); edge guards for `<30` equities (Sharpe), empty history (max DD), empty trade_log (win rate) |
| DASH-08 | "Last updated" timestamp in AWST | `_fmt_last_updated(now)` applies `now.astimezone(pytz.timezone('Australia/Perth')).strftime('%Y-%m-%d %H:%M AWST')`; asserts `now.tzinfo is not None` (catches naive-datetime fixture bugs) |
| DASH-09 | Visual theme matches backtest aesthetic (same palette as email) | Palette constants shared via `system_params` read by dashboard (and Phase 6 notifier) - documented for Phase 6 reuse in UI-SPEC §Phase 6 Reuse Notes; 12-colour palette locked in UI-SPEC §Color |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Style:** 2-space indent, single quotes, snake_case for functions, UPPER_SNAKE for constants.
- **Log prefix:** Phase 5 introduces `[Dashboard]` (new prefix per CONTEXT <prior_decisions>).
- **Architecture:** Hexagonal-lite. `dashboard.py` is a NEW I/O hex (analog of `state_manager.py` + `data_fetcher.py`). Strictly forbidden to import `signal_engine`, `sizing_engine`, `data_fetcher`, `main`, `notifier`, `numpy`, or `pandas` (enforced by AST blocklist test extension).
- **Atomic writes:** `state.json` writes use tempfile + fsync + `os.replace`; dashboard writes mirror this pattern.
- **Never crash on cosmetic failure:** Dashboard render failures wrap in `try/except Exception: logger.warning(...)` in main.py - state is already saved, email still goes out.
- **Timezone:** `pytz.timezone('Australia/Perth')` for all user-facing timestamps.
- **Instrument keys:** `SPI200`, `AUDUSD` (state.json keys); YF tickers `^AXJO` / `AUDUSD=X` do not appear in the dashboard (display names come from UI-SPEC `_INSTRUMENT_DISPLAY_NAMES` dict).
- **GSD Workflow Enforcement:** Start all edits through a GSD command; no direct file edits outside a GSD workflow.

## Architectural Responsibility Map

Dashboard is a single-tier static-HTML render - there is no browser / server / API split. The architectural concern is the hexagonal-lite boundary between the I/O hex (`dashboard.py`) and pure-math neighbours, plus the single external dependency (Chart.js CDN).

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| HTML rendering (blocks, shell, tables) | I/O hex (dashboard.py) | — | String construction + escape is pure Python; no I/O until the final atomic write. The "I/O" classification is structural (owns the file write) |
| Inline CSS | I/O hex (dashboard.py) | — | Module-level constant `_INLINE_CSS` interpolated with palette tokens at import; no external stylesheet per PROJECT.md |
| Chart instantiation (JavaScript) | Browser (client-side) | I/O hex emits the `<script>` | Chart.js runs in the user's browser; Python emits the code + the serialised data payload |
| Stats computation (Sharpe, DD, win rate, total return) | Pure math (inside dashboard.py) | — | Stats helpers take plain dicts/lists, return plain floats/strings; stdlib-only (`statistics`, `math`) - NOT imported from `sizing_engine` per D-01 hex fence |
| Unrealised P&L + trail-stop display math | Pure math (inside dashboard.py) | — | UI-SPEC Positions table Derived render-time calculations re-implements the `compute_unrealised_pnl` + `get_trailing_stop` formulas inline; does NOT import `sizing_engine` per D-01 |
| Atomic file write | I/O hex (dashboard.py) | filesystem (POSIX / Windows) | Mirrors `state_manager._atomic_write` pattern: tempfile + `tmp.flush()` + `os.fsync(tmp.fileno())` + `os.replace` + (POSIX only) parent-dir fsync |
| State read | State hex (state_manager.py) | I/O hex consumes via `load_state` | Dashboard CLI path calls `state_manager.load_state()`; production path gets state dict handed in by main.py post-save |
| Orchestrator integration | Adapter (main.py) | I/O hex (dashboard.py) | main.py imports `dashboard` (sibling hex like state_manager); new import is legal for main.py - FORBIDDEN_MODULES_MAIN is `{numpy, yfinance, requests, pandas}` only |

## Standard Stack

### Core (already in requirements.txt - no new deps)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.11 | Language | Matches project baseline (`.python-version` 3.11.8); dict-insertion-order determinism + `zoneinfo` in stdlib |
| `html` | stdlib | XSS escape via `html.escape(value, quote=True)` | D-15 locks stdlib; `markupsafe` explicitly rejected in CONTEXT downstream_notes |
| `json` | stdlib | Serialise equity-history payload into inline `<script>` | Stable key-ordering with `sort_keys=True`; built-in handles floats without numpy surface |
| `statistics` | stdlib | `mean`, `stdev` for Sharpe (D-07) | No numpy import possible per D-01; `stdev` matches numpy `std(ddof=1)` behaviour [VERIFIED in this session: stdev of 5-sample series = 286.36] |
| `math` | stdlib | `log`, `sqrt` for Sharpe daily-log-returns + annualisation | Raises `ValueError` on zero/negative input [VERIFIED in this session]; NaN-safe via `math.isnan` / `math.isfinite` |
| `tempfile` | stdlib | `NamedTemporaryFile(dir=parent)` for atomic write | Mirrors `state_manager._atomic_write` |
| `pathlib` | stdlib | `Path` for out_path | Already project convention |
| `datetime` | stdlib | Freezer-test target + `now` arg default | Already project convention |
| `pytz` | 2024.x (not pinned; transitive via pandas pin `2.3.3`) | AWST conversion | D-01 explicitly allows; state_manager uses stdlib `zoneinfo` but dashboard uses pytz because CONTEXT D-01 locks it and UI-SPEC §Header locks the `pytz.timezone('Australia/Perth')` call site [VERIFIED: pytz present as transitive via pandas -> dateutil/pytz]. Note: if a future hardening step wants stdlib-only, `zoneinfo.ZoneInfo('Australia/Perth')` drops in 1:1. |
| `pytest-freezer` | 0.4.9 (already pinned) | Lock `now` in golden-snapshot test | Used by Phase 4; no new dep |

### External (single asset, pinned CDN)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Chart.js UMD | 4.4.6 | Equity curve line chart | PROJECT.md + CONTEXT D-12 locked; jsdelivr CDN with SRI SHA-384 pinning |

### Installation

No pip install required. No new package added to requirements.txt. The only external asset is Chart.js loaded at runtime in the browser.

### Version verification

```bash
# Verify Chart.js UMD version + SRI (run BEFORE committing _CHARTJS_SRI constant):
curl -sL https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.js | openssl dgst -sha384 -binary | base64
# Expected output: MH1axGwz/uQzfIcjFdjEfsM0xlf5mmWfAwwggaOh5IPFvgKFGbJ2PZ4VBbgSYBQN
```

[VERIFIED 2026-04-21: both `https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.js` and `https://unpkg.com/chart.js@4.4.6/dist/chart.umd.js` return a BYTE-IDENTICAL 205,615-byte file, hash `MH1axGwz/uQzfIcjFdjEfsM0xlf5mmWfAwwggaOh5IPFvgKFGbJ2PZ4VBbgSYBQN`. The placeholder in CONTEXT D-12 (`sha384-C5GVzRkc2bvIeI4A/1dpJpBdFfJKydDPTGdcOKtKjIaCfHBqBjqfGyMEWFi3ExWn`) is STALE. Planner must commit the verified hash.]

jsdelivr response headers confirm the asset is immutable and version-locked: `cache-control: public, max-age=31536000, s-maxage=31536000, immutable`, `x-jsd-version: 4.4.6`, `x-jsd-version-type: version`. Safe to pin.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| jsdelivr CDN | unpkg.com CDN | unpkg returns byte-identical file [VERIFIED]; jsdelivr preferred because it's in PROJECT.md + CONTEXT D-12; both carry the same SRI hash so if jsdelivr goes down the operator can flip to unpkg with zero hash change. Recommendation: stick with jsdelivr as primary; document unpkg as fallback comment in `dashboard.py` |
| stdlib `zoneinfo` | pytz | CONTEXT D-01 explicitly locks pytz; state_manager uses zoneinfo for internal stamping but dashboard re-reads pytz per UI-SPEC `_fmt_last_updated` call site |
| markupsafe.escape | `html.escape(value, quote=True)` | D-15 locks stdlib; zero-dep stance |
| Jinja2 | pure Python block-builder | CONTEXT <deferred>: Jinja2 rejected; would need PROJECT.md stack amendment |
| numpy for stats | `statistics` + `math` stdlib | D-01 forbids numpy import in dashboard.py (hex fence) |

## Architecture Patterns

### System Architecture Diagram

```
      ┌───────────────────────────┐
      │  main.run_daily_check()   │ (Phase 4)
      │                           │
      │  state_manager.save_state │ ◀── state.json atomic write
      │         │                 │
      │         │ (state dict)    │
      │         ▼                 │
      │  try: dashboard           │
      │    .render_dashboard(     │
      │      state, 'dashboard    │
      │      .html', now=run_date)│
      │  except Exception: log    │
      └─────────┬─────────────────┘
                │ state (plain dict)
                ▼
      ┌───────────────────────────────────────────┐
      │  dashboard.render_dashboard               │
      │                                           │
      │  1. body = ''                             │
      │  2. body += _render_header(state, now)    │  (UI-SPEC Header)
      │  3. body += _render_signal_cards(state)   │  (DASH-03)
      │  4. body += _render_equity_chart_         │  (DASH-04; inline <script>
      │             container(state)              │      + Chart.js CDN load)
      │  5. body += _render_positions_table(state)│  (DASH-05)
      │  6. body += _render_trades_table(state)   │  (DASH-06)
      │  7. body += _render_key_stats(state)      │  (DASH-07)
      │  8. body += _render_footer()              │  (disclaimer)
      │  9. html = _render_html_shell(body, …)    │  (<!DOCTYPE> + <head>
      │                                           │      + inline CSS
      │                                           │      + Chart.js <script>)
      │ 10. _atomic_write(html, out_path)         │  (tempfile + fsync
      │                                           │      + os.replace)
      │                                           │
      │  Every state-derived string passes        │
      │  through html.escape(v, quote=True)       │  (D-15 XSS guard)
      │  Every JSON payload injected into the     │
      │  inline <script> passes through           │  (</script> injection guard)
      │    json.dumps(…).replace('</', '<\\/')   │
      └───────────────┬───────────────────────────┘
                      │ dashboard.html (atomic file write)
                      ▼
      ┌───────────────────────────────────────────┐
      │  Operator's browser                       │
      │                                           │
      │  1. Parses inline CSS (dark theme)        │
      │  2. Loads Chart.js UMD from jsdelivr CDN  │  (SRI check; browser
      │     <script integrity="sha384-…">         │      refuses on hash
      │  3. Executes inline <script>              │      mismatch)
      │     new Chart(canvas, {                   │
      │       data: {labels:[…], datasets:[…]},   │
      │       options: {…}                        │  (D-11 category axis +
      │     })                                    │      maintainAspectRatio
      │                                           │      false + no legend)
      │  4. User sees: header, signal cards,      │
      │     equity curve, positions table,        │
      │     trades table, stats tiles, footer     │
      └───────────────────────────────────────────┘
```

Data flow highlights:
- Dashboard is one-shot: state dict in -> HTML string out -> single atomic write.
- The Chart.js load is the ONE external dependency (SRI-locked).
- Browser-side execution is purely presentational; no AJAX, no hydration, no client state.

### Recommended Project Structure (files introduced / modified in Phase 5)

```
repo-root/
├── dashboard.py                        # NEW: I/O hex; 7 render blocks + 5 formatters + 4 stats helpers + render_dashboard + _atomic_write_html
├── dashboard.html                      # NEW: written each run; gitignored
├── .gitignore                          # MODIFIED: add 'dashboard.html'
├── main.py                             # MODIFIED: lines 514-519 retrofit (B-1 last_close) + post-save_state render_dashboard call (D-06)
├── tests/
│   ├── test_dashboard.py               # NEW: 6 classes (TestStatsMath, TestFormatters, TestRenderBlocks, TestEmptyState, TestGoldenSnapshot, TestAtomicWrite)
│   ├── test_signal_engine.py           # MODIFIED: TestDeterminism appends DASHBOARD_PATH + FORBIDDEN_MODULES_DASHBOARD + test_dashboard_no_forbidden_imports
│   ├── test_main.py                    # MODIFIED: test_orchestrator_reads_both_int_and_dict_signal_shape asserts 'last_close' in signals dict (B-1)
│   ├── regenerate_dashboard_golden.py  # NEW: offline script mirrors regenerate_goldens.py — loads sample_state.json + renders dashboard.html with a frozen clock
│   └── fixtures/
│       └── dashboard/
│           ├── sample_state.json       # NEW: mid-campaign state (both instruments have positions + signals + ~50 equity points + 5 closed trades + 1 warning)
│           ├── empty_state.json        # NEW: Phase 3 reset_state() output as JSON - for TestEmptyState
│           └── golden.html             # NEW: committed reference rendering of sample_state.json at frozen clock 2026-04-22 09:00 AWST
```

### Pattern 1: Block-builder rendering (D-02)

**What:** Each logical HTML region is a pure function from state dict to HTML string. The shell function wraps them.
**When to use:** Static render with no interactivity, one viewer, zero build step.
**Source:** CONTEXT D-02 locks; derived from `state_manager.py`'s per-concern-public-function pattern.

```python
# Source: CONTEXT D-02 + UI-SPEC §Component Hierarchy
def _render_signal_cards(state: dict) -> str:
  '''Render two signal cards (SPI200 + AUDUSD). UI-SPEC §Signal cards.'''
  cards: list[str] = []
  for state_key, display_name in _INSTRUMENT_DISPLAY_NAMES.items():
    sig_entry = state.get('signals', {}).get(state_key)
    if not isinstance(sig_entry, dict):
      # Empty state (D-13): signal label em-dash in gold
      cards.append(_render_empty_signal_card(display_name))
      continue
    signal = sig_entry.get('signal', 0)
    signal_as_of = sig_entry.get('signal_as_of', 'never')
    scalars = sig_entry.get('last_scalars', {})
    cards.append(_render_populated_signal_card(
      display_name=display_name,
      signal=signal,
      signal_as_of=signal_as_of,
      scalars=scalars,
    ))
  return (
    '<section aria-labelledby="heading-signals">\n'
    '  <h2 id="heading-signals">Signal Status</h2>\n'
    '  <div class="cards-row">\n'
    + '\n'.join(cards) + '\n'
    '  </div>\n'
    '</section>\n'
  )

def render_dashboard(
  state: dict,
  out_path: Path = Path('dashboard.html'),
  now: datetime | None = None,
) -> None:
  '''Public API per CONTEXT D-01. Writes atomically; never mutates state.'''
  if now is None:
    now = datetime.now(pytz.timezone('Australia/Perth'))
  body = (
    _render_header(state, now)
    + _render_signal_cards(state)
    + _render_equity_chart_container(state)
    + _render_positions_table(state)
    + _render_trades_table(state)
    + _render_key_stats(state)
    + _render_footer()
  )
  html_str = _render_html_shell(body)
  _atomic_write_html(html_str, out_path)
```

### Pattern 2: Inline `<script>` + CDN `<script>` separation (D-11, D-12)

**What:** The Chart.js library loads via `<script src=...>` with SRI; the instantiation runs as a separate inline `<script>` in the body, after the `<canvas>`.
**When to use:** No build step + no external JS file + no CSP header to configure.
**Source:** Chart.js 4.x documentation; D-11 + D-12.

```python
# Source: CONTEXT D-11 + D-12, verified Chart.js 4.4.6 docs
_CHARTJS_URL = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.js'
_CHARTJS_SRI = 'sha384-MH1axGwz/uQzfIcjFdjEfsM0xlf5mmWfAwwggaOh5IPFvgKFGbJ2PZ4VBbgSYBQN'

def _render_html_shell(body: str) -> str:
  '''Full HTML document. Chart.js loaded in <head> with SRI; inline <script>
  runs in the body next to the <canvas>.'''
  return (
    '<!DOCTYPE html>\n'
    '<html lang="en">\n'
    '<head>\n'
    '  <meta charset="utf-8">\n'
    '  <title>Trading Signals — Dashboard</title>\n'
    f'  <style>{_INLINE_CSS}</style>\n'
    f'  <script src="{_CHARTJS_URL}" '
    f'integrity="{_CHARTJS_SRI}" crossorigin="anonymous"></script>\n'
    '</head>\n'
    '<body>\n'
    f'{body}'
    '</body>\n'
    '</html>\n'
  )

def _render_equity_chart_container(state: dict) -> str:
  equity_history = state.get('equity_history', [])
  if not equity_history:
    # D-13 empty state
    return (
      '<section aria-labelledby="heading-equity">\n'
      '  <h2 id="heading-equity">Equity Curve</h2>\n'
      '  <div class="chart-container empty-state">'
      'No equity history yet — first full run needed'
      '</div>\n'
      '</section>\n'
    )
  # Build labels + data as plain Python lists, then JSON-serialise.
  labels = [row['date'] for row in equity_history]
  data = [float(row['equity']) for row in equity_history]
  # JSON-in-JS injection safety: json.dumps emits '</script>' verbatim inside
  # string values; we need to escape the forward slash so the HTML parser does
  # NOT see a </script> closing tag mid-string.
  # html.escape does NOT fix this — it only handles < > & ' " for HTML attrs.
  payload = json.dumps(
    {'labels': labels, 'data': data},
    ensure_ascii=False,
  ).replace('</', '<\\/')
  return (
    '<section aria-labelledby="heading-equity">\n'
    '  <h2 id="heading-equity">Equity Curve</h2>\n'
    '  <div class="chart-container">\n'
    '    <canvas id="equityChart" '
    'aria-label="Account equity line chart over time" role="img"></canvas>\n'
    '  </div>\n'
    '  <script>\n'
    f'    (function() {{\n'
    f'      const payload = {payload};\n'
    '      new Chart(document.getElementById("equityChart"), {\n'
    '        type: "line",\n'
    '        data: {\n'
    '          labels: payload.labels,\n'
    '          datasets: [{\n'
    '            label: "Account equity",\n'
    f'            data: payload.data,\n'
    f'            borderColor: "{_COLOR_LONG}",\n'
    f'            backgroundColor: "{_COLOR_LONG}",\n'
    '            fill: false,\n'
    '            tension: 0.1,\n'
    '            borderWidth: 2,\n'
    '            pointRadius: 0,\n'
    '            pointHoverRadius: 4\n'
    '          }]\n'
    '        },\n'
    '        options: {\n'
    '          scales: {\n'
    f'            x: {{ type: "category", ticks: {{ color: "{_COLOR_TEXT_MUTED}", maxTicksLimit: 10 }}, '
    f'grid: {{ color: "{_COLOR_BORDER}" }} }},\n'
    f'            y: {{ ticks: {{ color: "{_COLOR_TEXT_MUTED}", callback: (v) => "$" + v.toLocaleString() }}, '
    f'grid: {{ color: "{_COLOR_BORDER}" }} }}\n'
    '          },\n'
    '          plugins: {\n'
    '            legend: { display: false },\n'
    '            tooltip: { callbacks: { label: (ctx) => "$" + ctx.parsed.y.toLocaleString() } }\n'
    '          },\n'
    '          maintainAspectRatio: false,\n'
    '          responsive: true\n'
    '        }\n'
    '      });\n'
    '    })();\n'
    '  </script>\n'
    '</section>\n'
  )
```

### Pattern 3: Atomic write mirror (D-03 + state_manager._atomic_write precedent)

**What:** Identical durability sequence to `state_manager._atomic_write`: tempfile in same directory + write + flush + fsync(fd) + close + os.replace + parent-dir fsync (POSIX only).
**When to use:** Every file write that overwrites an existing operator-visible file.
**Source:** `state_manager.py:88-133`, Phase 3 D-17 (post-replace dir fsync).

```python
# Source: state_manager.py _atomic_write (Phase 3 D-17 corrected ordering)
def _atomic_write_html(data: str, path: Path) -> None:
  '''Mirror state_manager._atomic_write. Private helper; same fsync discipline.'''
  parent = path.parent
  tmp_path_str: str | None = None
  try:
    with tempfile.NamedTemporaryFile(
      dir=parent, delete=False, mode='w', suffix='.tmp', encoding='utf-8',
    ) as tmp:
      tmp_path_str = tmp.name
      tmp.write(data)
      tmp.flush()
      os.fsync(tmp.fileno())
    os.replace(tmp_path_str, path)
    if os.name == 'posix':
      dir_fd = os.open(str(parent), os.O_RDONLY)
      try:
        os.fsync(dir_fd)
      finally:
        os.close(dir_fd)
    tmp_path_str = None
  finally:
    if tmp_path_str is not None:
      try:
        os.unlink(tmp_path_str)
      except FileNotFoundError:
        pass
```

### Pattern 4: Escape at leaf interpolation (D-15)

**What:** Every string value sourced from `state` passes through `html.escape(value, quote=True)` at the point it meets the HTML string - NOT at block-assembly time. Numbers are formatted into safe strings first via `_fmt_currency` etc., so no double-escape.
**When to use:** Any state-derived text that lands inside HTML.
**Source:** D-15; Python stdlib docs for `html.escape`.

```python
# Source: D-15 + Python html stdlib docs
import html

def _render_instrument_chip(state_key: str) -> str:
  '''Render the instrument display name with XSS escape belt + braces.
  state_key is NEVER user-controlled (comes from SYMBOL_MAP), but the
  escape is cheap and defends against future multi-tenant drift.'''
  display = _INSTRUMENT_DISPLAY_NAMES.get(state_key, state_key)
  return f'<span class="chip">{html.escape(display, quote=True)}</span>'
```

[VERIFIED in this session] `html.escape('</script><script>alert(1)</script>', quote=True)` returns `'&lt;/script&gt;&lt;script&gt;alert(1)&lt;/script&gt;'` - safe for HTML context but NOT safe for JS-string context (see Pattern 2 for the JSON-in-JS fix).

### Anti-Patterns to Avoid

- **Interpolating state into an inline `<script>` via `html.escape`** - it does not escape `</`; you get `</script>` mid-string and the browser closes the script block early. Always use `json.dumps(...).replace('</', '<\\/')` for `<script>` context.
- **Using `document.write` for the chart instantiation** - breaks if the script loads after DOMContentLoaded. Use the IIFE pattern (`(function() { ... })();`) after the `<canvas>` is already in the DOM.
- **Setting canvas `width` / `height` attributes** - Chart.js `responsive: true` + `maintainAspectRatio: false` owns sizing; the parent `<div>` needs `position: relative; height: 320px`. UI-SPEC §Chart Component locks this.
- **Calling `state_manager.save_state` from `dashboard.py`** - violates D-05. Dashboard is read-only over state.
- **Importing `sizing_engine.compute_unrealised_pnl`** - violates D-01 hex fence. Re-implement inline per UI-SPEC §Positions table Derived render-time calculations; one unit test locks the math against a known case.
- **Using `str.format` / `%` formatting for the inline CSS** - palette tokens have literal `#` characters that can interact oddly with `%` formatting; stick with f-string at module-load time.
- **Regenerating the golden HTML "in-test" instead of via a separate script** - hides diffs from the PR reviewer. Mirror the Phase 1 `regenerate_goldens.py` pattern: a separate script the operator runs MANUALLY, and `TestGoldenSnapshot` diffs the byte-level output against the committed file.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTML-entity escape | Custom `.replace('<', '&lt;')` chain | `html.escape(value, quote=True)` | Stdlib handles `<`, `>`, `&`, `"`, `'`; hand-rolling misses edge cases (numeric entities, attribute-context vs element-context) |
| JSON serialisation for the chart payload | Hand-rolled JS-string builder | `json.dumps(data, ensure_ascii=False)` + `.replace('</', '<\\/')` | Python's json is bit-stable with `sort_keys=True`; hand-rolled misses float-precision + unicode edge cases |
| Atomic file write | Direct `open('w').write()` | Tempfile + fsync + `os.replace` (mirror `state_manager._atomic_write`) | Crash mid-write leaves half-written `dashboard.html`; `os.replace` is atomic POSIX-wide + Windows-wide (Python 3.3+) |
| Sharpe ratio / stdev | Manual `sum((x - mean)**2)` loop | `statistics.stdev` | Matches numpy `std(ddof=1)`; raises `StatisticsError` on <2 samples - catchable; [VERIFIED stdev of [100000, 100500, 99800, 100200, 100400] == 286.36] |
| Annualised log-return math | Hand-rolled Taylor expansion | `math.log` + `math.sqrt` | Correct handling of NaN / zero / negative inputs; `math.log(0)` raises `ValueError` catchably; [VERIFIED in this session] |
| Chart.js date-axis date adapter | Installing `chartjs-adapter-date-fns` | Category x-axis with pre-formatted ISO-date strings (D-11) | Adds a second external asset to the SRI-locked list; ISO strings sort correctly alphabetically so category axis works transparently |
| HTML-escape for `<script>` JS-string content | `html.escape` (which doesn't work here) | `json.dumps` + `.replace('</', '<\\/')` | The `</script>` injection is an HTML-parser-boundary concern, not an HTML-entity concern; `html.escape` escapes the `<` to `&lt;` which is WRONG inside JS-string literals |
| AWST timezone arithmetic | Manual `timedelta(hours=8)` | `pytz.timezone('Australia/Perth')` | Perth has no DST so manual offset works today, but `pytz` future-proofs against any TZ-data update; also UI-SPEC `_fmt_last_updated` asserts `now.tzinfo is not None` which only works with real tz objects |

**Key insight:** Dashboard rendering looks "just string concatenation" but every category above (escape, atomic write, stats math, JSON-in-JS) has a known-pitfall path. Stay on the stdlib + state_manager precedents; skip custom implementations.

## Runtime State Inventory

Not applicable — Phase 5 is a greenfield render module, not a rename / refactor / migration. No existing runtime state is renamed or moved.

**The one minor data-shape change (B-1 retrofit) is documented as an additive field in Step 5 below; no migration, no schema bump, backward-compat via `.get('last_close')`.**

## Common Pitfalls

### Pitfall 1: `</script>` injection via JSON-in-JS

**What goes wrong:** Python `json.dumps({'label': '</script><img src=x onerror=alert(1)>'})` emits the literal string `"</script>..."` inside the `<script>` block; the browser's HTML parser sees `</script>` and closes the script block early, then interprets the rest of the payload as HTML - which gets parsed and executed.

**Why it happens:** `html.escape` escapes `<` to `&lt;` which is WRONG inside JS-string literals (you'd break JSON parsing). JSON encoding alone does not escape forward slash. The HTML parser's "script end tag" detection is done BEFORE the JavaScript parser sees the string.

**How to avoid:** After `json.dumps(...)`, call `.replace('</', '<\\/')`. The backslash-slash is valid inside JS strings and prevents the HTML parser from seeing `</script>`. [VERIFIED in this session: `json.dumps({'x': '</script>'}).replace('</', r'<\/')` produces `{"x": "<\/script>"}` which is safe.]

**Warning signs:** In the rendered `dashboard.html`, grep for the literal substring `</` inside any `<script>` block. The only matches should be `<\\/...` (escaped) or nothing. Add a golden-snapshot assertion that `'</script>' not in html[head_end:]` - any unescaped occurrence in the body is a bug.

### Pitfall 2: Golden snapshot byte drift from dict insertion order

**What goes wrong:** Python 3.7+ dicts preserve insertion order. `json.dumps({'b': 2, 'a': 1})` produces `{"b": 2, "a": 1}`, but `json.dumps({'a': 1, 'b': 2})` produces `{"a": 1, "b": 2}`. If the render code builds dicts in a slightly different order on different code paths, the golden snapshot drifts.

**Why it happens:** `state['signals'][state_key]` is a dict that was built in `main.py` with keys in a specific order (`signal`, `signal_as_of`, `as_of_run`, `last_scalars`, `last_close`). The dashboard reads these fields; if the render code iterates via `.items()` the order matches the write order - but if a future code path re-constructs the dict, ordering drifts.

**How to avoid:** For any JSON serialised into the HTML body (chart payload), pass `sort_keys=True` to `json.dumps`. [VERIFIED in this session: `json.dumps({'a': 1}, sort_keys=True) == json.dumps({'b': 2}, sort_keys=True)` is False but comparing `{'b':2,'a':1}` vs `{'a':1,'b':2}` under sort_keys yields `True`.] For block-builder output strings (no JSON), the deterministic-iteration contract is "iterate `_INSTRUMENT_DISPLAY_NAMES` in declaration order" - and `_INSTRUMENT_DISPLAY_NAMES` is a module-level constant so its order is fixed at import.

**Warning signs:** Running `python tests/regenerate_dashboard_golden.py` twice in a row produces non-zero git diff on `tests/fixtures/dashboard/golden.html`.

### Pitfall 3: `statistics.stdev` raises on <2 samples

**What goes wrong:** `statistics.stdev([100.0])` raises `statistics.StatisticsError: variance requires at least two data points`. Sharpe computation on a 1-point equity history crashes.

**Why it happens:** stdev requires at least 2 samples (ddof=1); D-07 already guards with `len(equities) < 30` returning `—`, but the guard is on `len(equities)` not on `len(log_returns)`. If `len(equities) == 30` then `len(log_returns) == 29` which is still fine, but any off-by-one could crash.

**How to avoid:** Compute log_returns FIRST, then guard `if len(log_returns) < 2: return '—'`. [VERIFIED in this session.] Also guard `if std_r == 0: return '—'` to avoid division-by-zero when all equities are identical (a pathological but real scenario on a long FLAT streak).

**Warning signs:** `TestStatsMath.test_sharpe_single_point_returns_dash` + `test_sharpe_flat_equity_returns_dash` in the plan should both pass.

### Pitfall 4: `math.log` of zero or negative account

**What goes wrong:** `math.log(0)` raises `ValueError: math domain error`; same for negative numbers. If the account ever goes to zero or negative (e.g., catastrophic loss), Sharpe computation crashes.

**Why it happens:** Daily log return is `log(eq[t] / eq[t-1])`. If `eq[t-1] == 0` you get division-by-zero (raises first); if `eq[t] <= 0` you get log-of-non-positive.

**How to avoid:** Before the log-return loop, guard: `if any(e <= 0 for e in equities): return '—'`. This is also the right semantic - a negative/zero equity run is a blow-up, Sharpe is undefined. [VERIFIED in this session: `math.log(0)` and `math.log(-5)` both raise `ValueError`.]

**Warning signs:** Fuzzing the Sharpe helper with equities `[100_000, 50_000, 0, -1_000]` should return `—` not crash.

### Pitfall 5: `maintainAspectRatio: false` requires fixed-height parent

**What goes wrong:** Chart.js with `maintainAspectRatio: false` + `responsive: true` expects the parent `<div>` to have a measurable height. If the parent has `height: auto` the canvas collapses to 0px and the chart is invisible (but the SRI load succeeds and there are no console errors).

**Why it happens:** Chart.js sizes the canvas to match the parent's box-model height; `height: auto` collapses to 0 because there's no content yet.

**How to avoid:** UI-SPEC §Chart Component already locks `Container size (height): 320px (fixed) on all viewports` and `position: relative; height: 320px` on the parent. Planner must emit exactly that CSS. Document in `_INLINE_CSS` with a comment explaining why.

**Warning signs:** Open `dashboard.html` in a local browser; if the chart area shows a 1100px-wide, 0px-tall band where the chart should be, the parent height is wrong.

### Pitfall 6: `html.escape` does not escape forward slash

**What goes wrong:** `html.escape('<a href="/foo">', quote=True)` returns `&lt;a href=&quot;/foo&quot;&gt;` - note the `/` is preserved. This is correct for HTML but wrong inside a `<script>` block where `</...>` is an HTML-parser end-of-script signal.

**Why it happens:** `html.escape` is designed for HTML-element and HTML-attribute contexts; JS-string context needs a different escape set.

**How to avoid:** Separate the escape strategy by context:
- HTML text + attributes -> `html.escape(value, quote=True)`
- JS string inside `<script>` -> `json.dumps(value)` (which handles `"`, `\`, control chars) + `.replace('</', '<\\/')` (which handles the HTML-parser end-of-script escape)

This is covered by the Pattern 2 code above; call it out in the plan's "dashboard.py authoring checklist" so the executor doesn't conflate the two.

**Warning signs:** `TestRenderBlocks.test_chart_payload_escapes_script_close` in the plan asserts that a trade-log entry with `'</script>'` in any string field renders as `<\/script>` in the chart payload - and separately as `&lt;/script&gt;` inside any HTML text rendering that value.

### Pitfall 7: Cross-platform atomic write (Windows semantics)

**What goes wrong:** On POSIX systems, `os.replace` is atomic and `os.fsync(dir_fd)` makes the rename durable. On Windows, `os.replace` is atomic (Python 3.3+) but `os.open(dir, os.O_RDONLY)` + `os.fsync` on a directory fd is not supported - `os.open` on a directory raises `PermissionError` on Windows.

**Why it happens:** Windows does not expose directory file descriptors the same way POSIX does.

**How to avoid:** Mirror `state_manager._atomic_write` exactly - guard the parent-dir fsync with `if os.name == 'posix':`. This code already works (Phase 3 shipped). [VERIFIED at state_manager.py:121-126.]

**Warning signs:** Plan test `TestAtomicWrite.test_atomic_write_cross_platform` should run the same code path on the primary CI (macOS/Linux); for Windows verification the operator runs locally on Windows, which is documented as a manual check in VALIDATION.md.

### Pitfall 8: Forgetting to update `.gitignore` for `dashboard.html`

**What goes wrong:** `dashboard.html` gets committed by accident on the first run; operator sees it in `git status` and `git add .` - the repo is polluted with a build artefact.

**Why it happens:** D-03 says `gitignored`; the planner forgets to add to `.gitignore` in Wave 0.

**How to avoid:** Wave 0 scaffold task EXPLICITLY includes an edit to `.gitignore` adding `dashboard.html`. A grep verifies: `grep -F 'dashboard.html' .gitignore` must return non-empty.

**Warning signs:** `git status` after a `python main.py --once` run shows `dashboard.html` as untracked.

### Pitfall 9: Golden-HTML byte drift from naive-datetime `now`

**What goes wrong:** `render_dashboard(state, path, now=datetime(2026, 4, 22, 9, 0))` (no tzinfo) silently produces a different string than `render_dashboard(state, path, now=datetime(2026, 4, 22, 9, 0, tzinfo=pytz.timezone('Australia/Perth')))` because `now.astimezone(pytz.timezone('Australia/Perth'))` on a naive datetime assumes system-local time. Tests that pass in CI (UTC) fail on the operator's laptop (AWST) with golden drift.

**Why it happens:** Naive datetime arithmetic depends on system timezone.

**How to avoid:** UI-SPEC §Format Helper Contracts locks: `_fmt_last_updated(now)` raises `ValueError` on naive datetime. The planner's TestFormatters class should include `test_fmt_last_updated_rejects_naive_datetime`. Regenerator script must instantiate `now = datetime(2026, 4, 22, 9, 0, tzinfo=pytz.timezone('Australia/Perth'))`.

**Warning signs:** `test_golden_snapshot_matches_committed` fails with a 1-character diff in the "Last updated" timestamp.

## Code Examples

### Stats helpers (stdlib-only, hex-safe)

```python
# Source: CONTEXT D-07 / D-08 / D-09 / D-10 + stdlib docs + this-session verification
import math
import statistics

def _compute_sharpe(state: dict) -> str:
  '''D-07: daily log-returns, rf=0, annualised × √252. Returns em-dash if <30 samples.'''
  equities = [row['equity'] for row in state.get('equity_history', [])]
  if len(equities) < 30:
    return '—'
  if any(e <= 0 for e in equities):  # Pitfall 4 guard
    return '—'
  log_returns = [math.log(equities[i] / equities[i - 1]) for i in range(1, len(equities))]
  if len(log_returns) < 2:  # Pitfall 3 guard (belt + braces)
    return '—'
  mean_r = statistics.mean(log_returns)
  std_r = statistics.stdev(log_returns)
  if std_r == 0:  # degenerate flat streak
    return '—'
  sharpe = (mean_r / std_r) * math.sqrt(252)
  return f'{sharpe:.2f}'


def _compute_max_drawdown(state: dict) -> str:
  '''D-08: rolling peak-to-trough %.'''
  equities = [row['equity'] for row in state.get('equity_history', [])]
  if not equities:
    return '—'
  running_max = equities[0]
  max_dd = 0.0
  for eq in equities:
    running_max = max(running_max, eq)
    if running_max == 0:  # guard divide-by-zero on degenerate fixture
      continue
    dd = (eq - running_max) / running_max
    max_dd = min(max_dd, dd)
  return f'{max_dd * 100:.1f}%'


def _compute_win_rate(state: dict) -> str:
  '''D-09: closed trades with gross_pnl > 0 / total.'''
  closed = state.get('trade_log', [])
  if not closed:
    return '—'
  wins = sum(1 for t in closed if t.get('gross_pnl', 0) > 0)
  return f'{wins / len(closed) * 100:.1f}%'


def _compute_total_return(state: dict) -> str:
  '''D-10: (current_equity - INITIAL_ACCOUNT) / INITIAL_ACCOUNT * 100.'''
  eq_hist = state.get('equity_history', [])
  if eq_hist:
    current = eq_hist[-1].get('equity', state.get('account', INITIAL_ACCOUNT))
  else:
    current = state.get('account', INITIAL_ACCOUNT)
  total_return = (current - INITIAL_ACCOUNT) / INITIAL_ACCOUNT
  return f'{total_return * 100:+.1f}%'
```

### Numeric formatters (UI-SPEC §Format Helper Contracts)

```python
# Source: UI-SPEC §Format Helper Contracts + CONTEXT D-16
import html
import pytz
from datetime import datetime

# Palette constants (UI-SPEC §Color)
_COLOR_LONG = '#22c55e'
_COLOR_SHORT = '#ef4444'
_COLOR_TEXT_MUTED = '#cbd5e1'


def _fmt_currency(value: float) -> str:
  '''$1,234.56 / -$567.89 / $0.00. Always 2dp. No K/M/B suffix.'''
  if value < 0:
    return f'-${-value:,.2f}'
  return f'${value:,.2f}'


def _fmt_percent_signed(fraction: float) -> str:
  '''+5.3% / -12.5% / +0.0%. Input is a fraction (0.053 -> +5.3%).'''
  return f'{fraction * 100:+.1f}%'


def _fmt_percent_unsigned(fraction: float) -> str:
  '''58.3% / 12.5%. Input is a fraction.'''
  return f'{fraction * 100:.1f}%'


def _fmt_pnl_with_colour(value: float) -> str:
  '''Safe HTML span: LONG-green for positive, SHORT-red for negative, muted for zero.'''
  if value > 0:
    colour = _COLOR_LONG
    body = _fmt_currency(value)
    # "+" prefix for positive-value currency (UI-SPEC locks this behaviour).
    body = f'+{body}'
  elif value < 0:
    colour = _COLOR_SHORT
    body = _fmt_currency(value)
  else:
    colour = _COLOR_TEXT_MUTED
    body = '$0.00'
  # Belt + braces: escape the colour + body (literal numerics/hex are safe; but
  # this discipline makes reviewer scan trivial).
  return f'<span style="color: {html.escape(colour, quote=True)}">{html.escape(body, quote=True)}</span>'


def _fmt_em_dash() -> str:
  '''Single call site for the em-dash empty-value token; grep-friendly.'''
  return '—'


def _fmt_last_updated(now: datetime) -> str:
  '''YYYY-MM-DD HH:MM AWST. Raises ValueError on naive datetime (Pitfall 9).'''
  if now.tzinfo is None:
    raise ValueError(
      '_fmt_last_updated requires a timezone-aware datetime; '
      f'got naive datetime={now!r}'
    )
  awst = now.astimezone(pytz.timezone('Australia/Perth'))
  return awst.strftime('%Y-%m-%d %H:%M AWST')
```

### Unrealised P&L + trail-stop re-implementation (UI-SPEC §Positions table)

```python
# Source: UI-SPEC §Positions table Derived render-time calculations
# Re-implementing inline per D-01 hex fence (no sizing_engine import).
from system_params import (
  AUDUSD_COST_AUD,
  AUDUSD_NOTIONAL,
  SPI_COST_AUD,
  SPI_MULT,
  TRAIL_MULT_LONG,
  TRAIL_MULT_SHORT,
)

_CONTRACT_SPECS = {
  'SPI200': (SPI_MULT, SPI_COST_AUD),
  'AUDUSD': (AUDUSD_NOTIONAL, AUDUSD_COST_AUD),
}


def _compute_trail_stop_display(position: dict) -> float:
  '''UI-SPEC trail-stop formula. Mirror of sizing_engine.get_trailing_stop
  (anchor on position['atr_entry'], not today's ATR - D-15).'''
  atr_entry = position['atr_entry']
  if position['direction'] == 'LONG':
    peak = position.get('peak_price') or position['entry_price']
    return peak - TRAIL_MULT_LONG * atr_entry
  trough = position.get('trough_price') or position['entry_price']
  return trough + TRAIL_MULT_SHORT * atr_entry


def _compute_unrealised_pnl_display(
  position: dict, state_key: str, current_close: float,
) -> float | None:
  '''UI-SPEC unrealised P&L formula. Mirror of sizing_engine.compute_unrealised_pnl
  with cost_aud_open = SPI_COST_AUD/2 or AUDUSD_COST_AUD/2 (D-13 opening half).'''
  if current_close is None:
    return None
  multiplier, cost_aud_round_trip = _CONTRACT_SPECS[state_key]
  cost_aud_open = cost_aud_round_trip / 2
  direction_mult = 1.0 if position['direction'] == 'LONG' else -1.0
  price_diff = current_close - position['entry_price']
  gross = direction_mult * price_diff * position['n_contracts'] * multiplier
  open_cost = cost_aud_open * position['n_contracts']
  return gross - open_cost
```

A TestStatsMath method should lock this against `sizing_engine.compute_unrealised_pnl(position, current_close, multiplier, cost_aud_open)` with a shared fixture - so if the two drift, both implementations surface the bug.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Jinja2 server-side template | Pure Python block-builder strings | D-02 locks | Avoids adding a dep and a template file; single-module authoring |
| Building the chart with d3.js | Chart.js 4.x UMD from CDN | PROJECT.md locks | One external asset, SRI-lockable, no build step |
| Webpack / Vite bundling | Zero build step, single HTML file | PROJECT.md locks | No node/npm toolchain; operator can open the file directly |
| Per-run `dashboard_TIMESTAMP.html` files | One overwriting `dashboard.html` | D-03 locks | Simpler gitignore; operator bookmarks one file |
| `chartjs-adapter-date-fns` for date axis | Category axis with pre-formatted ISO strings | D-11 locks | Drops a second SRI-locked asset from the dependency list |
| `markupsafe` for escape | `html.escape(value, quote=True)` | D-15 locks + stdlib preference | Zero new deps |

**Deprecated/outdated:**
- Chart.js 2.x API differs (dataset config nested differently) - not a concern since D-12 locks 4.4.6.
- The CONTEXT D-12 placeholder SRI hash (`C5GVzRkc2bvIeI4A...`) is stale - [VERIFIED: the correct hash for jsdelivr + unpkg Chart.js 4.4.6 is `MH1axGwz/uQzfIcjFdjEfsM0xlf5mmWfAwwggaOh5IPFvgKFGbJ2PZ4VBbgSYBQN`]. Planner must commit the verified hash as `_CHARTJS_SRI`.

## Assumptions Log

No `[ASSUMED]` claims in this research. All key facts were verified in-session:

- SRI hash via `curl | openssl dgst` (2026-04-21).
- byte-identical jsdelivr / unpkg CDN content via `diff -q`.
- `html.escape` behaviour (does not escape `/`).
- `json.dumps` + `.replace('</', '<\\/')` escape discipline.
- `statistics.stdev` raising `StatisticsError` on <2 samples.
- `math.log(0)` / `math.log(-5)` raising `ValueError`.
- Phase 4 `main.py:514-519` shape (read from source file in-session).
- Existing test assertion scope (grepped `last_scalars` / `state['signals']` across `tests/`).
- state_manager atomic-write discipline (read `state_manager.py` in-session).
- Chart.js CDN immutability via HTTP headers (`cache-control: immutable`, `x-jsd-version: 4.4.6`).

## Open Questions

### 1. Should the inline `<script>` be wrapped in `DOMContentLoaded`?

- **What we know:** D-11 Chart.js config does not specify. The inline `<script>` runs at the point in the HTML document where it's parsed. If the `<canvas>` is earlier in the body than the `<script>`, the DOM element is already present and Chart.js can instantiate immediately.
- **What's unclear:** Whether a future operator change (e.g., moving scripts to `<head>`) would break the IIFE pattern.
- **Recommendation:** Use the IIFE `(function() { ... })();` placed in the body AFTER the `<canvas>` element. This is the simplest pattern, no DOMContentLoaded handler needed, and it matches the "single static HTML" posture.

### 2. Should Content-Security-Policy (`<meta http-equiv>`) be set?

- **What we know:** The file is opened locally from disk - no HTTP server, so no CSP header. Even a `<meta http-equiv="Content-Security-Policy" content="script-src ...">` would constrain the inline `<script>`.
- **What's unclear:** If the operator ever serves `dashboard.html` behind a reverse proxy with CSP, the inline `<script>` would break.
- **Recommendation:** Do NOT ship a CSP meta tag in v1. Document in a module-level comment that "if this is ever served behind a CSP, the inline `<script>` instantiation needs a nonce or hash". Chart.js 4.x itself has a `styleNonce` option for CSP-sensitive deployments (per [Chart.js GitHub issue #5208](https://github.com/chartjs/Chart.js/issues/5208)) but Phase 5 doesn't need it for local-file viewing.

### 3. Should the golden-HTML snapshot be one file or one-per-scenario?

- **What we know:** CONTEXT D-14 describes a singular "committed `tests/fixtures/dashboard/golden.html`". UI-SPEC §Phase 5 Reuse Notes and D-13 emphasize two scenarios: "sample mid-campaign" + "empty / first-run".
- **What's unclear:** Whether `TestEmptyState` also snapshots, or just asserts on substrings.
- **Recommendation:** Ship TWO golden files: `tests/fixtures/dashboard/golden.html` (populated sample state — TestGoldenSnapshot) and `tests/fixtures/dashboard/golden_empty.html` (reset_state() output — TestEmptyState). Both regenerated by `tests/regenerate_dashboard_golden.py`. This keeps diff-review surfaces separate and lets the "empty state renders all sections" claim be byte-verified.

### 4. Where does `dashboard.render_dashboard` get called from under `--test`?

- **What we know:** D-06 says "after final save_state". Under `--test`, save_state is SKIPPED for structural read-only guarantee. So under `--test`, does the dashboard render?
- **What's unclear:** Whether `--test` should produce a dashboard file (useful for operator preview) or skip it (stricter read-only).
- **Recommendation:** Render the dashboard even under `--test` - the dashboard file is a build artefact, not authoritative state. The operator running `python main.py --test` likely wants to see the preview. Wire the call OUTSIDE the `if args.test: return 0` branch so it fires in both modes. Document this in the plan; include a TestOrchestrator test case `test_run_daily_check_test_mode_renders_dashboard`.

### 5. What is the exact interface for `render_dashboard` from main.py?

- **What we know:** D-01 signature: `render_dashboard(state, out_path=Path('dashboard.html'), now=None)`. D-06: "after the final save_state" with `now=run_date`.
- **What's unclear:** Whether `out_path` should be configurable via CLI (no — CONTEXT deferred list).
- **Recommendation:** Hardcode `Path('dashboard.html')` in main.py's call site. No CLI override in Phase 5; a future CONF-* could add it.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11 | Dashboard module | ✓ | 3.11.8 (pyenv) | — |
| `html` stdlib | XSS escape | ✓ | stdlib | — |
| `json` stdlib | JSON-in-JS serialisation | ✓ | stdlib | — |
| `statistics` stdlib | Sharpe stdev | ✓ | stdlib | — |
| `math` stdlib | log/sqrt | ✓ | stdlib | — |
| `tempfile` stdlib | Atomic write | ✓ | stdlib | — |
| `pytz` | AWST conversion | ✓ | transitive via pandas 2.3.3 | `zoneinfo.ZoneInfo('Australia/Perth')` is a stdlib drop-in |
| `pytest` 8.3.3 | Test runner | ✓ | pinned | — |
| `pytest-freezer` 0.4.9 | Clock lock for golden | ✓ | pinned | — |
| Chart.js 4.4.6 UMD | Equity chart in browser | ✓ (CDN) | Pinned SRI | unpkg.com identical copy [VERIFIED byte-identical] |
| `curl` + `openssl` | SRI regeneration (operator-only, on version bump) | ✓ (macOS / Linux / GHA) | — | — |

**Missing dependencies with no fallback:** none.

**Missing dependencies with fallback:** none (all mandatory deps present).

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.3.3 + pytest-freezer 0.4.9 (already pinned) |
| Config file | `pyproject.toml` (project convention; configure test paths + `-q` default) |
| Quick run command | `pytest tests/test_dashboard.py -x -q` |
| Full suite command | `pytest -x -q` (runs all tests; Phase 4 full-suite convention) |

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DASH-01 | `dashboard.html` is single file with inline CSS | golden HTML | `pytest tests/test_dashboard.py::TestGoldenSnapshot -x` | ❌ Wave 0 |
| DASH-01 | No external stylesheet reference | unit | `pytest tests/test_dashboard.py::TestRenderBlocks::test_html_has_no_external_stylesheet_links -x` | ❌ Wave 0 |
| DASH-02 | SRI hash present + matches committed | unit | `pytest tests/test_dashboard.py::TestRenderBlocks::test_chartjs_sri_matches_committed -x` | ❌ Wave 0 |
| DASH-03 | Signal cards render correct colour per signal | unit | `pytest tests/test_dashboard.py::TestRenderBlocks::test_signal_card_colours -x` | ❌ Wave 0 |
| DASH-04 | Equity chart canvas + script interpolate equity_history | unit | `pytest tests/test_dashboard.py::TestRenderBlocks::test_equity_chart_payload_matches_state -x` | ❌ Wave 0 |
| DASH-04 | `</script>` injection defense | unit | `pytest tests/test_dashboard.py::TestRenderBlocks::test_chart_payload_escapes_script_close -x` | ❌ Wave 0 |
| DASH-05 | Positions table renders 8 columns + current from last_close | unit | `pytest tests/test_dashboard.py::TestRenderBlocks::test_positions_table_columns_and_values -x` | ❌ Wave 0 |
| DASH-05 | Unrealised P&L matches sizing_engine output on shared fixture | unit | `pytest tests/test_dashboard.py::TestStatsMath::test_unrealised_pnl_matches_sizing_engine -x` | ❌ Wave 0 |
| DASH-06 | Last 20 trades rendered newest-first | unit | `pytest tests/test_dashboard.py::TestRenderBlocks::test_trades_table_slice_and_order -x` | ❌ Wave 0 |
| DASH-07 | Sharpe formula + <30 guard | unit | `pytest tests/test_dashboard.py::TestStatsMath::test_sharpe_* -x` | ❌ Wave 0 |
| DASH-07 | Max drawdown formula + empty guard | unit | `pytest tests/test_dashboard.py::TestStatsMath::test_max_drawdown_* -x` | ❌ Wave 0 |
| DASH-07 | Win rate uses gross_pnl > 0 | unit | `pytest tests/test_dashboard.py::TestStatsMath::test_win_rate_* -x` | ❌ Wave 0 |
| DASH-07 | Total return against INITIAL_ACCOUNT | unit | `pytest tests/test_dashboard.py::TestStatsMath::test_total_return_* -x` | ❌ Wave 0 |
| DASH-08 | "Last updated" AWST format | unit | `pytest tests/test_dashboard.py::TestFormatters::test_fmt_last_updated_awst -x` | ❌ Wave 0 |
| DASH-08 | Naive datetime rejected | unit | `pytest tests/test_dashboard.py::TestFormatters::test_fmt_last_updated_rejects_naive_datetime -x` | ❌ Wave 0 |
| DASH-09 | Palette hex tokens in CSS | unit | `pytest tests/test_dashboard.py::TestRenderBlocks::test_inline_css_contains_palette -x` | ❌ Wave 0 |
| B-1 retrofit | `state['signals'][key]['last_close']` present post-run | unit | `pytest tests/test_main.py::TestOrchestrator::test_orchestrator_reads_both_int_and_dict_signal_shape -x` | ✅ (extend existing) |
| D-01 hex fence | dashboard.py blocks forbidden imports | unit | `pytest tests/test_signal_engine.py::TestDeterminism::test_dashboard_no_forbidden_imports -x` | ❌ Wave 0 |
| D-06 integration | main.py calls render_dashboard after save_state | unit | `pytest tests/test_main.py::TestOrchestrator::test_run_daily_check_renders_dashboard -x` | ❌ Wave 0 |
| D-06 integration | dashboard render failure does not crash run | unit | `pytest tests/test_main.py::TestOrchestrator::test_dashboard_failure_never_crashes_run -x` | ❌ Wave 0 |
| D-14 golden snapshot | Byte-identical render of sample_state.json | golden | `pytest tests/test_dashboard.py::TestGoldenSnapshot::test_golden_snapshot_matches_committed -x` | ❌ Wave 0 |
| D-14 golden snapshot | Empty-state render is byte-identical | golden | `pytest tests/test_dashboard.py::TestEmptyState::test_empty_state_matches_committed -x` | ❌ Wave 0 |
| D-14 atomic write | tempfile + os.replace mirror | unit | `pytest tests/test_dashboard.py::TestAtomicWrite::test_atomic_write_success_path -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest tests/test_dashboard.py -x -q` (sub-second suite, runs every task)
- **Per wave merge:** `pytest -x -q` (full suite including Phase 1-4 regressions, <5 seconds)
- **Phase gate:** Full suite green BEFORE `/gsd-verify-work 5`

### Wave 0 Gaps

- [ ] `tests/test_dashboard.py` — new file with 6 test-class skeletons (TestStatsMath, TestFormatters, TestRenderBlocks, TestEmptyState, TestGoldenSnapshot, TestAtomicWrite); mirror `tests/test_state_manager.py` scaffolding convention (module-level path constants + `_make_*` fixture helpers + class-per-concern).
- [ ] `tests/fixtures/dashboard/` directory — new; contains `sample_state.json`, `empty_state.json`, `golden.html`, `golden_empty.html`.
- [ ] `tests/regenerate_dashboard_golden.py` — new offline script mirror of `tests/regenerate_goldens.py`; loads fixtures, calls `render_dashboard(state, tmp, now=datetime(2026, 4, 22, 9, 0, tzinfo=pytz.timezone('Australia/Perth')))`, writes to `tests/fixtures/dashboard/golden*.html`.
- [ ] `.gitignore` update — append `dashboard.html` (Pitfall 8).
- [ ] `tests/test_signal_engine.py::TestDeterminism` extension — add `DASHBOARD_PATH = Path('dashboard.py')`, `FORBIDDEN_MODULES_DASHBOARD = frozenset(...)`, and a new parametrised test `test_dashboard_no_forbidden_imports`.
- [ ] `tests/test_main.py::TestOrchestrator` extension — (a) extend `test_orchestrator_reads_both_int_and_dict_signal_shape` to assert `'last_close' in sig` and `sig['last_close'] == pytest.approx(expected_close)`; (b) add `test_run_daily_check_renders_dashboard` asserting `dashboard.html` exists post-run; (c) add `test_dashboard_failure_never_crashes_run` by monkeypatching `main.dashboard.render_dashboard` to raise and asserting `rc == 0`.
- [ ] Framework install: none — pytest + pytest-freezer already pinned.

## Security Domain

Security enforcement: absent in `.planning/config.json` -> treat as enabled.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Single-operator local app; no login. |
| V3 Session Management | no | No sessions; static file. |
| V4 Access Control | no | No multi-user concept; file is gitignored local artefact. |
| V5 Input Validation | yes | All state values pass through `html.escape(v, quote=True)` (D-15) at HTML leaf; JSON payload injected into `<script>` passes through `json.dumps(...)` + `.replace('</', '<\\/')`. The "input" here is `state.json` - trusted by filesystem perms, but belt + braces still applied per D-15. |
| V6 Cryptography | no | No crypto operations. The only crypto-adjacent feature is the SRI SHA-384 hash, which is verified externally (Pattern 2 section); no crypto code in dashboard.py. |

### Known Threat Patterns for Static HTML Dashboard

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| XSS via unsanitised state values (e.g. exit_reason, instrument name) | Tampering (if state.json compromised) / Information Disclosure (if operator shares the dashboard URL) | `html.escape(value, quote=True)` at every leaf interpolation (D-15) |
| `</script>` injection in JSON chart payload | Tampering | `json.dumps(...)` + `.replace('</', '<\\/')` (Pitfall 1) |
| Chart.js CDN tampering | Tampering | SHA-384 SRI integrity attribute on `<script src>` (D-12); browser refuses to execute on hash mismatch |
| Corrupt `dashboard.html` from mid-write crash | Denial of Service (stale dashboard) | Atomic write via tempfile + fsync + `os.replace` (Pattern 3, mirrors state_manager precedent) |
| Stale timestamp exploitation (freeze `now` to hide drift) | Tampering with audit trail | `_fmt_last_updated` raises on naive datetime (Pitfall 9); `now` is derived from `main._compute_run_date()` which reads `datetime.now(AWST)` once per run |
| Dashboard render failure crashes the main run | Denial of Service (missed email + signal) | try/except Exception wrap in main.py (D-06); never raise upward |

## Sources

### Primary (HIGH confidence)

- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/state_manager.py` — atomic write pattern (`_atomic_write`), load_state signature, 11-field trade shape, _REQUIRED_STATE_KEYS.
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/main.py` — lines 430-520 inspected; exact shape of `state['signals'][state_key]` at lines 514-519; `_SYMBOL_CONTRACT_SPECS` contract-cost lookup.
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/sizing_engine.py` — Position TypedDict; compute_unrealised_pnl + get_trailing_stop formulas re-implemented inline per D-01.
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/system_params.py` — INITIAL_ACCOUNT ($100,000), SPI_MULT (5.0), SPI_COST_AUD (6.0), AUDUSD_NOTIONAL (10,000), AUDUSD_COST_AUD (5.0), TRAIL_MULT_LONG/SHORT.
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/signal_engine.py` — 8-key `get_latest_indicators` dict contract (atr/adx/pdi/ndi/mom1/mom3/mom12/rvol); no close in the shape (confirms B-1 retrofit is needed).
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/tests/test_signal_engine.py:480-550` — existing FORBIDDEN_MODULES + `_top_level_imports` AST walk pattern for hex-fence enforcement.
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/tests/test_main.py:393-432` — existing test that asserts on `sig['last_scalars']`; this is the ONE test that needs the `'last_close' in sig` extension.
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/tests/test_state_manager.py` — class-per-concern test scaffold pattern for `tests/test_dashboard.py` mirror.
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/tests/regenerate_goldens.py` — offline-regen script template for `tests/regenerate_dashboard_golden.py` mirror.
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/requirements.txt` — verified `pytest-freezer==0.4.9` already pinned; no new deps needed.
- Chart.js 4.4.6 UMD — direct curl from `https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.js` and `https://unpkg.com/chart.js@4.4.6/dist/chart.umd.js` (both 205,615 bytes, byte-identical, SRI `sha384-MH1axGwz/uQzfIcjFdjEfsM0xlf5mmWfAwwggaOh5IPFvgKFGbJ2PZ4VBbgSYBQN`); jsdelivr HTTP headers `cache-control: immutable`, `x-jsd-version: 4.4.6`.

### Secondary (MEDIUM confidence)

- Python stdlib `html.escape` behaviour, `statistics.stdev` edge cases, `math.log` exception paths — verified in-session via direct Python invocation.
- [Chart.js CSP and nonce requirements (WebSearch - MDN + Chart.js issue tracker)](https://github.com/chartjs/Chart.js/issues/5208) — confirmed Chart.js 4.x has `styleNonce` option; not needed for local-file dashboard but documented for future CSP deployments.

### Tertiary (LOW confidence)

- None — all claims in this research are backed by primary-source verification or stdlib testing within the session.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - versions pinned in requirements.txt; Chart.js SRI verified byte-level; no new deps.
- Architecture: HIGH - directly mirrors state_manager.py + data_fetcher.py I/O-hex patterns; AST blocklist enforcement already shipping for 3 modules.
- Pitfalls: HIGH - every pitfall has a session-verified failure mode or a direct grep/read of existing code.
- B-1 retrofit scope: HIGH - exact line numbers in main.py confirmed + exact test to extend identified.
- Golden-HTML byte stability: MEDIUM - verified on macOS; cross-platform determinism (Windows line endings, locale, etc.) depends on using `encoding='utf-8'` + `mode='w'` consistently; tests run on macOS + Linux CI will catch 99% of cases but Windows is out of scope for v1.
- SRI: HIGH - triple-verified (jsdelivr + unpkg + byte-compare).

**Research date:** 2026-04-21
**Valid until:** 2026-05-21 (30 days; stable domain — Chart.js 4.4.6 is immutable CDN asset, stdlib primitives don't drift, Phase 4 state schema is locked).

Sources:
- [Chart.js CSP - styleNonce option (GitHub Issue #5208)](https://github.com/chartjs/Chart.js/issues/5208)
- [CSP: script-src - MDN Web Docs](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Security-Policy/script-src)
- [CSP Nonce - Script & Style Attribute](https://content-security-policy.com/nonce/)
- [jsdelivr Chart.js 4.4.6 CDN endpoint](https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.js)
- [unpkg Chart.js 4.4.6 mirror](https://unpkg.com/chart.js@4.4.6/dist/chart.umd.js)
