---
phase: 27
plan: 03
type: execute
wave: 1A
parallel: true
depends_on: []
files_modified:
  - system_params.py
  - notifier.py
  - auth_store.py
  - data_fetcher.py
  - tests/test_secret_redaction.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "redact_secret(s: str) -> str returns prefix[:6] + '...' for any non-empty input."
    - "All log lines and exception messages that include API keys, TOTP secrets, session secrets, or auth-store secrets pass through redact_secret() before emission."
    - "Grep gate: zero log/raise/print sites in notifier.py, auth_store.py, data_fetcher.py emit a full secret variable un-redacted."
  artifacts:
    - path: system_params.py
      provides: "redact_secret helper"
      contains: "def redact_secret"
    - path: tests/test_secret_redaction.py
      provides: "redact_secret unit tests + log-content regression tests"
      contains: "redact_secret"
  key_links:
    - from: "notifier.requests.post error handler"
      to: "system_params.redact_secret"
      via: "redact before re-raise"
      pattern: "redact_secret\\("
---

## Review fixes applied

- [x] No changes — both reviewers marked this plan clean. Wave label updated to `1A` per Codex sequencing matrix (agreed-1) for consistency; otherwise unchanged.
- [x] agreed-1 (wave/dependency rebuild) — wave changed `1` → `1A`; depends_on remains empty.

<objective>
Centralise secret redaction. Add `redact_secret(s: str) -> str` to system_params.py. Audit notifier.py (already has explicit "Fix 1 (T-06-02): redact api_key from any echo" pattern at line 1379), auth_store.py (TOTP secret persistence), data_fetcher.py (no API key today but future-proof), and any exception handlers that interpolate an api_key / secret variable into the message.

Purpose: credential leakage prevention (review item #13).
Output: redact_secret helper + audited call sites + regression test.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@system_params.py
@notifier.py
@auth_store.py
@data_fetcher.py

<interfaces>
# Existing redaction patterns to consolidate:
#   notifier.py:1342 — comment "literal api_key with '[REDACTED]'" — replace inline string-replace with redact_secret(api_key)
#   notifier.py:1379 — "Fix 1 (T-06-02): redact api_key from any echo, THEN truncate"
#   auth_store.py logs around totp_secret persistence
#
# New helper (system_params.py):
#   def redact_secret(s: str | None) -> str:
#     '''Redact any secret to first 6 chars + ellipsis. Empty/None → "[empty]".'''
#     if not s: return '[empty]'
#     if len(s) <= 6: return '[short]'  # too short to safely show 6 chars
#     return s[:6] + '...'
#
# Hex-boundary: system_params is already on the FORBIDDEN_MODULES_STDLIB_ONLY hex; redact_secret uses
# only stdlib — safe.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: redact_secret helper + audit + regression</name>
  <read_first>
    - system_params.py
    - notifier.py lines 1316-1410 (api_key plumbing + redaction comments)
    - auth_store.py (full — find every logger.* and Exception with secret in message)
    - data_fetcher.py (audit — likely no secret today)
  </read_first>
  <behavior>
    - test_redact_secret_long: redact_secret('re_abc123def456ghi789') == 're_abc...'.
    - test_redact_secret_short: redact_secret('abc123') == '[short]'.
    - test_redact_secret_empty: redact_secret('') == '[empty]' and redact_secret(None) == '[empty]'.
    - test_notifier_resend_error_redacts: simulate Resend 401 by monkeypatching requests.post → raises with response body containing 're_abc123def456'; assert the captured exception message + log line contain 're_abc...' and NOT the full token.
    - test_auth_store_totp_log_redacts: monkeypatch logger; call set_totp_secret('JBSWY3DPEHPK3PXP'); assert no log line contains the full base32 secret.
  </behavior>
  <action>
1. **system_params.py:** add `redact_secret` per <interfaces>.

2. **notifier.py:**
   - Locate the api_key handling block (lines 1340-1410). Replace any inline `.replace(api_key, '[REDACTED]')` with `redact_secret(api_key)` interpolation:
     - Before: `logger.error(f'[Email] Resend POST failed: {body.replace(api_key, "[REDACTED]")}')`
     - After: `logger.error(f'[Email] Resend POST failed (key={redact_secret(api_key)}): {body.replace(api_key, "[REDACTED]")}')`
     - Keep the body.replace for defense-in-depth (Resend echoes the key back in error responses) AND log the prefix separately so operator can confirm "yes that's my key" when triaging.
   - Import `redact_secret` from system_params at top.

3. **auth_store.py:** audit every `logger.{info,warning,error}` line — grep for `secret`, `token`, `code`, `key`. The current `logger.info('[Auth] totp secret persisted (enrolled=False)')` at line 251 is already redaction-safe (no secret in message). Look for any other log line that interpolates a secret variable. If found, wrap in `redact_secret()`.

4. **data_fetcher.py:** future-proof — if any logger.* lines emit URL with auth (none today per inspection), wrap. Otherwise just import redact_secret and add a comment-anchor for future use.

5. **tests/test_secret_redaction.py (NEW):** 5 tests per behavior block. The Resend-error simulation:
   ```python
   def test_notifier_resend_error_redacts(monkeypatch, caplog):
     class FakeResp:
       status_code = 401
       text = '{"error": "Invalid API key: re_abc123def456ghi789"}'
       def raise_for_status(self): raise requests.HTTPError('401', response=self)
     monkeypatch.setattr('notifier.requests.post', lambda *a, **kw: FakeResp())
     # call the dispatch function with a known api_key
     # assert 're_abc...' is in caplog.text and 're_abc123def456' is NOT
   ```
   Use whatever the existing notifier test fixtures do for monkeypatching requests — see tests/test_notifier.py for prior art.

6. Grep verification:
   ```
   grep -rn 'logger\.\|raise.*api_key\|raise.*secret\|raise.*token' notifier.py auth_store.py data_fetcher.py | grep -v 'redact_secret\|REDACTED\|\[empty\]\|comment\|#'
   # visual review: any match must NOT interpolate a raw secret variable
   ```
  </action>
  <verify>
    <automated>pytest tests/test_secret_redaction.py -x -v</automated>
  </verify>
  <done>
    - redact_secret in system_params.py with 3 named test cases pass.
    - Notifier Resend error path uses redact_secret on api_key prefix.
    - auth_store.py audit complete (no raw secret interpolations remain).
    - 5 tests in test_secret_redaction.py green.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Application logs (stdout/stderr/journalctl) | Could be tailed by ops or backed up offsite — must not contain plaintext secrets |
| Crash-email body | Sent to operator inbox over network — must not echo secrets |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation |
|-----------|----------|-----------|-------------|------------|
| T-27-03-01 | Information disclosure | RESEND_API_KEY appearing in journalctl after Resend 401 → leaks to log archives | mitigate | redact_secret on every log emission of api_key; defense-in-depth body.replace stays. |
| T-27-03-02 | Information disclosure | TOTP secret appearing in auth_store logs | mitigate | Audit complete; no raw secret interpolation. Regression test asserts. |
| T-27-03-03 | Repudiation | Operator denies a key was leaked when it was | accept | Out of scope — single-operator system; no chain-of-custody requirement. |
</threat_model>

<verification>
```
pytest tests/test_secret_redaction.py -x -v
grep -rn 'logger\.' notifier.py auth_store.py data_fetcher.py | grep -iE 'api_key|secret|token' | grep -v 'redact_secret\|REDACTED'
# expected: zero matches that emit a raw variable
```
</verification>

<success_criteria>
- redact_secret in system_params.py with 6-char prefix policy.
- Notifier + auth_store + data_fetcher audited; all secret-emitting log paths redacted.
- 5+ tests in test_secret_redaction.py green.
- Grep gate: no raw-secret log interpolation remains.
</success_criteria>

<output>
Create `27-03-SUMMARY.md` with: redact_secret signature, list of audited files + line numbers patched, regression test count, before/after grep counts.
</output>
