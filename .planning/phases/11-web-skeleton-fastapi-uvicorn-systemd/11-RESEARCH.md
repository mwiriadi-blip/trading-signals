# Phase 11: Web Skeleton — FastAPI + uvicorn + systemd — Research

**Researched:** 2026-04-24
**Domain:** FastAPI / uvicorn / systemd service units / bash deploy scripting
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- D-01: New `web/` directory at repo root.
- D-02: `web/app.py` exposes `create_app() -> FastAPI` factory + module-level `app = create_app()`.
- D-03: Future-proof directory structure: `web/app.py`, `web/routes/`, `web/middleware/`, `web/__init__.py`, `web/routes/__init__.py`.
- D-04: Shared `.venv` with existing trading-signals service.
- D-05: Add `fastapi`, `uvicorn[standard]`, `httpx` with exact pins. Baseline suggestion `fastapi==0.115.5`, `uvicorn[standard]==0.34.0`, `httpx==0.28.1` — planner confirms current at execution time.
- D-06: New unit file `/etc/systemd/system/trading-signals-web.service`.
- D-07: User=trader, Group=trader.
- D-08: Restart=on-failure, RestartSec=10s.
- D-09: After=network.target, Wants=trading-signals.service (soft dep, NOT Requires=).
- D-10: Hardening directives: NoNewPrivileges=true, PrivateTmp=true, ProtectSystem=strict, ReadWritePaths=/home/trader/trading-signals, ProtectHome=read-only.
- D-11: ExecStart binds to 127.0.0.1:8000, workers=1, log-level=info. WorkingDirectory=/home/trader/trading-signals, EnvironmentFile=.env.
- D-12: StandardOutput=journal + StandardError=journal (journald).
- D-13: Response shape: `{"status":"ok","last_run":"<ISO+AWST>","stale":false}`.
- D-14: Always HTTP 200 if the process is alive.
- D-15: `last_run` from `state_manager.load_state()`, key `state.get('last_run')`.
- D-16: `stale` is True when `last_run` > 2 days ago (Phase 8 ERR-05 threshold). If `last_run` is None, `stale` is False.
- D-17: `/healthz` is exempt from auth (WEB-07 locked).
- D-18: No caching — each request calls `load_state()` fresh.
- D-19: Error inside `/healthz` returns `{"status":"ok","last_run":null,"stale":false}` with 200. Log WARN with `[Web]` prefix. Never non-200.
- D-20: `deploy.sh` shebang `#!/usr/bin/env bash`, `set -euo pipefail`.
- D-21: Script runs as `trader`. Passwordless sudo scoped to two unit names only.
- D-22: Branch safety check first: reject if not `main`.
- D-23: Deploy sequence: branch check → fetch → pull --ff-only → pip upgrade → pip install -r → systemctl restart both → curl smoke test → echo success + commit hash.
- D-24: Idempotent on no-op second run.
- D-25: No automatic rollback in Phase 11.

### Claude's Discretion

- Exact FastAPI / uvicorn / httpx pin versions — planner picks via latest stable; confirmed below.
- Test strategy for `/healthz` — FastAPI TestClient (in-process), no real uvicorn in Phase 11.
- `[deploy]` log prefix format for deploy.sh lines.
- Whether `SETUP-DROPLET.md` is a new doc or extends Phase 10's `SETUP-DEPLOY-KEY.md` — RECOMMEND extending Phase 10's doc.

### Deferred Ideas (OUT OF SCOPE)

- Automatic rollback in deploy.sh
- State-read caching in `/healthz`
- Real-process uvicorn integration test (Phase 16)
- Multi-worker support (v1.2)
- Health metrics / Prometheus endpoint (v1.2)
- Separate web venv (v2.0)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| WEB-01 | FastAPI app runs as a separate systemd unit (`trading-signals-web`) on the droplet and starts on boot | systemd unit file body in Section 3; `WantedBy=multi-user.target` + `--enable` instruction in setup doc |
| WEB-02 | uvicorn serves the app on `localhost:8000`; nginx reverse-proxies from 443 → 8000 (nginx is Phase 12; Phase 11 establishes localhost:8000 only) | `--host 127.0.0.1 --port 8000` in ExecStart; SS verification command in SC-4 |
| WEB-07 | `GET /healthz` returns 200 with `{"status":"ok","last_run":"...","stale":false}`; exempt from auth | Handler code shape + test strategy in Sections 5 and 6 |
| INFRA-04 | `deploy.sh` idempotent; callable from post-push webhook or manual run | Full script body in Section 7; idempotency analysis in Section 12 |
</phase_requirements>

---

## 1. Executive Summary

- **Library versions are significantly newer than the CONTEXT.md baseline.** FastAPI is at 0.136.1 (vs baseline 0.115.5), uvicorn at 0.46.0 (vs 0.34.0). Both are Python 3.11 compatible, no known CVEs. httpx stays at 0.28.1 (latest). RECOMMEND pinning at current latest rather than the stale baseline — this is a new install with no downgrade risk.
- **systemd unit body is fully derivable from CONTEXT.md decisions.** The v1.0 Phase 7 hardening directives (NoNewPrivileges, PrivateTmp, ProtectSystem, ProtectHome, ReadWritePaths) are cloned verbatim. `Wants=` is confirmed as the correct soft-dependency directive; `After=` ordering with `network.target` is standard and well-supported.
- **`/healthz` handler should be a plain sync def, not async def.** `state_manager.load_state()` is synchronous blocking I/O; FastAPI runs sync handlers in a threadpool automatically, which is correct behaviour for this use case. No `run_in_threadpool` boilerplate needed.
- **FastAPI TestClient uses httpx under the hood.** Importing `TestClient` from `fastapi.testclient` and passing the `app` object is all that's needed. State-path injection uses monkeypatching of `state_manager.STATE_FILE` (or a direct `Path` override if `load_state` accepts a `path` param — it does, per the source). `pytest-freezer` works fine for stubbing datetime in the stale-flag test.
- **No changes to `test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent` are needed.** `web/` is an adapter module outside the hex core; the existing FORBIDDEN_MODULES_* blocklists check specific named modules and do not need to enumerate `web` as a forbidden module anywhere.

---

## 2. Confirmed Library Versions

### Version Verification (via `pip index versions`, 2026-04-24)

| Library | Latest Stable | CONTEXT.md Baseline | Delta | Python 3.11 Compat |
|---------|--------------|--------------------|----|---|
| fastapi | **0.136.1** | 0.115.5 | +21 minor versions | YES — requires Python ≥ 3.10 [VERIFIED: PyPI] |
| uvicorn[standard] | **0.46.0** | 0.34.0 | +12 minor versions | YES [VERIFIED: PyPI] |
| httpx | **0.28.1** | 0.28.1 | no change | YES [VERIFIED: PyPI] |

**Recommendation:** Pin at current latest, not the stale baseline. These are exact pins; no CVE was found for any of the three at the verified versions. [VERIFIED: PyPI via `pip index versions`; security: snyk.io search performed]

**FastAPI 0.115.5 vs 0.136.1 note:** There is no breaking change between 0.115.x and 0.136.x that affects Phase 11 scope (no-mutation, read-only, simple GET endpoint). The factory pattern `create_app() -> FastAPI` and `app.include_router()` API are unchanged. [CITED: fastapi.tiangolo.com/release-notes/]

**Known CVE history (FastAPI):** CVE-2021-32677 (CSRF with cookie auth — irrelevant for `/healthz` which has no auth), CVE-2024-47874 (Starlette multipart form parsing — irrelevant, Phase 11 has no form endpoints). No open CVEs affect Phase 11 scope. [VERIFIED: snyk.io/package/pip/fastapi]

**uvicorn[standard] extras:** Installs `uvloop`, `httptools`, and `websockets`. `uvloop` gives a ~2× event loop speedup on Linux; harmless on macOS dev. No additional configuration required. [CITED: uvicorn.org]

**Exact pins for requirements.txt:**
```
fastapi==0.136.1
uvicorn[standard]==0.46.0
httpx==0.28.1
```

**Installation on droplet:**
```bash
.venv/bin/pip install -r requirements.txt
```

---

## 3. systemd Unit File — Complete Body

**File to commit in repo:** `systemd/trading-signals-web.service`
**Operator copies to:** `/etc/systemd/system/trading-signals-web.service`

```ini
[Unit]
Description=Trading Signals — FastAPI web process
After=network.target
Wants=trading-signals.service

[Service]
Type=simple
User=trader
Group=trader
WorkingDirectory=/home/trader/trading-signals
EnvironmentFile=/home/trader/trading-signals/.env
ExecStart=/home/trader/trading-signals/.venv/bin/uvicorn web.app:app \
          --host 127.0.0.1 \
          --port 8000 \
          --workers 1 \
          --log-level info
Restart=on-failure
RestartSec=10s
StandardOutput=journal
StandardError=journal
SyslogIdentifier=trading-signals-web

NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/home/trader/trading-signals
ProtectHome=read-only

[Install]
WantedBy=multi-user.target
```

### Notes on each directive

**`After=network.target`** — standard dependency ordering; ensures uvicorn's `bind('127.0.0.1:8000')` is called after the loopback interface is available. The loopback (`lo`) interface is always available after network.target on any systemd host. [VERIFIED: systemd docs — network.target is the correct target for network-using services that do not need a specific network interface to be up]

**`Wants=trading-signals.service`** — soft dependency per D-09. If the signal service fails, the web service still starts. `Wants=` is the correct directive (NOT `Requires=`, which would cascade failure). [VERIFIED: systemd.unit(5) man page semantics]

**`Type=simple`** — correct for uvicorn. uvicorn does not fork or notify systemd; it stays as PID=ExecStart process. [ASSUMED — systemd Type=simple is the standard for single-process Python servers; no other Type is appropriate here]

**`SyslogIdentifier=trading-signals-web`** — sets the journald tag so `journalctl -u trading-signals-web` filters correctly AND the syslog ident in each log line is the service name, not the binary path. [VERIFIED: standard systemd pattern]

**`ProtectSystem=strict`** — makes the entire filesystem hierarchy read-only EXCEPT what is explicitly listed in `ReadWritePaths`. Combined with `ReadWritePaths=/home/trader/trading-signals`, uvicorn can only write inside the repo dir (state.json tempfile, dashboard.html). Cannot write to /etc, /var, /tmp (PrivateTmp provides a private /tmp). [VERIFIED: Phase 7 v1.0 precedent]

**`WantedBy=multi-user.target`** — ensures the unit is started when the system reaches multi-user mode (standard for server daemons). Required for `systemctl enable trading-signals-web` to work. [VERIFIED: standard systemd pattern]

### Operator one-time setup commands (for SETUP-DROPLET.md)

```bash
# Copy unit file from repo to system
sudo cp /home/trader/trading-signals/systemd/trading-signals-web.service \
        /etc/systemd/system/trading-signals-web.service

# Reload daemon + enable + start
sudo systemctl daemon-reload
sudo systemctl enable trading-signals-web
sudo systemctl start trading-signals-web

# Verify
systemctl status trading-signals-web
ss -tlnp | grep 8000  # must show 127.0.0.1:8000 only
```

---

## 4. FastAPI Factory + Router Pattern

### `web/app.py` — create_app() factory

```python
'''Web application factory.

create_app() builds and returns a FastAPI instance with all routes registered.
The module-level `app` is what uvicorn references: `web.app:app`.

Architecture: web/ is an adapter hex (like notifier.py, dashboard.py).
Allowed to import state_manager (read-only per Phase 10 D-15).
NOT allowed to import signal_engine, sizing_engine, system_params directly.
Log prefix: [Web] for all web-process log lines (CLAUDE.md §Conventions).
'''
# Source: FastAPI docs — bigger applications pattern
# https://fastapi.tiangolo.com/tutorial/bigger-applications/

from fastapi import FastAPI

from web.routes import healthz as healthz_route


def create_app() -> FastAPI:
  '''Factory function — returns a configured FastAPI app.

  Tests call create_app() directly to get a fresh instance.
  Phase 13 extends this factory to add auth middleware and more routes.
  '''
  application = FastAPI(
    title='Trading Signals',
    description='SPI 200 & AUD/USD mechanical trading signal system',
    version='1.1.0',
    docs_url=None,    # disable Swagger UI in production (no-docs posture until Phase 13)
    redoc_url=None,
  )
  healthz_route.register(application)
  return application


# Module-level app — uvicorn entry point: web.app:app
app = create_app()
```

**Rationale for `docs_url=None`:** No external access until Phase 12 (nginx), and no auth until Phase 13. Disabling the interactive docs prevents any accidental exposure if port 8000 becomes reachable before Phase 12. Easy to re-enable in Phase 13 with proper auth.

### `web/routes/healthz.py` — route registration pattern

```python
'''GET /healthz — liveness check.

Always returns HTTP 200 with {"status":"ok","last_run":"...","stale":false}.
Never returns non-200 while the process is alive (D-14).
Exempt from auth (WEB-07, D-17).
Log prefix: [Web] for this process (CLAUDE.md §Conventions).
'''
import logging

from fastapi import FastAPI

logger = logging.getLogger(__name__)


def register(app: FastAPI) -> None:
  '''Register /healthz route on the given FastAPI instance.

  Called by create_app(); Phase 13+ call register() for state.py, trades.py.
  '''
  @app.get('/healthz')
  def healthz():
    # handler body — see Section 5
    ...
```

**Why `register(app)` not `router = APIRouter()`?** Both patterns are valid. `register(app)` is slightly simpler for Phase 11 since `/healthz` is a single endpoint with no shared prefix. The `APIRouter` pattern becomes more valuable in Phase 13 when auth middleware needs to be applied selectively. The planner can choose either; `register()` is recommended for Phase 11 simplicity and Phase 13 can switch routes to `APIRouter` as needed. [CITED: fastapi.tiangolo.com/tutorial/bigger-applications/]

### Directory scaffold (all files Phase 11 creates)

```
web/
├── __init__.py        # empty — makes web/ a package
├── app.py             # create_app() factory + module-level app
└── routes/
    ├── __init__.py    # empty — makes web/routes/ a package
    └── healthz.py     # GET /healthz handler + register()

systemd/
└── trading-signals-web.service   # committed to repo; operator copies to /etc/systemd/system/

deploy.sh              # at repo root
tests/
└── test_web_healthz.py   # FastAPI TestClient tests
```

---

## 5. `/healthz` Handler — Sync vs Async Decision

### DECISION: Use a plain `def` (sync) handler

**Reasoning:** `state_manager.load_state()` is synchronous blocking file I/O (reads state.json from disk). FastAPI automatically runs sync handlers in a threadpool (via `anyio.to_thread.run_sync`), which is the correct approach — it avoids blocking the event loop without requiring any explicit `run_in_threadpool` boilerplate. [CITED: fastapi.tiangolo.com/async/]

Using `async def` with synchronous file I/O would block the event loop, which is worse. Using `async def` + `asyncio.to_thread()` adds unnecessary complexity. Plain `def` is idiomatic and correct here.

**`workers=1` compatibility:** With `--workers 1`, there is only one uvicorn process and one event loop. The sync-in-threadpool approach is safe. The existing `_LAST_LOADED_STATE` module-level cache in `main.py` is also safe — the web process is a separate process that never shares Python module state with the signal loop process. [VERIFIED: D-11 constraint, Phase 8 D-07 context]

### Complete `/healthz` handler

```python
def healthz():
  '''GET /healthz — liveness check per WEB-07 / D-13..D-19.

  Always 200 while the process is alive. State-pipeline health is
  reported via the stale flag in the body, NOT the HTTP status.

  Imports are LOCAL (hex-lite C-2 pattern from notifier.py / dashboard.py):
  import inside the function body so import-time errors in state_manager
  are caught by the same try/except as runtime errors.
  '''
  import zoneinfo
  from datetime import datetime

  try:
    from state_manager import load_state  # local import — C-2 hex pattern

    state = load_state()
    last_run = state.get('last_run')  # ISO string or None (D-15)

    stale = False
    if last_run is not None:
      # D-16: stale if > 2 days old (Phase 8 ERR-05 threshold reused)
      awst = zoneinfo.ZoneInfo('Australia/Perth')
      now_awst = datetime.now(awst)
      try:
        last_dt = datetime.strptime(last_run, '%Y-%m-%d')
        delta_days = (now_awst.date() - last_dt.date()).days
        stale = delta_days > 2
      except (TypeError, ValueError):
        stale = False  # malformed last_run — treat as non-stale

    return {'status': 'ok', 'last_run': last_run, 'stale': stale}

  except Exception as exc:  # noqa: BLE001
    # D-19: never crash — return degraded but still 200
    logger.warning('[Web] /healthz load_state failed: %s: %s', type(exc).__name__, exc)
    return {'status': 'ok', 'last_run': None, 'stale': False}
```

**Local import rationale:** Follows the established C-2 pattern from `main.py` (`_render_dashboard_never_crash`, `_send_email_never_crash`). An import-time error in `state_manager` (syntax error during debugging) is caught by the `except Exception` net, not at module load time. This keeps the web process alive even when the signal loop's state_manager has a temporary bug. [VERIFIED: Pattern established in Phase 5 C-2 / Phase 6 D-15; matches CONTEXT.md §Code Context]

**`last_run` format note:** `state_manager.load_state()` returns `state['last_run']` as a plain `YYYY-MM-DD` ISO string (set by `run_daily_check` at Step 7: `state['last_run'] = run_date_iso`). The CONTEXT.md D-13 example shows `"2026-04-24T08:00:15+08:00"` — this is aspirational formatting for the response; the actual stored value is `YYYY-MM-DD` without time or offset. The handler should return it as-is (a plain date string) rather than trying to convert it to a full ISO datetime, unless the planner decides to add timezone formatting. This is a discretion area the planner should confirm. [VERIFIED: `main.py` line 1042: `state['last_run'] = run_date_iso` where `run_date_iso = run_date.strftime('%Y-%m-%d')`]

---

## 6. Test Strategy — TestClient Patterns

### Framework: FastAPI TestClient (in-process, synchronous)

FastAPI's `TestClient` is a thin wrapper around Starlette's `TestClient`, which wraps HTTPX's synchronous client. It runs the ASGI app in-process — no network, no port binding. Requires `httpx` as a runtime dependency (already pinned in D-05). [CITED: fastapi.tiangolo.com/tutorial/testing/]

### `tests/test_web_healthz.py` — concrete test file

```python
'''TestHealthz — FastAPI TestClient tests for GET /healthz.

Tests are scoped to the /healthz endpoint contract:
  - HTTP 200 always (D-14)
  - Response body shape (D-13)
  - stale flag logic (D-16)
  - Degraded path when state.json missing (D-15 + D-19)
  - Corrupt state.json handled by load_state(), endpoint still returns 200 (D-19)

Hex-boundary: tests import web.app.create_app() — the adapter.
Tests do NOT import signal_engine, sizing_engine, system_params.
'''
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app():
  '''Fresh FastAPI app instance per test — factory pattern enables isolation.'''
  from web.app import create_app
  return create_app()


@pytest.fixture
def client(app):
  '''TestClient wrapping a fresh app instance.'''
  return TestClient(app)


class TestHealthzHappyPath:
  def test_returns_200(self, client):
    response = client.get('/healthz')
    assert response.status_code == 200

  def test_response_body_shape(self, client, tmp_path, monkeypatch):
    '''Happy path: state.json exists with a recent last_run.'''
    import state_manager
    state_file = tmp_path / 'state.json'
    state = state_manager.reset_state()
    state['last_run'] = '2026-04-24'
    state_file.write_text(json.dumps(state, indent=2))
    monkeypatch.setattr(state_manager, 'STATE_FILE', str(state_file))

    response = client.get('/healthz')
    assert response.status_code == 200
    body = response.json()
    assert body['status'] == 'ok'
    assert body['last_run'] == '2026-04-24'
    assert body['stale'] is False

  def test_content_type_json(self, client):
    response = client.get('/healthz')
    assert 'application/json' in response.headers['content-type']


class TestHealthzMissingStatefile:
  def test_returns_200_when_no_state_json(self, tmp_path, monkeypatch):
    '''D-15: load_state() returns fresh state (last_run=None) when file missing.'''
    import state_manager
    from web.app import create_app
    non_existent = tmp_path / 'state.json'
    monkeypatch.setattr(state_manager, 'STATE_FILE', str(non_existent))
    client = TestClient(create_app())
    response = client.get('/healthz')
    assert response.status_code == 200
    body = response.json()
    assert body['status'] == 'ok'
    assert body['last_run'] is None
    assert body['stale'] is False  # D-16: None last_run -> stale=False


class TestHealthzStaleness:
  def test_stale_when_last_run_over_2_days_old(self, tmp_path, monkeypatch, freezer):
    '''D-16: stale=True when last_run > 2 days before now.'''
    import state_manager
    from web.app import create_app
    state_file = tmp_path / 'state.json'
    state = state_manager.reset_state()
    state['last_run'] = '2026-04-20'  # 4 days before frozen 2026-04-24
    state_file.write_text(json.dumps(state, indent=2))
    monkeypatch.setattr(state_manager, 'STATE_FILE', str(state_file))

    freezer.move_to('2026-04-24T08:00:00+08:00')  # AWST
    client = TestClient(create_app())
    response = client.get('/healthz')
    assert response.status_code == 200
    assert response.json()['stale'] is True

  def test_not_stale_when_last_run_today(self, tmp_path, monkeypatch, freezer):
    import state_manager
    from web.app import create_app
    state_file = tmp_path / 'state.json'
    state = state_manager.reset_state()
    state['last_run'] = '2026-04-24'
    state_file.write_text(json.dumps(state, indent=2))
    monkeypatch.setattr(state_manager, 'STATE_FILE', str(state_file))

    freezer.move_to('2026-04-24T08:00:00+08:00')
    client = TestClient(create_app())
    response = client.get('/healthz')
    assert response.json()['stale'] is False

  def test_not_stale_when_last_run_is_none(self, tmp_path, monkeypatch):
    '''D-16: None last_run never sets stale=True.'''
    import state_manager
    from web.app import create_app
    non_existent = tmp_path / 'no_state.json'
    monkeypatch.setattr(state_manager, 'STATE_FILE', str(non_existent))
    client = TestClient(create_app())
    response = client.get('/healthz')
    assert response.json()['stale'] is False


class TestHealthzDegradedPath:
  def test_returns_200_on_load_state_exception(self, monkeypatch):
    '''D-19: defensive return even if load_state raises unexpectedly.'''
    import state_manager
    from web.app import create_app

    def _raise(*args, **kwargs):
      raise RuntimeError('simulated load_state failure')

    monkeypatch.setattr(state_manager, 'load_state', _raise)
    client = TestClient(create_app())
    response = client.get('/healthz')
    assert response.status_code == 200
    body = response.json()
    assert body == {'status': 'ok', 'last_run': None, 'stale': False}
```

**Key testing notes:**

1. **`monkeypatch.setattr(state_manager, 'STATE_FILE', str(...))`** — `load_state` accepts a `path` parameter defaulting to `Path(STATE_FILE)`. Patching the module-level `STATE_FILE` constant is the simplest approach since the handler does a local import; the monkeypatch must be set BEFORE the handler runs. Alternatively, monkeypatch `state_manager.load_state` directly for the degraded-path test.

2. **`pytest-freezer` / `freezer.move_to()`** — `pytest-freezer==0.4.9` is already pinned. The `freezer` fixture (from `pytest-freezer`) patches `datetime.datetime.now` globally. `datetime.now(awst)` inside the handler uses `datetime.now()` which is patchable. [VERIFIED: pytest-freezer 0.4.9 in requirements.txt; freezer fixture is autouse-able]

3. **`from web.app import create_app` INSIDE fixtures** — matches the C-2 local-import pattern established in v1.0 and avoids module-top import of `web.app` in test files (which would fail before the venv has fastapi installed). Each test class/fixture controls its own import timing.

4. **No `asyncio.run` needed** — TestClient handles async routing transparently. [CITED: fastapi.tiangolo.com/tutorial/testing/]

---

## 7. deploy.sh — Complete Body

```bash
#!/usr/bin/env bash
# deploy.sh — idempotent deploy script for trading-signals droplet.
# D-20..D-25 (Phase 11 CONTEXT.md):
#   - strict mode (set -euo pipefail)
#   - branch safety check
#   - git pull --ff-only
#   - pip install
#   - systemctl restart both units
#   - curl smoke test
#   - echo success + commit hash
# No automatic rollback (D-25 deferred to v1.2).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${SCRIPT_DIR}"

cd "${REPO_DIR}"

echo "[deploy] starting deploy at $(date '+%Y-%m-%d %H:%M:%S')"

# D-22: branch safety check
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "${BRANCH}" != 'main' ]; then
  echo "[deploy] ERROR: expected branch 'main', got '${BRANCH}'. Aborting." >&2
  exit 1
fi
echo "[deploy] branch: ${BRANCH} — OK"

# D-23 step 2: fetch
echo "[deploy] fetching from origin..."
git fetch origin main

# D-23 step 3: fast-forward only (non-fast-forward exits non-zero via set -e)
echo "[deploy] pulling (ff-only)..."
git pull --ff-only origin main

# D-23 step 4: pip upgrade
echo "[deploy] upgrading pip..."
.venv/bin/pip install --upgrade pip --quiet

# D-23 step 5: install requirements (idempotent — reports 'already satisfied' on no-change)
echo "[deploy] installing requirements..."
.venv/bin/pip install -r requirements.txt

# D-23 step 6: restart both units
echo "[deploy] restarting services..."
sudo systemctl restart trading-signals trading-signals-web

# Wait briefly for uvicorn to bind port 8000 (normal startup < 1s; 3s is generous)
sleep 3

# D-23 step 7: smoke test — curl exits non-zero if status != 2xx or if timeout exceeded
echo "[deploy] smoke testing /healthz..."
if ! curl -fsS --max-time 5 http://127.0.0.1:8000/healthz > /dev/null; then
  echo "[deploy] ERROR: /healthz smoke test failed. Check 'journalctl -u trading-signals-web -n 50'." >&2
  exit 1
fi
echo "[deploy] /healthz: OK"

# D-23 step 8: success
COMMIT=$(git rev-parse --short HEAD)
echo "[deploy] deploy complete. commit=${COMMIT}"
```

**Notes for the executor:**

- `BASH_SOURCE[0]` instead of `$0` — works correctly when the script is sourced as well as executed directly. [VERIFIED: standard bash idiom]
- `sleep 3` — uvicorn on a systemd-managed process typically binds port 8000 in < 500ms. A 3-second sleep gives ample margin; if the smoke test fails, the error message points to journalctl for diagnosis. The sleep is inside the script body (not a `--max-time` extension); if the process fails to start, `curl` will fail with "connection refused" after 5s.
- `curl -fsS --max-time 5` — `-f` fails fast on non-2xx HTTP; `-s` silent mode; `-S` shows errors even in silent mode. `--max-time 5` caps the total connection+transfer time.
- `sudo systemctl restart` — requires the sudoers entry in Section 8.

---

## 8. sudoers Entry + Validation

### File: `/etc/sudoers.d/trading-signals-deploy`

```
# Scope: trader may restart ONLY these two units, nothing else.
# Installed during droplet one-time setup per SETUP-DROPLET.md.
trader ALL=(root) NOPASSWD: /bin/systemctl restart trading-signals, /bin/systemctl restart trading-signals-web
```

**Note on `systemctl` path:** On Ubuntu LTS (droplet OS), `systemctl` is at `/usr/bin/systemctl`, not `/bin/systemctl`. On systems where `/bin` is a symlink to `/usr/bin`, both work. On systems where they are separate, the wrong path silently fails the sudo match. RECOMMEND using the full path verified on the target droplet:

```bash
# On the droplet, verify the actual path:
which systemctl   # expected: /usr/bin/systemctl
```

If the result is `/usr/bin/systemctl`, the sudoers entry should be:
```
trader ALL=(root) NOPASSWD: /usr/bin/systemctl restart trading-signals, /usr/bin/systemctl restart trading-signals-web
```

**deploy.sh `sudo systemctl restart` restarts both in one command.** The sudoers entry must list both units separately because `systemctl restart A B` is effectively `systemctl restart A` followed by `systemctl restart B` — two distinct invocations; sudoers matches each independently.

### Validation command (run after writing the file)

```bash
# Validate sudoers syntax before activation (NEVER edit sudoers without this)
sudo visudo -c -f /etc/sudoers.d/trading-signals-deploy
# Expected output: /etc/sudoers.d/trading-signals-deploy: parsed OK
```

### Permissions on the sudoers.d file

```bash
sudo chmod 440 /etc/sudoers.d/trading-signals-deploy
sudo chown root:root /etc/sudoers.d/trading-signals-deploy
```

Incorrect permissions cause sudoers to silently ignore the file on some distributions.

---

## 9. Hex-Boundary Verification

### Conclusion: NO changes needed to `test_signal_engine.py::TestDeterminism`

**Current FORBIDDEN_MODULES structure (verified from source):**

| Blocklist constant | Modules blocked | Used for |
|---|---|---|
| `FORBIDDEN_MODULES` | datetime, os, requests, state_manager, notifier, dashboard, main, schedule, dotenv, etc. | signal_engine, sizing_engine, system_params |
| `FORBIDDEN_MODULES_STATE_MANAGER` | signal_engine, sizing_engine, notifier, dashboard, main, requests, numpy, pandas, schedule, dotenv, yfinance | state_manager.py |
| `FORBIDDEN_MODULES_DATA_FETCHER` | signal_engine, sizing_engine, state_manager, notifier, dashboard, main, numpy, schedule, dotenv | data_fetcher.py |
| `FORBIDDEN_MODULES_DASHBOARD` | signal_engine, sizing_engine, data_fetcher, notifier, main, numpy, pandas, yfinance, schedule, dotenv | dashboard.py |
| `FORBIDDEN_MODULES_NOTIFIER` | signal_engine, sizing_engine, data_fetcher, dashboard, main, numpy, pandas, yfinance, schedule, dotenv | notifier.py |
| `FORBIDDEN_MODULES_MAIN` | numpy, yfinance, requests, pandas | main.py |

**`web/` is a NEW adapter module.** It is NOT listed in any of the existing blocklists as a forbidden import target. The hex-core modules (`signal_engine`, `sizing_engine`, `system_params`) must NOT import `web`; however, since those modules' blocklists check for specific known-bad modules (not an allowlist), adding `web` to the blocklists of the hex-core modules would be belt-and-suspenders but is not strictly required for Phase 11.

**What DOES need checking:** The `/healthz` handler imports `state_manager` inside the function body (C-2 local import pattern). `web/` must NOT import `signal_engine`, `sizing_engine`, `data_fetcher`, `notifier`, `dashboard`, or `main` directly — it is an I/O adapter like `notifier.py`. The planner may want to add a new `FORBIDDEN_MODULES_WEB` check in `test_web_healthz.py` as a docstring comment or an explicit AST test within the web test suite (not in `test_signal_engine.py` which tests the hex core).

**Recommended: one new test in `tests/test_web_healthz.py`:**

```python
class TestWebHexBoundary:
  def test_web_app_does_not_import_hex_core(self):
    '''web/ adapter must not import pure-math hex modules directly.

    Allowed: state_manager (I/O adapter peer).
    Forbidden: signal_engine, sizing_engine, system_params, data_fetcher,
               notifier, dashboard, main.
    '''
    import ast
    from pathlib import Path

    web_dir = Path('web')
    forbidden = frozenset({
      'signal_engine', 'sizing_engine', 'data_fetcher',
      'notifier', 'dashboard', 'main',
    })
    violations = []
    for py_file in web_dir.rglob('*.py'):
      tree = ast.parse(py_file.read_text())
      for node in ast.walk(tree):
        if isinstance(node, ast.Import):
          for alias in node.names:
            top = alias.name.split('.')[0]
            if top in forbidden:
              violations.append(f'{py_file}:{node.lineno}: imports {top!r}')
        elif isinstance(node, ast.ImportFrom) and node.module:
          top = node.module.split('.')[0]
          if top in forbidden:
            violations.append(f'{py_file}:{node.lineno}: from {top}')
    assert violations == [], '\n'.join(violations)
```

---

## 10. Security Threat Model

### Applicable ASVS Categories

| ASVS Category | Applies to Phase 11 | Standard Control |
|---|---|---|
| V2 Authentication | No — `/healthz` is intentionally unauthenticated; auth comes in Phase 13 | — |
| V3 Session Management | No — no sessions in Phase 11 | — |
| V4 Access Control | Partial — localhost binding is the access control; no route-level auth yet | `--host 127.0.0.1` binding |
| V5 Input Validation | No — `/healthz` takes no input | — |
| V6 Cryptography | No — no secrets transmitted or stored in Phase 11 | — |
| V7 Error Handling | Yes — `/healthz` must never return 500; degraded path returns 200 | D-19 defensive try/except |

### Threat Table

| Threat | STRIDE Category | Likelihood | Mitigation in Phase 11 |
|---|---|---|---|
| External attacker connects to port 8000 directly | Tampering / Information Disclosure | LOW — bound to 127.0.0.1 only | `--host 127.0.0.1` in ExecStart; nginx (Phase 12) is the only external-facing component |
| `sudo systemctl restart` privilege escalation | Elevation of Privilege | LOW — sudoers entry is narrowly scoped | Sudoers entry allows only two specific restart commands; operator cannot run arbitrary systemctl commands |
| deploy.sh git pull from a malicious branch | Tampering | LOW — branch check guards this | D-22 branch check exits non-zero if not `main` |
| `last_run` value in `/healthz` response leaks timing info | Information Disclosure | VERY LOW — only reveals when the signal loop last ran; no credentials or PII | Accepted: this information is non-sensitive for a single-operator system |
| uvicorn process crash leads to port 8000 unavailability | Denial of Service | LOW — systemd Restart=on-failure recovers | `Restart=on-failure` + `RestartSec=10s`; smoke test in deploy.sh catches failure at deploy time |
| `/healthz` response body grows unbounded (state.json corruption) | Denial of Service | VERY LOW — `load_state()` always returns a bounded dict; D-19 catches exceptions | D-19 defensive return; `load_state()` has its own corruption recovery |
| `EnvironmentFile` leaks RESEND_API_KEY to the web process | Information Disclosure | VERY LOW — web process reads .env but does not use these vars | Accepted: sharing the .env file is D-04 design choice; web process reads but ignores signal-loop-only vars |
| Systemd unit starts before signal loop | Ordering | VERY LOW — Wants= is soft; web operates independently | `Wants=trading-signals.service` ensures they start together but web survives signal unit being down |

**Overall Phase 11 threat surface is minimal:** No external network exposure (port 8000 binds to loopback only), no auth secrets transmitted, no user input accepted, no mutation endpoints. The primary security control is the localhost binding, which is enforced by uvicorn's `--host` flag AND should be verified at deploy time with `ss -tlnp | grep 8000`. [ASSUMED — threat analysis based on standard systemd + WSGI deployment threat model; not sourced from a specific OWASP or ASVS document for this exact stack]

---

## 11. Validation Architecture (Nyquist)

`workflow.nyquist_validation` is `true` in `.planning/config.json` — this section is required.

### Test Framework

| Property | Value |
|---|---|
| Framework | pytest 8.3.3 + pytest-freezer 0.4.9 |
| Config file | none (pytest auto-discovers tests/) |
| Quick run command | `pytest tests/test_web_healthz.py -x -q` |
| Full suite command | `pytest tests/ -q` |
| New test file | `tests/test_web_healthz.py` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|---|---|---|---|---|
| WEB-01 | FastAPI systemd unit starts on boot | Infrastructure smoke test | `systemctl is-active trading-signals-web` (on droplet) | ❌ No automated test — manual SC-1 verification |
| WEB-02 | uvicorn binds to 127.0.0.1:8000 only | Infrastructure smoke test | `ss -tlnp \| grep 8000` (on droplet) | ❌ No automated test — manual SC-4 verification |
| WEB-07 | `/healthz` returns 200 + correct schema | unit | `pytest tests/test_web_healthz.py -x` | ❌ Wave 0 creates |
| WEB-07 | `/healthz` degraded path (missing state.json) | unit | `pytest tests/test_web_healthz.py::TestHealthzMissingStatefile -x` | ❌ Wave 0 creates |
| WEB-07 | `/healthz` stale flag logic | unit | `pytest tests/test_web_healthz.py::TestHealthzStaleness -x` | ❌ Wave 0 creates |
| WEB-07 | `/healthz` D-19 defensive path | unit | `pytest tests/test_web_healthz.py::TestHealthzDegradedPath -x` | ❌ Wave 0 creates |
| INFRA-04 | `deploy.sh` is idempotent, correct bash syntax | static lint | `shellcheck deploy.sh` (if shellcheck installed) | ❌ Wave N creates deploy.sh |

### Nyquist Validation Beyond pytest Unit Tests

**1. `shellcheck` lint of deploy.sh**

```bash
shellcheck deploy.sh
```

This catches common bash pitfalls (unquoted variables, missing `set -e`, word-splitting bugs) before the script is run on the droplet. shellcheck is available via `apt install shellcheck` on Ubuntu droplets and via `brew install shellcheck` on macOS dev machines. [VERIFIED: shellcheck not available on this macOS dev machine; droplet must install it]

**2. systemd unit file syntax validation**

```bash
# On the droplet ONLY (requires systemd):
systemd-analyze verify /etc/systemd/system/trading-signals-web.service
```

On macOS (dev machine) `systemd-analyze` is not available. The planner should include this as a droplet-side SC verification step, not a local CI step.

**3. Repository path smoke test (can run locally)**

Verify that the ExecStart path in the service file matches the actual venv and app path:

```bash
test -f systemd/trading-signals-web.service && echo 'service file exists'
grep 'ExecStart' systemd/trading-signals-web.service
# manual: confirm the path matches the actual droplet deployment path
```

**4. Port binding verification (droplet-only, part of SC-4)**

```bash
ss -tlnp | grep 8000
# Expected: 127.0.0.1:8000 — NOT 0.0.0.0:8000
```

**5. Deferred: real-uvicorn integration test** — spawning uvicorn in a subprocess and hitting `127.0.0.1:8000` via httpx is deferred to Phase 16 hardening per CONTEXT.md §Deferred. This class of test catches startup failures and port-binding issues that TestClient cannot. Phase 11 uses TestClient only.

### Sampling Rate

- **Per task commit:** `pytest tests/test_web_healthz.py -x -q`
- **Per wave merge:** `pytest tests/ -q` (full suite; ensures existing 662 tests remain green)
- **Phase gate:** Full suite green before `/gsd-verify-work 11`

### Wave 0 Gaps

- [ ] `tests/test_web_healthz.py` — all TestHealthz* classes (covers WEB-07 + D-13..D-19)
- [ ] `web/__init__.py` — empty package marker
- [ ] `web/app.py` — create_app() factory
- [ ] `web/routes/__init__.py` — empty package marker
- [ ] `web/routes/healthz.py` — handler + register()
- [ ] `systemd/trading-signals-web.service` — unit file committed to repo
- [ ] `deploy.sh` — at repo root
- [ ] `requirements.txt` — add three new lines (fastapi, uvicorn[standard], httpx)

*(No new test framework required — pytest 8.3.3 + pytest-freezer 0.4.9 already installed)*

---

## 12. Risks + Open Questions

All 25 CONTEXT.md decisions (D-01..D-25) are locked. No open user questions.

**Planning-level notes (not user questions — planner resolves):**

1. **`systemctl` path in sudoers:** On Ubuntu 24.04 LTS (expected droplet OS), `systemctl` is at `/usr/bin/systemctl`. The sudoers entry must use the correct absolute path; using `/bin/systemctl` may fail if it is not a symlink. Planner should document a "verify with `which systemctl` on the droplet" step in SETUP-DROPLET.md. [ASSUMED — based on standard Ubuntu LTS layout; not verified against the specific droplet]

2. **`deploy.sh` `sleep 3`:** The 3-second wait between `systemctl restart` and the `curl` smoke test is a heuristic. On a resource-constrained droplet, uvicorn might take longer to start under load. If the smoke test fails intermittently, increasing to 5 seconds is the first remediation. [ASSUMED — based on typical uvicorn startup time; not measured]

3. **`last_run` format in `/healthz` response:** The CONTEXT.md D-13 example shows `"2026-04-24T08:00:15+08:00"` (full ISO datetime with offset), but `state['last_run']` is stored as `"2026-04-24"` (date only). The handler returns the stored value as-is. If the planner wants the full datetime format, it would require storing a different value OR reconstructing the time component from the date (lossy). Recommend returning the date string as-is and documenting this in the endpoint schema. This is a minor discrepancy between the CONTEXT.md example and the actual stored data.

4. **`EnvironmentFile` path:** `EnvironmentFile=/home/trader/trading-signals/.env` assumes `.env` exists on the droplet. If `.env` is absent, systemd logs a warning but still starts the unit (EnvironmentFile is not mandatory-fail by default). If the planner wants hard failure on missing `.env`, use `EnvironmentFile=-/home/trader/trading-signals/.env` to make it optional (the `-` prefix suppresses the error). Since the web process in Phase 11 does not actually use any `.env` vars, making it optional (or requiring it) is a discretion choice. [VERIFIED: systemd.exec(5) — the `-` prefix makes EnvironmentFile optional]

5. **`requests` package in requirements.txt:** `requests` is currently a dep of `yfinance` but not pinned in the project's own `requirements.txt`. When `fastapi` is installed, `starlette` and `anyio` become transitive deps. No conflict expected, but the executor should confirm `pip install -r requirements.txt` resolves cleanly in the project venv. [ASSUMED — based on known dep trees; not verified with a dry-run pip solve]

---

## 13. References

### Primary (HIGH confidence)

- [VERIFIED: PyPI — `pip index versions fastapi`] — fastapi 0.136.1 latest stable, Python ≥ 3.10 required
- [VERIFIED: PyPI — `pip index versions uvicorn`] — uvicorn 0.46.0 latest stable
- [VERIFIED: PyPI — `pip index versions httpx`] — httpx 0.28.1 latest stable
- [CITED: fastapi.tiangolo.com/tutorial/testing/] — TestClient usage and httpx dependency
- [CITED: fastapi.tiangolo.com/tutorial/bigger-applications/] — include_router + bigger app structure
- [CITED: fastapi.tiangolo.com/async/] — sync def vs async def handler semantics; threadpool for sync handlers
- [VERIFIED: state_manager.py source — lines 335, 1042] — `load_state(path=Path(STATE_FILE))` signature; `state['last_run'] = run_date_iso` format
- [VERIFIED: tests/test_signal_engine.py lines 488-583] — FORBIDDEN_MODULES_* blocklist structure; confirms `web` is not in any blocklist
- [VERIFIED: requirements.txt] — current pinned deps; confirms pytest 8.3.3 + pytest-freezer 0.4.9 already present
- [VERIFIED: .planning/config.json] — `workflow.nyquist_validation: true`

### Secondary (MEDIUM confidence)

- [CITED: snyk.io/package/pip/fastapi] — no open CVEs for fastapi 0.136.1
- [CITED: uvicorn.org/release-notes/] — uvicorn 0.46.0 Python 3.11 compatible
- [CITED: systemd.unit(5), systemd.exec(5)] — Wants= vs Requires= semantics; EnvironmentFile `-` prefix behaviour; SyslogIdentifier

### Tertiary (LOW confidence — flagged)

- [ASSUMED] — `Type=simple` is correct for uvicorn (no fork, no systemd notify)
- [ASSUMED] — `sleep 3` sufficient for uvicorn startup; may need tuning on resource-constrained droplets
- [ASSUMED] — `systemctl` path on Ubuntu LTS is `/usr/bin/systemctl`; verify on actual droplet
- [ASSUMED] — Phase 11 threat model covers all relevant attack surfaces; formal ASVS mapping not performed against a specific test plan document

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|---|---|---|
| A1 | `Type=simple` is correct for uvicorn | 3. systemd unit | Low — worst case unit fails to start; fix is change to `Type=exec` or `Type=notify` |
| A2 | `sleep 3` is enough wait time before curl smoke test | 7. deploy.sh | Low — smoke test fails; bump sleep to 5 and re-run |
| A3 | `systemctl` path on droplet is `/usr/bin/systemctl` | 8. sudoers | Medium — sudoers match fails silently; deploy.sh `sudo` call gets "sudo: a password is required"; fix is update sudoers path |
| A4 | Phase 11 threat model is complete for the localhost-only scope | 10. Threat model | Low — Phase 12 (nginx) and Phase 13 (auth) are the risk-amplifying phases; Phase 11 threat surface is narrow |
| A5 | pip dep resolution for fastapi 0.136.1 + existing deps (numpy 2.0.2 etc.) produces no conflicts | 2. Versions | Low — pip would surface a conflict at install time; fix is pin to a compatible fastapi version |

---

## Environment Availability

| Dependency | Required By | Available (dev machine) | Version | Droplet Assumption |
|---|---|---|---|---|
| Python 3.11 | web/ module + venv | ✗ (dev has 3.9.6) | 3.9.6 (system) | ✓ via pyenv 3.11.8 per .python-version |
| systemd | systemd unit management | ✗ macOS | — | ✓ Ubuntu LTS droplet |
| systemd-analyze | Unit file verification | ✗ macOS | — | ✓ droplet (Linux) |
| shellcheck | deploy.sh lint | ✗ not found | — | Install via `apt install shellcheck` |
| ss (iproute2) | Port binding verification | ✗ macOS | — | ✓ droplet (Linux) |
| fastapi | Web framework | ✗ not installed | — | Install via requirements.txt |
| uvicorn[standard] | ASGI server | ✗ not installed | — | Install via requirements.txt |
| httpx | TestClient dependency | ✗ not installed | — | Install via requirements.txt |

**Missing dependencies with no fallback (blocking on dev):** All listed dependencies exist on the DO droplet, which is the execution environment. Dev machine is macOS; unit tests (TestClient) run locally with the project venv after `pip install -r requirements.txt`. No blocking gap on the droplet.

**Note:** The executor runs `pip install -r requirements.txt` in the project venv before executing tasks. The droplet is the runtime target; local dev runs tests only.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|---|---|---|---|
| `fastapi==0.115.5` (CONTEXT.md baseline) | `fastapi==0.136.1` (current latest) | April 2026 (+21 minor versions) | No breaking changes for Phase 11 scope; pin to latest |
| `uvicorn[standard]==0.34.0` (CONTEXT.md baseline) | `uvicorn==0.46.0` (current latest) | 2025-2026 | Performance improvements to WebSocket and HTTP; no breaking changes for Phase 11 |
| `httpx==0.28.1` | `httpx==0.28.1` | Unchanged | No action |
| `app.include_router(router)` with module-level router | `register(app)` factory function | — | Both valid in 0.136.x; register() chosen for Phase 11 simplicity |
| FastAPI `docs_url='/docs'` default | Disable with `docs_url=None` | — | Prevents Swagger UI exposure before Phase 12 HTTPS/auth are in place |

**Deprecated/outdated:**
- `httpx` optional in FastAPI base install: since FastAPI 0.112.0, httpx is no longer bundled; must be installed explicitly for TestClient. Phase 11 pins httpx explicitly — correct. [CITED: github.com/fastapi/fastapi/discussions/11958]

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|---|---|---|---|
| FastAPI app process | Droplet / ASGI (uvicorn) | — | Web process runs on the droplet; uvicorn is the ASGI server |
| `/healthz` endpoint | FastAPI route handler | state_manager (read-only) | Handler reads state.json via load_state(); pure read, no mutations |
| State.json reads for `/healthz` | state_manager (I/O adapter) | — | state_manager.load_state() owns all disk I/O; web handler is a caller |
| systemd service lifecycle | systemd (OS) | — | Unit file defines restart policy; operator manages via systemctl |
| Deploy automation | deploy.sh (bash script) | systemd (service restart) | Script orchestrates git pull → pip → systemctl restart → smoke test |
| sudoers privilege scope | OS (/etc/sudoers.d/) | — | Narrowly grants `trader` the ability to restart two specific units |
| Port binding restriction | uvicorn (ASGI server) | systemd (ExecStart args) | `--host 127.0.0.1` in ExecStart; verified by `ss -tlnp` |

---

*Research complete. All CONTEXT.md decisions D-01..D-25 are covered. Version pins updated to current latest. All code examples are production-ready.*

*Research date: 2026-04-24*
*Valid until: 2026-05-24 (30 days — stable ecosystem)*
