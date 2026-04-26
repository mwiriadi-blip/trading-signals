# Phase 15: Live Calculator + Sentinels — Pattern Map

**Mapped:** 2026-04-26
**Files analyzed:** 14 (8 source files modified + 6 test files modified)
**Analogs found:** 14 / 14

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `sizing_engine.py` | pure-math service | transform | `sizing_engine.py` existing dataclasses (SizingDecision, PyramidDecision, ClosedTrade, StepResult) + `get_trailing_stop` | exact — same file, same dataclass pattern |
| `state_manager.py` | state I/O service | CRUD | `state_manager.clear_warnings` (lines 621-643) | exact — same file, same filter-on-source pattern |
| `main.py` | orchestrator | event-driven | `main.py:run_daily_check` steps 6-7 (append_warning loop + mutate_state) | exact — same file, same in-memory-then-save pattern |
| `web/routes/trades.py` | web handler | request-response | `web/routes/trades.py` `open_trade._apply` + `close_trade._apply` mutator pattern | exact — same file, same mutate_state closure pattern |
| `web/routes/dashboard.py` | web adapter | request-response | `web/routes/dashboard.py` fragment-GET regex branch (lines 144-162) | exact — same file, `?fragment=` branch to return `Response` HTML |
| `dashboard.py` | HTML renderer | transform | `dashboard.py:_render_single_position_row` (lines 1010-1080) + `_render_positions_table` (lines 1083-1173) | exact — same file, same per-instrument tbody + `<tr>` cell rendering |
| `notifier.py` | email renderer | transform | `notifier.py:_has_critical_banner` (lines 548-564) + `_render_header_email` critical banner blocks (lines 591-641) | exact — same file, same source-key branch + inline-CSS `<tr>` block |
| `tests/test_signal_engine.py` | test — AST gate | transform | `test_signal_engine.py` `FORBIDDEN_MODULES_DASHBOARD` constant + `test_dashboard_no_forbidden_imports` (lines 556-565, 860-882) | exact — same file, constant update only |
| `tests/test_sizing_engine.py` | test — pure-math | transform | `tests/test_sizing_engine.py:TestExits` class (lines 405-519) | exact — same file, same class-per-concern + `_make_position` fixture pattern |
| `tests/test_state_manager.py` | test — state I/O | CRUD | `tests/test_state_manager.py:TestClearWarnings` class (lines 1328-1379) | exact — same file, same reset_state + append_warning setup pattern |
| `tests/test_web_dashboard.py` | test — web fragment | request-response | `tests/test_web_dashboard.py` (existing test_web_dashboard.py structure) | role-match — fragment-GET test added alongside existing web tests |
| `tests/test_dashboard.py` | test — HTML render | transform | `tests/test_dashboard.py` (existing render tests) | role-match — render test added alongside existing dashboard render tests |
| `tests/test_notifier.py` | test — email render | transform | `tests/test_notifier.py` existing `_has_critical_banner` and banner tests | role-match — banner hierarchy tests extend existing notifier test classes |
| `tests/test_main.py` | test — integration | event-driven | `tests/test_main.py` (existing W3 invariant test) | role-match — drift lifecycle test extends main integration tests |

---

## Pattern Assignments

### `sizing_engine.py` — `DriftEvent` dataclass + `detect_drift` function

**Analog:** `sizing_engine.py` existing dataclasses (lines 39-93)

**Imports pattern** (lines 17-32):
```python
import dataclasses
import math

from signal_engine import FLAT, LONG, SHORT
from system_params import (
  MAX_PYRAMID_LEVEL,
  TRAIL_MULT_LONG,
  TRAIL_MULT_SHORT,
  Position,
)
```
No new top-level imports are needed — `dataclasses` is already imported.

**Dataclass pattern** (lines 39-93) — copy `frozen=True, slots=True`, same as all others:
```python
@dataclasses.dataclass(frozen=True, slots=True)
class SizingDecision:
  contracts: int
  warning: str | None = None

@dataclasses.dataclass(frozen=True, slots=True)
class PyramidDecision:
  add_contracts: int
  new_level: int
```
`DriftEvent` uses this same `@dataclasses.dataclass(frozen=True, slots=True)` decorator block with no default fields (all required).

**Core detect_drift pattern** — iterates the two known instrument keys, guarded by D-04 conservative skip. Handles both int-shape (Phase 3 reset) and dict-shape signals (Pitfall 3 in RESEARCH.md):
```python
# LONG/SHORT/FLAT already imported at top via: from signal_engine import FLAT, LONG, SHORT
for instrument in ('SPI200', 'AUDUSD'):
    pos = positions.get(instrument)
    if pos is None:
        continue
    sig_entry = signals.get(instrument)
    if sig_entry is None:
        continue
    # D-04 + Pitfall 3: handle int-shape (reset state) vs dict-shape (daily-run state)
    if isinstance(sig_entry, int):
        sig_val = sig_entry
    elif isinstance(sig_entry, dict):
        sig_val = sig_entry.get('signal')
    else:
        continue
    if sig_val is None:
        continue
```

**Error handling pattern** — none needed; pure-math, returns empty list on missing data per D-04.

---

### `state_manager.py` — `clear_warnings_by_source` function

**Analog:** `state_manager.py:clear_warnings` (lines 621-643)

**Function signature and docstring pattern** (lines 621-623):
```python
def clear_warnings(state: dict) -> dict:
  '''D-02 (Phase 8): clear state['warnings'] after the current run's
  email has been built and dispatched. Preserves D-10 sole-writer
  invariant — state_manager is the ONLY module that mutates
  state['warnings']; notifier reads but never writes.
  ...
  In-place mutation; returns the same dict for chaining.
  '''
  state['warnings'] = []
  return state
```

`clear_warnings_by_source` follows this EXACT same pattern:
- Same return type: `dict` (returns `state` for chaining)
- Same in-place mutation
- Same docstring style referencing the D-XX decision
- Sole writer invariant referenced in docstring
- Add AFTER `clear_warnings` (line 644+) in the same file section

**Core pattern** — list comprehension filter on source key:
```python
def clear_warnings_by_source(state: dict, source: str) -> dict:
  state['warnings'] = [
    w for w in state.get('warnings', [])
    if w.get('source') != source
  ]
  return state
```

---

### `main.py` — drift recompute step in `run_daily_check`

**Analog:** `main.py:run_daily_check` steps 6-7 (lines 1270-1275)

**Existing pattern to extend** (lines 1270-1275):
```python
# Step 6: flush queued warnings (empty in Wave 2; Wave 3 DATA-05 appends).
for source, message in pending_warnings:
    state = state_manager.append_warning(state, source, message)

# Step 7: bookkeeping — last_run.
state['last_run'] = run_date_iso
```

**Insertion point:** Between step 6 (flush warnings) and step 7 (last_run). The drift recompute block goes here as in-memory mutation — before `_apply_daily_run` captures `_accumulated = state` for the `mutate_state` call at step 9.

**Insertion pattern** — mirrors the `pending_warnings` flush loop:
```python
# Step 6b: drift recompute (Phase 15 D-02)
# clear_warnings_by_source + detect_drift + append_warning loop
# MUST be in-memory only (no extra mutate_state call — W3 invariant).
state = state_manager.clear_warnings_by_source(state, 'drift')
drift_events = sizing_engine.detect_drift(state['positions'], state['signals'])
for ev in drift_events:
    state = state_manager.append_warning(state, 'drift', ev.message)
    logger.info(
        '[Sched] drift detected for %s: held=%s signal=%s severity=%s',
        ev.instrument, ev.held_direction, ev.signal_direction, ev.severity,
    )
```

**Log prefix pattern** (lines 1063-1067): all signal-loop activity uses `[Sched]` prefix exactly as shown above.

**W3 invariant preservation:** the `_apply_daily_run` closure at step 9 (lines 1299-1310) captures `_accumulated = state` AFTER the drift block, so drift warnings travel inside the single `mutate_state` call. No additional `mutate_state` call is added.

```python
# Step 9 (UNCHANGED — W3 preserved): the _accumulated dict now includes
# the drift-updated warnings key. No extra mutate_state call.
_accumulated = state
def _apply_daily_run(fresh_state: dict) -> None:
    for key in (
        'positions', 'signals', 'account', 'trade_log',
        'equity_history', 'last_run', 'warnings',  # warnings includes drift
    ):
        if key in _accumulated:
            fresh_state[key] = _accumulated[key]
state = state_manager.mutate_state(_apply_daily_run)
```

---

### `web/routes/trades.py` — drift recompute in each mutator's `_apply`

**Analog:** `web/routes/trades.py:close_trade._apply` (lines 557-596) and `open_trade._apply` (lines 472-531)

**Existing `_apply` closure pattern** (lines 557-596):
```python
def _apply(state):
    pos = state['positions'].get(req.instrument)
    if pos is None:
        msg = f'no open position for instrument {req.instrument}'
        raise _OpenConflict(msg)
    # ... apply mutation logic ...
    record_trade(state, trade)
```

**Drift block appended INSIDE each `_apply`, after the position mutation, using local imports (C-2 pattern)**:
```python
def _apply(state):
    # ... existing mutation logic ...
    record_trade(state, trade)           # or existing_pos mutation

    # Phase 15 D-02: drift recompute after position mutation
    from sizing_engine import detect_drift
    from state_manager import clear_warnings_by_source, append_warning
    clear_warnings_by_source(state, 'drift')
    events = detect_drift(state['positions'], state['signals'])
    for ev in events:
        append_warning(state, source='drift', message=ev.message)
```

**Local import pattern** (from Phase 11 C-2, already used lines 466-467):
```python
from state_manager import mutate_state
from sizing_engine import check_pyramid
```
All imports inside handler bodies, never at module top.

**Error handling pattern** — `_apply` raises `_OpenConflict` for conflicts; the drift block runs ONLY on the success path (after mutation committed), so it has no error path of its own.

---

### `web/routes/dashboard.py` — `?fragment=forward-stop` GET handler

**Analog:** `web/routes/dashboard.py:get_dashboard` fragment branch (lines 144-162)

**Existing fragment-GET pattern** (lines 144-162):
```python
if fragment is not None:
    # Extract the tbody whose id matches `fragment`.
    m = re.search(
        rb'<tbody id="' + re.escape(fragment.encode('utf-8')) + rb'">(.*?)</tbody>',
        content, re.DOTALL,
    )
    if not m:
        return Response(
            content=b'', status_code=404,
            media_type='text/html; charset=utf-8',
        )
    return Response(
        content=m.group(1),
        media_type='text/html; charset=utf-8',
    )
```

**New fragment branch pattern** — added BEFORE the existing `if fragment is not None` generic branch (so `forward-stop` is intercepted first):
```python
if fragment is not None and fragment.startswith('forward-stop'):
    # Phase 15 CALC-03: ?fragment=forward-stop&instrument=SPI200&z=7850.00
    from sizing_engine import get_trailing_stop   # local import — C-2 pattern
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
    # D-06: synthesize position with updated peak/trough
    synth = dict(pos)
    if synth['direction'] == 'LONG':
        peak = synth.get('peak_price') or synth['entry_price']
        synth['peak_price'] = max(peak, z)
    else:
        trough = synth.get('trough_price') or synth['entry_price']
        synth['trough_price'] = min(trough, z)
    # get_trailing_stop uses position['atr_entry']; current_price and atr are del'd
    w = get_trailing_stop(synth, 0.0, 0.0)
    span_id = f'forward-stop-{instrument}-w'
    if not _math.isfinite(w):
        w_html = '—'
    else:
        from dashboard import _fmt_currency
        w_html = _fmt_currency(w)
    return Response(
        content=f'<span id="{span_id}">{w_html}</span>'.encode('utf-8'),
        media_type='text/html; charset=utf-8',
    )
```

**Response format pattern** (lines 159-162):
```python
return Response(
    content=m.group(1),
    media_type='text/html; charset=utf-8',
)
```
All fragments return `Response(..., media_type='text/html; charset=utf-8')` — same here.

---

### `dashboard.py` — calculator row + drift banner + side-by-side stop cell

**Analog:** `dashboard.py:_render_single_position_row` (lines 1010-1080) + `_render_positions_table` (lines 1083-1173)

**Imports pattern** — no new module-level imports. All `sizing_engine` uses are LOCAL inside function bodies (C-2 pattern, enforced by `FORBIDDEN_MODULES_DASHBOARD` after the test update).

**Format helper pattern** (lines 584-609):
```python
def _fmt_em_dash() -> str:
    return '—'

def _fmt_currency(value: float) -> str:
    if value < 0:
        return f'-${-value:,.2f}'
    return f'${value:,.2f}'

def _fmt_percent_unsigned(fraction: float) -> str:
    return f'{fraction * 100:.1f}%'
```
All new numeric display in Phase 15 uses these exact formatters — no new formatters needed.

**HTML escaping pattern** (lines 1022-1036): every dynamic value goes through `html.escape(value, quote=True)` at the leaf render site. The `_fmt_pnl_with_colour` helper (lines 612-634) shows the combined format-then-escape pattern for coloured spans.

**Per-instrument tbody extension pattern** (lines 1127-1141):
```python
tbody_blocks.append(
    f'    <tbody id="position-group-{state_key_esc}" '
    f'''hx-headers='{{"X-Trading-Signals-Auth": "{{{{WEB_AUTH_SECRET}}}}"}}' '''
    f'hx-trigger="positions-changed from:body" '
    f'hx-get="/?fragment=position-group-{state_key_esc}" '
    f'hx-swap="innerHTML">\n'
    f'{row_html}'
    f'    </tbody>\n'
)
```
Phase 15 `_render_calc_row` output is appended after `row_html` inside each `<tbody>` block, producing a second `<tr class="calc-row">` as its sibling.

**calc-row local import pattern** (C-2 convention):
```python
def _render_calc_row(state: dict, state_key: str, pos: dict) -> str:
    from sizing_engine import get_trailing_stop, check_pyramid  # local — C-2
    # ... render STOP, DIST, NEXT ADD, LEVEL, IF HIGH cells
```

**Side-by-side stop cell** — replaces the existing Phase 14 `trail_cell` logic (lines 1043-1052):
```python
# Existing Phase 14 pattern (to be replaced for manual_stop set case):
if pos.get('manual_stop') is not None:
    trail_cell = (
        f'{trail_currency} '
        f'<span class="badge badge-manual" title="...">manual</span>'
    )
else:
    trail_cell = trail_currency

# Phase 15 D-10 replacement for the manual_stop is not None branch:
if pos.get('manual_stop') is not None:
    manual_val = html.escape(_fmt_currency(pos['manual_stop']), quote=True)
    computed_val = html.escape(_fmt_currency(trail_stop), quote=True)
    trail_cell = (
        f'<td class="trail-stop-split">'
        f'<span class="manual-stop-val">manual: {manual_val}</span>'
        f'<span class="stop-sep"> | </span>'
        f'<span class="computed-stop-val">computed: {computed_val} <em>(will close)</em></span>'
        f'</td>'
    )
```

**Drift banner pattern** — placed BEFORE `_render_positions_table` section in `render_dashboard`, mirroring the `_render_header_email` critical-banner-before-content ordering:
```python
def _render_drift_banner(state: dict) -> str:
    '''Phase 15 SENTINEL-01/02: amber (drift) or red (reversal) banner.
    Rendered BEFORE Open Positions section per D-13 stack hierarchy.
    Returns empty string when no drift warnings present.
    '''
    drift_warnings = [
        w for w in state.get('warnings', [])
        if w.get('source') == 'drift'
    ]
    if not drift_warnings:
        return ''
    has_reversal = any('reversal recommended' in w.get('message', '') for w in drift_warnings)
    css_class = 'sentinel-banner sentinel-reversal' if has_reversal else 'sentinel-banner sentinel-drift'
    lines_html = '\n'.join(
        f'        <li>{html.escape(w["message"], quote=True)}</li>'
        for w in drift_warnings
    )
    return (
        f'<div class="{css_class}" role="alert" aria-live="polite">\n'
        f'  <p class="sentinel-heading">Drift detected</p>\n'
        f'  <ul class="sentinel-body">\n'
        f'{lines_html}\n'
        f'  </ul>\n'
        f'</div>\n'
    )
```

---

### `notifier.py` — `_has_critical_banner` extension + `_render_drift_banner` + `_render_header_email` insertion

**Analog:** `notifier.py:_has_critical_banner` (lines 548-564) + `_render_header_email` critical banner 2 block (lines 616-641)

**`_has_critical_banner` extension** (lines 548-564) — add a third `if` branch INSIDE the `for w in state.get('warnings', [])` loop:
```python
def _has_critical_banner(state: dict) -> bool:
    if state.get('_stale_info'):
        return True
    for w in state.get('warnings', []):
        if (
            w.get('source') == 'state_manager'
            and w.get('message', '').startswith('recovered from corruption')
        ):
            return True
        if w.get('source') == 'drift':   # NEW Phase 15
            return True
    return False
```

**Email banner inline-CSS pattern** (lines 600-614, critical banner 1):
```python
parts.append(
    f'<tr><td style="padding:12px 16px;background:{_COLOR_SURFACE};'
    f'border-left:4px solid {_COLOR_SHORT};'
    f'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\','
    f'Roboto,sans-serif;font-size:14px;color:{_COLOR_TEXT};'
    f'line-height:1.5;">'
    f'<p style="margin:0 0 4px 0;font-size:16px;font-weight:700;'
    f'color:{_COLOR_TEXT};letter-spacing:0.02em;">'
    f'━━━ Stale state ━━━</p>'
    f'<p style="margin:0;color:{_COLOR_TEXT_MUTED};font-size:13px;">'
    f'{safe_msg}</p>'
    f'</td></tr>\n'
    f'<tr><td height="16" style="height:16px;font-size:0;line-height:0;">'
    f'&nbsp;</td></tr>\n'
)
```

**Drift banner insertion point** — AFTER critical banner 2 (corrupt-reset, line 641), BEFORE `# --- HERO CARD ---` (line 643). The insertion is a new `# --- CRITICAL BANNER 3: drift/reversal (Phase 15) ---` block.

**Drift banner email pattern** (inline-CSS version of dashboard banner; body text reuses `DriftEvent.message` strings from `state['warnings']`):
```python
# --- CRITICAL BANNER 3: drift/reversal (Phase 15 D-02/D-03/D-12/D-13) ---
drift_warnings = [
    w for w in state.get('warnings', [])
    if w.get('source') == 'drift'
]
if drift_warnings:
    has_reversal = any(
        'reversal recommended' in w.get('message', '') for w in drift_warnings
    )
    border_color = _COLOR_SHORT if has_reversal else _COLOR_FLAT
    bullet_lines = '<br>\n      '.join(
        f'&bull; {html.escape(w["message"], quote=True)}'
        for w in drift_warnings
    )
    parts.append(
        f'<tr><td style="padding:12px 16px;background:{_COLOR_SURFACE};'
        f'border-left:4px solid {border_color};'
        f'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\','
        f'Roboto,sans-serif;font-size:14px;color:{_COLOR_TEXT};'
        f'line-height:1.5;">'
        f'<p style="margin:0 0 4px 0;font-size:14px;font-weight:600;'
        f'color:{_COLOR_TEXT};letter-spacing:0.02em;">'
        f'━━━ Drift detected ━━━</p>'
        f'<p style="margin:0;color:{_COLOR_TEXT_MUTED};font-size:13px;line-height:1.6;">'
        f'{bullet_lines}</p>'
        f'</td></tr>\n'
        f'<tr><td height="16" style="height:16px;font-size:0;line-height:0;">'
        f'&nbsp;</td></tr>\n'
    )
```

**Note on `_format_drift_lines` helper (D-12):** Both dashboard and email renderers extract `w['message']` from `state['warnings']` where `source == 'drift'`. The shared helper is the `DriftEvent.message` string itself — no separate Python function is needed. The lockstep parity test asserts the bullet text matches between both renderers given the same warning entries.

---

### `tests/test_signal_engine.py` — `FORBIDDEN_MODULES_DASHBOARD` constant update

**Analog:** `tests/test_signal_engine.py` lines 556-565

**Current constant** (lines 556-558):
```python
FORBIDDEN_MODULES_DASHBOARD = frozenset({
    # Sibling hexes — dashboard.py is a peer, never imports them
    'signal_engine', 'sizing_engine', 'data_fetcher', 'notifier', 'main',
```

**Phase 15 change** — remove `'sizing_engine'` from the frozenset and add a regression comment:
```python
FORBIDDEN_MODULES_DASHBOARD = frozenset({
    # Sibling hexes — dashboard.py is a peer, never imports them
    # NOTE: sizing_engine is ALLOWED as of Phase 15 (CALC-01..04 calculator
    # sub-row uses sizing_engine locally per C-2; CONTEXT D-01 explicit approval).
    'signal_engine', 'data_fetcher', 'notifier', 'main',
    # Heavy scientific stack (stdlib statistics + math are sufficient per D-07)
    'numpy', 'pandas',
    ...
})
```

---

### `tests/test_sizing_engine.py` — `TestDetectDrift` class

**Analog:** `tests/test_sizing_engine.py:TestExits` (lines 405-519)

**Class docstring pattern** (lines 405-422):
```python
class TestExits:
  '''EXIT-06..09 unit tests for get_trailing_stop + check_stop_hit.

  D-15 anchor: stop distance uses position['atr_entry'] (NOT the `atr` argument).
  Some tests pass a deliberately-wrong `atr=999.0` to prove the parameter is
  ignored — the result should still be the entry-ATR-anchored value.
  ...
  '''
```

**Test method naming convention** — descriptive, covers the exact scenario:
```python
def test_long_trailing_stop_peak_update(self) -> None:
    '''EXIT-06 + D-15: LONG stop = peak_price - TRAIL_MULT_LONG * atr_entry.
    peak=7050, atr_entry=53 -> stop = 7050 - 3*53 = 6891.0.
    Pass atr=999 to prove the argument is ignored (D-15 anchor).'''
    pos = _make_position(direction='LONG', peak_price=7050.0, atr_entry=53.0)
    assert get_trailing_stop(pos, current_price=7100.0, atr=999.0) == 6891.0
```

**`_make_position` helper pattern** — used throughout TestExits. `TestDetectDrift` uses the same helper for building `positions` dict (the `pos` values for `detect_drift`'s first arg).

**`TestDetectDrift` structure**:
- 15 test methods covering all `(held_direction, signal_direction)` × `(instrument)` combinations
- Tests for D-04 conservative skip (missing signal, int-shape signal)
- Tests asserting `DriftEvent` field values (instrument, held_direction, signal_direction, severity, message)
- Tests asserting exact message strings per D-14 template

---

### `tests/test_state_manager.py` — `TestClearWarningsBySource` class

**Analog:** `tests/test_state_manager.py:TestClearWarnings` (lines 1328-1379)

**Class template to copy verbatim structure from**:
```python
class TestClearWarnings:
  '''Phase 8 D-02: clear_warnings empties state['warnings'] in place and
  returns the same dict. Preserves D-10 sole-writer invariant...'''

  def test_clear_warnings_empties_list(self) -> None:
    state = reset_state()
    fixed_now = datetime(2026, 4, 22, 9, 30, 0, tzinfo=UTC)
    state = append_warning(state, 'sizing_engine', 'msg 1', now=fixed_now)
    state = append_warning(state, 'state_manager', 'msg 2', now=fixed_now)
    state = append_warning(state, 'notifier', 'msg 3', now=fixed_now)
    assert len(state['warnings']) == 3, 'precondition: 3 warnings appended'
    result = clear_warnings(state)
    assert result['warnings'] == []

  def test_clear_warnings_in_place_mutation(self) -> None:
    ...
    result = clear_warnings(state)
    assert result is state  # same reference
```

`TestClearWarningsBySource` follows this template exactly, with the critical difference being 3-source setup + asserting the matching source is removed AND the non-matching sources remain.

---

### `tests/test_web_dashboard.py` — `TestForwardStopFragment` + `TestSideBySideStopDisplay`

**Analog:** Existing `tests/test_web_dashboard.py` structure (Phase 14 tests for fragment responses and position row rendering).

**Fragment test client pattern** (from existing test_web_dashboard.py Phase 14 tests):
```python
# Set up TestClient with the FastAPI app
from fastapi.testclient import TestClient
# ... test GET with fragment param ...
response = client.get('/?fragment=forward-stop&instrument=SPI200&z=7850.00',
                      headers={'X-Trading-Signals-Auth': 'test-secret'})
assert response.status_code == 200
assert 'id="forward-stop-SPI200-w"' in response.text
```

**Bit-identical parity test pattern** (per D-07) — directly calls `sizing_engine.get_trailing_stop` and compares to fragment handler output:
```python
def test_forward_stop_matches_sizing_engine_bit_for_bit(self) -> None:
    # Build synthesized position as the handler would
    synth = dict(base_pos)
    synth['peak_price'] = max(base_pos.get('peak_price') or base_pos['entry_price'], z)
    expected_w = get_trailing_stop(synth, 0.0, 0.0)
    # Call the fragment endpoint and extract value from span
    response = client.get(f'/?fragment=forward-stop&instrument=SPI200&z={z}', ...)
    assert _fmt_currency(expected_w) in response.text
```

---

### `tests/test_dashboard.py` — `TestRenderCalculatorRow` + `TestRenderDriftBanner`

**Analog:** Existing `tests/test_dashboard.py` render tests.

**Dashboard render test pattern** — builds a `state` dict directly (not via `load_state`), calls the private render function, asserts HTML substring:
```python
def test_some_render(self) -> None:
    state = _make_state_with_position(direction='LONG', ...)
    html_out = _render_single_position_row(state, 'SPI200', state['positions']['SPI200'])
    assert 'Trail Stop' in html_out or '$7,640' in html_out
```

`TestRenderCalculatorRow` uses `_render_calc_row` (new helper) with the same pattern. `TestRenderDriftBanner` calls `_render_drift_banner` directly with a state that has `warnings` containing `source='drift'` entries.

---

### `tests/test_notifier.py` — `TestDriftBanner` + `TestBannerStackOrder`

**Analog:** Existing `tests/test_notifier.py` tests for `_has_critical_banner` and email render.

**`_has_critical_banner` test pattern** — populates `state['warnings']` with a specific source and asserts the return value:
```python
def test_has_critical_banner_drift_source(self) -> None:
    state = reset_state()
    state = append_warning(state, source='drift', message='You hold LONG SPI200...')
    assert _has_critical_banner(state) is True

def test_has_critical_banner_no_drift(self) -> None:
    state = reset_state()
    assert _has_critical_banner(state) is False
```

**Parity test pattern** (D-12) — same DriftEvent messages must appear byte-for-byte in both dashboard and email output:
```python
def test_drift_banner_body_parity_with_dashboard(self) -> None:
    message = 'You hold LONG SPI200, today\'s signal is FLAT — consider closing.'
    state['warnings'].append({'source': 'drift', 'message': message, 'date': '2026-04-26'})
    dashboard_html = _render_drift_banner(state)
    email_html = _render_header_email(state, now=...)
    assert message in dashboard_html
    assert message in email_html
```

---

### `tests/test_main.py` — `TestDriftWarningLifecycle`

**Analog:** Existing `tests/test_main.py` W3 invariant test and run_daily_check integration tests.

**W3 invariant test pattern** (existing):
```python
def test_happy_path_save_state_called_exactly_twice(self, ...):
    # mock mutate_state / save_state and count calls
    # assert call_count == 2
```

**`TestDriftWarningLifecycle` extends this**: after a mocked run that produces signals, asserts that:
1. `clear_warnings_by_source('drift')` was called before `detect_drift`
2. `detect_drift` was called with `(state['positions'], state['signals'])`
3. `append_warning` was called for each DriftEvent
4. `mutate_state` call count is still exactly 2 (W3 invariant preserved)

---

## Shared Patterns

### Local import discipline (C-2 — Phase 11 carry-forward)
**Source:** `web/routes/trades.py` lines 466-467, `web/routes/dashboard.py` lines 117-118
**Apply to:** Every new import of `sizing_engine` in `web/routes/dashboard.py` (forward-stop handler) and `web/routes/trades.py` (_apply mutators), and all `sizing_engine` imports in `dashboard.py` (`_render_calc_row`).
```python
# Pattern: local import inside function body, NOT at module top
def _render_calc_row(state, state_key, pos):
    from sizing_engine import get_trailing_stop, check_pyramid  # local — C-2
```

### HTML escaping at leaf render sites
**Source:** `dashboard.py` lines 1022-1036, `notifier.py:_render_header_email` lines 597-614
**Apply to:** All new `dashboard.py` render helpers, all new `notifier.py` email banner blocks.
```python
# Every dynamic value: html.escape(value, quote=True) at the leaf
instrument_cell = html.escape(display, quote=True)
safe_msg = html.escape(w.get('message', ''), quote=True)
```

### Sole-writer invariant for `state['warnings']`
**Source:** `state_manager.py` lines 591-619 (`append_warning` docstring)
**Apply to:** `web/routes/trades.py` `_apply` mutators, `main.py` drift recompute step
```python
# ONLY state_manager.append_warning writes to state['warnings'].
# Never: state['warnings'].append({...}) directly.
state = state_manager.append_warning(state, source='drift', message=ev.message)
```

### `state.get(key, [])` defensive reads on warning lists
**Source:** `notifier.py` lines 558, 620, 649; `dashboard.py` various
**Apply to:** All new code reading `state['warnings']` for drift entries.
```python
for w in state.get('warnings', []):  # NOT state['warnings'] — defensive
```

### `_COLOR_*` constants for banner borders
**Source:** `notifier.py` lines 600-601, 628-629; `system_params.py` lines 122-130
**Apply to:** `dashboard.py:_render_drift_banner` (CSS class variables) and `notifier.py:_render_drift_banner` (inline-CSS).
- Reversal border: `_COLOR_SHORT` (`#ef4444`)
- Drift-only border: `_COLOR_FLAT` (`#eab308`)

### `mutate_state` closure pattern
**Source:** `state_manager.py` lines 550-589, `web/routes/trades.py` lines 533, 599, 636
**Apply to:** Any new web handler that modifies state (no new ones in Phase 15, but the drift block goes INSIDE existing `_apply` closures).
```python
def _apply(state):      # receives freshly loaded state
    # ... mutate state in place ...
    # return value is IGNORED by mutate_state
mutate_state(_apply)    # mutate_state returns the post-mutation state
```

---

## No Analog Found

None — all files have strong analogs in the codebase.

---

## Metadata

**Analog search scope:** `sizing_engine.py`, `state_manager.py`, `main.py`, `web/routes/trades.py`, `web/routes/dashboard.py`, `dashboard.py`, `notifier.py`, `tests/test_sizing_engine.py`, `tests/test_state_manager.py`, `tests/test_signal_engine.py`
**Files read:** 10 source files + 3 test files
**Pattern extraction date:** 2026-04-26

### Key constraints confirmed by source inspection

1. `FORBIDDEN_MODULES_DASHBOARD` (test_signal_engine.py lines 556-565) currently contains `'sizing_engine'` — **must be removed** before any `from sizing_engine import ...` in `dashboard.py` can pass the AST gate test.

2. `get_trailing_stop(position, current_price, atr)` — `current_price` is deleted on line 234 and `atr` is deleted on line 235. Passing `0.0` for both is correct for the forward-look use case.

3. `_apply_daily_run` closure in `main.py` (lines 1299-1310) copies `'warnings'` key from `_accumulated` to `fresh_state`. Drift warnings appended to `state` BEFORE `_accumulated = state` will be included in the `mutate_state` save — no extra save needed.

4. `clear_warnings` (full clear, lines 621-643) is used ONLY in `_dispatch_email_and_maintain_warnings`. `clear_warnings_by_source` is the new Phase 15 scoped-clear function. These must NOT be confused (Pitfall 8 in RESEARCH.md).

5. The `_render_header_email` insertion point for the drift banner is AFTER the corrupt-reset block (line 641, after the last `parts.append(...)` for critical banner 2) and BEFORE `parts.append(_render_hero_card_email(state, now))` on line 644. This matches D-13 hierarchy: corruption → stale → reversal/drift → hero card.
