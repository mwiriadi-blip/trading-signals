'''Phase 28 / DEBT-01 / UAT-26-2..6: Multi-tab market-scoping walkthrough.

Sourced from 26-UAT.md Tests 2..6.

Plan-06 live-DOM tightening (2026-05-10): the active-market identifier
is exposed via the market-strip — a `<a>` element carrying both
`data-market-id="SPI200"` and `aria-current="page"` when its market is
the active scope. Other markets render as `aria-current="false"`. There
is no top-level `[data-active-market]` attribute.

UAT-2/3/4 are parametrized over (SPI200, AUDUSD); plan 06 aggregates
each parametrize-pair into a single evidence row in 28-VERIFICATION.md.
'''
from __future__ import annotations

import pytest

pytestmark = pytest.mark.uat

MARKETS = ('SPI200', 'AUDUSD')


def _active_market(page) -> str | None:
  '''Return the data-market-id of the market-strip link with aria-current=page.'''
  el = page.locator('[data-market-id][aria-current="page"]').first
  if el.count() == 0:
    return None
  return el.get_attribute('data-market-id')


@pytest.mark.parametrize('market', MARKETS)
def test_uat2_signals_tab_scopes_to_market(page, base_url, market):
  '''UAT-2: /markets/{M}/signals scopes the active market to M.'''
  page.goto(f'{base_url}/markets/{market}/signals')
  page.wait_for_selector('[data-market-id][aria-current="page"]', timeout=15_000)

  active = _active_market(page)
  assert active == market, (
    f'Signals tab scoping mismatch: URL={market} active={active}. '
    f'Suspected layer: web/routes/markets.py active-market middleware.'
  )


@pytest.mark.parametrize('market', MARKETS)
def test_uat3_settings_tab_scopes_to_market(page, base_url, market):
  '''UAT-3: /markets/{M}/settings scopes the active market to M.'''
  page.goto(f'{base_url}/markets/{market}/settings')
  page.wait_for_selector('[data-market-id][aria-current="page"]', timeout=15_000)

  active = _active_market(page)
  assert active == market, (
    f'Settings tab scoping mismatch: URL={market} active={active}. '
    f'Suspected layer: web/routes/markets.py active-market middleware.'
  )


@pytest.mark.parametrize('market', MARKETS)
def test_uat4_market_test_tab_scopes_to_market(page, base_url, market):
  '''UAT-4: /markets/{M}/market-test scopes the active market to M.'''
  page.goto(f'{base_url}/markets/{market}/market-test')
  page.wait_for_selector('[data-market-id][aria-current="page"]', timeout=15_000)

  active = _active_market(page)
  assert active == market, (
    f'Market-test tab scoping mismatch: URL={market} active={active}. '
    f'Suspected layer: web/routes/markets.py active-market middleware.'
  )


def test_uat5_panel_swap_patch_does_not_401(page, base_url):
  '''UAT-5: PATCH from a panel-swapped form returns non-401.

  We assert AUTH semantics (no 401), not VALIDATION semantics — a 4xx
  validation rejection of an empty body is fine.
  '''
  page.goto(f'{base_url}/markets/SPI200/settings')
  page.wait_for_selector('[hx-patch]', timeout=15_000)

  hx_patch_attr = page.locator('[hx-patch]').first
  endpoint = hx_patch_attr.get_attribute('hx-patch')
  assert endpoint, 'hx-patch attribute empty'
  target = endpoint if endpoint.startswith('http') else base_url + endpoint

  # context.request bypasses page.route handlers, so attach the header
  # explicitly. Inherits cookies from the browser context.
  import os
  from pathlib import Path
  secret = os.environ.get('WEB_AUTH_SECRET')
  if not secret:
    env_path = Path(__file__).resolve().parents[2] / '.env.uat'
    if env_path.is_file():
      for line in env_path.read_text().splitlines():
        s = line.strip()
        if s.startswith('WEB_AUTH_SECRET=') and '=' in s:
          secret = s.split('=', 1)[1].strip().strip('"').strip("'")
          break
  headers = {'X-Trading-Signals-Auth': secret} if secret else {}

  api = page.context.request
  response = api.patch(target, data={}, headers=headers)
  assert response.status != 401, (
    f'PATCH {target} returned 401 (auth failure on panel-swapped form). '
    f'Status was {response.status}. Suspected layer: cookie scope after htmx swap.'
  )


def test_uat6_header_session_widget_renders(page, base_url):
  '''UAT-6: header session widget renders without literal placeholder leaks.'''
  page.goto(base_url + '/')
  page.wait_for_selector('header', timeout=15_000)

  header = page.locator('header').first
  assert header.count() == 1, 'No <header> element found'
  text = header.inner_text().strip()
  assert text, 'Header rendered empty'

  forbidden = ('{{', '}}', 'Undefined', 'WEB_AUTH_SECRET')
  for token in forbidden:
    assert token not in text, (
      f'Header contains literal placeholder {token!r}: {text!r}'
    )
