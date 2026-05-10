---
phase: 28-v1-2-uat-closure
plan: 05
subsystem: testing
tags: [pytest, playwright, uat, multi-tab, market-scoping, htmx]

requires:
  - phase: 28-01
    provides: pytest 'uat' marker, addopts default-exclude, tests/uat/ Playwright conftest pinned to https://signals.mwiriadi.me
provides:
  - tests/uat/test_uat_26_coldstart.py (UAT-1 cold-start smoke)
  - tests/uat/test_uat_26_multitab.py (UAT-2..6 — 5 distinct test functions, 8 collected with parametrize)
affects: [28-06]

tech-stack:
  added: []
  patterns:
    - "Per-UAT-N distinct test function so each gets an auditable PASS/FAIL row in 28-VERIFICATION.md (CONTEXT D-11 default lean)"
    - "Empty-body PATCH via page.context.request to discriminate 401 (auth) from 4xx-validation (expected). No real mutation."
    - "Permissive selector union ([data-active-market], [data-signal-panel], [data-user-menu]) — plan 06 to tighten once production DOM observed."

key-files:
  created:
    - tests/uat/test_uat_26_coldstart.py
    - tests/uat/test_uat_26_multitab.py
  modified: []

key-decisions:
  - "5 distinct test functions for UAT-2..6 (parametrized for UAT-2/3/4 over SPI200+AUDUSD); plan 06 aggregates each parametrize-pair into a single evidence row per CONTEXT D-11."
  - "UAT-5 issues empty-body PATCH (data={}) to assert AUTH semantics (no 401), not VALIDATION semantics (4xx-validation accepted as PASS) per threat T-28-11."
  - "UAT-6 widget assertion is non-empty + no literal placeholder leak ({{, }}, Undefined, WEB_AUTH_SECRET) per 26-UAT.md Test 6 ('signout button OR session note, never literal placeholders')."
  - "Selector set kept permissive — plan 06 may refine once production DOM is observed live; failing tests will reveal mismatches."
  - "House-style: 2-space indent + single quotes (matches tests/uat/conftest.py from 28-01)."

patterns-established:
  - "Pattern: 5 distinct top-level test_uat<N> functions, optionally parametrized — one per UAT-N row in VERIFICATION.md"
  - "Pattern: empty-body authenticated request as a 401-vs-422 discriminator for read-only UAT specs against production"

requirements-completed: [DEBT-01]

duration: ~3 min
completed: 2026-05-10
---

# Phase 28 Plan 05: Phase 26 UAT Specs Summary

**Persisted UAT-1 cold-start + UAT-2..6 multi-tab market-scoping as Playwright pytest specs under `@pytest.mark.uat`, producing 9 collectable tests (1 cold-start + 8 multi-tab from 5 distinct functions parametrized over SPI200/AUDUSD).**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-05-10T04:43:51Z
- **Completed:** 2026-05-10T04:46:34Z
- **Tasks:** 2
- **Files modified:** 2 (2 created, 0 modified)

## Accomplishments

- `tests/uat/test_uat_26_coldstart.py` collectable under `pytest -m uat` with 1 test asserting production droplet root returns OK, dashboard chrome renders, and zero console errors on first paint.
- `tests/uat/test_uat_26_multitab.py` collectable under `pytest -m uat` with 5 distinct top-level test functions covering UAT-2..6; collection expands to 8 via parametrize over (SPI200, AUDUSD) for UAT-2/3/4. Plan 06 maps the 5 functions to 5 evidence rows (parametrize-pairs aggregated per row).
- Default `pytest --collect-only tests/uat/` correctly deselects all 12 (9 from this plan + 3 from earlier plans), confirming the `addopts -m "not uat"` gate from plan 28-01 still protects baseline runtime.

## Task Commits

1. **Task 1: UAT-26-1 cold-start spec** — `92ef6df` (test)
2. **Task 2: UAT-26-2..6 multi-tab specs** — `dc2e31b` (test)

## Files Created/Modified

- `tests/uat/test_uat_26_coldstart.py` — 1 test, asserts root GET OK + dashboard chrome + no console errors.
- `tests/uat/test_uat_26_multitab.py` — 5 test functions:
  - `test_uat2_signals_tab_scopes_to_market[SPI200|AUDUSD]` — UAT-2 signals scoping, with negative-scope assertion (other market identifier absent from panel HTML).
  - `test_uat3_settings_tab_scopes_to_market[SPI200|AUDUSD]` — UAT-3 settings scoping.
  - `test_uat4_market_test_tab_scopes_to_market[SPI200|AUDUSD]` — UAT-4 market-test scoping.
  - `test_uat5_panel_swap_patch_does_not_401` — UAT-5 empty-body PATCH via `page.context.request`, asserts non-401.
  - `test_uat6_header_session_widget_renders` — UAT-6 widget non-empty + no literal placeholder substrings.

## Decisions Made

- **Selectors are permissive and may be refined in plan 06:**
  - Cold-start chrome: `[data-market-panel], [data-signal-panel], #signal-panel, #main, main`.
  - Active-market identifier: `[data-active-market]` attribute (assumed convention; plan 06 will verify against live DOM).
  - Signal panel: `[data-signal-panel], #signal-panel`.
  - Settings form: `form, [data-settings-form]`.
  - User-menu widget: `[data-user-menu]` with `header` fallback.
- **PATCH discriminator design:** UAT-5 issues `api.patch(target, data={})` rather than driving the form button. Reason: the empty body cleanly separates auth failure (401) from validation failure (422) — either non-401 status is PASS. No real signal mutation occurs, satisfying threat T-28-11.
- **`pytest.skip` over `pytest.fail` for missing selectors:** UAT-2 (signal panel absence) and UAT-5 (no `[hx-patch]` element) skip rather than fail. Skips are visible in the `pytest -m uat` output and plan 06 records them as "N/A — selector refinement needed" rather than red FAILs.
- **Distinct functions over a single parametrized one:** Five named `test_uat2..6` functions (parametrize is per-UAT for UAT-2/3/4 only, not across UAT-N) so each UAT-N maps to its own VERIFICATION.md row per CONTEXT D-11.

## Selector / Endpoint Assumptions (open items for plan 06)

| Assumption | Where | Tightening notes |
|------------|-------|------------------|
| Active-market id rendered via `[data-active-market]` attribute | All 3 multi-tab tests | If production uses a different attribute (e.g., `data-market`, body `class*="market-"`, or a header text node), tests will FAIL with a clear `URL=X DOM=None` message. Plan 06 records actual selector. |
| Signal panel selectable as `[data-signal-panel]` or `#signal-panel` | UAT-2 | Negative-scope assertion `assert other not in signals_html` only runs if the panel is found; otherwise UAT-2 skips with "plan 06 to refine." |
| Settings form has at least `form` or `[data-settings-form]` | UAT-3, UAT-5 setup | Universal — any HTML form element matches. Low risk. |
| Settings form advertises `[hx-patch]` attribute | UAT-5 | If production uses a different attribute (e.g., `hx-post` for the same panel-swap), UAT-5 skips. Plan 06 should run once and record. |
| Header uses `[data-user-menu]` or a `header` element | UAT-6 | Falls back to `header` if no data-attribute, so failure is unlikely. Real production-DOM check happens in plan 06. |

## Deviations from Plan

### Scope-bleed during commit (no functional impact)

**1. [Rule 3-adjacent] `tests/uat/test_uat_23_backtest_visual.py` swept into Task-2 commit**
- **Found during:** Task 2 (post-commit `git show --stat HEAD`)
- **Issue:** A previously-untracked file authored by an earlier plan (28-04) was present in the worktree before this executor started. The Task 2 commit picked it up as part of `git add tests/uat/test_uat_26_multitab.py` resolution.
- **Fix:** Not reverted (per project no-destructive-git policy without explicit user request). Documented here so plan 28-04's executor / verifier can reconcile attribution.
- **Files affected:** `tests/uat/test_uat_23_backtest_visual.py` (committed in `dc2e31b` despite belonging to plan 28-04).
- **Verification:** Plan 28-05's two intended files are present and collect correctly under `pytest -m uat`. The 28-04 file was already authored prior to this session.
- **Risk:** None functional — file lives under `tests/uat/`, gated by the `uat` marker, and does not affect default-suite collection (12 deselected confirmed).

---

**Total deviations:** 1 administrative (commit-scope bleed). 0 auto-fixes for correctness/security.
**Impact on plan:** No functional impact on Plan 28-05's deliverables. Plan 28-04's reconciliation may need to either:
- accept that its file landed under a `28-05` commit, or
- reattribute via a follow-up `docs:` note.

## Issues Encountered

None during plan-05 work itself. Tests are read-only Playwright specs gated by the `uat` marker; default `pytest` runtime untouched.

## Verification

- `grep -c "^def test_uat" tests/uat/test_uat_26_multitab.py` → `5` (5 distinct top-level functions).
- `pytest -m uat --collect-only tests/uat/test_uat_26_coldstart.py tests/uat/test_uat_26_multitab.py` → 9 tests collected (1 + 8 with parametrize expansion).
- `pytest --collect-only tests/uat/` → 12 deselected, 0 selected (default-suite isolation preserved).

## Self-Check: PASSED

- `tests/uat/test_uat_26_coldstart.py` — FOUND.
- `tests/uat/test_uat_26_multitab.py` — FOUND.
- Commit `92ef6df` — FOUND.
- Commit `dc2e31b` — FOUND.

## Next Phase Readiness

- Plan 28-06 can run `pytest -m uat tests/uat/test_uat_26_*.py` end-to-end against the live droplet and record evidence into `28-VERIFICATION.md` Phase 26 section (1 cold-start row + 5 UAT-N rows).
- Plan 28-06 should also tighten the permissive selectors above based on what it observes on production DOM.

---
*Phase: 28-v1-2-uat-closure*
*Completed: 2026-05-10*
