'''Signals component implementation.'''

import html
import math


def _next_triggers(scalars: dict, vote_params: dict, signal_int: int) -> list[str]:
  '''Ordered list of conditions to flip from FLAT to LONG/SHORT.

  Priority: ADX gate first (kill-switch), then momentum vote count.
  Returns empty list when already in a directional state, when scalars are
  missing, or when no conditions remain.
  '''
  if signal_int != 0:
    return []
  if not scalars:
    return []
  adx_gate = float(vote_params.get('adx_gate', 25.0))
  mom_threshold = float(vote_params.get('momentum_threshold', 0.02))
  votes_required = int(vote_params.get('momentum_votes_required', 2))
  direction_mode = str(vote_params.get('direction_mode', 'both'))

  adx = float(scalars.get('adx', float('nan')))
  moms = [
    float(scalars.get('mom1', float('nan'))),
    float(scalars.get('mom3', float('nan'))),
    float(scalars.get('mom12', float('nan'))),
  ]
  valid_moms = [m for m in moms if not math.isnan(m)]
  votes_up = sum(1 for m in valid_moms if m > mom_threshold)
  votes_dn = sum(1 for m in valid_moms if m < -mom_threshold)

  def _ladder(direction: str) -> list[str]:
    steps: list[str] = []
    if math.isnan(adx):
      steps.append('ADX missing')
    elif adx < adx_gate:
      gap = adx_gate - adx
      steps.append(f'ADX ≥ {adx_gate:g} (now {adx:.1f}, +{gap:.1f})')
    have = votes_up if direction == 'LONG' else votes_dn
    need = votes_required - have
    if need > 0:
      sign = '+' if direction == 'LONG' else '−'
      pct = mom_threshold * 100
      noun = 'vote' if need == 1 else 'votes'
      steps.append(f'{need} more Mom {sign}{pct:.1f}% {noun}')
    return steps

  candidates: list[tuple[str, list[str]]] = []
  if direction_mode in ('both', 'long_only'):
    candidates.append(('LONG', _ladder('LONG')))
  if direction_mode in ('both', 'short_only'):
    candidates.append(('SHORT', _ladder('SHORT')))

  candidates = [(d, steps) for d, steps in candidates if steps]
  if not candidates:
    return []
  candidates.sort(key=lambda c: len(c[1]))
  direction, steps = candidates[0]
  numbered = [f'{i + 1}) {s}' for i, s in enumerate(steps)]
  return [f'→ {direction}: ' + '  '.join(numbered)]


def _signal_card_stop(
  state: dict,
  state_key: str,
  scalars: dict,
  signal_int: int,
  settings: dict,
  vote_params: dict,
) -> str | None:
  '''Trailing stop line for the Signal Status card.

  - Open position (any direction): real stop via _compute_trail_stop_display.
  - No position: hypothetical stop using today's ATR + last_close, for the
    side the votes lean toward (or signal_int direction).
  - Returns None when no meaningful stop can be computed.
  '''
  import dashboard as d
  import system_params as sp

  positions = state.get('positions') or {}
  pos = positions.get(state_key)
  if pos:
    stop_val = d._compute_trail_stop_display(pos, settings=settings)
    if stop_val is not None and not math.isnan(stop_val):
      direction = pos.get('direction', '')
      manual = pos.get('manual_stop') is not None
      tag = 'manual' if manual else f'trail · {direction}'
      return f'Stop {stop_val:.4f} <span class="stop-tag">({tag})</span>'

  if not scalars:
    return None
  atr = float(scalars.get('atr', float('nan')))
  sigs = state.get('signals') or {}
  sig_entry = sigs.get(state_key) or {}
  last_close = sig_entry.get('last_close')
  if last_close is None or math.isnan(atr) or atr <= 0:
    return None
  last_close = float(last_close)

  if signal_int == 1:
    direction = 'LONG'
  elif signal_int == -1:
    direction = 'SHORT'
  else:
    mom_threshold = float(vote_params.get('momentum_threshold', 0.02))
    moms = [
      float(scalars.get('mom1', float('nan'))),
      float(scalars.get('mom3', float('nan'))),
      float(scalars.get('mom12', float('nan'))),
    ]
    up = sum(1 for m in moms if not math.isnan(m) and m > mom_threshold)
    dn = sum(1 for m in moms if not math.isnan(m) and m < -mom_threshold)
    direction_mode = str(vote_params.get('direction_mode', 'both'))
    if up > dn and direction_mode != 'short_only':
      direction = 'LONG'
    elif dn > up and direction_mode != 'long_only':
      direction = 'SHORT'
    else:
      return None

  if direction == 'LONG':
    trail_mult = float(settings.get('trail_mult_long', sp.TRAIL_MULT_LONG))
    stop_val = last_close - trail_mult * atr
  else:
    trail_mult = float(settings.get('trail_mult_short', sp.TRAIL_MULT_SHORT))
    stop_val = last_close + trail_mult * atr
  return f'Hypothetical stop {stop_val:.4f} <span class="stop-tag">(if {direction} @ {last_close:.4f})</span>'


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

    # Trigger ladder + trailing stop lines.
    triggers_html = ''
    stop_html = ''
    if sig_entry is not None:
      import signal_engine
      vp_card = sig_entry.get('vote_params') or signal_engine.resolve_vote_params(
        d._strategy_settings_for(state, state_key),
      )
      scalars_for_card = sig_entry.get('last_scalars') or {}
      settings_for_card = d._strategy_settings_for(state, state_key)
      triggers = _next_triggers(scalars_for_card, vp_card, signal_int)
      if triggers:
        triggers_html = (
          f'      <p class="triggers">Triggers '
          f'{html.escape(triggers[0], quote=True)}</p>\n'
        )
      stop_line = _signal_card_stop(
        state, state_key, scalars_for_card, signal_int,
        settings_for_card, vp_card,
      )
      if stop_line:
        stop_html = f'      <p class="stop-line">{stop_line}</p>\n'

    parts.append(
      '    <article class="card">\n'
      f'      <p class="eyebrow">{eyebrow}</p>\n'
      f'      <p class="big-label signal-{state_class}">'
      f'<span class="status-dot status-dot--{state_class}" aria-hidden="true"></span>'
      f'{label}'
      f'</p>\n'
      f'      <p class="sub">{signal_as_of_line}</p>\n'
      f'      <p class="scalars">{scalars_line}</p>\n'
      f'{triggers_html}'
      f'{stop_html}'
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
