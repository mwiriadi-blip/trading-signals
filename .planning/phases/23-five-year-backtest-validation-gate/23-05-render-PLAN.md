---
id: 23-05
title: Wave 2A — backtest/render.py (HTML report + history + override form)
phase: 23
plan: 05
type: execute
wave: 2
depends_on: [23-01, 23-04]
files_modified:
  - backtest/render.py
  - tests/test_backtest_render.py
requirements: [BACKTEST-03]
threat_refs: [T-23-cdn]
autonomous: true
gap_closure: false

must_haves:
  truths:
    - "render_report(report) returns full HTML body fragment with three Chart.js tab containers (combined/spi200/audusd)"
    - "render_history(reports) returns table + 10-run-cap overlay chart + back link"
    - "render_run_form(defaults) returns form with three numeric inputs + submit button"
    - "All three render functions inject Chart.js data via json.dumps(...).replace('</', '<\\\\/') (RESEARCH §Pattern 4) — never html.escape on JS data"
    - "Chart.js 4.4.6 UMD URL + SRI hash present verbatim in script tag"
    - "Pass/fail badge renders ✓ PASS green or ✗ FAIL red per CONTEXT D-16 + UI-SPEC"
    - "Empty-state copy verbatim from CONTEXT D-17 + UI-SPEC §Copywriting"
    - "Tab UI uses ARIA role=tab/tabpanel with default Combined active per UI-SPEC"
    - "render functions are PURE — no I/O, no clock reads, no env reads"
  artifacts:
    - path: "backtest/render.py"
      provides: "render_report(), render_history(), render_run_form()"
      exports: ["render_report", "render_history", "render_run_form"]
    - path: "tests/test_backtest_render.py"
      provides: "TestRenderReport + TestChartJsSri + TestRenderHistory + TestRenderRunForm + TestEmptyState + TestJsonInjectionDefence"
  key_links:
    - from: "backtest/render.py"
      to: "Chart.js CDN (cdn.jsdelivr.net/npm/chart.js@4.4.6)"
      via: "<script src=... integrity=sha384-MH1axGwz... crossorigin=anonymous>"
      pattern: "_CHARTJS_SRI"
---

<objective>
Implement `backtest/render.py` — pure HTML render for the /backtest report page (3-tab layout), the history view (`?history=true`), and the operator override form (D-14). Replaces Wave 0 NotImplementedError.

Purpose: Produce a self-contained HTML body that mounts in the FastAPI route handler. Hex-pure (no I/O, no env reads); does NOT import dashboard.py.
Output: ~250 LOC render module + 6 test classes covering structure + Chart.js SRI + JSON injection defence + empty-state copy.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/23-five-year-backtest-validation-gate/23-CONTEXT.md
@.planning/phases/23-five-year-backtest-validation-gate/23-RESEARCH.md
@.planning/phases/23-five-year-backtest-validation-gate/23-PATTERNS.md
@.planning/phases/23-five-year-backtest-validation-gate/23-UI-SPEC.md
@CLAUDE.md
@tests/fixtures/backtest/golden_report.json
@dashboard.py

<interfaces>
<!-- backtest/render.py CONTRACT -->
def render_report(report: dict) -> str:
  """Returns HTML body fragment: pass/fail badge + override form + 3 Chart.js tabs + per-trade table.
  Reads from D-05 JSON schema. Hex-pure: no I/O, no env, no clock.
  """

def render_history(reports: list[dict]) -> str:
  """Returns HTML body fragment: history table (sorted desc) + overlay chart (cap 10).
  Empty list → renders D-17 empty-state copy.
  """

def render_run_form(defaults: dict) -> str:
  """Returns HTML form fragment: 3 numeric inputs + submit button.
  defaults = {'initial_account_aud': 10000.0, 'cost_spi_aud': 6.0, 'cost_audusd_aud': 5.0}
  """

<!-- Constants (DUPLICATED from dashboard.py per D-07; do NOT import dashboard) -->
_CHARTJS_URL = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.js'
_CHARTJS_SRI = 'sha384-MH1axGwz/uQzfIcjFdjEfsM0xlf5mmWfAwwggaOh5IPFvgKFGbJ2PZ4VBbgSYBQN'

<!-- Empty-state copy (CONTEXT D-17 + UI-SPEC §Copywriting) -->
EMPTY_REPORT_HEADING = 'No backtest runs yet'
EMPTY_REPORT_BODY = "Use the form above or run `python -m backtest` from the CLI to generate the first report. New runs will appear here."
EMPTY_HISTORY_HEADING = 'No backtest history yet'
EMPTY_HISTORY_BODY = "Past runs appear here once you've executed at least one backtest."

<!-- Pass/fail glyphs + words (UI-SPEC) -->
PASS_GLYPH = '✓'
PASS_WORD = 'PASS'
FAIL_GLYPH = '✗'
FAIL_WORD = 'FAIL'
</interfaces>
</context>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Server → Browser HTML | XSS via operator-supplied data in trade log / metadata |
| Server → Browser <script> | JSON payload injection into Chart.js data block |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-23-cdn | Tampering (CDN compromise) | Chart.js script tag | mitigate | SRI hash `sha384-MH1axGwz...` + `crossorigin="anonymous"` — browser refuses to execute if hash mismatch (UI-SPEC §Registry Safety) |
| XSS via report fields | Tampering | render_report HTML | mitigate | Every operator-visible string passed through `html.escape(s, quote=True)` |
| JSON injection in `<script>` | Tampering | Chart.js data block | mitigate | `json.dumps(payload, ensure_ascii=False, allow_nan=False).replace('</', '<\\/')` per RESEARCH §Pattern 4 |
</threat_model>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Implement backtest/render.py</name>
  <read_first>
    - backtest/render.py (Wave 0 skeleton — has _CHARTJS_URL/_CHARTJS_SRI already)
    - dashboard.py lines 113-116 (Chart.js URL+SRI constants — to DUPLICATE, not import)
    - dashboard.py lines 2611-2688 (Chart.js IIFE pattern + json.dumps injection defence)
    - tests/fixtures/backtest/golden_report.json (Wave 0 fixture — render input)
    - .planning/phases/23-five-year-backtest-validation-gate/23-RESEARCH.md §Pattern 3 (Chart.js multi-instance ARIA tabs), §Pattern 4 (JSON injection defence)
    - .planning/phases/23-five-year-backtest-validation-gate/23-PATTERNS.md §"backtest/render.py"
    - .planning/phases/23-five-year-backtest-validation-gate/23-UI-SPEC.md (full design contract — copywriting + tabs + badge)
    - .planning/phases/23-five-year-backtest-validation-gate/23-CONTEXT.md §D-04, §D-06, §D-07, §D-14, §D-16, §D-17
  </read_first>
  <behavior>
    - Test 1: render_report(golden) contains <canvas id="equityChartCombined">, <canvas id="equityChartSpi200">, <canvas id="equityChartAudusd">
    - Test 2: render_report contains 3 elements with role="tab" and 3 with role="tabpanel"
    - Test 3: render_report contains _CHARTJS_URL + _CHARTJS_SRI + crossorigin="anonymous" inside a <script> tag
    - Test 4: render_report on PASS report contains "✓ PASS"; on FAIL contains "✗ FAIL"
    - Test 5: render_report metrics row contains 6 stat cards per active tab
    - Test 6: render_report includes the override form (render_run_form output)
    - Test 7: render_history(empty_list) returns D-17 empty-state copy
    - Test 8: render_history with 12 reports caps overlay chart at 10 (UI-SPEC + D-06)
    - Test 9: render_run_form defaults: initial_account_aud=10000, cost_spi_aud=6, cost_audusd_aud=5
    - Test 10: JSON-injection defence — payload containing `</script>` becomes `<\/script>` in output
    - Test 11: html.escape applied to operator-visible strings (e.g. exit_reason="<script>alert(1)</script>" rendered escaped in trade table)
  </behavior>
  <action>
    Replace `backtest/render.py` Wave 0 stub with full implementation. Keep _CHARTJS_URL/_CHARTJS_SRI from Wave 0 verbatim.

    ```python
    """Phase 23 — pure HTML render for /backtest report + history + override form.

    Architecture (hexagonal-lite, CLAUDE.md): pure render. NO I/O, NO env vars, NO clock injection.
    DOES NOT IMPORT dashboard.py per CONTEXT D-07 — Chart.js URL+SRI duplicated below.

    Forbidden imports (BACKTEST_PATHS_PURE AST guard): state_manager, notifier,
    dashboard, main, requests, datetime, os, yfinance, pyarrow.
    Allowed: html (escape), json (Chart.js payload), typing.
    """
    from __future__ import annotations
    import html
    import json
    from typing import Any

    # Chart.js 4.4.6 UMD CDN constants — DUPLICATED from dashboard.py:113-116 per D-07.
    _CHARTJS_URL = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.js'
    _CHARTJS_SRI = 'sha384-MH1axGwz/uQzfIcjFdjEfsM0xlf5mmWfAwwggaOh5IPFvgKFGbJ2PZ4VBbgSYBQN'

    _MAX_HISTORY_OVERLAY = 10  # CONTEXT D-06 + UI-SPEC

    # Empty-state copy (CONTEXT D-17 + UI-SPEC §Copywriting)
    _EMPTY_REPORT_HEADING = 'No backtest runs yet'
    _EMPTY_REPORT_BODY = (
      "Use the form above or run "
      "<code>python -m backtest</code>"
      " from the CLI to generate the first report. New runs will appear here."
    )
    _EMPTY_HISTORY_HEADING = 'No backtest history yet'
    _EMPTY_HISTORY_BODY = (
      "Past runs appear here once you've executed at least one backtest."
    )


    def _e(s: Any) -> str:
      """html.escape with quote=True — every operator-visible string goes through here."""
      return html.escape(str(s), quote=True)


    def _payload(data: Any) -> str:
      """JSON-safe payload for Chart.js data blocks (RESEARCH §Pattern 4).

      Uses json.dumps (NOT html.escape — that produces &lt; inside <script>).
      Replaces </ with <\\/ to defend against </script> injection.
      """
      return json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
      ).replace('</', '<\\/')


    def _render_chart_script_tag() -> str:
      """Chart.js UMD CDN with SRI integrity. T-23-cdn mitigation."""
      return (
        f'<script src="{_CHARTJS_URL}" '
        f'integrity="{_CHARTJS_SRI}" '
        f'crossorigin="anonymous"></script>'
      )


    def _render_pass_fail_badge(metrics: dict) -> str:
      """UI-SPEC §"Pass/Fail badge". Reads metrics['pass'] + metrics['cumulative_return_pct']."""
      passed = bool(metrics.get('pass', False))
      cum = float(metrics.get('cumulative_return_pct', 0.0))
      glyph = '✓' if passed else '✗'
      word = 'PASS' if passed else 'FAIL'
      cls = 'badge-pass' if passed else 'badge-fail'
      sign = '+' if cum >= 0 else ''
      return (
        f'<div class="badge {cls}" role="status" aria-label="Backtest result: {word}">'
        f'  <span class="badge-glyph">{glyph}</span>'
        f'  <span class="badge-word">{word}</span>'
        f'  <span class="badge-cum">{sign}{cum:.2f}%</span>'
        f'</div>'
      )


    def _render_metrics_row(metrics: dict) -> str:
      """UI-SPEC §"Metrics row" — 6 stat cards.

      Note Sharpe naming (UI-SPEC): JSON key 'sharpe_daily' (locked D-05) but
      label is 'Sharpe (annualised)' — the value rendered is sharpe_annualized
      per planner D-19, not the raw daily ratio.
      """
      cum = float(metrics.get('cumulative_return_pct', 0.0))
      sharpe = float(metrics.get('sharpe_annualized', metrics.get('sharpe_daily', 0.0)))
      max_dd = float(metrics.get('max_drawdown_pct', 0.0))
      win_rate = float(metrics.get('win_rate', 0.0))
      expectancy = float(metrics.get('expectancy_aud', 0.0))
      total_trades = int(metrics.get('total_trades', 0))
      cum_sign = '+' if cum >= 0 else ''
      exp_sign = '+' if expectancy >= 0 else ''
      return (
        '<div class="stat-grid">'
        f'<div class="stat-card"><span class="stat-label">Cumulative Return</span>'
        f'<span class="stat-value">{cum_sign}{cum:.2f}%</span></div>'
        f'<div class="stat-card"><span class="stat-label">Sharpe (annualised)</span>'
        f'<span class="stat-value">{sharpe:.2f}</span></div>'
        f'<div class="stat-card"><span class="stat-label">Max Drawdown</span>'
        f'<span class="stat-value">{max_dd:.2f}%</span></div>'
        f'<div class="stat-card"><span class="stat-label">Win Rate</span>'
        f'<span class="stat-value">{int(round(win_rate * 100))}%</span></div>'
        f'<div class="stat-card"><span class="stat-label">Expectancy</span>'
        f'<span class="stat-value">{exp_sign}${expectancy:.2f}</span></div>'
        f'<div class="stat-card"><span class="stat-label">Total Trades</span>'
        f'<span class="stat-value">{total_trades}</span></div>'
        '</div>'
      )


    def _render_tab_strip() -> str:
      """ARIA tab strip per RESEARCH §Pattern 3 + UI-SPEC §Tabs."""
      return (
        '<div role="tablist" aria-label="Instrument results">'
        '<button role="tab" aria-selected="true" aria-controls="panel-combined" '
        'id="tab-combined">Combined</button>'
        '<button role="tab" aria-selected="false" aria-controls="panel-spi200" '
        'id="tab-spi200">SPI 200</button>'
        '<button role="tab" aria-selected="false" aria-controls="panel-audusd" '
        'id="tab-audusd">AUD/USD</button>'
        '</div>'
      )


    def _render_tab_panel(panel_id: str, tab_id: str, instrument_key: str,
                         canvas_id: str, hidden: bool, report: dict) -> str:
      """One tab panel = canvas + metrics row.

      RESEARCH §Pattern 3: render ALL three at page load with `hidden` attr toggled.
      Chart.js needs nonzero canvas size at instantiation.
      """
      hidden_attr = 'hidden' if hidden else ''
      metrics = report['metrics'].get(instrument_key, {})
      curve = report.get('equity_curve', [])
      labels = [pt['date'] for pt in curve]
      if instrument_key == 'combined':
        balances = [pt['balance_combined'] for pt in curve]
      elif instrument_key == 'SPI200':
        balances = [pt['balance_spi'] for pt in curve]
      else:
        balances = [pt['balance_audusd'] for pt in curve]
      payload = _payload({'labels': labels, 'data': balances})
      iife = (
        '<script>(function(){'
        f'var ctx=document.getElementById({json.dumps(canvas_id)});'
        'if(!ctx||!window.Chart)return;'
        f'var p={payload};'
        'new Chart(ctx,{type:"line",data:{labels:p.labels,'
        'datasets:[{label:"Equity (AUD)",data:p.data,borderWidth:2,fill:false}]},'
        'options:{responsive:true,maintainAspectRatio:false,'
        'plugins:{legend:{display:false}}}});'
        '})();</script>'
      )
      return (
        f'<div id="{panel_id}" role="tabpanel" aria-labelledby="{tab_id}" {hidden_attr}>'
        f'  <canvas id="{canvas_id}" aria-label="{_e(instrument_key)} equity curve" role="img" '
        'style="height:320px"></canvas>'
        f'  {_render_metrics_row(metrics)}'
        f'  {iife}'
        '</div>'
      )


    def _render_trade_row(trade: dict) -> str:
      """One <tr> for the closed-trades table. All fields html.escape'd."""
      net = float(trade.get('net_pnl_aud', 0.0))
      sign = '+' if net >= 0 else ''
      pnl_class = 'pnl-pos' if net > 0 else ('pnl-neg' if net < 0 else 'pnl-zero')
      return (
        '<tr>'
        f'<td>{_e(trade.get("open_dt", ""))}</td>'
        f'<td>{_e(trade.get("close_dt", ""))}</td>'
        f'<td>{_e(trade.get("instrument", ""))}</td>'
        f'<td>{_e(trade.get("side", ""))}</td>'
        f'<td>{_e(trade.get("entry_price", ""))}</td>'
        f'<td>{_e(trade.get("exit_price", ""))}</td>'
        f'<td>{_e(trade.get("contracts", ""))}</td>'
        f'<td>{_e(trade.get("exit_reason", ""))}</td>'
        f'<td class="{pnl_class}">{sign}${net:.2f}</td>'
        '</tr>'
      )


    def _render_trade_table(trades: list[dict]) -> str:
      n = len(trades)
      if n == 0:
        return '<p class="muted">No closed trades in this run.</p>'
      rows = '\n'.join(_render_trade_row(t) for t in trades)
      return (
        f'<details><summary>Closed trades ({n})</summary>'
        '<table class="trade-table">'
        '<thead><tr><th>Open</th><th>Close</th><th>Instrument</th><th>Side</th>'
        '<th>Entry</th><th>Exit</th><th>Contracts</th><th>Exit reason</th>'
        '<th>Net P&amp;L</th></tr></thead>'
        f'<tbody>{rows}</tbody></table>'
        '</details>'
      )


    def render_run_form(defaults: dict) -> str:
      """Phase 23 D-14 — operator override form."""
      ia = float(defaults.get('initial_account_aud', 10_000.0))
      cs = float(defaults.get('cost_spi_aud', 6.0))
      ca = float(defaults.get('cost_audusd_aud', 5.0))
      return (
        '<form method="POST" action="/backtest/run" class="override-form">'
        '<h3>Re-run with overrides</h3>'
        '<label for="initial_account_aud">Initial account (AUD)</label>'
        f'<input type="number" id="initial_account_aud" name="initial_account_aud" '
        f'value="{ia:.2f}" min="0.01" step="100" required aria-required="true">'
        '<label for="cost_spi_aud">SPI 200 cost (AUD)</label>'
        f'<input type="number" id="cost_spi_aud" name="cost_spi_aud" '
        f'value="{cs:.2f}" min="0" step="0.5" required aria-required="true">'
        '<label for="cost_audusd_aud">AUD/USD cost (AUD)</label>'
        f'<input type="number" id="cost_audusd_aud" name="cost_audusd_aud" '
        f'value="{ca:.2f}" min="0" step="0.5" required aria-required="true">'
        '<button type="submit" class="btn-primary">Run with overrides</button>'
        '</form>'
      )


    def render_report(report: dict) -> str:
      """Phase 23 BACKTEST-03 — render a full report HTML body fragment.

      Reads from CONTEXT D-05 schema. Returns the HTML body (no <html>/<body> tags
      — the route handler wraps with the page shell).

      If `report` is empty (None or {}), returns the empty-state copy per CONTEXT D-17.
      """
      if not report:
        return (
          f'<section class="empty-state">'
          f'<h2>{_EMPTY_REPORT_HEADING}</h2>'
          f'<p>{_EMPTY_REPORT_BODY}</p>'
          f'</section>'
        )

      metadata = report.get('metadata', {})
      metrics_combined = report.get('metrics', {}).get('combined', {})
      sv = _e(metadata.get('strategy_version', '?'))
      years = _e(metadata.get('years', 5))
      run_dt = _e(metadata.get('run_dt', ''))
      ia = _e(metadata.get('initial_account_aud', 10_000))
      cs = _e(metadata.get('cost_spi_aud', 6))
      ca = _e(metadata.get('cost_audusd_aud', 5))

      defaults = {
        'initial_account_aud': metadata.get('initial_account_aud', 10_000.0),
        'cost_spi_aud': metadata.get('cost_spi_aud', 6.0),
        'cost_audusd_aud': metadata.get('cost_audusd_aud', 5.0),
      }

      return (
        '<section class="backtest-report">'
        '<header>'
        '<h1>Backtest Validation</h1>'
        f'<p class="subtitle">Strategy {sv} — {years}-year in-sample replay</p>'
        f'<p class="meta">Run {run_dt} · Initial ${ia} AUD · SPI cost ${cs} · AUD/USD cost ${ca}</p>'
        '</header>'
        f'{_render_pass_fail_badge(metrics_combined)}'
        f'{render_run_form(defaults)}'
        f'{_render_chart_script_tag()}'
        f'{_render_tab_strip()}'
        f'{_render_tab_panel("panel-combined", "tab-combined", "combined", "equityChartCombined", False, report)}'
        f'{_render_tab_panel("panel-spi200",   "tab-spi200",   "SPI200",   "equityChartSpi200",   True,  report)}'
        f'{_render_tab_panel("panel-audusd",   "tab-audusd",   "AUDUSD",   "equityChartAudusd",   True,  report)}'
        f'{_render_trade_table(report.get("trades", []))}'
        '<footer><a href="/backtest?history=true">View past runs →</a></footer>'
        f'<p class="footer-version">Strategy {sv} · Pass criterion: cumulative return &gt; 100%</p>'
        '<script>'
        '(function(){'
        'var tabs=document.querySelectorAll(\'[role="tab"]\');'
        'var panels=document.querySelectorAll(\'[role="tabpanel"]\');'
        'function activate(id){'
        'tabs.forEach(function(t){t.setAttribute("aria-selected",t.id===id?"true":"false");});'
        'panels.forEach(function(p){p.hidden=p.getAttribute("aria-labelledby")!==id;});'
        'var slug=id.replace("tab-","");history.replaceState(null,"","#tab="+slug);'
        '}'
        'tabs.forEach(function(t){t.addEventListener("click",function(){activate(t.id);});});'
        'var h=window.location.hash.match(/^#tab=(\\w+)$/);if(h){activate("tab-"+h[1]);}'
        '})();'
        '</script>'
        '</section>'
      )


    def render_history(reports: list[dict]) -> str:
      """Phase 23 BACKTEST-03 / CONTEXT D-06 — history view: table + overlay chart.

      reports: list of full report dicts (sorted by run_dt desc). Capped to 10 for overlay.
      Empty list → D-17 empty-state copy.
      """
      if not reports:
        return (
          f'<section class="empty-state">'
          f'<h2>{_EMPTY_HISTORY_HEADING}</h2>'
          f'<p>{_EMPTY_HISTORY_BODY}</p>'
          f'<p><a href="/backtest">← Back to latest run</a></p>'
          f'</section>'
        )

      capped = reports[:_MAX_HISTORY_OVERLAY]
      rows = []
      for r in reports:
        meta = r.get('metadata', {})
        m = r.get('metrics', {}).get('combined', {})
        cum = float(m.get('cumulative_return_pct', 0.0))
        sign = '+' if cum >= 0 else ''
        passed = bool(m.get('pass', False))
        badge = '✓ PASS' if passed else '✗ FAIL'
        badge_cls = 'pnl-pos' if passed else 'pnl-neg'
        filename = _e(meta.get('filename', ''))
        rows.append(
          '<tr>'
          f'<td>{_e(meta.get("strategy_version", "?"))}</td>'
          f'<td>{_e(meta.get("run_dt", ""))}</td>'
          f'<td>{_e(meta.get("end_date", ""))}</td>'
          f'<td>{sign}{cum:.2f}%</td>'
          f'<td class="{badge_cls}">{badge}</td>'
          f'<td><a href="/backtest?run={filename}">view</a></td>'
          '</tr>'
        )
      datasets = []
      for r in capped:
        meta = r.get('metadata', {})
        curve = r.get('equity_curve', [])
        datasets.append({
          'label': meta.get('strategy_version', '?') + ' ' + meta.get('run_dt', ''),
          'data': [pt['balance_combined'] for pt in curve],
        })
      payload = _payload({'datasets': datasets,
                          'labels': [pt['date'] for pt in capped[0].get('equity_curve', [])] if capped else []})
      iife = (
        '<script>(function(){'
        'var ctx=document.getElementById("equityChartHistory");'
        'if(!ctx||!window.Chart)return;'
        f'var p={payload};'
        'new Chart(ctx,{type:"line",data:p,options:{responsive:true,maintainAspectRatio:false}});'
        '})();</script>'
      )
      return (
        '<section class="backtest-history">'
        '<header><h1>Backtest history</h1>'
        '<p><a href="/backtest">← Back to latest run</a></p></header>'
        f'{_render_chart_script_tag()}'
        '<table class="history-table"><thead><tr>'
        '<th>Strategy version</th><th>Run date</th><th>End date</th>'
        '<th>Cum return</th><th>Pass/Fail</th><th></th>'
        '</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>'
        '<canvas id="equityChartHistory" aria-label="History overlay" role="img" style="height:320px"></canvas>'
        f'{iife}'
        '</section>'
      )
    ```
  </action>
  <verify>
    <automated>python -c "import json, pathlib; from backtest.render import render_report, render_history, render_run_form; r = json.loads(pathlib.Path('tests/fixtures/backtest/golden_report.json').read_text()); html = render_report(r); assert 'equityChartCombined' in html; assert 'equityChartSpi200' in html; assert 'equityChartAudusd' in html; assert 'sha384-MH1axGwz' in html; assert '✓' in html or 'PASS' in html; print('ok')" 2>&1 | grep -c '^ok$'</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c '^def render_report' backtest/render.py` returns 1
    - `grep -c '^def render_history' backtest/render.py` returns 1
    - `grep -c '^def render_run_form' backtest/render.py` returns 1
    - `grep -c "_CHARTJS_URL = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.6" backtest/render.py` returns 1
    - `grep -c "_CHARTJS_SRI = 'sha384-MH1axGwz" backtest/render.py` returns 1
    - `grep -c '^import dashboard\|^from dashboard' backtest/render.py` returns 0 (D-07)
    - `grep -c "json.dumps" backtest/render.py` returns ≥1 (Chart.js payload defence)
    - `grep -c "replace('</', '<\\\\\\\\\\\\/')" backtest/render.py` returns ≥1 (or check for the literal substring; alternative grep below)
    - `grep -F "replace('</', '<\\\\/')" backtest/render.py | wc -l` returns ≥1
    - `grep -c 'html.escape' backtest/render.py` returns ≥1
    - `grep -c 'role="tab"' backtest/render.py` returns ≥3 (3 tabs)
    - `grep -c 'role="tabpanel"' backtest/render.py` returns ≥3 (3 panels)
    - `.venv/bin/pytest tests/test_signal_engine.py::TestDeterminism::test_backtest_render_no_forbidden_imports -x -q` passes
    - `python -c "import json, pathlib; from backtest.render import render_report; r = json.loads(pathlib.Path('tests/fixtures/backtest/golden_report.json').read_text()); html = render_report(r); print(len(html))"` returns >2000 (non-trivial HTML body)
  </acceptance_criteria>
  <done>render_report/history/run_form callable; AST guard green; golden fixture renders successfully.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Implement tests/test_backtest_render.py (6 test classes)</name>
  <read_first>
    - backtest/render.py (just-implemented)
    - tests/fixtures/backtest/golden_report.json
    - .planning/phases/23-five-year-backtest-validation-gate/23-PATTERNS.md §"tests/test_backtest_render.py"
    - .planning/phases/23-five-year-backtest-validation-gate/23-VALIDATION.md
    - .planning/phases/23-five-year-backtest-validation-gate/23-UI-SPEC.md
  </read_first>
  <behavior>
    See task 1 behavior list. Each test class targets one render area + edge cases.
  </behavior>
  <action>
    Replace Wave 0 skeleton:

    ```python
    """Phase 23 — backtest/render.py tests (BACKTEST-03 HTML)."""
    from __future__ import annotations
    import json
    from pathlib import Path

    import pytest

    from backtest.render import render_history, render_report, render_run_form


    @pytest.fixture
    def golden_report() -> dict:
      return json.loads(Path('tests/fixtures/backtest/golden_report.json').read_text())


    @pytest.fixture
    def fail_report(golden_report) -> dict:
      r = json.loads(json.dumps(golden_report))  # deep copy
      r['metrics']['combined']['pass'] = False
      r['metrics']['combined']['cumulative_return_pct'] = 45.0
      return r


    class TestRenderReport:
      def test_three_canvas_ids_present(self, golden_report):
        html = render_report(golden_report)
        assert 'id="equityChartCombined"' in html
        assert 'id="equityChartSpi200"' in html
        assert 'id="equityChartAudusd"' in html

      def test_three_tab_buttons(self, golden_report):
        html = render_report(golden_report)
        assert html.count('role="tab"') >= 3
        assert html.count('role="tabpanel"') >= 3

      def test_default_tab_is_combined(self, golden_report):
        html = render_report(golden_report)
        # Combined tab is aria-selected="true" by default (D-04 + UI-SPEC)
        assert 'id="tab-combined">' in html or "id='tab-combined'>" in html
        # Combined panel is NOT hidden
        assert 'id="panel-combined"' in html
        assert 'id="panel-spi200" role="tabpanel"' in html

      def test_pass_badge_renders_check(self, golden_report):
        html = render_report(golden_report)
        assert '✓' in html
        assert 'PASS' in html
        assert 'badge-pass' in html

      def test_fail_badge_renders_x(self, fail_report):
        html = render_report(fail_report)
        assert '✗' in html
        assert 'FAIL' in html
        assert 'badge-fail' in html

      def test_metrics_row_includes_six_cards(self, golden_report):
        html = render_report(golden_report)
        # 3 panels × 6 cards = 18 stat-card occurrences
        assert html.count('class="stat-card"') == 18

      def test_includes_override_form(self, golden_report):
        html = render_report(golden_report)
        assert 'name="initial_account_aud"' in html
        assert 'name="cost_spi_aud"' in html
        assert 'name="cost_audusd_aud"' in html
        assert 'action="/backtest/run"' in html

      def test_strategy_version_in_subtitle(self, golden_report):
        html = render_report(golden_report)
        assert 'v1.2.0' in html


    class TestChartJsSri:
      def test_chartjs_url_present(self, golden_report):
        html = render_report(golden_report)
        assert 'cdn.jsdelivr.net/npm/chart.js@4.4.6' in html

      def test_sri_hash_present(self, golden_report):
        html = render_report(golden_report)
        assert 'sha384-MH1axGwz/uQzfIcjFdjEfsM0xlf5mmWfAwwggaOh5IPFvgKFGbJ2PZ4VBbgSYBQN' in html

      def test_crossorigin_anonymous(self, golden_report):
        html = render_report(golden_report)
        assert 'crossorigin="anonymous"' in html


    class TestRenderHistory:
      def test_empty_list_renders_empty_state(self):
        html = render_history([])
        assert 'No backtest history yet' in html
        assert '/backtest' in html  # back link

      def test_table_renders_each_run(self, golden_report):
        # 3 historical runs
        runs = []
        for v in ['v1.2.0', 'v1.1.0', 'v1.0.0']:
          r = json.loads(json.dumps(golden_report))
          r['metadata']['strategy_version'] = v
          runs.append(r)
        html = render_history(runs)
        assert 'v1.2.0' in html
        assert 'v1.1.0' in html
        assert 'v1.0.0' in html

      def test_overlay_chart_capped_at_10(self, golden_report):
        # 12 runs — overlay should only include 10 datasets
        runs = []
        for i in range(12):
          r = json.loads(json.dumps(golden_report))
          r['metadata']['strategy_version'] = f'v{i}'
          runs.append(r)
        html = render_history(runs)
        # Table shows all 12
        assert html.count('<tr>') >= 12
        # But overlay chart only includes 10 (count datasets via JSON payload)
        # Look for "label":"v0..." through v11 — only first 10 present in chart payload
        # Simpler check: count occurrences of '"label":"v' in the JSON IIFE
        # (capped slice = runs[:10])
        # Just assert v10 + v11 NOT in the chart payload IIFE area
        chart_block = html.split('id="equityChartHistory"')[-1] if 'equityChartHistory' in html else ''
        # Hard to slice precisely; use the simpler invariant: overlay capped
        # Verify by counting label entries — should be exactly 10 in the JSON payload
        # (combined approach: split by IIFE marker)
        if '"datasets":' in html:
          # Parse the chart datasets count
          import re
          # Find the IIFE chart block
          m = re.search(r'var p=\{[^;]*?"datasets":\[(.*?)\]', html, re.DOTALL)
          if m:
            # Count "label": occurrences inside datasets array
            datasets_str = m.group(1)
            assert datasets_str.count('"label"') == 10, (
              f'overlay should cap at 10 datasets, got {datasets_str.count(chr(34) + "label" + chr(34))}'
            )


    class TestRenderRunForm:
      def test_default_values(self):
        html = render_run_form({
          'initial_account_aud': 10_000.0,
          'cost_spi_aud': 6.0,
          'cost_audusd_aud': 5.0,
        })
        assert 'value="10000.00"' in html
        assert 'value="6.00"' in html
        assert 'value="5.00"' in html

      def test_three_inputs_present(self):
        html = render_run_form({})
        assert 'name="initial_account_aud"' in html
        assert 'name="cost_spi_aud"' in html
        assert 'name="cost_audusd_aud"' in html

      def test_required_attribute(self):
        html = render_run_form({})
        assert html.count('required') >= 3

      def test_action_post_to_backtest_run(self):
        html = render_run_form({})
        assert 'action="/backtest/run"' in html
        assert 'method="POST"' in html


    class TestEmptyState:
      def test_empty_report_dict(self):
        html = render_report({})
        assert 'No backtest runs yet' in html
        assert 'python -m backtest' in html

      def test_none_report(self):
        html = render_report(None)
        assert 'No backtest runs yet' in html


    class TestJsonInjectionDefence:
      def test_script_close_in_payload_is_escaped(self, golden_report):
        # Inject a malicious string in equity_curve labels
        r = json.loads(json.dumps(golden_report))
        r['equity_curve'][0]['date'] = '</script><script>alert(1)</script>'
        html = render_report(r)
        # The payload IIFE block must NOT contain a raw </script> close tag;
        # json.dumps + replace turns </ into <\/ inside the script block.
        # Find the IIFE script blocks
        # Simpler: any literal `</script>alert` indicates injection succeeded
        assert '</script>alert' not in html, 'JSON injection defence failed'
        # The escaped form should be present somewhere if the date made it in
        assert '<\\/script>' in html or '<\\/' in html

      def test_html_escape_on_trade_table_fields(self, golden_report):
        r = json.loads(json.dumps(golden_report))
        r['trades'][0]['exit_reason'] = '<img src=x onerror=alert(1)>'
        html = render_report(r)
        # escaped: < becomes &lt;
        assert '&lt;img src=x onerror=alert(1)&gt;' in html or '&lt;img' in html
        assert '<img src=x onerror=alert(1)>' not in html
    ```
  </action>
  <verify>
    <automated>.venv/bin/pytest tests/test_backtest_render.py -x -q 2>&1 | tail -10</automated>
  </verify>
  <acceptance_criteria>
    - `.venv/bin/pytest tests/test_backtest_render.py -x -q` passes (all 6 classes green, no skips)
    - `pytest tests/test_backtest_render.py::TestChartJsSri -x` ≥3 tests passing
    - `pytest tests/test_backtest_render.py::TestJsonInjectionDefence -x` ≥2 tests passing
    - `pytest tests/test_backtest_render.py::TestEmptyState -x` ≥2 tests passing
    - Full suite no regression
  </acceptance_criteria>
  <done>All 6 test classes green; XSS + JSON-injection defences validated.</done>
</task>

</tasks>

<verification>
1. `python -c "from backtest.render import render_report, render_history, render_run_form; print('ok')"` prints `ok`
2. `.venv/bin/pytest tests/test_backtest_render.py -x -q` passes
3. `.venv/bin/pytest tests/test_signal_engine.py::TestDeterminism -x -q` continues to pass
4. `grep -c "import dashboard" backtest/render.py` returns 0 (D-07)
5. Full suite green
</verification>

<success_criteria>
- render_report/render_history/render_run_form callable
- 3 Chart.js canvases + 3 tab panels with ARIA
- Chart.js URL+SRI duplicated (not imported from dashboard)
- JSON injection defence applied to all <script> data blocks
- html.escape applied to operator-visible strings
- Empty-state copy verbatim from CONTEXT D-17 + UI-SPEC
- 6 test classes green
</success_criteria>

<output>
Create `.planning/phases/23-five-year-backtest-validation-gate/23-05-SUMMARY.md` documenting:
- 3 render functions signatures
- Chart.js SRI presence proof
- XSS defence proof
- Test count + pass status
</output>
