# Phase 10: Foundation — v1.0 Cleanup & Deploy Key — Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-24
**Phase:** 10-foundation-v1-0-cleanup-deploy-key
**Areas discussed:** BUG-01 fix location, ruff F401 cleanup strategy, Deploy-key commit workflow, GHA cron retirement

---

## BUG-01 fix location

| Option | Description | Selected |
|--------|-------------|----------|
| main.py _handle_reset() 1-liner (Recommended) | Add `state['account'] = float(initial_account)` after line 1280. Keeps state_manager.reset_state() API pure. | |
| reset_state() takes optional initial_account param | Change reset_state(initial_account=INITIAL_ACCOUNT) so it sets both fields coherently. Cleaner API but touches all callers. | |
| Both — defense-in-depth | Fix the main.py call site AND extend reset_state() to accept the param. More work but tightens invariant at two layers. | ✓ |

**User's choice:** Both — defense-in-depth
**Notes:** Defense-in-depth captured as D-01 (main.py 1-liner) + D-02 (reset_state signature extension). D-03 locks regression tests at both layers. Rationale: BUG-01 is a CONF-01 regression type; tightening at two layers prevents future CONF-flag additions from recreating the same mismatch.

---

## ruff F401 cleanup strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Hybrid audit + CI guard (Recommended) | Audit each F401: remove if unused, add `# noqa: F401  # re-exported` if public re-export. Add test `test_ruff_clean_notifier`. | ✓ |
| Remove all 19 imports | Delete every unused import. Fastest but risks breaking callers relying on transitive re-exports. | |
| Add # noqa: F401 to all 19 | Suppress without removing. Preserves API surface; keeps dead imports. No CI guard needed. | |

**User's choice:** Hybrid audit + CI guard (Recommended)
**Notes:** D-04 covers the audit taxonomy (unused vs re-export vs type-only); D-05 locks the CI guard via `test_ruff_clean_notifier` running `ruff check notifier.py --output-format=json` and asserting zero F401 entries; D-06 explicitly scopes the guard to notifier.py only — other source files are out of scope for this phase to keep blast radius small.

---

## Deploy-key commit workflow (push-when + author + conflict handling)

| Option | Description | Selected |
|--------|-------------|----------|
| End-of-run push + bot author + fail-loud (Recommended) | Push at end of run_daily_check when state changed. Author `DO Droplet <droplet@trading-signals>`. Message `chore(state): daily signal update [skip ci]` (v1.0 convention). Push failure logs ERROR + next run's warning surfaces it. | ✓ |
| End-of-run push + bot author + auto-rebase retry | Same identity, but on push failure: `git pull --rebase` then retry once. Recovers from most conflicts automatically. | |
| Nightly timer + diff-gate + bot author | Systemd timer at 01:00 AWST: only pushes if `git diff --quiet` is non-empty. Decouples push from run; avoids empty commits. | |

**User's choice:** End-of-run push + bot author + fail-loud (Recommended)
**Notes:** Captured as D-07 through D-15. Key points: push logic lives in new `main._push_state_to_git()` helper (D-07) to preserve hex-lite boundary (state_manager stays subprocess-free); skip-if-unchanged gate via `git diff --quiet state.json` (D-09) prevents empty commits; fail-loud path goes through `state_manager.append_warning` (D-12) to preserve Phase 8 D-08 sole-writer invariant; auto-rebase retry explicitly deferred (D-13) — captured in deferred-ideas for v1.2 if push failures become noisy. D-14 separates operator setup (SSH keypair, GitHub deploy-key registration) from code; SETUP-DEPLOY-KEY.md lives in phase directory as one-time setup doc.

---

## GHA cron retirement method

| Option | Description | Selected |
|--------|-------------|----------|
| Rename to .disabled, keep secrets (Recommended) | `git mv daily.yml daily.yml.disabled`. Reversible. Secrets stay as rollback insurance. | ✓ |
| Delete file + remove secrets | Clean slate. Removes all GHA artifacts. To revert, restore file from git and re-add secrets. | |
| Keep file, add `if: false` guard | File stays as documentation. No actual runs. Least destructive but confusing (contract looks active). | |

**User's choice:** Rename to .disabled, keep secrets (Recommended)
**Notes:** D-16 (rename via `git mv` to preserve history), D-17 (secrets stay in place as rollback insurance), D-18 (update Phase 9's `test_daily_workflow_has_timeout_minutes` to read from the .disabled path — keeps the contract assertion valid and protects the restore-GHA scenario), D-19 (PROJECT.md + ROADMAP.md + CLAUDE.md prose updates to reflect droplet-primary + GHA-disabled status).

---

## Claude's Discretion

Per D-Claude: exact log format for push failures (planner picks), `subprocess.check_output` vs `subprocess.run(check=True)` (equivalent — planner picks cleaner read), order of Phase 10 plan tasks (recommend BUG → CHORE → INFRA but planner may reorder), single vs split plan (phase is small — likely single plan, planner decides).

## Deferred Ideas

- Auto-rebase retry on push failure (v1.2 candidate if fail-loud proves noisy)
- Diff-based state.json gate extension (fingerprint vs simple diff) — v1.2
- Deploy key rotation policy — out of scope for single-operator phase
- Repo secrets cleanup — v1.2+ once droplet path is proven
- Extending ruff F401 CI guard to other source files — future chore sweep
- `test_daily_workflow_has_timeout_minutes` deletion (D-18 option b) — if GHA rollback is formally abandoned
