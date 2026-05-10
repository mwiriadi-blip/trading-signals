---
phase: 29
plan_id: 29-12-UAT-17-2-IOS-SAFARI-DETAILS-OPEN
plan: 12
type: execute
wave: 3
depends_on: [29-11-UAT-17-1-ATR-SEED-EXPOSURE]
requirements: []
files_modified:
  - web/routes/dashboard.py
  - dashboard_legacy/trace_panels.py
  - dashboard_legacy/render_helpers.py
  - tests/test_trace_details_open_serverside.py
autonomous: true
must_haves:
  truths:
    - "Trace panel renders `<details open>` server-side from `tsi_trace_open` cookie (no client-JS dependency for first paint)."
    - "iOS Safari reload preserves trace panel open state because the `open` attribute is in the initial HTML, not added by JS post-load."
    - "Integration test: setting `tsi_trace_open=SPI200` cookie produces response HTML containing `<details ... open ...>` for SPI200, NOT for AUDUSD."
  artifacts:
    - path: "web/routes/dashboard.py"
      provides: "Cookie-driven `<details open>` substitution path verified end-to-end"
      contains: "tsi_trace_open"
    - path: "dashboard_legacy/trace_panels.py"
      provides: "`<details>` opening tag emits server-side `open` attribute when allowlisted"
      contains: "details"
    - path: "tests/test_trace_details_open_serverside.py"
      provides: "Integration test asserting `<details open>` in response when cookie set"
      contains: "tsi_trace_open"
  key_links:
    - from: "request cookie tsi_trace_open"
      to: "rendered <details ... open ...>"
      via: "_resolve_trace_open_keys allowlist + placeholder substitution"
      pattern: "tsi_trace_open|TRACE_OPEN_"
---

<objective>
Resolve Phase 28 FAIL UAT-17-2 per D-04: server-side render `<details open>` based on `tsi_trace_open` cookie so iOS Safari reload preserves state without depending on client-side JS to re-open the panel after load. Operator re-runs the iPhone Safari scenario manually post-fix; PASS row appended by 29-14.

Purpose: 28-VERIFICATION.md UAT-17-2 evidence: iPhone Safari reload collapses panel; desktop Chrome works. The server-side `<details open>` substitution path EXISTS (`{{TRACE_OPEN_<KEY>}}` placeholder per Phase 17 D-04 + commit history) but operator evidence shows it's not firing on iOS reload — either the placeholder isn't being substituted, or the cookie isn't being read on iOS Safari's reload request, or both.
Output: investigate the existing path, fix the gap, lock with integration test.

depends_on: [29-11] — both plans touch the trace render path; D-04 wave-3 ordering serialises them to avoid merge conflicts.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-CONTEXT.md
@.planning/phases/28-v1-2-uat-closure/28-VERIFICATION.md

<read_first>
- `web/routes/dashboard.py` lines 95-200 (cookie reader + allowlist), 560-600 (`{{TRACE_OPEN_<M>}}` placeholder substitution)
- `dashboard_legacy/trace_panels.py:184-217` (`_render_trace_panels` — emits `{placeholder}` after data-instrument)
- `dashboard_legacy/render_helpers.py:300-330` (`_resolve_trace_open_keys` allowlist filter)
- `dashboard_renderer/assets.py:88` (the JS that WRITES the cookie on toggle — confirm it sets `Secure; SameSite=Lax; Path=/`)
- `28-VERIFICATION.md` UAT-17-2 row (suspected: cookie attribute interaction on iOS Safari OR placeholder not substituting)
- 29-CONTEXT.md §D-04 (server-side render, NOT cookie-attribute tweaks)
- `tests/uat/test_uat_17_cookie_persistence.py` (Phase 28 PASS evidence — desktop Chrome cookie round-trip works)
</read_first>

<interfaces>
Existing path (per `web/routes/dashboard.py` and `dashboard_legacy/trace_panels.py`):
1. Cookie `tsi_trace_open=SPI200,AUDUSD` (comma-separated allowlisted instrument keys).
2. Route handler reads cookie via `request.cookies.get('tsi_trace_open', '')`.
3. `_resolve_trace_open_keys(cookie_value, allowlist)` returns the filtered list.
4. For each instrument with a `{{TRACE_OPEN_<KEY>}}` placeholder in rendered HTML, the route substitutes ` open` if key is in resolved list, else `''`.
5. `<details class="trace-disclosure" data-instrument="SPI200" open>` is the target output.

The "FAIL on iOS Safari, PASS on desktop Chrome" pattern + Phase 28 D-19 evidence ("suspected: cookie-write inline JS at root.html — likely Secure+SameSite=Lax interaction on iOS Safari, OR backend not reading `tsi_trace_open` to seed `<details open>` on render") points at one of:

- (A) Placeholder substitution silently broken on a specific code path.
- (B) iOS Safari NOT sending the cookie back on reload (cookie attribute issue — `Secure` requires HTTPS, but production droplet IS HTTPS; `SameSite=Lax` allows top-level reload).
- (C) Cookie set with wrong `Path` (e.g., `Path=/markets/SPI200` only → not sent on `/markets/AUDUSD`).
- (D) iOS Safari quirk where `document.cookie` writes from inline script fire AFTER the `<details>` element has already been parsed (race), so reload sees the cookie but the `<details>` was rendered closed on the SERVER pass because the cookie wasn't there yet on the previous-page transition.

Investigation should confirm which. Most likely: (D) — first-time toggle writes the cookie, but the same-page reload sends the cookie correctly; if D-04 says "render `<details open>` from cookie" and that's already happening, the failure is on the FIRST toggle-then-reload cycle: the toggle JS writes the cookie, reload sends it, server renders open — should work. If it doesn't, audit the substitution path for a regex bug, missing call site, or the assets.js cookie-write attribute mismatch (e.g., setting `Path=/markets/SPI200` instead of `Path=/`).
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Audit existing cookie-driven `<details open>` server-side path; identify and fix the gap</name>
  <files>web/routes/dashboard.py, dashboard_legacy/trace_panels.py, dashboard_legacy/render_helpers.py, dashboard_renderer/assets.py (only if cookie-write attributes need fixing)</files>
  <read_first>
    - web/routes/dashboard.py:95-200 (cookie reader + allowlist resolver)
    - web/routes/dashboard.py:560-600 (placeholder substitution loop)
    - dashboard_legacy/trace_panels.py:184-217 (`_render_trace_panels` emits placeholder)
    - dashboard_legacy/render_helpers.py:300-330 (`_resolve_trace_open_keys`)
    - dashboard_renderer/assets.py:88 (JS cookie writer — check `Path=`, `SameSite=`, `Secure` attributes)
    - 28-VERIFICATION.md UAT-17-2 evidence cell verbatim
  </read_first>
  <action>
    Per D-04: do NOT change cookie attributes alone (symptom-only). The fix MUST guarantee server-side `<details open>` is the source of truth.

    Investigation steps (executor must complete in order):

    1. **Verify the existing substitution path actually fires.** With a curl probe:
       ```
       curl -sI -b "tsi_trace_open=SPI200" "https://signals.mwiriadi.me/markets/SPI200/dashboard" -H "auth..." | grep -E "details|TRACE_OPEN"
       curl -s  -b "tsi_trace_open=SPI200" "https://signals.mwiriadi.me/markets/SPI200/dashboard" -H "auth..." | grep -oE "<details[^>]+SPI200[^>]*>"
       ```
       Expected: `<details class="trace-disclosure" data-instrument="SPI200" open>`. Actual?

    2. If actual already shows ` open` → the server is correct; the iOS reload bug is at the cookie-write step, not the render step. Pivot to fixing `dashboard_renderer/assets.py:88` cookie attributes:
       - Confirm cookie write sets `Path=/`, `SameSite=Lax`, `Secure`. If `Path` is missing/wrong, fix to `Path=/`.
       - Add `Max-Age=31536000` (1 year) so the cookie survives a Safari "tab discard" → reload cycle.

    3. If actual shows literal `{{TRACE_OPEN_SPI200}}` or no `open` attribute → the substitution path has a bug. Trace through `web/routes/dashboard.py` to find why. Likely candidates:
       - Placeholder regex not matching the emitted form (e.g., trace_panels emits `{TRACE_OPEN_<KEY>}` but route substitutes `{{TRACE_OPEN_<KEY>}}`).
       - Substitution loop only runs on a code path that doesn't include the trace section (e.g., behind a feature flag).
       - `_resolve_trace_open_keys` returning empty list because the allowlist is empty for this market.

    4. **Apply the smallest fix** that makes the substitution work end-to-end.

    5. The fix MUST be locality-correct (D-04): the `<details open>` attribute is server-rendered from cookie, NOT a client-side enhancement.

    Document the actual root cause in commit message. Do NOT speculate — verify each step against the live droplet or a local fixture.

    File-size cap: ≤500 LOC each modified file.
  </action>
  <acceptance_criteria>
    - At least one source file modified with a clear behavioural change (substitution fix OR cookie-attribute fix OR both).
    - `grep -q "tsi_trace_open" web/routes/dashboard.py` still succeeds (the cookie reader stays).
    - Server-side substitution verified by integration test (Task 2). The route handler emits `<details ... open>` when cookie is set.
    - Manual smoke (operator-runnable, NOT in automated acceptance — Plan 29-14 closure does the operator iPhone re-test): `curl -b "tsi_trace_open=SPI200" <route>` returns HTML with `<details class="trace-disclosure" data-instrument="SPI200" open>`.
    - Full default suite green: `.venv/bin/pytest -q` rc=0.
  </acceptance_criteria>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && .venv/bin/pytest -q -k "trace or dashboard"</automated>
  </verify>
  <done>Server-side `<details open>` cookie path audited; gap identified and fixed; commit message documents actual root cause (not speculation).</done>
</task>

<task type="auto">
  <name>Task 2: Integration test — cookie set → response HTML has `<details open>`</name>
  <files>tests/test_trace_details_open_serverside.py</files>
  <read_first>
    - existing integration tests for the dashboard route via `grep -rln "TestClient\\|test_web_dashboard\\|test_dashboard_route" tests/`
    - web/routes/dashboard.py route handler entry point (function name + signature)
    - 29-CONTEXT.md §D-04
  </read_first>
  <action>
    Create `tests/test_trace_details_open_serverside.py` with `TestTraceDetailsOpenServerSide`:

    1. `test_details_open_when_cookie_includes_instrument` — using FastAPI's `TestClient`, set cookie `tsi_trace_open=SPI200,AUDUSD`, GET the route that renders the trace panels for SPI200; assert response.status_code == 200 AND response.text contains a regex match for `<details[^>]+data-instrument="SPI200"[^>]+open\b` (the `open` attribute is present); assert NO literal `{{TRACE_OPEN_SPI200}}` placeholder leaks.
    2. `test_details_closed_when_cookie_excludes_instrument` — set cookie `tsi_trace_open=` (empty); GET same route; assert response contains `<details[^>]+data-instrument="SPI200"[^>]*>` WITHOUT an `open` attribute (regex assertion: matches `<details ...>` but does NOT match `<details ... open>`).
    3. `test_no_cookie_renders_closed` — no cookie; GET; assert details elements render without `open` attribute.
    4. `test_unknown_instrument_in_cookie_ignored` — cookie `tsi_trace_open=EVIL_INJECT`; GET; assert response renders without crashing AND no `<details ... open>` emitted (allowlist filter works).

    Use whatever auth fixture other integration tests use. If no FastAPI TestClient pattern is established, follow `tests/test_web_*.py` patterns.

    File ≤500 LOC. Estimated ~80 LOC.
  </action>
  <acceptance_criteria>
    - `test -f tests/test_trace_details_open_serverside.py` succeeds.
    - `grep -q "test_details_open_when_cookie_includes_instrument" tests/test_trace_details_open_serverside.py` succeeds.
    - `grep -q "test_details_closed_when_cookie_excludes_instrument" tests/test_trace_details_open_serverside.py` succeeds.
    - `grep -q "tsi_trace_open" tests/test_trace_details_open_serverside.py` succeeds.
    - `pytest tests/test_trace_details_open_serverside.py -x -q` rc=0.
    - Full default suite green: `.venv/bin/pytest -q` rc=0.
    - `wc -l tests/test_trace_details_open_serverside.py` ≤500.
  </acceptance_criteria>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && .venv/bin/pytest tests/test_trace_details_open_serverside.py -x -q</automated>
  </verify>
  <done>Integration test locks server-side `<details open>` rendering from cookie. Future regression to JS-only enhancement fails CI.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| `tsi_trace_open` cookie ↔ render | untrusted input must allowlist-filter before reaching render |
| browser JS cookie writer ↔ server cookie reader | attribute mismatch silently breaks reload state |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-29-12-01 | Tampering | Attacker submits `tsi_trace_open=<script>` to attempt XSS via `<details open>` substitution | mitigate | `_resolve_trace_open_keys` allowlist (existing) + html-escape on `data-instrument` value (existing) |
| T-29-12-02 | DoS / UX | Cookie attribute mismatch causes iOS Safari to drop cookie on reload | mitigate | Cookie write sets `Path=/; SameSite=Lax; Secure; Max-Age=31536000`; integration test asserts server reads cookie correctly |
| T-29-12-03 | Tampering (drift) | Future commit reverts to client-side-only `<details open>` enhancement | mitigate | `test_details_open_when_cookie_includes_instrument` integration test asserts server-side rendering |
</threat_model>

<verification>
- `pytest tests/test_trace_details_open_serverside.py -q` rc=0.
- Full suite green.
- Operator manual iPhone re-test: tap toggle → reload → panel still open. (Plan 29-14 captures this.)
</verification>

<success_criteria>
Phase 28 FAIL UAT-17-2 has a server-side rendering fix locked by integration test. Plan 29-14 appends PASS row to 28-VERIFICATION.md citing this plan + operator iPhone re-test.
</success_criteria>

<output>
After completion, create `.planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-12-SUMMARY.md`.
</output>