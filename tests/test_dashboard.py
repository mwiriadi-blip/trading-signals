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
from datetime import datetime
from pathlib import Path

import pytest  # noqa: F401 — Wave 1 param tests
import pytz

from dashboard import render_dashboard  # noqa: F401 — Wave 2 goldens / atomic write

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
  net_pnl). Wave 1 fills this body.
  '''
  raise NotImplementedError('Wave 1: fills per UI-SPEC F-8 + state_manager.reset_state shape')


# =========================================================================
# Test classes — one per concern dimension (D-13)
# =========================================================================

class TestStatsMath:
  '''Wave 1 (VALIDATION rows 05-02-T1): unit tests for
  _compute_sharpe, _compute_max_drawdown, _compute_win_rate,
  _compute_total_return, _compute_unrealised_pnl_display.
  Happy path + empty history + single-point + all-losses + all-wins + flat equity.
  '''

  def test_scaffold_placeholder(self) -> None:
    '''Wave 0 placeholder — Wave 1/2 populate real tests.'''
    assert True


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
