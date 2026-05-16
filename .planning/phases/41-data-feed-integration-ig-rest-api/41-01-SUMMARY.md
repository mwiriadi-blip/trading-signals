---
phase: 41
plan: "01"
subsystem: data-feed
tags: [ig, data-feed, test-scaffold, wave-0, tdd]
dependency_graph:
  requires: []
  provides: [ig-fixture-schema, ig-test-contract]
  affects: [tests/test_data_fetcher.py]
tech_stack:
  added: []
  patterns: [tdd-red-gate, class-level-skipif, fake-response-stub]
key_files:
  created:
    - tests/fixtures/fetch/ig_spi200_prices.json
    - tests/fixtures/fetch/ig_audusd_prices.json
  modified:
    - tests/test_data_fetcher.py
decisions:
  - class-level pytestmark avoids affecting existing TestFetch class
  - _load_ig_fixture uses json.load not pd.read_json (raw IG JSON, not orient=split)
  - _FakeResponse defined adjacent to TestIGFetch for locality
  - pre-existing golden dashboard snapshot failure confirmed out-of-scope
metrics:
  duration: "344s"
  completed: "2026-05-16"
  tasks: 2
  files: 3
requirements: [FEED-01]
---

# Phase 41 Plan 01: IG REST API Test Scaffold Summary

Wave 0 test-first gate: 2 IG response fixtures + 12 named test skeletons locking the Plan 02 implementation contract before any source change.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create IG response fixtures (SPI200 + AUDUSD) | d623013 | tests/fixtures/fetch/ig_spi200_prices.json, tests/fixtures/fetch/ig_audusd_prices.json |
| 2 | Append TestIGFetch + TestIGNormalise skeletons | 2b7abcb | tests/test_data_fetcher.py |

## What Was Built

**Task 1 — IG response fixtures**

Two hand-crafted JSON fixture files mirroring the exact IG `/prices/{epic}/D/{n}` response shape from RESEARCH.md §Code Examples:

- `ig_spi200_prices.json`: 5 daily candles, SPI200 index range ~7810–7900, epic `IX.D.ASX.IFM.IP` documented in `_fixture_metadata`
- `ig_audusd_prices.json`: 5 daily candles, AUD/USD FX range ~0.651–0.668, epic `CS.D.AUDUSD.MINI.IP`

Every candle: `lastTradedVolume=0` (spread-bet convention, Pitfall 2); `bid != ask` on every candle (non-trivial mid-price math); `snapshotTimeUTC` ISO 8601 without trailing `Z`, monotonically increasing, parseable by `pd.to_datetime(..., utc=True)`.

**Task 2 — Test skeletons**

Appended to `tests/test_data_fetcher.py`:
- `_load_ig_fixture(name)` — raw `json.load` helper (not `pd.read_json`)
- `_FakeResponse` class — mimics `requests.Response` with `.raise_for_status()`, `.json()`, `.headers`, `.status_code`
- `TestIGNormalise` (4 tests): mid-price math (D-12), Volume=0 accepted (Pitfall 2), UTC DatetimeIndex (Pitfall 3), canonical OHLCV columns
- `TestIGFetch` (8 tests): SPI200/AUDUSD happy path, retry-on-timeout (3 attempts), fallback-to-yfinance, fallback-emits-warning, missing-credentials-uses-yfinance, session-403-no-retry, prices-403-triggers-one-reauth (Pitfall 4)

All 12 new tests skip with `"Plan 41-02 not yet shipped — IG helpers absent"` via class-level `pytestmark = pytest.mark.skipif(not hasattr(data_fetcher, '_ig_normalise'), ...)`. Existing 8 TestFetch + TestColumnShape tests pass with no regression.

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None. Fixtures are complete hand-crafted data. Test bodies have real assertions (not `pass`) ready to activate when Plan 02 ships.

## Out-of-Scope Issue Logged

Pre-existing failure `tests/test_dashboard.py::TestGoldenSnapshot::test_golden_snapshot_matches_committed` exists at the base commit (2c5927f) and is unrelated to this plan's changes. Not fixed here per scope boundary rule.

## Threat Flags

None — fixtures contain only synthetic prices and assumed epic codes in `_fixture_metadata`. No credentials, no real account data (T-41-01-01 accepted per plan threat register).

## Self-Check: PASSED

| Item | Status |
|------|--------|
| tests/fixtures/fetch/ig_spi200_prices.json | FOUND |
| tests/fixtures/fetch/ig_audusd_prices.json | FOUND |
| tests/test_data_fetcher.py | FOUND |
| commit d623013 | FOUND |
| commit 2b7abcb | FOUND |
| TestIGFetch class count == 1 | PASS |
| TestIGNormalise class count == 1 | PASS |
| pytest tests/test_data_fetcher.py | 8 passed, 12 skipped, 0 failed |
