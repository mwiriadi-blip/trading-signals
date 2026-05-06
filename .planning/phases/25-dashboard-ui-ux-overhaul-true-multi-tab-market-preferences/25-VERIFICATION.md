---
phase: 25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences
verified: 2026-05-06T01:47:37Z
status: gaps_found
score: 19/22 decisions verified
overrides_applied: 0
gaps:
  - truth: "D-14: Market Test override fields render inherited Settings defaults as placeholder text"
    status: failed
    reason: "render_market_test_tab() in settings.py has no placeholder attributes sourced from Settings state. SUMMARY claims shipped; code has empty inputs with no placeholder inheritance."
    artifacts:
      - path: "dashboard_renderer/components/settings.py"
        issue: "render_market_test_tab() inputs have no placeholder='...' values from Settings defaults; static inputs only"
    missing:
      - "Per-market Settings values passed into render_market_test_tab() and emitted as placeholder='...' on ADX gate, votes, risk % override fields"
      - "Test asserting placeholder values appear in Market Test form HTML"

  - truth: "3 pre-existing test failures caused by Phase 25 D-11 not updated-compatible test suite"
    status: failed
    reason: "Three tests fail in test_dashboard.py that are broken by Phase 25 D-11 (equity gate). These are not pre-existing — they were passing before Phase 25 and Phase 25 D-11 broke them without fixing them."
    artifacts:
      - path: "tests/test_dashboard.py"
        issue: "test_chart_payload_escapes_script_close — D-11 hides chart at <5 points so injection-defense test never fires (state has 1 equity entry); test expects chart to render"
      - path: "tests/test_dashboard.py"
        issue: "test_equity_chart_empty_state_placeholder — asserts old copy 'No equity history yet — first full run needed'; D-11 changed copy to 'Chart appears once 5 daily equity points have been recorded.' but test was not updated"
      - path: "tests/test_dashboard.py"
        issue: "test_empty_state_matches_committed — golden_empty.html fixture drifted (rendered=49057 bytes, golden=48413 bytes; URLs differ /signals vs /markets/SPI200/signals)"
    missing:
      - "Update test_chart_payload_escapes_script_close to use >=5 equity entries so chart renders and injection defense can be tested"
      - "Update test_equity_chart_empty_state_placeholder to assert new D-11 placeholder copy"
      - "Regenerate golden_empty.html to match current render output"
---

# Phase 25: Dashboard UI/UX Overhaul Verification Report

**Phase Goal:** UI-only refactor of the operator dashboard. True multi-tab market preferences (URL-canonical), first-run empty-state collapse, Settings scannable fieldsets, system trust surface visible above the fold. No signal/state/persistence changes.
**Verified:** 2026-05-06T01:47:37Z
**Status:** gaps_found
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths — Decision-by-Decision

| # | Decision | Status | Evidence |
|---|----------|--------|----------|
| D-01 | Hybrid shell: market tabs use hx-get/hx-push-url HTMX swap; function tabs are full-page nav | VERIFIED | nav.py: market anchors have hx-get/hx-target="#market-panel"/hx-push-url="true"; function anchors have plain hrefs |
| D-02 | CSS/JS extracted to shared assets.py; no external /static/ files | VERIFIED | dashboard_renderer/assets.py is source of truth; shell.py imports from it; no link rel=stylesheet |
| D-03 | URL is canonical source of selected market: /markets/<MARKET>/<function> | VERIFIED | web/routes/dashboard.py: 3 new GET routes /markets/{market_id}/{signals,settings,market-test} registered |
| D-04 | Account is bare /account; market tab strip emits zero DOM (not display:none) when active_function=account | VERIFIED | nav.py:100 — `if active_function == 'account': return ''` |
| D-05 | Cookie selected_market: SameSite=Lax, no HttpOnly, HttpOnly=false for JS readability | VERIFIED | _MARKET_COOKIE_ATTRS has SameSite=Lax but no HttpOnly; tests TestPhase25SelectedMarketCookie pass |
| D-06 | Server-rendered status strip: last_run_at, last_run_status (dot), next_run_at | VERIFIED | header.py render_status_strip() implemented; formatters.py _derive_status_dot_class() covers 4 states |
| D-07 | Auto-refresh: 08:01 AWST one-shot + visibilitychange hx-get | VERIFIED | shell.py _STATUS_STRIP_REFRESH_JS + status strip has hx-trigger="refresh, visibilitychange..." |
| D-08 | AWST (UTC+8, no DST) — fixed offset, never browser TZ | VERIFIED | shell.py: "Fixed UTC+8 offset; ignores browser local TZ"; Date.UTC arithmetic used |
| D-09 | First-run: last_run is null shows single onboarding card, hides 11 trace panels | VERIFIED | signals.py: gate at top of render_signal_cards — onboarding-card with locked copy |
| D-10 | Stats bar hidden until closed_paper + closed_live >= 1 | VERIFIED | paper_trades.py: stats_html = '' when combined < 1; DOM absent not display:none |
| D-11 | Equity chart hidden until >=5 distinct (date, value) tuples | VERIFIED | dashboard.py _distinct_equity_tuples() + gate at len(distinct) < 5; locked copy "Chart appears once 5 daily equity points have been recorded." |
| D-12 | Three Settings fieldsets: Entry rules / Risk / Direction | VERIFIED | settings.py: 3 fieldsets with legend elements; TestPhase25Settings passes |
| D-13 | Helper text drafted and operator-approved for all Settings fields | VERIFIED | Per SUMMARY: operator answered "Approve all 9 as drafted" at checkpoint; <small class="field-help"> present in settings.py |
| D-14 | Market Test override fields show inherited Settings defaults as placeholder="…" | FAILED | render_market_test_tab() has no placeholder attributes; inputs are static with no state-derived placeholder values; no test covers this |
| D-15 | Font token rebalance: --fs-body 14→16px; proportional scale | VERIFIED | assets.py: --fs-body: 16px, --fs-label: 14px, --fs-heading: 23px, --fs-display: 32px; TestPhase25Fonts 4/4 pass |
| D-16 | +Add market chip: inline-expanding mini-form beside market tab strip | VERIFIED | nav.py render_add_market_chip() returns `<details class="add-market-chip">` with hx-post to /markets |
| D-17 | Buried href="#settings-tab" Add market link removed | VERIFIED | grep returns 0 matches for btn-modify.*Add market in dashboard.py |
| D-18 | WAI-ARIA tabs: role=tablist, aria-current=page, roving tabindex, arrow-key nav | VERIFIED | nav.py: role=tablist/tab, aria-current=page/false, tabindex 0/-1; shell.py _TABS_KEYBOARD_JS: ArrowLeft/Right/Home/End |
| D-19 | A11y hardening: aria-expanded sync, focus rings, status-dot glyphs, label-for, zero inline color | VERIFIED | aria-expanded: dashboard.py imports _DETAILS_ARIA_SYNC_INLINE_JS and emits in shell; focus-visible: assets.py 773-780; status-dot glyphs: signals.py big-label; label-for: settings.py + dashboard.py explicit for/id pairs; inline color grep returns 0 |
| D-20 | Wide tables wrapped in overflow-x:auto scrollable region with data-label + stacked-row @media 600px | VERIFIED | positions.py + trades.py: table-scroll wrapper with tabindex=0 and aria-label=(scrollable); assets.py @media 600px stacked-row CSS |
| D-21 | Button renames and Account terminology unified | VERIFIED | dashboard.py: "Record paper trade", "Open live position", "Update balances"; "Account Management" → 0 results grep |
| D-22 | Strategy version: single source of truth via _resolve_strategy_version(state) | VERIFIED | dashboard_renderer/api.py resolves via d._resolve_strategy_version(state); render_footer(strategy_version) takes arg; no hard-coded literals in renderer |

**Decision score: 21/22 verified (D-14 failed)**

### OR-Resolutions

| # | Resolution | Status | Evidence |
|---|-----------|--------|----------|
| OR-01 | Status dot 3-state: success/stale/failure/never from state['last_run'] + 26h grace | VERIFIED | formatters.py _derive_status_dot_class: 4 branches; TestPhase25StatusDotDerivation 7/7 pass |
| OR-02 | Countdown format: >24h shows day+time+AWST, <24h Nh Mm, <1h NNm | VERIFIED | formatters.py _format_countdown_text; static "08:00 AWST" prefix always rendered server-side |
| OR-03 | First-market fallback: insertion-order first market in state.markets | VERIFIED | nav.py _first_market_id: `next(iter(markets))` |

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `dashboard_renderer/components/nav.py` | Two-axis nav (function + market strips) | VERIFIED | render_function_strip, render_market_strip, render_two_axis_nav, render_add_market_chip |
| `dashboard_renderer/assets.py` | Single source of truth for CSS tokens + shell constants | VERIFIED | All font tokens, color tokens, new Phase 25 tokens present |
| `dashboard_renderer/components/header.py` | render_status_strip() | VERIFIED | Implemented with AWST datetime, aria-live=polite |
| `dashboard_renderer/formatters.py` | OR-01/OR-02 helpers | VERIFIED | _derive_status_dot_class, _compute_next_awst_0800, _format_countdown_text |
| `dashboard_renderer/shell.py` | _AWST_COUNTDOWN_JS, _TABS_KEYBOARD_JS, _STATUS_STRIP_REFRESH_JS, _DETAILS_ARIA_SYNC_JS | VERIFIED | All 4 JS constants present and wired |
| `dashboard_renderer/context.py` | active_function + active_market fields | VERIFIED | RenderContext has both fields |
| `dashboard_renderer/pages.py` | render_panel_only for HTMX swap | VERIFIED | Present; wired into HTMX panel path |
| `dashboard_renderer/components/signals.py` | D-09 onboarding gate + D-19 signal-class wiring | VERIFIED | Gate at top of render_signal_cards; signal-flat/long/short classes |
| `dashboard_renderer/components/paper_trades.py` | D-10 stats bar gate | VERIFIED | stats_html='' when closed < 1 |
| `dashboard.py` | D-11 _distinct_equity_tuples + chart gate | VERIFIED | Helper and gate at line 1860-1891 |
| `dashboard_renderer/components/settings.py` | D-12 fieldsets + D-13 helper text + D-14 placeholder inheritance | STUB (D-14) | D-12 and D-13 done; D-14 placeholder inheritance not implemented |
| `web/routes/dashboard.py` | GET /markets/{id}/{function} + /status-strip + /markets-strip + cookie helpers | VERIFIED | All 5 routes registered; cookie helpers present |
| `tests/test_dashboard.py` | Phase 25 test suite | PARTIAL | 308 pass; 3 broken by D-11 implementation without test-suite update |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| market tab anchor | /markets/{id}/{function} route | hx-get + hx-push-url | VERIFIED | nav.py emits hx-get="/markets/{esc}/{function}" hx-target="#market-panel" |
| /status-strip endpoint | render_status_strip | auth-gated GET handler | VERIFIED | web/routes/dashboard.py real handler; auth via AuthMiddleware |
| render_status_strip | state['last_run'] | formatters._derive_status_dot_class | VERIFIED | header.py passes state and now_awst to formatter |
| _DETAILS_ARIA_SYNC_JS | dashboard.py shell emit | import alias | VERIFIED | dashboard.py imports as _DETAILS_ARIA_SYNC_INLINE_JS; emits in _render_html_shell |
| strategy version | state → _resolve_strategy_version → render_footer | api.py pipeline | VERIFIED | api.py:33-37 chains resolution |
| +Add market chip | POST /markets | hx-post + hx-headers auth | VERIFIED | nav.py chip form has hx-headers auth header |

---

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| render_status_strip | last_run_at, last_run_status | state['last_run'] | Yes — reads daemon state | FLOWING |
| render_signal_cards | last_run gate | state.get('last_run') | Yes — None vs set | FLOWING |
| _render_equity_chart_container | distinct equity tuples | state['equity_history'] | Yes — deduped from state | FLOWING |
| render_paper_trades_region | closed_paper + closed_live | state['paper_trades'] + state['closed_trades'] | Yes — counts from state | FLOWING |
| render_market_test_tab | placeholder values | NOT WIRED — static form | No | HOLLOW (D-14 not implemented) |

---

## Behavioral Spot-Checks

| Behavior | Result | Status |
|----------|--------|--------|
| GET /markets/{market_id}/signals returns 200 with auth | TestPhase25MarketRoutes 5/5 pass | PASS |
| GET /status-strip returns HTML fragment with id=status-strip | TestPhase25StatusStripEndpoint 3/3 pass | PASS |
| Unauthed /status-strip returns 401/403 | test_status_strip_unauthed_returns_401_or_403 pass | PASS |
| selected_market cookie set on market route | TestPhase25SelectedMarketCookie 2/2 pass | PASS |
| D-11: 3 identical equity points hides chart | TestPhase25Equity 2/2 pass | PASS |
| D-09: last_run=None renders onboarding card | TestPhase25FirstRun 3/3 pass | PASS |
| D-18: aria-current=page on active tab | TestPhase25ActiveTab 3/3 pass | PASS |
| D-19 #5: zero inline color styles | TestPhase25NoInlineColor 2/2 pass | PASS |
| D-20: table-scroll wrappers present | TestPhase25WideTable 2/2 pass | PASS |
| D-21: button renames | TestPhase25ButtonRename 3/3 pass | PASS |
| test_chart_payload_escapes_script_close | FAILS — D-11 hides chart at 1 equity entry | FAIL |
| test_equity_chart_empty_state_placeholder | FAILS — old copy assertion not updated | FAIL |
| test_empty_state_matches_committed | FAILS — golden fixture drift | FAIL |

---

## Requirements Coverage

All 22 D-decisions from CONTEXT.md and 3 OR-resolutions from CONTEXT.md assessed. 21/22 D-decisions verified. D-14 failed.

---

## Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| `dashboard_renderer/components/settings.py` render_market_test_tab() | D-14 stub — static inputs with no placeholder values from Settings state | BLOCKER | Market Test UX shows blank inputs instead of operator's current Settings defaults; D-14 was the stated requirement |
| `tests/test_dashboard.py` test_equity_chart_empty_state_placeholder | Old placeholder copy assertion "No equity history yet — first full run needed" | BLOCKER | Test suite has 3 test failures; CI would reject |
| `tests/test_dashboard.py` test_chart_payload_escapes_script_close | XSS injection defense test now untestable due to D-11 gate | BLOCKER | Security regression test no longer exercises the defense |
| `tests/fixtures/dashboard/golden_empty.html` | Golden fixture 644 bytes shorter than current render | WARNING | _render_to_str produces different output than golden; URL format changed |

---

## Human Verification Required

### 1. D-14 placeholder UX

**Test:** Open the dashboard, navigate to Market Test tab. Check override fields (ADX, momentum votes, risk %).
**Expected:** Inputs show placeholder text like `placeholder="25"` reflecting current Settings defaults.
**Why human:** The render is static in code; only a browser render with real state can confirm the UX intent.

### 2. Mobile responsive behavior

**Test:** Open dashboard at 599px width on a real device or browser devtools narrow viewport.
**Expected:** Wide tables (Open Positions, Closed Trades) stack rows with data-label column headers visible inline; tab anchors have >=44px hit area.
**Why human:** CSS stacked-row layout and touch target size can only be confirmed visually.

### 3. HTMX market tab swap in browser

**Test:** On a live instance with two markets, click between market tabs on the Signals page.
**Expected:** Panel content swaps without page reload; URL updates to /markets/{MARKET}/signals; browser history stack is correct.
**Why human:** hx-push-url behavior and HTMX swap requires browser execution.

### 4. Status strip countdown accuracy

**Test:** Observe status strip in browser near 08:00 AWST on a weekday.
**Expected:** Countdown shows "in Nm" format then "running now..." and auto-refreshes at 08:01 AWST.
**Why human:** Time-triggered behavior requires real-time observation.

---

## Gaps Summary

**2 genuine gaps found:**

**Gap 1 — D-14 not implemented (BLOCKER)**
The SUMMARY for 25-08 claims "D-14: Market Test override fields render inherited defaults as placeholder='...' instead of pre-filling values" shipped. The code at `dashboard_renderer/components/settings.py::render_market_test_tab()` has static inputs with no placeholder values derived from state. No test was written for D-14 (no xfail was ever scaffolded for this in test_dashboard.py). This is a false claim in the SUMMARY — the feature is missing.

**Gap 2 — Three test failures introduced by D-11 (BLOCKER)**
D-11 (equity chart gate) changed the chart behavior and placeholder copy but left 3 pre-Phase-25 tests broken:
1. `test_chart_payload_escapes_script_close` — uses 1-entry equity state; D-11 hides chart so the XSS injection-defense branch is never reached. The security regression test is now non-functional.
2. `test_equity_chart_empty_state_placeholder` — asserts old copy "No equity history yet — first full run needed" but D-11 changed the copy to "Chart appears once 5 daily equity points have been recorded."
3. `test_empty_state_matches_committed` — golden_empty.html fixture is 644 bytes smaller than current render.

The SUMMARYs from Plans 25-08 and 25-09 note these as "pre-existing follow-up items from Plan 25-07's D-11 work" — but they originate from Phase 25 work, not from earlier phases. The XSS defense test being non-functional is particularly concerning.

**Non-gap observations:**
- deploy.sh test failures (3) are pre-Phase-25 and unrelated.
- The dashboard*.html files showing v1.0.0 are runtime-generated cached files; the regeneration mechanism (`_REQUIRED_DASHBOARD_MARKER` changed to `class="tabs tabs-function"`) forces regen on first post-deploy request. This is the intended behavior, not a bug.
- D-14 has no test coverage at all (no xfail was ever scaffolded in Plan 25-01 test scaffolding), which means it was effectively descoped from the test contract but not from the CONTEXT/UI-SPEC decision list.

---

_Verified: 2026-05-06T01:47:37Z_
_Verifier: Claude (gsd-verifier)_
