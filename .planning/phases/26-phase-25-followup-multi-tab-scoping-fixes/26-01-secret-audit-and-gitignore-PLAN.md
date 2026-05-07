---
phase: 26
plan: 01
type: execute
wave: 0
parallel: false
depends_on: []
files_modified:
  - .gitignore
  - auth.json
autonomous: false
requirements: []
must_haves:
  truths:
    - "auth.json TOTP secret rotated on disk OR confirmed never-committed and operator-acknowledged"
    - ".gitignore covers all leaked artifacts in repo root from `git status`"
    - "AGENTS.md placement decided (root vs .planning/) and committed accordingly"
  artifacts:
    - path: .gitignore
      provides: "Ignore rules for OS junk + agent runtime dirs + debug HTML"
      contains: ".DS_Store"
    - path: .planning/phases/26-phase-25-followup-multi-tab-scoping-fixes/26-01-SUMMARY.md
      provides: "Rotation evidence + history audit log"
      contains: "auth.json"
  key_links:
    - from: ".gitignore"
      to: "git status"
      via: "untracked-files filter"
      pattern: ".DS_Store"
---

<objective>
C1 cleanup. Audit auth.json (real TOTP secret on operator droplet — already gitignored line 2). Verify never landed in commit. Rotate if needed. Extend .gitignore with leaked agent-tooling artifacts. Decide AGENTS.md home.

Purpose: Stop bleed before code changes. Wave 0 ships first, blocks no other plan.
Output: Updated .gitignore, rotation evidence in SUMMARY, AGENTS.md placement decided.
</objective>

<context>
@.planning/STATE.md
@.gitignore
@.planning/phases/26-phase-25-followup-multi-tab-scoping-fixes/26-CONTEXT.md
@.planning/phases/26-phase-25-followup-multi-tab-scoping-fixes/26-PATTERNS.md

<interfaces>
# auth.json schema (from local inspection):
#   schema_version: 1
#   totp_secret: <base32 string>      # REAL secret if non-zero file
#   totp_enrolled: bool
#   totp_enrolled_at: ISO timestamp
#   trusted_devices: []
#   pending_magic_links: []
# Already ignored at .gitignore line 2.
# Audit verdict (run before plan): `git log --all --full-history -- auth.json` → 0 commits (clean).
</interfaces>
</context>

<tasks>

<task type="checkpoint:human-action" gate="blocking">
  <name>Task 1: Audit + rotate auth.json TOTP secret</name>
  <what-built>Pre-flight audit script result.</what-built>
  <how-to-verify>
1. Run `git log --all --full-history -- auth.json` from repo root.
2. Expected: zero commits (auth.json gitignored since inception per .gitignore line 2).
3. If zero commits → file never leaked via git → no rotation strictly required, but operator should still rotate TOTP secret on production droplet because the file sits in plaintext on local dev machine.
4. If any commits exist → IMMEDIATE: rotate TOTP, force-push history rewrite, notify operator.
5. Operator decision: rotate now (fresh enrolment via dashboard `/auth/totp/enroll`) OR accept-as-is with documented rationale in 26-01-SUMMARY.md.
  </how-to-verify>
  <resume-signal>Type "rotated" with new enrolment date, or "accept-as-is" with rationale.</resume-signal>
</task>

<task type="auto">
  <name>Task 2: Extend .gitignore</name>
  <files>.gitignore</files>
  <action>
Append a new section after existing rules, copying the comment style at .gitignore lines 3-6 (multi-line rationale). Add a Phase-26-tagged comment header.

Add these patterns:
```
# Phase 26 cleanup (2026-05-07) — agent runtime + OS junk + debug artefacts
# These appear from MCP tooling, finder metadata, and ad-hoc debug exports.
**/.DS_Store
_debug_new_dashboard.html
.agents/
.claude-flow/
.codex/
.cowork/
.cursor/
.mcp.json
.playwright-mcp/
```
Do NOT add `auth.json`, `state.json`, `last_email.html` — already covered.
Do NOT add `AGENTS.md` — see Task 3.
  </action>
  <verify>
    <automated>git check-ignore -v .DS_Store .agents/x .claude-flow/x .codex/x .cowork/x .cursor/x .mcp.json .playwright-mcp/x _debug_new_dashboard.html backtest/.DS_Store 2>&1 | grep -c gitignore</automated>
  </verify>
  <done>git check-ignore returns 10 hits (one per pattern). git status shows none of the listed files in untracked.</done>
</task>

<task type="checkpoint:decision" gate="blocking">
  <name>Task 3: Decide AGENTS.md placement</name>
  <decision>Where does AGENTS.md live?</decision>
  <context>AGENTS.md sits at repo root, untracked. CONTEXT C1 says "documentation; commit or move to .planning/".</context>
  <options>
    <option id="root">
      <name>Commit at repo root</name>
      <pros>Discoverable on GitHub front page; matches CLAUDE.md convention.</pros>
      <cons>Pollutes root if it's process-only docs.</cons>
    </option>
    <option id="planning">
      <name>Move to .planning/AGENTS.md</name>
      <pros>Matches process-docs convention; root stays clean.</pros>
      <cons>Less discoverable for new contributors.</cons>
    </option>
    <option id="ignore">
      <name>Add to .gitignore</name>
      <pros>If it's per-machine notes, not project-shared.</pros>
      <cons>Loses any shared context.</cons>
    </option>
  </options>
  <resume-signal>Reply: "root", "planning", or "ignore".</resume-signal>
</task>

</tasks>

<verification>
- `git status` shows zero untracked files from the C1 list (all either gitignored or committed).
- `cat .gitignore` contains Phase 26 section.
- 26-01-SUMMARY.md records: auth.json git-history audit verdict, rotation status, AGENTS.md decision.
</verification>

<success_criteria>
- auth.json never appeared in git history (or rotated if it did).
- .gitignore covers .DS_Store (recursive), agent dirs, .mcp.json, _debug_*.html.
- AGENTS.md placed per operator decision.
</success_criteria>

## Threat Model

| Threat ID | Category | Component | Disposition | Mitigation |
|---|---|---|---|---|
| T-26-01 | Information disclosure | auth.json on local FS | mitigate | git history audit + operator-driven TOTP re-enrolment |
| T-26-02 | Information disclosure | leaked .mcp.json (per-machine API tokens) | mitigate | gitignore before any future commit |
| T-26-03 | Tampering | .agents/.claude-flow/.cowork mutable runtime state | accept | runtime-only; not user-supplied; no remote sync |

## Rollback

`git checkout HEAD -- .gitignore` reverts. auth.json rotation is operator-driven; document any new TOTP secret out-of-band.

## Notes

Pattern map: 26-PATTERNS.md §C1.

<output>
Create `.planning/phases/26-phase-25-followup-multi-tab-scoping-fixes/26-01-SUMMARY.md` with:
- Rotation verdict (rotated/accept-as-is + date)
- AGENTS.md placement decision
- .gitignore diff
</output>
