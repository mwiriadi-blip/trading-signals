'''Trades component implementation.'''

import html

from dashboard_renderer.formatters import (
  _EXIT_REASON_DISPLAY,
  _display_names,
  _fmt_currency,
  _fmt_pnl_with_colour,
)


def render_trades_table(state: dict) -> str:
  trade_log = state.get('trade_log', [])
  is_admin = state.get('_account_include_open_form', False)
  # D-06: render last 200 only; full state preserved; admin endpoint serves full log
  slice_newest_first = list(reversed(trade_log[-200:]))
  n_total = len(trade_log)
  rendered_rows = []
  for display_i, trade in enumerate(slice_newest_first):
    actual_index = n_total - 1 - display_i
    closed = html.escape(trade.get('exit_date', ''), quote=True)
    instrument_key = trade.get('instrument', '')
    instrument_display = _display_names(state).get(instrument_key, instrument_key)
    instrument = html.escape(instrument_display, quote=True)
    direction_raw = trade.get('direction', '')
    direction_int = 1 if direction_raw == 'LONG' else -1 if direction_raw == 'SHORT' else 0
    dir_label = html.escape(direction_raw, quote=True)
    # D-19 #5: use semantic class instead of inline style="color:..."
    _DIR_CLASS = {1: 'signal-long', -1: 'signal-short', 0: 'signal-flat'}
    dir_class = _DIR_CLASS.get(direction_int, 'signal-flat')
    entry_price = html.escape(_fmt_currency(trade.get('entry_price', 0.0)), quote=True)
    exit_price = html.escape(_fmt_currency(trade.get('exit_price', 0.0)), quote=True)
    contracts = html.escape(str(trade.get('n_contracts', 0)), quote=True)
    exit_reason_raw = trade.get('exit_reason', '')
    reason_display = _EXIT_REASON_DISPLAY.get(exit_reason_raw, exit_reason_raw)
    reason = html.escape(reason_display, quote=True)
    pnl_cell = _fmt_pnl_with_colour(trade.get('net_pnl', 0.0))
    delete_cell = (
      f'        <td><button hx-delete="/trades/{actual_index}"\n'
      f'                    hx-confirm="Delete this trade? This cannot be undone."\n'
      f'                    class="btn-row btn-close">Delete</button></td>\n'
      if is_admin else ''
    )
    rendered_rows.append(
      '      <tr>\n'
      f'        <td data-label="Closed">{closed}</td>\n'
      f'        <td data-label="Instrument">{instrument}</td>\n'
      f'        <td data-label="Direction"><span class="{dir_class}">{dir_label}</span></td>\n'
      f'        <td data-label="Entry → Exit" class="num">{entry_price} → {exit_price}</td>\n'
      f'        <td data-label="Contracts" class="num">{contracts}</td>\n'
      f'        <td data-label="Reason">{reason}</td>\n'
      f'        <td data-label="P&amp;L" class="num">{pnl_cell}</td>\n'
      f'{delete_cell}'
      '      </tr>\n'
    )
  colspan = '8' if is_admin else '7'
  if not rendered_rows:
    rendered_rows = [
      '      <tr>\n'
      f'        <td colspan="{colspan}" class="empty-state">— No closed trades yet —</td>\n'
      '      </tr>\n'
    ]
  body = ''.join(rendered_rows)
  actions_th = '        <th scope="col">Actions</th>\n' if is_admin else ''
  return (
    '<section aria-labelledby="heading-trades">\n'
    '  <h2 id="heading-trades">Closed Trades</h2>\n'
    '  <p class="subtle">last 200</p>\n'
    '  <div class="table-scroll" tabindex="0" role="region" aria-label="Closed trades (scrollable)">\n'
    '  <table class="data-table">\n'
    '    <caption class="visually-hidden">Most recent 200 closed trades, '
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
    f'{actions_th}'
    '      </tr>\n'
    '    </thead>\n'
    '    <tbody>\n'
    f'{body}'
    '    </tbody>\n'
    '  </table>\n'
    '  </div>\n'
    '</section>\n'
  )
