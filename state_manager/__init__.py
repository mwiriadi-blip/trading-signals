'''State Manager — atomic JSON persistence, corruption recovery, schema migration.

Owns state.json at the repo root and exposes public functions:
  load_state, save_state, record_trade, update_equity_history,
  reset_state, mutate_state, append_warning, clear_warnings,
  clear_warnings_by_source.

STATE-01..07 (REQUIREMENTS.md §Persistence). Atomic write via tempfile +
fsync(file) + os.replace + fsync(parent dir) — D-08 amended by D-17 (post-
replace dir fsync for rename durability). Corruption = JSONDecodeError only
(D-05); on corrupt: backup + reinit + warn (STATE-03, D-06 + B-1 path.name
derivation + B-2 microsecond timestamp). Schema migration via MIGRATIONS dict
walk-forward (STATE-04). Post-parse semantic validation via
_validate_loaded_state (D-18) — raises ValueError on missing required keys.

Architecture (hexagonal-lite, CLAUDE.md): I/O hex. This is the ONE module
allowed to do filesystem I/O. Must NOT import signal_engine, sizing_engine,
notifier, dashboard, main, requests, numpy, or pandas.

All clock-dependent functions accept a `now=None` parameter (defaulting to
datetime.now(timezone.utc)) so tests are deterministic without pytest-freezer.

All public mutation functions return the mutated state dict — callers must
capture: `state = append_warning(state, ...)`.

Phase 14 D-13 amendment: state_manager is now a peer writer to state.json
with the FastAPI web layer. Cross-process coordination via fcntl.LOCK_EX
advisory lock acquired in _atomic_write. INTRA-PROCESS REENTRANCY: mutate_state
holds its own outer flock and calls io._save_state_unlocked directly to avoid
the intra-process flock-on-different-fd deadlock.

Phase 31: state_manager is now a package. Submodules:
  io.py        — I/O kernel (_atomic_write*, _backup_corrupt, _save_state_unlocked)
  migrations.py — schema migration registry + orchestrator
  validation.py — datetime guards + trade/state validators
  trades.py    — record helpers (append_warning, record_trade, etc.)
  __init__.py  — this file: public API orchestrator
'''
import fcntl
import json
import logging
import os
import shutil
import sys
import threading
import warnings
import zoneinfo
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any, Callable
from decimal import Decimal as _Decimal

from system_params import (
  INITIAL_ACCOUNT,
  MAX_WARNINGS,
  STATE_FILE,
  STATE_SCHEMA_VERSION,
  AUD_QUANTIZE,
  AUD_ROUND,
  _decimal_default,
  AUDUSD_CONTRACTS,
  DEFAULT_MARKETS,
  DEFAULT_STRATEGY_SETTINGS,
  SPI_CONTRACTS,
  _DEFAULT_AUDUSD_LABEL,
  _DEFAULT_SPI_LABEL,
  default_settings_for_market,
  STRATEGY_VERSION,
)

from state_manager import io, migrations, validation, trades

# =========================================================================
# Re-exports from submodules — placed early so orchestrator functions below
# can reference these names as module globals (enabling monkeypatch in tests).
#
# Tests and production callers import private symbols directly from
# state_manager (flat-file convention). Re-exporting keeps all existing
# import paths unchanged after the package split.
# =========================================================================

# --- migrations ---
from state_manager.migrations import (
  MIGRATIONS,
  _ADMIN_UID,
  _migrate,
  _migrate_v1_to_v2,
  _migrate_v2_to_v3,
  _migrate_v3_to_v4,
  _migrate_v4_to_v5,
  _migrate_v5_to_v6,
  _migrate_v6_to_v7,
  _migrate_v7_to_v8,
  _migrate_v8_to_v9,
  _migrate_v9_to_v10,
  _migrate_v10_to_v11,
  _migrate_v11_to_v12,
  _default_market_registry,
  _default_strategy_settings,
)

# --- validation ---
from state_manager.validation import (
  StateV12,
  _assert_tz_aware,
  _coerce_legacy_naive_iso,
  _read_signal_strategy_version,
  _validate_loaded_state,
  _validate_trade,
)

# --- trades ---
from state_manager.trades import (
  append_warning,
  clear_warnings,
  clear_warnings_by_source,
  record_trade,
  update_equity_history,
)

# =========================================================================
# Module-level constants (private + re-exported for downstream callers)
# =========================================================================

logger = logging.getLogger(__name__)

_AWST = zoneinfo.ZoneInfo('Australia/Perth')

# Re-entrancy guard for mutate_state.  threading.local() is safe for
# concurrent test runs — each thread has its own independent value.
_MUTATE_STATE_ACTIVE = threading.local()

# Re-exported so any caller that imported these from state_manager still works.
_REQUIRED_TRADE_FIELDS = validation._REQUIRED_TRADE_FIELDS
_REQUIRED_STATE_KEYS = validation._REQUIRED_STATE_KEYS


def _assert_migration_chain_contiguous() -> None:
  '''Phase 27 #12 — fail-fast on schema-migration chain gaps.

  Defined here (in __init__) rather than re-exported from migrations so that
  monkeypatch.setattr(state_manager, 'MIGRATIONS', ...) and
  monkeypatch.setattr(state_manager, 'STATE_SCHEMA_VERSION', ...) in tests
  are visible to this function (reads module-global names at call time).

  Also fires at import time in migrations.py (separate instance there) as
  a defense-in-depth guard on the submodule. Both instances protect the chain.
  '''
  # Read module-global names so monkeypatches are effective.
  _migrations = globals()['MIGRATIONS']
  _ssv = globals().get('STATE_SCHEMA_VERSION', STATE_SCHEMA_VERSION)
  if _ssv < 1:
    raise RuntimeError(
      f'STATE_SCHEMA_VERSION must be >= 1, got {_ssv}'
    )
  missing = [
    v for v in range(2, _ssv + 1)
    if v not in _migrations
  ]
  if missing:
    raise RuntimeError(
      f'MIGRATIONS chain has gaps: missing keys {missing} '
      f'(STATE_SCHEMA_VERSION={_ssv})'
    )


# =========================================================================
# Public API — orchestrators
# =========================================================================

def reset_state(initial_account=INITIAL_ACCOUNT) -> dict:
  '''STATE-07 / D-01 / D-03 / Phase 10 BUG-01 D-02: fresh state,
  account + initial_account both equal to `initial_account` (default
  INITIAL_ACCOUNT from system_params).

  Phase 10 D-02 closes BUG-01 at the module boundary: both
  `state['account']` and `state['initial_account']` are set from the
  same source-of-truth argument, so no caller can create a state where
  they differ.

  Each call returns a NEW dict (no shared mutable references) so that
  mutating one returned state doesn't bleed into a future reset.
  '''
  # Phase 27 #1: route initial_account through Decimal-quantize so a
  # Decimal-typed caller (truth #4 round-trip path) doesn't leak a raw
  # Decimal into the float-typed in-memory state. Floats stay floats.
  ia_float = float(_Decimal(str(initial_account)).quantize(
    AUD_QUANTIZE, rounding=AUD_ROUND,
  ))
  # Phase 33 TENANT-01: v12 shape — per-user state under state['users'][_ADMIN_UID].
  # tour_completed=False for fresh reset (new user, no tour done yet);
  # the migrator uses True (existing admin, tour already completed).
  return {
    'schema_version': STATE_SCHEMA_VERSION,
    'admin_user_id': _ADMIN_UID,              # Phase 33: constant, never inline string
    'last_run': None,
    'signals': {                              # D-03: FLAT init (dict shape only)
      'SPI200': {'signal': 0, 'strategy_version': STRATEGY_VERSION},
      'AUDUSD': {'signal': 0, 'strategy_version': STRATEGY_VERSION},
    },
    'warnings': [],
    'markets': _default_market_registry(),
    'strategy_settings': _default_strategy_settings(),
    # v12: all per-user data lives under users{}
    'users': {
      _ADMIN_UID: {
        'account': ia_float,                  # D-02: from arg
        'initial_account': ia_float,          # D-02: from arg
        'contracts': {
          'SPI200': _DEFAULT_SPI_LABEL,
          'AUDUSD': _DEFAULT_AUDUSD_LABEL,
        },
        'positions': {                        # D-01: None = inactive
          'SPI200': None,
          'AUDUSD': None,
        },
        'trade_log': [],
        'equity_history': [],
        'paper_trades': [],
        'ui_prefs': {'tour_completed': False},  # False: fresh user, tour not done
      },
    },
  }


def load_state(path: Path = Path(STATE_FILE), now=None, _under_lock: bool = False) -> dict:
  '''STATE-01 / STATE-03 / STATE-04 / D-18: load state.json; recover on corruption.

  If path does not exist: returns reset_state() output (fresh state).
    B-3: does NOT save the fresh state — orchestrator (Phase 4) must
    explicitly call save_state to materialize state.json on first run.
  On JSONDecodeError (D-05 — NARROW catch, NOT bare ValueError per Pitfall 4):
    - backup file via io._backup_corrupt
    - reinit via reset_state (STATE-07)
    - append warning with source='state_manager' (D-07)
    - save fresh state to path
    - return fresh state
  On successful parse:
    - walk MIGRATIONS forward (STATE-04) via _migrate (module-global for testability)
    - run _validate_loaded_state (D-18 — raises ValueError on missing keys)
    - return validated state

  Phase 14 D-13 _under_lock parameter (PRIVATE — underscore-prefixed):
    Set to True ONLY by mutate_state, which already holds fcntl.LOCK_EX
    on `path`. When True, the corruption-recovery save uses
    io._save_state_unlocked (no second lock acquire) to avoid the intra-
    process flock-on-different-fd deadlock.

  NOTE: _migrate and _migrate_v7_to_v8 are referenced as module-global
  names (not via migrations._migrate) so that monkeypatch.setattr(
  state_manager, '_migrate', ...) in tests can intercept the call.
  '''
  # Phase 27 #12: re-check the migration chain at every load_state entry.
  _assert_migration_chain_contiguous()
  if not path.exists():
    return reset_state()                  # B-3: no auto-save on missing file
  raw = path.read_bytes()
  try:
    state = json.loads(raw)
  except (json.JSONDecodeError, UnicodeDecodeError):
    # D-05 narrow catch (Pitfall 4): two cases represent 'bytes on disk are
    # not parseable JSON':
    #   - JSONDecodeError: syntactically invalid JSON (e.g., truncated braces)
    #   - UnicodeDecodeError: bytes aren't decodable as any JSON-supported
    #     encoding (e.g., b'\x00\xff\x00...' which json.loads attempts to
    #     autodetect as UTF-16 and fails). Both are ValueError subclasses but
    #     NEITHER is bare ValueError — Pitfall 4 (bare ValueError masking
    #     non-corruption bugs like schema mismatch) is still enforced.
    if now is None:
      now = datetime.now(UTC)
    backup_name = io._backup_corrupt(path, now)
    state = reset_state()
    state = append_warning(
      state, 'state_manager',
      f'recovered from corruption; backup at {backup_name}',
      now=now,
    )
    if _under_lock:
      io._save_state_unlocked(state, path=path)
    else:
      save_state(state, path=path)
    return state
  # Happy path: Phase 33 pre-migration backup, then migrate, then validate.
  # Backup is non-destructive shutil.copy2 — fires only when upgrading to v12.
  _old_version = state.get('schema_version', 0)
  if _old_version < 12:
    if now is None:
      now = datetime.now(UTC)
    _backup_ts = now.date().isoformat()
    _backup_path = path.parent / f'{path.name}.v11-backup-{_backup_ts}'
    if not _backup_path.exists():
      shutil.copy2(str(path), str(_backup_path))
  # Call _migrate and _migrate_v7_to_v8 via module-global names so that
  # monkeypatch.setattr(state_manager, '_migrate', ...) works in tests.
  state = _migrate(state)
  if 'markets' not in state or 'strategy_settings' not in state:
    state = _migrate_v7_to_v8(state)
  # Phase 33 TENANT-01: Pydantic structural validation on v12 shape.
  StateV12.model_validate(state)
  _validate_loaded_state(state)           # D-18: raises ValueError on missing keys
  # Phase 27 #6: read-path UTC-coercion shim — legacy naive ISO datetimes
  # in equity_history emit DeprecationWarning rather than failing the load.
  state = _coerce_legacy_naive_iso(state)
  # D-14 (Phase 8): materialise runtime-only _resolved_contracts from
  # tier labels. Underscore prefix = excluded from save_state (below).
  # Phase 33 B2: contracts now live at state['users'][_ADMIN_UID]['contracts'].
  # Use _ADMIN_UID constant — never inline string.
  _user_bucket = state.get('users', {}).get(_ADMIN_UID, {})
  _user_contracts = _user_bucket.get('contracts', {})
  state['_resolved_contracts'] = {
    'SPI200':  SPI_CONTRACTS[_user_contracts['SPI200']],
    'AUDUSD':  AUDUSD_CONTRACTS[_user_contracts['AUDUSD']],
  }
  for key, market in state.get('markets', {}).items():
    if key not in state['_resolved_contracts'] and isinstance(market, dict):
      state['_resolved_contracts'][key] = {
        'multiplier': float(market.get('multiplier', 1.0)),
        'cost_aud': float(market.get('cost_aud', 0.0)),
      }
  return state


def save_state(state: dict, path: Path = Path(STATE_FILE)) -> None:
  '''STATE-02 / D-08 (amended by D-17): atomic write of state to path.

  JSON formatting: sort_keys=True (git-friendly diffs), indent=2 (project
  convention), allow_nan=False (Claude's Discretion). NaN in state is a
  bug; allow_nan=False surfaces it as ValueError immediately rather than
  silently persisting non-standard JSON.

  Keys with `_` prefix are excluded from the persisted JSON per the
  runtime-only convention (D-14 Phase 8).

  OSError on os.replace is RE-RAISED: data integrity > silent failure.

  Durability ordering per D-17: see io._atomic_write docstring.
  '''
  # D-14 (Phase 8): strip runtime-only keys (underscore-prefixed) before
  # dumping. `_resolved_contracts` is the first underscore-prefixed key.
  persisted = {k: v for k, v in state.items() if not k.startswith('_')}
  # Phase 27 #1: route money values through Decimal-quantize-HALF_UP at save
  # time so disk format is canonical AUD-cent precision. _migrate_v8_to_v9
  # called via module global so test patches to it also work.
  persisted = _migrate_v8_to_v9(persisted)
  data = json.dumps(persisted, sort_keys=True, indent=2, allow_nan=False,
                    default=_decimal_default)
  io._atomic_write(data, path)


def mutate_state(
  mutator: Callable[[dict], None],
  path: Path = Path(STATE_FILE),
) -> dict:
  '''Phase 14 D-13 + REVIEWS HIGH #1: lock around the full READ-MODIFY-WRITE.

  Provides the load -> mutate -> save critical section as a single atomic
  unit for any caller (web POST handlers, daily loop). Without this wrapper,
  fcntl on save_state alone admits stale-read lost updates.

  Contract:
    - mutator receives a freshly loaded state dict (post-migration).
    - mutator MUTATES the dict in place; return value ignored.
    - The dict is then saved exactly once via io._save_state_unlocked
      (REUSES the lock acquired here — see io._atomic_write docstring for
      why the inner save_state path can NOT re-acquire the same lock
      from a different fd in the same process without deadlocking).
    - Cross-process coordination via fcntl.LOCK_EX on the destination file.

  Usage:
    def _bump_account(state):
      state['account'] += 100.0
    mutate_state(_bump_account)

  Returns the post-mutation state dict (after save).
  '''
  # Re-entrancy guard: set flag BEFORE fcntl.flock so a nested call raises
  # immediately without ever attempting lock acquisition (avoids deadlock).
  prior = getattr(_MUTATE_STATE_ACTIVE, 'value', False)
  if prior:
    caller = sys._getframe(1).f_code.co_name
    raise RuntimeError(
      f'mutate_state is not re-entrant — do not call mutate_state inside a '
      f'mutate_state callback (detected from caller: {caller!r})'
    )
  _MUTATE_STATE_ACTIVE.value = True
  try:
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
    try:
      fcntl.flock(fd, fcntl.LOCK_EX)
      try:
        state = load_state(path=path, _under_lock=True)
        mutator(state)
        io._save_state_unlocked(state, path=path)
        return state
      finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
      os.close(fd)
  finally:
    _MUTATE_STATE_ACTIVE.value = prior


def mutate_user_state(
  uid: str,
  mutator: Callable[[dict], None],
  path: Path = Path(STATE_FILE),
) -> dict:
  '''Phase 36 D-01/D-02/D-03: per-user outer flock + inner mutate_state.

  Acquisition order: state/users/{uid}.lock (OUTER) -> state.json (INNER).
  Both locks always acquired in this order by all callers — no deadlock.

  The outer lock serializes concurrent writes for the SAME user (e.g. daily
  fan-out vs HTMX write). Cross-user writes are serialized by the inner
  state.json flock in mutate_state regardless (D-04).

  lock_path is constructed relative to CWD so tests can redirect via
  monkeypatch.chdir(tmp_path) (D-03).
  '''
  lock_dir = Path('state/users')
  lock_dir.mkdir(parents=True, exist_ok=True)
  lock_path = lock_dir / f'{uid}.lock'
  # 'a+' creates file if absent; existing content ignored (lock-only fd).
  with open(lock_path, 'a+') as lock_file:
    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
    try:
      return mutate_state(mutator, path=path)
    finally:
      fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def load_user_state(uid: str, path: Path = Path(STATE_FILE)) -> dict:
  '''Phase 36 D-05: return state["users"][uid] slice.

  Re-exported from state_manager so routes can:
    from state_manager import load_user_state
  Only per-user data reads use this; signal/market reads keep load_state().

  Raises KeyError with a clear message if uid is not in state["users"].
  Routes should catch KeyError and raise HTTPException 403 rather than letting
  it propagate as a 500.
  '''
  state = load_state(path=path)
  user = state.get('users', {}).get(uid)
  if user is None:
    raise KeyError(f'user {uid!r} not in state["users"]')
  return user


__all__ = [
  # Public API
  'load_state', 'save_state', 'reset_state', 'mutate_state',
  'mutate_user_state', 'load_user_state',
  'append_warning', 'clear_warnings', 'clear_warnings_by_source',
  'record_trade', 'update_equity_history',
  # Private but re-exported for backward compat with existing test imports
  'MIGRATIONS', '_ADMIN_UID', '_assert_migration_chain_contiguous', '_migrate',
  '_migrate_v1_to_v2', '_migrate_v2_to_v3', '_migrate_v3_to_v4',
  '_migrate_v4_to_v5', '_migrate_v5_to_v6', '_migrate_v6_to_v7',
  '_migrate_v7_to_v8', '_migrate_v8_to_v9', '_migrate_v9_to_v10',
  '_migrate_v10_to_v11', '_migrate_v11_to_v12', '_default_market_registry',
  '_default_strategy_settings',
  'StateV12',
  '_assert_tz_aware', '_coerce_legacy_naive_iso', '_read_signal_strategy_version',
  '_validate_loaded_state', '_validate_trade',
]
