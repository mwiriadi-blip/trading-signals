---
phase: 25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences
verified: 2026-05-07T00:00:00Z
status: verified
score: 22/22 decisions verified
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 19/22
  previous_verified: 2026-05-06T01:47:37Z
  gaps_closed:
    - "D-14: Market Test override fields render inherited Settings defaults as placeholder text"
    - "test_chart_payload_escapes_script_close green — </script> count updated 5→6 + ≥5 equity entries seeded"
    - "test_equity_chart_empty_state_placeholder green — assertion updated to D-11 copy"
    - "test_empty_state_matches_committed green — empty_state.json + golden regenerated"
  gaps_remaining: []
  regressions: []
  closure_commits:
    - 8f62f1b  # 25-11 task 2/3: D-11 test repairs
    - b33d67c  # 25-11 task 4: golden regen
    - aa594f2  # 25-11 task 1: D-14 placeholder inheritance
  followup_phase: 26-phase-25-followup-multi-tab-scoping-fixes
---

# Phase 25: Dashboard UI/UX Overhaul Verification Report

**Phase Goal:** UI-only refactor of the operator dashboard. True multi-tab market preferences (URL-canonical), first-run empty-state collapse, Settings scannable fieldsets, system trust surface visible above the fold. No signal/state/persistence changes.

**Verified:** 2026-05-07
**Status:** verified
**Re-verification:** Yes — fresh audit against current main after Plan 25-11 gap closure and Phase 26 follow-up work (commits up through `5bec4be`).

---

## Re-verification Verdict

All four gaps from the 2026-05-06 audit are closed. Headline value prop (URL-canonical multi-tab market scoping) is now end-to-end live in current code: `/markets/{M}/{fn}` flows `active_market` from route → `render_dashboard_as_str` → `_build_render_context` → `_render_page_body` → leaf renderers (`render_signal_cards`, `render_settings_tab`, `render_market_test_tab`), and each leaf filters `display_names` to the active market. Plan 25-11 wired D-14 placeholder inheritance (7 fields) and repaired the 3 D-11-broken tests; Phase 26 plans 04/05 then closed the remaining multi-tab scoping leakage (B1/B2/B3) that Phase 25 missed but the original verification did not surface.

**Full pytest suite:** 1794 passed, 0 failed (`.venv/bin/pytest -q` on commit `5bec4be`).

---

## Goal Achievement

### Observable Truths — Decision-by-Decision (current main)

| # | Decision | Status | Evidence |
|---|----------|--------|----------|
| D-01 | Hybrid shell: market tabs use hx-get/hx-push-url; function tabs full-page nav | VERIFIED | `dashboard_renderer/components/nav.py` market anchors emit hx-get + hx-push-url=true; function anchors are plain hrefs |
| D-02 | CSS/JS extracted to shared assets.py | VERIFIED | `dashboard_renderer/assets.py` is single source; no `<link rel=stylesheet>` |
| D-03 | URL canonical for selected market: /markets/<M>/<fn> | VERIFIED | `web/routes/dashboard.py:316-326` registers all 3 GET routes; `_serve_market_scoped_page` passes `active_market=market_id` into renderer (`api.py:28,40` and onward); `dashboard.py:1956,2052` reads `ctx.active_market` and falls back to `_first_market_id(state)` |
| D-04 | Account is bare /account; market strip empty when active_function=account | VERIFIED | `nav.py` returns `''` for market strip when `active_function=='account'` |
| D-05 | Cookie selected_market: SameSite=Lax, Secure, no HttpOnly | VERIFIED | `web/routes/dashboard.py:236` `_MARKET_COOKIE_ATTRS = '; Max-Age=2592000; Path=/; Secure; SameSite=Lax'`; Plan 26-07 R7 tightened write-path regex to `^[A-Z0-9_]{2,20}$` allowlist |
| D-06 | Server-rendered status strip: last_run_at, status dot, next_run_at | VERIFIED | `dashboard_renderer/components/header.py` render_status_strip implemented; formatters._derive_status_dot_class covers 4 states |
| D-07 | Auto-refresh: 08:01 AWST one-shot + visibilitychange | VERIFIED | `shell.py` _STATUS_STRIP_REFRESH_JS + status strip hx-trigger="refresh, visibilitychange…" |
| D-08 | AWST UTC+8 fixed offset | VERIFIED | `shell.py` "Fixed UTC+8 offset; ignores browser local TZ"; Date.UTC arithmetic |
| D-09 | First-run gate: last_run is None → onboarding card | VERIFIED | `signals.py:13-19` early return with onboarding-card section |
| D-10 | Stats bar hidden until closed_paper + closed_live ≥1 | VERIFIED | `paper_trades.py` stats_html='' when combined < 1 |
| D-11 | Equity chart hidden until ≥5 distinct (date,value) tuples | VERIFIED | `dashboard.py:1846-1885` `_distinct_equity_tuples` + gate; copy "Chart appears once 5 daily equity points have been recorded." Tests: TestPhase25Equity green, test_equity_chart_empty_state_placeholder green (Plan 25-11) |
| D-12 | Three Settings fieldsets: Entry rules / Risk / Direction | VERIFIED | `settings.py` 3 fieldsets with legend elements; TestPhase25Settings green |
| D-13 | Helper text drafted and operator-approved | VERIFIED | `settings.py` `<small class="field-help">` present; helper text locked per `25-helper-text-locked.md` |
| D-14 | Market Test override fields show inherited Settings defaults as placeholder | VERIFIED (NEW — closed by Plan 25-11) | `settings.py:121-178` `render_market_test_tab` derives 7 placeholders from `_strategy_settings_for(state, target_market)` (ADX, votes, risk_long, risk_short, atr_long, atr_short, contract_cap); TestPhase25MarketTestPlaceholders class added at `tests/test_dashboard.py:3512` |
| D-15 | Font token rebalance: --fs-body 14→16px proportional | VERIFIED | `assets.py` --fs-body:16px, --fs-label:14px, --fs-heading:23px, --fs-display:32px |
| D-16 | +Add market chip: inline-expanding mini-form | VERIFIED | `nav.py` render_add_market_chip returns `<details class="add-market-chip">` with hx-post |
| D-17 | Buried href="#settings-tab" Add market link removed | VERIFIED | grep returns 0 matches |
| D-18 | WAI-ARIA tabs: roving tabindex, arrow-key nav | VERIFIED | `nav.py` role=tablist/tab, aria-current=page/false, tabindex 0/-1; shell.py _TABS_KEYBOARD_JS handles ArrowLeft/Right/Home/End |
| D-19 | A11y hardening (10 sub-items) | VERIFIED | aria-expanded sync, focus rings, status-dot glyphs, label-for, zero inline color (grep returns 0) |
| D-20 | Wide tables overflow-x:auto + stacked-row @media 600px | VERIFIED | `positions.py` + `trades.py` table-scroll wrapper with tabindex=0; assets.py @media 600px stacked-row CSS |
| D-21 | Button renames + Account terminology unified | VERIFIED | `dashboard.py` "Record paper trade" :1439, "Open live position" :855, "Update balances" :1803; "Account Management" → 0 results |
| D-22 | Strategy version: single source of truth | VERIFIED | `dashboard_renderer/api.py:33` resolves via `d._resolve_strategy_version(state)`; no hardcoded v1.0.0 / v1.1.0 literals in `dashboard_renderer/` or `templates/` |

**Decision score: 22/22 verified.** D-14 was closed by Plan 25-11 commit `aa594f2`; the previous fail at the placeholder layer is now wired with state-derived values and covered by `TestPhase25MarketTestPlaceholders`.

### OR-Resolutions

| # | Resolution | Status | Evidence |
|---|------------|--------|----------|
| OR-01 | Status dot 3-state from state['last_run'] + 26h grace | VERIFIED | `formatters.py::_derive_status_dot_class` 4 branches |
| OR-02 | Countdown format >24h day+time, <24h Nh Mm, <1h NNm | VERIFIED | `formatters.py::_format_countdown_text`; static "08:00 AWST" prefix |
| OR-03 | First-market fallback: insertion-order first market | VERIFIED | `nav.py::_first_market_id`: `next(iter(markets))` |

---

## Multi-Tab Market Scoping (Headline Value Prop)

Phase 25 shipped the URL routes and cookie but Phase 26 audit found the renderer still leaked all markets onto every per-market URL because `active_market` was being dropped between `_build_render_context` and the leaf renderers. That gap was closed by Phase 26 plans 26-04 and 26-05 (both on this branch, commits `9a49d88`, `28043eb`, `7bcd3db`, `8154323`, `65164a7`). Re-verifying the value prop end-to-end:

| Layer | File | Behaviour | Status |
|-------|------|-----------|--------|
| Route | `web/routes/dashboard.py:316-326` | 3 GET routes registered | VERIFIED |
| Route → renderer | `web/routes/dashboard.py:283-297` | `render_panel_html` / `render_dashboard_as_str` called with `active_market=market_id` | VERIFIED |
| Renderer entry | `dashboard_renderer/api.py:28-40, 66-82, 127-143, 153-166, 184-193` | `active_market` flows through `render_dashboard_as_str` → `render_dashboard_page` → `_build_render_context` → `_render_page_body` | VERIFIED |
| Leaf renderer (signals) | `dashboard_renderer/components/signals.py:27-30` | `if active_market and active_market in display_names: display_names = {active_market: …}` | VERIFIED |
| Leaf renderer (settings) | `dashboard_renderer/components/settings.py` `render_settings_tab` | Filters `display_names` to active_market | VERIFIED |
| Leaf renderer (market-test) | `dashboard_renderer/components/settings.py:121-137` | Filters `display_names` to active_market AND derives D-14 placeholders from active market's strategy_settings | VERIFIED |
| Test contract | `tests/test_web_app_factory.py:615` `TestPhase26MarketScoping` | 4/4 tests exercise SPI200 / AUDUSD / ESM scoping (xfails removed in commit `1f56726`) | VERIFIED |
| Placeholder substitution on market-scoped path | `web/routes/dashboard.py:306` `_substitute(body.encode('utf-8'), request)` | Phase 26 B2/B3 — fixes auth/secret/session-note placeholder leak on `/markets/{M}/{fn}` | VERIFIED |

**Verdict:** Headline value prop is real in current code; trader switching to `/markets/AUDUSD/signals` now sees only the AUDUSD signal card, not all markets. The Phase 26 follow-up did not retroactively change Phase 25's D-decision list — D-03 was always specified to make URL canonical for market state, but the renderer didn't honour it until Phase 26. We treat this as a Phase-25 contract that was finally fulfilled in Phase 26, and credit D-03 as VERIFIED in current main.

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `dashboard_renderer/components/nav.py` | Two-axis nav | VERIFIED | render_function_strip, render_market_strip, render_two_axis_nav, render_add_market_chip |
| `dashboard_renderer/assets.py` | CSS tokens + shell constants | VERIFIED | All Phase 25 tokens present |
| `dashboard_renderer/components/header.py` | render_status_strip | VERIFIED | AWST datetime, aria-live=polite |
| `dashboard_renderer/formatters.py` | OR-01/OR-02 helpers | VERIFIED | _derive_status_dot_class, _compute_next_awst_0800, _format_countdown_text |
| `dashboard_renderer/shell.py` | 4 JS constants | VERIFIED | _AWST_COUNTDOWN_JS, _TABS_KEYBOARD_JS, _STATUS_STRIP_REFRESH_JS, _DETAILS_ARIA_SYNC_JS |
| `dashboard_renderer/context.py` | active_function + active_market fields | VERIFIED | Both fields present and threaded by Phase 26 |
| `dashboard_renderer/pages.py` / `api.py` | render_panel_html for HTMX swap | VERIFIED | Phase 26 Plan 06 split out; replaces legacy mixed-return form |
| `dashboard_renderer/components/signals.py` | D-09 onboarding gate + D-19 wiring | VERIFIED | Gate at top of render_signal_cards |
| `dashboard_renderer/components/paper_trades.py` | D-10 stats bar gate | VERIFIED | stats_html='' when closed < 1 |
| `dashboard.py` | D-11 _distinct_equity_tuples + gate | VERIFIED | Helper at :1846, gate at :1877 |
| `dashboard_renderer/components/settings.py` | D-12 fieldsets + D-13 helper text + D-14 placeholders | VERIFIED | All three present; D-14 closed by Plan 25-11 |
| `web/routes/dashboard.py` | 3 market routes + /status-strip + cookie helpers | VERIFIED | All routes registered; cookie discipline tightened by Plan 26-07 |
| `tests/test_dashboard.py` | Phase 25 test suite | VERIFIED | 231 tests; the 3 D-11-broken tests green; TestPhase25MarketTestPlaceholders added |
| `tests/test_web_app_factory.py` | Phase 25 + Phase 26 scoping suites | VERIFIED | 35 tests; TestPhase26MarketScoping 4/4 green |

---

## Key Link Verification

| From | To | Via | Status |
|------|----|-----|--------|
| market tab anchor | /markets/{id}/{function} | hx-get + hx-push-url | VERIFIED |
| /markets/{M}/{fn} route | per-market render | active_market kwarg threaded api → context → leaf | VERIFIED |
| /status-strip endpoint | render_status_strip | auth-gated GET handler | VERIFIED |
| render_status_strip | state['last_run'] | formatters._derive_status_dot_class | VERIFIED |
| _DETAILS_ARIA_SYNC_JS | dashboard.py shell emit | import alias | VERIFIED |
| strategy version | state → _resolve_strategy_version → render_footer | api.py pipeline | VERIFIED |
| +Add market chip | POST /markets | hx-post + hx-headers auth | VERIFIED |
| market-scoped page | placeholder substitution | _substitute helper (Plan 26-04) | VERIFIED |
| selected_market write | regex allowlist | `_MARKET_ID_RE.fullmatch` (Plan 26-07 R7) | VERIFIED |

---

## Behavioral Spot-Checks

| Behavior | Result | Status |
|----------|--------|--------|
| Full pytest suite | 1794 passed in 110.19s | PASS |
| TestPhase26MarketScoping (4 tests) | green per 26-05-SUMMARY commit `8154323` | PASS |
| TestPhase25MarketTestPlaceholders (D-14) | green per 25-11-SUMMARY commit `aa594f2` | PASS |
| test_chart_payload_escapes_script_close | green per 25-11 commit `8f62f1b` (count 5→6, ≥5 equity entries) | PASS |
| test_equity_chart_empty_state_placeholder | green per 25-11 commit `8f62f1b` | PASS |
| test_empty_state_matches_committed | green per 25-11 commit `b33d67c` (golden regen) | PASS |

---

## Anti-Patterns Found

None blocking. The two genuine issues from the 2026-05-06 audit (D-14 stub, 3 broken D-11 tests) are closed in current code.

Note for orchestrator: Phase 26 plans 04/05 closed a multi-tab scoping leakage that the original Phase 25 verification missed. The original audit verified the routes existed (D-03 tab) but did not run an eyebrow-level scoping assertion against the rendered output. Future verifications of any "URL-canonical state" decision should include a content-level scoping check, not just route-existence + cookie-attribute checks.

---

## Human Verification Required

None blocking. The previous audit's 4 human-verification items remain advisable for production smoke (mobile responsive, HTMX swap in browser, status strip countdown accuracy, D-14 placeholder UX) but Plan 25-11's automated tests and Phase 26's TestPhase26MarketScoping now cover the previously-uncovered surfaces server-side.

---

## Gaps Summary

**0 genuine gaps.** Re-verification verdict: **verified**.

---

# Original verification (2026-05-06) — appendix

The original initial-verification artefact recorded `gaps_found` (19/22 decisions verified) at 2026-05-06T01:47:37Z. Plan 25-11 (commits `8f62f1b`, `b33d67c`, `aa594f2`) closed all 4 gaps; Phase 26 plans 04/05/06/07 hardened the multi-tab scoping path beyond the original audit's reach. The original frontmatter and report below are preserved for traceability.

```yaml
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
```

The full original report (decision-by-decision table, key links, human verification list, gaps summary) was the basis for Plan 25-11 task scoping. All items resolved; preserved here only as audit history. The 2026-05-07 verdict at the top of this file supersedes it.

---

_Re-verified: 2026-05-07_
_Verifier: Claude (gsd-verifier)_
_Branch: chore/document-nginx-sudoers @ 5bec4be_
