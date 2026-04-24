---
phase: 10
reviewers: [gemini, codex]
reviewed_at: 2026-04-24T00:00:00+08:00
plans_reviewed: [10-01-PLAN.md, 10-02-PLAN.md, 10-03-PLAN.md, 10-04-PLAN.md]
self_cli_skipped: claude
---

# Cross-AI Plan Review — Phase 10

## Gemini Review

This review covers the four implementation plans (**10-01** through **10-04**) for **Phase 10: Foundation — v1.0 Cleanup & Deploy Key**.

### Summary
The plans provide a comprehensive and technically sound roadmap for closing v1.0 carry-over items and pivoting the infrastructure from GitHub Actions (GHA) to a DigitalOcean (DO) droplet. The strategy is modular, respects the project's **hexagonal-lite architecture**, and ensures no regressions for the existing signal engine or state management logic. The addition of a nightly git-push mechanism correctly preserves state history in GitHub without relying on the now-retired GHA cron.

### Strengths
- **Defense-in-Depth:** Plan 10-01 fixes **BUG-01** at both the call-site (`main.py`) and the module boundary (`state_manager.py`), ensuring the `account` vs `initial_account` invariant is robust against future caller errors.
- **Architectural Integrity:** Plan 10-03 places the git-subprocess logic in the `main.py` orchestrator, keeping `state_manager.py` restricted to simple disk I/O and preserving the established hexagonal boundaries.
- **Invariant Preservation:** The "two-saves-per-run" rule (Phase 8 W3) is carefully maintained in Plan 10-03 by not adding a third save call during the git-push failure path.
- **Robust Error Handling:** The `_push_state_to_git` helper follows the "never-crash" pattern established by the email and dashboard components, using specific exception handling (`CalledProcessError`, `TimeoutExpired`) and `state_manager.append_warning` for visibility.
- **Operational Readiness:** Plan 10-04 includes a high-quality `SETUP-DEPLOY-KEY.md` runbook that proactively addresses tricky SSH pitfalls (e.g., `IdentitiesOnly`, `known_hosts` prompts, and `WorkingDirectory` requirements for systemd).

### Concerns
- **Invalid Email Format (LOW):** The research and Plan 10-03 use `droplet @trading-signals` (with a space) as the git author email. While git is flexible, standard RFC-compliant emails are preferred to avoid potential parsing issues in downstream git history tools.
  - *Mitigation:* The operator should confirm if this space is intentional; if not, `droplet@trading-signals` is recommended.
- **Local Import vs Exception Scope (LOW):** Plan 10-03 uses a local `import subprocess` inside the `try` block. While Python handles this correctly for the subsequent `except subprocess.CalledProcessError` clauses, it relies on the import succeeding before any git command is called.
  - *Analysis:* Since `subprocess` is stdlib, failure is highly unlikely, and the `except Exception` fallback provides safety. The pattern is consistent with `_send_email_never_crash`.

### Suggestions
- **Verification Window:** The success criterion SC-4 ("no cron fires for 2 consecutive weekdays") should be explicitly added to the operator's final checklist in `10-04-SUMMARY.md` to ensure the GHA retirement is verified in production.
- **Ruff JSON Schema:** Ensure the `test_ruff_clean_notifier` test (Plan 10-02) specifically asserts on the `code` field and not the entire object, as correctly noted in the research, to maintain compatibility across minor Ruff version bumps.

### Risk Assessment: LOW
The phase is well-scoped and avoids "big bang" changes. By renaming the GHA workflow to `.disabled` instead of deleting it, the plans provide a zero-cost rollback path. The logic changes are surgical, and the new infra wiring is covered by extensive mocking in the regression tests.

**Status: Approved. Ready for execution.**

---

## Codex Review

### 10-01-PLAN.md

**Summary:** Solid, low-risk bug-fix plan. It correctly implements the locked defense-in-depth approach for BUG-01 at both the orchestrator layer (`main.py::_handle_reset`) and the module boundary (`state_manager.reset_state`), and adds targeted regression coverage for both reset entry paths. Slightly over-specified, but the extra detail is mostly harmless.

**Strengths**
- Implements both locked fixes: D-01 and D-02.
- Preserves hex-lite boundaries; no I/O leaks into `state_manager`.
- Tests both CLI-flag and interactive reset paths, matching the actual bug surface.
- Backward-compat coverage for `reset_state()` default behavior.
- Scope tight to BUG-01.

**Concerns**
- `LOW`: More tests than the locked decision strictly requires (`1.0` edge case, "other fields unchanged" check). Mild scope expansion.
- `LOW`: Acceptance criteria rely on grep/string matching and exact trace text more than behavior. Can make execution noisy without improving confidence much.
- `LOW`: `_handle_reset()` mutates both fields after calling `reset_state()` instead of passing `initial_account` into `reset_state()`. Matches D-01/D-02, but leaves a slightly awkward double-source pattern.

**Suggestions**
- Prefer calling `state_manager.reset_state(initial_account=float(initial_account))` in `_handle_reset()` and then setting only `contracts`, unless the exact locked D-01 one-line shape must be preserved.
- Keep regression tests behavior-focused; drop nonessential grep-style acceptance checks if they slow execution.
- If keeping current shape, add a short comment in `main.py` explaining why both layers exist.

**Risk:** LOW — complete, aligned with locked decisions, unlikely to cause regressions.

### 10-02-PLAN.md

**Summary:** The cleanup portion is good, but the regression guard is under-specified relative to the phase requirements. Correctly identifies current `notifier.py` F401 set as 4 unused imports and removes them cleanly. The main issue is that the proposed test intentionally does **not** enforce `returncode == 0`, which conflicts with both D-05 and Success Criterion 2.

**Strengths**
- Correctly narrows scope to `notifier.py` only, matching D-06.
- Uses live repo reality: 4 F401s, not stale 19-count.
- Removal strategy is simple and appropriate; no over-engineering.
- Subprocess-based ruff test is a reasonable CI guard.

**Concerns**
- `HIGH`: The planned test explicitly avoids asserting `result.returncode == 0`, but D-05 says to assert both `returncode == 0` and zero `F401` entries. SC-2 also says `ruff check notifier.py` returns zero warnings. As written, the test would allow other lint failures in `notifier.py` and still pass.
- `LOW`: The "exactly 4 deleted lines" acceptance criterion is brittle if formatting changes.
- `LOW`: The manual "re-add SPI_MULT and ensure RED" verification is unnecessary ceremony for a tiny lint chore.

**Suggestions**
- Change `test_ruff_clean_notifier` to assert BOTH `result.returncode == 0` AND parsed JSON has zero F401 entries.
- Keep the JSON parsing but make the primary assertion the full clean pass — that's the actual phase contract.
- Drop the exact diff-stat requirement; behavior matters more than line count.

**Risk:** MEDIUM — the code change itself is low risk, but the planned test does not fully enforce the locked requirement, so the phase could be marked complete while still missing SC-2.

### 10-03-PLAN.md

**Summary:** The most important and riskiest plan in the phase. Largely preserves architecture correctly: git subprocess logic stays in `main.py`, failures do not crash the run, two-saves-per-run invariant is intentionally preserved. Main weaknesses: test coupling, one missing branch in coverage, a few implementation details more brittle than necessary.

**Strengths**
- Keeps git subprocess logic in `main.py`, preserving hex-lite boundaries.
- Correctly honors D-12: append warning, no extra `save_state()`.
- Hardcoded argv lists, no `shell=True`, explicit timeouts, explicit `state.json` scope.
- Reuses existing never-crash wrapper pattern.
- Covers important happy path and failure path behaviors.

**Concerns**
- `MEDIUM`: Plan does not test the weekend-skip exclusion path, even though D-15 explicitly says weekend-skip and `--test` must never reach `_push_state_to_git`.
- `MEDIUM`: Integration wiring tests call `main.main(['--force-email'])` and `main.main(['--test'])`, dragging in email dispatch and other side effects. More coupled than needed.
- `MEDIUM`: Local `import subprocess` inside `try` + typed `except subprocess.CalledProcessError` / `TimeoutExpired`. Probably works when import succeeds, but an unnecessarily fragile pattern for stdlib code.
- `LOW`: Log message says `git push failed` for any `CalledProcessError`, including possible `git commit` failure. Misleading for debugging.
- `LOW`: Plan inserts `_push_state_to_git` after dashboard rendering; D-08's locked flow describes `save_state()` then `_push_state_to_git()`. Functionally probably fine, but a small drift from the stated sequence.

**Suggestions**
- Add one explicit test proving weekend skip does not call `_push_state_to_git`.
- Test `run_daily_check()` directly for wiring instead of `main.main(...)` where possible.
- Prefer module-top `import subprocess`, or use generic `except Exception` plus type checks inside, unless the local-import pattern is non-negotiable.
- Split commit failure vs push failure logging, or log `git commit/push failed` generically with the command included.
- Keep the helper call immediately after `save_state()` for exact alignment with D-08.

**Risk:** MEDIUM — architecturally sound, but this is the phase's most failure-prone change and the test plan could be tighter around branch coverage and side-effect isolation.

### 10-04-PLAN.md

**Summary:** Mostly sound on workflow retirement and path-update work; the `SETUP-DEPLOY-KEY.md` runbook is well thought through. The biggest gap is documentation completeness: the plan updates `CLAUDE.md` and `.planning/PROJECT.md`, but it deliberately leaves some user-facing deployment docs stale.

**Strengths**
- Handles workflow retirement via rename, preserving rollback.
- Updates the centralized `WORKFLOW_PATH`, fixing the whole `TestGHAWorkflow` class.
- Deploy-key runbook includes the right operational details: SSH key, deploy key registration, SSH config, remote switch, host-key bootstrap, first-run validation.
- Security posture reasonable for ASVS L1: dedicated key, `IdentitiesOnly yes`, no secret material in repo.

**Concerns**
- `MEDIUM`: `docs/DEPLOY.md` and likely `README.md` remain operationally stale. Even if the broken badge is intentional, the deployment runbook still appears to describe the retired path.
- `MEDIUM`: Plan is tagged as addressing only `INFRA-03`, but also carries the operator runbook for D-14, which is part of INFRA-02. Traceability slightly muddy.
- `LOW`: Leaving the README badge untouched is defensible, but is a deliberate inconsistency that future readers may misread as neglected docs rather than intentional rollback preservation.
- `LOW`: Plan depends on 10-03 mainly for documentation linkage — acceptable but slightly stricter than necessary.

**Suggestions**
- Either update `docs/DEPLOY.md` in this plan or explicitly mark it deferred so the inconsistency is intentional and traceable.
- In summary/verification artifacts, call out that SC-4 is only partially automatable and needs operator confirmation after two weekdays.
- Consider a one-line note in README or PROJECT docs explaining the badge points to a retired workflow intentionally.

**Risk:** MEDIUM — workflow rename itself is low risk, but incomplete doc alignment can create rollout mistakes around deployment and rollback expectations.

### Overall

The plan set is generally strong and well-structured. Preserves architectural invariants, respects the "no third `save_state()`" rule, and splits work along sensible file boundaries. The main issues are: **10-02 does not fully enforce SC-2**, and **10-03 needs slightly better branch coverage and less coupling in wiring tests**.

**Highest-Priority Fixes**
- Make `10-02` assert `ruff check notifier.py` exits `0`, not just "no F401".
- Add a weekend-skip non-invocation test to `10-03`.
- Reduce `10-03` integration test coupling by exercising `run_daily_check()` directly.
- Decide explicitly whether `docs/DEPLOY.md` is in-scope for `10-04`; doc drift is the main rollout-quality gap.

---

## Consensus Summary

### Agreed Strengths
- **Hex-lite architecture preserved** (gemini + codex): git subprocess in `main.py`, `state_manager.py` stays I/O-narrow.
- **Phase 8 W3 two-saves invariant honored** (gemini + codex): no third `save_state()` on push failure path.
- **Defense-in-depth BUG-01 fix** (both reviewers): call-site + module-boundary layering in Plan 10-01.
- **SSH deploy-key runbook quality** (both reviewers): SETUP-DEPLOY-KEY.md covers the tricky SSH pitfalls.
- **Never-crash wrapper pattern reused correctly** (both reviewers): `_push_state_to_git` mirrors `_send_email_never_crash`.

### Agreed Concerns
- **🔴 HIGH — 10-02 test must enforce `returncode == 0`** (codex HIGH; gemini flags the same shape via "assert on code field"): the F401 test as drafted allows other lint errors to pass. Tighten before execute. This is the **#1 priority fix**.
- **🟡 MEDIUM — 10-03 test coverage gap for D-15 weekend/--test skip** (codex MEDIUM; implicitly acknowledged by gemini's verification-window note): add an explicit "weekend does not invoke `_push_state_to_git`" assertion.
- **🟡 MEDIUM — 10-03 local `import subprocess` pattern is fragile** (both reviewers, LOW-MEDIUM): codex recommends module-top import; gemini accepts the pattern as consistent with `_send_email_never_crash`. Plan 10-03 should document the choice, either by inlining the helper's rationale or by switching to a module-top import.

### Divergent Views
- **10-03 test coupling (`main.main` vs `run_daily_check`):** codex calls MEDIUM-risk over-coupling; gemini does not flag this. Worth resolving — the planner can either accept codex's suggestion or defend the current design.
- **Doc drift for `docs/DEPLOY.md` and README badge:** codex flags as MEDIUM (rollout-quality gap); gemini accepts the current Plan 10-04 Task 1 Step C explicit "leave badge as retired indicator" decision. The split is interpretive — the planner should decide whether `docs/DEPLOY.md` is in scope for Phase 10 or deferred.
- **Git author email `droplet@trading-signals`:** gemini flags LOW (possible parser issues); codex does not mention. Benign but worth a 5-second check — Plan 10-03 already uses the no-space form per D-10.

### Recommended Revision (if `--reviews` is run)
1. **[HIGH]** Tighten `test_ruff_clean_notifier` to assert `result.returncode == 0` AND zero F401 entries (addresses SC-2 gap).
2. **[MEDIUM]** Add `test_weekend_run_skips_push_state_to_git` (or equivalent) to Plan 10-03 (addresses D-15 coverage gap).
3. **[MEDIUM]** Plan 10-03: replace `main.main(...)` coupling with direct `run_daily_check()` invocation in wiring tests, or justify the coupling inline.
4. **[LOW]** Plan 10-04: resolve `docs/DEPLOY.md` scope — either add a task or add a Deferred-Ideas note in CONTEXT.md.
5. **[LOW]** Plan 10-03: split log message for commit-vs-push failure, or make the message generic (e.g. `'[State] git command failed (%s): %s'`).
6. **[LOW]** Plan 10-03: consider module-top `import subprocess` to simplify exception typing; if keeping local import, add a one-line rationale in the helper docstring.

Consensus risk: **LOW-MEDIUM**. Both reviewers approve execution contingent on the HIGH-severity 10-02 fix. The MEDIUM issues in 10-03 and 10-04 are test-coverage and doc-drift concerns — not blockers, but worth addressing via `/gsd-plan-phase 10 --reviews` before execute.
