# Phase 3: State Persistence with Recovery - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in `03-CONTEXT.md` — this log preserves the alternatives considered.

**Date:** 2026-04-21
**Phase:** 03-state-persistence-with-recovery
**Areas discussed:** Position schema + field set, Crash & corruption recovery, `warnings` field design, `record_trade` boundaries

---

## Position schema + field set

### Q1: How should an inactive (flat) position be represented in state.json positions[instrument]?

| Option | Description | Selected |
|--------|-------------|----------|
| None when flat (Recommended) | positions['SPI200'] = None when flat; full Position dict per D-08 when active. Matches Phase 2 step() returning position_after=None on close. Cleanest type contract: bool(state['positions']['SPI200']) tells you if active. | ✓ |
| {active: false} per SPEC literal | positions['SPI200'] = {'active': false} when flat; full dict + active=true when active. Matches SPEC.md as written but introduces a status flag that conflicts with Phase 2's None convention. Requires translating between Phase 2 Position dict and state shape. | |
| Always Position dict, n_contracts=0 means flat | Position field always present with all D-08 fields populated (entry_price stays at last close on flatten). Simplifies typing but bleeds stale entry data after a close. Worst option for forensic clarity. | |

**User's choice:** None when flat (Recommended)

### Q2: Should `trail_stop` and `unrealised_pnl` be persisted in state.json positions, or recomputed each daily run?

| Option | Description | Selected |
|--------|-------------|----------|
| Don't persist — recompute (Recommended) | State stores Position-shaped dict per D-08 only. trail_stop is recomputed each run via get_trailing_stop(); unrealised_pnl via compute_unrealised_pnl(). Single source of truth — no cache invalidation, no schema drift between Phase 2 D-08 and state. Dashboard reads them transiently. | ✓ |
| Persist both as cached convenience | State stores Position fields + trail_stop + unrealised_pnl. save_state recomputes and writes both each call. Dashboard / email reads pre-computed values directly. Cost: cache must be invalidated on every state mutation; SPEC and D-08 drift formally reconciled. | |
| Persist trail_stop only | Persist trail_stop (cheap to compute, useful for dashboard 'stop at $X' display). Unrealised_pnl always recomputed (depends on current_price which mutates between calls). Hybrid — minor inconsistency but pragmatic. | |

**User's choice:** Don't persist — recompute (Recommended)

### Q3: What should `signals` (top-level dict) contain after reset_state()?

| Option | Description | Selected |
|--------|-------------|----------|
| {SPI200: 0, AUDUSD: 0} — FLAT for both (Recommended) | Matches CLAUDE.md FLAT=0 convention. Pre-populated for both instruments so orchestrator doesn't have to handle missing keys. Type contract is consistent: signals[instrument] is always int in {-1, 0, 1}. | ✓ |
| Empty {} — orchestrator populates | reset_state writes signals: {}. First daily run populates each instrument as it's processed. Cost: orchestrator + dashboard need defensive .get() defaults. | |
| {SPI200: None, AUDUSD: None} — no signal yet | Explicit 'no signal computed yet' sentinel. Differentiates first run from FLAT vote. Cost: type becomes int \| None throughout the system; defensive checks needed. | |

**User's choice:** {SPI200: 0, AUDUSD: 0} — FLAT for both (Recommended)

### Q4: How should `update_equity_history` compute equity given equity = account + sum(unrealised)?

| Option | Description | Selected |
|--------|-------------|----------|
| Accept equity as caller-computed input (Recommended) | Signature: update_equity_history(state, date, equity). Orchestrator uses Phase 2 compute_unrealised_pnl (already in step() result) and passes the total. Keeps state_manager.py as pure I/O hex — no sizing_engine import. Hexagonal-lite preserved. | ✓ |
| state_manager imports compute_unrealised_pnl | Signature: update_equity_history(state, date, current_prices, multipliers, costs). state_manager imports compute_unrealised_pnl from sizing_engine and iterates open positions. Cost: BREAKS hexagonal-lite — state_manager hex now depends on sizing hex. | |
| Pass current_prices dict, compute via inline stub | Signature: update_equity_history(state, date, current_prices). state_manager has its own simplified PnL stub. Cost: dual-maintenance — PnL formula now lives in two places (sizing_engine + state_manager). Drift risk. | |

**User's choice:** Accept equity as caller-computed input (Recommended)

---

## Crash & corruption recovery

### Q1: What counts as 'corrupt' for the purposes of triggering STATE-03 (backup + reinitialise)?

| Option | Description | Selected |
|--------|-------------|----------|
| JSON parse error only (Recommended) | load_state() catches json.JSONDecodeError → backup + reinit. Schema mismatches (missing keys, wrong types) raise as bugs because they indicate code-vs-state divergence the operator should know about. Narrow definition; keeps recovery surgical. | ✓ |
| JSON parse error + missing required top-level keys | Catches both file truncation/garbage AND partial-write cases where the JSON is valid but truncated mid-object. Adds a required-keys check (schema_version, account, last_run, positions, signals, trade_log, equity_history, warnings). Slightly broader recovery surface. | |
| JSON parse error + schema_version mismatch + missing keys + type mismatches | Maximum recovery surface. Any 'this state file doesn't look right' triggers backup + reinit. Cost: hides real bugs (e.g., a code-side typo that drops a required key on save) by silently nuking state. Risky. | |

**User's choice:** JSON parse error only (Recommended)

### Q2: Where should the .corrupt.<timestamp> backup file go?

| Option | Description | Selected |
|--------|-------------|----------|
| Same dir as state.json (Recommended per SPEC literal) | state.json.corrupt.20260421T093045Z next to state.json. Matches STATE-03 literal text. Visible in `ls`, easy to inspect manually. Cost: clutters root dir if recovery happens often. | ✓ |
| .backups/state.json.corrupt.<ts> subdir | Auto-created .backups/ subdir keeps root clean. Slightly nicer for repos with many backups. Cost: deviates from SPEC.md literal; adds a directory creation step. | |
| Configurable via env var, default same dir | STATE_BACKUP_DIR env var with fallback to state.json's parent. Most flexible. Cost: extra config surface that's probably never tuned in this single-operator project. | |

**User's choice:** Same dir as state.json (Recommended per SPEC literal)

### Q3: Should a corruption-recovery event surface anywhere beyond the [State] log line?

| Option | Description | Selected |
|--------|-------------|----------|
| Append to `warnings` field (Recommended) | load_state() appends {date, source: 'state_manager', message: 'recovered from corruption; backup at state.json.corrupt.20260421T093045Z'} to the freshly-initialised state.warnings list. Surfaces in the daily email per Phase 5. Operator sees it next morning. No silent recoveries. | ✓ |
| Log line only (with [State] prefix) | stderr [State] WARNING corruption recovered, backup at <path>. Operator sees only if checking GitHub Actions logs. Email/dashboard remain silent. | |
| Log + warnings + dashboard banner | Log line + warnings field + dashboard renders a red banner if state.warnings has any entries from the last 24h. Most visible. Cost: dashboard logic + extra coupling for an edge case. | |

**User's choice:** Append to `warnings` field (Recommended)

### Q4: How should `save_state()` handle a crash between tempfile.write and os.replace (STATE-02 atomicity)?

| Option | Description | Selected |
|--------|-------------|----------|
| tempfile.NamedTemporaryFile + fsync + os.replace (Recommended) | Standard atomic-write pattern: write to state.json.tmp.<pid>, fsync the file, fsync the parent directory, then os.replace(tmp, state.json). os.replace is atomic on POSIX; original survives if process dies before the replace call. Crash mid-write leaves state.json untouched. | ✓ |
| tempfile + os.replace (skip fsync) | Same flow but no fsync. Faster but doesn't guarantee durability against power loss / OS crash between write and replace. Probably fine for daily-run cadence on Replit/Actions — those environments don't lose power mid-task. | |
| Backup-original-then-overwrite | Copy state.json → state.json.bak, then overwrite state.json directly. Simpler to reason about. Cost: NOT atomic — two process-crashable steps. Crash between copy and overwrite leaves state.json possibly mid-written. | |

**User's choice:** tempfile.NamedTemporaryFile + fsync + os.replace (Recommended)

---

## `warnings` field design

### Q1: What shape should each warning entry take in state['warnings']?

| Option | Description | Selected |
|--------|-------------|----------|
| {date, source, message} (Recommended) | List of {date: 'YYYY-MM-DD', source: 'state_manager'\|'sizing_engine'\|'notifier'\|'fetch'\|'orchestrator', message: str}. Source identifies which subsystem flagged it. Date is the run date. Easy to render in email/dashboard. Easy to filter by source. | ✓ |
| {timestamp, source, level, message} | Adds ISO timestamp (not just date) and a level field ('info', 'warning', 'error'). More structured — enables filtering 'show only errors'. Cost: extra fields adoption-time, level taxonomy is yet another thing to bikeshed. | |
| Plain string list | ['recovered from corruption at 2026-04-21', 'size=0 for SPI200', ...]. Simplest. Cost: no source attribution, no easy filtering, harder to render structured. | |

**User's choice:** {date, source, message} (Recommended)

### Q2: Who writes to `warnings` and when?

| Option | Description | Selected |
|--------|-------------|----------|
| state_manager exposes append_warning(state, source, message); callers invoke (Recommended) | state_manager owns the warning append helper (validates shape, adds today's date). Phase 2 sizing-zero warnings, Phase 4 fetch/network warnings, Phase 5 email send failures, and Phase 3's own corruption-recovery message all call append_warning(state, source, msg). state_manager's only direct write is the corruption-recovery one in load_state. | ✓ |
| Each subsystem writes directly via state['warnings'].append({...}) | No helper — callers construct the dict and append. Cost: shape drift over time (someone forgets the date field, someone uses 'warning' instead of 'message'). | |
| state_manager owns it entirely — other subsystems return warnings to orchestrator, which calls | Subsystems just return their warnings list as part of their return value. Orchestrator aggregates and bulk-appends via state_manager. Cost: every Phase 2/4/5 function needs a warnings-out parameter or return tuple. | |

**User's choice:** state_manager exposes append_warning(state, source, message); callers invoke (Recommended)

### Q3: Should `warnings` be bounded (cap size) or unbounded?

| Option | Description | Selected |
|--------|-------------|----------|
| Bounded — keep last N entries, default N=100 (Recommended) | Trim oldest when len > N. 100 entries is roughly 5 months of daily runs assuming ~0-1 warnings/day. Keeps state.json small (matters for Resend email body if state is embedded). Configurable via system_params constant. | ✓ |
| Unbounded — grow forever | Never trim. Operator manually clears via reset_state() or manual edit. Cost: state.json grows; daily email may pull stale warnings; dashboard scroll list gets long. | |
| Bounded by age — drop entries older than 30 days | Time-based trim instead of count-based. More predictable for a daily-cadence system. Cost: needs current-date awareness, slight clock dependency. | |

**User's choice:** Bounded — keep last N entries, default N=100 (Recommended)

### Q4: Should the daily email (Phase 5) surface warnings, and if so which ones?

| Option | Description | Selected |
|--------|-------------|----------|
| Show warnings from last 24h only (Recommended) | Email's warnings section lists state['warnings'] filtered to today's date. Operator sees fresh issues without noise from old ones. Defer Phase 5 design but Phase 3 should support the filter naturally (date field already there). | ✓ |
| Show all warnings since reset (last N from state) | Show whatever's in state['warnings'] in full. Cost: noisy if old warnings linger; user has to scroll past resolved issues. | |
| Phase 5's call — Phase 3 just stores | Defer the rendering decision to Phase 5 entirely. Phase 3 ensures the schema supports filtering (date field present) but doesn't prescribe what email shows. Operator picks during Phase 5 design. | |

**User's choice:** Show warnings from last 24h only (Recommended)

---

## `record_trade` boundaries

### Q1: Should `record_trade()` close the corresponding position in the same call (set positions[instrument]=None)?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — record_trade owns the close (Recommended) | record_trade(state, trade) appends to trade_log AND sets positions[trade['instrument']] = None (per Area 1 None-when-flat decision) AND adjusts account by trade['net_pnl']. Single atomic state mutation. Matches the mental model 'record_trade = the trade is now in the books.' | ✓ |
| No — caller closes position separately | record_trade only appends to trade_log + adjusts account. Caller must explicitly set positions[instrument] = None before/after. Cost: two-step protocol that's easy to half-do; orchestrator must remember both. | |
| Configurable via close_position kwarg | record_trade(state, trade, close_position=True) defaults to closing. Caller can opt out (rarely useful but possible — e.g., partial pyramid close that reduces n_contracts but doesn't fully exit). Cost: extra surface for an edge case that probably shouldn't be supported in v1. | |

**User's choice:** Yes — record_trade owns the close (Recommended)

### Q2: Where does the D-13 closing-half cost get applied (Phase 2 D-13 says 'Phase 3 record_trade applies the closing half')?

| Option | Description | Selected |
|--------|-------------|----------|
| Inside record_trade — deduct cost_aud_close from net_pnl before trade['net_pnl'] is finalised (Recommended) | trade dict from caller includes gross_pnl + opening_cost_already_deducted. record_trade computes closing_cost_half = instrument_cost_aud * trade['n_contracts'] / 2 and writes trade['net_pnl'] = gross - opening_half - closing_half. Symmetric with Phase 2 compute_unrealised_pnl which deducts the opening half. Single source of truth for cost timing. | ✓ |
| Caller computes net_pnl with full cost; record_trade just stores | Orchestrator (Phase 4) computes the full net_pnl including both halves and passes trade['net_pnl'] ready to store. record_trade is dumb storage. Cost: D-13 boundary blurs — the 'half on close' rule lives in two places (Phase 2 docstring + Phase 4 orchestrator code). | |
| record_trade takes (gross_pnl, multiplier, cost_aud) and computes both halves | Most explicit signature: record_trade(state, instrument, direction, entry_*, exit_*, n_contracts, gross_pnl, multiplier, cost_aud). record_trade splits the cost itself. Cost: longer signature, more positional args. | |

**User's choice:** Inside record_trade — deduct cost_aud_close from net_pnl before trade['net_pnl'] is finalised (Recommended)

### Q3: Should `record_trade` validate the trade dict shape (required fields, types)?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — raise ValueError on missing/wrong fields (Recommended) | record_trade asserts the trade dict has all required fields (instrument, direction, entry_date, exit_date, entry_price, exit_price, n_contracts, gross_pnl, exit_reason). Wrong types or missing keys raise ValueError immediately. Catches integration bugs at the boundary; fails loudly during Phase 4 wire-up. | ✓ |
| No — trust caller, store as-is | Append whatever dict is passed. trust the orchestrator. Cost: malformed trades silently corrupt trade_log; bugs surface later (e.g., dashboard renders 'undefined' for missing exit_price). | |
| Soft validation — log warning + drop bad fields | Validate keys, log warning if anything is off, but still append after normalising. Cost: hides integration bugs; worst of both worlds. | |

**User's choice:** Yes — raise ValueError on missing/wrong fields (Recommended)

### Q4: Should `record_trade` be idempotent on accidental re-call (same trade already in trade_log)?

| Option | Description | Selected |
|--------|-------------|----------|
| No idempotency — each call appends (Recommended) | record_trade(state, trade) always appends, no dedupe. Simpler contract. Caller (orchestrator) is responsible for not calling it twice for the same close. Phase 4 orchestrator naturally calls it once per step()'s closed_trade. Risk of double-record only on explicit caller bug — catchable in code review. | ✓ |
| Idempotent by (instrument, exit_date, entry_date) tuple | Before appending, check if a trade with the same (instrument, exit_date, entry_date) is already in trade_log. If so, skip. Cost: false sense of safety — also blocks legitimate same-day re-open-then-close edge cases (rare but possible). | |
| Idempotent by trade_id (caller-supplied UUID) | record_trade requires a unique trade_id field; dedupe by it. Cost: orchestrator has to generate UUIDs; shape changes; overengineering for a single-operator daily system. | |

**User's choice:** No idempotency — each call appends (Recommended)

---

## Claude's Discretion

The user accepted Claude's discretion on the following smaller decisions (captured in CONTEXT.md `<decisions>` Claude's Discretion subsection):

- **Schema version mechanism**: int counter (1, 2, 3) + `MIGRATIONS = {1: noop}` dict pattern in state_manager.py; auto-migrate forward on load
- **Test strategy**: mirror Phase 1/2 — single test file with dimension-named classes; crash test mocks `os.replace`; corruption test writes garbage bytes
- **State file location**: repo root (`./state.json`) per SPEC.md FILE STRUCTURE; gitignored
- **AST blocklist extension**: extend Phase 1+2 `tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent` to cover state_manager.py with same forbidden list (signal_engine, sizing_engine, notifier, dashboard, main, requests) — but ALLOW system_params (for Position TypedDict + constants)
- **Type hints**: public API fully typed; Position TypedDict from system_params for positions
- **JSON formatting on save**: `sort_keys=True, indent=2, allow_nan=False` for git-friendly diffs and bug-catching
- **Date format**: ISO YYYY-MM-DD for date-only fields (last_run, warning entries); ISO 8601 basic format with time + Z for backup filename uniqueness

---

## Deferred Ideas

Captured in CONTEXT.md `<deferred>` block:

- **Phase 5 (notifier)**: warning rendering format, Resend-failure-→-warning wire-up
- **Phase 4 (orchestrator)**: signals dict population, last_run mutation, ClosedTrade → trade dict projection, equity computation
- **Phase 6 (dashboard)**: derived field display (recompute trail_stop/unrealised_pnl), warnings panel design
- **Phase 7 (deployment/scheduling)**: GitHub Actions state.json commit-back flow
- **v2 schema (future milestone)**: multi-instrument keys, trade log archival, schema validation library
- **Out of scope (v1)**: state.json encryption, multi-process locking — single-operator daily system, neither needed
