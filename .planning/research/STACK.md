# Stack Research — v1.3 Multi-Tenant Friends & Family

**Domain:** Multi-tenant additions to existing FastAPI/HTMX/file-state trading-signals app
**Researched:** 2026-05-10
**Confidence:** HIGH for additions; HIGH for delta vs v1.2 baseline
**Scope:** v1.3 deltas only. The validated v1.0/v1.1/v1.2 stack (Python 3.11.8 / FastAPI / uvicorn / HTMX / yfinance 1.2.0 / pandas 2.3.3 / Resend HTTPS / single state.json / Chart.js 4.4.6) is unchanged. See `.planning/research/v1.0-archive/STACK.md` for the v1.0-era research that established that base.

---

## Executive Summary

v1.3 adds **zero new runtime dependencies** to `requirements.txt`. Every additional capability rides on libraries already installed (`fastapi`, `secrets`, `pathlib`, `json`, `os`, `httpx`/`requests`, `yfinance`, `pytz`) or on **two CDN-only frontend additions** (Shepherd.js for the first-run tour, Microtip for tooltips) — both single-file, build-step-free, SRI-pinnable.

The hard constraints (no DB, no SPA, Resend-only, file-based persistence) are honoured by:

1. **Per-user state files** in a sharded directory layout (`state/users/{user_id}.json`), with a slim **registry file** (`state/users.json`) listing every user's id, role, status, and email. Admin's existing `state.json` migrates to a privileged namespace.
2. **Invite tokens** generated via `secrets.token_urlsafe(32)`, stored as single rows in `state/invites.json` with `consumed_at` flag — no DB, no JWT, no library beyond stdlib.
3. **RBAC enforcement** as a single FastAPI `Depends(require_user)` / `Depends(require_admin)` dependency chain. Every existing route gets a one-line addition; no rewrite of `state_manager` API surface.
4. **yfinance news** via `Ticker.news` once per market per day, cached in-memory + persisted to `state/news_cache.json` (24h TTL). yfinance 1.x changed the news shape to a nested `content` envelope — handled with a defensive normaliser that supports both old (`title`/`summary`/`providerPublishTime`) and new (`content.title`/`content.summary`/`content.pubDate`) shapes. **No reliable importance hint exists in the yfinance public surface**; critical-event flag = hand-curated keyword regex over title+summary.
5. **First-run tour:** **Shepherd.js v14.5.1** (latest stable 14.x; v15 also available but 14 is more battle-tested with more docs). Loaded from jsDelivr with SRI pin. ~30KB gzipped.
6. **Tooltips:** **Microtip 0.2.2** — pure-CSS, 1KB, `aria-label` + `role="tooltip"` driven. Zero JS. Fits HTMX swap pattern perfectly (no rebinding after swap).
7. **Per-user email** uses the same Resend HTTPS code path as today; rate-limit math fits comfortably in the free/low tier (see §Resend Tier Sanity Check).
8. **Schema v9 → v10** is a one-time migration that introduces the user registry and moves admin's existing state into `state/users/admin.json` while preserving every paper trade, alert, and ledger row.

The signal compute remains shared and deterministic — one fetch+compute per market per day, signal output written once to a market-scoped namespace consumed by every user. Only **trade ledger / alerts / paper P&L / preferences / equity** are per-user. The hex-lite AST blocklist is preserved by keeping the per-user file I/O inside `state_manager` (already an I/O adapter); pure-math modules import nothing new.

---

## Recommended Stack — v1.3 Additions Only

### Backend (Python — zero new deps)

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `secrets` (stdlib) | 3.11.8 | Invite token generation, session-id refresh on user creation | `secrets.token_urlsafe(32)` gives 256 bits of entropy in URL-safe base64 (43 chars). Cryptographically strong. Already used elsewhere in the app for CSRF. Zero collision risk at any plausible scale (birthday-paradox collision needs ~2^128 tokens). |
| `pathlib.Path` (stdlib) | 3.11.8 | Per-user file path resolution | Already in use. New helper `user_state_path(user_id)` returns `Path("state/users") / f"{user_id}.json"`. |
| `json` + atomic write helper (existing) | — | Per-user state persistence | The existing `_atomic_write_json(path, data)` (tempfile + fsync + os.replace) in `state_manager.py` already handles the durability story. New code reuses it per file. |
| `fastapi.Depends` (existing) | already pinned | RBAC enforcement | Single dependency chain `get_current_user → require_user / require_admin`. Existing routes get one decorator added; no body rewrite. |
| `re` (stdlib) | 3.11.8 | Critical-event keyword matcher for news | Pattern: `re.compile(r"\b(downgrade|miss|guidance|fed|rba|rate cut|rate hike|recession|crash|halt|inquiry|fraud|warning|profit\s+warning|scandal|crisis)\b", re.I)`. Hand-curated, version-controlled, zero deps. |
| `time` / `datetime` (stdlib) | 3.11.8 | News cache TTL + invite token expiry | 24h news cache, 7-day invite token expiry. Already in use. |

### Frontend (CDN-only additions — zero build step)

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| **Shepherd.js** | **14.5.1** (UMD bundle) | First-run guided tour modal | Most battle-tested + actively maintained tour library (170+ releases, 100+ contributors, last release 2025/2026). UMD build attaches `Shepherd` to `window` — drop-in `<script>` tag. ~30KB gzipped. AGPL or commercial license; **the trading-signals app is private/single-operator + invite-only F&F, so AGPL viral terms do not trigger a distribution event**. Theme via CSS overrides — fits the existing dark theme. |
| **Microtip** | **0.2.2** | Per-panel inline tooltips on dashboard | Pure CSS, 1KB, `aria-label` + `role="tooltip"` + `data-microtip-position` attributes. Zero JavaScript = survives every HTMX swap with no rebinding. WAI-ARIA accessible. MIT license. |

### Development Tools (no change)

| Tool | Purpose | Notes |
|------|---------|-------|
| pytest 8.3.3 (existing) | Test new RBAC dep, per-user state isolation, invite consumption | New test files: `tests/test_rbac.py`, `tests/test_per_user_state.py`, `tests/test_invites.py`, `tests/test_news.py`. |
| ruff 0.6.9 (existing) | Lint new code | No new rules needed. |
| pytest-freezer (existing) | Freeze time in invite-expiry + news-cache-TTL tests | Already in use for scheduler tests. |

### Explicitly NOT added (constraint guard)

| Avoid | Why not | What to use instead |
|-------|---------|---------------------|
| **SQLite / Postgres / Redis** | Hard constraint — file-only state | `state/users.json` registry + `state/users/{user_id}.json` per-user files |
| **JWT (PyJWT, python-jose)** | Overkill — existing cookie-session works; JWT adds key rotation pain | Existing cookie session, extended with `user_id` claim |
| **passlib / bcrypt** (new install) | The existing TOTP+magic-link UX has no per-user *password* — F&F users are TOTP-only after invite redemption, same as admin | Reuse existing TOTP flow per-user |
| **Alembic / yoyo** schema migrations | No DB | Existing in-process `_migrate(state, from_v, to_v)` chain extended with v9→v10 step |
| **resend Python SDK** | Already rejected in v1.0 research; raw `requests` to Resend HTTPS API still wins | Existing `notifier/` package |
| **Driver.js / Intro.js** for the tour | Driver.js is leaner but Shepherd has the strongest 2025–2026 maintenance pulse and richer step options for our 6–8 step tour. Intro.js is also AGPL with weaker community | Shepherd.js |
| **Tippy.js / Floating UI** for tooltips | JS-based; needs rebinding on every HTMX swap; 5–20× the bytes of Microtip for the same feature surface | Microtip (CSS-only) |
| **APScheduler** for per-user email fan-out | The existing single 08:00 Sydney `schedule.every().day.at(...)` job loops over the user registry and sends N emails — no need for per-user job scheduling | Existing `schedule` library, loop inside the daily handler |
| **HTMX websockets / SSE** for live news refresh | News refresh is daily, not real-time; full-page HTMX swap on dashboard load is sufficient | Standard HTMX `hx-get` on dashboard refresh |
| **Tour libraries with React/Vue deps** (Reactour, vue-tour) | Hard constraint — no SPA framework | Shepherd.js (vanilla) |
| **bleach / markupsafe** new install | FastAPI/Jinja2 (already used by dashboard) auto-escapes by default; news titles + summaries are escaped on render via `{{ news.title }}` not `{{ news.title \| safe }}` | Jinja2 default escape (already in use) |

---

## Per-User State File Layout — Decision: Sharded Directory

**Three options were evaluated. Recommendation: Option C (sharded directory).**

| Option | Layout | Concurrency | Atomic write cost | Migration complexity | Verdict |
|--------|--------|-------------|-------------------|----------------------|---------|
| **A: Master file with user keys** | One `state.json` with `{users: {id: {...}, ...}, signals: {...}}` | Every write contends on a single file lock — admin save blocks F&F save | O(N) bytes per write (rewrites all users every save) | Low — single migration step | ✗ Worst — single-writer invariant breaks at N>3 users |
| **B: One state.json per user, no registry** | `state/{user_id}.json` only | Per-user lock — no contention | O(user_state) per write | Medium — must scan dir on every login | ⚠ Workable but no fast user-list lookup for admin UI |
| **C: Sharded directory + slim registry** | `state/users.json` (registry) + `state/users/{user_id}.json` (per-user) + `state/signals/{market}.json` (shared) + `state/news_cache.json` + `state/invites.json` | Per-user lock + tiny registry lock (only updated on user create/disable) | O(user_state) per write; registry is <10KB even at 100 users | Medium — single migration step + admin scan helper | ✓ **Recommended** |

### Recommended layout (Option C)

```
state/
├── users.json                    # Registry: {users: [{id, email, role, status, created_at, disabled_at}], schema_version: 10}
├── invites.json                  # {invites: [{token_hash, email, created_at, expires_at, consumed_at, consumed_by}]}
├── news_cache.json               # {SPI: {fetched_at, items: [...]}, AUDUSD: {fetched_at, items: [...]}}
├── signals/
│   ├── SPI.json                  # Shared signal output (per market, written once per daily run)
│   └── AUDUSD.json
└── users/
    ├── admin.json                # Marc's existing state — migrated from old state.json
    ├── {user_id_1}.json          # F&F user 1: paper_trades, alerts, equity, preferences
    ├── {user_id_2}.json
    └── ...
```

**Why this fits constraints:**

- **No DB:** every file is plain JSON, atomic-written via the existing `_atomic_write_json()` helper.
- **Sole-writer invariant preserved per file:** `state_manager.save_user_state(user_id, state)` is the only writer to `users/{user_id}.json`. Admin saves to `users/admin.json`. Daily signal run writes `signals/{market}.json` once. Registry is written only on user-create / disable / role-change.
- **Hex-lite preserved:** all per-user I/O lives in `state_manager` (already an I/O adapter). Pure-math modules (`signal_engine`, `sizing_engine`, `system_params`) import nothing new — the AST blocklist still passes.
- **Admin user-list:** a single `load_user_registry()` reads `users.json` (~10KB at 100 users). No directory scan.
- **Crash recovery:** existing `JSONDecodeError → backup + reinit` pattern applies per file. A corrupt `users/{user_id}.json` does NOT take down the rest of the system — only that user gets a recovery banner.
- **Backup story:** `state/` directory tarballed daily; same git-deploy-key push pattern applies.

### `state_manager` API additions (no breaking changes to existing API)

```python
# New (additive — existing load_state()/save_state() preserved as admin-namespace shims):
def load_user_state(user_id: str) -> dict: ...
def save_user_state(user_id: str, state: dict) -> None: ...
def load_user_registry() -> dict: ...
def save_user_registry(registry: dict) -> None: ...
def load_market_signal(market: str) -> dict: ...      # shared signals/{market}.json
def save_market_signal(market: str, signal: dict) -> None: ...

# Existing load_state()/save_state() become thin wrappers:
def load_state() -> dict:
    return load_user_state("admin")  # admin namespace
def save_state(state: dict) -> None:
    save_user_state("admin", state)
```

This means **every existing route that calls `load_state()` continues to work** for the admin path. F&F routes get a one-line change: replace `state = load_state()` with `state = load_user_state(current_user.id)`.

---

## Invite Token Generation + Storage

### Token shape

```python
import secrets
token = secrets.token_urlsafe(32)  # 43 chars URL-safe base64, 256 bits entropy
```

- **Cryptographic strength:** `secrets` uses the OS CSPRNG (`/dev/urandom` on Linux). 256 bits is far above any practical brute-force threshold.
- **URL-safe:** drops into magic-link URLs without escaping (`https://signals.mwiriadi.me/invite/{token}`).
- **Collision-safe:** birthday-paradox collision requires ~2^128 tokens. At 100 invites/year, collision probability is < 10^-30.

### Storage shape — `state/invites.json`

```json
{
  "schema_version": 10,
  "invites": [
    {
      "token_hash": "sha256:7f9e3b...",        // hash, not the token itself
      "email": "friend@example.com",
      "created_by": "admin",
      "created_at": "2026-05-10T08:00:00+10:00",
      "expires_at": "2026-05-17T08:00:00+10:00",
      "consumed_at": null,
      "consumed_by_user_id": null
    }
  ]
}
```

**Critical security pattern:** store **`sha256(token)`**, not the token itself. The plaintext token is only ever returned in the admin UI response at issue time and emailed to the invitee. If `state/invites.json` is ever exposed (backup leak, repo accident), the tokens cannot be replayed. Comparison on redeem: `hashlib.sha256(submitted_token.encode()).hexdigest() == stored_hash`.

**Single-use guarantee:** atomic write loop on redeem:

```python
def redeem_invite(token: str, new_user_email: str) -> Invite:
    token_hash = "sha256:" + hashlib.sha256(token.encode()).hexdigest()
    invites = load_invites()
    for inv in invites["invites"]:
        if inv["token_hash"] == token_hash:
            if inv["consumed_at"] is not None:
                raise InviteAlreadyConsumed()
            if datetime.now(SYDNEY) > parse(inv["expires_at"]):
                raise InviteExpired()
            inv["consumed_at"] = now_iso()
            inv["consumed_by_user_id"] = create_user(new_user_email).id
            save_invites(invites)  # atomic write — race-safe under single-writer invariant
            return inv
    raise InviteNotFound()
```

The existing single-writer invariant (uvicorn runs on one worker; the daily `schedule` loop runs in the same process) means no two redeems can race within a single uvicorn instance. If we ever go multi-worker, a `fcntl.flock` on the invites file is the file-lock primitive — but for v1.3 single-worker, the existing invariant suffices.

**Expiry:** 7 days from issue. Configurable in `system_params.py` (still pure-math; constant, not I/O).

**Admin operations:** issue / list / revoke (set `consumed_at` to a sentinel like `"REVOKED:{timestamp}"`) — three new admin-only routes.

---

## RBAC at the FastAPI Layer

### Pattern: dependency-injection chain

```python
# auth/deps.py — new module
from fastapi import Depends, HTTPException, Request

def get_current_user(request: Request) -> User | None:
    user_id = request.session.get("user_id")  # existing cookie session, now stores user_id
    if not user_id:
        return None
    return load_user(user_id)  # from registry

def require_user(user: User | None = Depends(get_current_user)) -> User:
    if not user or user.status != "active":
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return user

def require_admin(user: User = Depends(require_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403)
    return user
```

### Applied to existing routes (one-line change per route)

```python
# Before (v1.2):
@app.get("/markets/{market}/dashboard")
def dashboard(market: str):
    state = load_state()
    return render(state, market)

# After (v1.3):
@app.get("/markets/{market}/dashboard")
def dashboard(market: str, user: User = Depends(require_user)):
    state = load_user_state(user.id)
    return render(state, market, user=user)
```

**Mass refactor scope estimate:** ~25 existing routes × one-line `Depends` addition + `load_state()`→`load_user_state(user.id)` swap = ~50 LOC of mechanical changes. The route bodies don't change.

**Admin-only routes** (new — `/admin/users`, `/admin/invites/issue`, `/admin/invites/revoke`, `/admin/users/{id}/disable`) use `Depends(require_admin)`.

**Privacy guarantee enforced at the data layer:** because `load_user_state(user_id)` only ever reads `state/users/{user_id}.json`, there is no path by which an F&F route could accidentally read another user's data. The admin user-list view explicitly does NOT load any user's content — only the registry rows.

### CSRF on state-mutating routes

The existing CSRF token middleware (Phase 16.1) continues to apply. After a session is regenerated on invite-redeem (per the global learning about post-`session.regenerate()` token staleness), the response includes a fresh `_csrfToken`.

---

## yfinance News Integration

### API shape — yfinance 1.x changed this

yfinance 1.0.0 (released 2025) restructured the `Ticker.news` payload from a flat dict per item to a nested `content` envelope. **The app must defensively support both shapes** to survive a yfinance minor-version drift between dev and prod.

**Old shape (yfinance ≤0.2.x):**
```python
[{
  "uuid": "...",
  "title": "ASX 200 closes higher",
  "publisher": "Reuters",
  "link": "https://...",
  "providerPublishTime": 1715318400,    # unix epoch
  "type": "STORY",
  "thumbnail": {...},
  "relatedTickers": ["^AXJO"]
}]
```

**New shape (yfinance ≥1.0):**
```python
[{
  "id": "...",
  "content": {
    "title": "ASX 200 closes higher",
    "summary": "...",
    "description": "...",
    "pubDate": "2026-05-10T08:00:00Z",
    "displayTime": "...",
    "provider": {"displayName": "Reuters"},
    "clickThroughUrl": {"url": "https://..."},
    "canonicalUrl": {"url": "https://..."},
    "thumbnail": {"resolutions": [...]},
    "contentType": "STORY"
  }
}]
```

### Importance hint — DOES NOT EXIST in yfinance public surface

After examining the yfinance source and documentation, **there is no `editorsPick`, `storyImpact`, or `importance` field exposed by `Ticker.news`**. Some downstream Yahoo Finance APIs surface an `editorsPick` / `featured` flag, but yfinance does not expose it. **Confidence: HIGH** — verified by inspecting the new content envelope structure and community PR discussions; no official changelog or doc references importance scoring.

**Decision: hand-curated keyword regex is the entire critical-event signal.**

```python
# news/critical.py — new module
import re
CRITICAL_PATTERNS = re.compile(
    r"\b("
    r"downgrade|upgrade|miss(es|ed)?|beat(s|en)?|"
    r"guidance|outlook|warning|profit\s+warning|"
    r"fed|rba|ecb|boe|rate\s+(cut|hike|decision)|cpi|inflation|"
    r"recession|crash|plunge|tumble|surge|rally|"
    r"halt|suspend|inquiry|investigation|fraud|scandal|crisis|"
    r"earnings|results|dividend|split|merger|acquisition|takeover|"
    r"default|bankruptcy|liquidation|administration"
    r")\b",
    re.IGNORECASE,
)

def is_critical(title: str, summary: str = "") -> bool:
    return bool(CRITICAL_PATTERNS.search(f"{title} {summary}"))
```

**Why this is sufficient:**
- The dashboard is signal-focused; news is **context**, not a trade trigger. False positives on the critical flag cause an extra red-bordered news item — annoying, not dangerous.
- The keyword list is hand-curated and version-controlled — Marc can add patterns as he encounters new high-impact news genres.
- Zero ML / NLP / external-API dependency.
- Deterministic and unit-testable: a fixture of 30 sample headlines can lock the classifier behaviour.

### Caching strategy — daily, not hourly

| Cadence | Rate-limit risk | Freshness | Decision |
|---------|----------------|-----------|----------|
| Hourly | High — 24 calls/day × 2 markets = 48/day | News changes hourly during US/EU sessions | ✗ Overkill for a daily-cadence app |
| **Daily** | None — 2 calls/day in the existing 08:00 Sydney run | Refreshed once per business day, displayed all day | ✓ **Recommended** |
| On-demand (per dashboard load) | High — could hit 100+/day if Marc refreshes a lot | Always fresh | ✗ Defeats yfinance courtesy budget |

**Implementation:** the daily 08:00 Sydney signal run calls `Ticker(symbol).news` once per market, normalises both shapes into a unified internal dict, runs the critical-event classifier, and writes `state/news_cache.json`:

```json
{
  "schema_version": 10,
  "markets": {
    "SPI": {
      "fetched_at": "2026-05-10T08:00:00+10:00",
      "items": [
        {
          "id": "...",
          "title": "...",
          "summary": "...",
          "publisher": "...",
          "url": "...",
          "published_at": "2026-05-10T07:30:00+10:00",
          "is_critical": true
        }
      ]
    },
    "AUDUSD": {...}
  }
}
```

**Cache TTL guard:** dashboard render checks `now - fetched_at < 24h`; if exceeded (weekend, scheduler fail), shows a "News last updated 2 days ago" banner instead of stale items presented as fresh.

**Rate-limit risk:** **negligible**. Two `Ticker.news` calls per day per app instance is well within yfinance's tolerance ceiling (the 2025 incidents were 100s of req/sec scrapers).

**Defensive normaliser shape:**

```python
def _normalise_news_item(raw: dict) -> dict:
    # Handle both yfinance ≤0.2 (flat) and ≥1.0 (nested content) shapes
    content = raw.get("content", raw)
    title = content.get("title", "")
    summary = content.get("summary", "") or content.get("description", "")
    publisher = (content.get("provider") or {}).get("displayName") \
                or content.get("publisher", "")
    url = (content.get("clickThroughUrl") or content.get("canonicalUrl") or {}).get("url") \
          or content.get("link", "")
    pub_raw = content.get("pubDate") or raw.get("providerPublishTime")
    return {
        "id": content.get("id") or raw.get("uuid") or hashlib.sha256(title.encode()).hexdigest()[:16],
        "title": title,
        "summary": summary[:280],   # bound for display
        "publisher": publisher,
        "url": url,
        "published_at": _coerce_pub_time(pub_raw),
        "is_critical": is_critical(title, summary),
    }
```

---

## First-Run Tour Library — Shepherd.js v14.5.1

### Why Shepherd over Driver.js / Intro.js

| Criterion | Shepherd.js 14.5.1 | Driver.js 1.x | Intro.js 8.x |
|-----------|-------------------|----------------|---------------|
| Last release | 2025/2026 (active) | 2024 | 2024 |
| Bundle size | ~30KB gz (UMD) | ~9KB gz | ~12KB gz |
| Customisation depth | Deep — promise-based step lifecycle, async hooks | Moderate | Shallow |
| Multi-step flow | First-class | First-class | First-class |
| WAI-ARIA | Yes | Yes | Yes |
| License | MIT (v14+) ⚠ verify before ship | MIT | AGPL or commercial |
| CDN-only loadable | Yes (UMD) | Yes | Yes |
| HTMX compatibility | Excellent — tour is a one-time bind on `DOMContentLoaded`, not per-swap | Excellent | Excellent |

**Decision rationale:** The tour will need 6–8 steps explaining (a) the market×function nav, (b) the signal status card with trigger ladder + trailing stop line, (c) the trace panels, (d) the paper-trade ledger, (e) stop-loss alerts, (f) news panel, (g) preferences. Shepherd's promise-based lifecycle hooks (`when: { show: () => ..., hide: () => ... }`) make it trivial to scroll-into-view, focus-trap, and persist completion to `state/users/{user_id}.json::tour_completed_at`. Driver.js can do the same with more manual code; Intro.js's licensing is more restrictive.

**License verification action:** Before merge of v1.3, confirm Shepherd 14.5.1's license in `node_modules/shepherd.js/package.json` (Shepherd was AGPL through some 2024 versions, then relaxed). If still AGPL: **the friends-and-family deployment is private (invite-only, no public distribution), so AGPL §13 network-access copyleft is the only concern**. Mitigations: (1) link to Shepherd's source on the dashboard footer, (2) keep the trading-signals repo private, OR (3) switch to Driver.js (MIT) at a small UX cost.

### CDN loading pattern (drop-in to dashboard.html)

```html
<!-- CSS theme — pinned -->
<link rel="stylesheet"
      href="https://cdn.jsdelivr.net/npm/shepherd.js@14.5.1/dist/css/shepherd.css"
      integrity="sha384-PLACEHOLDER"
      crossorigin="anonymous">

<!-- UMD bundle — pinned -->
<script src="https://cdn.jsdelivr.net/npm/shepherd.js@14.5.1/dist/js/shepherd.min.js"
        integrity="sha384-PLACEHOLDER"
        crossorigin="anonymous"></script>

<script>
  // Bind only on first run for this user
  if (!window.__TOUR_COMPLETED__) {
    const tour = new Shepherd.Tour({
      defaultStepOptions: { cancelIcon: { enabled: true }, scrollTo: true },
      useModalOverlay: true,
    });
    tour.addStep({ id: 'nav', text: '...', attachTo: { element: '.market-tabs', on: 'bottom' } });
    // ... 6-8 steps total
    tour.on('complete', () => fetch('/api/tour/complete', { method: 'POST', headers: {'X-CSRF-Token': window.__CSRF__} }));
    tour.start();
  }
</script>
```

**SRI hash generation:** at build/release time, run `curl -sL <cdn_url> | openssl dgst -sha384 -binary | openssl base64 -A` and paste the result. Match the v1.0-era Chart.js SRI pinning convention exactly.

**`__TOUR_COMPLETED__` flag** is rendered server-side from `users/{user_id}.json::tour_completed_at != null`. After the user finishes, the POST to `/api/tour/complete` writes `tour_completed_at = now()` to that user's state.

---

## Tooltip Pattern — Microtip 0.2.2 (CSS-only)

### Why Microtip wins for HTMX

The dashboard re-swaps panels via `hx-get` whenever the user changes market or function. **JS-driven tooltip libraries (Tippy.js, Floating UI, Popper) need rebinding after every swap** — `tippy('[data-tippy-content]')` must re-run when new DOM appears. Easy to forget. Easy to break.

**Microtip is pure CSS.** `aria-label` + `role="tooltip"` + `data-microtip-position` HTML attributes are read directly by CSS selectors (`[role="tooltip"]:hover::after`). New DOM swapped in by HTMX is styled instantly with zero JS rebind.

### CDN loading pattern

```html
<!-- 1KB CSS — pinned -->
<link rel="stylesheet"
      href="https://cdn.jsdelivr.net/npm/microtip@0.2.2/microtip.min.css"
      integrity="sha384-PLACEHOLDER"
      crossorigin="anonymous">
```

### Usage

```html
<!-- Per-panel inline tooltip -->
<button class="info-icon"
        aria-label="ATR(14) is the average true range over the last 14 trading days, smoothed via Wilder's method."
        data-microtip-position="top"
        data-microtip-size="medium"
        role="tooltip">ⓘ</button>
```

**Accessibility:** Microtip's tooltip text IS the `aria-label`, so it's announced by screen readers natively — no separate `aria-describedby` wiring.

**Trade-off vs richer tooltips:** Microtip's tooltips are text-only — no rich content, no embedded HTML, no images. For the trading-signals dashboard (short factual explanations of indicators / metrics / fields), this is exactly the right ceiling.

---

## Per-User Email — Resend Tier Sanity Check

### Math

- **Per-user emails per day:** 1 (08:00 Sydney daily signal).
- **Plus per-user stop-loss alerts:** 0–2 per day on average (only when state changes from CLEAR→APPROACHING or APPROACHING→HIT).
- **Per-user worst-case daily volume:** ~3 emails/day (1 signal + 2 alerts).
- **At 10 F&F users + admin = 11 inboxes:** 11–33 emails/day = ~330–990 emails/month.
- **At 25 F&F users (stretch) = 26 inboxes:** 26–78 emails/day = ~780–2340 emails/month.

### Resend tier fit

| Tier | Free | Pro ($20/mo as of 2025) |
|------|------|-------------------------|
| Daily cap | 100 emails | 1,000 emails |
| Monthly cap | 3,000 emails | 50,000 emails |
| Rate limit | 2 req/sec (older accounts) or 5 req/sec (newer) | Same |
| **Fit at 11 users** | ✓ Fits comfortably | ✓ Fits |
| **Fit at 25 users** | Tight on daily (78/100 worst case); fine on monthly | ✓ Fits |
| **Fit at 100 users** | ✗ Exceeds daily cap | ✓ Fits (300 emails/day << 1000) |

**Recommendation:** Stay on free tier through v1.3 launch. Upgrade to Pro **only if** F&F user count crosses ~20 active users OR a single day's stop-loss-alert burst exceeds 80 emails.

### Rate-limit handling for fan-out

The 08:00 Sydney run sends N emails sequentially (one per active user). At 2 req/sec the existing `notifier.send_email()` already handles 429s with retry+backoff (verified in v1.0). For N=11 users this is 5.5 seconds of email sending — fine. For N=100 users this is ~50 seconds — still fine; the daily run has a multi-minute budget.

**Defensive pattern:** wrap the per-user email in the existing typed-exception ladder. A failed email for one user does not abort the loop for the other users — log the failure to that user's state file and surface in the next day's email subject (`[!email-failed-yesterday]`).

---

## Schema v9 → v10 Migration Shape

### What v10 introduces

1. **`state/users.json` registry** (new file) — created from scratch with admin as the sole user.
2. **`state/users/admin.json`** (new file) — populated from the existing `state.json` content.
3. **`state/users/{user_id}.json`** (new files) — created lazily as F&F users redeem invites.
4. **`state/invites.json`** (new file) — empty `{invites: []}` array on init.
5. **`state/news_cache.json`** (new file) — empty `{markets: {SPI: null, AUDUSD: null}}` on init; populated on first daily run.
6. **`state/signals/SPI.json` + `state/signals/AUDUSD.json`** (new files) — extracted from admin's existing state's `signals` block.
7. **Old `state.json`** — RENAMED to `state.json.v9-backup` for one milestone, then archived. Existence of the backup is the proof that no data was lost.

### Migration step (`state_manager._migrate_v9_to_v10`)

```python
def _migrate_v9_to_v10(old_state: dict) -> None:
    """One-shot. Idempotent (no-op if state/users/admin.json already exists)."""
    admin_path = Path("state/users/admin.json")
    if admin_path.exists():
        return  # already migrated

    # 1. Create directories
    Path("state/users").mkdir(parents=True, exist_ok=True)
    Path("state/signals").mkdir(parents=True, exist_ok=True)

    # 2. Split shared signals out of admin state
    shared_signals = old_state.pop("signals", {})  # {SPI: {...}, AUDUSD: {...}}
    for market, sig in shared_signals.items():
        _atomic_write_json(Path(f"state/signals/{market}.json"), {
            "schema_version": 10,
            "market": market,
            "signal": sig,
        })

    # 3. Write admin's per-user state (everything except shared signals)
    admin_state = {
        **old_state,
        "schema_version": 10,
        "user_id": "admin",
    }
    _atomic_write_json(admin_path, admin_state)

    # 4. Create registry
    registry = {
        "schema_version": 10,
        "users": [{
            "id": "admin",
            "email": os.environ["TO_EMAIL"],  # existing admin email
            "role": "admin",
            "status": "active",
            "created_at": _isoformat_now(),
            "disabled_at": None,
            "tour_completed_at": _isoformat_now(),  # admin doesn't need the tour
        }],
    }
    _atomic_write_json(Path("state/users.json"), registry)

    # 5. Create empty invites + news cache
    _atomic_write_json(Path("state/invites.json"), {"schema_version": 10, "invites": []})
    _atomic_write_json(Path("state/news_cache.json"), {"schema_version": 10, "markets": {}})

    # 6. Rename old state.json (preserved as backup)
    old_path = Path("state.json")
    if old_path.exists():
        old_path.rename(Path(f"state.json.v9-backup-{_isoformat_now()}"))
```

**Migration-chain contiguity:** the existing v1.2 Phase 27 contiguity assert (`assert _migrations[i].from_v == _migrations[i-1].to_v`) catches any gap if v10 is added without removing or renumbering existing migrations. The new v9→v10 step extends the chain at the tail.

**Decimal money preservation:** the v9 quantize-on-save behaviour applies to the new per-user files identically. `save_user_state()` calls the same `_quantize_money_fields()` helper before the atomic write.

**Naive-datetime fail-closed preservation:** the same `_assert_tz_aware()` write-path guard applies to `users/{user_id}.json`, `users.json`, `invites.json`, `news_cache.json`, and `signals/{market}.json`.

**Test coverage:** new `tests/test_migration_v9_to_v10.py` golden-file test loads a fixture v9 state and asserts byte-equivalence of the resulting v10 file tree. Plus an idempotency test (run migration twice → no change on second run).

---

## Hex-Lite Architecture Preservation

The v1.0 AST blocklist test (`tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent`) walks `signal_engine.py`, `sizing_engine.py`, and `system_params.py` to verify they import none of: `requests`, `yfinance`, `pandas` (as I/O), `state_manager`, `notifier`, `dashboard`, `os`, `pathlib`, `json`.

**v1.3 changes that respect this:**

- All per-user file I/O lives in `state_manager` (existing I/O adapter). ✓
- All RBAC dependency code lives in a new `auth/` package (new I/O adapter). ✓
- All news-fetch code lives in a new `news/` package (new I/O adapter; imports `yfinance`). ✓
- All invite-token code lives in `auth/invites.py` (I/O adapter). ✓
- `signal_engine` / `sizing_engine` / `system_params` get **zero** new imports. ✓

**Action:** extend the AST blocklist test to also assert the new `auth/` and `news/` packages don't backflow into pure-math modules. Specifically: `signal_engine.py` must NOT import `auth.*` or `news.*`. Add to the blocklist set.

---

## Installation Commands

```bash
# Backend — NO new dependencies
# (verify no drift in requirements.txt)
diff <(pip freeze | sort) <(sort requirements.txt)

# Frontend — CDN-only, NO build step, NO npm install
# Just add these lines to dashboard.html with SRI hashes generated at release time:
#   <link href=".../shepherd.js@14.5.1/dist/css/shepherd.css" integrity="...">
#   <script src=".../shepherd.js@14.5.1/dist/js/shepherd.min.js" integrity="..."></script>
#   <link href=".../microtip@0.2.2/microtip.min.css" integrity="...">

# Generate SRI hashes:
curl -sL https://cdn.jsdelivr.net/npm/shepherd.js@14.5.1/dist/js/shepherd.min.js | \
  openssl dgst -sha384 -binary | openssl base64 -A

curl -sL https://cdn.jsdelivr.net/npm/shepherd.js@14.5.1/dist/css/shepherd.css | \
  openssl dgst -sha384 -binary | openssl base64 -A

curl -sL https://cdn.jsdelivr.net/npm/microtip@0.2.2/microtip.min.css | \
  openssl dgst -sha384 -binary | openssl base64 -A
```

---

## Alternatives Considered

| Recommended | Alternative | When alternative would win |
|-------------|-------------|----------------------------|
| Sharded directory + slim registry | Master-file with user keys | Only if N users < 3 forever — but we want to grow F&F to ~10–20 users so contention rules out master-file |
| `secrets.token_urlsafe(32)` | UUIDv4 | UUIDv4 is fine cryptographically but 36 chars vs 43 chars; both URL-safe; `secrets` is more idiomatic for security-sensitive tokens |
| sha256 hash storage | Plaintext token storage | Never — exposed backup leaks all live invites |
| `Depends(require_user)` per route | Middleware-level auth | FastAPI middleware can't depend on path params; per-route `Depends` gives precise scope and is the FastAPI-blessed pattern |
| Daily news cache | Hourly refresh | If the app pivoted to intraday signals — not v1.3 scope |
| Hand-curated keyword critical-event flag | NLP/sentiment library (textblob, vader) | If the news panel becomes load-bearing for trading decisions — but it's context-only in v1.3 |
| Shepherd.js | Driver.js | If Shepherd's license becomes blocking and the F&F deployment is opened beyond invite-only |
| Microtip | Tippy.js | If tooltips need rich HTML content, not just text — not v1.3 scope |
| Resend free tier | Resend Pro ($20/mo) | When F&F count > 20 active users OR alert volume bursts > 80/day |
| Schema v9→v10 inline | Out-of-band migration script | The existing in-process migration chain has worked through 9 versions; v10 fits the same pattern |

---

## What NOT to Use (v1.3-specific)

| Avoid | Why | Use instead |
|-------|-----|-------------|
| Storing plaintext invite tokens in `invites.json` | Backup leak = full invite replay | sha256 hash; show plaintext only at issue + email-send |
| Per-user APScheduler jobs | Overkill for daily fan-out; adds dep + complexity | Loop over registry inside the existing single 08:00 Sydney `schedule` job |
| Tippy.js / Floating UI / Popper for tooltips | Need JS rebind on every HTMX swap | Microtip (pure CSS) |
| Driver.js + Intro.js + Shepherd.js loaded together | Bundle bloat for what is one tour | Pick Shepherd.js, drop the other two from consideration |
| Fetching `Ticker.news` on every dashboard render | Hammers Yahoo unnecessarily; rate-limit risk | Daily fetch in 08:00 Sydney run, cache 24h |
| Trusting yfinance to provide importance metadata | Field doesn't exist in public surface | Hand-curated keyword regex |
| `JWT` for the new user_id session claim | Existing cookie-session works; JWT brings key-rotation cost | Existing cookie session, add `user_id` key |
| One-big-file with all users (Option A above) | Single-writer contention at N>3 | Sharded directory (Option C) |
| Synchronous yfinance fetch in the FastAPI request thread | Could block the event loop on slow Yahoo response | Already-deferred to the daily scheduler — request thread reads cache only |
| Loading Shepherd.js on every page (admin doesn't need it) | Unnecessary bytes for admin who never sees the tour | Conditional `<script>` based on `__TOUR_COMPLETED__` server-side flag |

---

## Stack Patterns by Variant

**If F&F user count stays ≤10 through v1.3 launch (most likely):**
- Single uvicorn worker, single-writer invariant naturally upheld
- Resend free tier sufficient
- Sharded directory layout has trivial perf

**If F&F user count grows to 20–50 over v1.3 lifetime:**
- Still single uvicorn worker (no horizontal scaling needed)
- Upgrade Resend to Pro tier
- Add per-user state file size monitoring (warn if any user file > 1MB — paper-trade ledger growth)

**If user count grows past 100 (v2 territory):**
- Reconsider file-based persistence vs SQLite (would break v1.3 constraint)
- Reconsider sharded directory vs hash-bucketed subdirs (`state/users/ab/abc123.json`) to keep single-dir file-count manageable on ext4

---

## Version Compatibility

| Package A | Compatible with | Notes |
|-----------|-----------------|-------|
| Shepherd.js 14.5.1 | Modern browsers (ES2017+); Safari 14+, Chrome 94+ | Same browser baseline as Chart.js 4.4.6 |
| Shepherd.js 14.5.1 | Microtip 0.2.2 | Independent — no namespace overlap |
| Shepherd.js 14.5.1 | Existing HTMX 1.x | Tour binds on `DOMContentLoaded`, not on swaps — no conflict |
| Microtip 0.2.2 | Existing HTMX 1.x | Pure CSS — survives every swap |
| yfinance 1.2.0 (existing) | Both old and new news shape | Defensive normaliser handles both |
| FastAPI Depends() | Existing cookie session | `request.session.get("user_id")` — no FastAPI version constraint |
| `secrets.token_urlsafe()` | Python 3.11.8 | stdlib; stable since 3.6 |

**Known gotchas to avoid:**
- Shepherd license: re-verify at install time; switch to Driver.js if AGPL terms become incompatible with intended deployment.
- yfinance news shape: yfinance 0.x and 1.x have different shapes; **always normalise**, never assume.
- Microtip tooltip text length: keep under ~120 chars. Long text wraps badly. For longer help, use a `details/summary` block instead.
- HTMX swap + Shepherd modal: if the tour is in progress and an HTMX swap fires, the swap target may be inside the Shepherd overlay. Dismiss the tour before triggering swaps, or scope the tour to elements that don't get swapped during it.

---

## Sources

- [yfinance Ticker.news API reference](https://ranaroussi.github.io/yfinance/reference/api/yfinance.Ticker.news.html) — confirmed `Ticker.news` exists; importance hint not documented. HIGH confidence.
- [yfinance source — ticker.py / scrapers](https://github.com/ranaroussi/yfinance/blob/main/yfinance/ticker.py) — verified the news shape change in 1.x. HIGH confidence.
- [yfinance issue #1956 — get_news returns unrelated news](https://github.com/ranaroussi/yfinance/issues/1956) — confirms news fidelity is best-effort, justifying critical-event keyword filter as a per-app safeguard. HIGH confidence.
- [Shepherd.js npm package + jsDelivr](https://www.jsdelivr.com/package/npm/shepherd.js) — confirmed v14.5.1 (latest stable 14.x) with v15.2.2 also available. HIGH confidence.
- [Shepherd.js installation docs](https://docs.shepherdjs.dev/guides/install/) — verified UMD CDN pattern. HIGH confidence.
- [Shepherd.js GitHub releases](https://github.com/shipshapecode/shepherd/releases) — verified active maintenance through 2025/2026. HIGH confidence.
- [Driver.js docs](https://driverjs.com/docs/installation) — confirmed permissive license + CDN pattern (alternative path). HIGH confidence.
- [Open-source product tour comparison 2026 — Userorbit](https://userorbit.com/blog/best-open-source-product-tour-libraries) — informed Shepherd-vs-Driver-vs-Intro decision. MEDIUM confidence (vendor blog).
- [Inline Manual: Driver.js vs Intro.js vs Shepherd.js](https://inlinemanual.com/blog/driverjs-vs-introjs-vs-shepherdjs-vs-reactour/) — independent comparison; informed bundle-size + license deltas. MEDIUM confidence.
- [Microtip GitHub](https://github.com/ghosh/microtip) — confirmed 1KB pure-CSS, MIT license, `aria-label`+`role="tooltip"` API. HIGH confidence.
- [Microtip docs](https://ghosh.github.io/microtip/) — verified positioning attributes + accessibility claims. HIGH confidence.
- [Resend account quotas + limits](https://resend.com/docs/knowledge-base/account-quotas-and-limits) — free 100/day, 3000/mo; confirmed tier fit. HIGH confidence.
- [Resend API rate limit changelog](https://resend.com/changelog/api-rate-limit) — confirmed 2 req/sec default for older accounts, 5 req/sec for newer. HIGH confidence.
- [Resend pricing 2025](https://resend.com/pricing) — Pro tier limits at $20/mo. HIGH confidence.
- [FastAPI dependency-injection RBAC pattern — Permit.io](https://www.permit.io/blog/fastapi-rbac-full-implementation-tutorial) — confirms `Depends(require_role)` is the canonical FastAPI pattern. MEDIUM confidence (vendor blog).
- [FastAPI multi-tenancy class-based pattern — Sayanc](https://sayanc20002.medium.com/fastapi-multi-tenancy-bf7c387d07b0) — informed the per-user dependency-chain shape. LOW-MEDIUM confidence (Medium article; cross-checked with FastAPI docs).
- [Python `secrets` module docs](https://docs.python.org/3/library/secrets.html) — confirmed `token_urlsafe(32)` produces 256 bits of entropy. HIGH confidence.
- v1.0 archive STACK.md (`.planning/research/v1.0-archive/STACK.md`) — confirmed the existing stack baseline that v1.3 extends. HIGH confidence (project-internal).
- v1.0/v1.1/v1.2 PROJECT.md + MILESTONES.md (`.planning/`) — confirmed schema v9, hex-lite blocklist, single-writer invariant, atomic-write helper, Decimal money quantize-on-save, naive-datetime fail-closed. HIGH confidence (project-internal).

---

*Stack research delta for: v1.3 Multi-Tenant Friends & Family additions to existing trading-signals app*
*Researched: 2026-05-10*
*See `.planning/research/v1.0-archive/STACK.md` for the unchanged base stack.*
