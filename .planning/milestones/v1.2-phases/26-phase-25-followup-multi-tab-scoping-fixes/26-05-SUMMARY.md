---
phase: 26
plan: 05
type: execute
status: complete
completed: 2026-05-07
files_modified:
  - dashboard.py
  - dashboard_renderer/components/signals.py
  - dashboard_renderer/components/settings.py
  - dashboard_renderer/components/header.py
  - dashboard_renderer/api.py
  - tests/test_web_app_factory.py
  - tests/test_dashboard.py
  - tests/fixtures/dashboard/golden.html
  - tests/fixtures/dashboard/golden_empty.html
  - .gitignore
phase26_market_scoping_pass_count: 4
---

# Phase 26 Plan 05: active-market scoping (B1 + R3) Summary

## One-liner

Threaded `ctx.active_market` from `_render_page_body` through three per-market
renderers (signal cards, settings tab, market-test tab) and forwarded the
kwarg through `render_dashboard_page` → `_build_render_context` (also fixing
the missing `active_function=page` per R3); on-disk siblings now pass
`active_market=_first_market_id(state)` explicitly.

## Kwargs added per file

| File | Function | New keyword-only kwarg | Default |
|---|---|---|---|
| `dashboard_renderer/components/signals.py` | `render_signal_cards` | `active_market: str \| None` | `None` |
| `dashboard_renderer/components/settings.py` | `render_settings_tab` | `active_market: str \| None` | `None` |
| `dashboard_renderer/components/settings.py` | `render_market_test_tab` | `active_market: str \| None` | `None` |
| `dashboard.py` | `_render_signal_cards` (wrapper) | `active_market: str \| None` | `None` |
| `dashboard.py` | `_render_settings_tab` (wrapper) | `active_market: str \| None` | `None` |
| `dashboard.py` | `_render_market_test_tab` (wrapper) | `active_market: str \| None` | `None` |
| `dashboard_renderer/api.py` | `render_dashboard_page` | `active_market: str \| None` | `None` |

`render_dashboard_page` also now forwards `active_function=page` to
`_build_render_context` (was previously dropped — R3 fix).

`render_dashboard` sibling-regen loop builds a fresh `RenderContext` per
sibling page with `active_function=sibling_page` and
`active_market=_first_market_id(state) or None` so the on-disk fallback is
explicit rather than implicit.

## Filter shape

Inside each leaf renderer, before the per-market loop:

```python
display_names = d._display_names(state)
if active_market and active_market in display_names:
    display_names = {active_market: display_names[active_market]}
```

For `render_market_test_tab`, the inherited-defaults lookup prefers
`active_market` when set+present, otherwise falls back to first-market via
`next(iter(display_names), None)` — same behaviour as before for unscoped
callers.

## Verification

### TestPhase26MarketScoping (acceptance gate for B1)

```
$ pytest tests/test_web_app_factory.py::TestPhase26MarketScoping -v
tests/test_web_app_factory.py::TestPhase26MarketScoping::test_spi200_settings_eyebrow_only_active_market PASSED
tests/test_web_app_factory.py::TestPhase26MarketScoping::test_audusd_settings_eyebrow_only_active_market PASSED
tests/test_web_app_factory.py::TestPhase26MarketScoping::test_esm_market_test_eyebrow_only_active_market PASSED
tests/test_web_app_factory.py::TestPhase26MarketScoping::test_spi200_signals_card_only_active_market PASSED

============================== 4 passed in 1.09s ===============================
```

**Pass count: 4 / 4.**

### Regression suites

```
$ pytest tests/test_dashboard.py -x
============================= 237 passed in 0.60s ==============================

$ pytest -x   # full suite
================= 1788 passed, 6 xfailed in 111.10s (0:01:51) ==================
```

Pre-Plan-26-05 baseline: `1784 passed, 10 xfailed`. Post: `1788 passed,
6 xfailed`. Delta: 4 xfails flipped green (TestPhase26MarketScoping), no
regressions. Remaining 6 xfails are scoped to Plan 26-04 (B2/B3/PATCH-survives).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] Hardcoded multi-market subtitle leaked other markets' display names**
- **Found during:** Task 2 verification — `test_esm_market_test_eyebrow_only_active_market` failed because `'SPI 200' in resp.text` (true via the `<p class="subtitle">SPI 200 &amp; AUD/USD mechanical system</p>` literal in `header.py:62`).
- **Issue:** Phase-pre-25 hardcoded subtitle violated B1's per-market-scoping contract on `/markets/{M}/{fn}` pages.
- **Fix:** Replaced literal "SPI 200 & AUD/USD mechanical system" with market-agnostic "Mechanical multi-market trading system" in `dashboard_renderer/components/header.py`. Updated `tests/test_dashboard.py::test_header_contains_title_and_awst_timestamp` to match. Regenerated `tests/fixtures/dashboard/golden.html` and `golden_empty.html`.
- **Files modified:** `dashboard_renderer/components/header.py`, `tests/test_dashboard.py`, `tests/fixtures/dashboard/golden.html`, `tests/fixtures/dashboard/golden_empty.html`
- **Commits:** `7bcd3db`

**2. [Rule 3 — Blocking] Worktree branched from main, missing Plan 26-01/02/03 prereq commits**
- **Found during:** Task 0 — TestPhase26MarketScoping did not exist in worktree.
- **Issue:** Worktree was created from `main` (HEAD `9874b3c`) before `chore/document-nginx-sudoers` (HEAD `7b318c3`) had Plan 26-01/02/03 committed; the prereq xfail tests Task 3 needs to un-xfail were absent.
- **Fix:** `git reset --hard chore/document-nginx-sudoers` to bring the executing-branch tip into the worktree. Non-destructive of any worktree-local commits (none yet) and matches the orchestrator's intended branch base.
- **Files modified:** none (working tree unchanged after reset).
- **Commits:** none.

**3. [Rule 2 — Auto-add] state.json.corrupt.* runtime artefact untracked**
- **Found during:** Pre-task-3 status check — pytest run produced `state.json.corrupt.20260507T085553_692126Z`.
- **Issue:** Test runs that detect corrupt state rotate the file with a UTC-timestamp suffix; the existing `.gitignore` only ignored the bare `state.json` name, leaking timestamped artefacts into `git status` output.
- **Fix:** Added `state.json.corrupt.*` to `.gitignore`.
- **Files modified:** `.gitignore`
- **Commits:** included in final metadata commit.

## Authentication gates

None encountered.

## Manual smoke verdict

Not yet run on droplet — Plan 26-05 is renderer-only; `_serve_market_scoped_page`
already plumbs `active_market=market_id` to `render_dashboard_as_str`
(`web/routes/dashboard.py:264, 274`) so the existing route layer is unchanged.
Operator smoke after Plan 26-04 lands (which fixes the placeholder leak that
otherwise breaks the page):

- `/markets/SPI200/settings` → only SPI 200 fieldset.
- `/markets/AUDUSD/signals` → only AUDUSD signal card.
- `/markets/ESM/market-test` → only ES Mini override form.

## Threat Flags

None — no new network surface, auth path, or trust-boundary schema changes.

## Self-Check: PASSED

- [x] `dashboard.py` modified — `_render_page_body` forwards `ctx.active_market`; wrappers accept kwarg.
- [x] `dashboard_renderer/components/signals.py` modified — `render_signal_cards` accepts `active_market`.
- [x] `dashboard_renderer/components/settings.py` modified — both `render_settings_tab` and `render_market_test_tab` accept `active_market`.
- [x] `dashboard_renderer/api.py` modified — `render_dashboard_page` adds kwarg + `active_function=page`; sibling regen passes `_first_market_id(state)`.
- [x] `tests/test_web_app_factory.py` xfail decorators removed from 4 TestPhase26MarketScoping tests.
- [x] All commits exist: `f4c6a7a`, `7bcd3db`, `1f56726`.
- [x] `pytest tests/test_web_app_factory.py::TestPhase26MarketScoping -v` → 4 passed.
- [x] Full suite: 1788 passed, 6 xfailed.
