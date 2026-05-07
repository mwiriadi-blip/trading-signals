---
phase: 27
plan: 14
type: execute
wave: 3
parallel: true
depends_on:
  - 27-08-html-escape-audit-PLAN.md
  - 27-09-signal-shape-unification-PLAN.md
  - 27-11-crash-email-fallback-PLAN.md
files_modified:
  - dashboard.py
  - dashboard_legacy/__init__.py
  - dashboard_legacy/page_body.py
  - dashboard_legacy/render_helpers.py
  - dashboard_legacy/section_renderers.py
  - tests/test_dashboard_split_seam.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "dashboard.py either becomes <500 LOC OR is converted to a package whose files are each <500 LOC."
    - "Web routes (web/routes/dashboard.py) continue to work unchanged."
    - "Rendered HTML output is byte-identical to pre-split (visual diff = empty)."
    - "tests/test_dashboard.py + tests/test_dashboard_renderer.py pass without test changes."
    - "dashboard_renderer/ package (separate from this monolith) is unaffected."
  artifacts:
    - path: dashboard.py
      provides: "either thin entry-point shim OR reduced to <500 LOC"
      contains: "render_dashboard"
  key_links:
    - from: "web/routes/dashboard.py"
      to: "dashboard.<API>"
      via: "import unchanged"
      pattern: "import dashboard"
---

<objective>
Split dashboard.py (2212 LOC) into package modules. Note the project ALREADY has `dashboard_renderer/` — this remaining `dashboard.py` is the legacy server-side renderer / FastAPI route surface. Target: each module <500 LOC, OR consolidate the legacy code into dashboard_renderer/ if a clean migration path exists.

Sequenced LAST in Wave 3 so all functional changes from earlier plans (HTML escape audit, signal-shape unification removing isinstance(int) branch in dashboard_renderer/components/signals.py, crash-email banner integration in render_status_strip) land BEFORE the split.

Purpose: file-size hygiene (review item #4).
Output: dashboard.py reorganised + line counts <500 + byte-identical HTML output.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@dashboard.py

<interfaces>
# Two viable strategies — Task 1 will pick based on actual content:
#
# Strategy A: Migrate-into-dashboard_renderer (most eloquent if seams align)
#   The dashboard_renderer/ package already owns the modern rendering API. If most of dashboard.py's
#   2212 LOC is renderer-helpers that haven't been migrated yet, fold them into dashboard_renderer/
#   as new component files. dashboard.py shrinks to a thin shim re-exporting names that web/routes
#   reference.
#
# Strategy B: Create dashboard_legacy/ package (most pragmatic if dashboard.py has cross-cutting
# concerns that don't fit the dashboard_renderer/ component model)
#   Create dashboard_legacy/ with these seams:
#     - page_body.py        — _render_page_body and full-page assembly
#     - render_helpers.py   — small string/HTML helpers
#     - section_renderers.py — per-section render functions (positions table, equity chart, etc.)
#   dashboard.py becomes a re-export shim.
#
# > Most eloquent: Strategy A IF the content is mostly already-ported helpers. Strategy B IF
# > dashboard.py has logic that doesn't fit dashboard_renderer/'s component model (e.g. a single
# > big `_render_page_body` function that's an entry point, not a component).
#
# Read dashboard.py first to decide. Document choice in 27-14-SUMMARY.md.
#
# Test invariant: byte-identical HTML output across split. Use the existing dashboard_renderer
# golden-snapshot pattern (per Phase 25 plan 25-11) — render before, render after, diff bytes.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Inventory dashboard.py — pick strategy + manifest</name>
  <read_first>
    - dashboard.py (full — 2212 LOC; read in chunks of ~500)
    - dashboard_renderer/ — list current components
    - web/routes/dashboard.py — capture what it imports from dashboard.*
    - tests/test_dashboard.py + tests/test_dashboard_renderer.py — public API surface
  </read_first>
  <action>
1. Read dashboard.py in chunks. Classify each function as:
   - **(A) Could fit dashboard_renderer/ component model** (pure render-helpers, no I/O, takes RenderContext-shaped input).
   - **(B) Cross-cutting / entry-point** (orchestrates a full page, has I/O, doesn't fit component model).
2. If >70% is type A → use Strategy A (migrate into dashboard_renderer/).
3. Otherwise → Strategy B (create dashboard_legacy/ package).
4. Capture web/routes/dashboard.py's import surface from dashboard:
   ```bash
   grep -n 'import dashboard\|from dashboard import' web/routes/dashboard.py
   ```
   Every reference is a shim re-export.
5. Capture tests' references:
   ```bash
   grep -n 'dashboard\.' tests/test_dashboard.py tests/test_dashboard_renderer.py
   ```
6. Write manifest at `.planning/phases/27-code-quality-correctness-sweep-apply-2026-05-07-code-review-/dashboard-split-manifest.md` with:
   - chosen strategy + 1-line rationale (locality of behaviour, contract preservation)
   - line-range → target file mapping
   - re-exports needed in dashboard.py
   - byte-identical-HTML test plan (use existing golden-snapshot fixture or build a fresh one)
  </action>
  <verify>
    <automated>test -f .planning/phases/27-code-quality-correctness-sweep-apply-2026-05-07-code-review-/dashboard-split-manifest.md</automated>
  </verify>
  <done>Manifest written; strategy chosen and justified; re-export list complete.</done>
</task>

<task type="auto">
  <name>Task 2: Execute split per chosen strategy</name>
  <read_first>
    - manifest from Task 1
    - dashboard.py
  </read_first>
  <action>
1. **Capture pre-split HTML golden:** render dashboard for canonical fixture state; save bytes to a temp path.
2. Execute the chosen strategy (A or B per Task 1).
   - **Strategy A:** create new component files in dashboard_renderer/components/; move functions; update dashboard_renderer/__init__.py if needed.
   - **Strategy B:** create dashboard_legacy/ package; move functions; create __init__.py with re-exports.
3. Update dashboard.py to be either a thin shim (Strategy A → re-export from dashboard_renderer; Strategy B → re-export from dashboard_legacy).
4. **Render post-split:** invoke render with same fixture state; capture bytes; diff against pre-split.
5. If diff is non-empty → STOP, debug, do not commit. The split is done WHEN bytes match.
6. Run `pytest tests/test_dashboard.py tests/test_dashboard_renderer.py -x` — MUST pass unchanged.
7. Run full `pytest -x`.
8. Verify line counts: every file <500 LOC.
9. Update web/routes/dashboard.py imports ONLY if Task 1 found re-export gaps the shim couldn't cover (the shim should make it unnecessary).
  </action>
  <verify>
    <automated>pytest tests/test_dashboard.py tests/test_dashboard_renderer.py -x</automated>
  </verify>
  <done>
    - Split executed per chosen strategy.
    - Pre-split / post-split HTML byte-identical.
    - Every file <500 LOC.
    - Existing dashboard tests green without test changes.
    - Full suite green.
  </done>
</task>

<task type="auto">
  <name>Task 3: Parity test — line-count + byte-identity</name>
  <read_first>
    - tests/test_dashboard_renderer.py (golden-snapshot pattern)
  </read_first>
  <action>
1. **tests/test_dashboard_split_seam.py (NEW):**
   ```python
   import pathlib
   def test_dashboard_files_under_500_loc():
     suspects = [pathlib.Path('dashboard.py')]
     for d in ['dashboard_renderer/components', 'dashboard_legacy']:
       p = pathlib.Path(d)
       if p.is_dir():
         suspects.extend(p.glob('*.py'))
     for f in suspects:
       loc = f.read_text().count('\n')
       assert loc < 500, f'{f} exceeded 500 LOC: {loc}'

   def test_dashboard_html_output_byte_identical(canonical_state):
     # Reuse the existing golden-snapshot fixture from tests/test_dashboard_renderer.py.
     # If the fixture name differs, adapt.
     from dashboard import render_dashboard  # or whatever the public entry point is
     out = render_dashboard(canonical_state)
     golden = pathlib.Path('tests/fixtures/dashboard_canonical.html').read_bytes()
     assert out == golden, 'HTML output drifted across split'
   ```
   Adjust `canonical_state` fixture name to whatever the existing test suite provides.
  </action>
  <verify>
    <automated>pytest tests/test_dashboard_split_seam.py -x -v</automated>
  </verify>
  <done>2 parity tests green.</done>
</task>

</tasks>

<threat_model>
N/A — pure code reorganisation. The XSS hardening from Plan 27-08 is preserved by the split (it's already in dashboard.py / dashboard_renderer/ before this plan runs).
</threat_model>

<verification>
```
pytest tests/test_dashboard.py tests/test_dashboard_renderer.py tests/test_dashboard_split_seam.py -x
wc -l dashboard.py dashboard_legacy/*.py 2>/dev/null || wc -l dashboard.py dashboard_renderer/components/*.py
pytest -x   # full suite
```
</verification>

<success_criteria>
- dashboard.py + every co-package file <500 LOC.
- HTML output byte-identical to pre-split.
- Existing tests green unchanged.
- 2 new parity tests green.
- web/routes/dashboard.py imports unchanged (or only re-exports adjusted).
</success_criteria>

<output>
Create `27-14-SUMMARY.md` with: chosen strategy (A or B) + rationale, manifest summary, line counts before/after, byte-identity test outcome.
</output>
