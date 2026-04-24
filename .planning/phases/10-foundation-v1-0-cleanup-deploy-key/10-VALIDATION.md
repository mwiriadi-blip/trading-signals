---
phase: 10
slug: foundation-v1-0-cleanup-deploy-key
status: green
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-24
revised: 2026-04-24 (reviews mode — added tests per 10-REVIEWS.md HIGH/MEDIUM/LOW)
audited: 2026-04-24 (nyquist retro-audit — all 15 rows green; 3 manual-only items retained)
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
| 10-01-01 | 01 | 1 | BUG-01 | — | reset_state() syncs account field | unit | `pytest tests/test_state_manager.py::TestResetState -q` | ✅ | ✅ green |
| 10-01-02 | 01 | 1 | BUG-01 | — | _handle_reset syncs account field via CLI + interactive paths | unit | `pytest tests/test_main.py::TestHandleReset -q` | ✅ | ✅ green |
| 10-02-01 | 02 | 1 | CHORE-02 | — | notifier.py F401-clean AND ruff exits 0 (returncode gate per REVIEW HIGH) | unit | `pytest tests/test_notifier.py::test_ruff_clean_notifier -q` | ✅ | ✅ green |
| 10-02-02 | 02 | 1 | CHORE-02 | — | ruff guard is F401-sensitive (temp-file probe) per REVIEW HIGH/LOW | unit (subprocess + tmp_path) | `pytest tests/test_notifier.py::test_ruff_clean_notifier_detects_f401_regression -q` | ✅ | ✅ green |
| 10-03-01 | 03 | 2 | INFRA-02 | T-10-01 (deploy-key leak) | _push_state_to_git commits + pushes state.json; fails loud + warns on error | unit (subprocess mocked) | `pytest tests/test_main.py::TestPushStateToGit -q` | ✅ | ✅ green |
| 10-03-02 | 03 | 2 | INFRA-02 | T-10-08 (log-verb distinction) | Push-failure log emits `[State] git push failed` verb (REVIEW LOW) | unit (subprocess mocked) | `pytest tests/test_main.py::TestPushStateToGit::test_push_failure_logs_error_and_appends_warning -q` | ✅ | ✅ green |
| 10-03-03 | 03 | 2 | INFRA-02 | T-10-08 (log-verb distinction) | Commit-failure log emits `[State] git commit failed` verb (REVIEW LOW) | unit (subprocess mocked) | `pytest tests/test_main.py::TestPushStateToGit::test_commit_failure_logs_error_and_appends_warning -q` | ✅ | ✅ green |
| 10-03-04 | 03 | 2 | INFRA-02 | — | run_daily_check invokes _push_state_to_git after save_state (direct run_daily_check invocation per REVIEW MEDIUM) | unit | `pytest tests/test_main.py::TestRunDailyCheckPushesState::test_run_daily_check_invokes_push_after_save -q` | ✅ | ✅ green |
| 10-03-05 | 03 | 2 | INFRA-02 | — | D-15: --test mode does NOT reach _push_state_to_git (REVIEW MEDIUM — NEW) | unit | `pytest tests/test_main.py::TestRunDailyCheckPushesState::test_run_daily_check_does_not_push_on_test_mode -q` | ✅ | ✅ green |
| 10-03-06 | 03 | 2 | INFRA-02 | — | D-15: weekend skip does NOT reach _push_state_to_git (REVIEW MEDIUM — NEW) | unit (freeze_time Sat) | `pytest tests/test_main.py::TestRunDailyCheckPushesState::test_run_daily_check_does_not_push_on_weekend -q` | ✅ | ✅ green |
| 10-03-07 | 03 | 2 | INFRA-02 | — | CLI dispatch smoke test — main.main(['--force-email']) reaches helper (REVIEW MEDIUM retained smoke) | integration | `pytest tests/test_main.py::TestRunDailyCheckPushesState::test_main_cli_dispatch_reaches_push_helper_smoke -q` | ✅ | ✅ green |
| 10-04-01 | 04 | 3 | INFRA-03 | — | .github/workflows/daily.yml renamed to .disabled; path regression test updated | unit | `pytest tests/test_scheduler.py::TestGHAWorkflow -q` | ✅ | ✅ green |
| 10-04-02 | 04 | 3 | INFRA-03 | — | SETUP-DEPLOY-KEY.md exists in phase dir with operator commands | file check | `test -f .planning/phases/10-foundation-v1-0-cleanup-deploy-key/SETUP-DEPLOY-KEY.md && grep -q 'ssh-keygen' .planning/phases/10-foundation-v1-0-cleanup-deploy-key/SETUP-DEPLOY-KEY.md` | ✅ | ✅ green |
| 10-04-03 | 04 | 3 | INFRA-03 | T-10-06 (stale-docs misconfig) | SETUP-DEPLOY-KEY.md includes docs/DEPLOY.md staleness pointer (REVIEW LOW) | file check | `grep -q 'docs/DEPLOY.md' .planning/phases/10-foundation-v1-0-cleanup-deploy-key/SETUP-DEPLOY-KEY.md && grep -q 'docs-sweep' .planning/phases/10-foundation-v1-0-cleanup-deploy-key/SETUP-DEPLOY-KEY.md` | ✅ | ✅ green |
| 10-04-04 | 04 | 3 | INFRA-03 | — | docs/DEPLOY.md INTENTIONALLY untouched per REVIEW LOW option (b) | file check | `git diff --quiet docs/DEPLOY.md` | ✅ (baseline) | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/test_main.py::TestHandleReset` — new test class: D-03 CLI-flag path + interactive path (BUG-01) — live at line 1495
- [x] `tests/test_main.py::TestPushStateToGit` — new test class with 6 tests: D-07/D-08/D-09/D-10/D-12 coverage + commit-vs-push log-verb distinction per REVIEW LOW (INFRA-02) — live at line 2015
- [x] `tests/test_main.py::TestRunDailyCheckPushesState` — new test class with 4 tests: D-08 direct-run_daily_check wiring + D-15 weekend-skip (NEW per REVIEW MEDIUM) + D-15 --test skip (NEW per REVIEW MEDIUM) + CLI smoke (REVIEW MEDIUM retained) (INFRA-02) — live at line 2274
- [x] `tests/test_state_manager.py::TestResetState` — new test class: D-02 custom initial_account + default backward-compat (BUG-01) — live at line 922
- [x] `tests/test_notifier.py::test_ruff_clean_notifier` — new test: runs `ruff check notifier.py --output-format=json`, asserts BOTH `returncode == 0` (REVIEW HIGH fix for SC-2) AND zero F401 entries (CHORE-02 D-05) — live at line 1966
- [x] `tests/test_notifier.py::test_ruff_clean_notifier_detects_f401_regression` — new test (REVIEW HIGH/LOW): uses tmp_path to write a probe file with an unused import; asserts `ruff check` returns non-zero and emits at least one F401 entry — proves the guard's F401 sensitivity without mutating notifier.py (CHORE-02 D-05) — live at line 2021
- [x] `tests/test_scheduler.py` — `WORKFLOW_PATH` constant updated from `.github/workflows/daily.yml` to `.github/workflows/daily.yml.disabled` (INFRA-03 D-18; one-line change covers all 12 TestGHAWorkflow tests per research finding)

All Wave 0 work is test-side only; no framework install needed (pytest + pytest-freezer already pinned). Wave 0 confirmed complete via 2026-04-24 retro-audit — all 6 test classes/files exist and are exercised in the 44 Phase-10 test count (passing locally in 0.69s).

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

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (including the 5 new review-driven tests: `test_ruff_clean_notifier_detects_f401_regression`, `test_commit_failure_logs_error_and_appends_warning`, `test_run_daily_check_does_not_push_on_weekend`, `test_run_daily_check_does_not_push_on_test_mode`, `test_main_cli_dispatch_reaches_push_helper_smoke`)
- [x] No watch-mode flags
- [x] Feedback latency < 90s (quick path: 0.69s measured 2026-04-24; full suite: ~93s)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** APPROVED (reviews-mode revision 2026-04-24 → retro-audited 2026-04-24)

---

## Audit Trail

### 2026-04-24 — Nyquist retro-audit (post-execution)

Auditor: gsd-nyquist-auditor (spawned by `/gsd-validate-phase 10`)

Scope: validate that all 15 verification-map rows (6 pre-execution + 9 reviews-mode) map to real code in the live tree, and flip Status from ⬜ pending → ✅ green for every row whose automated command runs green.

**Findings**

- **Gaps found:** 0
- **Rows validated:** 15 / 15
- **Automated rows flipped to ✅ green:** 15 / 15
- **Escalated to manual-only:** 0 (three pre-existing manual-only items retained unchanged)

**Evidence**

- `tests/test_state_manager.py::TestResetState` live at line 922 (4 tests)
- `tests/test_main.py::TestHandleReset` live at line 1495 (3 tests)
- `tests/test_notifier.py::test_ruff_clean_notifier` live at line 1966
- `tests/test_notifier.py::test_ruff_clean_notifier_detects_f401_regression` live at line 2021
- `tests/test_main.py::TestPushStateToGit` live at line 2015 (6 tests including `test_push_failure_logs_error_and_appends_warning` @ line 2085 and `test_commit_failure_logs_error_and_appends_warning` @ line 2138)
- `tests/test_main.py::TestRunDailyCheckPushesState` live at line 2274 (4 tests: `test_run_daily_check_invokes_push_after_save` @ 2282, `test_run_daily_check_does_not_push_on_test_mode` @ 2311, `test_run_daily_check_does_not_push_on_weekend` @ 2337, `test_main_cli_dispatch_reaches_push_helper_smoke` @ 2366)
- `tests/test_scheduler.py::TestGHAWorkflow` live at line 344 (WORKFLOW_PATH points at `.github/workflows/daily.yml.disabled`); `TestDeployDocs` live at line 532
- `.github/workflows/daily.yml.disabled` exists; `.github/workflows/daily.yml` absent (confirmed)
- `SETUP-DEPLOY-KEY.md` in phase dir contains `ssh-keygen`, `docs/DEPLOY.md`, and `docs-sweep` tokens
- `git diff --quiet docs/DEPLOY.md` returns clean (file intentionally untouched per REVIEW LOW option (b))

**Test execution (2026-04-24 audit session)**

Full 8-class run across Phase 10 rows:

```
pytest tests/test_main.py::TestHandleReset \
       tests/test_state_manager.py::TestResetState \
       tests/test_notifier.py::test_ruff_clean_notifier \
       tests/test_notifier.py::test_ruff_clean_notifier_detects_f401_regression \
       tests/test_main.py::TestPushStateToGit \
       tests/test_main.py::TestRunDailyCheckPushesState \
       tests/test_scheduler.py::TestGHAWorkflow \
       tests/test_scheduler.py::TestDeployDocs -q
→ 44 passed in 0.69s
```

Full suite (pre-audit orchestrator run): 681 passed in 93.46s.

**Manual-only rows — audit disposition**

The three (well, effectively four with the deferred rewrite) manual-only rows were re-checked for whether any could be promoted to automated coverage:

1. SC-3 droplet deploy-key live push — **confirmed manual-only.** Requires real SSH credentials, network, and GitHub API. No automation path without either a live droplet or a mocked GitHub test harness that would reimplement the whole auth surface. Retain as operator-executed per SETUP-DEPLOY-KEY.md.
2. SC-4 GHA 2-weekday silence — **confirmed manual-only.** Requires 2 wall-clock business days elapsed post-merge + operator inbox observation. Not amenable to automation. Retain as operator-confirmed (matches Phase 7 Wave 2 pattern).
3. Deploy-key commit authorship in GitHub commit log — **confirmed manual-only.** Requires browser/GitHub UI session. Covered by the same live-push sequence as item 1.
4. docs/DEPLOY.md rewrite — **confirmed deferred.** Scoped out to post-Phase-12 docs-sweep phase; not a Phase 10 verification obligation.

Nothing re-classified.

**Frontmatter update**

- `status: draft` → `status: green`
- `nyquist_compliant: false` → `nyquist_compliant: true`
- `wave_0_complete: false` → `wave_0_complete: true`
- Added `audited: 2026-04-24` line

No test files created, modified, or deleted by this audit. No implementation files touched. Only `10-VALIDATION.md` updated.
