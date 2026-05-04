'''Signals component implementation.'''

import html


def render_signal_cards(state: dict) -> str:
  import dashboard as d

  signals = state.get('signals', {})
  parts = [
    '<section aria-labelledby="heading-signals">\n',
    '  <h2 id="heading-signals">Signal Status</h2>\n',
    '  <div class="cards-row">\n',
  ]
  for state_key, display in d._display_names(state).items():
    eyebrow = html.escape(display, quote=True)
    sig_entry = signals.get(state_key)
    if sig_entry is None:
      label = html.escape(d._fmt_em_dash(), quote=True)
      colour = html.escape(d._COLOR_FLAT, quote=True)
      signal_as_of_line = 'Signal as of never'
      scalars_line = html.escape(d._fmt_em_dash(), quote=True)
    elif isinstance(sig_entry, int):
      label = html.escape(d._SIGNAL_LABEL.get(sig_entry, d._fmt_em_dash()), quote=True)
      colour = html.escape(d._SIGNAL_COLOUR.get(sig_entry, d._COLOR_FLAT), quote=True)
      signal_as_of_line = 'Signal as of never'
      scalars_line = html.escape(d._fmt_em_dash(), quote=True)
    else:
      signal_int = sig_entry.get('signal', 0)
      label = html.escape(d._SIGNAL_LABEL.get(signal_int, d._fmt_em_dash()), quote=True)
      colour = html.escape(d._SIGNAL_COLOUR.get(signal_int, d._COLOR_FLAT), quote=True)
      signal_as_of = html.escape(sig_entry.get('signal_as_of', 'never'), quote=True)
      signal_as_of_line = f'Signal as of {signal_as_of}'
      scalars = sig_entry.get('last_scalars') or {}
      if scalars:
        adx = f'{scalars.get("adx", 0.0):.1f}'
        mom1 = d._fmt_percent_signed(scalars.get('mom1', 0.0))
        mom3 = d._fmt_percent_signed(scalars.get('mom3', 0.0))
        mom12 = d._fmt_percent_signed(scalars.get('mom12', 0.0))
        rvol = f'{scalars.get("rvol", 0.0):.2f}'
        scalars_line = (
          f'ADX {html.escape(adx, quote=True)}  ·  '
          f'Mom<sub>1</sub> {html.escape(mom1, quote=True)}  ·  '
          f'Mom<sub>3</sub> {html.escape(mom3, quote=True)}  ·  '
          f'Mom<sub>12</sub> {html.escape(mom12, quote=True)}  ·  '
          f'RVol {html.escape(rvol, quote=True)}'
        )
      else:
        scalars_line = html.escape(d._fmt_em_dash(), quote=True)
    parts.append(
      '    <article class="card">\n'
      f'      <p class="eyebrow">{eyebrow}</p>\n'
      f'      <p class="big-label" style="color: {colour}">{label}</p>\n'
      f'      <p class="sub">{signal_as_of_line}</p>\n'
      f'      <p class="scalars">{scalars_line}</p>\n'
      '    </article>\n'
    )
    trace_sig_dict = sig_entry if isinstance(sig_entry, dict) else {}
    trace_placeholder = d._TRACE_OPEN_PLACEHOLDER.get(state_key, '')
    parts.append(d._render_trace_panels(trace_sig_dict, state_key, trace_placeholder))
  parts.append('  </div>\n')
  parts.append('</section>\n')
  return ''.join(parts)
