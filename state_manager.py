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

Phase 14 D-13 amendment to D-15: state_manager is now a peer writer to
state.json with the FastAPI web layer (web/routes/trades.py mutations).
Cross-process coordination via fcntl.LOCK_EX advisory lock acquired in
_atomic_write. Lock held across the tempfile→fsync→replace→dir-fsync
critical section; released by explicit fcntl.LOCK_UN + os.close on the
lock fd.

REVIEWS HIGH #1 fix: fcntl on save_state ALONE serializes the WRITE
but not the READ-MODIFY-WRITE — two writers can both load the same
pre-lock snapshot, both serialize the write, and the second save
clobbers the first. The new public helper mutate_state(mutator, path)
holds the lock across the FULL load → mutate → save critical section.
Web routes and main.py daily loop both call mutate_state.

INTRA-PROCESS REENTRANCY (corrected per IN-02 / Rule 1 fix vs original
RESEARCH §Pattern 9 which mistakenly claimed reentrancy across DIFFERENT
fds): on POSIX, fcntl.flock locks the open-file-description, NOT the
inode/path. Two fds in the SAME process do NOT share lock ownership;
the inner save_state must call _atomic_write_unlocked when the outer
mutate_state already holds the lock. See _atomic_write docstring.
Cross-process safety is preserved (separate file descriptors).

The sole-writer invariant for state['warnings'] (TRADE-06) is
unchanged: only state_manager.append_warning writes to that key; web
handlers never call it.
'''
import fcntl  # Phase 14 D-13: cross-process advisory lock around _atomic_write + mutate_state
import json  # noqa: F401 — used in save_state/load_state (Waves 1/2)
import logging  # Phase 22 D-06: WARN log for missing strategy_version on signal rows
import math  # used in _validate_trade (D-19) + update_equity_history (B-4) finiteness checks
import os  # noqa: F401 — used in _atomic_write/_backup_corrupt (Waves 1/2)
import sys  # noqa: F401 — used in load_state stderr logging (Wave 2)
import tempfile  # noqa: F401 — used in _atomic_write (Wave 1)
import warnings  # Phase 27 #6: read-path UTC-coercion shim emits DeprecationWarning
import zoneinfo  # noqa: F401 — used in append_warning via _AWST (Wave 2)
from datetime import (  # noqa: F401 — used in append_warning/_backup_corrupt (Waves 1/2)
  UTC,
  datetime,
  timezone,
)
from pathlib import Path
from typing import Any, Callable  # noqa: F401 — Callable used in mutate_state signature (Phase 14)

from system_params import (
  INITIAL_ACCOUNT,  # used in reset_state + MIGRATIONS[2] (Phase 8)
  MAX_WARNINGS,  # noqa: F401 — used in append_warning (Wave 2)
  STATE_FILE,
  STATE_SCHEMA_VERSION,  # noqa: F401 — used in _migrate (Wave 1)
  # Phase 8 additions (D-14, CONF-02): tier vocabulary + default labels
  AUDUSD_CONTRACTS,
  DEFAULT_MARKETS,
  DEFAULT_STRATEGY_SETTINGS,
  SPI_CONTRACTS,
  _DEFAULT_AUDUSD_LABEL,
  _DEFAULT_SPI_LABEL,
  # Phase 27 #1: Decimal money-math precision boundary
  AUD_QUANTIZE,  # noqa: F401 — used in _migrate_v8_to_v9
  AUD_ROUND,  # noqa: F401 — used in _migrate_v8_to_v9
  _decimal_default,  # used in save_state json.dumps default= kwarg
  # Phase 27 #11 (Plan 27-09): strategy_version stamp for bare-int promotion
  STRATEGY_VERSION,  # used in _migrate_v9_to_v10
)
from decimal import Decimal as _Decimal

# =========================================================================
# Module-level constants (private)
# =========================================================================

logger = logging.getLogger(__name__)  # Phase 22 D-06: WARN on defensive-read fallback

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
# Schema migration registry (D-04, STATE-04)
# =========================================================================

def _migrate_v1_to_v2(s: dict) -> dict:
  '''Phase 8 CONF-01/CONF-02 backfill: add initial_account (default $100k)
  and contracts (default mini tier) for pre-v2 state files.

  D-15 silent migration: no append_warning, no log. s.get(..., default) is
  idempotent when the keys are already present — operator choice (a state
  file with 'initial_account'/'contracts' already set) is preserved.
  '''
  return {
    **s,
    'initial_account': s.get('initial_account', INITIAL_ACCOUNT),
    'contracts': s.get('contracts', {
      'SPI200': _DEFAULT_SPI_LABEL,
      'AUDUSD': _DEFAULT_AUDUSD_LABEL,
    }),
  }


def _migrate_v2_to_v3(s: dict) -> dict:
  '''Phase 14 D-09: backfill manual_stop=None on every existing Position dict.

  Position TypedDict gained manual_stop in Phase 14. Existing v2 state files
  have positions like {SPI200: None, AUDUSD: {direction:..., entry_price:...}}
  — the dict-valued positions need manual_stop=None added; None positions
  stay None (no position to migrate).

  Idempotent: running on already-v3 data is a no-op (manual_stop preserved
  via pos.get(...) returning the existing value, then dict-merge keeping it).
  load_state passes the result through _validate_loaded_state which checks
  KEY PRESENCE only — manual_stop value is enforced by sizing_engine
  get_trailing_stop NaN guards (Plan 14-03).

  D-15 silent migration: no append_warning, no log. Backfill is transparent
  to the operator (mirrors _migrate_v1_to_v2 contract).
  '''
  positions = s.get('positions', {})
  new_positions = {}
  for instrument, pos in positions.items():
    if pos is None:
      new_positions[instrument] = None
    else:
      new_positions[instrument] = {**pos, 'manual_stop': pos.get('manual_stop')}
  return {**s, 'positions': new_positions}


def _migrate_v3_to_v4(s: dict) -> dict:
  '''Phase 22 D-04 / D-05 (v1.2): backfill strategy_version on existing
  dict-shaped signal rows.

  Existing rows on first v1.2 deploy were produced under v1.1 logic
  (same signal logic as v1.0; hosting change only). Stamp 'v1.1.0' so
  historical rows are honest about the deployment lineage.

  Idempotent: rows that already carry a strategy_version field are NOT
  overwritten (defensive — supports replayed migrations and manual
  state.json edits — see TestMigrateV3ToV4 in tests/test_state_manager.py).

  Legacy int-shape signal rows (Phase 3 reset_state, e.g. signals.SPI200=0)
  are skipped: only dict-shaped rows are migrated. main.py per the D-08
  upgrade branch (Pitfall 7) tolerates both shapes on read and always
  writes the dict shape on the next run, so any int-shape row will
  acquire strategy_version on its next signal write.

  D-15 silent migration: no append_warning, no log line. Mirror of
  _migrate_v2_to_v3's contract.
  '''
  signals = s.get('signals', {})
  for sig in signals.values():
    if isinstance(sig, dict) and 'strategy_version' not in sig:
      sig['strategy_version'] = 'v1.1.0'
  return s


def _migrate_v4_to_v5(s: dict) -> dict:
  '''Phase 17 D-08 (v1.2): backfill empty ohlc_window + indicator_scalars
  on existing dict-shaped signal rows.

  Existing rows on first v1.2.x deploy carry signal / strategy_version /
  last_scalars but no ohlc_window / indicator_scalars. Stamp empty list +
  empty dict; main.py populates on the next daily run.

  Idempotent: rows that already carry a populated ohlc_window or
  indicator_scalars are NOT overwritten (defensive — supports replayed
  migrations and partial-state edits). Two independent 'field' not in sig
  guards so a partial-prior-state row still backfills the missing field
  per LEARNINGS 2026-04-27 idempotency rule.

  Legacy int shape (Phase 3 reset_state) is skipped: only dict-shaped
  signal rows are migrated. main.py reads both shapes per D-08 upgrade
  branch.

  D-15 silent migration: no append_warning, no log line.
  '''
  signals = s.get('signals', {})
  for inst_key, sig in signals.items():
    if isinstance(sig, dict):
      if 'ohlc_window' not in sig:
        sig['ohlc_window'] = []
      if 'indicator_scalars' not in sig:
        sig['indicator_scalars'] = {}
  return s


def _migrate_v5_to_v6(s: dict) -> dict:
  '''Phase 19 (v1.2): introduce paper_trades array.

  v5 rows had no paper_trades concept. Add empty list at top level.
  Idempotent: never overwrite an existing populated paper_trades.

  D-15 silent migration: no append_warning, no log line — operator-driven
  ledger; first POST will populate it on demand.
  '''
  if 'paper_trades' not in s:
    s['paper_trades'] = []
  return s


def _migrate_v6_to_v7(s: dict) -> dict:
  '''Phase 20 (v1.2): introduce last_alert_state field on paper_trades rows.

  Existing rows on first v1.2.x post-deploy load have no last_alert_state.
  Stamp None -- the next daily-run alert evaluator treats None as a fresh
  state and emails on first transition (D-05).

  Idempotent: never overwrite an existing populated last_alert_state value.
  Defensive: only touches dict-shaped rows (skips any malformed entries).
  D-15 silent migration (matches Phase 22 D-15 + Phase 17/19 precedent):
  no append_warning, no log line.
  '''
  for row in s.get('paper_trades', []):
    if isinstance(row, dict) and 'last_alert_state' not in row:
      row['last_alert_state'] = None
  return s


def _default_market_registry() -> dict:
  return {key: dict(value) for key, value in DEFAULT_MARKETS.items()}


def _default_strategy_settings(markets: dict | None = None) -> dict:
  source = markets if markets is not None else DEFAULT_MARKETS
  return {
    key: dict(DEFAULT_STRATEGY_SETTINGS)
    for key in source
  }


def _migrate_v7_to_v8(s: dict) -> dict:
  '''Phase 24: add market registry + per-market strategy settings.

  Preserves existing SPI/AUDUSD state while making future market additions
  data-driven. Existing manually added keys in positions/signals are also
  represented if present.
  '''
  markets = s.get('markets')
  if not isinstance(markets, dict):
    markets = _default_market_registry()
  else:
    merged = _default_market_registry()
    for key, value in markets.items():
      if isinstance(value, dict):
        merged[key] = {**merged.get(key, {}), **value}
    markets = merged

  for container_name, default_value in (
    ('positions', None),
    ('signals', 0),
  ):
    container = s.setdefault(container_name, {})
    if isinstance(container, dict):
      for key in markets:
        container.setdefault(key, default_value)

  settings = s.get('strategy_settings')
  if not isinstance(settings, dict):
    settings = _default_strategy_settings(markets)
  else:
    merged_settings = _default_strategy_settings(markets)
    for key, value in settings.items():
      if isinstance(value, dict):
        merged_settings[key] = {**merged_settings.get(key, dict(DEFAULT_STRATEGY_SETTINGS)), **value}
    settings = merged_settings

  return {**s, 'markets': markets, 'strategy_settings': settings}


def _quantize_aud(v) -> float:
  '''Phase 27 #1: route a money-shaped value through Decimal-quantize-HALF_UP
  and return as a float (state.json wire format stays JSON-numeric for
  backward compatibility with existing readers).

  None / NaN / inf flow through unchanged so non-money sentinels are
  preserved (e.g., realised_pnl=None for an open paper trade).

  Float→Decimal coercion goes via str(v) so float-binary repr noise
  ('1234.5600000000004') is stripped before quantize.
  '''
  if v is None:
    return v
  if isinstance(v, bool):
    # Defensive: bool is a subclass of int; a bool money field is a bug
    # we want to preserve as-is rather than silently coerce to 1.00 / 0.00.
    return v
  if isinstance(v, int | float):
    if isinstance(v, float) and not math.isfinite(v):
      return v  # NaN / inf — don't coerce; downstream save_state allow_nan=False catches.
  try:
    return float(_Decimal(str(v)).quantize(AUD_QUANTIZE, rounding=AUD_ROUND))
  except Exception:
    return v  # un-coercible (string label, etc.) — leave untouched.


def _migrate_v8_to_v9(s: dict) -> dict:
  '''Phase 27 #1: quantize all money-denominated state.json fields via
  Decimal(AUD_QUANTIZE, HALF_UP) so AUD-cent precision survives every
  save/load cycle (truth #4: round-trip preserves cents).

  Idempotent: quantizing an already-quantized value yields the same value.
  Defensive: only touches dict-shaped rows; missing fields are skipped.
  D-15 silent migration: no append_warning, no log line.

  Money fields touched (per plan must_haves):
    state['account']                       — top-level cash balance
    state['initial_account']               — reset baseline
    state['equity_history'][i]['equity']   — daily equity rows
    state['paper_trades'][i]['realised_pnl']     — closed paper-trade PnL
    state['paper_trades'][i]['unrealised_pnl']   — if persisted (None on open)
    state['paper_trades'][i]['entry_cost_aud']   — opening-half cost
    state['trade_log'][i]['gross_pnl' / 'net_pnl' / 'cost_aud']  — closed trades

  NOT touched: position fields (entry_price/atr_entry/peak_price are price-
  domain, not AUD-cent-domain), signal fields, OHLC/indicator scalars.
  These remain float64 — the Decimal slice is ONLY at the AUD-money boundary.
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


def _migrate_v9_to_v10(s: dict) -> dict:
  '''Phase 27 #11 (Plan 27-09 / Phase 26 DEBT.md R5): drop bare-int signal
  back-compat. Promote any legacy bare-int rows in state['signals'] to the
  canonical dict shape with keys {signal, strategy_version}.

  Truth #1 (post-migration invariant): state['signals'][market_id] is a
  dict for every state that has flowed through load_state(). The renderer
  pin in dashboard_renderer/components/signals.py asserts this hard.

  Phase 27 WR-02 scope clarification: several non-renderer call sites
  (notifier/formatters._detect_signal_changes / _extract_signal /
  _extract_signal_int, dashboard_legacy/calc_rows._render_entry_target_row,
  daily_run.py old_signals capture + 3.g read, crash_boundary._build_*)
  retain the legacy `isinstance(raw, int)` branch by design — they are
  reachable from test fixtures that build state dicts directly without
  routing through load_state() (e.g. tests/fixtures/notifier/empty_state.json,
  tests/test_notifier.py::TestDetectSignalChanges::test_detect_legacy_int_signal_shape).
  Removing the branches reds those tests; updating every fixture is
  out-of-scope for Plan 27-09. The post-migration invariant therefore
  applies on the *production* read path (everything that hits load_state)
  but is intentionally relaxed on the *test* read path.

  Pre-migration legacy shape (Phase 3 reset_state, in-tree until 27-09):
    state['signals']['SPI200'] = 0   # FLAT
    state['signals']['SPI200'] = 1   # LONG
    state['signals']['SPI200'] = -1  # SHORT

  Post-migration canonical shape:
    state['signals']['SPI200'] = {
      'signal': 0 | 1 | -1,
      'strategy_version': STRATEGY_VERSION,
    }

  We use the production field name `signal` (NOT `direction` as the plan
  text says — production code at main.py:1190, signals.py:45,
  sizing_engine.py:153 all use `signal`). Plan deviation Rule 1 (plan vs
  reality).

  Idempotent: dict-shaped rows pass through unchanged (no overwrite of
  existing strategy_version or other fields like last_close /
  last_scalars / ohlc_window).

  Defensive: only touches int-shaped rows; missing/None values skipped.
  D-15 silent migration: no append_warning, no log line.

  After this migrator runs at load_state, the renderer's defensive
  `isinstance(record, int)` branch is dead code (deleted in
  dashboard_renderer/components/signals.py).
  '''
  signals = s.get('signals', {})
  if not isinstance(signals, dict):
    return s
  out_signals = dict(signals)
  for k, v in signals.items():
    # Promote ONLY bare-int rows. Bool is an int subclass — exclude it
    # defensively (no production path produces bool here, but `True is 1`
    # in Python's ABC tree).
    if isinstance(v, int) and not isinstance(v, bool):
      out_signals[k] = {
        'signal': v,
        'strategy_version': STRATEGY_VERSION,
      }
  out = dict(s)
  out['signals'] = out_signals
  return out


MIGRATIONS: dict = {
  1: lambda s: s,  # no-op at v1; hook proves the walk-forward mechanism works
  2: _migrate_v1_to_v2,  # Phase 8 IN-06: named function for future migrations
  3: _migrate_v2_to_v3,  # Phase 14 D-09: backfill manual_stop on existing Positions
  4: _migrate_v3_to_v4,  # Phase 22 D-04/D-05/D-09: strategy_version on signal rows
  5: _migrate_v4_to_v5,  # Phase 17 D-08: ohlc_window + indicator_scalars on signal rows
  6: _migrate_v5_to_v6,  # Phase 19 D-08: paper_trades[] top-level array
  7: _migrate_v6_to_v7,  # Phase 20 D-08: last_alert_state on paper_trades[] rows
  8: _migrate_v7_to_v8,  # Phase 24: markets + strategy_settings
  9: _migrate_v8_to_v9,  # Phase 27 #1: Decimal-quantize money fields (AUD cents, HALF_UP)
  10: _migrate_v9_to_v10,  # Phase 27 #11 (Plan 27-09): promote bare-int signal rows to dict
}


def _assert_migration_chain_contiguous() -> None:
  '''Phase 27 #12 — fail-fast on schema-migration chain gaps.

  Walks integer keys [2, STATE_SCHEMA_VERSION] in MIGRATIONS and raises
  RuntimeError listing every missing key. A future contributor who adds
  STATE_SCHEMA_VERSION = N+1 with a `_migrate_vN_to_vN+1` function but
  forgets to register it in the MIGRATIONS dict will hit this gate at
  module-load time AND at every load_state() entry — they get a clear
  message at the point load_state would otherwise silently corrupt
  state by skipping the missing migrator.

  Called at TWO sites (review-fix M1 — defensive AND behavioral):
    - module bottom (after MIGRATIONS dict is defined): fails at import
    - load_state() entry: fails on every load even if module-load was
      somehow bypassed (e.g., partial reload, importlib hackery)
  '''
  if STATE_SCHEMA_VERSION < 1:
    raise RuntimeError(
      f'STATE_SCHEMA_VERSION must be >= 1, got {STATE_SCHEMA_VERSION}'
    )
  missing = [
    v for v in range(2, STATE_SCHEMA_VERSION + 1)
    if v not in MIGRATIONS
  ]
  if missing:
    raise RuntimeError(
      f'MIGRATIONS chain has gaps: missing keys {missing} '
      f'(STATE_SCHEMA_VERSION={STATE_SCHEMA_VERSION})'
    )


# Defensive guard: fails at import-time if the in-tree chain has a gap.
_assert_migration_chain_contiguous()


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

# =========================================================================
# Private helpers
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

  Durability sequence (D-17 ordering — corrected from RESEARCH.md §Pattern 1):
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
    - INTRA-PROCESS REENTRANCY (Rule 1 fix vs original RESEARCH §Pattern 9
      which mistakenly claimed reentrancy across DIFFERENT fds): on POSIX,
      flock locks the open-file-description, NOT the inode/path. Two fds in
      the SAME process to the SAME file do NOT share lock ownership, and a
      second LOCK_EX acquire blocks forever waiting for the first to release.
      The mutate_state -> save_state -> _atomic_write call chain WOULD
      deadlock here. Solution: mutate_state holds its own outer flock and
      calls _atomic_write_unlocked directly via _save_state_unlocked,
      bypassing this re-acquisition. Cross-process safety preserved
      (different processes -> different open-file-descriptions -> independent
      lock ownership semantics still serialize correctly).
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

def reset_state(initial_account=INITIAL_ACCOUNT) -> dict:
  '''STATE-07 / D-01 / D-03 / Phase 10 BUG-01 D-02: fresh state,
  account + initial_account both equal to `initial_account` (default
  INITIAL_ACCOUNT from system_params).

  Phase 10 D-02 closes BUG-01 at the module boundary: both
  `state['account']` and `state['initial_account']` are set from the
  same source-of-truth argument, so no caller can create a state where
  they differ. Defense-in-depth alongside main.py::_handle_reset D-01
  call-site fix.

  Each call returns a NEW dict (no shared mutable references) so that
  mutating one returned state doesn't bleed into a future reset.
  '''
  # Phase 27 #1: route initial_account through Decimal-quantize so a
  # Decimal-typed caller (truth #4 round-trip path) doesn't leak a raw
  # Decimal into the float-typed in-memory state. Floats stay floats.
  ia_float = float(_Decimal(str(initial_account)).quantize(
    AUD_QUANTIZE, rounding=AUD_ROUND,
  ))
  return {
    'schema_version': STATE_SCHEMA_VERSION,
    'account': ia_float,                      # D-02: from arg
    'last_run': None,
    'positions': {                            # D-01: None = inactive
      'SPI200': None,
      'AUDUSD': None,
    },
    'signals': {                              # D-03: FLAT init (Phase 27 #11
                                              # Plan 27-09: dict shape only —
                                              # bare-int back-compat removed
                                              # per Phase 26 DEBT.md R5)
      'SPI200': {'signal': 0, 'strategy_version': STRATEGY_VERSION},
      'AUDUSD': {'signal': 0, 'strategy_version': STRATEGY_VERSION},
    },
    'trade_log': [],
    'equity_history': [],
    'warnings': [],
    # Phase 8 (v2 schema): CONF-01 + CONF-02 top-level keys emitted on
    # fresh reset so corruption-recovery path + initial setup produce a
    # state that passes _validate_loaded_state under schema v2.
    'initial_account': ia_float,  # D-02: from arg
    'contracts': {
      'SPI200': _DEFAULT_SPI_LABEL,
      'AUDUSD': _DEFAULT_AUDUSD_LABEL,
    },
    'markets': _default_market_registry(),
    'strategy_settings': _default_strategy_settings(),
  }

def load_state(path: Path = Path(STATE_FILE), now=None, _under_lock: bool = False) -> dict:
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

  Phase 14 D-13 _under_lock parameter (PRIVATE — underscore-prefixed):
    Set to True ONLY by mutate_state, which already holds fcntl.LOCK_EX
    on `path`. When True, the corruption-recovery save uses
    _save_state_unlocked (no second lock acquire) to avoid the intra-
    process flock-on-different-fd deadlock.
  '''
  # Phase 27 #12: re-check the migration chain at every load_state entry.
  # Module-load already runs this once; running it again here is cheap and
  # catches any partial-reload / importlib-hackery scenario where a
  # contributor mutates MIGRATIONS or STATE_SCHEMA_VERSION without
  # re-importing. Fires BEFORE the migration walk would silently skip a
  # missing key.
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
    backup_name = _backup_corrupt(path, now)
    state = reset_state()
    state = append_warning(
      state, 'state_manager',
      f'recovered from corruption; backup at {backup_name}',
      now=now,
    )
    if _under_lock:
      _save_state_unlocked(state, path=path)
    else:
      save_state(state, path=path)
    return state
  # Happy path: migrate, then D-18 validate, then return
  state = _migrate(state)
  if 'markets' not in state or 'strategy_settings' not in state:
    state = _migrate_v7_to_v8(state)
  _validate_loaded_state(state)           # D-18: raises ValueError on missing keys
  # Phase 27 #6: read-path UTC-coercion shim — legacy naive ISO datetimes
  # in equity_history emit DeprecationWarning rather than failing the load.
  state = _coerce_legacy_naive_iso(state)
  # D-14 (Phase 8): materialise runtime-only _resolved_contracts from
  # tier labels. Underscore prefix = excluded from save_state (below).
  # KeyError propagates if a label in state['contracts'] is absent from
  # system_params.*_CONTRACTS — caller should repair via --reset.
  state['_resolved_contracts'] = {
    'SPI200':  SPI_CONTRACTS[state['contracts']['SPI200']],
    'AUDUSD':  AUDUSD_CONTRACTS[state['contracts']['AUDUSD']],
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
  # Phase 27 #1: route money values through Decimal-quantize-HALF_UP at save
  # time so disk format is canonical AUD-cent precision. Without this,
  # repeated float arithmetic + json round-trip can accumulate ULP drift.
  # _decimal_default is the encoder hook for any Decimal values that survive
  # to json.dumps (sizing_engine / pnl_engine results assigned directly into
  # state without prior quantize).
  persisted = _migrate_v8_to_v9(persisted)
  data = json.dumps(persisted, sort_keys=True, indent=2, allow_nan=False,
                    default=_decimal_default)
  _atomic_write(data, path)


def _save_state_unlocked(state: dict, path: Path) -> None:
  '''Same as save_state but uses _atomic_write_unlocked — caller MUST already
  hold fcntl.LOCK_EX on `path`. Used exclusively by mutate_state to avoid the
  intra-process flock-on-different-fd deadlock (see _atomic_write docstring).

  D-14 underscore-key filter applies identically; allow_nan=False preserved.
  Phase 27 #1: same Decimal-quantize-HALF_UP coercion + _decimal_default
  encoder as save_state.
  '''
  persisted = {k: v for k, v in state.items() if not k.startswith('_')}
  persisted = _migrate_v8_to_v9(persisted)
  data = json.dumps(persisted, sort_keys=True, indent=2, allow_nan=False,
                    default=_decimal_default)
  _atomic_write_unlocked(data, path)


def mutate_state(
  mutator: Callable[[dict], None],
  path: Path = Path(STATE_FILE),
) -> dict:
  '''Phase 14 D-13 + REVIEWS HIGH #1: lock around the full READ-MODIFY-WRITE.

  Provides the load -> mutate -> save critical section as a single atomic
  unit for any caller (web POST handlers, daily loop). Without this wrapper,
  fcntl on save_state alone admits stale-read lost updates: two writers can
  both load the same pre-mutation snapshot, both acquire+release the save
  lock, second clobbers first.

  Contract:
    - mutator receives a freshly loaded state dict (post-migration).
    - mutator MUTATES the dict in place; return value ignored.
    - The dict is then saved exactly once via _save_state_unlocked
      (REUSES the lock acquired here — see _atomic_write docstring for
      why the inner save_state path can NOT re-acquire the same lock
      from a different fd in the same process without deadlocking).
    - Cross-process coordination via fcntl.LOCK_EX on the destination file.

  Usage:
    def _bump_account(state):
      state['account'] += 100.0
    mutate_state(_bump_account)

  Returns the post-mutation state dict (after save).
  '''
  fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
  try:
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
      state = load_state(path=path, _under_lock=True)
      mutator(state)
      _save_state_unlocked(state, path=path)
      return state
    finally:
      fcntl.flock(fd, fcntl.LOCK_UN)
  finally:
    os.close(fd)

def append_warning(state: dict, source: str, message: str, now=None) -> dict:
  '''D-09 / D-10 / D-11: append {date, source, message}; FIFO trim to MAX_WARNINGS.

  Date format: ISO YYYY-MM-DD in AWST (Australia/Perth) per CLAUDE.md
  "Times always AWST in user-facing output" (RESEARCH §Open Question 3 / A1).

  State_manager is the SOLE writer to state['warnings'] (D-10). All other
  subsystems must call this helper rather than directly appending.

  `now` defaults to datetime.now(timezone.utc); tests inject a fixed UTC
  datetime for determinism without pytest-freezer.

  MAX_WARNINGS rationale (B-5 reviews-revision pass; tightened in
  Phase 27 #16 review-fix agreed-4 from prior 100 baseline):
    MAX_WARNINGS = 50 is intentionally conservative for v1's daily cadence
    (~7 weeks of warnings at 1/day average). A bad-day loop generating
    25+ warnings in one run fills half the bound. Chronic high-warning
    regimes (e.g., a bug emitting hundreds per day) should bump
    MAX_WARNINGS in system_params.py rather than expanding the contract
    here. The FIFO drop-oldest discipline ensures the bound is
    best-effort history — operators see the most recent 50 events, which
    is the actionable window for a daily-cadence system.
  '''
  if now is None:
    now = datetime.now(UTC)
  # Phase 27 #6 fail-closed: caller-provided naive datetimes raise here
  # BEFORE any FIFO mutation, so the write path is rejected pre-mutation.
  _assert_tz_aware(now, context='append_warning')
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


def clear_warnings_by_source(state: dict, source: str) -> dict:
  '''Phase 15 D-02: filter out warnings whose `source` key matches the
  argument. Pure dict operation — no I/O. Caller wraps in mutate_state
  for persistence atomicity. Returns the same state dict for chaining.

  Preserves D-10 sole-writer invariant — state_manager is the ONLY
  module that mutates state['warnings']; notifier reads but never writes.

  Use case (Phase 15 SENTINEL-01..03): drift warnings lifecycle —
  clear_warnings_by_source(state, 'drift') then re-append fresh events
  from sizing_engine.detect_drift. Surgical, leaves corruption/stale/
  sizing_engine warnings intact.

  NOTE: This is DIFFERENT from clear_warnings(state) — that one wipes
  ALL warnings (used post-email-dispatch). Pitfall 8 in 15-RESEARCH.md.
  '''
  state['warnings'] = [
    w for w in state.get('warnings', [])
    if w.get('source') != source
  ]
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
  _validate_trade(trade, allowed_instruments=set(state.get('positions', {}).keys()))
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
