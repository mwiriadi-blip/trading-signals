# Phase 28: v1.2 UAT Closure - Context

**Gathered:** 2026-05-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Operator-facing closure of the 8 deferred v1.2 UAT scenarios so v1.2 closes cleanly before v1.3 substance lands. Scenarios are split across three v1.2 phases:

- **Phase 17** (3 scenarios): ATR(14) hand-recalc to 1e-6, iOS Safari tap-to-toggle on the trace panel, cookie persistence across one browser reload.
- **Phase 23** (2 scenarios): live-yfinance CLI run (`python -m backtest --years 5`, rc=0 + cumulative-return >100% gate clean), `/backtest` browser visual smoke (no template-leak artefacts).
- **Phase 26** (3 row-groups, 6 underlying scenarios): cold-start smoke + UAT-2..6 multi-tab market-scoping browser walkthrough on the production droplet.

All sign-off rolls into a single `28-VERIFICATION.md`. Verification target is the live production droplet `https://signals.mwiriadi.me`. No staging clone. No code changes expected as part of Phase 28 itself; any defect surfaced is handed to Phase 29.

This phase is mechanical UAT closure; ROADMAP.md sets `Plan-time verification: none`.

</domain>

<decisions>
## Implementation Decisions

### Verification approach (P26 sign-off basis)

- **D-01:** All 6 Phase 26 UATs (cold-start + UAT-2..6) are **re-run in browser**, not signed off retroactively against the existing `26-UAT.md` xfail-flipped-green pytest coverage. The literal text of DEBT-01 ("verify ... end-to-end against production droplet + browser/phone") is honoured: Phase 26's automated coverage is treated as a regression net, not as the primary evidence for Phase 28 sign-off.
- **D-02:** Browser scenarios are MCP-driven on **desktop Chrome via Playwright MCP**. The operator does not click manually for desktop runs — Claude drives the browser session against the production droplet during Phase 28 execution.
- **D-03:** The single operator-manual scenario is **Phase 17 iOS Safari tap-to-toggle** (it requires real iOS Safari touch semantics; no MCP equivalent in scope). Operator runs this on their iPhone against the live droplet and pastes a 1-line PASS/FAIL note into VERIFICATION.md.
- **D-04:** MCP automation is extended **beyond Phase 26** to also cover: Phase 17 cookie persistence across reload, Phase 17 ATR(14) hand-recalc to 1e-6 (Playwright scrapes displayed OHLC; Python recomputes ATR(14); asserts |delta| ≤ 1e-6), and Phase 23 `/backtest` visual smoke (Playwright loads `/backtest`, asserts no `{{`/`}}`/`Undefined`/missing-CSS markers in rendered HTML).
- **D-05:** Phase 23 live-yfinance CLI run (`python -m backtest --years 5`) is **Bash-driven, not MCP-driven** — it's not a browser test. Claude runs it live during Phase 28; rc + last 10 lines of stdout are pasted into the Evidence cell.
- **D-06:** Per-scenario evidence shape is **text PASS/FAIL + 1-line observed-behaviour note**. No screenshots required. No per-scenario timestamp column.

### VERIFICATION.md format

- **D-07:** `28-VERIFICATION.md` **groups scenarios by source phase** with three sections: `## Phase 17 Scenarios`, `## Phase 23 Scenarios`, `## Phase 26 Scenarios`. This mirrors how DEBT-01 enumerates the deferred items and lets each section cite its source UAT.md / VERIFICATION.md.
- **D-08:** Frontmatter **matches Phase 27 verbatim** (`phase`, `verified`, `status`, `score`, `overrides_applied`, `test_suite`, `notes`). `score` is `8/8 scenarios verified` when fully green; the test-suite gate line records the pytest baseline at HEAD at sign-off time.
- **D-09:** Per-scenario row uses **5 columns**: `Scenario | Source | Mode | Status | Evidence`. `Source` is the source phase + original UAT identifier (e.g., `17 / UAT-1`, `26 / UAT-3`). `Mode` is `MCP` / `Manual` / `CLI`.
- **D-10:** **No deep-dive sections.** The table is the whole document. This is a deliberate departure from Phase 27's per-plan `### Plan NN` evidence blocks — Phase 28 is 8 manual scenarios, not 14 plans of code work, so a flat table is the correct shape.
- **D-11:** Phase 26's UAT-2..6 (5 multi-tab sub-scenarios) — open question for the planner: render as **5 rows or 1 row-group**. Default lean: 5 rows so each UAT-N has its own auditable PASS/FAIL line, taking total table row-count to: Phase 17 (3) + Phase 23 (2) + Phase 26 (1 cold-start + 5 multi-tab) = **10 rows for the 8-conceptual-scenario set**. The planner may collapse if it makes the table unreadable; if so, it must preserve UAT-N evidence in the single Evidence cell.

### Helper artefacts

- **D-12:** Playwright runs are **persisted as pytest-playwright spec files under `tests/uat/`** (e.g., `tests/uat/test_uat_17_atr_handcalc.py`, `tests/uat/test_uat_26_multitab.py`). They are part of the project pytest suite but are **gated by an `@pytest.mark.uat` marker** so the default `pytest` invocation skips them and the full UAT pass is `pytest -m uat`. This protects the existing 2006-test default-suite runtime.
- **D-13:** `pytest-playwright` is added as a **dev dependency** during Phase 28. Bringing in a new dev dep is in scope here because it's the substrate that lets Phase 28 produce reusable evidence rather than transient one-shot MCP runs.
- **D-14:** **No separate operator checklist doc.** The iPhone Safari row in `28-VERIFICATION.md` carries an inline acceptance note ("open `/markets/SPI200/dashboard` on iPhone Safari, tap the trace panel toggle, observe collapse, reload, observe state preserved"). The operator reads it and fills in PASS/FAIL + 1-line note. No `28-OPERATOR-CHECKLIST.md`. No video.
- **D-15:** Phase 23 live-yfinance CLI scenario is **NOT persisted as a test** — running it under pytest would couple the test suite to live Yahoo network availability and rate limits. Phase 28 records the live run output once; future regression coverage relies on the existing `tests/test_backtest_*` deterministic-fixture suite, not the live run.

### Failure handling

- **D-16:** Failure policy is **aggregate-and-roll-into-Phase-29**. All 8 scenarios run regardless of intermediate FAILs. Phase 28 does not halt on first failure. Fixes for any FAIL are scoped into Phase 29 (v1.2.1 patch wrap), which already exists as the patch-wrap phase by design.
- **D-17:** Flake threshold is **3 attempts max** (the first run + up to 2 retries). If any attempt within those 3 passes, the scenario is PASS — with a `(retried Nx)` note appended to the Evidence cell. Three consecutive failing attempts is a real FAIL.
- **D-18:** When FAILs are aggregated, `28-VERIFICATION.md` frontmatter `status` is **`partial`** (not `passed-with-deferrals`, not `failed`). `partial` is a new value relative to the Phase 27 precedent that only used `passed` — the planner should note this in the frontmatter `notes:` field and reference D-18 so future readers know it's an intentional vocabulary extension.
- **D-19:** Each FAIL Evidence cell carries: `symptom` + `suspected layer` + `reproduction command`. Example: `"FAIL: ATR(14) shows 14.732, hand-recalc = 14.521 (delta 0.211 > 1e-6 tolerance) | suspected: signal_engine.compute_atr or trace render | repro: pytest -m uat tests/uat/test_uat_17_atr_handcalc.py"`. This gives Phase 29 a real lead — the FAIL row is the hand-off contract.
- **D-20:** Phase 29's roadmap entry is updated implicitly: anything Phase 28 records as FAIL is added to Phase 29's scope on top of its existing DEBT-02/03/04 + OPS-02 work. The planner for Phase 29 reads `28-VERIFICATION.md` as required input.

### Claude's Discretion

- Exact wording of each iPhone Safari acceptance note in the table (operator-readable, ≤1 line).
- Whether the Phase 26 UAT-2..6 multi-tab scenarios render as 5 rows or 1 row-group (D-11 default lean is 5; planner may collapse if necessary).
- Exact Playwright assertion shape per scenario (e.g., for cookie persistence: assert `Set-Cookie` round-trip vs. assert displayed-toggle-state survives reload — both prove the SC, planner picks).
- Where Playwright traces / screenshots get written if a run fails (default `tests/uat/_traces/` gitignored — only the textual rc/output goes into VERIFICATION.md regardless).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase boundary + requirements
- `.planning/ROADMAP.md` §"Phase 28: v1.2 UAT Closure" — phase goal, success criteria, plan-time verification = none.
- `.planning/REQUIREMENTS.md` §DEBT-01 — explicit enumeration of the 8 deferred UAT scenarios.

### Source v1.2 phase artefacts (the deferred UATs trace back to these)
- `.planning/milestones/v1.2-phases/17-per-signal-calculation-transparency/17-VERIFICATION.md` — UAT-1..3 deferred items (ATR-recalc, iOS Safari tap, cookie reload). The "ohlc_window=[]" caveat is documented here.
- `.planning/milestones/v1.2-phases/23-five-year-backtest-validation-gate/23-HUMAN-UAT.md` — UAT-1..2 deferred items (live yfinance CLI, /backtest browser visual smoke).
- `.planning/milestones/v1.2-phases/26-phase-25-followup-multi-tab-scoping-fixes/26-UAT.md` — UAT-1 cold-start + UAT-2..6 multi-tab walkthroughs. Documents the existing xfail-flipped-green coverage that Phase 28 D-01 is consciously *not* relying on as primary evidence.

### Format precedent
- `.planning/milestones/v1.2-phases/27-code-quality-correctness-sweep-apply-2026-05-07-code-review-/27-VERIFICATION.md` — frontmatter shape (`phase`, `verified`, `status`, `score`, `overrides_applied`, `test_suite`, `notes`) that D-08 inherits verbatim. Note: Phase 28 deliberately *drops* the per-plan deep-dive sections that follow the table in this precedent (D-10).

### Project constraints
- `CLAUDE.md` §Rules — "ALWAYS run tests after code changes", file-size and PII rules. Relevant when persisting Playwright specs under `tests/uat/`.
- `.claude/LEARNINGS.md` (project-local) — Phase 17 trace-panel drift entry (2026-05-10) is relevant context for the ATR-recalc UAT (the trace panel reads engine-resolved `vote_params` per `signal_engine.resolve_vote_params`; the recalc must read the same persisted values, not re-derive defaults).

### Hand-off target
- `.planning/ROADMAP.md` §"Phase 29: v1.2.1 Retroactive Patch Wrap + Validation Sweep" — the absorber for any Phase 28 FAIL per D-16 / D-19 / D-20.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- **Existing pytest suite (2006 tests, ~265s at HEAD per Phase 27 baseline):** Phase 28's `tests/uat/` additions extend this suite under a new `@pytest.mark.uat` marker so the default invocation stays at ~2006/265s. Confirmed via `tests/conftest.py` already exists.
- **`signal_engine.resolve_vote_params(settings)` + persisted `sig['vote_params']` (Phase 17 polish, commit `587b6f0`):** The ATR(14) hand-recalc UAT must read the same persisted values the engine wrote, never re-derive from defaults — this is the project-LEARNING from 2026-05-10. The recalc helper (Playwright scrape + Python recompute) follows the same locality discipline.
- **`tests/test_backtest_*` deterministic-fixture suite:** Already covers backtest correctness against pinned fixtures. Phase 28's Phase 23 CLI scenario tests *live yfinance* specifically — the existing fixture-based tests are deliberately not duplicated as a live-network UAT (D-15).
- **Phase 27 `27-VERIFICATION.md` template:** Direct format precedent for Phase 28 frontmatter (D-08).

### Established Patterns

- **Production droplet is the verification target.** Project has no staging clone; v1.2 + v1.1 + v1.0 all signed off against `signals.mwiriadi.me`. Phase 28 follows suit.
- **`@pytest.mark.<marker>` for slow / opt-in tests** — established by the existing pytest config; new `uat` marker fits the same idiom (see `pytest-playwright` integration plan in D-12).
- **`.planning/phases/<NN>-<slug>/<NN>-VERIFICATION.md` location convention** — all v1.2 phases use this layout. Phase 28 inherits it: `.planning/phases/28-v1-2-uat-closure/28-VERIFICATION.md`.

### Integration Points

- **`tests/uat/` (NEW):** Phase 28 creates this directory + `conftest.py` (Playwright fixtures + base_url config pointing at the prod droplet) + per-UAT spec files. Plus `pyproject.toml` / `requirements-dev.txt` adds `pytest-playwright` and the marker registration in `pytest.ini` / `pyproject.toml`.
- **`.planning/phases/28-v1-2-uat-closure/28-VERIFICATION.md`:** The single closure artefact (D-08 / D-09 / D-10).
- **Phase 29 hand-off:** Any FAIL row in `28-VERIFICATION.md` is consumed by `/gsd-discuss-phase 29` (or its planner) per D-19 / D-20. No automated linkage — the contract is "Phase 29 reads 28-VERIFICATION.md".

</code_context>

<specifics>
## Specific Ideas

- **Playwright MCP server choice was deliberated and locked to `playwright` MCP** (over `chrome-devtools-mcp` or `Claude_in_Chrome`). Rationale: Playwright is the substrate the persisted `tests/uat/` specs run on (D-12), so using Playwright MCP for the live drive keeps the live-evidence shape and the persisted-test shape symmetric — the same selectors, the same assertions, the same flake-retry semantics.
- **The 1e-6 ATR tolerance comes verbatim from ROADMAP.md SC-1 + REQUIREMENTS DEBT-01.** Don't loosen it. If the recalc shows e.g. a 1e-3 mismatch, that's a real FAIL → Phase 29 territory.
- **The `/backtest` "no template-leak" assertion** should grep the rendered HTML for at least: `{{`, `}}`, `Undefined`, `None None` (Python str-repr leak), and a missing-CSS marker (e.g., absence of an expected stylesheet `<link>`). Planner refines the exact pattern set.
- **Phase 17 cookie-persistence "across one reload"** means: tap trace panel toggle → cookie set with toggle state → `page.reload()` → toggle state visually preserved → no logout / session loss. Two concrete things being verified together (cookie write + cookie read), not one.

</specifics>

<deferred>
## Deferred Ideas

- **Cross-browser desktop check (Firefox).** Considered as a Phase 26 client env option; deferred — no Chrome-specific htmx-swap suspicion on record. Revisit only if a real defect surfaces in Chrome that suggests cross-browser variance.
- **Per-scenario screenshot evidence in VERIFICATION.md.** Considered for visual scenarios (cold-start, /backtest, market-strip); deferred — D-06 locks text-only evidence. Reusable Playwright traces still get captured by the spec runner under `tests/uat/_traces/` (gitignored) for debugging if a UAT fails, but they don't go into VERIFICATION.md.
- **Pre-recorded video of the iPhone Safari run.** Considered for the iOS scenario; deferred — D-14 keeps it inline-checklist-only.
- **A separate `28-OPERATOR-CHECKLIST.md` doc.** Considered; deferred — D-14 keeps the checklist inline in the VERIFICATION.md row.
- **Halt-on-first-FAIL with same-phase hotfix.** Considered as failure-handling option; deferred — D-16 routes fixes to Phase 29 instead so Phase 28 stays mechanical.
- **`status: failed` on FAIL.** Considered; deferred — D-18 uses `partial` because it's more honest than `passed-with-deferrals` but doesn't block the v1.3-substance roadmap the way `failed` would.

</deferred>

---

*Phase: 28-v1-2-uat-closure*
*Context gathered: 2026-05-10*
