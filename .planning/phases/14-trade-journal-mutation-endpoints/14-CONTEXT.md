# Phase 14: Trade Journal — Mutation Endpoints — Context

**Gathered:** 2026-04-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Add three POST endpoints — `/trades/open`, `/trades/close`, `/trades/modify` — that let the operator record executed trades through HTMX-driven forms in the existing dashboard. Every mutation flows through `state_manager.save_state()`. v1.0 sole-writer invariant for `state['warnings']` is preserved (no endpoint touches `state['warnings']` directly — only `state_manager.append_warning` writes there).

This phase introduces a **second writer** to `state.json` (the daily signal loop being the first), which requires explicit write coordination and an amendment to Phase 10 D-15 ("web is read-only").

**Phase 14 requirements (6):** TRADE-01 (POST /trades/open), TRADE-02 (request validation + 400 on invalid), TRADE-03 (POST /trades/close + record_trade), TRADE-04 (POST /trades/modify), TRADE-05 (HTMX forms in dashboard), TRADE-06 (sole-writer invariant preserved).

**Explicitly out of scope (deferred to Phase 15):**
- Live calculator banners (per-instrument stop + pyramid display) — CALC-01..04
- Drift / reversal sentinels — SENTINEL-01..03
- Email banner integration for sentinels

**Depends on:** Phase 13 (auth middleware in place; AuthMiddleware as sole chokepoint will gate /trades/* automatically per Phase 13 D-01)

</domain>

<decisions>
## Implementation Decisions

### Area 1 — POST /trades/open

- **D-01: Position-already-exists handling.** Same direction → pyramid-up via `sizing_engine.check_pyramid` (D-02). Opposite direction → 409 Conflict with body `'instrument {X} already has an open {DIRECTION} position; close it first via POST /trades/close before opening a {NEW_DIRECTION}'`. Replace/overwrite is NEVER allowed — protects against accidental overwrite of a real position via typo.

- **D-02: Pyramid gate uses `sizing_engine.check_pyramid`.** When pyramid-up applies, handler calls `sizing_engine.check_pyramid(position, current_price=request.entry_price, atr=...)`. ATR comes from `state['signals'][instrument]['atr']` (last computed value). If `should_add: true` → increment n_contracts and pyramid_level (capped at MAX_PYRAMID_LEVEL=2), recompute peak/trough as needed, save. If `should_add: false` (price hasn't moved enough OR already at MAX_PYRAMID_LEVEL) → 409 Conflict with reason from check_pyramid output. Keeps v1.0 risk discipline intact.

- **D-03: Client may override peak_price / trough_price / pyramid_level with strict coherence checks.** All three optional in request body. Validation:
  - LONG: `peak_price >= entry_price` (else 400); `trough_price` MUST be absent or null (else 400 — it's None for LONG per Phase 2 D-08)
  - SHORT: `trough_price <= entry_price` (else 400); `peak_price` MUST be absent or null
  - `pyramid_level` MUST be int in `[0, MAX_PYRAMID_LEVEL=2]` (else 400)
  - When all three are absent (default path): peak_price = entry_price for LONG (None for SHORT), trough_price = entry_price for SHORT (None for LONG), pyramid_level = 0
  - Allows back-dating a position that's already pyramided. Strict checks prevent inconsistent state from leaking to disk.

- **D-04: Pydantic v2 model with field-level constraints; 422 → 400 remap; executed_at? optional.**
  ```python
  class OpenTradeRequest(BaseModel):
    instrument: Literal['SPI200', 'AUDUSD']
    direction: Literal['LONG', 'SHORT']
    entry_price: float = Field(gt=0)        # plus a custom validator: math.isfinite (rejects NaN, inf)
    contracts: int = Field(ge=1)
    executed_at: date | None = None         # ISO YYYY-MM-DD; default today AWST
    peak_price: float | None = None
    trough_price: float | None = None
    pyramid_level: int | None = None
  ```
  FastAPI's default 422 (Unprocessable Entity) is remapped to 400 (per SC-2: "returns HTTP 400 with field-level errors") via a custom exception handler that converts Pydantic's `RequestValidationError` to a 400 with body `{"errors": [{"field": "...", "reason": "..."}]}`. `executed_at` defaults to `datetime.now(zoneinfo.ZoneInfo('Australia/Perth')).date()` when absent.

### Area 2 — POST /trades/close

- **D-05: `gross_pnl` computed INLINE in close handler — raw price-delta formula. Anti-pitfall.**
  ```python
  # CRITICAL: gross_pnl MUST be raw price-delta, NOT realised_pnl.
  # record_trade D-14 deducts the closing-half cost; passing realised_pnl
  # (which already has half deducted by sizing_engine.compute_unrealised_pnl)
  # would double-count the closing cost. See state_manager.py:499-506,
  # Phase 4 D-15/D-19 anti-pitfall.
  if direction == 'LONG':
    gross_pnl = (exit_price - position['entry_price']) * position['n_contracts'] * multiplier
  else:  # SHORT
    gross_pnl = (position['entry_price'] - exit_price) * position['n_contracts'] * multiplier
  ```
  Inline math — no call to `sizing_engine.compute_unrealised_pnl` to avoid the realised-vs-gross confusion.

- **D-06: `exit_reason = 'operator_close'`.** Distinct literal value, hardcoded in the close handler. Differentiates from v1.0 reasons (`'signal_reversal'`, `'adx_dropout'`, `'trailing_stop_hit'`, `'manual_reset'`). Dashboard / trade_log filters can identify operator-initiated closes for UX (e.g., different row-color, audit visibility).

- **D-07: `multiplier` and `cost_aud` from `state['_resolved_contracts'][instrument]`.** `state_manager.load_state()` rematerializes `_resolved_contracts` after loading from disk (state_manager.py:394–401), so the runtime key is reliably present in any `state` dict the web handler holds. Read pattern:
  ```python
  resolved = state['_resolved_contracts'][instrument]
  multiplier = resolved['multiplier']
  cost_aud = resolved['cost_aud']
  ```
  Honors operator's tier choice (spi-mini/spi-standard/spi-full × audusd-standard/audusd-mini) without re-deriving.

- **D-08: `executed_at?` optional → default today AWST date.** Same pattern as D-04. Allows back-dating an exit (closed yesterday, journaled today). Mapped to `exit_date` in the trade dict passed to `record_trade`.

- **Close handler trade-dict construction (full 11-field set):**
  ```python
  trade = {
    'instrument': position['instrument'],            # from existing position (state lookup)
    'direction':  position['direction'],             # from existing position
    'n_contracts': position['n_contracts'],          # from existing position (full close — no partial)
    'entry_date': position['entry_date'],            # from existing position
    'exit_date':  request.executed_at or today_awst,  # D-08
    'exit_reason': 'operator_close',                  # D-06 literal
    'entry_price': position['entry_price'],          # from existing position
    'exit_price':  request.exit_price,               # from request
    'gross_pnl':   <inline raw price-delta>,         # D-05
    'multiplier':  state['_resolved_contracts'][...]['multiplier'],  # D-07
    'cost_aud':    state['_resolved_contracts'][...]['cost_aud'],    # D-07
  }
  state_manager.record_trade(state, trade)
  state_manager.save_state(state)
  ```

### Area 3 — POST /trades/modify

- **D-09: New `manual_stop: float | None` field added to `Position` TypedDict (system_params.py).** Schema migration required (v3 → v4 in `state_manager._migrate_*`). When `manual_stop` is set, `sizing_engine.get_trailing_stop` returns it instead of computing from peak/trough. When `None`, falls back to computed trailing stop (existing v1.0 behavior preserved). Tests for: (a) v1.0 positions without `manual_stop` field still load and behave identically (migration backfills None); (b) precedence — `manual_stop` overrides computed; (c) clearing — POST `{new_stop: null}` resets to None and reverts to computed.

- **D-10: `new_contracts` mutable up/down; `pyramid_level` resets to 0 on any modify.** Operator semantic: modify is "starting fresh from this position's perspective". Pyramid history remains in `trade_log` (no data loss). Future pyramid-up via `/trades/open` operates from a known clean state. Validation: `new_contracts >= 1` (else 400). No upper bound (operator may exceed initial sizing — their call).

- **D-11: Atomic single save_state.** Apply both new_stop and new_contracts updates in-memory, validate, then `save_state(state)` exactly once. If validation fails on either field, 400 returned, NO save. Either both succeed or both rejected.

- **D-12: At-least-one-field required.** Pydantic validator: at least one of `new_stop` / `new_contracts` MUST be present (or non-null). Empty modify body returns 400 with `'at least one of new_stop, new_contracts must be present'`. Prevents wasted save_state calls and operator confusion.

- **Modify request schema:**
  ```python
  class ModifyTradeRequest(BaseModel):
    instrument: Literal['SPI200', 'AUDUSD']
    new_stop: float | None = None      # null = clear override; absent = no change
    new_contracts: int | None = None
    @model_validator(mode='after')
    def at_least_one(self):
      if self.new_stop is None and self.new_contracts is None:
        raise ValueError('at least one of new_stop, new_contracts must be present')
      return self
  ```
  Distinguishing absent vs null requires `Optional[Union[float, NotProvidedSentinel]]` patterns; planner picks the cleanest Pydantic v2 approach.

### Area 4 — Write coordination with daily signal loop

- **D-13: `state_manager.save_state` acquires fcntl exclusive lock on state.json before atomic write.** Cross-process safe: both web POSTs (in the FastAPI process) and main.py's daily save (in trading-signals.service) compete for the same OS-level lock. Implementation:
  ```python
  import fcntl
  with open(path, 'r+') as f:           # open for lock; actual write goes via tempfile+os.replace
    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
    try:
      _atomic_write(json.dumps(state, ...), path)
    finally:
      pass  # lock released on file close
  ```
  Caveat: `fcntl.flock` works on POSIX (Linux/macOS); the droplet is Ubuntu (Linux) and developer machine is macOS — both supported. Windows would need `msvcrt.locking` instead but Windows is not a target.

  Lock timeout: NONE — block indefinitely. Daily save is ~50ms; web POST is ~10–100ms. Worst case overlap is sub-second. If the lock ever exceeds 5 seconds, something is fundamentally wrong (zombie process holding lock). Test: a fixture that opens an exclusive lock from another process and asserts save_state blocks → completes when lock released.

  Required regression test pass after the change: `pytest tests/test_state_manager.py -x` must remain 100% green; lock acquisition latency < 10ms in normal operation.

- **D-14: Phase 10 D-15 ("web is read-only on state.json") is explicitly amended by Phase 14 D-13.** The amendment text in Phase 14 CONTEXT.md (this file):

  > Phase 10 D-15 stated "web unit is READ-ONLY on state.json; signal loop is sole writer". This was correct for Phases 11–13 (web only served `/healthz` and `GET /` / `GET /api/state` — pure reads). **As of Phase 14, D-15 is amended:** the web layer becomes a second writer to state.json via `/trades/{open,close,modify}` endpoints. Cross-writer coordination is enforced by Phase 14 D-13 (fcntl exclusive lock in `state_manager.save_state`). The signal loop and the web layer are equal peers from a write-correctness standpoint; both block on the same OS-level lock. The "sole-writer invariant for `state['warnings']`" (TRADE-06) remains intact — only `state_manager.append_warning` writes to that key, and no Phase 14 endpoint calls it.

- **HTMX response shape and error display (Claude's Discretion below) — planner picks reasonable defaults.**

### Claude's Discretion

- **HTMX partial response shape.** Recommend per-row swap (hx-target on the affected `<tr>`) for open/close/modify success cases — minimal partial size, fast UX. Error display: inline `<div class="error">` rendered above the form on 400, with field-level error rows. Planner picks final HTML structure consistent with v1.0 dashboard.html aesthetic.

- **CSRF posture.** Phase 13 D-01 shared-secret header (`X-Trading-Signals-Auth`) acts as a CSRF token equivalent — third-party origins can't supply it, and same-origin browser POSTs include it via HTMX `hx-headers`. No additional CSRF token machinery needed for v1.1 single-operator. Document explicitly in PLAN.md.

- **Pydantic v1 vs v2 import path.** FastAPI 0.136+ uses Pydantic v2. `Field`, `BaseModel`, `model_validator` are v2 APIs. Planner verifies the installed version at planning time.

- **NotProvided sentinel for distinguishing "absent" vs "null" in modify request.** D-12 requires distinguishing "field not sent" (no change) from "field sent as null" (clear override for new_stop). Planner picks: Pydantic v2 `model_fields_set` introspection vs sentinel value vs explicit `__pydantic_fields_set__` check.

- **HTMX form HTML structure in dashboard.html.** Phase 14 modifies `dashboard.py::render_dashboard` to include three forms. Planner decides exact layout (3 separate forms vs tabbed UI vs inline-per-position-row). Recommend keeping it simple: one "open" form at top of positions section, "close" + "modify" buttons inline on each open position row.

- **Partial-close support.** Out of scope for Phase 14 per discussion (operator wanting partial close uses full-close + new-open). Document in deferred-items.md.

### Folded Todos

None — `gsd-sdk query todo.match-phase 14` returned zero matches.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents (researcher, planner, executor) MUST read these before implementing.**

### Phase spec + scope
- `.planning/ROADMAP.md` §Phase 14 — phase goal, success criteria SC-1..SC-6, dependency on Phase 13
- `.planning/REQUIREMENTS.md` — TRADE-01 (POST /trades/open), TRADE-02 (validation), TRADE-03 (POST /trades/close), TRADE-04 (POST /trades/modify), TRADE-05 (HTMX forms), TRADE-06 (sole-writer invariant)
- `.planning/PROJECT.md` §Current Milestone — HTMX or vanilla JS (no React); single-operator tool

### Prior-phase decisions that constrain Phase 14
- `.planning/phases/13-auth-read-endpoints/13-CONTEXT.md`:
  - D-01 — AuthMiddleware as sole chokepoint; /trades/* automatically gated by auth (zero per-route boilerplate)
  - D-22 — `docs_url=None, redoc_url=None, openapi_url=None` set on FastAPI app; planner inherits
- `.planning/phases/10-foundation-v1-0-cleanup-deploy-key/10-CONTEXT.md`:
  - **D-15 amended by Phase 14 D-14** (this phase) — web is no longer read-only; coordination via fcntl lock per D-13
- `.planning/milestones/v1.0-phases/02-sizing-engine-trailing-stop-pyramid/02-CONTEXT.md`:
  - D-08 — peak_price for LONG, trough_price for SHORT (None for the other direction)
  - D-09 — Position TypedDict signature (extended by Phase 14 D-09 with `manual_stop`)
  - D-12 — pyramid mechanics; check_pyramid is the gate (Phase 14 D-02 reuses)
- `.planning/milestones/v1.0-phases/03-state-manager-persistence/03-CONTEXT.md`:
  - D-13 — record_trade contract (closes via state['positions'][instrument] = None; appends to trade_log; mutates account)
  - D-14 — closing-half cost split happens INSIDE record_trade
  - D-15 — _validate_trade is the gate; raises ValueError on shape errors
  - D-19 (extended Phase 4) — gross_pnl MUST be raw price-delta, NOT realised_pnl (Phase 14 D-05 anti-pitfall)
  - D-20 — record_trade does NOT mutate caller's trade dict (returns a new state)
- `.planning/milestones/v1.0-phases/08-hardening-warning-carry-over-stale-banner-crash-email-config/08-CONTEXT.md`:
  - D-14 — underscore-prefix runtime keys auto-stripped by save_state, rematerialized by load_state. Phase 14 reads `state['_resolved_contracts']` post-load.
  - W3 — invariant: 2 saves per run for main.py. Phase 14's web-side save_state calls are SEPARATE from main.py's run-save accounting.

### Source files touched by Phase 14
- `web/routes/trades.py` (NEW) — three handlers: open, close, modify
- `web/app.py` (MODIFIED) — register `web.routes.trades` alongside existing dashboard + state routes
- `dashboard.py` (MODIFIED) — `render_dashboard` adds three HTMX forms (per Claude's Discretion structure)
- `state_manager.py` (MODIFIED) — `save_state` acquires fcntl exclusive lock per D-13; new schema migration v3→v4 adds `manual_stop` field per D-09
- `system_params.py` (MODIFIED) — Position TypedDict adds `manual_stop: float | None` per D-09
- `sizing_engine.py` (MODIFIED) — `get_trailing_stop` honors `manual_stop` override per D-09; tests added
- `tests/test_web_trades.py` (NEW) — endpoint contract tests (open, close, modify; validation; pyramid-up; conflict; lock contention)
- `tests/test_state_manager.py` (MODIFIED) — fcntl lock regression tests
- `tests/test_sizing_engine.py` (MODIFIED) — manual_stop precedence tests
- `tests/test_system_params.py` (MODIFIED if present) — Position TypedDict shape test

### Architectural invariants (do not break)
- `CLAUDE.md` §Architecture — hex-lite. `web/routes/trades.py` may import: fastapi, stdlib, `state_manager` (now read+write), `sizing_engine` (for `check_pyramid` per D-02), `system_params` (for instrument constants). NOT `signal_engine`, `notifier`, `main`, `dashboard`. The `sizing_engine` import is NEW for the web tier — verify the existing AST forbidden-imports test allows it (it should — sizing_engine is pure-math, web is adapter, both can be imported into web).
- `CLAUDE.md` §Conventions — 2-space indent, single quotes, snake_case, `[Web]` log prefix on all web log lines.
- v1.0 sole-writer invariant for `state['warnings']` — ONLY `state_manager.append_warning` writes there. NO Phase 14 endpoint touches `state['warnings']` directly. AST test required (TRADE-06): walk `web/routes/trades.py` and assert no expression references `state['warnings'] =` or `.append` on it.

### Schema migration scope
The Position TypedDict change (D-09) requires:
- A new `_migrate_v3_to_v4` function in `state_manager.py` that walks `state['positions']` and adds `manual_stop: None` to each Position dict
- A bump in the migration chain in `_migrate`
- A bump of the on-disk `schema_version` field
- An update to v1.0 fixtures in `tests/test_state_manager.py` if any embed Position dicts directly (likely yes — re-run after migration to confirm test data still loads)

This migration must be backward-compatible: existing droplet state.json files (v3) must load cleanly and gain `manual_stop: None` on each Position automatically.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable assets
- `state_manager.save_state(state, path)` — atomic tempfile+fsync+os.replace; Phase 14 D-13 wraps with fcntl lock. The `_atomic_write` helper at line 113 is the candidate for the lock-protected critical section.
- `state_manager.record_trade(state, trade)` — the existing close primitive. 11-field validation already in `_validate_trade` (state_manager.py:199–265). Phase 14 close handler constructs the 11-field dict per D-05/D-06/D-07/D-08, then calls record_trade unchanged.
- `state_manager.load_state(path, now)` — rematerializes `_resolved_contracts` per Phase 8 D-14 (state_manager.py:394–401). Phase 14 reads `state['_resolved_contracts'][instrument]` reliably after every load.
- `sizing_engine.check_pyramid(position, current_price, atr)` — pure-math gate for pyramid-up (Phase 14 D-02). Returns `PyramidDecision` with `should_add: bool` and reason metadata.
- `sizing_engine.get_trailing_stop(position, ...)` — Phase 14 D-09 modifies this to honor `manual_stop` override.
- `dashboard.render_dashboard(state, out_path, now)` — Phase 14 modifies the rendered HTML to include three HTMX forms (Claude's Discretion structure).
- `system_params.Position` TypedDict — Phase 14 D-09 adds `manual_stop: float | None` field. Backward-compatible migration via `_migrate_v3_to_v4`.
- `system_params.SPI_CONTRACTS` and `AUDUSD_CONTRACTS` — per-tier multiplier and cost dicts. Already consumed by `state_manager.load_state`'s `_resolved_contracts` materialization. Phase 14 reads via `state['_resolved_contracts']` (D-07).

### Established patterns
- **Local imports inside handlers** — Phase 11 C-2 + Phase 13 carry-forward. `web/routes/trades.py` handlers import `state_manager`, `sizing_engine`, `system_params` LOCALLY inside handler bodies, not at module top.
- **Pydantic v2 idioms** — FastAPI 0.136+ uses Pydantic v2. `BaseModel`, `Field`, `Literal`, `model_validator(mode='after')` are the v2 APIs. Confirmed available via the existing `requirements.txt` pin.
- **`[Web]` log prefix** — established Phase 11; reuse for all new log lines.
- **Test file naming** — `tests/test_web_<route>.py`. Phase 14 adds `tests/test_web_trades.py`. Mirrors Phase 13's `tests/test_web_auth_middleware.py` etc.
- **Hex-boundary AST guard** — `tests/test_web_healthz.py::TestWebHexBoundary.FORBIDDEN_FOR_WEB` enforces. Phase 14 verifies `sizing_engine` and `system_params` are NOT in the forbidden list (they shouldn't be — they're pure-math, adapter can import).

### Integration points
- `web/app.py::create_app()` — Phase 14 calls `web.routes.trades.register(application)` alongside existing healthz/dashboard/state route registrations.
- `state_manager.save_state` — single chokepoint for the fcntl lock per D-13. All callers (main.py and web routes) get coordination for free.
- `state_manager._migrate` — extends with `_migrate_v3_to_v4` for `manual_stop` field per D-09.
- `dashboard.py::render_dashboard` — extends to include HTMX forms (Claude's Discretion structure).

</code_context>

<specifics>
## Specific Ideas

- **Pyramid-up via /trades/open is operator-initiated.** The endpoint TRUSTS the operator's price input (no real-time market lookup) but APPLIES the v1.0 risk gate (`check_pyramid` requires price ≥ entry + level×ATR). If the operator says "I pyramided at 7900" but check_pyramid says "no, gate is at 7950", the endpoint returns 409. Operator can override only by closing the position and opening fresh.

- **Anti-pitfall comment in D-05's gross_pnl computation is mandatory.** Future maintainers WILL be tempted to call `compute_unrealised_pnl` and forget the closing-cost double-deduction. The inline comment must explicitly cite Phase 4 D-15/D-19 and `state_manager.py:499-506` for context.

- **`manual_stop` field is opt-in.** Existing v1.0 positions without the field still work — the migration backfills None, and `get_trailing_stop` falls back to the computed peak/trough trailing stop. Operator never sees `manual_stop` unless they POST /trades/modify {new_stop: ...}.

- **fcntl lock blocks indefinitely.** D-13 chose no-timeout because daily save is ~50ms and web POSTs are ~100ms — overlap windows are sub-second. A 5-second timeout would be defensive but would expose web users to sporadic 503s during edge cases. Block-and-wait is simpler and aligns with "single operator, single droplet" reality.

- **Error response shape — JSON for 4xx, HTMX partial for 200/201.** Field-level 400 errors return JSON `{"errors": [{"field": "...", "reason": "..."}]}` so HTMX clients can `hx-on:after-request` populate inline error rows. 200 success responses return HTMX partials (per Claude's Discretion).

- **/trades/modify doesn't add to trade_log.** It mutates an open position; no closed trade is recorded. Different from /trades/close which appends to trade_log. Document explicitly in PLAN.md to prevent confusion during testing.

- **`pyramid_level` reset on modify (D-10) means v1.0 trade_log retains pyramid history.** Operator always sees the full pyramid arc in trade_log even though the in-memory `pyramid_level` resets — pyramid history is a closed-trade audit, not an open-position state.

</specifics>

<deferred>
## Deferred Ideas

- **Partial-close support.** Phase 14 only models full closes (entire `n_contracts` of a position closed in one POST). Partial close — close 1 of 3 contracts at price X — would require either: (a) extending record_trade to accept a partial n_contracts and update position rather than zero it, or (b) modeling a partial close as `record_trade(full)` + `open(remaining)`. v1.2 candidate if operator workflow demands it.

- **Live calculator banners and drift sentinels.** CALC-01..04 + SENTINEL-01..03 → Phase 15. Phase 14's modify endpoint sets up the data substrate (manual_stop) but doesn't render any calculator UX.

- **Rate-limit on /trades/* at nginx layer.** Phase 12 only added rate-limit to /healthz; Phase 13 noted /api/state and / should also get rate-limited; Phase 14 should extend to /trades/*. If planner doesn't include in this phase, mark as Phase 16 hardening.

- **Audit log of mutations.** Currently every successful mutation lands in trade_log (for /trades/close) or modifies position (for /trades/open and /trades/modify). A separate audit log capturing operator IP, timestamp, request body hash, and the specific change applied would help forensic review. Out of scope for v1.1; Phase 13 D-01..D-06 already audit auth FAILURES — successful mutations are visible via state.json + trade_log diff over time.

- **Multi-position per instrument.** v1.0 architecture assumes one position slot per instrument. Phase 14 preserves this. v2.0 would require a fundamental schema change (state['positions'][instrument] becomes a list, not a single dict).

- **Operator-supplied exit_reason.** Phase 14 D-06 hardcodes `'operator_close'`. v1.2 could allow `{exit_reason: 'profit_target' | 'stop_loss' | 'hedge_unwind' | 'free_text'}` for richer trade journaling.

- **WebSocket broadcast of state changes.** A Phase 14 mutation only updates state.json; the dashboard re-renders on next GET / (or HTMX partial swap). Multi-tab dashboards would benefit from server-push via WebSocket. v1.2+ if multi-device usage emerges.

- **HTMX form HTML structure decisions.** Punted to Claude's Discretion — recommend per-row inline buttons for close/modify, top-of-section form for open. Planner finalizes layout matching v1.0 aesthetic.

- **NotProvided sentinel for distinguishing "absent" vs "null" in PATCH-style modify.** D-12 mentions; planner picks the cleanest Pydantic v2 approach (likely `model_fields_set` introspection).

### Reviewed Todos (not folded)
None — `gsd-sdk query todo.match-phase 14` returned zero matches.

</deferred>

---

*Phase: 14-trade-journal-mutation-endpoints*
*Context gathered: 2026-04-25*
