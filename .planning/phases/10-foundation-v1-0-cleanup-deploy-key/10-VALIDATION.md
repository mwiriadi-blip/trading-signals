---
phase: 10
slug: foundation-v1-0-cleanup-deploy-key
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-24
revised: 2026-04-24 (reviews mode — added tests per 10-REVIEWS.md HIGH/MEDIUM/LOW)
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

Reviews-mode revision 2026-04-24: added rows for the review-driven new tests
— `test_ruff_clean_notifier_detects_f401_regression` (HIGH/LOW),
`test_commit_failure_logs_error_and_appends_warning` (LOW log-verb
distinction), `test_run_daily_check_does_not_push_on_weekend` (MEDIUM D-15),
`test_run_daily_check_does_not_push_on_test_mode` (MEDIUM D-15), and
`test_main_cli_dispatch_reaches_push_helper_smoke` (MEDIUM retained CLI
smoke alongside direct run_daily_check coverage).

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 10-01-01 | 01 | 1 | BUG-01 | — | reset_state() syncs account field | unit | `pytest tests/test_state_manager.py::TestResetState -q` | ❌ W0 | ⬜ pending |
| 10-01-02 | 01 | 1 | BUG-01 | — | _handle_reset syncs account field via CLI + interactive paths | unit | `pytest tests/test_main.py::TestHandleReset -q` | ❌ W0 | ⬜ pending |
| 10-02-01 | 02 | 1 | CHORE-02 | — | notifier.py F401-clean AND ruff exits 0 (returncode gate per REVIEW HIGH) | unit | `pytest tests/test_notifier.py::test_ruff_clean_notifier -q` | ❌ W0 | ⬜ pending |
| 10-02-02 | 02 | 1 | CHORE-02 | — | ruff guard is F401-sensitive (temp-file probe) per REVIEW HIGH/LOW | unit (subprocess + tmp_path) | `pytest tests/test_notifier.py::test_ruff_clean_notifier_detects_f401_regression -q` | ❌ W0 | ⬜ pending |
| 10-03-01 | 03 | 2 | INFRA-02 | T-10-01 (deploy-key leak) | _push_state_to_git commits + pushes state.json; fails loud + warns on error | unit (subprocess mocked) | `pytest tests/test_main.py::TestPushStateToGit -q` | ❌ W0 | ⬜ pending |
| 10-03-02 | 03 | 2 | INFRA-02 | T-10-08 (log-verb distinction) | Push-failure log emits `[State] git push failed` verb (REVIEW LOW) | unit (subprocess mocked) | `pytest tests/test_main.py::TestPushStateToGit::test_push_failure_logs_error_and_appends_warning -q` | ❌ W0 | ⬜ pending |
| 10-03-03 | 03 | 2 | INFRA-02 | T-10-08 (log-verb distinction) | Commit-failure log emits `[State] git commit failed` verb (REVIEW LOW) | unit (subprocess mocked) | `pytest tests/test_main.py::TestPushStateToGit::test_commit_failure_logs_error_and_appends_warning -q` | ❌ W0 | ⬜ pending |
| 10-03-04 | 03 | 2 | INFRA-02 | — | run_daily_check invokes _push_state_to_git after save_state (direct run_daily_check invocation per REVIEW MEDIUM) | unit | `pytest tests/test_main.py::TestRunDailyCheckPushesState::test_run_daily_check_invokes_push_after_save -q` | ❌ W0 | ⬜ pending |
| 10-03-05 | 03 | 2 | INFRA-02 | — | D-15: --test mode does NOT reach _push_state_to_git (REVIEW MEDIUM — NEW) | unit | `pytest tests/test_main.py::TestRunDailyCheckPushesState::test_run_daily_check_does_not_push_on_test_mode -q` | ❌ W0 | ⬜ pending |
| 10-03-06 | 03 | 2 | INFRA-02 | — | D-15: weekend skip does NOT reach _push_state_to_git (REVIEW MEDIUM — NEW) | unit (freeze_time Sat) | `pytest tests/test_main.py::TestRunDailyCheckPushesState::test_run_daily_check_does_not_push_on_weekend -q` | ❌ W0 | ⬜ pending |
| 10-03-07 | 03 | 2 | INFRA-02 | — | CLI dispatch smoke test — main.main(['--force-email']) reaches helper (REVIEW MEDIUM retained smoke) | integration | `pytest tests/test_main.py::TestRunDailyCheckPushesState::test_main_cli_dispatch_reaches_push_helper_smoke -q` | ❌ W0 | ⬜ pending |
| 10-04-01 | 04 | 3 | INFRA-03 | — | .github/workflows/daily.yml renamed to .disabled; path regression test updated | unit | `pytest tests/test_scheduler.py::TestGHAWorkflow -q` | ✅ | ⬜ pending |
| 10-04-02 | 04 | 3 | INFRA-03 | — | SETUP-DEPLOY-KEY.md exists in phase dir with operator commands | file check | `test -f .planning/phases/10-foundation-v1-0-cleanup-deploy-key/SETUP-DEPLOY-KEY.md && grep -q 'ssh-keygen' .planning/phases/10-foundation-v1-0-cleanup-deploy-key/SETUP-DEPLOY-KEY.md` | ❌ | ⬜ pending |
| 10-04-03 | 04 | 3 | INFRA-03 | T-10-06 (stale-docs misconfig) | SETUP-DEPLOY-KEY.md includes docs/DEPLOY.md staleness pointer (REVIEW LOW) | file check | `grep -q 'docs/DEPLOY.md' .planning/phases/10-foundation-v1-0-cleanup-deploy-key/SETUP-DEPLOY-KEY.md && grep -q 'docs-sweep' .planning/phases/10-foundation-v1-0-cleanup-deploy-key/SETUP-DEPLOY-KEY.md` | ❌ | ⬜ pending |
| 10-04-04 | 04 | 3 | INFRA-03 | — | docs/DEPLOY.md INTENTIONALLY untouched per REVIEW LOW option (b) | file check | `git diff --quiet docs/DEPLOY.md` | ✅ (baseline) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_main.py::TestHandleReset` — new test class: D-03 CLI-flag path + interactive path (BUG-01)
- [ ] `tests/test_main.py::TestPushStateToGit` — new test class with 6 tests: D-07/D-08/D-09/D-10/D-12 coverage + commit-vs-push log-verb distinction per REVIEW LOW (INFRA-02)
- [ ] `tests/test_main.py::TestRunDailyCheckPushesState` — new test class with 4 tests: D-08 direct-run_daily_check wiring + D-15 weekend-skip (NEW per REVIEW MEDIUM) + D-15 --test skip (NEW per REVIEW MEDIUM) + CLI smoke (REVIEW MEDIUM retained) (INFRA-02)
- [ ] `tests/test_state_manager.py::TestResetState` — new test class: D-02 custom initial_account + default backward-compat (BUG-01)
- [ ] `tests/test_notifier.py::test_ruff_clean_notifier` — new test: runs `ruff check notifier.py --output-format=json`, asserts BOTH `returncode == 0` (REVIEW HIGH fix for SC-2) AND zero F401 entries (CHORE-02 D-05)
- [ ] `tests/test_notifier.py::test_ruff_clean_notifier_detects_f401_regression` — new test (REVIEW HIGH/LOW): uses tmp_path to write a probe file with an unused import; asserts `ruff check` returns non-zero and emits at least one F401 entry — proves the guard's F401 sensitivity without mutating notifier.py (CHORE-02 D-05)
- [ ] `tests/test_scheduler.py` — update class-level `WORKFLOW_PATH` constant from `.github/workflows/daily.yml` to `.github/workflows/daily.yml.disabled` (INFRA-03 D-18; one-line change covers all 12 tests per research finding)

All Wave 0 work is test-side only; no framework install needed (pytest + pytest-freezer already pinned).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Droplet deploy key accepted by GitHub; SSH push succeeds end-to-end | INFRA-02 SC-3 | Requires live SSH key + GitHub API + network | Follow `SETUP-DEPLOY-KEY.md` on droplet; run `ssh -T git@github.com` (expect "Hi NAME/repo! You've successfully authenticated"); then run `python main.py --once` and confirm new state.json commit appears in `git log origin/main` authored by `DO Droplet <droplet@trading-signals>` |
| GHA cron silent for 2 consecutive weekdays | INFRA-03 SC-4 | Requires waiting 2 business days post-merge and watching operator inbox | Operator confirms no `[Trading Signals]` email from GitHub Actions between T+0 and T+2 weekdays post-merge; `/gsd-verify-work 10` treats SC-4 as "pending operator confirmation" matching Phase 7 Wave 2 pattern |
| Deploy-key commit authorship visible in GitHub commit log | INFRA-02 SC-3 | Requires browser/GitHub UI access | Operator opens `https://github.com/<user>/<repo>/commits/main`, confirms last 3 state.json commits show author `DO Droplet <droplet@trading-signals>` |
| docs/DEPLOY.md rewrite (deferred per REVIEW LOW) | — (deferred to post-Phase-12 docs-sweep) | Broader rewrite needs v1.1 infra (HTTPS/nginx/systemd) to describe | Tracked in `10-CONTEXT.md §Deferred Ideas`; no Phase 10 verification — new docs-sweep phase will own the rewrite + its own verification matrix |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (including the 5 new review-driven tests: `test_ruff_clean_notifier_detects_f401_regression`, `test_commit_failure_logs_error_and_appends_warning`, `test_run_daily_check_does_not_push_on_weekend`, `test_run_daily_check_does_not_push_on_test_mode`, `test_main_cli_dispatch_reaches_push_helper_smoke`)
- [ ] No watch-mode flags
- [ ] Feedback latency < 90s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending (reviews-mode revision 2026-04-24)
