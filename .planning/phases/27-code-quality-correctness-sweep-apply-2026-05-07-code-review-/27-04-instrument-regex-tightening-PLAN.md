---
phase: 27
plan: 04
type: execute
wave: 1A
parallel: true
depends_on: []
files_modified:
  - tests/test_instrument_regex.py
  - system_params.py  # <!-- review-fix: agreed-8 — adds KNOWN_MARKET_IDS membership set + is_known_market() -->
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
    - "Two-layer policy: INSTRUMENT_ID_RE for syntax (^[A-Z0-9_]{2,20}$), KNOWN_MARKET_IDS for membership."
    - "INSTRUMENT_ID_RE accepts SPI200X (syntactically valid) but is_known_market('SPI200X') returns False."
    - "is_known_market(id) -> bool wraps the membership check and is the public API for 'is this an actual supported market'."
    - "Every code path that routes/looks-up by instrument id calls is_known_market BEFORE hitting state['signals'][id] or similar."
    - "All instrument-id syntax validation funnels through INSTRUMENT_ID_RE in system_params."
  artifacts:
    - path: tests/test_instrument_regex.py
      provides: "two-layer regression: syntax (regex) + semantics (membership)"
      contains: "test_instrument_regex_rejects"
    - path: system_params.py
      provides: "INSTRUMENT_ID_RE + KNOWN_MARKET_IDS + is_known_market()"
      contains: "KNOWN_MARKET_IDS"
  key_links:
    - from: "web/routes/dashboard.py path validators"
      to: "INSTRUMENT_ID_RE + is_known_market"
      via: "shared compiled pattern + membership check"
      pattern: "is_known_market"
---

## Review fixes applied

- [x] agreed-1 (wave/dependency rebuild) — wave changed `1` → `1A`; depends_on remains empty.
- [x] agreed-8 (instrument regex two-layer policy) — Codex correctly identified that `INSTRUMENT_ID_RE = ^[A-Z0-9_]{2,20}$` is syntactically permissive and CANNOT reject `SPI200X`. Added `KNOWN_MARKET_IDS = {'SPI200', 'AUDUSD'}` set + `is_known_market(id)` function for membership validation. Tests now assert "SPI200X passes regex, fails membership" — testing the two layers separately.
- [x] M1 (brittle implementation tests) — replaced overly-strict "must reject SPI200X" assertion with two-layer behavior tests.
- [x] M2 (doc rule) — SUMMARY artifact stays inside `.planning/phases/27-.../`.

<objective>
Audit and tighten every regex matching instrument tickers / market IDs. Anchor with `^...$`, drop greedy `.` matches, prefer character classes. Centralise the canonical syntax pattern (INSTRUMENT_ID_RE) AND a separate membership set (KNOWN_MARKET_IDS) into system_params.

**Two-layer policy (review-fix agreed-8):**
- **Layer 1 — syntax:** INSTRUMENT_ID_RE = `^[A-Z0-9_]{2,20}$` validates that the input LOOKS like a market id.
- **Layer 2 — semantics:** KNOWN_MARKET_IDS = {'SPI200', 'AUDUSD'} validates that the input IS one we actually support.

Generic ID syntax cannot reject "SPI200X" because it's syntactically valid. Only membership can.

Purpose: routing/validation correctness (review item #8) — a too-loose regex like `SPI200.*` would let `SPI200evil` reach a downstream lookup; the syntax regex prevents that. The membership set prevents valid-but-unsupported ids reaching downstream lookups.

Output: INSTRUMENT_ID_RE + KNOWN_MARKET_IDS + is_known_market() helper + two-layer regression tests.
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
#
# system_params.py additions (review-fix agreed-8):
#   import re
#   INSTRUMENT_ID_RE = re.compile(r'^[A-Z0-9_]{2,20}$')  # syntax layer
#   KNOWN_MARKET_IDS: frozenset[str] = frozenset({'SPI200', 'AUDUSD'})  # membership layer
#   def is_known_market(market_id: str) -> bool:
#     '''Two-layer check: syntactically valid AND in supported set.
#     SPI200X passes INSTRUMENT_ID_RE but returns False here.'''
#     if not isinstance(market_id, str): return False
#     if not INSTRUMENT_ID_RE.fullmatch(market_id): return False
#     return market_id in KNOWN_MARKET_IDS
#
# Likely scattered call sites:
#   web/routes/dashboard.py — path-param validation, cookie validation
#   dashboard.py — _render_signal_cards instrument-key iteration
#   notifier.py — instrument-name interpolation in email body (already escapes via html.escape)
#   main.py — argparse choices, _resolve flags
#
# Audit method: grep -rn 're\.compile\|re\.match\|re\.search\|re\.fullmatch' production .py files,
# inspect each, replace any matching-an-instrument-id pattern with INSTRUMENT_ID_RE.fullmatch(...)
# AND insert is_known_market() check at every routing entry point that looks up by id.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: INSTRUMENT_ID_RE + KNOWN_MARKET_IDS + is_known_market + two-layer audit</name>
  <read_first>
    - system_params.py
    - web/routes/dashboard.py (full — every Pydantic Field(regex=...) and re.compile)
    - dashboard.py (any market-id loops)
    - main.py (argparse market choices)
  </read_first>
  <behavior>
    - test_instrument_id_re_accepts_known_syntax: SPI200, AUDUSD, AUD_USD, A1, ABCDEFGHIJKLMNOPQRST (20 chars) all match the syntax regex.
    - test_instrument_id_re_rejects_too_short: 'A' rejected.
    - test_instrument_id_re_rejects_too_long: 21-char string rejected.
    - test_instrument_id_re_rejects_lowercase: 'spi200' rejected.
    - test_instrument_id_re_rejects_special_chars: 'SPI-200', 'SPI/200', 'SPI 200' all rejected.
    - test_instrument_id_re_accepts_extension_attack_syntactically: 'SPI200X' DOES match INSTRUMENT_ID_RE (syntactically valid) — proves regex alone cannot reject it.  <!-- review-fix: agreed-8 -->
    - test_is_known_market_rejects_extension_attack: is_known_market('SPI200X') == False — membership layer rejects it.  <!-- review-fix: agreed-8 -->
    - test_is_known_market_accepts_real_markets: is_known_market('SPI200') == True; is_known_market('AUDUSD') == True.
    - test_is_known_market_rejects_garbage_syntax: is_known_market('foo bar') == False (fails syntax layer first).
    - test_no_unanchored_instrument_regex_in_prod: AST-walk for every `re.compile(...)` in PROD files; if the pattern contains [A-Z]{2,…} or letters-and-digits chars typical of instrument IDs but lacks `^...$` anchors, fail.
  </behavior>
  <action>
1. **system_params.py:** add INSTRUMENT_ID_RE + KNOWN_MARKET_IDS + is_known_market per <interfaces>. Confirm `re` is already imported (or add `import re`).

2. **Audit pass:** run
   ```
   grep -rn 're\.compile\|re\.match\|re\.search\|re\.fullmatch\|Pattern.*r["\047]' \
     dashboard.py main.py notifier.py state_manager.py auth_store.py data_fetcher.py web/ dashboard_renderer/
   ```
   For each match:
   - If it matches an instrument id (syntax) → replace with `INSTRUMENT_ID_RE` (import from system_params).
   - If it's a placeholder like `{{[A-Z0-9_]{2,20}}}` (Phase 26 _substitute) → leave (different domain).
   - Document each replacement in SUMMARY with file:line before/after.

3. **Routing entry points:** every place that looks up `state['signals'][market_id]` or `markets[id]` MUST gate on `is_known_market(market_id)` first. Grep:
   ```
   grep -rn 'signals\[\|markets\[' dashboard.py main.py web/routes/dashboard.py
   ```
   For each match, ensure an `is_known_market` check precedes the lookup (or the value comes from a source already validated by is_known_market).

4. **Pydantic models** (FastAPI path params): ensure `Field(pattern=r'^[A-Z0-9_]{2,20}$')` (or v2 syntax) anchors are present. Pydantic syntax validation gives Layer 1; the route handler MUST add Layer 2 (`is_known_market`) before doing any state lookup.

5. **tests/test_instrument_regex.py (NEW):** 10 tests per behavior block. The AST walker for the last test:
   ```python
   import ast, pathlib
   PROD = ['dashboard.py','main.py','notifier.py','state_manager.py','auth_store.py','data_fetcher.py']
   def _suspicious(pat: str) -> bool:
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
             if '{{' in pat: continue   # whitelist substitution placeholder
             assert not _suspicious(pat), f'{path}:{node.lineno} unanchored: {pat}'
   ```

6. Run `pytest tests/test_instrument_regex.py -x -v`.
  </action>
  <verify>
    <automated>pytest tests/test_instrument_regex.py -x -v</automated>
  </verify>
  <done>
    - INSTRUMENT_ID_RE + KNOWN_MARKET_IDS + is_known_market in system_params.py.
    - Every flagged regex either rewritten to use INSTRUMENT_ID_RE or whitelisted with comment.
    - Every routing entry point gates on is_known_market.
    - 10 tests in test_instrument_regex.py green.
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
| T-27-04-01 | Tampering | Attacker submits `SPI200X` to /markets/SPI200X/signals — too-loose regex matches and triggers a state lookup that allocates memory or hits a fallback path | mitigate | Two-layer: INSTRUMENT_ID_RE.fullmatch + Pydantic pattern enforces ^[A-Z0-9_]{2,20}$ (Layer 1); is_known_market(id) enforces membership (Layer 2). AST walker prevents regression. |
| T-27-04-02 | Spoofing | N/A | accept | — |
</threat_model>

<verification>
```
pytest tests/test_instrument_regex.py -x -v
grep -rn 're\.compile' dashboard.py main.py notifier.py state_manager.py auth_store.py data_fetcher.py web/ | grep -v 'INSTRUMENT_ID_RE\|^#'
grep -rn 'signals\[\|markets\[' dashboard.py main.py web/routes/dashboard.py | grep -v 'is_known_market'
# visual review: every state lookup is preceded by is_known_market gate
pytest -x   # full suite
```
</verification>

<success_criteria>
- INSTRUMENT_ID_RE + KNOWN_MARKET_IDS + is_known_market in system_params.py.
- All instrument-id regexes funnelled through it (or whitelisted with reason).
- Every routing entry point gates on is_known_market BEFORE state lookup.
- 10 two-layer tests green.
- AST walker confirms no unanchored instrument regex in prod code.
</success_criteria>

<output>
Create `27-04-SUMMARY.md` listing INSTRUMENT_ID_RE definition + KNOWN_MARKET_IDS contents + is_known_market signature + before/after for each rewritten regex (file:line) + AST walker output + list of routing sites gated on is_known_market.
</output>
