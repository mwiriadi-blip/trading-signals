"""Phase 23 — backtest module constants.

Architecture: pure constants module (mirrors system_params.py role for
backtest-scoped params).
Forbidden imports: stdlib + typing only (this is a hex-pure constants module).
Reuse `system_params.SPI_MULT` etc. via direct import in simulator.py — do NOT
re-export here.
"""

BACKTEST_INITIAL_ACCOUNT_AUD: float = 10_000.0  # AUD per CONTEXT D-02 (locked)
BACKTEST_COST_SPI_AUD: float = 6.0              # AUD round-trip per CLAUDE.md D-11
BACKTEST_COST_AUDUSD_AUD: float = 5.0           # AUD round-trip per CLAUDE.md D-11
BACKTEST_DEFAULT_YEARS: int = 5                 # CONTEXT D-03
BACKTEST_PASS_THRESHOLD_PCT: float = 100.0      # CONTEXT D-16 (strict greater-than)
BACKTEST_CACHE_TTL_SECONDS: int = 86_400        # 24h, CONTEXT D-01
