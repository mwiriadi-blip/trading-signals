# Phase 14: Trade Journal — Mutation Endpoints — Context

**Gathered:** 2026-04-25
**Status:** Ready for planning
**Last revised:** 2026-04-25 (REVIEWS pass)

> **2026-04-25 revision note:** Schema migration corrected to **v2 → v3** throughout
> (current `STATE_SCHEMA_VERSION` in `system_params.py` is 2; Phase 14 bumps to 3).
> Stale `v3 → v4` / `_migrate_v3_to_v4` references in `<canonical_refs>` were
> swept and replaced. REVIEWS MEDIUM #5 fix.
>
> Additional REVIEWS-driven changes baked in:
> - HIGH #1 (lost-update race): D-13 amended to require a `state_manager.mutate_state(mutator, path)`
>   helper that holds `fcntl.LOCK_EX` across the full READ-MODIFY-WRITE critical
>   section — not just the save. See revised D-13 below.
> - HIGH #2/#3 (HTMX response shape + cancel topology): per-instrument rows are
>   now wrapped in `<tbody id="position-group-{instrument}">`; close-success
>   returns empty body + `HX-Trigger: positions-changed` header (NOT a `<div>`
>   banner that would land as a direct child of `<tbody>`).
> - HIGH #4 (auth-secret in HTML): `dashboard.html` on disk emits a literal
>   `{{WEB_AUTH_SECRET}}` placeholder; the GET / handler substitutes the real
>   secret at request time so the on-disk artifact never carries it.
> - MEDIUM #6: D-15 added — `manual_stop` is **display-only in Phase 14**.
>   `check_stop_hit` (daily loop) continues to use the computed trailing stop.
> - MEDIUM #7: pyramid-gate ATR is read from
>   `state['signals'][instrument]['last_scalars']['atr']` (verified shape via
>   `main.py:1225`), not `state['signals'][instrument]['atr']`.

<domain>
## Phase Boundary

Add three POST endpoints — `/trades/open`, `/trades/close`, `/trades/modify` — that let the operator record executed trades through HTMX-driven forms in the existing dashboard. Every mutation flows through `state_manager.mutate_state()` (the new lock-around-load-mutate-save helper introduced by Plan 14-02; see D-13). v1.0 sole-writer invariant for `state['warnings']` is preserved (no endpoint touches `state['warnings']` directly — only `state_manager.append_warning` writes there).

This phase introduces a **second writer** to `state.json` (the daily signal loop being the first), which requires explicit write coordination and an amendment to Phase 10 D-15 ("web is read-only").

**Phase 14 requirements (6):** TRADE-01 (POST /trades/open), TRADE-02 (request validation + 400 on invalid), TRADE-03 (POST /trades/close + record_trade), TRADE-04 (POST /trades/modify), TRADE-05 (HTMX forms in dashboard), TRADE-06 (sole-writer invariant).

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

- **D-02: Pyramid gate uses `sizing_engine.check_pyramid`.** When pyramid-up applies, handler calls `sizing_engine.check_pyramid(position, current_price=request.entry_price, atr=...)`. ATR comes from `state['signals'][instrument]['last_scalars']['atr']` — the canonical shape produced by `main.py:1225` (the daily loop writes `state['signals'][state_key] = {'signal': …, 'last_scalars': scalars, 'last_close': …, …}` per Phase 6 D-05 + G-2 revision; `scalars['atr']` lives inside `last_scalars`). REVIEWS MEDIUM #7: the older draft of this decision read `state['signals'][instrument]['atr']` which does NOT exist on disk — fixed to nested `['last_scalars']['atr']`. If `should_add: true` → increment n_contracts and pyramid_level (capped at MAX_PYRAMID_LEVEL=2), recompute peak/trough as needed, save. If `should_add: false` (price hasn't moved enough OR already at MAX_PYRAMID_LEVEL) → 409 Conflict with reason from check_pyramid output. Keeps v1.0 risk discipline intact.

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

- **D-09: New `manual_stop: float | None` field added to `Position` TypedDict (system_params.py).** Schema migration required: **v2 → v3** in `state_manager._migrate_*` (post-research correction 2026-04-25 — current `STATE_SCHEMA_VERSION` in `system_params.py` is 2, not 3 as initially assumed). New `_migrate_v2_to_v3(state)` walks `state['positions']` and adds `manual_stop: None` to each Position dict; bumps `STATE_SCHEMA_VERSION` to 3. When `manual_stop` is set, `sizing_engine.get_trailing_stop` returns it instead of computing from peak/trough. When `None`, falls back to computed trailing stop (existing v1.0 behavior preserved). Tests for: (a) v1.0 positions without `manual_stop` field still load and behave identically (migration backfills None); (b) precedence — `manual_stop` overrides computed; (c) clearing — POST `{new_stop: null}` resets to None and reverts to computed.

- **D-10: `new_contracts` mutable up/down; `pyramid_level` resets to 0 on ANY successful modify** (REVIEWS LOW #9). Operator semantic: modify is "starting fresh from this position's perspective". Pyramid history remains in `trade_log` (no data loss). Future pyramid-up via `/trades/open` operates from a known clean state. Validation: `new_contracts >= 1` (else 400). No upper bound (operator may exceed initial sizing — their call). **Implementation rule (REVIEWS LOW #9 fix):** the `pos['pyramid_level'] = 0` assignment lives OUTSIDE the `if 'new_contracts' in req.model_fields_set` block — it fires on `new_stop`-only modifies too, matching the spec ("any modify").

- **D-11: Atomic single save_state.** Apply both new_stop and new_contracts updates in-memory, validate, then persist exactly once via the `mutate_state` critical section (D-13). If validation fails on either field, 400 returned, NO save. Either both succeed or both rejected.

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

- **D-13 (REVISED 2026-04-25, REVIEWS HIGH #1): `state_manager.mutate_state(mutator, path)` holds `fcntl.LOCK_EX` across the entire READ-MODIFY-WRITE critical section.** `fcntl.flock` around `save_state` ALONE serializes the WRITE but not the READ-MODIFY-WRITE — two writers can both `load → mutate → save` from the same pre-lock snapshot, both serialize the write, and the second save clobbers the first's mutation (lost-update race). Plan 14-02 introduces a new public helper:

  ```python
  import fcntl, os
  from pathlib import Path
  from typing import Callable

  def mutate_state(mutator: Callable[[dict], None], path: Path = Path(STATE_FILE)) -> dict:
    '''Phase 14 D-13 + REVIEWS HIGH #1: lock around the full READ-MODIFY-WRITE.

    Provides the load → mutate → save critical section as a single atomic unit
    for any caller (web POST handlers, daily loop). Without this wrapper,
    fcntl on save_state alone admits stale-read lost updates: two writers can
    both load the same pre-mutation snapshot, both acquire+release the save
    lock, second clobbers first.

    Reentrancy note: fcntl.flock is reentrant within a single process. The
    inner save_state's lock acquisition is a no-op at the kernel level when
    the outer mutate_state lock is already held. Cross-process safety is
    preserved (separate file descriptors).
    '''
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
    try:
      fcntl.flock(fd, fcntl.LOCK_EX)
      try:
        state = load_state(path=path)
        mutator(state)
        save_state(state, path=path)
        return state
      finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
      os.close(fd)
  ```

  The inner `save_state` STILL acquires its own `fcntl.LOCK_EX` (Plan 14-02's original change is preserved as defense-in-depth) — `fcntl.flock` is reentrant within a single process, so the inner lock acquisition is a kernel no-op when the outer `mutate_state` lock is already held. Cross-process safety is unchanged.

  Lock timeout: NONE — block indefinitely. Daily save is ~50ms; web POST is ~10–100ms; mutate_state critical section is ~150ms worst case. If the lock ever exceeds 5 seconds, something is fundamentally wrong (zombie process holding lock).

  Web POST handlers (Plan 14-04) and the daily loop in `main.py` BOTH call `mutate_state` instead of bare `load_state` + `save_state`. The daily loop's W3 invariant ("2 saves per run") is preserved — `mutate_state` is called twice per run (once for the main update, once for warning flush) — verified by extending the existing W3 regression test.

  **Threat status:** T-14-01 (lost-update race) is now FULLY MITIGATED (was: ACCEPTED RESIDUAL).

- **D-14: Phase 10 D-15 ("web is read-only on state.json") is explicitly amended by Phase 14 D-13.** The amendment text in Phase 14 CONTEXT.md (this file):

  > Phase 10 D-15 stated "web unit is READ-ONLY on state.json; signal loop is sole writer". This was correct for Phases 11–13 (web only served `/healthz` and `GET /` / `GET /api/state` — pure reads). **As of Phase 14, D-15 is amended:** the web layer becomes a second writer to state.json via `/trades/{open,close,modify}` endpoints. Cross-writer coordination is enforced by Phase 14 D-13 (`mutate_state` helper holds fcntl exclusive lock across the entire read-modify-write critical section). The signal loop and the web layer are equal peers from a write-correctness standpoint; both block on the same OS-level lock. The "sole-writer invariant for `state['warnings']`" (TRADE-06) remains intact — only `state_manager.append_warning` writes to that key, and no Phase 14 endpoint calls it.

- **D-15 (NEW 2026-04-25, REVIEWS MEDIUM #6): `manual_stop` is DISPLAY-ONLY in Phase 14.**

  Scope:
  - `sizing_engine.get_trailing_stop` honors `manual_stop` (Plan 14-03 — used by dashboard for the displayed Trail Stop value).
  - `dashboard._compute_trail_stop_display` mirrors that precedence (Plan 14-05) so the operator sees the override on the dashboard.
  - **`sizing_engine.check_stop_hit` does NOT honor `manual_stop`.** The daily loop (`main.run_daily_check`) continues to use the v1.0 computed trailing stop (peak − 3·atr_entry for LONG; trough + 2·atr_entry for SHORT) for exit-detection. Setting `manual_stop` via `/trades/modify` changes what the dashboard SHOWS but does NOT change when the daily loop will exit.
  - Plan 14-03 docs this in the `check_stop_hit` docstring; Plan 14-05's manual-badge tooltip uses copy "(manual; dashboard only)" so the operator sees the scope.
  - Phase 15 candidate: align `check_stop_hit` with `manual_stop` for behavioral consistency (deferred — see Deferred Ideas).

- **HTMX response shape and error display (Claude's Discretion below) — planner picks reasonable defaults.**

### Claude's Discretion

- **HTMX partial response shape and per-instrument tbody grouping.** Each instrument's row is wrapped in a dedicated `<tbody id="position-group-{instrument}">` (multiple `<tbody>` elements in one `<table>` is valid HTML5). All open / close-form / modify-form / cancel handlers target this `<tbody>` with `hx-swap="innerHTML"` so confirmation rows + cancel rows + final result rows are SINGLE-tbody-level swaps — no orphaned panels, no invalid `<div>`-as-child-of-`<tbody>` shapes (REVIEWS HIGH #2 + #3). Close-success returns empty body + `HX-Trigger: positions-changed` event header; the dashboard's per-tbody `hx-trigger="positions-changed from:body"` listens for the event and refreshes via a `?fragment=position-group-{instrument}` GET / partial.

- **Auth header in HTMX forms — server-rendered placeholder discipline (REVIEWS HIGH #4).**
  - `dashboard.html` on disk emits the literal placeholder `{{WEB_AUTH_SECRET}}` inside the form's `hx-headers` attribute — the actual secret is NEVER written to disk in the rendered HTML cache.
  - The GET / handler in `web/routes/dashboard.py` substitutes the placeholder with the real `WEB_AUTH_SECRET` env value at request time and returns the resulting bytes.
  - Tests assert: (a) `Path('dashboard.html').read_text()` contains the literal `{{WEB_AUTH_SECRET}}` and does NOT contain the real secret value, (b) the TestClient response body contains the real secret in `hx-headers`, (c) the literal `{{WEB_AUTH_SECRET}}` does NOT leak into the response body.
  - **New threat T-14-15 (auth secret leak via on-disk dashboard.html) is mitigated by this placeholder-substitution discipline (HIGH severity, MITIGATED).**

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
  - **D-15 amended by Phase 14 D-14** (this phase) — web is no longer read-only; coordination via fcntl-locked `mutate_state` helper per D-13
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
  - W3 — invariant: 2 saves per run for main.py. Phase 14's web-side mutate_state calls are SEPARATE from main.py's run-save accounting; main.py's two calls migrate from `save_state` to `mutate_state` per D-13 — same count, locked critical section.

### Source files touched by Phase 14
- `web/routes/trades.py` (NEW) — three POST handlers + three GET HTMX support handlers
- `web/app.py` (MODIFIED) — register `web.routes.trades` alongside existing dashboard + state routes; install RequestValidationError handler
- `web/routes/dashboard.py` (MODIFIED) — GET / handler substitutes `{{WEB_AUTH_SECRET}}` placeholder at request time per D-14 (REVIEWS HIGH #4); supports `?fragment=position-group-{instrument}` query param for HX-Trigger refresh
- `dashboard.py` (MODIFIED) — `render_dashboard` adds open form + per-tbody-grouped position rows + manual badge + confirmation banner slot; emits literal `{{WEB_AUTH_SECRET}}` placeholder in `hx-headers`
- `state_manager.py` (MODIFIED) — `save_state` acquires fcntl exclusive lock per D-13; new public `mutate_state(mutator, path)` helper holds the lock across load → mutate → save (REVIEWS HIGH #1); new schema migration `_migrate_v2_to_v3` adds `manual_stop` field per D-09
- `main.py` (MODIFIED — Plan 14-02) — daily loop's `save_state` calls migrate to `mutate_state(mutator)` so the daily run holds the lock across its load → mutate → save; W3 invariant (2 saves per run) preserved
- `system_params.py` (MODIFIED) — Position TypedDict adds `manual_stop: float | None` per D-09; STATE_SCHEMA_VERSION bumped 2 → 3
- `sizing_engine.py` (MODIFIED) — `get_trailing_stop` honors `manual_stop` override per D-09; `check_stop_hit` does NOT honor `manual_stop` per D-15 (display-only scope)
- `tests/test_web_trades.py` (NEW) — endpoint contract tests (open, close, modify; validation; pyramid-up; conflict; lock contention; tbody topology; placeholder substitution)
- `tests/test_state_manager.py` (MODIFIED) — fcntl lock + `mutate_state` cross-process tests
- `tests/test_sizing_engine.py` (MODIFIED) — manual_stop precedence tests
- `tests/test_dashboard.py` (MODIFIED) — per-tbody grouping + manual badge + placeholder-not-leaking tests
- `tests/test_system_params.py` (MODIFIED if present) — Position TypedDict shape test

### Architectural invariants (do not break)
- `CLAUDE.md` §Architecture — hex-lite. `web/routes/trades.py` may import: fastapi, stdlib, `state_manager` (now read+write), `sizing_engine` (for `check_pyramid` per D-02), `system_params` (for instrument constants). NOT `signal_engine`, `notifier`, `main`, `dashboard`. The `sizing_engine` import is NEW for the web tier — verify the existing AST forbidden-imports test allows it (it should — sizing_engine is pure-math, web is adapter, both can be imported into web).
- `CLAUDE.md` §Conventions — 2-space indent, single quotes, snake_case, `[Web]` log prefix on all web log lines.
- v1.0 sole-writer invariant for `state['warnings']` — ONLY `state_manager.append_warning` writes there. NO Phase 14 endpoint touches `state['warnings']` directly. AST test required (TRADE-06): walk `web/routes/trades.py` and assert no expression references `state['warnings'] =`, `state['warnings'] += [...]` (AugAssign — REVIEWS LOW #8), or `.append/.extend/.insert` on it.

### Schema migration scope
The Position TypedDict change (D-09) requires:
- A new `_migrate_v2_to_v3` function in `state_manager.py` that walks `state['positions']` and adds `manual_stop: None` to each Position dict
- A bump in the migration chain in `_migrate`
- A bump of the on-disk `schema_version` field (2 → 3)
- An update to v1.0 fixtures in `tests/test_state_manager.py` if any embed Position dicts directly (likely yes — re-run after migration to confirm test data still loads)

This migration must be backward-compatible: existing droplet state.json files (v2) must load cleanly and gain `manual_stop: None` on each Position automatically.

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
- `system_params.Position` TypedDict — Phase 14 D-09 adds `manual_stop: float | None` field. Backward-compatible migration via `_migrate_v2_to_v3`.
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
- `state_manager.mutate_state` — NEW Phase 14 helper; web routes + main.py daily loop both go through it for full READ-MODIFY-WRITE atomicity.
- `state_manager._migrate` — extends with `_migrate_v2_to_v3` for `manual_stop` field per D-09.
- `dashboard.py::render_dashboard` — extends to include HTMX forms (Claude's Discretion structure).
- `web/routes/dashboard.py::GET /` handler — extends to substitute `{{WEB_AUTH_SECRET}}` placeholder at request time per D-14 + REVIEWS HIGH #4.

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

- **Phase 15 candidate: `check_stop_hit` honors `manual_stop`.** Per D-15, Phase 14's `manual_stop` is display-only — the daily loop continues to use the v1.0 computed trailing stop for exit-detection. A Phase 15 follow-up could align `check_stop_hit` so that operator overrides also drive automated exits, eliminating the dashboard-vs-loop divergence. Out of scope for Phase 14 (TRADE-04 spec is mutation endpoint correctness, not exit-detection re-design).

### Reviewed Todos (not folded)
None — `gsd-sdk query todo.match-phase 14` returned zero matches.

</deferred>

---

*Phase: 14-trade-journal-mutation-endpoints*
*Context gathered: 2026-04-25*
*Last revised: 2026-04-25 (REVIEWS pass — see top of file for sweep summary)*
