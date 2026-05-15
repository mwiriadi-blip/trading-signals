---
phase: 38-news-integration
plan: "01"
subsystem: news-integration-substrate
tags: [system_params, test-fixtures, ast-boundary, hex-guard, wave-0]
dependency_graph:
  requires: []
  provides:
    - NEWS_KEYWORDS_SPI200 constant in system_params.py
    - NEWS_KEYWORDS_AUDUSD constant in system_params.py
    - NEWS_DAMPENER_ALLOWLIST constant in system_params.py
    - NEWS_FILTER_PATH path constant in tests/test_signal_engine.py
    - NEWS_FETCHER_PATH path constant in tests/test_signal_engine.py
    - FORBIDDEN_MODULES_NEWS_FETCHER frozenset in tests/test_signal_engine.py
    - _HEX_PATHS_STDLIB_ONLY extended with NEWS_FILTER_PATH
    - test_news_modules_exist_after_wave2 hard-existence meta-gate
    - tests/fixtures/news/news_fixture_pre055.json
    - tests/fixtures/news/news_fixture_post055.json
    - tests/fixtures/news/news_classifier_30.json
  affects: [Plan 02 (news_filter.py), Plan 03 (news_fetcher.py)]
tech_stack:
  added: []
  patterns:
    - tuple[str, ...] keyword constants in system_params.py (D-06 pattern)
    - Wave-ordered AST guard skip-missing pattern for pre-Wave-2 paths
    - Hard-existence meta-gate test (compensates for skip-missing)
    - pytest.skip for Wave-ordered execution (not xfail — skip is correct here)
key_files:
  created:
    - tests/fixtures/news/news_fixture_pre055.json
    - tests/fixtures/news/news_fixture_post055.json
    - tests/fixtures/news/news_classifier_30.json
  modified:
    - system_params.py
    - tests/test_signal_engine.py
decisions:
  - "Used conditional-assert variant for test_news_modules_exist_after_wave2: if EITHER file exists BOTH must exist. This keeps Wave 1 suite green (neither exists) while catching partial Wave 2 landing (one exists, other missing). Plan spec offered this as the recommended fallback."
  - "Skip-missing guard added to both test_forbidden_imports_absent AND test_phase2_hex_modules_no_numpy_pandas since NEWS_FILTER_PATH appears in _HEX_PATHS_STDLIB_ONLY (the stdlib-only list) — both parametrized tests iterate that list."
  - "FORBIDDEN_MODULES_NEWS_FETCHER placed adjacent to FORBIDDEN_MODULES_DATA_FETCHER per plan spec; mirrors exact pattern including numpy/schedule/dotenv/pytz blocking."
metrics:
  duration: "~15min"
  completed: "2026-05-16"
  tasks: 3
  files: 5
---

# Phase 38 Plan 01: News Integration Substrate Summary

Wave 0 foundation for Phase 38 news integration. Three keyword tuple constants in system_params.py, AST hex-boundary extensions in test_signal_engine.py, and three JSON test fixtures under tests/fixtures/news/.

## What Was Built

### system_params.py additions (Task 1)

Three module-level constants typed as `tuple[str, ...]` in a new `# === Phase 38 constants` section:

- `NEWS_KEYWORDS_SPI200` — 25 keywords: Australian systemic events (rba, reserve bank, rate cut/hike, interest rate, recession, gdp, inflation, cpi, stagflation), ASX circuit-breaker events (asx halt, trading halt, market halt, circuit breaker, crash, sell-off, rout, collapse, plunge), global systemic drivers (fed, federal reserve, ecb, bank of japan, tariff, trade war, sanctions, pandemic, lockdown)
- `NEWS_KEYWORDS_AUDUSD` — 28 keywords: AUD/USD direct drivers (rba, reserve bank, rate cut/hike, interest rate, aud, aussie dollar, australian dollar, china gdp, iron ore, commodity, terms of trade), USD drivers (fed, federal reserve, fomc, us cpi, us gdp, dollar, dxy, greenback), macro risk (recession, stagflation, tariff, trade war, sanctions, pandemic, lockdown, geopolitical)
- `NEWS_DAMPENER_ALLOWLIST` — 11 suppressors: first-rate, second-rate, first rate, second rate, flat-rate, flat rate, pro-rate, pro rate, interest in, rate your, interest and

All entries lowercase. Hex-boundary preserved (stdlib-only: re, decimal, typing). AST guard test_forbidden_imports_absent passes.

### tests/test_signal_engine.py extensions (Task 2)

Four structural additions:

1. `NEWS_FILTER_PATH = Path('news_filter.py')` and `NEWS_FETCHER_PATH = Path('news_fetcher.py')` path constants declared adjacent to ALERT_ENGINE_PATH
2. `_HEX_PATHS_STDLIB_ONLY` extended: `[...ALERT_ENGINE_PATH, NEWS_FILTER_PATH]` — registers news_filter.py for stdlib-only AST check once Plan 02 lands it
3. `FORBIDDEN_MODULES_NEWS_FETCHER` frozenset blocking signal_engine, sizing_engine, state_manager, notifier, dashboard, main, numpy, schedule, dotenv, pytz from news_fetcher.py imports
4. Skip-missing guard added to `test_forbidden_imports_absent` and `test_phase2_hex_modules_no_numpy_pandas` — both skip if the parametrized path does not yet exist on disk (Wave-ordered execution support)
5. `test_news_modules_exist_after_wave2` hard-existence meta-gate: if either news module exists, both must exist; if neither exists (Wave 1), the test skips cleanly

TestDeterminism: 77 passed, 2 skipped (both expected Wave 1 skips).

### tests/fixtures/news/ (Task 3)

Three JSON fixtures:

- `news_fixture_pre055.json` — 5 items, flat pre-0.2.55 schema (uuid/title/publisher/link/providerPublishTime/type/thumbnail/relatedTickers). Covers: benign, RBA rate decision, XSS payload `<script>alert(1)</script>`, "first-rate" dampener phrase, routine company news.
- `news_fixture_post055.json` — 5 items, nested post-0.2.55 content envelope (id/content.title/content.pubDate/content.provider.displayName/content.canonicalUrl/content.clickThroughUrl). One item has `clickThroughUrl: null` to exercise the None-fallback in the normaliser. Same five semantic themes as pre055 for parity.
- `news_classifier_30.json` — 30 labelled headlines (16 positive label=1, 14 negative label=0; 15 SPI200 + 15 AUDUSD). Positive examples: RBA rate decisions, Fed/FOMC actions, market halts, tariff/trade-war news, recession/CPI events, AUD/dollar drivers. Negative examples: routine earnings, iron ore production updates, customer satisfaction articles, dampener phrases (first-rate, flat rate, pro-rate, rate your, interest and).

## Verification

All plan verification criteria met:

1. `pytest tests/test_signal_engine.py::TestDeterminism` — 77 passed, 2 skipped (Wave 1 expected)
2. `python -c "import system_params as s; assert hasattr(s,'NEWS_KEYWORDS_SPI200') and hasattr(s,'NEWS_KEYWORDS_AUDUSD') and hasattr(s,'NEWS_DAMPENER_ALLOWLIST')"` — exits 0
3. Three fixtures parse as valid JSON with required structural shape — verified
4. Full suite: 2326 passed, 3 skipped, 0 failures — no regression

## Wave 2 Completion Gate

When Plans 02 and 03 land `news_filter.py` and `news_fetcher.py`:
- `test_news_modules_exist_after_wave2` transitions from SKIP to PASS — this is the completion signal
- `test_forbidden_imports_absent` and `test_phase2_hex_modules_no_numpy_pandas` will run against both files (skip guard no longer fires)
- Plan 02 must achieve precision ≥0.7 / recall ≥0.9 against `news_classifier_30.json`

## Deviations from Plan

None — plan executed exactly as written. The choice between the two `test_news_modules_exist_after_wave2` variants (RED-by-design vs conditional-assert) was explicitly documented as an executor decision in the plan; chose the conditional-assert variant to maintain Wave 1 green suite invariant.

## Known Stubs

None. This plan creates constants and fixtures only — no UI rendering, no data sources to wire.

## Threat Flags

None beyond the threat model already declared in the plan (T-38-01-01 through T-38-01-04 all addressed by plan design).

## Self-Check: PASSED

- `system_params.py` — NEWS_KEYWORDS_SPI200, NEWS_KEYWORDS_AUDUSD, NEWS_DAMPENER_ALLOWLIST present (grep verified)
- `tests/test_signal_engine.py` — NEWS_FILTER_PATH, NEWS_FETCHER_PATH, FORBIDDEN_MODULES_NEWS_FETCHER, test_news_modules_exist_after_wave2 present (grep verified)
- `tests/fixtures/news/news_fixture_pre055.json` — exists, parses, len=5, uuid+title+link+publisher+providerPublishTime present, XSS payload present
- `tests/fixtures/news/news_fixture_post055.json` — exists, parses, len=5, content+id present, one clickThroughUrl=null
- `tests/fixtures/news/news_classifier_30.json` — exists, parses, len=30, pos=16 (within 12..20 gate)
- Commits: ec3bed6 (Task 1), f6c7f82 (Task 2), dd31f9d (Task 3) — all in git log
