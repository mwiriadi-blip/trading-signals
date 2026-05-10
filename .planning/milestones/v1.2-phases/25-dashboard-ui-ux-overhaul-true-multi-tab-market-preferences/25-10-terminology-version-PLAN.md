---
phase: 25
plan: 10
type: execute
wave: 4
depends_on: [25-02, 25-09]
files_modified:
  - dashboard_renderer/components/paper_trades.py
  - dashboard_renderer/components/footer.py
  - dashboard.py
  - dashboard.html
  - dashboard-signals.html
  - dashboard-account.html
  - dashboard-settings.html
  - dashboard-market-test.html
autonomous: true
requirements: [P25-13, P25-14]
must_haves:
  truths:
    - "Paper-trade form submit button copy is 'Record paper trade' (replaces 'Open Position')"
    - "Live-trade form submit button copy is 'Open live position'"
    - "Account-related labels unified under 'Account' / 'Account balance' (eliminating 'Account Management' tab and 'Account Baseline' form heading)"
    - "All 5 dashboard*.html files render with v1.2.0 strategy version (no v1.0.0 or v1.1.0 literals remain)"
    - "footer.py reads strategy_version from state via _resolve_strategy_version (NOT from system_params — hex boundary preserved)"
  artifacts:
    - path: dashboard_renderer/components/footer.py
      provides: "render_footer takes strategy_version primitive arg; reads via state pipeline (already present pre-Phase-25)"
      contains: "strategy_version"
    - path: dashboard.py
      provides: "Account terminology unified across renderer code"
      contains: "Account"
  key_links:
    - from: "Stale dashboard*.html sibling files"
      to: "Forced regeneration via _REQUIRED_DASHBOARD_MARKER bump (Plan 02)"
      via: "_is_stale → re-render on first request post-deploy"
      pattern: "_REQUIRED_DASHBOARD_MARKER"
---

<objective>
Wave 4 final cleanup. Apply D-21 disambiguating renames and D-22 strategy-version reconciliation. Deletes the 4 stale sibling HTML files (or relies on the marker change from Plan 02 to force regeneration) so the v1.0.0/v1.1.0 literals get replaced with the live `_resolve_strategy_version(state)` output.

Output: button copy renames; "Account Management" / "Account Baseline" / "Account balance" reconciled to "Account" / "Account balance"; all 5 sibling HTML files render with current strategy version.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-RESEARCH.md
@.planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-UI-SPEC.md
@dashboard_renderer/components/paper_trades.py
@dashboard_renderer/components/footer.py
@dashboard.py

<interfaces>
# Per UI-SPEC §Disambiguated buttons:
#   Paper-trade open form submit: 'Open Position' → 'Record paper trade'
#   Live-trade open form submit: 'Open Position' → 'Open live position'
#   Paper-trade close button: → 'Close paper trade'
#   Live-trade close button: → 'Close live position'
#
# Per UI-SPEC §Account page (D-21):
#   Pick ONE term: 'Account balance' chosen as canonical (replaces 'Account Management' tab and 'Account Baseline' form heading).
#   - Function tab label: 'Account' (already updated in Plan 03)
#   - Section heading: 'Account' (already in UI-SPEC)
#   - Form heading: 'Account balance' (replacing 'Account Baseline')
#   - Field label: 'Account balance' (existing)
#   - Save button: 'Update balances' (sentence case, replaces 'Update Balances')
#
# Per UI-SPEC §Strategy version footer:
#   render_footer reads strategy_version from state via _resolve_strategy_version.
#   The 4 stale sibling HTMLs regenerate automatically when Plan 02's marker change forces _is_stale=True.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Apply D-21 button + heading renames in renderer code; D-22 verification of strategy version pipeline</name>
  <read_first>
    - dashboard_renderer/components/paper_trades.py — locate the submit button copy
    - dashboard.py — locate the live-trade `Open Position` button (around line 800 per CONTEXT.md), the `Account Management` tab label, the `Account Baseline` form heading, and the `Update Balances` save button
    - dashboard_renderer/components/footer.py — verify it already reads strategy_version (Phase 22 work; Plan 25-10 is verification + ensuring stale HTMLs regenerate)
    - .planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-RESEARCH.md §7 (strategy version reconciliation) + §Pitfall 4 (stale sibling-page caches)
  </read_first>
  <files>dashboard_renderer/components/paper_trades.py, dashboard.py, dashboard_renderer/components/footer.py</files>
  <action>
**Step 1 — paper-trade button copy in paper_trades.py:**

Locate `<button type="submit">Open position</button>` (or `Open Position`) in render_paper_trade_form (or whatever it's named). Replace text:
- Submit: `Open Position` / `Open position` → `Record paper trade`
- Close button (if rendered here): existing copy → `Close paper trade`

Add `class="btn-primary"` to the submit button if it's not already present (per UI-SPEC).

**Step 2 — live-trade button copy in dashboard.py (or wherever the live-trade form lives):**

Locate the live-trade form's `<button type="submit">Open Position</button>`. Replace text → `Open live position`. Add btn-primary class.

If a live-trade close button exists with generic copy, set it to `Close live position`.

**Step 3 — Account terminology reconciliation in dashboard.py:**

Use grep to find all occurrences:
```bash
grep -n "Account Management\|Account Baseline\|Update Balances" dashboard.py dashboard_renderer/
```

For each match:
- `Account Management` (tab label) → already changed to `Account` in Plan 03; verify and remove residual.
- `Account Baseline` (form heading) → `Account balance`
- `Update Balances` (save button) → `Update balances` (sentence case)

The Account section heading should already be `Account` per UI-SPEC §Account page (the section header subtitle adds the new locked copy `Account-wide controls. Market-agnostic.`).

**Step 4 — verify strategy version pipeline in footer.py:**

`dashboard_renderer/components/footer.py:render_footer(strategy_version)` already takes the version as a primitive argument (Phase 22 work). Verify:
- footer.py does NOT `from system_params import STRATEGY_VERSION` (hex boundary per LEARNINGS 2026-04-27).
- The arg flows from `_resolve_strategy_version(state)` per dashboard.py:1080-1114.
- The displayed copy is `Strategy {strategy_version}` per UI-SPEC.

Run grep:
```bash
grep -rn "from system_params" dashboard_renderer/ dashboard.py
```
Expected: zero results in dashboard_renderer/. Any match must be excised.

**Step 5 — flip xfail decorators on tests:**

Remove `@pytest.mark.xfail` from:
- `tests/test_dashboard.py::TestPhase25ButtonRename` (3 methods)
- `tests/test_dashboard.py::TestPhase25StrategyVersion` (1 method)

Run, confirm green.

**Step 6 — verify 4 sibling HTMLs regenerate:**

Plan 02 changed `_REQUIRED_DASHBOARD_MARKER` to a token absent from current sibling files. After Plan 25-10's deploy, the next request triggers `_is_stale=True` → regeneration via the renderer chain → all 5 files emit current strategy version + new tab classes + new fieldsets + etc.

Pre-deploy local check (manual):
```bash
ls -la dashboard*.html
# Existing HTML files have old marker. New marker in code is Phase 25 "class=\"tabs tabs-function\"".
# After running a request handler that calls render_dashboard, the files get regenerated.
# Test locally by spawning the test harness:
python -c "from web.app import create_app; from fastapi.testclient import TestClient; client=TestClient(create_app()); resp=client.get('/', headers={'X-Trading-Signals-Auth':'a'*32}); print(resp.status_code)"
# Then verify:
grep -l 'v1.0.0\|v1.1.0' dashboard*.html
# Expected: zero files matching (only v1.2.0 should appear — and only if state.signals[*].strategy_version is v1.2.0).
```

If state.json on the dev environment has older strategy_version values in signals[*].strategy_version, the rendered footer reflects that — which is correct per RESEARCH §7 ("the rendered footer is the source for what the operator sees"). To force v1.2.0 in the dev rendering, ensure state.json has `signals.SPI200.strategy_version = 'v1.2.0'`.
  </action>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && grep -rn "from system_params import STRATEGY_VERSION" dashboard_renderer/ 2>&1 | head -3 && python -m pytest tests/test_dashboard.py::TestPhase25ButtonRename tests/test_dashboard.py::TestPhase25StrategyVersion -q --no-header 2>&1 | tail -10</automated>
  </verify>
  <done>
    - Paper-trade button: "Record paper trade"
    - Live-trade button: "Open live position"
    - "Account Management" eliminated; "Account Baseline" replaced by "Account balance"; "Update Balances" → "Update balances"
    - dashboard_renderer/ has zero `from system_params` imports (hex boundary preserved)
    - TestPhase25ButtonRename + TestPhase25StrategyVersion tests PASS
  </done>
</task>

<task type="auto">
  <name>Task 2: Force-regenerate sibling HTMLs + final phase-wide test sweep</name>
  <read_first>
    - web/routes/dashboard.py:_is_stale (around line 119)
    - .planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-RESEARCH.md §Pitfall 4
  </read_first>
  <files>(no source modifications; this task verifies + triggers regeneration on dev)</files>
  <action>
**Step 1 — confirm 5 sibling HTMLs regenerate after marker change:**

Spawn a TestClient request to `/` (and to each market-scoped variant) — each request triggers `_is_stale=True` because the new marker `class="tabs tabs-function"` is absent from the on-disk HTML. The handler regenerates the file:

```bash
python -c "
from fastapi.testclient import TestClient
from web.app import create_app
client = TestClient(create_app())
for path in ['/', '/signals', '/account', '/settings', '/market-test']:
    resp = client.get(path, headers={'X-Trading-Signals-Auth': 'a'*32})
    print(path, resp.status_code)
"
```

After the requests:

```bash
grep -l 'Strategy v1\.0\.0\|Strategy v1\.1\.0' dashboard*.html
# Expected: zero files matched.

grep -l 'Strategy v1\.2\.0' dashboard*.html
# Expected: all 5 files matched (assuming dev state has v1.2.0 signals).
```

If any file still shows old version literals, debug `_is_stale` — the marker change from Plan 02 should have triggered regeneration.

**Step 2 — full Phase 25 xfail sweep:**

Run the full suite with focus on Phase 25 tests:
```bash
pytest tests/ -k "TestPhase25" -q
```

Expected outcome: ALL Phase 25 tests should now be PASS (no XFAIL remaining at end of Plan 10). If any are still XFAIL, identify which acceptance gate is unaddressed and either flip the decorator or document a deferred item in the SUMMARY.

**Step 3 — full suite green check:**

```bash
pytest -q
```

Expected exit code 0. No regressions.

**Step 4 — terminology grep gate:**

```bash
grep -rn "Account Management\|Account Baseline" dashboard_renderer/ dashboard.py 2>/dev/null
# Expected: zero results.

grep -rn "Open Position</button>\|Open position</button>" dashboard_renderer/ dashboard.py 2>/dev/null
# Expected: zero results.
```
  </action>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && python -m pytest tests/ -k "TestPhase25" -q --no-header 2>&1 | tail -15 && grep -rn "Account Management\|Account Baseline" dashboard_renderer/ dashboard.py 2>/dev/null | head -3 || echo "Account terminology unified" && python -m pytest -q --no-header 2>&1 | tail -5</automated>
  </verify>
  <done>
    - All Phase 25 tests PASS (zero XFAIL remaining)
    - Full suite (1319+ tests) green
    - All 5 sibling HTML files render current strategy version (no v1.0.0/v1.1.0)
    - Account terminology grep gate green
    - Button rename grep gate green
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Renderer → HTML output | Pure copy edits + verification; no new attack surface. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-25-10-01 | (n/a) | terminology + version reconcile | accept | Pure copy/render changes; no new logic surfaces or input handlers. Hex-boundary preservation verified by grep gate. |
</threat_model>

<verification>
- All Phase 25 tests PASS.
- Full suite green.
- 5 dashboard*.html files render v1.2.0 footer (assuming state has v1.2.0 signals).
- Account terminology unified to "Account" / "Account balance".
- Paper/live button copy distinct and meaningful.
</verification>

<success_criteria>
- D-21 disambiguating renames complete.
- D-22 strategy version single source of truth via state pipeline; stale literals gone.
- Phase 25 closed at code level: every D-XX decision and every ROADMAP item #1..#10 has implementation + passing tests.
</success_criteria>

<output>
After completion, create `.planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-10-SUMMARY.md` summarising rename locations, regen verification, and the final test counts. This is the last plan; the SUMMARY should also note the overall Phase 25 close-out (number of waves, total file edits, total tests added/flipped).
</output>
