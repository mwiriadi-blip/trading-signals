# Phase 2: Signal Engine — Sizing, Exits, Pyramiding - Context

**Gathered:** 2026-04-21 (seeded from Phase 1 REVIEWS pass-2 follow-up; refined via `/gsd-discuss-phase 2`)
**Status:** Ready for planning
**Source:** seed = Phase 1 REVIEWS follow-up; update = `/gsd-discuss-phase 2` session 2026-04-21
**Reviews-revision pass:** 2026-04-21 — D-15..D-19 added from `/gsd-review --phase 2 --all` cross-AI feedback

<domain>
## Phase Boundary

Produce pure-math position sizing, exit decisions, and pyramid-level transitions for any given (state, indicators, today's bar) input — pure functions, fixture-tested, with the 9-cell signal-transition truth table locked down. Addresses requirements SIZE-01..06, EXIT-01..09, PYRA-01..05 (20 requirements).

**In scope:**
- `calc_position_size(account, signal, atr, rvol, multiplier) -> SizingDecision` — ATR-based risk sizing with vol-targeting, skip-if-zero (no `max(1, …)` floor)
- `get_trailing_stop(position, current_price, atr) -> float` — LONG uses peak − 3×`atr_entry`; SHORT uses trough + 2×`atr_entry`; intraday HIGH/LOW drives peak/trough updates (D-15: stop distance anchored to `position['atr_entry']`, NOT today's atr)
- `check_stop_hit(position, high, low, atr) -> bool` — intraday LOW ≤ LONG stop; HIGH ≥ SHORT stop (uses `atr_entry` per D-15)
- `check_pyramid(position, current_price, atr_entry) -> PyramidDecision` — level 0→1 at +1×ATR, level 1→2 at +2×ATR, cap at level 2 (3 total contracts); advances at most 1 level per call (PYRA-05 enforced statelessly)
- `compute_unrealised_pnl(position, current_price, multiplier, cost_aud_open) -> float` — gross minus half-cost-on-open per D-13 (signature expanded by D-17)
- Optional thin `step(position, bar, indicators, old_signal, new_signal, account, multiplier, cost_aud_open) -> StepResult` wrapper that chains exit-then-entry per EXIT-03/04 (signature expanded by D-17; owns peak/trough updates per D-16; applies pyramid add per D-18)
- 9-cell signal-transition truth table: {LONG, SHORT, none} × {LONG, SHORT, FLAT} with exit-then-entry sequencing
- 15 named scenario fixtures (9 transitions + 6 edge cases)

**Out of scope (belongs to later phases):**
- State persistence (Phase 3) — sizing/exit functions take state as input, don't write
- yfinance fetch (Phase 4)
- Orchestration, CLI, email, dashboard, scheduling (Phases 4–7)
- Account mutation on close/reversal (Phase 3 owns; D-19)

</domain>

<decisions>
## Implementation Decisions

### Constants layout (from Phase 1 REVIEWS follow-up #4)

- **D-01: Introduce `system_params.py` BEFORE Phase 2 adds its constants.**
  Rationale: Phase 1 left `ADX_GATE`, `MOM_THRESHOLD`, `ATR_PERIOD`, `ADX_PERIOD`, `MOM_PERIODS`, `RVOL_PERIOD`, `ANNUALISATION_FACTOR`, `LONG`, `SHORT`, `FLAT` all in `signal_engine.py`. Phase 2 adds `RISK_PCT_LONG=0.01`, `RISK_PCT_SHORT=0.005`, `TRAIL_MULT_LONG=3.0`, `TRAIL_MULT_SHORT=2.0`, `VOL_SCALE_TARGET=0.12`, `VOL_SCALE_MIN=0.3`, `VOL_SCALE_MAX=2.0`, `PYRAMID_TRIGGERS=(1.0, 2.0)`, `MAX_PYRAMID_LEVEL=2`, `ADX_EXIT_GATE=20`, plus contract specs per D-11. Keeping all of these in `signal_engine.py` would bloat the pure-math hex and mix trading-policy parameters with signal logic.
  Concretely: create `system_params.py` at repo root. Move Phase 1 constants that are policy-shaped (`ADX_GATE`, `MOM_THRESHOLD`, periods) OUT of `signal_engine.py` and INTO `system_params.py`. Leave `LONG=1 / SHORT=-1 / FLAT=0` as signal-encoding primitives in `signal_engine.py` (they're type constants, not policy). Sizing/exit functions read from `system_params` — no hardcoded literals.

### Input contracts at the Phase 1 → Phase 2 boundary

- **D-02: Phase 2 sizing and exit functions accept scalar inputs (atr: float, rvol: float, etc.), NOT raw DataFrames.**
  Rationale: Phase 1 already provides `get_latest_indicators(df) -> dict` that does the last-row extraction and `float()` cast. Phase 2 consumers work from scalars extracted by that helper. Phase 4 orchestrator becomes the single place that unpacks the dict → scalars → calls Phase 2 functions. This keeps Phase 2 fully pure-math and isolates the Phase 1 dict contract to one caller.
- **D-03: All Phase 2 public functions explicitly guard against NaN inputs.**
  Rationale: Per Phase 1 REVIEWS pass 2, Phase 1 passes through NaN (warm-up bars, flat-price div-by-zero) without raising. Phase 2 must define explicit behavior for NaN ATR, NaN RVol, NaN stop prices. Per SIZE-03 the RVol NaN case maps to vol_scale = 2.0 (floor the reciprocal). Extend the same explicit contract to every Phase 2 function: document NaN behavior in the docstring and cover it with a named test. Per the 2026-04-21 review-revision pass (B-1) the per-function NaN policy is now: `get_trailing_stop` → `float('nan')`, `check_stop_hit` → `False`, `check_pyramid` → `PyramidDecision(0, current_level)`.

### Testing & fixture strategy

- **D-04: Reuse Phase 1's pure-loop oracle pattern for Phase 2 where the math warrants it.**
  Most Phase 2 arithmetic is simple enough that oracle mirrors would be overkill (`calc_position_size` is 3 multiplications + a clip). Oracle mirrors make sense for: (a) `check_pyramid` state-machine (a hand-written loop reference that consumes a sequence of (state, price, atr_entry) tuples and returns the state trajectory), (b) anything with subtle rounding. Skip oracles for pure arithmetic.
- **D-05: 9-cell signal-transition truth table gets named scenario fixtures in the style of Phase 1's `TestVote` scenarios.** Filenames ARE documentation (e.g., `scenario_transition_long_to_short_reverse.csv`).
- **D-06: Extend the determinism snapshot from Phase 1** rather than adding a parallel Phase 2 snapshot. Phase 2 functions are state transitions, not time series, so the snapshot mechanism doesn't map 1:1 — commit expected SizingDecision/PyramidDecision/stop-hit outputs for a handful of representative (state, today's bar) inputs as JSON goldens, hashed once at fixture-regeneration time.
- **D-14: 15 scenario fixtures total.**
  9 transitions (one per truth-table cell): `transition_long_to_long`, `transition_long_to_short`, `transition_long_to_flat`, `transition_short_to_long`, `transition_short_to_short`, `transition_short_to_flat`, `transition_none_to_long`, `transition_none_to_short`, `transition_none_to_flat`.
  6 edge cases: `pyramid_gap_crosses_both_levels_caps_at_1`, `adx_drop_below_20_while_in_trade`, `long_trail_stop_hit_intraday_low`, `short_trail_stop_hit_intraday_high`, `long_gap_through_stop`, `n_contracts_zero_skip_warning`.
  Each fixture includes (prev_position_state, today's OHLC bar, today's indicators, expected decision).

### Module layout

- **D-07: Phase 2 code lives in a new `sizing_engine.py` at the repo root.**
  Pure-math module, analogous to `signal_engine.py`. Imports from `system_params.py` and the three signal constants (`LONG`, `SHORT`, `FLAT`) from `signal_engine.py`. Must NOT import `state_manager.py`, `notifier.py`, `dashboard.py`, `main.py`, `requests`, `datetime`, `os`, or any other I/O/network module. Phase 1's `TestDeterminism::test_forbidden_imports_absent` AST guard gets extended in Wave 0 of Phase 2 to cover `sizing_engine.py` with the same blocklist.
  SPEC.md currently lists sizing/exit/pyramid functions under `signal_engine.py`; Phase 2 plan docs flag this as a SPEC.md amendment needed at Wave 0. Functional behavior is unchanged.

### Type contracts

- **D-08: `Position` is a `TypedDict` in `system_params.py`.**
  Fields: `direction: Literal['LONG', 'SHORT']`, `entry_price: float`, `entry_date: str`, `n_contracts: int`, `pyramid_level: int`, `peak_price: float | None`, `trough_price: float | None`, `atr_entry: float`.
  `peak_price` is populated for LONG positions, None for SHORT; mirror for `trough_price`. Phase 3's state.json dict round-trips directly into this TypedDict. Use `typing.TypedDict` (Python 3.11+ has solid support) with the `total=True` default.

- **D-09: Return types mix dataclasses and primitives.**
  `calc_position_size` returns `SizingDecision(contracts: int, warning: str | None)` (dataclass) — `warning` captures the SIZE-05 "size=0" string or any future sizing edge case. `check_pyramid` returns `PyramidDecision(add_contracts: int, new_level: int)` — makes the level transition explicit to the caller. `get_trailing_stop` returns `float`, `check_stop_hit` returns `bool`, `compute_unrealised_pnl` returns `float`. Dataclasses are `@dataclass(frozen=True, slots=True)` and live in `sizing_engine.py` (alongside the functions that produce them).

### API shape

- **D-10: Both individual callables AND a thin `step()` wrapper.** **(amended 2026-04-21 by D-17 — see below for expanded signatures)**
  Individual functions (`calc_position_size`, `get_trailing_stop`, `check_stop_hit`, `check_pyramid`, `compute_unrealised_pnl`) are the primary API — Phase 4 orchestrator calls them in explicit sequence with logging between steps. A thin helper `step(position, bar, indicators, old_signal, new_signal) -> StepResult` chains exits-first-then-entries per EXIT-03/04 for cases where the orchestrator just wants "apply the daily transition." `step()` composes the individual functions, does not duplicate their logic. Both paths share the same dataclass return types.
  `StepResult` is a dataclass capturing: the updated position (or None if flat), closed trade (if any, with realised P&L), sizing decision, pyramid decision, and list of warnings surfaced during the step.
  *Note 2026-04-21 reviews-revision pass:* the original signatures shown here — `step(position, bar, indicators, old_signal, new_signal) -> StepResult` and `compute_unrealised_pnl(position, current_price, multiplier) -> float` — are SUPERSEDED by D-17. The actual implemented signatures are `step(position, bar, indicators, old_signal, new_signal, account, multiplier, cost_aud_open) -> StepResult` and `compute_unrealised_pnl(position, current_price, multiplier, cost_aud_open) -> float`. See D-17 for rationale.

### Contract specs (OVERRIDES SPEC.md)

- **D-11: SPI = $5/pt mini contract, $6 AUD round-trip cost.**
  SPEC.md and CLAUDE.md currently state $25/pt full ASX 200 SPI + $30 round-trip. Operator confirmed in discuss-phase 2 that the actual broker quote is the SPI mini at $5/pt. Concretely: `SPI_MULT = 5`, `SPI_COST_AUD = 6.0`. AUD/USD unchanged: `AUDUSD_NOTIONAL = 10000`, `AUDUSD_COST_AUD = 5.0`. A Wave 0 task must amend SPEC.md §6 and CLAUDE.md to match — these documents are project-wide canonical refs and must not silently contradict `system_params.py`. Sizing math in `calc_position_size` multiplies through these constants; fixture expected-outputs are computed against the $5/pt multiplier.

### Cost timing (OVERRIDES SPEC.md implicit convention)

- **D-13: Round-trip cost is split half on open, half on close.**
  For SPI: $3 AUD deducted when a position opens; $3 AUD deducted when it closes. For AUD/USD: $2.50 each side. Operator prefers this over "full round-trip deducted at close" because unrealised P&L during the position reflects the opening half — more realistic intra-trade accounting.
  `compute_unrealised_pnl(position, current_price, multiplier, cost_aud_open)` returns `(current_price - entry_price) * n_contracts * multiplier - open_cost`, where `open_cost = cost_aud_open * n_contracts`. Caller supplies `cost_aud_open = instrument_cost_aud / 2` (e.g., SPI: `6.0/2 = 3.0`; AUD/USD: `5.0/2 = 2.5`). Signature finalized by D-17.
  `record_trade` (Phase 3) applies the closing half on exit. Phase 2 calculates the split; Phase 3 wires it into the trade log.

### Pyramid invariant enforcement

- **D-12: PYRA-05 (max 1 pyramid step per daily run) is enforced STATELESSLY inside `check_pyramid`.**
  `check_pyramid(position, current_price, atr_entry)` reads `position.pyramid_level` and evaluates ONLY the trigger for the NEXT level:
  - At level 0: adds if `unrealised_distance >= 1 * atr_entry` → returns `PyramidDecision(add_contracts=1, new_level=1)`
  - At level 1: adds if `unrealised_distance >= 2 * atr_entry` → returns `PyramidDecision(add_contracts=1, new_level=2)`
  - At level 2: never adds → returns `PyramidDecision(add_contracts=0, new_level=2)`
  The function NEVER returns `add_contracts=2`. The "gap day crosses both thresholds" case naturally caps at one add per run because only the current-level trigger is evaluated. No run-date awareness needed; no orchestrator flag needed.
  *Note (D-18):* `check_pyramid` itself remains stateless — it never mutates the position. The decision-application step (mutating `position_after['n_contracts']` and `position_after['pyramid_level']`) is owned by `step()`, not by `check_pyramid`. D-18 governs how `step()` applies the decision.

### Reviews-revision pass — 2026-04-21 (D-15..D-19, post cross-AI review)

These five decisions arose from the `/gsd-review --phase 2` cross-AI review (Gemini LOW + Codex MEDIUM). They lock the previously ambiguous semantics around trailing-stop ATR anchor, peak/trough update ownership, the expanded `compute_unrealised_pnl` and `step()` signatures, the post-pyramid position state, and the reversal-sizing account boundary. They are non-negotiable from this point forward; downstream plan revisions reference these IDs by number.

- **D-15: Trailing-stop ATR anchor = `position['atr_entry']` (NOT today's atr).**
  Rationale: Stop distance must remain consistent with the original sizing risk. Today's ATR responds to vol regime changes and could ratchet the stop AWAY from price during vol spikes (LONG stop drifts down on a vol spike). Operator already locked "no max(1) floor" / conservative-defaults posture; anchoring to entry ATR matches.
  Concretely: `get_trailing_stop(position, current_price, atr)` ignores its `atr` parameter for the trail distance — uses `position['atr_entry']` instead. The `atr` parameter stays in the signature for API stability but is unused (mirrors the existing `current_price` parameter convention from RESEARCH §Pattern 2). `check_stop_hit` mirrors the same anchor (uses `position['atr_entry']` not the `atr` argument).
  Affected: 02-03-PLAN.md `get_trailing_stop`/`check_stop_hit` AC + docstrings; sizing_engine.py docstrings; fixture `expected_trail_stop` values must be recomputed using `atr_entry` (which equals `prev_position.atr_entry`, NOT `indicators.atr`).
  Resolves: Gemini "Trailing Stop Ratchet Logic" + Codex consensus concern #1.

- **D-16: Peak/trough updates owned by `step()` BEFORE calling stop logic.**
  Rationale: D-10 documents `step()` as a "thin wrapper that chains exit-then-entry". Making it the single owner of peak/trough updates makes it a complete daily-transition wrapper rather than a half-built one. Avoids correctness risk where individual callers forget to update peak before calling `check_stop_hit`.
  Concretely: At the very start of `step()`, BEFORE any exit/entry logic, on a shallow copy of the input position update `peak_price = max(peak_price or entry_price, bar['high'])` for LONG / `trough_price = min(trough_price or entry_price, bar['low'])` for SHORT. Because `Position` is a TypedDict (a plain dict at runtime), `step()` works on a fresh shallow copy `dict(position)` to preserve the "never mutate input" invariant — the updated peak/trough lives on the copy that becomes `position_after`.
  Individual callers (`get_trailing_stop`, `check_stop_hit`) continue to assume peak/trough is already updated — no signature change. The owner is now `step()`.
  Resolves: Codex MEDIUM #5 + Codex consensus concern #1 ownership half.
  Affected: 02-05-PLAN.md `step()` Task 1 — add explicit peak/trough update step at the top + AC asserting it. 02-03-PLAN.md docstrings clarified to say "assumes peak/trough already updated by caller (typically `step()`)."

- **D-17: API contract amendment to D-10 — `compute_unrealised_pnl` and `step()` signatures expand.**
  D-10's signatures expand to:
  - `compute_unrealised_pnl(position, current_price, multiplier, cost_aud_open) -> float` (adds `cost_aud_open` so the half-on-open D-13 split is testable in isolation; Codex HIGH #3 + RESEARCH Open Question A3)
  - `step(position, bar, indicators, old_signal, new_signal, account, multiplier, cost_aud_open) -> StepResult` (adds `account`/`multiplier`/`cost_aud_open` because reversal sizing needs them — these can't be defaulted)
  Rationale: D-10 was written before the cost-split D-13 was elaborated and before reversal sizing was considered concretely. The expanded signatures are the minimum needed; defaulting them would introduce hidden state. Cleaner to make Phase 4 orchestrator pass the per-instrument cost as a scalar than to couple the math layer to the constant table (Pitfall 6).
  Resolves: Codex HIGH #3 ("API contract drift").
  Affected: D-10 line above gets the "**(amended 2026-04-21 by D-17)**" note; 02-02-PLAN.md `compute_unrealised_pnl` AC; 02-05-PLAN.md `step()` Task 1 AC + objective; SPEC.md §signal_engine.py module-split note already includes the expanded signatures via plan 02-01.

- **D-18: `step()` applies pyramid add to `position_after`.**
  Rationale: `position_after` should mean "true post-step state". Codex HIGH #4 correctly flags that returning a `pyramid_decision` without applying it leaves `position_after` pre-pyramid, undercutting the determinism story. Apply the add to `position_after['n_contracts']` and `position_after['pyramid_level']` inside `step()`. The `pyramid_decision` field stays in StepResult for traceability/Phase 3 audit logging — applying the decision does not erase its visibility.
  Concretely: after `check_pyramid` returns `PyramidDecision(add_contracts=1, new_level=N)`, `step()` mutates the working position copy: `position['n_contracts'] += pyramid_decision.add_contracts; position['pyramid_level'] = pyramid_decision.new_level`. If `add_contracts == 0`, both fields stay unchanged. This preserves D-12's stateless intent for `check_pyramid` itself (the function is the same); only `step()` knows about the application.
  Resolves: Codex HIGH #4.
  Affected: 02-05-PLAN.md `step()` Task 1 — explicit AC: "if `pyramid_decision.add_contracts > 0`, then `position_after['n_contracts'] == position['n_contracts'] + 1` AND `position_after['pyramid_level'] == pyramid_decision.new_level`". Fixture `pyramid_gap_crosses_both_levels_caps_at_1` expected `position_after` must reflect this (n_contracts incremented by 1, pyramid_level=1).

- **D-19: Reversal sizing uses INPUT account; Phase 2 does NOT mutate account.**
  Rationale: Account mutation is Phase 3 (`record_trade` updates state). Phase 2 sizing functions are pure-math by D-02 — they take scalars in, return values out. Sizing the reversed leg off the input account (pre-close P&L) is a documented approximation; Phase 3/4 owns precise account-state evolution. The approximation is small (a single trade's P&L delta against $100k typically) and avoids re-entering the cost-accounting hex from inside step().
  Resolves: Codex MEDIUM "muddy boundary" (re-sizing post-close account ambiguity).
  Affected: 02-05-PLAN.md `step()` Task 1 — explicit docstring note "Reversal sizing uses input `account`; account mutation is Phase 3's responsibility (D-19)." + AC assertion.

### Claude's Discretion

- Exact `SizingDecision` / `PyramidDecision` / `StepResult` field ordering + docstring style — pick one consistent with Phase 1's style
- Whether `step()` helper reuses Phase 2's `StepResult` dataclass or returns a plain tuple. Prefer `StepResult` for parity with D-09.
- Whether scenario fixtures use CSV format (like Phase 1) or JSON (since Phase 2 inputs include more structure than OHLCV). Recommended: JSON per fixture, since each scenario carries (position, bar, indicators, expected_decisions) — multiple dataclass-shaped objects that CSV would awkwardly flatten.
- Exact `Position` field name for SHORT's trough (named `trough_price` in D-08 for clarity, but `peak_price` reused for both directions with semantics flipped is a viable alternative — pick one and document).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 2 requirements (NOTE: D-11 and D-13 override SPEC.md — see decisions)
- `SPEC.md` §SYSTEM LOGIC §5 (Position sizing) — risk_pct, trail_mult, vol_scale formulas
- `SPEC.md` §SYSTEM LOGIC §6 (Contract specs) — **SUPERSEDED by D-11 for SPI (now mini $5/pt $6 RT)**; AUD/USD unchanged
- `SPEC.md` §SYSTEM LOGIC §7 (Exit rules) — signal reversal, ADX < 20 drop-out, trailing stop hit
- `SPEC.md` §SYSTEM LOGIC §8 (Pyramiding) — +1×ATR / +2×ATR thresholds, max 3 contracts
- `SPEC.md` §signal_engine.py — function signatures for `get_trailing_stop`, `check_stop_hit`, `calc_position_size`, `compute_unrealised_pnl`, `check_pyramid`. **SUPERSEDED by D-07 for file location (now `sizing_engine.py`); also SUPERSEDED by D-17 for `compute_unrealised_pnl`/`step()` signatures.**
- `.planning/REQUIREMENTS.md` §Position Sizing (SIZE-01..06), §Exit Rules (EXIT-01..09), §Pyramiding (PYRA-01..05)
- `.planning/ROADMAP.md` §Phase 2 — goal + 5 success criteria + operator decisions (no-floor sizing, FLAT closes, intraday H/L)

### Phase 1 upstream
- `.planning/phases/01-signal-engine-core-indicators-vote/01-CONTEXT.md` — Phase 1 locked decisions (signal encoding, NaN policy, API shape)
- `.planning/phases/01-signal-engine-core-indicators-vote/01-REVIEWS.md` — pass-2 retrospective incl. follow-up items folded into this CONTEXT
- `.planning/phases/01-signal-engine-core-indicators-vote/01-VERIFICATION.md` — what Phase 1 actually delivers + accepted deviations (oracle-byte hash vs production-byte hash)
- `signal_engine.py` — Phase 1 public API this phase consumes (`get_latest_indicators`, `LONG`/`SHORT`/`FLAT`, constants)
- `tests/oracle/wilder.py`, `tests/oracle/mom_rvol.py` — pure-loop oracle pattern to reuse where D-04 says it helps

### Project-wide conventions
- `CLAUDE.md` §Operator Decisions — `n_contracts == 0` skips (no `max(1, …)` floor); FLAT closes open position; intraday HIGH/LOW for trailing stops
- `CLAUDE.md` §Conventions — signal integers, log prefixes, pytest + ruff
- `CLAUDE.md` §Architecture — hexagonal-lite; pure-math modules (`signal_engine.py`, `sizing_engine.py` per D-07) must not import `state_manager.py`, `notifier.py`, `dashboard.py`
- `CLAUDE.md` §Stack — **SUPERSEDED by D-11 for SPI multiplier/cost; Wave 0 task amends this**

### Reviews-revision artifacts (2026-04-21)
- `.planning/phases/02-signal-engine-sizing-exits-pyramiding/02-REVIEWS.md` — cross-AI review feedback (Gemini LOW + Codex MEDIUM); origin of D-15..D-19 + B-1..B-6 plan tweaks

### Carry-forward todos now RESOLVED by this CONTEXT
- `.planning/STATE.md` §Todos Carried Forward — "Confirm SPI contract multiplier" → **resolved in D-11** (SPI mini $5/pt, $6 RT)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets (from Phase 1)

- `signal_engine.compute_indicators(df)` — produces the 8-column indicator DataFrame; Phase 2 consumes the last row via `get_latest_indicators`
- `signal_engine.get_latest_indicators(df) -> dict` — canonical Phase 1 → Phase 2 boundary: returns `{atr, adx, pdi, ndi, mom1, mom3, mom12, rvol}` as Python floats (NaN preserved as `float('nan')`)
- `signal_engine.get_signal(df) -> int` — returns LONG/SHORT/FLAT as int; Phase 2's signal-transition matrix consumes this
- `LONG=1`, `SHORT=-1`, `FLAT=0` constants (remain in `signal_engine.py` per D-01)
- `tests/oracle/` pattern — pure-loop reference implementation alongside vectorized production (reuse per D-04 where warranted)
- `tests/fixtures/scenario_*.csv` pattern — named synthetic fixtures per truth-table cell; Phase 2 likely uses JSON per-fixture instead (see Claude's Discretion)
- `tests/regenerate_goldens.py` — offline script pattern for golden regeneration (D-04 from Phase 1)
- `tests/regenerate_scenarios.py` — offline script that regenerates Phase 1 scenario CSVs from scenarios.README.md recipes (committed in quick task 260421-723); Phase 2's scenario regenerator should mirror this shape
- Fixture CSV format with `float_format='%.17g'` (Phase 1 Pitfall 4) — applies to any Phase 2 CSV emissions
- `_assert_index_aligned` helper pattern (Phase 1 Plan 04) — applicable where applicable to DataFrame-input tests
- `TestDeterminism::test_forbidden_imports_absent` AST blocklist — extend in Wave 0 of Phase 2 to cover `sizing_engine.py` and `system_params.py`

### Established Patterns

- Hexagonal-lite: pure math modules (`signal_engine.py` + `sizing_engine.py`) must not import I/O or persistence modules — enforced by AST blocklist
- 2-space indent, single quotes, snake_case, hand-rolled math (no pandas-ta/TA-Lib)
- Every task in a plan has `<read_first>` + `<acceptance_criteria>` blocks with grep/pytest-verifiable conditions
- Deviations are documented inline in SUMMARY.md with Rule-1/2/3 classification
- Constants amendments (SPEC.md, CLAUDE.md) committed as Wave 0 docs tasks BEFORE code tasks read from them

### Integration Points

- **Upstream:** Phase 1's `get_latest_indicators` dict + `get_signal` int (consumed as scalars per D-02); `LONG`/`SHORT`/`FLAT` constants
- **Downstream:** Phase 4 orchestrator will chain Phase 1 → Phase 2 → Phase 3 state write per bar via individual callables (D-10 primary path) or `step()` helper (D-10 convenience path)
- **Sibling (Phase 3):** Phase 3's state.json dict round-trips directly into `Position` TypedDict (D-08). Phase 2 consumes Position as input but doesn't persist — Phase 3 owns persistence

</code_context>

<specifics>
## Specific Ideas

- **Wave 0 must include SPEC.md + CLAUDE.md amendments** reflecting D-11 (SPI mini $5/pt, $6 RT) BEFORE any Phase 2 code is written. Silent-contradiction between spec docs and `system_params.py` is exactly the kind of drift Phase 1 REVIEWS flagged about documentation gaps.
- **Scenario fixtures use JSON, not CSV** (per Claude's Discretion in D-14). Each fixture captures a tuple of dataclass-shaped objects: `{prev_position, bar: {O,H,L,C,V}, indicators: {...}, expected_sizing, expected_trail_stop, expected_pyramid, expected_new_position}`. Regenerator script produces these offline.
- **Phase 2 uses Phase 1's get_latest_indicators pattern.** Phase 4 orchestrator will call `compute_indicators(df)` then `get_latest_indicators(out)` to get a scalar dict, then destructure into the individual Phase 2 function calls. Tests in Phase 2 construct this dict directly; they do NOT call compute_indicators (that's a Phase 1 concern, already tested).
- **No `max(1, …)` floor on sizing.** Per operator decision. If the sized contract count is 0 after vol-scale clip, return `SizingDecision(contracts=0, warning='size=0: account $X, ATR $Y, RVol $Z → vol_scale_contracts=$W < 1')`.
- **Intraday HIGH/LOW convention (operator-locked):** Peak updates AND stop-hit detection use intraday HIGH (LONG) / LOW (SHORT). Phase 2 fixtures supply HIGH and LOW explicitly. Close-only fixtures are under-specified for this phase. Update ownership belongs to `step()` (D-16).
- **Exit-then-entry two-phase eval (EXIT-03/04):** When signal reverses (LONG→SHORT or SHORT→LONG), `step()` applies: (1) close the existing position via a virtual EXIT-01/02 first, (2) compute exit P&L + closing-cost-half, (3) size the new position in the reversed direction (sized from INPUT account per D-19), (4) open it with opening-cost-half. Tests assert both legs fire in one call.
- **Determinism at Phase 2:** Follow Phase 1's oracle-anchored SHA256 discipline (D-06). Commit JSON goldens + a `tests/determinism/phase2_snapshot.json` with SHA256 of each fixture's expected_decision structure. Re-run in `TestDeterminism` (extend Phase 1's class or add a new one — planner's call).

</specifics>

<deferred>
## Deferred Ideas

### Phase 1 code-level polish — items closed in quick task 260421-723

- ~~**Follow-up #1:** Oracle-hash comment on `TestDeterminism::test_snapshot_hash_stable`~~ → closed by quick task 260421-723 commit `edb1641`
- ~~**Follow-up #2:** `test_compute_indicators_is_idempotent`~~ → closed by quick task 260421-723 commit `4ca36ac`
- ~~**Follow-up #5:** `tests/regenerate_scenarios.py`~~ → closed by quick task 260421-723 commit `2ace992`

### Phase 1 code-level polish — still open (optional)

- **Follow-up #6 (optional):** Second determinism test that hashes shipped PRODUCTION `compute_indicators` output. Re-evaluate during Phase 2 review — if tolerance-based comparison + oracle-byte lock continues to feel sufficient, skip.

### Phase 4 orchestrator guard (REVIEWS item #3)

- **Follow-up #3:** When Phase 4 orchestrator wraps calls to `get_signal` and `get_latest_indicators`, add a defensive contract check (non-empty DataFrame, required indicator columns present, float64 dtype). Not Phase 2's concern; captured here so Phase 4 planning picks it up.

### Other watchlist items from Phase 1 REVIEWS pass 2

- **Extreme price scale sensitivity** (Gemini). 1e-9 `atol` is absolute; untested on sub-dollar scales.
- **RVol NaN on single non-NaN value window** (Gemini). Phase 2's SIZE-03 handles magnitude; ensure the guard also handles explicit NaN (covered by D-03).

### Phase 3 schema coordination

- `Position` TypedDict defined in `system_params.py` per D-08 will become the canonical Position shape. Phase 3's state.json dict serialization must round-trip through this type (positions dict keyed by instrument, each value matches Position TypedDict). Coordinate during Phase 3 planning.

</deferred>

---

*Phase: 02-signal-engine-sizing-exits-pyramiding*
*Context seeded: 2026-04-21 from Phase 1 REVIEWS pass-2 follow-up*
*Context refined: 2026-04-21 via `/gsd-discuss-phase 2` — 8 new decisions locked (D-07..D-14)*
*Reviews-revision pass: 2026-04-21 — D-15..D-19 added from cross-AI review (Gemini LOW + Codex MEDIUM); D-10 amended*
*Next step: re-run plans 02-01..05 against revised CONTEXT.md (already in flight)*
