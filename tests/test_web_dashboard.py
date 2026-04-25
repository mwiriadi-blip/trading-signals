'''Phase 13 WEB-05 + D-07..D-11 — GET / dashboard contract tests.

Reference: 13-CONTEXT.md D-07..D-11, 13-VALIDATION.md test-class
enumeration (lines 787-792), 13-UI-SPEC.md §GET / byte-level contract,
13-REVIEWS.md §Codex MEDIUM #3 (SC-2 bytes-equality lock on stale path).

Fixture strategy:
  - tmp_path provides real on-disk dashboard.html and state.json (no mocks
    of os.stat — Starlette's FileResponse hits multiple stat paths).
  - os.utime(path, ns=(atime_ns, mtime_ns)) sets controlled mtimes for
    staleness scenarios.
  - monkeypatch.chdir(tmp_path) makes the handler's relative paths
    ('dashboard.html', 'state.json') resolve to tmp_path. This avoids
    polluting the repo root during tests.
  - WEB_AUTH_SECRET is set by the autouse fixture in tests/conftest.py.
'''
import logging
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Local mirrors of tests/conftest.py constants (single source of truth lives in
# conftest.py; mirrored here because pytest's conftest auto-discovery does not
# expose conftest as an importable module without tests/__init__.py).
# Mirror pattern matches tests/test_web_app_factory.py:21-22.
VALID_SECRET = 'a' * 32  # D-17 minimum length
AUTH_HEADER_NAME = 'X-Trading-Signals-Auth'  # AUTH-01 header


@pytest.fixture
def auth_headers():
  '''Phase 13 AUTH-01: header dict for authorized TestClient requests.

  Note: tests/conftest.py also provides this fixture; defining it locally
  shadows the conftest version with identical behaviour and keeps this
  file self-documenting.
  '''
  return {AUTH_HEADER_NAME: VALID_SECRET}


@pytest.fixture
def client_with_dashboard(monkeypatch, tmp_path):
  '''TestClient bound to a temporary working directory.

  Yields (client, tmp_path, render_calls). render_calls is a list that
  appends one entry every time dashboard.render_dashboard is invoked —
  letting tests assert exact regen counts.

  The tracked render_dashboard WRITES a deterministic body to dashboard.html
  so bytes-equality tests (REVIEWS MEDIUM #3) can verify the served
  response matches the regenerated content.
  '''
  monkeypatch.chdir(tmp_path)

  # Stub state_manager.load_state to a benign payload (no real disk read).
  import state_manager
  monkeypatch.setattr(
    state_manager, 'load_state',
    lambda *_a, **_kw: {'schema_version': 1, 'last_run': '2026-04-25'},
  )

  # Track render_dashboard invocations.
  render_calls = []
  import dashboard

  def _track_render(state, *args, **kwargs):
    render_calls.append(state)
    # Touch dashboard.html so subsequent _is_stale() returns False.
    Path('dashboard.html').write_text('<html>regenerated</html>', encoding='utf-8')

  monkeypatch.setattr(dashboard, 'render_dashboard', _track_render)

  import sys
  sys.modules.pop('web.app', None)
  from web.app import create_app
  client = TestClient(create_app())
  return client, tmp_path, render_calls


def _make_html(path: Path, content: str = '<html>cached</html>') -> None:
  '''Write a dashboard.html with given content; mtime is "now".'''
  path.write_text(content, encoding='utf-8')


def _set_mtime_ns(path: Path, mtime_ns: int) -> None:
  '''Set both atime and mtime to mtime_ns (nanoseconds since epoch).'''
  os.utime(path, ns=(mtime_ns, mtime_ns))


class TestDashboardResponse:
  '''D-07: GET / serves dashboard.html via FileResponse with correct headers.'''

  def test_returns_200_with_auth_when_dashboard_exists(self, client_with_dashboard, auth_headers):
    '''D-07: GET / with valid auth + dashboard.html present → 200.'''
    client, tmp, _ = client_with_dashboard
    _make_html(tmp / 'dashboard.html')
    r = client.get('/', headers=auth_headers)
    assert r.status_code == 200, (
      f'Expected 200 with auth + dashboard.html present, got {r.status_code}: '
      f'{r.text[:200]}'
    )

  def test_content_type_is_html(self, client_with_dashboard, auth_headers):
    '''D-07: Content-Type is text/html; charset=utf-8.'''
    client, tmp, _ = client_with_dashboard
    _make_html(tmp / 'dashboard.html')
    r = client.get('/', headers=auth_headers)
    assert r.headers['content-type'] == 'text/html; charset=utf-8', (
      f'Expected Content-Type "text/html; charset=utf-8", '
      f'got {r.headers.get("content-type")!r}'
    )

  def test_body_matches_dashboard_html_contents(self, client_with_dashboard, auth_headers):
    '''D-07: served body byte-equals dashboard.html on disk.'''
    client, tmp, _ = client_with_dashboard
    _make_html(tmp / 'dashboard.html', '<html><body>operator dashboard</body></html>')
    r = client.get('/', headers=auth_headers)
    assert r.text == '<html><body>operator dashboard</body></html>'

  def test_unauthenticated_returns_401(self, client_with_dashboard):
    '''AUTH-01 inheritance: GET / without auth → 401, not the dashboard.'''
    client, tmp, _ = client_with_dashboard
    _make_html(tmp / 'dashboard.html')
    r = client.get('/')  # no auth headers
    assert r.status_code == 401, (
      f'Expected 401 without auth, got {r.status_code}: {r.text[:120]}'
    )


class TestStaleness:
  '''D-08: state.json mtime > dashboard.html mtime triggers regen.

  SC-2 (REVIEWS MEDIUM #3): on the stale path, BOTH conditions are locked:
    1. render_dashboard is called exactly once
    2. the served response bytes EQUAL the regenerated file bytes
       (catches the subtle bug where the handler regens but serves
        the pre-regen snapshot).
  '''

  def test_fresh_dashboard_is_not_regenerated(self, client_with_dashboard, auth_headers):
    '''D-08: html mtime >= state mtime → render_dashboard NOT called.'''
    client, tmp, calls = client_with_dashboard
    state_path = tmp / 'state.json'
    html_path = tmp / 'dashboard.html'

    state_path.write_text('{}', encoding='utf-8')
    html_path.write_text('<html>fresh</html>', encoding='utf-8')

    # Set state mtime to T, dashboard mtime to T + 100ms (html is fresher).
    base_ns = 1_700_000_000_000_000_000  # arbitrary fixed nanosecond timestamp
    _set_mtime_ns(state_path, base_ns)
    _set_mtime_ns(html_path, base_ns + 100_000_000)  # +100ms

    r = client.get('/', headers=auth_headers)
    assert r.status_code == 200
    assert calls == [], (
      f'Fresh dashboard should NOT trigger regen (D-08 strict-greater-than), '
      f'but render_dashboard was called {len(calls)} time(s)'
    )

  def test_stale_state_triggers_regen_and_serves_regenerated_bytes(self, client_with_dashboard, auth_headers):
    '''SC-2 lock (REVIEWS MEDIUM #3): on the stale path, regen is called AND
    the served body equals the regenerated file bytes.

    The `client_with_dashboard` fixture replaces render_dashboard with
    `_track_render` which writes `<html>regenerated</html>` to
    dashboard.html. This test seeds dashboard.html with `<html>stale</html>`
    (different bytes), marks state.json as newer, issues GET /, and asserts:
      1. response body == '<html>regenerated</html>'  (NOT '<html>stale</html>')
      2. render_dashboard was called exactly once

    If the handler regenerates but then serves the pre-regen buffer, (1)
    fires red. If the handler skips regen entirely, (2) fires red. Prior
    version of this test only checked (2) — REVIEWS MEDIUM #3 added (1).
    '''
    client, tmp, calls = client_with_dashboard
    state_path = tmp / 'state.json'
    html_path = tmp / 'dashboard.html'

    html_path.write_text('<html>stale</html>', encoding='utf-8')
    state_path.write_text('{}', encoding='utf-8')

    # Use real wall-clock times with os.utime so any mtime_ns semantics bug
    # in the handler still trips the staleness check. state.json is 60s
    # AHEAD of dashboard.html, unambiguously stale.
    now = time.time()
    os.utime(state_path, (now, now))
    os.utime(html_path, (now - 60, now - 60))

    r = client.get('/', headers=auth_headers)
    assert r.status_code == 200, (
      f'Stale path should return 200 after regen, got {r.status_code}: {r.text[:200]}'
    )
    # SC-2 lock: served body must be the REGENERATED bytes, not the stale.
    assert r.text == '<html>regenerated</html>', (
      f'Served stale bytes after regen — body={r.text[:50]!r}. '
      f'Expected "<html>regenerated</html>" (from _track_render writer). '
      f'If body == "<html>stale</html>", handler skipped regen or served '
      f'pre-regen snapshot (REVIEWS MEDIUM #3 regression).'
    )
    assert len(calls) == 1, (
      f'render_dashboard called {len(calls)}x, expected 1. '
      f'If 0: staleness check is broken. If >1: regen loop or retry bug.'
    )

  def test_equal_mtime_does_not_trigger_regen(self, client_with_dashboard, auth_headers):
    '''D-08: strict greater-than — equal mtimes do NOT regen.'''
    client, tmp, calls = client_with_dashboard
    state_path = tmp / 'state.json'
    html_path = tmp / 'dashboard.html'

    html_path.write_text('<html>tied</html>', encoding='utf-8')
    state_path.write_text('{}', encoding='utf-8')

    same_ns = 1_700_000_000_000_000_000
    _set_mtime_ns(state_path, same_ns)
    _set_mtime_ns(html_path, same_ns)

    r = client.get('/', headers=auth_headers)
    assert r.status_code == 200
    assert calls == [], (
      f'Equal mtimes should NOT regen (D-08 uses > not >=), '
      f'but render_dashboard was called {len(calls)} time(s)'
    )

  def test_state_missing_does_not_regen(self, client_with_dashboard, auth_headers):
    '''D-08 / _is_stale: state.json missing → False → no regen attempt.'''
    client, tmp, calls = client_with_dashboard
    (tmp / 'dashboard.html').write_text('<html>existing</html>', encoding='utf-8')
    # state.json deliberately NOT created.

    r = client.get('/', headers=auth_headers)
    assert r.status_code == 200
    assert calls == [], (
      f'Missing state.json should NOT trigger regen, '
      f'but render_dashboard was called {len(calls)} time(s)'
    )


class TestRenderFailure:
  '''D-10: render_dashboard exception → log WARN + serve stale (200).'''

  def test_render_exception_logs_warn_and_serves_stale(self, monkeypatch, tmp_path, caplog, auth_headers):
    '''D-10: when render_dashboard raises, handler logs WARN and serves the stale on-disk copy.'''
    monkeypatch.chdir(tmp_path)

    # Existing stale dashboard.html — should be served despite render failure.
    (tmp_path / 'dashboard.html').write_text('<html>stale-but-served</html>', encoding='utf-8')
    (tmp_path / 'state.json').write_text('{}', encoding='utf-8')

    base_ns = 1_700_000_000_000_000_000
    _set_mtime_ns(tmp_path / 'dashboard.html', base_ns)
    _set_mtime_ns(tmp_path / 'state.json', base_ns + 100_000_000)  # stale

    import state_manager
    monkeypatch.setattr(
      state_manager, 'load_state',
      lambda *_a, **_kw: {'schema_version': 1},
    )

    import dashboard

    def _exploding_render(state, *args, **kwargs):
      raise RuntimeError('simulated render failure')

    monkeypatch.setattr(dashboard, 'render_dashboard', _exploding_render)

    import sys
    sys.modules.pop('web.app', None)
    from web.app import create_app
    client = TestClient(create_app())

    with caplog.at_level(logging.WARNING, logger='web.routes.dashboard'):
      r = client.get('/', headers=auth_headers)

    # 200 — stale on-disk copy was served despite the exception.
    assert r.status_code == 200, (
      f'D-10: render failure must NOT crash; expected 200 (serve stale), '
      f'got {r.status_code}: {r.text[:200]}'
    )
    assert r.text == '<html>stale-but-served</html>', (
      f'D-10: stale copy must be served unmodified; got body {r.text[:200]!r}'
    )

    # WARN log line must contain [Web] prefix + regen-failed message + ExcType.
    warns = [rec for rec in caplog.records
             if rec.levelname == 'WARNING' and rec.name == 'web.routes.dashboard']
    assert len(warns) >= 1, (
      f'D-10: expected at least 1 WARN line at web.routes.dashboard, got {len(warns)}'
    )
    msg = warns[0].getMessage()
    assert '[Web]' in msg and 'regen failed' in msg and 'RuntimeError' in msg, (
      f'D-10 log shape mismatch: expected "[Web] dashboard regen failed: ..." '
      f'with ExcType "RuntimeError", got {msg!r}'
    )


class TestFirstRun:
  '''D-10: dashboard.html absent → 503 plain-text "dashboard not ready".'''

  def test_missing_dashboard_returns_503(self, client_with_dashboard, auth_headers):
    '''D-10: no dashboard.html → 503.'''
    client, tmp, _ = client_with_dashboard
    # Deliberately do NOT create dashboard.html. Also no state.json so
    # _is_stale's first FileNotFoundError branch is exercised, returning
    # True; render is attempted but our stubbed render_dashboard writes
    # dashboard.html — so we also disable that for this test.
    import dashboard
    # Override the tracked render to NOT create dashboard.html (simulate
    # render itself failing to write — e.g., disk full mid-write).
    def _no_write_render(*_a, **_kw):
      pass  # silently does nothing — dashboard.html still missing
    monkeypatch_dashboard = pytest.MonkeyPatch()
    try:
      monkeypatch_dashboard.setattr(dashboard, 'render_dashboard', _no_write_render)
      r = client.get('/', headers=auth_headers)
    finally:
      monkeypatch_dashboard.undo()

    assert r.status_code == 503, (
      f'D-10: missing dashboard.html → 503, got {r.status_code}: {r.text[:200]}'
    )

  def test_503_body_is_dashboard_not_ready(self, client_with_dashboard, auth_headers):
    '''D-10: 503 body is the literal string "dashboard not ready".'''
    client, tmp, _ = client_with_dashboard
    import dashboard
    monkeypatch_dashboard = pytest.MonkeyPatch()
    try:
      monkeypatch_dashboard.setattr(dashboard, 'render_dashboard', lambda *_a, **_kw: None)
      r = client.get('/', headers=auth_headers)
    finally:
      monkeypatch_dashboard.undo()

    assert r.status_code == 503
    assert r.text == 'dashboard not ready', (
      f'Expected body literal "dashboard not ready", got {r.text!r}'
    )

  def test_503_content_type_is_text_plain(self, client_with_dashboard, auth_headers):
    '''D-10: 503 Content-Type is "text/plain; charset=utf-8".'''
    client, tmp, _ = client_with_dashboard
    import dashboard
    monkeypatch_dashboard = pytest.MonkeyPatch()
    try:
      monkeypatch_dashboard.setattr(dashboard, 'render_dashboard', lambda *_a, **_kw: None)
      r = client.get('/', headers=auth_headers)
    finally:
      monkeypatch_dashboard.undo()

    assert r.status_code == 503
    assert r.headers.get('content-type') == 'text/plain; charset=utf-8', (
      f'Expected Content-Type "text/plain; charset=utf-8", '
      f'got {r.headers.get("content-type")!r}'
    )
