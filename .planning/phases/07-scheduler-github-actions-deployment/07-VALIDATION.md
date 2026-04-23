---
phase: 7
slug: scheduler-github-actions-deployment
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-23
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.3.3 + pytest-freezer 0.4.9 (both pinned in requirements.txt) |
| **Config file** | pyproject.toml (pytest section) |
| **Quick run command** | `pytest tests/test_scheduler.py -q` |
| **Full suite command** | `pytest -q` |
| **Estimated runtime** | ~3 seconds quick; ~8 seconds full (per current 150+ test suite baseline) |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_scheduler.py tests/test_main.py -q`
- **After every plan wave:** Run `pytest -q` (full suite including TestDeterminism AST blocklist)
- **Before `/gsd-verify-work`:** Full suite must be green AND `ruff check` clean
- **Max feedback latency:** 10 seconds (quick) / 15 seconds (full)

---

## Per-Task Verification Map

> The planner populates this table after producing Wave plans. One row per task with the requirement, expected secure/functional behaviour, and the automated command that proves it.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 07-01-01 | 01 | 0 | SCHED-04 (scaffold) | — | Stubs raise NotImplementedError; file layout matches contract | unit | `pytest tests/test_scheduler.py -k "stubs" -q` (Wave 0 transient; superseded by Wave 1 bodies) | ✅ | ✅ green |
| 07-01-02 | 01 | 0 | SCHED-01..07 (skeleton) | — | Test classes present for TestWeekdayGate/TestImmediateFirstRun/TestLoopDriver/TestLoopErrorHandling/TestDefaultModeDispatch/TestDotenvLoading | unit | `pytest tests/test_scheduler.py --collect-only -q \| grep -c "::test_"` | ✅ | ✅ green |
| 07-01-03 | 01 | 0 | Hex-lite (no req-id; arch) | — | AST blocklist blocks schedule + dotenv from non-main modules; main.py allows both | unit | `pytest tests/test_signal_engine.py::TestDeterminism -q` | ✅ | ✅ green |
| 07-02-01 | 02 | 1 | SCHED-03 (weekday gate) | — | Sat + Sun return (0, None, None, run_date) without fetch; Mon–Fri proceed | unit | `pytest tests/test_scheduler.py::TestWeekdayGate -q` | ✅ | ✅ green |
| 07-02-02 | 02 | 1 | SCHED-02 (immediate first run) | — | `_run_daily_check_caught` fires before `_run_schedule_loop`; fake schedule receives .do() registration after first run | unit | `pytest tests/test_scheduler.py::TestImmediateFirstRun -q` | ✅ | ✅ green |
| 07-02-03 | 02 | 1 | SCHED-01 (canonical schedule line) | — | Loop driver calls `schedule.every().day.at('00:00').do(...)` with no tz argument; logs `'[Sched] scheduler entered; next fire 00:00 UTC (08:00 AWST) Mon–Fri'` at entry | unit | `pytest tests/test_scheduler.py::TestLoopDriver -q` | ✅ | ✅ green |
| 07-02-04 | 02 | 1 | Never-crash (D-02) | — | DataFetchError raised by fake job is caught + logged WARN; loop continues to next tick | unit | `pytest tests/test_scheduler.py::TestLoopErrorHandling -q` | ✅ | ✅ green |
| 07-02-05 | 02 | 1 | SCHED-07 / CLI-05 (default-mode flip) | — | Default `python main.py` dispatches to immediate-run-then-loop; `--once` stays one-shot; deprecated `[Sched] One-shot mode...` log line deleted | unit | `pytest tests/test_scheduler.py::TestDefaultModeDispatch tests/test_main.py -q` | ✅ | ✅ green |
| 07-02-06 | 02 | 1 | SCHED-07 (dotenv loading) | — | `load_dotenv()` fires at top of `main()`; missing `.env` is no-op; env vars take precedence | unit | `pytest tests/test_scheduler.py::TestDotenvLoading -q` | ✅ | ✅ green |
| 07-02-07 | 02 | 1 | SCHED-03 / SCHED-04 (test_main fixup) | — | Two existing tests in test_main.py:129,146 updated to match new log line (not deprecated Phase 4 stub) | unit | `pytest tests/test_main.py -q` | ✅ | ✅ green |
| 07-03-01 | 03 | 2 | SCHED-05 (GHA workflow) | — | `.github/workflows/daily.yml` passes GH's workflow-syntax check; all locked contract elements present (cron, permissions, concurrency, checkout, setup-python+cache+version-file, install, run, git-auto-commit with `add_options: '-f'` + `if: success()`) | static | `python -c "import yaml; yaml.safe_load(open('.github/workflows/daily.yml'))"` + grep assertions via `pytest tests/test_scheduler.py::TestGHAWorkflow -q` | ✅ | ✅ green |
| 07-03-02 | 03 | 2 | SCHED-06 / D-14..D-16 (docs) | — | `docs/DEPLOY.md` contains GHA quickstart + Replit alternative section + env-var contract + troubleshooting section (~150 lines) | static | `pytest tests/test_scheduler.py::TestDeployDocs -q` (grep assertions: "GitHub Actions", "Replit", "RESEND_API_KEY", "SIGNALS_EMAIL_TO", "Troubleshooting", "Reserved VM", "Always On") | ✅ | ✅ green |
| 07-03-03 | 03 | 2 | SC-4 amendment | — | ROADMAP.md SC-4 drops `ANTHROPIC_API_KEY` reference; `RESEND_API_KEY` + `SIGNALS_EMAIL_TO` remain | static | `grep -c "ANTHROPIC_API_KEY" .planning/ROADMAP.md` must be 0 | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/test_scheduler.py` — 6 test classes with stubs (TestWeekdayGate, TestImmediateFirstRun, TestLoopDriver, TestLoopErrorHandling, TestDefaultModeDispatch, TestDotenvLoading); Wave 2 adds TestGHAWorkflow + TestDeployDocs
- [x] `main.py` stubs — `_run_schedule_loop`, `_run_daily_check_caught` raising NotImplementedError; `load_dotenv()` call at top of `main()` (functional in Wave 0 so local-dev works)
- [x] `requirements.txt` additions — `schedule==1.2.2` + `python-dotenv==1.0.1` (pins from researcher, verified against PyPI 2026-04-23)
- [x] `system_params.py` additions — `LOOP_SLEEP_S = 60`, `SCHEDULE_TIME_UTC = '00:00'`, `WEEKDAY_SKIP_THRESHOLD = 5`
- [x] `tests/test_signal_engine.py` AST blocklist extension — `schedule` + `dotenv` added to `FORBIDDEN_MODULES_{STATE_MANAGER,DATA_FETCHER,DASHBOARD,NOTIFIER}`; confirmed absent from `FORBIDDEN_MODULES_MAIN`
- [x] `.env.example` header comment update — document GHA Secrets vs Replit Secrets precedence vs local `.env`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| GHA workflow executes on schedule + commits state.json | SCHED-05 | Requires live GH runner + real Yahoo Finance data + real Resend delivery + real git push | (1) Fork/clone repo to a GH account. (2) Add secrets: `RESEND_API_KEY` + `SIGNALS_EMAIL_TO` under repo → Settings → Secrets and variables → Actions. (3) Enable Actions workflows. (4) Click Actions → Daily signal check → Run workflow (manual `workflow_dispatch`). (5) Verify: green run in Actions UI, email arrives, new commit on main with message `chore(state): daily signal update [skip ci]` authored by github-actions[bot]. (6) Check state.json diff is sensible (timestamps updated, signals/positions reflect today's market). |
| Replit Reserved VM + Always On runs the schedule loop 24/7 | SCHED-06 | Requires active Replit Core subscription + filesystem persistence across restarts | Document-only in docs/DEPLOY.md; operator verifies Replit path only if/when GHA becomes unviable. No automated coverage in Phase 7. |
| Email arrives at 08:00 AWST on the weekday after deploy | End-to-end SC | Only visible by waiting a day | Complete GHA setup on Fri afternoon; wait for Mon 08:00 AWST email; verify subject + content. Not blocking for phase close. |
| GHA cron drift within documented 0–30 min range | SCHED-05 operator-facing | GHA cron is documented best-effort; delay may exceed budget on rare days | Document in troubleshooting; operator checks Actions UI log timestamp vs 00:00 UTC expected. |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (scheduler test file, loop driver stubs, new constants, dep pins)
- [x] No watch-mode flags (pytest `--looponfail` etc.) — single-shot only
- [x] Feedback latency < 10s quick / < 15s full
- [x] `nyquist_compliant: true` set in frontmatter after Wave 0 completes

**Approval:** approved on 2026-04-23

---

## Validation Audit 2026-04-23

| Metric | Count |
|--------|-------|
| Tasks audited | 13 |
| COVERED | 13 |
| PARTIAL | 0 |
| MISSING | 0 |

All automated commands verified green against commit 6622db0dd48df15a59f75bbd20ff960c3ec05d8c.

Verification evidence:
- Full suite: `pytest -q` → 552 passed, 0 failed, 0 xfailed (23.04s)
- Scheduler file: `pytest tests/test_scheduler.py -q` → 36 passed (0.52s)
- Wave 1 six scheduler classes: 12 passed (0.47s)
- `TestGHAWorkflow`: 12 passed (0.39s)
- `TestDeployDocs`: 12 passed (0.37s)
- `TestDeterminism` (AST blocklist): 44 passed (0.32s)
- `test_main.py`: 28 passed (2.16s)
- `grep -c "ANTHROPIC_API_KEY" .planning/ROADMAP.md` → 0

Audit notes:
- 07-01-01 "stubs raise NotImplementedError" — the `-k "stubs"` scaffold tests were transient Wave 0 xfail markers. Wave 1 replaced the scaffolds with 12 real tests across the six scheduler classes. Marked ✅ green via Wave 1 transition per audit hint: the scaffold was never intended to persist, and all downstream behaviour is now covered by the Wave 1 body tests (TestWeekdayGate/TestImmediateFirstRun/TestLoopDriver/TestLoopErrorHandling/TestDefaultModeDispatch/TestDotenvLoading).
- 07-01-02 "6 classes collected" — current collection shows 8 classes (6 Wave 1 scheduler + 2 Wave 2 deployment). The original command `pytest tests/test_scheduler.py --collect-only -q | grep -c "::test_"` returns 36 tests, exceeding the required ≥ 6. Green.
- All Wave 0 "File Exists: ❌ W0" markers updated to ✅ — the scaffold files landed in commit 340161e (Wave 0) and were filled by Wave 1 (commits 3279c31, d9400fc, fe210f6) and extended by Wave 2 (commits bbdc5e9, 5b0a3b9).
