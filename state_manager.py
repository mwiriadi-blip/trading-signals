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
import math  # used in _validate_trade (D-19) + update_equity_history (B-4) finiteness checks
import os  # noqa: F401 — used in _atomic_write/_backup_corrupt (Waves 1/2)
import sys  # noqa: F401 — used in load_state stderr logging (Wave 2)
import tempfile  # noqa: F401 — used in _atomic_write (Wave 1)
import zoneinfo  # noqa: F401 — used in append_warning via _AWST (Wave 2)
from datetime import (  # noqa: F401 — used in append_warning/_backup_corrupt (Waves 1/2)
  UTC,
  datetime,
  timezone,
)
from pathlib import Path
from typing import Any  # noqa: F401 — retained for Waves 1-3 type hints

from system_params import (
  INITIAL_ACCOUNT,  # used in reset_state + MIGRATIONS[2] (Phase 8)
  MAX_WARNINGS,  # noqa: F401 — used in append_warning (Wave 2)
  STATE_FILE,
  STATE_SCHEMA_VERSION,  # noqa: F401 — used in _migrate (Wave 1)
  # Phase 8 additions (D-14, CONF-02): tier vocabulary + default labels
  AUDUSD_CONTRACTS,
  SPI_CONTRACTS,
  _DEFAULT_AUDUSD_LABEL,
  _DEFAULT_SPI_LABEL,
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
  # Phase 8 (v2 schema): CONF-01 + CONF-02 required top-level keys
  'initial_account', 'contracts',
})

# =========================================================================
# Schema migration registry (D-04, STATE-04)
# =========================================================================

MIGRATIONS: dict = {
  1: lambda s: s,  # no-op at v1; hook proves the walk-forward mechanism works
  # Phase 8 v2 backfill (D-15 silent — no append_warning, no log):
  # Pre-Phase-8 state.json missing 'initial_account' and/or 'contracts'
  # gets defaults silently. s.get(..., default) is idempotent when the
  # keys are already present (CONF-01/CONF-02 preserves operator choice).
  2: lambda s: {
    **s,
    'initial_account': s.get('initial_account', INITIAL_ACCOUNT),
    'contracts': s.get('contracts', {
      'SPI200': _DEFAULT_SPI_LABEL,
      'AUDUSD': _DEFAULT_AUDUSD_LABEL,
    }),
  },
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

def _validate_trade(trade: dict) -> None:
  '''D-15 + D-19 (extended 2026-04-21 reviews-revision pass): raise ValueError
  if trade dict is missing required fields or has invalid field values/types.

  Required fields per _REQUIRED_TRADE_FIELDS (11 total).

  D-15 (base):
    instrument must be in {'SPI200', 'AUDUSD'}.
    direction must be in {'LONG', 'SHORT'}.
    n_contracts must be int > 0.

  D-19 (extended-field type checks):
    entry_date, exit_date, exit_reason: must be non-empty str.
    entry_price, exit_price, gross_pnl, multiplier, cost_aud: must be
      finite numeric (int or float); explicitly rejecting bool (Python
      quirk: isinstance(True, int) is True) and NaN/+inf/-inf via
      math.isfinite. Catches Phase 4 wire-up bugs that pass typed
      surrogate values (booleans, NaN from sizing edge cases).

  Raises:
    ValueError: with a specific message naming the offending field
                or value, so Phase 4 wire-up bugs surface immediately.
  '''
  missing = _REQUIRED_TRADE_FIELDS - trade.keys()
  if missing:
    raise ValueError(
      f'record_trade: missing required fields: {sorted(missing)}'
    )
  # D-15 base checks
  if trade['instrument'] not in {'SPI200', 'AUDUSD'}:
    raise ValueError(
      f'record_trade: invalid instrument={trade["instrument"]!r}; '
      f'must be in {{SPI200, AUDUSD}}'
    )
  if trade['direction'] not in {'LONG', 'SHORT'}:
    raise ValueError(
      f'record_trade: invalid direction={trade["direction"]!r}; '
      f'must be in {{LONG, SHORT}}'
    )
  if (
    not isinstance(trade['n_contracts'], int)
    or isinstance(trade['n_contracts'], bool)
    or trade['n_contracts'] <= 0
  ):
    raise ValueError(
      f'record_trade: n_contracts must be int > 0, '
      f'got {trade["n_contracts"]!r}'
    )
  # D-19 extended checks: string fields must be non-empty str
  for field in ('entry_date', 'exit_date', 'exit_reason'):
    value = trade[field]
    if not isinstance(value, str) or len(value) == 0:
      raise ValueError(
        f'record_trade: field {field!r} must be non-empty str, '
        f'got {value!r}'
      )
  # D-19 extended checks: numeric fields must be finite int/float (NOT bool, NOT NaN/inf)
  for field in ('entry_price', 'exit_price', 'gross_pnl', 'multiplier', 'cost_aud'):
    value = trade[field]
    if (
      not isinstance(value, int | float)
      or isinstance(value, bool)
      or not math.isfinite(value)
    ):
      raise ValueError(
        f'record_trade: field {field!r} must be finite numeric '
        f'(int or float, not bool, not NaN/inf), got {value!r}'
      )

def _validate_loaded_state(state: dict) -> None:
  '''D-18 (reviews-revision pass, 2026-04-21): raise ValueError if state
  is missing required top-level keys.

  Called by load_state AFTER _migrate but BEFORE returning a successfully-
  parsed state. The validator's ValueError propagates to caller — it does
  NOT trigger corruption recovery (D-05 narrow catch is preserved: only
  json.JSONDecodeError triggers backup; semantic mismatches raise as bugs).

  Rationale (D-05's bug-surfacing posture extended to schema):
    Valid JSON like {"schema_version": 1} parses fine, will migrate (no-op
    at v1), then downstream code crashes with KeyError on state['account'].
    D-18 makes this surface as ValueError immediately at the load boundary,
    with a specific message naming the missing key(s), so the operator
    sees a real error rather than a confusing downstream crash.

  Validates KEY PRESENCE only — value types/ranges are NOT checked here
  (record_trade does that for trade-shape; equity validation is at the
  update_equity_history boundary per B-4). Narrow validation; one job.

  Required top-level keys per STATE-01:
    schema_version, account, last_run, positions, signals, trade_log,
    equity_history, warnings (8 total).

  Raises:
    ValueError: with sorted list of missing keys for deterministic test
                assertions and stable error messages.
  '''
  missing = _REQUIRED_STATE_KEYS - state.keys()
  if missing:
    raise ValueError(f'state missing required keys: {sorted(missing)}')

# =========================================================================
# Public API
# =========================================================================

def reset_state() -> dict:
  '''STATE-07 / D-01 / D-03: fresh state, $100k account, empty collections.

  Each call returns a NEW dict (no shared mutable references) so that
  mutating one returned state doesn't bleed into a future reset.
  '''
  return {
    'schema_version': STATE_SCHEMA_VERSION,
    'account': INITIAL_ACCOUNT,
    'last_run': None,
    'positions': {                            # D-01: None = inactive
      'SPI200': None,
      'AUDUSD': None,
    },
    'signals': {                              # D-03: FLAT=0 init
      'SPI200': 0,
      'AUDUSD': 0,
    },
    'trade_log': [],
    'equity_history': [],
    'warnings': [],
    # Phase 8 (v2 schema): CONF-01 + CONF-02 top-level keys emitted on
    # fresh reset so corruption-recovery path + initial setup produce a
    # state that passes _validate_loaded_state under schema v2.
    'initial_account': INITIAL_ACCOUNT,
    'contracts': {
      'SPI200': _DEFAULT_SPI_LABEL,
      'AUDUSD': _DEFAULT_AUDUSD_LABEL,
    },
  }

def load_state(path: Path = Path(STATE_FILE), now=None) -> dict:
  '''STATE-01 / STATE-03 / STATE-04 / D-18: load state.json; recover on corruption.

  If path does not exist: returns reset_state() output (fresh state).
    B-3: does NOT save the fresh state — orchestrator (Phase 4) must
    explicitly call save_state to materialize state.json on first run.
  On JSONDecodeError (D-05 — NARROW catch, NOT bare ValueError per Pitfall 4):
    - backup file via _backup_corrupt (D-06 + B-1 path.name + B-2 microsecond ts)
    - reinit via reset_state (STATE-07)
    - append warning with source='state_manager' (D-07)
    - save fresh state to path (so next run reads clean state.json)
    - return fresh state
  On successful parse:
    - walk MIGRATIONS forward (STATE-04)
    - run _validate_loaded_state (D-18 — raises ValueError on missing keys)
    - return validated state

  Schema mismatches (raises by _migrate OR _validate_loaded_state)
  PROPAGATE — those indicate code-vs-state divergence the operator should
  know about (D-05 narrow definition; silently nuking state on a code-side
  typo would mask bugs). The validator runs OUTSIDE the JSONDecodeError
  try/except so its ValueError is not caught as corruption.
  '''
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
    backup_name = _backup_corrupt(path, now)
    state = reset_state()
    state = append_warning(
      state, 'state_manager',
      f'recovered from corruption; backup at {backup_name}',
      now=now,
    )
    save_state(state, path=path)
    return state
  # Happy path: migrate, then D-18 validate, then return
  state = _migrate(state)
  _validate_loaded_state(state)           # D-18: raises ValueError on missing keys
  # D-14 (Phase 8): materialise runtime-only _resolved_contracts from
  # tier labels. Underscore prefix = excluded from save_state (below).
  # KeyError propagates if a label in state['contracts'] is absent from
  # system_params.*_CONTRACTS — caller should repair via --reset.
  state['_resolved_contracts'] = {
    'SPI200':  SPI_CONTRACTS[state['contracts']['SPI200']],
    'AUDUSD':  AUDUSD_CONTRACTS[state['contracts']['AUDUSD']],
  }
  return state

def save_state(state: dict, path: Path = Path(STATE_FILE)) -> None:
  '''STATE-02 / D-08 (amended by D-17): atomic write of state to path.

  JSON formatting: sort_keys=True (git-friendly diffs), indent=2 (project
  convention), allow_nan=False (Claude's Discretion). NaN in state is a
  bug; allow_nan=False surfaces it as ValueError immediately rather than
  silently persisting non-standard JSON.

  Keys with `_` prefix are excluded from the persisted JSON per the
  runtime-only convention (D-14 Phase 8). `_resolved_contracts` is the
  first underscore-prefixed key; future transient keys (e.g., Plan 03's
  `_stale_info`) inherit the same exclusion automatically. The in-memory
  state dict is NOT mutated — the filter builds a new dict for dumping.

  OSError on os.replace is RE-RAISED (RESEARCH §Open Question 2):
  data integrity > silent failure. Orchestrator (Phase 4) handles.

  Durability ordering per D-17: see _atomic_write docstring.
  '''
  # D-14 (Phase 8): strip runtime-only keys (underscore-prefixed) before
  # dumping. `_resolved_contracts` is the first underscore-prefixed key;
  # the convention is load-time materialisation only. Plan 03's
  # `_stale_info` also relies on this filter for transient signalling.
  persisted = {k: v for k, v in state.items() if not k.startswith('_')}
  data = json.dumps(persisted, sort_keys=True, indent=2, allow_nan=False)
  _atomic_write(data, path)

def append_warning(state: dict, source: str, message: str, now=None) -> dict:
  '''D-09 / D-10 / D-11: append {date, source, message}; FIFO trim to MAX_WARNINGS.

  Date format: ISO YYYY-MM-DD in AWST (Australia/Perth) per CLAUDE.md
  "Times always AWST in user-facing output" (RESEARCH §Open Question 3 / A1).

  State_manager is the SOLE writer to state['warnings'] (D-10). All other
  subsystems must call this helper rather than directly appending.

  `now` defaults to datetime.now(timezone.utc); tests inject a fixed UTC
  datetime for determinism without pytest-freezer.

  MAX_WARNINGS rationale (B-5 reviews-revision pass):
    MAX_WARNINGS = 100 is intentionally conservative for v1's daily cadence
    (~5 months of warnings at 1/day average). A bad-day loop generating
    50+ warnings in one run still fits within the bound. Chronic
    high-warning regimes (e.g., a bug emitting hundreds per day) should
    bump MAX_WARNINGS in system_params.py rather than expanding the
    contract here. The FIFO drop-oldest discipline ensures the bound
    is best-effort history — operators see the most recent 100 events,
    which is the actionable window for a daily-cadence system.
  '''
  if now is None:
    now = datetime.now(UTC)
  today_awst = now.astimezone(_AWST).strftime('%Y-%m-%d')
  entry = {'date': today_awst, 'source': source, 'message': message}
  # FIFO trim: keep last (MAX_WARNINGS - 1) + new entry = MAX_WARNINGS total
  state['warnings'] = state['warnings'][-(MAX_WARNINGS - 1):] + [entry]
  return state

def clear_warnings(state: dict) -> dict:
  '''D-02 (Phase 8): clear state['warnings'] after the current run's
  email has been built and dispatched. Preserves D-10 sole-writer
  invariant — state_manager is the ONLY module that mutates
  state['warnings']; notifier reads but never writes.

  Intended flow in main.run_daily_check (canonical sequence per
  Plan 03 revision):
    1. Build email payload reading state['warnings'] as-of run start.
    2. save_state(state) to persist the run's mutations (end of
       run_daily_check step 5).
    3. notifier.send_daily_email(...) — dispatch.
    4. clear_warnings(state) — empty N-1 warnings list FIRST.
    5. If dispatch failed (SendStatus.ok is False), append_warning
       with source='notifier' so NEXT run surfaces the missed send —
       tagged with THIS run's AWST date.
    6. save_state(state) — single post-dispatch save (W3: total
       per-run save count = 2).

  In-place mutation; returns the same dict for chaining.
  '''
  state['warnings'] = []
  return state

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
  '''
  _validate_trade(trade)
  # D-14: closing-half cost split. Phase 2 deducted opening half via
  # compute_unrealised_pnl during the position's lifetime. Phase 3 deducts
  # the closing half here at trade close.
  closing_cost_half = trade['cost_aud'] * trade['n_contracts'] / 2
  net_pnl = trade['gross_pnl'] - closing_cost_half
  state['account'] += net_pnl
  # D-20: append a copy of trade WITH net_pnl, do NOT mutate caller's dict.
  state['trade_log'].append(dict(trade, net_pnl=net_pnl))
  # D-13 / D-01: position is closed atomically with the trade record.
  state['positions'][trade['instrument']] = None
  return state

def update_equity_history(state: dict, date: str, equity: float) -> dict:
  '''STATE-06 / D-04 / B-4: append {date, equity} to equity_history.

  D-04: equity is caller-computed (state_manager is pure I/O hex; must NOT
  import sizing_engine to compute unrealised_pnl — that would break
  hexagonal-lite). Phase 4 orchestrator computes:
    equity = state['account'] + sum(unrealised_pnl across active positions)
  using sizing_engine.compute_unrealised_pnl per active position, then
  passes the total here.

  B-4 (reviews-revision pass, 2026-04-21): minimal boundary validation.
    - date must be str of length 10 (ISO YYYY-MM-DD shape; not a full
      format check — that's the orchestrator's job)
    - equity must be finite numeric (int or float, not bool, not NaN/inf)
    Catches Phase 4 wire-up bugs (e.g., passing a datetime object instead
    of a string, or a NaN that leaked from a sizing edge case) immediately
    rather than relying on save_state's allow_nan=False catch later.

  Date format per CLAUDE.md: ISO YYYY-MM-DD (no time component for
  equity_history entries; daily-cadence system).

  Returns the mutated state dict.

  Raises:
    ValueError: on malformed date (not str / wrong length) or non-finite
                equity (NaN, ±inf, bool, non-numeric).
  '''
  # B-4: validate date shape
  if not isinstance(date, str) or len(date) != 10:
    raise ValueError(
      f'update_equity_history: date must be str of length 10 '
      f'(ISO YYYY-MM-DD), got {date!r}'
    )
  # B-4: validate equity is finite numeric (rejecting bool, NaN, ±inf)
  if (
    not isinstance(equity, int | float)
    or isinstance(equity, bool)
    or not math.isfinite(equity)
  ):
    raise ValueError(
      f'update_equity_history: equity must be finite numeric '
      f'(int or float, not bool, not NaN/inf), got {equity!r}'
    )
  entry = {'date': date, 'equity': equity}
  state['equity_history'].append(entry)
  return state
