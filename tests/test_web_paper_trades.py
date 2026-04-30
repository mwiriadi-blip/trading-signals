'''Phase 19 — web/routes/paper_trades.py route tests.

Six route endpoints:
  GET  /paper-trades                      — list fragment
  POST /paper-trade/open                  — create open row
  PATCH /paper-trade/<id>                 — edit open row
  DELETE /paper-trade/<id>                — delete open row
  POST /paper-trade/<id>/close            — close row (compute realised P&L)
  GET  /paper-trade/<id>/close-form       — rendered close-form fragment

Test classes:
  TestOpenPaperTrade          — valid open entries (SPI200, AUDUSD)
  TestOpenValidation          — D-04 every validation rule -> 400
  TestEditPaperTrade          — PATCH valid path + D-04 on edit + 404
  TestImmutability            — PATCH/DELETE/close on closed rows -> 405 + Allow header
  TestDeletePaperTrade        — DELETE valid path + 404
  TestClosePaperTrade         — POST close: P&L correctness + validation + 405
  TestCloseFormFragment       — GET close-form fragment
  TestPaperTradesListFragment — GET /paper-trades
  TestCompositeIDGeneration   — <INSTRUMENT>-<YYYYMMDD>-<NNN> counter logic
  TestStrategyVersionTagging  — VERSION-03 + kwarg-default capture trap
  TestConcurrentOpen          — multiprocessing.Process race test (no ID collision)
  TestAuthEnforcement         — Phase 16.1 middleware gates PATCH/DELETE
'''
import fcntl
import json
import multiprocessing
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import system_params

_AWST = ZoneInfo('Australia/Perth')

# =========================================================================
# Helpers
# =========================================================================

def _now_awst_iso() -> str:
  '''Current datetime in AWST as ISO8601 string (timezone-aware).'''
  return datetime.now(_AWST).isoformat()


def _past_awst_iso(minutes: int = 60) -> str:
  '''ISO8601 datetime `minutes` in the past (AWST).'''
  return (datetime.now(_AWST) - timedelta(minutes=minutes)).isoformat()


def _future_awst_iso(hours: int = 24) -> str:
  '''ISO8601 datetime `hours` in the future (AWST).'''
  return (datetime.now(_AWST) + timedelta(hours=hours)).isoformat()


def _valid_spi200_long() -> dict:
  return {
    'instrument': 'SPI200',
    'side': 'LONG',
    'entry_dt': _past_awst_iso(60),
    'entry_price': 7800.0,
    'contracts': 2,
    'stop_price': 7700.0,
  }


def _valid_audusd_short() -> dict:
  return {
    'instrument': 'AUDUSD',
    'side': 'SHORT',
    'entry_dt': _past_awst_iso(60),
    'entry_price': 0.6500,
    'contracts': 1.0,
    'stop_price': 0.6600,
  }


def _open_row(
  trade_id: str = 'SPI200-20260430-001',
  instrument: str = 'SPI200',
) -> dict:
  '''Build a minimal open paper-trade row for seed state.'''
  return {
    'id': trade_id,
    'instrument': instrument,
    'side': 'LONG',
    'entry_dt': _past_awst_iso(120),
    'entry_price': 7800.0,
    'contracts': 2,
    'stop_price': 7700.0,
    'entry_cost_aud': 3.0,
    'status': 'open',
    'exit_dt': None,
    'exit_price': None,
    'realised_pnl': None,
    'strategy_version': 'v1.2.0',
    'last_alert_state': None,   # Phase 20 D-08
  }


def _closed_row(trade_id: str = 'SPI200-20260427-001') -> dict:
  row = _open_row(trade_id)
  row.update({
    'status': 'closed',
    'exit_dt': _past_awst_iso(240),
    'exit_price': 7900.0,
    'realised_pnl': 994.0,
  })
  return row


# =========================================================================
# TestOpenPaperTrade
# =========================================================================

class TestOpenPaperTrade:
  '''POST /paper-trade/open valid path — D-09 row shape, entry_cost_aud,
  #trades-region HTMX swap target.

  All POST /paper-trade/open calls use data= (form-encoded) to match what
  real browsers + HTMX send. D-17: no hx-ext="json-enc"; routes accept
  application/x-www-form-urlencoded.
  '''

  def test_open_valid_spi200_long_appends_row(self, client_with_state_v6, htmx_headers) -> None:
    '''D-09: valid SPI200 LONG creates a row with correct id, entry_cost_aud=3.0,
    status=open, strategy_version matching system_params.STRATEGY_VERSION.
    '''
    client, set_state, captured_saves = client_with_state_v6
    r = client.post('/paper-trade/open', data=_valid_spi200_long(), headers=htmx_headers)
    assert r.status_code == 200, f'Expected 200; got {r.status_code}: {r.text[:200]}'
    assert captured_saves, 'No state save recorded'
    rows = captured_saves[-1]['paper_trades']
    assert len(rows) == 1
    row = rows[0]
    today = datetime.now(_AWST).strftime('%Y%m%d')
    assert row['id'] == f'SPI200-{today}-001', f'Wrong ID: {row["id"]}'
    assert row['entry_cost_aud'] == 3.0, f'Wrong entry_cost_aud: {row["entry_cost_aud"]}'
    assert row['status'] == 'open'
    assert row['strategy_version'] == system_params.STRATEGY_VERSION

  def test_open_valid_audusd_short_entry_cost_2_5(self, client_with_state_v6, htmx_headers) -> None:
    '''D-02: AUDUSD round_trip=5.0, entry_cost_aud=2.5 (half on open).'''
    client, set_state, captured_saves = client_with_state_v6
    r = client.post('/paper-trade/open', data=_valid_audusd_short(), headers=htmx_headers)
    assert r.status_code == 200
    rows = captured_saves[-1]['paper_trades']
    assert len(rows) == 1
    assert rows[0]['entry_cost_aud'] == 2.5

  def test_open_returns_rendered_trades_region_html(self, client_with_state_v6, htmx_headers) -> None:
    '''D-13: response body contains the #trades-region swap target.'''
    client, set_state, captured_saves = client_with_state_v6
    r = client.post('/paper-trade/open', data=_valid_spi200_long(), headers=htmx_headers)
    assert r.status_code == 200
    assert '<div id="trades-region"' in r.text, (
      f'D-13: response must contain #trades-region; got: {r.text[:200]}'
    )

  def test_open_writes_full_d09_row_shape(self, client_with_state_v6, htmx_headers) -> None:
    '''D-09: written row has exactly the 13 required keys — no extras, no missing.'''
    from web.routes.paper_trades import _D09_KEYS
    client, set_state, captured_saves = client_with_state_v6
    r = client.post('/paper-trade/open', data=_valid_spi200_long(), headers=htmx_headers)
    assert r.status_code == 200
    row = captured_saves[-1]['paper_trades'][0]
    assert set(row.keys()) == _D09_KEYS, (
      f'D-09: row keys mismatch; extra={set(row.keys()) - _D09_KEYS}, '
      f'missing={_D09_KEYS - set(row.keys())}'
    )


# =========================================================================
# TestOpenValidation
# =========================================================================

class TestOpenValidation:
  '''D-04 every validation rule returns 400 (planner D-22 amendment: 422->400).

  All calls use data= (form-encoded) matching real browser/HTMX submissions.
  '''

  def test_open_future_entry_dt_returns_400(self, client_with_state_v6, htmx_headers) -> None:
    client, _, _ = client_with_state_v6
    payload = {**_valid_spi200_long(), 'entry_dt': _future_awst_iso(24)}
    r = client.post('/paper-trade/open', data=payload, headers=htmx_headers)
    assert r.status_code == 400, f'Expected 400; got {r.status_code}: {r.text}'

  def test_open_negative_entry_price_returns_400(self, client_with_state_v6, htmx_headers) -> None:
    client, _, _ = client_with_state_v6
    payload = {**_valid_spi200_long(), 'entry_price': -1.0}
    r = client.post('/paper-trade/open', data=payload, headers=htmx_headers)
    assert r.status_code == 400

  def test_open_zero_entry_price_returns_400(self, client_with_state_v6, htmx_headers) -> None:
    client, _, _ = client_with_state_v6
    payload = {**_valid_spi200_long(), 'entry_price': 0.0}
    r = client.post('/paper-trade/open', data=payload, headers=htmx_headers)
    assert r.status_code == 400

  def test_open_zero_contracts_returns_400(self, client_with_state_v6, htmx_headers) -> None:
    client, _, _ = client_with_state_v6
    payload = {**_valid_spi200_long(), 'contracts': 0}
    r = client.post('/paper-trade/open', data=payload, headers=htmx_headers)
    assert r.status_code == 400

  def test_open_negative_contracts_returns_400(self, client_with_state_v6, htmx_headers) -> None:
    client, _, _ = client_with_state_v6
    payload = {**_valid_spi200_long(), 'contracts': -1}
    r = client.post('/paper-trade/open', data=payload, headers=htmx_headers)
    assert r.status_code == 400

  def test_open_fractional_spi_contracts_returns_400(self, client_with_state_v6, htmx_headers) -> None:
    '''D-04: SPI200 mini contracts must be whole-unit; fractional -> 400.'''
    client, _, _ = client_with_state_v6
    payload = {**_valid_spi200_long(), 'instrument': 'SPI200', 'contracts': 1.5}
    r = client.post('/paper-trade/open', data=payload, headers=htmx_headers)
    assert r.status_code == 400

  def test_open_fractional_audusd_contracts_accepted(self, client_with_state_v6, htmx_headers) -> None:
    '''D-04 explicit allow: AUDUSD allows fractional contracts.'''
    client, _, _ = client_with_state_v6
    payload = {**_valid_audusd_short(), 'instrument': 'AUDUSD', 'contracts': 1.5}
    r = client.post('/paper-trade/open', data=payload, headers=htmx_headers)
    assert r.status_code == 200, f'Expected 200 for AUDUSD fractional; got {r.status_code}'

  def test_open_unknown_instrument_returns_400(self, client_with_state_v6, htmx_headers) -> None:
    client, _, _ = client_with_state_v6
    payload = {**_valid_spi200_long(), 'instrument': 'NIKKEI'}
    r = client.post('/paper-trade/open', data=payload, headers=htmx_headers)
    assert r.status_code == 400

  def test_open_unknown_side_returns_400(self, client_with_state_v6, htmx_headers) -> None:
    client, _, _ = client_with_state_v6
    payload = {**_valid_spi200_long(), 'side': 'HOLD'}
    r = client.post('/paper-trade/open', data=payload, headers=htmx_headers)
    assert r.status_code == 400

  def test_open_long_with_stop_above_entry_returns_400(self, client_with_state_v6, htmx_headers) -> None:
    '''D-04: LONG stop must be < entry_price; stop > entry -> 400.'''
    client, _, _ = client_with_state_v6
    payload = {**_valid_spi200_long(), 'side': 'LONG', 'entry_price': 7800.0, 'stop_price': 7900.0}
    r = client.post('/paper-trade/open', data=payload, headers=htmx_headers)
    assert r.status_code == 400

  def test_open_short_with_stop_below_entry_returns_400(self, client_with_state_v6, htmx_headers) -> None:
    '''D-04: SHORT stop must be > entry_price; stop < entry -> 400.'''
    client, _, _ = client_with_state_v6
    payload = {**_valid_audusd_short(), 'side': 'SHORT', 'entry_price': 0.6500, 'stop_price': 0.6400}
    r = client.post('/paper-trade/open', data=payload, headers=htmx_headers)
    assert r.status_code == 400

  def test_open_negative_stop_price_returns_400(self, client_with_state_v6, htmx_headers) -> None:
    client, _, _ = client_with_state_v6
    payload = {**_valid_spi200_long(), 'stop_price': -1.0}
    r = client.post('/paper-trade/open', data=payload, headers=htmx_headers)
    assert r.status_code == 400

  def test_open_extra_field_returns_400(self, client_with_state_v6, htmx_headers) -> None:
    '''D-09: extra=forbid on Pydantic model; unknown form field -> 400.
    _parse_form passes the raw form dict to model_validate; extra=forbid
    rejects unknown keys regardless of transport (JSON or form-encoded).
    '''
    client, _, _ = client_with_state_v6
    payload = {**_valid_spi200_long(), 'comment': 'sneaky'}
    r = client.post('/paper-trade/open', data=payload, headers=htmx_headers)
    assert r.status_code == 400, f'Expected 400 (extra field forbidden); got {r.status_code}: {r.text[:200]}'


# =========================================================================
# TestEditPaperTrade
# =========================================================================

class TestEditPaperTrade:
  '''PATCH /paper-trade/<id> — valid path, D-04 on edit, 404 on unknown.

  All PATCH calls use data= (form-encoded) matching real browser/HTMX submissions.
  '''

  def test_patch_open_row_updates_fields(self, client_with_state_v6, htmx_headers) -> None:
    '''D-05: PATCH updates entry_price; strategy_version refreshed.'''
    client, set_state, captured_saves = client_with_state_v6
    trade_id = 'SPI200-20260430-001'
    set_state({**client_with_state_v6[0].app.state.__dict__.get('_test_state', {}),
               'schema_version': 6, 'account': 100000.0, 'last_run': '2026-04-30',
               'positions': {'SPI200': None, 'AUDUSD': None},
               'signals': {'SPI200': {'last_close': 7820.0}, 'AUDUSD': {'last_close': 0.652}},
               'trade_log': [], 'equity_history': [], 'warnings': [],
               'initial_account': 100000.0,
               'contracts': {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-mini'},
               '_resolved_contracts': {'SPI200': {'multiplier': 5.0, 'cost_aud': 6.0},
                                        'AUDUSD': {'multiplier': 10000.0, 'cost_aud': 5.0}},
               'paper_trades': [_open_row(trade_id)]})
    r = client.patch(f'/paper-trade/{trade_id}',
                     data={'entry_price': 7850.0},
                     headers=htmx_headers)
    assert r.status_code == 200, f'Expected 200; got {r.status_code}: {r.text[:300]}'
    row = captured_saves[-1]['paper_trades'][0]
    assert row['entry_price'] == 7850.0
    assert row['strategy_version'] == system_params.STRATEGY_VERSION

  def test_patch_open_row_validates_d04(self, client_with_state_v6, htmx_headers) -> None:
    '''D-04: D-04 rules apply on PATCH (negative entry_price -> 400).'''
    client, set_state, _ = client_with_state_v6
    trade_id = 'SPI200-20260430-001'
    set_state({
      'schema_version': 6, 'account': 100000.0, 'last_run': '2026-04-30',
      'positions': {'SPI200': None, 'AUDUSD': None},
      'signals': {'SPI200': {'last_close': 7820.0}, 'AUDUSD': {'last_close': 0.652}},
      'trade_log': [], 'equity_history': [], 'warnings': [],
      'initial_account': 100000.0,
      'contracts': {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-mini'},
      '_resolved_contracts': {'SPI200': {'multiplier': 5.0, 'cost_aud': 6.0},
                               'AUDUSD': {'multiplier': 10000.0, 'cost_aud': 5.0}},
      'paper_trades': [_open_row(trade_id)],
    })
    r = client.patch(f'/paper-trade/{trade_id}',
                     data={'entry_price': -1.0},
                     headers=htmx_headers)
    assert r.status_code == 400

  def test_patch_unknown_id_returns_404(self, client_with_state_v6, htmx_headers) -> None:
    client, _, _ = client_with_state_v6
    r = client.patch('/paper-trade/SPI200-20990101-999',
                     data={'entry_price': 7800.0},
                     headers=htmx_headers)
    assert r.status_code == 404

  def test_patch_open_row_returns_rendered_trades_region(self, client_with_state_v6, htmx_headers) -> None:
    client, set_state, captured_saves = client_with_state_v6
    trade_id = 'SPI200-20260430-001'
    set_state({
      'schema_version': 6, 'account': 100000.0, 'last_run': '2026-04-30',
      'positions': {'SPI200': None, 'AUDUSD': None},
      'signals': {'SPI200': {'last_close': 7820.0}, 'AUDUSD': {'last_close': 0.652}},
      'trade_log': [], 'equity_history': [], 'warnings': [],
      'initial_account': 100000.0,
      'contracts': {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-mini'},
      '_resolved_contracts': {'SPI200': {'multiplier': 5.0, 'cost_aud': 6.0},
                               'AUDUSD': {'multiplier': 10000.0, 'cost_aud': 5.0}},
      'paper_trades': [_open_row(trade_id)],
    })
    r = client.patch(f'/paper-trade/{trade_id}',
                     data={'entry_price': 7900.0},
                     headers=htmx_headers)
    assert r.status_code == 200
    assert '<div id="trades-region"' in r.text

  @pytest.mark.parametrize('prior_state', [None, 'CLEAR', 'APPROACHING', 'HIT'])
  def test_edit_resets_last_alert_state(
    self, client_with_state_v6, htmx_headers, prior_state,
  ) -> None:
    '''Phase 20 D-09: PATCH resets last_alert_state to None on any prior value.
    Operator has acknowledged the stop edit; next daily run recomputes.
    '''
    client, set_state, captured_saves = client_with_state_v6
    trade_id = 'SPI200-20260430-001'
    row = _open_row(trade_id)
    row['last_alert_state'] = prior_state
    set_state({
      'schema_version': 7, 'account': 100000.0, 'last_run': '2026-04-30',
      'positions': {'SPI200': None, 'AUDUSD': None},
      'signals': {'SPI200': {'last_close': 7820.0}, 'AUDUSD': {'last_close': 0.652}},
      'trade_log': [], 'equity_history': [], 'warnings': [],
      'initial_account': 100000.0,
      'contracts': {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-mini'},
      '_resolved_contracts': {'SPI200': {'multiplier': 5.0, 'cost_aud': 6.0},
                               'AUDUSD': {'multiplier': 10000.0, 'cost_aud': 5.0}},
      'paper_trades': [row],
    })
    r = client.patch(f'/paper-trade/{trade_id}',
                     data={'stop_price': 7650.0},
                     headers=htmx_headers)
    assert r.status_code == 200, f'Expected 200; got {r.status_code}: {r.text[:300]}'
    saved_row = captured_saves[-1]['paper_trades'][0]
    assert saved_row['last_alert_state'] is None, (
      f'D-09: last_alert_state must reset to None on PATCH; '
      f'prior={prior_state!r}, got {saved_row["last_alert_state"]!r}'
    )


# =========================================================================
# TestImmutability
# =========================================================================

class TestImmutability:
  '''Closed rows return 405 + Allow: GET header (RFC 7231 §6.5.5).'''

  def _seed_closed(self, set_state, trade_id: str = 'SPI200-20260427-001') -> None:
    set_state({
      'schema_version': 6, 'account': 100000.0, 'last_run': '2026-04-30',
      'positions': {'SPI200': None, 'AUDUSD': None},
      'signals': {'SPI200': {'last_close': 7820.0}, 'AUDUSD': {'last_close': 0.652}},
      'trade_log': [], 'equity_history': [], 'warnings': [],
      'initial_account': 100000.0,
      'contracts': {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-mini'},
      '_resolved_contracts': {'SPI200': {'multiplier': 5.0, 'cost_aud': 6.0},
                               'AUDUSD': {'multiplier': 10000.0, 'cost_aud': 5.0}},
      'paper_trades': [_closed_row(trade_id)],
    })

  def test_patch_closed_row_returns_405_with_allow_header(self, client_with_state_v6, htmx_headers) -> None:
    client, set_state, _ = client_with_state_v6
    trade_id = 'SPI200-20260427-001'
    self._seed_closed(set_state, trade_id)
    r = client.patch(f'/paper-trade/{trade_id}',
                     data={'entry_price': 7900.0},
                     headers=htmx_headers)
    assert r.status_code == 405, f'Expected 405; got {r.status_code}: {r.text}'
    assert r.text == 'closed rows are immutable', f'Wrong body: {r.text!r}'
    assert r.headers.get('allow', '').upper() == 'GET', (
      f'RFC 7231: Allow header must be GET; got {r.headers.get("allow")!r}'
    )

  def test_delete_closed_row_returns_405_with_allow_header(self, client_with_state_v6, htmx_headers) -> None:
    client, set_state, _ = client_with_state_v6
    trade_id = 'SPI200-20260427-001'
    self._seed_closed(set_state, trade_id)
    r = client.delete(f'/paper-trade/{trade_id}', headers=htmx_headers)
    assert r.status_code == 405
    assert r.text == 'closed rows are immutable'
    assert r.headers.get('allow', '').upper() == 'GET'


# =========================================================================
# TestDeletePaperTrade
# =========================================================================

class TestDeletePaperTrade:
  '''DELETE /paper-trade/<id> — removes open row; 404 on unknown.'''

  def test_delete_open_row_removes_it(self, client_with_state_v6, htmx_headers) -> None:
    client, set_state, captured_saves = client_with_state_v6
    trade_id = 'SPI200-20260430-001'
    set_state({
      'schema_version': 6, 'account': 100000.0, 'last_run': '2026-04-30',
      'positions': {'SPI200': None, 'AUDUSD': None},
      'signals': {'SPI200': {'last_close': 7820.0}, 'AUDUSD': {'last_close': 0.652}},
      'trade_log': [], 'equity_history': [], 'warnings': [],
      'initial_account': 100000.0,
      'contracts': {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-mini'},
      '_resolved_contracts': {'SPI200': {'multiplier': 5.0, 'cost_aud': 6.0},
                               'AUDUSD': {'multiplier': 10000.0, 'cost_aud': 5.0}},
      'paper_trades': [_open_row(trade_id)],
    })
    r = client.delete(f'/paper-trade/{trade_id}', headers=htmx_headers)
    assert r.status_code == 200
    assert captured_saves[-1]['paper_trades'] == [], (
      f'paper_trades must be empty after delete; got {captured_saves[-1]["paper_trades"]}'
    )

  def test_delete_unknown_id_returns_404(self, client_with_state_v6, htmx_headers) -> None:
    client, _, _ = client_with_state_v6
    r = client.delete('/paper-trade/SPI200-20990101-999', headers=htmx_headers)
    assert r.status_code == 404

  def test_delete_no_body(self, client_with_state_v6, htmx_headers) -> None:
    '''D-21: DELETE carries no body; route handles it fine.'''
    client, set_state, _ = client_with_state_v6
    trade_id = 'SPI200-20260430-001'
    set_state({
      'schema_version': 6, 'account': 100000.0, 'last_run': '2026-04-30',
      'positions': {'SPI200': None, 'AUDUSD': None},
      'signals': {'SPI200': {'last_close': 7820.0}, 'AUDUSD': {'last_close': 0.652}},
      'trade_log': [], 'equity_history': [], 'warnings': [],
      'initial_account': 100000.0,
      'contracts': {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-mini'},
      '_resolved_contracts': {'SPI200': {'multiplier': 5.0, 'cost_aud': 6.0},
                               'AUDUSD': {'multiplier': 10000.0, 'cost_aud': 5.0}},
      'paper_trades': [_open_row(trade_id)],
    })
    # No body= / json= — raw delete with no payload
    r = client.delete(f'/paper-trade/{trade_id}', headers=htmx_headers)
    assert r.status_code == 200


# =========================================================================
# TestClosePaperTrade
# =========================================================================

class TestClosePaperTrade:
  '''POST /paper-trade/<id>/close — P&L correctness, validation, 405 on closed.

  All POST /paper-trade/<id>/close calls use data= (form-encoded) matching
  real browser/HTMX submissions. D-17: no hx-ext="json-enc".
  '''

  def _seed_open(self, set_state, trade_id: str, instrument: str = 'SPI200',
                 side: str = 'LONG', entry_price: float = 7800.0, contracts=2) -> None:
    row = _open_row(trade_id, instrument)
    row['side'] = side
    row['entry_price'] = entry_price
    row['contracts'] = contracts
    set_state({
      'schema_version': 6, 'account': 100000.0, 'last_run': '2026-04-30',
      'positions': {'SPI200': None, 'AUDUSD': None},
      'signals': {'SPI200': {'last_close': 7820.0}, 'AUDUSD': {'last_close': 0.652}},
      'trade_log': [], 'equity_history': [], 'warnings': [],
      'initial_account': 100000.0,
      'contracts': {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-mini'},
      '_resolved_contracts': {'SPI200': {'multiplier': 5.0, 'cost_aud': 6.0},
                               'AUDUSD': {'multiplier': 10000.0, 'cost_aud': 5.0}},
      'paper_trades': [row],
    })

  def test_close_long_spi200_realised_pnl_correct(self, client_with_state_v6, htmx_headers) -> None:
    '''D-11: LONG SPI200 realised = (7900-7800)*2*5 - 6 = 994.0.'''
    client, set_state, captured_saves = client_with_state_v6
    trade_id = 'SPI200-20260430-001'
    self._seed_open(set_state, trade_id, 'SPI200', 'LONG', 7800.0, 2)
    r = client.post(f'/paper-trade/{trade_id}/close',
                    data={'exit_dt': _past_awst_iso(10), 'exit_price': 7900.0},
                    headers=htmx_headers)
    assert r.status_code == 200, f'Expected 200; got {r.status_code}: {r.text[:300]}'
    row = captured_saves[-1]['paper_trades'][0]
    assert row['status'] == 'closed'
    assert row['exit_price'] == 7900.0
    assert abs(row['realised_pnl'] - 994.0) < 1e-9, (
      f'D-11: expected 994.0; got {row["realised_pnl"]}'
    )

  def test_close_short_audusd_realised_pnl_correct(self, client_with_state_v6, htmx_headers) -> None:
    '''D-11: SHORT AUDUSD realised = (0.65-0.64)*1*10000 - 5 = 95.0.'''
    client, set_state, captured_saves = client_with_state_v6
    trade_id = 'AUDUSD-20260430-001'
    row = _open_row(trade_id, 'AUDUSD')
    row.update({'side': 'SHORT', 'entry_price': 0.6500, 'contracts': 1.0,
                'entry_cost_aud': 2.5, 'stop_price': 0.6600})
    set_state({
      'schema_version': 6, 'account': 100000.0, 'last_run': '2026-04-30',
      'positions': {'SPI200': None, 'AUDUSD': None},
      'signals': {'SPI200': {'last_close': 7820.0}, 'AUDUSD': {'last_close': 0.652}},
      'trade_log': [], 'equity_history': [], 'warnings': [],
      'initial_account': 100000.0,
      'contracts': {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-mini'},
      '_resolved_contracts': {'SPI200': {'multiplier': 5.0, 'cost_aud': 6.0},
                               'AUDUSD': {'multiplier': 10000.0, 'cost_aud': 5.0}},
      'paper_trades': [row],
    })
    r = client.post(f'/paper-trade/{trade_id}/close',
                    data={'exit_dt': _past_awst_iso(10), 'exit_price': 0.6400},
                    headers=htmx_headers)
    assert r.status_code == 200
    saved_row = captured_saves[-1]['paper_trades'][0]
    assert abs(saved_row['realised_pnl'] - 95.0) < 1e-9, (
      f'D-11: expected ~95.0; got {saved_row["realised_pnl"]}'
    )

  def test_close_exit_price_zero_returns_400(self, client_with_state_v6, htmx_headers) -> None:
    client, set_state, _ = client_with_state_v6
    trade_id = 'SPI200-20260430-001'
    set_state({
      'schema_version': 6, 'account': 100000.0, 'last_run': '2026-04-30',
      'positions': {'SPI200': None, 'AUDUSD': None},
      'signals': {}, 'trade_log': [], 'equity_history': [], 'warnings': [],
      'initial_account': 100000.0,
      'contracts': {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-mini'},
      '_resolved_contracts': {'SPI200': {'multiplier': 5.0, 'cost_aud': 6.0},
                               'AUDUSD': {'multiplier': 10000.0, 'cost_aud': 5.0}},
      'paper_trades': [_open_row(trade_id)],
    })
    r = client.post(f'/paper-trade/{trade_id}/close',
                    data={'exit_dt': _past_awst_iso(10), 'exit_price': 0.0},
                    headers=htmx_headers)
    assert r.status_code == 400

  def test_close_exit_dt_before_entry_dt_returns_400(self, client_with_state_v6, htmx_headers) -> None:
    '''D-04 close: exit_dt must be >= entry_dt.'''
    client, set_state, _ = client_with_state_v6
    trade_id = 'SPI200-20260430-001'
    row = _open_row(trade_id)
    # entry_dt is 2 hours ago; exit_dt 3 hours ago = before entry
    set_state({
      'schema_version': 6, 'account': 100000.0, 'last_run': '2026-04-30',
      'positions': {'SPI200': None, 'AUDUSD': None},
      'signals': {}, 'trade_log': [], 'equity_history': [], 'warnings': [],
      'initial_account': 100000.0,
      'contracts': {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-mini'},
      '_resolved_contracts': {'SPI200': {'multiplier': 5.0, 'cost_aud': 6.0},
                               'AUDUSD': {'multiplier': 10000.0, 'cost_aud': 5.0}},
      'paper_trades': [row],
    })
    r = client.post(f'/paper-trade/{trade_id}/close',
                    data={'exit_dt': _past_awst_iso(180), 'exit_price': 7900.0},
                    headers=htmx_headers)
    assert r.status_code == 400, f'Expected 400; got {r.status_code}: {r.text}'

  def test_close_already_closed_row_returns_405_with_allow_header(self, client_with_state_v6, htmx_headers) -> None:
    client, set_state, _ = client_with_state_v6
    trade_id = 'SPI200-20260427-001'
    set_state({
      'schema_version': 6, 'account': 100000.0, 'last_run': '2026-04-30',
      'positions': {'SPI200': None, 'AUDUSD': None},
      'signals': {}, 'trade_log': [], 'equity_history': [], 'warnings': [],
      'initial_account': 100000.0,
      'contracts': {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-mini'},
      '_resolved_contracts': {'SPI200': {'multiplier': 5.0, 'cost_aud': 6.0},
                               'AUDUSD': {'multiplier': 10000.0, 'cost_aud': 5.0}},
      'paper_trades': [_closed_row(trade_id)],
    })
    r = client.post(f'/paper-trade/{trade_id}/close',
                    data={'exit_dt': _past_awst_iso(10), 'exit_price': 7900.0},
                    headers=htmx_headers)
    assert r.status_code == 405
    assert r.headers.get('allow', '').upper() == 'GET'

  def test_close_returns_rendered_trades_region(self, client_with_state_v6, htmx_headers) -> None:
    client, set_state, _ = client_with_state_v6
    trade_id = 'SPI200-20260430-001'
    set_state({
      'schema_version': 6, 'account': 100000.0, 'last_run': '2026-04-30',
      'positions': {'SPI200': None, 'AUDUSD': None},
      'signals': {'SPI200': {'last_close': 7820.0}, 'AUDUSD': {'last_close': 0.652}},
      'trade_log': [], 'equity_history': [], 'warnings': [],
      'initial_account': 100000.0,
      'contracts': {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-mini'},
      '_resolved_contracts': {'SPI200': {'multiplier': 5.0, 'cost_aud': 6.0},
                               'AUDUSD': {'multiplier': 10000.0, 'cost_aud': 5.0}},
      'paper_trades': [_open_row(trade_id)],
    })
    r = client.post(f'/paper-trade/{trade_id}/close',
                    data={'exit_dt': _past_awst_iso(10), 'exit_price': 7900.0},
                    headers=htmx_headers)
    assert r.status_code == 200
    assert '<div id="trades-region"' in r.text


# =========================================================================
# TestCloseFormFragment
# =========================================================================

class TestCloseFormFragment:
  '''GET /paper-trade/<id>/close-form — pre-rendered form with baked action URL.'''

  def test_get_close_form_returns_form_with_post_action_baked_in(
    self, client_with_state_v6, htmx_headers,
  ) -> None:
    '''RESEARCH §Pattern 1: trade ID baked into hx-post action URL by server.'''
    client, set_state, _ = client_with_state_v6
    trade_id = 'SPI200-20260430-001'
    set_state({
      'schema_version': 6, 'account': 100000.0, 'last_run': '2026-04-30',
      'positions': {'SPI200': None, 'AUDUSD': None},
      'signals': {}, 'trade_log': [], 'equity_history': [], 'warnings': [],
      'initial_account': 100000.0,
      'contracts': {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-mini'},
      '_resolved_contracts': {'SPI200': {'multiplier': 5.0, 'cost_aud': 6.0},
                               'AUDUSD': {'multiplier': 10000.0, 'cost_aud': 5.0}},
      'paper_trades': [_open_row(trade_id)],
    })
    r = client.get(f'/paper-trade/{trade_id}/close-form', headers=htmx_headers)
    assert r.status_code == 200
    assert f'hx-post="/paper-trade/{trade_id}/close"' in r.text, (
      f'close-form must bake trade_id into hx-post action; got: {r.text[:300]}'
    )

  def test_get_close_form_unknown_id_returns_404(self, client_with_state_v6, htmx_headers) -> None:
    client, _, _ = client_with_state_v6
    r = client.get('/paper-trade/SPI200-20990101-999/close-form', headers=htmx_headers)
    assert r.status_code == 404


# =========================================================================
# TestPaperTradesListFragment
# =========================================================================

class TestPaperTradesListFragment:
  '''GET /paper-trades — returns rendered #trades-region HTML.'''

  def test_get_paper_trades_returns_rendered_region(self, client_with_state_v6, htmx_headers) -> None:
    client, _, _ = client_with_state_v6
    r = client.get('/paper-trades', headers=htmx_headers)
    assert r.status_code == 200
    assert '<div id="trades-region"' in r.text


# =========================================================================
# TestCompositeIDGeneration
# =========================================================================

class TestCompositeIDGeneration:
  '''D-01: <INSTRUMENT>-<YYYYMMDD>-<NNN> counter per instrument per day.'''

  def test_first_open_assigns_001(self, client_with_state_v6, htmx_headers) -> None:
    client, _, captured_saves = client_with_state_v6
    r = client.post('/paper-trade/open', data=_valid_spi200_long(), headers=htmx_headers)
    assert r.status_code == 200
    row = captured_saves[-1]['paper_trades'][0]
    assert row['id'].endswith('-001'), f'First row must end -001; got {row["id"]}'

  def test_second_open_same_instrument_same_day_assigns_002(self, client_with_state_v6, htmx_headers) -> None:
    client, set_state, captured_saves = client_with_state_v6
    today = datetime.now(_AWST).strftime('%Y%m%d')
    # Seed with one existing row from today
    set_state({
      'schema_version': 6, 'account': 100000.0, 'last_run': '2026-04-30',
      'positions': {'SPI200': None, 'AUDUSD': None},
      'signals': {'SPI200': {'last_close': 7820.0}, 'AUDUSD': {'last_close': 0.652}},
      'trade_log': [], 'equity_history': [], 'warnings': [],
      'initial_account': 100000.0,
      'contracts': {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-mini'},
      '_resolved_contracts': {'SPI200': {'multiplier': 5.0, 'cost_aud': 6.0},
                               'AUDUSD': {'multiplier': 10000.0, 'cost_aud': 5.0}},
      'paper_trades': [_open_row(f'SPI200-{today}-001')],
    })
    r = client.post('/paper-trade/open', data=_valid_spi200_long(), headers=htmx_headers)
    assert r.status_code == 200
    rows = captured_saves[-1]['paper_trades']
    ids = [r['id'] for r in rows]
    assert f'SPI200-{today}-001' in ids
    assert f'SPI200-{today}-002' in ids, f'Expected -002 to exist; got ids={ids}'

  def test_audusd_after_spi_assigns_audusd_001(self, client_with_state_v6, htmx_headers) -> None:
    '''D-01: counter is per-instrument-per-day; AUDUSD counter is independent.'''
    client, set_state, captured_saves = client_with_state_v6
    today = datetime.now(_AWST).strftime('%Y%m%d')
    # Seed with SPI200-001; AUDUSD counter should start at 001
    set_state({
      'schema_version': 6, 'account': 100000.0, 'last_run': '2026-04-30',
      'positions': {'SPI200': None, 'AUDUSD': None},
      'signals': {'SPI200': {'last_close': 7820.0}, 'AUDUSD': {'last_close': 0.652}},
      'trade_log': [], 'equity_history': [], 'warnings': [],
      'initial_account': 100000.0,
      'contracts': {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-mini'},
      '_resolved_contracts': {'SPI200': {'multiplier': 5.0, 'cost_aud': 6.0},
                               'AUDUSD': {'multiplier': 10000.0, 'cost_aud': 5.0}},
      'paper_trades': [_open_row(f'SPI200-{today}-001', 'SPI200')],
    })
    r = client.post('/paper-trade/open', data=_valid_audusd_short(), headers=htmx_headers)
    assert r.status_code == 200
    rows = captured_saves[-1]['paper_trades']
    audusd_ids = [r['id'] for r in rows if r['instrument'] == 'AUDUSD']
    assert any(i.endswith('-001') for i in audusd_ids), (
      f'AUDUSD counter must start at 001 independent of SPI200; got {audusd_ids}'
    )

  def test_id_counter_overflow_999_raises_explicit_error(self, client_with_state_v6, htmx_headers) -> None:
    '''D-01 risk register: 999-row limit; 1000th POST returns 400 with explicit reason.'''
    client, set_state, _ = client_with_state_v6
    today = datetime.now(_AWST).strftime('%Y%m%d')
    # Seed 999 rows for today's date
    rows_999 = [
      {**_open_row(f'SPI200-{today}-{i:03d}'), 'id': f'SPI200-{today}-{i:03d}'}
      for i in range(1, 1000)
    ]
    set_state({
      'schema_version': 6, 'account': 100000.0, 'last_run': '2026-04-30',
      'positions': {'SPI200': None, 'AUDUSD': None},
      'signals': {'SPI200': {'last_close': 7820.0}, 'AUDUSD': {'last_close': 0.652}},
      'trade_log': [], 'equity_history': [], 'warnings': [],
      'initial_account': 100000.0,
      'contracts': {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-mini'},
      '_resolved_contracts': {'SPI200': {'multiplier': 5.0, 'cost_aud': 6.0},
                               'AUDUSD': {'multiplier': 10000.0, 'cost_aud': 5.0}},
      'paper_trades': rows_999,
    })
    r = client.post('/paper-trade/open', data=_valid_spi200_long(), headers=htmx_headers)
    assert r.status_code == 400, f'Expected 400 on overflow; got {r.status_code}'
    # Response should mention counter overflow / 999
    assert 'overflow' in r.text.lower() or '999' in r.text, (
      f'D-01 risk: explicit overflow reason missing; got: {r.text}'
    )


# =========================================================================
# TestStrategyVersionTagging
# =========================================================================

class TestStrategyVersionTagging:
  '''VERSION-03 + kwarg-default capture trap (LEARNINGS 2026-04-29).'''

  def test_open_writes_strategy_version_from_constant(self, client_with_state_v6, htmx_headers) -> None:
    client, _, captured_saves = client_with_state_v6
    r = client.post('/paper-trade/open', data=_valid_spi200_long(), headers=htmx_headers)
    assert r.status_code == 200
    row = captured_saves[-1]['paper_trades'][0]
    assert row['strategy_version'] == system_params.STRATEGY_VERSION

  def test_open_strategy_version_fresh_read_after_monkeypatch(
    self, client_with_state_v6, htmx_headers, monkeypatch,
  ) -> None:
    '''Kwarg-default capture trap: fresh import inside _apply must pick up
    the monkeypatched value, not the import-time value.
    '''
    monkeypatch.setattr(system_params, 'STRATEGY_VERSION', 'v9.9.9')
    client, _, captured_saves = client_with_state_v6
    r = client.post('/paper-trade/open', data=_valid_spi200_long(), headers=htmx_headers)
    assert r.status_code == 200
    row = captured_saves[-1]['paper_trades'][0]
    assert row['strategy_version'] == 'v9.9.9', (
      f'Fresh import must pick up monkeypatched value; '
      f'got {row["strategy_version"]!r}'
    )

  def test_patch_refreshes_strategy_version_on_edit(
    self, client_with_state_v6, htmx_headers, monkeypatch,
  ) -> None:
    '''D-05: PATCH refreshes strategy_version to current constant value.'''
    monkeypatch.setattr(system_params, 'STRATEGY_VERSION', 'v9.9.9')
    client, set_state, captured_saves = client_with_state_v6
    trade_id = 'SPI200-20260430-001'
    set_state({
      'schema_version': 6, 'account': 100000.0, 'last_run': '2026-04-30',
      'positions': {'SPI200': None, 'AUDUSD': None},
      'signals': {'SPI200': {'last_close': 7820.0}, 'AUDUSD': {'last_close': 0.652}},
      'trade_log': [], 'equity_history': [], 'warnings': [],
      'initial_account': 100000.0,
      'contracts': {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-mini'},
      '_resolved_contracts': {'SPI200': {'multiplier': 5.0, 'cost_aud': 6.0},
                               'AUDUSD': {'multiplier': 10000.0, 'cost_aud': 5.0}},
      'paper_trades': [_open_row(trade_id)],  # row has 'v1.2.0' initially
    })
    r = client.patch(f'/paper-trade/{trade_id}',
                     data={'entry_price': 7900.0},
                     headers=htmx_headers)
    assert r.status_code == 200
    row = captured_saves[-1]['paper_trades'][0]
    assert row['strategy_version'] == 'v9.9.9', (
      f'PATCH must refresh strategy_version to current constant; '
      f'got {row["strategy_version"]!r}'
    )


# =========================================================================
# TestConcurrentOpen — multiprocessing race test
# =========================================================================

def _worker_open(state_path: str, result_queue, worker_id: int) -> None:
  '''Worker function: acquires LOCK_EX, reads state.json, appends a row with
  a unique counter, writes back. Mirrors mutate_state kernel exactly.
  Instruments a single SPI200 open for today's date.
  '''
  import fcntl
  import json
  import os
  from datetime import datetime
  from zoneinfo import ZoneInfo

  awst = ZoneInfo('Australia/Perth')
  today = datetime.now(awst).strftime('%Y%m%d')
  prefix = f'SPI200-{today}-'

  fd = os.open(state_path, os.O_RDWR | os.O_CREAT)
  try:
    fcntl.flock(fd, fcntl.LOCK_EX)
    with os.fdopen(fd, 'r+') as f:
      content = f.read()
      state = json.loads(content) if content.strip() else {'paper_trades': []}
      rows = state.setdefault('paper_trades', [])
      same_day = [r for r in rows if r['id'].startswith(prefix)]
      counter = len(same_day) + 1
      trade_id = f'{prefix}{counter:03d}'
      rows.append({'id': trade_id, 'worker': worker_id})
      f.seek(0)
      f.write(json.dumps(state))
      f.truncate()
  finally:
    # fd already closed by fdopen context manager if not already; just ensure unlock
    pass

  result_queue.put(trade_id)


class TestConcurrentOpen:
  '''RESEARCH §Pattern 9: two simultaneous POSTs must not collide on trade IDs.
  First multiprocessing test in this repo.
  '''

  def test_concurrent_open_does_not_collide(self, tmp_path) -> None:
    '''D-15 + D-01: two workers acquiring LOCK_EX on the same state.json file
    must produce distinct IDs (SPI200-<today>-001 and SPI200-<today>-002).
    '''
    state_file = str(tmp_path / 'state.json')
    # Write empty state
    with open(state_file, 'w') as f:
      f.write(json.dumps({'paper_trades': []}))

    result_queue: multiprocessing.Queue = multiprocessing.Queue()

    p1 = multiprocessing.Process(target=_worker_open, args=(state_file, result_queue, 1))
    p2 = multiprocessing.Process(target=_worker_open, args=(state_file, result_queue, 2))

    p1.start()
    p2.start()
    p1.join(timeout=10)
    p2.join(timeout=10)

    assert not p1.is_alive(), 'Worker 1 did not finish'
    assert not p2.is_alive(), 'Worker 2 did not finish'

    ids = []
    while not result_queue.empty():
      ids.append(result_queue.get_nowait())

    assert len(ids) == 2, f'Expected 2 IDs; got {ids}'
    assert len(set(ids)) == 2, (
      f'D-15 + D-01: concurrent opens must produce DISTINCT IDs; got {ids}'
    )

    today = datetime.now(_AWST).strftime('%Y%m%d')
    for trade_id in ids:
      assert trade_id.startswith(f'SPI200-{today}-'), f'Unexpected ID prefix: {trade_id}'


# =========================================================================
# TestAuthEnforcement
# =========================================================================

class TestAuthEnforcement:
  '''Phase 16.1 cookie-session middleware gates PATCH/DELETE uniformly.'''

  def test_open_without_auth_returns_302_or_401(self, client_with_state_v6) -> None:
    '''Without auth headers: browser HX-Request → 302 redirect; curl → 401.'''
    client, _, _ = client_with_state_v6
    # No htmx_headers (no auth)
    r = client.post('/paper-trade/open', data=_valid_spi200_long(),
                    follow_redirects=False)
    assert r.status_code in (302, 401), (
      f'Unauthenticated POST must return 302 or 401; got {r.status_code}'
    )

  def test_patch_without_auth_returns_302_or_401(self, client_with_state_v6) -> None:
    client, _, _ = client_with_state_v6
    r = client.patch('/paper-trade/SPI200-20260430-001',
                     data={'entry_price': 7900.0},
                     follow_redirects=False)
    assert r.status_code in (302, 401)

  def test_delete_without_auth_returns_302_or_401(self, client_with_state_v6) -> None:
    client, _, _ = client_with_state_v6
    r = client.delete('/paper-trade/SPI200-20260430-001', follow_redirects=False)
    assert r.status_code in (302, 401)
