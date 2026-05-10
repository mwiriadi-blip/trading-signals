---
phase: 22
phase_name: Strategy versioning & audit trail
milestone: v1.2
created: 2026-04-30
status: locked
requirements: [VERSION-01, VERSION-02, VERSION-03]
source: SPEC.md §v1.2+ Long-Term Roadmap (operator brainstorm 2026-04-29) + ROADMAP.md v1.2 Phase 22 Success Criteria
---

# Phase 22 — Strategy Versioning & Audit Trail (CONTEXT)

## Goal

Every signal output and paper trade row carries a `strategy_version` tag, so historical results stay interpretable when the signal logic changes (Mom periods, ADX gate cutoff, RVol period, sizing weights, vote rule). Closed trades retain the version they were entered under, even if `STRATEGY_VERSION` later bumps.

## Scope

**In:**
- `STRATEGY_VERSION = 'v1.2.0'` constant in `system_params.py`
- `state.signals[<instrument>].strategy_version` field on every write
- state.json migration v3 → v4 (backfill `strategy_version: 'v1.1.0'` on existing signal rows)
- `docs/STRATEGY-CHANGELOG.md` with v1.0.0 / v1.1.0 / v1.2.0 entries
- Defensive read: rows missing `strategy_version` default to `'v1.0.0'`

**Out (deferred to Phase 19 plan):**
- `state.paper_trades` schema doesn't exist yet (Phase 19 is Wave 2). Phase 19 plan will reference VERSION-01 and write `strategy_version` on every paper-trade entry from day one.

**Out (deferred to v1.3+):**
- Bumping `STRATEGY_VERSION` mid-milestone — first bump happens whenever the operator changes any signal-logic constant; v1.2 launches at `v1.2.0` with no logic change yet.

## Locked decisions

### D-01 — `STRATEGY_VERSION` location

Top of `system_params.py`, in a new `# Strategy version` section near the top of the file (before the Phase 1 indicator constants block at line 19), with a docstring explaining bump semantics.

### D-02 — Format

`STRATEGY_VERSION = 'v1.2.0'` — string with `v` prefix, semver `MAJOR.MINOR.PATCH`. Matches git tag convention (`v1.0`, `v1.1`). Operator can grep `STRATEGY_VERSION = 'v` to find every bump in git history.

### D-03 — Bump semantics

Bump on signal-logic change ONLY:
- Mom periods (`MOM_1`, `MOM_3`, `MOM_12`)
- ADX gate cutoff (`ADX_GATE_THRESHOLD`)
- RVol period (`RVOL_PERIOD`)
- Sizing weights (`POSITION_SIZE_PCT_LONG`, `POSITION_SIZE_PCT_SHORT`)
- Vote rule logic (currently 2-of-3)

Do NOT bump on:
- UI / dashboard changes
- Infra / hosting changes
- Email / notifier changes
- Auth / web layer changes
- Test changes
- Docs changes
- New deployment phases (e.g., adding multi-user, news, backtest)

Versioning style:
- **MAJOR** — breaking signal logic change (e.g. switching from 2-of-3 vote to 3-of-3 vote, or moving from ADX gate to a different filter)
- **MINOR** — adding/removing an indicator input (e.g. introducing a new momentum window)
- **PATCH** — tuning a numeric threshold (e.g. ADX gate 25 → 22)

### D-04 — state.json `schema_version` bump

3 → 4. Adds `strategy_version` field to `state.signals[<instrument>]`. Clean migration via `_migrate_v3_to_v4`.

### D-05 — Migration value for existing signal rows

`v1.1.0`. On first v1.2 deploy, the existing `state.signals` rows on the droplet were produced under v1.1 logic — which is the same signal logic as v1.0 plus the hosting change. Stamping `v1.1.0` is honest about the deployment history.

Migration code:
```python
def _migrate_v3_to_v4(s: dict) -> dict:
    """v3 → v4: backfill strategy_version on existing signal rows.

    Phase 22 (v1.2): adds strategy_version tag to state.signals[<inst>].
    Existing rows on first v1.2 deploy were produced under v1.1 logic
    (same signal logic as v1.0; hosting change only). Stamp 'v1.1.0'.
    """
    signals = s.get('signals', {})
    for inst_key, sig in signals.items():
        if isinstance(sig, dict) and 'strategy_version' not in sig:
            sig['strategy_version'] = 'v1.1.0'
    return s
```

### D-06 — Backwards-compat read

Any code reading `state.signals[<inst>].strategy_version` defaults to `'v1.0.0'` if the field is missing. Belt-and-suspenders: `_migrate_v3_to_v4` should backfill all existing rows on first v1.2 load, but defensive read prevents crashes if a row somehow lands without the field (e.g. concurrent write race, manual state.json edit).

```python
strategy_version = signal.get('strategy_version', 'v1.0.0')
```

### D-07 — paper_trades migration

NOT NEEDED in Phase 22. Phase 19 (LEDGER) hasn't shipped yet — `state.paper_trades` array doesn't exist on the droplet. When Phase 19 lands, its plan will write `strategy_version` from day one (read from `system_params.STRATEGY_VERSION`). Phase 22 has zero paper-trades concerns.

If Phase 19 ships before Phase 22 (it shouldn't per the wave order, but defensive design): Phase 19 plan should import `STRATEGY_VERSION` from `system_params`. If `STRATEGY_VERSION` doesn't exist yet (Phase 22 not landed), Phase 19 plan must FAIL the import at the planner step — surface as a deviation.

### D-08 — `STRATEGY-CHANGELOG.md` content

Three honest entries:

```markdown
# Strategy Changelog

Append-only record of signal-logic changes. Each entry documents the
constants present at that version. Bump `STRATEGY_VERSION` in
`system_params.py` on signal-logic changes only (see Phase 22 D-03).

## v1.2.0 — 2026-04-30 (no logic change)

Versioning system introduced. Signal logic unchanged from v1.1.0 / v1.0.0.

Constants at this version:
- ATR_PERIOD = 14
- ADX_PERIOD = 20
- ADX_GATE_THRESHOLD = 25
- MOM_PERIODS = [1, 3, 12]
- RVOL_PERIOD = 20
- VOTE_RULE = "2-of-3 momentum sign agreement"
- POSITION_SIZE_PCT_LONG = 0.01
- POSITION_SIZE_PCT_SHORT = 0.005
- TRAILING_STOP_ATR_MULTIPLIER = 3.0

## v1.1.0 — 2026-04-30 (no logic change)

Hosted dashboard + interactive trade journal + auth UX.
Signal logic unchanged from v1.0.0.

## v1.0.0 — 2026-04-24 (initial)

Original signal logic from v1.0 milestone (Phases 1-9).
ATR/ADX/Mom/RVol indicators, 2-of-3 momentum vote gated by ADX>=25.
```

### D-09 — Migration function placement

`_migrate_v3_to_v4` is added to `state_manager.py` between line 142 (where `_migrate_v2_to_v3` ends) and line 156 (where the migration dispatch table starts). Add to the dispatch table:

```python
_MIGRATION_DISPATCH = {
    1: _migrate_v0_to_v1,        # if exists
    2: _migrate_v1_to_v2,        # Phase 8 IN-06
    3: _migrate_v2_to_v3,        # Phase 14 D-09
    4: _migrate_v3_to_v4,        # Phase 22 (v1.2)  ← NEW
}
```

Bump `STATE_SCHEMA_VERSION = 4` in `system_params.py` line 111.

### D-10 — Forbidden-imports guard

`system_params.py` is already in the AST-guard pure-math list. Adding `STRATEGY_VERSION = 'v1.2.0'` is a string literal — no imports added, no hex-boundary impact. The forbidden-imports test in `tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent` does NOT need updating.

## Files to modify

- `system_params.py` — add `STRATEGY_VERSION` constant + bump `STATE_SCHEMA_VERSION`
- `state_manager.py` — add `_migrate_v3_to_v4` + register in dispatch + apply `strategy_version` to new signal writes
- `signal_engine.py` — verify no changes needed (compute returns values; state-shaping happens in `state_manager.save_state`)
- `main.py` — verify no changes needed (orchestration calls already go through `state_manager`)
- `dashboard.py` — render `strategy_version` somewhere visible (header? footer? next to each signal?) — to be decided in plan
- `docs/STRATEGY-CHANGELOG.md` — NEW, 3 entries
- `tests/test_state_manager.py` — add migration tests for v3→v4
- `tests/test_system_params.py` — add `STRATEGY_VERSION` format test (matches `^v\d+\.\d+\.\d+$`)
- `tests/test_dashboard.py` — assert `strategy_version` rendered
- `tests/fixtures/state/*.json` — golden fixtures may need backfill (or migration tests cover this)

## Out of scope (don't modify)

- `notifier.py` — no signal-logic awareness needed (email already shows banners; version display is dashboard-only for v1.2)
- `web/` — no auth or routing changes
- `auth_store.py` — unrelated
- Phase 19/20/23 plans — those phases consume `STRATEGY_VERSION`; Phase 22 just provides it

## Risk register

| Risk | Mitigation |
|------|-----------|
| Migration drops a signal row | Migration is additive (adds field); existing fields preserved. Test via `test_migrate_v3_to_v4_preserves_other_fields` |
| `STRATEGY_VERSION` import circularity | `system_params.py` already imported by `state_manager.py`; no new edges |
| Defensive read masks a real bug (silently using v1.0.0 default for an actually-broken row) | Add a `[State] WARN signal row missing strategy_version field — defaulting to v1.0.0` log line so it surfaces in journalctl |
| Operator forgets to bump on a real signal change | Manual discipline; supplement with a test that grep's `STRATEGY_VERSION` value matches the constants the test knows are "current" — if a constant changes without a version bump, test fails (covered by VERSION-01 success criterion) |

## Verification (what proves the phase shipped)

1. `python3 -c "import system_params; print(system_params.STRATEGY_VERSION)"` prints `v1.2.0`
2. `python3 -c "import system_params; print(system_params.STATE_SCHEMA_VERSION)"` prints `4`
3. Run signal cycle on a fresh state.json (`schema_version=3` baseline) — after run, `cat state.json | jq '.signals.SPI200.strategy_version'` returns `'v1.2.0'`
4. Run signal cycle on existing droplet state.json (already at v3) — first run migrates to v4 with `strategy_version='v1.1.0'` on existing rows; subsequent run rewrites those instruments' rows with `'v1.2.0'` (because the daily check writes a fresh signal); rows for instruments NOT touched in this run keep `'v1.1.0'`
5. `cat docs/STRATEGY-CHANGELOG.md` shows 3 entries (v1.0.0 / v1.1.0 / v1.2.0)
6. `pytest tests/test_state_manager.py::TestMigration -v` shows new `test_migrate_v3_to_v4_*` cases passing
7. Dashboard at `/` displays `strategy_version` somewhere (placement decided in plan)
