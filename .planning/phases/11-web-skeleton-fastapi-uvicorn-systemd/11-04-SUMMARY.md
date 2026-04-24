---
phase: 11
plan: "04"
subsystem: web-skeleton
tags: [operator-runbook, systemd, sudoers, deploy, documentation, tests]
dependency_graph:
  requires:
    - "11-02 (systemd/trading-signals-web.service)"
    - "11-03 (deploy.sh)"
  provides:
    - "SETUP-DROPLET.md — operator one-time setup runbook"
    - "tests/test_setup_droplet_doc.py — doc-completeness + cross-artifact drift guard"
  affects:
    - "Phase 12 operator will follow this runbook then extend it for nginx"
tech_stack:
  added: []
  patterns:
    - "Operator runbook with automated completeness guard (markdown assertions via pytest)"
    - "Cross-artifact drift guard: doc asserts against deploy.sh and systemd unit at test time"
key_files:
  created:
    - SETUP-DROPLET.md
    - tests/test_setup_droplet_doc.py
  modified: []
decisions:
  - "Created SETUP-DROPLET.md as a new sibling doc (not extending Phase 10 SETUP-DEPLOY-KEY.md) — cleaner per-phase separation"
  - "Exact two-rule sudoers entry with /usr/bin/systemctl (Ubuntu LTS default path, verify with `which systemctl`)"
  - "Passwordless sudo verification step added (REVIEWS HIGH #4) to catch sudoers miss before first deploy"
  - ".env marked NOT required in Phase 11 (EnvironmentFile=- in unit file per REVIEWS MEDIUM #5)"
metrics:
  duration: "279 seconds"
  completed: "2026-04-24"
  tasks_completed: 2
  tasks_total: 2
  files_created: 2
  files_modified: 0
---

# Phase 11 Plan 04: SETUP-DROPLET.md Operator Runbook Summary

**One-liner:** Operator runbook with sudoers passwordless-sudo verification step, EnvironmentFile=- optional note, and 37-test cross-artifact drift guard.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Create SETUP-DROPLET.md | a082ab5 | SETUP-DROPLET.md |
| 2 | Write tests/test_setup_droplet_doc.py | b598a21 | tests/test_setup_droplet_doc.py |

## What Was Built

### SETUP-DROPLET.md

7-section operator runbook covering the complete Phase 11 one-time droplet setup:

1. **Prerequisites** — includes `.env` NOT required note (EnvironmentFile=- per REVIEWS MEDIUM #5)
2. **Install systemd unit** — cp, daemon-reload, enable, start, systemd-analyze verify
3. **Install sudoers entry** — `which systemctl` path check, exact two-rule entry, chmod 440, visudo -c -f, **passwordless sudo verification step** (REVIEWS HIGH #4)
4. **Verify port binding (WEB-02 / SC-4)** — ss -tlnp, curl loopback, external negative check
5. **Verify deploy.sh end-to-end (INFRA-04 / SC-3)** — two-run idempotency check
6. **Verify boot persistence (WEB-01 / SC-1)** — sudo reboot + status check
7. **Troubleshooting** — 8-row table; What's NOT in this doc section

Key security posture:
- Anti-pattern WARNING block: NEVER NOPASSWD: ALL, NEVER 0.0.0.0
- Exact sudoers form: `trader ALL=(root) NOPASSWD: /usr/bin/systemctl restart trading-signals, /usr/bin/systemctl restart trading-signals-web`

### tests/test_setup_droplet_doc.py (37 tests, 9 classes)

| Class | Tests | What It Guards |
|-------|-------|----------------|
| TestDocStructure | 7 | All 7 section headings present (load-bearing grep targets) |
| TestSystemdInstall | 6 | Install sequence: cp, daemon-reload, enable, start, status ≥2, systemd-analyze |
| TestSudoersInstall | 8 | Exact sudoers entry; visudo; chmod 440; chown root:root; `which systemctl`; **passwordless-sudo verification step (HIGH #4)** |
| TestEnvFileOptional | 2 | EnvironmentFile=- present; `.env` not-required wording (MEDIUM #5) |
| TestPortBindingVerify | 4 | ss -tlnp; 127.0.0.1:8000 ≥2; curl loopback; external negative |
| TestDeployIdempotency | 3 | bash deploy.sh ≥2; Already up to date ≥2; Requirement already satisfied |
| TestBootPersistence | 1 | sudo reboot present |
| TestAntiPatternWarnings | 3 | NOPASSWD: ALL + NEVER; 0.0.0.0:8000; visudo |
| TestCrossArtifactDriftGuard | 3 | Unit file name matches; smoke URL matches deploy.sh; **sudoers-form matches deploy.sh's two split sudo -n calls (HIGH #4)** |

## Deviations from Plan

None — plan executed exactly as written. The SETUP-DROPLET.md content provided in the plan was followed exactly, including all REVIEWS HIGH #4 and MEDIUM #5 additions.

## Post-REVIEWS Additions Verified

- **REVIEWS HIGH #4** — `sudo -n systemctl restart trading-signals-web` verification step present in `## Install sudoers entry for trader` section. `test_passwordless_sudo_verification_step` asserts this. `test_sudoers_form_matches_deploy_sh_restart_calls` asserts doc's two-rule sudoers form matches deploy.sh's two separate `sudo -n systemctl restart <unit>` lines.
- **REVIEWS MEDIUM #5** — `.env` NOT required note in Prerequisites and Troubleshooting table. `EnvironmentFile=-` reference present. `TestEnvFileOptional` class asserts both.

## Known Stubs

None — SETUP-DROPLET.md is a complete operator runbook. All verification steps reference real Phase 11 artifacts (systemd/trading-signals-web.service, deploy.sh, web/app.py) already committed in Plans 11-01 through 11-03.

## Threat Flags

None — no new network endpoints, auth paths, file access patterns, or schema changes introduced. This plan creates documentation and test files only.

## Self-Check: PASSED

- `SETUP-DROPLET.md` exists: FOUND
- `tests/test_setup_droplet_doc.py` exists: FOUND
- Task 1 commit a082ab5: FOUND (verified in git log)
- Task 2 commit b598a21: FOUND (verified in git log)
- `pytest tests/test_setup_droplet_doc.py -x -q`: 37 passed
- `pytest tests/ -q`: 797 passed (760 prior + 37 new)
- `grep -nE '\*\*[A-Z]+-[0-9]+$' .planning/REQUIREMENTS.md`: ZERO matches (no newline bug)
