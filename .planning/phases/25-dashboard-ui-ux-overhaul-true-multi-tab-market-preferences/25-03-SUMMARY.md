---
phase: 25
plan: "03"
subsystem: dashboard_renderer
tags: [nav, aria, htmx, two-axis-nav, roving-tabindex, render-context, xfail-flip, wave-2]
dependency_graph:
  requires: [25-01, 25-02]
  provides:
    - "render_two_axis_nav: WAI-ARIA tabs function strip + HTMX market strip"
    - "RenderContext.active_function + RenderContext.active_market fields"
    - "render_dashboard accepts active_function/active_market kwargs + htmx_panel_only flag"
    - "render_panel_only in pages.py for Plan 25-04 HTMX swap path"
    - "<section id=market-panel> HTMX swap target in all rendered pages"
  affects:
    - "25-04 (htmx_panel_only path + market-panel swap target now wired)"
    - "25-05 (two-axis nav rendered; + Add market chip slot prepared with comment)"
tech_stack:
  added: []
  patterns:
    - "WAI-ARIA tabs pattern: role=tablist + role=tab + aria-current=page + roving tabindex"
    - "Two-strip composition: function strip (full-page nav) + market strip (HTMX swap)"
    - "Insertion-order market fallback: _first_market_id() uses next(iter(state['markets']))"
    - "html.escape(market_id, quote=True) on all market_id HTML attribute emission (T-25-03-01)"
    - "_TABS_KEYBOARD_JS: ArrowLeft/Right/Home/End roving tabindex; re-binds on htmx:afterSwap"
key_files:
  created: []
  modified:
    - "dashboard_renderer/components/nav.py — full render_function_strip/render_market_strip/render_two_axis_nav + _first_market_id"
    - "dashboard_renderer/shell.py — _TABS_KEYBOARD_JS added + wired into render_html_shell after _AWST_COUNTDOWN_JS"
    - "dashboard_renderer/context.py — RenderContext.active_function + active_market fields added"
    - "dashboard_renderer/api.py — _build_render_context + render_dashboard extended; htmx_panel_only flag"
    - "dashboard_renderer/pages.py — render_panel_only added for HTMX swap path (Plan 25-04)"
    - "dashboard.py — _render_tabbed_dashboard uses render_two_axis_nav + market-panel wrapper; _render_single_page_dashboard uses render_two_axis_nav + market-panel wrapper; _render_dashboard_page_nav deprecated"
    - "tests/test_dashboard.py — xfail removed from TestPhase25ActiveTab (3) + 6 pre-existing-feature tests; _empty_state positions [] -> {} bug fixed"
    - "tests/fixtures/dashboard/golden.html — regenerated with new nav"
    - "tests/fixtures/dashboard/golden_empty.html — regenerated with new nav"
    - "dashboard-signals.html, dashboard-account.html, dashboard-settings.html, dashboard-market-test.html — regenerated with new nav"
decisions:
  - "_render_tabbed_dashboard extended with render_two_axis_nav rather than left unchanged — required for _render_to_str test helper to pass the three ActiveTab acceptance gates"
  - "market-panel wrapper added to _render_tabbed_dashboard around market-scoped tabs (signals/settings/market-test); account left outside"
  - "render_panel_only returns body-only content (no <section id=market-panel> wrapper) — Plan 25-04 will decide on wrapper strategy for HTMX swap responses"
  - "6 additional xfail decorators removed (not in plan scope) because _empty_state positions bug fix revealed these tests were already passing"
  - "Golden HTML fixtures regenerated from reset_state() + sample_state.json to match new nav output"
metrics:
  duration: ~45min
  completed: "2026-05-05"
  tasks: 2
  files: 15
---

# Phase 25 Plan 03: Two-Axis Nav Summary

WAI-ARIA tabs two-axis nav (function strip × market strip) implemented in `nav.py`; `RenderContext` extended with `active_function`/`active_market`; all render paths wired; roving-tabindex JS helper added; three Phase-25 ActiveTab xfail gates flipped to PASS.

## Performance

- **Duration:** ~45 min
- **Completed:** 2026-05-05
- **Tasks:** 2
- **Files modified:** 15

## Accomplishments

**Task 1 — nav.py implementation + shell.py JS helper:**
- `render_function_strip`: 4 anchors with `aria-current="page"` on active, `tabindex="0"/-1` roving, market-scoped hrefs use `_first_market_id` OR-03 fallback, all labels `html.escape`'d
- `render_market_strip`: zero DOM for `active_function='account'` (D-04); HTMX attrs `hx-get/hx-target/hx-swap/hx-push-url` on each market anchor; all `market_id` values `html.escape(market_id, quote=True)` (T-25-03-01)
- `render_two_axis_nav`: composes both strips
- `_first_market_id`: insertion-order first-market fallback (OR-03; pure `next(iter(markets))`)
- `_TABS_KEYBOARD_JS`: ArrowLeft/Right/Home/End roving tabindex; re-binds on `htmx:afterSwap`; wired into `render_html_shell` after `_AWST_COUNTDOWN_JS`

**Task 2 — Context/API/pages/dashboard.py wiring:**
- `RenderContext`: `active_function: str = 'signals'` + `active_market: str | None = None` fields added
- `_build_render_context`: plumbs new fields through
- `render_dashboard`: keyword-only `active_function`/`active_market`/`htmx_panel_only` params; existing callers unaffected (defaults unchanged)
- `render_panel_only` (pages.py): Plan 25-04 prep — returns raw panel body without shell/nav
- `_render_single_page_dashboard`: uses `render_two_axis_nav`; wraps market-scoped content in `<section id="market-panel" aria-live="polite">` (HTMX swap target)
- `_render_tabbed_dashboard`: prepends `render_two_axis_nav`; wraps market-scoped tabs in `<section id="market-panel">`; account tab lives outside wrapper
- `_render_dashboard_page_nav`: marked deprecated (definition retained for Plan 25-09 cleanup)

**Test gate status:**
- `TestPhase25ActiveTab` (3 tests): xfail decorators removed → all 3 PASS
- 204 passed, 21 xfailed — no regressions

## Task Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | nav.py implementation + roving-tabindex JS | c430898 | dashboard_renderer/components/nav.py, dashboard_renderer/shell.py |
| 2 | Wire active_function/active_market through render stack | e0e11b2 | dashboard.py, dashboard_renderer/api.py, dashboard_renderer/context.py, dashboard_renderer/pages.py, tests/test_dashboard.py, tests/fixtures/dashboard/*.html, dashboard-*.html |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `_empty_state()` positions field was `[]` (list) instead of `{}` (dict)**
- **Found during:** Task 2 verification — `_render_to_str` called `_render_tabbed_dashboard` which called `_render_trailing_stop_guidance` which does `state.get('positions', {}).get(market_id)` — crashes on list
- **Issue:** All 30 Phase-25 xfail tests using `_render_to_str` were crashing with AttributeError before reaching their assertions. They reported XFAIL for the wrong reason (crash, not assertion failure).
- **Fix:** Changed `_empty_state()` positions from `[]` to `{}` in `tests/test_dashboard.py`
- **Cascade:** Once the crash was fixed, 6 xfail tests that tested already-implemented behavior (trace tables, stats-bar, equity chart, hx-post /markets, strategy version, AWST label) became XPASS(strict) = FAILURE. Removed their xfail decorators since the features were already implemented.
- **Files modified:** tests/test_dashboard.py
- **Commits:** e0e11b2

**2. [Rule 1 - Bug] Golden HTML fixtures drift after nav output changed**
- **Found during:** Task 2 verification — `TestEmptyState` and `TestGoldenSnapshot` comparing byte-identical output against stale goldens
- **Fix:** Regenerated both `golden.html` (from sample_state.json) and `golden_empty.html` (from reset_state()) using the existing regen scripts
- **Files modified:** tests/fixtures/dashboard/golden.html, tests/fixtures/dashboard/golden_empty.html
- **Commits:** e0e11b2

**3. [Rule 2 - Missing critical functionality] market-panel wrapper added to `_render_tabbed_dashboard`**
- **Found during:** Task 2 plan verification — `render_dashboard` with `active_function/active_market` produced HTML without `id="market-panel"` because the tabbed dashboard route only called `_render_tabbed_dashboard` (all 4 tabs composite)
- **Fix:** Added `<section id="market-panel" aria-live="polite">` wrapper around market-scoped tabs (signals, settings, market-test) in `_render_tabbed_dashboard`. Account tab placed outside wrapper.
- **Commits:** e0e11b2

### xfail Flips Summary

| Test | Reason flipped | Plan |
|------|---------------|------|
| TestPhase25ActiveTab::test_active_function_tab_has_aria_current | Implementation complete | P25-03 (this plan) |
| TestPhase25ActiveTab::test_function_tab_strip_has_aria_label | Implementation complete | P25-03 (this plan) |
| TestPhase25ActiveTab::test_market_tab_strip_has_aria_label | Implementation complete | P25-03 (this plan) |
| TestPhase25FirstRun::test_last_run_set_renders_trace_tables | Already implemented (unmasked by positions fix) | P25-07 pre-existing |
| TestPhase25StatsBar::test_one_closed_paper_trade_renders_stats_bar | Already implemented | P25-07 pre-existing |
| TestPhase25Equity::test_five_distinct_points_renders_chart | Already implemented | P25-07 pre-existing |
| TestPhase25AddMarket::test_add_market_chip_form_posts_to_markets | hx-post="/markets" already in forms | P25-04 pre-existing |
| TestPhase25StrategyVersion::test_footer_renders_v120_when_state_has_v120 | State-driven version already works | P25-10 pre-existing |
| TestPhase25Countdown::test_status_strip_displays_awst_label | AWST string already in JS countdown | P25-05 pre-existing |

## Threat Surface Scan

T-25-03-01 (XSS via market_id) mitigated per plan: all market_id values pass through `html.escape(market_id, quote=True)` before emission. Grep gate:
```
grep -E 'f"<a[^"]*\{market_id\b' dashboard_renderer/components/nav.py | grep -v escape
```
Returns zero matches — confirmed.

## Threat Flags

None. No new network endpoints, auth paths, or trust boundary surfaces introduced.

## Known Stubs

- `render_panel_only` (pages.py): returns raw body content. Plan 25-04 decides exact wrapper strategy for HTMX swap responses — this stub is intentional.
- `<!-- Phase 25 Plan 05: + Add market chip injected here (D-16) -->`: placeholder comment in `render_market_strip`. Plan 25-05 fills it in.

## Self-Check

Files exist:
- `dashboard_renderer/components/nav.py` — modified ✓
- `dashboard_renderer/shell.py` — modified ✓
- `dashboard_renderer/context.py` — modified ✓
- `dashboard_renderer/api.py` — modified ✓
- `dashboard_renderer/pages.py` — modified ✓
- `dashboard.py` — modified ✓
- `tests/test_dashboard.py` — modified ✓
- `tests/fixtures/dashboard/golden.html` — regenerated ✓
- `tests/fixtures/dashboard/golden_empty.html` — regenerated ✓

Commits exist:
- `c430898` — Task 1 ✓
- `e0e11b2` — Task 2 ✓

Test gate:
- `TestPhase25ActiveTab`: 3/3 PASS ✓
- Full suite: 204 passed, 21 xfailed, 0 failed ✓

## Self-Check: PASSED
