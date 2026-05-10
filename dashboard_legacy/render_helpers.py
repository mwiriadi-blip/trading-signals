"""dashboard_legacy.render_helpers — formatters, stats wrappers, display-math, module constants, resolve helpers.

Extracted from dashboard.py (Plan 27-14). Pure thin wrappers around dashboard_renderer.* +
module-level lookup dicts that the rest of dashboard_legacy/* (and dashboard.py shim) re-export.

Hex-boundary preserved (CLAUDE.md): stdlib + pytz + dashboard_renderer + system_params only.
No imports from signal_engine, sizing_engine, data_fetcher, notifier, main, numpy, pandas,
yfinance, or requests.
"""
import html  # noqa: F401 — used by callers via re-export at dashboard.py shim
import logging
import math  # noqa: F401 — used by callers via re-export
from datetime import datetime  # noqa: F401 — type-hint surface for callers

from dashboard_renderer import formatters as dr_formatters
from dashboard_renderer import stats as dr_stats
from dashboard_renderer.assets import _INLINE_CSS  # noqa: F401 — re-export (shim consumers)
from dashboard_renderer.assets import _TRACE_TOGGLE_JS  # noqa: F401 — re-export
from system_params import (
    _COLOR_FLAT,
    _COLOR_LONG,
    _COLOR_SHORT,
    DEFAULT_MARKETS,
    DEFAULT_STRATEGY_SETTINGS,
    FALLBACK_CONTRACT_SPECS,
    TRAIL_MULT_LONG,  # noqa: F401 — re-exported for positions_section.py callers
    TRAIL_MULT_SHORT,  # noqa: F401 — re-exported for positions_section.py callers
)

# Plan 27-14: use the 'dashboard' logger name (not __name__) so journalctl
# tags + test caplog filters on logger='dashboard' continue to capture
# these emits post-split. The pre-split monolith logged under 'dashboard';
# preserve that name for tools that grep journalctl by [Dashboard] tag.
logger = logging.getLogger('dashboard')


# =========================================================================
# Display-name + contract-spec dicts — extracted from dashboard.py:160-170
# =========================================================================

_INSTRUMENT_DISPLAY_NAMES = {
  'SPI200': 'SPI 200',
  'AUDUSD': 'AUD / USD',
}

# Phase 8 IN-05: _CONTRACT_SPECS is a re-export of system_params.FALLBACK_CONTRACT_SPECS.
_CONTRACT_SPECS = FALLBACK_CONTRACT_SPECS


def _market_registry(state: dict | None = None) -> dict:
  markets = (state or {}).get('markets')
  if not isinstance(markets, dict):
    return {key: dict(value) for key, value in DEFAULT_MARKETS.items()}
  merged = {key: dict(value) for key, value in DEFAULT_MARKETS.items()}
  for key, value in markets.items():
    if isinstance(value, dict):
      merged[key] = {**merged.get(key, {}), **value}
  return dict(sorted(
    merged.items(),
    key=lambda item: (item[1].get('sort_order', 999), item[0]),
  ))


def _enabled_market_registry(state: dict | None = None) -> dict:
  return {
    key: market for key, market in _market_registry(state).items()
    if market.get('enabled', True)
  }


def _display_names(state: dict | None = None) -> dict[str, str]:
  return {
    key: str(market.get('display_name') or key)
    for key, market in _enabled_market_registry(state).items()
  }


def _strategy_settings_for(state: dict, market_id: str) -> dict:
  settings = state.get('strategy_settings', {}).get(market_id, {})
  if not isinstance(settings, dict):
    settings = {}
  return {**DEFAULT_STRATEGY_SETTINGS, **settings}

def _fmt_em_dash() -> str:
  '''UI-SPEC §Format Helper Contracts: single call site for the em-dash empty-value token.'''
  return dr_formatters.fmt_em_dash()


def _fmt_currency(value: float) -> str:
  '''UI-SPEC §Format Helper Contracts: $1,234.56 / -$567.89 / $0.00.'''
  return dr_formatters.fmt_currency(value)


def _fmt_percent_signed(fraction: float) -> str:
  '''UI-SPEC §Format Helper Contracts: +5.3% / -12.5% / +0.0%.'''
  return dr_formatters.fmt_percent_signed(fraction)


def _fmt_percent_unsigned(fraction: float) -> str:
  '''UI-SPEC §Format Helper Contracts: 58.3% / 12.5%. Input is a fraction.'''
  return dr_formatters.fmt_percent_unsigned(fraction)


def _fmt_pnl_with_colour(value: float) -> str:
  '''UI-SPEC §Format Helper Contracts + CONTEXT D-16: P&L span coloured by sign.'''
  return dr_formatters.fmt_pnl_with_colour(value)


def _fmt_last_updated(now: datetime) -> str:
  '''UI-SPEC §Format Helper Contracts + DASH-08: YYYY-MM-DD HH:MM AWST.'''
  return dr_formatters.fmt_last_updated(now)


# =========================================================================
# Phase 17 D-05 + D-06: indicator format helper (pure; math only)
# =========================================================================

def _format_indicator_value(
  value: float,
  seed_required: int,
  bars_available: int,
) -> str:
  '''Phase 17 D-05 + D-06: format a single indicator scalar for display.'''
  return dr_formatters.format_indicator_value(value, seed_required, bars_available)

def _compute_sharpe(state: dict) -> str:
  '''CONTEXT D-07: daily log-returns, rf=0, annualised × √252.'''
  return dr_stats.compute_sharpe(state, em_dash=_fmt_em_dash())


def _compute_max_drawdown(state: dict) -> str:
  '''CONTEXT D-08: rolling peak-to-trough %. Always <= 0.'''
  return dr_stats.compute_max_drawdown(state, em_dash=_fmt_em_dash())


def _compute_win_rate(state: dict) -> str:
  '''CONTEXT D-09: closed trades with gross_pnl > 0.'''
  return dr_stats.compute_win_rate(state, em_dash=_fmt_em_dash())


def _compute_total_return(state: dict) -> str:
  '''D-16 (Phase 8): use state["initial_account"] as the baseline.'''
  return dr_stats.compute_total_return(state)


def _compute_aggregate_stats(paper_trades=None, signals=None) -> dict:
  '''Phase 19 D-06 — compute 5-key aggregate stats for the sticky stats bar.

  Returns dict with keys: realised, unrealised, wins, losses, win_rate.
  Mutable-default avoided (planner trap): use None sentinels.

  pnl_engine is LOCAL-imported (mirrors sizing_engine convention — Phase 11 C-2
  + dashboard hex symmetry). dashboard.py does NOT import pnl_engine at module
  top per hex-boundary preservation.

  win_rate: wins / (wins + losses) * 100; '—' when denominator is 0.
  Zero realised_pnl rows are excluded from wins AND losses (CONTEXT D-06).
  Open rows with last_close=None or NaN skip unrealised contribution.
  '''
  return dr_stats.compute_aggregate_stats(paper_trades=paper_trades, signals=signals)

def _compute_trail_stop_display(position: dict, settings: dict | None = None) -> float:
  '''UI-SPEC §Positions table Trail Stop formula. Anchors on position['atr_entry']
  (NOT today's ATR — matches sizing_engine D-15 semantics).

  LONG: peak_price - TRAIL_MULT_LONG * atr_entry (fallback: entry_price if peak_price None)
  SHORT: trough_price + TRAIL_MULT_SHORT * atr_entry (fallback: entry_price if trough_price None)

  Phase 14 D-09 + UI-SPEC §Decision 6: manual_stop precedence — when operator
  has set a stop via /trades/modify (position['manual_stop'] is not None),
  return that value directly. Mirrors sizing_engine.get_trailing_stop precedence
  (CLAUDE.md hex-lite lockstep). NaN guard on atr_entry runs FIRST so the
  parity test against sizing_engine.get_trailing_stop holds bit-identically
  for the NaN-pass-through case (B-1).

  Pitfall 5: position.get('manual_stop') so pre-migration position dicts
  (no key) silently fall through to computed.
  '''
  return dr_stats.compute_trail_stop_display(position, settings=settings)


def _compute_unrealised_pnl_display(
  position: dict, state_key: str, current_close: float | None,
  state: dict | None = None,
) -> float | None:
  '''UI-SPEC §Positions table Unrealised P&L formula. Inline re-implementation
  of sizing_engine.compute_unrealised_pnl per CONTEXT D-01 hex fence. Returns
  None when current_close is None (caller renders em-dash).

  Per CLAUDE.md §Operator Decisions / CONTEXT D-13: opening-half cost is
  deducted here (matches sizing_engine.compute_unrealised_pnl exactly —
  TestStatsMath::test_unrealised_pnl_matches_sizing_engine locks parity).

  Phase 8 WR-01 fix: prefer the operator-selected tier values from
  state['_resolved_contracts'][state_key]; fall back to the module-level
  _CONTRACT_SPECS defaults when state is None or lacks _resolved_contracts
  (pre-Phase-8 state shape or non-load_state callers like unit tests that
  build state dicts directly). Mirrors D-17 resolved-tier flow.
  '''
  if current_close is not None:
    has_resolved = state is not None and state.get('_resolved_contracts', {}).get(state_key) is not None
    if not has_resolved:
      logger.debug(
        '[Dashboard] _resolved_contracts missing for %s; falling back to '
        'module-level _CONTRACT_SPECS default tier', state_key,
      )
  return dr_stats.compute_unrealised_pnl_display(
    position=position,
    state_key=state_key,
    current_close=current_close,
    contract_specs=_CONTRACT_SPECS,
    state=state,
  )

# Phase 22 D-06: dashboard fallback when no signal row carries strategy_version.
_DEFAULT_STRATEGY_VERSION = 'v1.0.0'

# =========================================================================
# Phase 17 D-13: trace panel constants (hex-boundary preserved — no imports
# from signal_engine, system_params, state_manager, etc.)
# =========================================================================

# D-13: indicator formula text catalogue (presentation-only, plain text).
# Lookup keys match state.signals[<inst>].indicator_scalars keys exactly.
# Inlined here per D-10: formula text is presentation, not logic; the
# engine's behaviour is pinned by tests/test_signal_engine.py independently.
_TRACE_FORMULAS: dict[str, str] = {
  'tr': 'TR = max(High - Low, |High - prev Close|, |Low - prev Close|)',
  'atr': 'ATR(14) = Wilder-smooth(TR, 14) - initial seed = SMA(TR, 14)',
  'plus_di': '+DI(20) = 100 * Wilder-smooth(+DM, 20) / ATR(20)',
  'minus_di': '-DI(20) = 100 * Wilder-smooth(-DM, 20) / ATR(20)',
  'adx': 'ADX(20) = 100 * Wilder-smooth(|+DI - -DI| / (+DI + -DI), 20)',
  'mom1': 'Mom1 = (Close_t - Close_{t-1}) / Close_{t-1}',
  'mom3': 'Mom3 = (Close_t - Close_{t-3}) / Close_{t-3}',
  'mom12': 'Mom12 = (Close_t - Close_{t-12}) / Close_{t-12}',
  'rvol': 'RVol(20) = Volume_t / SMA(Volume, 20)',
}

# D-06: seed window length per indicator. Hardcoded per D-10 (NOT imported
# from signal_engine — if the engine constants drift, the dashboard golden
# test surfaces the mismatch rather than silently rendering stale text).
_SEED_LENGTHS: dict[str, int] = {
  'tr': 1, 'atr': 14, 'plus_di': 20, 'minus_di': 20,
  'adx': 20, 'mom1': 2, 'mom3': 4, 'mom12': 13, 'rvol': 20,
}

# D-04: instrument keys whose <details open> we honour at the route-layer
# cookie read. Mirrors state.signals keys (SPI200, AUDUSD).
_VALID_TRACE_INSTRUMENT_KEYS: frozenset = frozenset({'SPI200', 'AUDUSD'})

# D-17 (PATTERNS.md §Pattern To Design From Scratch): attribute-level
# placeholder substitution. dashboard.py emits these literal strings inside
# each <details data-instrument="..."> opening tag at write time.
# web/routes/dashboard.py substitutes them per-request with ' open' or ''
# based on the tsi_trace_open cookie (allowlist-filtered).
# Note: attribute-level vs Phase 16.1's block-level placeholders — new design.
#
# Phase 29 Plan 12: replaced static 2-entry dict with a defaultdict-style
# callable so ALL market IDs (including Phase 25+ dynamically-added markets)
# emit the correct {{TRACE_OPEN_<KEY>}} placeholder. The static dict form is
# kept as a legacy fallback for any out-of-tree callers that accessed the dict
# directly by key; _TRACE_OPEN_PLACEHOLDER.get(key, '') is the canonical call
# site — callers that do .get() still work; new markets now produce a
# placeholder instead of an empty string.
class _TraceOpenPlaceholderMap:
  '''Returns {{TRACE_OPEN_<KEY>}} for any valid instrument key; '' for invalid.

  Mimics dict .get(key, default) so existing call sites are unchanged.
  Invalid key = does not satisfy ^[A-Z0-9_]{2,20}$ (matches _MARKET_ID_RE).
  '''
  import re as _re
  _RE = _re.compile(r'^[A-Z0-9_]{2,20}$')

  def get(self, key: str, default: str = '') -> str:  # noqa: ANN001
    if not self._RE.fullmatch(key or ''):
      return default
    return f'{{{{TRACE_OPEN_{key}}}}}'


_TRACE_OPEN_PLACEHOLDER = _TraceOpenPlaceholderMap()

# D-03 + D-12: _TRACE_TOGGLE_JS re-exported from assets.py (Phase 25).
from dashboard_renderer.assets import _TRACE_TOGGLE_JS  # noqa: F811

def _resolve_strategy_version(state: dict) -> str:
  '''Phase 22: extract the active strategy version from state.signals.

  Reads strategy_version off each dict-shaped signal row, picks the
  lexicographic max (str) when instruments disagree (transient migration
  window), defaults to 'v1.0.0' if no row carries the field. Emits a
  [State] WARN log for each dict-shaped row that lacks the field —
  surfaces silent migration drift in journalctl rather than rendering a
  spurious default.

  Hex-boundary (LEARNINGS 2026-04-27): dashboard.py does NOT import
  system_params.STRATEGY_VERSION. The version arrives via the state dict
  (which the orchestrator at main.py:1280 has already tagged on the most
  recent run). This preserves the rule "pass primitives, not module
  references, into render layer".

  Tie-break for cross-version states (e.g. SPI200=v1.1.0, AUDUSD=v1.2.0):
  lexicographic max of the strings starting with 'v'. For semver-formatted
  strings of the same MAJOR.MINOR.PATCH digit-width this matches numerical
  max. Cross-MAJOR comparisons are approximate; in practice instruments
  converge within one daily run after a bump.
  '''
  signals = state.get('signals', {})
  found: list[str] = []
  for sig in signals.values():
    if isinstance(sig, dict):
      if 'strategy_version' in sig:
        found.append(sig['strategy_version'])
      else:
        logger.warning(
          '[State] WARN signal row missing strategy_version field — '
          'defaulting to v1.0.0',
        )
  if not found:
    return _DEFAULT_STRATEGY_VERSION
  return max(found, key=str)


_SIGNAL_LABEL = {1: 'LONG', -1: 'SHORT', 0: 'FLAT'}
_SIGNAL_COLOUR = {1: _COLOR_LONG, -1: _COLOR_SHORT, 0: _COLOR_FLAT}


def _resolve_trace_open_keys(
  state: dict,
  trace_open_keys: list,
) -> set:
  '''Phase 17 D-04: which per-instrument <details> render with the `open`
  attribute. Caller (web/routes/dashboard.py) computes the list from the
  tsi_trace_open cookie; this helper applies a defensive allowlist
  intersection against _VALID_TRACE_INSTRUMENT_KEYS AND against the keys
  actually present in state.signals.

  Hex-boundary preserved: reads only state-dict primitives + a list of
  strings; no module-attribute reads, no I/O, no auth.
  '''
  present_keys = set(state.get('signals', {}).keys())
  return {
    k for k in trace_open_keys
    if k in _VALID_TRACE_INSTRUMENT_KEYS and k in present_keys
  }

# Exit-reason display mapping (UI-SPEC §Closed trades table §Reason column).
# Unknown / unmapped values fall through raw (html.escape applied at render leaf).
_EXIT_REASON_DISPLAY = {
  'flat_signal': 'Signal flat',
  'signal_reversal': 'Reversal',
  'stop_hit': 'Stop hit',
  'adx_exit': 'ADX drop',
}
