# Phase 19: Paper-trade Ledger — Pattern Map

**Mapped:** 2026-04-30
**Files analyzed:** 22 new symbols / files (10 source-side, 12 test-side)
**Analogs found:** 19 strong / 3 design-from-scratch
**Hex-boundary risks:** 1 documented (CONTEXT D-14 wording vs. actual codebase reality — both `system_params` and `state_manager` ARE allowed for `dashboard.py` per `FORBIDDEN_MODULES_DASHBOARD`)

---

## File Classification

| New / Modified Symbol | Role | Data flow | Closest analog | Match |
|-----------------------|------|-----------|----------------|-------|
| `_migrate_v5_to_v6` (state_manager.py) | I/O hex / migration | transform | `_migrate_v4_to_v5` (state_manager.py:185) | exact |
| `MIGRATIONS[6] = _migrate_v5_to_v6` | dispatch table entry | wiring | `MIGRATIONS[5]` (state_manager.py:220) | exact |
| `STATE_SCHEMA_VERSION = 6` | constant bump | wiring | Phase 17 bump 4→5 (system_params.py:121) | exact |
| `pnl_engine.py` (NEW module) | pure-math | transform | `sizing_engine.py::compute_unrealised_pnl` (sizing_engine.py:479-512) | exact |
| `compute_unrealised_pnl` (pnl_engine.py) | pure-math | transform | `sizing_engine.compute_unrealised_pnl` (sizing_engine.py:479-512) | exact |
| `compute_realised_pnl` (pnl_engine.py) | pure-math | transform | `sizing_engine.compute_unrealised_pnl` shape; close-side math via `record_trade` D-14 (state_manager.py:749+) | adapt |
| `web/routes/paper_trades.py` (NEW) | adapter / mutation route | request-response | `web/routes/trades.py` (web/routes/trades.py:1-729) | exact |
| `register(app)` mount (web/app.py:158) | wiring | wiring | `trades_route.register(application)` (web/app.py:158) | exact |
| `_validate_open_form` helper | adapter validator | transform | `OpenTradeRequest` Pydantic model + `@model_validator` chain (web/routes/trades.py:95-145) | adapt (CONTEXT picks dict-helper over Pydantic — see note) |
| `_compute_next_trade_id` (composite ID generator) | adapter helper | transform | NONE — Phase 14 used Pydantic auto-IDs / instrument as PK | design-from-scratch |
| `_method_not_allowed_405` helper | adapter helper | transform | NONE — first manual 405 in repo (RESEARCH §Pitfall 2) | design-from-scratch |
| `_check_immutable` (close-row guard) | adapter helper | transform | `_OpenConflict` sentinel (web/routes/trades.py:81-87) | role-match (sentinel pattern, different status code) |
| `_render_paper_trades_open` (dashboard.py) | render hex | transform | `_render_positions_table` (dashboard.py:1955-2059) | exact |
| `_render_paper_trades_closed` (dashboard.py) | render hex | transform | `_render_trades_table` (dashboard.py:2062+) | exact |
| `_render_paper_trades_stats` (dashboard.py) | render hex | transform | `_render_key_stats` (dashboard.py:2131) + `_render_trace_panels` (dashboard.py:1361) | role-match |
| `_render_paper_trades_region` (orchestrator) | render hex | transform | `render_dashboard` body composition (dashboard.py:2430-2444) | exact |
| `_compute_aggregate_stats` | pure-ish helper | transform | `_compute_total_return` / `_compute_sharpe` / `_compute_win_rate` (dashboard.py:817-878) | exact |
| `render_dashboard` body extension | composition | wiring | Phase 17 trace-panel insertion via `_render_signal_cards` calling `_render_trace_panels` per-card (dashboard.py:1465) | role-match |
| Inline CSS additions (`.stats-bar`, `.paper-trades-table`, `.row-clickable`, `.pnl-positive/negative/zero`) | render hex | transform | `_INLINE_CSS` block (dashboard.py:196-…) | exact |
| `tests/test_state_manager.py::TestMigrateV5ToV6` | test | request-response | `TestMigrateV4ToV5` (tests/test_state_manager.py:2095-2304) | exact |
| `tests/test_pnl_engine.py` (NEW) | test | request-response | `tests/test_sizing_engine.py` (sibling) + parametrize grid in RESEARCH Pattern 10 | exact |
| `tests/test_web_paper_trades.py` (NEW) | test | request-response | `tests/test_web_trades.py` (entire file) | exact |
| `tests/test_dashboard.py::TestRenderPaperTrades` | test | request-response | `tests/test_dashboard.py::TestRenderBlocks` (test_dashboard.py:606-…) | exact |
| `tests/fixtures/state_v6_with_paper_trades.json` | test fixture | data | `tests/fixtures/dashboard/sample_state_v5.json` + `tests/fixtures/state_v2_no_manual_stop.json` | exact |
| AST forbidden-imports extension for `pnl_engine.py` | test | wiring | `_HEX_PATHS_ALL` parametrize list (tests/test_signal_engine.py:590) + `FORBIDDEN_MODULES_STDLIB_ONLY` (tests/test_signal_engine.py:500) | exact |
| HTMX TestClient PATCH/DELETE | test | request-response | NONE — Phase 14 only uses POST + GET | design-from-scratch (RESEARCH §Pattern 8 spells it out) |
| `multiprocessing.Process` race test | test | request-response | NONE in this codebase; RESEARCH §Pattern 9 designed-from-scratch | design-from-scratch |

---

## Pattern Assignments

### `_migrate_v5_to_v6` (state_manager.py)

**Closest analog:** `state_manager.py:185-212` — `_migrate_v4_to_v5`
**Why this analog:** Same shape (top-level dict mutation, idempotency guard, silent migration with no log/warning), and Phase 17 just shipped this pattern 24 hours ago.

**Pattern to copy** (verbatim docstring shape + idempotency guard):
```python
# state_manager.py:185-212 verbatim docstring shape
def _migrate_v4_to_v5(s: dict) -> dict:
  '''Phase 17 D-08 (v1.2): backfill empty ohlc_window + indicator_scalars
  on existing dict-shaped signal rows.
  ...
  Idempotent: rows that already carry a populated ohlc_window or
  indicator_scalars are NOT overwritten (defensive — supports replayed
  migrations and partial-state edits).
  ...
  D-15 silent migration: no append_warning, no log line.
  '''
  signals = s.get('signals', {})
  for inst_key, sig in signals.items():
    if isinstance(sig, dict):
      if 'ohlc_window' not in sig:
        sig['ohlc_window'] = []
      if 'indicator_scalars' not in sig:
        sig['indicator_scalars'] = {}
  return s
```

**Pattern to adapt:**
- Phase 19 mutates the **top-level** state dict (adds `paper_trades = []`), not nested `signals.values()`. Single membership check: `if 'paper_trades' not in s`.
- Return a **new dict** via `{**s, 'paper_trades': s.get('paper_trades', [])}` is also acceptable; the v4→v5 idiom mutates in-place and returns. CONTEXT D-08 spec uses in-place + return — match it.

**Hex-boundary check:** clean. `state_manager` is the I/O hex; migrations are its purpose.

---

### `MIGRATIONS[6] = _migrate_v5_to_v6`

**Closest analog:** `state_manager.py:215-221` — the existing `MIGRATIONS` dispatch table.

**Pattern to copy:**
```python
# state_manager.py:215-221
MIGRATIONS: dict = {
  1: lambda s: s,
  2: _migrate_v1_to_v2,
  3: _migrate_v2_to_v3,
  4: _migrate_v3_to_v4,
  5: _migrate_v4_to_v5,
  # 6: _migrate_v5_to_v6,   <-- Phase 19 appends here
}
```

**Pattern to adapt:** none — append a single line.

**Hex-boundary check:** clean.

---

### `STATE_SCHEMA_VERSION = 6` (system_params.py)

**Closest analog:** `system_params.py:121` — the existing constant + trailing-comment bump log.

**Pattern to copy:** keep the trailing-comment audit trail; append `; Phase 19 → v6 (paper_trades[] top-level array; D-08)`.

```python
# system_params.py:121 — current
STATE_SCHEMA_VERSION: int = 5  # bump on each schema change (STATE-04); Phase 14 → v3 (manual_stop on Position; D-09); Phase 22 → v4 (strategy_version on signal rows; D-04); Phase 17 → v5 (ohlc_window + indicator_scalars on signal rows; D-08)
```

**Pattern to adapt:** flip `5` → `6` and extend the trailing audit string.

**Hex-boundary check:** clean.

---

### NEW MODULE — `pnl_engine.py`

**Closest analog:** `sizing_engine.py:1-32` (module docstring + import block) + `sizing_engine.py:479-512` (`compute_unrealised_pnl`).

**Why this analog:** Phase 19 D-11 explicitly mirrors the Phase 2 D-13/D-17 invariants. `sizing_engine.compute_unrealised_pnl` is the literal shape: `(side, entry_price, current_price, contracts, multiplier, cost_aud_open) -> float`.

**Pattern to copy** (module docstring shape + AST forbidden-import contract):
```python
# sizing_engine.py:1-15 verbatim shape — DO copy
'''Sizing Engine — pure-math position sizing, ...

Architecture (hexagonal-lite, CLAUDE.md): pure math ONLY. Imports system_params
(constants ...). Must NOT import state_manager, notifier, dashboard, main, requests,
datetime, os, or any I/O/network/clock module.
'''
import math
from system_params import (
  ...
)
```

**Core formula pattern from sizing_engine.py:479-512:**
```python
def compute_unrealised_pnl(
  position: Position,
  current_price: float,
  multiplier: float,
  cost_aud_open: float,
) -> float:
  direction_mult = 1.0 if position['direction'] == 'LONG' else -1.0
  price_diff = current_price - position['entry_price']
  gross = direction_mult * price_diff * position['n_contracts'] * multiplier
  open_cost = cost_aud_open * position['n_contracts']
  return gross - open_cost
```

**Pattern to adapt:**
- `pnl_engine` takes **plain floats**, not a `Position` TypedDict. Paper trades are dicts; do NOT couple to `Position` (RESEARCH anti-pattern). Signature mirrors RESEARCH §Pattern 5:
  `compute_unrealised_pnl(side: str, entry_price, last_close, contracts, multiplier, entry_cost_aud) -> float`
  `compute_realised_pnl(side: str, entry_price, exit_price, contracts, multiplier, round_trip_cost_aud) -> float`
- Cost handling differs from sizing_engine: `compute_unrealised_pnl` deducts the `entry_cost_aud` (= half-RT, per D-02). `compute_realised_pnl` deducts the **full** `round_trip_cost_aud` at close-time (CONTEXT D-11 — both halves applied at close in Phase 19, unlike sizing_engine which splits across `compute_unrealised_pnl` + `record_trade` D-14).
- Branch `if side == 'LONG': ... else: # SHORT` (RESEARCH §Pattern 5 explicit). NaN `last_close` propagates naturally (RESEARCH §Pitfall 5 verified).
- No imports from `system_params` are strictly required if the caller passes the multiplier and cost as floats. Keep `pnl_engine` `import math` only — caller-side adapters supply constants.

**Hex-boundary check:** clean. Forbidden imports identical to `sizing_engine.py` (`state_manager`, `notifier`, `dashboard`, `main`, `requests`, `datetime`, `os`, `numpy`, `pandas`, `yfinance`, etc.). AST guard (test_signal_engine.py:590, `_HEX_PATHS_ALL` + `_HEX_PATHS_STDLIB_ONLY`) **must be extended** to include `pnl_engine.py` in both lists.

---

### NEW MODULE — `web/routes/paper_trades.py`

**Closest analog:** `web/routes/trades.py:1-729` — the entire file.

**Why this analog:** Phase 14 owns the canonical mutation-route shape: hex-fence comment block, `register(app)` factory, Pydantic v2 request models with `extra='forbid'` + `@model_validator(mode='after')`, `_OpenConflict` sentinel raised inside `_apply` so `mutate_state` releases the lock before HTTP-response construction (RESEARCH §Pitfall 6), local imports of `state_manager` / `sizing_engine` / `system_params` inside handler bodies (Phase 11 C-2), and `hx-ext="json-enc"` discipline on HTMX-sent forms (RESEARCH §Pitfall 8).

**Module docstring + register pattern to copy** (web/routes/trades.py:1-72 + 455-462):
```python
'''POST /paper-trade/{open,close,...} — Phase 19 LEDGER-01..06 + D-01..D-16.
... contract block enumerating each D-XX decision ...

Architecture (CLAUDE.md hex-lite + Phase 14 D-14):
  web/routes/ is an adapter hex.
  Allowed: fastapi, starlette, stdlib, state_manager (read+WRITE per D-14),
           pnl_engine (Phase 19 — pure-math peer of sizing_engine),
           system_params (STRATEGY_VERSION + multiplier/cost constants).
  Forbidden: signal_engine, data_fetcher, notifier, main.

  state_manager + pnl_engine + system_params imports are LOCAL inside
  handler bodies per Phase 11 C-2.

Auth: Phase 13 AuthMiddleware gates /paper-trade/* automatically.
Log prefix: [Web].
'''
def register(app: FastAPI) -> None:
  @app.post('/paper-trade/open')
  def open_paper_trade(req: OpenPaperTradeRequest): ...
  @app.patch('/paper-trade/{trade_id}')
  def edit_paper_trade(trade_id: str, req: EditPaperTradeRequest): ...
  @app.delete('/paper-trade/{trade_id}')
  def delete_paper_trade(trade_id: str): ...
  @app.post('/paper-trade/{trade_id}/close')
  def close_paper_trade(trade_id: str, req: ClosePaperTradeRequest): ...
  @app.get('/paper-trade/{trade_id}/close-form')
  def close_form(trade_id: str): ...
  @app.get('/paper-trades')
  def get_paper_trades_fragment(): ...
```

**`_OpenConflict` sentinel pattern to copy** (web/routes/trades.py:81-87 + 543-559):
```python
# web/routes/trades.py:81-87 — copy literally; rename per Phase 19 conflict types.
class _PaperTradeConflict(Exception):
  '''Internal sentinel: raised inside `_apply` mutators so the
  mutate_state finally-blocks release the fcntl lock before the handler
  converts to an HTTP response (RESEARCH §Pitfall 6).'''

# Handler shape (web/routes/trades.py:543-559):
try:
  state = mutate_state(_apply)
except _PaperTradeConflict as exc:
  logger.warning('[Web] /paper-trade/... conflict: %s', exc)
  return Response(content=str(exc), status_code=..., media_type='text/plain; charset=utf-8')
```

**`_apply` closure with fresh-import of STRATEGY_VERSION** (web/routes/trades.py:467-541 + RESEARCH §Pattern 4 + LEARNINGS 2026-04-29 kwarg-default trap):
```python
def _apply(state):
  from system_params import STRATEGY_VERSION  # FRESH import inside closure — VERSION-03 critical
  rows = state.setdefault('paper_trades', [])
  ...
  rows.append({..., 'strategy_version': STRATEGY_VERSION, ...})
```

**Pydantic request-model pattern** (web/routes/trades.py:95-145):
```python
class OpenPaperTradeRequest(BaseModel):
  model_config = ConfigDict(extra='forbid')  # REVIEW HR-01: typo defence
  instrument: Literal['SPI200', 'AUDUSD']
  side: Literal['LONG', 'SHORT']
  entry_price: float = Field(gt=0)
  contracts: float = Field(gt=0)  # SPI integer enforced by post-validator
  entry_dt: datetime
  stop_price: float | None = None

  @model_validator(mode='after')
  def _coherence(self):
    # D-04 rules: stop on right side of entry, SPI integer contracts, etc.
    ...
```

**`hx-ext="json-enc"` discipline on HTMX form** (web/routes/trades.py:362-366 verbatim — REVIEW CR-01):
```python
# REVIEW CR-01: hx-ext="json-enc" converts the form-encoded body to JSON.
# Without it the FastAPI handler (Pydantic body parameter, no Form(...)) returns 400.
'<button ... hx-post="/paper-trade/open" hx-ext="json-enc" ...>'
```

**Pattern to adapt:**
- Phase 14 routes are organised by trade-action (open/close/modify); Phase 19 routes are organised by trade-id (PATCH/DELETE/close-form on `{trade_id}`). The handler bodies follow the same load-via-`_apply`, conflict-sentinel-on-not-found, render-fragment-on-success pattern.
- HTMX swap target is `#trades-region` outerHTML (CONTEXT D-13), not per-instrument tbody (Phase 14 HIGH #3). Simpler: a single `<div id="trades-region">` wraps stats-bar + open-table + close-form + closed-table; every mutation reflows the whole region.
- All four mutation routes (`open`, `close`, edit-PATCH, delete-DELETE) return the rendered region via a shared helper `_render_paper_trades_region(state)` from `dashboard.py` — CONTEXT D-12 + D-13.

**Hex-boundary check:** clean. Same allowed/forbidden imports as `web/routes/trades.py`. Local-import discipline preserved.

---

### `_validate_open_form(form_dict, ...) -> dict | HTTPException`

**Closest analog:** Phase 14 uses **Pydantic `@model_validator`** (web/routes/trades.py:118-145) rather than a dict-walking validator function. CONTEXT D-04 calls for a `_validate_open_form` helper specifically.

**Why this analog (Pydantic model_validator):** It enforces D-04 cleanly: `Field(gt=0)` for prices/contracts, `Literal[...]` for instrument/side, `@model_validator(mode='after')` for cross-field coherence (stop_price on right side of entry; SPI integer; future-dated `entry_dt`).

**Pattern to copy** (web/routes/trades.py:118-145 verbatim shape):
```python
@model_validator(mode='after')
def _coherence(self):
  for name, val in (('entry_price', self.entry_price), ...):
    if val is not None and not math.isfinite(val):
      raise ValueError(f'{name}: must be finite (not NaN/+/-inf)')
  if self.side == 'LONG' and self.stop_price is not None:
    if self.stop_price >= self.entry_price:
      raise ValueError('stop_price: must be < entry_price for LONG')
  ...
  return self
```

**Pattern to adapt:**
- Pydantic v2 raises `RequestValidationError` → 422 → remapped to **400** by the global handler in web/app.py:175-177 + web/routes/trades.py:241-256. CONTEXT D-04 specifies **422** for paper trades. Decide one: either (a) add a per-route `paper_trades` validation handler that returns 422 (skipping the global 400 remap), or (b) follow the codebase convention of 400 (and update CONTEXT D-04 in a follow-up). RESEARCH §Pitfall 8 references 422; the existing handler returns 400. **Flag for planner — coverage gate question.**
- If CONTEXT picks the explicit "validator function" shape (D-04 wording: `_validate_open_form(form_dict) -> dict | HTTPException`), the closest analog is the Pydantic-model-then-`model_validator` chain transposed to a manual function — but no such manual validator exists in the codebase. The Pydantic path is recommended.

**Hex-boundary check:** clean (Pydantic is allowed in adapter hex).

---

### `_compute_next_trade_id(paper_trades, instrument, entry_dt) -> str`

**Closest analog:** **NONE in the codebase.** Phase 14 has no composite ID generator — instruments themselves are PKs (one position per instrument). Phase 3 trades are stored as a list with no ID column.

**Why no analog:** CONTEXT D-01's `<INSTRUMENT>-<YYYYMMDD>-<NNN>` ID is a Phase 19 first.

**Pattern to design from scratch** (RESEARCH §Pattern 4 inside `_apply`):
```python
def _apply(state):
  rows = state.setdefault('paper_trades', [])
  today_awst = _now_awst().strftime('%Y%m%d')
  prefix = f'{req.instrument}-{today_awst}-'
  same_day = [r for r in rows if r['id'].startswith(prefix)]
  if len(same_day) >= 999:
    raise _PaperTradeConflict(
      f'ID counter overflow for {req.instrument} on {today_awst}; '
      'edit state.json to free counter slots'
    )
  counter = len(same_day) + 1
  trade_id = f'{prefix}{counter:03d}'
```

**Adjacent precedents:**
- AWST date computation: `_now_awst()` at web/routes/trades.py:73-78 (`datetime.now(_AWST)` with `zoneinfo.ZoneInfo('Australia/Perth')`) — copy verbatim.
- Counter-overflow loud-failure pattern: CONTEXT risk-register `test_id_counter_overflow_999_raises_explicit_error`. No in-repo analog; design per CONTEXT.

**Hex-boundary check:** clean — runs inside `_apply` closure (adapter), not inside `pnl_engine`.

---

### `_method_not_allowed_405(allow: str) -> Response` helper

**Closest analog:** **NONE in the codebase.** RESEARCH §Pitfall 2 + §Pattern 3 + direct Python execution confirms this is the **first manual 405 in the codebase**.

**Why no analog:** Existing handlers return 409 (`_OpenConflict` sentinel — web/routes/trades.py:548-550), 404 (web/routes/trades.py:694-697), or 400 (Pydantic 422→400 remap). The CONTEXT D-05 closed-row-immutable contract requires 405 with `Allow: GET` per RFC 7231 §6.5.5.

**Pattern to design from scratch** (RESEARCH §Pattern 3 verbatim):
```python
from fastapi.responses import Response

def _method_not_allowed_405(allow: str = 'GET') -> Response:
  '''RFC 7231 §6.5.5 — 405 MUST include Allow header listing allowed methods.
  FastAPI auto-generated 405 (wrong method on a registered path) includes
  Allow automatically; this manual 405 (closed-row enforcement) does NOT —
  must be set explicitly.
  '''
  return Response(
    content='closed rows are immutable',
    status_code=405,
    headers={'Allow': allow},
    media_type='text/plain; charset=utf-8',
  )
```

**Pattern to copy from sentinel handling** (web/routes/trades.py:543-550): use a sentinel `_RowImmutable` that the handler's `try/except` converts to the 405 Response — keeps the lock-release-before-response invariant intact.

**Hex-boundary check:** clean.

---

### `_render_paper_trades_open` / `_closed` / `_stats` / `_region` (dashboard.py)

**Closest analog:** `dashboard.py:1955-2059` (`_render_positions_table`) for `_render_paper_trades_open`; `dashboard.py:2062+` (`_render_trades_table`) for `_render_paper_trades_closed`; `dashboard.py:2131` (`_render_key_stats`) for `_render_paper_trades_stats`; `render_dashboard` body composition (dashboard.py:2430-2444) for `_render_paper_trades_region`.

**Why this analog:** Phase 5 + Phase 14 + Phase 17 already established the per-block render-helper pattern. Each helper takes `state: dict`, returns a single `<section>...</section>` HTML string with `aria-labelledby`, `<table class="data-table">`, `<thead>`/`<tbody>`/`<caption>`, empty-state `<td colspan="...">` row.

**Pattern to copy** (dashboard.py:1990-2059 — table-skeleton boilerplate):
```python
def _render_positions_table(state: dict) -> str:
  positions = state.get('positions', {})
  tbody_blocks = []
  any_position = False
  for state_key in _INSTRUMENT_DISPLAY_NAMES:
    pos = positions.get(state_key)
    if pos is None:
      ...
      continue
    any_position = True
    state_key_esc = html.escape(state_key, quote=True)
    row_html = _render_single_position_row(state, state_key, pos)
    tbody_blocks.append(...)
  if not any_position:
    tbody_blocks.append(
      '    <tbody id="positions-empty">\n'
      '      <tr><td colspan="9" class="empty-state">— No open positions —</td></tr>\n'
      '    </tbody>\n'
    )
  return (
    _render_open_form() + '<section aria-labelledby="heading-positions">\n'
    '  <h2 id="heading-positions">Open Positions</h2>\n'
    '  <table class="data-table">\n'
    '    <caption class="visually-hidden">...</caption>\n'
    '    <thead><tr>...</tr></thead>\n'
    f'{"".join(tbody_blocks)}'
    '  </table></section>\n'
  )
```

**Per-cell escape pattern** (dashboard.py:2009): `html.escape(str(value), quote=True)` at every leaf. **Required** for paper-trade IDs, exit reasons, instrument names.

**Empty-state copy** (dashboard.py:2032 + CONTEXT D-16): single `<td colspan="N">` row with the literal copy from D-16. Verbatim CONTEXT.

**`render_dashboard` body extension pattern** (dashboard.py:2430-2444):
```python
body = (
  _render_header(state, now, is_cookie_session=is_cookie_session)
  + _render_signal_cards(state)
  + _render_paper_trades_region(state)   # <-- Phase 19 inserts here, between cards and equity
  + _render_equity_chart_container(state)
  + _render_drift_banner(state)
  + _render_positions_table(state)
  ...
)
```

**Pattern to adapt:**
- Phase 19 paper-trades tables iterate over `state.get('paper_trades', [])` filtered by `status`, NOT by `_INSTRUMENT_DISPLAY_NAMES`. Closed table sorts by `exit_dt` desc.
- Per-row MTM lookup: `last_close = signals.get(row['instrument'], {}).get('last_close')` then `pnl_engine.compute_unrealised_pnl(...)` if `last_close` is not None / not NaN; else render `n/a (no close price yet)` per CONTEXT D-07 + RESEARCH §Pitfall 5.
- Click-row UX (CONTEXT D-03): each open-row carries `data-trade-id` and a `<button class="btn-row btn-close" hx-get="/paper-trade/{id}/close-form" hx-target="#close-form-section" hx-swap="outerHTML">Close</button>`. Mirrors web/routes/trades.py:317-325 button shape exactly.
- Aggregate-stats helper `_compute_aggregate_stats(paper_trades, signals)` returns `{realised, unrealised, wins, losses, win_rate}` — render-helper takes the dict, formats each badge.

**Hex-boundary check:** clean. Phase 19 adds `from pnl_engine import compute_unrealised_pnl` at dashboard.py top (or LOCAL inside the helper for symmetry with sizing_engine). `pnl_engine` is **not** in `FORBIDDEN_MODULES_DASHBOARD` (tests/test_signal_engine.py:556-569). No new forbidden imports introduced.

---

### `_compute_aggregate_stats(paper_trades, signals) -> dict`

**Closest analog:** `dashboard.py:817-878` — `_compute_sharpe`, `_compute_max_drawdown`, `_compute_win_rate`, `_compute_total_return`. All take `state: dict`, return formatted `str`. CONTEXT D-06 spec returns a `dict` of primitives (5 keys) so the render helper can format each badge independently.

**Why this analog:** Same hex tier (pure-ish helper inside dashboard hex), same defensive empty-state guards (em-dash on degenerate input), same `state.get('...', default)` discipline.

**Pattern to copy** (dashboard.py:854-863 — `_compute_win_rate`):
```python
def _compute_win_rate(state: dict) -> str:
  closed = state.get('trade_log', [])
  if not closed:
    return _fmt_em_dash()
  wins = sum(1 for t in closed if t.get('gross_pnl', 0) > 0)
  return f'{wins / len(closed) * 100:.1f}%'
```

**Pattern to adapt:**
- Returns a 5-key `dict` (CONTEXT D-06: `realised`, `unrealised`, `wins`, `losses`, `win_rate`), not a single `str`. Render helper formats per-badge.
- `wins` counts `realised_pnl > 0`; `losses` counts `realised_pnl < 0`; **zero is neither** (CONTEXT D-06 explicit; risk-register `test_aggregate_stats_zero_pnl_excluded_from_wins_losses`).
- `unrealised` sums `pnl_engine.compute_unrealised_pnl(...)` over open rows, **skipping** rows where `last_close is None or math.isnan(...)` (CONTEXT D-07 + RESEARCH §Pitfall 5).
- `win_rate` returns `None` (or em-dash string per render-time decision) when `wins+losses == 0`.

**Hex-boundary check:** clean. Helper imports `pnl_engine` (allowed peer per D-14); no `state_manager` / `system_params` access required.

---

### Inline CSS — `.stats-bar`, `.paper-trades-table`, `.row-clickable`, `.pnl-positive/negative/zero`

**Closest analog:** `dashboard.py:196-…` — `_INLINE_CSS` f-string block.

**Why this analog:** Project ships zero external stylesheets; all CSS is one f-string with `:root` CSS-variable substitution from `_COLOR_*` constants.

**Pattern to copy** (dashboard.py:196-211 — variable-substitution structure):
```python
_INLINE_CSS = f'''
:root {{
  --color-bg: {_COLOR_BG};
  ...
  --space-3: 12px; --space-4: 16px; --space-6: 24px;
  ...
}}
body {{ ... }}
.container {{ max-width: 1100px; margin: 0 auto; ... }}
'''
```

**Pattern to adapt:**
- Append new rules to the same `_INLINE_CSS` f-string (RESEARCH §Pattern 7 dictates exact rules):
  ```css
  .stats-bar { position: sticky; top: 0; z-index: 10; display: flex;
               flex-wrap: wrap; gap: var(--space-4);
               background: var(--color-surface);
               border-bottom: 1px solid var(--color-border);
               padding: var(--space-3) var(--space-6); }
  .paper-trades-table { ... }
  .row-clickable { cursor: pointer; }
  .row-clickable:hover { background: var(--color-bg); }
  .pnl-positive { color: var(--color-long); }
  .pnl-negative { color: var(--color-short); }
  .pnl-zero { color: var(--color-text-dim); }
  ```
- `position: sticky` is **first occurrence** in the codebase. RESEARCH §Pitfall 4 confirms iOS Safari 17+ supports it without `-webkit-sticky`; the existing `<main>` has no `overflow` ancestor.
- Mobile breakpoint pattern follows RESEARCH §Pattern 7: `@media (max-width: 600px) { .stats-bar-item { min-width: calc(33% - var(--space-4)); } }`.

**Hex-boundary check:** clean.

---

### Mount in `web/app.py`

**Closest analog:** `web/app.py:158` — `trades_route.register(application)`.

**Why this analog:** Project uses `register(app)` factory pattern, not `app.use(...)` (CONTEXT mention is conceptual / Express-style). Each route module exposes a `register(app: FastAPI) -> None` function; `create_app()` calls each in registration order.

**Pattern to copy** (web/app.py:155-170):
```python
healthz_route.register(application)
dashboard_route.register(application)
state_route.register(application)
trades_route.register(application)
paper_trades_route.register(application)   # <-- Phase 19 inserts here
login_route.register(application)
totp_route.register(application)
devices_route.register(application)
reset_route.register(application)
```

**Pattern to adapt:**
- Add `from web.routes import paper_trades as paper_trades_route` at the top alongside other route imports (web/app.py:40-47).
- Mount immediately after `trades_route.register` so the AuthMiddleware (registered LAST per D-06) gates `/paper-trade/*` exactly like `/trades/*`.
- The 422→400 remap handler at web/app.py:175-177 already covers all routes; **no additional handler-add needed** unless CONTEXT D-04 picks 422 (see Validator section above — flagged for planner).

**Hex-boundary check:** clean.

---

### `tests/test_state_manager.py::TestMigrateV5ToV6`

**Closest analog:** `tests/test_state_manager.py:2095-2304` — `TestMigrateV4ToV5` (Phase 17, just shipped).

**Why this analog:** 24-hour-old precedent. Identical invariants: backfills on dict-shaped rows, additive (preserves other fields), idempotent (key-already-present guard), partial-state independence (multi-key migrations only), full-walk via `_migrate` ends at new schema_version.

**Pattern to copy** (verbatim test class shape — six methods):
- `test_migrate_v5_to_v6_backfills_paper_trades_when_absent` (mirrors `test_migrate_v4_to_v5_backfills_existing_signal_rows` line 2108-2150)
- `test_migrate_v5_to_v6_via_full_migrate_sets_schema_6` (mirrors line 2152-2187)
- `test_migrate_v5_to_v6_preserves_other_top_level_fields` (mirrors line 2189-2215)
- `test_migrate_v5_to_v6_idempotent_paper_trades_already_populated` (mirrors line 2217-2237)
- `TestFullWalkV0ToV6` class (mirrors `TestFullWalkV0ToV5` at line 2306+, extending the chain v0→…→v6)

**Pattern to adapt:**
- Phase 19's migration is single-key (top-level `paper_trades`), so the partial-state and skip-int-shape tests don't apply. Replace with a single `test_migrate_v5_to_v6_idempotent_when_paper_trades_already_has_rows` that seeds `paper_trades=[{...row...}]` and asserts the rows are preserved untouched.

**Hex-boundary check:** clean.

---

### `tests/test_pnl_engine.py` (NEW)

**Closest analog:** `tests/test_sizing_engine.py` (sibling pure-math module) + RESEARCH §Pattern 10 parametrize grid.

**Pattern to copy** (RESEARCH §Pattern 10 — verbatim parametrize grid):
- 7-row LONG/SHORT × SPI/AUDUSD × win/loss/edge grid for `compute_unrealised_pnl`
- 4-row LONG/SHORT × SPI/AUDUSD parametrize for `compute_realised_pnl`
- NaN propagation test: `test_compute_unrealised_pnl_nan_last_close` asserts `math.isnan(result)` (RESEARCH §Pitfall 5 verified).

**Pattern to adapt:** none — grid is fully specified in RESEARCH.

**Hex-boundary check:** clean.

---

### `tests/test_web_paper_trades.py` (NEW)

**Closest analog:** `tests/test_web_trades.py` (entire file).

**Why this analog:** Phase 14 ships every required pattern: HTMX-aware fixture (`client_with_state_v3` + `htmx_headers` from tests/conftest.py:198-280), state-stub + save-capture monkeypatch, `_OpenConflict` sentinel-test discipline, `assert r.status_code == ...` + body-substring assertions.

**Fixture pattern to copy** (tests/conftest.py:205-280): create a `client_with_state_v6` fixture that mirrors `client_with_state_v3` but seeds `paper_trades=[]` and bumps `schema_version=6`. Same `mutate_state` stub.

**Test grid to author:**
- POST /paper-trade/open valid → 200 + composite ID + `entry_cost_aud=3.0` (SPI) / `2.5` (AUDUSD)
- POST /paper-trade/open invalid (every D-04 rule × parametrize): future `entry_dt`, `entry_price <= 0`, `contracts <= 0`, fractional SPI contracts, wrong-side stop, etc. → 422 (or 400 — flag-decision-pending)
- PATCH /paper-trade/{id} of open row → 200 + fields updated + `strategy_version` refreshed
- PATCH /paper-trade/{id} of closed row → **405 + `closed rows are immutable` + `Allow: GET`** (RESEARCH §Pattern 8 verbatim assertions)
- DELETE /paper-trade/{id} of open row → 200 + row removed
- DELETE /paper-trade/{id} of closed row → 405 + Allow header
- POST /paper-trade/{id}/close → 200 + `realised_pnl` correct per D-11 hand-computed values for LONG/SHORT × SPI/AUDUSD
- Composite ID generation: `SPI200-20260430-001`, `SPI200-20260430-002`, `AUDUSD-20260430-001` parametrize
- ID counter overflow at 999 → explicit error (CONTEXT risk-register)
- **Concurrent-open race test** via `multiprocessing.Process` (RESEARCH §Pattern 9 verbatim) — first multiprocessing test in repo
- Cookie-auth middleware enforcement: PATCH/DELETE without cookie → 401 (Phase 16.1 pattern; tests/test_web_routes_devices.py is the closest analog for cookie-only routes)

**Pattern to adapt:**
- HTMX TestClient `client.patch(...)` and `client.delete(...)` — first use in repo (RESEARCH §Pattern 8). httpx supports both natively.

**Hex-boundary check:** clean. Test imports `from fastapi.testclient import TestClient`, `multiprocessing`, `fcntl`, `os`, `json` — all stdlib + test infra.

---

### `tests/test_dashboard.py::TestRenderPaperTrades`

**Closest analog:** `tests/test_dashboard.py:606+` — `TestRenderBlocks`.

**Pattern to copy** (per-block substring + colour + escape assertions, tests/test_dashboard.py:615-660 verbatim shape):
```python
def test_paper_trades_open_table_renders_unrealised_pnl_per_row(self):
  state = _make_state_v6_with_two_open_trades()
  output = dashboard._render_paper_trades_open(
    state['paper_trades'], state['signals']
  )
  assert 'SPI200-20260430-001' in output
  assert '+997.00' in output  # hand-computed unrealised P&L
  assert 'class="pnl-positive"' in output
```

**Pattern to adapt:**
- Add `_make_state_v6_with_paper_trades()` builder helper in test setup, mirroring tests/conftest.py:222-248 default state shape but extended with `paper_trades=[...]`.
- Sticky-CSS class assertion: `assert 'position: sticky' in dashboard._INLINE_CSS` (one-line check).
- Empty-state assertions for D-16 copy: literal-string match.

**Hex-boundary check:** clean.

---

### `tests/fixtures/state_v6_with_paper_trades.json` (NEW)

**Closest analog:** `tests/fixtures/dashboard/sample_state_v5.json` + `tests/fixtures/state_v2_no_manual_stop.json`.

**Pattern to copy** (sample_state_v5.json shape: `{schema_version, account, last_run, positions, signals, trade_log, equity_history, warnings, initial_account, contracts, _resolved_contracts}`).

**Pattern to adapt:**
- `schema_version: 6`
- Add `paper_trades: [...]` with **2 open + 2 closed** rows covering all four LONG/SHORT × SPI/AUDUSD combinations.
- Each row carries the full D-09 13-key shape (id, instrument, side, entry_dt, entry_price, contracts, stop_price, entry_cost_aud, status, exit_dt, exit_price, realised_pnl, strategy_version).
- Hand-computed `realised_pnl` values match `compute_realised_pnl` outputs to 1e-9 — the fixture is the canonical golden for `_compute_aggregate_stats` tests.

**Hex-boundary check:** N/A (data fixture).

---

### AST forbidden-imports extension for `pnl_engine.py`

**Closest analog:** `tests/test_signal_engine.py:590` — `_HEX_PATHS_ALL = [SIGNAL_ENGINE_PATH, SIZING_ENGINE_PATH, SYSTEM_PARAMS_PATH]`.

**Pattern to copy** (tests/test_signal_engine.py:457-500 — path constants + frozenset definitions):
```python
# Add at module top alongside SIGNAL_ENGINE_PATH / SIZING_ENGINE_PATH:
PNL_ENGINE_PATH = Path('pnl_engine.py')
TEST_PNL_ENGINE_PATH = Path('tests/test_pnl_engine.py')

# Extend the parametrize lists (test_signal_engine.py:590-592):
_HEX_PATHS_ALL = [
  SIGNAL_ENGINE_PATH, SIZING_ENGINE_PATH, SYSTEM_PARAMS_PATH,
  PNL_ENGINE_PATH,   # <-- Phase 19 extension
]
_HEX_PATHS_STDLIB_ONLY = [
  SIZING_ENGINE_PATH, SYSTEM_PARAMS_PATH,
  PNL_ENGINE_PATH,   # <-- Phase 19 — pnl_engine is stdlib-only (math + system_params)
]
```

**Pattern to adapt:** none — extending two parametrize lists.

**Hex-boundary check:** clean. The two existing tests (`test_forbidden_imports_absent` line 762 + `test_phase2_hex_modules_no_numpy_pandas` line 785) auto-pick up the new path via `@pytest.mark.parametrize('module_path', _HEX_PATHS_ALL)`.

---

## Shared Patterns

### Authentication / cookie-session
**Source:** Phase 16.1 — `web/middleware/auth.py` (registered last in web/app.py:182, runs first per D-06).
**Apply to:** All four `/paper-trade/*` routes automatically — middleware gates **all** HTTP methods uniformly (RESEARCH §Standard Stack confirms PATCH/DELETE pass through without special-casing). No per-route auth code in `paper_trades.py`. Cookie-session validator pattern at web/routes/dashboard.py:118-136 (`_is_cookie_session`) — paper-trade routes do NOT need it (they're not public-static-style; AuthMiddleware handles them).

### Hex-discipline local imports (Phase 11 C-2)
**Source:** web/routes/trades.py:467-468, 537-538, 564, 613-614, 640.
**Apply to:** Every `_apply` closure in `paper_trades.py`. Imports from `state_manager`, `pnl_engine`, `system_params` go INSIDE the closure body, not at module top.
```python
def _apply(state):
  from state_manager import mutate_state  # LOCAL — Phase 11 C-2
  from pnl_engine import compute_realised_pnl  # LOCAL
  from system_params import STRATEGY_VERSION  # LOCAL — VERSION-03 fresh-read
```

### Sentinel-on-conflict + lock-release-before-response
**Source:** web/routes/trades.py:81-87 + 543-559.
**Apply to:** Every paper-trade route handler. Define `_PaperTradeNotFound`, `_PaperTradeImmutable`, `_PaperTradeIDOverflow` sentinels; raise inside `_apply`; catch in handler; return appropriate Response. Guarantees `mutate_state`'s `flock(LOCK_UN)` runs before HTTP response construction (RESEARCH §Pitfall 6).

### `html.escape(value, quote=True)` at every leaf
**Source:** web/routes/trades.py:306-307 (`esc = lambda s: html.escape(str(s), quote=True)`); dashboard.py:1410, 1438, 1465 (per-cell escape).
**Apply to:** Every `_render_paper_trades_*` helper — every dynamic value (trade ID, instrument, side, prices, dates) flows through `html.escape(..., quote=True)` at the leaf render site. **Required for paper-trade IDs** which are user-influenced strings (operator-typed instrument key + date).

### `hx-ext="json-enc"` on every HTMX-sent form
**Source:** web/routes/trades.py:362-366 (REVIEW CR-01 comment), :383-386, :1500-1503.
**Apply to:** Every `<form hx-post="...">` and `<form hx-patch="...">` and `<button hx-delete="...">` rendered by `_render_paper_trades_*` helpers. Without it FastAPI Pydantic-body parameters return 400 (the form's body is form-encoded; FastAPI expects JSON). RESEARCH §Pitfall 8 explicit.

### Composite-key escape
**Source:** dashboard.py:2009 — `state_key_esc = html.escape(state_key, quote=True)`.
**Apply to:** Every paper-trade ID in URL paths (`hx-get="/paper-trade/{trade_id_esc}/close-form"`). The trade ID `SPI200-20260430-001` itself is server-generated and safe, but operators editing state.json could inject — defensive escape at every render site.

### Atomic mutation via `mutate_state`
**Source:** state_manager.py:631-670 (the entire kernel).
**Apply to:** All four mutation routes. Single `mutate_state(_apply)` call per route. ID generation (RESEARCH §Pattern 4) MUST run inside the `_apply` closure under the held flock — never compute the ID before calling `mutate_state` and never do `load_state()` inside `_apply` (RESEARCH §Pitfall 6).

---

## No Analog Found (design from scratch)

| Symbol | Role | Reason | Reference for design |
|--------|------|--------|----------------------|
| `_method_not_allowed_405` helper | adapter helper | First manual 405 in codebase | RESEARCH §Pattern 3 + RFC 7231 §6.5.5 verbatim |
| `_compute_next_trade_id` (composite) | adapter helper | Phase 14 used instrument-as-PK; no composite IDs | RESEARCH §Pattern 4 + CONTEXT D-01 + risk-register overflow |
| `multiprocessing.Process` race test | test | First multiprocessing test in repo | RESEARCH §Pattern 9 verbatim |
| HTMX `client.patch()` / `client.delete()` test calls | test | Phase 19 introduces PATCH/DELETE first | RESEARCH §Pattern 8 verbatim |
| `position: sticky` CSS | render hex | First sticky positioning in `_INLINE_CSS` | RESEARCH §Pattern 7 + §Pitfall 4 |

---

## Hex-boundary spotlight

**Verified safe (CONTEXT D-14 reconciled with codebase):**
- `dashboard.py` adding `from pnl_engine import compute_unrealised_pnl` is **safe**: `pnl_engine` is NOT in `FORBIDDEN_MODULES_DASHBOARD` (tests/test_signal_engine.py:556-569). Phase 19 PATTERNS treat `pnl_engine` as same hex-tier as `signal_engine` and `sizing_engine`.
- **Note on CONTEXT D-14 wording:** The phrase "dashboard.py continues to NOT import system_params / state_manager" is **not literally true** in the current codebase — `dashboard.py:79-100` already imports both `state_manager.load_state` and a dozen `system_params` constants. The forbidden set is the one in tests/test_signal_engine.py:556-569 (no `signal_engine`, `data_fetcher`, `notifier`, `main`, `numpy`, `pandas`, `yfinance`, `requests`, `schedule`, `dotenv`). CONTEXT D-14's intent is clearer in the second sentence: "adds `pnl_engine` to the import list — `pnl_engine` is pure-math (same hex-tier as `signal_engine` and `sizing_engine`), so this is safe per the existing rule." Planner should treat the **AST guard** (`FORBIDDEN_MODULES_DASHBOARD`) as the source of truth and ignore the prose hyperbole.
- **Sizing-engine module-top guard:** `tests/test_signal_engine.py:888-913` (`test_dashboard_no_module_top_sizing_engine_import`) bans **only** `sizing_engine` from module-top — it does NOT ban `pnl_engine`. If Phase 19 wants module-top `from pnl_engine import compute_unrealised_pnl`, no test fails. If symmetry with `sizing_engine` is preferred (LOCAL inside helper bodies), follow Phase 11 C-2 / Phase 14 D-02 / Phase 15 D-01 — also no test fails. **Planner picks one**; recommend LOCAL for symmetry with `sizing_engine`.

**Verified safe — `pnl_engine.py` forbidden imports:**
- `pnl_engine.py` must satisfy `FORBIDDEN_MODULES` (test_signal_engine.py:488-497) AND `FORBIDDEN_MODULES_STDLIB_ONLY` (line 500). Allowed: `math`, `system_params` (for `SPI_MULT`, `SPI_COST_AUD`, `AUDUSD_NOTIONAL`, `AUDUSD_COST_AUD`, OR none if caller passes the floats directly per RESEARCH §Pattern 5). Recommend: import nothing from `system_params` — keep `pnl_engine` decoupled per the Phase 2 D-17 anti-coupling Pitfall 6 ("cost is an explicit parameter, not derived from multiplier").

**Verified safe — `web/routes/paper_trades.py` adapter:**
- Imports `pnl_engine`, `state_manager.mutate_state`, `system_params.STRATEGY_VERSION` (LOCAL inside `_apply`). Forbidden: `signal_engine`, `data_fetcher`, `notifier`, `main`. Tests/test_web_healthz.py::TestWebHexBoundary enforces this (web/routes/trades.py:42-43 references the constraint).

---

## Metadata

**Analog search scope:** `web/routes/`, `state_manager.py`, `dashboard.py`, `sizing_engine.py`, `system_params.py`, `tests/test_state_manager.py`, `tests/test_dashboard.py`, `tests/test_web_trades.py`, `tests/test_signal_engine.py`, `tests/conftest.py`, `tests/fixtures/`.
**Files scanned:** 22 (10 source, 12 test).
**Pattern extraction date:** 2026-04-30
**Phase precedents leveraged:** 2 (sizing_engine pure-math), 14 (mutate_state + HTMX route shape), 16.1 (cookie-session middleware passthrough), 17 (migration shape, just shipped 24 hours ago), 22 (strategy_version fresh-read closure pattern).
