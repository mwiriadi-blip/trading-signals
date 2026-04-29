'''Phase 16.1 Plan 03 Task 2 — notifier.send_magic_link_email tests.

F-03: send a 2FA reset magic-link email via Resend.
- Reuses Phase 12 _post_to_resend transport.
- SIGNALS_EMAIL_FROM env var (per-send) — fail-loud missing.
- RESEND_API_KEY env var (per-send) — fall back to last_email.html if missing.
- Subject (verbatim): "Trading Signals — 2FA reset link (valid 1 hour)"
- HTML body has button-link + plain-text fallback + AWST-formatted expires.
- Failures: log [Email] error + return SendStatus(ok=False, reason=...).
  Helper NEVER raises (CLAUDE.md "Email sends NEVER crash the workflow").
- Log line on success: "[Email] magic link sent to=%s action=%s expires=%s"

Tests mirror tests/test_notifier.py patterns: monkeypatch env vars, patch
notifier._post_to_resend to capture call args, no real network.
'''
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests

import notifier


# Fixed expires_at for assertions: 2026-04-29T09:00:00+00:00 = 17:00 AWST.
FIXED_EXPIRES_AT_UTC = '2026-04-29T09:00:00+00:00'
FIXED_LINK = 'https://signals.example.com/reset-totp?token=abc123'


@pytest.fixture(autouse=True)
def _isolate_email_env(monkeypatch, tmp_path):
  '''Per-test env baseline: SIGNALS_EMAIL_FROM set, RESEND_API_KEY set.

  Tests that exercise missing-env paths call monkeypatch.delenv themselves;
  LIFO finalizer ordering means their override beats this autouse setenv.
  Also chdir to tmp_path so last_email.html fallback writes there.
  '''
  monkeypatch.setenv('SIGNALS_EMAIL_FROM', 'signals@example.com')
  monkeypatch.setenv('RESEND_API_KEY', 'test-api-key')
  monkeypatch.chdir(tmp_path)


class TestSendMagicLinkEmail:
  '''F-03 contract: send_magic_link_email(to, link, action, expires_at).'''

  def test_resend_post_body_shape_to_subject_html_text_present(
    self, monkeypatch,
  ):
    '''Captured kwargs include to=[recipient], verbatim subject, html with link, text with link.'''
    captured: dict = {}

    def _fake_post(*args, **kwargs):
      captured.update(kwargs)
      # Also capture positionals for compatibility with how the helper calls it.
      captured['_args'] = args

    monkeypatch.setattr(notifier, '_post_to_resend', _fake_post)
    status = notifier.send_magic_link_email(
      to_email='mwiriadi@gmail.com',
      link=FIXED_LINK,
      action='totp-reset',
      expires_at=FIXED_EXPIRES_AT_UTC,
    )
    assert status.ok is True
    # Resend POST shape: subject literal + body shape.
    assert captured.get('subject') == 'Trading Signals — 2FA reset link (valid 1 hour)'
    # to_addr can be passed positionally or as kwarg — accept either.
    to_addr = captured.get('to_addr') or (captured['_args'][2] if len(captured.get('_args', ())) >= 3 else None)
    assert to_addr == 'mwiriadi@gmail.com'
    html_body = captured.get('html_body') or ''
    text_body = captured.get('text_body') or ''
    assert FIXED_LINK in html_body
    assert FIXED_LINK in text_body

  def test_html_body_contains_link_as_button(self, monkeypatch):
    '''HTML has <a href="<link>" with inline-CSS button styling.'''
    captured: dict = {}
    monkeypatch.setattr(
      notifier, '_post_to_resend',
      lambda *a, **kw: captured.update(kw),
    )
    notifier.send_magic_link_email(
      to_email='mwiriadi@gmail.com', link=FIXED_LINK,
      action='totp-reset', expires_at=FIXED_EXPIRES_AT_UTC,
    )
    html_body = captured.get('html_body', '')
    assert f'href="{FIXED_LINK}"' in html_body or f'href={FIXED_LINK}' in html_body
    # Inline CSS button (mirror notifier.py palette aesthetic).
    assert 'style=' in html_body
    assert 'border' in html_body or 'background' in html_body

  def test_html_body_link_is_html_escaped(self, monkeypatch):
    '''Link with ?token=foo&bar=baz → HTML body has &amp; not raw &.'''
    captured: dict = {}
    monkeypatch.setattr(
      notifier, '_post_to_resend',
      lambda *a, **kw: captured.update(kw),
    )
    link_with_amp = 'https://signals.example.com/reset-totp?token=foo&bar=baz'
    notifier.send_magic_link_email(
      to_email='mwiriadi@gmail.com', link=link_with_amp,
      action='totp-reset', expires_at=FIXED_EXPIRES_AT_UTC,
    )
    html_body = captured.get('html_body', '')
    # The href must contain the escaped &amp;, not raw &.
    assert '&amp;' in html_body
    # Must not contain unescaped & in the href context (allow & in entity refs only).
    # A simple check: the literal '?token=foo&bar=baz' raw string MUST NOT appear in html_body.
    assert '?token=foo&bar=baz' not in html_body

  def test_plain_text_fallback_present(self, monkeypatch):
    '''text_body is non-empty and contains the link verbatim.'''
    captured: dict = {}
    monkeypatch.setattr(
      notifier, '_post_to_resend',
      lambda *a, **kw: captured.update(kw),
    )
    notifier.send_magic_link_email(
      to_email='mwiriadi@gmail.com', link=FIXED_LINK,
      action='totp-reset', expires_at=FIXED_EXPIRES_AT_UTC,
    )
    text_body = captured.get('text_body', '')
    assert text_body
    assert FIXED_LINK in text_body
    # Should mention reset / 2FA so operator's plain-text-only client shows context.
    assert '2FA' in text_body or 'reset' in text_body.lower()

  def test_subject_format_exact(self, monkeypatch):
    '''Subject literal matches F-03 verbatim (em-dash, parenthetical).'''
    captured: dict = {}
    monkeypatch.setattr(
      notifier, '_post_to_resend',
      lambda *a, **kw: captured.update(kw),
    )
    notifier.send_magic_link_email(
      to_email='mwiriadi@gmail.com', link=FIXED_LINK,
      action='totp-reset', expires_at=FIXED_EXPIRES_AT_UTC,
    )
    assert captured.get('subject') == 'Trading Signals — 2FA reset link (valid 1 hour)'

  def test_log_line_format(self, monkeypatch, caplog):
    '''On success: log line "[Email] magic link sent to=... action=... expires=..."'''
    monkeypatch.setattr(notifier, '_post_to_resend', lambda *a, **kw: None)
    with caplog.at_level('INFO', logger='notifier'):
      notifier.send_magic_link_email(
        to_email='mwiriadi@gmail.com', link=FIXED_LINK,
        action='totp-reset', expires_at=FIXED_EXPIRES_AT_UTC,
      )
    # Find the magic-link log line.
    matching = [r for r in caplog.records if '[Email] magic link sent' in r.getMessage()]
    assert matching, f'No [Email] magic link sent log found; records={[r.getMessage() for r in caplog.records]}'
    msg = matching[0].getMessage()
    assert 'to=mwiriadi@gmail.com' in msg
    assert 'action=totp-reset' in msg
    assert 'expires=' in msg

  def test_resend_failure_returns_send_status_ok_false_no_raise(
    self, monkeypatch,
  ):
    '''Resend transport raises → helper logs + returns ok=False, never raises.'''
    def _raise(*args, **kwargs):
      raise notifier.ResendError('synthetic resend failure')

    monkeypatch.setattr(notifier, '_post_to_resend', _raise)
    # Must not raise.
    status = notifier.send_magic_link_email(
      to_email='mwiriadi@gmail.com', link=FIXED_LINK,
      action='totp-reset', expires_at=FIXED_EXPIRES_AT_UTC,
    )
    assert status.ok is False
    assert status.reason is not None
    assert 'synthetic resend failure' in status.reason or 'resend' in status.reason.lower()

  def test_unexpected_exception_is_caught(self, monkeypatch):
    '''Any exception from _post_to_resend must be caught (never-crash).'''
    def _raise(*args, **kwargs):
      raise requests.exceptions.ConnectionError('synthetic network blip')

    monkeypatch.setattr(notifier, '_post_to_resend', _raise)
    status = notifier.send_magic_link_email(
      to_email='mwiriadi@gmail.com', link=FIXED_LINK,
      action='totp-reset', expires_at=FIXED_EXPIRES_AT_UTC,
    )
    assert status.ok is False
    assert status.reason is not None

  def test_missing_resend_api_key_falls_back_to_last_email_html(
    self, monkeypatch, tmp_path,
  ):
    '''No RESEND_API_KEY → write last_email.html (fallback) + return ok=False reason=no_api_key.'''
    monkeypatch.delenv('RESEND_API_KEY', raising=False)
    # Patch _post_to_resend so we'd notice if it was called erroneously.
    called = []
    monkeypatch.setattr(notifier, '_post_to_resend', lambda *a, **kw: called.append(1))
    status = notifier.send_magic_link_email(
      to_email='mwiriadi@gmail.com', link=FIXED_LINK,
      action='totp-reset', expires_at=FIXED_EXPIRES_AT_UTC,
    )
    assert status.ok is False
    assert called == [], 'Resend POST must NOT be called when RESEND_API_KEY is missing'
    # last_email.html fallback (notifier.py convention).
    assert (tmp_path / 'last_email.html').exists()

  def test_missing_signals_email_from_returns_send_status_ok_false(
    self, monkeypatch,
  ):
    '''No SIGNALS_EMAIL_FROM → fail-loud (matches Phase 12 D-15 pattern).'''
    monkeypatch.delenv('SIGNALS_EMAIL_FROM', raising=False)
    called = []
    monkeypatch.setattr(notifier, '_post_to_resend', lambda *a, **kw: called.append(1))
    status = notifier.send_magic_link_email(
      to_email='mwiriadi@gmail.com', link=FIXED_LINK,
      action='totp-reset', expires_at=FIXED_EXPIRES_AT_UTC,
    )
    assert status.ok is False
    assert status.reason == 'missing_sender'
    assert called == [], 'Resend POST must NOT be called without SIGNALS_EMAIL_FROM'
