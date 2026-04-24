---
phase: 10-foundation-v1-0-cleanup-deploy-key
plan: 02
subsystem: testing
tags: [ruff, lint, f401, regression-guard, ci-guard, chore, subprocess, pytest]

# Dependency graph
requires:
  - phase: 06-notifier
    provides: notifier.py module + system_params import block that accumulated unused imports during pre-Phase-8 refactoring
  - phase: 09-milestone-v1.0-gap-closure
    provides: deferred-items baseline (19 F401 flagged, later confirmed as 4 on 2026-04-24 via live ruff)
provides:
  - notifier.py ruff-clean (zero warnings of ANY category, not just F401)
  - test_ruff_clean_notifier CI guard (PRIMARY gate on returncode == 0; SECONDARY diagnostic on F401 count)
  - test_ruff_clean_notifier_detects_f401_regression sensitivity check (tmp_path probe proving guard F401-sensitivity without mutating notifier.py)
  - First subprocess+ruff regression test pattern in the codebase (template for future D-06 follow-ups)
affects:
  - Future phases modifying notifier.py (CI guard forces ruff-clean posture)
  - Deferred D-06 follow-up (extending guard to state_manager.py, main.py, dashboard.py, sizing_engine.py, signal_engine.py)

# Tech tracking
tech-stack:
  added: []  # No new deps — subprocess is stdlib; ruff 0.6.9 already pinned in requirements.txt
  patterns:
    - "subprocess+ruff CI regression guard with argv list (no shell=True), timeout=30, text=True"
    - "Primary-gate-on-returncode + secondary-diagnostic-on-rule-filter — catches broader regressions while narrowing failure messages to known phase-specific categories"
    - "tmp_path sensitivity sibling test — proves guard has detection capability via self-contained probe, avoiding brittle 're-add offender and revert' ceremony"

key-files:
  created: []
  modified:
    - notifier.py (import block trimmed — 4 F401 offenders removed)
    - tests/test_notifier.py (2 new module-level tests appended at EOF — +101 lines)

key-decisions:
  - "D-04: Remove all 4 F401 offenders outright (no noqa, no TYPE_CHECKING) — verified genuinely unused per research + execute-time grep confirmation"
  - "D-05 REVIEW HIGH fix: assert BOTH returncode == 0 AND zero F401 entries — closes SC-2 gap where the earlier draft allowed non-F401 ruff warnings to slip through"
  - "D-05 REVIEW LOW fix: replace 'manually re-add SPI_MULT and verify RED' ceremony with tmp_path sensitivity sibling — self-contained, no notifier.py mutation during test run"
  - "D-06: Scope locked to notifier.py only — state_manager.py, main.py, dashboard.py ruff warnings are deferred follow-up"

patterns-established:
  - "subprocess+ruff CI guard pattern: argv list-form, capture_output=True, text=True, timeout=30 — template for future per-file ruff-clean CI guards"
  - "Primary-gate-plus-narrow-diagnostic dual assertion: primary catches any regression via returncode; secondary filter narrows the failure message to the specific rule category the phase closed — reds actionable in CI output"
  - "Sensitivity sibling test pattern: tmp_path + hardcoded probe proves guard detection without mutating production code"

requirements-completed: [CHORE-02]

# Metrics
duration: ~5min (319s)
completed: 2026-04-24
---

# Phase 10 Plan 02: CHORE-02 ruff F401 Cleanup Summary

**notifier.py import block trimmed (4 unused system_params imports removed) and CI regression guard added (2 module-level tests — primary returncode gate + tmp_path F401 sensitivity probe) using subprocess+ruff with zero new third-party deps.**

## Performance

- **Duration:** ~5 min (319s)
- **Started:** 2026-04-24T10:54:06Z
- **Completed:** 2026-04-24T10:59:25Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Removed 4 F401 unused imports from notifier.py (AUDUSD_COST_AUD, AUDUSD_NOTIONAL, SPI_COST_AUD, SPI_MULT) — pure import-block deletion, zero behavior change, verified via `ruff check notifier.py --output-format=json` returning `[]`.
- Added `tests/test_notifier.py::test_ruff_clean_notifier` asserting BOTH `result.returncode == 0` (PRIMARY gate enforcing ROADMAP SC-2 "zero warnings of ANY category") AND zero entries with `code == 'F401'` (SECONDARY diagnostic narrowing the failure message to the Phase 10 regression). Closes 10-REVIEWS.md HIGH gap where the earlier draft only filtered F401 and silently allowed non-F401 warnings to pass.
- Added `tests/test_notifier.py::test_ruff_clean_notifier_detects_f401_regression` sensitivity sibling — writes a 2-line probe module (`'''docstring'''\nimport os\n`) via pytest `tmp_path`, asserts `ruff check` returns non-zero AND emits ≥1 F401 entry. Proves guard F401-sensitivity without requiring manual notifier.py mutation (closes 10-REVIEWS.md Codex LOW).
- Ruff check on `tests/test_notifier.py` itself remains clean — no new warnings introduced in the test file.
- Zero regression: `pytest tests/test_notifier.py -q` now runs 157 tests (155 existing + 2 new), all green.

## Task Commits

Each task was committed atomically with `--no-verify` (parallel worktree):

1. **Task 1: Remove 4 F401 offenders from notifier.py** — `884eada` (chore)
2. **Task 2: Add ruff F401 CI regression guard (test_ruff_clean_notifier + sensitivity sibling)** — `efee6e0` (test)

**Plan metadata (this summary):** committed separately at the end of this agent's run.

_Note: Plan is TDD in spirit (new tests guard a cleanup) but each task commits atomically rather than RED/GREEN/REFACTOR per task — the cleanup in Task 1 is not a behavior change (dead-code removal), so the PRIMARY gate test_ruff_clean_notifier in Task 2 is the first and only assertion wave._

## Files Created/Modified

- `notifier.py` — Removed 4 lines from the `from system_params import (...)` block (lines 71, 72, 75, 76 of the pre-edit file): AUDUSD_COST_AUD, AUDUSD_NOTIONAL, SPI_COST_AUD, SPI_MULT. Preserved all 13 runtime-used names (_COLOR_BG, _COLOR_BORDER, _COLOR_FLAT, _COLOR_LONG, _COLOR_SHORT, _COLOR_SURFACE, _COLOR_TEXT, _COLOR_TEXT_DIM, _COLOR_TEXT_MUTED, FALLBACK_CONTRACT_SPECS, INITIAL_ACCOUNT, TRAIL_MULT_LONG, TRAIL_MULT_SHORT).
- `tests/test_notifier.py` — Appended 101 lines at EOF: (1) `test_ruff_clean_notifier` module-level function (D-05 primary + secondary), (2) `test_ruff_clean_notifier_detects_f401_regression` module-level function using pytest `tmp_path` (sensitivity sibling). Both tests use local imports (`json`, `subprocess`) inside their function bodies per existing test file convention. No module-top imports added.

## Ruff Before/After

**Before Task 1** (`ruff check notifier.py --output-format=json`):
- Returncode: 1
- 4 entries, all `code == 'F401'` at rows 71, 72, 75, 76:
  - `system_params.AUDUSD_COST_AUD imported but unused`
  - `system_params.AUDUSD_NOTIONAL imported but unused`
  - `system_params.SPI_COST_AUD imported but unused`
  - `system_params.SPI_MULT imported but unused`

**After Task 1** (`ruff check notifier.py --output-format=json`):
- Returncode: 0
- stdout: `[]` (empty JSON array)
- `ruff check notifier.py` → "All checks passed!"

## Test Count Delta

- Before: `pytest tests/test_notifier.py -q` → 155 passed
- After: `pytest tests/test_notifier.py -q` → 157 passed (+2 new, 0 regression)

## REVIEW HIGH Fix Confirmation

Both assertions present in `test_ruff_clean_notifier`:

1. `assert len(f401_entries) == 0` — SECONDARY diagnostic filter on `code == 'F401'` (narrows CI failure message to the Phase 10 regression category)
2. `assert result.returncode == 0` — PRIMARY gate enforcing ROADMAP SC-2 "ruff check notifier.py returns zero warnings" across ALL rule categories (F401, E-series, W-series, UP-series, etc.)

This closes the 10-REVIEWS.md HIGH severity gap where the earlier plan draft asserted only on the F401 filter and silently allowed any non-F401 ruff warning to slip through the guard. The assertion message on the PRIMARY gate explicitly references `SC-2` for traceability (`grep -q "SC-2" tests/test_notifier.py` → PASS).

## Decisions Made

None beyond following the plan as written. Plan deliberately pre-decided:
- Remove outright (no noqa, no TYPE_CHECKING) per D-04 — research already verified genuine unused status.
- Dual assertion (returncode + F401 filter) per D-05 HIGH review fix.
- tmp_path sensitivity sibling per D-05 LOW review fix (replaces manual mutation ceremony).
- Local imports inside test function bodies — matches existing test_main.py convention.
- Module-level test functions (not class-nested) — matches D-05 one-shot convention.

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None. Execute-time grep (`grep -n "AUDUSD_COST_AUD" notifier.py`, etc.) confirmed each of the 4 identifiers appeared exactly once on its import line, validating the research finding that all 4 were genuinely unused. Baseline `ruff check` emitted exactly 4 F401 entries matching the plan's interfaces block. Existing 155 notifier tests all passed after Task 1. Both new tests passed first-try after Task 2.

## User Setup Required

None — pure code/test change with no external service configuration.

## Next Phase Readiness

- CHORE-02 is CLOSED. ROADMAP Phase 10 SC-2 ("ruff check notifier.py emits zero warnings") is now asserted by a CI regression guard that runs as part of `pytest tests/test_notifier.py`.
- Pattern established (subprocess+ruff+tmp_path) is reusable for deferred D-06 follow-up to sweep F401 warnings in `state_manager.py`, `main.py`, `dashboard.py`, `sizing_engine.py`, `signal_engine.py` — a future `chore(quick)` or milestone phase can lift this template verbatim.
- Plan 10-02 did not modify STATE.md or ROADMAP.md per parallel-worktree protocol — orchestrator owns those writes after all Wave 1 agents complete.

## Self-Check: PASSED

**Files verified:**
- `notifier.py` — FOUND (import block trimmed; `ruff check notifier.py` → All checks passed!)
- `tests/test_notifier.py` — FOUND (test_ruff_clean_notifier + test_ruff_clean_notifier_detects_f401_regression present at EOF)

**Commits verified:**
- `884eada` — FOUND (Task 1: chore(10-02): remove 4 F401 unused imports from notifier.py)
- `efee6e0` — FOUND (Task 2: test(10-02): add ruff F401 CI regression guard for notifier.py)

**Acceptance criteria (all greps PASS):**
- `def test_ruff_clean_notifier` present — PASS
- `def test_ruff_clean_notifier_detects_f401_regression` present — PASS
- `assert result.returncode == 0` present (REVIEW HIGH fix) — PASS
- `code.*F401` filter present — PASS
- `ruff.*check.*notifier.py.*--output-format=json` subprocess argv present — PASS
- `timeout=30` present — PASS
- `SC-2` traceability in assertion message present — PASS

**Runtime verification:**
- `pytest tests/test_notifier.py::test_ruff_clean_notifier -q` → 1 passed
- `pytest tests/test_notifier.py::test_ruff_clean_notifier_detects_f401_regression -q` → 1 passed
- `pytest tests/test_notifier.py -q` → 157 passed (155 existing + 2 new, zero regression)
- `ruff check tests/test_notifier.py` → All checks passed!
- `python -c "import notifier"` → OK

---
*Phase: 10-foundation-v1-0-cleanup-deploy-key*
*Plan: 02*
*Completed: 2026-04-24*
