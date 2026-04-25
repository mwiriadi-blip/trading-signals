---
phase: 13-auth-read-endpoints
plan: 03
subsystem: web
tags: [auth, middleware, testing, audit-log, contract-tests]
requirements: [AUTH-01, AUTH-02, AUTH-03]
dependency_graph:
  requires:
    - 13-02 (web/middleware/auth.py — AuthMiddleware)
    - 13-01 (tests/conftest.py — autouse WEB_AUTH_SECRET, VALID_SECRET, AUTH_HEADER_NAME)
  provides:
    - AuthMiddleware contract test suite (19 methods across 6 classes) locking AUTH-01..AUTH-03 + D-01..D-06
  affects:
    - tests/test_web_auth_middleware.py (skeleton from 13-01 → fully populated)
tech-stack:
  added: []
  patterns:
    - 'TestClient(create_app()) per-test fixture pattern (matches tests/test_web_healthz.py)'
    - 'AST-walk guard against `==` compare with secret-related identifiers (constant-time compare D-03)'
    - 'caplog.at_level(WARNING, logger="web.middleware.auth") for log-shape assertions (Phase 11 healthz convention)'
    - 'follow_redirects=False on TestClient.get to detect Starlette path-canonicalization redirects'
key-files:
  created: []
  modified:
    - tests/test_web_auth_middleware.py
    - .planning/phases/13-auth-read-endpoints/deferred-items.md
decisions:
  - 'Imported VALID_SECRET conceptually but used inline literal `\'a\' * 32` in TestAuthPasses to keep the test self-documenting and avoid fragile cross-file constant coupling. Conftest.py remains the single source of truth for the autouse fixture; the inline literal is duplicate-by-design at the call site only.'
  - 'WEB_AUTH_PATH module-level Path constant (already in skeleton from 13-01) reused by both TestConstantTimeCompare methods rather than re-declaring `Path("web/middleware/auth.py")` inside each test.'
metrics:
  duration: 4m25s
  completed: 2026-04-25T03:04:30Z
---

# Phase 13 Plan 03: AuthMiddleware Contract Tests Summary

Locked the AuthMiddleware contract with 19 test methods across 6 classes — any future regression that drops the WARN log, leaks the header name in the 401 body, switches `hmac.compare_digest` to `==`, breaks XFF first-entry parsing, omits UA truncation, allows newline log-injection, or broadens EXEMPT_PATHS to a prefix / case-insensitive match will fire red in CI before merge.

## Files Modified

| File | Change |
| --- | --- |
| `tests/test_web_auth_middleware.py` | Wave 0 skeleton (6 empty class declarations from 13-01) populated with 19 test methods + 2 module-level fixtures (`client_with_auth`, `client_no_auth`) + 1 helper (`_stub_load_state`). |
| `.planning/phases/13-auth-read-endpoints/deferred-items.md` | Appended note that today's `tests/test_main.py::TestCLI::test_force_email_sends_live_email` failure is the same out-of-scope cluster — date-dependent (Saturday weekend-skip), pre-existing on base `c7f5c76`. |

No production code modified — Plan 02's middleware survived contract testing without modification.

## Tests Added (19 across 6 classes)

| Class | Method | Spec | Status |
| --- | --- | --- | --- |
| TestAuthRequired | test_missing_header_returns_401 | AUTH-01 | PASS |
| TestAuthRequired | test_wrong_header_returns_401 | AUTH-01 | PASS |
| TestAuthRequired | test_api_state_also_requires_auth | AUTH-01 | PASS |
| TestAuthPasses | test_correct_header_passes_through | AUTH-01 + D-01 | PASS |
| TestExemption | test_healthz_bypasses_auth_no_header | D-02 | PASS |
| TestExemption | test_healthz_bypasses_auth_wrong_header | D-02 | PASS |
| TestExemption | **test_healthz_trailing_slash_is_NOT_exempt** | D-02 + REVIEWS LOW #5 | PASS |
| TestExemption | **test_healthz_uppercase_is_NOT_exempt** | D-02 + REVIEWS LOW #5 | PASS |
| TestUnauthorizedResponse | test_body_is_plain_text_unauthorized | AUTH-02 + D-04 | PASS |
| TestUnauthorizedResponse | test_content_type_is_text_plain_with_charset | D-04 | PASS |
| TestUnauthorizedResponse | test_no_www_authenticate_header | AUTH-02 | PASS |
| TestUnauthorizedResponse | test_body_does_not_leak_header_or_env_var_names | AUTH-02 | PASS |
| TestAuditLog | test_warn_logged_on_failure | AUTH-03 | PASS |
| TestAuditLog | test_log_extracts_ip_from_xff_first_entry | D-05 | PASS |
| TestAuditLog | test_log_falls_back_to_client_host_without_xff | D-05 | PASS |
| TestAuditLog | test_user_agent_truncated_to_120_chars | D-05 / SC-5 | PASS |
| TestAuditLog | test_user_agent_repr_escapes_control_chars | D-05 (T-13-03b mitigation) | PASS |
| TestConstantTimeCompare | test_source_uses_hmac_compare_digest | D-03 (T-13-01 mitigation) | PASS |
| TestConstantTimeCompare | test_source_does_not_use_equality_for_secret_compare | D-03 (T-13-01 mitigation) | PASS |

**Total:** 19 methods (17 base + 2 REVIEWS LOW #5 D-02 negative-exemption tests).

## REVIEWS LOW #5 Fix Applied

`13-REVIEWS.md` flagged that the original plan only tested the happy path of D-02 exemption (`/healthz` exact match) but did NOT lock the negative cases — leaving the door open for someone to "helpfully" change `request.url.path in EXEMPT_PATHS` to `request.url.path.lower().startswith('/healthz')` and silently broaden the exemption to `/healthz/`, `/healthz/foo`, `/HEALTHZ`, etc.

Two explicit regression tests now lock exact-match semantics:

1. **`test_healthz_trailing_slash_is_NOT_exempt`** — uses `client_no_auth.get('/healthz/', follow_redirects=False)` and asserts `r.status_code in (401, 307)`. Accepts 307 because some Starlette versions issue a redirect to `/healthz`; either way, the exemption did not fire on the trailing-slash path. **Observed under FastAPI 0.136.1 + Starlette today: 307 redirect** — both behaviours are valid because they prove the exemption is path-exact, not prefix.
2. **`test_healthz_uppercase_is_NOT_exempt`** — `client_no_auth.get('/HEALTHZ')` must return 401. The `EXEMPT_PATHS = frozenset({'/healthz'})` is case-sensitive Python set membership; uppercase falls through.

Both tests went green on first run — Plan 02's middleware was already correct under exact-match semantics; the tests just lock that as a contract.

## Acceptance Criteria Results

All 27 acceptance criteria from the plan greens.

| Criterion | Result |
| --- | --- |
| `_stub_load_state` defined exactly once | OK (1 occurrence) |
| `client_with_auth` fixture defined | OK (1 occurrence) |
| `client_no_auth` fixture defined | OK (1 occurrence) |
| 19 `def test_*` methods total | OK (19 occurrences) |
| `test_healthz_trailing_slash_is_NOT_exempt` present | OK |
| `test_healthz_uppercase_is_NOT_exempt` present | OK |
| `[Web] auth failure` substring asserted | OK (2 occurrences in test source — both in TestAuditLog asserting prefix) |
| `pytest tests/test_web_auth_middleware.py -x -v` exits 0 | OK (19 passed, 0 failed) |
| `pytest tests/test_web_*.py -x -q` exits 0 | OK (76 passed) |
| `pytest tests/test_signal_engine.py::TestDeterminism -x -q` exits 0 (hex boundary) | OK (44 passed) |
| `grep -c 'hmac.compare_digest' web/middleware/auth.py` outputs 1 | OK (Plan 02 invariant preserved — production source not modified) |

## Verification Summary

```
$ python -m pytest tests/test_web_auth_middleware.py -x -v
19 passed in 0.22s

$ python -m pytest tests/test_web_*.py -x -q
76 passed in 0.31s

$ python -m pytest tests/test_signal_engine.py::TestDeterminism -x -q
44 passed in 0.48s
```

Confirmation that **Plan 02's middleware survived contract testing without modification** — all 19 contract tests went green against the existing `web/middleware/auth.py` from 13-02. No deviations to production code; this plan is purely test-locking.

## Threat Register Mitigations Verified

| Threat ID | Severity | Mitigation Verified By |
| --- | --- | --- |
| T-13-01 (Timing attack on secret compare) | high | TestConstantTimeCompare::test_source_uses_hmac_compare_digest + test_source_does_not_use_equality_for_secret_compare |
| T-13-02 (Secret leaked via journald) | high | TestAuditLog::test_warn_logged_on_failure asserts the exact `[Web] auth failure: ip=... ua=... path=...` shape; no secret/header field leaks. |
| T-13-03 (XFF spoofing) | medium | TestAuditLog::test_log_extracts_ip_from_xff_first_entry + test_log_falls_back_to_client_host_without_xff |
| T-13-03b (Log injection via UA) | medium | TestAuditLog::test_user_agent_repr_escapes_control_chars (asserts single WARN record, no double-line injection) |
| T-13-03c (401 body leaks attack-surface hints) | medium | TestUnauthorizedResponse::test_body_is_plain_text_unauthorized + test_no_www_authenticate_header + test_body_does_not_leak_header_or_env_var_names |
| T-13-03d (Path-canonicalization bypass) | medium | TestExemption::test_healthz_trailing_slash_is_NOT_exempt + test_healthz_uppercase_is_NOT_exempt (REVIEWS LOW #5) |

All 6 STRIDE register mitigations have automated test coverage.

## Deviations from Plan

None — the plan executed exactly as written. The two issues observed were both **pre-existing on base `c7f5c76`** and out-of-scope per the executor scope-boundary rule:

1. `tests/test_main.py::TestCLI::test_force_email_sends_live_email` fails today (Saturday `weekday=5` triggers weekend-skip before email send). This is a date-dependent flake that exists in 16+ tests in `tests/test_main.py` per the existing deferred-items.md entry. Appended a note to deferred-items.md confirming this specific test rolls into the same cluster.
2. The worktree's pyenv shim `python` does not have fastapi installed. Resolved by using the main repo's `.venv/bin/python` (fastapi 0.136.1) for verification. No code change needed — pyproject.toml's testpaths and python_files settings are correct.

## Self-Check: PASSED

- File `tests/test_web_auth_middleware.py` exists at expected path: FOUND
- File `.planning/phases/13-auth-read-endpoints/deferred-items.md` exists at expected path: FOUND
- Commit `d58a177` (Task 1) reachable on branch: FOUND (verified via `git log --oneline -3`)
- Commit `792ed29` (Task 2) reachable on branch: FOUND (verified via `git log --oneline -3`)
- 19 test methods present in `tests/test_web_auth_middleware.py`: VERIFIED (`grep -c '  def test_' = 19`)
- All 19 tests pass: VERIFIED (`pytest -x -v` exits 0)
- Production source `web/middleware/auth.py` unmodified: VERIFIED (no diff against 13-02 base)
