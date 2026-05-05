---
phase: 25
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - tests/test_dashboard.py
  - tests/test_web_app_factory.py
  - tests/test_web_dashboard.py
autonomous: true
requirements: [P25-01, P25-02, P25-03, P25-04, P25-05, P25-06, P25-07, P25-08, P25-09, P25-10, P25-11, P25-12, P25-13, P25-14, P25-15]
must_haves:
  truths:
    - "Failing test scaffolds exist for every Phase-25 acceptance criterion that can be unit-/integration-tested"
    - "Existing route-shadowing regression test (tests/test_web_app_factory.py:344) remains intact"
    - "Tests fail with NotImplementedError-style markers (xfail or skip) rather than producing false greens"
  artifacts:
    - path: tests/test_dashboard.py
      provides: "Phase-25 unit test classes (TestPhase25FirstRun, TestPhase25StatsBar, TestPhase25Equity, TestPhase25Settings, TestPhase25Fonts, TestPhase25AddMarket, TestPhase25ActiveTab, TestPhase25NoInlineColor, TestPhase25WideTable, TestPhase25ButtonRename, TestPhase25StrategyVersion)"
      contains: "class TestPhase25FirstRun"
    - path: tests/test_web_app_factory.py
      provides: "Phase-25 routing/cookie classes (TestPhase25MarketRoutes, TestPhase25SelectedMarketCookie, TestPhase25StatusStrip)"
      contains: "class TestPhase25MarketRoutes"
    - path: tests/test_web_dashboard.py
      provides: "Phase-25 status-strip endpoint integration class (TestPhase25StatusStripEndpoint)"
      contains: "class TestPhase25StatusStripEndpoint"
  key_links:
    - from: "tests/test_dashboard.py"
      to: "dashboard_renderer + dashboard.py"
      via: "render_dashboard / render_dashboard_page calls"
      pattern: "render_dashboard\\("
    - from: "tests/test_web_app_factory.py"
      to: "web/app.create_app"
      via: "create_app(...) + TestClient"
      pattern: "create_app\\("
---

<objective>
Wave 1 test scaffolding for Phase 25. Create failing-by-design test classes for every acceptance gate listed in 25-RESEARCH.md §Validation Architecture so subsequent implementation plans (Waves 2–4) execute against a real RED→GREEN cycle.

Purpose: Prevents implementation-without-verification. Every D-XX decision below has a corresponding test that flips green only when the implementation lands.
Output: 3 test files extended with 14 new test classes; all marked xfail or skip until implementation lands.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-CONTEXT.md
@.planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-RESEARCH.md
@.planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-UI-SPEC.md
@tests/conftest.py
@tests/test_dashboard.py
@tests/test_web_app_factory.py
@tests/test_web_dashboard.py

<interfaces>
# From tests/conftest.py (autouse fixture WEB_AUTH_SECRET, VALID_SECRET = 'a'*32, AUTH_HEADER_NAME = 'X-Trading-Signals-Auth')
# From dashboard_renderer/api.py:
#   def render_dashboard(state: dict, now: datetime | None = None, ...) -> str
# From state schema: state['last_run'] is YYYY-MM-DD string OR None (NOT last_run_at)
# state['warnings'] is list of dicts with 'date' and 'message'
# state['markets'] is dict {market_id: {sort_order, contract_size, ...}}
# state['signals'][market_id]['strategy_version'] is the rendered version source
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add Phase-25 unit test classes to tests/test_dashboard.py</name>
  <read_first>
    - tests/test_dashboard.py (existing TestTabbedDashboard class at line 3100 for fixture pattern)
    - tests/conftest.py (autouse VALID_SECRET fixture)
    - .planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-RESEARCH.md §Validation Architecture (P25-04..P25-14 rows)
    - .planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-UI-SPEC.md §Copywriting Contract
  </read_first>
  <files>tests/test_dashboard.py</files>
  <action>
Append 11 new test classes to tests/test_dashboard.py. Every test method MUST be decorated with `@pytest.mark.xfail(strict=True, reason="Phase 25 implementation pending: see <plan-NN>")` so they fail when run today and turn green only after implementation. Strict=True means an unexpected pass also fails — locking the contract.

Imports to add at top of file (only if missing):
```python
import pytest
from dashboard_renderer.api import render_dashboard
```

Helper fixture (add once, at top of new section):
```python
def _empty_state(last_run=None, markets=None, warnings=None, equity_history=None, signals=None, paper_trades=None):
    """Phase 25 fixture builder. Returns a minimal valid state dict."""
    return {
        'last_run': last_run,
        'markets': markets or {'SPI200': {'sort_order': 10, 'contract_size': 5}, 'AUDUSD': {'sort_order': 20, 'contract_size': 100000}},
        'warnings': warnings or [],
        'equity_history': equity_history or [],
        'signals': signals or {},
        'paper_trades': paper_trades or [],
        'positions': [],
        'closed_trades': [],
        'strategy_settings': {'SPI200': {}, 'AUDUSD': {}},
        'account_balance_paper': 100000.0,
        'account_balance_live': 100000.0,
    }
```

Test classes to add (each method xfail-decorated):

```python
class TestPhase25FirstRun:
    """D-09: state['last_run'] is None hides 11 trace tables, shows 1 onboarding card."""

    @pytest.mark.xfail(strict=True, reason="Phase 25 P25-07: first-run collapse implementation pending")
    def test_last_run_none_renders_zero_trace_tables(self):
        html_out = render_dashboard(_empty_state(last_run=None))
        assert 'class="trace-indicators-table"' not in html_out

    @pytest.mark.xfail(strict=True, reason="Phase 25 P25-07: first-run collapse implementation pending")
    def test_last_run_none_renders_onboarding_card(self):
        html_out = render_dashboard(_empty_state(last_run=None))
        assert 'Awaiting first daily run' in html_out
        assert 'Calculations and equity curve will populate after the first cycle at 08:00 AWST.' in html_out

    @pytest.mark.xfail(strict=True, reason="Phase 25 P25-07: first-run collapse implementation pending")
    def test_last_run_set_renders_trace_tables(self):
        state = _empty_state(last_run='2026-04-23', signals={'SPI200': {'strategy_version': 'v1.2.0', 'signal': 0}})
        html_out = render_dashboard(state)
        assert 'class="trace-indicators-table"' in html_out


class TestPhase25StatsBar:
    """D-10: stats bar hidden until closed_paper + closed_live >= 1."""

    @pytest.mark.xfail(strict=True, reason="Phase 25 P25-07: stats-bar gate pending")
    def test_zero_trades_omits_stats_bar(self):
        html_out = render_dashboard(_empty_state(last_run='2026-04-23'))
        assert 'class="stats-bar"' not in html_out

    @pytest.mark.xfail(strict=True, reason="Phase 25 P25-07: stats-bar gate pending")
    def test_one_closed_paper_trade_renders_stats_bar(self):
        state = _empty_state(last_run='2026-04-23', paper_trades=[{'status': 'closed', 'realised_pnl': 100.0}])
        html_out = render_dashboard(state)
        assert 'class="stats-bar"' in html_out


class TestPhase25Equity:
    """D-11: equity chart hidden until ≥5 distinct (date, value) tuples."""

    @pytest.mark.xfail(strict=True, reason="Phase 25 P25-07: equity-chart gate pending")
    def test_three_identical_points_hides_chart(self):
        eq = [{'date': '2026-04-23', 'equity': 100000.0}] * 3
        html_out = render_dashboard(_empty_state(last_run='2026-04-23', equity_history=eq))
        assert 'id="equityChart"' not in html_out
        assert 'Chart appears once 5 daily equity points have been recorded.' in html_out

    @pytest.mark.xfail(strict=True, reason="Phase 25 P25-07: equity-chart gate pending")
    def test_five_distinct_points_renders_chart(self):
        eq = [{'date': f'2026-04-{20+i}', 'equity': 100000.0 + i} for i in range(5)]
        html_out = render_dashboard(_empty_state(last_run='2026-04-23', equity_history=eq))
        assert 'id="equityChart"' in html_out


class TestPhase25Settings:
    """D-12: 3 fieldsets — Entry rules / Risk / Direction."""

    @pytest.mark.xfail(strict=True, reason="Phase 25 P25-08: settings fieldset grouping pending")
    def test_settings_renders_three_fieldsets(self):
        html_out = render_dashboard(_empty_state(last_run='2026-04-23'))
        assert html_out.count('<fieldset') >= 3

    @pytest.mark.xfail(strict=True, reason="Phase 25 P25-08: settings fieldset grouping pending")
    def test_settings_legends_match_spec(self):
        html_out = render_dashboard(_empty_state(last_run='2026-04-23'))
        assert '<legend>Entry rules</legend>' in html_out
        assert '<legend>Risk</legend>' in html_out
        assert '<legend>Direction</legend>' in html_out


class TestPhase25Fonts:
    """D-15: --fs-body 14px → 16px; other tokens scale by 16/14."""

    @pytest.mark.xfail(strict=True, reason="Phase 25 P25-09: font scale rebalance pending")
    def test_fs_body_is_16px(self):
        html_out = render_dashboard(_empty_state())
        assert '--fs-body: 16px' in html_out

    @pytest.mark.xfail(strict=True, reason="Phase 25 P25-09: font scale rebalance pending")
    def test_fs_label_is_14px(self):
        html_out = render_dashboard(_empty_state())
        # 12 * (16/14) = 13.71 → 14
        assert '--fs-label: 14px' in html_out

    @pytest.mark.xfail(strict=True, reason="Phase 25 P25-09: font scale rebalance pending")
    def test_fs_heading_is_23px(self):
        html_out = render_dashboard(_empty_state())
        # 20 * (16/14) = 22.86 → 23
        assert '--fs-heading: 23px' in html_out

    @pytest.mark.xfail(strict=True, reason="Phase 25 P25-09: font scale rebalance pending")
    def test_fs_display_is_32px(self):
        html_out = render_dashboard(_empty_state())
        # 28 * (16/14) = 32 exactly
        assert '--fs-display: 32px' in html_out


class TestPhase25AddMarket:
    """D-16/D-17: + Add market chip beside market tabs."""

    @pytest.mark.xfail(strict=True, reason="Phase 25 P25-04: add-market chip pending")
    def test_market_strip_contains_add_market_chip(self):
        html_out = render_dashboard(_empty_state(last_run='2026-04-23'))
        assert 'class="add-market-chip"' in html_out
        assert '+ Add market' in html_out

    @pytest.mark.xfail(strict=True, reason="Phase 25 P25-04: add-market chip pending")
    def test_add_market_chip_form_posts_to_markets(self):
        html_out = render_dashboard(_empty_state(last_run='2026-04-23'))
        assert 'hx-post="/markets"' in html_out

    @pytest.mark.xfail(strict=True, reason="Phase 25 P25-04: add-market chip pending")
    def test_buried_settings_link_removed(self):
        html_out = render_dashboard(_empty_state(last_run='2026-04-23'))
        assert 'href="#settings-tab"' not in html_out


class TestPhase25ActiveTab:
    """D-18: active tab gets aria-current=page + distinct CSS rule."""

    @pytest.mark.xfail(strict=True, reason="Phase 25 P25-03: two-axis nav pending")
    def test_active_function_tab_has_aria_current(self):
        # When rendering /signals page, the Signals function tab must have aria-current="page"
        html_out = render_dashboard(_empty_state(last_run='2026-04-23'))
        # Match: a tag containing both 'Signals' and aria-current="page"
        import re
        assert re.search(r'<a[^>]*aria-current="page"[^>]*>\s*Signals\s*</a>', html_out) is not None

    @pytest.mark.xfail(strict=True, reason="Phase 25 P25-03: two-axis nav pending")
    def test_function_tab_strip_has_aria_label(self):
        html_out = render_dashboard(_empty_state(last_run='2026-04-23'))
        assert 'aria-label="Function"' in html_out

    @pytest.mark.xfail(strict=True, reason="Phase 25 P25-03: two-axis nav pending")
    def test_market_tab_strip_has_aria_label(self):
        html_out = render_dashboard(_empty_state(last_run='2026-04-23'))
        assert 'aria-label="Market"' in html_out


class TestPhase25NoInlineColor:
    """D-19 #5: no inline style="color:..." anywhere."""

    @pytest.mark.xfail(strict=True, reason="Phase 25 P25-09: a11y inline-style cleanup pending")
    def test_rendered_html_has_no_inline_color_styles(self):
        html_out = render_dashboard(_empty_state(last_run='2026-04-23', signals={'SPI200': {'strategy_version': 'v1.2.0', 'signal': 1}}))
        assert 'style="color:' not in html_out

    @pytest.mark.xfail(strict=True, reason="Phase 25 P25-09: status-dot beside FLAT/LONG/SHORT pending")
    def test_signal_label_has_status_dot(self):
        state = _empty_state(last_run='2026-04-23', signals={'SPI200': {'strategy_version': 'v1.2.0', 'signal': 0}})
        html_out = render_dashboard(state)
        # Status dot glyph beside FLAT label per D-19 #3
        assert 'class="status-dot status-dot--flat"' in html_out or 'class="status-dot status-dot--neutral"' in html_out


class TestPhase25WideTable:
    """D-20: wide tables wrapped in scrollable region."""

    @pytest.mark.xfail(strict=True, reason="Phase 25 P25-09: wide-table wrapper pending")
    def test_open_positions_table_is_wrapped(self):
        html_out = render_dashboard(_empty_state(last_run='2026-04-23'))
        # The positions section should contain a div with table-scroll class
        assert 'class="table-scroll"' in html_out

    @pytest.mark.xfail(strict=True, reason="Phase 25 P25-09: wide-table wrapper pending")
    def test_table_scroll_has_role_region(self):
        html_out = render_dashboard(_empty_state(last_run='2026-04-23'))
        assert 'role="region"' in html_out


class TestPhase25ButtonRename:
    """D-21: paper Open position → Record paper trade; live Open Position → Open live position."""

    @pytest.mark.xfail(strict=True, reason="Phase 25 P25-10: button rename pending")
    def test_paper_trade_button_renamed(self):
        html_out = render_dashboard(_empty_state(last_run='2026-04-23'))
        assert 'Record paper trade' in html_out
        # Old text should be gone — but check carefully because "Open position" might appear elsewhere
        # The submit button specifically: scan for `<button type="submit"` containing "Open position" in paper section
        # Easier check: count occurrences. After rename, "Open Position" (case-sensitive) should not appear.
        assert 'Open Position</button>' not in html_out

    @pytest.mark.xfail(strict=True, reason="Phase 25 P25-10: button rename pending")
    def test_live_trade_button_renamed(self):
        html_out = render_dashboard(_empty_state(last_run='2026-04-23'))
        assert 'Open live position' in html_out

    @pytest.mark.xfail(strict=True, reason="Phase 25 P25-10: terminology reconciliation pending")
    def test_account_terminology_unified(self):
        html_out = render_dashboard(_empty_state(last_run='2026-04-23'))
        # "Account Management" tab label is replaced by "Account" (per UI-SPEC §Tab strips)
        # And section heading is "Account" (per UI-SPEC §Account page)
        # "Account Baseline" form heading should be gone
        assert 'Account Baseline' not in html_out
        assert 'Account Management' not in html_out


class TestPhase25StrategyVersion:
    """D-22: strategy version sourced from state.signals[*].strategy_version."""

    @pytest.mark.xfail(strict=True, reason="Phase 25 P25-10: footer regen pending")
    def test_footer_renders_v120_when_state_has_v120(self):
        state = _empty_state(
            last_run='2026-04-23',
            signals={'SPI200': {'strategy_version': 'v1.2.0', 'signal': 0}, 'AUDUSD': {'strategy_version': 'v1.2.0', 'signal': 0}},
        )
        html_out = render_dashboard(state)
        assert 'v1.2.0' in html_out
        assert 'v1.0.0' not in html_out
        assert 'v1.1.0' not in html_out


class TestPhase25Countdown:
    """D-06/D-07/OR-01/OR-02: System Status strip server-render."""

    @pytest.mark.xfail(strict=True, reason="Phase 25 P25-05: status strip pending")
    def test_status_strip_present_in_header(self):
        html_out = render_dashboard(_empty_state(last_run='2026-04-23'))
        assert 'id="status-strip"' in html_out

    @pytest.mark.xfail(strict=True, reason="Phase 25 P25-05: status strip pending")
    def test_status_strip_first_run_shows_awaiting(self):
        html_out = render_dashboard(_empty_state(last_run=None))
        assert 'Awaiting first run' in html_out

    @pytest.mark.xfail(strict=True, reason="Phase 25 P25-05: status strip pending")
    def test_status_strip_displays_awst_label(self):
        html_out = render_dashboard(_empty_state(last_run='2026-04-23'))
        # Operator-locked: display literal must read AWST (not AEST)
        assert 'AWST' in html_out
        assert 'AEST' not in html_out
```

After appending: do NOT modify existing tests. Run pytest with -m "not slow" to confirm new xfail tests register and "fail as expected".
  </action>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && python -m pytest tests/test_dashboard.py -k "TestPhase25" --no-header -rxX 2>&1 | tail -40</automated>
  </verify>
  <done>
    - All 11 new test classes appear in tests/test_dashboard.py
    - All test methods carry `@pytest.mark.xfail(strict=True, ...)` decorator
    - `pytest tests/test_dashboard.py -k TestPhase25 -rxX` reports XFAIL count == number of tests added (no XPASS, no FAIL)
    - Existing tests in test_dashboard.py still pass (no regressions): `pytest tests/test_dashboard.py -k "not TestPhase25" -q` exits 0
  </done>
</task>

<task type="auto">
  <name>Task 2: Add Phase-25 routing/cookie/status-strip endpoint test classes</name>
  <read_first>
    - tests/test_web_app_factory.py (focus on lines 246-379 — TestMarketRoutesRegistered class + the route-shadowing regression test at line 344)
    - tests/test_web_dashboard.py (existing TestClient + auth header pattern)
    - tests/conftest.py (VALID_SECRET, AUTH_HEADER_NAME, autouse WEB_AUTH_SECRET fixture)
    - .planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-RESEARCH.md §4 (route ordering) + §5 (cookie pattern) + §Validation Architecture
  </read_first>
  <files>tests/test_web_app_factory.py, tests/test_web_dashboard.py</files>
  <action>
Append two test classes to tests/test_web_app_factory.py and one to tests/test_web_dashboard.py. Use the same xfail-strict pattern as Task 1.

In tests/test_web_app_factory.py (extend module imports if needed: `import pytest`, `from fastapi.testclient import TestClient`, `from web.app import create_app`):

```python
class TestPhase25MarketRoutes:
    """D-01..D-05: GET /markets/{market_id}/{function} routes registered correctly."""

    @pytest.mark.xfail(strict=True, reason="Phase 25 P25-02: routes pending")
    def test_market_signals_route_registered(self):
        app = create_app()
        paths = {r.path for r in app.routes}
        assert '/markets/{market_id}/signals' in paths

    @pytest.mark.xfail(strict=True, reason="Phase 25 P25-02: routes pending")
    def test_market_settings_route_registered(self):
        app = create_app()
        paths = {r.path for r in app.routes}
        assert '/markets/{market_id}/settings' in paths

    @pytest.mark.xfail(strict=True, reason="Phase 25 P25-02: routes pending")
    def test_market_market_test_route_registered(self):
        app = create_app()
        paths = {r.path for r in app.routes}
        assert '/markets/{market_id}/market-test' in paths

    @pytest.mark.xfail(strict=True, reason="Phase 25 P25-02: routes pending")
    def test_get_market_signals_returns_200_with_auth(self):
        client = TestClient(create_app())
        resp = client.get(
            '/markets/SPI200/signals',
            headers={'X-Trading-Signals-Auth': 'a' * 32},
        )
        assert resp.status_code == 200

    @pytest.mark.xfail(strict=True, reason="Phase 25 P25-02: route validation pending")
    def test_unknown_market_returns_404(self):
        client = TestClient(create_app())
        resp = client.get(
            '/markets/NOPE/signals',
            headers={'X-Trading-Signals-Auth': 'a' * 32},
        )
        assert resp.status_code == 404

    def test_existing_route_shadowing_regression_still_passes(self):
        """REGRESSION GUARD — must remain green throughout Phase 25.
        Mirrors test_patch_market_settings_literal_path_updates_settings at line 344
        but as a placeholder that asserts the literal /markets/settings path is registered
        BEFORE /markets/{market_id} in the route list (registration-order check).
        """
        app = create_app()
        ordered_patch_paths = [r.path for r in app.routes if 'PATCH' in getattr(r, 'methods', set())]
        if '/markets/settings' in ordered_patch_paths and '/markets/{market_id}' in ordered_patch_paths:
            assert ordered_patch_paths.index('/markets/settings') < ordered_patch_paths.index('/markets/{market_id}'), \
                'Route shadowing regression — /markets/settings literal must come before /markets/{market_id}'


class TestPhase25SelectedMarketCookie:
    """D-05: GET /markets/{m}/{fn} sets cookie selected_market with HttpOnly=false; SameSite=Lax."""

    @pytest.mark.xfail(strict=True, reason="Phase 25 P25-02: cookie write pending")
    def test_market_route_sets_selected_market_cookie(self):
        client = TestClient(create_app())
        resp = client.get(
            '/markets/AUDUSD/signals',
            headers={'X-Trading-Signals-Auth': 'a' * 32},
        )
        # Look for Set-Cookie header containing selected_market=AUDUSD
        set_cookies = [v for k, v in resp.headers.items() if k.lower() == 'set-cookie']
        # At minimum one Set-Cookie must contain selected_market=AUDUSD
        assert any('selected_market=AUDUSD' in sc for sc in set_cookies)

    @pytest.mark.xfail(strict=True, reason="Phase 25 P25-02: cookie attrs pending")
    def test_selected_market_cookie_has_lax_samesite_no_httponly(self):
        client = TestClient(create_app())
        resp = client.get(
            '/markets/SPI200/signals',
            headers={'X-Trading-Signals-Auth': 'a' * 32},
        )
        set_cookies = [v for k, v in resp.headers.items() if k.lower() == 'set-cookie']
        market_cookie = next((sc for sc in set_cookies if 'selected_market=' in sc), None)
        assert market_cookie is not None
        assert 'SameSite=Lax' in market_cookie
        # D-05: NOT HttpOnly — JS must be able to read the cookie
        assert 'HttpOnly' not in market_cookie
        assert 'Path=/' in market_cookie
        assert 'Secure' in market_cookie  # production HTTPS-only requirement
```

In tests/test_web_dashboard.py append:

```python
class TestPhase25StatusStripEndpoint:
    """D-06/D-07: GET /status-strip returns fragment HTML."""

    @pytest.mark.xfail(strict=True, reason="Phase 25 P25-05: /status-strip endpoint pending")
    def test_status_strip_endpoint_returns_200(self):
        from fastapi.testclient import TestClient
        from web.app import create_app
        client = TestClient(create_app())
        resp = client.get('/status-strip', headers={'X-Trading-Signals-Auth': 'a' * 32})
        assert resp.status_code == 200

    @pytest.mark.xfail(strict=True, reason="Phase 25 P25-05: /status-strip endpoint pending")
    def test_status_strip_endpoint_returns_html_fragment(self):
        from fastapi.testclient import TestClient
        from web.app import create_app
        client = TestClient(create_app())
        resp = client.get('/status-strip', headers={'X-Trading-Signals-Auth': 'a' * 32})
        assert 'text/html' in resp.headers.get('content-type', '')
        body = resp.text
        # Fragment should contain the strip wrapper, NOT a full <html> document
        assert 'id="status-strip"' in body
        assert '<html' not in body.lower()

    @pytest.mark.xfail(strict=True, reason="Phase 25 P25-05: /status-strip endpoint pending")
    def test_status_strip_unauthed_returns_401_or_403(self):
        from fastapi.testclient import TestClient
        from web.app import create_app
        client = TestClient(create_app())
        resp = client.get('/status-strip')
        assert resp.status_code in (401, 403)
```
  </action>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && python -m pytest tests/test_web_app_factory.py::TestPhase25MarketRoutes tests/test_web_app_factory.py::TestPhase25SelectedMarketCookie tests/test_web_dashboard.py::TestPhase25StatusStripEndpoint -rxX --no-header 2>&1 | tail -30</automated>
  </verify>
  <done>
    - 3 new test classes appended (TestPhase25MarketRoutes, TestPhase25SelectedMarketCookie, TestPhase25StatusStripEndpoint)
    - The 1 non-xfail regression-guard test (`test_existing_route_shadowing_regression_still_passes`) PASSES today
    - All other Phase-25 tests report XFAIL
    - `pytest tests/test_web_app_factory.py tests/test_web_dashboard.py -k "not TestPhase25" -q` still exits 0 (no regressions)
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Test code → CI runner | Test files are source code; no untrusted input. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-25-01-01 | (n/a) | test files | accept | Pure test scaffolding — introduces no new attack surface; no production code paths exercised. xfail-strict prevents accidental greens. |
</threat_model>

<verification>
- All Phase-25 test classes added with @pytest.mark.xfail(strict=True, ...)
- `pytest tests/test_dashboard.py tests/test_web_app_factory.py tests/test_web_dashboard.py -k "Phase25" -rxX` shows XFAIL counts ≥ all asserted gates; zero XPASS, zero FAIL.
- Existing 1319+ test suite remains green: `pytest -q` exits 0.
- Route-shadowing regression test (test_patch_market_settings_literal_path_updates_settings) intact.
</verification>

<success_criteria>
- 14 new test classes total: 11 in test_dashboard.py, 2 in test_web_app_factory.py, 1 in test_web_dashboard.py.
- Every Phase-25 acceptance gate from RESEARCH §Validation Architecture (P25-01..P25-15) has at least one test method.
- Wave 0 gap closure: Subsequent implementation plans flip xfail → pass without modifying these test files except to remove xfail decorators.
</success_criteria>

<output>
After completion, create `.planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-01-SUMMARY.md` summarising new test classes, count of xfail tests added, and any deviations.
</output>
