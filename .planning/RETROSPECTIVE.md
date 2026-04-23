# Retrospective — Trading Signals

Living retrospective; append new milestone sections at the top.

## Milestone: v1.0 — MVP Mechanical Signal System

**Shipped:** 2026-04-24
**Timeline:** 4 days (2026-04-20 → 2026-04-24)
**Phases:** 9 | **Plans:** 33 | **Commits:** 250 | **Tests:** 662 (all green)

### What Was Built

A GitHub-Actions-scheduled Python CLI that fetches yfinance data for SPI 200 + AUD/USD, computes deterministic ATR/ADX/momentum-vote signals, sizes positions with trailing-stop + pyramiding, renders an HTML dashboard, emails the operator via Resend at 08:00 AWST weekdays, persists atomic state with corruption recovery, and handles crashes with a last-ditch crash-email boundary. Signal-only — no live trading. 80 requirements verified; hex-lite architecture enforced by AST blocklist.

### What Worked

- **GSD discipline end-to-end.** Every phase went through discuss (mostly) → research/pattern-map → plan → checker → execute → verify. Checker caught 5 blockers in Phase 8 (iteration 1) before they reached execution — saved what would have been a multi-hour debug cycle around the warning-carry-over flow (`B1` append-before-clear would have wiped the notifier-failure warning).
- **Cross-AI review as a gating step.** The Gemini + Codex review after Phase 8 planning surfaced `_LAST_LOADED_STATE=None` (Codex MEDIUM) and the silent-failure gap (Codex MEDIUM) before Phase 8 executed. These would have cost a full verification cycle to discover post-execution.
- **Pattern mapper agent.** On Phase 8 the mapper found every analog file with line-number excerpts in one shot — the planner cited them verbatim and executors replicated them without drift.
- **Worktree isolation for parallel waves.** Worked cleanly for Phase 8 (sequential 3-wave chain on a shared context). The LEARNINGS.md warning about worktree agents editing main was honoured; when Phase 8 executor wrote STATE/ROADMAP to main instead of the worktree, it was caught and reverted pre-merge.
- **Plan-checker's grep-verifiable acceptance bar.** After Phase 8 iteration 1 flagged "pattern shifts"/"verified by reading" as non-automatable, every subsequent plan was strictly grep/python/pytest-verifiable. No subjective criteria made it past execution.
- **Code-review-fix iteration loop.** Two passes (critical+warning, then `--all`) cleanly closed all 8 review findings without regressions.

### What Was Inefficient

- **STATE.md drift across commands.** The SDK's `state.begin-phase` / `state.planned-phase` subcommands produced inconsistent frontmatter when called with mixed positional/flag args. Required manual reverts and re-runs at phase transitions (Phase 8, Phase 9). Worth a fix in `gsd-sdk` for v1.1 tooling.
- **Executor agents writing to main repo.** Phase 8 executor wrote STATE.md/ROADMAP.md to the main repo path while doing source work in the worktree. The LEARNINGS.md pattern catches this — but it still costs a post-merge revert cycle each time. The agent-prompt `<critical_rule>` block could be stricter (e.g., refuse absolute paths outside cwd).
- **Verification filename drift.** Phases 3 and 4 shipped with `VERIFICATION.md` (no prefix); Phases 1/2/5/6/8 shipped `{NN}-VERIFICATION.md`. Phase 7 skipped VERIFICATION.md entirely in favor of `UAT.md` + `SECURITY.md`. The milestone-audit workflow had to accommodate all three styles. Should standardize in v1.1.
- **CONTEXT.md size ballooning.** Phase 8's 17-decision CONTEXT.md (230 lines) was so dense that the planner needed 3+ re-reads during revision. Still net-positive (every ambiguity was pinned before planning), but future phases should consider CONTEXT-AMENDMENTS.md for post-hoc additions rather than mutating the main doc.
- **SDK `milestone.complete` crashed on version flag.** Had to hand-roll the archive step (cp ROADMAP/REQUIREMENTS to milestones/, write MILESTONES.md manually). Worth tracking in gsd-sdk v1.1.
- **Pre-close audit surfaced 4 "human_needed" items** that can't be automated. GSD currently treats these as gates — more useful to auto-defer them to STATE.md §Deferred Items at close-time so the close flow doesn't need a manual acknowledgement step for every UAT scenario that's inherently operator-visual.

### Patterns Established (carry to v1.1+)

- **Underscore-prefix persistence rule** (`_resolved_contracts`, `_stale_info`) — runtime-only keys auto-stripped by `save_state`. Enforced by regression test. Extend to any future transient state.
- **SendStatus NamedTuple return for notifier** — orchestrator translates failures into `append_warning` (preserves hex-lite boundary — notifier never writes to state directly). Pattern for any future I/O adapter.
- **Layer A (never-crash per-job) + Layer B (outer crash-email except Exception)** — typed exceptions (DataFetchError/ShortFrameError) bubble to exit codes without email; unhandled exceptions trigger crash-email boundary. Clear semantics for any future crash-path additions.
- **Local imports inside `_run_X_never_crash` wrappers** — keeps hex boundary intact even when main.py calls notifier/dashboard. Replicated across Phase 6, 7, 8.
- **Clock injection via `now=None` default** — let tests pass fixed UTC datetimes without pytest-freezer. Pattern proven in `append_warning`; extend to any new helper that reads wall clock.
- **Grep-verifiable acceptance criteria as the quality bar** — no visual inspection escape clauses. Every criterion must be a runnable assertion.

### Key Lessons

1. **Planner-checker iteration is cheap; execution iteration is expensive.** Phase 8 had 5 blockers in iteration 1 that would have manifested as 5 distinct debug cycles if they'd reached execution. The 2-minute checker run saved hours.
2. **Cross-AI review catches different blind spots.** Gemini rated Phase 8 LOW risk; Codex rated it MEDIUM. Both identified unique issues neither Claude nor the plan-checker surfaced. Worth the overhead on high-stakes phases.
3. **Pattern-mapper > pure research for refactor-heavy phases.** Phase 8 reused Phase 3/6/7 patterns; the mapper identified the exact file+line analogs and the planner/executor replicated with zero drift. For greenfield phases, research still wins.
4. **"Just-in-time" research decisions save context.** Phase 8 skipped research entirely because CONTEXT.md was exhaustive — plans compensated with concrete grep-verifiable ACs. VALIDATION.md was absent but no quality was lost. Don't rubber-stamp the full pipeline for every phase.
5. **Spec divergence beats spec rot.** ERR-01 had a locked test that contradicted the spec text. Resolving it by amending the spec (not the code) was the right call — the code's "don't email on transient data errors" design was correct; the spec was stale. Pattern: when test + code + review all agree, the spec is wrong.
6. **Back-to-back waves need explicit execution notes.** Phase 8 Plans 02 → 03 left main.py red between them. `<execution_note>` blocks in the plan headers made this explicit. Required discipline — future phases with breaking contract changes should always flag this.

### Cost Observations

- **Model mix:** Opus for planners (design decisions); Sonnet for executors, checkers, researchers, reviewers (mechanical + analytical). Auditor + integration-checker on Sonnet worked well — Opus would have been overkill.
- **Sessions:** ~25-30 across the milestone (estimate from git log + active work).
- **Notable:** The `--reviews` replan pass after cross-AI review (Phase 8) was cheap (1 planner spawn) and landed 4 material fixes + 2 execution_note blocks. High ROI per token.

### What I'd Do Differently

- Standardize VERIFICATION.md filename from Day 1 (always `{NN}-VERIFICATION.md`).
- Always run `/gsd-review` on phases that touch the warning pipeline or error boundaries — catch silent-failure gaps before execution.
- Include a Phase-0 "scaffolding" phase that sets up the test matrix + hex-lite blocklist + regenerate-goldens scripts. Phase 1's Plan 01-01 did this implicitly but a dedicated phase would have been cleaner.
- Write `execution_note` blocks earlier — they'd have caught the Phase 4 → Phase 6 CLI-01/03 split sooner.

---

## Cross-Milestone Trends

_To be populated at v1.1 close._

| Metric | v1.0 | v1.1 |
|--------|------|------|
| Phases | 9 | — |
| Plans | 33 | — |
| Tests | 662 | — |
| Commits | 250 | — |
| Review blockers caught pre-execution | 5 (Phase 8) | — |
| Code-review findings fixed | 8 (0 critical, 2 warning, 6 info) | — |

---

*Living retrospective. Updated at each `/gsd-complete-milestone`.*
