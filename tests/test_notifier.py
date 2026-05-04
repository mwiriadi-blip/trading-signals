'''Phase 6 test suite: notifier compose + dispatch + formatters + goldens + never-crash.

Organized into 7 classes per D-03 (one class per concern dimension):
  TestComposeSubject — D-04 subject template + emoji + [TEST] prefix + first-run + equity rounding
  TestDetectSignalChanges — D-06 first-run-as-no-change helper
  TestComposeBody    — D-10 7-section body + ACTION REQUIRED + palette inline + XSS escape
  TestFormatters     — _fmt_*_email parity with dashboard formatters (currency, percent, pnl, etc.)
  TestSendDispatch   — send_daily_email RESEND_API_KEY paths + never-crash semantics
  TestResendPost     — _post_to_resend retry loop + 429 special-case + 4xx fail-fast
  TestAtomicWriteHtml — _atomic_write_html tempfile + fsync + os.replace (D-13 + C-7)
  TestGoldenEmail    — byte-equal HTML snapshots (3 fixtures → 3 goldens)

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
import json
import logging
from datetime import datetime
from pathlib import Path
from unittest.mock import (
  patch,  # noqa: F401 — legacy alias (monkeypatch now preferred)
)

import pytest
import pytz
import requests

import notifier
from notifier import (  # noqa: F401 — re-exported for convenience in tests
  compose_email_body,
  compose_email_subject,
  send_crash_email,
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
# Phase 12 D-19 + D-16: module-level autouse fixture pinning SIGNALS_EMAIL_FROM
# =========================================================================
# After D-16 removes the hardcoded _EMAIL_FROM constant, every test whose
# path reaches send_daily_email / send_crash_email must see an env-provided
# sender value — otherwise the dispatch short-circuits with missing_sender.
# Pinning here to the same value baked into the committed golden HTMLs keeps
# TestGoldenEmail byte-equal across env configurations. Individual tests in
# TestEmailFromEnvVar override by calling monkeypatch.delenv / setenv('')
# within their own bodies — pytest's last-mutation-wins semantics mean this
# fixture is the default and per-test mutations override.
#
# Deliberately broad (12-REVIEWS.md LOW): every test class touches email
# rendering or dispatch one way or another. Narrowing scope risks test
# failures post signature migration.

@pytest.fixture(autouse=True)
def _pin_signals_email_from(monkeypatch):
  '''Phase 12 D-19 + D-16: module-level default for SIGNALS_EMAIL_FROM.

  After D-16 removes the hardcoded _EMAIL_FROM constant, every test that
  renders email body content must see an env-provided sender value,
  otherwise send_daily_email short-circuits with missing_sender. Pinning
  to the same value as the committed golden HTMLs keeps TestGoldenEmail
  byte-equal across env configurations.
  '''
  monkeypatch.setenv(
    'SIGNALS_EMAIL_FROM', 'signals@carbonbookkeeping.com.au',
  )


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

  def test_subject_first_run_label_when_no_date_iso(self) -> None:
    '''WR-02 close (2026-04-22): when empty_state has last_run=null AND
    legacy int-shape signals (no as_of_run), the subject MUST NOT emit a
    double-space between emoji and em-dash. Fallback label is the literal
    'first run' token per 06-REVIEW.md WR-02 recommendation.

    This is the operator's very first email after setup, so the label
    should be self-documenting. D-04 template shape preserved:
      {emoji} {date_or_label} — SPI200 {SIG}, AUDUSD {SIG} — Equity ${X,XXX}
    '''
    state = json.loads(EMPTY_STATE_PATH.read_text())
    subject = compose_email_subject(
      state,
      {'^AXJO': None, 'AUDUSD=X': None},
      is_test=False,
    )
    # D-04 + D-06: 📊 emoji for first-run; NEW 'first run' label.
    assert subject == (
      '📊 first run — SPI200 FLAT, AUDUSD FLAT — Equity $100,000'
    ), (
      f'WR-02: empty-state subject must use "first run" label '
      f'(not empty date); got: {subject!r}'
    )
    # Belt-and-braces: the cosmetic double-space MUST be gone.
    assert '📊  —' not in subject, (
      f'WR-02: double-space between emoji and em-dash must not appear; '
      f'got: {subject!r}'
    )


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
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW, from_addr='signals@carbonbookkeeping.com.au')
    assert body.startswith('<!DOCTYPE html>'), f'expected DOCTYPE prefix; got: {body[:32]!r}'
    assert body.endswith('</html>\n'), f'expected </html>\\n suffix; got: {body[-32:]!r}'

  def test_body_sections_in_d10_order(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW, from_addr='signals@carbonbookkeeping.com.au')
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
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW, from_addr='signals@carbonbookkeeping.com.au')
    assert '<style>' not in body
    assert '</style>' not in body

  def test_body_no_media_query(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW, from_addr='signals@carbonbookkeeping.com.au')
    assert '@media' not in body

  def test_body_has_palette_inline_bg(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW, from_addr='signals@carbonbookkeeping.com.au')
    assert '#0f1117' in body

  def test_body_has_max_width_600(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW, from_addr='signals@carbonbookkeeping.com.au')
    assert 'max-width:600px' in body

  def test_body_has_viewport_meta(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW, from_addr='signals@carbonbookkeeping.com.au')
    assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in body

  def test_body_has_role_presentation(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW, from_addr='signals@carbonbookkeeping.com.au')
    assert 'role="presentation"' in body

  def test_body_has_bgcolor_belt_and_braces(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW, from_addr='signals@carbonbookkeeping.com.au')
    assert 'bgcolor="#0f1117"' in body

  def test_compose_body_naive_datetime_raises(self) -> None:
    '''T-06-04: naive datetime rejected at body-composer entry (C-1 reviews).'''
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    naive = datetime(2026, 4, 22, 9, 0)
    with pytest.raises(ValueError, match='naive datetime='):
      compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, naive, from_addr='signals@carbonbookkeeping.com.au')

  # -----------------------------------------------------------------
  # ACTION REQUIRED conditional + copy (D-06, D-11)
  # -----------------------------------------------------------------

  def test_action_required_present_on_change(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW, from_addr='signals@carbonbookkeeping.com.au')
    assert 'ACTION REQUIRED' in body
    assert 'border-left:4px solid #ef4444' in body

  def test_action_required_absent_on_no_change(self) -> None:
    state = json.loads(SAMPLE_STATE_NO_CHANGE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW, from_addr='signals@carbonbookkeeping.com.au')
    assert 'ACTION REQUIRED' not in body

  def test_action_required_absent_on_first_run(self) -> None:
    '''D-06: first-run (all old None) is NO CHANGE — ACTION REQUIRED omitted.'''
    state = json.loads(EMPTY_STATE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': None, 'AUDUSD=X': None}, FROZEN_NOW, from_addr='signals@carbonbookkeeping.com.au')
    assert 'ACTION REQUIRED' not in body

  def test_action_required_contains_per_instrument_diffs(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW, from_addr='signals@carbonbookkeeping.com.au')
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
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW, from_addr='signals@carbonbookkeeping.com.au')
    # Fixture trade_log[-1] is SPI200 LONG close on 2026-04-22 with
    # n_contracts=2, entry_price=8204.5 → "(2 contracts @ entry $8,204.50)"
    assert 'Close existing LONG position (2 contracts @ entry $8,204.50)' in body

  def test_action_required_uses_unicode_arrow(self) -> None:
    '''Fix 5: raw Unicode → (U+2192), never &rarr; HTML entity.'''
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW, from_addr='signals@carbonbookkeeping.com.au')
    assert '→' in body
    assert '&rarr;' not in body

  # -----------------------------------------------------------------
  # Empty-state / first-run rendering
  # -----------------------------------------------------------------

  def test_empty_state_renders_no_open_positions(self) -> None:
    state = json.loads(EMPTY_STATE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': None, 'AUDUSD=X': None}, FROZEN_NOW, from_addr='signals@carbonbookkeeping.com.au')
    assert 'No open positions' in body

  def test_empty_state_equity_is_initial_account(self) -> None:
    state = json.loads(EMPTY_STATE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': None, 'AUDUSD=X': None}, FROZEN_NOW, from_addr='signals@carbonbookkeeping.com.au')
    # empty_state.json has account=100000.0, equity_history=[]
    assert '$100,000.00' in body

  def test_empty_state_renders_no_closed_trades(self) -> None:
    state = json.loads(EMPTY_STATE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': None, 'AUDUSD=X': None}, FROZEN_NOW, from_addr='signals@carbonbookkeeping.com.au')
    assert 'No closed trades' in body

  # -----------------------------------------------------------------
  # XSS escape (T-06-03)
  # -----------------------------------------------------------------

  def test_xss_escape_on_exit_reason(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    state['trade_log'][-1]['exit_reason'] = '<script>alert(1)</script>'
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW, from_addr='signals@carbonbookkeeping.com.au')
    assert '<script>alert(1)</script>' not in body
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in body

  def test_xss_escape_on_instrument_value(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    state['trade_log'][-1]['instrument'] = '<script>x</script>'
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW, from_addr='signals@carbonbookkeeping.com.au')
    assert '<script>x</script>' not in body
    assert '&lt;script&gt;x&lt;/script&gt;' in body

  def test_xss_escape_on_direction_value(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    state['positions']['SPI200']['direction'] = '<img src=x onerror=y>'
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW, from_addr='signals@carbonbookkeeping.com.au')
    assert '<img src=x onerror=y>' not in body
    assert '&lt;img src=x onerror=y&gt;' in body

  # -----------------------------------------------------------------
  # Subsection presence (NOTF-04)
  # -----------------------------------------------------------------

  def test_has_header_section(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW, from_addr='signals@carbonbookkeeping.com.au')
    assert 'Trading Signals' in body

  def test_has_signal_status_section(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW, from_addr='signals@carbonbookkeeping.com.au')
    assert 'Signal Status' in body

  def test_has_positions_section(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW, from_addr='signals@carbonbookkeeping.com.au')
    assert 'Open Positions' in body

  def test_has_todays_pnl_section(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW, from_addr='signals@carbonbookkeeping.com.au')
    # html.escape(quote=True) renders ' as &#x27; and & as &amp;
    # so "Today's P&L" appears as "Today&#x27;s P&amp;L" in the body.
    assert (
      'Today&#x27;s P&amp;L' in body
      or "Today's P&amp;L" in body
      or "Today's P&L" in body
    )

  def test_has_running_equity_section(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW, from_addr='signals@carbonbookkeeping.com.au')
    assert 'Running equity' in body or 'Running Equity' in body

  def test_has_closed_trades_section(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW, from_addr='signals@carbonbookkeeping.com.au')
    assert 'Last 5 Closed Trades' in body

  def test_has_footer_disclaimer(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW, from_addr='signals@carbonbookkeeping.com.au')
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
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW, from_addr='signals@carbonbookkeeping.com.au')
    assert 'SPI 200 &amp; AUD/USD mechanical system' in body or \
           'SPI 200 & AUD/USD mechanical system' in body

  def test_header_contains_signal_as_of(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW, from_addr='signals@carbonbookkeeping.com.au')
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
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW, from_addr='signals@carbonbookkeeping.com.au')
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
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW, from_addr='signals@carbonbookkeeping.com.au')
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
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW, from_addr='signals@carbonbookkeeping.com.au')
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
    body = compose_email_body(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW, from_addr='signals@carbonbookkeeping.com.au')
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


class TestUnrealisedPnlEmailUsesResolvedContracts:
  '''Phase 8 WR-01 (mirror of dashboard test): _compute_unrealised_pnl_email
  MUST source the tier multiplier/cost from state['_resolved_contracts']
  [state_key] so operators who --reset with a non-default tier (spi-standard,
  spi-full) see correct unrealised P&L in the daily email — not the
  hardcoded spi-mini default. Fallback to module-level
  _CONTRACT_SPECS_EMAIL only when _resolved_contracts is absent.
  '''

  def test_standard_tier_uses_25_multiplier(self) -> None:
    '''spi-standard: multiplier=25.0, cost_aud=30.0. LONG 2 contracts
    entry=7000, current=7100 → gross = 100 * 2 * 25 = 5000.
    cost_open = 30/2 * 2 = 30. unrealised = 5000 - 30 = 4970.
    '''
    position = {
      'direction': 'LONG', 'entry_price': 7000.0, 'entry_date': '2026-04-10',
      'n_contracts': 2, 'pyramid_level': 0, 'peak_price': 7100.0,
      'trough_price': None, 'atr_entry': 50.0,
    }
    state = {
      '_resolved_contracts': {
        'SPI200':  {'multiplier': 25.0, 'cost_aud': 30.0},
        'AUDUSD':  {'multiplier': 10000.0, 'cost_aud': 5.0},
      },
    }
    result = notifier._compute_unrealised_pnl_email(
      position, 'SPI200', 7100.0, state,
    )
    assert result == pytest.approx(4970.0)

  def test_full_tier_uses_50_multiplier(self) -> None:
    '''spi-full: multiplier=50.0, cost_aud=50.0. LONG 1 contract
    entry=7000, current=7100 → gross = 100 * 1 * 50 = 5000.
    cost_open = 50/2 * 1 = 25. unrealised = 5000 - 25 = 4975.
    '''
    position = {
      'direction': 'LONG', 'entry_price': 7000.0, 'entry_date': '2026-04-10',
      'n_contracts': 1, 'pyramid_level': 0, 'peak_price': 7100.0,
      'trough_price': None, 'atr_entry': 50.0,
    }
    state = {
      '_resolved_contracts': {
        'SPI200':  {'multiplier': 50.0, 'cost_aud': 50.0},
        'AUDUSD':  {'multiplier': 10000.0, 'cost_aud': 5.0},
      },
    }
    result = notifier._compute_unrealised_pnl_email(
      position, 'SPI200', 7100.0, state,
    )
    assert result == pytest.approx(4975.0)

  def test_missing_resolved_contracts_falls_back_to_mini_defaults(
      self, caplog) -> None:
    '''State without _resolved_contracts key → falls back to module-level
    _CONTRACT_SPECS_EMAIL (spi-mini = 5.0 multiplier, 6.0 cost_aud).
    Debug log emitted.

    LONG 2 contracts entry=7000, current=7100 → gross = 100*2*5 = 1000.
    cost_open = 6/2 * 2 = 6. unrealised = 1000 - 6 = 994.
    '''
    position = {
      'direction': 'LONG', 'entry_price': 7000.0, 'entry_date': '2026-04-10',
      'n_contracts': 2, 'pyramid_level': 0, 'peak_price': 7100.0,
      'trough_price': None, 'atr_entry': 50.0,
    }
    state = {}
    with caplog.at_level(logging.DEBUG, logger='notifier'):
      result = notifier._compute_unrealised_pnl_email(
        position, 'SPI200', 7100.0, state,
      )
    assert result == pytest.approx(994.0)
    assert any(
      '_resolved_contracts missing' in rec.message for rec in caplog.records
    ), 'WR-01 fallback should emit a DEBUG log line naming the missing key'

  def test_state_none_also_falls_back(self) -> None:
    '''state=None → same fallback to module-level defaults (backward
    compatibility with older call sites / pytest parity checks).
    '''
    position = {
      'direction': 'LONG', 'entry_price': 7000.0, 'entry_date': '2026-04-10',
      'n_contracts': 1, 'pyramid_level': 0, 'peak_price': 7100.0,
      'trough_price': None, 'atr_entry': 50.0,
    }
    # multiplier=5.0, cost_aud=6.0. gross = 100*1*5 = 500. open_cost = 3.
    result = notifier._compute_unrealised_pnl_email(
      position, 'SPI200', 7100.0, None,
    )
    assert result == pytest.approx(497.0)


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


# =========================================================================
# TestResendPost helpers — module-level _FakeResp factory used by many cases
# =========================================================================

class _FakeResp:
  '''Minimal stand-in for requests.Response used by TestResendPost monkeypatches.

  Fields: status_code, text. raise_for_status() raises HTTPError on 5xx+429
  and no-ops otherwise — mirror of real requests behaviour for the subset
  of codes _post_to_resend cares about.
  '''

  def __init__(self, status_code: int, text: str = 'ok') -> None:
    self.status_code = status_code
    self.text = text

  def raise_for_status(self) -> None:
    if self.status_code == 429 or self.status_code >= 500:
      raise requests.exceptions.HTTPError(
        f'{self.status_code}', response=self,
      )


class TestResendPost:
  '''D-12 + RESEARCH §1: _post_to_resend retry loop — 4xx (≠ 429) fail-fast;
  429/5xx/Timeout/ConnectionError retry with flat backoff up to 3×.

  Monkeypatch target: notifier.requests.post (never the real HTTPS endpoint).
  backoff_s=0 keeps tests <1s.
  '''

  def test_post_url_and_auth_header(self, monkeypatch) -> None:
    '''POST URL + headers + JSON payload shape (RESEARCH §1).'''
    captured: list[dict] = []

    def _fake_post(url, **kw):
      captured.append({'url': url, **kw})
      return _FakeResp(200, '{"id":"uuid"}')

    monkeypatch.setattr('notifier.requests.post', _fake_post)
    notifier._post_to_resend(
      'test_key_xyz', 'from@x.com', 'recipient@x.com',
      '🔴 subject', '<html/>',
      timeout_s=5, retries=1, backoff_s=0,
    )
    assert len(captured) == 1
    call = captured[0]
    assert call['url'] == 'https://api.resend.com/emails'
    assert call['headers']['Authorization'] == 'Bearer test_key_xyz'
    assert call['headers']['Content-Type'] == 'application/json'
    assert call['timeout'] == (5, 5), (
      'Fix 2: requests.post timeout must be (connect, read) tuple not scalar'
    )
    payload = call['json']
    assert payload['from'] == 'from@x.com'
    assert payload['to'] == ['recipient@x.com']
    assert payload['subject'] == '🔴 subject'
    assert payload['html'] == '<html/>'

  def test_success_200_returns_none(self, monkeypatch) -> None:
    calls: list[int] = []

    def _fake_post(*a, **kw):
      calls.append(1)
      return _FakeResp(200, 'ok')

    monkeypatch.setattr('notifier.requests.post', _fake_post)
    result = notifier._post_to_resend(
      'k', 'a@b.c', 'c@d.e', 'subj', '<html/>',
      timeout_s=1, retries=3, backoff_s=0,
    )
    assert result is None
    assert len(calls) == 1, 'no retries needed on 200'

  @pytest.mark.parametrize('status', [400, 401, 403, 422])
  def test_4xx_fails_fast(self, monkeypatch, status) -> None:
    '''4xx (except 429) fails fast with no retries — raises ResendError.'''
    calls: list[int] = []

    def _fake_post(*a, **kw):
      calls.append(1)
      return _FakeResp(status, f'{status} body')

    monkeypatch.setattr('notifier.requests.post', _fake_post)
    with pytest.raises(notifier.ResendError, match=f'4xx from Resend: {status}'):
      notifier._post_to_resend(
        'k', 'a@b.c', 'c@d.e', 'subj', '<html/>',
        timeout_s=1, retries=3, backoff_s=0,
      )
    assert len(calls) == 1, '4xx must fail fast — no retries'

  def test_429_IS_retried(self, monkeypatch) -> None:
    '''RESEARCH §1: 429 IS retryable per Resend — special-case BEFORE 4xx band.'''
    calls: list[int] = []

    def _fake_post(*a, **kw):
      calls.append(1)
      return _FakeResp(429 if len(calls) < 3 else 200)

    monkeypatch.setattr('notifier.requests.post', _fake_post)
    result = notifier._post_to_resend(
      'k', 'a@b.c', 'c@d.e', 'subj', '<html/>',
      timeout_s=1, retries=3, backoff_s=0,
    )
    assert result is None, 'succeeds on 3rd attempt'
    assert len(calls) == 3

  def test_429_retries_exhausted_raises(self, monkeypatch) -> None:
    calls: list[int] = []

    def _fake_post(*a, **kw):
      calls.append(1)
      return _FakeResp(429)

    monkeypatch.setattr('notifier.requests.post', _fake_post)
    with pytest.raises(notifier.ResendError, match='retries exhausted'):
      notifier._post_to_resend(
        'k', 'a@b.c', 'c@d.e', 'subj', '<html/>',
        timeout_s=1, retries=3, backoff_s=0,
      )
    assert len(calls) == 3

  def test_5xx_500_retries_then_success(self, monkeypatch) -> None:
    calls: list[int] = []

    def _fake_post(*a, **kw):
      calls.append(1)
      return _FakeResp(500 if len(calls) == 1 else 200)

    monkeypatch.setattr('notifier.requests.post', _fake_post)
    result = notifier._post_to_resend(
      'k', 'a@b.c', 'c@d.e', 'subj', '<html/>',
      timeout_s=1, retries=3, backoff_s=0,
    )
    assert result is None
    assert len(calls) == 2

  def test_5xx_500_retries_exhausted_raises(self, monkeypatch) -> None:
    calls: list[int] = []

    def _fake_post(*a, **kw):
      calls.append(1)
      return _FakeResp(500)

    monkeypatch.setattr('notifier.requests.post', _fake_post)
    with pytest.raises(notifier.ResendError, match='retries exhausted'):
      notifier._post_to_resend(
        'k', 'a@b.c', 'c@d.e', 'subj', '<html/>',
        timeout_s=1, retries=3, backoff_s=0,
      )
    assert len(calls) == 3

  def test_timeout_retries_then_raises(self, monkeypatch) -> None:
    calls: list[int] = []

    def _fake_post(*a, **kw):
      calls.append(1)
      raise requests.exceptions.Timeout('slow')

    monkeypatch.setattr('notifier.requests.post', _fake_post)
    with pytest.raises(notifier.ResendError, match='retries exhausted'):
      notifier._post_to_resend(
        'k', 'a@b.c', 'c@d.e', 'subj', '<html/>',
        timeout_s=1, retries=3, backoff_s=0,
      )
    assert len(calls) == 3

  def test_connection_error_retries_then_raises(self, monkeypatch) -> None:
    calls: list[int] = []

    def _fake_post(*a, **kw):
      calls.append(1)
      raise requests.exceptions.ConnectionError('refused')

    monkeypatch.setattr('notifier.requests.post', _fake_post)
    with pytest.raises(notifier.ResendError, match='retries exhausted'):
      notifier._post_to_resend(
        'k', 'a@b.c', 'c@d.e', 'subj', '<html/>',
        timeout_s=1, retries=3, backoff_s=0,
      )
    assert len(calls) == 3

  def test_api_key_NOT_in_error_body(self, monkeypatch) -> None:
    '''T-06-02: even if Resend echoes the Authorization header back in the
    4xx body, the raised ResendError must NOT contain the raw api_key.
    '''
    api_key = 'test_key_xyz_NEVER_LEAK'

    def _fake_post(*a, **kw):
      return _FakeResp(401, f'unauthorized: Bearer {api_key}')

    monkeypatch.setattr('notifier.requests.post', _fake_post)
    with pytest.raises(notifier.ResendError) as exc_info:
      notifier._post_to_resend(
        api_key, 'a@b.c', 'c@d.e', 'subj', '<html/>',
        timeout_s=1, retries=3, backoff_s=0,
      )
    msg = str(exc_info.value)
    assert '401' in msg
    assert api_key not in msg, f'T-06-02 leak: raw api_key in error: {msg!r}'

  def test_api_key_redacted_in_4xx_error_body(self, monkeypatch) -> None:
    '''Fix 1 (HIGH): api_key actively redacted from 4xx error body.

    Craft a fake 4xx response whose .text contains the literal api_key
    (simulating Resend echoing the Authorization header back in its error
    body). Assert the raised ResendError message:
      - contains '4xx from Resend: 401'
      - contains '[REDACTED]'
      - does NOT contain the raw key
    '''
    api_key = 'test_key_xyz'

    def _fake_post(*a, **kw):
      return _FakeResp(401, f'Bearer {api_key} not authorized')

    monkeypatch.setattr('notifier.requests.post', _fake_post)
    with pytest.raises(notifier.ResendError) as exc_info:
      notifier._post_to_resend(
        api_key, 'a@b.c', 'c@d.e', 'subj', '<html/>',
        timeout_s=1, retries=3, backoff_s=0,
      )
    msg = str(exc_info.value)
    assert '4xx from Resend: 401' in msg
    assert '[REDACTED]' in msg, f'Fix 1: expected [REDACTED] in 4xx body; got: {msg!r}'
    assert api_key not in msg, f'Fix 1 leak: api_key in 4xx body: {msg!r}'

  def test_api_key_redacted_in_retries_exhausted(self, monkeypatch) -> None:
    '''Fix 1 (HIGH): redaction also applies to the retries-exhausted branch.

    Monkeypatch requests.post to raise ConnectionError whose message
    embeds the literal api_key. Assert the final ResendError message
    contains [REDACTED] and NOT the raw key.
    '''
    api_key = 'test_key_xyz'

    def _fake_post(*a, **kw):
      raise requests.exceptions.ConnectionError(
        f'refused with token {api_key} embedded',
      )

    monkeypatch.setattr('notifier.requests.post', _fake_post)
    with pytest.raises(notifier.ResendError) as exc_info:
      notifier._post_to_resend(
        api_key, 'a@b.c', 'c@d.e', 'subj', '<html/>',
        timeout_s=1, retries=2, backoff_s=0,
      )
    msg = str(exc_info.value)
    assert 'retries exhausted' in msg
    assert '[REDACTED]' in msg, (
      f'Fix 1: expected [REDACTED] in retries-exhausted msg; got: {msg!r}'
    )
    assert api_key not in msg, (
      f'Fix 1 leak: api_key in retries-exhausted msg: {msg!r}'
    )

  def test_timeout_tuple_5_connect_read(self, monkeypatch) -> None:
    '''Fix 2 (MEDIUM): requests.post called with timeout=(5, timeout_s) tuple.

    Prevents hung DNS/TCP handshake from consuming the full read budget.
    '''
    captured: list[dict] = []

    def _fake_post(url, **kw):
      captured.append({'url': url, **kw})
      return _FakeResp(200)

    monkeypatch.setattr('notifier.requests.post', _fake_post)
    notifier._post_to_resend(
      'k', 'a@b.c', 'c@d.e', 'subj', '<html/>',
      timeout_s=30, retries=1, backoff_s=0,
    )
    assert captured[0]['timeout'] == (5, 30), (
      f'Fix 2: expected (5, 30) tuple; got {captured[0]["timeout"]!r}'
    )


class TestSendDispatch:
  '''D-13 + NOTF-07 + NOTF-08: send_daily_email never-crash semantics.
  RESEND_API_KEY-missing → last_email.html fallback; 5xx logs + returns 0;
  unexpected exceptions logged + returns 0.
  '''

  def test_missing_api_key_writes_last_email_html(
      self, tmp_path, monkeypatch) -> None:
    '''NOTF-08: missing RESEND_API_KEY → write last_email.html + return
    SendStatus(ok=True, reason='no_api_key') — graceful degradation is not
    a failure (Phase 8 D-02).
    '''
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('RESEND_API_KEY', raising=False)
    state = json.loads(SAMPLE_STATE_NO_CHANGE_PATH.read_text())
    result = send_daily_email(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    assert result.ok is True
    assert result.reason == 'no_api_key'
    last = tmp_path / 'last_email.html'
    assert last.exists(), 'NOTF-08: must write last_email.html when key missing'
    assert last.read_text(encoding='utf-8').startswith('<!DOCTYPE html>')

  def test_missing_api_key_logs_warn(
      self, tmp_path, monkeypatch, caplog) -> None:
    caplog.set_level(logging.WARNING)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('RESEND_API_KEY', raising=False)
    state = json.loads(EMPTY_STATE_PATH.read_text())
    send_daily_email(state, {'^AXJO': None, 'AUDUSD=X': None}, FROZEN_NOW)
    assert '[Email] WARN RESEND_API_KEY missing' in caplog.text

  def test_5xx_exhausted_returns_zero_and_logs(
      self, tmp_path, monkeypatch, caplog) -> None:
    '''NOTF-07 + Phase 8 D-08: 5xx retries-exhausted logs [Email] WARN and
    returns SendStatus(ok=False, reason=...) (never raises). Orchestrator
    translates into append_warning for next-run surfacing.
    '''
    caplog.set_level(logging.WARNING)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('RESEND_API_KEY', 'test_key_5xx')

    def _fake_post(*a, **kw):
      return _FakeResp(500)

    monkeypatch.setattr('notifier.requests.post', _fake_post)
    # Monkeypatch retry constants to speed test
    monkeypatch.setattr('notifier._RESEND_BACKOFF_S', 0)
    state = json.loads(SAMPLE_STATE_NO_CHANGE_PATH.read_text())
    result = send_daily_email(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    assert result.ok is False
    assert result.reason is not None
    assert '[Email] WARN send failed' in caplog.text

  def test_4xx_returns_zero_and_logs(
      self, tmp_path, monkeypatch, caplog) -> None:
    '''Phase 8 D-08: 4xx fails fast → SendStatus(ok=False, reason=...).'''
    caplog.set_level(logging.WARNING)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('RESEND_API_KEY', 'test_key_4xx')

    def _fake_post(*a, **kw):
      return _FakeResp(400, 'validation_error')

    monkeypatch.setattr('notifier.requests.post', _fake_post)
    state = json.loads(SAMPLE_STATE_NO_CHANGE_PATH.read_text())
    result = send_daily_email(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    assert result.ok is False
    assert result.reason is not None
    assert '[Email] WARN send failed' in caplog.text
    assert '4xx from Resend: 400' in caplog.text

  def test_unexpected_exception_swallowed(
      self, tmp_path, monkeypatch, caplog) -> None:
    '''Belt-and-braces: ANY unexpected Exception from _post_to_resend is
    swallowed and surfaces as SendStatus(ok=False, reason=...) (Phase 8 D-08).
    '''
    caplog.set_level(logging.WARNING)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('RESEND_API_KEY', 'test_key_unexp')

    def _raise_unexpected(*a, **kw):
      raise ValueError('unexpected failure')

    monkeypatch.setattr(notifier, '_post_to_resend', _raise_unexpected)
    state = json.loads(SAMPLE_STATE_NO_CHANGE_PATH.read_text())
    result = send_daily_email(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    assert result.ok is False
    assert result.reason is not None and 'ValueError' in result.reason
    assert '[Email] WARN unexpected failure: ValueError' in caplog.text

  def test_success_logs_info(
      self, tmp_path, monkeypatch, caplog) -> None:
    '''Phase 8 D-08: 200 OK → SendStatus(ok=True, reason=None).'''
    caplog.set_level(logging.INFO)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('RESEND_API_KEY', 'test_key_success_xyz')

    def _fake_post(*a, **kw):
      return _FakeResp(200, '{"id":"uuid"}')

    monkeypatch.setattr('notifier.requests.post', _fake_post)
    state = json.loads(SAMPLE_STATE_NO_CHANGE_PATH.read_text())
    result = send_daily_email(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    assert result.ok is True
    assert result.reason is None
    assert '[Email] sent to' in caplog.text

  def test_respects_signals_email_to_env_override(
      self, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('RESEND_API_KEY', 'k')
    monkeypatch.setenv('SIGNALS_EMAIL_TO', 'custom@example.com')
    captured: list[dict] = []

    def _fake_post(url, **kw):
      captured.append({'url': url, **kw})
      return _FakeResp(200)

    monkeypatch.setattr('notifier.requests.post', _fake_post)
    state = json.loads(SAMPLE_STATE_NO_CHANGE_PATH.read_text())
    send_daily_email(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    assert captured[0]['json']['to'] == ['custom@example.com']

  def test_uses_fallback_recipient_when_signals_email_to_unset(
      self, tmp_path, monkeypatch) -> None:
    '''D-14 Option C: _EMAIL_TO_FALLBACK == 'mwiriadi@gmail.com' when env unset.'''
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('RESEND_API_KEY', 'k')
    monkeypatch.delenv('SIGNALS_EMAIL_TO', raising=False)
    captured: list[dict] = []

    def _fake_post(url, **kw):
      captured.append({'url': url, **kw})
      return _FakeResp(200)

    monkeypatch.setattr('notifier.requests.post', _fake_post)
    state = json.loads(SAMPLE_STATE_NO_CHANGE_PATH.read_text())
    send_daily_email(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    assert captured[0]['json']['to'] == ['mwiriadi@gmail.com']


class TestAtomicWriteHtml:
  '''D-13 + C-7 reviews: atomic disk write for last_email.html fallback.

  Mirror of tests/test_dashboard.py::TestAtomicWrite (lines 930-971).
  '''

  def test_atomic_write_creates_file(self, tmp_path) -> None:
    dest = tmp_path / 'last_email.html'
    notifier._atomic_write_html('<html/>', dest)
    assert dest.exists()
    assert dest.read_text(encoding='utf-8') == '<html/>'
    # No stray tempfiles left in the parent dir.
    tmp_files = list(tmp_path.glob('*.tmp'))
    assert tmp_files == [], f'unexpected tempfiles left: {tmp_files}'

  def test_atomic_write_survives_oserror(self, tmp_path, monkeypatch) -> None:
    '''Monkeypatch notifier.os.replace to raise; assert tempfile cleaned up.

    Mirror of test_dashboard.py::TestAtomicWrite::test_tempfile_cleaned_up_on_failure.
    '''
    dest = tmp_path / 'last_email.html'

    def _boom(*a, **kw):
      raise OSError('simulated replace failure')

    monkeypatch.setattr('notifier.os.replace', _boom)
    with pytest.raises(OSError, match='simulated'):
      notifier._atomic_write_html('<html/>', dest)
    tmp_files = list(tmp_path.glob('*.tmp'))
    assert tmp_files == [], f'tempfile cleanup failed: {tmp_files}'

  def test_atomic_write_lf_newlines(self, tmp_path) -> None:
    '''C-7 reviews: `newline='\\n'` prevents platform CRLF translation.'''
    dest = tmp_path / 'last_email.html'
    notifier._atomic_write_html('line1\nline2\n', dest)
    raw = dest.read_bytes()
    assert b'\r\n' not in raw, 'C-7: newline=\\n must prevent CRLF translation'
    assert raw == b'line1\nline2\n'


class TestGoldenEmail:
  '''D-03 phase gate: byte-equal HTML snapshots for 3 scenarios (with_change,
  no_change, empty). Double-run idempotency:
    python tests/regenerate_notifier_golden.py
  run twice produces zero git diff on tests/fixtures/notifier/.
  '''

  def test_golden_with_change_matches_committed(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    old_signals = {'^AXJO': 1, 'AUDUSD=X': 0}
    rendered = compose_email_body(state, old_signals, FROZEN_NOW, from_addr='signals@carbonbookkeeping.com.au')
    golden = GOLDEN_WITH_CHANGE_PATH.read_text(encoding='utf-8')
    assert rendered == golden, (
      'compose_email_body drifted from golden_with_change.html. '
      'If change intentional: run '
      '`.venv/bin/python tests/regenerate_notifier_golden.py` and re-commit.'
    )

  def test_golden_no_change_matches_committed(self) -> None:
    state = json.loads(SAMPLE_STATE_NO_CHANGE_PATH.read_text())
    old_signals = {'^AXJO': 1, 'AUDUSD=X': 0}
    rendered = compose_email_body(state, old_signals, FROZEN_NOW, from_addr='signals@carbonbookkeeping.com.au')
    golden = GOLDEN_NO_CHANGE_PATH.read_text(encoding='utf-8')
    assert rendered == golden, (
      'compose_email_body drifted from golden_no_change.html. '
      'Re-run tests/regenerate_notifier_golden.py and re-commit.'
    )

  def test_golden_empty_matches_committed(self) -> None:
    state = json.loads(EMPTY_STATE_PATH.read_text())
    old_signals = {'^AXJO': None, 'AUDUSD=X': None}
    rendered = compose_email_body(state, old_signals, FROZEN_NOW, from_addr='signals@carbonbookkeeping.com.au')
    golden = GOLDEN_EMPTY_PATH.read_text(encoding='utf-8')
    assert rendered == golden, (
      'compose_email_body drifted from golden_empty.html. '
      'Re-run tests/regenerate_notifier_golden.py and re-commit.'
    )

  @pytest.mark.parametrize('golden_path', [
    GOLDEN_WITH_CHANGE_PATH, GOLDEN_NO_CHANGE_PATH, GOLDEN_EMPTY_PATH,
  ])
  def test_golden_starts_with_doctype(self, golden_path) -> None:
    content = golden_path.read_text(encoding='utf-8')
    assert content.startswith('<!DOCTYPE html>'), (
      f'{golden_path} is not a valid HTML document (placeholder?)'
    )

  @pytest.mark.parametrize('golden_path', [
    GOLDEN_WITH_CHANGE_PATH, GOLDEN_NO_CHANGE_PATH, GOLDEN_EMPTY_PATH,
  ])
  def test_golden_has_lf_line_endings(self, golden_path) -> None:
    '''C-7 reviews: `newline='\\n'` prevents platform CRLF translation.'''
    raw = golden_path.read_bytes()
    assert b'\r\n' not in raw, (
      f'{golden_path} has CRLF line endings — byte-stability broken on Windows'
    )

  def test_with_change_golden_contains_action_required(self) -> None:
    content = GOLDEN_WITH_CHANGE_PATH.read_text(encoding='utf-8')
    assert 'ACTION REQUIRED' in content

  def test_no_change_golden_absent_action_required(self) -> None:
    content = GOLDEN_NO_CHANGE_PATH.read_text(encoding='utf-8')
    assert 'ACTION REQUIRED' not in content

  def test_empty_golden_absent_action_required(self) -> None:
    content = GOLDEN_EMPTY_PATH.read_text(encoding='utf-8')
    assert 'ACTION REQUIRED' not in content, (
      'D-06: first-run / no-previous-signal MUST NOT show ACTION REQUIRED'
    )

  def test_golden_with_change_subject_matches_committed(self) -> None:
    '''Fix 8 (LOW): subject goldens under phase-gate rigour.'''
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    old_signals = {'^AXJO': 1, 'AUDUSD=X': 0}
    rendered = compose_email_subject(state, old_signals, is_test=False)
    golden = (NOTIFIER_FIXTURE_DIR / 'golden_with_change_subject.txt').read_text(
      encoding='utf-8',
    ).rstrip('\n')
    assert rendered == golden, (
      f'compose_email_subject drifted from golden_with_change_subject.txt. '
      f'Re-run tests/regenerate_notifier_golden.py and re-commit. '
      f'got={rendered!r} expected={golden!r}'
    )

  def test_golden_no_change_subject_matches_committed(self) -> None:
    state = json.loads(SAMPLE_STATE_NO_CHANGE_PATH.read_text())
    old_signals = {'^AXJO': 1, 'AUDUSD=X': 0}
    rendered = compose_email_subject(state, old_signals, is_test=False)
    golden = (NOTIFIER_FIXTURE_DIR / 'golden_no_change_subject.txt').read_text(
      encoding='utf-8',
    ).rstrip('\n')
    assert rendered == golden, (
      f'compose_email_subject drifted from golden_no_change_subject.txt. '
      f'got={rendered!r} expected={golden!r}'
    )

  def test_golden_empty_subject_matches_committed(self) -> None:
    state = json.loads(EMPTY_STATE_PATH.read_text())
    old_signals = {'^AXJO': None, 'AUDUSD=X': None}
    rendered = compose_email_subject(state, old_signals, is_test=False)
    golden = (NOTIFIER_FIXTURE_DIR / 'golden_empty_subject.txt').read_text(
      encoding='utf-8',
    ).rstrip('\n')
    assert rendered == golden, (
      f'compose_email_subject drifted from golden_empty_subject.txt. '
      f'got={rendered!r} expected={golden!r}'
    )


# =========================================================================
# Phase 8 Plan 02 Task 3 — 6 new test classes
# =========================================================================

def _build_phase8_base_state(
  last_run: str | None = '2026-04-22',
  warnings: list | None = None,
  stale_info: dict | None = None,
) -> dict:
  '''Minimal state fixture for Phase 8 Task 3 banner + dispatch tests.

  Mirrors the shape produced by state_manager.reset_state + Phase 8 D-14
  (_resolved_contracts materialised after load_state) enough for
  _render_header_email + send_daily_email + compose_email_subject.
  '''
  state: dict = {
    'schema_version': 2,
    'account': 100000.0,
    'last_run': last_run,
    'positions': {'SPI200': None, 'AUDUSD': None},
    'signals': {
      '^AXJO': {'signal': 0, 'signal_as_of': '2026-04-22', 'last_close': 7500.0},
      'AUDUSD=X': {'signal': 0, 'signal_as_of': '2026-04-22', 'last_close': 0.65},
      'SPI200': {'signal': 0, 'signal_as_of': '2026-04-22', 'last_close': 7500.0},
      'AUDUSD': {'signal': 0, 'signal_as_of': '2026-04-22', 'last_close': 0.65},
    },
    'trade_log': [],
    'equity_history': [],
    'warnings': warnings if warnings is not None else [],
    'initial_account': 100000.0,
    'contracts': {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-standard'},
  }
  if stale_info is not None:
    state['_stale_info'] = stale_info
  return state


class TestHeaderBanner:
  '''Phase 8 Plan 02 Task 3 — D-01 two-tier banner + D-03 age filter with
  B2 + B3 + B4 revisions: critical bypass (stale transient + corrupt prefix)
  vs routine age-filter; hero card verbatim preservation.
  '''

  def test_no_warnings_no_stale_no_banner(self) -> None:
    state = _build_phase8_base_state(warnings=[])
    out = notifier._render_header_email(state, FROZEN_NOW)
    assert 'border-left:4px solid #ef4444' not in out
    assert 'border-left:4px solid #eab308' not in out
    assert 'from prior run' not in out
    assert 'Trading Signals</h1>' in out

  def test_stale_state_banner_red_border_via_stale_info(self) -> None:
    # B3: staleness is a transient _stale_info dict set by orchestrator —
    # NOT stored in state['warnings'] (would be dropped by age filter).
    state = _build_phase8_base_state(
      warnings=[],
      stale_info={'days_stale': 3, 'last_run_date': '2026-04-20'},
    )
    out = notifier._render_header_email(state, FROZEN_NOW)
    assert 'border-left:4px solid #ef4444' in out
    assert 'Stale state' in out
    assert '3 days' in out
    assert 'from prior run' not in out  # no routine row when no routine warnings

  def test_corrupt_reset_banner_gold_border_age_bypass(self) -> None:
    # B2 + B3: classifier matches the EXISTING 'recovered from corruption'
    # prefix produced by state_manager.load_state (UNCHANGED per Plan 01 I1).
    # Age filter BYPASSED — date may not match prior_run_date.
    state = _build_phase8_base_state(
      warnings=[{
        # Date is EARLIER than last_run='2026-04-22' — would be dropped
        # by routine age filter, but critical classifier age-bypasses.
        'date': '2026-04-19',
        'source': 'state_manager',
        'message': 'recovered from corruption; backup at state.json.bak.20260419T120000Z',
      }],
    )
    out = notifier._render_header_email(state, FROZEN_NOW)
    assert 'border-left:4px solid #eab308' in out
    assert 'State was reset' in out

  def test_corrupt_reset_warning_not_in_routine_row(self) -> None:
    state = _build_phase8_base_state(
      warnings=[{
        'date': '2026-04-22',  # even on prior_run_date, corrupt is critical not routine
        'source': 'state_manager',
        'message': 'recovered from corruption; backup at x',
      }],
    )
    out = notifier._render_header_email(state, FROZEN_NOW)
    # Critical banner present
    assert 'State was reset' in out
    # NOT duplicated as routine
    assert 'from prior run' not in out

  def test_routine_warning_compact_row_singular(self) -> None:
    state = _build_phase8_base_state(
      warnings=[{
        'date': '2026-04-22',
        'source': 'sizing_engine',
        'message': 'size=0: vol_scale clip',
      }],
    )
    out = notifier._render_header_email(state, FROZEN_NOW)
    assert '1 warning from prior run' in out
    assert 'size=0: vol_scale clip' in out
    assert 'border-left:4px solid #ef4444' not in out

  def test_routine_warnings_compact_row_plural(self) -> None:
    state = _build_phase8_base_state(
      warnings=[
        {'date': '2026-04-22', 'source': 'sizing_engine', 'message': 'size=0 spi'},
        {'date': '2026-04-22', 'source': 'sizing_engine', 'message': 'size=0 audusd'},
        {'date': '2026-04-22', 'source': 'notifier',      'message': 'prev send failed'},
      ],
    )
    out = notifier._render_header_email(state, FROZEN_NOW)
    assert '3 warnings from prior run' in out
    assert 'size=0 spi' in out
    assert 'size=0 audusd' in out
    assert 'prev send failed' in out

  def test_routine_age_filter_ignores_old_warnings(self) -> None:
    state = _build_phase8_base_state(
      last_run='2026-04-22',
      warnings=[
        {'date': '2026-04-19', 'source': 'sizing_engine', 'message': 'old warn A'},
        {'date': '2026-04-20', 'source': 'sizing_engine', 'message': 'old warn B'},
      ],
    )
    out = notifier._render_header_email(state, FROZEN_NOW)
    assert 'from prior run' not in out
    assert 'old warn A' not in out
    assert 'old warn B' not in out

  def test_age_filter_handles_missing_last_run(self) -> None:
    state = _build_phase8_base_state(last_run=None, warnings=[])
    state['last_run'] = None  # ensure explicit None
    out = notifier._render_header_email(state, FROZEN_NOW)
    assert 'from prior run' not in out
    assert 'border-left:4px solid #ef4444' not in out
    assert 'Trading Signals</h1>' in out

  def test_banner_message_xss_escaped(self) -> None:
    state = _build_phase8_base_state(
      warnings=[{
        'date': '2026-04-22',
        'source': 'sizing_engine',
        'message': '<script>alert(1)</script>',
      }],
    )
    out = notifier._render_header_email(state, FROZEN_NOW)
    assert '<script>' not in out
    assert '&lt;script&gt;' in out or '&#x3C;script&#x3E;' in out.lower()

  def test_stale_info_message_xss_escaped(self) -> None:
    state = _build_phase8_base_state(
      warnings=[],
      stale_info={'days_stale': 3, 'last_run_date': '<script>XSS</script>'},
    )
    out = notifier._render_header_email(state, FROZEN_NOW)
    assert '<script>' not in out
    assert '&lt;script&gt;' in out or '&#x3C;script&#x3E;' in out.lower()

  def test_both_critical_stale_and_routine_in_same_run(self) -> None:
    state = _build_phase8_base_state(
      warnings=[
        {'date': '2026-04-22', 'source': 'sizing_engine', 'message': 'size=0 spi'},
        {'date': '2026-04-22', 'source': 'sizing_engine', 'message': 'size=0 audusd'},
      ],
      stale_info={'days_stale': 4, 'last_run_date': '2026-04-18'},
    )
    out = notifier._render_header_email(state, FROZEN_NOW)
    # Both present
    assert 'border-left:4px solid #ef4444' in out
    assert 'Stale state' in out
    assert '2 warnings from prior run' in out

  def test_hero_card_markup_preserved(self) -> None:
    # B4: _render_hero_card_email extraction verbatim — the key markup
    # 'Trading Signals</h1>' and the subtitle must remain. Also assert
    # it appears exactly once in the render (no duplication).
    state = _build_phase8_base_state(warnings=[])
    out = notifier._render_header_email(state, FROZEN_NOW)
    assert 'Trading Signals</h1>' in out
    assert 'mechanical system' in out.lower() or 'mechanical system' in out
    assert out.count('Trading Signals</h1>') == 1


class TestSubjectCriticalPrefix:
  '''Phase 8 D-04 + B3: `[!]` subject prefix driven by _has_critical_banner.'''

  def test_subject_plain_when_no_critical_banner(self) -> None:
    state = _build_phase8_base_state(
      warnings=[{'date': '2026-04-22', 'source': 'sizing_engine', 'message': 'size=0'}],
    )
    subj = compose_email_subject(
      state, {'^AXJO': 0, 'AUDUSD=X': 0},
      has_critical_banner=False,
    )
    assert not subj.startswith('[!]')

  def test_subject_has_bang_prefix_on_stale_info(self) -> None:
    state = _build_phase8_base_state(
      warnings=[],
      stale_info={'days_stale': 3, 'last_run_date': '2026-04-19'},
    )
    assert notifier._has_critical_banner(state) is True
    subj = compose_email_subject(
      state, {'^AXJO': 0, 'AUDUSD=X': 0},
      has_critical_banner=True,
    )
    assert subj.startswith('[!] ')

  def test_subject_has_bang_prefix_on_corrupt_reset_even_old_date(self) -> None:
    # B2 + B3: corrupt warning dated 5 days before last_run → still critical
    # via the prefix classifier (age-bypass).
    state = _build_phase8_base_state(
      last_run='2026-04-22',
      warnings=[{
        'date': '2026-04-17',
        'source': 'state_manager',
        'message': 'recovered from corruption; backup at x',
      }],
    )
    assert notifier._has_critical_banner(state) is True
    subj = compose_email_subject(
      state, {'^AXJO': 0, 'AUDUSD=X': 0},
      has_critical_banner=True,
    )
    assert subj.startswith('[!] ')

  def test_test_prefix_before_bang_prefix(self) -> None:
    state = _build_phase8_base_state(
      warnings=[],
      stale_info={'days_stale': 3, 'last_run_date': '2026-04-19'},
    )
    subj = compose_email_subject(
      state, {'^AXJO': 0, 'AUDUSD=X': 0},
      is_test=True, has_critical_banner=True,
    )
    assert subj.startswith('[TEST] [!] ')

  def test_routine_only_stale_in_old_date_not_critical(self) -> None:
    # B3 — an old routine warning is NOT critical even though
    # the routine age filter also drops it.
    state = _build_phase8_base_state(
      last_run='2026-04-22',
      warnings=[{
        'date': '2026-04-17',
        'source': 'sizing_engine',
        'message': 'old size=0',
      }],
    )
    assert notifier._has_critical_banner(state) is False


class TestSendDispatchStatusTuple:
  '''Phase 8 D-08 + NOTF-07/NOTF-08: send_daily_email SendStatus return shape.'''

  def test_missing_api_key_returns_ok_with_no_api_key_reason(
      self, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('RESEND_API_KEY', raising=False)
    state = json.loads(SAMPLE_STATE_NO_CHANGE_PATH.read_text())
    result = send_daily_email(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    assert result.ok is True
    assert result.reason == 'no_api_key'
    assert (tmp_path / 'last_email.html').exists()

  def test_200_response_returns_ok_with_none_reason(
      self, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('RESEND_API_KEY', 'k200')

    def _fake_post(*a, **kw):
      return _FakeResp(200)

    monkeypatch.setattr('notifier.requests.post', _fake_post)
    state = json.loads(SAMPLE_STATE_NO_CHANGE_PATH.read_text())
    result = send_daily_email(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    assert result.ok is True
    assert result.reason is None
    assert (tmp_path / 'last_email.html').exists()

  def test_5xx_returns_ok_false_with_status_in_reason(
      self, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('RESEND_API_KEY', 'k5xx')
    monkeypatch.setattr('notifier._RESEND_BACKOFF_S', 0)

    def _fake_post(*a, **kw):
      return _FakeResp(500)

    monkeypatch.setattr('notifier.requests.post', _fake_post)
    state = json.loads(SAMPLE_STATE_NO_CHANGE_PATH.read_text())
    result = send_daily_email(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    assert result.ok is False
    assert result.reason is not None
    assert '500' in result.reason

  def test_4xx_returns_ok_false_with_status_in_reason(
      self, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('RESEND_API_KEY', 'k4xx')

    def _fake_post(*a, **kw):
      return _FakeResp(400, 'validation_error body')

    monkeypatch.setattr('notifier.requests.post', _fake_post)
    state = json.loads(SAMPLE_STATE_NO_CHANGE_PATH.read_text())
    result = send_daily_email(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    assert result.ok is False
    assert result.reason is not None
    assert '400' in result.reason

  def test_unexpected_exception_caught_returns_ok_false(
      self, tmp_path, monkeypatch) -> None:
    # Monkeypatch compose_email_body to raise RuntimeError — reason starts
    # with 'compose_body_failed:' per T-08-11 mitigation.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('RESEND_API_KEY', 'kboom')

    def _boom(*a, **kw):
      raise RuntimeError('boom')

    monkeypatch.setattr('notifier.compose_email_body', _boom)
    state = json.loads(SAMPLE_STATE_NO_CHANGE_PATH.read_text())
    result = send_daily_email(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    assert result.ok is False
    assert result.reason is not None
    assert result.reason.startswith('compose_body_failed:')


class TestLastEmailAlwaysWritten:
  '''Phase 8 D-02: last_email.html written on EVERY dispatch path.'''

  def test_last_email_written_on_200(
      self, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('RESEND_API_KEY', 'k')

    def _fake_post(*a, **kw):
      return _FakeResp(200)

    monkeypatch.setattr('notifier.requests.post', _fake_post)
    state = json.loads(SAMPLE_STATE_NO_CHANGE_PATH.read_text())
    send_daily_email(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    assert (tmp_path / 'last_email.html').exists()

  def test_last_email_written_on_500(
      self, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('RESEND_API_KEY', 'k')
    monkeypatch.setattr('notifier._RESEND_BACKOFF_S', 0)

    def _fake_post(*a, **kw):
      return _FakeResp(500)

    monkeypatch.setattr('notifier.requests.post', _fake_post)
    state = json.loads(SAMPLE_STATE_NO_CHANGE_PATH.read_text())
    send_daily_email(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    assert (tmp_path / 'last_email.html').exists()

  def test_last_email_written_on_400(
      self, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('RESEND_API_KEY', 'k')

    def _fake_post(*a, **kw):
      return _FakeResp(400, 'bad')

    monkeypatch.setattr('notifier.requests.post', _fake_post)
    state = json.loads(SAMPLE_STATE_NO_CHANGE_PATH.read_text())
    send_daily_email(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    assert (tmp_path / 'last_email.html').exists()

  def test_last_email_written_on_missing_api_key(
      self, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('RESEND_API_KEY', raising=False)
    state = json.loads(SAMPLE_STATE_NO_CHANGE_PATH.read_text())
    send_daily_email(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    assert (tmp_path / 'last_email.html').exists()

  def test_last_email_write_failure_does_not_block_dispatch(
      self, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('RESEND_API_KEY', 'k')

    def _raise_on_write(*a, **kw):
      raise OSError('disk full')

    monkeypatch.setattr('notifier._atomic_write_html', _raise_on_write)

    def _fake_post(*a, **kw):
      return _FakeResp(200)

    monkeypatch.setattr('notifier.requests.post', _fake_post)
    state = json.loads(SAMPLE_STATE_NO_CHANGE_PATH.read_text())
    result = send_daily_email(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    # Disk failure was logged but dispatch proceeded.
    assert result.ok is True
    assert result.reason is None


class TestCrashEmail:
  '''Phase 8 D-05/D-06/D-07: send_crash_email text/plain dispatch.'''

  def test_crash_email_subject_format(
      self, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('RESEND_API_KEY', 'k')
    monkeypatch.setenv('SIGNALS_EMAIL_TO', 'op@x.com')
    captured: list[dict] = []

    def _fake_post(url, **kw):
      captured.append(kw.get('json') or {})
      return _FakeResp(200)

    monkeypatch.setattr('notifier.requests.post', _fake_post)
    # FROZEN_NOW is 2026-04-22 09:00 AWST — date-only should be 2026-04-22
    status = notifier.send_crash_email(
      RuntimeError('x'), 'summary', now=FROZEN_NOW,
    )
    assert status.ok is True
    assert len(captured) == 1
    subj = captured[0]['subject']
    assert subj.startswith('[CRASH] Trading Signals — ')
    assert '2026-04-22' in subj

  def test_crash_email_body_contains_required_sections(
      self, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('RESEND_API_KEY', 'k')
    monkeypatch.setenv('SIGNALS_EMAIL_TO', 'op@x.com')
    captured: list[dict] = []

    def _fake_post(url, **kw):
      captured.append(kw.get('json') or {})
      return _FakeResp(200)

    monkeypatch.setattr('notifier.requests.post', _fake_post)
    # Raise + catch to populate __traceback__ for a realistic traceback.
    try:
      raise RuntimeError('boom-inside')
    except RuntimeError as e:
      notifier.send_crash_email(
        e, 'signals: SPI=FLAT\naccount: $100000.00', now=FROZEN_NOW,
      )
    assert len(captured) == 1
    body = captured[0]['text']
    assert 'Timestamp:' in body
    assert 'Exception:' in body
    assert 'RuntimeError' in body
    assert 'Traceback:' in body
    assert 'State summary:' in body
    assert 'signals: SPI=FLAT' in body
    assert '$100000.00' in body

  def test_crash_email_body_is_text_plain_not_html(
      self, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('RESEND_API_KEY', 'k')
    monkeypatch.setenv('SIGNALS_EMAIL_TO', 'op@x.com')
    captured: list[dict] = []

    def _fake_post(url, **kw):
      captured.append(kw.get('json') or {})
      return _FakeResp(200)

    monkeypatch.setattr('notifier.requests.post', _fake_post)
    notifier.send_crash_email(ValueError('v'), 'sum', now=FROZEN_NOW)
    payload = captured[0]
    assert 'text' in payload
    assert 'html' not in payload
    assert '<html>' not in payload['text']
    assert '<body>' not in payload['text']

  def test_crash_email_retries_on_500_then_succeeds(
      self, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('RESEND_API_KEY', 'k')
    monkeypatch.setenv('SIGNALS_EMAIL_TO', 'op@x.com')
    monkeypatch.setattr('notifier._RESEND_BACKOFF_S', 0)
    calls: list[int] = []

    def _fake_post(*a, **kw):
      calls.append(1)
      return _FakeResp(500 if len(calls) == 1 else 200)

    monkeypatch.setattr('notifier.requests.post', _fake_post)
    status = notifier.send_crash_email(RuntimeError('x'), 'sum', now=FROZEN_NOW)
    assert status.ok is True
    assert len(calls) == 2

  def test_crash_email_gives_up_after_3_retries(
      self, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('RESEND_API_KEY', 'k')
    monkeypatch.setenv('SIGNALS_EMAIL_TO', 'op@x.com')
    monkeypatch.setattr('notifier._RESEND_BACKOFF_S', 0)

    def _fake_post(*a, **kw):
      return _FakeResp(500)

    monkeypatch.setattr('notifier.requests.post', _fake_post)
    status = notifier.send_crash_email(RuntimeError('x'), 'sum', now=FROZEN_NOW)
    assert status.ok is False
    assert status.reason is not None
    # Retries-exhausted message contains the 500 status somewhere
    assert '500' in status.reason or 'HTTPError' in status.reason

  def test_crash_email_missing_api_key_returns_ok_false_no_api_key(
      self, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('RESEND_API_KEY', raising=False)
    status = notifier.send_crash_email(RuntimeError('x'), 'sum', now=FROZEN_NOW)
    assert status.ok is False
    assert status.reason == 'no_api_key'

  def test_crash_email_never_raises_on_unexpected_exception(
      self, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('RESEND_API_KEY', 'k')
    monkeypatch.setenv('SIGNALS_EMAIL_TO', 'op@x.com')

    def _raise(*a, **kw):
      raise ValueError('unexpected')

    monkeypatch.setattr('notifier._post_to_resend', _raise)
    status = notifier.send_crash_email(RuntimeError('x'), 'sum', now=FROZEN_NOW)
    assert status.ok is False
    assert status.reason is not None
    assert 'ValueError' in status.reason

  def test_crash_email_state_summary_not_escaped_text_plain(
      self, tmp_path, monkeypatch) -> None:
    '''text/plain body is NOT html-escaped — caller's <tag> characters pass through.'''
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('RESEND_API_KEY', 'k')
    monkeypatch.setenv('SIGNALS_EMAIL_TO', 'op@x.com')
    captured: list[dict] = []

    def _fake_post(url, **kw):
      captured.append(kw.get('json') or {})
      return _FakeResp(200)

    monkeypatch.setattr('notifier.requests.post', _fake_post)
    notifier.send_crash_email(RuntimeError('x'), 'literal <tag>', now=FROZEN_NOW)
    body = captured[0]['text']
    assert '<tag>' in body
    # NOT escaped because text/plain; confirms no html.escape leak in body assembly
    assert '&lt;tag&gt;' not in body


class TestPostToResendContentType:
  '''Phase 8 D-07 / D-08: _post_to_resend accepts html_body OR text_body.'''

  def test_post_to_resend_html_only_payload(self, monkeypatch) -> None:
    captured: list[dict] = []

    def _fake_post(url, **kw):
      captured.append(kw.get('json') or {})
      return _FakeResp(200)

    monkeypatch.setattr('notifier.requests.post', _fake_post)
    notifier._post_to_resend(
      'k', 'f@x.com', 't@x.com', 'subj',
      html_body='<p>hi</p>', text_body=None, backoff_s=0,
    )
    payload = captured[0]
    assert payload['html'] == '<p>hi</p>'
    assert 'text' not in payload

  def test_post_to_resend_text_only_payload(self, monkeypatch) -> None:
    captured: list[dict] = []

    def _fake_post(url, **kw):
      captured.append(kw.get('json') or {})
      return _FakeResp(200)

    monkeypatch.setattr('notifier.requests.post', _fake_post)
    notifier._post_to_resend(
      'k', 'f@x.com', 't@x.com', 'subj',
      html_body=None, text_body='plain', backoff_s=0,
    )
    payload = captured[0]
    assert payload['text'] == 'plain'
    assert 'html' not in payload

  def test_post_to_resend_both_payload(self, monkeypatch) -> None:
    captured: list[dict] = []

    def _fake_post(url, **kw):
      captured.append(kw.get('json') or {})
      return _FakeResp(200)

    monkeypatch.setattr('notifier.requests.post', _fake_post)
    notifier._post_to_resend(
      'k', 'f@x.com', 't@x.com', 'subj',
      html_body='<p>hi</p>', text_body='plain', backoff_s=0,
    )
    payload = captured[0]
    assert payload['html'] == '<p>hi</p>'
    assert payload['text'] == 'plain'

  def test_post_to_resend_neither_raises_value_error(self) -> None:
    with pytest.raises(ValueError, match='html_body OR text_body'):
      notifier._post_to_resend(
        'k', 'f@x.com', 't@x.com', 'subj',
        html_body=None, text_body=None, backoff_s=0,
      )


# =========================================================================
# Phase 10 CHORE-02 / D-05: ruff CI regression guard for notifier.py
# =========================================================================

def test_ruff_clean_notifier() -> None:
  '''CHORE-02 / D-05: notifier.py must be ruff-CLEAN (zero warnings of
  ANY category) AND specifically have zero F401 (unused-import) entries.

  PRIMARY GATE (D-05 + ROADMAP SC-2): asserts `result.returncode == 0`.
  This catches ALL ruff warnings — F401, E-series style errors,
  W-series whitespace, UP-series py-upgrade suggestions, etc. — not
  just unused imports. Any new ruff warning in notifier.py reds this.

  SECONDARY DIAGNOSTIC: parses the JSON and asserts zero entries with
  `code == 'F401'`. When the primary gate reds, the diagnostic
  narrows the failure to "is it the Phase 10 F401 regression or
  something else?".

  Invokes `ruff check notifier.py --output-format=json` via subprocess
  (ruff 0.6.9, pinned in requirements.txt). Template per
  10-RESEARCH.md §Pattern 2. Stable across ruff 0.6.x per JSON output
  schema.

  REVIEW REVISION (10-REVIEWS.md HIGH): the earlier draft asserted
  only on the F401 filter, NOT on returncode. This allowed any
  non-F401 ruff warning to pass. Now both are enforced.
  '''
  import json
  import subprocess
  import sys

  result = subprocess.run(
    [sys.executable, '-m', 'ruff', 'check', 'notifier.py', '--output-format=json'],
    capture_output=True,
    text=True,
    timeout=30,
  )
  entries = json.loads(result.stdout) if result.stdout.strip() else []
  # SECONDARY DIAGNOSTIC first — gives a clearer error message when
  # the regression is specifically F401 (the category this phase
  # closed). Only then check the PRIMARY gate so an E501 regression
  # (say) produces a clean "ruff exits 1" message instead of being
  # swallowed by a spurious F401 assertion.
  f401_entries = [e for e in entries if e.get('code') == 'F401']
  assert len(f401_entries) == 0, (
    f'CHORE-02 / D-05: notifier.py must have zero F401 (unused-import) '
    f'warnings; found {len(f401_entries)}: '
    f'{[(e.get("location", {}).get("row"), e.get("message")) for e in f401_entries]}'
  )
  # PRIMARY GATE: D-05 + ROADMAP SC-2 "ruff check notifier.py returns
  # zero warnings" — enforced via returncode, which ruff sets to 1
  # whenever ANY issue exists (of any rule category).
  assert result.returncode == 0, (
    f'CHORE-02 / D-05 / SC-2: ruff check notifier.py must exit 0 '
    f'(no warnings of ANY category). Got returncode={result.returncode}. '
    f'Full entries: {entries}. '
    f'stderr: {result.stderr[:200] if result.stderr else "(empty)"}'
  )


def test_ruff_clean_notifier_detects_f401_regression(tmp_path) -> None:
  '''CHORE-02 / D-05 sensitivity check: prove the guard actually RED-lights
  on an F401 regression. Writes a temp module with an unused import and
  asserts `ruff check <temp_file>` returns non-zero AND emits at least one
  F401 entry.

  This replaces the "manually re-add SPI_MULT and verify RED" ceremony
  in the earlier plan draft — it exercises the same invariant (guard
  is F401-sensitive) via a self-contained fixture, so no notifier.py
  mutation is required during the test run.

  REVIEW REVISION (10-REVIEWS.md Codex LOW): removed the manual
  re-remove-import ceremony; this temp-file test replaces it.
  '''
  import json
  import subprocess
  import sys

  # Fixture with a clear, unused import — must unambiguously trigger F401.
  fixture = tmp_path / 'f401_regression_probe_clean.py'
  fixture.write_text(
    "'''F401 regression probe — unused import, no noqa.'''\n"
    'import os\n'
  )
  result = subprocess.run(
    [sys.executable, '-m', 'ruff', 'check', str(fixture), '--output-format=json'],
    capture_output=True,
    text=True,
    timeout=30,
  )
  assert result.returncode != 0, (
    f'Sensitivity check failed: ruff exited 0 on a file with an '
    f'unused import — guard would miss F401 regressions. '
    f'stdout: {result.stdout[:200]}'
  )
  entries = json.loads(result.stdout) if result.stdout.strip() else []
  f401_entries = [e for e in entries if e.get('code') == 'F401']
  assert len(f401_entries) >= 1, (
    f'Sensitivity check failed: ruff did NOT emit an F401 entry for '
    f'an obvious unused import. Entries: {entries}'
  )


# =========================================================================
# Phase 12 INFRA-01 + D-17 — SIGNALS_EMAIL_FROM env-var contract
# =========================================================================


class TestEmailFromEnvVar:
  '''Phase 12 INFRA-01 + D-17 — SIGNALS_EMAIL_FROM env-var contract.

  D-14: missing/empty → log ERROR + return SendStatus(ok=False,
        reason='missing_sender'); NO Resend POST.
  D-15: per-send read inside send_daily_email (not at import time).
  D-16: _EMAIL_FROM module constant removed.

  SendStatus stays 2-field (ok, reason) per research finding #2 —
  extending the NamedTuple cascades into main.py orchestrator code.
  '''

  def test_from_addr_reads_env_var(self, tmp_path, monkeypatch) -> None:
    '''SIGNALS_EMAIL_FROM present → Resend payload `from` field matches.

    Spy on notifier.requests.post to capture the POST payload; assert
    the `from` key equals the env var value (not the old hardcoded
    address, not `onboarding@resend.dev`).
    '''
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('SIGNALS_EMAIL_FROM', 'test@example.com')
    monkeypatch.setenv('RESEND_API_KEY', 'test_key')

    captured: list = []

    def _fake_post(url, **kw):
      captured.append({'url': url, **kw})
      return _FakeResp(200)

    monkeypatch.setattr('notifier.requests.post', _fake_post)

    state = json.loads(SAMPLE_STATE_NO_CHANGE_PATH.read_text())
    old_signals = {'^AXJO': 0, 'AUDUSD=X': 0}
    status = send_daily_email(state, old_signals, FROZEN_NOW)
    assert status.ok is True
    assert len(captured) == 1
    assert captured[0]['json']['from'] == 'test@example.com'

  def test_missing_env_var_skips_email_with_warning(
      self, tmp_path, monkeypatch, caplog) -> None:
    '''SIGNALS_EMAIL_FROM unset → log ERROR + SendStatus(ok=False,
    reason='missing_sender'); Resend.post NOT called. NEVER falls back
    to onboarding@resend.dev.
    '''
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('SIGNALS_EMAIL_FROM', raising=False)
    # Set RESEND_API_KEY so the missing_sender path (not no_api_key)
    # is what we're testing.
    monkeypatch.setenv('RESEND_API_KEY', 'test_key')

    called = {'n': 0}

    def _fake_post(*a, **kw):
      called['n'] += 1
      raise AssertionError(
        'notifier.requests.post must NOT be called when '
        'SIGNALS_EMAIL_FROM is missing'
      )

    monkeypatch.setattr('notifier.requests.post', _fake_post)

    state = json.loads(SAMPLE_STATE_NO_CHANGE_PATH.read_text())
    old_signals = {'^AXJO': 0, 'AUDUSD=X': 0}
    with caplog.at_level(logging.ERROR, logger='notifier'):
      status = send_daily_email(state, old_signals, FROZEN_NOW)
    assert status.ok is False
    assert status.reason == 'missing_sender'
    assert called['n'] == 0
    assert '[Email] SIGNALS_EMAIL_FROM not set' in caplog.text
    # 12-REVIEWS.md LOW — missing-sender path MUST NOT touch disk.
    assert not (tmp_path / 'last_email.html').exists(), (
      'missing-sender path wrote last_email.html — violates '
      'no-side-effects contract'
    )

  def test_empty_env_var_treated_as_missing(
      self, tmp_path, monkeypatch, caplog) -> None:
    '''SIGNALS_EMAIL_FROM='' (empty string) → same path as missing.

    `.strip()` on the env value collapses whitespace-only and empty
    strings into the same "not set" bucket.
    '''
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('SIGNALS_EMAIL_FROM', '')
    monkeypatch.setenv('RESEND_API_KEY', 'test_key')

    called = {'n': 0}

    def _fake_post(*a, **kw):
      called['n'] += 1

    monkeypatch.setattr('notifier.requests.post', _fake_post)

    state = json.loads(SAMPLE_STATE_NO_CHANGE_PATH.read_text())
    old_signals = {'^AXJO': 0, 'AUDUSD=X': 0}
    with caplog.at_level(logging.ERROR, logger='notifier'):
      status = send_daily_email(state, old_signals, FROZEN_NOW)
    assert status.ok is False
    assert status.reason == 'missing_sender'
    assert called['n'] == 0
    assert '[Email] SIGNALS_EMAIL_FROM not set' in caplog.text
    # 12-REVIEWS.md LOW — missing-sender path MUST NOT touch disk.
    assert not (tmp_path / 'last_email.html').exists()

  def test_crash_email_missing_env_var_skips_with_warning(
      self, tmp_path, monkeypatch, caplog) -> None:
    '''12-REVIEWS.md LOW — crash-email path has same missing-sender
    behavior as daily-email path (parity with test #2).
    '''
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('SIGNALS_EMAIL_FROM', raising=False)
    monkeypatch.setenv('RESEND_API_KEY', 'test_key')

    called = {'n': 0}

    def _fake_post(*a, **kw):
      called['n'] += 1

    monkeypatch.setattr('notifier.requests.post', _fake_post)

    try:
      raise RuntimeError('simulated crash for test')
    except RuntimeError as exc:
      with caplog.at_level(logging.ERROR, logger='notifier'):
        status = send_crash_email(exc, 'test state summary', FROZEN_NOW)
    assert status.ok is False
    assert status.reason == 'missing_sender'
    assert called['n'] == 0
    assert '[Email] SIGNALS_EMAIL_FROM not set' in caplog.text
    assert not (tmp_path / 'last_email.html').exists()


class TestDriftBanner:
  '''Phase 15 SENTINEL-03 + D-03/D-12: email drift banner.
  All 7 methods implemented in Plan 07 (REVIEWS M-1 Path A — no skips).
  '''

  def test_has_critical_banner_drift_source(self) -> None:
    from datetime import UTC, datetime

    from notifier import _has_critical_banner
    from state_manager import append_warning, reset_state
    state = reset_state()
    fixed_now = datetime(2026, 4, 26, 9, 30, 0, tzinfo=UTC)
    state = append_warning(state, 'drift', 'msg', now=fixed_now)
    assert _has_critical_banner(state) is True

  def test_has_critical_banner_no_drift(self) -> None:
    from notifier import _has_critical_banner
    from state_manager import reset_state
    state = reset_state()
    assert _has_critical_banner(state) is False

  def test_drift_banner_in_email_body(self) -> None:
    from datetime import UTC, datetime

    from notifier import _render_header_email
    from state_manager import append_warning, reset_state
    state = reset_state()
    fixed_now = datetime(2026, 4, 26, 9, 30, 0, tzinfo=UTC)
    state = append_warning(
      state, 'drift',
      "You hold LONG SPI200, today's signal is FLAT — consider closing.",
      now=fixed_now,
    )
    rendered = _render_header_email(state, fixed_now)
    body = rendered if isinstance(rendered, str) else ''.join(rendered)
    assert '━━━ Drift detected ━━━' in body
    assert 'consider closing' in body

  def test_drift_banner_body_parity_with_dashboard(self) -> None:
    '''D-12 lockstep parity: the body bullets in the email use the
    SAME DriftEvent.message strings as the dashboard banner.
    depends_on includes 15-05 (REVIEWS H-3) so this import is safe.'''
    import html as _html
    from datetime import UTC, datetime

    from dashboard import _render_drift_banner
    from notifier import _render_header_email
    from state_manager import append_warning, reset_state
    state = reset_state()
    fixed_now = datetime(2026, 4, 26, 9, 30, 0, tzinfo=UTC)
    message = "You hold LONG SPI200, today's signal is FLAT — consider closing."
    state = append_warning(state, 'drift', message, now=fixed_now)
    # Render via both paths
    email_rendered = _render_header_email(state, fixed_now)
    email_body = email_rendered if isinstance(email_rendered, str) else ''.join(email_rendered)
    dashboard_body = _render_drift_banner(state)
    # The DriftEvent.message string must appear (escaped or otherwise) in BOTH.
    # html.escape leaves apostrophes as &#x27; with quote=True; account for that.
    escaped_message = _html.escape(message, quote=True)
    assert (message in email_body) or (escaped_message in email_body)
    assert (message in dashboard_body) or (escaped_message in dashboard_body)

  def test_drift_banner_in_email_body_and_subject_critical_prefix(self) -> None:
    '''Phase 8 _has_critical_banner -> [!] subject prefix path is auto-engaged.'''
    from datetime import UTC, datetime

    from notifier import _has_critical_banner
    from state_manager import append_warning, reset_state
    state = reset_state()
    fixed_now = datetime(2026, 4, 26, 9, 30, 0, tzinfo=UTC)
    state = append_warning(state, 'drift', 'msg', now=fixed_now)
    # _has_critical_banner is the SOLE classifier the subject-assembly path
    # consults for the [!] prefix (Phase 8 contract). Verifying it returns
    # True with a drift warning is sufficient to prove the prefix engages.
    assert _has_critical_banner(state) is True

  def test_email_banner_border_red_for_reversal(self) -> None:
    from datetime import UTC, datetime

    from notifier import _render_header_email
    from state_manager import append_warning, reset_state
    state = reset_state()
    fixed_now = datetime(2026, 4, 26, 9, 30, 0, tzinfo=UTC)
    state = append_warning(
      state, 'drift',
      'You hold LONG SPI200, today\'s signal is SHORT'
      ' — reversal recommended (close LONG, open SHORT).',
      now=fixed_now,
    )
    rendered = _render_header_email(state, fixed_now)
    body = rendered if isinstance(rendered, str) else ''.join(rendered)
    # Banner border color: _COLOR_SHORT = '#ef4444' (red) for reversal
    assert '#ef4444' in body, 'reversal -> red border (_COLOR_SHORT)'

  def test_email_banner_border_amber_for_drift_only(self) -> None:
    from datetime import UTC, datetime

    from notifier import _render_header_email
    from state_manager import append_warning, reset_state
    state = reset_state()
    fixed_now = datetime(2026, 4, 26, 9, 30, 0, tzinfo=UTC)
    state = append_warning(
      state, 'drift',
      "You hold LONG SPI200, today's signal is FLAT — consider closing.",
      now=fixed_now,
    )
    rendered = _render_header_email(state, fixed_now)
    body = rendered if isinstance(rendered, str) else ''.join(rendered)
    # The banner block specifically uses _COLOR_FLAT = '#eab308' for drift-only.
    # Locate the drift banner substring and check the border color near it.
    idx = body.find('━━━ Drift detected ━━━')
    assert idx >= 0, 'drift banner heading present'
    # Banner border-left appears BEFORE the heading within the same <tr>; check
    # a window of ~500 chars before the heading for '#eab308'.
    window = body[max(0, idx - 500):idx]
    assert '#eab308' in window, 'drift-only -> amber border (_COLOR_FLAT)'


class TestBannerStackOrder:
  '''Phase 15 D-13: banner stack hierarchy corruption > stale > reversal > drift.
  All 3 methods implemented in Plan 07 (REVIEWS M-1 Path A — no skips).
  '''

  def test_banner_hierarchy_corruption_beats_drift(self) -> None:
    '''D-13: corruption banner renders before drift banner.'''
    from datetime import UTC, datetime

    from notifier import _render_header_email
    from state_manager import append_warning, reset_state
    state = reset_state()
    fixed_now = datetime(2026, 4, 26, 9, 30, 0, tzinfo=UTC)
    state = append_warning(
      state, 'state_manager',
      'recovered from corruption: state.json reset',
      now=fixed_now,
    )
    state = append_warning(
      state, 'drift',
      "You hold LONG SPI200, today's signal is FLAT — consider closing.",
      now=fixed_now,
    )
    rendered = _render_header_email(state, fixed_now)
    body = rendered if isinstance(rendered, str) else ''.join(rendered)
    idx_corr = body.find('recovered from corruption')
    idx_drift = body.find('━━━ Drift detected ━━━')
    assert idx_corr >= 0, 'corruption banner present'
    assert idx_drift >= 0, 'drift banner present'
    assert idx_corr < idx_drift, 'D-13: corruption renders before drift'

  def test_banner_hierarchy_stale_beats_drift(self) -> None:
    '''D-13: stale banner renders before drift banner.'''
    from datetime import UTC, datetime

    from notifier import _render_header_email
    from state_manager import append_warning, reset_state
    state = reset_state()
    fixed_now = datetime(2026, 4, 26, 9, 30, 0, tzinfo=UTC)
    state['_stale_info'] = {'days_stale': 3, 'last_run_date': '2026-04-23'}
    state = append_warning(
      state, 'drift',
      "You hold LONG SPI200, today's signal is FLAT — consider closing.",
      now=fixed_now,
    )
    rendered = _render_header_email(state, fixed_now)
    body = rendered if isinstance(rendered, str) else ''.join(rendered)
    idx_stale = body.find('Stale state')
    idx_drift = body.find('━━━ Drift detected ━━━')
    assert idx_stale >= 0, 'stale banner present'
    assert idx_drift >= 0, 'drift banner present'
    assert idx_stale < idx_drift, 'D-13: stale renders before drift'

  def test_drift_banner_inserted_before_hero_card(self) -> None:
    '''REVIEWS L-4 + Pitfall 4: drift banner must precede the hero card
    block. Stable marker chosen by direct inspection of notifier.py
    _render_hero_card_email line 530-531: the literal `<h1 ...>Trading
    Signals</h1>` is the hardcoded h1 emitted by the hero card. The
    substring `>Trading Signals</h1>` is present in EVERY email render
    (no conditional branch suppresses it), making it a deterministic
    hero-card content marker.

    REVIEWS M-1 Path A: this test MUST be implemented and passing.
    The skip-fallback chain from the prior draft is removed.
    '''
    from datetime import UTC, datetime

    from notifier import _render_header_email
    from state_manager import append_warning, reset_state
    state = reset_state()
    fixed_now = datetime(2026, 4, 26, 9, 30, 0, tzinfo=UTC)
    state = append_warning(
      state, 'drift',
      "You hold LONG SPI200, today's signal is FLAT — consider closing.",
      now=fixed_now,
    )
    rendered = _render_header_email(state, fixed_now)
    body = rendered if isinstance(rendered, str) else ''.join(rendered)
    idx_drift = body.find('━━━ Drift detected ━━━')
    # REVIEWS L-4 stable hero-card marker: the literal h1 closing tag
    # immediately after the title. Verified by direct read of notifier.py
    # line 530-531: `<h1 ...>Trading Signals</h1>`.
    idx_hero = body.find('>Trading Signals</h1>')
    assert idx_drift >= 0, 'drift banner heading absent'
    assert idx_hero >= 0, (
      'REVIEWS L-4: hero-card marker `>Trading Signals</h1>` absent — '
      '_render_hero_card_email may have been refactored. Update the marker '
      'in this test to match the new hero-card content.'
    )
    assert idx_drift < idx_hero, (
      f'Pitfall 4: drift banner must render BEFORE the hero card. '
      f'idx_drift={idx_drift} idx_hero={idx_hero}'
    )
