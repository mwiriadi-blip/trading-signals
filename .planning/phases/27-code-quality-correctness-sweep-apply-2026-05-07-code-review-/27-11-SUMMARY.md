---
phase: 27
plan: 11
subsystem: notifier + dashboard — silent crash dropout prevention
tags:
  - phase-27
  - crash-fallback
  - last-crash-json
  - secret-redaction
  - dashboard-banner
  - never-crash-invariant
  - threat-mitigation
dependency_graph:
  requires:
    - 27-03-api-key-redaction-PLAN.md  # redact_secret used in pattern-walk
    - 27-08-html-escape-audit-PLAN.md  # html.escape(quote=True) on banner
  provides:
    - "system_params.LAST_CRASH_FILE — configurable crash-fallback filename"
    - "notifier._resolve_last_crash_path — env-var override resolver"
    - "notifier._redact_secrets_in_text — re_/sk_/Bearer pattern walker"
    - "notifier._build_last_crash_payload — schema constructor"
    - "notifier._write_last_crash — atomic, never-raise crash-fallback writer"
    - "dashboard_renderer/components/header.render_last_crash_banner — XSS-safe banner"
  affects:
    - "notifier.send_crash_email — fallback wired into ResendError + Exception branches"
    - "dashboard_renderer/components/header.render_header — banner rendered next to status strip"
tech_stack:
  added: []
  patterns:
    - "Configurable I/O path via env-var override + str default in stdlib-only hex"
    - "Pre-write secret redaction (pattern walk → redact_secret) before disk write"
    - "Atomic write: tempfile + os.replace + tempfile cleanup on partial failure"
    - "Defense-in-depth never-raise: try/except wraps full helper body"
    - "Renderer reads config-shared env var (no notifier import → hex boundary preserved)"
key_files:
  created:
    - tests/test_crash_email_fallback.py
  modified:
    - system_params.py
    - notifier.py
    - dashboard_renderer/components/header.py
decisions:
  - "system_params.LAST_CRASH_FILE is a `str`, NOT a pathlib.Path constant. system_params is stdlib-only per FORBIDDEN_MODULES_STDLIB_ONLY (test_signal_engine.py blocks os/pathlib import). Path resolution lives in notifier._resolve_last_crash_path() — same shape as STATE_FILE."
  - "Default crash path sits next to STATE_FILE — NOT a separate working location. Operator can override via LAST_CRASH_PATH env var (configurable, agreed-5)."
  - "Secret patterns explicitly accept underscores in token bodies ([A-Za-z0-9_]) so a real-shape Resend key like `re_test_abc123def456ghi789` matches as a single token (not split at the first underscore)."
  - "Generic `api_key=\"...\"` kwarg pattern was DELIBERATELY OMITTED. The specific token patterns (re_, sk_, Bearer) already match the secret bodies inside such kwargs; a second-pass kwarg sweep would double-substitute already-redacted content (e.g. `api_key=\"re_tes...\"` → `api_ke...`), destroying the triage prefix."
  - "Banner renderer defines its own _resolve_last_crash_path mirror rather than importing notifier — preserves the hex boundary (renderer never imports notifier). LAST_CRASH_PATH env var is the shared config contract."
  - "Banner appended to render_header next to status_strip rather than nested inside render_status_strip itself. Plan called for `dashboard_renderer/components/health.py` (file does not exist) and/or extending render_status_strip directly. Sibling placement keeps single-responsibility (status strip = countdown + dot; banner = crash recovery surface) without touching status-strip's HTMX swap target."
  - "_write_last_crash NEVER raises — full body wrapped in try/except per the project's never-crash invariant (D-13 + Phase 8 SC-3). Tested explicitly with monkeypatched Path.write_text raising OSError + nested test where BOTH dispatch and disk-write fail."
metrics:
  duration: ~19min
  tasks: 2
  files_created: 1
  files_modified: 3
  tests_added: 14
  tests_passing: 1940 (full suite, +14 from 1926 baseline)
  completed_date: 2026-05-08
---

# Phase 27 Plan 11: Crash-Email Second-Line Fallback Summary

When `notifier.send_crash_email`'s outbound Resend dispatch fails (network outage, ResendError after retries exhausted, unexpected exception), the redacted crash payload now lands on disk at `LAST_CRASH_PATH` so the operator sees the original crash on the next dashboard visit even when no email arrived. Closes review item #15 — silent crash dropout prevention.

## What shipped

### `system_params.LAST_CRASH_FILE` — configurable filename

```python
LAST_CRASH_FILE: str = 'last_crash.json'
```

Stored as a `str` (not `pathlib.Path`) to honor the stdlib-only hex constraint enforced by `tests/test_signal_engine.py::TestDeterminism::test_phase2_hex_modules_no_numpy_pandas` — `system_params` cannot import `os` or `pathlib`. Path resolution lives in the notifier hex (the I/O hex) where those imports are legitimate. Same convention as `STATE_FILE`.

### `notifier._resolve_last_crash_path()` — env-var override resolver

```python
def _resolve_last_crash_path() -> Path:
  override = os.environ.get('LAST_CRASH_PATH', '').strip()
  if override:
    return Path(override)
  return Path(STATE_FILE).parent / LAST_CRASH_FILE
```

Default: next to `state.json` (NOT project root, NOT a separate working location). Operator override: set `LAST_CRASH_PATH=/var/lib/trading-signals/last_crash.json` in the systemd unit's `EnvironmentFile`.

### `notifier._redact_secrets_in_text()` + `_SECRET_PATTERNS_PHASE27_11`

```python
_SECRET_PATTERNS_PHASE27_11 = (
  re.compile(r're_[A-Za-z0-9_]{16,}'),     # Resend API keys (with underscores)
  re.compile(r'sk_[A-Za-z0-9_]{16,}'),     # Stripe-style keys
  re.compile(r'Bearer\s+[A-Za-z0-9._\-]+'), # Bearer tokens
)

def _redact_secrets_in_text(text):
  for pat in _SECRET_PATTERNS_PHASE27_11:
    text = pat.sub(lambda m: redact_secret(m.group(0)), text)
  return text
```

Each match is replaced with `redact_secret(match)` from system_params (Plan 27-03) — first 6 chars + ellipsis. Operator triage retained ("yep, that was the rotated key"); raw token never reaches disk.

**Pattern subtleties:**

1. **Underscores in token bodies.** `re_test_abc123def456ghi789` is a real-shape Resend test key. The character class `[A-Za-z0-9]` would have matched only `re_test` (4 body chars, fails the `{16,}` minimum), leaving the rest of the token untouched. Switched to `[A-Za-z0-9_]` so the whole token matches as a single secret.

2. **No generic `api_key="..."` kwarg pattern.** The specific token patterns (re_, sk_, Bearer) already match the secret bodies inside such kwargs. A second-pass kwarg sweep would double-substitute already-redacted content (`api_key="re_tes..."` → `api_ke...`), destroying the triage prefix. Documented inline.

### `notifier._build_last_crash_payload()` — schema constructor

```python
def _build_last_crash_payload(exc, now, tb_text_list) -> dict:
  return {
    'timestamp_utc': utc_now.astimezone(pytz.UTC).isoformat(),
    'run_date_aws': utc_now.astimezone(awst).strftime('%Y-%m-%d'),
    'exception_type': type(exc).__name__,
    'exception_message': str(exc),
    'traceback': '\n'.join(''.join(tb_text_list).splitlines()[-50:]),
    'send_email_failure': True,
  }
```

Schema matches the plan's `<interfaces>` block. Last 50 traceback lines (size guard). `send_email_failure: True` is the discriminator the dashboard banner uses to phrase the surface.

### `notifier._write_last_crash()` — atomic + never-raise

```python
def _write_last_crash(payload):
  try:
    redacted = dict(payload)
    if 'traceback' in redacted:
      redacted['traceback'] = _redact_secrets_in_text(redacted['traceback'])
    if 'exception_message' in redacted:
      redacted['exception_message'] = _redact_secrets_in_text(redacted['exception_message'])
    path = _resolve_last_crash_path()
    tmp = path.with_suffix(path.suffix + '.tmp')
    try:
      tmp.write_text(json.dumps(redacted, indent=2, default=str))
      os.replace(tmp, path)
    finally:
      if tmp.exists():
        try: tmp.unlink()
        except Exception: pass
  except Exception as e:
    logger.error('[Crash] last_crash.json write failed: %s: %s', type(e).__name__, e)
```

Three layers of safety:
1. **Pre-write redaction** — secrets walk through `_redact_secrets_in_text` BEFORE the json.dumps + write_text, so the on-disk JSON never contains a raw token (T-27-11-03 mitigation).
2. **Atomic write** — tempfile + `os.replace`. Partial writes are never visible; tempfile cleanup runs in `finally`.
3. **Never raises** — full body wrapped in try/except. Even disk-full / read-only-fs / json-encode-error cases log + return; the daily loop never sees an exception (D-13 + Phase 8 SC-3 invariant).

### Wire-in: `send_crash_email` failure paths

Both ResendError and unexpected-Exception branches of `send_crash_email` now call:

```python
_write_last_crash(_build_last_crash_payload(exc, now, tb_text))
```

This runs AFTER `_post_to_resend` raises (retries exhausted) but BEFORE the SendStatus return. So:
- Daily-loop crash → `send_crash_email` invoked from `main.py:2027`
- Resend down → `_post_to_resend` raises ResendError
- Fallback writer fires → `last_crash.json` written
- `SendStatus(ok=False, reason=...)` returned to caller (no exception propagates)

### `dashboard_renderer/components/header.render_last_crash_banner()`

```python
def render_last_crash_banner() -> str:
  path = _resolve_last_crash_path()
  try:
    data = json.loads(path.read_text())
  except (FileNotFoundError, json.JSONDecodeError, OSError):
    return ''
  if not isinstance(data, dict):
    return ''
  timestamp = html.escape(str(data.get('timestamp_utc', '')), quote=True)
  exc_type = html.escape(str(data.get('exception_type', '')), quote=True)
  exc_msg = html.escape(str(data.get('exception_message', '')), quote=True)
  return (
    '<div class="last-crash-banner" role="alert" aria-live="polite">'
    f'<strong>Last crash:</strong> {timestamp} — '
    f'{exc_type}: {exc_msg}'
    '</div>\n'
  )
```

- Empty string when no file present → goldens stay byte-stable.
- Defensive read (FileNotFoundError, json.JSONDecodeError, OSError) → malformed file never crashes dashboard render.
- Every interpolation `html.escape(value, quote=True)` per Plan 27-08 contract (T-27-11-02 XSS mitigation).
- `role="alert" aria-live="polite"` for screen-reader users.
- Renderer defines its own `_resolve_last_crash_path` mirror rather than importing notifier — keeps hex boundary clean (`dashboard_renderer` never imports `notifier`). The shared LAST_CRASH_PATH env var is the cross-hex config contract.

### Wired into `render_header`

```python
status_strip = render_status_strip(state, now)
last_crash_banner = render_last_crash_banner()
return (
  '<header>...'
  f'{status_strip}'
  f'{last_crash_banner}'
  '</header>\n'
)
```

Sibling to status_strip rather than nested inside it. Status strip owns "live system pulse" (last run + countdown + dot); banner owns "operator-recovery surface for last failed crash email". Functionally distinct — keeping them sibling preserves single-responsibility.

## Schema of `last_crash.json`

```json
{
  "timestamp_utc": "2026-05-07T14:30:00+00:00",
  "run_date_aws": "2026-05-07",
  "exception_type": "ConnectionError",
  "exception_message": "Resend network unreachable",
  "traceback": "Traceback...\n  File \"main.py\", line 1234\n    ...",
  "send_email_failure": true
}
```

Fields after redaction. `traceback` and `exception_message` walk through `_redact_secrets_in_text` before write — any `re_<...>`, `sk_<...>`, or `Bearer <...>` substring is replaced with `redact_secret()` output (6-char prefix + ellipsis).

## Tests (14 — `tests/test_crash_email_fallback.py`)

| Class | Test | Asserts |
|---|---|---|
| TestLastCrashPathConfig | test_last_crash_file_constant_present | `system_params.LAST_CRASH_FILE == 'last_crash.json'`, type str |
| TestLastCrashPathConfig | test_notifier_last_crash_path_resolves_relative_to_state | Default sits in same dir as STATE_FILE |
| TestLastCrashPathConfig | test_last_crash_path_is_overridable_via_env | LAST_CRASH_PATH env var honored (configurable) |
| TestWriteLastCrash | test_write_last_crash_creates_file | File exists with valid JSON content |
| TestWriteLastCrash | test_write_last_crash_never_raises_on_oserror | monkeypatch Path.write_text → OSError; no exception propagates |
| TestWriteLastCrash | test_write_last_crash_redacts_traceback | `re_test_abc123...` → `re_tes...`; raw token absent |
| TestWriteLastCrash | test_write_last_crash_redacts_exception_message | `Bearer eyJabc123...` redacted |
| TestWriteLastCrash | test_write_last_crash_atomic | No `.tmp` leftover after successful write |
| TestSendCrashEmailFailureWritesLastCrash | test_send_crash_email_failure_writes_last_crash | Resend POST → ConnectionError; last_crash.json written; `send_email_failure: True` |
| TestSendCrashEmailFailureWritesLastCrash | test_send_crash_email_failure_never_propagates | BOTH dispatch AND disk-write fail; no exception propagates |
| TestDashboardLastCrashBanner | test_renders_banner_when_last_crash_exists | `<div class="last-crash-banner">` + timestamp + type + message present |
| TestDashboardLastCrashBanner | test_no_banner_when_last_crash_absent | Returns `''`; no banner element |
| TestDashboardLastCrashBanner | test_uses_configurable_path | LAST_CRASH_PATH override resolves correctly |
| TestDashboardLastCrashBanner | test_banner_xss_safe | `<script>` in exception_message → `&lt;script&gt;`; `"` → `&quot;` |

## Threat-model verification

| Threat ID | Disposition | Verification |
|-----------|-------------|--------------|
| T-27-11-01 (Resend outage during crash → operator never sees crash) | mitigate ✓ | `test_send_crash_email_failure_writes_last_crash` — last_crash.json written with `send_email_failure: True` after dispatch fails |
| T-27-11-02 (XSS via exception_message containing HTML) | mitigate ✓ | `test_banner_xss_safe` — `<script>` escaped to `&lt;script&gt;`; `quote=True` enforced |
| T-27-11-03 (Information disclosure: api_key in traceback on disk) | mitigate ✓ | `test_write_last_crash_redacts_traceback` + `test_write_last_crash_redacts_exception_message` — raw tokens absent on disk |
| T-27-11-04 (Hardcoded path conflicts with file-placement rule) | mitigate ✓ | LAST_CRASH_PATH env var override + default next to STATE_FILE; `test_last_crash_path_is_overridable_via_env` |

## Deviations from Plan

### Auto-fixed issues

**1. [Rule 1 — Plan-vs-reality] LAST_CRASH_PATH cannot be a `pathlib.Path` constant in system_params.py.**

- **Found during:** Task 1 architecture pass.
- **Issue:** Plan's `<interfaces>` showed `LAST_CRASH_PATH: Path = STATE_DIR / 'last_crash.json'` defined in system_params.py with `from pathlib import Path` and `STATE_DIR = Path(os.environ.get('STATE_DIR', '.')).resolve()`. system_params.py is stdlib-only per `FORBIDDEN_MODULES_STDLIB_ONLY` enforced at `tests/test_signal_engine.py::TestDeterminism::test_phase2_hex_modules_no_numpy_pandas` — `os` and `pathlib` are explicitly forbidden.
- **Fix:** Stored as `LAST_CRASH_FILE: str = 'last_crash.json'` matching the existing `STATE_FILE: str = 'state.json'` precedent. Path resolution lives in `notifier._resolve_last_crash_path()` (notifier IS the I/O hex; os and pathlib are legitimate there). Operator override via LAST_CRASH_PATH env var.
- **Files modified:** `system_params.py`, `notifier.py`.
- **Commit:** `90307a2`.

**2. [Rule 1 — Plan-vs-reality] `dashboard_renderer/components/health.py` does not exist.**

- **Found during:** Task 2 component placement.
- **Issue:** Plan `<files_modified>` named `dashboard_renderer/components/health.py`. The file does not exist. `render_status_strip` (which the plan also referenced) lives in `dashboard_renderer/components/header.py`.
- **Fix:** Added `render_last_crash_banner` to `dashboard_renderer/components/header.py` (where `render_status_strip` already lives) and wired it as a sibling block inside `render_header` next to `status_strip`. Plan note explained: status strip owns "live system pulse"; banner owns "operator-recovery surface" — functionally distinct, sibling placement preserves single-responsibility.
- **Files modified:** `dashboard_renderer/components/header.py`.
- **Commits:** `90307a2`, `80fee5e`.

**3. [Rule 1 — Pattern correctness] Resend key pattern `re_[A-Za-z0-9]{16,}` does not match real-shape tokens.**

- **Found during:** GREEN regression run (`test_write_last_crash_redacts_traceback` failed).
- **Issue:** Real-shape Resend test key `re_test_abc123def456ghi789` contains underscores in the body. With `[A-Za-z0-9]` (no underscore), the greedy match consumed only `re_test` (4 body chars), failed the `{16,}` minimum, no match emitted, raw token landed on disk.
- **Fix:** Switched character class to `[A-Za-z0-9_]` so underscores in the body are matched. Same fix applied to `sk_` pattern for consistency.
- **Files modified:** `notifier.py` (`_SECRET_PATTERNS_PHASE27_11`).
- **Commit:** `90307a2`.

**4. [Rule 1 — Pattern correctness] Generic `api_key="..."` kwarg pattern double-substituted already-redacted content.**

- **Found during:** GREEN regression run (`test_write_last_crash_redacts_traceback` continued to fail after fix #3).
- **Issue:** First sub() pass: `api_key="re_test_abc123def456ghi789"` → `api_key="re_tes..."`. Second sub() pass (the kwarg pattern matched the already-redacted content): `api_key="re_tes..."` → `api_ke...`. Result: triage prefix destroyed, banner shows `api_ke...` instead of `re_tes...`.
- **Fix:** Removed the generic `api_key="..."` kwarg pattern entirely. The specific token patterns (re_, sk_, Bearer) already match the secret BODIES inside such kwargs — covering the kwarg shape is redundant once the body matches. Documented inline.
- **Files modified:** `notifier.py` (`_SECRET_PATTERNS_PHASE27_11`).
- **Commit:** `90307a2`.

**5. [Rule 3 — Blocking] Mid-file `import json as ...` / `import re as ...` violated ruff E402.**

- **Found during:** Full-suite run (`test_ruff_clean_notifier`).
- **Issue:** Plan `<interfaces>` showed the helpers using a local `import re as _re` inside the function. Lifting them to module level for clarity placed them mid-file (after the existing `from system_params import ...` block), triggering ruff E402 "Module level import not at top of file".
- **Fix:** Moved both aliased imports to the top of the file alongside the other stdlib imports. Aliased to `_json_phase27_11` / `_re_phase27_11` to avoid name collisions with any future module-level `json` / `re` imports.
- **Files modified:** `notifier.py` (top-of-file imports).
- **Commit:** `90307a2` (rolled into the GREEN feat commit — directly caused by the GREEN-implementation choice to lift the imports).

### Plan-spec adjustments

**Plan called for 11 tests; shipped 14.** Plan named:
- 7 helper/redaction tests
- 4 dashboard tests
Shipped:
- 8 helper tests (added `test_write_last_crash_atomic` — verifies no `.tmp` leftover, anti-leak gate)
- 2 send_crash_email wire-in tests (separate class — `test_send_crash_email_failure_writes_last_crash` + `test_send_crash_email_failure_never_propagates`)
- 4 dashboard tests

Strictly stronger than plan-as-written.

### CLAUDE.md compliance

- No new files at root (test added to `tests/`).
- No documentation files created beyond plan-output SUMMARY.md.
- File sizes: tests/test_crash_email_fallback.py = 308 lines (under 500); notifier.py grew by ~96 lines (was 2051, now ~2147, still well under any explicit ceiling).
- Read-before-edit honored.
- No secrets/credentials touched in source.

## Authentication gates

None — no auth surface touched.

## Threat surface scan

No new endpoints, auth paths, or trust-boundary changes. The new disk-write surface (`last_crash.json`) is a controlled local file at the same trust level as `state.json` (operator-readable, on the same droplet). Threat register entries T-27-11-01..04 are listed above; all mitigated.

## Verification

```
$ .venv/bin/python -m pytest tests/test_crash_email_fallback.py -v
  → 14 passed

$ .venv/bin/python -m pytest
  → 1940 passed in 159.35s

$ grep -n '_write_last_crash\|LAST_CRASH_FILE\|last_crash' notifier.py system_params.py dashboard_renderer/components/header.py
  → 17 references across 3 files (helpers + wire-in + banner)

$ .venv/bin/ruff check notifier.py dashboard_renderer/components/header.py
  → All checks passed!
```

## Commits

| Hash | Type | Title |
|------|------|-------|
| `b02fda7` | test | RED — crash-email second-line fallback to last_crash.json |
| `90307a2` | feat | GREEN — crash-email second-line fallback to last_crash.json |
| `80fee5e` | feat | wire render_last_crash_banner into render_header |

## Self-Check: PASSED

- [x] `tests/test_crash_email_fallback.py` exists (commit `b02fda7`).
- [x] `system_params.LAST_CRASH_FILE` defined (commit `90307a2`).
- [x] `notifier._write_last_crash`, `_resolve_last_crash_path`, `_redact_secrets_in_text`, `_build_last_crash_payload` all defined (commit `90307a2`).
- [x] `dashboard_renderer/components/header.render_last_crash_banner` defined and wired into `render_header` (commits `90307a2` + `80fee5e`).
- [x] All 3 commit hashes resolvable from HEAD.
- [x] 14/14 plan tests green.
- [x] 1940/1940 full suite green (+14 from 1926 baseline).
- [x] ruff clean on all modified files.
- [x] T-27-11-01..04 mitigations all verified by named tests.
