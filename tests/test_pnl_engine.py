'''Phase 19 — pnl_engine.py pure-math P&L tests.

Covers:
  TestComputeUnrealisedPnl — LONG/SHORT × SPI200/AUDUSD × win/loss/zero/NaN
  TestComputeRealisedPnl   — LONG/SHORT × SPI200/AUDUSD × win/loss
  TestPnlEngineHexBoundary — module imports only math (+ optional typing); public
                              surface callable.

D-11 (CONTEXT.md): P&L formula reference.
D-19 (19-01-PLAN.md): pnl_engine.py imports math + typing only; multiplier and
round-trip cost arrive as explicit float args (Phase 2 D-17 anti-coupling rule).
'''
import ast
import math
from pathlib import Path

import pytest

PNL_ENGINE_PATH = Path('pnl_engine.py')


# =========================================================================
# TestComputeUnrealisedPnl
# =========================================================================

_UNREALISED_CASES = [
  # (id, side, entry, last_close, contracts, multiplier, entry_cost_aud, expected)
  # LONG_SPI200_win: (7900-7800)*2*5 - 3 = 997.0
  ('LONG_SPI200_win',  'LONG',  7800.0, 7900.0, 2.0, 5.0,     3.0,  997.0),
  # LONG_SPI200_loss: (7700-7800)*2*5 - 3 = -1003.0
  ('LONG_SPI200_loss', 'LONG',  7800.0, 7700.0, 2.0, 5.0,     3.0, -1003.0),
  # SHORT_SPI200_win: (7900-7800)*2*5 - 3 = 997.0
  ('SHORT_SPI200_win', 'SHORT', 7900.0, 7800.0, 2.0, 5.0,     3.0,  997.0),
  # SHORT_SPI200_loss: (7800-7900)*2*5 - 3 = -1003.0
  ('SHORT_SPI200_loss','SHORT', 7800.0, 7900.0, 2.0, 5.0,     3.0, -1003.0),
  # LONG_AUDUSD_win: (0.65-0.64)*1*10000 - 2.5 = 97.5
  ('LONG_AUDUSD_win',  'LONG',  0.6400, 0.6500, 1.0, 10000.0, 2.5,  97.5),
  # LONG_AUDUSD_loss: (0.64-0.65)*1*10000 - 2.5 = -102.5
  ('LONG_AUDUSD_loss', 'LONG',  0.6500, 0.6400, 1.0, 10000.0, 2.5, -102.5),
  # SHORT_AUDUSD_win: (0.65-0.64)*1*10000 - 2.5 = 97.5
  ('SHORT_AUDUSD_win', 'SHORT', 0.6500, 0.6400, 1.0, 10000.0, 2.5,  97.5),
  # zero_contracts_zero_pnl: (7900-7800)*0*5 - 0 = 0.0
  ('zero_contracts_zero_pnl', 'LONG', 7800.0, 7900.0, 0.0, 5.0, 0.0, 0.0),
]


class TestComputeUnrealisedPnl:
  '''D-11: compute_unrealised_pnl LONG/SHORT × SPI200/AUDUSD × win/loss/zero/NaN.'''

  @pytest.mark.parametrize('case_id,side,entry,last_close,contracts,mult,entry_cost,expected',
                           _UNREALISED_CASES,
                           ids=[c[0] for c in _UNREALISED_CASES])
  def test_compute_unrealised_pnl(
    self, case_id, side, entry, last_close, contracts, mult, entry_cost, expected,
  ) -> None:
    '''D-11: parametrized grid covers all LONG/SHORT × instrument × win/loss quadrants.
    All expected values within abs(result - expected) < 1e-9.
    '''
    from pnl_engine import compute_unrealised_pnl
    result = compute_unrealised_pnl(side, entry, last_close, contracts, mult, entry_cost)
    assert abs(result - expected) < 1e-9, (
      f'{case_id}: expected {expected}, got {result}'
    )

  def test_compute_unrealised_pnl_nan_last_close(self) -> None:
    '''D-07 + D-11: NaN last_close propagates through the formula naturally.
    math.isnan(result) must be True — no exception, just NaN output.
    '''
    from pnl_engine import compute_unrealised_pnl
    result = compute_unrealised_pnl('LONG', 7800.0, float('nan'), 2.0, 5.0, 3.0)
    assert math.isnan(result), (
      f'D-07: NaN last_close must produce NaN result; got {result!r}'
    )


# =========================================================================
# TestComputeRealisedPnl
# =========================================================================

_REALISED_CASES = [
  # (id, side, entry, exit_price, contracts, multiplier, round_trip_cost, expected)
  # LONG_SPI200_win: (7900-7800)*2*5 - 6.0 = 994.0
  ('LONG_SPI200_win',   'LONG',  7800.0, 7900.0, 2.0, 5.0,     6.0,  994.0),
  # LONG_SPI200_loss: (7700-7800)*2*5 - 6.0 = -1006.0
  ('LONG_SPI200_loss',  'LONG',  7800.0, 7700.0, 2.0, 5.0,     6.0, -1006.0),
  # SHORT_SPI200_win: (7900-7800)*2*5 - 6.0 = 994.0
  ('SHORT_SPI200_win',  'SHORT', 7900.0, 7800.0, 2.0, 5.0,     6.0,  994.0),
  # SHORT_SPI200_loss: (7800-7900)*2*5 - 6.0 = -1006.0
  ('SHORT_SPI200_loss', 'SHORT', 7800.0, 7900.0, 2.0, 5.0,     6.0, -1006.0),
  # LONG_AUDUSD_win: (0.65-0.64)*1*10000 - 5.0 = 95.0
  ('LONG_AUDUSD_win',   'LONG',  0.6400, 0.6500, 1.0, 10000.0, 5.0,  95.0),
  # LONG_AUDUSD_loss: (0.64-0.65)*1*10000 - 5.0 = -105.0
  ('LONG_AUDUSD_loss',  'LONG',  0.6500, 0.6400, 1.0, 10000.0, 5.0, -105.0),
  # SHORT_AUDUSD_win: (0.65-0.64)*1*10000 - 5.0 = 95.0
  ('SHORT_AUDUSD_win',  'SHORT', 0.6500, 0.6400, 1.0, 10000.0, 5.0,  95.0),
  # SHORT_AUDUSD_loss: (0.64-0.65)*1*10000 - 5.0 = -105.0  NOTE: entry < exit for SHORT = loss
  ('SHORT_AUDUSD_loss', 'SHORT', 0.6400, 0.6500, 1.0, 10000.0, 5.0, -105.0),
]


class TestComputeRealisedPnl:
  '''D-11: compute_realised_pnl LONG/SHORT × SPI200/AUDUSD × win/loss.
  Full round-trip cost deducted at close (CONTEXT D-11 — both halves applied here).
  '''

  @pytest.mark.parametrize('case_id,side,entry,exit_price,contracts,mult,rt_cost,expected',
                           _REALISED_CASES,
                           ids=[c[0] for c in _REALISED_CASES])
  def test_compute_realised_pnl(
    self, case_id, side, entry, exit_price, contracts, mult, rt_cost, expected,
  ) -> None:
    '''D-11: parametrized grid covers all LONG/SHORT × instrument × win/loss quadrants.
    All expected values within abs(result - expected) < 1e-9.
    '''
    from pnl_engine import compute_realised_pnl
    result = compute_realised_pnl(side, entry, exit_price, contracts, mult, rt_cost)
    assert abs(result - expected) < 1e-9, (
      f'{case_id}: expected {expected}, got {result}'
    )


# =========================================================================
# TestPnlEngineHexBoundary
# =========================================================================

class TestPnlEngineHexBoundary:
  '''D-14 + D-19: pnl_engine.py must import ONLY math (and optionally typing).
  Public surface: compute_unrealised_pnl + compute_realised_pnl callable.
  '''

  def test_pnl_engine_module_imports_only_math_and_typing(self) -> None:
    '''D-19: AST-walk pnl_engine.py imports; ONLY math and typing are allowed.
    No system_params, state_manager, datetime, os, numpy, pandas, etc.
    '''
    tree = ast.parse(PNL_ENGINE_PATH.read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
      if isinstance(node, ast.Import):
        for alias in node.names:
          imported.add(alias.name.split('.')[0])
      elif isinstance(node, ast.ImportFrom):
        if node.module:
          imported.add(node.module.split('.')[0])
    forbidden = imported - {'math', 'typing', '__future__'}
    assert not forbidden, (
      f'D-19: pnl_engine.py must only import math/typing; '
      f'found forbidden: {sorted(forbidden)}'
    )

  def test_pnl_engine_has_public_surface(self) -> None:
    '''D-11: both public functions exist and are callable.'''
    import pnl_engine
    assert callable(pnl_engine.compute_unrealised_pnl), (
      'D-11: pnl_engine.compute_unrealised_pnl must be callable'
    )
    assert callable(pnl_engine.compute_realised_pnl), (
      'D-11: pnl_engine.compute_realised_pnl must be callable'
    )
