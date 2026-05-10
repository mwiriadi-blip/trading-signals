---
phase: 25
slug: dashboard-ui-ux-overhaul-true-multi-tab-market-preferences
status: draft
shadcn_initialized: false
preset: none
created: 2026-05-05
---

# Phase 25 — UI Design Contract

> Visual and interaction contract for the dashboard UI/UX overhaul. Operator-facing trading dashboard, server-rendered HTML via `dashboard_renderer/` + raw HTMX 1.9.12. No SPA framework, no Tailwind, no component library — vanilla HTML + scoped `<style>` block emitted from `dashboard_renderer/shell.py`. Tokens already exist in `dashboard.html:64-78`; this phase rebalances them, does not invent a new system.

---

## Design System

| Property | Value |
|----------|-------|
| Tool | none (vanilla CSS custom properties) |
| Preset | not applicable |
| Component library | none — bespoke per-renderer-component HTML in `dashboard_renderer/components/` |
| Icon library | none — text glyphs only (●, [!], ↑, ↓, →, ✓). Status dot is a CSS-rendered `<span>` with `border-radius:50%`, NOT an icon font. (D-19) |
| Font | System stack — `-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif`. Mono = `ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace` for tabular numerics. No webfont download. |

**Shell strategy (D-02):** Common `<style>` and `<script>` are deduped via `dashboard_renderer/shell.py` emitting a single inline `<style>` block per page. We are NOT introducing external `/static/dashboard.css`/`/static/dashboard.js` — the inline-shell DASH-01 pattern is preserved. Token table below is the canonical source; `shell.py` is the only place these literals appear post-Phase-25.

---

## Spacing Scale

8-point base. Existing `--space-N` tokens (`dashboard.html:74-75`) are kept as-is; `--space-3 = 12px` is the documented exception (used for label gaps, table cell horizontal padding) — we keep it for backwards compatibility but new spacing decisions must pick from the multiples-of-4 column.

| Token | Value | Usage |
|-------|-------|-------|
| `--space-1` | 4px | Icon gaps, status-dot offset, inline `+`/`-` adjustments |
| `--space-2` | 8px | Tab gaps, button row gaps, compact label↔value spacing, tile internal `<p>` margins |
| `--space-3` | 12px | **Exception (kept).** Table cell horizontal padding, market-selector gap. New code prefers `--space-2` or `--space-4`. |
| `--space-4` | 16px | Default element spacing; eyebrow→value, header `.meta` gap, fieldset legend bottom margin |
| `--space-6` | 24px | Card padding, stats-grid gap, cards-row gap |
| `--space-8` | 32px | Section bottom margin, container vertical padding-top, tab-panel padding-bottom |
| `--space-12` | 48px | Container padding-bottom, footer top margin |

**New tokens introduced this phase:**

| Token | Value | Usage |
|-------|-------|-------|
| `--space-status-dot` | 8px | Status-dot diameter (next to FLAT/LONG/SHORT labels per D-19; status-strip indicator per D-06) |
| `--touch-target-min` | 44px | Minimum hit area for tab anchors and `+ Add market` chip (mobile a11y; D-15 + D-18) |

Exceptions: `--space-3 = 12px` (legacy, kept for stability — see above). `--space-status-dot` and `--touch-target-min` exist outside the 4/8/16/24/32/48 scale because they encode physical-device contracts (visual dot legibility, finger touch target), not layout rhythm.

---

## Typography

D-15: `--fs-body` 14px → 16px to kill iOS auto-zoom on input focus. All other `--fs-*` tokens scale by `16/14 ≈ 1.143×`, rounded to whole pixels. Hierarchy is preserved.

| Role | Token | Old (px) | **New (px)** | Weight | Line Height | Usage |
|------|-------|----------|--------------|--------|-------------|-------|
| Label / Eyebrow | `--fs-label` | 12 | **14** | 600 | 1.4 | Eyebrows (`SIGNAL`, `LAST UPDATED`), table `<th>`, stat-tile label, `<small>` Settings helper text, status-strip label |
| Body | `--fs-body` | 14 | **16** | 400 | 1.5 | Paragraph text, table `<td>`, `<input>`/`<select>` text, button labels, tab labels |
| Heading | `--fs-heading` | 20 | **23** | 600 | 1.3 | `<section> h2` ("Account", "Open Positions", "Settings", "Market Test") |
| Display | `--fs-display` | 28 | **32** | 600 | 1.2 | `<header> h1` ("Trading Signals"), card `.big-label` (FLAT/LONG/SHORT), stat-tile `.value` |

**Weight policy:** exactly two weights — 400 (body, subtitles, paragraph) and 600 (labels, headings, display, button text). No 300/500/700.

**Mono numerics:** every column where numbers must align (P&L, prices, indicator outputs, timestamps in status strip) uses `font-family: var(--font-mono)` + `font-variant-numeric: tabular-nums`. This is non-negotiable — tabular alignment is a trading-data correctness affordance.

**Letter-spacing rule:** `text-transform: uppercase` labels and eyebrows get `letter-spacing: 0.04em`. Nothing else gets letter-spacing.

---

## Color

Existing palette in `dashboard.html:65-73` is the source of truth. The 60/30/10 split below describes what already exists; Phase 25 does not invent a new palette — it **regularises** (replaces inline `style="color:#eab308"` with the token, per D-19) and adds two semantic tokens for the status strip.

| Role | Token | Value | Usage |
|------|-------|-------|-------|
| Dominant (60%) | `--color-bg` | `#0f1117` | Page background, table-row hover background |
| Secondary (30%) | `--color-surface` | `#161a24` | Cards, tab-panel background, stat-tiles, tables, fieldset background, status-strip container |
| Border | `--color-border` | `#252a36` | All 1px borders (cards, tables, tab-strip, fieldset border, focus-ring fallback) |
| Text | `--color-text` | `#e5e7eb` | Default body text |
| Text-muted | `--color-text-muted` | `#cbd5e1` | Subtitles, table column headers, helper `<small>`, eyebrows |
| Text-dim | `--color-text-dim` | `#64748b` | Empty-state copy, footer, disabled controls, "n/a" placeholders |
| Accent — LONG | `--color-long` | `#22c55e` | LONG signal label, primary CTA border + text, P&L positive, status-strip success dot, `[OK]` badges |
| Accent — SHORT | `--color-short` | `#ef4444` | SHORT signal label, P&L negative, "Close" buttons, status-strip failure dot, ALERT-HIT state, destructive confirmations |
| Accent — FLAT | `--color-flat` | `#eab308` | FLAT signal label, "Modify" buttons, status-strip stale/amber dot, ALERT-APPROACHING state, "+ Add market" chip border |

**Accent reserved for** (explicit list — these are the ONLY surfaces that may use `--color-long`/`--color-short`/`--color-flat`):
1. Signal big-labels — FLAT/LONG/SHORT card on each instrument (`dashboard.html:683` and equivalents).
2. P&L numerics in tables (Open Positions unrealised, Closed Trades realised).
3. Primary CTA outlined buttons (`.btn-primary` uses `--color-long` border + text).
4. Row-action buttons — `.btn-close` uses `--color-short`, `.btn-modify` uses `--color-flat`.
5. Status-strip dot (D-06) — green = `last_run_status=success`, amber = stale (>26h since `last_run_at`), red = `last_run_status=failure`.
6. Status-dot glyph beside FLAT/LONG/SHORT labels (D-19) — non-colour cue for colourblind users.
7. ALERT-pane state badges (Phase 20 pre-existing) — green CLEAR, amber APPROACHING, red HIT.
8. Active tab indicator — bottom-border 2px in `--color-long` (NEW in Phase 25, D-18); replaces the no-rule-at-all current state.

Accent is NOT used for: hyperlinks, focus rings (those use `--color-text`), default body text emphasis, table-row striping, or generic borders.

**New semantic tokens introduced this phase (D-19):**

| Token | Value | Usage |
|-------|-------|-------|
| `--color-focus-ring` | `#e5e7eb` (= `--color-text`) | `:focus-visible` outline on all interactive elements (anchors, buttons, `<summary>`, `<select>`, tab anchors). 2px solid + 2px offset. |
| `--color-status-stale` | `#eab308` (= `--color-flat`) | Status-strip dot when `now - last_run_at > 26h` (one daily cycle + 2h grace). Distinct semantic name from `--color-flat` even though same hex — auditors must not collapse them. |

**Destructive:** `--color-short` (`#ef4444`) is reused. No separate destructive token. Confirmation copy carries the destructive weight (see Copywriting Contract).

---

## Copywriting Contract

Phase 25 fixes terminology drift across 4 dashboard HTML files (D-21) and writes copy for the new System Status strip, first-run empty state, equity-empty state, and Settings helper text. Operator reviews helper-text copy during `/gsd-plan-phase 25` (D-13) — planner drafts; operator rewrites the 2-3 fields they care about.

### Page-level / shell

| Element | Copy |
|---------|------|
| `<title>` (all pages) | `Trading Signals — {Function} — {Market}` (e.g. `Trading Signals — Signals — SPI200`); Account is `Trading Signals — Account` (no market segment per D-04) |
| `<h1>` (header) | `Trading Signals` |
| `.subtitle` | `SPI 200 & AUD/USD mechanical system` |

### Tab strips (D-18, D-21)

| Element | Copy |
|---------|------|
| Function tab — Signals | `Signals` |
| Function tab — Account | `Account` |
| Function tab — Settings | `Settings` |
| Function tab — Market Test | `Market Test` |
| Market tab labels | Instrument code as stored in `state.markets` (e.g. `SPI200`, `AUDUSD`); no friendly aliasing in this phase |
| Add-market chip | `+ Add market` (replaces buried `<a class="btn-row btn-modify" href="#settings-tab">Add market</a>` per D-16) |
| Add-market expanded form — submit button | `Add market` (sentence case; matches Settings page Add Market button — D-21) |
| Add-market expanded form — cancel | `Cancel` |
| Active tab `aria-current` | `page` (D-18) |
| Function tab strip `aria-label` | `Function` |
| Market tab strip `aria-label` | `Market` |

### System Status strip (D-06, D-07, D-08)

| Element | Copy |
|---------|------|
| Strip label — last run | `Last run` (uppercase eyebrow style) |
| Strip label — next run | `Next run` (uppercase eyebrow style) |
| Last-run value (success) | `<time datetime="…">{ISO}</time> · OK` with green dot |
| Last-run value (failure) | `<time datetime="…">{ISO}</time> · Failed` with red dot |
| Last-run value (stale, >26h) | `<time datetime="…">{ISO}</time> · Stale` with amber dot |
| Last-run value (never run) | `Awaiting first run` with grey-dim dot — NO `<time>` element rendered |
| Next-run value | `08:00 AWST · in {N}h {M}m` (countdown computed JS-side from fixed UTC+8 offset, never browser TZ — D-08) |
| Next-run value (within current cycle minute) | `08:00 AWST · running now…` |
| Aria-live region for countdown | `aria-live="off"` (countdown changes every minute; announcing it would be hostile to SR users) |
| Aria-live region for status change | `aria-live="polite"` on the status-dot wrapper so a `success → failure` transition is announced after auto-refresh |

### First-run empty state (D-09)

| Element | Copy |
|---------|------|
| Onboarding card heading | `Awaiting first daily run` |
| Onboarding card body | `Calculations and equity curve will populate after the first cycle at 08:00 AWST.` |
| When shown | `state.last_run_at is null` — replaces the 11 stacked `n/a (need N bars, have 0)` panels |

### Stats bar empty state (D-10)

| Element | Copy |
|---------|------|
| Stats bar | **Hidden** until `closed_paper_trades + closed_live_trades >= 1`. No "0 trades" placeholder rendered — the section is omitted from the DOM. |

### Equity chart empty state (D-11)

| Element | Copy |
|---------|------|
| Heading (above chart slot) | `Equity curve` |
| Empty-state body (when fewer than 5 distinct `(date, value)` tuples) | `Chart appears once 5 daily equity points have been recorded.` (centered in `--color-text-dim`, no chart frame) |
| When shown | Strict `len({(d,v) for d,v in equity_history}) >= 5` — three identical $100,000 points still produces ONE distinct point and the chart stays hidden (D-11) |

### Settings page (D-12, D-13)

| Element | Copy |
|---------|------|
| Section heading | `Settings` |
| Subtle subtitle | `Per-market trading rules. Changes take effect on the next 08:00 AWST cycle.` |
| Fieldset 1 legend | `Entry rules` |
| Fieldset 2 legend | `Risk` |
| Fieldset 3 legend | `Direction` |
| Save button | `Save settings` (sentence case — replaces existing `Save Settings`, D-21) |
| Add-market form heading (Settings page; planner decides if retained alongside chip per D-17) | `Add a market` |
| Add-market submit | `Add market` |
| Helper text — drafted by planner during `/gsd-plan-phase 25`, operator reviews | One `<small>` per field, max 80 chars, format: `{plain-English meaning}. {Default or unit}.` |

### Market Test page (D-14)

| Element | Copy |
|---------|------|
| Section heading | `Market test` |
| Subtle subtitle | `Override settings for a one-shot signal calculation. Does not modify saved settings.` |
| Override field placeholders | Render the inherited Settings default as `placeholder="…"` text (e.g. `placeholder="25"` on the ADX field); helper text below reads `Inherits {field-name} from Settings ({value}) when blank.` |
| Run button | `Run test` (sentence case — replaces `Run Test`, D-21) |

### Account page (D-04)

| Element | Copy |
|---------|------|
| Section heading | `Account` |
| Subtle subtitle | `Account-wide controls. Market-agnostic.` |
| Account balance label (D-21 reconciliation) | `Account balance` chosen as the single canonical term across **all** UI surfaces (replaces "Account Management" tab label / "Account Baseline" form heading / "Account balance" field — three names collapse to one) |
| Save button | `Update balances` (sentence case — replaces `Update Balances`) |

### Disambiguated buttons (D-21)

| Element | Old copy | New copy |
|---------|----------|----------|
| Paper-trade open form submit | `Open Position` | `Record paper trade` |
| Live-trade open form submit | `Open Position` | `Open live position` |
| Paper-trade close button | (varies) | `Close paper trade` |
| Live-trade close button | (varies) | `Close live position` |

### Error / fallback states

| Element | Copy |
|---------|------|
| HTMX 4xx surfacing (existing `handleTradesError` pattern) | Show inline alert: `Couldn't save changes. {server message}. Try again, or refresh the page if the problem persists.` |
| Status-strip refresh failure | Strip continues to show the last successful state with a tooltip on the dot: `Status check failed at {time}. Showing last known state.` Do NOT collapse the strip on failure. |
| Add-market 4xx | Inline below the form: `Couldn't add {market}. {server message}.` Form stays expanded with values intact so the operator can edit and retry. |
| First-run network failure (no state.json yet) | Falls through to the D-09 onboarding card — no separate "loading…" copy. |

### Destructive confirmations

| Action | Confirmation copy |
|--------|-------------------|
| Close paper trade | `Close this paper trade? Realised P&L will be locked in and the row becomes immutable.` (existing Phase 19 dialog — Phase 25 confirms wording, does not introduce new) |
| Close live position | `Close live position for {instrument}? This is recorded as a real position close.` |
| Delete market (if surfaced — planner confirms with operator whether this UI exists) | `Remove {market}? Closed trades and equity history are preserved; open positions must be closed first.` |
| No general-purpose "Are you sure?" — every destructive confirmation names the action and the consequence. |

### Strategy version footer (D-22)

| Element | Copy |
|---------|------|
| Footer literal | `Strategy {STRATEGY_VERSION}` (e.g. `Strategy v1.2.0`) — sourced from `system_params.STRATEGY_VERSION` via `dashboard_renderer/components/footer.py`, never hard-coded. Reconciles `dashboard-signals.html:837` (was `v1.0.0`) and `dashboard.html:1113` (was `v1.1.0`). |

---

## Layout & Interaction Contracts

> Phase 25 introduces non-trivial interaction contracts (two-axis nav, status-strip refresh, market-tab swap). These are out of scope for the standard 6-dimension UI checker but are load-bearing for the executor and auditor. Keep them here as a single source of truth.

### Two-axis nav (D-01, D-03..D-05, D-18)

- **Function tab strip** — `<nav role="tablist" aria-label="Function">`, anchors `<a role="tab" href="…" aria-current="page">…</a>` — **full-page navigation** (no HTMX swap). Active tab gets bottom-border 2px solid `--color-long` AND `aria-current="page"`. Inactive tabs render with `--color-text-muted` and no border-bottom. Roving tabindex per WAI-ARIA pattern: only the active anchor has `tabindex="0"`, others `tabindex="-1"`. ←/→ arrow keys move focus along the row. Tab key moves focus between strips (function strip ↔ market strip).
- **Market tab strip** — `<nav role="tablist" aria-label="Market">`, anchors with `hx-get="/markets/{id}/{function}"` + `hx-push-url="true"` + `hx-target="#market-panel"` + `hx-swap="innerHTML"`. Hidden entirely when on `/account` (D-04) — emit zero DOM, not `display:none`, to avoid keyboard trap. URL update preserves market-segment-in-URL invariant per D-03. Same roving-tabindex + arrow-key behaviour as function strip.
- **`+ Add market` chip** — last item in market strip, NOT a tab (excluded from `role="tablist"` traversal). Click toggles inline mini-form (`<details>` element, `aria-expanded` synced). Form posts to existing `POST /markets` (`web/routes/markets.py:135`) with `hx-headers='{"X-Trading-Signals-Auth":"…"}'` per established pattern. On 2xx, form collapses + market strip refreshes via HTMX `HX-Trigger` response header. On 4xx, form stays expanded with inline error per Copywriting contract.
- **Cookie `selected_market`** — server sets on every market-scoped page render (D-05). HttpOnly=false, SameSite=Lax, Path=/, no Domain attribute. Read by JS on `/account` to seed market-scoped function tab links (e.g. clicking "Signals" from `/account` routes to `/markets/{cookie_value}/signals`). Fallback if cookie missing: first market in `state.markets` ordering (deterministic; no SPI/AUDUSD preference baked into code).
- **localStorage NOT used.** Cookie is the only client-readable persistence (D-05). Any planner suggestion to add localStorage is rejected — cookie is sufficient and provides single source of truth.

### Active-tab affordance (D-18 — fixes current "no rule" bug)

```
Inactive tab:  color: var(--color-text-muted); border-bottom: 1px solid var(--color-border);
Hover/focus:   color: var(--color-text); background: var(--color-surface);
Active:        color: var(--color-text); border-bottom: 2px solid var(--color-long);
                aria-current="page"; tabindex="0"
Focus-visible: outline: 2px solid var(--color-focus-ring); outline-offset: 2px;
                (applies in addition to active styling — never replaces it)
```

### System Status strip (D-06, D-07, D-08)

- Server-rendered initial state via `dashboard_renderer/components/header.py` — emits `<span class="status-dot status-dot--{state}">`, `<time datetime="{iso}">{display}</time>`, `<span class="next-run">08:00 AWST · <span data-countdown="{next_run_at_iso}">…</span></span>`.
- JS countdown helper computes ms-to-target using a **fixed UTC+8 offset**, never `Intl.DateTimeFormat` browser-local TZ (operator may travel; daemon always runs AWST). Updates every 60s. Helper inlined in `shell.py` script block (no separate `/static/dashboard.js` per D-02).
- Refresh strategy (D-07): `hx-get="/status-strip"` triggered by **both** (a) a one-shot timer at 08:01 AWST (60s buffer past daemon trigger to give state.json time to write); (b) `visibilitychange` event when tab regains focus. No idle polling.
- New endpoint `GET /status-strip` returns the strip fragment HTML (planner's call whether route lives in `web/routes/dashboard.py` or new `web/routes/status.py`).
- AWST timezone: Perth, UTC+8, no DST. The daemon's PROJECT.md explicitly anchors to AWST. Operator's loose "AEST" in discussion was misnomer; this contract is canonical.

### Wide-table responsive (D-20)

- Each wide table (Open Positions 9 cols, Closed Trades 7 cols, Trailing Stops 7 cols) wrapped in `<div class="table-scroll" tabindex="0" role="region" aria-label="{table-name} (scrollable)">…</div>` with `overflow-x:auto`. `tabindex="0"` makes the scrollable region keyboard-focusable per WAI-ARIA scrollable-region guidance.
- Under `@media (max-width: 600px)`, tables switch to a stacked-row layout: each `<tr>` becomes a `display:block` card, `<th>` text repeats inline before `<td>` value via `data-label` attribute pattern. Existing `dashboard.html:645` media query is the extension point.
- Numeric columns retain mono font + tabular-nums in both layouts.

### A11y hardening (D-19) — verbatim work items

1. `<details data-instrument="…">` per-instrument trace-table toggle: sync `aria-expanded` attribute with the cookie-driven open/close state on render AND on click. Currently aria-expanded is desynced from visual state.
2. `<summary>` elements get visible focus rings (`:focus-visible { outline: 2px solid var(--color-focus-ring); outline-offset: 2px; }`). Currently relies on browser default which most don't render usefully.
3. FLAT/LONG/SHORT signal big-labels get a status-dot glyph (`<span class="status-dot status-dot--{state}" aria-hidden="true"></span>`) before the text. Non-colour cue for colourblind users. The `aria-hidden` is correct because the text already conveys state to AT.
4. Market `<select>` (`dashboard.html:672`) gets `id="market-select-{function}"` and the visible "Market" `<h2>` becomes `<label for="market-select-{function}">Market</label>` (or h2 keeps semantic role and a separate `<label>` is added — planner decides; pairing must exist either way).
5. **All inline `style="color:#eab308"` (and any other inline color literal) is removed and replaced with token classes:** `.signal-flat { color: var(--color-flat); }`, `.signal-long { color: var(--color-long); }`, `.signal-short { color: var(--color-short); }`. Grep gate: `grep -rn 'style="color:' dashboard*.html dashboard_renderer/` must return zero matches post-Phase-25.
6. All `<form>` inputs have explicit `<label for="…">…</label>` pairing. No `aria-label` substitutes for visible labels except where the input is decorative (e.g. quick-search) — not applicable here.
7. Tab strip arrow-key navigation per WAI-ARIA tabs pattern (D-18; covered above).

### Touch targets

- Tab anchors and `+ Add market` chip have minimum 44×44px hit area (`min-height: var(--touch-target-min)`; `padding` chosen so total height meets target). Applies to all viewports — desktop too, since trackpad clicks benefit equally.
- Buttons (`.btn-primary`, `.btn-row`) — desktop padding stays current; under `@media (max-width: 600px)` padding bumps to meet 44px. Mobile-only rule, not desktop, to avoid making the desktop dashboard feel chunky.

### Focus management

- Every interactive element supports `:focus-visible` with `outline: 2px solid var(--color-focus-ring); outline-offset: 2px`. No `outline: none` ever.
- Auto-focus only inside the `+ Add market` form on expansion (the instrument-code input). Nowhere else — operator's keyboard flow shouldn't be hijacked.

---

## Registry Safety

| Registry | Blocks Used | Safety Gate |
|----------|-------------|-------------|
| (none) | not applicable — no shadcn, no third-party UI registries | not applicable |

This is a vanilla-CSS / server-rendered HTML codebase. No registry import surface to vet. New CSS literals introduced this phase live entirely in `dashboard_renderer/shell.py` and the renderer component modules, all reviewed via the standard PR/codemoot path.

---

## Checker Sign-Off

- [ ] Dimension 1 Copywriting: PASS
- [ ] Dimension 2 Visuals: PASS
- [ ] Dimension 3 Color: PASS
- [ ] Dimension 4 Typography: PASS
- [ ] Dimension 5 Spacing: PASS
- [ ] Dimension 6 Registry Safety: PASS

**Approval:** pending
