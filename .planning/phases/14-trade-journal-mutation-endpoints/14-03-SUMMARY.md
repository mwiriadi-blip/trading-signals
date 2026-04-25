---
phase: 14-trade-journal-mutation-endpoints
plan: 03
subsystem: sizing-engine
tags: [phase14, sizing-engine, manual-stop, pure-math, hex-lite, d-09, d-15, tdd]

# Dependency graph
requires:
  - phase: 14-trade-journal-mutation-endpoints
    plan: 01
    provides: 'TestManualStopOverride skeleton + _make_position helper baseline'
  - phase: 14-trade-journal-mutation-endpoints
    plan: 02
    provides: 'system_params.Position.manual_stop: float | None field; STATE_SCHEMA_VERSION=3; _migrate_v2_to_v3 backfill on load'
provides:
  - 'sizing_engine.get_trailing_stop honors position[manual_stop] override (D-09): returns operator-set value when not None; falls through to v1.0 computed peak/trough trailing stop when None or absent'
  - 'Defensive .get(manual_stop) handles pre-migration position dicts (no key) without KeyError — mitigates T-14-07'
  - 'NaN-passthrough invariant (B-1) preserved: NaN atr_entry returns float(nan) BEFORE manual_stop branch'
  - 'check_stop_hit docstring documents Phase 14 D-15 boundary: manual_stop intentionally NOT honored in daily-loop hit detection (Phase 15 deferred)'
  - 'TestManualStopOverride: 5 tests covering LONG override, SHORT override, None fallback, NaN guard precedence, and pre-migration missing-key path'
affects: [14-04, 14-05]

# Tech tracking
tech-stack:
  added: []  # no new dependencies; 4-line addition to existing pure-math hex
  patterns:
    - 'Override-precedence pattern in pure-math hex: NaN guard FIRST, override branch SECOND, computed branch THIRD — locks ordering invariant via test class with explicit precedence-table docstring'
    - 'Defensive .get() over subscript when reading new TypedDict fields during migration windows: protects against transient calls on pre-migration data even when migration normally backfills the field'
    - 'Documentation-only edits to functions intentionally NOT participating in a precedence change: docstring records the deliberate boundary so future readers don''t "fix" the asymmetry by accident (D-15)'

key-files:
  created: []
  modified:
    - 'sizing_engine.py — get_trailing_stop gains 4-line manual_stop branch (between NaN guard and LONG/SHORT switch); docstring extended with D-09 paragraph; check_stop_hit docstring extended with D-15 non-honoring note (658 -> 685 lines, +27)'
    - 'tests/test_sizing_engine.py — _make_position helper extends with manual_stop=None kwarg + body assignment; TestManualStopOverride placeholder skip replaced with 5 populated tests; class docstring rewritten with explicit precedence ordering (1203 -> 1286 lines, +83)'

key-decisions:
  - 'Position the manual_stop branch AFTER B-1 NaN guard (atr_entry NaN -> float(nan)) and BEFORE the LONG/SHORT direction switch. Order locked by test_manual_stop_with_nan_atr_entry_returns_nan: NaN passthrough takes precedence over override.'
  - 'Use position.get(''manual_stop'') (not subscript) for backward-compat with pre-migration position dicts. Plan 14-02 migration backfills None on load, but defensive .get protects transient pre-migration calls. Mitigates T-14-07.'
  - 'Phase 14 D-15: check_stop_hit (daily-loop exit detection) intentionally does NOT honor manual_stop. Display-only scope per plan; Phase 15 candidate to align. Documented in check_stop_hit docstring so future readers do not "fix" the asymmetry by adding a parallel branch.'
  - '_make_position helper kwarg added at the END of the keyword-arg list (manual_stop=None) — backward-compat for all 88 existing _make_position call sites. Default None preserves v1.0 behavior in TestExits / TestPyramid / TestTransitions / TestEdgeCases / TestStep.'
  - 'TestManualStopOverride uses 5 tests not 6: short test picks manual_stop=7950.0 (NOT 7900.0 which equals computed) so the SHORT override path test cannot be satisfied by a coincidental numeric collision with the trough+trail computation.'

patterns-established:
  - 'Pure-math precedence-chain extension via insert-only edit: identify the existing chain anchor (NaN guard), insert new branch after the anchor and before the next branch, never reorder existing logic. Preserves diff readability and confines blast radius.'
  - 'Documentation-only docstring edit on a sibling function (check_stop_hit) to record a deliberate non-participation boundary: paired with the precedence-introducing edit on get_trailing_stop, the docstring on check_stop_hit explicitly cites the parent decision (D-15) so readers see the asymmetry was intentional.'

requirements-completed: [TRADE-04]

# Metrics
duration: 4m31s
completed: 2026-04-25
---

# Phase 14 Plan 03: sizing_engine.get_trailing_stop manual_stop precedence Summary

**`sizing_engine.get_trailing_stop` now honors operator-set `position['manual_stop']` (Phase 14 D-09): returns the override directly when not None; falls through to the v1.0 peak/trough computed trailing stop when None or absent. Pure-math hex boundary preserved; B-1 NaN passthrough preserved; pre-migration missing-key positions handled defensively.**

## Performance

- **Duration:** 4m31s
- **Started:** 2026-04-25T10:01:53Z
- **Completed:** 2026-04-25T10:06:24Z
- **Tasks:** 1 (single-task plan per revision)
- **Files modified:** 2
- **Files created:** 0

## Accomplishments

- **D-09 precedence locked end-to-end.** `sizing_engine.get_trailing_stop` reads `position.get('manual_stop')` AFTER the NaN guard and BEFORE the LONG/SHORT direction switch. When the value is not None, the function returns it verbatim — no peak/trough math, no ATR multiple, no rounding. When None (the v1.0 default backfilled by Plan 14-02's `_migrate_v2_to_v3`), the function falls through to the existing computed trailing stop and v1.0 behavior is preserved bit-exact.
- **TestManualStopOverride populated with 5 tests** (replacing the Plan 14-01 single skip placeholder):
  - `test_manual_stop_overrides_long_computed` — LONG with `manual_stop=7700.0` returns 7700.0 (computed peak-trail would be 7950.0)
  - `test_manual_stop_overrides_short_computed` — SHORT with `manual_stop=7950.0` returns 7950.0 (computed trough+trail would be 7900.0; deliberately picks a non-equal value to prove the override path is exercised, not a coincidental match)
  - `test_manual_stop_none_falls_back_to_computed` — `manual_stop=None` produces the v1.0 7950.0 computed stop
  - `test_manual_stop_with_nan_atr_entry_returns_nan` — NaN `atr_entry` returns `float('nan')` even when `manual_stop=7700.0` is set, locking the NaN-guard-FIRST precedence
  - `test_manual_stop_via_get_with_missing_key_falls_back_to_computed` — bare-dict position WITHOUT the `manual_stop` key falls through to computed via `position.get(...)` returning None default
- **D-15 boundary documented in check_stop_hit.** The daily-loop hit detection (`check_stop_hit`) intentionally does NOT honor `manual_stop`. The function body is unchanged in this plan; only its docstring is extended with the Phase 14 D-15 (REVIEWS MEDIUM #6) note explaining the asymmetry and citing the Phase 15 deferred-alignment candidate. This prevents future readers from "fixing" the asymmetry by adding a parallel branch by mistake.
- **Hex-lite invariant preserved.** AST guard verified: `sizing_engine.py` still imports only stdlib (`dataclasses`, `math`) + `signal_engine` (LONG/SHORT/FLAT) + `system_params` (constants + Position). No new imports of `os`, `datetime`, `state_manager`, `notifier`, `dashboard`, `main`, or `requests`.

## Task Commits

Each task was committed atomically:

1. **Task 1: sizing_engine.get_trailing_stop manual_stop precedence + TestManualStopOverride populated** — `8fd6d04` (feat)

## The exact 4-line manual_stop branch position in get_trailing_stop

```python
def get_trailing_stop(
  position: Position,
  current_price: float,
  atr: float,
) -> float:
  '''... (docstring extended with Phase 14 D-09 paragraph) ...'''
  del current_price  # Reserved; not used in trail-stop math (D-16).
  del atr  # D-15: stop distance uses position['atr_entry'] not this parameter.
  atr_entry = position['atr_entry']
  if not math.isfinite(atr_entry):
    return float('nan')  # B-1: NaN-pass-through
  # Phase 14 D-09: manual_stop takes precedence over computed trailing stop.
  # When operator has set a stop via /trades/modify, return it directly.
  # When None (default), fall through to v1.0 computed trailing stop.
  # Defensive .get() handles pre-migration position dicts (no key) — RESEARCH Pitfall 5.
  manual = position.get('manual_stop')
  if manual is not None:
    return manual
  if position['direction'] == 'LONG':
    peak = position['peak_price']
    if peak is None:
      peak = position['entry_price']
    return peak - TRAIL_MULT_LONG * atr_entry
  # SHORT branch
  trough = position['trough_price']
  if trough is None:
    trough = position['entry_price']
  return trough + TRAIL_MULT_SHORT * atr_entry
```

The 4 lines (`manual = ...; if manual is not None: return manual`) sit BETWEEN the B-1 NaN guard at line 230 and the LONG branch at line 235 (post-edit line numbers). This position locks the precedence: NaN > manual_stop > computed.

## TestManualStopOverride structure (5 tests covering 4 scenarios + backward-compat)

| Test | Direction | manual_stop | atr_entry | Expected | Asserts |
|------|-----------|-------------|-----------|----------|---------|
| test_manual_stop_overrides_long_computed | LONG | 7700.0 | 50.0 | 7700.0 | LONG override path |
| test_manual_stop_overrides_short_computed | SHORT | 7950.0 (NOT 7900.0) | 50.0 | 7950.0 | SHORT override path; deliberate non-collision with computed |
| test_manual_stop_none_falls_back_to_computed | LONG | None | 50.0 | 7950.0 | v1.0 fallback path |
| test_manual_stop_with_nan_atr_entry_returns_nan | LONG | 7700.0 | NaN | NaN | B-1 precedence > override |
| test_manual_stop_via_get_with_missing_key_falls_back_to_computed | LONG | (key absent) | 50.0 | 7950.0 | Defensive .get() (T-14-07 mitigation) |

All 5 tests green; existing TestExits (14 tests) still green via backward-compatible default `manual_stop=None` in `_make_position`.

## check_stop_hit docstring carries the Phase 14 non-honoring note

```python
def check_stop_hit(
  position: Position, high: float, low: float, atr: float,
) -> bool:
  '''EXIT-08/09: True if today's intraday bar hit the trailing stop.
  ...
  B-1 NaN policy: ...

  Phase 14 D-15 (REVIEWS MEDIUM #6) — manual_stop NOT honored here, intentionally:
    get_trailing_stop honors position['manual_stop'] (D-09) for display
    and operator-facing reporting. check_stop_hit is invoked by the daily
    signal loop (main.run_daily_check), which is OUT OF Phase 14 scope —
    the loop continues to use the v1.0 computed stop level for hit
    detection. Phase 15 candidate (deferred): align check_stop_hit with
    manual_stop so dashboard and exit-detection no longer diverge. ...
  ...
  '''
  # body UNCHANGED — only the docstring is extended in this plan
```

`grep -q "manual_stop NOT honored here, intentionally" sizing_engine.py` exits 0. The function body is byte-identical to pre-Plan-14-03; only its docstring is extended.

## Test counts (full sizing_engine.py suite)

```bash
$ pytest tests/test_sizing_engine.py --tb=no -q
133 passed in 0.27s
```

**Delta vs pre-Plan-14-03 baseline (128 passed + 1 skipped placeholder = 129 collected):**
- +5 TestManualStopOverride methods (was: 1 skip placeholder)
- 0 skip placeholders remain (Plan 14-01 skeleton fully replaced)
- 133 - 128 = 5 ✓

## Smoke checks (all 4 acceptance smoke commands pass)

```bash
# 1. Override path
$ python -c "from sizing_engine import get_trailing_stop; from system_params import Position; pos = Position(direction='LONG', entry_price=7000.0, entry_date='2026-04-15', n_contracts=2, pyramid_level=0, peak_price=8100.0, trough_price=None, atr_entry=50.0, manual_stop=7700.0); assert get_trailing_stop(pos, 8050.0, 50.0) == 7700.0"
# OK

# 2. None falls through to computed
$ python -c "from sizing_engine import get_trailing_stop; from system_params import Position; pos = Position(direction='LONG', entry_price=7000.0, entry_date='2026-04-15', n_contracts=2, pyramid_level=0, peak_price=8100.0, trough_price=None, atr_entry=50.0, manual_stop=None); assert get_trailing_stop(pos, 8050.0, 50.0) == 7950.0"
# OK

# 3. NaN guard precedence over override
$ python -c "from sizing_engine import get_trailing_stop; import math; pos = {'direction': 'LONG', ..., 'atr_entry': float('nan'), 'manual_stop': 7700.0}; assert math.isnan(get_trailing_stop(pos, 8050.0, 50.0))"
# OK

# 4. Missing-key defensive .get path
$ python -c "from sizing_engine import get_trailing_stop; pos = {'direction': 'LONG', ..., 'atr_entry': 50.0}  # no manual_stop key; assert get_trailing_stop(pos, 8050.0, 50.0) == 7950.0"
# OK
```

## Hex-lite AST guard (forbidden imports check)

```bash
$ python -c "import ast; tree = ast.parse(open('sizing_engine.py').read()); forbidden = {'os', 'datetime', 'state_manager', 'notifier', 'dashboard', 'main', 'requests'}; bad = [...]; assert not bad, bad"
# OK
```

`sizing_engine.py` imports only `dataclasses`, `math`, `signal_engine` (LONG/SHORT/FLAT), `system_params` (constants + Position). The 4-line manual_stop branch added zero new module imports — `position.get(...)` is a dict method, no module dependency.

## Cross-suite cooperation (Plan 14-02 + Plan 14-03)

```bash
$ pytest tests/test_state_manager.py tests/test_sizing_engine.py -x -q
215 passed in 1.06s
```

The Plan 14-02 schema migration (Position.manual_stop=None backfill on load) and the Plan 14-03 consumer (`get_trailing_stop` reads `position.get('manual_stop')`) cooperate cleanly: 82 state_manager tests + 133 sizing_engine tests all green, no overlap failures.

## Full suite delta vs baseline

| Metric | Pre-Plan-14-03 | Post-Plan-14-03 | Delta |
|--------|----------------|-----------------|-------|
| Passed | 896 | 901 | +5 |
| Failed | 16 (test_main weekend-skip pre-existing) | 16 (same set) | 0 |
| Skipped | 4 | 3 | -1 (placeholder replaced) |

Net delta: +5 new tests pass, 0 new failures, 1 placeholder eliminated. The 16 weekend-skip failures in `tests/test_main.py` are pre-existing baseline (documented in Plan 14-02 SUMMARY § Issues Encountered — today is Saturday 2026-04-25; same test set fails on the parent commit `1f3c4bc`).

The web tests (`tests/test_web_*.py`) ERROR at collection due to missing `fastapi` — pre-existing baseline; out of scope for Plan 14-03.

## Files Modified

**Modified:**
- `sizing_engine.py` — get_trailing_stop manual_stop branch + docstring D-09 paragraph; check_stop_hit docstring D-15 note (658 -> 685 lines, +27)
- `tests/test_sizing_engine.py` — _make_position kwarg extension; TestManualStopOverride 5 tests populated; class docstring rewritten (1203 -> 1286 lines, +83)

## Decisions Made

- **Branch insertion point: AFTER NaN guard, BEFORE direction switch.** Locked by `test_manual_stop_with_nan_atr_entry_returns_nan`. Rationale: a broken-upstream `atr_entry=NaN` should propagate NaN to the caller (B-1 invariant) regardless of operator override — the override is interpreted as "use this stop level", but if the position's atr_entry is NaN, the entire stop computation is fundamentally compromised, and surfacing NaN forces the orchestrator to skip the stop check rather than use a stale operator-set value. The `manual` short-circuit happens after this guard.
- **Defensive `position.get('manual_stop')` over subscript `position['manual_stop']`.** Plan 14-02's `_migrate_v2_to_v3` backfills `manual_stop=None` on every Position dict at load time, so under normal operation the key is always present. However, defensive `.get()` protects against transient calls during migration (e.g., a test fixture that constructs a bare dict, or a future bug where migration is skipped). Mitigates T-14-07 (E: pre-migration KeyError crash). The cost is one extra lookup branch (Python dict `.get` vs `__getitem__`); negligible.
- **check_stop_hit body UNCHANGED — only docstring extended with D-15 note.** The plan revision explicitly scoped manual_stop as display-only in Phase 14. Adding a parallel branch in `check_stop_hit` would broaden the scope to behavioral consistency between dashboard display and daily-loop exit detection — that's a Phase 15 candidate per CONTEXT D-15. The docstring note records the deliberate boundary so future readers don't add the branch by mistake.
- **SHORT test value picked deliberately to avoid coincidental match.** `test_manual_stop_overrides_short_computed` uses `manual_stop=7950.0` (NOT 7900.0 which equals trough+trail at trough=7800, atr=50). This makes the test's invariant "override-not-computed" rather than "value-equals-coincidence". A test that asserted `manual_stop=7900.0 -> 7900.0` would PASS even if the override branch was deleted (the computed branch would coincidentally produce 7900.0 too).
- **_make_position kwarg added at END of the kwarg list.** Preserves all 88 existing call sites' positional + keyword call shapes without any test code changes. Default `None` makes the new kwarg invisible to v1.0 tests; existing TestExits / TestPyramid / TestTransitions / TestEdgeCases / TestStep behave exactly as before.

## Deviations from Plan

None — plan executed exactly as written.

The plan's `<action>` block specified:
1. Insert 4-line manual_stop branch in get_trailing_stop (between NaN guard and direction switch) ✓
2. Add Phase 14 D-09 paragraph to get_trailing_stop docstring ✓
3. Add Phase 14 D-15 non-honoring note to check_stop_hit docstring ✓
4. Extend _make_position with manual_stop=None kwarg ✓
5. Replace TestManualStopOverride skeleton with 5 tests ✓

All 5 production sub-edits + all 5 test additions landed exactly as specified. No Rule 1/2/3 auto-fixes triggered. No Rule 4 architectural questions raised. Hex-lite preserved; backward compat verified (TestExits 14 tests still green); cross-plan cooperation verified (test_state_manager + test_sizing_engine 215 tests green together).

## Issues Encountered

- **Pre-existing baseline failures unchanged.** `tests/test_main.py` continues to show 16 failures (weekend-skip baseline; today is Saturday 2026-04-25). Out of Plan 14-03 scope; documented in Plan 14-02 SUMMARY.
- **Web test collection errors unchanged.** `tests/test_web_*.py` continue to ERROR on missing `fastapi` (pre-existing; verified by `git stash` reproduction on the parent commit `1f3c4bc`). Out of Plan 14-03 scope; will be resolved by Plan 14-04 + 14-05 dependencies.

## TDD Gate Compliance

This plan's frontmatter is `type: execute` with the single task tagged `tdd="true"`. The TDD discipline was followed in two phases inside the single commit:

1. **RED:** Populated `TestManualStopOverride` with 5 real tests + extended `_make_position` helper. Tests fail because `get_trailing_stop` lacks the manual_stop branch:
   ```bash
   $ pytest tests/test_sizing_engine.py::TestManualStopOverride -x -q
   FAILED ... AssertionError: D-09: LONG with manual_stop=7700.0 must return 7700.0 directly; got 7950.0
   ```
2. **GREEN:** Added the 4-line manual_stop branch in `get_trailing_stop` + the docstring updates. Tests pass:
   ```bash
   $ pytest tests/test_sizing_engine.py::TestManualStopOverride -x -q
   5 passed
   ```
3. **REFACTOR:** No refactor needed — the insert-only edit kept the existing precedence chain intact.

The RED + GREEN phases were combined into a single atomic commit (`8fd6d04`) per the plan's single-task-per-plan structure. The git log shows one `feat(14-03)` commit; no separate `test(14-03)` precursor commit exists. This is acceptable for a 4-line production change paired with the test class population — splitting would have required a `test(14-03)` commit that intentionally fails CI, which is structurally inconsistent with `commit_docs: true` workflow expectations.

## User Setup Required

None — Plan 14-03 is internal sizing_engine + tests. No environment variables, no external services, no migration steps.

## Self-Check

**Files exist:**
- FOUND: sizing_engine.py (modified — get_trailing_stop manual_stop branch + docstring; check_stop_hit docstring D-15 note)
- FOUND: tests/test_sizing_engine.py (modified — _make_position kwarg; TestManualStopOverride 5 tests populated)
- FOUND: .planning/phases/14-trade-journal-mutation-endpoints/14-03-SUMMARY.md (this file)

**Commits exist:**
- FOUND: 8fd6d04 (Task 1)

## Self-Check: PASSED

## Next Phase Readiness

Plan 14-04 (web/routes/trades.py POST endpoints — `/trades/open`, `/trades/close`, `/trades/modify`) can now spawn. Its dependency surface is satisfied:

- `sizing_engine.get_trailing_stop` honors `manual_stop` overrides (D-09 — operator-set stops via POST `/trades/modify` are now reflected in the stop value the dashboard renders).
- `state_manager.mutate_state` (Plan 14-02) is the canonical write API for all three POST handlers — full READ-MODIFY-WRITE atomicity under fcntl.LOCK_EX (REVIEWS HIGH #1 closed).
- `system_params.Position.manual_stop` field exists (Plan 14-02) — `/trades/modify` writes `state['positions'][instrument]['manual_stop'] = req.new_stop`.

Plan 14-05 (dashboard manual_stop badge + HTMX form rendering) inherits the precedence pattern: `dashboard.py::_compute_trail_stop_display` MUST replicate the EXACT `manual = position.get('manual_stop'); if manual is not None: return manual` block introduced here. The lockstep parity test (Plan 14-05 owned) will compare both functions' outputs side-by-side on a battery of position fixtures.

Phase 15 candidate: align `check_stop_hit` with `manual_stop` so the daily loop's exit detection also honors operator overrides (closes the dashboard-vs-loop divergence documented in D-15 + the new check_stop_hit docstring note). Out of Phase 14 scope.

No blockers, no concerns.

---
*Phase: 14-trade-journal-mutation-endpoints*
*Plan: 03*
*Completed: 2026-04-25*
