---
phase: 27
plan: 05
type: execute
wave: 1C
parallel: false
depends_on:
  - 27-01-decimal-money-math-PLAN.md  # <!-- review-fix: agreed-1 — entry_side_cost takes Decimal -->
files_modified:
  - pnl_engine.py
  - sizing_engine.py
  - notifier.py
  - main.py  # <!-- review-fix: M3 — main.py:1514 has resolved['cost_aud']/2 -->
  - tests/test_entry_side_cost.py
  - tests/test_signals_email_to_required.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "entry_side_cost(rt_cost: Decimal) -> Decimal helper exported from pnl_engine; replaces every cost_aud/2 literal in pnl_engine + sizing_engine + notifier email body + main.py."
    - "_EMAIL_TO_FALLBACK constant deleted from notifier.py; SIGNALS_EMAIL_TO env var becomes required."
    - "BOTH send_daily_email (line 1492) AND send_crash_email (line 1576) updated — no remaining _EMAIL_TO_FALLBACK references."
    - "Missing SIGNALS_EMAIL_TO behavior: log + return at send time AND append a state-health warning marker — operator notices via dashboard health strip on next visit."
    - "Grep gate: zero `cost_aud / 2` or `cost_aud/2` literals in pnl_engine.py, sizing_engine.py, notifier.py, AND main.py."
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
    - from: "main.py:1514 (resolved cost arithmetic)"
      to: "pnl_engine.entry_side_cost"
      via: "import + call"
      pattern: "entry_side_cost\\("
---

## Review fixes applied

- [x] agreed-1 (wave/dependency rebuild) — wave changed `1` → `1C` per Codex sequencing matrix; depends_on=[27-01] retained (entry_side_cost takes Decimal).
- [x] M3 (cost_aud/2 grep gate scope) — added `main.py` to file inventory and grep gate; main.py:1514 has `resolved['cost_aud'] / 2` that was missed in original plan.
- [x] M3 (_EMAIL_TO_FALLBACK both call sites) — task scope now covers BOTH send_daily_email (line 1492) AND send_crash_email (line 1576); both use _EMAIL_TO_FALLBACK and both must be updated.
- [x] M3 (behavior contradiction resolved) — chose option (b): log + return at send time. Added bounded warning/state-health marker so missing env var is visible in dashboard. Rationale: preserves existing never-crash invariant; operator catches via dashboard health strip + journalctl ERROR. Fail-fast at startup (option a) would crash daemon on env-var typo, which is worse than silent skip + visible warning.
- [x] M2 (doc rule) — SUMMARY artifact stays inside `.planning/phases/27-.../`.
- [x] M1 (brittle implementation tests) — test_no_magic_cost_div_in_prod uses AST detection (BinOp node match), not literal-string grep — already behavior-level.

<objective>
Two related cleanups bundled (both small, both touch notifier.py + pnl_engine.py + main.py):

1. **Magic /2 cost helper (item #7):** replace every `cost_aud / 2` literal with `entry_side_cost(rt_cost)`. Document the entry-side ≈ exit-side symmetry assumption. Scope includes pnl_engine, sizing_engine, notifier, AND main.py:1514 (review-fix M3).
2. **Hardcoded fallback email (item #9):** delete `_EMAIL_TO_FALLBACK = 'mwiriadi@gmail.com'` from notifier.py:99. Update BOTH send_daily_email AND send_crash_email call sites. SIGNALS_EMAIL_TO env var becomes required; missing → log ERROR + return + append state-health warning marker (review-fix M3).

Depends on 27-01 because entry_side_cost takes Decimal.

Purpose: code clarity (#7) + secret-as-config hygiene (#9 — operator's personal email currently lives in source tree, leaks to GitHub repo).
Output: helper + fail-soft env-var guard with health-marker + 6+ regression tests.
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
@main.py

<interfaces>
# Current "magic /2" sites (review-fix M3 — added main.py:1514):
#   sizing_engine.py:517 — docstring "cost_aud_open: per-contract opening cost in AUD (instrument_cost_aud / 2)"
#   sizing_engine.py:575 — same docstring
#   notifier.py — email-body cost-rendering string e.g. "f'Opening cost: ${cost_aud/2 * n_contracts:.2f}'"
#   main.py:1514 — `resolved['cost_aud'] / 2`     <!-- review-fix: M3 -->
#   tests/test_notifier.py:530 — DOCSTRING "Opening half-cost = cost_aud/2 * n_contracts" — keep as comment
#   tests/test_backtest_simulator.py:84 — assertion docstring — keep
#
# Helper:
#   def entry_side_cost(rt_cost: Decimal) -> Decimal:
#     '''Allocate the entry-side share of a round-trip cost.
#
#     ASSUMPTION: entry-side commission ≈ exit-side commission (symmetric brokers),
#     so the half-split is a reasonable allocation for unrealised P&L.
#
#     Returns rt_cost / 2 quantized to AUD_QUANTIZE with HALF_UP rounding.
#     '''
#     from system_params import AUD_QUANTIZE, AUD_ROUND
#     return (rt_cost / Decimal(2)).quantize(AUD_QUANTIZE, rounding=AUD_ROUND)
#
# Hardcoded email — BOTH call sites (review-fix M3):
#   notifier.py:99: _EMAIL_TO_FALLBACK = 'mwiriadi@gmail.com'              — DELETE
#   notifier.py:1492: send_daily_email — to_addr = os.environ.get('SIGNALS_EMAIL_TO', _EMAIL_TO_FALLBACK)
#   notifier.py:1576: send_crash_email — also uses _EMAIL_TO_FALLBACK     — UPDATE
#
# Behavior on missing SIGNALS_EMAIL_TO (review-fix M3 — chose option b):
#   to_addr = os.environ.get('SIGNALS_EMAIL_TO', '').strip()
#   if not to_addr:
#     logger.error('[Email] SIGNALS_EMAIL_TO env var required — email skipped')
#     # State-health warning marker — visible on dashboard health strip:
#     try:
#       from state_manager import append_warning
#       append_warning(state, '[Email] SIGNALS_EMAIL_TO env var missing — emails disabled')
#     except Exception as e:
#       logger.error(f'[Email] could not append health warning: {e}')   # never-crash
#     return
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: entry_side_cost helper + replace literals (incl. main.py:1514)</name>
  <read_first>
    - pnl_engine.py (full)
    - sizing_engine.py lines 510-590 (cost-allocation flow)
    - notifier.py — grep for `cost_aud / 2`, `cost_aud/2`
    - main.py lines 1505-1525 — `resolved['cost_aud'] / 2`     <!-- review-fix: M3 -->
  </read_first>
  <behavior>
    - test_entry_side_cost_halves_quantized: entry_side_cost(Decimal('5.00')) == Decimal('2.50').
    - test_entry_side_cost_odd_cents: entry_side_cost(Decimal('5.01')) == Decimal('2.51') with HALF_UP rounding (per Plan 27-01 AUD_ROUND choice).
    - test_no_magic_cost_div_in_prod: AST walker — BinOp(left=Name('cost_aud') or contains 'cost', op=Div, right=Constant(2)) is found ZERO times in pnl_engine.py, sizing_engine.py, notifier.py, AND main.py.
  </behavior>
  <action>
1. **pnl_engine.py:** define `entry_side_cost(rt_cost: Decimal) -> Decimal` per <interfaces>. Public surface (no `_` prefix).

2. **sizing_engine.py:** docstrings on lines 517 + 575 stay as documentation. Inspect function bodies near those lines for any actual `cost_aud / 2` computation; replace with `entry_side_cost(cost_aud)`.

3. **notifier.py:** find every `cost_aud / 2` or `cost_aud/2` in code (not docstrings). Replace with `entry_side_cost(cost_aud)`. Import:
   ```python
   from pnl_engine import entry_side_cost  # Phase 27 #7
   ```

4. **main.py:1514 (review-fix M3):** the line is `resolved['cost_aud'] / 2`. Replace with `entry_side_cost(resolved['cost_aud'])`. Add import at top of main.py:
   ```python
   from pnl_engine import entry_side_cost
   ```
   `resolved['cost_aud']` is now Decimal (per Plan 27-01). entry_side_cost returns Decimal. If the consumer downstream needs float (e.g. for a JSON response), explicit `float(...)` coercion at the boundary.

5. **tests/test_entry_side_cost.py (NEW):** 3 tests per behavior block. AST walker:
   ```python
   import ast, pathlib
   PROD = ['pnl_engine.py','sizing_engine.py','notifier.py','main.py']  # review-fix M3
   def _is_cost_div_two(node):
     if not isinstance(node, ast.BinOp): return False
     if not isinstance(node.op, ast.Div): return False
     # Match: cost_aud / 2 OR resolved['cost_aud'] / 2
     left = node.left
     if isinstance(left, ast.Name) and 'cost' in left.id.lower():
       left_ok = True
     elif isinstance(left, ast.Subscript) and isinstance(left.value, ast.Name):
       # resolved['cost_aud']
       slc = left.slice
       if isinstance(slc, ast.Constant) and isinstance(slc.value, str) and 'cost' in slc.value.lower():
         left_ok = True
       else:
         left_ok = False
     else:
       left_ok = False
     right_ok = isinstance(node.right, ast.Constant) and node.right.value == 2
     return left_ok and right_ok
   def test_no_magic_cost_div_in_prod():
     for path in PROD:
       tree = ast.parse(pathlib.Path(path).read_text())
       for node in ast.walk(tree):
         assert not _is_cost_div_two(node), f'{path}:{node.lineno} magic /2'
   ```

6. Run: `pytest tests/test_entry_side_cost.py tests/test_pnl_engine.py tests/test_notifier.py tests/test_main.py -x -v`.
  </action>
  <verify>
    <automated>pytest tests/test_entry_side_cost.py -x -v</automated>
  </verify>
  <done>
    - entry_side_cost in pnl_engine.py.
    - All `cost_aud / 2` in production code (pnl_engine + sizing_engine + notifier + main.py) replaced.
    - 3 tests green; AST walker covers all 4 files.
    - Test-fixture occurrences (tests/test_notifier.py:530, tests/test_backtest_simulator.py:84) untouched.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Delete _EMAIL_TO_FALLBACK; require SIGNALS_EMAIL_TO; both call sites + state-health marker</name>
  <read_first>
    - notifier.py lines 95-105 (_EMAIL_TO_FALLBACK declaration)
    - notifier.py lines 1485-1500 (send_daily_email consumption)
    - notifier.py lines 1570-1585 (send_crash_email consumption)  <!-- review-fix: M3 -->
    - state_manager.py — append_warning signature
    - .env.example
  </read_first>
  <behavior>
    - test_signals_email_to_required_send_daily: monkeypatch env to remove SIGNALS_EMAIL_TO; call send_daily_email; assert it logs ERROR with 'SIGNALS_EMAIL_TO env var required' AND returns (does not crash).
    - test_signals_email_to_required_send_crash: same scenario for send_crash_email — both paths must handle missing env var consistently.  <!-- review-fix: M3 -->
    - test_signals_email_to_present: with SIGNALS_EMAIL_TO='ops@example.com' set, both dispatch functions proceed normally.
    - test_state_health_warning_appended: with SIGNALS_EMAIL_TO missing AND a state dict provided, the health-warning marker is appended to state['warnings'] (visible on dashboard).
    - test_no_hardcoded_email_in_notifier: grep notifier.py — zero matches for `_EMAIL_TO_FALLBACK` or literal email regex `[a-z]+@[a-z]+\.[a-z]+`.
  </behavior>
  <action>
1. **notifier.py:99:** delete `_EMAIL_TO_FALLBACK = 'mwiriadi@gmail.com'`.

2. **notifier.py:1492 (send_daily_email):** replace
   ```python
   to_addr = os.environ.get('SIGNALS_EMAIL_TO', _EMAIL_TO_FALLBACK)
   ```
   with the missing-env-var handling block from <interfaces> (log + state-health marker + return). The state-health-marker append is wrapped in try/except so notifier never crashes the daily run.

3. **notifier.py:1576 (send_crash_email) — review-fix M3:** apply the SAME replacement. Both call sites must behave identically. The crash-email path is even more critical to handle gracefully: failing here means crash-on-crash. The fallback (Plan 27-11 last_crash.json) catches this case.

4. **tests/test_signals_email_to_required.py (NEW):** 5 tests per behavior block. Cover BOTH send_daily_email and send_crash_email. Construct a state dict for the warnings-marker test.

5. **.env.example:** confirm SIGNALS_EMAIL_TO is documented. Append a comment noting Phase 27 made it required (no fallback).

6. Run `pytest tests/test_signals_email_to_required.py tests/test_notifier.py -x -v`.
  </action>
  <verify>
    <automated>pytest tests/test_signals_email_to_required.py -x -v</automated>
  </verify>
  <done>
    - `grep -c '_EMAIL_TO_FALLBACK\|mwiriadi@gmail' notifier.py` == 0.
    - 5 tests green; both send_daily_email AND send_crash_email covered.
    - State-health warning appended on missing env var.
    - Existing test_notifier.py tests still green (any test relying on fallback now monkeypatches SIGNALS_EMAIL_TO).
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
| T-27-05-01 | Information disclosure | Operator's email leaked in repo | mitigate | Constant deleted; env-var only. |
| T-27-05-02 | DoS / silent failure | Env var missing in production deploy → emails silently dropped → operator unaware | mitigate | Logs ERROR + appends state-health warning visible on dashboard health strip. Operator notices on next dashboard visit. Plan 27-11 last_crash.json provides additional fallback path. |
</threat_model>

<verification>
```
pytest tests/test_entry_side_cost.py tests/test_signals_email_to_required.py -x -v
grep -n 'cost_aud / 2\|cost_aud/2' pnl_engine.py sizing_engine.py notifier.py main.py | grep -v '^#\|"""\|'\'''\''\''
# expected: zero matches in non-docstring lines (incl. main.py per M3)
grep -n 'mwiriadi\|gmail\|@.*\.\(com\|au\)' notifier.py | grep -v 'docstring\|#'
# expected: zero matches
pytest -x   # full suite
```
</verification>

<success_criteria>
- entry_side_cost helper exported from pnl_engine.
- All production cost_aud/2 literals replaced (pnl_engine, sizing_engine, notifier, main.py).
- _EMAIL_TO_FALLBACK constant gone; SIGNALS_EMAIL_TO required for BOTH email paths.
- State-health warning appended on missing env var.
- 8+ tests across the two new test files green.
</success_criteria>

<output>
Create `27-05-SUMMARY.md` listing helper signature, replacement sites (file:line before/after — incl. main.py:1514), env-var guard implementation for BOTH send_daily_email + send_crash_email, state-health marker integration, AST walker output.
</output>
