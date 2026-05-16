'''Daily email body sections — action_required, signal_status, positions,
todays_pnl, closed_trades.

Extracted from notifier.py in Plan 27-12 (notifier package split). Each
function returns a self-contained <tr><td>...</td></tr> block; composed
into the full body shell by `notifier.templates.compose_email_body`.

XSS posture (preserved): every dynamic value flows through
html.escape(value, quote=True) at leaf render site (Phase 5 D-15).
'''
import html

from system_params import (
  _COLOR_BORDER,
  _COLOR_FLAT,
  _COLOR_LONG,
  _COLOR_SHORT,
  _COLOR_SURFACE,
  _COLOR_TEXT,
  _COLOR_TEXT_DIM,
  _COLOR_TEXT_MUTED,
  INITIAL_ACCOUNT,
)

from .formatters import (
  _EXIT_REASON_DISPLAY_EMAIL,
  _SIGNAL_COLOUR_EMAIL,
  _SIGNAL_LABELS_EMAIL,
  _STATE_KEY_TO_YF_SYMBOL,
  _closed_position_for_instrument_on,
  _compute_trail_stop_email,
  _compute_unrealised_pnl_email,
  _detect_signal_changes,
  _extract_last_close,
  _extract_signal_as_of,
  _extract_signal_int,
  _fmt_currency_email,
  _fmt_em_dash_email,
  _fmt_instrument_display_email,
  _fmt_percent_signed_email,
  _fmt_pnl_with_colour_email,
)


def _render_action_required_email(
  state: dict, old_signals: dict, run_date_iso: str,
) -> str:
  '''Section 2 (conditional): ACTION REQUIRED red-border block (D-11).

  Emitted ONLY when _detect_signal_changes is True. First-run is a no-op
  per D-06. Close-position copy sourced from
  _closed_position_for_instrument_on (last-3 scan per Fix 4). Uses raw
  Unicode → (U+2192) per Fix 5 — NEVER &rarr;.
  '''
  if not _detect_signal_changes(state, old_signals):
    return ''

  pieces: list[str] = []
  for state_key, yf_sym in _STATE_KEY_TO_YF_SYMBOL.items():
    old = old_signals.get(yf_sym)
    new = _extract_signal_int(state, state_key) or 0
    if old is None or old == new:
      continue
    inst = _fmt_instrument_display_email(state_key)
    old_label = _SIGNAL_LABELS_EMAIL.get(old, 'FLAT')
    new_label = _SIGNAL_LABELS_EMAIL.get(new, 'FLAT')
    # Close-position copy from trade_log (last-3 scan per Fix 4).
    closed = _closed_position_for_instrument_on(state, state_key, run_date_iso)
    close_copy = ''
    if closed is not None:
      direction_raw = str(closed.get('direction', ''))
      n_contracts = int(closed.get('n_contracts', 0))
      entry_price = float(closed.get('entry_price', 0.0))
      contract_word = 'contract' if n_contracts == 1 else 'contracts'
      close_copy = (
        f'<p style="margin:4px 0 0 0;color:{_COLOR_TEXT_MUTED};">'
        f'Close existing {html.escape(direction_raw, quote=True)} position '
        f'({html.escape(str(n_contracts), quote=True)} '
        f'{html.escape(contract_word, quote=True)} @ entry '
        f'{html.escape(_fmt_currency_email(entry_price), quote=True)}).'
        f'</p>'
      )
    # Open-new copy (skip on LONG/SHORT → FLAT since there's nothing to open).
    open_copy = ''
    if new != 0:
      open_copy = (
        f'<p style="margin:4px 0 0 0;color:{_COLOR_TEXT_MUTED};">'
        f'Open new {html.escape(new_label, quote=True)} position.'
        f'</p>'
      )
    # Raw Unicode → per Fix 5 (never &rarr;). Also escape labels/inst.
    pieces.append(
      f'<div style="margin-top:12px;">'
      f'<p style="margin:0;font-weight:600;color:{_COLOR_TEXT};">'
      f'{html.escape(inst, quote=True)}: '
      f'{html.escape(old_label, quote=True)} → '
      f'{html.escape(new_label, quote=True)}'
      f'</p>'
      f'{close_copy}{open_copy}'
      f'</div>'
    )

  if not pieces:
    return ''

  body_items = ''.join(pieces)
  return (
    f'<tr><td style="padding:12px 16px;background:{_COLOR_SURFACE};'
    f'border-left:4px solid {_COLOR_SHORT};'
    f'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\','
    f'Roboto,sans-serif;font-size:14px;color:{_COLOR_TEXT};'
    f'line-height:1.5;">'
    f'<p style="margin:0 0 8px 0;font-size:20px;font-weight:700;'
    f'color:{_COLOR_TEXT};letter-spacing:0.02em;">'
    f'━━━ ACTION REQUIRED ━━━</p>'
    f'{body_items}'
    f'</td></tr>\n'
    f'<tr><td height="32" style="height:32px;font-size:0;line-height:0;">'
    f'&nbsp;</td></tr>\n'
  )


def _render_signal_status_email(state: dict) -> str:
  '''Section 3: signal-status table — 2 rows × 5 cols (D-10).

  Instrument / Signal (coloured) / As of / ADX / Mom snapshot.
  '''
  rows: list[str] = []
  for state_key in ('SPI200', 'AUDUSD'):
    display = _fmt_instrument_display_email(state_key)
    sig_int = _extract_signal_int(state, state_key)
    as_of = _extract_signal_as_of(state, state_key)
    raw = state.get('signals', {}).get(state_key)
    scalars = raw.get('last_scalars') if isinstance(raw, dict) else None

    if sig_int is None or raw is None:
      sig_html = f'<span style="color:{_COLOR_FLAT};font-weight:600">—</span>'
    else:
      label = _SIGNAL_LABELS_EMAIL.get(sig_int, 'FLAT')
      colour = _SIGNAL_COLOUR_EMAIL.get(sig_int, _COLOR_FLAT)
      sig_html = (
        f'<span style="color:{colour};font-weight:600">'
        f'{html.escape(label, quote=True)}</span>'
      )

    if as_of:
      as_of_html = html.escape(as_of, quote=True)
    else:
      as_of_html = (
        f'<span style="color:{_COLOR_TEXT_DIM}">never</span>'
      )

    if scalars:
      adx_cell = html.escape(f'{scalars.get("adx", 0.0):.1f}', quote=True)
      mom1 = _fmt_percent_signed_email(scalars.get('mom1', 0.0))
      mom3 = _fmt_percent_signed_email(scalars.get('mom3', 0.0))
      mom12 = _fmt_percent_signed_email(scalars.get('mom12', 0.0))
      mom_cell = (
        f'{html.escape(mom1, quote=True)} &middot; '
        f'{html.escape(mom3, quote=True)} &middot; '
        f'{html.escape(mom12, quote=True)}'
      )
    else:
      adx_cell = html.escape(_fmt_em_dash_email(), quote=True)
      mom_cell = html.escape(_fmt_em_dash_email(), quote=True)

    rows.append(
      f'<tr style="border-bottom:1px solid {_COLOR_BORDER};">'
      f'<td style="padding:8px 12px;font-size:14px;color:{_COLOR_TEXT};">'
      f'{html.escape(display, quote=True)}</td>'
      f'<td style="padding:8px 12px;font-size:14px;">{sig_html}</td>'
      f'<td style="padding:8px 12px;font-size:14px;color:{_COLOR_TEXT_MUTED};">'
      f'{as_of_html}</td>'
      f'<td style="padding:8px 12px;font-size:14px;text-align:right;'
      f'font-family:\'SF Mono\',Menlo,Consolas,monospace;color:{_COLOR_TEXT};">'
      f'{adx_cell}</td>'
      f'<td style="padding:8px 12px;font-size:14px;text-align:right;'
      f'font-family:\'SF Mono\',Menlo,Consolas,monospace;color:{_COLOR_TEXT};">'
      f'{mom_cell}</td>'
      f'</tr>'
    )

  header_row = (
    f'<tr style="background:{_COLOR_SURFACE};'
    f'border-bottom:1px solid {_COLOR_BORDER};">'
    f'<th scope="col" style="padding:8px 12px;text-align:left;font-size:12px;'
    f'font-weight:600;color:{_COLOR_TEXT_MUTED};text-transform:uppercase;'
    f'letter-spacing:0.04em;">Instrument</th>'
    f'<th scope="col" style="padding:8px 12px;text-align:left;font-size:12px;'
    f'font-weight:600;color:{_COLOR_TEXT_MUTED};text-transform:uppercase;'
    f'letter-spacing:0.04em;">Signal</th>'
    f'<th scope="col" style="padding:8px 12px;text-align:left;font-size:12px;'
    f'font-weight:600;color:{_COLOR_TEXT_MUTED};text-transform:uppercase;'
    f'letter-spacing:0.04em;">As of</th>'
    f'<th scope="col" style="padding:8px 12px;text-align:right;font-size:12px;'
    f'font-weight:600;color:{_COLOR_TEXT_MUTED};text-transform:uppercase;'
    f'letter-spacing:0.04em;">ADX</th>'
    f'<th scope="col" style="padding:8px 12px;text-align:right;font-size:12px;'
    f'font-weight:600;color:{_COLOR_TEXT_MUTED};text-transform:uppercase;'
    f'letter-spacing:0.04em;">Mom</th>'
    f'</tr>'
  )
  body = ''.join(rows)
  return (
    f'<tr><td style="padding:0 12px;">'
    f'<h2 style="margin:0 12px 8px;font-size:20px;font-weight:600;'
    f'color:{_COLOR_TEXT};line-height:1.3;">Signal Status</h2>'
    f'<table role="presentation" cellpadding="0" cellspacing="0" '
    f'border="0" width="100%">'
    f'<thead>{header_row}</thead><tbody>{body}</tbody></table>'
    f'<p style="margin:4px 12px 0;font-size:11px;color:{_COLOR_TEXT_MUTED};">'
    f'Mom reads as 21d &middot; 63d &middot; 252d</p>'
    f'</td></tr>\n'
    f'<tr><td height="32" style="height:32px;font-size:0;line-height:0;">'
    f'&nbsp;</td></tr>\n'
  )


def _render_positions_email(state: dict) -> str:
  '''Section 4: open positions table — 7 cols (D-10).

  Instrument / Direction / Entry / Current / Contracts / Trail Stop /
  Unrealised P&L. Empty-state: single row "No open positions" colspan=7.
  '''
  positions = state.get('positions', {})
  rendered_rows: list[str] = []
  for state_key in ('SPI200', 'AUDUSD'):
    pos = positions.get(state_key)
    if pos is None:
      continue
    display = _fmt_instrument_display_email(state_key)
    direction_raw = str(pos.get('direction', ''))
    direction_int = (
      1 if direction_raw == 'LONG' else -1 if direction_raw == 'SHORT' else 0
    )
    dir_colour = _SIGNAL_COLOUR_EMAIL.get(direction_int, _COLOR_FLAT)
    entry_cell = html.escape(_fmt_currency_email(pos['entry_price']), quote=True)
    last_close = _extract_last_close(state, state_key)
    if last_close is None:
      current_cell = html.escape(_fmt_em_dash_email(), quote=True)
    else:
      current_cell = html.escape(_fmt_currency_email(last_close), quote=True)
    contracts_cell = html.escape(str(pos['n_contracts']), quote=True)
    trail = _compute_trail_stop_email(pos)
    trail_cell = html.escape(_fmt_currency_email(trail), quote=True)
    unrealised = _compute_unrealised_pnl_email(pos, state_key, last_close, state)
    if unrealised is None:
      pnl_cell = html.escape(_fmt_em_dash_email(), quote=True)
    else:
      pnl_cell = _fmt_pnl_with_colour_email(unrealised)
    rendered_rows.append(
      f'<tr style="border-bottom:1px solid {_COLOR_BORDER};">'
      f'<td style="padding:8px 12px;font-size:14px;color:{_COLOR_TEXT};">'
      f'{html.escape(display, quote=True)}</td>'
      f'<td style="padding:8px 12px;font-size:14px;">'
      f'<span style="color:{dir_colour};font-weight:600">'
      f'{html.escape(direction_raw, quote=True)}</span></td>'
      f'<td style="padding:8px 12px;font-size:14px;text-align:right;'
      f'font-family:\'SF Mono\',Menlo,Consolas,monospace;color:{_COLOR_TEXT};">'
      f'{entry_cell}</td>'
      f'<td style="padding:8px 12px;font-size:14px;text-align:right;'
      f'font-family:\'SF Mono\',Menlo,Consolas,monospace;color:{_COLOR_TEXT};">'
      f'{current_cell}</td>'
      f'<td style="padding:8px 12px;font-size:14px;text-align:right;'
      f'font-family:\'SF Mono\',Menlo,Consolas,monospace;color:{_COLOR_TEXT};">'
      f'{contracts_cell}</td>'
      f'<td style="padding:8px 12px;font-size:14px;text-align:right;'
      f'font-family:\'SF Mono\',Menlo,Consolas,monospace;color:{_COLOR_TEXT};">'
      f'{trail_cell}</td>'
      f'<td style="padding:8px 12px;font-size:14px;text-align:right;'
      f'font-family:\'SF Mono\',Menlo,Consolas,monospace;">{pnl_cell}</td>'
      f'</tr>'
    )

  if not rendered_rows:
    body = (
      f'<tr><td colspan="7" style="padding:16px;text-align:center;'
      f'font-size:14px;color:{_COLOR_TEXT_DIM};">'
      f'— No open positions —</td></tr>'
    )
  else:
    body = ''.join(rendered_rows)

  header_row = (
    f'<tr style="background:{_COLOR_SURFACE};'
    f'border-bottom:1px solid {_COLOR_BORDER};">'
    f'<th scope="col" style="padding:8px 12px;text-align:left;font-size:12px;'
    f'font-weight:600;color:{_COLOR_TEXT_MUTED};text-transform:uppercase;'
    f'letter-spacing:0.04em;">Instrument</th>'
    f'<th scope="col" style="padding:8px 12px;text-align:left;font-size:12px;'
    f'font-weight:600;color:{_COLOR_TEXT_MUTED};text-transform:uppercase;'
    f'letter-spacing:0.04em;">Direction</th>'
    f'<th scope="col" style="padding:8px 12px;text-align:right;font-size:12px;'
    f'font-weight:600;color:{_COLOR_TEXT_MUTED};text-transform:uppercase;'
    f'letter-spacing:0.04em;">Entry</th>'
    f'<th scope="col" style="padding:8px 12px;text-align:right;font-size:12px;'
    f'font-weight:600;color:{_COLOR_TEXT_MUTED};text-transform:uppercase;'
    f'letter-spacing:0.04em;">Current</th>'
    f'<th scope="col" style="padding:8px 12px;text-align:right;font-size:12px;'
    f'font-weight:600;color:{_COLOR_TEXT_MUTED};text-transform:uppercase;'
    f'letter-spacing:0.04em;">Contracts</th>'
    f'<th scope="col" style="padding:8px 12px;text-align:right;font-size:12px;'
    f'font-weight:600;color:{_COLOR_TEXT_MUTED};text-transform:uppercase;'
    f'letter-spacing:0.04em;">Trail Stop</th>'
    f'<th scope="col" style="padding:8px 12px;text-align:right;font-size:12px;'
    f'font-weight:600;color:{_COLOR_TEXT_MUTED};text-transform:uppercase;'
    f'letter-spacing:0.04em;">Unrealised P&amp;L</th>'
    f'</tr>'
  )
  return (
    f'<tr><td style="padding:0 12px;">'
    f'<h2 style="margin:0 12px 8px;font-size:20px;font-weight:600;'
    f'color:{_COLOR_TEXT};line-height:1.3;">Open Positions</h2>'
    f'<table role="presentation" cellpadding="0" cellspacing="0" '
    f'border="0" width="100%">'
    f'<thead>{header_row}</thead><tbody>{body}</tbody></table>'
    f'</td></tr>\n'
    f'<tr><td height="32" style="height:32px;font-size:0;line-height:0;">'
    f'&nbsp;</td></tr>\n'
  )


def _render_todays_pnl_email(state: dict) -> str:
  '''Section 5: Today's P&L + Running equity rollup (D-10).

  today_change = equity_history[-1].equity - equity_history[-2].equity
                 when len ≥ 2 else em-dash.
  running_equity = equity_history[-1].equity (or state['account'] when empty).
  since_inception = (running_equity - INITIAL_ACCOUNT) / INITIAL_ACCOUNT.
  '''
  equity_history = state.get('equity_history') or []
  if len(equity_history) >= 2:
    change = equity_history[-1]['equity'] - equity_history[-2]['equity']
    change_html = _fmt_pnl_with_colour_email(change)
  else:
    change_html = (
      f'<span style="color:{_COLOR_TEXT_DIM}">'
      f'{html.escape(_fmt_em_dash_email(), quote=True)}</span>'
    )

  from decimal import Decimal
  if equity_history:
    equity = equity_history[-1]['equity']
  else:
    equity = float(state.get('account', INITIAL_ACCOUNT))
  equity_cell = html.escape(_fmt_currency_email(equity), quote=True)

  since_inception_frac = (Decimal(str(equity)) - INITIAL_ACCOUNT) / INITIAL_ACCOUNT
  since_inception_str = _fmt_percent_signed_email(since_inception_frac)
  if since_inception_frac > 0:
    si_colour = _COLOR_LONG
  elif since_inception_frac < 0:
    si_colour = _COLOR_SHORT
  else:
    si_colour = _COLOR_TEXT_MUTED
  si_html = (
    f'<span style="color:{si_colour}">'
    f'{html.escape(since_inception_str, quote=True)}</span>'
  )

  # Pre-escape apostrophe-bearing literals (Python 3.11 f-string expressions
  # cannot contain backslashes). html.escape with quote=True renders ' as &#x27;.
  today_pnl_heading = html.escape("Today's P&L", quote=True)
  todays_change_label = html.escape("Today's change", quote=True)

  return (
    f'<tr><td style="padding:20px 24px;">'
    f'<h2 style="margin:0 0 16px;font-size:20px;font-weight:600;'
    f'color:{_COLOR_TEXT};line-height:1.3;">{today_pnl_heading}</h2>'
    f'<p style="margin:0;font-size:12px;font-weight:600;'
    f'color:{_COLOR_TEXT_MUTED};text-transform:uppercase;letter-spacing:0.04em;">'
    f'{todays_change_label}</p>'
    f'<p style="margin:8px 0 4px;font-size:22px;font-weight:600;'
    f'font-family:\'SF Mono\',Menlo,Consolas,monospace;">{change_html}</p>'
    f'<p style="margin:0 0 24px;font-size:12px;color:{_COLOR_TEXT_MUTED};">'
    f'from yesterday&#39;s close</p>'
    f'<p style="margin:0;font-size:12px;font-weight:600;'
    f'color:{_COLOR_TEXT_MUTED};text-transform:uppercase;letter-spacing:0.04em;">'
    f'Running equity</p>'
    f'<p style="margin:8px 0 4px;font-size:22px;font-weight:600;'
    f'font-family:\'SF Mono\',Menlo,Consolas,monospace;color:{_COLOR_TEXT};">'
    f'{equity_cell}</p>'
    f'<p style="margin:0;font-size:12px;color:{_COLOR_TEXT_MUTED};">'
    f'{si_html} since inception</p>'
    f'</td></tr>\n'
    f'<tr><td height="32" style="height:32px;font-size:0;line-height:0;">'
    f'&nbsp;</td></tr>\n'
  )


def _render_closed_trades_email(state: dict) -> str:
  '''Section 6: last 5 closed trades — 5 cols, newest first (D-10).

  Closed / Instrument / Direction / Entry → Exit / P&L.
  Uses net_pnl (NOT gross_pnl) per Phase 5 dashboard precedent.
  Empty-state: single row "No closed trades yet" colspan=5.
  '''
  trade_log = state.get('trade_log') or []
  slice_newest_first = list(reversed(trade_log[-5:]))
  rendered_rows: list[str] = []
  for trade in slice_newest_first:
    exit_date = html.escape(str(trade.get('exit_date', '')), quote=True)
    instrument_raw = str(trade.get('instrument', ''))
    instrument_display = _fmt_instrument_display_email(instrument_raw)
    instrument_cell = html.escape(instrument_display, quote=True)
    direction_raw = str(trade.get('direction', ''))
    direction_int = (
      1 if direction_raw == 'LONG' else -1 if direction_raw == 'SHORT' else 0
    )
    dir_colour = _SIGNAL_COLOUR_EMAIL.get(direction_int, _COLOR_FLAT)
    entry_price = html.escape(
      _fmt_currency_email(float(trade.get('entry_price', 0.0))), quote=True,
    )
    exit_price = html.escape(
      _fmt_currency_email(float(trade.get('exit_price', 0.0))), quote=True,
    )
    pnl_cell = _fmt_pnl_with_colour_email(float(trade.get('net_pnl', 0.0)))
    # Exit-reason rendered as dim small-print subtitle below P&L (retains
    # UI-SPEC §6 5-col layout while exercising T-06-03 leaf escape on
    # the highest-risk state-derived string). Display map converts known
    # raw values; unknown values pass through verbatim (html.escape at leaf).
    exit_reason_raw = str(trade.get('exit_reason', ''))
    reason_display = _EXIT_REASON_DISPLAY_EMAIL.get(
      exit_reason_raw, exit_reason_raw,
    )
    reason_html = html.escape(reason_display, quote=True)
    rendered_rows.append(
      f'<tr style="border-bottom:1px solid {_COLOR_BORDER};">'
      f'<td style="padding:8px 12px;font-size:14px;color:{_COLOR_TEXT};">'
      f'{exit_date}</td>'
      f'<td style="padding:8px 12px;font-size:14px;color:{_COLOR_TEXT};">'
      f'{instrument_cell}</td>'
      f'<td style="padding:8px 12px;font-size:14px;">'
      f'<span style="color:{dir_colour};font-weight:600">'
      f'{html.escape(direction_raw, quote=True)}</span></td>'
      f'<td style="padding:8px 12px;font-size:14px;text-align:right;'
      f'font-family:\'SF Mono\',Menlo,Consolas,monospace;color:{_COLOR_TEXT};'
      f'white-space:normal;">'
      f'{entry_price} → {exit_price}</td>'
      f'<td style="padding:8px 12px;font-size:14px;text-align:right;'
      f'font-family:\'SF Mono\',Menlo,Consolas,monospace;">'
      f'{pnl_cell}'
      f'<div style="margin-top:2px;font-size:11px;font-weight:400;'
      f'font-family:-apple-system,BlinkMacSystemFont,sans-serif;'
      f'color:{_COLOR_TEXT_DIM};">{reason_html}</div>'
      f'</td>'
      f'</tr>'
    )

  if not rendered_rows:
    body = (
      f'<tr><td colspan="5" style="padding:16px;text-align:center;'
      f'font-size:14px;color:{_COLOR_TEXT_DIM};">'
      f'— No closed trades yet —</td></tr>'
    )
  else:
    body = ''.join(rendered_rows)

  header_row = (
    f'<tr style="background:{_COLOR_SURFACE};'
    f'border-bottom:1px solid {_COLOR_BORDER};">'
    f'<th scope="col" style="padding:8px 12px;text-align:left;font-size:12px;'
    f'font-weight:600;color:{_COLOR_TEXT_MUTED};text-transform:uppercase;'
    f'letter-spacing:0.04em;">Closed</th>'
    f'<th scope="col" style="padding:8px 12px;text-align:left;font-size:12px;'
    f'font-weight:600;color:{_COLOR_TEXT_MUTED};text-transform:uppercase;'
    f'letter-spacing:0.04em;">Instrument</th>'
    f'<th scope="col" style="padding:8px 12px;text-align:left;font-size:12px;'
    f'font-weight:600;color:{_COLOR_TEXT_MUTED};text-transform:uppercase;'
    f'letter-spacing:0.04em;">Direction</th>'
    f'<th scope="col" style="padding:8px 12px;text-align:right;font-size:12px;'
    f'font-weight:600;color:{_COLOR_TEXT_MUTED};text-transform:uppercase;'
    f'letter-spacing:0.04em;">Entry → Exit</th>'
    f'<th scope="col" style="padding:8px 12px;text-align:right;font-size:12px;'
    f'font-weight:600;color:{_COLOR_TEXT_MUTED};text-transform:uppercase;'
    f'letter-spacing:0.04em;">P&amp;L</th>'
    f'</tr>'
  )
  return (
    f'<tr><td style="padding:0 12px;">'
    f'<h2 style="margin:0 12px 8px;font-size:20px;font-weight:600;'
    f'color:{_COLOR_TEXT};line-height:1.3;">Last 5 Closed Trades</h2>'
    f'<table role="presentation" cellpadding="0" cellspacing="0" '
    f'border="0" width="100%">'
    f'<thead>{header_row}</thead><tbody>{body}</tbody></table>'
    f'</td></tr>\n'
    f'<tr><td height="32" style="height:32px;font-size:0;line-height:0;">'
    f'&nbsp;</td></tr>\n'
  )
