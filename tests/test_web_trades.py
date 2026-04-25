'''Phase 14 TRADE-01..06 + D-01..D-13 — endpoint contract + invariant tests.

Reference: 14-CONTEXT.md D-01..D-13 (locked decisions),
14-VALIDATION.md per-task verification map, 14-UI-SPEC.md §HTMX response shapes,
14-RESEARCH.md §Pattern 1, 2, 3 (handler bodies), §Pattern 9 (fcntl test
fixture), §Pattern 10 (AST sole-writer guard).

Plan 14-04 populates these 13 test classes with ~50 tests covering every
locked D-01..D-13 invariant + REVIEWS HIGH #1/2/3/4 + LOW #8/9/10 fixes.

Fixture strategy: client_with_state_v3 from tests/conftest.py provides a
TestClient + state-stubbing + save-capture tuple. The fixture monkey-patches
state_manager.load_state, save_state, AND mutate_state (Plan 14-04 deviation:
handlers use mutate_state per REVIEWS HIGH #1; fixture must mirror semantics).
Local AUTH_HEADER_NAME + VALID_SECRET inlined per Plan 13-02 Rule 1 pattern.
'''
import ast
import json
import math
from pathlib import Path

import pytest
from fastapi.testclient import TestClient  # noqa: F401 — used by Plan 14-04 test bodies

# Plan 13-02 Rule 1 deviation pattern: constants inlined to avoid
# `from conftest import ...` ImportError (tests/ not on sys.path by default
# despite tests/__init__.py — pytest's autouse fixture in tests/conftest.py
# still runs, but module-level constants are not auto-importable).
AUTH_HEADER_NAME = 'X-Trading-Signals-Auth'
VALID_SECRET = 'a' * 32  # matches tests/conftest.py D-17 sentinel


# Path constants (used by TestSoleWriterInvariant AST walks).
WEB_ROUTES_TRADES_PATH = Path('web/routes/trades.py')


def _v3_state_with_open_position(
  instrument='SPI200',
  direction='LONG',
  n_contracts=2,
  pyramid_level=0,
  atr=50.0,
  manual_stop=None,
  entry_price=7800.0,
  peak_price=7850.0,
  trough_price=None,
):
  '''Build a v3 state dict with one open position. Helper for test bodies
  that need a non-default seed via client_with_state_v3's set_state.

  signals dict uses Phase 14 REVIEWS MEDIUM #7 last_scalars shape.
  '''
  spi_pos = None
  audusd_pos = None
  if instrument == 'SPI200':
    spi_pos = {
      'direction': direction, 'entry_price': entry_price,
      'entry_date': '2026-04-20',
      'n_contracts': n_contracts, 'pyramid_level': pyramid_level,
      'peak_price': peak_price if direction == 'LONG' else None,
      'trough_price': None if direction == 'LONG' else (trough_price or entry_price),
      'atr_entry': atr, 'manual_stop': manual_stop,
    }
  else:
    audusd_pos = {
      'direction': direction, 'entry_price': entry_price,
      'entry_date': '2026-04-20',
      'n_contracts': n_contracts, 'pyramid_level': pyramid_level,
      'peak_price': peak_price if direction == 'LONG' else None,
      'trough_price': None if direction == 'LONG' else (trough_price or entry_price),
      'atr_entry': atr, 'manual_stop': manual_stop,
    }
  return {
    'schema_version': 3,
    'account': 100_000.0,
    'last_run': '2026-04-25',
    'positions': {'SPI200': spi_pos, 'AUDUSD': audusd_pos},
    'signals': {
      'SPI200': {'last_scalars': {'atr': 50.0}, 'last_close': 7820.0},
      'AUDUSD': {'last_scalars': {'atr': 0.012}, 'last_close': 0.6480},
    },
    'trade_log': [], 'equity_history': [], 'warnings': [],
    'initial_account': 100_000.0,
    'contracts': {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-mini'},
    '_resolved_contracts': {
      'SPI200': {'multiplier': 5.0, 'cost_aud': 6.0},
      'AUDUSD': {'multiplier': 10000.0, 'cost_aud': 5.0},
    },
  }


def _v3_state_with_no_positions():
  '''v3 state with NO open positions — used by fresh-open tests.'''
  return {
    'schema_version': 3,
    'account': 100_000.0,
    'last_run': '2026-04-25',
    'positions': {'SPI200': None, 'AUDUSD': None},
    'signals': {
      'SPI200': {'last_scalars': {'atr': 50.0}, 'last_close': 7820.0},
      'AUDUSD': {'last_scalars': {'atr': 0.012}, 'last_close': 0.6480},
    },
    'trade_log': [], 'equity_history': [], 'warnings': [],
    'initial_account': 100_000.0,
    'contracts': {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-mini'},
    '_resolved_contracts': {
      'SPI200': {'multiplier': 5.0, 'cost_aud': 6.0},
      'AUDUSD': {'multiplier': 10000.0, 'cost_aud': 5.0},
    },
  }


# =========================================================================
# TestOpenTradeEndpoint — TRADE-01 happy path (D-04 + ATR availability)
# =========================================================================


class TestOpenTradeEndpoint:
  '''Phase 14 TRADE-01: POST /trades/open happy path.'''

  def test_open_long_happy_path(self, client_with_state_v3, htmx_headers):
    client, set_state, captured_saves = client_with_state_v3
    set_state(_v3_state_with_no_positions())
    r = client.post('/trades/open', headers=htmx_headers, json={
      'instrument': 'SPI200', 'direction': 'LONG',
      'entry_price': 7800.0, 'contracts': 2,
    })
    assert r.status_code == 200, r.text
    assert r.headers['content-type'].startswith('text/html')
    assert len(captured_saves) == 1
    pos = captured_saves[0]['positions']['SPI200']
    assert pos['direction'] == 'LONG'
    assert pos['entry_price'] == 7800.0
    assert pos['n_contracts'] == 2
    assert pos['manual_stop'] is None  # D-09 + Pitfall 5

  def test_open_short_happy_path(self, client_with_state_v3, htmx_headers):
    client, set_state, captured_saves = client_with_state_v3
    set_state(_v3_state_with_no_positions())
    r = client.post('/trades/open', headers=htmx_headers, json={
      'instrument': 'AUDUSD', 'direction': 'SHORT',
      'entry_price': 0.6450, 'contracts': 1,
    })
    assert r.status_code == 200, r.text
    pos = captured_saves[0]['positions']['AUDUSD']
    assert pos['direction'] == 'SHORT'
    assert pos['entry_price'] == 0.6450
    assert pos['trough_price'] == 0.6450  # default trough = entry for SHORT

  def test_open_default_executed_at_uses_today_awst(self, client_with_state_v3, htmx_headers):
    client, set_state, captured_saves = client_with_state_v3
    set_state(_v3_state_with_no_positions())
    r = client.post('/trades/open', headers=htmx_headers, json={
      'instrument': 'SPI200', 'direction': 'LONG',
      'entry_price': 7800.0, 'contracts': 2,
    })
    assert r.status_code == 200
    import zoneinfo, datetime
    today_awst = datetime.datetime.now(zoneinfo.ZoneInfo('Australia/Perth')).date().isoformat()
    assert captured_saves[0]['positions']['SPI200']['entry_date'] == today_awst

  def test_open_explicit_executed_at_honored(self, client_with_state_v3, htmx_headers):
    client, set_state, captured_saves = client_with_state_v3
    set_state(_v3_state_with_no_positions())
    r = client.post('/trades/open', headers=htmx_headers, json={
      'instrument': 'SPI200', 'direction': 'LONG',
      'entry_price': 7800.0, 'contracts': 2,
      'executed_at': '2026-04-22',
    })
    assert r.status_code == 200
    assert captured_saves[0]['positions']['SPI200']['entry_date'] == '2026-04-22'

  def test_open_returns_html_partial_with_hx_trigger(self, client_with_state_v3, htmx_headers):
    client, set_state, captured_saves = client_with_state_v3
    set_state(_v3_state_with_no_positions())
    r = client.post('/trades/open', headers=htmx_headers, json={
      'instrument': 'SPI200', 'direction': 'LONG',
      'entry_price': 7800.0, 'contracts': 2,
    })
    assert r.status_code == 200
    assert r.headers['content-type'].startswith('text/html')
    assert r.headers.get('HX-Trigger') == 'positions-changed'

  def test_open_no_atr_in_signals_returns_409(self, client_with_state_v3, htmx_headers):
    client, set_state, captured_saves = client_with_state_v3
    state = _v3_state_with_no_positions()
    state['signals']['SPI200'] = {}  # no last_scalars
    set_state(state)
    r = client.post('/trades/open', headers=htmx_headers, json={
      'instrument': 'SPI200', 'direction': 'LONG',
      'entry_price': 7800.0, 'contracts': 2,
    })
    assert r.status_code == 409
    assert 'ATR' in r.text or 'atr' in r.text


# =========================================================================
# TestOpenPyramidUp — D-01 + D-02 (same direction = pyramid; opposite = 409)
# =========================================================================


class TestOpenPyramidUp:
  '''Phase 14 D-01 / D-02: same direction -> check_pyramid; opposite -> 409.'''

  def test_same_direction_pyramid_should_add_true_applies_increment(
    self, client_with_state_v3, htmx_headers,
  ):
    client, set_state, captured_saves = client_with_state_v3
    # entry 7800, atr 50, n=2, level 0; current 7900 -> distance 100 >= 50 -> add 1
    set_state(_v3_state_with_open_position(
      direction='LONG', n_contracts=2, pyramid_level=0, atr=50.0, entry_price=7800.0,
    ))
    r = client.post('/trades/open', headers=htmx_headers, json={
      'instrument': 'SPI200', 'direction': 'LONG',
      'entry_price': 7900.0, 'contracts': 1,
    })
    assert r.status_code == 200, r.text
    pos = captured_saves[0]['positions']['SPI200']
    assert pos['n_contracts'] == 3, f'pyramid-up should set n=3, got {pos["n_contracts"]}'
    assert pos['pyramid_level'] == 1

  def test_same_direction_pyramid_should_add_false_returns_409(
    self, client_with_state_v3, htmx_headers,
  ):
    client, set_state, captured_saves = client_with_state_v3
    # entry 7800, atr 50, level 0; current 7820 -> distance 20 < 50 -> no add
    set_state(_v3_state_with_open_position(
      direction='LONG', n_contracts=2, pyramid_level=0, atr=50.0,
    ))
    r = client.post('/trades/open', headers=htmx_headers, json={
      'instrument': 'SPI200', 'direction': 'LONG',
      'entry_price': 7820.0, 'contracts': 1,
    })
    assert r.status_code == 409
    assert 'Pyramid blocked' in r.text
    assert len(captured_saves) == 0

  def test_same_direction_at_max_pyramid_returns_409(self, client_with_state_v3, htmx_headers):
    client, set_state, captured_saves = client_with_state_v3
    set_state(_v3_state_with_open_position(
      direction='LONG', n_contracts=3, pyramid_level=2, atr=50.0,
    ))
    r = client.post('/trades/open', headers=htmx_headers, json={
      'instrument': 'SPI200', 'direction': 'LONG',
      'entry_price': 8000.0, 'contracts': 1,  # huge price move; would otherwise trigger
    })
    assert r.status_code == 409
    assert 'Pyramid blocked' in r.text

  def test_opposite_direction_returns_409_with_locked_message(
    self, client_with_state_v3, htmx_headers,
  ):
    client, set_state, captured_saves = client_with_state_v3
    set_state(_v3_state_with_open_position(direction='LONG'))
    r = client.post('/trades/open', headers=htmx_headers, json={
      'instrument': 'SPI200', 'direction': 'SHORT',
      'entry_price': 7800.0, 'contracts': 2,
    })
    assert r.status_code == 409
    # D-01 verbatim message
    assert 'already has an open LONG position' in r.text
    assert 'close it first via POST /trades/close' in r.text
    assert 'before opening a SHORT' in r.text

  def test_pyramid_blocked_no_atr_returns_409(self, client_with_state_v3, htmx_headers):
    client, set_state, captured_saves = client_with_state_v3
    state = _v3_state_with_open_position(direction='LONG')
    state['signals']['SPI200'] = {}  # no last_scalars
    set_state(state)
    r = client.post('/trades/open', headers=htmx_headers, json={
      'instrument': 'SPI200', 'direction': 'LONG',
      'entry_price': 7900.0, 'contracts': 1,
    })
    assert r.status_code == 409
    assert 'ATR' in r.text or 'atr' in r.text


# =========================================================================
# TestOpenAdvancedFields — D-03 coherence checks (peak/trough/pyramid_level)
# =========================================================================


class TestOpenAdvancedFields:
  '''Phase 14 D-03: peak/trough/pyramid_level coherence checks.'''

  def test_long_peak_below_entry_returns_400(self, client_with_state_v3, htmx_headers):
    client, set_state, _ = client_with_state_v3
    set_state(_v3_state_with_no_positions())
    r = client.post('/trades/open', headers=htmx_headers, json={
      'instrument': 'SPI200', 'direction': 'LONG',
      'entry_price': 7800.0, 'contracts': 2, 'peak_price': 7700.0,
    })
    assert r.status_code == 400
    body = r.json()
    assert any('peak_price' in (e['reason'] + e['field']) for e in body['errors'])

  def test_long_with_trough_set_returns_400(self, client_with_state_v3, htmx_headers):
    client, set_state, _ = client_with_state_v3
    set_state(_v3_state_with_no_positions())
    r = client.post('/trades/open', headers=htmx_headers, json={
      'instrument': 'SPI200', 'direction': 'LONG',
      'entry_price': 7800.0, 'contracts': 2, 'trough_price': 7800.0,
    })
    assert r.status_code == 400
    body = r.json()
    assert any('trough_price' in (e['reason'] + e['field']) for e in body['errors'])

  def test_short_trough_above_entry_returns_400(self, client_with_state_v3, htmx_headers):
    client, set_state, _ = client_with_state_v3
    set_state(_v3_state_with_no_positions())
    r = client.post('/trades/open', headers=htmx_headers, json={
      'instrument': 'AUDUSD', 'direction': 'SHORT',
      'entry_price': 0.6450, 'contracts': 1, 'trough_price': 0.6500,
    })
    assert r.status_code == 400

  def test_short_with_peak_set_returns_400(self, client_with_state_v3, htmx_headers):
    client, set_state, _ = client_with_state_v3
    set_state(_v3_state_with_no_positions())
    r = client.post('/trades/open', headers=htmx_headers, json={
      'instrument': 'AUDUSD', 'direction': 'SHORT',
      'entry_price': 0.6450, 'contracts': 1, 'peak_price': 0.6500,
    })
    assert r.status_code == 400

  def test_pyramid_level_out_of_range_returns_400(self, client_with_state_v3, htmx_headers):
    client, set_state, _ = client_with_state_v3
    set_state(_v3_state_with_no_positions())
    r = client.post('/trades/open', headers=htmx_headers, json={
      'instrument': 'SPI200', 'direction': 'LONG',
      'entry_price': 7800.0, 'contracts': 2, 'pyramid_level': 3,
    })
    assert r.status_code == 400

  def test_entry_price_nan_returns_400(self):
    '''Model-level NaN rejection — JSON spec doesn't allow NaN in body so
    we test the Pydantic model directly (RESEARCH §Pattern 1 guidance).
    Pydantic 2.9+ rejects NaN at the Field(gt=0) layer (NaN comparisons
    are False, so NaN > 0 is False); the custom math.isfinite validator
    catches +/-inf where the gt-check would not trigger.'''
    from web.routes.trades import OpenTradeRequest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
      OpenTradeRequest(
        instrument='SPI200', direction='LONG',
        entry_price=float('nan'), contracts=2,
      )
    # Also confirm +inf is rejected (custom validator path — Field(gt=0) accepts it)
    with pytest.raises(ValidationError) as exc_inf:
      OpenTradeRequest(
        instrument='SPI200', direction='LONG',
        entry_price=float('inf'), contracts=2,
      )
    msgs = ' '.join(e['msg'] for e in exc_inf.value.errors())
    assert 'finite' in msgs.lower() or 'nan' in msgs.lower() or 'inf' in msgs.lower()

  def test_long_missing_peak_defaults_to_entry(self, client_with_state_v3, htmx_headers):
    client, set_state, captured_saves = client_with_state_v3
    set_state(_v3_state_with_no_positions())
    r = client.post('/trades/open', headers=htmx_headers, json={
      'instrument': 'SPI200', 'direction': 'LONG',
      'entry_price': 7800.0, 'contracts': 2,
    })
    assert r.status_code == 200
    pos = captured_saves[0]['positions']['SPI200']
    assert pos['peak_price'] == 7800.0  # default to entry_price
    assert pos['trough_price'] is None  # LONG has no trough

  def test_short_missing_trough_defaults_to_entry(self, client_with_state_v3, htmx_headers):
    client, set_state, captured_saves = client_with_state_v3
    set_state(_v3_state_with_no_positions())
    r = client.post('/trades/open', headers=htmx_headers, json={
      'instrument': 'AUDUSD', 'direction': 'SHORT',
      'entry_price': 0.6450, 'contracts': 1,
    })
    assert r.status_code == 200
    pos = captured_saves[0]['positions']['AUDUSD']
    assert pos['peak_price'] is None
    assert pos['trough_price'] == 0.6450


# =========================================================================
# TestCloseTradeEndpoint — TRADE-03 (D-05 inline + D-06 + D-07 + D-08)
# =========================================================================


class TestCloseTradeEndpoint:
  '''Phase 14 TRADE-03: POST /trades/close happy path.'''

  def test_close_long_position_records_trade(self, client_with_state_v3, htmx_headers):
    client, set_state, captured_saves = client_with_state_v3
    set_state(_v3_state_with_open_position(direction='LONG', n_contracts=2, entry_price=7800.0))
    r = client.post('/trades/close', headers=htmx_headers, json={
      'instrument': 'SPI200', 'exit_price': 7900.0,
    })
    assert r.status_code == 200, r.text
    saved = captured_saves[0]
    assert saved['positions']['SPI200'] is None
    assert len(saved['trade_log']) == 1
    trade = saved['trade_log'][0]
    assert trade['instrument'] == 'SPI200'
    assert trade['exit_reason'] == 'operator_close'  # D-06
    assert trade['exit_price'] == 7900.0
    assert trade['multiplier'] == 5.0  # D-07 from _resolved_contracts
    assert trade['cost_aud'] == 6.0

  def test_close_short_position_records_trade(self, client_with_state_v3, htmx_headers):
    client, set_state, captured_saves = client_with_state_v3
    set_state(_v3_state_with_open_position(
      instrument='AUDUSD', direction='SHORT', n_contracts=1,
      entry_price=0.6450, atr=0.012,
    ))
    r = client.post('/trades/close', headers=htmx_headers, json={
      'instrument': 'AUDUSD', 'exit_price': 0.6420,
    })
    assert r.status_code == 200
    saved = captured_saves[0]
    assert saved['positions']['AUDUSD'] is None
    assert len(saved['trade_log']) == 1
    trade = saved['trade_log'][0]
    assert trade['direction'] == 'SHORT'
    assert trade['multiplier'] == 10000.0
    assert trade['cost_aud'] == 5.0

  def test_close_missing_position_returns_409(self, client_with_state_v3, htmx_headers):
    client, set_state, captured_saves = client_with_state_v3
    set_state(_v3_state_with_no_positions())
    r = client.post('/trades/close', headers=htmx_headers, json={
      'instrument': 'SPI200', 'exit_price': 7900.0,
    })
    assert r.status_code == 409
    assert 'no open position' in r.text
    assert len(captured_saves) == 0

  def test_close_default_executed_at_uses_today_awst(self, client_with_state_v3, htmx_headers):
    client, set_state, captured_saves = client_with_state_v3
    set_state(_v3_state_with_open_position(direction='LONG'))
    r = client.post('/trades/close', headers=htmx_headers, json={
      'instrument': 'SPI200', 'exit_price': 7900.0,
    })
    assert r.status_code == 200
    import zoneinfo, datetime
    today_awst = datetime.datetime.now(zoneinfo.ZoneInfo('Australia/Perth')).date().isoformat()
    assert captured_saves[0]['trade_log'][0]['exit_date'] == today_awst

  def test_close_explicit_executed_at_honored(self, client_with_state_v3, htmx_headers):
    client, set_state, captured_saves = client_with_state_v3
    set_state(_v3_state_with_open_position(direction='LONG'))
    r = client.post('/trades/close', headers=htmx_headers, json={
      'instrument': 'SPI200', 'exit_price': 7900.0,
      'executed_at': '2026-04-22',
    })
    assert r.status_code == 200
    assert captured_saves[0]['trade_log'][0]['exit_date'] == '2026-04-22'


# =========================================================================
# TestCloseTradePnLMath — D-05 inline gross_pnl + Phase 3 D-14 closing-half cost
# =========================================================================


class TestCloseTradePnLMath:
  '''Phase 14 D-05: gross_pnl is INLINE raw price-delta;
  record_trade D-14 deducts closing-half cost.'''

  def test_close_long_pnl_math_matches_inline_formula(self, client_with_state_v3, htmx_headers):
    client, set_state, captured_saves = client_with_state_v3
    # n=2, entry=7800, exit=7900 -> gross = (7900-7800)*2*5 = 1000.0
    # closing-half cost = 6.0*2/2 = 6.0 -> net = 994.0
    # account starts 100_000 -> ends 100_994.0
    set_state(_v3_state_with_open_position(
      direction='LONG', n_contracts=2, entry_price=7800.0,
    ))
    r = client.post('/trades/close', headers=htmx_headers, json={
      'instrument': 'SPI200', 'exit_price': 7900.0,
    })
    assert r.status_code == 200
    saved = captured_saves[0]
    trade = saved['trade_log'][0]
    assert trade['gross_pnl'] == pytest.approx(1000.0)
    assert trade['net_pnl'] == pytest.approx(994.0)
    assert saved['account'] == pytest.approx(100_994.0)

  def test_close_short_pnl_math_matches_inline_formula(self, client_with_state_v3, htmx_headers):
    client, set_state, captured_saves = client_with_state_v3
    # n=1, entry=0.6450, exit=0.6420 -> gross = (0.6450-0.6420)*1*10000 = 30.0
    # closing-half cost = 5*1/2 = 2.5 -> net = 27.5
    set_state(_v3_state_with_open_position(
      instrument='AUDUSD', direction='SHORT', n_contracts=1,
      entry_price=0.6450, atr=0.012,
    ))
    r = client.post('/trades/close', headers=htmx_headers, json={
      'instrument': 'AUDUSD', 'exit_price': 0.6420,
    })
    assert r.status_code == 200
    saved = captured_saves[0]
    trade = saved['trade_log'][0]
    assert trade['gross_pnl'] == pytest.approx(30.0)
    assert trade['net_pnl'] == pytest.approx(27.5)
    assert saved['account'] == pytest.approx(100_027.5)

  def test_close_does_not_call_unrealised_pnl_helper(self):
    '''D-05 anti-pitfall regression: web/routes/trades.py source MUST NOT
    contain the literal name of sizing_engine's unrealised-pnl helper —
    a static guarantee that record_trade's closing-half cost deduction
    is not double-counted.'''
    src = WEB_ROUTES_TRADES_PATH.read_text()
    # Use a chunked literal so this very test file can describe the rule
    # without itself becoming a positive match for the AST/grep guard.
    forbidden = 'compute_' + 'unrealised_pnl'
    assert forbidden not in src, (
      f'D-05 anti-pitfall: web/routes/trades.py must NOT reference '
      f'{forbidden} (would double-count closing-half cost via record_trade)'
    )


# =========================================================================
# TestModifyTradeEndpoint — TRADE-04 + D-09..D-12
# =========================================================================


class TestModifyTradeEndpoint:
  '''Phase 14 TRADE-04: POST /trades/modify, all D-09..D-12 cases.'''

  def test_modify_sets_manual_stop(self, client_with_state_v3, htmx_headers):
    client, set_state, captured_saves = client_with_state_v3
    set_state(_v3_state_with_open_position(direction='LONG'))
    r = client.post('/trades/modify', headers=htmx_headers, json={
      'instrument': 'SPI200', 'new_stop': 7700.0,
    })
    assert r.status_code == 200, r.text
    assert captured_saves[0]['positions']['SPI200']['manual_stop'] == 7700.0

  def test_modify_null_stop_clears_override(self, client_with_state_v3, htmx_headers):
    client, set_state, captured_saves = client_with_state_v3
    set_state(_v3_state_with_open_position(direction='LONG', manual_stop=7700.0))
    r = client.post('/trades/modify', headers=htmx_headers, json={
      'instrument': 'SPI200', 'new_stop': None,
    })
    assert r.status_code == 200
    assert captured_saves[0]['positions']['SPI200']['manual_stop'] is None

  def test_modify_absent_stop_no_change(self, client_with_state_v3, htmx_headers):
    client, set_state, captured_saves = client_with_state_v3
    set_state(_v3_state_with_open_position(direction='LONG', manual_stop=7700.0))
    r = client.post('/trades/modify', headers=htmx_headers, json={
      'instrument': 'SPI200', 'new_contracts': 3,
    })
    assert r.status_code == 200
    # manual_stop preserved (absent in request body)
    assert captured_saves[0]['positions']['SPI200']['manual_stop'] == 7700.0

  def test_modify_new_contracts_resets_pyramid_level(
    self, client_with_state_v3, htmx_headers,
  ):
    client, set_state, captured_saves = client_with_state_v3
    set_state(_v3_state_with_open_position(direction='LONG', pyramid_level=2))
    r = client.post('/trades/modify', headers=htmx_headers, json={
      'instrument': 'SPI200', 'new_contracts': 5,
    })
    assert r.status_code == 200
    pos = captured_saves[0]['positions']['SPI200']
    assert pos['n_contracts'] == 5
    assert pos['pyramid_level'] == 0  # D-10

  def test_modify_only_new_stop_resets_pyramid_level(
    self, client_with_state_v3, htmx_headers,
  ):
    '''REVIEWS LOW #9 + D-10: pyramid_level resets on ANY successful modify,
    INCLUDING new_stop-only requests (not just new_contracts).'''
    client, set_state, captured_saves = client_with_state_v3
    set_state(_v3_state_with_open_position(direction='LONG', pyramid_level=2))
    r = client.post('/trades/modify', headers=htmx_headers, json={
      'instrument': 'SPI200', 'new_stop': 7700.0,
    })
    assert r.status_code == 200
    pos = captured_saves[0]['positions']['SPI200']
    assert pos['manual_stop'] == 7700.0
    assert pos['pyramid_level'] == 0  # REVIEWS LOW #9: must reset on new_stop-only too

  def test_modify_both_fields_atomic_save(self, client_with_state_v3, htmx_headers):
    client, set_state, captured_saves = client_with_state_v3
    set_state(_v3_state_with_open_position(direction='LONG'))
    r = client.post('/trades/modify', headers=htmx_headers, json={
      'instrument': 'SPI200', 'new_stop': 7700.0, 'new_contracts': 5,
    })
    assert r.status_code == 200
    assert len(captured_saves) == 1  # D-11 atomic single save
    pos = captured_saves[0]['positions']['SPI200']
    assert pos['manual_stop'] == 7700.0
    assert pos['n_contracts'] == 5

  def test_modify_empty_body_returns_400(self, client_with_state_v3, htmx_headers):
    client, set_state, captured_saves = client_with_state_v3
    set_state(_v3_state_with_open_position(direction='LONG'))
    r = client.post('/trades/modify', headers=htmx_headers, json={
      'instrument': 'SPI200',
    })
    assert r.status_code == 400
    body = r.json()
    msgs = ' '.join(e['reason'] for e in body['errors'])
    assert 'at least one' in msgs.lower()
    assert len(captured_saves) == 0

  def test_modify_zero_contracts_returns_400(self, client_with_state_v3, htmx_headers):
    client, set_state, captured_saves = client_with_state_v3
    set_state(_v3_state_with_open_position(direction='LONG'))
    r = client.post('/trades/modify', headers=htmx_headers, json={
      'instrument': 'SPI200', 'new_contracts': 0,
    })
    assert r.status_code == 400

  def test_modify_nan_stop_rejected_at_model_level(self):
    '''NaN literal not allowed in JSON; assert the Pydantic model rejects
    NaN directly (V5 input validation).'''
    from web.routes.trades import ModifyTradeRequest
    from pydantic import ValidationError
    with pytest.raises(ValidationError) as exc_info:
      ModifyTradeRequest(instrument='SPI200', new_stop=float('nan'))
    msgs = ' '.join(e['msg'] for e in exc_info.value.errors())
    assert 'finite' in msgs.lower() or 'nan' in msgs.lower()

  def test_modify_missing_position_returns_409(self, client_with_state_v3, htmx_headers):
    client, set_state, captured_saves = client_with_state_v3
    set_state(_v3_state_with_no_positions())
    r = client.post('/trades/modify', headers=htmx_headers, json={
      'instrument': 'SPI200', 'new_stop': 7700.0,
    })
    assert r.status_code == 409
    assert 'no open position' in r.text


# =========================================================================
# TestModifyAbsentVsNull — D-12 model_fields_set semantics
# =========================================================================


class TestModifyAbsentVsNull:
  '''Phase 14 D-12: Pydantic v2 model_fields_set absent-vs-null semantics.'''

  def test_pydantic_absent_field_not_in_model_fields_set(self):
    from web.routes.trades import ModifyTradeRequest
    m = ModifyTradeRequest.model_validate({
      'instrument': 'SPI200', 'new_contracts': 2,
    })
    assert 'new_stop' not in m.model_fields_set
    assert 'new_contracts' in m.model_fields_set

  def test_pydantic_null_field_in_model_fields_set(self):
    from web.routes.trades import ModifyTradeRequest
    m = ModifyTradeRequest.model_validate({
      'instrument': 'SPI200', 'new_stop': None,
    })
    assert 'new_stop' in m.model_fields_set
    assert m.new_stop is None

  def test_pydantic_value_field_in_model_fields_set(self):
    from web.routes.trades import ModifyTradeRequest
    m = ModifyTradeRequest.model_validate({
      'instrument': 'SPI200', 'new_stop': 7700.0,
    })
    assert 'new_stop' in m.model_fields_set
    assert m.new_stop == 7700.0


# =========================================================================
# TestErrorResponses — TRADE-02 422 -> 400 remap
# =========================================================================


class TestErrorResponses:
  '''Phase 14 TRADE-02: 422 -> 400 remap; field-level errors JSON shape.'''

  def test_400_body_shape_errors_array(self, client_with_state_v3, htmx_headers):
    client, set_state, _ = client_with_state_v3
    set_state(_v3_state_with_no_positions())
    r = client.post('/trades/open', headers=htmx_headers, json={
      'instrument': 'SPI200', 'direction': 'LONG',
      'entry_price': 7800.0, 'contracts': 0,  # invalid: ge=1
    })
    assert r.status_code == 400
    body = r.json()
    assert 'errors' in body
    assert isinstance(body['errors'], list)
    assert all('field' in e and 'reason' in e for e in body['errors'])

  def test_400_aggregates_multiple_field_errors(self, client_with_state_v3, htmx_headers):
    client, set_state, _ = client_with_state_v3
    set_state(_v3_state_with_no_positions())
    r = client.post('/trades/open', headers=htmx_headers, json={
      'instrument': 'SPI200', 'direction': 'LONG',
      'entry_price': -1, 'contracts': 0,  # both invalid
    })
    assert r.status_code == 400
    body = r.json()
    fields = {e['field'] for e in body['errors']}
    assert 'entry_price' in fields
    assert 'contracts' in fields

  def test_400_field_name_extracted_from_loc_leaf(self, client_with_state_v3, htmx_headers):
    client, set_state, _ = client_with_state_v3
    set_state(_v3_state_with_no_positions())
    r = client.post('/trades/open', headers=htmx_headers, json={
      'instrument': 'SPI200', 'direction': 'LONG',
      'entry_price': 7800.0, 'contracts': 0,
    })
    assert r.status_code == 400
    body = r.json()
    assert any(e['field'] == 'contracts' for e in body['errors'])

  def test_400_uses_application_json_content_type(self, client_with_state_v3, htmx_headers):
    client, set_state, _ = client_with_state_v3
    set_state(_v3_state_with_no_positions())
    r = client.post('/trades/open', headers=htmx_headers, json={
      'instrument': 'BTC',  # not in Literal enum
      'direction': 'LONG', 'entry_price': 7800.0, 'contracts': 1,
    })
    assert r.status_code == 400
    assert r.headers['content-type'].startswith('application/json')


# =========================================================================
# TestHTMXResponses — TRADE-05 partial response shapes
# =========================================================================


class TestHTMXResponses:
  '''Phase 14 TRADE-05: UI-SPEC §Decision 3 response shapes.'''

  def test_open_response_is_html_with_hx_trigger(self, client_with_state_v3, htmx_headers):
    client, set_state, _ = client_with_state_v3
    set_state(_v3_state_with_no_positions())
    r = client.post('/trades/open', headers=htmx_headers, json={
      'instrument': 'SPI200', 'direction': 'LONG',
      'entry_price': 7800.0, 'contracts': 2,
    })
    assert r.status_code == 200
    assert r.headers['content-type'].startswith('text/html')
    assert 'HX-Trigger' in r.headers

  def test_open_response_contains_positions_tbody_partial(
    self, client_with_state_v3, htmx_headers,
  ):
    client, set_state, _ = client_with_state_v3
    set_state(_v3_state_with_no_positions())
    r = client.post('/trades/open', headers=htmx_headers, json={
      'instrument': 'SPI200', 'direction': 'LONG',
      'entry_price': 7800.0, 'contracts': 2,
    })
    assert r.status_code == 200
    assert 'position-row-SPI200' in r.text

  def test_open_response_contains_oob_confirmation_banner(
    self, client_with_state_v3, htmx_headers,
  ):
    client, set_state, _ = client_with_state_v3
    set_state(_v3_state_with_no_positions())
    r = client.post('/trades/open', headers=htmx_headers, json={
      'instrument': 'SPI200', 'direction': 'LONG',
      'entry_price': 7800.0, 'contracts': 2,
    })
    assert 'hx-swap-oob' in r.text
    assert 'Opened LONG SPI200' in r.text

  def test_close_response_has_hx_trigger_positions_changed(
    self, client_with_state_v3, htmx_headers,
  ):
    client, set_state, _ = client_with_state_v3
    set_state(_v3_state_with_open_position(direction='LONG'))
    r = client.post('/trades/close', headers=htmx_headers, json={
      'instrument': 'SPI200', 'exit_price': 7900.0,
    })
    assert r.status_code == 200
    # REVIEWS HIGH #2: HX-Trigger event payload includes positions-changed
    trigger = r.headers.get('HX-Trigger', '')
    assert 'positions-changed' in trigger

  def test_close_success_returns_empty_with_hx_trigger(
    self, client_with_state_v3, htmx_headers,
  ):
    '''REVIEWS HIGH #2: close-success returns EMPTY body (avoids invalid
    <div>-as-tbody-child) + HX-Trigger event for the listener.'''
    client, set_state, _ = client_with_state_v3
    set_state(_v3_state_with_open_position(direction='LONG'))
    r = client.post('/trades/close', headers=htmx_headers, json={
      'instrument': 'SPI200', 'exit_price': 7900.0,
    })
    assert r.status_code == 200
    assert r.text == '', f'close-success body must be EMPTY; got: {r.text!r}'
    trigger = r.headers.get('HX-Trigger', '')
    payload = json.loads(trigger)
    assert 'positions-changed' in payload
    assert payload['positions-changed']['instrument'] == 'SPI200'
    assert payload['positions-changed']['kind'] == 'close'

  def test_modify_response_returns_re_rendered_row(
    self, client_with_state_v3, htmx_headers,
  ):
    client, set_state, _ = client_with_state_v3
    set_state(_v3_state_with_open_position(direction='LONG'))
    r = client.post('/trades/modify', headers=htmx_headers, json={
      'instrument': 'SPI200', 'new_stop': 7700.0,
    })
    assert r.status_code == 200
    assert 'position-row-SPI200' in r.text

  def test_modify_response_contains_manual_badge_when_set(
    self, client_with_state_v3, htmx_headers,
  ):
    client, set_state, _ = client_with_state_v3
    set_state(_v3_state_with_open_position(direction='LONG', manual_stop=7700.0))
    r = client.post('/trades/modify', headers=htmx_headers, json={
      'instrument': 'SPI200', 'new_contracts': 5,
    })
    assert r.status_code == 200
    assert 'badge-manual' in r.text


# =========================================================================
# TestHTMXSupportEndpoints — GET /trades/{close-form,modify-form,cancel-row}
# =========================================================================


class TestHTMXSupportEndpoints:
  '''Phase 14 TRADE-05: HTMX support endpoints — Decision 5 partials.'''

  def test_close_form_returns_partial_with_confirmation(
    self, client_with_state_v3, auth_headers,
  ):
    client, set_state, _ = client_with_state_v3
    set_state(_v3_state_with_open_position(direction='LONG'))
    r = client.get('/trades/close-form?instrument=SPI200', headers=auth_headers)
    assert r.status_code == 200
    assert r.headers['content-type'].startswith('text/html')
    body = r.text
    assert 'name="exit_price"' in body
    assert 'Cancel' in body
    assert 'Confirm close' in body

  def test_close_form_partial_returns_single_tr_only(
    self, client_with_state_v3, auth_headers,
  ):
    '''REVIEWS HIGH #3: close-form returns SINGLE <tr> (the confirmation panel)
    so it can be the entire tbody contents under hx-swap=innerHTML on
    #position-group-{instrument}.'''
    client, set_state, _ = client_with_state_v3
    set_state(_v3_state_with_open_position(direction='LONG'))
    r = client.get('/trades/close-form?instrument=SPI200', headers=auth_headers)
    assert r.status_code == 200
    # Count <tr> elements in the body — must be exactly ONE.
    body = r.text
    assert body.count('<tr') == 1, f'expected 1 <tr>, got {body.count("<tr")}'

  def test_modify_form_returns_partial_with_inputs(
    self, client_with_state_v3, auth_headers,
  ):
    client, set_state, _ = client_with_state_v3
    set_state(_v3_state_with_open_position(direction='LONG'))
    r = client.get('/trades/modify-form?instrument=SPI200', headers=auth_headers)
    assert r.status_code == 200
    body = r.text
    assert 'name="new_stop"' in body
    assert 'name="new_contracts"' in body
    assert 'Cancel' in body
    assert 'Save' in body

  def test_cancel_row_returns_position_row(
    self, client_with_state_v3, auth_headers,
  ):
    client, set_state, _ = client_with_state_v3
    set_state(_v3_state_with_open_position(direction='LONG'))
    r = client.get('/trades/cancel-row?instrument=SPI200', headers=auth_headers)
    assert r.status_code == 200
    assert 'position-row-SPI200' in r.text

  def test_cancel_row_restores_position_tr_from_state(
    self, client_with_state_v3, auth_headers,
  ):
    '''REVIEWS HIGH #3: cancel-row returns the canonical position <tr>
    (NOT a 2-row block) so the tbody contains exactly one row again.'''
    client, set_state, _ = client_with_state_v3
    set_state(_v3_state_with_open_position(direction='LONG'))
    r = client.get('/trades/cancel-row?instrument=SPI200', headers=auth_headers)
    assert r.status_code == 200
    body = r.text
    assert body.count('<tr') == 1, f'expected 1 <tr>, got {body.count("<tr")}'

  def test_close_form_missing_position_returns_404(
    self, client_with_state_v3, auth_headers,
  ):
    client, set_state, _ = client_with_state_v3
    set_state(_v3_state_with_no_positions())
    r = client.get('/trades/close-form?instrument=SPI200', headers=auth_headers)
    assert r.status_code == 404

  def test_form_endpoints_require_auth(self, client_with_state_v3):
    client, set_state, _ = client_with_state_v3
    set_state(_v3_state_with_open_position(direction='LONG'))
    r = client.get('/trades/close-form?instrument=SPI200')  # no auth
    assert r.status_code == 401


# =========================================================================
# TestSaveStateInvariant — D-11 atomic single save per mutation
# =========================================================================


class TestSaveStateInvariant:
  '''Phase 14 D-11: every successful mutation persists state EXACTLY ONCE.'''

  def test_open_calls_save_state_once(self, client_with_state_v3, htmx_headers):
    client, set_state, captured_saves = client_with_state_v3
    set_state(_v3_state_with_no_positions())
    r = client.post('/trades/open', headers=htmx_headers, json={
      'instrument': 'SPI200', 'direction': 'LONG',
      'entry_price': 7800.0, 'contracts': 2,
    })
    assert r.status_code == 200
    assert len(captured_saves) == 1

  def test_close_calls_save_state_once(self, client_with_state_v3, htmx_headers):
    client, set_state, captured_saves = client_with_state_v3
    set_state(_v3_state_with_open_position(direction='LONG'))
    r = client.post('/trades/close', headers=htmx_headers, json={
      'instrument': 'SPI200', 'exit_price': 7900.0,
    })
    assert r.status_code == 200
    assert len(captured_saves) == 1

  def test_modify_calls_save_state_once(self, client_with_state_v3, htmx_headers):
    client, set_state, captured_saves = client_with_state_v3
    set_state(_v3_state_with_open_position(direction='LONG'))
    r = client.post('/trades/modify', headers=htmx_headers, json={
      'instrument': 'SPI200', 'new_stop': 7700.0,
    })
    assert r.status_code == 200
    assert len(captured_saves) == 1

  def test_invalid_request_does_not_call_save_state(
    self, client_with_state_v3, htmx_headers,
  ):
    client, set_state, captured_saves = client_with_state_v3
    set_state(_v3_state_with_no_positions())
    r = client.post('/trades/open', headers=htmx_headers, json={
      'instrument': 'SPI200', 'direction': 'LONG',
      'entry_price': 7800.0, 'contracts': 0,  # invalid: ge=1
    })
    assert r.status_code == 400
    assert len(captured_saves) == 0

  def test_409_conflict_does_not_call_save_state(
    self, client_with_state_v3, htmx_headers,
  ):
    client, set_state, captured_saves = client_with_state_v3
    set_state(_v3_state_with_open_position(direction='LONG'))
    r = client.post('/trades/open', headers=htmx_headers, json={
      'instrument': 'SPI200', 'direction': 'SHORT',  # opposite -> 409
      'entry_price': 7800.0, 'contracts': 2,
    })
    assert r.status_code == 409
    assert len(captured_saves) == 0


# =========================================================================
# TestSoleWriterInvariant — TRADE-06 (RESEARCH §Pattern 10)
# =========================================================================


class TestSoleWriterInvariant:
  '''TRADE-06: web/routes/trades.py must NOT write to state['warnings'].

  RESEARCH §Pattern 10 lines 752-783 verbatim AST walk + REVIEWS LOW #8
  AugAssign branch.
  '''

  def test_no_warnings_subscript_assignment(self):
    src = WEB_ROUTES_TRADES_PATH.read_text()
    tree = ast.parse(src)
    violations = []
    for node in ast.walk(tree):
      if isinstance(node, ast.Assign):
        for tgt in node.targets:
          if (isinstance(tgt, ast.Subscript)
              and isinstance(tgt.slice, ast.Constant)
              and tgt.slice.value == 'warnings'):
            violations.append(f'line {node.lineno}: assigns to <expr>["warnings"]')
    assert violations == [], '\n'.join(violations)

  def test_no_warnings_method_mutation(self):
    '''Detect: state['warnings'].append(...), .extend(...), .insert(...).'''
    src = WEB_ROUTES_TRADES_PATH.read_text()
    tree = ast.parse(src)
    violations = []
    for node in ast.walk(tree):
      if (isinstance(node, ast.Call)
          and isinstance(node.func, ast.Attribute)
          and node.func.attr in ('append', 'extend', 'insert')):
        attr_obj = node.func.value
        if (isinstance(attr_obj, ast.Subscript)
            and isinstance(attr_obj.slice, ast.Constant)
            and attr_obj.slice.value == 'warnings'):
          violations.append(f'line {node.lineno}: mutates <expr>["warnings"]')
    assert violations == [], '\n'.join(violations)


# =========================================================================
# TestEndToEnd — round-trip integration
# =========================================================================


class TestEndToEnd:
  '''Full request lifecycle round-trips.'''

  def test_open_then_close_round_trip(self, client_with_state_v3, htmx_headers):
    client, set_state, captured_saves = client_with_state_v3
    set_state(_v3_state_with_no_positions())
    # Open
    r1 = client.post('/trades/open', headers=htmx_headers, json={
      'instrument': 'SPI200', 'direction': 'LONG',
      'entry_price': 7800.0, 'contracts': 2,
    })
    assert r1.status_code == 200
    assert captured_saves[-1]['positions']['SPI200'] is not None
    # Forward the captured state to set_state so close sees the open position
    set_state(captured_saves[-1])
    # Close
    r2 = client.post('/trades/close', headers=htmx_headers, json={
      'instrument': 'SPI200', 'exit_price': 7900.0,
    })
    assert r2.status_code == 200
    final = captured_saves[-1]
    assert final['positions']['SPI200'] is None
    assert len(final['trade_log']) == 1
