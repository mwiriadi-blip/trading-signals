'''Phase 14 TRADE-01..06 + D-01..D-13 — endpoint contract + invariant tests.

Reference: 14-CONTEXT.md D-01..D-13 (locked decisions),
14-VALIDATION.md per-task verification map, 14-UI-SPEC.md §HTMX response shapes,
14-RESEARCH.md §Pattern 1, 2, 3 (handler bodies), §Pattern 9 (fcntl test
fixture), §Pattern 10 (AST sole-writer guard).

Wave 0 ships skeletons (Plan 14-01); test bodies land in Plan 14-04
(endpoints) — see plan files for the per-test ownership map.

Fixture strategy: client_with_state_v3 from tests/conftest.py provides
a TestClient + state-stubbing + save-capture tuple. Local AUTH_HEADER_NAME
+ VALID_SECRET inlined per Plan 13-02 Rule 1 deviation pattern.
'''
from pathlib import Path

import pytest
from fastapi.testclient import TestClient  # noqa: F401 — used by Plan 14-04 test bodies

# Plan 13-02 Rule 1 deviation pattern: constants inlined to avoid
# `from conftest import ...` ImportError (tests/ not on sys.path by default
# despite tests/__init__.py — pytest's autouse fixture in tests/conftest.py
# still runs, but module-level constants are not auto-importable).
AUTH_HEADER_NAME = 'X-Trading-Signals-Auth'
VALID_SECRET = 'a' * 32  # matches tests/conftest.py D-17 sentinel


class TestOpenTradeEndpoint:
  '''Phase 14 TRADE-01: POST /trades/open happy path + validation.

  Covers: TRADE-01 (open trade endpoint), TRADE-02 (request validation).
  Plan 14-04 populates this class.
  '''

  def test_placeholder_wave_0(self):
    pytest.skip('Wave 0 skeleton; Plan 14-04 implements')


class TestOpenPyramidUp:
  '''Phase 14 D-01/D-02: same-direction open against existing position
  routes through sizing_engine.check_pyramid; opposite-direction open
  returns 409 (operator must close-then-open).

  Covers: TRADE-01. Plan 14-04 populates.
  '''

  def test_placeholder_wave_0(self):
    pytest.skip('Wave 0 skeleton; Plan 14-04 implements')


class TestOpenAdvancedFields:
  '''Phase 14 D-03: peak/trough/pyramid_level coherence checks across
  the OpenTradeRequest Pydantic model_validator.

  Covers: TRADE-02. Plan 14-04 populates.
  '''

  def test_placeholder_wave_0(self):
    pytest.skip('Wave 0 skeleton; Plan 14-04 implements')


class TestCloseTradeEndpoint:
  '''Phase 14 TRADE-03: POST /trades/close happy path.
  D-05 inline gross_pnl, D-06 exit_reason='operator_close',
  D-07 _resolved_contracts read.

  Plan 14-04 populates.
  '''

  def test_placeholder_wave_0(self):
    pytest.skip('Wave 0 skeleton; Plan 14-04 implements')


class TestCloseTradePnLMath:
  '''Phase 14 D-05: realised P&L computed via inline raw price-delta formula.
  LONG: (exit-entry) * n_contracts * multiplier
  SHORT: (entry-exit) * n_contracts * multiplier
  Result must match the formula precisely (no helper indirection).

  Plan 14-04 populates.
  '''

  def test_placeholder_wave_0(self):
    pytest.skip('Wave 0 skeleton; Plan 14-04 implements')


class TestModifyTradeEndpoint:
  '''Phase 14 TRADE-04: POST /trades/modify, all D-09..D-12 cases.
  Includes manual_stop set/clear, peak/trough adjust, pyramid_level adjust.

  Plan 14-04 populates.
  '''

  def test_placeholder_wave_0(self):
    pytest.skip('Wave 0 skeleton; Plan 14-04 implements')


class TestModifyAbsentVsNull:
  '''Phase 14 D-12: Pydantic v2 model_fields_set absent-vs-null semantics.
  Field absent from JSON body  -> not in model_fields_set -> no-op.
  Field present with value=null -> in model_fields_set -> CLEAR the position attr.

  Plan 14-04 populates.
  '''

  def test_placeholder_wave_0(self):
    pytest.skip('Wave 0 skeleton; Plan 14-04 implements')


class TestErrorResponses:
  '''Phase 14 TRADE-02: 422 -> 400 remap; field-level errors JSON shape.
  Tests the FastAPI RequestValidationError exception handler registered
  at create_app() (RESEARCH §Pattern 6).

  Plan 14-04 populates.
  '''

  def test_placeholder_wave_0(self):
    pytest.skip('Wave 0 skeleton; Plan 14-04 implements')


class TestHTMXResponses:
  '''Phase 14 TRADE-05: UI-SPEC §Decision 3 response shapes.
  HX-Request=true -> HTMLResponse partials + OOB confirmation banner +
  HX-Trigger headers. JSON 4xx for non-HTMX clients.

  Plan 14-04 populates.
  '''

  def test_placeholder_wave_0(self):
    pytest.skip('Wave 0 skeleton; Plan 14-04 implements')


class TestHTMXSupportEndpoints:
  '''Phase 14 TRADE-05: HTMX support endpoints.
  GET /trades/close-form, GET /trades/modify-form, GET /trades/cancel-row.
  Each returns an HTMLResponse partial used by hx-get on the dashboard.

  Plan 14-04 populates.
  '''

  def test_placeholder_wave_0(self):
    pytest.skip('Wave 0 skeleton; Plan 14-04 implements')


class TestSaveStateInvariant:
  '''Phase 14 TRADE-06: every SUCCESSFUL mutation calls save_state exactly
  once; FAILED mutations (validation error, conflict) do NOT call save_state.
  Verified via captured_saves closure on client_with_state_v3 fixture.

  Plan 14-04 populates.
  '''

  def test_placeholder_wave_0(self):
    pytest.skip('Wave 0 skeleton; Plan 14-04 implements')


class TestSoleWriterInvariant:
  '''Phase 14 TRADE-06: AST walk per RESEARCH §Pattern 10 lines 752-783.
  web/routes/trades.py is the SOLE writer of state['warnings'] in the
  web tier — no other web/ module may .append() to it or assign-subscript.

  Wave 0: web/routes/trades.py does not yet exist; the AST walk no-ops.
  Plan 14-04 enables this by creating the file; the test runs as a real
  guard from then on.
  '''

  def test_placeholder_wave_0(self):
    pytest.skip('Wave 0 skeleton; Plan 14-04 implements')


class TestEndToEnd:
  '''Phase 14 TRADE-01..06: full request lifecycle.
  Open trade -> modify -> close -> verify trade_log + state.json + dashboard
  badge progression. Coherence test for the entire mutation surface.

  Plan 14-04 populates.
  '''

  def test_placeholder_wave_0(self):
    pytest.skip('Wave 0 skeleton; Plan 14-04 implements')


# Path constants (used by Plan 14-04 / TestSoleWriterInvariant AST walk).
WEB_ROUTES_TRADES_PATH = Path('web/routes/trades.py')
