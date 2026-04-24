---
phase: 07-scheduler-github-actions-deployment
plan: 01
subsystem: scheduler/deps/scaffold
tags:
  - scheduler
  - dependencies
  - ast-blocklist
  - dotenv
  - test-scaffold
dependency_graph:
  requires:
    - Phase 6 (_send_email_never_crash precedent; main() dispatch ladder; 4-tuple run_daily_check contract)
    - Phase 5 (_render_dashboard_never_crash C-2 local-import pattern)
    - Phase 4 (main.py orchestrator; '[Sched] One-shot mode' log line PRESERVED for Wave 1 deletion)
    - Phase 3 (system_params.py constants block style)
  provides:
    - requirements.txt pins for schedule==1.2.2, python-dotenv==1.0.1, PyYAML==6.0.2 (Wave 1 + Wave 2 consume)
    - system_params.LOOP_SLEEP_S / SCHEDULE_TIME_UTC / WEEKDAY_SKIP_THRESHOLD (Wave 1 weekday gate + loop)
    - main._run_daily_check_caught stub (Wave 1 fills body)
    - main._run_schedule_loop stub (Wave 1 fills body)
    - main._get_process_tzname wrapper (Wave 1 patches in tests instead of time.tzname)
    - main() live load_dotenv() bootstrap (Wave 0 functional)
    - tests/test_scheduler.py 6-class scaffold + _FakeScheduler/_FakeJob helpers
    - AST blocklist extensions for DASHBOARD + NOTIFIER (Wave 0-onwards)
  affects:
    - main.py (3 new helpers + dotenv bootstrap)
    - tests/test_signal_engine.py (FORBIDDEN_MODULES_{DASHBOARD,NOTIFIER} extended)
    - .env.example (header rewritten)
tech-stack:
  added:
    - schedule 1.2.2 (pinned; future Wave 1 loop driver)
    - python-dotenv 1.0.1 (pinned; Wave 0 live load_dotenv())
    - PyYAML 6.0.2 (pinned per 07-REVIEWS.md MEDIUM action; Wave 2 consumes)
  patterns:
    - C-2 local-import pattern (Phase 5/6) — applied to load_dotenv inside main() and will apply to `import schedule` inside _run_schedule_loop Wave 1
    - Injected-collaborator testability (scheduler=None, sleep_fn=None, max_ticks=None) — signature locked Wave 0
    - Thin wrapper for test-patchability (_get_process_tzname) — addresses Codex MEDIUM-fix for time.tzname brittleness
    - AST blocklist additive extension (two strings + one comment per frozenset)
key-files:
  created:
    - tests/test_scheduler.py
  modified:
    - requirements.txt
    - system_params.py
    - main.py
    - tests/test_signal_engine.py
    - .env.example
decisions:
  - D-06 bootstrap goes live in Wave 0 (zero-risk; local-dev works immediately)
  - D-01/D-02 stub signatures locked; bodies arrive Wave 1
  - Phase 4 '[Sched] One-shot mode' log line PRESERVED (Wave 1 deletes alongside tests/test_main.py:129,146 update — Pitfall 3 mitigation)
  - PyYAML pinned even though only Wave 2 consumes (explicit dep graph)
  - _get_process_tzname wrapper (not monkeypatch of time.tzname) per 07-REVIEWS.md Codex MEDIUM fix
metrics:
  duration: ~8 min
  completed_date: 2026-04-23
---

# Phase 07 Plan 01: Wave 0 Scaffold — Pin Deps + Seed Stubs + Extend AST Blocklist Summary

**One-liner:** Pins `schedule==1.2.2` + `python-dotenv==1.0.1` + `PyYAML==6.0.2`; seeds three Phase 7 helpers in `main.py` (two stubs + a live `_get_process_tzname` wrapper + live `load_dotenv()`); creates a 6-class `tests/test_scheduler.py` skeleton; extends `FORBIDDEN_MODULES_{DASHBOARD,NOTIFIER}` AST blocklists so Wave 1 can land the loop + weekday gate body without re-wiring any cross-cutting concern.

---

## Files Touched

| File | Change | Line delta |
|------|--------|-----------|
| `requirements.txt` | Append 3 pins (PyYAML, python-dotenv, schedule); alpha-sort preserved | 6 → 9 (+3) |
| `system_params.py` | New "Phase 7 constants" block at end of file (LOOP_SLEEP_S, SCHEDULE_TIME_UTC, WEEKDAY_SKIP_THRESHOLD) | 124 → 132 (+8) |
| `main.py` | New Phase 7 helpers block (3 helpers: 1 functional wrapper + 2 stubs) between `_send_email_never_crash` and `_build_parser`; live `load_dotenv()` bootstrap inside `main()` body before `_build_parser()` | 792 → 864 (+72) |
| `tests/test_scheduler.py` | NEW file; 6 test classes + `_FakeScheduler` + `_FakeJob` helpers; one xfail(strict=True) scaffold test per class | 0 → 95 (+95) |
| `tests/test_signal_engine.py` | Append `'schedule', 'dotenv'` + one comment line to FORBIDDEN_MODULES_DASHBOARD + FORBIDDEN_MODULES_NOTIFIER frozensets; FORBIDDEN_MODULES_MAIN untouched | 1065 → 1071 (+6) |
| `.env.example` | Full header rewrite (three-tier deploy commentary: LOCAL DEV / GITHUB ACTIONS / REPLIT + D-12 formal contract); two existing env-var lines preserved verbatim | 9 → 26 (+17) |

**Total:** +201 lines, 1 file created, 5 files modified.

---

## Pin Versions Installed

Verified via `importlib.metadata.version(...)` after `pip install -r requirements.txt`:

| Package | Version | PyPI verification | Rationale |
|---------|---------|-------------------|-----------|
| `schedule` | 1.2.2 | 2026-04-23 (07-RESEARCH.md §Standard Stack) | Latest 1.2.x patch; no open CVEs |
| `python-dotenv` | 1.0.1 | 2026-04-23 (07-RESEARCH.md §Standard Stack) | Last 1.0.x patch; no open CVEs |
| `PyYAML` | 6.0.2 | 2026-04-23 (07-REVIEWS.md Consensus MEDIUM) | Latest 6.0.x patch; 6.0.x ABI-stable since 2022. Pinned explicitly so Wave 2 `python -c "import yaml; yaml.safe_load(...)"` acceptance criterion does not depend on a transitive dep |

`requirements.txt` grep verifications:
- `^schedule==1\.2\.2$` → 1 match
- `^python-dotenv==1\.0\.1$` → 1 match
- `^PyYAML==6\.0\.2$` → 1 match
- `(>=|~=)` → 0 matches (no soft pins)

**Note:** Neither `schedule` nor `dotenv` expose a `__version__` attribute at the module level (pytest-style metadata only). The verification uses `importlib.metadata.version(...)` instead of attribute access. Plan Task 1's `<automated>` verification block assumed attribute access; deviation noted below.

---

## Constants Added (`system_params.py`)

```python
# =========================================================================
# Phase 7 constants — scheduler loop + weekday gate (D-01, D-03, D-07)
# =========================================================================

LOOP_SLEEP_S: int = 60                   # tick-budget between schedule.run_pending calls (D-01)
SCHEDULE_TIME_UTC: str = '00:00'         # 08:00 AWST = 00:00 UTC — passed to schedule.at() (D-07)
WEEKDAY_SKIP_THRESHOLD: int = 5          # weekday() >= 5 means Sat/Sun (stdlib contract; D-03)
```

Type annotations explicit. UPPER_SNAKE naming. Appended at end of file after Position TypedDict, matching the Phase 3 constants block style.

---

## Stub Function Signatures (`main.py`)

Wave 0 verbatim (Wave 1 executor has this exact target):

```python
def _get_process_tzname() -> str:
  '''Return the process-local timezone abbreviation (e.g. "UTC", "AEST").

  Thin wrapper around `time.tzname[0]` so Wave 1's UTC assertion inside
  `_run_schedule_loop` is patchable in tests without touching the `time`
  module's attributes (07-REVIEWS.md Codex MEDIUM-fix: `time.tzname` is
  platform-dependent and not always writable, whereas a module-level
  function in `main` is always patchable via `monkeypatch.setattr`).

  Production behaviour: identical to `time.tzname[0]`.
  Test behaviour: `monkeypatch.setattr('main._get_process_tzname', lambda: 'UTC')`.
  '''
  import time as _time  # LOCAL — keep stdlib import graph tidy
  return _time.tzname[0]


def _run_daily_check_caught(job, args) -> None:
  '''D-02 (Phase 7 Wave 1): never-crash wrapper for scheduled run_daily_check.
  ...
  Wave 0: stub raises so any accidental call during Wave 0 fails loudly.
  '''
  raise NotImplementedError('[Sched] Wave 1 lands body per 07-02-PLAN.md D-02')


def _run_schedule_loop(
  job,
  args,
  scheduler=None,
  sleep_fn=None,
  tick_budget_s: float = 60.0,
  max_ticks: int | None = None,
) -> int:
  '''D-01 (Phase 7 Wave 1): factored schedule loop driver with injectable fakes.
  ...
  Wave 0: stub raises so any accidental call during Wave 0 fails loudly.
  '''
  raise NotImplementedError('[Sched] Wave 1 lands body per 07-02-PLAN.md D-01')
```

`_get_process_tzname` is FULLY FUNCTIONAL in Wave 0 (returns a non-empty string matching `time.tzname[0]`). The two stubs raise `NotImplementedError` — Wave 1 fills them per 07-02-PLAN.md.

**Live `load_dotenv()` bootstrap** inside `main()` body (lines 819-820, before `_build_parser()` at line 822):

```python
# D-06 (Phase 7): load .env into os.environ BEFORE parsing args.
# Local import keeps `dotenv` off module-top imports so the AST blocklist
# on every non-main module stays meaningful; main.py is the sole consumer.
from dotenv import load_dotenv  # noqa: PLC0415 — C-2 local-import pattern
load_dotenv()  # no-op when .env absent; env vars take precedence (override=False default)
```

`load_dotenv()` is idempotent and side-effect-neutral when `.env` is absent, so it ships live in Wave 0.

---

## Test Scaffold (`tests/test_scheduler.py`)

6 test classes, each containing one `xfail(strict=True)` scaffold test:

| Class | D-ref | Wave-1 target |
|-------|-------|---------------|
| `TestWeekdayGate` | D-03 | weekday() >= 5 short-circuits; parametrised Sat/Sun |
| `TestImmediateFirstRun` | D-04 | default mode calls `_run_daily_check_caught` BEFORE `_run_schedule_loop` |
| `TestLoopDriver` | D-01 | `max_ticks=0/1` termination; run_pending + sleep calls; UTC assertion via `_get_process_tzname` patch |
| `TestLoopErrorHandling` | D-02 | typed + catch-all exceptions swallowed; rc!=0 WARN |
| `TestDefaultModeDispatch` | D-05 | `[Sched] scheduler entered` log line fires; deprecated `One-shot mode` removed |
| `TestDotenvLoading` | D-06 | `load_dotenv` fires exactly once at top of `main()` |

Each scaffold test has `@pytest.mark.xfail(strict=True)` with a Wave-1 marker reason. If Wave 1 accidentally leaves a scaffold behind without removing the xfail marker, `strict=True` causes an XPASS, failing the suite.

Also committed: `_FakeScheduler` + `_FakeJob` helpers (per 07-RESEARCH.md §Example 6) for Wave 1 loop-driver injection.

---

## AST Blocklist Deltas

`tests/test_signal_engine.py` frozensets:

| Frozenset | Before | After | Delta |
|-----------|--------|-------|-------|
| `FORBIDDEN_MODULES_DASHBOARD` | 9 strings | 11 strings | +`'schedule'`, +`'dotenv'` (+comment) |
| `FORBIDDEN_MODULES_NOTIFIER` | 8 strings | 10 strings | +`'schedule'`, +`'dotenv'` (+comment) |
| `FORBIDDEN_MODULES_MAIN` | 4 strings | 4 strings | UNCHANGED — main.py is sole legitimate consumer of schedule + dotenv |
| `FORBIDDEN_MODULES` / `FORBIDDEN_MODULES_STATE_MANAGER` / `FORBIDDEN_MODULES_DATA_FETCHER` | — | — | UNCHANGED — already contained `'schedule'` + `'dotenv'` pre-Phase-7 (verified 07-RESEARCH.md lines 279–286) |

Python-level assertion verified:
- `'schedule' in FORBIDDEN_MODULES_DASHBOARD` → True
- `'dotenv'   in FORBIDDEN_MODULES_DASHBOARD` → True
- `'schedule' in FORBIDDEN_MODULES_NOTIFIER`  → True
- `'dotenv'   in FORBIDDEN_MODULES_NOTIFIER`  → True
- `'schedule' in FORBIDDEN_MODULES_MAIN`      → False
- `'dotenv'   in FORBIDDEN_MODULES_MAIN`      → False

---

## `.env.example` Header Diff

Replaced Phase 6 placeholder header with three-tier deploy commentary:

- **LOCAL DEV** — `load_dotenv()` picks up `.env` automatically; never commit `.env`.
- **GITHUB ACTIONS** — add secrets under Settings → Secrets and variables → Actions (D-12).
- **REPLIT** — add in Secrets tab; no `.env` file needed.

Formal env-var contract spelled out:
- `RESEND_API_KEY` — required for deploy
- `SIGNALS_EMAIL_TO` — required for deploy (recipient override)
- `RESET_CONFIRM=YES` — dev/CI only (_handle_reset interactive prompt skip)

Superseded env vars absent: `ANTHROPIC_API_KEY`, `FROM_EMAIL`, `TO_EMAIL` (grep count = 0).

Two existing env-var lines (`RESEND_API_KEY=re_xxx...`, `SIGNALS_EMAIL_TO=your-email@example.com`) preserved verbatim at end of file.

---

## Phase 4 Log Line Preservation Confirmation

`grep -c "One-shot mode" main.py` → 1 match (still present at main.py).

This is INTENTIONAL. Wave 1 (07-02-PLAN.md Task 5) deletes this line alongside the `tests/test_main.py:129,146` assertion updates in the SAME plan — Pitfall 3 mitigation (atomic test transition per 07-REVIEWS.md Gemini strength). Deleting it here would leave the existing test assertions at tests/test_main.py:129,146 broken.

---

## Codex MEDIUM-fix Landed

`main._get_process_tzname` is available as a patchable attribute. Verified:

```python
>>> import time, main
>>> main._get_process_tzname() == time.tzname[0]
True
```

Wave 1 tests will patch `main._get_process_tzname` instead of `time.tzname`. The wrapper is regular-module-level function that is always writable via `monkeypatch.setattr('main._get_process_tzname', lambda: 'UTC')`, unlike `time.tzname` which is platform-dependent.

---

## Deviations from Plan

### [Rule 1 - Plan bug] Plan's `<automated>` verification assumed attribute-level `__version__` access

**Found during:** Task 1 verification.

**Issue:** Plan's verify block runs:
```python
python -c "import schedule, dotenv, yaml, system_params; assert schedule.__version__ == '1.2.2'; assert dotenv.__version__ == '1.0.1'"
```

However, neither the `schedule` nor `dotenv` modules expose a `__version__` attribute on the top-level module (`schedule` 1.2.2 has no attr; `dotenv` 1.0.1 has none either). Only `yaml.__version__` works that way.

**Fix:** Used `importlib.metadata.version('schedule' | 'python-dotenv' | 'PyYAML')` instead. All three pins verified at `1.2.2`, `1.0.1`, `6.0.2` respectively. Acceptance criteria — which separately check `grep -c "^schedule==1\.2\.2$" requirements.txt` and `python -c "import system_params; print(...)"` — all pass. Wave 1 should use `importlib.metadata.version(...)` rather than attribute access in any runtime assertion.

**Files affected:** None (no code changed; the deviation is in the verification approach used by the executor).

**Commit:** N/A — verification-only.

---

## Pytest Suite Summary

| Category | Count |
|----------|-------|
| Passed | 516 |
| xfailed (new Wave 0 scaffolds) | 6 |
| Skipped | 0 |
| Failed | 0 |

All 516 pre-existing tests stay green. The 6 new `xfail(strict=True)` scaffolds fail as expected (not counted as failures).

**Ruff:** `ruff check .` exits 0 — all Python files clean.

---

## Commits

| Task | Commit | Message |
|------|--------|---------|
| Task 1 | `1d0e210` | `feat(07-01): pin schedule+dotenv+PyYAML, add Phase 7 constants, extend AST blocklist` |
| Task 2 | `340161e` | `feat(07-01): seed scheduler stubs + tz wrapper + load_dotenv bootstrap + test scaffold` |

---

## Wave Handoff

Wave 1 (07-02-PLAN.md) can now:
1. Fill `_run_daily_check_caught` body (signature locked).
2. Fill `_run_schedule_loop` body (signature + injection pattern locked; `_get_process_tzname` available for UTC assertion).
3. Prepend weekday gate to `run_daily_check` (`WEEKDAY_SKIP_THRESHOLD = 5` constant available).
4. Amend `main()` default-mode branch (stubs exist at known names).
5. DELETE `'[Sched] One-shot mode ...'` log line alongside `tests/test_main.py:129,146` updates (Pitfall 3).
6. Populate the 6 scheduler test classes (scaffold + fakes already committed).

Wave 2 (07-03-PLAN.md) can now:
1. Write `.github/workflows/daily.yml` (no deps to add).
2. Write `docs/DEPLOY.md` (no deps to add).
3. Add `TestGHAWorkflow` (PyYAML pinned so `yaml.safe_load(...)` in the Wave 2 acceptance test works without transitive-dep reliance).

---

## Self-Check: PASSED

- Task 1 commit `1d0e210` → `git log --all | grep 1d0e210` FOUND
- Task 2 commit `340161e` → `git log --all | grep 340161e` FOUND
- `requirements.txt` FOUND (9 lines)
- `system_params.py` FOUND (132 lines; Phase 7 constants present)
- `main.py` FOUND (864 lines; 3 Phase 7 helpers present; load_dotenv bootstrap present)
- `tests/test_scheduler.py` FOUND (95 lines; 6 classes; 6 xfail placeholders)
- `tests/test_signal_engine.py` FOUND (1071 lines; DASHBOARD + NOTIFIER blocklists extended)
- `.env.example` FOUND (26 lines; three-tier deploy commentary)
- Full pytest suite: 516 passed, 6 xfailed, 0 failed
- Ruff: clean on all Python files
- Phase 4 `'One-shot mode'` log line: PRESERVED (count = 1) — Wave 1 deletes alongside test_main.py updates
