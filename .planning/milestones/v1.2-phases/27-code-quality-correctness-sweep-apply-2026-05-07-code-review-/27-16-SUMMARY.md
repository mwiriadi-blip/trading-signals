---
phase: 27
plan: 16
subsystem: deployment doc-sweep — retire GHA/Replit prose, document DigitalOcean droplet primary
tags:
  - phase-27
  - cleanup
  - deployment-docs
  - droplet-primary
  - post-Phase-12-docs-sweep
dependency_graph:
  requires:
    - 27-15-notifier-py-fossil-cleanup-PLAN.md  # Wave 4 doc-sweep continuation
  provides:
    - "docs/DEPLOY.md describes DigitalOcean droplet + systemd as primary"
    - "Replit removed from active docs (preserved only in v1.0 archive)"
    - "GHA presence in active docs limited to a single rollback-insurance note"
    - "tests/test_scheduler.py::TestDeployDocs rewritten to verify the new shape"
completed: 2026-05-10
---

## Outcome

6 files patched. Zero behavioural diff. Pre-existing failures in `tests/test_main.py` unchanged (verified by stash-test against HEAD).

## Files modified

| File | Change |
|---|---|
| `docs/DEPLOY.md` | Full rewrite — DigitalOcean droplet + systemd primary; SETUP-DROPLET.md cross-references; environment-variable matrix expanded with WEB_AUTH_SECRET/USERNAME, OPERATOR_RECOVERY_EMAIL, BASE_URL, SIGNALS_EMAIL_FROM; new troubleshooting entries (deploy.sh failures, healthz retry exhaustion, magic-link BASE_URL); single GHA note pointing at `daily.yml.disabled` as rollback insurance; Replit removed entirely; 152 lines (target ~150). |
| `README.md` | Stale GHA status badge dropped (workflow is `.disabled` — badge always 404'd); `${{GITHUB_REPOSITORY}}` placeholder paragraph dropped; Quickstart `--once` comment now reads "CI/cron mode"; Documentation list adds SETUP-DROPLET.md as first-class entry; Deployment section rewritten to point at SETUP-DROPLET.md + deploy.sh + docs/DEPLOY.md; 44 lines (was 53). |
| `scheduler_driver.py:122` | Comment: "Replit or GHA runner misconfiguration" → "droplet misconfiguration". |
| `state_actions.py:21` | Comment: "in both droplet systemd / GHA one-shot / Replit schedule modes" → "in droplet systemd one-shot and loop modes". |
| `tests/test_scheduler.py::TestDeployDocs` | Rewritten. Dropped: `test_deploy_md_has_gha_quickstart`, `test_deploy_md_has_replit_alternative`, `test_deploy_md_cost_estimate`, `test_readme_has_gha_status_badge`. Added: `test_deploy_md_describes_droplet`, `test_deploy_md_no_replit_in_active_docs`, `test_deploy_md_gha_disabled_note`, `test_readme_points_at_setup_droplet`, `test_readme_has_no_stale_gha_badge`, `test_readme_has_no_replit`. Kept and tightened: env-var contract test (now requires WEB_AUTH_SECRET/USERNAME, OPERATOR_RECOVERY_EMAIL, BASE_URL, SIGNALS_EMAIL_FROM); troubleshooting test (new required entries: deploy.sh, healthz, magic-link, AssertionError; case-insensitive). `TestGHAWorkflow` (12 tests) untouched — pins disabled workflow contract per Phase 10 INFRA-03. |
| `.planning/PROJECT.md:85,113` | Dropped "stale, rewrite deferred to post-Phase-12 docs-sweep" caveat from `:85` and ", Replit alternative" trailing clause from the v1.1 deployment-decision row at `:113`. Historical Key-Decisions rows at `:107,108` (Python+Resend rationale citing original Replit/GHA fit) preserved verbatim. |

## Verification

```
=== Bucket A (must be 0) ===
Replit in DEPLOY.md: 0
Replit in README: 0
GHA/Replit in scheduler_driver.py + state_actions.py: 0
Stale GHA badge in README: 0

=== Bucket B (must be > 0) ===
v1.0 phase 07 archive: 16 files intact
TestGHAWorkflow class: 1
.github/workflows/daily.yml.disabled: exists
SPEC.md Replit refs (historical brief): 16

=== New shape ===
DEPLOY.md: 152 lines, 1 'DigitalOcean' ref, 5 'SETUP-DROPLET.md' refs
README.md: 44 lines, points at SETUP-DROPLET.md + deploy.sh + DEPLOY.md

=== Tests ===
.venv/bin/pytest tests/test_scheduler.py
45 passed (TestGHAWorkflow:12 + TestDeployDocs:13 + others:20)

.venv/bin/pytest --tb=no -q
17 failed, 2013 passed
(All 17 failures are pre-existing in tests/test_main.py — verified by
stash-test against HEAD. Phase 27-16 introduces zero new failures.)
```

## Bucket B (intentionally preserved)

- `.planning/milestones/v1.0-phases/07-scheduler-github-actions-deployment/` — full v1.0 phase 07 archive (16 files). Phase 07 *was* the GHA deployment; archive must remain unchanged for audit trail.
- `SPEC.md` — original v0 project brief (~16 Replit references). Historical snapshot, not current architecture.
- `.planning/RETROSPECTIVE.md`, `MILESTONES.md`, `STATE.md`, `research/*.md` — historical narrative.
- `.github/workflows/daily.yml.disabled` — rollback insurance per Phase 10 INFRA-03.
- `tests/test_scheduler.py::TestGHAWorkflow` — 12 tests pinning the disabled workflow file's structural contract; rollback-insurance test class.
- `.planning/PROJECT.md:107,108` — historical Key-Decisions rows describing original Python+Resend rationale.

## Pre-existing failures (out-of-scope)

17 tests in `tests/test_main.py` fail on HEAD before this phase (verified by `git stash -u` + targeted re-run). Categories:
- `TestCLI::test_force_email_*` (4)
- `TestCLI::test_test_flag_*`, `test_default_mode_*` (2)
- `TestOrchestrator::*` (5)
- `TestEmailNeverCrash::*` (2)
- `TestRunDailyCheckTupleReturn::*` (2)
- `TestCrashEmailBoundary::*`, `TestWarningCarryOverFlow::*` (2)

These are unrelated to deployment-doc-sweep and should be addressed in a separate debug session.
