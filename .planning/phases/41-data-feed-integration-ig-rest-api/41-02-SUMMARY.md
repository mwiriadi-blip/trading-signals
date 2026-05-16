---
phase: 41
plan: "02"
subsystem: data-feed
tags: [ig, data-feed, implementation, wave-1, tdd]
dependency_graph:
  requires: [41-01]
  provides: [ig-rest-branch, ig-fetch-helpers, last-fetch-source]
  affects: [data_fetcher.py, system_params.py, .env.example, tests/test_data_fetcher.py]
tech_stack:
  added: []
  patterns: [ig-rest-session, bid-ask-mid-normalise, credential-gate-fallback, ssrf-guard, per-endpoint-version-header]
key_files:
  created: []
  modified:
    - system_params.py
    - .env.example
    - data_fetcher.py
    - tests/test_data_fetcher.py
decisions:
  - ig_epic stored in DEFAULT_MARKETS alongside existing market config (D-11)
  - VERSION header is per-endpoint — 2 for /session, 1 for /prices (Pitfall 1)
  - Session 403 = no retry; prices 403 = one re-auth then retry (Pitfall 4)
  - LAST_FETCH_SOURCE dict tracks 'ig'/'yfinance'/'yfinance_fallback' per symbol
  - redact_secret applied to IG_API_KEY in all log lines (T-41-02-01 / ASVS V2)
  - _ig_base_url gates IG_ACCOUNT_TYPE to known dict values — SSRF guard (T-41-02-04)
  - fetch_ohlcv signature unchanged; IG branch is purely additive (D-10)
metrics:
  duration: "~15 min"
  completed: "2026-05-16"
  tasks: 2
  files: 4
requirements: [FEED-01, FEED-02]
---

# Phase 41 Plan 02: IG REST API Implementation Summary

IG-first data path with graceful yfinance fallback implemented in data_fetcher.py; 6 private helpers, LAST_FETCH_SOURCE tracking, credential gate, and all 12 Plan 01 test skeletons activated and passing.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add ig_epic to DEFAULT_MARKETS + IG env vars to .env.example | 0a4b764 | system_params.py, .env.example |
| 2 | Implement IG branch + helpers in data_fetcher.py + unskip Plan 01 tests | 49adc0d | data_fetcher.py, tests/test_data_fetcher.py |

## What Was Built

**Task 1 — system_params.py + .env.example**

- `DEFAULT_MARKETS['SPI200']` gains `'ig_epic': 'IX.D.ASX.IFM.IP'` (ASSUMED per research A1; operator must verify via IG /markets API)
- `DEFAULT_MARKETS['AUDUSD']` gains `'ig_epic': 'CS.D.AUDUSD.MINI.IP'` (ASSUMED per research A2; operator must verify)
- `.env.example` gains Phase 41 block: `IG_API_KEY=`, `IG_USERNAME=`, `IG_PASSWORD=`, `IG_ACCOUNT_TYPE=demo`

**Task 2 — data_fetcher.py IG branch**

Six private helpers added before `fetch_ohlcv`:

| Helper | Purpose |
|--------|---------|
| `_ig_base_url()` | Maps `IG_ACCOUNT_TYPE` env var to demo/live URL; SSRF guard gates to known dict |
| `_ig_create_session()` | POST /session with VERSION:2; returns headers dict; never logs tokens |
| `_ig_fetch_ohlcv_raw()` | GET /prices/{epic}/D/{n} with VERSION:1 (Pitfall 1); returns prices list |
| `_ig_normalise()` | Converts bid/ask candles to mid-price OHLCV DataFrame; UTC index; Volume=0 OK |
| `_epic_for_symbol()` | Looks up ig_epic from DEFAULT_MARKETS by yfinance symbol |
| `_fetch_via_ig()` | Orchestrates session + fetch + retry + one re-auth on prices 403 (Pitfall 4) |

Module-level additions:
- `_IG_BASE_URLS` dict (demo/live base URLs)
- `LAST_FETCH_SOURCE: dict[str, str]` — populated by fetch_ohlcv; Plan 03 reads this for dashboard warnings (D-02)

`fetch_ohlcv` credential gate (additive, before existing yfinance loop):
- `IG_API_KEY` set + epic found → try IG; fallback to yfinance on None return with WARNING log
- `IG_API_KEY` absent → WARNING log + set `LAST_FETCH_SOURCE[symbol]='yfinance'`; yfinance primary

Tests: removed `pytestmark = pytest.mark.skipif(...)` from both `TestIGNormalise` and `TestIGFetch`. All 12 tests activate and pass.

## Verification Results

```
LOC: 452 (cap 500) — OK
ruff check data_fetcher.py — All checks passed
TestIGFetch: 8 passed
TestIGNormalise: 4 passed
tests/test_data_fetcher.py + tests/test_system_params.py: 38 passed
grep -c "def _ig_create_session" == 1 (all 6 helpers verified)
grep -c "LAST_FETCH_SOURCE" == 4 (declaration + 3 assignment sites)
VERSION '2' for /session, VERSION '1' for /prices — verified
grep -cE "except Exception\b" == 0
grep -c "redact_secret" == 4
grep -c "pytestmark = pytest.mark.skipif" == 0
```

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

- `ig_epic` values (`IX.D.ASX.IFM.IP` and `CS.D.AUDUSD.MINI.IP`) are ASSUMED epic codes. Both are flagged with inline comments for operator verification via the IG /markets API before live use. These are documented assumptions (A1, A2 in RESEARCH.md), not implementation stubs — the fetch path is fully wired.

## Out-of-Scope Issue

Pre-existing `tests/test_dashboard.py::TestGoldenSnapshot::test_golden_snapshot_matches_committed` failure confirmed at base commit a0071b7 (pre-existed in Plan 01 SUMMARY too). Not caused by Plan 02 changes. Deferred.

## Threat Flags

None — no new network endpoints, auth paths, or schema changes beyond what the plan's threat model covers. All STRIDE mitigations from the plan threat register are implemented:
- T-41-02-01: `redact_secret` applied to IG_API_KEY in log lines
- T-41-02-02: IG_PASSWORD never logged (POST body only, over TLS)
- T-41-02-03: session tokens in-memory only; no persistence
- T-41-02-04: `_ig_base_url()` SSRF guard gates IG_ACCOUNT_TYPE to known dict
- T-41-02-05: retry count capped at `retries` param (default 3)

## Self-Check: PASSED

| Item | Status |
|------|--------|
| system_params.py SPI200 ig_epic | FOUND |
| system_params.py AUDUSD ig_epic | FOUND |
| .env.example IG_API_KEY= line | FOUND |
| data_fetcher.py LAST_FETCH_SOURCE | FOUND |
| data_fetcher.py _ig_normalise | FOUND |
| data_fetcher.py _fetch_via_ig | FOUND |
| commit 0a4b764 | FOUND |
| commit 49adc0d | FOUND |
| TestIGFetch 8 passed | PASS |
| TestIGNormalise 4 passed | PASS |
| LOC 452 <= 500 | PASS |
| ruff check data_fetcher.py | PASS |
| No bare Exception catches | PASS |
| No skipif guards remaining | PASS |
