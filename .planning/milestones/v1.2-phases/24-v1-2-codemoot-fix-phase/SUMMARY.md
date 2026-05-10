---
phase: 24
plan: PLAN
status: complete
---

# Phase 24: v1.2 Codemoot Fix Phase — Summary

## What was built

Fixed 3 bugs and 5 cleanup items from post-milestone codemoot review/security-audit/cleanup scans.

### Bugs Fixed

| ID | File | Fix |
|----|------|-----|
| BUG-01 | auth_store.py | Added `_ensure_aware()` helper to coerce naive datetimes to UTC before comparison — prevents `TypeError` crash when auth.json has timezone-naive timestamps |
| BUG-02 | main.py | Replaced `assert tzname == 'UTC'` with `raise RuntimeError(...)` — assert disabled by `python -O` |
| BUG-03 | main.py | `--once` mode now persists returned state with warnings from `_push_state_to_git` |

### Cleanup Done

| ID | File | Change |
|----|------|--------|
| CLEAN-01 | main.py | Removed dead `_SYMBOL_CONTRACT_SPECS` map |
| CLEAN-02 | main.py | Removed unused `import alert_engine` (specific imports from alert_engine remain) |
| CLEAN-03 | alert_engine.py | Removed unused `AlertLevel` type alias |
| CLEAN-04 | web/routes/totp.py | Deduplicated `_is_safe_next` — now imports from `web.routes.login` |
| CLEAN-06 | web/routes/reset.py | Deduplicated `_client_ip_from_request` — now imports `_get_client_ip` from `web.middleware.auth` |

### Intentionally Skipped

| ID | Reason |
|----|--------|
| CLEAN-05 | auth_store `_atomic_write` duplication — auth_store's import contract is "stdlib only" (hex peer of state_manager). Extracting adds module churn for 30 identical lines between peers that won't diverge. |
| CLEAN-07 | CDN URL duplication — intentional per locked CONTEXT D-07 decision. backtest/render.py explicitly documents this at line 16. |

## Self-Check: PASSED

- All 3 bugs addressed
- 5 of 7 cleanup items addressed (2 intentionally skipped with rationale)
- Test suite: 1691 passed (12 pre-existing failures in nginx/ruff tests unrelated to this phase)

## Key Files

### Modified
- auth_store.py (BUG-01)
- main.py (BUG-02, BUG-03, CLEAN-01, CLEAN-02)
- alert_engine.py (CLEAN-03)
- web/routes/totp.py (CLEAN-04)
- web/routes/reset.py (CLEAN-06)

## Commits
- `b8468a9` — fix(main): UTC scheduler guard, --once state persistence, dead code cleanup
- `bcf6393` — fix(phase-24): auth_store naive datetime crash, dead code cleanup, dedup _is_safe_next
- `3a89cc0` — fix(phase-24): dedup _get_client_ip in reset.py (CLEAN-06)
