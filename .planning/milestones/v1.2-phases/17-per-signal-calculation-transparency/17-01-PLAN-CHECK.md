# Plan Check — Phase 17-01 Per-signal Calculation Transparency

**Verdict:** PASS (with one annotated WARNING)
**Checked:** 2026-04-30
**Plan file:** `.planning/phases/17-per-signal-calculation-transparency/17-01-PLAN.md`

---

## Verdict: PASS

All 10 CONTEXT verification items, all 7 ROADMAP success criteria, and all 5 REQUIREMENTS TRACE lines are covered by named tasks with runnable automated verify commands. One WARNING noted (see below).

---

## Strengths

1. **CONTEXT verification matrix fully wired (lines 927–937 of plan).** Every one of the 10 verification checks has an exact task owner:
   - Schema bump → Task 1 (`STATE_SCHEMA_VERSION=5`)
   - Migration backfills empty `ohlc_window`/`indicator_scalars` → Task 2 (`_migrate_v4_to_v5`)
   - 40-entry rows after one daily run → Task 3 (`TestRunDailyCheckPersistsTracePayload`)
   - HTML contains all 9 formula strings → Task 4 (`test_all_formula_strings_present`)
   - Two `<details data-instrument="...">` blocks → Task 4 (`test_inputs_panel_renders_40_rows`)
   - 40 rows with `data-row-index` → Task 4 same test
   - Hand-recalc 1e-6 tolerance → Task 6 / SUMMARY (deferred UAT, explicitly documented)
   - Cookie persistence → Task 6 / SUMMARY (deferred UAT, explicitly documented)
   - Hex-boundary grep zero matches → Task 4 acceptance_criteria line + Task 6 step g
   - Pytest invocation covering all four new test classes → Task 6 step i (exact pytest invocation)

2. **Phase 22 LEARNINGS all encoded.**
   - Kwarg-default capture trap: `trace_open_keys: list[str] | None = None` (Task 4 plan.md line ~676); `test_render_dashboard_default_trace_open_keys_is_none_not_mutable_default` asserts `inspect.signature` at runtime (Task 4 behavior block).
   - Idempotent migration with two independent guards: explicitly in Task 2 behavior (`test_migrate_v4_to_v5_idempotent_partial_state`) proving independence of the two `'field' not in sig` checks.
   - Hex-boundary primitives-only: Task 4 action step j + acceptance_criteria grep + AST guard re-run every task.

3. **Cookie safety / iOS trap fully tested.**
   - Allowlist filter `frozenset(k for k in raw.split(',') if k in _VALID_TRACE_INSTRUMENT_KEYS)` in Task 5 (`_resolve_trace_open` helper); `test_tsi_trace_open_cookie_tampered_unknown_keys_filtered` covers XSS/log-injection path.
   - `.trace-indicator-name { cursor: pointer; }` in Task 4 CSS block (plan line ~623); `test_dashboard_indicator_name_has_cursor_pointer_css` asserts the substring in `_INLINE_CSS` source.

---

## Gaps / Issues

### WARNING — PATTERNS.md File Classification table lists `render_dashboard(... trace_open_keys: list[str] = [])` (mutable-default form) in the summary row (PATTERNS.md line 22), but the "Pattern to adapt" prose on the same page (line 218) and the actual plan task 4 action (plan line ~676) correctly use `None`. No ambiguity in the implementation instruction — the prose overrides the table header and the test (`test_render_dashboard_default_trace_open_keys_is_none_not_mutable_default`) pins the correct form. Executor must follow the plan task, not the PATTERNS.md table row. No change to the plan required; this is a PATTERNS.md documentation inconsistency only.

No blockers found.

---

## Hex-boundary Audit: PASS

Task 4 action step j explicitly instructs: verify NO new top-level imports added to `dashboard.py`. The acceptance_criteria line for that check is:

```
grep -nE "^import system_params\b|^from system_params\b|^import signal_engine\b|^from signal_engine\b|^import state_manager\b|^from state_manager\b|^import data_fetcher\b|^from data_fetcher\b|^import yfinance\b|^from yfinance\b|^import requests\b|^from requests\b" dashboard.py
```
Returns ZERO matches.

Additionally, `tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent` is re-run in the `<verify><automated>` block of every task (Tasks 1–5) and confirmed in Task 6 step h. PATTERNS.md hex-boundary spotlight table (lines 395–412) confirms all 10 new symbols are clean. Formula text inlined as `_TRACE_FORMULAS` + `_SEED_LENGTHS` string constants per D-10.

---

## Cookie Safety Audit: PASS

Task 5 implements `_resolve_trace_open` with:
```python
frozenset(k for k in raw.split(',') if k in _VALID_TRACE_INSTRUMENT_KEYS)
```
Module-level `_VALID_TRACE_INSTRUMENT_KEYS = frozenset({'SPI200', 'AUDUSD'})` defined at route-module top. Test `test_tsi_trace_open_cookie_tampered_unknown_keys_filtered` (Task 5 behavior block) asserts `AAPL`, `EVIL_PAYLOAD`, `javascript:alert(1)` are dropped and do NOT appear in rendered HTML. STRIDE T-17-01 row documents this disposition as "mitigate" with the filter as mitigation. RESEARCH.md §Security independently surfaces this requirement (was not in CONTEXT.md D-12; surfaces as D-16 in the plan).

---

## iOS Safari Trap Audit: PASS

Task 4 action step g includes in the CSS block:
```
.trace-indicator-name { cursor: pointer; }  /* D-15 — Mobile Safari click fix */
```
Task 4 behavior block includes `test_dashboard_indicator_name_has_cursor_pointer_css`:
> assert the substring `.trace-indicator-name { cursor: pointer; }` (or whitespace-tolerant equivalent) appears in `_INLINE_CSS`

Task 4 acceptance_criteria:
```
grep -nE "\.trace-indicator-name \{ cursor: pointer" dashboard.py
```
Matches at least once. RESEARCH.md §Pitfall 1 is the cited source.

---

## Phase 22 LEARNINGS Audit: PASS

| Learning | Coverage in Plan |
|----------|-----------------|
| Kwarg-default capture trap (2026-04-29) | Task 4: `trace_open_keys: list[str] \| None = None`; `test_render_dashboard_default_trace_open_keys_is_none_not_mutable_default` via `inspect.signature` |
| Idempotent migration + skips-int-legacy + preserves-other-fields | Task 2: 7 tests covering backfill, idempotency (2 independent guards), partial-state, int-legacy, field preservation, schema bump, full v0→v5 walk |
| Hex-boundary primitives-only in dashboard.py | Task 4: `_TRACE_FORMULAS`, `_SEED_LENGTHS` inlined; forbidden-imports grep + AST guard re-run every task |

---

## Coverage Table

| Check | Source | Task | Plan Location |
|-------|--------|------|---------------|
| Schema bump → STATE_SCHEMA_VERSION=5 | CONTEXT §Verification 1 / SC-1 | Task 1 | acceptance_criteria line 1 |
| Migration backfills ohlc_window=[] + indicator_scalars={} | CONTEXT §Verification 2 | Task 2 | behavior block, 7 tests |
| 40-entry rows after one daily run | CONTEXT §Verification 3 / TRACE-01 | Task 3 | `TestRunDailyCheckPersistsTracePayload` |
| HTML contains all 9 formula strings | CONTEXT §Verification 4 / TRACE-02 | Task 4 | `test_all_formula_strings_present` |
| Two `<details data-instrument="...">` blocks | CONTEXT §Verification 5 | Task 4 | `test_inputs_panel_renders_40_rows` |
| 40 rows with data-row-index | CONTEXT §Verification 6 / TRACE-01 | Task 4 | same test |
| Hand-recalc 1e-6 tolerance | CONTEXT §Verification 7 / SC-5 | Task 6 | deferred operator UAT, SUMMARY |
| Cookie persistence (SPI200 open → refresh) | CONTEXT §Verification 9 / D-12 | Task 6 | deferred operator UAT, SUMMARY |
| Hex-boundary grep zero matches | CONTEXT §Verification 10 / TRACE-05 | Tasks 1–5 + Task 6g | acceptance_criteria each task |
| Pytest invocation — all 4 test classes | CONTEXT §Verification 8 | Task 6i | exact pytest invocation |
| ROADMAP SC-1 (3 panels render) | ROADMAP §Phase 17 | Task 4 | `TestTracePanels` |
| ROADMAP SC-2 (40 OHLC bars) | ROADMAP §Phase 17 | Tasks 3+4 | ohlc_window write + render |
| ROADMAP SC-3 (Indicators panel 9 indicators) | ROADMAP §Phase 17 | Task 4 | `_render_trace_indicators` |
| ROADMAP SC-4 (Vote panel + ADX gate) | ROADMAP §Phase 17 | Task 4 | `_render_trace_vote` + `test_adx_gate_badge_pass_*` |
| ROADMAP SC-5 (1e-6 hand-recalc) | ROADMAP §Phase 17 | Task 6 | deferred UAT documented in SUMMARY |
| ROADMAP SC-6 (no new I/O / no mutation) | ROADMAP §Phase 17 | Task 4 | `test_render_does_not_mutate_state` (deepcopy guard) |
| ROADMAP SC-7 (AST guard extended) | ROADMAP §Phase 17 | Every task verify block | `test_forbidden_imports_absent` re-run |
| TRACE-01 (Inputs panel, 40 OHLC rows) | REQUIREMENTS.md | Tasks 3+4 | ohlc_window + render test |
| TRACE-02 (Indicators panel, formula + numeric) | REQUIREMENTS.md | Task 4 | `_render_trace_indicators` + formula tests |
| TRACE-03 (Vote panel, 2-of-3 + ADX) | REQUIREMENTS.md | Task 4 | `_render_trace_vote` + badge tests |
| TRACE-04 (no state mutation, --test safe) | REQUIREMENTS.md | Task 4 | `test_render_does_not_mutate_state` + empty-state tests |
| TRACE-05 (forbidden-imports guard) | REQUIREMENTS.md | All tasks | `test_forbidden_imports_absent` |
| D-01 (persist OHLC + scalars, no live fetch) | CONTEXT §Decisions | Task 3 | `main.py` write site extension |
| D-02 (40 bars, ohlc_window name) | CONTEXT §Decisions | Task 3 | `df.tail(40)` + key name `ohlc_window` |
| D-03 (tap-to-toggle, data-formula-open) | CONTEXT §Decisions | Task 4 | `_TRACE_TOGGLE_JS` + `test_dashboard_emits_trace_toggle_js` |
| D-04 (inline, default-collapsed, cookie) | CONTEXT §Decisions | Tasks 4+5 | `<details>` + placeholder substitution |
| D-05 (6 decimals) | CONTEXT §Decisions | Task 4 | `_format_indicator_value` + `TestFormatIndicatorValue` |
| D-06 (NaN reason text) | CONTEXT §Decisions | Task 4 | `_format_indicator_value` seed-short + flat-price branches |
| D-07 (badges + gate + outcome line) | CONTEXT §Decisions | Task 4 | `_render_trace_vote` + badge tests |
| D-08 (schema bump 4→5) | CONTEXT §Decisions | Tasks 1+2 | `STATE_SCHEMA_VERSION=5` + MIGRATIONS[5] |
| D-09 (ohlc_window + indicator_scalars shape) | CONTEXT §Decisions | Task 3 | signal-row write site |
| D-10 (hex-boundary, formulas inlined) | CONTEXT §Decisions | Task 4 | `_TRACE_FORMULAS` + `_SEED_LENGTHS` + grep gate |
| D-11 (--test read-only, empty-state copy) | CONTEXT §Decisions | Task 4 | `test_inputs_panel_empty_state` |
| D-12 (cookie attrs, no signing, 90-day) | CONTEXT §Decisions | Tasks 4+5 | `_TRACE_TOGGLE_JS` + `_resolve_trace_open` |
| D-13 (formula text inlined, no MathJax) | CONTEXT §Decisions | Task 4 | `_TRACE_FORMULAS` dict |
| D-14 (render_dashboard kwarg None default) | Planner-encoded | Task 4 | signature + mutable-default test |
| D-15 (cursor: pointer CSS) | RESEARCH-encoded | Task 4 | CSS block + `test_dashboard_indicator_name_has_cursor_pointer_css` |
| D-16 (cookie allowlist filter) | RESEARCH-encoded | Task 5 | `_VALID_TRACE_INSTRUMENT_KEYS` + tamper test |
| D-17 (attribute-level placeholder) | PATTERNS-encoded | Tasks 4+5 | `{{TRACE_OPEN_*}}` placeholders + substitution |

---

## Scope Sanity

- 6 tasks across 1 plan. Tasks 1–3 are narrow (1–2 files each). Task 4 is the largest (dashboard.py + 3 test artifacts) but is cohesive and within the 5-task ceiling.
- Wave: 1 (no dependencies). Wave assignment is valid.
- Total files modified: 11 (as listed in frontmatter). Within budget for a single-wave plan.

---

## Dimension 8 (Nyquist Compliance)

Every task has `<verify><automated>` with a specific `pytest` invocation. Tasks 1–5 all re-run `test_forbidden_imports_absent`. No watch-mode flags. No full E2E suite. Sampling density: 1 automated verify per task (5 tasks, all with coverage). PASS.

---

## Recommendation

**Proceed to execute.** No blockers. The one WARNING (PATTERNS.md table header typo on `trace_open_keys: list[str] = []`) is a documentation inconsistency in the reference file only — the implementation instructions in the plan task itself are correct and the regression test pins the correct `None` default. No plan revision needed.
