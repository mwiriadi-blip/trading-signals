'''Phase 13 AUTH-01..AUTH-03 + D-01..D-06 — middleware contract tests.

Wave 0 skeleton — test bodies populated by Plan 13-03.

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


class TestAuthRequired:
  '''AUTH-01 + D-01: missing/wrong header returns 401.'''
  pass


class TestAuthPasses:
  '''AUTH-01 + D-01: correct header reaches the route handler.'''
  pass


class TestExemption:
  '''D-02: /healthz bypasses AuthMiddleware via EXEMPT_PATHS allowlist.'''
  pass


class TestUnauthorizedResponse:
  '''AUTH-02 + D-04: 401 body literal and headers.'''
  pass


class TestAuditLog:
  '''AUTH-03 + D-05: WARN log shape (ip from XFF first entry, ua truncated %r-escaped, path).'''
  pass


class TestConstantTimeCompare:
  '''D-03: hmac.compare_digest is used (AST guard against == comparison).'''
  pass
