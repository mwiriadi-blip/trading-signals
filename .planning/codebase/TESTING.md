# Testing Patterns

**Analysis Date:** 2026-05-16

## Test Framework

**Runner:**
- `pytest` v8.0+ (pyproject.toml `minversion = '8.0'`)
- Python 3.13
- Config: `pyproject.toml [tool.pytest.ini_options]`
- Discovery: files `test_*.py`, classes `Test*`, functions `test_*`
- Default addopts: `-ra --strict-markers -m "not uat"` (UAT excluded by default)

**Assertion Library:**
- `assert` statements (builtin); no `assertEqual()`
- Error assertions: `with pytest.raises(ValueError, match='schema mismatch')`

**Run Commands:**
```bash
.venv/bin/pytest -x --tb=short                         # All tests, stop on first failure
.venv/bin/pytest -x --tb=short tests/test_<module>.py  # Single file
.venv/bin/pytest -k "direction_mode" --tb=short        # Pattern match
.venv/bin/pytest -m uat                                # UAT only (hits production droplet)
pytest --cov=signal_engine --cov-report=term-missing   # With coverage
```

## Test File Organization

**Location:** All tests in `tests/` at repo root. File mirrors module: `signal_engine.py` ↔ `test_signal_engine.py`

```
tests/
├── conftest.py                     # Shared fixtures (autouse + named)
├── subprocess_helpers_v12.py       # Shared subprocess test utilities
├── test_signal_engine.py           # Signal engine indicator + vote tests
├── test_sizing_engine.py           # Position sizing, exits, pyramid tests
├── test_state_manager.py           # State persistence, atomicity, migration
├── test_web_*.py                   # Web route tests (FastAPI TestClient)
├── test_auth_store*.py             # Auth store tests
├── test_dashboard.py               # Dashboard rendering tests
├── test_notifier.py                # Email compose + dispatch tests
├── test_backtest_*.py              # Backtest simulator/metrics/CLI tests
├── fixtures/
│   ├── phase2/                     # JSON scenario fixtures for sizing tests
│   ├── backtest/                   # Backtest scenario fixtures
│   ├── fetch/                      # Recorded OHLCV fixtures
│   ├── notifier/                   # Email golden fixtures
│   └── news/                       # News filter fixtures
├── determinism/
│   └── phase2_snapshot.json        # Determinism golden snapshot
├── oracle/
│   ├── wilder.py                   # Pure-loop Wilder reference implementation
│   └── goldens/                    # HTML render goldens
└── uat/
    ├── conftest.py                 # UAT fixtures (Playwright page, base_url)
    ├── test_uat_17_atr_handcalc.py
    ├── test_uat_17_cookie_persistence.py
    ├── test_uat_23_backtest_visual.py
    ├── test_uat_26_coldstart.py
    └── test_uat_26_multitab.py
```

## Test Structure

**Class organization:** one class per concern dimension per phase research conventions

```python
class TestSizing:
  '''D-13: position size = account * risk_pct / stop_dist * vol_scale.'''
  def test_risk_pct_long_is_1pct(self) -> None: ...
  def test_vol_scale_nan_guard(self) -> None: ...

class TestExits:
  '''D-14: stop-hit detection and trailing stop logic.'''
  def test_long_trail_stop_hit_intraday_low(self) -> None: ...

class TestTransitions:
  '''D-15: position transitions (long→short, short→flat, etc.).'''
  @pytest.mark.parametrize('fixture_name', TRANSITION_FIXTURES)
  def test_transition_produces_correct_position(self, fixture_name: str) -> None: ...
```

**Docstrings on test methods:** always present, referencing spec decision labels (D-xx, R-xx):
```python
def test_risk_pct_long_is_1pct(self) -> None:
  '''SIZE-01 LONG branch: account=100000, atr=53, rvol=0.15, mult=5 -> contracts=1.

  Computed: risk_pct=0.01, trail_mult=3.0, stop_dist=53*3*5=795,
  vol_scale=clip(0.12/0.15,0.3,2.0)=0.8, n_raw=(100000*0.01/795)*0.8=1.00629.
  '''
  decision = calc_position_size(account=100000.0, signal=LONG, atr=53.0, rvol=0.15, multiplier=5.0)
  assert decision == SizingDecision(contracts=1, warning=None), decision
```

## Mocking

**Primary tool:** `monkeypatch` (pytest built-in)

**Module-level attribute replacement:**
```python
def test_with_stub(monkeypatch):
  import state_manager
  monkeypatch.setattr(state_manager, 'load_state', lambda *_a, **_kw: stub_state)
  monkeypatch.setattr(state_manager, 'save_state', lambda state, *_a, **_kw: captured.append(dict(state)))
```

**`unittest.mock.patch` legacy:** present in some older test files but `monkeypatch` is preferred (annotated `# noqa: F401 — legacy alias (monkeypatch now preferred)`)

**Custom fake classes for complex behavior:**
```python
class _FakeResponse:
  '''Minimal stand-in for requests.Response.'''
  def __init__(self, status_code: int): self.status_code = status_code

# Usage:
monkeypatch.setattr('notifier.requests.post', lambda *a, **kw: _FakeResponse(200))
```

**Environment variables:**
```python
monkeypatch.setenv('WEB_AUTH_SECRET', 'a' * 32)
monkeypatch.delenv('WEB_AUTH_SECRET', raising=False)  # Tests for missing-var path
```

**What to mock:**
- External I/O: `yfinance.Ticker`, HTTP requests (`notifier.requests.post`)
- State managers: `load_state`, `save_state`, `mutate_state`, `mutate_user_state`
- Environment variables: auth secrets, API keys

**What NOT to mock:**
- Core pure-math logic (`signal_engine`, `sizing_engine`, `pnl_engine`)
- Exception propagation paths (test real exceptions)
- Config parsing and fail-closed validation

## Fixtures and Factories

**`tests/conftest.py` shared fixtures:**

| Fixture | Scope | Purpose |
|---------|-------|---------|
| `_set_web_auth_credentials_for_web_tests` | autouse | Sets `WEB_AUTH_SECRET`, `WEB_AUTH_USERNAME`, `OPERATOR_RECOVERY_EMAIL` for all `test_web_*` and `test_auth_store*` files |
| `valid_cookie_token` | function | Signed `tsi_session` cookie token built with `VALID_SECRET` |
| `valid_pending_token` | function | Signed `tsi_pending` cookie token |
| `valid_enroll_token` | function | Signed `tsi_enroll` cookie token |
| `isolated_auth_json` | function | Redirects `auth_store.DEFAULT_AUTH_PATH` to `tmp_path` |
| `auth_headers` | function | `{AUTH_HEADER_NAME: VALID_SECRET}` dict |
| `htmx_headers` | function | `auth_headers` + `HX-Request: true` |
| `client_with_state_v3` | function | TestClient + `(set_state, captured_saves)` — v12 schema with open SPI200 LONG |
| `client_with_state_v6` | function | TestClient + `(set_state, captured_saves)` — v12 schema, no open positions |
| `pending_invite_auth_json` | function | `auth.json` with admin + one unconsumed invite |
| `multi_user_state_json` | function | `state.json` with 3 users (active/paused/disabled) |

**Key constants in `conftest.py` (import these, do not redefine):**
```python
from tests.conftest import VALID_SECRET, VALID_USERNAME, AUTH_HEADER_NAME
```
Note: `tests/` is NOT on `sys.path` by default — some older test files inline these constants with `# Plan 13-02 Rule 1 deviation pattern` comment explaining why.

**TestClient + state pattern:**
```python
def test_trade_open(client_with_state_v3):
  client, set_state, captured_saves = client_with_state_v3
  set_state({'positions': {'SPI200': None}, ...})  # Seed custom state
  response = client.post('/trades/open', json={...}, headers=auth_headers)
  assert len(captured_saves) == 1        # Exactly one save (atomicity)
  assert captured_saves[0]['positions']['SPI200'] is not None
```

**JSON scenario fixtures:**
```python
PHASE2_FIXTURES_DIR = Path('tests/fixtures/phase2')

def _load_phase2_fixture(name: str) -> dict:
  return json.loads((PHASE2_FIXTURES_DIR / f'{name}.json').read_text())

@pytest.mark.parametrize('fixture_name', TRANSITION_FIXTURES)
def test_transition(self, fixture_name: str) -> None:
  fix = _load_phase2_fixture(fixture_name)
  result = step(fix['prev_position'], fix['bar'], ...)
  assert result == fix['expected']
```

**Regeneration scripts** (for golden/fixture updates):
- `tests/regenerate_goldens.py`
- `tests/regenerate_phase2_fixtures.py`
- `tests/regenerate_dashboard_golden.py`

## Custom Markers

```
uat — live operator-facing UAT scenarios that hit the production droplet
      Run with: pytest -m uat
      Excluded by default: addopts = '-m "not uat"'
```

## Test Types

**Unit tests:**
- Single function/method in isolation
- Minimal fixtures, no real I/O
- Example: `test_signal_engine_direction_mode.py` — calls `get_signal()` directly with synthetic DataFrame

**Integration tests:**
- Multi-layer workflows (fetch → compute → signal, or web route → state mutation)
- Example: `test_web_trades.py` — POST /trades/* via TestClient → assert `captured_saves`

**Scenario/fixture tests:**
- Recorded scenarios loaded from JSON, exercised end-to-end
- Example: `test_sizing_engine.py::TestTransitions` — 9 JSON transition fixtures via `@pytest.mark.parametrize`

**Oracle/determinism tests:**
- Output compared against reference implementation
- `tests/oracle/wilder.py` — pure-loop Wilder smoothing used as ground truth for `test_signal_engine.py::TestDeterminism`

**UAT tests (Playwright):**
- Browser-driven, hit live production droplet
- Marker: `@pytest.mark.uat`
- Requires: `pytest-playwright==0.5.2` from `requirements-dev.txt`; `playwright install chromium`
- Env vars: `UAT_17_DASHBOARD_PATH`, `UAT_17_INSTRUMENT`, `base_url` fixture

## Error Testing Pattern

```python
def test_missing_secret_raises(monkeypatch):
  monkeypatch.delenv('WEB_AUTH_SECRET', raising=False)
  with pytest.raises(RuntimeError, match='WEB_AUTH_SECRET'):
    from web.app import create_app
    create_app()
```

## sys.modules Cache Clearing

Web tests that call `create_app()` must clear the cached module first:
```python
import sys
sys.modules.pop('web.app', None)
from web.app import create_app
```
This prevents test-order-dependent failures from module-level state leaking across tests.

## CI Configuration

No active GitHub Actions CI pipeline found. `daily.yml.disabled` is the only workflow file (disabled). Testing is run locally before commits.

```bash
.venv/bin/pytest -x --tb=short  # Required before any commit
```

## Coverage Gaps

- No enforced coverage percentage target
- UAT scenarios require manual operator trigger against production
- Some older test files duplicate `VALID_SECRET` / `AUTH_HEADER_NAME` constants instead of importing from `conftest` (known limitation — `tests/` not on `sys.path`)

---

*Testing analysis: 2026-05-16*
