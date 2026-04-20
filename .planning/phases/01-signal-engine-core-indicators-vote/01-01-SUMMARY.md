---
phase: 01-signal-engine-core-indicators-vote
plan: 01
subsystem: dev-environment
tags: [python, scaffold, environment, pytest, ruff, wave-0]
dependency_graph:
  requires: []
  provides:
    - "Python 3.11.8 venv with 5 Phase 1 deps bit-locked"
    - "pyproject.toml pytest + ruff config (R-05)"
    - ".editorconfig enforcing 2-space indent (R-05 fallback)"
    - "tests/ package skeleton with oracle contract README"
    - "CLAUDE.md amended per R-02"
  affects:
    - "All Phase 1 plans (02-06) depend on this venv and test layout"
    - "Phase 2 and beyond inherit pyproject.toml config"
tech_stack:
  added:
    - "numpy==2.0.2"
    - "pandas==2.3.3"
    - "pytest==8.3.3"
    - "yfinance==1.2.0"
    - "ruff==0.6.9"
    - "pyenv 2.6.27 (installed via Homebrew)"
    - "Python 3.11.8 (installed via pyenv)"
  patterns:
    - "Exact version pins (no >=, no ~=) in requirements.txt"
    - "pyenv-managed Python 3.11 runtime; .python-version for GHA setup-python"
    - "venv at repo root in .venv/, gitignored"
    - "ruff lint-only (no ruff format) to preserve 2-space indent convention"
    - ".editorconfig + reviewer discipline + future Plan 06 lint guard as the 2-space enforcement triad"
key_files:
  created:
    - ".python-version"
    - "requirements.txt"
    - "pyproject.toml"
    - ".editorconfig"
    - "tests/__init__.py"
    - "tests/conftest.py"
    - "tests/oracle/__init__.py"
    - "tests/oracle/README.md"
    - "tests/fixtures/.gitkeep"
    - "tests/determinism/.gitkeep"
  modified:
    - ".gitignore (+4 entries: .venv/, .pytest_cache/, .ruff_cache/)"
    - "CLAUDE.md (Stack section: pandas/numpy/yfinance pins per R-02)"
decisions:
  - "Installed pyenv via Homebrew (plan preflight treats pyenv-missing as hard error; Homebrew was available so installed pyenv fresh rather than switching to brew install python@3.11)"
  - "Wrote pyproject.toml strings using single quotes (TOML single/double quotes are equivalent) to align with CLAUDE.md §Conventions single-quote policy"
  - "Ruff format is NOT used in Phase 1 because ruff 0.6.9 does not expose an indent-width knob — would reflow all code to 4-space. Lint-only (ruff check) is used."
metrics:
  duration_minutes: 9
  completed_date: "2026-04-20"
  tasks_completed: 3
  files_created: 10
  files_modified: 2
  commits: 3
---

# Phase 01 Plan 01: Wave 0 Environment Scaffold Summary

**One-liner:** Python 3.11.8 venv + 5 exact-pinned Phase 1 deps + pyproject.toml (pytest ini, ruff lint-only with 2-space indent caveat) + test-package skeleton with oracle-contract README documenting Wilder seed-window NaN rule (R-02, R-04, R-05).

## What Was Built

1. **Runtime lock:** Installed pyenv 2.6.27 via Homebrew, then `pyenv install 3.11.8` + `pyenv local 3.11.8` → wrote `.python-version=3.11.8`. Created `.venv` via `python -m venv .venv`; venv Python confirms 3.11.8.
2. **Dependency lock:** `requirements.txt` pins exactly 5 Phase 1 deps to bit-locked versions:
   - `numpy==2.0.2`
   - `pandas==2.3.3`
   - `pytest==8.3.3`
   - `yfinance==1.2.0`
   - `ruff==0.6.9`
   Later-phase deps (`requests`, `schedule`, `pytz`, `python-dotenv`) deliberately omitted per REVIEWS.md Codex LOW concern — Phase 4 will add its own pins.
3. **Build config:** `pyproject.toml` provides pytest ini (`minversion = '8.0'`, `testpaths = ['tests']`, `addopts = '-ra --strict-markers'`) and ruff config (`line-length = 100`, `target-version = 'py311'`, lint selectors `E F W I B UP`, `quote-style = 'single'`, `indent-style = 'space'`). `requires-python = '>=3.11,<3.12'` locks interpreter at project level.
4. **Indent enforcement (R-05 caveat):** ruff 0.6.9 does NOT expose an `indent-width` knob, so ruff format would reflow project code to 4-space. Solution: never run `ruff format`, use `ruff check` only, and enforce 2-space via `.editorconfig` (`indent_size = 2`), reviewer discipline, and Plan 06's forthcoming `test_no_four_space_indent` grep guard.
5. **Test skeleton:** Empty `tests/__init__.py`, `tests/conftest.py`, `tests/oracle/__init__.py`; `.gitkeep` placeholders in `tests/fixtures/` and `tests/determinism/`. Verified: `pytest tests/` exits 5 (no tests collected); `ruff check .` exits 0.
6. **Oracle contract:** `tests/oracle/README.md` (135 lines) documents:
   - Oracle as pure-Python loops separated from SUT (D-02)
   - Golden CSV format with `%.17g` float precision (R-03, RESEARCH Pitfall 4)
   - Scenario JSON shape with `expected_signal` + `last_row`
   - Regeneration via `tests/regenerate_goldens.py`, never in CI (D-04)
   - R-04 bar-0 TR convention = `high - low` (pandas `skipna=True` semantics)
   - 1e-9 tolerance via `numpy.testing.assert_allclose` + SHA256 determinism snapshot (D-14)
   - R-05 ruff format caveat
   - **Wilder seed-window NaN rule** (REVIEWS.md Codex MEDIUM concern) — explicit rule both oracle and production must implement identically
7. **Project stack amendment (R-02):** CLAUDE.md §Stack now reflects `pandas 2.3+ (pinned 2.3.3)`, `numpy 2.0+ (pinned 2.0.2)`, `yfinance >=1.2,<2.0 (pinned 1.2.0)` + a new sentence explaining exact-pin discipline. All other CLAUDE.md sections byte-identical to before.

## Verification Results

| Gate | Command | Expected | Actual |
|------|---------|----------|--------|
| Python version | `.venv/bin/python --version` | `3.11.x` | `Python 3.11.8` ✓ |
| numpy | `pip show numpy` | `2.0.2` | `2.0.2` ✓ |
| pandas | `pip show pandas` | `2.3.3` | `2.3.3` ✓ |
| pytest | `pip show pytest` | `8.3.3` | `8.3.3` ✓ |
| yfinance | `pip show yfinance` | `1.2.0` | `1.2.0` ✓ |
| ruff | `pip show ruff` | `0.6.9` | `0.6.9` ✓ |
| ruff check | `.venv/bin/ruff check .` | exit 0 | exit 0 ✓ |
| pytest | `.venv/bin/pytest tests/` | exit 5 | exit 5 ✓ |
| requirements.txt line count | `wc -l requirements.txt` | 5 | 5 ✓ |
| CLAUDE.md pins | grep `pandas 2.3`, `numpy 2.0`, `yfinance.*1.2` | all 3 present | all 3 present ✓ |
| `.venv/` git-ignored | `git check-ignore .venv/` | ignored | ignored ✓ |

All 3 tasks' acceptance criteria satisfied, with one documented grep-pattern defect in the plan (below).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] pyenv preflight — pyenv not installed**
- **Found during:** Task 1 start
- **Issue:** The plan's pyenv preflight emits a hard error ("Cannot proceed") when pyenv is missing. pyenv was NOT installed on this machine.
- **Fix:** Installed pyenv 2.6.27 via Homebrew (`brew install pyenv`), which was available. This matches REVIEWS.md Gemini's preflight suggestion and the plan's fallback allowance: "If the user insists on `brew install python@3.11` instead, accept that path" — we chose the cleaner pyenv path rather than the brew python@3.11 path because pyenv gives reproducible version management for future GHA setup-python pickup via `.python-version`.
- **Files modified:** system-level (pyenv installed), plus pyenv-managed `/Users/marcwiriadisastra/.pyenv/versions/3.11.8/`
- **Commit:** included in `7330764` (Task 1 commit).

### AC Grep-Pattern Defects (not code issues — plan bookkeeping)

**Plan AC `grep -c 'Hand-roll ATR' CLAUDE.md` returns 0, both pre- and post-edit.** The literal line in CLAUDE.md is `**Hand-roll** ATR(14), ADX(20), ...` — markdown bold `**` separates "Hand-roll" from "ATR". The semantic intent of the AC (preserve the Hand-roll sentence) is met: `git diff HEAD~1 HEAD -- CLAUDE.md` shows the line is byte-identical before and after Task 3. Treating this as a plan-AC phrasing defect, not a real failure. Hand-roll sentence preserved byte-for-byte.

### Scope-Boundary Notes

No pre-existing warnings, linting errors, or unrelated files were touched. `.planning/STATE.md` and `.planning/config.json` show modifications from the executor-init phase (unrelated to these 3 tasks); they will be included in the final metadata commit, not any task commit.

## Known Stubs

None. Phase 1 is pre-code — the test skeleton files are *intentionally* empty placeholders with documented follow-up plans (02 populates oracle, 03 populates fixtures, 04-05 populate production + vote tests, 06 adds architectural guards). Oracle README explicitly flags future plans' ownership of each placeholder.

## Self-Check

### Created Files

```
FOUND: .python-version
FOUND: requirements.txt
FOUND: pyproject.toml
FOUND: .editorconfig
FOUND: tests/__init__.py
FOUND: tests/conftest.py
FOUND: tests/oracle/__init__.py
FOUND: tests/oracle/README.md
FOUND: tests/fixtures/.gitkeep
FOUND: tests/determinism/.gitkeep
```

### Commits

```
FOUND: 7330764 chore(01-01): pin Python 3.11 and install Phase 1 dependencies
FOUND: b9411b0 chore(01-01): add pyproject.toml config and test-package skeleton
FOUND: 64246fd docs(01-01): amend CLAUDE.md stack pins per R-02
```

## Self-Check: PASSED
