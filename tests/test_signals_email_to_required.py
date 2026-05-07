'''Phase 27 #9 — SIGNALS_EMAIL_TO is required (no hardcoded fallback).

Behavior tests for review-fix M3 (option b — log + return + state-health
warning marker; fail-soft, never crash):
  test_signals_email_to_required_send_daily — missing env var → log ERROR,
    return SendStatus(ok=False), do NOT call _post_to_resend, do NOT crash.
  test_signals_email_to_required_send_crash — same for send_crash_email
    (M3 — both paths must behave consistently).
  test_signals_email_to_required_send_stop_alert — same for the stop-alert
    dispatch path (M3 — third call site uses _EMAIL_TO_FALLBACK too).
  test_signals_email_to_present — env set → both paths proceed normally.
  test_state_health_warning_appended — missing env var with state dict →
    state['warnings'] gains a marker entry visible on dashboard health strip.
  test_no_hardcoded_email_in_notifier — grep gate: zero `_EMAIL_TO_FALLBACK`
    refs and zero literal email-shaped strings in notifier.py source.
'''
import json
import logging
import re
from datetime import datetime
from pathlib import Path

import pytest
import pytz


SAMPLE_STATE_PATH = Path(__file__).parent / 'fixtures' / 'notifier' / 'sample_state_no_change.json'
FROZEN_NOW = datetime(2026, 5, 8, 0, 0, 0, tzinfo=pytz.UTC)


@pytest.fixture(autouse=True)
def _pin_signals_email_from(monkeypatch):
  '''Match the convention from tests/test_notifier.py: pin SIGNALS_EMAIL_FROM
  so dispatch helpers don't short-circuit with missing_sender. Tests in this
  file mutate SIGNALS_EMAIL_TO specifically.
  '''
  monkeypatch.setenv('SIGNALS_EMAIL_FROM', 'signals@carbonbookkeeping.com.au')


# =========================================================================
# send_daily_email — SIGNALS_EMAIL_TO required
# =========================================================================

class TestSendDailyEmailRequiresSignalsEmailTo:
  '''review-fix M3: SIGNALS_EMAIL_TO unset → log ERROR + skip (never crash).'''

  def test_signals_email_to_required_send_daily(
      self, tmp_path, monkeypatch, caplog,
  ) -> None:
    '''Missing SIGNALS_EMAIL_TO → ERROR log + SendStatus(ok=False), no
    network call.'''
    from notifier import send_daily_email
    caplog.set_level(logging.ERROR)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('RESEND_API_KEY', 'k')
    monkeypatch.delenv('SIGNALS_EMAIL_TO', raising=False)

    posted: list = []

    def _fake_post(*a, **kw):
      posted.append((a, kw))
      raise AssertionError('must not call _post_to_resend when env var missing')

    monkeypatch.setattr('notifier.requests.post', _fake_post)
    state = json.loads(SAMPLE_STATE_PATH.read_text())
    result = send_daily_email(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    assert result.ok is False
    assert posted == [], 'no network dispatch when SIGNALS_EMAIL_TO missing'
    assert 'SIGNALS_EMAIL_TO' in caplog.text
    assert 'required' in caplog.text.lower() or 'missing' in caplog.text.lower()

  def test_signals_email_to_empty_string_treated_as_missing(
      self, tmp_path, monkeypatch, caplog,
  ) -> None:
    '''Empty string env var (set but blank) is also rejected — common
    deploy-typo failure mode.'''
    from notifier import send_daily_email
    caplog.set_level(logging.ERROR)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('RESEND_API_KEY', 'k')
    monkeypatch.setenv('SIGNALS_EMAIL_TO', '   ')  # whitespace only

    monkeypatch.setattr(
      'notifier.requests.post',
      lambda *a, **kw: (_ for _ in ()).throw(
        AssertionError('must not dispatch on blank env'),
      ),
    )
    state = json.loads(SAMPLE_STATE_PATH.read_text())
    result = send_daily_email(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    assert result.ok is False
    assert 'SIGNALS_EMAIL_TO' in caplog.text


# =========================================================================
# send_crash_email — SIGNALS_EMAIL_TO required (review-fix M3 — same behavior)
# =========================================================================

class TestSendCrashEmailRequiresSignalsEmailTo:

  def test_signals_email_to_required_send_crash(
      self, tmp_path, monkeypatch, caplog,
  ) -> None:
    '''Missing SIGNALS_EMAIL_TO on crash path → ERROR log + SendStatus
    (ok=False), no network call. Crash-on-crash must be avoided.'''
    from notifier import send_crash_email
    caplog.set_level(logging.ERROR)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('RESEND_API_KEY', 'k')
    monkeypatch.delenv('SIGNALS_EMAIL_TO', raising=False)

    posted: list = []

    def _fake_post(*a, **kw):
      posted.append((a, kw))
      raise AssertionError('must not call _post_to_resend on crash path')

    monkeypatch.setattr('notifier.requests.post', _fake_post)
    try:
      raise RuntimeError('synthetic crash for crash-email test')
    except RuntimeError as exc:
      result = send_crash_email(exc, 'state-summary stub', FROZEN_NOW)
    assert result.ok is False
    assert posted == []
    assert 'SIGNALS_EMAIL_TO' in caplog.text


# =========================================================================
# send_stop_alert_email — third call site (line 1939)
# =========================================================================

class TestSendStopAlertEmailRequiresSignalsEmailTo:

  def test_signals_email_to_required_send_stop_alert(
      self, tmp_path, monkeypatch, caplog,
  ) -> None:
    '''Missing SIGNALS_EMAIL_TO → ERROR log + return False, no network.'''
    from notifier import send_stop_alert_email
    caplog.set_level(logging.ERROR)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('RESEND_API_KEY', 'k')
    monkeypatch.delenv('SIGNALS_EMAIL_TO', raising=False)

    posted: list = []

    def _fake_post(*a, **kw):
      posted.append((a, kw))
      raise AssertionError('must not dispatch when SIGNALS_EMAIL_TO missing')

    monkeypatch.setattr('notifier.requests.post', _fake_post)
    transitions = [{
      'state_key': 'SPI200', 'direction': 'LONG', 'level': 'approach',
      'distance_atr': 0.5, 'stop_price': 7800.0, 'last_close': 7820.0,
      'as_of': '2026-05-08',
    }]
    ok = send_stop_alert_email(transitions, 'https://example.com/dashboard')
    assert ok is False
    assert posted == []
    assert 'SIGNALS_EMAIL_TO' in caplog.text


# =========================================================================
# Happy path — both dispatch functions proceed when env present
# =========================================================================

class TestSignalsEmailToPresent:

  def test_send_daily_email_dispatches_when_env_present(
      self, tmp_path, monkeypatch,
  ) -> None:
    from notifier import send_daily_email
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('RESEND_API_KEY', 'k')
    monkeypatch.setenv('SIGNALS_EMAIL_TO', 'ops@example.com')

    captured: list[dict] = []

    class _FakeResp:
      def __init__(self, status_code: int = 200, body: str = '{}'):
        self.status_code = status_code
        self.text = body

      def json(self):
        return {'id': 'fake'}

    def _fake_post(url, **kw):
      captured.append({'url': url, **kw})
      return _FakeResp(200)

    monkeypatch.setattr('notifier.requests.post', _fake_post)
    state = json.loads(SAMPLE_STATE_PATH.read_text())
    result = send_daily_email(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    assert result.ok is True
    assert captured[0]['json']['to'] == ['ops@example.com']

  def test_send_crash_email_dispatches_when_env_present(
      self, tmp_path, monkeypatch,
  ) -> None:
    from notifier import send_crash_email
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('RESEND_API_KEY', 'k')
    monkeypatch.setenv('SIGNALS_EMAIL_TO', 'ops@example.com')

    captured: list[dict] = []

    class _FakeResp:
      def __init__(self, status_code: int = 200, body: str = '{}'):
        self.status_code = status_code
        self.text = body

      def json(self):
        return {'id': 'fake'}

    def _fake_post(url, **kw):
      captured.append({'url': url, **kw})
      return _FakeResp(200)

    monkeypatch.setattr('notifier.requests.post', _fake_post)
    try:
      raise RuntimeError('synthetic crash')
    except RuntimeError as exc:
      result = send_crash_email(exc, 'state-summary stub', FROZEN_NOW)
    assert result.ok is True
    assert captured[0]['json']['to'] == ['ops@example.com']


# =========================================================================
# State-health warning marker (review-fix M3)
# =========================================================================

class TestStateHealthWarningMarker:
  '''When SIGNALS_EMAIL_TO is missing AND the dispatch helper has access
  to the state dict, it must append a marker to state['warnings'] so the
  dashboard health strip surfaces the misconfiguration.

  send_daily_email already takes state as an argument — the marker is
  appended inline; never-crash invariant preserved via try/except around
  the state_manager.append_warning call.
  '''

  def test_state_health_warning_appended_send_daily(
      self, tmp_path, monkeypatch,
  ) -> None:
    '''Missing env var + state → state['warnings'] gains a 'SIGNALS_EMAIL_TO'
    marker entry.'''
    from notifier import send_daily_email
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('RESEND_API_KEY', 'k')
    monkeypatch.delenv('SIGNALS_EMAIL_TO', raising=False)
    monkeypatch.setattr(
      'notifier.requests.post',
      lambda *a, **kw: (_ for _ in ()).throw(
        AssertionError('must not dispatch'),
      ),
    )
    state = json.loads(SAMPLE_STATE_PATH.read_text())
    initial_warnings = list(state.get('warnings', []))
    send_daily_email(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    new_warnings = state.get('warnings', [])
    assert len(new_warnings) > len(initial_warnings), (
      'expected a new state-health warning entry on missing SIGNALS_EMAIL_TO'
    )
    new_entry = new_warnings[-1]
    # state_manager.append_warning shape: {date, source, message}
    assert 'SIGNALS_EMAIL_TO' in new_entry.get('message', ''), (
      f'warning marker must mention SIGNALS_EMAIL_TO; got: {new_entry!r}'
    )


# =========================================================================
# Hardcoded email grep gate
# =========================================================================

class TestNoHardcodedEmailInNotifier:

  def test_no_email_to_fallback_constant_in_notifier(self) -> None:
    '''Constant `_EMAIL_TO_FALLBACK` must be deleted from notifier.py.'''
    src = Path('notifier.py').read_text(encoding='utf-8')
    assert '_EMAIL_TO_FALLBACK' not in src, (
      "notifier.py must not reference _EMAIL_TO_FALLBACK (Phase 27 #9)"
    )

  def test_no_literal_operator_email_in_notifier(self) -> None:
    '''Operator's personal email address must not appear anywhere in
    notifier.py source — secret-as-config hygiene.'''
    src = Path('notifier.py').read_text(encoding='utf-8')
    assert 'mwiriadi@gmail.com' not in src
    assert 'mwiriadi@' not in src
    # Generic literal-email regex (excluding @example.com test fixtures
    # which would never appear in production source anyway). notifier.py
    # may legitimately reference @example.com in docstrings, so we only
    # forbid real-looking domains.
    leaked = re.findall(
      r'[a-zA-Z0-9._%+-]+@(?!example\.|x\.com|domain\.com)[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
      src,
    )
    # Allow @carbonbookkeeping.com.au (verified Resend sender, lives as
    # an example only inside docstrings/comments — never as a hardcoded
    # default; presence is documentation, not config). Filter it out.
    leaked = [m for m in leaked if 'carbonbookkeeping' not in m]
    assert leaked == [], (
      f"notifier.py contains hardcoded operator-shaped email addresses: {leaked}"
    )
