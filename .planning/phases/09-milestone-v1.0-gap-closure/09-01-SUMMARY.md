---
phase: 09-milestone-v1.0-gap-closure
plan: 01
subsystem: milestone-closure
tags: [documentation, gha, traceability, milestone-closure]
dependency_graph:
  requires:
    - .planning/v1.0-MILESTONE-AUDIT.md (source of gap evidence)
    - .planning/REQUIREMENTS.md (target of reconciliation)
    - .github/workflows/daily.yml (target of timeout cap)
    - tests/test_scheduler.py::TestGHAWorkflow (target for regression guard)
  provides:
    - 80/80 VERIFIED requirement traceability (ready for milestone archive)
    - 10-minute job-level runaway-run cap on the daily GHA workflow
    - Regression guard locking the cap (future deletes fail fast)
  affects:
    - v1.0 milestone status (tech_debt → ready_to_archive)
    - Phase 7 IN-01 carry-over (closed)
tech_stack:
  added: []
  patterns:
    - pytest + PyYAML static validation (already established in Phase 7)
    - Spec-text amendment to match test-locked design (operator decision at plan time)
key_files:
  created:
    - .planning/phases/09-milestone-v1.0-gap-closure/09-01-SUMMARY.md
    - .planning/phases/09-milestone-v1.0-gap-closure/deferred-items.md
  modified:
    - .planning/REQUIREMENTS.md (+102 / -101 lines — 37 checkbox flips + 59 status flips + ERR-01 rewrite + SIG-05..08 rewrites + coverage header + amendment footer)
    - .github/workflows/daily.yml (+1 line — `timeout-minutes: 10` at job level)
    - tests/test_scheduler.py (+22 lines — `test_daily_workflow_has_timeout_minutes` inside TestGHAWorkflow)
decisions:
  - ERR-01 spec amended (not email-path added) — matches already-shipped + already-test-locked behaviour; operator chose amend over add at plan time
  - Footer date uses today's date (2026-04-23) not the draft's 2026-04-24 placeholder — AC grep adjusted atomically
metrics:
  duration: ~4 minutes (doc edits + 1 YAML line + 1 test method + verification)
  completed_date: 2026-04-23
  tasks: 2
  files_modified: 3
  files_created: 2
  tests_before: 661
  tests_after: 662
---

# Phase 9 Plan 01: Milestone v1.0 Gap Closure Summary

**One-liner:** Closed three v1.0 tech-debt items — ERR-01 spec reconciled with the test-locked no-email design, all 80 traceability rows flipped to VERIFIED/Complete, and GHA workflow capped at 10-minute runaway-run timeout with regression guard.

## Task Breakdown

### Task 1 — REQUIREMENTS.md reconciliation (commit f3f6e3c)

Single file touched: `.planning/REQUIREMENTS.md` (+102 / -101 lines).

**Change A — ERR-01 row rewrite.** Replaced the original text ("yfinance failure after 3 retries sends an error email and exits gracefully") with the amended no-email spec that matches the implemented path (`except (DataFetchError, ShortFrameError): return 2` with no crash-email call) and the existing `tests/test_main.py::TestCrashEmailBoundary::test_data_fetch_error_does_not_fire_crash_email` guard. Cross-reference to the guard test embedded in the row text.

**Change B — 37 checkbox flips.** Flipped all remaining `- [ ]` to `- [x]` via a single `replace_all`:

| Category | Flipped |
|----------|---------|
| DATA-01..06 | 6 |
| STATE-01..07 | 7 |
| NOTF-01..09 | 9 |
| DASH-01..09 | 9 |
| CLI-01..04 | 4 |
| ERR-01 (via Change A) + ERR-06 | 2 |
| **Total** | **37** |

Net: 43 pre-existing `- [x]` + 37 flipped = **80/80 checked**.

**Change C — 59 traceability-table status flips.** Every `| Pending |` row replaced with `| Complete |` (bulk replace). Two rows got richer descriptors:
- ERR-01: `Complete (spec amended in Phase 9 to match \`test_data_fetch_error_does_not_fire_crash_email\` lock)`
- SIG-05..08: `Complete (Plan 01-03 goldens + Plan 01-05 production SUT verified @ 1e-9)` (replaced the prior "Goldens ready; production SUT pending" descriptor since Phase 1 shipped 2026-04-20)

Net: Zero `| Pending |` rows remain.

**Change D — Coverage header + footer.** Line 298 updated from `- Mapped to phases: 80` to `- Mapped to phases: 80/80, Verified: 80/80`. Appended amendment footer line dated 2026-04-23 documenting the Phase 9 reconciliation.

### Task 2 — GHA timeout + regression test (commit 2e3d314)

**Edit A — `.github/workflows/daily.yml`.** Inserted `    timeout-minutes: 10` (4-space indent) between `runs-on: ubuntu-latest` and `steps:` under `jobs.daily`. PyYAML parses the value as int 10 (not string). Caps runaway runs at 10 minutes — well above the ~2 min happy-path runtime and the ~30s Phase 8 D-07 crash-email retry budget.

**Edit B — `tests/test_scheduler.py`.** Appended `test_daily_workflow_has_timeout_minutes` inside `TestGHAWorkflow` (placed after `test_no_ssh_or_pat_token_references`, before `class TestDeployDocs`). Two independent assertions:
1. `'timeout-minutes' in daily` — fails if the key is removed.
2. `daily['timeout-minutes'] == 10` — fails if the value is changed.

TestGHAWorkflow went from 12 → 13 tests. Full `tests/test_scheduler.py` green (39 passed).

## Files Changed

| File | Delta | Purpose |
|------|-------|---------|
| `.planning/REQUIREMENTS.md` | +102 / -101 | ERR-01 rewrite + 37 checkbox flips + 59 status flips + header + footer |
| `.github/workflows/daily.yml` | +1 | Job-level `timeout-minutes: 10` |
| `tests/test_scheduler.py` | +22 | New regression guard method (22 lines including 4-line docstring) |
| `.planning/phases/09-milestone-v1.0-gap-closure/deferred-items.md` | new | Pre-existing ruff F401 warnings in notifier.py logged as out-of-scope debt |
| `.planning/phases/09-milestone-v1.0-gap-closure/09-01-SUMMARY.md` | new | This file |

## Grep / Test Evidence

```
=== Task 1 ACs ===
AC1 old-err01 (expect 0):         0   ✓
AC2 new-err01 (expect >=1):       1   ✓
AC3 guard-ref (expect >=1):       2   ✓  (bullet + traceability row both cross-reference)
AC4 unchecked (expect 0):         0   ✓
AC5 checked (expect 80):          80  ✓
AC6 pending (expect 0):           0   ✓
AC7 header (expect 1):            1   ✓
AC8 amend (expect 1):             1   ✓

=== Task 2 ACs ===
AC1 timeout count (expect 1):     1   ✓
AC3 test method (expect 1):       1   ✓
AC4 new test runs:                1 passed in 0.60s           ✓
AC5 TestGHAWorkflow regression:   13 passed in 0.39s          ✓
AC6 full test_scheduler.py:       39 passed in 0.52s          ✓
AC7 locked-guard test:            1 passed in 0.39s           ✓

=== Final gates ===
Locked-guard diff (expect empty): OK: tests/test_main.py unchanged from HEAD   ✓
Full suite: 662 passed in 93.86s                                               ✓
```

Before/after test count: **661 → 662** (+1, the new regression guard).

## Deviations from Plan

**1. [Rule 3 - Doc date] Footer date 2026-04-23 instead of draft's 2026-04-24**
- **Found during:** Task 1 Change D
- **Issue:** Plan draft line used `2026-04-24` but executor context explicitly said "use today's actual date when executing; if you run today as 2026-04-23, use that. Update the AC8 grep string atomically."
- **Fix:** Used `2026-04-23` in the footer line and adjusted the Task 1 AC8 grep to match (`Amended 2026-04-23: Phase 9 gap closure`). Behaviour-neutral.
- **Files modified:** `.planning/REQUIREMENTS.md`
- **Commit:** f3f6e3c

No other deviations. Core logic, test scope, and commit shape all match the plan exactly.

## Deferred Issues (out of scope)

Pre-existing ruff F401 unused-import warnings in `notifier.py` (19 errors, 17 auto-fixable). Confirmed via `git stash` comparison that these predate Phase 9 — likely introduced during Phase 8 `CONF-02` refactor when `FALLBACK_CONTRACT_SPECS` replaced direct constant reads. Logged to `.planning/phases/09-milestone-v1.0-gap-closure/deferred-items.md`. Fix path: a tiny `chore(quick)` task to run `ruff check --fix notifier.py`. Zero behaviour impact (F401 = unused imports only).

## Threat Model Verification

Plan 09-01 `<threat_model>` dispositions:

| Threat ID | Category | Disposition | Status |
|-----------|----------|-------------|--------|
| T-09-01 | D (DoS) on daily.yml | **mitigate** | Mitigated — `timeout-minutes: 10` caps GHA minute exhaustion. Regression guard locks it. |
| T-09-02 | I (Info Disclosure) on ERR-01 spec | **accept** | Accepted — no new disclosure; behaviour was already observable. |
| T-09-03 | T (Tampering) on checkbox flips | **accept** | Accepted — all 80 boxes backed by VERIFIED audit + SUMMARY evidence. |
| T-09-04 | R (Repudiation) on footer | **mitigate** | Mitigated — dated amendment footer + per-task commits give dual audit trail. |
| T-09-05 | E (Elevation) on GHA permissions | **accept** | Accepted — `permissions:` block untouched (least-privilege preserved). |
| T-09-06 | S (Spoofing) | **accept** | Accepted — no auth surface added. |

Net security posture: **improved** (T-09-01 mitigation added; all others no-change accepts).

## Success Criteria

All 6 plan success criteria met:

1. ✓ REQUIREMENTS.md ERR-01 amended + 80/80 `- [x]` + 0 `| Pending |` + header = `Mapped to phases: 80/80, Verified: 80/80`.
2. ✓ `.github/workflows/daily.yml` has `timeout-minutes: 10` at job level, parseable as int 10.
3. ✓ `test_daily_workflow_has_timeout_minutes` exists and passes; full `TestGHAWorkflow` + `test_scheduler.py` green; locked guard unchanged + green.
4. ✓ No changes to main.py, notifier.py, state_manager.py, signal_engine.py, sizing_engine.py, dashboard.py, data_fetcher.py, system_params.py, or any existing test method.
5. ✓ Full `pytest -x -q` green (662 passed). Ruff clean on files modified by Phase 9 (pre-existing `notifier.py` F401s deferred).
6. ✓ Commits follow CLAUDE.md style: `docs(09-01): reconcile ERR-01 spec text + sync traceability to 80/80 verified` and `chore(09-01): add GHA timeout-minutes 10 + regression test`.

## Commits

| Commit | Message | Files |
|--------|---------|-------|
| f3f6e3c | docs(09-01): reconcile ERR-01 spec text + sync traceability to 80/80 verified | `.planning/REQUIREMENTS.md` |
| 2e3d314 | chore(09-01): add GHA timeout-minutes 10 + regression test | `.github/workflows/daily.yml`, `tests/test_scheduler.py` |

## Next Steps

- Run `/gsd-verify-work 9` to close Phase 9.
- v1.0-MILESTONE-AUDIT.md §Requirements Coverage now reads 80/80 VERIFIED (was 79/80 + 1 PARTIAL); milestone moves from `tech_debt` → `ready_to_archive`.
- Phase 7 IN-01 carry-over item closed.
- Follow-up nit (optional): small `chore(quick)` task to clean up pre-existing `notifier.py` F401 warnings (see `deferred-items.md`).

## Self-Check: PASSED

Files created:
- `.planning/phases/09-milestone-v1.0-gap-closure/09-01-SUMMARY.md` — FOUND
- `.planning/phases/09-milestone-v1.0-gap-closure/deferred-items.md` — FOUND

Files modified:
- `.planning/REQUIREMENTS.md` — git log confirms f3f6e3c
- `.github/workflows/daily.yml` — git log confirms 2e3d314
- `tests/test_scheduler.py` — git log confirms 2e3d314

Commits exist:
- f3f6e3c — FOUND on worktree-agent-ac589bb4
- 2e3d314 — FOUND on worktree-agent-ac589bb4

Locked-behaviour guard (`tests/test_main.py`): `git diff --exit-code HEAD -- tests/test_main.py` returns zero diff — UNCHANGED.

Full test suite: 662 passed, 0 failed.
