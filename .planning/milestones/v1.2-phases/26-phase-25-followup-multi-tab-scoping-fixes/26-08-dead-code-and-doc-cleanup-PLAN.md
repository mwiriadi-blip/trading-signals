---
phase: 26
plan: 08
type: execute
wave: 4
parallel: false
depends_on:
  - 26-06-renderer-api-cleanup-PLAN.md
  - 26-07-cache-and-cookie-hardening-PLAN.md
files_modified:
  - dashboard.py
  - .planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-VERIFICATION.md
autonomous: false
requirements: []
must_haves:
  truths:
    - "_render_market_selector deleted (zero callers per 26-PATTERNS audit)"
    - "_render_dashboard_page_nav deleted (already absorbed into Plan 06; verified absent here)"
    - "25-VERIFICATION.md superseded by re-run via /gsd-verify-work 25 OR closing-note appended"
    - "C5 lazy-regen siblings: deferred to v1.3 with tracked debt note"
  artifacts:
    - path: dashboard.py
      provides: "Phase 25 dead code removed"
      contains: "_render_single_page_dashboard"
    - path: .planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-VERIFICATION.md
      provides: "Fresh verification OR superseded note"
      contains: "verified"
  key_links:
    - from: "grep _render_market_selector"
      to: "zero matches"
      via: "post-cleanup audit"
      pattern: "_render_market_selector"
---

<objective>
C2 + C3 + C4 + C5. Final dead-code sweep (C2 was absorbed by Plan 06 — verify absent; delete C3 here). Resolve stale 25-VERIFICATION.md (C4). Defer C5 lazy-regen with debt note.

Purpose: Close Phase 25 narrative loose ends. Wave 4 runs after all fix waves green.
Output: Dead code gone. Phase 25 verification reconciled.
</objective>

<context>
@.planning/phases/26-phase-25-followup-multi-tab-scoping-fixes/26-CONTEXT.md
@.planning/phases/26-phase-25-followup-multi-tab-scoping-fixes/26-PATTERNS.md
@.planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-VERIFICATION.md
@.planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-11-gap-closure-SUMMARY.md
@dashboard.py

<interfaces>
# C2 — _render_dashboard_page_nav: deleted in Plan 26-06; verify absent here.
# C3 — _render_market_selector at dashboard.py:770-782; per 26-PATTERNS §R4: 0 non-self callers; only mention is comment at line 1975.
# C4 — 25-VERIFICATION.md: status: gaps_found / D-14 + 3 broken tests; both closed by 25-11-gap-closure-SUMMARY.md.
# C5 — render_dashboard writes 4 sibling files every regen; lazy-regen optional, deferred.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Delete _render_market_selector + audit Plan 06's deletion of _render_dashboard_page_nav</name>
  <files>dashboard.py</files>
  <action>
1. Verify Plan 06 already deleted `_render_dashboard_page_nav`:
```
grep -n "_render_dashboard_page_nav" dashboard.py
```
Expected: 0. If non-zero, delete the function body now.
2. Delete `_render_market_selector` at dashboard.py:770-782. Body is ~12 lines.
3. Audit caller comment at dashboard.py:1975 — if it references the now-deleted function, update to reflect removal (or delete the dangling comment).
4. Final grep gate:
```
grep -rn "_render_market_selector\|_render_dashboard_page_nav" --include="*.py" . | grep -v "test_\|26-\|25-"
```
Expected: 0 matches.
  </action>
  <verify>
    <automated>grep -v '^#' dashboard.py | grep -c "_render_market_selector\|_render_dashboard_page_nav"</automated>
  </verify>
  <done>Grep returns 0. Suite green: `pytest -x`.</done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 2: C4 — Resolve 25-VERIFICATION.md staleness</name>
  <what-built>Phase 25 verification reconciliation.</what-built>
  <how-to-verify>
Two paths (operator picks):

**(A) Re-verify (most-eloquent):** Run `/gsd-verify-work 25` from a fresh context. This produces a new 25-VERIFICATION.md against current main. Replaces the stale `gaps_found` document with a clean `verified` (or `gaps_found` if real gaps remain — 25-11 should have closed them).

**(B) Append closing note:** Add a new section to 25-VERIFICATION.md:
```markdown
---

## SUPERSEDED

This verification report was generated 2026-05-06 against pre-gap-closure state.
All 2 gaps documented above were closed by Plan 25-11 (see 25-11-gap-closure-SUMMARY.md).
Re-verified via Phase 26 — see 26-VERIFICATION.md.
```
Append-only; do NOT delete the body.

**Operator choice:** A is cleaner; B is faster.
  </how-to-verify>
  <resume-signal>Reply: "re-verified" with new status, or "superseded-note-appended".</resume-signal>
</task>

<task type="auto">
  <name>Task 3: C5 — Document lazy-regen sibling debt</name>
  <files>.planning/phases/26-phase-25-followup-multi-tab-scoping-fixes/26-DEBT.md</files>
  <action>
Create a small debt note documenting the C5 deferral. Caveman terse.

Content:
```markdown
# Phase 26 — Deferred Items

## C5 — Lazy-regen siblings on page-route hit

**Status:** Deferred to v1.3.

**Problem:** dashboard_renderer.api.render_dashboard_files writes 4 sibling HTMLs (signals, account, settings, market-test) on every state mutation. ~5x I/O per run vs lazy regen on first page hit.

**Why deferred:** Optional polish; current behaviour is correct (just wasteful). Phase 26's BROKEN/RISKY backlog is the priority. Lazy-regen path is half-implemented in `_serve_dashboard_page` already (web/routes/dashboard.py).

**Picking up in v1.3:** Move sibling regen from render_dashboard_files into `_serve_dashboard_page`'s 404-or-stale path. _is_stale_for (Plan 26-07 R1) is the unlock.
```
  </action>
  <verify>
    <automated>test -f .planning/phases/26-phase-25-followup-multi-tab-scoping-fixes/26-DEBT.md && grep -c "C5" .planning/phases/26-phase-25-followup-multi-tab-scoping-fixes/26-DEBT.md</automated>
  </verify>
  <done>26-DEBT.md exists with C5 entry; grep returns ≥1.</done>
</task>

</tasks>

<verification>
```
grep -rn "_render_market_selector\|_render_dashboard_page_nav" --include="*.py" . | grep -v "test_\|26-\|25-"
# expected: zero
pytest -x
# full suite green
ls .planning/phases/26-phase-25-followup-multi-tab-scoping-fixes/26-DEBT.md
ls .planning/phases/25-*/25-VERIFICATION.md  # exists, either re-verified or with SUPERSEDED note
```
</verification>

<success_criteria>
- Both DEPRECATED functions deleted.
- 25-VERIFICATION.md resolved (one of: re-verified, superseded note).
- 26-DEBT.md tracks C5 deferral.
- Full pytest green.
</success_criteria>

## Rollback

`git revert <plan-08-commit>`. Deletes can be restored via revert; debt note is a new file (rm or revert).

## Notes

Pattern map: 26-PATTERNS.md §C2/C3/C4. Phase 25 staged the deprecations → Phase 26 cleans up.

<output>
Create `26-08-SUMMARY.md` listing deletions, 25-VERIFICATION.md resolution path chosen, debt note creation.
</output>
