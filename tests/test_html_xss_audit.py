'''Phase 27 Plan 27-08: HTML escape audit — XSS regression + anti-double-escape.

Per 27-08 render-variable taxonomy:
  (a) Untrusted text (state['warnings'], paper-trade fields from yfinance/operator
      input, Resend error body) → MUST be escaped via html.escape(value, quote=True).
  (b) Trusted HTML fragment (render_status_strip output, render_signal_card output,
      any render_*() return value) → MUST NOT be re-escaped (anti-double-escape).
  (c) Trusted constant (STRATEGY_VERSION, hardcoded class names) → no action needed.

Threat register (T-27-08-01..03):
  T-27-08-01 — yfinance ticker / state warning carries `<script>` → reaches
              dashboard or email un-escaped.
  T-27-08-02 — selected_market cookie bypasses regex validation → renderer
              receives a hostile market_id.
  T-27-08-03 — Mechanical bulk-escape introduces double-escape on trusted
              fragments (render_status_strip output) → broken page.

These tests assert all three threats are mitigated.
'''
import html
import re
from datetime import datetime

import pytest
import pytz

from dashboard_renderer.components.positions import _render_drift_banner
from dashboard_renderer.components.paper_trades import (
  _render_paper_trades_closed,
  _render_paper_trades_open,
)
from dashboard_renderer.components.header import (
  render_header,
  render_status_strip,
)
from dashboard_renderer.components.nav import render_market_strip
from dashboard_renderer.components.settings import render_settings_tab
from dashboard_renderer.components.signals import render_signal_cards
from dashboard_renderer.components.trades import render_trades_table
from notifier import compose_email_body

PERTH = pytz.timezone('Australia/Perth')
NOW_AWST = PERTH.localize(datetime(2026, 5, 8, 9, 0))

# Canonical XSS payloads — if any of these survive un-escaped, the renderer
# is vulnerable.
XSS_SCRIPT = '<script>alert(1)</script>'
XSS_IMG = '<img src=x onerror=alert(1)>'
XSS_ATTR = '" onerror="alert(1)'

# Expected escaped forms (html.escape with quote=True).
ESC_SCRIPT = html.escape(XSS_SCRIPT, quote=True)
ESC_IMG = html.escape(XSS_IMG, quote=True)
ESC_ATTR = html.escape(XSS_ATTR, quote=True)


def _assert_no_raw_xss(out: str, payload: str, where: str) -> None:
  '''Strict assertion: payload must NOT appear raw in the output.'''
  assert payload not in out, (
    f'XSS payload {payload!r} survived raw in {where}; '
    f'output excerpt: {out[:200]!r}'
  )


def _assert_escaped(out: str, escaped: str, where: str) -> None:
  '''Strict assertion: escaped form MUST appear in the output.'''
  assert escaped in out, (
    f'expected escaped form {escaped!r} not found in {where}; '
    f'output excerpt: {out[:200]!r}'
  )


# ---------------------------------------------------------------------------
# Class (a) — Untrusted text MUST be escaped. T-27-08-01.
# ---------------------------------------------------------------------------


class TestXssUntrustedTextEscaped:
  '''XSS regression — every external-source text field must escape on render.'''

  def test_xss_warning_field_escaped(self) -> None:
    '''state['warnings'][i].message can carry yfinance error text → escaped.'''
    state = {
      'warnings': [
        {'source': 'drift',
         'message': f'You hold LONG SPI200 — {XSS_SCRIPT}',
         'date': '2026-05-08'}
      ]
    }
    out = _render_drift_banner(state)
    _assert_no_raw_xss(out, XSS_SCRIPT, '_render_drift_banner')
    _assert_escaped(out, ESC_SCRIPT, '_render_drift_banner')

  def test_xss_paper_trade_open_instrument_escaped(self) -> None:
    '''paper_trade.instrument flows from POST body → escaped on render.'''
    paper_trades = [
      {
        'id': 'pt-001',
        'status': 'open',
        'instrument': XSS_IMG,
        'side': 'LONG',
        'entry_price': 100.0,
        'contracts': 1,
        'stop_price': None,
        'entry_cost_aud': 0.0,
      }
    ]
    out = _render_paper_trades_open(paper_trades=paper_trades, signals={})
    _assert_no_raw_xss(out, XSS_IMG, '_render_paper_trades_open(instrument)')
    _assert_escaped(out, ESC_IMG, '_render_paper_trades_open(instrument)')

  def test_xss_paper_trade_open_side_escaped(self) -> None:
    '''paper_trade.side flows from POST body → escaped on render.'''
    paper_trades = [
      {
        'id': 'pt-001',
        'status': 'open',
        'instrument': 'SPI200',
        'side': XSS_SCRIPT,
        'entry_price': 100.0,
        'contracts': 1,
        'stop_price': None,
        'entry_cost_aud': 0.0,
      }
    ]
    out = _render_paper_trades_open(paper_trades=paper_trades, signals={})
    _assert_no_raw_xss(out, XSS_SCRIPT, '_render_paper_trades_open(side)')
    _assert_escaped(out, ESC_SCRIPT, '_render_paper_trades_open(side)')

  def test_xss_paper_trade_closed_instrument_escaped(self) -> None:
    '''paper_trade closed row instrument also escaped.'''
    paper_trades = [
      {
        'id': 'pt-002',
        'status': 'closed',
        'instrument': XSS_IMG,
        'side': 'LONG',
        'entry_price': 100.0,
        'exit_price': 110.0,
        'exit_dt': '2026-05-08',
        'realised_pnl': 50.0,
      }
    ]
    out = _render_paper_trades_closed(paper_trades=paper_trades)
    _assert_no_raw_xss(out, XSS_IMG, '_render_paper_trades_closed(instrument)')
    _assert_escaped(out, ESC_IMG, '_render_paper_trades_closed(instrument)')

  def test_xss_market_id_escaped_in_market_strip(self) -> None:
    '''selected_market / market_id reaches render_market_strip → escaped.

    T-27-08-02: defense-in-depth even though regex-validated upstream.
    '''
    state = {'markets': {XSS_ATTR: {'display_name': 'evil'}}}
    out = render_market_strip(state, active_market='', active_function='signals')
    _assert_no_raw_xss(out, XSS_ATTR, 'render_market_strip')
    # html.escape with quote=True turns " into &quot;
    assert '&quot;' in out, f'quote not escaped; out={out[:300]!r}'

  def test_xss_signal_as_of_escaped(self) -> None:
    '''signal_as_of from state.json → escaped through render_signal_cards.'''
    state = {
      'last_run': '2026-05-08',
      'markets': {'SPI200': {'display_name': 'SPI 200'}},
      'signals': {
        'SPI200': {
          'signal': 1,
          'signal_as_of': XSS_SCRIPT,
          'last_close': 100.0,
        }
      },
    }
    out = render_signal_cards(state, active_market='SPI200')
    _assert_no_raw_xss(out, XSS_SCRIPT, 'render_signal_cards(signal_as_of)')
    _assert_escaped(out, ESC_SCRIPT, 'render_signal_cards(signal_as_of)')

  def test_xss_warning_field_escaped_in_email(self) -> None:
    '''Notifier email body — drift warning with XSS payload → escaped.

    Smoke test that Phase 6 D-10 escape coverage hasn't regressed.
    '''
    state = {
      'last_run': '2026-05-08',
      'account': 100000.0,
      'initial_account': 100000.0,
      'positions': {},
      'signals': {
        '^AXJO': {'signal': 0, 'signal_as_of': '2026-05-08', 'last_close': 7000.0},
        'AUDUSD=X': {'signal': 0, 'signal_as_of': '2026-05-08', 'last_close': 0.65},
      },
      'warnings': [
        {'source': 'drift',
         'message': f'attack: {XSS_SCRIPT}',
         'date': '2026-05-08'}
      ],
      'trade_log': [],
      'equity_history': [],
    }
    body = compose_email_body(
      state, {'^AXJO': 0, 'AUDUSD=X': 0}, NOW_AWST,
      from_addr='signals@carbonbookkeeping.com.au',
    )
    _assert_no_raw_xss(body, XSS_SCRIPT, 'compose_email_body(warning)')
    _assert_escaped(body, ESC_SCRIPT, 'compose_email_body(warning)')


# ---------------------------------------------------------------------------
# Class (b) — Trusted HTML fragments MUST NOT be double-escaped. T-27-08-03.
# ---------------------------------------------------------------------------


class TestAntiDoubleEscape:
  '''Anti-double-escape — trusted render_*() output composed into pages stays raw.'''

  def test_status_strip_output_not_double_escaped_in_header(self) -> None:
    '''render_status_strip returns trusted HTML; render_header composes it raw.

    If render_header ran the strip output through html.escape, every < would
    appear as &lt; — page would be visibly broken.
    '''
    state = {'last_run': '2026-05-08', 'warnings': []}
    out = render_header(state, NOW_AWST)
    # Trusted markers from render_status_strip must remain RAW.
    assert '<div id="status-strip"' in out, (
      f'render_status_strip output appears double-escaped or missing in header; '
      f'out excerpt: {out[:400]!r}'
    )
    assert '&lt;div id=&quot;status-strip&quot;' not in out, (
      'status-strip fragment was double-escaped'
    )
    assert '<span class="status-dot' in out
    assert '&lt;span class=&quot;status-dot' not in out

  def test_signal_card_html_not_double_escaped(self) -> None:
    '''render_signal_cards returns trusted HTML — markers stay raw.'''
    state = {
      'last_run': '2026-05-08',
      'markets': {'SPI200': {'display_name': 'SPI 200'}},
      'signals': {
        'SPI200': {
          'signal': 1,
          'signal_as_of': '2026-05-08',
          'last_close': 100.0,
          'last_scalars': {'adx': 25.0, 'mom1': 0.05, 'mom3': 0.02,
                            'mom12': 0.01, 'rvol': 1.0},
        }
      },
    }
    out = render_signal_cards(state, active_market='SPI200')
    # Hardcoded class names are trusted constants and must remain raw <span>.
    assert '<article class="card">' in out, (
      f'<article> tag not raw in render_signal_cards output; '
      f'out excerpt: {out[:300]!r}'
    )
    assert '&lt;article' not in out
    assert '<p class="eyebrow">' in out
    assert '&lt;p class=' not in out

  def test_settings_tab_form_not_double_escaped(self) -> None:
    '''render_settings_tab — <form>/<fieldset>/<input> tags stay raw.'''
    state = {
      'markets': {'SPI200': {'display_name': 'SPI 200'}},
      'strategy_settings': {
        'SPI200': {
          'adx_gate': 25.0, 'momentum_votes_required': 2,
          'trail_mult_long': 1.5, 'trail_mult_short': 1.5,
          'risk_pct_long': 0.01, 'risk_pct_short': 0.005,
          'contract_cap': 3, 'one_contract_floor': False,
          'direction_mode': 'both',
        }
      },
    }
    out = render_settings_tab(state, active_market='SPI200')
    assert '<form hx-patch="/markets/settings"' in out
    assert '&lt;form hx-patch' not in out

  def test_drift_banner_trusted_wrapper_not_double_escaped(self) -> None:
    '''_render_drift_banner — outer <div class="sentinel-banner ..."> stays raw.

    Only the message body inside <li> is escaped; the wrapper structure isn't.
    '''
    state = {
      'warnings': [
        {'source': 'drift', 'message': 'plain text', 'date': '2026-05-08'}
      ]
    }
    out = _render_drift_banner(state)
    assert '<div class="sentinel-banner' in out
    assert '&lt;div class=' not in out
    assert '<ul class="sentinel-body">' in out


# ---------------------------------------------------------------------------
# Coverage-stability gate — Phase 6 D-10 escape pattern in notifier package
# preserved (count of html.escape call sites doesn't regress).
# ---------------------------------------------------------------------------


class TestNotifierEscapeCoverageStable:
  '''Plan 27-08 must_haves: notifier package existing escape coverage REUSED, not parallel.

  Pre-Phase-27 baseline: 79 inline html.escape(value, quote=True) call sites.
  This test pins the floor; if a future refactor drops escape calls, the
  test fails loudly and the dropper must justify in the PR.
  '''

  def test_notifier_html_escape_count_at_or_above_baseline(self) -> None:
    from pathlib import Path
    pkg = Path('notifier')
    count = sum(
      len(re.findall(r'html\.escape\(', p.read_text()))
      for p in pkg.glob('*.py')
    )
    # Phase 6 D-10 baseline: 69 active call sites (Phase 27 inspection
    # 2026-05-08; the prior grep of 79 included docstring/comment text).
    # Allow growth, never shrinkage. Aggregated across notifier/*.py
    # post-Plan 27-12 split (CR-01 fix).
    assert count >= 69, (
      f'notifier package html.escape count regressed: {count} < 69. '
      f'Phase 6 D-10 escape coverage must be preserved.'
    )

  def test_no_parallel_e_helper_introduced(self) -> None:
    '''Plan 27-08 must_haves truth #6: no `_e` alias parallel to html.escape.

    The canonical helper IS html.escape — adding a wrapper would split the
    convention. Reject any `def _e(` or `def _escape(` definition that
    leaks through.
    '''
    from pathlib import Path
    pkg_files = list(Path('notifier').glob('*.py'))
    for p in pkg_files + [
      Path('dashboard.py'),
      Path('dashboard_renderer/components/footer.py'),
      Path('dashboard_renderer/components/header.py'),
      Path('dashboard_renderer/components/nav.py'),
      Path('dashboard_renderer/components/paper_trades.py'),
      Path('dashboard_renderer/components/positions.py'),
      Path('dashboard_renderer/components/settings.py'),
      Path('dashboard_renderer/components/signals.py'),
      Path('dashboard_renderer/components/trades.py'),
    ]:
      if not p.exists():
        continue
      src = p.read_text()
      assert not re.search(r'^def _e\(', src, re.MULTILINE), (
        f'{p}: parallel _e() helper found — must reuse html.escape direct call '
        f'(Plan 27-08 must_haves truth #6).'
      )
      assert not re.search(r'^def _escape\(', src, re.MULTILINE), (
        f'{p}: parallel _escape() helper found — must reuse html.escape direct.'
      )


# ---------------------------------------------------------------------------
# Source-level grep gate — every html.escape() call in dashboard.py +
# dashboard_renderer/components/*.py uses quote=True (attribute-context safe).
# ---------------------------------------------------------------------------


class TestEscapeQuoteTrueGate:
  '''Every html.escape() call must use quote=True per Phase 6 D-10 contract.

  Without quote=True, attribute-context interpolations (e.g.,
  `<td title="{escaped}">`) remain XSS-vulnerable to `"` payloads.
  '''

  @pytest.mark.parametrize('relpath', [
    'dashboard.py',
    'dashboard_renderer/components/footer.py',
    'dashboard_renderer/components/header.py',
    'dashboard_renderer/components/nav.py',
    'dashboard_renderer/components/positions.py',
    'dashboard_renderer/components/settings.py',
    'dashboard_renderer/components/signals.py',
    'dashboard_renderer/components/trades.py',
    'dashboard_renderer/shell.py',
    'dashboard_renderer/formatters.py',
  ])
  def test_html_escape_uses_quote_true(self, relpath: str) -> None:
    '''AST-walk every Call node where func is `html.escape` and assert
    `quote=True` is in the keywords. AST naturally skips docstring
    matches (those are str literals, not Call nodes).
    '''
    import ast
    from pathlib import Path
    p = Path(relpath)
    if not p.exists():
      pytest.skip(f'{relpath} not found')
    src = p.read_text()
    tree = ast.parse(src)
    bad: list[tuple[int, str]] = []
    for node in ast.walk(tree):
      if not isinstance(node, ast.Call):
        continue
      func = node.func
      # Match html.escape(...) — ast.Attribute(value=Name('html'), attr='escape').
      if not (
        isinstance(func, ast.Attribute)
        and func.attr == 'escape'
        and isinstance(func.value, ast.Name)
        and func.value.id == 'html'
      ):
        continue
      kwarg_names = {kw.arg for kw in node.keywords if kw.arg is not None}
      if 'quote' not in kwarg_names:
        # Take the source line for the diagnostic message.
        line = src.splitlines()[node.lineno - 1].strip()
        bad.append((node.lineno, line))
        continue
      # Find the quote keyword and verify its value is True.
      for kw in node.keywords:
        if kw.arg == 'quote':
          val = kw.value
          if not (isinstance(val, ast.Constant) and val.value is True):
            line = src.splitlines()[node.lineno - 1].strip()
            bad.append((node.lineno, line))
          break
    assert not bad, (
      f'{relpath}: html.escape() without quote=True at lines '
      f'{[ln for ln, _ in bad]} — attribute-context XSS vector. '
      f'Phase 6 D-10 contract requires quote=True at every leaf escape.'
    )
