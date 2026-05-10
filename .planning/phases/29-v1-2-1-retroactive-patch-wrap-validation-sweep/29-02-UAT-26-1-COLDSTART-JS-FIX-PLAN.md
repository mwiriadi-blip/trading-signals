---
phase: 29
plan_id: 29-02-UAT-26-1-COLDSTART-JS-FIX
plan: 02
type: execute
wave: 1
depends_on: []
requirements: []
files_modified:
  - dashboard_legacy/section_renderers.py
  - tests/uat/test_uat_26_coldstart.py
autonomous: true
must_haves:
  truths:
    - "Equity-chart inline JS y-axis option block is brace-balanced; cold-start dashboard has zero JS `pageerror` on first paint."
    - "UAT-26-1 regression: `pytest -m uat tests/uat/test_uat_26_coldstart.py` asserts zero `pageerror` events on initial load."
  artifacts:
    - path: "dashboard_legacy/section_renderers.py"
      provides: "Brace-balanced equityChart inline JS scales config (y axis closes correctly)"
      contains: "y: {"
    - path: "tests/uat/test_uat_26_coldstart.py"
      provides: "Regression test asserting no pageerror on cold-start"
      exports: []
  key_links:
    - from: "dashboard_legacy/section_renderers.py:218-220"
      to: "browser JS parser"
      via: "balanced braces in y-axis ticks/grid block"
      pattern: "y: \\{ ticks: \\{[^}]*\\}, grid: \\{[^}]*\\} \\}"
---

<objective>
Resolve Phase 28 FAIL UAT-26-1 (28-VERIFICATION.md row): equityChart inline JS y-axis brace bug at `dashboard_legacy/section_renderers.py:218-220` causes a `missing ) after argument list` JS pageerror on every cold-start load. One-line structural fix at known file:line + UAT regression test.

Purpose: Visible to every authenticated user — cold-start dashboard fails to initialise the equity chart and the JS error blocks downstream HTMX wiring.
Output: brace-balanced y-axis options block + regression test extending the Phase 28 `tests/uat/` substrate.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-CONTEXT.md
@.planning/phases/28-v1-2-uat-closure/28-VERIFICATION.md

<read_first>
- `dashboard_legacy/section_renderers.py:200-235` (the equityChart options block and its surrounding render function)
- 28-VERIFICATION.md row "Cold-start smoke | 26 / UAT-1 | MCP | FAIL" — explicit symptom and suspected file:line
- 29-CONTEXT.md §D-05 (one-line fix at known file:line — no discussion needed)
- `tests/uat/conftest.py` and `tests/uat/test_uat_26_coldstart.py` (existing UAT substrate from Phase 28 plan 28-01 + 28-05)
</read_first>

<interfaces>
The Phase 28 UAT substrate provides:
- `@pytest.mark.uat` marker (gated out of default suite via `pyproject.toml` `addopts`)
- `tests/uat/conftest.py` `uat_credentials()` fixture + auth wiring (`.env.uat` loader, header injection via `page.route()`)
- A live or staged droplet target. `tests/uat/test_uat_26_coldstart.py` already EXISTS — this plan EXTENDS it (or adds a new test method) to assert zero pageerror on cold-start, not just selector presence.

Browser-side: Playwright `page.on('pageerror', handler)` collects JS errors. The Phase 28 evidence shows the existing test catches selectors fine; the FAIL was diagnosed via separate MCP run capturing pageerror.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Fix equityChart y-axis brace structure</name>
  <files>dashboard_legacy/section_renderers.py</files>
  <read_first>
    - dashboard_legacy/section_renderers.py:200-235 (the chart options block; the y axis runs from line 218 to ~220)
    - 28-VERIFICATION.md UAT-26-1 evidence cell (root cause one-liner)
  </read_first>
  <action>
    Per D-05: the current rendered JS is structurally:
    ```
    y: { ticks: { color: ..., callback: ... }},
       grid: { color: ... }}
    ```
    which closes the `y` object after `ticks` (the second `}` on the line ending `}},`) and leaves `grid: { color: ... }}` as a stray sibling with one unmatched `}`. The intent is one `y` object containing `ticks` AND `grid`.

    Restructure lines 218-220 of `dashboard_legacy/section_renderers.py` so the y axis renders as:
    ```
    y: { ticks: { color: "<TEXT_MUTED>", callback: (v) => "$" + v.toLocaleString() },
         grid: { color: "<BORDER>" } }
    ```

    Concretely: change the f-string fragment so:
    - `ticks: { ... }` closes with a single `}` followed by `,`
    - `grid: { color: "..." }` closes with a single `}`
    - the outer `y: { ... }` closes with a single `}`

    Compare to the surrounding `x: { type: "category", ticks: {...}, grid: {...} }` on lines 215-217 which IS correctly balanced — mirror that shape for `y`.

    Do NOT change indentation/whitespace in unrelated regions; minimise the diff. Do NOT touch the `_COLOR_TEXT_MUTED` / `_COLOR_BORDER` constants.

    File-size check: `dashboard_legacy/section_renderers.py` must remain ≤500 LOC after edit (CLAUDE.md cap). The edit is a brace rebalance, not a size change.
  </action>
  <acceptance_criteria>
    - `wc -l dashboard_legacy/section_renderers.py` ≤500.
    - `grep -nE "y: \\{ ticks: \\{" dashboard_legacy/section_renderers.py` matches exactly the y-axis line in the equityChart block.
    - Brace-count sanity: extract the multi-line `options:` block and confirm `{` count equals `}` count for the JS literal as written. Use `python -c "import ast; src=open('dashboard_legacy/section_renderers.py').read(); ..."` or a manual brace-count grep — whichever the executor finds simplest. The structural rule: every `{` in the rendered JS must have a matching `}`.
    - `python -c "from dashboard_legacy.section_renderers import _render_equity_chart_section" 2>&1 | grep -c SyntaxError` returns 0 (Python parse still clean).
    - Render the section against a fixture and check it: `python -c "from dashboard_legacy.section_renderers import _render_equity_chart_section; html = _render_equity_chart_section([{'date':'2026-01-01','equity':10000.0},{'date':'2026-01-02','equity':10100.0}]); js_block = html.split('<script>')[1].split('</script>')[0]; opens = js_block.count('{'); closes = js_block.count('}'); assert opens == closes, (opens, closes); print('balanced', opens)"` exits 0 and prints `balanced N` with N>0.
  </acceptance_criteria>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && python -c "from dashboard_legacy.section_renderers import _render_equity_chart_section; html = _render_equity_chart_section([{'date':'2026-01-01','equity':10000.0},{'date':'2026-01-02','equity':10100.0},{'date':'2026-01-03','equity':10200.0},{'date':'2026-01-04','equity':10150.0},{'date':'2026-01-05','equity':10300.0}]); js_block = html.split('<script>')[1].split('</script>')[0]; opens = js_block.count('{'); closes = js_block.count('}'); assert opens == closes, (opens, closes); print('balanced', opens)"</automated>
  </verify>
  <done>Equity-chart inline JS is brace-balanced; cold-start render produces parseable JavaScript.</done>
</task>

<task type="auto">
  <name>Task 2: UAT regression test — zero pageerror on cold-start</name>
  <files>tests/uat/test_uat_26_coldstart.py</files>
  <read_first>
    - tests/uat/test_uat_26_coldstart.py (existing test methods + import surface)
    - tests/uat/conftest.py (auth wiring + page fixture pattern)
    - 28-VERIFICATION.md UAT-26-1 row (the repro command is `pytest -m uat tests/uat/test_uat_26_coldstart.py`)
  </read_first>
  <action>
    Add a new test method `test_no_pageerror_on_coldstart` to `tests/uat/test_uat_26_coldstart.py` (or extend the existing class — match whichever shape is already there). The method:

    1. Collects `pageerror` events into a list via `page.on('pageerror', errors.append)`.
    2. Navigates to `/markets/SPI200/dashboard` (or whichever path the existing test uses for cold-start) with auth wiring from `conftest.py`.
    3. Waits for `networkidle` or for a stable selector that proves the page settled.
    4. Asserts `len(errors) == 0` with a message that prints the captured error texts on failure: `assert errors == [], f'JS pageerror(s): {[str(e) for e in errors]}'`.
    5. Decorated with `@pytest.mark.uat` so it stays gated out of the default suite.

    Test should run in <10s. Match the structure of the existing UAT test methods — do NOT introduce a new auth pattern or a new fixture if one already serves.

    File-size check: `tests/uat/test_uat_26_coldstart.py` must remain ≤500 LOC.
  </action>
  <acceptance_criteria>
    - `wc -l tests/uat/test_uat_26_coldstart.py` ≤500.
    - `grep -q "test_no_pageerror_on_coldstart" tests/uat/test_uat_26_coldstart.py` succeeds.
    - `grep -q "page.on('pageerror'" tests/uat/test_uat_26_coldstart.py` (or `pageerror`) succeeds.
    - `grep -q "@pytest.mark.uat" tests/uat/test_uat_26_coldstart.py` (existing decorator usage preserved or added).
    - `pytest -m uat tests/uat/test_uat_26_coldstart.py::*test_no_pageerror_on_coldstart -q` returns rc=0 (the brace fix from Task 1 is what makes it green).
  </acceptance_criteria>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && .venv/bin/pytest -m uat tests/uat/test_uat_26_coldstart.py -k test_no_pageerror_on_coldstart -q</automated>
  </verify>
  <done>Regression test exists, runs under `pytest -m uat`, captures `pageerror` events, asserts zero errors on cold-start. Locks the brace fix in.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| browser JS parser | malformed inline JS breaks every authenticated page |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-29-02-01 | DoS (self) | Inline JS syntax error blocks all dashboard JS on cold-start | mitigate | Brace-balance fix at line 218-220 + UAT pageerror regression test |
| T-29-02-02 | Tampering (XSS) | Re-introduction of malformed JS during future edits | accept | Pre-existing render-time HTML escape (`_e()`) + Phase 27 XSS audit cover content; brace-balance is structural, not data-driven |
</threat_model>

<verification>
- Full default suite green: `.venv/bin/pytest -q` rc=0.
- UAT cold-start green: `pytest -m uat tests/uat/test_uat_26_coldstart.py -q` rc=0.
- Manual: visit `/markets/SPI200/dashboard` with DevTools open, assert console clean.
</verification>

<success_criteria>
Phase 28 FAIL row UAT-26-1 has a passing automated regression. Phase 29 closure plan (29-14) appends PASS row to 28-VERIFICATION.md citing this plan.
</success_criteria>

<output>
After completion, create `.planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-02-SUMMARY.md`.
</output>