---
phase: 27
plan: 11
type: execute
wave: 2B
parallel: true
depends_on:
  - 27-03-api-key-redaction-PLAN.md  # <!-- review-fix: agreed-5 — redact_secret applied to traceback -->
  - 27-08-html-escape-audit-PLAN.md  # <!-- review-fix: agreed-5 — _e() escapes banner content -->
files_modified:
  - notifier.py
  - main.py
  - dashboard.py
  - dashboard_renderer/components/health.py
  - system_params.py  # <!-- review-fix: agreed-5 — LAST_CRASH_PATH config constant -->
  - tests/test_crash_email_fallback.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "If notifier.send_email raises, the crash payload is written to LAST_CRASH_PATH (configurable, defaults to <state_dir>/last_crash.json — NOT project root)."
    - "Traceback is passed through redact_secret (Plan 27-03) BEFORE write — secrets never reach disk."
    - "Dashboard's health/settings page renders a banner referencing LAST_CRASH_PATH content if file exists."
    - "Banner content goes through _e() escape (Plan 27-08) — XSS-safe."
    - "Operator sees crash next visit even if email never reached them."
    - "Existing never-crash invariant preserved: writing last_crash.json itself never propagates exception out of daily loop."
  artifacts:
    - path: notifier.py
      provides: "_write_last_crash helper (atomic + redacted + never-raise)"
      contains: "_write_last_crash"
    - path: system_params.py
      provides: "LAST_CRASH_PATH config constant"
      contains: "LAST_CRASH_PATH"
    - path: dashboard_renderer/components/health.py
      provides: "render_last_crash_banner integrated into status strip"
      contains: "last_crash"
    - path: tests/test_crash_email_fallback.py
      provides: "fault-injection regression + redaction test + XSS test"
      contains: "last_crash"
  key_links:
    - from: "notifier crash-email path"
      to: "_write_last_crash (with redacted traceback)"
      via: "fallback on send_email exception"
      pattern: "_write_last_crash"
    - from: "_write_last_crash"
      to: "system_params.redact_secret"
      via: "redact traceback before disk write"
      pattern: "redact_secret"
    - from: "dashboard health/settings page"
      to: "system_params.LAST_CRASH_PATH"
      via: "configurable file read + _e() escape + render"
      pattern: "LAST_CRASH_PATH"
---

## Review fixes applied

- [x] agreed-1 (wave/dependency rebuild) — wave changed `2` → `2B`; depends_on=[27-03, 27-08] explicit per agreed-5.
- [x] agreed-5 (Codex HIGH dependencies on 27-03 + 27-08) — added depends_on=[27-03, 27-08]. Sequencing now Wave 2A (27-03) → 2B (27-11).
- [x] agreed-5 (configurable path, not project root) — added `LAST_CRASH_PATH` config constant in system_params.py. Default: `<state_dir>/last_crash.json` (same dir as state.json — NOT project root, which conflicts with repo file-placement rule).
- [x] agreed-5 (redact traceback before write) — traceback passed through `redact_secret` (from 27-03) before disk write. Unit test asserts a faked traceback containing `re_test_abc123...` is redacted.
- [x] agreed-5 (banner uses _e()) — dashboard banner content escaped via _e() (from 27-08). XSS regression test included.
- [x] M1 (brittle implementation tests) — kept behavioral tests (file exists, redaction applied, banner renders); no source-position checks.
- [x] M2 (doc rule) — SUMMARY artifact stays inside `.planning/phases/27-.../`.

<objective>
Add a second-line crash fallback: when notifier.send_email itself crashes (Resend down, network failure), write the crash payload to LAST_CRASH_PATH (configurable, defaults to state_dir) and surface it on the dashboard's health/settings page.

**Critical constraints (review-fix agreed-5):**
- Path is configurable via `system_params.LAST_CRASH_PATH`, defaults to `<state_dir>/last_crash.json` (NOT project root).
- Traceback is passed through `redact_secret` (Plan 27-03) before disk write — never write raw secrets.
- Dashboard banner content escapes via `_e()` (Plan 27-08) — XSS-safe.

Purpose: silent crash dropout prevention (review item #15). Today, a Resend outage during a daily-run crash means the operator never sees the crash email.
Output: `_write_last_crash` helper (redacted + never-raise) + LAST_CRASH_PATH config + dashboard surfacing + fault-injection regression.
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
@system_params.py

<interfaces>
# Schema for last_crash.json:
#   {
#     "timestamp_utc": "2026-05-07T14:30:00+00:00",
#     "run_date_aws": "2026-05-07",
#     "exception_type": "requests.exceptions.ConnectionError",
#     "exception_message": "...",                       # via redact_secret if it could contain secrets
#     "traceback": "...",                                # str — limited to last 50 lines for size
#                                                          # PASSED THROUGH redact_secret BEFORE WRITE (agreed-5)
#     "send_email_failure": true                         # discriminator
#   }
#
# system_params.py addition (review-fix agreed-5):
#   from pathlib import Path
#   STATE_DIR = Path(os.environ.get('STATE_DIR', '.')).resolve()  # may already exist
#   LAST_CRASH_PATH: Path = STATE_DIR / 'last_crash.json'         # <!-- review-fix: agreed-5 -->
#
# Helper:
#   def _write_last_crash(payload: dict, *, path: Path = None) -> None:
#     '''Atomic write — never raises (per project never-crash invariant).
#     Traceback is redacted via redact_secret BEFORE write (agreed-5).'''
#     from system_params import LAST_CRASH_PATH, redact_secret
#     if path is None: path = LAST_CRASH_PATH
#     try:
#       # Redact every string field that could contain secrets
#       redacted = dict(payload)
#       if 'traceback' in redacted:
#         # redact common secret patterns inside the traceback string
#         redacted['traceback'] = _redact_secrets_in_text(redacted['traceback'])
#       if 'exception_message' in redacted:
#         redacted['exception_message'] = _redact_secrets_in_text(redacted['exception_message'])
#       tmp = path.with_suffix('.json.tmp')
#       tmp.write_text(json.dumps(redacted, indent=2, default=str))
#       os.replace(tmp, path)
#     except Exception as e:
#       logger.error(f'[Crash] last_crash.json write failed: {e}')
#
#   def _redact_secrets_in_text(text: str) -> str:
#     '''Walk known secret patterns; replace with redacted form via redact_secret.'''
#     # Find Resend keys, RESEND_API_KEY env-var values, OAuth tokens, etc.
#     # Defensive: pattern-match `re_[A-Za-z0-9]{20,}` and similar.
#     import re as _re
#     for pat in [r're_[A-Za-z0-9]{20,}', r'sk_[A-Za-z0-9]{20,}', r'Bearer\s+[A-Za-z0-9._\-]+']:
#       text = _re.sub(pat, lambda m: redact_secret(m.group(0)), text)
#     return text
#
# Call site: notifier.send_email outermost except clause writes the crash payload.
#
# Dashboard integration: dashboard_renderer/components/health.py extends render_status_strip
# (Phase 25 D-15) to include a "last crash" sub-block when LAST_CRASH_PATH file exists.
# Every interpolation goes through _e() (Plan 27-08).
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: LAST_CRASH_PATH config + _write_last_crash helper (redacted, never-raise)</name>
  <!-- review-fix: agreed-5 -->
  <read_first>
    - notifier.py — send_email body + outermost exception handlers
    - main.py — crash-email caller
    - system_params.py — STATE_DIR if it exists; redact_secret (from 27-03)
  </read_first>
  <behavior>
    - test_last_crash_path_default_in_state_dir: system_params.LAST_CRASH_PATH points to STATE_DIR / 'last_crash.json' — NOT to project root.  <!-- review-fix: agreed-5 -->
    - test_write_last_crash_creates_file: call _write_last_crash with payload; file exists with valid JSON content.
    - test_write_last_crash_never_raises: monkeypatch Path.write_text to raise OSError; call _write_last_crash; no exception propagates.
    - test_write_last_crash_redacts_traceback: payload['traceback'] contains 're_test_abc123def456ghi789'; after _write_last_crash, the on-disk JSON has 're_tes...' or '[REDACTED]' — NOT the full token.  <!-- review-fix: agreed-5 -->
    - test_write_last_crash_redacts_exception_message: payload['exception_message'] contains 'Bearer eyJabc123...'; on-disk shows redacted form.
    - test_send_email_failure_writes_last_crash: monkeypatch requests.post to ConnectionError; invoke send_email; LAST_CRASH_PATH exists with `send_email_failure: true`.
    - test_send_email_failure_continues_daily_run: same scenario; daily run main() return code well-defined (never-crash).
  </behavior>
  <action>
1. **system_params.py:** add `LAST_CRASH_PATH` per <interfaces>. Locate or define STATE_DIR (likely already present). Default path = STATE_DIR / 'last_crash.json'. Inline comment: `# Phase 27 #15 (review-fix agreed-5): configurable, NOT project root`.

2. **notifier.py:** define `_write_last_crash` per <interfaces>. Use pathlib.Path + atomic write. Import `traceback`, `pathlib.Path`, `redact_secret`, `LAST_CRASH_PATH` from system_params.

3. **notifier.py:** define `_redact_secrets_in_text(text)` helper per <interfaces>. Pattern-match common secret formats; replace via redact_secret.

4. **Wire into send_email failure path** (the requests.post except block):
   ```python
   except Exception as e:
     payload = {
       'timestamp_utc': datetime.now(timezone.utc).isoformat(),
       'run_date_aws': run_date_aws,
       'exception_type': type(e).__name__,
       'exception_message': str(e),
       'traceback': '\n'.join(traceback.format_exc().splitlines()[-50:]),
       'send_email_failure': True,
     }
     _write_last_crash(payload)   # redacts internally before write
     # then existing failure path (logger.error etc.)
   ```

5. **tests/test_crash_email_fallback.py (NEW):** 7 tests per behavior block. Use tmp_path fixture for path isolation. Test redaction explicitly:
   ```python
   def test_write_last_crash_redacts_traceback(monkeypatch, tmp_path):
     crash_path = tmp_path / 'last_crash.json'
     monkeypatch.setattr('system_params.LAST_CRASH_PATH', crash_path)
     payload = {
       'timestamp_utc': '2026-05-07T00:00:00+00:00',
       'run_date_aws': '2026-05-07',
       'exception_type': 'HTTPError',
       'exception_message': '401 Unauthorized: re_test_abc123def456ghi789',
       'traceback': 'Traceback ...\nresend.send(api_key="re_test_abc123def456ghi789")',
       'send_email_failure': True,
     }
     notifier._write_last_crash(payload)
     on_disk = json.loads(crash_path.read_text())
     assert 're_test_abc123def456ghi789' not in on_disk['traceback']
     assert 're_test_abc123def456ghi789' not in on_disk['exception_message']
   ```
  </action>
  <verify>
    <automated>pytest tests/test_crash_email_fallback.py -x -v -k "Task1 or write_last_crash or last_crash_path or send_email_failure"</automated>
  </verify>
  <done>
    - LAST_CRASH_PATH in system_params.py (default = STATE_DIR / 'last_crash.json').
    - _write_last_crash + _redact_secrets_in_text in notifier.py.
    - send_email failure path writes redacted last_crash.json.
    - 7 tests green.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Dashboard surfacing of last_crash (configurable path + _e escaping)</name>
  <!-- review-fix: agreed-5 -->
  <read_first>
    - dashboard.py — settings/health page renderer
    - dashboard_renderer/components/ — list components for placement
    - .planning/phases/25-* status-strip plan for OR-01 status-dot derivation pattern
  </read_first>
  <behavior>
    - test_dashboard_renders_banner_when_last_crash_exists: create LAST_CRASH_PATH file in test cwd; render dashboard; HTML contains '.last-crash-banner' marker AND exception_message + timestamp.
    - test_dashboard_no_banner_when_last_crash_absent: no file; no .last-crash-banner element.
    - test_dashboard_uses_configurable_path: monkeypatch system_params.LAST_CRASH_PATH to a custom location; renderer reads from THAT path (proves it's not hardcoded).  <!-- review-fix: agreed-5 -->
    - test_dashboard_banner_xss_safe: exception_message containing `<script>alert(1)</script>` lands escaped in banner (cross-tested with Plan 27-08 _e).
  </behavior>
  <action>
1. **Placement decision:** extend `render_status_strip` (Phase 25 D-15) in `dashboard_renderer/components/health.py` to include a "last crash" sub-block when LAST_CRASH_PATH exists. Locality: status strip already owns "system trust surface".
   > **Most eloquent:** extend health component — locality preserved, single component owns crash visibility + status. Alternative (separate component) would split the trust-surface concern across two components.

2. **Read configurable path** (review-fix agreed-5):
   ```python
   from system_params import LAST_CRASH_PATH
   import json
   def render_last_crash_banner() -> str:
     try:
       data = json.loads(LAST_CRASH_PATH.read_text())
     except (FileNotFoundError, json.JSONDecodeError):
       return ''
     return (
       f'<div class="last-crash-banner">'
       f'<strong>Last crash:</strong> {_e(data["timestamp_utc"])} — '
       f'{_e(data["exception_type"])}: {_e(data["exception_message"])}'
       f'</div>'
     )
   ```
   Wrap every interpolation in `_e()` from Plan 27-08.

3. **tests/test_crash_email_fallback.py (extend):** 4 dashboard tests per behavior block.
  </action>
  <verify>
    <automated>pytest tests/test_crash_email_fallback.py -x -v</automated>
  </verify>
  <done>
    - Banner rendered when file exists; absent when absent.
    - Configurable path verified via monkeypatch.
    - 4 dashboard tests green; XSS escape verified.
    - Total 11 tests in test_crash_email_fallback.py green.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Resend / network → daily run | Outage must not silently disappear |
| last_crash.json (disk) → dashboard HTML | Crash payload may contain exception text from any source — must escape |
| Traceback content → disk | Traceback may contain api_key/token strings — must redact |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation |
|-----------|----------|-----------|-------------|------------|
| T-27-11-01 | DoS / silent failure | Resend outage during a crash → operator never sees crash | mitigate | last_crash.json fallback + dashboard banner. Operator sees on next visit. |
| T-27-11-02 | Tampering (XSS) | exception_message contains attacker-controlled HTML | mitigate | _e() escape on render (Plan 27-08). |
| T-27-11-03 | Information disclosure | last_crash.json on disk contains api_key in traceback | mitigate | Pre-write redact via redact_secret + pattern-walk on traceback. Test asserts. |
| T-27-11-04 | Tampering | Hardcoded path conflicts with repo file-placement rule and varies between local/droplet | mitigate | LAST_CRASH_PATH configurable in system_params; defaults to STATE_DIR (same as state.json). |
</threat_model>

<verification>
```
pytest tests/test_crash_email_fallback.py -x -v
grep -n '_write_last_crash\|LAST_CRASH_PATH\|last_crash' notifier.py dashboard.py dashboard_renderer/components/*.py system_params.py
pytest -x   # full suite
```
</verification>

<success_criteria>
- LAST_CRASH_PATH configurable (defaults to STATE_DIR, NOT project root).
- _write_last_crash atomic + never-raise + redacts traceback BEFORE write.
- send_email failure path uses it.
- Dashboard renders banner when file exists; reads from configurable path; escapes via _e().
- 11 tests green (7 helper/redaction + 4 rendering/configurability/XSS).
- Existing never-crash invariant preserved.
</success_criteria>

<output>
Create `27-11-SUMMARY.md` with: helper signature, schema of last_crash.json, configurable-path rationale, redaction pattern list, dashboard integration site, redact_secret integration confirmation, fault-injection test result.
</output>
