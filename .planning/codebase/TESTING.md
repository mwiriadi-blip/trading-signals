# Testing Patterns

**Analysis Date:** 2026-05-15

## Test Framework

**Runner:**
- `pytest` v8.0+ (pyproject.toml `minversion = '8.0'`)
- Python 3.13
- Config: `.planning` via `pyproject.toml [tool.pytest.ini_options]`
- Test discovery: files matching `test_*.py`, classes `Test*`, functions `test_*`

**Run Commands:**
```bash
.venv/bin/pytest -x --tb=short                    # Run all tests, stop on first failure
.venv/bin/pytest -x --tb=short tests/test_<module>.py  # Run single test file
pytest tests/test_signal_engine.py::TestDeterminism::test_atr_matches_oracle  # Single test
pytest -k "direction_mode" --tb=short             # Run tests matching pattern
pytest -m "not uat"                               # Exclude UAT tests (default)
pytest -m uat                                     # Run only UAT tests (operator-facing)
```

**Assertion Library:**
- `assert` statements (builtin); no `assertEqual()` or `assertRaises()`
- Comparison assertions use `==`, `!=`, `<`, `>`, `<=`, `>=`
- Truth assertions use `assert x is None`, `assert x is not None`, `assert x`

## Test File Organization

**Location:**
- All tests in `tests/` directory at repo root
- Co-located with source (not separate tree) — test file mirrors module name: `signal_engine.py` ↔ `test_signal_engine.py`
- Fixtures live in `tests/fixtures/<module>/` subdirs (e.g., `tests/fixtures/phase2/`)
- Determinism snapshots in `tests/determinism/` (e.g., `phase2_snapshot.json`)
- Golden/oracle files in `tests/oracle/` (e.g., `wilder.py` — pure-loop reference implementation)

**Naming:**
- Test files: `test_<module>.py` (e.g., `test_signal_engine.py`, `test_data_fetcher.py`)
- Test classes: `Test<Concern>` grouping related tests (e.g., `TestDeterminism`, `TestRiskCalculation`, `TestFetch`, `TestColumnShape`)
- Test functions: `test_<behavior_or_spec>` — descriptive, reads like a sentence (e.g., `test_risk_pct_long_is_1pct`, `test_vol_scale_nan_guard`, `test_get_signal_long_only_blocks_short_votes`)

**Structure:**
```
tests/
├── test_signal_engine.py          # Signal phase tests
├── test_sizing_engine.py          # Sizing phase tests (organized by class)
├── test_data_fetcher.py           # Data fetch tests (offline, monkeypatched yf.Ticker)
├── test_web_*.py                  # Web layer tests (depend on conftest fixtures)
├── conftest.py                    # Shared fixtures (autouse + named)
├── fixtures/
│   ├── phase2/                    # JSON scenario fixtures for sizing tests
│   │   ├── transition_long_to_long.json
│   │   ├── pyramid_gap_crosses_both_levels_caps_at_1.json
│   │   └── ...
│   └── fetch/                     # Recorded OHLCV fixtures for data_fetcher tests
│       ├── spi200_2020_2026.json
│       └── ...
├── determinism/
│   └── phase2_snapshot.json       # Determinism golden snapshot
├── oracle/
│   ├── wilder.py                  # Pure-loop Wilder-smoothing reference
│   └── goldens/
│       └── golden_empty.html      # HTML render golden for xfail tests
└── subprocess_helpers_v12.py      # Shared test utilities
```

## Test Structure

**Suite Organization:**
Classes group tests by concern dimension per Phase research patterns:

```python
class TestDeterminism:
  '''D-08: determinism oracle — signal output stable across runs.
  Compares output against test/oracle/wilder.py reference.
  '''
  def test_atr_matches_oracle(self) -> None: ...
  def test_adx_matches_oracle(self) -> None: ...

class TestRiskCalculation:
  '''D-13 size calculation + vol scaling.'''
  def test_risk_pct_long_is_1pct(self) -> None: ...
  def test_trail_mult_by_direction(self) -> None: ...

class TestFetch:
  '''D-13 yfinance retry + error handling (offline via monkeypatch).'''
  def test_retry_on_rate_limit(self) -> None: ...
  def test_empty_frame_exhausts_retries(self) -> None: ...
```

**Test setup/teardown:**
- Fixtures preferred over setUp/tearDown methods (pytest style)
- Autouse fixtures in `conftest.py` for cross-cutting setup (e.g., `_set_web_auth_credentials_for_web_tests`)
- Function-scoped fixtures for test-specific state (default scope)
- Session/module-scoped fixtures for expensive data (e.g., loading oracle snapshots once per module)

**Assertion patterns:**
Assertions include descriptive failure messages:
```python
def test_risk_pct_long_is_1pct(self) -> None:
  '''SIZE-01 LONG branch: account=100000, atr=53, rvol=0.15, mult=5 -> contracts=1.
  
  Computed: risk_pct=0.01, trail_mult=3.0, stop_dist=53*3*5=795,
  vol_scale=clip(0.12/0.15,0.3,2.0)=0.8, n_raw=(100000*0.01/795)*0.8=1.00629,
  int(1.00629)=1.
  '''
  decision = calc_position_size(
    account=100000.0, signal=LONG, atr=53.0, rvol=0.15, multiplier=5.0,
  )
  assert decision == SizingDecision(contracts=1, warning=None), decision
```

## Mocking

**Framework:** `monkeypatch` (pytest built-in) for isolation + custom FakeX classes for complex behavior

**Patterns:**

### Monkeypatch for module-level replacements:
```python
def test_with_stub(monkeypatch):
  import state_manager
  monkeypatch.setattr(state_manager, 'load_state', lambda *_a, **_kw: stub_state)
  # Now calls to state_manager.load_state() use the stub
```

### FakeTicker for yfinance retry testing:
```python
class _FakeTicker:
  '''Drop-in for yfinance.Ticker. Behaviour list controls what each .history() call returns.'''
  def __init__(self, symbol: str, behaviour, call_count: list) -> None:
    self.symbol = symbol
    self._behaviour = behaviour  # list of (exc_or_df) entries
    self._call_count = call_count

  def history(self, **kwargs):
    self._call_count.append(1)
    idx = min(len(self._call_count) - 1, len(self._behaviour) - 1)
    item = self._behaviour[idx]
    if isinstance(item, Exception):
      raise item
    return item

# Usage in test:
def test_retry_on_rate_limit(monkeypatch):
  behaviour = [YFRateLimitError(), recorded_df]  # Fail once, succeed
  call_count = []
  factory = _make_fake_ticker_factory(behaviour, call_count)
  monkeypatch.setattr('data_fetcher.yf.Ticker', factory)
  df = fetch_ohlcv('SPI200')
  assert len(call_count) == 2  # Retried once
```

**What to Mock:**
- External I/O: `yfinance.Ticker`, HTTP requests, file reads (use fixtures instead)
- State managers: `load_state`, `save_state` → test with stubs (see `conftest.py::client_with_state_v3`)
- DateTime: clock reads (use `monkeypatch.setenv('NOW_OVERRIDE', ...)` pattern)
- Environment variables: `monkeypatch.setenv('VAR_NAME', value)`

**What NOT to Mock:**
- Core logic functions (test the real `signal_engine.get_signal`, `sizing_engine.calc_position_size`)
- Math operations (test with real pandas/numpy)
- Error paths (test real exceptions, not stubs)
- Configuration loading (test real config parsing, fail-closed validation)

## Fixtures and Factories

**Test Data:**

### JSON scenario fixtures:
```python
def _load_phase2_fixture(name: str) -> dict:
  '''Load a Phase 2 JSON scenario fixture.'''
  import json
  path = PHASE2_FIXTURES_DIR / f'{name}.json'
  return json.loads(path.read_text())

# Tests reference by name:
def test_transition_long_to_short(self) -> None:
  fix = _load_phase2_fixture('transition_long_to_short')
  prev = fix['prev_position']
  bar = fix['bar']
  # ... assertions on expected vs actual
```

### Shared auth fixtures (conftest.py):
```python
@pytest.fixture
def valid_cookie_token() -> str:
  '''Phase 16.1: tsi_session-shaped signed token built with VALID_SECRET.'''
  from itsdangerous.url_safe import URLSafeTimedSerializer
  serializer = URLSafeTimedSerializer(VALID_SECRET, salt='tsi-session-cookie')
  return serializer.dumps({'u': VALID_USERNAME, 'iat': int(time.time())})

# Usage:
def test_cookie_auth(client, valid_cookie_token):
  response = client.get('/', cookies={'tsi_session': valid_cookie_token})
  assert response.status_code == 200
```

### TestClient + state fixture:
```python
@pytest.fixture
def client_with_state_v3(monkeypatch):
  '''Yields (client, set_state, captured_saves) tuple.
  Default seed: v3-schema state with one open SPI200 LONG position.
  Tests adjust via set_state().
  '''
  # ... monkeypatches load_state, save_state, mutate_state
  # ... returns (client, set_state, captured_saves)
  return client, set_state, captured_saves

# Usage:
def test_trade_open(client_with_state_v3):
  client, set_state, captured_saves = client_with_state_v3
  set_state({'positions': {'SPI200': None}})  # No open position
  response = client.post('/trades/open', json={'instrument': 'SPI200', ...})
  assert len(captured_saves) == 1  # Exactly one save
  assert captured_saves[0]['positions']['SPI200'] is not None  # Trade opened
```

**Location:**
- Fixtures live in `tests/conftest.py` (shared across all tests)
- JSON scenarios in `tests/fixtures/<module>/` (loaded by helper functions in test files)
- Golden snapshots in `tests/determinism/` and `tests/oracle/goldens/`

## Coverage

**Requirements:** No explicit percentage target enforced by CI; codemoot review flags untested code paths

**View Coverage:**
```bash
pytest --cov=signal_engine --cov=sizing_engine --cov-report=term-missing
```

**Missing coverage flags:**
- `tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent` — AST walk to catch hex-boundary violations
- `tests/test_http_timeouts.py` — AST regression checking HTTP_TIMEOUT_S single-source-of-truth constraint
- `tests/test_secret_redaction.py` — Verify all secrets flow through `redact_secret()` before logging

## Test Types

**Unit Tests:**
- Scope: Single function or class method
- Example: `test_risk_pct_long_is_1pct` tests `calc_position_size()` in isolation
- Setup: Minimal fixtures, no I/O
- Offline: All external calls mocked or stubbed

**Integration Tests:**
- Scope: Multi-function workflows (e.g., fetch → compute indicators → signal)
- Example: `test_sizing_decision_fixture` exercises full Phase 2 step() call
- Setup: More complex fixtures (state stubs, recorded OHLCV data)
- Mixed: Some real logic (signal_engine + sizing_engine), stubbed I/O (state_manager.load_state)

**Scenario Tests:**
- Scope: Full orchestration path with recorded scenarios
- Example: `TRANSITION_FIXTURES` in `test_sizing_engine.py` — 9 position-transition scenarios
- Setup: Loaded from JSON (tests/fixtures/phase2/*.json)
- Validation: Assert individual step outcomes (sizing, stop_hit, pyramid) against fixture expectations

**E2E Tests:**
- Scope: Full API request → response cycles (web routes)
- Example: `test_web_routes_*.py` classes test GET/POST handlers end-to-end
- Setup: `client_with_state_v3` fixture (TestClient + mocked state_manager)
- Validation: Assert HTTP status, response body shape, state mutations

**UAT Tests:**
- Scope: Operator-facing scenarios hitting production droplet
- Marker: `@pytest.mark.uat` (excluded by default; run with `pytest -m uat`)
- Location: Scattered per phase (e.g., test_web_routes_totp.py has UAT paths for TOTP enrollment)
- Run: Only on operator sign-off, not in CI

## Common Patterns

**Async Testing:**
Not used (trading-signals is synchronous). Async fixtures and async test functions not employed.

**Error Testing:**
```python
def test_missing_secret_raises_runtime_error(monkeypatch):
  '''Phase 13 D-17: missing WEB_AUTH_SECRET raises RuntimeError at boot.'''
  monkeypatch.delenv('WEB_AUTH_SECRET', raising=False)
  with pytest.raises(RuntimeError, match='WEB_AUTH_USERNAME env var is missing'):
    from web.app import create_app
    create_app()
```

**Exception context chaining:**
```python
def test_fetch_data_fetcher_error_wraps_yfinance(monkeypatch):
  '''D-01: DataFetchError wraps yfinance/network errors for orchestrator.'''
  behaviour = [ConnectionError('socket timeout')]
  monkeypatch.setattr('data_fetcher.yf.Ticker', _make_fake_ticker_factory(behaviour, []))
  with pytest.raises(DataFetchError, match='Failed to fetch'):
    fetch_ohlcv('SPI200')
```

**Fixture parametrization:**
```python
@pytest.mark.parametrize('signal,expected_direction', [
  (LONG, 'LONG'),
  (SHORT, 'SHORT'),
  (FLAT, 'FLAT'),
])
def test_signal_direction_names(signal, expected_direction):
  '''Verify signal-to-direction mapping.'''
  name = SIGNAL_NAMES[signal]
  assert name == expected_direction
```

**Golden file snapshots:**
```python
def test_chart_payload_escapes_script_close(client_with_state_v3):
  '''XSS defense: chart payload with </script> substring must escape as <\\/script>.'''
  # ... set up state with equity history
  response = client.get('/api/chart')
  body = response.json()
  
  with open('tests/oracle/goldens/golden_empty.html') as f:
    golden = f.read()
  
  # Regenerate golden if this test fails + you've verified the escaping
  # pytest --update-goldens tests/test_dashboard.py::test_chart_payload_escapes_script_close
  assert body['chart_html'] == golden
```

---

*Testing analysis: 2026-05-15*
