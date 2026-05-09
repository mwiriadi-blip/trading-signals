---
phase: 27
plan: 16
type: execute
wave: 4
parallel: false
depends_on:
  - 27-15-notifier-py-fossil-cleanup-PLAN.md  # Wave 4 doc-sweep continuation
files_modified:
  - docs/DEPLOY.md
  - README.md
  - scheduler_driver.py
  - state_actions.py
  - tests/test_scheduler.py
  - .planning/PROJECT.md
autonomous: true
requirements: []
must_haves:
  truths:
    - "docs/DEPLOY.md describes DigitalOcean droplet + systemd as the PRIMARY (and only documented) deployment path."
    - "Replit alternative is removed from active docs entirely (preserved only in v1.0 milestone archive)."
    - "GitHub Actions presence in active docs is limited to a single line noting `.github/workflows/daily.yml.disabled` as rollback insurance per Phase 10 INFRA-03."
    - "README.md Deployment section points at `SETUP-DROPLET.md` + `deploy.sh` + `docs/DEPLOY.md`. The stale GHA status badge is removed."
    - "tests/test_scheduler.py::TestDeployDocs assertions match the new doc shape (droplet-primary). TestGHAWorkflow is preserved unchanged — it pins `.github/workflows/daily.yml.disabled` as rollback insurance."
    - "scheduler_driver.py:122 + state_actions.py:21 inline comments describe the DO droplet path; Replit/GHA prose removed from CURRENT-architecture comments."
    - "Full test suite green post-edit."
  artifacts:
    - path: docs/DEPLOY.md
      provides: "operator runbook — DO droplet primary"
      contains: "DigitalOcean"
    - path: README.md
      provides: "Deployment section pointing at SETUP-DROPLET.md + deploy.sh"
      contains: "SETUP-DROPLET.md"
    - path: tests/test_scheduler.py
      provides: "TestDeployDocs rewritten; TestGHAWorkflow preserved (rollback insurance)"
      contains: "DigitalOcean"
  key_links:
    - from: "README.md Deployment section"
      to: "SETUP-DROPLET.md"
      via: "markdown link"
      pattern: "SETUP-DROPLET.md"
    - from: "docs/DEPLOY.md"
      to: "SETUP-DROPLET.md"
      via: "first-class reference for one-time droplet bring-up"
      pattern: "SETUP-DROPLET.md"
---

## Context

`.planning/PROJECT.md:85` records: *"DO droplet systemd is the PRIMARY path (Phase 11 onwards). GitHub Actions cron is disabled... Replit Always On remains documented as an alternative (see `docs/DEPLOY.md` — stale, rewrite deferred to post-Phase-12 docs-sweep per 10-CONTEXT.md Deferred Ideas)."*

This plan retires that deferral. After 27-16, the active docs reflect the actual deployment surface: DigitalOcean droplet + systemd + nginx + deploy.sh. Replit is removed from active docs entirely. GHA appears only as a single-line note about the disabled rollback-insurance workflow.

**Bucket A — REWRITE (active surface, currently misleading):**

- `docs/DEPLOY.md` — full rewrite. Stale GHA-primary / Replit-alternative content replaced with droplet-primary content + pointer at `SETUP-DROPLET.md` (the real one-time setup runbook).
- `README.md` — drop GHA status badge (workflow file is `.disabled`, badge 404s); rewrite Deployment section + Quickstart comment + DEPLOY.md description.
- `scheduler_driver.py:122` — drop "Replit or GHA runner misconfiguration" comment; mention droplet/UTC.
- `state_actions.py:21` — drop "GHA one-shot / Replit schedule modes"; mention droplet systemd.
- `tests/test_scheduler.py::TestDeployDocs` — rewrite assertions to verify the new doc shape. `TestGHAWorkflow` is preserved unchanged (it pins the disabled workflow file's structure as rollback insurance per Phase 10 INFRA-03 — that contract is still active).
- `.planning/PROJECT.md:85,113` — drop "stale, rewrite deferred" caveat + drop "Replit alternative" trailing clause from the v1.1 deployment-decision row.

**Bucket B — PRESERVE (history / archive / rollback insurance):**

- `.planning/milestones/v1.0-phases/07-scheduler-github-actions-deployment/*` — phase 07 archive in full (whole phase WAS the GHA deployment).
- `SPEC.md` — original Replit-targeted v0 spec (project brief).
- `.planning/RETROSPECTIVE.md`, `MILESTONES.md`, `STATE.md` historical entries, `research/*.md` — historical decision context.
- `.github/workflows/daily.yml.disabled` — rollback insurance per Phase 10 INFRA-03.
- `tests/test_scheduler.py::TestGHAWorkflow` — pins disabled workflow shape (rollback insurance).
- `tests/test_setup_droplet_doc.py`, `tests/test_setup_https_doc.py`, `tests/test_deploy_sh.py` — already droplet-shaped, untouched.
- `.planning/PROJECT.md:107,108` — historical "Key Decisions" rows describing why Python + yfinance + Resend was picked originally (because "runs on Replit/GHA"). Preserved as audit trail.

<objective>
Rewrite the deployment-related active docs and source comments to describe the DigitalOcean droplet path that's been live since Phase 11. Remove Replit from active docs. Keep GHA presence to a single line noting the disabled rollback workflow.

Comment + doc + test edits only. Zero runtime-behaviour change. Production deploy artifacts (`deploy.sh`, `systemd/trading-signals-web.service`, sudoers entry) are untouched.

Output: 6 files patched; 0 behavioural diffs; full test suite still green.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/PROJECT.md
@SETUP-DROPLET.md
@deploy.sh
@systemd/trading-signals-web.service
@.github/workflows/daily.yml.disabled

<interfaces>
# New docs/DEPLOY.md structure (target ~150 lines, must satisfy
# TestDeployDocs::test_deploy_md_length_sane after rewrite — see Task 5):
#
#   # DEPLOY.md — operator runbook
#   ## TL;DR (DigitalOcean droplet)
#   ## Architecture (units + nginx + state.json deploy-key push-back)
#   ## One-time bring-up (link to SETUP-DROPLET.md)
#   ## Routine deploys (deploy.sh; sudoers; healthz retry loop)
#   ## Environment variables (RESEND_API_KEY, SIGNALS_EMAIL_TO,
#                              WEB_AUTH_SECRET, WEB_AUTH_USERNAME,
#                              OPERATOR_RECOVERY_EMAIL, BASE_URL,
#                              SIGNALS_EMAIL_FROM)
#   ## Local development (Python 3.13 venv; TZ=UTC for default loop mode;
#                          --once / --test / --reset bypass UTC assertion)
#   ## Troubleshooting (no email arrived; DataFetchError; deploy.sh failures;
#                       healthz retry exhausted; magic-link email not sent;
#                       AssertionError process tz must be UTC)
#   ## Notes (GHA workflow disabled; Replit retired; SPEC.md is historical)
#
# tests/test_scheduler.py::TestDeployDocs new assertions:
#   - test_deploy_md_exists                 — keep
#   - test_readme_exists                    — keep
#   - test_deploy_md_describes_droplet      — NEW (replaces gha_quickstart):
#       'DigitalOcean' in content AND 'systemd' in content AND
#       'SETUP-DROPLET.md' in content AND 'deploy.sh' in content
#   - test_deploy_md_no_replit_in_active_docs — NEW: 'Replit' NOT in content
#       (Replit retired from active docs; archive paths untouched)
#   - test_deploy_md_gha_disabled_note      — NEW: 'daily.yml.disabled' in content
#   - test_deploy_md_env_var_contract       — keep + extend with WEB_AUTH_SECRET,
#                                              WEB_AUTH_USERNAME, BASE_URL
#   - test_deploy_md_troubleshooting_section — keep; NEW required entries:
#       'no email arrived', 'DataFetchError', 'AssertionError', 'deploy.sh',
#       'healthz', 'magic-link'
#       (drop 'commit conflict', 'Replit', '[skip ci]', 'no state.json commit',
#        'later than 08:00 AWST' — these were GHA-specific)
#   - test_deploy_md_local_dev_tz_note      — keep verbatim
#   - test_readme_points_at_deploy_md       — keep
#   - test_readme_has_quickstart_commands   — keep
#   - test_readme_points_at_setup_droplet   — NEW: 'SETUP-DROPLET.md' in README
#   - test_readme_has_no_stale_gha_badge    — NEW:
#       'actions/workflows/daily.yml/badge.svg' NOT in README content
#   - test_deploy_md_length_sane            — keep (allow 100-300 range)
#   DROPPED:
#   - test_deploy_md_has_gha_quickstart     — REMOVED
#   - test_deploy_md_has_replit_alternative — REMOVED
#   - test_deploy_md_cost_estimate          — REMOVED (GHA tier minutes irrelevant)
#   - test_readme_has_gha_status_badge      — REMOVED (badge dropped)
#
# scheduler_driver.py:122 — replace
#   "other tz — Replit or GHA runner misconfiguration would otherwise silently"
# with
#   "other tz — droplet misconfiguration would otherwise silently"
#
# state_actions.py:21 — replace
#   "in both droplet systemd / GHA one-shot / Replit schedule modes; no"
# with
#   "in droplet systemd one-shot and loop modes; no"
#
# .planning/PROJECT.md:85 — replace the parenthetical
#   "...remains documented as an alternative (see `docs/DEPLOY.md` — stale,
#    rewrite deferred to post-Phase-12 docs-sweep per 10-CONTEXT.md Deferred Ideas)."
# with
#   "is retired from active docs as of Phase 27-16 (preserved only in the
#    v1.0 milestone archive)."
#
# .planning/PROJECT.md:113 — drop the trailing ", Replit alternative" from the
# decision row text.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Rewrite docs/DEPLOY.md to droplet-primary</name>
  <read_first>
    - docs/DEPLOY.md (current, 173 lines, GHA-primary)
    - SETUP-DROPLET.md (droplet bring-up runbook)
    - deploy.sh (deploy script — sudoers, healthz retry)
    - systemd/trading-signals-web.service (web unit)
    - .github/workflows/daily.yml.disabled (rollback workflow contract)
    - .planning/PROJECT.md (deployment-state ground truth)
  </read_first>
  <action>
1. Replace `docs/DEPLOY.md` content per the new structure in `<interfaces>` above. Target ~150 lines (sanity range 100-300 per length test).
2. Single GHA mention is one line in `## Notes` referencing `.github/workflows/daily.yml.disabled` as rollback insurance per Phase 10 INFRA-03.
3. NO `Replit` substring anywhere in active body.
4. `SETUP-DROPLET.md` appears at least twice (one-time bring-up + a back-reference in environment variables section).
5. `deploy.sh` appears in routine deploys section.
6. Local-development section keeps `TZ=UTC` guidance (the assertion is still live in scheduler_driver.py).
  </action>
  <done>
    - docs/DEPLOY.md fully rewritten.
    - `grep -c 'Replit' docs/DEPLOY.md` returns 0.
    - `grep -c 'DigitalOcean\|droplet\|systemd' docs/DEPLOY.md` returns ≥ 5.
    - `grep -c 'SETUP-DROPLET.md' docs/DEPLOY.md` returns ≥ 2.
    - `grep -c 'daily.yml.disabled' docs/DEPLOY.md` returns ≥ 1.
    - `grep -c 'TZ=UTC' docs/DEPLOY.md` returns ≥ 1.
    - Length 100-300 lines.
  </done>
</task>

<task type="auto">
  <name>Task 2: Rewrite README.md Deployment section + drop stale GHA badge</name>
  <read_first>
    - README.md (current — 53 lines)
  </read_first>
  <action>
1. Drop the GHA status badge line (line 3) and its setup paragraph (lines 11-16) — workflow is `.disabled` so the badge always shows missing-workflow.
2. Update Quickstart comment line 26: `--once # one-shot run (CI/cron mode)` (drop "GitHub Actions").
3. Update Documentation entry line 38: change "(GitHub Actions + Replit setup, env vars, troubleshooting)" → "(droplet runbook, env vars, troubleshooting)".
4. Replace the `## Deployment` section (lines 49-52) with:
   ```
   ## Deployment

   - **Primary:** DigitalOcean droplet + systemd. See [SETUP-DROPLET.md](SETUP-DROPLET.md) for the one-time bring-up runbook (web unit + sudoers + auth secrets + nginx wiring per Phase 11–13).
   - **Routine deploys:** SSH to the droplet and run `bash deploy.sh` — fast-forward pull from `origin/main`, refresh deps, restart `trading-signals` + `trading-signals-web` units, healthz-gated.
   - **Operator runbook:** [docs/DEPLOY.md](docs/DEPLOY.md) — env vars, daily-run schedule, troubleshooting.
   ```
  </action>
  <done>
    - README.md no longer contains `actions/workflows/daily.yml/badge.svg`.
    - README.md no longer contains `${{GITHUB_REPOSITORY}}` placeholder.
    - README.md no longer contains `Replit`.
    - `grep -c 'SETUP-DROPLET.md' README.md` returns ≥ 1.
    - `grep -c 'deploy.sh' README.md` returns ≥ 1.
    - `python main.py --once|--test|--reset|<default>` Quickstart commands still listed.
  </done>
</task>

<task type="auto">
  <name>Task 3: Patch source comments (scheduler_driver.py, state_actions.py)</name>
  <read_first>
    - scheduler_driver.py — lines 115-130
    - state_actions.py — lines 15-25
  </read_first>
  <action>
1. scheduler_driver.py:122 — replace "Replit or GHA runner misconfiguration" with "droplet misconfiguration".
2. state_actions.py:21 — replace "in both droplet systemd / GHA one-shot / Replit schedule modes" with "in droplet systemd one-shot and loop modes".
  </action>
  <done>
    - `grep -c 'Replit\|GHA' scheduler_driver.py state_actions.py` returns 0.
    - Comments still describe the single-threaded UTC invariant + module-level assignment safety.
  </done>
</task>

<task type="auto">
  <name>Task 4: Rewrite tests/test_scheduler.py::TestDeployDocs</name>
  <read_first>
    - tests/test_scheduler.py — lines 625-774
  </read_first>
  <action>
1. Replace the `class TestDeployDocs` block (lines 625-773) with the new assertions per `<interfaces>` above.
2. `TestGHAWorkflow` is UNTOUCHED — it pins the disabled workflow's contract as rollback insurance per Phase 10 INFRA-03.
3. New assertions explicitly verify the absence of stale Replit / GHA-badge references in active docs.
  </action>
  <done>
    - `pytest -x tests/test_scheduler.py` passes.
    - `TestGHAWorkflow` still has 12 tests; all pass.
    - `TestDeployDocs` test count: 11 (was 13; -2 dropped: gha_quickstart, replit_alternative, cost_estimate, gha_status_badge; +2 added: setup_droplet_link, no_stale_gha_badge, gha_disabled_note, droplet_described, no_replit_active).
  </done>
</task>

<task type="auto">
  <name>Task 5: Update .planning/PROJECT.md (drop stale-doc caveat + Replit-alternative clause)</name>
  <read_first>
    - .planning/PROJECT.md — lines 85, 113
  </read_first>
  <action>
1. PROJECT.md:85 — replace the parenthetical per `<interfaces>`.
2. PROJECT.md:113 — drop the trailing ", Replit alternative" from the v1.1 deployment-decision row.
  </action>
  <done>
    - PROJECT.md:85 no longer says "stale, rewrite deferred".
    - PROJECT.md:113 no longer says "Replit alternative".
    - Historical rows at PROJECT.md:107,108 (Key Decisions describing original Python+Resend rationale) are preserved verbatim — they document v1.0 reasoning.
  </done>
</task>

<task type="auto">
  <name>Task 6: Final regression + summary</name>
  <action>
1. Run `pytest -x` (full suite). Must pass.
2. Confirm Bucket B preserved:
   ```bash
   ls .planning/milestones/v1.0-phases/07-scheduler-github-actions-deployment/  # archive intact
   grep -c 'Replit' SPEC.md      # >> 0 (historical spec preserved)
   grep -c 'TestGHAWorkflow' tests/test_scheduler.py  # >= 1
   ls .github/workflows/daily.yml.disabled  # exists
   ```
3. Confirm Bucket A clean:
   ```bash
   grep -c 'Replit' docs/DEPLOY.md README.md tests/test_scheduler.py  # all 0
   grep -c 'GitHub Actions' docs/DEPLOY.md  # 0 or 1 (single rollback-note mention permitted)
   ```
4. Write `27-16-SUMMARY.md`.
5. Mark Phase 27-16 complete in ROADMAP.md.
  </action>
  <done>
    - Full suite green.
    - Bucket B preserved.
    - Bucket A clean.
    - SUMMARY + ROADMAP updated.
  </done>
</task>

</tasks>

## Out-of-scope (explicit)

- `SPEC.md` — original v0 spec brief; ~15-20 Replit references. This is a historical project-brief snapshot, NOT current architecture. Preserved verbatim.
- `.planning/RETROSPECTIVE.md`, `STATE.md`, `MILESTONES.md`, `research/*.md` — historical narrative; preserved.
- `.planning/milestones/v1.0-phases/07-scheduler-github-actions-deployment/*` — phase 07 archive; preserved (whole phase 07 WAS the GHA deployment).
- `.github/workflows/daily.yml.disabled` — rollback insurance per Phase 10 INFRA-03.
- `tests/test_scheduler.py::TestGHAWorkflow` — pins the disabled workflow's structural contract; rollback-insurance test class.
- `deploy.sh`, `systemd/*.service`, sudoers entry — production deploy artifacts; not touched.
