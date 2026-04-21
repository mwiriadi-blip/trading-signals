---
created: 2026-04-22T05:30:00.000Z
title: Configurable starting account and contract sizes
area: config
files:
  - system_params.py:70-92
  - .planning/phases/02-signal-engine-sizing-exits-pyramiding/02-CONTEXT.md (D-11 locks SPI_MULT=5, SPI_COST_AUD=6)
  - .planning/phases/04-end-to-end-skeleton-fetch-orchestrator-cli/04-CONTEXT.md (D-10 total return vs INITIAL_ACCOUNT)
  - .planning/phases/05-dashboard/05-CONTEXT.md (D-10 total return uses INITIAL_ACCOUNT)
---

## Problem

The system currently hardcodes:
- `INITIAL_ACCOUNT = 100_000` in `system_params.py` — the starting account base
- `SPI_MULT = 5` — SPI 200 mini contract ($5/point)
- `AUDUSD_NOTIONAL = 10_000`
- `SPI_COST_AUD = 6.0`
- `AUDUSD_COST_AUD = 5.0`

The operator (Marc) wants to:
1. **Enter the starting account amount as a base at setup/reset time** — not hardcoded. All trade sizing (`calc_position_size` in `sizing_engine.py`) and total-return math (dashboard DASH-07 / future email) derive from this base, so changing the base should cascade correctly.
2. **Pick contract size per instrument** — e.g. SPI 200 options are mini at $5/point, standard at $25/point, full at $50/point. Brokers differ; the operator may move between products or test with different sizes. Currently locked to $5 per Phase 2 D-11.

This surfaces during Phase 5 discuss-phase review of Total Return calculation (D-10: `(current - INITIAL_ACCOUNT) / INITIAL_ACCOUNT`) — that formula silently assumes the constant is always correct, but if the operator resets with a different base, the dashboard math is wrong until the constant is edited + committed.

## Solution

**TBD** — two sub-problems, likely separate phases or one combined config phase:

### Sub-problem A: starting account as runtime config
- Add a CLI flag or prompt at `--reset`: `python main.py --reset --initial-account 50000`
- Persist in `state.json` as a new top-level key `initial_account` (backward-compat: fall back to system_params.INITIAL_ACCOUNT=100_000 if key missing)
- Dashboard D-10 / email total-return formula reads `state['initial_account']` not `system_params.INITIAL_ACCOUNT`
- Schema version bump OR nested-under-existing key to avoid migration per Phase 3 D-08 precedent
- Validation: initial_account must be positive float, ≥ some minimum (e.g. $1,000) to avoid division-by-zero or absurd edge cases

### Sub-problem B: contract-size selection per instrument
- Extend `system_params` contract specs to support preset tiers:
  ```python
  SPI_CONTRACTS = {
    'mini': {'multiplier': 5.0, 'cost_aud': 6.0},      # current default
    'standard': {'multiplier': 25.0, 'cost_aud': 30.0}, # original SPEC.md
    'full': {'multiplier': 50.0, 'cost_aud': 50.0},     # ASX 200 SPI large
  }
  AUDUSD_CONTRACTS = {...}
  ```
- At `--reset` (or via a separate `--set-contract spi mini` subcommand), persist the selected tier into state.json per instrument
- Orchestrator (main.py) reads the selected tier at each run and passes through to `sizing_engine.step()` and `_closed_trade_to_record(cost_close_aud=...)`
- Migration: existing state.json (no contract field) falls back to `'mini'` (current locked behaviour)

### Cross-phase coordination
- **Dashboard (Phase 5)**: Total-return formula + key-stats display must read dynamic base, not the constant.
- **Email (Phase 6)**: Same — account-base references need to use the state field.
- **Tests**: existing Phase 2 fixture tests + Phase 3 record_trade tests assume SPI_MULT=5 + INITIAL_ACCOUNT=100k. Replacing constants with state-driven config touches those fixtures too. Careful: could be a large blast radius.
- **Backwards-compat**: all existing state.json files in the repo (if any) must still load without migration errors. Phase 3 `_validate_loaded_state` + `_migrate` hook is the place to add defaults.

### When to do this
- Before `--reset` gets real operator use in production (Phase 7 GHA deployment).
- Could fit as a decimal phase `/gsd-insert-phase 2.1` after Phase 2 but that touches too much downstream; probably better as a standalone phase after Phase 5 (before Phase 6/7 to avoid retrofit).
- Alternatively: Phase 8 Hardening could absorb this as a scope addition — fits the "make it real" theme of that phase.

### Open questions for the operator
- Is the starting-account prompt interactive (`input("Enter starting account: ")`) or CLI-flag-only (`--initial-account 50000`)?
- Should contract size be selectable per run, or only at `--reset` (locked for the life of the account)?
- Should tiers be a fixed enum (`mini`/`standard`/`full`) or fully-custom (operator provides multiplier + cost directly)?
