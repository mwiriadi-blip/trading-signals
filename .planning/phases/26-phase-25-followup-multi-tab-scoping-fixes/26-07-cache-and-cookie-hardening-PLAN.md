---
phase: 26
plan: 07
type: execute
wave: 3
parallel: true
depends_on:
  - 26-04-template-substitute-helper-PLAN.md
  - 26-05-active-market-scoping-PLAN.md
files_modified:
  - web/routes/dashboard.py
  - web/routes/markets.py
  - dashboard_renderer/components/nav.py
  - dashboard_renderer/components/signals.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "_is_stale_for(page_output) parameterised — each sibling checks its own marker"
    - "add_market writes the same dict shape as run_daily_check (no int sentinel)"
    - "markets-strip reads active_function from query param, not Referer"
    - "selected_market cookie read path enforces ^[A-Z0-9_]{2,20}$ regex"
  artifacts:
    - path: web/routes/dashboard.py
      provides: "_is_stale_for + cookie regex tighten + active_function from query"
      contains: "_is_stale_for"
    - path: web/routes/markets.py
      provides: "add_market writes dict-shape signal"
      contains: "'signal_as_of'"
    - path: dashboard_renderer/components/signals.py
      provides: "Defensive int-branch removed (now unreachable after R5)"
  key_links:
    - from: "_is_stale_for"
      to: "each sibling HTML"
      via: "marker check per file"
      pattern: "_is_stale_for\\("
    - from: "markets-strip"
      to: "request.query_params['active_function']"
      via: "hx-get URL param"
      pattern: "active_function="
---

<objective>
R1 + R5 + R6 + R7 grouped — four small hardenings touching the same 4 files.

Purpose: Eliminate fragile coupling (R1 single-marker check, R5 dict-shape divergence, R6 Referer dependency, R7 permissive cookie sanitiser).
Output: Each fragility either fixed or pinned with regex.
</objective>

<context>
@.planning/phases/26-phase-25-followup-multi-tab-scoping-fixes/26-CONTEXT.md
@.planning/phases/26-phase-25-followup-multi-tab-scoping-fixes/26-PATTERNS.md
@web/routes/dashboard.py
@web/routes/markets.py
@dashboard_renderer/components/nav.py
@dashboard_renderer/components/signals.py
@main.py

<interfaces>
# R1 — _is_stale (web/routes/dashboard.py:74,119) currently single-file marker check.
# R5 canonical signal write shape (main.py:1489-1499):
#   {'signal':int, 'signal_as_of':iso_or_None, 'as_of_run':iso_or_None,
#    'last_scalars':{}, 'last_close':float|None, 'strategy_version':STRATEGY_VERSION, 'ohlc_window':[]}
# R6 nav.py:104-105 emits the markets-strip element — add active_function as query param.
# R7 cookie sanitiser current (web/routes/dashboard.py:228-233): strips " and ; only.
#    Pydantic write-side regex (web/routes/markets.py:20): ^[A-Z0-9_]{2,20}$
# Allowlist for active_function: {signals, account, settings, market-test}.
# Renderer defensive int branch: dashboard_renderer/components/signals.py:35-39 (handles signals[id] == int 0).
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: R1 — Per-file _is_stale_for</name>
  <files>web/routes/dashboard.py</files>
  <behavior>
    - _is_stale_for(page_output: Path) -> bool checks marker against each sibling file path.
    - Existing _is_stale callers updated to pass the dashboard.html or sibling Path explicitly.
    - Behaviour unchanged for dashboard.html; siblings now also gated.
  </behavior>
  <action>
1. Refactor `_is_stale` (lines 74,119) into `_is_stale_for(page_output: Path) -> bool` — same body, accept the path.
2. Each sibling-serve path that reads a sibling HTML calls `_is_stale_for(sibling_path)` before deciding to regen.
3. Reuse `_REQUIRED_DASHBOARD_MARKER` — check marker presence in each sibling. If marker absent → stale → regen.
4. Use `_atomic_write_html` from dashboard_renderer/api.py (per 26-PATTERNS §"Atomic file write") for any new writes — do NOT raw `path.write_text`.
  </action>
  <verify>
    <automated>pytest tests/test_web_dashboard.py -k "stale or marker" -v</automated>
  </verify>
  <done>Existing stale tests green; new behaviour: removing marker from any sibling triggers regen.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: R5 — add_market writes dict-shape signal</name>
  <files>web/routes/markets.py, dashboard_renderer/components/signals.py</files>
  <behavior>
    - add_market sets state['signals'][market_id] = full dict matching run_daily_check shape with sentinel-zero values.
    - Renderer's defensive int branch (signals.py:35-39) deleted — now unreachable.
    - Existing markets continue to render correctly.
  </behavior>
  <action>
1. web/routes/markets.py:158 — replace `state.setdefault('signals', {})[req.market_id] = 0` with:
```python
import system_params  # local import per hex-boundary convention
state.setdefault('signals', {})[req.market_id] = {
    'signal': 0,
    'signal_as_of': None,
    'as_of_run': None,
    'last_scalars': {},
    'last_close': None,
    'strategy_version': system_params.STRATEGY_VERSION,
    'ohlc_window': [],
}
```
2. dashboard_renderer/components/signals.py:35-39 — delete the `isinstance(signal_record, int)` defensive branch. Keep only the dict-shape branch.
3. Audit grep: `grep -rn "signals\[.*\] = 0\b" --include='*.py' .` — should return zero non-test matches.
4. Update any test that asserted int-sentinel — point to dict shape.
  </action>
  <verify>
    <automated>pytest tests/test_markets.py tests/test_dashboard.py -x</automated>
  </verify>
  <done>Suite green. Adding a fresh market then rendering produces "Signal as of: never" via the new dict path, not the int branch.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: R6 — markets-strip reads active_function from query param</name>
  <files>dashboard_renderer/components/nav.py, web/routes/dashboard.py</files>
  <behavior>
    - nav.py emits `hx-get="/markets-strip?active_function={active_function}"` (URL-encoded).
    - markets-strip route reads `request.query_params.get('active_function', 'signals')` and validates against allowlist {signals, account, settings, market-test}.
    - Referer-based fallback removed.
  </behavior>
  <action>
1. dashboard_renderer/components/nav.py — locate the `hx-get="/markets-strip"` emission (around line 104-105 per 26-PATTERNS §R6). Append `?active_function={active_function}` (URL-encoded; active_function is already a-z hyphens, safe).
2. web/routes/dashboard.py — markets-strip handler (around line 341-346): replace Referer-derived `active_function` lookup with:
```python
ALLOWED_FUNCTIONS = {'signals', 'account', 'settings', 'market-test'}
active_function = request.query_params.get('active_function', 'signals')
if active_function not in ALLOWED_FUNCTIONS:
    active_function = 'signals'
```
3. Mirror the allowlist-validation pattern from `_resolve_trace_open` (web/routes/dashboard.py:151-163).
  </action>
  <verify>
    <automated>pytest tests/test_web_dashboard.py -k "strip or markets_strip" -v</automated>
  </verify>
  <done>markets-strip route works without Referer; allowlist rejects unknown values.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 4: R7 — Cookie regex tighten on read + write</name>
  <files>web/routes/dashboard.py</files>
  <behavior>
    - _set_market_cookie rejects market_id failing ^[A-Z0-9_]{2,20}$ (write-path defence-in-depth).
    - Read-path (line ~336) drops cookie value if it fails the same regex; falls back to first-market.
  </behavior>
  <action>
1. Add module-scope: `import re; _MARKET_ID_RE = re.compile(r'^[A-Z0-9_]{2,20}$')`.
2. Replace `_set_market_cookie` (lines 228-233) body with regex fullmatch check before setting header.
3. At the cookie-read site (line ~336): wrap `request.cookies.get('selected_market', '')` with regex check; if match fails, treat as empty.
4. Pattern mirrors `_resolve_trace_open` (lines 151-163) allowlist-validation discipline.
  </action>
  <verify>
    <automated>pytest tests/test_web_app_factory.py -k "Cookie or SelectedMarket" -v</automated>
  </verify>
  <done>Existing cookie tests green; new test (add to TestPhase25SelectedMarketCookie or new class): malformed cookie value (`a`, `123`, `abc;evil`, whitespace) is rejected.</done>
</task>

</tasks>

<verification>
```
pytest tests/test_web_dashboard.py tests/test_web_app_factory.py tests/test_markets.py tests/test_dashboard.py -x
grep -rn "signals\[.*\] = 0\b" --include='*.py' . | grep -v 'test_\|^Binary'
# expected: zero matches
grep -n "active_function" web/routes/dashboard.py dashboard_renderer/components/nav.py | grep -v Referer
# expected: query_params.get pattern
```
</verification>

<success_criteria>
- 4 hardenings landed.
- No int sentinel in state['signals'] writes.
- No Referer dependency for markets-strip.
- Cookie regex enforced both write + read.
- Full pytest green.
</success_criteria>

## Threat Model

| Threat ID | Category | Component | Disposition | Mitigation |
|---|---|---|---|---|
| T-26-09 | Tampering | Forged selected_market cookie injects arbitrary string into state lookup | mitigate | regex fullmatch on read path drops malformed values; Pydantic upstream validates write path. |
| T-26-10 | Spoofing | Forged Referer manipulates active_function tab highlight | mitigate (closed) | R6 removes Referer dependency; allowlist enforced. |
| T-26-11 | DoS | Crafted long cookie value triggers regex catastrophic backtracking | accept | regex `^[A-Z0-9_]{2,20}$` is bounded-length and not subject to ReDoS. |

## Rollback

`git revert <plan-07-commit>`. Each sub-task is independently revertable; no migrations.

## Notes

Pattern map: 26-PATTERNS.md §R1, §R5, §R6, §R7. `_atomic_write_html` reuse for sibling writes (§"Atomic file write").

<output>
Create `26-07-SUMMARY.md` listing each sub-task verdict + regex/grep evidence.
</output>
