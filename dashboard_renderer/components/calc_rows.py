"""dashboard_renderer.components.calc_rows — calculator + entry-target sub-rows.

Phase 32 Plan 02: ported VERBATIM from dashboard_legacy/calc_rows.py.
All imports rewritten to canonical dashboard_renderer.* paths.
sizing_engine imports are LOCAL function-body only (C-2 pattern).
"""
import html
import logging
import math

from dashboard_renderer.formatters import (
  _fmt_currency,
  _fmt_em_dash,
  _fmt_percent_unsigned,
  _strategy_settings_for,
)
from dashboard_renderer.stats import compute_trail_stop_display as _compute_trail_stop_display
from system_params import TRAIL_MULT_LONG, TRAIL_MULT_SHORT

logger = logging.getLogger(__name__)


def _render_calc_row(state: dict, state_key: str, pos: dict) -> str:
  '''Phase 15 CALC-01/04: calculator sub-row rendered after a position row.

  Cells (REVIEWS H-1 + M-3 + L-3):
    - STOP        : current trailing stop (manual_stop precedence honored)
    - DIST        : |current_close - trail_stop| in $ and %  (M-3: current-price baseline)
    - NEXT ADD    : entry +/- (level+1)*atr_entry           (Pitfall 6)
    - LEVEL       : level N/MAX_PYRAMID_LEVEL or "fully pyramided"
    - NEW STOP    : projected stop AFTER the next pyramid add (H-1: synthesize peak=NEXT_ADD)
    - IF HIGH     : forward-look HTMX input + W placeholder (em-dash on first render)
                    + conditional "(enter high to project)" hint (L-3)

  sizing_engine import is LOCAL (C-2; permitted by Plan 01
  FORBIDDEN_MODULES_DASHBOARD update + Plan 01 Task 2 AST guard for
  module-top imports). check_pyramid is intentionally NOT imported —
  its return type does not contain the next-add price (Pitfall 6 +
  REVIEWS H-1: compute the price + projected stop directly).
  '''
  from sizing_engine import get_trailing_stop  # LOCAL — C-2 + REVIEWS M-2
  from system_params import MAX_PYRAMID_LEVEL

  state_key_esc = html.escape(state_key, quote=True)
  direction = pos.get('direction', 'LONG')
  entry_price = float(pos.get('entry_price', 0.0))
  atr_entry = float(pos.get('atr_entry', 0.0))
  # Position TypedDict (system_params.py) names the field `pyramid_level`.
  # Phase 15 plan/tests called it `current_level`. Accept both — production
  # uses pyramid_level; some test fixtures use current_level.
  # Tolerate non-int values (defensive — e.g. XSS-escape regression fixtures).
  try:
    current_level = int(pos.get('pyramid_level', pos.get('current_level', 0)))
  except (ValueError, TypeError):
    current_level = 0

  # STOP cell — reuse Phase 14 _compute_trail_stop_display for the value
  # (handles manual_stop precedence + NaN guards).
  settings = _strategy_settings_for(state, state_key)
  trail_stop = _compute_trail_stop_display(pos, settings)
  stop_html = (
    html.escape(_fmt_currency(trail_stop), quote=True)
    if trail_stop is not None and math.isfinite(trail_stop)
    else _fmt_em_dash()
  )

  # REVIEWS M-3: DIST baseline = current_close, NOT entry_price.
  # Source: state['signals'][state_key]['last_close']. When signal is int
  # shape (Phase 3 reset) or missing, current_close is None -> em-dash.
  sig_entry = state.get('signals', {}).get(state_key)
  if isinstance(sig_entry, dict):
    current_close_raw = sig_entry.get('last_close')
    try:
      current_close = float(current_close_raw) if current_close_raw is not None else None
    except (TypeError, ValueError):
      current_close = None
  else:
    current_close = None

  if (
    current_close is not None and math.isfinite(current_close) and current_close > 0
    and trail_stop is not None and math.isfinite(trail_stop)
  ):
    dist_abs = abs(current_close - trail_stop)
    dist_pct = dist_abs / current_close
    dist_dollar = html.escape(_fmt_currency(dist_abs), quote=True)
    dist_pct_html = html.escape(_fmt_percent_unsigned(dist_pct), quote=True)
  else:
    dist_dollar = _fmt_em_dash()
    dist_pct_html = _fmt_em_dash()

  # NEXT ADD price (Pitfall 6 formula — direction-aware)
  can_pyramid = (
    current_level < MAX_PYRAMID_LEVEL
    and math.isfinite(atr_entry) and atr_entry > 0
    and entry_price > 0
  )
  if can_pyramid:
    if direction == 'LONG':
      next_add_price = entry_price + (current_level + 1) * atr_entry
    else:  # SHORT
      next_add_price = entry_price - (current_level + 1) * atr_entry
    next_add_html = html.escape(_fmt_currency(next_add_price), quote=True)
  else:
    next_add_price = None
    next_add_html = _fmt_em_dash()

  # LEVEL cell
  if current_level >= MAX_PYRAMID_LEVEL:
    level_html = (
      f'<span class="calc-dim">level {current_level}/{MAX_PYRAMID_LEVEL} — '
      f'fully pyramided</span>'
    )
  else:
    level_html = f'level {current_level}/{MAX_PYRAMID_LEVEL}'

  # REVIEWS H-1 + ATR annotation: NEW STOP cell.
  # Synthesize a position whose peak (LONG) / trough (SHORT) is at
  # next_add_price; drop manual_stop so we get the COMPUTED projected stop.
  # Same pattern as the forward-look fragment handler in Plan 06.
  if can_pyramid and next_add_price is not None:
    synth_for_add = dict(pos)
    if direction == 'LONG':
      synth_for_add['peak_price'] = max(
        pos.get('peak_price') or entry_price, next_add_price,
      )
    else:
      synth_for_add['trough_price'] = min(
        pos.get('trough_price') or entry_price, next_add_price,
      )
    synth_for_add['manual_stop'] = None
    try:
      new_stop_value = get_trailing_stop(synth_for_add, 0.0, 0.0)
    except Exception:
      new_stop_value = float('nan')
    if math.isfinite(new_stop_value):
      new_stop_html = html.escape(_fmt_currency(new_stop_value), quote=True)
    else:
      new_stop_html = _fmt_em_dash()
    # Step annotation matches "+1×ATR" for level-0->1, "+2×ATR" for level-1->2
    atr_step_label = f'(+{current_level + 1}×ATR)'
  else:
    new_stop_html = _fmt_em_dash()
    atr_step_label = ''

  # IF HIGH — forward-look input + W placeholder + conditional hint (REVIEWS L-3)
  forward_input = (
    f'<input id="forward-stop-{state_key_esc}-z" name="z" type="number" step="0.01" min="0" '
    f'hx-get="/?fragment=forward-stop&amp;instrument={state_key_esc}" '
    f'hx-trigger="input changed delay:300ms" '
    f'hx-target="#forward-stop-{state_key_esc}-w" '
    f'hx-include="this" '
    f'class="calc-input" '
    f'aria-label="Enter today&apos;s high to project trailing stop for {state_key_esc}">'
  )
  # REVIEWS L-3: hint shown only on initial render (W is em-dash).
  # When Plan 06's fragment response replaces the W span with a real value,
  # the response also overrides the hint span (Plan 06 returns the W span
  # alone; the hint span outside the swap target stays put — but is still
  # only meaningful when W is em-dash). Rendering the hint here is safe
  # because the swap target only replaces #forward-stop-{X}-w. To make the
  # hint disappear after typing, Plan 06 returns a wrapper that includes
  # both the W span AND a (no-op or empty) hint span via an oob swap on
  # a sibling id. For Wave 2 we render the hint as a separate span with
  # id="forward-stop-{X}-hint"; Plan 06 will optionally hx-swap-oob it
  # out. (Documented constraint: this plan ships only the initial-render
  # hint; the conditional disappearance is Plan 06 scope.)
  hint_html = (
    f'<span id="forward-stop-{state_key_esc}-hint" class="calc-dim">'
    f'(enter high to project)</span>'
  )

  # Pyramid label sub-formatting: when can_pyramid we want
  # "next add at $X (+1×ATR)" + "new stop $S" — adjacent labels per UI-SPEC.
  next_add_with_step = (
    f'{next_add_html} <span class="calc-dim">{atr_step_label}</span>'
    if atr_step_label
    else next_add_html
  )

  return (
    f'    <tr class="calc-row" aria-label="Calculator data for {state_key_esc}">\n'
    f'      <td colspan="9" class="calc-cell">\n'
    f'        <span class="calc-label">STOP</span>\n'
    f'        <span class="calc-value num">{stop_html}</span>\n'
    f'        <span class="calc-sep"> | </span>\n'
    f'        <span class="calc-label">DIST</span>\n'
    f'        <span class="calc-value num">{dist_dollar}</span>\n'
    f'        <span class="calc-dim"> / </span>\n'
    f'        <span class="calc-value num">{dist_pct_html}</span>\n'
    f'        <span class="calc-sep"> | </span>\n'
    f'        <span class="calc-label">NEXT ADD</span>\n'
    f'        <span class="calc-value num">{next_add_with_step}</span>\n'
    f'        <span class="calc-sep"> | </span>\n'
    f'        <span class="calc-label">LEVEL</span>\n'
    f'        <span class="calc-value">{level_html}</span>\n'
    f'        <span class="calc-sep"> | </span>\n'
    f'        <span class="calc-label">NEW STOP</span>\n'
    f'        <span class="calc-value num">{new_stop_html}</span>\n'
    f'        <span class="calc-sep"> | </span>\n'
    f'        <span class="calc-label">IF HIGH</span>\n'
    f'        {forward_input}\n'
    f'        <span class="calc-dim">stop rises to</span>\n'
    f'        <span id="forward-stop-{state_key_esc}-w" class="calc-value num">{_fmt_em_dash()}</span>\n'
    f'        {hint_html}\n'
    f'      </td>\n'
    f'    </tr>\n'
  )

def _render_entry_target_row(state: dict, state_key: str) -> str:
  '''Phase 15 CALC-02: entry-target row when position is None and signal
  is LONG or SHORT. Returns empty string when signal is FLAT.

  sizing_engine.calc_position_size import is LOCAL (C-2).
  '''
  sig_entry = state.get('signals', {}).get(state_key)
  if sig_entry is None:
    return ''
  if isinstance(sig_entry, int):
    sig_val = sig_entry
    last_close = None
    atr = None
    rvol = None
  elif isinstance(sig_entry, dict):
    sig_val = sig_entry.get('signal')
    last_close = sig_entry.get('last_close')
    last_scalars = sig_entry.get('last_scalars') or {}
    atr = last_scalars.get('atr')
    rvol = last_scalars.get('rvol')
  else:
    return ''
  if sig_val not in (1, -1):
    return ''
  direction_label = 'LONG' if sig_val == 1 else 'SHORT'
  # D-19 #5: use semantic class instead of inline style="color:..."
  direction_class = 'signal-long' if sig_val == 1 else 'signal-short'
  state_key_esc = html.escape(state_key, quote=True)

  # Threshold = today's last_close (RESEARCH §Open Question 2)
  if last_close is not None and math.isfinite(last_close):
    threshold_html = html.escape(_fmt_currency(last_close), quote=True)
  else:
    threshold_html = _fmt_em_dash()

  # Suggested contracts via calc_position_size (LOCAL import)
  contracts_html = _fmt_em_dash()
  initial_stop_html = _fmt_em_dash()
  try:
    if all(v is not None and math.isfinite(v)
           for v in (last_close, atr, rvol)):
      from sizing_engine import calc_position_size  # LOCAL — C-2
      account = float(state.get('account', 0.0))
      contracts_per_inst = state.get('_resolved_contracts', {}).get(state_key) or {}
      multiplier = float(contracts_per_inst.get('multiplier', 1.0))
      decision = calc_position_size(
        account, sig_val, atr, rvol, multiplier,
        settings=_strategy_settings_for(state, state_key),
      )
      if decision.contracts > 0:
        contracts_html = html.escape(
          f'{decision.contracts} contracts', quote=True,
        )
        settings = _strategy_settings_for(state, state_key)
        if sig_val == 1:
          initial_stop = last_close - float(settings.get('trail_mult_long', TRAIL_MULT_LONG)) * atr
        else:
          initial_stop = last_close + float(settings.get('trail_mult_short', TRAIL_MULT_SHORT)) * atr
        if math.isfinite(initial_stop):
          initial_stop_html = html.escape(_fmt_currency(initial_stop), quote=True)
  except Exception:
    # Fallback to em-dashes; never crash the dashboard render
    pass

  return (
    f'    <tr class="calc-row" aria-label="Entry target for {state_key_esc}">\n'
    f'      <td colspan="9" class="calc-cell entry-target">\n'
    f'        <span class="calc-label">Entry target</span>\n'
    f'        <span class="calc-sep"> | </span>\n'
    f'        <span class="calc-dim">Signal:</span>\n'
    f'        <span class="{direction_class}">{direction_label}</span>\n'
    f'        <span class="calc-dim"> — enter on next close ≥ </span>\n'
    f'        <span class="calc-value num">{threshold_html}</span>\n'
    f'        <span class="calc-sep"> | </span>\n'
    f'        <span class="calc-dim">Size:</span>\n'
    f'        <span class="calc-value">{contracts_html}</span>\n'
    f'        <span class="calc-sep"> | </span>\n'
    f'        <span class="calc-dim">Initial stop:</span>\n'
    f'        <span class="calc-value num">{initial_stop_html}</span>\n'
    f'      </td>\n'
    f'    </tr>\n'
  )
