# Phase 3: State Persistence with Recovery - Context

**Gathered:** 2026-04-21 via `/gsd-discuss-phase 3` session
**Status:** Ready for planning
**Amended:** 2026-04-21 — added D-17..D-20 from `/gsd-plan-phase 3 --reviews` revision pass

<domain>
## Phase Boundary

Provide a `state_manager.py` module the orchestrator (Phase 4) can rely on to load, mutate, and save `state.json` durably — with crash-mid-write protection, corruption recovery, and a schema-version migration hook ready for v2. Addresses requirements STATE-01..07.

**In scope:**
- `load_state() -> dict` — atomic read; on JSON-parse error: backup the corrupt file + reinitialise + append corruption warning + return fresh state (STATE-03)
- `save_state(state: dict) -> None` — atomic write via tempfile + fsync (file + parent dir) + os.replace (STATE-02)
- `record_trade(state: dict, trade: dict) -> dict` — appends to trade_log, computes & deducts D-13 closing-half cost, adjusts account, sets `positions[trade['instrument']] = None`, validates shape (raise ValueError on missing/wrong fields)
- `update_equity_history(state: dict, date: str, equity: float) -> dict` — appends `{date, equity}` (caller computes equity per Phase 2's compute_unrealised_pnl)
- `reset_state() -> dict` — fresh state with `account=100_000`, empty positions/trade_log/equity_history/warnings, `signals={SPI200: 0, AUDUSD: 0}`, current `schema_version`
- `append_warning(state: dict, source: str, message: str) -> dict` — helper for all subsystems to record warnings into `state['warnings']` (bounded to last 100)
- Schema-version migration hook (no-op at v1; structure ready for v2)
- Test suite: named scenarios for each STATE-XX requirement + crash-mid-write simulation + corruption recovery + AST blocklist extension

**Out of scope (belongs to later phases):**
- Orchestration logic that calls these functions (Phase 4)
- yfinance fetch (Phase 4)
- Email rendering of `state['warnings']` (Phase 5 — Phase 3 just stores; Phase 5 picks the display rule, defaulting to last-24h-only)
- Dashboard reads of state.json (Phase 6)

</domain>

<decisions>
## Implementation Decisions

### Position schema — what's stored vs what's recomputed (Area 1)

- **D-01: An inactive (flat) position is represented as `positions[instrument] = None`.**
  Rationale: matches Phase 2's `step()` which returns `position_after = None` on close. Cleanest type contract — `bool(state['positions']['SPI200'])` tells you if active. SPEC.md's `{active: false}` representation is explicitly superseded — that shape requires translating between Phase 2 Position dict and state shape, introducing two sources of truth for "is this position active." When active, `positions[instrument]` is a Position-shaped dict per Phase 2 D-08.

- **D-02: Derived fields (`trail_stop`, `unrealised_pnl`) are NOT persisted in state.json.**
  Rationale: state.json holds the Position-shaped dict per Phase 2 D-08 (direction, entry_price, entry_date, n_contracts, pyramid_level, peak_price, trough_price, atr_entry) — nothing more. `trail_stop` is recomputed each daily run via `get_trailing_stop()`; `unrealised_pnl` via `compute_unrealised_pnl()`. Single source of truth — no cache invalidation, no schema drift between Phase 2 D-08 and the state file. Dashboard (Phase 6) and email (Phase 5) read these as transient computed values, not persisted state. SPEC.md's `trail_stop` and `unrealised_pnl` fields in the positions block are explicitly superseded.

- **D-03: `signals` (top-level dict) is initialised to `{'SPI200': 0, 'AUDUSD': 0}` by `reset_state()`.**
  Rationale: matches CLAUDE.md FLAT=0 convention. Pre-populated for both instruments so orchestrator and dashboard don't need defensive `.get()` defaults. Type contract is consistent: `signals[instrument]` is always `int` in `{-1, 0, 1}`.

- **D-04: `update_equity_history(state, date, equity)` accepts equity as a caller-computed input.**
  Rationale: state_manager.py stays a pure I/O hex — must NOT import sizing_engine (would break hexagonal-lite per CLAUDE.md). The orchestrator (Phase 4) already has `step()` results containing `unrealised_pnl` per position; aggregating `equity = state['account'] + sum(unrealised_pnl across active positions)` is the orchestrator's responsibility before calling update_equity_history.

### Crash & corruption recovery (Area 2)

- **D-05: "Corrupt" means JSON parse error only.**
  Rationale: `load_state()` catches `json.JSONDecodeError` → triggers backup + reinit + warning. Schema mismatches (missing required keys, wrong types) RAISE as bugs because they indicate code-vs-state divergence the operator should know about — silently nuking state on a code-side typo would mask real bugs. Narrow definition; keeps recovery surgical.

- **D-06: Backup file goes in the same directory as state.json, named `state.json.corrupt.<ISO-timestamp>`.**
  Rationale: matches STATE-03 literal text in REQUIREMENTS.md. Visible in `ls`, easy for operator to inspect manually. Filename: `state.json.corrupt.20260421T093045Z` (ISO 8601 basic format, UTC). The repo root holds `state.json` per SPEC.md FILE STRUCTURE; backups go alongside.

- **D-07: A corruption-recovery event appends to `state['warnings']` with `source='state_manager'`.**
  Rationale: surfaces in the daily email (Phase 5) per D-13's last-24h filter. Operator sees it next morning. No silent recoveries. Message format: `'recovered from corruption; backup at state.json.corrupt.<ts>'`. Also logs to stderr with `[State]` prefix per CLAUDE.md log convention.

- **D-08: Atomic write protocol — `tempfile.NamedTemporaryFile + fsync(file) + fsync(parent dir) + os.replace`.** *(amended 2026-04-21 — see D-17 for corrected durability ordering)*
  Rationale: standard atomic-write pattern. fsync the file (data durability), fsync the parent directory (rename durability — important on ext4/xfs), then `os.replace` (atomic on POSIX). Crash mid-write leaves original `state.json` untouched. tempfile name pattern: `state.json.tmp.<pid>` or `tempfile.NamedTemporaryFile(dir='.', delete=False)` — implementation detail.
  **Amendment (D-17, 2026-04-21):** The relative ordering of parent-dir fsync vs `os.replace` was incorrect in the original phrasing. Per Linux kernel rename guarantees and LWN durability discussions, parent-dir fsync MUST happen AFTER `os.replace` to make the rename itself durable. Atomicity (no torn writes) is preserved by either order, but durability against power loss after the rename is only guaranteed by the post-replace fsync. See D-17 below for the corrected sequence and the RESEARCH.md correction note.

### `warnings` field design (Area 3)

- **D-09: Each warning entry has shape `{date: 'YYYY-MM-DD', source: str, message: str}`.**
  Rationale: minimal but structured. `source` identifies which subsystem flagged it (`'state_manager'`, `'sizing_engine'`, `'notifier'`, `'fetch'`, `'orchestrator'`). `date` is the run date (not full timestamp — daily-cadence system). Easy to render in email/dashboard. Easy to filter (`[w for w in state['warnings'] if w['date'] == today]`). No level/severity field — every entry is something the operator should see.

- **D-10: `state_manager.append_warning(state, source, message) -> dict` is the canonical helper for all writes to `state['warnings']`.**
  Rationale: single helper validates shape (required keys: source + message), adds today's date automatically (consistent date format), enforces D-11 bound. Phase 2's size=0 warnings, Phase 4's fetch/network warnings, Phase 5's email send failures, and Phase 3's own corruption-recovery message ALL call `append_warning(state, source, msg)`. state_manager is the only direct writer to `state['warnings']` — other subsystems route through this helper. Prevents schema drift over time.

- **D-11: `state['warnings']` is bounded to the last 100 entries.**
  Rationale: roughly 5 months of daily runs assuming ~0-1 warnings/day. Keeps state.json small (matters when state is embedded in dashboard HTML per SPEC §dashboard). Trim oldest entries when `len > 100`. Bound is configurable via a `MAX_WARNINGS` constant in `system_params.py` (mirroring Phase 2's policy-constants pattern per D-01 of Phase 2).

- **D-12: Daily email surfaces only warnings from the last 24 hours.**
  Rationale: operator sees fresh issues without noise from old ones. Phase 3 stores all warnings (subject to D-11 bound); Phase 5 filters to today. Phase 3 ensures the schema supports the filter (`date` field is present on every entry).

### `record_trade` boundaries (Area 4)

- **D-13: `record_trade(state, trade)` owns the position close.**
  Rationale: single atomic state mutation — appends to `trade_log`, deducts D-13 closing-half cost, adjusts `state['account']` by net P&L, AND sets `positions[trade['instrument']] = None` (per D-01). Matches the mental model "record_trade = the trade is now in the books." Orchestrator calls record_trade once per `step()` result that has `closed_trade is not None`; record_trade handles all the bookkeeping in one call.

- **D-14: `record_trade` deducts the D-13 closing-half cost INSIDE the function.**
  Rationale: completes the cost-split symmetry started in Phase 2. Phase 2's `compute_unrealised_pnl` deducts the opening half (`cost_aud_open`); Phase 3's `record_trade` deducts the closing half. Single source of truth for cost timing. The trade dict from caller carries: `{instrument, direction, entry_date, exit_date, entry_price, exit_price, n_contracts, gross_pnl, exit_reason, multiplier, cost_aud}`. record_trade computes:
  ```
  closing_cost_half = trade['cost_aud'] * trade['n_contracts'] / 2
  net_pnl = trade['gross_pnl'] - closing_cost_half
  state['account'] += net_pnl
  ```
  Then writes `trade['net_pnl'] = net_pnl` into the trade dict before appending to trade_log (so trade_log entries record the FINAL net_pnl). The opening half was already deducted from `compute_unrealised_pnl`'s output during the position's lifetime — it never flowed through `account` until close.

  **Note:** `gross_pnl` from caller is the price-delta P&L only: `(exit_price - entry_price) * n_contracts * multiplier` for LONG, mirror for SHORT. The orchestrator computes this from the `closed_trade` returned by Phase 2's `step()` and passes it forward. Phase 2's `_close_position` already computes and stores the gross — orchestrator hands it to record_trade as-is.

  **Amendment (D-20, 2026-04-21):** The trade-dict mutation pattern (`trade['net_pnl'] = net_pnl` then append) was undocumented as part of the contract. D-20 below replaces it with a non-mutating append (`dict(trade, net_pnl=net_pnl)`). Trade_log entries still carry net_pnl; caller's input dict is preserved.

- **D-15: `record_trade` validates the trade dict shape and raises `ValueError` on missing/wrong fields.** *(extended 2026-04-21 — see D-19 for full-field type checks)*
  Rationale: catches integration bugs at the boundary (Phase 4 wire-up). Required fields: `instrument` (str in {'SPI200', 'AUDUSD'}), `direction` ('LONG'|'SHORT'), `entry_date` + `exit_date` (ISO YYYY-MM-DD strings), `entry_price` + `exit_price` + `gross_pnl` (float), `n_contracts` (int > 0), `exit_reason` (str), `multiplier` + `cost_aud` (float). Wrong types or missing keys raise ValueError with a specific message naming the offending field. Phase 4 wire-up tests catch these immediately.
  **Extension (D-19, 2026-04-21):** Original implementation only validates `instrument`, `direction`, `n_contracts`. D-19 below extends `_validate_trade` to enforce types on the remaining 8 fields (string non-empty for `entry_date`/`exit_date`/`exit_reason`; finite numeric — explicitly rejecting bool — for `entry_price`/`exit_price`/`gross_pnl`/`multiplier`/`cost_aud`).

- **D-16: `record_trade` is NOT idempotent — each call appends.**
  Rationale: simpler contract. Caller (Phase 4 orchestrator) is responsible for calling it exactly once per `step()` result that has `closed_trade is not None`. Orchestrator naturally does this; double-record only happens on explicit caller bug, catchable in code review. Idempotency-by-key approaches (instrument+exit_date) would block legitimate same-day re-open-then-close edge cases (rare but possible) and false-sense-of-safety the caller's responsibility. Idempotency-by-UUID is overengineering for a single-operator daily system.

### Reviews-revision amendments (Area 5)

> **2026-04-21 reviews-revision pass.** Decisions D-17..D-20 below are amendments / extensions to D-08, D-15 produced by `/gsd-plan-phase 3 --reviews` after cross-AI review (Gemini LOW · Codex MEDIUM, 8 actionable items). They lock the conservative / D-05-aligned default for each item flagged as HIGH or MEDIUM in the review.

- **D-17: Atomic write durability ordering — `write → flush/fsync(file) → close → os.replace → fsync(parent dir)`.** *(amends D-08; resolves Codex HIGH #3, 2026-04-21 reviews-revision pass)*
  Rationale: The parent-directory fsync's purpose is to make the RENAME durable on disk (per Linux kernel rename guarantees, LWN durability discussions). fsync'ing BEFORE the replace means the rename itself isn't on disk yet — defeats the point. Atomicity (no torn writes) is preserved by either order, but durability against power loss AFTER the rename is only guaranteed by the post-replace fsync. This is the canonical durable-write idiom.
  **Affected:**
  - `state_manager.py::_atomic_write` — body must perform `os.replace(tmp_path_str, path)` BEFORE the `if os.name == 'posix': ... os.fsync(dir_fd)` block, not after.
  - `tests/test_state_manager.py::TestAtomicity` — add `test_atomic_write_fsyncs_parent_dir_after_os_replace` that patches both `os.replace` and `os.fsync`, captures call order via a single mock-call list, and asserts `os.replace` is recorded before the parent-dir `os.fsync`.
  - 02-PLAN.md AC grep checks — currently only enforce presence of `os.replace`, `os.fsync`, POSIX guard. Must additionally enforce post-replace ordering via the new test.
  - `03-RESEARCH.md` §Pattern 1 (Atomic Write) describes the wrong order — see RESEARCH.md correction note below.

- **D-18: Post-parse semantic validation — `_validate_loaded_state(state)` raises `ValueError` on missing required keys.** *(extends D-05; resolves consensus concern #1, 2026-04-21 reviews-revision pass)*
  Rationale: D-05 (corrupt = `JSONDecodeError` only) plus D-15 (record_trade raises on bad shape) imply state schema mismatches should also RAISE — bug-surfacing posture, not silent recovery. Gemini's "fill missing keys with defaults" alternative would mask code-side bugs that drop required keys on save (the same risk D-05 was designed to prevent for parse errors). Per D-05's spirit, the right resolution is RAISE.
  **Concretely:** After `_migrate(state)` in `load_state`, call `_validate_loaded_state(state)`. Helper checks `set(state.keys()) >= REQUIRED_KEYS` where `REQUIRED_KEYS = {'schema_version', 'account', 'last_run', 'positions', 'signals', 'trade_log', 'equity_history', 'warnings'}`. On mismatch raise `ValueError(f'state missing required keys: {sorted(missing)}')`. Do NOT route through corruption recovery (D-05 narrow catch is preserved) — raise propagates to caller (orchestrator handles).
  **Affected:** 03-PLAN.md (Wave 2 — same plan that owns load_state's corruption branch). Add `_validate_loaded_state` private helper + `test_load_state_valid_json_missing_keys_raises_value_error` in TestLoadSave (or new TestSchemaValidation).

- **D-19: `_validate_trade` extends to all 11 D-15 fields with explicit type checks.** *(extends D-15; resolves consensus concern #2, 2026-04-21 reviews-revision pass)*
  Rationale: D-15 says "raises ValueError on missing/wrong fields" but the original implementation only validates `instrument`, `direction`, `n_contracts`. Reviewers correctly flag the remaining 8 fields can silently corrupt trade_log. Extension closes that gap.
  **Concretely:** `_validate_trade` adds (after the existing checks):
    - `entry_date`, `exit_date`, `exit_reason` → `isinstance(value, str) and len(value) > 0` (non-empty string)
    - `entry_price`, `exit_price`, `gross_pnl`, `multiplier`, `cost_aud` → `isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)` (Python quirk: `isinstance(True, int)` is True — explicitly reject bool; reject NaN/+inf/-inf via `math.isfinite`)
  ValueError message names the offending field and value.
  **Affected:** 04-PLAN.md `_validate_trade` task action + AC + 4-6 new TestRecordTrade tests (representative coverage, not all 8×3 violations): `test_record_trade_raises_on_non_string_entry_date`, `test_record_trade_raises_on_empty_string_exit_reason`, `test_record_trade_raises_on_bool_for_numeric_field`, `test_record_trade_raises_on_nan_gross_pnl`, `test_record_trade_raises_on_inf_cost_aud`, `test_record_trade_raises_on_string_entry_price`. `import math` added to state_manager.py imports if not already present.

- **D-20: `record_trade` does NOT mutate caller's trade dict.** *(amends D-14 trade_log append pattern; resolves Codex MEDIUM #5, 2026-04-21 reviews-revision pass)*
  Rationale: in-place mutation as documented in 04-PLAN.md is undocumented as part of the contract. Phase 4 reusing the same dict afterwards would be surprised. Codex's suggested refactor is cleaner: append `dict(trade, net_pnl=net_pnl)` to trade_log instead of mutating `trade` then appending. Trade_log entries still carry the computed `net_pnl`; caller's input dict is preserved verbatim. Tiny code change, zero behavioral change for trade_log content, much cleaner contract for Phase 4.
  **Concretely:** Replace
  ```
  trade['net_pnl'] = net_pnl
  state['trade_log'].append(trade)
  ```
  with
  ```
  state['trade_log'].append(dict(trade, net_pnl=net_pnl))
  ```
  Caller's `trade` dict is unchanged after the call.
  **Affected:** 04-PLAN.md `record_trade` task action + AC + docstring update + new test `test_record_trade_does_not_mutate_caller_trade_dict` (asserts `'net_pnl' not in trade` after the call).

### Plan tweaks (no CONTEXT.md decision needed; recorded for traceability)

> Bucket B from REVIEWS.md — small plan-only fixes folded into the same revision pass. Listed here for cross-reference; no D-XX decision required.

- **B-1 (resolves Codex MEDIUM #4):** `_backup_corrupt` derives backup name from `path.name` rather than hardcoding `'state.json'`. In 03-PLAN.md Task 1, `backup_name = f'{path.name}.corrupt.{ts}'`. Tests still assert `state.json.corrupt.<ts>` for the canonical path (path.name == 'state.json').
- **B-2 (resolves Codex MEDIUM #6):** Backup-name collision hardening — change ISO-second timestamp `'%Y%m%dT%H%M%SZ'` to ISO-microsecond `'%Y%m%dT%H%M%S_%fZ'` in `_backup_corrupt`. Eliminates same-second collision risk. Update TestCorruptionRecovery filename-pattern assertion to allow the longer suffix (now matches `state.json.corrupt.20260421T093045_123456Z`).
- **B-3 (resolves Codex LOW #8):** Document `load_state(missing file)` contract in 02-PLAN.md `load_state` task action + docstring: "If the state file does not exist, returns fresh state from `reset_state()` but does NOT persist it. The orchestrator must explicitly call `save_state(state)` to materialize state.json on first run."
- **B-4 (resolves Codex LOW #9):** `update_equity_history` minimal validation — in 04-PLAN.md `update_equity_history` task action, add `if not isinstance(date, str) or len(date) != 10: raise ValueError(...)` and `if not math.isfinite(equity): raise ValueError(...)`. Add corresponding TestEquityHistory tests.
- **B-5 (resolves Gemini LOW):** Document `MAX_WARNINGS = 100` rationale in 03-PLAN.md `append_warning` task action + docstring: "MAX_WARNINGS = 100 is intentionally conservative for v1 daily-cadence (~5 months of warnings if 1/day). A bad-day loop generating 50+ warnings still fits; chronic high-warning regimes should bump the constant in system_params.py rather than expanding the contract here."

### RESEARCH.md correction

> The `03-RESEARCH.md` §Architecture Patterns §Pattern 1 (Atomic Write with Cleanup-on-Failure) describes the durability sequence as `write → flush → fsync(file) → close → fsync(parent dir) → os.replace`. **This ordering is wrong for durability.** The correct canonical idiom (locked into the planner via D-17 above) is:
>
> `write → flush → fsync(file) → close → os.replace → fsync(parent dir)`
>
> Reason: parent-directory fsync's purpose is to make the rename durable on disk; fsync'ing BEFORE the replace makes the not-yet-renamed temp-file's directory entry durable but leaves the rename itself only in the OS write cache. Atomicity (no torn writes) is preserved by either order — only durability against power loss AFTER the rename differs. RESEARCH.md should be treated as corrected by D-17 wherever it says "fsync parent dir before os.replace"; the planner has authority over the spec at this point.

### Claude's Discretion

- **Schema version mechanism**: Use `schema_version: int = 1` (top-level int counter, not semver). Migration dict pattern in state_manager.py: `MIGRATIONS = {1: lambda s: s}` (no-op at v1; future migrations land as `MIGRATIONS[2] = lambda s: ...`). On `load_state()`, walk migrations from `state['schema_version']` to current, applying each transform. Auto-migrate forward (recommended for forward-only schema evolution); refusing-on-mismatch is overly defensive for a single-operator system. Save bumps schema_version to current.
- **Test strategy**: Mirror Phase 1/2 patterns — `tests/test_state_manager.py` with classes `TestLoadSave`, `TestAtomicity`, `TestCorruptionRecovery`, `TestRecordTrade`, `TestEquityHistory`, `TestReset`, `TestWarnings`, `TestSchemaVersion`. Crash-mid-write simulated by mocking `os.replace` to raise mid-call, then asserting original state.json is intact. No determinism snapshot — state.json is a moving target, not an oracle artifact.
- **State file location**: Repo root (`./state.json`) per SPEC.md FILE STRUCTURE. Already in `.gitignore` per SPEC. GitHub Actions workflow will commit it to a tracking branch per Phase 7 — that's deferred.
- **AST blocklist extension**: Extend `tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent` to cover `state_manager.py` with the same forbidden-imports list (signal_engine, sizing_engine, notifier, dashboard, main, requests) — but allow `system_params` (for the `Position` TypedDict and `MAX_WARNINGS` constant). state_manager.py CAN import: stdlib (json, os, tempfile, datetime, pathlib, math), system_params. State_manager IS the I/O hex — it's the one module allowed to do filesystem I/O.
- **Type hints**: Public API fully typed with `dict[str, Any]` returns + named arg types. Internal helpers use explicit types where it helps readability. `Position` TypedDict from `system_params.py` is the typed shape for positions inside state['positions'].
- **JSON formatting on save**: `json.dumps(..., sort_keys=True, indent=2, allow_nan=False)` — sorted keys for git-friendly diffs; indent=2 for readability; allow_nan=False because state should never contain NaN (would be a bug).
- **Date format**: ISO `YYYY-MM-DD` per CLAUDE.md conventions. `last_run` and warning dates are date-only (no time component); `state.json.corrupt.<ts>` backup uses ISO 8601 basic format with time + microseconds + Z (`20260421T093045_123456Z` per B-2) for filename uniqueness.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 3 requirements & success criteria
- `.planning/REQUIREMENTS.md` §Persistence — STATE-01 (top-level keys), STATE-02 (atomic writes), STATE-03 (corruption backup), STATE-04 (schema version), STATE-05 (record_trade), STATE-06 (update_equity_history), STATE-07 (reset_state)
- `.planning/ROADMAP.md` §Phase 3 — Goal + 5 success criteria + dependency declaration ("parallelable with Phases 1–2")

### Project-level functional spec (with overrides documented)
- `SPEC.md` §state_manager.py — function signatures (`load_state`, `save_state`, `record_trade`, `update_equity_history`); state.json structure example. **SUPERSEDED by D-01** for inactive position representation (now `None`, not `{active: false}`); **SUPERSEDED by D-02** for derived fields (trail_stop and unrealised_pnl are NOT persisted)
- `SPEC.md` §FILE STRUCTURE — state.json at repo root, gitignored
- `SPEC.md` §`--reset` flag — confirms reset_state behaviour for orchestrator wire-up (Phase 4)

### Phase 2 upstream (LOCKED — Phase 3 consumes these)
- `.planning/phases/02-signal-engine-sizing-exits-pyramiding/02-CONTEXT.md` D-08 — `Position` TypedDict (the canonical shape for `state['positions'][instrument]` when active)
- `.planning/phases/02-signal-engine-sizing-exits-pyramiding/02-CONTEXT.md` D-13 — cost-split convention (Phase 3 record_trade applies the closing half, mirroring Phase 2's compute_unrealised_pnl opening half)
- `.planning/phases/02-signal-engine-sizing-exits-pyramiding/02-CONTEXT.md` D-19 — account mutation is Phase 3's job; Phase 2 uses input account, doesn't mutate
- `system_params.py` — `Position` TypedDict (D-08), `SPI_COST_AUD = 6.0`, `AUDUSD_COST_AUD = 5.0`, `SPI_MULT = 5`, `AUDUSD_NOTIONAL = 10000` (used by record_trade for cost split)
- `sizing_engine.py` `step()` and `_close_position` docstrings — describe the `closed_trade` payload Phase 4 will hand to record_trade

### Phase 1 upstream (relevant cross-phase)
- `.planning/phases/01-signal-engine-core-indicators-vote/01-CONTEXT.md` D-13 — test layout pattern (one test file, multiple classes)
- `.planning/phases/01-signal-engine-core-indicators-vote/01-VERIFICATION.md` — what Phase 1 actually delivers + accepted deviations (referenced for AST blocklist extension pattern in Phase 2 was inspired here)

### Project-wide conventions
- `CLAUDE.md` §Operator Decisions — atomic state.json writes (tempfile + fsync + os.replace), `Australia/Perth` TZ for any user-facing dates
- `CLAUDE.md` §Conventions — log prefix `[State]`, ISO date format
- `CLAUDE.md` §Architecture — hexagonal-lite: state_manager.py is the I/O hex; signal_engine and sizing_engine are pure-math hexes; they do NOT import each other; main.py orchestrates

### AST blocklist precedent
- `tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent` — Phase 1+2 AST blocklist; Phase 3 extends this list to cover `state_manager.py` with appropriate allow-list (system_params OK; signal_engine/sizing_engine/notifier/dashboard/main NOT OK)

### Reviews-revision pass (2026-04-21)
- `.planning/phases/03-state-persistence-with-recovery/03-REVIEWS.md` — Cross-AI review (Gemini LOW · Codex MEDIUM, 8 actionable items). Source for D-17..D-20 amendments and B-1..B-5 plan tweaks.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `system_params.py::Position` (D-08 from Phase 2) — the canonical TypedDict shape for `state['positions'][instrument]` when active. state_manager.py imports it and uses it as the typed shape.
- `system_params.py` constants — `SPI_COST_AUD = 6.0`, `AUDUSD_COST_AUD = 5.0`, `SPI_MULT = 5`, `AUDUSD_NOTIONAL = 10000` — record_trade reads these for cost split (D-14).
- `sizing_engine.py` `_close_position` already produces a `ClosedTrade` dataclass with most of the fields record_trade needs (`direction`, `entry_price`, `exit_price`, `n_contracts`, `realised_pnl`, `exit_reason`, `exit_date`). Phase 4 orchestrator will project this dataclass into the dict shape record_trade expects (D-15).
- `tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent` AST guard pattern — Phase 3 extends this to cover state_manager.py per Claude's Discretion above.
- `tests/test_sizing_engine.py` test class structure (TestSizing/TestExits/TestPyramid/TestTransitions/TestEdgeCases/TestStep) — Phase 3 mirrors with TestLoadSave/TestAtomicity/TestCorruptionRecovery/TestRecordTrade/TestEquityHistory/TestReset/TestWarnings/TestSchemaVersion.
- `tests/regenerate_*.py` scripts (Phase 1/2) — pattern for offline data generation scripts; Phase 3 doesn't need a regenerator (state files are runtime artifacts, not committed test fixtures).

### Established Patterns

- **Hexagonal-lite hex separation:** state_manager.py is the I/O hex; signal_engine and sizing_engine are pure-math hexes. They do NOT import each other. Enforced by AST blocklist (extended per Claude's Discretion).
- **2-space indent, single quotes, snake_case** per CLAUDE.md, with PEP 8 via `ruff check` (not `ruff format`).
- **Log prefix `[State]`** for state_manager.py stderr lines per CLAUDE.md §Conventions.
- **ISO YYYY-MM-DD dates** in user-facing fields (last_run, equity_history entries, warning entries). Time-aware ISO 8601 basic format only for filename uniqueness on corrupt backups.
- **Test classes per dimension** mirroring Phase 1+2 — one test file (`tests/test_state_manager.py`), multiple classes by concern.
- **Constants live in `system_params.py`** per Phase 2 D-01 — Phase 3 adds `INITIAL_ACCOUNT = 100_000`, `MAX_WARNINGS = 100`, `STATE_FILE = 'state.json'`, `STATE_SCHEMA_VERSION = 1` (or wherever the planner decides — these are policy constants).
- **No max(1, …) defensive flooring** — operator preference; Phase 3 should never silently clamp inputs. Validate or fail.

### Integration Points

- **Upstream from Phase 2:** state_manager consumes the `Position` TypedDict (D-08) and the cost constants (D-13). Read at module-import time from `system_params`.
- **Downstream to Phase 4 (orchestrator):** Phase 4 calls `load_state()` → `save_state(state)` → `record_trade(state, trade)` → `update_equity_history(state, date, equity)` → `append_warning(state, source, msg)` → `reset_state()`. State_manager.py is the I/O boundary the orchestrator pivots around.
- **Downstream to Phase 5 (notifier):** Phase 5 reads `state['warnings']` (filtered to last 24h per D-12) for the daily email body. Phase 5 reads `state['equity_history']` for the email's P&L line. State_manager itself doesn't render — just stores.
- **Downstream to Phase 6 (dashboard):** Phase 6 reads state.json directly (per SPEC.md), renders trail_stop/unrealised_pnl as transient computed values (per D-02). State_manager doesn't expose render helpers.
- **Sibling Phase 7 (deployment):** GitHub Actions commits state.json to a tracking branch after each daily run. State_manager doesn't know about deployment — just produces the file.

</code_context>

<specifics>
## Specific Ideas

- **Single test file (`tests/test_state_manager.py`)** organised into dimension-named classes — same pattern as Phase 1 and Phase 2. The class taxonomy itself doubles as documentation of what state_manager guarantees.
- **Crash-mid-write test uses mock-os.replace-raises** — patch `os.replace` to raise `OSError` mid-call, then assert that:
  1. `state.json` on disk is bytewise-equal to the pre-call snapshot
  2. The tempfile (`state.json.tmp.<pid>` or similar) is left behind for forensics OR cleaned up — picker's call (cleanup is friendlier; leaving it is debuggable)
- **Corruption recovery test** writes garbage to state.json (`b'\x00\xff\x00not json'`), calls load_state(), asserts: returned state matches reset_state() output AND `state.json.corrupt.<ts>` backup exists in same dir AND `state['warnings']` contains a recovery entry with `source='state_manager'`.
- **Schema migration test** writes a state.json with `schema_version: 1`, calls load_state(), asserts the no-op migration ran (state unchanged) and `state['schema_version']` is current. When v2 migration is added in a future phase, this test extends to cover the v1→v2 transform.
- **append_warning bound test** appends 105 warnings, asserts `len(state['warnings']) == 100` and the FIRST 5 (oldest) are dropped (FIFO).
- **record_trade closing-cost test** constructs a trade with `gross_pnl=1000.0`, `n_contracts=2`, `cost_aud=6.0` (SPI). Asserts: `state['account']` increased by `1000 - (6.0 * 2 / 2) = 994.0`, AND trade entry in trade_log has `net_pnl=994.0`, AND `positions['SPI200'] is None`.
- **Hexagonal-lite test** extends Phase 1's AST blocklist test to assert state_manager.py imports only stdlib + system_params — no signal_engine, no sizing_engine, no notifier, no dashboard, no requests.

</specifics>

<deferred>
## Deferred Ideas

### Phase 5 (notifier) — uses Phase 3's outputs
- **Email warning rendering rule** — Phase 3 stores all warnings (D-11 bound); Phase 5 filters to last-24h (D-12). The exact rendering format (table? bullet list? collapse if empty?) is Phase 5's call.
- **Email failure → warning** — when Resend send fails, Phase 5 should call `state_manager.append_warning(state, 'notifier', '...')`. Wire-up belongs to Phase 5.

### Phase 4 (orchestrator) — calls Phase 3's API
- **`signals` dict population** — Phase 4 orchestrator calls `signal_engine.get_signal(df)` per instrument and writes `state['signals'][instrument] = result` BEFORE invoking Phase 2 step(). Phase 3 just initialises the dict shape per D-03.
- **`last_run` mutation** — Phase 4 orchestrator sets `state['last_run'] = today_iso` once per run. Phase 3 doesn't auto-set; it's the orchestrator's decision when to mark the run complete.
- **closed_trade → trade dict projection** — Phase 4 orchestrator translates `sizing_engine.ClosedTrade` dataclass into the dict shape `record_trade` expects (D-15). Trivial mapping but explicitly Phase 4's responsibility.
- **Equity computation** — Phase 4 sums `step_result.unrealised_pnl` across active positions, adds `state['account']`, passes the total to `update_equity_history(state, date, equity)`.

### Phase 6 (dashboard) — reads state.json
- **Display of derived fields (trail_stop, unrealised_pnl)** — dashboard recomputes these from state + indicators (per D-02). Dashboard is not Phase 3's concern; Phase 3 just persists the canonical Position dict.
- **Warnings panel in dashboard** — same all-or-recent question as email; dashboard can show a different filter (e.g., last 7 days). Defer.

### Phase 7 (deployment / scheduling)
- **GitHub Actions workflow committing state.json** — separate concern; Phase 3 just produces the file. The commit-back-to-branch flow is Phase 7's job.
- **Multi-branch merge conflicts on state.json** — if the workflow ever runs on multiple branches simultaneously (it shouldn't, but...), state.json conflicts. Out of scope.

### v2 schema (future milestone)
- **Multi-instrument dynamic position keys** — current state.json positions has fixed keys SPI200 + AUDUSD. v2 might support arbitrary instrument lists. Migration hook (D-04 success criterion / Claude's Discretion above) prepares the structure.
- **Trade log compression / archival** — trade_log grows unbounded. v2 might rotate to monthly files or compress old entries.
- **State schema validation library** (jsonschema) — overkill for v1; we hand-validate top-level keys in load_state's "is this state present and valid" check (D-18 hand-rolls this for v1).

### Out-of-Scope Capabilities (mentioned but not Phase 3)
- **Encrypting state.json** — single-operator local file system; no PII. Not needed in v1.
- **Multi-process locking on state.json** — single daily run; no concurrent writers. Not needed in v1.

</deferred>

---

*Phase: 03-state-persistence-with-recovery*
*Context gathered: 2026-04-21 via `/gsd-discuss-phase 3` — 16 decisions locked across 4 areas (D-01..D-16)*
*Amended: 2026-04-21 via `/gsd-plan-phase 3 --reviews` — added D-17..D-20 + B-1..B-5 from cross-AI review (Gemini LOW · Codex MEDIUM)*
*Next step: `/gsd-plan-phase 3` (revision pass updates 03-01..04-PLAN.md and 03-VALIDATION.md)*
