# Phase 11: Web Skeleton — FastAPI + uvicorn + systemd — Pattern Map

**Mapped:** 2026-04-24
**Files analyzed:** 10 (8 new, 2 modified/extended)
**Analogs found:** 7 / 10 (3 have no close codebase analog — see §No Analog Found)

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `web/__init__.py` | package marker | — | any existing `tests/__init__.py` | exact (empty file) |
| `web/app.py` | adapter / factory | request-response | `main.py` (orchestrator) + `dashboard.py` (adapter) | role-match |
| `web/routes/__init__.py` | package marker | — | `tests/__init__.py` | exact (empty file) |
| `web/routes/healthz.py` | adapter handler | request-response | `main.py::_render_dashboard_never_crash` + `main.py::_send_email_never_crash` | role-match (C-2 local import pattern) |
| `tests/test_web_healthz.py` | test | request-response | `tests/test_dashboard.py` + `tests/test_main.py` | role-match |
| `requirements.txt` | config | — | existing `requirements.txt` | exact (append pattern) |
| `deploy.sh` | operator script | — | `.github/workflows/daily.yml` (shell sections) | partial-match (only automation surface) |
| `systemd/trading-signals-web.service` | systemd unit | — | no existing `.service` file in repo | no analog |
| `SETUP-DEPLOY-KEY.md` (extend) | operator doc | — | `.planning/phases/10-foundation-v1-0-cleanup-deploy-key/SETUP-DEPLOY-KEY.md` | no analog found — doc does not exist yet |
| `tests/test_signal_engine.py` | test (confirm no change) | — | itself | exact (read-only confirm) |

---

## Pattern Assignments

### `web/__init__.py` and `web/routes/__init__.py` (package markers)

**Analog:** `tests/__init__.py`

Both are empty package markers. Copy the existing empty `tests/__init__.py`:

**Pattern** (`tests/__init__.py`, line 1 — file is empty):
```python
```

These two files are empty. No imports, no content.

---

### `web/app.py` (adapter, request-response)

**Analog:** `main.py` (orchestrator wiring) + `dashboard.py` (hex adapter docstring pattern)

**Docstring pattern** (`dashboard.py` lines 1-67):
The existing adapter modules (`dashboard.py`, `notifier.py`) open with a comprehensive docstring that declares:
- what the module owns and exposes
- which hex-boundary imports are allowed/forbidden
- the AST blocklist that enforces the boundary
- the "never-crash posture" if applicable

Copy this docstring pattern for `web/app.py`.

**Module-level logger pattern** (`dashboard.py` lines 105-106):
```python
logger = logging.getLogger(__name__)
```

**Import pattern for an adapter module** (`dashboard.py` lines 67-100):
For `web/app.py`, the imports are minimal — only `fastapi` and `web.routes.healthz`. Do NOT import `state_manager` at the module top of `web/app.py`; state reading happens inside the handler (C-2 local import, see `healthz.py` below).

**Factory pattern** (RESEARCH.md §4, lines 206-224 — no codebase analog; use RESEARCH.md):
```python
from fastapi import FastAPI

from web.routes import healthz as healthz_route


def create_app() -> FastAPI:
  application = FastAPI(
    title='Trading Signals',
    description='SPI 200 & AUD/USD mechanical trading signal system',
    version='1.1.0',
    docs_url=None,
    redoc_url=None,
  )
  healthz_route.register(application)
  return application


app = create_app()
```

**Key conventions to match:**
- 2-space indent (CLAUDE.md §Conventions)
- Single quotes (CLAUDE.md §Conventions)
- `[Web]` log prefix for any `logger.info/warning` calls (CLAUDE.md §Conventions — new prefix for Phase 11)
- `docs_url=None` and `redoc_url=None` — no Swagger UI before Phase 12/13 auth

---

### `web/routes/healthz.py` (adapter handler, request-response)

**Analog:** `main.py::_render_dashboard_never_crash` (lines 111-129) and `main.py::_send_email_never_crash` (lines 136-176)

These are the canonical C-2 local-import + never-crash patterns in this codebase.

**C-2 local import pattern** (`main.py` lines 114-129):
```python
def _render_dashboard_never_crash(state: dict, out_path: Path, now: datetime) -> None:
  '''D-06: dashboard render failure never crashes the run.

  C-2 reviews: `import dashboard` lives INSIDE the helper body (not at
  module top) so import-time errors in dashboard.py — syntax errors,
  bad sub-imports, circular-import bugs — are caught by the SAME
  `except Exception` that catches runtime render failures. Without
  this, an import-time dashboard error takes down main.py at module
  load time, before the helper even runs.
  '''
  try:
    import dashboard  # local import — C-2 isolates import-time failures
    dashboard.render_dashboard(state, out_path, now=now)
  except Exception as e:
    logger.warning('[Dashboard] render failed: %s: %s', type(e).__name__, e)
```

**Apply this pattern to `/healthz` handler.** The `from state_manager import load_state` goes INSIDE the `healthz()` function body, not at module top. The module-top `import logging` and `logger = logging.getLogger(__name__)` are fine at module level (they never fail).

**Logger declaration** (`dashboard.py` line 106 — apply same pattern):
```python
import logging

from fastapi import FastAPI

logger = logging.getLogger(__name__)
```

**register() function shape** (RESEARCH.md §4 — no codebase analog):
```python
def register(app: FastAPI) -> None:
  @app.get('/healthz')
  def healthz():
    # local imports + try/except body here
    ...
```

**Complete handler body** (RESEARCH.md §5):
The handler uses `zoneinfo` (stdlib, Python 3.9+) and `datetime` imported inside the function for AWST time calculation. Follow the C-2 pattern exactly:
```python
def healthz():
  import zoneinfo
  from datetime import datetime

  try:
    from state_manager import load_state  # local import — C-2 hex pattern

    state = load_state()
    last_run = state.get('last_run')  # ISO 'YYYY-MM-DD' string or None (D-15)

    stale = False
    if last_run is not None:
      awst = zoneinfo.ZoneInfo('Australia/Perth')
      now_awst = datetime.now(awst)
      try:
        from datetime import date as _date
        last_dt = _date.fromisoformat(last_run)
        delta_days = (now_awst.date() - last_dt).days
        stale = delta_days > 2
      except (TypeError, ValueError):
        stale = False

    return {'status': 'ok', 'last_run': last_run, 'stale': stale}

  except Exception as exc:  # noqa: BLE001
    # D-19: never crash — return degraded but still 200
    logger.warning('[Web] /healthz load_state failed: %s: %s', type(exc).__name__, exc)
    return {'status': 'ok', 'last_run': None, 'stale': False}
```

**Log prefix:** `[Web]` per CLAUDE.md §Conventions (new prefix for Phase 11; existing prefixes are `[Signal]`, `[State]`, `[Email]`, `[Sched]`, `[Fetch]`).

**state_manager.load_state() signature** (`state_manager.py` line 335):
```python
def load_state(path: Path = Path(STATE_FILE), now=None) -> dict:
```
The handler calls `load_state()` with no args; it uses the module-level `STATE_FILE` constant. Monkeypatching `state_manager.STATE_FILE` in tests is the correct approach (see test pattern below).

**`last_run` actual format:** `state_manager.py` stores `state['last_run']` as a plain `YYYY-MM-DD` string (not a full ISO datetime with offset). The `/healthz` handler returns it as-is. The CONTEXT.md D-13 example showing `"2026-04-24T08:00:15+08:00"` is aspirational; the real stored value is `"2026-04-24"`.

---

### `tests/test_web_healthz.py` (test, request-response)

**Analog 1:** `tests/test_dashboard.py` (class-per-concern structure, module-level path constants, `tmp_path` isolation)
**Analog 2:** `tests/test_main.py` (freezer fixture mention, monkeypatch.setattr patterns)
**Analog 3:** `tests/test_state_manager.py` (monkeypatch of module-level constants)

**Class-per-concern structure** (`tests/test_dashboard.py` lines 1-30):
The project consistently uses one class per concern dimension with a docstring describing the concern. Copy this exact structure:
```python
class TestHealthzHappyPath:     # D-13..D-15: basic contract
class TestHealthzMissingStatefile:  # D-15: missing state.json
class TestHealthzStaleness:     # D-16: stale flag logic
class TestHealthzDegradedPath:  # D-19: exception in load_state
class TestWebHexBoundary:       # AST guard — web/ does not import hex core
```

**Module-level path constants** (`tests/test_dashboard.py` lines 52-59):
```python
DASHBOARD_PATH = Path('dashboard.py')
TEST_DASHBOARD_PATH = Path('tests/test_dashboard.py')
```
Apply same pattern for web tests:
```python
WEB_APP_PATH = Path('web/app.py')
WEB_HEALTHZ_PATH = Path('web/routes/healthz.py')
TEST_WEB_HEALTHZ_PATH = Path('tests/test_web_healthz.py')
```

**monkeypatch.setattr for module constant** (`tests/test_state_manager.py` lines 456-460 and `tests/test_main.py` line 1771):
```python
# Pattern 1: patch a module-level constant (used in test_state_manager.py)
monkeypatch.setattr(state_manager, '_migrate', bad_migrate)

# Pattern 2: patch via string target (used in test_main.py)
monkeypatch.setattr('state_manager.save_state', lambda s, path=None: None)
```
For `/healthz` tests, use Pattern 1 to patch `STATE_FILE`:
```python
import state_manager
monkeypatch.setattr(state_manager, 'STATE_FILE', str(tmp_path / 'state.json'))
```

**pytest-freezer fixture** (`tests/test_main.py` lines 7-8 and RESEARCH.md §6):
pytest-freezer 0.4.9 is already pinned. The `freezer` fixture is automatically available — no import needed. Use in test method signatures:
```python
def test_stale_when_last_run_over_2_days_old(self, tmp_path, monkeypatch, freezer):
    freezer.move_to('2026-04-24T08:00:00+08:00')
```
Note: Existing tests in this codebase use `now=` injection for determinism (no `freezer` in method signatures yet). Phase 11's `/healthz` handler uses `datetime.now(awst)` internally (not injectable), so `freezer` is the correct approach for staleness tests.

**`@pytest.fixture` scoping** (`tests/test_main.py` lines 1754-1758):
```python
@pytest.fixture
def _ctx(self, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ...
```
Phase 11 uses module-level fixtures for `app` and `client` (not class-level), matching the RESEARCH.md §6 pattern. This is consistent with FastAPI TestClient idiom.

**Local import inside fixtures** (RESEARCH.md §6 + C-2 pattern):
```python
@pytest.fixture
def app():
    from web.app import create_app  # local import — avoids top-level import failure before venv ready
    return create_app()
```

**reset_state() usage** (`state_manager.py` line 304):
```python
def reset_state() -> dict:
    '''STATE-07: fresh state, $100k account, empty collections.'''
```
Tests use `state_manager.reset_state()` to build the base dict, then mutate:
```python
state = state_manager.reset_state()
state['last_run'] = '2026-04-24'
state_file.write_text(json.dumps(state, indent=2))
```

---

### `requirements.txt` (config, append pattern)

**Analog:** existing `requirements.txt` (lines 1-9)

```
PyYAML==6.0.2
numpy==2.0.2
pandas==2.3.3
python-dotenv==1.0.1
pytest==8.3.3
pytest-freezer==0.4.9
ruff==0.6.9
schedule==1.2.2
yfinance==1.2.0
```

**Append pattern:** exact pins, no `>=`, no `~=` (CLAUDE.md §Stack). Add 3 lines, maintaining alphabetical order is not required (existing file is not alphabetical). Add after `yfinance==1.2.0`:
```
fastapi==0.136.1
uvicorn[standard]==0.46.0
httpx==0.28.1
```
Note: `pytz` is a transitive dep already used by `yfinance` and explicitly used by `dashboard.py`/`notifier.py` but not currently pinned in `requirements.txt`. Phase 11 does not add `pytz` explicitly — the handler uses `zoneinfo` (stdlib) instead of `pytz` to avoid a new pin.

---

### `deploy.sh` (operator script, bash)

**Analog:** `.github/workflows/daily.yml` shell sections (lines 28-36) — the only existing automation surface in the repo.

**GHA workflow bash style** (`.github/workflows/daily.yml` lines 28-36):
```yaml
- name: Install deps
  run: |
    python -m pip install --upgrade pip
    pip install -r requirements.txt

- name: Run daily check
  env:
    RESEND_API_KEY:   ${{ secrets.RESEND_API_KEY }}
    SIGNALS_EMAIL_TO: ${{ secrets.SIGNALS_EMAIL_TO }}
  run: python main.py --once
```
The GHA YAML uses bare shell without `set -euo pipefail` (GHA provides its own error handling). `deploy.sh` must add `set -euo pipefail` explicitly per D-20.

**deploy.sh has no existing analog in the repo.** Use RESEARCH.md §7 as the authoritative shape. Style conventions from GHA YAML and CLAUDE.md:
- `[deploy]` log prefix on human-readable echo lines (D-25 / CONTEXT §Claude's Discretion)
- Exact same `pip install --upgrade pip && pip install -r requirements.txt` sequence as GHA (lines 28-31)
- `BASH_SOURCE[0]` for script-directory detection (standard bash idiom)

**Full body** (RESEARCH.md §7, lines 494-557 — authoritative, copy verbatim):
```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${SCRIPT_DIR}"
cd "${REPO_DIR}"

echo "[deploy] starting deploy at $(date '+%Y-%m-%d %H:%M:%S')"

BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "${BRANCH}" != 'main' ]; then
  echo "[deploy] ERROR: expected branch 'main', got '${BRANCH}'. Aborting." >&2
  exit 1
fi
echo "[deploy] branch: ${BRANCH} — OK"

echo "[deploy] fetching from origin..."
git fetch origin main

echo "[deploy] pulling (ff-only)..."
git pull --ff-only origin main

echo "[deploy] upgrading pip..."
.venv/bin/pip install --upgrade pip --quiet

echo "[deploy] installing requirements..."
.venv/bin/pip install -r requirements.txt

echo "[deploy] restarting services..."
sudo systemctl restart trading-signals trading-signals-web

sleep 3

echo "[deploy] smoke testing /healthz..."
if ! curl -fsS --max-time 5 http://127.0.0.1:8000/healthz > /dev/null; then
  echo "[deploy] ERROR: /healthz smoke test failed. Check 'journalctl -u trading-signals-web -n 50'." >&2
  exit 1
fi
echo "[deploy] /healthz: OK"

COMMIT=$(git rev-parse --short HEAD)
echo "[deploy] deploy complete. commit=${COMMIT}"
```

---

### `systemd/trading-signals-web.service` (systemd unit)

**No existing analog in repo.** v1.0 Phase 7 explicitly did NOT create a systemd unit (Phase 7 CONTEXT.md line 330: "No systemd unit file for Linux deployment"). The hardening directives in CONTEXT.md D-10 define the pattern from scratch.

Use RESEARCH.md §3 (lines 117-148) as the authoritative template — copy verbatim:

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

**Critical notes for executor:**
- `--host 127.0.0.1` is mandatory (never `0.0.0.0`) per D-11
- `--workers 1` is mandatory per D-11 (preserves `_LAST_LOADED_STATE` assumption from Phase 8 D-07)
- `Wants=` not `Requires=` per D-09 (soft dependency — web survives signal unit being down)
- `SyslogIdentifier=trading-signals-web` enables `journalctl -u trading-signals-web` filtering

---

### `SETUP-DROPLET.md` (operator doc extension)

**Analog:** The SETUP-DEPLOY-KEY.md referenced in Phase 10 does not yet exist in the repo (confirmed: `Glob(".planning/phases/10-*/SETUP*")` returned no results). Phase 11 creates a new `SETUP-DROPLET.md` companion doc.

**Style reference:** `.github/workflows/daily.yml` and `.planning/milestones/v1.0-phases/07-*/07-CONTEXT.md` operator runbook sections. Convention: bash code blocks with `# comments`, sectioned by responsibility.

**Sudoers entry** (RESEARCH.md §8 — note: use `/usr/bin/systemctl` on Ubuntu 24.04 LTS, verify path on droplet):
```
# Scope: trader may restart ONLY these two units, nothing else.
trader ALL=(root) NOPASSWD: /usr/bin/systemctl restart trading-signals, /usr/bin/systemctl restart trading-signals-web
```

---

### `tests/test_signal_engine.py` (confirm no change)

**Status:** No change needed. Verified via RESEARCH.md §9 (lines 615-628): `web/` is a new adapter module not listed in any `FORBIDDEN_MODULES_*` blocklist. The blocklists check specific known-bad module names; `web` is not in any of them. The hex-core modules (`signal_engine`, `sizing_engine`, `system_params`) must not import `web`, but since `web` is new there is no existing import to block.

The planner should include a confirmatory grep in the plan:
```bash
grep -n 'web' tests/test_signal_engine.py
```
Expected: zero matches (confirming no update needed).

---

## Shared Patterns

### C-2 Local Import Pattern (hex boundary enforcement)
**Source:** `main.py` lines 111-129 (`_render_dashboard_never_crash`)
**Apply to:** `web/routes/healthz.py` handler body

The C-2 pattern places adapter-to-adapter imports (`from state_manager import load_state`) INSIDE the function body, not at module top. This ensures import-time errors in `state_manager` are caught by the same `except Exception` that catches runtime failures. The pattern is established in Phase 5 and reused by every adapter function that calls into another adapter.

```python
try:
    import <module>  # local import — C-2 isolates import-time failures
    <module>.function(...)
except Exception as e:
    logger.warning('[Prefix] action failed: %s: %s', type(e).__name__, e)
```

### Never-Crash Posture
**Source:** `main.py` lines 121-129 and 155-176
**Apply to:** `web/routes/healthz.py`

The `/healthz` endpoint must NEVER return non-200 while the FastAPI process is alive (D-14/D-19). Any exception from `load_state()` returns `{'status': 'ok', 'last_run': None, 'stale': False}` with 200. This mirrors `_render_dashboard_never_crash` and `_send_email_never_crash` — the web process's cosmetic/diagnostic output never aborts the process.

### Log Prefix Convention
**Source:** `CLAUDE.md` §Conventions
**Apply to:** `web/app.py`, `web/routes/healthz.py`, all future `web/` modules

Existing prefixes: `[Signal]`, `[State]`, `[Email]`, `[Sched]`, `[Fetch]`
New prefix for Phase 11: `[Web]`

Usage:
```python
logger.info('[Web] starting up')
logger.warning('[Web] /healthz load_state failed: %s: %s', type(exc).__name__, exc)
```

### Module Logger Declaration
**Source:** `dashboard.py` line 106
**Apply to:** All `web/` modules that log

```python
logger = logging.getLogger(__name__)
```

### Exact Version Pins in requirements.txt
**Source:** `requirements.txt` lines 1-9 + `CLAUDE.md` §Stack
**Apply to:** `requirements.txt` additions

No `>=`, no `~=`, no `^`. Exact pins only. Phase 11 adds:
```
fastapi==0.136.1
uvicorn[standard]==0.46.0
httpx==0.28.1
```

### Class-Per-Concern Test Structure
**Source:** `tests/test_dashboard.py` lines 1-24, `tests/test_state_manager.py` lines 1-15
**Apply to:** `tests/test_web_healthz.py`

One class per concern dimension. Each class has a docstring naming the requirements it covers.

### tmp_path Isolation in Tests
**Source:** `tests/test_dashboard.py` line 18, `tests/test_state_manager.py` line 8
**Apply to:** All `test_web_healthz.py` tests that write to disk

```python
# NEVER write to real state.json or dashboard.html
# Always use tmp_path for isolated test artifacts
def test_something(self, tmp_path, monkeypatch):
    state_file = tmp_path / 'state.json'
    ...
```

---

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `systemd/trading-signals-web.service` | systemd unit | — | No systemd unit files exist in the repo. v1.0 Phase 7 explicitly excluded systemd. Use RESEARCH.md §3 as authoritative template. |
| `SETUP-DROPLET.md` | operator doc | — | No existing operator setup docs found under `.planning/phases/10-*/SETUP*`. Create new document from scratch following the style of `.planning/milestones/v1.0-phases/07-*/07-CONTEXT.md` operator runbook sections. |
| `deploy.sh` | operator script | — | No existing deploy scripts in the repo. `.github/workflows/daily.yml` provides style reference for pip/python invocation patterns. Use RESEARCH.md §7 as authoritative body. |

---

## Metadata

**Analog search scope:** repo root `*.py`, `tests/*.py`, `.github/workflows/*.yml`, `.planning/milestones/v1.0-phases/07-*/`, `.planning/phases/10-*/`
**Files scanned:** `dashboard.py`, `notifier.py` (grep), `main.py` (lines 107-176), `state_manager.py` (lines 298-396), `requirements.txt`, `tests/test_dashboard.py` (lines 1-80), `tests/test_state_manager.py` (lines 1-93), `tests/test_main.py` (lines 1-50, 1749-1909), `.github/workflows/daily.yml`
**Pattern extraction date:** 2026-04-24
