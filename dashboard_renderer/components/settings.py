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
    # id prefix per UI-SPEC: settings-{market_id}-{field-name}
    pre = f'settings-{market_id_esc}'
    sections.append(
      '<section class="open-form settings-form" '
      '''hx-headers='{"X-Trading-Signals-Auth": "{{WEB_AUTH_SECRET}}"}'>\n'''
      f'  <p class="eyebrow">{html.escape(display, quote=True)} SETTINGS</p>\n'
      '  <h2>Settings</h2>\n'
      '  <p class="subtitle">Per-market trading rules. Changes take effect on the next 08:00 AWST cycle.</p>\n'
      '  <form hx-patch="/markets/settings" hx-ext="json-enc" '
      'hx-swap="none" hx-on::after-request="handleTradesError(event)">\n'
      f'    <input type="hidden" name="market_id" value="{market_id_esc}">\n'
      '    <fieldset>\n'
      '      <legend>Entry rules</legend>\n'
      '      <div class="field">\n'
      f'        <label for="{pre}-adx_gate">ADX gate</label>\n'
      f'        <input id="{pre}-adx_gate" name="adx_gate" type="number" step="0.1" min="0" value="{settings["adx_gate"]}">\n'
      '        <small class="field-help">Skips trade days when trend strength is weak. Default 25.</small>\n'
      '      </div>\n'
      '      <div class="field">\n'
      f'        <label for="{pre}-momentum_votes_required">Momentum votes</label>\n'
      f'        <input id="{pre}-momentum_votes_required" name="momentum_votes_required" type="number" step="1" min="1" max="3" value="{settings["momentum_votes_required"]}">\n'
      '        <small class="field-help">Number of positive momentum windows required to enter. Default 2.</small>\n'
      '      </div>\n'
      '    </fieldset>\n'
      '    <fieldset>\n'
      '      <legend>Risk</legend>\n'
      '      <div class="field">\n'
      f'        <label for="{pre}-trail_mult_long">Long ATR stop multiple</label>\n'
      f'        <input id="{pre}-trail_mult_long" name="trail_mult_long" type="number" step="0.1" min="0.1" value="{settings["trail_mult_long"]}">\n'
      '        <small class="field-help">Trailing-stop distance for long positions. Default 1.5×ATR.</small>\n'
      '      </div>\n'
      '      <div class="field">\n'
      f'        <label for="{pre}-trail_mult_short">Short ATR stop multiple</label>\n'
      f'        <input id="{pre}-trail_mult_short" name="trail_mult_short" type="number" step="0.1" min="0.1" value="{settings["trail_mult_short"]}">\n'
      '        <small class="field-help">Trailing-stop distance for short positions. Default 1.5×ATR.</small>\n'
      '      </div>\n'
      '      <div class="field">\n'
      f'        <label for="{pre}-risk_pct_long">Long risk percent</label>\n'
      f'        <input id="{pre}-risk_pct_long" name="risk_pct_long" type="number" step="0.1" min="0.1" value="{float(settings["risk_pct_long"]) * 100:.2f}">\n'
      '        <small class="field-help">Account risk per long trade. Default 1.0%.</small>\n'
      '      </div>\n'
      '      <div class="field">\n'
      f'        <label for="{pre}-risk_pct_short">Short risk percent</label>\n'
      f'        <input id="{pre}-risk_pct_short" name="risk_pct_short" type="number" step="0.1" min="0.1" value="{float(settings["risk_pct_short"]) * 100:.2f}">\n'
      '        <small class="field-help">Account risk per short trade. Default 1.0%.</small>\n'
      '      </div>\n'
      '      <div class="field">\n'
      f'        <label for="{pre}-contract_cap">Contract cap</label>\n'
      f'        <input id="{pre}-contract_cap" name="contract_cap" type="number" step="1" min="1" value="{html.escape(cap_value, quote=True)}">\n'
      '        <small class="field-help">Maximum contracts per pyramid level. Default 3.</small>\n'
      '      </div>\n'
      '    </fieldset>\n'
      '    <fieldset>\n'
      '      <legend>Direction</legend>\n'
      '      <div class="field">\n'
      f'        <label for="{pre}-direction_mode">Mode</label>\n'
      f'        <select id="{pre}-direction_mode" name="direction_mode">'
      f'<option value="both"{both_selected}>Both</option>'
      f'<option value="long_only"{long_only_selected}>Long only</option>'
      f'<option value="short_only"{short_only_selected}>Short only</option>'
      '</select>\n'
      '        <small class="field-help">Long-only, short-only, or both. Default both.</small>\n'
      '      </div>\n'
      '      <div class="field">\n'
      f'        <label class="checkbox-field" for="{pre}-one_contract_floor"><input id="{pre}-one_contract_floor" name="one_contract_floor" type="checkbox"{checked}> 1-contract floor</label>\n'
      '        <small class="field-help">Skip the trade when sizing would compute &lt; 1 contract. Default off.</small>\n'
      '      </div>\n'
      '    </fieldset>\n'
      '    <button type="submit" class="btn-primary">Save settings</button>\n'
      '  </form>\n'
      '  <div class="error" role="alert" aria-live="polite" hidden></div>\n'
      '</section>\n'
    )
  return ''.join(sections)


def render_add_market_form(state: dict) -> str:
  del state
  # D-19 #6: every <input> must have a paired <label for="..."> (aria-label-for audit)
  return (
    '<section class="open-form" '
    '''hx-headers='{"X-Trading-Signals-Auth": "{{WEB_AUTH_SECRET}}"}'>\n'''
    '  <p class="eyebrow">ADD MARKET</p>\n'
    '  <form hx-post="/markets" hx-ext="json-enc" hx-swap="none" '
    'hx-on::after-request="handleTradesError(event)">\n'
    '    <div class="field"><label for="add-market-form-id">Market ID</label><input id="add-market-form-id" name="market_id" required pattern="[A-Z0-9_]{2,20}"></div>\n'
    '    <div class="field"><label for="add-market-form-name">Display name</label><input id="add-market-form-name" name="display_name" required></div>\n'
    '    <div class="field"><label for="add-market-form-symbol">Symbol</label><input id="add-market-form-symbol" name="symbol" required></div>\n'
    '    <div class="field"><label for="add-market-form-currency">Currency</label><input id="add-market-form-currency" name="currency" value="AUD" required></div>\n'
    '    <div class="field"><label for="add-market-form-multiplier">Multiplier</label><input id="add-market-form-multiplier" name="multiplier" type="number" step="0.0001" min="0.0001" required></div>\n'
    '    <div class="field"><label for="add-market-form-cost">Cost AUD</label><input id="add-market-form-cost" name="cost_aud" type="number" step="0.01" min="0" value="0"></div>\n'
    '    <button type="submit" class="btn-primary">Add Market</button>\n'
    '  </form>\n'
    '  <div class="error" role="alert" aria-live="polite" hidden></div>\n'
    '</section>\n'
  )


def render_market_test_tab(state: dict) -> str:
  import dashboard as d

  display_names = d._display_names(state)
  options = ''.join(
    f'        <option value="{html.escape(key, quote=True)}">{html.escape(display, quote=True)}</option>\n'
    for key, display in display_names.items()
  )

  # D-14: override fields show the first market's inherited Settings as
  # placeholder="<inherited default>" so blanks fall back server-side.
  first_market_id = next(iter(display_names), None)
  settings = d._strategy_settings_for(state, first_market_id) if first_market_id else {}
  adx_placeholder = html.escape(str(settings.get('adx_gate', '')), quote=True)
  votes_placeholder = html.escape(str(settings.get('momentum_votes_required', '')), quote=True)
  risk_long_placeholder = html.escape(
    f"{float(settings['risk_pct_long']) * 100:.2f}" if 'risk_pct_long' in settings else '',
    quote=True,
  )
  risk_short_placeholder = html.escape(
    f"{float(settings['risk_pct_short']) * 100:.2f}" if 'risk_pct_short' in settings else '',
    quote=True,
  )
  atr_long_placeholder = html.escape(str(settings.get('trail_mult_long', '')), quote=True)
  atr_short_placeholder = html.escape(str(settings.get('trail_mult_short', '')), quote=True)
  cap_value = settings.get('contract_cap')
  cap_placeholder = html.escape(str(cap_value) if cap_value is not None else '', quote=True)

  # D-19 #6: every <input>/<select> must have a paired <label for="..."> (aria-label-for audit)
  return (
    '<section class="open-form market-test-form" '
    '''hx-headers='{"X-Trading-Signals-Auth": "{{WEB_AUTH_SECRET}}"}'>\n'''
    '  <p class="eyebrow">MARKET TEST</p>\n'
    '  <form hx-post="/market-test/run" hx-target="#market-test-result" '
    'hx-swap="innerHTML" hx-on::after-request="handleTradesError(event)">\n'
    '    <div class="field"><label for="market-test-market">Market</label><select id="market-test-market" name="market_id" required>\n'
    f'{options}'
    '    </select></div>\n'
    '    <div class="field"><label for="market-test-start-date">Start date</label><input id="market-test-start-date" name="start_date" type="date" required></div>\n'
    '    <div class="field"><label for="market-test-end-date">End date</label><input id="market-test-end-date" name="end_date" type="date" required></div>\n'
    '    <div class="field"><label for="market-test-balance">Initial balance</label><input id="market-test-balance" name="initial_account_aud" type="number" step="100" min="1" value="10000" required></div>\n'
    f'    <div class="field"><label for="market-test-adx">ADX override</label><input id="market-test-adx" name="adx_gate" type="number" step="0.1" min="0" placeholder="{adx_placeholder}"></div>\n'
    f'    <div class="field"><label for="market-test-votes">Votes override</label><input id="market-test-votes" name="momentum_votes_required" type="number" step="1" min="1" max="3" placeholder="{votes_placeholder}"></div>\n'
    f'    <div class="field"><label for="market-test-risk-long">Long risk %</label><input id="market-test-risk-long" name="risk_pct_long" type="number" step="0.1" min="0.1" placeholder="{risk_long_placeholder}"></div>\n'
    f'    <div class="field"><label for="market-test-risk-short">Short risk %</label><input id="market-test-risk-short" name="risk_pct_short" type="number" step="0.1" min="0.1" placeholder="{risk_short_placeholder}"></div>\n'
    f'    <div class="field"><label for="market-test-atr-long">Long ATR multiple</label><input id="market-test-atr-long" name="trail_mult_long" type="number" step="0.1" min="0.1" placeholder="{atr_long_placeholder}"></div>\n'
    f'    <div class="field"><label for="market-test-atr-short">Short ATR multiple</label><input id="market-test-atr-short" name="trail_mult_short" type="number" step="0.1" min="0.1" placeholder="{atr_short_placeholder}"></div>\n'
    f'    <div class="field"><label for="market-test-cap">Contract cap</label><input id="market-test-cap" name="contract_cap" type="number" step="1" min="1" placeholder="{cap_placeholder}"></div>\n'
    '    <button type="submit" class="btn-primary">Run Test</button>\n'
    '  </form>\n'
    '  <div class="error" role="alert" aria-live="polite" hidden></div>\n'
    '  <div id="market-test-result" class="market-test-result"></div>\n'
    '</section>\n'
  )
