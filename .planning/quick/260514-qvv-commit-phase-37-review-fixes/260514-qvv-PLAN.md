---
phase: quick
plan: 260514-qvv
type: execute
wave: 1
depends_on: []
files_modified:
  - auth_store/_users.py
  - system_params.py
  - tests/test_web_admin_invite.py
  - tests/test_web_invite.py
  - tests/test_rate_limit_constants.py
  - web/routes/admin/__init__.py
  - web/routes/admin/_renderers.py
  - web/routes/invite/__init__.py
  - web/routes/invite/_renderers.py
  - .planning/phases/37-per-user-email-fan-out-admin-invite-disable-routes-invite-ac/37-01-PLAN.md
  - .planning/phases/37-per-user-email-fan-out-admin-invite-disable-routes-invite-ac/37-02-PLAN.md
  - .planning/phases/37-per-user-email-fan-out-admin-invite-disable-routes-invite-ac/37-03-PLAN.md
  - .planning/phases/37-per-user-email-fan-out-admin-invite-disable-routes-invite-ac/37-04-PLAN.md
  - .planning/phases/37-per-user-email-fan-out-admin-invite-disable-routes-invite-ac/37-05-PLAN.md
autonomous: true
requirements: []

must_haves:
  truths:
    - "Full test suite passes (Python 3.13)"
    - "All Phase 37 code-review fixes (CR-01..CR-04, WR-01..WR-05, IN-01..IN-03) are recorded in a single commit"
    - "Phase 37 planning doc edits committed alongside the code fixes"
    - "No secrets, .env, or .planning/LEARNINGS.md scratch files included"
  artifacts:
    - path: ".planning/phases/37-per-user-email-fan-out-admin-invite-disable-routes-invite-ac/37-REVIEW-FIX.md"
      provides: "Source-of-truth for finding-by-finding fix scope (already on disk)"
  key_links:
    - from: "37-REVIEW-FIX.md"
      to: "git commit message"
      via: "commit body lists CR/WR/IN ids"
      pattern: "CR-0[1-4]|WR-0[1-5]|IN-0[1-3]"
---

<objective>
Verify Phase 37 code-review fixes pass tests, then commit all uncommitted changes (code + planning docs) in a single review-fix commit.

Purpose: Close the loop on 12 review findings already implemented in working tree but not yet committed.
Output: One clean git commit referencing 37-REVIEW-FIX.md.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
</execution_context>

<context>
@.planning/phases/37-per-user-email-fan-out-admin-invite-disable-routes-invite-ac/37-REVIEW-FIX.md
@.planning/phases/37-per-user-email-fan-out-admin-invite-disable-routes-invite-ac/37-REVIEW.md
@CLAUDE.md
</context>

<tasks>

<task type="auto">
  <name>Task 1: Run full test suite to confirm fixes hold</name>
  <files>(no edits — verification only)</files>
  <action>
    Run the full pytest suite with the project venv to confirm Phase 37 review fixes still pass. The 37-REVIEW-FIX.md doc claims 2325 passed at fix time — verify nothing has regressed in the working tree since.

    Command: `.venv/bin/pytest -x --tb=short`

    If failures appear, STOP and surface them — do not commit. Do NOT run `ruff format` (CLAUDE.md: 2-space indent must be preserved).
  </action>
  <verify>
    <automated>.venv/bin/pytest -x --tb=short 2>&1 | tail -20</automated>
  </verify>
  <done>Test suite exits 0 with passing count consistent with 37-REVIEW-FIX.md (~2325 passed, 2 skipped, 0 failures).</done>
</task>

<task type="auto">
  <name>Task 2: Stage and commit review fixes with traceable message</name>
  <files>
    auth_store/_users.py,
    system_params.py,
    tests/test_web_admin_invite.py,
    tests/test_web_invite.py,
    tests/test_rate_limit_constants.py,
    web/routes/admin/__init__.py,
    web/routes/admin/_renderers.py,
    web/routes/invite/__init__.py,
    web/routes/invite/_renderers.py,
    .planning/phases/37-per-user-email-fan-out-admin-invite-disable-routes-invite-ac/37-01-PLAN.md,
    .planning/phases/37-per-user-email-fan-out-admin-invite-disable-routes-invite-ac/37-02-PLAN.md,
    .planning/phases/37-per-user-email-fan-out-admin-invite-disable-routes-invite-ac/37-03-PLAN.md,
    .planning/phases/37-per-user-email-fan-out-admin-invite-disable-routes-invite-ac/37-04-PLAN.md,
    .planning/phases/37-per-user-email-fan-out-admin-invite-disable-routes-invite-ac/37-05-PLAN.md
  </files>
  <action>
    Stage ONLY the files listed above by name (do NOT use `git add -A` or `git add .` — the working tree contains other untracked files like `.planning/LEARNINGS.md`, backtest JSON, REVIEW/REVIEWS docs, and a state.json backup that must NOT be in this commit).

    Run `git status` first to confirm working tree shape, then `git diff --stat` on the staged set to sanity-check.

    Stage the new test file explicitly: `tests/test_rate_limit_constants.py` (currently untracked per git status).

    Commit message (HEREDOC):

    ```
    fix(37): address code-review findings — 12 fixed (CR-01..CR-04, WR-01..WR-05, IN-01..IN-03)

    Security:
    - CR-01: drop raw invite token from admin issue-invite response
    - CR-02: store sha256 token_hash in wizard cookie, raw token in hidden form field
    - CR-04: disable-user PATCH reads `disabled` from Form body, not query string
    - WR-01: validate invite email format before minting token (422 on bad input)
    - WR-02: 403 when admin_uid cannot be resolved during invite issuance
    - WR-03: URL-escape token_hash in hx-delete attribute

    Correctness:
    - CR-03: create_user persists password_hash field (None for admin rows)
    - WR-04: new test_rate_limit_constants.py guards drift between system_params
      and web.middleware.auth rate-limit constants
    - WR-05: corrected misleading timing-safe docstring in _peek_invite_token

    Cleanup:
    - IN-01: removed dead user_devices loop in admin_list_users
    - IN-02: replaced relative path in test with Path(__file__) resolution
    - IN-03: extracted INVITE_WIZARD_TTL_SECONDS to system_params

    Phase 37 plan docs (37-01..37-05) updated to reflect post-review state.

    Test result: 2325 passed, 2 skipped, 0 failures.
    Ref: .planning/phases/37-.../37-REVIEW-FIX.md

    Co-Authored-By: RuFlo <ruv@ruv.net>
    ```

    After commit, run `git status` to verify only the intended files were committed and the untracked LEARNINGS/REVIEW/backtest files are still untracked (not lost, not committed).
  </action>
  <verify>
    <automated>git log -1 --stat --format='%s%n%n%b' | head -60 && git status --short | head -30</automated>
  </verify>
  <done>
    Single commit exists with message referencing CR-01..CR-04, WR-01..WR-05, IN-01..IN-03. Only the 14 intended files (9 code + 5 plan docs) appear in the commit. `.planning/LEARNINGS.md`, backtest JSON, REVIEW/REVIEWS markdown, and state.json backup remain untracked.
  </done>
</task>

</tasks>

<verification>
- `.venv/bin/pytest -x --tb=short` passes
- `git log -1` shows the review-fix commit
- `git status` shows only the previously-untracked planning docs (LEARNINGS, REVIEWS, backtests, state backup) still uncommitted
</verification>

<success_criteria>
- Test suite green
- One commit on `main` with finding IDs in the body
- No secrets, no .env, no scratch files included
- Working tree free of the 9 code files + 5 plan doc files
</success_criteria>

<output>
After completion, no SUMMARY file required (quick mode). Return commit SHA to user.
</output>
