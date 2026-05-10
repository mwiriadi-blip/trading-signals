---
phase: 26
plan: 03
type: execute
wave: 1
parallel: true
depends_on: []
files_modified:
  - tests/test_web_dashboard.py
  - tests/test_web_app_factory.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "Failing-by-design xfail tests exist for B1 (per-market eyebrow scoping), B2 (zero placeholder leak), B3 (header session widget), and PATCH-from-panel-swap success"
    - "Tests use existing client_with_dashboard + auth_headers fixtures (tests/test_web_dashboard.py:43-94)"
    - "Tests fail today (xfail strict=True) and flip green only when Plans 04 + 05 land"
  artifacts:
    - path: tests/test_web_dashboard.py
      provides: "TestPhase26PlaceholderLeak (B2/B3) — zero {{[A-Z_]+}} markers in market-scoped GET"
      contains: "class TestPhase26PlaceholderLeak"
    - path: tests/test_web_app_factory.py
      provides: "TestPhase26MarketScoping (B1) — eyebrow text only matches active market"
      contains: "class TestPhase26MarketScoping"
  key_links:
    - from: "tests/test_web_app_factory.py"
      to: "web/app.create_app + dashboard.render_dashboard_page"
      via: "TestClient.get('/markets/{M}/{fn}')"
      pattern: "/markets/.*/(signals|settings|market-test)"
    - from: "tests/test_web_dashboard.py"
      to: "_serve_market_scoped_page"
      via: "regex search for {{[A-Z_]+}}"
      pattern: "\\{\\{[A-Z_]+\\}\\}"
---

<objective>
TDD-style scaffold mirroring Phase 25 Plan 25-01. Add xfail(strict=True) tests for B1, B2, B3, and PATCH-from-swap. They fail today; Plans 04/05 turn them green.

Purpose: Lock the contract before fix lands. Phase 25 verifier flagged D-14 as "no test was written" — don't repeat that.
Output: 2 test classes appended to existing test files. Both red until Plans 04 + 05.
</objective>

<context>
@.planning/phases/26-phase-25-followup-multi-tab-scoping-fixes/26-CONTEXT.md
@.planning/phases/26-phase-25-followup-multi-tab-scoping-fixes/26-PATTERNS.md
@tests/test_web_dashboard.py
@tests/test_web_app_factory.py
@tests/conftest.py

<interfaces>
# Fixtures in scope (do NOT redefine):
#   tests/test_web_dashboard.py:43  VALID_SECRET = 'a' * 32
#   tests/test_web_dashboard.py:44  AUTH_HEADER_NAME = 'X-Trading-Signals-Auth'
#   tests/test_web_dashboard.py:47-55  auth_headers fixture
#   tests/test_web_dashboard.py:58-94  client_with_dashboard fixture
# Existing class to mirror style:
#   tests/test_web_dashboard.py:407-499  TestAuthSecretPlaceholderSubstitution (gold standard)
#   tests/test_web_app_factory.py:388-505 TestPhase25MarketRoutes / TestPhase25SelectedMarketCookie
# State shape for renderer fixture:
#   {markets: {SPI200: {sort_order:10, ...}, AUDUSD: {sort_order:20, ...}, ESM: {sort_order:30, ...}},
#    last_run: '2026-04-23', signals: {...}, equity_history: [], paper_trades: [], closed_trades: [], positions: [],
#    strategy_settings: {SPI200: {}, AUDUSD: {}, ESM: {}}, ...}
# Eyebrow text format from settings.py: f'{display_name.upper()} SETTINGS' (e.g. 'SPI 200 SETTINGS', 'AUD / USD SETTINGS', 'ES MINI SETTINGS')
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Append TestPhase26MarketScoping to tests/test_web_app_factory.py</name>
  <files>tests/test_web_app_factory.py</files>
  <behavior>
    - GET /markets/SPI200/settings: response.text contains 'SPI 200 SETTINGS', does NOT contain 'AUD / USD SETTINGS' or 'ES MINI SETTINGS'.
    - GET /markets/AUDUSD/settings: contains 'AUD / USD SETTINGS', not the others.
    - GET /markets/ESM/market-test: contains 'ES MINI MARKET TEST' (or equivalent eyebrow), not the others.
    - GET /markets/SPI200/signals: signal-card region contains 'SPI 200' eyebrow only (one occurrence in eyebrow position).
    - All tests xfail(strict=True, reason="Phase 26 B1: active_market threading pending — Plan 26-05").
  </behavior>
  <action>
Append a new class `TestPhase26MarketScoping` after the existing TestPhase25 classes. Use the same monkeypatch.chdir + WEB_AUTH_SECRET pattern as TestPhase25MarketRoutes (line 388). Build a 3-market state fixture (SPI200, AUDUSD, ESM with all required keys per 25-01 fixture builder). Synthesize a dashboard.html shell that the routes will read.

Each test:
1. monkeypatch.chdir(tmp_path); set WEB_AUTH_SECRET + WEB_AUTH_USERNAME env.
2. monkeypatch state_manager.load_state to return 3-market state.
3. Write minimal `(tmp_path / 'dashboard.html').write_text('<html>{{WEB_AUTH_SECRET}}</html>')` so the route doesn't 503.
4. `client.get('/markets/{M}/{fn}', headers={AUTH_HEADER_NAME: VALID_SECRET})`.
5. assert status == 200.
6. assert active-market eyebrow string IN response.text.
7. assert other-market eyebrow strings NOT in response.text.

Decorate each method with `@pytest.mark.xfail(strict=True, reason="Phase 26 Plan 26-05 (B1) implementation pending")`.

Inline VALID_SECRET / AUTH_HEADER_NAME as in test_web_app_factory.py per Plan 13-02 convention (with comment pointing to conftest.py single-source). Do NOT `from tests.conftest import …`.
  </action>
  <verify>
    <automated>pytest tests/test_web_app_factory.py::TestPhase26MarketScoping -v 2>&1 | grep -c XFAIL</automated>
  </verify>
  <done>4 xfail-marked tests defined; pytest reports 4 XFAILED (not XPASSED, not FAILED).</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Append TestPhase26PlaceholderLeak + TestPhase26HeaderSessionWidget + TestPhase26PanelPatchSurvives to tests/test_web_dashboard.py</name>
  <files>tests/test_web_dashboard.py</files>
  <behavior>
    - TestPhase26PlaceholderLeak: GET /markets/SPI200/signals, /markets/SPI200/settings, /markets/SPI200/market-test all return resp.text where `re.search(r'\{\{[A-Z_]+\}\}', resp.text)` is None.
    - TestPhase26HeaderSessionWidget: header HTML contains either signout button OR session note, never the literal placeholder strings `{{SIGNOUT_BUTTON}}` or `{{SESSION_NOTE}}`.
    - TestPhase26PanelPatchSurvives: After GET /markets/SPI200/settings, extract WEB_AUTH_SECRET embedded in form, simulate PATCH /strategy with that header value → status != 401-due-to-placeholder. (Acceptable: 200 / 4xx-validation; NOT 401.)
    - All tests xfail(strict=True, reason="Phase 26 B2/B3: substitute helper pending — Plan 26-04").
  </behavior>
  <action>
Append three classes after the existing TestAuthSecretPlaceholderSubstitution class (line 499). Reuse client_with_dashboard + auth_headers fixtures.

Each test:
1. Use client_with_dashboard fixture (handles tmp_path, env, state mock, dashboard.html shell).
2. Override the synthetic dashboard.html shell to include all 5 placeholder kinds: `{{WEB_AUTH_SECRET}}`, `{{SIGNOUT_BUTTON}}`, `{{SESSION_NOTE}}`, `{{TRACE_OPEN_SPI200}}`, `{{TRACE_OPEN_AUDUSD}}`.
3. GET the market-scoped path with auth_headers.
4. Assert response 200.
5. Assert `re.search(r'\{\{[A-Z_]+\}\}', resp.text)` is None (TestPhase26PlaceholderLeak).
6. For TestPhase26HeaderSessionWidget: assert exactly one of (signout-button HTML id/class) OR (session-note HTML class) present; placeholder strings absent.
7. For TestPhase26PanelPatchSurvives: extract `name="X-Trading-Signals-Auth" value="..."` from response if form-embedded, OR confirm cookie path; PATCH /strategy with extracted secret as header; assert resp.status_code != 401.

Mark every method `@pytest.mark.xfail(strict=True, reason="Phase 26 Plan 26-04 (B2/B3): placeholder substitute helper pending")`.
  </action>
  <verify>
    <automated>pytest tests/test_web_dashboard.py -k "Phase26" -v 2>&1 | grep -E "XFAIL|XPASS|FAILED" | grep -v "XFAILED" | wc -l</automated>
  </verify>
  <done>All Phase26 tests in test_web_dashboard.py report XFAILED (count of non-XFAILED lines == 0).</done>
</task>

</tasks>

<verification>
```
pytest tests/test_web_app_factory.py::TestPhase26MarketScoping -v
pytest tests/test_web_dashboard.py -k "Phase26" -v
```
Both invocations: every Phase26 test reports XFAILED. No XPASSED, no FAILED, no ERRORS.

Full suite: `pytest -x` exits 0 (xfail tests don't break suite).
</verification>

<success_criteria>
- TestPhase26MarketScoping has ≥4 xfail tests (one per market × function combo).
- TestPhase26PlaceholderLeak has ≥3 xfail tests (one per page).
- TestPhase26HeaderSessionWidget has ≥2 xfail tests (cookie-session true / false branches).
- TestPhase26PanelPatchSurvives has ≥1 xfail test.
- Total ≥10 new xfail tests; zero false greens.
</success_criteria>

## Rollback

`git revert <plan-03-commit>`. Tests are additive; no other code touched.

## Notes

Pattern map: 26-PATTERNS.md §"Test patterns (cross-cutting)". Mirror Phase 25 Plan 25-01 xfail discipline.

Caveman: tests fail today, plans 04/05 flip green.

<output>
Create `26-03-SUMMARY.md` listing test counts + xfail-status snapshot.
</output>
