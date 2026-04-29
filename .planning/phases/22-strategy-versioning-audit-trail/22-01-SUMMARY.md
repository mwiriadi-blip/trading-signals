---
phase: 22-strategy-versioning-audit-trail
plan: 01
subsystem: state-schema
tags: [versioning, schema-migration, audit-trail, dashboard, system-params, hex-boundary]

# Dependency graph
requires:
  - phase: 14-position-mods
    provides: STATE_SCHEMA_VERSION dispatch chain (MIGRATIONS dict, _migrate walker, v2->v3 backfill precedent for position dicts)
  - phase: 8-multi-tier-contracts
    provides: _migrate_v1_to_v2 precedent + idempotent migration discipline
  - phase: 5-dashboard
    provides: render_dashboard composition + _render_footer + html.escape leaf-site convention
  - phase: 16.1-auth
    provides: hex-boundary precedent for primitive-arg pattern (is_cookie_session bool flowed via state, not module import)
provides:
  - STRATEGY_VERSION = 'v1.2.0' string constant on system_params (single source of truth for the active version)
  - STATE_SCHEMA_VERSION bump 3 -> 4 with _migrate_v3_to_v4 walker entry
  - state.signals[<inst>].strategy_version field on every dict-shaped row (live writes + v1.1.0 backfill)
  - state_manager._read_signal_strategy_version defensive-read helper (D-06 WARN log)
  - dashboard._resolve_strategy_version primitive-arg path (hex-boundary preserved)
  - docs/STRATEGY-CHANGELOG.md (3 entries, newest-first, locked constants block)
affects: [phase-19-ledger, phase-23-future, phase-19-paper-trades]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Schema bump rules pre-existing tests pinning the previous version - assertions on schema_version must compare against STATE_SCHEMA_VERSION (the symbol), not the literal value"
    - "Defensive-read helper with single-WARN-per-fallback log surfaces silent migration drift in journalctl"
    - "Primitive-str arg into render layer for cross-hex data (LEARNINGS 2026-04-27 reinforced)"
    - "Lex-max tie-break for transient cross-instrument version disagreement (max(versions, key=str))"

key-files:
  created:
    - docs/STRATEGY-CHANGELOG.md
    - tests/test_system_params.py
    - tests/test_strategy_changelog.py
  modified:
    - system_params.py
    - state_manager.py
    - main.py
    - dashboard.py
    - tests/test_state_manager.py
    - tests/test_main.py
    - tests/test_dashboard.py
    - tests/fixtures/dashboard/sample_state.json
    - tests/fixtures/dashboard/golden.html
    - tests/fixtures/dashboard/golden_empty.html

key-decisions:
  - "STRATEGY_VERSION = 'v1.2.0' (D-02): semver with 'v' prefix matches git tag convention, greppable for bump audit"
  - "Backfill value v1.1.0 (D-05): existing rows on first v1.2 deploy were produced under v1.1 logic - honest about lineage"
  - "Migration is additive + idempotent: existing fields preserved exactly; rows already carrying strategy_version not overwritten"
  - "Defensive read defaults to v1.0.0 with WARN log when field absent (D-06): belt-and-suspenders surfaces drift rather than silent fallback"
  - "Dashboard reads version off state dict, never imports system_params.STRATEGY_VERSION (LEARNINGS 2026-04-27 hex-boundary)"
  - "Tie-break = lexicographic max via max(versions, key=str): deterministic, approximate for cross-MAJOR but converges within one daily run"
  - "Footer placement (D-08 not pinned to a specific surface): chosen footer because least-disruptive; doesn't reorder UI-SPEC §Component Hierarchy"

patterns-established:
  - "Schema-bump test alignment: every prior `schema_version == N` literal assertion must move to `== STATE_SCHEMA_VERSION` so the next bump is one-line"
  - "WARN-on-fallback: defensive-read helpers emit a single [State] WARN per fallback so the operator sees migration drift in journalctl"
  - "Primitive-arg render hex-boundary (Phase 16.1 D-13 generalised): when a render module needs a value owned by system_params, pass it as a primitive arg, never as a module-level import"

requirements-completed: [VERSION-01, VERSION-02]
# VERSION-03 (paper_trades tagging) is the contract Phase 22 EXPOSES; Phase 19 (LEDGER) consumes it from day one per D-07. Phase 22 itself touches no paper_trades surface (array does not exist on the droplet yet).

# Metrics
duration: ~22min
completed: 2026-04-30
---

# Phase 22 Plan 01: Strategy Versioning & Audit Trail Summary

**Adds STRATEGY_VERSION='v1.2.0' to system_params, bumps STATE_SCHEMA_VERSION 3->4 with v3->v4 backfill of strategy_version='v1.1.0' on existing dict-shaped signal rows, tags every fresh signal-row write with the live constant via fresh attribute access (no kwarg-default capture), renders the version in the dashboard footer through a primitive str arg (hex-boundary preserved), and ships docs/STRATEGY-CHANGELOG.md with three honest entries (v1.0.0 / v1.1.0 / v1.2.0).**

## Performance

- **Duration:** ~22 minutes
- **Started:** 2026-04-29T20:24:30Z
- **Completed:** 2026-04-29T20:46:34Z
- **Tasks:** 6 (5 implementation + 1 verification/summary)
- **Files modified:** 10 (4 source + 1 doc + 5 test/fixture files; 3 newly created)

## Accomplishments

- `system_params.STRATEGY_VERSION = 'v1.2.0'` shipped, plus schema bump 3 -> 4 (D-01..D-04).
- `_migrate_v3_to_v4` registered in `MIGRATIONS[4]` — additive, idempotent, skips legacy int-shape signal rows (D-05/D-09).
- Every fresh signal-row write inside `run_daily_check` now carries `strategy_version=system_params.STRATEGY_VERSION` via fresh attribute access (sidesteps the global LEARNINGS 2026-04-29 kwarg-default capture trap).
- Dashboard footer renders the active strategy version via `_resolve_strategy_version(state)` + primitive `_render_footer(strategy_version)` arg — preserves the hex-boundary rule (no `STRATEGY_VERSION` import in dashboard.py).
- D-06 defensive-read helper `_read_signal_strategy_version` emits `[State] WARN signal row missing strategy_version field — defaulting to v1.0.0` so silent migration drift surfaces in journalctl.
- `docs/STRATEGY-CHANGELOG.md` seeded with three honest entries (v1.2.0 / v1.1.0 / v1.0.0, newest first), v1.2.0 pins the constants block as the lineage anchor.
- 19 new tests across 4 test files (5 system_params + 9 state_manager + 2 main + 4 dashboard + 4 changelog = pinned regression coverage for every D-decision).

## Task Commits

Each task was committed atomically on `main` (config branching_strategy=none):

1. **Task 1: Add STRATEGY_VERSION + bump STATE_SCHEMA_VERSION** — `7b6f6a3` (feat)
2. **Task 2: _migrate_v3_to_v4 + defensive-read helper + dispatch entry** — `d56f7c3` (feat)
3. **Task 3: Tag fresh signal rows with STRATEGY_VERSION** — `135450f` (feat)
4. **Task 4: Render strategy_version in dashboard footer** — `a1039bf` (feat)
5. **Task 5: STRATEGY-CHANGELOG.md + structure tests** — `3b6b5ac` (docs)

Task 6 (this SUMMARY.md) is a docs-only follow-up commit (separate from per-task commits).

_TDD breakdown: tasks 1-4 followed RED -> GREEN within a single commit (single-author project, no separate test/feat split per task per project convention)._

## Files Created/Modified

- `system_params.py` — added `STRATEGY_VERSION: str = 'v1.2.0'` constant block + bumped `STATE_SCHEMA_VERSION` 3 -> 4 with comment lineage. No new imports (D-10).
- `state_manager.py` — added `_migrate_v3_to_v4` (between `_migrate_v2_to_v3` and `MIGRATIONS`), registered as `MIGRATIONS[4]`, added `_read_signal_strategy_version` defensive-read helper. New `import logging` + module-level `logger` (stdlib only; not on FORBIDDEN_MODULES_STATE_MANAGER).
- `main.py` — added `'strategy_version': system_params.STRATEGY_VERSION` to the signal-row dict at the per-symbol writer (step 3.o of `run_daily_check`). Fresh attribute access — no kwarg default, no module-local alias.
- `dashboard.py` — added `_DEFAULT_STRATEGY_VERSION = 'v1.0.0'` + `_resolve_strategy_version(state)` helper. Changed `_render_footer()` signature to `_render_footer(strategy_version: str)`; emits `<div class="strategy-version">Strategy version: <code>...</code></div>` via `html.escape` leaf-site escape. `render_dashboard` resolves the version once and passes it as a primitive. `system_params.STRATEGY_VERSION` is NOT imported (hex-boundary preserved).
- `docs/STRATEGY-CHANGELOG.md` — NEW; three entries newest-first per CONTEXT D-08 verbatim.
- `tests/test_system_params.py` — NEW; 5 tests (presence, str type, regex format, exact 'v1.2.0', schema int + bool-subtype guard).
- `tests/test_state_manager.py` — added `TestMigrateV3ToV4` class (9 tests: backfill, full-walk, additive, idempotent, int-shape skip, skip-existing, v0->v4 chain, defensive-read WARN, defensive-read happy-path-no-noise). Updated 4 prior tests pinning `schema_version == 3` to compare against `STATE_SCHEMA_VERSION` (Rule-1 deviation).
- `tests/test_main.py` — added `TestRunDailyCheckTagsStrategyVersion` (2 tests: tag-applied + monkeypatch-bumped-flows-through).
- `tests/test_dashboard.py` — added `TestRenderDashboardStrategyVersion` (4 tests: footer-contains-version, default-when-missing, max-tie-break, no-STRATEGY_VERSION-import). Updated `test_footer_disclaimer` for the new signature.
- `tests/test_strategy_changelog.py` — NEW; 4 structure tests (file-exists, three-sections, descending-order, v1.2.0 constants block).
- `tests/fixtures/dashboard/sample_state.json` — backfilled `strategy_version='v1.2.0'` on both dict-shaped signal rows so the populated-render golden mirrors what the orchestrator writes from Phase 22 onward.
- `tests/fixtures/dashboard/golden.html` + `golden_empty.html` — regenerated via `tests/regenerate_dashboard_golden.py` (footer line is the only delta).

## Decisions Made

All locked decisions D-01..D-10 from `22-CONTEXT.md` honoured:

- **D-01..D-03 (constant location, format, bump semantics):** `STRATEGY_VERSION = 'v1.2.0'` placed at the top of `system_params.py` ABOVE the Phase 1 indicator constants block, with a docstring spelling out the bump rules (signal-logic only).
- **D-04 (schema bump):** `STATE_SCHEMA_VERSION: int = 4` with trailing comment lineage `Phase 14 -> v3 ... ; Phase 22 -> v4 (strategy_version on signal rows; D-04)`.
- **D-05 (migration value v1.1.0):** existing droplet rows on first v1.2 deploy will be stamped `'v1.1.0'`, honest about the deployment history.
- **D-06 (defensive read):** `_read_signal_strategy_version` returns `'v1.0.0'` + WARN; dashboard `_resolve_strategy_version` mirrors the same default + WARN per dict-shaped row missing the field.
- **D-07 (paper_trades deferred):** Phase 22 touches NO paper_trades surface. The `state.paper_trades` array doesn't exist on the droplet; Phase 19 (LEDGER) will consume `system_params.STRATEGY_VERSION` from day one.
- **D-08 (changelog content):** three entries verbatim from CONTEXT, newest-first, v1.2.0 pins the constants block.
- **D-09 (migration placement):** `_migrate_v3_to_v4` inserted between `_migrate_v2_to_v3` and the `MIGRATIONS` dict; registered as `MIGRATIONS[4]`.
- **D-10 (forbidden-imports unchanged):** `system_params.py` adds only string literals + comments; the AST guard `tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent` remains green. `state_manager.py` adds `import logging` only (stdlib, not on FORBIDDEN_MODULES_STATE_MANAGER); `dashboard.py` adds NO imports.

Risk-register coverage (all four rows mitigated by tests):

| Risk | Mitigation in this plan |
|------|------------------------|
| Migration drops a signal row | `test_migrate_v3_to_v4_preserves_other_signal_fields` asserts every original key on each row is preserved with exact value. |
| `STRATEGY_VERSION` import circularity | No new edges — `system_params` already imported by `state_manager.py`; `main.py` imports `system_params` at module top; `dashboard.py` does NOT import `STRATEGY_VERSION`. |
| Defensive read masks a real bug | Two log assertions: `test_defensive_read_logs_WARN_on_missing_strategy_version` proves the WARN fires; `test_defensive_read_returns_existing_value_without_warn` proves no false-positive noise. WARN message follows the `[State]` log-prefix convention from CLAUDE.md. |
| Operator forgets to bump on a real signal change | v1.2.0 changelog section pins the canonical constants block (`ATR_PERIOD = 14`, etc.). `test_changelog_v1_2_0_lists_constants` enforces presence — any future bump that drops a constant from the list surfaces in CI. |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Plan bug] Updated 4 pre-existing tests that hard-coded `schema_version == 3`**
- **Found during:** Task 2 (running full `pytest tests/test_state_manager.py` after the schema bump).
- **Issue:** The plan documented the schema bump 3 -> 4 but did NOT enumerate prior tests that pinned the literal value `3`. Four assertions failed: `test_migrate_walks_schema_version_to_current`, `test_v2_fixture_loads_with_manual_stop_backfilled_on_open_positions`, `test_save_then_load_v3_round_trips`, `test_v3_open_position_round_trips_through_save_state`.
- **Fix:** Updated each assertion to compare against `STATE_SCHEMA_VERSION` (the symbol from system_params) instead of the hardcoded `3`. The one assertion that explicitly pins the bump (`assert STATE_SCHEMA_VERSION == 3, 'Phase 14 bumps STATE_SCHEMA_VERSION to 3'`) was rewritten as `assert STATE_SCHEMA_VERSION == 4, 'Phase 22 bumps STATE_SCHEMA_VERSION to 4'`.
- **Files modified:** `tests/test_state_manager.py` (4 sites).
- **Verification:** Full `tests/test_state_manager.py` passes (96 tests).
- **Committed in:** `d56f7c3` (Task 2 commit).
- **New project pattern:** schema-bump tests should compare against `STATE_SCHEMA_VERSION`, not the literal value, so the next bump is a one-line edit. Documented in patterns-established frontmatter.

**2. [Rule 1 - Plan bug] Replaced impossible "no system_params import in dashboard.py" assertion with a `STRATEGY_VERSION` symbol-check**
- **Found during:** Task 4 (reading dashboard.py before editing).
- **Issue:** Plan task 4 acceptance criterion required `grep -nE "^import system_params\b|^from system_params\b" dashboard.py` to return ZERO matches. That is impossible — dashboard.py has imported `from system_params import (palette + contract specs)` since Phase 5/8 (legitimate, not on `FORBIDDEN_MODULES_DASHBOARD`). The actual hex-boundary rule from LEARNINGS 2026-04-27 is "STRATEGY_VERSION flows via state, not via module import" — that is what should be pinned.
- **Fix:** Replaced the planned `test_dashboard_does_not_import_system_params` test with `test_dashboard_does_not_import_strategy_version_symbol` — AST-walks the `from system_params import (...)` statements and asserts `STRATEGY_VERSION` is NOT among the imported names AND there is no bare `import system_params` (which would expose `STRATEGY_VERSION` via attribute access). Sharper guard than the planned grep.
- **Files modified:** `tests/test_dashboard.py`.
- **Verification:** New AST test passes; the existing `from system_params import (palette + contract specs)` line at dashboard.py:82 is preserved untouched.
- **Committed in:** `a1039bf` (Task 4 commit).

**3. [Rule 3 - Blocking] Added `import logging` + module-level `logger` to state_manager.py**
- **Found during:** Task 2 (writing the D-06 defensive-read helper).
- **Issue:** Plan specified `logger.warning('[State] WARN ...')` for the D-06 defensive-read but state_manager.py had NO logger — it used `print(..., file=sys.stderr)` for the existing `_backup_corrupt` warning. The new tests use `caplog` which requires a logger.
- **Fix:** Added `import logging` (stdlib) and `logger = logging.getLogger(__name__)` to state_manager.py. `logging` is NOT on `FORBIDDEN_MODULES_STATE_MANAGER`; the forbidden-imports guard remains green.
- **Files modified:** `state_manager.py`.
- **Verification:** `pytest tests/test_signal_engine.py::TestDeterminism::test_state_manager_no_forbidden_imports` passes.
- **Committed in:** `d56f7c3` (Task 2 commit).

**4. [Rule 3 - Blocking] Backfilled `strategy_version='v1.2.0'` on `tests/fixtures/dashboard/sample_state.json`**
- **Found during:** Task 4 (regenerating the populated-render golden).
- **Issue:** Plan called for the populated-render golden to show the active strategy version. The committed sample_state.json fixture had no `strategy_version` field on its signal rows, so the rendered footer would default to `'v1.0.0'` (D-06 fallback) rather than reflecting the operator's intent.
- **Fix:** Backfilled `strategy_version='v1.2.0'` on both dict-shaped rows in `sample_state.json`, then ran `tests/regenerate_dashboard_golden.py`. Empty-state fixture (`empty_state.json`) uses int-shape signals (`{SPI200: 0, AUDUSD: 0}`), so its golden naturally renders the D-06 default `'v1.0.0'` — that branch is now covered by the regenerated `golden_empty.html`.
- **Files modified:** `tests/fixtures/dashboard/sample_state.json`, `tests/fixtures/dashboard/golden.html`, `tests/fixtures/dashboard/golden_empty.html`.
- **Verification:** `pytest tests/test_dashboard.py::TestGoldenSnapshot tests/test_dashboard.py::TestEmptyState` passes.
- **Committed in:** `a1039bf` (Task 4 commit).

---

**Total deviations:** 4 auto-fixed (2 plan-bug, 2 blocking)
**Impact on plan:** All four are mechanical follow-ons to the planned changes; no scope creep, no new functionality. Plan was correct in intent; these polish the test seams the planner couldn't see without reading the existing test/fixture surface.

## Issues Encountered

- 12 pre-existing test failures in `tests/test_nginx_signals_conf.py` (6), `tests/test_notifier.py` (2), `tests/test_setup_https_doc.py` (1), and a couple of nginx-conf forbidden-pattern checks — UNRELATED to Phase 22. Reproduced on `git stash`-applied baseline (no Phase 22 edits) so confirmed pre-existing rot. The `nginx_signals_conf` tests look for placeholder `<owned-domain>.com` in the conf file but the project has hardcoded `signals.mwiriadi.me` (likely tracked as a separate todo). The `test_ruff_clean_notifier` failures are `FileNotFoundError` on the `ruff` binary — venv config concern. Logged as out-of-scope; NOT fixed.

## Verification Matrix Results

All six checks from CONTEXT.md §Verification (and the plan's `<verification>` block) pass:

1. `python3 -c "import system_params; print(system_params.STRATEGY_VERSION)"` → `v1.2.0` ✓
2. `python3 -c "import system_params; print(system_params.STATE_SCHEMA_VERSION)"` → `4` ✓
3. Synthetic v3 state.json with dict-shaped signal rows → `state_manager.load_state` returns `schema_version=4` and stamps both rows with `strategy_version='v1.1.0'` ✓ (verified via inline Python in this session).
4. `cat docs/STRATEGY-CHANGELOG.md | grep -c '^## v'` → `3` ✓
5. `pytest tests/test_state_manager.py tests/test_main.py tests/test_dashboard.py tests/test_system_params.py tests/test_strategy_changelog.py tests/test_signal_engine.py::TestDeterminism -q` → `371 passed` ✓
6. `python3` AST check that `dashboard.py` does NOT import `STRATEGY_VERSION` from `system_params` → confirmed (imported names are palette + contract specs only) ✓

## Out-of-scope Deferred (per D-07)

VERSION-03 (paper-trade `strategy_version` tag) is the contract this plan EXPOSES; Phase 19 (LEDGER) consumes it from day one. When Phase 19 lands, its plan must:
- `import system_params` at the top of the paper_trades writer module
- Tag every `state.paper_trades` row at write-time with `'strategy_version': system_params.STRATEGY_VERSION` via the same fresh-attribute-access pattern used in main.py:1280 (per LEARNINGS 2026-04-29 kwarg-default trap).

## Next Phase Readiness

- Versioning surface ready for Phase 19 (LEDGER) to consume: `system_params.STRATEGY_VERSION` import, `docs/STRATEGY-CHANGELOG.md` lineage anchor, `_read_signal_strategy_version` defensive-read helper available for cross-row reads.
- No blockers for Phase 23 / future signal-logic changes — bump `STRATEGY_VERSION` in `system_params.py` AND append a section to `STRATEGY-CHANGELOG.md` per D-03.
- Operator visibility: every dashboard render now shows the active strategy version in the footer; every signal row written from this commit forward carries the tag; the v3->v4 migration backfills existing droplet state on first deploy with `'v1.1.0'`.

## Self-Check: PASSED

All 8 files modified/created exist on disk; all 5 task commit hashes (`7b6f6a3`, `d56f7c3`, `135450f`, `a1039bf`, `3b6b5ac`) found in `git log --oneline --all`.

---
*Phase: 22-strategy-versioning-audit-trail*
*Completed: 2026-04-30*
