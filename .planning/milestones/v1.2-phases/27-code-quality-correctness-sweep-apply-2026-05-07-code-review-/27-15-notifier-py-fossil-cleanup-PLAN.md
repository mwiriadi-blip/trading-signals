---
phase: 27
plan: 15
type: execute
wave: 4
parallel: false
depends_on:
  - 27-12-notifier-split-PLAN.md  # monolith deleted under CR-01 of 27-12
  - 27-14-dashboard-split-PLAN.md  # last phase to touch hex-peer comments
files_modified:
  - system_params.py
  - crash_boundary.py
  - web/app.py
  - web/middleware/auth.py
  - tests/test_setup_https_doc.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "Zero `notifier.py` string occurrences in production source comments that describe the CURRENT architecture (hex peers, palette imports, error-handling reach)."
    - "Legitimate fossil references that document HISTORY (CR-01 fix breadcrumbs, Plan 27-12 provenance docstrings inside notifier/*.py, test path constants pointing at tests/test_notifier.py) are PRESERVED — they describe the deletion event, not the current shape."
    - "tests/test_setup_https_doc.py SETUP-HTTPS drift-guard docstring/header refers to the `notifier package` (or `notifier/`), not the deleted file."
    - "Full test suite green post-edit (no test references the changed comments)."
  artifacts:
    - path: system_params.py
      provides: "comments updated: 'notifier.py' -> 'notifier package' at lines 264, 336"
      contains: "notifier package"
    - path: crash_boundary.py
      provides: "comment updated at line 39"
      contains: "notifier package"
    - path: web/app.py
      provides: "hex-peer comment at line 4 updated to 'notifier/, dashboard_legacy/'"
      contains: "dashboard_legacy"
    - path: web/middleware/auth.py
      provides: "hex-peer comment at line 33 updated"
      contains: "notifier/"
    - path: tests/test_setup_https_doc.py
      provides: "docstring refs at lines 7 and 281 updated to 'notifier package (Plan 02 + 27-12 split)'"
      contains: "notifier package"
  key_links:
    - from: "test_setup_https_doc.test_signals_email_from_matches_notifier"
      to: "notifier/*.py glob"
      via: "Path('notifier').glob('*.py')"
      pattern: "notifier package"
---

## Context

Phase 27-12 (notifier-split) under CR-01 deleted `notifier.py` and replaced it with the `notifier/` package. Phase 27-14 reduced `dashboard.py` to a 224-LOC re-export shim and introduced `dashboard_legacy/`. After all that, several comments and docstrings still reference `notifier.py` as if it were a live file. They fall into two buckets:

**Bucket A — describes CURRENT architecture (stale, must fix):**

- `system_params.py:264` — comment claims `notifier.py` reads `state['_resolved_contracts']`. The notifier package reads it; comment should say so.
- `system_params.py:336` — palette-import comment names `notifier.py` as the consumer. Update to `notifier package`.
- `crash_boundary.py:39` — "import-time errors in notifier.py" — package now.
- `web/app.py:4` — hex-peer doc names `notifier.py, dashboard.py`. Update to `notifier/`, `dashboard_legacy/` (per 27-14 outcome).
- `web/middleware/auth.py:33` — same hex-peer pattern.
- `tests/test_setup_https_doc.py:7` (docstring header) and `:281` (class docstring) — name `notifier.py` as the SETUP-HTTPS drift-guard target. The actual assertion at line 331-345 already globs `notifier/*.py`. Bring the prose in line with the assertion.

**Bucket B — describes HISTORY (legitimate fossils, KEEP as-is):**

- `notifier/*.py` module headers: "Extracted from notifier.py in Plan 27-12 (notifier package split)" — historical provenance, useful for git archaeology, do not touch.
- `notifier/__init__.py:142` — references `tests/test_notifier.py` (a test FILE, not the module).
- `notifier/dispatch.py:43` — same: test FILE reference.
- `notifier/transport.py:7` — describes monkeypatch target `notifier.requests.post` (a Python attribute path, not the deleted module file).
- `notifier/templates_alerts.py:36, 59` — palette/import-style references that explain why the file matches `notifier.py`'s historical aesthetic; harmless and informational.
- `state_manager.py:494` — points at `tests/test_notifier.py::TestDetectSignalChanges::...` — test FILE path.
- `tests/test_*.py` — every "CR-01 fix:" or "WR-06 fix:" comment that explicitly documents the monolith deletion. These are deletion-event breadcrumbs that lose meaning if scrubbed; they exist precisely so a future reader understands why the test scans `notifier/*.py` instead of a single file. KEEP.
- `tests/test_notifier.py:60` and `tests/test_signal_engine.py:478` — `TEST_NOTIFIER_PATH = Path('tests/test_notifier.py')` — points at the TEST FILE.
- `tests/test_notifier_magic_link.py:89, 202` — refers to "notifier.py palette aesthetic" and "notifier.py convention" — describes a style/convention, not a live file. Borderline; KEEP for now (purely descriptive).

This plan ONLY touches Bucket A. It is comment-only — zero behavioural change.

<objective>
Bring stale comments/docstrings in line with the post-27-12 / post-27-14 architecture. Pure prose-update; no executable line changes; no test additions beyond the existing suite running green.

Purpose: developer-experience + drift-guard hygiene — the next reader looking for "notifier.py" lands on real history, not phantom file references.

Output: 5 files patched; 0 behavioural diffs; full test suite still green.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/27-code-quality-correctness-sweep-apply-2026-05-07-code-review-/27-12-notifier-split-PLAN.md
@.planning/phases/27-code-quality-correctness-sweep-apply-2026-05-07-code-review-/notifier-split-manifest.md

<interfaces>
# Edit pattern (per file): replace exact strings, keep surrounding text intact.
#
# system_params.py:264:
#   - "# dashboard.py and notifier.py when state['_resolved_contracts'] is"
#   + "# dashboard.py and the notifier package when state['_resolved_contracts'] is"
#
# system_params.py:336:
#   - "# notifier.py can import the same palette without cross-hex import (hex"
#   + "# the notifier package can import the same palette without cross-hex import (hex"
#
# crash_boundary.py:39:
#   - "  helper body (not at module top) so import-time errors in notifier.py"
#   + "  helper body (not at module top) so import-time errors in the notifier package"
#
# web/app.py:4:
#   - "  web/ is an adapter hex (peer of notifier.py, dashboard.py)."
#   + "  web/ is an adapter hex (peer of notifier/, dashboard_legacy/, dashboard.py shim)."
#
# web/middleware/auth.py:33:
#   - "  web/middleware/ is an adapter hex (peer of web/routes/, notifier.py)."
#   + "  web/middleware/ is an adapter hex (peer of web/routes/, notifier/)."
#
# tests/test_setup_https_doc.py:7:
#   - "  - notifier.py (Plan 02) — SIGNALS_EMAIL_FROM env var name"
#   + "  - notifier package (Plan 02 + 27-12 split) — SIGNALS_EMAIL_FROM env var name"
#
# tests/test_setup_https_doc.py:281:
#   - "  nginx/signals.conf (Plan 01), deploy.sh (Plan 03), or notifier.py"
#   + "  nginx/signals.conf (Plan 01), deploy.sh (Plan 03), or the notifier package"
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Patch production source comments (system_params, crash_boundary, web/app, web/middleware/auth)</name>
  <read_first>
    - system_params.py — lines 260-270 and 332-340
    - crash_boundary.py — lines 35-45
    - web/app.py — lines 1-10
    - web/middleware/auth.py — lines 28-40
  </read_first>
  <behavior>
    - Each edit is comment-only; runtime behaviour unchanged.
    - After edits, `grep -n 'notifier\.py' system_params.py crash_boundary.py web/app.py web/middleware/auth.py` returns ZERO lines.
  </behavior>
  <action>
1. system_params.py:264 — replace "notifier.py" with "the notifier package".
2. system_params.py:336 — replace "notifier.py" with "the notifier package".
3. crash_boundary.py:39 — replace "notifier.py" with "the notifier package".
4. web/app.py:4 — replace the hex-peer line with: `web/ is an adapter hex (peer of notifier/, dashboard_legacy/, dashboard.py shim).`
5. web/middleware/auth.py:33 — replace `notifier.py` with `notifier/`.
6. Run targeted regression: pytest -x tests/test_setup_https_doc.py tests/test_notifier.py tests/test_secret_redaction.py — must pass.
  </action>
  <verify>
    <automated>! grep -q 'notifier\.py' system_params.py crash_boundary.py web/app.py web/middleware/auth.py</automated>
  </verify>
  <done>
    - 4 files patched; 5 line-edits; comments only.
    - Targeted tests pass.
  </done>
</task>

<task type="auto">
  <name>Task 2: Patch SETUP-HTTPS drift-guard docstring (tests/test_setup_https_doc.py)</name>
  <read_first>
    - tests/test_setup_https_doc.py — lines 1-15 and 275-290
  </read_first>
  <behavior>
    - Header docstring at line 7 names the drift-guard target as `notifier package (Plan 02 + 27-12 split)`.
    - TestCrossArtifactDriftGuard class docstring at line 281 names `the notifier package`.
    - The actual test assertion at line 331-345 (`test_signals_email_from_matches_notifier`) is unchanged — it already globs `notifier/*.py`.
  </behavior>
  <action>
1. Replace line 7 prose per `<interfaces>` block.
2. Replace line 281 prose per `<interfaces>` block.
3. Run: `pytest -x tests/test_setup_https_doc.py` — must pass.
  </action>
  <verify>
    <automated>! grep -nE 'notifier\.py' tests/test_setup_https_doc.py</automated>
  </verify>
  <done>
    - 2 docstring edits; assertion logic unchanged.
    - test_setup_https_doc.py green.
  </done>
</task>

<task type="auto">
  <name>Task 3: Confirm legitimate fossils preserved + final regression</name>
  <read_first>
    - notifier/__init__.py — confirm "Extracted from notifier.py in Plan 27-12" provenance docstring intact
    - tests/test_notifier.py — confirm `TEST_NOTIFIER_PATH = Path('tests/test_notifier.py')` constant intact
    - tests/test_crash_email_fallback.py:110 — confirm WR-06 fix breadcrumb intact
  </read_first>
  <behavior>
    - All Bucket B fossils still present (this task is read-only verification + full suite run).
    - Full test suite green.
  </behavior>
  <action>
1. Spot-check Bucket B preservation:
   ```bash
   grep -c 'notifier\.py' notifier/__init__.py     # >= 1 (Plan 27-12 provenance)
   grep -c 'notifier\.py' tests/test_notifier.py   # >= 1 (CR-01 fix marker + TEST_NOTIFIER_PATH constant)
   grep -c 'notifier\.py' state_manager.py         # >= 1 (test path reference)
   ```
2. Run full suite: `pytest -x` — every test must pass.
3. Confirm Bucket A is clean:
   ```bash
   grep -nE 'notifier\.py' system_params.py crash_boundary.py web/app.py web/middleware/auth.py tests/test_setup_https_doc.py
   # expect zero output
   ```
  </action>
  <verify>
    <automated>pytest -x --tb=short 2>&1 | tail -3 | grep -q 'passed'</automated>
  </verify>
  <done>
    - Bucket B preserved.
    - Bucket A scrubbed.
    - Full suite green.
    - 27-15-SUMMARY.md written.
  </done>
</task>

</tasks>

## Out-of-scope (explicit)

- The 19 fossil refs inside `notifier/*.py` headers ("Extracted from notifier.py in Plan 27-12"). These are git-archaeology breadcrumbs and stay.
- All `tests/test_*.py` "CR-01 fix:" / "WR-06 fix:" deletion-event markers. They exist to explain to a future reader why the test scans the package; scrubbing them would silently remove that context.
- `TEST_NOTIFIER_PATH = Path('tests/test_notifier.py')` constants — point at the live test FILE, not the deleted module.
- `notifier/transport.py:7` — describes monkeypatch attribute path `notifier.requests.post`, not the deleted file.
- `tests/test_notifier_magic_link.py:89, 202` — descriptive style references; not architecturally misleading.

If a future reviewer wants to scrub Bucket B too, that's a separate phase.
