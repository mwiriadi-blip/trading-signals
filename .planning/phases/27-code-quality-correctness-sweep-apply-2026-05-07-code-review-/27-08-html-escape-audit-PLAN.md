---
phase: 27
plan: 08
type: execute
wave: 2A
parallel: true
depends_on: [27-01, 27-02, 27-03, 27-04, 27-05, 27-06, 27-07]  # <!-- revision-fix: blocker-1 — Wave 2A must follow Wave 1; encode full Wave 1 list. No Decimal coupling — deps are for sequencing, not coupling. -->
files_modified:
  - notifier.py
  - dashboard.py
  - dashboard_renderer/components/*.py
  - tests/test_html_xss_audit.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "Every f-string / .format() / + concatenation building HTML in notifier.py + dashboard.py + dashboard_renderer/ that interpolates an UNTRUSTED-text variable passes through html.escape(value, quote=True) (or _e alias)."
    - "TRUSTED HTML fragments (e.g. render_status_strip output, prebuilt safe markup) are NOT escaped — anti-double-escape policy."
    - "Render-variable taxonomy classifies every dynamic interpolation into: (a) untrusted text (escape), (b) trusted HTML fragment (don't escape), (c) trusted constant (no escape needed)."
    - "XSS regression test: injecting `<script>alert(1)</script>` into every external-source field lands as `&lt;script&gt;alert(1)&lt;/script&gt;`."
    - "Anti-double-escape regression test: passing a known-trusted HTML fragment through the renderer leaves it RAW (no `&lt;` where `<` should remain)."
    - "notifier.py existing escape pattern from Phase 6 D-10 is REUSED if it has a helper; no parallel _e alias introduced."
  artifacts:
    - path: tests/test_html_xss_audit.py
      provides: "XSS injection regression + anti-double-escape regression"
      contains: "test_xss_"
  key_links:
    - from: "dashboard_renderer/components/signals.py"
      to: "html.escape (or _e alias)"
      via: "every untrusted-text interpolation"
      pattern: "html\\.escape\\(\\|_e\\("
---

## Helper decision

<!-- revision-fix: warning-1 — Task 0 records the canonical helper choice in this block. Task 0 verification greps for this block. -->

Recorded by Task 0 after inspecting notifier.py:
- Canonical helper name: _to be filled by Task 0_
- Locality strategy (centralised vs per-module): _to be filled by Task 0_
- Reused existing helper from Phase 6 D-10: _yes/no — to be filled by Task 0_

## Review fixes applied

- [x] agreed-1 (wave/dependency rebuild) — wave changed `2` → `2A`; depends_on emptied (no functional Decimal coupling needed; 2A precedes 2B). 27-01 not actually required for HTML escaping.
- [x] agreed-9 (Codex HIGH — trusted-fragment classification) — added `<render_variable_taxonomy>` block classifying every dynamic interpolation as (a) untrusted text → escape, (b) trusted HTML fragment → DON'T escape, (c) trusted constant → no escape. Mechanical bulk-escape replaced with classified-escape.
- [x] agreed-9 (anti-double-escape regression test) — added explicit "raw expected markup remains raw" test. Pass a trusted HTML fragment through the renderer; assert NOT double-escaped.
- [x] agreed-9 (Codex MEDIUM — verify notifier existing escape pattern before introducing _e) — added explicit Task 0 to inspect notifier.py for existing escape helper from Phase 6 D-10 and REUSE it. Do not introduce parallel _e if a helper already exists.
- [x] M1 (brittle implementation tests) — `_e(` literal grep is paired with classification (#9), used as coverage hint only — not the only gate.
- [x] M2 (doc rule) — SUMMARY artifact stays inside `.planning/phases/27-.../`.
- [x] revision blocker-1 — depends_on populated with full Wave 1 list ([27-01..27-07]) for correct Wave 2A sequencing.
- [x] revision warning-1 — Task 0 `<done>` made machine-verifiable via `## Helper decision` block + grep.

<objective>
Audit every HTML-building site in notifier.py + dashboard.py + dashboard_renderer/ for unescaped untrusted data. Apply CLASSIFIED escaping (not mechanical bulk-escape):

- **Untrusted text** (state['warnings'] entries, ticker error strings, exception messages) → ESCAPE.
- **Trusted HTML fragment** (render_status_strip output, already-safe component output) → DO NOT escape (would produce double-escape: `&lt;span&gt;` instead of `<span>`).
- **Trusted constant** (template literal, hardcoded class names) → no action needed.

Notifier already has heavy coverage from Phase 6 D-10. The audit FOCUS is dashboard.py + dashboard_renderer/ AND verifying we don't introduce a parallel escape helper (REUSE the Phase 6 D-10 one if it exists).

Purpose: stored XSS prevention (review item #10) WITHOUT breaking trusted HTML fragments.
Output: classified escape audit, _e alias (or REUSED existing helper), anti-double-escape regression tests, XSS regression tests.
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

<render_variable_taxonomy>
<!-- review-fix: agreed-9 — explicit classification, not mechanical escape -->

| Field / Variable | Source | Class | Action |
|------------------|--------|-------|--------|
| state['warnings'][i] | yfinance error / requests error / operator-supplied | (a) untrusted text | _e(value) |
| ticker symbol from yfinance | external API | (a) untrusted text | _e(value) |
| paper_trades[i].label / notes | persisted state, but originally from yfinance/external | (a) untrusted text | _e(value) |
| selected_market cookie | regex-validated AT input but defense-in-depth | (a) untrusted text | _e(value) |
| Resend error response body | external API | (a) untrusted text | _e(value) |
| STRATEGY_VERSION | source-controlled constant | (c) trusted constant | no action |
| last_run timestamps | controlled (datetime.now formatted) | (c) trusted constant | no action |
| render_status_strip(...) output | already-safe HTML fragment from a component | (b) trusted HTML fragment | DO NOT escape |
| render_signal_card(...) output | component output | (b) trusted HTML fragment | DO NOT escape |
| render_*(...)  output (ANY component returning HTML string) | component output | (b) trusted HTML fragment | DO NOT escape |
| Hardcoded `<span class="...">` literals | source code | (c) trusted constant | no action |
| signal direction value (-1/0/1, mapped to enum) | typed constant | (c) trusted constant | no action |
| numeric money values (after _format) | controlled formatter output | (c) trusted constant | no action (but: formatter output could include `<` if it ever changed; defensive _e is acceptable) |

**Classification rule:** if a variable is the OUTPUT of a render_* function, it is trusted HTML — leave raw.
If a variable is the INPUT to interpolation from any external/persisted source, it is untrusted text — escape.
</render_variable_taxonomy>

<interfaces>
# Existing pattern in notifier.py (Phase 6 D-10) — VERIFY FIRST, then REUSE:
#   grep -n 'html\.escape\|def _e\|def escape' notifier.py
# If notifier.py already exposes an escape helper (e.g. `_e_html` or similar), REUSE it.
# If not, add `_e(v) -> str: return html.escape(str(v), quote=True)` per component.
#
# Audit grep:
#   grep -nE 'f["\047].*\{[a-z_]' dashboard.py dashboard_renderer/components/*.py | grep -v 'html\.escape\|^#'
# For each match, classify per <render_variable_taxonomy> and apply escape ONLY if class (a).
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 0: Verify notifier.py existing escape helper (Phase 6 D-10) before introducing _e</name>
  <!-- review-fix: agreed-9 Codex MEDIUM -->
  <!-- revision-fix: warning-1 — done criterion now machine-verifiable -->
  <read_first>
    - notifier.py — full grep for escape patterns
  </read_first>
  <action>
1. `grep -nE 'html\.escape|def _e|def _escape|def escape' notifier.py` — capture every helper currently defined.
2. If a helper exists (e.g. `_e_html`, `_safe_html`, etc.):
   - REUSE that helper name across dashboard_renderer/components/*.py.
   - Do NOT introduce a parallel `_e` alias.
3. If NO helper exists in notifier.py:
   - Define `_e(v) -> str: return html.escape(str(v), quote=True)` PER component module (locality).
4. **Decision recorded** in this PLAN.md's `## Helper decision` block at the top of the file:
   - Fill in `Canonical helper name`, `Locality strategy`, `Reused existing helper from Phase 6 D-10`.
   - This makes Task 0 verification machine-checkable.
  </action>
  <verify>
    <automated>grep -qE "Helper decision|canonical_escape_helper" .planning/phases/27-code-quality-correctness-sweep-apply-2026-05-07-code-review-/27-08-html-escape-audit-PLAN.md && grep -A 4 "## Helper decision" .planning/phases/27-code-quality-correctness-sweep-apply-2026-05-07-code-review-/27-08-html-escape-audit-PLAN.md | grep -vE "to be filled by Task 0" | grep -qE "Canonical helper name:.*\S"</automated>
  </verify>
  <done>
    - `## Helper decision` block in 27-08-PLAN.md has canonical helper name filled in (no longer "_to be filled by Task 0_").
    - Locality strategy + reuse-from-D-10 flag recorded.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 1: Classified-escape audit + apply per taxonomy</name>
  <read_first>
    - dashboard.py (full — 2212 LOC)
    - dashboard_renderer/components/*.py (all components)
    - notifier.py (post Task 0)
  </read_first>
  <behavior>
    - test_xss_warning_field_escaped: inject `<script>alert(1)</script>` into state['warnings'][0]; render dashboard; assert `&lt;script&gt;` IS in output AND raw `<script>alert(1)` is NOT.
    - test_xss_ticker_field_escaped: same with ticker `<img src=x onerror=alert(1)>`.
    - test_xss_paper_trade_label_escaped: same with paper_trade label.
    - test_xss_resend_error_in_email_escaped: notifier crash-email body containing `<script>` — escaped.
    - test_xss_selected_market_cookie_escaped: cookie bypassing regex validation, downstream renderer escapes (defense-in-depth).
    - test_anti_double_escape_trusted_fragment: pass a known-trusted HTML fragment (`<span class="status">OK</span>`) through the renderer composition path; assert it remains RAW (`<span` NOT `&lt;span`).  <!-- review-fix: agreed-9 -->
    - test_anti_double_escape_status_strip_output: render_status_strip output composed into the page is NOT double-escaped.
    - test_existing_escape_coverage_unchanged: grep notifier.py — count of escape calls >= pre-Phase-27 count.
  </behavior>
  <action>
1. **Audit pass:** for each of {dashboard.py, every file in dashboard_renderer/components/}, grep:
   ```
   grep -nE 'f["\047].*\{[a-z_]' dashboard.py dashboard_renderer/components/*.py | grep -v 'html\.escape\|^#'
   ```
   For each match, classify per <render_variable_taxonomy>:
   - **(a) Untrusted text:** wrap in `_e(var)` (or the canonical helper from Task 0).
   - **(b) Trusted HTML fragment:** leave raw. Add a `# trusted: render_*() output` inline comment for the auditor's benefit.
   - **(c) Trusted constant:** leave raw. (Optional: add defensive `_e()` for numeric values where the formatter contract is loose.)

2. Apply the canonical helper name (from Task 0) per file. If introducing per-module aliases, place at top:
   ```python
   from html import escape as _html_escape
   def _e(v) -> str:
     return _html_escape(str(v), quote=True)
   ```

3. **tests/test_html_xss_audit.py (NEW):** 8 tests per behavior block. Anti-double-escape tests use a known-trusted fragment:
   ```python
   def test_anti_double_escape_trusted_fragment():
     trusted = '<span class="status">OK</span>'
     # exercise whatever composition site combines fragments
     out = render_dashboard_with_fragment(trusted, ...)
     assert '<span class="status">OK</span>' in out
     assert '&lt;span' not in out, 'trusted fragment was double-escaped'
   ```

4. Run `pytest tests/test_html_xss_audit.py -x -v` and the existing dashboard test suite.

5. Final grep gate (pair with classification, not standalone):
   ```
   grep -rnE 'f["\047].*\{[a-z_]' dashboard.py dashboard_renderer/components/*.py | grep -v 'html\.escape\|_e(\|^#\|"""'
   # visual review per taxonomy: every remaining match is consciously class (b) or (c)
   ```
  </action>
  <verify>
    <automated>pytest tests/test_html_xss_audit.py tests/test_dashboard_renderer.py -x -v</automated>
  </verify>
  <done>
    - Canonical escape helper applied (Task 0 chose; consistent across files).
    - Untrusted-text interpolations escaped (taxonomy class a).
    - Trusted HTML fragments preserved raw (taxonomy class b — anti-double-escape verified).
    - 8 regression tests green.
    - Existing dashboard tests still green.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| yfinance / Resend / cookie input → rendered HTML | Untrusted strings must be escaped before reaching `<body>` |
| Component render output → page composition | Already-safe HTML must NOT be double-escaped |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation |
|-----------|----------|-----------|-------------|------------|
| T-27-08-01 | Tampering (XSS) | Attacker controls a yfinance ticker error string with `<script>` → ships into dashboard's warnings panel | mitigate | _e() escape on render; XSS regression test asserts. |
| T-27-08-02 | Tampering (XSS) | selected_market cookie bypasses regex validation, reaches renderer un-escaped | mitigate | Defense-in-depth — regex-validated AND escaped at render. |
| T-27-08-03 | DoS / UX bug | Mechanical escape introduces double-escape; trusted HTML fragments render as `&lt;span&gt;` instead of `<span>` → broken page | mitigate | Render-variable taxonomy classifies fragments; anti-double-escape regression test asserts trusted fragments remain raw. |
</threat_model>

<verification>
```
pytest tests/test_html_xss_audit.py -x -v
grep -rnE 'f["\047].*\{[a-z_]' dashboard.py dashboard_renderer/components/*.py | grep -v 'html\.escape\|_e(\|^#'
# visual review per taxonomy
pytest -x   # full suite
```
</verification>

<success_criteria>
- Canonical escape helper chosen (REUSED from notifier if present, else per-component _e).
- Untrusted-text interpolations escaped per taxonomy class (a).
- Trusted HTML fragments NOT double-escaped (taxonomy class b verified by regression test).
- 8 regression tests green.
- Notifier escape coverage unchanged or expanded.
</success_criteria>

<output>
Create `27-08-SUMMARY.md` with: render-variable taxonomy table, helper-name decision (Task 0 outcome), list of touched component files + count of new escape sites per file (class a), list of trusted fragments NOT escaped (class b), before/after grep counts, regression test summary.
</output>
