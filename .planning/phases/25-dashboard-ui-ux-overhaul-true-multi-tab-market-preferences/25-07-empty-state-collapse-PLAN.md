---
phase: 25
plan: 07
type: execute
wave: 3
depends_on: [25-01, 25-02]
files_modified:
  - dashboard_renderer/components/signals.py
  - dashboard_renderer/stats.py
  - dashboard.py
autonomous: true
requirements: [P25-04, P25-05, P25-06]
must_haves:
  truths:
    - "When state['last_run'] is None: zero <table class=trace-indicators-table> in output; one onboarding card with the locked copy 'Awaiting first daily run'"
    - "Stats bar omitted from DOM (not display:none) when closed_paper_trades + closed_live_trades < 1"
    - "Equity chart hidden (canvas absent) when number of distinct (date, equity) tuples in state.equity_history < 5"
    - "When equity tuples >= 5, chart renders using the deduped distinct list (not the raw equity_history)"
  artifacts:
    - path: dashboard_renderer/components/signals.py
      provides: "_render_trace_panels gated on state.get('last_run') — emits onboarding card when None, full trace tables otherwise"
      contains: "Awaiting first daily run"
    - path: dashboard_renderer/stats.py
      provides: "Stats bar render function returns '' when closed_trades_total < 1"
      contains: "stats-bar"
    - path: dashboard.py
      provides: "_distinct_equity_tuples helper + equity chart hidden when len(distinct) < 5"
      contains: "_distinct_equity_tuples"
  key_links:
    - from: "render_signal_cards"
      to: "_render_trace_panels"
      via: "Trace panels emitted only when last_run is set"
      pattern: "last_run is None"
    - from: "render_dashboard equity slot"
      to: "_distinct_equity_tuples"
      via: "len(distinct) < 5 → hide canvas"
      pattern: "_distinct_equity_tuples"
---

<objective>
Wave 3. Implement first-run empty-state collapse per D-09/D-10/D-11. Hides 11-table trace panels behind one onboarding card on first install; hides stats bar until closed trades exist; hides equity chart until ≥5 distinct (date, equity) points.

Output: gated rendering of trace panels, stats bar, and equity chart based on D-09/D-10/D-11 thresholds.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-RESEARCH.md
@.planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-UI-SPEC.md
@dashboard_renderer/components/signals.py
@dashboard_renderer/stats.py
@dashboard.py

<interfaces>
# Per RESEARCH §9: trace tables live inside <details class="trace-disclosure" data-instrument="...">
# rendered by dashboard.py:_render_trace_panels (called from signals.py:60). 
# Wrap entire <details> emission in `if state.get('last_run') is None: return ''` else existing render.
#
# Per RESEARCH §11: equity chart current branch already hides on totally empty equity_history;
# extend to hide when distinct tuples < 5. Helper _distinct_equity_tuples deduplicates by (date, equity).
#
# Per UI-SPEC §First-run empty state and §Equity chart empty state: exact copy locked.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Gate trace panels (D-09) and stats bar (D-10)</name>
  <read_first>
    - dashboard_renderer/components/signals.py (existing render_signal_cards)
    - dashboard.py — locate _render_trace_panels (called from signals.py)
    - dashboard_renderer/stats.py (existing stats-bar renderer)
    - .planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-UI-SPEC.md §First-run empty state, §Stats bar empty state
  </read_first>
  <files>dashboard_renderer/components/signals.py, dashboard.py, dashboard_renderer/stats.py</files>
  <action>
**Step 1 — gate trace panels in dashboard.py:_render_trace_panels:**

Add the D-09 gate at the top of the function:

```python
def _render_trace_panels(state, instrument, ...existing args...):
    # Phase 25 D-09: hide trace tables on first run; render single onboarding card instead.
    if state.get('last_run') is None:
        return (
            '<section class="onboarding-card" aria-labelledby="onboarding-heading">\n'
            '  <h3 id="onboarding-heading">Awaiting first daily run</h3>\n'
            '  <p>Calculations and equity curve will populate after the first cycle at 08:00 AWST.</p>\n'
            '</section>\n'
        )
    # ... existing render code unchanged ...
```

The onboarding card emits ONCE per page (not per instrument). Achieve this by emitting it from the parent caller (signals.py) when `last_run is None`, and short-circuiting `_render_trace_panels` to return ''. Choose whichever is cleaner — the single-card-once invariant matters.

Recommended: in `dashboard_renderer/components/signals.py:render_signal_cards`, check `state.get('last_run')` ONCE at the top:

```python
def render_signal_cards(state):
    if state.get('last_run') is None:
        return (
            '<section class="onboarding-card" aria-labelledby="onboarding-heading">\n'
            '  <h3 id="onboarding-heading">Awaiting first daily run</h3>\n'
            '  <p>Calculations and equity curve will populate after the first cycle at 08:00 AWST.</p>\n'
            '</section>\n'
        )
    # ... existing per-instrument card rendering ...
```

This ensures the FLAT/LONG/SHORT cards (which are the user-facing market summary) and the trace tables (the deep-dive panels) BOTH collapse to the single onboarding card on first run. Preserves the D-09 intent (RESEARCH §9: "the cards STAY — D-09 is about trace tables being a 'wall of n/a'") — but on TRUE first run (last_run is None) there is NO signal data anyway, so hiding the cards is correct. Once `last_run` is set, both cards and trace tables render normally.

**Step 2 — gate stats bar in dashboard_renderer/stats.py:**

Locate the stats-bar renderer (probably named `render_stats_grid` or similar). Add the D-10 gate:

```python
def render_stats_grid(state):
    # Phase 25 D-10: hide stats bar until at least one closed trade exists.
    paper_trades = state.get('paper_trades', []) or []
    closed_paper = sum(1 for t in paper_trades if isinstance(t, dict) and t.get('status') == 'closed')
    closed_trades = state.get('closed_trades', []) or []
    closed_live = len(closed_trades)
    if (closed_paper + closed_live) < 1:
        return ''  # zero DOM (not display:none)
    # ... existing render unchanged ...
```

**Step 3 — flip xfail decorators on tests:**

Remove `@pytest.mark.xfail` from `tests/test_dashboard.py::TestPhase25FirstRun` and `TestPhase25StatsBar`. Run pytest, confirm green.
  </action>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && python -m pytest tests/test_dashboard.py::TestPhase25FirstRun tests/test_dashboard.py::TestPhase25StatsBar -q --no-header 2>&1 | tail -10</automated>
  </verify>
  <done>
    - render_signal_cards returns onboarding card only when last_run is None
    - Stats bar renderer returns '' when closed trades total is 0
    - All xfail tests for FirstRun and StatsBar now PASS
  </done>
</task>

<task type="auto">
  <name>Task 2: Gate equity chart (D-11) with distinct (date, equity) tuple count</name>
  <read_first>
    - dashboard.py — locate `_render_equity_chart_container` (around line 2514 per RESEARCH §11)
    - .planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-RESEARCH.md §11 (full implementation pattern)
    - .planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-UI-SPEC.md §Equity chart empty state
  </read_first>
  <files>dashboard.py</files>
  <action>
Add helper near the top of dashboard.py (or in dashboard_renderer/formatters.py if grouping with the other helpers):

```python
def _distinct_equity_tuples(equity_history: list) -> list:
    """Phase 25 D-11: dedupe (date, equity) tuples; chart hides until >=5 distinct.
    
    Three identical {date: '2026-04-23', equity: 100000.0} produces ONE distinct entry, not three.
    """
    seen = set()
    distinct = []
    for row in equity_history:
        if not isinstance(row, dict):
            continue
        try:
            key = (row['date'], float(row['equity']))
        except (KeyError, TypeError, ValueError):
            continue
        if key not in seen:
            seen.add(key)
            distinct.append(row)
    return distinct
```

Modify `_render_equity_chart_container` (or its current empty-state branch around dashboard.py:2524-2532):

```python
def _render_equity_chart_container(state, ...existing args...):
    equity_history = state.get('equity_history', []) or []
    distinct = _distinct_equity_tuples(equity_history)
    if len(distinct) < 5:
        # D-11 empty state — locked copy from UI-SPEC §Equity chart empty state
        return (
            '<section aria-labelledby="heading-equity">\n'
            '  <h2 id="heading-equity">Equity curve</h2>\n'
            '  <div class="empty-state">'
            'Chart appears once 5 daily equity points have been recorded.'
            '</div>\n'
            '</section>\n'
        )
    # Use distinct (NOT raw equity_history) for labels and data
    labels = [row['date'] for row in distinct]
    data = [float(row['equity']) for row in distinct]
    # ... existing canvas + Chart.js render unchanged ...
```

Flip xfail decorators on `tests/test_dashboard.py::TestPhase25Equity`. Run, confirm green.
  </action>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && python -m pytest tests/test_dashboard.py::TestPhase25Equity -q --no-header 2>&1 | tail -5</automated>
  </verify>
  <done>
    - _distinct_equity_tuples helper added
    - Equity chart hidden when distinct tuple count < 5
    - When ≥5, chart uses the deduped list
    - TestPhase25Equity tests PASS
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| state.json read → HTML output | No new attack surface; pure rendering changes. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-25-07-01 | (n/a) | empty-state gating | accept | Pure render-side gating with no new external input. The locked copy strings contain no interpolation. |
</threat_model>

<verification>
- TestPhase25FirstRun (3), TestPhase25StatsBar (2), TestPhase25Equity (2) all PASS.
- Grep gate: `grep -c '<table class="trace-indicators-table"' <(python -c 'from dashboard_renderer.api import render_dashboard; print(render_dashboard({"last_run": None, "markets": {}, "warnings": [], "equity_history": [], "signals": {}, "paper_trades": [], "positions": [], "closed_trades": [], "strategy_settings": {}, "account_balance_paper": 0, "account_balance_live": 0}))')` returns 0.
</verification>

<success_criteria>
- D-09: zero trace tables on first install; one onboarding card with locked copy.
- D-10: stats bar absent from DOM when no closed trades.
- D-11: equity chart hidden until ≥5 distinct (date, equity) tuples.
</success_criteria>

<output>
After completion, create `.planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-07-SUMMARY.md` summarising the gate locations and any callsite updates required.
</output>
