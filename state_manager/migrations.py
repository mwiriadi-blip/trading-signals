'''state_manager.migrations — schema migration registry and orchestrator.

Owns all _migrate_vX_to_vY functions, the MIGRATIONS dict, the _migrate
orchestrator, and _assert_migration_chain_contiguous (called at module bottom
so it fires at import time — defensive fail-fast on chain gaps).

_read_signal_strategy_version lives in validation.py (not here) to keep
this file under 500 LOC (D-04 in CONTEXT.md).
'''
import logging
from decimal import Decimal as _Decimal

from system_params import (
  INITIAL_ACCOUNT,
  STATE_SCHEMA_VERSION,
  STRATEGY_VERSION,
  AUD_QUANTIZE,
  AUD_ROUND,
  AUDUSD_CONTRACTS,
  DEFAULT_MARKETS,
  DEFAULT_STRATEGY_SETTINGS,
  SPI_CONTRACTS,
  _DEFAULT_AUDUSD_LABEL,
  _DEFAULT_SPI_LABEL,
  default_settings_for_market,
)

logger = logging.getLogger(__name__)


# =========================================================================
# Default registry helpers (used by _migrate_v7_to_v8 and reset_state)
# =========================================================================

def _default_market_registry() -> dict:
  return {key: dict(value) for key, value in DEFAULT_MARKETS.items()}


def _default_strategy_settings(markets: dict | None = None) -> dict:
  source = markets if markets is not None else DEFAULT_MARKETS
  # Per-market lookup (v11): SPI200/AUDUSD ship with backtested optima; any
  # operator-added market falls back to the conservative DEFAULT_STRATEGY_SETTINGS
  # via default_settings_for_market.
  return {
    key: default_settings_for_market(key)
    for key in source
  }


# =========================================================================
# Money-quantize helper (used by _migrate_v8_to_v9)
# =========================================================================

def _quantize_aud(v) -> float:
  '''Phase 27 #1: route a money-shaped value through Decimal-quantize-HALF_UP
  and return as a float (state.json wire format stays JSON-numeric for
  backward compatibility with existing readers).

  None / NaN / inf flow through unchanged so non-money sentinels are
  preserved (e.g., realised_pnl=None for an open paper trade).

  Float→Decimal coercion goes via str(v) so float-binary repr noise
  ('1234.5600000000004') is stripped before quantize.
  '''
  import math
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


# =========================================================================
# Schema migration functions
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

  D-15 silent migration: no append_warning, no log.
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
  overwritten.

  D-15 silent migration: no append_warning, no log line.
  '''
  signals = s.get('signals', {})
  for sig in signals.values():
    if isinstance(sig, dict) and 'strategy_version' not in sig:
      sig['strategy_version'] = 'v1.1.0'
  return s


def _migrate_v4_to_v5(s: dict) -> dict:
  '''Phase 17 D-08 (v1.2): backfill empty ohlc_window + indicator_scalars
  on existing dict-shaped signal rows.

  Idempotent: rows that already carry a populated ohlc_window or
  indicator_scalars are NOT overwritten. Two independent 'field' not in sig
  guards so a partial-prior-state row still backfills the missing field
  per LEARNINGS 2026-04-27 idempotency rule.

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

  D-15 silent migration: no append_warning, no log line.
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
  D-15 silent migration: no append_warning, no log line.
  '''
  for row in s.get('paper_trades', []):
    if isinstance(row, dict) and 'last_alert_state' not in row:
      row['last_alert_state'] = None
  return s


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


def _migrate_v8_to_v9(s: dict) -> dict:
  '''Phase 27 #1: quantize all money-denominated state.json fields via
  Decimal(AUD_QUANTIZE, HALF_UP) so AUD-cent precision survives every
  save/load cycle (truth #4: round-trip preserves cents).

  Idempotent: quantizing an already-quantized value yields the same value.
  Defensive: only touches dict-shaped rows; missing fields are skipped.
  D-15 silent migration: no append_warning, no log line.
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

  Idempotent: dict-shaped rows pass through unchanged.
  Defensive: only touches int-shaped rows; missing/None values skipped.
  D-15 silent migration: no append_warning, no log line.
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


def _migrate_v10_to_v11(s: dict) -> dict:
  '''v11: backfill contract_type + financing_rate_annual_pct on every market
  registry entry. Pulls defaults from DEFAULT_MARKETS for known markets;
  operator-added markets get contract_type='cfd' and financing_rate_annual_pct=0.0
  as conservative starting values.

  Idempotent: existing contract_type / financing_rate_annual_pct values are
  preserved. D-15 silent migration: no append_warning, no log line.
  '''
  markets = s.get('markets')
  if not isinstance(markets, dict):
    return s
  out_markets = {}
  for key, value in markets.items():
    if not isinstance(value, dict):
      out_markets[key] = value
      continue
    entry = dict(value)
    if 'contract_type' not in entry:
      default_market = DEFAULT_MARKETS.get(key, {})
      entry['contract_type'] = str(default_market.get('contract_type', 'cfd'))
    if 'financing_rate_annual_pct' not in entry:
      default_market = DEFAULT_MARKETS.get(key, {})
      entry['financing_rate_annual_pct'] = float(
        default_market.get('financing_rate_annual_pct', 0.0),
      )
    out_markets[key] = entry
  out = dict(s)
  out['markets'] = out_markets
  return out


# =========================================================================
# Migration registry and orchestrator
# =========================================================================

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
  11: _migrate_v10_to_v11,  # v11: contract_type + financing_rate_annual_pct on markets
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


# Defensive guard: fails at import-time if the in-tree chain has a gap.
_assert_migration_chain_contiguous()
