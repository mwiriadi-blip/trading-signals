---
phase: 27
plan: 12
type: execute
wave: 3
parallel: true
depends_on:
  - 27-01-decimal-money-math-PLAN.md
  - 27-02-http-timeout-standardization-PLAN.md
  - 27-03-api-key-redaction-PLAN.md
  - 27-05-magic-cost-helper-and-fallback-email-PLAN.md
  - 27-08-html-escape-audit-PLAN.md
  - 27-10-warnings-fifo-rundate-lookahead-tests-PLAN.md
  - 27-11-crash-email-fallback-PLAN.md
files_modified:
  - notifier.py (deleted at end)
  - notifier/__init__.py (NEW)
  - notifier/templates.py (NEW)
  - notifier/transport.py (NEW)
  - notifier/warnings_fifo.py (NEW)
  - notifier/crash_path.py (NEW)
  - tests/test_notifier_package_seam.py (NEW)
autonomous: true
requirements: []
must_haves:
  truths:
    - "notifier/ is a package; each file <500 LOC."
    - "Public API surface preserved: send_email, _dispatch_email_and_maintain_warnings, and any other names imported externally remain callable as `notifier.<name>`."
    - "Every external import site (`from notifier import send_email`, `import notifier`) continues to work — no caller changes required."
    - "All existing notifier tests pass without modification (proving public API parity)."
  artifacts:
    - path: notifier/__init__.py
      provides: "re-export of public API"
      contains: "from .transport import send_email"
    - path: notifier/templates.py
      provides: "HTML template rendering"
      contains: "def render"
    - path: notifier/transport.py
      provides: "Resend POST + send_email + crash-fallback wiring"
      contains: "send_email"
    - path: notifier/warnings_fifo.py
      provides: "_dispatch_email_and_maintain_warnings + FIFO bound"
      contains: "WARNINGS_FIFO_MAX_LEN"
    - path: notifier/crash_path.py
      provides: "_write_last_crash helper"
      contains: "_write_last_crash"
  key_links:
    - from: "notifier/__init__.py"
      to: "notifier/transport.py"
      via: "re-export"
      pattern: "from \\.transport"
---

<objective>
Split notifier.py (1974 LOC) into a package along clean seams. Target: each module <500 LOC.

Sequenced LAST in Wave 3 so it inherits ALL functional changes from Waves 1-2 (Decimal money in cost interpolation, HTTP_TIMEOUT_S, redact_secret, entry_side_cost, _EMAIL_TO_FALLBACK removal, html.escape audit, WARNINGS_FIFO_MAX_LEN bound, last_crash.json fallback). Splitting BEFORE these changes would force re-rebasing each functional patch.

Purpose: file-size hygiene (review item #2). 1974 LOC is well beyond the 500-LOC project convention.
Output: notifier/ package with preserved public API + every existing import unchanged.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@notifier.py

<interfaces>
# Proposed seams (read notifier.py and adjust to match actual structure):
#
# notifier/templates.py        — HTML email body building (likely ~600 LOC)
#                                 Contains: every f-string + html.escape interpolation,
#                                 the per-instrument render helpers, the warnings list renderer.
# notifier/transport.py        — Resend HTTP POST + send_email orchestration (~300 LOC)
#                                 Contains: requests.post call, redact_secret usage, 
#                                 SIGNALS_EMAIL_TO/FROM env-var checks, crash-fallback wiring.
# notifier/warnings_fifo.py    — _dispatch_email_and_maintain_warnings + WARNINGS_FIFO_MAX_LEN
#                                  enforcement (~150 LOC).
# notifier/crash_path.py       — _write_last_crash + last_crash.json schema (~80 LOC).
# notifier/__init__.py         — re-exports for public API surface (~30 LOC).
#
# Public API to preserve (callers must continue importing these as `from notifier import X`):
#   send_email(...)
#   _dispatch_email_and_maintain_warnings(...)
#   _write_last_crash(...)         (added in Plan 27-11)
#   render_email_html(...)         (whatever the public templating entry point is)
#   Any name in tests/test_notifier.py that's referenced via `notifier.X` or `from notifier import X`.
#
# After split: tests/test_notifier.py imports MUST work unchanged.
# Method to verify: `git stash test changes; pytest tests/test_notifier.py -x; git stash pop`.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Inventory notifier.py — group into seams</name>
  <read_first>
    - notifier.py (full — read in chunks if needed)
    - tests/test_notifier.py — capture every `notifier.X` reference (the public API to preserve)
  </read_first>
  <action>
1. Read notifier.py in chunks. For each function/class, classify into one of the four seams (templates / transport / warnings_fifo / crash_path).
2. Build a manifest:
   ```
   notifier.py:LINE_RANGE  →  notifier/SEAM.py
     def name(...)           keep / rename / private
   ```
3. Capture the public API surface from `tests/test_notifier.py`:
   ```bash
   grep -n 'notifier\.\|from notifier import' tests/test_notifier.py
   ```
   Every match is a name that must be re-exported from `notifier/__init__.py`.
4. Confirm no circular imports between proposed seams. If templates.py imports from transport.py and vice versa → restructure.

Output of Task 1: a manifest file (.planning/phases/27-…/notifier-split-manifest.md) used by Task 2.
  </action>
  <verify>
    <automated>test -f .planning/phases/27-code-quality-correctness-sweep-apply-2026-05-07-code-review-/notifier-split-manifest.md && wc -l .planning/phases/27-code-quality-correctness-sweep-apply-2026-05-07-code-review-/notifier-split-manifest.md</automated>
  </verify>
  <done>
    - Manifest written.
    - Public API surface enumerated.
    - No circular-import risks identified.
  </done>
</task>

<task type="auto">
  <name>Task 2: Create notifier/ package; mechanical move; preserve public API</name>
  <read_first>
    - the manifest from Task 1
    - notifier.py
  </read_first>
  <action>
1. Create directory `notifier/`.
2. For each seam, create the new file and move the corresponding functions/classes per the manifest. Preserve module docstrings, comment headers, and Phase-tag annotations.
3. Update intra-package imports (e.g. transport.py importing from templates.py).
4. Create `notifier/__init__.py` re-exporting every public API name:
   ```python
   '''Phase 27 #2 — package split. Public API surface preserved.'''
   from .transport import send_email, _dispatch_email_and_maintain_warnings
   from .crash_path import _write_last_crash
   from .templates import render_email_html  # adjust to actual public template entry
   # ... add any additional names per Task 1 manifest
   __all__ = ['send_email', '_dispatch_email_and_maintain_warnings', '_write_last_crash', 'render_email_html']
   ```
5. Delete `notifier.py`.
6. Run `pytest tests/test_notifier.py -x` — MUST pass without test changes. If a test fails because a previously-importable name is no longer accessible via `notifier.X`, add it to `__init__.py` re-exports.
7. Run full `pytest -x`.
8. Verify line counts:
   ```bash
   wc -l notifier/*.py
   # expected: every file <500 LOC
   ```
9. Verify ruff:
   ```bash
   ruff check notifier/
   # expected: clean (or pre-existing F401 warnings now have a home — Plan 09 STATE note about deferred ruff F401 in notifier.py, this split is the chance to clear them)
   ```
  </action>
  <verify>
    <automated>pytest tests/test_notifier.py -x && wc -l notifier/*.py | awk '$1 > 499 && $2 != "total" { print "OVERLENGTH: " $0; exit 1 } END { print "all under 500" }'</automated>
  </verify>
  <done>
    - notifier/ package exists; notifier.py deleted.
    - Every file <500 LOC.
    - tests/test_notifier.py passes unchanged.
    - Full suite green.
    - ruff clean (or any remaining warnings logged in 27-DEBT.md).
  </done>
</task>

<task type="auto">
  <name>Task 3: Public API parity test (lock in the contract)</name>
  <read_first>
    - notifier/__init__.py
  </read_first>
  <action>
1. **tests/test_notifier_package_seam.py (NEW):** assert that every name in the historical public API is still importable.
   ```python
   def test_public_api_preserved():
     import notifier
     for name in ['send_email', '_dispatch_email_and_maintain_warnings', '_write_last_crash', 'render_email_html']:
       assert hasattr(notifier, name), f'{name} missing from notifier package'
   def test_no_module_level_notifier_py():
     import sys, pathlib
     # notifier.py must be deleted; only the package directory exists
     assert not pathlib.Path('notifier.py').exists()
     assert pathlib.Path('notifier/__init__.py').exists()
   ```
  </action>
  <verify>
    <automated>pytest tests/test_notifier_package_seam.py -x -v</automated>
  </verify>
  <done>2 tests green.</done>
</task>

</tasks>

<threat_model>
N/A — pure code reorganisation. No security-relevant surface change. The XSS / redact-secret / FIFO bound from Waves 1-2 are PRESERVED by the split (they're already in notifier.py before this plan runs).
</threat_model>

<verification>
```
pytest -x   # full suite — NO test changes required
wc -l notifier/*.py  # all <500
ruff check notifier/
grep -rn '^import notifier\|^from notifier' --include='*.py' | grep -v '^tests/'
# every match must continue to work
```
</verification>

<success_criteria>
- notifier/ is a package; each file <500 LOC.
- Public API parity (tests/test_notifier.py unchanged + green).
- 2 new parity tests green.
- Full suite green.
- ruff clean.
</success_criteria>

<output>
Create `27-12-SUMMARY.md` with: manifest summary (file → seam mapping), public API list, line counts per new file, before/after wc -l notifier{.py,/*.py}.
</output>
