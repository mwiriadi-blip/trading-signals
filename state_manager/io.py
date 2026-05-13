'''state_manager.io — I/O kernel for atomic state persistence.

Owns the durable-write and lock primitives. No domain logic.

_atomic_write_unlocked: tempfile + fsync + os.replace + dir-fsync (no lock).
_atomic_write: same, wrapped with fcntl.LOCK_EX acquire/release.
_backup_corrupt: rename corrupt state file to .corrupt.<ts> backup.
_save_state_unlocked: same as save_state but skips lock acquire — used
  by mutate_state which already holds the lock.

POSIX flock intra-process reentrancy note (D-02, Phase 14):
  flock locks the open-file-description, NOT the inode/path. Two fds in
  the SAME process do NOT share lock ownership; a second LOCK_EX acquire
  on the same file from the same process blocks forever. mutate_state
  (in __init__) therefore calls _save_state_unlocked / _atomic_write_unlocked
  directly rather than routing through save_state -> _atomic_write.
'''
import fcntl
import json
import logging
import math
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from system_params import STATE_FILE, AUD_QUANTIZE, AUD_ROUND, _decimal_default
from decimal import Decimal as _Decimal

logger = logging.getLogger(__name__)


# =========================================================================
# Money-quantize helper (mirrors save_state / _save_state_unlocked usage)
# =========================================================================

def _quantize_aud(v) -> float:
  '''Route a money-shaped value through Decimal-quantize-HALF_UP.

  Mirrors state_manager._quantize_aud — kept here so io.py is self-contained
  for the save paths. None / NaN / inf pass through unchanged.
  '''
  if v is None:
    return v
  if isinstance(v, bool):
    return v
  if isinstance(v, int | float):
    if isinstance(v, float) and not math.isfinite(v):
      return v
  try:
    return float(_Decimal(str(v)).quantize(AUD_QUANTIZE, rounding=AUD_ROUND))
  except Exception:
    return v


def _quantize_state_money(s: dict) -> dict:
  '''Apply AUD-cent quantize to all money-denominated state fields.

  Same logic as _migrate_v8_to_v9 in migrations.py; kept in io.py so
  save_state / _save_state_unlocked can call it without importing migrations
  (avoids a circular import: __init__ -> io -> migrations -> __init__).
  '''
  out = dict(s)
  if 'account' in out:
    out['account'] = _quantize_aud(out['account'])
  if 'initial_account' in out:
    out['initial_account'] = _quantize_aud(out['initial_account'])

  eq_hist = out.get('equity_history')
  if isinstance(eq_hist, list):
    new_hist = []
    for row in eq_hist:
      if isinstance(row, dict) and 'equity' in row:
        new_row = dict(row)
        new_row['equity'] = _quantize_aud(row['equity'])
        new_hist.append(new_row)
      else:
        new_hist.append(row)
    out['equity_history'] = new_hist

  paper_trades = out.get('paper_trades')
  if isinstance(paper_trades, list):
    new_pt = []
    for row in paper_trades:
      if isinstance(row, dict):
        new_row = dict(row)
        for f in ('realised_pnl', 'unrealised_pnl', 'entry_cost_aud',
                  'entry_price', 'exit_price'):
          if f in new_row:
            new_row[f] = _quantize_aud(new_row[f])
        new_pt.append(new_row)
      else:
        new_pt.append(row)
    out['paper_trades'] = new_pt

  trade_log = out.get('trade_log')
  if isinstance(trade_log, list):
    new_tl = []
    for row in trade_log:
      if isinstance(row, dict):
        new_row = dict(row)
        for f in ('gross_pnl', 'net_pnl', 'cost_aud'):
          if f in new_row:
            new_row[f] = _quantize_aud(new_row[f])
        new_tl.append(new_row)
      else:
        new_tl.append(row)
    out['trade_log'] = new_tl

  return out


# =========================================================================
# Atomic write helpers
# =========================================================================

def _atomic_write_unlocked(data: str, path: Path) -> None:
  '''STATE-02 / D-08 (amended by D-17): tempfile + fsync(file) + os.replace +
  fsync(parent dir). NO LOCK ACQUISITION — caller is responsible for holding
  fcntl.LOCK_EX on `path` if cross-process serialization is required.

  This unlocked helper is the I/O kernel of the durable write. Used by:
    - _atomic_write (acquires the lock + delegates)
    - mutate_state (already holds the lock from its outer flock window)

  Splitting prevents the intra-process flock-on-different-fd deadlock that
  would arise if mutate_state's inner save_state path tried to acquire a
  SECOND fcntl.LOCK_EX on the same file (POSIX/BSD flock locks the
  open-file-description; two fds in the same process do NOT share lock
  ownership and the second acquire blocks forever waiting for the first
  to release).

  Durability sequence (D-17 ordering):
    1. write data to tempfile in same directory as target
    2. flush + fsync(tempfile.fileno())  -- data durable on disk
    3. close tempfile (NamedTemporaryFile context exit)
    4. os.replace(tempfile, target)      -- atomic rename
    5. fsync(parent dir fd) on POSIX     -- rename itself durable on disk

  Tempfile cleanup: try/finally unlinks the tempfile if any step before
  os.replace raises (Pitfall 1). On success, tmp_path_str is set to None
  so the finally clause is a no-op.
  '''
  parent = path.parent
  tmp_path_str = None
  try:
    with tempfile.NamedTemporaryFile(
      dir=parent, delete=False, mode='w', suffix='.tmp', encoding='utf-8',
    ) as tmp:
      tmp_path_str = tmp.name
      tmp.write(data)
      tmp.flush()
      os.fsync(tmp.fileno())
    # tempfile closed; D-17: os.replace BEFORE parent-dir fsync
    os.replace(tmp_path_str, path)
    if os.name == 'posix':
      dir_fd = os.open(str(parent), os.O_RDONLY)
      try:
        os.fsync(dir_fd)
      finally:
        os.close(dir_fd)
    tmp_path_str = None  # success: do not delete in finally
  finally:
    if tmp_path_str is not None:
      try:
        os.unlink(tmp_path_str)
      except FileNotFoundError:
        pass


def _atomic_write(data: str, path: Path) -> None:
  '''STATE-02 / D-08 (amended by D-17, then by Phase 14 D-13):
  tempfile + fsync(file) + os.replace + fsync(parent dir),
  serialized cross-process via fcntl.LOCK_EX advisory lock on the destination file.

  Wraps _atomic_write_unlocked with a fresh fcntl.LOCK_EX acquire/release
  cycle. Public API for callers that DON'T already hold the lock (e.g.,
  save_state called directly, --reset, test fixtures).

  Phase 14 D-13 lock semantics:
    - fcntl.flock advisory lock on the DESTINATION file's open fd
    - Held across the entire critical section (write tempfile -> fsync ->
      rename -> dir fsync)
    - Released by explicit fcntl.LOCK_UN + os.close(lock_fd) in outer finally
    - Blocking-indefinite (no timeout) per D-13
    - Lock fd opened via os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
    - POSIX-only (Linux droplet + macOS dev); not portable to Windows
    - INTRA-PROCESS REENTRANCY: mutate_state holds its own outer flock and
      calls _atomic_write_unlocked directly via _save_state_unlocked,
      bypassing this re-acquisition. Cross-process safety preserved.
  '''
  lock_fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
  try:
    fcntl.flock(lock_fd, fcntl.LOCK_EX)  # blocks until exclusive lock acquired
    try:
      _atomic_write_unlocked(data, path)
    finally:
      fcntl.flock(lock_fd, fcntl.LOCK_UN)
  finally:
    os.close(lock_fd)


def _backup_corrupt(path: Path, now: datetime) -> str:
  '''D-06 (amended by B-1 + B-2, 2026-04-21 reviews-revision pass):
  rename corrupt state file to {path.name}.corrupt.<ISO-microsecond-ts>.

  B-1: backup name derived from path.name (NOT hardcoded 'state.json') so
    the helper is robust to non-default paths in tests and future reuse.
    For the canonical path (path.name == 'state.json'), the result is
    'state.json.corrupt.<ts>' which still matches REQUIREMENTS.md STATE-03.
  B-2: ISO 8601 basic format with MICROSECOND precision (%Y%m%dT%H%M%S_%fZ)
    eliminates same-second collision risk. Format: 20260421T093045_123456Z.

  Returns the backup filename (basename only, no directory) for caller to
  record in the corruption-recovery warning message.

  Logs a [State] WARNING line to stderr per CLAUDE.md §Conventions.
  '''
  ts = now.strftime('%Y%m%dT%H%M%S_%fZ')      # B-2: microsecond precision
  backup_name = f'{path.name}.corrupt.{ts}'   # B-1: derive from path.name
  backup_path = path.parent / backup_name
  os.rename(str(path), str(backup_path))
  print(
    f'[State] WARNING: state.json was corrupt; backup at {backup_name}',
    file=sys.stderr,
  )
  return backup_name


def _save_state_unlocked(state: dict, path: Path) -> None:
  '''Same as save_state but uses _atomic_write_unlocked — caller MUST already
  hold fcntl.LOCK_EX on `path`. Used exclusively by mutate_state to avoid the
  intra-process flock-on-different-fd deadlock (see _atomic_write docstring).

  D-14 underscore-key filter applies identically; allow_nan=False preserved.
  Phase 27 #1: same Decimal-quantize-HALF_UP coercion + _decimal_default
  encoder as save_state.
  '''
  persisted = {k: v for k, v in state.items() if not k.startswith('_')}
  persisted = _quantize_state_money(persisted)
  data = json.dumps(persisted, sort_keys=True, indent=2, allow_nan=False,
                    default=_decimal_default)
  _atomic_write_unlocked(data, path)
