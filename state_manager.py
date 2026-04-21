'''State Manager — atomic JSON persistence, corruption recovery, schema migration.

Owns state.json at the repo root and exposes 6 public functions:
  load_state, save_state, record_trade, update_equity_history,
  reset_state, append_warning.

STATE-01..07 (REQUIREMENTS.md §Persistence). Atomic write via tempfile +
fsync(file) + os.replace + fsync(parent dir) — D-08 amended by D-17 (post-
replace dir fsync for rename durability). Corruption = JSONDecodeError only
(D-05); on corrupt: backup + reinit + warn (STATE-03, D-06 + B-1 path.name
derivation + B-2 microsecond timestamp). Schema migration via MIGRATIONS dict
walk-forward (STATE-04). Post-parse semantic validation via
_validate_loaded_state (D-18) — raises ValueError on missing required keys.
Closing-half cost deducted in record_trade per D-14 (Phase 2 deducted opening
half via compute_unrealised_pnl). Trade-dict shape validated to all 11 fields
per D-15 + D-19 extension. record_trade does NOT mutate caller's trade dict
(D-20). update_equity_history validates date + equity at boundary (B-4).

Architecture (hexagonal-lite, CLAUDE.md): I/O hex. This is the ONE module
allowed to do filesystem I/O. Must NOT import signal_engine, sizing_engine,
notifier, dashboard, main, requests, numpy, or pandas. AST blocklist in
tests/test_signal_engine.py::TestDeterminism enforces this structurally.

All clock-dependent functions accept a `now=None` parameter (defaulting to
datetime.now(timezone.utc)) so tests are deterministic without pytest-freezer.

All public mutation functions return the mutated state dict — callers must
capture: `state = append_warning(state, ...)`.

save_state OSError handling (RESEARCH §Open Question 2): re-raise. Silent
save failures cause data loss; orchestrator (Phase 4) handles the exception
explicitly per CLAUDE.md "data integrity > silent failure" stance.
'''
import json  # noqa: F401 — used in save_state/load_state (Waves 1/2)
import os  # noqa: F401 — used in _atomic_write/_backup_corrupt (Waves 1/2)
import sys  # noqa: F401 — used in load_state stderr logging (Wave 2)
import tempfile  # noqa: F401 — used in _atomic_write (Wave 1)
import zoneinfo  # noqa: F401 — used in append_warning via _AWST (Wave 2)
from datetime import (  # noqa: F401 — used in append_warning/_backup_corrupt (Waves 1/2)
  datetime,
  timezone,
)
from pathlib import Path
from typing import Any  # noqa: F401 — retained for Waves 1-3 type hints

from system_params import (
  INITIAL_ACCOUNT,  # noqa: F401 — used in reset_state (Wave 2)
  MAX_WARNINGS,  # noqa: F401 — used in append_warning (Wave 2)
  STATE_FILE,
  STATE_SCHEMA_VERSION,  # noqa: F401 — used in _migrate (Wave 1)
)

# =========================================================================
# Module-level constants (private)
# =========================================================================

_AWST = zoneinfo.ZoneInfo('Australia/Perth')

_REQUIRED_TRADE_FIELDS = frozenset({
  'instrument', 'direction', 'entry_date', 'exit_date',
  'entry_price', 'exit_price', 'gross_pnl', 'n_contracts',
  'exit_reason', 'multiplier', 'cost_aud',
})

# D-18 (reviews-revision pass, 2026-04-21): required state top-level keys
# for _validate_loaded_state. Wave 2 implements the validator; this constant
# is populated NOW so Wave 2 can reference it without import churn.
_REQUIRED_STATE_KEYS = frozenset({
  'schema_version', 'account', 'last_run', 'positions',
  'signals', 'trade_log', 'equity_history', 'warnings',
})

# =========================================================================
# Schema migration registry (D-04, STATE-04)
# =========================================================================

MIGRATIONS: dict = {
  1: lambda s: s,  # no-op at v1; hook proves the walk-forward mechanism works
  # 2: lambda s: {**s, 'new_field': default_value},  # v2 stub for future
}

# =========================================================================
# Private helpers
# =========================================================================

def _atomic_write(data: str, path: Path) -> None:
  '''STATE-02 / D-08 (amended by D-17): tempfile + fsync(file) + os.replace + fsync(parent dir).

  Durability sequence (D-17 ordering — corrected from RESEARCH.md §Pattern 1):
    1. write data to tempfile in same directory as target
    2. flush + fsync(tempfile.fileno())  -- data durable on disk
    3. close tempfile (NamedTemporaryFile context exit)
    4. os.replace(tempfile, target)      -- atomic rename
    5. fsync(parent dir fd) on POSIX     -- rename itself durable on disk

  Why fsync-AFTER-replace: parent-dir fsync's purpose is to make the
  DIRECTORY ENTRY UPDATE (the rename) durable. fsync'ing before the
  replace only persists the not-yet-renamed temp file's directory entry.
  Atomicity (no torn writes) is preserved either way; durability against
  power loss AFTER the rename is only guaranteed by the post-replace fsync.

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
    # tempfile is now closed (NamedTemporaryFile context exit)
    # D-17: os.replace BEFORE parent-dir fsync (rename durability)
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

def _migrate(state: dict) -> dict:
  '''STATE-04: walk schema_version forward to STATE_SCHEMA_VERSION.

  Pitfall 5 (RESEARCH.md): state without schema_version key defaults to 0
  via state.get('schema_version', 0), walks up to current.
  '''
  version = state.get('schema_version', 0)
  while version < STATE_SCHEMA_VERSION:
    version += 1
    state = MIGRATIONS[version](state)
  state['schema_version'] = STATE_SCHEMA_VERSION
  return state

def _backup_corrupt(path: Path, now: datetime) -> str:
  '''D-06 (amended by B-1 + B-2): rename corrupt state file to
  {path.name}.corrupt.<ISO-microsecond-ts>.

  B-1: backup name derived from path.name (NOT hardcoded 'state.json').
  B-2: microsecond-precision timestamp ('%Y%m%dT%H%M%S_%fZ').

  Returns the backup filename (string, basename only) for caller to record
  in the warning message. Wave 2 fills this in.
  '''
  raise NotImplementedError('Wave 2: implement corrupt backup (B-1 + B-2)')

def _validate_trade(trade: dict) -> None:
  '''D-15 + D-19 (reviews-revision pass): raise ValueError if trade dict
  is missing required fields or has invalid field types/values.

  D-15: instrument in {SPI200, AUDUSD}; direction in {LONG, SHORT};
    n_contracts int > 0; all 11 required fields present per
    _REQUIRED_TRADE_FIELDS.
  D-19: extends to all 8 remaining fields:
    entry_date/exit_date/exit_reason must be non-empty str;
    entry_price/exit_price/gross_pnl/multiplier/cost_aud must be finite
    numeric (rejecting bool via isinstance bool check, rejecting NaN/inf
    via math.isfinite).

  Wave 3 fills this in (and adds `import math` to the imports block).
  '''
  raise NotImplementedError('Wave 3: implement trade validation (D-15 + D-19)')

def _validate_loaded_state(state: dict) -> None:
  '''D-18 (reviews-revision pass, 2026-04-21): raise ValueError if state
  is missing required top-level keys per _REQUIRED_STATE_KEYS.

  Called by load_state AFTER _migrate but BEFORE returning. Runs OUTSIDE
  the JSONDecodeError except block so its ValueError propagates to caller
  — does NOT trigger corruption recovery (D-05 narrow catch is preserved:
  only json.JSONDecodeError triggers backup; semantic mismatches raise as
  bugs).

  Validates KEY PRESENCE only — value types are NOT checked here (record_trade
  does that for trade-shape; equity validation is at the
  update_equity_history boundary per B-4).

  Wave 2 fills this in.
  '''
  raise NotImplementedError('Wave 2: implement state-shape validation (D-18)')

# =========================================================================
# Public API
# =========================================================================

def reset_state() -> dict:
  '''STATE-07 / D-01 / D-03: fresh state, $100k account, empty collections.

  Wave 2 fills this in. See PATTERNS.md §reset_state canonical shape.
  '''
  raise NotImplementedError('Wave 2: implement reset_state')

def load_state(path: Path = Path(STATE_FILE), now=None) -> dict:
  '''STATE-01 / STATE-03 / STATE-04 / D-18: load state.json; recover on corruption.

  If path does not exist: returns a fresh state dict. The file is NOT
  created on this call (B-3 — no side-effect on read; state_manager.py
  never auto-saves on load). The orchestrator (Phase 4) must explicitly
  call save_state(state) after load_state on first run to materialize
  state.json. (Wave 2 will refactor the literal here to call reset_state().)

  On JSONDecodeError (D-05): backup file (D-06 + B-1 + B-2), reinit, append
  warning with source='state_manager' (D-07), save fresh state (this branch
  DOES persist — recovery rewrites state.json), return it.
    - Wave 1: corruption branch raises NotImplementedError('Wave 2: ...')
    - Wave 2: implements the corruption recovery
  On successful parse: walk MIGRATIONS forward (STATE-04), run
  _validate_loaded_state (D-18 — raises ValueError on missing required
  keys, Wave 2), and return.
  '''
  if not path.exists():
    # Wave 1: literal fresh-state shape (Wave 2 refactors to call reset_state()).
    # B-3: do NOT save here — no side-effect on read; orchestrator owns
    # file materialization via explicit save_state(state) on first run.
    return {
      'schema_version': STATE_SCHEMA_VERSION,
      'account': INITIAL_ACCOUNT,
      'last_run': None,
      'positions': {'SPI200': None, 'AUDUSD': None},
      'signals': {'SPI200': 0, 'AUDUSD': 0},
      'trade_log': [],
      'equity_history': [],
      'warnings': [],
    }
  raw = path.read_bytes()
  try:
    state = json.loads(raw)
  except json.JSONDecodeError as exc:
    # Wave 2 implements: backup + reinit + warn (and that branch DOES save_state).
    raise NotImplementedError('Wave 2: implement corruption recovery branch') from exc
  return _migrate(state)

def save_state(state: dict, path: Path = Path(STATE_FILE)) -> None:
  '''STATE-02 / D-08 (amended by D-17): atomic write of state to path.

  JSON formatting: sort_keys=True (git-friendly diffs), indent=2 (project
  convention), allow_nan=False (Claude's Discretion). NaN in state is a
  bug; allow_nan=False surfaces it as ValueError immediately rather than
  silently persisting non-standard JSON.

  OSError on os.replace is RE-RAISED (RESEARCH §Open Question 2):
  data integrity > silent failure. Orchestrator (Phase 4) handles.

  Durability ordering per D-17: see _atomic_write docstring.
  '''
  data = json.dumps(state, sort_keys=True, indent=2, allow_nan=False)
  _atomic_write(data, path)

def append_warning(state: dict, source: str, message: str, now=None) -> dict:
  '''D-09 / D-10 / D-11: append {date, source, message}; FIFO trim to MAX_WARNINGS.

  Date format: ISO YYYY-MM-DD in AWST (Australia/Perth) per CLAUDE.md.
  All subsystems route through this helper — state_manager is the SOLE
  writer to state['warnings'] (D-10) to prevent schema drift.

  MAX_WARNINGS rationale (B-5): conservative bound for v1 daily-cadence
  (~5 months at 1/day); chronic high-warning regimes should bump the
  constant in system_params.py rather than expanding the contract here.

  Wave 2 fills this in. See PATTERNS.md §append_warning pattern.
  '''
  raise NotImplementedError('Wave 2: implement append_warning')

def record_trade(state: dict, trade: dict) -> dict:
  '''STATE-05 / D-13 / D-14 / D-15 / D-16 / D-19 / D-20: record a closed trade.

  D-15 + D-19: validates trade shape and field types; raises ValueError
    on missing/wrong fields (extended to all 11 fields per D-19).
  D-14: deducts CLOSING-HALF cost (cost_aud * n_contracts / 2) from
    trade['gross_pnl']; computes net_pnl.
  D-13: appends to trade_log (as a copy with net_pnl per D-20), adjusts
    state['account'], sets state['positions'][trade['instrument']] = None
    (atomic mutation).
  D-16: NOT idempotent — caller must call exactly once per closed_trade.
  D-20 (reviews-revision pass): does NOT mutate caller's trade dict.
    The trade_log entry is built via dict(trade, net_pnl=net_pnl).

  CRITICAL Phase 4 boundary (RESEARCH §Pitfall 3):
    trade['gross_pnl'] MUST be raw price-delta P&L:
      (exit_price - entry_price) * n_contracts * multiplier  (LONG)
      (entry_price - exit_price) * n_contracts * multiplier  (SHORT)
    It MUST NOT be Phase 2's ClosedTrade.realised_pnl — that already has
    the closing cost deducted by Phase 2 _close_position. Passing
    realised_pnl as gross_pnl causes double-counting of the closing cost.
    Phase 4 orchestrator is responsible for this projection.

  Wave 3 fills this in. See PATTERNS.md §record_trade validation pattern.
  '''
  raise NotImplementedError('Wave 3: implement record_trade (D-13/D-14/D-15/D-16/D-19/D-20)')

def update_equity_history(state: dict, date: str, equity: float) -> dict:
  '''STATE-06 / D-04 / B-4: append {date, equity} to equity_history.

  D-04: equity is caller-computed (state_manager is pure I/O hex; must NOT
  import sizing_engine to compute unrealised_pnl). Phase 4 orchestrator
  sums state['account'] + sum(unrealised_pnl across active positions) and
  passes the total here.

  B-4 (reviews-revision pass): minimal boundary validation — date must be
  str of length 10 (ISO YYYY-MM-DD shape); equity must be finite numeric
  (rejecting bool, NaN, ±inf via math.isfinite). Raises ValueError on
  malformed input.

  Wave 3 fills this in (and adds `import math` to the imports block).
  '''
  raise NotImplementedError('Wave 3: implement update_equity_history (D-04 + B-4)')
