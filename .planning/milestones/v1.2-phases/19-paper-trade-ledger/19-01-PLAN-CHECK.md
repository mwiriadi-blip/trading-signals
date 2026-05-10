# Phase 19 Plan Check — 19-01-PLAN.md

**Checked:** 2026-04-30
**Verdict:** PASS (with one WARNING)
**Plans checked:** 1 (single-plan phase)
**Issues:** 0 blockers, 2 warnings

---

## Verdict: PASS

The plan fully covers every phase goal, requirement, and locked decision. Every CONTEXT.md
verification item has a concrete producing task and a greppable acceptance criterion. The
plan is executable as written.

---

## Strengths

1. **D-22 (400 not 422) is fully operationalized** — plan/interfaces block explicitly amends
   every CONTEXT D-04 "422" to "400", pin traces to `web/app.py:174-177` global handler, and
   all test names use `_returns_400`. The planner caught and corrected the CONTEXT wording
   before it could cause a test mismatch (plan lines 301-303, 579-593).

2. **Kwarg-default capture trap is closed at every write site** — Task 4 action requires
   `from system_params import STRATEGY_VERSION` INSIDE `_apply` closure bodies (not at module
   top, not as kwarg default), and `TestStrategyVersionTagging::test_open_strategy_version_fresh_read_after_monkeypatch`
   verifies the trap is actually closed via monkeypatch. This directly implements the 2026-04-29
   LEARNINGS entry (plan lines 632-633, 883-884).

3. **Concurrency race test is designed-from-scratch and specific** — `TestConcurrentOpen::test_concurrent_open_does_not_collide`
   uses `multiprocessing.Process`, mirrors the `mutate_state` kernel exactly inside each worker,
   and asserts non-colliding IDs. This is the first multiprocessing test in the repo and it
   directly validates the D-15 atomicity claim (plan lines 638-640, RESEARCH §Pattern 9).

4. **405 + Allow header fully specified** — `_method_not_allowed_405(allow='GET')` helper is
   quoted verbatim with `headers={'Allow': allow}`, every immutability test asserts
   `response.headers.get('allow') == 'GET'`, and this covers PATCH, DELETE, and close-on-closed
   (plan lines 600-602, 740-750).

5. **Hex-boundary fact-check is explicit** — plan corrects CONTEXT D-14's incorrect prose
   ("dashboard.py does NOT import system_params") against the real AST guard at
   `tests/test_signal_engine.py:556-569`, and documents that `pnl_engine` is not in
   `FORBIDDEN_MODULES_DASHBOARD`. This prevents a false-positive test failure during execution
   (plan lines 324-328).

---

## Gaps (Warnings)

### WARNING 1 — LEDGER-02 field name mismatch (`pnl` vs `realised_pnl`)

**Dimension:** requirement_coverage
**Severity:** WARNING

REQUIREMENTS.md LEDGER-02 (line 34) lists the field as `pnl` (nullable). CONTEXT.md D-09
(line 179) defines the canonical row shape with the field named `realised_pnl`. The plan
implements `realised_pnl` throughout (fixture, routes, dashboard, tests). The CONTEXT.md
D-09 row shape supersedes the REQUIREMENTS.md text and the implementation is internally
consistent, but the mismatch means LEDGER-02's exact wording is not literally satisfied.

Fix: annotate LEDGER-02 in REQUIREMENTS.md that `pnl` was renamed to `realised_pnl` per
CONTEXT D-09, or accept the CONTEXT as the authoritative spec override. No code change
needed — the plan's implementation is correct.

### WARNING 2 — HTML form vs JSON body path left open until GREEN time (planner D-17)

**Dimension:** task_completeness
**Severity:** WARNING

Task 4 action (lines 851-856) defers the decision on whether route handlers use `Form(...)`
parameters or `application/json` + client-side serialization to "GREEN time". This is
explicitly documented and accepted by the planner, but it means the dashboard HTML form
shape in Task 5 depends on the Task 4 decision. The plan correctly marks the Task 4
acceptance criteria as testing via `client.post(..., json={...})` (TestClient path), and
the SUMMARY section is told to document the decision. No blocker, but the executor must
make this decision before Task 5 and document it.

---

## Hex-Boundary Audit: PASS

| Module | Allowed imports | Plan states | Status |
|--------|----------------|-------------|--------|
| `pnl_engine.py` | `math`, `typing` only | planner D-19 + Task 3 action explicit | PASS |
| `dashboard.py` | Adds `from pnl_engine import compute_unrealised_pnl` | LOCAL inside helpers; not in `FORBIDDEN_MODULES_DASHBOARD` | PASS |
| `web/routes/paper_trades.py` | `pnl_engine`, `state_manager.mutate_state`, `system_params.STRATEGY_VERSION` (all LOCAL inside `_apply`) | Task 4 action + acceptance criteria grep for zero module-top imports | PASS |
| AST guard extension | `PNL_ENGINE_PATH` appended to both `_HEX_PATHS_ALL` and `_HEX_PATHS_STDLIB_ONLY` | Task 3 action lines 527-540 + acceptance criteria grep returning ≥3 | PASS |

One nuance: RESEARCH.md summary line 108 says "pnl_engine.py imports nothing project-internal
beyond `system_params`", but planner D-19 pins it to `math + typing` ONLY (no `system_params`).
The plan correctly resolves this: callers pass multiplier/cost as explicit float args; pnl_engine
never imports system_params. The plan's Task 3 module body confirms this. PASS.

---

## 400 vs 422 Audit (D-22): PASS

CONTEXT D-04 uses "422" throughout. Plan/interfaces block at lines 301-303 explicitly amends:
"CODEBASE 422→400 remap... Phase 19 routes inherit this handler. CONTEXT D-04's '422' wording
is HEREBY AMENDED in this plan: every '422' mention becomes 400. Tests assert `r.status_code == 400`."
Every test in `TestOpenValidation` and `TestEditPaperTrade` is named `_returns_400`. Acceptance
criteria grep checks confirm 400. The CONTEXT verification item #4 in the plan's `<verification>`
block also says "400 with explicit reason (D-04 + planner D-22)". PASS.

---

## 405 + Allow Header Audit: PASS

`_method_not_allowed_405(allow='GET')` helper quoted verbatim at plan lines 740-750 with
`headers={'Allow': allow}`. Tests `test_patch_closed_row_returns_405_with_allow_header` and
`test_delete_closed_row_returns_405_with_allow_header` both assert `response.headers.get('allow') == 'GET'`.
`test_close_already_closed_row_returns_405_with_allow_header` adds close-on-closed coverage.
The `TestSentinelLockReleaseBeforeResponse` test verifies the sentinel is raised and resolved
before the Response is built (preventing a lock-held-across-network-write bug). PASS.

---

## Concurrency Race Test Audit: PASS

`TestConcurrentOpen::test_concurrent_open_does_not_collide(tmp_path)` uses
`multiprocessing.Process`, mirrors the `mutate_state` flock kernel inside each worker,
asserts non-colliding IDs (`SPI200-{today}-001` and `SPI200-{today}-002`). Explicitly noted
as "first multiprocessing test in repo". RESEARCH §Pattern 9 is cited verbatim. PASS.

---

## Phase 22 LEARNINGS Audit

| Learning | Where applied | Status |
|----------|--------------|--------|
| Kwarg-default capture trap (2026-04-29) | `from system_params import STRATEGY_VERSION` INSIDE `_apply` closure; monkeypatch test asserts | PASS |
| Migration idempotent | `_migrate_v5_to_v6`: single `if 'paper_trades' not in s` guard; `test_migrate_v5_to_v6_idempotent_paper_trades_already_populated` | PASS |
| Mutable-default avoidance | All helpers use `param=None` then `if param is None: param = []` | PASS |
| NaN propagation / math.isnan guard before f-string | `_render_paper_trades_open` body quotes the exact guard; Task 5 test `test_open_table_renders_na_when_last_close_nan` | PASS |
| Self-invalidating grep gate | All acceptance criteria greps use `grep -nE '^def NAME\b'` line-anchored | PASS |
| POSIX flock not reentrant | `_apply` closures MUST NOT call `load_state`/`save_state`; enforced by `test_405_response_is_built_after_mutate_state_returns` | PASS |

---

## Coverage Table

| ID | Description | Task | Acceptance / Test |
|----|-------------|------|-------------------|
| CONTEXT V-1 | `STATE_SCHEMA_VERSION` = 6 | Task 1 | `python3 -c "import system_params; print(STATE_SCHEMA_VERSION)"` → 6; `grep -nE` acceptance |
| CONTEXT V-2 | v5→v6 migration stamps `paper_trades=[]` | Task 2 | `TestMigrateV5ToV6::test_migrate_v5_to_v6_backfills_paper_trades_when_absent` |
| CONTEXT V-3 | POST valid SPI200 LONG → composite ID + strategy_version + entry_cost_aud=3.0 | Task 4 | `TestOpenPaperTrade::test_open_valid_spi200_long_appends_row` |
| CONTEXT V-4 | Future entry_dt → 400 | Task 4 | `TestOpenValidation::test_open_future_entry_dt_returns_400` |
| CONTEXT V-5 | Stop-side 400 (LONG stop > entry) | Task 4 | `TestOpenValidation::test_open_long_with_stop_above_entry_returns_400` |
| CONTEXT V-6 | PATCH open row updates; strategy_version refreshed | Task 4 | `TestEditPaperTrade::test_patch_open_row_updates_fields` |
| CONTEXT V-7 | PATCH closed row → 405 + body + Allow: GET | Task 4 | `TestImmutability::test_patch_closed_row_returns_405_with_allow_header` |
| CONTEXT V-8 | DELETE open row → removed | Task 4 | `TestDeletePaperTrade::test_delete_open_row_removes_it` |
| CONTEXT V-9 | DELETE closed row → 405 | Task 4 | `TestImmutability::test_delete_closed_row_returns_405_with_allow_header` |
| CONTEXT V-10 | Close → realised_pnl correct LONG + SHORT × SPI + AUDUSD | Task 4 | `TestClosePaperTrade::test_close_long_spi200_realised_pnl_correct` + `test_close_short_audusd_realised_pnl_correct` |
| CONTEXT V-11 | Dashboard `/` contains stats-bar + open table + closed table + close-form | Task 5 | `TestRenderDashboardComposition::test_render_dashboard_includes_paper_trades_region` |
| CONTEXT V-12 | Stats bar values match hand-computed fixture | Task 5 | `TestRenderPaperTradesStats::test_stats_bar_renders_realised_total` + unrealised |
| CONTEXT V-13 | Empty-state copy strings (D-16) | Task 5 | `test_open_table_empty_state_copy` + `test_closed_table_empty_state_copy` |
| CONTEXT V-14 | Full pytest suite passes | Task 6 | `pytest tests/ -x -q` in Task 6 verify |
| CONTEXT V-15 | Hex-boundary grep on dashboard.py | Task 5 + Task 6 | acceptance criteria grep + Task 6 verification item 15 |
| CONTEXT V-16 | pnl_engine.py forbidden-imports AST pass | Task 3 | `pytest tests/test_signal_engine.py::TestDeterminism -x` |
| CONTEXT V-17 | Concurrent open no collision | Task 4 | `TestConcurrentOpen::test_concurrent_open_does_not_collide` |
| ROADMAP SC-1 | POST /paper-trade/open → validated → appended | Task 4 | full `TestOpenPaperTrade` + `TestOpenValidation` |
| ROADMAP SC-2 | POST close → realised P&L → status=closed | Task 4 | `TestClosePaperTrade` |
| ROADMAP SC-3 | Closed rows immutable; 405 on PATCH/DELETE | Task 4 | `TestImmutability` |
| ROADMAP SC-4 | Open table with unrealised MTM | Task 5 | `TestRenderPaperTradesOpenTable` |
| ROADMAP SC-5 | Closed table sortable by exit_dt desc | Task 5 | `TestRenderPaperTradesClosedTable::test_closed_table_sorted_by_exit_dt_desc` |
| ROADMAP SC-6 | Aggregate stats (realised, unrealised, wins, losses, win rate) | Task 5 | `TestRenderPaperTradesStats` (8 tests) |
| ROADMAP SC-7 | Atomic write via mutate_state flock kernel | Task 4 | `TestImmutability::TestSentinelLockReleaseBeforeResponse` + SC-7 in `<success_criteria>` |
| LEDGER-01 | Web form validated server-side; rejects future dates / negative prices / contracts ≤ 0 | Task 4 | `TestOpenValidation` (13 tests, each D-04 rule) |
| LEDGER-02 | Per-trade row persisted with strategy_version (`pnl` named `realised_pnl` per D-09) | Task 4 | `TestOpenPaperTrade::test_open_writes_full_d09_row_shape` (13 keys) |
| LEDGER-03 | Open trades table with unrealised MTM | Task 5 | `TestRenderPaperTradesOpenTable` |
| LEDGER-04 | Closed table sortable desc; closed rows immutable | Task 4 + 5 | `TestImmutability` + `test_closed_table_sorted_by_exit_dt_desc` |
| LEDGER-05 | Close form; server computes realised P&L; closed rows immutable | Task 4 | `TestClosePaperTrade` + `TestCloseFormFragment` |
| LEDGER-06 | Aggregate stats bar | Task 5 | `TestRenderPaperTradesStats` |
| VERSION-03 | Every paper-trade row tagged with STRATEGY_VERSION at write time | Task 4 | `TestStrategyVersionTagging` (3 tests, monkeypatch asserting fresh read) |

---

## Dimension Scores

| Dimension | Status | Notes |
|-----------|--------|-------|
| 1 Requirement Coverage | PASS | LEDGER-01..06 + VERSION-03 all have tasks; frontmatter field lists all 7 |
| 2 Task Completeness | PASS | All 6 tasks have files, action, verify (automated), acceptance_criteria, done |
| 3 Dependency Correctness | PASS | `depends_on: []` wave 1; no circular deps; Phase 22 already complete |
| 4 Key Links Planned | PASS | 7 key_links in frontmatter; each traced to a task action |
| 5 Scope Sanity | PASS | 6 tasks; dense but single-plan justified by tight coupling of migration→module→routes→dashboard→summary |
| 6 Verification Derivation | PASS | 22 must_haves.truths are user-observable and greppable |
| 7 Context Compliance | PASS (w/WARNING) | D-01..D-16 all covered; D-22 correctly overrides D-04; LEDGER-02 field name mismatch is a WARNING only |
| 7b Scope Reduction | PASS | No "v1/static/future/placeholder" language; all decisions delivered in full |
| 7c Architectural Tier Compliance | PASS | Responsibility map in RESEARCH.md; all capabilities in correct tiers |
| 8 Nyquist Compliance | PASS | Every task has `<automated>` pytest command; TDD RED/GREEN shape; sampling continuous across 5 tasks |
| 9 Cross-Plan Data Contracts | N/A | Single plan |
| 10 CLAUDE.md Compliance | PASS | 2-space indent, single-quotes, ruff, snake_case, UPPER_SNAKE, exact version pins respected; atomic write; never-crash email pattern unchanged |
| 11 Research Resolution | PASS | RESEARCH.md has no `## Open Questions` section (all resolved inline) |
| 12 Pattern Compliance | PASS | PATTERNS.md maps 19 analogs + 3 design-from-scratch; plan references each analog by file:line |

