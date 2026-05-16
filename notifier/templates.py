'''Daily email composition shell + header + hero + footer.

Extracted from notifier.py in Plan 27-12 (notifier package split).

Public templating entry point: `compose_email_body` — composes the
D-07 HTML shell + D-10 7-section body. Per-section renderers split
between this module (header, hero, footer) and templates_sections
(action_required, signal_status, positions, todays_pnl, closed_trades).

XSS posture (preserved): every dynamic value flows through
html.escape(value, quote=True) at leaf render site (Phase 5 D-15).
Inline style='...' on every coloured span — NO CSS classes, NO <style>.

Clock injection (D-01): compose_email_body(state, old_signals, now)
requires a timezone-aware datetime (T-06-04). C-1 reviews (Phase 5):
construct via PERTH.localize(...) — never datetime(..., tzinfo=PERTH).

Crash email redaction (Phase 43 D-01, T-43-01/T-43-02):
  CRASH_EMAIL_STATE_ALLOWLIST — only these top-level state keys may appear
  in a crash email body. All other keys (users, warnings, admin_user_id,
  and any future additions) are excluded by default. ALLOWLIST semantics
  means new state schema keys are denied automatically — no blocklist
  maintenance required.
  _redact_state_for_crash_email(state) — returns a NEW dict containing
  ONLY allowlisted keys. The literal string "[REDACTED]" is added at the
  summary level so operators can distinguish "absent" from "hidden".
'''
import html
from datetime import datetime

from system_params import (
  _COLOR_BG,
  _COLOR_BORDER,
  _COLOR_FLAT,
  _COLOR_SHORT,
  _COLOR_SURFACE,
  _COLOR_TEXT,
  _COLOR_TEXT_DIM,
  _COLOR_TEXT_MUTED,
)

from .formatters import (
  _extract_signal_as_of,
  _fmt_last_updated_email,
)
from .templates_sections import (
  _render_action_required_email,
  _render_closed_trades_email,
  _render_positions_email,
  _render_signal_status_email,
  _render_todays_pnl_email,
)

# Phase 43 D-01: Allowlist for crash-email state serialisation.
# ONLY system-metadata keys. Per-user, credential, and trade keys are
# NEVER added. Unknown/new keys are excluded by default (T-43-02).
CRASH_EMAIL_STATE_ALLOWLIST: frozenset[str] = frozenset({
  'schema_version',
  'last_run',
  'markets',
  'strategy_settings',
  'signals',
})


def _redact_state_for_crash_email(state: dict) -> dict:
  '''Return a NEW dict with ONLY allowlisted top-level keys.

  Excluded keys are replaced at the summary level by a single
  "[REDACTED]" marker so operators can distinguish "absent" from
  "hidden" during debugging (T-43-03 accept: full state never
  belongs in email; operator uses journalctl for forensics).

  Defence-in-depth: any allowlisted value that is itself a dict is
  passed through as-is (current schema has no nested user-scoped
  structures under allowlisted keys). If the schema ever introduces
  nested user substructures under an allowlisted key, add a recursive
  filter at that point — do NOT add user-scoped keys to the allowlist.
  '''
  redacted: dict = {}
  excluded: list[str] = []
  for key, value in state.items():
    if key in CRASH_EMAIL_STATE_ALLOWLIST:
      redacted[key] = value
    else:
      excluded.append(key)
  if excluded:
    redacted['_redacted_keys'] = '[REDACTED]: ' + ', '.join(sorted(excluded))
  return redacted


def _render_hero_card_email(state: dict, now: datetime) -> str:
  '''B4 revision (Phase 8): the existing hero card (Trading Signals h1 +
  subtitle + Last updated + Signal as of) — extracted verbatim from
  pre-edit _render_header_email so the new composing _render_header_email
  can assemble parts=[banner?, hero, routine?].

  Section 1: site title + subtitle + last-updated + signal-as-of (D-10, Fix 6).
  '''
  last_updated = _fmt_last_updated_email(now)
  # Signal-as-of: prefer a single shared value if both instruments match.
  spi_as_of = _extract_signal_as_of(state, 'SPI200')
  audusd_as_of = _extract_signal_as_of(state, 'AUDUSD')
  if spi_as_of is not None and audusd_as_of is not None:
    if spi_as_of == audusd_as_of:
      signal_as_of_line = f'Signal as of {html.escape(spi_as_of, quote=True)}'
    else:
      signal_as_of_line = (
        f'Signal as of {html.escape(spi_as_of, quote=True)} (SPI 200) '
        f'&middot; {html.escape(audusd_as_of, quote=True)} (AUD / USD)'
      )
  elif spi_as_of is not None:
    signal_as_of_line = f'Signal as of {html.escape(spi_as_of, quote=True)} (SPI 200)'
  elif audusd_as_of is not None:
    signal_as_of_line = (
      f'Signal as of {html.escape(audusd_as_of, quote=True)} (AUD / USD)'
    )
  else:
    signal_as_of_line = (
      f'Signal as of <span style="color:{_COLOR_TEXT_DIM}">never</span>'
    )
  return (
    f'<tr><td style="padding:20px 24px;">'
    f'<h1 style="margin:0;font-size:22px;font-weight:600;'
    f'color:{_COLOR_TEXT};line-height:1.2;">Trading Signals</h1>'
    f'<p style="margin:4px 0 8px 0;font-size:14px;color:{_COLOR_TEXT_MUTED};'
    f'line-height:1.5;">'
    f'{html.escape("SPI 200 & AUD/USD mechanical system", quote=True)}</p>'
    f'<p style="margin:0;font-size:12px;color:{_COLOR_TEXT_MUTED};line-height:1.4;">'
    f'<span style="font-weight:600;letter-spacing:0.04em;'
    f'text-transform:uppercase;">Last updated</span>'
    f'&nbsp;&middot;&nbsp;<span>{html.escape(last_updated, quote=True)}</span>'
    f'</p>'
    f'<p style="margin:4px 0 0 0;font-size:14px;'
    f'color:{_COLOR_TEXT_MUTED};line-height:1.5;">{signal_as_of_line}</p>'
    f'</td></tr>\n'
    f'<tr><td height="32" style="height:32px;font-size:0;line-height:0;">'
    f'&nbsp;</td></tr>\n'
  )


def _has_critical_banner(state: dict) -> bool:
  '''D-04 + B2/B3 revisions (Phase 8): True iff state has a critical
  surface — transient `_stale_info` (ERR-05) OR a `state['warnings']`
  entry whose message starts with `'recovered from corruption'` (ERR-03).
  Age filter BYPASSED: corrupt warnings may be tagged with a date other
  than `prior_run_date`; staleness is not even stored in warnings (it is
  a transient runtime key set by orchestrator pre-render).
  '''
  if state.get('_stale_info'):
    return True
  for w in state.get('warnings', []):
    if (
      w.get('source') == 'state_manager'
      and w.get('message', '').startswith('recovered from corruption')
    ):
      return True
    if w.get('source') == 'drift':   # NEW Phase 15 SENTINEL-03
      return True
  return False


def _render_header_email(state: dict, now: datetime) -> str:
  '''D-01 / D-03 / B2 + B3 revisions (Phase 8):

  Composes: [critical banner?] + hero card + [routine row?].

  Critical banner sources (age-filter BYPASSED — always render when present):
    - `state['_stale_info']` (transient dict from orchestrator) — red border
      `_COLOR_SHORT`, label "Stale state", message includes days_stale.
    - `state['warnings']` entry where `source='state_manager'` AND
      `message.startswith('recovered from corruption')` — gold border
      `_COLOR_FLAT`, label "State was reset".

  Routine row source (subject to D-03 age filter):
    `state['warnings']` entries where `w['date'] == prior_run_date` AND not
    matched by the critical classifier above. Compact metadata line +
    stacked list of messages.

  Hero card: delegated to `_render_hero_card_email` (B4 — verbatim extract).

  XSS posture (preserved): every dynamic value flows through
  `html.escape(value, quote=True)` at leaf render site.
  '''
  parts: list[str] = []

  # --- CRITICAL BANNER 1: stale state via transient _stale_info (B3) ---
  stale_info = state.get('_stale_info')
  if stale_info:
    days = stale_info.get('days_stale', 0)
    last_run_date = stale_info.get('last_run_date', 'unknown')
    safe_msg = html.escape(
      f'Last run was {days} days ago ({last_run_date}) — data + signals may be stale',
      quote=True,
    )
    parts.append(
      f'<tr><td style="padding:12px 16px;background:{_COLOR_SURFACE};'
      f'border-left:4px solid {_COLOR_SHORT};'
      f'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\','
      f'Roboto,sans-serif;font-size:14px;color:{_COLOR_TEXT};'
      f'line-height:1.5;">'
      f'<p style="margin:0 0 4px 0;font-size:16px;font-weight:700;'
      f'color:{_COLOR_TEXT};letter-spacing:0.02em;">'
      f'━━━ Stale state ━━━</p>'
      f'<p style="margin:0;color:{_COLOR_TEXT_MUTED};font-size:13px;">'
      f'{safe_msg}</p>'
      f'</td></tr>\n'
      f'<tr><td height="16" style="height:16px;font-size:0;line-height:0;">'
      f'&nbsp;</td></tr>\n'
    )

  # --- CRITICAL BANNER 2: corrupt-reset via warnings prefix (B2 / B3) ---
  # Age-filter BYPASSED: state_manager.load_state appends this warning with
  # TODAY's date at corrupt-recovery time, which is likely NOT equal to
  # prior_run_date (state.json was missing/corrupt and thus has no prior_run).
  corrupt_warnings = [
    w for w in state.get('warnings', [])
    if w.get('source') == 'state_manager'
    and w.get('message', '').startswith('recovered from corruption')
  ]
  for w in corrupt_warnings:
    safe_msg = html.escape(w.get('message', ''), quote=True)
    parts.append(
      f'<tr><td style="padding:12px 16px;background:{_COLOR_SURFACE};'
      f'border-left:4px solid {_COLOR_FLAT};'
      f'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\','
      f'Roboto,sans-serif;font-size:14px;color:{_COLOR_TEXT};'
      f'line-height:1.5;">'
      f'<p style="margin:0 0 4px 0;font-size:16px;font-weight:700;'
      f'color:{_COLOR_TEXT};letter-spacing:0.02em;">'
      f'━━━ State was reset ━━━</p>'
      f'<p style="margin:0;color:{_COLOR_TEXT_MUTED};font-size:13px;">'
      f'{safe_msg}</p>'
      f'</td></tr>\n'
      f'<tr><td height="16" style="height:16px;font-size:0;line-height:0;">'
      f'&nbsp;</td></tr>\n'
    )

  # --- CRITICAL BANNER 3: drift/reversal (Phase 15 D-03/D-12/D-13/SENTINEL-03) ---
  # Border color follows D-13: red (_COLOR_SHORT) when any reversal severity,
  # amber (_COLOR_FLAT) when drift-only. Body bullets reuse DriftEvent.message
  # strings from state['warnings'] — D-12 lockstep parity with the dashboard
  # banner in dashboard._render_drift_banner.
  drift_warnings = [
    w for w in state.get('warnings', [])
    if w.get('source') == 'drift'
  ]
  if drift_warnings:
    has_reversal = any(
      'reversal recommended' in w.get('message', '')
      for w in drift_warnings
    )
    border_color = _COLOR_SHORT if has_reversal else _COLOR_FLAT
    bullet_lines = '<br>\n      '.join(
      f'&bull; {html.escape(w.get("message", ""), quote=True)}'
      for w in drift_warnings
    )
    parts.append(
      f'<tr><td style="padding:12px 16px;background:{_COLOR_SURFACE};'
      f'border-left:4px solid {border_color};'
      f'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\','
      f'Roboto,sans-serif;font-size:14px;color:{_COLOR_TEXT};'
      f'line-height:1.5;">'
      f'<p style="margin:0 0 4px 0;font-size:14px;font-weight:600;'
      f'color:{_COLOR_TEXT};letter-spacing:0.02em;">'
      f'━━━ Drift detected ━━━</p>'
      f'<p style="margin:0;color:{_COLOR_TEXT_MUTED};font-size:13px;line-height:1.6;">'
      f'{bullet_lines}</p>'
      f'</td></tr>\n'
      f'<tr><td height="16" style="height:16px;font-size:0;line-height:0;">'
      f'&nbsp;</td></tr>\n'
    )

  # --- HERO CARD (verbatim from pre-edit function, B4) ---
  parts.append(_render_hero_card_email(state, now))

  # --- ROUTINE ROW: age-filtered non-critical warnings (D-03) ---
  prior_run_date = state.get('last_run')
  if prior_run_date:
    routine = [
      w for w in state.get('warnings', [])
      if w.get('date') == prior_run_date
      and not (
        w.get('source') == 'state_manager'
        and w.get('message', '').startswith('recovered from corruption')
      )
    ]
  else:
    routine = []

  if routine:
    n = len(routine)
    # Plural/singular labels kept as literal substrings so grep audits can
    # locate the routine-row metadata copy in source (D-01 / Phase 8 AC).
    if n == 1:
      label = f'{n} warning from prior run'
    else:
      label = f'{n} warnings from prior run'
    items_html = ''.join(
      f'<div style="margin:4px 0;color:{_COLOR_TEXT_DIM};font-size:12px;">'
      f'&bull; {html.escape(w.get("message", ""), quote=True)}'
      f'</div>'
      for w in routine
    )
    parts.append(
      f'<tr><td style="padding:8px 16px;background:{_COLOR_BG};'
      f'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\','
      f'Roboto,sans-serif;font-size:12px;color:{_COLOR_TEXT_MUTED};">'
      f'<div>{label}</div>'
      f'{items_html}'
      f'</td></tr>\n'
      f'<tr><td height="16" style="height:16px;font-size:0;line-height:0;">'
      f'&nbsp;</td></tr>\n'
    )

  return ''.join(parts)


def _render_footer_email(
  state: dict, now: datetime, from_addr: str,
) -> str:  # noqa: ARG001
  '''Section 7: footer disclaimer + sender + run-date (D-10).

  state arg reserved for future use (e.g. schema_version surfacing).
  Phase 12 (D-16): from_addr threaded in from compose_email_body →
  send_daily_email's per-dispatch env-var read (D-15). The old
  module-level sender constant was removed.
  '''
  run_date_iso = now.strftime('%Y-%m-%d')
  return (
    f'<tr><td style="padding:20px 24px;text-align:center;">'
    f'<p style="margin:0 0 4px;font-size:12px;color:{_COLOR_TEXT_DIM};'
    f'line-height:1.4;">Signal-only system. Not financial advice.</p>'
    f'<p style="margin:0 0 4px;font-size:12px;color:{_COLOR_TEXT_DIM};'
    f'line-height:1.4;">Trading Signals — sent by '
    f'{html.escape(from_addr, quote=True)}</p>'
    f'<p style="margin:0;font-size:12px;color:{_COLOR_TEXT_DIM};'
    f'line-height:1.4;">Run date: {html.escape(run_date_iso, quote=True)}</p>'
    f'</td></tr>\n'
  )


def compose_email_body(
  state: dict,
  old_signals: dict,
  now: datetime,
  *,
  from_addr: str,
) -> str:
  '''D-07 HTML shell + D-10 7-section body (NOTF-03/04/06/09).

  - Inline CSS only; NO <style>; NO CSS classes; NO @media query.
  - role="presentation" on layout tables (D-07 accessibility).
  - bgcolor attributes alongside inline style (D-07 Outlook redundancy).
  - max-width:600px;width:100% fluid-hybrid (D-08).
  - Full <meta> tag suite for Gmail + iOS Mail (RESEARCH §2).
  - Every state-derived string escaped via html.escape(value, quote=True)
    at leaf interpolation (NOTF-09; Phase 5 D-15 leaf discipline).
  - Raw Unicode → (U+2192) in ACTION REQUIRED per Fix 5 — never &rarr;.
  - Clock injection: uses now= parameter; must be tz-aware (T-06-04).

  Phase 12 (D-16): `from_addr` is a KEYWORD-ONLY argument (no default)
  threaded to _render_footer_email so the rendered footer's sender
  address is driven by send_daily_email's env-var read (D-15). The
  "no default" is deliberate — makes signature drift fail loudly
  (RESEARCH §Pattern 2).
  '''
  # Belt-and-braces naive-datetime rejection (T-06-04) — also enforced
  # inside _fmt_last_updated_email but surface the error at the top
  # call site for clearer traces.
  if now.tzinfo is None:
    raise ValueError(
      f'compose_email_body requires a timezone-aware datetime; '
      f'got naive datetime={now!r}'
    )
  run_date_iso = now.strftime('%Y-%m-%d')

  sections = (
    _render_header_email(state, now)
    + _render_action_required_email(state, old_signals, run_date_iso)
    + _render_signal_status_email(state)
    + _render_positions_email(state)
    + _render_todays_pnl_email(state)
    + _render_closed_trades_email(state)
    + _render_footer_email(state, now, from_addr)
  )

  return (
    f'<!DOCTYPE html>\n'
    f'<html lang="en">\n'
    f'<head>\n'
    f'<meta charset="utf-8">\n'
    f'<meta name="viewport" content="width=device-width, initial-scale=1">\n'
    f'<meta name="color-scheme" content="dark only">\n'
    f'<meta name="supported-color-schemes" content="dark">\n'
    f'<meta name="x-apple-disable-message-reformatting">\n'
    f'<meta name="format-detection" content="telephone=no,date=no,'
    f'address=no,email=no">\n'
    f'<title>Trading Signals &mdash; {html.escape(run_date_iso, quote=True)}'
    f'</title>\n'
    f'</head>\n'
    f'<body style="margin:0;padding:0;background:{_COLOR_BG};'
    f'color:{_COLOR_TEXT};font-family:-apple-system,BlinkMacSystemFont,'
    f'\'Segoe UI\',Roboto,sans-serif;">\n'
    f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
    f'width="100%" bgcolor="{_COLOR_BG}" style="background:{_COLOR_BG};">\n'
    f'<tr><td align="center" style="padding:16px 8px;">\n'
    f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
    f'width="100%" bgcolor="{_COLOR_SURFACE}" '
    f'style="max-width:600px;width:100%;background:{_COLOR_SURFACE};'
    f'border:1px solid {_COLOR_BORDER};">\n'
    f'{sections}'
    f'</table>\n'
    f'</td></tr>\n'
    f'</table>\n'
    f'</body>\n'
    f'</html>\n'
  )
