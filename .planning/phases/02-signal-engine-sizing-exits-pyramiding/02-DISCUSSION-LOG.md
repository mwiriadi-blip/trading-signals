# Phase 2: Sizing, Exits, Pyramiding - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in `02-CONTEXT.md` — this log preserves the alternatives considered.

**Date:** 2026-04-21
**Phase:** 02-signal-engine-sizing-exits-pyramiding
**Seed source:** Phase 1 REVIEWS pass-2 follow-up (decisions D-01..D-06 pre-existed)
**Areas discussed this session:** Module layout, Position state shape, Decision return types, Chained step vs separate functions, SPI contract override, SPI cost, PYRA-05 enforcement location, Cost timing, Scenario fixture count

---

## Existing context check

| Option | Description | Selected |
|--------|-------------|----------|
| Update it | Load seed and surface additional gray areas | ✓ |
| View it | Show seed first, decide after | |
| Skip | Use seed as-is, proceed to plan-phase | |

---

## Pre-flight: SPI contract multiplier

| Option | Description | Selected |
|--------|-------------|----------|
| $25/pt full ASX 200 SPI | Keeps SPEC.md and CLAUDE.md literal: SPI_MULT=25, SPI_COST=30 round-trip | |
| $5/pt SPI mini | Overrides SPEC.md: SPI_MULT=5; cost TBD from broker. SIG-06 math affected. | ✓ |
| Not sure — defer to Plan 02 | Work with $25/pt default; carry-forward todo | |

**User's choice:** $5/pt SPI mini — overrides SPEC.md, captured as D-11.

---

## Area selection

| Option | Description | Selected |
|--------|-------------|----------|
| Module layout | signal_engine.py vs new file vs split per concern | ✓ |
| Position state shape | TypedDict vs NamedTuple vs raw dict | ✓ |
| Decision return types | Primitives vs dataclasses vs tuples | ✓ |
| Chained step vs separate | Single step() vs individual callables | ✓ |

**User's choice:** All 4 areas selected.

---

## Module layout

### Q: Where do Phase 2 functions live?

| Option | Description | Selected |
|--------|-------------|----------|
| New `sizing_engine.py` | Pure-math module, signal_engine.py stays focused. Hex boundary clean. | ✓ |
| Grow signal_engine.py | Honors SPEC.md literal but mixes concerns at ~500+ lines | |
| Split per concern (sizing.py/exits.py/pyramid.py) | Finest granularity; 3 new modules for Phase 2 alone | |

**User's choice:** New `sizing_engine.py` — captured as D-07.

---

## Position state shape

### Q: What type does the `position` parameter carry?

| Option | Description | Selected |
|--------|-------------|----------|
| TypedDict `Position` in system_params.py | IDE completion + mypy; Phase 3 state.json deserializes into it | ✓ |
| NamedTuple `Position` | Immutable; Phase 3 dict-shaped state needs conversion at boundary | |
| Raw dict (defer schema) | Simplest; weakest type safety | |

**User's choice:** TypedDict `Position` in system_params.py — captured as D-08.

---

## Decision return types

### Q: What do Phase 2 functions return?

| Option | Description | Selected |
|--------|-------------|----------|
| Dataclasses for decisions, primitives for scalars | SizingDecision + PyramidDecision; float/bool elsewhere | ✓ |
| All primitives | SIZE-05 "size=0" warning becomes awkward global list | |
| All dataclasses | Over-engineered for trailing_stop and stop_hit | |

**User's choice:** Dataclasses for decisions, primitives for scalars — captured as D-09.

---

## Chained step vs separate

### Q: Does Phase 2 expose a single step() that chains functions, or keep them separately callable?

| Option | Description | Selected |
|--------|-------------|----------|
| Separate callables, no composite step | Phase 4 orchestrator chains them; max flexibility | |
| Composite `step()` only | Harder to unit-test each concern | |
| Both — individual functions + thin step() wrapper | Individual primary; step() convenience | ✓ |

**User's choice:** Both — captured as D-10.

---

## SPI mini round-trip cost

### Q: SPEC.md had $30 for full contract. What's the mini cost?

| Option | Description | Selected |
|--------|-------------|----------|
| $6 round-trip (typical IB/CMC mini) | SPI_COST_AUD=6.0 | ✓ |
| $10 round-trip | SPI_COST_AUD=10.0 | |
| Unknown — use $6 default, flag to confirm | Placeholder + carry-forward todo | |

**User's choice:** $6 round-trip — captured as D-11 (SPI_COST_AUD=6.0).

---

## PYRA-05 enforcement location

### Q: Where is "max 1 pyramid step per daily run" enforced?

| Option | Description | Selected |
|--------|-------------|----------|
| Inside `check_pyramid` — stateless | Evaluates only next-level trigger; naturally caps at 1 | ✓ |
| Orchestrator owns a per-run flag | Phase 4 sets pyramid_added_today; adds state to orchestrator | |

**User's choice:** Inside `check_pyramid` stateless — captured as D-12.

---

## Cost timing

### Q: How is cost charged?

| Option | Description | Selected |
|--------|-------------|----------|
| Deducted on close only | Full round-trip at exit; matches "round-trip" semantics | |
| Split half on open, half on close | Half deducted each side; realistic intra-trade accounting | ✓ |
| Unrealised ignores cost; record_trade applies at close | Same as option 1 from unrealised side | |

**User's choice:** Split half on open, half on close — captured as D-13. Overrides SPEC.md's implicit "round-trip at close" convention.

---

## Scenario fixture count

### Q: How many scenarios beyond the 9-cell transition matrix?

| Option | Description | Selected |
|--------|-------------|----------|
| 9 transitions + 6 edge cases = 15 total | Matches Phase 1 rigor; clear test output names | ✓ |
| Minimal: 9 transitions only | Edge cases via parametrized unit tests | |
| Expand: 9 + 10+ edge fixtures | Every EXIT/PYRA gets its own; ~20 files | |

**User's choice:** 15 total — captured as D-14.

---

## Closing: more areas?

| Option | Description | Selected |
|--------|-------------|----------|
| I'm ready for context | Write CONTEXT.md now | ✓ |
| Exit-reversal sequencing mechanics | EXIT-03/04 two-phase eval detail | |
| Dataclass location + naming | sizing_engine.py vs system_params.py | |
| Oracle scope for Phase 2 | Which Phase 2 functions get oracle mirrors | |

**User's choice:** I'm ready for context.

---

## Claude's Discretion (captured in CONTEXT.md)

- Exact dataclass field ordering + docstring style
- Whether `step()` reuses `StepResult` or returns a plain tuple
- Scenario fixture format: CSV vs JSON (recommended JSON per specifics)
- `Position` field naming for SHORT's trough

## Deferred Ideas

All tracked in CONTEXT.md `<deferred>` section, including:
- Phase 1 polish items (REVIEWS #1/#2/#5 closed by quick task 260421-723; #6 still optional)
- Phase 4 orchestrator guard (REVIEWS #3)
- Extreme price scale sensitivity and RVol-NaN-single-value watchlist items
- Phase 3 schema coordination note
