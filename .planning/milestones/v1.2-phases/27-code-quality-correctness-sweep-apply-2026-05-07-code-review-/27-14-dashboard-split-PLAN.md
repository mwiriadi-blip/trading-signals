---
phase: 27
plan: 14
type: execute
wave: 3
parallel: false  # <!-- review-fix: agreed-1 — Wave 3 sequential -->
depends_on:
  - 27-08-html-escape-audit-PLAN.md  # <!-- review-fix: agreed-10 — golden captured AFTER -->
  - 27-11-crash-email-fallback-PLAN.md  # <!-- review-fix: agreed-10 — banner changes baked in BEFORE -->
  - 27-12-notifier-split-PLAN.md  # sequential per agreed-1
  - 27-13-main-split-PLAN.md  # sequential per agreed-1
  - 27-09-signal-shape-unification-PLAN.md
files_modified:
  - dashboard.py
  - dashboard_legacy/__init__.py
  - dashboard_legacy/page_body.py
  - dashboard_legacy/render_helpers.py
  - dashboard_legacy/section_renderers.py
  - tests/test_dashboard_split_seam.py
  - tests/fixtures/dashboard_canonical.html  # <!-- review-fix: agreed-10 — captured AFTER 27-08+27-11 land -->
autonomous: true
requirements: []
must_haves:
  truths:
    - "dashboard.py either becomes <500 LOC OR is converted to a package whose files are each <500 LOC."
    - "Web routes (web/routes/dashboard.py) continue to work unchanged."
    - "Rendered HTML output is byte-identical to PRE-SPLIT (golden captured AFTER 27-08 escaping + 27-11 crash banner LAND, BEFORE any dashboard.py move)."
    - "Golden fixture records the HEAD commit SHA used for capture as a file-comment for traceability."
    - "Strategy chosen (A migrate-into-dashboard_renderer or B dashboard_legacy package) is documented with rationale; preferred B unless A clearly reduces duplication."
    - "Route-level smoke tests through FastAPI in addition to renderer unit tests."
    - "tests/test_dashboard.py + tests/test_dashboard_renderer.py pass without test changes."
    - "dashboard_renderer/ package (separate from this monolith) is unaffected."
  artifacts:
    - path: dashboard.py
      provides: "either thin entry-point shim OR reduced to <500 LOC"
      contains: "render_dashboard"
    - path: tests/fixtures/dashboard_canonical.html
      provides: "byte-golden captured AFTER 27-08+27-11 land"
      contains: "<!-- captured at HEAD"
  key_links:
    - from: "web/routes/dashboard.py"
      to: "dashboard.<API>"
      via: "import unchanged"
      pattern: "import dashboard"
---

## Review fixes applied

- [x] agreed-1 (wave/dependency rebuild) — wave 3 SEQUENTIAL; depends_on=[27-08, 27-11, 27-12, 27-13, 27-09] explicit (27-09 because dashboard renderer cleanup depends on signal-shape migration).
- [x] agreed-10 (Codex HIGH golden capture timing) — explicit ordering: golden captured AT HEAD AFTER 27-08 + 27-11 are committed, BEFORE any dashboard.py move/edit. The HEAD commit SHA used for capture is recorded in the fixture as a file-comment for traceability. Capture task is the FIRST task in this plan; split execution is the SECOND task.
- [x] agreed-10 (route-level smoke tests via FastAPI) — added beyond renderer unit tests. Tests hit FastAPI endpoints `/markets/SPI200/...` and assert response is structurally identical pre/post-split.
- [x] agreed-10 (Strategy B preferred unless A clearly wins) — explicit guidance: choose B (dashboard_legacy/ package) by default; only choose A if Task 0 inventory shows >70% of dashboard.py is already-componentizable (low likelihood given 2212 LOC monolith). State chosen strategy + rationale in plan rationale at execution time.
- [x] M1 (brittle implementation tests) — LOC tests use ±10% tolerance.
- [x] M2 (doc rule) — manifest stays inside `.planning/phases/27-.../`.

<objective>
Split dashboard.py (2212 LOC) into package modules. The project ALREADY has `dashboard_renderer/` — this plan addresses the legacy server-side renderer / FastAPI route surface.

**Critical sequencing (review-fix agreed-10):** golden HTML capture happens AFTER 27-08 (escaping) and 27-11 (crash banner) land. Otherwise any byte-identity test against an older snapshot would fail spuriously due to escaping or banner additions. The golden snapshot records the EXACT POST-FUNCTIONAL-CHANGES output; the split must preserve THAT output byte-for-byte.

Target: each module <500 LOC (±10% per M1), OR consolidate into dashboard_renderer/ if a clean migration path exists.

Sequenced LAST in Wave 3 (after 27-13 main split) so the dashboard split sees the post-functional-change codebase.

Purpose: file-size hygiene (review item #4).
Output: dashboard.py reorganised + line counts <500 + byte-identical HTML output preserved.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@dashboard.py

<interfaces>
# Two viable strategies:
#
# Strategy A: Migrate-into-dashboard_renderer (chosen IF >70% type-A content)
#   The dashboard_renderer/ package already owns the modern rendering API. If most of dashboard.py's
#   2212 LOC is renderer-helpers that haven't been migrated yet, fold them into dashboard_renderer/
#   as new component files.
#
# Strategy B: Create dashboard_legacy/ package (DEFAULT — review-fix agreed-10)
#   Create dashboard_legacy/ with these seams:
#     - page_body.py        — _render_page_body and full-page assembly
#     - render_helpers.py   — small string/HTML helpers
#     - section_renderers.py — per-section render functions
#   dashboard.py becomes a re-export shim.
#
# > **Most eloquent (review-fix agreed-10):** Strategy B by default. dashboard.py likely contains
# > a single big `_render_page_body` orchestrator that doesn't fit the dashboard_renderer/
# > component model. Folding it into dashboard_renderer/ would muddy that package's responsibility
# > (component-level rendering vs page-level orchestration). Locality argues for a dedicated
# > legacy package.
#
# Test invariants:
#   1. Byte-identical HTML output across split (golden captured AFTER 27-08+27-11).
#   2. FastAPI route-level smoke tests (review-fix agreed-10) — hit /markets/SPI200/... and assert
#      structural identity pre/post-split.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Capture golden HTML AFTER 27-08+27-11 land, BEFORE any dashboard.py move</name>
  <!-- review-fix: agreed-10 — pin capture timing -->
  <read_first>
    - dashboard.py — current public render entry point
    - tests/test_dashboard_renderer.py — existing canonical-state fixture
  </read_first>
  <behavior>
    - Golden capture happens in the SAME commit as the manifest (Task 1), AFTER all functional changes from 27-08 + 27-11 are merged into the working tree.
    - Fixture file records HEAD commit SHA in a file-comment for traceability.
    - test_golden_records_post_functional_state: open tests/fixtures/dashboard_canonical.html — file exists AND first line/header is `<!-- captured at HEAD <SHA> after 27-08+27-11 -->`.
  </behavior>
  <action>
1. **Verify pre-conditions (review-fix agreed-10):** confirm working tree has 27-08 (HTML escape) + 27-11 (crash banner) committed. If either is missing, STOP — split cannot proceed safely.
   ```bash
   git log --oneline | grep -E '27-08|27-11'   # both must appear
   ```

2. **Capture canonical state fixture:** use the existing canonical_state fixture from tests/test_dashboard_renderer.py. Render dashboard:
   ```python
   import json, pathlib, subprocess
   from dashboard import render_dashboard   # or whatever the public entry is
   from tests.fixtures import canonical_state   # or however it's loaded
   head_sha = subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode().strip()
   html = render_dashboard(canonical_state)
   header = f'<!-- captured at HEAD {head_sha} after 27-08+27-11 -->\n'
   pathlib.Path('tests/fixtures/dashboard_canonical.html').write_bytes(
     (header + html).encode('utf-8')
   )
   ```

3. **Sanity-check the golden:** verify it contains expected post-27-08 markers (escaped untrusted text where applicable) and post-27-11 markers (crash banner shape if `last_crash.json` is in fixture state, OR no banner if absent). Document either way in 27-14-SUMMARY.md.

4. Commit: `test(27-14): capture dashboard golden HTML at HEAD after 27-08+27-11`.
  </action>
  <verify>
    <automated>test -f tests/fixtures/dashboard_canonical.html && head -1 tests/fixtures/dashboard_canonical.html | grep -q 'captured at HEAD'</automated>
  </verify>
  <done>
    - tests/fixtures/dashboard_canonical.html exists.
    - First line records HEAD SHA + post-27-08+27-11 marker.
    - Sanity-check passes (post-functional-change markers visible).
  </done>
</task>

<task type="auto">
  <name>Task 2: Inventory dashboard.py — pick strategy + manifest</name>
  <read_first>
    - dashboard.py (full — 2212 LOC; read in chunks of ~500)
    - dashboard_renderer/ — list current components
    - web/routes/dashboard.py — capture imports from dashboard.*
    - tests/test_dashboard.py + tests/test_dashboard_renderer.py — public API surface
  </read_first>
  <action>
1. Read dashboard.py in chunks. Classify each function as:
   - **(A) Could fit dashboard_renderer/ component model** (pure render-helpers, no I/O, takes RenderContext-shaped input).
   - **(B) Cross-cutting / entry-point** (orchestrates a full page, has I/O, doesn't fit component model).

2. **Strategy decision (review-fix agreed-10 default = B):**
   - If >70% type A → Strategy A.
   - **DEFAULT → Strategy B** (dashboard_legacy/ package). Choose A only if Task 0 inventory clearly shows component-fit majority.

3. Capture web/routes/dashboard.py's import surface:
   ```bash
   grep -n 'import dashboard\|from dashboard import' web/routes/dashboard.py
   ```

4. Capture tests' references:
   ```bash
   grep -n 'dashboard\.' tests/test_dashboard.py tests/test_dashboard_renderer.py
   ```

5. Write manifest at `.planning/phases/27-.../dashboard-split-manifest.md`:
   - chosen strategy + 1-line rationale
   - line-range → target file mapping
   - re-exports needed in dashboard.py
   - byte-identical-HTML test plan (uses Task 1 golden)
   - FastAPI route smoke-test plan (review-fix agreed-10)
  </action>
  <verify>
    <automated>test -f .planning/phases/27-code-quality-correctness-sweep-apply-2026-05-07-code-review-/dashboard-split-manifest.md</automated>
  </verify>
  <done>Manifest written; strategy chosen and justified; re-export list complete.</done>
</task>

<task type="auto">
  <name>Task 3: Execute split per chosen strategy</name>
  <read_first>
    - manifest from Task 2
    - golden from Task 1
    - dashboard.py
  </read_first>
  <action>
1. **Re-render BEFORE moving anything:** sanity check — current `render_dashboard(canonical_state)` matches the Task 1 golden byte-for-byte. If not, the working tree drifted between Task 1 and now → STOP, regenerate golden, restart Task 3.

2. **Execute the chosen strategy (A or B per Task 2).**
   - **Strategy A:** create new component files in dashboard_renderer/components/; move functions; update dashboard_renderer/__init__.py if needed.
   - **Strategy B (default):** create dashboard_legacy/ package; move functions; create __init__.py with re-exports.

3. Update dashboard.py to be a thin re-export shim.

4. **Re-render post-split:** render with same fixture state; capture bytes; diff against Task 1 golden.

5. If diff is non-empty → STOP, debug, do not commit. Split is done WHEN bytes match.

6. Run `pytest tests/test_dashboard.py tests/test_dashboard_renderer.py -x` — MUST pass unchanged.

7. Run full `pytest -x`.

8. Verify line counts: every file <500 LOC (±10%).

9. **Update web/routes/dashboard.py** ONLY if Task 2 found re-export gaps the shim couldn't cover.
  </action>
  <verify>
    <automated>pytest tests/test_dashboard.py tests/test_dashboard_renderer.py -x</automated>
  </verify>
  <done>
    - Split executed per chosen strategy.
    - Pre-split / post-split HTML byte-identical (golden = post-split).
    - Every file <500 LOC (±10%).
    - Existing dashboard tests green without changes.
    - Full suite green.
  </done>
</task>

<task type="auto">
  <name>Task 4: Parity test — line-count + byte-identity + FastAPI route smoke</name>
  <!-- review-fix: agreed-10 — added FastAPI route-level smoke -->
  <read_first>
    - tests/test_dashboard_renderer.py (golden-snapshot pattern)
    - web/routes/dashboard.py (FastAPI routes)
  </read_first>
  <action>
1. **tests/test_dashboard_split_seam.py (NEW):**
   ```python
   import pathlib
   from fastapi.testclient import TestClient

   def test_dashboard_files_under_500_loc():
     suspects = [pathlib.Path('dashboard.py')]
     for d in ['dashboard_renderer/components', 'dashboard_legacy']:
       p = pathlib.Path(d)
       if p.is_dir():
         suspects.extend(p.glob('*.py'))
     for f in suspects:
       loc = f.read_text().count('\n')
       assert loc < 550, f'{f} exceeded LOC budget: {loc}'   # ±10% tolerance per M1

   def test_dashboard_html_output_byte_identical(canonical_state):
     '''Golden = post-27-08+27-11 capture. Split must preserve byte-identical output.'''
     from dashboard import render_dashboard
     out = render_dashboard(canonical_state)
     golden = pathlib.Path('tests/fixtures/dashboard_canonical.html').read_text()
     # Strip the SHA header comment for comparison
     golden_body = golden.split('\n', 1)[1]
     assert out == golden_body, 'HTML output drifted across split'

   def test_fastapi_route_smoke():
     '''review-fix agreed-10: route-level test in addition to renderer unit tests.'''
     from web.app import app   # adjust to actual app entry
     client = TestClient(app)
     r = client.get('/markets/SPI200/dashboard')   # adjust to real route
     assert r.status_code == 200
     assert '<html' in r.text or '<!doctype' in r.text.lower()
     # Spot-check post-functional markers visible (depends on Task 1 golden contents)
     # e.g. last-crash banner CSS class if fixture state has last_crash.json
   ```
  </action>
  <verify>
    <automated>pytest tests/test_dashboard_split_seam.py -x -v</automated>
  </verify>
  <done>3 parity tests green (LOC, byte-identity, FastAPI route smoke).</done>
</task>

</tasks>

<threat_model>
N/A — pure code reorganisation. The XSS hardening from Plan 27-08 is preserved by the split.
</threat_model>

<verification>
```
pytest tests/test_dashboard.py tests/test_dashboard_renderer.py tests/test_dashboard_split_seam.py -x
wc -l dashboard.py dashboard_legacy/*.py 2>/dev/null || wc -l dashboard.py dashboard_renderer/components/*.py
pytest -x   # full suite
```
</verification>

<success_criteria>
- Golden HTML captured AFTER 27-08 + 27-11 land (HEAD SHA recorded in fixture).
- Strategy chosen (default B) + rationale documented.
- dashboard.py + every co-package file <500 LOC (±10%).
- HTML output byte-identical pre/post-split (golden = post-split).
- FastAPI route smoke tests green.
- Existing tests green unchanged.
- 3 new parity tests green.
- web/routes/dashboard.py imports unchanged (or only re-exports adjusted).
</success_criteria>

<output>
Create `27-14-SUMMARY.md` with: golden capture HEAD SHA, chosen strategy (A or B) + rationale, manifest summary, line counts before/after, byte-identity test outcome, FastAPI route smoke test outcome.
</output>
