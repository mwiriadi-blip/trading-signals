---
phase: 26
plan: 04
type: execute
wave: 2
parallel: true
depends_on:
  - 26-03-failing-test-scaffolding-PLAN.md
files_modified:
  - web/routes/dashboard.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "Single _substitute(content: bytes, request: Request) -> bytes helper resolves all 5 placeholder kinds"
    - "_serve_dashboard_content and _serve_market_scoped_page both call _substitute"
    - "Zero `{{[A-Z_]+}}` markers in any served market-scoped HTML"
    - "Header session widget renders signout button OR session note (never placeholder)"
  artifacts:
    - path: web/routes/dashboard.py
      provides: "_substitute helper + B2/B3 fix"
      contains: "_substitute"
  key_links:
    - from: "_serve_market_scoped_page"
      to: "_substitute"
      via: "shared helper call"
      pattern: "_substitute\\(.*request"
    - from: "_serve_dashboard_content"
      to: "_substitute"
      via: "same helper call"
      pattern: "_substitute\\(.*request"
---

<objective>
B2 + B3 together. Extract `_substitute(content: bytes, request: Request) -> bytes` from `_serve_dashboard_content` (web/routes/dashboard.py:500-562). Call from `_serve_market_scoped_page` (235-284). Resolves `{{WEB_AUTH_SECRET}}`, `{{SIGNOUT_BUTTON}}`, `{{SESSION_NOTE}}`, `{{TRACE_OPEN_*}}`. B3 falls out (most-eloquent path per 26-PATTERNS §B3).

Purpose: Locality of substitution rule in one place.
Output: `_substitute` private helper, both serve paths thread through it.
</objective>

<context>
@.planning/phases/26-phase-25-followup-multi-tab-scoping-fixes/26-CONTEXT.md
@.planning/phases/26-phase-25-followup-multi-tab-scoping-fixes/26-PATTERNS.md
@web/routes/dashboard.py

<interfaces>
# Existing canonical substitution block (web/routes/dashboard.py:500-537):
#   {{WEB_AUTH_SECRET}}     → os.environ.get('WEB_AUTH_SECRET','')
#   {{SIGNOUT_BUTTON}}      → dashboard._render_signout_button() if _is_cookie_session(request)
#   {{SESSION_NOTE}}        → dashboard._render_session_note()
#   {{TRACE_OPEN_SPI200}}   → 'open' if 'SPI200' in _resolve_trace_open(request) else ''
#   {{TRACE_OPEN_AUDUSD}}   → 'open' if 'AUDUSD' in _resolve_trace_open(request) else ''
# Also covers any future {{TRACE_OPEN_<MARKET>}} — generalise.
# Hex-boundary: _is_cookie_session lives in web/routes/, NOT renderer. Helper stays in web/routes/dashboard.py.
# Local-import convention: import dashboard inside the helper, not at module top (per tests/test_web_healthz.py::TestWebHexBoundary).
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Extract _substitute helper</name>
  <files>web/routes/dashboard.py</files>
  <behavior>
    - _substitute(content: bytes, request: Request) -> bytes resolves all 5 placeholder kinds.
    - For market-scoped path, all `{{TRACE_OPEN_<MARKET>}}` markers (any market id matching ^[A-Z0-9_]{2,20}$) are resolved by lookup against _resolve_trace_open(request) — generalised over hardcoded SPI200/AUDUSD.
    - When _is_cookie_session(request) returns True: {{SIGNOUT_BUTTON}} → button HTML, {{SESSION_NOTE}} → empty.
    - When False: {{SIGNOUT_BUTTON}} → empty, {{SESSION_NOTE}} → note HTML.
    - Helper itself has no Response coupling — pure bytes→bytes.
  </behavior>
  <action>
1. Read web/routes/dashboard.py lines 500-562 to capture the exact substitution block currently inside `_serve_dashboard_content`.
2. Define new private function `_substitute(content: bytes, request: Request) -> bytes` at module scope (above _serve_dashboard_content). Body = the substitution block, decoded → str.replace chains → encoded.
3. Generalise `{{TRACE_OPEN_*}}` substitution to handle any market id: regex-find all `{{TRACE_OPEN_([A-Z0-9_]{2,20})}}` occurrences and replace each with 'open' or '' based on _resolve_trace_open(request) cookie set.
4. Replace lines 504-537 inside `_serve_dashboard_content` with a single call: `content = _substitute(content, request)`.
5. In `_serve_market_scoped_page` (235-284), after building `body = render_dashboard_as_str(...)` and before `return Response(content=body.encode('utf-8'), …)`, call `body_bytes = _substitute(body.encode('utf-8'), request)`. Use `body_bytes` in the Response.
6. Local imports: `import dashboard` and `from web.middleware.auth import _is_cookie_session` (or wherever it lives) stay LOCAL to the function bodies that need them, per hex-boundary convention.
7. Logging prefix `[Web]` for any new warn/info lines.

Hex-boundary check: helper imports stay inside the function. Renderer (`dashboard_renderer/`) NOT touched. Header.py keeps the `is_cookie_session is None` punt-to-web branch — that's correct; this helper is the web-layer substituter.
  </action>
  <verify>
    <automated>pytest tests/test_web_dashboard.py::TestPhase26PlaceholderLeak tests/test_web_dashboard.py::TestPhase26HeaderSessionWidget tests/test_web_dashboard.py::TestPhase26PanelPatchSurvives tests/test_web_dashboard.py::TestAuthSecretPlaceholderSubstitution -v</automated>
  </verify>
  <done>All Phase 26 test classes named above flip from XFAIL → PASS. TestAuthSecretPlaceholderSubstitution stays green (no regression on the canonical path).</done>
</task>

<task type="auto">
  <name>Task 2: Remove xfail decorators from now-passing Phase 26 tests</name>
  <files>tests/test_web_dashboard.py</files>
  <action>
For every test in TestPhase26PlaceholderLeak, TestPhase26HeaderSessionWidget, TestPhase26PanelPatchSurvives that newly passes, REMOVE the `@pytest.mark.xfail(...)` decorator (xfail strict=True with passing test would XPASS-FAIL otherwise — but we want them green going forward).

Do NOT touch TestPhase26MarketScoping in test_web_app_factory.py — Plan 26-05 owns that.
  </action>
  <verify>
    <automated>pytest tests/test_web_dashboard.py -k "Phase26 and not MarketScoping" -v 2>&1 | grep -cE "PASSED|passed"</automated>
  </verify>
  <done>All 3 Phase 26 classes in test_web_dashboard.py report PASSED (not XFAILED, not XPASSED).</done>
</task>

</tasks>

<verification>
```
grep -rn '{{[A-Z_]\+}}' web/routes/dashboard.py | grep -v '_substitute\|comment\|#'
# expected: only string literals inside _substitute (the regex/replace patterns themselves)

pytest tests/test_web_dashboard.py -k "Phase26 or AuthSecret" -v
# expected: all green

pytest -x  # full suite
```
</verification>

<success_criteria>
- One private function `_substitute` defined in web/routes/dashboard.py.
- Exactly 2 callers (_serve_dashboard_content + _serve_market_scoped_page).
- All Phase 26 tests in test_web_dashboard.py green.
- TestAuthSecretPlaceholderSubstitution remains green.
- No `{{…}}` markers leak in served market-scoped HTML.
</success_criteria>

## Threat Model

| Threat ID | Category | Component | Disposition | Mitigation |
|---|---|---|---|---|
| T-26-04 | Information disclosure | _substitute output reveals WEB_AUTH_SECRET in HTML body | accept | by design — secret is auth header value the SPA needs to authenticate XHRs; existing pattern from TestAuthSecretPlaceholderSubstitution. Mitigation: TLS-only deploy + 32-char min secret (D-17). |
| T-26-05 | Spoofing | Attacker submits crafted Referer to influence trace_open cookie via _substitute | mitigate | _resolve_trace_open already allowlist-validates cookie values (web/routes/dashboard.py:151-163); _substitute consumes the resolved set, not raw cookie. |
| T-26-06 | Tampering | Attacker requests /markets/{evil}/{evil} with `{evil}` containing `{{X}}` to inject placeholders | mitigate | active_market path param is Pydantic ^[A-Z0-9_]{2,20}$ validated upstream; _substitute regex `[A-Z0-9_]{2,20}` accepts only same charset. |

## Rollback

`git revert <plan-04-commit>`. Helper is purely additive at the function-introduction level; the inlined block in `_serve_dashboard_content` becomes a single function call — revert restores the inline block.

## Notes

Pattern map: 26-PATTERNS.md §B2 most-eloquent option (A). 26-PATTERNS.md §B3 shows B3 dissolves into B2.

Hex-boundary: helper stays in web/routes/dashboard.py. Renderer header.py `is_cookie_session is None` punt-pattern preserved.

<output>
Create `26-04-SUMMARY.md` listing the helper signature, call sites, before/after grep counts for `{{[A-Z_]+}}`.
</output>
