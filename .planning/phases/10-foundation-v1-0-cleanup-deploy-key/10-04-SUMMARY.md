---
plan: 10-04
phase: 10-foundation-v1-0-cleanup-deploy-key
requirements_addressed: [INFRA-03]
status: complete
completed: 2026-04-24
---

# Plan 10-04 Summary — INFRA-03 GHA Retirement + Operator Doc + D-19 Prose

## Outcome

Retired the v1.0 GitHub Actions cron workflow so the DigitalOcean droplet systemd unit (Phase 11+) is the sole signal runner. `.github/workflows/daily.yml` renamed to `.disabled` via `git mv` (history preserved; rollback = single reverse git mv). Test-regression path pointer updated via a one-line `WORKFLOW_PATH` constant change covering all 12 `TestGHAWorkflow` tests. New operator runbook `SETUP-DEPLOY-KEY.md` documents the full droplet-side SSH deploy-key setup (6 steps + 6 pitfalls). Prose updates in `CLAUDE.md` and `.planning/PROJECT.md` reflect droplet-primary posture; `docs/DEPLOY.md` intentionally deferred to a post-Phase-12 docs-sweep.

## What was built

**Task 1 — GHA rename + test constant:**
- `git mv .github/workflows/daily.yml .github/workflows/daily.yml.disabled` (history preserved — `git log --follow` traces back to Phase 7 origin)
- `tests/test_scheduler.py:357` `WORKFLOW_PATH` constant updated from `'.github/workflows/daily.yml'` → `'.github/workflows/daily.yml.disabled'` (single-line change covers all 12 TestGHAWorkflow tests per plan D-18 option a)
- README.md badge URL and `TestDeployDocs` assertion left untouched — the badge rendering as "no recent runs" once GHA history ages out IS the intended visual indicator that the workflow is retired

**Task 2 — D-19 prose updates:**
- `CLAUDE.md:46` Deployment line rewritten: droplet-primary + GHA-disabled + docs/DEPLOY.md staleness pointer
- `.planning/PROJECT.md:77` Deployment prose rewritten (same)
- `.planning/PROJECT.md:78` State-persistence prose names `_push_state_to_git` helper + Phase 10 INFRA-02 traceability
- `.planning/PROJECT.md:105` Key Decisions table row rewritten for v1.1 posture
- `.planning/ROADMAP.md` unchanged — spot-check confirmed lines 209 + 215 already v1.1-correct from the earlier roadmap commit
- `docs/DEPLOY.md` INTENTIONALLY untouched per 10-CONTEXT.md Deferred Ideas (`git diff --quiet docs/DEPLOY.md` clean)

**Task 3 — SETUP-DEPLOY-KEY.md operator runbook (234 lines):**
- Quickstart 6-step checklist
- Step 1: ed25519 keypair generation with file-mode 0600/0700 hygiene
- Step 2: GitHub UI deploy-key registration with write access
- Step 3: `~/.ssh/config` block with `IdentitiesOnly yes` (prevents agent-key collision)
- Step 4: HTTPS→SSH remote switch via `git remote set-url`
- Step 5: `ssh -T git@github.com` host-key trust bootstrap
- Step 6: `python main.py --once` first-run bootstrap exercising `_push_state_to_git` + expected log + git-commit authorship
- Pitfalls section: systemd `WorkingDirectory=`, clock drift, deploy-key rotation, rollback procedure, README badge rationale, **and `docs/DEPLOY.md` staleness pointer** (REVIEW-LOW resolution)

## Verification

- **Task 1:** `pytest tests/test_scheduler.py::TestGHAWorkflow tests/test_scheduler.py::TestDeployDocs -q` → 25 passed in 0.47s. `test -f .github/workflows/daily.yml.disabled && ! test -f .github/workflows/daily.yml` → both exit 0. `git log --follow .github/workflows/daily.yml.disabled` traces history back through Phase 7 origin.
- **Task 2:** All grep acceptance checks pass (see commit message). `docs/DEPLOY.md` diff clean.
- **Task 3:** All 11 grep acceptance patterns matched (ssh-keygen, ssh-ed25519, IdentitiesOnly yes, ssh -T git@github.com, git remote set-url, python main.py --once, _push_state_to_git, WorkingDirectory=, 0600, docs/DEPLOY.md, docs-sweep).
- **Full regression suite:** `pytest -x -q` → 681 passed in 93.46s (no regression from Wave 2 baseline).

## Commits

- `11fdd3b` — refactor(10-04): retire GHA cron — git mv daily.yml → daily.yml.disabled (D-16)
- `5c97f6d` — docs(10-04): update CLAUDE.md + PROJECT.md for droplet-primary / GHA-disabled (D-19)
- (pending) docs(10-04): SETUP-DEPLOY-KEY.md operator runbook + INFRA-03 summary

## Acceptance criteria met (per 10-04-PLAN.md)

**Task 1:**
- `test -f .github/workflows/daily.yml.disabled` ✓
- `! test -f .github/workflows/daily.yml` ✓
- `grep -q "WORKFLOW_PATH = '\.github/workflows/daily\.yml\.disabled'" tests/test_scheduler.py` ✓
- `pytest tests/test_scheduler.py::TestGHAWorkflow -q` → 12 passed ✓
- `pytest tests/test_scheduler.py::TestDeployDocs -q` → 13 passed ✓
- Full suite `pytest -q` → 681 passed ✓

**Task 2:**
- `grep -q "DigitalOcean droplet systemd is the primary path" CLAUDE.md` ✓
- `! grep -q "GitHub Actions is the primary path" CLAUDE.md` ✓
- `grep -q "DigitalOcean droplet systemd is the PRIMARY path" .planning/PROJECT.md` ✓
- `grep -q "daily.yml.disabled" CLAUDE.md` ✓
- `grep -q "daily.yml.disabled" .planning/PROJECT.md` ✓
- `grep -q "Phase 10 INFRA-02" .planning/PROJECT.md` ✓
- `grep -q "_push_state_to_git" .planning/PROJECT.md` ✓
- `grep -q "DO droplet systemd PRIMARY (v1.1)" .planning/PROJECT.md` ✓
- `grep -q "docs-sweep\|stale" .planning/PROJECT.md` ✓
- `grep -q "docs-sweep\|stale" CLAUDE.md` ✓
- `git diff --quiet docs/DEPLOY.md` ✓ (REVIEW LOW — deferred)

**Task 3:**
- All 11 grep patterns present in SETUP-DEPLOY-KEY.md (see Verification above)

## Deviations

**Execution path:** Plan executed inline by orchestrator (not spawned executor agent) after the Plan 10-03 executor hit sandbox restrictions. Plan 10-04 is straightforward file rename + prose + new doc (no subprocess mocking or pytest invocation from inside a worktree), so inline execution on main avoids worktree complexity.

**Substantive deviations:** None. All D-16/D-18/D-19 locked decisions honored verbatim. SETUP-DEPLOY-KEY.md content is verbatim from the plan's template. docs/DEPLOY.md intentionally untouched per REVIEW-LOW / 10-CONTEXT.md Deferred Ideas.

## Files modified

- `.github/workflows/daily.yml` → renamed to `daily.yml.disabled` (no content change)
- `tests/test_scheduler.py` — 1 line changed (WORKFLOW_PATH constant)
- `CLAUDE.md` — 1 line changed (Deployment line)
- `.planning/PROJECT.md` — 3 lines changed (Deployment prose + State persistence prose + Key Decisions table row)
- `.planning/phases/10-foundation-v1-0-cleanup-deploy-key/SETUP-DEPLOY-KEY.md` — new, 234 lines

## Files NOT modified (by design)

- `docs/DEPLOY.md` — deferred to post-Phase-12 docs-sweep per 10-CONTEXT.md Deferred Ideas (REVIEW-LOW resolution)
- `README.md` — badge URL left untouched per D-18(a); "no recent runs" rendering is the intended retirement signal
- `.planning/ROADMAP.md` — lines 209 + 215 already v1.1-correct from earlier roadmap commit; no edit needed

## Next

Phase 10 execution complete — all 4 plans green. Next step: `/gsd-verify-work 10` for phase-level verification, then close the milestone.
