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
  Wave 1 (06-02) fills 6 cases: change day (🔴), no-change day (📊), [TEST] prefix
  ordering, first-run (📊 per D-06), equity rounding, empty state.
  '''

  def test_scaffold_placeholder_compose_subject(self) -> None:
    '''Nyquist Dimension 8: placeholder for NOTF-02 — passes via
    pytest.raises(NotImplementedError). Wave 1 (06-02) replaces this
    with real compose_email_subject cases.
    '''
    with pytest.raises(NotImplementedError, match='Wave 1'):
      compose_email_subject({}, {}, is_test=False)


class TestComposeBody:
  '''D-07/D-08/D-10/D-11: 7-section HTML body, ACTION REQUIRED conditional,
  palette inline, XSS escape on state-derived strings, mobile markup.
  Wave 1 (06-02) fills section-order + ACTION REQUIRED + first-run + XSS + formatters.
  Wave 2 (06-03) adds byte-equal goldens.
  '''

  def test_scaffold_placeholder_compose_body(self) -> None:
    '''Nyquist Dimension 8: placeholder for NOTF-03..06, NOTF-09 —
    passes via pytest.raises(NotImplementedError). Wave 1 (06-02)
    replaces this with real compose_email_body cases.
    '''
    with pytest.raises(NotImplementedError, match='Wave 1'):
      compose_email_body({}, {}, FROZEN_NOW)


class TestFormatters:
  '''D-02: notifier owns _fmt_currency_email, _fmt_percent_signed_email,
  _fmt_percent_unsigned_email, _fmt_pnl_with_colour_email, _fmt_em_dash_email,
  _fmt_last_updated_email, _fmt_instrument_display_email. Wave 1 (06-02) fills.
  '''

  def test_scaffold_placeholder_formatters(self) -> None:
    '''Nyquist Dimension 8: placeholder — Wave 1 fills per-formatter cases.

    Wave 1 (06-02) replaces this with real formatter assertions
    (currency signs, percent signs, P&L colour spans, em-dash, AWST
    last-updated, instrument display names).
    '''
    assert hasattr(notifier, '_EMAIL_FROM'), 'Wave 0 stub must expose _EMAIL_FROM'
    # Placeholder: Wave 1 fills real formatter assertions
    pytest.xfail('Wave 1 (06-02) fills TestFormatters cases')


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
