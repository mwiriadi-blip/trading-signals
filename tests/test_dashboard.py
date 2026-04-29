'''Phase 5 test suite: dashboard render, formatters, stats math, goldens, atomic write.

Organized into 6 classes per D-13 (one class per concern dimension):
  TestStatsMath       — Wave 1 (VALIDATION 05-02-T1): _compute_sharpe, _compute_max_drawdown,
                        _compute_win_rate, _compute_total_return, _compute_unrealised_pnl_display.
  TestFormatters      — Wave 1 (VALIDATION 05-02-T2): _fmt_currency, _fmt_percent_*,
                        _fmt_pnl_with_colour, _fmt_em_dash, _fmt_last_updated.
  TestRenderBlocks    — Waves 1/2 (VALIDATION 05-02-T3 + 05-03-T1): per-block substring
                        asserts, palette presence, Chart.js SRI, XSS escape on exit_reason,
                        </script> injection defence.
  TestEmptyState      — Wave 2 (VALIDATION 05-03-T2): render_dashboard(reset_state()) byte-
                        matches committed golden_empty.html; all sections render.
  TestGoldenSnapshot  — Wave 2 (VALIDATION 05-03-T2): render_dashboard(sample_state) with
                        FROZEN_NOW byte-matches committed golden.html.
  TestAtomicWrite     — Wave 2 (VALIDATION 05-03-T2): tempfile + fsync + os.replace;
                        mirrors test_state_manager.py::TestAtomicity.

All tests use pytest's tmp_path for isolated HTML output — never write to the real
./dashboard.html. Clock determinism via the FROZEN_NOW module constant (no freezer
fixture needed — dashboard.py accepts a now= parameter).

Wave 0 (this commit): 6 empty class skeletons each with a `test_scaffold_placeholder`
method + module-level path constants + _make_state fixture helper (NotImplementedError
stub). Waves 1/2 fill in real test bodies.

C-1 reviews fix: pytz timezones must be applied via .localize(), NOT via
`datetime(..., tzinfo=pytz.timezone(...))`. Passing a pytz tz to datetime.tzinfo= yields
a historical LMT offset (+07:43:24 for Perth pre-1895) instead of the wall-clock AWST
(+08:00) we want. Use PERTH.localize(...) — always.
'''
import html  # noqa: F401 — Wave 1 TestRenderBlocks escape assertions
import json  # noqa: F401 — Wave 0 fixture loader
import math  # noqa: F401 — Wave 1 isfinite checks on stats output
import re
from datetime import datetime
from pathlib import Path
from unittest.mock import patch  # noqa: F401 — Wave 2 atomic-write patch targets land early

import pytest
import pytz

import dashboard
from dashboard import (  # noqa: F401 — render_dashboard is Wave 2 goldens
  _fmt_em_dash,
  render_dashboard,
)

# =========================================================================
# Module-level path + fixture constants
# =========================================================================

DASHBOARD_PATH = Path('dashboard.py')
TEST_DASHBOARD_PATH = Path('tests/test_dashboard.py')
REGENERATE_SCRIPT_PATH = Path('tests/regenerate_dashboard_golden.py')
DASHBOARD_FIXTURE_DIR = Path(__file__).parent / 'fixtures' / 'dashboard'
SAMPLE_STATE_PATH = DASHBOARD_FIXTURE_DIR / 'sample_state.json'
EMPTY_STATE_PATH = DASHBOARD_FIXTURE_DIR / 'empty_state.json'
GOLDEN_HTML_PATH = DASHBOARD_FIXTURE_DIR / 'golden.html'
GOLDEN_EMPTY_HTML_PATH = DASHBOARD_FIXTURE_DIR / 'golden_empty.html'

# C-1 reviews fix: pytz timezones must be applied via .localize(), NOT via
# tzinfo=. Passing a pytz tz to datetime.tzinfo= yields a historical LMT
# offset (+07:43:24 for Perth pre-1895) instead of the wall-clock AWST
# (+08:00) we want. Use PERTH.localize(...) instead.
PERTH = pytz.timezone('Australia/Perth')
FROZEN_NOW = PERTH.localize(datetime(2026, 4, 22, 9, 0))


# =========================================================================
# Test fixture helpers
# =========================================================================

def _make_state(
  account: float = 100_000.0,
  with_positions: bool = True,
  with_signals: bool = True,
  with_trades: int = 5,
  with_equity: int = 60,
) -> dict:
  '''Build a state dict with sensible defaults (mid-campaign by default).

  Mirrors state_manager.reset_state() top-level shape. Knobs let TestEmptyState
  request empty-scenario dicts. Trade shape is the authoritative 12-field schema
  per UI-SPEC F-8 hygiene note (instrument/direction/entry_date/exit_date/
  entry_price/exit_price/gross_pnl/n_contracts/exit_reason/multiplier/cost_aud/
  net_pnl).
  '''
  equity_history = [
    {'date': f'2026-01-{i + 1:02d}', 'equity': 100_000.0 + i * 50}
    for i in range(with_equity)
  ]
  # Authoritative 12-field trade schema (UI-SPEC F-8 + state_manager.record_trade D-20)
  trade_bases = [
    ('SPI200', 'LONG', 7850.0, 7920.0, 350.0, 347.0, 'stop_hit', 6.0, 5.0),
    ('AUDUSD', 'SHORT', 0.66, 0.658, 200.0, 197.5, 'flat_signal', 5.0, 10000.0),
    ('SPI200', 'SHORT', 7900.0, 7950.0, -250.0, -253.0, 'signal_reversal', 6.0, 5.0),
    ('AUDUSD', 'LONG', 0.652, 0.6555, 350.0, 347.5, 'adx_exit', 5.0, 10000.0),
    ('SPI200', 'LONG', 7980.0, 8020.0, 200.0, 197.0, 'flat_signal', 6.0, 5.0),
  ]
  trade_log = []
  for i in range(with_trades):
    base = trade_bases[i % len(trade_bases)]
    trade_log.append({
      'instrument': base[0],
      'direction': base[1],
      'entry_date': f'2026-02-{(i * 7 % 28) + 1:02d}',
      'exit_date': f'2026-02-{(i * 7 % 28) + 7:02d}',
      'entry_price': base[2],
      'exit_price': base[3],
      'gross_pnl': base[4],
      'n_contracts': 1,
      'exit_reason': base[6],
      'multiplier': base[8],
      'cost_aud': base[7],
      'net_pnl': base[5],
    })
  positions = {'SPI200': None, 'AUDUSD': None}
  if with_positions:
    positions['SPI200'] = {
      'atr_entry': 50.0,
      'direction': 'LONG',
      'entry_date': '2026-04-10',
      'entry_price': 8000.0,
      'n_contracts': 2,
      'peak_price': 8100.0,
      'pyramid_level': 0,
      'trough_price': None,
    }
  signals = {}
  if with_signals:
    signals = {
      'SPI200': {
        'as_of_run': '2026-04-21T09:00:00+08:00',
        'last_close': 8085.0,
        'last_scalars': {
          'adx': 32.5, 'atr': 50.0, 'mom1': 0.031, 'mom12': 0.092,
          'mom3': 0.048, 'ndi': 12.4, 'pdi': 28.1, 'rvol': 1.12,
        },
        'signal': 1,
        'signal_as_of': '2026-04-21',
      },
      'AUDUSD': {
        'as_of_run': '2026-04-21T09:00:00+08:00',
        'last_close': 0.6502,
        'last_scalars': {
          'adx': 18.3, 'atr': 0.0042, 'mom1': -0.005, 'mom12': 0.014,
          'mom3': 0.001, 'ndi': 21.2, 'pdi': 19.0, 'rvol': 0.95,
        },
        'signal': 0,
        'signal_as_of': '2026-04-21',
      },
    }
  return {
    'account': account,
    'equity_history': equity_history,
    'last_run': '2026-04-21',
    'positions': positions,
    'schema_version': 1,
    'signals': signals,
    'trade_log': trade_log,
    'warnings': [],
  }


def _make_render_state_with_position(manual_stop=None):
  '''Phase 14 render-test helper: state dict suitable for render_dashboard()
  with one open SPI200 LONG position. Optional manual_stop value.

  Mirrors state_manager.reset_state shape with the Phase 14 v3 schema
  (position dict carries `manual_stop` field). Includes _resolved_contracts
  so _compute_unrealised_pnl_display sources the right tier.
  '''
  return {
    'schema_version': 3,
    'account': 100_000.0,
    'last_run': '2026-04-25',
    'positions': {
      'SPI200': {
        'direction': 'LONG', 'entry_price': 7800.0, 'entry_date': '2026-04-20',
        'n_contracts': 2, 'pyramid_level': 0,
        'peak_price': 8100.0, 'trough_price': None,
        'atr_entry': 50.0, 'manual_stop': manual_stop,
      },
      'AUDUSD': None,
    },
    'signals': {
      'SPI200': {'last_close': 8000.0},
      'AUDUSD': {},
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
# Test classes — one per concern dimension (D-13)
# =========================================================================

class TestStatsMath:
  '''Wave 1 (VALIDATION rows 05-02-T1): unit tests for
  _compute_sharpe, _compute_max_drawdown, _compute_win_rate,
  _compute_total_return, _compute_trail_stop_display, _compute_unrealised_pnl_display.
  Happy path + empty history + under-30-samples + flat equity + non-positive equity +
  all-losses + all-wins + sizing_engine parity + trail-stop fallback.
  '''

  # --- Sharpe ---

  def test_sharpe_happy_path(self) -> None:
    '''60 realistic floats → finite Sharpe formatted as f".2f".'''
    equities = [100000 + i * 50 for i in range(60)]
    state = {
      'equity_history': [
        {'date': f'2026-01-{i + 1:02d}', 'equity': e} for i, e in enumerate(equities)
      ],
    }
    result = dashboard._compute_sharpe(state)
    assert result != _fmt_em_dash()
    assert re.match(r'^-?\d+\.\d{2}$', result), f'expected f".2f" format, got {result!r}'

  def test_sharpe_returns_dash_under_30_samples(self) -> None:
    '''<30 equity rows → em-dash per CONTEXT D-07.'''
    state = {
      'equity_history': [
        {'date': f'2026-01-{i + 1:02d}', 'equity': 100000 + i} for i in range(25)
      ],
    }
    assert dashboard._compute_sharpe(state) == '—'

  def test_sharpe_returns_dash_on_flat_equity(self) -> None:
    '''Flat equity (stdev==0) → em-dash (Pitfall 3 belt-and-braces).'''
    state = {
      'equity_history': [
        {'date': f'2026-01-{i + 1:02d}', 'equity': 100000.0} for i in range(40)
      ],
    }
    assert dashboard._compute_sharpe(state) == '—'

  def test_sharpe_returns_dash_on_zero_or_negative_equity(self) -> None:
    '''Non-positive equity → em-dash (Pitfall 4: math.log domain error guard).'''
    equities = [100000, 50000, 0, -1000] + [1000 + i for i in range(30)]
    state = {
      'equity_history': [
        {'date': f'2026-01-{i + 1:02d}', 'equity': float(e)} for i, e in enumerate(equities)
      ],
    }
    assert dashboard._compute_sharpe(state) == '—'

  def test_sharpe_returns_dash_on_empty_history(self) -> None:
    '''Empty equity_history → em-dash.'''
    assert dashboard._compute_sharpe({'equity_history': []}) == '—'

  # --- Max Drawdown ---

  def test_max_drawdown_happy_path(self) -> None:
    '''Peak-to-trough %: min over (eq - running_max)/running_max for [100k,105k,95k,110k,90k]
    → running_max hits 110k, trough 90k → (90k-110k)/110k*100 = -18.2%.'''
    equities = [100000, 105000, 95000, 110000, 90000]
    state = {
      'equity_history': [
        {'date': f'2026-01-{i + 1:02d}', 'equity': float(e)} for i, e in enumerate(equities)
      ],
    }
    assert dashboard._compute_max_drawdown(state) == '-18.2%'

  def test_max_drawdown_returns_dash_on_empty(self) -> None:
    '''Empty equity_history → em-dash.'''
    assert dashboard._compute_max_drawdown({'equity_history': []}) == '—'

  def test_max_drawdown_all_time_high(self) -> None:
    '''Monotonically increasing equities → max DD = 0.0%.'''
    equities = [100000 + i * 100 for i in range(10)]
    state = {
      'equity_history': [
        {'date': f'2026-01-{i + 1:02d}', 'equity': float(e)} for i, e in enumerate(equities)
      ],
    }
    assert dashboard._compute_max_drawdown(state) == '0.0%'

  # --- Win Rate ---

  def test_win_rate_happy_path(self) -> None:
    '''3 wins out of 5 gross_pnl values [100, -50, 200, -30, 150] → 60.0%.'''
    trades = [
      {'gross_pnl': 100.0}, {'gross_pnl': -50.0}, {'gross_pnl': 200.0},
      {'gross_pnl': -30.0}, {'gross_pnl': 150.0},
    ]
    state = {'trade_log': trades}
    assert dashboard._compute_win_rate(state) == '60.0%'

  def test_win_rate_returns_dash_on_empty_log(self) -> None:
    '''Empty trade_log → em-dash per CONTEXT D-09.'''
    assert dashboard._compute_win_rate({'trade_log': []}) == '—'

  def test_win_rate_uses_gross_pnl_not_net_pnl(self) -> None:
    '''CONTEXT D-09: gross_pnl > 0 counts as win (industry "win before costs" convention).
    A trade with gross_pnl=5.0 but net_pnl=-1.0 IS a win.'''
    trades = [
      {'gross_pnl': 5.0, 'net_pnl': -1.0},   # win (gross > 0)
      {'gross_pnl': -10.0, 'net_pnl': -15.0},  # loss
    ]
    state = {'trade_log': trades}
    assert dashboard._compute_win_rate(state) == '50.0%'

  # --- Total Return ---

  def test_total_return_happy_path(self) -> None:
    '''current_equity 104532.18 → (104532.18-100000)/100000 = 0.0453218 → "+4.5%".'''
    state = {'equity_history': [{'date': '2026-04-24', 'equity': 104532.18}]}
    assert dashboard._compute_total_return(state) == '+4.5%'

  def test_total_return_negative(self) -> None:
    '''current_equity 95000 → -5.0%.'''
    state = {'equity_history': [{'date': '2026-04-24', 'equity': 95000.0}]}
    assert dashboard._compute_total_return(state) == '-5.0%'

  def test_total_return_from_account_when_history_empty(self) -> None:
    '''Empty history → fall back to state["account"] per CONTEXT D-10.'''
    state = {'equity_history': [], 'account': 100000.0}
    assert dashboard._compute_total_return(state) == '+0.0%'

  def test_total_return_zero_when_equal_to_initial(self) -> None:
    '''equity == INITIAL_ACCOUNT → "+0.0%" (signed format locked).'''
    state = {'equity_history': [{'date': '2026-01-01', 'equity': 100000.0}]}
    assert dashboard._compute_total_return(state) == '+0.0%'

  # --- Unrealised P&L display (inline re-implementation parity) ---

  def test_unrealised_pnl_matches_sizing_engine(self) -> None:
    '''VALIDATION row 05-02-T1: hex-boundary re-implementation parity check.

    dashboard._compute_unrealised_pnl_display (inline in dashboard.py per D-01 hex
    fence) must produce bit-identical output to sizing_engine.compute_unrealised_pnl
    on a shared fixture. Drift between the two surfaces a red test.

    Note: sizing_engine import is a TEST dependency, NOT a dashboard.py dependency —
    the AST blocklist only scans dashboard.py (not tests/). Hex fence intact.
    '''
    import sizing_engine  # test-only import (D-01 allows in tests/)
    from system_params import SPI_COST_AUD, SPI_MULT

    # LONG case
    long_pos = {
      'direction': 'LONG', 'entry_price': 8000.0, 'entry_date': '2026-04-10',
      'n_contracts': 2, 'pyramid_level': 0, 'peak_price': 8100.0,
      'trough_price': None, 'atr_entry': 50.0,
    }
    current_close = 8085.0
    dashboard_long = dashboard._compute_unrealised_pnl_display(long_pos, 'SPI200', current_close)
    sizing_long = sizing_engine.compute_unrealised_pnl(
      long_pos, current_close, SPI_MULT, SPI_COST_AUD / 2,
    )
    assert dashboard_long == pytest.approx(sizing_long)

    # SHORT case
    short_pos = {
      'direction': 'SHORT', 'entry_price': 8000.0, 'entry_date': '2026-04-10',
      'n_contracts': 1, 'pyramid_level': 0, 'peak_price': None,
      'trough_price': 7800.0, 'atr_entry': 50.0,
    }
    current_close_short = 7820.0
    dashboard_short = dashboard._compute_unrealised_pnl_display(
      short_pos, 'SPI200', current_close_short,
    )
    sizing_short = sizing_engine.compute_unrealised_pnl(
      short_pos, current_close_short, SPI_MULT, SPI_COST_AUD / 2,
    )
    assert dashboard_short == pytest.approx(sizing_short)

  def test_unrealised_pnl_returns_none_when_last_close_missing(self) -> None:
    '''current_close=None → None (caller renders em-dash; math helper stays pure).'''
    position = {
      'direction': 'LONG', 'entry_price': 8000.0, 'entry_date': '2026-04-10',
      'n_contracts': 2, 'pyramid_level': 0, 'peak_price': 8100.0,
      'trough_price': None, 'atr_entry': 50.0,
    }
    assert dashboard._compute_unrealised_pnl_display(position, 'SPI200', None) is None

  # --- Trail stop display ---

  def test_trail_stop_long(self) -> None:
    '''LONG: peak_price - TRAIL_MULT_LONG(3.0) * atr_entry(50.0) = 8100 - 150 = 7950.0.'''
    position = {
      'direction': 'LONG', 'peak_price': 8100.0, 'trough_price': None,
      'entry_price': 8000.0, 'atr_entry': 50.0,
    }
    assert dashboard._compute_trail_stop_display(position) == pytest.approx(7950.0)

  def test_trail_stop_short(self) -> None:
    '''SHORT: trough_price + TRAIL_MULT_SHORT(2.0) * atr_entry(50.0) = 7800 + 100 = 7900.0.'''
    position = {
      'direction': 'SHORT', 'peak_price': None, 'trough_price': 7800.0,
      'entry_price': 8000.0, 'atr_entry': 50.0,
    }
    assert dashboard._compute_trail_stop_display(position) == pytest.approx(7900.0)

  def test_trail_stop_long_fallback_to_entry(self) -> None:
    '''LONG with peak_price=None falls back to entry_price. 8000 - 3.0 * 50 = 7850.0.'''
    position = {
      'direction': 'LONG', 'peak_price': None, 'trough_price': None,
      'entry_price': 8000.0, 'atr_entry': 50.0,
    }
    assert dashboard._compute_trail_stop_display(position) == pytest.approx(7850.0)


class TestUnrealisedPnlUsesResolvedContracts:
  '''Phase 8 WR-01: _compute_unrealised_pnl_display MUST source the tier
  multiplier/cost from state['_resolved_contracts'][state_key] so operators
  who --reset with a non-default tier (e.g. spi-standard, spi-full) see
  correct unrealised P&L on the dashboard — not the hardcoded spi-mini
  scalar default. Fallback to module-level _CONTRACT_SPECS only when
  _resolved_contracts is absent (pre-Phase-8 state or direct unit-test
  construction).
  '''

  def test_standard_tier_uses_25_multiplier(self) -> None:
    '''spi-standard: multiplier=25.0, cost_aud=30.0. LONG 2 contracts
    entry=7000, current=7100 → gross = 100 * 2 * 25 = 5000.
    cost_open = 30/2 * 2 = 30. unrealised = 5000 - 30 = 4970.
    '''
    position = {
      'direction': 'LONG', 'entry_price': 7000.0, 'entry_date': '2026-04-10',
      'n_contracts': 2, 'pyramid_level': 0, 'peak_price': 7100.0,
      'trough_price': None, 'atr_entry': 50.0,
    }
    state = {
      '_resolved_contracts': {
        'SPI200':  {'multiplier': 25.0, 'cost_aud': 30.0},
        'AUDUSD':  {'multiplier': 10000.0, 'cost_aud': 5.0},
      },
    }
    result = dashboard._compute_unrealised_pnl_display(
      position, 'SPI200', 7100.0, state,
    )
    assert result == pytest.approx(4970.0)

  def test_full_tier_uses_50_multiplier(self) -> None:
    '''spi-full: multiplier=50.0, cost_aud=50.0. LONG 1 contract
    entry=7000, current=7100 → gross = 100 * 1 * 50 = 5000.
    cost_open = 50/2 * 1 = 25. unrealised = 5000 - 25 = 4975.
    '''
    position = {
      'direction': 'LONG', 'entry_price': 7000.0, 'entry_date': '2026-04-10',
      'n_contracts': 1, 'pyramid_level': 0, 'peak_price': 7100.0,
      'trough_price': None, 'atr_entry': 50.0,
    }
    state = {
      '_resolved_contracts': {
        'SPI200':  {'multiplier': 50.0, 'cost_aud': 50.0},
        'AUDUSD':  {'multiplier': 10000.0, 'cost_aud': 5.0},
      },
    }
    result = dashboard._compute_unrealised_pnl_display(
      position, 'SPI200', 7100.0, state,
    )
    assert result == pytest.approx(4975.0)

  def test_missing_resolved_contracts_falls_back_to_mini_defaults(
      self, caplog) -> None:
    '''State without _resolved_contracts key (pre-Phase-8 shape or unit-test
    direct construction) → falls back to module-level _CONTRACT_SPECS
    (spi-mini = 5.0 multiplier, 6.0 cost_aud). Debug log emitted.

    LONG 2 contracts entry=7000, current=7100 → gross = 100*2*5 = 1000.
    cost_open = 6/2 * 2 = 6. unrealised = 1000 - 6 = 994.
    '''
    import logging
    position = {
      'direction': 'LONG', 'entry_price': 7000.0, 'entry_date': '2026-04-10',
      'n_contracts': 2, 'pyramid_level': 0, 'peak_price': 7100.0,
      'trough_price': None, 'atr_entry': 50.0,
    }
    state = {}  # No _resolved_contracts
    with caplog.at_level(logging.DEBUG, logger='dashboard'):
      result = dashboard._compute_unrealised_pnl_display(
        position, 'SPI200', 7100.0, state,
      )
    assert result == pytest.approx(994.0)
    assert any(
      '_resolved_contracts missing' in rec.message for rec in caplog.records
    ), 'WR-01 fallback should emit a DEBUG log line naming the missing key'

  def test_state_none_also_falls_back(self) -> None:
    '''state=None → same fallback to module-level defaults (backward
    compatibility with older call sites / pytest parity checks).
    '''
    position = {
      'direction': 'LONG', 'entry_price': 7000.0, 'entry_date': '2026-04-10',
      'n_contracts': 1, 'pyramid_level': 0, 'peak_price': 7100.0,
      'trough_price': None, 'atr_entry': 50.0,
    }
    # multiplier=5.0, cost_aud=6.0. gross = 100*1*5 = 500. open_cost = 3.
    result = dashboard._compute_unrealised_pnl_display(
      position, 'SPI200', 7100.0, None,
    )
    assert result == pytest.approx(497.0)


class TestFormatters:
  '''Wave 1 (VALIDATION rows 05-02-T2): unit tests for
  _fmt_currency, _fmt_percent_signed, _fmt_percent_unsigned, _fmt_pnl_with_colour,
  _fmt_em_dash, _fmt_last_updated. Covers positive/negative/zero/edge cases +
  naive-datetime rejection (Pitfall 9).
  '''

  # --- _fmt_currency ---

  def test_fmt_currency_positive(self) -> None:
    assert dashboard._fmt_currency(1234.56) == '$1,234.56'

  def test_fmt_currency_negative(self) -> None:
    '''Negative uses leading -$, NOT parentheses (UI-SPEC §Format Helper Contracts).'''
    assert dashboard._fmt_currency(-567.89) == '-$567.89'

  def test_fmt_currency_zero(self) -> None:
    '''Always 2 dp, never collapses to "$0".'''
    assert dashboard._fmt_currency(0.0) == '$0.00'

  def test_fmt_currency_large(self) -> None:
    '''Thousands separator, no K/M suffix.'''
    assert dashboard._fmt_currency(100000.0) == '$100,000.00'

  def test_fmt_currency_small_fraction(self) -> None:
    '''Small negative fractions keep the 2dp + leading -$.'''
    assert dashboard._fmt_currency(-0.01) == '-$0.01'

  # --- _fmt_percent_signed ---

  def test_fmt_percent_signed_positive(self) -> None:
    '''Input 0.053 → "+5.3%".'''
    assert dashboard._fmt_percent_signed(0.053) == '+5.3%'

  def test_fmt_percent_signed_negative(self) -> None:
    '''Input -0.125 → "-12.5%".'''
    assert dashboard._fmt_percent_signed(-0.125) == '-12.5%'

  def test_fmt_percent_signed_zero(self) -> None:
    '''Python +.1f on 0.0 yields "+0.0%" — UI-SPEC locks this behaviour.'''
    assert dashboard._fmt_percent_signed(0.0) == '+0.0%'

  # --- _fmt_percent_unsigned ---

  def test_fmt_percent_unsigned_positive(self) -> None:
    assert dashboard._fmt_percent_unsigned(0.583) == '58.3%'

  def test_fmt_percent_unsigned_negative(self) -> None:
    '''Max DD uses unsigned format but negative sign appears naturally from negative input.'''
    assert dashboard._fmt_percent_unsigned(-0.125) == '-12.5%'

  # --- _fmt_pnl_with_colour ---

  def test_fmt_pnl_with_colour_positive(self) -> None:
    '''Positive → LONG green, "+" prefix.'''
    result = dashboard._fmt_pnl_with_colour(1234.56)
    assert '#22c55e' in result
    assert '+$1,234.56' in result

  def test_fmt_pnl_with_colour_negative(self) -> None:
    '''Negative → SHORT red, leading -$.'''
    result = dashboard._fmt_pnl_with_colour(-567.89)
    assert '#ef4444' in result
    assert '-$567.89' in result

  def test_fmt_pnl_with_colour_zero(self) -> None:
    '''Zero → muted colour, no "+" or "-" prefix.'''
    result = dashboard._fmt_pnl_with_colour(0.0)
    assert '#cbd5e1' in result
    assert '$0.00' in result
    assert '+$0.00' not in result
    assert '-$0.00' not in result

  # --- _fmt_em_dash ---

  def test_fmt_em_dash(self) -> None:
    '''Single U+2014 codepoint.'''
    result = dashboard._fmt_em_dash()
    assert result == '—'
    assert len(result) == 1
    assert ord(result) == 0x2014

  # --- _fmt_last_updated ---

  def test_fmt_last_updated_awst(self) -> None:
    '''VALIDATION row 05-02-T2 AWST test. C-1 reviews: use PERTH.localize(...) —
    datetime(..., tzinfo=pytz.timezone(...)) silently picks historical LMT offset
    (+07:43:24 for Perth pre-1895) instead of +08:00 AWST.'''
    now = PERTH.localize(datetime(2026, 4, 22, 9, 0))
    assert dashboard._fmt_last_updated(now) == '2026-04-22 09:00 AWST'

  def test_fmt_last_updated_rejects_naive_datetime(self) -> None:
    '''RESEARCH Pitfall 9: naive datetime silently breaks golden-snapshot byte stability.'''
    with pytest.raises(ValueError, match='timezone-aware'):
      dashboard._fmt_last_updated(datetime(2026, 4, 22, 9, 0))  # no tzinfo

  def test_fmt_last_updated_converts_utc_to_awst(self) -> None:
    '''Perth is UTC+8, no DST. 01:00 UTC → 09:00 AWST.'''
    utc_now = datetime(2026, 4, 22, 1, 0, tzinfo=pytz.UTC)
    assert dashboard._fmt_last_updated(utc_now) == '2026-04-22 09:00 AWST'


class TestRenderBlocks:
  '''Wave 1/2 (VALIDATION rows 05-02-T3 + 05-03-T1): per-block substring
  asserts, palette presence, Chart.js SRI match, no-external-stylesheet,
  </script> injection defence, XSS escape on exit_reason.
  Wave 1 populates per-block substring + colour + copy + per-surface XSS tests.
  '''

  # --- Header ---

  def test_header_contains_title_and_awst_timestamp(self) -> None:
    '''UI-SPEC §Header: H1, subtitle (escaped &), Last-updated AWST.'''
    state = _make_state()
    output = dashboard._render_header(state, FROZEN_NOW)
    assert '<h1>Trading Signals</h1>' in output
    # The '&' in 'SPI 200 & AUD/USD mechanical system' must be escaped to &amp;
    assert 'SPI 200 &amp; AUD/USD mechanical system' in output
    assert '2026-04-22 09:00 AWST' in output

  def test_header_uses_render_header_signature(self) -> None:
    '''_render_header inherits _fmt_last_updated's naive-datetime rejection.'''
    state = _make_state()
    with pytest.raises(ValueError, match='timezone-aware'):
      dashboard._render_header(state, datetime(2026, 4, 22, 9, 0))  # naive

  # --- Signal cards ---

  def test_signal_card_colours(self) -> None:
    '''VALIDATION row 05-02-T3: LONG=green, SHORT=red, FLAT=gold.'''
    state = _make_state()
    state['signals']['SPI200']['signal'] = 1
    state['signals']['AUDUSD']['signal'] = -1
    output = dashboard._render_signal_cards(state)
    assert '#22c55e' in output  # LONG chip
    assert '#ef4444' in output  # SHORT chip

    state['signals']['SPI200']['signal'] = 0
    state['signals']['AUDUSD']['signal'] = 0
    output = dashboard._render_signal_cards(state)
    assert '#eab308' in output  # FLAT chip

  def test_signal_card_empty_state(self) -> None:
    '''Missing signal entry: "Signal as of never" + FLAT colour.'''
    state = _make_state()
    state['signals'] = {}
    output = dashboard._render_signal_cards(state)
    assert 'Signal as of never' in output
    assert '#eab308' in output  # FLAT colour

  def test_signal_card_displays_instrument_names(self) -> None:
    '''Display names (not raw state keys).'''
    state = _make_state()
    output = dashboard._render_signal_cards(state)
    assert 'SPI 200' in output
    assert 'AUD / USD' in output

  def test_signal_card_shows_scalars(self) -> None:
    '''Scalars: ADX formatted .1f, Mom* as signed percent.'''
    state = _make_state()
    state['signals']['SPI200']['last_scalars'] = {
      'adx': 32.5, 'mom1': 0.031, 'mom3': 0.048, 'mom12': 0.092,
      'rvol': 1.12, 'atr': 50.0, 'pdi': 28.1, 'ndi': 12.4,
    }
    output = dashboard._render_signal_cards(state)
    assert '32.5' in output  # ADX
    assert '+3.1%' in output  # Mom1 as signed percent

  def test_signal_card_escapes_signal_as_of(self) -> None:
    '''C-5 reviews per-surface XSS coverage: signal_as_of value MUST be escaped at leaf.

    Operator-authored state is trusted-by-filesystem but D-15 requires leaf-level
    escape as belt-and-braces — every state-derived string on every surface.
    '''
    state = _make_state()
    state['signals']['SPI200']['signal_as_of'] = '<script>alert(1)</script>'
    output = dashboard._render_signal_cards(state)
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in output
    assert '<script>' not in output

  # --- Positions table ---

  def test_positions_table_columns_and_values(self) -> None:
    '''VALIDATION row 05-02-T3: 8 cols + SPI200 row values from sample_state.json.'''
    with SAMPLE_STATE_PATH.open('r', encoding='utf-8') as fh:
      state = json.load(fh)
    output = dashboard._render_positions_table(state)
    for header in (
      'Instrument', 'Direction', 'Entry', 'Current', 'Contracts',
      'Pyramid', 'Trail Stop', 'Unrealised P&amp;L',
    ):
      assert header in output, f'missing header: {header!r}'
    assert '$8,000.00' in output  # entry
    assert '$8,085.00' in output  # current (from state['signals']['SPI200']['last_close'])
    assert '>2<' in output         # contracts cell (use angle brackets to avoid matching other '2')
    assert 'Lvl 0' in output       # pyramid
    assert '$7,950.00' in output   # trail stop = 8100 - 3*50

  def test_positions_table_empty_state_colspan_9(self) -> None:
    '''Phase 14 UI-SPEC §Decision 2: empty-state colspan bumped 8 → 9 to span
    the new Actions column. Was colspan="8" pre-Phase-14 (UI-SPEC F-4 / CONTEXT
    D-13 history retained for trail).

    Phase 15 CALC-02: empty-state placeholder only renders when there are
    no positions AND no entry-target rows. Set signals to FLAT for both
    instruments so the entry-target render path returns '' and the
    empty-state branch fires.
    '''
    state = _make_state()
    state['positions'] = {'SPI200': None, 'AUDUSD': None}
    state['signals'] = {
      'SPI200': {'signal': 0, 'last_close': 8085.0,
                  'last_scalars': {'atr': 50.0, 'rvol': 1.0}},
      'AUDUSD': {'signal': 0, 'last_close': 0.6500,
                  'last_scalars': {'atr': 0.005, 'rvol': 1.0}},
    }
    output = dashboard._render_positions_table(state)
    assert 'colspan="9"' in output
    assert 'colspan="8"' not in output, 'stale colspan=8 must not appear'
    assert '— No open positions —' in output

  def test_positions_table_last_close_missing_renders_em_dash(self) -> None:
    '''Position present but last_close=None → Current + Unrealised P&L em-dashed.'''
    state = _make_state()
    state['signals']['SPI200']['last_close'] = None
    output = dashboard._render_positions_table(state)
    # There should be exactly 2 em-dashes in the SPI200 row: Current + Unrealised.
    # Use a substring that's unambiguous — the Current column's <td class="num">—</td>.
    assert '<td class="num">—</td>' in output

  def test_positions_table_escapes_display_fallback(self) -> None:
    '''C-5 reviews per-surface XSS coverage: unknown instrument key falls back via
    html.escape at leaf.

    The standard iteration uses _INSTRUMENT_DISPLAY_NAMES which is a fixed constant,
    but the direction cell, entry price, and all other state-derived cells do flow
    through html.escape. This test confirms the discipline by injecting an XSS
    payload into an escapable cell (pyramid level as a crafted string). Since
    _INSTRUMENT_DISPLAY_NAMES is a locked module constant, the nearest falloff
    path is the pyramid_level string — which flows through html.escape(f'Lvl {n}').
    We verify the leaf-escape discipline using a string payload in pyramid_level.
    '''
    state = _make_state()
    state['positions']['SPI200']['pyramid_level'] = '<img src=x onerror=alert(1)>'
    output = dashboard._render_positions_table(state)
    assert '&lt;img src=x onerror=alert(1)&gt;' in output
    assert '<img src=x' not in output

  # --- Trades table ---

  def test_trades_table_slice_and_order(self) -> None:
    '''VALIDATION row 05-02-T3: 25 trades → render exactly 20 <tbody> rows, newest first.'''
    state = _make_state(with_trades=5)
    # Build 25 synthetic trades with unique exit_dates so order is verifiable
    trades = []
    for i in range(25):
      trades.append({
        'instrument': 'SPI200', 'direction': 'LONG',
        'entry_date': f'2026-02-{(i % 27) + 1:02d}',
        'exit_date': f'2026-03-{(i % 27) + 1:02d}',
        'entry_price': 8000.0 + i, 'exit_price': 8050.0 + i,
        'gross_pnl': 250.0, 'n_contracts': 1, 'exit_reason': 'flat_signal',
        'multiplier': 5.0, 'cost_aud': 6.0, 'net_pnl': 247.0,
      })
    state['trade_log'] = trades
    output = dashboard._render_trades_table(state)
    # Count tbody rows. The thead <tr> and the tbody <tr>s are both '<tr>';
    # tbody rows are inside <tbody>. Count inside the tbody slice.
    tbody_start = output.find('<tbody>')
    tbody_end = output.find('</tbody>')
    tbody_slice = output[tbody_start:tbody_end]
    tr_count = tbody_slice.count('<tr>')
    assert tr_count == 20, f'expected 20 tbody rows, got {tr_count}'
    # Newest-first: trades[-1] is the last trade pushed; its exit_date is '2026-03-25'
    # (i=24 → (24 % 27) + 1 = 25). The FIRST rendered row should reference this date.
    first_tr_start = tbody_slice.find('<tr>')
    first_tr_end = tbody_slice.find('</tr>', first_tr_start)
    first_row = tbody_slice[first_tr_start:first_tr_end]
    assert '2026-03-25' in first_row, f'first row should be newest; got {first_row!r}'

  def test_trades_table_empty_state_colspan_7(self) -> None:
    '''Empty trade_log → colspan="7" placeholder.'''
    state = _make_state()
    state['trade_log'] = []
    output = dashboard._render_trades_table(state)
    assert 'colspan="7"' in output
    assert '— No closed trades yet —' in output

  def test_trades_table_exit_reason_display_map(self) -> None:
    '''Mapped exit_reasons render as display text, not raw keys.'''
    state = _make_state(with_trades=0)
    state['trade_log'] = [
      {'instrument': 'SPI200', 'direction': 'LONG', 'entry_date': '2026-02-01',
       'exit_date': '2026-02-07', 'entry_price': 8000.0, 'exit_price': 8050.0,
       'gross_pnl': 250.0, 'n_contracts': 1, 'exit_reason': 'flat_signal',
       'multiplier': 5.0, 'cost_aud': 6.0, 'net_pnl': 247.0},
      {'instrument': 'AUDUSD', 'direction': 'SHORT', 'entry_date': '2026-02-08',
       'exit_date': '2026-02-14', 'entry_price': 0.66, 'exit_price': 0.658,
       'gross_pnl': 200.0, 'n_contracts': 1, 'exit_reason': 'signal_reversal',
       'multiplier': 10000.0, 'cost_aud': 5.0, 'net_pnl': 197.5},
      {'instrument': 'SPI200', 'direction': 'LONG', 'entry_date': '2026-02-15',
       'exit_date': '2026-02-22', 'entry_price': 7900.0, 'exit_price': 7920.0,
       'gross_pnl': 100.0, 'n_contracts': 1, 'exit_reason': 'stop_hit',
       'multiplier': 5.0, 'cost_aud': 6.0, 'net_pnl': 97.0},
      {'instrument': 'AUDUSD', 'direction': 'LONG', 'entry_date': '2026-02-23',
       'exit_date': '2026-03-01', 'entry_price': 0.65, 'exit_price': 0.655,
       'gross_pnl': 500.0, 'n_contracts': 1, 'exit_reason': 'adx_exit',
       'multiplier': 10000.0, 'cost_aud': 5.0, 'net_pnl': 497.5},
    ]
    output = dashboard._render_trades_table(state)
    assert 'Signal flat' in output
    assert 'Reversal' in output
    assert 'Stop hit' in output
    assert 'ADX drop' in output
    # Raw keys MUST NOT appear as displayed text
    assert 'flat_signal' not in output
    assert 'signal_reversal' not in output

  def test_escape_applied_to_exit_reason(self) -> None:
    '''VALIDATION row 05-02-T2 XSS test: mapped exit reasons get escaped at leaf.

    Even a known-key exit_reason passes through html.escape; if the payload
    were injected into a known-map value, the leaf escape catches it. This
    test specifically exercises a <script> payload.
    '''
    state = _make_state(with_trades=0)
    state['trade_log'] = [
      {'instrument': 'SPI200', 'direction': 'LONG', 'entry_date': '2026-02-01',
       'exit_date': '2026-02-07', 'entry_price': 8000.0, 'exit_price': 8050.0,
       'gross_pnl': 250.0, 'n_contracts': 1,
       'exit_reason': '<script>alert(1)</script>',
       'multiplier': 5.0, 'cost_aud': 6.0, 'net_pnl': 247.0},
    ]
    output = dashboard._render_trades_table(state)
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in output
    assert '<script>alert(1)</script>' not in output

  def test_trades_table_escapes_unknown_exit_reason(self) -> None:
    '''C-5 reviews per-surface XSS coverage: unknown exit_reason (display-map miss)
    falls through html.escape at leaf.'''
    state = _make_state(with_trades=0)
    state['trade_log'] = [
      {'instrument': 'SPI200', 'direction': 'LONG', 'entry_date': '2026-02-01',
       'exit_date': '2026-02-07', 'entry_price': 8000.0, 'exit_price': 8050.0,
       'gross_pnl': 250.0, 'n_contracts': 1,
       'exit_reason': '<img src=x onerror=alert(1)>',
       'multiplier': 5.0, 'cost_aud': 6.0, 'net_pnl': 247.0},
    ]
    output = dashboard._render_trades_table(state)
    assert '&lt;img src=x onerror=alert(1)&gt;' in output
    assert '<img src=x' not in output

  # --- Key stats block ---

  def test_key_stats_block(self) -> None:
    '''VALIDATION row 05-02-T3: 4 labels + computed values on sample_state.'''
    with SAMPLE_STATE_PATH.open('r', encoding='utf-8') as fh:
      state = json.load(fh)
    output = dashboard._render_key_stats(state)
    for label in ('Total Return', 'Sharpe', 'Max Drawdown', 'Win Rate'):
      assert label in output, f'missing label: {label!r}'
    # Sample state fixture ends at equity=104532.18 → +4.5% total return
    assert '+4.5%' in output
    # Sample state has 60 equity rows (monotonic increase) → 0.0% max DD
    assert '0.0%' in output
    # 5 trades with gross_pnl [350, 200, -250, 350, 200] → 4/5 = 80.0% win rate
    assert '80.0%' in output

  def test_key_stats_total_return_coloured(self) -> None:
    '''Tile 1 (Total Return) coloured — positive green, negative red, zero muted.'''
    # Positive
    state = _make_state(with_equity=1, with_trades=0, with_positions=False, with_signals=False)
    state['equity_history'] = [{'date': '2026-01-01', 'equity': 105_000.0}]
    output = dashboard._render_key_stats(state)
    assert '#22c55e' in output

    # Negative
    state['equity_history'] = [{'date': '2026-01-01', 'equity': 95_000.0}]
    output = dashboard._render_key_stats(state)
    assert '#ef4444' in output

    # Zero
    state['equity_history'] = [{'date': '2026-01-01', 'equity': 100_000.0}]
    output = dashboard._render_key_stats(state)
    assert '#cbd5e1' in output

  # --- Footer ---

  def test_footer_disclaimer(self) -> None:
    '''Exact copy per UI-SPEC §Footer disclaimer.'''
    output = dashboard._render_footer()
    assert 'Signal-only system. Not financial advice.' in output

  # --- Wave 2: Chart.js + HTML shell + inline CSS tests (VALIDATION 05-03-T1) ---

  def test_chartjs_sri_matches_committed(self, tmp_path) -> None:
    '''VALIDATION row 05-03-T1: exact SRI substring match on rendered HTML.

    SRI verified 2026-04-21 via curl + openssl; a drift from this value means
    either Chart.js version bumped or the CDN file was tampered with —
    either way, the rendered dashboard.html MUST contain the exact locked hash.
    '''
    state = _make_state()
    out = tmp_path / 'd.html'
    dashboard.render_dashboard(state, out_path=out, now=FROZEN_NOW)
    html_text = out.read_text()
    expected = (
      '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.js" '
      'integrity="sha384-MH1axGwz/uQzfIcjFdjEfsM0xlf5mmWfAwwggaOh5IPFvgKFGbJ2PZ4VBbgSYBQN" '
      'crossorigin="anonymous"></script>'
    )
    assert expected in html_text

  def test_equity_chart_payload_matches_state(self, tmp_path) -> None:
    '''VALIDATION row 05-03-T1: payload contains labels for each equity row, in date order.'''
    state = _make_state(with_equity=5)
    out = tmp_path / 'd.html'
    dashboard.render_dashboard(state, out_path=out, now=FROZEN_NOW)
    html_text = out.read_text()
    for row in state['equity_history']:
      assert row['date'] in html_text

  def test_chart_payload_escapes_script_close(self, tmp_path) -> None:
    '''Pitfall 1: </script> injection defence.

    C-4 reviews strengthening: the original .find()-based assertion could
    false-pass when an injected raw </script> appeared inside the payload
    (find() stops at the injected tag, so the assertion measures only the
    prefix). Replace with COUNT-based assertions that verify:
      (a) total </script> occurrences == count of real <script> blocks
          we emit (currently 1: the Chart.js instantiation IIFE), AND
      (b) the escaped form (either '<\\/script>' or r'<\\/script>' depending
          on whether the reader sees the raw-source or parsed form) IS
          present in the chart payload body.
    '''
    state = _make_state(with_equity=0)
    # Injected value with literal </script> + subsequent HTML — the classic
    # break-out-of-script-block payload.
    state['equity_history'] = [{
      'date': '</script><img src=x onerror=alert(1)>',
      'equity': 100.0,
    }]
    out = tmp_path / 'd.html'
    dashboard.render_dashboard(state, out_path=out, now=FROZEN_NOW)
    html_text = out.read_text()

    # Assertion (a): the rendered HTML must contain EXACTLY FIVE </script>
    # close tags — one for the Chart.js CDN <script src="..."></script> in
    # <head>, one for the HTMX 1.9.12 CDN <script src="..."></script> in
    # <head> (Phase 14 TRADE-05), one for the HTMX json-enc extension CDN
    # <script src="..."></script> in <head> (REVIEW CR-01), one for the
    # inline handleTradesError JS block in <head> (Phase 14 UI-SPEC §Decision 4),
    # and one that closes the Chart.js instantiation IIFE in <body>. If the
    # injected </script> leaked through unescaped, this count would be 6 (or more);
    # that is the exact failure mode C-4 wants to catch.
    # (Pre-Phase-14 count was 2; Phase 14 adds 2 more in <head>; CR-01 fix adds 1.)
    assert html_text.count('</script>') == 5, (
      f'unexpected </script> count {html_text.count("</script>")} — '
      'injection defence failed. Expected exactly 5 (Chart.js CDN close + '
      'HTMX CDN close + HTMX json-enc CDN close + inline handleTradesError close + '
      'Chart.js IIFE close).'
    )

    # Assertion (b): the escaped form (json.dumps + .replace('</', '<\\/'))
    # IS present inside the chart payload. Accept either Python raw-string
    # form or the single-backslash form — both are valid JS string escapes.
    assert ('<\\/script>' in html_text or r'<\/script>' in html_text), (
      'escaped </script> form missing from chart payload — the defence '
      "replace('</', '<\\/') must have fired on the injected date value."
    )

  def test_html_has_no_external_stylesheet_links(self, tmp_path) -> None:
    '''DASH-01: CSS is entirely inline inside a <style> block.'''
    state = _make_state()
    out = tmp_path / 'd.html'
    dashboard.render_dashboard(state, out_path=out, now=FROZEN_NOW)
    html_text = out.read_text()
    # Zero <link rel="stylesheet"> — all CSS is inline per DASH-01.
    assert '<link rel="stylesheet"' not in html_text

  def test_inline_css_contains_palette(self, tmp_path) -> None:
    '''DASH-09: visual theme palette hexes present in rendered <style> block.'''
    state = _make_state()
    out = tmp_path / 'd.html'
    dashboard.render_dashboard(state, out_path=out, now=FROZEN_NOW)
    html_text = out.read_text()
    for hex_token in ('#0f1117', '#22c55e', '#ef4444', '#eab308'):
      assert hex_token in html_text, f'palette hex {hex_token} missing from rendered HTML'

  def test_equity_chart_empty_state_placeholder(self, tmp_path) -> None:
    '''D-13: empty equity_history → placeholder text, NO Chart.js canvas.'''
    state = _make_state(with_equity=0)
    state['equity_history'] = []
    out = tmp_path / 'd.html'
    dashboard.render_dashboard(state, out_path=out, now=FROZEN_NOW)
    html_text = out.read_text()
    assert 'No equity history yet — first full run needed' in html_text
    assert '<canvas id="equityChart"' not in html_text

  def test_equity_chart_uses_category_axis(self, tmp_path) -> None:
    '''UI-SPEC §Chart Component: category x-axis, no date adapter needed.

    Also asserts maintainAspectRatio=false (Pitfall 5 with fixed parent
    height) and pointRadius=0 (dense line, minimal noise).
    '''
    state = _make_state(with_equity=10)
    out = tmp_path / 'd.html'
    dashboard.render_dashboard(state, out_path=out, now=FROZEN_NOW)
    html_text = out.read_text()
    assert 'type: "category"' in html_text
    assert 'chartjs-adapter-date-fns' not in html_text
    assert 'maintainAspectRatio: false' in html_text
    assert 'pointRadius: 0' in html_text

  def test_html_shell_structure(self, tmp_path) -> None:
    '''<!DOCTYPE> + <html lang="en"> + <head> + <title> + <meta charset>.'''
    state = _make_state()
    out = tmp_path / 'd.html'
    dashboard.render_dashboard(state, out_path=out, now=FROZEN_NOW)
    html_text = out.read_text()
    assert html_text.startswith('<!DOCTYPE html>\n<html lang="en">\n')
    assert '<title>Trading Signals — Dashboard</title>' in html_text
    assert '<meta charset="utf-8">' in html_text

  def test_module_main_entrypoint_exists(self) -> None:
    '''C-6 reviews: CONTEXT D-05 convenience CLI (`python -m dashboard`).'''
    src = DASHBOARD_PATH.read_text()
    assert "if __name__ == '__main__':" in src, (
      'CONTEXT D-05 convenience CLI missing — `python -m dashboard` '
      'must be supported as an operator preview path.'
    )


class TestEmptyState:
  '''Wave 2 (VALIDATION row 05-03-T2): render_dashboard(reset_state()) byte-matches
  committed golden_empty.html; all sections render with placeholders.
  '''

  def test_empty_state_matches_committed(self, tmp_path) -> None:
    '''VALIDATION row 05-03-T2: render of reset_state output is byte-identical
    to committed golden_empty.html.
    '''
    import state_manager  # test-only lazy import (keeps hex-fence report clean)
    state = state_manager.reset_state()
    out = tmp_path / 'd.html'
    dashboard.render_dashboard(state, out_path=out, now=FROZEN_NOW)
    rendered_bytes = out.read_bytes()
    golden_bytes = GOLDEN_EMPTY_HTML_PATH.read_bytes()
    assert rendered_bytes == golden_bytes, (
      'Empty-state render drifted from golden_empty.html. '
      'If change intentional: run `.venv/bin/python tests/regenerate_dashboard_golden.py` '
      'then re-commit tests/fixtures/dashboard/golden_empty.html.'
    )


class TestGoldenSnapshot:
  '''Wave 2 (VALIDATION row 05-03-T2): render_dashboard(sample_state) with
  FROZEN_NOW byte-matches committed golden.html.
  '''

  def test_golden_snapshot_matches_committed(self, tmp_path) -> None:
    '''VALIDATION row 05-03-T2: sample_state.json render byte-identical to golden.html.'''
    state = json.loads(SAMPLE_STATE_PATH.read_text())
    out = tmp_path / 'd.html'
    dashboard.render_dashboard(state, out_path=out, now=FROZEN_NOW)
    rendered_bytes = out.read_bytes()
    golden_bytes = GOLDEN_HTML_PATH.read_bytes()
    assert rendered_bytes == golden_bytes, (
      'Populated render drifted from golden.html. '
      'If change intentional: run `.venv/bin/python tests/regenerate_dashboard_golden.py` '
      'then re-commit tests/fixtures/dashboard/golden.html.'
    )


class TestAtomicWrite:
  '''Wave 2 (VALIDATION row 05-03-T2): tempfile + fsync + os.replace mirror.
  Mirrors test_state_manager.py::TestAtomicity::test_crash_on_os_replace_leaves_original_intact.
  '''

  def test_atomic_write_success_path(self, tmp_path) -> None:
    '''tempfile + fsync + os.replace; no .tmp left behind.'''
    state = _make_state()
    out = tmp_path / 'd.html'
    dashboard.render_dashboard(state, out_path=out, now=FROZEN_NOW)
    assert out.exists()
    # No stray tempfiles in the parent dir.
    tmp_files = list(tmp_path.glob('*.tmp'))
    assert tmp_files == [], f'unexpected tempfiles left: {tmp_files}'

  def test_crash_on_os_replace_leaves_original_intact(self, tmp_path) -> None:
    '''Mirror of test_state_manager.py::TestAtomicity (lines 213-234).

    Monkeypatch `dashboard.os.replace` to raise OSError; assert the original
    dashboard.html bytes are preserved (D-17 atomic-write durability).
    '''
    out = tmp_path / 'd.html'
    original_bytes = b'<!DOCTYPE html><html><body>ORIGINAL</body></html>'
    out.write_bytes(original_bytes)
    state = _make_state()
    with patch('dashboard.os.replace', side_effect=OSError('disk full')):
      with pytest.raises(OSError, match='disk full'):
        dashboard.render_dashboard(state, out_path=out, now=FROZEN_NOW)
    assert out.read_bytes() == original_bytes, (
      'Original dashboard.html must be byte-identical after failed os.replace'
    )

  def test_tempfile_cleaned_up_on_failure(self, tmp_path) -> None:
    '''Failed os.replace → tempfile cleanup via try/finally (no .tmp left).'''
    out = tmp_path / 'd.html'
    state = _make_state()
    with patch('dashboard.os.replace', side_effect=OSError('disk full')):
      with pytest.raises(OSError):
        dashboard.render_dashboard(state, out_path=out, now=FROZEN_NOW)
    tmp_files = list(tmp_path.glob('*.tmp'))
    assert tmp_files == [], f'tempfile not cleaned up after os.replace failure: {tmp_files}'


# =========================================================================
# Phase 8 Task 3 — dashboard total-return uses state['initial_account'] baseline
# =========================================================================


class TestTotalReturnInitialAccount:
  '''D-16 (Phase 8) + CONF-01: _compute_total_return reads state
  ['initial_account'] as the baseline; falls back to INITIAL_ACCOUNT
  when the key is absent (defense-in-depth for pre-Phase-8 state).
  '''

  def test_custom_initial_account_50k_account_75k_returns_plus_50pct(self) -> None:
    '''initial=50k, account=75k, empty equity_history → '+50.0%'.'''
    state = {
      'initial_account': 50_000.0,
      'account': 75_000.0,
      'equity_history': [],
    }
    assert dashboard._compute_total_return(state) == '+50.0%'

  def test_custom_initial_account_100k_account_50k_returns_minus_50pct(self) -> None:
    '''initial=100k, account=50k, empty equity_history → '-50.0%'.'''
    state = {
      'initial_account': 100_000.0,
      'account': 50_000.0,
      'equity_history': [],
    }
    assert dashboard._compute_total_return(state) == '-50.0%'

  def test_missing_initial_account_falls_back_to_INITIAL_ACCOUNT(self) -> None:
    '''No initial_account key → fallback to INITIAL_ACCOUNT baseline
    (100k); account==100k gives '+0.0%'.
    '''
    state = {
      'account': 100_000.0,
      'equity_history': [],
    }
    assert dashboard._compute_total_return(state) == '+0.0%'


# =========================================================================
# Phase 14 TRADE-05 — HTMX form markup in render_dashboard output
# =========================================================================

class TestRenderDashboardHTMXVendorPin:
  '''Phase 14 TRADE-05 + UI-SPEC §HTMX vendor pin: HTMX 1.9.12 SRI-pinned
  <script> in <head>, AFTER Chart.js, plus inline handleTradesError JS.
  Confirmation banner slot present in body wrapper.

  Exact pin (UI-SPEC + RESEARCH §Pattern 7):
    URL: https://cdn.jsdelivr.net/npm/htmx.org@1.9.12/dist/htmx.min.js
    SRI: sha384-ujb1lZYygJmzgSwoxRggbCHcjc0rB2XoQrxeTUQyRjrOnlCoYta87iKBWq3EsdM2

  Mirrors the Chart.js precedent at dashboard.py:115-116 (Phase 5).
  '''

  _EXPECTED_URL = 'https://cdn.jsdelivr.net/npm/htmx.org@1.9.12/dist/htmx.min.js'
  _EXPECTED_SRI = 'sha384-ujb1lZYygJmzgSwoxRggbCHcjc0rB2XoQrxeTUQyRjrOnlCoYta87iKBWq3EsdM2'

  def test_htmx_script_tag_present_with_exact_sri(self, tmp_path) -> None:
    '''The exact pinned URL + SRI + crossorigin attributes are emitted.'''
    out = tmp_path / 'd.html'
    dashboard.render_dashboard(_make_render_state_with_position(), out_path=out, now=FROZEN_NOW)
    rendered = out.read_text()
    assert self._EXPECTED_URL in rendered, (
      f'HTMX URL not found in rendered HTML; expected {self._EXPECTED_URL}'
    )
    assert self._EXPECTED_SRI in rendered, (
      f'HTMX SRI not found in rendered HTML; expected {self._EXPECTED_SRI}'
    )
    assert 'crossorigin="anonymous"' in rendered, (
      'HTMX <script> must include crossorigin="anonymous"'
    )

  def test_htmx_script_appears_after_chartjs_in_head(self, tmp_path) -> None:
    '''Parse order matters: HTMX must be AFTER Chart.js (UI-SPEC §HTMX vendor pin
    load location: "<head> after Chart.js").
    '''
    out = tmp_path / 'd.html'
    dashboard.render_dashboard(_make_render_state_with_position(), out_path=out, now=FROZEN_NOW)
    rendered = out.read_text()
    chartjs_idx = rendered.find('chart.js@4.4.6')
    htmx_idx = rendered.find('htmx.org@1.9.12')
    assert chartjs_idx >= 0, 'Chart.js <script> missing from rendered HTML'
    assert htmx_idx >= 0, 'HTMX <script> missing from rendered HTML'
    assert htmx_idx > chartjs_idx, (
      f'UI-SPEC: HTMX must be AFTER Chart.js; '
      f'chartjs_idx={chartjs_idx}, htmx_idx={htmx_idx}'
    )

  def test_handle_trades_error_js_inline(self, tmp_path) -> None:
    '''UI-SPEC §Decision 4: inline JS handler for hx-on::after-request.'''
    out = tmp_path / 'd.html'
    dashboard.render_dashboard(_make_render_state_with_position(), out_path=out, now=FROZEN_NOW)
    rendered = out.read_text()
    assert 'function handleTradesError' in rendered, (
      'UI-SPEC §Decision 4: inline handleTradesError JS missing'
    )

  def test_confirmation_banner_slot_present(self, tmp_path) -> None:
    '''UI-SPEC §Decision 3: <div id="confirmation-banner"> for OOB swap.'''
    out = tmp_path / 'd.html'
    dashboard.render_dashboard(_make_render_state_with_position(), out_path=out, now=FROZEN_NOW)
    rendered = out.read_text()
    assert 'id="confirmation-banner"' in rendered, (
      'UI-SPEC §Decision 3: #confirmation-banner div missing from shell'
    )

  # ---- REVIEW CR-01: HTMX json-enc extension ------------------------------

  _EXPECTED_JSON_ENC_URL = 'https://cdn.jsdelivr.net/npm/htmx.org@1.9.12/dist/ext/json-enc.js'
  _EXPECTED_JSON_ENC_SRI = 'sha384-nRnAvEUI7N/XvvowiMiq7oEI04gOXMCqD3Bidvedw+YNbj7zTQACPlRI3Jt3vYM4'

  def test_json_enc_extension_script_present(self, tmp_path) -> None:
    '''REVIEW CR-01: the json-enc extension script tag must be emitted with
    the verified SRI hash. Without it, HTMX submits form-encoded bodies
    while FastAPI handlers expect JSON — every browser POST 400s.
    '''
    out = tmp_path / 'd.html'
    dashboard.render_dashboard(_make_render_state_with_position(), out_path=out, now=FROZEN_NOW)
    rendered = out.read_text()
    assert self._EXPECTED_JSON_ENC_URL in rendered, (
      f'CR-01: json-enc URL not found; expected {self._EXPECTED_JSON_ENC_URL}'
    )
    assert self._EXPECTED_JSON_ENC_SRI in rendered, (
      f'CR-01: json-enc SRI hash not found; expected {self._EXPECTED_JSON_ENC_SRI}'
    )
    # The json-enc script must come AFTER the core HTMX script (extension
    # registers itself onto the global htmx object).
    htmx_idx = rendered.find('htmx.min.js')
    json_enc_idx = rendered.find('json-enc.js')
    assert htmx_idx >= 0 and json_enc_idx > htmx_idx, (
      'CR-01: json-enc must load AFTER core HTMX script'
    )

  def test_open_form_has_json_enc_attribute(self, tmp_path) -> None:
    '''REVIEW CR-01: the open form must declare hx-ext="json-enc" so HTMX
    converts the form-encoded submission into JSON before POSTing.
    '''
    out = tmp_path / 'd.html'
    dashboard.render_dashboard(_make_render_state_with_position(), out_path=out, now=FROZEN_NOW)
    rendered = out.read_text()
    # The attribute must be inside the open form (between hx-post="/trades/open"
    # and the closing > of the <form> tag).
    open_post_idx = rendered.find('hx-post="/trades/open"')
    assert open_post_idx >= 0, 'open form hx-post attribute missing'
    form_close_idx = rendered.find('>', open_post_idx)
    form_attrs = rendered[open_post_idx:form_close_idx]
    assert 'hx-ext="json-enc"' in form_attrs, (
      f'CR-01: open form must declare hx-ext="json-enc"; got attrs={form_attrs!r}'
    )


class TestRenderPositionsTableHTMXForm:
  '''Phase 14 TRADE-05 + UI-SPEC §Decision 1, 2, 3, 7: open form, action
  buttons, target IDs.
  '''

  def test_open_form_section_present(self, tmp_path) -> None:
    '''UI-SPEC §Decision 1: <section class="open-form"> ABOVE the positions table.'''
    out = tmp_path / 'd.html'
    dashboard.render_dashboard(_make_render_state_with_position(), out_path=out, now=FROZEN_NOW)
    rendered = out.read_text()
    assert 'class="open-form"' in rendered
    assert 'OPEN NEW POSITION' in rendered  # eyebrow per UI-SPEC §Copywriting
    # Order: open-form section MUST appear BEFORE the Open Positions <h2>
    of_idx = rendered.find('class="open-form"')
    h2_idx = rendered.find('id="heading-positions"')
    assert of_idx < h2_idx, (
      f'UI-SPEC §Decision 1: open form must appear ABOVE Open Positions; '
      f'open-form idx={of_idx}, heading idx={h2_idx}'
    )

  def test_open_form_hx_post_uses_swap_none(self, tmp_path) -> None:
    '''Phase 14 REVIEWS HIGH #3: open form uses hx-swap="none" (response is
    empty + carries HX-Trigger event header). Per-instrument <tbody> blocks
    listen for the event via hx-trigger="positions-changed from:body" and
    self-refresh via fragment GET — no single #positions-tbody target exists.
    '''
    out = tmp_path / 'd.html'
    dashboard.render_dashboard(_make_render_state_with_position(), out_path=out, now=FROZEN_NOW)
    rendered = out.read_text()
    assert 'hx-post="/trades/open"' in rendered
    assert 'hx-swap="none"' in rendered
    # Old single-tbody target must NOT appear
    assert 'hx-target="#positions-tbody"' not in rendered
    assert 'id="positions-tbody"' not in rendered
    assert 'hx-on::after-request="handleTradesError(event)"' in rendered

  def test_open_form_required_fields_present(self, tmp_path) -> None:
    '''UI-SPEC §Decision 7: 4 required fields (instrument, direction, entry_price, contracts).'''
    out = tmp_path / 'd.html'
    dashboard.render_dashboard(_make_render_state_with_position(), out_path=out, now=FROZEN_NOW)
    rendered = out.read_text()
    assert 'name="instrument"' in rendered
    assert 'name="direction"' in rendered
    assert 'name="entry_price"' in rendered
    assert 'name="contracts"' in rendered
    # All required inputs have for/id label wiring (CLAUDE.md §Frontend HTML shells without JavaScript)
    assert 'for="open-form-instrument"' in rendered
    assert 'id="open-form-instrument"' in rendered
    assert 'for="open-form-entry-price"' in rendered
    assert 'id="open-form-entry-price"' in rendered

  def test_open_form_advanced_collapsed_details(self, tmp_path) -> None:
    '''UI-SPEC §Decision 7: <details class="form-advanced"> wraps optional fields.'''
    out = tmp_path / 'd.html'
    dashboard.render_dashboard(_make_render_state_with_position(), out_path=out, now=FROZEN_NOW)
    rendered = out.read_text()
    assert 'class="form-advanced"' in rendered
    assert '<summary>Advanced</summary>' in rendered
    assert 'name="executed_at"' in rendered
    assert 'name="peak_price"' in rendered
    assert 'name="trough_price"' in rendered
    assert 'name="pyramid_level"' in rendered

  def test_actions_column_header_present(self, tmp_path) -> None:
    '''UI-SPEC §Decision 2: 9th <th scope="col">Actions</th> in positions thead.'''
    out = tmp_path / 'd.html'
    dashboard.render_dashboard(_make_render_state_with_position(), out_path=out, now=FROZEN_NOW)
    rendered = out.read_text()
    assert '<th scope="col">Actions</th>' in rendered

  def test_per_instrument_tbody_present(self, tmp_path) -> None:
    '''Phase 14 REVIEWS HIGH #3: each instrument has its own
    <tbody id="position-group-{instrument}">. Old single id="positions-tbody"
    is removed — confirmation/cancel swaps now target the per-instrument
    tbody for valid HTML5 single-tbody-level swaps.
    '''
    out = tmp_path / 'd.html'
    dashboard.render_dashboard(_make_render_state_with_position(), out_path=out, now=FROZEN_NOW)
    rendered = out.read_text()
    assert 'id="position-group-SPI200"' in rendered
    # Old single tbody id is gone
    assert 'id="positions-tbody"' not in rendered

  def test_position_row_has_id_and_action_buttons(self, tmp_path) -> None:
    '''UI-SPEC §Decision 2 + Phase 14 REVIEWS HIGH #3: each row has
    id="position-row-{instrument}". The Close + Modify buttons target the
    parent per-instrument tbody (hx-target="#position-group-{instrument}",
    hx-swap="innerHTML") so confirmation/cancel rows swap at single-tbody
    granularity.
    '''
    out = tmp_path / 'd.html'
    dashboard.render_dashboard(_make_render_state_with_position(), out_path=out, now=FROZEN_NOW)
    rendered = out.read_text()
    assert 'id="position-row-SPI200"' in rendered
    assert 'class="btn-row btn-close"' in rendered
    assert 'class="btn-row btn-modify"' in rendered
    assert 'hx-get="/trades/close-form?instrument=SPI200"' in rendered
    assert 'hx-get="/trades/modify-form?instrument=SPI200"' in rendered
    # REVIEWS HIGH #3: action buttons target the per-instrument tbody
    assert 'hx-target="#position-group-SPI200"' in rendered
    assert 'hx-swap="innerHTML"' in rendered
    # Close + Modify are type="button" (not submit; not inside a form) per UI-SPEC §Accessibility
    assert 'type="button" class="btn-row btn-close"' in rendered

  def test_empty_state_uses_colspan_9(self, tmp_path) -> None:
    '''UI-SPEC §Decision 2: empty-state row spans 9 columns (Actions added).'''
    empty_state = _make_render_state_with_position()
    empty_state['positions']['SPI200'] = None
    out = tmp_path / 'd.html'
    dashboard.render_dashboard(empty_state, out_path=out, now=FROZEN_NOW)
    rendered = out.read_text()
    assert 'colspan="9"' in rendered
    assert '— No open positions —' in rendered
    # No stale 8-colspan in the empty-state row
    assert 'colspan="8" class="empty-state"' not in rendered


class TestRenderManualStopBadge:
  '''Phase 14 D-09 + UI-SPEC §Decision 6: manual_stop visualization.

  When position.manual_stop is None: no badge; displayed Trail Stop is computed.
  When position.manual_stop is set: badge present; displayed Trail Stop equals
  the override value (NOT the computed value).
  '''

  def test_no_badge_when_manual_stop_is_none(self, tmp_path) -> None:
    '''Default v1.0 behavior preserved: manual_stop=None → no badge.'''
    out = tmp_path / 'd.html'
    dashboard.render_dashboard(
      _make_render_state_with_position(manual_stop=None), out_path=out, now=FROZEN_NOW,
    )
    rendered = out.read_text()
    assert 'class="badge badge-manual"' not in rendered, (
      'manual_stop=None must NOT render a badge'
    )
    # Computed trail = 8100 - 3*50 = 7950.0
    assert '$7,950' in rendered, (
      'manual_stop=None must show computed trail = 8100 - 3*50 = 7950'
    )

  def test_badge_present_when_manual_stop_set(self, tmp_path) -> None:
    '''Phase 15 D-10: side-by-side stop cell when manual_stop is set.
    Replaces Phase 14 badge with explicit `manual: $X | computed: $Y (will close)`
    structure. Asserts the trail-stop-split markup is present.
    '''
    out = tmp_path / 'd.html'
    dashboard.render_dashboard(
      _make_render_state_with_position(manual_stop=7700.0), out_path=out, now=FROZEN_NOW,
    )
    rendered = out.read_text()
    assert 'class="trail-stop-split"' in rendered, (
      'D-10: trail-stop-split container must be present when manual_stop is set'
    )
    assert 'class="manual-stop-val"' in rendered, (
      'D-10: manual-stop-val span must wrap the manual value'
    )
    assert 'class="computed-stop-val"' in rendered, (
      'D-10: computed-stop-val span must wrap the computed value'
    )
    assert '(will close)' in rendered, (
      'D-10 + D-15: (will close) annotation clarifies which value the daily loop respects'
    )
    assert 'manual: $7,700' in rendered, (
      'D-10: manual value (7700) must be visible in the manual: prefix'
    )

  def test_displayed_value_equals_manual_stop_not_computed(self, tmp_path) -> None:
    '''Phase 15 D-10 + D-15: side-by-side cell shows BOTH manual and computed
    values. The (will close) annotation goes on the COMPUTED value because
    sizing_engine.check_stop_hit honors the computed stop, not manual_stop
    (D-15: manual_stop is DISPLAY-ONLY in Phase 14/15; full alignment deferred).
    Computed = peak (8100) - 3*atr (50) = 7950. Manual = 7700.
    '''
    out = tmp_path / 'd.html'
    dashboard.render_dashboard(
      _make_render_state_with_position(manual_stop=7700.0), out_path=out, now=FROZEN_NOW,
    )
    rendered = out.read_text()
    assert '$7,700' in rendered, 'D-10: manual value must be displayed'
    assert '$7,950' in rendered, (
      'D-10: computed value must ALSO be displayed (side-by-side, not suppressed)'
    )
    # (will close) is on the COMPUTED value per D-15
    idx_computed = rendered.find('computed:')
    idx_will_close = rendered.find('(will close)')
    assert idx_computed >= 0 and idx_will_close >= 0
    assert 0 < idx_will_close - idx_computed < 200, (
      'D-15: (will close) annotation must be adjacent to the computed value'
    )

  def test_compute_trail_stop_display_lockstep_parity_with_sizing_engine(self) -> None:
    '''CLAUDE.md hex-lite lockstep: dashboard._compute_trail_stop_display
    and sizing_engine.get_trailing_stop must return bit-identical values
    for any Position dict, including manual_stop set/unset cases.

    Locks the discipline that future Phase 14+ changes to either side
    cannot drift without a red test.
    '''
    from dashboard import _compute_trail_stop_display
    from sizing_engine import get_trailing_stop

    # Case 1: LONG manual_stop set → both return 7700.0
    pos = {
      'direction': 'LONG', 'entry_price': 7000.0, 'entry_date': '2026-04-15',
      'n_contracts': 2, 'pyramid_level': 0,
      'peak_price': 8100.0, 'trough_price': None,
      'atr_entry': 50.0, 'manual_stop': 7700.0,
    }
    assert _compute_trail_stop_display(pos) == get_trailing_stop(pos, 8050.0, 50.0) == 7700.0

    # Case 2: LONG manual_stop None → both return computed 7950.0
    pos['manual_stop'] = None
    assert _compute_trail_stop_display(pos) == get_trailing_stop(pos, 8050.0, 50.0) == 7950.0

    # Case 3: SHORT manual_stop set
    short_pos = {
      'direction': 'SHORT', 'entry_price': 7000.0, 'entry_date': '2026-04-15',
      'n_contracts': 2, 'pyramid_level': 0,
      'peak_price': None, 'trough_price': 6900.0,
      'atr_entry': 50.0, 'manual_stop': 7050.0,
    }
    assert _compute_trail_stop_display(short_pos) == get_trailing_stop(short_pos, 6950.0, 50.0) == 7050.0

    # Case 4 (REVIEWS LOW #11): SHORT manual_stop None → computed trough + 2*atr
    short_pos_no_manual = {
      'direction': 'SHORT', 'entry_price': 7000.0, 'entry_date': '2026-04-15',
      'n_contracts': 2, 'pyramid_level': 0,
      'peak_price': None, 'trough_price': 6900.0,
      'atr_entry': 50.0, 'manual_stop': None,
    }
    # Computed: 6900 + 2*50 = 7000
    assert _compute_trail_stop_display(short_pos_no_manual) == get_trailing_stop(
      short_pos_no_manual, 6950.0, 50.0,
    ) == 7000.0, (
      'REVIEWS LOW #11: SHORT manual_stop=None must fall through to computed '
      'trough + 2*atr; lockstep parity with sizing_engine'
    )

  def test_compute_trail_stop_display_lockstep_parity_with_zero_peak_long(self) -> None:
    '''REVIEW HR-02 regression: peak_price=0.0 (a valid float, NOT None) must
    propagate through dashboard._compute_trail_stop_display unchanged so the
    displayed stop matches sizing_engine.get_trailing_stop.

    Pre-fix bug: dashboard used `position.get(peak_price) or entry_price` —
    truthiness drops 0.0 to entry_price, diverging from sizing_engine which
    uses explicit `is None`. Hypothetical AUDUSD-near-zero edge case but
    the contract is "lockstep" — must hold for every float, including 0.0.
    '''
    from dashboard import _compute_trail_stop_display
    from sizing_engine import get_trailing_stop

    pos = {
      'direction': 'LONG', 'entry_price': 100.0, 'entry_date': '2026-04-15',
      'n_contracts': 1, 'pyramid_level': 0,
      'peak_price': 0.0,  # valid float zero — must NOT fall through to entry
      'trough_price': None,
      'atr_entry': 50.0, 'manual_stop': None,
    }
    # Both should compute peak (0.0) - 3*50 = -150.0; truthiness bug would
    # have used entry (100) - 3*50 = -50.0 in the dashboard side only.
    dashboard_val = _compute_trail_stop_display(pos)
    sizing_val = get_trailing_stop(pos, 50.0, 50.0)
    assert dashboard_val == sizing_val == -150.0, (
      f'HR-02: dashboard and sizing_engine must agree on peak_price=0.0 case; '
      f'dashboard={dashboard_val!r}, sizing={sizing_val!r} (expected -150.0)'
    )

  def test_compute_trail_stop_display_lockstep_parity_with_zero_trough_short(self) -> None:
    '''REVIEW HR-02 regression: SHORT branch — trough_price=0.0 must propagate.

    Pre-fix bug: dashboard's `or` truthiness dropped 0.0 to entry_price.
    Symmetric to the LONG case above.
    '''
    from dashboard import _compute_trail_stop_display
    from sizing_engine import get_trailing_stop

    pos = {
      'direction': 'SHORT', 'entry_price': 100.0, 'entry_date': '2026-04-15',
      'n_contracts': 1, 'pyramid_level': 0,
      'peak_price': None,
      'trough_price': 0.0,  # valid float zero — must NOT fall through to entry
      'atr_entry': 50.0, 'manual_stop': None,
    }
    # Both should compute trough (0.0) + 2*50 = 100.0; truthiness bug would
    # have used entry (100) + 2*50 = 200.0 in the dashboard side only.
    dashboard_val = _compute_trail_stop_display(pos)
    sizing_val = get_trailing_stop(pos, 50.0, 50.0)
    assert dashboard_val == sizing_val == 100.0, (
      f'HR-02: dashboard and sizing_engine must agree on trough_price=0.0 case; '
      f'dashboard={dashboard_val!r}, sizing={sizing_val!r} (expected 100.0)'
    )

  def test_no_badge_for_audusd_when_spi_has_manual_stop(self, tmp_path) -> None:
    '''Phase 15 D-10: per-row isolation — side-by-side stop cell on SPI200
    must not leak to AUDUSD's row. AUDUSD (no manual_stop) shows the
    single computed stop value, no trail-stop-split markup.
    '''
    state = _make_render_state_with_position(manual_stop=7700.0)
    state['positions']['AUDUSD'] = {
      'direction': 'LONG', 'entry_price': 0.6450, 'entry_date': '2026-04-20',
      'n_contracts': 1, 'pyramid_level': 0,
      'peak_price': 0.6500, 'trough_price': None,
      'atr_entry': 0.012, 'manual_stop': None,
    }
    out = tmp_path / 'd.html'
    dashboard.render_dashboard(state, out_path=out, now=FROZEN_NOW)
    rendered = out.read_text()
    spi_start = rendered.find('id="position-row-SPI200"')
    audusd_start = rendered.find('id="position-row-AUDUSD"')
    assert spi_start >= 0 and audusd_start >= 0
    spi_end = rendered.find('</tr>', spi_start)
    audusd_end = rendered.find('</tr>', audusd_start)
    spi_row = rendered[spi_start:spi_end]
    audusd_row = rendered[audusd_start:audusd_end]
    assert 'trail-stop-split' in spi_row, (
      'D-10: SPI200 (manual_stop set) must contain trail-stop-split markup'
    )
    assert 'trail-stop-split' not in audusd_row, (
      'D-10: AUDUSD (no manual_stop) must NOT contain trail-stop-split markup'
    )


class TestAuthHeaderPlaceholder:
  '''Phase 14 REVIEWS HIGH #4: dashboard.html on disk emits literal
  {{WEB_AUTH_SECRET}} placeholder in hx-headers attributes. The real
  secret is substituted at request time by web/routes/dashboard.py
  (Plan 14-04 Task 5) so the on-disk artifact NEVER carries the secret.

  Phase 14 REVIEWS HIGH #3: each instrument has its own
  <tbody id="position-group-{instrument}">. Multiple <tbody> elements
  in one <table> is valid HTML5 and enables single-tbody-level swaps
  for close/modify forms with no orphan rows.
  '''

  def test_render_dashboard_emits_auth_header_placeholder(
      self, tmp_path, monkeypatch,
  ) -> None:
    '''REVIEWS HIGH #4: rendered dashboard.html contains literal placeholder
    string `{{WEB_AUTH_SECRET}}`; real WEB_AUTH_SECRET value (even when set
    in the env) does NOT appear in the disk file.
    '''
    # Force WEB_AUTH_SECRET to a recognisable value so we can assert it does
    # NOT appear in the rendered output (placeholder discipline).
    monkeypatch.setenv('WEB_AUTH_SECRET', 'a' * 32)
    out = tmp_path / 'd.html'
    dashboard.render_dashboard(
      _make_render_state_with_position(), out_path=out, now=FROZEN_NOW,
    )
    rendered = out.read_text()
    assert '{{WEB_AUTH_SECRET}}' in rendered, (
      'REVIEWS HIGH #4: dashboard.html must emit literal placeholder'
    )
    assert 'a' * 32 not in rendered, (
      'REVIEWS HIGH #4: real WEB_AUTH_SECRET MUST NOT leak into disk file; '
      'substitution happens at GET / request time by web/routes/dashboard.py'
    )

  def test_per_instrument_tbody_groups_present(self, tmp_path) -> None:
    '''REVIEWS HIGH #3: each instrument has its own
    <tbody id="position-group-{instrument}">.
    '''
    state = _make_render_state_with_position()
    # Add an AUDUSD position too
    state['positions']['AUDUSD'] = {
      'direction': 'LONG', 'entry_price': 0.6450, 'entry_date': '2026-04-20',
      'n_contracts': 1, 'pyramid_level': 0,
      'peak_price': 0.6500, 'trough_price': None,
      'atr_entry': 0.012, 'manual_stop': None,
    }
    out = tmp_path / 'd.html'
    dashboard.render_dashboard(state, out_path=out, now=FROZEN_NOW)
    rendered = out.read_text()
    assert 'id="position-group-SPI200"' in rendered
    assert 'id="position-group-AUDUSD"' in rendered
    # Action buttons target the per-instrument tbody, not a single positions-tbody
    assert 'hx-target="#position-group-SPI200"' in rendered
    assert 'hx-target="#position-group-AUDUSD"' in rendered

  def test_each_instrument_in_separate_tbody(self, tmp_path) -> None:
    '''Exactly 2 <tbody> elements within <table> when both positions open.'''
    state = _make_render_state_with_position()
    state['positions']['AUDUSD'] = {
      'direction': 'LONG', 'entry_price': 0.6450, 'entry_date': '2026-04-20',
      'n_contracts': 1, 'pyramid_level': 0,
      'peak_price': 0.6500, 'trough_price': None,
      'atr_entry': 0.012, 'manual_stop': None,
    }
    out = tmp_path / 'd.html'
    dashboard.render_dashboard(state, out_path=out, now=FROZEN_NOW)
    rendered = out.read_text()
    # Find the positions table block
    m = re.search(
      r'<h2 id="heading-positions">.*?</table>', rendered, re.DOTALL,
    )
    assert m is not None
    table_block = m.group(0)
    tbody_count = table_block.count('<tbody')
    assert tbody_count == 2, (
      f'REVIEWS HIGH #3: expected 2 per-instrument tbodies, found {tbody_count}'
    )


class TestRenderCalculatorRow:
  '''Phase 15 CALC-01/02/04: per-instrument calculator sub-row rendering.'''

  def test_calc_row_long_position_renders_stop_distance_next_add(self) -> None:
    from dashboard import _render_calc_row
    pos = {
      'direction': 'LONG',
      'entry_price': 7800.0,
      'atr_entry': 50.0,
      'peak_price': 7850.0,
      'current_level': 0,
      'manual_stop': None,
      'contracts': 2,
    }
    state = {
      'positions': {'SPI200': pos},
      'signals': {'SPI200': {'signal': 1, 'last_close': 7860.0,
                              'last_scalars': {'atr': 50.0, 'rvol': 1.0}}},
      'account': 100000.0,
    }
    html_out = _render_calc_row(state, 'SPI200', pos)
    assert 'STOP' in html_out
    assert 'DIST' in html_out
    assert 'NEXT ADD' in html_out
    assert 'LEVEL' in html_out
    assert 'NEW STOP' in html_out  # REVIEWS H-1
    assert 'IF HIGH' in html_out
    assert 'class="calc-row"' in html_out

  def test_trail_stop_matches_display_helper(self) -> None:
    from dashboard import _render_calc_row, _compute_trail_stop_display, _fmt_currency
    pos = {
      'direction': 'LONG',
      'entry_price': 7800.0,
      'atr_entry': 50.0,
      'peak_price': 7900.0,
      'current_level': 0,
      'manual_stop': None,
    }
    state = {
      'positions': {'SPI200': pos},
      'signals': {'SPI200': {'signal': 1, 'last_close': 7900.0,
                              'last_scalars': {'atr': 50.0, 'rvol': 1.0}}},
      'account': 100000.0,
    }
    expected_stop = _compute_trail_stop_display(pos)
    expected_str = _fmt_currency(expected_stop)
    html_out = _render_calc_row(state, 'SPI200', pos)
    assert expected_str in html_out

  def test_entry_target_row_flat_long(self) -> None:
    from dashboard import _render_entry_target_row
    state = {
      'positions': {},
      'signals': {
        'SPI200': {
          'signal': 1,
          'last_close': 7810.25,
          'last_scalars': {'atr': 50.0, 'rvol': 1.0},
        }
      },
      'account': 100000.0,
      '_resolved_contracts': {'SPI200': {'multiplier': 5.0}},
    }
    html_out = _render_entry_target_row(state, 'SPI200')
    assert 'Entry target' in html_out
    assert 'LONG' in html_out
    assert '$7,810.25' in html_out
    assert 'entry-target' in html_out

  def test_entry_target_row_flat_short(self) -> None:
    from dashboard import _render_entry_target_row
    state = {
      'positions': {},
      'signals': {
        'AUDUSD': {
          'signal': -1,
          'last_close': 0.6500,
          'last_scalars': {'atr': 0.005, 'rvol': 1.0},
        }
      },
      'account': 100000.0,
      '_resolved_contracts': {'AUDUSD': {'multiplier': 10000.0}},
    }
    html_out = _render_entry_target_row(state, 'AUDUSD')
    assert 'Entry target' in html_out
    assert 'SHORT' in html_out

  def test_no_calc_row_when_flat_signal(self) -> None:
    from dashboard import _render_entry_target_row
    state = {
      'positions': {},
      'signals': {'SPI200': {'signal': 0}},
    }
    html_out = _render_entry_target_row(state, 'SPI200')
    assert html_out == ''

  def test_pyramid_section_level_0(self) -> None:
    from dashboard import _render_calc_row
    pos = {
      'direction': 'LONG',
      'entry_price': 7800.0,
      'atr_entry': 50.0,
      'peak_price': 7850.0,
      'current_level': 0,
      'manual_stop': None,
    }
    state = {
      'positions': {'SPI200': pos},
      'signals': {'SPI200': {'signal': 1, 'last_close': 7860.0,
                              'last_scalars': {'atr': 50.0, 'rvol': 1.0}}},
      'account': 100000.0,
    }
    html_out = _render_calc_row(state, 'SPI200', pos)
    assert 'level 0/2' in html_out
    assert '(+1×ATR)' in html_out

  def test_pyramid_section_level_1(self) -> None:
    from dashboard import _render_calc_row
    pos = {
      'direction': 'LONG',
      'entry_price': 7800.0,
      'atr_entry': 50.0,
      'peak_price': 7900.0,
      'current_level': 1,
      'manual_stop': None,
    }
    state = {
      'positions': {'SPI200': pos},
      'signals': {'SPI200': {'signal': 1, 'last_close': 7950.0,
                              'last_scalars': {'atr': 50.0, 'rvol': 1.0}}},
      'account': 100000.0,
    }
    html_out = _render_calc_row(state, 'SPI200', pos)
    assert 'level 1/2' in html_out
    # Pitfall 6: next-add LONG = entry + (level+1)*atr_entry = 7800 + 2*50 = 7900
    assert '$7,900' in html_out
    assert '(+2×ATR)' in html_out

  def test_pyramid_section_at_max(self) -> None:
    from dashboard import _render_calc_row
    from system_params import MAX_PYRAMID_LEVEL
    pos = {
      'direction': 'LONG',
      'entry_price': 7800.0,
      'atr_entry': 50.0,
      'peak_price': 7950.0,
      'current_level': MAX_PYRAMID_LEVEL,
      'manual_stop': None,
    }
    state = {
      'positions': {'SPI200': pos},
      'signals': {'SPI200': {'signal': 1, 'last_close': 7950.0,
                              'last_scalars': {'atr': 50.0, 'rvol': 1.0}}},
      'account': 100000.0,
    }
    html_out = _render_calc_row(state, 'SPI200', pos)
    assert 'fully pyramided' in html_out

  def test_distance_dollar_and_percent_formatting(self) -> None:
    '''REVIEWS M-3: distance baseline = current_close, NOT entry_price.
    Fixture: current_close (7860) != entry_price (7800). Stop = peak - 3*atr =
    7800 - 150 = 7650. Expected dist = |7860 - 7650| = 210 (current baseline);
    entry baseline would give 150 — different.
    '''
    from dashboard import _render_calc_row
    pos = {
      'direction': 'LONG',
      'entry_price': 7800.0,
      'atr_entry': 50.0,
      'peak_price': 7800.0,
      'current_level': 0,
      'manual_stop': None,
    }
    state = {
      'positions': {'SPI200': pos},
      'signals': {'SPI200': {
        'signal': 1,
        'last_close': 7860.0,
        'last_scalars': {'atr': 50.0, 'rvol': 1.0},
      }},
      'account': 100000.0,
    }
    html_out = _render_calc_row(state, 'SPI200', pos)
    assert '$210' in html_out, (
      f'REVIEWS M-3: distance must use current_close (7860) baseline '
      f'(expected $210), not entry_price (7800) baseline ($150). '
      f'Output: {html_out!r}'
    )
    idx_dist = html_out.find('DIST')
    assert idx_dist >= 0
    dist_section = html_out[idx_dist:idx_dist + 400]
    assert '$210' in dist_section
    assert '2.7%' in dist_section, (
      f'REVIEWS M-3: distance percent must be 210/7860=2.7%, not '
      f'150/7800=1.9% (entry baseline). Output: {dist_section!r}'
    )

  def test_pyramid_section_includes_new_stop_after_add(self) -> None:
    '''REVIEWS H-1: CALC-04 — render NEXT ADD price AND projected new stop.
    Fixture: LONG SPI200, entry=7800, peak=7820, atr=50, level=0.
    NEXT ADD = 7800 + 1*50 = 7850. Synth peak = max(7820, 7850) = 7850.
    S = 7850 - 3*50 = 7700.
    '''
    from dashboard import _render_calc_row, _fmt_currency
    from sizing_engine import get_trailing_stop
    pos = {
      'direction': 'LONG',
      'entry_price': 7800.0,
      'atr_entry': 50.0,
      'peak_price': 7820.0,
      'current_level': 0,
      'manual_stop': None,
    }
    state = {
      'positions': {'SPI200': pos},
      'signals': {'SPI200': {'signal': 1, 'last_close': 7820.0,
                              'last_scalars': {'atr': 50.0, 'rvol': 1.0}}},
      'account': 100000.0,
    }
    html_out = _render_calc_row(state, 'SPI200', pos)
    synth = dict(pos)
    next_add_price = 7800.0 + 1 * 50.0
    synth['peak_price'] = max(pos['peak_price'], next_add_price)
    synth['manual_stop'] = None
    expected_s = get_trailing_stop(synth, 0.0, 0.0)
    expected_s_str = _fmt_currency(expected_s)
    assert _fmt_currency(next_add_price) in html_out, (
      f'NEXT ADD price {next_add_price} ({_fmt_currency(next_add_price)}) '
      f'not rendered. Output: {html_out!r}'
    )
    assert 'NEW STOP' in html_out, (
      f'REVIEWS H-1: NEW STOP cell absent. Output: {html_out!r}'
    )
    assert expected_s_str in html_out, (
      f'REVIEWS H-1: projected new stop ({expected_s_str}) absent. '
      f'Output: {html_out!r}'
    )


class TestRenderDriftBanner:
  '''Phase 15 SENTINEL-01/02 + D-11/D-13: dashboard drift banner rendering.'''

  def test_amber_drift_banner(self) -> None:
    from dashboard import _render_drift_banner
    state = {
      'warnings': [
        {'source': 'drift',
         'message': "You hold LONG SPI200, today's signal is FLAT — consider closing.",
         'date': '2026-04-26'}
      ]
    }
    html_out = _render_drift_banner(state)
    assert 'sentinel-drift' in html_out
    assert 'sentinel-reversal' not in html_out
    assert 'Drift detected' in html_out
    assert 'consider closing' in html_out

  def test_red_reversal_banner(self) -> None:
    from dashboard import _render_drift_banner
    state = {
      'warnings': [
        {'source': 'drift',
         'message': "You hold LONG SPI200, today's signal is SHORT — reversal recommended (close LONG, open SHORT).",
         'date': '2026-04-26'}
      ]
    }
    html_out = _render_drift_banner(state)
    assert 'sentinel-reversal' in html_out
    assert 'reversal recommended' in html_out

  def test_mixed_drift_reversal_uses_reversal_color(self) -> None:
    from dashboard import _render_drift_banner
    state = {
      'warnings': [
        {'source': 'drift',
         'message': "You hold LONG SPI200, today's signal is FLAT — consider closing.",
         'date': '2026-04-26'},
        {'source': 'drift',
         'message': "You hold SHORT AUDUSD, today's signal is LONG — reversal recommended (close SHORT, open LONG).",
         'date': '2026-04-26'},
      ]
    }
    html_out = _render_drift_banner(state)
    assert 'sentinel-reversal' in html_out, 'mixed: any reversal -> red banner'

  def test_no_banner_when_no_drift(self) -> None:
    from dashboard import _render_drift_banner
    state = {'warnings': []}
    assert _render_drift_banner(state) == ''
    state2 = {'warnings': [{'source': 'sizing_engine', 'message': 'x',
                             'date': '2026-04-26'}]}
    assert _render_drift_banner(state2) == ''

  def test_banner_lists_all_drifted_instruments(self) -> None:
    from dashboard import _render_drift_banner
    state = {
      'warnings': [
        {'source': 'drift',
         'message': "You hold LONG SPI200, today's signal is FLAT — consider closing.",
         'date': '2026-04-26'},
        {'source': 'drift',
         'message': "You hold SHORT AUDUSD, today's signal is LONG — reversal recommended (close SHORT, open LONG).",
         'date': '2026-04-26'},
      ]
    }
    html_out = _render_drift_banner(state)
    assert 'SPI200' in html_out
    assert 'AUDUSD' in html_out
    assert html_out.count('<li>') == 2


class TestBannerStackOrder:
  '''Phase 15 D-13 + REVIEWS H-2: dashboard banner stack hierarchy.'''

  def test_dashboard_banner_hierarchy_corruption_beats_drift(self, tmp_path) -> None:
    '''REVIEWS H-2 + D-13: drift banner sits at top-level slot below
    equity-chart and above positions section. Future corruption banner
    additions sit ABOVE this slot in the same composition.
    '''
    from datetime import datetime, timezone
    from dashboard import render_dashboard
    from state_manager import append_warning, reset_state
    state = reset_state()
    fixed_now = datetime(2026, 4, 26, 9, 30, 0, tzinfo=timezone.utc)
    state = append_warning(state, 'state_manager',
                            'recovered from corruption: state.json reset',
                            now=fixed_now)
    state = append_warning(state, 'drift',
                            "You hold LONG SPI200, today's signal is FLAT — consider closing.",
                            now=fixed_now)
    state['positions'] = {}
    state['signals'] = {}
    out_path = tmp_path / 'dashboard.html'
    render_dashboard(state, out_path=out_path, now=fixed_now)
    body = out_path.read_text(encoding='utf-8')
    idx_drift = body.find('Drift detected')
    assert idx_drift >= 0, 'drift banner heading absent — REVIEWS H-2 broken'
    idx_equity = max(
      body.find('aria-labelledby="heading-equity"'),
      body.find('class="equity-chart-container"'),
      body.find('id="equityChart"'),
    )
    idx_positions = body.find('aria-labelledby="heading-positions"')
    if idx_equity >= 0:
      assert idx_equity < idx_drift, (
        f'REVIEWS H-2: drift banner must sit AFTER equity chart slot. '
        f'idx_equity={idx_equity} idx_drift={idx_drift}'
      )
    assert idx_drift < idx_positions, (
      f'REVIEWS H-2: drift banner must sit BEFORE positions section heading. '
      f'idx_drift={idx_drift} idx_positions={idx_positions}'
    )

  def test_dashboard_banner_hierarchy_stale_beats_drift(self, tmp_path) -> None:
    '''REVIEWS H-2 + D-13: same H-2 top-level slot placement holds when
    stale info is present.
    '''
    from datetime import datetime, timezone
    from dashboard import render_dashboard
    from state_manager import append_warning, reset_state
    state = reset_state()
    fixed_now = datetime(2026, 4, 26, 9, 30, 0, tzinfo=timezone.utc)
    state['_stale_info'] = {'days_stale': 3, 'last_run_date': '2026-04-23'}
    state = append_warning(state, 'drift',
                            "You hold LONG SPI200, today's signal is FLAT — consider closing.",
                            now=fixed_now)
    state['positions'] = {}
    state['signals'] = {}
    out_path = tmp_path / 'dashboard.html'
    render_dashboard(state, out_path=out_path, now=fixed_now)
    body = out_path.read_text(encoding='utf-8')
    idx_drift = body.find('Drift detected')
    assert idx_drift >= 0, 'drift banner heading absent — REVIEWS H-2 broken'
    idx_positions = body.find('aria-labelledby="heading-positions"')
    assert idx_drift < idx_positions, (
      f'REVIEWS H-2: drift banner must sit BEFORE positions section heading '
      f'even when stale info is present. idx_drift={idx_drift} '
      f'idx_positions={idx_positions}'
    )

  def test_drift_banner_renders_before_positions_heading(self, tmp_path) -> None:
    '''REVIEWS H-2: drift banner is in top-level slot above the Open
    Positions section heading. NOT injected into _render_positions_table.
    '''
    from datetime import datetime, timezone
    from dashboard import render_dashboard
    from state_manager import append_warning, reset_state
    state = reset_state()
    fixed_now = datetime(2026, 4, 26, 9, 30, 0, tzinfo=timezone.utc)
    state = append_warning(state, 'drift',
                            "You hold LONG SPI200, today's signal is FLAT — consider closing.",
                            now=fixed_now)
    state['positions'] = {}
    state['signals'] = {}
    out_path = tmp_path / 'dashboard.html'
    render_dashboard(state, out_path=out_path, now=fixed_now)
    body = out_path.read_text(encoding='utf-8')
    idx_drift = body.find('Drift detected')
    idx_positions_heading = body.find('aria-labelledby="heading-positions"')
    assert idx_drift >= 0, 'drift banner absent'
    assert idx_positions_heading >= 0, 'positions section heading absent'
    assert idx_drift < idx_positions_heading, (
      f'REVIEWS H-2: drift banner must render BEFORE Open Positions heading. '
      f'idx_drift={idx_drift} idx_positions_heading={idx_positions_heading}'
    )


# =========================================================================
# Phase 16.1 Plan 01 Task 5 — Sign Out button + session note placeholders
# =========================================================================


class TestRenderSignoutButton:
  '''Phase 16.1: render_dashboard accepts is_cookie_session: bool | None = None.
    None  → emit literal {{SIGNOUT_BUTTON}}{{SESSION_NOTE}} placeholders for
            web-layer per-request substitution (mirrors {{WEB_AUTH_SECRET}}
            pattern).
    True  → render Sign Out button inline (cookie session active).
    False → render session note inline (header-auth flow — UI-SPEC §Surface 4
            generalised post-E-01).
  '''

  def test_signout_button_present_when_cookie_session_True(self, tmp_path) -> None:
    out = tmp_path / 'd.html'
    state = _make_render_state_with_position()
    render_dashboard(state, out_path=out, now=FROZEN_NOW, is_cookie_session=True)
    rendered = out.read_text()
    assert 'class="signout-form"' in rendered
    assert 'action="/logout"' in rendered
    assert '>Sign out<' in rendered
    assert 'aria-label="Sign out of Trading Signals"' in rendered
    assert 'class="session-note"' not in rendered
    # Placeholders fully resolved
    assert '{{SIGNOUT_BUTTON}}' not in rendered
    assert '{{SESSION_NOTE}}' not in rendered

  def test_session_note_present_when_cookie_session_False(self, tmp_path) -> None:
    out = tmp_path / 'd.html'
    state = _make_render_state_with_position()
    render_dashboard(state, out_path=out, now=FROZEN_NOW, is_cookie_session=False)
    rendered = out.read_text()
    assert 'class="session-note"' in rendered
    assert 'Signed in via header — close browser tabs to sign out.' in rendered
    assert 'class="signout-form"' not in rendered
    assert '{{SIGNOUT_BUTTON}}' not in rendered
    assert '{{SESSION_NOTE}}' not in rendered

  def test_default_kwarg_emits_placeholders_for_web_layer_substitution(
    self, tmp_path,
  ) -> None:
    '''Default None → main.py daily-loop callers emit placeholders that the
    web layer substitutes per request (Phase 14 {{WEB_AUTH_SECRET}} pattern).
    '''
    out = tmp_path / 'd.html'
    state = _make_render_state_with_position()
    render_dashboard(state, out_path=out, now=FROZEN_NOW)
    rendered = out.read_text()
    assert '{{SIGNOUT_BUTTON}}' in rendered
    assert '{{SESSION_NOTE}}' in rendered
    # Neither final widget rendered yet — that's the web layer's job.
    assert 'class="signout-form"' not in rendered
    assert 'class="session-note"' not in rendered

  def test_btn_signout_css_rules_present(self, tmp_path) -> None:
    '''Plan 01 Task 5: .btn-signout and .session-note rules in <style>.'''
    out = tmp_path / 'd.html'
    state = _make_render_state_with_position()
    render_dashboard(state, out_path=out, now=FROZEN_NOW, is_cookie_session=True)
    rendered = out.read_text()
    assert '.btn-signout' in rendered
    assert '.session-note' in rendered

  def test_no_hx_headers_on_signout_form(self, tmp_path) -> None:
    '''Sign Out form is plain HTML POST — uses the cookie session, NO
    hx-headers (D-13 unchanged for HTMX trade forms; signout authenticates
    via cookie not header).
    '''
    out = tmp_path / 'd.html'
    state = _make_render_state_with_position()
    render_dashboard(state, out_path=out, now=FROZEN_NOW, is_cookie_session=True)
    rendered = out.read_text()
    # Locate the signout form block and assert no hx-headers within
    import re as _re
    match = _re.search(
      r'<form[^>]*class="signout-form"[^>]*>.*?</form>',
      rendered, _re.DOTALL,
    )
    assert match is not None
    assert 'hx-headers' not in match.group(0)

  def test_hx_headers_count_unchanged_from_phase_14_baseline(self, tmp_path) -> None:
    '''D-13 belt-and-suspenders preserved: HTMX trade-form hx-headers count
    must equal the Phase 14 baseline (2 occurrences — open-form +
    position-table-section).
    '''
    out = tmp_path / 'd.html'
    state = _make_render_state_with_position()
    render_dashboard(state, out_path=out, now=FROZEN_NOW, is_cookie_session=True)
    rendered = out.read_text()
    assert rendered.count('hx-headers') == 2, (
      f'D-13 belt-and-suspenders: expected exactly 2 hx-headers occurrences '
      f'(open-form + position-table-section), got {rendered.count("hx-headers")}'
    )
