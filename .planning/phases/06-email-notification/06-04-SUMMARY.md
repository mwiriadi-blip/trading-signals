---
phase: 06-email-notification
plan: 4
subsystem: email-notification
tags: [gap-closure, docstring, cosmetic, wr-01, wr-02, golden-snapshot]

requires:
  - phase: 06-email-notification
    provides: 06-03 (Wave 2 PHASE GATE — 515/515 tests, 6 byte-stable goldens, regenerator double-run idempotent)
  - phase: 06-email-notification
    provides: 06-REVIEW.md (WR-01 docstring drift + WR-02 subject double-space findings)

provides:
  - main.run_daily_check docstring accurately describes exception-propagation failure model + frames None-guard as defense-in-depth (WR-01 closed)
  - notifier.compose_email_subject emits literal 'first run' label when date_iso resolves empty — no more double-space between emoji and em-dash (WR-02 closed)
  - tests/fixtures/notifier/golden_empty_subject.txt regenerated (55 → 64 bytes) with 'first run' token
  - tests/test_notifier.py::TestComposeSubject gains 1 new pinning test: test_subject_first_run_label_when_no_date_iso (byte-exact + double-space absence)
  - Regenerator double-run idempotency preserved across ALL 6 goldens (PHASE GATE held)

affects:
  - Phase 6 milestone closure — cleanly clears the 2 non-blocking code-review warnings before /gsd-verify-work 6 final sign-off

tech-stack:
  added: []
  patterns:
    - WR-01: docstring contract now aligned with runtime — exceptions propagate to main()'s typed-exception boundary; None-guard framed as defense-in-depth (not active today, preserved for future non-exception failure returns)
    - WR-02: inline string-literal 'first run' label — self-documenting for the operator's very first email; preserves D-04 subject template shape (no new constant, no API change, no `now` param added)

key-files:
  created:
    - .planning/phases/06-email-notification/06-04-SUMMARY.md
  modified:
    - main.py (docstring reword + main() dispatch-ladder comment reword — net +4 LoC)
    - notifier.py (6-line date_label branch in compose_email_subject — net +7 LoC)
    - tests/test_notifier.py (new pinning test in TestComposeSubject — net +31 LoC)
    - tests/fixtures/notifier/golden_empty_subject.txt (regenerated; 55 → 64 bytes)

key-decisions:
  - "WR-01 fix is docstring-only — no return statement added/removed in run_daily_check; grep -c 'return 0, state, old_signals, run_date' main.py stays at exactly 2."
  - "WR-01 scope widened to fix a second stale comment in main() dispatch ladder (lines 763-768) that repeated the same false '(rc, None, None, None)' claim — the plan's grep gate `grep -c '(rc, None, None, None)' main.py = 0` forced this site too. Documented as deviation #1 (Rule 2 — missing critical: stale contract documentation at a sibling site)."
  - "WR-02 fix uses inline `date_label = date_iso if date_iso else 'first run'` — no module-level constant, no `now` parameter added to compose_email_subject. API stable; hex boundary untouched."
  - "Regenerator (tests/regenerate_notifier_golden.py) is NOT modified — it is idempotent already, and the only behaviour change is that it now writes 64 bytes to golden_empty_subject.txt instead of 55."

patterns-established:
  - "Gap-closure plans scoped to cosmetic warnings: 2 tasks max, zero scope creep, same-day landing, PHASE GATE preserved. Future phases can use this shape for review-debt cleanups."

requirements-completed: []

duration: ~5 min
completed: 2026-04-22
---

# Phase 6 Plan 4: Gap Closure (WR-01 + WR-02) Summary

**Docstring reworded to reflect exception-propagation failure model (WR-01); subject template gains 'first run' label fallback that kills the first-run double-space between emoji and em-dash (WR-02); 1 new pinning test; 1 golden regenerated; 5 other goldens byte-identical; Phase 6 PHASE GATE held.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-04-22T21:23:29Z
- **Completed:** 2026-04-22T21:26:18Z
- **Tasks:** 2 (WR-01 + WR-02)
- **Files modified:** 4 (main.py, notifier.py, tests/test_notifier.py, tests/fixtures/notifier/golden_empty_subject.txt)
- **Commits:** 2 (one per task)

## Accomplishments

- **WR-01 closed.** The `run_daily_check` docstring no longer claims a `(rc, None, None, None)` failure return path that does not exist. Replacement text cites `main()`'s typed-exception boundary + frames the None-guard at `main.py:765-770` as defense-in-depth. A second occurrence of the same stale claim inside the main() dispatch-ladder comment was also reworded — caught by the plan's grep gate.
- **WR-02 closed.** `notifier.compose_email_subject` now emits `'first run'` as a self-documenting label when `date_iso` resolves empty (first run — `last_run=null` AND no dict-shape `as_of_run` on any instrument). Subject is now `📊 first run — SPI200 FLAT, AUDUSD FLAT — Equity $100,000` — no double-space anywhere.
- **New pinning test.** `TestComposeSubject::test_subject_first_run_label_when_no_date_iso` asserts the exact byte output + belt-and-braces that `'📊  —'` never appears. TDD RED → GREEN cycle confirmed (captured in commit `9ede078`).
- **Golden regenerated deterministically.** `golden_empty_subject.txt` went from 55 → 64 bytes (swap of empty slot for `'first run'`). Other 5 goldens (3 HTML bodies + 2 other subject .txt files) are byte-identical to pre-gap-closure commit — verified via sha256sum against the baseline captured at plan start.
- **PHASE GATE preserved.** `.venv/bin/python tests/regenerate_notifier_golden.py && git diff --exit-code tests/fixtures/notifier/` returns exit 0 after the task-2 commit. 3 consecutive regenerator runs during plan execution all produced identical sha256 for `golden_empty_subject.txt` (`1c06f4ef233fe834aee485bc11b8d8df0c4175d0c122bf7f31ee10ae2894de3e`).

## Task Commits

Each task was committed atomically:

1. **Task 1: WR-01 — reword run_daily_check docstring** — `9832a28` (docs)
2. **Task 2: WR-02 — 'first run' label + new pinning test + regenerated golden** — `9ede078` (fix; TDD RED/GREEN rolled into single commit alongside the regenerated golden — new test transitioned from RED to GREEN inside the task before commit, verified by manual pytest run showing the expected AssertionError pre-patch)

_Note: Task 2 is fix-paced TDD — the RED phase was demonstrated via a direct pytest run between writing the test and patching `compose_email_subject`; the single `fix(06-04): ...` commit records test + code + golden together because the trio must land atomically to keep the suite green on every commit._

## Files Created/Modified

- `main.py` — docstring reword at `run_daily_check` (L437-448) + main() dispatch-ladder comment reword (L763-768); no return statement or behaviour change.
- `notifier.py` — 6-line `date_label` branch in `compose_email_subject` (~L338-352); f-string now references `date_label` instead of `date_iso`; no new imports, no new module-level constants, no API change.
- `tests/test_notifier.py` — new method `test_subject_first_run_label_when_no_date_iso` in `TestComposeSubject` (inserted before `class TestDetectSignalChanges`); 31 lines including docstring, byte-exact equality assertion, and belt-and-braces double-space absence check.
- `tests/fixtures/notifier/golden_empty_subject.txt` — regenerated via `tests/regenerate_notifier_golden.py`; bytes `📊 first run — SPI200 FLAT, AUDUSD FLAT — Equity $100,000\n` (64 bytes UTF-8, single trailing LF).
- `.planning/phases/06-email-notification/06-04-SUMMARY.md` — this file.

## Decisions Made

- **Inline literal, not module constant.** Per plan constraint, `'first run'` lives inline in `compose_email_subject` — no module-level constant, to make the edit self-contained and prevent accidental reuse.
- **No API change to `compose_email_subject`.** The alternative fix (adding a `now` parameter so the subject could fall back to the runtime clock) was explicitly rejected in the plan's `gap_closure_scope`. Signature stays `(state, old_signals, is_test=False) -> str`.
- **WR-02 is subject-only.** `compose_email_body` is untouched. Confirmed by the 3 HTML body goldens remaining byte-identical to the pre-gap-closure commit.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 — Missing Critical: stale contract documentation at sibling site] Extended WR-01 docstring reword to also fix a duplicate stale comment in main() dispatch ladder**

- **Found during:** Task 1 (WR-01 docstring reword)
- **Issue:** After replacing the `run_daily_check` docstring's false `(rc, None, None, None)` claim, the plan's grep gate `grep -c "(rc, None, None, None)" main.py` still returned 1 because the same claim was repeated verbatim in the `main()` dispatch-ladder comment (L765-768): `# run_daily_check may return (rc, None, None, None) on failure paths — / # only dispatch email when all three post-run values are populated.` If left in place, the WR-01 code-review finding would be only half-fixed — the stale contract still documented at the *call site* would mislead future readers in exactly the same way as the docstring did.
- **Fix:** Reworded the main() comment to match the new docstring framing: `# Fix 10 None-guard is / # defense-in-depth for any future non-exception failure return from / # run_daily_check — today all failure paths propagate exceptions to / # the typed-exception boundary below, so the guard is not reachable.` No code change — comment only.
- **Files modified:** `main.py` (comment at L763-768 — in addition to the docstring at L437-448)
- **Verification:** `grep -c "(rc, None, None, None)" main.py` returns 0 (target 0); `grep -c "defense-in-depth" main.py` returns 2 (target ≥1) — the string now appears in both the docstring and the call-site comment, accurately telling the same story in both places.
- **Committed in:** `9832a28` (part of Task 1 commit)

**2. [Rule 2 — Missing Critical: grep string must appear on a single line] Reflowed the docstring so `defense-in-depth` is not split across a line break**

- **Found during:** Task 1 grep verification
- **Issue:** The plan's literal replacement text in `06-REVIEW.md:72-78` had `defense-in-` / `depth` broken across two lines (`\n` between the hyphen and `depth`). Pasting verbatim caused `grep -c "defense-in-depth" main.py` to return 0 (grep matches on a single line by default), failing the acceptance criterion `grep -c "defense-in-depth" main.py ≥ 1`.
- **Fix:** Reflowed the 4th line of the new docstring paragraph so `defense-in-depth` stays on one line (`  depth for any future non-exception failure return.` → `  defense-in-depth for any future non-exception failure return.`). Semantics unchanged; PEP 8 line length still OK.
- **Files modified:** `main.py` (docstring at L447 region)
- **Verification:** `grep -c "defense-in-depth" main.py` returns 2 (target ≥1); ruff clean.
- **Committed in:** `9832a28` (part of Task 1 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 2 — missing critical: both needed to satisfy plan-defined grep gates; one at a sibling code site, one for text flow).
**Impact on plan:** Both deviations were forced by the plan's own grep-countable acceptance criteria; neither expanded scope. Deviation #1 actually strengthens the WR-01 close — the same stale contract is no longer documented anywhere in main.py.

## Issues Encountered

- **No `.venv` inside worktree.** The plan's verification commands reference `.venv/bin/pytest`, but the worktree copy does not include the `.venv` directory. Worked around by using the absolute path to the repo's `.venv`: `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/.venv/bin/pytest`. Python 3.11.8, pytest 8.3.3, ruff 0.6.9 — all as expected. No impact on verification outcome.

## Verification Results

| Gate | Result |
|------|--------|
| Full suite `.venv/bin/pytest tests/ -q` | **516 passed** (was 515 + 1 new pinning test) |
| Ruff `.venv/bin/ruff check .` | **All checks passed!** |
| PHASE GATE: regenerator double-run | **`git diff --exit-code tests/fixtures/notifier/` exit 0** (IDEMPOTENT) |
| WR-01 `grep -c "(rc, None, None, None)" main.py` | **0** (target 0) |
| WR-01 `grep -c "defense-in-depth" main.py` | **2** (target ≥1) |
| WR-01 `grep -c "main()'s typed-exception" main.py` | **1** (target ≥1) |
| WR-01 `grep -c "propagate up" main.py` | **1** (target ≥1) |
| WR-01 `grep -c "return 0, state, old_signals, run_date" main.py` | **2** (target exactly 2 — unchanged) |
| WR-01 `grep -c "def _force_email_stub" main.py` | **0** (target 0 — stub deletion from Wave 2 preserved) |
| WR-02 `grep -c "📊 first run — SPI200 FLAT" tests/fixtures/notifier/golden_empty_subject.txt` | **1** (target 1) |
| WR-02 `grep -c "📊  —" tests/fixtures/notifier/golden_empty_subject.txt` | **0** (target 0) |
| WR-02 `grep -c "date_label = date_iso if date_iso else 'first run'" notifier.py` | **1** (target 1) |
| Non-empty subject goldens byte-identical | **VERIFIED** via sha256sum — `golden_with_change_subject.txt` (`405e980f…`) + `golden_no_change_subject.txt` (`03a2fef1…`) unchanged; git diff --stat lists ONLY `golden_empty_subject.txt` |
| 3 HTML body goldens byte-identical | **VERIFIED** via sha256sum — `golden_with_change.html` (`f66f69e9…`) + `golden_no_change.html` (`485841ed…`) + `golden_empty.html` (`d7f2ca61…`) unchanged |
| Phase 5 dashboard regression guard `tests/test_dashboard.py` | **70 passed** (no regression) |
| Hex boundary `test_notifier_no_forbidden_imports` | **green** (no new imports in notifier.py) |
| `TestComposeSubject` (7 methods, 6 pre-existing + 1 new) | **7/7 green** |
| `TestGoldenEmail` (15 methods including 3 subject byte-equal against regenerated golden) | **15/15 green** |
| NOTF-covered tests (`TestResendPost` + `TestSendDispatch` + `TestAtomicWriteHtml` + `TestEmailNeverCrash`) | **29/29 green** |
| CLI-01/03 contracts (`test_test_flag_sends_test_prefixed_email_no_state_mutation` + `test_force_email_sends_live_email` + `TestRunDailyCheckTupleReturn`) | **4/4 green** |
| New pinning test `test_subject_first_run_label_when_no_date_iso` | **PASS** (TDD RED → GREEN confirmed; RED failure message: `AssertionError: WR-02: empty-state subject must use "first run" label ... got: '📊  — SPI200 FLAT, AUDUSD FLAT — Equity $100,000'`) |

## Threat Model Coverage

Per the plan's `<threat_model>`, no new mitigations required and no mitigations weakened. The cosmetic gap closure adds:

- **T-06-07 (Info Disclosure — docstring edit leaks implementation detail):** accept. New docstring text describes public behaviour visible to any reader of the open-source repo; no secrets, PII, or security-attack-surface details.
- **T-06-08 (Tampering — 'first run' literal confused with a date by downstream parsers):** accept. Subject line is a display surface only; no downstream code parses it for dates. Inbox clients render the subject as a string — no semantic interpretation.

Wave 2 `[REDACTED]` redaction discipline (3 matches in notifier.py) untouched; `html.escape` leaf discipline (55 sites) untouched — `compose_email_body` not modified.

## Auth Gates Encountered

**None.** No Resend HTTPS calls during verification — all `send_daily_email` path tests use monkeypatched `requests.post`. No `RESEND_API_KEY` needed.

## Requirements Traceability

No requirements are closed by this gap-closure plan (`requirements_completed: []` in frontmatter). Phase 6 requirements NOTF-01..09 + CLI-01/03 Phase 6 slices were all marked complete in `06-03-SUMMARY.md` and are unaffected by this close-out.

## Hex Boundary Confirmation

- `notifier.py` imports unchanged — `test_notifier_no_forbidden_imports` green.
- `main.py` dispatch structure unchanged — the reworded docstring/comment contain no code changes.
- `signal_engine.py` + `sizing_engine.py` + `system_params.py` untouched — hex boundaries held.

## Next Phase Readiness

- Phase 6 code review debt cleared — both WR-01 and WR-02 closed with grep-countable evidence.
- Phase 6 PHASE GATE still green (regenerator idempotent across all 6 goldens).
- Ready for `/gsd-verify-work 6` final sign-off, then Phase 6 milestone closure.
- Blocks: none.

## Self-Check: PASSED

- [x] `main.py:437-448` docstring no longer claims `(rc, None, None, None)` failure return; texually cites `main()`'s typed-exception boundary + `defense-in-depth` framing
- [x] `main.py:763-768` dispatch-ladder comment aligned with new framing (deviation #1)
- [x] `notifier.py::compose_email_subject` emits `'first run'` when `date_iso` resolves empty
- [x] `tests/fixtures/notifier/golden_empty_subject.txt` = `📊 first run — SPI200 FLAT, AUDUSD FLAT — Equity $100,000\n` (64 bytes)
- [x] `tests/test_notifier.py::TestComposeSubject::test_subject_first_run_label_when_no_date_iso` present + passing
- [x] Other 5 goldens byte-identical to pre-gap-closure commit (sha256 verified)
- [x] Regenerator double-run idempotent across all 6 goldens (`git diff --exit-code` exit 0)
- [x] Full suite 516 passed; ruff clean
- [x] Phase 5 dashboard unaffected (70 passed)
- [x] Hex boundary green (no new imports in notifier.py)
- [x] `compose_email_body` untouched; `compose_email_subject` signature unchanged
- [x] 2 commits on worktree (`9832a28`, `9ede078`) verified via `git log`

### Artifact existence verification

```
main.py — FOUND (792 LoC)
notifier.py — FOUND (1223 LoC)
tests/test_notifier.py — FOUND (1238 LoC)
tests/fixtures/notifier/golden_empty_subject.txt — FOUND (64 bytes)
.planning/phases/06-email-notification/06-04-SUMMARY.md — FOUND (this file)
```

### Commit existence verification

```
9832a28 — FOUND (Task 1 WR-01)
9ede078 — FOUND (Task 2 WR-02)
```

---
*Phase: 06-email-notification*
*Plan: 4 (gap closure — WR-01 + WR-02)*
*Completed: 2026-04-22*
