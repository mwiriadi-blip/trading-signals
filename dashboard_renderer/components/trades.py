'''Trades component implementation.'''

import html


def render_trades_table(state: dict) -> str:
  import dashboard as d

  trade_log = state.get('trade_log', [])
  slice_newest_first = list(reversed(trade_log[-20:]))
  rendered_rows = []
  for trade in slice_newest_first:
    closed = html.escape(trade.get('exit_date', ''), quote=True)
    instrument_key = trade.get('instrument', '')
    instrument_display = d._display_names(state).get(instrument_key, instrument_key)
    instrument = html.escape(instrument_display, quote=True)
    direction_raw = trade.get('direction', '')
    direction_int = 1 if direction_raw == 'LONG' else -1 if direction_raw == 'SHORT' else 0
    dir_label = html.escape(direction_raw, quote=True)
    # D-19 #5: use semantic class instead of inline style="color:..."
    _DIR_CLASS = {1: 'signal-long', -1: 'signal-short', 0: 'signal-flat'}
    dir_class = _DIR_CLASS.get(direction_int, 'signal-flat')
    entry_price = html.escape(d._fmt_currency(trade.get('entry_price', 0.0)), quote=True)
    exit_price = html.escape(d._fmt_currency(trade.get('exit_price', 0.0)), quote=True)
    contracts = html.escape(str(trade.get('n_contracts', 0)), quote=True)
    exit_reason_raw = trade.get('exit_reason', '')
    reason_display = d._EXIT_REASON_DISPLAY.get(exit_reason_raw, exit_reason_raw)
    reason = html.escape(reason_display, quote=True)
    pnl_cell = d._fmt_pnl_with_colour(trade.get('net_pnl', 0.0))
    rendered_rows.append(
      '      <tr>\n'
      f'        <td data-label="Closed">{closed}</td>\n'
      f'        <td data-label="Instrument">{instrument}</td>\n'
      f'        <td data-label="Direction"><span class="{dir_class}">{dir_label}</span></td>\n'
      f'        <td data-label="Entry → Exit" class="num">{entry_price} → {exit_price}</td>\n'
      f'        <td data-label="Contracts" class="num">{contracts}</td>\n'
      f'        <td data-label="Reason">{reason}</td>\n'
      f'        <td data-label="P&amp;L" class="num">{pnl_cell}</td>\n'
      '      </tr>\n'
    )
  if not rendered_rows:
    rendered_rows = [
      '      <tr>\n'
      '        <td colspan="7" class="empty-state">— No closed trades yet —</td>\n'
      '      </tr>\n'
    ]
  body = ''.join(rendered_rows)
  return (
    '<section aria-labelledby="heading-trades">\n'
    '  <h2 id="heading-trades">Closed Trades</h2>\n'
    '  <p class="subtle">last 20</p>\n'
    '  <div class="table-scroll" tabindex="0" role="region" aria-label="Closed trades (scrollable)">\n'
    '  <table class="data-table">\n'
    '    <caption class="visually-hidden">Most recent 20 closed trades, '
    'newest first</caption>\n'
    '    <thead>\n'
    '      <tr>\n'
    '        <th scope="col">Closed</th>\n'
    '        <th scope="col">Instrument</th>\n'
    '        <th scope="col">Direction</th>\n'
    '        <th scope="col">Entry → Exit</th>\n'
    '        <th scope="col">Contracts</th>\n'
    '        <th scope="col">Reason</th>\n'
    '        <th scope="col">P&amp;L</th>\n'
    '      </tr>\n'
    '    </thead>\n'
    '    <tbody>\n'
    f'{body}'
    '    </tbody>\n'
    '  </table>\n'
    '  </div>\n'
    '</section>\n'
  )
