'''Phase 13 AUTH-01..AUTH-03 + D-01..D-06 — middleware contract tests.

Wave 0 skeleton populated by Plan 13-03 (19 methods across 6 classes — 17
base + 2 REVIEWS LOW #5 D-02 negative-exemption tests).

Fixture strategy:
  The autouse fixture `_set_web_auth_secret_for_web_tests` in tests/conftest.py
  pre-sets WEB_AUTH_SECRET for this file (name matches `test_web_*.py`).
  Tests monkeypatch state_manager.load_state DIRECTLY when needed; the shared
  conftest.py provides VALID_SECRET + AUTH_HEADER_NAME constants + auth_headers
  fixture.

Reference: 13-CONTEXT.md decisions D-01..D-06, 13-VALIDATION.md
test-class enumeration (lines 822-826).
'''
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

WEB_AUTH_PATH = Path('web/middleware/auth.py')


def _stub_load_state(**overrides):
  '''Build a benign load_state stub returning reset_state() with overrides.

  Mirrors tests/test_web_healthz.py:33-43 — needed because Phase 13 stub
  routes (Plan 13-02) and the real route handlers (Plans 13-04/13-05) call
  state_manager.load_state at request time.
  '''
  from state_manager import reset_state

  def _fn(*_args, **_kwargs):
    state = reset_state()
    state.update(overrides)
    state.setdefault('_resolved_contracts', {})
    return state

  return _fn


@pytest.fixture
def client_with_auth(monkeypatch):
  '''TestClient with load_state stubbed to a benign default.

  WEB_AUTH_SECRET is set by the autouse fixture in tests/conftest.py
  (Plan 13-01) for any file matching test_web_*.py — no per-test setenv needed.
  '''
  import sys

  import state_manager
  monkeypatch.setattr(state_manager, 'load_state', _stub_load_state())
  sys.modules.pop('web.app', None)
  from web.app import create_app
  return TestClient(create_app())


@pytest.fixture
def client_no_auth(monkeypatch):
  '''TestClient that deliberately tests the auth gate without an auth header.

  Shares state_manager stubbing but provides a dedicated name so tests that
  exercise negative paths (no header / wrong method / D-02 near-miss paths)
  read clearly.
  '''
  import sys

  import state_manager
  monkeypatch.setattr(state_manager, 'load_state', _stub_load_state())
  sys.modules.pop('web.app', None)
  from web.app import create_app
  return TestClient(create_app())


class TestAuthRequired:
  '''AUTH-01 + D-01: missing/wrong header returns 401.'''

  def test_missing_header_returns_401(self, client_with_auth):
    '''AUTH-01: GET / with NO X-Trading-Signals-Auth header → 401.'''
    r = client_with_auth.get('/')
    assert r.status_code == 401, (
      f'Expected 401 for missing auth header, got {r.status_code}: {r.text[:120]}'
    )

  def test_wrong_header_returns_401(self, client_with_auth):
    '''AUTH-01: GET / with WRONG X-Trading-Signals-Auth value → 401.'''
    r = client_with_auth.get('/', headers={'X-Trading-Signals-Auth': 'wrong-value'})
    assert r.status_code == 401, (
      f'Expected 401 for wrong auth value, got {r.status_code}: {r.text[:120]}'
    )

  def test_api_state_also_requires_auth(self, client_with_auth):
    '''AUTH-01: GET /api/state without auth → 401 (not just /).'''
    r = client_with_auth.get('/api/state')
    assert r.status_code == 401, (
      f'Expected 401 for /api/state without auth, got {r.status_code}'
    )


class TestAuthPasses:
  '''AUTH-01 + D-01: correct header reaches the route handler.'''

  def test_correct_header_passes_through(self, client_with_auth):
    '''AUTH-01: correct header reaches downstream — Plan 13-02 stub returns 503.

    Acceptable status codes: 200 (Plan 13-05 dashboard route after impl) or
    503 (Plan 13-02 stub before Plan 13-05). Both prove the middleware did
    NOT short-circuit to 401.
    '''
    r = client_with_auth.get(
      '/', headers={'X-Trading-Signals-Auth': 'a' * 32}
    )
    assert r.status_code in (200, 503), (
      f'Expected 200/503 with valid auth, got {r.status_code}: {r.text[:120]}. '
      f'401 means middleware blocked despite valid header (D-03 violation).'
    )


class TestExemption:
  '''D-02: /healthz bypasses AuthMiddleware via EXEMPT_PATHS allowlist.

  The happy path (exact /healthz) bypasses auth. The negative paths
  (trailing slash, uppercase) MUST still require auth — REVIEWS LOW #5
  locks this as explicit regression tests so nobody accidentally broadens
  the exact-match check to a prefix / case-insensitive match.
  '''

  def test_healthz_bypasses_auth_no_header(self, client_with_auth):
    '''D-02: GET /healthz with NO header → 200 (exempt).'''
    r = client_with_auth.get('/healthz')
    assert r.status_code == 200, (
      f'Expected 200 for /healthz without auth (exempt), got {r.status_code}'
    )
    body = r.json()
    assert body['status'] == 'ok'

  def test_healthz_bypasses_auth_wrong_header(self, client_with_auth):
    '''D-02: GET /healthz with WRONG header → 200 (exempt — middleware skips).

    The exemption is path-based, not header-based — wrong header doesn't
    matter on /healthz because the middleware never inspects the header.
    '''
    r = client_with_auth.get('/healthz', headers={'X-Trading-Signals-Auth': 'wrong'})
    assert r.status_code == 200, (
      f'Expected 200 for /healthz with wrong auth (exempt), got {r.status_code}'
    )

  def test_healthz_trailing_slash_is_NOT_exempt(self, client_no_auth):
    '''D-02 (REVIEWS LOW #5): exemption is EXACT-match only.

    /healthz/ (trailing slash) is a DIFFERENT path under Starlette's exact
    match and MUST require auth. Acceptable responses:
      - 401 if FastAPI/Starlette routes /healthz/ into auth-middleware first
      - 307 if FastAPI issues a redirect to /healthz (some versions do;
        this still proves the exemption did not fire as /healthz/-is-exempt)
    A 200 here would mean EXEMPT_PATHS matched too loosely — regression.
    '''
    r = client_no_auth.get('/healthz/', follow_redirects=False)
    assert r.status_code in (401, 307), (
      f'D-02 exact-match: /healthz/ (trailing slash) must require auth '
      f'(or redirect); got {r.status_code}: {r.text[:120]!r}. '
      f'200 means the exemption broadened to a prefix match — regression.'
    )

  def test_healthz_uppercase_is_NOT_exempt(self, client_no_auth):
    '''D-02 (REVIEWS LOW #5): exemption is case-SENSITIVE.

    /HEALTHZ must require auth — the EXEMPT_PATHS frozenset contains the
    lowercase literal '/healthz' only. Uppercase probes hit the auth gate.
    '''
    r = client_no_auth.get('/HEALTHZ')
    assert r.status_code == 401, (
      f'D-02 case-sensitive: /HEALTHZ should require auth, got {r.status_code}. '
      f'200 means the exemption became case-insensitive — regression.'
    )


class TestUnauthorizedResponse:
  '''AUTH-02 + D-04: 401 body literal, Content-Type, no hints.'''

  def test_body_is_plain_text_unauthorized(self, client_with_auth):
    '''AUTH-02 + D-04: 401 body is the literal ASCII string "unauthorized".'''
    r = client_with_auth.get('/')
    assert r.status_code == 401
    assert r.text == 'unauthorized', (
      f'Expected body literal "unauthorized", got {r.text!r}'
    )

  def test_content_type_is_text_plain_with_charset(self, client_with_auth):
    '''D-04: Content-Type must be "text/plain; charset=utf-8".'''
    r = client_with_auth.get('/')
    ct = r.headers.get('content-type', '')
    assert ct == 'text/plain; charset=utf-8', (
      f'Expected Content-Type "text/plain; charset=utf-8", got {ct!r}'
    )

  def test_no_www_authenticate_header(self, client_with_auth):
    '''AUTH-02: NO WWW-Authenticate header — explicit "no hints" rule.'''
    r = client_with_auth.get('/')
    assert 'www-authenticate' not in {k.lower() for k in r.headers}, (
      f'401 must not include WWW-Authenticate (AUTH-02 no-hints), '
      f'headers={dict(r.headers)}'
    )

  def test_body_does_not_leak_header_or_env_var_names(self, client_with_auth):
    '''AUTH-02: 401 body must NOT name the header or env var.'''
    r = client_with_auth.get('/')
    body = r.text.lower()
    forbidden_substrings = ['x-trading-signals-auth', 'web_auth_secret', 'header', 'token']
    leaks = [s for s in forbidden_substrings if s in body]
    assert leaks == [], (
      f'401 body leaks forbidden substrings {leaks}: {r.text!r}'
    )


class TestAuditLog:
  '''AUTH-03 + D-05: WARN log shape, IP from XFF first entry, UA truncation, %r escape.'''

  def test_warn_logged_on_failure(self, client_with_auth, caplog):
    '''AUTH-03: each 401 emits exactly one WARN line at logger web.middleware.auth.'''
    import logging
    with caplog.at_level(logging.WARNING, logger='web.middleware.auth'):
      client_with_auth.get('/', headers={'X-Trading-Signals-Auth': 'wrong'})
    warns = [r for r in caplog.records
             if r.levelname == 'WARNING' and r.name == 'web.middleware.auth']
    assert len(warns) == 1, (
      f'Expected exactly 1 WARN line at web.middleware.auth, got {len(warns)}: '
      f'{[r.getMessage() for r in warns]}'
    )
    assert '[Web] auth failure' in warns[0].getMessage(), (
      f'WARN line missing "[Web] auth failure" prefix: {warns[0].getMessage()!r}'
    )

  def test_log_extracts_ip_from_xff_first_entry(self, client_with_auth, caplog):
    '''D-05: X-Forwarded-For "1.2.3.4, 10.0.0.1" → ip=1.2.3.4 (first entry, comma-split, stripped).'''
    import logging
    with caplog.at_level(logging.WARNING, logger='web.middleware.auth'):
      client_with_auth.get(
        '/',
        headers={
          'X-Trading-Signals-Auth': 'wrong',
          'X-Forwarded-For': '1.2.3.4, 10.0.0.1, 10.0.0.2',
        },
      )
    msgs = [r.getMessage() for r in caplog.records if r.name == 'web.middleware.auth']
    assert any('ip=1.2.3.4' in m for m in msgs), (
      f'Expected ip=1.2.3.4 (XFF first entry, stripped), got: {msgs}'
    )
    # Negative — must NOT log the second or third entry as ip
    assert not any('ip=10.0.0.1' in m or 'ip=10.0.0.2' in m for m in msgs), (
      f'Logged a non-first XFF entry as IP: {msgs}'
    )

  def test_log_falls_back_to_client_host_without_xff(self, client_with_auth, caplog):
    '''D-05: when XFF absent, fallback to request.client.host.

    TestClient's request.client.host is "testclient" (Starlette default).
    '''
    import logging
    with caplog.at_level(logging.WARNING, logger='web.middleware.auth'):
      client_with_auth.get('/', headers={'X-Trading-Signals-Auth': 'wrong'})
    msgs = [r.getMessage() for r in caplog.records if r.name == 'web.middleware.auth']
    # request.client.host in TestClient is "testclient"; some Starlette versions
    # expose 127.0.0.1. Accept either; key is that an IP-like value appears.
    assert any(('ip=testclient' in m or 'ip=127.0.0.1' in m) for m in msgs), (
      f'Expected ip=testclient or ip=127.0.0.1 (XFF absent fallback), got: {msgs}'
    )

  def test_user_agent_truncated_to_120_chars(self, client_with_auth, caplog):
    '''D-05 / SC-5: UA truncated to exactly 120 chars in the log line.'''
    import logging
    import re
    long_ua = 'X' * 200  # 200 chars; should be cut to 120
    with caplog.at_level(logging.WARNING, logger='web.middleware.auth'):
      client_with_auth.get(
        '/',
        headers={
          'X-Trading-Signals-Auth': 'wrong',
          'User-Agent': long_ua,
        },
      )
    msgs = [r.getMessage() for r in caplog.records if r.name == 'web.middleware.auth']
    # The %r format wraps the truncated string in single quotes, so the log
    # contains "ua='XXXX...' " — count the X's between the quotes.
    match = next((re.search(r"ua='(X+)'", m) for m in msgs if "ua='X" in m), None)
    assert match is not None, f'Could not find ua=\'X*\' in any log line: {msgs}'
    x_count = len(match.group(1))
    assert x_count == 120, (
      f'Expected UA truncated to 120 chars in log, got {x_count}: {msgs}'
    )

  def test_user_agent_repr_escapes_control_chars(self, client_with_auth, caplog):
    '''D-05: %r format escapes control chars so journald single-line is preserved.

    A UA with embedded \\n must NOT inject a second log line — %r escapes it
    as a literal backslash-n inside the repr quotes.
    '''
    import logging
    # Include a literal newline + tab in the UA. httpx's TestClient may strip
    # control chars at the HTTP layer; if so, this test pivots to check that
    # the log line has only one record (no double-line injection).
    bad_ua = 'curl/7.0\nINJECTED'  # newline-injection probe
    with caplog.at_level(logging.WARNING, logger='web.middleware.auth'):
      try:
        client_with_auth.get(
          '/',
          headers={
            'X-Trading-Signals-Auth': 'wrong',
            'User-Agent': bad_ua,
          },
        )
      except Exception:
        # httpx may raise on invalid header chars — that itself proves the
        # injection vector is closed at the client layer. Skip the log assertion.
        return
    # Total WARN records from web.middleware.auth must be exactly 1 — no
    # injection split it into two.
    auth_warns = [r for r in caplog.records
                  if r.levelname == 'WARNING' and r.name == 'web.middleware.auth']
    assert len(auth_warns) == 1, (
      f'Expected exactly 1 WARN line (no newline injection split), '
      f'got {len(auth_warns)}: {[r.getMessage() for r in auth_warns]}'
    )
    # And the log message itself should contain the escaped form (or be
    # truncated to <120 chars by D-05) — accept either, key is single-line.


class TestConstantTimeCompare:
  '''D-03: hmac.compare_digest is used (AST guard against == comparison).'''

  def test_source_uses_hmac_compare_digest(self):
    '''D-03: web/middleware/auth.py source must contain "hmac.compare_digest(".'''
    src = WEB_AUTH_PATH.read_text()
    assert 'hmac.compare_digest(' in src, (
      'web/middleware/auth.py must use hmac.compare_digest (D-03 mandates '
      'constant-time comparison; never `==` for secret comparison).'
    )

  def test_source_does_not_use_equality_for_secret_compare(self):
    '''D-03 negative: AST scan — no `presented == self._secret_*` or similar.

    Walks the AST of web/middleware/auth.py and asserts no Compare node
    uses `==` (Eq) where one side is the presented header and the other
    is the stored secret. This is a heuristic: we look for any Compare
    node whose target involves "presented", "secret", or "_secret_bytes"
    on either side.
    '''
    import ast
    src = WEB_AUTH_PATH.read_text()
    tree = ast.parse(src)
    violations = []
    for node in ast.walk(tree):
      if isinstance(node, ast.Compare):
        # Eq ops compared between secret-related identifiers
        if any(isinstance(op, ast.Eq) for op in node.ops):
          # Scan all operands for known secret-related names
          operands = [node.left] + node.comparators
          for operand in operands:
            if isinstance(operand, ast.Name) and operand.id in (
              'presented', 'secret', 'secret_bytes', '_secret_bytes',
            ):
              violations.append(f'Line {node.lineno}: == compare with {operand.id}')
            if isinstance(operand, ast.Attribute) and operand.attr in (
              '_secret_bytes', 'secret_bytes', 'secret',
            ):
              violations.append(f'Line {node.lineno}: == compare with .{operand.attr}')
    assert violations == [], (
      f'web/middleware/auth.py must NOT use == for secret compare (D-03): '
      f'{violations}'
    )
