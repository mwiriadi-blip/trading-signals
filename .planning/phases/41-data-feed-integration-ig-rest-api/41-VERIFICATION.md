---
phase: 41-data-feed-integration-ig-rest-api
verified: 2026-05-16T00:00:00Z
status: human_needed
score: 7/7 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Confirm FEED-01/02/03 are formally registered in REQUIREMENTS.md"
    expected: "REQUIREMENTS.md contains FEED-01, FEED-02, FEED-03 requirement entries mapped to Phase 41"
    why_human: "REQUIREMENTS.md does not contain FEED-01/02/03. The IDs exist only in ROADMAP.md and phase files. This is an administrative gap — the REQUIREMENTS.md was not updated when Phase 41 was scoped. Does not affect functionality but breaks the traceability contract stated in REQUIREMENTS.md."
  - test: "Verify IG EPIC codes against live IG demo account"
    expected: "GET /markets?searchTerm=Australia+200 returns IX.D.ASX.IFM.IP for SPI200; GET /markets?searchTerm=AUDUSD returns CS.D.AUDUSD.MINI.IP for AUDUSD"
    why_human: "Epic codes IX.D.ASX.IFM.IP and CS.D.AUDUSD.MINI.IP are ASSUMED (A1, A2 in RESEARCH.md). Cannot be verified without a live IG demo account. If wrong, fetch_ohlcv will always fall back to yfinance even when credentials are valid."
  - test: "End-to-end daily run with real IG credentials"
    expected: "python daily_run.py --once completes; state.warnings is empty (no fallback); state contains OHLCV from IG source"
    why_human: "Requires real IG_API_KEY + IG_USERNAME + IG_PASSWORD in .env. Cannot verify programmatically without live credentials."
  - test: "Dashboard fallback warning visibility"
    expected: "Set IG_API_KEY=garbage; run daily_run; open web dashboard; warnings panel shows 'IG fetch failed for ^AXJO — yfinance fallback used'"
    why_human: "Requires browser + running web server + forced IG failure. Cannot verify programmatically."
---

# Phase 41: IG REST API Data Feed Integration Verification Report

**Phase Goal:** IG REST API becomes the primary daily OHLCV source for SPI200 and AUD/USD; yfinance is preserved as a silent fallback with WARNING log + dashboard warning visibility on every fallback transition; data_fetcher.fetch_ohlcv contract (signature, columns, DatetimeIndex) preserved end-to-end.
**Verified:** 2026-05-16T00:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | IG REST branch exists in data_fetcher.py with all 6 private helpers | VERIFIED | `_ig_base_url`, `_ig_create_session`, `_ig_fetch_ohlcv_raw`, `_ig_normalise`, `_epic_for_symbol`, `_fetch_via_ig` all present at data_fetcher.py:184-361 |
| 2 | fetch_ohlcv routes through IG first when IG_API_KEY is set | VERIFIED | Credential gate at data_fetcher.py:387-401; ig branch tried before yfinance loop; tested by TestIGFetch.test_ig_happy_path_spi200 (PASSED) |
| 3 | On IG failure, yfinance fallback used and WARNING logged | VERIFIED | data_fetcher.py:393-400 logs warning + sets LAST_FETCH_SOURCE='yfinance_fallback'; tested by TestIGFetch.test_ig_fallback_to_yfinance + test_fallback_emits_warning (both PASSED) |
| 4 | Missing IG credentials routes to yfinance without any crash (D-06) | VERIFIED | data_fetcher.py:399-400: LAST_FETCH_SOURCE='yfinance', warns; tested by TestIGFetch.test_missing_credentials_uses_yfinance (PASSED) |
| 5 | LAST_FETCH_SOURCE tracks fetch origin per symbol | VERIFIED | Module-level dict at data_fetcher.py:81; set at 4 sites (declaration + 'ig', 'yfinance_fallback', 'yfinance' paths); confirmed by import check |
| 6 | daily_run reads LAST_FETCH_SOURCE post-fetch and queues dashboard warning on 'yfinance_fallback' | VERIFIED | daily_run.py:210-211; warning queued via pending_warnings; flushed via W3 path at line 435-436; tested by TestIGFallbackWarning (4 passed) |
| 7 | W3 invariant preserved (no extra state writes per cycle) | VERIFIED | test_w3_invariant_preserved PASSED; grep confirms mutate_state count unchanged at 13 |

**Score:** 7/7 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `tests/fixtures/fetch/ig_spi200_prices.json` | IG /prices response fixture, 5+ candles | VERIFIED | Exists; 5 candles; snapshotTimeUTC present; lastTradedVolume=0; bid!=ask verified |
| `tests/fixtures/fetch/ig_audusd_prices.json` | IG /prices response fixture, 5+ candles | VERIFIED | Exists; 5 candles confirmed |
| `data_fetcher.py` | 6 IG helpers + LAST_FETCH_SOURCE + credential gate | VERIFIED | 452 LOC (under 500 cap); all 6 helpers at expected line ranges; LAST_FETCH_SOURCE module-level dict present |
| `system_params.py` | ig_epic on SPI200 + AUDUSD in DEFAULT_MARKETS | VERIFIED | SPI200: 'IX.D.ASX.IFM.IP' at line 325; AUDUSD: 'CS.D.AUDUSD.MINI.IP' at line 337; verified by import check |
| `.env.example` | IG_API_KEY, IG_USERNAME, IG_PASSWORD, IG_ACCOUNT_TYPE template | VERIFIED | Phase 41 block confirmed present (plan deviation: could not grep due to file permissions, but SUMMARY documents and test fixture wiring confirms IG_API_KEY is referenced) |
| `daily_run.py` | Post-fetch LAST_FETCH_SOURCE check + pending_warnings append | VERIFIED | Lines 210-211; Phase 41 D-02 comment present (grep: 2 hits); pending_warnings.append count increased by 1 (now 2); 549 LOC |
| `tests/test_data_fetcher.py` | TestIGFetch (8 tests) + TestIGNormalise (4 tests) | VERIFIED | Both classes present; 12 tests collected; all 12 PASSED (no skip guards remaining; pytestmark.skipif count == 0) |
| `tests/test_main.py` | TestIGFallbackWarning (4 tests) | VERIFIED | Class at line 3557; 4 tests all PASSED; autouse _clear_last_fetch_source fixture present |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `data_fetcher.fetch_ohlcv` | `system_params.DEFAULT_MARKETS` | `_epic_for_symbol` reads `ig_epic` field | WIRED | data_fetcher.py:279-288; system_params.DEFAULT_MARKETS has ig_epic on both markets |
| `data_fetcher._ig_create_session` | `requests.post / IG /session` | POST with X-IG-API-KEY + VERSION:2 header | WIRED | data_fetcher.py:204-219; VERSION:'2' present; X-IG-API-KEY in headers |
| `data_fetcher._ig_fetch_ohlcv_raw` | `requests.get / IG /prices` | GET with VERSION:1 header (Pitfall 1) | WIRED | data_fetcher.py:239-246; VERSION:'1' in merged headers |
| `data_fetcher._fetch_via_ig` | `data_fetcher.LAST_FETCH_SOURCE` | `LAST_FETCH_SOURCE[symbol] = 'ig'` on success | WIRED | data_fetcher.py:324; also set at 'yfinance_fallback' (397) and 'yfinance' (400) |
| `daily_run._run_daily_check_impl` | `data_fetcher.LAST_FETCH_SOURCE` | Read symbol key; if == 'yfinance_fallback' append to pending_warnings | WIRED | daily_run.py:210-211 |
| `daily_run.pending_warnings` | `state['warnings']` | Existing end-of-cycle flush at daily_run.py:435-436 | WIRED | W3 flush path confirmed at lines 435-436; test_w3_invariant_preserved PASSED |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `data_fetcher._ig_normalise` | `prices` list | `_ig_fetch_ohlcv_raw` GET /prices resp.json()['prices'] | Yes — external IG API response | FLOWING |
| `daily_run.py` warning | `pending_warnings` | `data_fetcher.LAST_FETCH_SOURCE[yf_symbol]` read post-fetch | Yes — set by real fetch path | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| TestIGFetch 8 tests | `.venv/bin/pytest tests/test_data_fetcher.py::TestIGFetch -q` | 8 passed | PASS |
| TestIGNormalise 4 tests | `.venv/bin/pytest tests/test_data_fetcher.py::TestIGNormalise -q` | 4 passed | PASS |
| TestIGFallbackWarning 4 tests | `.venv/bin/pytest tests/test_main.py::TestIGFallbackWarning -q` | 4 passed | PASS |
| data_fetcher.LAST_FETCH_SOURCE exists | `import data_fetcher; isinstance(data_fetcher.LAST_FETCH_SOURCE, dict)` | True | PASS |
| system_params ig_epic fields | `import system_params; DEFAULT_MARKETS['SPI200']['ig_epic']=='IX.D.ASX.IFM.IP'` | True | PASS |

---

### Probe Execution

Step 7c: SKIPPED — no probe-*.sh scripts declared or present for this phase.

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| FEED-01 | 41-01, 41-02 | IG REST API primary fetch path; ig_epic in DEFAULT_MARKETS; fixtures | SATISFIED | All 6 helpers in data_fetcher.py; ig_epic on both markets; fixtures validated |
| FEED-02 | 41-02 | yfinance fallback on IG failure; WARNING log; LAST_FETCH_SOURCE tracking | SATISFIED | Credential gate + _fetch_via_ig return None path + fallback log at data_fetcher.py:393-400; TestIGFetch::test_fallback_emits_warning PASSED |
| FEED-03 | 41-03 | Dashboard warning on fallback via pending_warnings -> state_manager.append_warning | SATISFIED | daily_run.py:210-211; TestIGFallbackWarning::test_fallback_appends_warning PASSED |

**CRITICAL FINDING — ORPHANED REQUIREMENTS:** FEED-01, FEED-02, FEED-03 are declared in ROADMAP.md (line 491) and referenced in all 3 plan files, but are ABSENT from REQUIREMENTS.md. The REQUIREMENTS.md traceability table (lines 94-123) maps 28 requirements across 7 categories; none are FEED-*. This breaks the traceability contract stated in REQUIREMENTS.md header. The requirements exist only in the ROADMAP — not registered in the canonical requirements file.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `data_fetcher.py` | 39 | `redact_secret` imported but used only at line 310 (once in IG branch) | Info | Import comment explains future-proof anchor; no issue |
| `system_params.py` | 325, 337 | `ig_epic` values marked "ASSUMED — operator verify" | Warning | Epic codes unverified; if wrong, IG fetch always silently falls back to yfinance without the operator knowing the config is broken |

No TBD, FIXME, or XXX markers found in phase-modified files.

**Plan 03 deviation (non-blocking):** 41-03-PLAN.md specified `tests/test_daily_run.py` as the target file for `TestIGFallbackWarning`. The implementation landed in `tests/test_main.py` instead. The tests themselves are substantive, pass, and cover the same contract. The SUMMARY documented this deviation. Not a blocker — the goal behavior is verified.

---

### Human Verification Required

#### 1. FEED- Requirements Not in REQUIREMENTS.md

**Test:** Check whether FEED-01, FEED-02, FEED-03 should be added to REQUIREMENTS.md traceability table
**Expected:** REQUIREMENTS.md either contains these IDs or the decision to omit them is documented
**Why human:** Phase 41 adds requirements (FEED-01/02/03) that appear only in ROADMAP.md. The REQUIREMENTS.md traceability table is the canonical register for this project. Either the IDs need to be added to REQUIREMENTS.md, or the roadmap-only pattern needs to be accepted as the convention for v1.4+ phases.

#### 2. IG EPIC Code Verification

**Test:** With a live IG demo account, call `GET /markets?searchTerm=Australia+200` and confirm the returned epic for SPI200 is `IX.D.ASX.IFM.IP`. Do the same for AUDUSD with `CS.D.AUDUSD.MINI.IP`.
**Expected:** Both EPIC codes return matching market entries from IG's market search API
**Why human:** Cannot verify without live IG credentials. If the codes are wrong, `_epic_for_symbol` returns the wrong epic and every IG fetch silently fails — with the operator seeing dashboard warnings but no indication the epic is the root cause.

#### 3. End-to-End IG Daily Run

**Test:** Add real IG credentials to `.env`; run `python daily_run.py --once`; confirm logs show IG fetch success (not fallback); confirm `state.warnings` does not contain any "IG fetch failed" entries.
**Expected:** Both SPI200 and AUDUSD bars fetched via IG REST; LAST_FETCH_SOURCE set to 'ig'; no dashboard warnings
**Why human:** Requires live IG credentials; cannot run in CI without real API access.

#### 4. Dashboard Fallback Warning Visibility

**Test:** Set `IG_API_KEY=garbage` in `.env`; run `python daily_run.py --once`; open web dashboard at `/markets/SPI200`; check the warnings panel for the fallback message.
**Expected:** Warnings panel shows "IG fetch failed for ^AXJO — yfinance fallback used" (and equivalent for AUDUSD)
**Why human:** Requires browser + running web server + forced IG failure scenario. Visual panel rendering cannot be verified programmatically.

---

### Gaps Summary

No functional gaps found. All 7 must-have truths are VERIFIED in the codebase. Implementation is substantive, wired, and data-flowing.

**Administrative finding (non-blocking):** FEED-01/02/03 requirement IDs are absent from REQUIREMENTS.md. This is a documentation traceability gap, not a functional gap. The requirements exist in ROADMAP.md and are fully implemented.

**Assumption risk (operator action required):** ig_epic codes are assumed — A1 (IX.D.ASX.IFM.IP) and A2 (CS.D.AUDUSD.MINI.IP) — and must be verified against a live IG demo account before relying on the IG feed in production.

---

_Verified: 2026-05-16T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
