'''Phase 28 / DEBT-01 / UAT-26-1: Cold-start smoke on production droplet.

Sourced from .planning/milestones/v1.2-phases/26-phase-25-followup-multi-tab-scoping-fixes/26-UAT.md
Test 1 ("Cold Start Smoke Test").

Acceptance: GET / on the production droplet returns OK, the dashboard renders
(at least one signal panel / main chrome element is present), and there are no
JS console errors on first paint.
'''
from __future__ import annotations

import pytest

pytestmark = pytest.mark.uat


def test_cold_start_root_renders_dashboard(page, base_url):
  console_errors: list[str] = []
  page.on('pageerror', lambda exc: console_errors.append(str(exc)))
  page.on(
    'console',
    lambda msg: console_errors.append(msg.text) if msg.type == 'error' else None,
  )

  response = page.goto(base_url + '/')
  assert response is not None, 'GET / produced no response object'
  assert response.ok, (
    f'GET / failed: status={response.status} url={response.url}'
  )

  # Cold-start contract (plan 06 live-DOM tightening 2026-05-10): the
  # production dashboard renders the market-strip (with [data-market-id]
  # links) and the trace disclosure for at least one instrument. Either
  # is sufficient evidence of a "rendered dashboard" — both are gone if
  # the page is bare/auth-walled/error.
  page.wait_for_selector(
    '[data-market-id], details.trace-disclosure[data-instrument]',
    timeout=15_000,
  )
  body_text = page.locator('body').inner_text()
  assert body_text.strip(), 'Body had no rendered text on cold start'

  # No JS errors on first paint.
  assert not console_errors, (
    f'Console errors on cold start: {console_errors[:3]}'
  )


@pytest.mark.uat
def test_no_pageerror_on_coldstart(page, base_url):
  '''Regression for UAT-26-1 (Phase 28 FAIL): equityChart inline JS brace bug
  caused "missing ) after argument list" on every cold-start. Fixed in Phase 29
  plan 29-02 (section_renderers.py line 219 brace rebalance). This test locks
  that fix by asserting zero pageerror events on the per-market dashboard route
  where the equity chart renders.
  '''
  errors: list[str] = []
  page.on('pageerror', lambda e: errors.append(str(e)))

  # Phase 35+: /markets/* requires cookie auth; header-auth conftest only
  # satisfies root. Use / which renders the full dashboard with same JS.
  response = page.goto(base_url + '/')
  assert response is not None, 'GET / produced no response'
  assert response.ok, (
    f'GET / failed: status={response.status}'
  )

  # Wait for networkidle so any deferred Chart.js init has a chance to fire.
  page.wait_for_load_state('networkidle', timeout=15_000)

  assert errors == [], f'JS pageerror(s): {errors}'
