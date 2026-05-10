---
phase: 27
plan: 12
type: execute
wave: 3
parallel: false  # <!-- review-fix: agreed-1 — Wave 3 sequential, not parallel -->
depends_on:
  - 27-02-http-timeout-standardization-PLAN.md
  - 27-03-api-key-redaction-PLAN.md
  - 27-05-magic-cost-helper-and-fallback-email-PLAN.md
  - 27-08-html-escape-audit-PLAN.md
  - 27-10-warnings-fifo-rundate-lookahead-tests-PLAN.md
  - 27-11-crash-email-fallback-PLAN.md
files_modified:
  - notifier.py        # remains as RE-EXPORT SHIM after Task A; deleted ONLY in Task B if safe
  - notifier/__init__.py
  - notifier/templates.py
  - notifier/transport.py
  - notifier/warnings_fifo.py
  - notifier/crash_path.py
  - tests/test_notifier_package_seam.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "notifier/ is a package; each file <500 LOC."
    - "_dispatch_email_and_maintain_warnings STAYS in main.py — NOT moved to notifier/. (review-fix agreed-3 — it lives at main.py:1638, will move to daily_loop/crash_boundary in 27-13.)"
    - "Two-commit pattern: Task A creates notifier/ package + KEEPS notifier.py as re-export shim; Task B deletes notifier.py ONLY if no test/prod code references notifier.X directly via the file (vs. package)."
    - "Public API surface preserved: send_email, _write_last_crash, render_email_html (or actual public templating name verified in Task 0), and any other names imported externally remain callable as `notifier.<name>`."
    - "Every monkeypatch path that tests depend on (notifier.requests.post, notifier._post_to_resend, etc.) is preserved via re-export in notifier/__init__.py."
    - "All existing notifier tests pass without modification (proving public API parity)."
  artifacts:
    - path: notifier/__init__.py
      provides: "re-export of public API + monkeypatch-target names"
      contains: "from .transport import send_email"
    - path: notifier/templates.py
      provides: "HTML template rendering"
      contains: "def render"  # <!-- revision-fix: warning-3 — name finalized in Task 0; existence signal kept, false-precision noted --> # canonical entry name resolved in Task 0
    - path: notifier/transport.py
      provides: "Resend POST + send_email + crash-fallback wiring + requests re-export for monkeypatch"
      contains: "send_email"
    - path: notifier/warnings_fifo.py
      provides: "FIFO bound enforcement only — NOT _dispatch_email_and_maintain_warnings"
      contains: "MAX_WARNINGS"
    - path: notifier/crash_path.py
      provides: "_write_last_crash helper"
      contains: "_write_last_crash"
  key_links:
    - from: "notifier/__init__.py"
      to: "notifier/transport.py"
      via: "re-export"
      pattern: "from \\.transport"
    - from: "notifier/__init__.py"
      to: "notifier/transport.requests"
      via: "re-export for monkeypatch (notifier.requests.post)"
      pattern: "requests"
---

## Review fixes applied

- [x] agreed-1 (wave/dependency rebuild) — wave changed `3` parallel → `3` SEQUENTIAL; depends_on=[27-02, 27-03, 27-05, 27-08, 27-10, 27-11] explicit. parallel: false.
- [x] agreed-3 (OpenCode HIGH critical location error) — REMOVED `_dispatch_email_and_maintain_warnings` from this plan's remit. Reason: function lives at main.py:1638, NOT in notifier — moving it would create circular dependency + break 10+ tests via `main._dispatch_email_and_maintain_warnings`. Function STAYS in main.py and will move to `daily_loop.py` / `crash_boundary.py` in Plan 27-13. notifier/warnings_fifo.py contains ONLY the FIFO bound enforcement helper (used by main.py).
- [x] agreed-3 (Codex HIGH shim+delete two-commit pattern) — adopted. Task A creates notifier/ package while keeping notifier.py as re-export shim. Task B deletes notifier.py ONLY if grep confirms no `from notifier.py import` (file-form) usage remains. If usage exists, KEEP shim; document.
- [x] agreed-3 (monkeypatch re-export manifest) — explicit task to verify and re-export every name tests monkeypatch: `notifier.requests` (for `notifier.requests.post = ...`), `notifier._post_to_resend`, etc. Task 0 enumerates these.
- [x] agreed-3 (verify render_email_html actual name) — Task 0 verifies actual public templating name in current notifier.py before declaring it a templates entry point.
- [x] M1 (brittle implementation tests) — LOC threshold tests use ±10% tolerance OR drop in favor of "no module exceeds 500 LOC". Anti-pattern of "every file is exactly 480 LOC" avoided.
- [x] M2 (doc rule) — manifest stays inside `.planning/phases/27-.../`.
- [x] revision warning-3 — `must_haves.artifacts` entry for `notifier/templates.py` annotated: `contains: "def render"` paired with comment that canonical entry name is resolved in Task 0 (existence signal kept, false-precision noted).

<objective>
Split notifier.py (1974 LOC) into a package along clean seams. Target: each module <500 LOC.

Sequenced LAST in Wave 3 (sequential after 27-13 too — see ordering matrix) so it inherits ALL functional changes from Waves 1-2. Splitting BEFORE these would force re-rebasing each functional patch.

**Critical correction (review-fix agreed-3):** `_dispatch_email_and_maintain_warnings` is NOT moved here. It lives at main.py:1638 (verified by OpenCode HIGH). It will relocate in Plan 27-13's main split. notifier/warnings_fifo.py contains ONLY the bound-enforcement helper (the `while len(state['warnings']) > MAX_WARNINGS: pop(0)` loop), which the main-side dispatcher imports.

**Two-commit pattern (review-fix agreed-3):**
- **Commit A:** create notifier/ package; KEEP notifier.py as a re-export shim (`from notifier.transport import *` etc.). All tests pass; both `notifier.X` (file form) AND `notifier.X` (package form via __init__) work.
- **Commit B:** grep for any test/code that imports from notifier.py file specifically. If zero, delete notifier.py. If non-zero, KEEP the shim and document in 27-DEBT.md.

Purpose: file-size hygiene (review item #2). 1974 LOC is well beyond the 500-LOC project convention.
Output: notifier/ package with preserved public API + monkeypatch-target preservation + every existing import unchanged.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@notifier.py

<interfaces>
# Proposed seams (review-fix agreed-3 — _dispatch_* REMOVED from notifier remit):
#
# notifier/templates.py        — HTML email body building (~600 LOC)
# notifier/transport.py        — Resend HTTP POST + send_email orchestration (~300 LOC)
#                                  Re-exports `requests` at module level so `notifier.requests.post`
#                                  monkeypatch path continues to work.
# notifier/warnings_fifo.py    — FIFO bound enforcement HELPER ONLY (not dispatcher) (~80 LOC)
#                                  e.g. `def enforce_fifo_bound(state): while len > MAX_WARNINGS: pop(0)`
# notifier/crash_path.py       — _write_last_crash + _redact_secrets_in_text (~120 LOC) (from 27-11)
# notifier/__init__.py         — re-exports for public API + monkeypatch targets (~50 LOC)
#
# Public API to preserve (callers must continue importing as `from notifier import X`):
#   send_email(...)
#   _write_last_crash(...)         (added in Plan 27-11)
#   <actual public templating entry point>   (verify in Task 0 — may not be 'render_email_html')
#   _post_to_resend                (tests monkeypatch this)
#   requests                       (tests do `monkeypatch.setattr('notifier.requests.post', ...)`)
#   Any name in tests/test_notifier.py referenced via `notifier.X` or `from notifier import X`.
#
# NOT moved (stays in main.py per agreed-3):
#   _dispatch_email_and_maintain_warnings  — lives at main.py:1638
#                                              moves to daily_loop/crash_boundary in 27-13
#
# Verification method: `pytest tests/test_notifier.py` MUST pass without modification.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 0: Inventory + monkeypatch target enumeration + verify render_email_html actual name</name>
  <!-- review-fix: agreed-3 -->
  <read_first>
    - notifier.py (full — read in chunks)
    - tests/test_notifier.py — capture every `notifier.X` reference
  </read_first>
  <action>
1. Read notifier.py in chunks. For each function/class, classify into one of the four seams (templates / transport / warnings_fifo / crash_path).

2. **CRITICAL (review-fix agreed-3):** confirm `_dispatch_email_and_maintain_warnings` is at main.py:1638 (NOT in notifier.py). If grep finds it in notifier.py, the OpenCode finding is stale — but trust OpenCode's analysis: the orchestrator should leave it where it sits. notifier/warnings_fifo.py contains ONLY the bound-enforcement helper, called BY main-side code.

3. **Verify actual public templating name** (review-fix agreed-3 OpenCode MEDIUM): grep for `def render*` in notifier.py and `notifier.render*` in tests. The plan assumed `render_email_html` — verify or update. Document the actual name in the manifest.

4. **Enumerate monkeypatch targets:**
   ```bash
   grep -nE 'notifier\.[a-zA-Z_]|from notifier import|monkeypatch\.(setattr|setitem).*notifier' tests/test_notifier.py
   ```
   Every match is a name that must be re-exported from `notifier/__init__.py`. Common cases:
   - `notifier.requests.post` — requires re-exporting the `requests` module reference
   - `notifier._post_to_resend` — private name, but tests monkeypatch it
   - `notifier._dispatch_email_and_maintain_warnings` — STAYS in main.py per agreed-3, but if tests monkeypatch via notifier.X (vs main.X), document in 27-DEBT.md as a test-side cleanup follow-up.

5. **Confirm no circular imports.** transport may import from templates (build body); templates should NOT import from transport (no cycle).

6. **Manifest output:** `.planning/phases/27-.../notifier-split-manifest.md` with:
   - line-range → seam mapping
   - actual public templating entry point name
   - monkeypatch-target re-export list
   - confirmation that _dispatch_email_and_maintain_warnings stays in main.py
  </action>
  <verify>
    <automated>test -f .planning/phases/27-code-quality-correctness-sweep-apply-2026-05-07-code-review-/notifier-split-manifest.md && wc -l .planning/phases/27-code-quality-correctness-sweep-apply-2026-05-07-code-review-/notifier-split-manifest.md</automated>
  </verify>
  <done>
    - Manifest written.
    - Public API + monkeypatch targets enumerated.
    - Actual public templating name verified (not assumed).
    - _dispatch_email_and_maintain_warnings confirmed staying in main.py.
    - No circular-import risks.
  </done>
</task>

<task type="auto">
  <name>Task A (commit 1): Create notifier/ package; KEEP notifier.py as re-export shim</name>
  <!-- review-fix: agreed-3 (shim-first) -->
  <read_first>
    - manifest from Task 0
    - notifier.py
  </read_first>
  <action>
1. Create directory `notifier/`.

2. For each seam, create the new file and move corresponding functions/classes per the manifest. Preserve module docstrings, comment headers, Phase-tag annotations.

3. **notifier/transport.py:** at top, add `import requests` so it's accessible as `notifier.transport.requests`. Then __init__.py re-exports it.

4. **notifier/warnings_fifo.py:** contains ONLY the FIFO bound helper (review-fix agreed-3):
   ```python
   '''Phase 27 #16 — FIFO bound enforcement helper.
   _dispatch_email_and_maintain_warnings stays in main.py; this module is the
   stateless bound-enforcement helper that main-side dispatcher imports.'''
   from system_params import MAX_WARNINGS
   def enforce_fifo_bound(state: dict) -> None:
     while len(state.get('warnings', [])) > MAX_WARNINGS:
       state['warnings'].pop(0)
   ```

5. Update intra-package imports (transport.py importing from templates.py, etc.).

6. Create `notifier/__init__.py` re-exporting every public + monkeypatch-target name per manifest:
   ```python
   '''Phase 27 #2 — package split. Public API + monkeypatch-target preservation.'''
   from .transport import send_email, _post_to_resend
   from .transport import requests        # <-- monkeypatch target: notifier.requests.post
   from .crash_path import _write_last_crash, _redact_secrets_in_text
   from .templates import <actual_public_template_name>     # name from Task 0 manifest
   from .warnings_fifo import enforce_fifo_bound
   __all__ = ['send_email', '_post_to_resend', '_write_last_crash', '_redact_secrets_in_text',
              '<actual_public_template_name>', 'enforce_fifo_bound', 'requests']
   ```

7. **KEEP notifier.py as re-export shim (review-fix agreed-3):**
   ```python
   '''Phase 27 #2 shim — package lives in notifier/. This file remains as a
   transitional shim for any straggling `from notifier.py` style imports.
   Will be deleted in Task B if no such imports remain.'''
   from notifier import *  # noqa: F401,F403
   from notifier import requests, _post_to_resend, _write_last_crash, _redact_secrets_in_text  # noqa: F401
   ```

8. Run `pytest tests/test_notifier.py -x` — MUST pass without test changes.

9. Run full `pytest -x`.

10. Verify line counts:
    ```bash
    wc -l notifier/*.py
    # expected: every file <500 LOC (or use ±10% tolerance per M1)
    ```

11. Commit: `feat(27-12): notifier package shim — Task A`.
  </action>
  <verify>
    <automated>pytest tests/test_notifier.py -x && wc -l notifier/*.py | awk '$1 > 499 && $2 != "total" { print "OVERLENGTH: " $0; exit 1 } END { print "all under 500" }'</automated>
  </verify>
  <done>
    - notifier/ package exists; notifier.py STAYS as shim.
    - Every package file <500 LOC.
    - tests/test_notifier.py passes unchanged.
    - Full suite green.
    - _dispatch_email_and_maintain_warnings still in main.py (verify via grep).
    - Commit made.
  </done>
</task>

<task type="auto">
  <name>Task B (commit 2): Delete notifier.py if and only if no file-form imports remain</name>
  <!-- review-fix: agreed-3 (delete-only-if-safe) -->
  <read_first>
    - notifier.py (post Task A — verify it's only the shim)
  </read_first>
  <action>
1. Grep for any remaining file-form imports of notifier.py:
   ```bash
   grep -rnE 'from notifier\.py|import notifier\.py' --include='*.py'
   # expected: zero matches (Python doesn't usually use .py in imports anyway)
   ```

2. Grep for any code/test that depends on `notifier` being a single .py file (e.g. checks `pathlib.Path('notifier.py').exists()` for some reason):
   ```bash
   grep -rn 'notifier\.py' --include='*.py' .
   # visual review: any match must be either a docstring/comment OR a test that needs updating
   ```

3. **If grep is clean → delete notifier.py.**
4. **If grep finds usages → KEEP notifier.py as shim. Document in 27-DEBT.md** with rationale + plan to clean up later.

5. Run `pytest -x` again to confirm green.

6. Commit: `feat(27-12): notifier shim removed — Task B` (only if Step 4 chose deletion).
  </action>
  <verify>
    <automated>pytest -x</automated>
  </verify>
  <done>
    - Either notifier.py deleted (preferred), OR notifier.py kept as shim with rationale.
    - Full suite still green.
    - Decision documented.
  </done>
</task>

<task type="auto">
  <name>Task 3: Public API + monkeypatch parity test</name>
  <read_first>
    - notifier/__init__.py
    - manifest from Task 0
  </read_first>
  <action>
1. **tests/test_notifier_package_seam.py (NEW):** assert every monkeypatch-target name is still importable.
   ```python
   def test_public_api_preserved():
     import notifier
     # base public surface
     for name in ['send_email', '_post_to_resend', '_write_last_crash',
                  '_redact_secrets_in_text', 'enforce_fifo_bound']:
       assert hasattr(notifier, name), f'{name} missing from notifier package'

   def test_monkeypatch_target_requests_preserved():
     '''notifier.requests must be the requests module so tests can monkeypatch notifier.requests.post.'''
     import notifier
     import requests as _real_requests
     assert notifier.requests is _real_requests or hasattr(notifier.requests, 'post')

   def test_dispatch_helper_stays_in_main(): 
     '''review-fix agreed-3: _dispatch_email_and_maintain_warnings stays in main.py.'''
     import main
     assert hasattr(main, '_dispatch_email_and_maintain_warnings'), \
       'main._dispatch_email_and_maintain_warnings missing — should NOT have moved to notifier'
     # And verify it's NOT in notifier
     import notifier
     assert not hasattr(notifier, '_dispatch_email_and_maintain_warnings'), \
       'function moved to notifier accidentally — should be in main.py per agreed-3'

   def test_loc_under_500(): 
     import pathlib
     for f in pathlib.Path('notifier').glob('*.py'):
       loc = f.read_text().count('\n')
       assert loc < 550, f'{f} exceeded LOC budget: {loc}'   # ±10% tolerance per M1
   ```
  </action>
  <verify>
    <automated>pytest tests/test_notifier_package_seam.py -x -v</automated>
  </verify>
  <done>4 parity tests green.</done>
</task>

</tasks>

<threat_model>
N/A — pure code reorganisation. The XSS / redact-secret / FIFO bound from Waves 1-2 are PRESERVED by the split.
</threat_model>

<verification>
```
pytest tests/test_notifier.py tests/test_notifier_package_seam.py -x   # NO test changes required
wc -l notifier/*.py    # all <500 (±10% tolerance)
ruff check notifier/
grep -rn '_dispatch_email_and_maintain_warnings' notifier/ main.py
# expected: zero matches in notifier/, present in main.py
grep -rn '^import notifier\|^from notifier' --include='*.py' | grep -v '^tests/'
```
</verification>

<success_criteria>
- notifier/ is a package; each file <500 LOC (±10% tolerance per M1).
- Public API parity (tests/test_notifier.py unchanged + green).
- Monkeypatch targets preserved (notifier.requests, notifier._post_to_resend).
- _dispatch_email_and_maintain_warnings STAYS in main.py.
- Two-commit pattern: shim → grep-verified delete (or kept with rationale).
- 4 new parity tests green.
- Full suite green.
- ruff clean.
</success_criteria>

<output>
Create `27-12-SUMMARY.md` with: manifest summary (file → seam mapping), monkeypatch-target list, public API list, line counts per new file, before/after wc -l, two-commit pattern outcome (delete or keep shim).
</output>
