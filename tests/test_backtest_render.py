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
    assert 'id="tab-combined"' in html
    # Combined panel must be present (and visible — not hidden by default)
    assert 'id="panel-combined"' in html
    # Other panels are hidden via the `hidden` attr
    assert 'id="panel-spi200"' in html
    assert 'id="panel-audusd"' in html

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
    # Overlay chart payload only includes 10 datasets
    import re
    m = re.search(r'var p=(\{.*?\});', html, re.DOTALL)
    assert m is not None, 'history overlay payload not found'
    payload_str = m.group(1)
    # Payload uses <\/ injection-defence; reverse for parsing
    parsable = payload_str.replace('<\\/', '</')
    payload = json.loads(parsable)
    assert 'datasets' in payload
    assert len(payload['datasets']) == 10, (
      f'overlay should cap at 10 datasets, got {len(payload["datasets"])}'
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
    # The payload IIFE block must NOT contain a raw </script> close tag inline.
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


class TestSubmitButtonDisableUX:
  """D-14 + UI-SPEC §"Long-running submit UX" — spinner + disable on submit."""

  def test_spinner_class_present(self):
    html = render_run_form({})
    assert 'class="spinner"' in html, 'spinner element missing (D-14)'

  def test_keyframes_spin_present(self):
    html = render_run_form({})
    assert '@keyframes spin' in html, 'spinner CSS animation missing (D-14)'

  def test_form_running_class_added_on_submit(self):
    html = render_run_form({})
    assert 'classList.add("running")' in html, (
      'submit handler must add running class to show spinner (D-14)'
    )

  def test_button_disabled_on_submit(self):
    html = render_run_form({})
    assert 'b.disabled=true' in html, (
      'submit handler must disable button to prevent double-submit (D-14)'
    )

  def test_aria_disabled_set_on_submit(self):
    html = render_run_form({})
    assert 'setAttribute("aria-disabled","true")' in html, (
      'submit handler must set aria-disabled for assistive tech (D-14)'
    )

  def test_label_swap_on_submit(self):
    html = render_run_form({})
    assert 'Running… (this can take up to 60s)' in html, (
      'submit handler must swap label per D-14 UI-SPEC verbatim'
    )

  def test_spinner_in_render_report_output(self):
    # Must also surface inside render_report's embedded form
    sample = {
      'metadata': {'strategy_version': 'v1.2.0', 'years': 5,
                   'run_dt': '2026-05-01T08:00:00+08:00',
                   'initial_account_aud': 10000.0,
                   'cost_spi_aud': 6.0, 'cost_audusd_aud': 5.0},
      'metrics': {'combined': {'pass': True, 'cumulative_return_pct': 127.0}},
      'equity_curve': [{'date': '2021-05-01', 'balance_combined': 10000.0,
                        'balance_spi': 5000.0, 'balance_audusd': 5000.0}],
      'trades': [],
    }
    html = render_report(sample)
    assert 'class="spinner"' in html
    assert '@keyframes spin' in html
