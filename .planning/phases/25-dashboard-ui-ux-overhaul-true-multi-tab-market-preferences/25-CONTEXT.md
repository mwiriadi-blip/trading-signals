# Phase 25: Dashboard UI/UX overhaul — true multi-tab market preferences and first-run polish - Context

**Gathered:** 2026-05-05
**Status:** Ready for planning

<domain>
## Phase Boundary

UI-only refactor of the operator dashboard. Trader switches market once and every panel (Signals, Settings, Market Test) reflects that selection across page navs and refreshes; first-run UX shows ~1 empty card, not 11 stacked "n/a" panels; Settings page is scannable, not a wall of inputs; system trust surface (next-run countdown + last-run health) visible above the fold.

No signal/state/persistence changes. No new compute, no new state.json fields beyond what the existing daemon already writes (`last_run_at`, `last_run_status`, `next_run_at` are sourced from current state — verify in research).

Source: `/ui-ux-pro-max` review 2026-05-05. All 10 priority items in ROADMAP.md §Phase 25 are locked into scope.

</domain>

<decisions>
## Implementation Decisions

### Shell architecture (item #3 — consolidate 4 dashboard HTML files)
- **D-01:** Hybrid shell — function tabs (Signals / Account / Settings / Market Test) are full-page navs; only the **market tab strip** uses `hx-get` + `hx-push-url` to swap the panel without scroll/state loss.
  - Rationale: matches what `dashboard_renderer/` already supports (page composition wrappers in `pages.py`, fragment serving via `/?fragment=...` in `dashboard.py:1461`). Lower-risk than full htmx SPA shell while still de-duping the four-file chrome.
  - URL: `/markets/<MARKET>/<signals|settings|market-test>` for market-scoped functions; `/account` for the market-agnostic function.
- **D-02:** Common `<style>` and `<script>` are extracted to shared static assets. Decision deferred to research: whether existing `dashboard_renderer/shell.py` should emit shared static `<link>`/`<script>` tags or inline a single shared block. Either way, the 4-file × ~1000-LOC duplication must collapse.

### URL & market-state persistence (item #1)
- **D-03:** URL is the canonical source of selected market. `/markets/<MARKET>/<function>` for market-scoped functions; `/account` for Account.
- **D-04:** Account is bare `/account` — no market segment. Market tab strip is hidden when on Account (it's market-agnostic). Asymmetric URL is acceptable; Account is the only function that ignores market.
- **D-05:** Persistence model:
  - Within market-scoped functions, market is read from URL.
  - Cookie (`selected_market`, server-set, HttpOnly=false so JS can read for client-side links) remembers last market across sessions and seeds links from `/account` back to a market-scoped function.
  - localStorage NOT used (cookie is enough; one source of truth).
  - Fallback if cookie missing: first market in `state.markets` ordering (deterministic, no preference for SPI200 vs AUDUSD in code).

### System Status strip (item #7)
- **D-06:** Server-rendered + client countdown. Render `last_run_at` (ISO with `<time datetime="…">`), `last_run_status` (success/failure → green/amber dot), `next_run_at` once per page load. Countdown to next 08:00 AWST runs in JS from `next_run_at`.
- **D-07:** Auto-refresh strategy: **both** a single scheduled `hx-get` at 08:01 AWST **and** `visibilitychange`-triggered `hx-get` when tab regains focus. New endpoint: `GET /status-strip` → returns the strip fragment HTML.
  - Rationale: belt-and-braces. 08:01 timer covers tabs left open through the daily cycle; visibilitychange covers tabs parked in background. Zero polling on idle focused tabs.
  - JS computes ms until next 08:01 AWST (Perth, UTC+8 no DST) using a fixed offset; do not use the browser's local TZ.
- **D-08:** Timezone is **AWST** (Australian Western Standard Time, Perth, UTC+8 no DST). Operator wrote "AEST" in discussion — that was loose terminology; the daemon's cycle is 08:00 AWST per PROJECT.md and STATE.md.

### First-run empty-state collapse (item #5)
- **D-09:** Single boolean rule for hiding the per-instrument trace tables: `state.last_run_at is null` → show one onboarding card "Awaiting first daily run at 08:00 AWST. Calculations and equity curve will populate after the first cycle." Once any run completes, render whatever bars exist (even if some are still "need N bars, have M").
- **D-10:** All-zeros stats bar (`dashboard.html:762-769`) hidden until trade count ≥1 (closed paper trades + closed live trades combined).
- **D-11:** Equity chart hidden until ≥5 distinct points (already in scope from ROADMAP item #5; reaffirmed). "Distinct" means distinct `(date, value)` tuples — three identical points produce one distinct point, not three.

### Settings copy & grouping (item #6)
- **D-12:** Three fieldsets locked: **Entry rules** (ADX gate, momentum votes), **Risk** (long/short ATR stop, long/short risk %, contract cap), **Direction** (mode, 1-contract floor). Mapping of the 18 fields to fieldsets is the planner's job.
- **D-13:** Planner drafts label + 1-line `<small>` helper text for every field; operator reviews during `/gsd-plan-phase 25`. No copy walked through here. Operator will rewrite the 2-3 fields they care about during plan review.
- **D-14:** Market Test page shows inherited Settings defaults as `placeholder` text on override fields (already in ROADMAP scope).

### Mobile font scale (item #4)
- **D-15:** Proportional scale rebalance. `--fs-body` 14px → 16px; every other `--fs-*` token grows by `16/14` (≈1.143×). Hierarchy preserved. Round to whole pixels (existing tokens are integer px in `dashboard.html:76`).

### Add-market UX (item #1, sub-detail)
- **D-16:** "+ Add market" chip beside the market tab strip is an inline-expanding mini-form. Click expands to show instrument code + label inputs, `hx-post`s to existing `/markets` endpoint (`web/routes/markets.py:135`), collapses on success and refreshes the market tab strip via `hx-swap`. No modal, no redirect to Settings.
- **D-17:** This **replaces** the buried `<a class="btn-row btn-modify" href="#settings-tab">Add market</a>` in `dashboard.html:676`. Settings page may also retain its own add-market form (planner decides — single source of truth preferred).

### Active-tab affordance + a11y (item #2)
- **D-18:** Two tab strips → two independent WAI-ARIA tabs widgets, each with its own roving tabindex. ←/→ arrow nav within the active row only; Tab key moves focus between strips. Active tab gets distinct CSS rule (currently absent) AND `aria-current="page"`.

### a11y hardening (item #10)
- **D-19:** All ten sub-items in ROADMAP §Phase 25 item #10 are locked. Specific work items (sync `aria-expanded` with cookie-driven `details[data-instrument]`, focus rings on `<summary>`, status dot beside FLAT/LONG/SHORT colour labels, `id`/`for` pairing on Market `<select>`, replace inline `style="color:#eab308"` with `--color-flat`/`--color-long`/`--color-short` tokens) carry forward verbatim into PLAN.md tasks.

### Wide-table responsive (item #8)
- **D-20:** Wrap each wide table (Open Positions 9 cols, Closed Trades 7 cols, Trailing Stops 7 cols) in `overflow-x:auto` container. Add stacked-row layout under 600px. Existing single media query at `dashboard.html:645` is the extension point.

### Terminology & version reconciliation (item #9)
- **D-21:** Disambiguating renames:
  - Paper "Open position" button (`dashboard.html:800`) → "Record paper trade"
  - Live "Open Position" button → "Open live position"
  - Pick **one** term across "Account Management" (tab) / "Account Baseline" (form) / "Account balance" (field). Planner proposes a single term in PLAN.md; operator confirms during plan review.
- **D-22:** Strategy version: single source of truth via existing `STRATEGY_VERSION` constant (Phase 22 work). Reconcile `dashboard-signals.html:837` (v1.0.0) and `dashboard.html:1113` (v1.1.0) — both must read from the constant via the renderer, not hard-coded literals.

### Claude's Discretion
- Exact CSS class names, token names, and component file splits within `dashboard_renderer/components/` are planner's call (operator will catch anything offensive in plan review).
- Whether the `/status-strip` endpoint lives in `web/routes/dashboard.py` or a new `web/routes/status.py` is a planner decision.
- HTMX swap semantics for the market-tab swap (`outerHTML` vs `innerHTML`, `hx-target` selector) are planner's call provided URL push and scroll preservation work.
- Whether to introduce a small JS helper for the AWST countdown or inline the math in the strip template — planner decides.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Roadmap & milestone
- `.planning/ROADMAP.md` §Phase 25 — full 10-item scope, locked. Every item carries forward verbatim.
- `.planning/PROJECT.md` — project overview, current production state, 08:00 AWST cycle confirmation.
- `.planning/STATE.md` — milestone status, operator timezone (Perth/AWST UTC+8 no DST).

### UI review source
- `/ui-ux-pro-max` review output 2026-05-05 — referenced in ROADMAP.md as the source of all 10 items. If a saved transcript exists in `.planning/`, planner should locate and read it; if not, ROADMAP.md §Phase 25 is the canonical capture.

### Existing renderer (read before planning)
- `dashboard_renderer/__init__.py` and `dashboard_renderer/api.py` — public surface for page rendering.
- `dashboard_renderer/pages.py` — page composition wrappers (`render_dashboard_page_body`, currently delegates to `dashboard._render_single_page_dashboard`).
- `dashboard_renderer/shell.py` — HTML shell (`<head>`, HTMX/Chart.js script tags). This is the natural place to dedupe `<style>` and `<script>` chrome across the 4 pages.
- `dashboard_renderer/components/` — `header.py`, `footer.py`, `signals.py`, `settings.py`, `positions.py`, `trades.py`, `paper_trades.py`. Settings fieldset grouping work targets `settings.py`.
- `dashboard.py:2673` `_render_dashboard_page_nav` — current flat 4-tab nav. Replace with two-axis (market × function) nav rendering.
- `dashboard.py:1461` and `dashboard.py:1747` — existing `/?fragment=...` fragment-serving pattern for HTMX panel swaps. Reuse for the market-tab swap.

### Routes (read before planning)
- `web/routes/dashboard.py:165-204` — current flat function routes (`/`, `/signals`, `/account`, `/settings`, `/market-test`). Will gain `/markets/{market_id}/<function>` variants.
- `web/routes/markets.py:135` `POST /markets` — existing add-market endpoint. The "+ Add market" chip's mini-form posts here.
- `web/routes/markets.py:164-176` — existing `/markets/settings` and `/markets/{market_id}/settings` patterns. Note 2026-05-05 commit `18ea2c5` fixed a route-shadowing bug; the literal `/markets/settings` is registered before `/markets/{market_id}` to avoid collision. Same ordering rule applies to the new `/markets/{market_id}/<function>` routes.

### Templates currently in scope
- `dashboard.html` (1117 LOC) — main shell + chrome.
- `dashboard-signals.html` (841 LOC), `dashboard-account.html` (838 LOC), `dashboard-settings.html` (724 LOC), `dashboard-market-test.html` (696 LOC) — duplicated headers, styles, scripts. Target consolidation surface.
- Specific lines called out by ROADMAP §Phase 25: `dashboard.html:76` (--fs-body token), `:645` (mobile media query), `:658` (static last-run literal), `:672` (Market `<select>`), `:676` (buried Add-market link), `:683` (FLAT/LONG/SHORT colour-only labels), `:762-769` (all-zeros stats bar), `:800` (paper Open position button), `:837` (equity chart 3-point flat-line), `:1041-1074` (Settings forms), `:1113` (strategy version literal), `dashboard-signals.html:837` (strategy version literal v1.0.0).

### Tests as contract documentation
- `tests/test_web_app_factory.py:256-367` — pins existing market route patterns including the route-shadowing regression test. New routes must extend, not break, these assertions.
- `tests/test_dashboard.py:3120` — pins `hx-patch="/markets/settings"` form count ≥2.

### Prior phase context (precedent)
- `.planning/phases/16.1-phone-friendly-auth-ux-for-dashboard-access/` — most recent dashboard UX phase; precedent for mobile-friendly form decisions and AWST timezone handling.
- Phase 22 (`STRATEGY_VERSION` constant) — single source of truth for the strategy version literal reconciliation in item #9. Verify the constant exists and is renderer-accessible before planning the version-display fix.

### No new ADRs created
No new ADR files exist for Phase 25. UI-only refactor; architectural decisions captured in this CONTEXT.md.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `dashboard_renderer/components/*.py` — already split per panel; landing zone for the consolidation refactor. `header.py` is the natural home for the new System Status strip.
- HTMX 1.9.12 SRI-pinned + json-enc extension already loaded on every page (`dashboard.html:8-9`). No new vendor deps needed for the market-tab panel swap or the status-strip refresh.
- `/?fragment=...` fragment-serving pattern (`dashboard.py:1461`, `dashboard.py:1747`) is the precedent for HTMX partial responses. Extend with `/?fragment=market-panel-<function>-<market>` (or similar) for the market-tab swap.
- Existing `_resolved_contracts` runtime materialisation per market in `state.json` schema — Settings page renders per-market settings already; the multi-tab refactor surfaces what's already in state.

### Established Patterns
- All HTMX writes go through `hx-headers='{"X-Trading-Signals-Auth": "{{WEB_AUTH_SECRET}}"}'` (auth-gated). The new "+ Add market" mini-form's `hx-post` to `/markets` must follow this pattern.
- Atomic-write contract for state.json (DASH-01, STATE-01..07) is **not** touched by this phase — UI-only.
- All forms use `hx-on::after-request="handleTradesError(event)"` for 4xx surfacing. New status-strip refresh and market-panel swap should follow the same error-handling convention.
- Inline `<style>` + inline single-file dashboard pattern (DASH-01) is currently honored. The hybrid shell decision (D-01) means we keep that pattern but de-dupe via `dashboard_renderer/shell.py` rather than introducing external `/static/dashboard.css`. Planner confirms during research.

### Integration Points
- New `GET /status-strip` route → `web/routes/dashboard.py` or new `web/routes/status.py` (planner's call). Reads from existing state fields; no new state writes.
- New `GET /markets/{market_id}/<function>` routes → extend `web/routes/dashboard.py:165-204`. Must register **literal** function paths (or use route-ordering) to avoid the same shadowing class of bug fixed in `18ea2c5` for `/markets/settings`.
- Cookie `selected_market` set/read in either the dashboard route handler (server-set on every market-scoped page render) or a small middleware. Must be HttpOnly=false so JS can read it from `/account` to seed market-scoped links.
- Footer strategy-version literals (`dashboard.html:1113`, `dashboard-signals.html:837`) — replace with renderer-emitted token from `dashboard_renderer/components/footer.py`, sourced from the `STRATEGY_VERSION` constant introduced in Phase 22.

</code_context>

<specifics>
## Specific Ideas

- Status strip refresh wakes at **08:01 AWST**, not 08:00 — gives the daemon a 60-second head start; avoids the strip refreshing before `last_run_at` is updated.
- "Distinct points" for equity chart is `(date, value)` tuples, not array length. Three identical $100,000 points = one distinct point, chart stays hidden.
- Operator timezone strictness: Perth, UTC+8, no DST. JS countdown computes from a **fixed** UTC offset, never from `Intl.DateTimeFormat` browser-local TZ (operator may travel; the trading cycle is anchored to AWST regardless).
- Settings copy is a plan-phase review concern, not a discuss-phase concern. Operator expects to find the 2-3 fields where the planner's draft is wrong and rewrite those, not 18.

</specifics>

<deferred>
## Deferred Ideas

None raised — discussion stayed within the locked 10-item scope. If multi-account or live-broker integration comes up during planning, capture as v1.3+ candidate, do not fold in.

</deferred>

---

*Phase: 25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences*
*Context gathered: 2026-05-05*
