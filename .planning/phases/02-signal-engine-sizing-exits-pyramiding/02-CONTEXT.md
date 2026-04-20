# Phase 2: Signal Engine — Sizing, Exits, Pyramiding - Context

**Gathered:** 2026-04-21 (seed from Phase 1 REVIEWS follow-up — refine via `/gsd-discuss-phase 2`)
**Status:** Seed — folds 6 follow-up items from Phase 1's pass-2 cross-AI review. Run `/gsd-discuss-phase 2` (choose "Update it") to surface any remaining gray areas.
**Source:** `.planning/phases/01-signal-engine-core-indicators-vote/01-REVIEWS.md` §Recommended Follow-Up

<domain>
## Phase Boundary

Produce pure-math position sizing, exit decisions, and pyramid-level transitions for any given (state, indicators, today's bar) input — pure functions, fixture-tested, with the 9-cell signal-transition truth table locked down. Addresses requirements SIZE-01..06, EXIT-01..09, PYRA-01..05 (20 requirements).

**In scope:**
- `calc_position_size(account, signal, atr, rvol, multiplier)` — ATR-based risk sizing with vol-targeting, skip-if-zero (no `max(1, …)` floor)
- `get_trailing_stop(position, current_price, atr)` — LONG uses peak − 3×ATR; SHORT uses trough + 2×ATR; intraday HIGH/LOW drives peak/trough updates
- `check_stop_hit(position, high, low, atr)` — intraday LOW ≤ LONG stop; HIGH ≥ SHORT stop
- `check_pyramid(position, current_price, atr_entry)` — level 0→1 at +1×ATR, level 1→2 at +2×ATR, cap at level 2 (3 total contracts), max 1 step per run
- 9-cell signal-transition truth table: {LONG, SHORT, none} × {LONG, SHORT, FLAT} with exit-then-entry sequencing

**Out of scope (belongs to later phases):**
- State persistence (Phase 3) — sizing/exit functions take state as input, don't write
- yfinance fetch (Phase 4)
- Orchestration, CLI, email, dashboard, scheduling (Phases 4–7)

</domain>

<decisions>
## Implementation Decisions

### Constants layout (from Phase 1 REVIEWS follow-up #4)

- **D-01: Introduce `system_params.py` (or equivalent module) BEFORE Phase 2 adds its constants.**
  Rationale: Phase 1 left `ADX_GATE`, `MOM_THRESHOLD`, `ATR_PERIOD`, `ADX_PERIOD`, `MOM_PERIODS`, `RVOL_PERIOD`, `ANNUALISATION_FACTOR`, `LONG`, `SHORT`, `FLAT` all in `signal_engine.py`. Phase 2 adds `RISK_PCT_LONG=0.01`, `RISK_PCT_SHORT=0.005`, `TRAIL_MULT_LONG=3.0`, `TRAIL_MULT_SHORT=2.0`, `VOL_SCALE_TARGET=0.12`, `VOL_SCALE_MIN=0.3`, `VOL_SCALE_MAX=2.0`, `PYRAMID_TRIGGERS=(1.0, 2.0)`, `MAX_PYRAMID_LEVEL=2`, `ADX_EXIT_GATE=20`, plus per-instrument contract specs (`SPI_MULT=25`, `SPI_COST=30`, `AUDUSD_NOTIONAL=10000`, `AUDUSD_COST=5`). Keeping all of these in `signal_engine.py` would bloat the pure-math hex and mix trading-policy parameters with signal logic.
  Concretely: create `system_params.py` at repo root. Move Phase 1 constants that are policy-shaped (`ADX_GATE`, `MOM_THRESHOLD`, periods) OUT of `signal_engine.py` and INTO `system_params.py`. Leave `LONG=1 / SHORT=-1 / FLAT=0` as signal-encoding primitives in `signal_engine.py` (they're type constants, not policy). Sizing/exit functions read from `system_params` — no hardcoded literals.

### Input contracts at the Phase 1 → Phase 2 boundary (from Phase 1 REVIEWS follow-up #3, Phase 2 portion)

- **D-02: Phase 2 sizing and exit functions accept scalar inputs (atr: float, rvol: float, etc.), NOT raw DataFrames.**
  Rationale: Phase 1 already provides `get_latest_indicators(df) -> dict` that does the last-row extraction and `float()` cast. Phase 2 consumers work from scalars extracted by that helper. Phase 4 orchestrator becomes the single place that unpacks the dict → scalars → calls Phase 2 functions. This keeps Phase 2 fully pure-math and isolates the Phase 1 dict contract to one caller.
- **D-03: All Phase 2 public functions explicitly guard against NaN inputs.**
  Rationale: Per Phase 1 REVIEWS pass 2, Phase 1 passes through NaN (warm-up bars, flat-price div-by-zero) without raising. Phase 2 must define explicit behavior for NaN ATR, NaN RVol, NaN stop prices. Per SIZE-03 the RVol NaN case maps to vol_scale = 2.0 (floor the reciprocal). Extend the same explicit contract to every Phase 2 function: document NaN behavior in the docstring and cover it with a named test.

### Testing & fixture strategy (continuing Phase 1 conventions)

- **D-04: Reuse Phase 1's pure-loop oracle pattern for Phase 2 arithmetic** where helpful (e.g., independent hand-coded vol_scale and stop-distance calculators). Not every Phase 2 function needs an oracle — sizing is simpler math than Wilder — but pyramiding logic with state transitions benefits from a reference implementation.
- **D-05: 9-cell signal-transition truth table gets named scenario fixtures in the style of Phase 1's `TestVote` scenarios.** Each of the 9 cells (prev ∈ {LONG, SHORT, none} × new ∈ {LONG, SHORT, FLAT}) gets a fixture + a named test. Pyramid and exit-rule edge cases get additional named fixtures (gap-up crossing 2×ATR, ADX drop below 20, intraday HIGH touching trail stop).
- **D-06: Extend the determinism snapshot from Phase 1** rather than adding a parallel Phase 2 snapshot. Phase 2 functions are state transitions, not time series, so the snapshot mechanism doesn't map 1:1 — but the same SHA256 discipline for test expectations makes sense: commit expected outputs for a handful of representative (state, today's bar) inputs.

### Claude's Discretion

- Exact module name for constants (`system_params.py` vs `config/params.py` vs `constants.py`) — pick one and document
- Whether to expose a single `step(state, bar, indicators) -> new_state` function that chains size → exit → pyramid, or keep them as separate callable functions orchestrated by Phase 4
- Data class vs dict for `position` input (Phase 3 will own the canonical state schema; Phase 2 can use a TypedDict or NamedTuple in the interim)
- Whether to include a `DecisionResult` type that unifies size/exit/pyramid outputs or keep each function's return type minimal

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 2 requirements
- `SPEC.md` §SYSTEM LOGIC §5 (Position sizing) — risk_pct, trail_mult, vol_scale formulas
- `SPEC.md` §SYSTEM LOGIC §6 (Contract specs) — SPI $25/pt $30 round-trip; AUD/USD $10,000 notional $5 round-trip
- `SPEC.md` §SYSTEM LOGIC §7 (Exit rules) — signal reversal, ADX < 20 drop-out, trailing stop hit
- `SPEC.md` §SYSTEM LOGIC §8 (Pyramiding) — +1×ATR / +2×ATR thresholds, max 3 contracts
- `SPEC.md` §signal_engine.py — function signatures for `get_trailing_stop`, `check_stop_hit`, `calc_position_size`, `compute_unrealised_pnl`, `check_pyramid`
- `.planning/REQUIREMENTS.md` §Position Sizing (SIZE-01..06), §Exit Rules (EXIT-01..09), §Pyramiding (PYRA-01..05)
- `.planning/ROADMAP.md` §Phase 2 — goal + 5 success criteria + operator decisions (no-floor sizing, FLAT closes, intraday H/L)

### Phase 1 upstream
- `.planning/phases/01-signal-engine-core-indicators-vote/01-CONTEXT.md` — Phase 1 locked decisions (signal encoding, NaN policy, API shape)
- `.planning/phases/01-signal-engine-core-indicators-vote/01-REVIEWS.md` — pass-2 retrospective incl. follow-up items folded into this CONTEXT
- `.planning/phases/01-signal-engine-core-indicators-vote/01-VERIFICATION.md` — what Phase 1 actually delivers + accepted deviations (oracle-byte hash vs production-byte hash)
- `signal_engine.py` — Phase 1 public API this phase consumes (`get_latest_indicators`, `LONG`/`SHORT`/`FLAT`, constants)
- `tests/oracle/wilder.py`, `tests/oracle/mom_rvol.py` — pure-loop oracle pattern to reuse where appropriate

### Project-wide conventions
- `CLAUDE.md` §Operator Decisions — `n_contracts == 0` skips (no `max(1, …)` floor); FLAT closes open position; intraday HIGH/LOW for trailing stops
- `CLAUDE.md` §Conventions — signal integers, log prefixes, pytest + ruff
- `CLAUDE.md` §Architecture — hexagonal-lite; `signal_engine.py` must not import `state_manager.py`

### Carry-forward todos from STATE.md
- `.planning/STATE.md` §Todos Carried Forward — "Confirm SPI contract multiplier with operator's broker at Phase 2 kickoff ($25/pt full ASX 200 vs $5/pt SPI mini)"

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets (from Phase 1)

- `signal_engine.compute_indicators(df)` — produces the 8-column indicator DataFrame Phase 2 sizing/exit functions consume via `get_latest_indicators`
- `signal_engine.get_latest_indicators(df) -> dict` — canonical Phase 1 → Phase 2 boundary: returns `{atr, adx, pdi, ndi, mom1, mom3, mom12, rvol}` as Python floats (NaN preserved as `float('nan')`)
- `signal_engine.get_signal(df) -> int` — returns LONG/SHORT/FLAT as int; Phase 2's signal-transition matrix consumes this
- `LONG=1`, `SHORT=-1`, `FLAT=0` constants (remain in `signal_engine.py` per D-01)
- `tests/oracle/` pattern — pure-loop reference implementation alongside vectorized production, 1e-14 equivalence
- `tests/fixtures/scenario_*.csv` pattern — named synthetic fixtures per truth-table cell
- `tests/regenerate_goldens.py` — offline script pattern for golden regeneration (D-04 from Phase 1)
- Fixture CSV format with `%.17g` precision (Phase 1 Pitfall 4)
- `_assert_index_aligned` helper pattern (Phase 1 Plan 04, REVIEWS-addressed) — applicable to any (state, bar) comparison test

### Established Patterns

- Hexagonal-lite: pure math in `signal_engine.py` (Phase 1 + 2) must not import I/O or persistence modules — enforced by `TestDeterminism::test_forbidden_imports_absent` AST blocklist
- 2-space indent, single quotes, snake_case, hand-rolled math (no pandas-ta/TA-Lib)
- Every task in a plan has `<read_first>` + `<acceptance_criteria>` blocks with grep/pytest-verifiable conditions
- Deviations are documented inline in SUMMARY.md, not silently absorbed

### Integration Points

- **Upstream:** Phase 1's `get_latest_indicators` dict + `get_signal` int (consumed as scalars per D-02)
- **Downstream:** Phase 4 orchestrator will chain Phase 1 → Phase 2 → Phase 3 state write per bar
- **Sibling (no direct coupling):** Phase 3 state schema will include position fields Phase 2 reads/writes conceptually (`entry_price`, `n_contracts`, `pyramid_level`, `peak_price`/`trough_price`, `atr_entry`); Phase 2 consumes state as input but doesn't persist

</code_context>

<specifics>
## Specific Ideas

- **Phase 2 authoring note from REVIEWS pass 2:** production code will be the first consumer of `get_latest_indicators`. If the dict-key contract feels clumsy in practice (e.g., too many `latest['atr']` lookups in sizing code), flag it in SUMMARY. Phase 4 can wrap with a NamedTuple adapter if useful. Don't change Phase 1's API in this phase — that's Phase 1 debt.
- **9-cell truth table is the verification anchor.** The named scenarios approach from Phase 1 scaled cleanly (all 9 passed on first try). Replicate for signal transitions: `transition_none_to_long`, `transition_long_to_flat`, `transition_long_to_short_reverse`, etc. Filenames ARE documentation.
- **Intraday HIGH/LOW convention (operator-locked):** Both peak updates AND stop-hit detection use intraday HIGH (LONG) / LOW (SHORT), not close-only. Phase 2 fixtures must supply HIGH and LOW explicitly — a close-only fixture is under-specified for this phase.
- **No `max(1, …)` floor on sizing:** Per operator decision in Phase 1 STATE.md. If the sized contract count is 0 after vol-scale clip, return a `SkipTrade` decision with a warning string (not a silent `size=1` floor). Surface the warning into the return value so Phase 6 email can render it.
- **Pyramid adds cap at 1 per daily run.** Per PYRA-05: never double-add on gap days even if unrealised P&L crosses both +1×ATR and +2×ATR in a single bar. The `check_pyramid` function's state input must include `pyramid_level` so it can enforce the "one step per run" invariant without needing run-date awareness.

</specifics>

<deferred>
## Deferred Ideas

Items from Phase 1 REVIEWS pass-2 follow-up that do NOT belong in Phase 2 — captured here so they're not lost.

### Phase 1 code-level polish (REVIEWS items #1, #2, #5, #6)

Apply as a small `/gsd-quick` amendment to Phase 1 OR fold into the first housekeeping chunk of Phase 2's Wave 0.

- **Follow-up #1:** Add a comment block to `tests/test_signal_engine.py::TestDeterminism::test_snapshot_hash_stable` explaining why the test re-runs the oracle (not production) and linking to Phase 1 REVIEWS pass 2 + `01-06-SUMMARY.md`. Closes the documentation gap both reviewers flagged.
- **Follow-up #2:** Add `test_compute_indicators_is_idempotent` to `TestIndicators` — call `compute_indicators` twice and assert `allclose(out1, out2, atol=0, equal_nan=True)`. Locks a property Phase 2/4 relies on defensively.
- **Follow-up #5:** Commit `tests/regenerate_scenarios.py` that regenerates all 9 scenario CSVs from `scenarios.README.md` segment-endpoint recipes. Closes Codex's "reproducible on paper, not scripted" gap. Mirror the `tests/regenerate_goldens.py` never-runs-in-CI discipline (D-04 from Phase 1).
- **Follow-up #6 (optional):** Add a second determinism test that hashes the shipped PRODUCTION `compute_indicators` output and freezes the current SHA256 values. Acceptable tradeoff: locks current production bytes at the cost of requiring a snapshot update on any legitimate numpy/pandas upgrade. Skip if Phase 2 review agrees 1e-9 tolerance-based comparison + oracle-byte lock is enough.

### Phase 4 orchestrator guard (REVIEWS item #3)

- **Follow-up #3:** When Phase 4 orchestrator wraps calls to `get_signal` and `get_latest_indicators`, add a defensive contract check:
  - Non-empty DataFrame (fail fast with a clear error if `len(df) == 0`)
  - Required indicator columns present (fail fast if any of `[ATR, ADX, PDI, NDI, Mom1, Mom3, Mom12, RVol]` are missing)
  - `float64` dtype on indicator columns (catches numpy 2.0 float32 leak per Phase 1 Pitfall 5)
  Matches REQUIREMENTS §ERR-04 spirit ("top-level except wraps `run_daily_check`"). Phase 4's concern, not Phase 2's.

### Other items surfaced during pass-2 review (not REVIEWS-numbered, but worth tracking)

- **Extreme price scale sensitivity** (Gemini). 1e-9 `atol` is absolute; untested on sub-dollar scales. If Phase 1 is ever extended to new instruments (e.g., a crypto pair or micro-cap equity), revisit tolerance.
- **RVol NaN on single non-NaN value window** (Gemini). Phase 2's SIZE-03 handles magnitude (≤1e-9 → vol_scale=2.0); ensure the guard also handles explicit NaN (not just tiny-positive).

</deferred>

---

*Phase: 02-signal-engine-sizing-exits-pyramiding*
*Context seeded: 2026-04-21 from Phase 1 REVIEWS pass-2 follow-up*
*Next step: `/gsd-discuss-phase 2` — select "Update it" to surface any gray areas not already locked above*
