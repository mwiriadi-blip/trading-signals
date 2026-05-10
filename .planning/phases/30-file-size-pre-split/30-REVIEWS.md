---
phase: 30
reviewers: [gemini, codex, opencode]
reviewed_at: 2026-05-11T00:00:00+10:00
plans_reviewed: [30-01-PLAN.md, 30-02-PLAN.md, 30-03-PLAN.md, 30-04-PLAN.md, 30-05-PLAN.md, 30-06-PLAN.md, 30-07-PLAN.md]
---

# Cross-AI Plan Review — Phase 30

## Gemini Review

# Phase 30: File-Size Pre-Split — Cross-AI Plan Review

## Summary
The proposed plans for Phase 30 provide a systematic and risk-aware approach to refactoring the codebase to meet the 500-LOC limit (D-09) before multi-tenant features are introduced. The strategy of using "Wave 1" for parallel execution of surgical splits and "Wave 2" as a comprehensive integration gate is sound. The plans prioritize backward compatibility and test parity, specifically identifying critical re-exports and closure-capture constraints that could otherwise break the system. However, the dependency between `login.py` and `totp.py` and the potential for `dashboard.py`'s `register()` function to exceed the LOC limit even after splitting remain the primary technical hurdles.

## Strengths
- **Proactive Boundary Enforcement:** Plan 30-01 extends the AST blocklist *before* adding the new I/O modules, ensuring architectural integrity is maintained throughout the development of v1.3.
- **Strict Parity Requirements:** The requirement for byte-identical HTML output for the dashboard (Plan 30-03) and the 1880+ test suite pass (Plan 30-07) provides a high degree of confidence in the "behavior-preserving" claim.
- **Closure Awareness:** Plan 30-03 correctly identifies the risk of moving nested helpers that capture local state (closures) out of the `register()` function, which is a common pitfall in FastAPI route refactoring.
- **Future-Proofing:** Splitting `paper_trades.py` (Plan 30-06) despite it being currently under the cap is a wise tactical move to prevent merge conflicts during the upcoming `user_id` injection phase.

## Concerns

### 1. Parallel Dependency Race Condition (HIGH)
**Plans 30-04 and 30-05** run in the same Wave 1. `totp.py` has a hard dependency on `web.routes.login._is_safe_next`.
- **Risk:** If `login.py` is deleted and the new package directory `web/routes/login/` is not yet fully populated or indexed by the filesystem/Python interpreter, `totp.py` (or its split version) will fail to import.
- **Severity:** High (Broken builds during Wave 1).

### 2. Dashboard `__init__.py` Overflow (MEDIUM)
**Plan 30-03** notes that `dashboard.py` is 650 LOC and many helpers *must* stay inside `register()` due to closures.
- **Risk:** If the remaining logic in `register()` plus the module boilerplate exceeds 500 LOC, the split fails the D-09 requirement. The plan marks this as a "BLOCKER" but does not provide a remediation path (e.g., refactoring closures into a "DashboardContext" object or passing session state explicitly to `_renderers.py`).
- **Severity:** Medium (Potential for plan failure/stalling).

### 3. Missing Re-export for `_is_safe_next` (MEDIUM)
**Plan 30-05** mentions re-exporting `_is_safe_next` in `__all__`.
- **Risk:** If `totp.py` uses `from web.routes.login import _is_safe_next`, simply having it in `__all__` is sufficient, but if any internal code or tests use `web.routes.login._is_safe_next` via attribute access on the module object, the assignment in `__init__.py` must be explicit.
- **Severity:** Medium (Minor runtime/test failures).

### 4. Integration Gate Scope (LOW)
**Plan 30-07** (Integration Gate) is comprehensive but relies on manual "grep checks" for `web/app.py`.
- **Risk:** Human error in verifying import blocks.
- **Severity:** Low (Caught by subsequent test runs).

## Suggestions
- **Sequential Wave 1.1:** Move Plan 30-05 (`login.py` split) to a "Wave 1.0" or ensure it finishes before 30-04 (`totp.py` split) to guarantee that the `_is_safe_next` export surface is stable before the consumer is refactored.
- **Dashboard Contingency:** If `register()` in `dashboard.py` exceeds 500 LOC, consider refactoring the captured variables (`_session_secret`, etc.) into a small `State` dependency or a Pydantic `Context` object. This would allow the nested helpers to be moved to `_renderers.py` as pure functions, significantly thinning `__init__.py`.
- **Automated Export Validation:** In Plan 30-07, add a small script to iterate through a list of "Must-Have Symbols" and use `getattr(importlib.import_module('web.routes.X'), 'Y')` to verify that the split packages correctly re-export all legacy names.
- **Formatting Hygiene:** Ensure that the splitting process doesn't introduce trailing whitespace or line-ending changes that would invalidate the "byte-identical" success criterion for the dashboard.

## Risk Assessment
**Overall Risk: MEDIUM**

**Justification:** The plans are technically precise and respect the project's architectural constraints (D-09, AST guards). The "Medium" rating is driven by the **circular/cross-module dependencies** in the web routes and the **high density of the dashboard logic**. While the success criteria are strict (byte-identity), the lack of a defined refactoring path for the dashboard closures means that the 500-LOC goal might not be achievable through a simple "cut and paste" split alone. If the dashboard split hits the LOC blocker, it will require a more invasive architectural change than originally planned for this phase.

---

## Codex Review

**Summary**

The phase plan is generally sound: it isolates mechanical file splitting before semantic multi-tenant work, preserves package import surfaces, and adds the AST boundary guard early. The biggest risks are not architectural intent but execution ordering and parity verification. In particular, the parallel `login`/`totp` split has a real transient breakage risk, and `dashboard.py` may not actually fit under the 500 LOC cap if most closure-bound logic must remain inside `register()`. Plan 30-07 is a strong integration gate, but it should include a few sharper checks to prove handler identity/signature parity and dashboard byte parity rather than relying mostly on tests to imply them.

**Strengths**

- The phase goal is well scoped: behavior-preserving split first, multi-tenant semantics later.
- Package-per-route preserves caller imports such as `from web.routes import trades` and `trades.register(app)`.
- Re-export requirements are explicitly called out for known test and cross-route imports.
- Dashboard closure safety is correctly identified as a hard constraint, especially around session secret, serializer, and cookie attributes.
- Splitting `paper_trades.py` before it exceeds the cap is pragmatic and avoids noisy future diffs.
- Deriving `FORBIDDEN_MODULES_BACKTEST_PURE` from `FORBIDDEN_MODULES` avoids duplicated policy drift.
- Wave 2's "no source edits" gate is a good discipline: integration should expose defects instead of hiding them with opportunistic fixes.

**Concerns**

- **HIGH:** Parallel Wave 1 execution has a dependency hazard between `totp` and `login`. If Plan 30-04 lands before Plan 30-05 re-exports `_is_safe_next`, imports can fail during intermediate CI or branch integration.
- **HIGH:** Dashboard LOC overflow is acknowledged but not resolved. If `register()` plus imports/re-exports exceeds 500 LOC, the plan intentionally blocks, but that means Phase 30 may fail late unless measured before implementation.
- **HIGH:** "Same handler signature" is a success criterion, but Wave 2 only says public names are resolvable. It should explicitly compare route path/method/name/endpoint signatures before and after.
- **MEDIUM:** Byte-identical dashboard HTML is listed only for the dashboard route. Other route splits include render helper movement and should at least verify template/render parity through existing route tests or targeted snapshot checks.
- **MEDIUM:** Re-exporting private names such as `_is_safe_next`, `_D09_KEYS`, `_MULTIPLIER`, and `_COST_AUD` preserves compatibility, but `__all__` must not accidentally broaden the route package surface or omit currently imported private helpers.
- **MEDIUM:** Moving constants like `_AWST`, `_OPERATOR_CLOSE`, `_MULTIPLIER`, and `_COST_AUD` into `_models.py` or `_renderers.py` can create subtle import cycles if `register()` imports storage/service dependencies and helpers import back from `__init__`.
- **MEDIUM:** The AST blocklist addition to `FORBIDDEN_MODULES` should confirm whether blocking top-level `web` is too broad for any existing pure tests, fixtures, or type-check-only imports.
- **LOW:** `ruff check web/routes/` is useful but narrow. Import cycles and dead re-export issues may only show under full test import.
- **LOW:** Deleting legacy `.py` files and replacing them with same-named directories can expose packaging/cache issues in local environments. CI should run from a clean checkout.

**Plan-Specific Feedback**

**30-01 OPS-03 AST Blocklist**
- Sound and low risk.
- Add a test assertion that `FORBIDDEN_MODULES_BACKTEST_PURE >= FORBIDDEN_MODULES` or specifically contains the four new names via derivation.
- Confirm the import scanner normalizes `from web.routes...` to top-level `web`; otherwise blocking `web` may not catch all intended imports.

**30-02 Split `trades.py`**
- Good split boundary: models/exceptions/request parsing separate cleanly from render helpers and route registration.
- Watch `_build_position_dict`: if it touches persistence, request state, or formatting dependencies, `_models.py` may become a misleading home.
- Re-export all currently imported names, not only the two known Pydantic models. Use `rg "web.routes.trades"` before and after.

**30-03 Split `dashboard.py`**
- Correctly treats closure-capturing helpers as unsafe to move.
- The blocker condition is appropriate, but pre-measure it before making the split. If the resulting `__init__.py` is likely over 500 LOC, the coordinator should decide the decomposition upfront.
- If overflow occurs, a safer approved alternative may be dependency-injected helper factories, for example moving pure rendering functions that accept serializer/cookie/session dependencies explicitly. That should be treated as a design change, not an automatic split.

**30-04 Split `totp.py`**
- Main weakness is the Wave 1 dependency on `login`.
- Make Plan 30-04 explicitly depend on 30-05, or split `_is_safe_next` into a small shared auth/navigation helper first if that already matches local patterns.
- Be careful with `_log_totp_failure`: logging helpers sometimes depend on request/session/client IP context and may not be purely render-related.

**30-05 Split `login.py`**
- `_is_safe_next` re-export is security-critical. Add focused tests for unsafe absolute URLs, protocol-relative URLs, encoded redirects, blank values, and safe relative paths if they do not already exist.
- Ensure `_is_safe_next` behavior is byte-for-byte or assertion-for-assertion identical. This is not just compatibility; it is open-redirect protection.
- `_log_login_failure` in `_renderers.py` may be semantically odd. If it is not rendering-related, leave it in `__init__.py` unless moving it is necessary for LOC.

**30-06 Split `paper_trades.py`**
- Splitting now is justified despite being under cap.
- Constants used by `tests/test_system_params.py` are a smell, but preserving the import surface is the right move for this phase.
- Verify any D-09 key ordering remains stable if `_D09_KEYS` moves. Snapshot or exact-list tests should catch this.

**30-07 Integration Gate**
- Strong gate overall.
- Gate C should compare actual imports from `web/app.py`, not only grep strings. Grep can pass while semantics change.
- Gate D should include `inspect.signature()` checks for route handlers and known exported callables.
- Gate F is necessary but expensive; still appropriate for this phase because the whole point is behavior preservation.
- Add a clean-import gate from a fresh Python process for each package.
- Add an explicit dashboard fixture byte comparison command/artifact to Gate F or as its own gate, since it is a named success criterion.

**Suggestions**

- Make 30-04 depend on 30-05, or move `_is_safe_next` first in a tiny preparatory change.
- Add a preflight LOC projection for `dashboard/__init__.py` before editing.
- Define the exact export list for each new `__init__.py` from current `rg` results and module globals used by tests.
- Add an import-cycle check, either via tests or a simple clean-process import script.
- Extend Wave 2 Gate D to verify route path/method/endpoint/signature parity, not just name availability.
- Treat movement of security-sensitive helpers as pure relocation only; no cleanup, renaming, or behavior edits in this phase.
- Keep each `_renderers.py` limited to functions that render or format response content. Logging and validation helpers should stay near route logic unless moving them is required and tested.

**Risk Assessment**

Overall risk: **MEDIUM**.

The plan is directionally correct and well constrained, but it touches five live route modules in a shipped auth-sensitive app. Most risk comes from import surface regressions, route registration drift, private helper re-export omissions, and dashboard closure constraints. If the login/totp ordering is fixed and Wave 2 adds explicit route/signature/dashboard-byte parity checks, the residual risk drops closer to low-medium.

---

## OpenCode Review

## Phase 30 Cross-AI Plan Review

### 1. Summary

Solid, well-structured phase with clear Wave 1/2 separation. The package-per-file approach and D-01–D-12 decisions are sound. Five concerns below — none are blockers, but two (dashboard `__init__.py` overflow, totp↔login circular import) need a contingency path explicitly documented before execution begins.

---

### 2. Strengths

- **Wave 1 + Wave 2 gate pattern** is correct. Isolates the risky splits from integration verification; the hard STOP on gate failure prevents compounding defects.
- **D-01 `register(app)` pattern** preserves caller contracts byte-for-byte, keeping `web/app.py` import block stable.
- **D-10/D-11/D-12 derived set design** (`FORBIDDEN_MODULES_BACKTEST_PURE = FORBIDDEN_MODULES | frozenset({'pyarrow'})`) eliminates a common source of drift.
- **Paper_trades split before it's needed (D-09)** is pragmatic — injecting `user_id` into a 493-LOC file in Phase 31 would trigger another split cycle.
- **Test import surface audit** (Plan 30-06 correctly catching `_D09_KEYS`, `_MULTIPLIER`, `_COST_AUD`) shows the author traced actual test code rather than assuming.

---

### 3. Concerns

**HIGH — Dashboard `__init__.py` LOC overflow (Plan 30-03)**
`register()` body is ~500 LOC today. After extracting closure-free helpers to `_renderers.py`, `__init__.py` may still exceed the D-09 cap. The plan's fallback is "surface as BLOCKER" — but with no documented alternative decomposition. Need a pre-approved fallback (e.g., coordinator-approved exception to raise the cap for this single file, or an `_handlers.py` module that receives captured vars via explicit parameter).

**MEDIUM — totp ↔ login cross-import at package boundary (Plans 30-04, 30-05)**
`web/routes/totp/__init__.py` imports `_is_safe_next` from `web/routes/login`. Both run in parallel Wave 1. This works if and only if `login/__init__.py` is *fully evaluated* before `totp/`'s import statement executes. In CPython, package `__init__.py` runs to completion on first import. The risk is a *circular* dependency: if `login/__init__.py` (transitively) imports `web.routes.totp`, you get `ImportError`. The plan doesn't audit for this cycle. **Verify** that `login/__init__.py`'s import chain does not reach `web.routes.totp.*` before execution.

**MEDIUM — `'web'` in FORBIDDEN_MODULES may break existing tests (Plan 30-01)**
The plan asserts "Test passes immediately" but does not verify that `signal_engine` or `sizing_engine` lack `from web import ...` imports today. If any existing module uses `from web.routes.something import helper`, adding `'web'` to FORBIDDEN_MODULES will flag it. **Verify** via a dry-run grep before executing. If hits exist, decision is needed: carve out `'web.routes'` vs. `'web'` full-tree.

**LOW — No coverage parity check in Integration Gate (Plan 30-07)**
Gate F checks "1880+ tests green" but does not check coverage. A split can accidentally drop coverage. Add `pytest --cov=` threshold check as sub-gate F.2 or at minimum a human review of `diff --stat` coverage reports.

**LOW — `_is_stale_for` assumed closure-free (Plan 30-03)**
Plan says `_is_stale_for` is "module-level closure-free" but asserts this without reading the source. If `_is_stale_for` references `_session_secret` or any variable from `register()`'s closure scope, moving it to `_renderers.py` will raise `NameError` at runtime. The plan should state explicit verification steps before the move.

---

### 4. Suggestions

1. **Document dashboard overflow fallback.** Before executing Plan 30-03, write a one-paragraph contingency: if `__init__.py` > 500 LOC after extracting closure-free helpers, coordinator approves ONE of: (a) raise cap to 550 for this file only, or (b) move closure-capturing helpers to `_handlers.py` with explicit closure-parameter injection via `functools.partial` or a factory function.

2. **Add circular-import audit to Plan 30-07.** Gate C should also verify `python -c "from web.routes.totp import ..."` and `python -c "from web.routes.login import ..."` both resolve without `ImportError`. This catches the totp↔login cycle risk.

3. **Change Plan 30-01 execution order:** Add a pre-flight grep: `rg "from web[\. ]" signal_engine.py sizing_engine.py` to confirm `'web'` is safe in FORBIDDEN_MODULES.

4. **Add coverage gate.** Gate F already runs full suite. Run `diff --coverage-report` or at minimum `--coverage --junitxml` to compare line coverage before/after. A drop >1% is an automatic stop-and-review signal.

5. **Template path invariance.** After each split, verify `rg "TemplateResponse" web/routes/*/` shows the template name argument hasn't changed.

---

### 5. Risk Assessment

**Overall: LOW** — with one MEDIUM caveat

The phase is well-scoped and architecturally conservative. The **one MEDIUM risk** is the dashboard `__init__.py` overflow. If the ~500 LOC `register()` body overflows after extraction, the phase has no documented fallback. Pre-authorizing the contingency (suggestion #1) drops this to LOW.

---

## Consensus Summary

Phase 30 reviewed by 3 AI systems (Gemini, Codex, OpenCode). Claude skipped (running inside Claude Code).

### Agreed Strengths

- Wave 1 + Wave 2 gate pattern is correct and well-disciplined
- `register(app)` pattern preserved in `__init__.py` — caller contracts byte-for-byte stable
- Proactive AST blocklist extension (30-01) before v1.3 modules exist
- `FORBIDDEN_MODULES_BACKTEST_PURE` derived from base set eliminates policy drift
- Paper_trades pre-split (D-09) is pragmatic — prevents mid-refactor surgery in Phase 31
- Closure-capture constraint on dashboard correctly identified and enforced

### Agreed Concerns

1. **(HIGH — 3/3)** Dashboard `__init__.py` LOC overflow: `register()` is ~500 LOC by itself; after extraction of closure-free helpers the file may still violate the D-09 cap. Plan says "BLOCKER" but no pre-approved alternative decomposition exists. Must document contingency before execution.

2. **(HIGH/MEDIUM — 3/3)** totp↔login cross-import ordering in parallel Wave 1: `totp/__init__.py` imports `_is_safe_next` from `web.routes.login`. Both run in Wave 1 in parallel. Needs either (a) explicit dependency ordering (30-05 before 30-04), or (b) a circular-import audit confirming `login/__init__.py` doesn't transitively import `web.routes.totp`.

3. **(MEDIUM — 2/3)** `'web'` in FORBIDDEN_MODULES pre-flight: Plan 30-01 asserts test passes immediately but doesn't verify hex modules don't already import `web.*`. A pre-flight grep is needed before editing.

4. **(MEDIUM — 2/3)** Handler identity not explicitly verified in Wave 2: Gate D checks names are resolvable but doesn't compare route path/method/endpoint/signature parity before and after.

### Divergent Views

- **Overall risk rating:** Gemini says MEDIUM, Codex says MEDIUM, OpenCode says LOW (with MEDIUM caveat). Divergence centres on how likely the dashboard overflow is to actually trigger.
- **`_log_*` helper placement:** Codex questions whether `_log_login_failure` and `_log_totp_failure` belong in `_renderers.py` (semantically odd — not render-related); others don't flag this.
- **Coverage gate:** Only OpenCode recommends adding `pytest --cov` threshold check; others rely on test count parity.

### Recommended Pre-Execution Actions

1. Pre-measure `dashboard/__init__.py` LOC after a dry-run split and document the approved overflow fallback before Plan 30-03 executes.
2. Add explicit `depends_on: ["30-05"]` to Plan 30-04, or sequence login split first in a sub-wave.
3. Run pre-flight grep `rg "from web" signal_engine.py sizing_engine.py system_params.py backtest/` to confirm Plan 30-01 is safe before executing.
4. Extend Plan 30-07 Gate D to include route signature parity check (`inspect.signature` or equivalent).
