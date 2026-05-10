'''Phase 28 / DEBT-01 / UAT-17-3: Trace-panel toggle cookie persists across one reload.

Sourced from .planning/milestones/v1.2-phases/17-per-signal-calculation-transparency/
17-VERIFICATION.md UAT-3.

What is being verified together (per 28-CONTEXT.md specifics block):
  1. Cookie WRITE — clicking the trace-panel toggle sets a cookie.
  2. Cookie READ — page.reload() restores the toggle to its post-click state.
  3. No session loss — user remains logged in across the reload.

A spec that proves only (1) misses read regressions; only (2) masks write
regressions. The whole flow is the contract.

Auth assumption (plan 06 may extend conftest if needed):
  This spec assumes the production droplet either (a) does not require
  authentication for the dashboard route, or (b) the operator has
  pre-loaded a session via storage_state. The LOGGED_IN_INDICATOR check
  acts as the no-session-loss assertion in case (b); if (a), the
  indicator selector should be adjusted in plan 06 to a public-page
  marker (e.g. dashboard header element).

Selector contract — the constants below are the implementation contract.
If the production droplet uses different attribute names, update them
here AND record the deviation in 28-03-SUMMARY.md.

Per Phase 17 verification, the cookie is `tsi_trace_open` and the
disclosure is a `<details data-instrument="SPI200">` element whose `open`
attribute reflects toggle state. The selectors below are written tolerant
to either a future `[data-trace-toggle]` / `[data-trace-panel]` rename or
the current `<details data-instrument>` shape — see _toggle_state.
'''
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.uat

DASHBOARD_PATH = os.environ.get('UAT_17_DASHBOARD_PATH', '/markets/SPI200/dashboard')

# Selector contract. Tolerant to both the v1.2 `<details data-instrument>`
# shape and a future `[data-trace-panel]` rename. Plan 06 may tighten.
PANEL_SELECTOR = '[data-trace-panel], details[data-instrument="SPI200"]'
TOGGLE_SELECTOR = '[data-trace-toggle], details[data-instrument="SPI200"] > summary'

# Per Phase 17, the disclosure carries an `open` attribute when expanded.
# Future renames may use `data-collapsed='true'|'false'`. Probe both.
LOGGED_IN_INDICATOR = '[data-user-menu], header, main'


def _toggle_state(page) -> str:
  '''Return a stable string describing the panel's toggle state.

  Returns 'open' / 'closed' regardless of whether the underlying DOM uses
  the HTML `open` attribute on `<details>` or a `data-collapsed` flag.
  '''
  el = page.locator(PANEL_SELECTOR).first
  # `<details open>` — attribute present (string '') means open.
  open_attr = el.get_attribute('open')
  if open_attr is not None:
    return 'open'
  collapsed = el.get_attribute('data-collapsed')
  if collapsed is not None:
    return 'closed' if collapsed == 'true' else 'open'
  return 'closed'


def test_trace_panel_toggle_persists_across_reload(page, base_url):
  page.goto(f'{base_url}{DASHBOARD_PATH}')
  page.wait_for_selector(LOGGED_IN_INDICATOR, timeout=15_000)
  page.wait_for_selector(PANEL_SELECTOR, timeout=15_000)

  initial = _toggle_state(page)

  # ACT: click toggle (cookie WRITE leg).
  page.locator(TOGGLE_SELECTOR).first.click()
  # Wait for state to flip; tolerant to either toggle shape.
  page.wait_for_function(
    '''(args) => {
      const el = document.querySelector(args.sel);
      if (!el) return false;
      const openAttr = el.getAttribute('open');
      const collapsed = el.getAttribute('data-collapsed');
      const now = openAttr !== null
        ? 'open'
        : (collapsed === 'true' ? 'closed' : 'open');
      return now !== args.was;
    }''',
    arg={'sel': PANEL_SELECTOR.split(',')[0].strip(), 'was': initial},
    timeout=5_000,
  )
  post_click = _toggle_state(page)
  assert post_click != initial, (
    f'Toggle click did not flip state: initial={initial} post_click={post_click}'
  )

  # ASSERT cookie WRITE actually happened (not just JS-only state).
  cookies = page.context.cookies()
  toggle_cookie_names = [c['name'] for c in cookies if 'trace' in c['name'].lower()]
  assert toggle_cookie_names, (
    f'No trace-panel cookie written after toggle. '
    f"Cookie names present: {[c['name'] for c in cookies]}"
  )

  # ACT: reload (cookie READ leg).
  page.reload()
  page.wait_for_selector(PANEL_SELECTOR, timeout=15_000)

  # ASSERT 1: visual state preserved across reload.
  post_reload = _toggle_state(page)
  assert post_reload == post_click, (
    f'Toggle state lost across reload: post_click={post_click} post_reload={post_reload}'
  )

  # ASSERT 2: still logged in / no session loss after reload.
  assert page.locator(LOGGED_IN_INDICATOR).first.count() == 1, (
    'LOGGED_IN_INDICATOR missing after reload — session was lost.'
  )
