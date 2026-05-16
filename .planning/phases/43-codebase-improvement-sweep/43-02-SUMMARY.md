---
phase: 43-codebase-improvement-sweep
plan: "02"
subsystem: news-gating
tags: [news, fail-closed, gate, D-02, security]
dependency_graph:
  requires: []
  provides: [NewsResult, CriticalEventResult, BLOCK_ON_FAILURE-policy]
  affects: [news_fetcher, news_filter, daily_run, dashboard_renderer]
tech_stack:
  added: [dataclasses.dataclass, typing.Literal]
  patterns: [fail-closed gate, typed error reasons, structured result types]
key_files:
  created: []
  modified:
    - news_fetcher.py
    - news_filter.py
    - daily_run.py
    - dashboard_renderer/components/news.py
    - dashboard_renderer/components/signals.py
    - tests/test_news_fetcher.py
    - tests/test_news_filter.py
    - tests/test_integration_f1.py
    - tests/test_web_news_dashboard_integration.py
decisions:
  - "NewsResult frozen dataclass wraps fetch_news return — never a bare list (D-02)"
  - "CriticalEventResult gate_status: clear/blocked/unknown drives BLOCK_ON_FAILURE"
  - "news.py wraps filtered list into NewsResult at render time (no architecture change)"
  - "test_integration_f1: monkeypatch fetch_news to clear result so F1 chain proceeds"
metrics:
  duration: ~25min
  completed: "2026-05-16"
  tasks: 1
  files: 9
---

# Phase 43 Plan 02: Fail-Closed News Gating Summary

**One-liner:** NewsResult + CriticalEventResult dataclasses enforce fail-closed BLOCK_ON_FAILURE policy — fetch failure blocks signals via gate_status='unknown'.

## What Was Built

### Task 1: Fail-closed news gating (D-02)

Resolved the Gemini/Codex design debate by adopting Codex's `CriticalEventResult` shape AND Gemini's explicit `BLOCK_ON_FAILURE` policy in `daily_run.py`.

**news_fetcher.py — NewsResult dataclass:**
- `NewsResult(items, error, fetched_at)` frozen dataclass added
- `fetch_news` now returns `NewsResult` — never a bare list, never raises
- Typed error reasons: `"timeout"`, `"network_unreachable"`, `"parse_error"` (T-43-05: no raw exception text surfaced)
- `ReadTimeout` → `"timeout"`, `ConnectionError` → `"network_unreachable"`, other → `"parse_error"`

**news_filter.py — CriticalEventResult dataclass:**
- `CriticalEventResult(triggered, fetch_error, gate_status)` frozen dataclass added
- `has_critical_event(result: NewsResult, market_id: str) -> CriticalEventResult`
- Mapping: `error is not None` → `gate_status="unknown"`, keyword match → `"blocked"`, no match → `"clear"`

**daily_run.py — BLOCK_ON_FAILURE policy:**
- `_NEWS_FAIL_POLICY = 'BLOCK_ON_FAILURE'` module constant
- News gate check inserted in per-symbol loop before signal generation (step 3.c.ii)
- `gate_status in ('blocked', 'unknown')` → `continue` (skip signal generation)
- Skip recorded in `state['news_gate_skips']` for dashboard surfacing

**dashboard_renderer/components/news.py:**
- Imports `NewsResult` from `news_fetcher`
- Wraps filtered headlines list in `NewsResult(items=filtered, error=None)` at render time
- `has_critical_event` called with `NewsResult`, extracts `.triggered` for banner

**dashboard_renderer/components/signals.py:**
- Handles `NewsResult` return from `fetch_news`
- Extracts `.items` for news panel rendering
- Logs non-clear `gate_status` at WARNING level

**Tests — 14 new tests:**
- `test_news_fetcher.py`: `test_fetch_news_returns_newsresult`, 5 new D-02 cases (genuine-no-news, critical-event-found, timeout, connection-error, malformed), `test_has_critical_event_returns_unknown_on_fetch_error`, `test_daily_run_skips_signals_when_gate_status_unknown`
- `test_news_filter.py`: `test_has_critical_event_returns_unknown_on_fetch_error`, `test_has_critical_event_unknown_on_network_error`, `test_has_critical_event_clear_on_successful_no_news` + updated existing 4 tests to new API
- Updated `test_integration_f1.py`: monkeypatch `news_fetcher.fetch_news` → `NewsResult(error=None)` so F1 chain proceeds without gate blocking
- Updated `test_web_news_dashboard_integration.py`: monkeypatch returns `NewsResult`

## Acceptance Criteria Verification

- `grep -n "class NewsResult" news_fetcher.py` → line 63 (1 match)
- `grep -n "class CriticalEventResult" news_filter.py` → line 43 (1 match)
- `grep -nE "gate_status.*unknown" news_filter.py` → lines 144, 155, 160 (≥1 match)
- `grep -n "BLOCK_ON_FAILURE" daily_run.py` → lines 42, 44, 247, 257 (≥1 match)
- `grep -n "return \[\]" news_fetcher.py` → 0 matches (no bare list returns)
- Full suite: 2413 passed, 0 failed

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Integration test cascade — fetch_news gate blocked F1 chain**
- **Found during:** Full suite run
- **Issue:** `test_integration_f1.py` uses `_T` fake ticker without `.news` attribute; news gate correctly triggered `parse_error` → `gate_status='unknown'` → SKIP signals → email missing FLAT labels
- **Fix:** Added `monkeypatch.setattr(_nf, 'fetch_news', lambda *_a, **_kw: _clear_result)` in `_setup_f1()` so the integration test's fake yfinance boundary doesn't hit the live news gate
- **Files modified:** `tests/test_integration_f1.py`
- **Commit:** c508c2a

**2. [Rule 2 - Missing critical functionality] `news.py` render-time NewsResult wrapping**
- **Found during:** Implementation of `has_critical_event` signature change
- **Issue:** `dashboard_renderer/components/news.py` receives a pre-filtered list but `has_critical_event` now takes `NewsResult`
- **Fix:** Wrapped filtered list in `NewsResult(items=filtered, error=None)` at render time — no architecture change, preserves D-02 contract
- **Files modified:** `dashboard_renderer/components/news.py`
- **Commit:** c508c2a

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes at trust boundaries introduced. The `news_gate_skips` key added to `state` is transient metadata (not persisted to state.json via `mutate_state` — written to in-memory accumulator only, replayed by `_apply_daily_run` if present). T-43-04 (BLOCK_ON_FAILURE policy) and T-43-05 (typed error reasons, no raw exception text) both mitigated per plan threat model.

## Known Stubs

None — all data flows wired. `news_gate_skips` in state is populated on skip and will surface to the dashboard in a future plan.

## Self-Check: PASSED

- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/.claude/worktrees/agent-ac33a0b3c59281c4b/news_fetcher.py` — NewsResult class at line 63
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/.claude/worktrees/agent-ac33a0b3c59281c4b/news_filter.py` — CriticalEventResult class at line 43
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/.claude/worktrees/agent-ac33a0b3c59281c4b/daily_run.py` — BLOCK_ON_FAILURE constant and gate check
- Commit c508c2a verified: `git log --oneline -1` → `c508c2a feat(43-02): ...`
- Full suite: 2413 passed, 0 failed
