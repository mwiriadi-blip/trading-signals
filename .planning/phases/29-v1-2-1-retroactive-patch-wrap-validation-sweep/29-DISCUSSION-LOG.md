# Phase 29: v1.2.1 Retroactive Patch Wrap + Validation Sweep - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-10
**Phase:** 29-v1-2-1-retroactive-patch-wrap-validation-sweep
**Areas discussed:** FAIL absorption, VALIDATION/SECURITY depth, DEBT-02 patch-wrap shape, OPS-02 path fix

---

## FAIL absorption

### UAT-23-1 live-yfinance 0-trades regression

| Option | Description | Selected |
|--------|-------------|----------|
| Investigate inside Phase 29 | First plan is a time-boxed root-cause spike (≤1 day). If fix is small, land here. If it explodes, split into Phase 29.5 mid-flight without re-discussing. | ✓ |
| Spike now, fix in Phase 29.5 | Lock Phase 29 to docs/debt + small bugs. Spawn Phase 29.5 immediately for the yfinance regression in parallel. Cleaner phase boundaries but more numbering churn. | |
| Fix all 4 inside Phase 29 | Treat all 4 FAILs as ordinary plans regardless of blast radius. Simpler scoping but Phase 29 stops being a clean cleanup phase. | |

**User's choice:** Investigate inside Phase 29 with mid-flight Phase 29.5 escape hatch.
**Notes:** Captures both the cheap-path (small fix in Phase 29) and the explode-path (Phase 29.5) without forcing a decision before evidence exists.

### UAT-17-2 iOS Safari trace-panel reload state loss

| Option | Description | Selected |
|--------|-------------|----------|
| Server-side render from cookie + operator recheck | Backend reads `tsi_trace_open` and seeds `<details open>` server-side. Operator re-runs iPhone scenario manually; PASS row appended to 28-VERIFICATION.md. | ✓ |
| Client-side cookie-attribute fix only | Adjust Secure / SameSite on cookie write. Cheaper but fragile — relies on JS to re-open after load, which is what's failing. | |
| Defer to v1.3.x as known issue | Document in REQUIREMENTS.md as v1.3.x deferred. Phase 29 skips it. Faster but leaves a real bug live for F&F users. | |

**User's choice:** Server-side render from cookie + operator recheck.
**Notes:** Locality-correct fix; the `<details>` open state is a server-rendered attribute, not a client enhancement.

### UAT-17-1 ATR(14) hand-recalc 1e-6 mismatch

| Option | Description | Selected |
|--------|-------------|----------|
| Expose engine ATR seed in trace panel | Trace panel shows the persisted Wilder seed at window-start. Hand-recalc picks up from that seed and converges to displayed ATR within 1e-6. Matches Phase 17 LEARNING. | ✓ |
| Widen displayed OHLC window to 100+ bars | Show enough bars to seed Wilder from scratch. UI cost: trace panel becomes much taller. Simpler engine-side. | |
| Loosen tolerance to 1e-3 | Acknowledge 40-bar window as a UX choice; loosen the SC. Cheapest but breaks the original 1e-6 requirement. | |

**User's choice:** Expose engine ATR seed in trace panel.
**Notes:** Honours the 2026-05-10 project LEARNING about reading engine-resolved values.

### UAT-26-1 cold-start JS bug — not discussed

One-line fix at `dashboard_legacy/section_renderers.py:218-220` (root cause already in 28-VERIFICATION.md evidence cell). Treated as ordinary plan with regression test. No alternatives presented.

---

## VALIDATION/SECURITY depth

### VALIDATION.md backfill depth

| Option | Description | Selected |
|--------|-------------|----------|
| Mechanical retrofit | Enumerate SC items, map each to existing tests, record coverage matrix. No new tests. Pure docs. Gaps become deferred items, not blockers. | ✓ |
| Mechanical + close obvious gaps | Retrofit + write tests for any SC with zero coverage. Larger phase but no quiet holes. | |
| True audit + Nyquist follow-ups | Each phase gets `/gsd-validate-phase` style depth; gaps file separate retroactive plans. Most thorough but balloons phase scope. | |

**User's choice:** Mechanical retrofit.

### SECURITY.md backfill depth

| Option | Description | Selected |
|--------|-------------|----------|
| Mirror VALIDATION depth | Same depth as VALIDATION (mechanical). Symmetric, one combined plan per phase. | ✓ |
| Different — SECURITY mechanical even if VALIDATION isn't | Phase 19/22/25 are UI-only with low threat surface. | |
| Different — SECURITY deeper | Tenant boundary work in v1.3 is coming; treat SECURITY as real gap audit. | |

**User's choice:** Mirror VALIDATION depth.

### Sweep packaging

| Option | Description | Selected |
|--------|-------------|----------|
| One plan per phase | 7 plans, each writes both VALIDATION + SECURITY for that phase. Parallelisable; per-plan commits cleaner; one failure doesn't block all. | ✓ |
| One sweep plan, batch all 7 | Single plan, single commit. Faster ceremony; harder to review; one failure blocks all. | |
| Two plans — VALIDATION sweep + SECURITY sweep | Split by doc-type, each batches all 7. Reasonable middle ground. | |

**User's choice:** One plan per phase.

---

## DEBT-02 patch-wrap shape

### Patch-wrap evidence shape

| Option | Description | Selected |
|--------|-------------|----------|
| Single MILESTONES.md note + targeted regression tests | One v1.2.1 entry naming each commit with one-line note + test pointer. Tests only for behaviour-locking commits (scheduler tz, signal status ladder, vote_params). UX-only fixes get a one-liner. | ✓ |
| Per-commit retroactive PLAN.md + test | Each commit gets its own `29-NN-RETRO-PLAN.md`. Most thorough but heavy ceremony. | |
| Single MILESTONES.md note only — no new tests | Trust commit messages; backfill nothing. Lightest touch but no behaviour lock. | |

**User's choice:** Single MILESTONES.md note + targeted regression tests.

### MILESTONES.md location

| Option | Description | Selected |
|--------|-------------|----------|
| Main `.planning/MILESTONES.md` | Append v1.2.1 sub-entry under v1.2 entry. Single source of truth. | ✓ |
| `.planning/milestones/v1.2-ROADMAP.md` (archived) | Closer to v1.2 source of truth but archive layer is read less often. | |
| Both — main + archive | Duplicate. Sync risk. | |

**User's choice:** Main `.planning/MILESTONES.md`.

---

## OPS-02 path fix

### Path fix shape

| Option | Description | Selected |
|--------|-------------|----------|
| Module-level `Path(__file__).resolve().parents[N]` constant | Each of 3 modules (`backtest/cli.py`, `backtest/data_fetcher.py`, `web/routes/backtest.py`) defines its own anchor. No contract change, no DI. **Most eloquent.** | ✓ |
| Single `paths.py` helper module | New `paths.py` exports `PROJECT_ROOT` + `BACKTESTS_DIR`. Three callers import it. DRY but couples 3 modules to a fourth. | |
| CLI/route arg with default | Each entry point accepts `--project-root` / FastAPI Depends. Most testable but biggest contract change. | |
| Env-var override | `os.environ.get('TSI_PROJECT_ROOT', ...)`. Ops-friendly but indirect. | |

**User's choice:** Module-level `Path(__file__).resolve().parents[N]` constant.

### Regression test depth

| Option | Description | Selected |
|--------|-------------|----------|
| Subprocess from `/tmp` and project root, assert identical output paths | Real-world repro of bug. Matches ROADMAP SC-4. | ✓ |
| Unit test on resolved constant only | Fast but doesn't prove CWD-independence end-to-end. | |
| Both | Belt and braces. | |

**User's choice:** Subprocess from `/tmp` and project root.

---

## Claude's Discretion

- Exact wording of the 5 v1.2.1 commit summary lines in MILESTONES.md.
- Wave ordering details if planner finds tighter dependencies during research.
- Exact Nyquist matrix column shape per VALIDATION.md (recommend matching Phase 27 verbatim).
- Threat-categorisation taxonomy in SECURITY.md (recommend matching Phase 27).
- Whether the cold-start JS bug fix and its regression test live in one plan or two.
- Where the yfinance spike RCA writeup goes if Phase 29.5 spawns (recommend `.planning/phases/29-.../29-NN-YFINANCE-SPIKE.md`).

## Deferred Ideas

- `paths.py` helper module — revisit if a fourth caller emerges in v1.3.
- Per-commit retroactive PLAN.md for v1.2.1 commits — too heavy.
- Loosen ATR tolerance to 1e-3 — would break original 1e-6 SC.
- True audit (vs mechanical retrofit) of VALIDATION/SECURITY sweep — scope risk; gaps surface as deferred items per phase.
- Defer iOS Safari fix as v1.3.x — leaves real bug live for F&F users.
