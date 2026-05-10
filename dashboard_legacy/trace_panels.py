"""dashboard_legacy.trace_panels — Phase 17 Inputs/Indicators/Vote panels.

Extracted from dashboard.py (Plan 27-14). Owns trace-panel rendering for the
per-instrument <details> blocks. Hex-boundary preserved.
"""
import html
import math

from dashboard_legacy.render_helpers import (
    _SEED_LENGTHS,
    _TRACE_FORMULAS,
    _format_indicator_value,
)


# Fixed display order for indicator rows — matches _TRACE_FORMULAS key order.
_INDICATOR_DISPLAY_ORDER = ['tr', 'atr', 'plus_di', 'minus_di', 'adx', 'mom1', 'mom3', 'mom12', 'rvol']
_INDICATOR_DISPLAY_NAMES = {
  'tr': 'TR', 'atr': 'ATR(14)', 'plus_di': '+DI(20)', 'minus_di': '-DI(20)',
  'adx': 'ADX(20)', 'mom1': 'Mom1', 'mom3': 'Mom3', 'mom12': 'Mom12', 'rvol': 'RVol(20)',
}


def _render_trace_inputs(ohlc_window: list) -> str:
  '''Phase 17 D-02 + D-11: Inputs panel — rolling 40-bar OHLC table.

  Empty ohlc_window -> "Awaiting first daily run" placeholder per D-11.
  Non-empty -> one <tr data-row-index="N"> per bar, columns Date/Open/High/Low/Close.
  All leaf values pass through html.escape per T-17-03 (XSS defence-in-depth).
  '''
  if not ohlc_window:
    return (
      '<section class="trace-panel">\n'
      '  <p><em>Awaiting first daily run — calculations will appear after '
      'the next 08:00 AEST cycle.</em></p>\n'
      '</section>\n'
    )
  rows = []
  for i, entry in enumerate(ohlc_window):
    date_esc = html.escape(str(entry.get('date', '')), quote=True)
    open_esc = html.escape(f'{entry.get("open", 0.0):.2f}', quote=True)
    high_esc = html.escape(f'{entry.get("high", 0.0):.2f}', quote=True)
    low_esc = html.escape(f'{entry.get("low", 0.0):.2f}', quote=True)
    close_esc = html.escape(f'{entry.get("close", 0.0):.2f}', quote=True)
    rows.append(
      f'<tr data-row-index="{i}">'
      f'<td class="date">{date_esc}</td>'
      f'<td class="num">{open_esc}</td>'
      f'<td class="num">{high_esc}</td>'
      f'<td class="num">{low_esc}</td>'
      f'<td class="num">{close_esc}</td>'
      '</tr>\n'
    )
  return (
    '<section class="trace-panel">\n'
    '  <p class="eyebrow">INPUTS — OHLC WINDOW (40 bars)</p>\n'
    '  <table class="trace-ohlc-table">\n'
    '    <thead><tr><th>Date</th><th>Open</th><th>High</th><th>Low</th><th>Close</th></tr></thead>\n'
    '    <tbody>\n'
    + ''.join(rows)
    + '  </tbody></table>\n'
    '</section>\n'
  )

def _render_trace_indicators(
  indicator_scalars: dict,
  bars_available: int,
  atr_seed: float | None = None,
) -> str:
  '''Phase 17 D-03 + D-05 + D-06: Indicators panel — one row per indicator
  with tap-to-toggle formula reveal.

  Each indicator row: name cell (cursor:pointer, data-formula-open="false",
  title=formula tooltip) + value cell (6-decimal or reason text).
  Followed immediately by a hidden formula-row for D-03 tap-to-toggle.

  Empty indicator_scalars: all 9 rows render with "n/a (need N bars, have 0)".

  Phase 29 Plan 11: if atr_seed is provided and finite, render an extra
  "ATR seed (bar -1)" row before the ATR(14) row so hand-recalc can anchor
  to the engine-persisted Wilder seed. Stale rows (None or NaN) show a
  "(stale row — refresh after next 08:00 cycle)" fallback.
  '''
  rows = []

  # ATR seed row (before the main indicator loop).
  if atr_seed is None or (isinstance(atr_seed, float) and math.isnan(atr_seed)):
    seed_cell = '<em>(stale row — refresh after next 08:00 cycle)</em>'
  else:
    seed_val_esc = html.escape(f'{float(atr_seed):.6f}', quote=True)
    seed_cell = seed_val_esc
  seed_title = html.escape(
    'Wilder seed at bar before window — hand-recalc starts here', quote=True
  )
  rows.append(
    f'<tr>'
    f'<td class="trace-indicator-name" title="{seed_title}">'
    f'ATR seed (bar -1)</td>'
    f'<td class="num">{seed_cell}</td>'
    f'</tr>\n'
  )

  for key in _INDICATOR_DISPLAY_ORDER:
    formula = _TRACE_FORMULAS.get(key, '')
    formula_esc = html.escape(formula, quote=True)
    display_name = _INDICATOR_DISPLAY_NAMES.get(key, key)
    name_esc = html.escape(display_name, quote=True)
    seed = _SEED_LENGTHS.get(key, 1)
    raw = indicator_scalars.get(key, float('nan'))
    value_str = _format_indicator_value(float(raw), seed, bars_available)
    value_esc = html.escape(value_str, quote=True)
    rows.append(
      f'<tr>'
      f'<td class="trace-indicator-name" data-formula-open="false" title="{formula_esc}">'
      f'{name_esc}</td>'
      f'<td class="num">{value_esc}</td>'
      f'</tr>\n'
      f'<tr class="formula-row" hidden>'
      f'<td colspan="2">{formula_esc}</td>'
      f'</tr>\n'
    )
  return (
    '<section class="trace-panel">\n'
    '  <p class="eyebrow">INDICATORS</p>\n'
    '  <table class="trace-indicators-table">\n'
    '    <tbody>\n'
    + ''.join(rows)
    + '  </tbody></table>\n'
    '</section>\n'
  )

def _render_trace_vote(
  indicator_scalars: dict,
  signal: int,
  vote_params: dict | None = None,
) -> str:
  '''Phase 17 D-07: Vote panel — 3 Mom badges + ADX gate badge + outcome.

  Badge classes: plus/minus/zero for Mom sign; pass/fail for ADX gate.
  Gate + momentum threshold come from `vote_params` (the resolved per-trade
  params persisted by daily_run alongside indicator_scalars). Falls back to
  25.0 / 0.02 for state rows written before vote_params existed.
  Empty indicator_scalars: "Awaiting first daily run." per D-11.
  '''
  if not indicator_scalars:
    return (
      '<section class="trace-panel trace-vote">\n'
      '  <p><em>Awaiting first daily run.</em></p>\n'
      '</section>\n'
    )
  _OUTCOME_LABEL = {1: 'LONG', -1: 'SHORT', 0: 'FLAT'}
  vp = vote_params or {}
  adx_gate_threshold = float(vp.get('adx_gate', 25.0))
  mom_threshold = float(vp.get('momentum_threshold', 0.02))

  def _mom_badge(val: float) -> str:
    if math.isnan(val) or val == 0.0:
      return '<span class="trace-badge zero">0</span>'
    if val > 0:
      return '<span class="trace-badge plus">+</span>'
    return '<span class="trace-badge minus">-</span>'

  mom1 = float(indicator_scalars.get('mom1', float('nan')))
  mom3 = float(indicator_scalars.get('mom3', float('nan')))
  mom12 = float(indicator_scalars.get('mom12', float('nan')))
  adx = float(indicator_scalars.get('adx', float('nan')))

  seed_mom = _SEED_LENGTHS.get('mom1', 2)
  bars_avail = 40  # display context: we always show 40 bars when populated

  mom1_val = html.escape(_format_indicator_value(mom1, seed_mom, bars_avail), quote=True)
  mom3_val = html.escape(_format_indicator_value(mom3, _SEED_LENGTHS.get('mom3', 4), bars_avail), quote=True)
  mom12_val = html.escape(_format_indicator_value(mom12, _SEED_LENGTHS.get('mom12', 13), bars_avail), quote=True)

  adx_finite = not math.isnan(adx)
  adx_pass = adx_finite and adx >= adx_gate_threshold
  adx_badge_cls = 'pass' if adx_pass else 'fail'
  adx_val_str = html.escape(_format_indicator_value(adx, _SEED_LENGTHS.get('adx', 20), bars_avail), quote=True)
  gate_text = html.escape(f'>= {adx_gate_threshold:g}', quote=True)
  gate_result = 'PASS' if adx_pass else 'FAIL'

  outcome_label = html.escape(_OUTCOME_LABEL.get(signal, 'FLAT'), quote=True)

  # Prelim "Vote" applies the same momentum threshold the engine uses, so
  # Vote/FINAL only diverge when the ADX gate or direction mode flipped it.
  votes = sum(1 for v in (mom1, mom3, mom12) if not math.isnan(v) and v > mom_threshold)
  anti_votes = sum(1 for v in (mom1, mom3, mom12) if not math.isnan(v) and v < -mom_threshold)
  if votes > anti_votes:
    prelim = 'LONG'
  elif anti_votes > votes:
    prelim = 'SHORT'
  else:
    prelim = 'FLAT'
  prelim_esc = html.escape(prelim, quote=True)

  return (
    '<section class="trace-panel trace-vote">\n'
    '  <p class="eyebrow">VOTE</p>\n'
    '  <table class="trace-vote-table"><tbody>\n'
    f'  <tr><td>Mom1</td><td>{_mom_badge(mom1)}</td><td class="num">{mom1_val}</td></tr>\n'
    f'  <tr><td>Mom3</td><td>{_mom_badge(mom3)}</td><td class="num">{mom3_val}</td></tr>\n'
    f'  <tr><td>Mom12</td><td>{_mom_badge(mom12)}</td><td class="num">{mom12_val}</td></tr>\n'
    f'  <tr><td>ADX gate</td><td><span class="trace-badge {adx_badge_cls}">{gate_result}</span></td>'
    f'<td class="num">ADX {adx_val_str} {gate_text}</td></tr>\n'
    '  </tbody></table>\n'
    f'  <p>Vote: {prelim_esc}</p>\n'
    f'  <p class="trace-outcome">FINAL: {outcome_label}</p>\n'
    '</section>\n'
  )

def _render_trace_panels(
  sig_dict: dict,
  instrument_key: str,
  placeholder: str,
) -> str:
  '''Phase 17 D-04: per-instrument <details> wrapper around the three trace
  panels (Inputs / Indicators / Vote).

  `placeholder` is the literal string "{{TRACE_OPEN_<KEY>}}" (from
  _TRACE_OPEN_PLACEHOLDER[instrument_key]) — emitted verbatim AFTER the
  data-instrument attribute. web/routes/dashboard.py substitutes it
  per-request with " open" or "" based on the tsi_trace_open cookie.

  Design note (PATTERNS.md §Pattern To Design From Scratch): attribute-level
  substitution vs Phase 16.1's block-level. The placeholder is inside the
  opening tag, not surrounding a content block.
  '''
  inst_esc = html.escape(instrument_key, quote=True)
  ohlc_window = sig_dict.get('ohlc_window', [])
  indicator_scalars = sig_dict.get('indicator_scalars', {})
  signal = sig_dict.get('signal', 0)
  vote_params = sig_dict.get('vote_params')
  # Phase 29 Plan 11: extract persisted Wilder ATR seed (may be absent on
  # legacy state rows written before Plan 11 — treated as stale).
  atr_seed = sig_dict.get('atr_seed')
  bars_available = len(ohlc_window)
  inner = (
    _render_trace_inputs(ohlc_window)
    + _render_trace_indicators(indicator_scalars, bars_available, atr_seed=atr_seed)
    + _render_trace_vote(indicator_scalars, signal, vote_params)
  )
  return (
    f'<details class="trace-disclosure" data-instrument="{inst_esc}"{placeholder}>\n'
    '  <summary class="trace-summary">Show calculations</summary>\n'
    + inner
    + '</details>\n'
  )
