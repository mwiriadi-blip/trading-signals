---
phase: 27
plan: 11
type: execute
wave: 2
parallel: true
depends_on: []
files_modified:
  - notifier.py
  - main.py
  - dashboard.py
  - dashboard_renderer/components/health.py (NEW or extend existing)
  - tests/test_crash_email_fallback.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "If notifier.send_email raises (Resend down, network error), the crash payload is written to last_crash.json in the project root with timestamp + traceback + run-date."
    - "The dashboard's settings/health page renders a banner referencing last_crash.json content if the file exists."
    - "Operator sees the crash next visit even if email never reached them."
    - "Existing never-crash invariant preserved: writing last_crash.json itself never propagates an exception out of the daily loop."
  artifacts:
    - path: notifier.py (or new module)
      provides: "_write_last_crash helper"
      contains: "last_crash.json"
    - path: dashboard.py
      provides: "render_last_crash_banner integration in health/settings page"
      contains: "last_crash"
    - path: tests/test_crash_email_fallback.py
      provides: "fault-injection regression"
      contains: "last_crash.json"
  key_links:
    - from: "notifier crash-email path"
      to: "_write_last_crash"
      via: "fallback on send_email exception"
      pattern: "_write_last_crash"
    - from: "dashboard health/settings page"
      to: "last_crash.json"
      via: "file read + render"
      pattern: "last_crash"
---

<objective>
Add a second-line crash fallback: when notifier.send_email itself crashes (Resend down, network failure), write the crash payload to `last_crash.json` and surface it on the dashboard's settings/health page.

Purpose: silent crash dropout prevention (review item #15). Today, a Resend outage during a daily-run crash means the operator never sees the crash email — the entire failure mode is invisible.
Output: `_write_last_crash` helper + dashboard surfacing + fault-injection regression.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@notifier.py
@main.py
@dashboard.py

<interfaces>
# Schema for last_crash.json:
#   {
#     "timestamp_utc": "2026-05-07T14:30:00+00:00",
#     "run_date_aws": "2026-05-07",
#     "exception_type": "requests.exceptions.ConnectionError",
#     "exception_message": "...",
#     "traceback": "...",         # str — limited to last 50 lines for size
#     "send_email_failure": true   # discriminator: True if notifier.send_email crashed (Phase 27 fallback path);
#                                  # False if a daily-run-loop crash that send_email handled normally (legacy).
#   }
#
# Helper:
#   def _write_last_crash(payload: dict, *, path: Path = Path('last_crash.json')) -> None:
#     '''Atomic write — never raises (per project never-crash invariant).'''
#     try:
#       tmp = path.with_suffix('.json.tmp')
#       tmp.write_text(json.dumps(payload, indent=2, default=str))
#       os.replace(tmp, path)
#     except Exception as e:
#       logger.error(f'[Crash] last_crash.json write failed: {e}')  # silent-degrade
#
# Call site: in notifier.send_email's outermost except clause:
#   try:
#     resp = requests.post(...)
#     resp.raise_for_status()
#   except Exception as e:
#     payload = {
#       'timestamp_utc': datetime.now(timezone.utc).isoformat(),
#       'run_date_aws': run_date_aws,  # from caller
#       'exception_type': type(e).__name__,
#       'exception_message': str(e),
#       'traceback': '\n'.join(traceback.format_exc().splitlines()[-50:]),
#       'send_email_failure': True,
#     }
#     _write_last_crash(payload)
#     # then proceed with existing failure path (logger.error etc.)
#
# Dashboard integration: in the settings or health page renderer, check if last_crash.json exists.
# If yes, render a red banner with timestamp + exception_message. Add a "Dismiss" button (POST /clear-last-crash)
# that deletes the file, but keep dismiss out of scope for this plan if it adds complexity — minimum
# is "render the banner if file exists".
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: _write_last_crash helper + notifier wiring</name>
  <read_first>
    - notifier.py — send_email body + outermost exception handlers
    - main.py — crash-email caller (per STATE.md, _run_daily_check_caught wraps run_daily_check; that's where the CALLER-side crash flow lives, but THIS plan is about send_email ITSELF crashing during the crash-email-DISPATCH)
  </read_first>
  <behavior>
    - test_write_last_crash_creates_file: call _write_last_crash with a payload; assert last_crash.json exists with valid JSON content.
    - test_write_last_crash_never_raises: monkeypatch Path.write_text to raise OSError; call _write_last_crash; no exception propagates.
    - test_send_email_failure_writes_last_crash: monkeypatch requests.post to raise ConnectionError; invoke send_email (or whichever wrapper handles dispatch); assert last_crash.json exists with `send_email_failure: true`.
    - test_send_email_failure_continues_daily_run: same scenario; the daily run main() return code is still well-defined (not aborted). (Verifies never-crash invariant.)
  </behavior>
  <action>
1. **notifier.py:** define `_write_last_crash` per <interfaces>. Use `pathlib.Path` + atomic write pattern (already used elsewhere in state_manager). Import `traceback`, `pathlib.Path`.

2. Wire it into the send_email failure path. The existing pattern (per STATE.md Plan 03 reference) has _dispatch_email_and_maintain_warnings as the orchestrator. Find the equivalent point in send_email (or in the requests.post except block at line 1367) and add the fallback write.

3. **tests/test_crash_email_fallback.py (NEW):** 4 tests per behavior block. Use tmp_path fixture for isolation:
   ```python
   def test_send_email_failure_writes_last_crash(monkeypatch, tmp_path):
     crash_path = tmp_path / 'last_crash.json'
     monkeypatch.setattr('notifier._LAST_CRASH_PATH', crash_path)  # parameterise the path
     monkeypatch.setattr('notifier.requests.post', lambda *a, **kw: (_ for _ in ()).throw(requests.exceptions.ConnectionError('boom')))
     notifier.send_email(subject='test', html='<p>x</p>', api_key='k', run_date_aws='2026-05-07')
     assert crash_path.exists()
     payload = json.loads(crash_path.read_text())
     assert payload['send_email_failure'] is True
   ```
  </action>
  <verify>
    <automated>pytest tests/test_crash_email_fallback.py -x -v</automated>
  </verify>
  <done>
    - _write_last_crash exported from notifier (or wherever placed).
    - send_email failure path writes last_crash.json.
    - 4 tests green.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Dashboard surfacing of last_crash.json</name>
  <read_first>
    - dashboard.py — settings/health page renderer
    - dashboard_renderer/components/ — list existing components for placement decision
    - .planning/phases/25-* status-strip plan for OR-01 status-dot derivation pattern
  </read_first>
  <behavior>
    - test_dashboard_renders_banner_when_last_crash_exists: create last_crash.json in test cwd; render dashboard; assert HTML contains 'last_crash' marker (e.g. CSS class .last-crash-banner) AND the exception_message + timestamp are visible.
    - test_dashboard_no_banner_when_last_crash_absent: no file; render dashboard; assert no .last-crash-banner element.
    - XSS regression: exception_message containing `<script>alert(1)</script>` lands escaped in the banner (cross-tested with Plan 27-08 escape policy).
  </behavior>
  <action>
1. Place the banner integration in the most natural location — likely the System Status strip from Phase 25 D-15 (`render_status_strip` already lives in `dashboard_renderer/components/`). Most eloquent:
   > **Most eloquent:** extend status_strip to include a "last crash" sub-block when last_crash.json exists. Locality: status strip already owns "system trust surface" per Phase 25; adding crash visibility there keeps one component responsible for one concern.

2. Read last_crash.json at render time (file-read in the component, not pre-resolved by the orchestrator — keeps the component self-contained). Wrap in try/except FileNotFoundError → return empty banner.

3. Escape every interpolation per Plan 27-08 (`_e(...)` alias).

4. **tests/test_crash_email_fallback.py extension:** add 3 dashboard-rendering tests per behavior block.
  </action>
  <verify>
    <automated>pytest tests/test_crash_email_fallback.py -x -v</automated>
  </verify>
  <done>
    - Banner rendered when file exists; absent when file absent.
    - 3 dashboard tests green.
    - XSS escape verified.
    - Total 7 tests in test_crash_email_fallback.py green.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Resend / network → daily run | Outage must not silently disappear |
| last_crash.json (disk) → dashboard HTML | Crash payload may contain exception text from any source — must escape |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation |
|-----------|----------|-----------|-------------|------------|
| T-27-11-01 | DoS / silent failure | Resend outage during a crash → operator never sees the crash | mitigate | last_crash.json fallback + dashboard banner. Operator sees on next dashboard visit. |
| T-27-11-02 | Tampering (XSS) | Crash payload exception_message contains attacker-controlled HTML (e.g. yfinance returned an HTML error page) | mitigate | _e() escape on render (Plan 27-08 alias). |
| T-27-11-03 | Information disclosure | last_crash.json on disk could contain sensitive info (api_key in traceback) | mitigate | Pre-write redact via redact_secret on traceback string (uses Plan 27-03 helper). Add to payload pipeline. |
</threat_model>

<verification>
```
pytest tests/test_crash_email_fallback.py -x -v
grep -n '_write_last_crash\|last_crash.json' notifier.py dashboard.py dashboard_renderer/components/*.py
pytest -x   # full suite
```
</verification>

<success_criteria>
- _write_last_crash helper writes atomically + never raises.
- send_email failure path uses it.
- Dashboard renders banner when file exists.
- 7 tests green (4 helper + 3 rendering).
- Existing never-crash invariant preserved.
</success_criteria>

<output>
Create `27-11-SUMMARY.md` with: helper signature, schema of last_crash.json, dashboard integration site, redact_secret integration confirmation, fault-injection test result.
</output>
