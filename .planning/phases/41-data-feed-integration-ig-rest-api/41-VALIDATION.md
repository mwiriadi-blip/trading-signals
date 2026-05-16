---
phase: 41
slug: data-feed-integration-ig-rest-api
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-16
updated: 2026-05-16
---

# Phase 41 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | pytest.ini or pyproject.toml |
| **Quick run command** | `.venv/bin/pytest -x --tb=short tests/test_data_fetcher.py` |
| **Full suite command** | `.venv/bin/pytest -x --tb=short` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/pytest -x --tb=short tests/test_data_fetcher.py`
- **After every plan wave:** Run `.venv/bin/pytest -x --tb=short`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

Tests under TestIGFetch + TestIGNormalise are CREATED by Plan 01 (Wave 0) and become live (unskipped + passing) after Plan 02 lands. TestIGFallbackWarning is created by Plan 03.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 41-01-01 | 01 | 0 | FEED-01 | T-41-01-01..03 | IG fixtures parse cleanly; no real creds in fixtures | unit | `python -c "import json; json.load(open('tests/fixtures/fetch/ig_spi200_prices.json'))"` | ❌ W0 | ⬜ pending |
| 41-01-02 | 01 | 0 | FEED-01 | T-41-01-02 | TestIGFetch + TestIGNormalise skeletons collected (skipped pending Plan 02) | unit | `.venv/bin/pytest --collect-only tests/test_data_fetcher.py 2>&1 \| grep -cE "(TestIGFetch\|TestIGNormalise)::test_"` | ❌ W0 | ⬜ pending |
| 41-02-01 | 02 | 1 | FEED-01 | — | ig_epic fields land in DEFAULT_MARKETS; .env.example documents IG vars | unit | `python -c "import system_params; assert system_params.DEFAULT_MARKETS['SPI200']['ig_epic']=='IX.D.ASX.IFM.IP'"` | ❌ W0 | ⬜ pending |
| 41-02-02 | 02 | 1 | FEED-01, FEED-02 | T-41-02-01..07 | IG branch happy path + retries + 403 re-auth + fallback; redact_secret applied; VERSION header per Pitfall 1 | unit | `.venv/bin/pytest -x --tb=short tests/test_data_fetcher.py::TestIGFetch tests/test_data_fetcher.py::TestIGNormalise -v` | ❌ W0 | ⬜ pending |
| 41-03-01 | 03 | 2 | FEED-03 | T-41-03-01..03 | Fallback transition queues dashboard warning via pending_warnings → state_manager.append_warning (W3 invariant preserved) | unit | `.venv/bin/pytest -x --tb=short tests/test_daily_run.py::TestIGFallbackWarning -v` | ❌ W0 | ⬜ pending |

**File Exists column note:** All test code paths in this table are CREATED by Wave 0 (Plan 01) or by the implementation plans themselves (Plans 02-03 add daily_run tests). Mark ❌ W0 until each respective wave commits the test file additions; flip to ✅ after that wave's commit lands.

*Status legend: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/fixtures/fetch/ig_spi200_prices.json` — hand-crafted IG response fixture (≥5 candles, lastTradedVolume=0, bid≠ask)
- [ ] `tests/fixtures/fetch/ig_audusd_prices.json` — AUDUSD equivalent
- [ ] `tests/test_data_fetcher.py` — append TestIGFetch (≥8 tests) + TestIGNormalise (≥4 tests) with class-level `pytestmark = pytest.mark.skipif(not hasattr(data_fetcher, '_ig_normalise'), ...)`
- [ ] `_FakeResponse` helper class + `_load_ig_fixture` loader present in test file

*Existing pytest infrastructure covers all phase requirements — no new framework installation needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| EPIC code correctness | D-11, FEED-01 | Requires live IG demo account | Run `GET /markets?searchTerm=Australia+200` against demo API; confirm `IX.D.ASX.IFM.IP` returns SPI200 results. Resolves Assumptions Log A1. |
| AUDUSD EPIC correctness | D-11, FEED-01 | Requires live IG demo account | Run `GET /markets?searchTerm=AUDUSD` against demo API; confirm `CS.D.AUDUSD.MINI.IP`. Resolves Assumptions Log A2. |
| Demo vs live URL routing | D-09 | Requires credentials | Set `IG_ACCOUNT_TYPE=demo` and `live`; confirm base URL changes accordingly via debug log. |
| End-to-end daily run | D-01, FEED-01..03 | Requires IG credentials in .env | Run `python daily_run.py --once` with real IG creds; confirm SPI200 + AUDUSD bars fetched and `state.warnings` empty (no fallback). |
| Dashboard fallback warning visibility | D-02, FEED-03 | Requires forced IG failure | Set `IG_API_KEY=garbage`; run daily_run; check web dashboard warnings panel shows `IG fetch failed for ^AXJO — yfinance fallback used`. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
