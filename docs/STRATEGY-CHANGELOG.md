# Strategy Changelog

Append-only record of signal-logic changes. Each entry documents the
constants present at that version. Bump `STRATEGY_VERSION` in
`system_params.py` on signal-logic changes only (see Phase 22 D-03).

## v1.2.0 — 2026-04-30 (no logic change)

Versioning system introduced. Signal logic unchanged from v1.1.0 / v1.0.0.

Constants at this version:
- ATR_PERIOD = 14
- ADX_PERIOD = 20
- ADX_GATE_THRESHOLD = 25
- MOM_PERIODS = [1, 3, 12]
- RVOL_PERIOD = 20
- VOTE_RULE = "2-of-3 momentum sign agreement"
- POSITION_SIZE_PCT_LONG = 0.01
- POSITION_SIZE_PCT_SHORT = 0.005
- TRAILING_STOP_ATR_MULTIPLIER = 3.0

## v1.1.0 — 2026-04-30 (no logic change)

Hosted dashboard + interactive trade journal + auth UX.
Signal logic unchanged from v1.0.0.

## v1.0.0 — 2026-04-24 (initial)

Original signal logic from v1.0 milestone (Phases 1-9).
ATR/ADX/Mom/RVol indicators, 2-of-3 momentum vote gated by ADX>=25.
