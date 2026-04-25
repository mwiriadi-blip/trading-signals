# Phase 14: Trade Journal — Mutation Endpoints — Pattern Map

**Mapped:** 2026-04-25
**Files analyzed:** 13 (4 NEW + 9 MODIFIED)
**Analogs found:** 12 / 13 (one Phase-14-novel concern — fcntl lock — has no in-codebase analog and points to RESEARCH §Pattern 9)

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `web/routes/trades.py` (NEW) | controller (route module) | request-response | `web/routes/state.py` | exact (route module + register() shape) — extends with POST + Pydantic + local mutating import |
| `tests/test_web_trades.py` (NEW) | test (endpoint contract + AST guard) | request-response | `tests/test_web_state.py` + `tests/test_web_healthz.py::TestWebHexBoundary` | exact (HTMX-aware extension of `client_with_state` + AST-walk guard) |
| `tests/fixtures/state_v2_no_manual_stop.json` (NEW) | test fixture (JSON state) | file-I/O | `tests/fixtures/dashboard/sample_state.json` | exact (full v2-schema state with Position dicts but no `manual_stop` key) |
| `tests/test_dashboard.py` (extended) | test (render + HTMX form markup) | request-response | existing `tests/test_dashboard.py` (golden-html parity test pattern) | role-match (extend with new HTMX-form structural assertions) |
| `state_manager.py::_migrate_v2_to_v3` (NEW function) | service (migration step) | transform | `state_manager._migrate_v1_to_v2` (line 86) | exact (named function + lambda registration in MIGRATIONS dict) |
| `state_manager._atomic_write` / `save_state` (MODIFIED) | service (atomic I/O) | file-I/O | existing `_atomic_write` (line 113) | exact for shape; **fcntl-lock wrap is novel — no in-codebase analog → use RESEARCH §Pattern 9 verbatim** |
| `system_params.Position` TypedDict (MODIFIED) | model (TypedDict) | data shape | existing Position field block (line 137-158) | exact (add one field with `float \| None` annotation matching `peak_price`/`trough_price` precedent) |
| `sizing_engine.get_trailing_stop` (MODIFIED) | service (pure-math) | transform | existing function (line 180-240) | exact (insert manual_stop branch ABOVE existing direction switch) |
| `web/app.py` (MODIFIED) | config (FastAPI factory) | request-response | existing `create_app()` route registration block (line 86-89) | exact (one extra `register()` call + one `add_exception_handler()` call) |
| `dashboard.py::_render_positions_table` (MODIFIED) | component (HTML table) | request-response | existing `_render_positions_table` (line 683-760) | exact (add Actions column + per-row id + manual badge to existing rendering loop) |
| `requirements.txt` (DOC-ONLY) | config | n/a | existing requirements.txt | n/a — no new pins; HTMX is CDN-vendored (mirrors Chart.js precedent at `dashboard.py:115-116`) |
| `tests/test_state_manager.py::TestAtomicity` (extended) | test (atomicity + fcntl) | file-I/O | existing `TestAtomicity` (line 221-340) | exact for atomicity assertions; fcntl-test-pattern is novel → see RESEARCH §Pattern 9 (multiprocess holder fixture) |
| `tests/test_sizing_engine.py::TestTrailingStop` (extended) | test (pure-math) | transform | existing trailing-stop tests (line 421-453) | exact (add `TestManualStopOverride` class with same `_make_position` helper) |
| `tests/test_system_params.py::TestPositionTypedDict` (NEW or extended) | test (type-shape) | n/a | (no current explicit Position-shape test — see "No Analog Found" below) | partial — RESEARCH §Pattern 11 prescribes a round-trip-via-load_state test instead |
| `tests/test_web_healthz.py::TestWebHexBoundary.FORBIDDEN_FOR_WEB` (MODIFIED) | test (AST guard) | n/a | existing `FORBIDDEN_FOR_WEB` block (line 188-191) | exact (remove `'sizing_engine'` mirroring how Phase 13 D-07 removed `'dashboard'` — analog: line 184-187 comment + line 212-214 regression test) |
| `tests/conftest.py` (extended) | test fixture | n/a | existing autouse `_set_web_auth_secret_for_web_tests` (line 35-53) + `auth_headers` fixture (line 62-65) | exact (add HTMX-header fixture and `client_with_state_v3` fixture mirroring `tests/test_web_state.py::client_with_state` at line 39-62) |

---

## Pattern Assignments

### `web/routes/trades.py` (NEW — controller, request-response)

**Analog:** `web/routes/state.py` (62 lines — direct shape match for module docstring + register() + local-import-inside-handler)

**Module docstring + imports pattern** (`web/routes/state.py:1-43`):
```python
'''GET /api/state — Phase 13 WEB-06 + D-12..D-15.

Returns the current state.json as JSON, with top-level underscore-prefixed
keys stripped. Used by mobile / CLI / external scripts that need the
source-of-truth state without HTML rendering.

Contract (CONTEXT.md 2026-04-25):
  D-12: ...
  D-13: ...
  D-14: ...
  D-15: ...

Architecture (CLAUDE.md hex-lite + Phase 10 D-15):
  web/routes/ is an adapter hex.
  Allowed: fastapi, starlette, stdlib, state_manager (read-only per Phase 10 D-15).
  Forbidden: signal_engine, sizing_engine, system_params, notifier, main, dashboard.
  Enforced by tests/test_web_healthz.py::TestWebHexBoundary.

  state_manager import is LOCAL (inside the handler) per Phase 11 C-2.

Log prefix: [Web].
'''
import logging

from fastapi import FastAPI
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
```

**Phase 14 adaptation (mandatory text in docstring):**
- Cite `Phase 14 D-01..D-13` (replacing Phase 13 D-12..D-15 references)
- **Architecture section MUST extend "Allowed" to include `sizing_engine` (Phase 14 D-02 — `check_pyramid` import) AND `state_manager` becomes read+write per Phase 14 D-14 amendment.**
- **Architecture section MUST acknowledge Phase 14 D-14 amendment to Phase 10 D-15** ("web is no longer read-only on state.json — coordinated via fcntl lock per D-13").

**register() function pattern** (`web/routes/state.py:46-66`):
```python
def register(app: FastAPI) -> None:
  '''Register GET /api/state on the given FastAPI instance.'''

  @app.get('/api/state')
  def get_state():
    from state_manager import load_state  # local import — C-2 hex boundary

    state = load_state()  # D-14: trust Phase 3 recovery; no try/except here

    # D-12: strip TOP-LEVEL underscore-prefixed keys only. Nested dicts
    # (e.g., positions[instrument] dicts) keep their keys intact in case
    # v1.2 adds a legitimate `_comment` or similar inside a position.
    clean = {k: v for k, v in state.items() if not k.startswith('_')}

    return JSONResponse(
      content=clean,
      headers={'Cache-Control': 'no-store'},  # D-13
    )
    # D-15: FastAPI JSONResponse default is compact (no indent) — no
    # additional kwarg needed. Verified by RESEARCH.md §JSONResponse defaults.
```

**Phase 14 adaptation:**
- Use `@app.post(...)` decorator instead of `@app.get(...)` for the three mutation endpoints.
- Local imports inside each POST handler MUST include `state_manager` AND `sizing_engine` (per Phase 14 D-02 / hex extension): `from state_manager import load_state, save_state, record_trade` and `from sizing_engine import check_pyramid`.
- Import `system_params.MAX_PYRAMID_LEVEL` locally inside the Pydantic `model_validator` (per RESEARCH §Pattern 1 line 343).

**Pydantic v2 schema + handler bodies:** Use **RESEARCH §Pattern 1, §Pattern 2, §Pattern 3 verbatim** (lines 287-520 of `14-RESEARCH.md`). These are research-composed — there is no in-codebase Pydantic-v2 analog (Phase 13 used neither request bodies nor Pydantic models).

**Anti-pitfall comment (D-05) MUST appear inline in `close_trade` handler:**
```python
# D-05 ANTI-PITFALL — DO NOT USE sizing_engine.compute_unrealised_pnl HERE.
# record_trade D-14 deducts the closing-half cost. compute_unrealised_pnl
# already deducts the opening-half cost. Passing realised_pnl as gross_pnl
# would double-count the closing cost. See state_manager.py:499-506,
# Phase 4 D-15/D-19 anti-pitfall.
```

---

### `tests/test_web_trades.py` (NEW — test, request-response + AST guard)

**Analog 1 (TestClient + state-stubbing fixture):** `tests/test_web_state.py:1-62` (`client_with_state` factory)

**Verbatim fixture excerpt** (`tests/test_web_state.py:38-62`):
```python
@pytest.fixture
def client_with_state(monkeypatch):
  '''Build a TestClient with a configurable load_state.

  WEB_AUTH_SECRET is preset by the autouse fixture in tests/conftest.py.
  Yields a (client, set_state_fn) tuple. Caller invokes set_state_fn(payload)
  to control what state_manager.load_state returns for that test.
  '''
  import sys
  sys.modules.pop('web.app', None)
  from web.app import create_app

  state_box = {'value': {'schema_version': 1, 'last_run': '2026-04-25'}}

  import state_manager
  monkeypatch.setattr(
    state_manager, 'load_state', lambda *_a, **_kw: state_box['value']
  )

  client = TestClient(create_app())

  def set_state(payload):
    state_box['value'] = payload

  return client, set_state
```

**Phase 14 adaptation:**
- Rename to `client_with_state_v3` and seed `state_box['value']` with a state dict whose `schema_version=3` AND whose `positions` dicts contain the new `manual_stop` key.
- Add a parallel `monkeypatch.setattr(state_manager, 'save_state', ...)` so POST handlers can be tested without disk I/O. Capture saved-state via a list closure for assertions.
- Add a `htmx_headers` fixture: `return {'X-Trading-Signals-Auth': VALID_SECRET, 'HX-Request': 'true'}` so HTMX-aware code paths can be exercised.

**Analog 2 (AST-walk guard for invariants):** `tests/test_web_healthz.py::TestWebHexBoundary` (line 181-245)

**Verbatim AST-walk pattern** (`tests/test_web_healthz.py:193-210`):
```python
def test_web_modules_do_not_import_hex_core(self):
  import ast

  web_dir = Path('web')
  violations = []
  for py_file in sorted(web_dir.rglob('*.py')):
    tree = ast.parse(py_file.read_text())
    for node in ast.walk(tree):
      if isinstance(node, ast.Import):
        for alias in node.names:
          top = alias.name.split('.')[0]
          if top in self.FORBIDDEN_FOR_WEB:
            violations.append(f'{py_file}:{node.lineno}: import {alias.name}')
      elif isinstance(node, ast.ImportFrom) and node.module:
        top = node.module.split('.')[0]
        if top in self.FORBIDDEN_FOR_WEB:
          violations.append(f'{py_file}:{node.lineno}: from {node.module}')
  assert violations == [], '\n'.join(violations)
```

**Phase 14 adaptation:** Use this exact AST-walk shape for the new `TestSoleWriterInvariant` class enforcing TRADE-06. The full new test body is given in **RESEARCH §Pattern 10 (line 752-783) verbatim** — copy that into `tests/test_web_trades.py`.

---

### `tests/fixtures/state_v2_no_manual_stop.json` (NEW — fixture, file-I/O)

**Analog:** `tests/fixtures/dashboard/sample_state.json` (lines 246-258 — full Position dict)

**Verbatim positions block** (`tests/fixtures/dashboard/sample_state.json:246-258`):
```json
"positions": {
  "AUDUSD": null,
  "SPI200": {
    "atr_entry": 50.0,
    "direction": "LONG",
    "entry_date": "2026-04-10",
    "entry_price": 8000.0,
    "n_contracts": 2,
    "peak_price": 8100.0,
    "pyramid_level": 0,
    "trough_price": null
  }
},
"schema_version": 1,
```

**Phase 14 adaptation:**
- Bump `"schema_version": 2` (the fixture's purpose is the v2→v3 migration round-trip per RESEARCH §Pattern 11; v2 is the state on disk before Phase 14 ships).
- Position dict MUST NOT contain `manual_stop` — the migration is responsible for adding `manual_stop: null` on first load.
- Include both instruments with at least one open Position (so the migration can be observed on a non-empty positions dict). Recommend SPI200 LONG and AUDUSD SHORT (covers both peak_price/trough_price branches).
- Include the Phase 8 v2-schema mandatory keys (`initial_account`, `contracts` per `state_manager._REQUIRED_STATE_KEYS` at `state_manager.py:75-80`).

---

### `tests/test_dashboard.py` (extended — render parity + HTMX-form markup)

**Analog:** existing tests in `tests/test_dashboard.py` (golden-html parity tests) — only structural search needed; no exact line excerpt because golden-comparison is the established pattern.

**Phase 14 adaptation (per UI-SPEC §Decision 1, 2, 6, 7):**
- Add `TestOpenForm` class asserting the rendered HTML contains: `<section class="open-form">`, `hx-post="/trades/open"`, `hx-target="#positions-tbody"`, and the four required `<input>`/`<select>` elements with the `for=`/`id=` accessibility wiring.
- Add `TestActionsColumn` class asserting `<th scope="col">Actions</th>`, `id="position-row-SPI200"`, `class="btn-row btn-close"` and `class="btn-row btn-modify"` are present per row.
- Add `TestManualStopBadge` class with two scenarios: `manual_stop=None` → no `class="badge badge-manual"` in rendered HTML; `manual_stop=7700.0` → badge present and the displayed Trail Stop value equals the `manual_stop` value (verifies `_compute_trail_stop_display` precedence per UI-SPEC §Decision 6).
- The empty-state `colspan` change (8 → 9 per UI-SPEC §Decision 2) requires regenerating the existing dashboard golden via `tests/regenerate_dashboard_golden.py`. Document in PLAN.md.

---

### `state_manager.py::_migrate_v2_to_v3` (NEW function — service, transform)

**Analog:** `state_manager._migrate_v1_to_v2` at `state_manager.py:86-101`

**Verbatim function body:**
```python
def _migrate_v1_to_v2(s: dict) -> dict:
  '''Phase 8 CONF-01/CONF-02 backfill: add initial_account (default $100k)
  and contracts (default mini tier) for pre-v2 state files.

  D-15 silent migration: no append_warning, no log. s.get(..., default) is
  idempotent when the keys are already present — operator choice (a state
  file with 'initial_account'/'contracts' already set) is preserved.
  '''
  return {
    **s,
    'initial_account': s.get('initial_account', INITIAL_ACCOUNT),
    'contracts': s.get('contracts', {
      'SPI200': _DEFAULT_SPI_LABEL,
      'AUDUSD': _DEFAULT_AUDUSD_LABEL,
    }),
  }


MIGRATIONS: dict = {
  1: lambda s: s,  # no-op at v1; hook proves the walk-forward mechanism works
  2: _migrate_v1_to_v2,  # Phase 8 IN-06: named function for future migrations
}
```

**Phase 14 adaptation:** Use **RESEARCH §Pattern 11 verbatim** (lines 793-826 of `14-RESEARCH.md`) for the new `_migrate_v2_to_v3` body. Critical points:
- The function walks `s.get('positions', {})` and adds `'manual_stop': pos.get('manual_stop')` to each non-None Position dict.
- Idempotent: re-running on already-migrated state is a no-op.
- Add to `MIGRATIONS` dict as `3: _migrate_v2_to_v3,` (mirroring the existing `2: _migrate_v1_to_v2` registration line).
- Bump `STATE_SCHEMA_VERSION` in `system_params.py:111` from `2` to `3`.

---

### `state_manager._atomic_write` + `save_state` (MODIFIED — service, file-I/O)

**Analog:** existing `_atomic_write` at `state_manager.py:113-158` (the function that gets the fcntl wrap)

**Verbatim existing body** (`state_manager.py:113-158`):
```python
def _atomic_write(data: str, path: Path) -> None:
  '''STATE-02 / D-08 (amended by D-17): tempfile + fsync(file) + os.replace + fsync(parent dir).
  ...
  '''
  parent = path.parent
  tmp_path_str = None
  try:
    with tempfile.NamedTemporaryFile(
      dir=parent, delete=False, mode='w', suffix='.tmp', encoding='utf-8',
    ) as tmp:
      tmp_path_str = tmp.name
      tmp.write(data)
      tmp.flush()
      os.fsync(tmp.fileno())
    # tempfile is now closed (NamedTemporaryFile context exit)
    # D-17: os.replace BEFORE parent-dir fsync (rename durability)
    os.replace(tmp_path_str, path)
    if os.name == 'posix':
      dir_fd = os.open(str(parent), os.O_RDONLY)
      try:
        os.fsync(dir_fd)
      finally:
        os.close(dir_fd)
    tmp_path_str = None  # success: do not delete in finally
  finally:
    if tmp_path_str is not None:
      try:
        os.unlink(tmp_path_str)
      except FileNotFoundError:
        pass
```

**Existing `save_state` body** (`state_manager.py:404-429`) — what gets the lock-wrap diff:
```python
def save_state(state: dict, path: Path = Path(STATE_FILE)) -> None:
  '''STATE-02 / D-08 (amended by D-17): atomic write of state to path.
  ...
  '''
  # D-14 (Phase 8): strip runtime-only keys (underscore-prefixed) before
  # dumping. ...
  persisted = {k: v for k, v in state.items() if not k.startswith('_')}
  data = json.dumps(persisted, sort_keys=True, indent=2, allow_nan=False)
  _atomic_write(data, path)
```

**Phase 14 adaptation:**
- **No in-codebase analog for fcntl.flock — this concern is brand new.** Use **RESEARCH §Pattern 9 verbatim** (lines 686-736 of `14-RESEARCH.md`) for the wrapped function.
- Discipline (RESEARCH §Pattern 9): open the **destination** file for the lock (NOT the tempfile) via `os.open(str(path), os.O_RDWR | os.O_CREAT, 0o644)`, acquire `fcntl.flock(lock_fd, fcntl.LOCK_EX)`, perform the existing tempfile→fsync→replace→dir-fsync sequence INSIDE the lock-held window, then `fcntl.flock(lock_fd, fcntl.LOCK_UN)` and `os.close(lock_fd)` in `finally`.
- Augment the `_atomic_write` docstring with a "Phase 14 D-13" amendment block describing the lock semantics, mirroring how `_atomic_write` was amended by D-17 in Phase 8.

**Analog for the new lock-contention test:** **No in-codebase analog.** Use RESEARCH §Pattern 9 line 743 prescription: a pytest fixture spawning a `multiprocessing.Process` that holds `fcntl.LOCK_EX` on `state.json` for 0.5s; main test asserts `save_state` blocks for `>= 0.4s` and `< 1.0s`.

---

### `system_params.Position` TypedDict (MODIFIED — model)

**Analog:** existing Position TypedDict at `system_params.py:137-158`

**Verbatim existing block:**
```python
class Position(TypedDict):
  '''Open position state. Round-trips directly to/from Phase 3 state.json.

  Fields:
    direction:     'LONG' or 'SHORT'
    entry_price:   Fill price at position open
    entry_date:    ISO YYYY-MM-DD of entry bar
    n_contracts:   Current contract count (may increase via pyramid)
    pyramid_level: 0 = initial, 1 = added once, 2 = added twice (cap, PYRA-04)
    peak_price:    Highest HIGH since entry for LONG; None for SHORT (D-08)
    trough_price:  Lowest LOW since entry for SHORT; None for LONG (D-08)
    atr_entry:     ATR at time of entry — used for stop distance + pyramid
                   thresholds (D-15: stop anchored to entry ATR, not today's)
  '''
  direction: Literal['LONG', 'SHORT']
  entry_price: float
  entry_date: str
  n_contracts: int
  pyramid_level: int
  peak_price: float | None       # LONG: highest HIGH since entry; None for SHORT
  trough_price: float | None     # SHORT: lowest LOW since entry; None for LONG
  atr_entry: float
```

**Phase 14 adaptation:**
- Add **one** new field at the bottom of the field list:
  ```python
  manual_stop: float | None      # Phase 14 D-09: operator override for trailing stop;
                                 # None = use computed peak/trough trailing stop
  ```
- Extend the docstring `Fields:` block with one line for `manual_stop`.
- Match precedent: `peak_price` / `trough_price` already use `float | None` annotation — `manual_stop` follows verbatim.
- Bump `STATE_SCHEMA_VERSION` from 2 to 3 (line 111).

---

### `sizing_engine.get_trailing_stop` (MODIFIED — service, transform)

**Analog:** existing function at `sizing_engine.py:180-240`

**Verbatim existing body** (the bit that gets the manual-stop branch):
```python
def get_trailing_stop(
  position: Position,
  current_price: float,
  atr: float,
) -> float:
  '''EXIT-06/07: compute current trailing stop price. D-15 anchor: stop distance
  uses position['atr_entry'], NOT the `atr` argument.
  ...
  B-1 NaN policy: if position['atr_entry'] is NaN (broken upstream data),
  return float('nan'). ...
  '''
  del current_price  # Reserved; not used in trail-stop math (D-16).
  del atr  # D-15: stop distance uses position['atr_entry'] not this parameter.
  atr_entry = position['atr_entry']
  if not math.isfinite(atr_entry):
    return float('nan')  # B-1: NaN-pass-through
  if position['direction'] == 'LONG':
    peak = position['peak_price']
    if peak is None:
      peak = position['entry_price']
    return peak - TRAIL_MULT_LONG * atr_entry
  # SHORT branch
  trough = position['trough_price']
  if trough is None:
    trough = position['entry_price']
  return trough + TRAIL_MULT_SHORT * atr_entry
```

**Phase 14 adaptation:**
- Insert the manual_stop precedence branch **AFTER the NaN guard** (so NaN passthrough is preserved when `atr_entry` is NaN regardless of `manual_stop`) and **BEFORE the LONG/SHORT direction switch**:
  ```python
  # Phase 14 D-09: manual_stop takes precedence over computed trailing stop.
  # When operator has set a stop via /trades/modify, return it directly.
  # When None (default), fall through to v1.0 computed trailing stop.
  manual = position.get('manual_stop')
  if manual is not None:
    return manual
  ```
- Use `position.get('manual_stop')` (NOT `position['manual_stop']`) so the function still works on pre-migration state dicts loaded from disk (defensive read; `_migrate_v2_to_v3` will backfill on next load_state but transient calls during migration must not KeyError).
- Update the docstring's "Pitfall" section with a new "Phase 14 D-09" bullet describing the manual_stop precedence.
- The mirror update in `dashboard.py::_compute_trail_stop_display` (per UI-SPEC §Decision 6) MUST use the IDENTICAL precedence — copy the same `manual = position.get('manual_stop'); if manual is not None: return manual` block. Existing parity test (CLAUDE.md hex-lite §`sizing_engine` and `dashboard` lockstep) will catch divergence.

---

### `web/app.py` (MODIFIED — config, FastAPI factory)

**Analog:** existing `create_app()` at `web/app.py:60-101` — direct copy of the route-registration block

**Verbatim existing block** (`web/app.py:86-94`):
```python
  # Register routes first (they become the inner-most layer of the dispatch).
  healthz_route.register(application)
  dashboard_route.register(application)
  state_route.register(application)

  # D-06: AuthMiddleware MUST be registered LAST — Starlette runs middleware
  # in REVERSE of registration, so 'last registered' = 'first to dispatch'.
  # Future middleware (request-id, compression) goes ABOVE this line.
  application.add_middleware(AuthMiddleware, secret=secret)
```

**Phase 14 adaptation:**
- Add `from web.routes import trades as trades_route` to module-top imports (mirroring `from web.routes import state as state_route` at line 30).
- Insert `trades_route.register(application)` after `state_route.register(application)` and BEFORE `application.add_middleware(...)`.
- Add the 422→400 remap exception handler per **RESEARCH §Pattern 6 verbatim** (lines 575-608). The handler registration line `application.add_exception_handler(RequestValidationError, _validation_exception_handler)` goes BETWEEN the route-registrations and the `add_middleware` call (Starlette runs handlers from in-to-out; placement within create_app() doesn't affect dispatch order, but keep grouped with route registrations for readability).
- Update the docstring (lines 1-21) to add a Phase 14 D-13/D-14 paragraph documenting the amendment to D-15 and the new trades_route.

---

### `dashboard.py::_render_positions_table` (MODIFIED — component, HTML rendering)

**Analog:** existing function at `dashboard.py:683-760`

**Verbatim existing core loop and table structure** (`dashboard.py:730-760`):
```python
  if not rendered_rows:
    rendered_rows = [
      '      <tr>\n'
      '        <td colspan="8" class="empty-state">— No open positions —</td>\n'
      '      </tr>\n'
    ]
  body = ''.join(rendered_rows)
  return (
    '<section aria-labelledby="heading-positions">\n'
    '  <h2 id="heading-positions">Open Positions</h2>\n'
    '  <table class="data-table">\n'
    '    <caption class="visually-hidden">Open positions with current price, '
    'contracts, trail stop, and unrealised P&amp;L</caption>\n'
    '    <thead>\n'
    '      <tr>\n'
    '        <th scope="col">Instrument</th>\n'
    '        <th scope="col">Direction</th>\n'
    '        <th scope="col">Entry</th>\n'
    '        <th scope="col">Current</th>\n'
    '        <th scope="col">Contracts</th>\n'
    '        <th scope="col">Pyramid</th>\n'
    '        <th scope="col">Trail Stop</th>\n'
    '        <th scope="col">Unrealised P&amp;L</th>\n'
    '      </tr>\n'
    '    </thead>\n'
    '    <tbody>\n'
    f'{body}'
    '    </tbody>\n'
    '  </table>\n'
    '</section>\n'
  )
```

**Verbatim existing per-row rendering pattern** (`dashboard.py:711-728`):
```python
trail_stop = _compute_trail_stop_display(pos)
trail_cell = html.escape(_fmt_currency(trail_stop), quote=True)
unrealised = _compute_unrealised_pnl_display(pos, state_key, last_close, state)
if unrealised is None:
  pnl_cell = html.escape(_fmt_em_dash(), quote=True)
else:
  pnl_cell = _fmt_pnl_with_colour(unrealised)  # already html.escape'd internally
rendered_rows.append(
  '      <tr>\n'
  f'        <td>{instrument_cell}</td>\n'
  f'        <td><span style="color: {dir_colour}">{dir_label}</span></td>\n'
  f'        <td class="num">{entry_cell}</td>\n'
  f'        <td class="num">{current_cell}</td>\n'
  f'        <td class="num">{contracts_cell}</td>\n'
  f'        <td class="num">{pyramid_cell}</td>\n'
  f'        <td class="num">{trail_cell}</td>\n'
  f'        <td class="num">{pnl_cell}</td>\n'
  '      </tr>\n'
)
```

**Phase 14 adaptation (per UI-SPEC §Decision 2, 6):**
- Wrap each `<tr>` with `id="position-row-{state_key}"` (e.g., `id="position-row-SPI200"`).
- Wrap the `<tbody>` with `id="positions-tbody"` (UI-SPEC §Decision 3 hx-target).
- Add `<th scope="col">Actions</th>` to the thead row (9 columns now, not 8).
- Append a new `<td>` per row containing the two HTMX action buttons per UI-SPEC §Decision 2:
  ```html
  <td>
    <button class="btn-row btn-close" type="button"
            hx-get="/trades/close-form?instrument={state_key}"
            hx-target="#position-row-{state_key}"
            hx-swap="outerHTML">Close</button>
    <button class="btn-row btn-modify" type="button"
            hx-get="/trades/modify-form?instrument={state_key}"
            hx-target="#position-row-{state_key}"
            hx-swap="outerHTML">Modify</button>
  </td>
  ```
- Modify the `trail_cell` to append the manual badge per UI-SPEC §Decision 6 when `pos.get('manual_stop') is not None`. Use the existing `_compute_trail_stop_display` (which Phase 14 modifies per UI-SPEC §Decision 6 final-paragraph code block — copy the manual_stop precedence inline matching `sizing_engine.get_trailing_stop`).
- Update the empty-state row to `colspan="9"` (was 8 — UI-SPEC §Decision 2).

**HTMX vendor pin:** Use **RESEARCH §Pattern 7 verbatim** (lines 619-633). Place the new `_HTMX_URL` and `_HTMX_SRI` constants adjacent to the existing `_CHARTJS_URL` / `_CHARTJS_SRI` block at `dashboard.py:115-116`:
```python
# Existing (dashboard.py:115-116):
_CHARTJS_URL = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.js'
_CHARTJS_SRI = 'sha384-MH1axGwz/uQzfIcjFdjEfsM0xlf5mmWfAwwggaOh5IPFvgKFGbJ2PZ4VBbgSYBQN'

# Phase 14 NEW (place immediately after):
_HTMX_URL = 'https://cdn.jsdelivr.net/npm/htmx.org@1.9.12/dist/htmx.min.js'
_HTMX_SRI = 'sha384-ujb1lZYygJmzgSwoxRggbCHcjc0rB2XoQrxeTUQyRjrOnlCoYta87iKBWq3EsdM2'
```

The HTMX `<script>` tag goes in the existing `<head>`-emitting helper at `dashboard.py:989-991` (the Chart.js block) — INSERT after the Chart.js script tag, BEFORE the closing `</head>`, per UI-SPEC §HTMX vendor pin.

---

### `tests/test_state_manager.py::TestAtomicity` (extended — test, file-I/O)

**Analog:** existing `TestAtomicity` class at `tests/test_state_manager.py:221-340`

**Verbatim atomicity-mock pattern** (`tests/test_state_manager.py:229-250`):
```python
def test_crash_on_os_replace_leaves_original_intact(self, tmp_path) -> None:
  '''STATE-02: if os.replace raises mid-write, state.json is byte-identical to original.'''
  path = tmp_path / 'state.json'
  original_state = {
    'schema_version': 1, 'account': 99999.0, 'last_run': None,
    'positions': {'SPI200': None, 'AUDUSD': None},
    'signals': {'SPI200': 0, 'AUDUSD': 0},
    'trade_log': [], 'equity_history': [], 'warnings': [],
  }
  save_state(original_state, path=path)
  original_bytes = path.read_bytes()

  new_state = dict(original_state)
  new_state['account'] = 50000.0

  with patch('state_manager.os.replace', side_effect=OSError('disk full')):
    with pytest.raises(OSError, match='disk full'):
      save_state(new_state, path=path)

  assert path.read_bytes() == original_bytes, (
    'STATE-02: original state.json must be byte-identical after failed os.replace'
  )
```

**Phase 14 adaptation:**
- All existing TestAtomicity tests MUST remain green after Phase 14's fcntl wrap (regression discipline per CONTEXT D-13: "Required regression test pass after the change: `pytest tests/test_state_manager.py -x` must remain 100% green").
- Add new `TestFcntlLock` class with three tests:
  1. `test_save_state_blocks_when_external_lock_held`: per RESEARCH §Pattern 9 line 743 — multiprocess holder spawns, holds `fcntl.LOCK_EX` for 0.5s; `save_state` from main test blocks, returns after `>= 0.4s` and `< 1.0s` elapsed. Use `multiprocessing.Process` and `time.perf_counter()`.
  2. `test_save_state_releases_lock_after_successful_write`: after `save_state` returns, a separate `os.open()` + `fcntl.flock(LOCK_EX | LOCK_NB)` succeeds immediately (no stale lock).
  3. `test_save_state_releases_lock_after_failed_os_replace`: combined with existing `test_crash_on_os_replace_leaves_original_intact` pattern — patch `os.replace` to raise; verify the lock is still released (next `flock(LOCK_EX | LOCK_NB)` succeeds).
- Add `Test_v2_to_v3_Migration` class (per RESEARCH §Pattern 11 line 838-841):
  - `test_v2_state_loads_with_manual_stop_backfilled_to_None`: load `tests/fixtures/state_v2_no_manual_stop.json`, assert each non-None position has `manual_stop is None`.
  - `test_save_then_load_v3_round_trips`: load v2 → save → re-load → identical Position dicts.
  - `test_migration_idempotent`: `_migrate_v2_to_v3(_migrate_v2_to_v3(state))` produces identical dict.

**Existing migration-test analog** (`tests/test_state_manager.py:1142-1171`) for the new `Test_v2_to_v3_Migration` class shape:
```python
def test_migrate_v2_appends_no_warning(self) -> None:
  '''D-15: _migrate on v1 state MUST NOT append a warning — silent
  migration. Backfill is transparent to the operator.'''
  state = {
    'schema_version': 1,
    'account': INITIAL_ACCOUNT, 'last_run': None,
    'positions': {'SPI200': None, 'AUDUSD': None},
    'signals': {'SPI200': 0, 'AUDUSD': 0},
    'trade_log': [], 'equity_history': [], 'warnings': [],
  }
  warnings_before = list(state['warnings'])  # copy
  migrated = _migrate(state)
  assert migrated['warnings'] == warnings_before, (
    f'D-15: _migrate must NOT append a warning; '
    f'before={warnings_before!r} after={migrated["warnings"]!r}'
  )

def test_migrate_walks_schema_version_to_current(self) -> None:
  '''STATE-04 (Phase 8 extension): after _migrate, schema_version equals
  STATE_SCHEMA_VERSION (now 2 per Phase 8).'''
  ...
  migrated = _migrate(state)
  assert migrated['schema_version'] == STATE_SCHEMA_VERSION
  assert STATE_SCHEMA_VERSION == 2, 'Phase 8 bumps STATE_SCHEMA_VERSION to 2'
```

**Phase 14 adaptation:** The Phase-14 mirror of `test_migrate_walks_schema_version_to_current` MUST update the literal assertion: `assert STATE_SCHEMA_VERSION == 3, 'Phase 14 bumps STATE_SCHEMA_VERSION to 3'`. The existing line `assert STATE_SCHEMA_VERSION == 2, ...` (test_state_manager.py:1171) MUST be bumped to `== 3` in the same edit.

---

### `tests/test_sizing_engine.py::TestManualStopOverride` (NEW class — test, transform)

**Analog:** existing `TestTrailingStop` tests at `tests/test_sizing_engine.py:421-453`

**Verbatim test-shape pattern** (`tests/test_sizing_engine.py:421-439`):
```python
def test_long_trailing_stop_peak_update(self) -> None:
  '''EXIT-06 + D-15: LONG stop = peak_price - TRAIL_MULT_LONG * atr_entry.
  peak=7050, atr_entry=53 -> stop = 7050 - 3*53 = 6891.0.
  Pass atr=999 to prove the argument is ignored (D-15 anchor).'''
  pos = _make_position(direction='LONG', peak_price=7050.0, atr_entry=53.0)
  assert get_trailing_stop(pos, current_price=7100.0, atr=999.0) == 6891.0  # D-15

def test_long_trailing_stop_d15_anchor_explicit(self) -> None:
  '''D-15 explicit anchor proof: same position, two different atr arguments,
  same stop result. If the atr arg leaked into the math, the two calls would
  return different stops.'''
  pos = _make_position(direction='LONG', peak_price=7050.0, atr_entry=53.0)
  assert get_trailing_stop(pos, 7100.0, atr=53.0) == get_trailing_stop(pos, 7100.0, atr=200.0)

def test_long_trailing_stop_peak_none_falls_back_to_entry(self) -> None:
  '''Pitfall 3: peak_price=None -> use entry_price (no TypeError).
  entry=7000, atr_entry=53 -> stop = 7000 - 159 = 6841.0.'''
  pos = _make_position(direction='LONG', peak_price=None, entry_price=7000.0, atr_entry=53.0)
  assert get_trailing_stop(pos, current_price=7100.0, atr=53.0) == 6841.0
```

**Phase 14 adaptation:**
- Add `TestManualStopOverride` class with three tests (D-09 contract):
  1. `test_manual_stop_overrides_long_computed`: position with `manual_stop=7700.0` and `peak_price=8100.0, atr_entry=50.0` (computed would be 7950.0) — `get_trailing_stop` returns 7700.0 directly.
  2. `test_manual_stop_overrides_short_computed`: SHORT mirror.
  3. `test_manual_stop_none_falls_back_to_computed`: `manual_stop=None` — function returns the computed peak/trough trailing stop (existing v1.0 behavior preserved).
  4. `test_manual_stop_with_nan_atr_entry_still_returns_nan`: NaN-passthrough invariant (B-1 in `get_trailing_stop` docstring) — `manual_stop=7700.0` AND `atr_entry=float('nan')` → returns `float('nan')` (NaN guard runs FIRST, before the manual_stop branch). Locks the discipline that the manual_stop branch is positioned AFTER the NaN guard per the pattern assignment above.
  5. `test_manual_stop_via_get_with_missing_key_falls_back_to_computed`: pre-migration position dict (no `manual_stop` key at all) — `position.get('manual_stop')` returns None, falls through to computed. Locks the defensive `.get()` choice.
- Reuse the existing `_make_position` helper; extend it with a `manual_stop=None` keyword default.

---

### `tests/test_system_params.py::TestPositionTypedDict` (NEW or extended)

**No direct in-codebase analog for explicit Position-shape testing.** Phase 14's coverage is best provided by:
- Adding the field to `Position` (system_params.py edit) — TypedDict is structural, not enforced at runtime, so no "type-shape test" is meaningful.
- Round-trip-via-`load_state` test (already covered by `tests/test_state_manager.py::Test_v2_to_v3_Migration` per the assignment above) — this validates the actual semantic ("Position dict gains `manual_stop` after migration").

**Recommendation:** SKIP a separate `tests/test_system_params.py::TestPositionTypedDict` class. The migration round-trip test (RESEARCH §Pattern 11) is the binding contract; testing the TypedDict in isolation would add no enforcement above what Python provides.

If the planner insists on a system_params test, mirror the simple constants assertion style at `tests/test_state_manager.py:1170-1171`:
```python
def test_position_typeddict_has_manual_stop_field(self):
  '''Phase 14 D-09: Position TypedDict gains manual_stop: float | None.'''
  from system_params import Position
  assert 'manual_stop' in Position.__annotations__
  # Annotation should be `float | None` (UnionType in 3.11+)
  ann = Position.__annotations__['manual_stop']
  assert ann == (float | None) or repr(ann) == 'float | None'
```

---

### `tests/test_web_healthz.py::TestWebHexBoundary.FORBIDDEN_FOR_WEB` (MODIFIED — test, AST guard)

**Analog:** existing `FORBIDDEN_FOR_WEB` block at `tests/test_web_healthz.py:184-191` AND the Phase 13 D-07 regression test at line 212-214

**Verbatim existing block:**
```python
class TestWebHexBoundary:
  '''AST guard: web/ must NOT import pure-math hex modules.'''

  # Phase 13 D-07: dashboard is now an ALLOWED adapter import for
  # web/routes/dashboard.py (web layer calls dashboard.render_dashboard()
  # on stale-state regen). Removing 'dashboard' from this set is the
  # hex-boundary extension.
  FORBIDDEN_FOR_WEB = frozenset({
    'signal_engine', 'sizing_engine', 'system_params',
    'data_fetcher', 'notifier', 'main',
  })
```

**Verbatim Phase 13 promotion-regression-test pattern** (`tests/test_web_healthz.py:212-214`):
```python
def test_dashboard_is_not_forbidden_for_web_phase_13_D07(self):
  '''Regression: Phase 13 D-07 promotes dashboard to allowed import.'''
  assert 'dashboard' not in self.FORBIDDEN_FOR_WEB
```

**Phase 14 adaptation:**
- Remove `'sizing_engine'` from the `FORBIDDEN_FOR_WEB` frozenset. The new set:
  ```python
  # Phase 13 D-07: dashboard promoted (web/routes/dashboard.py imports it).
  # Phase 14 D-02 (this phase): sizing_engine promoted (web/routes/trades.py
  # imports check_pyramid for the pyramid-up gate per Pattern 1).
  FORBIDDEN_FOR_WEB = frozenset({
    'signal_engine', 'system_params',
    'data_fetcher', 'notifier', 'main',
  })
  ```
  **Rationale:** `system_params` MUST stay in FORBIDDEN_FOR_WEB at module-top (per existing C-2/hex rules) but is allowed via LOCAL import inside Pydantic validators (per RESEARCH §Pattern 1 line 343 — `from system_params import MAX_PYRAMID_LEVEL`). The AST walk in `test_web_modules_do_not_import_hex_core` (line 193-210) walks ALL nodes including local imports, which would create a violation. Two options for the planner:
    - **Option A (recommended):** Promote `system_params` for trades.py too (it's pure constants, no I/O). Update the comment block.
    - **Option B:** Inline the constant value (`MAX_PYRAMID_LEVEL = 2`) into `web/routes/trades.py` as a duplicate local constant. Less clean — duplicates source-of-truth.
  - **Recommend Option A.** The AST walker walks the whole tree including function bodies; `system_params` cannot be both forbidden and locally-imported. The planner picks; document the choice in PLAN.md.
- Add the Phase-14 mirror of the regression test:
  ```python
  def test_sizing_engine_is_not_forbidden_for_web_phase_14_D02(self):
    '''Regression: Phase 14 D-02 promotes sizing_engine to allowed import
    (web/routes/trades.py imports check_pyramid for the pyramid-up gate).'''
    assert 'sizing_engine' not in self.FORBIDDEN_FOR_WEB
  ```
- Extend `test_web_adapter_imports_are_local_not_module_top` (line 216-245) to add `Path('web/routes/trades.py')` to the `web_files` list AND add `'sizing_engine'` to the `forbidden_module_top` frozenset — module-top imports of `sizing_engine` from web/ would be a C-2 violation even though the module itself is permitted.

---

### `tests/conftest.py` (extended — fixture)

**Analog:** existing autouse fixture and `auth_headers` at `tests/conftest.py:35-65`

**Verbatim existing block:**
```python
@pytest.fixture(autouse=True)
def _set_web_auth_secret_for_web_tests(monkeypatch, request):
  '''Phase 13 D-16/D-17 REVIEWS HIGH fix.
  ...
  '''
  if 'test_web_' in str(request.node.fspath):
    monkeypatch.setenv('WEB_AUTH_SECRET', VALID_SECRET)


@pytest.fixture
def valid_secret() -> str:
  '''Phase 13: 32-char sentinel that passes D-17 minimum-length check.'''
  return VALID_SECRET


@pytest.fixture
def auth_headers(valid_secret) -> dict:
  '''Phase 13 AUTH-01: header dict for authorized TestClient requests.'''
  return {AUTH_HEADER_NAME: valid_secret}
```

**Phase 14 adaptation:** Add two new fixtures (preserving the existing block):
```python
@pytest.fixture
def htmx_headers(auth_headers) -> dict:
  '''Phase 14: auth headers + HX-Request signal so handlers can detect
  HTMX-originated requests (UI-SPEC §Decision 3 — banner OOB swap on success).'''
  return {**auth_headers, 'HX-Request': 'true'}


@pytest.fixture
def client_with_state_v3(monkeypatch):
  '''Phase 14 mirror of tests/test_web_state.py::client_with_state — yields
  a TestClient + (set_state, captured_saves) tuple. captured_saves accumulates
  every state dict that save_state was called with (no disk I/O).

  Default seed: a v3-schema state with one open SPI200 LONG position whose
  manual_stop is None (post-migration shape). Tests adjust via set_state.
  '''
  import sys
  sys.modules.pop('web.app', None)
  from web.app import create_app

  default_state = {
    'schema_version': 3,
    'account': 100_000.0,
    'last_run': '2026-04-25',
    'positions': {
      'SPI200': {
        'direction': 'LONG', 'entry_price': 7800.0, 'entry_date': '2026-04-20',
        'n_contracts': 2, 'pyramid_level': 0,
        'peak_price': 7850.0, 'trough_price': None, 'atr_entry': 50.0,
        'manual_stop': None,  # Phase 14 D-09
      },
      'AUDUSD': None,
    },
    'signals': {'SPI200': {'atr': 50.0, 'last_close': 7820.0}, 'AUDUSD': {}},
    'trade_log': [], 'equity_history': [], 'warnings': [],
    'initial_account': 100_000.0,
    'contracts': {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-mini'},
    '_resolved_contracts': {
      'SPI200': {'multiplier': 5.0, 'cost_aud': 6.0},
      'AUDUSD': {'multiplier': 10000.0, 'cost_aud': 5.0},
    },
  }
  state_box = {'value': default_state}
  captured_saves = []

  import state_manager
  monkeypatch.setattr(
    state_manager, 'load_state', lambda *_a, **_kw: state_box['value']
  )
  monkeypatch.setattr(
    state_manager, 'save_state',
    lambda state, *_a, **_kw: captured_saves.append(dict(state))
  )

  client = TestClient(create_app())

  def set_state(payload):
    state_box['value'] = payload

  return client, set_state, captured_saves
```

---

## Shared Patterns

### Local imports inside handlers (Phase 11 C-2 + Phase 14 hex extension)
**Source:** `web/routes/state.py:51`, `web/routes/dashboard.py:81-83`, `web/routes/healthz.py:31`
**Apply to:** Every handler in `web/routes/trades.py`
```python
@app.post('/trades/open')
def open_trade(req: OpenTradeRequest):
  # Phase 11 C-2 + Phase 14 D-02: local imports preserve hex boundary
  from state_manager import load_state, save_state
  from sizing_engine import check_pyramid
  ...
```

### `[Web]` log prefix (Phase 11 conventions / CLAUDE.md §Conventions)
**Source:** `web/app.py:96` (`logger.info('[Web] FastAPI app created ...')`), `web/routes/healthz.py:51-55` (`logger.warning('[Web] /healthz load_state failed: %s: %s', ...)`)
**Apply to:** Every log line in `web/routes/trades.py`
```python
logger.warning('[Web] /trades/open conflict: %s', msg)
logger.info('[Web] /trades/close completed for instrument=%s', instrument)
```

### Module docstring style (Phase 10/11/13 convention)
**Source:** `web/routes/state.py:1-37`, `web/routes/dashboard.py:1-44`, `web/routes/healthz.py:1-13`
**Apply to:** `web/routes/trades.py`, modified header of `state_manager.py` (add Phase 14 D-13 paragraph), `system_params.py` (add Phase 14 D-09 paragraph)
**Convention:** Triple-single-quote opening; first line is one-sentence summary; `Contract (CONTEXT.md <date>):` block with per-decision bullets; `Architecture (CLAUDE.md hex-lite + Phase X D-Y):` block; `Log prefix: [Tag].` line at end.

### TestClient + state-stub fixture
**Source:** `tests/test_web_state.py:38-62`
**Apply to:** `tests/test_web_trades.py` and `tests/conftest.py::client_with_state_v3`
**Pattern:** `sys.modules.pop('web.app', None)` → `from web.app import create_app` → `monkeypatch.setattr(state_manager, 'load_state', ...)` → `TestClient(create_app())`. Yield `(client, set_state)` tuple.

### Migration-step shape (state_manager pattern)
**Source:** `state_manager.py:86-101` (`_migrate_v1_to_v2`) and `state_manager.py:104-107` (MIGRATIONS dict)
**Apply to:** New `_migrate_v2_to_v3` and the MIGRATIONS dict registration
**Pattern:** Named function with docstring citing the phase + decision (e.g., "Phase 14 D-09 backfill: ..."); idempotent body using `s.get(..., default)` or `**s` spread; one-line addition to MIGRATIONS dict (`3: _migrate_v2_to_v3,`).

### Pydantic v2 validation (no in-codebase analog — first use)
**Source:** RESEARCH §Pattern 4 (lines 522-528) — references Patterns 1, 2, 3 verbatim
**Apply to:** All three POST handlers in `web/routes/trades.py`
**Discipline:** `BaseModel` + `Literal[...]` enums + `Field(gt=0, ge=1)` constraints + `@model_validator(mode='after')` for cross-field coherence (D-03) + `model_fields_set` for absent-vs-null PATCH semantics (D-12). Coupled with the **422→400 remap** (RESEARCH §Pattern 6) registered at `web/app.py::create_app()`.

### Atomic-write fcntl lock (no in-codebase analog — first use)
**Source:** RESEARCH §Pattern 9 (lines 686-736)
**Apply to:** `state_manager._atomic_write` (the function called by `save_state`)
**Discipline:** Open destination file with `os.open(str(path), os.O_RDWR | os.O_CREAT, 0o644)`; acquire `fcntl.flock(lock_fd, fcntl.LOCK_EX)` (blocks indefinitely per D-13); execute existing tempfile→fsync→replace→dir-fsync sequence; release with `fcntl.flock(lock_fd, fcntl.LOCK_UN)` and `os.close(lock_fd)` in `finally`. Cross-platform: POSIX-only (Linux droplet + macOS dev).

---

## No Analog Found

| File / Concern | Role | Data Flow | Reason | Replacement Reference |
|----------------|------|-----------|--------|------------------------|
| fcntl.flock advisory lock around `_atomic_write` | service (file-I/O) | file-I/O coordination | First use of cross-process file locking in codebase | **RESEARCH §Pattern 9** (lines 686-736) — verbatim |
| Pydantic v2 request bodies (BaseModel + Field + model_validator) | controller (request validation) | request-response | First use of Pydantic in codebase (Phase 13's GET endpoints had no request bodies) | **RESEARCH §Pattern 1, 2, 3, 4, 5** (lines 287-566) — verbatim |
| 422→400 RequestValidationError remap | config (FastAPI exception handler) | request-response | First custom exception handler in codebase | **RESEARCH §Pattern 6** (lines 575-608) — verbatim |
| HTMX 1.9.12 SRI vendor pin | config (CDN-pinned vendor lib) | n/a | First HTMX use; closest analog is the **Chart.js precedent at `dashboard.py:115-116`** | **RESEARCH §Pattern 7** (lines 619-633) + Chart.js precedent — verbatim |
| HTMX response shapes (HTMLResponse partials + OOB swap + JSON 4xx) | controller | request-response | First HTMX server-side use; no in-codebase analog | **RESEARCH §Pattern 8** (lines 635-669) — verbatim |
| AST guard against `state['warnings']` mutation | test (invariant) | static analysis | AST-walk pattern itself has analog (`tests/test_web_healthz.py:193-210`); this specific subscript-assignment + .append() detection is novel | **RESEARCH §Pattern 10** (lines 752-783) — verbatim AST walk |
| Multiprocess fcntl lock-contention test fixture | test (cross-process) | file-I/O | First multiprocess test in codebase | **RESEARCH §Pattern 9** (line 743) prescription — `multiprocessing.Process` holding `fcntl.LOCK_EX` for 0.5s; main test asserts `save_state` blocks `>= 0.4s` and `< 1.0s` |
| `system_params.Position` TypedDict shape test | test (type-shape) | n/a | No existing explicit Position-shape test; round-trip-via-load_state covers semantic | Recommendation: SKIP isolated TypedDict test; migration round-trip in `Test_v2_to_v3_Migration` is the binding contract |

---

## Metadata

**Analog search scope:**
- `web/routes/` (3 existing files: healthz.py, dashboard.py, state.py)
- `web/app.py` (single file)
- `state_manager.py` (full file — migration + atomic-write patterns)
- `sizing_engine.py` (lines 160-240 — get_trailing_stop function)
- `system_params.py` (lines 100-170 — color/Position/constants)
- `dashboard.py` (lines 100-200 + 683-820 — INLINE_CSS, Chart.js block, _render_positions_table)
- `tests/conftest.py` (full)
- `tests/test_web_state.py` (lines 1-130 — client_with_state fixture pattern)
- `tests/test_web_healthz.py` (lines 175-245 — TestWebHexBoundary AST guard)
- `tests/test_state_manager.py` (lines 220-340 + 1142-1216 — TestAtomicity + TestSaveStateExcludesUnderscoreKeys)
- `tests/test_sizing_engine.py` (lines 415-510 — TestTrailingStop)
- `tests/fixtures/dashboard/sample_state.json` (lines 246-258 — Position block analog)

**Files scanned:** 14 (read directly) + ~10 grep'd for marker locations
**Pattern extraction date:** 2026-04-25
