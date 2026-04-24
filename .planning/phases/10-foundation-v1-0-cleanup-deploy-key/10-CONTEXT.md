# Phase 10: Foundation — v1.0 Cleanup & Deploy Key — Context

**Gathered:** 2026-04-24
**Status:** Ready for planning
**Revised:** 2026-04-24 (reviews mode — see §Deferred Ideas for docs/DEPLOY.md scoping decision)

<domain>
## Phase Boundary

Close four v1.0 carry-over items before v1.1 feature work starts:

1. **BUG-01** — `reset_state()` sets `state['account']` and `state['initial_account']` coherently so the dashboard total-return formula stops producing spurious +900% results on day one.
2. **CHORE-02** — Clean the 19 pre-existing ruff F401 warnings in `notifier.py`; add a CI regression guard.
3. **INFRA-02** — Droplet-side GitHub deploy key + end-of-run state.json push, preserving the v1.0 "state history in git" durability property after the GHA cron retires.
4. **INFRA-03** — Retire the GHA cron workflow (rename to `.disabled`) so the droplet systemd unit is the sole daily runner (no duplicate emails, no competing state writes).

**No HTTPS, no FastAPI, no domain work** — those start in Phase 11+. Phase 10 is parallelizable with Phase 11 because the files touched are disjoint.

</domain>

<decisions>
## Implementation Decisions

### Area 1 — BUG-01 (defense-in-depth fix)

- **D-01: Fix the immediate bug in `main.py::_handle_reset`.** Add `state['account'] = float(initial_account)` immediately after the existing `state['initial_account'] = float(initial_account)` (currently [main.py:1280](main.py:1280)). One-line change; covers both the CLI-flag path and the interactive-Q&A path because they both flow through the same `_handle_reset` function after argument resolution.

- **D-02: Also extend `state_manager.reset_state()` to accept an optional `initial_account` parameter.** Signature: `reset_state(initial_account: float = INITIAL_ACCOUNT) -> dict`. Inside, both `state['account']` and `state['initial_account']` are set from the parameter. Callers that don't pass it (Phase 3 tests, corrupt-recovery branch inside `load_state`, `_migrate` backfill) keep current behavior via the default value — zero breakage. This tightens the invariant at the module boundary so future callers can't recreate the bug.

- **D-03: Regression tests at two layers.**
  - `tests/test_main.py::TestHandleReset::test_reset_syncs_account_to_initial_account` — parametrized with both CLI-flag path (via `argparse.Namespace(initial_account=10000, spi_contract='spi-mini', audusd_contract='audusd-standard')`) and interactive-Q&A path (monkeypatched `input()` returning `'10000'`). Asserts `state['account'] == state['initial_account'] == 10000.0` after `_handle_reset` completes.
  - `tests/test_state_manager.py::TestResetState::test_reset_state_accepts_custom_initial_account` — direct call `reset_state(initial_account=50000)` asserts both fields equal `50000.0`. Also `test_reset_state_default_preserves_backward_compat` asserts `reset_state()` with no arg still returns `account == initial_account == INITIAL_ACCOUNT` (so existing Phase 3 tests stay green).

### Area 2 — ruff F401 cleanup (hybrid audit)

- **D-04: Audit each of the 19 F401 warnings in `notifier.py` and classify.**
  - **Genuinely unused** → remove the import line
  - **Public re-export** (imported to expose via `from notifier import X` pattern) → add `# noqa: F401  # re-exported for public API` on the same line
  - **Type-only import** (imported for type hints but not used at runtime due to `TYPE_CHECKING` pattern) → move under `if TYPE_CHECKING:` block; no noqa needed
  - Expected split: majority are genuine dead imports from pre-Phase-8 refactoring; ≤3 are likely re-exports. Audit discovers exact split.

- **D-05: New regression test `tests/test_notifier.py::test_ruff_clean_notifier`.**
  - Runs `ruff check notifier.py --output-format=json` via `subprocess.run()`
  - Asserts `returncode == 0` AND the JSON output contains zero entries with `code == 'F401'`
  - Runs in CI by virtue of being in the default test path

- **D-06: Do NOT extend to other source files.** `state_manager.py`, `main.py`, etc. might have their own F401 warnings — those are OUT OF SCOPE for Phase 10. If the CI guard in D-05 proves useful, a follow-up phase can extend to other files. Keep this phase small.

### Area 3 — INFRA-02 (droplet-side deploy key + state push)

- **D-07: Push logic lives in a new `_push_state_to_git(state, now)` helper in `main.py`.** Hex-lite boundary preserved: the helper wraps subprocess calls to git; it does NOT move into `state_manager.py` (which stays I/O-free except for the `state.json` read/write). Helper uses local imports (`import subprocess` inside the function) to match the v1.0 `_send_email_never_crash` pattern — keeps module-level import surface lean.

- **D-08: Push is triggered at the end of `run_daily_check()` after `save_state()` completes successfully.** Flow:
  1. `save_state(state)` — existing Phase 3 atomic write
  2. `_push_state_to_git(state, now)` — new helper; checks if state.json diff is non-empty, commits + pushes if so, skips silently if no change
  3. `run_daily_check` returns as before

- **D-09: Skip-if-unchanged gate via `git diff --quiet state.json`.** Inside the helper:
  ```python
  rc = subprocess.run(['git', 'diff', '--quiet', 'state.json'], capture_output=True).returncode
  if rc == 0:
      logger.info('[State] state.json unchanged — skipping git push')
      return
  ```
  Prevents empty commits on no-op reruns (e.g., `--force-email` after a successful earlier run).

- **D-10: Commit author identity is `DO Droplet <droplet@trading-signals>`** via git's `-c user.email=... -c user.name=...` flags so it doesn't modify the global git config. Non-human email makes it clearly traceable to infrastructure in the commit log. Exact invocation:
  ```python
  subprocess.run([
      'git',
      '-c', 'user.email=droplet@trading-signals',
      '-c', 'user.name=DO Droplet',
      'commit', '-m', 'chore(state): daily signal update [skip ci]',
      'state.json',
  ], check=True)
  ```

- **D-11: Commit message reused verbatim from v1.0 Phase 7 convention:** `chore(state): daily signal update [skip ci]`. The `[skip ci]` tag is vestigial (no CI runs on state commits) but preserves the grep-pattern so tools that looked for v1.0 state commits continue to work.

- **D-12: Fail-loud on push errors; do NOT crash the daily run.** If `subprocess.run(['git', 'push', ...], check=True)` raises `CalledProcessError`:
  1. Log at ERROR with `[State]` prefix. **REVIEW REVISION (10-REVIEWS.md Codex LOW):** commit and push failures emit DISTINCT log verbs — `[State] git commit failed: <stderr excerpt>` vs `[State] git push failed: <stderr excerpt>` — so debugging is not misleading. The earlier spec allowed a single `[State] git push failed` for any CalledProcessError including commit failures; Plan 10-03 Task 1 now splits the except clauses per subcommand.
  2. Call `state_manager.append_warning(state, source='state_pusher', message=f'Nightly state.json <verb> failed: {reason}')` — preserves Phase 8 D-08 sole-writer pattern by going through `append_warning`, NOT touching `state['warnings']` directly.
  3. `save_state(state)` one more time to persist the new warning — this is the ONLY exception to the "two saves per run" invariant from Phase 8 W3; document this explicitly in the helper's docstring. Alternative: rely on next run's normal save cycle to persist the warning. **Adopted approach: rely on next run.** Keeps the two-save invariant clean; worst case, a single missed-push warning is delayed by one run.
  4. NEXT run's email surfaces the missed push via the routine warnings row (Phase 8 age filter picks it up).

- **D-13: No auto-rebase retry in Phase 10.** User selected "fail-loud" over "auto-rebase retry" — merge conflicts on state.json should be rare (only happens if someone pushes a competing state.json from a second droplet or local workstation) and warrant operator investigation, not silent recovery. Captured as deferred if push failures become noisy in production.

- **D-14: Deploy key setup is an operator task, not code.** The droplet-side SSH keypair, GitHub deploy-key registration (with write access), and `~/.ssh/config` routing are one-time setup steps performed by the operator before Phase 10 code can push. Phase 10 plan MUST include a `SETUP-DEPLOY-KEY.md` doc in the phase directory with the exact commands (matches the walkthrough from earlier conversation — ssh-keygen, add public key to GitHub, configure ~/.ssh/config for github.com, switch remote from HTTPS to SSH, verify with `ssh -T git@github.com`). The doc is committed; the code assumes the key is already in place and fails loudly if not (D-12 covers this failure mode).

- **D-15: The `trading-signals-web` systemd unit (Phase 11+) is NOT involved in state pushes.** Only the daily `trading-signals` unit pushes. Web process only reads state (GET /, GET /api/state) — never writes state. This preserves the "one writer" invariant for state.json on the droplet. **Additionally:** the daily runner only pushes when `run_daily_check()` actually ran past the weekday gate and past the `--test` structural read-only gate. Weekend-skip (line 829 `return` before load_state) and `--test` (line 1046 `return` before save_state) MUST NOT invoke `_push_state_to_git`. Plan 10-03 Task 2 adds `test_run_daily_check_does_not_push_on_weekend` and `test_run_daily_check_does_not_push_on_test_mode` to regression-guard this per REVIEW MEDIUM (10-REVIEWS.md Codex).

### Area 4 — INFRA-03 (GHA cron retirement)

- **D-16: Rename `.github/workflows/daily.yml` → `.github/workflows/daily.yml.disabled` via `git mv`.** Preserves full file history (git follows the rename). One `git mv` reverses the decision if the droplet path is ever abandoned. The `.disabled` suffix is explicit documentation that the file is intentionally inactive — not abandoned, not forgotten.

- **D-17: Leave the GitHub repo secrets (`RESEND_API_KEY`, `SIGNALS_EMAIL_TO`) in place.** Unused while GHA is disabled; harmless; useful for quick rollback. If the operator later decides to permanently commit to the droplet path, secrets can be deleted in a separate cleanup sweep (v1.2+).

- **D-18: Update Phase 9's `test_daily_workflow_has_timeout_minutes` regression test.** Currently reads from `.github/workflows/daily.yml`. Two options:
  - **(a)** Update the path to `.github/workflows/daily.yml.disabled` so the regression asserts the disabled file retains the `timeout-minutes: 10` contract. Valuable if we ever re-enable.
  - **(b)** Delete the test entirely (GHA is retired; timeout assertion is moot).
  **Adopted: (a) — update path, keep the assertion.** Zero-cost; protects the rollback path; documents that the disabled file is still well-formed.

- **D-19: PROJECT.md + ROADMAP.md + CLAUDE.md cross-references updated** to reflect droplet-primary, GHA-disabled state. Specifically: PROJECT.md "Deployment target" section, ROADMAP.md "Operator Decisions Baked In" table, any prose that says "GHA is the primary deployment path". Search-and-replace pass during Phase 10 plan. **`docs/DEPLOY.md` is INTENTIONALLY out of scope** per the reviews-mode Deferred Ideas entry below — the file's Quickstart and "What the workflow does" sections describe the GHA-primary path in depth and cannot be surgically edited; the doc needs a broader rewrite that is deferred to a future docs-sweep phase.

### Claude's Discretion

- **Exact log format for push failures (D-12)** — reasonable default: `'[State] git push failed: %s', stderr[:200]`. Planner picks final wording. **Planner decision (reviews mode):** commit-vs-push log verb distinction is LOCKED per D-12 amendment — separate except clauses; REVIEW LOW closed.
- **Whether to use `subprocess.check_output` vs `subprocess.run(check=True)`** — equivalent; pick whichever reads cleaner per codebase convention. **Planner picked:** `subprocess.run(..., check=True, capture_output=True, timeout=...)` across all three calls (diff / commit / push) for uniform error surface and stderr capture for `append_warning`.
- **Order of Phase 10 plan tasks** — recommend: Task 1 = BUG-01 + CHORE-02 (doc-like changes to touchy files), Task 2 = INFRA-02 deploy-key code, Task 3 = INFRA-03 GHA retire + SETUP-DEPLOY-KEY.md + test updates. Planner may reorder.
- **Whether to squash all 4 items into a single plan vs split into 2 plans** — Phase is small (~4hr total); single plan is probably fine. Planner decides based on file overlap and commit atomicity. **Planner picked:** 4 plans across 3 waves (10-01 BUG-01 + 10-02 CHORE-02 parallel Wave 1; 10-03 INFRA-02 Wave 2; 10-04 INFRA-03 Wave 3).
- **Local `import subprocess` vs module-top import** — REVIEW LOW (10-REVIEWS.md): either is acceptable. **Planner picked Option A** per planner-reviews.md discretion — keep local import mirroring `_send_email_never_crash` pattern; Plan 10-03 Task 1 docstring explicitly documents the rationale so future readers understand the convention.

### Folded Todos

None — the `gsd-sdk query todo.match-phase 10` call returned zero matches. No backlog items cross-reference Phase 10 scope.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents (researcher, planner, executor) MUST read these before implementing.**

### Phase spec + scope
- `.planning/ROADMAP.md` §Phase 10 — goal, 4 success criteria, dependency graph
- `.planning/REQUIREMENTS.md` — BUG-01 (line referencing `reset_state()`), CHORE-02 (ruff F401), INFRA-02 (deploy key + nightly push), INFRA-03 (disable GHA cron)
- `.planning/PROJECT.md` — v1.1 Current Milestone architecture; `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/CLAUDE.md` for project conventions (2-space indent, single quotes, log prefixes, hex-lite boundary)

### Prior-phase decisions that constrain Phase 10
- `.planning/milestones/v1.0-phases/03-state-persistence-with-recovery/03-CONTEXT.md` — `state_manager` module contract: sole writer to `state['warnings']`, atomic save via tempfile+fsync+os.replace, `_migrate` chain pattern for schema evolution
- `.planning/milestones/v1.0-phases/07-scheduler-github-actions-deployment/07-CONTEXT.md` — original deployment architecture being replaced; env-var contract for `RESEND_API_KEY` + `SIGNALS_EMAIL_TO`; commit-back pattern via `stefanzweifel/git-auto-commit-action@v5`
- `.planning/milestones/v1.0-phases/07-scheduler-github-actions-deployment/07-03-PLAN.md` — GHA workflow contract (cron, concurrency, permissions) that we're retiring; commit message `chore(state): daily signal update [skip ci]` that we're reusing
- `.planning/milestones/v1.0-phases/08-hardening-warning-carry-over-stale-banner-crash-email-config/08-CONTEXT.md` — D-08 notifier `SendStatus` returns (hex-lite pattern to mirror in `_push_state_to_git`); D-14 underscore-prefix persistence rule; W3 "2 saves per run" invariant (D-12 preserves it)
- `.planning/phases/09-milestone-v1.0-gap-closure/09-VERIFICATION.md` — `test_daily_workflow_has_timeout_minutes` in tests/test_scheduler.py (needs path update per D-18)

### Source files touched by Phase 10
- `main.py` — `_handle_reset()` (line 1129+) for BUG-01 D-01; new `_push_state_to_git()` helper for INFRA-02; `run_daily_check()` end-of-function hook for D-08
- `state_manager.py` — `reset_state()` (line 304) for BUG-01 D-02 signature extension
- `notifier.py` — top-of-file import block for CHORE-02 F401 audit
- `tests/test_main.py` — TestHandleReset extension for D-03
- `tests/test_state_manager.py` — TestResetState extension for D-03
- `tests/test_notifier.py` — new `test_ruff_clean_notifier` for D-05
- `tests/test_scheduler.py` — `test_daily_workflow_has_timeout_minutes` path update for D-18
- `.github/workflows/daily.yml` → rename to `daily.yml.disabled` for D-16
- `.planning/phases/10-foundation-v1-0-cleanup-deploy-key/SETUP-DEPLOY-KEY.md` — new operator setup doc for D-14
- `.planning/PROJECT.md` + `.planning/ROADMAP.md` + `CLAUDE.md` — prose updates for D-19
- `docs/DEPLOY.md` — **NOT in Phase 10 scope**; deferred to future docs-sweep phase per §Deferred Ideas

### Architectural invariants (do not break)
- `CLAUDE.md` §Architecture — hex-lite: `state_manager` stays I/O-narrow (no subprocess, no git calls); `main.py` is the sole orchestrator; `signal_engine` ↔ `state_manager` no cross-import
- `CLAUDE.md` §Conventions — 2-space indent, single quotes, `[Signal]/[State]/[Email]/[Sched]/[Fetch]` log prefixes (new `_push_state_to_git` uses `[State]`), atomic state writes via tempfile+fsync+os.replace
- `tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent` — AST blocklist; Phase 10 adds NO new third-party deps (pure stdlib `subprocess` + `ruff` via CLI — ruff is already pinned in requirements.txt)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable assets
- `state_manager.append_warning(state, source, message, now=None)` (Phase 3) — used by D-12 for the "git push failed" warning path. Clock-injection pattern (now=None default) makes it testable with fixed datetimes.
- `state_manager.save_state()` (Phase 3) — atomic tempfile + fsync + os.replace. Untouched by this phase.
- `main._send_email_never_crash` (Phase 6/8) — template pattern for the new `_push_state_to_git()` helper: local imports inside function, try/except wrapping subprocess, log on failure, return to caller without crashing.
- `notifier._post_to_resend` retry loop (Phase 6) — NOT reused here; git push isn't retried in Phase 10 (fail-loud per D-13).
- v1.0 Phase 7 commit message `chore(state): daily signal update [skip ci]` — reused verbatim per D-11.

### Established patterns
- **Local imports inside `_never_crash` wrappers** — matches `_send_email_never_crash` and `_render_dashboard_never_crash`. Preserves hex boundary at module-import time.
- **Clock injection via `now=None`** — `state_manager.append_warning` takes `now=None` and defaults to `datetime.now(AWST)`. New `_push_state_to_git(state, now=None)` mirrors.
- **Grep-verifiable acceptance criteria** — established in Phase 8/9 plan-checker loop; Phase 10 plans must continue this (no "verified by reading").

### Integration points
- `main.run_daily_check()` — add call to `_push_state_to_git(state, now)` at the very end, after the existing `save_state(state)` call. Position matters: must be after save_state (so state.json reflects today's run) but before return (so push is committed before the function exits).
- `main.main()` outer except boundary (Phase 8 Layer B) — the new helper lives INSIDE `run_daily_check` and its errors are caught by `_run_daily_check_caught` (Layer A per-job never-crash). If the helper itself somehow raises past its try/except, Layer A handles it. No change to Layer B.

</code_context>

<specifics>
## Specific Ideas

- **Defense-in-depth BUG-01 fix.** Both the call-site override (D-01) AND the module-boundary signature change (D-02). The bug is a CONF-01 regression; tightening at two layers means future CONF-flag additions (e.g., CONF-03 if we add per-trade commission customization) can't recreate the same mismatch.

- **Commit message verbatim from v1.0.** `chore(state): daily signal update [skip ci]` — don't invent a new convention when the v1.0 Phase 7 message is already well-known and grep-friendly for log searches.

- **Deploy-key commit author is a fake email intentionally.** `DO Droplet <droplet@trading-signals>` is not a real mailbox. Git accepts any email in the author field; the string's purpose is documentation ("this commit came from the droplet, not a human"). Future tooling that greps `droplet@trading-signals` can identify these commits unambiguously.

- **SETUP-DEPLOY-KEY.md lives in the phase directory, not repo root.** It's a Phase 10 artifact — once executed, it's documentation. If it moves to repo root later (v1.1 publish step), that's a separate decision.

- **The `test_daily_workflow_has_timeout_minutes` test migration (D-18 option (a)) is a minor but deliberate choice.** We could delete the test; instead we update its path. This costs nothing and protects the "restore-GHA" rollback scenario — if the operator ever decides to go back to GHA, the test ensures the disabled file still has the timeout contract. Cheap insurance.

- **Phase 10 adds NO new third-party dependencies.** `subprocess` is stdlib. `ruff` is already pinned at 0.6.9. Keeps the AST forbidden-imports guard happy without any blocklist edits.

</specifics>

<deferred>
## Deferred Ideas

- **Auto-rebase retry on push failure (D-13).** If the fail-loud approach proves too noisy in production (e.g., user pushes competing state.json from a second environment), add a single `git pull --rebase && git push` retry before the warning-and-skip path. v1.2 candidate.

- **Diff-based state.json gate extension.** Currently D-09 skips push when `git diff --quiet state.json` is clean. Could extend to a fingerprint comparison (hash of state contents excluding `last_run` timestamp) to skip pushes where only the timestamp changed. Low value unless push logs become noisy. v1.2 candidate.

- **Deploy key rotation policy.** Production-grade setups rotate SSH deploy keys quarterly. v1.1 ignores this (single-operator, low-stakes). Revisit when/if project moves to team ownership.

- **Repo secrets cleanup.** Per D-17, `RESEND_API_KEY` + `SIGNALS_EMAIL_TO` stay in GitHub Settings during v1.1. Delete them in v1.2+ if the droplet path proves stable and rollback is no longer desired.

- **Extending ruff F401 CI guard to other source files.** Per D-06, only `notifier.py` is in Phase 10 scope. `state_manager.py`, `main.py`, `dashboard.py`, `sizing_engine.py`, `signal_engine.py` may have their own warnings — sweep in a future `chore(quick)` task.

- **test_daily_workflow_has_timeout_minutes test deletion (D-18 option (b)).** If the GHA-rollback scenario is formally abandoned (say, in v1.2 when repo secrets are deleted), delete the test along with `daily.yml.disabled` itself. Until then, keep both as a safety net.

- **`docs/DEPLOY.md` rewrite (REVIEW LOW — codex 10-04 MEDIUM).** The current file (172 lines) describes GHA as the PRIMARY path in its Quickstart, "What the workflow does", and Cost sections, with the Replit alternative in a trailing section. Phase 10 cannot surgically amend this — a v1.1-correct DEPLOY.md needs a full rewrite covering: (1) droplet systemd as primary, (2) SETUP-DEPLOY-KEY.md as the operator-onboarding prerequisite, (3) `deploy.sh` idempotent-update runbook (produced by Phase 11 INFRA-04), (4) nginx + HTTPS wiring (produced by Phase 12), (5) Replit/GHA listed as historical alternatives retained for rollback. **Option (b) adopted per 10-REVIEWS.md — defer to a docs-sweep phase after Phase 12 so the rewrite has the full droplet + HTTPS + web-layer story to describe.** Phase 10's `CLAUDE.md`/`.planning/PROJECT.md` edits (D-19) are sufficient for the immediate rollout; Phase 10's `SETUP-DEPLOY-KEY.md` covers the deploy-key-specific onboarding; `docs/DEPLOY.md` will be rewritten when v1.1 has more infrastructure to document coherently. Gemini did not flag this concern (evaluated Plan 10-04 Task 1 Step C's "leave README badge as retired indicator" decision as the acceptable baseline for current-phase docs posture). Tracking stays in this Deferred Ideas entry until a new docs-sweep phase is scheduled.

### Reviewed Todos (not folded)
None — `gsd-sdk query todo.match-phase 10` returned zero matches.

</deferred>

---

*Phase: 10-foundation-v1-0-cleanup-deploy-key*
*Context gathered: 2026-04-24*
*Reviews-mode revision: 2026-04-24 — D-12 commit-vs-push log distinction locked; D-15 weekend/--test skip coverage locked; D-19 docs/DEPLOY.md scoping locked (deferred); local-import rationale Option A locked*
