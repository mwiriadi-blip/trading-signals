---
phase: 27
plan: 05
type: execute
wave: 1
parallel: true
depends_on:
  - 27-01-decimal-money-math-PLAN.md
files_modified:
  - pnl_engine.py
  - sizing_engine.py
  - notifier.py
  - tests/test_entry_side_cost.py
  - tests/test_signals_email_to_required.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "entry_side_cost(rt_cost: Decimal) -> Decimal helper exported from pnl_engine; replaces every cost_aud/2 literal in pnl_engine + sizing_engine + notifier email body."
    - "_EMAIL_TO_FALLBACK constant deleted from notifier.py; SIGNALS_EMAIL_TO env var is required (fail-fast on missing)."
    - "Grep gate: zero `cost_aud / 2` or `cost_aud/2` literals in production code (test fixtures may keep theirs — by design)."
    - "Grep gate: zero literal email addresses in notifier.py."
  artifacts:
    - path: pnl_engine.py
      provides: "entry_side_cost helper"
      contains: "def entry_side_cost"
  key_links:
    - from: "sizing_engine cost arithmetic"
      to: "pnl_engine.entry_side_cost"
      via: "import + call"
      pattern: "entry_side_cost\\("
---

<objective>
Two related cleanups bundled (both small, both touch notifier.py + pnl_engine.py):

1. **Magic /2 cost helper (item #7):** replace every `cost_aud / 2` literal with `entry_side_cost(rt_cost)`. Document the entry-side ≈ exit-side symmetry assumption.
2. **Hardcoded fallback email (item #9):** delete `_EMAIL_TO_FALLBACK = 'mwiriadi@gmail.com'` from notifier.py:99. SIGNALS_EMAIL_TO env var becomes required; missing → fail-fast at module load OR at send time with clear ValueError.

Depends on 27-01 because entry_side_cost takes Decimal.

Purpose: code clarity (#7) + secret-as-config hygiene (#9 — operator's personal email currently lives in source tree, leaks to GitHub repo).
Output: helper + fail-fast env-var guard + 2 regression tests.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@pnl_engine.py
@sizing_engine.py
@notifier.py

<interfaces>
# Current "magic /2" sites (from grep):
#   sizing_engine.py:517 — docstring "cost_aud_open: per-contract opening cost in AUD (instrument_cost_aud / 2)"
#   sizing_engine.py:575 — same docstring
#   notifier.py — email-body cost-rendering string e.g. "f'Opening cost: ${cost_aud/2 * n_contracts:.2f}'"
#   tests/test_notifier.py:530 — DOCSTRING "Opening half-cost = cost_aud/2 * n_contracts" — keep as comment
#   tests/test_backtest_simulator.py:84 — assertion docstring — keep
#
# Helper:
#   def entry_side_cost(rt_cost: Decimal) -> Decimal:
#     '''Allocate the entry-side share of a round-trip cost.
#
#     ASSUMPTION: entry-side commission ≈ exit-side commission (symmetric brokers),
#     so the half-split is a reasonable allocation for unrealised P&L. If the broker
#     charges asymmetric (e.g. exit fee includes regulatory levies), this becomes
#     a misallocation; revisit then.
#
#     Returns rt_cost / 2 quantized to AUD_QUANTIZE.
#     '''
#     from system_params import AUD_QUANTIZE
#     return (rt_cost / Decimal(2)).quantize(AUD_QUANTIZE)
#
# Hardcoded email:
#   notifier.py:99: _EMAIL_TO_FALLBACK = 'mwiriadi@gmail.com'
#   notifier.py:1492: to_addr = os.environ.get('SIGNALS_EMAIL_TO', _EMAIL_TO_FALLBACK)
# Replace .get() with explicit check; raise ValueError('SIGNALS_EMAIL_TO env var required') if missing.
# Quick task 260425-91t already documented .env.example contract — operator side is set up.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: entry_side_cost helper + replace literals</name>
  <read_first>
    - pnl_engine.py (full)
    - sizing_engine.py lines 510-590 (cost-allocation flow)
    - notifier.py — grep for `cost_aud / 2`, `cost_aud/2`, `/ 2 *`, etc.
  </read_first>
  <behavior>
    - test_entry_side_cost_halves_quantized: entry_side_cost(Decimal('5.00')) == Decimal('2.50').
    - test_entry_side_cost_odd_cents: entry_side_cost(Decimal('5.01')) == Decimal('2.51') OR Decimal('2.50') (verify ROUND_HALF_EVEN default; pin with explicit assertion).
    - test_no_magic_cost_div_in_prod: AST walker — every BinOp(left=Name('cost_aud'), op=Div, right=Constant(2)) is found ZERO times in pnl_engine.py, sizing_engine.py, notifier.py (excluding test fixtures).
  </behavior>
  <action>
1. **pnl_engine.py:** define `entry_side_cost(rt_cost: Decimal) -> Decimal` per <interfaces>. Add to module's public surface (no `_` prefix).

2. **sizing_engine.py:** the docstrings on lines 517 + 575 stay as documentation (they describe the contract); ANY actual computation site that does `cost_aud / 2` should call `entry_side_cost(cost_aud)` instead. Inspect the function bodies near those lines.

3. **notifier.py:** find every `cost_aud / 2` or `cost_aud/2` in code (not docstrings). Replace with `entry_side_cost(cost_aud)`. Import:
   ```python
   from pnl_engine import entry_side_cost  # Phase 27 #7
   ```

4. **tests/test_entry_side_cost.py (NEW):** 3 tests per behavior block. AST walker:
   ```python
   import ast, pathlib
   PROD = ['pnl_engine.py','sizing_engine.py','notifier.py']
   def _is_cost_div_two(node):
     if not isinstance(node, ast.BinOp): return False
     if not isinstance(node.op, ast.Div): return False
     left_ok = isinstance(node.left, ast.Name) and 'cost' in node.left.id.lower()
     right_ok = isinstance(node.right, ast.Constant) and node.right.value == 2
     return left_ok and right_ok
   def test_no_magic_cost_div_in_prod():
     for path in PROD:
       tree = ast.parse(pathlib.Path(path).read_text())
       for node in ast.walk(tree):
         assert not _is_cost_div_two(node), f'{path}:{node.lineno} magic /2'
   ```

5. Run: `pytest tests/test_entry_side_cost.py tests/test_pnl_engine.py tests/test_notifier.py -x -v`.
  </action>
  <verify>
    <automated>pytest tests/test_entry_side_cost.py -x -v</automated>
  </verify>
  <done>
    - entry_side_cost in pnl_engine.py.
    - All `cost_aud / 2` in production code (pnl_engine + sizing_engine + notifier) replaced.
    - 3 tests in test_entry_side_cost.py green.
    - Test-fixture occurrences (tests/test_notifier.py:530, tests/test_backtest_simulator.py:84) untouched (by design — they're docstring-comments).
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Delete _EMAIL_TO_FALLBACK; require SIGNALS_EMAIL_TO env var</name>
  <read_first>
    - notifier.py lines 95-105 (constant declaration)
    - notifier.py lines 1480-1500 (consumption site)
    - .env.example (operator-facing template)
  </read_first>
  <behavior>
    - test_signals_email_to_required: monkeypatch env to remove SIGNALS_EMAIL_TO; call the dispatch function; assert it raises ValueError with message 'SIGNALS_EMAIL_TO env var required' (or returns the documented "no-send" code with a clear log line — pick the path that matches the existing never-crash pattern from notifier.py).
    - test_signals_email_to_present: with SIGNALS_EMAIL_TO='ops@example.com' set, dispatch proceeds normally.
    - test_no_hardcoded_email_in_notifier: grep notifier.py — zero matches for literal email regex `[a-z]+@[a-z]+\.[a-z]+`.
  </behavior>
  <action>
1. **notifier.py:99:** delete the line `_EMAIL_TO_FALLBACK = 'mwiriadi@gmail.com'`.
2. **notifier.py:1492:** replace
   ```python
   to_addr = os.environ.get('SIGNALS_EMAIL_TO', _EMAIL_TO_FALLBACK)
   ```
   with
   ```python
   to_addr = os.environ.get('SIGNALS_EMAIL_TO', '').strip()
   if not to_addr:
     logger.error('[Email] SIGNALS_EMAIL_TO env var required — email skipped')
     return  # consistent with SIGNALS_EMAIL_FROM handling at line 1450
   ```
   This preserves the never-crash pattern (logs + skip) instead of raising. Operator catches the missing env var via the next-day signal-not-received signal + dashboard health strip.

3. **tests/test_signals_email_to_required.py (NEW):** 3 tests per behavior block.

4. **.env.example:** confirm SIGNALS_EMAIL_TO is documented (per quick task `260425-91t`). Append a comment noting Phase 27 made it required.

5. Run `pytest tests/test_signals_email_to_required.py tests/test_notifier.py -x -v`.
  </action>
  <verify>
    <automated>pytest tests/test_signals_email_to_required.py -x -v</automated>
  </verify>
  <done>
    - `grep -c '_EMAIL_TO_FALLBACK\|mwiriadi@gmail' notifier.py` == 0.
    - 3 tests in test_signals_email_to_required.py green.
    - Existing test_notifier.py tests still green (any test that previously relied on the fallback now monkeypatches SIGNALS_EMAIL_TO explicitly).
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Source tree → public GitHub repo | Constants in source are publicly visible — operator's personal email should not live in source |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation |
|-----------|----------|-----------|-------------|------------|
| T-27-05-01 | Information disclosure | Operator's email leaked in repo (low-severity, already public-ish but cleanup is correct hygiene) | mitigate | Constant deleted; env-var only. |
| T-27-05-02 | DoS | If env var missing in production deploy, daily run silently doesn't email | mitigate | Logs `[Email] SIGNALS_EMAIL_TO env var required — email skipped` at ERROR level → operator notices via journalctl + dashboard health strip. |
</threat_model>

<verification>
```
pytest tests/test_entry_side_cost.py tests/test_signals_email_to_required.py -x -v
grep -n 'cost_aud / 2\|cost_aud/2' pnl_engine.py sizing_engine.py notifier.py | grep -v '^#\|"""\|'\'''\''\''
# expected: zero matches in non-docstring lines
grep -n 'mwiriadi\|gmail\|@.*\.\(com\|au\)' notifier.py | grep -v 'docstring\|#'
# expected: zero matches
pytest -x   # full suite
```
</verification>

<success_criteria>
- entry_side_cost helper exported from pnl_engine.
- All production cost_aud/2 literals replaced.
- _EMAIL_TO_FALLBACK constant gone; SIGNALS_EMAIL_TO required.
- 6+ tests across the two new test files green.
</success_criteria>

<output>
Create `27-05-SUMMARY.md` listing helper signature, replacement sites (file:line before/after), env-var guard implementation, AST walker output.
</output>
