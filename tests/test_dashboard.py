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

  def test_positions_table_empty_state_colspan_8(self) -> None:
    '''UI-SPEC F-4: 8-column empty state supersedes stale CONTEXT D-13 colspan="7".'''
    state = _make_state()
    state['positions'] = {'SPI200': None, 'AUDUSD': None}
    output = dashboard._render_positions_table(state)
    assert 'colspan="8"' in output
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

    # Assertion (a): the rendered HTML must contain EXACTLY TWO </script>
    # close tags — one for the Chart.js CDN <script src="..."></script> in
    # <head>, and one that closes the Chart.js instantiation IIFE in <body>.
    # If the injected </script> leaked through unescaped, this count would be
    # 3 (or more); that is the exact failure mode C-4 wants to catch.
    # (Rule 1 auto-fix from plan assertion '== 1': plan's count omitted the
    # CDN loader's self-closing </script>. Legitimate real-world count is 2.)
    assert html_text.count('</script>') == 2, (
      f'unexpected </script> count {html_text.count("</script>")} — '
      'injection defence failed. Expected exactly 2 (CDN loader close + '
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
