'''Settings component implementation.'''

import html


def render_settings_tab(state: dict) -> str:
  import dashboard as d

  sections = []
  for market_id, display in d._display_names(state).items():
    settings = d._strategy_settings_for(state, market_id)
    cap_value = '' if settings.get('contract_cap') is None else str(settings.get('contract_cap'))
    checked = ' checked' if settings.get('one_contract_floor') else ''
    direction_mode = str(settings.get('direction_mode', 'both'))
    both_selected = ' selected' if direction_mode == 'both' else ''
    long_only_selected = ' selected' if direction_mode == 'long_only' else ''
    short_only_selected = ' selected' if direction_mode == 'short_only' else ''
    market_id_esc = html.escape(market_id, quote=True)
    sections.append(
      '<section class="open-form settings-form" '
      '''hx-headers='{"X-Trading-Signals-Auth": "{{WEB_AUTH_SECRET}}"}'>\n'''
      f'  <p class="eyebrow">{html.escape(display, quote=True)} SETTINGS</p>\n'
      '  <form hx-patch="/markets/settings" hx-ext="json-enc" '
      'hx-swap="none" hx-on::after-request="handleTradesError(event)">\n'
      f'    <input type="hidden" name="market_id" value="{market_id_esc}">\n'
      f'    <div class="field"><label>ADX</label><input name="adx_gate" type="number" step="0.1" min="0" value="{settings["adx_gate"]}"></div>\n'
      f'    <div class="field"><label>Momentum votes</label><input name="momentum_votes_required" type="number" step="1" min="1" max="3" value="{settings["momentum_votes_required"]}"></div>\n'
      f'    <div class="field"><label>Long ATR stop</label><input name="trail_mult_long" type="number" step="0.1" min="0.1" value="{settings["trail_mult_long"]}"></div>\n'
      f'    <div class="field"><label>Short ATR stop</label><input name="trail_mult_short" type="number" step="0.1" min="0.1" value="{settings["trail_mult_short"]}"></div>\n'
      f'    <div class="field"><label>Long risk %</label><input name="risk_pct_long" type="number" step="0.1" min="0.1" value="{float(settings["risk_pct_long"]) * 100:.2f}"></div>\n'
      f'    <div class="field"><label>Short risk %</label><input name="risk_pct_short" type="number" step="0.1" min="0.1" value="{float(settings["risk_pct_short"]) * 100:.2f}"></div>\n'
      f'    <div class="field"><label>Contract cap</label><input name="contract_cap" type="number" step="1" min="1" value="{html.escape(cap_value, quote=True)}"></div>\n'
      '    <div class="field"><label>Direction</label>'
      '<select name="direction_mode">'
      f'<option value="both"{both_selected}>Both</option>'
      f'<option value="long_only"{long_only_selected}>Long only</option>'
      f'<option value="short_only"{short_only_selected}>Short only</option>'
      '</select></div>\n'
      f'    <label class="checkbox-field"><input name="one_contract_floor" type="checkbox"{checked}> 1-contract floor</label>\n'
      '    <button type="submit" class="btn-primary">Save Settings</button>\n'
      '  </form>\n'
      '  <div class="error" role="alert" aria-live="polite" hidden></div>\n'
      '</section>\n'
    )
  return ''.join(sections)


def render_add_market_form(state: dict) -> str:
  del state
  return (
    '<section class="open-form" '
    '''hx-headers='{"X-Trading-Signals-Auth": "{{WEB_AUTH_SECRET}}"}'>\n'''
    '  <p class="eyebrow">ADD MARKET</p>\n'
    '  <form hx-post="/markets" hx-ext="json-enc" hx-swap="none" '
    'hx-on::after-request="handleTradesError(event)">\n'
    '    <div class="field"><label>Market ID</label><input name="market_id" required pattern="[A-Z0-9_]{2,20}"></div>\n'
    '    <div class="field"><label>Display name</label><input name="display_name" required></div>\n'
    '    <div class="field"><label>Symbol</label><input name="symbol" required></div>\n'
    '    <div class="field"><label>Currency</label><input name="currency" value="AUD" required></div>\n'
    '    <div class="field"><label>Multiplier</label><input name="multiplier" type="number" step="0.0001" min="0.0001" required></div>\n'
    '    <div class="field"><label>Cost AUD</label><input name="cost_aud" type="number" step="0.01" min="0" value="0"></div>\n'
    '    <button type="submit" class="btn-primary">Add Market</button>\n'
    '  </form>\n'
    '  <div class="error" role="alert" aria-live="polite" hidden></div>\n'
    '</section>\n'
  )


def render_market_test_tab(state: dict) -> str:
  import dashboard as d

  options = ''.join(
    f'        <option value="{html.escape(key, quote=True)}">{html.escape(display, quote=True)}</option>\n'
    for key, display in d._display_names(state).items()
  )
  return (
    '<section class="open-form market-test-form" '
    '''hx-headers='{"X-Trading-Signals-Auth": "{{WEB_AUTH_SECRET}}"}'>\n'''
    '  <p class="eyebrow">MARKET TEST</p>\n'
    '  <form hx-post="/market-test/run" hx-target="#market-test-result" '
    'hx-swap="innerHTML" hx-on::after-request="handleTradesError(event)">\n'
    '    <div class="field"><label>Market</label><select name="market_id" required>\n'
    f'{options}'
    '    </select></div>\n'
    '    <div class="field"><label>Start date</label><input name="start_date" type="date" required></div>\n'
    '    <div class="field"><label>End date</label><input name="end_date" type="date" required></div>\n'
    '    <div class="field"><label>Initial balance</label><input name="initial_account_aud" type="number" step="100" min="1" value="10000" required></div>\n'
    '    <div class="field"><label>ADX override</label><input name="adx_gate" type="number" step="0.1" min="0"></div>\n'
    '    <div class="field"><label>Votes override</label><input name="momentum_votes_required" type="number" step="1" min="1" max="3"></div>\n'
    '    <div class="field"><label>Long risk %</label><input name="risk_pct_long" type="number" step="0.1" min="0.1"></div>\n'
    '    <div class="field"><label>Short risk %</label><input name="risk_pct_short" type="number" step="0.1" min="0.1"></div>\n'
    '    <button type="submit" class="btn-primary">Run Test</button>\n'
    '  </form>\n'
    '  <div class="error" role="alert" aria-live="polite" hidden></div>\n'
    '  <div id="market-test-result" class="market-test-result"></div>\n'
    '</section>\n'
  )
