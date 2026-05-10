# Phase 25: Dashboard UI/UX overhaul — true multi-tab market preferences and first-run polish - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-05
**Phase:** 25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences
**Areas discussed:** Shell architecture, Account URL pattern, System Status strip refresh, Settings copy authority, Status strip refresh trigger, Add-market UX, First-run detection rule, Mobile font scale rebalance

---

## Shell architecture (item #3 — consolidate 4 dashboard HTML files)

| Option | Description | Selected |
|--------|-------------|----------|
| htmx panel-swap shell | Single shell template; hx-get + hx-push-url swap function panel; market tab strip swaps both URL market segment and panel. Highest payoff, most refactor surface. | |
| Multipage with shared static CSS/JS | Keep 4 routes; extract common style/script to /static/dashboard.css and /static/dashboard.js. Lower-risk smaller diff. | |
| Hybrid — multipage + htmx for market tab only | Function tabs are full-page navs; only market tab strip uses hx-get to swap panel. Compromise. | ✓ |

**User's choice:** Hybrid — multipage + htmx for market tab only.
**Notes:** Lower-risk than full htmx SPA shell; preserves natural function-tab navigation while keeping market switching smooth. Renderer's existing fragment-serving pattern (`/?fragment=...`) is the precedent.

---

## Account tab URL pattern (item #1, sub-detail)

| Option | Description | Selected |
|--------|-------------|----------|
| Bare /account | Account stays at /account with no market segment. Market tabs hidden when on Account. Asymmetric but honest. | ✓ |
| /markets/<MARKET>/account with market ignored | Uniform URL pattern; market segment present but Account ignores it. Cleaner state machine, slightly misleading URL. | |
| /account?market=<MARKET> | Bare path + query param. Compromise; some routers treat ? differently for caching. | |

**User's choice:** Bare /account.
**Notes:** Account is the only market-agnostic function. Asymmetric URL acceptable. Market tab strip hidden when on Account.

---

## System Status strip data source + refresh model (item #7)

| Option | Description | Selected |
|--------|-------------|----------|
| Server-render + client countdown | Server renders last_run_at, status, next_run_at; JS computes countdown locally. No polling. Cheapest. | ✓ |
| htmx polling every 30s | hx-get='/status' with hx-trigger='every 30s'. ~2880 extra req/day per open tab. | |
| htmx polling every 5min + SSE on run completion | Lighter poll + push on cycle finish. Most accurate, most code. | |

**User's choice:** Server-render + client countdown. Refresh trigger to be combined with auto-refresh at 08:00 AWST + run health update.
**Notes:** Operator wrote "08:00 AEST" — clarified to AWST per project timezone (Perth, UTC+8 no DST). Triggered follow-up question on refresh trigger.

---

## Settings copy authority (item #6)

| Option | Description | Selected |
|--------|-------------|----------|
| Planner drafts, you review in plan-phase | Planner proposes label + 1-line helper for each of 18 fields, grouped into 3 fieldsets. You review during /gsd-plan-phase. | ✓ |
| You dictate now, area-by-area | Walk through all 18 fields here. Slower but no surprise copy ships. | |
| Planner drafts, you review only in execute-phase | Skip review until UI rendered. Fastest, risk of redo. | |

**User's choice:** Planner drafts, you review in plan-phase.
**Notes:** Operator expects to rewrite 2-3 cryptic labels, not all 18.

---

## Status strip refresh trigger (follow-up to item #7)

| Option | Description | Selected |
|--------|-------------|----------|
| Schedule one hx-get at 08:01 AWST | JS computes ms until next 08:01 AWST and triggers single hx-get to refresh. Zero polling. | |
| hx-get on tab focus (visibilitychange) | Refresh whenever tab regains focus. No timer. Stale if tab focused through 08:00. | |
| Both — 08:01 timer + visibilitychange | Belt-and-braces. Covers tab-open-all-day and tab-parked-in-background. | ✓ |
| Page-load only, no auto-refresh | Static after render. User sees yesterday's stamp until they navigate. | |

**User's choice:** Both — 08:01 timer + visibilitychange.
**Notes:** New endpoint required: `GET /status-strip` returning the strip fragment HTML.

---

## Add-market UX (item #1, sub-detail)

| Option | Description | Selected |
|--------|-------------|----------|
| Inline expand to mini-form | Chip click reveals small inline form, hx-posts to existing /markets endpoint. Closest to current Settings add-market form. | ✓ |
| Modal dialog | Click opens overlay modal. More 'app-like', adds focus-trap a11y surface. | |
| Redirect to Settings | Chip is link to /settings#add-market. Reuses existing form verbatim, breaks stay-in-flow feel. | |

**User's choice:** Inline expand to mini-form.
**Notes:** Replaces the buried `<a class="btn-row btn-modify" href="#settings-tab">Add market</a>` in dashboard.html:676.

---

## First-run empty-state collapse rule (item #5)

| Option | Description | Selected |
|--------|-------------|----------|
| state.last_run_at is null | Single boolean check. Once any run completes, render whatever bars exist. Simple rule. | ✓ |
| Per-instrument: hide if 0 bars | Each instrument's table independently hides until ≥1 bar. Mixed states on day 1. | |
| Stricter: hide until ATR(14) computable (≥15 bars) | Only show when indicator math is meaningful. Longest empty-state window. | |

**User's choice:** state.last_run_at is null.
**Notes:** Cleanest rule for the planner to implement. No threshold tuning required.

---

## Mobile font scale rebalance (item #4)

| Option | Description | Selected |
|--------|-------------|----------|
| Proportional scale (multiply all by 16/14) | Every --fs-* token grows ~14.3%. Hierarchy preserved. Whole UI slightly larger. | ✓ |
| Pin headings, only body changes | Headings stay; body grows to 16. Hierarchy compresses. | |
| Planner drafts a new scale, you review | Defer to plan-phase. Planner proposes complete --fs-* table. | |

**User's choice:** Proportional scale (multiply all by 16/14).
**Notes:** Round to whole pixels (existing tokens are integer px in dashboard.html:76).

---

## Claude's Discretion

- Exact CSS class names, token names, and component file splits within `dashboard_renderer/components/`.
- Whether `/status-strip` lives in `web/routes/dashboard.py` or new `web/routes/status.py`.
- HTMX swap semantics for market-tab swap (`outerHTML` vs `innerHTML`, `hx-target` selector) — provided URL push and scroll preservation work.
- Whether to factor AWST countdown into a small JS helper or inline in the strip template.
- Whether `dashboard_renderer/shell.py` deduplication uses inline shared block vs external static stylesheet — research-phase decision.

## Deferred Ideas

None raised. Discussion stayed within the locked 10-item scope from ROADMAP.md §Phase 25.
