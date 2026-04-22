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


class TestFormatters:
  '''Wave 1 (VALIDATION rows 05-02-T2): unit tests for
  _fmt_currency, _fmt_percent_signed, _fmt_percent_unsigned, _fmt_pnl_with_colour,
  _fmt_em_dash, _fmt_last_updated. Covers positive/negative/zero/edge cases +
  naive-datetime rejection (Pitfall 9).
  '''

  def test_scaffold_placeholder(self) -> None:
    '''Wave 0 placeholder — Wave 1/2 populate real tests.'''
    assert True


class TestRenderBlocks:
  '''Wave 1/2 (VALIDATION rows 05-02-T3 + 05-03-T1): per-block substring
  asserts, palette presence, Chart.js SRI match, no-external-stylesheet,
  </script> injection defence, XSS escape on exit_reason.
  '''

  def test_scaffold_placeholder(self) -> None:
    '''Wave 0 placeholder — Wave 1/2 populate real tests.'''
    assert True


class TestEmptyState:
  '''Wave 2 (VALIDATION row 05-03-T2): render_dashboard(reset_state()) byte-matches
  committed golden_empty.html; all sections render with placeholders.
  '''

  def test_scaffold_placeholder(self) -> None:
    '''Wave 0 placeholder — Wave 1/2 populate real tests.'''
    assert True


class TestGoldenSnapshot:
  '''Wave 2 (VALIDATION row 05-03-T2): render_dashboard(sample_state) with
  FROZEN_NOW byte-matches committed golden.html.
  '''

  def test_scaffold_placeholder(self) -> None:
    '''Wave 0 placeholder — Wave 1/2 populate real tests.'''
    assert True


class TestAtomicWrite:
  '''Wave 2 (VALIDATION row 05-03-T2): tempfile + fsync + os.replace mirror.
  Mirrors test_state_manager.py::TestAtomicity::test_crash_on_os_replace_leaves_original_intact.
  '''

  def test_scaffold_placeholder(self) -> None:
    '''Wave 0 placeholder — Wave 1/2 populate real tests.'''
    assert True
