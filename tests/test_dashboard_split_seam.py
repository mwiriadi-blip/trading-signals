"""Plan 27-14 Task 4 + Phase 32 Plan 04 Task 3: dashboard split parity gates.

Structural assertions for the dashboard_renderer/ split:

  1. test_dashboard_files_under_500_loc — dashboard_renderer/*.py LOC caps.
  2. test_dashboard_html_output_byte_identical — render_dashboard_files against
     the canonical fixture produces output byte-identical to the golden.
  3. test_fastapi_dashboard_route_smoke — review-fix agreed-10: route-level
     test in addition to renderer unit tests. Hits the FastAPI app and
     asserts the dashboard route returns valid HTML.
"""
import json
import pathlib
import sys
from datetime import datetime

import pytest
import pytz
from fastapi.testclient import TestClient

import dashboard_renderer.api as dashboard


# Fixtures + constants
DASHBOARD_FIXTURE_DIR = pathlib.Path(__file__).parent / 'fixtures' / 'dashboard'
SAMPLE_STATE_PATH = DASHBOARD_FIXTURE_DIR / 'sample_state.json'
GOLDEN_PATH = pathlib.Path(__file__).parent / 'fixtures' / 'dashboard_canonical.html'

PERTH = pytz.timezone('Australia/Perth')
FROZEN_NOW = PERTH.localize(datetime(2026, 4, 22, 9, 0))

# AUTH header constants — match tests/test_web_dashboard.py.
VALID_SECRET = 'a' * 32
AUTH_HEADER_NAME = 'X-Trading-Signals-Auth'


def test_dashboard_files_under_500_loc() -> None:
  """43-07: dashboard_legacy/ and dashboard.py shim removed; LOC caps hold.

  dashboard_renderer/*.py all <=500 LOC (assets.py exempt — CSS/JS data file).
  """
  _repo = pathlib.Path(__file__).parent.parent
  assert not (_repo / 'dashboard_legacy').exists(), (
    'dashboard_legacy/ tombstone must be deleted (43-07)'
  )
  assert not (_repo / 'dashboard.py').exists(), (
    'dashboard.py shim must be deleted (43-07)'
  )

  too_big = []
  for f in sorted((_repo / 'dashboard_renderer').rglob('*.py')):
    if f.name == 'assets.py':
      continue  # exempt: data file (CSS/JS constants), not subject to LOC cap
    loc = f.read_text().count('\n')
    if loc >= 550:
      too_big.append((str(f), loc))
  assert not too_big, (
    'dashboard_renderer/*.py LOC budget violated '
    '(<500 plan target; <550 M1 ±10% tolerance):\n  '
    + '\n  '.join(f'{p}: {n} LOC' for p, n in too_big)
  )


def test_dashboard_html_output_byte_identical(tmp_path) -> None:
  """Plan 27-14 truth #3: HTML output byte-identical pre/post-split.

  Golden = post-split capture (Task 1) at HEAD AFTER 27-08 + 27-11 land.
  Strip the SHA-header comment line for the comparison; the rest of the
  file must match render_dashboard(sample_state.json, FROZEN_NOW)
  byte-for-byte.
  """
  state = json.loads(SAMPLE_STATE_PATH.read_text())
  out = tmp_path / 'd.html'
  dashboard.render_dashboard_files(state, out_path=out, now=FROZEN_NOW)
  rendered = out.read_bytes()

  golden_full = GOLDEN_PATH.read_bytes()
  # First line is `<!-- captured at HEAD <SHA> after 27-08+27-11 -->\n`
  # (added by Task 1). Everything after is the canonical render bytes.
  first_newline = golden_full.index(b'\n')
  golden_body = golden_full[first_newline + 1:]

  assert rendered == golden_body, (
    'HTML output drifted across split. dashboard.py + dashboard_legacy/* '
    'must produce byte-identical render to the Task 1 golden. '
    f'Lengths: rendered={len(rendered)}, golden={len(golden_body)}.'
  )


def test_fastapi_dashboard_route_smoke(tmp_path, monkeypatch) -> None:
  """Plan 27-14 review-fix agreed-10: route-level test in addition to
  renderer unit tests. Hits the FastAPI dashboard route through the real
  app stack and asserts the response is structurally a complete HTML page.

  Mirrors the auth + chdir + render-stub pattern from
  tests/test_web_dashboard.py::client_with_dashboard so this stays
  hermetic (no real disk read of state.json, no daily-loop dependency).
  """
  # Plan 16.1 boot-validates these via web/app.py::_read_auth_credentials.
  # tests/test_web_*.py get them from the autouse fixture in conftest.py;
  # this file's name doesn't match that pattern so we set them explicitly.
  monkeypatch.setenv('WEB_AUTH_SECRET', VALID_SECRET)
  monkeypatch.setenv('WEB_AUTH_USERNAME', 'opuser')
  monkeypatch.setenv('OPERATOR_RECOVERY_EMAIL', 'op@example.com')

  monkeypatch.chdir(tmp_path)

  # Stub state_manager.load_state (mirrors test_web_dashboard.py).
  import state_manager
  monkeypatch.setattr(
    state_manager, 'load_state',
    lambda *_a, **_kw: {'schema_version': 1, 'last_run': '2026-04-25'},
  )

  # Stub render_dashboard_files to write a minimal valid HTML payload to disk.
  def _track_render(state, *args, **kwargs):
    out = kwargs.get('out_path') or pathlib.Path('dashboard.html')
    pathlib.Path(out).write_text(
      '<!DOCTYPE html><html><nav class="tabs tabs-function"></nav>'
      '<body>route-smoke</body></html>',
      encoding='utf-8',
    )

  monkeypatch.setattr(dashboard, 'render_dashboard_files', _track_render)

  # Pre-create the dashboard.html so GET / can serve it.
  pathlib.Path('dashboard.html').write_text(
    '<!DOCTYPE html><html><nav class="tabs tabs-function"></nav>'
    '<body>route-smoke</body></html>',
    encoding='utf-8',
  )

  sys.modules.pop('web.app', None)
  from web.app import create_app
  client = TestClient(create_app())

  r = client.get('/', headers={AUTH_HEADER_NAME: VALID_SECRET})
  assert r.status_code == 200, (
    f'GET / with auth expected 200; got {r.status_code}: {r.text[:200]}'
  )
  body = r.text.lower()
  assert '<!doctype html>' in body or '<html' in body, (
    f'expected HTML response body; got {r.text[:200]}'
  )
  assert r.headers['content-type'].startswith('text/html'), (
    f'expected text/html content-type; got {r.headers.get("content-type")!r}'
  )
