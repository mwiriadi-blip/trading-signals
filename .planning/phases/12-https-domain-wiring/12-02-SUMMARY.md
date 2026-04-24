---
phase: 12
plan: 02
subsystem: notifier
tags: [notifier, env-var, refactor, email, never-crash, infra-01]
dependency_graph:
  requires:
    - "Phase 6 notifier.py compose/dispatch surface (notifier.SendStatus, _post_to_resend)"
    - "Phase 8 D-08 SendStatus dispatch-result contract (orchestrator routes ok=False → append_warning)"
    - "Phase 11 EnvironmentFile=- convention (SIGNALS_EMAIL_FROM arrives via /etc/trading-signals/.env)"
  provides:
    - "notifier.py: env-var-driven sender with fail-loud missing path (no hardcoded _EMAIL_FROM)"
    - "tests/test_notifier.py::TestEmailFromEnvVar (4 tests) + module-level autouse SIGNALS_EMAIL_FROM fixture"
    - "tests/regenerate_notifier_golden.py: pinned SIGNALS_EMAIL_FROM via setdefault + from_addr kwarg threading"
  affects:
    - "Plan 12-04 SETUP-HTTPS.md §7 — operator adds SIGNALS_EMAIL_FROM=... to /etc/trading-signals/.env + `python main.py --force-email` confirmation step"
    - "main._dispatch_email_and_maintain_warnings — new `missing_sender` SendStatus reason routes to append_warning (preserves Phase 8 W3 invariant)"
tech_stack:
  added: []
  patterns:
    - "Per-send os.environ.get('SIGNALS_EMAIL_FROM', '').strip() read at top of dispatch function (D-15, mirrors RESEND_API_KEY read pattern at notifier.py:1417)"
    - "Keyword-only argument with no default (compose_email_body from_addr) — signature drift fails loudly (RESEARCH §Pattern 2)"
    - "Module-level autouse fixture pinning SIGNALS_EMAIL_FROM to the golden-committed value (D-19); individual tests override via monkeypatch.delenv / setenv('') — pytest last-mutation-wins"
    - "SendStatus stays 2-field (ok, reason) — research finding #2 rejected D-14's aspirational attempts=0 (would cascade into main.py Phase 8 dispatch + 20 downstream tests)"
key_files:
  created: []
  modified:
    - notifier.py
    - tests/test_notifier.py
    - tests/regenerate_notifier_golden.py
decisions:
  - "D-14 functional intent preserved via orchestrator routing (not direct notifier append_warning). Missing SIGNALS_EMAIL_FROM returns SendStatus(ok=False, reason='missing_sender'); main._dispatch_email_and_maintain_warnings translates ok=False into state_manager.append_warning on the next run. Preserves Phase 8 W3 two-saves-per-run invariant — notifier NEVER calls save_state or append_warning directly."
  - "SendStatus stays 2-field (ok, reason). Research finding #2 locks this — extending to 3-field (attempts=0) would cascade into main.py Phase 8 dispatch code + 20 downstream tests. Observable behavior unchanged."
  - "from_addr is keyword-only with NO default in compose_email_body signature. Makes signature drift fail loudly; every call site must pass from_addr explicitly (38 test call sites + 1 notifier internal call + 1 regenerator call — all updated in this plan)."
  - "Missing-sender path returns BEFORE compose_email_body and last_email.html write (12-REVIEWS.md LOW no-side-effects contract). TestEmailFromEnvVar #2/#3/#4 assert last_email.html is NOT created."
  - "Module-level autouse fixture `_pin_signals_email_from` pins SIGNALS_EMAIL_FROM for every test in tests/test_notifier.py (D-19). Intentionally broad — every test class touches email rendering or dispatch; narrowing scope would require per-class fixtures on 7+ classes."
metrics:
  duration: "~15 minutes"
  completed: "2026-04-24T21:08:00Z"
  tasks_completed: 3
  files_created: 0
  files_modified: 3
  tests_added: 4
  tests_total: 161 (tests/test_notifier.py — full file passes)
---

# Phase 12 Plan 02: notifier SIGNALS_EMAIL_FROM Refactor Summary

**One-liner:** Removed hardcoded `_EMAIL_FROM` constant and replaced with per-send `os.environ.get('SIGNALS_EMAIL_FROM')` reads in both `send_daily_email` and `send_crash_email`; missing/empty env var fails loudly with `logger.error` + `SendStatus(ok=False, reason='missing_sender')` (no Resend call, no last_email.html write); threaded `from_addr` as keyword-only kwarg through `compose_email_body` → `_render_footer_email`.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Wave 0 RED: TestEmailFromEnvVar + autouse fixture | 69415cc | tests/test_notifier.py |
| 2 | Wave 1 GREEN: refactor notifier.py + update 38 test call sites | ac9cf0e | notifier.py, tests/test_notifier.py |
| 3 | Pin SIGNALS_EMAIL_FROM in golden regenerator | 95602d3 | tests/regenerate_notifier_golden.py |

## Exact Changes

### notifier.py (6 edits — research finding #1 four touch sites + 2 send_* env reads)

| Edit | Location | Before → After |
|------|----------|----------------|
| 1 | line 99 | `_EMAIL_FROM = 'signals@carbonbookkeeping.com.au'` → DELETED (D-16) |
| 2 | line 1135 (`_render_footer_email` signature) | `(state: dict, now: datetime)` → `(state: dict, now: datetime, from_addr: str)` |
| 3 | line 1147 (footer HTML interpolation) | `{html.escape(_EMAIL_FROM, quote=True)}` → `{html.escape(from_addr, quote=True)}` |
| 4 | lines 1154-1158 (`compose_email_body` signature) | added `*, from_addr: str` as keyword-only no-default arg |
| 5 | line 1188 (internal `_render_footer_email` call) | `_render_footer_email(state, now)` → `_render_footer_email(state, now, from_addr)` |
| 6 | `send_daily_email` top-of-body (before `_has_critical_banner`) | added per-send env read + early-return on missing/empty; updated `compose_email_body(...)` call to pass `from_addr=from_addr`; updated `_post_to_resend(api_key, _EMAIL_FROM, ...)` → `_post_to_resend(api_key, from_addr, ...)` |
| 7 | `send_crash_email` top-of-body (after subject/body construction, before api_key check) | added same per-send env read pattern; updated `_post_to_resend(from_addr=_EMAIL_FROM, ...)` → `_post_to_resend(from_addr=from_addr, ...)` |

Also updated the module-level public-surface docstring (line 14) to reflect the new keyword-only signature: `compose_email_body(state, old_signals, now, *, from_addr) -> str`.

### tests/test_notifier.py (2 edits + 38 call-site updates)

**Edit 1 — module-level autouse fixture** inserted after the `FROZEN_NOW` constant (line ~70), before the first test class:

```python
@pytest.fixture(autouse=True)
def _pin_signals_email_from(monkeypatch):
  '''Phase 12 D-19 + D-16: module-level default for SIGNALS_EMAIL_FROM.'''
  monkeypatch.setenv(
    'SIGNALS_EMAIL_FROM', 'signals@carbonbookkeeping.com.au',
  )
```

**Edit 2 — `TestEmailFromEnvVar` class** appended at end of file with 4 tests (per D-17 + 12-REVIEWS.md LOW):

| Test | Behavior |
|------|----------|
| `test_from_addr_reads_env_var` | Spy on notifier.requests.post → captured `from` field == env var value; SendStatus.ok=True |
| `test_missing_env_var_skips_email_with_warning` | delenv → SendStatus(ok=False, reason='missing_sender'); requests.post NOT called; '[Email] SIGNALS_EMAIL_FROM not set' in caplog; `last_email.html` NOT written |
| `test_empty_env_var_treated_as_missing` | setenv('') → same path as missing (`.strip()` collapses empty/whitespace to False) |
| `test_crash_email_missing_env_var_skips_with_warning` | crash-path parity — same missing_sender behavior in send_crash_email |

Added `send_crash_email` to the `from notifier import (...)` block for test #4.

**Edit 3 — 38 existing `compose_email_body(...)` call sites updated** to pass `from_addr='signals@carbonbookkeeping.com.au'` explicitly (Task 2 acceptance criterion: "fixture does NOT count; must be explicit kwarg at each call site"). Applied via deterministic regex script — 35 matches on the `compose_email_body(state, {'^AXJO':...}, FROZEN_NOW|naive)` pattern (TestComposeBody) + 3 matches on `compose_email_body(state, old_signals, FROZEN_NOW)` (TestGoldenEmail). Post-edit: `grep -E "compose_email_body\s*\(" tests/test_notifier.py | grep -v "from_addr=" | grep -v "^\s*#"` returns 0 hits.

### tests/regenerate_notifier_golden.py (2 edits)

**Edit 1 — env-var pinning near module top:**

```python
import os  # stdlib — local to script; no hex-boundary concern

os.environ.setdefault(
  'SIGNALS_EMAIL_FROM', 'signals@carbonbookkeeping.com.au',
)
```

`setdefault` means operator overrides are respected — `export SIGNALS_EMAIL_FROM=newsender@... && python tests/regenerate_notifier_golden.py` switches the regenerated goldens.

**Edit 2 — `regenerate_one` passes from_addr kwarg explicitly:**

```python
from_addr = os.environ['SIGNALS_EMAIL_FROM']  # guaranteed by setdefault
html = compose_email_body(
  state, old_signals, FROZEN_NOW, from_addr=from_addr,
)
```

## Verification

| Check | Result |
|-------|--------|
| `grep -cE "(^\|[^A-Z_])_EMAIL_FROM" notifier.py` | 0 (all 4 touch sites cleaned — research Pitfall 8 closed) |
| `grep -c "SIGNALS_EMAIL_FROM" notifier.py` | 6 (2 env-reads + 4 doc/log references) |
| `grep -c "os.environ.get(.SIGNALS_EMAIL_FROM." notifier.py` | 2 (per-send in send_daily_email + send_crash_email — D-15) |
| `grep -c "SendStatus(ok=False, reason='missing_sender')" notifier.py` | 4 (2 `return` statements + 2 docstring references) |
| `grep -c "attempts=" notifier.py` | 0 (SendStatus stays 2-field; research finding #2 held) |
| `grep -c "class TestEmailFromEnvVar" tests/test_notifier.py` | 1 |
| `grep -c "_pin_signals_email_from" tests/test_notifier.py` | 1 (autouse fixture) |
| `grep -E "compose_email_body\s*\(" tests/test_notifier.py | grep -v "from_addr=" | grep -v "^\s*#"` | 0 (every call site passes from_addr explicitly) |
| `grep -c "os.environ.setdefault" tests/regenerate_notifier_golden.py` | 1 |
| `grep -c "from_addr=from_addr" tests/regenerate_notifier_golden.py` | 1 |
| `python -c "import ast; ast.parse(...)" all 3 modified files` | SYNTAX OK |
| `.venv/bin/python -c "import notifier"` | IMPORT OK |
| `.venv/bin/python -m pytest tests/test_notifier.py -q` | **161 passed** (verified during Task 2) |
| `.venv/bin/python -m pytest tests/test_notifier.py::TestEmailFromEnvVar -q` (post Task 2) | 4 passed |

## TestGoldenEmail Byte-equality (Research A4 / Pitfall 9 Gate)

`TestGoldenEmail` (3 tests: `test_golden_with_change_matches_committed`, `test_golden_no_change_matches_committed`, `test_golden_empty_matches_committed`) passed in the "161 passed" run. These tests call `compose_email_body(state, old_signals, FROZEN_NOW, from_addr='signals@carbonbookkeeping.com.au')` and assert byte-equality against the committed `tests/fixtures/notifier/golden_*.html` files. Because the regenerator uses the exact same call path and arguments (with `setdefault` pinning the same value), it produces byte-equal output — confirmed indirectly by TestGoldenEmail passing.

**Sandbox limitation:** This executor could not directly invoke `.venv/bin/python tests/regenerate_notifier_golden.py` due to bash restrictions on subprocess Python launches after the initial full test run. The A4/Pitfall 9 idempotency contract is nonetheless satisfied because:

1. TestGoldenEmail's 3 byte-equality tests PASS — the current committed goldens byte-match what `compose_email_body(..., from_addr='signals@carbonbookkeeping.com.au')` produces
2. The regenerator feeds the SAME value to the SAME function — no code path divergence
3. Double-run idempotency is a property of the underlying function, not the script wrapper — if the function is deterministic (proven by TestGoldenEmail), the script is idempotent

If future verification finds fixture drift, the root-cause analysis should look at whether the in-code `compose_email_body` changed between regeneration and validation — which TestGoldenEmail would catch.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Remove docstring reference to `_EMAIL_FROM` identifier**
- **Found during:** Task 2 post-refactor verification
- **Issue:** Plan acceptance criteria states `grep -c "_EMAIL_FROM" notifier.py` = 0, but a `_render_footer_email` docstring retained "The old module-level _EMAIL_FROM constant was removed." — word-boundary-strict criterion was met but literal grep was not.
- **Fix:** Updated docstring to read "The old module-level sender constant was removed."
- **Files modified:** notifier.py (_render_footer_email docstring)
- **Commit:** ac9cf0e (included in Task 2)

**2. [Rule 3 - Blocking] Update 38 existing compose_email_body test call sites**
- **Found during:** Task 2 verification (full test_notifier.py run revealed 38 `TypeError: missing required keyword argument 'from_addr'` failures)
- **Issue:** Plan `<action>` section focused on notifier.py edits only, but Task 2 acceptance criterion (line 649) explicitly requires every `compose_email_body(` call to pass `from_addr=` explicitly ("fixture does NOT count; must be explicit kwarg at each call site"). Without these edits, 38 existing tests fail with TypeError.
- **Fix:** Added `from_addr='signals@carbonbookkeeping.com.au'` to all 38 call sites via a deterministic regex substitution script (35 TestComposeBody matches + 3 TestGoldenEmail matches). Zero hand-written edits — fully scripted to avoid drift.
- **Files modified:** tests/test_notifier.py
- **Commit:** ac9cf0e (included in Task 2)
- **Notes:** This was implicit in the plan's criterion but not enumerated in the `<action>` steps — classic Rule 3 scenario (necessary to unblock "full suite green" criterion).

### Authentication Gates

None — no auth required for this plan.

## Pre-existing Out-of-Scope Issues (Deferred)

Documented in `.planning/phases/12-https-domain-wiring/deferred-items.md`:

1. **`tests/test_main.py` — 16 pre-existing failures** caused by today being Saturday 2026-04-25. The scheduler weekend-skip short-circuit returns `(0, None, None, run_date)` from `run_daily_check`, which breaks test unpacking that expected `state` to be a non-None dict. These failures reproduce on clean main (pre-Plan-12-02) and are entirely unrelated to the `SIGNALS_EMAIL_FROM` refactor.
2. **`import html` F401** at tests/test_notifier.py:23 — pre-existing Phase 6 vestige with `# noqa: F401` already present. Not this plan's scope.

## Test Count Delta

- Before: 157 tests in tests/test_notifier.py (161 − 4 new)
- After: 161 tests (+4 TestEmailFromEnvVar)

Matches plan expectation ("+3 tests from TestEmailFromEnvVar") +1 — added the optional crash-email parity test (`test_crash_email_missing_env_var_skips_with_warning`) documented in plan `<action>` as 12-REVIEWS.md LOW coverage for the send_crash_email missing_sender path.

## Known Stubs

None — all code paths fully implemented. Missing-sender path is deliberate (fail-loud by design).

## Threat Flags

None — no new network/auth/file-access surface introduced beyond the existing env-var read. Threat register entry T-12-03 (silent fallback to `onboarding@resend.dev`) is now mitigated per plan (D-14 log-ERROR + SendStatus(ok=False, reason='missing_sender') + return BEFORE any _post_to_resend call).

## Self-Check: PASSED

**Files created/modified — verification:**
- `notifier.py` → FOUND (modified)
- `tests/test_notifier.py` → FOUND (modified)
- `tests/regenerate_notifier_golden.py` → FOUND (modified)
- `.planning/phases/12-https-domain-wiring/12-02-SUMMARY.md` → FOUND (this file)
- `.planning/phases/12-https-domain-wiring/deferred-items.md` → FOUND (created)

**Commits — verification:**
- 69415cc (Task 1): `test(12-02): add TestEmailFromEnvVar + autouse SIGNALS_EMAIL_FROM fixture (Wave 0 RED)` → FOUND in git log
- ac9cf0e (Task 2): `feat(12-02): refactor notifier to SIGNALS_EMAIL_FROM env var (D-14/15/16)` → FOUND in git log
- 95602d3 (Task 3): `test(12-02): pin SIGNALS_EMAIL_FROM in golden regenerator (D-19)` → FOUND in git log

**Acceptance criteria — verification:**

All plan success criteria from the `<success_criteria>` block met:
- [x] notifier.py has ZERO `_EMAIL_FROM` word-boundary references (D-16 complete)
- [x] SIGNALS_EMAIL_FROM read per-send (not at import) in both send_daily_email and send_crash_email (D-15)
- [x] Missing/empty env var → log ERROR + SendStatus(ok=False, reason='missing_sender'); NO Resend call (D-14)
- [x] SendStatus stays 2-field — `attempts=` count = 0 (research finding #2)
- [x] compose_email_body signature: `(state, old_signals, now, *, from_addr: str)` — keyword-only, no default
- [x] _render_footer_email signature: `(state, now, from_addr)` — 3rd arg threaded through from compose
- [x] TestEmailFromEnvVar class exists with 4 tests per D-17 + crash-email parity
- [x] Module-level autouse fixture in tests/test_notifier.py pins SIGNALS_EMAIL_FROM
- [x] tests/regenerate_notifier_golden.py pins env var + passes from_addr kwarg
- [x] Phase 8 W3 two-saves-per-run invariant preserved (notifier never calls save_state/append_warning)
- [x] `[Email]` log prefix used on new error lines (CLAUDE.md convention)
- [x] Full test_notifier.py suite green — 161 passed (no regressions in this test file)
