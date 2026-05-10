'''Phase 28 / DEBT-01 / UAT-17-3: Trace-panel toggle cookie persists across one reload.

Sourced from 17-VERIFICATION.md UAT-3.

Verified together (per CONTEXT.md specifics block):
  1. Cookie WRITE — toggling the trace disclosure sets `tsi_trace_open`.
  2. Cookie READ — page.reload() restores the toggle's open/closed state.
  3. No session loss — user remains authenticated across the reload.

Plan-06 live-DOM tightening (2026-05-10): the disclosure is a
`<details class="trace-disclosure" data-instrument="SPI200">` element.
Cookie is `tsi_trace_open=<comma-separated open instruments>` (Path=/,
SameSite=Lax, Max-Age=7776000, Secure). The cookie write happens via
JS click handler on the `<summary>`.
'''
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.uat

DASHBOARD_PATH = os.environ.get('UAT_17_DASHBOARD_PATH', '/')
INSTRUMENT = os.environ.get('UAT_17_INSTRUMENT', 'SPI200')

PANEL_SELECTOR = f'details.trace-disclosure[data-instrument="{INSTRUMENT}"]'
TOGGLE_SELECTOR = f'{PANEL_SELECTOR} > summary.trace-summary'
LOGGED_IN_INDICATOR = 'nav[role="tablist"]'  # tablist only renders for authed sessions


def _is_open(page) -> bool:
  return page.evaluate(
    f"() => document.querySelector('{PANEL_SELECTOR}').open"
  )


def test_trace_panel_toggle_persists_across_reload(page, base_url):
  page.goto(f'{base_url}{DASHBOARD_PATH}')
  page.wait_for_selector(LOGGED_IN_INDICATOR, timeout=15_000)
  page.wait_for_selector(PANEL_SELECTOR, timeout=15_000)

  initial = _is_open(page)

  # ACT: click toggle (cookie WRITE leg).
  page.locator(TOGGLE_SELECTOR).first.click()
  page.wait_for_function(
    f"() => document.querySelector('{PANEL_SELECTOR}').open !== {str(initial).lower()}",
    timeout=5_000,
  )
  post_click = _is_open(page)
  assert post_click != initial, (
    f'Toggle click did not flip state: initial={initial} post_click={post_click}'
  )

  # ASSERT cookie WRITE.
  cookies = page.context.cookies()
  trace_cookies = [c for c in cookies if c['name'] == 'tsi_trace_open']
  assert trace_cookies, (
    f'No tsi_trace_open cookie after toggle. '
    f"Cookie names present: {[c['name'] for c in cookies]}"
  )
  cookie_value = trace_cookies[0]['value']
  if post_click:
    assert INSTRUMENT in cookie_value, (
      f'Cookie value {cookie_value!r} does not record open instrument {INSTRUMENT}'
    )

  # ACT: reload (cookie READ leg).
  page.reload()
  page.wait_for_selector(PANEL_SELECTOR, timeout=15_000)

  # ASSERT 1: visual state preserved across reload.
  post_reload = _is_open(page)
  assert post_reload == post_click, (
    f'Toggle state lost across reload: post_click={post_click} post_reload={post_reload}'
  )

  # ASSERT 2: still logged in / no session loss after reload.
  assert page.locator(LOGGED_IN_INDICATOR).count() >= 1, (
    'LOGGED_IN_INDICATOR missing after reload — session was lost.'
  )
