"""dashboard_renderer.components.account — account region renderers.

Phase 32 Plan 02: ported VERBATIM from dashboard_legacy/account_section.py.
All imports rewritten to canonical dashboard_renderer.* paths.
"""
import html
import logging

from system_params import INITIAL_ACCOUNT

from dashboard_renderer.components.positions import render_positions_table
from dashboard_renderer.components.trades import render_trades_table
from dashboard_renderer.formatters import (
  _CONTRACT_SPECS,
  _fmt_currency,
  _fmt_em_dash,
  _fmt_percent_signed,
)
from dashboard_renderer.stats import (
  compute_max_drawdown as _compute_max_drawdown,
  compute_sharpe as _compute_sharpe,
  compute_total_return as _compute_total_return,
  compute_unrealised_pnl_display as _compute_unrealised_pnl_display_raw,
  compute_win_rate as _compute_win_rate,
)

logger = logging.getLogger(__name__)


def _compute_unrealised_pnl_display(
  position: dict,
  state_key: str,
  current_close: float | None,
  state: dict | None = None,
) -> float | None:
  '''Thin adapter: matches the 4-arg legacy signature of
  dashboard_legacy.render_helpers._compute_unrealised_pnl_display,
  forwarding to the canonical 5-arg dashboard_renderer.stats version.
  '''
  return _compute_unrealised_pnl_display_raw(
    position=position,
    state_key=state_key,
    current_close=current_close,
    contract_specs=_CONTRACT_SPECS,
    state=state,
  )


def _render_key_stats(state: dict) -> str:
  '''UI-SPEC §Key stats block — 4 tiles Total Return/Sharpe/MaxDD/WinRate (DASH-07).

  Tile 1 Total Return is coloured (positive → long, negative → short, zero →
  muted). Tiles 2-4 are not coloured (magnitude reads as negative by sign;
  double-encoding would be noisy per UI-SPEC).
  '''
  total_return = _compute_total_return(state)
  sharpe = _compute_sharpe(state)
  max_dd = _compute_max_drawdown(state)
  win_rate = _compute_win_rate(state)

  # D-19 #5: Total Return CSS class — no inline style="color:..."
  # .pnl-positive/.pnl-negative/.pnl-zero defined in _INLINE_CSS (Plan 25-09)
  if total_return == _fmt_em_dash():
    tr_class = 'pnl-zero'
  elif total_return.startswith('-'):
    tr_class = 'pnl-negative'
  elif total_return in ('+0.0%', '-0.0%'):
    tr_class = 'pnl-zero'
  else:
    tr_class = 'pnl-positive'
  tr_value_esc = html.escape(total_return, quote=True)
  sharpe_esc = html.escape(sharpe, quote=True)
  max_dd_esc = html.escape(max_dd, quote=True)
  win_rate_esc = html.escape(win_rate, quote=True)

  return (
    '<section aria-labelledby="heading-stats">\n'
    '  <h2 id="heading-stats">Key Stats</h2>\n'
    '  <div class="stats-grid">\n'
    '    <div class="stat-tile">\n'
    '      <p class="label">Total Return</p>\n'
    f'      <p class="value {tr_class}">{tr_value_esc}</p>\n'
    '    </div>\n'
    '    <div class="stat-tile">\n'
    '      <p class="label">Sharpe</p>\n'
    f'      <p class="value">{sharpe_esc}</p>\n'
    '    </div>\n'
    '    <div class="stat-tile">\n'
    '      <p class="label">Max Drawdown</p>\n'
    f'      <p class="value">{max_dd_esc}</p>\n'
    '    </div>\n'
    '    <div class="stat-tile">\n'
    '      <p class="label">Win Rate</p>\n'
    f'      <p class="value">{win_rate_esc}</p>\n'
    '    </div>\n'
    '  </div>\n'
    '</section>\n'
  )


def _compute_account_stat_values(state: dict) -> dict:
  initial = float(state.get('initial_account', INITIAL_ACCOUNT))
  account = float(state.get('account', initial))
  realised = sum(float(t.get('net_pnl', 0.0)) for t in state.get('trade_log', []))
  unrealised = 0.0
  open_trades = 0
  exposure = 0.0
  for market_id, pos in state.get('positions', {}).items():
    if pos is None:
      continue
    open_trades += 1
    sig = state.get('signals', {}).get(market_id, {})
    last_close = sig.get('last_close') if isinstance(sig, dict) else None
    if last_close is None:
      continue
    resolved = state.get('_resolved_contracts', {}).get(market_id, {})
    multiplier = float(resolved.get('multiplier', 1.0))
    exposure += abs(float(last_close) * float(pos.get('n_contracts', 0)) * multiplier)
    upnl = _compute_unrealised_pnl_display(pos, market_id, float(last_close), state)
    if upnl is not None:
      unrealised += upnl
  equity = account + unrealised
  return {
    'initial': initial,
    'account': account,
    'realised': realised,
    'unrealised': unrealised,
    'equity': equity,
    'total_return': ((equity / initial) - 1.0) if initial > 0 else 0.0,
    'max_drawdown': _compute_max_drawdown(state),
    'win_rate': _compute_win_rate(state),
    'open_exposure': exposure,
    'open_trades': open_trades,
    'closed_trades': len(state.get('trade_log', [])),
  }


def _render_account_stats(state: dict) -> str:
  stats = _compute_account_stat_values(state)
  tiles = [
    ('Starting Balance', _fmt_currency(stats['initial'])),
    ('Account Balance', _fmt_currency(stats['account'])),
    ('Realised P&L', f'{stats["realised"]:+,.2f}'),
    ('Unrealised P&L', f'{stats["unrealised"]:+,.2f}'),
    ('Total Return', _fmt_percent_signed(stats['total_return'])),
    ('Max Drawdown', stats['max_drawdown']),
    ('Win Rate', stats['win_rate']),
    ('Open Exposure', _fmt_currency(stats['open_exposure'])),
    ('Open Trades', str(stats['open_trades'])),
    ('Closed Trades', str(stats['closed_trades'])),
  ]
  body = ''.join(
    '    <div class="stat-tile">\n'
    f'      <p class="label">{html.escape(label, quote=True)}</p>\n'
    f'      <p class="value">{html.escape(value, quote=True)}</p>\n'
    '    </div>\n'
    for label, value in tiles
  )
  return (
    '<section aria-labelledby="heading-account-stats">\n'
    '  <h2 id="heading-account-stats">Key Stats</h2>\n'
    '  <div class="stats-grid account-stats-grid">\n'
    f'{body}'
    '  </div>\n'
    '</section>\n'
  )


def _render_account_balance_form(state: dict) -> str:
  initial = float(state.get('initial_account', INITIAL_ACCOUNT))
  account = float(state.get('account', initial))
  return (
    '<section class="open-form account-balance-form">\n'
    '  <p class="eyebrow">ACCOUNT BASELINE</p>\n'
    '  <form hx-patch="/account/balance" hx-ext="json-enc" '
    'hx-target="#account-management-region" hx-swap="outerHTML" '
    'hx-on::after-request="handleTradesError(event)">\n'
    f'    <div class="field"><label for="account-balance-initial">Starting balance</label><input id="account-balance-initial" name="initial_account" type="number" step="0.01" min="0.01" value="{initial:.2f}" required></div>\n'
    f'    <div class="field"><label for="account-balance-current">Account balance</label><input id="account-balance-current" name="account" type="number" step="0.01" min="0" value="{account:.2f}" required></div>\n'
    '    <button type="submit" class="btn-primary">Update balances</button>\n'
    '  </form>\n'
    '  <div class="error" role="alert" aria-live="polite" hidden></div>\n'
    '</section>\n'
  )


def _render_account_management_region(state: dict) -> str:
  return (
    '<div id="account-management-region">\n'
    + _render_account_balance_form(state)
    + _render_account_stats(state)
    + render_positions_table(state, include_open_form=True)
    + render_trades_table(state)
    + '</div>\n'
  )
