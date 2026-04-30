'''Phase 20 — alert_engine.py pure-math alert state tests.

Covers:
  TestComputeAlertState   -- HIT precedence, APPROACHING threshold, CLEAR default,
                             LONG/SHORT asymmetry, NaN-safe parametrize, atr<=0 guard
  TestComputeAtrDistance  -- correct distance, NaN on zero/negative/NaN ATR
  TestEngineHexBoundary   -- module imports only math + typing (+ optional __future__);
                             public surface callable.

D-10 (20-CONTEXT.md): alert state formula + NaN policy.
D-11 (20-CONTEXT.md): hex-boundary preservation.
'''
import ast
import math
from pathlib import Path

import pytest

ALERT_ENGINE_PATH = Path('alert_engine.py')


# =========================================================================
# TestComputeAlertState
# =========================================================================

class TestComputeAlertState:
  '''D-10: compute_alert_state covers HIT/APPROACHING/CLEAR logic with
  LONG/SHORT asymmetry, NaN-safe inputs, atr<=0 guard.'''

  def test_long_clear_default(self) -> None:
    '''LONG: low above stop, close far from stop. Returns CLEAR.
    stop=4200, low=4250>stop, abs(4255-4200)=55 > 0.5*10=5. CLEAR.
    '''
    from alert_engine import compute_alert_state
    result = compute_alert_state('LONG', 4250.0, 4260.0, 4255.0, 4200.0, 10.0)
    assert result == 'CLEAR', f'Expected CLEAR; got {result!r}'

  def test_short_clear_default(self) -> None:
    '''SHORT: high below stop, close far from stop. Returns CLEAR.
    stop=4260, high=4250<stop, abs(4205-4260)=55 > 5. CLEAR.
    '''
    from alert_engine import compute_alert_state
    result = compute_alert_state('SHORT', 4200.0, 4250.0, 4205.0, 4260.0, 10.0)
    assert result == 'CLEAR', f'Expected CLEAR; got {result!r}'

  def test_long_approaching_within_half_atr(self) -> None:
    '''LONG: low above stop, abs(close-stop) <= 0.5*atr. Returns APPROACHING.
    stop=4200, low=4205>stop, abs(4204-4200)=4 <= 0.5*10=5. APPROACHING.
    '''
    from alert_engine import compute_alert_state
    result = compute_alert_state('LONG', 4205.0, 4210.0, 4204.0, 4200.0, 10.0)
    assert result == 'APPROACHING', f'Expected APPROACHING; got {result!r}'

  def test_short_approaching_within_half_atr(self) -> None:
    '''SHORT: high below stop, abs(close-stop) <= 0.5*atr. Returns APPROACHING.
    stop=4200, high=4196<stop, abs(4196-4200)=4 <= 5. APPROACHING.
    '''
    from alert_engine import compute_alert_state
    result = compute_alert_state('SHORT', 4180.0, 4196.0, 4196.0, 4200.0, 10.0)
    assert result == 'APPROACHING', f'Expected APPROACHING; got {result!r}'

  def test_long_hit_low_at_stop(self) -> None:
    '''LONG: low == stop. Boundary equality counts as HIT (D-10 <=).
    stop=4200, low=4200. Returns HIT.
    '''
    from alert_engine import compute_alert_state
    result = compute_alert_state('LONG', 4200.0, 4250.0, 4220.0, 4200.0, 10.0)
    assert result == 'HIT', f'Expected HIT at boundary; got {result!r}'

  def test_long_hit_low_below_stop(self) -> None:
    '''LONG: low < stop. Returns HIT.
    stop=4200, low=4150<stop. HIT.
    '''
    from alert_engine import compute_alert_state
    result = compute_alert_state('LONG', 4150.0, 4160.0, 4155.0, 4200.0, 10.0)
    assert result == 'HIT', f'Expected HIT; got {result!r}'

  def test_short_hit_high_at_stop(self) -> None:
    '''SHORT: high == stop. Boundary equality counts as HIT (D-10 >=).
    stop=4200, high=4200. Returns HIT.
    '''
    from alert_engine import compute_alert_state
    result = compute_alert_state('SHORT', 4150.0, 4200.0, 4180.0, 4200.0, 10.0)
    assert result == 'HIT', f'Expected HIT at boundary; got {result!r}'

  def test_short_hit_high_above_stop(self) -> None:
    '''SHORT: high > stop. Returns HIT.
    stop=4200, high=4250>stop. HIT.
    '''
    from alert_engine import compute_alert_state
    result = compute_alert_state('SHORT', 4180.0, 4250.0, 4220.0, 4200.0, 10.0)
    assert result == 'HIT', f'Expected HIT; got {result!r}'

  def test_hit_precedence_over_approaching_long(self) -> None:
    '''D-10 HIT precedence: LONG with low<=stop AND abs(close-stop)<=0.5*atr.
    Returns HIT, NOT APPROACHING. HIT check runs before APPROACHING check.
    '''
    from alert_engine import compute_alert_state
    # low=4198 <= stop=4200 (HIT); close=4202, abs(4202-4200)=2 <= 0.5*10=5 (APPROACHING)
    result = compute_alert_state('LONG', 4198.0, 4210.0, 4202.0, 4200.0, 10.0)
    assert result == 'HIT', (
      f'D-10 HIT precedence violated: expected HIT, got {result!r}'
    )

  def test_hit_precedence_over_approaching_short(self) -> None:
    '''D-10 HIT precedence: SHORT mirror.
    high=4202 >= stop=4200 (HIT); close=4198, abs(4198-4200)=2 <= 5 (APPROACHING).
    Returns HIT, NOT APPROACHING.
    '''
    from alert_engine import compute_alert_state
    result = compute_alert_state('SHORT', 4188.0, 4202.0, 4198.0, 4200.0, 10.0)
    assert result == 'HIT', (
      f'D-10 HIT precedence (SHORT) violated: expected HIT, got {result!r}'
    )

  @pytest.mark.parametrize('nan_field', [
    'today_low', 'today_high', 'today_close', 'stop_price', 'atr',
  ])
  def test_nan_input_returns_clear(self, nan_field: str) -> None:
    '''D-10 NaN policy: any NaN input returns CLEAR (no false-positive email).'''
    from alert_engine import compute_alert_state
    kwargs = {
      'today_low': 4150.0, 'today_high': 4160.0, 'today_close': 4155.0,
      'stop_price': 4200.0, 'atr': 10.0,
    }
    kwargs[nan_field] = float('nan')
    result = compute_alert_state('LONG', **kwargs)
    assert result == 'CLEAR', (
      f'D-10: NaN {nan_field!r} must return CLEAR; got {result!r}'
    )

  def test_atr_zero_returns_clear(self) -> None:
    '''D-10: atr=0.0 returns CLEAR (divide-by-zero guard; <= 0 branch).'''
    from alert_engine import compute_alert_state
    result = compute_alert_state('LONG', 4205.0, 4210.0, 4204.0, 4200.0, 0.0)
    assert result == 'CLEAR', f'D-10: atr=0 must return CLEAR; got {result!r}'

  def test_atr_negative_returns_clear(self) -> None:
    '''D-10: atr=-1.0 returns CLEAR (atr<=0 guard).'''
    from alert_engine import compute_alert_state
    result = compute_alert_state('LONG', 4205.0, 4210.0, 4204.0, 4200.0, -1.0)
    assert result == 'CLEAR', f'D-10: negative atr must return CLEAR; got {result!r}'

  def test_unknown_side_returns_clear(self) -> None:
    '''Defensive: side=\'FOO\' — neither LONG nor SHORT branch fires.
    Falls through to APPROACHING check; if abs(close-stop) > 0.5*atr returns CLEAR.
    '''
    from alert_engine import compute_alert_state
    # close far from stop: abs(4255-4200)=55 > 0.5*10=5 -> CLEAR
    result = compute_alert_state('FOO', 4250.0, 4260.0, 4255.0, 4200.0, 10.0)
    assert result == 'CLEAR', (
      f'Defensive: unknown side with far close must return CLEAR; got {result!r}'
    )


# =========================================================================
# TestComputeAtrDistance
# =========================================================================

class TestComputeAtrDistance:
  '''D-10: compute_atr_distance returns abs(close-stop)/atr.
  Returns float(\'nan\') when atr<=0 or any input is NaN.
  '''

  def test_positive_distance(self) -> None:
    '''close=4205, stop=4200, atr=10 -> abs(5)/10 = 0.5.'''
    from alert_engine import compute_atr_distance
    result = compute_atr_distance(4205.0, 4200.0, 10.0)
    assert abs(result - 0.5) < 1e-9, f'Expected 0.5; got {result!r}'

  def test_zero_distance_at_stop(self) -> None:
    '''close==stop -> 0.0.'''
    from alert_engine import compute_atr_distance
    result = compute_atr_distance(4200.0, 4200.0, 10.0)
    assert result == 0.0, f'Expected 0.0; got {result!r}'

  def test_distance_with_close_below_stop(self) -> None:
    '''abs is applied: close=4195 < stop=4200, atr=10 -> abs(-5)/10=0.5.'''
    from alert_engine import compute_atr_distance
    result = compute_atr_distance(4195.0, 4200.0, 10.0)
    assert abs(result - 0.5) < 1e-9, f'Expected 0.5 (abs); got {result!r}'

  def test_atr_zero_returns_nan(self) -> None:
    '''atr=0.0 -> float(\'nan\') (divide-by-zero guard).'''
    from alert_engine import compute_atr_distance
    result = compute_atr_distance(4205.0, 4200.0, 0.0)
    assert math.isnan(result), f'D-10: atr=0 must return NaN; got {result!r}'

  def test_atr_negative_returns_nan(self) -> None:
    '''atr=-1.0 -> float(\'nan\') (atr<=0 guard).'''
    from alert_engine import compute_atr_distance
    result = compute_atr_distance(4205.0, 4200.0, -1.0)
    assert math.isnan(result), f'D-10: atr<0 must return NaN; got {result!r}'

  @pytest.mark.parametrize('nan_field', ['today_close', 'stop_price', 'atr'])
  def test_nan_input_returns_nan(self, nan_field: str) -> None:
    '''D-10: any NaN input returns float(\'nan\') (no exception).'''
    from alert_engine import compute_atr_distance
    kwargs = {'today_close': 4205.0, 'stop_price': 4200.0, 'atr': 10.0}
    kwargs[nan_field] = float('nan')
    result = compute_atr_distance(**kwargs)
    assert math.isnan(result), (
      f'D-10: NaN {nan_field!r} must return NaN; got {result!r}'
    )


# =========================================================================
# TestEngineHexBoundary
# =========================================================================

class TestEngineHexBoundary:
  '''D-10 + D-11: alert_engine.py must import ONLY math and typing (plus
  optional __future__). Public surface callable.
  '''

  def test_alert_engine_imports_subset_of_allowed(self) -> None:
    '''D-11: AST-walk alert_engine.py imports; assert subset of allowed set.'''
    tree = ast.parse(ALERT_ENGINE_PATH.read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
      if isinstance(node, ast.Import):
        for alias in node.names:
          imported.add(alias.name.split('.')[0])
      elif isinstance(node, ast.ImportFrom):
        if node.module:
          imported.add(node.module.split('.')[0])
    allowed = {'math', 'typing', 'system_params', '__future__'}
    forbidden = imported - allowed
    assert not forbidden, (
      f'D-11: alert_engine.py must only import math/typing/system_params; '
      f'found forbidden: {sorted(forbidden)}'
    )

  def test_alert_engine_public_surface(self) -> None:
    '''D-10: both public functions exist and are callable at module top level.'''
    import alert_engine
    assert callable(alert_engine.compute_alert_state), (
      'D-10: alert_engine.compute_alert_state must be callable'
    )
    assert callable(alert_engine.compute_atr_distance), (
      'D-10: alert_engine.compute_atr_distance must be callable'
    )
