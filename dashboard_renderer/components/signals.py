'''Signals component implementation.'''

import html


def render_signal_cards(state: dict, *, active_market: str | None = None) -> str:
  import dashboard as d

  # Phase 25 D-09: hide trace tables on first run; show single onboarding card.
  # last_run is None means the daemon has never completed a cycle — no signal
  # data exists yet, so the full card+trace wall of "n/a" panels is replaced
  # by a single oriented card. Once any run completes, full rendering resumes.
  if state.get('last_run') is None:
    return (
      '<section class="onboarding-card" aria-labelledby="onboarding-heading">\n'
      '  <h3 id="onboarding-heading">Awaiting first daily run</h3>\n'
      '  <p>Calculations and equity curve will populate after the first cycle at 08:00 AWST.</p>\n'
      '</section>\n'
    )

  signals = state.get('signals', {})
  parts = [
    '<section aria-labelledby="heading-signals">\n',
    '  <h2 id="heading-signals">Signal Status</h2>\n',
    '  <div class="cards-row">\n',
  ]
  # Phase 26 B1: when active_market is set and present, render only that market.
  display_names = d._display_names(state)
  if active_market and active_market in display_names:
    display_names = {active_market: display_names[active_market]}
  for state_key, display in display_names.items():
    eyebrow = html.escape(display, quote=True)
    sig_entry = signals.get(state_key)
    if sig_entry is None:
      label = html.escape(d._fmt_em_dash(), quote=True)
      signal_int = 0
      signal_as_of_line = 'Signal as of never'
      scalars_line = html.escape(d._fmt_em_dash(), quote=True)
    else:
      # Phase 27 #11 (Plan 27-09): bare-int branch deleted. After v9->v10
      # migration runs at load_state, sig_entry is guaranteed to be a dict
      # (or None — handled above). Phase 26 DEBT.md R5.
      signal_int = sig_entry.get('signal', 0)
      label = html.escape(d._SIGNAL_LABEL.get(signal_int, d._fmt_em_dash()), quote=True)
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
    # D-19 #5: semantic class from signal int — no inline style="color:..."
    # D-19 #3: status-dot glyph beside FLAT/LONG/SHORT label
    # Map signal int → class suffix: 1→long, -1→short, 0→flat (fallback flat)
    _STATE_CLASS = {1: 'long', -1: 'short', 0: 'flat'}
    state_class = _STATE_CLASS.get(signal_int, 'flat')
    parts.append(
      '    <article class="card">\n'
      f'      <p class="eyebrow">{eyebrow}</p>\n'
      f'      <p class="big-label signal-{state_class}">'
      f'<span class="status-dot status-dot--{state_class}" aria-hidden="true"></span>'
      f'{label}'
      f'</p>\n'
      f'      <p class="sub">{signal_as_of_line}</p>\n'
      f'      <p class="scalars">{scalars_line}</p>\n'
      '    </article>\n'
    )
    # Phase 27 WR-08: Plan 27-09 truth #1 + the renderer's TestRendererDefensiveIntBranchRemoved
    # pin guarantee sig_entry reaching this point is None or dict. The
    # `or {}` collapses both None and any unexpected falsy shape to {}.
    trace_sig_dict = sig_entry or {}
    # Backfill missing vote_params from current per-market settings so stale
    # state rows (written before vote_params was persisted) render with the
    # gate the next daily_run will use, not the hardcoded 25.0/0.02 fallback.
    if trace_sig_dict.get('vote_params') is None:
      import signal_engine
      trace_sig_dict = {
        **trace_sig_dict,
        'vote_params': signal_engine.resolve_vote_params(
          d._strategy_settings_for(state, state_key),
        ),
      }
    trace_placeholder = d._TRACE_OPEN_PLACEHOLDER.get(state_key, '')
    parts.append(d._render_trace_panels(trace_sig_dict, state_key, trace_placeholder))
  parts.append('  </div>\n')
  parts.append('</section>\n')
  return ''.join(parts)
