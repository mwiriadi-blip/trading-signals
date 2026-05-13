# Phase 36: Per-Route User-ID Scoping + Privacy Boundary + Per-User Flock - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-13
**Phase:** 36-per-route-user-id-scoping-privacy-boundary-per-user-flock
**Areas discussed:** mutate_user_state API, Centralized loaders, display_name source, RedactStateFilter scope

---

## mutate_user_state API

| Option | Description | Selected |
|--------|-------------|----------|
| Full state dict | fn(state) — fn navigates state["users"][uid] itself. Thin wrapper: mutate_user_state acquires per-user flock then delegates to mutate_state(fn). Zero friction migrating existing closures. | ✓ |
| Scoped user sub-dict | fn(user_state) — wrapper extracts state["users"][uid], passes it to fn, writes back. Safer against cross-user writes. Requires refactoring every existing _apply closure. | |
| You decide | Claude picks based on migration cost and consistency with mutate_state. | |

**User's choice:** Full state dict (Recommended)
**Notes:** Keeps migration mechanical — rename mutate_state(_apply) → mutate_user_state(user_id, _apply) everywhere without touching _apply bodies.

---

## Centralized loaders

| Option | Description | Selected |
|--------|-------------|----------|
| Single load_user_state(uid) | Returns state["users"][uid] slice. Routes destructure what they need. Consistent with load_state() pattern. | ✓ |
| Per-domain loaders | load_paper_trades_for_user(uid), load_alerts_for_user(uid), etc. More explicit API per data type. | |
| You decide | Claude picks based on existing patterns. | |

**User's choice:** Single load_user_state(uid) (Recommended)

**Follow-up — where does load_user_state live?**

| Option | Description | Selected |
|--------|-------------|----------|
| state_manager/__init__.py | Re-exported alongside load_state(), save_state(), mutate_state(). One import location. | ✓ |
| state_manager/io.py | Closer to I/O kernel; __init__.py still re-exports it. Minor difference. | |

**User's choice:** state_manager/__init__.py (Recommended)

---

## display_name source

| Option | Description | Selected |
|--------|-------------|----------|
| email directly (Most eloquent) | display_name = user["email"]. No transformation, no schema change. Admin-only. | ✓ |
| email.split('@')[0] | Strips domain. No schema change. | |
| Add display_name to User record | Extend User TypedDict + default-fill in load_auth migration. | |

**User's choice:** email directly (Most eloquent)
**Notes:** User asked "What is the eloquent way?" — Claude assessed email directly as most eloquent: zero indirection, single-line assignment, no derivation function, no schema change. Admin-only view, admin already knows every email.

---

## RedactStateFilter scope

| Option | Description | Selected |
|--------|-------------|----------|
| Admin route only — FastAPI response_model | response_model=list[PublicUserSummary] handles admin HTML. SC-2 fan-out/crash-email checks green by default. Defer broader filter to Phase 37. | ✓ |
| Also add explicit redact() util now | Standalone function for crash-email + future log checks. Phase 37 has a ready hook. | |
| You decide | Claude picks based on TestTenantIsolation SC-2 requirements. | |

**User's choice:** Admin route only — FastAPI response_model (Recommended)

**Follow-up — PublicUserSummary model location:**

| Option | Description | Selected |
|--------|-------------|----------|
| web/routes/admin/_models.py | Adjacent to admin router. Follows trades/_models.py pattern. | ✓ |
| auth_store/_users.py | Closer to User TypedDict but mixes web concerns into auth_store. | |
| web/dependencies.py | Inconsistent — mixing Pydantic response models with Depends factories. | |

**User's choice:** web/routes/admin/_models.py (Recommended)

---

## Claude's Discretion

- Exact field name for `has_active_position` check in user state slice
- Whether `TestTenantIsolation` goes in `test_web_admin.py` or new `test_tenant_isolation.py`
- Whether `mutate_user_state` returns full mutated state dict or user sub-dict

## Deferred Ideas

- Standalone `redact_user_state_for_public()` filter function — Phase 37 (crash-email per-user path)
- Fan-out log line redaction — Phase 37 (`per_user_fanout.py`)
- `display_name` as stored User field — Phase 37 invite-acceptance flow
- Per-domain loaders — not needed given single `load_user_state(uid)` decision
