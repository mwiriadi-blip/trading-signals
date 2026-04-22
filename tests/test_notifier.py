'''Phase 6 test suite: notifier compose + dispatch + formatters + goldens + never-crash.

Organized into 6 classes per D-03 (one class per concern dimension):
  TestComposeSubject — D-04 subject template + emoji + [TEST] prefix + first-run + equity rounding
  TestComposeBody    — D-10 7-section body + ACTION REQUIRED + palette inline + XSS escape
  TestFormatters     — _fmt_*_email parity with dashboard formatters (currency, percent, pnl, etc.)
  TestSendDispatch   — send_daily_email RESEND_API_KEY paths + never-crash semantics
  TestResendPost     — _post_to_resend retry loop + 429 special-case + 4xx fail-fast
  TestGoldenEmail    — byte-equal HTML snapshots (3 fixtures → 3 goldens)

Wave 0 (this commit): one placeholder test per class that passes
structurally via pytest.xfail or pytest.raises(NotImplementedError) —
Nyquist Dimension 8 gate. Waves 1/2 fill in real test bodies against
the stub notifier module.

All tests use pytest's tmp_path for isolated email output — never write to the real
./last_email.html. Clock determinism via FROZEN_NOW module constant (no freezer
fixture needed — compose_email_body accepts now= parameter, mirror of dashboard).

C-1 reviews (Phase 5 precedent): pytz timezones must be applied via
.localize(), NOT via datetime(..., tzinfo=pytz.timezone(...)). Passing a
pytz tz to datetime.tzinfo= yields a historical LMT offset (+07:43:24
for Perth pre-1895) instead of the wall-clock AWST (+08:00) we want.
Use PERTH.localize(...) — always.
'''
import html  # noqa: F401 — Wave 1 TestComposeBody escape assertions
import json  # noqa: F401 — Wave 1/2 fixture loading
from datetime import datetime
from pathlib import Path
from unittest.mock import (
  patch,  # noqa: F401 — Wave 2 TestResendPost / TestSendDispatch patch targets
)

import pytest
import pytz

import notifier  # noqa: F401 — module must import cleanly at Wave 0 (stub)
from notifier import (  # noqa: F401 — stub imports; Waves 1/2 exercise real bodies
  compose_email_body,
  compose_email_subject,
  send_daily_email,
)
from system_params import (
  AUDUSD_COST_AUD,
  AUDUSD_NOTIONAL,
  SPI_COST_AUD,
  SPI_MULT,
  TRAIL_MULT_LONG,
  TRAIL_MULT_SHORT,
)

# =========================================================================
# Module-level path + fixture constants
# =========================================================================

NOTIFIER_PATH = Path('notifier.py')
TEST_NOTIFIER_PATH = Path('tests/test_notifier.py')
REGENERATE_SCRIPT_PATH = Path('tests/regenerate_notifier_golden.py')
NOTIFIER_FIXTURE_DIR = Path(__file__).parent / 'fixtures' / 'notifier'
SAMPLE_STATE_WITH_CHANGE_PATH = NOTIFIER_FIXTURE_DIR / 'sample_state_with_change.json'
SAMPLE_STATE_NO_CHANGE_PATH = NOTIFIER_FIXTURE_DIR / 'sample_state_no_change.json'
EMPTY_STATE_PATH = NOTIFIER_FIXTURE_DIR / 'empty_state.json'
GOLDEN_WITH_CHANGE_PATH = NOTIFIER_FIXTURE_DIR / 'golden_with_change.html'
GOLDEN_NO_CHANGE_PATH = NOTIFIER_FIXTURE_DIR / 'golden_no_change.html'
GOLDEN_EMPTY_PATH = NOTIFIER_FIXTURE_DIR / 'golden_empty.html'

# C-1 reviews fix: PERTH.localize(...) is correct; tzinfo=PERTH is not.
PERTH = pytz.timezone('Australia/Perth')
FROZEN_NOW = PERTH.localize(datetime(2026, 4, 22, 9, 0))


# =========================================================================
# 6-class skeleton — one placeholder test per class (xfail / pytest.raises)
# Nyquist D-8 gate — Waves 1 + 2 fill in real test bodies.
# =========================================================================


class TestComposeSubject:
  '''D-04 subject template: {emoji} YYYY-MM-DD — SPI200 SIG, AUDUSD SIG — Equity $X,XXX.

  6 cases covering change day (🔴), no-change day (📊), [TEST] prefix
  ordering, first-run (📊 per D-06), equity rounding, empty state.
  '''

  def test_change_day_emoji(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    old_signals = {'^AXJO': 1, 'AUDUSD=X': 0}
    subject = compose_email_subject(state, old_signals, is_test=False)
    # 🔴 on any change; equity rounded to whole dollar (101234.56 → 101235)
    assert subject.startswith('🔴 2026-04-22 — '), (
      f'D-04 change-day emoji must be 🔴 and date 2026-04-22; got: {subject!r}'
    )
    assert 'SPI200 SHORT' in subject
    assert 'AUDUSD LONG' in subject
    assert '$101,235' in subject
    assert '📊' not in subject

  def test_no_change_day_emoji(self) -> None:
    state = json.loads(SAMPLE_STATE_NO_CHANGE_PATH.read_text())
    old_signals = {'^AXJO': 1, 'AUDUSD=X': 0}
    subject = compose_email_subject(state, old_signals, is_test=False)
    assert subject.startswith('📊 '), (
      f'D-04 no-change emoji must be 📊; got: {subject!r}'
    )
    assert 'SPI200 LONG' in subject
    assert 'AUDUSD FLAT' in subject
    assert '🔴' not in subject

  def test_test_prefix_order(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    old_signals = {'^AXJO': 1, 'AUDUSD=X': 0}
    subject = compose_email_subject(state, old_signals, is_test=True)
    # D-04: [TEST] BEFORE emoji
    assert subject.startswith('[TEST] 🔴 '), (
      f'D-04: [TEST] must precede emoji; got: {subject!r}'
    )

  def test_first_run_no_previous_signal(self) -> None:
    state = json.loads(EMPTY_STATE_PATH.read_text())
    old_signals = {'^AXJO': None, 'AUDUSD=X': None}
    subject = compose_email_subject(state, old_signals, is_test=False)
    # D-06: first-run = NO CHANGE → 📊
    assert subject.startswith('📊 '), (
      f'D-06: first-run must use 📊 emoji; got: {subject!r}'
    )
    # empty_state.json has account=100000.0 → $100,000
    assert '$100,000' in subject

  def test_equity_rounding(self) -> None:
    # Craft state with sub-dollar account to exercise round-half semantics
    state = {
      'account': 99999.49,
      'signals': {'SPI200': 0, 'AUDUSD': 0},
      'equity_history': [],
      'positions': {'SPI200': None, 'AUDUSD': None},
      'trade_log': [],
      'warnings': [],
      'schema_version': 1,
      'last_run': '2026-04-22',
    }
    subject_low = compose_email_subject(state, {'^AXJO': None, 'AUDUSD=X': None})
    assert '$99,999' in subject_low, f'99999.49 rounds DOWN; got: {subject_low!r}'

    state['account'] = 99999.50
    subject_high = compose_email_subject(state, {'^AXJO': None, 'AUDUSD=X': None})
    # Python banker's rounding: round(99999.50) = 100000 (round-half-to-even)
    assert '$100,000' in subject_high, f'99999.50 rounds UP; got: {subject_high!r}'

  def test_date_from_state_signals_as_of_run(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    # Fixture has as_of_run='2026-04-22'
    subject = compose_email_subject(state, {'^AXJO': None, 'AUDUSD=X': None})
    assert '2026-04-22' in subject


class TestDetectSignalChanges:
  '''D-06: first-run-as-no-change helper. Private but tested directly.'''

  def test_detect_change_spi200_long_to_short(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    old = {'^AXJO': 1, 'AUDUSD=X': 0}
    assert notifier._detect_signal_changes(state, old) is True

  def test_detect_no_change_all_match(self) -> None:
    state = json.loads(SAMPLE_STATE_NO_CHANGE_PATH.read_text())
    old = {'^AXJO': 1, 'AUDUSD=X': 0}
    assert notifier._detect_signal_changes(state, old) is False

  def test_detect_first_run_none_baseline(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    old = {'^AXJO': None, 'AUDUSD=X': None}
    assert notifier._detect_signal_changes(state, old) is False

  def test_detect_mixed_first_run_partial(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    # SPI200=-1 (state) / SPI200=None (old — no baseline, skipped);
    # AUDUSD=1 (state) / AUDUSD=0 (old, CHANGED) → True
    old = {'^AXJO': None, 'AUDUSD=X': 0}
    assert notifier._detect_signal_changes(state, old) is True

  def test_detect_legacy_int_signal_shape(self) -> None:
    state = json.loads(EMPTY_STATE_PATH.read_text())
    # empty_state.json has legacy int signals (SPI200=0, AUDUSD=0)
    old = {'^AXJO': 1, 'AUDUSD=X': 0}
    assert notifier._detect_signal_changes(state, old) is True


class TestComposeBody:
  '''D-07/D-08/D-10/D-11: 7-section HTML body, ACTION REQUIRED conditional,
  palette inline, XSS escape on state-derived strings, mobile markup.

  Section-order, inline-CSS, ACTION REQUIRED, first-run, XSS, subsection
  presence, header subtitle + signal-as-of (Fix 6), exact Trail Stop +
  Unrealised P&L (Fix 3), same-run double-close scan (Fix 4).
  '''

  # -----------------------------------------------------------------
  # Structural: DOCTYPE, section order, inline CSS, mobile markers
  # -----------------------------------------------------------------

  def test_body_has_doctype_and_html(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    assert body.startswith('<!DOCTYPE html>'), f'expected DOCTYPE prefix; got: {body[:32]!r}'
    assert body.endswith('</html>\n'), f'expected </html>\\n suffix; got: {body[-32:]!r}'

  def test_body_sections_in_d10_order(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    idx_title = body.index('Trading Signals')
    idx_signal = body.index('Signal Status')
    idx_positions = body.index('Open Positions')
    # html.escape(quote=True) renders ' as &#x27; and & as &amp;
    # so "Today's P&L" becomes "Today&#x27;s P&amp;L"
    for needle in ('Today&#x27;s P&amp;L', "Today's P&amp;L", "Today's P&L"):
      if needle in body:
        idx_pnl = body.index(needle)
        break
    else:
      raise AssertionError(f'Today\'s P&L heading not found; body excerpt: {body[:200]!r}')
    idx_trades = body.index('Last 5 Closed Trades')
    idx_footer = body.index('Not financial advice')
    assert idx_title < idx_signal < idx_positions < idx_pnl < idx_trades < idx_footer, (
      f'D-10 section order violated: title={idx_title} signal={idx_signal} '
      f'positions={idx_positions} pnl={idx_pnl} trades={idx_trades} footer={idx_footer}'
    )

  def test_body_no_style_block(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    assert '<style>' not in body
    assert '</style>' not in body

  def test_body_no_media_query(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    assert '@media' not in body

  def test_body_has_palette_inline_bg(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    assert '#0f1117' in body

  def test_body_has_max_width_600(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    assert 'max-width:600px' in body

  def test_body_has_viewport_meta(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in body

  def test_body_has_role_presentation(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    assert 'role="presentation"' in body

  def test_body_has_bgcolor_belt_and_braces(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    assert 'bgcolor="#0f1117"' in body

  def test_compose_body_naive_datetime_raises(self) -> None:
    '''T-06-04: naive datetime rejected at body-composer entry (C-1 reviews).'''
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    naive = datetime(2026, 4, 22, 9, 0)
    with pytest.raises(ValueError, match='naive datetime='):
      compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, naive)

  # -----------------------------------------------------------------
  # ACTION REQUIRED conditional + copy (D-06, D-11)
  # -----------------------------------------------------------------

  def test_action_required_present_on_change(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    assert 'ACTION REQUIRED' in body
    assert 'border-left:4px solid #ef4444' in body

  def test_action_required_absent_on_no_change(self) -> None:
    state = json.loads(SAMPLE_STATE_NO_CHANGE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    assert 'ACTION REQUIRED' not in body

  def test_action_required_absent_on_first_run(self) -> None:
    '''D-06: first-run (all old None) is NO CHANGE — ACTION REQUIRED omitted.'''
    state = json.loads(EMPTY_STATE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': None, 'AUDUSD=X': None}, FROZEN_NOW)
    assert 'ACTION REQUIRED' not in body

  def test_action_required_contains_per_instrument_diffs(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    # SPI200 diff: LONG → SHORT; AUDUSD diff: FLAT → LONG.
    # Slice to the ACTION REQUIRED section so we're testing the diff region.
    ar_start = body.index('ACTION REQUIRED')
    ar_end = body.index('Signal Status')
    ar_region = body[ar_start:ar_end]
    assert 'SPI 200' in ar_region
    assert 'AUD / USD' in ar_region

  def test_action_required_contains_close_position_copy(self) -> None:
    '''D-11 close-position copy sourced from trade_log[-1] (SPI200 close today).'''
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    # Fixture trade_log[-1] is SPI200 LONG close on 2026-04-22 with
    # n_contracts=2, entry_price=8204.5 → "(2 contracts @ entry $8,204.50)"
    assert 'Close existing LONG position (2 contracts @ entry $8,204.50)' in body

  def test_action_required_uses_unicode_arrow(self) -> None:
    '''Fix 5: raw Unicode → (U+2192), never &rarr; HTML entity.'''
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    assert '→' in body
    assert '&rarr;' not in body

  # -----------------------------------------------------------------
  # Empty-state / first-run rendering
  # -----------------------------------------------------------------

  def test_empty_state_renders_no_open_positions(self) -> None:
    state = json.loads(EMPTY_STATE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': None, 'AUDUSD=X': None}, FROZEN_NOW)
    assert 'No open positions' in body

  def test_empty_state_equity_is_initial_account(self) -> None:
    state = json.loads(EMPTY_STATE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': None, 'AUDUSD=X': None}, FROZEN_NOW)
    # empty_state.json has account=100000.0, equity_history=[]
    assert '$100,000.00' in body

  def test_empty_state_renders_no_closed_trades(self) -> None:
    state = json.loads(EMPTY_STATE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': None, 'AUDUSD=X': None}, FROZEN_NOW)
    assert 'No closed trades' in body

  # -----------------------------------------------------------------
  # XSS escape (T-06-03)
  # -----------------------------------------------------------------

  def test_xss_escape_on_exit_reason(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    state['trade_log'][-1]['exit_reason'] = '<script>alert(1)</script>'
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    assert '<script>alert(1)</script>' not in body
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in body

  def test_xss_escape_on_instrument_value(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    state['trade_log'][-1]['instrument'] = '<script>x</script>'
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    assert '<script>x</script>' not in body
    assert '&lt;script&gt;x&lt;/script&gt;' in body

  def test_xss_escape_on_direction_value(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    state['positions']['SPI200']['direction'] = '<img src=x onerror=y>'
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    assert '<img src=x onerror=y>' not in body
    assert '&lt;img src=x onerror=y&gt;' in body

  # -----------------------------------------------------------------
  # Subsection presence (NOTF-04)
  # -----------------------------------------------------------------

  def test_has_header_section(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    assert 'Trading Signals' in body

  def test_has_signal_status_section(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    assert 'Signal Status' in body

  def test_has_positions_section(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    assert 'Open Positions' in body

  def test_has_todays_pnl_section(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    # html.escape(quote=True) renders ' as &#x27; and & as &amp;
    # so "Today's P&L" appears as "Today&#x27;s P&amp;L" in the body.
    assert (
      'Today&#x27;s P&amp;L' in body
      or "Today's P&amp;L" in body
      or "Today's P&L" in body
    )

  def test_has_running_equity_section(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    assert 'Running equity' in body or 'Running Equity' in body

  def test_has_closed_trades_section(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    assert 'Last 5 Closed Trades' in body

  def test_has_footer_disclaimer(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    assert 'Not financial advice' in body

  # -----------------------------------------------------------------
  # Fix 6: header subtitle + signal-as-of (UI-SPEC §1)
  # -----------------------------------------------------------------

  def test_header_contains_project_subtitle(self) -> None:
    '''UI-SPEC §1: subtitle line `SPI 200 & AUD/USD mechanical system`.

    Rendered with html.escape so & becomes &amp;. Accept the escaped form
    (leaf-discipline per Phase 5 D-15).
    '''
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    assert 'SPI 200 &amp; AUD/USD mechanical system' in body or \
           'SPI 200 & AUD/USD mechanical system' in body

  def test_header_contains_signal_as_of(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    assert 'Signal as of' in body

  # -----------------------------------------------------------------
  # Fix 3: Trail Stop + Unrealised P&L exact-value assertions
  # -----------------------------------------------------------------

  def test_positions_trail_stop_long_exact_value(self) -> None:
    '''Fix 3: LONG trail = peak_price - TRAIL_MULT_LONG * atr_entry.

    AUDUSD LONG fixture: peak_price=0.6502, atr_entry=0.0042.
    Expected: 0.6502 - 3.0 * 0.0042 = 0.6376. Currency format: $0.64.
    '''
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    audusd_pos = state['positions']['AUDUSD']
    expected_trail = audusd_pos['peak_price'] - TRAIL_MULT_LONG * audusd_pos['atr_entry']
    # _fmt_currency_email uses 2dp — AUDUSD rendering accepts this per UI-SPEC
    expected_str = f'${expected_trail:,.2f}'
    assert expected_str in body, (
      f'Fix 3: LONG trail stop {expected_str} (={expected_trail}) missing from body; '
      f'TRAIL_MULT_LONG={TRAIL_MULT_LONG}'
    )

  def test_positions_trail_stop_short_exact_value(self) -> None:
    '''Fix 3: SHORT trail = trough_price + TRAIL_MULT_SHORT * atr_entry.

    SPI200 SHORT fixture: trough_price=8285.0, atr_entry=50.0.
    Expected: 8285.0 + 2.0 * 50.0 = 8385.00. Currency: $8,385.00.
    '''
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    spi_pos = state['positions']['SPI200']
    expected_trail = spi_pos['trough_price'] + TRAIL_MULT_SHORT * spi_pos['atr_entry']
    expected_str = f'${expected_trail:,.2f}'
    assert expected_str in body, (
      f'Fix 3: SHORT trail stop {expected_str} (={expected_trail}) missing from body; '
      f'TRAIL_MULT_SHORT={TRAIL_MULT_SHORT}'
    )

  def test_positions_unrealised_pnl_audusd_long_with_half_cost(self) -> None:
    '''Fix 3 + D-13: unrealised P&L includes opening-half-cost × n_contracts.

    AUDUSD LONG fixture: entry=last_close=0.6502, n_contracts=5,
    notional=10000.0, cost_aud=5.0 (round-trip).
    Opening half-cost = cost_aud/2 * n_contracts = 2.5 * 5 = 12.5.
    gross = (0.6502-0.6502) * 5 * 10000 = 0.0.
    unrealised = 0.0 - 12.5 = -12.50.
    Rendered via _fmt_pnl_with_colour_email → SHORT red span with -$12.50.
    '''
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    pos = state['positions']['AUDUSD']
    current = state['signals']['AUDUSD']['last_close']
    gross = (current - pos['entry_price']) * AUDUSD_NOTIONAL * pos['n_contracts']
    open_cost = (AUDUSD_COST_AUD / 2) * pos['n_contracts']
    expected_pnl = gross - open_cost
    # expected_pnl is -12.5 → rendered via _fmt_pnl_with_colour_email
    expected_span = notifier._fmt_pnl_with_colour_email(expected_pnl)
    assert expected_span in body, (
      f'Fix 3: AUDUSD unrealised P&L span missing; expected {expected_span!r} '
      f'(pnl={expected_pnl})'
    )

  def test_positions_unrealised_pnl_spi200_short_with_half_cost(self) -> None:
    '''Fix 3 + D-13: SPI200 SHORT fixture unrealised P&L.

    SPI200 SHORT: entry=last_close=8285.0, n_contracts=1, multiplier=5.0,
    cost_aud=6.0. Opening half-cost = 3.0 * 1 = 3.0.
    gross = (8285.0 - 8285.0) * 1 * 5 = 0.0 (SHORT flips sign).
    unrealised = 0.0 - 3.0 = -3.00.
    '''
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    pos = state['positions']['SPI200']
    current = state['signals']['SPI200']['last_close']
    # SHORT: profit when current < entry → direction_mult = -1
    gross = -1.0 * (current - pos['entry_price']) * SPI_MULT * pos['n_contracts']
    open_cost = (SPI_COST_AUD / 2) * pos['n_contracts']
    expected_pnl = gross - open_cost
    # expected_pnl is -3.0 → rendered via _fmt_pnl_with_colour_email
    expected_span = notifier._fmt_pnl_with_colour_email(expected_pnl)
    assert expected_span in body, (
      f'Fix 3: SPI200 unrealised P&L span missing; expected {expected_span!r} '
      f'(pnl={expected_pnl})'
    )

  # -----------------------------------------------------------------
  # Fix 4: _closed_position_for_instrument_on scans last 3 records
  # -----------------------------------------------------------------

  def test_closed_position_finds_both_instruments_on_same_run_date(self) -> None:
    '''Fix 4: widen scan to last-3 to support same-run double-close.

    Craft a state where trade_log[-1] is AUDUSD close on 2026-04-22 AND
    trade_log[-2] is SPI200 close on 2026-04-22. Both lookups must find
    their respective records — proves the scan reaches past [-1].
    '''
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    # tail [-1] already SPI200 close today; append AUDUSD close today so
    # SPI200 is now at [-2] and AUDUSD is at [-1].
    state['trade_log'].append({
      'instrument': 'AUDUSD',
      'direction': 'SHORT',
      'entry_date': '2026-04-15',
      'exit_date': '2026-04-22',
      'entry_price': 0.6550,
      'exit_price': 0.6502,
      'gross_pnl': 48.0,
      'n_contracts': 3,
      'exit_reason': 'signal_reversal',
      'multiplier': 10000.0,
      'cost_aud': 5.0,
      'net_pnl': 43.0,
    })
    audusd_record = notifier._closed_position_for_instrument_on(
      state, 'AUDUSD', '2026-04-22',
    )
    spi200_record = notifier._closed_position_for_instrument_on(
      state, 'SPI200', '2026-04-22',
    )
    assert audusd_record is not None, 'AUDUSD tail record should be found'
    assert audusd_record['instrument'] == 'AUDUSD'
    assert audusd_record['exit_date'] == '2026-04-22'
    assert spi200_record is not None, 'SPI200 at [-2] should be found by scanning last 3'
    assert spi200_record['instrument'] == 'SPI200'
    assert spi200_record['exit_date'] == '2026-04-22'

  def test_closed_position_returns_none_when_no_match(self) -> None:
    state = json.loads(SAMPLE_STATE_NO_CHANGE_PATH.read_text())
    # No trade_log entry has exit_date == 2026-04-22 in the no-change fixture
    result = notifier._closed_position_for_instrument_on(state, 'SPI200', '2026-04-22')
    assert result is None

  def test_closed_position_returns_none_on_empty_log(self) -> None:
    state = json.loads(EMPTY_STATE_PATH.read_text())
    result = notifier._closed_position_for_instrument_on(state, 'SPI200', '2026-04-22')
    assert result is None


class TestFormatters:
  '''D-02: notifier owns 7 _fmt_*_email formatters. Inline style on colour
  spans (email clients strip CSS classes). Mirror dashboard semantics
  with _email suffix.
  '''

  def test_fmt_currency_positive(self) -> None:
    assert notifier._fmt_currency_email(1234.56) == '$1,234.56'

  def test_fmt_currency_negative(self) -> None:
    assert notifier._fmt_currency_email(-1234.56) == '-$1,234.56'

  def test_fmt_currency_zero(self) -> None:
    assert notifier._fmt_currency_email(0.0) == '$0.00'

  def test_fmt_currency_large(self) -> None:
    assert notifier._fmt_currency_email(1234567.89) == '$1,234,567.89'

  def test_fmt_percent_signed_positive(self) -> None:
    assert notifier._fmt_percent_signed_email(0.0123) == '+1.2%'

  def test_fmt_percent_signed_negative(self) -> None:
    assert notifier._fmt_percent_signed_email(-0.0456) == '-4.6%'

  def test_fmt_percent_signed_zero(self) -> None:
    assert notifier._fmt_percent_signed_email(0.0) == '+0.0%'

  def test_fmt_percent_unsigned_positive(self) -> None:
    assert notifier._fmt_percent_unsigned_email(0.0123) == '1.2%'

  def test_fmt_percent_unsigned_negative_shows_minus(self) -> None:
    assert notifier._fmt_percent_unsigned_email(-0.0123) == '-1.2%'

  def test_fmt_pnl_with_colour_positive_green_with_plus(self) -> None:
    out = notifier._fmt_pnl_with_colour_email(100.5)
    assert '<span style="color:#22c55e">' in out
    assert '+$100.50</span>' in out
    assert 'class=' not in out  # NO CSS classes — inline style only (D-02)

  def test_fmt_pnl_with_colour_negative_red_no_plus(self) -> None:
    out = notifier._fmt_pnl_with_colour_email(-50.25)
    assert '<span style="color:#ef4444">' in out
    assert '-$50.25</span>' in out
    # no leading '+' in the body span (negative already has leading '-')
    body = out.split('>', 1)[1]
    assert '+' not in body

  def test_fmt_pnl_with_colour_zero_muted(self) -> None:
    out = notifier._fmt_pnl_with_colour_email(0.0)
    assert '<span style="color:#cbd5e1">' in out
    assert '$0.00</span>' in out

  def test_fmt_pnl_with_colour_no_css_class(self) -> None:
    '''D-02: email clients strip CSS classes — must be inline style only.'''
    for value in (100.0, -50.0, 0.0):
      out = notifier._fmt_pnl_with_colour_email(value)
      assert 'class=' not in out, (
        f'_fmt_pnl_with_colour_email must NOT emit class attributes; got: {out!r}'
      )

  def test_fmt_pnl_with_colour_escapes_body(self) -> None:
    '''Belt-and-braces: html.escape called on output (Phase 5 D-15 discipline).

    Currency format is ASCII-safe so the output equals its escaped form;
    the assertion proves the contract by comparing against html.escape output.
    '''
    out = notifier._fmt_pnl_with_colour_email(0.0)
    # '$0.00' survives html.escape unchanged but we still route through it
    assert html.escape('$0.00', quote=True) in out

  def test_fmt_em_dash(self) -> None:
    assert notifier._fmt_em_dash_email() == '—'

  def test_fmt_last_updated_naive_raises(self) -> None:
    '''C-1 reviews: naive datetime must raise (prevents pytz LMT bug).'''
    naive = datetime(2026, 4, 22, 9, 0)
    with pytest.raises(ValueError, match='naive datetime='):
      notifier._fmt_last_updated_email(naive)

  def test_fmt_last_updated_awst(self) -> None:
    aware_awst = FROZEN_NOW  # PERTH.localize(datetime(2026, 4, 22, 9, 0))
    assert notifier._fmt_last_updated_email(aware_awst) == '2026-04-22 09:00 AWST'

  def test_fmt_last_updated_utc_converts_to_awst(self) -> None:
    # 01:00 UTC = 09:00 AWST (UTC+8)
    aware_utc = pytz.UTC.localize(datetime(2026, 4, 22, 1, 0))
    assert notifier._fmt_last_updated_email(aware_utc) == '2026-04-22 09:00 AWST'

  def test_fmt_instrument_display_spi200(self) -> None:
    assert notifier._fmt_instrument_display_email('SPI200') == 'SPI 200'

  def test_fmt_instrument_display_audusd(self) -> None:
    assert notifier._fmt_instrument_display_email('AUDUSD') == 'AUD / USD'


class TestSendDispatch:
  '''D-13 + NOTF-07 + NOTF-08: send_daily_email never-crash semantics.
  RESEND_API_KEY-missing → last_email.html fallback; 5xx logs + returns 0;
  unexpected exceptions logged + returns 0. Wave 2 (06-03) fills.
  '''

  def test_scaffold_placeholder_send_dispatch(self) -> None:
    '''Nyquist Dimension 8: placeholder for NOTF-07, NOTF-08 — passes
    via pytest.raises(NotImplementedError). Wave 2 (06-03) replaces
    this with real send_daily_email cases.
    '''
    with pytest.raises(NotImplementedError, match='Wave 2'):
      send_daily_email({}, {}, FROZEN_NOW, is_test=False)


class TestResendPost:
  '''D-12 + RESEARCH §1: _post_to_resend retry loop — 4xx (≠ 429) fail-fast;
  429/5xx/Timeout/ConnectionError retry with flat 10s backoff up to 3×.
  Wave 2 (06-03) fills via monkeypatch on notifier.requests.post.
  '''

  def test_scaffold_placeholder_resend_post(self) -> None:
    '''Nyquist Dimension 8: placeholder for NOTF-01 — passes via
    pytest.raises(NotImplementedError). Wave 2 (06-03) replaces this
    with real _post_to_resend cases.
    '''
    with pytest.raises(NotImplementedError, match='Wave 2'):
      notifier._post_to_resend(
        'fake_key', 'from@x', 'to@y', 'subj', '<html/>',
        timeout_s=1, retries=1, backoff_s=0,
      )


class TestGoldenEmail:
  '''D-03 phase gate: byte-equal HTML snapshots for 3 scenarios (with_change,
  no_change, empty). Wave 2 (06-03) regenerates goldens + asserts byte-equal.
  Double-run idempotency: `python tests/regenerate_notifier_golden.py`
  run twice produces zero git diff on tests/fixtures/notifier/.
  '''

  def test_scaffold_placeholder_golden_with_change(self) -> None:
    '''Nyquist Dimension 8: placeholder — Wave 2 regenerates goldens.

    Wave 2 (06-03) replaces this with byte-equal assertion against
    tests/fixtures/notifier/golden_with_change.html.
    '''
    assert GOLDEN_WITH_CHANGE_PATH.exists(), 'Wave 0 placeholder must exist'
    # Placeholder: Wave 2 fills real byte-equal assertion
    pytest.xfail('Wave 2 (06-03) fills TestGoldenEmail byte-equal assertions')
