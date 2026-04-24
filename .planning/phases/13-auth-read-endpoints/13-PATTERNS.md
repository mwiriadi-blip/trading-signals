# Phase 13: Auth + Read Endpoints — Pattern Map

**Mapped:** 2026-04-25
**Files analyzed:** 9 (4 new source + 4 new tests + 2 modified existing — `web/app.py` and `tests/test_web_healthz.py` modifications + `SETUP-DROPLET.md` doc-extension)
**Analogs found:** 9 / 10 (one new file — `web/middleware/auth.py` — has no exact analog in this codebase; closest structural analogs documented inline)

---

## File Classification

| New / Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---------------------|------|-----------|----------------|---------------|
| `web/middleware/__init__.py` (NEW) | package marker | n/a | `web/routes/__init__.py` (empty file) | exact |
| `web/middleware/auth.py` (NEW) | ASGI middleware (request gate) | request-response | structural: `web/routes/healthz.py` (module docstring, [Web] log prefix, never-crash error handling). Functional: no analog — first ASGI middleware in repo. | role-mismatch (no middleware exists yet) — see "No Analog Found" |
| `web/routes/dashboard.py` (NEW) | route handler (file-serving) | request-response (file I/O) | `web/routes/healthz.py` | exact |
| `web/routes/state.py` (NEW) | route handler (JSON read) | request-response | `web/routes/healthz.py` | exact |
| `web/app.py` (MODIFIED) | factory / composition root | startup | itself (Phase 11 baseline) — extend in place | n/a (modify existing) |
| `tests/test_web_auth_middleware.py` (NEW) | pytest unit tests | request-response (TestClient) | `tests/test_web_healthz.py` | exact |
| `tests/test_web_dashboard.py` (NEW) | pytest unit tests | request-response | `tests/test_web_healthz.py` | exact |
| `tests/test_web_state.py` (NEW) | pytest unit tests | request-response | `tests/test_web_healthz.py` | exact |
| `tests/test_web_app_factory.py` (NEW) | pytest factory startup tests | startup-validation | `tests/test_web_healthz.py::TestWebHexBoundary` (AST guard pattern) + factory fixture style | role-match |
| `tests/test_web_healthz.py` (MODIFIED) | extend `app_instance` fixture, extend `FORBIDDEN_FOR_WEB` | n/a | itself | n/a |
| `SETUP-DROPLET.md` (MODIFIED) | doc extension (operator runbook) | n/a | itself (existing structure) | n/a |

---

## Pattern Assignments

### `web/middleware/__init__.py` (NEW — package marker)

**Analog:** `web/routes/__init__.py` (existing, empty 0-byte file)

**Pattern:** trivial — empty file. The Python interpreter treats it as a package marker. Same as `web/routes/__init__.py`. Just `touch` it.

```python
# web/middleware/__init__.py — empty (zero bytes)
# (Mirror of web/routes/__init__.py established in Phase 11)
```

The directory was reserved in Phase 11 D-03 specifically for this phase. No content required.

---

### `web/middleware/auth.py` (NEW — ASGI middleware, request-response)

**Closest structural analog:** `web/routes/healthz.py` (file-level conventions only — module docstring, logger setup, [Web] prefix, never-crash posture). **Functional analog:** none — Phase 13 introduces the first ASGI middleware in the project. Researcher's RESEARCH.md §Pattern 1 (lines 264–337) provides verbatim implementation already cleared by D-01..D-06; planner should treat that as the reference body.

**Module docstring style — copy from `web/routes/healthz.py:1-13`:**

```python
'''GET /healthz — Phase 11 WEB-07 + D-13..D-19.

Response schema: {'status':'ok', 'last_run':<YYYY-MM-DD str|null>, 'stale':<bool>}

Contract (CONTEXT.md 2026-04-24 reconciled post-REVIEWS HIGH #1):
  D-13: last_run is a DATE-ONLY ISO string ('YYYY-MM-DD'), matching
        what main.py:1042 writes via state['last_run'] = run_date_iso.
  D-14: always HTTP 200 if process is alive.
  D-15: last_run from state_manager.load_state() — local import (C-2).
  D-16: stale=True iff (now.date() - last_run_date).days > 2. Handler
        uses date.fromisoformat (date-only, REVIEWS HIGH #1).
  D-19: NEVER non-200; on exception, return degraded body + WARN [Web].
'''
```

The Phase 11 docstring convention is:
1. Triple-quoted single-line summary referring to the route + phase
2. (optional) Response schema preview
3. "Contract (CONTEXT.md ...):" block listing each `D-XX` decision in scope, one bullet per `D-XX`, with REVIEWS reconciliation refs where applicable

For `web/middleware/auth.py`, the docstring should enumerate D-01..D-06 (and the architecture/log-prefix note).

**Module-top imports + logger setup — copy from `web/routes/healthz.py:14-18`:**

```python
import logging

from fastapi import FastAPI

logger = logging.getLogger(__name__)
```

**Never-crash error handling pattern — copy from `web/routes/healthz.py:50-56`:**

```python
    except Exception as exc:  # noqa: BLE001 — D-19 never-crash
      logger.warning(
        '[Web] /healthz load_state failed: %s: %s',
        type(exc).__name__,
        exc,
      )
      return {'status': 'ok', 'last_run': None, 'stale': False}
```

The middleware itself does not need this never-crash wrapping (auth failure is a deliberate 401, not a "degraded 200"), but the **`[Web]` log-prefix + `logger.warning` + `type(exc).__name__: msg`** convention is the codebase pattern. The middleware's `_log_failure` helper (RESEARCH.md lines 322–336) already follows this.

**Local-import (hex-boundary) convention:** the middleware does NOT need any of `state_manager` / `dashboard` imports — it only consumes `request.headers` and `request.url.path`. So no local-import pattern applies here. Module-top imports are limited to `hmac`, `logging`, `starlette.middleware.base`, `starlette.requests`, `starlette.responses`, `starlette.types`.

**No analog for:**
- `BaseHTTPMiddleware` subclass with `__init__(app, *, secret)` — first occurrence in codebase
- `dispatch(self, request, call_next)` async coroutine — first occurrence
- `hmac.compare_digest` — first occurrence

The planner should copy the implementation body verbatim from RESEARCH.md §Pattern 1 (lines 264–337). It is sourced from official Starlette docs and conforms to all locked decisions.

---

### `web/routes/dashboard.py` (NEW — GET /, request-response with file I/O)

**Analog:** `web/routes/healthz.py` (exact-match: same `register(app: FastAPI)` shape, same local-import, same never-crash pattern).

**Module-top boilerplate — copy from `web/routes/healthz.py:1-18`:**

```python
'''GET /healthz — Phase 11 WEB-07 + D-13..D-19.

Response schema: {'status':'ok', 'last_run':<YYYY-MM-DD str|null>, 'stale':<bool>}

Contract (CONTEXT.md 2026-04-24 reconciled post-REVIEWS HIGH #1):
  D-13: last_run is a DATE-ONLY ISO string ('YYYY-MM-DD'), matching
        what main.py:1042 writes via state['last_run'] = run_date_iso.
  ...
'''
import logging

from fastapi import FastAPI

logger = logging.getLogger(__name__)
```

For `web/routes/dashboard.py`, mirror this exactly: triple-quoted docstring listing D-07..D-11; bare `import logging` + `from fastapi import FastAPI`; module-level `logger = logging.getLogger(__name__)`. Add a module-level path constant for `_DASHBOARD_PATH = 'dashboard.html'` and `_STATE_PATH = 'state.json'` (this is new — but matches codebase style; cf. `state_manager.py:64` `_AWST = zoneinfo.ZoneInfo('Australia/Perth')` for the underscore-prefix module-private convention).

**`register(app: FastAPI)` function-decorator pattern — copy from `web/routes/healthz.py:21-25`:**

```python
def register(app: FastAPI) -> None:
  '''Register GET /healthz on the given FastAPI instance.'''

  @app.get('/healthz')
  def healthz() -> dict:
```

For `dashboard.py`:

```python
def register(app: FastAPI) -> None:
  '''Register GET / on the given FastAPI instance.'''

  @app.get('/')
  def get_dashboard():
    ...
```

**Local-import inside handler (hex-boundary preservation) — copy from `web/routes/healthz.py:26-32`:**

```python
  @app.get('/healthz')
  def healthz() -> dict:
    import zoneinfo
    from datetime import date as _date
    from datetime import datetime

    try:
      from state_manager import load_state  # local import — C-2

      state = load_state()
```

**Phase 11 D-15 / C-2 convention:** `from state_manager import load_state` lives INSIDE the handler function body, not at the module top. Phase 13 `web/routes/dashboard.py` extends this to `from dashboard import render_dashboard` (NEW allowed adapter import per Phase 13 hex-boundary extension). Both must be local-import.

**Never-crash + degraded-response pattern — copy from `web/routes/healthz.py:30-56`:**

```python
    try:
      from state_manager import load_state  # local import — C-2

      state = load_state()
      last_run = state.get('last_run')  # YYYY-MM-DD str or None

      stale = False
      if last_run is not None:
        # D-16: state stores date-only strings — use date.fromisoformat.
        awst = zoneinfo.ZoneInfo('Australia/Perth')
        now_awst = datetime.now(awst)
        try:
          last_dt = _date.fromisoformat(last_run)
          delta_days = (now_awst.date() - last_dt).days
          stale = delta_days > 2
        except (TypeError, ValueError):
          stale = False

      return {'status': 'ok', 'last_run': last_run, 'stale': stale}

    except Exception as exc:  # noqa: BLE001 — D-19 never-crash
      logger.warning(
        '[Web] /healthz load_state failed: %s: %s',
        type(exc).__name__,
        exc,
      )
      return {'status': 'ok', 'last_run': None, 'stale': False}
```

For `dashboard.py`, the never-crash pattern is more nuanced because D-10 distinguishes two failure modes:

1. **Render failure** → log WARN, serve stale on-disk copy (200) — same `try/except Exception ... logger.warning('[Web] dashboard regen failed, serving stale: %s: %s', type(exc).__name__, exc)` shape as healthz.
2. **`dashboard.html` missing entirely** → 503 plain-text `dashboard not ready` — DIFFERENT from healthz (which never returns non-200). Use `PlainTextResponse(content='dashboard not ready', status_code=503, media_type='text/plain; charset=utf-8')`.

Verbatim implementation already provided in RESEARCH.md §Pattern 3 (lines 415–478) — planner copies that body. The `[Web]` log-prefix and `type(exc).__name__: msg` formatting match healthz convention.

---

### `web/routes/state.py` (NEW — GET /api/state, request-response)

**Analog:** `web/routes/healthz.py` (exact-match for same reasons as `dashboard.py` above).

**Same module-top + register-pattern as `dashboard.py`** — see above section. Differences from healthz:

1. Returns `JSONResponse(content=clean, headers={'Cache-Control': 'no-store'})` instead of bare dict (D-13 requires explicit `Cache-Control`).
2. No `try/except` around `load_state()` per D-14 (trust Phase 3 recovery).
3. Top-level underscore-key strip: `clean = {k: v for k, v in state.items() if not k.startswith('_')}` (D-12).

**Reference excerpt from RESEARCH.md §Pattern (lines 645–655):**

```python
@app.get('/api/state')
def get_state():
  from state_manager import load_state
  state = load_state()
  clean = {k: v for k, v in state.items() if not k.startswith('_')}  # D-12
  return JSONResponse(
    content=clean,
    headers={'Cache-Control': 'no-store'},
  )
```

Wrap inside `register(app: FastAPI)` per the healthz pattern. Module-top imports limited to `import logging`, `from fastapi import FastAPI`, `from fastapi.responses import JSONResponse`. `from state_manager import load_state` is LOCAL inside the handler.

---

### `web/app.py` (MODIFIED — factory amendment)

**Existing baseline (read in full — `web/app.py:1-39`, 39 lines):**

```python
'''Web application factory — Phase 11 D-02.

Architecture (CLAUDE.md hex-lite + Phase 10 D-15):
  web/ is an adapter hex (peer of notifier.py, dashboard.py).
  Allowed web imports: fastapi, stdlib, read-only state access via healthz handler.
  Forbidden imports: signal_engine, sizing_engine, system_params,
                     data_fetcher, notifier, dashboard, main.
  Enforced by tests/test_web_healthz.py::TestWebHexBoundary.

Log prefix: [Web] for all web-process log lines.
'''
import logging

from fastapi import FastAPI

from web.routes import healthz as healthz_route

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
  '''Factory — returns a configured FastAPI app (D-02).

  Swagger UI (/docs) and Redoc (/redoc) are LEFT AT FASTAPI DEFAULTS
  for Phase 11 (REVIEWS MEDIUM #6). No external HTTPS yet (Phase 12);
  disabling them is extra policy beyond locked Phase 11 decisions.
  '''
  application = FastAPI(
    title='Trading Signals',
    description='SPI 200 & AUD/USD mechanical trading signal system',
    version='1.1.0',
  )
  healthz_route.register(application)
  logger.info('[Web] FastAPI app created (Phase 11 — /healthz only)')
  return application


# Module-level app — uvicorn entry point: `uvicorn web.app:app`
app = create_app()
```

**Modifications required by Phase 13:**

1. **Module docstring update** — extend `Allowed web imports: ...` to include `dashboard` (new permitted adapter import per D-07). Update `Forbidden imports: ...` to remove `dashboard`. Update header from "Phase 11 D-02" to "Phase 11 D-02 + Phase 13 D-01..D-21".

2. **Add module-top imports** for new routes + middleware + os:
   ```python
   import logging
   import os

   from fastapi import FastAPI

   from web.middleware.auth import AuthMiddleware
   from web.routes import dashboard as dashboard_route
   from web.routes import healthz as healthz_route
   from web.routes import state as state_route
   ```

3. **Add `_MIN_SECRET_LEN` constant + `_read_auth_secret()` helper** before `create_app()` (verbatim from RESEARCH.md §Pattern 2 lines 359–375).

4. **Extend `create_app()` body** to:
   - Call `secret = _read_auth_secret()` BEFORE `FastAPI(...)` instantiation (D-16/D-17 fail-closed).
   - Pass `docs_url=None, redoc_url=None, openapi_url=None` to `FastAPI(...)` (D-21 + RESEARCH extension Pitfall 1).
   - Register all three routes: `healthz_route.register(application)`, `dashboard_route.register(application)`, `state_route.register(application)`.
   - Add `application.add_middleware(AuthMiddleware, secret=secret)` as the FINAL line before `return application` (D-06 — registered LAST runs FIRST).
   - Update the `logger.info(...)` line to `'[Web] FastAPI app created (Phase 13 — /, /api/state, /healthz; auth=on)'`.

5. **Inline comment** at the `add_middleware` line pinning D-06: "Starlette runs middleware in REVERSE of registration. AuthMiddleware MUST stay LAST so it runs FIRST. Future middleware (request-id, compression, etc.) must be registered BEFORE this line."

**Existing `app = create_app()` module-level call** at the bottom (Phase 11 line 39) — REMAINS as is. uvicorn entry point `web.app:app` keeps working.

Verbatim full amendment shown in RESEARCH.md §Pattern 2 (lines 346–407). Planner copies that body and adapts the docstring.

---

### `tests/test_web_auth_middleware.py` (NEW — middleware tests)

**Analog:** `tests/test_web_healthz.py` (exact-match: same `TestClient`, same `monkeypatch.setenv` strategy, same class-per-decision-area structure).

**Module docstring + imports — copy from `tests/test_web_healthz.py:1-19`:**

```python
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
```

For Phase 13, mirror this structure: triple-quoted docstring naming "Phase 13 AUTH-01..AUTH-03 + D-01..D-06 — middleware contract tests"; same imports.

**Fixture pattern — copy from `tests/test_web_healthz.py:22-30` and ADAPT for new secret env:**

```python
@pytest.fixture
def app_instance():
  from web.app import create_app
  return create_app()


@pytest.fixture
def client(app_instance):
  return TestClient(app_instance)
```

**ADAPTATION required by Phase 13** (per RESEARCH §Pitfall 7 — `create_app()` raises on missing `WEB_AUTH_SECRET` once D-16 lands; healthz fixture must be updated to setenv FIRST):

```python
VALID_SECRET = 'a' * 32  # meets D-17 minimum of 32 chars

@pytest.fixture
def valid_secret():
  return VALID_SECRET

@pytest.fixture
def app_instance(monkeypatch, valid_secret):
  monkeypatch.setenv('WEB_AUTH_SECRET', valid_secret)
  from web.app import create_app
  return create_app()

@pytest.fixture
def client(app_instance):
  return TestClient(app_instance)

@pytest.fixture
def auth_headers(valid_secret):
  return {'X-Trading-Signals-Auth': valid_secret}
```

This pattern is also the reference for **modifying `tests/test_web_healthz.py::app_instance`** in the same commit (per RESEARCH.md Pitfall 7 + Open Question 3).

**Stub-helper pattern — copy from `tests/test_web_healthz.py:33-43`:**

```python
def _stub_load_state(**overrides):
  '''Build a stub load_state() returning reset_state() dict with overrides.'''
  from state_manager import reset_state

  def _fn(*_args, **_kwargs):
    state = reset_state()
    state.update(overrides)
    state.setdefault('_resolved_contracts', {})
    return state

  return _fn
```

Reuse verbatim. Phase 13 tests that need a benign state stub (auth-passes-through cases) can use this helper.

**Test class structure — copy from `tests/test_web_healthz.py:46-178`** (4 classes: `TestHealthzHappyPath`, `TestHealthzMissingStatefile`, `TestHealthzStaleness`, `TestHealthzDegradedPath`). Each class groups assertions per decision area with one assertion per test method.

**Test method pattern — copy from `tests/test_web_healthz.py:49-50`:**

```python
class TestHealthzHappyPath:
  '''D-13..D-15: basic /healthz contract.'''

  def test_returns_200(self, client):
    assert client.get('/healthz').status_code == 200

  def test_content_type_is_json(self, client):
    assert 'application/json' in client.get('/healthz').headers['content-type']
```

For Phase 13 middleware tests, classes per RESEARCH.md §Validation Architecture lines 774–786:
- `TestAuthRequired` (missing-header → 401, wrong-header → 401, correct-header → 200/503)
- `TestAuthPasses` (correct-header passes through to route handler)
- `TestExemption` (`/healthz` bypasses auth even without header)
- `TestUnauthorizedResponse` (401 body literal, content-type, no WWW-Authenticate)
- `TestAuditLog` (caplog assertions: WARN line, IP from XFF, UA truncation, %r escaping, fallback)
- `TestConstantTimeCompare` (AST guard: source contains `hmac.compare_digest`, NOT `==` between secret and presented)

**caplog pattern for log-assertion — copy from `tests/test_web_healthz.py:163-178`:**

```python
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
```

For Phase 13 audit-log tests, the only changes are: (a) `logger='web.middleware.auth'` instead of `'web.routes.healthz'`; (b) trigger via `client.get('/', headers={'X-Trading-Signals-Auth': 'wrong'})` instead of mocking load_state.

---

### `tests/test_web_dashboard.py` (NEW — GET / tests)

**Analog:** `tests/test_web_healthz.py` (exact-match — same fixtures, same class style, same `monkeypatch.setattr` for `state_manager.load_state` and `dashboard.render_dashboard`).

Same docstring + imports + fixture pattern as `tests/test_web_auth_middleware.py` above. Same `_stub_load_state` helper (copy or import from a future shared `tests/conftest.py`).

**Test classes per RESEARCH.md lines 787–792:**
- `TestDashboardResponse` (auth-required, content-type=text/html, FileResponse Last-Modified header present)
- `TestStaleness` (mtime comparison D-08 — fresh dashboard.html NOT regenerated, stale dashboard.html triggers regen)
- `TestRenderFailure` (D-10: render exception → log WARN + serve stale)
- `TestFirstRun` (D-10: missing dashboard.html → 503 plain-text `dashboard not ready`)

**Pattern for monkeypatching `dashboard.render_dashboard` follows the same shape as healthz tests' `monkeypatch.setattr(state_manager, 'load_state', ...)` (`tests/test_web_healthz.py:65-67`):**

```python
import state_manager
monkeypatch.setattr(
  state_manager, 'load_state', _stub_load_state(last_run='2026-04-24'),
)
```

For Phase 13:

```python
import dashboard
calls = []
def _track_render(state, *args, **kwargs):
  calls.append(state)

monkeypatch.setattr(dashboard, 'render_dashboard', _track_render)
```

(then assert `len(calls) == 0` for fresh, `len(calls) == 1` for stale).

`os.stat` mocking pattern: use `tmp_path` fixture + real files written with controlled mtime via `os.utime(path, (atime_ns, mtime_ns))` to set atime/mtime. Avoid mocking `os.stat` directly.

---

### `tests/test_web_state.py` (NEW — GET /api/state tests)

**Analog:** `tests/test_web_healthz.py` (exact-match, same as above).

**One test class per RESEARCH.md lines 793–797: `TestStateResponse`.** Test methods cover:
- `test_auth_required` (no header → 401)
- `test_content_type_is_json`
- `test_strips_underscore_prefixed_top_level_keys`
- `test_preserves_nested_underscore_keys`
- `test_cache_control_no_store`
- `test_response_is_compact_json` (assert no `\n  ` indent in raw text)

`monkeypatch.setattr(state_manager, 'load_state', ...)` pattern is the same as healthz tests, with stub returning a dict that includes both top-level `_foo` keys (must be stripped) and nested dicts that contain `_bar` keys (must be preserved).

---

### `tests/test_web_app_factory.py` (NEW — startup-validation tests)

**Analog:** `tests/test_web_healthz.py::TestWebHexBoundary` (lines 181–221) — for the AST-guard pattern. Plus general factory-fixture style.

**AST guard pattern — copy from `tests/test_web_healthz.py:181-221`:**

```python
class TestWebHexBoundary:
  '''AST guard: web/ must NOT import pure-math hex modules.'''

  FORBIDDEN_FOR_WEB = frozenset({
    'signal_engine', 'sizing_engine', 'system_params',
    'data_fetcher', 'notifier', 'dashboard', 'main',
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

  def test_web_app_does_not_import_state_manager_at_module_top(self):
    '''C-2: state_manager import must be LOCAL, not module-top.'''
    import ast

    for py_path in [WEB_APP_PATH, WEB_HEALTHZ_PATH]:
      tree = ast.parse(py_path.read_text())
      for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module:
          top = node.module.split('.')[0]
          assert top != 'state_manager', f'{py_path}: state_manager module-top import'
        if isinstance(node, ast.Import):
          for alias in node.names:
            top = alias.name.split('.')[0]
            assert top != 'state_manager', f'{py_path}: state_manager module-top import'
```

**MODIFICATION REQUIRED by Phase 13** (in `tests/test_web_healthz.py` directly, not in `test_web_app_factory.py`):
- Remove `'dashboard'` from `FORBIDDEN_FOR_WEB` set (Phase 13 promotes `dashboard` to allowed adapter import per D-07).
- Extend the `module-top import` test to include `dashboard` AND the new files (`web/routes/dashboard.py`, `web/routes/state.py`, `web/middleware/auth.py`).

**`test_web_app_factory.py` test classes per RESEARCH.md lines 798–805:**
- `TestSecretValidation` — calls `create_app()` directly (no fixture); uses `monkeypatch.delenv('WEB_AUTH_SECRET', raising=False)` to assert `RuntimeError` raised; uses `monkeypatch.setenv('WEB_AUTH_SECRET', 'short')` to assert short-secret raises; `monkeypatch.setenv('WEB_AUTH_SECRET', 'a' * 32)` to assert exactly-32-char accepted.
- `TestDocsDisabled` — uses the `client` fixture with valid auth headers; asserts `client.get('/docs', headers=auth_headers).status_code == 404`, similarly for `/redoc` and `/openapi.json`. Plus a no-auth variant asserting 401 (proves middleware reaches it).

**RuntimeError-raises pattern — Python idiomatic, no codebase analog. Use:**

```python
import pytest

class TestSecretValidation:
  def test_missing_secret_raises(self, monkeypatch):
    monkeypatch.delenv('WEB_AUTH_SECRET', raising=False)
    with pytest.raises(RuntimeError, match='WEB_AUTH_SECRET'):
      from web.app import create_app
      create_app()
```

---

### `tests/test_web_healthz.py` (MODIFIED — fixture + boundary updates)

**Existing baseline:** read in full above (`tests/test_web_healthz.py:1-221`).

**Modifications required:**

1. **Fixture `app_instance` (lines 22-25)** — add `monkeypatch` + `WEB_AUTH_SECRET` setenv, mirroring the new `tests/test_web_auth_middleware.py::app_instance` fixture above. Without this, all healthz tests break the moment Phase 13 D-16 lands.

2. **`TestWebHexBoundary.FORBIDDEN_FOR_WEB` (lines 184-187)** — remove `'dashboard'` from the set. Resulting set:
   ```python
   FORBIDDEN_FOR_WEB = frozenset({
     'signal_engine', 'sizing_engine', 'system_params',
     'data_fetcher', 'notifier', 'main',
   })
   ```
   (Note: also add a regression assertion to prove `'dashboard'` is NOT in this set.)

3. **`test_web_app_does_not_import_state_manager_at_module_top` (lines 208-221)** — extend the `for py_path in [...]` list to include `Path('web/routes/dashboard.py')`, `Path('web/routes/state.py')`, `Path('web/middleware/auth.py')`. Extend the assertion to also forbid module-top `dashboard` import (cf. `state_manager` case).

---

### `SETUP-DROPLET.md` (MODIFIED — append "Configure auth secret" section)

**Existing baseline:** read in full above (`SETUP-DROPLET.md:1-242`).

**Existing structure (so the new section slots correctly):**

| Section heading | Lines |
|-----------------|-------|
| `# SETUP-DROPLET.md — Trading Signals web-layer one-time setup` (title) | 1-12 |
| `## Install systemd unit` | 16-43 |
| `## Install sudoers entry for trader` | 46-107 |
| `## Verify port binding (WEB-02 / SC-4)` | 110-138 |
| `## Verify deploy.sh end-to-end (INFRA-04 / SC-3)` | 142-196 |
| `## Verify boot persistence (WEB-01 / SC-1)` | 200-213 |
| `## Troubleshooting` | 217-228 |
| `## What's NOT in this doc` | 232-237 |
| trailing footer | 239-242 |

**Slot location for Phase 13 section:** **between `## Install systemd unit` and `## Install sudoers entry for trader`** — i.e., after unit installation but BEFORE the sudoers step. Rationale: the unit references `EnvironmentFile=-/etc/trading-signals/.env`, so the `.env` must exist with `WEB_AUTH_SECRET` BEFORE the unit can start successfully under D-16 fail-closed.

**Alternative slot:** between `## Install sudoers entry for trader` and `## Verify port binding`. Either works; planner picks the clearer flow. RESEARCH.md does not pick a specific slot.

**Existing section header style — match this exact pattern:**

```markdown
## Install systemd unit

```bash
sudo cp /home/trader/trading-signals/systemd/trading-signals-web.service \
        /etc/systemd/system/trading-signals-web.service
...
```
```

`##` H2 heading → blank line → optional intro paragraph → fenced bash code block → blank line → "Expected:" or "Validate:" subsection → another fenced block.

**Phase 13 section (per D-19) should follow this structure:**

```markdown
## Configure auth secret (Phase 13 AUTH-01)

Generate a 32-character hex secret (≈128 bits entropy):

```bash
openssl rand -hex 16
# Example output: a1b2c3d4e5f6...  (32 hex chars)
```

(Fallback if `openssl` is not installed: `python3 -c "import secrets; print(secrets.token_hex(16))"`.)

Append the secret to `/home/trader/trading-signals/.env` (create the file if absent — `EnvironmentFile=-` makes it optional in Phase 11, but Phase 13 D-16 fail-closed requires it):

```bash
echo "WEB_AUTH_SECRET=<paste-32-char-hex-here>" >> /home/trader/trading-signals/.env
chmod 600 /home/trader/trading-signals/.env
```

Restart the web unit and verify it boots cleanly:

```bash
sudo systemctl restart trading-signals-web
journalctl -u trading-signals-web -n 20 --no-pager
# Expected: no `RuntimeError: WEB_AUTH_SECRET env var is missing or empty` line.
```

Test the auth gate end-to-end:

```bash
curl -sI http://127.0.0.1:8000/
# Expected: HTTP/1.1 401 Unauthorized

curl -sI -H "X-Trading-Signals-Auth: <your-secret>" http://127.0.0.1:8000/
# Expected: HTTP/1.1 200 OK (or 503 if dashboard.html not yet rendered).
```
```

**Update `## What's NOT in this doc` (lines 232-237)** — remove the `Auth secret → Phase 13` line since Phase 13 IS now in this doc. The `HTTPS / nginx / Let's Encrypt → Phase 12` line stays (Phase 12 has its own SETUP-HTTPS.md).

**Update prerequisites (line 10)** — change "`.env` file is **NOT required** for Phase 11" to acknowledge that AFTER Phase 13 it IS required: keep the Phase 11 sentence as historical context but add "Phase 13 (AUTH) introduces `WEB_AUTH_SECRET` and makes `.env` REQUIRED — see §Configure auth secret below."

**Doc-completeness test pattern** — `tests/test_setup_droplet_doc.py` already enforces section headers via regex (lines 22-42 above). Phase 13 plan must add a corresponding test, e.g.:

```python
def test_section_configure_auth_secret(self, doc_text):
  assert re.search(r'^## Configure auth secret', doc_text, re.MULTILINE)

def test_openssl_command_present(self, doc_text):
  assert 'openssl rand -hex 16' in doc_text

def test_env_file_chmod_600(self, doc_text):
  assert 'chmod 600' in doc_text and '.env' in doc_text
```

---

## Shared Patterns

### Module docstring style (Phase 11 convention — applies to ALL new web/ source files)

**Source:** `web/routes/healthz.py:1-13`, `state_manager.py:1-33`, `dashboard.py:1-60`, `web/app.py:1-11`

```python
'''GET /<route> — Phase <N> <REQ-IDS> + D-XX..D-YY.

Response schema: <one-liner if applicable>

Contract (CONTEXT.md <date> reconciled post-REVIEWS <area>):
  D-XX: <short prose stating the decision-bound behavior>.
  D-YY: <...>.

Architecture (CLAUDE.md hex-lite + Phase 10 D-15):
  <module-role-in-hex>.
  Allowed: <module list>.
  Forbidden: <module list>.

Log prefix: [Web] for all web-process log lines.
'''
```

Apply to: `web/middleware/auth.py`, `web/routes/dashboard.py`, `web/routes/state.py`. Update `web/app.py` docstring header from "Phase 11 D-02" to "Phase 11 D-02 + Phase 13 D-01..D-21+".

### Logging convention (CLAUDE.md §Conventions, established Phase 11)

**Source:** `web/routes/healthz.py:18, 51-55`, `dashboard.py:1076`, `notifier.py` (passim)

```python
import logging

logger = logging.getLogger(__name__)

# usage:
logger.info('[Web] FastAPI app created (Phase 13 — /, /api/state, /healthz; auth=on)')
logger.warning('[Web] auth failure: ip=%s ua=%r path=%s', client_ip, ua, path)
logger.warning('[Web] dashboard regen failed, serving stale: %s: %s', type(exc).__name__, exc)
```

Rules:
- `logger = logging.getLogger(__name__)` at module top, immediately after imports.
- `[Web]` prefix on EVERY log line emitted by `web/` code.
- Format string with `%`-args (NOT f-strings) — lazy-evaluation, journald-friendly.
- For exceptions: `'%s: %s', type(exc).__name__, exc` — never log full traceback in WARN; INFO is irrelevant for failures.
- For UA / user-controlled strings: use `%r` to escape control chars.

### Hex-boundary preservation (CLAUDE.md §Architecture)

**Source:** `tests/test_web_healthz.py:181-221`, `web/routes/healthz.py:31-32`

Two complementary rules:

1. **AST blocklist** — `tests/test_web_healthz.py::TestWebHexBoundary.FORBIDDEN_FOR_WEB` lists modules that `web/` MUST NOT import. Phase 13 promotes `dashboard` from forbidden to allowed; result: `{signal_engine, sizing_engine, system_params, data_fetcher, notifier, main}`.

2. **Local-import rule (Phase 11 C-2)** — adapter imports (`state_manager`, `dashboard`) MUST be LOCAL inside the handler function, not at module top. The corresponding test extends to all new files:

```python
# Inside the handler:
from state_manager import load_state  # local import — C-2
from dashboard import render_dashboard  # local import — Phase 13 hex-boundary extension
```

Apply to: `web/routes/dashboard.py` (both imports), `web/routes/state.py` (only `state_manager`). NOT applicable to `web/middleware/auth.py` (it imports neither).

### `register(app: FastAPI)` route module pattern (Phase 11 C-1)

**Source:** `web/routes/healthz.py:21-25`, `web/app.py:33`

```python
# In each web/routes/<route>.py:
def register(app: FastAPI) -> None:
  '''Register GET /<path> on the given FastAPI instance.'''

  @app.get('/<path>')
  def <handler_name>():
    ...

# In web/app.py create_app():
healthz_route.register(application)
dashboard_route.register(application)  # NEW Phase 13
state_route.register(application)      # NEW Phase 13
```

Each route module exposes ONE public name: `register`. No FastAPI APIRouter, no decorators on module-level functions. This is the codebase convention for testability (each route module is self-contained; `create_app()` composes them).

### Test fixture pattern (Phase 11 + Phase 13 amendment)

**Source:** `tests/test_web_healthz.py:22-30`, RESEARCH.md §Pitfall 7 (lines 559–578)

After D-16 lands, ALL web-test fixtures that call `create_app()` must FIRST `monkeypatch.setenv('WEB_AUTH_SECRET', ...)`. Pattern:

```python
VALID_SECRET = 'a' * 32  # 32 chars — meets D-17 minimum

@pytest.fixture
def valid_secret():
  return VALID_SECRET

@pytest.fixture
def app_instance(monkeypatch, valid_secret):
  monkeypatch.setenv('WEB_AUTH_SECRET', valid_secret)
  from web.app import create_app
  return create_app()

@pytest.fixture
def client(app_instance):
  return TestClient(app_instance)

@pytest.fixture
def auth_headers(valid_secret):
  return {'X-Trading-Signals-Auth': valid_secret}
```

This is a NEW pattern — apply uniformly to all four new test files AND retrofit `tests/test_web_healthz.py::app_instance`. Researcher recommends a shared `tests/conftest.py` or per-file copy; planner picks. (Note: `tests/conftest.py` is empty today — `tests/conftest.py:0 bytes`.)

### Doc-completeness test (`tests/test_setup_droplet_doc.py` pattern)

**Source:** `tests/test_setup_droplet_doc.py:22-42`

Every section header in `SETUP-DROPLET.md` has a corresponding `def test_section_<name>(self, doc_text)` regex assertion in `tests/test_setup_droplet_doc.py::TestDocStructure`. Phase 13 plan must add:

```python
def test_section_configure_auth_secret(self, doc_text):
  assert re.search(r'^## Configure auth secret', doc_text, re.MULTILINE)
```

…plus content tests for `openssl rand -hex 16`, `chmod 600`, `WEB_AUTH_SECRET=`, etc.

---

## No Analog Found

| File | Role | Data Flow | Reason | Recommendation |
|------|------|-----------|--------|----------------|
| `web/middleware/auth.py` | ASGI middleware | request-response | First ASGI middleware in the project. Phase 11 left `web/middleware/` directory empty (D-03) reserved for exactly this phase. | Use **RESEARCH.md §Pattern 1 (lines 264–337)** as the reference implementation — sourced from official Starlette docs. Match `web/routes/healthz.py` for module-level conventions (docstring style, `logger`, `[Web]` prefix). |
| `tests/test_web_app_factory.py::TestSecretValidation` | startup validation | startup | First test in the project that asserts `RuntimeError` raised at factory time. | Use Python idiom `with pytest.raises(RuntimeError, match='WEB_AUTH_SECRET'):` per RESEARCH.md §Code Examples. No codebase analog. |

---

## Project Conventions to Honor (from CLAUDE.md)

| Convention | Source | Apply To |
|------------|--------|----------|
| 2-space indent | CLAUDE.md §Conventions, enforced by `tests/test_signal_engine.py::_has_two_space_indent_evidence` | All new `.py` files |
| Single quotes for strings | CLAUDE.md §Conventions; ruff `flake8-quotes` | All new `.py` files. Triple-double-quote `"""..."""` is OK only if the docstring contains single quotes that would conflict; preferred form is `'''...'''` (cf. `web/routes/healthz.py:1`, `state_manager.py:1`, `dashboard.py:1` all use `'''`) |
| `snake_case` for functions, `UPPER_SNAKE` for constants | CLAUDE.md §Conventions | `_read_auth_secret`, `_MIN_SECRET_LEN`, `EXEMPT_PATHS`, `AUTH_HEADER`, `UA_TRUNCATE`, `_DASHBOARD_PATH`, `_STATE_PATH`, `_is_stale`, `get_dashboard`, `get_state` |
| Module-private names prefixed `_` | `state_manager.py:64-79` (`_AWST`, `_REQUIRED_TRADE_FIELDS`), `dashboard.py:_INLINE_CSS` | `_DASHBOARD_PATH`, `_STATE_PATH`, `_MIN_SECRET_LEN`, `_read_auth_secret`, `_is_stale` |
| Log prefix `[Web]` | CLAUDE.md §Conventions, established `web/app.py:34`, `web/routes/healthz.py:51` | EVERY `logger.*` call in new web code |
| ISO `YYYY-MM-DD` for dates, AWST for user-facing times | CLAUDE.md §Conventions | Not applicable to Phase 13 (no date formatting in new code; SETUP-DROPLET.md examples may include UTC timestamps from journald — leave as-is) |
| Phase decision references `D-XX` in docstrings | `web/routes/healthz.py:5-12`, `state_manager.py:9-16` | Module docstrings of all new files |
| `# noqa: BLE001 — D-XX never-crash` for broad `except Exception` | `web/routes/healthz.py:50` | `web/routes/dashboard.py` D-10 catch (the only Phase 13 broad-except site; middleware's compare-mismatch is NOT a catch — it's a deliberate 401) |

### Forbidden imports (TestDeterminism / TestWebHexBoundary)

**Source:** `tests/test_signal_engine.py:565-589` (`FORBIDDEN_MODULES`, `FORBIDDEN_MODULES_STDLIB_ONLY`, `FORBIDDEN_MODULES_STATE_MANAGER`, `_HEX_PATHS_ALL`); `tests/test_web_healthz.py:184-187` (`FORBIDDEN_FOR_WEB`).

**Phase 13 modifications:**

1. `tests/test_web_healthz.py::TestWebHexBoundary.FORBIDDEN_FOR_WEB` — remove `'dashboard'`. Resulting set:
   ```python
   FORBIDDEN_FOR_WEB = frozenset({
     'signal_engine', 'sizing_engine', 'system_params',
     'data_fetcher', 'notifier', 'main',
   })
   ```

2. `tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent` — **NO CHANGE**. That test guards `signal_engine.py`, `sizing_engine.py`, `system_params.py` (the pure-math hexes). Phase 13 touches NONE of those. The pure-math hexes still must NOT import `state_manager`, `notifier`, `dashboard`, `web.*`, etc.

3. The `web/routes/dashboard.py` allowed import of the `dashboard` module is **specifically permitted** by Phase 13 D-07 amendment to the `web/` allowed-imports list. Verified by deleting `'dashboard'` from `FORBIDDEN_FOR_WEB`.

---

## Metadata

**Analog search scope:**
- `web/` (3 files: `__init__.py`, `app.py`, `routes/healthz.py` — Phase 11 baseline)
- `tests/test_web_*.py` (2 files: `test_web_healthz.py`, `test_web_systemd_unit.py`)
- `tests/test_setup_droplet_doc.py` (existing doc-completeness pattern)
- `state_manager.py`, `dashboard.py` (module docstring style + atomic-write convention reference)
- `tests/test_signal_engine.py::TestDeterminism` (forbidden-imports / 2-space-indent guard pattern)
- `SETUP-DROPLET.md` (existing operator runbook structure)
- Repo root (file inventory)

**Files scanned:** ~30. **Files read in full:** 5 (`web/app.py`, `web/routes/healthz.py`, `tests/test_web_healthz.py`, `web/routes/__init__.py`-empty, `SETUP-DROPLET.md`). **Files read partially:** 4 (`state_manager.py:1-80`, `dashboard.py:1-60 + 1050-1089`, `tests/test_signal_engine.py:580-820`, `tests/test_setup_droplet_doc.py:1-60`).

**Pattern extraction date:** 2026-04-25

**Patterns identified:**
1. Module docstring with `D-XX` decision-refs + Architecture (hex-lite) block + `Log prefix: [Web]` line — uniform across `web/`, `state_manager.py`, `dashboard.py`.
2. `register(app: FastAPI) -> None` pattern for each route module; `create_app()` calls each `register(...)` in turn.
3. Local-imports inside handler functions to preserve hex boundary (Phase 11 C-2); enforced by AST guard test.
4. `[Web]` log prefix + `logger.warning('... %s: %s', type(exc).__name__, exc)` for exception logging.
5. `pytest` + `fastapi.testclient.TestClient` + `monkeypatch.setattr(state_manager, 'load_state', stub)` for handler tests; `caplog.at_level(logging.WARNING, logger='<dotted-module>')` for log-assertion tests.
6. Phase 13 NEW pattern: factory-time `monkeypatch.setenv('WEB_AUTH_SECRET', ...)` BEFORE `create_app()` call (RESEARCH §Pitfall 7); applies to all web-test fixtures including the existing `tests/test_web_healthz.py::app_instance`.
7. Doc-completeness test (`tests/test_setup_droplet_doc.py`) requires a `def test_section_<name>` regex assertion for every new `## Section header` in `SETUP-DROPLET.md`.

---

*Phase: 13-auth-read-endpoints*
*PATTERNS.md generated: 2026-04-25*
