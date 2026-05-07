---
phase: 27
plan: 04
type: execute
wave: 1
parallel: true
depends_on: []
files_modified:
  - tests/test_instrument_regex.py
  - system_params.py
  - dashboard.py
  - main.py
  - notifier.py
  - state_manager.py
  - auth_store.py
  - data_fetcher.py
  - web/routes/dashboard.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "Every re.compile / re.match against an instrument id (SPI200, AUDUSD, etc.) is anchored ^...$ with explicit char class [A-Z0-9_]{2,20}."
    - "False-positive rejection: 'SPI200X' must NOT match an SPI200 regex; 'AUDUSDX' must NOT match an AUDUSD regex."
    - "All instrument-id validation funnels through a single helper INSTRUMENT_ID_RE in system_params (or markets module)."
  artifacts:
    - path: tests/test_instrument_regex.py
      provides: "false-positive + anchor regression tests for every instrument-id regex in code"
      contains: "test_instrument_regex_rejects"
  key_links:
    - from: "web/routes/dashboard.py path validators"
      to: "INSTRUMENT_ID_RE"
      via: "shared compiled pattern"
      pattern: "INSTRUMENT_ID_RE"
---

<objective>
Audit and tighten every regex matching instrument tickers / market IDs. Anchor with `^...$`, drop greedy `.` matches, prefer character classes. Centralise the canonical pattern into a single constant.

Purpose: routing/validation correctness (review item #8) — a too-loose regex like `SPI200.*` would let `SPI200evil` reach a downstream lookup, and `selected_market` cookie validation already mirrors `^[A-Z0-9_]{2,20}$` (Phase 26 R7 — Plan 26-07).
Output: INSTRUMENT_ID_RE constant + audit + false-positive regression tests.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/26-phase-25-followup-multi-tab-scoping-fixes/26-07-cache-and-cookie-hardening-PLAN.md
@system_params.py

<interfaces>
# Phase 26 R7 already established the canonical mirror: ^[A-Z0-9_]{2,20}$
# Likely scattered call sites:
#   web/routes/dashboard.py — path-param validation, cookie validation
#   dashboard.py — _render_signal_cards instrument-key iteration
#   notifier.py — instrument-name interpolation in email body (already escapes via html.escape)
#   main.py — argparse choices, _resolve flags
#
# Add to system_params.py:
#   INSTRUMENT_ID_RE = re.compile(r'^[A-Z0-9_]{2,20}$')  # Phase 27 #8 single-source pattern
#
# Audit method: grep -rn 're\.compile\|re\.match\|re\.search\|re\.fullmatch' production .py files,
# inspect each, replace any matching-an-instrument-id pattern with INSTRUMENT_ID_RE.fullmatch(...).
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: INSTRUMENT_ID_RE + audit + false-positive tests</name>
  <read_first>
    - system_params.py
    - web/routes/dashboard.py (full — every Pydantic Field(regex=...) and re.compile)
    - dashboard.py (any market-id loops)
    - main.py (argparse market choices)
  </read_first>
  <behavior>
    - test_instrument_id_re_accepts_known: SPI200, AUDUSD, AUD_USD, A1, ABCDEFGHIJKLMNOPQRST (20 chars) all match.
    - test_instrument_id_re_rejects_too_short: 'A' rejected.
    - test_instrument_id_re_rejects_too_long: 21-char string rejected.
    - test_instrument_id_re_rejects_lowercase: 'spi200' rejected.
    - test_instrument_id_re_rejects_special_chars: 'SPI-200', 'SPI/200', 'SPI 200' all rejected.
    - test_instrument_id_re_rejects_extension_attack: 'SPI200X', 'SPI200evil' all rejected (anchored).
    - test_no_unanchored_instrument_regex_in_prod: AST-walk for every `re.compile(...)` in PROD files; if the pattern contains [A-Z]{2,…} or letters-and-digits chars typical of instrument IDs but lacks `^...$` anchors, fail.
  </behavior>
  <action>
1. **system_params.py:** add `INSTRUMENT_ID_RE` per <interfaces>. Confirm `re` is already imported (or add `import re`).

2. **Audit pass:** run
   ```
   grep -rn 're\.compile\|re\.match\|re\.search\|re\.fullmatch\|Pattern.*r["\047]' \
     dashboard.py main.py notifier.py state_manager.py auth_store.py data_fetcher.py web/ dashboard_renderer/
   ```
   For each match:
   - If it matches an instrument id → replace with `INSTRUMENT_ID_RE` (import from system_params).
   - If it matches a placeholder like `{{[A-Z0-9_]{2,20}}}` (Phase 26 _substitute) → leave (different domain).
   - Document each replacement in SUMMARY with file:line before/after.

3. **Pydantic models** (FastAPI path params): ensure `Field(pattern=r'^[A-Z0-9_]{2,20}$')` (or the equivalent v2 syntax) anchors are present. If a path param accepts `market: str` without pattern, add it.

4. **tests/test_instrument_regex.py (NEW):** 7 tests per behavior block. The AST walker for the last test:
   ```python
   import ast, pathlib, re as _re
   PROD = ['dashboard.py','main.py','notifier.py','state_manager.py','auth_store.py','data_fetcher.py']
   def _suspicious(pat: str) -> bool:
     # heuristic: pattern contains [A-Z…] alpha/digit class typical of instrument IDs
     # AND is not anchored with ^ or fullmatch
     if '[A-Z' in pat and '^' not in pat: return True
     return False
   def test_no_unanchored_instrument_regex_in_prod():
     for path in PROD:
       tree = ast.parse(pathlib.Path(path).read_text())
       for node in ast.walk(tree):
         if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
            and isinstance(node.func.value, ast.Name) and node.func.value.id == 're':
           if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
             pat = node.args[0].value
             # whitelist: substitution placeholder regex `{{[A-Z0-9_]{2,20}}}` is NOT instrument validation
             if '{{' in pat: continue
             assert not _suspicious(pat), f'{path}:{node.lineno} unanchored: {pat}'
   ```

5. Run `pytest tests/test_instrument_regex.py -x -v`.
  </action>
  <verify>
    <automated>pytest tests/test_instrument_regex.py -x -v</automated>
  </verify>
  <done>
    - INSTRUMENT_ID_RE constant in system_params.py.
    - Every flagged regex either rewritten to use INSTRUMENT_ID_RE or whitelisted with comment explaining why.
    - 7 tests in test_instrument_regex.py green.
    - Full suite green (`pytest -x`).
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| HTTP path/query/cookie → market lookup | Untrusted input must not bypass routing or hit unintended state keys |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation |
|-----------|----------|-----------|-------------|------------|
| T-27-04-01 | Tampering | Attacker submits `SPI200X` to /markets/SPI200X/signals — too-loose regex matches and triggers a state lookup that allocates memory or hits a fallback path | mitigate | INSTRUMENT_ID_RE.fullmatch + Pydantic pattern enforces ^[A-Z0-9_]{2,20}$. AST walker prevents regression. |
| T-27-04-02 | Spoofing | N/A | accept | — |
</threat_model>

<verification>
```
pytest tests/test_instrument_regex.py -x -v
grep -rn 're\.compile' dashboard.py main.py notifier.py state_manager.py auth_store.py data_fetcher.py web/ | grep -v 'INSTRUMENT_ID_RE\|^#'
# visual review: every remaining literal regex is non-instrument (not [A-Z0-9_] over-broad)
pytest -x   # full suite
```
</verification>

<success_criteria>
- INSTRUMENT_ID_RE constant in system_params.py.
- All instrument-id regexes funnelled through it (or whitelisted with reason).
- 7 false-positive / anchor-rejection tests green.
- AST walker confirms no unanchored instrument regex in prod code.
</success_criteria>

<output>
Create `27-04-SUMMARY.md` listing INSTRUMENT_ID_RE definition + before/after for each rewritten regex (file:line) + AST walker output.
</output>
