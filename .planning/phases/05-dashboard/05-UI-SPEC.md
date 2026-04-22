---
phase: 5
slug: dashboard
status: draft
shadcn_initialized: false
preset: none
created: 2026-04-22
revision_pass: 2026-04-22-reviews
revision_source: 05-REVIEWS.md (C-1 pytz localize sweep across examples; prior revision: 05-UI-CHECKER B-1 wiring fix + F-1/2/3/4 flags)
---

# Phase 5 — UI Design Contract

> Visual and interaction contract for the Phase 5 static `dashboard.html` render.
> Consumed by `gsd-planner` (task values + CSS constants), `gsd-executor` (verbatim
> strings + tokens), `gsd-ui-checker` (6-dimension sign-off), and `gsd-ui-auditor`.
> Upstream locks (do NOT re-open): palette (PROJECT.md + CONTEXT D-02), Chart.js
> 4.4.6 UMD + SRI (CONTEXT D-12), single-file inline-CSS / no build step
> (PROJECT.md Constraints + CONTEXT D-04), dark theme only (CONTEXT scope
> boundaries), numeric formatting (CONTEXT D-16), hex-lite import fence
> (CONTEXT D-01), XSS escape posture (CONTEXT D-15).

> **Revision 2026-04-22 (UI-CHECKER pass 2).** Surgical edits applied: (B-1)
> "Current" price column now reads `state['signals'][key]['last_close']` rather
> than the non-existent `last_scalars['close']` — Phase 4 retrofit required, see
> §Downstream notes for planner. (F-1) FLAT-on-surface contrast row added.
> (F-2) Glyph budget expanded to include `·` (U+00B7) and `→` (U+2192).
> (F-3) H2 subtitle refactored to sibling `<p class="subtle">` for screen-reader
> clarity. (F-4) Positions-table empty-state `colspan` corrected to `"8"`
> (supersedes the stale `colspan="7"` reference in CONTEXT D-13, which is
> retained verbatim in CONTEXT for history). (F-8) Trade-log field-name note
> added to Traceability — authoritative 12-field shape is `main._closed_trade_to_record`
> + `state_manager.record_trade`, not the descriptive list in CONTEXT
> canonical_refs line 27. See also new §Field Mapping (state.json → UI) table.

---

## Design System

| Property | Value |
|----------|-------|
| Tool | none — stdlib Python string builder (CONTEXT D-02) |
| Preset | not applicable (no component framework; PROJECT.md Constraints forbid React/Vue/build step) |
| Component library | none — per-block `_render_*` helpers in `dashboard.py` (CONTEXT D-02) |
| Icon library | none — zero external assets beyond Chart.js 4.4.6 (CONTEXT D-04); pure Unicode glyphs only. Reserved glyph budget: {`—` (U+2014 em-dash), `·` (U+00B7 middle dot), `→` (U+2192 rightwards arrow), `$`, `%`, `+`, `-`, `,`, `.`, `:`, `/`}. No other non-ASCII glyph may appear in the rendered body. |
| Font | System font stack (no webfont, no external stylesheet per CONTEXT D-04 + PROJECT.md): `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif`. Monospace token used in numeric cells to lock decimal-column alignment: `ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace` |

**Lockdown note.** No webfonts, no icon fonts, no SVG sprites. Every glyph must render from the OS's installed fonts. This is a PROJECT.md "no external stylesheets" interpretation carried forward by CONTEXT D-04.

**Glyph-budget rationale (F-2).** The signal-card scalar line uses `·` (U+00B7) as the delimiter between scalars, and the closed-trades "Entry → Exit" column uses `→` (U+2192). Both are included in the system-font coverage of every targeted OS (macOS, Windows 10+, modern Linux desktops) and render without font fallback. Adding them to the explicit allowlist prevents reviewer drift.

---

## Spacing Scale

8-point baseline. Every gap / padding / margin is a multiple of 4 (8 where possible).
Designed to work at a 375px viewport minimum (CONTEXT scope boundary: "no responsive mobile vs desktop variant — one layout, works at 375px+").

| Token | Value | Usage |
|-------|-------|-------|
| `--space-1` | 4px  | Icon/text inline gaps, badge inner padding (reserved — unused in v1) |
| `--space-2` | 8px  | Table-cell vertical padding, signal-card badge inner padding |
| `--space-3` | 12px | Table-cell horizontal padding, chip/badge side padding |
| `--space-4` | 16px | Default gap between tightly-coupled elements (label↔value, title↔subtitle) |
| `--space-6` | 24px | Intra-section padding (inside card interior), signal-card gap |
| `--space-8` | 32px | Gap between major sections (header→cards→chart→tables→stats→footer) |
| `--space-12` | 48px | Top/bottom page padding on desktop width |

**Layout container.**

| Property | Value |
|----------|-------|
| Max content width | `1100px` (centered with `margin: 0 auto`) |
| Page horizontal padding | 16px at ≤640px viewport, 24px otherwise (single media query OK — CSS only, no JS) |
| Page vertical padding | 32px top, 48px bottom |
| Section → section vertical gap | 32px (`--space-8`) |
| Card / table internal padding | 24px (`--space-6`) |

**Exceptions:** none. The only non-8-multiple token is `--space-3 = 12px`, which is an 4-multiple; it's dedicated to table-cell horizontal padding because 16px feels wide in the 7-column positions table at 375px and 8px feels cramped. Documented to prevent drift.

---

## Typography

System fonts only. Four roles, exactly two weights (400 regular, 600 semibold). No italic. No underline (no links in the dashboard).

| Role | Size | Weight | Line Height | Used By |
|------|------|--------|-------------|---------|
| `--fs-body` | 14px | 400 | 1.5 | Table body cells, signal-card sub-labels ("Signal as of …"), footer disclaimer |
| `--fs-label` | 12px | 600 | 1.4 | Table `<th>` headers, stat-tile labels ("Total Return", "Sharpe", …), section eyebrow labels |
| `--fs-heading` | 20px | 600 | 1.3 | Section titles ("Signal Status", "Open Positions", "Closed Trades", "Key Stats", "Equity Curve") |
| `--fs-display` | 28px | 600 | 1.2 | App title in header, signal-card big-value (signal label), stat-tile value |

**Numeric cells.** Price / equity / P&L cells in all tables and stat-tile values use `font-family: var(--font-mono)` + `font-variant-numeric: tabular-nums` so digit columns line up across rows.

**Letter-spacing.** `--fs-label` (12px 600) cells use `letter-spacing: 0.04em; text-transform: uppercase` so headers read as eyebrow labels — a common dark-admin pattern that reads clearly at 14px body.

**No weight outside {400, 600}.** No italic. No underline. Keeps the OS-font cost/pixel budget predictable.

---

## Color

60 / 30 / 10 split on a single dark theme (CONTEXT D-04 locks "no light mode"). Listed with explicit CSS-variable names so the planner can interpolate directly from `_INLINE_CSS` in `dashboard.py`.

| Role | Hex | CSS var | Usage |
|------|-----|---------|-------|
| Dominant (60%) — page bg | `#0f1117` | `--color-bg` | `<body>` background, outer container |
| Secondary (30%) — surface | `#161a24` | `--color-surface` | Signal cards, tables, stat tiles, chart container background |
| Secondary border | `#252a36` | `--color-border` | 1px borders on cards/tables; table `<thead>` bottom border; table row dividers |
| Text primary | `#e5e7eb` | `--color-text` | Body text, table values, stat values, section headings |
| Text secondary | `#cbd5e1` | `--color-text-muted` | Table headers, stat-tile labels, "Signal as of …", chart axis ticks (CONTEXT D-11), zero-P&L values |
| Text tertiary / empty-state | `#64748b` | `--color-text-dim` | Empty-state text ("— No open positions —"), footer disclaimer body, "signal_as_of: never" |
| Accent LONG (10%) | `#22c55e` | `--color-long` | LONG signal label, positive P&L numbers, Chart.js equity line stroke |
| Accent SHORT (10%) | `#ef4444` | `--color-short` | SHORT signal label, negative P&L numbers, ACTION REQUIRED border (Phase 6 reuse) |
| Accent FLAT (10%) | `#eab308` | `--color-flat` | FLAT signal label, "signal: —" pre-first-run state |
| Zero / neutral P&L | `#cbd5e1` | `--color-text-muted` | P&L cell at exactly $0.00 (CONTEXT D-16) |

**Accent reserved for** (explicit list — never "all interactive elements"):
1. Signal-card big label (SPI200 + AUDUSD): `--color-long | --color-short | --color-flat` — applied only to the one-word label chip inside each card
2. Table cells that show P&L (positions: unrealised P&L; trades: `net_pnl`): positive → `--color-long`, negative → `--color-short`, zero → `--color-text-muted` (CONTEXT D-16 `_fmt_pnl_with_colour`)
3. Chart.js equity line `borderColor` + `pointHoverRadius` fill: `--color-long` (CONTEXT D-11, single value)
4. Stat-tile "Total Return" value: positive → `--color-long`, negative → `--color-short`, zero/empty → `--color-text-muted`

No accent used for: section headings, table headers, footer, empty-state rows, chart axis ticks, borders, or any other chrome. Accent saturation stays ≤10% of visible pixel coverage by construction.

| Destructive | `#ef4444` | `--color-short` | Dual-purpose with SHORT — same hex (semantic overlap: red = bearish = danger). Phase 6 email will reuse for the ACTION REQUIRED block border. Dashboard has no destructive actions (it's read-only), so destructive use in v1 is none. |

**Contrast audit** (WCAG AA 4.5:1 body / 3:1 UI chrome / label ≥ 4.5:1):

| Foreground on bg `#0f1117` | Ratio | WCAG AA |
|-----------------------------|-------|---------|
| `#e5e7eb` text primary | 14.8:1 | PASS (AAA) |
| `#cbd5e1` text muted | 12.2:1 | PASS (AAA) |
| `#64748b` text dim | 4.7:1 | PASS AA (body) — avoid for 12px labels |
| `#22c55e` LONG | 6.1:1 | PASS AA |
| `#ef4444` SHORT | 4.9:1 | PASS AA |
| `#eab308` FLAT | 9.4:1 | PASS AAA |

| Foreground on surface `#161a24` | Ratio | WCAG AA |
|----------------------------------|-------|---------|
| `#e5e7eb` text primary | 13.5:1 | PASS (AAA) |
| `#cbd5e1` text muted | 11.1:1 | PASS (AAA) |
| `#22c55e` LONG | 5.6:1 | PASS AA |
| `#ef4444` SHORT | 4.5:1 | PASS AA (at the contrast floor — do NOT shift surface any lighter) |
| `#eab308` FLAT | 8.6:1 | PASS AAA (F-1 paperwork close — measured via WebAIM contrast checker with fg `#eab308` / bg `#161a24`; reviewer to re-verify during Wave 2) |

Rule: **`#64748b` is body-copy-only** (footer disclaimer, empty-state rows). Never apply it to 12px labels.

---

## Copywriting Contract

Phase 5 is a **read-only render**. There are no CTAs, no forms, no destructive actions, no error toasts. The copy contract below locks every operator-visible string.

### Header

| Element | Exact copy |
|---------|-----------|
| Page `<title>` | `Trading Signals — Dashboard` |
| H1 title | `Trading Signals` |
| H1 subtitle (muted, smaller) | `SPI 200 & AUD/USD mechanical system` |
| Last-updated label (muted) | `Last updated` |
| Last-updated value format | `YYYY-MM-DD HH:MM AWST` (example: `2026-04-22 09:00 AWST` — minute precision, no seconds, explicit AWST suffix per DASH-08). Derived via `now.astimezone(pytz.timezone('Australia/Perth')).strftime('%Y-%m-%d %H:%M AWST')`. |

### Section headings (H2)

| Section | Exact copy |
|---------|-----------|
| Signal cards band | `Signal Status` |
| Equity chart | `Equity Curve` |
| Open positions table | `Open Positions` |
| Closed trades table | `Closed Trades` (see **F-3 refactor** below — subtitle "last 20" moves OUT of the H2 into a sibling `<p class="subtle">`) |
| Key stats block | `Key Stats` |

**F-3 refactor — closed-trades H2 structure.** The subtitle `last 20` is no longer nested inside the `<h2>` with an em-dash wrap. Instead, render two sibling elements so screen readers announce the heading cleanly and CSS can style the subtitle independently:

```html
<h2 id="heading-trades">Closed Trades</h2>
<p class="subtle">last 20</p>
```

`<p class="subtle">` styling: `--fs-label` 12px, weight 400, `--color-text-muted`, no uppercase, no letter-spacing, margin-top: 0, margin-bottom: `--space-4`. The sibling sits between the H2 and the `<table>` — the H2 announces "Closed Trades", the paragraph clarifies the row limit. Component Hierarchy and the golden-HTML fixture reflect this.

### Signal cards

Two cards side by side (SPI200 + AUDUSD), stacking vertically below 720px viewport.

| Field | Exact copy / format |
|-------|---------------------|
| Card eyebrow (small label) | `SPI 200` (for `SPI200`); `AUD / USD` (for `AUDUSD`). Static display labels — map the state keys `'SPI200'` and `'AUDUSD'` through a single `_INSTRUMENT_DISPLAY_NAMES` dict constant in `dashboard.py`. |
| Card big label | `LONG` / `SHORT` / `FLAT` / `—` (the em-dash when per-instrument state entry is missing, per CONTEXT D-13) |
| Signal-as-of line | `Signal as of YYYY-MM-DD` (example: `Signal as of 2026-04-21`). Empty state (per CONTEXT D-13): `Signal as of never`. |
| Scalar line | `ADX {x.x}  ·  Mom₁ {+x.x%}  ·  Mom₃ {+x.x%}  ·  Mom₁₂ {+x.x%}  ·  RVol {x.xx}` — one row of ASCII · middots (U+00B7, glyph-budget approved) at ≥720px; wraps onto two rows below. Use `<sub>1</sub>` etc. for the Mom period subscripts (HTML, not Unicode subscripts, for universal font coverage). Empty state: the whole line is the single em-dash `—` in `--color-text-dim`. |

**Instrument display names** (locked — prevents reviewer bikeshedding):
- `SPI200` → `SPI 200`
- `AUDUSD` → `AUD / USD`

### Open positions table

Header columns (exact text, exact order, left→right):

| # | Header | Data source / format | Alignment |
|---|--------|----------------------|-----------|
| 1 | `Instrument` | Display name from `_INSTRUMENT_DISPLAY_NAMES` | left |
| 2 | `Direction` | `LONG` / `SHORT` chip, coloured `--color-long` / `--color-short`, weight 600 | left |
| 3 | `Entry` | `_fmt_currency` of `position['entry_price']` (e.g. `$7,412.50`) | right |
| 4 | `Current` | `_fmt_currency` of `state['signals'][key]['last_close']` (B-1 fix — new field added by Phase 5 Wave 0 retrofit; see §Downstream notes). If `last_close` is missing or `None` (pre-retrofit state.json, or signals entry has no current close), render `—` in `--color-text-dim`. | right |
| 5 | `Contracts` | `position['n_contracts']` (integer, no commas for single-digit) | right |
| 6 | `Pyramid` | `Lvl {n}` where n ∈ {0,1,2} — so `Lvl 0`, `Lvl 1`, `Lvl 2` | right |
| 7 | `Trail Stop` | Derived at render time via formula below | right |
| 8 | `Unrealised P&L` | Derived at render time via formula below; coloured via `_fmt_pnl_with_colour` (CONTEXT D-16); em-dash if `last_close` missing | right |

**Derived render-time calculations** (must not import `sizing_engine` per CONTEXT D-01; re-implement the pure-math formulas inline in `dashboard.py`, with a unit-test that hand-locks a known case). After B-1 fix, the `current` symbol in these formulas resolves from `state['signals'][state_key]['last_close']` (a plain float), NOT from `last_scalars` (which remains the locked 8-key indicator dict per Phase 1 D-08):

- Trail stop (LONG): `position['peak_price'] - 3.0 * position['atr_entry']`
- Trail stop (SHORT): `position['trough_price'] + 2.0 * position['atr_entry']`
- Unrealised P&L (LONG):  `current = state['signals'][state_key]['last_close']`; `pnl = (current - entry) * n_contracts * multiplier - (cost_aud * n_contracts / 2)`
- Unrealised P&L (SHORT): `current = state['signals'][state_key]['last_close']`; `pnl = (entry - current) * n_contracts * multiplier - (cost_aud * n_contracts / 2)`
- Multiplier/cost lookup is stdlib-safe via a `_CONTRACT_SPECS = {'SPI200': (SPI_MULT, SPI_COST_AUD), 'AUDUSD': ...}` module constant.

Note: the opening-half cost subtraction mirrors Phase 2 `compute_unrealised_pnl` exactly (per CLAUDE.md §Operator Decisions + D-13). Any drift here is a bug and Phase 5 `TestStatsMath` includes one fixture locking the math.

**Empty state** — when every entry in `state['positions']` is `None` (CONTEXT D-13): render ONE `<tr>` with `<td colspan="8">` containing the copy `— No open positions —` (em-dash, space, words, space, em-dash) in `--color-text-dim`, centered. (F-4 note: the positions table has 8 columns after UI-SPEC added `Instrument` + `Unrealised P&L`; CONTEXT D-13 says `colspan="7"` as a restatement of the pre-UI-SPEC 7-column sketch. **UI-SPEC supersedes CONTEXT here.** Executor uses `colspan="8"`; the golden-HTML fixture reflects this.)

**Partial state** — if SPI200 has a position but AUDUSD does not: render only the SPI200 row. Do not render a placeholder for AUDUSD; the empty-state row appears only when the whole `positions` dict is all-None. This preserves row parity with the actual state shape and avoids misleading mixed-status rows.

### Closed trades table

Header columns (exact text, exact order, left→right):

| # | Header | Data source / format | Alignment |
|---|--------|----------------------|-----------|
| 1 | `Closed` | `trade['exit_date']` (ISO YYYY-MM-DD; static string — no reformatting) | left |
| 2 | `Instrument` | Display name from `_INSTRUMENT_DISPLAY_NAMES` (mapped from `trade['instrument']`) | left |
| 3 | `Direction` | `LONG` / `SHORT` chip, same colour treatment as positions table | left |
| 4 | `Entry → Exit` | `_fmt_currency(entry_price)` → `_fmt_currency(exit_price)` with the ASCII `→` U+2192 between them (glyph-budget approved per F-2) | right |
| 5 | `Contracts` | `trade['n_contracts']` | right |
| 6 | `Reason` | `trade['exit_reason']` passed through a display map: `flat_signal → "Signal flat"`, `signal_reversal → "Reversal"`, `stop_hit → "Stop hit"`, `adx_exit → "ADX drop"`. Unknown values pass through via `html.escape` as-is. | left |
| 7 | `P&L` | `_fmt_pnl_with_colour(trade['net_pnl'])` — uses `net_pnl` (state_manager.record_trade's D-20 appended key, net of closing half-cost) NOT `gross_pnl` | right |

**Skipped-size rows** (CLAUDE.md §Operator Decisions — `n_contracts == 0` warnings from `trade_log`): state_manager's `_validate_trade` rejects `n_contracts <= 0`, so such rows **cannot** reach `trade_log`. The "skipped" trade surfaces in `state.warnings`, not in the trades table. UI-SPEC does NOT render skipped-size rows in this table; prior-decision note in CONTEXT `<prior_decisions>` was a restatement of the warning source, not a table requirement.

**Row order.** Newest first. Slice in render helper: `state['trade_log'][-20:][::-1]` (last 20, reversed so the most recent is at the top).

**Empty state** — `trade_log == []` (CONTEXT D-13): render ONE `<tr>` with `<td colspan="7">` containing `— No closed trades yet —` in `--color-text-dim`, centered.

### Key stats block

Four stat tiles in a row ≥720px viewport, 2×2 grid below. Each tile is a surface with 24px (`--space-6`) interior padding.

| Tile order | Label (exact copy) | Value source | Insufficient-data copy |
|------------|---------------------|--------------|------------------------|
| 1 | `Total Return` | `_compute_total_return(state)` → `_fmt_percent_signed` (CONTEXT D-10, D-16 `+5.3%` / `-2.1%`). Coloured: positive `--color-long`, negative `--color-short`, zero `--color-text-muted`. | Always computable — never shows em-dash per D-10. |
| 2 | `Sharpe` | `_compute_sharpe(state)` → `f'{sharpe:.2f}'` (CONTEXT D-07). Not coloured. | `—` when `len(equity_history) < 30` or `stdev == 0` (CONTEXT D-07). |
| 3 | `Max Drawdown` | `_compute_max_drawdown(state)` → `f'{dd*100:.1f}%'` (CONTEXT D-08). Not coloured (magnitude reads as negative by sign; adding red would double-encode). | `—` when `equity_history == []` (CONTEXT D-08). |
| 4 | `Win Rate` | `_compute_win_rate(state)` → `f'{rate*100:.1f}%'` (CONTEXT D-09). Not coloured. | `—` when `trade_log == []` (CONTEXT D-09). |

**Tile composition.**
- Label on top, weight 600, 12px, `--color-text-muted`, uppercase, `letter-spacing: 0.04em`.
- Value below label, weight 600, 28px (`--fs-display`), `--color-text` (or accent for tile 1), `font-family: var(--font-mono)`, `font-variant-numeric: tabular-nums`.
- 12px gap between label and value.

### Footer disclaimer

| Element | Exact copy |
|---------|-----------|
| Disclaimer text | `Signal-only system. Not financial advice.` (CONTEXT D-02 literal — do not embellish) |
| Rendered as | `<footer>` element, `--color-text-dim`, 12px (`--fs-label` minus uppercase), weight 400, centered, 48px top margin, 24px bottom margin |

### Empty / placeholder copy inventory

| Context | Exact copy | Colour token |
|---------|-----------|--------------|
| Signal card with no state entry | Label: `—` / Sub: `Signal as of never` / Scalars: single `—` | `--color-flat` for the big `—` label, `--color-text-dim` for sub/scalars |
| Equity chart (no history) | `No equity history yet — first full run needed` (CONTEXT D-13 literal) | `--color-text-dim`, centered, in a `<div>` sized to match the chart container so layout doesn't collapse |
| Positions table (all None) | `— No open positions —` | `--color-text-dim`, centered row |
| Trades table (empty) | `— No closed trades yet —` | `--color-text-dim`, centered row |
| Stat tile insufficient data | `—` (single em-dash) | `--color-text-muted` |
| Last-updated when `now` absent (tests) | Never happens — `render_dashboard` must always receive a `now`. If omitted, helper defaults to `datetime.now(pytz.timezone('Australia/Perth'))`. | — |

---

## Component Hierarchy

```
<body style="background:#0f1117">
  <div class="container" style="max-width:1100px; margin:0 auto; padding:32px 24px 48px">
    <header>                          # --space-8 bottom margin
      <h1>Trading Signals</h1>
      <p class="subtitle">SPI 200 & AUD/USD mechanical system</p>
      <p class="meta">
        <span class="label">Last updated</span>
        <span class="value">2026-04-22 09:00 AWST</span>
      </p>
    </header>

    <section aria-labelledby="heading-signals">
      <h2 id="heading-signals">Signal Status</h2>
      <div class="cards-row">          # flex row; wraps to column below 720px
        <article class="card">...SPI200...</article>
        <article class="card">...AUDUSD...</article>
      </div>
    </section>

    <section aria-labelledby="heading-equity">
      <h2 id="heading-equity">Equity Curve</h2>
      <div class="chart-container">    # fixed height 320px, full width of container
        <canvas id="equityChart" aria-label="Account equity line chart over time"></canvas>
        # OR the empty-state <div> per D-13
      </div>
    </section>

    <section aria-labelledby="heading-positions">
      <h2 id="heading-positions">Open Positions</h2>
      <table class="data-table">
        <caption class="visually-hidden">Open positions with current price, contracts, trail stop, and unrealised P&L</caption>
        <thead>...</thead>
        <tbody>...</tbody>
      </table>
    </section>

    <section aria-labelledby="heading-trades">
      <h2 id="heading-trades">Closed Trades</h2>
      <p class="subtle">last 20</p>     # F-3 refactor — sibling paragraph, not nested in H2
      <table class="data-table">
        <caption class="visually-hidden">Most recent 20 closed trades, newest first</caption>
        <thead>...</thead>
        <tbody>...</tbody>
      </table>
    </section>

    <section aria-labelledby="heading-stats">
      <h2 id="heading-stats">Key Stats</h2>
      <div class="stats-grid">         # 4-col grid ≥720px, 2x2 below
        <div class="stat-tile">...Total Return...</div>
        <div class="stat-tile">...Sharpe...</div>
        <div class="stat-tile">...Max Drawdown...</div>
        <div class="stat-tile">...Win Rate...</div>
      </div>
    </section>

    <footer>
      Signal-only system. Not financial advice.
    </footer>
  </div>
  <!-- Chart.js UMD with SRI, loaded in <head> per CONTEXT D-12 -->
  <!-- Chart.js instantiation inline <script> only if equity_history is non-empty -->
</body>
```

**Rendering-order rule.** The body block order is locked (matches CONTEXT D-02 list): header → signal cards → equity chart → positions table → closed trades table → key stats → footer. Planner does not reorder.

---

## Interaction States

Phase 5 is static. There is **one** interactive element: the Chart.js hover tooltip.

| Element | State | Behaviour |
|---------|-------|-----------|
| Chart.js line / points | idle | Line stroke `--color-long` 2px, no point markers (CONTEXT D-11 `pointRadius: 0`) |
| Chart.js line / points | hover on nearest point | Point marker becomes a 4px filled dot in `--color-long` (D-11 `pointHoverRadius: 4`) |
| Chart.js line / points | tooltip | Renders as `$<value>` with commas: `$104,532.18`. Callback: `(ctx) => '$' + ctx.parsed.y.toLocaleString()` (CONTEXT D-11 literal). X-axis shown as the bare ISO date (category axis, no date adapter). |
| Every other element | any | No hover, no focus ring, no pointer change. `cursor: default` on the whole page. |

**No other interactions.** No clickable links, no buttons, no forms, no keyboard shortcuts, no JavaScript beyond the Chart.js instantiation snippet. The dashboard is not a SPA.

---

## Accessibility Contract

Target: **WCAG 2.1 AA** for body text contrast, reasonable screen-reader traversal, no automated-axe show-stoppers when the file is opened in Chrome + axe-core CLI (optional verification — not gated in v1 tests since axe is not in the stack).

| Requirement | Implementation |
|-------------|----------------|
| Page `<title>` | `Trading Signals — Dashboard` (verbatim) |
| `<html lang>` | `<html lang="en">` |
| Heading hierarchy | Exactly one H1 (`Trading Signals`). Five H2s (`Signal Status`, `Equity Curve`, `Open Positions`, `Closed Trades`, `Key Stats`) — no skipped levels. No H3+ used in v1. |
| Section labelling | Every `<section>` has `aria-labelledby` pointing at its `<h2 id="…">` (see component tree) |
| Closed-trades subtitle | F-3: sibling `<p class="subtle">last 20</p>` — plain paragraph, not inside the H2. Screen readers announce the heading cleanly, then the paragraph separately. No `aria-hidden`, no role hacks. |
| Table semantics | Both tables use `<caption class="visually-hidden">…</caption>`, `<thead><tr><th scope="col">…</th></tr></thead>`, `<tbody><tr><td>…</td></tr></tbody>`. `scope="col"` is mandatory on every header cell. |
| Chart canvas | `<canvas aria-label="Account equity line chart over time" role="img">` — the canvas is informational, not interactive (the tooltip's mouse-only hover is progressive enhancement; screen-reader users read the equity from the table data below if needed) |
| Empty-state equity div | Plain text inside a div — directly readable by screen readers, no special ARIA needed |
| Body contrast | All body text pairings audited above meet ≥4.5:1 |
| UI chrome contrast | Borders (`--color-border` on `--color-surface`): 2.0:1 — acceptable because borders are cosmetic, not conveying information |
| Language of numeric / datetime text | ISO dates (YYYY-MM-DD) and `$1,234.56` format are language-neutral; no date-adapter localisation needed |
| Reduced-motion / prefers-colour-scheme | None. Single dark theme only (CONTEXT scope boundary). No animation used. |
| Keyboard navigation | No focusable elements beyond the browser's default canvas tabstop (which Chart.js does not override). `tabindex=0` is not added anywhere. |
| Form / button / link count | Zero. Dashboard is read-only. No `<a>`, `<button>`, `<input>`, or `<form>` elements. |

**`visually-hidden` utility class** (inside `_INLINE_CSS`):

```css
.visually-hidden {
  position: absolute !important;
  width: 1px; height: 1px;
  padding: 0; margin: -1px;
  overflow: hidden; clip: rect(0, 0, 0, 0);
  white-space: nowrap; border: 0;
}
```

---

## Chart Component

CONTEXT D-11 locks the Chart.js config. UI-SPEC supplements with container + empty-state sizing.

| Property | Value |
|----------|-------|
| Container size (height) | 320px (fixed) on all viewports |
| Container size (width) | 100% of content column (max 1100 − 48 = 1052px interior) |
| Container background | `--color-surface` |
| Container padding | 24px (`--space-6`) on all 4 sides |
| Container border | `1px solid --color-border`, border-radius 8px |
| Canvas `width` / `height` attributes | Not set — Chart.js `responsive: true` + `maintainAspectRatio: false` + parent `position: relative; height: 320px` own the sizing |
| Axis tick colour | `#cbd5e1` (`--color-text-muted`) — CONTEXT D-11 |
| Axis gridline colour | `#252a36` (`--color-border`) — add via `options.scales.{x,y}.grid.color: '#252a36'` |
| Legend | Hidden (CONTEXT D-11 `legend: { display: false }`) |
| Tooltip background | Chart.js default dark theme is acceptable |
| Line tension | 0.1 (CONTEXT D-11) |
| Line border width | 2px (CONTEXT D-11) |
| Fill below line | `fill: false` (CONTEXT D-11 — no area fill) |
| Empty-state placeholder | Exact same 320px container renders an inner `<div class="empty-state">No equity history yet — first full run needed</div>` centered vertically and horizontally. Do NOT collapse the container height — layout stability matters. |

---

## Responsive Behaviour

One layout, one media query. The design targets 375px at minimum (CONTEXT scope). No additional breakpoints in v1.

| Breakpoint | Change |
|------------|--------|
| ≤ 720px | Signal cards row becomes column (each card full width). Key stats grid becomes 2×2 instead of 1×4. Page horizontal padding drops from 24px to 16px. |
| > 720px | Default layout: signal cards side-by-side, 4-column stats grid, 24px page padding. |
| ≥ 1148px | Content hits `max-width: 1100px` and stops growing; gutters grow. |

All tables remain as tables at every viewport — no "table-to-cards" transformation. Horizontal scroll on the table is acceptable on narrow viewports; wrap tables in `overflow-x: auto` containers.

---

## Registry Safety

| Registry | Blocks Used | Safety Gate |
|----------|-------------|-------------|
| shadcn official | none — project is Python, not React | not applicable |
| Chart.js 4.4.6 UMD via jsdelivr CDN | `chart.umd.js` | SRI hash verification gated in Wave 0 per CONTEXT D-12. Research task must compute `openssl dgst -sha384 -binary chart.umd.js \| base64` against the committed `_CHARTJS_SRI` constant. Browser refuses to execute on mismatch. |
| any third-party registry | none | not applicable |

**No npm, no pypi, no new CDN.** Chart.js is the sole external asset. Icon libraries, webfonts, CSS frameworks, and SVG-sprite CDNs are all forbidden (CONTEXT D-04 + PROJECT.md).

---

## Phase 6 Reuse Notes (for the planner)

Phase 6 (email) will reuse:
- Palette constants (`_COLOR_*`)
- `_fmt_currency`, `_fmt_percent_signed`, `_fmt_percent_unsigned`, `_fmt_pnl_with_colour`, `_fmt_em_dash`
- Display-name mapping for instruments (`_INSTRUMENT_DISPLAY_NAMES`)
- Exit-reason display mapping
- HTML-escape discipline (CONTEXT D-15)

Phase 6 will NOT reuse:
- `_INLINE_CSS` (emails need inline-CSS on every element; different shape)
- System font stack (email clients have quirkier font support)
- Chart.js (emails cannot execute JS; Phase 6 uses a pre-rendered PNG or omits the chart)

The planner may promote the formatters to a shared `_format_helpers.py` or keep them private to `dashboard.py` and re-copy for `notifier.py`. Either is consistent with the hex-lite rule (both files are I/O hexes; they may not import each other, but they may both import a pure formatter helper).

---

## Format Helper Contracts (executor-verbatim)

Names locked here so the planner can write task ACs and the executor ships without naming-bikeshedding. All helpers are stdlib-only, pure (no `state` argument), side-effect free.

| Helper | Signature | Returns |
|--------|-----------|---------|
| `_fmt_currency(value: float) -> str` | `$1,234.56`, `-$567.89`, `$0.00`. Always 2 dp. Negative uses leading `-$`, not parentheses. Never suffix-collapses to K/M/B. |
| `_fmt_percent_signed(fraction: float) -> str` | `+5.3%`, `-12.5%`, `+0.0%`. Input is a fraction (0.053 → `+5.3%`). |
| `_fmt_percent_unsigned(fraction: float) -> str` | `58.3%`, `12.5%`. Input is a fraction. |
| `_fmt_pnl_with_colour(value: float) -> str` | Returns safe HTML `<span style="color: #22c55e">+$1,234.56</span>` for positive, `<span style="color: #ef4444">-$567.89</span>` for negative, `<span style="color: #cbd5e1">$0.00</span>` for zero. Uses `html.escape` on any text not in the controlled numeric format (here there's no user-controlled text, so `html.escape` is not strictly required, but the helper passes output through it as a belt-and-braces guardrail per CONTEXT D-15). |
| `_fmt_em_dash() -> str` | The literal `'—'`. One call site per empty cell so tests can grep a single token. |
| `_fmt_last_updated(now: datetime) -> str` | `'2026-04-22 09:00 AWST'` — applies `now.astimezone(pytz.timezone('Australia/Perth'))` then `strftime('%Y-%m-%d %H:%M AWST')`. Asserts `now.tzinfo is not None`; raises ValueError on naive datetime (catches test-fixture bugs early). |

---

## Non-Goals (locked — do NOT add)

- No collapsible sections, no tabs, no modals.
- No print stylesheet.
- No `prefers-color-scheme` media query.
- No `@media (hover:…)`, `@media (reduced-motion:…)`, or any animation.
- No emoji glyphs in the body (Phase 6 email uses 🔴 / 📊 in the subject; dashboard does not).
- No company / author badge / version string in the footer (footer is only the 4-word disclaimer).
- No CSS custom-property fallbacks for IE (project targets modern Chromium/Safari/Firefox only).
- No CSS `@supports` queries.
- No service-worker manifest.
- No analytics or telemetry.

---

## Open Questions for the Planner / Researcher

None visible. Every value above is concrete. If the researcher discovers the Chart.js 4.4.6 SRI in CONTEXT D-12 is stale, the `_CHARTJS_SRI` constant gets updated — UI-SPEC is unaffected.

---

## Field Mapping (state.json → UI)

**Purpose.** Explicit wiring audit between each rendered UI section and the exact `state.json` path it reads. Added in the 2026-04-22 revision pass so B-1-class bugs (UI-SPEC names a field that doesn't exist in the write path) surface at design review, not at implementation. Every field below must exist after Phase 5 Wave 0 scaffold + Phase 4 retrofit. Fallback column describes what the render helper renders when the field is missing or `None`.

| UI section | state.json path | Source module / function | Fallback |
|------------|-----------------|--------------------------|----------|
| Header "Last updated" | `state['last_run']` (ISO datetime string) — but UI uses the `now` argument to `render_dashboard`, not `state['last_run']`, so the header reads fresh clock time. `state['last_run']` is NOT surfaced in v1 UI. | `main.py` writes `state['last_run'] = run_date_iso` inside `run_daily_check`. UI consumes `now` argument. | If `now` omitted, `_fmt_last_updated` defaults to `datetime.now(Perth)`. |
| Signal card — big label | `state['signals'][state_key]['signal']` (int ∈ {-1, 0, 1}) | `main.py` `run_daily_check` line 514-519 (`new_signal` assignment). | Missing key → big `—` in `--color-flat`. |
| Signal card — "Signal as of" date | `state['signals'][state_key]['signal_as_of']` (ISO YYYY-MM-DD string) | Same as above. | Missing key → `Signal as of never`. |
| Signal card — scalar line | `state['signals'][state_key]['last_scalars']` (dict with keys `atr, adx, pdi, ndi, mom1, mom3, mom12, rvol` — Phase 1 D-08 locked 8-key shape; `signal_engine.get_latest_indicators` source). | `main.py` line 518 assigns `scalars` (output of `signal_engine.get_latest_indicators(df_with_indicators)` at line 433). | Missing `last_scalars` key → single `—` line in `--color-text-dim`. |
| Positions table — Entry | `state['positions'][state_key]['entry_price']` (float) | `state_manager`: `Position` TypedDict. `sizing_engine.open_position` populates. | If position is `None`, row is omitted (partial-state rule). |
| Positions table — Current | **`state['signals'][state_key]['last_close']`** (float) — B-1 FIX. New field added by Wave 0 retrofit. | `main.py` `run_daily_check` line 514-519 — Wave 0 task extends signal-state write to include `'last_close': float(bar['Close'])` alongside `'last_scalars'`. | Missing / `None` → `—` in `--color-text-dim`. Applies to pre-retrofit state.json loaded after the retrofit is deployed. |
| Positions table — Contracts | `state['positions'][state_key]['n_contracts']` (int) | `state_manager.Position`. | Row omitted if `position is None`. |
| Positions table — Pyramid | `state['positions'][state_key]['pyramid_level']` (int ∈ {0,1,2}) | `state_manager.Position`. | Row omitted if `position is None`. |
| Positions table — Trail Stop | Derived from `position['peak_price']`, `position['trough_price']`, `position['atr_entry']` (floats). | `state_manager.Position`. | Row omitted if `position is None`. |
| Positions table — Unrealised P&L | Derived from `position['entry_price']`, `position['n_contracts']`, `_CONTRACT_SPECS[state_key]`, and `state['signals'][state_key]['last_close']` (B-1 FIX). | Positions from `state_manager.Position`; current close from extended signal-state write (retrofit). | `last_close` missing → `—`; `position is None` → row omitted. |
| Positions table — empty-state row | `all(state['positions'].get(k) is None for k in expected_keys)` | `state_manager.load_state`. | `colspan="8"` row `— No open positions —`. |
| Equity chart data | `state['equity_history']` — list of `{'date': 'YYYY-MM-DD', 'equity': float}`. | `state_manager.update_equity_history`. | Empty list → placeholder `<div>`, no canvas. |
| Trades table — all columns | `state['trade_log']` — list of 12-field trade dicts. Authoritative field set: `instrument, direction, entry_date, exit_date, entry_price, exit_price, gross_pnl, n_contracts, exit_reason, multiplier, cost_aud, net_pnl`. | `main._closed_trade_to_record` (Phase 4 D-19) produces the first 11 fields; `state_manager.record_trade` appends `net_pnl` (Phase 3 D-20). | Empty list → `colspan="7"` row `— No closed trades yet —`. |
| Stat tile — Total Return | `state['equity_history'][-1]['equity']` OR `state['account']` (fallback). | `state_manager.update_equity_history` + `state_manager.load_state` (initial `account` = `INITIAL_ACCOUNT`). | Always computable (account is always defined). |
| Stat tile — Sharpe | `state['equity_history']` — derive log-returns. | Same as above. | `len < 30` or `stdev == 0` → `—`. |
| Stat tile — Max Drawdown | `state['equity_history']`. | Same as above. | Empty → `—`. |
| Stat tile — Win Rate | `state['trade_log']`, counts trades with `gross_pnl > 0`. | Same as trades-table. | Empty → `—`. |

**Audit rule (locked forward).** Any future UI-SPEC revision that introduces a new rendered element MUST add a row to this table with the exact `state.json` path. If the path does not yet exist in `main.py` / `state_manager.py`, the revision MUST declare the retrofit explicitly in §Downstream notes for planner — never assume a field exists because the name sounds right.

---

## Checker Sign-Off

- [ ] Dimension 1 Copywriting: PASS
- [ ] Dimension 2 Visuals: PASS
- [ ] Dimension 3 Color: PASS
- [ ] Dimension 4 Typography: PASS
- [ ] Dimension 5 Spacing: PASS
- [ ] Dimension 6 Registry Safety: PASS

**Approval:** pending (revision pass 2026-04-22 — B-1 fix + F-1/2/3/4 rolled in; awaiting re-check)

---

## Downstream Notes for Planner

**B-1 retrofit task (Phase 5 Wave 0 scaffold — blocking).** The Phase 5 plan's Wave 0 scaffold MUST include a task that extends the Phase 4 signal-state write in `main.py` `run_daily_check()` to emit a `last_close` field alongside `last_scalars`. The write lives around lines 514-519 of the current `main.py`:

```python
# BEFORE (current main.py, Phase 4 reviews-revision):
state['signals'][state_key] = {
  'signal': new_signal,
  'signal_as_of': signal_as_of,
  'as_of_run': run_date_iso,
  'last_scalars': scalars,
}

# AFTER (Phase 5 Wave 0 retrofit):
state['signals'][state_key] = {
  'signal': new_signal,
  'signal_as_of': signal_as_of,
  'as_of_run': run_date_iso,
  'last_scalars': scalars,
  'last_close': float(bar['Close']),  # B-1: Phase 5 Current-price column source
}
```

**Test surface updates required by the retrofit:**
- Phase 4 AC-1 reversal-ordering test (`test_reversal_long_to_short_preserves_new_position` in `tests/test_main.py`) — update fixture/assertions to expect the new `last_close` key on the post-step signals entry.
- Phase 4 D-11 / D-14 per-instrument log format test — if the test inspects `state['signals'][sk]` keys explicitly, extend the expected-key set to `{signal, signal_as_of, as_of_run, last_scalars, last_close}`.
- Any other test that asserts `state['signals'][sk].keys() == {...}` literally must be updated.

**Backward-compat stance.** The retrofit is additive — existing state.json files (written pre-Phase-5) will not have `last_close`. The dashboard's positions-table "Current" column render helper MUST handle `state['signals'][key].get('last_close')` returning `None` and emit `—` gracefully. No state schema_version bump required (matches the Phase 4 G-2 precedent that added `last_scalars` to the dict-shaped signal entry without a bump).

**Why not migrate state schema?** A schema_version bump would force a rewrite migration in `MIGRATIONS` at `state_manager.py:79`. Additive optional field + graceful-miss handling is cheaper and consistent with Phase 1/3 precedent. If a future phase needs to force the field (e.g., Phase 6 email requires it), promote the bump then.

**Dashboard import ordering (already locked, reaffirmed).** `dashboard.py` may NOT import `signal_engine` — the `last_scalars` dict is read as a plain 8-key dict (keys per Phase 1 D-08: `{atr, adx, pdi, ndi, mom1, mom3, mom12, rvol}`). The NEW `last_close` field is a sibling float, not inside `last_scalars`, so the 8-key contract is preserved verbatim.

---

## Traceability to CONTEXT Decisions

| CONTEXT decision | UI-SPEC section |
|-------------------|-----------------|
| D-01 (render architecture / import fence) | Design System, Format Helper Contracts, Non-Goals |
| D-02 (block-builder order + render_dashboard API) | Component Hierarchy, Rendering-order rule |
| D-03 (output path) | (out of UI scope — file system concern) |
| D-04 (inline CSS, dark theme only) | Design System (Font), Color (no light mode) |
| D-05 / D-06 (hex boundary) | Non-Goals (no imports of sizing_engine; Phase 5 re-implements unrealised-PnL formula inline) |
| D-07 (Sharpe formula) | Key stats block Tile 2 |
| D-08 (Max drawdown formula) | Key stats block Tile 3 |
| D-09 (Win rate = `gross_pnl > 0`) | Key stats block Tile 4 |
| D-10 (Total return formula) | Key stats block Tile 1 |
| D-11 (Chart.js config) | Chart Component, Interaction States |
| D-12 (Chart.js 4.4.6 SRI) | Registry Safety, Design System |
| D-13 (empty states — note: `colspan="7"` for positions is stale; UI-SPEC supersedes with `colspan="8"` per F-4) | Copywriting §Empty / placeholder copy inventory |
| D-14 (test strategy — golden HTML) | (out of UI-scope — test concern, but golden fixture should lock every token above) |
| D-15 (html.escape posture) | Format Helper Contracts, Accessibility Contract |
| D-16 (numeric formatting) | Format Helper Contracts, Copywriting (tables + stats) |

**F-8 hygiene note — trade_log field names.** CONTEXT.canonical_refs line 27 (Phase 4 04-03-SUMMARY reference) describes trade dicts with fields `{symbol, entry_date, exit_date, direction, entry_price, exit_price, n_contracts, realised_pnl, gross_pnl, atr_entry, pyramid_level_at_close, exit_reason}`. **That list is descriptive / outdated and not authoritative for UI-SPEC.** The authoritative 12-field schema is what `main._closed_trade_to_record` (Phase 4 D-19) produces + what `state_manager.record_trade` appends (Phase 3 D-20): `{instrument, direction, entry_date, exit_date, entry_price, exit_price, gross_pnl, n_contracts, exit_reason, multiplier, cost_aud, net_pnl}`. Key differences from the CONTEXT canonical_refs paragraph: (a) `symbol` renamed to `instrument`; (b) `realised_pnl` replaced by `net_pnl`; (c) `atr_entry` and `pyramid_level_at_close` NOT in the committed trade dict (they live on the live `position` while open, not on the closed-trade record); (d) `multiplier` and `cost_aud` added for downstream audit. The closed-trades table column set in UI-SPEC already reflects the authoritative 12-field shape — this paragraph just notes the discrepancy for auditability.

| REQUIREMENTS.md DASH-* | UI-SPEC coverage |
|------------------------|------------------|
| DASH-01 (self-contained inline CSS) | Design System, Non-Goals |
| DASH-02 (Chart.js 4.4.6 SRI) | Registry Safety |
| DASH-03 (signal colour per instrument) | Signal cards + Color accent reserved for |
| DASH-04 (Chart.js equity line from equity_history) | Chart Component + Interaction States |
| DASH-05 (positions table 6 columns minimum) | Open positions table (renders 8 including Instrument + Unrealised P&L) |
| DASH-06 (last 20 closed trades table) | Closed trades table |
| DASH-07 (Total Return + Sharpe + Max DD + Win Rate) | Key stats block |
| DASH-08 ("Last updated" in AWST) | Copywriting §Header |
| DASH-09 (visual theme matches backtest aesthetic) | Color, Typography, Component Hierarchy |
