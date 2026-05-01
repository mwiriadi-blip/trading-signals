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
