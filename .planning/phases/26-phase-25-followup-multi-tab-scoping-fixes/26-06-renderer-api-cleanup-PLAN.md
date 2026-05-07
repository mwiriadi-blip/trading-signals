---
phase: 26
plan: 06
type: execute
wave: 3
parallel: true
depends_on:
  - 26-04-template-substitute-helper-PLAN.md
  - 26-05-active-market-scoping-PLAN.md
files_modified:
  - dashboard_renderer/api.py
  - dashboard.py
  - web/routes/dashboard.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "render_dashboard_files returns None — pure file-write"
    - "render_panel_html returns str — HTMX panel-only path"
    - "No mixed-return-type function in dashboard_renderer.api"
    - "nav_mode parameter removed from _render_single_page_dashboard and render_dashboard_page"
    - "Deprecated _render_dashboard_page_nav deleted"
  artifacts:
    - path: dashboard_renderer/api.py
      provides: "Split render_dashboard_files (None) + render_panel_html (str)"
      contains: "render_panel_html"
    - path: dashboard.py
      provides: "_render_dashboard_page_nav deleted; nav_mode dropped"
      contains: "_render_single_page_dashboard"
  key_links:
    - from: "web/routes/dashboard.py"
      to: "render_panel_html"
      via: "HTMX panel call site"
      pattern: "render_panel_html\\("
---

<objective>
R2 + R4. Split `render_dashboard()` mixed-return into `render_dashboard_files() -> None` (file-write) + `render_panel_html() -> str` (panel-only). Drop `nav_mode` dead param. Delete DEPRECATED `_render_dashboard_page_nav`.

Purpose: Eliminate annotation-vs-return-type lie that lets `.encode()`-on-None NPEs ship.
Output: Two clear functions with correct types. Dead code gone.
</objective>

<context>
@.planning/phases/26-phase-25-followup-multi-tab-scoping-fixes/26-CONTEXT.md
@.planning/phases/26-phase-25-followup-multi-tab-scoping-fixes/26-PATTERNS.md
@dashboard_renderer/api.py
@dashboard_renderer/pages.py
@dashboard.py
@web/routes/dashboard.py

<interfaces>
# Today's mixed shape:
#   render_dashboard(state, ..., htmx_panel_only=False) -> None  # annotation
#   when htmx_panel_only=True → returns str  # actual at lines 85-89
# Existing partner already correct:
#   render_dashboard_as_str(state, ...) -> str  (api.py:116-140)
# Existing panel-only emitter:
#   render_panel_only(ctx) -> str  (dashboard_renderer/pages.py:20-37)
# Caller of htmx_panel_only=True:
#   web/routes/dashboard.py:259-266 inside _serve_market_scoped_page (HTMX panel branch)
# Dead code to delete:
#   dashboard.py:2083-end-of-fn  _render_dashboard_page_nav  (DEPRECATED, 0 callers)
#   dashboard.py:2050  nav_mode parameter on _render_single_page_dashboard (unreferenced inside body)
#   dashboard_renderer/api.py:110  nav_mode parameter on render_dashboard_page (only ever 'web'/'file')
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Split render_dashboard into render_dashboard_files + render_panel_html</name>
  <files>dashboard_renderer/api.py</files>
  <action>
1. Define new public function `render_panel_html(state, *, active_market: str | None = None, ...) -> str` that builds RenderContext and calls `render_panel_only(ctx)` from `dashboard_renderer/pages.py`.
2. Rename `render_dashboard` → `render_dashboard_files` and:
   - Drop `htmx_panel_only` parameter entirely.
   - Set return annotation to `-> None`.
   - Remove the `if htmx_panel_only: return ...` branch.
3. Keep all existing file-write behaviour (4 sibling files + main dashboard.html via _atomic_write_html).
4. Add import-shim for backward compat IF any non-test caller exists: scan with `grep -rn 'render_dashboard(' --include='*.py' | grep -v render_dashboard_files\|render_dashboard_as_str\|render_dashboard_page\|render_panel_html`. For every match, update the call site.
5. `render_dashboard_as_str` and `render_dashboard_page` left unchanged structurally (Plan 05 already added active_market to render_dashboard_page).
  </action>
  <verify>
    <automated>python -c "from dashboard_renderer.api import render_dashboard_files, render_panel_html; import inspect; assert inspect.signature(render_dashboard_files).return_annotation is None or 'None' in str(inspect.signature(render_dashboard_files).return_annotation); assert 'str' in str(inspect.signature(render_panel_html).return_annotation)"</automated>
  </verify>
  <done>Both functions exist with correct annotations; no `htmx_panel_only` param remains.</done>
</task>

<task type="auto">
  <name>Task 2: Update HTMX panel call site + drop nav_mode + delete _render_dashboard_page_nav</name>
  <files>web/routes/dashboard.py, dashboard.py, dashboard_renderer/api.py</files>
  <action>
1. web/routes/dashboard.py: in `_serve_market_scoped_page` (~line 259-266), replace the `dashboard.render_dashboard(state, htmx_panel_only=True, ...)` call with `from dashboard_renderer.api import render_panel_html; body = render_panel_html(state, active_market=market_id, ...)`. Verify the surrounding `body.encode('utf-8')` then `_substitute(body_bytes, request)` chain (Plan 04) still applies.
2. dashboard.py: locate `_render_single_page_dashboard` (~line 2050). Drop `nav_mode` parameter. Audit body for `nav_mode` references — should be zero per 26-PATTERNS §R4. If any exist, prefer the 'file' branch (sibling-regen path).
3. dashboard.py: delete `_render_dashboard_page_nav` function (line 2083 to end-of-function, ~30 lines).
4. dashboard_renderer/api.py: `render_dashboard_page` — drop `nav_mode` parameter from signature. Audit for body references; remove if any.
5. Update any callers passing `nav_mode=` kwarg to drop it. Grep: `grep -rn 'nav_mode' --include='*.py' .`
  </action>
  <verify>
    <automated>grep -rn 'nav_mode\|_render_dashboard_page_nav' --include='*.py' . | grep -v '\.git\|test_\|26-\|25-' | wc -l</automated>
  </verify>
  <done>Grep returns 0. Suite green: `pytest -x`.</done>
</task>

</tasks>

<verification>
```
pytest tests/test_web_app_factory.py tests/test_web_dashboard.py tests/test_dashboard.py -x
grep -rn 'render_dashboard(' --include='*.py' . | grep -v '_files\|_as_str\|_page\|_nav\|test_\|26-\|25-' || true
grep -rn 'nav_mode\|_render_dashboard_page_nav' --include='*.py' . | grep -v 'test_\|26-\|25-' || true
```
Both grep tails empty.
</verification>

<success_criteria>
- `render_dashboard_files` returns None per annotation.
- `render_panel_html` returns str per annotation.
- No `htmx_panel_only` parameter anywhere.
- No `nav_mode` parameter anywhere.
- `_render_dashboard_page_nav` deleted.
- Full pytest green.
</success_criteria>

## Rollback

`git revert <plan-06-commit>`. Function rename creates a clean diff; rename-back restores prior shape. No data changes.

## Notes

Pattern map: 26-PATTERNS.md §R2 + §R4. `render_panel_only` body in pages.py:20-37 already exists — promote signature, not the body.

C2 (delete _render_dashboard_page_nav) absorbed here; Plan 26-08 only handles _render_market_selector + doc cleanup.

<output>
Create `26-06-SUMMARY.md` listing function signatures before/after + grep verdicts.
</output>
