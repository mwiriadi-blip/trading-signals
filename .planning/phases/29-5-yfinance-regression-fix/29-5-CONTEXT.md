# Phase 29.5: yfinance Regression Fix — Context

**Gathered:** 2026-05-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Single-workstream fix phase. Scope is **exclusively** the backtest settings
wiring bug identified by the Phase 29 / plan 13 spike (UAT-23-1).

**In scope:**
- Wire `settings=default_settings_for_market(instrument)` into
  `backtest/cli.py::_run_one_instrument` at the single call site (line 135).
- Add or update integration test(s) asserting non-zero trades when the CLI runs
  with per-market settings.
- Verify `python -m backtest --years 5` exits 0 (PASS) with non-zero trades for
  both SPI200 and AUDUSD.

**Out of scope:**
- Any Phase 29 debt-closure work (DEBT-02, DEBT-03, DEBT-04, OPS-02,
  UAT-26-1, UAT-17-1, UAT-17-2). Those remain in Phase 29 and are not
  re-opened here.
- Signal engine logic changes.
- yfinance schema handling.
- New backtest methodology (no new CLI flags, no settings sweep, no schema bumps).

Phase 29 leaves Phase 29.5 with the spike artefact only — no fix attempts were
made in Phase 29. The RCA is complete and canonical.

</domain>

<decisions>
## Implementation Decisions

- **D-01:** Canonical input is
  `.planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-13-YFINANCE-SPIKE-RCA.md`.
  All implementation decisions flow from that document. Read it before planning.
- **D-02:** Fix shape is TIGHT (1 call site, 0 new modules). Do not introduce a
  `paths.py`-style helper or a new `get_settings()` indirection — pass the result
  of the existing `system_params` lookup directly at the call site.
- **D-03:** Test update policy — update or add tests in `tests/test_backtest_cli.py`
  and/or `tests/test_backtest_simulator.py` to cover the wired path. Do NOT
  regenerate deterministic parquet fixtures; the existing cached data is correct.
- **D-04:** Acceptance gate — `python -m backtest --years 5` with cached parquet
  data produces `total_trades > 0` for both instruments and exits with code 0.
  This closes UAT-23-1.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Spike artefacts (required input)
- `.planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-13-YFINANCE-SPIKE-DIAGNOSTIC.md`
  — full diagnostic trace: branches ruled out, signal counts, sizing math.
- `.planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-13-YFINANCE-SPIKE-RCA.md`
  — **canonical root cause + blast radius + recommended fix shape**. Read this first.

### Fix site
- `backtest/cli.py:135` — `_run_one_instrument`, the single call site where
  `simulate()` must receive `settings=`.

### Existing assets (no changes needed)
- `system_params.DEFAULT_STRATEGY_SETTINGS_BY_MARKET` — already contains correct
  per-market settings (`adx_gate=20`, `votes_required=1`, `risk_pct_long=0.05`,
  `one_contract_floor=True` for SPI200).
- `backtest/simulator.py::simulate()` — signature already accepts `settings=None`;
  no changes to this file.
- `.planning/backtests/data/^AXJO-2021-05-10-2026-05-10.parquet` (1265 rows)
- `.planning/backtests/data/AUDUSD=X-2021-05-10-2026-05-10.parquet` (1300 rows)
  — cached data is correct; do NOT re-fetch or regenerate.

### Test files (update, don't regenerate)
- `tests/test_backtest_cli.py`
- `tests/test_backtest_simulator.py`

### Project constraints
- `CLAUDE.md` §Rules — file-size cap 500 LOC, no ungated edits, always read before edit.
- Phase 29.5 scope boundary: ONLY the settings wiring fix. No Phase 29 work.

</canonical_refs>

<acceptance>
## Acceptance Criteria

- `python -m backtest --years 5` (using cached parquet data) exits 0 (PASS).
- `total_trades > 0` for both SPI200 and AUDUSD in the output report.
- All existing tests pass (`npm run build && python -m pytest` or equivalent).
- UAT-23-1 can be marked PASS.

</acceptance>

---

*Phase: 29-5-yfinance-regression-fix*
*Context gathered: 2026-05-10*
*Spawned from: Phase 29 / plan 13 escape-29-5 branch*
