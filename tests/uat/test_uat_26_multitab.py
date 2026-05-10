'''Phase 28 / DEBT-01 / UAT-26-2..6: Multi-tab market-scoping walkthrough.

Sourced from .planning/milestones/v1.2-phases/26-phase-25-followup-multi-tab-scoping-fixes/26-UAT.md
Tests 2..6.

Per CONTEXT D-11 default lean, each UAT-N is a distinct test function so each
gets its own auditable PASS/FAIL row in 28-VERIFICATION.md. UAT-2/3/4 are
parametrized over the two production markets (SPI200, AUDUSD) for symmetry —
plan 06 aggregates each parametrize-pair into a single evidence row.
'''
from __future__ import annotations

import pytest

pytestmark = pytest.mark.uat

# Production markets per 26-UAT.md (Test 3 explicitly references SPI200).
MARKETS = ('SPI200', 'AUDUSD')


def _market_identifier_in_dom(page) -> str | None:
  '''Return the market id the page believes it's scoped to, or None.

  Convention: pages render the active market via [data-active-market] on
  the page chrome. Plan 06 may refine if production uses a different
  attribute name; failing tests will reveal that.
  '''
  attr = page.locator('[data-active-market]').first
  if attr.count():
    return attr.get_attribute('data-active-market')
  return None


@pytest.mark.parametrize('market', MARKETS)
def test_uat2_signals_tab_scopes_to_market(page, base_url, market):
  '''UAT-2: /markets/{M}/signals shows only market M's signal data.'''
  page.goto(f'{base_url}/markets/{market}/signals')
  page.wait_for_selector('body', timeout=15_000)

  in_dom = _market_identifier_in_dom(page)
  assert in_dom == market, (
    f'Signals tab scoping mismatch: URL={market} DOM={in_dom}. '
    f'Suspected layer: web/routes/dashboard.py active-market middleware.'
  )

  # Negative scope: the OTHER market's identifier must not appear in the
  # rendered signal panel.
  other = next(m for m in MARKETS if m != market)
  panel = page.locator('[data-signal-panel], #signal-panel').first
  if panel.count() == 0:
    pytest.skip('No signal panel selector matched — plan 06 to refine.')
  signals_html = panel.inner_html()
  assert other not in signals_html, (
    f'Cross-market leak: {other} found in {market} signal panel.'
  )


@pytest.mark.parametrize('market', MARKETS)
def test_uat3_settings_tab_scopes_to_market(page, base_url, market):
  '''UAT-3: /markets/{M}/settings shows only market M's settings form.'''
  page.goto(f'{base_url}/markets/{market}/settings')
  page.wait_for_selector('form, [data-settings-form]', timeout=15_000)

  in_dom = _market_identifier_in_dom(page)
  assert in_dom == market, (
    f'Settings tab scoping mismatch: URL={market} DOM={in_dom}. '
    f'Suspected layer: web/routes/dashboard.py active-market middleware.'
  )


@pytest.mark.parametrize('market', MARKETS)
def test_uat4_market_test_tab_scopes_to_market(page, base_url, market):
  '''UAT-4: /markets/{M}/market-test scopes to market M.'''
  page.goto(f'{base_url}/markets/{market}/market-test')
  page.wait_for_selector('body', timeout=15_000)

  in_dom = _market_identifier_in_dom(page)
  assert in_dom == market, (
    f'Market-test tab scoping mismatch: URL={market} DOM={in_dom}. '
    f'Suspected layer: web/routes/dashboard.py active-market middleware.'
  )


def test_uat5_panel_swap_patch_does_not_401(page, base_url):
  '''UAT-5: PATCH from a panel-swapped form returns non-401.

  Read-only contract: navigate to settings, locate a hx-patch endpoint on
  the form, then issue an empty-body PATCH via the same browser context
  (same cookies). We assert the response is NOT 401 — i.e. the cookie /
  auth-secret survives the htmx swap. A 4xx-validation result is fine
  (the empty body is rejected by validation, not by auth).
  '''
  page.goto(f'{base_url}/markets/SPI200/settings')
  page.wait_for_selector('form, [data-settings-form]', timeout=15_000)

  hx_patch_attr = page.locator('[hx-patch]').first
  if hx_patch_attr.count() == 0:
    pytest.skip('No hx-patch endpoint on settings page — UAT-5 not applicable.')
  endpoint = hx_patch_attr.get_attribute('hx-patch')
  assert endpoint, 'hx-patch attribute empty'
  target = endpoint if endpoint.startswith('http') else base_url + endpoint

  # Same browser context => same cookies. Empty PATCH body — we are
  # asserting AUTH semantics (no 401), not VALIDATION semantics.
  api = page.context.request
  response = api.patch(target, data={})
  assert response.status != 401, (
    f'PATCH {target} returned 401 (auth failure on panel-swapped form). '
    f'Status was {response.status}. Suspected layer: cookie scope after htmx swap.'
  )


def test_uat6_header_session_widget_renders(page, base_url):
  '''UAT-6: header session widget renders user identity correctly.

  Acceptance: widget exists and is non-empty. We do NOT assert a specific
  username because the production droplet may render either authenticated
  identity OR a sign-in note depending on session state — both are valid
  per 26-UAT.md Test 6 ("signout button OR session note, never literal
  placeholders").
  '''
  page.goto(base_url + '/')
  page.wait_for_selector('[data-user-menu], header', timeout=15_000)

  widget = page.locator('[data-user-menu]').first
  if widget.count() == 0:
    # Fallback: a header element must at least exist with content.
    header = page.locator('header').first
    assert header.count() == 1, 'Neither [data-user-menu] nor header found'
    text = header.inner_text().strip()
  else:
    text = widget.inner_text().strip()
  assert text, 'Header session widget rendered empty'

  # Negative: literal placeholder substrings must not survive into the DOM.
  forbidden = ('{{', '}}', 'Undefined', 'WEB_AUTH_SECRET')
  for token in forbidden:
    assert token not in text, (
      f'Header widget contains literal placeholder {token!r}: {text!r}'
    )
