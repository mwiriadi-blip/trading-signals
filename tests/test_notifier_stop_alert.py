'''Phase 20 D-02/D-13 — notifier.send_stop_alert_email tests.

send_stop_alert_email(transitions, dashboard_url) -> bool

- Phase 6 never-crash: all failures return False, never raise.
- D-02: HTML + plain-text body (both bodies passed to _post_to_resend).
- D-13 XSS defense: every transitions field html.escape'd in HTML body.
- RESEARCH §Pitfall 3 / UAT-16-B: email body uses ONLY inline style="..."
  attributes; never class="alert-..." (CSS classes are dashboard-only).
- RESEARCH §Pitfall 2: HTML and plain-text bodies built from the same
  transitions list; every transition id + new_state appears in both.
- D-02 subject: N==1 → per-trade format; N>1 → batched format.
- D-01: empty transitions list → returns False, no network call.
'''
import math
from unittest.mock import MagicMock

import pytest

import notifier


# =========================================================================
# Fixtures
# =========================================================================

def _make_transition(
  trade_id: str = 'SPI200-20260430-001',
  instrument: str = 'SPI200',
  side: str = 'LONG',
  entry_price: float = 8200.0,
  stop_price: float = 8100.0,
  today_close: float = 8110.0,
  atr_distance: float = 0.31,
  new_state: str = 'APPROACHING',
  old_state: str | None = None,
) -> dict:
  return {
    'id': trade_id, 'instrument': instrument, 'side': side,
    'entry_price': entry_price, 'stop_price': stop_price,
    'today_close': today_close, 'atr_distance': atr_distance,
    'new_state': new_state, 'old_state': old_state,
  }


@pytest.fixture(autouse=True)
def _isolate_email_env(monkeypatch, tmp_path):
  '''Per-test env baseline: both required env vars set.
  Tests that exercise missing-env paths call monkeypatch.delenv themselves.
  '''
  monkeypatch.setenv('SIGNALS_EMAIL_FROM', 'signals@example.com')
  monkeypatch.setenv('RESEND_API_KEY', 'test-api-key')
  monkeypatch.setenv('SIGNALS_EMAIL_TO', 'operator@example.com')
  monkeypatch.chdir(tmp_path)


# =========================================================================
# TestSendStopAlertEmail
# =========================================================================

class TestSendStopAlertEmail:
  '''D-02/D-13: send_stop_alert_email contract.'''

  def test_n_zero_transitions_skips_send(self, monkeypatch) -> None:
    '''D-01: empty list returns False; _post_to_resend NEVER called.'''
    called = []
    monkeypatch.setattr(notifier, '_post_to_resend', lambda *a, **kw: called.append(1))
    result = notifier.send_stop_alert_email([], 'https://signals.example.com/')
    assert result is False
    assert called == [], '_post_to_resend must NOT be called with zero transitions'

  def test_n_one_transition_subject_format(self, monkeypatch) -> None:
    '''D-02 N==1 subject: [!stop] INSTRUMENT SIDE STATE -- id.'''
    captured: dict = {}
    monkeypatch.setattr(notifier, '_post_to_resend', lambda *a, **kw: captured.update(kw))
    t = _make_transition(trade_id='SPI200-20260430-001', instrument='SPI200',
                         side='LONG', new_state='APPROACHING')
    notifier.send_stop_alert_email([t], 'https://signals.example.com/')
    subject = captured.get('subject', '')
    assert '[!stop]' in subject, f'Subject must start with [!stop]; got {subject!r}'
    assert 'SPI200' in subject
    assert 'LONG' in subject
    assert 'APPROACHING' in subject
    assert 'SPI200-20260430-001' in subject

  def test_n_three_transitions_subject_format(self, monkeypatch) -> None:
    '''D-02 N>1 subject: [!stop] 3 transition(s) in today\'s paper trades.'''
    captured: dict = {}
    monkeypatch.setattr(notifier, '_post_to_resend', lambda *a, **kw: captured.update(kw))
    transitions = [
      _make_transition(trade_id=f'SPI200-2026043{i}-001') for i in range(3)
    ]
    notifier.send_stop_alert_email(transitions, 'https://signals.example.com/')
    subject = captured.get('subject', '')
    assert '[!stop]' in subject
    assert '3' in subject
    assert 'transition' in subject.lower()

  def test_post_to_resend_called_with_html_and_text(self, monkeypatch) -> None:
    '''D-02: _post_to_resend called with both html_body AND text_body non-empty.'''
    captured: dict = {}
    monkeypatch.setattr(notifier, '_post_to_resend', lambda *a, **kw: captured.update(kw))
    notifier.send_stop_alert_email(
      [_make_transition()], 'https://signals.example.com/',
    )
    html_body = captured.get('html_body', '')
    text_body = captured.get('text_body', '')
    assert html_body, 'html_body must be non-empty'
    assert text_body, 'text_body must be non-empty'
    # HTML contains table markup; text does not
    assert '<table' in html_body
    assert '<table' not in text_body

  def test_html_body_is_html_escaped(self, monkeypatch) -> None:
    '''D-13 XSS defense: HTML-special chars in transition id are escaped.
    Uses a synthetic id with <script> injection attempt.
    '''
    captured: dict = {}
    monkeypatch.setattr(notifier, '_post_to_resend', lambda *a, **kw: captured.update(kw))
    evil_id = '<script>alert(1)</script>'
    t = _make_transition(trade_id=evil_id)
    notifier.send_stop_alert_email([t], 'https://signals.example.com/')
    html_body = captured.get('html_body', '')
    assert '<script>' not in html_body, (
      'D-13: raw HTML tags must not appear in html_body'
    )
    assert '&lt;script&gt;' in html_body, (
      'D-13: escaped form must appear in html_body'
    )

  def test_html_body_uses_inline_styles_only(self, monkeypatch) -> None:
    '''RESEARCH §Pitfall 3 / UAT-16-B: email badges use inline style=".."
    attributes ONLY; never class="alert-..." (Gmail mobile strips <style>).
    '''
    captured: dict = {}
    monkeypatch.setattr(notifier, '_post_to_resend', lambda *a, **kw: captured.update(kw))
    notifier.send_stop_alert_email(
      [_make_transition(new_state='HIT')], 'https://signals.example.com/',
    )
    html_body = captured.get('html_body', '')
    # Must have inline style attributes (at least table + header + badge areas)
    assert html_body.count('style="') >= 3, (
      f'html_body must have >= 3 inline style= attributes; got {html_body.count("style=")}'
    )
    # Must NOT use CSS class-based alert badges (dashboard-only)
    assert 'class="alert-' not in html_body, (
      'RESEARCH §Pitfall 3: email body must NOT use class="alert-..." (dashboard-only)'
    )

  def test_html_text_parity_every_transition_id_in_both(self, monkeypatch) -> None:
    '''RESEARCH §Pitfall 2: every transition id AND new_state appear in BOTH bodies.'''
    captured: dict = {}
    monkeypatch.setattr(notifier, '_post_to_resend', lambda *a, **kw: captured.update(kw))
    transitions = [
      _make_transition(trade_id='SPI200-20260430-001', new_state='APPROACHING'),
      _make_transition(trade_id='AUDUSD-20260430-001', new_state='HIT'),
      _make_transition(trade_id='SPI200-20260430-002', new_state='CLEAR'),
    ]
    notifier.send_stop_alert_email(transitions, 'https://signals.example.com/')
    html_body = captured.get('html_body', '')
    text_body = captured.get('text_body', '')
    for t in transitions:
      assert t['id'] in html_body, f'{t["id"]!r} not found in html_body'
      assert t['id'] in text_body, f'{t["id"]!r} not found in text_body'
      assert t['new_state'] in html_body, f'{t["new_state"]!r} not found in html_body'
      assert t['new_state'] in text_body, f'{t["new_state"]!r} not found in text_body'

  def test_distance_format_within_trigger(self, monkeypatch) -> None:
    '''D-02: APPROACHING distance text is "0.31 ATR (within trigger)".'''
    captured: dict = {}
    monkeypatch.setattr(notifier, '_post_to_resend', lambda *a, **kw: captured.update(kw))
    t = _make_transition(atr_distance=0.31, new_state='APPROACHING')
    notifier.send_stop_alert_email([t], 'https://signals.example.com/')
    html_body = captured.get('html_body', '')
    text_body = captured.get('text_body', '')
    assert '0.31 ATR (within trigger)' in html_body, (
      f'D-02: APPROACHING distance format wrong in html_body; '
      f'snippet: {html_body[:500]!r}'
    )
    assert '0.31 ATR (within trigger)' in text_body

  def test_distance_format_beyond_stop(self, monkeypatch) -> None:
    '''D-02: HIT distance text is "1.50 ATR (beyond stop)".'''
    captured: dict = {}
    monkeypatch.setattr(notifier, '_post_to_resend', lambda *a, **kw: captured.update(kw))
    t = _make_transition(atr_distance=1.50, new_state='HIT')
    notifier.send_stop_alert_email([t], 'https://signals.example.com/')
    html_body = captured.get('html_body', '')
    text_body = captured.get('text_body', '')
    assert '1.50 ATR (beyond stop)' in html_body
    assert '1.50 ATR (beyond stop)' in text_body

  def test_distance_format_unknown_when_nan(self, monkeypatch) -> None:
    '''D-10 NaN-distance: float(\'nan\') atr_distance renders as "distance unknown".'''
    captured: dict = {}
    monkeypatch.setattr(notifier, '_post_to_resend', lambda *a, **kw: captured.update(kw))
    t = _make_transition(atr_distance=float('nan'), new_state='APPROACHING')
    notifier.send_stop_alert_email([t], 'https://signals.example.com/')
    html_body = captured.get('html_body', '')
    text_body = captured.get('text_body', '')
    assert 'distance unknown' in html_body, (
      f'NaN atr_distance must render as "distance unknown" in html_body'
    )
    assert 'distance unknown' in text_body

  def test_dashboard_url_appears_in_html_body(self, monkeypatch) -> None:
    '''D-02: dashboard link appears in html_body as an <a href="...">.'''
    captured: dict = {}
    monkeypatch.setattr(notifier, '_post_to_resend', lambda *a, **kw: captured.update(kw))
    url = 'https://signals.mwiriadi.me/'
    notifier.send_stop_alert_email([_make_transition()], url)
    html_body = captured.get('html_body', '')
    assert url in html_body, (
      f'dashboard_url must appear in html_body; url={url!r}'
    )
    assert f'href="{url}"' in html_body or f"href='{url}'" in html_body or url in html_body

  def test_resend_post_returns_200_returns_true(self, monkeypatch) -> None:
    '''Happy path: _post_to_resend succeeds (no raise) -> returns True.'''
    monkeypatch.setattr(notifier, '_post_to_resend', lambda *a, **kw: None)
    result = notifier.send_stop_alert_email(
      [_make_transition()], 'https://signals.example.com/',
    )
    assert result is True

  def test_resend_error_returns_false_no_raise(self, monkeypatch, caplog) -> None:
    '''ResendError -> returns False, never raises. caplog contains [Email] WARN.'''
    def _raise(*args, **kwargs):
      raise notifier.ResendError('boom')

    monkeypatch.setattr(notifier, '_post_to_resend', _raise)
    result = notifier.send_stop_alert_email(
      [_make_transition()], 'https://signals.example.com/',
    )
    assert result is False
    warn_msgs = [r.getMessage() for r in caplog.records if 'WARN' in r.getMessage()]
    assert warn_msgs, f'Expected [Email] WARN log; got {[r.getMessage() for r in caplog.records]!r}'

  def test_unexpected_exception_returns_false_no_raise(self, monkeypatch) -> None:
    '''Any exception from _post_to_resend caught -> returns False (never-crash invariant).'''
    def _raise(*args, **kwargs):
      raise RuntimeError('whatever')

    monkeypatch.setattr(notifier, '_post_to_resend', _raise)
    result = notifier.send_stop_alert_email(
      [_make_transition()], 'https://signals.example.com/',
    )
    assert result is False

  def test_missing_resend_api_key_returns_false(self, monkeypatch, caplog) -> None:
    '''No RESEND_API_KEY -> returns False with [Email] WARN log.'''
    monkeypatch.delenv('RESEND_API_KEY', raising=False)
    called = []
    monkeypatch.setattr(notifier, '_post_to_resend', lambda *a, **kw: called.append(1))
    result = notifier.send_stop_alert_email(
      [_make_transition()], 'https://signals.example.com/',
    )
    assert result is False
    assert called == []

  def test_missing_signals_email_from_returns_false(self, monkeypatch) -> None:
    '''No SIGNALS_EMAIL_FROM -> returns False.'''
    monkeypatch.delenv('SIGNALS_EMAIL_FROM', raising=False)
    called = []
    monkeypatch.setattr(notifier, '_post_to_resend', lambda *a, **kw: called.append(1))
    result = notifier.send_stop_alert_email(
      [_make_transition()], 'https://signals.example.com/',
    )
    assert result is False
    assert called == []

  def test_signals_email_to_used_as_recipient(self, monkeypatch) -> None:
    '''SIGNALS_EMAIL_TO value is used as to_addr (mirror send_daily_email pattern).'''
    captured: dict = {}

    def _fake_post(*args, **kwargs):
      captured.update(kwargs)
      captured['_args'] = args

    monkeypatch.setenv('SIGNALS_EMAIL_TO', 'custom@example.com')
    monkeypatch.setattr(notifier, '_post_to_resend', _fake_post)
    notifier.send_stop_alert_email([_make_transition()], 'https://signals.example.com/')
    to_addr = captured.get('to_addr') or (
      captured['_args'][2] if len(captured.get('_args', ())) >= 3 else None
    )
    assert to_addr == 'custom@example.com', (
      f'SIGNALS_EMAIL_TO must be used as recipient; got {to_addr!r}'
    )
