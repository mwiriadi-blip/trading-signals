# Phase 16: Hardening + UAT Completion - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-26
**Phase:** 16-hardening-uat-completion
**Areas discussed:** F1 test fixture + assertions, Planted-regression meta-test, UAT artifact + deployment gate, Milestone close mechanics

---

## Gray Area Selection

| Option | Description | Selected |
|--------|-------------|----------|
| F1 test fixture + assertions | What state seed feeds the chain; what assertions on last_email.html; reuse Phase 1 fixtures? | ✓ |
| Planted-regression meta-test approach | Permanent monkey-patch test vs one-time validation vs combo | ✓ |
| UAT artifact + deployment gate | New 16-HUMAN-UAT.md vs update archive; deploy as Phase 16 task or prerequisite | ✓ |
| Milestone close mechanics | Same-session vs separate; how to handle real-day SC-3c gating | ✓ |

**Notes:** All 4 areas selected — operator wanted full coverage given Phase 16 is the final v1.1 gate.

---

## Area 1: F1 test fixture + assertions

### Q1.1: What state/data seed should F1 use as the input to the full chain?

| Option | Description | Selected |
|--------|-------------|----------|
| Reuse Phase 1 scenario fixture | `tests/fixtures/scenarios/*.json` — 9 deterministic scenarios with known signal outputs and golden CSVs. Lowest-effort, leverages existing test infra. | ✓ |
| Build dedicated F1 fixture | New `tests/fixtures/integration/f1_state.json` with hand-picked positions + signals + warnings. Highest coverage, more maintenance. | |
| Replay an archived real run | Use a real production state.json + yfinance response from a past day. Most realistic, but ties test to a frozen historical snapshot. | |

**User's choice:** Reuse Phase 1 scenario fixture
**Notes:** Aligns with CLAUDE.md's "leverage existing test infra" principle and Phase 1's deterministic-scenario design pattern. F1 picks a scenario that exercises both instruments with non-FLAT signals.

### Q1.2: How thoroughly should F1 assert on the rendered last_email.html?

| Option | Description | Selected |
|--------|-------------|----------|
| Section presence + a few key values | Subject emoji + date format; body has signal + position direction + equity; banner appears when expected. Catches cross-module breaks without being brittle. | ✓ |
| Golden snapshot match | Byte-for-byte against `tests/fixtures/integration/golden_email.html`. Strictest, but brittle. | |
| Just smoke test (no value asserts) | File exists, non-empty, has minimum HTML structure. Lowest signal. | |

**User's choice:** Section presence + a few key values
**Notes:** Avoids fighting with the existing per-component snapshot tests in `test_dashboard.py` and `test_notifier.py` which already cover byte-for-byte rendering.

### Q1.3: Should F1 cover both instruments or one?

| Option | Description | Selected |
|--------|-------------|----------|
| Both SPI200 and AUDUSD in one pass | Fixture has both instruments active. Single test exercises both code paths. Catches cross-instrument bugs. | ✓ |
| Just SPI200 | Single instrument keeps the test simpler. | |
| Two parametrized cases | `@pytest.mark.parametrize` over instruments. Two test runs. | |

**User's choice:** Both SPI200 and AUDUSD in one pass
**Notes:** Single-test design matches ROADMAP SC-1's framing.

---

## Area 2: Planted-regression meta-test

### Q2.1: How should the planted-regression meta-test work?

| Option | Description | Selected |
|--------|-------------|----------|
| Permanent monkey-patch test | `test_f1_catches_planted_regression` in same file. Uses `unittest.mock.patch` to rename/stub, asserts F1 fails, then asserts F1 passes without patch. Permanent CI signal. | ✓ |
| One-time validation in SUMMARY.md | Executor manually performs rename, runs F1, confirms red, reverts, records demo in SUMMARY.md. No persistent test. | |
| Snapshot proof + permanent meta-test combo | Both — SUMMARY.md captures one-time demo PLUS permanent monkey-patch test. | |

**User's choice:** Permanent monkey-patch test
**Notes:** ROADMAP SC-2 says "meta-test confirms F1 red-lights on that planted break" — wording implies permanent test, not one-time check.

### Q2.2: What's the exact planted regression the meta-test exercises?

| Option | Description | Selected |
|--------|-------------|----------|
| Rename `get_signal` → `compute_signal` | Per ROADMAP SC-2 example. Hits signal_engine → main.py wiring. Most likely real-world break. | ✓ |
| Stub `append_warning` to no-op | Hits state_manager → main.py wiring + dashboard banner reading. | |
| Stub `render_dashboard` to return empty string | Hits dashboard → last_email composition. | |

**User's choice:** Rename `get_signal` → `compute_signal`
**Notes:** Matches ROADMAP SC-2's literal example text — keeps planning tight to the spec.

---

## Area 3: UAT artifact + deployment gate

### Q3.1: Where should operator UAT notes for the 3 scenarios live?

| Option | Description | Selected |
|--------|-------------|----------|
| New `16-HUMAN-UAT.md` in phase 16 dir | Fresh artifact specific to v1.1's hosted-dashboard verification. References archived 06-HUMAN-UAT.md for context. | ✓ |
| Update archived `06-HUMAN-UAT.md` | Append v1.1 verification notes under a new section in the existing archived file. | |
| Both: new 16-HUMAN-UAT.md + status update in archived | Operator notes in 16-HUMAN-UAT.md; archived gets a pointer line per scenario. Most traceable. | |

**User's choice:** New `16-HUMAN-UAT.md` in phase 16 dir
**Notes:** Keeps each milestone's UAT records together with that milestone's other artifacts. Archive stays immutable.

### Q3.2: Is deploying Phases 13-15 to the droplet a Phase 16 task or a prerequisite?

| Option | Description | Selected |
|--------|-------------|----------|
| Phase 16 task | First plan = deploy stack to droplet (push, pull, restart, smoke test). Makes the dependency explicit and reviewable. | ✓ |
| Prerequisite gate | Phase 16 starts AFTER operator confirms deploy. Cleaner separation but the deploy isn't tracked anywhere. | |
| Separate `/gsd-ship` before Phase 16 | Open a PR for Phases 13+14+15 before Phase 16. Adds review layer. | |

**User's choice:** Phase 16 task
**Notes:** Makes the deploy auditable and forces the dependency to be visible in the plan graph.

### Q3.3: What deploy mechanism are you comfortable with?

| Option | Description | Selected |
|--------|-------------|----------|
| Direct git push to origin/main + droplet pull | Simplest. `git push origin main` from Mac, `git pull && systemctl restart` on droplet. No PR review layer. | ✓ |
| PR review first, then merge + droplet pull | git push to phase-15-stack branch, open PR, review (you + cross-AI), merge, droplet pull. | |
| Tag + tagged-deploy | Tag main as `v1.1-rc1`, droplet pulls the tag. Adds version stability. | |

**User's choice:** Direct git push to origin/main + droplet pull
**Notes:** Single-operator project, low review-bandwidth. Phase 16 + Phase 11's `deploy.sh` already provide enough automation guardrails.

---

## Area 4: Milestone close mechanics

### Q4.1: When does the v1.1 milestone archive happen relative to Phase 16 verify-work?

| Option | Description | Selected |
|--------|-------------|----------|
| Same session as verify-work | Phase 16 verify-work passes → immediately `/gsd-complete-milestone`. Single chain. | |
| Separate session after verify-work | Verify-work passes; user takes a break; comes back and runs `/gsd-complete-milestone`. More careful pacing. | ✓ |
| Bundle with v1.2 kickoff | Archive v1.1 + start v1.2 milestone in same session. Fast onramp but commits to next-milestone scope. | |

**User's choice:** Separate session after verify-work
**Notes:** Operator wants explicit pause before milestone archive — gives time to review verify-work output and decide if anything else should be deferred to v1.2.

### Q4.2: What if SC-3c (drift banner in real weekday Gmail) takes >1 weekday run to verify?

| Option | Description | Selected |
|--------|-------------|----------|
| Phase 16 stays open until verified | verify-work returns `PARTIAL — awaiting weekday operator confirmation`. Operator updates 16-HUMAN-UAT.md once observed. | ✓ |
| Force-close with a known-pending note | Phase 16 closes 'pending operator weekday verification' — milestone archives with a note. | |
| Synthesize a real-day check | Force a drift state on a real weekday, trigger the daily run, capture screenshot. | |

**User's choice:** Phase 16 stays open until verified
**Notes:** Honors the "real" in "real weekday Gmail" — synthesized checks aren't equivalent to organic-drift verification.

### Q4.3: Anything else to surface for Phase 16?

| Option | Description | Selected |
|--------|-------------|----------|
| Nothing else — ready to write CONTEXT.md | All 4 areas covered. Move to context capture. | ✓ |
| ruff F401 cleanup belongs here too | CHORE-02 currently mapped to Phase 10 — fold into Phase 16? | |
| Need to deploy Phase 10/12 first | Droplet may have unshipped Phase 10/12 work — gate Phase 16 on resolving that first. | |

**User's choice:** Nothing else — ready to write CONTEXT.md
**Notes:** Operator acknowledged the Phase 10/12 deploy-state question (raised by /gsd-execute-phase 15 finding) but chose to defer it to a separate investigation rather than expanding Phase 16 scope. Captured in CONTEXT.md `<deferred>` for visibility.

---

## Claude's Discretion

- F1 fixture selection — which exact scenario from the 9 Phase 1 fixtures
- Test runtime budget — target < 5s, no hard SLA
- Specific text-pattern strings F1 looks for in `last_email.html`
- Smoke-check curl target (127.0.0.1 vs HTTPS domain)

## Deferred Ideas

- Phases 10 + 12 deployment status — investigate before Phase 16 deploy task
- CHORE-02 ruff F401 — leave for v1.2 if Phase 10 never executes formally
- Tagged release strategy — adopt `v1.1-rc1` style for v1.2+ if v1.1 deploy goes well
- Cross-AI peer review on deploy plan — adopt for v1.2 if v1.1 deploy issues arise
- Real-day drift simulation helper — add `tests/manual/inject_drift_for_uat.py` if waiting becomes painful
