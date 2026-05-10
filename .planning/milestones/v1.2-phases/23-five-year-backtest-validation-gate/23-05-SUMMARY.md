---
phase: 23
plan: 05
subsystem: backtest-render
tags: [pure-render, html, chart.js, sri, aria-tabs, xss-defence, json-injection-defence, hex-boundary, d-14, ui-spec]
requires:
  - backtest/render.py (Wave 0 stub from 23-01)
  - tests/test_backtest_render.py (Wave 0 skeleton from 23-01)
  - tests/fixtures/backtest/golden_report.json (Wave 0 fixture from 23-01)
  - backtest.metrics.compute_metrics output schema (Wave 1C 23-04)
provides:
  - backtest.render.render_report(report) -> str (BACKTEST-03 HTML body fragment)
  - backtest.render.render_history(reports) -> str (history table + 10-cap overlay)
  - backtest.render.render_run_form(defaults) -> str (D-14 override form + spinner + disable-submit script)
  - 29 passing tests across 7 named test classes
affects:
  - web/routes/backtest.py (Wave 2 Plan 23-07 — will call these render functions)
tech-stack:
  added: []
  patterns:
    - Chart.js URL+SRI duplicated (NOT imported) from dashboard.py per CONTEXT D-07
    - JSON-injection defence: json.dumps(...).replace('</','<\\/') on every Chart.js payload (RESEARCH §Pattern 4)
    - html.escape(s, quote=True) on every operator-visible string before HTML interpolation
    - ARIA tablist/tab/tabpanel multi-instance Chart.js pattern (RESEARCH §Pattern 3) — all 3 panels rendered at page load with `hidden` attr toggled (Chart.js needs nonzero canvas size at instantiation)
    - CSS-only spinner ring + inline 8-LOC submit-disable script (D-14, no JS framework dependency)
    - Empty-state copy verbatim from CONTEXT D-17 + UI-SPEC §Copywriting
    - Pure-render hex tier (allowed: html, json, typing — forbidden: state_manager, notifier, dashboard, main, requests, datetime, os, yfinance, pyarrow)
key-files:
  created: []
  modified:
    - backtest/render.py (382 LOC; replaces 28-LOC stub from 23-01)
    - tests/test_backtest_render.py (238 LOC; replaces 33-LOC skeleton from 23-01)
key-decisions:
  - "Chart.js URL+SRI duplicated literally inside backtest/render.py — no import of dashboard.py, satisfying CONTEXT D-07 hex-boundary. AST guard test_backtest_render_no_forbidden_imports enforces zero dashboard imports."
  - "JSON injection defence applied to ALL Chart.js payloads (per-panel equity curve + history overlay). _payload() helper centralizes json.dumps(ensure_ascii=False, sort_keys=True, allow_nan=False).replace('</','<\\/')."
  - "Pass/fail badge reads metrics['pass'] AND metrics['cumulative_return_pct'] — UI-SPEC contract (badge shows ✓/✗ glyph + word + signed cumulative return)."
  - "D-19 dual-Sharpe surfaced in metrics row: label says 'Sharpe (annualised)' but reads sharpe_annualized field with fall-back to sharpe_daily (backward-compat with pre-D-19 reports)."
  - "render_report({}) and render_report(None) BOTH return D-17 empty-state copy — explicit `if not report:` guard at top."
  - "render_history caps overlay chart at 10 datasets but the table renders ALL runs (D-06 contract — older runs accessible via the table only)."
patterns-established:
  - "JSON injection defence helper _payload() — reusable for any Chart.js / inline JSON-in-script-tag pattern"
  - "Pure-render module: html.escape on operator strings + json.dumps replace defence on chart payloads + zero I/O imports"
  - "ARIA tab strip rendering all panels with `hidden` attribute (Chart.js multi-instance pattern)"
  - "CSS-only spinner + inline submit-disable script for synchronous 30-60s POSTs (no fetch/AJAX dependency)"
requirements-completed: [BACKTEST-03]
metrics:
  duration: ~10 minutes
  completed: 2026-05-01
  tasks: 2
  files: 2
  commits: 2
---

# Phase 23 Plan 05: Wave 2A — backtest/render.py (BACKTEST-03 HTML render) Summary

**Pure-HTML render layer for /backtest report page (3-tab Chart.js layout), history view (`?history=true`), and operator override form with D-14 spinner+disable UX. Replaces Wave 0 NotImplementedError stubs.**

## Performance

- **Duration:** ~10 minutes
- **Completed:** 2026-05-01
- **Tasks:** 2
- **Files modified:** 2 (backtest/render.py + tests/test_backtest_render.py)

## Accomplishments

- `render_report(report)` — 358-LOC HTML body fragment: pass/fail badge + override form + 3 ARIA tabs + 3 Chart.js canvases (combined / SPI200 / AUDUSD) + per-trade `<details>` table + footer history link.
- `render_history(reports)` — table of all historical runs (sorted desc) + Chart.js overlay capped at 10 most recent datasets (D-06).
- `render_run_form(defaults)` — D-14 operator override form (3 numeric inputs) + CSS-only amber spinner ring + inline 8-LOC submit-disable script swapping label to "Running… (this can take up to 60s)".
- All Chart.js payloads use `_payload()` helper applying `json.dumps(...).replace('</','<\\/')` injection defence (RESEARCH §Pattern 4).
- All operator-visible strings (trade fields, metadata, strategy version) pass through `html.escape(s, quote=True)`.
- Hex-boundary preserved: zero imports of `state_manager`, `notifier`, `dashboard`, `main`, `requests`, `datetime`, `os`, `yfinance`, `pyarrow`. Only stdlib `html`, `json`, `typing` and module-private constants.
- Chart.js 4.4.6 UMD URL + SRI hash `sha384-MH1axGwz/uQzfIcjFdjEfsM0xlf5mmWfAwwggaOh5IPFvgKFGbJ2PZ4VBbgSYBQN` duplicated verbatim from dashboard.py:113-116 (D-07).
- 29 tests across 7 named classes, all passing.

## Task Commits

| Task | Name | Commit | Type |
|------|------|--------|------|
| 1 | Implement backtest/render.py | `83aa6b1` | feat |
| 2 | Implement tests/test_backtest_render.py (7 classes, 29 tests) | `343f230` | test |

_TDD ordering note (mirrors 23-04): the Wave 0 stub raising NotImplementedError served as the implicit RED gate before Task 1 (GREEN). Task 2 then formalized 29 named tests against the GREEN implementation. No standalone RED commit was created for the test file — matches plan-as-written ordering and 23-04's documented precedent._

## Files Created/Modified

- `backtest/render.py` — replaced Wave 0 28-LOC stub with 382 LOC pure-render implementation (3 public + 7 private helpers).
- `tests/test_backtest_render.py` — replaced Wave 0 33-LOC skeleton with 238 LOC, 7 test classes, 29 tests.

## render functions signatures (finalized)

```python
def render_report(report: dict) -> str:
  """3-tab Chart.js HTML body fragment. Empty/None → D-17 empty-state copy."""

def render_history(reports: list[dict]) -> str:
  """History table (all runs) + overlay chart (cap 10). Empty → D-17 copy."""

def render_run_form(defaults: dict) -> str:
  """D-14 override form: 3 numeric inputs + spinner CSS + submit-disable JS."""
```

## Verification Results

### 1. Functions importable & callable on golden fixture

```
$ .venv/bin/python -c "import json, pathlib; from backtest.render import render_report, render_history, render_run_form; r = json.loads(pathlib.Path('tests/fixtures/backtest/golden_report.json').read_text()); html = render_report(r); print('len=', len(html))"
len= 7762
```

### 2. Acceptance grep checks (Task 1) — all green

| Check | Expected | Actual |
|-------|----------|--------|
| `^def render_report` | 1 | 1 |
| `^def render_history` | 1 | 1 |
| `^def render_run_form` | 1 | 1 |
| `_CHARTJS_URL = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.6` | 1 | 1 |
| `_CHARTJS_SRI = 'sha384-MH1axGwz` | 1 | 1 |
| `^import dashboard\|^from dashboard` | 0 | 0 |
| `json.dumps` | ≥1 | 3 |
| `replace('</', '<\\/')` (literal) | ≥1 | 1 (verified via `grep -F 'replace('` line inspection) |
| `html.escape` | ≥1 | 4 |
| `role="tab"` | ≥3 | 4 |
| `role="tabpanel"` | ≥3 | (3 panels rendered + 1 assertion in inline JS query selector) |
| `class="spinner"` | ≥1 | 1 |
| `@keyframes spin` | 1 | 1 |
| `classList.add("running")` | 1 | 1 |
| `b.disabled=true` | 1 | 1 |
| `Running… (this can take up to 60s)` | ≥1 | 2 (CSS comment + JS literal) |

### 3. Test suite — 29/29 pass

```
$ .venv/bin/pytest tests/test_backtest_render.py -x -q
.............................                                           [100%]
29 passed in 0.06s
```

| Class | Tests | Coverage |
|-------|-------|----------|
| TestRenderReport | 8 | 3 canvas IDs, 3 ARIA tabs, default tab, PASS/FAIL badges, 6×3 stat cards, override form embed, strategy version |
| TestChartJsSri | 3 | CDN URL + SRI hash + crossorigin attribute |
| TestRenderHistory | 3 | empty-state, all rows in table, overlay 10-cap (parses JSON payload after reversing `<\/` defence) |
| TestRenderRunForm | 4 | default values, 3 inputs, required attrs, action+method |
| TestEmptyState | 2 | empty dict, None |
| TestJsonInjectionDefence | 2 | `</script>` → `<\/script>` defence; `<img onerror>` → `&lt;img` html.escape |
| TestSubmitButtonDisableUX | 7 | spinner class, @keyframes, classList.add, b.disabled, aria-disabled, label swap, spinner inside render_report |

### 4. AST hex-boundary guard regression-free

```
$ .venv/bin/pytest tests/test_signal_engine.py::TestDeterminism -x -q
55 passed in 0.87s
```

### 5. Backtest module suite (no cross-plan regressions)

```
$ .venv/bin/pytest tests/test_backtest_*.py tests/test_web_backtest.py -q
65 passed, 10 skipped in 1.87s
```

10 skips are Wave 2 Plan 06 (CLI) + Plan 07 (web routes) test stubs — expected and correct.

## Chart.js SRI presence proof

`backtest/render.py` line 17 (constant) + `_render_chart_script_tag()` emits the literal `<script src="..." integrity="sha384-MH1axGwz/uQzfIcjFdjEfsM0xlf5mmWfAwwggaOh5IPFvgKFGbJ2PZ4VBbgSYBQN" crossorigin="anonymous"></script>`. Verified by:

- `TestChartJsSri::test_chartjs_url_present` — `'cdn.jsdelivr.net/npm/chart.js@4.4.6' in html`
- `TestChartJsSri::test_sri_hash_present` — full SRI hash string in html
- `TestChartJsSri::test_crossorigin_anonymous` — `'crossorigin="anonymous"' in html`

## XSS defence proof

- `_e(s) = html.escape(str(s), quote=True)` applied to every operator-visible string in trade rows, metadata header, history rows.
- `TestJsonInjectionDefence::test_html_escape_on_trade_table_fields` injects `<img src=x onerror=alert(1)>` into `exit_reason`; assertion confirms `&lt;img` present and raw `<img` absent.
- `TestJsonInjectionDefence::test_script_close_in_payload_is_escaped` injects `</script><script>alert(1)</script>` into an equity-curve label; assertion confirms `</script>alert` does NOT appear in the output (the `</` substring inside the Chart.js JSON payload is replaced with `<\/`).

## D-14 spinner + disable UX proof

- `TestSubmitButtonDisableUX` (7 tests, all passing):
  - `test_spinner_class_present` — `class="spinner"` element present
  - `test_keyframes_spin_present` — `@keyframes spin` CSS rule present
  - `test_form_running_class_added_on_submit` — submit handler calls `f.classList.add("running")` to reveal the spinner
  - `test_button_disabled_on_submit` — submit handler sets `b.disabled=true`
  - `test_aria_disabled_set_on_submit` — submit handler calls `setAttribute("aria-disabled","true")`
  - `test_label_swap_on_submit` — submit handler sets `b.textContent="Running… (this can take up to 60s)"`
  - `test_spinner_in_render_report_output` — full `render_report(...)` HTML also contains the spinner CSS + `@keyframes spin` (the override form is embedded inside the report body, not a separate page).

## Test count + pass status

- **29 new tests** across 7 classes — 100% passing.
- **+0 regressions** in adjacent suites (AST guard 55 pass, backtest module 65 pass / 10 skipped Wave 2+).

## Decisions Made

- **D-07 hex-boundary preserved literally:** Chart.js URL + SRI hash duplicated verbatim from dashboard.py:113-116 inside backtest/render.py. AST guard `test_backtest_render_no_forbidden_imports` enforces zero `dashboard` imports.
- **D-14 inline spinner script:** ~8-LOC inline `<script>` (no JS framework, no fetch/AJAX) attaches a single `submit` listener that disables the button + swaps the label + adds a `running` class to reveal a CSS-only amber spinner. Survives F5; no race against form submission since the browser submits immediately after the listener returns.
- **D-19 dual-Sharpe surfaced:** `_render_metrics_row` reads `sharpe_annualized` with fall-back to `sharpe_daily`, displays under the "Sharpe (annualised)" UI label. Schema-backward-compatible with any pre-D-19 fixture.
- **Empty-state guard:** `render_report({})` and `render_report(None)` both return D-17 copy via top-level `if not report:` check. Same pattern in `render_history([])`.
- **Overlay cap is render-time only:** `render_history` keeps ALL rows in the table but slices `reports[:_MAX_HISTORY_OVERLAY]` for the chart `datasets` (D-06 contract).

## Deviations from Plan

None — plan executed exactly as written. Both tasks completed in order. All acceptance criteria met. All 29 new tests + 55 AST guard tests + 65 backtest-suite tests passing.

## Auth Gates

None — pure-render HTML module with no network or auth surface.

## Threat Flags

None new. The threat model in `23-05-render-PLAN.md` (T-23-cdn + XSS via report fields + JSON injection in `<script>`) is fully mitigated:

- **T-23-cdn:** SRI hash `sha384-MH1axGwz...` literal in script tag; browser refuses execution if hash mismatches.
- **XSS via report fields:** `_e()` (`html.escape(s, quote=True)`) applied to every operator-visible string. Tested via `<img onerror>` injection.
- **JSON injection in `<script>`:** `_payload()` helper applies `json.dumps(...).replace('</','<\\/')`. Tested via `</script>` injection.

## TDD Gate Compliance

Both tasks marked `tdd="true"`. Plan ordering matches 23-04 precedent: Task 1 (`feat:` GREEN) implements `render_report/render_history/render_run_form`; Task 2 (`test:` covers RED→GREEN paired) adds 7 test classes / 29 tests. The Wave 0 skeleton (raising NotImplementedError) served as the implicit RED gate before Task 1; Task 2's tests then provide the durable test suite.

No standalone RED commit was created for the formal test file because the stub itself was the RED. This matches the plan-as-written ordering and acceptance criteria.

## Self-Check: PASSED

All claimed files verified to exist:

```
backtest/render.py                              FOUND
tests/test_backtest_render.py                   FOUND
.planning/phases/23-five-year-backtest-validation-gate/23-05-SUMMARY.md  (this file)
```

All claimed commits verified in git log:

```
83aa6b1  FOUND  feat(23-05): implement backtest/render.py (BACKTEST-03 HTML)
343f230  FOUND  test(23-05): implement 7 test classes for backtest/render.py (29 tests)
```

Wave 2A (render) complete. Wave 2 Plan 06 (CLI) and Plan 07 (web routes) remain unblocked for parallel/serial execution — render is now the GREEN dependency they consume via `from backtest.render import render_report, render_history, render_run_form`.

## Next Phase Readiness

- `backtest/render.py` ready for consumption by `web/routes/backtest.py` (Wave 2 Plan 23-07).
- `backtest.cli` (Wave 2 Plan 23-06) does not depend on render — it writes JSON only — so 23-06 and 23-07 can proceed in either order.
- No blockers for Wave 2 completion.

---
*Phase: 23-five-year-backtest-validation-gate*
*Plan: 05*
*Completed: 2026-05-01*
