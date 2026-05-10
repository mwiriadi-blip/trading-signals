---
phase: 28-v1-2-uat-closure
plan: 01
subsystem: testing
tags: [pytest, playwright, uat, marker, dev-deps]

requires:
  - phase: v1.2 baseline
    provides: pytest 8.x suite (~2030 tests), tests/conftest.py house style
provides:
  - uat marker registration in pyproject.toml
  - addopts excluding uat from default collection
  - tests/uat/ package with Playwright conftest pinned to https://signals.mwiriadi.me
  - pytest-playwright dev dep pin
  - .gitignore entry for trace artefacts
affects: [28-02, 28-03, 28-04, 28-05, 28-06]

tech-stack:
  added: [pytest-playwright==0.5.2 (dev dep, requirements-dev.txt)]
  patterns:
    - "@pytest.mark.uat for opt-in live-droplet specs (default-suite excluded via addopts)"
    - "Per-test Playwright tracing with on-failure persistence"
    - "UAT credentials via env (UAT_USER/UAT_PASS), never hardcoded"

key-files:
  created:
    - requirements-dev.txt
    - tests/uat/__init__.py
    - tests/uat/conftest.py
  modified:
    - pyproject.toml
    - .gitignore

key-decisions:
  - "Indented uat/conftest.py at 2 spaces with single quotes to match tests/conftest.py house style (plan sample showed 4-space)"
  - "BASE_URL is overridable via UAT_BASE_URL env var (defaults to production droplet) so a future op-mode override is possible without editing the file"

patterns-established:
  - "Pattern: gated live-environment tests via dual mechanism — pytest marker + addopts default-exclude — protects baseline runtime"
  - "Pattern: Playwright trace lifecycle bound to pytest_runtest_makereport rep_call so failures get a saved zip and passes don't"

requirements-completed: [DEBT-01]

duration: 8 min
completed: 2026-05-10
---

# Phase 28 Plan 01: UAT Substrate Setup Summary

**Persisted UAT scaffolding — pytest `uat` marker + addopts default-exclude + tests/uat/ Playwright conftest pinned to the production droplet — so plans 02–05 can land spec files without mutating the 2030-test default-suite baseline.**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-05-10 (this session)
- **Completed:** 2026-05-10
- **Tasks:** 2
- **Files modified:** 5 (2 modified + 3 created)

## Accomplishments
- Registered `uat` marker in `pyproject.toml` and added `-m "not uat"` to `addopts` so default `pytest` skips live UAT specs (T-28-02 mitigation).
- Created `requirements-dev.txt` pinning `pytest-playwright==0.5.2` (D-13).
- Created `tests/uat/` package with `conftest.py` wired to `https://signals.mwiriadi.me` (override via `UAT_BASE_URL`), per-test Playwright tracing with on-failure persistence, and an env-var-only credential helper (T-28-01 mitigation).
- Added `tests/uat/_traces/` to `.gitignore` (D-04).

## Task Commits

1. **Task 1: Register uat marker + exclude by default + add dev dep** — `caac4d2` (chore)
2. **Task 2: Create tests/uat/ package with conftest.py + .gitignore trace dir** — `d4766b6` (feat)

**Plan metadata commit:** _to be committed after this SUMMARY.md_

## Files Created/Modified
- `pyproject.toml` — `[tool.pytest.ini_options]` extended: `addopts` now `-ra --strict-markers -m "not uat"`; `markers = ['uat: …']`.
- `requirements-dev.txt` — new file. Pins `pytest-playwright==0.5.2` for pytest 8.x compatibility. Includes inline `playwright install chromium` bootstrap note.
- `tests/uat/__init__.py` — zero-byte package marker.
- `tests/uat/conftest.py` — Playwright fixtures: `base_url` (session scope), `browser_context_args` override merging `BASE_URL`, `page` fixture wrapping per-test `context.tracing.start()` + on-failure trace zip, `pytest_runtest_makereport` hook to expose `rep_call`, `uat_credentials()` env-var helper. Module docstring documents the read-only contract for plans 02–05.
- `.gitignore` — appended `tests/uat/_traces/` after the `.playwright-mcp/` block.

## Decisions Made
- **Indentation choice:** plan-sample showed 4-space, but `tests/conftest.py` is 2-space single-quote — matched the existing project house style for consistency. Behaviourally identical.
- **`UAT_BASE_URL` env override:** kept the env-var fallback so a future operator can point a single run at a stage URL or local FastAPI without editing the file. Default still production droplet per CONTEXT.

## Deviations from Plan

None - plan executed exactly as written. Style choice (2-space) is documented above as a Decision, not a Deviation, since the plan-listed file content was a sample-block guideline, not a fidelity requirement.

## Verification Results

| Check | Pre-edit | Post-edit | Status |
|-------|----------|-----------|--------|
| `pytest --collect-only -q \| tail -1` | `2030 tests collected in 1.71s` | `2030 tests collected in 1.11s` | PASS — count unchanged |
| `pytest -m uat --collect-only` | n/a | `0 selected, no UnknownMarkWarning` | PASS — marker registered |
| `grep -c 'not uat' pyproject.toml` | 0 | 1 | PASS |
| `grep -A 3 '^markers' pyproject.toml` | absent | shows `'uat: …'` | PASS |
| `grep 'pytest-playwright' requirements-dev.txt` | n/a | matches | PASS |
| `test -f tests/uat/__init__.py` | n/a | exists, 0 bytes | PASS |
| `grep BASE_URL\|tracing.start\|uat_credentials tests/uat/conftest.py` | n/a | all 3 strings present | PASS |
| `grep 'tests/uat/_traces/' .gitignore` | absent | matches | PASS |

**Baseline preservation:** the existing default `pytest` invocation still collects exactly 2030 tests — Phase 28's substrate is invisible to the production CI pipeline until `pytest -m uat` is invoked explicitly.

## Issues Encountered

- **Plan said baseline was ~2006 tests, actual baseline at HEAD is 2030.** Captured the actual count pre-edit and verified post-edit equality. The "2006" figure was from Phase 27 closure context (now slightly stale due to subsequent test additions). No action needed; the acceptance criterion is "unchanged from pre-Phase-28 baseline" which holds.
- **`pytest-playwright` was NOT installed locally during this plan.** The deliverable per plan instructions is the dev-dep pin in `requirements-dev.txt`; collection was verified without the package present (confirms the conftest.py is syntactically valid Python and the `uat` marker is registered independent of the playwright pytest plugin). Plans 02–05 will install it locally when they land actual spec files: `pip install -r requirements-dev.txt && playwright install chromium`.

## User Setup Required

None — the dev dep pin lives in `requirements-dev.txt` and is opt-in. Operators only need to install it before running plans 02–05's specs:

```bash
pip install -r requirements-dev.txt
playwright install chromium  # one-time browser bootstrap
```

## Next Phase Readiness

- Plans 02–05 can now land `tests/uat/test_uat_*.py` spec files: each spec marks `@pytest.mark.uat`, imports nothing from this conftest beyond what pytest auto-injects, and reads `UAT_USER`/`UAT_PASS` via `uat_credentials()` to gate authenticated flows.
- Plan 06 (regression net) drives the full UAT suite via `pytest -m uat`.
- No blockers. Threat model T-28-01 / T-28-02 mitigations are in place; T-28-03 is plan-02-onward responsibility (read-only contract enforced via code review).

## Self-Check: PASSED

- `[ -f requirements-dev.txt ]` → present
- `[ -f tests/uat/__init__.py ]` → present (0 bytes)
- `[ -f tests/uat/conftest.py ]` → present, contains BASE_URL / page.context.tracing.start / uat_credentials
- `git log --oneline --grep="28-01" -3` → caac4d2 + d4766b6 both reachable
- `pytest --collect-only -q | tail -1` → 2030 tests collected (unchanged from pre-edit baseline)
- `pytest -m uat --collect-only 2>&1 | grep -c UnknownMarkWarning` → 0 (marker registered cleanly)
- All `<verification>` plan-level commands ran clean.

---
*Phase: 28-v1-2-uat-closure*
*Completed: 2026-05-10*
