'''System-wide trading parameters — shared constants and Position TypedDict.

All policy constants for Phase 1 indicator logic and Phase 2 sizing/exit/pyramid
logic live here. Pure module: no I/O, no network, no clock reads.

Architecture (hexagonal-lite, CLAUDE.md): shared by signal_engine.py (Phase 1
indicator periods + vote thresholds), sizing_engine.py (Phase 2 sizing/exit
constants), and state_manager.py (Phase 3 I/O hex). Must NOT import notifier,
dashboard, main, requests, datetime, os, or any I/O/network module.

D-01: Phase 1 policy constants migrated from signal_engine.py (ADX_GATE,
MOM_THRESHOLD, periods). LONG/SHORT/FLAT signal encoding stays in signal_engine.py.
D-08: Position TypedDict lives here so Phase 3 state.json round-trips directly.
D-11: SPI mini $5/pt, $6 AUD RT (operator confirmed at /gsd-discuss-phase 2).
D-XX (Phase 3): INITIAL_ACCOUNT, MAX_WARNINGS, STATE_SCHEMA_VERSION, STATE_FILE added.
'''
import re
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal, TypedDict

# =========================================================================
# Strategy version (Phase 22 D-01..D-03)
# =========================================================================
# Bump on signal-logic change ONLY (Mom periods, ADX gate cutoff, RVol
# period, sizing weights, vote rule). Do NOT bump on UI / infra / email /
# auth / test / docs changes. Style: MAJOR.MINOR.PATCH semver, 'v' prefix
# to match git tags. Operator can grep `STRATEGY_VERSION = 'v` to find
# every bump in git history. See docs/STRATEGY-CHANGELOG.md for entries.
STRATEGY_VERSION: str = 'v1.2.0'

# =========================================================================
# Phase 27 #5: canonical outbound HTTP timeout (single source of truth)
# =========================================================================
# HTTP_TIMEOUT_S applies to EVERY outbound HTTP call in production code
# (Resend POST, yfinance session, future adapters). Without an explicit
# timeout, requests blocks indefinitely on a stuck socket — the daily
# run hangs and the crash-email path never fires (T-27-02-01 DoS).
#
# Read-phase budget: 30s. Connect-phase is split per call site — notifier
# uses (5, HTTP_TIMEOUT_S) so DNS / TCP handshake gets a tight 5s window.
#
# Single source: do NOT introduce a second timeout constant. AST regression
# in tests/test_http_timeouts.py enforces (T-27-02-02 drift mitigation).
HTTP_TIMEOUT_S: int = 30

# =========================================================================
# Phase 27 #13: secret redaction helper (single source of truth)
# =========================================================================
# Any secret variable (RESEND_API_KEY, TOTP secret, session secret,
# magic-link token) bound for a log line, exception message, or echoed
# response body MUST flow through redact_secret() FIRST. Returns a 6-char
# prefix + ellipsis so operator triage works ('was that THIS key?')
# without exposing the full token to journalctl / log archives.
#
# T-27-03-01 (RESEND_API_KEY in journalctl) + T-27-03-02 (TOTP secret in
# auth_store logs) — both mitigated. Regression: tests/test_secret_redaction.py.
#
# Hex-boundary: stdlib-only — safe to live in system_params (FORBIDDEN_MODULES_STDLIB_ONLY).


def redact_secret(s: str | None) -> str:
  '''Redact any secret to first 6 chars + ellipsis.

  Returns:
    '[empty]' if s is None or '' (empty string).
    '[short]' if len(s) <= 6 (too short to safely show 6 chars).
    s[:6] + '...' otherwise.
  '''
  if not s:
    return '[empty]'
  if len(s) <= 6:
    return '[short]'
  return s[:6] + '...'

# =========================================================================
# Phase 27 #1: Decimal money-math precision boundary (review-fix agreed-7)
# =========================================================================
# Money arithmetic (P&L, account balance, equity history, paper-trade
# realised/unrealised) flows through Python's stdlib Decimal at the
# pnl_engine + state_manager persistence boundary so AUD-cent precision
# survives repeated save/load cycles. Indicator math (ATR/ADX/Mom/RVol on
# numpy/pandas) STAYS float64 — the hex boundary is preserved.
#
# AUD_QUANTIZE pins precision to 2dp (cents). AUD_ROUND = ROUND_HALF_UP
# (NOT banker's rounding ROUND_HALF_EVEN) — chosen for trading PnL display
# intuition: $2.005 rounds to $2.01.
#
# T-27-01-01 (tampering — money values silently drift via float ULP
# accumulation across saves): mitigated by quantize-on-write in state_manager
# + Decimal-typed pnl_engine returns + round-trip regression test.
# T-27-01-03 (DoS — dashboard JSON crashes on raw Decimal): mitigated by
# _decimal_default encoder hook below; every dashboard json.dumps uses it.
#
# Hex-boundary: stdlib `decimal` is safe under FORBIDDEN_MODULES_STDLIB_ONLY.

AUD_QUANTIZE: Decimal = Decimal('0.01')
AUD_ROUND = ROUND_HALF_UP


def to_aud(x) -> Decimal:
  '''Coerce x (int/float/str/Decimal) to Decimal quantized to AUD cents.

  Routes through Decimal(str(x)) FIRST so float-binary representation noise
  (e.g., 0.1 + 0.2 == 0.30000000000000004) is canonicalised to its decimal
  string form before quantization. Quantize uses HALF_UP rounding.

  Examples:
    to_aud(1234.56)    -> Decimal('1234.56')
    to_aud('2.005')    -> Decimal('2.01')   (HALF_UP, not HALF_EVEN)
    to_aud(Decimal(0)) -> Decimal('0.00')
  '''
  return Decimal(str(x)).quantize(AUD_QUANTIZE, rounding=AUD_ROUND)


def _decimal_default(o):
  '''json.dumps default= hook: serialize Decimal as canonical string.

  Used by state_manager.save_state and dashboard JSON paths so raw Decimal
  values flowing through state['account'] / equity rows / paper_trades P&L
  fields don't raise `TypeError: Object of type Decimal is not JSON
  serializable`. String form preserves cent precision exactly across the
  wire (avoids float-binary truncation).

  Non-Decimal objects fall through to the default TypeError so genuine
  serialization bugs still surface.
  '''
  if isinstance(o, Decimal):
    return str(o)
  raise TypeError(
    f'Object of type {type(o).__name__} is not JSON serializable'
  )

# =========================================================================
# Phase 27 #8: instrument-id syntax + membership (review-fix agreed-8)
# =========================================================================
# Two-layer policy for "is this a valid market id?":
#
#   Layer 1 — INSTRUMENT_ID_RE (^[A-Z0-9_]{2,20}$): syntax validation.
#     Rejects lowercase, special chars, unbounded length, empty inputs.
#     Cannot reject 'SPI200X' — that string IS syntactically valid; the
#     regex is generic by design so we don't have to edit the pattern
#     every time a market is added.
#
#   Layer 2 — KNOWN_MARKET_IDS (frozenset): semantic membership.
#     Pins the actual supported markets. is_known_market(id) is the
#     public API for "should I let this id reach state['signals'][id]?".
#
# T-27-04-01 (tampering — `/markets/SPI200X/signals` triggers a state
# lookup with a too-loose regex): mitigated by both layers together.
# Pydantic Field(pattern=r'^[A-Z0-9_]{2,20}$') on the request side
# enforces Layer 1 at parse time; route handlers + state lookups gate
# on is_known_market for Layer 2.
#
# Hex-boundary: stdlib re only — safe under FORBIDDEN_MODULES_STDLIB_ONLY.

INSTRUMENT_ID_RE: re.Pattern[str] = re.compile(r'^[A-Z0-9_]{2,20}$')

# Canonical default markets. Mirrors DEFAULT_MARKETS keys (below) but
# is owned separately so KNOWN_MARKET_IDS can be imported by adapter
# layers (web/routes, validators) without dragging the full registry.
# Operator-added markets via POST /markets are validated against
# state['markets'] at the adapter boundary; this set is the static
# fallback / route-time default.
KNOWN_MARKET_IDS: frozenset[str] = frozenset({'SPI200', 'AUDUSD'})


def is_known_market(market_id: object) -> bool:
  '''Two-layer check: syntactically valid id AND in KNOWN_MARKET_IDS.

  Returns False for non-string inputs, ids that fail INSTRUMENT_ID_RE,
  or ids that pass syntax but are not in the canonical default set.
  Never raises — defensive at the trust boundary. Operator-added
  markets must be validated against state['markets'] separately.

  Examples:
    is_known_market('SPI200')   -> True
    is_known_market('AUDUSD')   -> True
    is_known_market('SPI200X')  -> False  (passes regex, fails membership)
    is_known_market('spi200')   -> False  (fails regex)
    is_known_market(None)       -> False  (defensive)
  '''
  if not isinstance(market_id, str):
    return False
  if not INSTRUMENT_ID_RE.fullmatch(market_id):
    return False
  return market_id in KNOWN_MARKET_IDS

# =========================================================================
# Phase 1 constants — migrated from signal_engine.py (D-01)
# =========================================================================

# --- Indicator periods (locked) ---
ATR_PERIOD: int = 14
ADX_PERIOD: int = 20
MOM_PERIODS: tuple[int, int, int] = (21, 63, 252)
RVOL_PERIOD: int = 20
ANNUALISATION_FACTOR: int = 252

# --- Vote thresholds (SPEC.md §3) ---
ADX_GATE: float = 25.0          # entry gate; FLAT if ADX < ADX_GATE
MOM_THRESHOLD: float = 0.02     # |mom| > threshold counts as a vote

# =========================================================================
# Phase 2 constants — sizing, exits, pyramid (D-01, SPEC.md §5/7/8)
# =========================================================================

# --- Position sizing (SIZE-01..04) ---
RISK_PCT_LONG: float = 0.01      # 1.0% account risk per LONG entry
RISK_PCT_SHORT: float = 0.005    # 0.5% account risk per SHORT entry

# --- Trailing stop multipliers (EXIT-06/07, SIZE-02) ---
TRAIL_MULT_LONG: float = 3.0    # LONG stop = peak - 3 * atr_entry
TRAIL_MULT_SHORT: float = 2.0   # SHORT stop = trough + 2 * atr_entry

# --- Vol-scaling clip (SIZE-03) ---
VOL_SCALE_TARGET: float = 0.12
VOL_SCALE_MIN: float = 0.3
VOL_SCALE_MAX: float = 2.0

# --- Pyramid triggers (PYRA-01..04, D-12) ---
PYRAMID_TRIGGERS: tuple[float, float] = (1.0, 2.0)  # multiples of atr_entry
MAX_PYRAMID_LEVEL: int = 2       # cap at 3 total contracts (level 0=1, 1=2, 2=3)

# --- ADX exit gate (EXIT-05) ---
ADX_EXIT_GATE: float = 20.0     # close position if ADX drops below this

# =========================================================================
# Contract specs — D-11 (operator confirmed, overrides SPEC.md original)
# =========================================================================

# SPI 200 mini: $5/pt, $6 AUD RT (split $3 on open + $3 on close per D-13)
SPI_MULT: float = 5.0
SPI_COST_AUD: float = 6.0       # round-trip; half deducted on open, half on close

# AUD/USD: $10,000 notional, $5 AUD RT (split $2.50 on open + $2.50 on close)
AUDUSD_NOTIONAL: float = 10000.0
AUDUSD_COST_AUD: float = 5.0    # round-trip; half deducted on open, half on close

# =========================================================================
# Phase 8 constants — contract tier presets (D-11, CONF-02)
# =========================================================================
# Label vocabulary: instrument-prefixed for CLI self-documentation
# (--spi-contract spi-mini reads naturally vs generic 'mini'). Tier
# multiplier + cost values per Phase 2 D-11. Baseline spellings locked
# per Phase 8 CONTEXT.md D-11; operator divergence may extend this dict
# in a follow-up milestone without schema bump.

SPI_CONTRACTS: dict[str, dict[str, float]] = {
  'spi-mini':     {'multiplier': 5.0,  'cost_aud': 6.0},
  'spi-standard': {'multiplier': 25.0, 'cost_aud': 30.0},
  'spi-full':     {'multiplier': 50.0, 'cost_aud': 50.0},
}

AUDUSD_CONTRACTS: dict[str, dict[str, float]] = {
  'audusd-standard': {'multiplier': 10000.0, 'cost_aud': 5.0},
  'audusd-mini':     {'multiplier': 1000.0,  'cost_aud': 0.5},
}

# D-11: defaults used by _migrate v1→v2 when state.json has no 'contracts' key.
_DEFAULT_SPI_LABEL: str = 'spi-mini'
_DEFAULT_AUDUSD_LABEL: str = 'audusd-standard'

# Phase 8 IN-05: shared fallback (multiplier, cost_aud) tuples used by
# dashboard.py and the notifier package when state['_resolved_contracts'] is
# unavailable (pre-Phase-8 state shape or unit tests that build state dicts
# directly). Single source of truth — previously duplicated inline in both
# render modules. Values match the default SPI mini / AUD standard tiers
# (preserves pre-Phase-8 behavior when no tier has been selected).
FALLBACK_CONTRACT_SPECS: dict[str, tuple[float, float]] = {
  'SPI200': (SPI_MULT, SPI_COST_AUD),
  'AUDUSD': (AUDUSD_NOTIONAL, AUDUSD_COST_AUD),
}

# =========================================================================
# Phase 3 constants — state persistence (STATE-01, STATE-07, D-11)
# =========================================================================

INITIAL_ACCOUNT: float = 100_000.0  # starting account balance (STATE-07, reset_state)
MAX_WARNINGS: int = 50              # FIFO bound on state['warnings'] (D-11; Phase 27 #16 review-fix agreed-4: tightened from 100 to 50)
STATE_SCHEMA_VERSION: int = 10      # bump on each schema change (STATE-04); Phase 14 → v3 (manual_stop on Position; D-09); Phase 22 → v4 (strategy_version on signal rows; D-04); Phase 17 → v5 (ohlc_window + indicator_scalars on signal rows; D-08); Phase 19 → v6 (paper_trades[] top-level array; D-08); Phase 20 → v7 (last_alert_state on paper_trades[] rows; D-08); v8 markets + per-market strategy_settings; Phase 27 #1 → v9 quantize money fields via Decimal (AUD cents, HALF_UP); Phase 27 #11 (Plan 27-09) → v10 promote bare-int signal rows to dict (Phase 26 DEBT.md R5 — back-compat removal).
STATE_FILE: str = 'state.json'      # repo-root state file path (SPEC.md §FILE STRUCTURE)

# Phase 27 Plan 27-11 (review-fix agreed-5): second-line crash fallback.
# When notifier.send_crash_email's outbound dispatch fails (Resend down,
# network outage), the redacted crash payload is written here so the
# operator sees it on the next dashboard visit even if the email never
# reached them. Default sits next to STATE_FILE (NOT a separate working
# location). Operator can override at runtime via the LAST_CRASH_PATH
# env var — resolution lives in notifier._resolve_last_crash_path() so
# system_params stays stdlib-only (no os/pathlib import here, per
# FORBIDDEN_MODULES_STDLIB_ONLY hex constraint enforced in
# tests/test_signal_engine.py::TestDeterminism).
LAST_CRASH_FILE: str = 'last_crash.json'

# =========================================================================
# Phase 24 constants — market registry + per-market strategy settings
# =========================================================================

DEFAULT_MARKETS: dict[str, dict] = {
  'SPI200': {
    'display_name': 'SPI 200',
    'symbol': '^AXJO',
    'currency': 'AUD',
    'multiplier': SPI_MULT,
    'cost_aud': SPI_COST_AUD,
    'enabled': True,
    'sort_order': 10,
  },
  'AUDUSD': {
    'display_name': 'AUD / USD',
    'symbol': 'AUDUSD=X',
    'currency': 'AUD',
    'multiplier': AUDUSD_NOTIONAL,
    'cost_aud': AUDUSD_COST_AUD,
    'enabled': True,
    'sort_order': 20,
  },
}

DEFAULT_STRATEGY_SETTINGS: dict[str, float | int | bool | None] = {
  'adx_gate': ADX_GATE,
  'momentum_votes_required': 2,
  'trail_mult_long': TRAIL_MULT_LONG,
  'trail_mult_short': TRAIL_MULT_SHORT,
  'risk_pct_long': RISK_PCT_LONG,
  'risk_pct_short': RISK_PCT_SHORT,
  'one_contract_floor': False,
  'contract_cap': None,
  'direction_mode': 'both',
}

# =========================================================================
# Palette constants — Phase 5 + Phase 6 shared (D-02 retrofit)
# =========================================================================
# Originally defined in dashboard.py module-level; migrated here so
# the notifier package can import the same palette without cross-hex import (hex
# fence D-01). Underscore prefix preserves "shared-implementation-detail"
# semantics rather than "stable public API".

_COLOR_BG: str = '#0f1117'
_COLOR_SURFACE: str = '#161a24'
_COLOR_BORDER: str = '#252a36'
_COLOR_TEXT: str = '#e5e7eb'
_COLOR_TEXT_MUTED: str = '#cbd5e1'
_COLOR_TEXT_DIM: str = '#64748b'
_COLOR_LONG: str = '#22c55e'
_COLOR_SHORT: str = '#ef4444'
_COLOR_FLAT: str = '#eab308'

# =========================================================================
# Position TypedDict — D-08
# =========================================================================


class Position(TypedDict):
  '''Open position state. Round-trips directly to/from Phase 3 state.json.

  Fields:
    direction:     'LONG' or 'SHORT'
    entry_price:   Fill price at position open
    entry_date:    ISO YYYY-MM-DD of entry bar
    n_contracts:   Current contract count (may increase via pyramid)
    pyramid_level: 0 = initial, 1 = added once, 2 = added twice (cap, PYRA-04)
    peak_price:    Highest HIGH since entry for LONG; None for SHORT (D-08)
    trough_price:  Lowest LOW since entry for SHORT; None for LONG (D-08)
    atr_entry:     ATR at time of entry — used for stop distance + pyramid
                   thresholds (D-15: stop anchored to entry ATR, not today's)
    manual_stop:   Operator override for trailing stop. None = use the
                   computed peak/trough trailing stop (v1.0 default).
                   Set via /trades/modify endpoint (Phase 14 D-09).
  '''
  direction: Literal['LONG', 'SHORT']
  entry_price: float
  entry_date: str
  n_contracts: int
  pyramid_level: int
  peak_price: float | None       # LONG: highest HIGH since entry; None for SHORT
  trough_price: float | None     # SHORT: lowest LOW since entry; None for LONG
  atr_entry: float
  manual_stop: float | None      # Phase 14 D-09: operator override for trailing stop;
                                 # None = use computed peak/trough trailing stop (v1.0 default)


# =========================================================================
# Phase 7 constants — scheduler loop + weekday gate (D-01, D-03, D-07)
# =========================================================================

LOOP_SLEEP_S: int = 60                   # tick-budget between schedule.run_pending calls (D-01)
SCHEDULE_TIME_UTC: str = '00:00'         # 08:00 AWST = 00:00 UTC — passed to schedule.at() (D-07)
WEEKDAY_SKIP_THRESHOLD: int = 5          # weekday() >= 5 means Sat/Sun (stdlib contract; D-03)

# =========================================================================
# Phase 16.1 auth/TOTP constants (added 2026-04-29)
# =========================================================================
# F-04 / F-05: pyotp parameters and issuer label.
# D-11: tsi_session 12h TTL.
# Salts share the 'tsi-*-cookie' root for grep-discoverability (LEARNING 2026-04-27).

TOTP_ISSUER: str = 'Trading Signals'
TOTP_DIGITS: int = 6
TOTP_PERIOD: int = 30
TOTP_VALID_WINDOW: int = 1

TSI_SESSION_TTL_SECONDS: int = 43200  # 12 hours (D-11)
TSI_PENDING_TTL_SECONDS: int = 600    # 10 minutes
TSI_ENROLL_TTL_SECONDS: int = 600     # 10 minutes

TSI_SESSION_SALT: str = 'tsi-session-cookie'
TSI_PENDING_SALT: str = 'tsi-pending-cookie'
TSI_ENROLL_SALT: str = 'tsi-enroll-cookie'

# Phase 16.1 Plan 02 — trusted-device cookie config (E-05; 30 days).
TSI_TRUSTED_TTL_SECONDS = 2592000
TSI_TRUSTED_SALT = 'tsi-trusted-cookie'

# Phase 16.1 Plan 03 — magic-link reset (F-02 + F-08).
# Salts share the 'magic-link' root for grep-discoverability; the literal
# 'magic-link' string is also locked into web/routes/login.py and
# web/routes/reset.py — keep these aligned.
MAGIC_LINK_TTL_SECONDS = 3600          # 1 hour (F-02)
MAGIC_LINK_SALT = 'magic-link'         # F-02; unique vs tsi-*-cookie salts
RATE_LIMIT_LOGIN_PER_15M = 5           # F-08
RATE_LIMIT_FORGOT_PER_HOUR = 3         # F-08
RATE_LIMIT_RESET_PER_HOUR = 10         # F-08
RATE_LIMIT_MAGIC_LINKS_PER_24H = 3     # F-08 per-account

TOTP_ACCOUNT_DOMAIN: str = 'signals.mwiriadi.me'
AUTH_JSON_PATH: str = 'auth.json'
