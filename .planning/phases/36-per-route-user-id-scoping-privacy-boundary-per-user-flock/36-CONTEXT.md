# Phase 36: Per-Route User-ID Scoping + Privacy Boundary + Per-User Flock - Context

**Gathered:** 2026-05-13
**Status:** Ready for planning

<domain>
## Phase Boundary

Thread `uid` through every per-user HTMX route (paper_trades, trades, alerts, journal, equity reads) via `current_user_id` Depends; introduce `mutate_user_state(uid, mutator)` with per-user `fcntl.flock` serializing fan-out vs HTMX writes; add `load_user_state(uid)` as the canonical per-user read helper; install `PublicUserSummary` Pydantic model + admin `/admin/users` route; light up `TestTenantIsolation` as the milestone-wide quality gate. Admin remains the only real user — observable behaviour is identical at this phase boundary.

</domain>

<decisions>
## Implementation Decisions

### mutate_user_state API shape

- **D-01:** `mutate_user_state(uid: str, fn: Callable[[dict], Any]) -> dict` — fn receives the **full state dict** (same shape as `mutate_state`). The wrapper acquires `fcntl.flock(state/users/{uid}.lock, LOCK_EX)` as an OUTER lock, then delegates to `mutate_state(fn)` which acquires its own `flock(state.json, LOCK_EX)`. Two distinct lock files — no intra-process reentrancy issue.

- **D-02:** `mutate_user_state` lives in `state_manager/__init__.py` and is re-exported alongside `mutate_state`, `load_state`, `save_state`. Callers: `from state_manager import mutate_user_state`.

- **D-03:** The `state/users/` directory is auto-created by `mutate_user_state` on first call (`state/users/` is gitignored per Phase 33). The lock file `state/users/{uid}.lock` is opened with `open(lock_path, 'a+')` to create-if-absent before `fcntl.flock`.

- **D-04:** Per-user flock purpose: serializes daily fan-out writes (Phase 37) vs concurrent HTMX writes for the **same user**. Cross-user writes are serialized by the inner `state.json` flock in `mutate_state` regardless.

### Centralized loaders

- **D-05:** `load_user_state(uid: str, path: Path = Path(STATE_FILE)) -> dict` — returns `load_state(path)["users"][uid]`. Re-exported from `state_manager/__init__.py`. Routes destructure what they need from the returned user slice. No per-domain loaders.

- **D-06:** Read paths that only need signals (shared) keep calling `load_state()` directly — they do NOT go through `load_user_state`. Only per-user data reads use `load_user_state`.

### PublicUserSummary and admin route

- **D-07:** `PublicUserSummary` is a Pydantic `BaseModel` with fields: `user_id: str`, `display_name: str`, `status: str` (`"active"` or `"disabled"`), `last_seen_date: str | None`, `has_active_position: bool`. Lives in `web/routes/admin/_models.py` — follows the `trades/_models.py` pattern.

- **D-08:** `display_name = user["email"]` — no schema change. Admin-only view; admin issued every invite so already knows the email. No derivation function needed.

- **D-09:** `status` is derived: `"disabled"` if `user.get("disabled")` else `"active"`.

- **D-10:** `has_active_position` is derived from the user's state slice: `bool(load_user_state(uid).get("current_position"))` or equivalent field.

- **D-11:** `GET /admin/users` returns `response_model=list[PublicUserSummary]`. FastAPI's response model serialization enforces redaction automatically — no trade content can leak through.

### RedactStateFilter scope

- **D-12:** Phase 36 uses **FastAPI `response_model` only** on the admin route. No standalone `redact()` utility. `TestTenantIsolation` SC-2 fan-out/crash-email assertions are green by default (fan-out doesn't exist yet; `crash_boundary.py` doesn't log per-user trade content today). Explicit filter for crash-email/logs deferred to Phase 37.

### TestTenantIsolation quality gate

- **D-13:** `TestTenantIsolation` test class introduced in `tests/test_web_admin.py` (or `tests/test_tenant_isolation.py`). Fixture: create user A with 5 paper trades; assert zero `(entry_price|n_contracts|"direction":\s*"(LONG|SHORT)")` matches in: (a) admin `/admin/users` response HTML/JSON; (b) user B's served dashboard; (c) crash-email body simulation. Fan-out log check is stubbed/skipped until Phase 37.

- **D-14:** Every entity-ID route (paper-trade close, trade modify, journal patch, alert ack) gets a paired `test_<route>_returns_404_for_other_users_entity` test: create user A's row, authenticate as user B, assert 404. Added to existing test files (`test_web_paper_trades.py`, `test_web_trades.py`) to keep file count down.

### Claude's Discretion

- Exact field name for "active position" check in `has_active_position` (`current_position`, `open_position`, or similar — read `state_manager/migrations.py` v12 output shape to confirm).
- Whether `TestTenantIsolation` goes in `test_web_admin.py` or a new `test_tenant_isolation.py`.
- Whether `mutate_user_state` returns the full mutated state dict (like `mutate_state`) or just the user sub-dict — either is consistent since fn operates on full state.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase goal + requirements
- `.planning/ROADMAP.md` — Phase 36 goal, success criteria, §Phase 36 (all 4 SCs); §Key context (privacy gate, flock, `TestTenantIsolation`, AST hex boundary)
- `.planning/REQUIREMENTS.md` — TENANT-02 (per-user route scoping), TENANT-03 (privacy boundary), RBAC-04 (admin user-list — PublicUserSummary fields)

### State manager (mutate_user_state + load_user_state live here)
- `state_manager/__init__.py` — public API; `mutate_state` pattern to mirror for `mutate_user_state`; `load_state` pattern for `load_user_state`
- `state_manager/io.py` — `_atomic_write` flock pattern (lines 182–199); intra-process reentrancy note (lines 11–16); `_save_state_unlocked` (line 233+); `mutate_user_state` outer flock must follow same lock-acquire/release discipline
- `state_manager/migrations.py` — `_migrate_v11_to_v12` (line 360+): confirms `state["users"][uid]` sub-dict shape; `_ADMIN_UID` constant

### Web dependencies + admin router (already landed from Phase 35)
- `web/dependencies.py` — `current_user_id()` and `require_admin()` Depends factories; all per-user routes declare `user_id: str = Depends(current_user_id)`
- `web/routes/admin/__init__.py` — existing admin router; `GET /admin/users` registers here (Phase 36 adds it)
- `web/app.py` — `create_app()` router registration order; admin router already mounted

### Routes being migrated (read fully before editing)
- `web/routes/paper_trades/__init__.py` — calls `mutate_state`; Phase 36 migrates to `mutate_user_state`
- `web/routes/trades/__init__.py` — calls `mutate_state`; Phase 36 migrates to `mutate_user_state`
- `web/routes/markets.py` — reads signals (shared); keeps `load_state()`, does NOT migrate to `load_user_state`

### Admin models (new file, Phase 36)
- `web/routes/admin/_models.py` — `PublicUserSummary` Pydantic model (to be created); follows `web/routes/trades/_models.py` pattern

### Prior phase decisions
- `.planning/phases/35-cookie-depends-current-user-sub-router-admin-gate/35-CONTEXT.md` — D-01..D-10: `current_user_id` Depends, session payload `{u, uid, iat}`, shim location, admin router structure
- `.planning/phases/34-user-registry-invite-token-storage/34-CONTEXT.md` — D-05/D-06: User TypedDict fields (`uid, email, role, created_at, disabled`); uid = `uuid4().hex`
- `.planning/phases/33-schema-migration-v11-v12-admin-namespace-backup-gitignore/PATTERNS.md` — if exists: `state/users/` gitignore, `state["users"][uid]` structure

### Hex boundary guard
- `tests/test_web_healthz.py::TestWebHexBoundary` — AST guard must remain green; `state_manager` exports new functions but stays I/O hex (no web imports)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `state_manager/__init__.py::mutate_state(fn)` — exact pattern for `mutate_user_state`; outer flock on `state/users/{uid}.lock` wraps a `mutate_state(fn)` call
- `state_manager/io.py::_atomic_write` — flock acquire/release pattern (lock destination fd, release before `os.replace`); `mutate_user_state` outer flock uses same discipline on `state/users/{uid}.lock`
- `web/dependencies.py::current_user_id` — already wired; routes add `user_id: str = Depends(current_user_id)` to function signature; Phase 35 confirmed this compiles without breaking existing routes
- `web/routes/trades/_models.py` — Pydantic model file pattern; `PublicUserSummary` follows identical module placement as `web/routes/admin/_models.py`
- `auth_store/_users.py::get_user(uid)` — used by `require_admin`; `GET /admin/users` calls `list_users()` from auth_store then hydrates with `load_user_state(uid)` per user for `has_active_position`

### Established Patterns
- `mutate_state(_apply)` closure pattern (all HTMX write routes): `def _apply(state): ...; mutate_state(_apply)` — Phase 36 renames call to `mutate_user_state(user_id, _apply)` with identical `_apply` body
- `state/users/` gitignore from Phase 33 — `state/users/{uid}.lock` is a runtime sidecar; never committed
- POSIX flock intra-process reentrancy: `mutate_state` holds its own outer flock on `state.json`; per-user flock on `state/users/{uid}.lock` is a DIFFERENT fd — no deadlock

### Integration Points
- `web/routes/paper_trades/__init__.py` — 5 entity-ID routes: open, close, modify; each needs `user_id: str = Depends(current_user_id)` param + `mutate_user_state(user_id, _apply)` call
- `web/routes/trades/__init__.py` — trade-record routes; same migration pattern
- `web/routes/admin/__init__.py` — add `GET /admin/users` returning `list[PublicUserSummary]`; sources: `list_users()` from auth_store + `load_user_state(uid)` per user for position check
- `tests/test_web_paper_trades.py` + `tests/test_web_trades.py` — add 404-for-other-users paired tests here (D-14)

</code_context>

<specifics>
## Specific Ideas

- `mutate_user_state` is explicitly a **thin wrapper** — the full state dict goes to fn unchanged. This keeps migration mechanical: rename `mutate_state(_apply)` → `mutate_user_state(user_id, _apply)` everywhere, no _apply body changes required.
- `display_name = user["email"]` — one-liner, no transformation. Admin-only, admin knows all emails. Most eloquent: zero indirection.
- FastAPI `response_model` handles `PublicUserSummary` redaction automatically — no custom serializer needed. Trade content fields simply don't appear on the model, so FastAPI strips them from the response.

</specifics>

<deferred>
## Deferred Ideas

- Standalone `redact_user_state_for_public(user_state)` filter function — deferred to Phase 37 when crash-email per-user path lands and needs explicit redaction.
- Fan-out log line redaction — deferred to Phase 37 (`per_user_fanout.py` orchestrator seam).
- `display_name` as a stored User field — deferred; if F&F users want custom display names, Phase 37 invite-acceptance flow can add the field.
- Per-domain loaders (`load_paper_trades_for_user`, etc.) — not needed; single `load_user_state(uid)` is sufficient.

</deferred>

---

*Phase: 36-per-route-user-id-scoping-privacy-boundary-per-user-flock*
*Context gathered: 2026-05-13*
