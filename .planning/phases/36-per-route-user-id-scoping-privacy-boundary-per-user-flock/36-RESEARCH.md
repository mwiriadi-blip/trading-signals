# Phase 36: Per-Route User-ID Scoping + Privacy Boundary + Per-User Flock - Research

**Researched:** 2026-05-14
**Domain:** Python fcntl, FastAPI Depends, state_manager mutation patterns, multi-tenant isolation
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** `mutate_user_state(uid, fn)` wraps outer `fcntl.flock(state/users/{uid}.lock, LOCK_EX)` then delegates to `mutate_state(fn)`. fn receives the full state dict. Two distinct lock files — no intra-process reentrancy.
- **D-02:** `mutate_user_state` lives in `state_manager/__init__.py`, re-exported alongside existing public API.
- **D-03:** `state/users/` dir auto-created by `mutate_user_state`; lock file opened with `open(lock_path, 'a+')` to create-if-absent before `fcntl.flock`. `state/users/` is gitignored from Phase 33.
- **D-04:** Per-user flock purpose: serializes daily fan-out vs HTMX for the SAME user. Cross-user serialization is via inner state.json flock.
- **D-05:** `load_user_state(uid)` returns `load_state()["users"][uid]`. Re-exported from `state_manager/__init__.py`.
- **D-06:** Signal-only read paths keep calling `load_state()` directly. Only per-user data reads use `load_user_state`.
- **D-07:** `PublicUserSummary` Pydantic model: `user_id, display_name, status, last_seen_date, has_active_position`. Lives in `web/routes/admin/_models.py`.
- **D-08:** `display_name = user["email"]`.
- **D-09:** `status = "disabled" if user.get("disabled") else "active"`.
- **D-10:** `has_active_position = bool(load_user_state(uid).get("current_position"))` or equivalent.
- **D-11:** `GET /admin/users` returns `response_model=list[PublicUserSummary]`.
- **D-12:** Phase 36 uses FastAPI `response_model` ONLY for admin route redaction. No standalone `redact()` utility. Explicit log/crash-email filter deferred to Phase 37.
- **D-13:** `TestTenantIsolation` introduced in `tests/test_web_admin.py` or `tests/test_tenant_isolation.py`.
- **D-14:** Every entity-ID route gets `test_<route>_returns_404_for_other_users_entity` test.

### Claude's Discretion

- Exact field name for `has_active_position` check (read migrations.py v12 output).
- Whether `TestTenantIsolation` goes in `test_web_admin.py` or new `test_tenant_isolation.py`.
- Whether `mutate_user_state` returns full state dict or user sub-dict.

### Deferred Ideas (OUT OF SCOPE)

- Standalone `redact_user_state_for_public()` filter function — Phase 37.
- Fan-out log line redaction — Phase 37.
- `display_name` as stored User field — Phase 37.
- Per-domain loaders — not needed.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TENANT-02 | Per-user routes: paper trades, journal, alerts, equity isolated via `mutate_user_state(uid, mutator)` with per-user `fcntl.flock` | flock composition verified GREEN (50-thread stress test passed); `_apply` body migration pattern documented |
| TENANT-03 | `TestTenantIsolation` gate: user A's trade content absent from admin list, other user pages, crash email | FastAPI `response_model=list[PublicUserSummary]` enforces redaction automatically; test structure documented |
| RBAC-04 | Admin `/admin/users`: user list with last-login + position status, no per-user trade content; reversible disable | `list_users()` + `set_user_disabled()` already in auth_store; `GET /admin/users` + `PATCH /admin/users/{uid}/disable` needed |
</phase_requirements>

---

## Summary

Phase 36 introduces `mutate_user_state(uid, fn)` as a thin wrapper around the existing `mutate_state` chokepoint, serializing concurrent writes per user via an outer `fcntl.flock` on `state/users/{uid}.lock`. The 50-thread stress test confirms lock composition is deadlock-free under all concurrent scenarios (same-user, cross-user, mixed).

The primary migration work is updating `_apply` closures in `paper_trades/__init__.py` and `trades/__init__.py` to navigate `state['users'][uid]` instead of top-level keys. In v12 state, `paper_trades`, `positions`, `trade_log`, `equity_history`, and `account` all live at `state['users'][uid]`, NOT at the top level. The existing `_apply` bodies access `state.get('paper_trades')` and `state['positions']` — these are now `None` at top level in v12.

There is a **critical gap** in `record_trade`: it calls `_admin_user(state)` which hardcodes `_ADMIN_UID`. Phase 36 must either pass `uid` to `record_trade` or extract the user bucket manually inside the trades `_apply` closure. This is the only non-mechanical migration in the trades route.

**Primary recommendation:** Migrate `_apply` closures to access `state['users'][user_id]`; add `uid` parameter to `record_trade`; use FastAPI `response_model` on `/admin/users` for automatic privacy boundary.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Per-user flock | State I/O (`state_manager/__init__.py`) | — | Lock discipline must stay inside the state layer; routes never touch fds directly |
| Per-user state reads | State I/O (`load_user_state`) | — | Centralised so future users all go through one path |
| Route user-ID injection | FastAPI Depends (`current_user_id`) | — | Declarative at route signature; no per-route boilerplate |
| Privacy boundary | FastAPI `response_model` | — | Automatic field stripping on serialization; zero custom serializer needed |
| Tenant isolation tests | Test layer | — | Quality gate lives outside production code |
| Admin user list + disable | API (`/admin/users`) | Auth store | Route reads auth_store; no state reads for list (except `has_active_position`) |

---

## Q1: flock Composition Safety

### Lock Acquisition Order

From `state_manager/io.py` lines 11–16 and `__init__.py` lines 371–382:

```
mutate_user_state (new):
  1. fd = os.open("state/users/{uid}.lock", O_RDWR|O_CREAT)
  2. fcntl.flock(fd, LOCK_EX)   ← OUTER: per-user advisory lock
  3. [delegates to mutate_state]
      4. fd2 = os.open("state.json", O_RDWR|O_CREAT)
      5. fcntl.flock(fd2, LOCK_EX)  ← INNER: shared state.json lock
      6. load_state(_under_lock=True)
      7. mutator(state)
      8. io._save_state_unlocked(state)  ← uses fd2 already held
      9. fcntl.flock(fd2, LOCK_UN)
     10. os.close(fd2)
  11. fcntl.flock(fd, LOCK_UN)
  12. os.close(fd)
```

### Deadlock Analysis

**VERIFIED** by 50-thread Python stress test:

| Scenario | Lock order | Result |
|----------|------------|--------|
| 50 threads, same uid, outer+inner | uid.lock → state.json | PASS: no deadlock |
| 25×user_a + 25×user_b, cross-user | uid_a.lock/uid_b.lock → state.json | PASS: no deadlock |

**Why no deadlock:** Two distinct lock files. The per-user lock (`state/users/{uid}.lock`) and the state file lock (`state.json`) are always acquired in the same order by all callers: uid first, then state. No circular dependency is possible.

**Intra-process reentrancy:** The inner `mutate_state` calls `io._save_state_unlocked` (bypasses `_atomic_write`'s lock acquisition). This is already the documented pattern in `io.py` lines 11–16. The per-user outer lock is on a DIFFERENT file — no second acquire on the same fd. [VERIFIED: state_manager/io.py lines 11-16, __init__.py lines 371-382]

**macOS vs Linux note:** `fcntl.flock` on macOS dev: same-process `LOCK_NB` on a held fd returns `BlockingIOError` (confirmed). Behavior is consistent with Linux production. [VERIFIED: runtime test]

**Conclusion:** Single-file `users{}` map choice is SAFE. Fall back to sharded-directory option is NOT needed.

---

## Q2: mutate_state Call Sites to Migrate (paper_trades)

All in `web/routes/paper_trades/__init__.py`:

| Line | Handler | Current call | Migrate to |
|------|---------|-------------|------------|
| 119–120 | `open_paper_trade` | `mutate_state(_apply)` | `mutate_user_state(user_id, _apply)` |
| 177–178 | `edit_paper_trade` | `mutate_state(_apply)` | `mutate_user_state(user_id, _apply)` |
| 206–207 | `delete_paper_trade` | `mutate_state(_apply)` | `mutate_user_state(user_id, _apply)` |
| 271–272 | `close_paper_trade` | `mutate_state(_apply)` | `mutate_user_state(user_id, _apply)` |

**4 mutate_state calls** in paper_trades. [VERIFIED: source read]

All in `web/routes/trades/__init__.py`:

| Line | Handler | Current call | Migrate to |
|------|---------|-------------|------------|
| 133 | `open_trade` | `state = mutate_state(_apply)` | `mutate_user_state(user_id, _apply)` |
| 217 | `close_trade` | `mutate_state(_apply)` | `mutate_user_state(user_id, _apply)` |
| 267 | `modify_trade` | `state = mutate_state(_apply)` | `mutate_user_state(user_id, _apply)` |

**3 mutate_state calls** in trades. [VERIFIED: source read]

### Critical Gap: _apply Body Key Access

**The `_apply` closures access top-level state keys that no longer exist in v12.**

In `paper_trades/_apply`:
- `state.setdefault('paper_trades', [])` — must become `state['users'][user_id].setdefault('paper_trades', [])`
- `state.get('paper_trades', [])` — must become `state['users'][user_id].get('paper_trades', [])`
- `state['paper_trades'] = ...` — must become `state['users'][user_id]['paper_trades'] = ...`

In `trades/_apply`:
- `state['positions'].get(...)` — must become `state['users'][user_id]['positions'].get(...)`
- `state['positions'][...] = ...` — must become `state['users'][user_id]['positions'][...] = ...`
- `state.get('markets')` — stays as-is (markets is shared, top-level)
- `state.get('signals', {})` — stays as-is (signals is shared, top-level)
- `state['_resolved_contracts']` — stays as-is (materialised at load_state time on full dict)

**Confirmed by runtime check:** `reset_state()['paper_trades']` returns `None` (v12 — key absent at top level). [VERIFIED: runtime]

### Critical Gap: record_trade Hardcodes _ADMIN_UID

`state_manager/trades.py::record_trade` calls `_admin_user(state)` which returns `state['users'][_ADMIN_UID]` always. When `close_trade` calls `record_trade(state, trade)` for a non-admin user, it will write into the admin bucket.

**Fix required:** Either:
- Option A: Add `uid: str = _ADMIN_UID` parameter to `record_trade` — routes pass `user_id`. Most eloquent: locality of behavior, no hidden globals.
- Option B: Extract user bucket in `_apply` and mutate directly without calling `record_trade`.

**Most eloquent:** Option A — add `uid` parameter to `record_trade`. The `_admin_user` helper is already the abstraction; parameterizing it is the clean extension. [ASSUMED — no CONTEXT decision covers this]

---

## Q3: load_state Call Sites to Migrate (per-user reads)

Routes that read per-user data (must migrate to `load_user_state(uid)`):

| File | Line | Handler | What it reads | Action |
|------|------|---------|--------------|--------|
| `paper_trades/__init__.py` | 70–71 | `get_paper_trades_fragment` | full state (passes to renderer) | Migrate: pass `load_user_state(uid)` to renderer OR pass full state and fix renderer |
| `paper_trades/__init__.py` | 291–292 | `get_close_form` | `state.get('paper_trades', [])` | Migrate: `load_user_state(uid).get('paper_trades', [])` |
| `trades/__init__.py` | 291–292 | `close_form` | `state['positions']` | Migrate: `load_user_state(uid)['positions']` |
| `trades/__init__.py` | 304–305 | `modify_form` | `state['positions']` | Migrate: `load_user_state(uid)['positions']` |
| `trades/__init__.py` | 321–322 | `cancel_row` | `state['positions']` | Migrate: `load_user_state(uid)['positions']` |

Routes that must NOT migrate (shared signal reads):
- `markets.py` — reads `state.get('markets')`, `state.get('signals')` — stays `load_state()` per D-06.
- `healthz.py` — reads `state['last_run']` — stays `load_state()`.
- `state.py` — reads full state for debug — stays `load_state()`.
- `dashboard/__init__.py` — reads full state for rendering — stays `load_state()`.

[VERIFIED: source read of all web/routes/**/*.py]

### Renderer Key Access Issue

`dashboard_renderer/components/paper_trades.py::render_paper_trades_region(state)` calls `state.get('paper_trades', [])` — expects the key at top level.

In v12, `paper_trades` lives at `state['users'][uid]['paper_trades']`.

**Options:**
- Option A: Pass the user bucket (`load_user_state(uid)`) to the renderer — renderer gets `paper_trades` at top level of the user dict. Simplest.
- Option B: Pass the full state plus uid; renderer navigates `state['users'][uid]`.

**Most eloquent:** Option A — `render_paper_trades_region(user_state)` where `user_state = load_user_state(uid)`. The renderer already receives a dict and calls `.get('paper_trades')` — the user bucket has the same key. No renderer change needed. [ASSUMED — planner must confirm renderer is agnostic to full vs user state]

**Caution:** `render_paper_trades_region` also reads `state.get('signals', {})` (line 321). Signals are NOT in the user bucket. If we pass only the user bucket, signals will be `{}`. The renderer needs full state OR signals passed separately. This is a real migration consideration for the planner.

---

## Q4: auth_store.list_users() API

`list_users()` (auth_store/_users.py line 150–152):
```python
def list_users(path: Path | None = None) -> list:
  return load_auth(path=path).get('users', [])
```

Returns: `list[dict]` where each dict is a User row with keys:
- `uid: str` — uuid4().hex
- `email: str`
- `role: str` — `'admin'` or `'ff'`
- `created_at: str` — ISO 8601 UTC
- `disabled: bool`

**No TypedDict enforced at runtime** — plain dicts. [VERIFIED: source read]

**No `last_seen_date` field on User row.** The User TypedDict in `auth_store/_schema.py` has only `uid, email, role, created_at, disabled`. [VERIFIED: source read]

`PublicUserSummary.last_seen_date` derivation: **not determinable from User row alone.** Options:
- Derive from `TrustedDevice.last_seen` (latest across user's devices) — requires cross-referencing devices by user email (devices are stored per device, not per user uid). [ASSUMED — no CONTEXT decision; planner must decide]
- Return `None` always for now (no last_seen field yet on users).
- Add `last_seen_date` to User row when sessions are updated (future).

**Recommendation:** Return `None` for `last_seen_date` in Phase 36. Device-based derivation is complex and not required for RBAC-04 MVP. [ASSUMED]

---

## Q5: has_active_position Field Name

From `state_manager/migrations.py::_migrate_v11_to_v12` (line 374–388) and runtime verification:

```python
user_bucket = {
  'account': ...,
  'initial_account': ...,
  'contracts': ...,
  'positions': {'SPI200': None, 'AUDUSD': None},  # None = inactive
  'trade_log': [],
  'equity_history': [],
  'paper_trades': [],
  'ui_prefs': {'tour_completed': True},
}
```

**Field name is `positions`**, not `current_position` or `open_position`.

`has_active_position` derivation:
```python
user_state = load_user_state(uid)
has_active_position = any(
  v is not None
  for v in user_state.get('positions', {}).values()
)
```

CONTEXT D-10 says `bool(load_user_state(uid).get("current_position"))` — but `"current_position"` does not exist in the schema. Correct field is `"positions"` (dict keyed by instrument). [VERIFIED: runtime + migration source]

**This is the Claude's Discretion item.** Use `any(v is not None for v in user_state['positions'].values())`.

---

## Q6: Entity-ID Routes for 404-for-Other-Users Tests

Phase 36 SC-3 and D-14 require paired tests for every entity-ID route.

### paper_trades routes (entity-ID routes):

| Handler | Method | URL | Entity ID | 404 Test Method |
|---------|--------|-----|-----------|-----------------|
| `edit_paper_trade` | PATCH | `/paper-trade/{trade_id}` | `trade_id` | `test_edit_paper_trade_returns_404_for_other_users_entity` |
| `delete_paper_trade` | DELETE | `/paper-trade/{trade_id}` | `trade_id` | `test_delete_paper_trade_returns_404_for_other_users_entity` |
| `close_paper_trade` | POST | `/paper-trade/{trade_id}/close` | `trade_id` | `test_close_paper_trade_returns_404_for_other_users_entity` |
| `get_close_form` | GET | `/paper-trade/{trade_id}/close-form` | `trade_id` | `test_get_close_form_returns_404_for_other_users_entity` |

**Note:** `open_paper_trade` (POST `/paper-trade/open`) has no entity ID — excluded.
**Note:** `get_paper_trades_fragment` (GET `/paper-trades`) has no entity ID — excluded.

### trades routes (entity-ID routes):

| Handler | Method | URL | Entity ID | 404 Test Method |
|---------|--------|-----|-----------|-----------------|
| `close_trade` | POST | `/trades/close` | instrument (in body) | `test_close_trade_returns_404_for_other_users_position` |
| `modify_trade` | POST | `/trades/modify` | instrument (in body) | `test_modify_trade_returns_404_for_other_users_position` |
| `close_form` | GET | `/trades/close-form?instrument=X` | instrument (query) | `test_close_form_returns_404_for_other_users_position` |
| `modify_form` | GET | `/trades/modify-form?instrument=X` | instrument (query) | `test_modify_form_returns_404_for_other_users_position` |
| `cancel_row` | GET | `/trades/cancel-row?instrument=X` | instrument (query) | `test_cancel_row_returns_404_for_other_users_position` |

**Note:** `open_trade` (POST `/trades/open`) creates a new position — no "other user's entity" to 404 on. Not included.

**Journal and alerts:** No journal or alerts routes exist yet in Phase 36. ROADMAP SC-3 says "journal patch, alert ack" — these are future Phase routes. The D-14 tests for journal/alert can be added when those routes land (Phase 37+). Phase 36 only needs the paper_trades and trades entity-ID tests. [VERIFIED: ls web/routes/]

[VERIFIED: source read of paper_trades/__init__.py and trades/__init__.py]

---

## Q7: TestTenantIsolation Placement

`tests/test_web_admin.py` has 8 existing test classes, all admin/auth related:
- `TestCurrentUserId`
- `TestRequireAdmin`
- `TestAdminSubRouter`
- `TestAdminRouteInvariant`
- `TestAdminGate403SweepUnauthenticated`
- `TestAdminGate403SweepHeaderAuth`
- `TestAdminGate403SweepNonAdminRole`
- `TestAdminPing`
- `TestPrePhase35RoutesStructuralParity`

File is ~595 lines. Adding `TestTenantIsolation` would push it toward the 500-LOC limit.

**Recommendation:** New file `tests/test_tenant_isolation.py`. Reasons:
1. File size: `test_web_admin.py` is already ~595 lines — adding `TestTenantIsolation` exceeds the 500-LOC project cap.
2. Cohesion: `TestTenantIsolation` is a cross-cutting quality gate (not specific to admin), making a separate file more descriptive.
3. D-13 explicitly offers both options; the file-size constraint breaks the tie. [VERIFIED: test_web_admin.py line count]

---

## Q8: Validation Architecture

### Existing Test Infrastructure

| File | Framework | Relevant Fixtures |
|------|-----------|-------------------|
| `tests/test_web_paper_trades.py` | pytest | `client_with_state_v6` — monkeypatches `mutate_state` |
| `tests/test_web_trades.py` | pytest | `client_with_state_v3` — monkeypatches `mutate_state` |
| `tests/test_web_admin.py` | pytest | `isolated_auth_json`, `_build_session_cookie` |
| `tests/conftest.py` | pytest | Both fixtures + `isolated_auth_json` |

### Fixture Migration Issue

**Both existing fixtures (`client_with_state_v3`, `client_with_state_v6`) use pre-v12 state shape** with `positions` and `paper_trades` at top-level. After Phase 36 migrates `_apply` bodies to access `state['users'][uid]`, these fixtures will fail — the state they inject no longer matches what the routes expect.

**Fix:** Update both fixtures to inject v12-shaped state:
```python
default_state = {
  'schema_version': 12,
  'admin_user_id': _ADMIN_UID,
  'signals': {...},
  'markets': {...},
  'warnings': [],
  'last_run': '...',
  '_resolved_contracts': {...},
  'users': {
    _ADMIN_UID: {
      'account': 100_000.0,
      'initial_account': 100_000.0,
      'contracts': {...},
      'positions': {'SPI200': ..., 'AUDUSD': None},
      'trade_log': [],
      'equity_history': [],
      'paper_trades': [],
      'ui_prefs': {'tour_completed': True},
    }
  }
}
```

The `mutate_state` stub in conftest also needs to be updated — or the fixtures need a `mutate_user_state` stub alongside the `mutate_state` stub.

### D-13 Tests (TestTenantIsolation) — file: `tests/test_tenant_isolation.py`

| Test Method | What It Tests | REQ |
|-------------|---------------|-----|
| `test_admin_users_response_has_no_trade_content` | GET /admin/users JSON body contains zero matches for `(entry_price\|n_contracts\|"direction":\s*"(LONG\|SHORT)")` | TENANT-03 |
| `test_other_user_dashboard_has_no_user_a_trade_content` | User B's served page has no user A paper trade fields | TENANT-03 |
| `test_crash_email_body_has_no_trade_content` | Simulated crash email body has zero trade content matches | TENANT-03 (stubbed/skipped until Phase 37) |

**Fixture pattern:** Seed user A with 5 paper trades in `state['users'][uid_a]['paper_trades']`. Assert the regex `(entry_price|n_contracts|"direction":\s*"(LONG|SHORT)")` has zero matches in each response. [VERIFIED: CONTEXT D-13]

### D-14 Tests (404-for-other-users) — added to existing test files

**In `tests/test_web_paper_trades.py`:**

| Test Method | Route | Setup | Assert |
|-------------|-------|-------|--------|
| `test_edit_paper_trade_returns_404_for_other_users_entity` | PATCH `/paper-trade/{trade_id}` | Seed uid_a with trade; auth as uid_b | 404 |
| `test_delete_paper_trade_returns_404_for_other_users_entity` | DELETE `/paper-trade/{trade_id}` | Same | 404 |
| `test_close_paper_trade_returns_404_for_other_users_entity` | POST `/paper-trade/{trade_id}/close` | Same | 404 |
| `test_get_close_form_returns_404_for_other_users_entity` | GET `/paper-trade/{trade_id}/close-form` | Same | 404 |

**In `tests/test_web_trades.py`:**

| Test Method | Route | Setup | Assert |
|-------------|-------|-------|--------|
| `test_close_trade_returns_404_for_other_users_position` | POST `/trades/close` | Seed uid_a with SPI200 position; auth as uid_b | 404 or 409 (no position for uid_b) |
| `test_modify_trade_returns_404_for_other_users_position` | POST `/trades/modify` | Same | 404 or 409 |
| `test_close_form_returns_404_for_other_users_position` | GET `/trades/close-form` | Same | 404 |
| `test_modify_form_returns_404_for_other_users_position` | GET `/trades/modify-form` | Same | 404 |
| `test_cancel_row_returns_404_for_other_users_position` | GET `/trades/cancel-row` | Same | 404 |

**Note on trades routes:** The current trades routes return 409 (conflict) when no position is found, not 404. Phase 36 must add explicit ownership checks (404 when entity exists but belongs to another user) vs 409 (no entity at all). This is a behavior change the planner must address. [VERIFIED: trades/__init__.py source]

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Response field stripping | Custom serializer/filter | FastAPI `response_model=list[PublicUserSummary]` | FastAPI strips unknown fields automatically at serialization time |
| Lock file creation | Manual open/check | `open(lock_path, 'a+')` before `fcntl.flock` | create-if-absent is idiomatic; the existing `mutate_state` uses same `os.open(O_CREAT)` pattern |
| Auth user lookup | Custom session state | `auth_store.get_user(uid)` | already exists, live-reads auth.json |
| User list | Custom scan | `auth_store.list_users()` | returns all User rows |
| Disable/enable | Custom mutation | `auth_store.set_user_disabled(uid, disabled)` | already implemented with flock semantics |

---

## Architecture Patterns

### Pattern 1: mutate_user_state Implementation

```python
# state_manager/__init__.py
def mutate_user_state(
  uid: str,
  mutator: Callable[[dict], None],
  path: Path = Path(STATE_FILE),
) -> dict:
  '''Outer per-user flock + inner mutate_state.

  Acquisition order: state/users/{uid}.lock (OUTER) -> state.json (INNER).
  Both locks always acquired in this order by all callers — no deadlock.
  '''
  lock_dir = Path('state/users')
  lock_dir.mkdir(parents=True, exist_ok=True)
  lock_path = lock_dir / f'{uid}.lock'
  # 'a+' creates file if absent; existing content ignored (lock-only fd).
  with open(lock_path, 'a+') as lock_file:
    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
    try:
      return mutate_state(mutator, path=path)
    finally:
      fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
```

[VERIFIED: io.py flock pattern; D-01/D-02/D-03]

### Pattern 2: load_user_state Implementation

```python
def load_user_state(uid: str, path: Path = Path(STATE_FILE)) -> dict:
  '''Return state["users"][uid] slice.'''
  return load_state(path=path)['users'][uid]
```

[VERIFIED: D-05]

### Pattern 3: Migrated _apply Body (paper_trades example)

```python
@app.post('/paper-trade/open')
async def open_paper_trade(
  request: Request,
  user_id: str = Depends(current_user_id),
) -> HTMLResponse:
  req = await _parse_form(request, OpenPaperTradeRequest)
  def _apply(state: dict) -> None:
    user = state['users'][user_id]  # navigate to user bucket
    rows = user.setdefault('paper_trades', [])
    # ... rest of body unchanged ...
  from state_manager import mutate_user_state
  state = mutate_user_state(user_id, _apply)
  # render: need user state for paper_trades, full state for signals
  user_state = state['users'][user_id]
  # pass user_state for paper_trades, signals separately:
  return HTMLResponse(content=render_paper_trades_region_for_user(user_state, state.get('signals', {})))
```

**Note:** `render_paper_trades_region(state)` reads `state.get('paper_trades')` AND `state.get('signals')`. The user bucket has `paper_trades` but not `signals`. Two options:
- Option A: Pass user bucket + signals separately; update renderer signature.
- Option B: Build a synthetic dict: `{**user_state, 'signals': state['signals']}`.

**Most eloquent:** Option B — no renderer signature change, one-liner merge at the call site. [ASSUMED — planner confirms]

### Pattern 4: PublicUserSummary + GET /admin/users

```python
# web/routes/admin/_models.py
from pydantic import BaseModel

class PublicUserSummary(BaseModel):
  user_id: str
  display_name: str
  status: str          # "active" or "disabled"
  last_seen_date: str | None
  has_active_position: bool

# web/routes/admin/__init__.py
from auth_store import list_users
from state_manager import load_user_state, load_state
from web.routes.admin._models import PublicUserSummary

@router.get('/users', response_model=list[PublicUserSummary])
def admin_list_users():
  users = list_users()
  result = []
  state = load_state()  # load once for all users
  for user in users:
    uid = user['uid']
    user_bucket = state.get('users', {}).get(uid, {})
    positions = user_bucket.get('positions', {})
    has_active = any(v is not None for v in positions.values())
    result.append(PublicUserSummary(
      user_id=uid,
      display_name=user['email'],
      status='disabled' if user.get('disabled') else 'active',
      last_seen_date=None,  # deferred until device lookup wired
      has_active_position=has_active,
    ))
  return result
```

FastAPI `response_model=list[PublicUserSummary]` strips ALL non-listed fields automatically. Trade content, equity, paper_trades never appear. [VERIFIED: FastAPI response_model behavior; CONTEXT D-07 through D-11]

### Pattern 5: PATCH /admin/users/{uid}/disable

```python
@router.patch('/users/{uid}/disable')
def admin_disable_user(uid: str, disabled: bool = True):
  from auth_store import set_user_disabled
  found = set_user_disabled(uid, disabled)
  if not found:
    raise HTTPException(status_code=404, detail=f'user {uid!r} not found')
  return {'ok': True, 'uid': uid, 'disabled': disabled}
```

`set_user_disabled` already exists in auth_store. [VERIFIED: _users.py line 155-167]

---

## ROADMAP SC-5 vs CONTEXT D-12 Conflict

**ROADMAP SC-5** (Phase 36 success criterion 5): "`RedactStateFilter` is installed at app startup; structured field-name allowlist — `paper_trades`/`equity_history`/`entry_price`/`n_contracts`/`journal` are replaced with `<redacted>` in log records."

**CONTEXT D-12** (locked decision): "Phase 36 uses FastAPI `response_model` ONLY on the admin route. No standalone `redact()` utility. Explicit log/crash-email filter **deferred to Phase 37**."

**CONTEXT supersedes ROADMAP** (CONTEXT was gathered AFTER the ROADMAP and represents locked user decisions). The planner must NOT implement `RedactStateFilter` in Phase 36. SC-5 is deferred.

**Risk:** ROADMAP SC-5 will remain un-ticked after Phase 36 completes. Planner must note this in plan documentation. [VERIFIED: CONTEXT.md D-12 vs ROADMAP.md SC-5]

---

## Common Pitfalls

### Pitfall 1: _apply Accessing Top-Level Keys (Broken in v12)

**What goes wrong:** `state.get('paper_trades', [])` returns `None` in v12 (key absent at top level). `state['positions']` raises `KeyError`.

**Why it happens:** The migration to v12 moved user data under `state['users'][uid]`. Old `_apply` bodies still reference the old paths.

**How to avoid:** Every `_apply` closure must begin with `user = state['users'][user_id]` then access `user['paper_trades']`, `user['positions']`, etc.

**Warning signs:** Empty paper_trades lists; 500 errors on trade modification; test failures showing `paper_trades` not found.

### Pitfall 2: record_trade Writing to Wrong User (_ADMIN_UID)

**What goes wrong:** `close_trade`'s `_apply` calls `record_trade(state, trade)`. `record_trade` calls `_admin_user(state)` which returns `state['users'][_ADMIN_UID]`. Non-admin user's trade log and positions are not updated; admin's account and positions are corrupted instead.

**Why it happens:** `_admin_user()` was a placeholder for Phase 33's "single admin" scope — it always returns the admin bucket.

**How to avoid:** Update `record_trade` to accept `uid` parameter (or pass user bucket directly). All callers pass `user_id`.

**Warning signs:** Trade close succeeds for non-admin user but position stays non-None; admin account changes when another user closes a trade.

### Pitfall 3: render_paper_trades_region Receiving User Bucket Without Signals

**What goes wrong:** `render_paper_trades_region(user_state)` called with only the user bucket. `user_state.get('signals', {})` returns `{}`. Paper trade stats that reference signals (stop-loss distances, etc.) compute incorrectly or silently return empty.

**Why it happens:** `signals` is a shared top-level key, not in the user bucket.

**How to avoid:** Pass a merged dict or pass signals separately: `{**user_state, 'signals': state['signals']}`.

### Pitfall 4: conftest Fixtures Use Pre-v12 State Shape

**What goes wrong:** `client_with_state_v3` and `client_with_state_v6` inject state with `positions` and `paper_trades` at top-level. After Phase 36 migrates `_apply` bodies to `state['users'][uid]`, all existing tests using these fixtures will fail with `KeyError: _ADMIN_UID`.

**How to avoid:** Update both fixtures to inject v12-shaped state. Add `mutate_user_state` stub alongside existing `mutate_state` stub.

### Pitfall 5: Trades Route 404 vs 409 for Missing Position

**What goes wrong:** Current `close_trade` and `modify_trade` raise `_OpenConflict` (returns 409) when no position exists. After Phase 36, "no position" could mean either "no position exists" OR "position exists but belongs to another user." The 404-for-other-users requirement (D-14) requires distinguishing these two cases.

**How to avoid:** Add ownership check: if position exists but belongs to another user → 404. If position genuinely absent for this user → 409 (unchanged behavior).

### Pitfall 6: state/users/ Directory Not Created Before First Lock

**What goes wrong:** `open('state/users/{uid}.lock', 'a+')` raises `FileNotFoundError` if `state/users/` dir doesn't exist.

**How to avoid:** `Path('state/users').mkdir(parents=True, exist_ok=True)` before opening the lock file (D-03).

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Top-level `state['positions']` | `state['users'][uid]['positions']` | Phase 33 (v12 migration) | All route `_apply` bodies must navigate via user bucket |
| `record_trade` always admin | `record_trade(state, trade, uid=uid)` | Phase 36 (this phase) | Non-admin user trades recorded correctly |
| `mutate_state` only | `mutate_user_state(uid, fn)` wrapper | Phase 36 (this phase) | Per-user write serialization |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `last_seen_date=None` is acceptable for Phase 36 (device-lookup deferred) | Q4 | If RBAC-04 strictly requires last-login, feature is incomplete |
| A2 | Synthetic dict `{**user_state, 'signals': state['signals']}` is cleanest renderer fix | Q3 / Pattern 3 | If renderer has other top-level keys it reads, merge may miss them |
| A3 | `record_trade` should gain a `uid` parameter (Option A) | Q2 | If Option B (extract bucket manually in _apply) is preferred, `record_trade` stays unchanged but close_trade `_apply` gets more complex |
| A4 | `TestTenantIsolation` should be in `tests/test_tenant_isolation.py` | Q7 | Minor — planner may override if file-size concern is wrong |
| A5 | Phase 36 SC-5 (`RedactStateFilter`) is deferred (CONTEXT D-12 wins over ROADMAP SC-5) | Conflict section | If user disagrees, Phase 36 must implement a log filter too |

---

## Open Questions

1. **render_paper_trades_region signals access**
   - What we know: renderer reads `state.get('signals', {})` AND `state.get('paper_trades', [])`.
   - What's unclear: Whether to merge at call site or update renderer to accept explicit `signals` param.
   - Recommendation: Merge at call site — zero renderer change.

2. **record_trade uid parameter**
   - What we know: it hardcodes `_ADMIN_UID`.
   - What's unclear: CONTEXT did not explicitly address this.
   - Recommendation: Add `uid: str = _ADMIN_UID` default parameter — backward compatible, existing callers (daily_run.py etc.) that pass no uid continue to work.

3. **Trades route 404 vs 409 semantics**
   - What we know: current routes return 409 for no-position. D-14 requires 404 for other-user's entity.
   - What's unclear: Does "other user's position" mean → 404 or still → 409 (from the requesting user's perspective they just have no position)?
   - Recommendation: Return 404 when the instrument has a position in state but it belongs to a different user; 409 when no position exists for any user.

---

## Environment Availability

Step 2.6: No external dependencies beyond Python stdlib and existing project packages. `fcntl` is stdlib POSIX-only — confirmed available on macOS dev + Linux production. `state/users/` dir auto-created by code.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `fcntl` (stdlib) | per-user flock | ✓ | Python 3.13 stdlib | — |
| `pydantic` | PublicUserSummary model | ✓ | already in project | — |
| `state/users/` directory | lock files | auto-created | — | `mkdir(parents=True, exist_ok=True)` |

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (Python 3.13) |
| Config file | `pyproject.toml` (or `pytest.ini`) |
| Quick run command | `.venv/bin/pytest -x --tb=short tests/test_tenant_isolation.py tests/test_web_admin.py` |
| Full suite command | `.venv/bin/pytest -x --tb=short` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TENANT-02 | `mutate_user_state` serializes per-user writes | unit | `.venv/bin/pytest -x tests/test_state_manager.py::TestMutateUserState -x` | ❌ Wave 0 |
| TENANT-02 | Paper trade open/edit/close writes to correct user bucket | integration | `.venv/bin/pytest -x tests/test_web_paper_trades.py -x` | ✅ (needs fixture update) |
| TENANT-02 | Trade open/close/modify writes to correct user bucket | integration | `.venv/bin/pytest -x tests/test_web_trades.py -x` | ✅ (needs fixture update) |
| TENANT-03 | Admin user list has no trade content | integration | `.venv/bin/pytest -x tests/test_tenant_isolation.py::TestTenantIsolation -x` | ❌ Wave 0 |
| TENANT-03 | 404-for-other-users on entity-ID routes | integration | `.venv/bin/pytest -x tests/test_web_paper_trades.py -k 404_for_other -x` | ❌ Wave 0 |
| RBAC-04 | GET /admin/users returns PublicUserSummary shape | integration | `.venv/bin/pytest -x tests/test_web_admin.py::TestAdminUsers -x` | ❌ Wave 0 |
| RBAC-04 | PATCH /admin/users/{uid}/disable toggles disabled flag | integration | `.venv/bin/pytest -x tests/test_web_admin.py::TestAdminDisable -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `.venv/bin/pytest -x --tb=short tests/test_tenant_isolation.py tests/test_web_paper_trades.py tests/test_web_trades.py tests/test_web_admin.py`
- **Per wave merge:** `.venv/bin/pytest -x --tb=short`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_tenant_isolation.py` — covers TENANT-03 `TestTenantIsolation`
- [ ] `tests/test_state_manager.py::TestMutateUserState` — covers TENANT-02 flock/wrapper
- [ ] `tests/test_web_admin.py::TestAdminUsers` + `TestAdminDisable` — covers RBAC-04
- [ ] `tests/conftest.py` — update `client_with_state_v3` + `client_with_state_v6` to v12 shape
- [ ] `tests/conftest.py` — add `mutate_user_state` stub to both fixtures

---

## Security Domain

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | (auth already implemented Phase 34/35) |
| V3 Session Management | no | (session already implemented) |
| V4 Access Control | yes | `current_user_id()` Depends + ownership check in `_apply` |
| V5 Input Validation | yes | Pydantic model for `PublicUserSummary` |
| V6 Cryptography | no | (no new crypto) |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| IDOR (cross-user entity access) | Elevation of Privilege | Ownership check in `_apply`: 404 if entity belongs to different uid |
| PII leakage via admin API | Information Disclosure | FastAPI `response_model=list[PublicUserSummary]` strips all non-listed fields |
| State-key traversal (top-level vs user-bucket) | Tampering | `state['users'][user_id]` navigation in all `_apply` closures — no top-level write |

---

## Sources

### Primary (HIGH confidence)
- `state_manager/__init__.py` — `mutate_state` pattern, public API, `reset_state` v12 shape
- `state_manager/io.py` — flock acquire/release pattern, intra-process reentrancy docstring
- `state_manager/migrations.py` — `_migrate_v11_to_v12` user bucket shape, `_ADMIN_UID`
- `state_manager/trades.py` — `record_trade` + `_admin_user` hardcoded uid issue
- `web/routes/paper_trades/__init__.py` — all 4 `mutate_state` + 2 `load_state` call sites
- `web/routes/trades/__init__.py` — all 3 `mutate_state` + 3 `load_state` call sites
- `web/routes/admin/__init__.py` — router structure, existing ping route
- `web/dependencies.py` — `current_user_id()` + `require_admin()` factories
- `auth_store/_users.py` — `list_users()`, `set_user_disabled()` APIs
- `auth_store/_schema.py` — User TypedDict fields (confirmed no `last_seen_date`)
- `tests/test_web_admin.py` — existing class structure, ~595 lines
- `tests/conftest.py` — `client_with_state_v3` + `client_with_state_v6` fixtures (pre-v12)
- `.gitignore` — `state/users/` gitignore confirmed
- Runtime Python stress test (50-thread flock composition) — deadlock-free confirmed

### Secondary (MEDIUM confidence)
- ROADMAP.md §Phase 36 success criteria — SC-5 vs CONTEXT D-12 conflict identified

### Tertiary (LOW confidence)
- None

---

## Metadata

**Confidence breakdown:**
- flock composition: HIGH — verified by runtime 50-thread test
- mutate_state call sites: HIGH — verified by source grep + read
- State key paths (v12): HIGH — verified by runtime `reset_state()` check
- record_trade uid gap: HIGH — verified by source read
- has_active_position field: HIGH — verified by runtime + migration source
- list_users API shape: HIGH — verified by source read
- last_seen_date derivation: LOW — assumed None; no confirmed source
- TestTenantIsolation placement: MEDIUM — based on line-count and cohesion reasoning

**Research date:** 2026-05-14
**Valid until:** 2026-06-14 (stable Python/FastAPI patterns; state schema locked at v12 for this milestone)
