---
phase: 14
reviewers: [gemini, codex]
skipped_reviewers: [claude]
skip_reason: "Running inside Claude Code — claude CLI skipped for independence"
reviewed_at: 2026-04-25
plans_reviewed:
  - 14-01-PLAN.md
  - 14-02-PLAN.md
  - 14-03-PLAN.md
  - 14-04-PLAN.md
  - 14-05-PLAN.md
---

# Cross-AI Plan Review — Phase 14: Trade Journal — Mutation Endpoints

## Gemini Review

### Summary
High-quality, architecturally consistent plans that strictly follow the hexagonal-lite discipline and Phase 14's unique constraints. The coordination of cross-process writes via `fcntl` and the lockstep parity between the math and rendering engines are particularly well-handled.

### Strengths
- **Lockstep Parity (D-09):** Plan 14-03 and 14-05 ensure `sizing_engine` and `dashboard.py` implement identical `manual_stop` precedence and NaN guards, backed by a bit-identical parity test.
- **Cross-Process Coordination (D-13):** The `fcntl.flock` implementation correctly targets the destination file to handle the `os.replace` inode-swap behavior (verified by the Pattern 9 argument).
- **Type-Safe Validation:** Comprehensive Pydantic v2 usage with `model_fields_set` for PATCH semantics and a global 422→400 remap satisfies ASVS V5 requirements.
- **Static Invariants (TRADE-06):** The AST-walk test in Plan 14-04 provides a robust, automated guard against accidental writes to `state['warnings']` from the web tier.
- **Defensive Reads (Pitfall 5/7):** Consistent use of `.get('manual_stop')` and pre-migration backfilling ensures the daily signal loop survives the deployment transition.

### Concerns
- **MEDIUM — Orphaned Confirmation Row:** In Plan 14-05, clicking "Close" swaps a position `<tr>` for two `<tr>` blocks (original + panel). The `Confirm close` button targets `#position-row-{inst}`. If the response is empty (success), it deletes the first row but leaves the panel row orphaned in the DOM.
- **LOW — Sole-Writer Check Completeness:** Plan 14-04's AST test (Pattern 10) checks `Assign` and `Call`. It may miss `AugAssign` (e.g., `state['warnings'] += [new_err]`).
- **LOW — Pyramid Reset Scope:** Decision D-10 states pyramid resets to 0 on *any* modify, but the handler only resets it if `new_contracts` is present. If only `new_stop` is modified, the pyramid level is currently preserved — handler/spec inconsistency.

### Suggestions
- HTMX grouping: wrap each instrument's position data in its own `<tbody id="position-group-{instrument}">` so handlers can target the group and replace the whole `<tbody>` (avoids orphan rows entirely).
- AST guard extension: add `ast.AugAssign` branch to `TestSoleWriterInvariant`.
- D-10 clarification: move `pos['pyramid_level'] = 0` outside the `new_contracts` conditional in `modify_trade`.

### Risk Assessment
**LOW** — Plans are surgical and respect v1.0 durability/security standards. The `fcntl` serialization makes the second-writer introduction safe. Remaining refinements are minor.

---

## Codex Review

### Summary
The plan set is detailed, internally cross-referenced, and generally disciplined on D-01..D-13, T-14-0x, and test-first rollout. The main weakness is not validation or schema work; it is **write correctness and HTMX response shape**. As written, the second-writer story is only partially solved, and several proposed partial responses in `14-04-PLAN.md` will produce invalid or non-reversible DOM swaps.

### Strengths
- Wave structure is mostly sound: 14-01 scaffolds, 14-02/14-03 unblock schema + pure-math, 14-04/14-05 split routes vs rendering cleanly.
- D-05 anti-pitfall is handled explicitly and repeatedly. The plan correctly forbids `compute_unrealised_pnl` in close flow.
- D-12 absent-vs-null is treated correctly with Pydantic v2 `model_fields_set`.
- TRADE-06 well defended: AST checks for `state['warnings']` are appropriate.
- `fcntl` guidance locks the destination file, not the tempfile — right inode to coordinate on.
- v2 fixture + round-trip migration tests are the right backward-compat shape.
- Plan 14-01 promotes BOTH `sizing_engine` AND `system_params` out of `FORBIDDEN_FOR_WEB`.
- Plan 14-05 parity test against `sizing_engine.get_trailing_stop` prevents UI drift.
- HTMX SRI pin is exact and consistently propagated.

### Concerns
- **HIGH — `fcntl` around `save_state()` does not prevent stale-read lost updates** (14-02-PLAN / D-13 / T-14-01). Two writers can still `load → mutate → save` from the same pre-lock snapshot and clobber each other. The lock serializes the WRITE but not the READ-MODIFY-WRITE critical section. Correctness bug, not just accepted residual risk.
- **HIGH — Plan 14-04 close-success partial returns banner HTML for `outerHTML` on a `<tr>`.** `_render_close_success_partial` returns a `<div>` banner; HTMX swaps it into `#position-row-{instrument}` (a `<tr>`). Result: invalid table DOM (`<div>` direct child of `<tbody>`).
- **HIGH — Plan 14-04 close/modify form/cancel topology orphans rows.** The cancel flow targets `#position-row-{instrument}` but the swap introduces TWO rows (original + confirmation panel). Cancel only restores the original; the panel row is left dangling.
- **HIGH — Plan 14-05 `_render_open_form()` doesn't emit `hx-headers` with `X-Trading-Signals-Auth`.** Locked architecture (Phase 13 D-01) requires shared-secret header on all non-/healthz routes. As written, browser POSTs will 401. Plan vaguely mentions "browser extension/proxy injects it" — out of scope and contradicts UI-SPEC.
- **MEDIUM — Schema version inconsistency.** D-09 and 14-02 say `v2 → v3`, but `canonical_refs` section in CONTEXT.md still references `_migrate_v3_to_v4` and "existing droplet state.json files (v3)". Will leak into implementation/tests if not normalized.
- **MEDIUM — `check_stop_hit()` ignores `manual_stop`** in Plan 14-03 (intentional per scope). Display logic and exit-detection logic diverge — if operator sets a manual stop, dashboard shows it but the signal loop won't actually exit on it. Material behavioral footgun.
- **MEDIUM — Plan 14-04 reads `state['signals'][instrument]['atr']` for pyramid gate** but other plans/test snippets show `signals` as ints (LONG=1/SHORT=-1/FLAT=0). Fixture shape inconsistency — needs reconciliation.
- **LOW — Global `RequestValidationError` remap** (Plan 14-04) — tests should assert it doesn't accidentally change existing `/api/state` / `/` behavior beyond status remap on malformed inputs.
- **LOW — Plan 14-05 parity coverage is `LONG manual / LONG none / SHORT manual`** — missing `SHORT none` case for full 4-case lockstep.

### Suggestions
- **Fix the writer race** by moving from "lock on save" to "lock around load-mutate-save". Introduce `state_manager.mutate_state(mutator, path)` helper:
  ```python
  def mutate_state(mutator, path=Path(STATE_FILE)):
    with _locked_state_file(path):
      state = load_state(path=path)
      mutator(state)
      save_state(state, path=path)
      return state
  ```
  Then `/trades/open|close|modify` AND the daily loop both use `mutate_state(...)`.

- **Fix close-success HTMX response shape.** For row-targeted close, return either:
  1. Empty string + `HX-Trigger: positions-changed` event so a tbody-level listener rebuilds, OR
  2. A valid replacement `<tr>` only.
  
  NOT a `<div>` banner inside outerHTML on a `<tr>`.

- **Fix close/modify form/cancel swap topology.** Use a wrapper target that can legally contain both rows (`<tbody id="position-group-{instrument}">` per gemini's suggestion), or replace the original row with a single `<tr><td colspan="9">...</td></tr>` panel only — then cancel cleanly restores one row.

- **Fix `hx-headers` rendering.** Either:
  1. Render `hx-headers='{"X-Trading-Signals-Auth": "<server-injected-secret>"}'` from server config (planner picks how — likely a per-request rendered template variable), or
  2. Move header injection to a documented JS bootstrap that reads from a non-secret session source.

- **Normalize schema-version wording across all plans:**
  - Pick one: `STATE_SCHEMA_VERSION 2 → 3`
  - Rename every reference to `_migrate_v2_to_v3`
  - Remove all `v3 → v4` text from `canonical_refs` and prose

- **Add the missing parity case** in Plan 14-05:
  ```python
  # Case 4: SHORT manual_stop None → computed trough + 2*atr
  ```

- **State `manual_stop` Phase 14 scope explicitly.** If display-only (no impact on `check_stop_hit`), say so bluntly in plan + UI copy. Otherwise operators will assume `/trades/modify` changes actual stop-hit behavior.

### Risk Assessment
**MEDIUM-HIGH** — Validation, migration, and test strategy are strong, but two issues are substantial: cross-process lost-update gap despite `fcntl`, and invalid HTMX/table swap shapes in 14-04. Implementation-level failure modes can corrupt operator state or break the UI even if unit tests are otherwise thorough. Fix those first; rest of the plan is solid.

---

## Consensus Summary

### Agreed Strengths (mentioned by both reviewers)
- D-09 lockstep parity between `sizing_engine.get_trailing_stop` and `dashboard._compute_trail_stop_display`
- `fcntl` locks the destination file (correct inode under `os.replace` semantics)
- Pydantic v2 `model_fields_set` for D-12 absent-vs-null
- TRADE-06 sole-writer AST guard is the right approach
- Plan 14-01 promotes BOTH `sizing_engine` and `system_params` out of `FORBIDDEN_FOR_WEB`
- HTMX SRI hash pinned exactly

### Agreed Concerns

**HIGH severity (codex caught; gemini missed two of these):**

1. **Cross-process lost-update race despite fcntl** — `fcntl` on save_state alone doesn't serialize the load-mutate-save critical section. Two writers can both load the same snapshot, both acquire-and-release the lock to save, and the second save clobbers the first's mutation. Need `mutate_state(mutator, path)` wrapper that holds the lock across the full READ-MODIFY-WRITE.
2. **Close-success HTMX response returns invalid DOM** — `_render_close_success_partial` returns a `<div>` banner for outerHTML swap on a `<tr>`. Result: `<div>` becomes a direct child of `<tbody>` — invalid table HTML.
3. **Cancel-row swap topology orphans rows** — confirmation panel is added as a second `<tr>`; cancel restores the original but leaves the panel row in the DOM. (Gemini caught as MEDIUM; codex as HIGH.)
4. **Browser HTMX POSTs will 401** — `_render_open_form()` doesn't emit `hx-headers` with `X-Trading-Signals-Auth`. Phase 13 D-01 locks shared-secret-header auth for all non-/healthz routes. Plans hand-wave with "browser extension injects it" — contradicts UI-SPEC and locked architecture.

**MEDIUM:**

5. Schema version reference inconsistency — D-09 + 14-02 say v2→v3, but `canonical_refs` still has v3→v4 references. Normalize.
6. `check_stop_hit()` ignores `manual_stop` — display vs exit-detection divergence. Material behavioral footgun if not made explicit.
7. `state['signals'][instrument]['atr']` shape vs `signals` as ints — fixture inconsistency between Plan 14-04 and other plans/tests.

**LOW:**

8. AST AugAssign gap in `TestSoleWriterInvariant` — `state['warnings'] += [...]` would slip through. (Gemini.)
9. D-10 pyramid reset scope inconsistency — handler only resets when `new_contracts` present; spec says "any modify". (Gemini.)
10. Global RequestValidationError remap — add regression test for existing `/api/state` and `/` behavior. (Codex.)
11. Parity test missing `SHORT none` 4th case — only 3 of 4 covered. (Codex.)

### Divergent Views
- **Risk level:** Gemini = LOW, Codex = MEDIUM-HIGH. Codex caught 4 HIGH issues gemini missed (the lost-update race, two HTMX response shape issues, the missing hx-headers). The MEDIUM-HIGH verdict is correct — these are real correctness gaps that would fail at runtime, not theoretical.

### Recommended Path Forward

The 4 HIGH issues + 3 MEDIUM are all addressable through targeted plan revisions, not a full replan. The structural changes:

**Architectural revision (Plan 14-02):**
- Add `mutate_state(mutator, path)` helper to `state_manager.py` with full critical-section lock
- Refactor daily loop in `main.py` to use `mutate_state` for the daily save (test surface: confirm Phase 8 W3 invariant — exactly 2 saves per run — still holds)
- Plan 14-04's three handlers all use `mutate_state` instead of `load_state` + `save_state`

**HTMX response revision (Plan 14-04 + 14-05):**
- Wrap each position group in `<tbody id="position-group-{instrument}">` so handlers target a wrapper that can legally contain multiple `<tr>` elements
- Close-success returns empty + `HX-Trigger: positions-changed` (not a `<div>` banner)
- Cancel-row targets the wrapping `<tbody>` for clean restore
- `_render_open_form()` emits `hx-headers='{"X-Trading-Signals-Auth": "<server-rendered-value>"}'` — and dashboard.py becomes auth-secret aware (server reads env, renders into HTML at request time, NOT at module load — so secret is never logged in the HTML cache)

**Doc normalization (CONTEXT.md):**
- Sweep all `v3→v4` references → `v2→v3`
- Make `manual_stop` Phase 14 scope explicit (display-only vs exit-detection)

**Two options for applying the fixes:**

**Option A — Edit plans inline** (faster if comfortable with manual edits):
1. Plan 14-02: add `mutate_state` helper task; revise fcntl scope from save-only to load-mutate-save
2. Plan 14-04: update all 3 handlers to use `mutate_state`; replace close-success response shape; fix cancel topology
3. Plan 14-05: wrap positions in `<tbody id="position-group-...">`; render `hx-headers` with auth secret server-side; add 4th parity case
4. CONTEXT.md: normalize schema-version wording; add explicit `manual_stop` scope clarification
5. Optional: Plan 14-04 AST AugAssign extension; D-10 handler/spec reconciliation

**Option B — Replan with `--reviews` flag** (cleaner audit trail, longer):
```
/gsd-plan-phase 14 --reviews
```
Re-runs the planner with REVIEWS.md as input. Plan-checker re-verifies.

**Recommendation: Option B.** The lost-update fix touches `state_manager.py` API surface (new `mutate_state` helper + main.py refactor), the HTMX topology change cascades through Plan 14-04 + 14-05, and the auth-header fix has security implications worth the planner re-threading. Manual edits risk missing a downstream consequence (e.g., Phase 8 W3 invariant in main.py, or HX-Trigger event handling in dashboard.html).
