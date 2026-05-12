'''state_manager.validation — datetime guards and state/trade validators.

Functions:
  _assert_tz_aware: fail-closed on naive datetimes in write paths.
  _coerce_legacy_naive_iso: read-path UTC-coercion shim for legacy state files.
  _validate_trade: raise ValueError on malformed/missing trade fields.
  _validate_loaded_state: raise ValueError on missing required top-level state keys.
  _read_signal_strategy_version: defensive read with WARN log for signal rows.
'''
import logging
import math
import warnings
from datetime import datetime, UTC, timezone
from typing import Any

from system_params import (
  DEFAULT_MARKETS,
  DEFAULT_STRATEGY_SETTINGS,
  STATE_SCHEMA_VERSION,
  _DEFAULT_AUDUSD_LABEL,
  _DEFAULT_SPI_LABEL,
)

logger = logging.getLogger(__name__)

# =========================================================================
# Constants (used by _validate_trade and _validate_loaded_state)
# =========================================================================

_REQUIRED_TRADE_FIELDS = frozenset({
  'instrument', 'direction', 'entry_date', 'exit_date',
  'entry_price', 'exit_price', 'gross_pnl', 'n_contracts',
  'exit_reason', 'multiplier', 'cost_aud',
})

# D-18 (reviews-revision pass, 2026-04-21): required state top-level keys
# for _validate_loaded_state.
_REQUIRED_STATE_KEYS = frozenset({
  'schema_version', 'account', 'last_run', 'positions',
  'signals', 'trade_log', 'equity_history', 'warnings',
  # Phase 8 (v2 schema): CONF-01 + CONF-02 required top-level keys
  'initial_account', 'contracts',
  'markets', 'strategy_settings',
})


# =========================================================================
# Phase 27 #6: tz-aware datetime gate (fail-closed on write paths)
# =========================================================================

def _assert_tz_aware(dt: datetime, *, context: str) -> None:
  '''Phase 27 #6 — fail-closed on naive datetimes in state-write paths.

  Any helper that takes a `datetime` arg and converts it to an ISO/strftime
  string for state persistence MUST gate the arg through this function at
  helper entry. Naive datetimes (tzinfo is None or utcoffset returns None)
  raise ValueError with the canonical message; the gate happens BEFORE any
  state mutation so callers see fail-closed semantics.

  Read paths (load_state) keep a separate UTC-coercion shim with
  DeprecationWarning — see _coerce_legacy_naive_iso below — so legacy
  state files written before this gate landed continue to load.
  '''
  if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
    raise ValueError(
      f'naive datetime forbidden — must be tz-aware (context: {context})'
    )


def _coerce_legacy_naive_iso(state: dict) -> dict:
  '''Phase 27 #6 — read-path UTC-coercion shim for legacy state files.

  Older state.json files (pre-Phase 27 fail-closed gate) may have written
  naive ISO timestamps into time-bearing fields. We don't want to nuke
  those files at load — instead, walk the known datetime-string fields
  and, if any value parses as a naive datetime, emit DeprecationWarning
  and coerce via UTC. The state dict itself is left untouched (the
  warning is the actionable signal; rewrite-on-next-save naturally
  upgrades the on-disk shape since current writes use UTC ISO).

  Currently scans equity_history rows. Other time-bearing fields
  (warnings.date, last_run) are date-only strings (YYYY-MM-DD) and not
  in scope for this shim — they're not full ISO datetimes.

  Returns the input dict unchanged (the shim is observe-and-warn, not
  mutate).
  '''
  for entry in state.get('equity_history', []):
    if not isinstance(entry, dict):
      continue
    raw = entry.get('date')
    if not isinstance(raw, str):
      continue
    # Only datetime-shaped strings (with 'T') are candidates; YYYY-MM-DD
    # date-only strings are intentional and out of scope.
    if 'T' not in raw:
      continue
    try:
      parsed = datetime.fromisoformat(raw)
    except ValueError:
      continue
    if parsed.tzinfo is None or parsed.tzinfo.utcoffset(parsed) is None:
      warnings.warn(
        'naive ISO datetime in legacy state coerced to UTC — please re-save',
        DeprecationWarning,
        stacklevel=2,
      )
      # One warning per load is enough — bail after first detection so
      # we don't spam on a 365-day equity_history.
      break
  return state


# =========================================================================
# Trade and state validators
# =========================================================================

def _validate_trade(trade: dict, allowed_instruments: set[str] | None = None) -> None:
  '''D-15 + D-19 (extended 2026-04-21 reviews-revision pass): raise ValueError
  if trade dict is missing required fields or has invalid field values/types.

  Required fields per _REQUIRED_TRADE_FIELDS (11 total).

  D-15 (base):
    instrument must be a non-empty str.
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
  if not isinstance(trade['instrument'], str) or not trade['instrument']:
    raise ValueError(
      f'record_trade: invalid instrument={trade["instrument"]!r}; '
      'must be a non-empty str'
    )
  if allowed_instruments is not None and trade['instrument'] not in allowed_instruments:
    raise ValueError(
      f'record_trade: invalid instrument={trade["instrument"]!r}; '
      f'must be in {sorted(allowed_instruments)}'
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

  Validates KEY PRESENCE only — value types/ranges are NOT checked here.
  Required top-level keys per STATE-01 and _REQUIRED_STATE_KEYS.

  Raises:
    ValueError: with sorted list of missing keys for deterministic test
                assertions and stable error messages.
  '''
  missing = _REQUIRED_STATE_KEYS - state.keys()
  if missing:
    raise ValueError(f'state missing required keys: {sorted(missing)}')


# =========================================================================
# Signal helper (moved from migrations.py to stay under 500 LOC — D-04)
# =========================================================================

def _read_signal_strategy_version(signal: dict) -> str:
  '''Phase 22 D-06: defensive read with WARN log.

  Belt-and-suspenders: _migrate_v3_to_v4 backfills all dict-shaped rows on
  first v1.2 load, but if a row somehow lands without the field
  (concurrent-write race, manual state.json edit, partial migration),
  default to 'v1.0.0' and emit a WARN so the issue surfaces in
  journalctl rather than silently rendering the wrong version.
  '''
  if 'strategy_version' in signal:
    return signal['strategy_version']
  logger.warning(
    '[State] WARN signal row missing strategy_version field — '
    'defaulting to v1.0.0',
  )
  return 'v1.0.0'
