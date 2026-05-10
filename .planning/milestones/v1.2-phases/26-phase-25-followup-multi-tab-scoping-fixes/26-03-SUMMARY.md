---
phase: 26
plan: 03
type: execute
status: complete
completed: 2026-05-07
files_modified:
  - tests/test_web_dashboard.py
  - tests/test_web_app_factory.py
xfail_count: 10
classes_added: 4
---

# Phase 26 Plan 03 — Failing-test scaffolding (TDD RED gate)

## One-liner

Added 10 xfail(strict=True) tests across 4 classes that lock the post-fix
contract for B1 (per-market eyebrow scoping), B2 (zero placeholder leak),
B3 (header session widget), and PATCH-from-panel-swap survives. Tests fail
today (RED) and flip green when Plans 26-04 and 26-05 land.

## Test counts

| File | Class | Tests | Locks | Flips green when |
|---|---|---|---|---|
| tests/test_web_app_factory.py | TestPhase26MarketScoping | 4 | B1 | Plan 26-05 |
| tests/test_web_dashboard.py | TestPhase26PlaceholderLeak | 3 | B2 | Plan 26-04 |
| tests/test_web_dashboard.py | TestPhase26HeaderSessionWidget | 2 | B3 | Plan 26-04 |
| tests/test_web_dashboard.py | TestPhase26PanelPatchSurvives | 1 | PATCH-from-swap | Plan 26-04 |
| **total** | | **10** | | |

Plan success criteria: ≥10 xfail tests, ≥4 / ≥3 / ≥2 / ≥1 per class. Met.

## xfail snapshot (pre-fix RED state)

```
$ pytest tests/test_web_app_factory.py::TestPhase26MarketScoping -v
tests/test_web_app_factory.py::TestPhase26MarketScoping::test_spi200_settings_eyebrow_only_active_market XFAIL
tests/test_web_app_factory.py::TestPhase26MarketScoping::test_audusd_settings_eyebrow_only_active_market XFAIL
tests/test_web_app_factory.py::TestPhase26MarketScoping::test_esm_market_test_eyebrow_only_active_market XFAIL
tests/test_web_app_factory.py::TestPhase26MarketScoping::test_spi200_signals_card_only_active_market XFAIL
============================== 4 xfailed in 2.18s ==============================

$ pytest tests/test_web_dashboard.py -k "Phase26" -v
tests/test_web_dashboard.py::TestPhase26PlaceholderLeak::test_market_signals_has_no_placeholder_markers XFAIL
tests/test_web_dashboard.py::TestPhase26PlaceholderLeak::test_market_settings_has_no_placeholder_markers XFAIL
tests/test_web_dashboard.py::TestPhase26PlaceholderLeak::test_market_market_test_has_no_placeholder_markers XFAIL
tests/test_web_dashboard.py::TestPhase26HeaderSessionWidget::test_no_cookie_session_renders_session_note XFAIL
tests/test_web_dashboard.py::TestPhase26HeaderSessionWidget::test_with_valid_cookie_session_renders_signout_button XFAIL
tests/test_web_dashboard.py::TestPhase26PanelPatchSurvives::test_patch_with_extracted_secret_does_not_401 XFAIL
====================== 45 deselected, 6 xfailed in 1.23s =======================

$ pytest -x   # full suite
================= 1784 passed, 10 xfailed in 110.13s (0:01:50) =================
```

All Phase26 tests report XFAILED. No XPASSED, no FAILED, no ERROR. Full suite
green (xfail tests don't break the suite). RED gate satisfied.

## What each class locks

### TestPhase26MarketScoping (B1 — Plan 26-05)

Three-market state fixture (SPI200, AUDUSD, ESM) injected via
`monkeypatch.setattr(state_manager, 'load_state', ...)`. Each test:

1. Synthesises a minimal `dashboard.html` shell so the route doesn't 503.
2. Sets `WEB_AUTH_SECRET` + `WEB_AUTH_USERNAME` env.
3. GETs `/markets/{M}/{fn}` with `X-Trading-Signals-Auth: VALID_SECRET`.
4. Asserts active-market eyebrow string IN `resp.text` AND other markets'
   eyebrow strings NOT in `resp.text`.

Eyebrow text format from `dashboard_renderer/components/settings.py:24`:
`f'{display.upper()} SETTINGS'`. Matches plan §interfaces:
- `SPI 200 SETTINGS`
- `AUD / USD SETTINGS`
- `ES MINI SETTINGS`

For market-test, the test allows either `'ES Mini'` or `'ES MINI'` because
Plan 26-05 will pick the exact eyebrow shape; the locked contract is
"active market display name appears, others don't".

### TestPhase26PlaceholderLeak (B2 — Plan 26-04)

Synthetic `dashboard.html` shell injected with all 5 placeholder kinds:
`{{WEB_AUTH_SECRET}}`, `{{SIGNOUT_BUTTON}}`, `{{SESSION_NOTE}}`,
`{{TRACE_OPEN_SPI200}}`, `{{TRACE_OPEN_AUDUSD}}`.

Each test (3 — signals / settings / market-test):

1. GETs `/markets/SPI200/{fn}` with valid auth header.
2. Asserts `re.findall(r'\{\{[A-Z_]+\}\}', resp.text)` is empty.

Mirrors the CONTEXT acceptance #6 grep:
`grep -rn '{{[A-Z_]\+}}' …` returns zero in served HTML.

### TestPhase26HeaderSessionWidget (B3 — Plan 26-04)

Two branches of `_is_cookie_session(request)`:

1. **No cookie** — header request with `X-Trading-Signals-Auth` only.
   Expectation: session-note HTML rendered (`class="session-note"`),
   signout button absent, both placeholder strings absent.
2. **Valid cookie** — request with `tsi_session=<valid_cookie_token>` from
   the conftest fixture.
   Expectation: signout button HTML rendered (`class="btn-signout"`),
   session note absent, both placeholder strings absent.

Asserts at least one of the two widget HTML markers AND that neither
placeholder string leaks.

### TestPhase26PanelPatchSurvives (PATCH-from-swap — Plan 26-04)

End-to-end contract: extract the WEB_AUTH_SECRET from a market-scoped GET
response and replay it on a real PATCH; must not 401-due-to-placeholder.

1. GET `/markets/SPI200/settings` with valid header auth.
2. Regex-extract `X-Trading-Signals-Auth": "<value>"` from the embedded
   `hx-headers='...'` JSON (settings form contains this verbatim per
   `dashboard_renderer/components/settings.py:23`).
3. PATCH `/markets/settings` with the extracted value as the auth header
   and a minimally-valid `MarketSettingsRequest` JSON body.
4. Assert `patch_resp.status_code != 401`.

Today extraction yields the literal `{{WEB_AUTH_SECRET}}` placeholder; auth
middleware rejects with 401; xfail RED. Post-Plan-26-04, extraction yields
the real 32-char secret; PATCH passes auth; xfail flips green.

## Plan literal vs. real endpoint — deviation

Plan 26-03 task 2 behaviour says:

> simulate PATCH /strategy with that header value → status != 401

The actual endpoint that settings forms POST to is `PATCH /markets/settings`
(see `dashboard_renderer/components/settings.py:27` `hx-patch="/markets/settings"`
and `web/routes/markets.py:166` `@app.patch('/markets/settings')`). No
`/strategy` endpoint exists in the repo. Test uses the real endpoint.
Documented here as a Rule 1 (plan-literal bug) deviation; contract being
locked is unchanged: `secret extracted from form must enable PATCH success`.

## Conventions followed

- VALID_SECRET / AUTH_HEADER_NAME mirrored locally per Plan 13-02 convention
  (no `from tests.conftest import …`); comment points to single-source.
- `@pytest.mark.xfail(strict=True, reason="…")` decorator on every test.
- TestClient bound after `sys.modules.pop('web.app', None)` to avoid app
  module cache interference (RESEARCH §Pitfall 4).
- `_phase26_three_market_state*` factory + `_phase26_*_setup` helper at
  module scope to keep test bodies focussed on assertions.
- `_request_with_cookies` reused (already present at line 27) so the
  cookie-session test follows the file's existing cookie-injection idiom.

## Files modified

- `tests/test_web_app_factory.py`: appended `TestPhase26MarketScoping`
  (4 xfail methods) plus `_phase26_three_market_state` and `_phase26_setup`
  module-scope helpers. Net +~150 lines after `TestPhase25AddMarketHXTrigger`.
- `tests/test_web_dashboard.py`: appended `TestPhase26PlaceholderLeak`
  (3 methods), `TestPhase26HeaderSessionWidget` (2 methods),
  `TestPhase26PanelPatchSurvives` (1 method) plus
  `_phase26_three_market_state_dashboard` and `_phase26_dashboard_setup`
  module-scope helpers. Net +~210 lines after `TestPhase25StatusStripEndpoint`.

No production code touched. Pure additive test scaffolding.

## Self-Check: PASSED

- ✅ `tests/test_web_dashboard.py` — present, contains `TestPhase26PlaceholderLeak`,
  `TestPhase26HeaderSessionWidget`, `TestPhase26PanelPatchSurvives`.
- ✅ `tests/test_web_app_factory.py` — present, contains `TestPhase26MarketScoping`.
- ✅ `pytest tests/test_web_app_factory.py::TestPhase26MarketScoping -v` reports
  4 XFAILED, 0 XPASSED, 0 FAILED, 0 ERROR.
- ✅ `pytest tests/test_web_dashboard.py -k "Phase26" -v` reports 6 XFAILED,
  0 XPASSED, 0 FAILED, 0 ERROR.
- ✅ `pytest -x` full suite: 1784 passed, 10 xfailed, exit 0.

## Rollback

`git revert <plan-26-03-commit>`. Tests are additive; no other code touched.
