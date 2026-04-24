# Phase 12 Deferred Items

Pre-existing issues found during Plan 12-02 execution that are OUT OF SCOPE
for this plan. Documented per executor scope-boundary rule
(@$HOME/.claude/get-shit-done/references/executor-examples.md).

## Pre-existing test failure (clock-drift)

**Test:** `tests/test_main.py::TestCLI::test_force_email_sends_live_email`

**Failure:** `--force-email` path skips on weekends (today = Sat 2026-04-25):

```
INFO  main:main.py:1043 [Sched] weekend skip 2026-04-25 (weekday=5) — no fetch, no state mutation
assert 0 == 1  # sent list is empty because weekend-skip short-circuits
```

**Pre-existing check:** `git stash && pytest -q` reproduces the SAME failure
without any Plan 12-02 changes — confirmed at commit `69415cc` (Task 1 commit).
The test apparently relies on a clock assumption that was valid when the
test was written but drifts on weekends.

**Scope:** Completely unrelated to `SIGNALS_EMAIL_FROM` refactor (touches
scheduler weekend logic, not notifier.py or email paths). Existing on
main before this plan started.

**Disposition:** Log and move on. Should be addressed by a future
`/gsd:quick` or `/gsd:debug` cycle — not part of Phase 12.

## Pre-existing F401 in `test_notifier.py`

`import html  # noqa: F401` at line 23 was present before Plan 12-02
(Phase 6 vestige). Left in place — not this plan's scope.
