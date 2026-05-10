---
phase: 27
plan: 03
subsystem: secrets + logging hex-boundary
tags:
  - phase-27
  - secret-redaction
  - api-key-leak-prevention
  - defense-in-depth
  - logging-hardening
  - threat-mitigation
requires: []
provides:
  - system_params.redact_secret (single canonical secret redactor — 6-char prefix + ellipsis policy)
  - notifier _post_to_resend ResendError (key=<prefix>...) shape — operator triage signal
  - tests/test_secret_redaction.py (7-test regression suite + structural grep gate)
affects:
  - tests/test_notifier.py (6 assertions migrated to new error format)
tech-stack:
  added: []
  patterns:
    - Single-source secret redactor + defense-in-depth body.replace stays
    - Triage prefix (redact_secret) + scrub body (replace) — two layers, one for ops, one for leak prevention
    - Structural grep-gate test that scans source text for raw-variable interpolations in logger.* / raise sites
key-files:
  created:
    - tests/test_secret_redaction.py
  modified:
    - system_params.py
    - notifier.py
    - data_fetcher.py
    - tests/test_notifier.py
decisions:
  - 6-char prefix is the policy (not 4, not 8) — matches Resend's 're_<7+>' format and pyotp base32 secrets, lets operator triage 'is this MY key' without exposing enough characters to brute-force
  - '[short]' marker for inputs ≤6 chars rather than truncating further — short inputs are usually misconfiguration (env var unset, sentinel value), not real secrets
  - data_fetcher.py imports redact_secret as a future-proof anchor with no call site today — yfinance does not consume an API key, but the pattern is in place for any future vendor-key fetcher
  - notifier keeps the existing body.replace(api_key, '[REDACTED]') AND adds the redact_secret(api_key) prefix — defense-in-depth: prefix is operator-triage signal, replace() is leak prevention
  - auth_store.py audit confirmed clean (no raw secret interpolations); regression test pins the contract so a future logger.info(f'totp={secret}') would fail at PR review
metrics:
  duration: ~25min
  tasks: 1
  files: 5
  tests-added: 7
  tests-passing: 1823 (full suite, +7 from 1816)
  completed: 2026-05-08
---

# Phase 27 Plan 03: API Key Redaction Summary

Centralised secret redaction behind `system_params.redact_secret`. Wired into the two `notifier._post_to_resend` ResendError emission paths so the operator can triage which key blew up without exposing the full token to journalctl. Auditor pass over `auth_store.py` and `data_fetcher.py` confirmed both are already clean — `data_fetcher.py` gets the import as a future-proof anchor; `auth_store.py` is pinned by a regression test that scans for any future raw-secret log emission.

## What shipped

### `system_params.redact_secret` — single source of truth

```python
def redact_secret(s: str | None) -> str:
  '''Redact any secret to first 6 chars + ellipsis.

  Returns:
    '[empty]' if s is None or '' (empty string).
    '[short]' if len(s) <= 6 (too short to safely show 6 chars).
    s[:6] + '...' otherwise.
  '''
  if not s:
    return '[empty]'
  if len(s) <= 6:
    return '[short]'
  return s[:6] + '...'
```

Lives directly under `HTTP_TIMEOUT_S` on the same `FORBIDDEN_MODULES_STDLIB_ONLY` hex. Stdlib-only — no imports added, no hex-boundary mutation.

### `notifier.py` — two ResendError emission paths now surface the prefix

| Path                                | Before                                              | After                                                                   |
| ----------------------------------- | --------------------------------------------------- | ----------------------------------------------------------------------- |
| 4xx fail-fast (line ~1394)          | `'4xx from Resend: <status> <body>'`                | `'4xx from Resend (key=<prefix>...): <status> <body>'`                  |
| Retries-exhausted (line ~1410)      | `'retries exhausted ...; last error: ...'`          | `'retries exhausted ... (key=<prefix>...); last error: ...'`            |

The defense-in-depth `body.replace(api_key, '[REDACTED]')` scrub is preserved and runs BEFORE the redact_secret prefix is appended. Two layers:

- **Layer 1 (leak prevention)** — body.replace scrubs any echo of the raw key out of `resp.text` before the message is built. Even if Resend echoes the Authorization header back in its 401 body, the raw key never reaches the log buffer.
- **Layer 2 (operator triage)** — `redact_secret(api_key)` writes the first 6 chars to the message. Operator triaging a flood of failures can correlate "yep, that's the key I rotated yesterday" without `journalctl` ever seeing the full secret.

### `data_fetcher.py` — future-proof anchor

yfinance does not consume an API key today, so there is no live call site. Adding `redact_secret` to the import block now means the next vendor-key fetcher (Alpha Vantage, Polygon, Tiingo) can wrap log/raise interpolations without anyone needing to remember to also touch the import. Comment-anchor at the import documents the intent.

### `auth_store.py` — audit confirmed clean

Every `logger.info` / `logger.warning` line was inspected. The closest-to-suspicious line is:

```python
logger.info('[Auth] totp secret persisted (enrolled=False)')
```

This is a schema-status string, NOT an interpolation of the `secret` variable. No change needed; regression test `TestAuthStoreTotpLogRedacts::test_auth_store_totp_log_redacts` pins this by calling `set_totp_secret('JBSWY3DPEHPK3PXP')` and asserting the raw base32 secret appears in zero log records.

### `tests/test_secret_redaction.py` — 7-test regression suite

| Test                                                       | Locks in                                                                                       |
| ---------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `test_redact_secret_long`                                  | `redact_secret('re_abc123def456ghi789') == 're_abc...'`                                        |
| `test_redact_secret_short`                                 | `redact_secret('abc123') == '[short]'` AND `redact_secret('a') == '[short]'`                   |
| `test_redact_secret_empty`                                 | `redact_secret('') == '[empty]'` AND `redact_secret(None) == '[empty]'`                        |
| `test_notifier_resend_error_redacts`                       | 4xx fail-fast: ResendError contains `'re_abc...'`, raw key absent (T-27-03-01)                 |
| `test_notifier_retries_exhausted_redacts`                  | Retries-exhausted (ConnectionError carrying raw key in message): same shape                    |
| `test_auth_store_totp_log_redacts`                         | `set_totp_secret('JBSWY3DPEHPK3PXP')` — caplog scan, raw secret absent (T-27-03-02)            |
| `test_no_raw_secret_interpolation_in_logger_or_raise`      | Source-text scan over notifier/auth_store/data_fetcher for `f'... {api_key} ...'` shapes etc.  |

The grep gate is structural — it scans for `f'...{api_key}...'`, `.format(api_key=...)`, and `logger.METHOD(... %s ..., api_key)` shapes against `notifier.py`, `auth_store.py`, `data_fetcher.py`. False positives are tolerable; false negatives are not. Today's pass-result: zero raw-variable interpolations found.

## Audited call sites

| File             | Line  | Original shape                                                  | Disposition                                    |
| ---------------- | ----- | --------------------------------------------------------------- | ---------------------------------------------- |
| notifier.py      | 1394  | `f'4xx from Resend: {resp.status_code} {safe_body}'`            | Patched — adds `(key={redact_secret(api_key)})` |
| notifier.py      | 1410  | `f'retries exhausted ... last error: {err_repr[:200]}'`         | Patched — adds `(key={redact_secret(api_key)})` |
| notifier.py      | 1942  | `'[Email] WARN send_stop_alert_email: missing RESEND_API_KEY'`  | Already safe (env-var NAME, not value)         |
| auth_store.py    | 251   | `'[Auth] totp secret persisted (enrolled=False)'`               | Already safe (schema-status, not value)        |
| data_fetcher.py  | n/a   | (no logger lines mention api_key/secret/token)                  | Future-proof anchor: redact_secret imported    |

## Deviations from Plan

### Auto-fixed issues

**1. [Rule 3 - Blocking] Existing notifier tests asserted literal `'4xx from Resend: <status>'` substring**

- **Found during:** GREEN regression suite — 6 tests in `tests/test_notifier.py` failed after the ResendError format gained the `(key=<prefix>...)` infix.
- **Issue:** Tests `test_4xx_fails_fast` (4× parametrized for 400/401/403/422), `test_api_key_redacted_in_4xx_error_body`, and `test_4xx_returns_zero_and_logs` all asserted `'4xx from Resend: <status>'` as a literal substring or `pytest.raises(match=...)` regex.
- **Fix:** Migrated each assertion to a regex matching the new shape `r'4xx from Resend \(key=[^)]+\): <status>'`. Added `import re` at the top of `tests/test_notifier.py` (4 lines). Updated the docstring of `test_api_key_redacted_in_4xx_error_body` to call out the new format.
- **Files modified:** `tests/test_notifier.py`.
- **Commit:** `d7e5b5a` (rolled into the GREEN feat commit — these were directly caused by the task's format change).
- **Why Rule 3, not Rule 1:** This is not a bug — the literal-substring assertions were entirely correct against the prior shape. The task itself changed the shape; the tests had to follow. Documenting the migration here so a future reviewer can confirm the behavior change was intentional, not a silent test-loosening.

### Plan-spec adjustments

**Plan called for ~5 tests; shipped 7.** Plan named 5 behaviors:

1. test_redact_secret_long
2. test_redact_secret_short
3. test_redact_secret_empty
4. test_notifier_resend_error_redacts
5. test_auth_store_totp_log_redacts

Shipped: those 5 + `test_notifier_retries_exhausted_redacts` (covers the second emission path the plan implicitly required by saying "AND the retries-exhausted message") + `test_no_raw_secret_interpolation_in_logger_or_raise` (the structural grep gate the plan called out in `<verification>` but did NOT enumerate as a test). Strictly stronger than plan-as-written.

## Authentication gates

None — no auth surface touched. The TOTP secret regression test exercises `auth_store.set_totp_secret`, which is a test-mode-only path (monkeypatched `DEFAULT_AUTH_PATH` to `tmp_path`).

## Threat surface scan

None new. The plan's threat register (T-27-03-01 RESEND_API_KEY in journalctl, T-27-03-02 TOTP secret in auth_store logs) describes mitigations of pre-existing surface, not new endpoints / auth paths / file access. `redact_secret` is a pure function; the wiring sites were already production code paths.

## Verification

```
pytest tests/test_secret_redaction.py -x -v
  → 7 passed in 0.13s

pytest tests/test_notifier.py tests/test_auth_store.py tests/test_http_timeouts.py tests/test_secret_redaction.py
  → 215 passed in 90.95s

pytest
  → 1823 passed in 112.58s (full suite, +7 from 1816)

grep -rnE 'logger\.' notifier.py auth_store.py data_fetcher.py | grep -iE 'api_key|secret|token' | grep -v 'redact_secret\|REDACTED'
  → 2 lines (notifier.py:1942 — env-var NAME; auth_store.py:251 — schema-status text); both safe
```

Before/after grep counts:

| Metric                                                                        | Before | After |
| ----------------------------------------------------------------------------- | ------ | ----- |
| Total `logger.*` / `raise` sites mentioning api_key/secret/token              | 2      | 2     |
| Raw-variable interpolations in those sites                                    | 0      | 0     |
| ResendError emissions that surface a redact_secret prefix                     | 0      | 2     |
| Defense-in-depth body.replace scrubs preserved                                | 2      | 2     |
| Regression tests pinning the redaction contract                               | 0      | 7     |

## Commits

| Hash    | Type | Title                                                                              |
| ------- | ---- | ---------------------------------------------------------------------------------- |
| 0fba96a | test | RED — secret redaction regression suite                                            |
| d7e5b5a | feat | GREEN — redact_secret helper + notifier wire-in                                    |

## Self-Check: PASSED

- `system_params.py` modified — confirmed (`redact_secret` at the bottom of the HTTP_TIMEOUT_S section).
- `notifier.py` modified — confirmed (`redact_secret` import + 2 ResendError emission sites updated).
- `data_fetcher.py` modified — confirmed (future-proof import + comment-anchor).
- `tests/test_secret_redaction.py` created — confirmed (7 tests, all green).
- `tests/test_notifier.py` modified — confirmed (`import re` added; 6 assertions migrated).
- Both commit hashes (`0fba96a`, `d7e5b5a`) resolvable via `git log --oneline`.
- Full suite 1823 green; +7 new tests landed cleanly.
- `auth_store.py` audit complete — no production-code change needed; regression test pins the contract.
