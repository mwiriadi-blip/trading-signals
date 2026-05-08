'''Phase 27 #13 — secret redaction regression suite.

Locks in three invariants:
  1. system_params.redact_secret is the single canonical redactor and
     follows the 6-char-prefix policy ('xxxxxx...' for long; '[short]'
     for ≤6 chars; '[empty]' for None/empty).
  2. notifier._post_to_resend's 4xx error body — and its retries-
     exhausted fallback — emits redact_secret(api_key) so the operator
     can correlate which key without exposing the full token. The
     defense-in-depth body.replace('[REDACTED]') stays.
  3. auth_store.set_totp_secret never writes the raw base32 secret to
     any log line.

T-27-03-01 (RESEND_API_KEY in journalctl) + T-27-03-02 (TOTP secret
in auth_store logs) — both mitigated by redact_secret.

Hex-boundary: tests live under tests/ — they may import production
modules (notifier, auth_store, system_params) but must NOT mutate
on-disk state. Each test is self-contained via monkeypatch + caplog
+ tmp_path.
'''
import logging
import re

import pytest
import requests

import auth_store
import notifier
from system_params import redact_secret


# =========================================================================
# redact_secret — unit tests (3 cases)
# =========================================================================


class TestRedactSecret:
  '''The 6-char-prefix-policy contract.'''

  def test_redact_secret_long(self) -> None:
    '''Long inputs return prefix[:6] + '...' verbatim.'''
    assert redact_secret('re_abc123def456ghi789') == 're_abc...'

  def test_redact_secret_short(self) -> None:
    '''Inputs ≤6 chars are too short to safely show 6 chars; return marker.'''
    assert redact_secret('abc123') == '[short]'
    assert redact_secret('a') == '[short]'

  def test_redact_secret_empty(self) -> None:
    '''Empty string and None both collapse to '[empty]'.'''
    assert redact_secret('') == '[empty]'
    assert redact_secret(None) == '[empty]'


# =========================================================================
# notifier — Resend error path uses redact_secret on api_key prefix
# =========================================================================


class _FakeResp:
  '''Minimal stand-in for requests.Response (mirror of test_notifier._FakeResp).'''

  def __init__(self, status_code: int, text: str = 'ok') -> None:
    self.status_code = status_code
    self.text = text

  def raise_for_status(self) -> None:
    if self.status_code == 429 or self.status_code >= 500:
      raise requests.exceptions.HTTPError(
        f'{self.status_code}', response=self,
      )


class TestNotifierResendErrorRedacts:
  '''4xx + retries-exhausted error paths surface the api_key prefix via
  redact_secret() so operator triage works WITHOUT logging the full token.
  '''

  def test_notifier_resend_error_redacts(self, monkeypatch) -> None:
    '''4xx fail-fast: ResendError message contains redact_secret(api_key)
    prefix, NOT the raw api_key. Defense-in-depth body.replace stays.
    '''
    api_key = 're_abc123def456ghi789'

    def _fake_post(*a, **kw):
      # Resend echoing the Authorization header back in the error body
      # is the threat T-27-03-01 calls out — body must not leak it.
      return _FakeResp(401, f'Invalid API key: Bearer {api_key}')

    monkeypatch.setattr('notifier.requests.post', _fake_post)
    with pytest.raises(notifier.ResendError) as exc_info:
      notifier._post_to_resend(
        api_key, 'from@x.com', 'to@x.com', 'subj', '<html/>',
        timeout_s=1, retries=1, backoff_s=0,
      )
    msg = str(exc_info.value)
    # The redacted prefix MUST appear (operator triage signal).
    assert 're_abc...' in msg, f'expected redacted prefix; got: {msg!r}'
    # The raw key MUST NOT leak.
    assert api_key not in msg, f'leak: full api_key in error: {msg!r}'

  def test_notifier_retries_exhausted_redacts(self, monkeypatch) -> None:
    '''Retries-exhausted branch (5xx / network): final ResendError
    message contains redact_secret(api_key) prefix, NOT the raw key.
    '''
    api_key = 're_abc123def456ghi789'

    def _fake_post(*a, **kw):
      # ConnectionError whose message embeds the literal api_key —
      # mirrors the existing test_api_key_redacted_in_retries_exhausted
      # case but asserts the prefix is also surfaced.
      raise requests.exceptions.ConnectionError(
        f'connection lost: Bearer {api_key}',
      )

    monkeypatch.setattr('notifier.requests.post', _fake_post)
    with pytest.raises(notifier.ResendError) as exc_info:
      notifier._post_to_resend(
        api_key, 'from@x.com', 'to@x.com', 'subj', '<html/>',
        timeout_s=1, retries=2, backoff_s=0,
      )
    msg = str(exc_info.value)
    assert 're_abc...' in msg, f'expected redacted prefix; got: {msg!r}'
    assert api_key not in msg, f'leak: full api_key in retries-exhausted: {msg!r}'


# =========================================================================
# auth_store — TOTP secret persistence never logs the raw secret
# =========================================================================


class TestAuthStoreTotpLogRedacts:
  '''set_totp_secret writes the secret to auth.json via the atomic-write
  kernel and emits a single info log line confirming persistence. The
  log line MUST NOT echo the secret value (T-27-03-02).
  '''

  def test_auth_store_totp_log_redacts(
    self, tmp_path, monkeypatch, caplog,
  ) -> None:
    '''set_totp_secret('JBSWY3DPEHPK3PXP') — caplog scan finds zero
    occurrences of the raw base32 secret across all log levels.
    '''
    secret = 'JBSWY3DPEHPK3PXP'
    auth_path = tmp_path / 'auth.json'
    monkeypatch.setattr('auth_store.DEFAULT_AUTH_PATH', auth_path)

    with caplog.at_level(logging.DEBUG, logger='auth_store'):
      auth_store.set_totp_secret(secret)

    assert secret not in caplog.text, (
      f'T-27-03-02 leak: TOTP secret found in log:\n{caplog.text!r}'
    )
    # Sanity: at least one log line was emitted (proves we caught the
    # set_totp_secret log call rather than silently catching no logs).
    assert any('totp' in r.message.lower() for r in caplog.records), (
      'expected set_totp_secret to emit at least one log line'
    )


# =========================================================================
# Grep gate — zero raw-secret log/raise interpolations across covered files
# =========================================================================


class TestSecretRedactionGrepGate:
  '''Static check — every logger.* / raise-with-message in
  notifier/auth_store/data_fetcher that mentions an api_key/secret
  variable name MUST go through redact_secret OR a literal '[REDACTED]'
  scrub.

  This is a structural gate — it scans source text for known leak shapes
  rather than executing code. False positives are tolerable; false
  negatives are not.
  '''

  # CR-01 fix: notifier.py monolith deleted; scan every notifier/*.py
  # in the post-Plan 27-12 package layout instead.
  COVERED_FILES = tuple(
    [str(p) for p in __import__('pathlib').Path('notifier').glob('*.py')]
    + ['auth_store.py', 'data_fetcher.py']
  )

  # Suspicious pattern: an f-string or %-format interpolation of a bare
  # secret-named variable. Allows {api_key:redact_secret(...)} or
  # {redact_secret(api_key)} or '[REDACTED]'-scrubbed strings.
  LEAK_VARIABLE_NAMES = ('api_key', 'totp_secret', 'session_secret', 'token')

  def test_no_raw_secret_interpolation_in_logger_or_raise(self) -> None:
    import re as _re
    leaks: list[tuple[str, int, str]] = []
    for fname in self.COVERED_FILES:
      with open(fname, encoding='utf-8') as f:
        for lineno, line in enumerate(f, start=1):
          stripped = line.strip()
          if stripped.startswith('#'):
            continue
          # Only audit logger.* and raise lines.
          if not (
            _re.search(r'\blogger\.(info|warning|error|debug|critical)\b', line)
            or _re.match(r'\s*raise\s+[A-Z]', line)
          ):
            continue
          for name in self.LEAK_VARIABLE_NAMES:
            # f-string interpolation: f'... {api_key} ...' or .format(api_key=...)
            f_pat = _re.compile(r"f['\"][^'\"]*\{" + name + r"[^a-zA-Z_]")
            if f_pat.search(line):
              # Allow only if redact_secret wraps the variable inline.
              if f'redact_secret({name})' not in line:
                leaks.append((fname, lineno, line.rstrip()))
            # %-format with the variable name in trailing args:
            #   logger.warning('msg %s', api_key)
            pct_args = _re.compile(
              r'logger\.\w+\([^)]*%[sdr][^)]*\)',
            )
            if pct_args.search(line) and _re.search(
              rf'[,(]\s*{name}\s*[,)]', line,
            ):
              if f'redact_secret({name})' not in line:
                leaks.append((fname, lineno, line.rstrip()))
    assert not leaks, (
      'raw-secret interpolation in log/raise sites:\n  '
      + '\n  '.join(f'{f}:{n}: {l}' for f, n, l in leaks)
    )
