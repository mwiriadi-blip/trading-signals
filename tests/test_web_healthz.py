'''Phase 11 WEB-07 + D-13..D-19 — GET /healthz contract tests.

Fixture strategy (REVIEWS HIGH #2):
  Tests monkeypatch state_manager.load_state DIRECTLY with a stub.
  Setting state_manager.STATE_FILE does NOT work because
  load_state(path: Path = Path(STATE_FILE), ...) binds the default
  at function-definition time.

last_run format (REVIEWS HIGH #1):
  State stores YYYY-MM-DD date strings (main.py:1042). Tests use
  that format in stubs.
'''
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

WEB_APP_PATH = Path('web/app.py')
WEB_HEALTHZ_PATH = Path('web/routes/healthz.py')


@pytest.fixture
def app_instance():
  from web.app import create_app
  return create_app()


@pytest.fixture
def client(app_instance):
  return TestClient(app_instance)


def _stub_load_state(**overrides):
  '''Build a stub load_state() returning reset_state() dict with overrides.'''
  from state_manager import reset_state

  def _fn(*_args, **_kwargs):
    state = reset_state()
    state.update(overrides)
    state.setdefault('_resolved_contracts', {})
    return state

  return _fn


class TestHealthzHappyPath:
  '''D-13..D-15: basic /healthz contract.'''

  def test_returns_200(self, client):
    assert client.get('/healthz').status_code == 200

  def test_content_type_is_json(self, client):
    assert 'application/json' in client.get('/healthz').headers['content-type']

  def test_response_keys_exact(self, client):
    body = client.get('/healthz').json()
    assert set(body.keys()) == {'status', 'last_run', 'stale'}, body

  def test_status_field_is_ok(self, client):
    assert client.get('/healthz').json()['status'] == 'ok'

  def test_last_run_yyyymmdd_when_state_present(self, monkeypatch, freezer):
    '''D-13/D-15: last_run reflects YYYY-MM-DD (REVIEWS HIGH #1).'''
    import state_manager
    monkeypatch.setattr(
      state_manager, 'load_state', _stub_load_state(last_run='2026-04-24'),
    )
    freezer.move_to('2026-04-24T08:00:00+08:00')

    from web.app import create_app
    client = TestClient(create_app())
    body = client.get('/healthz').json()
    assert body == {'status': 'ok', 'last_run': '2026-04-24', 'stale': False}


class TestHealthzMissingStatefile:
  '''D-15: missing state -> last_run=None.'''

  def test_returns_200_when_no_state(self, monkeypatch):
    import state_manager
    monkeypatch.setattr(state_manager, 'load_state', _stub_load_state())

    from web.app import create_app
    assert TestClient(create_app()).get('/healthz').status_code == 200

  def test_body_when_no_state(self, monkeypatch):
    import state_manager
    monkeypatch.setattr(state_manager, 'load_state', _stub_load_state())

    from web.app import create_app
    body = TestClient(create_app()).get('/healthz').json()
    assert body == {'status': 'ok', 'last_run': None, 'stale': False}


class TestHealthzStaleness:
  '''D-16: date-level delta using date.fromisoformat.'''

  def test_stale_true_when_last_run_4_days_ago(self, monkeypatch, freezer):
    import state_manager
    monkeypatch.setattr(
      state_manager, 'load_state', _stub_load_state(last_run='2026-04-20'),
    )
    freezer.move_to('2026-04-24T08:00:00+08:00')

    from web.app import create_app
    assert TestClient(create_app()).get('/healthz').json()['stale'] is True

  def test_stale_false_when_last_run_today(self, monkeypatch, freezer):
    import state_manager
    monkeypatch.setattr(
      state_manager, 'load_state', _stub_load_state(last_run='2026-04-24'),
    )
    freezer.move_to('2026-04-24T08:00:00+08:00')

    from web.app import create_app
    assert TestClient(create_app()).get('/healthz').json()['stale'] is False

  def test_stale_false_at_threshold_2_days(self, monkeypatch, freezer):
    '''D-16 boundary: > 2 days -> stale=True. Exactly 2 days -> False.'''
    import state_manager
    monkeypatch.setattr(
      state_manager, 'load_state', _stub_load_state(last_run='2026-04-22'),
    )
    freezer.move_to('2026-04-24T08:00:00+08:00')

    from web.app import create_app
    assert TestClient(create_app()).get('/healthz').json()['stale'] is False

  def test_stale_false_when_last_run_is_none(self, monkeypatch):
    import state_manager
    monkeypatch.setattr(state_manager, 'load_state', _stub_load_state())

    from web.app import create_app
    assert TestClient(create_app()).get('/healthz').json()['stale'] is False


class TestHealthzDegradedPath:
  '''D-19: handler NEVER returns non-200.'''

  def test_returns_200_when_load_state_raises(self, monkeypatch):
    import state_manager

    def _raise(*args, **kwargs):
      raise RuntimeError('simulated')

    monkeypatch.setattr(state_manager, 'load_state', _raise)

    from web.app import create_app
    assert TestClient(create_app()).get('/healthz').status_code == 200

  def test_body_when_load_state_raises(self, monkeypatch):
    import state_manager

    def _raise(*args, **kwargs):
      raise RuntimeError('simulated')

    monkeypatch.setattr(state_manager, 'load_state', _raise)

    from web.app import create_app
    body = TestClient(create_app()).get('/healthz').json()
    assert body == {'status': 'ok', 'last_run': None, 'stale': False}

  def test_warn_logged_with_web_prefix(self, monkeypatch, caplog):
    import logging
    import state_manager

    def _raise(*args, **kwargs):
      raise RuntimeError('simulated')

    monkeypatch.setattr(state_manager, 'load_state', _raise)

    from web.app import create_app
    client = TestClient(create_app())
    with caplog.at_level(logging.WARNING, logger='web.routes.healthz'):
      client.get('/healthz')

    warns = [r for r in caplog.records if r.levelname == 'WARNING']
    assert any('[Web]' in r.getMessage() for r in warns)


class TestWebHexBoundary:
  '''AST guard: web/ must NOT import pure-math hex modules.'''

  # Phase 13 D-07: dashboard is now an ALLOWED adapter import for
  # web/routes/dashboard.py (web layer calls dashboard.render_dashboard()
  # on stale-state regen). Removing 'dashboard' from this set is the
  # hex-boundary extension.
  # Phase 14 D-02 (this phase): sizing_engine is promoted to allowed
  # for web/routes/trades.py (which imports check_pyramid for the
  # pyramid-up gate per 14-PATTERNS.md Option A).
  # Phase 14 (Plan 14-01 deviation log): system_params ALSO promoted in
  # the same edit because Pydantic model_validator bodies in
  # web/routes/trades.py import MAX_PYRAMID_LEVEL locally (RESEARCH §Pattern
  # 1 line 343). The ast.walk in test_web_modules_do_not_import_hex_core
  # walks ALL nodes including local imports inside function bodies, so
  # a forbidden module cannot be locally-imported anywhere in web/. Inlining
  # MAX_PYRAMID_LEVEL=2 as a duplicate constant (Option B) was rejected
  # to preserve single-source-of-truth.
  FORBIDDEN_FOR_WEB = frozenset({
    'signal_engine',
    'data_fetcher', 'notifier', 'main',
  })

  def test_web_modules_do_not_import_hex_core(self):
    import ast

    web_dir = Path('web')
    violations = []
    for py_file in sorted(web_dir.rglob('*.py')):
      tree = ast.parse(py_file.read_text())
      for node in ast.walk(tree):
        if isinstance(node, ast.Import):
          for alias in node.names:
            top = alias.name.split('.')[0]
            if top in self.FORBIDDEN_FOR_WEB:
              violations.append(f'{py_file}:{node.lineno}: import {alias.name}')
        elif isinstance(node, ast.ImportFrom) and node.module:
          top = node.module.split('.')[0]
          if top in self.FORBIDDEN_FOR_WEB:
            violations.append(f'{py_file}:{node.lineno}: from {node.module}')
    assert violations == [], '\n'.join(violations)

  def test_dashboard_is_not_forbidden_for_web_phase_13_D07(self):
    '''Regression: Phase 13 D-07 promotes dashboard to allowed import.'''
    assert 'dashboard' not in self.FORBIDDEN_FOR_WEB

  def test_sizing_engine_is_not_forbidden_for_web_phase_14_D02(self):
    '''Regression: Phase 14 D-02 promotes sizing_engine to allowed import
    (web/routes/trades.py imports check_pyramid for the pyramid-up gate).'''
    assert 'sizing_engine' not in self.FORBIDDEN_FOR_WEB

  def test_system_params_is_not_forbidden_for_web_phase_14(self):
    '''Regression: Phase 14 promotes system_params alongside sizing_engine.
    web/routes/trades.py imports MAX_PYRAMID_LEVEL inside its Pydantic
    model_validator body (RESEARCH §Pattern 1 line 343). The AST walker
    sees this local import as a violation; promoting system_params resolves
    it. Single-source-of-truth preserved (no duplicate constant).'''
    assert 'system_params' not in self.FORBIDDEN_FOR_WEB

  def test_web_adapter_imports_are_local_not_module_top(self):
    '''C-2 + Phase 13 hex extension: state_manager AND dashboard imports must be LOCAL.'''
    import ast

    forbidden_module_top = frozenset({'state_manager', 'dashboard'})

    web_files = [
      WEB_APP_PATH,
      WEB_HEALTHZ_PATH,
      Path('web/routes/dashboard.py'),
      Path('web/routes/state.py'),
      Path('web/middleware/auth.py'),
    ]
    for py_path in web_files:
      if not py_path.exists():
        # Wave 0: not all files exist yet. Skip; Wave 1+ will populate.
        continue
      tree = ast.parse(py_path.read_text())
      for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module:
          top = node.module.split('.')[0]
          assert top not in forbidden_module_top, (
            f'{py_path}: {top} module-top import (C-2 violation)'
          )
        if isinstance(node, ast.Import):
          for alias in node.names:
            top = alias.name.split('.')[0]
            assert top not in forbidden_module_top, (
              f'{py_path}: {top} module-top import (C-2 violation)'
            )
