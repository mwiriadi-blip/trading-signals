---
phase: 10
slug: foundation-v1-0-cleanup-deploy-key
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-24
---

# Phase 10 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x (+ pytest-freezer) |
| **Config file** | `pytest.ini` (existing) |
| **Quick run command** | `pytest tests/test_main.py tests/test_state_manager.py tests/test_notifier.py tests/test_scheduler.py -x -q` |
| **Full suite command** | `pytest -q` |
| **Estimated runtime** | ~30 seconds (quick) / ~90 seconds (full) |

---

## Sampling Rate

- **After every task commit:** Run quick run command (targeted files only)
- **After every plan wave:** Run full suite command
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 90 seconds

---

## Per-Task Verification Map

Populated by planner. Each task below maps to a PLAN.md task and an automated verification command.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 10-01-01 | 01 | 1 | BUG-01 | — | reset_state() syncs account field | unit | `pytest tests/test_state_manager.py::TestResetState -q` | ❌ W0 | ⬜ pending |
| 10-01-02 | 01 | 1 | BUG-01 | — | _handle_reset syncs account field via CLI + interactive paths | unit | `pytest tests/test_main.py::TestHandleReset -q` | ❌ W0 | ⬜ pending |
| 10-02-01 | 02 | 1 | CHORE-02 | — | notifier.py F401-clean | unit | `pytest tests/test_notifier.py::test_ruff_clean_notifier -q` | ❌ W0 | ⬜ pending |
| 10-03-01 | 03 | 2 | INFRA-02 | T-10-01 (deploy-key leak) | _push_state_to_git commits + pushes state.json; fails loud + warns on error | unit (subprocess mocked) | `pytest tests/test_main.py::TestPushStateToGit -q` | ❌ W0 | ⬜ pending |
| 10-03-02 | 03 | 2 | INFRA-02 | — | run_daily_check invokes _push_state_to_git after save_state | unit | `pytest tests/test_main.py::TestRunDailyCheckPushesState -q` | ❌ W0 | ⬜ pending |
| 10-04-01 | 04 | 3 | INFRA-03 | — | .github/workflows/daily.yml renamed to .disabled; path regression test updated | unit | `pytest tests/test_scheduler.py::TestGHAWorkflow -q` | ✅ | ⬜ pending |
| 10-04-02 | 04 | 3 | INFRA-03 | — | SETUP-DEPLOY-KEY.md exists in phase dir with operator commands | file check | `test -f .planning/phases/10-foundation-v1-0-cleanup-deploy-key/SETUP-DEPLOY-KEY.md && grep -q 'ssh-keygen' .planning/phases/10-foundation-v1-0-cleanup-deploy-key/SETUP-DEPLOY-KEY.md` | ❌ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_main.py::TestHandleReset` — new test class: D-03 CLI-flag path + interactive path (BUG-01)
- [ ] `tests/test_main.py::TestPushStateToGit` — new test class: D-07/D-08/D-09/D-10/D-12 coverage with subprocess mocks (INFRA-02)
- [ ] `tests/test_main.py::TestRunDailyCheckPushesState` — new test class: end-of-run hook assertion (INFRA-02 D-08)
- [ ] `tests/test_state_manager.py::TestResetState` — new test class: D-02 custom initial_account + default backward-compat (BUG-01)
- [ ] `tests/test_notifier.py::test_ruff_clean_notifier` — new test: runs `ruff check notifier.py --output-format=json`, asserts zero F401 entries (CHORE-02 D-05)
- [ ] `tests/test_scheduler.py` — update class-level `WORKFLOW_PATH` constant from `.github/workflows/daily.yml` to `.github/workflows/daily.yml.disabled` (INFRA-03 D-18; one-line change covers all 12 tests per research finding)

All Wave 0 work is test-side only; no framework install needed (pytest + pytest-freezer already pinned).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Droplet deploy key accepted by GitHub; SSH push succeeds end-to-end | INFRA-02 SC-3 | Requires live SSH key + GitHub API + network | Follow `SETUP-DEPLOY-KEY.md` on droplet; run `ssh -T git@github.com` (expect "Hi NAME/repo! You've successfully authenticated"); then run `python main.py --once` and confirm new state.json commit appears in `git log origin/main` authored by `DO Droplet <droplet@trading-signals>` |
| GHA cron silent for 2 consecutive weekdays | INFRA-03 SC-4 | Requires waiting 2 business days post-merge and watching operator inbox | Operator confirms no `[Trading Signals]` email from GitHub Actions between T+0 and T+2 weekdays post-merge; `/gsd-verify-work 10` treats SC-4 as "pending operator confirmation" matching Phase 7 Wave 2 pattern |
| Deploy-key commit authorship visible in GitHub commit log | INFRA-02 SC-3 | Requires browser/GitHub UI access | Operator opens `https://github.com/<user>/<repo>/commits/main`, confirms last 3 state.json commits show author `DO Droplet <droplet@trading-signals>` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 90s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
