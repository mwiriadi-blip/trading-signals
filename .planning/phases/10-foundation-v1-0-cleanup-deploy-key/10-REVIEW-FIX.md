---
phase: 10-foundation-v1-0-cleanup-deploy-key
fix_scope: critical_warning
findings_in_scope: 1
fixed: 1
skipped: 3
iteration: 1
status: all_fixed
completed: 2026-04-24
---

# Phase 10 Code Review Fix Report

## Summary

Applied the single warning-level finding from 10-REVIEW.md (WR-01). The three info-level findings (IN-01/02/03) are explicitly out of scope since no `--all` flag was passed — they are documented as optional cleanups for follow-up.

## Fixed

### WR-01 — `_push_state_to_git` timeout and generic-exception branches now covered

**Status:** fixed
**Fix commit:** `528b5a2` — test(10): fix WR-01 — cover TimeoutExpired + generic-Exception branches
**Files modified:** `tests/test_main.py` (+230 lines, 6 new test methods in `TestPushStateToGit`)

**Tests added:**
| Test name | Branch covered |
|-----------|----------------|
| `test_diff_timeout_logs_and_appends_warning` | `main.py:255-267` diff timeout |
| `test_diff_unexpected_exception_logs_and_appends_warning` | `main.py:268-281` diff generic exception |
| `test_commit_timeout_logs_and_appends_warning` | `main.py:318-330` commit timeout |
| `test_commit_unexpected_exception_logs_and_appends_warning` | `main.py:331-344` commit generic exception |
| `test_push_timeout_logs_and_appends_warning` | `main.py:373-384` push timeout |
| `test_push_unexpected_exception_logs_and_appends_warning` | `main.py:385-397` push generic exception |

**Assertions per test (representative):**
- Distinct `[State]`-prefixed log verb for this subcommand × error-class (e.g., `'[State] git push subprocess timeout'`)
- Exception class name appears in the warning message written via `state_manager.append_warning`
- Short-circuit behavior: diff-timeout must not reach commit/push; commit-timeout must not reach push
- `source='state_pusher'` on every `append_warning` call

**Verification:**
- `pytest tests/test_main.py::TestPushStateToGit -q` → 12 passed in 0.48s (6 original + 6 new)
- `pytest -x -q` full suite → 803 passed in 93.76s (+6 from baseline 797; no regression on any other test)

## Skipped (out of scope — no `--all` flag)

### IN-01 — `_handle_reset` could collapse two sites into `reset_state(initial_account=...)`
**Status:** skipped (info-level; intentional defense-in-depth per 10-CONTEXT.md D-01+D-02; Codex's earlier replan suggestion was explicitly rejected in reviews-mode — skipping here is consistent with that decision)

### IN-02 — Local `import subprocess` inside outer try raises `NameError` in TimeoutExpired except clause if import itself fails
**Status:** skipped (info-level; stdlib `subprocess` essentially cannot fail to import; hardening would diverge from the `_send_email_never_crash` project convention for no real-world benefit)

### IN-03 — Fresh-droplet precondition: `state.json` must be `git add -f`'d before first run
**Status:** skipped (info-level docs nit; Phase 11 `deploy.sh` is the canonical place to enforce this precondition; helper docstring change would duplicate that guarantee)

## Iteration Summary

- Iterations: 1 (single pass; no `--auto` flag)
- Scope: critical + warning (no `--all` flag)
- Final status: **all_fixed** (1/1 warning fixed; 3/3 info deferred by scope)

## Next Steps

- `/gsd-code-review 10` — optional re-review to confirm no new issues surfaced by the added tests (unlikely; tests are pure additions with no production-code changes)
- `/gsd-ship 10` — push Phase 10 work to origin/main, open PR
- Operator follow-up: promote UAT Tests 7 & 8 to `pass` post-ship after deploy-key + 2-weekday observation (tracked in 10-UAT.md §Blocked and 10-VALIDATION.md §Manual-Only)
