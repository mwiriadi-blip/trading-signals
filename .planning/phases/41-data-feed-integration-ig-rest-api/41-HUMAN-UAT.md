---
status: partial
phase: 41-data-feed-integration-ig-rest-api
source: [41-VERIFICATION.md]
started: 2026-05-16T00:00:00Z
updated: 2026-05-16T00:00:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. FEED requirements not in REQUIREMENTS.md
expected: FEED-01/02/03 are added to REQUIREMENTS.md canonical traceability table, OR operator explicitly accepts roadmap-only convention for v1.4+ phases
result: [pending]

### 2. IG epic code verification
expected: `IX.D.ASX.IFM.IP` (SPI200) and `CS.D.AUDUSD.MINI.IP` (AUDUSD) verified against live IG demo API GET /markets?searchTerm=... before relying on IG feed in production
result: [pending]

### 3. End-to-end daily run with real IG credentials
expected: `python daily_run.py --once` with real IG creds logs IG success (not fallback); `state.warnings` empty; LAST_FETCH_SOURCE shows 'ig'
result: [pending]

### 4. Dashboard fallback warning panel
expected: Set `IG_API_KEY=garbage`; run daily_run; warnings panel in browser shows "IG fetch failed for [symbol] — yfinance fallback used"
result: [pending]

## Summary

total: 4
passed: 0
issues: 0
pending: 4
skipped: 0
blocked: 0

## Gaps
