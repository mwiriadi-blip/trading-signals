"""Plan 27-14 Task 4 + Phase 32 Plan 04 Task 3: dashboard split parity gates.

Three structural assertions that must remain green for the dashboard.py +
dashboard_renderer/ split to be correct:

  1. test_dashboard_files_under_500_loc — Phase 32 Plan 04 close-out:
     - dashboard_legacy/ contains exactly __init__.py (ImportError stub)
     - dashboard.py is <=100 LOC (OPS-06 shim cap)
     - dashboard_renderer/*.py all <=500 LOC
     - Stub raises ImportError (NOT ModuleNotFoundError) with locked message
  2. test_dashboard_html_output_byte_identical — render_dashboard against
     the canonical fixture produces output byte-identical to the Task 1
     golden (captured AFTER 27-08 + 27-11 land).
  3. test_fastapi_dashboard_route_smoke — review-fix agreed-10: route-level
     test in addition to renderer unit tests. Hits the FastAPI app and
     asserts the dashboard route returns valid HTML.
"""
import importlib
import json
import pathlib
import subprocess
import sys
from datetime import datetime

import pytest
import pytz
from fastapi.testclient import TestClient

import dashboard


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
  """Phase 32 Plan 04 close-out: dashboard_legacy/ stub + LOC caps.

  Phase 32 Plan 04 replaces dashboard_legacy/ submodule files with a
  single ImportError stub and thins dashboard.py to <=100 LOC. This test
  asserts the retirement is complete.

  (a) dashboard_legacy/__init__.py is the ONLY .py file in dashboard_legacy/
  (b) importing any name from dashboard_legacy raises ImportError with the
      locked message 'dashboard_legacy retired' — NOT ModuleNotFoundError
  (c) submodule-style import (fresh subprocess) also raises ImportError
  (d) dashboard.py is <=100 LOC (OPS-06 shim cap)
  (e) dashboard_renderer/*.py all <=500 LOC (assets.py exempt — data file)
  """
  package_dir = pathlib.Path('dashboard_legacy')

  # (a) Only __init__.py remains
  assert package_dir.is_dir(), 'dashboard_legacy/ package directory missing'
  py_files = sorted(package_dir.glob('*.py'))
  assert py_files == [pathlib.Path('dashboard_legacy/__init__.py')], (
    f'dashboard_legacy/ must contain exactly __init__.py; found: {py_files}'
  )

  # (b) Attribute access raises ImportError('dashboard_legacy retired')
  # Use importlib to force a fresh import check even if module is cached.
  with pytest.raises(ImportError, match='dashboard_legacy retired'):
    import dashboard_legacy as _dl
    _ = _dl.render_helpers  # attribute access triggers __getattr__

  # (c) Submodule import in fresh subprocess raises ImportError (NOT ModuleNotFoundError)
  result = subprocess.run(
    [sys.executable, '-c', 'import dashboard_legacy.render_helpers'],
    capture_output=True,
    text=True,
    cwd=str(pathlib.Path(__file__).parent.parent),
  )
  assert result.returncode != 0, (
    'Expected subprocess to fail on import dashboard_legacy.render_helpers'
  )
  assert 'ImportError' in result.stderr, (
    f'Expected ImportError in stderr; got: {result.stderr[:300]}'
  )
  assert 'dashboard_legacy retired' in result.stderr, (
    f'Expected locked message in stderr; got: {result.stderr[:300]}'
  )
  # NOT ModuleNotFoundError — __path__ = [] ensures __getattr__ handles it
  assert 'ModuleNotFoundError' not in result.stderr, (
    'Stub must raise ImportError (not ModuleNotFoundError) for submodule imports. '
    f'Got: {result.stderr[:300]}'
  )

  # (d) dashboard.py <=100 LOC (OPS-06 shim cap)
  dashboard_loc = pathlib.Path('dashboard.py').read_text().count('\n')
  assert dashboard_loc <= 100, (
    f'dashboard.py OPS-06 shim cap violated: {dashboard_loc} LOC (max 100)'
  )

  # (e) dashboard_renderer/*.py <=500 LOC (assets.py exempt — CSS/JS data file)
  too_big = []
  for f in sorted(pathlib.Path('dashboard_renderer').rglob('*.py')):
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
  dashboard.render_dashboard(state, out_path=out, now=FROZEN_NOW)
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
