---
phase: 27
fixed_at: 2026-05-08T00:00:00Z
review_path: .planning/phases/27-code-quality-correctness-sweep-apply-2026-05-07-code-review-/27-REVIEW.md
iteration: 1
findings_in_scope: 15
fixed: 14
skipped: 1
status: partial
---

# Phase 27: Code Review Fix Report

**Fixed at:** 2026-05-08
**Source review:** .planning/phases/27-code-quality-correctness-sweep-apply-2026-05-07-code-review-/27-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 15 (1 Critical + 8 Warning + 6 Info — `--fix all`)
- Fixed: 14
- Skipped: 1

**Verification:** full suite `python -m pytest tests/` → 2028 passed in 152s.

## Fixed Issues

### CR-01: notifier.py monolith and notifier/ package coexist post-split

**Files modified:** `notifier.py` (deleted), `tests/test_html_xss_audit.py`, `tests/test_http_timeouts.py`, `tests/test_entry_side_cost.py`, `tests/test_instrument_regex.py`, `tests/test_notifier.py`, `tests/test_secret_redaction.py`, `tests/test_signals_email_to_required.py`, `tests/test_setup_https_doc.py`, `tests/test_signal_engine.py`
**Commits:** 5a3ada6 (test re-points) + 838f15e (file deletion)
**Applied fix:** Deleted the 2195-line `notifier.py` monolith. Re-pointed every grep / AST gate / read-bytes test that named `notifier.py` to scan `notifier/*.py` instead — XSS escape-count aggregation, `_RESEND_TIMEOUT_S` deletion gate, `(5, HTTP_TIMEOUT_S)` source check, ruff CI gate (`ruff check notifier/`), forbidden-imports parametrize, secret-redaction grep gate, hardcoded-email scan, `SIGNALS_EMAIL_FROM` env-var read assertion. The shipping code path (`notifier/`) is now the single source of truth and is what every structural test gate validates.

### WR-01: Phase 27 #7 entry-side-cost helper adoption gate too narrow

**Files modified:** `web/routes/paper_trades.py`, `web/routes/trades.py`, `dashboard_renderer/stats.py`, `tests/test_entry_side_cost.py`
**Commit:** 402ee38
**Applied fix:** Routed all 3 production sites that split round-trip cost in half through `pnl_engine.entry_side_cost(rt_cost)` (local imports per planner D-19). Extended `tests/test_entry_side_cost.py::PROD_FILES` to include the 3 new paths so the AST `cost / 2` BinOp gate enforces the single source of truth on the persistence + display paths, not just on the engines.

### WR-02: Bare-int signal defensive branches survive past v10 migration

**Files modified:** `state_manager.py` (docstring only)
**Commit:** 1caf9de
**Applied fix:** Took option B from the review (relax invariant, document scope) — NOT option A (delete branches). Reason: option A was tried first and red-lit 11 existing tests including `tests/test_notifier.py::TestDetectSignalChanges::test_detect_legacy_int_signal_shape` which explicitly pins bare-int support, plus golden-email comparisons whose fixtures (`tests/fixtures/notifier/empty_state.json`) feed bare-int signals directly without flowing through `load_state()`. Updated `_migrate_v9_to_v10` docstring to clarify that the dict-only invariant applies to the production read path (everything that hits `load_state`) but is intentionally relaxed on the test read path (fixtures that bypass migration). Listed the specific call sites that retain the lenient `isinstance(raw, int)` branch by design.
**Note:** Marked `fixed: requires human verification` — semantic decision (lenient vs strict). If the project later updates fixtures to dict shape, the branches in `notifier/formatters.py`, `dashboard_legacy/calc_rows.py`, `daily_run.py`, `crash_boundary.py` should be removed and a `TestRendererDefensiveIntBranchRemoved`-style pin extended.

### WR-03: state_manager docstring states MAX_WARNINGS = 100 (drift)

**Files modified:** `state_manager.py`
**Commit:** 8600ba1
**Applied fix:** Updated `append_warning` docstring rationale block: 100 → 50, "5 months" → "~7 weeks", "50+ warnings in one run still fits" → "25+ warnings in one run fills half the bound". Now matches `system_params.MAX_WARNINGS = 50` (Phase 27 #16 review-fix agreed-4).

### WR-04: SPI/AUDUSD multiplier constants duplicated in web/routes

**Files modified:** `tests/test_system_params.py`
**Commit:** 7c183ca
**Applied fix:** Added `TestPaperTradeRouteConstantsParity` class with two tests asserting `web.routes.paper_trades._MULTIPLIER == {SPI_MULT, AUDUSD_NOTIONAL}` and `_COST_AUD == {SPI_COST_AUD, AUDUSD_COST_AUD}`. The header comment in the route file already promised "If system_params changes, update here and bump tests" — this commit is the bump-test gate that makes the promise enforceable.

### WR-05: paper_trades_section row.get('id', '') → html.escape type fragility

**Files modified:** `dashboard_legacy/paper_trades_section.py`, `tests/test_dashboard.py`
**Commit:** 26cb153
**Applied fix:** Changed `trade_id = row.get('id', '')` → `trade_id = str(row.get('id', '') or '')` at both open-trades (line 142) and closed-trades (line 251) loops; same coercion for `instrument` field. Added `test_open_table_handles_non_str_trade_id` covering both `None` and `int` row['id'] / row['instrument'] — these would have raised `TypeError` from `html.escape` pre-fix.

### WR-06: stale notifier.py:1423 fixture reference

**Files modified:** `tests/test_crash_email_fallback.py`
**Commit:** 708129a
**Applied fix:** Replaced the literal `'  File "notifier.py", line 1423\n'` traceback fixture with `'  File "<test-fixture>", line 1\n'` — both because the monolith was deleted in CR-01 and because the original line number never matched the package layout.

### WR-07: dashboard_legacy/section_renderers.py equity-chart label hardening

**Files modified:** `dashboard_legacy/section_renderers.py`
**Commit:** 97947a1
**Applied fix:** Switched `json.dumps(..., ensure_ascii=False, ...)` → `ensure_ascii=True` on the equity-chart payload assembly. ASCII-only output forces `\uXXXX` escaping for U+2028 / U+2029 (JS line-terminator characters that some parsers treat as ending a string literal inside `<script>`). Updated docstring Pitfall 1 to document the dual defence (`</` scrub + ensure_ascii line-sep escaping).

### WR-08: dashboard_renderer/components/signals.py redundant isinstance check

**Files modified:** `dashboard_renderer/components/signals.py`
**Commit:** 8f74562
**Applied fix:** Collapsed `trace_sig_dict = sig_entry if isinstance(sig_entry, dict) else {}` → `trace_sig_dict = sig_entry or {}`. Safe because the renderer's `TestRendererDefensiveIntBranchRemoved` test pin already guarantees no bare-int sig_entry can reach this code path post-v10 migration; the `or {}` collapses both `None` and any unexpected falsy shape.

### IN-01: NaN check via self-inequality is opaque

**Files modified:** `paper_trade_alerts.py`, `notifier/templates_alerts.py`
**Commit:** 6b4770e
**Applied fix:** Added `import math` to both files; replaced `if x != x:` (3 sites) with `if math.isnan(x):`. Same behavior, standard idiom.

### IN-02: state_manager module docstring fcntl reentrancy claim stale

**Files modified:** `state_manager.py`
**Commit:** 8fd5d5c
**Applied fix:** Updated module docstring "fcntl.flock is reentrant within a single process" to match the corrected `_atomic_write` docstring: flock locks the open-file-description, NOT the inode/path; two fds in the same process do NOT share lock ownership; the inner `save_state` must call `_atomic_write_unlocked` when the outer `mutate_state` already holds the lock.

### IN-03: notifier/__init__.py CLI logging.basicConfig may double-init

**Files modified:** `notifier/__init__.py`
**Commit:** 3f2f8e4
**Applied fix:** Added `force=True` to the `logging.basicConfig(level=logging.INFO, format='%(message)s')` call inside `_cli_main()`. Matches the `main.py:100` convention; without it the call is a silent no-op when logging was already configured by an importing process.

### IN-04: dashboard_legacy/__init__.py 150-line re-export shim

**Files modified:** `dashboard_legacy/__init__.py`
**Commit:** 3ca2947
**Applied fix:** Verified via `grep -rn "from dashboard_legacy import"` that no caller relies on the package-level re-exports — every consumer imports from `dashboard_legacy.<submodule>` directly. Reduced `__init__.py` to a docstring-only file.

### IN-06: scheduler_driver.py imports time inside function body

**Files modified:** `scheduler_driver.py`
**Commit:** adc470b
**Applied fix:** Hoisted `import time` from inside `_get_process_tzname()` to the module top-level imports block, alongside `logging`. The local-import idiom was cargo-culted from the never-crash wrappers; this is a plain test seam, not a never-crash wrapper.

## Skipped Issues

### IN-05: paper_trades.py _D09_KEYS frozenset defined but never referenced

**File:** `web/routes/paper_trades.py:66-70`
**Reason:** skipped: the review's grep was incomplete. `_D09_KEYS` IS referenced in `tests/test_web_paper_trades.py:166-173` (`from web.routes.paper_trades import _D09_KEYS`) as the row-shape contract. The constant is the test fixture's source of truth, not dead code. Deleting it would red the row-shape contract test, which is the opposite of the review's intent.
**Original issue:** Constant defined but never referenced — review classified as dead code.

---

_Fixed: 2026-05-08_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
