'''Phase 28 UAT substrate (DEBT-01).

All tests under tests/uat/ are gated by `@pytest.mark.uat` and excluded
from the default `pytest` invocation. Run the full UAT pass with:

    pytest -m uat

The base_url targets the live production droplet. There is no staging
clone (project convention). Specs MUST be read-only against production
(no POSTs, no signal mutations) — see SECURITY threat model in PLAN-01.

Credentials policy: this conftest does NOT hardcode session tokens.
Specs that need an authenticated session must read UAT_USER + UAT_PASS
from the environment and skip cleanly if absent.
'''
from __future__ import annotations

import os
from pathlib import Path

import pytest

BASE_URL = os.environ.get('UAT_BASE_URL', 'https://signals.mwiriadi.me')
TRACE_DIR = Path(__file__).parent / '_traces'
TRACE_DIR.mkdir(exist_ok=True)


@pytest.fixture(scope='session')
def base_url() -> str:
  return BASE_URL


@pytest.fixture
def browser_context_args(browser_context_args):
  # Record traces; keep them gitignored (see .gitignore).
  return {**browser_context_args, 'base_url': BASE_URL}


@pytest.fixture
def page(page, request):
  # Start a Playwright trace per test; on failure write to TRACE_DIR.
  page.context.tracing.start(screenshots=True, snapshots=True, sources=False)
  yield page
  outcome = getattr(request.node, 'rep_call', None)
  failed = outcome is not None and outcome.failed
  trace_path = TRACE_DIR / f'{request.node.name}.zip'
  if failed:
    page.context.tracing.stop(path=str(trace_path))
  else:
    page.context.tracing.stop()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
  outcome = yield
  rep = outcome.get_result()
  setattr(item, f'rep_{rep.when}', rep)


def uat_credentials() -> tuple[str, str] | None:
  '''Return (user, pass) from env or None to skip the test.'''
  u = os.environ.get('UAT_USER')
  p = os.environ.get('UAT_PASS')
  if not u or not p:
    return None
  return u, p
