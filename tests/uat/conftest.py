'''Phase 28 UAT substrate (DEBT-01).

All tests under tests/uat/ are gated by `@pytest.mark.uat` and excluded
from the default `pytest` invocation. Run the full UAT pass with:

    pytest -m uat

The base_url targets the live production droplet. There is no staging
clone (project convention). Specs MUST be read-only against production
(no POSTs, no signal mutations) — see SECURITY threat model in PLAN-01.

Auth: the production droplet authenticates via X-Trading-Signals-Auth
header (per web/middleware/auth.py, validated against env WEB_AUTH_SECRET).
Plan 06 wires this in: WEB_AUTH_SECRET is read from the gitignored
.env.uat file (or process env as fallback) and injected via Playwright's
extra_http_headers on every request. Tests that don't need auth (none
in the v1.2 set) still inherit the header — droplet ignores it on
PUBLIC_PATHS.
'''
from __future__ import annotations

import os
from pathlib import Path

import pytest

BASE_URL = os.environ.get('UAT_BASE_URL', 'https://signals.mwiriadi.me')
TRACE_DIR = Path(__file__).parent / '_traces'
TRACE_DIR.mkdir(exist_ok=True)


def _load_env_uat() -> dict[str, str]:
  '''Parse .env.uat from repo root if present. Tolerant: KEY=value lines,
  blank/comment lines ignored, no quoting magic. Operator-only file,
  gitignored, never committed.
  '''
  env_path = Path(__file__).resolve().parents[2] / '.env.uat'
  if not env_path.is_file():
    return {}
  out: dict[str, str] = {}
  for line in env_path.read_text(encoding='utf-8').splitlines():
    s = line.strip()
    if not s or s.startswith('#') or '=' not in s:
      continue
    k, _, v = s.partition('=')
    out[k.strip()] = v.strip().strip('"').strip("'")
  return out


_ENV_UAT = _load_env_uat()


def _secret() -> str | None:
  '''Resolve WEB_AUTH_SECRET from process env or .env.uat. Process env wins.'''
  return os.environ.get('WEB_AUTH_SECRET') or _ENV_UAT.get('WEB_AUTH_SECRET')


@pytest.fixture(scope='session')
def base_url() -> str:
  return BASE_URL


@pytest.fixture
def browser_context_args(browser_context_args):
  # Note: do NOT inject WEB_AUTH_SECRET via extra_http_headers — that
  # would attach the header to cross-origin requests too (vendored CDN
  # scripts), triggering CORS preflights the CDN rejects (caught
  # 2026-05-10 by UAT-26-1 cold-start). The `page` fixture below
  # registers a route handler that adds the header ONLY for same-origin
  # requests to BASE_URL.
  return {**browser_context_args, 'base_url': BASE_URL}


_BASE_HOST = BASE_URL.split('//', 1)[-1].split('/', 1)[0]


def _install_auth_route(page) -> None:
  '''Add X-Trading-Signals-Auth to same-origin requests only.

  Glob is scoped to BASE_URL (`https://signals.mwiriadi.me/**`) so
  cross-origin scripts (CDN-hosted vendor JS) are NOT intercepted —
  intercepting them risks (a) CORS preflight failure when the auth
  header would attach, (b) subtle response-body differences when
  Playwright proxies a cross-origin response that triggered a
  vague "missing ) after argument list" SyntaxError on cold-start.
  '''
  secret = _secret()
  if not secret:
    return

  def handler(route):
    req = route.request
    hdrs = dict(req.headers)
    hdrs['X-Trading-Signals-Auth'] = secret
    route.continue_(headers=hdrs)

  page.route(lambda url: _BASE_HOST in url, handler)


@pytest.fixture
def page(page, request):
  _install_auth_route(page)
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
  '''Return (user, pass) from env or None to skip the test.

  Kept for forward-compat — Phase 16.1 cookie-session login needs both
  credentials + TOTP, which the v1.2 UAT set does not exercise. Header
  auth via WEB_AUTH_SECRET (above) is sufficient for the Phase 28 specs.
  '''
  u = os.environ.get('UAT_USER') or _ENV_UAT.get('UAT_USER')
  p = os.environ.get('UAT_PASS') or _ENV_UAT.get('UAT_PASS')
  if not u or not p:
    return None
  return u, p
