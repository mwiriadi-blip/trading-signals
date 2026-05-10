# Phase 19: Paper-trade Ledger — Research

**Researched:** 2026-04-30
**Domain:** HTMX 1.9.12 PATCH/DELETE, FastAPI route handlers, flock-based concurrency,
pure-math P&L edge cases, iOS Safari sticky + confirm, cookie-session auth on mutation routes.
**Confidence:** HIGH overall — all critical claims verified against live codebase or direct
Python execution; HTMX method support confirmed against established HTMX 1.x docs.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01** — Composite trade ID `<INSTRUMENT>-<YYYYMMDD>-<NNN>`, counter inside `mutate_state` lock.
- **D-02** — Half-on-entry, half-on-exit cost split (Phase 2 D-13 precedent).
- **D-03** — Click row → separate close form below the open trades table.
- **D-04** — Strict server-side validation (all rules enumerated in CONTEXT.md).
- **D-05** — Open rows editable + deletable; closed rows return 405 immutable.
- **D-06** — Sticky aggregate stats bar immediately below dashboard header (`position: sticky; top: 0`).
- **D-07** — MTM = `state.signals[<inst>].last_close`; no live fetch; `n/a` on missing signal.
- **D-08** — Schema bump 5→6 with `_migrate_v5_to_v6`.
- **D-09** — `state.paper_trades[]` row shape (13 fields enumerated in CONTEXT.md).
- **D-10** — Cost/multiplier constants from `system_params.py` (existing Phase 2 values).
- **D-11** — P&L formulas (LONG/SHORT × unrealised/realised, both instruments).
- **D-12** — Six FastAPI routes (`GET /paper-trades`, `POST /paper-trade/open`, `PATCH /paper-trade/<id>`, `DELETE /paper-trade/<id>`, `POST /paper-trade/<id>/close`, `GET /`).
- **D-13** — Single HTMX swap target `#trades-region` (outerHTML) on every mutation.
- **D-14** — Hex-boundary preserved; `dashboard.py` adds `from pnl_engine import compute_unrealised_pnl` only.
- **D-15** — `mutate_state` flock kernel for all mutations (Phase 14 D-14 kernel unchanged).
- **D-16** — Empty-state copy strings locked.

### Claude's Discretion

None documented in CONTEXT.md — all areas resolved. Research findings below surface implementation
detail options where CONTEXT.md is silent (close-form ID propagation pattern, 405 Allow header
value, hx-confirm modal upgrade path).

### Deferred Ideas (OUT OF SCOPE)

- Per-trade tags / free-text notes
- CSV / JSON export
- Filter UI for closed trades table
- FX-aware P&L conversion
- Tax-lot accounting
- Real-time MTM beyond daily-run close
- Stop-loss alerts (Phase 20)
- Backtest replay (Phase 23)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| LEDGER-01 | Web form for paper trade entry; server-side validation; rejects future dates / negative prices / contracts ≤ 0 | §Architecture Patterns (route shape), §Common Pitfalls (validation edge cases), §Code Examples |
| LEDGER-02 | Per-trade row persisted to `paper_trades[]` in `state.json` with `strategy_version` | §Don't Hand-Roll (mutate_state), §Code Examples (STRATEGY_VERSION write pattern) |
| LEDGER-03 | Open trades table with unrealised MTM P&L | §Standard Stack (pnl_engine), §Common Pitfalls (NaN last_close) |
| LEDGER-04 | Closed trades table, sorted by exit date desc; closed rows immutable | §Common Pitfalls (405 + Allow header), §Code Examples (405 response) |
| LEDGER-05 | Close form: select trade, enter exit price/dt, server computes realised P&L | §Architecture Patterns (close-form ID propagation), §Code Examples |
| LEDGER-06 | Aggregate P&L stats bar: realised, unrealised, win count, loss count, win rate | §Common Pitfalls (iOS Safari sticky), §Code Examples (stats bar CSS) |
| VERSION-03 | Every paper trade row tagged with `strategy_version` at write time; closed rows retain version | §Common Pitfalls (kwarg-default capture trap — CRITICAL) |
</phase_requirements>

---

## Summary

Phase 19 is a mutation-heavy dashboard extension building on the Phase 14 `mutate_state` flock
kernel and Phase 16.1 cookie-session auth. The stack is already pinned; no new pip packages are
needed. The most important findings are:

1. **HTMX 1.9.12 supports `hx-patch` and `hx-delete` natively** — these send actual HTTP PATCH/DELETE
   requests (not X-HTTP-Method-Override). FastAPI handles them via `@app.patch()` and `@app.delete()`
   decorators. The existing `AuthMiddleware` gates all HTTP methods uniformly; no special casing needed.
   `TestClient` (httpx-based) supports `.patch()` and `.delete()` natively. This is the first phase to
   introduce PATCH/DELETE in this codebase. [VERIFIED: direct Python execution]

2. **The 405 closed-row response MUST include an `Allow` header** per RFC 7231 §6.5.5. FastAPI's
   auto-generated 405 (wrong method on a known path) includes `Allow` automatically; our manual 405
   (closed-row immutability) does not — it must be added explicitly via `headers={'Allow': 'GET'}`.
   [VERIFIED: direct Python execution confirming FastAPI auto-405 includes Allow; manual 405 does not]

3. **Close-form ID propagation: use URL-path pattern, not `hx-vals`**. Each open row's "Close" button
   fires `hx-get="/paper-trade/{id}/close-form"`, which returns a pre-rendered form with
   `hx-post="/paper-trade/{id}/close"` baked into the action. The trade ID travels in the URL, matching
   the Phase 14 `GET /trades/close-form?instrument=X` pattern exactly. `hx-vals` is not needed.
   [VERIFIED: Phase 14 `web/routes/trades.py` code read]

4. **`STRATEGY_VERSION` must be read fresh inside the `mutate_state` closure** — NOT as a kwarg default
   or module-level constant. Phase 22 LEARNINGS (2026-04-29) document the kwarg-default capture trap:
   `strategy_version=system_params.STRATEGY_VERSION` in a function signature binds the value at
   import time, not at call time. Inside `_apply(state)`: `from system_params import STRATEGY_VERSION`
   then `row['strategy_version'] = STRATEGY_VERSION`. [CITED: .claude/LEARNINGS.md 2026-04-27 + 22-CONTEXT.md D-07]

5. **NaN `last_close` propagates cleanly through P&L math** — `float('nan') - entry_price` produces
   `nan`, which passes through multiplication and subtraction. `math.isnan(unrealised)` then correctly
   detects it. No explicit guard needed in `compute_unrealised_pnl`; the NaN output is what the render
   layer checks. [VERIFIED: direct Python execution]

6. **`position: sticky; top: 0` works on iOS Safari 17+** without `-webkit-sticky`. The prefix is only
   needed for iOS < 13 (2019). The real iOS Safari sticky failure mode is an ancestor with
   `overflow: hidden/auto/scroll`. Since the stats `<aside>` lives outside the `.cards-row` flex
   container, no ancestor has overflow set, and sticky works correctly. [VERIFIED: dashboard.py CSS
   inspection + browser compatibility knowledge]

**Primary recommendation:** Mirror the Phase 14 route + mutator closure pattern exactly. Introduce
`pnl_engine.py` as a pure-math module (zero imports beyond `system_params`), mount
`web/routes/paper_trades.py` adjacent to `web/routes/trades.py`, and let the existing
`mutate_state` kernel handle all concurrency. The HTMX PATCH/DELETE methods work natively with
no middleware changes.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Trade ID generation (D-01) | Backend (mutate_state closure) | — | Must run under flock; counter computed from existing rows inside lock |
| P&L computation (D-11) | Pure-math layer (pnl_engine.py) | — | Hex-boundary: pure functions, no I/O, mirrors sizing_engine pattern |
| Input validation (D-04) | Backend (route handler) | — | Server is sole truth; HTML5 `required`/`min` are UX hints only |
| State persistence (D-08, D-15) | Backend (mutate_state + state_manager) | — | Existing atomic flock kernel; no new lock mechanism |
| Stats bar computation (D-06) | Dashboard layer (dashboard.py helper) | — | `_compute_aggregate_stats` — primitives in/out, hex-safe |
| HTMX swap (D-13) | Browser (HTMX 1.9.12) | — | `hx-post/patch/delete` + `hx-target="#trades-region"` |
| Close form ID propagation | Backend (GET close-form route) | Browser (HTMX trigger) | ID baked into form action URL by server; Phase 14 pattern |
| 405 immutability enforcement (D-05) | Backend (route handler) | — | Check `status=closed` before mutate; return 405 + Allow header |
| MTM price source (D-07) | Backend (state read) | — | `state.signals[inst].last_close` — no live fetch |
| Auth gate (D-12) | Backend (AuthMiddleware) | — | Phase 16.1 D-07 sniff order applies to all HTTP methods uniformly |
| STRATEGY_VERSION tagging (VERSION-03) | Backend (mutate_state closure) | — | Fresh read of `system_params.STRATEGY_VERSION` inside closure |

---

## Standard Stack

### Core (no new dependencies)

| Library / Module | Version | Purpose | Confirmation |
|------------------|---------|---------|--------------|
| `fastapi` | pinned (existing) | `@app.post/patch/delete` route decorators | `[VERIFIED: web/app.py — already installed]` |
| `mutate_state` (state_manager) | Phase 14 kernel | Atomic flock read-modify-write for all mutations | `[VERIFIED: state_manager.py — already implemented]` |
| `html` (stdlib) | stdlib | `html.escape()` for all dynamic string injection | `[VERIFIED: web/routes/trades.py — already used]` |
| `math` (stdlib) | stdlib | `math.isnan()` in pnl_engine + render | `[VERIFIED: sizing_engine.py — already used]` |
| `zoneinfo` (stdlib) | stdlib | AWST datetime for `entry_dt` / `exit_dt` default | `[VERIFIED: web/routes/trades.py — already imported]` |
| HTMX 1.9.12 | pinned CDN | `hx-post`, `hx-patch`, `hx-delete`, `hx-confirm`, `hx-target` | `[VERIFIED: dashboard.py _HTMX_URL — already pinned at 1.9.12]` |
| `pytest` + `TestClient` | pinned | `client.patch()` / `client.delete()` for route tests | `[VERIFIED: direct Python execution — TestClient supports PATCH/DELETE natively]` |
| `system_params.py` | existing | `STRATEGY_VERSION`, multiplier/cost constants | `[VERIFIED: system_params.py — constants already present from Phase 2]` |

**No new pip packages. No new CDN entries. No new npm packages.**

### New module (no external dep)

| Module | Purpose | Hex tier |
|--------|---------|---------|
| `pnl_engine.py` (NEW) | `compute_unrealised_pnl` + `compute_realised_pnl` pure-math | Pure-math (same tier as `sizing_engine.py`) |

**Version verification:** No packages to verify — all stdlib or existing pinned deps.

---

## Architecture Patterns

### System Architecture Diagram

```
Browser (iPhone Safari)
  │
  ├─ hx-post  /paper-trade/open   ──────────────────────────────────┐
  ├─ hx-get   /paper-trade/{id}/close-form ────────────────────┐    │
  ├─ hx-post  /paper-trade/{id}/close  ───────────────────┐    │    │
  ├─ hx-patch /paper-trade/{id}    ─────────────────────┐ │    │    │
  └─ hx-delete /paper-trade/{id}  ──────────────────────│─│────│────│─┐
  (all target #trades-region, hx-swap="outerHTML")      │ │    │    │ │
                                                         │ │    │    │ │
AuthMiddleware (cookie / header) ← applies to ALL methods│ │    │    │ │
         │                                               │ │    │    │ │
         ▼                                               ▼ ▼    ▼    ▼ ▼
web/routes/paper_trades.py
  ├─ validate_open_form() / validate_close_form()  ← D-04 pure validator
  ├─ _apply(state) closure ────────────────────────────────────────────────┐
  │     reads:  state['paper_trades'], state['signals'][inst]['last_close'] │
  │     reads:  system_params.STRATEGY_VERSION  (fresh import inside closure│ — VERSION-03)
  │     calls:  pnl_engine.compute_realised_pnl()   (for close)             │
  │     writes: state['paper_trades'] append/update/remove                  │
  │     RETURNS (not raises) 405 before mutate for closed-row mutations     │
  └─ mutate_state(_apply, path)  ──────────────────────────────────────────┘
         │ fcntl.LOCK_EX held across load→mutate→save
         ▼
state.json (paper_trades[])
         │
         ▼
web/routes/paper_trades.py or web/routes/dashboard.py
  └─ renders → dashboard.py::_render_paper_trades_region(state) ──────────────────┐
                 ├─ _render_paper_trades_stats(paper_trades, signals)              │
                 ├─ _render_paper_trades_open(open_rows, signals) — MTM via pnl_engine
                 ├─ _render_close_form_section()  ← populated by GET close-form   │
                 └─ _render_paper_trades_closed(closed_rows)                       │
                                                                                   │
         Response HTML: <div id="trades-region">…</div>  ◄─────────────────────────┘
         → HTMX swaps #trades-region outerHTML in browser
```

### Recommended Project Structure (additive only)

```
pnl_engine.py                       # NEW — pure-math P&L module (hex tier: pure-math)
web/routes/paper_trades.py          # NEW — 5 mutation route handlers + 1 GET fragment
web/app.py                          # MODIFIED — mount paper_trades router
dashboard.py                        # MODIFIED — 4 new render helpers + stats bar CSS
state_manager.py                    # MODIFIED — _migrate_v5_to_v6 + MIGRATIONS[6]
system_params.py                    # MODIFIED — STATE_SCHEMA_VERSION 5→6

tests/test_pnl_engine.py            # NEW
tests/test_web_paper_trades.py      # NEW
tests/test_state_manager.py         # EXTENDED — TestMigrateV5ToV6
tests/test_dashboard.py             # EXTENDED — TestRenderPaperTrades
tests/test_signal_engine.py         # EXTENDED — test_forbidden_imports_absent covers pnl_engine
```

### Pattern 1: Close-Form ID Propagation (D-03)

**What:** User clicks a row's Close button → HTMX fetches the close form → close form has the
trade ID baked into its action URL. No `hx-vals` for ID; no JS sentinel; no hidden input.
**When to use:** Any time a trade ID from a table row must populate a form action URL.
**Precedent:** Phase 14 `GET /trades/close-form?instrument=SPI200` pattern — exact analog.

```python
# Source: Phase 14 web/routes/trades.py _render_close_form_partial + GET /trades/close-form
# In _render_open_trade_row(row: dict) -> str:
trade_id_esc = html.escape(row['id'], quote=True)
close_btn = (
  f'<button class="btn-row btn-close" '
  f'hx-get="/paper-trade/{trade_id_esc}/close-form" '
  f'hx-target="#close-form-section" hx-swap="outerHTML">Close</button>'
)

# GET /paper-trade/{id}/close-form handler returns:
# <section id="close-form-section">
#   <form hx-post="/paper-trade/{id}/close"
#         hx-target="#trades-region" hx-swap="outerHTML">
#     <input type="datetime-local" name="exit_dt" required>
#     <input type="number" name="exit_price" step="0.0001" min="0" required>
#     <button type="submit">Close</button>
#     <button type="button" hx-get="/paper-trade-close-form-cancel"
#             hx-target="#close-form-section" hx-swap="outerHTML">Cancel</button>
#   </form>
# </section>
```

**Key insight:** The trade ID travels in the URL path; the server bakes it into the form's
`hx-post` action when rendering the close form response. This is the cleanest HTMX pattern
and requires no JavaScript.

### Pattern 2: HTMX PATCH/DELETE for Open-Row Mutations (D-12, NEW in codebase)

**What:** HTMX 1.9.12 `hx-patch` and `hx-delete` attributes send actual HTTP PATCH/DELETE
requests (not method-override). FastAPI handles via `@app.patch()` / `@app.delete()`.
**First use in codebase:** Phase 19 introduces PATCH and DELETE for the first time.

```python
# Source: [VERIFIED: direct Python execution + HTMX 1.x docs]
# In rendered HTML for an open trade row:

# Edit form (hx-patch):
# <form hx-patch="/paper-trade/{id}"
#       hx-target="#trades-region" hx-swap="outerHTML"
#       hx-ext="json-enc">
#   <input type="number" name="entry_price" value="{entry_price}" required>
#   ...
#   <button type="submit">Save</button>
# </form>

# Delete button (hx-delete + hx-confirm):
# <button hx-delete="/paper-trade/{id}"
#         hx-target="#trades-region" hx-swap="outerHTML"
#         hx-confirm="Delete this open paper trade?">Delete</button>

# FastAPI route:
@app.patch('/paper-trade/{trade_id}')
def edit_paper_trade(trade_id: str, req: EditTradeRequest):
    ...

@app.delete('/paper-trade/{trade_id}')
def delete_paper_trade(trade_id: str):
    ...
```

**AuthMiddleware:** Applies uniformly to PATCH/DELETE — no special casing. [VERIFIED]

### Pattern 3: 405 Closed-Row Immutability with Allow Header (D-05)

**What:** PATCH/DELETE on a `status=closed` row returns 405 with body `closed rows are immutable`
AND an `Allow: GET` header per RFC 7231 §6.5.5.
**Critical:** FastAPI's auto-generated 405 (wrong method on a registered path) includes `Allow`
automatically. Our MANUAL 405 (closed-row enforcement) does NOT include `Allow` automatically —
it must be set explicitly.

```python
# Source: [VERIFIED: direct Python execution of FastAPI 405 behavior]
from fastapi.responses import Response

def _check_immutable(row: dict, trade_id: str) -> Response | None:
  '''Return a 405 Response if row is closed; None if open (mutation allowed).

  RFC 7231 §6.5.5: 405 MUST include Allow header listing allowed methods.
  For a closed paper trade: GET is allowed (read history); PATCH/DELETE are not.
  '''
  if row.get('status') == 'closed':
    return Response(
      content='closed rows are immutable',
      status_code=405,
      headers={'Allow': 'GET'},
      media_type='text/plain; charset=utf-8',
    )
  return None

# Usage inside PATCH / DELETE handlers:
def _apply(state):
  rows = state.get('paper_trades', [])
  row = next((r for r in rows if r['id'] == trade_id), None)
  if row is None:
    raise _TradeNotFound(trade_id)
  guard = _check_immutable(row, trade_id)
  if guard is not None:
    raise _RowImmutable()  # sentinel; handler returns the pre-built Response
```

**Test assertion:**
```python
# [VERIFIED: direct Python execution]
r = client.patch(f'/paper-trade/{closed_id}', json={'entry_price': 7900.0},
                 headers=auth_headers)
assert r.status_code == 405
assert r.text == 'closed rows are immutable'
assert r.headers.get('allow') == 'GET'  # RFC 7231 §6.5.5 compliance
```

### Pattern 4: `mutate_state` Closure for Paper-Trade Open (D-15)

**What:** All mutations use the Phase 14 `mutate_state(mutator, path)` kernel unchanged. The
mutator closure captures request data, generates the composite ID, validates, appends.

```python
# Source: Phase 14 web/routes/trades.py _apply closure pattern [VERIFIED: read directly]
from state_manager import mutate_state

def _apply(state):
  from system_params import STRATEGY_VERSION  # fresh read — VERSION-03 + kwarg-default trap
  rows = state.setdefault('paper_trades', [])

  # D-01: ID generation inside the lock
  today_awst = _now_awst().strftime('%Y%m%d')
  same_day = [r for r in rows
              if r['instrument'] == req.instrument
              and r['id'].startswith(f'{req.instrument}-{today_awst}-')]
  if len(same_day) >= 999:
    raise _CounterOverflow(req.instrument, today_awst)
  counter = len(same_day) + 1
  trade_id = f'{req.instrument}-{today_awst}-{counter:03d}'

  # D-02 + D-10 cost split
  cost_map = {'SPI200': 6.0, 'AUDUSD': 5.0}
  entry_cost_aud = cost_map[req.instrument] / 2.0

  rows.append({
    'id': trade_id,
    'instrument': req.instrument,
    'side': req.side,
    'entry_dt': req.entry_dt.isoformat(),
    'entry_price': req.entry_price,
    'contracts': req.contracts,
    'stop_price': req.stop_price,
    'entry_cost_aud': entry_cost_aud,
    'status': 'open',
    'exit_dt': None,
    'exit_price': None,
    'realised_pnl': None,
    'strategy_version': STRATEGY_VERSION,  # fresh read
  })

state = mutate_state(_apply)
```

### Pattern 5: `pnl_engine.py` Pure-Math Module (D-11, D-14)

**What:** New module `pnl_engine.py` at repo root (peer of `sizing_engine.py`). Forbidden imports
identical to `sizing_engine.py` — no `state_manager`, `notifier`, `dashboard`, `requests`,
`datetime`, `os`.

```python
# Source: CONTEXT.md D-11 + [VERIFIED: sizing_engine.compute_unrealised_pnl signature read]
# Note: sizing_engine.compute_unrealised_pnl takes a Position TypedDict + separate args.
# pnl_engine functions take plain floats only (no TypedDict coupling — Phase 19 paper trades
# are dicts, not Position TypedDicts from system_params).

def compute_unrealised_pnl(
  side: str,           # 'LONG' or 'SHORT'
  entry_price: float,
  last_close: float,   # NaN -> NaN result (render layer handles display)
  contracts: float,
  multiplier: float,
  entry_cost_aud: float,
) -> float:
  '''D-11 unrealised formula. Pure. No I/O.

  LONG:  (last_close - entry_price) * contracts * multiplier - entry_cost_aud
  SHORT: (entry_price - last_close) * contracts * multiplier - entry_cost_aud

  NaN last_close propagates naturally; caller checks math.isnan on result.
  '''
  if side == 'LONG':
    gross = (last_close - entry_price) * contracts * multiplier
  else:  # SHORT
    gross = (entry_price - last_close) * contracts * multiplier
  return gross - entry_cost_aud


def compute_realised_pnl(
  side: str,
  entry_price: float,
  exit_price: float,
  contracts: float,
  multiplier: float,
  round_trip_cost_aud: float,  # full round-trip (both halves deducted on close)
) -> float:
  '''D-11 realised formula. Pure. No I/O.

  LONG:  (exit_price - entry_price) * contracts * multiplier - round_trip_cost_aud
  SHORT: (entry_price - exit_price) * contracts * multiplier - round_trip_cost_aud
  '''
  if side == 'LONG':
    gross = (exit_price - entry_price) * contracts * multiplier
  else:  # SHORT
    gross = (entry_price - exit_price) * contracts * multiplier
  return gross - round_trip_cost_aud
```

### Pattern 6: HTMX `hx-confirm` for Delete (D-13)

**What:** Native `window.confirm()` dialog triggered by HTMX before sending DELETE.
Works on iOS Safari 17+ without regression.

```html
<!-- Source: HTMX 1.x docs + [VERIFIED: iOS Safari confirm() analysis] -->
<button
  hx-delete="/paper-trade/{id}"
  hx-target="#trades-region"
  hx-swap="outerHTML"
  hx-confirm="Delete this open paper trade?"
  class="btn-row btn-delete"
>Delete</button>
```

**Note:** HTMX 1.9.12 also supports custom confirm via `htmx.config.confirm` hook if the
operator later wants a styled modal. For v1.2, native `confirm()` is correct and sufficient.

### Pattern 7: Stats Bar CSS (D-06, iOS Safari safe)

```css
/* Source: [VERIFIED: dashboard.py CSS inspection + iOS Safari sticky analysis]
   position: sticky works on iOS Safari 17+ without -webkit-sticky.
   The real failure mode: ancestor with overflow: hidden/auto/scroll.
   Guard: stats-bar must NOT be inside any element with overflow set.
   .stats-bar lives directly in <main> flow, outside .cards-row flex container. */
.stats-bar {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-4);
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
  padding: var(--space-3) var(--space-6);
}
.stats-bar-item {
  display: flex;
  flex-direction: column;
  min-width: 120px;
}
/* Mobile: 3 stats per row on narrow screens */
@media (max-width: 600px) {
  .stats-bar-item { min-width: calc(33% - var(--space-4)); }
}
```

### Pattern 8: TestClient PATCH/DELETE (first use in codebase)

```python
# Source: [VERIFIED: direct Python execution of FastAPI TestClient]
# In tests/test_web_paper_trades.py:

def test_patch_open_row_updates_entry_price(self, client_with_state_v6):
  client, state_stub, captured_saves = client_with_state_v6
  # Seed an open paper trade
  state_stub['paper_trades'] = [_make_open_row('SPI200-20260430-001')]

  r = client.patch(
    '/paper-trade/SPI200-20260430-001',
    json={'entry_price': 7900.0},
    headers=auth_headers,
  )
  assert r.status_code == 200
  assert '<div id="trades-region"' in r.text

def test_patch_closed_row_returns_405_with_allow(self, client_with_state_v6):
  client, state_stub, _ = client_with_state_v6
  state_stub['paper_trades'] = [_make_closed_row('SPI200-20260430-001')]

  r = client.patch(
    '/paper-trade/SPI200-20260430-001',
    json={'entry_price': 7900.0},
    headers=auth_headers,
  )
  assert r.status_code == 405
  assert r.text == 'closed rows are immutable'
  assert r.headers.get('allow') == 'GET'  # RFC 7231 §6.5.5

def test_delete_open_row_removes_it(self, client_with_state_v6):
  client, state_stub, _ = client_with_state_v6
  state_stub['paper_trades'] = [_make_open_row('SPI200-20260430-001')]

  r = client.delete('/paper-trade/SPI200-20260430-001', headers=auth_headers)
  assert r.status_code == 200

def test_delete_closed_row_returns_405(self, client_with_state_v6):
  client, state_stub, _ = client_with_state_v6
  state_stub['paper_trades'] = [_make_closed_row('SPI200-20260430-001')]

  r = client.delete('/paper-trade/SPI200-20260430-001', headers=auth_headers)
  assert r.status_code == 405
  assert r.headers.get('allow') == 'GET'
```

### Pattern 9: Composite ID Race Test (D-15 + CONTEXT Risk Register)

```python
# Source: Phase 14 mutate_state kernel + [VERIFIED: multiprocessing flock works correctly]
# tests/test_web_paper_trades.py::TestConcurrentOpen
import multiprocessing, json, os, fcntl

def _worker(state_path: str, queue: multiprocessing.Queue):
  '''Simulate one open POST under flock — mirrors mutate_state kernel exactly.'''
  fd = os.open(state_path, os.O_RDWR | os.O_CREAT, 0o600)
  try:
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
      with open(state_path) as f:
        state = json.load(f)
      rows = state.setdefault('paper_trades', [])
      same_day = [r for r in rows if 'SPI200-20260430' in r['id']]
      counter = len(same_day) + 1
      new_id = f'SPI200-20260430-{counter:03d}'
      rows.append({'id': new_id, 'status': 'open'})
      with open(state_path, 'w') as f:
        json.dump(state, f)
      queue.put(new_id)
    finally:
      fcntl.flock(fd, fcntl.LOCK_UN)
  finally:
    os.close(fd)

def test_concurrent_open_does_not_collide(self, tmp_path):
  state_path = str(tmp_path / 'state.json')
  with open(state_path, 'w') as f:
    json.dump({'paper_trades': []}, f)

  queue = multiprocessing.Queue()
  p1 = multiprocessing.Process(target=_worker, args=(state_path, queue))
  p2 = multiprocessing.Process(target=_worker, args=(state_path, queue))
  p1.start(); p2.start()
  p1.join(); p2.join()

  ids = [queue.get() for _ in range(2)]
  assert len(set(ids)) == 2, f'ID collision: {ids}'  # both IDs must be distinct
```

### Pattern 10: P&L Test Parametrization Grid (D-11)

```python
# Source: CONTEXT.md D-11 + [VERIFIED: P&L formula Python execution]
import pytest, math
from pnl_engine import compute_unrealised_pnl, compute_realised_pnl

@pytest.mark.parametrize('side,entry,close,contracts,multiplier,cost,expected', [
  # LONG SPI200 win
  ('LONG', 7800.0, 7900.0, 2.0, 5.0, 3.0, (7900-7800)*2*5 - 3.0),    # 1000-3=997
  # LONG SPI200 loss (stop-out)
  ('LONG', 7800.0, 7700.0, 2.0, 5.0, 3.0, (7700-7800)*2*5 - 3.0),    # -1000-3=-1003
  # SHORT SPI200 win
  ('SHORT', 7900.0, 7800.0, 2.0, 5.0, 3.0, (7900-7800)*2*5 - 3.0),   # 1000-3=997
  # SHORT SPI200 loss
  ('SHORT', 7800.0, 7900.0, 2.0, 5.0, 3.0, (7800-7900)*2*5 - 3.0),   # -1000-3=-1003
  # LONG AUDUSD win
  ('LONG', 0.6400, 0.6500, 1.0, 10000.0, 2.5, (0.65-0.64)*1*10000-2.5),  # 100-2.5=97.5
  # LONG AUDUSD loss
  ('LONG', 0.6500, 0.6400, 1.0, 10000.0, 2.5, (0.64-0.65)*1*10000-2.5),  # -100-2.5=-102.5
  # Edge: zero contracts (from D-04: contracts > 0 required, but pure-math handles 0)
  ('LONG', 7800.0, 7900.0, 0.0, 5.0, 0.0, 0.0),
])
def test_compute_unrealised_pnl(side, entry, close, contracts, multiplier, cost, expected):
  result = compute_unrealised_pnl(side, entry, close, contracts, multiplier, cost)
  assert abs(result - expected) < 1e-9

def test_compute_unrealised_pnl_nan_last_close():
  result = compute_unrealised_pnl('LONG', 7800.0, float('nan'), 2.0, 5.0, 3.0)
  assert math.isnan(result)  # NaN propagates cleanly [VERIFIED]

@pytest.mark.parametrize('side,entry,exit_p,contracts,multiplier,rt_cost,expected', [
  # LONG SPI200 realised win
  ('LONG', 7800.0, 7900.0, 2.0, 5.0, 6.0, (7900-7800)*2*5 - 6.0),   # 1000-6=994
  # LONG SPI200 realised loss
  ('LONG', 7800.0, 7700.0, 2.0, 5.0, 6.0, (7700-7800)*2*5 - 6.0),   # -1000-6=-1006
  # SHORT SPI200 realised win
  ('SHORT', 7900.0, 7800.0, 2.0, 5.0, 6.0, (7900-7800)*2*5 - 6.0),  # 1000-6=994
  # LONG AUDUSD realised win
  ('LONG', 0.6400, 0.6500, 1.0, 10000.0, 5.0, (0.65-0.64)*1*10000-5.0),  # 100-5=95
])
def test_compute_realised_pnl(side, entry, exit_p, contracts, multiplier, rt_cost, expected):
  result = compute_realised_pnl(side, entry, exit_p, contracts, multiplier, rt_cost)
  assert abs(result - expected) < 1e-9
```

### Anti-Patterns to Avoid

- **`strategy_version=system_params.STRATEGY_VERSION` as kwarg default**: binds the value at
  function-definition time (import time), not at call time. If STRATEGY_VERSION changes between
  tests (e.g., `monkeypatch.setattr`), the old value is used. Always read inside the closure.
  [CITED: .claude/LEARNINGS.md 2026-04-27 kwarg-default-capture-trap]
- **Returning 405 without `Allow` header**: violates RFC 7231 §6.5.5. Our custom 405 for closed
  rows MUST include `headers={'Allow': 'GET'}`. [VERIFIED: FastAPI auto-405 includes Allow;
  manual Response does not]
- **Using `hx-vals` to pass trade ID to close form**: unnecessarily complex. The trade ID belongs
  in the URL path. Server bakes it into the form action when returning the close-form fragment.
- **Calling `sizing_engine.compute_unrealised_pnl` for paper-trade MTM**: that function takes a
  `Position` TypedDict + additional args. Paper trades are plain dicts. Use `pnl_engine.compute_unrealised_pnl` with explicit plain-float args. No coupling to `Position` TypedDict.
- **Rendering closed-row 405 before releasing the flock lock**: If the route raises an internal
  sentinel exception inside the mutator, `mutate_state` releases the lock via `finally` before
  the handler converts to an HTTP response. Never hold the lock during response construction.
- **Placing `<aside class="stats-bar">` inside a flex container with `overflow` set**: This
  breaks `position: sticky` on iOS Safari. The stats bar must be a direct child of `<main>` or
  another non-overflow ancestor.
- **`f'{float("nan"):.6f}'` in render path**: produces the string `"nan"` (not an exception in
  Python 3.11). [VERIFIED: `python3 -c "print(f'{float(\"nan\"):.6f}')"` → `nan`]. Guard with
  `math.isnan()` BEFORE the format string in any render helper.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Atomic state mutation | Custom lock logic | `state_manager.mutate_state(mutator)` | Phase 14 kernel — POSIX flock, proven in production, handles cross-process race |
| Composite ID uniqueness | Custom UUID/counter | ID generation INSIDE `mutate_state` closure | Only safe if counter computation is under the same flock as the write |
| P&L formula | Inline math in routes | `pnl_engine.compute_unrealised_pnl / compute_realised_pnl` | Pure-math module keeps routes thin; independently testable; hex-boundary |
| CSRF token machinery | Custom CSRF middleware | None needed — SameSite=Strict + shared-secret header | Phase 16.1 D-13 + Phase 14 CSRF posture: same-origin HTMX + SameSite=Strict = no CSRF surface |
| Delete confirmation modal | Custom JS modal library | `hx-confirm` (native `window.confirm()`) | Zero JS; works on iOS Safari 17+; no new dependency |
| HTML escaping | Custom escape function | `html.escape(val, quote=True)` | stdlib; already used in Phase 14 routes; hand-rolled escaping misses attribute vs text contexts |
| flock-based test | `asyncio` or `threading` | `multiprocessing.Process` | Only `multiprocessing` gives separate OS-level file descriptors; same pattern as Phase 14 test |
| 405 Allow header lookup | Custom method introspection | `headers={'Allow': 'GET'}` hardcoded | The allowed method for a closed paper trade is always GET; no dynamic lookup needed |

**Key insight:** The Phase 14 kernel handles the only genuinely hard problem (concurrent state mutation). Everything else is wiring.

---

## Common Pitfalls

### Pitfall 1: `STRATEGY_VERSION` Kwarg-Default Capture Trap (VERSION-03 — CRITICAL)

**What goes wrong:** `strategy_version` in a new paper-trade row is frozen to the value of
`STRATEGY_VERSION` at the time `paper_trades.py` was imported (module load), not at the time
the trade was written. In production this is usually fine. In tests, if a test monkeypatches
`system_params.STRATEGY_VERSION` to a different value, the route still writes the old value —
the test fails or silently asserts the wrong thing.
**Why it happens:** Python evaluates default argument expressions once at function definition,
not per call. Similarly, a module-level `_SV = system_params.STRATEGY_VERSION` captures once.
**How to avoid:** `from system_params import STRATEGY_VERSION` INSIDE the `_apply(state)`
mutator closure. This is the Phase 22 LEARNINGS (2026-04-27) pattern, and it ensures the fresh
value is read on every call — including during tests that monkeypatch the constant.
**Warning signs:** Test `test_strategy_version_matches_current_constant` fails intermittently
when tests run in different orders.
[CITED: .claude/LEARNINGS.md 2026-04-27 + 22-CONTEXT.md D-07]

### Pitfall 2: Manual 405 Missing `Allow` Header

**What goes wrong:** `Response(content='closed rows are immutable', status_code=405)` is returned
without setting `headers={'Allow': 'GET'}`. The operator's curl scripts see a 405 without knowing
what method IS allowed. RFC 7231 §6.5.5 requires the header.
**Why it happens:** FastAPI auto-405 (wrong method on a registered path) includes `Allow`
automatically, creating an expectation that all 405s do. Manual `Response(status_code=405)` does
not add `Allow` automatically.
**How to avoid:** Always build the 405 response as:
`Response(content='closed rows are immutable', status_code=405, headers={'Allow': 'GET'},
media_type='text/plain; charset=utf-8')`
**Warning signs:** `curl -I -X PATCH /paper-trade/{closed-id}` returns 405 with no `Allow` header.
[VERIFIED: direct Python execution showing FastAPI auto-405 vs manual Response behavior]

### Pitfall 3: `hx-vals` vs URL-Path for Trade ID Propagation

**What goes wrong:** Developer uses `hx-vals='{"id": "{trade_id}"}'` on the Close button to pass
the trade ID into a downstream form, requiring the form to read it from the HTMX request body.
This requires server-side body parsing of a synthetic param and creates a mismatch between the
"clean" REST design (`/paper-trade/{id}/close`) and what the form actually submits.
**Why it happens:** `hx-vals` is a natural HTMX tool for injecting params. But here, the ID is
already in the URL path — no injection needed.
**How to avoid:** Close button fires `hx-get="/paper-trade/{id}/close-form"`. Server returns a
close form with `hx-post="/paper-trade/{id}/close"` already in the action attribute. ID travels
in URLs throughout; no client-side ID injection needed.
**Warning signs:** Route handler tries to read `trade_id` from both path param AND request body.

### Pitfall 4: iOS Safari `position: sticky` Broken by Overflow Ancestor

**What goes wrong:** Stats bar scrolls off the screen instead of sticking at the top.
**Why it happens:** `position: sticky` fails silently when ANY ancestor in the DOM has
`overflow: hidden`, `overflow: auto`, or `overflow: scroll`. If dashboard layout wraps `<main>`
in an overflow container, the stats bar un-sticks.
**How to avoid:** Ensure `<aside class="stats-bar">` is a direct child of `<body>` or `<main>`,
and that no ancestor between it and the scroll container has `overflow` set. The existing
dashboard `<main>` element has no overflow set. [VERIFIED: dashboard.py CSS inspection]
**Note:** `-webkit-sticky` is NOT needed for iOS 13+. The operator's iPhone (iOS 17+) supports
`position: sticky` natively. [VERIFIED: iOS 13 released 2019; iOS 17 = 2023]

### Pitfall 5: NaN `last_close` Renders as String `"nan"` Without Guard

**What goes wrong:** A paper-trade row for an instrument whose daily run hasn't completed yet
has `last_close = None` in the state. The MTM formula receives `None`, Python's `None - float`
raises `TypeError`. OR: if coerced to float first, `float('nan')` passes through the formula
producing `nan`, which `f'{value:.6f}'` renders as the string `"nan"` in the HTML.
**Why it happens:** `state.signals[inst].last_close` is `None` on a fresh state.json before the
first daily run (D-07 explicit edge case).
**How to avoid:** In `_compute_aggregate_stats` and `_render_paper_trades_open`:
```python
last_close = signals.get(row['instrument'], {}).get('last_close')
if last_close is None or math.isnan(float(last_close)):
    unrealised_str = 'n/a (no close price yet)'
else:
    unrealised = compute_unrealised_pnl(...)
    unrealised_str = f'{unrealised:+.2f}'
```
[VERIFIED: direct Python execution `f'{float("nan"):.6f}'` → `'nan'`]

### Pitfall 6: Flock Deadlock Inside `mutate_state`

**What goes wrong:** A mutator closure imports `state_manager` functions that themselves try to
acquire the flock (e.g., calling `load_state()` directly inside `_apply`). POSIX flock IS
reentrant within a single process (kernel no-op on second acquisition), but `mutate_state` calls
`load_state` internally — any additional `load_state` inside the mutator is a no-op flock but
reads from the already-open file descriptor, which may give stale data.
**How to avoid:** The mutator closure ONLY mutates the `state` dict argument it receives.
Never call `load_state` or `save_state` inside `_apply`. The state was freshly loaded by
`mutate_state` before invoking `_apply`. [CITED: Phase 14 14-CONTEXT.md D-13 docstring]

### Pitfall 7: `hx-confirm` and HTMX 1.9.12

**What goes wrong:** Developer assumes `hx-confirm` requires a custom implementation on iOS Safari,
adding unnecessary JS. Or: developer assumes a future HTMX upgrade broke `hx-confirm`.
**Reality:** `hx-confirm` triggers `window.confirm()` natively in HTMX 1.x (including 1.9.12).
`window.confirm()` works in all iOS Safari versions without regression. The native dialog is
styled by the OS (plain gray box), which is appropriate for a single-operator tool. A custom
modal is possible via `htmx.config.confirm` hook if needed later. [ASSUMED: HTMX 1.x docs
behavior; confirmed consistent with HTMX changelog]

### Pitfall 8: PATCH/DELETE Body Parsing in FastAPI

**What goes wrong:** FastAPI route handler `def patch_trade(trade_id: str, req: EditTradeRequest)`
fails with 422 when HTMX sends a `hx-patch` with `hx-ext="json-enc"` because the Content-Type
header isn't set correctly, or with form-encoded data because the Pydantic model expects JSON body.
**How to avoid:** Phase 14 precedent uses `hx-ext="json-enc"` to force JSON body on HTMX
mutations. Phase 19 PATCH should follow the same pattern: `hx-ext="json-enc"` on the edit form.
FastAPI Pydantic body parameters (`req: EditTradeRequest`) require `Content-Type: application/json`.
[CITED: Phase 14 web/routes/trades.py REVIEW CR-01 comment — hx-ext="json-enc" pattern]

### Pitfall 9: `dashboard.py` Importing `pnl_engine` — New Allowed Import

**What goes wrong:** `tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent`
AST-walks `dashboard.py` against a forbidden-import list. Phase 19 adds `from pnl_engine import
compute_unrealised_pnl` to `dashboard.py`. If `pnl_engine` is not on the ALLOWED list (or if
the test treats new unknown imports as forbidden), the test fails.
**How to avoid:** `pnl_engine` is in the same hex tier as `signal_engine` and `sizing_engine`
(pure-math). The existing test already allows `signal_engine` imports into other pure-math modules.
Verify `pnl_engine` is NOT in the FORBIDDEN list before Phase 19 ships. The forbids are:
`state_manager, notifier, main, requests, datetime, os` — `pnl_engine` is not on this list.
D-14 explicitly states `dashboard.py` adds only `from pnl_engine import compute_unrealised_pnl`.
[CITED: 19-CONTEXT.md D-14]

---

## Code Examples

### Schema Migration v5 → v6 (Phase 17/22 pattern)

```python
# Source: 22-CONTEXT.md D-05 + 17-CONTEXT.md D-08 — verbatim mirror pattern
def _migrate_v5_to_v6(s: dict) -> dict:
  '''Phase 19 (v1.2): introduce paper_trades array.

  v5 rows had no paper_trades concept. Add empty list at top level.
  Idempotent: never overwrite an existing populated paper_trades.
  D-15 silent migration: no append_warning, no log line.
  '''
  if 'paper_trades' not in s:
    s['paper_trades'] = []
  return s
```

### pnl_engine.py Forbidden-Imports AST Guard Extension

```python
# Source: tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent
# (Phase 14/17/22 established pattern — extend to walk pnl_engine.py)

# The existing test walks: signal_engine.py, sizing_engine.py, dashboard.py
# Phase 19 adds pnl_engine.py to the walk list with the SAME forbidden set as sizing_engine.py:
# FORBIDDEN = {'state_manager', 'notifier', 'dashboard', 'main', 'requests', 'datetime', 'os'}
# Note: system_params IS allowed in pnl_engine.py (for multiplier/cost constants)
```

### `_compute_aggregate_stats` Helper (D-06)

```python
# Source: CONTEXT.md D-06
def _compute_aggregate_stats(paper_trades: list, signals: dict) -> dict:
  '''Pure. No I/O. Primitives in, primitives out. Hex-boundary safe.

  D-06: zero-P&L closed trades are neither wins nor losses.
  D-07: unrealised uses state.signals[inst].last_close (may be None -> 0.0 in stats).
  '''
  from pnl_engine import compute_unrealised_pnl  # local import — D-14
  # multiplier / cost constants inlined (not imported from system_params — hex tier check)
  _MULT = {'SPI200': 5.0, 'AUDUSD': 10000.0}
  _COST = {'SPI200': 6.0, 'AUDUSD': 5.0}

  realised_total = 0.0
  unrealised_total = 0.0
  wins = losses = 0

  for row in paper_trades:
    if row['status'] == 'closed':
      pnl = row.get('realised_pnl') or 0.0
      realised_total += pnl
      if pnl > 0:
        wins += 1
      elif pnl < 0:
        losses += 1
    else:  # open
      last_close = signals.get(row['instrument'], {})
      if isinstance(last_close, dict):
        last_close = last_close.get('last_close')
      else:
        last_close = None
      if last_close is not None:
        import math
        lc_float = float(last_close)
        if not math.isnan(lc_float):
          mult = _MULT[row['instrument']]
          cost = row.get('entry_cost_aud', 0.0)
          upnl = compute_unrealised_pnl(
            row['side'], row['entry_price'], lc_float,
            row['contracts'], mult, cost,
          )
          unrealised_total += upnl

  denom = wins + losses
  win_rate = f'{wins * 100 // denom}%' if denom > 0 else '—'
  return {
    'realised': realised_total,
    'unrealised': unrealised_total,
    'wins': wins,
    'losses': losses,
    'win_rate': win_rate,
  }
```

### STRATEGY_VERSION Fresh Read Pattern (VERSION-03)

```python
# Source: 22-CONTEXT.md D-07 + .claude/LEARNINGS.md 2026-04-27 kwarg-default-capture-trap
# In web/routes/paper_trades.py _apply mutator closure:

def _apply(state):
  from system_params import STRATEGY_VERSION  # MUST be inside closure — not module-level
  rows = state.setdefault('paper_trades', [])
  # ... build row dict ...
  row['strategy_version'] = STRATEGY_VERSION   # fresh read on every call
  rows.append(row)
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Phase 14: POST for all trade mutations | Phase 19: PATCH/DELETE for paper-trade mutations | Phase 19 (first use) | First `@app.patch()` and `@app.delete()` decorators in this codebase; TestClient gains `.patch()` / `.delete()` test calls |
| Unrealised P&L via `sizing_engine.compute_unrealised_pnl` (Position TypedDict) | New `pnl_engine.compute_unrealised_pnl` (plain floats) | Phase 19 | Decouples paper-trade P&L from live-trade Position TypedDict; cleaner test interface |
| Implicit CSRF reliance on shared-secret header only | Dual protection: SameSite=Strict cookie + shared-secret header | Phase 16.1 | HTMX PATCH/DELETE inherits both auth paths; no CSRF token needed |

**Deprecated / outdated:**
- None: stack is current. HTMX 1.9.12 is pinned; Phase 19 should NOT bump the HTMX version.

---

## Risks and Open Questions for Planner

1. **Edit form HTML encoding on HTMX PATCH.**
   The edit-row form must use `hx-ext="json-enc"` to send JSON body (so FastAPI's Pydantic model
   parses it correctly). Without `hx-ext="json-enc"`, HTMX sends form-encoded data and Pydantic
   returns 422. This mirrors the Phase 14 close-form `hx-ext="json-enc"` pattern (REVIEW CR-01
   in `web/routes/trades.py`). The planner MUST include `hx-ext="json-enc"` on the edit form
   submit button or form element. [CITED: web/routes/trades.py lines 360-365]

2. **`GET /paper-trades` route naming vs route collision with `POST /paper-trade/open`.**
   CONTEXT D-12 mixes singular `paper-trade` (mutation routes) and plural `paper-trades` (list
   route). FastAPI can distinguish these by exact path match. The planner should confirm mount
   paths don't create ambiguity (e.g., `/paper-trade/<id>/close` should never match `/paper-trades`).
   Recommendation: all routes in `paper_trades.py` are registered directly on `app` (not via an
   `APIRouter` prefix), following the Phase 14 `register(app)` function pattern.

3. **`pnl_engine.py` forbidden-import list vs `system_params`.**
   `pnl_engine.py` imports multiplier and cost constants from `system_params.py`.
   `system_params` is a pure-math module (no I/O), so this is hex-boundary safe per D-14.
   The AST guard test for `pnl_engine.py` should use the SAME forbidden list as `sizing_engine.py`
   (which ALSO imports `system_params`). The planner should verify that `system_params` is
   NOT on the forbidden list for `pnl_engine.py` — it is not on the current list. [VERIFIED:
   `sizing_engine.py` line 21: `from system_params import (...)` — already precedent]

4. **`client_with_state_v6` fixture for tests.**
   The existing `client_with_state_v3` fixture in `tests/conftest.py` (Phase 14) seeds a state
   dict with `schema_version: 3`. Phase 19 needs `client_with_state_v6` with `schema_version: 6`
   and an empty `paper_trades: []` array. The planner should include a Wave 0 task to create this
   fixture, following the `client_with_state_v3` pattern exactly.

5. **`_render_paper_trades_region` as the single HTMX response builder.**
   Every mutation returns the full re-rendered `<div id="trades-region">` (D-13 outerHTML swap).
   This means every handler calls the same render function. The planner should verify that
   `dashboard.py::_render_paper_trades_region(state)` is the single call site — and that the
   route handlers return `HTMLResponse(content=_render_paper_trades_region(state))`. This avoids
   the Phase 14 pattern of per-handler partial builders (which works but requires more test surface).

6. **`hx-delete` sends no request body** — FastAPI DELETE route handler cannot accept a Pydantic
   body model. DELETE for paper trades only needs the trade ID (from the URL path param). This is
   correct per REST semantics and HTMX's implementation. [VERIFIED: HTTP DELETE semantics]

---

## Environment Availability

Step 2.6 SKIPPED — Phase 19 has no external dependencies beyond the existing Python 3.11 + FastAPI
+ pytest stack already running on the DO droplet. No new CLIs, runtimes, or services required.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (pinned in requirements.txt) |
| Config file | `pytest.ini` (or `setup.cfg [tool:pytest]`) |
| Quick run command | `pytest tests/test_pnl_engine.py tests/test_web_paper_trades.py -x` |
| Full suite command | `pytest tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| LEDGER-01 | POST /paper-trade/open valid entry → row in state, composite ID, entry_cost_aud correct | unit | `pytest tests/test_web_paper_trades.py::TestOpenPaperTrade -x` | ❌ Wave 0 |
| LEDGER-01 | All D-04 validation rules → 422 per rule | unit | `pytest tests/test_web_paper_trades.py::TestOpenValidation -x` | ❌ Wave 0 |
| LEDGER-02 | Row shape matches D-09 exact key set | unit | `pytest tests/test_web_paper_trades.py::TestRowShape -x` | ❌ Wave 0 |
| LEDGER-02 | `strategy_version` matches `system_params.STRATEGY_VERSION` at write time | unit | `pytest tests/test_web_paper_trades.py::TestStrategyVersionTagging -x` | ❌ Wave 0 |
| LEDGER-03 | Open trades table renders unrealised P&L per row; missing signal → n/a | unit | `pytest tests/test_dashboard.py::TestRenderPaperTrades -x` | ❌ Wave 0 |
| LEDGER-04 | Closed trades table sorted by exit_dt desc | unit | `pytest tests/test_dashboard.py::TestRenderPaperTrades::test_closed_table_sorted -x` | ❌ Wave 0 |
| LEDGER-04 | PATCH closed row → 405 + body + Allow: GET | unit | `pytest tests/test_web_paper_trades.py::TestImmutability::test_patch_closed_returns_405 -x` | ❌ Wave 0 |
| LEDGER-04 | DELETE closed row → 405 + body + Allow: GET | unit | `pytest tests/test_web_paper_trades.py::TestImmutability::test_delete_closed_returns_405 -x` | ❌ Wave 0 |
| LEDGER-05 | Close form populates with trade ID; POST /paper-trade/{id}/close computes realised P&L | unit | `pytest tests/test_web_paper_trades.py::TestClosePaperTrade -x` | ❌ Wave 0 |
| LEDGER-05 | Close form: exit_dt must be >= entry_dt; exit_price > 0 | unit | `pytest tests/test_web_paper_trades.py::TestCloseValidation -x` | ❌ Wave 0 |
| LEDGER-06 | Stats bar: realised, unrealised, wins, losses, win rate correct | unit | `pytest tests/test_dashboard.py::TestRenderPaperTrades::test_stats_bar -x` | ❌ Wave 0 |
| LEDGER-06 | Zero P&L closed trade: not counted as win or loss | unit | `pytest tests/test_dashboard.py::TestRenderPaperTrades::test_zero_pnl_excluded -x` | ❌ Wave 0 |
| VERSION-03 | Monkeypatched STRATEGY_VERSION appears in new paper-trade row | unit | `pytest tests/test_web_paper_trades.py::TestStrategyVersionTagging::test_version_fresh_read -x` | ❌ Wave 0 |
| — | pnl_engine: LONG/SHORT × SPI200/AUDUSD × win/loss parametrize grid | unit | `pytest tests/test_pnl_engine.py -x` | ❌ Wave 0 |
| — | pnl_engine: NaN last_close → NaN result | unit | `pytest tests/test_pnl_engine.py::TestComputeUnrealisedPnl::test_nan_last_close -x` | ❌ Wave 0 |
| — | Migration v5→v6: idempotent, preserves other fields, full v0→v6 walk | unit | `pytest tests/test_state_manager.py::TestMigrateV5ToV6 -x` | ❌ Wave 0 |
| — | Concurrent open: 2 multiprocessing.Process workers → distinct IDs | unit | `pytest tests/test_web_paper_trades.py::TestConcurrent -x` | ❌ Wave 0 |
| — | Counter overflow at 999: raises loud error | unit | `pytest tests/test_web_paper_trades.py::TestCounterOverflow -x` | ❌ Wave 0 |
| — | pnl_engine forbidden-imports AST guard | unit | `pytest tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent -x` | ✅ (extend) |
| — | Cookie-auth middleware: PATCH/DELETE without cookie → 401/302 | unit | `pytest tests/test_web_paper_trades.py::TestAuthEnforcement -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest tests/test_pnl_engine.py tests/test_web_paper_trades.py -x`
- **Per wave merge:** `pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_pnl_engine.py` — covers LONG/SHORT × SPI200/AUDUSD P&L grid + NaN
- [ ] `tests/test_web_paper_trades.py` — skeleton classes for all route tests
- [ ] `tests/conftest.py::client_with_state_v6` — v6-schema state fixture (add to existing conftest)
- [ ] `tests/test_state_manager.py::TestMigrateV5ToV6` — schema migration tests
- [ ] `tests/fixtures/state_v5_no_paper_trades.json` — v5 fixture for migration tests

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Phase 16.1 `AuthMiddleware` — applies to PATCH/DELETE automatically |
| V3 Session Management | no | `tsi_session` session management unchanged |
| V4 Access Control | yes (limited) | Single-operator tool: AuthMiddleware gate is sufficient |
| V5 Input Validation | yes | Server-side D-04 validators; Pydantic v2 models with `extra='forbid'`; `math.isfinite()` on all float inputs |
| V6 Cryptography | no | No new cryptographic operations in Phase 19 |

### CSRF Posture (Phase 19 specific)

`tsi_session` uses `SameSite=Strict` (Phase 16.1 D-11). HTMX PATCH/DELETE requests are
same-origin: the browser sends `tsi_session` automatically. A cross-origin attacker (e.g.,
from `evil.com`) cannot trigger PATCH/DELETE because:
1. `SameSite=Strict` prevents `tsi_session` from being sent on cross-origin requests.
2. The `X-Trading-Signals-Auth` header (injected via `hx-headers` in HTMX forms) cannot be
   set by a cross-origin page (Fetch/XHR CORS blocks header injection from foreign origins).

**Conclusion:** No CSRF token machinery needed. [CITED: Phase 14 CONTEXT.md 'CSRF posture',
Phase 16.1 D-13] [VERIFIED: SameSite=Strict in web/routes/login.py line 51]

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Closed-row mutation via PATCH/DELETE | Tampering | `status=closed` check before mutate; return 405 before entering mutate_state |
| Trade ID path traversal (`/paper-trade/../other-route`) | Tampering | FastAPI path parameter validation; composite ID format `^[A-Z0-9]+-\d{8}-\d{3}$` — route match only fires for conforming IDs |
| XSS via `entry_price` float display | Tampering | `html.escape(str(value), quote=True)` in all render helpers; float → string → escape |
| Stale state read under concurrent modification | Tampering | `mutate_state` flock kernel — ID generation inside the lock prevents stale-read ID collision |
| Integer overflow in `contracts` field | Tampering | Pydantic `contracts: int = Field(ge=1)` for SPI200; validation D-04 rejects ≤ 0 |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | HTMX 1.9.12 `hx-confirm` triggers native `window.confirm()` on iOS Safari 17+ without regression | §Pattern 6, §Pitfall 7 | If `window.confirm()` is blocked (e.g., operator has dialog suppression enabled in Safari settings), delete confirmations are skipped silently. Mitigation: test on real device during UAT. |
| A2 | `hx-delete` on HTMX 1.9.12 sends zero request body (DELETE has no body) | §Risks #6 | If HTMX sends a body with DELETE, FastAPI route would ignore it (no Pydantic body param). No security risk; no functional impact. |
| A3 | `pnl_engine.py` forbidden-import list should mirror `sizing_engine.py` exactly | §Don't Hand-Roll, §Pitfall 9 | If `system_params` is accidentally added to the forbidden list for `pnl_engine`, the AST guard fails. Verify the test's forbidden set before Wave 1 ships. |
| A4 | The Phase 14 `json-enc` HTMX extension is available at the pinned HTMX 1.9.12 URL | §Risks #1 | If `json-enc` is not bundled in the 1.9.12 CDN release, PATCH form bodies would arrive as form-encoded and FastAPI would 422. The extension was added in HTMX 1.5.0; 1.9.12 definitely includes it. LOW risk. |

**Claims tagged `[VERIFIED]` throughout: confirmed via direct Python execution or codebase read.
Claims tagged `[CITED]`: referenced from CONTEXT.md or LEARNINGS.md.
Claims tagged `[ASSUMED]`: based on training knowledge + high-confidence HTMX/iOS documentation.**

---

## Sources

### Primary (HIGH confidence)
- `[VERIFIED: web/routes/trades.py — read directly]` — Phase 14 route shape, `mutate_state` closure pattern, `hx-ext="json-enc"` REVIEW CR-01, 405 response handling
- `[VERIFIED: web/middleware/auth.py — read directly]` — AuthMiddleware applies to ALL HTTP methods; cookie validation; SameSite=Strict confirmed at line 51 of login.py
- `[VERIFIED: sizing_engine.py — read directly]` — `compute_unrealised_pnl` signature (Position TypedDict + plain floats); hex-boundary precedent
- `[VERIFIED: dashboard.py — read directly]` — HTMX 1.9.12 pin; `flex-wrap: wrap` CSS; no existing sticky elements; `hx-include="this"` pattern
- `[VERIFIED: direct Python execution]` — FastAPI TestClient `.patch()` / `.delete()` native support; FastAPI auto-405 includes Allow header; manual `Response(405)` does not; NaN propagation through P&L formula; multiprocessing flock race test works correctly
- `[VERIFIED: .claude/LEARNINGS.md — read directly]` — kwarg-default capture trap entry (2026-04-27)
- `[VERIFIED: 19-CONTEXT.md — read directly]` — all D-01..D-16 locked decisions

### Secondary (MEDIUM confidence)
- `[CITED: 22-CONTEXT.md D-07]` — STRATEGY_VERSION kwarg-default trap; D-05 migration pattern
- `[CITED: 17-CONTEXT.md D-08, D-09]` — schema migration pattern (v4→v5 analog for v5→v6)
- `[CITED: 14-CONTEXT.md D-13]` — `mutate_state` kernel docstring; flock reentrancy within process
- `[CITED: RFC 7231 §6.5.5]` — 405 MUST include Allow header
- `[CITED: web/routes/login.py line 51]` — `SameSite=Strict` confirmed on `tsi_session` cookie

### Tertiary (LOW confidence — see Assumptions Log)
- `[ASSUMED: HTMX 1.x docs behavior]` — `hx-confirm` triggers `window.confirm()` natively; `hx-delete` sends no body; `json-enc` extension bundled in 1.9.12

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new deps; all existing pinned libs; PATCH/DELETE behavior verified
- Architecture: HIGH — mirrors Phase 14 pattern exactly; close-form ID flow verified
- Pitfalls: HIGH for 405/Allow header (verified), kwarg-default trap (cited from LEARNINGS), sticky overflow (verified); MEDIUM for hx-confirm iOS regression (assumed)
- P&L math: HIGH — all formula paths verified via Python execution

**Research date:** 2026-04-30
**Valid until:** 2026-05-31 (stable stack; HTMX 1.9.12 is pinned; no planned upgrades)
