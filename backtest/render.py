"""Phase 23 — pure HTML render for /backtest report + history + override form.

Architecture (hexagonal-lite, CLAUDE.md): pure render. NO I/O, NO env vars,
NO clock injection.
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
  'Use the form above or run '
  '<code>python -m backtest</code>'
  ' from the CLI to generate the first report. New runs will appear here.'
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
  metrics = report.get('metrics', {}).get(instrument_key, {})
  curve = report.get('equity_curve', [])
  labels = [pt.get('date', '') for pt in curve]
  if instrument_key == 'combined':
    balances = [pt.get('balance_combined', 0.0) for pt in curve]
  elif instrument_key == 'SPI200':
    balances = [pt.get('balance_spi', 0.0) for pt in curve]
  else:
    balances = [pt.get('balance_audusd', 0.0) for pt in curve]
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
  """Phase 23 D-14 — operator override form.

  D-14 + UI-SPEC §"Long-running submit UX": on submit, disable the button,
  change label to "Running… (this can take up to 60s)", show a CSS-only
  amber spinner ring (16px, 1s rotation), and set aria-disabled="true".
  Inline ~8 LOC <script> handles the disable + label swap. This prevents
  double-submission during the synchronous 30-60s POST.
  """
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
    # D-14 + UI-SPEC §"Long-running submit UX" — spinner + disable on submit
    '<style>'
    '.spinner{display:none;width:16px;height:16px;border:2px solid #eab308;'
    'border-top-color:transparent;border-radius:50%;'
    'animation:spin 1s linear infinite;vertical-align:middle;margin-left:8px}'
    '@keyframes spin{to{transform:rotate(360deg)}}'
    'form.running .spinner{display:inline-block}'
    '</style>'
    '<span class="spinner" aria-hidden="true"></span>'
    '<script>'
    '(function(){'
    'var f=document.querySelector(\'form.override-form\');if(!f)return;'
    'f.addEventListener("submit",function(){'
    'var b=f.querySelector(\'button[type="submit"]\');'
    'if(b){b.disabled=true;b.setAttribute("aria-disabled","true");'
    'b.textContent="Running… (this can take up to 60s)";}'
    'f.classList.add("running");'
    '});})();'
    '</script>'
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
      'label': str(meta.get('strategy_version', '?')) + ' ' + str(meta.get('run_dt', '')),
      'data': [pt.get('balance_combined', 0.0) for pt in curve],
    })
  payload = _payload({'datasets': datasets,
                      'labels': [pt.get('date', '') for pt in capped[0].get('equity_curve', [])] if capped else []})
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
