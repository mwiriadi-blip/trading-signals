'''Magic-link + stop-loss alert email templates.

Extracted from notifier.py in Plan 27-12 (notifier package split).

Independent template families that don't share rendering surface with the
daily email body:
  - Magic-link reset (Phase 16.1 F-03)
  - Stop-loss alert (Phase 20 D-02/D-13)

XSS posture (preserved): every dynamic value flows through
html.escape(value, quote=True) at leaf render site.
'''
import html
from datetime import datetime

import pytz

from system_params import (
  _COLOR_BG,
  _COLOR_BORDER,
  _COLOR_LONG,
  _COLOR_SURFACE,
  _COLOR_TEXT,
  _COLOR_TEXT_MUTED,
)

# =========================================================================
# Phase 16.1 Plan 03 F-03 — magic-link reset email
# =========================================================================

def _format_expires_awst(expires_at: str) -> str:
  '''Convert ISO 8601 UTC string to Australia/Perth AWST display.

  Display format: "29 Apr 2026 at 5:00 PM AWST" (operator-readable; uses
  pytz to match the rest of notifier.py — no zoneinfo import to keep
  compat with the existing Phase 7 deployment posture).

  Returns the input string verbatim if parsing fails (defensive — caller
  gets best-effort output rather than a crash).
  '''
  try:
    dt = datetime.fromisoformat(expires_at)
  except (TypeError, ValueError):
    return expires_at
  awst = pytz.timezone('Australia/Perth')
  awst_dt = dt.astimezone(awst)
  # %-d / %-I are GNU/BSD-specific; both are available on macOS and Linux
  # which are the only deploy targets per CLAUDE.md.
  try:
    return awst_dt.strftime('%-d %b %Y at %-I:%M %p AWST')
  except ValueError:
    return awst_dt.strftime('%d %b %Y at %I:%M %p AWST')


def _render_magic_link_html(link: str, action: str, expires_at: str) -> str:  # noqa: ARG001
  '''F-03: HTML body for the magic-link email.

  Mirrors notifier.py inline-CSS dark-theme palette (Phase 6 D-15 leaf-discipline).
  All operator-influenced strings are html.escape'd defensively even though
  the link is server-generated — global LEARNING "innerHTML with dynamic
  data requires escaping". The link contains '?token=...&...' query params
  that MUST become &amp; in the rendered href to keep the URL parsable.
  '''
  from html import escape as html_escape
  esc_link = html_escape(link, quote=True)
  expires_display = _format_expires_awst(expires_at)
  esc_expires = html_escape(expires_display, quote=True)
  return (
    '<!DOCTYPE html>\n'
    '<html lang="en">\n'
    '<head><meta charset="utf-8"></head>\n'
    f'<body style="background:{_COLOR_BG}; color:{_COLOR_TEXT}; '
    'font-family:-apple-system,BlinkMacSystemFont,sans-serif; padding:32px;">\n'
    f'  <div style="max-width:480px; margin:0 auto; background:{_COLOR_SURFACE}; '
    f'border:1px solid {_COLOR_BORDER}; border-radius:8px; padding:24px;">\n'
    '    <h1 style="font-size:20px; font-weight:600; margin:0 0 16px;">'
    'Trading Signals — 2FA reset</h1>\n'
    '    <p style="font-size:14px; line-height:1.5; margin:0 0 16px;">'
    f'Click the button below to reset your two-factor authenticator. '
    f'This link is valid until {esc_expires} and can be used once.</p>\n'
    '    <p style="margin:24px 0;">\n'
    f'      <a href="{esc_link}" style="display:inline-block; padding:12px 24px; '
    f'background:transparent; color:{_COLOR_LONG}; border:1px solid {_COLOR_LONG}; '
    'border-radius:4px; text-decoration:none; font-weight:600;">Reset 2FA</a>\n'
    '    </p>\n'
    f'    <p style="font-size:12px; color:{_COLOR_TEXT_MUTED}; margin:0;">'
    "If you didn't request this, ignore this email — your authenticator "
    'is unchanged.</p>\n'
    f'    <p style="font-size:12px; color:{_COLOR_TEXT_MUTED}; '
    f'margin:16px 0 0; word-break:break-all;">Or copy this link: {esc_link}</p>\n'
    '  </div>\n'
    '</body>\n'
    '</html>\n'
  )


def _render_magic_link_text(link: str, action: str, expires_at: str) -> str:  # noqa: ARG001
  '''F-03: plain-text fallback for clients that strip HTML.'''
  expires_display = _format_expires_awst(expires_at)
  return (
    'Trading Signals — 2FA reset\n\n'
    'Click this link to reset your authenticator (valid 1 hour, single-use):\n'
    f'{link}\n\n'
    f'Link expires: {expires_display}\n\n'
    "If you didn't request this, ignore this email — your authenticator "
    'is unchanged.\n'
  )


# =========================================================================
# Phase 20 D-02/D-13 — stop-loss alert email
# =========================================================================

def _build_alert_subject(transitions: list[dict]) -> str:
  '''D-02: [!stop] subject with N==1 per-trade or N>1 batched format.'''
  n = len(transitions)
  if n == 1:
    t = transitions[0]
    trade_id = html.escape(str(t.get('id', '')), quote=True)
    instrument = html.escape(str(t.get('instrument', '')), quote=True)
    side = html.escape(str(t.get('side', '')), quote=True)
    state = html.escape(str(t.get('new_state', '')), quote=True)
    return f'[!stop] {instrument} {side} {state} — {trade_id}'
  return f"[!stop] {n} transition(s) in today's paper trades"


def _render_alert_email_html(transitions: list[dict], dashboard_url: str) -> str:
  '''D-02/D-13: self-contained inline-styled HTML for the stop-alert email.

  Every interpolated string field wrapped in html.escape(str(v), quote=True).
  State badges use INLINE style attributes (Gmail mobile strips <style> blocks;
  RESEARCH §Pitfall 3 / UAT-16-B 2026-04-29).
  '''
  n = len(transitions)
  # Per-state badge inline styles (D-14 hex pairs from CONTEXT D-14 verbatim).
  _BADGE_STYLES = {
    'CLEAR': (
      'background:#d4edda;color:#155724;padding:2px 6px;'
      'border-radius:4px;font-weight:bold;'
    ),
    'APPROACHING': (
      'background:#fff3cd;color:#856404;padding:2px 6px;'
      'border-radius:4px;font-weight:bold;'
    ),
    'HIT': (
      'background:#f8d7da;color:#721c24;padding:2px 6px;'
      'border-radius:4px;font-weight:bold;'
    ),
  }
  default_badge = (
    'background:#e9ecef;color:#6c757d;padding:2px 6px;'
    'border-radius:4px;font-weight:bold;'
  )

  rows_html = []
  for t in transitions:
    esc_id      = html.escape(str(t.get('id', '')), quote=True)
    esc_inst    = html.escape(str(t.get('instrument', '')), quote=True)
    esc_side    = html.escape(str(t.get('side', '')), quote=True)
    esc_state   = html.escape(str(t.get('new_state', '')), quote=True)
    entry_fmt   = html.escape(f"{t.get('entry_price', 0.0):.2f}", quote=True)
    stop_fmt    = html.escape(f"{t.get('stop_price', 0.0):.2f}", quote=True)
    close_fmt   = html.escape(f"{t.get('today_close', 0.0):.2f}", quote=True)
    atr_dist    = t.get('atr_distance', 0.0)
    # NaN check via self-inequality (no math import needed; avoids import count change).
    if atr_dist != atr_dist:  # noqa: PLR0124 -- float NaN self-inequality check
      dist_text = 'distance unknown'
    else:
      label = 'within trigger' if t.get('new_state') == 'APPROACHING' else 'beyond stop'
      dist_text = f'{atr_dist:.2f} ATR ({label})'
    esc_dist = html.escape(dist_text, quote=True)
    badge_style = _BADGE_STYLES.get(str(t.get('new_state', '')), default_badge)
    rows_html.append(
      f'      <tr>'
      f'<td style="padding:6px 8px;border:1px solid #ddd;">{esc_id}</td>'
      f'<td style="padding:6px 8px;border:1px solid #ddd;">{esc_side}</td>'
      f'<td style="padding:6px 8px;border:1px solid #ddd;">${esc_inst} {entry_fmt}</td>'
      f'<td style="padding:6px 8px;border:1px solid #ddd;">${stop_fmt}</td>'
      f'<td style="padding:6px 8px;border:1px solid #ddd;">${close_fmt}</td>'
      f'<td style="padding:6px 8px;border:1px solid #ddd;">{esc_dist}</td>'
      f'<td style="padding:6px 8px;border:1px solid #ddd;">'
      f'<span style="{badge_style}">{esc_state}</span>'
      f'</td>'
      f'</tr>\n'
    )

  rows_str = ''.join(rows_html)
  esc_url = html.escape(dashboard_url, quote=True)
  return (
    '<!DOCTYPE html>\n'
    '<html lang="en">\n'
    '<head><meta charset="utf-8"></head>\n'
    '<body style="font-family:-apple-system,BlinkMacSystemFont,sans-serif;padding:24px;">\n'
    f'  <h2 style="margin:0 0 16px;">Stop-loss alert ({n} transition(s))</h2>\n'
    '  <table style="border-collapse:collapse;width:100%;">\n'
    '    <thead>\n'
    '      <tr style="background:#f5f5f5;">'
    '<th style="padding:8px;border:1px solid #ddd;text-align:left;">Trade</th>'
    '<th style="padding:8px;border:1px solid #ddd;text-align:left;">Side</th>'
    '<th style="padding:8px;border:1px solid #ddd;text-align:left;">Entry</th>'
    '<th style="padding:8px;border:1px solid #ddd;text-align:left;">Stop</th>'
    '<th style="padding:8px;border:1px solid #ddd;text-align:left;">Today\'s close</th>'
    '<th style="padding:8px;border:1px solid #ddd;text-align:left;">Distance</th>'
    '<th style="padding:8px;border:1px solid #ddd;text-align:left;">State</th>'
    '</tr>\n'
    '    </thead>\n'
    '    <tbody>\n'
    f'{rows_str}'
    '    </tbody>\n'
    '  </table>\n'
    f'  <p style="margin:16px 0 0;">Dashboard: '
    f'<a href="{esc_url}">{esc_url}</a></p>\n'
    '</body>\n'
    '</html>\n'
  )


def _render_alert_email_text(transitions: list[dict], dashboard_url: str) -> str:
  '''D-02: plain-text fallback for the stop-alert email.

  Same transitions argument as _render_alert_email_html (RESEARCH §Pitfall 2 parity).
  No HTML escaping (text/plain). Every id + new_state appears in the output.
  '''
  n = len(transitions)
  lines = [f'Stop-loss alert ({n} transition(s))', '']
  for t in transitions:
    trade_id  = str(t.get('id', ''))
    side      = str(t.get('side', ''))
    state     = str(t.get('new_state', ''))
    atr_dist  = t.get('atr_distance', 0.0)
    if atr_dist != atr_dist:  # noqa: PLR0124 -- float NaN self-inequality
      dist_label = 'distance unknown'
    else:
      label = 'within trigger' if t.get('new_state') == 'APPROACHING' else 'beyond stop'
      dist_label = f'{atr_dist:.2f} ATR ({label})'
    lines.append(f'{trade_id:<28}  {side:<6}  {state:<12}  {dist_label}')
  lines.append('')
  lines.append(f'Dashboard: {dashboard_url}')
  lines.append('')
  return '\n'.join(lines)
