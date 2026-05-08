'''Phase 27 Plan 11 — crash-email second-line fallback regression suite.

When notifier.send_crash_email's outbound dispatch fails (Resend outage,
network down), the original crash payload must still reach the operator
on next dashboard visit via LAST_CRASH_PATH on disk.

Constraints (review-fix agreed-5):
  - Path is configurable via system_params.LAST_CRASH_FILE; default is
    'last_crash.json' at the same location as STATE_FILE — NOT a separate
    project-root path. Test fixtures monkeypatch a tmp_path location.
  - Traceback + exception_message are passed through redact_secret /
    pattern-walk redaction BEFORE disk write. Secrets MUST NEVER reach disk.
  - Dashboard banner content escapes via html.escape(quote=True) at every
    interpolation site (Plan 27-08 contract).
  - The fallback writer NEVER raises — preserves the daily-loop never-crash
    invariant (D-13 + Phase 8 SC-3).
'''
import json
import os
from pathlib import Path

import pytest

import notifier
import system_params


# =========================================================================
# Task 1: LAST_CRASH config + _write_last_crash helper
# =========================================================================


class TestLastCrashPathConfig:
  '''review-fix agreed-5: configurable + NOT-project-root default.'''

  def test_last_crash_file_constant_present(self):
    # str (matches STATE_FILE convention; system_params is stdlib-only —
    # cannot hold a Path object that would require os/pathlib import).
    assert hasattr(system_params, 'LAST_CRASH_FILE')
    assert isinstance(system_params.LAST_CRASH_FILE, str)
    assert system_params.LAST_CRASH_FILE == 'last_crash.json'

  def test_notifier_last_crash_path_resolves_relative_to_state(self):
    '''Resolved path defaults next to STATE_FILE (review-fix agreed-5 —
    "configurable, defaults to <state_dir>/last_crash.json — NOT project root").
    '''
    # _resolve_last_crash_path() returns a pathlib.Path the caller can use.
    p = notifier._resolve_last_crash_path()
    assert isinstance(p, Path)
    # Default sits in the same directory as STATE_FILE — NOT a separate
    # working-file location.
    assert p.name == 'last_crash.json'
    assert Path(system_params.STATE_FILE).parent.resolve() == p.parent.resolve()

  def test_last_crash_path_is_overridable_via_env(self, monkeypatch, tmp_path):
    '''Operator can override via LAST_CRASH_PATH env var (configurable).'''
    custom = tmp_path / 'custom_crash.json'
    monkeypatch.setenv('LAST_CRASH_PATH', str(custom))
    p = notifier._resolve_last_crash_path()
    assert p == custom


class TestWriteLastCrash:
  '''Helper contract: atomic, never-raise, redacts traceback BEFORE disk write.'''

  def _payload(self):
    return {
      'timestamp_utc': '2026-05-07T00:00:00+00:00',
      'run_date_aws': '2026-05-07',
      'exception_type': 'HTTPError',
      'exception_message': '401 Unauthorized',
      'traceback': 'Traceback ...\n  raise ResendError(...)',
      'send_email_failure': True,
    }

  def test_write_last_crash_creates_file(self, monkeypatch, tmp_path):
    crash = tmp_path / 'last_crash.json'
    monkeypatch.setenv('LAST_CRASH_PATH', str(crash))
    notifier._write_last_crash(self._payload())
    assert crash.exists()
    on_disk = json.loads(crash.read_text())
    assert on_disk['send_email_failure'] is True
    assert on_disk['exception_type'] == 'HTTPError'

  def test_write_last_crash_never_raises_on_oserror(
    self, monkeypatch, tmp_path,
  ):
    '''If the filesystem write itself fails, _write_last_crash must NEVER
    propagate — the never-crash invariant must hold even on disk-full /
    read-only-fs scenarios. Operator visibility to that case comes from the
    logger.error line, not an exception.
    '''
    crash = tmp_path / 'last_crash.json'
    monkeypatch.setenv('LAST_CRASH_PATH', str(crash))

    def boom(self, *args, **kwargs):
      raise OSError('disk full (test)')

    monkeypatch.setattr(Path, 'write_text', boom)
    # Must NOT raise.
    notifier._write_last_crash(self._payload())
    # No file should exist after the failed write.
    assert not crash.exists()

  def test_write_last_crash_redacts_traceback(self, monkeypatch, tmp_path):
    '''review-fix agreed-5: secrets in tracebacks NEVER reach disk.'''
    crash = tmp_path / 'last_crash.json'
    monkeypatch.setenv('LAST_CRASH_PATH', str(crash))
    payload = self._payload()
    # Phase 27 WR-06: replace stale 'notifier.py:1423' reference with a
    # placeholder (the monolith was deleted in CR-01 and the line numbers
    # in notifier/transport.py do not match the original anyway).
    payload['traceback'] = (
      'Traceback (most recent call last):\n'
      '  File "<test-fixture>", line 1\n'
      '    resend.send(api_key="re_test_abc123def456ghi789")\n'
      '  ResendError: ...'
    )
    notifier._write_last_crash(payload)
    on_disk = json.loads(crash.read_text())
    # The full secret token must NOT appear in the on-disk traceback.
    assert 're_test_abc123def456ghi789' not in on_disk['traceback']
    # And the redacted prefix should appear instead.
    assert 're_tes' in on_disk['traceback'] or 'REDACTED' in on_disk['traceback']

  def test_write_last_crash_redacts_exception_message(
    self, monkeypatch, tmp_path,
  ):
    '''review-fix agreed-5: Bearer token in exception_message redacted.'''
    crash = tmp_path / 'last_crash.json'
    monkeypatch.setenv('LAST_CRASH_PATH', str(crash))
    payload = self._payload()
    payload['exception_message'] = (
      '401 Unauthorized — sent header Bearer eyJabc123def456ghi789jkl'
    )
    notifier._write_last_crash(payload)
    on_disk = json.loads(crash.read_text())
    assert 'eyJabc123def456ghi789jkl' not in on_disk['exception_message']

  def test_write_last_crash_atomic(self, monkeypatch, tmp_path):
    '''Atomic write: tempfile + os.replace — partial writes never visible.

    Soft-asserts the contract: after a successful call, the final file
    exists AND no .tmp leftover.
    '''
    crash = tmp_path / 'last_crash.json'
    monkeypatch.setenv('LAST_CRASH_PATH', str(crash))
    notifier._write_last_crash(self._payload())
    assert crash.exists()
    # No leftover tempfile in the same directory.
    leftovers = [p for p in tmp_path.iterdir() if p.name.endswith('.tmp')]
    assert leftovers == [], f'tempfile leaked: {leftovers}'


# =========================================================================
# Task 1 wire-in: send_crash_email failure path
# =========================================================================


class TestSendCrashEmailFailureWritesLastCrash:
  '''When the crash-email dispatch itself fails (Resend down / network),
  the crash payload still reaches LAST_CRASH_PATH so operator sees it next
  visit (review item #15 — silent crash dropout prevention).
  '''

  def test_send_crash_email_failure_writes_last_crash(
    self, monkeypatch, tmp_path,
  ):
    '''Outbound POST raises ConnectionError → fallback writes last_crash.json.'''
    crash_path = tmp_path / 'last_crash.json'
    monkeypatch.setenv('LAST_CRASH_PATH', str(crash_path))
    monkeypatch.setenv('RESEND_API_KEY', 're_test_abc123def456ghi789')
    monkeypatch.setenv('SIGNALS_EMAIL_FROM', 'signals@example.com')
    monkeypatch.setenv('SIGNALS_EMAIL_TO', 'op@example.com')

    import requests as _requests

    def boom(*args, **kwargs):
      raise _requests.exceptions.ConnectionError('network down (test)')

    monkeypatch.setattr(_requests, 'post', boom)

    try:
      raise RuntimeError('original crash for the test')
    except RuntimeError as e:
      result = notifier.send_crash_email(e, 'test state summary')

    # The dispatch should have returned ok=False (NEVER raises).
    assert result.ok is False
    # The fallback file should now exist.
    assert crash_path.exists(), 'last_crash.json should be written on dispatch failure'
    on_disk = json.loads(crash_path.read_text())
    assert on_disk['send_email_failure'] is True
    assert on_disk['exception_type'] == 'RuntimeError'
    # Secret never reaches disk even though it appeared in the dispatch
    # call kwargs.
    assert 're_test_abc123def456ghi789' not in json.dumps(on_disk)

  def test_send_crash_email_failure_never_propagates(
    self, monkeypatch, tmp_path,
  ):
    '''Even when BOTH the dispatch AND the fallback write fail, the daily
    loop never sees an exception. Defense in depth for never-crash invariant.
    '''
    crash_path = tmp_path / 'last_crash.json'
    monkeypatch.setenv('LAST_CRASH_PATH', str(crash_path))
    monkeypatch.setenv('RESEND_API_KEY', 're_test_abc123def456ghi789')
    monkeypatch.setenv('SIGNALS_EMAIL_FROM', 'signals@example.com')
    monkeypatch.setenv('SIGNALS_EMAIL_TO', 'op@example.com')

    import requests as _requests

    def boom_post(*args, **kwargs):
      raise _requests.exceptions.ConnectionError('network down (test)')

    def boom_write(self, *args, **kwargs):
      raise OSError('disk full (test)')

    monkeypatch.setattr(_requests, 'post', boom_post)
    monkeypatch.setattr(Path, 'write_text', boom_write)

    try:
      raise RuntimeError('original crash for the test')
    except RuntimeError as e:
      # Must NOT raise — dispatch failed AND disk write failed.
      result = notifier.send_crash_email(e, 'test state summary')

    assert result.ok is False


# =========================================================================
# Task 2: Dashboard banner integration (configurable + _e escape)
# =========================================================================


class TestDashboardLastCrashBanner:
  '''review-fix agreed-5: banner reads from configurable LAST_CRASH_PATH +
  every interpolation goes through html.escape(quote=True).
  '''

  def _write_crash_file(self, path, **overrides):
    payload = {
      'timestamp_utc': '2026-05-07T14:30:00+00:00',
      'run_date_aws': '2026-05-07',
      'exception_type': 'requests.exceptions.ConnectionError',
      'exception_message': 'Resend network unreachable',
      'traceback': 'Traceback ...\n  ConnectionError: ...',
      'send_email_failure': True,
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload))

  def test_renders_banner_when_last_crash_exists(self, monkeypatch, tmp_path):
    crash_path = tmp_path / 'last_crash.json'
    monkeypatch.setenv('LAST_CRASH_PATH', str(crash_path))
    self._write_crash_file(crash_path)

    from dashboard_renderer.components.header import render_last_crash_banner

    html_out = render_last_crash_banner()
    assert 'last-crash-banner' in html_out
    assert 'Resend network unreachable' in html_out
    assert '2026-05-07T14:30:00+00:00' in html_out
    assert 'requests.exceptions.ConnectionError' in html_out

  def test_no_banner_when_last_crash_absent(self, monkeypatch, tmp_path):
    crash_path = tmp_path / 'last_crash.json'
    monkeypatch.setenv('LAST_CRASH_PATH', str(crash_path))
    # File does NOT exist.
    from dashboard_renderer.components.header import render_last_crash_banner

    html_out = render_last_crash_banner()
    assert html_out == ''
    assert 'last-crash-banner' not in html_out

  def test_uses_configurable_path(self, monkeypatch, tmp_path):
    '''Renderer reads from LAST_CRASH_PATH env var, not a hardcoded path.

    Proof: write to a non-default location, point env var there, banner shows.
    '''
    custom = tmp_path / 'subdir' / 'special.json'
    custom.parent.mkdir()
    monkeypatch.setenv('LAST_CRASH_PATH', str(custom))
    self._write_crash_file(custom, exception_message='UniqueMessage42')

    from dashboard_renderer.components.header import render_last_crash_banner

    html_out = render_last_crash_banner()
    assert 'UniqueMessage42' in html_out

  def test_banner_xss_safe(self, monkeypatch, tmp_path):
    '''Plan 27-08 contract: html.escape(quote=True) on every interpolation.'''
    crash_path = tmp_path / 'last_crash.json'
    monkeypatch.setenv('LAST_CRASH_PATH', str(crash_path))
    self._write_crash_file(
      crash_path,
      exception_message='<script>alert(1)</script>',
      exception_type='Foo<bar>"&\'baz',
    )

    from dashboard_renderer.components.header import render_last_crash_banner

    html_out = render_last_crash_banner()
    # Raw script tag MUST NOT appear — every dynamic value passes through
    # html.escape(quote=True).
    assert '<script>alert(1)</script>' not in html_out
    assert '&lt;script&gt;' in html_out
    # Quote and ampersand also escaped (quote=True → " becomes &quot;).
    assert 'Foo<bar>"&\'baz' not in html_out
    assert '&lt;bar&gt;' in html_out
    assert '&quot;' in html_out
