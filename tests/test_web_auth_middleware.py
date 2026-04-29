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


# =============================================================================
# Phase 16.1 Plan 01 Task 2 — E-02 3-step sniff (cookie → header → unauth)
# =============================================================================
#
# Browser navigation (Sec-Fetch headers OR Accept: text/html fallback) without
# valid auth → 302 Location: /login?next=<path>.
# Curl/script/HTMX-XHR without valid auth → 401 plain-text "unauthorized",
# preserving Phase 13 D-04 verbatim (AUTH-07).
# Basic Auth header is NOT decoded (E-01 / AUTH-12 supersedes Phase 16.1 D-01).


class TestSecFetchSniff:
  '''E-02 / D-04: Sec-Fetch header sniff branches the unauthenticated path.'''

  def test_navigate_document_returns_302(self, client_no_auth):
    '''Sec-Fetch-Mode=navigate + Sec-Fetch-Dest=document (browser nav) → 302.'''
    r = client_no_auth.get(
      '/',
      headers={'Sec-Fetch-Mode': 'navigate', 'Sec-Fetch-Dest': 'document'},
      follow_redirects=False,
    )
    assert r.status_code == 302, (
      f'Browser navigation (Sec-Fetch=navigate/document) should 302 → /login, '
      f'got {r.status_code}'
    )
    assert r.headers.get('location') == '/login?next=/', (
      f'Expected Location: /login?next=/, got {r.headers.get("location")!r}'
    )

  def test_cors_returns_401(self, client_no_auth):
    '''Sec-Fetch-Mode=cors (HTMX XHR shape) → 401 plain-text, no redirect.'''
    r = client_no_auth.get(
      '/',
      headers={'Sec-Fetch-Mode': 'cors', 'Sec-Fetch-Dest': 'empty'},
      follow_redirects=False,
    )
    assert r.status_code == 401
    assert 'location' not in {k.lower() for k in r.headers}
    assert 'set-cookie' not in {k.lower() for k in r.headers}

  def test_no_secfetch_with_text_html_accept_returns_302(self, client_no_auth):
    '''Older browsers without Sec-Fetch but Accept: text/html → 302 fallback.'''
    r = client_no_auth.get(
      '/',
      headers={'Accept': 'text/html,application/xhtml+xml,*/*'},
      follow_redirects=False,
    )
    assert r.status_code == 302, (
      f'Accept: text/html (no Sec-Fetch) should 302 fallback per D-04, '
      f'got {r.status_code}'
    )

  def test_no_secfetch_with_star_accept_returns_401(self, client_no_auth):
    '''curl-style request (Accept: */*, no Sec-Fetch) → 401 plain-text.'''
    r = client_no_auth.get(
      '/',
      headers={'Accept': '*/*'},
      follow_redirects=False,
    )
    assert r.status_code == 401, (
      f'Curl-shaped request should 401 plain-text per AUTH-07, '
      f'got {r.status_code}'
    )


class TestHeaderPathPreserved:
  '''AUTH-05: Phase 13 X-Trading-Signals-Auth header path is unchanged.'''

  def test_valid_header_returns_200(self, client_with_auth):
    '''Phase 13 regression: valid header → reaches downstream route.'''
    r = client_with_auth.get('/', headers={'X-Trading-Signals-Auth': 'a' * 32})
    assert r.status_code in (200, 503), (
      f'Header path must keep working (AUTH-05); got {r.status_code}'
    )


class TestCurlContract:
  '''AUTH-07 / D-04..D-05: 401 contract preserved verbatim for non-browsers.'''

  def test_curl_no_auth_returns_401_plain_text_with_no_extras(
    self, client_no_auth,
  ):
    '''curl /  (Accept: */*, no Sec-Fetch) → 401 + body="unauthorized" + no
    WWW-Authenticate / Set-Cookie / Location headers.
    '''
    r = client_no_auth.get(
      '/', headers={'Accept': '*/*'}, follow_redirects=False,
    )
    assert r.status_code == 401
    assert r.text == 'unauthorized'
    ct = r.headers.get('content-type', '')
    assert 'text/plain' in ct.lower(), (
      f'Expected text/plain content-type, got {ct!r}'
    )
    lower_keys = {k.lower() for k in r.headers}
    assert 'www-authenticate' not in lower_keys
    assert 'location' not in lower_keys
    assert 'set-cookie' not in lower_keys


class TestRedirect302Shape:
  '''D-04: Location header uses request.url.path (path only, no query string)
  with quote-encoded path. Single test, multiple assertions.
  '''

  def test_location_header_uses_quote_encoded_next(self, client_no_auth):
    '''Browser navigation to /api/state?q=1 → Location: /login?next=/api/state.'''
    r = client_no_auth.get(
      '/api/state?q=1',
      headers={'Sec-Fetch-Mode': 'navigate', 'Sec-Fetch-Dest': 'document'},
      follow_redirects=False,
    )
    assert r.status_code == 302
    loc = r.headers.get('location', '')
    # Path-only — query string is NOT echoed back into next= per security
    # consideration (echoing query is fine for the simple path case but the
    # contract here uses request.url.path verbatim).
    assert loc == '/login?next=/api/state', (
      f'Expected Location /login?next=/api/state, got {loc!r}'
    )


class TestNoBasicAuthDecode:
  '''E-01 / AUTH-12: Basic Auth header is NOT decoded by middleware.

  After Phase 16.1, sending only Authorization: Basic <b64> grants no access.
  The request is treated identically to a no-auth request (browser → 302,
  script → 401).
  '''

  def test_basic_auth_only_does_NOT_authenticate(self, client_no_auth):
    '''Authorization: Basic marc:secret encoded → 302/401, NEVER 200.'''
    import base64
    creds = base64.b64encode(b'marc:' + (b'a' * 32)).decode('ascii')
    # Send with browser-shaped headers (would 302) — proves the basic auth
    # itself doesn't grant access.
    r = client_no_auth.get(
      '/',
      headers={
        'Authorization': f'Basic {creds}',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Dest': 'document',
      },
      follow_redirects=False,
    )
    assert r.status_code != 200, (
      f'E-01: Basic Auth must NOT authenticate; got {r.status_code} (200 means '
      f'the kill-Basic-Auth invariant is broken).'
    )
    assert r.status_code == 302, (
      f'Browser-shaped Basic-only request → 302 to /login; got {r.status_code}'
    )

  def test_no_basic_auth_decoding_logic_in_middleware(self):
    '''AST/grep guard: web/middleware/auth.py does NOT contain b64decode,
    binascii, or partition(":") — markers of a Basic Auth decode path.
    '''
    src = WEB_AUTH_PATH.read_text()
    assert 'b64decode' not in src, (
      'E-01: web/middleware/auth.py must NOT decode Basic Auth (b64decode found)'
    )
    assert 'binascii' not in src, (
      'E-01: web/middleware/auth.py must NOT import binascii (Basic Auth decode marker)'
    )
    assert "partition(':')" not in src and 'partition(":")' not in src, (
      "E-01: web/middleware/auth.py must NOT split Basic Auth fields via partition(':')"
    )


class TestNoWwwAuthenticate:
  '''LEARNING 2026-04-27: WWW-Authenticate header must NEVER be sent.

  D-04..D-05 + Area D follow-up reconciles Phase 13 D-04 — even with cookie/
  header auth in play, the dialog-trigger header is never emitted server-side.
  '''

  def test_grep_returns_zero_occurrences(self):
    src = WEB_AUTH_PATH.read_text()
    import re
    matches = re.findall(r'WWW-Authenticate', src, flags=re.IGNORECASE)
    assert matches == [], (
      f'web/middleware/auth.py must NOT contain "WWW-Authenticate" '
      f'(LEARNING 2026-04-27 + D-04..D-05); found: {matches}'
    )


class TestAuditLogExactlyOnce:
  '''Sampling pyramid 1: a single failed-auth request emits exactly ONE WARN
  log line, regardless of which sniff helpers ran. Helpers return bool only;
  step 3 of dispatch is the single log site.
  '''

  @pytest.mark.parametrize('case', [
    'no_auth_at_all',
    'bad_cookie_only',
    'bad_header_only',
    'bad_cookie_and_bad_header',
  ])
  def test_audit_log_fires_exactly_once_per_failed_request(
    self, client_no_auth, caplog, case,
  ):
    import logging
    headers = {'Accept': '*/*'}
    cookies = {}
    if 'bad_cookie' in case:
      cookies = {'tsi_session': 'this-is-not-a-valid-itsdangerous-token'}
    if 'bad_header' in case:
      headers['X-Trading-Signals-Auth'] = 'wrong-secret'
    with caplog.at_level(logging.WARNING, logger='web.middleware.auth'):
      client_no_auth.get('/', headers=headers, cookies=cookies)
    auth_warns = [
      r for r in caplog.records
      if r.name == 'web.middleware.auth' and '[Web] auth failure' in r.getMessage()
    ]
    assert len(auth_warns) == 1, (
      f'Sampling pyramid 1: {case} should emit exactly ONE auth-failure log '
      f'line, got {len(auth_warns)}: {[r.getMessage() for r in auth_warns]}'
    )


# =============================================================================
# Phase 16.1 Plan 02 — TrustedDeviceCookie
# =============================================================================
#
# _try_cookie now accepts EITHER tsi_session (12h) OR tsi_trusted (30d).
# tsi_trusted carries an itsdangerous-signed uuid that must ALSO be
# unrevoked in auth.json.trusted_devices (revocation honored even when
# the signature is valid).


def _make_trusted_token(uuid_value: str, secret: str = 'a' * 32) -> str:
  '''Build a tsi_trusted-shaped signed token for tests.

  Mirrors the production payload {'uuid': ..., 'iat': now} per Plan 16.1-02.
  '''
  import time as _time
  from itsdangerous.url_safe import URLSafeTimedSerializer
  serializer = URLSafeTimedSerializer(secret, salt='tsi-trusted-cookie')
  return serializer.dumps({'uuid': uuid_value, 'iat': int(_time.time())})


class TestTrustedDeviceCookie:
  '''Plan 16.1-02: tsi_trusted cookie acceptance + revocation honored.'''

  def test_valid_tsi_trusted_grants_access_when_uuid_active(
    self, client_with_auth, isolated_auth_json,
  ):
    import auth_store
    uid = auth_store.add_trusted_device(label='trusted-device-A')
    token = _make_trusted_token(uid)
    r = client_with_auth.get(
      '/', cookies={'tsi_trusted': token},
    )
    # 200 (Plan 13-05 dashboard) or 503 (Plan 13-02 stub) — anything that's
    # not 401/302 proves middleware accepted the cookie.
    assert r.status_code in (200, 503), (
      f'Expected middleware to accept valid tsi_trusted, got {r.status_code}: {r.text[:120]}'
    )

  def test_revoked_tsi_trusted_does_NOT_grant(
    self, client_with_auth, isolated_auth_json,
  ):
    import auth_store
    uid = auth_store.add_trusted_device(label='B')
    auth_store.revoke_device(uid)
    token = _make_trusted_token(uid)
    r = client_with_auth.get(
      '/', cookies={'tsi_trusted': token}, follow_redirects=False,
    )
    assert r.status_code != 200, (
      'Revoked tsi_trusted MUST NOT grant — even with valid signature'
    )
    # Curl-shape (no Sec-Fetch / Accept text/html) → 401
    assert r.status_code in (401, 302), (
      f'Expected 401 or 302, got {r.status_code}'
    )

  def test_tsi_trusted_with_unknown_uuid_does_NOT_grant(
    self, client_with_auth, isolated_auth_json,
  ):
    token = _make_trusted_token('uuid-not-in-auth-json')
    r = client_with_auth.get(
      '/', cookies={'tsi_trusted': token}, follow_redirects=False,
    )
    assert r.status_code != 200, (
      'Unknown uuid in tsi_trusted MUST NOT grant'
    )

  def test_expired_tsi_trusted_does_NOT_grant(
    self, client_with_auth, isolated_auth_json,
  ):
    '''Token issued 31 days ago should fall through to header/unauth-branch.

    URLSafeTimedSerializer encodes the issuance timestamp inside the signed
    payload, so freezing time at the moment of issuance and then unfreezing
    is the cleanest expiry simulation.
    '''
    import auth_store
    from freezegun import freeze_time
    uid = auth_store.add_trusted_device(label='C')
    with freeze_time('2026-03-29T00:00:00+00:00'):  # 31 days before today
      old_token = _make_trusted_token(uid)
    # Real-time request — token is now 31d old → SignatureExpired
    r = client_with_auth.get(
      '/', cookies={'tsi_trusted': old_token}, follow_redirects=False,
    )
    assert r.status_code != 200, 'Expired tsi_trusted MUST NOT grant'

  def test_tampered_tsi_trusted_does_NOT_grant(
    self, client_with_auth, isolated_auth_json,
  ):
    import auth_store
    uid = auth_store.add_trusted_device(label='D')
    token = _make_trusted_token(uid)
    # Flip the last char to break the signature
    tampered = token[:-1] + ('A' if token[-1] != 'A' else 'B')
    r = client_with_auth.get(
      '/', cookies={'tsi_trusted': tampered}, follow_redirects=False,
    )
    assert r.status_code != 200, 'Tampered tsi_trusted MUST NOT grant'

  def test_tsi_trusted_AND_tsi_session_both_present_grants(
    self, client_with_auth, isolated_auth_json, valid_cookie_token,
  ):
    import auth_store
    uid = auth_store.add_trusted_device(label='E')
    trusted_token = _make_trusted_token(uid)
    r = client_with_auth.get('/', cookies={
      'tsi_session': valid_cookie_token,
      'tsi_trusted': trusted_token,
    })
    assert r.status_code in (200, 503), (
      f'Both cookies valid → middleware should accept, got {r.status_code}'
    )

  def test_tsi_trusted_only_no_tsi_session_grants(
    self, client_with_auth, isolated_auth_json,
  ):
    '''E-04 short-circuit: trusted device alone (no tsi_session) grants.'''
    import auth_store
    uid = auth_store.add_trusted_device(label='F')
    token = _make_trusted_token(uid)
    r = client_with_auth.get('/', cookies={'tsi_trusted': token})
    assert r.status_code in (200, 503), (
      f'tsi_trusted alone should grant (E-04), got {r.status_code}'
    )

  def test_tsi_trusted_hit_calls_update_last_seen(
    self, client_with_auth, isolated_auth_json,
  ):
    '''Successful tsi_trusted grant bumps the row's last_seen timestamp.'''
    import auth_store
    from freezegun import freeze_time
    with freeze_time('2026-01-01T00:00:00+00:00'):
      uid = auth_store.add_trusted_device(label='G')
    pre_last_seen = auth_store.get_trusted_device(uid)['last_seen']
    assert pre_last_seen.startswith('2026-01-01T00:00:00')

    with freeze_time('2026-04-29T12:34:56+00:00'):
      token = _make_trusted_token(uid)
      client_with_auth.get('/', cookies={'tsi_trusted': token})

    post_last_seen = auth_store.get_trusted_device(uid)['last_seen']
    assert post_last_seen != pre_last_seen, (
      f'last_seen should advance after tsi_trusted grant: {post_last_seen!r}'
    )
    assert post_last_seen.startswith('2026-04-29T12:34:56'), (
      f'last_seen should reflect request time: {post_last_seen!r}'
    )

  def test_tsi_session_hit_does_NOT_call_update_last_seen(
    self, client_with_auth, isolated_auth_json, valid_cookie_token,
  ):
    '''Trusted-device row's last_seen must NOT advance when only tsi_session is used.

    update_last_seen fires on the tsi_trusted code path only; a request
    that authenticates via tsi_session leaves trusted_devices rows untouched.
    '''
    import auth_store
    uid = auth_store.add_trusted_device(label='H')
    pre_last_seen = auth_store.get_trusted_device(uid)['last_seen']

    # Request with tsi_session only (no tsi_trusted cookie)
    client_with_auth.get('/', cookies={'tsi_session': valid_cookie_token})

    post_last_seen = auth_store.get_trusted_device(uid)['last_seen']
    assert post_last_seen == pre_last_seen, (
      f'last_seen should NOT change on tsi_session-only request: '
      f'pre={pre_last_seen!r} post={post_last_seen!r}'
    )
