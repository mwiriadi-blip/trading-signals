---
phase: 27
plan: 08
type: execute
wave: 2
parallel: true
depends_on:
  - 27-01-decimal-money-math-PLAN.md
files_modified:
  - notifier.py
  - dashboard.py
  - dashboard_renderer/components/*.py
  - tests/test_html_xss_audit.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "Every f-string / .format() / + concatenation that builds HTML in notifier.py + dashboard.py + dashboard_renderer/ that interpolates a user-supplied or external-source value passes through html.escape(value, quote=True)."
    - "XSS regression test: injecting `<script>alert(1)</script>` into every observable field (warnings, error messages, ticker names from yfinance, paper-trade notes, market labels) lands as `&lt;script&gt;alert(1)&lt;/script&gt;` in the rendered HTML."
    - "Existing escape coverage in notifier.py (Phase 6 D-10) preserved; this plan adds dashboard-side parity."
  artifacts:
    - path: tests/test_html_xss_audit.py
      provides: "XSS injection regression for every external-source field"
      contains: "test_xss_"
  key_links:
    - from: "dashboard_renderer/components/signals.py"
      to: "html.escape"
      via: "every dynamic interpolation"
      pattern: "html\\.escape\\("
---

<objective>
Audit every HTML-building site in notifier.py + dashboard.py + dashboard_renderer/ for unescaped dynamic data. Notifier already has heavy coverage from Phase 6 D-10; the audit FOCUS is dashboard.py + dashboard_renderer/ (which ship the `/markets/{m}/{fn}` route HTML), plus any new external-source fields that landed in Phase 25/26.

Purpose: stored XSS prevention (review item #10).
Output: every external-source field escape-audited, regression tests injecting `<script>` into each field.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/26-phase-25-followup-multi-tab-scoping-fixes/26-CONTEXT.md
@notifier.py
@dashboard.py
@dashboard_renderer/components/

<interfaces>
# External-source fields (must be escaped at every render site):
#   1. state['warnings'] entries — operator-visible warning strings (could include yfinance error text with HTML metachars)
#   2. ticker symbols from yfinance — generally [A-Z0-9.] but defensive escape recommended
#   3. paper-trade rows — instrument label (validated via INSTRUMENT_ID_RE per Plan 27-04 — safe but escape anyway, defense-in-depth)
#   4. error messages bubbled up from Resend / yfinance / requests
#   5. STRATEGY_VERSION footer — controlled (not external) but still string-interpolated; escape for hygiene
#   6. last_run timestamps — controlled; escape anyway
#   7. user-input via cookies (selected_market) — validated via Plan 26-07 R7 regex but still escape on render
#
# Existing pattern in notifier.py (Phase 6 D-10) — keep:
#   f'<span style="color:{html.escape(colour, quote=True)}">{html.escape(body, quote=True)}</span>'
#
# Audit: in dashboard_renderer/components/*.py, grep for any `f"..."` or `.format(...)` that builds HTML.
# Each interpolation `{variable}` must be wrapped in html.escape(variable, quote=True) UNLESS the
# variable is a fixed enum mapped to a hardcoded HTML literal (e.g. `'open' if active else ''`).
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Audit + escape every dynamic-data HTML site</name>
  <read_first>
    - dashboard.py (full — 2212 LOC)
    - dashboard_renderer/components/*.py (all components)
    - notifier.py — html.escape grep results (high coverage already; verify no new gaps from Phase 25/26)
  </read_first>
  <behavior>
    - test_xss_warning_field_escaped: inject `<script>alert(1)</script>` into state['warnings'][0]; render dashboard HTML; assert `&lt;script&gt;alert(1)&lt;/script&gt;` is in the output AND raw `<script>alert(1)` is NOT.
    - test_xss_ticker_field_escaped: same with a fake ticker `<img src=x onerror=alert(1)>`.
    - test_xss_paper_trade_label_escaped: same with paper_trade['label'] (or whatever free-text field exists).
    - test_xss_resend_error_in_email_escaped: simulate notifier crash-email body containing `<script>` — already covered by Phase 6 D-10, but add explicit regression.
    - test_xss_selected_market_cookie_escaped: even though regex-validated, set cookie to a value the regex would reject (i.e. craft a fake request bypassing validation); assert downstream renderer escapes (defense-in-depth).
    - test_existing_escape_coverage_unchanged: grep notifier.py — count of `html.escape(` matches must be >= the pre-Phase-27 count (no regression).
  </behavior>
  <action>
1. **Audit pass:** for each of {dashboard.py, every file in dashboard_renderer/components/}, grep:
   ```
   grep -nE 'f["\047].*\{[a-z_]' dashboard.py dashboard_renderer/components/*.py | grep -v 'html\.escape\|^#'
   ```
   For each match, classify the interpolated variable:
   - **External / user-input:** wrap in `html.escape(var, quote=True)`.
   - **Internal / static / numeric:** leave (numbers can't contain HTML metachars; document with a comment if it's a judgment call).
   - **Already escape-safe (e.g. INSTRUMENT_ID_RE-validated):** wrap anyway (defense-in-depth, ~1ns cost).

2. **Most eloquent option for the bulk-fix:** create a `_e(v)` private alias = `html.escape(str(v), quote=True)` in each component module. Replaces `html.escape(value, quote=True)` (28 chars) with `_e(value)` (8 chars), keeping diffs minimal and readable.
   > **Most eloquent:** `_e` alias — locality (each component owns its alias), no cross-module coupling, mechanical bulk-replace via grep.

3. Add `_e` alias to each touched component file:
   ```python
   from html import escape as _html_escape
   def _e(v) -> str:
     return _html_escape(str(v), quote=True)
   ```

4. **tests/test_html_xss_audit.py (NEW):** 6 tests per behavior block. Use the existing dashboard-rendering test fixtures (see tests/test_dashboard_renderer.py for prior art).

5. Run `pytest tests/test_html_xss_audit.py -x -v` and the existing dashboard test suite.

6. Final grep gate:
   ```
   grep -rnE 'f["\047].*\{[a-z_]' dashboard.py dashboard_renderer/components/*.py | grep -v 'html\.escape\|_e(\|^#\|"""'
   # visual review: every remaining match is either numeric/static OR consciously internal
   ```
  </action>
  <verify>
    <automated>pytest tests/test_html_xss_audit.py tests/test_dashboard_renderer.py -x -v</automated>
  </verify>
  <done>
    - `_e` alias added to each touched component file.
    - All external-source interpolations escaped (visual audit + grep gate).
    - 6 XSS regression tests green.
    - Existing dashboard tests still green.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| yfinance / Resend / cookie input → rendered HTML | Untrusted strings must be escaped before reaching `<body>` |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation |
|-----------|----------|-----------|-------------|------------|
| T-27-08-01 | Tampering (XSS) | Attacker controls a yfinance ticker error string that includes `<script>` and it ships into the dashboard's warnings panel | mitigate | html.escape on render; regression test injects `<script>` and asserts escaped. |
| T-27-08-02 | Tampering (XSS) | selected_market cookie bypasses regex validation (zero-day in regex), reaches renderer un-escaped | mitigate | Defense-in-depth — regex-validated AND escaped at render. |
| T-27-08-03 | Spoofing | N/A | accept | — |
</threat_model>

<verification>
```
pytest tests/test_html_xss_audit.py -x -v
grep -rnE 'f["\047].*\{[a-z_]' dashboard.py dashboard_renderer/components/*.py | grep -v 'html\.escape\|_e(\|^#'
# visual review of remaining matches
pytest -x   # full suite
```
</verification>

<success_criteria>
- _e alias in every dashboard_renderer component file.
- All external-source HTML interpolations escaped.
- 6 XSS regression tests green.
- Notifier escape coverage unchanged or expanded.
</success_criteria>

<output>
Create `27-08-SUMMARY.md` with: list of touched component files + count of new escape sites per file, before/after grep counts, regression test summary.
</output>
