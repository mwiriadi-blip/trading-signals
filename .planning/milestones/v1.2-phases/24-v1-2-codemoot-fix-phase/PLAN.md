# Phase 24: v1.2 Codemoot Fix Phase

**Goal:** Fix verified bugs and cleanup items from post-milestone codemoot review/security-audit/cleanup scans.

## Bugs (from review --focus all)

### BUG-01: auth_store.py — naive datetime comparison crash
**File:** auth_store.py, lines ~420, ~446, ~471
**Problem:** `datetime.fromisoformat()` can return a naive datetime when auth.json has timestamps without timezone info. Comparing naive vs aware `datetime.now(timezone.utc)` raises `TypeError`. The comparison is OUTSIDE the try block so it crashes the function.
**Fix:** Wrap each `fromisoformat` + comparison in a try/except, or ensure the parsed datetime is always made aware (`.replace(tzinfo=timezone.utc)` if naive).

### BUG-02: main.py — UTC scheduler guard uses assert
**File:** main.py, line ~700
**Problem:** `assert tzname == 'UTC'` is disabled by `python -O`. Production safety check must not use assert.
**Fix:** Replace with `if tzname != 'UTC': raise RuntimeError(f'Scheduler requires UTC, got {tzname}')`.

### BUG-03: main.py — --once mode doesn't persist post-push warnings
**File:** main.py, line ~1884
**Problem:** `run_daily_check()` returns updated state with warnings from `_push_state_to_git`, but `--once` path discards returned state (`_state`) and never saves. Warnings are lost.
**Fix:** After `run_daily_check` returns in `--once` mode, persist returned state if it contains new warnings (or always do a final save).

## Cleanup (from codemoot cleanup)

### CLEAN-01: Dead code — `_SYMBOL_CONTRACT_SPECS` (main.py:82)
Delete unused contract spec map.

### CLEAN-02: Dead code — `import alert_engine` (main.py:43)
Remove unused module-level import (direct imports `compute_alert_state`, `compute_atr_distance` are used instead).

### CLEAN-03: Dead code — `AlertLevel` literal alias (alert_engine.py:24)
Remove unused `AlertLevel` type alias.

### CLEAN-04: Duplicate — `_is_safe_next` in totp.py
**File:** web/routes/totp.py:107
Duplicates `web/routes/login.py:_is_safe_next`. Extract to shared utility or import from login.

### CLEAN-05: Duplicate — atomic write in auth_store.py
**File:** auth_store.py:112
Duplicates `state_manager.py` atomic write. Import from state_manager or extract shared helper.

### CLEAN-06: Duplicate — `_get_client_ip` in reset.py
**File:** web/routes/reset.py:216
Duplicates `web/middleware/auth.py:_get_client_ip`. Import from middleware.

### CLEAN-07: Hardcoded — CDN URL duplication
**File:** dashboard.py:115 and backtest/render.py
Chart.js CDN URL duplicated. Extract to constant in system_params.py or a shared config.

## Not fixing (intentional/low-risk)

- **auth_store.py TOCTOU on consume/rate-limit:** Single-user app, no concurrency risk.
- **Hardcoded recovery email:** Operator's own email, intentional default.
- **.env secret:** Already gitignored; operator responsibility.
- **python-dotenv CVE:** We don't use vulnerable `set_key`/`unset_key` functions.
