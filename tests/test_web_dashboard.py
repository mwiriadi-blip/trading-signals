'''Phase 13 WEB-05 + D-07..D-11 — GET / dashboard contract tests.

Wave 0 skeleton — test bodies populated by Plan 13-05.

Reference: 13-CONTEXT.md D-07..D-11, 13-VALIDATION.md test-class
enumeration (lines 787-792).
'''
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


class TestDashboardResponse:
  '''D-07: GET / serves dashboard.html via FileResponse with text/html.'''
  pass


class TestStaleness:
  '''D-08: state.json mtime > dashboard.html mtime triggers regen.'''
  pass


class TestRenderFailure:
  '''D-10: render exception is logged WARN; stale on-disk copy is served (200).'''
  pass


class TestFirstRun:
  '''D-10: dashboard.html absent → 503 "dashboard not ready" (plain text).'''
  pass
