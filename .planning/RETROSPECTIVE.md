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

## Milestone: v1.1 — Interactive Trading Workstation

**Shipped:** 2026-04-30
**Phases:** 8 (10, 11, 12, 13, 14, 15, 16, 16.1) | **Plans:** 38 | **Commits:** 179

### What Was Built

Hosted dashboard at `https://signals.mwiriadi.me` with FastAPI + uvicorn + nginx + Let's Encrypt on a DigitalOcean droplet, daily 08:00 cycle moved from GHA cron → systemd. Cookie session + TOTP 2FA + 30-day trusted-device cookies + magic-link recovery (Phase 16.1). HTMX trade-mutation forms with sole-writer invariant preserved. Live calculator + drift sentinel pipeline with lockstep email-vs-dashboard banner parity.

### What Worked

- **Phase 16.1 inserted mid-milestone (URGENT, 2026-04-27)** without derailing the other phases — proved the GSD insertion pattern works for high-priority operator-driven scope changes.
- **F1 full-chain integration test** with sabotage verification — planted regressions actually red-light it.
- **Operator UAT closure through real-world deployment** (UAT-16-A/B/C verified by observing drift email in production Gmail mobile) rather than synthetic checks.

### What Was Inefficient

- Silent regression in `main.py::_run_daily_check_caught` (commit `3279c312`) discarded the 4-tuple from `run_daily_check(args)` and stopped daily emails for ~7 days. Diagnosed via `journalctl` pattern matching, fixed with 4 regression tests + inverted Phase-4 fossil test. Rooted in the Phase-4 fossil test still asserting the old `False` return and being treated as truth.

### Patterns Established

- **Shared function body = sequential plans** (LEARNINGS.md 2026-04-27) — when multiple plans touch the same file, the wave structure must serialize them, not parallelize.
- **Inverted fossil tests** — when a behavior intentionally changes, flip the existing test's assertion rather than adding a new one alongside, so future you can't regress to the old behavior.

### Cost Observations

- 6 days, 38 plans, 179 commits, +57,623 / -264 LOC (heavy on infra setup)
- Phase 16.1 fold-in (TOTP 2FA + trusted device + magic-link) was the longest single phase — 3 sequential plans on shared `auth_store.py` + `web/routes/totp.py`.

---

## Milestone: v1.2 — Trader-Grade Transparency & Validation

**Shipped:** 2026-05-10
**Phases:** 9 (17, 19, 20, 22, 23, 24, 25, 26, 27 — Phase 18 multi-user + Phase 21 news deferred to v1.3+) | **Plans:** 48 | **Commits:** 221

### What Was Built

- **Per-signal transparency** (Phase 17) — Inputs/Indicators/Vote panels make every signal hand-reproducible from the dashboard alone. Schema v4→v5 with `ohlc_window` + `indicator_scalars`.
- **Paper-trade ledger** (Phase 19) — manual entry, mark-to-market unrealised P&L, aggregate stats. Atomic-write contract preserved.
- **Stop-loss alerts** (Phase 20) — CLEAR/APPROACHING/HIT state machine, dedup'd per state transition.
- **Strategy versioning** (Phase 22) — `STRATEGY_VERSION='v1.2.0'` constant tags every signal/trade row.
- **5-year backtest gate** (Phase 23) — pure-compute `backtest/` module, `/backtest` route, `>100%` cum-return pass criterion.
- **Two-axis market × function nav** (Phase 25) — `/markets/{m}/{fn}` with cookie + URL persistence. WAI-ARIA roving tabindex. Schema v7→v8.
- **Phase 25 follow-up** (Phase 26) — fixed 4 BROKEN regressions (multi-tab scoping, template placeholder leak → 401, header session widget, deploy tests).
- **Code-quality sweep** (Phase 27) — Decimal money math (schema v8→v9), file-size hygiene (notifier/main/dashboard each <500 LOC, byte-identical render), naive-datetime fail-closed, migration-chain contiguity assert, look-ahead-bias backtest test, `--version` flag, lazy yfinance import.

### What Worked

- **Re-audit caught stale audit drift.** The 2026-05-02 milestone audit only covered Phases 17, 19, 20, 22, 23, 24 — Phases 25-27 closed afterward without an audit refresh. Re-audit on 2026-05-10 surfaced one procedural gap (Phase 26 missing VERIFICATION.md), which was closed atomically before milestone close (`ad7f2a1`). **Lesson: audit per phase-closure, not just per-milestone.**
- **xfail(strict=True) test scaffolding then flip-to-green.** Phase 26 used xfail-strict tests as the contract for the bug being open; the same tests flipping green serve as proof the fix landed. Pattern reused across Phases 25, 26, 27.
- **TDD on schema migrations.** Schema bumps v4→v5 (Phase 17), v6→v7 (Phase 20), v7→v8 (Phase 25), v8→v9 (Phase 27) all landed cleanly because the contiguity assert from Phase 27 fails fast at module load if any link is missing.
- **Byte-identical render parity** as the acceptance gate for Phase 27-14's `dashboard.py` 2221-LOC → 9-module package split. Refactor proven safe by golden HTML diff, not by hand inspection.
- **Decimal money math at I/O boundary, float64 for indicators.** Phase 27-01 split: write paths quantize HALF_UP to AUD cents; signal compute stays float64. No performance regression, no float-drift on P&L.

### What Was Inefficient

- **Phase 25 shipped 4 BROKEN regressions** (multi-tab scoping non-functional, template placeholder leak → 401 on PATCH, header session widget unresolved, 3 red deploy tests). Required a follow-up Phase 26 to clean up. Root cause: too much scope in a single phase (12 plans, 22 design decisions) without per-plan verification gates — the gap between "all plans complete" and "system actually works end-to-end" was bigger than expected.
- **Post-ship polish drifted outside phase-tracking.** 5 ad-hoc commits 2026-05-08..2026-05-10 (scheduler tz fix, signal status ladder, v1.1 backtested defaults, trace vote_params, market tab refresh) landed on `main` without a phase wrapper. They're real v1.2 deliverables but never appeared in any plan or summary. Deferred decision to v1.3: retroactive v1.2.1 patch phase or accept-as-state.
- **Phase 26 VERIFICATION.md missing** until day-of-close. Operator skipped browser-based UAT, relied on xfail-flip + 1794-test suite as evidence, but the formal closure doc didn't get written until commit `ad7f2a1` on 2026-05-10. **Lesson: xfail-flip is good evidence, but VERIFICATION.md captures the *rationale for accepting deferred UAT* — write it at the time of decision, not retroactively.**
- **Nyquist VALIDATION.md only on 2 of 9 phases** (23, 27). Phases 17-26 shipped before Nyquist became standard practice; retroactive validation deferred to v1.3 backlog and recommended only if subsystems evolve.

### Patterns Established

- **Per-phase audit cadence:** schedule a `/gsd-audit-phase` after every phase close; the milestone-audit is then a re-validation, not the first audit. Catches procedural gaps (missing VERIFICATION.md, stale UAT.md, xfail not flipped) at the right granularity.
- **Schema migration contiguity assert at module load** (Phase 27-07) — fails fast if the v3..vN chain has any gap. Cheap insurance, prevents silent corruption when migrations accidentally get reordered or dropped.
- **`_assert_tz_aware` fail-closed at write paths** — naive datetimes used to silently round-trip through `state.json` and cause subtle off-by-tz bugs in the daily run. Boundary check makes the error loud.
- **Decimal money math, float64 indicator math** — split by responsibility, quantize on save, dashboard `json.dumps` Decimal-safe.
- **Document deploy primary path explicitly** (Phase 27-16) — when there are 3 candidate paths (GHA cron / Replit Always On / DO droplet systemd) and one wins, retire the others from active docs (preserve only in archives) so future operators don't get confused.

### Key Lessons

1. **Multi-plan UI phases need per-plan verification gates.** Phase 25's 12 plans + 22 design decisions completed but shipped 4 BROKEN regressions. Either split mega-phases or add a per-plan acceptance test.
2. **xfail-flip is a great contract, VERIFICATION.md is the rationale.** Both. xfail proves the bug is gone; VERIFICATION.md explains why operator-deferred UAT is acceptable closure.
3. **Re-audit the audit.** A milestone audit that's >7 days old is stale if new phases closed in between. Re-run before `/gsd-complete-milestone`.
4. **Polish that lands on `main` outside phase-tracking is real scope.** Either wrap in a phase or formally accept-as-state at milestone close. Don't pretend it didn't happen.

### Cost Observations

- 11 days, 48 plans, 221 commits, +76,605 / -6,653 LOC (heavy on UI overhaul Phase 25 + file splits Phase 27)
- Phase 27 was the largest single phase (16 plans across 4 waves) — file-size splits + correctness sweep + security verification + Nyquist validation all in one
- Production was live and serving daily emails throughout the milestone (no downtime); Phase 25-27 work was merged-to-main with each phase's HTML output byte-identical to baseline (Phase 27-14 golden snapshot)

---

## Cross-Milestone Trends

| Metric | v1.0 | v1.1 | v1.2 |
|--------|------|------|------|
| Phases | 9 | 8 | 9 |
| Plans | 33 | 38 | 48 |
| Tests | 662 | 1319 | 1880+ |
| Commits | 250 | 179 | 221 |
| Days | 4 | 6 | 11 |
| Plans/day | 8.3 | 6.3 | 4.4 |
| Review blockers caught pre-execution | 5 (Phase 8) | — | xfail-strict scaffolding (Phase 26) |
| Code-review findings fixed | 8 (Phase 9 codemoot) | — | 19 (Phase 27 sweep) + 10 (Phase 24 codemoot) |
| Schema migrations | v1→v2 | v2→v3 (auth) | v4→v5→v6→v7→v8→v9 |
| Mid-milestone fold-ins | Phase 9 | Phase 16.1 | Phase 24, 25, 26, 27 |

**Trend:** Plans/day decreased as phases got more cross-cutting (UI overhaul + multi-file splits). Tests grew ~3x across milestones. Schema versions grew from one bump per milestone to six in v1.2 alone — a sign that v1.2 was schema-heavy (every functional area touched persistence).

---

*Living retrospective. Updated at each `/gsd-complete-milestone`.*
