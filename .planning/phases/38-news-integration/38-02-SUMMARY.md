---
phase: 38-news-integration
plan: "02"
subsystem: news-filter-classifier
tags: [news-filter, keyword-classifier, hex-boundary, tdd, wave-2]
dependency_graph:
  requires:
    - NEWS_KEYWORDS_SPI200 in system_params.py (Plan 01)
    - NEWS_KEYWORDS_AUDUSD in system_params.py (Plan 01)
    - NEWS_DAMPENER_ALLOWLIST in system_params.py (Plan 01)
    - NEWS_FILTER_PATH in _HEX_PATHS_STDLIB_ONLY (Plan 01)
    - tests/fixtures/news/news_classifier_30.json (Plan 01)
  provides:
    - news_filter.classify_headline(text, market_id) -> bool
    - news_filter.has_critical_event(headlines, market_id) -> bool
    - tests/test_news_filter.py — 14-test suite with precision/recall gate
  affects: [Plan 04 (web banner wiring — classify_headline consumer)]
tech_stack:
  added: []
  patterns:
    - stdlib-only hex module (re + logging + system_params — no third-party)
    - module-level compiled re.Pattern artefacts (import-time cost, zero per-call regex compile)
    - dampener slow-path: re.sub + re-run keyword search (preserves correctness for "first-rate after RBA rate cut")
    - TDD RED/GREEN with word-boundary + dampener fixture-driven precision/recall gate
key_files:
  created:
    - news_filter.py
    - tests/test_news_filter.py
  modified: []
decisions:
  - "Dampener slow-path substitutes matched spans then re-runs keyword search (vs per-span exclusion). Simpler, correct for overlapping dampener+keyword in same headline."
  - "has_critical_event accepts list[dict] with .get('title','') — structural typing avoids hard import of news_fetcher (concurrent Wave 2 plan). TypedDict annotation is doc-only."
  - "logging module confirmed not in FORBIDDEN_MODULES_STDLIB_ONLY before implementing — stdlib, not blocked by hex guard."
metrics:
  duration: "~10min"
  completed: "2026-05-16"
  tasks: 2
  files: 2
---

# Phase 38 Plan 02: news_filter.py — Keyword Classifier Summary

Stdlib-only hex module implementing word-boundary keyword classifier for critical-event news banners. TDD RED/GREEN; precision=0.941 and recall=1.000 on 30-headline sanity-check fixture (gate: ≥0.7/≥0.9).

## What Was Built

### news_filter.py (Task 2)

Pure-math hex module (129 LOC, well under 500-line limit). Imports: `re`, `logging`, `system_params` only — passes `_HEX_PATHS_STDLIB_ONLY` AST guard.

Module-level compiled artefacts (zero per-call regex compilation cost):
- `_MARKET_KEYWORDS: dict[str, tuple[str, ...]]` — maps `SPI200` and `AUDUSD` to their keyword tuples from `system_params`
- `_PATTERNS: dict[str, re.Pattern]` — compiled word-boundary OR patterns per market, IGNORECASE
- `_DAMPENER_RE: re.Pattern` — compiled OR of all dampener phrases (IGNORECASE)

Public API:
- `classify_headline(text: str, market_id: str) -> bool` — fast path (no dampener hit) skips scrubbing; slow path substitutes dampener spans then re-runs keyword pattern
- `has_critical_event(headlines: list, market_id: str) -> bool` — iterates `.get('title', '')` on each item; short-circuits on first match

Unknown `market_id` emits `logging.WARNING` (format: `classify_headline received unknown market_id=%r; returning False`) and returns `False`.

### tests/test_news_filter.py (Task 1 — TDD RED)

14 tests covering full contract:
- Unknown market: returns False + WARNING log (caplog fixture)
- SPI200 rate hike match, AUDUSD FOMC match
- Dampener suppresses "first-rate service" but not "first-rate service after RBA rate cut"
- Empty string returns False; case-insensitive matching
- Word-boundary prevents "integration" from matching (no substring false positives)
- `has_critical_event`: any-match fires, no-match returns False, missing title key safe, full NewsItem shape accepted
- `test_classifier_precision_recall`: iterates 30-headline fixture, computes tp/fp/fn, asserts precision ≥0.7 AND recall ≥0.9

## Classifier Performance (30-headline sanity-check)

| Metric | Result | Gate |
|--------|--------|------|
| True Positives | 16 | — |
| False Positives | 1 | — |
| False Negatives | 0 | — |
| True Negatives | 13 | — |
| Precision | 0.941 | ≥0.70 PASS |
| Recall | 1.000 | ≥0.90 PASS |

One FP: `"Westpac upgrades AUD forecast — interest and economic outlook positive"` (label=0, market=AUDUSD). The dampener removes "interest and" but "AUD" in "AUD forecast" still matches the AUDUSD keyword set. Precision=0.941 exceeds the 0.7 gate — no keyword tuning required.

NOTE: 30-headline fixture is a heuristic sanity-check (±15–20% CI at 95%). Exists to catch grossly miscalibrated keyword sets only.

## Verification

1. `.venv/bin/pytest -x --tb=short tests/test_news_filter.py` — 14 passed
2. `test_forbidden_imports_absent` and `test_phase2_hex_modules_no_numpy_pandas` — 22 passed (AST hex guard green for news_filter.py)
3. `test_news_modules_exist_after_wave2` — EXPECTED FAILURE (news_fetcher.py from Plan 03 not yet landed; partial-Wave-2 detector fires as designed; will flip to PASS when Plan 03 commits)
4. AST inspection: `{'logging', 're', 'system_params'}` — clean

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None. news_filter.py is a pure-math classifier — no UI rendering, no data sources.

## Threat Flags

None beyond the plan's declared threat model:
- T-38-02-01 (DoS via regex): mitigated — `re.escape()` on every keyword + word-boundary anchors
- T-38-02-02 (false-positive tampering): accepted — precision ≥0.7 gate validates FP rate bounded
- T-38-02-03 (cross-market leakage): mitigated — exact-key `_PATTERNS.get(market_id)` lookup; unknown market_id returns False with warning

## Self-Check: PASSED

- `news_filter.py` — exists, 129 LOC ≤500, imports ⊆ {re, logging, system_params} (AST verified)
- `tests/test_news_filter.py` — exists, 14 named tests present (grep verified)
- `test_classifier_precision_recall` — present (grep verified)
- `test_classify_headline_unknown_market_logs_warning` — present (caplog, grep verified)
- Commits: 10e652e (Task 1 RED), fb6fafa (Task 2 GREEN) — both in git log
