---
phase: 7
slug: scheduler-github-actions-deployment
status: draft
nyquist_compliant: false
wave_0_complete: false
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
| 07-01-01 | 01 | 0 | SCHED-04 (scaffold) | — | Stubs raise NotImplementedError; file layout matches contract | unit | `pytest tests/test_scheduler.py -k "stubs" -q` | ❌ W0 | ⬜ pending |
| 07-01-02 | 01 | 0 | SCHED-01..07 (skeleton) | — | Test classes present for TestWeekdayGate/TestImmediateFirstRun/TestLoopDriver/TestLoopErrorHandling/TestDefaultModeDispatch/TestDotenvLoading | unit | `pytest tests/test_scheduler.py --collect-only -q \| grep -c "::test_"` | ❌ W0 | ⬜ pending |
| 07-01-03 | 01 | 0 | Hex-lite (no req-id; arch) | — | AST blocklist blocks schedule + dotenv from non-main modules; main.py allows both | unit | `pytest tests/test_signal_engine.py::TestDeterminism -q` | ✅ | ⬜ pending |
| 07-02-01 | 02 | 1 | SCHED-03 (weekday gate) | — | Sat + Sun return (0, None, None, run_date) without fetch; Mon–Fri proceed | unit | `pytest tests/test_scheduler.py::TestWeekdayGate -q` | ❌ W0 | ⬜ pending |
| 07-02-02 | 02 | 1 | SCHED-02 (immediate first run) | — | `_run_daily_check_caught` fires before `_run_schedule_loop`; fake schedule receives .do() registration after first run | unit | `pytest tests/test_scheduler.py::TestImmediateFirstRun -q` | ❌ W0 | ⬜ pending |
| 07-02-03 | 02 | 1 | SCHED-01 (canonical schedule line) | — | Loop driver calls `schedule.every().day.at('00:00').do(...)` with no tz argument; logs `'[Sched] scheduler entered; next fire 00:00 UTC (08:00 AWST) Mon–Fri'` at entry | unit | `pytest tests/test_scheduler.py::TestLoopDriver -q` | ❌ W0 | ⬜ pending |
| 07-02-04 | 02 | 1 | Never-crash (D-02) | — | DataFetchError raised by fake job is caught + logged WARN; loop continues to next tick | unit | `pytest tests/test_scheduler.py::TestLoopErrorHandling -q` | ❌ W0 | ⬜ pending |
| 07-02-05 | 02 | 1 | SCHED-07 / CLI-05 (default-mode flip) | — | Default `python main.py` dispatches to immediate-run-then-loop; `--once` stays one-shot; deprecated `[Sched] One-shot mode...` log line deleted | unit | `pytest tests/test_scheduler.py::TestDefaultModeDispatch tests/test_main.py -q` | ❌ W0 | ⬜ pending |
| 07-02-06 | 02 | 1 | SCHED-07 (dotenv loading) | — | `load_dotenv()` fires at top of `main()`; missing `.env` is no-op; env vars take precedence | unit | `pytest tests/test_scheduler.py::TestDotenvLoading -q` | ❌ W0 | ⬜ pending |
| 07-02-07 | 02 | 1 | SCHED-03 / SCHED-04 (test_main fixup) | — | Two existing tests in test_main.py:129,146 updated to match new log line (not deprecated Phase 4 stub) | unit | `pytest tests/test_main.py -q` | ✅ | ⬜ pending |
| 07-03-01 | 03 | 2 | SCHED-05 (GHA workflow) | — | `.github/workflows/daily.yml` passes GH's workflow-syntax check; all locked contract elements present (cron, permissions, concurrency, checkout, setup-python+cache+version-file, install, run, git-auto-commit with `add_options: '-f'` + `if: success()`) | static | `python -c "import yaml; yaml.safe_load(open('.github/workflows/daily.yml'))"` + grep assertions via `pytest tests/test_scheduler.py::TestGHAWorkflow -q` | ❌ W2 | ⬜ pending |
| 07-03-02 | 03 | 2 | SCHED-06 / D-14..D-16 (docs) | — | `docs/DEPLOY.md` contains GHA quickstart + Replit alternative section + env-var contract + troubleshooting section (~150 lines) | static | `pytest tests/test_scheduler.py::TestDeployDocs -q` (grep assertions: "GitHub Actions", "Replit", "RESEND_API_KEY", "SIGNALS_EMAIL_TO", "Troubleshooting", "Reserved VM", "Always On") | ❌ W2 | ⬜ pending |
| 07-03-03 | 03 | 2 | SC-4 amendment | — | ROADMAP.md SC-4 drops `ANTHROPIC_API_KEY` reference; `RESEND_API_KEY` + `SIGNALS_EMAIL_TO` remain | static | `grep -c "ANTHROPIC_API_KEY" .planning/ROADMAP.md` must be 0 | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_scheduler.py` — 6 test classes with stubs (TestWeekdayGate, TestImmediateFirstRun, TestLoopDriver, TestLoopErrorHandling, TestDefaultModeDispatch, TestDotenvLoading); Wave 2 adds TestGHAWorkflow + TestDeployDocs
- [ ] `main.py` stubs — `_run_schedule_loop`, `_run_daily_check_caught` raising NotImplementedError; `load_dotenv()` call at top of `main()` (functional in Wave 0 so local-dev works)
- [ ] `requirements.txt` additions — `schedule==1.2.2` + `python-dotenv==1.0.1` (pins from researcher, verified against PyPI 2026-04-23)
- [ ] `system_params.py` additions — `LOOP_SLEEP_S = 60`, `SCHEDULE_TIME_UTC = '00:00'`, `WEEKDAY_SKIP_THRESHOLD = 5`
- [ ] `tests/test_signal_engine.py` AST blocklist extension — `schedule` + `dotenv` added to `FORBIDDEN_MODULES_{STATE_MANAGER,DATA_FETCHER,DASHBOARD,NOTIFIER}`; confirmed absent from `FORBIDDEN_MODULES_MAIN`
- [ ] `.env.example` header comment update — document GHA Secrets vs Replit Secrets precedence vs local `.env`

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

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (scheduler test file, loop driver stubs, new constants, dep pins)
- [ ] No watch-mode flags (pytest `--looponfail` etc.) — single-shot only
- [ ] Feedback latency < 10s quick / < 15s full
- [ ] `nyquist_compliant: true` set in frontmatter after Wave 0 completes

**Approval:** pending
