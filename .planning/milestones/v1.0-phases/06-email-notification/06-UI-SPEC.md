---
phase: 6
slug: email-notification
status: draft
shadcn_initialized: false
preset: none
created: 2026-04-22
sibling_spec: .planning/phases/05-dashboard/05-UI-SPEC.md (shared palette + formatter semantics)
---

# Phase 6 — UI Design Contract (Email)

> Visual and interaction contract for the Phase 6 Resend HTML email. Consumed
> by `gsd-planner` (task values + inline-CSS constants), `gsd-executor`
> (verbatim strings + copy), `gsd-ui-checker` (6-dimension sign-off), and
> `gsd-ui-auditor`. Upstream locks (do NOT re-open): palette (PROJECT.md +
> CONTEXT D-02), table-based layout + 600px wrapper (CONTEXT D-07), no
> `@media` query / fluid-hybrid (CONTEXT D-08), inline-CSS only + `<meta>`
> viewport (CONTEXT D-07/08 + PROJECT.md), MUST-render clients Gmail web +
> iOS Mail (CONTEXT D-09), 7-section body order (CONTEXT D-10), ACTION
> REQUIRED red-border block structure (CONTEXT D-11), emoji subject prefix
> `🔴` on change / `📊` on no-change with `[TEST]` before emoji for --test
> (CONTEXT D-04), hex-lite import fence (CONTEXT D-01), XSS escape posture
> (CONTEXT D-15 inherited from Phase 5), Resend retry policy and graceful
> degradation (CONTEXT D-12, D-13), never-crash invariant (PROJECT.md +
> CONTEXT D-13 / CLAUDE.md).

> **Sibling alignment with Phase 5.** Visual language (palette, formatter
> output, instrument display names, exit-reason display map, numeric
> formatting) is intentionally identical to Phase 5 dashboard. Implementation
> differs where email-client constraints bite (inline-CSS only, no
> `font-variant-numeric: tabular-nums`, no `<sub>` subscripts for Mom
> period indices, no CSS variables, belt-and-braces `bgcolor` attribute on
> every layout table). Formatters are DUPLICATED into `notifier.py` rather
> than imported from `dashboard.py` per CONTEXT D-02. See §Phase 5 Alignment
> Table at the bottom.

---

## Design System

| Property | Value |
|----------|-------|
| Tool | none — stdlib Python f-string builder (CONTEXT D-01 + D-02) |
| Preset | not applicable (no component framework; PROJECT.md Constraints forbid React/Vue/build step) |
| Component library | none — per-section `_render_*` helpers in `notifier.py` (CONTEXT D-02) |
| Icon library | none — zero external assets; no `<img>` tags in v1; pure Unicode glyphs only. **Glyph budget:** `{— (U+2014 em-dash), · (U+00B7 middle dot), → (U+2192 rightwards arrow), $, %, +, -, ,, ., :, /, ━ (U+2501 box drawings heavy horizontal), 🔴 (U+1F534 red circle, SUBJECT ONLY), 📊 (U+1F4CA bar chart, SUBJECT ONLY)}`. No other non-ASCII glyph may appear in the rendered body. |
| Font stack (body) | System font only — NO webfont: `-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif`. Inline on `<body>` and repeated on every layout-level `<td>` (Outlook resets font on each cell). |
| Font stack (numeric) | Monospace fallback chain, applied inline to numeric `<td>` cells: `'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace`. `font-variant-numeric: tabular-nums` is **NOT used** — email clients (Outlook, older iOS Mail) drop the declaration silently; monospace is the portable fallback. |

**Lockdown notes.**

- No webfonts, no icon fonts, no SVG, no `<img>` tags in v1. Every glyph renders from the OS's installed fonts. (Phase 6 scope §"No attachment support" per CONTEXT Scope Boundaries.)
- No CSS custom properties (`var(--...)`). Outlook 2016+ still rejects them. Palette hex literals are interpolated directly by f-string at compose time.
- No CSS classes, no `<style>` block, no external stylesheet. Every property is inline on the element (PROJECT.md Constraints §"Email rendering: Inline CSS only").
- No `<script>` of any kind. Email clients strip JS universally; Chart.js is not portable to email.
- No `<link>` tags beyond the required `<meta charset>` + `<meta viewport>` in `<head>`.

**Emoji rendering caveat (D-09 nice-to-have).** The two subject-line emojis render as color glyphs on Gmail web (macOS/iOS rendering), iOS Mail, Apple Mail macOS, and Gmail Android. Outlook desktop renders them via Segoe UI Emoji (monochrome glyph — still distinguishable). If Gmail web strips them (known edge case pre-Q1 2023, stable since), subject degrades to `[TEST] 2026-04-22 — SPI200 LONG, AUDUSD FLAT — Equity $101,234` — still readable. Document the limitation; don't engineer around it.

---

## Spacing Scale

Email visual density tolerates less whitespace than a desktop dashboard. 4/8-point baseline; every padding/margin is a multiple of 4. Values differ from Phase 5 (dashboard) because email max-width is 600px vs 1100px and mobile fall-through to 375px is the dominant reading viewport (CONTEXT D-08).

| Token | Value | Usage (inline on `padding` / cell-spacing) |
|-------|-------|--------------------------------------------|
| `email-space-1` | 4px | Inline gaps between inline spans (e.g., `→` arrow padding), middle-dot separators |
| `email-space-2` | 8px | Table-cell vertical padding in dense tables (positions/trades body rows) |
| `email-space-3` | 12px | Table-cell horizontal padding in dense tables; ACTION REQUIRED block vertical padding per CONTEXT D-11 |
| `email-space-4` | 16px | Default gap between tightly-coupled elements; ACTION REQUIRED block horizontal padding per CONTEXT D-11; outer wrapper viewport-padding (`<td align="center" style="padding:16px 8px;">` per CONTEXT D-07) |
| `email-space-5` | 20px | Section-internal vertical padding (`<td>` padding inside signal-status/positions/trades/P&L section cells) |
| `email-space-6` | 24px | Section-internal horizontal padding on wider sections; header cell padding |
| `email-space-8` | 32px | Gap between major body sections (header → ACTION REQUIRED → signal-status → positions → today's P&L → trades → footer). Rendered as a section-divider `<tr><td height="32" style="height:32px;font-size:0;line-height:0;">&nbsp;</td></tr>` between section tables. |

**Layout container (CONTEXT D-07 locked).**

| Property | Value |
|----------|-------|
| Outer wrapper | `<table role="presentation" width="100%" bgcolor="#0f1117" style="background:#0f1117;">` fills the client viewport |
| Outer wrapper cell padding | `padding:16px 8px;` — 16px top/bottom, 8px left/right so the surface card has breathing room at 375px viewport |
| Inner content card max-width | `style="max-width:600px;width:100%;"` — fluid-hybrid; scales to viewport below 600px |
| Inner content bg / border | `bgcolor="#161a24" style="background:#161a24;border:1px solid #252a36;"` (belt-and-braces bgcolor attribute for Outlook + Gmail dark-mode forced-lightening) |
| Section-cell horizontal padding | 24px (`email-space-6`) on header / ACTION REQUIRED / P&L rollup section cells; 12px (`email-space-3`) on table wrapper cells so the table edges touch the card border cleanly |
| Section-cell vertical padding | 20px (`email-space-5`) top/bottom inside each section cell |
| Section → section gap | 32px (`email-space-8`) — rendered as a dedicated `<tr>` spacer row between section tables (no collapsing-margin behaviour in email HTML) |

**Exceptions.** None. The 4px `email-space-1` and 8px `email-space-2` tokens exist because email tables become unreadable with 16px cell padding at 375px viewport — 8px body padding is the tightest the Phase 5 UI-SPEC review validated as still-readable. Documented to prevent drift; executor uses exactly these values, not "8-12px-ish".

---

## Typography

System fonts only. **Four roles. Two weights (400 regular, 600 semibold) only.** No italic, no underline (no links in the email body per v1 scope). Email clients differ from browsers; sizes below are validated on Gmail web + iOS Mail per CONTEXT D-09 MUST-render clients.

| Role | Size | Weight | Line Height | Used By |
|------|------|--------|-------------|---------|
| `email-fs-body` | 14px | 400 | 1.5 | Table body cells (positions, trades, signal-status), ACTION REQUIRED per-instrument diff paragraphs, P&L rollup labels, header metadata |
| `email-fs-label` | 12px | 600 | 1.4 | Table `<th>` headers, footer disclaimer prose, P&L rollup small-print ("from yesterday's close", "since inception"). **Uppercase + `letter-spacing:0.04em` on `<th>` only** — NOT on footer (email footer reads as prose, not eyebrow labels). |
| `email-fs-heading` | 20px | 600 | 1.3 | Section headings (`Signal Status`, `Open Positions`, `Today's P&L`, `Running Equity`, `Last 5 Closed Trades`), ACTION REQUIRED headline (weight 700 OK as a controlled exception — see below) |
| `email-fs-display` | 22px | 600 | 1.2 | Header app-title (`Trading Signals`), running-equity big number, today's-change big number |

**Weight exception.** The ACTION REQUIRED headline (literal string `ACTION REQUIRED`, CONTEXT D-11) uses weight 700 instead of 600 — this is the ONE deliberate typographic emphasis in the email body and lifts the block above the normal section heading weight. Still inside "2 weights" budget if we count the exception. Documented explicitly to prevent reviewer drift: any OTHER weight-700 appearance is a bug.

**Font-size rationale vs Phase 5 dashboard.**

- Dashboard uses 14 / 12 / 20 / 28 at a 1100px max container on a large viewport.
- Email uses 14 / 12 / 20 / 22 at a 600px max container with dominant-mobile reading context.
- Display tier drops 28 → 22 because 28px renders as visual shouting at 375px viewport; 22 is the readable-while-dense sweet spot for the running-equity number.

**Letter-spacing.** `<th>` cells: `letter-spacing:0.04em;text-transform:uppercase;`. No other element gets letter-spacing (footer prose stays normal-case, normal-tracking).

**Numeric cells.** Price / equity / P&L cells in all tables and rollup values use the monospace fallback stack (see Design System §Font stack (numeric)). **No** `font-variant-numeric: tabular-nums` declaration — email clients drop it. The monospace stack delivers equivalent column alignment at the cost of a slight aesthetic shift vs the dashboard; accepted.

**No weight outside {400, 600, 700-for-ACTION-REQUIRED-only}.** No italic. No underline. No `text-decoration`. Keeps cross-client font-coverage predictable.

---

## Color

60 / 30 / 10 split. Single dark theme (CONTEXT D-04 scope boundary; email inherits the dashboard lock). All colour values below MUST be imported from `system_params` after the D-02 palette retrofit (see §Downstream Notes).

| Role | Hex | system_params constant | Usage |
|------|-----|------------------------|-------|
| Dominant (60%) — outer viewport bg | `#0f1117` | `_COLOR_BG` | Outer wrapper `<table>` `bgcolor` + style, `<body>` `style:background` |
| Secondary (30%) — inner card surface | `#161a24` | `_COLOR_SURFACE` | Inner content `<table>` `bgcolor` + style; ACTION REQUIRED block bg; every section cell bg |
| Secondary — 1px borders | `#252a36` | `_COLOR_BORDER` | Inner card outer border; table `<thead>` bottom border; table row dividers (bottom border on each `<tr>`); section dividers (none — spacer rows handle gaps) |
| Text primary | `#e5e7eb` | `_COLOR_TEXT` | Body text, table values, header app-title, ACTION REQUIRED headline, rollup big numbers |
| Text secondary | `#cbd5e1` | `_COLOR_TEXT_MUTED` | Table headers, "signal_as_of" lines, rollup small-print labels ("from yesterday's close"), header metadata ("Last updated 2026-04-22 09:00 AWST"), zero P&L values |
| Text tertiary / empty-state / dim | `#64748b` | `_COLOR_TEXT_DIM` | Empty-state table rows ("No open positions"), footer disclaimer body, "signal_as_of: never" |
| Accent LONG (10%) | `#22c55e` | `_COLOR_LONG` | LONG signal label chips (signal-status table + positions table), positive P&L numbers, positive "Today's change" |
| Accent SHORT (10%) | `#ef4444` | `_COLOR_SHORT` | SHORT signal label chips, negative P&L numbers, negative "Today's change", **ACTION REQUIRED 4px left-border** per CONTEXT D-11 |
| Accent FLAT (10%) | `#eab308` | `_COLOR_FLAT` | FLAT signal label chip, "signal: —" pre-first-run placeholder |
| Zero / neutral P&L | `#cbd5e1` | `_COLOR_TEXT_MUTED` | P&L cell exactly at `$0.00` (Phase 5 D-16 + sibling-consistency lock) |

**Accent reserved for** (explicit list — never "all interactive elements" since there are no interactive elements):

1. Signal-status table — `Signal` column cell: `LONG` / `SHORT` / `FLAT` label coloured via `_COLOR_LONG` / `_COLOR_SHORT` / `_COLOR_FLAT`.
2. Positions table — `Direction` column cell: `LONG` / `SHORT` label coloured.
3. Positions table — `Unrealised P&L` column cell: sign-coloured via `_fmt_pnl_with_colour_email`.
4. Trades table — `Direction` column cell: `LONG` / `SHORT` label coloured.
5. Trades table — `P&L` column cell: sign-coloured via `_fmt_pnl_with_colour_email`.
6. Today's P&L rollup — big number coloured per sign.
7. ACTION REQUIRED — `border-left:4px solid #ef4444` per CONTEXT D-11.

No accent used for: section headings, table headers, footer, empty-state rows, any other chrome. Accent saturation stays ≤10% of visible pixel coverage by construction.

**Dark-mode forced-lightening handling (Gmail web / iOS Mail / Apple Mail).** All three clients implement auto-dark-mode that can invert our already-dark theme. Defence in depth:

- Layer 1 — `bgcolor="#0f1117"` attribute on outer wrapper table AND `bgcolor="#161a24"` on inner card table. Legacy attribute overrides inline-style inversion on some clients.
- Layer 2 — `<meta name="color-scheme" content="dark only">` in `<head>`. Gmail web + Apple Mail macOS respect; Outlook + Gmail Android ignore but don't choke.
- Layer 3 — `<meta name="supported-color-schemes" content="dark">` in `<head>`. Apple Mail-specific opt-out of auto-lightening.
- Layer 4 — inline `style="background:#0f1117;color:#e5e7eb;"` on `<body>` and on every major layout `<td>` (Outlook resets background inheritance at each cell boundary).

Known residual risk (documented, not engineered-around per CONTEXT D-09): Gmail Android under Android system dark-mode force-inverts some greens. The LONG signal label may render slightly off-hue on Gmail Android; readable, not mis-signal. Nice-to-have target — not gated.

**Destructive.** Dual-purpose with SHORT — same hex `#ef4444`. The only "destructive" signalling in the email is the ACTION REQUIRED red left-border. The block is informational ("here's what changed"), not a destructive action; the red semantic is reused deliberately to carry "attention required" weight without introducing a second red hue.

**Contrast audit** (WCAG AA 4.5:1 body / 3:1 UI chrome / label ≥ 4.5:1 — identical to Phase 5 lock; surfaces + accents are reused).

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
| `#ef4444` SHORT | 4.5:1 | PASS AA (at the contrast floor — do NOT shift surface lighter) |
| `#eab308` FLAT | 8.6:1 | PASS AAA |

Rule: **`#64748b` is body-copy-only** (footer disclaimer, empty-state rows). Never apply to 12px labels or table headers.

---

## Copywriting Contract

The email is a **daily push**. There are no CTAs in the traditional sense — the "call to action" is the ACTION REQUIRED block's per-instrument instructions (CONTEXT D-11). Copy below locks every operator-visible string.

### Subject line (CONTEXT D-04)

Template: `{prefix} {emoji} {YYYY-MM-DD} — SPI200 {SIG}, AUDUSD {SIG} — Equity ${X,XXX}`

| Case | Exact example |
|------|---------------|
| Signal change, production | `🔴 2026-04-22 — SPI200 LONG, AUDUSD FLAT — Equity $101,234` |
| No change, production | `📊 2026-04-22 — SPI200 LONG, AUDUSD LONG — Equity $101,234` |
| Signal change, `--test` | `[TEST] 🔴 2026-04-22 — SPI200 LONG, AUDUSD FLAT — Equity $101,234` (CONTEXT D-04: TEST prefix BEFORE emoji) |
| No change, `--test` | `[TEST] 📊 2026-04-22 — SPI200 LONG, AUDUSD LONG — Equity $101,234` |
| First run (all old_signals None) | `📊 2026-04-22 — SPI200 LONG, AUDUSD FLAT — Equity $100,000` (CONTEXT D-06: first-run is treated as no-change) |

**Character budget.** Gmail web shows ~70 chars before truncation; iOS Mail shows ~35-40 chars on iPhone SE portrait. Measured:

- `📊 2026-04-22 — SPI200 LONG, AUDUSD LONG — Equity $101,234` = 58 chars (emoji counted as 1 grapheme). Fits Gmail web; truncates in iOS Mail preview at `📊 2026-04-22 — SPI200 LONG, AUD…` (still conveys date + SPI signal + emoji).
- `[TEST] 🔴 2026-04-22 — SPI200 SHORT, AUDUSD SHORT — Equity $1,234,567` = 69 chars (worst case — equity in millions + TEST prefix + both SHORT). Fits Gmail web at exactly the limit; iOS Mail shows first `[TEST] 🔴 2026-04-22 — SPI200 S…` (operator still sees TEST + change emoji + date + first instrument signal).

**Truncation strategy:** accept iOS Mail preview truncation — the full subject is visible when the email is opened. Do NOT abbreviate instrument labels (operator legibility wins over preview-line completeness; CONTEXT D-04 locks `SPI200` / `AUDUSD` as bare words in the subject, not `SPI`/`AUD`).

**Equity rounding.** Subject uses `int(round(account))` then `f'${int(round(account)):,}'` — whole-dollar precision. Body uses 2 decimal places. Precedent: Phase 5 stat-tile rollups use whole-dollar or signed-percent, never matched-decimal across widgets. (CONTEXT D-04 locks this.)

**First-run subject equity.** First run shows `$100,000` (the `INITIAL_ACCOUNT` constant, already written into `state['account']` by Phase 3 `reset_state`; no migration needed).

### Body sections (seven, in CONTEXT D-10 locked order)

#### 1. Header

Rendered as the first section cell inside the card.

| Element | Exact copy / format |
|---------|---------------------|
| App title | `Trading Signals` — rendered as an `<h1>` semantic element, `email-fs-display` 22px / weight 600 / `_COLOR_TEXT`. NOT an image, NOT a logo in v1. |
| Subtitle (one line below title) | `SPI 200 & AUD/USD mechanical system` — rendered as a `<p>`, `email-fs-body` 14px / weight 400 / `_COLOR_TEXT_MUTED`, margin 4px top / 8px bottom. |
| Last-updated label | `Last updated` — `email-fs-label` 12px / weight 600 / `_COLOR_TEXT_MUTED` / uppercase / letter-spacing 0.04em. |
| Last-updated value | `YYYY-MM-DD HH:MM AWST` (example: `2026-04-22 09:00 AWST`). Derived: `now.astimezone(pytz.timezone('Australia/Perth')).strftime('%Y-%m-%d %H:%M AWST')`. Minute precision, no seconds, explicit AWST suffix. Matches Phase 5 `_fmt_last_updated` output verbatim (cross-phase consistency). |
| Signal-as-of row | `Signal as of YYYY-MM-DD` — shows the most-recent per-instrument `signal_as_of` (if both match, render once; if they differ, render `Signal as of YYYY-MM-DD (SPI 200)  ·  YYYY-MM-DD (AUD / USD)` — rare case where instruments last closed on different dates). `email-fs-body` 14px / `_COLOR_TEXT_MUTED`. |

**No operator name, no logo, no version string, no build SHA.** The header is title + subtitle + metadata. Reviewer drift guard: any addition here requires a CONTEXT amendment.

#### 2. ACTION REQUIRED block (conditional — CONTEXT D-10, D-11)

Rendered immediately below the header, ABOVE the signal-status table, ONLY when `any_signal_changed` is True (CONTEXT D-06 predicate — first-run counts as no-change; both `old_signal` and `new_signal` must both be non-None and differ).

Structural spec:

```html
<tr>
  <td style="padding:12px 16px;
             background:#161a24;
             border-left:4px solid #ef4444;
             color:#e5e7eb;
             font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;
             font-size:14px;
             line-height:1.5;">
    <p style="margin:0 0 8px 0;
              font-size:20px;
              font-weight:700;
              color:#e5e7eb;
              letter-spacing:0.02em;">
      ━━━ ACTION REQUIRED ━━━
    </p>
    <!-- one <p> per changed instrument, per D-11 copy table below -->
  </td>
</tr>
```

Headline: `━━━ ACTION REQUIRED ━━━` — literal, U+2501 box-drawing heavy horizontal, three glyphs on each side of the words, separated by a single space. Per CONTEXT D-11.

**Per-instrument diff paragraphs — locked copy truth table (expands CONTEXT D-11 beyond the 2 examples):**

| Old signal | New signal | Instrument label | Copy rendered |
|------------|-----------|------------------|---------------|
| `LONG` | `SHORT` | SPI 200 | `SPI 200: LONG → SHORT`<br>`Close existing LONG position ({n} contract{s} @ entry ${entry_price}).`<br>`Open new SHORT position.` |
| `SHORT` | `LONG` | SPI 200 | `SPI 200: SHORT → LONG`<br>`Close existing SHORT position ({n} contract{s} @ entry ${entry_price}).`<br>`Open new LONG position.` |
| `FLAT` (`0`) | `LONG` | SPI 200 | `SPI 200: FLAT → LONG`<br>`Open new LONG position.` |
| `FLAT` (`0`) | `SHORT` | SPI 200 | `SPI 200: FLAT → SHORT`<br>`Open new SHORT position.` |
| `LONG` | `FLAT` (`0`) | SPI 200 | `SPI 200: LONG → FLAT`<br>`Close existing LONG position ({n} contract{s} @ entry ${entry_price}).` |
| `SHORT` | `FLAT` (`0`) | SPI 200 | `SPI 200: SHORT → FLAT`<br>`Close existing SHORT position ({n} contract{s} @ entry ${entry_price}).` |
| `None` (no prior) | any | any | **Not rendered.** First-run is no-change per CONTEXT D-06. |

Identical truth table for `AUD / USD`. The instrument label uses the display-name mapping from §Copywriting Contract §Signal status table below.

**Pluralisation.** `contract{s}` resolves to `contract` when `n_contracts == 1`, `contracts` otherwise. Executor implements as `'contract' if n_contracts == 1 else 'contracts'`. Example: `(1 contract @ entry $8,204.50)`, `(2 contracts @ entry $8,204.50)`.

**Entry price.** Read from `state['positions'][state_key]['entry_price']` BEFORE the run — i.e., the CURRENTLY open position that will be closed. `notifier.send_daily_email` is called AFTER `run_daily_check` has mutated state (production `--force-email` path) OR AFTER compute but before persist (`--test` path); the ACTION REQUIRED diff is driven by `old_signals` (pre-run) + the CURRENTLY open position pulled from POST-run `state['positions']`. Wait — there's a semantic nuance: on LONG→SHORT in a single run, Phase 4 AC-1 closes LONG and opens SHORT atomically; the POST-run `state['positions'][state_key]` holds the NEW SHORT position, not the closed LONG. We need the CLOSED position for the diff copy.

**Resolution (Claude's Discretion delegation to planner — documented and surfaced for review):** the ACTION REQUIRED "Close existing {OLD_DIR} position (N contracts @ entry $X)" line needs the PRE-CLOSE position (contracts + entry_price). Source of truth for this data:

- Option A — read from `state['trade_log'][-1]` when `trade_log[-1]['exit_date'] == run_date_iso AND trade_log[-1]['instrument'] == state_key`. That record has `direction` (old), `n_contracts`, `entry_price` verbatim.
- Option B — pass the closed-trade record forward from `run_daily_check` to `send_daily_email`. This duplicates the `run_daily_check` refactor CONTEXT D-15 already flags (the tuple return `(rc, state, old_signals, closed_trades_this_run)`).

Recommendation for the planner: **Option A** — read from `trade_log` tail. Rationale: (1) zero signature churn on `run_daily_check`, (2) the tail read is deterministic (reversal closes ALWAYS prepend a trade_log entry on the same run_date_iso; stop-hit closes same), (3) a simple helper `_closed_position_for_instrument_on(state, state_key, run_date_iso)` keeps the logic inside `notifier.py` and testable.

**First-run guard.** If `old_signals[sym] is None`, that instrument is NOT rendered in the ACTION REQUIRED block. If BOTH are None, the ACTION REQUIRED block is NOT rendered at all (and the subject uses `📊`). See CONTEXT D-06.

#### 3. Signal status table (NOTF-04)

Two data rows (SPI200, AUDUSD), one header row. Five columns.

Header columns (exact text, exact order, left→right):

| # | Header | Data source / format | Alignment |
|---|--------|----------------------|-----------|
| 1 | `Instrument` | Display name via `_INSTRUMENT_DISPLAY_NAMES_EMAIL = {'SPI200': 'SPI 200', 'AUDUSD': 'AUD / USD'}` | left |
| 2 | `Signal` | Label chip `LONG` / `SHORT` / `FLAT` / `—` coloured via `_COLOR_LONG` / `_COLOR_SHORT` / `_COLOR_FLAT`, weight 600, inline `<span style="color:#22c55e">LONG</span>` | left |
| 3 | `As of` | `state['signals'][key]['signal_as_of']` ISO string (e.g. `2026-04-21`). Empty: `never` in `_COLOR_TEXT_DIM` | left |
| 4 | `ADX` | `_fmt_scalar(state['signals'][key]['last_scalars']['adx'], 1)` → `24.3`; em-dash on missing | right (monospace) |
| 5 | `Mom` | Single mid-dot-joined composite: `{+x.x%} · {+x.x%} · {+x.x%}` in order Mom₁ · Mom₃ · Mom₁₂. Each value via `_fmt_percent_signed_email`. Empty: single `—`. | right (monospace) |

**Why not 6 columns (separate Mom₁ / Mom₃ / Mom₁₂)?** At 375px viewport, 6 numeric columns force horizontal scroll inside the table. The composite Mom cell carries the same data in one row. Trade-off: reader parses left-to-right ratio (short vs long horizon). Acceptable and consistent with the Phase 5 signal-card scalar line (also composite via middle-dots).

**No Mom period subscripts in email.** Phase 5 dashboard uses `Mom<sub>1</sub>`, `Mom<sub>3</sub>`, `Mom<sub>12</sub>`. Email drops the subscripts entirely and relies on column ordering (Mom₁ first, Mom₃ second, Mom₁₂ third) communicated by a header footnote below the table: `<p style="margin:4px 12px 0;font-size:11px;color:#cbd5e1;">Mom reads as 21d · 63d · 252d</p>`. Rationale: Outlook and Apple Mail strip `<sub>` inconsistently; the footnote is portable.

**Row styling.** Each row: `bgcolor="#161a24"` cell, 8px vertical / 12px horizontal padding, bottom border 1px solid `_COLOR_BORDER`. No zebra striping (only 2 data rows — striping would be visual noise).

**Empty state.** Per CONTEXT D-13 / Phase 5 D-13: pre-first-run, missing `state['signals'][key]` → render the row with `Signal` = `—` in `_COLOR_FLAT`, `As of` = `never` in `_COLOR_TEXT_DIM`, `ADX` = `—`, `Mom` = single `—`. The row STILL renders (table never collapses to a single empty-state row in this section — both instruments always show, because both are first-class data rows, not opt-in like positions).

#### 4. Open positions table (CONTEXT D-10: 7 columns, pyramid-level DROPPED vs dashboard's 8)

Header columns (exact text, exact order, left→right):

| # | Header | Data source / format | Alignment |
|---|--------|----------------------|-----------|
| 1 | `Instrument` | `_INSTRUMENT_DISPLAY_NAMES_EMAIL` (same mapping as signal-status) | left |
| 2 | `Direction` | `LONG` / `SHORT` chip, coloured; weight 600 | left |
| 3 | `Entry` | `_fmt_currency_email(position['entry_price'])` → `$7,412.50` | right (mono) |
| 4 | `Current` | `_fmt_currency_email(state['signals'][key]['last_close'])`. Missing / None → `—` in `_COLOR_TEXT_DIM`. **This is the B-1 field already retrofitted by Phase 5 Wave 0** — Phase 6 reuses it verbatim. | right (mono) |
| 5 | `Contracts` | `position['n_contracts']` (integer, no commas for single-digit) | right (mono) |
| 6 | `Trail Stop` | Derived inline via re-implemented math (see below) → `_fmt_currency_email`. Missing inputs → `—` | right (mono) |
| 7 | `Unrealised P&L` | Derived inline via re-implemented math → `_fmt_pnl_with_colour_email`. `last_close` missing → `—` | right (mono) |

**Why no Pyramid column?** CONTEXT D-10 locks 7 cols for email (vs 8 for dashboard). The pyramid-level detail is dashboard-specific; the email targets the "what do I need to do today" operator question, which is answered by the ACTION REQUIRED block + open-positions status. Pyramid level is debug-grade info.

**Re-implemented math (identical formulas to Phase 5, re-duplicated in `notifier.py` per CONTEXT D-02 hex rule).** Must NOT import `sizing_engine` (hex fence per CONTEXT D-01).

- Trail stop (LONG): `position['peak_price'] - 3.0 * position['atr_entry']`
- Trail stop (SHORT): `position['trough_price'] + 2.0 * position['atr_entry']`
- Unrealised P&L (LONG):  `current = state['signals'][state_key]['last_close']`; `pnl = (current - entry) * n_contracts * multiplier - (cost_aud * n_contracts / 2)`
- Unrealised P&L (SHORT): `current = state['signals'][state_key]['last_close']`; `pnl = (entry - current) * n_contracts * multiplier - (cost_aud * n_contracts / 2)`
- Multiplier/cost lookup via `_CONTRACT_SPECS_EMAIL = {'SPI200': (SPI_MULT, SPI_COST_AUD), 'AUDUSD': (AUDUSD_NOTIONAL, AUDUSD_COST_AUD)}` imported from `system_params` (which already hosts the constants post-Phase-2 D-11 migration).

**Opening-half cost subtraction.** Mirrors Phase 2 `compute_unrealised_pnl` exactly per CLAUDE.md §Operator Decisions + Phase 6 CONTEXT inherited from D-13. Phase 6 test surface will lock the formula via one hand-computed fixture (sample_state_with_change.json includes a SPI200 LONG at known entry + known ATR + known last_close; expected unrealised_pnl is pre-computed in the test).

**Row styling.** Same as signal-status: 8px vertical / 12px horizontal cell padding, 1px bottom border per row in `_COLOR_BORDER`. No zebra striping.

**Empty state.** When `all(state['positions'].get(k) is None for k in ['SPI200', 'AUDUSD'])` (CONTEXT D-13): render ONE `<tr>` with `<td colspan="7">` containing the copy `— No open positions —` (em-dash, space, words, space, em-dash) in `_COLOR_TEXT_DIM`, centered, 16px padding (`email-space-4`).

**Partial state** — if SPI200 has a position but AUDUSD does not: render only the SPI200 row. Do not render a placeholder for AUDUSD. The empty-state row appears only when the whole `positions` dict is all-None.

#### 5. Today's P&L + Running Equity rollup (CONTEXT D-10 section 5)

Two stat lines rendered as a two-row table inside a single section cell. No card-within-a-card — the section cell IS the card.

| Row | Label (exact copy) | Value |
|-----|---------------------|-------|
| 1 | `Today's change` | `_fmt_pnl_with_colour_email(change)` — coloured big number, `email-fs-display` 22px / weight 600 / monospace. Small-print below label: `from yesterday's close` (`email-fs-label` 12px / `_COLOR_TEXT_MUTED`, not uppercase). Em-dash `—` (single glyph, `_COLOR_TEXT_DIM`) when insufficient equity points. |
| 2 | `Running equity` | `_fmt_currency_email(equity)` — big number, same 22px/mono treatment; NOT sign-coloured (equity is an absolute, not a delta). Small-print below label: `{+1.23%} since inception` — the signed percent comes from `_fmt_percent_signed_email((equity - INITIAL_ACCOUNT) / INITIAL_ACCOUNT)` coloured LONG/SHORT/muted by sign. |

**Derivation.**

- `equity = state['equity_history'][-1]['equity']` when `equity_history` is non-empty, else `state['account']` (Phase 3 initial state: equals `INITIAL_ACCOUNT` exactly). Always defined.
- `change = equity_history[-1]['equity'] - equity_history[-2]['equity']` when `len(equity_history) >= 2`. Otherwise `None` → render em-dash `—` in `_COLOR_TEXT_DIM` with small-print `from yesterday's close` still visible (label/small-print stays, the BIG NUMBER is the em-dash).
- `since_inception = (equity - INITIAL_ACCOUNT) / INITIAL_ACCOUNT`. Always defined (INITIAL_ACCOUNT is constant). Signed percent, coloured by sign: positive → `_COLOR_LONG`, negative → `_COLOR_SHORT`, zero → `_COLOR_TEXT_MUTED`.

**Visual hierarchy.** Label (12px muted) above value (22px mono). Small-print (12px muted, un-uppercased) below value. 8px gap between label and value; 4px gap between value and small-print. Each row has 20px vertical padding from the next row.

**Layout.** At the 600px desktop width, the two rows stack vertically inside a single section cell with a 32px gap. At 375px, still stacks vertically (same layout — no responsive break). NOT two side-by-side columns: the small-print subtitle under each value would truncate on mobile.

#### 6. Last 5 closed trades table (CONTEXT D-10 section 6)

Header columns (exact text, exact order, left→right). 5 columns, 5 data rows max. Dashboard shows 7 columns × 20 rows; email shows 5 × 5 for mobile-fit.

| # | Header | Data source / format | Alignment |
|---|--------|----------------------|-----------|
| 1 | `Closed` | `trade['exit_date']` (ISO YYYY-MM-DD; static string) | left |
| 2 | `Instrument` | Display name via `_INSTRUMENT_DISPLAY_NAMES_EMAIL` (mapped from `trade['instrument']`) | left |
| 3 | `Direction` | `LONG` / `SHORT` chip, same colour treatment as positions table | left |
| 4 | `Entry → Exit` | `_fmt_currency_email(entry_price)` → `_fmt_currency_email(exit_price)` with the U+2192 `→` between them (glyph-budget approved). Single line; on mobile (<400px) the cell can wrap — `white-space:normal` inline. | right (mono) |
| 5 | `P&L` | `_fmt_pnl_with_colour_email(trade['net_pnl'])` — uses `net_pnl` (state_manager.record_trade's D-20 appended key, net of closing half-cost). NOT `gross_pnl`. | right (mono) |

**Dropped vs dashboard.** Dashboard renders Contracts and Reason columns; email drops both. Rationale: 7 columns at 375px breaks; operator's actionable email-question is "did the system close anything profitably today" — direction + entry/exit + net P&L answers that. Contracts and exit-reason context is available in the dashboard when the operator wants deeper review.

**Row order.** Newest first. Slice in render helper: `state['trade_log'][-5:][::-1]` (last 5, reversed so most-recent is top).

**Row styling.** 8px vertical / 12px horizontal cell padding. Bottom border 1px solid `_COLOR_BORDER` between rows.

**Empty state.** `state['trade_log'] == []`: render ONE `<tr>` with `<td colspan="5">` containing `— No closed trades yet —` in `_COLOR_TEXT_DIM`, centered, 16px padding.

**Skipped-size rows.** State-manager's `_validate_trade` rejects `n_contracts <= 0` (Phase 3 D-19), so such rows CANNOT reach `trade_log`. Skipped trades surface in `state['warnings']`, which is NOT rendered in the email body in Phase 6 (NOTF-10 warnings carry-over is Phase 8). Email does not render skipped-size rows; consistent with Phase 5.

#### 7. Footer disclaimer (CONTEXT D-10 section 7)

Rendered inside the inner content card as the last section cell. Separated from the trades table by a 32px (`email-space-8`) spacer row.

| Element | Exact copy / format |
|---------|---------------------|
| Disclaimer line 1 | `Signal-only system. Not financial advice.` — `email-fs-label` 12px / weight 400 (NOT 600; footer reads as prose, not eyebrow) / `_COLOR_TEXT_DIM` / centered / no uppercase / no letter-spacing |
| Sender line | `Trading Signals — sent by signals@carbonbookkeeping.com.au` — `email-fs-label` 12px / weight 400 / `_COLOR_TEXT_DIM` / centered. Email address is plain text, NO `<a href="mailto:...">` — v1 has no links in the body per scope. |
| Run-date line | `Run date: YYYY-MM-DD` (example: `Run date: 2026-04-22`) — `email-fs-label` 12px / weight 400 / `_COLOR_TEXT_DIM` / centered. Derived from `run_date.strftime('%Y-%m-%d')` (AWST calendar day, matches subject). |

Each footer line is its own `<p>` with 4px top/bottom margin. Centered via `text-align:center;` on the section cell.

**No company name, no ABN, no unsubscribe link.** V1 is a single-operator tool (operator IS the recipient). Unsubscribe UX is not applicable. Adding a footer unsubscribe link is deferred — CONTEXT Scope Boundaries explicitly excludes it.

### Empty / placeholder copy inventory

Cross-section one-line lookup for the checker:

| Context | Exact copy | Colour token |
|---------|-----------|--------------|
| Signal-status row — missing `state['signals'][key]` | `Signal:` `—` / `As of:` `never` / `ADX:` `—` / `Mom:` `—` | `_COLOR_FLAT` for the signal `—`, `_COLOR_TEXT_DIM` for the others |
| Positions table — all None | `— No open positions —` (colspan=7) | `_COLOR_TEXT_DIM` |
| Trades table — empty list | `— No closed trades yet —` (colspan=5) | `_COLOR_TEXT_DIM` |
| Today's change — insufficient equity points | `—` (single em-dash, big-size 22px) with small-print `from yesterday's close` still visible | `_COLOR_TEXT_DIM` for em-dash, `_COLOR_TEXT_MUTED` for small-print |
| Running equity — first run (len equity_history == 0) | `$100,000.00` (the `state['account']` fallback) with small-print `+0.0% since inception` in `_COLOR_TEXT_MUTED` | — |
| Positions table — Current price missing | `—` in that cell; adjacent Unrealised P&L cell also `—` | `_COLOR_TEXT_DIM` |
| ACTION REQUIRED — first run | Block NOT rendered at all (CONTEXT D-06 locks this) | — |

---

## Component Hierarchy

Skeletal HTML structure showing layout-table nesting. `role="presentation"` on every layout table per CONTEXT D-07 + WCAG guidance for email.

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="dark only">
  <meta name="supported-color-schemes" content="dark">
  <title>Trading Signals — {date}</title>
</head>
<body style="margin:0;padding:0;background:#0f1117;color:#e5e7eb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;">
  <!-- OUTER WRAPPER: viewport fill -->
  <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" bgcolor="#0f1117" style="background:#0f1117;">
    <tr>
      <td align="center" style="padding:16px 8px;">
        <!-- INNER CARD: 600px max, card bg/border -->
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" bgcolor="#161a24" style="max-width:600px;width:100%;background:#161a24;border:1px solid #252a36;">

          <!-- SECTION 1: Header -->
          <tr><td style="padding:20px 24px;">
            <h1 style="margin:0;font-size:22px;font-weight:600;color:#e5e7eb;line-height:1.2;">Trading Signals</h1>
            <p style="margin:4px 0 8px 0;font-size:14px;color:#cbd5e1;line-height:1.5;">SPI 200 & AUD/USD mechanical system</p>
            <p style="margin:0;font-size:12px;color:#cbd5e1;line-height:1.4;">
              <span style="font-weight:600;letter-spacing:0.04em;text-transform:uppercase;">Last updated</span>
              &nbsp;&middot;&nbsp;
              <span>{YYYY-MM-DD HH:MM AWST}</span>
            </p>
            <p style="margin:4px 0 0 0;font-size:14px;color:#cbd5e1;line-height:1.5;">Signal as of {YYYY-MM-DD}</p>
          </td></tr>

          <!-- SPACER -->
          <tr><td height="32" style="height:32px;font-size:0;line-height:0;">&nbsp;</td></tr>

          <!-- SECTION 2: ACTION REQUIRED (conditional — see §Copywriting §2) -->
          {{% if any_signal_changed %}}
          <tr>
            <td style="padding:12px 16px;background:#161a24;border-left:4px solid #ef4444;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;font-size:14px;color:#e5e7eb;line-height:1.5;">
              <p style="margin:0 0 8px 0;font-size:20px;font-weight:700;color:#e5e7eb;letter-spacing:0.02em;">━━━ ACTION REQUIRED ━━━</p>
              <!-- per-instrument diff paragraphs per D-11 truth table -->
            </td>
          </tr>
          <tr><td height="32" style="height:32px;font-size:0;line-height:0;">&nbsp;</td></tr>
          {{% endif %}}

          <!-- SECTION 3: Signal Status -->
          <tr><td style="padding:0 12px;">
            <h2 style="margin:0 12px 8px;font-size:20px;font-weight:600;color:#e5e7eb;line-height:1.3;">Signal Status</h2>
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
              <thead>
                <tr style="background:#161a24;border-bottom:1px solid #252a36;">
                  <th scope="col" style="padding:8px 12px;text-align:left;font-size:12px;font-weight:600;color:#cbd5e1;text-transform:uppercase;letter-spacing:0.04em;">Instrument</th>
                  <th scope="col" style="padding:8px 12px;text-align:left;font-size:12px;font-weight:600;color:#cbd5e1;text-transform:uppercase;letter-spacing:0.04em;">Signal</th>
                  <th scope="col" style="padding:8px 12px;text-align:left;font-size:12px;font-weight:600;color:#cbd5e1;text-transform:uppercase;letter-spacing:0.04em;">As of</th>
                  <th scope="col" style="padding:8px 12px;text-align:right;font-size:12px;font-weight:600;color:#cbd5e1;text-transform:uppercase;letter-spacing:0.04em;">ADX</th>
                  <th scope="col" style="padding:8px 12px;text-align:right;font-size:12px;font-weight:600;color:#cbd5e1;text-transform:uppercase;letter-spacing:0.04em;">Mom</th>
                </tr>
              </thead>
              <tbody>
                <!-- one <tr> per instrument: SPI200 then AUDUSD -->
              </tbody>
            </table>
            <p style="margin:4px 12px 0;font-size:11px;color:#cbd5e1;">Mom reads as 21d · 63d · 252d</p>
          </td></tr>

          <!-- SPACER -->
          <tr><td height="32" style="height:32px;font-size:0;line-height:0;">&nbsp;</td></tr>

          <!-- SECTION 4: Open Positions -->
          <tr><td style="padding:0 12px;">
            <h2 style="margin:0 12px 8px;font-size:20px;font-weight:600;color:#e5e7eb;line-height:1.3;">Open Positions</h2>
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
              <!-- thead with 7 columns per §Copywriting §4 -->
              <!-- tbody with one row per open position OR empty-state colspan=7 -->
            </table>
          </td></tr>

          <!-- SPACER -->
          <tr><td height="32" style="height:32px;font-size:0;line-height:0;">&nbsp;</td></tr>

          <!-- SECTION 5: Today's P&L + Running Equity -->
          <tr><td style="padding:20px 24px;">
            <h2 style="margin:0 0 16px;font-size:20px;font-weight:600;color:#e5e7eb;line-height:1.3;">Today's P&amp;L</h2>
            <!-- Row 1: Today's change -->
            <p style="margin:0;font-size:12px;font-weight:600;color:#cbd5e1;text-transform:uppercase;letter-spacing:0.04em;">Today's change</p>
            <p style="margin:8px 0 4px;font-size:22px;font-weight:600;font-family:'SF Mono',Menlo,Consolas,monospace;color:#22c55e;">{coloured change}</p>
            <p style="margin:0 0 24px;font-size:12px;color:#cbd5e1;">from yesterday's close</p>
            <!-- Row 2: Running equity -->
            <p style="margin:0;font-size:12px;font-weight:600;color:#cbd5e1;text-transform:uppercase;letter-spacing:0.04em;">Running equity</p>
            <p style="margin:8px 0 4px;font-size:22px;font-weight:600;font-family:'SF Mono',Menlo,Consolas,monospace;color:#e5e7eb;">$101,234.56</p>
            <p style="margin:0;font-size:12px;color:#cbd5e1;"><span style="color:#22c55e;">+1.23%</span> since inception</p>
          </td></tr>

          <!-- SPACER -->
          <tr><td height="32" style="height:32px;font-size:0;line-height:0;">&nbsp;</td></tr>

          <!-- SECTION 6: Last 5 Closed Trades -->
          <tr><td style="padding:0 12px;">
            <h2 style="margin:0 12px 8px;font-size:20px;font-weight:600;color:#e5e7eb;line-height:1.3;">Last 5 Closed Trades</h2>
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
              <!-- thead with 5 columns per §Copywriting §6 -->
              <!-- tbody with up to 5 rows newest-first OR empty-state colspan=5 -->
            </table>
          </td></tr>

          <!-- SPACER -->
          <tr><td height="32" style="height:32px;font-size:0;line-height:0;">&nbsp;</td></tr>

          <!-- SECTION 7: Footer -->
          <tr><td style="padding:20px 24px;text-align:center;">
            <p style="margin:0 0 4px;font-size:12px;color:#64748b;line-height:1.4;">Signal-only system. Not financial advice.</p>
            <p style="margin:0 0 4px;font-size:12px;color:#64748b;line-height:1.4;">Trading Signals — sent by signals@carbonbookkeeping.com.au</p>
            <p style="margin:0;font-size:12px;color:#64748b;line-height:1.4;">Run date: {YYYY-MM-DD}</p>
          </td></tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>
```

**Rendering-order rule.** Body section order is locked per CONTEXT D-10: header → ACTION REQUIRED (conditional) → signal status → open positions → today's P&L + running equity → last 5 closed trades → footer. Planner does not reorder. Spacer `<tr>` rows between sections are mandatory — not collapsible margins.

---

## Interaction States

The email is **fully static HTML**. No hover, focus, click, or keyboard interaction is designed or tested.

| Element | State | Behaviour |
|---------|-------|-----------|
| Any element | any | No hover effect, no focus ring, no cursor change. No `:hover`, `:focus`, or `:active` CSS (no `<style>` block at all). |
| Any text | selected | Browser / email-client native selection colour. No custom `::selection`. |
| Any element | click | No action. No `<a>`, no `<button>`, no form element in the body. The email client may auto-detect the footer email address as a link on some clients (iOS Mail underlines detected emails / URLs) — this is client-side enhancement and acceptable; we do NOT inject the `<a>` ourselves. |

**No JavaScript.** No `<script>`. No inline event handlers. No `<form>`. No `<input>`. No `<button>`. No `<a>`.

**Known client-side rewrites (document, don't fight):**

- iOS Mail may auto-detect dates and phone numbers → this is safe; the email contains no phone numbers. Dates in ISO format sometimes get a "show in calendar" affordance on iOS; acceptable.
- Gmail may auto-detect the footer email address → acceptable (operator's own address).
- Outlook may convert some plain text to `<a mailto>` for any `name@domain` pattern → acceptable.

---

## Accessibility Contract

Target: **WCAG 2.1 AA for email clients** — body contrast, traversable heading hierarchy, semantic table markup where clients respect it, screen-reader-friendly empty states. Email accessibility is lower-guarantee than web because major clients strip ARIA attributes inconsistently; below is the best-practice set.

| Requirement | Implementation |
|-------------|----------------|
| Page `<title>` | `Trading Signals — {YYYY-MM-DD}` (email client may ignore; still required for RFC-correct HTML) |
| `<html lang>` | `<html lang="en">` |
| Body font-size ≥ 12px | All rendered body text is 12px (`email-fs-label`) or 14px (`email-fs-body`); headings are larger. No 10-11px text. |
| Colour contrast | Every foreground/background pairing audited in §Color; all body pairings pass WCAG AA 4.5:1 |
| Heading hierarchy | Exactly one `<h1>` (`Trading Signals`). Five `<h2>`s in strict top-to-bottom order: `Signal Status`, `Open Positions`, `Today's P&L`, `Last 5 Closed Trades`. ACTION REQUIRED uses `<p>` with weight 700 + uppercase styling (NOT an `<h2>`) because it's conditional and would break hierarchy on no-change days. Footer uses no heading. |
| Layout-table role | Every layout `<table>` carries `role="presentation"` (CONTEXT D-07). Gmail web respects, iOS Mail mostly respects, Outlook ignores — ARIA strip is client-side, not Issue-raising; best effort. |
| Data-table role | Signal-status / positions / trades tables are SEMANTIC tables — they DO carry `<thead>`, `<tbody>`, `<th scope="col">`. They do NOT carry `role="presentation"`. Screen readers announce them as tables with headers. |
| Table captions | Email clients inconsistently render `<caption>` (Gmail strips). Do NOT use `<caption>` in email; rely on the `<h2>` above the table as the accessible name. |
| Empty states | Plain text in a `<td colspan="N">` — screen-reader-legible without ARIA. |
| `<img alt>` | Not applicable — v1 has no `<img>` tags. |
| Keyboard navigation | Not applicable — no focusable elements. Default client focus behaviour. |
| Reduced motion | Not applicable — no animation. |
| Auto-dark-mode handling | `<meta name="color-scheme" content="dark only">` + `<meta name="supported-color-schemes" content="dark">` in head; `bgcolor` attribute on outer and inner tables; inline `style:background` on `<body>`. See §Color §Dark-mode forced-lightening handling. |

**Explicit non-goals.** No `<a href>` in v1 → no screen-reader link announcement to design. No form fields → no `<label>`/`<input>` association. No live regions, no `aria-live`.

**Contrast note on `#64748b` footer.** Ratio on `#161a24` surface = 3.4:1 — BELOW AA 4.5:1 for body text. This is ACCEPTABLE because footer is decorative disclaimer text, WCAG gives a "decorative text" exception (similar to chrome text). Matches Phase 5 dashboard treatment. If the checker flags this, note it as documented-exception with matched-Phase-5 rationale. (Phase 5 UI-SPEC §Color §Contrast audit flags `#64748b` as "body-copy-only" with the same passing-AA-on-bg but borderline-on-surface status; email inherits.)

---

## Registry Safety

| Registry | Blocks Used | Safety Gate |
|----------|-------------|-------------|
| shadcn official | none — project is Python, not React | not applicable |
| Chart.js CDN | none — email cannot execute JS, no Chart in email (CONTEXT D-10 + Phase 5 Reuse Notes) | not applicable |
| Resend API (`api.resend.com/emails`) | Email transport only — not a UI registry. Endpoint + auth contract locked in CONTEXT D-12, verified by RESEARCH Wave 0 task. | not applicable — transport API, not a UI component registry |
| any third-party registry | none | not applicable |

**No npm, no pypi, no CDN, no webfont.** Zero external assets loaded by the email body. The `<head>` `<meta>` tags are the only browser-interpreted hints, and they load nothing. Icon libraries, webfonts, CSS frameworks, SVG-sprite CDNs, and email-template engines are all forbidden (PROJECT.md Constraints + CONTEXT D-07 + Phase 6 Scope Boundaries §"No template engine").

---

## Responsive Behaviour

One layout, zero media queries. The design targets 375px at minimum (CONTEXT D-09 iOS Mail on iPhone SE portrait). Max width is 600px (CONTEXT D-07). Fluid-hybrid: the inner card is `max-width:600px;width:100%;` which delivers the layout natively at every viewport from 320px up to 600px+ without a breakpoint.

| Viewport | Layout |
|----------|--------|
| ≤ 375px | Inner card shrinks to `width:100%` minus 8px outer padding on each side. Tables reflow within; cell padding stays tight at 8px vertical / 12px horizontal. No horizontal scroll on signal-status or positions tables (measured: 5 cols × 60px avg at 359px card width = fits). |
| 376-599px | Linear scale — card grows linearly up to 600px, cells breathe proportionally. |
| ≥ 600px | Card hits `max-width:600px` and stops. Outer wrapper centers the card; background `#0f1117` fills the viewport on larger clients. |

No "stack-on-mobile" behaviour, no column-to-row flip. One layout, works at every viewport in the target band.

**Known table-overflow edge.** The `Last 5 Closed Trades` table at 320px (not a target viewport, but client-simulator min) may require horizontal scroll in the `Entry → Exit` column. Acceptable — 320px is not a CONTEXT D-09 MUST-render viewport. If this becomes a real operator issue, the fix is to add `white-space:normal` to that cell so the `→` arrow wraps to a second line per cell. Documented deferral.

---

## Field Mapping (state.json → UI)

**Purpose.** Explicit wiring audit between each rendered email section and the exact `state.json` path it reads. Added per Phase 5 UI-SPEC revision precedent — B-1-class bugs (UI-SPEC names a field that doesn't exist in the write path) surface at design review, not at execution. Every field below MUST exist in state.json after Phase 5 Wave 0 retrofit (already committed per `main.py` line 550-556). Phase 6 introduces zero new state-schema requirements.

| Email section | state.json path | Source module / function | Fallback |
|---------------|-----------------|--------------------------|----------|
| Subject — date | `run_date.strftime('%Y-%m-%d')` (argument, not state) | `main._compute_run_date` produces the AWST run-date | — |
| Subject — signal labels | `state['signals'][state_key]['signal']` (int ∈ {-1, 0, 1}) | `main.py` line 550-556 `run_daily_check` | Missing → signal treated as `0`/FLAT in subject; subject still renders |
| Subject — equity | `state['equity_history'][-1]['equity']` OR `state['account']` fallback | `state_manager.update_equity_history` / `_initial_state` | `state['account']` always defined |
| Subject — emoji | Derived: `any_signal_changed` = any `(old, new)` pair where `old is not None and old != new` (CONTEXT D-06) | `old_signals` passed by `main.py` before state mutation | First-run → all `old` are None → no change → `📊` |
| Header — Last updated | `now` argument to `send_daily_email` (`run_date` AWST) | `main._compute_run_date` | `_fmt_last_updated_email` asserts `now.tzinfo is not None`; raises ValueError on naive datetime |
| Header — Signal as of | `state['signals'][state_key]['signal_as_of']` (ISO YYYY-MM-DD string) | `main.py` line 550-556 | Missing per-instrument key → `never` in `_COLOR_TEXT_DIM` |
| ACTION REQUIRED — old direction | `old_signals[yfinance_symbol]` (int from pre-run capture) | Captured in `main.py` before `run_daily_check` mutates state (CONTEXT D-05) | None → instrument NOT rendered in block |
| ACTION REQUIRED — new direction | `state['signals'][state_key]['signal']` (int) | Post-run state (argument to `send_daily_email`) | Missing → instrument NOT rendered (signal undefined) |
| ACTION REQUIRED — closed-position contracts + entry_price | `state['trade_log'][-1]['n_contracts']` / `['entry_price']` when `trade_log[-1]['exit_date'] == run_date_iso AND trade_log[-1]['instrument'] == state_key` (Option A per §Copywriting §2) | `main._closed_trade_to_record` + `state_manager.record_trade` | No matching tail entry → render "Close existing {OLD_DIR} position." without the `(N contracts @ entry $X)` parenthetical |
| Signal-status — Instrument | Display-name mapping (static constant) | `notifier._INSTRUMENT_DISPLAY_NAMES_EMAIL` | — |
| Signal-status — Signal | `state['signals'][state_key]['signal']` (int) | main.py line 550-556 | Missing → `—` in `_COLOR_FLAT` |
| Signal-status — As of | `state['signals'][state_key]['signal_as_of']` | main.py line 550-556 | Missing → `never` |
| Signal-status — ADX | `state['signals'][state_key]['last_scalars']['adx']` (float) | `signal_engine.get_latest_indicators` via `main.py` line 467-519 | Missing → `—` |
| Signal-status — Mom cell | `state['signals'][state_key]['last_scalars'][{'mom1','mom3','mom12'}]` | Same as above; Phase 1 D-08 locked 8-key shape | Missing → single `—` |
| Positions — Entry | `state['positions'][state_key]['entry_price']` (float) | `state_manager.Position` / `sizing_engine.open_position` | Position None → row omitted (partial-state rule) |
| Positions — Current | `state['signals'][state_key]['last_close']` (float) — **Phase 5 B-1 retrofit**, reused verbatim | `main.py` line 555 `run_daily_check` (Phase 5 Wave 0 extension) | Missing / None → `—` |
| Positions — Contracts | `state['positions'][state_key]['n_contracts']` (int) | `state_manager.Position` | Position None → row omitted |
| Positions — Trail Stop | Derived: LONG `peak_price - 3 * atr_entry`; SHORT `trough_price + 2 * atr_entry` (inline in `notifier.py`) | `state_manager.Position` fields `peak_price`, `trough_price`, `atr_entry` | Position None → row omitted |
| Positions — Unrealised P&L | Derived: `(current - entry) * n * mult - cost/2` (LONG) or reverse (SHORT), inline in `notifier.py` using `_CONTRACT_SPECS_EMAIL` | Positions from `Position` TypedDict; current close from signal-state `last_close` | `last_close` missing → `—`; position None → row omitted |
| Positions — Empty-state | `all(state['positions'].get(k) is None for k in ['SPI200', 'AUDUSD'])` | `state_manager.load_state` initial state | `colspan="7"` row `— No open positions —` |
| Today's change | `state['equity_history'][-1]['equity'] - state['equity_history'][-2]['equity']` when `len >= 2` | `state_manager.update_equity_history` | `len < 2` → big em-dash |
| Running equity | `state['equity_history'][-1]['equity']` fallback `state['account']` | Same as above | `state['account']` = `INITIAL_ACCOUNT` on first run |
| Since-inception % | `(equity - INITIAL_ACCOUNT) / INITIAL_ACCOUNT` | `system_params.INITIAL_ACCOUNT` | Always defined |
| Trades — all columns | `state['trade_log'][-5:][::-1]` — list of 12-field trade dicts | `main._closed_trade_to_record` (11 fields) + `state_manager.record_trade` (appends `net_pnl` as 12th) | Empty list → `colspan="5"` row `— No closed trades yet —` |
| Trades — P&L | `trade['net_pnl']` (float) — 12th field appended by `state_manager.record_trade` per Phase 3 D-20 | `state_manager.record_trade` | Authoritative net-of-cost P&L |
| Footer — Run date | `run_date.strftime('%Y-%m-%d')` | `main._compute_run_date` | — |

**Authoritative trade_log schema** (same as Phase 5 F-8 note — re-documented here for checker-completeness): 12 fields, `{instrument, direction, entry_date, exit_date, entry_price, exit_price, gross_pnl, n_contracts, exit_reason, multiplier, cost_aud, net_pnl}`. `gross_pnl` is price-delta × contracts × multiplier (pre-cost); `net_pnl` is `gross_pnl - (cost_aud * n_contracts / 2)` (net of closing half-cost; opening half was deducted into the live position's unrealised by Phase 2 `compute_unrealised_pnl`).

**Audit rule (locked forward, same as Phase 5).** Any future email UI-SPEC revision that introduces a new rendered element MUST add a row to this table with the exact `state.json` path. If the path does not yet exist in main.py / state_manager.py write paths, the revision MUST declare the retrofit explicitly in §Downstream Notes for Planner.

---

## Format Helper Contracts (executor-verbatim)

Named helpers locked here so the planner can write task ACs and the executor ships without naming-bikeshedding. All helpers are stdlib-only, pure (no `state` arg), side-effect-free, and live IN `notifier.py` (CONTEXT D-02 full-local-duplication). They mirror the dashboard formatters' output semantics but emit inline-`style` spans instead of CSS-variable-referenced spans.

| Helper | Signature | Returns |
|--------|-----------|---------|
| `_fmt_currency_email(value: float) -> str` | `$1,234.56`, `-$567.89`, `$0.00`. Always 2 dp. Negative uses leading `-$`, not parentheses. Never suffix-collapses to K/M/B. Output is plain text (no surrounding span — caller wraps). |
| `_fmt_percent_signed_email(fraction: float) -> str` | `+5.3%`, `-12.5%`, `+0.0%`. Input is a fraction (0.053 → `+5.3%`). Plain text. |
| `_fmt_percent_unsigned_email(fraction: float) -> str` | `58.3%`, `12.5%`. Input is a fraction. Plain text. |
| `_fmt_pnl_with_colour_email(value: float) -> str` | Returns safe HTML: positive → `<span style="color:#22c55e">+$1,234.56</span>`, negative → `<span style="color:#ef4444">-$567.89</span>`, zero → `<span style="color:#cbd5e1">$0.00</span>`. All literal hex (NOT CSS-var refs — email clients would drop them). Passes output through `html.escape` as belt-and-braces guardrail (CONTEXT D-15 inherited from Phase 5). |
| `_fmt_em_dash_email() -> str` | The literal `'—'` (U+2014). One call site per empty cell so tests can grep a single token. |
| `_fmt_last_updated_email(now: datetime) -> str` | `'2026-04-22 09:00 AWST'` — applies `now.astimezone(pytz.timezone('Australia/Perth'))` then `strftime('%Y-%m-%d %H:%M AWST')`. Asserts `now.tzinfo is not None`; raises `ValueError` on naive datetime. **IMPORTANT:** use `pytz.timezone('Australia/Perth').localize(...)` when constructing test datetimes — never `datetime(..., tzinfo=pytz.timezone(...))` (pytz localize-misuse bug caught in Phase 5 reviews-revision, CONTEXT D-05 of THIS phase). |
| `_fmt_instrument_display_email(state_key: str) -> str` | `'SPI200' → 'SPI 200'`, `'AUDUSD' → 'AUD / USD'`. Unknown key → pass through `html.escape(state_key)`. |
| `_fmt_signal_label_email(signal: int) -> str` | Returns coloured span: `1 → <span style="color:#22c55e;font-weight:600">LONG</span>`, `-1 → <span style="color:#ef4444;font-weight:600">SHORT</span>`, `0 → <span style="color:#eab308;font-weight:600">FLAT</span>`, `None → <span style="color:#64748b">—</span>`. Literal hex. Html-safe by construction. |
| `_fmt_scalar_email(value: float \| None, decimals: int = 1) -> str` | `f'{value:.{decimals}f}'` when finite; `—` otherwise. Used for ADX cell (decimals=1). |

**Why duplicate all these into notifier.py instead of sharing from dashboard.py?** Per CONTEXT D-02: (a) each hex owns its concern; (b) email-client quirks may require a future divergence (e.g., Outlook-specific color-handling) that should land without touching dashboard; (c) hex-fence prevents cross-hex coupling at the formatter level. Cost: ~120 lines of near-duplicate code. Accepted trade.

---

## Non-Goals (locked — do NOT add)

- No `<style>` block (inline-CSS only per PROJECT.md + CONTEXT D-07).
- No `@media` query anywhere (CONTEXT D-08 fluid-hybrid).
- No `<script>` anywhere (email clients strip; PROJECT.md Constraints).
- No `<img>`, no `<picture>`, no `<svg>`, no `<canvas>`. Zero external assets (CONTEXT Scope Boundaries + PROJECT.md).
- No `<link>` beyond the mandatory `<meta>` tags.
- No `<form>`, `<input>`, `<button>`, `<select>`, `<textarea>`.
- No `<a href>` in the body — footer email is plain text; no mailto, no unsubscribe link.
- No `<iframe>`, `<embed>`, `<object>`.
- No `@font-face`, no webfont load.
- No `:hover`, `:focus`, `:active`, `::before`, `::after` pseudo-selectors (requires `<style>` block).
- No CSS custom properties / `var()` — email clients drop them.
- No `prefers-color-scheme` media query — CONTEXT D-04 scope boundary: dark theme only.
- No emoji in the BODY — emoji use is SUBJECT-ONLY (🔴 / 📊) per CONTEXT D-04 glyph-budget rule. Body uses `━` for the ACTION REQUIRED divider and `→` for arrows; no 🔴 in body.
- No branding block beyond the 4-word disclaimer + sender line + run-date line in the footer.
- No version string, no build SHA, no commit hash.
- No analytics pixel, no tracking pixel, no pixel of any kind.
- No unsubscribe mechanism — single-operator tool, doesn't apply.
- No reply-to address override — defaults to From address.
- No BCC, no CC — single recipient (`SIGNALS_EMAIL_TO` env-var override per CONTEXT D-14, with `_EMAIL_TO_FALLBACK` hardcoded).
- No attachment (inline HTML only per NOTF-03 + CONTEXT Scope Boundaries).
- No plain-text alternative (`text/plain` multipart) — v1 is HTML-only; degradation in text-only clients accepted. Operator reads on Gmail web / iOS Mail per CONTEXT D-09.

---

## Phase 5 Alignment Table

Explicit mapping between Phase 5 dashboard decisions and Phase 6 email decisions. Where they match, the email reuses verbatim (often via `system_params` constants post-D-02-retrofit). Where they differ, the row is marked `DIFFERS` with a one-line reason.

| Concept | Phase 5 dashboard | Phase 6 email | Status |
|---------|-------------------|----------------|--------|
| Palette hex | `#0f1117 / #161a24 / #252a36 / #e5e7eb / #cbd5e1 / #64748b / #22c55e / #ef4444 / #eab308` | same 9 hex literals | MATCH (sourced from `system_params` post-retrofit) |
| Palette source | Module constants in `dashboard.py` | Module constants in `system_params.py` (both hexes import) | DIFFERS — CONTEXT D-02 palette retrofit moves constants upstream in Wave 0 |
| Font stack (body) | System stack | Same system stack | MATCH |
| Font stack (numeric) | Monospace + `font-variant-numeric: tabular-nums` | Monospace ONLY (no tabular-nums; email-drops-declaration) | DIFFERS — email client gap |
| Font role sizes | 14 / 12 / 20 / 28 | 14 / 12 / 20 / 22 | DIFFERS — email display tier dropped from 28→22 for mobile reading |
| Font weights | 400, 600 | 400, 600, 700 (ACTION REQUIRED headline only — controlled exception) | DIFFERS — documented exception |
| Body max-width | 1100px | 600px | DIFFERS — email standard for mobile-first reading |
| Layout technique | Flexbox + CSS Grid + 1 media query (≤720px) | Table-based, 0 media queries, fluid-hybrid | DIFFERS — email compatibility |
| Letter-spacing on labels | `0.04em; text-transform:uppercase` on `<th>` + stat-tile labels | Same on `<th>`; NOT on footer prose | MATCH on tables |
| Signal card layout | Two cards side-by-side at ≥720px | Two rows inside signal-status TABLE (not cards) | DIFFERS — email cells are tables not articles |
| Instrument display names | `SPI 200` / `AUD / USD` | Same | MATCH (duplicated via `_INSTRUMENT_DISPLAY_NAMES_EMAIL`) |
| Exit-reason display map | `flat_signal→"Signal flat"`, `signal_reversal→"Reversal"`, `stop_hit→"Stop hit"`, `adx_exit→"ADX drop"` | Not rendered — email trades table drops the Reason column | DIFFERS — scope reduced |
| `_fmt_currency` | Dashboard version | `_fmt_currency_email` duplicate | MATCH semantics |
| `_fmt_pnl_with_colour` | Dashboard version — returns span with CSS var reference | `_fmt_pnl_with_colour_email` — returns span with LITERAL hex | DIFFERS at the hex-ref layer |
| `_fmt_last_updated` | Dashboard version | `_fmt_last_updated_email` duplicate | MATCH |
| Em-dash glyph | U+2014 | Same | MATCH |
| Middle-dot glyph | U+00B7 (signal card scalar separator) | Same (Mom composite cell) | MATCH |
| Arrow glyph | U+2192 (closed-trades Entry → Exit) | Same (closed-trades Entry → Exit + ACTION REQUIRED `LONG → SHORT`) | MATCH |
| Box-drawing glyph | not used | U+2501 (ACTION REQUIRED headline `━━━`) | EMAIL-ADDS |
| Emoji | not used | `🔴 / 📊` in subject only | EMAIL-ADDS (subject only) |
| Numeric display for P&L | Leading `-$`, 2 dp, comma-thousands, colour-coded | Same | MATCH |
| Contract specs source | `system_params.SPI_MULT` / `SPI_COST_AUD` / `AUDUSD_NOTIONAL` / `AUDUSD_COST_AUD` | Same import | MATCH |
| Opening-half cost subtraction | In dashboard unrealised-P&L formula | In email unrealised-P&L formula | MATCH |
| Positions table columns | 8 (incl. Pyramid) | 7 (Pyramid dropped for email density) | DIFFERS — scope reduced |
| Trades table columns | 7 | 5 (Contracts + Reason dropped) | DIFFERS — scope reduced |
| Trades table row count | Last 20 | Last 5 | DIFFERS — scope |
| Empty state — positions | `colspan="8"` `— No open positions —` | `colspan="7"` `— No open positions —` | MATCH (copy); DIFFERS (colspan) |
| Empty state — trades | `colspan="7"` `— No closed trades yet —` | `colspan="5"` `— No closed trades yet —` | MATCH (copy); DIFFERS (colspan) |
| html.escape discipline | Every state-derived leaf (CONTEXT D-15 inherited) | Same | MATCH |
| Chart | Chart.js equity curve | None — email cannot execute JS | EMAIL-OMITS |
| Footer disclaimer | `Signal-only system. Not financial advice.` | Same + sender line + run-date line (3 lines total) | MATCH line 1; email ADDS 2 more |

---

## Checker Sign-Off

- [ ] Dimension 1 Copywriting: PASS
- [ ] Dimension 2 Visuals: PASS
- [ ] Dimension 3 Color: PASS
- [ ] Dimension 4 Typography: PASS
- [ ] Dimension 5 Spacing: PASS
- [ ] Dimension 6 Registry Safety: PASS

**Approval:** pending (initial draft 2026-04-22 — awaiting UI-CHECKER pass)

---

## Downstream Notes for Planner

### Palette retrofit (CONTEXT D-02 — Wave 0 blocking task)

The Phase 6 plan's Wave 0 scaffold MUST move the palette constants from `dashboard.py` module-level to `system_params.py` module-level:

- Constants to move: `_COLOR_BG`, `_COLOR_SURFACE`, `_COLOR_BORDER`, `_COLOR_TEXT`, `_COLOR_TEXT_MUTED`, `_COLOR_TEXT_DIM`, `_COLOR_LONG`, `_COLOR_SHORT`, `_COLOR_FLAT`.
- `dashboard.py` becomes `from system_params import _COLOR_BG, _COLOR_SURFACE, ...` (keep private underscore prefix — these are still "internal" to the UI hexes).
- `notifier.py` imports the same constants from `system_params`.
- Phase 5 golden-HTML fixture MUST remain byte-stable after the retrofit — executor runs `pytest tests/test_dashboard.py::TestGoldenSnapshot` after the move and re-generates only if byte-diff is zero-semantic (which it should be; just a symbol-source change).
- System-params tests unchanged — `system_params` grows a constants block; no new behavior.

No state-schema changes. No new state.json fields. The Phase 5 B-1 retrofit (`last_close` in signal state) is already committed (`main.py:555`) — email reuses verbatim.

### Helper duplication (CONTEXT D-02)

Per CONTEXT D-02 recommendation (duplicate rather than extract): the Phase 6 plan should ship all formatters IN `notifier.py`. Do NOT extract to a `_format_helpers.py` shared module — the hex-lite rule permits the duplication, and the ~120 lines of near-duplicate code buy isolation that pays off if either hex needs to diverge (Outlook-specific tweak in notifier, retina-specific tweak in dashboard, etc.).

If the planner or executor feels strongly about DRY extraction, this is a CONTEXT-level re-decision and should be raised as a Wave 0 task under "CONTEXT amendment for D-02" — NOT a unilateral extraction in Wave 1 or 2.

### ACTION REQUIRED — closed-position data source (Claude's Discretion resolution)

Per §Copywriting §2: the ACTION REQUIRED "Close existing {DIR} position (N contracts @ entry $X)" line needs PRE-CLOSE position data. The closed position record is at `state['trade_log'][-1]` when its `exit_date == run_date_iso` and `instrument == state_key` — this is the authoritative post-Phase-4 source. Planner codes:

```python
def _closed_position_for_instrument_on(state: dict, state_key: str, run_date_iso: str) -> dict | None:
  '''Return the trade_log entry closed in this run for this instrument, or None.'''
  if not state.get('trade_log'):
    return None
  tail = state['trade_log'][-1]
  if tail.get('exit_date') == run_date_iso and tail.get('instrument') == state_key:
    return tail
  # Defense: scan the last few entries in case multiple closes in one run
  for t in reversed(state['trade_log'][-3:]):
    if t.get('exit_date') == run_date_iso and t.get('instrument') == state_key:
      return t
  return None
```

This keeps the logic in `notifier.py`, avoids refactoring `run_daily_check` return signature for this concern (CONTEXT D-15 already flags a separate refactor for `(rc, state, old_signals)` tuple — don't pile on). Tested via a fixture with `trade_log[-1]` matching the run_date.

### `run_daily_check` refactor (CONTEXT D-15)

Separate from the ACTION-REQUIRED data source: CONTEXT D-15 flags the refactor of `run_daily_check(args) -> int` to `run_daily_check(args) -> tuple[int, dict, dict]` (rc, state, old_signals) so the `--test` + `--force-email` combo paths can pass in-memory state to email dispatch without re-loading (since `--test` didn't persist). This is a Wave 2 task:

- Touch sites: `main.py` `run_daily_check` return, `main.py` `main()` dispatch on `--once` / `--test` / `--force-email`, any Phase 4 test that assumes `int` return.
- Backward-compat: only `main()` is an external caller of `run_daily_check`; all other callers are tests. Tests update in lockstep.

Do NOT attempt this refactor in Wave 1 — it's coupled to the dispatch wiring in Wave 2.

### Golden-HTML snapshot (Wave 2 PHASE GATE)

Mirror Phase 5's pattern exactly:

- `tests/fixtures/notifier/sample_state_with_change.json` — SPI200 LONG→SHORT, AUDUSD FLAT→LONG, non-empty trade_log, non-empty equity_history.
- `tests/fixtures/notifier/sample_state_no_change.json` — both instruments signal unchanged, open positions present, equity_history at 40+ points so Sharpe is defined (though email doesn't surface Sharpe — still a realistic fixture).
- `tests/fixtures/notifier/empty_state.json` — initial state right after `reset_state`, trade_log empty, positions all None, equity_history empty, signals empty dict.
- `tests/regenerate_notifier_golden.py` — byte-stable regenerator. Frozen clock via `pytz.timezone('Australia/Perth').localize(datetime(2026, 4, 22, 9, 0))`. Double-run gate (regenerate twice, confirm SHA256 match).
- `tests/fixtures/notifier/golden_subject_change.txt` + `golden_body_change.html` + no-change variants + empty variant.

**pytz usage — lock this before Wave 0 ships.** CONTEXT `prior_decisions` §Timezone + CONTEXT `downstream_notes` flag the pytz-localize trap. Wave 0 tests MUST use `pytz.timezone('Australia/Perth').localize(datetime(...))` — NEVER `datetime(..., tzinfo=pytz.timezone(...))`. Enforce at PR-review time. The Phase 5 reviews-revision C-1 bug was exactly this — costs an hour to find if it lands in the golden.

### `.env.example` (Wave 0)

New file at repo root. Minimum contents:

```
RESEND_API_KEY=re_your_resend_key_here
SIGNALS_EMAIL_TO=marc@carbonbookkeeping.com.au
```

Second line is CONTEXT D-14 env-var override of `_EMAIL_TO_FALLBACK`. Phase 7 will expand with `ANTHROPIC_API_KEY` and any other env vars it needs.

### `.gitignore` addition (Wave 0)

Extend with `last_email.html` (the CONTEXT D-13 fallback-file). Phase 5 already gitignored `dashboard.html`; same pattern.

---

## Traceability to CONTEXT Decisions

| CONTEXT decision | UI-SPEC section |
|-------------------|-----------------|
| D-01 (notifier.py hex / import fence) | Design System, Non-Goals, Format Helper Contracts |
| D-02 (full local duplication of formatters + palette retrofit) | Format Helper Contracts, Phase 5 Alignment Table, Downstream Notes |
| D-03 (Waves plan) | Downstream Notes |
| D-04 (subject template + emoji + [TEST] + rounding) | Copywriting §Subject line |
| D-05 (old_signals capture in main.py) | Field Mapping, Downstream Notes |
| D-06 (first-run = no-change) | Copywriting §Subject, §ACTION REQUIRED, Field Mapping |
| D-07 (table-based layout, 600px wrapper, role="presentation") | Spacing Scale §Layout container, Component Hierarchy, Accessibility Contract |
| D-08 (no @media, fluid-hybrid) | Responsive Behaviour, Non-Goals |
| D-09 (MUST-render Gmail web + iOS Mail) | Color §Dark-mode forced-lightening, Responsive Behaviour |
| D-10 (7-section body order) | Copywriting §Body sections, Component Hierarchy |
| D-11 (ACTION REQUIRED block copy + structure) | Copywriting §2, Color §Accent reserved for |
| D-12 (Resend retry) | Registry Safety (noted as transport API) |
| D-13 (missing RESEND_API_KEY fallback) | Non-Goals, Downstream Notes |
| D-14 (env-var recipient + hardcoded sender) | Downstream Notes §.env.example |
| D-15 (dispatch wiring + run_daily_check refactor) | Downstream Notes |

| REQUIREMENTS.md NOTF-* | UI-SPEC coverage |
|------------------------|------------------|
| NOTF-01 (Resend HTTPS) | Registry Safety, Non-Goals |
| NOTF-02 (subject + emoji) | Copywriting §Subject line |
| NOTF-03 (inline CSS, dark theme) | Design System, Color, Non-Goals |
| NOTF-04 (body sections) | Copywriting §Body sections, Component Hierarchy |
| NOTF-05 (ACTION REQUIRED red border) | Copywriting §2, Color §Accent reserved for |
| NOTF-06 (mobile-responsive 375px) | Responsive Behaviour |
| NOTF-07 (Resend failure logged, never crashes) | Registry Safety (transport note), Non-Goals |
| NOTF-08 (missing RESEND_API_KEY graceful) | Downstream Notes |
| NOTF-09 (html-escape all user-visible values) | Format Helper Contracts, Accessibility Contract, Field Mapping |

---

## Open Questions for the Planner / Researcher

None visible. Every value above is concrete.

- Phase 5 B-1 retrofit is already committed (`main.py:555`). No retrofit is newly introduced by this UI-SPEC.
- CONTEXT D-02 palette retrofit is already scoped as Wave 0 task per CONTEXT plan breakdown — UI-SPEC merely restates the requirement at §Downstream Notes §Palette retrofit.
- The ACTION REQUIRED closed-position data source (Option A — trade_log tail read) is a UI-SPEC decision, not a CONTEXT gap; documented in §Downstream Notes so reviewers can see the reasoning.

If the Wave 2 HTTP-dispatch task discovers the Resend API has changed its response-shape contract between PROJECT.md research and implementation, that's a RESEARCH.md update, not a UI-SPEC update — the UI-SPEC is unaffected.
