# Phase 15: Live Calculator + Sentinels — Research

**Researched:** 2026-04-26
**Domain:** Python dashboard rendering, HTMX fragment-GET, sizing_engine pure-math, notifier email extension
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Pure-math drift detector in `sizing_engine.detect_drift(positions, signals) -> list[DriftEvent]`. Frozen+slots dataclass per Phase 2 D-09 convention.
- **D-02:** Drift warnings cleared at signal-loop start AND after every mutate_state call. Sequence: clear_warnings_by_source('drift') → detect_drift → append_warning loop.
- **D-03:** Drift surfaces via `append_warning(source='drift')`; `notifier._has_critical_banner` extended with `source=='drift'` branch.
- **D-04:** Missing signal data → no drift event (conservative).
- **D-05:** Z (today's high) is operator-input via dashboard text field. No yfinance intraday fetch.
- **D-06:** W computed via `sizing_engine.get_trailing_stop(synthesized_position)`. Synthesized position mutates peak/trough based on Z input, uses ATR from `state['signals'][instrument]['last_scalars']['atr']`.
- **D-07:** Bit-identical parity test in tests/test_web_dashboard.py (or tests/test_web_calculator.py): 5 cases covering LONG/SHORT Z scenarios + manual_stop override.
- **D-08:** Forward-look input lives WITHIN the position row (8th or 9th column), not a separate section.
- **D-09:** `check_stop_hit` stays deferred to v1.2. Phase 15 does NOT modify it.
- **D-10:** Dashboard shows side-by-side `'manual: 7700 | computed: 7950 (will close)'` when manual_stop set.
- **D-11:** One merged banner listing all drifted instruments. Severity = max severity of constituent events. Border: `_COLOR_SHORT` (red) if any reversal, else `_COLOR_FLAT` (amber).
- **D-12:** Same wording dashboard + email. Single `_format_drift_lines(events)` helper. Lockstep parity test asserts body text byte-identical.
- **D-13:** Banner stack hierarchy: corruption > stale > reversal > drift. Render order preserved in DOM and email.
- **D-14:** Per-instrument banner copy template (exact strings specified in CONTEXT.md).

### Claude's Discretion

- Pyramid section markup: planner picks one-line summary per row.
- CSS for side-by-side manual|computed display.
- Forward-look input default value: `—` placeholder with `(enter high to project)` hint.
- HTMX swap target for forward-look: use explicit `#forward-stop-{instrument}-w` ID (more debuggable).
- Performance: no caching of detect_drift output (microseconds; single-operator).

### Deferred Ideas (OUT OF SCOPE)

- Aligning `check_stop_hit` with `manual_stop` (v1.2).
- Yahoo intraday data fetch for forward-look (v1.2).
- Banner badge for "no signal data" warning (v1.2).
- Email digest of drift events over time (v1.2+).
- Caching detect_drift output (profile-driven; not needed for v1.1).
- Refactoring `_render_drift_banner` to a shared helper module (v1.2).
- Audit log of historical drift events (v1.2).
- CSS visual badge for pyramid level=MAX (v1.2).
- Forward-look input default value operator preference (v1.2).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CALC-01 | Dashboard per-instrument row shows: current trailing stop price, distance-to-stop in $ and %, next pyramid trigger price | `get_trailing_stop(position, current_price, atr)` and `check_pyramid(position, current_price, atr_entry)` signatures verified. Distance = abs(entry_price - trail_stop). |
| CALC-02 | When signal=LONG and no position: dashboard shows entry target from `sizing_engine.calc_position_size` | `calc_position_size(account, signal, atr, rvol, multiplier)` returns `SizingDecision.contracts`. Entry threshold = today's last_close from `state['signals'][instrument]['last_close']`. |
| CALC-03 | When position is open: dashboard shows "at current bar high Z, stop would rise to W" | Synthesize position with updated peak/trough, call `get_trailing_stop(synthesized_pos, 0.0, 0.0)`. Fragment-GET endpoint pattern verified from Phase 14 code. |
| CALC-04 | Pyramid section: "level N active; add 1 contract at +Y per current ATR entry anchor; new stop after add: Z" | `check_pyramid(position, current_price, atr_entry)` returns `PyramidDecision(add_contracts, new_level)`. Next add price = entry_price + (current_level+1) * atr_entry (LONG) or entry_price - (current_level+1) * atr_entry (SHORT). |
| SENTINEL-01 | When state.positions has open position but today's signal is FLAT, amber drift banner on dashboard | `detect_drift(positions, signals)` pure-math in sizing_engine. Reads from `state['positions']` and `state['signals']`. |
| SENTINEL-02 | When positions has LONG but signal flipped to SHORT (or vice versa), red reversal banner | Same `detect_drift` function; severity='reversal' when opposite directions. |
| SENTINEL-03 | Drift/reversal banners also in daily email via `_has_critical_banner` classifier with new `source='drift'` | `notifier._has_critical_banner` extended per D-03. Email uses inline-CSS; matches Phase 8 banner pattern. |
</phase_requirements>

---

## Summary

Phase 15 adds two orthogonal work streams to the existing Phase 14 dashboard: (1) a calculator sub-row below each open position that surfaces sizing-engine derived numbers (trailing stop, distance-to-stop, pyramid level, forward-looking peak stop, and an entry-target block when flat), and (2) drift/reversal sentinel banners when `state.positions` disagrees with `state.signals`.

The architecture is well-prepared: Phase 14 already promoted `sizing_engine` and `system_params` out of `FORBIDDEN_FOR_WEB`, so `web/routes/dashboard.py` can import them for the forward-look fragment handler. The fragment-GET pattern (`?fragment=...` on GET /) is established in Phase 13/14 code. The Phase 8 `_has_critical_banner` / `append_warning` / warning-stack pattern provides the extension surface for drift sentinels. The HTMX 1.9.12 bundle is already loaded.

The primary implementation challenge is the `DriftEvent` dataclass placement: it must live in `sizing_engine.py` (pure-math hex), so `state_manager.clear_warnings_by_source` (a NEW helper) must be pure dict-op while the caller (`main.py` / `web/routes/trades.py`) wires through `mutate_state`. The forward-look fragment handler in `web/routes/dashboard.py` requires a NEW `?fragment=forward-stop&instrument=X` route branch that calls `sizing_engine.get_trailing_stop` with a synthesized position — this is the only non-trivial cross-hex call added to the web layer.

**Primary recommendation:** Implement in waves matching the existing codebase pattern — Wave 0: `DriftEvent` dataclass + `detect_drift` + `clear_warnings_by_source` scaffolds with full test skeletons; Wave 1: drift warning lifecycle in `main.py` and `web/routes/trades.py`; Wave 2: dashboard calculator sub-rows + forward-look fragment handler; Wave 3: email integration.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| DriftEvent dataclass + detect_drift | Pure-math (sizing_engine.py) | — | Must stay import-free of I/O to preserve hex-lite boundary; called from main.py, web layer, and dashboard render path |
| clear_warnings_by_source | State I/O (state_manager.py) | — | Mutates state['warnings']; only state_manager is the sole writer per TRADE-06 invariant |
| Drift warning lifecycle (clear+recompute) | Orchestrator (main.py + web/routes/trades.py) | — | Callers coordinate the pure-math detect_drift + the I/O append_warning; mirrors existing run_daily_check pattern |
| Calculator sub-row HTML | Dashboard renderer (dashboard.py) | — | Inline HTML, no server-request boundary; dashboard.py already owns position row rendering |
| Forward-look fragment handler | Web adapter (web/routes/dashboard.py) | sizing_engine (local import) | New GET branch on `?fragment=forward-stop`; calls sizing_engine locally per C-2 pattern |
| Drift banner rendering (dashboard) | Dashboard renderer (dashboard.py) | system_params (colors) | Matches _render_critical_banners placement; purely HTML rendering |
| Drift banner rendering (email) | Email renderer (notifier.py) | system_params (colors) | Inline-CSS email banner; parallels Phase 8 stale/corruption banner pattern |
| `_has_critical_banner` extension | Notifier (notifier.py) | — | Phase 8 classifier extended with `source='drift'` branch; email subject prefix auto-follows |
| Entry-target block | Dashboard renderer (dashboard.py) | sizing_engine (local import) | FLAT+directional-signal case; calls calc_position_size locally per CONTEXT D-02 |

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.11 (pinned) | Runtime | Project constraint; CLAUDE.md |
| sizing_engine | project module | DriftEvent, detect_drift, get_trailing_stop, check_pyramid, calc_position_size | Pure-math hex; already imported by web/routes/trades.py (Phase 14 D-02) |
| system_params | project module | `_COLOR_*` constants, `MAX_PYRAMID_LEVEL`, `Position` TypedDict | Shared constants; CLAUDE.md convention |
| state_manager | project module | clear_warnings_by_source (NEW), append_warning, mutate_state | I/O hex; sole-writer for state['warnings'] |
| dashboard.py | project module | _render_positions_table extension, CSS additions, _render_drift_banner | Existing HTML renderer |
| notifier.py | project module | _has_critical_banner extension, _render_drift_banner, _format_drift_lines | Existing email renderer |
| HTMX 1.9.12 | CDN (already loaded) | Forward-look fragment-GET trigger | Phase 14 pin; no new library |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| dataclasses | stdlib | `DriftEvent` frozen+slots dataclass | Follows Phase 2 D-09 pattern (SizingDecision, PyramidDecision, etc.) |
| html | stdlib | XSS escaping at leaf render sites | Already used throughout dashboard.py and notifier.py |
| math | stdlib | `math.isfinite` NaN guards | Already used in sizing_engine.py for B-1 NaN policy |
| pytest | 8.0+ (pinned) | Test framework | All new tests follow existing class-per-concern pattern |
| pytest-freezer | 0.4.9 (pinned) | Clock injection for deterministic tests | Already used in test_main.py |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `DriftEvent` in sizing_engine | DriftEvent in system_params | system_params is pure constants; putting a function-return dataclass there is semantically wrong. sizing_engine owns the logic and its return types |
| `_format_drift_lines` shared helper in system_params | Duplicate strings in dashboard + notifier | D-12 mandates single source; system_params is wrong hex layer. The helper belongs where rendering callers can reach it without violating hex boundaries — keeping it close to each renderer (both call a locally-imported `_format_drift_lines` from a shared module, OR duplicate with lockstep test) |

**Installation:** No new packages. All libraries are project modules or already-pinned dependencies.

---

## Architecture Patterns

### System Architecture Diagram

```
signal loop (main.py run_daily_check)
  └─ compute signals/positions
  └─ clear_warnings_by_source(state, 'drift')    [state_manager]
  └─ sizing_engine.detect_drift(positions, signals)
  └─ for event in drift_events: append_warning(state, 'drift', event.message)
  └─ mutate_state(_apply)   [save #1]
  └─ notifier.send_daily_email(state, ...)
     └─ _has_critical_banner(state)  → True if source='drift' present
     └─ _render_header_email(state)  → inserts drift banner after corruption/stale

web mutation (POST /trades/open|close|modify)
  └─ mutate_state(_apply):
     └─ apply position mutation
     └─ clear_warnings_by_source(state, 'drift')
     └─ sizing_engine.detect_drift(positions, signals)
     └─ for event: append_warning(state, 'drift', event.message)

GET / (dashboard serve)
  └─ render_dashboard(state)
     └─ _render_positions_table(state)
        └─ per-instrument tbody:
           └─ _render_single_position_row  [existing Phase 14]
           └─ _render_calc_row(state, instrument, pos)  [NEW Phase 15]
              ├─ trail-stop cell (CALC-01)
              ├─ distance cell $ and % (CALC-01)
              ├─ next-add price cell (CALC-04)
              ├─ pyramid level cell (CALC-04)
              └─ forward-look input + W cell (CALC-03)
           OR └─ _render_entry_target_row(state, instrument)  [NEW CALC-02]
        └─ _render_drift_banner(state)  [NEW SENTINEL-01/02]

GET /?fragment=forward-stop&instrument=X&z=NNNN
  └─ web/routes/dashboard.py NEW branch
     └─ local: from sizing_engine import get_trailing_stop
     └─ synthesize position with updated peak/trough
     └─ w = get_trailing_stop(synthesized_pos, 0.0, 0.0)
     └─ return <span id="forward-stop-{instrument}-w">$W</span>
```

### Recommended Project Structure

No new files are strictly required. The additions fit into existing files per CONTEXT.md §Source files touched. If the planner prefers a separate test file:

```
tests/
├── test_sizing_engine.py     # ADD: TestDetectDrift class
├── test_state_manager.py     # ADD: TestClearWarningsBySource class
├── test_web_dashboard.py     # ADD: TestForwardStopFragment, TestSideBySideStopDisplay
├── test_dashboard.py         # ADD: TestRenderCalculatorRow, TestRenderDriftBanner
├── test_notifier.py          # ADD: TestDriftBanner, TestBannerStackOrder
└── test_main.py              # ADD: TestDriftWarningLifecycle
```

Optional separate file (planner's discretion):
```
tests/
└── test_web_calculator.py    # Alternative to adding to test_web_dashboard.py
```

### Pattern 1: detect_drift pure-math function

```python
# Source: 15-CONTEXT.md D-01 + D-04 + D-14 (VERIFIED: source code inspection)
# In sizing_engine.py — add AFTER existing dataclasses, BEFORE calc_position_size

@dataclasses.dataclass(frozen=True, slots=True)
class DriftEvent:
  instrument: str
  held_direction: str     # 'LONG' or 'SHORT'
  signal_direction: str   # 'LONG', 'SHORT', or 'FLAT'
  severity: str           # 'drift' (position vs FLAT) or 'reversal' (LONG vs SHORT)
  message: str            # operator-facing copy from D-14 template


def detect_drift(positions: dict, signals: dict) -> list:
  '''D-01: pure-math drift detector. positions = state['positions'],
  signals = state['signals'].
  D-04: missing signal data → skip that instrument.
  '''
  events = []
  for instrument in ('SPI200', 'AUDUSD'):
    pos = positions.get(instrument)
    if pos is None:
      continue  # no open position — nothing to drift
    sig_entry = signals.get(instrument)
    if sig_entry is None:
      continue  # D-04: missing signal — conservative skip
    if not isinstance(sig_entry, dict):
      continue  # legacy int shape — conservative skip
    sig_val = sig_entry.get('signal')
    if sig_val is None:
      continue  # D-04
    from signal_engine import FLAT, LONG, SHORT
    held = pos['direction']  # 'LONG' or 'SHORT'
    held_int = LONG if held == 'LONG' else SHORT
    if sig_val == held_int:
      continue  # position matches signal — no drift
    signal_label = {LONG: 'LONG', SHORT: 'SHORT', FLAT: 'FLAT'}.get(sig_val, 'FLAT')
    if sig_val == FLAT:
      severity = 'drift'
      message = (
        f'You hold {held} {instrument}, today\'s signal is FLAT — consider closing.'
      )
    else:
      severity = 'reversal'
      new_dir = 'SHORT' if held == 'LONG' else 'LONG'
      message = (
        f'You hold {held} {instrument}, today\'s signal is {signal_label} — '
        f'reversal recommended (close {held}, open {new_dir}).'
      )
    events.append(DriftEvent(
      instrument=instrument,
      held_direction=held,
      signal_direction=signal_label,
      severity=severity,
      message=message,
    ))
  return events
```

### Pattern 2: clear_warnings_by_source (state_manager)

```python
# Source: 15-CONTEXT.md D-02 (VERIFIED: source code inspection of state_manager.py)
# Add after clear_warnings in state_manager.py

def clear_warnings_by_source(state: dict, source: str) -> dict:
  '''D-02 (Phase 15): filter out warnings matching source from state['warnings'].
  Pure dict operation — no I/O. Caller wraps in mutate_state for persistence.
  Returns mutated state dict for chaining (mirrors append_warning contract).
  '''
  state['warnings'] = [
    w for w in state.get('warnings', [])
    if w.get('source') != source
  ]
  return state
```

### Pattern 3: forward-look fragment handler (web/routes/dashboard.py)

```python
# Source: 15-CONTEXT.md D-05/D-06, 15-UI-SPEC.md §Forward-look HTMX
# (VERIFIED: existing fragment pattern in web/routes/dashboard.py)

# Add as NEW branch in get_dashboard() handler, before the generic fragment extract:

if fragment is not None and fragment.startswith('forward-stop'):
  # ?fragment=forward-stop&instrument=SPI200&z=7850.00
  from sizing_engine import get_trailing_stop  # local import — C-2 pattern
  from state_manager import load_state
  import math as _math

  instrument = request.query_params.get('instrument')
  z_raw = request.query_params.get('z', '')
  try:
    z = float(z_raw)
    if not _math.isfinite(z) or z <= 0:
      raise ValueError
  except (ValueError, TypeError):
    return Response(
      content=f'<span id="forward-stop-{instrument}-w">—</span>'.encode(),
      media_type='text/html; charset=utf-8',
    )

  state = load_state()
  pos = state.get('positions', {}).get(instrument)
  if pos is None:
    return Response(
      content=f'<span id="forward-stop-{instrument}-w">—</span>'.encode(),
      media_type='text/html; charset=utf-8',
    )

  # D-06: synthesize position with updated peak/trough based on Z input
  synth = dict(pos)
  if synth['direction'] == 'LONG':
    peak = synth.get('peak_price') or synth['entry_price']
    synth['peak_price'] = max(peak, z)
  else:  # SHORT
    trough = synth.get('trough_price') or synth['entry_price']
    synth['trough_price'] = min(trough, z)

  # get_trailing_stop(position, current_price, atr) — current_price and atr
  # are unused in the stop calc (D-15/D-16 in sizing_engine) but must be passed
  w = get_trailing_stop(synth, 0.0, 0.0)

  if not _math.isfinite(w):
    w_html = '—'
  else:
    from dashboard import _fmt_currency
    w_html = _fmt_currency(w)

  span_id = f'forward-stop-{instrument}-w'
  return Response(
    content=f'<span id="{span_id}">{w_html}</span>'.encode(),
    media_type='text/html; charset=utf-8',
  )
```

**Critical note on `get_trailing_stop` signature:** The function is `get_trailing_stop(position, current_price, atr)`. However per the docstring D-15/D-16, `current_price` is `del`'d (unused) and `atr` is `del`'d (stop uses `position['atr_entry']`). Passing `0.0` for both is safe. The synthesized position's `atr_entry` comes from `pos['atr_entry']` (the real entry ATR). [VERIFIED: sizing_engine.py lines 234-235]

**ATR for D-06 W calculation:** The sizing_engine `get_trailing_stop` uses `position['atr_entry']` (entry-time ATR), NOT today's ATR. The `atr` parameter is explicitly deleted inside the function. So `get_trailing_stop(synth, 0.0, 0.0)` gives the correct answer. The `state['signals'][instrument]['last_scalars']['atr']` today's ATR is NOT needed for the W stop — only needed for `calc_position_size` (CALC-02 entry target). [VERIFIED: sizing_engine.py line 235 `del atr`]

### Pattern 4: _has_critical_banner extension (notifier.py)

```python
# Source: 15-CONTEXT.md D-03 (VERIFIED: notifier.py lines 548-564)

def _has_critical_banner(state: dict) -> bool:
  if state.get('_stale_info'):
    return True
  for w in state.get('warnings', []):
    if (
      w.get('source') == 'state_manager'
      and w.get('message', '').startswith('recovered from corruption')
    ):
      return True
    if w.get('source') == 'drift':  # NEW Phase 15
      return True
  return False
```

### Pattern 5: drift banner insertion in _render_header_email (notifier.py)

```python
# Source: 15-CONTEXT.md D-13 + 15-UI-SPEC.md §Email Banner Contract
# (VERIFIED: notifier.py lines 567-679 structure)
# Insert AFTER corruption banner (#2), BEFORE hero card

# --- CRITICAL BANNER 3: drift/reversal (Phase 15) ---
drift_warnings = [
  w for w in state.get('warnings', [])
  if w.get('source') == 'drift'
]
if drift_warnings:
  # Determine severity: reversal if any reversal, else drift
  # (message text carries the severity cue; border color is the structural signal)
  # Use _COLOR_SHORT for reversal, _COLOR_FLAT for drift-only
  body_lines = [html.escape(w['message'], quote=True) for w in drift_warnings]
  bullet_html = '<br>\n      '.join(f'&bull; {line}' for line in body_lines)
  border_color = _COLOR_SHORT if any('reversal recommended' in w['message'] for w in drift_warnings) else _COLOR_FLAT
  parts.append(
    f'<tr><td style="padding:12px 16px;background:{_COLOR_SURFACE};'
    f'border-left:4px solid {border_color};'
    ...
    f'━━━ Drift detected ━━━</p>'
    f'<p ...>{bullet_html}</p>'
    f'</td></tr>\n'
    f'<tr><td height="16" ...>&nbsp;</td></tr>\n'
  )
```

**Note on `_format_drift_lines` helper (D-12):** The CONTEXT prescribes a shared helper producing the list of body lines. The planner must decide whether this lives in `sizing_engine` (pure-math, returns list[str]) or is a local helper in both renderers. Since it just maps `DriftEvent.message` strings, the simplest form is both renderers calling `[w.get('message', '') for w in drift_warnings]` directly. If a proper helper is added, it should NOT go in `system_params` (pure constants only). A lightweight option: add `_format_drift_lines(events)` as a private helper in `sizing_engine.py` alongside `detect_drift`. This keeps the body copy logic with its generator.

### Pattern 6: calc-row rendering in dashboard.py

```python
# Source: 15-UI-SPEC.md §Markup Contract (VERIFIED: source code inspection)
# dashboard._render_calc_row(state, state_key, pos) -> str
# Called from within per-instrument tbody rendering

def _render_calc_row(state: dict, state_key: str, pos: dict) -> str:
  '''Phase 15 CALC-01/03/04: calculator sub-row below position row.
  Uses sizing_engine functions imported LOCALLY per C-2 pattern.
  '''
  from sizing_engine import get_trailing_stop, check_pyramid
  # ... render STOP, DIST, NEXT ADD, LEVEL, IF HIGH fields
```

**CRITICAL hex note for dashboard.py:** Phase 14 CONTEXT D-02 promoted `sizing_engine` out of `FORBIDDEN_FOR_WEB` for use in `web/routes/trades.py`. But `FORBIDDEN_MODULES_DASHBOARD` in `tests/test_signal_engine.py` currently FORBIDS `sizing_engine` from being imported by `dashboard.py`. [VERIFIED: test_signal_engine.py lines 556-561 `FORBIDDEN_MODULES_DASHBOARD`]

```python
FORBIDDEN_MODULES_DASHBOARD = frozenset({
  'signal_engine', 'sizing_engine', 'data_fetcher', 'notifier', 'main',
  ...
})
```

This is the **most important architectural constraint** for Phase 15. The Phase 14 CONTEXT.md D-02 only unlocked `sizing_engine` for `web/routes/` — `dashboard.py` (the render module) is still forbidden from importing it.

**Consequence for CALC-01..04 and CALC-02/03:**

Option A (CONTEXT-compliant): `dashboard.py` continues to use the existing **inline re-implementation** pattern — `_compute_trail_stop_display` (which already mirrors `get_trailing_stop`) for the STOP cell. For CALC-04 (pyramid next-add), CALC-02 (calc_position_size), and CALC-03 (forward-look W), `dashboard.py` receives pre-computed values from the caller, OR uses inline math. The forward-look W value is computed in `web/routes/dashboard.py` (fragment handler) — which IS allowed to import sizing_engine.

Option B (extend FORBIDDEN_MODULES_DASHBOARD): Update the AST blocklist test to allow `sizing_engine` for `dashboard.py`, similar to how Phase 14 unlocked it for web/. This is a more invasive change but matches the Phase 15 CONTEXT which says `dashboard.py` will "import sizing_engine" in the Phase 15 context.

**Reading 15-CONTEXT.md §Architectural invariants carefully:** The CONTEXT states "dashboard.py continues to import system_params + (NEW for Phase 15) sizing_engine." This means **the plan MUST update `FORBIDDEN_MODULES_DASHBOARD` in the AST test** to remove `sizing_engine`. The CONTEXT explicitly approves this.

The planner should include a task: Update `FORBIDDEN_MODULES_DASHBOARD` in `tests/test_signal_engine.py` to remove `sizing_engine`, and add a regression comment explaining why (Phase 15 CALC-01..04 calculator sub-row uses sizing_engine functions locally per C-2). [ASSUMED based on CONTEXT.md wording — the test update is required but not explicitly spelled out as a task in CONTEXT]

### Anti-Patterns to Avoid

- **Importing sizing_engine at dashboard.py module top:** All `sizing_engine` imports in `dashboard.py` must be local (inside function bodies), matching the C-2 pattern established in Phase 11/13/14. The `test_web_adapter_imports_are_local_not_module_top` test enforces this for `state_manager` and `dashboard` in web/ routes; the same pattern applies here.
- **Writing to state['warnings'] directly in web handlers:** TRADE-06 sole-writer invariant. Only `state_manager.append_warning` writes there. `web/routes/trades.py` mutators call `append_warning` through `mutate_state`'s mutator callback, never directly.
- **Calling `get_trailing_stop` with today's ATR for the trail distance:** `get_trailing_stop` uses `position['atr_entry']` for stop distance (D-15) and ignores the `atr` parameter (`del atr` on line 235). Passing 0.0 is correct. Passing today's ATR produces identical results but is semantically misleading.
- **Computing next-add price incorrectly for CALC-04:** `check_pyramid` returns `PyramidDecision(add_contracts, new_level)` — the TRIGGER condition tells you IF an add happens, not the PRICE at which the next add triggers. For "next add at price P" display: `P_LONG = entry_price + (current_level + 1) * atr_entry`; `P_SHORT = entry_price - (current_level + 1) * atr_entry`. This is the inverse of the distance-threshold check inside `check_pyramid`. [VERIFIED: sizing_engine.py lines 372-384]
- **Using `check_pyramid`'s return value to get the next-add price:** `check_pyramid` doesn't return a price. The planner must compute it from the threshold formula: `threshold = (level + 1) * atr_entry` and `P = entry_price ± threshold` per direction.
- **Calling `detect_drift` with yfinance-keyed signals:** `state['signals']` is keyed by `state_key` ('SPI200', 'AUDUSD') NOT by yfinance symbol ('^AXJO', 'AUDUSD=X'). `detect_drift(state['positions'], state['signals'])` is the correct call.
- **Forgetting to update golden HTML fixtures:** `tests/fixtures/dashboard/golden.html` and `tests/fixtures/notifier/golden_*.html` will need regeneration after adding the calc-row and drift banner. The `regenerate_dashboard_golden.py` / `regenerate_notifier_golden.py` scripts handle this.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Trailing stop formula | Re-implement peak−TRAIL_MULT_LONG×atr_entry | `sizing_engine.get_trailing_stop` (for web/routes/dashboard.py fragment handler) or `_compute_trail_stop_display` (for dashboard.py render) | Both are already written, NaN-safe, manual_stop-aware per D-09 |
| Pyramid level check | Re-implement distance threshold | `sizing_engine.check_pyramid(position, current_price, atr_entry)` | Phase 2 implementation handles all edge cases (NaN, at-cap, gap days) |
| Position sizing | Re-implement ATR-based risk sizing | `sizing_engine.calc_position_size(account, signal, atr, rvol, multiplier)` | Phase 2 vol-scaling, NaN guards, SizingDecision return type |
| Warning data structure | Custom dict format | `state_manager.append_warning(state, source='drift', message=...)` | Phase 8 format `{date, source, message}`; sole-writer invariant |
| HTML escaping | Custom sanitiser | `html.escape(value, quote=True)` at every leaf render site | XSS posture established in Phase 5; grep `html.escape` to see all usage |
| HTMX polling for drift | Client-side JS polling | Server-side render + per-instrument tbody HX-Trigger event | `positions-changed` event from mutation responses already fires tbody refresh; drift banner regenerates within that flow |

**Key insight:** The entire calculator feature is a pure rendering pass over values that sizing_engine already computes. No new math, no new algorithms — just wiring existing pure-math outputs into HTML rendering. The only novelty is the forward-look Z input (operator-supplied intraday high), which is a single synthesized-position call to `get_trailing_stop`.

---

## Common Pitfalls

### Pitfall 1: `get_trailing_stop` parameter confusion
**What goes wrong:** Caller passes `z` (operator's intraday high) as the `current_price` argument to `get_trailing_stop`, expecting it to update the peak/trough. But `current_price` is DELETED inside the function (`del current_price` on line 234) — it does nothing.
**Why it happens:** The function signature looks like it takes current price, but D-16 ownership means peak/trough must be updated by the CALLER before calling get_trailing_stop.
**How to avoid:** Synthesize the position dict with updated peak/trough BEFORE calling `get_trailing_stop`. Per D-06: `if direction == 'LONG': synth['peak_price'] = max(existing_peak, z)`.
**Warning signs:** Forward-look W value equals the current stop (doesn't change as Z increases) — means peak wasn't updated.

### Pitfall 2: FORBIDDEN_MODULES_DASHBOARD not updated
**What goes wrong:** `dashboard.py` adds `from sizing_engine import get_trailing_stop` and the AST test `TestDeterminism::test_forbidden_imports_absent` in `test_signal_engine.py` fails.
**Why it happens:** `FORBIDDEN_MODULES_DASHBOARD` includes `sizing_engine` per Phase 5 Wave 0 design.
**How to avoid:** Phase 15 plan must include a Wave 0 task to update `FORBIDDEN_MODULES_DASHBOARD` in `tests/test_signal_engine.py`, removing `sizing_engine`. Add a regression comment: "sizing_engine promoted to allowed for dashboard.py in Phase 15 per CONTEXT D-01 (calculator sub-row)".
**Warning signs:** CI failure on `test_forbidden_imports_absent` for the dashboard module after adding local sizing_engine import.

### Pitfall 3: State['signals'] shape divergence for detect_drift
**What goes wrong:** `detect_drift` reads `signals[instrument]['signal']` but on a freshly reset state the signal may be an int (Phase 3 int-shape, D-08 backward-compat) instead of a dict.
**Why it happens:** run_daily_check always writes dict shape, but `reset_state()` writes int shape for signals (0 = FLAT).
**How to avoid:** `detect_drift` must handle both shapes: `sig_entry = signals.get(instrument); sig_val = sig_entry if isinstance(sig_entry, int) else sig_entry.get('signal') if isinstance(sig_entry, dict) else None`. D-04 conservative skip when None.
**Warning signs:** `detect_drift` raises `AttributeError: 'int' object has no attribute 'get'` on a fresh state.

### Pitfall 4: Drift banner in email uses wrong banner position
**What goes wrong:** Drift banner inserted AFTER hero card, violating D-13 stack hierarchy.
**Why it happens:** `_render_header_email` builds: stale banner → corruption banner → hero card. The drift banner must go between corruption banner and hero card.
**How to avoid:** Insert drift banner block between `# --- CRITICAL BANNER 2: corrupt-reset ---` and `# --- HERO CARD ---` in `_render_header_email`.
**Warning signs:** `TestBannerStackOrder` fails; email renders drift banner below the signal summary card.

### Pitfall 5: W3 invariant broken (extra save_state calls)
**What goes wrong:** drift clear+recompute in `run_daily_check` adds a third `mutate_state` call, breaking the `test_happy_path_save_state_called_exactly_twice` test.
**Why it happens:** The clear_warnings_by_source + detect_drift + append_warning sequence must be in-memory only, merged into the SAME `mutate_state` call that ends `run_daily_check`.
**How to avoid:** Per D-02 and D-03 of 15-CONTEXT.md, drift operations are in-memory mutations on the `state` dict. The single `mutate_state(_apply_daily_run)` at step 5 of run_daily_check replays them all atomically. Do NOT add a separate `mutate_state` call for drift.
**Warning signs:** `test_happy_path_save_state_called_exactly_twice` fails.

### Pitfall 6: next-add price formula direction error
**What goes wrong:** CALC-04 shows wrong next-add price for SHORT positions.
**Why it happens:** SHORT next-add is `entry_price - threshold` (price needs to go DOWN for profit), not `entry_price + threshold`.
**How to avoid:** `P_SHORT = pos['entry_price'] - (current_level + 1) * pos['atr_entry']`. Verify by reading `check_pyramid` lines 376-384: `distance = entry_price - current_price` for SHORT (price going down = positive distance).
**Warning signs:** SHORT position shows a next-add price ABOVE entry price.

### Pitfall 7: Sentinel banner color logic inverted
**What goes wrong:** Drift-only events get red border instead of amber; reversals get amber.
**Why it happens:** Boolean check written as `if any(e.severity == 'drift' ...)` instead of `if any(e.severity == 'reversal' ...)`.
**How to avoid:** `border_color = _COLOR_SHORT if any(e.severity == 'reversal' for e in events) else _COLOR_FLAT`. Also CSS class: `sentinel-reversal` when any reversal, `sentinel-drift` when all drift.
**Warning signs:** `TestRenderDriftBanner::test_reversal_color_is_red` fails; amber banner shown for reversal.

### Pitfall 8: clear_warnings_by_source called with wrong scope
**What goes wrong:** `clear_warnings(state)` (Phase 8 full clear) accidentally called instead of `clear_warnings_by_source(state, 'drift')`, wiping all warnings on each mutation.
**Why it happens:** Two similar functions; `clear_warnings` is the post-dispatch full clear used in `_dispatch_email_and_maintain_warnings`.
**How to avoid:** Only `clear_warnings_by_source(state, 'drift')` in the drift lifecycle path. `clear_warnings(state)` is post-email-dispatch only. Review grep: `grep -n 'clear_warnings' main.py web/routes/trades.py` — no bare `clear_warnings` call should appear in the drift recompute block.
**Warning signs:** Corruption/stale/fetch warnings disappear on each trade mutation.

---

## Code Examples

Verified patterns from official sources:

### get_trailing_stop exact signature and behavior
```python
# Source: sizing_engine.py lines 180-255 (VERIFIED)
def get_trailing_stop(
  position: Position,
  current_price: float,   # UNUSED — del'd on line 234 (D-16)
  atr: float,             # UNUSED — del'd on line 235 (D-15); uses position['atr_entry']
) -> float:
  # Returns manual_stop if set (D-09), else peak - TRAIL_MULT_LONG * atr_entry (LONG)
  # or trough + TRAIL_MULT_SHORT * atr_entry (SHORT).
  # NaN if atr_entry is NaN (B-1).
  # peak_price=None fallback: uses entry_price
```

### check_pyramid exact signature
```python
# Source: sizing_engine.py lines 333-384 (VERIFIED)
def check_pyramid(
  position: Position,
  current_price: float,   # today's close (mark-to-market; used for distance calc)
  atr_entry: float,       # ATR at entry time (from position['atr_entry'])
) -> PyramidDecision:
  # Returns PyramidDecision(add_contracts=0|1, new_level=int)
  # Does NOT return next-add price — caller must compute:
  #   LONG next-add: entry_price + (current_level + 1) * atr_entry
  #   SHORT next-add: entry_price - (current_level + 1) * atr_entry
```

### calc_position_size exact signature
```python
# Source: sizing_engine.py lines 118-177 (VERIFIED)
def calc_position_size(
  account: float,
  signal: int,       # LONG=1 or SHORT=-1 (not FLAT)
  atr: float,        # today's ATR from state['signals'][instrument]['last_scalars']['atr']
  rvol: float,       # from state['signals'][instrument]['last_scalars']['rvol']
  multiplier: float, # from state['_resolved_contracts'][instrument]['multiplier']
) -> SizingDecision:
  # Returns SizingDecision(contracts=int, warning=str|None)
  # contracts=0 means skip trade (no floor; operator decision)
```

### append_warning exact signature
```python
# Source: state_manager.py lines 591-619 (VERIFIED)
def append_warning(state: dict, source: str, message: str, now=None) -> dict:
  # Appends {date: AWST, source: source, message: message}
  # FIFO trim to MAX_WARNINGS=100
  # SOLE writer to state['warnings']
```

### mutate_state pattern for web handlers with drift
```python
# Source: 15-CONTEXT.md D-02 + web/routes/trades.py structure (VERIFIED)

def close_trade(req: CloseTradeRequest):
  conflict: list[str] = []

  def _apply(fresh_state: dict) -> None:
    # ... existing close mutation ...

    # Phase 15 drift recompute (D-02)
    from sizing_engine import detect_drift
    from state_manager import clear_warnings_by_source
    clear_warnings_by_source(fresh_state, 'drift')
    events = detect_drift(fresh_state['positions'], fresh_state['signals'])
    for ev in events:
      from state_manager import append_warning
      append_warning(fresh_state, source='drift', message=ev.message)

  from state_manager import mutate_state
  mutate_state(_apply)
```

### Fragment-GET response pattern (verified from Phase 14)
```python
# Source: web/routes/dashboard.py lines 143-162 (VERIFIED)
# Phase 15 adds a NEW fragment type before the generic regex extraction:

if fragment is not None and fragment == f'forward-stop':
  # ... compute W ...
  return Response(
    content=span_html.encode('utf-8'),
    media_type='text/html; charset=utf-8',
  )
```

### Dashboard golden fixture regeneration
```python
# Source: tests/regenerate_dashboard_golden.py (VERIFIED: file exists)
# After Phase 15 changes dashboard.py rendering, regenerate with:
#   cd /path/to/repo && python tests/regenerate_dashboard_golden.py
# Same for notifier:
#   python tests/regenerate_notifier_golden.py
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| dashboard.py forbidden from importing sizing_engine | Phase 15 promotes sizing_engine to allowed (removes from FORBIDDEN_MODULES_DASHBOARD) | Phase 15 | dashboard.py calc-row uses local get_trailing_stop/check_pyramid imports; AST test must be updated |
| No drift detection | detect_drift + DriftEvent + clear_warnings_by_source | Phase 15 | state['warnings'] gains 'drift' source key; email subject gets [!] on drift |
| Trailing stop shown as single computed value | Side-by-side manual:X | computed:Y (will close) | Phase 15 D-10 | Operator can see both values; daily loop still uses computed |
| Fragment-GET limited to `?fragment=position-group-{X}` | Also supports `?fragment=forward-stop&instrument={X}&z={Z}` | Phase 15 | Inline HTMX input for forward-looking stop projection |

**Deprecated/outdated:**
- `FORBIDDEN_MODULES_DASHBOARD` containing `sizing_engine`: deprecated by Phase 15 CONTEXT D-01 (calculator sub-row). AST test must be updated before first sizing_engine local import in dashboard.py.
- Single-value trailing stop cell (`trail_currency` only): replaced by `_render_trail_stop_cell(pos)` helper that returns either single-value or side-by-side depending on `pos.get('manual_stop')`.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `detect_drift` should handle both int-shape and dict-shape for `state['signals']` entries (Phase 3 reset shape vs Phase 4 dict shape) | Pattern 1, Pitfall 3 | If wrong: `detect_drift` raises AttributeError on freshly-reset state; all drift detection broken |
| A2 | `FORBIDDEN_MODULES_DASHBOARD` must be updated in `tests/test_signal_engine.py` to remove `sizing_engine` for Phase 15 to proceed (CONTEXT says "dashboard.py + sizing_engine") | Pattern 6, Pitfall 2 | If wrong: no code change needed; but then calc-row must use inline math (like `_compute_trail_stop_display` does) rather than local sizing_engine imports |
| A3 | Next-add price formula for CALC-04 is `entry_price + (current_level+1) * atr_entry` (LONG) / `entry_price - (current_level+1) * atr_entry` (SHORT) — derived from `check_pyramid`'s threshold logic | CALC-04 implementation | If wrong: CALC-04 shows wrong trigger price to operator |
| A4 | `_format_drift_lines` helper can be a private function in `sizing_engine.py` (alongside `detect_drift`) rather than a separate shared module | D-12 implementation | Low risk; purely organizational. Planner can also implement as local lambdas in both renderers with lockstep test asserting byte-identity |
| A5 | `dashboard.py` calc-row can call `sizing_engine.calc_position_size` locally (for CALC-02 entry-target contracts) — this is consistent with the hex promotion in CONTEXT D-01 | CALC-02 implementation | If wrong: calc_position_size result must be passed in as a pre-computed value from web layer |

---

## Open Questions

1. **_format_drift_lines placement**
   - What we know: D-12 requires a single helper producing body lines that both dashboard and email renderers use for byte-identity
   - What's unclear: Whether to put `_format_drift_lines` in `sizing_engine.py` (alongside `detect_drift`) or implement as identical local logic in both renderers backed by a parity test
   - Recommendation: Add `_format_drift_lines(events: list) -> list[str]` to `sizing_engine.py` as a private helper. Both renderers import it locally. One parity test asserts same output from both render paths.

2. **entry-target threshold price (CALC-02)**
   - What we know: UI-SPEC says "enter on next close ≥ X"; the threshold X is `state['signals'][instrument]['last_close']` (today's close used as the trigger reference)
   - What's unclear: Whether "entry target threshold" means today's close (i.e., "enter at today's close if signal is still LONG") or some ATR-derived level above today's close
   - Recommendation: Use `state['signals'][instrument]['last_close']` directly as X — it's the price the signal was based on. The copy "enter on next close ≥ X" implies the operator should enter if tomorrow's close stays above this level.

3. **Golden fixture update strategy**
   - What we know: `tests/fixtures/dashboard/golden.html` and notifier goldens will be invalidated by the new calc-row and drift banner HTML
   - What's unclear: Whether Phase 15 plan should (a) update the fixtures as part of a dedicated Wave task, or (b) disable golden tests temporarily and re-enable after final render pass
   - Recommendation: Include a dedicated "Wave 3: Update golden fixtures" task that runs `python tests/regenerate_dashboard_golden.py` and `python tests/regenerate_notifier_golden.py` with the sample_state fixture updated to include an open position + a drift scenario.

---

## Environment Availability

Step 2.6: SKIPPED — Phase 15 is purely code/config changes with no new external dependencies. All required tools (Python 3.11, pytest, existing CDN resources) are already verified from prior phases.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.0+ (pinned in pyproject.toml) |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `pytest tests/test_sizing_engine.py tests/test_state_manager.py -x -q` |
| Full suite command | `pytest -ra --strict-markers` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CALC-01 | Per-instrument calc-row renders trail stop, distance $+%, next-add price | unit (dashboard render) | `pytest tests/test_dashboard.py::TestRenderCalculatorRow -x` | ❌ Wave 0 |
| CALC-01 | Trail stop in calc-row matches `_compute_trail_stop_display` (existing parity) | unit (sizing parity) | `pytest tests/test_dashboard.py::TestRenderCalculatorRow::test_trail_stop_matches_display_helper -x` | ❌ Wave 0 |
| CALC-02 | When position=FLAT + signal=LONG/SHORT: entry-target row rendered with calc_position_size contracts | unit (dashboard render) | `pytest tests/test_dashboard.py::TestRenderCalculatorRow::test_entry_target_row_flat_long -x` | ❌ Wave 0 |
| CALC-02 | When position=FLAT + signal=FLAT: NO calc-row rendered | unit (dashboard render) | `pytest tests/test_dashboard.py::TestRenderCalculatorRow::test_no_calc_row_when_flat_signal -x` | ❌ Wave 0 |
| CALC-03 | Forward-look fragment GET returns `<span id="forward-stop-SPI200-w">$X</span>` | integration (web route) | `pytest tests/test_web_dashboard.py::TestForwardStopFragment -x` | ❌ Wave 0 |
| CALC-03 | W value from fragment handler is bit-identical to direct `get_trailing_stop(synthesized_pos)` call — 5 cases per D-07 | unit (parity) | `pytest tests/test_web_dashboard.py::TestForwardStopFragment::test_forward_stop_matches_sizing_engine_bit_for_bit -x` | ❌ Wave 0 |
| CALC-03 | Z=empty/0/negative → W cell shows `—` (no error, no HTMX error machinery) | integration (web route) | `pytest tests/test_web_dashboard.py::TestForwardStopFragment::test_degenerate_z_returns_em_dash -x` | ❌ Wave 0 |
| CALC-04 | Pyramid section shows "Pyramid: level N/2 — next add at $P (+1×ATR), new stop $S" | unit (dashboard render) | `pytest tests/test_dashboard.py::TestRenderCalculatorRow::test_pyramid_section_level_1 -x` | ❌ Wave 0 |
| CALC-04 | Pyramid section shows "Pyramid: level 2/2 — fully pyramided" at MAX | unit (dashboard render) | `pytest tests/test_dashboard.py::TestRenderCalculatorRow::test_pyramid_section_at_max -x` | ❌ Wave 0 |
| SENTINEL-01 | detect_drift(positions={SPI200: LONG pos}, signals={SPI200: FLAT}) → DriftEvent(severity='drift') | unit (pure-math) | `pytest tests/test_sizing_engine.py::TestDetectDrift::test_drift_long_vs_flat -x` | ❌ Wave 0 |
| SENTINEL-01 | Amber drift banner renders in dashboard HTML with `.sentinel-drift` class | unit (dashboard render) | `pytest tests/test_dashboard.py::TestRenderDriftBanner::test_amber_drift_banner -x` | ❌ Wave 0 |
| SENTINEL-01 | No banner when no drift events | unit (dashboard render) | `pytest tests/test_dashboard.py::TestRenderDriftBanner::test_no_banner_when_no_drift -x` | ❌ Wave 0 |
| SENTINEL-02 | detect_drift with LONG position + SHORT signal → DriftEvent(severity='reversal') | unit (pure-math) | `pytest tests/test_sizing_engine.py::TestDetectDrift::test_reversal_long_vs_short -x` | ❌ Wave 0 |
| SENTINEL-02 | Red reversal banner renders with `.sentinel-reversal` class | unit (dashboard render) | `pytest tests/test_dashboard.py::TestRenderDriftBanner::test_red_reversal_banner -x` | ❌ Wave 0 |
| SENTINEL-02 | Mixed drift+reversal events: single merged banner uses red border | unit (dashboard render) | `pytest tests/test_dashboard.py::TestRenderDriftBanner::test_mixed_drift_reversal_uses_reversal_color -x` | ❌ Wave 0 |
| SENTINEL-03 | Drift warning in state['warnings'] causes `_has_critical_banner` to return True | unit (notifier) | `pytest tests/test_notifier.py::TestDriftBanner::test_has_critical_banner_drift_source -x` | ❌ Wave 0 |
| SENTINEL-03 | Email body contains drift banner body text matching dashboard text byte-for-byte | unit (notifier parity) | `pytest tests/test_notifier.py::TestDriftBanner::test_drift_banner_body_parity_with_dashboard -x` | ❌ Wave 0 |
| SENTINEL-03 | Email subject gets `[!]` prefix when drift warning present | unit (notifier subject) | `pytest tests/test_notifier.py::TestDriftBanner::test_drift_banner_in_email_body_and_subject_critical_prefix -x` | ❌ Wave 0 |
| D-13 | Corruption warning coexisting with drift: corruption banner renders first | unit (banner hierarchy) | `pytest tests/test_notifier.py::TestBannerStackOrder::test_banner_hierarchy_corruption_beats_drift -x` | ❌ Wave 0 |
| D-13 | Stale info coexisting with drift: stale banner renders first | unit (banner hierarchy) | `pytest tests/test_notifier.py::TestBannerStackOrder::test_banner_hierarchy_stale_beats_drift -x` | ❌ Wave 0 |
| D-02 | clear_warnings_by_source removes matching source, leaves others intact | unit (state_manager) | `pytest tests/test_state_manager.py::TestClearWarningsBySource -x` | ❌ Wave 0 |
| D-02 | Drift warnings cleared + recomputed at signal-loop start (W3 invariant preserved) | integration (main) | `pytest tests/test_main.py::TestDriftWarningLifecycle -x` | ❌ Wave 0 |
| D-07 | Side-by-side manual|computed stop cell renders correctly when manual_stop set | unit (dashboard render) | `pytest tests/test_web_dashboard.py::TestSideBySideStopDisplay::test_manual_stop_side_by_side -x` | ❌ Wave 0 |
| D-07 | When manual_stop=None: single computed stop cell (no regression from Phase 14) | unit (dashboard render) | `pytest tests/test_web_dashboard.py::TestSideBySideStopDisplay::test_no_manual_stop_single_cell -x` | ❌ Wave 0 |

### Additional Critical Tests

| Test | Behavior | Why Critical |
|------|----------|-------------|
| `test_sizing_engine.py::TestDetectDrift::test_no_event_when_position_flat` | FLAT position → no drift event | Correctness invariant |
| `test_sizing_engine.py::TestDetectDrift::test_no_event_when_signal_missing` | D-04: missing signal → skip conservatively | Prevents false-positive drift banners |
| `test_sizing_engine.py::TestDetectDrift::test_signal_int_shape_compat` | int-shaped signal (reset state) → no crash | Backward compat with Phase 3 state shape |
| `test_main.py::TestDriftWarningLifecycle::test_w3_invariant_preserved` | mutate_state called exactly twice per run | W3 invariant; crash if broken |
| `test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent` | sizing_engine NOT in FORBIDDEN_MODULES_DASHBOARD after Phase 15 update | Must UPDATE test constant before adding sizing_engine local import to dashboard.py |

### Sampling Rate
- **Per task commit:** `pytest tests/test_sizing_engine.py tests/test_state_manager.py tests/test_dashboard.py tests/test_notifier.py tests/test_web_dashboard.py tests/test_main.py -x -q`
- **Per wave merge:** `pytest -ra --strict-markers`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_sizing_engine.py::TestDetectDrift` — covers SENTINEL-01, SENTINEL-02, D-04
- [ ] `tests/test_state_manager.py::TestClearWarningsBySource` — covers D-02
- [ ] `tests/test_dashboard.py::TestRenderCalculatorRow` — covers CALC-01, CALC-02, CALC-04
- [ ] `tests/test_dashboard.py::TestRenderDriftBanner` — covers SENTINEL-01, SENTINEL-02, D-13
- [ ] `tests/test_notifier.py::TestDriftBanner` — covers SENTINEL-03
- [ ] `tests/test_notifier.py::TestBannerStackOrder` — covers D-13
- [ ] `tests/test_web_dashboard.py::TestForwardStopFragment` — covers CALC-03, D-07
- [ ] `tests/test_web_dashboard.py::TestSideBySideStopDisplay` — covers D-10
- [ ] `tests/test_main.py::TestDriftWarningLifecycle` — covers D-02, W3 invariant
- [ ] Update `FORBIDDEN_MODULES_DASHBOARD` in `tests/test_signal_engine.py` to remove `sizing_engine`
- [ ] Regenerate golden fixtures: `tests/fixtures/dashboard/golden.html`, `tests/fixtures/notifier/golden_*.html`

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | No new auth surfaces; all endpoints behind existing AuthMiddleware |
| V3 Session Management | no | No session changes |
| V4 Access Control | no | Single-operator app; all new endpoints behind existing `X-Trading-Signals-Auth` |
| V5 Input Validation | yes | `z` parameter in forward-look fragment GET: validated as finite positive float; degenerate input returns `—` (no error propagation) |
| V6 Cryptography | no | No new crypto |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| XSS via `DriftEvent.message` in HTML banner | Tampering | `html.escape(message, quote=True)` at every leaf render site in dashboard._render_drift_banner and notifier._render_drift_banner. DriftEvent.message is server-constructed (not user-input), but escaping is project policy regardless. |
| Malformed `z` input in forward-look fragment | Tampering | `float(z_raw)` → `math.isfinite` check → return `—` on exception; no 4xx to avoid triggering HTMX error machinery on partial-typed values |
| Auth header exposure via new HTMX input | Info Disclosure | Forward-look `<input>` inside per-instrument `<tbody>` inherits the parent's `hx-headers='{"X-Trading-Signals-Auth": "{{WEB_AUTH_SECRET}}"}'` via HTMX's header inheritance mechanism. The placeholder substitution in web/routes/dashboard.py covers this (existing REVIEWS HIGH #4 discipline). |

---

## Sources

### Primary (HIGH confidence)
- `sizing_engine.py` lines 180-255 (get_trailing_stop), 333-384 (check_pyramid), 118-177 (calc_position_size) — VERIFIED by direct source inspection
- `system_params.py` — Position TypedDict, _COLOR_* constants — VERIFIED by direct source inspection
- `notifier.py` lines 548-679 — `_has_critical_banner`, `_render_header_email` — VERIFIED by direct source inspection
- `dashboard.py` lines 729-806, 1010-1173 — `_compute_trail_stop_display`, `_render_positions_table`, `_render_single_position_row` — VERIFIED by direct source inspection
- `state_manager.py` lines 591-643 — `append_warning`, `clear_warnings`, `mutate_state` — VERIFIED by direct source inspection
- `web/routes/dashboard.py` — fragment-GET pattern, placeholder substitution — VERIFIED by direct source inspection
- `web/routes/trades.py` — mutate_state pattern, local import discipline — VERIFIED by direct source inspection
- `tests/test_signal_engine.py` lines 488-580 — `FORBIDDEN_MODULES_DASHBOARD` — VERIFIED by direct source inspection
- `tests/test_web_healthz.py` lines 181-238 — `FORBIDDEN_FOR_WEB`, local-import test — VERIFIED by direct source inspection
- `.planning/phases/15-live-calculator-sentinels/15-CONTEXT.md` — D-01..D-14, architectural invariants — VERIFIED by direct file read
- `.planning/phases/15-live-calculator-sentinels/15-UI-SPEC.md` — markup contract, CSS, interaction contract — VERIFIED by direct file read

### Secondary (MEDIUM confidence)
- pyproject.toml `[tool.pytest.ini_options]` — pytest 8.0+, testpaths=['tests'] — VERIFIED by direct file read

### Tertiary (LOW confidence)
- None — all claims verified against source code or CONTEXT.md.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries verified by direct source inspection
- Architecture: HIGH — sizing_engine signatures, hex boundaries, warning patterns all verified
- Pitfalls: HIGH — most pitfalls derived from reading actual code (FORBIDDEN_MODULES_DASHBOARD, get_trailing_stop param behavior, W3 invariant)
- Test map: HIGH — test class names align with existing project conventions; framework config verified

**Research date:** 2026-04-26
**Valid until:** 2026-05-26 (stable dependencies; no fast-moving external libraries)
