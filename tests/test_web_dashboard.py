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
from datetime import UTC
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _request_with_cookies(client, method, url, **kwargs):
  cookies = kwargs.pop('cookies', None)
  if cookies:
    headers = dict(kwargs.pop('headers', {}) or {})
    cookie_parts = [f'{name}={value}' for name, value in cookies.items()]
    existing_cookie = headers.get('cookie') or headers.get('Cookie')
    if existing_cookie:
      cookie_parts.insert(0, existing_cookie)
    headers['cookie'] = '; '.join(cookie_parts)
    kwargs['headers'] = headers
  return client.request(method, url, **kwargs)

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

  def test_dashboard_html_alias_serves_signals_page(self, client_with_dashboard, auth_headers):
    '''Legacy /dashboard.html alias should continue to serve signals page.'''
    client, tmp, _ = client_with_dashboard
    (tmp / 'dashboard-signals.html').write_text('<html><body>signals-page</body></html>', encoding='utf-8')
    (tmp / 'dashboard.html').write_text('<html><nav class="tabs">fresh</nav></html>', encoding='utf-8')
    (tmp / 'state.json').write_text('{}', encoding='utf-8')
    base_ns = 1_700_000_000_000_000_000
    _set_mtime_ns(tmp / 'state.json', base_ns)
    _set_mtime_ns(tmp / 'dashboard.html', base_ns + 100_000_000)
    _set_mtime_ns(tmp / 'dashboard-signals.html', base_ns + 100_000_000)
    r = client.get('/dashboard.html', headers=auth_headers)
    assert r.status_code == 200
    assert 'signals-page' in r.text


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
    html_path.write_text('<html><nav class="tabs">fresh</nav></html>', encoding='utf-8')

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

  def test_missing_tab_marker_triggers_regen(self, client_with_dashboard, auth_headers):
    '''Code-only dashboard upgrades must not serve a stale pre-tabs cache.'''
    client, tmp, calls = client_with_dashboard
    state_path = tmp / 'state.json'
    html_path = tmp / 'dashboard.html'

    state_path.write_text('{}', encoding='utf-8')
    html_path.write_text('<html><h2>Signal Status</h2></html>', encoding='utf-8')

    now = time.time()
    os.utime(state_path, (now - 60, now - 60))
    os.utime(html_path, (now, now))

    r = client.get('/', headers=auth_headers)
    assert r.status_code == 200
    assert r.text == '<html>regenerated</html>'
    assert len(calls) == 1

  def test_equal_mtime_does_not_trigger_regen(self, client_with_dashboard, auth_headers):
    '''D-08: strict greater-than — equal mtimes do NOT regen.'''
    client, tmp, calls = client_with_dashboard
    state_path = tmp / 'state.json'
    html_path = tmp / 'dashboard.html'

    html_path.write_text('<html><nav class="tabs">tied</nav></html>', encoding='utf-8')
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


class TestAuthSecretPlaceholderSubstitution:
  '''REVIEWS HIGH #4: dashboard.html on disk emits literal placeholder;
  the GET / handler substitutes at request time so the on-disk artifact
  never carries the real WEB_AUTH_SECRET value.

  Threat T-14-15 (auth-secret leak via on-disk dashboard.html cache) is
  MITIGATED by this discipline. These tests lock the contract: disk file
  contains the placeholder (or no secret); response body contains the
  real secret; placeholder string never leaks into the response.
  '''

  def test_dashboard_html_disk_does_not_contain_real_secret(self):
    '''Disk file MUST NOT contain the real secret.

    Plan 14-05 emits the literal {{WEB_AUTH_SECRET}} placeholder. Until
    Plan 14-05 lands, the on-disk dashboard.html may not include the
    placeholder yet — so we ONLY assert "real secret absent". Once
    Plan 14-05 lands, additionally assert placeholder presence.
    '''
    disk_html = Path('dashboard.html').read_text() if Path('dashboard.html').exists() else ''
    if not disk_html:
      pytest.skip('dashboard.html not present in repo (rendered by daily run)')
    secret = 'a' * 32  # the test secret value from conftest
    assert secret not in disk_html, (
      'REVIEWS HIGH #4: real WEB_AUTH_SECRET must NOT leak into disk file'
    )

  def test_get_root_response_substitutes_placeholder(
    self, client_with_dashboard, auth_headers,
  ):
    '''The TestClient response body MUST contain the real secret in
    hx-headers when the on-disk dashboard.html contains the placeholder.

    Synthesizes a dashboard.html with the placeholder so the test is
    independent of Plan 14-05's emission timing.
    '''
    client, tmp, _ = client_with_dashboard
    (tmp / 'dashboard.html').write_text(
      '<html><body data-auth="{{WEB_AUTH_SECRET}}">test</body></html>',
      encoding='utf-8',
    )
    r = client.get('/', headers=auth_headers)
    assert r.status_code == 200
    assert 'a' * 32 in r.text, (
      'REVIEWS HIGH #4: real WEB_AUTH_SECRET must be substituted into response'
    )

  def test_get_root_response_does_not_leak_placeholder(
    self, client_with_dashboard, auth_headers,
  ):
    '''The literal {{WEB_AUTH_SECRET}} string MUST NOT appear in the
    response body when the placeholder is present on disk and a real
    secret is set in the env (the autouse conftest fixture sets it).'''
    client, tmp, _ = client_with_dashboard
    (tmp / 'dashboard.html').write_text(
      '<html><body data-auth="{{WEB_AUTH_SECRET}}">test</body></html>',
      encoding='utf-8',
    )
    r = client.get('/', headers=auth_headers)
    assert r.status_code == 200
    assert '{{WEB_AUTH_SECRET}}' not in r.text, (
      'REVIEWS HIGH #4: placeholder must be substituted, not leaked'
    )

  def test_get_root_with_fragment_returns_tbody_inner(
    self, client_with_dashboard, auth_headers,
  ):
    '''?fragment=position-group-SPI200 returns ONLY that tbody's inner HTML
    (used by Plan 14-05's per-tbody listener for HX-Trigger refresh).'''
    client, tmp, _ = client_with_dashboard
    (tmp / 'dashboard.html').write_text(
      '<html><body><table>'
      '<tbody id="position-group-SPI200"><tr><td>SPI</td></tr></tbody>'
      '<tbody id="position-group-AUDUSD"><tr><td>AUD</td></tr></tbody>'
      '</table></body></html>',
      encoding='utf-8',
    )
    r = client.get('/?fragment=position-group-SPI200', headers=auth_headers)
    assert r.status_code == 200
    body = r.text
    # Body must NOT contain a full <html>; it's a tbody inner partial
    assert '<html' not in body.lower()
    assert 'SPI' in body
    assert 'AUD' not in body  # only the requested fragment

  def test_get_root_with_unknown_fragment_returns_404(
    self, client_with_dashboard, auth_headers,
  ):
    '''Unknown fragment id returns 404 (not 200 with empty body).'''
    client, tmp, _ = client_with_dashboard
    (tmp / 'dashboard.html').write_text(
      '<html><body><p>no tbody here</p></body></html>',
      encoding='utf-8',
    )
    r = client.get('/?fragment=position-group-NONEXISTENT', headers=auth_headers)
    assert r.status_code == 404


class TestForwardStopFragment:
  '''Phase 15 CALC-03 + D-05/D-06/D-07: forward-look fragment GET handler.
  Wave 0 skeleton — bodies populated in Plan 06.

  Fixture note: client_with_state_v3 returns (client, set_state, captured_saves).
  Default state has SPI200 LONG (entry=7800, peak=7850, atr_entry=50), AUDUSD=None.
  AUDUSD SHORT tests inject a position via set_state before the request.
  '''

  def test_long_z_above_peak_updates_w(self, client_with_state_v3, htmx_headers) -> None:
    '''LONG Z=7900 > peak=7850 -> synth peak=7900 -> W = 7900 - 3*50 = 7750.'''
    from dashboard import _fmt_currency
    from sizing_engine import get_trailing_stop
    client, set_state, _ = client_with_state_v3
    resp = client.get('/?fragment=forward-stop&instrument=SPI200&z=7900', headers=htmx_headers)
    assert resp.status_code == 200
    synth = {'direction': 'LONG', 'entry_price': 7800.0, 'atr_entry': 50.0,
             'peak_price': 7900.0, 'manual_stop': None}
    expected_w = get_trailing_stop(synth, 0.0, 0.0)
    assert _fmt_currency(expected_w) in resp.text, (
      f'Expected {_fmt_currency(expected_w)} in {resp.text!r}'
    )

  def test_long_z_below_peak_w_unchanged(self, client_with_state_v3, htmx_headers) -> None:
    '''LONG Z=7820 < peak=7850 -> synth peak stays 7850 -> W = 7850 - 3*50 = 7700.'''
    from dashboard import _fmt_currency
    from sizing_engine import get_trailing_stop
    client, set_state, _ = client_with_state_v3
    resp = client.get('/?fragment=forward-stop&instrument=SPI200&z=7820', headers=htmx_headers)
    assert resp.status_code == 200
    synth = {'direction': 'LONG', 'entry_price': 7800.0, 'atr_entry': 50.0,
             'peak_price': 7850.0, 'manual_stop': None}
    expected_w = get_trailing_stop(synth, 0.0, 0.0)
    assert _fmt_currency(expected_w) in resp.text

  def test_short_z_below_trough_updates_w(self, client_with_state_v3, htmx_headers) -> None:
    '''SHORT Z=0.640 below trough=0.645 -> synth trough=0.640 -> W updated.'''
    import state_manager as sm
    from dashboard import _fmt_currency
    from sizing_engine import get_trailing_stop
    client, set_state, _ = client_with_state_v3
    # Inject AUDUSD SHORT position into state
    state = sm.load_state()
    state = dict(state)
    state['positions'] = dict(state.get('positions', {}))
    state['positions']['AUDUSD'] = {
      'direction': 'SHORT', 'entry_price': 0.65, 'entry_date': '2026-04-20',
      'n_contracts': 1, 'pyramid_level': 0,
      'peak_price': None, 'trough_price': 0.645, 'atr_entry': 0.005,
      'manual_stop': None,
    }
    set_state(state)
    resp = client.get('/?fragment=forward-stop&instrument=AUDUSD&z=0.640', headers=htmx_headers)
    assert resp.status_code == 200
    synth = {'direction': 'SHORT', 'entry_price': 0.65, 'atr_entry': 0.005,
             'trough_price': 0.640, 'manual_stop': None}
    expected_w = get_trailing_stop(synth, 0.0, 0.0)
    assert _fmt_currency(expected_w) in resp.text

  def test_short_z_above_trough_w_unchanged(self, client_with_state_v3, htmx_headers) -> None:
    '''SHORT Z=0.660 > trough=0.645 -> synth trough stays 0.645 -> W = trough + 3*atr.'''
    from dashboard import _fmt_currency
    from sizing_engine import get_trailing_stop
    client, set_state, _ = client_with_state_v3
    # Inject AUDUSD SHORT position into state
    import state_manager as sm
    state = sm.load_state()
    state = dict(state)
    state['positions'] = dict(state.get('positions', {}))
    state['positions']['AUDUSD'] = {
      'direction': 'SHORT', 'entry_price': 0.65, 'entry_date': '2026-04-20',
      'n_contracts': 1, 'pyramid_level': 0,
      'peak_price': None, 'trough_price': 0.645, 'atr_entry': 0.005,
      'manual_stop': None,
    }
    set_state(state)
    resp = client.get('/?fragment=forward-stop&instrument=AUDUSD&z=0.660', headers=htmx_headers)
    assert resp.status_code == 200
    synth = {'direction': 'SHORT', 'entry_price': 0.65, 'atr_entry': 0.005,
             'trough_price': 0.645, 'manual_stop': None}
    expected_w = get_trailing_stop(synth, 0.0, 0.0)
    assert _fmt_currency(expected_w) in resp.text

  def test_manual_stop_overrides_z_input(self, client_with_state_v3, htmx_headers) -> None:
    '''D-09 precedence: when manual_stop=7700 is set, W == 7700 regardless of Z=9999.

    Fixture choice: inject manual_stop via set_state inside the test (no new
    conftest fixture needed — set_state mutates the live state_box).
    '''
    from dashboard import _fmt_currency
    client, set_state, _ = client_with_state_v3
    # Inject manual_stop onto the SPI200 LONG position
    import state_manager as sm
    state = sm.load_state()
    state = dict(state)
    state['positions'] = dict(state.get('positions', {}))
    spi_pos = dict(state['positions']['SPI200'])
    spi_pos['manual_stop'] = 7700.0
    state['positions']['SPI200'] = spi_pos
    set_state(state)
    resp = client.get('/?fragment=forward-stop&instrument=SPI200&z=9999', headers=htmx_headers)
    assert resp.status_code == 200
    # manual_stop is honored by get_trailing_stop; W == manual_stop == 7700
    assert _fmt_currency(7700.0) in resp.text, (
      f'Expected {_fmt_currency(7700.0)!r} in body {resp.text!r}'
    )

  def test_forward_stop_matches_sizing_engine_bit_for_bit(
    self, client_with_state_v3, htmx_headers,
  ) -> None:
    '''D-07 bit-identical parity: 4 LONG/SHORT × peak/trough cases.

    The manual_stop case (case 5) is covered by test_manual_stop_overrides_z_input.
    '''
    from dashboard import _fmt_currency
    from sizing_engine import get_trailing_stop
    client, set_state, _ = client_with_state_v3

    # Inject AUDUSD SHORT position so the SHORT cases work
    import state_manager as sm
    state = sm.load_state()
    state = dict(state)
    state['positions'] = dict(state.get('positions', {}))
    state['positions']['AUDUSD'] = {
      'direction': 'SHORT', 'entry_price': 0.65, 'entry_date': '2026-04-20',
      'n_contracts': 1, 'pyramid_level': 0,
      'peak_price': None, 'trough_price': 0.645, 'atr_entry': 0.005,
      'manual_stop': None,
    }
    set_state(state)

    cases = [
      ('SPI200', '7900',
       {'direction': 'LONG', 'entry_price': 7800.0, 'atr_entry': 50.0,
        'peak_price': 7900.0, 'manual_stop': None}),
      ('SPI200', '7820',
       {'direction': 'LONG', 'entry_price': 7800.0, 'atr_entry': 50.0,
        'peak_price': 7850.0, 'manual_stop': None}),
      ('AUDUSD', '0.640',
       {'direction': 'SHORT', 'entry_price': 0.65, 'atr_entry': 0.005,
        'trough_price': 0.640, 'manual_stop': None}),
      ('AUDUSD', '0.660',
       {'direction': 'SHORT', 'entry_price': 0.65, 'atr_entry': 0.005,
        'trough_price': 0.645, 'manual_stop': None}),
    ]
    for instrument, z, synth in cases:
      resp = client.get(
        f'/?fragment=forward-stop&instrument={instrument}&z={z}',
        headers=htmx_headers,
      )
      assert resp.status_code == 200
      expected_w = get_trailing_stop(synth, 0.0, 0.0)
      assert _fmt_currency(expected_w) in resp.text, (
        f'Bit-parity failure for instrument={instrument} z={z}: '
        f'expected {_fmt_currency(expected_w)!r}; got {resp.text!r}'
      )

  def test_degenerate_z_returns_em_dash(self, client_with_state_v3, htmx_headers) -> None:
    '''Degenerate Z (empty, negative, zero, non-numeric, nan) returns em-dash, never 4xx.'''
    client, set_state, _ = client_with_state_v3
    for bad_z in ['', '-1', '0', 'abc', 'nan']:
      resp = client.get(
        f'/?fragment=forward-stop&instrument=SPI200&z={bad_z}',
        headers=htmx_headers,
      )
      assert resp.status_code == 200, f'degenerate Z={bad_z!r} should not 4xx'
      assert '—' in resp.text, (
        f'expected em-dash body for Z={bad_z!r}; got {resp.text!r}'
      )

  def test_missing_position_returns_em_dash(self, client_with_state_v3, htmx_headers) -> None:
    '''Instrument with no position in state returns em-dash, not 4xx.'''
    client, set_state, _ = client_with_state_v3
    resp = client.get(
      '/?fragment=forward-stop&instrument=NOTREAL&z=100',
      headers=htmx_headers,
    )
    assert resp.status_code == 200
    assert '—' in resp.text

  def test_response_span_id_matches_instrument(
    self, client_with_state_v3, htmx_headers,
  ) -> None:
    '''Response body contains the correct span id="forward-stop-SPI200-w".'''
    client, set_state, _ = client_with_state_v3
    resp = client.get(
      '/?fragment=forward-stop&instrument=SPI200&z=7900',
      headers=htmx_headers,
    )
    assert resp.status_code == 200
    assert 'id="forward-stop-SPI200-w"' in resp.text

  def test_forward_stop_fragment_requires_auth_header(
    self, client_with_state_v3,
  ) -> None:
    '''REVIEWS L-2: the forward-stop fragment route must inherit the
    AuthMiddleware gate (Phase 13 D-01). A request WITHOUT the
    X-Trading-Signals-Auth header returns 401. This is the regression
    lock against a future refactor that accidentally bypasses the middleware.
    '''
    client, set_state, _ = client_with_state_v3
    # No auth header — explicit empty dict so the auth header is absent
    resp = client.get(
      '/?fragment=forward-stop&instrument=SPI200&z=7900',
      headers={},
    )
    assert resp.status_code == 401, (
      f'REVIEWS L-2: forward-stop fragment must require auth header. '
      f'Got status={resp.status_code} body={resp.text!r}'
    )


class TestSideBySideStopDisplay:
  '''Phase 15 D-10: side-by-side manual:|computed: stop cell.
  Wave 0 skeleton — bodies populated in Plan 05/06.

  These tests render dashboard.py directly (no HTTP layer) and test the markup
  for the side-by-side stop cell shipped in Plan 05.
  '''

  def test_manual_stop_side_by_side(self) -> None:
    '''When manual_stop is set, the cell shows class="trail-stop-split" with
    both manual and computed values, plus the (will close) annotation.
    '''
    from dashboard import _render_single_position_row
    pos = {
      'direction': 'LONG',
      'entry_price': 7800.0,
      'atr_entry': 50.0,
      'peak_price': 7950.0,
      'current_level': 0,
      'manual_stop': 7700.0,
      'n_contracts': 2,
      'pyramid_level': 0,
      'trough_price': None,
    }
    state = {'positions': {'SPI200': pos}, 'signals': {}, 'account': 100000.0}
    html_out = _render_single_position_row(state, 'SPI200', pos)
    assert 'class="trail-stop-split"' in html_out, (
      f'Expected trail-stop-split class; got: {html_out[:500]}'
    )
    assert 'manual:' in html_out, 'Expected "manual:" label in output'
    assert 'computed:' in html_out, 'Expected "computed:" label in output'
    assert '<em>(will close)</em>' in html_out, 'Expected (will close) annotation'

  def test_no_manual_stop_single_cell(self) -> None:
    '''When manual_stop is None, the cell uses Phase 14 baseline (no split class).'''
    from dashboard import _render_single_position_row
    pos = {
      'direction': 'LONG',
      'entry_price': 7800.0,
      'atr_entry': 50.0,
      'peak_price': 7950.0,
      'current_level': 0,
      'manual_stop': None,
      'n_contracts': 2,
      'pyramid_level': 0,
      'trough_price': None,
    }
    state = {'positions': {'SPI200': pos}, 'signals': {}, 'account': 100000.0}
    html_out = _render_single_position_row(state, 'SPI200', pos)
    # Phase 14 baseline: single-cell rendering, no trail-stop-split class
    assert 'class="trail-stop-split"' not in html_out, (
      'Expected NO trail-stop-split when manual_stop is None'
    )

  def test_will_close_annotation_in_em(self) -> None:
    '''The (will close) annotation must be wrapped in <em> per UI-SPEC accessibility.'''
    from dashboard import _render_single_position_row
    pos = {
      'direction': 'LONG',
      'entry_price': 7800.0,
      'atr_entry': 50.0,
      'peak_price': 7950.0,
      'current_level': 0,
      'manual_stop': 7700.0,
      'n_contracts': 2,
      'pyramid_level': 0,
      'trough_price': None,
    }
    state = {'positions': {'SPI200': pos}, 'signals': {}, 'account': 100000.0}
    html_out = _render_single_position_row(state, 'SPI200', pos)
    assert '<em>(will close)</em>' in html_out, (
      'The (will close) annotation MUST be wrapped in <em> per UI-SPEC accessibility'
    )


class TestTradesDriftLifecycle:
  '''Phase 15 D-02 + REVIEWS H-4: web mutation handlers (open/close/modify)
  correctly recompute drift warnings via the _apply mutator drift block.

  Three integration tests cover the lifecycle:
    - open creates fresh drift warning when post-open state mismatches signals
    - close clears stale drift while preserving non-drift warnings (corruption etc.)
    - modify recomputes drift without nuking non-drift warnings

  Wave 0 skeleton — bodies populated in Plan 06 Task 3.
  '''

  def test_open_trade_creates_drift_when_signal_mismatch(
    self, client_with_state_v3, htmx_headers,
  ) -> None:
    '''REVIEWS H-4: POST /trades/open into a state where AUDUSD signal is LONG
    but we open SHORT AUDUSD. The _apply drift block must detect the mismatch
    and append a fresh drift warning to state['warnings'].

    Fixture choice: AUDUSD (not SPI200) to avoid the "position already exists"
    conflict — default state has SPI200 LONG position already present.
    AUDUSD signal is injected as LONG (signal=1) with ATR available so the
    open is permitted (ATR check in fresh-open path).
    '''
    import state_manager as sm
    from signal_engine import LONG as LONG_INT
    client, set_state, _ = client_with_state_v3
    # Inject AUDUSD LONG signal with ATR so the open is permitted
    state = sm.load_state()
    state = dict(state)
    state['signals'] = dict(state.get('signals', {}))
    state['signals']['AUDUSD'] = {
      'signal': LONG_INT,
      'last_scalars': {'atr': 0.005},
      'last_close': 0.65,
    }
    # AUDUSD position must be None (no existing position)
    state['positions'] = dict(state.get('positions', {}))
    state['positions']['AUDUSD'] = None
    set_state(state)

    # Open SHORT AUDUSD while signal is LONG -> reversal drift
    body = {
      'instrument': 'AUDUSD',
      'direction': 'SHORT',
      'entry_price': 0.6500,
      'contracts': 1,
    }
    resp = client.post('/trades/open', json=body, headers=htmx_headers)
    assert resp.status_code in (200, 201, 204), (
      f'open failed unexpectedly: {resp.status_code} {resp.text!r}'
    )
    # Re-load state: load_state() is patched to return state_box['value']
    final = sm.load_state()
    drift_warnings = [w for w in final.get('warnings', []) if w.get('source') == 'drift']
    assert len(drift_warnings) >= 1, (
      f'REVIEWS H-4: open trade with signal mismatch should create drift warning. '
      f'warnings={final.get("warnings", [])}'
    )
    assert any('AUDUSD' in w.get('message', '') for w in drift_warnings), (
      f'drift warning should mention AUDUSD; warnings={drift_warnings}'
    )

  def test_close_trade_clears_drift(
    self, client_with_state_v3, htmx_headers,
  ) -> None:
    '''REVIEWS H-4: POST /trades/close on SPI200 clears drift warnings when
    no remaining drifted positions exist. Non-drift warnings (corruption) are
    preserved.

    Pre-state: SPI200 LONG + drift warning + corruption warning.
    Action: POST /trades/close on SPI200.
    Expected: zero drift warnings, corruption warning preserved.
    '''
    from datetime import datetime

    import state_manager as sm
    client, set_state, _ = client_with_state_v3
    # Inject pre-state warnings into the live state
    state = sm.load_state()
    fixed_now = datetime(2026, 4, 26, 9, 30, 0, tzinfo=UTC)
    state = sm.append_warning(
      state, 'drift',
      "You hold LONG SPI200, today's signal is FLAT — consider closing.",
      now=fixed_now,
    )
    state = sm.append_warning(
      state, 'state_manager',
      'recovered from corruption: state.json reset',
      now=fixed_now,
    )
    set_state(state)

    body = {'instrument': 'SPI200', 'exit_price': 7860.0}
    resp = client.post('/trades/close', json=body, headers=htmx_headers)
    assert resp.status_code in (200, 201, 204), (
      f'close failed unexpectedly: {resp.status_code} {resp.text!r}'
    )

    final = sm.load_state()
    warnings = final.get('warnings', [])
    drift_warnings = [w for w in warnings if w.get('source') == 'drift']
    corruption_warnings = [
      w for w in warnings
      if w.get('source') == 'state_manager'
      and w.get('message', '').startswith('recovered from corruption')
    ]
    assert len(drift_warnings) == 0, (
      f'REVIEWS H-4: close-trade should clear drift warnings. '
      f'drift_warnings={drift_warnings}'
    )
    assert len(corruption_warnings) == 1, (
      f'REVIEWS H-4: close-trade must NOT nuke non-drift warnings. '
      f'Expected 1 corruption warning; got {len(corruption_warnings)}: {corruption_warnings}'
    )

  def test_modify_trade_recomputes_drift_preserves_non_drift_warnings(
    self, client_with_state_v3, htmx_headers,
  ) -> None:
    '''REVIEWS H-4: POST /trades/modify recomputes drift. Stale drift is
    cleared. Non-drift warnings (corruption) are preserved.

    Pre-state: SPI200 LONG + stale drift warning + corruption warning.
    SPI200 signal is set to LONG (matching position) so detect_drift
    returns empty after modify -> stale drift disappears.
    Action: POST /trades/modify (new_stop=7700).
    Expected: stale drift gone, corruption preserved.
    '''
    from datetime import datetime

    import state_manager as sm
    from signal_engine import LONG as LONG_INT
    client, set_state, _ = client_with_state_v3
    # Inject SPI200 LONG signal (matches position -> no drift after recompute)
    state = sm.load_state()
    state = dict(state)
    state['signals'] = dict(state.get('signals', {}))
    state['signals']['SPI200'] = {
      'signal': LONG_INT,
      'last_scalars': {'atr': 50.0},
      'last_close': 7820.0,
    }
    # Inject stale drift warning + corruption warning
    fixed_now = datetime(2026, 4, 26, 9, 30, 0, tzinfo=UTC)
    state = sm.append_warning(
      state, 'drift',
      'STALE DRIFT: signal flipped before modify',
      now=fixed_now,
    )
    state = sm.append_warning(
      state, 'state_manager',
      'recovered from corruption: state.json reset',
      now=fixed_now,
    )
    set_state(state)

    body = {'instrument': 'SPI200', 'new_stop': 7700.0}
    resp = client.post('/trades/modify', json=body, headers=htmx_headers)
    assert resp.status_code in (200, 201, 204), (
      f'modify failed unexpectedly: {resp.status_code} {resp.text!r}'
    )

    final = sm.load_state()
    warnings = final.get('warnings', [])
    drift_warnings = [w for w in warnings if w.get('source') == 'drift']
    corruption_warnings = [
      w for w in warnings
      if w.get('source') == 'state_manager'
      and w.get('message', '').startswith('recovered from corruption')
    ]
    # Stale drift warning must be gone (clear_warnings_by_source removed it;
    # detect_drift found no mismatch because SPI200 signal == LONG == position)
    stale_present = any('STALE DRIFT' in w.get('message', '') for w in drift_warnings)
    assert not stale_present, (
      f'REVIEWS H-4: modify-trade must clear stale drift warnings. '
      f'Stale message survived: {drift_warnings}'
    )
    assert len(corruption_warnings) == 1, (
      f'REVIEWS H-4: modify-trade must NOT nuke non-drift warnings. '
      f'Expected 1 corruption warning; got {len(corruption_warnings)}: {corruption_warnings}'
    )


# =========================================================================
# Phase 16.1 Plan 01 Task 5 — Session-aware placeholder substitution
# =========================================================================


class TestSessionPlaceholderSubstitution:
  '''Phase 16.1: web/routes/dashboard.py validates tsi_session cookie at
  request time and substitutes {{SIGNOUT_BUTTON}} / {{SESSION_NOTE}}
  placeholders accordingly. Mirrors Phase 14 {{WEB_AUTH_SECRET}} pattern.
  '''

  def test_get_dashboard_substitutes_signout_button_when_cookie_valid(
    self, client_with_dashboard, valid_cookie_token,
  ):
    client, tmp, _ = client_with_dashboard
    (tmp / 'dashboard.html').write_text(
      '<html><body>'
      '<header><p class="meta">'
      '{{SIGNOUT_BUTTON}}{{SESSION_NOTE}}'
      '</p></header>'
      '</body></html>',
      encoding='utf-8',
    )
    r = _request_with_cookies(client, 'GET', '/', cookies={'tsi_session': valid_cookie_token})
    assert r.status_code == 200
    body = r.text
    assert 'class="signout-form"' in body
    assert 'class="session-note"' not in body
    assert '{{SIGNOUT_BUTTON}}' not in body
    assert '{{SESSION_NOTE}}' not in body

  def test_get_dashboard_substitutes_session_note_when_header_auth_only(
    self, client_with_dashboard, auth_headers,
  ):
    client, tmp, _ = client_with_dashboard
    (tmp / 'dashboard.html').write_text(
      '<html><body>'
      '<header><p class="meta">'
      '{{SIGNOUT_BUTTON}}{{SESSION_NOTE}}'
      '</p></header>'
      '</body></html>',
      encoding='utf-8',
    )
    r = client.get('/', headers=auth_headers)
    assert r.status_code == 200
    body = r.text
    assert 'class="session-note"' in body
    assert 'class="signout-form"' not in body
    assert '{{SIGNOUT_BUTTON}}' not in body
    assert '{{SESSION_NOTE}}' not in body

  def test_existing_websecret_placeholder_substitution_still_works(
    self, client_with_dashboard, auth_headers,
  ):
    '''Phase 14 regression — ensure Phase 16.1 didn't break placeholder ordering.'''
    client, tmp, _ = client_with_dashboard
    (tmp / 'dashboard.html').write_text(
      '<html><body data-auth="{{WEB_AUTH_SECRET}}">'
      '<header><p class="meta">{{SIGNOUT_BUTTON}}{{SESSION_NOTE}}</p></header>'
      '</body></html>',
      encoding='utf-8',
    )
    r = client.get('/', headers=auth_headers)
    assert r.status_code == 200
    assert 'a' * 32 in r.text
    assert '{{WEB_AUTH_SECRET}}' not in r.text


class TestTraceCookieAllowlist:
  '''Phase 17 D-12 + D-16: tsi_trace_open cookie read + allowlist filter +
  attribute-level placeholder substitution in web/routes/dashboard.py.

  Four tests covering: no cookie, SPI200 only, both instruments, tampered
  cookie with unknown keys (allowlist filter drops them silently).
  '''

  def _make_html_with_placeholders(self, path):
    '''Write dashboard.html with both trace-open placeholders.'''
    path.write_text(
      '<html><body>'
      '<details data-instrument="SPI200"{{TRACE_OPEN_SPI200}}>SPI200</details>'
      '<details data-instrument="AUDUSD"{{TRACE_OPEN_AUDUSD}}>AUDUSD</details>'
      '</body></html>',
      encoding='utf-8',
    )

  def test_no_tsi_trace_open_cookie_substitutes_empty(
    self, client_with_dashboard, auth_headers,
  ):
    '''D-12: no tsi_trace_open cookie -> placeholders replaced with empty
    string -> no <details ... open> attribute.
    '''
    client, tmp, _ = client_with_dashboard
    self._make_html_with_placeholders(tmp / 'dashboard.html')
    r = client.get('/', headers=auth_headers)
    assert r.status_code == 200
    assert '{{TRACE_OPEN_SPI200}}' not in r.text, (
      'D-12: SPI200 placeholder must be substituted (not raw)'
    )
    assert '{{TRACE_OPEN_AUDUSD}}' not in r.text, (
      'D-12: AUDUSD placeholder must be substituted (not raw)'
    )
    # No cookie -> no "open" attribute on either details element.
    assert 'data-instrument="SPI200" open' not in r.text, (
      'D-12: no cookie -> SPI200 must NOT be open'
    )
    assert 'data-instrument="AUDUSD" open' not in r.text, (
      'D-12: no cookie -> AUDUSD must NOT be open'
    )

  def test_tsi_trace_open_cookie_with_spi200_substitutes_open_for_spi200(
    self, client_with_dashboard, auth_headers,
  ):
    '''D-12: tsi_trace_open=SPI200 -> SPI200 details gets " open" attribute,
    AUDUSD stays closed.
    '''
    client, tmp, _ = client_with_dashboard
    self._make_html_with_placeholders(tmp / 'dashboard.html')
    r = _request_with_cookies(client, 'GET', 
      '/', headers=auth_headers,
      cookies={'tsi_trace_open': 'SPI200'},
    )
    assert r.status_code == 200
    assert 'data-instrument="SPI200" open' in r.text, (
      'D-12: SPI200 in cookie -> <details ... open> must render'
    )
    assert 'data-instrument="AUDUSD" open' not in r.text, (
      'D-12: AUDUSD not in cookie -> must NOT be open'
    )

  def test_tsi_trace_open_cookie_with_both_substitutes_open_for_both(
    self, client_with_dashboard, auth_headers,
  ):
    '''D-12: tsi_trace_open=SPI200,AUDUSD -> both details get " open".'''
    client, tmp, _ = client_with_dashboard
    self._make_html_with_placeholders(tmp / 'dashboard.html')
    r = _request_with_cookies(client, 'GET', 
      '/', headers=auth_headers,
      cookies={'tsi_trace_open': 'SPI200,AUDUSD'},
    )
    assert r.status_code == 200
    assert 'data-instrument="SPI200" open' in r.text, (
      'D-12: SPI200 in cookie -> must be open'
    )
    assert 'data-instrument="AUDUSD" open' in r.text, (
      'D-12: AUDUSD in cookie -> must be open'
    )

  def test_tsi_trace_open_cookie_tampered_unknown_keys_filtered(
    self, client_with_dashboard, auth_headers,
  ):
    '''D-16 (RESEARCH §Security): unknown/tampered cookie values are
    silently dropped by the allowlist filter. Only SPI200/AUDUSD are valid.
    '''
    client, tmp, _ = client_with_dashboard
    self._make_html_with_placeholders(tmp / 'dashboard.html')
    r = _request_with_cookies(client, 'GET', 
      '/', headers=auth_headers,
      cookies={'tsi_trace_open': 'AAPL,EVIL_PAYLOAD,SPI200,javascript:alert(1)'},
    )
    assert r.status_code == 200
    # Only SPI200 is in the allowlist — it should be open.
    assert 'data-instrument="SPI200" open' in r.text, (
      'D-16: SPI200 is a valid key — must be open even with mixed tampered cookie'
    )
    # AUDUSD is not in the cookie value, so it stays closed.
    assert 'data-instrument="AUDUSD" open' not in r.text, (
      'D-16: AUDUSD not in cookie -> must stay closed'
    )
    # Tampered values must NOT appear in rendered HTML.
    assert 'AAPL' not in r.text, 'D-16: tampered key AAPL must not leak into HTML'
    assert 'EVIL_PAYLOAD' not in r.text, 'D-16: tampered key EVIL_PAYLOAD must not leak'
    assert 'javascript:alert(1)' not in r.text, 'D-16: XSS payload must not leak'
    # Placeholders must be gone.
    assert '{{TRACE_OPEN_SPI200}}' not in r.text
    assert '{{TRACE_OPEN_AUDUSD}}' not in r.text
