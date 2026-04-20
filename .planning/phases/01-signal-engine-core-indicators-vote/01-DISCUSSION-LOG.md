# Phase 1: Signal Engine Core — Indicators & Vote - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in `01-CONTEXT.md` — this log preserves the alternatives considered.

**Date:** 2026-04-20
**Phase:** 01-signal-engine-core-indicators-vote
**Areas discussed:** Golden fixture strategy, Module API shape, Edge-case / NaN policy, Test layout & determinism proof

---

## Golden fixture strategy

### Q1: What's the source of the 400-bar OHLCV fixture data?

| Option | Description | Selected |
|--------|-------------|----------|
| Synthetic deterministic series | Crafted or seeded-PRNG bars deliberately hitting every case. Stable forever, covers every vote branch. Not "realistic" market data. | |
| Real historical snapshot | One-time yfinance pull of ^AXJO or AUDUSD=X for 400 trading days, committed as CSV. Looks like prod data; yfinance retroactive adjustments can silently shift goldens. | |
| Both — real canonical + synthetic edge-case slices | One real 400-bar canonical + 5-10 small synthetic fixtures (10-30 bars) isolating each branch. | ✓ |

**User's choice:** Both — real canonical + synthetic edge-case slices

### Q2: How do we generate the hand-calculated golden values at 1e-9 precision?

| Option | Description | Selected |
|--------|-------------|----------|
| Dead-simple Python oracle in tests/oracle/ | Separate loop-based reference implementations. Committed alongside tests. Regenerable. Reviews well because loops are obviously correct. | ✓ |
| Trusted library one-shot (pandas-ta or TA-Lib) | Run pandas-ta ONCE, commit goldens, never add as runtime dep. Zero oracle code to maintain but blurs CLAUDE.md "no-TA-Lib" rule. | |
| Hand-calc in Excel/Sheets | Compute step-by-step in a spreadsheet. Max transparency; floating-point divergence between Excel and NumPy at 1e-9 is a known failure mode. | |

**User's choice:** Dead-simple Python oracle in tests/oracle/

### Q3: Fixture granularity — one big fixture or many targeted ones?

| Option | Description | Selected |
|--------|-------------|----------|
| Both — canonical 400-bar + many small scenario fixtures | 400-bar anchors full-pipeline regression; small (10-30 bar) scenarios isolate each vote branch + warm-up + edge cases. Each failure names the scenario. | ✓ |
| Single 400-bar fixture only | Parametrize tests by row-index. Less data to maintain; test failures harder to diagnose. | |
| Many small fixtures only | 15-20 small fixtures, no big one. Every test surgical; no full-pipeline regression. | |

**User's choice:** Both — one canonical 400-bar + many small scenario fixtures

### Q4: How do we regenerate goldens when formulas legitimately change?

| Option | Description | Selected |
|--------|-------------|----------|
| tests/regenerate_goldens.py script | Checked-in Python script. Run manually when formulas intentionally change. Git diff reviews the change. Never runs in CI. | ✓ |
| Frozen bytes forever | Regenerate only by deleting + re-running. Forces deliberate action; harder to review what changed. | |
| CI regenerates and diffs every build | Always fresh; flaky if oracle has any nondeterminism, slower tests. | |

**User's choice:** tests/regenerate_goldens.py script

---

## Module API shape

### Q1: What's the public surface of signal_engine.py?

| Option | Description | Selected |
|--------|-------------|----------|
| Only what main.py needs | Public: compute_indicators, get_signal. Private: _atr, _adx, _plus_di, _minus_di, _mom, _rvol. Smallest blast radius. | ✓ |
| Expose every indicator publicly | Public: atr, adx, plus_di, minus_di, mom, rvol, compute_indicators, get_signal. Trivial direct unit tests. | |
| Split into indicators.py + vote.py | Cleaner separation; violates CLAUDE.md "pure math in signal_engine.py" single-file rule. | |

**User's choice:** Only what main.py needs (extended to include get_latest_indicators helper from Q4)

### Q2: What does get_signal() return?

| Option | Description | Selected |
|--------|-------------|----------|
| Bare int: 1 \| -1 \| 0 | Matches LONG/SHORT/FLAT constants. Keeps function pure and signature predictable. | ✓ |
| Dataclass: SignalResult(signal, reason, votes_up, votes_dn, adx) | Richer debug output; larger API surface. | |
| Tuple: (signal, debug_dict) | Lightweight middle ground; breaks pure-int contract. | |

**User's choice:** Bare int: 1 | -1 | 0

### Q3: Shape of compute_indicators(df) output?

| Option | Description | Selected |
|--------|-------------|----------|
| Return new DataFrame with indicator columns appended | Input unchanged; output is input + [ATR, ADX, PDI, NDI, Mom1, Mom3, Mom12, RVol]. Matches SPEC.md docstring. | ✓ |
| Mutate input DataFrame in place | Slightly cheaper memory; tests and callers can silently double-compute columns. | |
| Return dict of Series | Cleanest type; deviates from SPEC.md's "Adds columns" contract. | |

**User's choice:** Return new DataFrame with indicator columns appended

### Q4: How should indicator values be accessed downstream?

| Option | Description | Selected |
|--------|-------------|----------|
| Last-row dict helper: get_latest_indicators(df) -> dict | Small helper returning last-bar scalars. Hides df.iloc[-1] indexing behind a single function. Prevents off-by-one errors. | ✓ |
| Direct df.iloc[-1] access at call sites | Fewer layers; .iloc[-1] scattered across main.py + sizing. | |
| Return indicators dict from compute_indicators alongside df | One call gives both series and scalars; clumsy tuple return. | |

**User's choice:** Last-row dict helper: get_latest_indicators(df) -> dict

---

## Edge-case / NaN policy

### Q1: get_signal(df) return when latest bar's ADX is NaN?

| Option | Description | Selected |
|--------|-------------|----------|
| Return FLAT (0) | NaN ADX behaves like ADX<25 — no position. Safe-by-default. | ✓ |
| Raise ValueError | Force caller to decide; every call site needs try/except. | |
| Return None (sentinel) | Breaks bare-int signal contract from API area. | |

**User's choice:** Return FLAT (0)

### Q2: get_signal return when Mom1/Mom3/Mom12 is NaN (warm-up)?

| Option | Description | Selected |
|--------|-------------|----------|
| NaN mom counts as "no vote" — FLAT unless ≥2 non-NaN moms agree | During first 252 bars Mom12 NaN; 2-of-2 agreement on Mom1+Mom3 can still produce LONG/SHORT. Natural, no special cases. | ✓ |
| Any NaN mom forces FLAT | Wastes first 252 bars; fixtures must be 252+ bars to exit FLAT. | |
| Skip NaN, require ≥2 of remaining to agree | Equivalent outcome to (a), different framing. | |

**User's choice:** NaN mom counts as "no vote" — signal FLAT unless ≥2 non-NaN moms vote the same way

### Q3: Division-by-zero guard in +DI / -DI when sum(TR) == 0?

| Option | Description | Selected |
|--------|-------------|----------|
| Return NaN (let it propagate) | 0/0 is undefined → NaN → ADX NaN → FLAT via Q1 rule. No magic numbers. | ✓ |
| Replace with tiny epsilon (1e-12) | +DI/-DI stay finite; arbitrary epsilon; hides pathological data. | |
| Return 0 for +DI / -DI | ADX=0 → FLAT; masks NaN-vs-zero distinction. | |

**User's choice:** Return NaN (let it propagate)

### Q4: RVol when 20-day return std is exactly 0?

| Option | Description | Selected |
|--------|-------------|----------|
| Return 0.0 (let Phase 2's vol_scale clamp handle it) | Phase 2 has SIZE-03 guard "RVol ≤ 1e-9 as 2.0"; Phase 1 returns mathematically correct 0. | ✓ |
| Return NaN when std == 0 | Duplicates Phase 2's guard logic in Phase 1. | |
| Replace with tiny epsilon (1e-9) | Hides zero-vol condition; Phase 2 guard never fires. | |

**User's choice:** Return 0.0 (let vol_scale clamp handle it in Phase 2)

---

## Test layout & determinism proof

### Q1: How should tests/test_signal_engine.py be organized?

| Option | Description | Selected |
|--------|-------------|----------|
| One file, grouped by concern with pytest classes | tests/test_signal_engine.py with TestIndicators, TestVote, TestEdgeCases, TestDeterminism classes. Matches roadmap success criterion verbatim. | ✓ |
| Split per concern | test_indicators.py + test_vote.py + test_edge_cases.py. Diverges from roadmap's `-k indicators_or_vote` filter. | |
| Split per indicator | test_atr.py, test_adx.py, test_mom.py, test_rvol.py, test_vote.py. Granular but incompatible with roadmap assertion. | |

**User's choice:** One file, grouped by concern with pytest classes

### Q2: How do we prove the 1e-9 determinism claim?

| Option | Description | Selected |
|--------|-------------|----------|
| Committed hash-of-outputs snapshot + deterministic test | tests/determinism/snapshot.json stores SHA256 of each indicator series. test_determinism.py recomputes and asserts match. Any numpy/pandas upgrade that shifts bits fails loudly. | ✓ |
| pytest run on fixed Python + pinned deps, no hash snapshot | Trust fixed inputs + pinned deps = deterministic output. No early warning on dep drift. | |
| Compare against oracle every run + numpy.testing.assert_allclose(atol=1e-9) | What main tests already do; conflates correctness with determinism. | |

**User's choice:** Committed hash-of-outputs snapshot + deterministic test

### Q3: pytest-freezer usage — where does frozen time matter in Phase 1?

| Option | Description | Selected |
|--------|-------------|----------|
| Not needed in Phase 1 | Indicator math takes a DataFrame — no datetime.now() calls. Defer to Phase 4+. | ✓ |
| Freeze time anyway as safety net | Noise, implies clock dependency when there isn't. | |
| Assert no datetime/time imports in signal_engine.py | Grep-style negative test enforcing pure-math discipline structurally. | |

**User's choice:** Not needed in Phase 1

### Q4: Test coverage goal — how do we know every vote branch is covered?

| Option | Description | Selected |
|--------|-------------|----------|
| Named scenario fixtures covering the 9-case truth table | Explicit fixture names per scenario. One test per scenario. Missing branches visible by name. | ✓ |
| pytest-cov with 100% branch coverage gate | CI fails on drop; doesn't distinguish "exercised" from "asserts correct behavior." | |
| Both — named scenarios AND coverage gate | Max rigor; more tooling cost. | |

**User's choice:** Named scenario fixtures covering the 9-case truth table

---

## Claude's Discretion

The user deferred the following implementation details to Claude's judgement (captured in `<decisions>` §Claude's Discretion of `01-CONTEXT.md`):

- Docstring convention (NumPy-style vs Google-style)
- Type hint coverage (public API only vs all internal helpers)
- Exact golden CSV format details (header row, float precision, NaN representation)
- Internal helper organisation (single `_ewm_wilder` utility vs per-indicator private functions)
- Whether `get_latest_indicators` lives in `signal_engine.py` or a tiny `signal_engine/adapters.py` if the file grows

## Deferred Ideas

- **Docstring/type-hint strict conventions** — set when writing code; revisit if Phase 2+ authors diverge.
- **Logging policy inside pure-math code** — Phase 1 has no logging; revisit if Phase 4 orchestrator wants richer signal diagnostics surfaced from within the pure layer.
- **Per-instrument freshness validation** (DATA-05 area) — Phase 4 concern.
- **Richer signal return type** (SignalResult dataclass) — declined for this phase; revisit if Phase 6 email needs it.
