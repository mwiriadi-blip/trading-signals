# Phase 29: v1.2.1 Retroactive Patch Wrap + Validation Sweep - Context

**Gathered:** 2026-05-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Cleanup phase that closes v1.2 debt and absorbs Phase 28 fallout before any v1.3 substance lands. Four workstreams:

1. **DEBT-02 — v1.2.1 patch wrap.** Formalise the 5 ad-hoc post-ship polish commits (scheduler tz `05a4c0c`, signal status ladder `da31412`, v1.1 backtested per-market defaults `b7ed1f2`, trace vote_params `587b6f0`/`bb780af`, market tab strip refresh `878199c`) as a single v1.2.1 entry in `.planning/MILESTONES.md` with regression tests where behaviour needs locking.
2. **DEBT-03 + DEBT-04 — VALIDATION/SECURITY sweep.** Backfill `VALIDATION.md` (Nyquist coverage matrix per Phase 23+27 format) and `SECURITY.md` (threat model + mitigations per Phase 27 format) for v1.2 phases 17, 19, 20, 22, 24, 25, 26. Phases 23 and 27 already have both. **Mechanical retrofit only** — record what tests already exist; gaps become deferred items, not blockers.
3. **OPS-02 — `.planning/backtests` path bug.** Fix CWD-relative path in `backtest/cli.py:46`, `backtest/data_fetcher.py:24`, `web/routes/backtest.py:45`. Module-level `Path(__file__).resolve().parents[N]` constant in each module.
4. **Phase 28 FAIL absorption (per Phase 28 D-20).** Resolve all 4 FAILs from `28-VERIFICATION.md`:
   - **UAT-26-1** cold-start JS bug at `dashboard_legacy/section_renderers.py:218-220` — one-line fix at known file:line + regression test.
   - **UAT-23-1** live-yfinance 0-trades regression — time-boxed root-cause spike (≤1 day) inside Phase 29; if fix is small, land here; if it explodes, split into Phase 29.5 mid-flight.
   - **UAT-17-1** ATR(14) hand-recalc 1e-6 tolerance — expose engine Wilder ATR seed in trace panel; hand-recalc picks up from persisted seed.
   - **UAT-17-2** iOS Safari trace-panel reload state loss — server-side render `<details open>` from `tsi_trace_open` cookie + operator iPhone recheck.

**Phase 28 PASS rows are not re-verified.** Phase 29 only touches the FAIL rows; the PASS rows in 28-VERIFICATION.md remain authoritative.

**Phase 28 status update:** When Phase 29 closes the 4 FAILs, append PASS rows to 28-VERIFICATION.md and flip frontmatter `status: partial` → `status: passed`. Don't rewrite history — append-only.

</domain>

<decisions>
## Implementation Decisions

### Phase 28 FAIL absorption

- **D-01:** All 4 Phase 28 FAILs are in Phase 29 scope (per Phase 28 D-20). The cold-start JS bug, ATR seeding fix, iOS Safari fix, and the live-yfinance regression all live as plans in this phase.
- **D-02:** Live-yfinance 0-trades regression (UAT-23-1) — first plan is a **time-boxed root-cause spike (≤1 day)**. If the fix is small (e.g., a single yfinance schema branch) it lands inside Phase 29. **Escape hatch:** if the spike reveals deep blast radius (signal-engine regression touching multiple modules, or ambiguous yfinance contract), the planner splits the fix into a new **Phase 29.5** mid-flight without re-running discuss-phase. Phase 29 then keeps only the spike + RCA writeup; Phase 29.5 owns the fix.
- **D-03:** ATR(14) hand-recalc fix (UAT-17-1) — **expose the engine's persisted Wilder ATR seed in the trace panel**, not widen the OHLC window, not loosen tolerance. Hand-recalc reads the seed at window-start and converges to the displayed ATR within 1e-6. This honours the 2026-05-10 project LEARNING (read engine-resolved values; never re-derive from defaults). Locality discipline matches Phase 17 polish commit `587b6f0`.
- **D-04:** iOS Safari trace-panel reload (UAT-17-2) — **server-side render `<details open>` based on `tsi_trace_open` cookie**. Eliminates reliance on client-side JS to re-open the panel after load (which is what's failing on iOS). Don't tinker with cookie attributes alone — that's symptom-only. Operator re-runs the iPhone Safari scenario manually; PASS row appended to `28-VERIFICATION.md`.
- **D-05:** Cold-start JS bug (UAT-26-1) at `dashboard_legacy/section_renderers.py:218-220` — one-line fix at known file:line (equityChart inline JS y-axis brace structure) + UAT regression test. No discussion needed; root cause is in the Phase 28 evidence cell.

### VALIDATION.md / SECURITY.md sweep

- **D-06:** **Mechanical retrofit only.** For each of the 7 phases (17, 19, 20, 22, 24, 25, 26): enumerate Success Criteria items from that phase's plan, map each to existing tests in the suite, record coverage in a Nyquist matrix matching Phase 23+27 format. **No new tests written as part of the sweep.** Coverage gaps surface as deferred items in the phase's `VALIDATION.md` Gaps section — they do NOT block Phase 29 close.
- **D-07:** **SECURITY.md mirrors VALIDATION depth** — also mechanical retrofit. For each phase: identify threat surface (auth touch, money math, I/O), record the mitigations already in code, note gaps as deferred. Format matches Phase 27's SECURITY.md.
- **D-08:** **Packaging — one plan per phase × 7 phases.** Each plan writes both `VALIDATION.md` and `SECURITY.md` for that phase in a single commit. Plans can run in parallel waves (no inter-dependencies). Easier to retry one if it fails; per-plan commits stay reviewable.
- **D-09:** Sweep targets the **archive location** for v1.2 phases: `.planning/milestones/v1.2-phases/<NN>-<slug>/<NN>-VALIDATION.md` and `.../<NN>-SECURITY.md`. Same path convention as the existing 23 and 27 docs.
- **D-10:** Phases 23 and 27 already have both docs; the sweep does NOT touch them. ROADMAP SC-2 / SC-3 wording mentions all 9 v1.2 phases including 23 — read as "every phase has them"; 23 already does.

### DEBT-02 patch-wrap shape

- **D-11:** **Single MILESTONES.md entry + targeted regression tests.** No per-commit retroactive `PLAN.md` files. The v1.2.1 entry names each commit with a one-line behaviour note + regression test pointer (or "no test — UX-only" annotation).
- **D-12:** Regression test policy:
  - **Tested (behaviour-locking):** scheduler tz fix (`05a4c0c`), signal status ladder trigger (`da31412`), trace vote_params backfill (`587b6f0` + `bb780af`).
  - **Untested (UX-only):** market tab strip refresh (`878199c`).
  - **Tested via existing fixture suite:** v1.1 backtested per-market defaults (`b7ed1f2`) — already covered by `tests/test_backtest_*` deterministic fixtures; sweep documents the pointer, no new test.
- **D-13:** Location — entry lives in **`.planning/MILESTONES.md`** as a v1.2.1 sub-section under the v1.2 entry. Single source of truth. Do NOT duplicate into the archived `.planning/milestones/v1.2-ROADMAP.md`.

### OPS-02 path fix

- **D-14:** **Module-level `Path(__file__).resolve().parents[N]` constant in each of the 3 callers** (`backtest/cli.py`, `backtest/data_fetcher.py`, `web/routes/backtest.py`). No new `paths.py` helper module — adds an import and a fourth coupled module for what is one line of locality.
- **D-15:** **Most eloquent: D-14.** Locality preserved (each module owns its own anchor); no contract change to entry points; composes naturally with existing CLI and FastAPI route signatures; no env-var indirection that would hide the default. The `paths.py` helper is shorter to write but couples three modules to a fourth and adds an import for a one-line constant — premature centralisation.
- **D-16:** Regression test — **subprocess-level**: invoke `python -m backtest --years 1` from `/tmp` AND from project root, parse stdout for the resolved output path, assert equality. Real-world repro of the bug; matches ROADMAP SC-4 wording ("runs both from `/tmp` and asserts identical output paths"). One test file, one fixture-style invocation.

### Plan ordering (planner guidance)

Recommended wave order (planner has final say):

- **Wave 1 (independent, fast):** OPS-02 path fix (D-14, D-16); UAT-26-1 cold-start JS one-liner (D-05); DEBT-02 v1.2.1 patch wrap (D-11..D-13).
- **Wave 2 (independent, parallelisable):** 7-plan VALIDATION/SECURITY sweep (D-06..D-10) — each phase as its own plan; can run as a parallel fan-out.
- **Wave 3 (UI fixes, possibly serial against the same files):** UAT-17-1 ATR seed exposure (D-03); UAT-17-2 server-side cookie render (D-04). Both touch trace-panel render path; serialise to avoid merge conflicts.
- **Wave 4 (gated by spike outcome):** UAT-23-1 yfinance regression spike (D-02). Either lands a fix here or splits into Phase 29.5 mid-flight.

### Phase 28 closure update

- **D-17:** When the 4 FAIL fixes land and verify, **append** PASS rows to `28-VERIFICATION.md` (don't rewrite original FAIL evidence — preserve history). Flip frontmatter `status: partial` → `status: passed` and update `score`. Add a "Phase 29 closure" notes paragraph naming the resolving plans/commits.

### Claude's Discretion

- Exact wording of the 5 v1.2.1 commit summary lines in MILESTONES.md.
- Wave ordering details if planner finds tighter dependencies during research.
- Exact Nyquist matrix column shape per VALIDATION.md (recommend matching Phase 27 verbatim).
- Threat-categorisation taxonomy in SECURITY.md (recommend matching Phase 27).
- Whether the cold-start JS bug fix and its regression test live in one plan or two.
- Where the yfinance spike RCA writeup goes if Phase 29.5 spawns (recommend `.planning/phases/29-.../29-NN-YFINANCE-SPIKE.md`).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase boundary + requirements
- `.planning/ROADMAP.md` §"Phase 29: v1.2.1 Retroactive Patch Wrap + Validation Sweep" — phase goal, success criteria SC-1..SC-4, plan-time verification = none.
- `.planning/REQUIREMENTS.md` §DEBT-02, DEBT-03, DEBT-04, OPS-02 — explicit requirement text for each workstream.

### Phase 28 hand-off (FAIL absorption)
- `.planning/phases/28-v1-2-uat-closure/28-VERIFICATION.md` — 4 FAIL rows with symptom + suspected layer + repro command for each. Phase 29 reads this file as required input per Phase 28 D-20.
- `.planning/phases/28-v1-2-uat-closure/28-CONTEXT.md` §D-19, D-20 — the contract that Phase 28 FAILs become Phase 29 scope.

### Format precedent (sweep targets)
- `.planning/milestones/v1.2-phases/23-five-year-backtest-validation-gate/23-VALIDATION.md` — Nyquist matrix format precedent.
- `.planning/milestones/v1.2-phases/27-code-quality-correctness-sweep-apply-2026-05-07-code-review-/27-VALIDATION.md` — second Nyquist precedent.
- `.planning/milestones/v1.2-phases/27-code-quality-correctness-sweep-apply-2026-05-07-code-review-/27-SECURITY.md` — threat model + mitigations format precedent.

### Source phases for VALIDATION/SECURITY sweep
- `.planning/milestones/v1.2-phases/17-per-signal-calculation-transparency/` — TRACE-1..5 SC items.
- `.planning/milestones/v1.2-phases/19-paper-trade-ledger/` — LEDGER-1..6 SC items.
- `.planning/milestones/v1.2-phases/20-stop-loss-monitoring-alerts/` — ALERT-1..4 SC items.
- `.planning/milestones/v1.2-phases/22-strategy-versioning-audit-trail/` — VERSION-1..3 SC items.
- `.planning/milestones/v1.2-phases/24-v1-2-codemoot-fix-phase/` — codemoot-driven SC items.
- `.planning/milestones/v1.2-phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/` — D-06 two-axis nav + multi-tab persistence.
- `.planning/milestones/v1.2-phases/26-phase-25-followup-multi-tab-scoping-fixes/` — UAT-1..6 multi-tab scoping.

### Source artefacts for DEBT-02 patch wrap
- Git commits (no separate doc — read commit messages directly):
  - `05a4c0c feat(sched): fire daily run at 08:00 Sydney (AEST/AEDT, DST-aware)` — scheduler tz fix.
  - `da31412 feat(signals): trigger ladder + trailing-stop line on Signal Status card` — signal status ladder trigger.
  - `b7ed1f2 feat(v11): backtested per-market defaults, $10K baseline, contract type + financing UI` — v1.1 backtested defaults.
  - `587b6f0 fix(trace): render engine-resolved vote params instead of re-derived defaults` — trace vote_params (primary fix).
  - `bb780af fix(trace): backfill vote_params at render time for stale state rows` — trace vote_params (stale-state companion).
  - `878199c fix(ui): refresh market tab strip on tab click so active underline tracks selection` — market tab UX fix.

### Source files for OPS-02 path fix
- `backtest/cli.py:46` — `_BACKTEST_DIR = Path('.planning/backtests')` (CWD-relative, broken).
- `backtest/data_fetcher.py:24` — `_CACHE_DIR_DEFAULT = Path('.planning/backtests/data')` (CWD-relative, broken).
- `web/routes/backtest.py:45` — `_BACKTEST_DIR = Path('.planning/backtests')` (CWD-relative, broken).

### Source files for Phase 28 FAILs
- **UAT-26-1:** `dashboard_legacy/section_renderers.py:218-220` — equityChart inline JS y-axis brace bug.
- **UAT-17-1:** `signal_engine.compute_atr` (Wilder seed exposure) + trace panel render path (where the seed gets surfaced to the UI).
- **UAT-17-2:** trace-panel server-side render path + `tsi_trace_open` cookie write/read; `<details>` element seeding.
- **UAT-23-1:** `backtest/data_fetcher.py` (yfinance schema), `signal_engine` modules (regression candidate). Specific files identified during the spike.

### Project constraints
- `CLAUDE.md` §Rules — file-size cap (D-09 from v1.2: 500 LOC), test discipline, no ungated edits.
- `.claude/LEARNINGS.md` (project-local) — 2026-05-10 trace-panel-drift entry: read engine-resolved persisted values, never re-derive from defaults. Directly relevant to D-03 ATR seed exposure.
- `.planning/MILESTONES.md` — destination for v1.2.1 patch-wrap entry per D-13.

### Hand-off target
- **Phase 29.5 (conditional):** spawned mid-flight per D-02 only if the yfinance spike reveals deep blast radius. No file pre-exists.
- **Phase 30:** consumes a clean Phase 29 — no v1.2 debt, no Phase 28 FAILs left, before file-size pre-split work begins.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Phase 23 + 27 VALIDATION.md / SECURITY.md** — direct format templates for the 14 sweep docs. Copy the heading structure verbatim.
- **`tests/test_backtest_*` deterministic-fixture suite** — already covers v1.1 backtested per-market defaults (`b7ed1f2`); DEBT-02 documents the pointer rather than writing new tests.
- **`tests/uat/` infrastructure** (Phase 28 plan 28-01) — `pytest-playwright` substrate + `@pytest.mark.uat` marker is in place. UAT-26-1 cold-start regression test extends this pattern.
- **`signal_engine.resolve_vote_params`** (Phase 17 polish, commit `587b6f0`) — the locality discipline of "read persisted engine values, never re-derive" is the model for D-03 ATR seed exposure.

### Established Patterns
- **`@pytest.mark.uat` opt-in** — UAT regression tests stay out of the default suite (still ~2030 tests, ~2m35s at HEAD per 28-VERIFICATION.md).
- **`.planning/milestones/v1.2-phases/<NN>-<slug>/<NN>-VALIDATION.md`** location — all v1.2 phase docs use this archive layout. Sweep follows suit.
- **Append-only verification updates** — when Phase 29 resolves Phase 28 FAILs, append PASS rows; preserve original FAIL evidence (matches the audit-trail discipline used in earlier phases).
- **Module-level `Path(__file__).resolve().parents[N]`** — Python idiom for project-root anchoring without DI overhead. Already used elsewhere in the codebase (planner: confirm during research; expected pattern for D-14).

### Integration Points
- **`.planning/MILESTONES.md`** — v1.2.1 entry inserted under the v1.2 entry. No new top-level sections.
- **`28-VERIFICATION.md`** — append-only update from Phase 29 closure plans (D-17). Don't move the file; don't rewrite original evidence.
- **3 backtest path callers** — `backtest/cli.py`, `backtest/data_fetcher.py`, `web/routes/backtest.py`. Each gets its own `Path(__file__).resolve().parents[N]` constant; the resolution is module-private.
- **Trace panel render path (UAT-17-1, UAT-17-2)** — both fixes touch the same render code; Wave 3 serialises them to avoid merge conflicts.

</code_context>

<specifics>
## Specific Ideas

- **The ATR seed must be the persisted, engine-computed value** — not a re-derivation from defaults. This is the explicit Phase 17 LEARNING from 2026-05-10 (project-local). The seed value is computed by `signal_engine.compute_atr` over full history; the trace panel writes that seed value alongside the displayed window so the hand-recalc has a deterministic anchor. Convergence tolerance stays 1e-6 per ROADMAP SC for DEBT-01.
- **iOS Safari fix is server-side rendering, not cookie-attribute tweaks.** The cookie `tsi_trace_open` is already written; the failure mode is that on iOS Safari reload, the `<details>` element is rendered closed and client JS doesn't re-open it before paint. Fix: backend reads the cookie, renders `<details open>` directly. This is locality-correct (the `<details>` element's open state is a server-rendered attribute, not a client-side enhancement).
- **Yfinance spike scope.** Time-box ≤1 day. First diagnostic: run `python -m backtest --years 5` with verbose logging on `data_fetcher` and check whether (a) the Volume column shape changed in yfinance (post-0.2.55-style regression), or (b) signal-engine's RVol gate is now zero-ing trades on live data even though fixtures still pass. If (a) is fix-shape (one schema branch), stay in Phase 29. If (b) is fix-shape (engine logic regression), spawn Phase 29.5.
- **MILESTONES.md v1.2.1 entry shape** — single section under the v1.2 entry titled `### v1.2.1 — Retroactive Patch Wrap (2026-05-10)` with a 5-row table: `| Commit | Behaviour | Test | Note |`. Each row one line.
- **Sweep doc ordering for waves** — when the planner schedules Wave 2 in parallel, group by independence. All 7 sweep plans are file-disjoint (each writes to its own phase directory); they can run as a 7-way fan-out without coordination.

</specifics>

<deferred>
## Deferred Ideas

- **`paths.py` helper module** — considered for OPS-02 (D-14); deferred. Would centralise the `Path(__file__).resolve().parents[N]` constant but couples 3 modules to a fourth for what is one line of locality. Revisit if a fourth caller emerges in v1.3 (e.g., per-user state path resolution might warrant centralisation).
- **Per-commit retroactive `PLAN.md` for the 5 v1.2.1 commits** — considered (D-11); deferred. Heavy ceremony for ad-hoc fixes already in git history; single MILESTONES.md note + targeted tests is the right shape.
- **Loosen ATR(14) tolerance to 1e-3** — considered (D-03); deferred. Would acknowledge inherent Wilder seed drift but breaks the original 1e-6 SC. Solving it via seed exposure preserves both the SC and the trace UX.
- **True audit (not mechanical retrofit) of VALIDATION/SECURITY sweep** — considered (D-06, D-07); deferred. Scope risk; mechanical retrofit captures the format debt now and gaps surface as deferred items per phase, file-able as v1.3.x DEBT entries if any prove load-bearing.
- **Defer iOS Safari fix as v1.3.x known issue** — considered (D-04); deferred. Real bug for F&F users; fix it now while the fix is small and the trace-panel render path is fresh.

</deferred>

---

*Phase: 29-v1-2-1-retroactive-patch-wrap-validation-sweep*
*Context gathered: 2026-05-10*
