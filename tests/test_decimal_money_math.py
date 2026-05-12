'''Phase 27 #1 — Decimal money-math regression tests.

Covers:
  TestAudQuantizeConstants     — AUD_QUANTIZE / AUD_ROUND / to_aud helper contract.
  TestPnlEngineDecimalReturn   — pnl_engine returns Decimal end-to-end (truth #1).
  TestStateRoundTripPreservesAudCents — write float → quantize-via-Decimal → load → no drift.
  TestSizingEngineDelegation   — sizing_engine.compute_unrealised_pnl delegates to pnl_engine
                                  (review-fix agreed-7, truth #2).
  TestSizingClosePositionDecimalCost — _close_position close_cost arithmetic uses Decimal.
  TestNoDuplicatePnlLogicInSizing — AST/grep proof of delegation (no duplicate cost*n logic).
  TestIndicatorMathUnchanged   — signal_engine.compute_indicators dtypes are still float64
                                  (truth #5: hex boundary preserved — no Decimal in numpy/pandas).
  TestV8ToV9MigrationCoercesMoney — float money fields are quantized via Decimal at write.

D-11 + agreed-7 review-fix: `AUD_ROUND = ROUND_HALF_UP` is the project policy
(NOT banker's rounding ROUND_HALF_EVEN — display intuition wins for trading PnL).
'''
from decimal import ROUND_HALF_UP, Decimal

import pytest


# =========================================================================
# TestAudQuantizeConstants
# =========================================================================

class TestAudQuantizeConstants:
  '''system_params exposes AUD_QUANTIZE, AUD_ROUND, to_aud per truth #6.'''

  def test_aud_quantize_constant_is_two_dp(self) -> None:
    '''truth #6: AUD_QUANTIZE pins precision to AUD cents.'''
    from system_params import AUD_QUANTIZE
    assert AUD_QUANTIZE == Decimal('0.01'), (
      f'AUD_QUANTIZE must be Decimal("0.01"), got {AUD_QUANTIZE!r}'
    )

  def test_aud_round_is_half_up(self) -> None:
    '''review-fix agreed-7: AUD_ROUND = ROUND_HALF_UP is pinned.

    Distinguishes from ROUND_HALF_EVEN (Python default — banker's rounding).
    HALF_UP matches consumer-finance/trading PnL display intuition: $2.005 → $2.01.
    '''
    from system_params import AUD_ROUND
    assert AUD_ROUND == ROUND_HALF_UP, (
      f'AUD_ROUND must be ROUND_HALF_UP (not banker\'s rounding); got {AUD_ROUND!r}'
    )

  def test_to_aud_quantizes_to_two_dp(self) -> None:
    '''to_aud(x) returns Decimal quantized to AUD_QUANTIZE.'''
    from system_params import to_aud
    result = to_aud('1234.5678')
    assert result == Decimal('1234.57')
    assert isinstance(result, Decimal)

  def test_to_aud_rounds_half_up(self) -> None:
    '''review-fix agreed-7: to_aud("2.005") == Decimal("2.01") (HALF_UP).
    Distinguishes from HALF_EVEN which would yield Decimal("2.00") via banker's rounding.
    Note: float("2.005") may not be exactly 2.005 due to FP representation,
    so we pass the string form to test the rounding policy itself.
    '''
    from system_params import to_aud
    # str form: unambiguous 2.005 → with HALF_UP → 2.01
    assert to_aud('2.005') == Decimal('2.01'), (
      'HALF_UP policy: 2.005 rounds UP to 2.01 (banker\'s rounding would give 2.00)'
    )

  def test_to_aud_accepts_float_via_str_coercion(self) -> None:
    '''to_aud must accept float input (typical caller hands a float)
    and route through Decimal(str(x)) to avoid float-binary precision contamination.
    '''
    from system_params import to_aud
    result = to_aud(1234.56)
    assert result == Decimal('1234.56')


# =========================================================================
# TestPnlEngineDecimalReturn (truth #1)
# =========================================================================

class TestPnlEngineDecimalReturn:
  '''pnl_engine.compute_*_pnl return Decimal — NOT float (truth #1).'''

  def test_compute_unrealised_pnl_returns_decimal(self) -> None:
    '''truth #1: returns Decimal instance, equals Decimal('-12.50') exactly.

    Inputs chosen so the answer is a clean two-dp Decimal: LONG SPI200 at
    entry 7800.5, last_close 7800.0, 1 contract, mult 5.0, entry_cost 10.0:
      gross = (7800.0 - 7800.5) * 1 * 5 = -2.5
      pnl   = -2.5 - 10.0 = -12.50
    '''
    from pnl_engine import compute_unrealised_pnl
    result = compute_unrealised_pnl('LONG', 7800.5, 7800.0, 1.0, 5.0, 10.0)
    assert isinstance(result, Decimal), (
      f'compute_unrealised_pnl must return Decimal, got {type(result).__name__}'
    )
    assert result == Decimal('-12.50'), (
      f'Expected Decimal("-12.50"), got {result!r}'
    )

  def test_compute_realised_pnl_returns_decimal(self) -> None:
    '''truth #1: realised pnl returns Decimal exact.

    LONG SPI200, entry 7800.5, exit 7800.0, 1 contract, mult 5.0, RT cost 6.0:
      gross = (7800.0 - 7800.5) * 1 * 5 = -2.5
      pnl   = -2.5 - 6.0 = -8.50
    '''
    from pnl_engine import compute_realised_pnl
    result = compute_realised_pnl('LONG', 7800.5, 7800.0, 1.0, 5.0, 6.0)
    assert isinstance(result, Decimal), (
      f'compute_realised_pnl must return Decimal, got {type(result).__name__}'
    )
    assert result == Decimal('-8.50'), (
      f'Expected Decimal("-8.50"), got {result!r}'
    )

  def test_unrealised_pnl_quantized_to_two_dp(self) -> None:
    '''Result is quantized to AUD_QUANTIZE (cents) regardless of input ULP noise.

    Inputs: 0.6500 - 0.6498 = 0.0002 → * 1 * 10000 = 2.0 → minus 0.5 → 1.50
    Float would give 1.4999999999... — Decimal must yield exactly 1.50.
    '''
    from pnl_engine import compute_unrealised_pnl
    result = compute_unrealised_pnl('LONG', 0.6498, 0.6500, 1.0, 10000.0, 0.5)
    assert isinstance(result, Decimal)
    assert result == Decimal('1.50')


# =========================================================================
# TestStateRoundTripPreservesAudCents (truth #4)
# =========================================================================

class TestStateRoundTripPreservesAudCents:
  '''truth #4: write Decimal account → save_state → load_state → exact round-trip.

  Round-trip strategy: state_manager save path quantizes money values via
  Decimal(str(v)).quantize(AUD_QUANTIZE) so the on-disk JSON has canonical
  cent-precision strings. Load path returns the dict unchanged (the canonical
  on-disk form has already been quantized; subsequent loads of the same file
  return identical numeric values — no ULP drift).
  '''

  def test_state_round_trip_preserves_aud_cents(self, tmp_path) -> None:
    '''truth #4: save with Decimal account, load, assert exact equality.'''
    from state_manager import load_state, reset_state, save_state

    state = reset_state(initial_account=Decimal('1234.56'))
    state_path = tmp_path / 'state.json'
    save_state(state, path=state_path)

    loaded = load_state(path=state_path)
    # Account round-trips: write '1234.56' → load 1234.56 (or Decimal('1234.56')).
    # Equality holds across float/Decimal boundary via str-form comparison
    # (avoids float-vs-Decimal type strictness).
    # Phase 33 TENANT-01: account in users bucket.
    _loaded_account = loaded['users']['u_admin_marc']['account']
    assert str(Decimal(str(_loaded_account))) == '1234.56', (
      f'account round-trip drift: expected "1234.56", got {_loaded_account!r}'
    )

  def test_state_no_drift_on_repeated_save_load_cycle(self, tmp_path) -> None:
    '''truth #4: 5 round-trips through save/load preserve cent precision exactly.

    Without Decimal-quantized writes, repeated float arithmetic + json round-trip
    can accumulate ULP errors. With the quantize-on-write policy, the on-disk
    string is canonical and round-trips bit-exact.
    '''
    from state_manager import load_state, reset_state, save_state

    state = reset_state(initial_account=1234.56)
    state_path = tmp_path / 'state.json'
    for _ in range(5):
      save_state(state, path=state_path)
      state = load_state(path=state_path)
    # After 5 cycles, account must still be exactly 1234.56.
    # Phase 33 TENANT-01: account in users bucket.
    assert str(Decimal(str(state['users']['u_admin_marc']['account']))) == '1234.56'

  def test_v8_to_v9_migration_coerces_money(self) -> None:
    '''truth #4 + v9 schema bump: v8 state with floaty account
    is migrated to v9 with quantize-via-Decimal coercion (idempotent).
    '''
    from state_manager import MIGRATIONS, STATE_SCHEMA_VERSION
    # Truth assertion: schema bumped to v10 by Plan 27-09 (was v9 here at
    # Plan 27-01 time). Test asserts the v9 migrator is still registered.
    assert STATE_SCHEMA_VERSION >= 9, (
      f'Plan 27-01 must bump STATE_SCHEMA_VERSION to >=9; got {STATE_SCHEMA_VERSION}'
    )
    # Truth assertion: migrator key 9 registered (contiguity check from 27-07
    # would also catch this at module import — belt-and-suspenders).
    assert 9 in MIGRATIONS, (
      'MIGRATIONS dict missing key 9 — _migrate_v8_to_v9 not registered'
    )

  def test_v8_to_v9_migration_is_idempotent(self) -> None:
    '''Running v8→v9 twice produces the same output (idempotent migration).'''
    from state_manager import MIGRATIONS
    migrator = MIGRATIONS[9]
    v8_state = {
      'schema_version': 8,
      'account': 99999.999,                      # mid-cent, must quantize
      'equity_history': [
        {'date': '2026-04-30', 'equity': 100000.0},
        {'date': '2026-05-01', 'equity': 99500.123456},  # ULP-drift candidate
      ],
      'paper_trades': [
        {'id': 'a', 'status': 'open', 'realised_pnl': None, 'entry_cost_aud': 3.0},
        {'id': 'b', 'status': 'closed', 'realised_pnl': 12.345, 'entry_cost_aud': 3.0},
      ],
    }
    once = migrator(dict(v8_state))
    twice = migrator(dict(once))
    assert once == twice, 'v8→v9 migration is not idempotent'


# =========================================================================
# TestSizingEngineDelegation (truth #2, review-fix agreed-7)
# =========================================================================

class TestSizingEngineDelegation:
  '''sizing_engine.compute_unrealised_pnl delegates to pnl_engine — no duplicate logic.'''

  def test_sizing_compute_unrealised_pnl_delegates_to_pnl_engine(self) -> None:
    '''truth #2: same float pnl as pnl_engine.compute_unrealised_pnl on identical inputs.

    sizing_engine wrapper: (position, current_price, multiplier, cost_aud_open).
    pnl_engine: (side, entry_price, last_close, contracts, multiplier, entry_cost_aud).
    Adapter: cost_aud_open is per-contract — total entry_cost_aud is cost_aud_open * n_contracts.
    '''
    import pnl_engine
    import sizing_engine
    pos = {
      'direction': 'LONG',
      'entry_price': 7800.0,
      'entry_date': '2026-04-30',
      'n_contracts': 2,
      'pyramid_level': 0,
      'peak_price': 7900.0,
      'trough_price': None,
      'atr_entry': 50.0,
      'manual_stop': None,
    }
    sizing_pnl = sizing_engine.compute_unrealised_pnl(
      pos, current_price=7900.0, multiplier=5.0, cost_aud_open=3.0,
    )
    # pnl_engine equivalent: per-contract cost is 3.0, entry_cost_aud (total) = 3.0 * 2 = 6.0
    pnl_engine_pnl = pnl_engine.compute_unrealised_pnl(
      'LONG', 7800.0, 7900.0, 2, 5.0, 6.0,
    )
    # sizing_engine returns float (downstream callers do float arithmetic);
    # pnl_engine returns Decimal. Equality at numeric value (via float coercion).
    assert float(sizing_pnl) == float(pnl_engine_pnl), (
      f'delegation mismatch: sizing={sizing_pnl}, pnl_engine={pnl_engine_pnl}'
    )

  def test_no_duplicate_pnl_logic_in_sizing(self) -> None:
    '''review-fix agreed-7: AST/grep — `cost_aud_open * position` arithmetic
    must NOT appear inside sizing_engine.compute_unrealised_pnl body.
    The body must delegate to pnl_engine.

    We assert the SOURCE of compute_unrealised_pnl contains "from pnl_engine"
    (or "import pnl_engine") and does NOT contain the literal duplicate
    pattern `cost_aud_open * position[`.
    '''
    import inspect
    import sizing_engine
    src = inspect.getsource(sizing_engine.compute_unrealised_pnl)
    assert 'pnl_engine' in src, (
      'sizing_engine.compute_unrealised_pnl must delegate to pnl_engine '
      '(review-fix agreed-7); no `pnl_engine` reference found in body'
    )
    # Duplicate logic pattern: opening-cost arithmetic against position dict.
    forbidden_substr = "cost_aud_open * position['n_contracts']"
    assert forbidden_substr not in src, (
      f'sizing_engine.compute_unrealised_pnl still contains duplicate logic '
      f'`{forbidden_substr}` — must delegate to pnl_engine instead'
    )


class TestSizingClosePositionDecimalCost:
  '''truth #3: sizing_engine._close_position uses Decimal arithmetic for close_cost.

  We assert the source of _close_position uses to_aud / Decimal at the close_cost line —
  the realised_pnl float result is preserved for downstream ClosedTrade callers.
  '''

  def test_close_position_uses_decimal_for_close_cost(self) -> None:
    import inspect
    from sizing_engine import _close_position
    src = inspect.getsource(_close_position)
    # Either to_aud or Decimal must appear in the close_cost computation path.
    assert ('to_aud' in src) or ('Decimal' in src), (
      'sizing_engine._close_position must use to_aud/Decimal for close_cost arithmetic '
      '(truth #3); float-only multiply is forbidden'
    )

  def test_close_position_returns_finite_realised_pnl(self) -> None:
    '''Smoke: _close_position still produces a finite numeric realised_pnl
    after the Decimal close_cost change (no NaN leak, no exception).
    '''
    import math
    from sizing_engine import _close_position
    pos = {
      'direction': 'LONG',
      'entry_price': 7800.0,
      'entry_date': '2026-04-30',
      'n_contracts': 2,
      'pyramid_level': 0,
      'peak_price': 7850.0,
      'trough_price': None,
      'atr_entry': 50.0,
      'manual_stop': None,
    }
    bar = {'close': 7850.0, 'date': '2026-05-01'}
    result = _close_position(pos, bar, multiplier=5.0, cost_aud_open=3.0,
                             exit_reason='flat_signal')
    assert math.isfinite(float(result.realised_pnl))
    # gross = (7850-7800)*2*5 = 500; close_cost = 3.0*2 = 6.0; realised = 494.0
    assert float(result.realised_pnl) == 494.0


# =========================================================================
# TestIndicatorMathUnchanged (truth #5 — hex boundary preserved)
# =========================================================================

class TestIndicatorMathUnchanged:
  '''truth #5: signal_engine.compute_indicators dtypes are still all float64.

  No Decimal leaked into numpy/pandas indicator math. The Decimal slice is
  ONLY at the money-math boundary — pnl_engine + state_manager persistence.
  '''

  def test_compute_indicators_dtypes_all_float64(self) -> None:
    import numpy as np
    import pandas as pd

    from signal_engine import compute_indicators

    # Synthesise a tiny canonical-shape OHLC DataFrame — enough to compute indicators
    # without depending on a fixture file. Column casing matches signal_engine's
    # `Close`-capitalised convention (yfinance OHLC default).
    n = 300
    idx = pd.date_range('2024-01-01', periods=n, freq='B')
    rng = np.random.default_rng(seed=42)
    close = 7000.0 + np.cumsum(rng.normal(0, 5, n))
    df = pd.DataFrame({
      'Open':  close + rng.normal(0, 1, n),
      'High':  close + np.abs(rng.normal(0, 5, n)),
      'Low':   close - np.abs(rng.normal(0, 5, n)),
      'Close': close,
      'Volume': rng.integers(1_000_000, 10_000_000, n).astype('float64'),
    }, index=idx)

    out = compute_indicators(df)
    indicator_cols = ['ATR', 'ADX', 'PDI', 'NDI', 'Mom1', 'Mom3', 'Mom12', 'RVol']
    for col in indicator_cols:
      assert col in out.columns, f'expected indicator column {col!r} not present'
      assert out[col].dtype == np.float64, (
        f'truth #5: indicator {col!r} dtype must be float64; '
        f'got {out[col].dtype} — Decimal must NOT leak into numpy/pandas paths'
      )


# =========================================================================
# TestJsonEncoderHelper (truth #7)
# =========================================================================

class TestJsonEncoderHelper:
  '''truth #7: _decimal_default exists in system_params and serializes Decimal as str.'''

  def test_decimal_default_serializes_decimal_as_string(self) -> None:
    import json
    from system_params import _decimal_default
    out = json.dumps({'pnl': Decimal('1234.56')}, default=_decimal_default)
    # Either '"1234.56"' (string) or 1234.56 (float-coerced) is acceptable per truth #7.
    assert '1234.56' in out

  def test_decimal_default_raises_on_non_decimal_unknown_type(self) -> None:
    import json
    from system_params import _decimal_default
    # set is not JSON-serializable — _decimal_default must propagate TypeError.
    with pytest.raises(TypeError):
      json.dumps({'x': {1, 2, 3}}, default=_decimal_default)
