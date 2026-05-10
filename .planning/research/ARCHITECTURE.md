# Architecture Research — v1.3 Multi-Tenant Friends & Family

**Domain:** Multi-tenant retrofit of a single-operator FastAPI + file-state trading signal app
**Researched:** 2026-05-10
**Confidence:** HIGH on integration shape (every existing seam was read at the file level); MEDIUM on the migration semantics for `state.json` v9→v10 (locked at the level of "what fields move where"; exact key names belong in the phase plan)

---

## Standard Architecture (v1.3 target)

### System Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                               ENTRY POINTS                                │
│  ┌──────────────┐  ┌──────────────────────────┐  ┌────────────────────┐  │
│  │  main.py     │  │  uvicorn web.app:app     │  │  systemd unit      │  │
│  │  (CLI shim)  │  │  (FastAPI server)        │  │  (08:00 Sydney)    │  │
│  └──────┬───────┘  └────────────┬─────────────┘  └─────────┬──────────┘  │
├─────────┼──────────────────────┼──────────────────────────┼──────────────┤
│         ▼                      ▼                          ▼              │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │             ORCHESTRATION LAYER (sole wall-clock readers)          │  │
│  │  daily_loop / daily_run / scheduler_driver / crash_boundary        │  │
│  │  + NEW v1.3: per_user_fanout (orchestrates N user emails / run)    │  │
│  └────────────────────────────────────────────────────────────────────┘  │
├──────────────────────────────────────────────────────────────────────────┤
│   PURE-MATH HEX (AST-guarded — must NOT change for v1.3)                 │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │ signal_engine, sizing_engine, system_params,                     │    │
│  │ pnl_engine, alert_engine, backtest/{simulator,metrics,render}    │    │
│  │ Inputs: floats, dicts, DataFrames. NO state, NO net, NO clock.   │    │
│  └──────────────────────────────────────────────────────────────────┘    │
├──────────────────────────────────────────────────────────────────────────┤
│   I/O ADAPTERS (peers — no cross-imports between them)                   │
│  ┌─────────────┐ ┌──────────────┐ ┌────────────┐ ┌───────────────────┐   │
│  │state_manager│ │auth_store    │ │data_fetcher│ │notifier/          │   │
│  │+ NEW user_  │ │+ NEW users[]│ │(yfinance)  │ │ (Resend HTTPS)    │   │
│  │  scoping    │ │+ NEW invites│ │+ NEW news  │ │                   │   │
│  └─────────────┘ └──────────────┘ └────────────┘ └───────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────────┐     │
│  │ web/ (FastAPI app, routes/, middleware/, services/)             │     │
│  │  + NEW current_user dependency, RBAC dependencies               │     │
│  │  + NEW admin/* routes (invite, user list, revoke)               │     │
│  │  + NEW /tour, /news per-market panels                           │     │
│  └─────────────────────────────────────────────────────────────────┘     │
│  ┌─────────────────────────────────────────────────────────────────┐     │
│  │ dashboard / dashboard_legacy/ (HTML render)                      │     │
│  │  + NEW user-scoped tables; SHARED signal panels                  │     │
│  │  + NEW news panel + tooltip overlay + first-run tour modal       │     │
│  └─────────────────────────────────────────────────────────────────┘     │
├──────────────────────────────────────────────────────────────────────────┤
│   PERSISTENCE                                                             │
│  ┌──────────────────┐ ┌──────────────────────┐ ┌─────────────────────┐   │
│  │ state.json (v10) │ │ auth.json + invites  │ │ news cache (in mem) │   │
│  │ admin namespace  │ │ users[], pending[]   │ │ per-market 1h TTL   │   │
│  │ + users{id:...}  │ │ trusted_devices/user │ │                     │   │
│  └──────────────────┘ └──────────────────────┘ └─────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility (v1.3 delta in **bold**) | Notes |
|-----------|----------------------------------------|-------|
| `state_manager.py` (1293 LOC) | load/save/migrate `state.json`; atomic write via `mutate_state(mutator)` under `fcntl.LOCK_EX`; **new helpers: `mutate_user_state(user_id, mutator)`, `load_user_view(user_id)`, `iter_user_ids()`** | New helpers wrap existing `mutate_state` — single chokepoint preserved |
| `auth_store.py` (520 LOC) | Atomic JSON for `auth.json`: TOTP secret, trusted devices, magic links. **Extended to hold `users[]` + `pending_invites[]`** | Same atomic-write contract; keeps `users` co-located with `trusted_devices` because they share lifecycle (user delete → revoke devices) |
| `web/middleware/auth.py` (349 LOC) | Cookie+TOTP+trusted-device+header auth. **Now resolves `request.state.user_id`** from validated cookie payload; exempt + public paths unchanged | The cookie payload moves from "no payload" to `{"uid": "<user_id>"}` — backward-compat shim accepts cookies without `uid` and treats them as admin during migration grace |
| `web/dependencies.py` (NEW, ~80 LOC) | FastAPI `Depends(current_user)` and `Depends(require_admin)` factories; reads `request.state.user_id` set by middleware | Single source of truth for "who is the caller"; routes import these and never touch the cookie directly |
| `web/routes/admin/*` (NEW package) | `/admin/users` (list), `/admin/invite` (POST issue), `/admin/users/{id}` (DELETE revoke) | Gated by `Depends(require_admin)` — never imported into other route modules |
| `web/routes/markets.py`, `dashboard.py`, `paper_trades.py`, `trades.py` | Existing surfaces. **Each gains an injected `user_id` arg via dependency**; SHARED signal-display routes read from admin namespace; per-user routes (paper trades, trades, equity, alerts, market preferences) scope by `user_id` | LOC pressure: trades.py is already 746, paper_trades 493, totp 614, login 608, dashboard 644 — all already exceed the 500-LOC D-09 cap, so v1.3 forces splits (see §File-Size Hygiene below) |
| `daily_loop.py` / `daily_run.py` | 9-step orchestration. **Step 9.6 (alerts) becomes a fan-out loop**: `for user_id in iter_user_ids(): evaluate_user_alerts(state, user_id); send_user_email(report, user_id)`. Signal compute (steps 3.a–3.o) runs ONCE per market, unchanged | Determinism preserved — every user gets the same signals computed from the same yfinance pull |
| `notifier/dispatch.py` (414 LOC) | Resend HTTPS POST. **`send_signal_email(report, recipient_email, user_view)`** — `user_view` carries that user's positions/alerts/equity; signal block stays shared | Fan-out lives in `daily_loop`, not here — `notifier` stays a transport |
| `news_fetcher.py` (NEW, ~120 LOC) | I/O hex peer of `data_fetcher.py`: `fetch_news(yfinance_symbol) -> list[NewsItem]`; in-process LRU cache with 1h TTL keyed by symbol | Lives outside the AST hex (it's I/O, like `data_fetcher`); imports `yfinance` only |
| `news_filter.py` (NEW pure module, ~60 LOC) | `is_critical(news_item, market) -> bool` — keyword + yfinance importance hint check. Pure, deterministic, AST-hex-eligible | Added to `_HEX_PATHS_STDLIB_ONLY` test list so the boundary stays enforced |
| `dashboard_legacy/tour_panel.py` (NEW, ~80 LOC) | First-run tour modal renderer; reads `user_view['tour_completed']` to short-circuit render | Sibling of existing `account_section.py` etc; no new packages |
| `web/routes/tour.py` (NEW, ~40 LOC) | `POST /tour/complete` — flips `tour_completed=True` for current user via `mutate_user_state` | Smallest possible new route module |

---

## Recommended Project Structure (v1.3 deltas only)

```
trading-signals/
├── auth_store.py                  # MODIFIED: + users[], pending_invites[], invite helpers
├── state_manager.py               # MODIFIED: + mutate_user_state, load_user_view, _migrate_v9_to_v10
├── news_fetcher.py                # NEW: I/O hex (yfinance.Ticker.news + 1h cache)
├── news_filter.py                 # NEW: pure-math hex (critical-event keyword check)
├── per_user_fanout.py             # NEW: orchestrator seam — fan-out alerts + email per user
├── web/
│   ├── app.py                     # MODIFIED: register admin + tour + news routes
│   ├── dependencies.py            # NEW: current_user, require_admin Depends factories
│   ├── middleware/
│   │   └── auth.py                # MODIFIED: cookie payload now {"uid": ...}; sets request.state.user_id
│   ├── routes/
│   │   ├── admin/
│   │   │   ├── __init__.py        # NEW
│   │   │   ├── users.py           # NEW: list / revoke
│   │   │   └── invites.py         # NEW: issue / consume
│   │   ├── tour.py                # NEW: POST /tour/complete
│   │   ├── news.py                # NEW: HTMX panel GET /markets/{m}/news
│   │   ├── trades.py              # SPLIT: trades_open.py + trades_close.py + trades_modify.py
│   │   ├── paper_trades.py        # SPLIT: paper_open.py + paper_modify.py + paper_close.py
│   │   ├── totp.py                # SPLIT: totp_enroll.py + totp_verify.py
│   │   └── login.py               # SPLIT: login_form.py + login_post.py
│   └── services/
│       └── invite_service.py      # NEW: invite token mint/consume — uses URLSafeTimedSerializer
└── dashboard_legacy/
    ├── tour_panel.py              # NEW
    └── tooltip_data.py            # NEW: tooltip content as Python dict (NOT JSON file — see §Guide UI)
```

### Structure Rationale

- **`admin/` is a route subpackage**, not a flag. Gives a single import locus that can be `Depends(require_admin)`-decorated at the router level — no per-route boilerplate.
- **`per_user_fanout.py` is a top-level seam, not buried in `daily_run.py`.** Phase 27 D-09 capped production source at 500 LOC; `daily_run.py` is already at 530 and an in-line fan-out loop would push it over. The seam is also testable in isolation: feed it a state + user list, assert N email dispatches.
- **News splits into two modules.** `news_fetcher.py` does I/O (yfinance + cache), `news_filter.py` is the pure critical-event check. Keeping the filter pure means it goes into the AST hex test alongside `alert_engine` and `pnl_engine` — protects the determinism contract.
- **No `users/` directory of per-user state files.** See §State Layout below — single `state.json` with a `users{}` map is cheaper, atomic, and matches the schema-migration habits already in place.
- **Tooltip content is a Python dict, not a JSON content file.** `dashboard_legacy/` already renders Python → HTML; importing a static dict is one fewer disk read per request and the content is too small (~40 strings) to warrant separate-file management.

---

## Architectural Patterns

### Pattern 1: Single-File Multi-Tenant State with `users{}` Map (RECOMMENDED)

**What:** `state.json` stays a single file. Schema v10 adds a top-level `users` dict keyed by `user_id`, plus a top-level `admin_user_id` pointer. Existing top-level keys (`positions`, `signals`, `trade_log`, `paper_trades`, `equity_history`, `alerts`, `markets`) are split: shared/computed values stay top-level (signals, ohlc_window, indicator_scalars, news cache); per-user values move under `state['users'][user_id]`.

**Schema v10 shape:**

```json
{
  "schema_version": 10,
  "admin_user_id": "u_admin_marc",
  "last_run": "2026-05-12",
  "signals": { "SPI200": {...}, "AUDUSD": {...} },          // SHARED (deterministic)
  "markets":  { "SPI200": {...}, "AUDUSD": {...} },         // SHARED (admin curates)
  "strategy_settings": { ... },                              // SHARED
  "_resolved_contracts": { ... },                            // SHARED runtime cache
  "warnings": [...],                                         // SHARED (system-level)
  "users": {
    "u_admin_marc": {
      "email": "mwiriadi@gmail.com",
      "role": "admin",
      "positions": {"SPI200": {...}, "AUDUSD": null},
      "trade_log": [...],
      "paper_trades": [...],
      "equity_history": [...],
      "account": 100000.00,
      "initial_account": 100000.00,
      "contracts": {...},
      "alerts": { "last_alert_state": {...} },
      "ui_prefs": { "active_market": "SPI200", "tour_completed": true }
    },
    "u_ff_alice_a1b2": {
      "email": "alice@example.com",
      "role": "friend_family",
      "positions": {...}, "trade_log": [...], ...
      "ui_prefs": { "tour_completed": false }
    }
  }
}
```

**When to use:** when (a) operator count is bounded (PROJECT.md says invite-only F&F, expected <20 users), (b) the existing atomic-write infrastructure is excellent and rewriting it for per-file is high-risk for low gain, (c) admin needs to enumerate all users in O(1) for the daily fan-out loop.

**Trade-offs:**

| Pro | Con |
|-----|-----|
| One `mutate_state` call still serializes all writers via the existing `fcntl.LOCK_EX` | All users contend for the same lock — but daily-cycle is once/day and HTMX edits are infrequent; lock-hold times are sub-millisecond |
| Schema migration is one `_migrate_v9_to_v10` step (rebucket fields under `users[admin_user_id]`) | One corrupt write affects everyone — mitigated by existing backup-on-corruption recovery |
| File size grows linearly with users — at 20 users × ~50KB each = 1MB. JSON parse is ~10ms. Acceptable | Above 100 users, parse time matters — but that's out of scope (PROJECT.md: F&F only) |
| Single-source enumeration: `state['users'].keys()` for fan-out, no directory scan | Backups must be coordinated — but a single-file backup is exactly what the existing `_backup_corrupt_file` already does |

**Why not per-user files (`users/{user_id}/state.json`):** would require N-fold extension of the atomic-write contract (tempfile + fsync + os.replace + dir-fsync + lock acquisition × N), break the existing `mutate_state(mutator)` chokepoint, and the daily fan-out would need a directory scan. The complexity multiplier is not justified by the gain (which is "blast radius of one corrupt file") — and corruption is already vanishingly rare with the current contract.

**Why not hybrid (admin in master, F&F in per-user):** asymmetric writes are a known foot-gun; admin and F&F end up with different invariants. Better to commit to one shape.

### Pattern 2: Cookie-Carries-`uid` + `Depends(current_user)` for Route Scoping

**What:** Extend the existing cookie payload. Today `tsi_session` is a signed-empty-string. v1.3 changes it to a signed JSON object: `{"uid": "u_admin_marc"}`. The middleware (`web/middleware/auth.py::AuthMiddleware._try_cookie`) decodes the payload and sets `request.state.user_id`. Routes consume it via:

```python
# web/dependencies.py (NEW)
from fastapi import Request, HTTPException

def current_user_id(request: Request) -> str:
    uid = getattr(request.state, 'user_id', None)
    if uid is None:
        raise HTTPException(status_code=401, detail='unauthenticated')
    return uid

def require_admin(request: Request) -> str:
    uid = current_user_id(request)
    # Cheap admin check — read auth_store.users (cached at app.state level) once per request.
    from auth_store import get_user_role
    if get_user_role(uid) != 'admin':
        raise HTTPException(status_code=403, detail='admin only')
    return uid
```

Routes:

```python
# web/routes/paper_trades.py — minimal diff
@app.post('/paper-trade/open')
async def paper_open(req: PaperOpenReq, user_id: str = Depends(current_user_id)):
    state_manager.mutate_user_state(user_id, lambda u: u['paper_trades'].append(...))
    ...
```

**When to use:** when you want every route handler to receive the user identity declaratively, with FastAPI's dependency-injection doing the wiring, and zero per-route boilerplate.

**Trade-offs:** middleware-set request.state + Depends is the FastAPI-idiomatic pattern; alternatives are worse:
- **Per-route decorator:** N decorators × M routes = touching every file; high diff, easy to forget one.
- **Middleware that injects directly into kwargs:** doesn't work with FastAPI's signature-based DI; would require monkeypatching the route function.
- **Reading `request.cookies` in each handler:** duplicates the cookie validation logic; bypasses `Depends` testing surface.

**Why this works for "shared display, per-user mutation":** Display routes (e.g. `GET /` rendering the dashboard) take `user_id: str = Depends(current_user_id)` and pass it through to the dashboard renderer. The renderer reads SHARED `state['signals']` for the signal panel and PER-USER `state['users'][user_id]` for positions/trades. One DI param, two scopings — controlled at the renderer, not duplicated across routes.

### Pattern 3: Daily-Cycle Fan-Out — Compute-Once, Distribute-Many

**What:** The existing 9-step daily orchestration in `daily_run.py::_run_daily_check_impl` does signal compute (steps 1–7) ONCE per market. v1.3 keeps that intact and changes only Step 9.6 (alerts) and a NEW Step 9.7 (per-user email):

```python
# per_user_fanout.py (NEW)
def fanout_alerts_and_emails(state, run_date, dashboard_url):
    """Step 9.6+9.7 replacement. Called once after mutate_state in daily_run."""
    for user_id, user_view in state['users'].items():
        # Per-user alert evaluation (uses SHARED signals, PER-USER positions)
        evaluate_user_alerts(state, user_id, dashboard_url)
        # Per-user email — same shared signal block, user-scoped P&L block
        send_user_email(state, user_id, run_date)
```

**Critical invariants preserved:**

- **No re-fetch:** yfinance is hit ONCE per market in step 3 (already true). The fan-out only reads the already-computed `state['signals']` and the per-user `state['users'][uid]`.
- **W3 invariant (exactly 2 `mutate_state` calls per run):** the alert-state commit was already a second `mutate_state` in `_evaluate_paper_trade_alerts_impl`. v1.3 batches it: ONE `mutate_state` per fan-out iteration would explode to 1+N saves. The eloquent fix is to BATCH all per-user alert state changes into a single `mutate_state` at the end of the fan-out — the function builds an in-memory dict of `{user_id: new_alert_state}` and applies them in one mutator. W3 stays at exactly 2.

> **Most eloquent:** batched-mutator fan-out. The fan-out loop builds an updates dict in memory; one terminal `mutate_state(lambda s: apply_all(s, updates))` writes everyone. Locality (the rule "we save once per run" stays in `state_manager`), no contract change to `mutate_state`, composes naturally with the existing 2-saves contract.

**Where fan-out lives:** `per_user_fanout.py` (new), called by `daily_run._run_daily_check_impl` between steps 9 and 9.5. NOT inside `daily_loop.py` (that's pure service-wiring) and NOT inside `notifier/` (that's transport). The orchestration belongs in an orchestrator-tier module.

### Pattern 4: News as a Dashboard-Render-Time Read with In-Process Cache

**What:** News fetch happens at HTTP request time via a 1h TTL in-process cache, NOT at daily-cycle time.

```python
# news_fetcher.py (NEW)
_NEWS_CACHE: dict[str, tuple[float, list[dict]]] = {}  # symbol -> (fetched_at, items)

def get_news(yfinance_symbol: str, ttl_seconds: int = 3600) -> list[dict]:
    now = time.monotonic()
    cached = _NEWS_CACHE.get(yfinance_symbol)
    if cached and (now - cached[0]) < ttl_seconds:
        return cached[1]
    items = _fetch_news(yfinance_symbol)  # yfinance.Ticker(s).news
    _NEWS_CACHE[yfinance_symbol] = (now, items)
    return items
```

**Why request-time, not daily-cycle:**
1. News goes stale faster than once a day; users hit dashboard at any time.
2. Request-time cache amortizes — first user pays the fetch cost (~500ms), rest see cache.
3. Daily cycle is already CPU-bound on indicator math; adding a network call would extend the run.
4. Crucially: news must NOT influence the signal — keeping it out of the daily cycle prevents accidental coupling.

**Critical-event keyword check (`news_filter.py`):** pure module, AST-hex-eligible. Reads (1) yfinance's `relatedTickers`/importance hint if present, (2) hand-curated keyword list (`['recession', 'rate cut', 'rate hike', 'crash', 'bankruptcy', 'fed', ...]`). Returns boolean. Tested with golden fixtures (a JSON of sample yfinance news rows + expected critical/not-critical labels) — same approach as the indicator oracle tests.

**HTMX panel route:** `GET /markets/{m}/news` → renders an HTML fragment (no full-page reload). Sits in `web/routes/news.py`, ~50 LOC. The dashboard's market panel does `<div hx-get="/markets/SPI200/news" hx-trigger="load">` — lazy load so a slow news fetch doesn't block the main dashboard render.

### Pattern 5: User Registry Co-Located in `auth.json`, Not a Separate File

**What:** `auth.json` already holds `trusted_devices[]`, `pending_magic_links[]`, and TOTP state. v1.3 adds two arrays:

```json
{
  "schema_version": 2,
  "users": [
    { "user_id": "u_admin_marc", "email": "mwiriadi@gmail.com", "role": "admin",
      "totp_secret": "...", "totp_enrolled": true, "created_at": "..." },
    { "user_id": "u_ff_alice_a1b2", "email": "alice@example.com", "role": "friend_family",
      "totp_secret": "...", "totp_enrolled": true, "invited_by": "u_admin_marc",
      "consumed_invite_token_hash": "sha256...", "created_at": "..." }
  ],
  "pending_invites": [
    { "token_hash": "sha256...", "issued_by": "u_admin_marc", "email": "alice@example.com",
      "created_at": "...", "expires_at": "...", "consumed": false }
  ],
  "trusted_devices": [
    { "uuid": "...", "user_id": "u_admin_marc", "label": "iPhone", ... }   // user_id added
  ],
  "pending_magic_links": [ ... ]   // user_id added per row
}
```

**Why not a separate `users.json`:** four reasons.
1. **Atomic-with-trust-state.** Adding a user and revoking their devices on delete are one transaction — keeping them in one file means one `save_auth` covers both.
2. **One atomic-write contract to maintain.** A second file means a second `_atomic_write` clone, a second corruption-recovery story, a second test.
3. **Invite-token storage MUST be transactional with user creation** — when consuming a magic-link invite, the same `mutate(auth)` flips `pending_invites[i].consumed=True` and pushes to `users[]`. A two-file split would mean two separate atomic writes with no cross-file transaction → race window where the invite is consumed but the user isn't created (or vice versa).
4. **`auth.json` already TypedDict-models its shape** (`AuthData`); adding `users` and `pending_invites` to that TypedDict is a small extension.

**When you'd split:** if `auth.json` exceeded ~100KB or if the user list became hot-read (multiple times per request). Neither is true at F&F scale.

**Hex boundary preserved:** `auth_store.py` already enforces "stdlib only — NOT itsdangerous, NOT pyotp." Invite token *minting* (signing) belongs in `web/services/invite_service.py` (which can use `itsdangerous.URLSafeTimedSerializer` like the cookie path); `auth_store` only stores the sha256 hash and the metadata.

### Pattern 6: Schema Migration v9 → v10 — Bucket Existing State Under `admin_user_id`

**What:** A single `_migrate_v9_to_v10(s: dict) -> dict` function in `state_manager.py` that:

1. Generates a deterministic admin user_id (`u_admin_marc` — locked in code).
2. Creates `s['users'] = {admin_user_id: {...}}`.
3. Moves these existing top-level keys into `s['users'][admin_user_id]`:
   - `positions`, `trade_log`, `paper_trades`, `equity_history`, `account`, `initial_account`, `contracts`, `alerts`, and any `ui_prefs`-shaped keys (e.g. `active_market_cookie_default`).
4. Leaves these top-level (SHARED): `signals`, `markets`, `strategy_settings`, `_resolved_contracts`, `warnings`, `last_run`, `schema_version`.
5. Stamps `s['admin_user_id'] = 'u_admin_marc'`.
6. Initializes `users[admin_user_id]['ui_prefs']['tour_completed'] = True` (admin has lived without the tour).

**Idempotency:** `_migrate_v9_to_v10` reads source keys with `.get()` and never mutates a key it has already moved. Re-running it on a v10 dict is a no-op.

**Migration chain contiguity gate** (`state_manager` module-load assert that `MIGRATIONS[2..STATE_SCHEMA_VERSION]` is gap-free) catches any drift — extending to v10 means adding `10: _migrate_v9_to_v10` to the dict and bumping `STATE_SCHEMA_VERSION = 10`.

**Pre-existing v11 in `system_params.py`:** the codebase already has `STATE_SCHEMA_VERSION: int = 11` and a `_migrate_v9_to_v10` + `_migrate_v10_to_v11` (per-market contract_type / financing_rate). v1.3's multi-tenant migration must therefore be `_migrate_v11_to_v12` (or higher — re-check at plan time). The shape of the migration is identical; only the version number changes. **Confirm at plan time, not now.**

### Pattern 7: Guide UI — HTML data-attributes for Tooltips, Cookie+state for Tour

**What:**

| Concern | Storage | Reason |
|---------|---------|--------|
| Tooltip content (per-panel help text) | Python dict in `dashboard_legacy/tooltip_data.py`, rendered into `<button data-tip="..." aria-describedby="...">` | Static content; ships with the binary; one fewer file to keep in sync; XSS-safe via `html.escape` at render time |
| Tour shown/hidden | Per-user `state['users'][uid]['ui_prefs']['tour_completed']` (boolean) | The tour is a one-time ceremony; needs to persist across logins, devices, and browsers — a cookie would re-show it on every fresh device |
| Tour modal open state mid-session | Hidden form field / HTMX swap target — no persistence | Ephemeral UI state |

**Why not cookie-only for tour:** F&F users may log in from phone+laptop; a cookie-only flag re-triggers the tour on each device. Per-user flag in `state.json` is correct.

**Why not separate JSON content file for tooltips:** for ~40 short strings, the file maintenance cost > the benefit. If marketing/copy ever wants to edit without a deploy, revisit — but that's a v1.4 concern.

**`POST /tour/complete` flow:**

```python
# web/routes/tour.py (NEW)
@app.post('/tour/complete')
async def complete_tour(user_id: str = Depends(current_user_id)):
    def _flip(u):
        u.setdefault('ui_prefs', {})['tour_completed'] = True
    state_manager.mutate_user_state(user_id, _flip)
    return Response(status_code=204)
```

`mutate_user_state` is a thin wrapper around `mutate_state` that ensures `users[uid]` exists and applies the mutator only to that subdict — single chokepoint preserved.

---

## Data Flow

### Per-user Daily Cycle Flow (replaces v1.2 single-user flow)

```
[systemd 08:00 Sydney trigger]
        ↓
main.py → daily_loop.run_daily_check
        ↓
daily_run._run_daily_check_impl
        ↓
state_manager.load_state()                  # ONE read of state.json
        ↓
FOR EACH market (SPI200, AUDUSD):           # SHARED COMPUTE — exactly as v1.2
  data_fetcher.fetch_ohlcv()                # ONE yfinance call per market
  signal_engine.compute_indicators()        # PURE
  signal_engine.get_signal()                # PURE
  sizing_engine.step(...)                   # PURE  (uses ADMIN positions for now —
                                            #  see "Pyramid/exit semantics" below)
END FOR
        ↓
state_manager.mutate_state(_apply_daily_run)   # SAVE #1 (W3 invariant)
        ↓
per_user_fanout.fanout_alerts_and_emails(state, run_date, dashboard_url):
  updates = {}
  FOR uid in state['users']:
    user_view = state['users'][uid]
    user_alerts = alert_engine.compute_user_alerts(  # PURE, takes shared signals + user positions
        state['signals'], user_view['positions'], user_view['alerts']['last_alert_state']
    )
    updates[uid] = user_alerts
    notifier.send_user_email(                # I/O: Resend HTTPS, per-user HTML
        state['signals'], user_view, run_date,
        recipient=user_view['email']
    )
  state_manager.mutate_state(_apply_alert_updates(updates))  # SAVE #2 — batched
        ↓
dashboard.render() → write dashboard.html       # admin-namespace dashboard for legacy URL
        ↓
_push_state_to_git(state, run_date)             # unchanged
```

**Key invariants:**
- yfinance hit count: still **exactly 2 per cycle** (one per market). Independent of N users.
- `mutate_state` call count: still **exactly 2 per cycle**. Fan-out batches alert updates.
- Signal determinism: SHARED. `state['signals']` is computed once and read N times — every user sees the same bytes.

### Pyramid/Exit Semantics — Critical Open Question

**v1.2 reality:** the orchestrator's per-symbol loop calls `sizing_engine.step()` with the operator's position and updates `state['positions'][market]`. There is ONE position per market.

**v1.3 dilemma:** if every user has their own `positions`, do we run `sizing_engine.step()` N times per market (once per user), or once for the admin and let users' "real" positions drift?

**Recommendation:** run `sizing_engine.step()` ONCE per market with **NO position context** (treat it as a pure signal-direction-only decision), then have `per_user_fanout` recompute per-user pyramid/exit decisions as a pure function of `(shared signal, shared indicators, this user's positions)`.

This means:
- The daily cycle's per-symbol loop changes shape: `sizing_engine.step` is called only to derive the *signal change* (LONG/FLAT/SHORT transition) and the *trailing stop level* — both deterministic from market data. Per-user position management moves to the fan-out.
- `sizing_engine.step` is already pure; the change is at the orchestrator level (which `position` to pass).
- Closed trades become per-user — `record_trade` becomes `record_user_trade(state, user_id, trade)`.

**Why this is hex-safe:** `sizing_engine` doesn't change. Only the orchestrator's call sites move from "one call per market" to "one signal-derive call per market + N position-resolve calls in the fan-out." Both are still pure-math calls; the AST guard sees no new imports.

**Trade-off:** a real change to the per-symbol loop in `daily_run.py`. Expect the diff to be ~50 LOC re-shape. Codecov risk: existing tests assume `state['positions']` lives at the top level — they need rewrite. This is the largest test-touch surface in v1.3.

### Request Flow — Authenticated Dashboard Hit

```
GET /  (HTTP request)
    ↓
nginx → uvicorn → FastAPI
    ↓
AuthMiddleware.dispatch
    ├─ EXEMPT_PATHS check (no)
    ├─ rate-limit check (no rule for GET /)
    ├─ PUBLIC_PATHS check (no)
    ├─ _try_cookie:
    │     decode tsi_session  → payload {"uid": "u_admin_marc"}
    │     request.state.user_id = "u_admin_marc"
    │     return True
    └─ call_next(request)
    ↓
web/routes/dashboard.py::dashboard_handler(user_id = Depends(current_user_id))
    ↓
DashboardService.render(user_id)
    ↓
state_manager.load_user_view(user_id)
    → returns {"signals": shared_signals, "user": state['users'][user_id]}
    ↓
dashboard_legacy.render(user_view)
    → composes HTML: SHARED signal panels + USER positions/trades/equity + tour modal
    ↓
HTTPResponse(html, 200)
```

---

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 1 admin (current) | Today's architecture works as-is once v10 migration runs |
| 1 admin + ≤20 F&F (v1.3 target) | Single `state.json`, fan-out fine, lock-contention sub-millisecond |
| 1 admin + 100 F&F | `state.json` parse cost ~50ms — still fine; fan-out is N×100ms email send → 10s total — well under cycle budget |
| 1 admin + 1000+ users | Out of scope. Move to SQLite (auth.json TypedDict already noted "Phase 18 will migrate to SQLite"); split state.json into per-user files OR move to Postgres |

### Scaling Priorities

1. **First bottleneck:** Resend rate limit (10 req/sec). Even 100 users serialized is 10s of email send time — fine for daily cycle. If it ever matters, parallelise sends with `concurrent.futures.ThreadPoolExecutor(max_workers=4)` inside `per_user_fanout` — BUT keep the `mutate_state` call serial.
2. **Second bottleneck:** `state.json` write contention if web traffic spikes. The `fcntl.LOCK_EX` is process-global; concurrent HTMX edits queue. At F&F scale this is invisible.

**Explicit non-concerns:** memory (state.json fits in RAM), CPU (signal compute is the same whether 1 or 100 users), yfinance rate limit (still 1 fetch per market per day).

---

## Anti-Patterns

### Anti-Pattern 1: Per-Route `if user.role == 'admin':` Checks

**What people do:** add an `if` guard at the top of every admin route handler.
**Why it's wrong:** N copies of the check; one missed file = privilege escalation. Doesn't compose with FastAPI's docs/dependency-tree.
**Do this instead:** `Depends(require_admin)` at the route definition. Single chokepoint. Tested once.

### Anti-Pattern 2: Re-Fetching yfinance Per User

**What people do:** in the fan-out loop, re-call `data_fetcher.fetch_ohlcv` per user "to get latest prices."
**Why it's wrong:** breaks determinism (different users see different prices if Yahoo updates between fetches), 100× the network cost, blows yfinance rate limits at scale.
**Do this instead:** fan-out reads from `state['signals']` exclusively. The single per-market fetch in step 3 is the ONLY yfinance call per cycle.

### Anti-Pattern 3: Signal Compute Inside the Fan-Out

**What people do:** call `signal_engine.get_signal` inside the per-user loop "for clarity."
**Why it's wrong:** N× the CPU for identical output; the determinism contract reads "compute once, distribute many"; hex-boundary signature (one signal per market per day) becomes muddier.
**Do this instead:** signal compute stays in step 3. Fan-out reads `state['signals']` and only resolves per-user position deltas (which are pure too — `sizing_engine.compute_unrealised_pnl` etc.).

### Anti-Pattern 4: News in the Pure-Math Hex

**What people do:** put `news_fetcher` next to `signal_engine` "because it's about markets."
**Why it's wrong:** `news_fetcher` does network I/O — putting it in the hex breaks the AST-blocklist test (yfinance import). Once it's in, the temptation to "let news influence the signal" is one line away.
**Do this instead:** `news_fetcher` is a peer of `data_fetcher.py` (I/O hex). Only `news_filter.py` (pure keyword check) sits in the hex.

### Anti-Pattern 5: Per-User State as a Separate Filesystem Tree

**What people do:** `users/{user_id}/state.json` because "isolation feels safer."
**Why it's wrong:** N atomic-write contracts to maintain; daily fan-out becomes a directory scan; backup/restore is now a multi-file dance; existing `mutate_state(mutator)` chokepoint cannot serialise cross-user invariants.
**Do this instead:** single `state.json` with a `users{}` map. Existing atomic-write covers all users.

### Anti-Pattern 6: Cookie-Only Tour-Completion Flag

**What people do:** set `tour_completed=true` cookie, done.
**Why it's wrong:** cookie is per-device per-browser. F&F user logs in from phone next day → re-sees the tour. Looks broken.
**Do this instead:** flag lives in `state['users'][uid]['ui_prefs']['tour_completed']`. Single source of truth for "have they seen this once."

### Anti-Pattern 7: Invite Token Stored Plaintext in `auth.json`

**What people do:** `pending_invites[i].token = "raw_token_string"`.
**Why it's wrong:** leaked auth.json reveals live invite tokens; attacker can claim invites meant for someone else.
**Do this instead:** mirror the existing `pending_magic_links` pattern — store `sha256(unhashed_token).hexdigest()`, never the raw token. This is already the established pattern in `auth_store.add_magic_link` / `consume_magic_link`. The invite path is structurally identical.

### Anti-Pattern 8: Synchronously Awaiting a 5xx Resend in the Fan-Out

**What people do:** if user N's email Resend POST fails, abort the fan-out.
**Why it's wrong:** users N+1..M never get their emails because user N's Gmail had a hiccup.
**Do this instead:** `notifier/transport.py` already returns `(success, errmsg)` and never raises. Fan-out catches the failure tuple, appends to `state['users'][uid]['warnings']` (so next email surfaces it), continues.

---

## Integration Points

### External Services (v1.3 deltas)

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| yfinance — news | `yfinance.Ticker(symbol).news` (no auth) — module-local in-process LRU cache, 1h TTL | Lazy-load at request time, not daily-cycle. yfinance returns `[{title, link, providerPublishTime, ...}, ...]`. May return `[]` silently — handle empty list as "no news available" panel state. |
| Resend — multi-recipient | Existing single-recipient POST per user; sequential in fan-out | Per-user emails go to per-user `email` field from `auth.json::users[]`. From-address remains `signals@carbonbookkeeping.com.au` (one verified sender). |
| Email reply-handling | None — outbound only | F&F users CANNOT reply to the email. If they need to opt out, dashboard has a toggle (admin-revocable). |

### Internal Boundaries (v1.3 deltas)

| Boundary | Communication | Notes |
|----------|---------------|-------|
| `web/middleware/auth.py` ↔ `web/dependencies.py` | `request.state.user_id` set by middleware, read by `Depends(current_user_id)` | One write site, one read site — testable at both ends |
| `web/routes/admin/*` ↔ `auth_store` (user list) | direct imports — `auth_store.list_users()`, `auth_store.add_user(...)`, `auth_store.revoke_user(uid)` | Admin routes are the only place that reads the full user list; F&F routes never enumerate users |
| `daily_run.py` ↔ `per_user_fanout.py` | `per_user_fanout.fanout_alerts_and_emails(state, run_date, dashboard_url)` | One call site (between step 9 and 9.5) — the entire multi-tenant fan-out is one function call |
| `per_user_fanout.py` ↔ `notifier/dispatch.py` | `notifier.send_user_email(state, user_view, run_date, recipient)` | New signature; the existing `send_signal_email` becomes a thin wrapper for backward compat |
| `state_manager.py` ↔ web routes | EXISTING `mutate_state(mutator)` + NEW `mutate_user_state(user_id, mutator)` | New helper is a 6-line wrapper around `mutate_state` — no new lock contract |
| `news_filter.py` ↔ AST hex test | `_HEX_PATHS_STDLIB_ONLY` extended to include `news_filter.py` | Test is a parametrized list — adding the path is a one-line extension |
| `news_fetcher.py` ↔ AST hex test | NOT in the hex list (it imports yfinance, by design) | Mirrors the existing `data_fetcher.py` carve-out — has its own `test_data_fetcher_no_forbidden_imports` test pattern |

### File-Size Hygiene (Phase 27 D-09 — 500 LOC cap)

**Already over-cap pre-v1.3, MUST split before adding scoping:**

| File | Current LOC | v1.3 Pressure | Recommended Split |
|------|------------|---------------|-------------------|
| `web/routes/trades.py` | 746 | + `user_id` injection in 3 POST routes + 3 GET helpers | `trades_open.py` + `trades_close.py` + `trades_modify.py` + `trades_helpers.py` (form GETs) |
| `web/routes/dashboard.py` | 644 | + per-user dashboard rendering | Split request handlers vs HTML composition: `dashboard_routes.py` (handlers) + already-existing `dashboard_legacy/` (composition) |
| `web/routes/totp.py` | 614 | + per-user TOTP state lookup (already by `user_id` since `auth_store` extension) | `totp_enroll.py` + `totp_verify.py` |
| `web/routes/login.py` | 608 | + invite-token consumption flow | `login_form.py` + `login_post.py` + `login_invite.py` |
| `web/routes/paper_trades.py` | 493 | + `user_id` injection in 4 mutation routes | Stays just-under unless invite UI lands here. Likely keeps |
| `state_manager.py` | 1293 | + `mutate_user_state`, `load_user_view`, `_migrate_v11_to_v12` | Already split-pressure pre-v1.3 — see `state_actions.py`. v1.3 may need a `state_manager_users.py` daughter for the new helpers if total grows past 1500 |

**Strategy:** complete the splits in their own phase BEFORE adding `user_id` scoping. Splitting an over-cap file while changing its semantics simultaneously courts merge-conflict pain (per global LEARNINGS on parallel worktrees + file scope).

---

## Build Order (Dependency-Respecting Phase Sequence)

Order chosen so each phase produces something testable, downstream phases depend only on stable upstream contracts, and the AST guard + atomic-write contract are never broken in between.

| Order | Phase | Rationale | Unblocks |
|-------|-------|-----------|----------|
| 1 | **File-size pre-split** (trades.py, login.py, totp.py, dashboard.py route) | Touch over-cap files BEFORE multi-tenant changes; merge surface stays clean. Behaviour-preserving — no semantics change | All later phases that diff these files |
| 2 | **Schema migration v9→v10 (or v11→v12) + admin namespace** | Foundational — every later phase reads `state['users']`. Zero behaviour change for the admin (their data is still there, one level down). 1880+ tests rerun against migrated state. | Phases 3–7 |
| 3 | **User registry + invite-token storage in `auth.json`** | `auth_store.users[]` + `pending_invites[]` + invite mint/consume helpers. No routes yet — pure storage layer | Phases 4, 5 |
| 4 | **Cookie payload + `current_user` Depends + admin-detection** | Middleware sets `request.state.user_id`; new `web/dependencies.py`. ALL existing routes get `Depends(current_user_id)` injected — but during this phase admin is still the only user, so observable behaviour is identical | Phase 5 |
| 5 | **RBAC + admin routes** (`/admin/users`, `/admin/invite`, revoke) + invite-acceptance flow | Admin can now invite; new users can claim invites via magic-link-style flow. F&F users land in `auth.json::users[]` and `state['users'][uid]` skeleton | Phase 6 |
| 6 | **Per-user route scoping** — `paper_trades`, `trades`, `markets` (mutations + display) read SHARED signals, write PER-USER positions | Now real multi-tenancy. Tests rewrite to confirm cross-user isolation. **Pyramid/exit semantics shift here** (see §Pyramid/Exit) — the largest semantic diff | Phase 7 |
| 7 | **Per-user email fan-out** (`per_user_fanout.py`) + admin-vs-F&F email shape | Daily cycle sends N emails. Admin email is "main email"; F&F email is leaner (positions + alerts + signal block, no admin sentinels) | Phase 8 |
| 8 | **News integration** (`news_fetcher.py`, `news_filter.py`, `/markets/{m}/news` HTMX panel) | Independent of multi-tenancy — could ship anywhere after phase 1, but ordering after 7 keeps the email-fan-out review window simple | Phase 9 |
| 9 | **Guide UI** (tooltips + first-run tour) | Frontend-leaning; backend touch is one route + one user_id flag | — |
| 10 | **Codemoot + Nyquist gate** | Per CLAUDE.md milestone gate. Backfill VALIDATION + SECURITY for any phase missing one | — |

**Why this order:**
- Schema before routes: routes need `state['users'][uid]` to exist. Reverse order → routes write to undefined keys.
- Auth-store users before middleware: middleware needs to look up role; lookup needs the store.
- Middleware before RBAC routes: admin gate is a `Depends` chained on `current_user`; need the dependency first.
- RBAC before per-user scoping: the "is this F&F or admin?" check determines what the dashboard should render — needs role available.
- Per-user scoping before email fan-out: fan-out reads `state['users']` — that has to be populated by working routes first.
- News and Guide UI come last: they're additive, not tangled with the auth/state changes.

---

## AST Hex Boundary — What Survives v1.3 Unchanged

| AST Test | Modules Locked | v1.3 Change |
|----------|---------------|-------------|
| `test_forbidden_imports_absent` (`_HEX_PATHS_ALL`) | `signal_engine`, `sizing_engine`, `system_params`, `pnl_engine`, `alert_engine`, `backtest/simulator`, `backtest/metrics` | None. No new imports. `news_filter.py` joins `_HEX_PATHS_STDLIB_ONLY`. |
| `test_phase2_hex_modules_no_numpy_pandas` (`_HEX_PATHS_STDLIB_ONLY`) | `sizing_engine`, `system_params`, `pnl_engine`, `alert_engine` | + `news_filter.py` |
| `test_state_manager_no_forbidden_imports` | `state_manager.py` | None. New helpers (`mutate_user_state`, `load_user_view`) use only existing imports |
| `test_data_fetcher_no_forbidden_imports` | `data_fetcher.py` | None. `news_fetcher.py` is a peer with its OWN test (mirroring this one) |
| `TestWebHexBoundary.FORBIDDEN_FOR_WEB` | web/* | Unchanged set. New web/dependencies.py and admin routes use only `fastapi`, `starlette`, `auth_store`, `state_manager` (already allowed) |

**The AST guard does not need to change.** Every new module either lives outside the guarded paths or imports only stdlib + already-allowed modules.

---

## Atomic-Write Contract — Preserved Verbatim

`state_manager._atomic_write` (tempfile + fsync + os.replace + dir-fsync, with `fcntl.LOCK_EX` cross-process) is the chokepoint for all `state.json` writes. v1.3 does NOT modify it.

`mutate_user_state(user_id, mutator)`:

```python
def mutate_user_state(user_id: str, mutator: Callable[[dict], None],
                     path: Path | None = None) -> dict:
    """Wrap mutator so it runs against state['users'][user_id] only.
    Single chokepoint preserved — delegates to existing mutate_state.
    """
    def _inner(s: dict) -> None:
        if user_id not in s.get('users', {}):
            raise ValueError(f'unknown user_id: {user_id}')
        mutator(s['users'][user_id])
    return mutate_state(_inner, path=path)
```

Lock semantics, fsync ordering, corruption recovery — all inherited unchanged.

---

## Sources

- `.planning/PROJECT.md` (project root) — v1.3 scope, F&F constraint, schema-migration policy
- `.planning/MILESTONES.md` — v1.0/v1.1/v1.2 architecture additions; Phase 27 file-size cap
- `.planning/research/v1.0-archive/ARCHITECTURE.md` — v1.0-era hex-lite blueprint (still authoritative)
- `state_manager.py` — read end-to-end: atomic-write, MIGRATIONS dict, mutate_state contract
- `auth_store.py` — read end-to-end: TypedDict shape, magic-link sha256 pattern, atomic-write parity with state_manager
- `web/app.py`, `web/middleware/auth.py`, `web/routes/*` — read for current cookie/auth/route patterns
- `daily_run.py`, `daily_loop.py` — read for the 9-step orchestration sequence and the 2-saves-per-run W3 invariant
- `tests/test_signal_engine.py::TestDeterminism` — read for AST guard structure and forbidden-imports lists

---
*Architecture research for: v1.3 multi-tenant retrofit of FastAPI + file-state trading signal app*
*Researched: 2026-05-10*
