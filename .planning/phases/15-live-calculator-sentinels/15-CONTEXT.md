# Phase 15: Live Calculator + Sentinels — Context

**Gathered:** 2026-04-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Turn the dashboard from a passive log into an active decision-support tool. Two work streams:

1. **Calculator (CALC-01..04):** Per-position rows surface trailing stop, distance-to-stop ($ and %), next pyramid trigger price, forward-looking peak stop ("if today's high reaches Z, stop rises to W"), and entry-target block when signal=LONG/SHORT but position is FLAT. All values derived from `sizing_engine` (no re-implementation; pure-math hex preserved).

2. **Sentinels (SENTINEL-01..03):** Detect drift when `state.positions` disagrees with `state.signals`. Render banner on dashboard AND in daily email (reuses Phase 8's `_has_critical_banner` classifier via a new `source='drift'` warning path). Per-instrument copy with explicit recommended action.

**Phase 15 requirements (7):** CALC-01 (per-instrument calculator row), CALC-02 (entry target when FLAT), CALC-03 (forward-look "if high reaches Z..."), CALC-04 (pyramid section), SENTINEL-01 (drift banner on dashboard), SENTINEL-02 (reversal banner — red, distinct from amber drift), SENTINEL-03 (drift banner in daily email).

**Explicitly out of scope (deferred to v1.2 or later):**
- Aligning `sizing_engine.check_stop_hit` with `manual_stop` — Phase 14 D-15 deferred; Phase 15 D-09 keeps deferred
- Yahoo intraday data fetch from web layer (forward-look uses operator-input field instead per D-05)
- Multi-position-per-instrument
- Operator-supplied exit_reason variants (Phase 14 deferred)
- Audit log of mutations beyond trade_log (Phase 14 deferred)

**Depends on:** Phase 14 (mutations live so operator's real positions drive calculator + drift detection)

</domain>

<decisions>
## Implementation Decisions

### Area 1 — Drift detection (SENTINEL-01..03)

- **D-01: Pure-math drift detector in `sizing_engine.detect_drift(positions, signals) -> list[DriftEvent]`.** New function in sizing_engine.py. Pure-math hex; takes plain args (state['positions'] dict, state['signals'] dict), returns list of `DriftEvent` dataclasses (frozen, slots=True per Phase 2 D-09 convention). DriftEvent fields:
  ```python
  @dataclasses.dataclass(frozen=True, slots=True)
  class DriftEvent:
    instrument: str          # 'SPI200' or 'AUDUSD'
    held_direction: str      # 'LONG' or 'SHORT' (from position)
    signal_direction: str    # 'LONG', 'SHORT', or 'FLAT' (from signal)
    severity: str            # 'drift' (open vs FLAT) or 'reversal' (LONG↔SHORT)
    message: str             # rendered per D-14 template — the operator-facing copy
  ```
  Reusable from main.py (signal loop), web/routes/trades.py (post-mutation refresh), and dashboard.py (live render — though dashboard reads from state['warnings'] in steady-state, see D-03).

- **D-02: Drift warnings cleared at signal-loop start AND after every mutate_state call.** New helper `state_manager.clear_warnings_by_source(state, source: str) -> dict` filters out warnings whose `source` matches. Signal loop call sequence (in main.py run_daily_check):
  ```python
  state = clear_warnings_by_source(state, 'drift')   # purge stale
  drift_events = sizing_engine.detect_drift(state['positions'], state['signals'])
  for event in drift_events:
    state = state_manager.append_warning(state, source='drift', message=event.message)
  ```
  Web mutation handlers (open/close/modify) do the same after the in-mutator state change but before save:
  ```python
  def _apply(state):
    # ... apply mutation ...
    clear_warnings_by_source(state, 'drift')
    drift_events = detect_drift(state['positions'], state['signals'])
    for event in drift_events:
      append_warning(state, source='drift', message=event.message)
  state_manager.mutate_state(_apply)
  ```
  Ensures `state['warnings']` always reflects current (positions × signals) reality.

- **D-03: Drift surfaces via `append_warning(source='drift')`; `notifier._has_critical_banner` extended.** Single source of truth = `state['warnings']`. Phase 8 classifier (notifier.py:548) extended:
  ```python
  def _has_critical_banner(state: dict) -> bool:
    if state.get('_stale_info'):
      return True
    for w in state.get('warnings', []):
      if w.get('source') == 'state_manager' and w.get('message', '').startswith('recovered from corruption'):
        return True
      if w.get('source') == 'drift':           # NEW Phase 15
        return True
    return False
  ```
  Email subject auto-gets `[!]` prefix when drift is present (existing Phase 8 behavior, no notifier subject changes). Banner body rendered via `_render_drift_banner(state)` helper invoked from `_render_header_email` and `dashboard._render_critical_banners`.

- **D-04: Missing signal data → no drift event.** If `state['signals'].get(instrument)` is None or `state['signals'][instrument]['signal']` is None, `detect_drift` skips that instrument. Conservative — don't claim drift when we don't know the signal. Test fixture covers this case.

### Area 2 — Forward-looking peak stop (CALC-03)

- **D-05: Z (today's high) is operator-input via dashboard text field.** No data fetch from yfinance, no signal-loop dependency. Per-position-row HTMX input:
  ```html
  <td class="forward-stop">
    <span>If high reaches</span>
    <input type="number" step="0.01" min="0"
           hx-get="/?fragment=forward-stop&instrument=SPI200"
           hx-trigger="input changed delay:300ms"
           hx-target="closest .w-cell"
           hx-include="this">
    <span>: stop rises to <span class="w-cell">—</span></span>
  </td>
  ```
  Operator types Z; HTMX fires `?fragment=forward-stop&instrument=X` GET; handler computes W; response replaces `.w-cell`. Phase 13 D-12 / Phase 14 fragment-GET pattern reused.

- **D-06: W computed via `sizing_engine.get_trailing_stop(synthesized_position)`.** Server handler builds a synthetic position dict:
  ```python
  pos = state['positions'][instrument].copy()
  if pos['direction'] == 'LONG':
    pos['peak_price'] = max(pos.get('peak_price') or pos['entry_price'], z_input)
  else:  # SHORT
    pos['trough_price'] = min(pos.get('trough_price') or pos['entry_price'], z_input)
  w = sizing_engine.get_trailing_stop(pos, atr=...)
  ```
  Honors `manual_stop` if set (Phase 14 D-09 precedence). Lockstep with all existing tests. ATR sourced from `state['signals'][instrument]['last_scalars']['atr']` per Phase 14 D-02 corrected shape.

- **D-07: Bit-identical parity test locks SC-3.** New `test_forward_stop_matches_sizing_engine_bit_for_bit` in tests/test_web_dashboard.py (or new tests/test_web_calculator.py if planner prefers). Cases:
  1. LONG Z>peak → W = max(peak,Z) − TRAIL_MULT_LONG×ATR matches sizing_engine
  2. LONG Z<peak (no peak update) → W stays at peak − TRAIL_MULT_LONG×ATR
  3. SHORT Z<trough → W = min(trough,Z) + TRAIL_MULT_SHORT×ATR
  4. SHORT Z>trough (no trough update) → W stays
  5. manual_stop set → W = manual_stop regardless of Z (Phase 14 D-09 honored)

- **D-08: Inline per-position-row input.** The forward-look input lives WITHIN the position row (8th or 9th column), not a separate section. Operator's eye stays on the row of interest. HTMX target = the same row's W cell. Adjacent placement to the existing trail-stop column is natural.

### Area 3 — manual_stop in check_stop_hit (Phase 14 D-15 carryover)

- **D-09: Stay deferred to v1.2.** Phase 15 does NOT modify `sizing_engine.check_stop_hit`. The function continues to use computed trailing stop (peak − TRAIL_MULT_LONG × atr for LONG, trough + TRAIL_MULT_SHORT × atr for SHORT). Operator-set `manual_stop` is honored by `get_trailing_stop` (Phase 14 D-09 — display) but NOT by `check_stop_hit` (daily-loop exit detection). Mitigations applied in this phase:
  - D-10 dashboard side-by-side display
  - Phase 14 manual badge tooltip already says "(manual; dashboard only)"
  - Forward-look display (D-05..D-08) shows the computed stop trajectory so operator sees what daily-loop will exit at
  - Deferred-items entry: "v1.2: align check_stop_hit with manual_stop. Decision: full-align vs asymmetric (only-tighten) is open — see Phase 15 discuss-log Area 3."

- **D-10: Dashboard shows side-by-side `'manual: 7700 | computed: 7950 (will close)'`.** When `manual_stop` is set on a position, the trail-stop cell renders BOTH values:
  ```html
  <td class="trail-stop">
    <span class="manual-stop">manual: 7700</span>
    <span class="separator"> | </span>
    <span class="computed-stop">computed: 7950 <em>(will close)</em></span>
  </td>
  ```
  Computed value gets `(will close)` annotation in italics. Manual value is informational only. When `manual_stop` is None, trail-stop cell shows only the computed value (existing Phase 14 D-09 + lockstep parity behavior — no change).

### Area 4 — Drift banner aggregation + email integration (SENTINEL-01..03 + SC-6)

- **D-11: One merged banner listing all drifted instruments.** Single banner aggregates events across SPI200 and AUDUSD. Severity = max severity of constituent events ('reversal' > 'drift'). Border color: `_COLOR_SHORT` (red) if any reversal, else `_COLOR_FLAT` (amber). Body lists each drifted instrument on its own line:
  ```
  Drift detected:
  • You hold LONG SPI200, today's signal is FLAT — consider closing.
  • You hold SHORT AUDUSD, today's signal is LONG — reversal recommended (close SHORT, open LONG).
  ```
  Banner header text = "Drift detected" (singular header even when multiple instruments — keeps the visual chrome simple).

- **D-12: Same wording dashboard + email; inline-CSS adapted for email.** Banner body text is shared between dashboard render path (`dashboard._render_drift_banner`) and email render path (`notifier._render_drift_banner`). Single `_format_drift_lines(events: list[DriftEvent]) -> str` helper produces the body lines; each adapter wraps with its own CSS scaffold. Lockstep parity test asserts the body text is byte-identical between the two render paths given the same DriftEvent list.

- **D-13: Banner stack hierarchy: corruption > stale > reversal > drift.** Most severe first. When multiple critical states exist:
  1. **Corruption** (`recovered from corruption` warning): gold border `_COLOR_FLAT`, label "State was reset" — most urgent (data integrity)
  2. **Stale state** (`_stale_info` transient): red border `_COLOR_SHORT`, label "Stale state" — system-health
  3. **Reversal** (any DriftEvent with severity='reversal'): red border `_COLOR_SHORT`, label "Drift detected" — live risk
  4. **Drift** (only DriftEvent with severity='drift', no reversal): amber border `_COLOR_FLAT`, label "Drift detected" — recommended action
  
  When reversal AND drift coexist, single banner uses reversal color (red). Existing Phase 8 critical banners (corruption, stale) render BEFORE the drift banner in DOM order. Email and dashboard match this ordering.

- **D-14: Per-instrument banner copy template.**
  ```python
  # In sizing_engine.detect_drift, when building DriftEvent.message:
  if signal_direction == 'FLAT':
    message = f'You hold {held_direction} {instrument}, today\'s signal is FLAT — consider closing.'
  else:  # opposite direction
    new_dir = 'SHORT' if held_direction == 'LONG' else 'LONG'
    message = (
      f'You hold {held_direction} {instrument}, today\'s signal is {signal_direction} — '
      f'reversal recommended (close {held_direction}, open {new_dir}).'
    )
  ```
  Test fixture asserts the exact rendered string for each (held_direction, signal_direction) combination. The literal `Drift detected:` header text is owned by the renderer (dashboard / notifier), not by detect_drift — keeps the pure-math hex free of presentational concerns.

### Claude's Discretion

- **Pyramid section markup (CALC-04).** The roadmap SC-4 says "level N active; next add at price P (+Y×ATR_entry)" and "new stop after add: S". Planner picks the inline display style (one-line per pyramid level or nested table). Recommend a single-line summary per row: `"Pyramid: level 1/2 — next add at 7950 (+1×ATR), new stop 7900"`. When position is at MAX_PYRAMID_LEVEL, show `"Pyramid: level 2/2 — fully pyramided"`.

- **CSS for side-by-side manual|computed display (D-10).** Planner decides exact CSS. Recommend monospace for the values + visual separator (` | ` with extra spacing), `_COLOR_TEXT_DIM` for `manual:` label and `_COLOR_TEXT` for `computed:` label, italic for `(will close)`. Keep within existing dashboard.py `_INLINE_CSS` token discipline.

- **Forward-look input default value.** When no Z is entered, what does the W cell show? Recommend showing the computed stop (i.e., as if Z = current peak/trough — no extension). Or a literal `—` placeholder until operator types. Pick whichever is calmer; recommend `—` placeholder with a hint label `"(enter high to project)"`.

- **Performance: drift recomputed on every dashboard render.** The `detect_drift` call is O(2 instruments × constant) = ~microseconds. Render-path inclusion is fine. Cache only if profiling shows budget pressure (it won't — single-operator, infrequent renders). No caching layer needed for v1.1.

- **HTMX swap target for forward-look HTMX response.** Planner picks: `hx-target="closest .w-cell"` vs explicit `#forward-stop-{instrument}-w` ID. Either works; ID is more debuggable.

- **Email banner color in inline-CSS.** Phase 8's existing banner CSS uses `_COLOR_SHORT` and `_COLOR_FLAT` constants from system_params. Planner reuses; no new colors.

### Folded Todos

None — `gsd-sdk query todo.match-phase 15` returned zero matches.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents (researcher, planner, executor) MUST read these before implementing.**

### Phase spec + scope
- `.planning/ROADMAP.md` §Phase 15 — phase goal, SC-1..SC-6 authoritative
- `.planning/REQUIREMENTS.md` — CALC-01 (per-instrument calculator row), CALC-02 (entry target FLAT), CALC-03 (forward-look), CALC-04 (pyramid section), SENTINEL-01 (drift banner dashboard), SENTINEL-02 (reversal banner red), SENTINEL-03 (drift banner email)
- `.planning/PROJECT.md` §Constraints — Determinism: "Daily signal output reproducible from state.json + Yahoo data for the same date" — Phase 15 D-09 keeps this intact by NOT changing check_stop_hit semantics

### Prior-phase decisions that constrain Phase 15
- `.planning/phases/14-trade-journal-mutation-endpoints/14-CONTEXT.md`:
  - D-02 — `sizing_engine` allowed-imported by web/ (FORBIDDEN_FOR_WEB no longer contains it); calculator import path is open
  - D-09 — `manual_stop` field on Position TypedDict; sizing_engine.get_trailing_stop honors it
  - D-13 — `mutate_state(mutator, path)` with fcntl lock; web handlers + main.py use it
  - D-15 — `manual_stop` is DISPLAY-ONLY in Phase 14; check_stop_hit unchanged. **Phase 15 D-09 keeps this deferred to v1.2.**
- `.planning/phases/13-auth-read-endpoints/13-CONTEXT.md`:
  - D-01 — AuthMiddleware sole chokepoint; Phase 15 calculator data + drift banners inherit auth
  - D-12 — fragment-GET pattern (`?fragment=...`) on GET / for partial swaps; Phase 15 forward-look HTMX reuses this
- `.planning/milestones/v1.0-phases/08-hardening-warning-carry-over-stale-banner-crash-email-config/08-CONTEXT.md`:
  - D-04 — `_has_critical_banner` classifier; Phase 15 D-03 extends with `source='drift'`
  - sole-writer-for-state['warnings'] invariant — only state_manager.append_warning writes; Phase 15 honors via D-03
- `.planning/milestones/v1.0-phases/02-sizing-engine-trailing-stop-pyramid/02-CONTEXT.md`:
  - D-09 — frozen+slots dataclass return-type convention; Phase 15 DriftEvent follows
  - get_trailing_stop / check_pyramid signatures — Phase 15 calculator reuses both unchanged

### Source files touched by Phase 15
- `sizing_engine.py` (MODIFIED) — adds `detect_drift(positions, signals) -> list[DriftEvent]`, `DriftEvent` dataclass; reuses existing `get_trailing_stop` and `check_pyramid` for calculator data; **`check_stop_hit` unchanged** per D-09
- `state_manager.py` (MODIFIED) — adds `clear_warnings_by_source(state, source: str) -> dict` helper
- `main.py` (MODIFIED) — daily loop calls clear_warnings_by_source('drift') + detect_drift + append_warning loop after sizing dispatch (per D-02 sequence)
- `web/routes/trades.py` (MODIFIED) — each handler's mutator clears + recomputes drift after position mutation (per D-02)
- `web/routes/dashboard.py` (MODIFIED) — adds `?fragment=forward-stop&instrument=X` GET handler; computes W from synthesized position per D-06
- `dashboard.py` (MODIFIED) — render_dashboard adds: per-position calculator row data (CALC-01..04); side-by-side manual|computed display (D-10); forward-look input HTMX (D-08); merged drift banner section (D-11..D-13); pyramid section markup
- `notifier.py` (MODIFIED) — `_has_critical_banner` extended for `source='drift'` (D-03); `_render_drift_banner(state)` helper added; `_render_header_email` includes drift banner per stack hierarchy (D-13)
- `tests/test_sizing_engine.py` (MODIFIED) — TestDetectDrift class (~15 tests covering all (held_direction, signal_direction) × (LONG/SHORT positions) × (FLAT/opposite signals) combinations)
- `tests/test_state_manager.py` (MODIFIED) — TestClearWarningsBySource (3-5 tests: removes matching, leaves others, idempotent on no-match, multiple sources)
- `tests/test_web_dashboard.py` (MODIFIED) — TestForwardStopFragment (5 cases per D-07); TestSideBySideStopDisplay (manual_stop set vs None)
- `tests/test_dashboard.py` (MODIFIED) — TestRenderCalculatorRow (per-instrument data); TestRenderDriftBanner (merged, hierarchy, color); TestRenderForwardLookInput (HTMX attribute markup)
- `tests/test_notifier.py` (MODIFIED) — TestDriftBanner (email body matches dashboard byte-for-byte per D-12; subject [!] prefix); TestBannerStackOrder (corruption > stale > reversal > drift per D-13)
- `tests/test_main.py` (MODIFIED) — TestDriftWarningLifecycle (warnings cleared then recomputed at signal-loop start per D-02; W3 invariant intact)

### Architectural invariants (do not break)
- `CLAUDE.md` §Architecture — hex-lite. `sizing_engine.detect_drift` stays pure-math (no I/O, no clocks, no env reads). `state_manager.clear_warnings_by_source` is a pure dict operation (no I/O — caller wraps in mutate_state for persistence). `dashboard.py` continues to import system_params + (NEW for Phase 15) sizing_engine. `web/routes/dashboard.py` adds local import of sizing_engine (already allowed per Phase 14 D-02).
- `CLAUDE.md` §Conventions — 2-space indent, single quotes, snake_case, `[Web]` log prefix on web logs, `[Sched]` log prefix on signal-loop drift detection.
- v1.0 sole-writer-for-state['warnings'] — ONLY state_manager.append_warning writes there. Phase 15 honors: detect_drift returns events; main.py / web handlers loop and call append_warning. AST test (Phase 14 TestSoleWriterInvariant) extended if needed to cover any new write surfaces (it shouldn't — drift goes through append_warning).
- v1.0 Determinism (PROJECT.md) — daily signal output reproducible from state.json + Yahoo data. Phase 15 D-09 keeps this intact (check_stop_hit unchanged); drift detection is deterministic given (positions, signals).
- Phase 8 W3 invariant — exactly 2 saves per daily run. Phase 15 D-02 inserts clear_warnings_by_source + detect_drift + append_warning sequence within run_daily_check, but these are in-memory mutations — the actual save_state count is unchanged. Test_main.py W3 invariant test must remain green.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable assets
- `sizing_engine.get_trailing_stop(position, atr)` — Phase 15 forward-look uses verbatim (D-06)
- `sizing_engine.check_pyramid(position, current_price, atr)` — Phase 15 calculator section (CALC-04) calls to compute next-add price P
- `sizing_engine.calc_position_size(...)` — Phase 15 entry-target (CALC-02) calls when signal=LONG/SHORT but position=FLAT
- `state_manager.append_warning(state, source, message)` — Phase 15 D-03 calls with source='drift'
- `notifier._has_critical_banner(state)` — Phase 15 D-03 extends with `source=='drift'` branch
- `notifier._render_header_email(state, now)` — Phase 15 inserts drift banner per D-13 hierarchy in this function (between corruption/stale and routine sections)
- `dashboard._render_critical_banners` (or equivalent) — Phase 15 inserts drift banner here, matching email's hierarchy ordering
- `system_params._COLOR_SHORT` / `_COLOR_FLAT` — reused for reversal (red) and drift (amber) banner border colors
- Phase 14 fragment-GET pattern (`?fragment=position-group-X` in `web/routes/dashboard.py`) — Phase 15 reuses for `?fragment=forward-stop&instrument=X`
- Phase 14 mutate_state mutator pattern — Phase 15 web/routes/trades.py mutators add the clear+recompute drift block

### Established patterns
- **Pure-math return-type dataclasses** — Phase 2 D-09: `@dataclasses.dataclass(frozen=True, slots=True)` for SizingDecision, PyramidDecision, ClosedTrade, StepResult. Phase 15 DriftEvent follows.
- **Local imports inside handlers** — Phase 11 C-2 carry-forward. `web/routes/dashboard.py` Phase 15 changes import sizing_engine LOCALLY inside the handler bodies (`from sizing_engine import detect_drift, get_trailing_stop` inside the `?fragment=forward-stop` handler), not at module top.
- **`[Sched]` log prefix on signal-loop activity** — Phase 1+ convention. Phase 15 main.py drift-recompute loop uses `[Sched] drift detected for {instrument}: held={dir}, signal={dir}` etc.
- **`_has_critical_banner` extension pattern** — Phase 8 already added two sources (`_stale_info`, `state_manager` corruption). Phase 15 adds a third (`drift`). Same shape: extra `or` branch in the function body.
- **Warning shape** — `{source: str, message: str, date: str}` per Phase 8 D-03. Drift warnings use `source='drift'`, `message=DriftEvent.message`, `date=run_date`.

### Integration points
- `main.py:run_daily_check` — Phase 15 inserts drift-recompute sequence between sizing dispatch (where positions are updated) and save_state (which is now mutate_state per Phase 14 D-13). Order: sizing → state['signals'] populated → clear_warnings_by_source('drift') → detect_drift → append_warning loop → mutate_state's save fires once with all updates.
- `web/routes/trades.py` mutators — each `_apply` function adds clear_warnings_by_source('drift') + detect_drift + append_warning loop after the position mutation. Atomic with the existing position mutation.
- `dashboard._render_critical_banners` (or `_render_header`) — Phase 15 adds drift banner section using `_render_drift_banner(state)` helper. Order per D-13: corruption → stale → reversal → drift. Each section conditionally rendered.
- `notifier._render_header_email` — same insertion as dashboard, mirrored for inline-CSS email layout. Lockstep parity test asserts body text is byte-identical (D-12).

</code_context>

<specifics>
## Specific Ideas

- **DriftEvent.message is the ONLY operator-facing copy that crosses the dashboard|email boundary.** Both renderers consume the same string. This guarantees lockstep parity (D-12) at the source level — no two-template-drift risk.

- **Banner border colors are FIXED to existing system_params constants.** Drift = `_COLOR_FLAT` (amber); reversal = `_COLOR_SHORT` (red). Mirrors Phase 8 stale/corruption colors. No new color tokens.

- **Forward-look input is per-row, NOT a global widget.** Operator's eye stays on the row of interest. Mirrors Phase 14's per-row close/modify button placement.

- **`(will close)` annotation in italics** for the computed stop in side-by-side display. The label tells the operator which value the daily-loop respects without requiring a tooltip read.

- **Pyramid section uses `level N/MAX_PYRAMID_LEVEL` notation** so operator sees both current and ceiling at a glance. Examples: `"Pyramid: level 0/2 — next add at 7900 (+1×ATR), new stop 7850"`, `"Pyramid: level 2/2 — fully pyramided"`.

- **Drift detection is conservative.** Missing signal data → no drift (D-04). Operator gets a "drift" banner only when there's clear evidence the signal contradicts the position. False-positive drift banners would erode trust in the system.

- **`sizing_engine.detect_drift` is independent of timeframe.** It operates on (positions, signals) — both already-extracted state values. Doesn't care if signals were computed today or 5 days ago. Caller (main.py / web/routes) is responsible for ensuring signals are current.

- **W3 invariant preservation:** Phase 15 inserts in-memory mutations only into the daily-loop sequence. The `mutate_state` call count stays at 2 (existing main.py post-Phase-14 state). Test_main.py's `test_happy_path_save_state_called_exactly_twice` (post-Phase-14 already migrated to count mutate_state calls) remains the W3 lock.

</specifics>

<deferred>
## Deferred Ideas

- **Aligning `check_stop_hit` with `manual_stop`.** Phase 14 D-15 + Phase 15 D-09: stay deferred to v1.2. When the operator wants exit-detection to honor manual_stop. Three open sub-decisions for v1.2 to lock: (a) full-align (manual_stop honored either tighter or looser), (b) asymmetric (only-tighten — manual_stop honored only when more conservative), (c) keep-deferred (manual_stop remains forever display-only). See Phase 15 14-DISCUSSION-LOG.md Area 3 for the option breakdown.

- **Yahoo intraday data fetch for forward-look.** Phase 15 D-05: operator-input field instead. v1.2 candidate if operators want hands-free forward-look. Adds yfinance call to web layer (Phase 11 contract assumption: web layer is fast & no network).

- **Banner badge for "no signal data — manual fallback" warning.** Phase 15 D-04 silently skips. v1.2 candidate to surface a yellow info banner when fetch fails.

- **Email digest of drift events over time.** Phase 15 emits per-day banner. A weekly digest of drift patterns ("you held LONG SPI200 against FLAT signal for 3 days this week") could help operator tune. v1.2+ analytics.

- **Caching detect_drift output.** Phase 15 recomputes on every dashboard render. Profile-driven optimization candidate; not needed for single-operator usage.

- **`_render_drift_banner` helper across `notifier` and `dashboard`.** Phase 15 implements two parallel functions with the same body text per D-12. Refactoring to a shared helper module (e.g., `web/_render_helpers.py` or `system_params.banners`) could centralize. v1.2 if drift banner gains complexity (e.g., per-instrument color, action buttons).

- **Audit log of historical drift events.** Phase 15 fires drift warnings into state['warnings'] and clears them at next signal run. A separate persistent log of every drift event over time would help post-incident analysis. v1.2 candidate if operator workflow demands forensics.

- **CSS visual treatment of pyramid section for level=MAX_PYRAMID_LEVEL.** Phase 15 displays "fully pyramided"; v1.2 could add a green badge or visual cue when at-cap.

- **Forward-look input default value.** Phase 15 Claude's Discretion: planner picks placeholder vs computed-default. v1.2 could allow operator to save a "default Z" per instrument as a personal preference.

### Reviewed Todos (not folded)
None — `gsd-sdk query todo.match-phase 15` returned zero matches.

</deferred>

---

*Phase: 15-live-calculator-sentinels*
*Context gathered: 2026-04-26*
