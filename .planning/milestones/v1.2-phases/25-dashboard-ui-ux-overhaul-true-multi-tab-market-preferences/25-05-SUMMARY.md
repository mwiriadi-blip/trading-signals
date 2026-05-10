---
phase: 25
plan: "05"
subsystem: dashboard-nav
tags: [htmx, market-chip, add-market, hx-trigger, nav, a11y]
dependency_graph:
  requires: [25-03, 25-04]
  provides: [add-market-chip, markets-strip-endpoint]
  affects: [dashboard_renderer/components/nav.py, web/routes/dashboard.py, web/routes/markets.py]
tech_stack:
  added: []
  patterns:
    - HX-Trigger: markets-changed fires strip refresh via hx-trigger=markets-changed from:body
    - <details> chip pattern for inline-expanding mini-form (no modal)
    - GET /markets-strip returns <nav> fragment for HTMX outerHTML swap
key_files:
  created: []
  modified:
    - dashboard_renderer/components/nav.py
    - web/routes/dashboard.py
    - dashboard.py
    - tests/test_dashboard.py
    - tests/test_web_app_factory.py
    - tests/fixtures/dashboard/golden.html
    - tests/fixtures/dashboard/golden_empty.html
    - dashboard-signals.html
    - dashboard-account.html
    - dashboard-settings.html
    - dashboard-market-test.html
decisions:
  - D-16 chip uses <details>/<summary> with inline form — no modal, no redirect
  - chip form fields match MarketRequest Pydantic model (market_id, display_name, symbol, multiplier, cost_aud)
  - GET /markets-strip infers active_function from Referer header, defaults to signals
  - golden_empty.html regenerated from reset_state() not empty_state.json fixture (different markets presence)
metrics:
  duration: ~25 minutes
  completed: 2026-05-05
  tasks_completed: 2
  tasks_total: 2
---

# Phase 25 Plan 05: Add Market Chip Summary

Inline-expanding "+ Add market" chip beside the market tab strip, wired to POST /markets via HTMX with auto-refresh on success.

## What Was Built

**Task 1 — Chip + strip + buried-link removal:**

- Added `render_add_market_chip()` to `dashboard_renderer/components/nav.py` — a `<details class="add-market-chip">` element containing an inline mini-form that posts JSON to `/markets` with `X-Trading-Signals-Auth` header (T-25-05-01 CSRF mitigation)
- Updated `render_market_strip()` to call the chip and to add HTMX attributes: `hx-trigger="markets-changed from:body" hx-get="/markets-strip" hx-swap="outerHTML"` — strip auto-refreshes when the POST /markets success response fires the `markets-changed` event
- Registered `GET /markets-strip` in `web/routes/dashboard.py` — returns the full `<nav>` fragment, reads `selected_market` cookie for active-market fallback, infers active_function from Referer
- Removed `<a class="btn-row btn-modify" href="#settings-tab">Add market</a>` from `dashboard.py:_render_market_selector()` per D-17
- Flipped xfail decorators off `TestPhase25AddMarket::test_market_strip_contains_add_market_chip` and `::test_buried_settings_link_removed`

**Task 2 — HX-Trigger regression test + baseline updates:**

- `POST /markets` already emitted `HX-Trigger: markets-changed` (line 162 of markets.py) — no server-side change needed
- Added `TestPhase25AddMarketHXTrigger` to `test_web_app_factory.py` locking the header behaviour
- Updated `hx-headers` count baseline from 6 to 7 in `test_hx_headers_count_unchanged_from_phase_14_baseline` (chip form is the 7th auth-headered element, consistent with T-25-05-01 discipline)
- Regenerated `golden.html` and `golden_empty.html` (golden_empty required re-rendering from `state_manager.reset_state()` — the regeneration script uses `empty_state.json` which lacks a `markets` dict and produces different output than the test's `reset_state()` call)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Chip form fields didn't match MarketRequest schema**

- **Found during:** Task 1 implementation
- **Issue:** Plan template showed `label` and `contract_size` fields; actual `MarketRequest` Pydantic model requires `display_name`, `symbol`, `multiplier`, `cost_aud`
- **Fix:** Updated chip form inputs to match the actual model fields (market_id, display_name, symbol, multiplier, cost_aud)
- **Files modified:** `dashboard_renderer/components/nav.py`
- **Commit:** 397d3fd

**2. [Rule 1 - Bug] golden_empty.html regeneration used wrong state fixture**

- **Found during:** Task 2 test verification
- **Issue:** The regeneration script (`regenerate_dashboard_golden.py`) renders from `empty_state.json` (no markets dict), but `TestEmptyState` renders from `state_manager.reset_state()` (has SPI200 + AUDUSD). After chip addition, the outputs diverged — the golden was ~643 bytes shorter.
- **Fix:** Re-rendered `golden_empty.html` directly from `reset_state()` output to match what the test produces
- **Files modified:** `tests/fixtures/dashboard/golden_empty.html`
- **Commit:** d76eb7b

**3. [Rule 1 - Bug] hx-headers count baseline needed updating**

- **Found during:** Task 2 test run
- **Issue:** `test_hx_headers_count_unchanged_from_phase_14_baseline` asserted count == 6; chip form adds a 7th `hx-headers` attribute (auth discipline requires it per T-25-05-01)
- **Fix:** Updated assertion from 6 to 7 with updated comment naming the chip form
- **Files modified:** `tests/test_dashboard.py`
- **Commit:** d76eb7b

## Verification Results

```
pytest tests/test_dashboard.py::TestPhase25AddMarket tests/test_web_app_factory.py::TestPhase25AddMarketHXTrigger
4 passed in 0.93s

pytest tests/test_dashboard.py tests/test_web_app_factory.py
237 passed, 19 xfailed in 2.18s
```

All success criteria met:
- "+ Add market" chip rendered beside market tabs (class="add-market-chip")
- Inline-expanding mini-form posts to /markets with auth header + json-enc
- Market strip auto-refreshes on markets-changed event (hx-trigger wired on strip)
- Legacy buried href="#settings-tab" link removed from renderer source
- All TestPhase25AddMarket tests PASS (no xfail remaining)
- TestPhase25AddMarketHXTrigger added and passes

## Known Stubs

None — all wiring is complete. The chip form fields are functional (POST /markets validates and creates markets). The /markets-strip endpoint serves a real nav fragment.

## Threat Flags

None beyond what the plan's threat model covers. The chip form's `hx-headers` auth and Pydantic validation on POST /markets together satisfy T-25-05-01 (Tampering mitigation).

## Self-Check: PASSED

Files exist:
- dashboard_renderer/components/nav.py — FOUND (render_add_market_chip defined)
- web/routes/dashboard.py — FOUND (GET /markets-strip registered)
- tests/test_web_app_factory.py — FOUND (TestPhase25AddMarketHXTrigger added)

Commits exist:
- 397d3fd — FOUND
- d76eb7b — FOUND
