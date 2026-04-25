'''Phase 13 D-16/D-17/D-21+ — create_app() factory contract tests.

Wave 0 skeleton — test bodies populated by Plan 13-02.

Reference: 13-CONTEXT.md D-16..D-21, 13-RESEARCH.md §Pitfall 1
(openapi_url=None research extension), 13-VALIDATION.md test-class
enumeration (lines 798-805).
'''
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


class TestSecretValidation:
  '''D-16/D-17: missing, empty, or <32-char WEB_AUTH_SECRET → RuntimeError at boot.'''
  pass


class TestDocsDisabled:
  '''D-21 + RESEARCH extension: /docs, /redoc, /openapi.json all disabled.'''
  pass
