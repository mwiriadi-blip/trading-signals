'''dashboard_renderer/components/nav.py — Phase 25 D-01/D-03/D-04/D-05/D-18 two-axis nav.

Security (T-25-03-01): all market_id values pass through html.escape(value, quote=True)
before emission in href, hx-get, data-market-id attributes.
'''

import html


# Function tab definition: (key, label, is_market_scoped). Order is visible left-to-right.
_FUNCTION_TABS = (
    ('signals', 'Signals', True),
    ('account', 'Account', False),
    ('settings', 'Settings', True),
    ('market-test', 'Market Test', True),
)


def _first_market_id(state: dict) -> str:
    '''Per OR-03: first-market fallback uses dict insertion order (Python 3.7+ guarantees).
    No special-case for SPI200; pure insertion order.
    '''
    markets = state.get('markets', {}) or {}
    if not markets:
        return ''
    return next(iter(markets))


def render_function_strip(active_function: str, active_market: str | None, state: dict | None = None) -> str:
    '''Function tab strip — full-page nav (no HTMX swap). Per D-01/D-18.

    aria-current='page' on the active anchor (D-18). Roving tabindex (active=0, inactive=-1).
    Market-scoped functions link to /markets/{fallback}/<function> when active_market is set or
    when state has markets (use first market in insertion order per OR-03).
    '''
    fallback_market = active_market or (_first_market_id(state) if state else '')
    out = ['<nav role="tablist" aria-label="Function" class="tabs tabs-function">\n']
    for key, label, is_market_scoped in _FUNCTION_TABS:
        if is_market_scoped and fallback_market:
            href = f'/markets/{html.escape(fallback_market, quote=True)}/{key}'
        elif key == 'account':
            href = '/account'
        else:
            href = f'/{key}'
        is_active = (key == active_function)
        tabindex = '0' if is_active else '-1'
        aria_current = 'page' if is_active else 'false'
        cls = 'tab-active' if is_active else 'tab-inactive'
        out.append(
            f'  <a role="tab" tabindex="{tabindex}" aria-current="{aria_current}" '
            f'class="{cls}" href="{href}" data-tab-key="{key}">'
            f'{html.escape(label, quote=True)}</a>\n'
        )
    out.append('</nav>\n')
    return ''.join(out)


def render_add_market_chip() -> str:
    '''Phase 25 D-16: + Add market chip beside the market tab strip.

    <details> wrapping inline mini-form. Posts to existing POST /markets.
    On 2xx, the existing handler emits HX-Trigger: markets-changed which refreshes the strip.
    NOT inside role=tablist — chip is excluded from arrow-key tab traversal per UI-SPEC.
    '''
    return (
        '  <details class="add-market-chip">\n'
        '    <summary aria-label="Add market">+ Add market</summary>\n'
        '    <form\n'
        '        hx-post="/markets"\n'
        '        hx-ext="json-enc"\n'
        '        hx-target="this"\n'
        '        hx-swap="outerHTML"\n'
        '        hx-headers=\'{"X-Trading-Signals-Auth": "{{WEB_AUTH_SECRET}}"}\'\n'
        '        hx-on::after-request="handleTradesError(event)">\n'
        '      <label for="add-market-id">Code</label>\n'
        '      <input id="add-market-id" name="market_id" type="text" pattern="[A-Z0-9_]{2,20}" required>\n'
        '      <label for="add-market-label">Label</label>\n'
        '      <input id="add-market-label" name="display_name" type="text" required>\n'
        '      <label for="add-market-symbol">Symbol</label>\n'
        '      <input id="add-market-symbol" name="symbol" type="text" required>\n'
        '      <label for="add-market-size">Multiplier</label>\n'
        '      <input id="add-market-size" name="multiplier" type="number" step="any" required>\n'
        '      <label for="add-market-cost">Cost (AUD)</label>\n'
        '      <input id="add-market-cost" name="cost_aud" type="number" step="any" value="0" required>\n'
        '      <button type="submit">Add market</button>\n'
        '      <button type="reset" onclick="this.closest(\'details\').open=false;return false;">Cancel</button>\n'
        '    </form>\n'
        '  </details>\n'
    )


def render_market_strip(state: dict, active_market: str, active_function: str) -> str:
    '''Market tab strip — HTMX swap (D-01/D-03).

    Hidden entirely (zero DOM) when active_function == 'account' (D-04).
    Tabs in insertion order in state['markets'] (per OR-03).
    The + Add market chip (D-16) is appended after the tab links.
    The strip listens for markets-changed HX-Trigger to auto-refresh (Plan 25-05).
    '''
    if active_function == 'account':
        return ''  # D-04
    markets = state.get('markets', {}) or {}
    out = [
        '<nav role="tablist" aria-label="Market" class="tabs tabs-market" id="market-tab-strip"'
        ' hx-trigger="markets-changed from:body" hx-get="/markets-strip" hx-swap="outerHTML">\n'
    ]
    for market_id in markets.keys():
        market_esc = html.escape(market_id, quote=True)
        is_active = (market_id == active_market)
        tabindex = '0' if is_active else '-1'
        aria_current = 'page' if is_active else 'false'
        cls = 'tab-active' if is_active else 'tab-inactive'
        out.append(
            f'  <a role="tab" tabindex="{tabindex}" aria-current="{aria_current}" '
            f'class="{cls}" '
            f'href="/markets/{market_esc}/{active_function}" '
            f'hx-get="/markets/{market_esc}/{active_function}" '
            f'hx-target="#market-panel" hx-swap="innerHTML" hx-push-url="true" '
            f'hx-headers=\'{{"X-Trading-Signals-Auth": "{{{{WEB_AUTH_SECRET}}}}"}}\' '
            f'data-market-id="{market_esc}">'
            f'{market_esc}</a>\n'
        )
    out.append(render_add_market_chip())
    out.append('</nav>\n')
    return ''.join(out)


def render_two_axis_nav(state: dict, active_function: str, active_market: str | None) -> str:
    '''Compose function strip + market strip.

    Phase 26 Plan 06 (R4) deleted the legacy single-strip nav helper in
    dashboard.py that this function replaced.
    '''
    return render_function_strip(active_function, active_market, state) + render_market_strip(
        state, active_market or '', active_function
    )
