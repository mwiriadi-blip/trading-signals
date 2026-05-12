---
phase: 32
reviewers: [gemini, codex]
reviewed_at: 2026-05-12T00:00:00+10:00
plans_reviewed: [32-01-PLAN.md, 32-02-PLAN.md, 32-03-PLAN.md, 32-04-PLAN.md]
---

# Cross-AI Plan Review — Phase 32: Dashboard Legacy Retirement

---

## Gemini Review

This is a comprehensive and technically rigorous implementation plan. The phased "Wave" approach correctly prioritizes logic migration before addressing the circular dependency "knot" and finally performing the cutover.

### Summary

The plan to retire `dashboard_legacy/` is exceptionally well-structured, demonstrating a deep understanding of the project's specific constraints (500 LOC cap, hex-lite boundaries, and XSS gates). By identifying the `shell.py` dead-code trap early and planning a surgical `ImportError` stub for the legacy directory, the strategy ensures that the transition is not just a "move" but a "cleanup" that hardens the system against regression.

### Strengths

- **Audit-First Logic Migration:** Decision D-03 (audit unique functions) prevents bloating the new renderer with redundant legacy code.
- **Dead Code Identification:** Recognizing that `shell.py` contains dead code while the legacy `page_body.py` holds the active shell logic is a critical catch that prevents a "broken layout" failure.
- **Stub Implementation:** The use of `__path__ = []` combined with `__getattr__` is an elegant, load-bearing solution to ensure consistent `ImportError` behavior, preventing the confusion of `ModuleNotFoundError` during the transition.
- **Acyclic Import Strategy:** Wave 3 dedicated specifically to untangling `import dashboard as d` is the correct way to handle Python's circular import issues in a refactor of this scale.
- **Test Gate Awareness:** Explicitly identifying the need to retarget `os.replace` patches in tests prevents the "vacuous pass" risk (where a test passes because it's patching a location no longer in use).

### Concerns

- **[MEDIUM] LOC Cap Pressure:** `components/positions.py` is projected at ~363 LOC after absorbing ~347 LOC from the legacy module. While under 500, the addition of imports and potential helper functions makes this a high-risk file for triggering the AST gate during future edits.
- **[LOW] Shim vs. Retargeting Ambiguity:** Success Criterion 3 describes `dashboard.py` as a "shim," but Decision D-05 states there will be "no backward-compat re-export layer." If all callers are retargeted in Wave 4, `dashboard.py` is less of a shim and more of a "deprecated shell" for logging continuity. This terminology might lead to confusion during implementation.
- **[LOW] Journalctl Continuity:** Finding 6 mentions keeping the 'dashboard' logger name in `dashboard.py`. If logic moves to `dashboard_renderer`, ensure the logger names used in those new modules (which the plan suggests changing to `__name__`) won't fragment the log history in a way that breaks existing monitoring/alerts.

### Suggestions

- **Pre-emptive Split for Positions:** Given the 500 LOC cap, consider splitting `components/positions.py` during Wave 2 into `components/positions_table.py` and `components/positions_forms.py` proactively, rather than waiting for overflow.
- **Logger Name Override:** To maintain journalctl continuity, consider explicitly naming loggers in `dashboard_renderer` modules as `logging.getLogger('dashboard.renderer.xxx')` rather than `__name__`, or ensure the root 'dashboard' logger is configured to capture all sub-module output.
- **Verify `main.py` entry points:** The plan focuses on `web/routes`. Ensure that `daily_run.py` or any CLI-based dashboard generators (like `regenerate_dashboard_golden.py`) are explicitly included in the Wave 4 retargeting task.

### Risk Assessment

**LOW.** The risk is low because the plan relies on a **byte-identity gate** (`TestGoldenSnapshot`). Since the output must be identical to the baseline, any logic errors during the porting process will be caught immediately. The clear dependency ordering (Waves 1-4) ensures the workspace remains in a runnable state between steps.

---

## Codex Review

### Summary

The phase plan is directionally strong: it identifies the real architectural problem, separates migration into sensible waves, preserves byte-identity as the primary behavioral gate, and explicitly handles the most dangerous risks: circular imports, dead shell code, `dashboard_legacy` retirement semantics, and the `os.replace` test patch trap. The largest risk is not the target architecture but migration correctness: many private underscore helpers are being moved across modules while preserving exact HTML output, escaping behavior, import boundaries, and test semantics. The plan is achievable, but it needs tighter pre/post inventories, explicit import-contract checks, and stronger golden fixture coverage around every absorbed legacy surface.

### Plan 32-01 Review

**Strengths:**
- Starts with the right modules: `render_helpers`, `section_renderers`, and `page_body` are foundational and likely unblock later component absorption.
- Correctly calls out that `dashboard_renderer/shell.py::render_html_shell` is dead code and must be replaced, not extended.
- Preserving underscore-prefixed names reduces churn and lowers risk for tests and internal callers.
- Audit-first migration is a good guard against duplicating thin wrappers or reviving obsolete logic.
- Test gate includes golden snapshots, XSS AST audit, and hex-boundary determinism.

**Concerns:**
- **[HIGH] "7 unique" functions from `render_helpers.py` needs a locked symbol inventory.** If this count is wrong, later waves may silently depend on missing helpers.
- **[HIGH] Replacing shell composition is likely the highest byte-identity risk in the phase.** Whitespace, attribute order, escaping, and conditional empty-state behavior can drift easily.
- **[MEDIUM] `components/header.py` may exceed its natural responsibility** if section-level nav/session-note logic is absorbed there without clear boundaries.
- **[MEDIUM] The `_render_page_body` annotation fix is mentioned in research but not explicitly listed as a Wave 1 task step**, even though `page_body.py` is absorbed here. (Note: the plan does reference this in the interfaces block — but it's worth making it an explicit task.)
- **[LOW] The test gate references `tests/test_signal_engine.py::TestDeterminism::test_dashboard_no_forbidden_imports`**; pytest selection syntax for class + method should be verified.

**Suggestions:**
- Add a before/after symbol manifest for `render_helpers.py`, `section_renderers.py`, and `page_body.py`: each symbol marked `duplicate`, `ported`, or `deleted`.
- Make `_render_page_body` annotation correction an explicit Wave 1 task item.
- Add a temporary migration assertion or test that active shell output from the new `dashboard_renderer.shell` matches the old `dashboard_legacy.page_body` output for the same fixture before deleting legacy.
- Run a targeted grep after Wave 1 for `render_html_shell`, `_render_html_shell`, and `_render_page_body` to confirm no mixed active/dead shell path remains.

**Risk Assessment: MEDIUM-HIGH.** The ordering is correct, but this wave touches the shell/composition path most likely to break byte identity.

### Plan 32-02 Review

**Strengths:**
- Creating new component files for trace, calc rows, and account is cleaner than bloating existing modules.
- The plan respects the 500 LOC cap and anticipates splitting `positions.py` if needed.
- Keeping `render_paper_trades_region` as the public entrypoint reduces caller churn.
- Explicitly preserving local `sizing_engine` imports protects the hex-lite boundary.

**Concerns:**
- **[HIGH] New files need explicit import discipline.** Component modules must not accidentally import `dashboard.py`, persistence, web routes, or state mutation helpers.
- **[HIGH] C-2 local imports risk being hoisted** through auto-organize tooling or manual cleanup, which would break the hex-lite boundary.
- **[MEDIUM] `positions.py` projected at ~363 LOC may still become dense** after imports, helper additions, and future fixes.
- **[MEDIUM] Paper trades and positions contain form rendering with dynamic values** — every moved dynamic leaf must preserve `html.escape(..., quote=True)` behavior.
- **[LOW] New component files may need package export updates** depending on how `dashboard_renderer/components/__init__.py` is structured.

**Suggestions:**
- Add explicit boundary checks after this wave: no `import dashboard` inside `dashboard_renderer/components`, no top-level `sizing_engine` imports, no forbidden I/O imports.
- Add XSS-specific fixture coverage for trace, positions forms, account form, calc rows, and paper trades if not already covered by the golden dashboard fixture.
- For `positions.py`, define the split rule upfront (table rendering vs form/action rendering) rather than waiting for LOC overflow.

**Risk Assessment: MEDIUM.** This wave is broad but mostly component-local. Risk is manageable if symbol inventory and XSS checks are strict.

### Plan 32-03 Review

**Strengths:**
- Correctly isolates circular import removal into its own wave after canonical symbols exist.
- The fresh subprocess import check is important and well-chosen.
- Rewiring `api.py`, `pages.py`, and residual component imports directly supports the phase goal of making `dashboard_renderer` canonical.

**Concerns:**
- **[HIGH] "Direct from-imports" can create new intra-package cycles** if modules import too specifically from each other. This needs an import graph check, not just a grep.
- **[MEDIUM] `dashboard_renderer/__init__.py` listed as modified but no explicit task defines the export policy.**
- **[MEDIUM] The subprocess check should verify both sides:** `import dashboard_renderer` does not load `dashboard`; `import dashboard` may load `dashboard_renderer` intentionally as shim.
- **[LOW] Eliminating `import dashboard as d` may miss alternate forms** like `from dashboard import ...`.

**Suggestions:**
- Add grep gates for ALL forms: `import dashboard`, `from dashboard import`, `dashboard_legacy`.
- Define `dashboard_renderer.__init__` policy explicitly.
- Consider using package-relative imports inside `dashboard_renderer` to make canonical ownership clear.

**Risk Assessment: MEDIUM.** Concept is sound, but import rewiring can create subtle cycles unless verified with a real import graph and fresh-process tests.

### Plan 32-04 Review

**Strengths:**
- Correctly saves shim/stub deletion work until after renderer is canonical and acyclic.
- Retargeting tests and production callers in the same wave is appropriate.
- The `dashboard_legacy` stub semantics are explicit and testable.
- Fixing `dashboard.os.replace` patches prevents vacuous atomic-write tests.
- Full suite, LOC audits, grep gates, and byte-identity checks align well with success criteria.

**Concerns:**
- **[HIGH] Stub behavior for submodule imports.** `__path__ = []` helps force `ImportError`, but the exact exception message for `import dashboard_legacy.foo` may come from import machinery depending on Python version, not always `__getattr__`. The plan already notes `__path__ = []` is LOAD-BEARING — validate early with a prototype.
- **[HIGH] Deleting seven submodules means any missed import becomes a hard failure.** The grep allowlist must run BEFORE deletion and then again AFTER deletion.
- **[MEDIUM] Retargeting tests from `dashboard.*` to `dashboard_renderer.*` may reduce coverage of the shim** unless a small explicit shim test remains.
- **[MEDIUM] "Golden snapshot byte-identical vs pre-Phase 32 baselines" requires baselines captured before changes.** The plan should clarify where those baselines live (fixture files in tests/).
- **[LOW] `dashboard.py` shim's public API contract should be enumerated explicitly** to avoid accidental omissions.

**Suggestions:**
- Verify stub behavior with all three access patterns: `import dashboard_legacy`, `import dashboard_legacy.some_module`, `getattr(dashboard_legacy, "anything")`.
- Keep a narrow `tests/test_dashboard_shim.py` asserting that `dashboard.py` delegates and contains no rendering logic.
- Add a final grep allowlist check matching the roadmap success criteria exactly.
- Make the pre-Phase 32 HTML baseline capture explicit — stored under `tests/fixtures/dashboard/`.

**Risk Assessment: MEDIUM-HIGH.** This is the cutover wave. Most risk comes from import-stub semantics, missed callers, and accidental loss of shim coverage.

### Overall Assessment

The wave ordering is correct: canonical rendering first, component absorption second, circular import removal third, then final shim/stub/caller cutover. The plans achieve the phase goals if executed with strict inventories and fresh-process import checks.

The main gaps are around proving completeness. Counts like "7 unique," "4 unique," and "6 underscore-prefixed" should become checked migration manifests. The import-retirement criteria should be automated, not manually inspected. The stub requirement is the one place to validate early with a tiny prototype before the deletion wave.

**Overall risk: MEDIUM-HIGH.** The target design is simple and appropriate, but the migration has high byte-identity and import-behavior sensitivity. Strong gates are already planned; adding symbol manifests, explicit import graph checks, and stub-behavior proof would bring the risk down to medium.

---

## OpenCode Review

OpenCode review failed or returned empty output.

---

## Qwen Review

Qwen review failed or returned empty output.

---

## Consensus Summary

Reviewed by 2 AI systems (Gemini, Codex). Qwen and OpenCode did not return usable output.

### Agreed Strengths

Both reviewers confirmed:

1. **Wave ordering is correct** — foundational absorption first (32-01, 32-02), then circular import elimination (32-03), then cutover (32-04).
2. **Dead code identification** — Catching that `shell.py::render_html_shell` is dead and the active shell is in `page_body.py` is the highest-value finding that prevents a silent byte-identity breakage.
3. **`__path__ = []` + `__getattr__` stub** is an elegant, load-bearing solution for forcing `ImportError` (not `ModuleNotFoundError`).
4. **Audit-first approach (D-03)** — Prevents porting thin wrappers that are already covered in `dashboard_renderer`.
5. **`os.replace` patch retargeting** — Both reviewers flagged this as critical; moving the patch to `dashboard_renderer.io.os.replace` prevents vacuous test passes.
6. **Byte-identity gate** (`TestGoldenSnapshot`) as the primary regression signal is well-chosen.

### Agreed Concerns

Both reviewers independently raised:

1. **[HIGH] Symbol inventory completeness** — The "7 unique" / "4 unique" / "6 underscore-prefixed" counts need locked manifests, not narrative summaries. If a count is off, later waves silently depend on missing helpers.
2. **[HIGH] Shell composition byte-identity risk** — Replacing `render_html_shell` body is the highest-risk step in 32-01. Whitespace/attribute order drift can fail the golden snapshot test in subtle ways.
3. **[HIGH] C-2 import hoisting risk** — `sizing_engine` local function-body imports in calc_rows and positions must not be lifted to module-top during the port (would break hex-lite AST gate).
4. **[MEDIUM] `positions.py` LOC pressure** — Projected at ~363 LOC; consider proactive split into `positions_table.py` + `positions_forms.py` rather than waiting for overflow.
5. **[MEDIUM] New intra-package import cycles** — Direct from-imports in 32-03 could inadvertently create new cycles; needs fresh-subprocess verification, not just grep.
6. **[MEDIUM] Stub behavior validation** — `__path__ = []` + `__getattr__` raises ImportError correctly for attribute access, but the exact behavior for `import dashboard_legacy.X` in all Python versions should be validated early (not only at Wave 4 cutover).

### Divergent Views

- **Gemini rated overall risk LOW** (trusting the byte-identity gate as a sufficient catch-all). **Codex rated overall risk MEDIUM-HIGH** (emphasizing that migration correctness — manifests, import-graph proofs, stub prototyping — is not fully specified).
- **Gemini suggested pre-emptive `positions.py` split during Wave 2.** Codex agreed positions needs attention but framed it as "define split rule upfront" rather than mandating a split.
- **Gemini raised logger continuity** as a concern (no `__name__` vs `'dashboard'` fragmentation for journalctl). **Codex did not explicitly flag this** but noted the acyclic import subprocess test should validate both directions.

### Recommended Pre-Execution Actions

Based on consensus findings, consider these low-cost additions before executing:

1. **Add a locked symbol manifest** to 32-01-PLAN.md listing each `render_helpers.py` symbol as `duplicate|ported|deleted` — confirms the "7 unique" count before execution.
2. **Validate stub behavior** in isolation: create a throwaway `__path__ = []` + `__getattr__` package and run `import that_pkg.submod` in a fresh subprocess to confirm `ImportError` (not `ModuleNotFoundError`) before Wave 4.
3. **Define `positions.py` split rule upfront** (e.g., table rendering goes in `positions.py`, form rendering in `position_forms.py`) so the executor doesn't need to make a discretionary call mid-task.
4. **Add grep gate for all import forms** (`import dashboard`, `from dashboard import`, `import dashboard as d`) not just the `as d` variant, in the 32-03 acceptance criteria.
