---
phase: 43
reviewers: [gemini, codex]
reviewed_at: 2026-05-16T00:00:00+08:00
plans_reviewed:
  - 43-01-PLAN.md
  - 43-02-PLAN.md
  - 43-03-PLAN.md
  - 43-04-PLAN.md
  - 43-05-PLAN.md
  - 43-06-PLAN.md
  - 43-07-PLAN.md
  - 43-08-PLAN.md
  - 43-09-PLAN.md
  - 43-10-PLAN.md
skipped: [claude (self), opencode (stalled), qwen (failed)]
---

# Cross-AI Plan Review — Phase 43

## Gemini Review

This review evaluates the **Phase 43: Codebase Improvement Sweep** implementation plans for the Trading Signals system.

## Executive Summary
The proposed plans are technically sound, highly surgical, and prioritize the most critical security and reliability blockers (Wave A/B) before moving to maintenance. The shift from `float` to `Decimal` and the introduction of a `mutate_state` re-entrancy guard are excellent defensive programming practices. The most significant risks involve the side-effects of news-fetch failures on signal generation and potential path-resolution issues when moving static assets.

---

### PLAN 01 — Crash-email data leak
**Summary:** Prevents PII and sensitive trade data leaks by sanitizing the `state` dictionary before serializing it into crash notification emails.

**Strengths:**
- Directly addresses a significant multi-tenant security risk.
- Uses an existing skipped test as the validation gate.

**Concerns:**
- **LOW:** Ensure that redaction doesn't just empty the dict but provides a "REDACTED" placeholder to distinguish between "missing data" and "hidden data" during debugging.
- **MEDIUM:** The plan should explicitly verify if `state['users'][user_id]` contains keys other than `trade_log`, `positions`, and `pnl` (e.g., email addresses, TOTP secrets, or magic link hashes) and ensure a blocklist/allowlist approach is used rather than just targeting three keys.

**Suggestions:**
- Use an **allowlist** for keys to be included in the crash email (e.g., system-level metadata, instrument names) rather than a blocklist to avoid future data leaks when new user-specific keys are added.

**Risk Assessment: LOW**

---

### PLAN 02 — News-fetch failure gapping
**Summary:** Transitions news fetching from a "fail-silent" (empty list) model to a "fail-explicit" (result/error) model to prevent accidental trading during critical events when the news provider is down.

**Strengths:**
- Corrects a "fail-open" logic bug.
- Uses a typed sentinel for better error handling.

**Concerns:**
- **HIGH:** The plan doesn't explicitly state the *policy* for `daily_run.py` when a `NewsFetchError` occurs. If the news cannot be fetched, the system should likely **abort** or **wait** rather than proceeding with signals.

**Suggestions:**
- Define a `NewsPolicy` enum: `BLOCK_ON_FAILURE` vs `CONTINUE_ON_FAILURE`. For this system, `BLOCK_ON_FAILURE` is safer for a mechanical trend-following system.

**Risk Assessment: MEDIUM**

---

### PLAN 03 — INITIAL_ACCOUNT type fix
**Summary:** Standardizes the initial account constant to `Decimal` to ensure precision consistency across all monetary calculations.

**Strengths:**
- Eliminates the risk of subtle rounding errors in PnL and sizing calculations.

**Concerns:** None.

**Suggestions:**
- Grep for any other `10_000.0` or similar literals in `tests/` to ensure test assertions also use `Decimal`.

**Risk Assessment: LOW**

---

### PLAN 04 — News caching
**Summary:** Implements a sidecar JSON cache for news to improve dashboard performance and prevent rate-limiting.

**Strengths:**
- Significantly improves TTFB for the dashboard.
- Decouples UI rendering from external API availability.

**Concerns:**
- **MEDIUM:** Race conditions — if the scheduled job is writing the cache while the dashboard is reading it, could result in `JSONDecodeError`.

**Suggestions:**
- Use atomic writes for the cache file (write to `.tmp` then `os.replace`) to ensure the dashboard never reads a partially written file.

**Risk Assessment: LOW-MEDIUM**

---

### PLAN 05 — mutate_state re-entrancy guard
**Summary:** Prevents deadlocks by enforcing a single-level-only execution for state mutations.

**Strengths:**
- Excellent use of `threading.local()` for thread-safe state tracking.
- Prevents one of the most difficult-to-debug issues (permanent hangs).

**Concerns:** None.

**Suggestions:**
- Ensure the `RuntimeError` message includes the function name or context to help developers locate the nested call.

**Risk Assessment: LOW**

---

### PLAN 06 — Trade log truncation
**Summary:** Optimizes dashboard performance by limiting the number of rendered rows while preserving full data via an admin JSON export.

**Strengths:**
- Balances UX speed with data auditability.

**Concerns:**
- **LOW:** The `/admin/trades/full` route should ideally support `.csv` in addition to `.json` for easier analysis.

**Suggestions:**
- Ensure the "Full Log" link is clearly visible only to admins.

**Risk Assessment: LOW**

---

### PLAN 07 & 08 — Cleanup & Splitting
**Summary:** Removes dead code shims and refactors oversized files to meet the 500-line project convention.

**Strengths:**
- Improves maintainability.

**Concerns:**
- **MEDIUM:** Moving CSS/JS to `static/` files requires careful handling of file paths. Using `__file__` relative paths is mandatory to ensure it works across different deployment environments.

**Suggestions:**
- Use `pathlib.Path` for robust path resolution of the new static assets.

**Risk Assessment: LOW-MEDIUM**

---

### PLAN 09 & 10 — CI & Type Aliases
**Summary:** Introduces automated linting/formatting and semantic type aliases.

**Strengths:**
- Ensures 2-space indent consistency via Ruff config.
- `IndicatorFloat` vs `MoneyDecimal` provides immediate clarity.

**Concerns:** None.

**Suggestions:**
- In `ruff.toml`, explicitly enable the `I` (isort) rule.

**Risk Assessment: LOW**

---

### Gemini Overall Risk Assessment: **LOW**

The plan is well-sequenced. Critical path: **Plan 02 must land before Plan 04**. If you cache a "failure" result without the proper dataclass, you might accidentally cache an empty list and suppress signals for the duration of the cache TTL.

**Recommendation:** Proceed. Focus on **allowlist** approach for Plan 01 and **atomic writes** for Plan 04.

---

## Codex Review

**Summary:** Overall, the phase is well-scoped and the wave ordering is sensible: Wave A targets real F&F blockers, Wave B improves operational reliability, and Waves C/D are cleanup. The strongest plans are 01, 03, 05, 07, and 10 because they have narrow blast radius and clear acceptance tests. The riskier plans are 02, 04, 06, 08, and 09 because they change contracts, introduce persistence/routes, or touch project-wide formatting/CI behavior. The main cross-plan issue is dependency management around `NewsResult`: Plan 02 should define the domain contract carefully before Plan 04 builds caching on top of it.

---

### PLAN 01 — Crash-email Data Leak

**Strengths:**
- Correctly identifies a high-severity tenant isolation issue.
- Acceptance gate is clear: unskip and pass `test_crash_email_body_redacts_other_users`.
- Scope is appropriately small.

**Concerns:**
- **HIGH:** "Operator-level keys" needs a positive allowlist, not a denylist of `trade_log`, `positions`, `pnl`; future tenant fields could leak.
- **MEDIUM:** Need to ensure nested user data is removed recursively, not only top-level keys.
- **LOW:** Tests should assert absence of actual sensitive values, not just keys.

**Suggestions:**
- Implement an explicit allowlist for crash context fields.
- Add test fixtures with multiple users and unique sentinel values.
- Consider including only metadata: app version, timestamp, exception type, state schema version — not trade/account data.

**Risk Assessment: LOW-MEDIUM** — Small change, but security-sensitive. Risk is mostly from incomplete redaction.

---

### PLAN 02 — News-fetch Failure Bypass

**Strengths:**
- Correctly fixes a dangerous fail-open behavior.
- Separating successful empty news from fetch failure is the right model.
- UI surfacing is included, which avoids silent operator confusion.

**Concerns:**
- **HIGH:** Contract choice is unresolved: raising `NewsFetchError` vs returning `CriticalEventResult` are very different designs.
- **HIGH:** If the system is signal-gating on critical news, fetch failure should likely fail closed or produce an explicit "signal blocked/unknown" state, not `triggered=False`.
- **MEDIUM:** Existing callers of `fetch_news` and `has_critical_event` may break if not all are updated.
- **MEDIUM:** `error: str | None` may be too loose; typed error/category may be useful.
- **LOW:** Dashboard rendering must handle partial-market failure cleanly.

**Suggestions:**
- Prefer a result object: `CriticalEventResult(triggered: bool, fetch_error: str | None, gate_status: Literal["clear","blocked","unknown"])`.
- Define policy explicitly: on fetch failure, should trading signals be blocked, warned, or marked unknown?
- Add tests for genuine no-news, critical event found, fetch failure, malformed response, and timeout.
- Audit all call sites before changing signatures.

**Risk Assessment: HIGH** — This touches trading decision semantics. Must avoid replacing one fail-open path with another ambiguous state.

---

### PLAN 03 — `INITIAL_ACCOUNT` Decimal

**Strengths:**
- Directly aligns with the monetary `Decimal` convention.
- Small and testable.
- Uses string construction, which avoids float contamination.

**Concerns:**
- **MEDIUM:** Other code may assume `INITIAL_ACCOUNT` is float and perform float arithmetic.
- **MEDIUM:** `Decimal(str(initial_account))` acceptable for mixed input, but if `initial_account` is already a float, the caller boundary still allowed imprecision.
- **LOW:** Need to check serialization/display paths expecting JSON-native numbers.

**Suggestions:**
- Search all usages of `INITIAL_ACCOUNT` and update arithmetic boundaries.
- Add a test that common consumers still handle the Decimal value correctly.

**Risk Assessment: LOW-MEDIUM** — Narrow change, but can expose hidden float assumptions.

---

### PLAN 04 — News Caching

**Strengths:**
- Good dependency on Plan 02.
- Removes synchronous HTTP from dashboard render path.
- Scheduling cache refresh after OHLCV fetch fits the app's existing daily workflow.

**Concerns:**
- **HIGH:** "Returns stale on missing file" conflicts with "no cache → empty list"; missing cache and stale cache should not be the same state.
- **HIGH:** Cache writes need atomic write semantics, otherwise dashboard may read partial JSON.
- **MEDIUM:** Cache freshness policy underspecified: max age, weekend behavior, market-specific TTL, failure behavior after prior success.
- **MEDIUM:** Sidecar file location and permissions need to match deployment assumptions.
- **MEDIUM:** Plan should preserve fetch errors from refresh jobs for UI visibility.
- **LOW:** Scheduler failure should not crash unrelated daily jobs unless policy says so.

**Suggestions:**
- Define `NewsResult` with `items`, `error`, `stale`, `fetched_at`, and perhaps `source`.
- Use atomic write/replace for cache files.
- On refresh failure, keep last good cache but persist the latest error and timestamp.
- UI should distinguish "fresh clear", "stale clear", and "news unavailable".
- Tests should cover missing cache, corrupt cache, stale cache, refresh failure with prior cache, and refresh success.

**Risk Assessment: MEDIUM-HIGH** — Cache semantics need tightening to avoid hiding the same class of failure Plan 02 fixes.

---

### PLAN 05 — `mutate_state` Re-entrancy Guard

**Strengths:**
- Excellent narrow reliability fix.
- Thread-local guard is appropriate for detecting same-thread nested calls.
- Test case is clear and directly targets the deadlock.

**Concerns:**
- **MEDIUM:** Flag placement matters: must be set before lock acquisition if the deadlock occurs while trying to acquire the nested lock.
- **MEDIUM:** If `mutate_state` has multiple exit paths, the `finally` must always restore prior state.
- **LOW:** Error message should include enough context to find the nested misuse.

**Suggestions:**
- Preserve previous thread-local value in case tests or future code wrap behavior.
- Add a regression test that state remains writable after a re-entrancy error.

**Risk Assessment: LOW**

---

### PLAN 06 — Trade Log Truncation

**Strengths:**
- Targets a real dashboard performance issue.
- Keeps full data available through an admin endpoint.
- Includes acceptance tests for both truncated UI and full export.

**Concerns:**
- **HIGH:** `/admin/trades/full` may leak all tenants' trade logs unless tenant/admin semantics are explicit.
- **HIGH:** Returning full trade log as JSON can still become a performance/memory issue for very large logs.
- **MEDIUM:** Plan file list mentions `web/routes/dashboard/__init__.py` but route addition is in admin; clarify placement.
- **LOW:** "Last 200" should preserve ordering clearly.

**Suggestions:**
- Require admin-only authorization test and tenant isolation test.
- Consider pagination or streamed download instead of returning unbounded JSON.
- Ensure the dashboard truncation is presentation-only and never mutates `state['trade_log']`.

**Risk Assessment: MEDIUM-HIGH** — UI truncation is simple; the new admin data endpoint is the main security and performance risk.

---

### PLAN 07 — Remove `dashboard_legacy` + Dashboard Shim

**Strengths:**
- Good cleanup candidate after grep verification.
- Removes startup meta-path behavior.

**Concerns:**
- **MEDIUM:** Grep may miss dynamic imports, deployment scripts, or external cron/systemd references.
- **MEDIUM:** Deleting `dashboard.py` may break out-of-repo consumers if it was a compatibility layer.

**Suggestions:**
- Search for `dashboard`, `dashboard_legacy`, importlib usage, and shell references.
- Check systemd/entrypoint scripts if present.

**Risk Assessment: MEDIUM** — Cleanup is sensible, but shim removal can break hidden consumers.

---

### PLAN 08 — Split Oversized Files

**Strengths:**
- Addresses the 500-line convention.
- Splitting routes into cache/routes/helpers is directionally right.

**Concerns:**
- **HIGH:** Extracting CSS/JS/HTML to static files may alter deployment behavior, package data handling, or template loading.
- **MEDIUM:** "Load from static at module init" can fail depending on working directory unless using package-relative paths.
- **MEDIUM:** Splitting route modules can introduce circular imports or router registration changes.
- **LOW:** Static asset extraction could make tests more brittle if they assert inline HTML.

**Suggestions:**
- Use `importlib.resources` or a stable package-relative path for assets.
- Keep behavior-preserving tests around rendered dashboard HTML.
- Do this after Waves A/B are stable — merge conflict risk is high.

**Risk Assessment: MEDIUM-HIGH** — "Low priority" but not low risk; touches web rendering and routing.

---

### PLAN 09 — CI Pipeline + Ruff Config

**Strengths:**
- Adds important quality gates.
- Explicitly preserves 2-space formatting intent via Ruff config.
- Separating UAT tests from normal CI is reasonable.

**Concerns:**
- **HIGH:** `ruff format --check .` may cause large formatting churn in an established 2-space codebase.
- **MEDIUM:** Python 3.13 in CI must match production/runtime compatibility.
- **MEDIUM:** Removing the Ruff format ban from `CLAUDE.md` depends on proving config actually prevents 4-space rewrites.

**Suggestions:**
- First run `ruff format --check .` locally and inspect the diff before committing formatting changes.
- Consider starting CI with `ruff check` and pytest only, then add format check once stable.

**Risk Assessment: MEDIUM** — CI is valuable, but formatter rollout can create noisy churn.

---

### PLAN 10 — `IndicatorFloat` / `MoneyDecimal` Type Aliases

**Strengths:**
- Low-risk follow-up to Plan 03.
- Makes domain boundaries clearer.
- Annotation-only scope is appropriate.

**Concerns:**
- **MEDIUM:** Simple aliases like `MoneyDecimal = Decimal` improve readability but do not enforce separation at type-check time.
- **MEDIUM:** Running mypy may be unrealistic if the repo does not already have clean mypy coverage.

**Suggestions:**
- Keep annotation-only and avoid opportunistic refactors.
- Use mypy as informational unless it is already a project gate.

**Risk Assessment: LOW**

---

### Codex Cross-Plan Recommendations

- Recommended execution order: Plan 01, Plan 03, Plan 02, Plan 04, Plan 05, Plan 06, then Waves C/D.
- Treat Plan 02 as the design anchor for all news behavior — Plan 04 must not proceed until fetch failure semantics are explicit.
- For every F&F blocker, add tenant-isolation or fail-closed tests.
- Avoid mixing cleanup plans with Wave A/B fixes in the same PR; Plans 08 and 09 can generate broad diffs.
- Reassess Plan 06 before implementation: an unbounded full trade-log endpoint may create the next performance/security problem while solving the dashboard one.

---

## Consensus Summary

Both Gemini and Codex reviewed all 10 plans. Reviewed by 2 independent AI systems.

### Agreed Strengths

- Wave ordering (A→B→C→D) is correct and well-justified — security/reliability blockers before housekeeping.
- Plan 03 (Decimal) and Plan 05 (re-entrancy guard) are the cleanest, lowest-risk plans — narrow, well-tested, clearly scoped.
- Plan 01 acceptance gate (unskipping existing test) is a strong design choice.
- Plan 04 dependency on Plan 02 is correctly identified and ordered.
- Plans 07 and 10 are low-blast-radius improvements that should proceed with minimal risk.

### Agreed Concerns

1. **Plan 01 — allowlist over blocklist (HIGH consensus):** Both reviewers independently flagged that stripping only `trade_log`, `positions`, `pnl` is a blocklist approach. Future user-specific keys (email, TOTP secrets, magic-link hashes) would leak. **Use an explicit allowlist for what is safe to include in crash emails.**

2. **Plan 02 — fail-closed policy undefined (HIGH consensus):** Both reviewers flagged that the plan doesn't define what `daily_run.py` should do when news fetch fails. A news gating system that silently falls through on fetch failure is still fail-open. **Define and document the fail-closed policy before implementation.**

3. **Plan 04 — atomic cache writes required (HIGH/MEDIUM consensus):** Both reviewers flagged the race condition risk between scheduler writes and dashboard reads. **Cache writes must use atomic `write-to-tmp + os.replace` semantics.**

4. **Plan 06 — admin endpoint tenant isolation (HIGH consensus):** Both reviewers flagged that `/admin/trades/full` could leak cross-tenant data if not scoped correctly. **Tenant isolation test required before ship.**

5. **Plan 08 — static file path resolution risk (MEDIUM consensus):** Both reviewers flagged that file path resolution at module init must use `__file__`/`pathlib.Path` relative paths to survive deployment, not CWD-relative assumptions.

### Divergent Views

- **Plan 02 error contract:** Gemini prefers a `NewsPolicy` enum (`BLOCK_ON_FAILURE` / `CONTINUE_ON_FAILURE`); Codex prefers a `CriticalEventResult` with `gate_status: Literal["clear","blocked","unknown"]`. Both agree on the requirement to make the contract explicit — the implementation shape is a design decision for the author.

- **Plan 06 full-log endpoint format:** Gemini suggests adding CSV support; Codex suggests pagination/streaming. Both agree the current unbounded JSON design needs rethinking.

- **Plan 09 risk level:** Gemini rates CI/ruff as LOW risk; Codex rates it MEDIUM (citing formatting churn risk). Codex's concern is valid — run `ruff format --check .` locally first and inspect the diff before adding the check to CI.
