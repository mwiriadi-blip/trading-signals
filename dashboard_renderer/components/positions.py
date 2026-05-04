'''Positions component implementation.'''

import html


def render_positions_table(state: dict, include_open_form: bool = True) -> str:
  import dashboard as d

  positions = state.get('positions', {})
  tbody_blocks = []
  any_position = False
  for state_key in d._display_names(state):
    pos = positions.get(state_key)
    if pos is None:
      entry_target_html = d._render_entry_target_row(state, state_key)
      if entry_target_html:
        any_position = True
        state_key_esc = html.escape(state_key, quote=True)
        tbody_blocks.append(
          f'    <tbody id="entry-target-{state_key_esc}">\n'
          f'{entry_target_html}'
          f'    </tbody>\n'
        )
      continue
    any_position = True
    state_key_esc = html.escape(state_key, quote=True)
    row_html = d._render_single_position_row(state, state_key, pos)
    sub_row = d._render_calc_row(state, state_key, pos)
    tbody_blocks.append(
      f'    <tbody id="position-group-{state_key_esc}" '
      f'''hx-headers='{{"X-Trading-Signals-Auth": "{{{{WEB_AUTH_SECRET}}}}"}}' '''
      f'hx-trigger="positions-changed from:body" '
      f'hx-get="/?fragment=position-group-{state_key_esc}" '
      f'hx-swap="innerHTML">\n'
      f'{row_html}'
      f'{sub_row}'
      f'    </tbody>\n'
    )
  if not any_position:
    tbody_blocks.append(
      '    <tbody id="positions-empty">\n'
      '      <tr>\n'
      '        <td colspan="9" class="empty-state">— No open positions —</td>\n'
      '      </tr>\n'
      '    </tbody>\n'
    )
  prefix = d._render_open_form(state) if include_open_form else ''
  return (
    prefix
    + '<section aria-labelledby="heading-positions">\n'
    '  <h2 id="heading-positions">Open Positions</h2>\n'
    '  <table class="data-table">\n'
    '    <caption class="visually-hidden">Open positions with current price, '
    'contracts, trail stop, and unrealised P&amp;L</caption>\n'
    '    <thead>\n'
    '      <tr>\n'
    '        <th scope="col">Instrument</th>\n'
    '        <th scope="col">Direction</th>\n'
    '        <th scope="col">Entry</th>\n'
    '        <th scope="col">Current</th>\n'
    '        <th scope="col">Contracts</th>\n'
    '        <th scope="col">Pyramid</th>\n'
    '        <th scope="col">Trail Stop</th>\n'
    '        <th scope="col">Unrealised P&amp;L</th>\n'
    '        <th scope="col">Actions</th>\n'
    '      </tr>\n'
    '    </thead>\n'
    f'{"".join(tbody_blocks)}'
    '  </table>\n'
    '</section>\n'
  )
