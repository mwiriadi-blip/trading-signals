---
phase: 25
plan: 06
type: execute
wave: 3
depends_on: [25-02, 25-04]
files_modified:
  - dashboard_renderer/components/header.py
  - dashboard_renderer/formatters.py
  - web/routes/dashboard.py
autonomous: true
requirements: [P25-03]
must_haves:
  truths:
    - "render_status_strip(state, now_awst) emits id=status-strip element with status-dot, last-run <time>, and next-run countdown placeholder"
    - "Status dot derivation follows OR-01: green (today + no warnings), amber (today + warnings, OR yesterday weekday + today is weekday, OR weekend inheriting Friday), red (last_run None OR > 1 weekday old), grey-dim never-run"
    - "Next-run countdown emits data-countdown attribute with target ISO so the inline AWST JS helper (Plan 02 _AWST_COUNTDOWN_JS) ticks it"
    - "GET /status-strip endpoint returns just the strip fragment HTML, auth-gated"
    - "Display string uses 'AWST' literal everywhere (per D-08 + OR-02); 'AEST' MUST not appear in any new strip output"
    - "Countdown format follows OR-02: `Mon 08:00 AWST · in 2d 16h` for >24h gaps; `in 6h 23m` or `in 14m` for <24h"
  artifacts:
    - path: dashboard_renderer/components/header.py
      provides: "render_status_strip(state, now_awst) -> str; called from render_header()"
      contains: "def render_status_strip"
    - path: dashboard_renderer/formatters.py
      provides: "_compute_next_awst_0800(now_awst) helper + _derive_status_dot_class(state, now_awst) helper per OR-01"
      contains: "_compute_next_awst_0800"
    - path: web/routes/dashboard.py
      provides: "GET /status-strip handler returning render_status_strip fragment"
      contains: "render_status_strip"
  key_links:
    - from: "render_status_strip"
      to: "state['last_run'] + state['warnings']"
      via: "OR-01 derivation rule"
      pattern: "last_run|warnings"
    - from: "/status-strip endpoint"
      to: "header.render_status_strip"
      via: "Response(content=render_status_strip(...))"
      pattern: "render_status_strip"
---

<objective>
Wave 3. Implement the System Status strip per D-06/D-07/D-08 and operator resolutions OR-01/OR-02. Server-renders last-run timestamp + status dot + next-run countdown placeholder; client-side JS (already shipped in Plan 02) ticks the countdown via fixed UTC+8 offset arithmetic. New GET /status-strip endpoint returns the strip fragment for HTMX refresh on 08:01 AWST timer + visibilitychange.

Output: render_status_strip helper, AWST helpers, /status-strip endpoint body, status dot class derivation per OR-01.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-RESEARCH.md
@.planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-UI-SPEC.md
@dashboard_renderer/components/header.py
@dashboard_renderer/formatters.py
@web/routes/dashboard.py

<interfaces>
# state['last_run']: 'YYYY-MM-DD' string OR None (verified RESEARCH §1).
# state['warnings']: list of dicts; each entry has at minimum 'date' (ISO string) and 'message' (str).
# Derivation rule per OR-01:
#   - last_run is None → red (never run)
#   - last_run > 1 weekday ago → red
#   - last_run == today AND warnings empty → green
#   - last_run == today AND warnings non-empty → amber
#   - last_run == yesterday weekday AND today is weekday → amber (one missed cycle)
#   - weekend (Sat/Sun): inherit Friday's status — if last_run is Friday, treat as today
#
# now_awst: datetime localized to Australia/Perth via pytz.timezone (project precedent).
# Use pytz.timezone('Australia/Perth').localize(datetime.utcnow()) — not direct tzinfo kwarg.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add helpers (_compute_next_awst_0800, _derive_status_dot_class) to formatters.py + render_status_strip in header.py</name>
  <read_first>
    - dashboard_renderer/components/header.py (existing render_header signature)
    - dashboard_renderer/formatters.py (existing helpers)
    - dashboard_renderer/api.py (where header is composed; how `now_awst` flows in via _resolve_now)
    - .planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-RESEARCH.md §10 (AWST handling) + §Pattern 3 (status strip)
    - .planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-UI-SPEC.md §System Status strip
  </read_first>
  <files>dashboard_renderer/formatters.py, dashboard_renderer/components/header.py</files>
  <action>
**Step 1 — append helpers to dashboard_renderer/formatters.py:**

```python
import html
from datetime import datetime, timedelta
import pytz


_PERTH = pytz.timezone('Australia/Perth')


def _compute_next_awst_0800(now_awst: datetime) -> datetime:
    """Return the next 08:00 AWST datetime (Mon-Fri only; weekends skip).
    
    OR-02 display rule: if >24h away, format as `Mon 08:00 AWST · in 2d 16h`;
    if <24h, format as `in 6h 23m` or `in 14m`.
    """
    # Strip to AWST date; target 08:00 local same day, or next weekday 08:00 if past
    today = now_awst.replace(hour=8, minute=0, second=0, microsecond=0)
    if now_awst < today and now_awst.weekday() < 5:  # Mon-Fri 0..4; before 08:00 today
        target = today
    else:
        target = today + timedelta(days=1)
    while target.weekday() >= 5:  # Sat=5, Sun=6 — skip
        target += timedelta(days=1)
    return target


def _format_countdown_text(now_awst: datetime, target_awst: datetime) -> str:
    """OR-02 format. >24h: `Mon 08:00 AWST · in 2d 16h`. <24h: `in Nh Mm`. <1h: `in NNm`."""
    delta = target_awst - now_awst
    total_min = max(0, int(delta.total_seconds() // 60))
    days = total_min // (24 * 60)
    hours = (total_min % (24 * 60)) // 60
    mins = total_min % 60
    day_name = target_awst.strftime('%a')  # Mon, Tue, ...
    if delta.total_seconds() >= 24 * 3600:
        return f'{day_name} 08:00 AWST · in {days}d {hours}h'
    if delta.total_seconds() >= 3600:
        return f'in {hours}h {mins}m'
    return f'in {mins}m'


def _derive_status_dot_class(state: dict, now_awst: datetime) -> tuple[str, str]:
    """OR-01 status derivation. Returns (css_class, status_text).
    
    css_class is one of: status-dot--success, status-dot--stale, status-dot--failure, status-dot--never.
    status_text is one of: 'OK', 'Stale', 'Failed', 'Never run'.
    """
    last_run = state.get('last_run')
    warnings = state.get('warnings', []) or []
    today = now_awst.date()
    today_iso = today.isoformat()
    weekday = now_awst.weekday()  # 0=Mon..6=Sun

    if last_run is None:
        return ('status-dot--never', 'Never run')

    # Compare last_run (date string) with today
    try:
        from datetime import date
        last_run_date = date.fromisoformat(last_run)
    except (TypeError, ValueError):
        return ('status-dot--never', 'Never run')

    days_diff = (today - last_run_date).days

    # Recent warnings — entries written on or after last_run_date
    recent_warnings = [w for w in warnings if isinstance(w, dict) and w.get('date', '') >= last_run]

    # Weekend handling: Sat/Sun inherit Friday's status (no run expected on weekends)
    if weekday >= 5:  # Sat, Sun
        # If last_run is Friday of this week, treat as "today"
        days_since_friday = (today - last_run_date).days
        # On Saturday (weekday=5), Friday was yesterday (days_diff=1); on Sunday, Friday was 2 days ago
        expected_days = 1 if weekday == 5 else 2
        if days_diff <= expected_days:
            if recent_warnings:
                return ('status-dot--stale', 'Stale')  # Amber: warnings present
            return ('status-dot--success', 'OK')
        return ('status-dot--failure', 'Failed')  # Red: more than expected

    # Weekday cases
    if last_run == today_iso:
        if recent_warnings:
            return ('status-dot--stale', 'Stale')  # Amber: today's run had warnings
        return ('status-dot--success', 'OK')

    # last_run yesterday, today is weekday → one missed cycle, amber
    if days_diff == 1:
        return ('status-dot--stale', 'Stale')

    # Multiple missed cycles → red
    return ('status-dot--failure', 'Failed')
```

**Step 2 — extend dashboard_renderer/components/header.py:**

```python
# Add to dashboard_renderer/components/header.py:

import html
from datetime import datetime
from dashboard_renderer.formatters import (
    _compute_next_awst_0800,
    _format_countdown_text,
    _derive_status_dot_class,
)


def render_status_strip(state: dict, now_awst: datetime) -> str:
    """Phase 25 D-06/D-07/D-08 + OR-01/OR-02: System Status strip.
    
    Server-renders last-run timestamp + status dot + next-run countdown placeholder.
    Client-side JS (Plan 02 _AWST_COUNTDOWN_JS) ticks the countdown using data-countdown.
    """
    last_run = state.get('last_run')
    dot_class, status_text = _derive_status_dot_class(state, now_awst)
    next_run = _compute_next_awst_0800(now_awst)
    next_run_iso = next_run.isoformat()
    countdown_initial = _format_countdown_text(now_awst, next_run)

    if last_run is None:
        last_run_html = '<span>Awaiting first run</span>'
    else:
        last_run_esc = html.escape(last_run, quote=True)
        last_run_html = f'<time datetime="{last_run_esc}">{last_run_esc}</time> · {status_text}'

    return (
        f'<div id="status-strip" class="status-strip" '
        f'hx-get="/status-strip" '
        f'hx-trigger="visibilitychange[document.visibilityState==\'visible\'] from:document" '
        f'hx-swap="outerHTML" aria-live="polite">\n'
        f'  <span class="status-dot {dot_class}" aria-hidden="true"></span>\n'
        f'  <span class="status-label">Last run</span>\n'
        f'  {last_run_html}\n'
        f'  <span class="status-sep"> · </span>\n'
        f'  <span class="status-label">Next run</span>\n'
        f'  <span data-countdown="{html.escape(next_run_iso, quote=True)}">{html.escape(countdown_initial, quote=True)}</span>\n'
        f'</div>\n'
    )
```

Update `render_header` to include `render_status_strip(state, now)` output as a sibling to the existing H1/subtitle block. Verify `now` is already AWST-localised (it is per `dashboard_renderer/api.py:18 _resolve_now`).
  </action>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && python -c "
from datetime import datetime
import pytz
from dashboard_renderer.components.header import render_status_strip
perth = pytz.timezone('Australia/Perth')
now = perth.localize(datetime(2026, 5, 5, 14, 30))  # weekday, mid-afternoon

# Fresh install
strip = render_status_strip({'last_run': None, 'warnings': []}, now)
assert 'id=\"status-strip\"' in strip
assert 'Awaiting first run' in strip
assert 'AWST' in strip
assert 'AEST' not in strip
assert 'status-dot--never' in strip

# Today's run, no warnings — green
strip2 = render_status_strip({'last_run': '2026-05-05', 'warnings': []}, now)
assert 'status-dot--success' in strip2

# Today's run with recent warning — amber
strip3 = render_status_strip({'last_run': '2026-05-05', 'warnings': [{'date': '2026-05-05', 'message': 'oops'}]}, now)
assert 'status-dot--stale' in strip3

# Old run — red
strip4 = render_status_strip({'last_run': '2026-04-01', 'warnings': []}, now)
assert 'status-dot--failure' in strip4

print('OK')
"</automated>
  </verify>
  <done>
    - render_status_strip helper exists and emits valid HTML
    - Helpers _compute_next_awst_0800, _format_countdown_text, _derive_status_dot_class pass parameterised tests
    - All four status states (success, stale, failure, never) emit distinct CSS classes
    - 'AWST' literal present, 'AEST' literal absent
    - render_header() composition includes the strip
  </done>
</task>

<task type="auto">
  <name>Task 2: Implement GET /status-strip endpoint body + flip xfail decorators</name>
  <read_first>
    - web/routes/dashboard.py — locate the /status-strip stub from Plan 04
    - dashboard_renderer/components/header.py (just-added render_status_strip)
    - dashboard_renderer/api.py:_resolve_now (AWST localisation pattern)
    - tests/test_web_dashboard.py::TestPhase25StatusStripEndpoint
    - tests/test_dashboard.py::TestPhase25Countdown
  </read_first>
  <files>web/routes/dashboard.py, tests/test_web_dashboard.py, tests/test_dashboard.py</files>
  <action>
**Step 1 — replace the /status-strip stub in web/routes/dashboard.py with real handler:**

```python
@router.get('/status-strip', response_class=Response)
async def get_status_strip(request: Request):
    """Phase 25 D-06/D-07: status strip fragment endpoint."""
    state = state_manager.load_state()
    from dashboard_renderer.components.header import render_status_strip
    from datetime import datetime
    import pytz
    perth = pytz.timezone('Australia/Perth')
    now_awst = datetime.now(perth)
    body = render_status_strip(state, now_awst)
    return Response(
        content=body.encode('utf-8'),
        media_type='text/html; charset=utf-8',
        status_code=200,
        headers={'Cache-Control': 'no-store, private'},
    )
```

**Step 2 — wire 08:01 AWST one-shot timer into the inline JS:**

Plan 02 added `_AWST_COUNTDOWN_JS` which ticks countdown displays. Now add a one-shot HTMX trigger at 08:01 AWST. Append to `dashboard_renderer/shell.py`:

```python
_STATUS_STRIP_REFRESH_JS = """
<script>
// Phase 25 D-07: schedule one-shot status-strip refresh at 08:01 AWST.
// 08:01 AWST = 00:01 UTC. Fixed offset, ignores browser local TZ.
(function () {
  function msToNext0801Utc() {
    const now = Date.now();
    const d = new Date(now);
    let target = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate(), 0, 1, 0, 0);
    if (target <= now) target += 86400000;
    return target - now;
  }
  function fireStatusStripRefresh() {
    const el = document.getElementById('status-strip');
    if (el && window.htmx) {
      window.htmx.trigger(el, 'refresh');
    }
    // Re-schedule for next day
    setTimeout(fireStatusStripRefresh, msToNext0801Utc());
  }
  document.addEventListener('DOMContentLoaded', function () {
    setTimeout(fireStatusStripRefresh, msToNext0801Utc());
  });
})();
</script>
"""
```

Update render_html_shell to emit `_STATUS_STRIP_REFRESH_JS` after the other inline scripts. Update the strip's `hx-trigger` to also accept `refresh` (e.g., `hx-trigger="refresh, visibilitychange[document.visibilityState=='visible'] from:document"`).

**Step 3 — flip xfail decorators on tests:**

Remove `@pytest.mark.xfail` from:
- `tests/test_web_dashboard.py::TestPhase25StatusStripEndpoint` (all three methods)
- `tests/test_dashboard.py::TestPhase25Countdown` (all three methods)

Run pytest and confirm they pass.

**Step 4 — surface OR-01 derivation in a regression test:**

Add a parametrised test to `tests/test_dashboard.py` that locks the OR-01 truth table:

```python
class TestPhase25StatusDotDerivation:
    """OR-01: 3-state rule lock."""
    
    @pytest.mark.parametrize('last_run,warnings,now_iso,expected_class', [
        # Fresh install
        (None, [], '2026-05-05T14:30:00+08:00', 'status-dot--never'),
        # Today + clean → green
        ('2026-05-05', [], '2026-05-05T14:30:00+08:00', 'status-dot--success'),
        # Today + warnings → amber
        ('2026-05-05', [{'date': '2026-05-05', 'message': 'x'}], '2026-05-05T14:30:00+08:00', 'status-dot--stale'),
        # Yesterday weekday + today weekday → amber
        ('2026-05-04', [], '2026-05-05T14:30:00+08:00', 'status-dot--stale'),
        # Old → red
        ('2026-04-01', [], '2026-05-05T14:30:00+08:00', 'status-dot--failure'),
        # Weekend Sat: Friday's run is OK → green
        ('2026-05-08', [], '2026-05-09T10:00:00+08:00', 'status-dot--success'),  # 2026-05-09 is a Saturday
        # Weekend Sun: Friday's run is OK → green  
        ('2026-05-08', [], '2026-05-10T10:00:00+08:00', 'status-dot--success'),  # 2026-05-10 is a Sunday
    ])
    def test_or_01_derivation_truth_table(self, last_run, warnings, now_iso, expected_class):
        from datetime import datetime
        import pytz
        from dashboard_renderer.components.header import render_status_strip
        # Parse ISO with offset to get a tz-aware datetime
        now = datetime.fromisoformat(now_iso)
        out = render_status_strip({'last_run': last_run, 'warnings': warnings}, now)
        assert expected_class in out, f'Expected {expected_class} for last_run={last_run}, got: {out[:300]}'
```

This test does NOT use xfail — it must pass green at end of Plan 06.
  </action>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && python -m pytest tests/test_web_dashboard.py::TestPhase25StatusStripEndpoint tests/test_dashboard.py::TestPhase25Countdown tests/test_dashboard.py::TestPhase25StatusDotDerivation -q --no-header 2>&1 | tail -15</automated>
  </verify>
  <done>
    - GET /status-strip returns the rendered strip HTML
    - 08:01 AWST one-shot refresh JS scheduled (re-arms daily)
    - visibilitychange-triggered refresh wired
    - All Phase 25 status-strip xfail tests now PASS
    - OR-01 truth-table regression test passes (no xfail)
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| /status-strip endpoint | Auth-gated; reads state.json; emits HTML fragment. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-25-06-01 | Information Disclosure | render_status_strip | mitigate | state['warnings'] could contain sensitive error text. Strip output renders only the COUNT/state derivation, not warning text — verified by reviewing render_status_strip output template (no `{warning.message}` interpolation). |
| T-25-06-02 | Auth bypass | /status-strip route | mitigate | Route added under existing dashboard router (auth-gated by AuthMiddleware). NOT in PUBLIC_PATHS. Unauth → 401/403 verified by `TestPhase25StatusStripEndpoint::test_status_strip_unauthed_returns_401_or_403`. |
| T-25-06-03 | Cache poisoning | /status-strip response | mitigate | `Cache-Control: no-store, private` header set. |
</threat_model>

<verification>
- All status-strip Phase-25 tests PASS.
- Manual: `curl -i -H "X-Trading-Signals-Auth: $WEB_AUTH_SECRET" http://localhost:PORT/status-strip` returns the strip HTML with `id="status-strip"`.
- AWST/AEST gate: `grep -rn 'AEST' dashboard_renderer/ web/routes/ | grep -v '\\.pyc'` returns 0 lines.
</verification>

<success_criteria>
- render_status_strip implements OR-01 derivation correctly across all 7 truth-table rows.
- Countdown format matches OR-02 (`Mon 08:00 AWST · in 2d 16h` for >24h, `in Nh Mm` for <24h).
- /status-strip endpoint live, auth-gated, no-store cached.
- 08:01 AWST timer + visibilitychange refresh both wired.
- AWST literal everywhere; AEST nowhere.
</success_criteria>

<output>
After completion, create `.planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-06-SUMMARY.md` summarising OR-01 implementation, OR-02 format choices, and any deviations.
</output>
