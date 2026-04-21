'''Phase 3 test suite: state persistence, atomic writes, corruption recovery,
trade recording, equity history, reset, warnings, and schema migration.

Organized into classes per D-13 (one class per concern dimension):
  TestLoadSave, TestAtomicity, TestCorruptionRecovery, TestRecordTrade,
  TestEquityHistory, TestReset, TestWarnings, TestSchemaVersion.

All tests use tmp_path (pytest built-in) for isolated state files — never
touch the real ./state.json. Clock-dependent functions accept now= injection
so tests are deterministic without pytest-freezer.

Wave 0 (this commit): empty skeletons with class docstrings and _make_trade
helper. Waves 1-3 fill in the test methods per the wave annotation in each
class docstring.
'''
import json  # noqa: F401 — used in Wave 1/2 TestLoadSave/TestCorruptionRecovery
import os  # noqa: F401 — used in Wave 1 TestAtomicity
from datetime import datetime, timezone  # noqa: F401 — used in Wave 1/2 clock injection
from pathlib import Path
from unittest.mock import patch  # noqa: F401 — used in Wave 1 TestAtomicity

import pytest  # noqa: F401 — used across Waves 1/2/3 for raises / parametrize

from state_manager import (
  MIGRATIONS,  # noqa: F401 — used in Wave 1 TestSchemaVersion
  append_warning,  # noqa: F401 — used in Wave 2 TestWarnings
  load_state,  # noqa: F401 — used in Waves 1/2 TestLoadSave/TestCorruptionRecovery
  record_trade,  # noqa: F401 — used in Wave 3 TestRecordTrade
  reset_state,  # noqa: F401 — used in Wave 2 TestReset
  save_state,  # noqa: F401 — used in Wave 1 TestLoadSave/TestAtomicity
  update_equity_history,  # noqa: F401 — used in Wave 3 TestEquityHistory
)
from system_params import (
  INITIAL_ACCOUNT,  # noqa: F401 — used in Wave 2 TestReset
  MAX_WARNINGS,  # noqa: F401 — used in Wave 2 TestWarnings
  STATE_FILE,  # noqa: F401 — used in Wave 1 TestLoadSave default path
  STATE_SCHEMA_VERSION,  # noqa: F401 — used in Wave 1 TestSchemaVersion
)

# =========================================================================
# Module-level path constants (mirrors test_signal_engine.py SIGNAL_ENGINE_PATH pattern)
# =========================================================================

STATE_MANAGER_PATH = Path('state_manager.py')
TEST_STATE_MANAGER_PATH = Path('tests/test_state_manager.py')

# =========================================================================
# Test fixture helpers
# =========================================================================

def _make_trade(
  instrument: str = 'SPI200',
  direction: str = 'LONG',
  entry_price: float = 7000.0,
  exit_price: float = 7100.0,
  n_contracts: int = 2,
  gross_pnl: float = 1000.0,
  cost_aud: float = 6.0,
  multiplier: float = 5.0,
  exit_reason: str = 'flat_signal',
  entry_date: str = '2026-01-02',
  exit_date: str = '2026-01-09',
) -> dict:
  '''Build a trade dict with sensible defaults. All required fields per D-15.

  gross_pnl is the RAW price-delta P&L (D-14 contract):
    (exit_price - entry_price) * n_contracts * multiplier  for LONG
    (entry_price - exit_price) * n_contracts * multiplier  for SHORT
  It is NOT Phase 2's ClosedTrade.realised_pnl (which already has the
  closing cost deducted). See state_manager.record_trade docstring for the
  Phase 4 boundary warning.
  '''
  return {
    'instrument': instrument,
    'direction': direction,
    'entry_price': entry_price,
    'exit_price': exit_price,
    'n_contracts': n_contracts,
    'gross_pnl': gross_pnl,
    'cost_aud': cost_aud,
    'multiplier': multiplier,
    'exit_reason': exit_reason,
    'entry_date': entry_date,
    'exit_date': exit_date,
  }

# =========================================================================
# Test classes — one per concern dimension (D-13)
# =========================================================================

class TestLoadSave:
  '''STATE-01 / STATE-02: load_state and save_state round-trip + atomic write success path.

  All tests use tmp_path to avoid touching the real ./state.json.
  Wave 1 fills this in.
  '''
  pass

class TestAtomicity:
  '''STATE-02 / D-08 (amended by D-17): crash simulation + post-replace fsync ordering proof.

  Patch target is `state_manager.os.replace` so the mock intercepts the
  exact call made inside save_state's _atomic_write helper.
  Wave 1 fills this in.
  '''
  pass

class TestCorruptionRecovery:
  '''STATE-03 / D-05 / D-06 (amended by B-1 + B-2) / D-07 / D-18: JSONDecodeError
  triggers backup + reinit + warning; valid-but-incomplete JSON raises ValueError.

  Wave 2 fills this in.
  '''
  pass

class TestRecordTrade:
  '''STATE-05 / D-13..D-16 / D-19 / D-20: validation, closing-half cost,
  account mutation, position close, no-mutation contract.

  All arithmetic verified from first principles (no oracle files needed).
  CRITICAL: gross_pnl is RAW price-delta P&L per D-14, NOT realised_pnl.
  Wave 3 fills this in.
  '''
  pass

class TestEquityHistory:
  '''STATE-06 / D-04 / B-4: update_equity_history appends {date, equity}
  after boundary validation (date shape + equity finiteness).

  Wave 3 fills this in.
  '''
  pass

class TestReset:
  '''STATE-07 / D-01 / D-03: reset_state shape — $100k account, None positions,
  FLAT signals, empty collections.

  Wave 2 fills this in.
  '''
  pass

class TestWarnings:
  '''D-09 / D-10 / D-11 / B-5: warning shape, AWST date, FIFO bound to MAX_WARNINGS.

  Wave 2 fills this in.
  '''
  pass

class TestSchemaVersion:
  '''STATE-04: MIGRATIONS dict walk-forward; no-op at v1; handles missing key.

  Wave 1 fills this in.
  '''
  pass
