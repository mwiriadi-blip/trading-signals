# Phase 23 — Deferred Items

Issues discovered during plan execution that are out-of-scope for the
current plan. Track here for later triage; do NOT auto-fix.

---

## test_nginx_signals_conf.py::TestNginxConfStructure::test_listen_443_ssl

**Discovered during:** Plan 23-02 execution (data_fetcher)
**Status:** Pre-existing failure — confirmed via `git stash` baseline check
(failure persists with the worktree at base commit, before any 23-02 edits).
**Scope:** Unrelated to the backtest module — touches nginx deploy config tests.
**Action:** Surface to operator / next maintenance pass; do NOT fix in 23-02.

## Pre-existing failure observed during 23-03 execution

- `tests/test_nginx_signals_conf.py::TestNginxConfStructure::test_listen_443_ssl` fails on the worktree base commit (71b6494) before any 23-03 changes. Out of scope for Phase 23 BACKTEST work — log only.

## Pre-existing failures observed during 23-04 execution

Same 3 failures persist on the worktree base commit (26021b4) before any 23-04 changes. All unrelated to backtest/metrics.py:

- `tests/test_nginx_signals_conf.py::TestNginxConfStructure::test_listen_443_ssl` — nginx deploy config drift
- `tests/test_notifier.py::test_ruff_clean_notifier_detects_f401_regression` — notifier ruff regression
- `tests/test_setup_https_doc.py::TestCrossArtifactDriftGuard::test_owned_domain_placeholder_matches_nginx_conf` — HTTPS doc cross-artifact drift

Out of scope for Phase 23 metrics plan — log only.
