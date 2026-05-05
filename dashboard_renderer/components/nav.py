'''dashboard_renderer/components/nav.py — Phase 25 D-01/D-03/D-04/D-05/D-18 two-axis nav.

Interface stubs only — full implementation lands in Plan 25-03 (Wave 2).

Security (T-25-02-01): stubs contain no user-controlled output. Plan 25-03
implementation MUST apply html.escape(market_id, quote=True) per RESEARCH
§Pattern 1 and §Security Domain row "XSS via market_id".
'''

import html


def render_function_strip(active_function: str, active_market: str | None) -> str:
  '''Function tab strip — full-page nav (no HTMX swap). Per D-01/D-18.

  Args:
      active_function: one of 'signals' | 'account' | 'settings' | 'market-test'.
      active_market: market_id when on a market-scoped function; None on /account.

  Returns:
      HTML string: <nav role="tablist" aria-label="Function">...</nav>.

  NOTE: Plan 25-02 ships interface stub. Plan 25-03 fills in body per RESEARCH §Pattern 1.
  '''
  return (
    '<nav role="tablist" aria-label="Function" class="tabs tabs-function">\n'
    '  <!-- TODO Plan 25-03: real anchors with aria-current + roving tabindex -->\n'
    '</nav>\n'
  )


def render_market_strip(state: dict, active_market: str, active_function: str) -> str:
  '''Market tab strip — HTMX swap (D-01/D-03).

  Hidden entirely (zero DOM, not display:none) when active_function == 'account' (D-04).

  Args:
      state: full state dict (reads state['markets']).
      active_market: market_id of the highlighted tab.
      active_function: function being viewed; if 'account', return ''.

  Returns:
      HTML string: <nav role="tablist" aria-label="Market">...</nav> OR '' on /account.

  NOTE: Plan 25-02 ships interface stub. Plan 25-03 fills in body per RESEARCH §Pattern 1.
  Plan 25-05 adds the + Add market chip (D-16).
  '''
  if active_function == 'account':
    return ''  # D-04: zero DOM — no market strip on account page
  return (
    '<nav role="tablist" aria-label="Market" class="tabs tabs-market" id="market-tab-strip">\n'
    '  <!-- TODO Plan 25-03: real market anchors with hx-get + hx-push-url -->\n'
    '</nav>\n'
  )


def render_two_axis_nav(state: dict, active_function: str, active_market: str | None) -> str:
  '''Compose function strip + market strip. Top-level entry point for Plan 25-03.

  Returns:
      Concatenated HTML for both strips. Replaces dashboard._render_dashboard_page_nav.
  '''
  return render_function_strip(active_function, active_market) + render_market_strip(
    state, active_market or '', active_function
  )
