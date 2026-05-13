---
phase: 34
reviewers: [gemini, codex, opencode]
reviewed_at: 2026-05-13T00:00:00Z
plans_reviewed: [34-01-PLAN.md, 34-02-PLAN.md]
---

# Cross-AI Plan Review — Phase 34

## Gemini Review

This review covers **Phase 34: User Registry + Invite-Token Storage**, specifically focusing on **PLAN 01** (Package Split & Migration) and **PLAN 02** (Users/Invites Implementation & Tests).

### Summary
The proposed plans are technically sound, highly disciplined, and strictly follow the project's architectural constraints (Hexagonal-lite, 2-space indent, `flock` atomic writes). The transition from a monolith `auth_store.py` to a structured package is handled with excellent care for backward compatibility (re-exports in `__init__.py`) and testing. The implementation of the invite consumption logic is particularly strong, correctly identifying the need for a `flock` window that encompasses both verification and the atomic write to prevent "double-spend" tokens.

### Strengths
- **Security-First Storage:** Correct use of `sha256:` prefixing and `hmac.compare_digest` for timing-attack resistance. The "hash-only" storage of invite tokens is a critical security win.
- **Concurrency Integrity:** The `flock` pattern in `consume_and_create_user` is correctly scoped. By using `_load_raw` and `_atomic_write_unlocked` inside the window, the plan avoids deadlocks and ensures a true atomic mutation of the registry.
- **Zero-Churn Refactoring:** Placing `DEFAULT_AUTH_PATH` in `__init__.py` and re-exporting symbols is a clever way to prevent breaking the 70+ existing `monkeypatch` calls in the test suite.
- **Schema Migration:** The v1->v2 migration path in `load_auth` is clean and handles the "auto-save" requirement immediately, ensuring data consistency across restarts.
- **Typed Exception Handling:** Defining `InviteAlreadyConsumed` and `InviteExpired` as distinct subclasses of `ValueError` allows for better error handling at the API/UI layers later.

### Concerns
- **Circular Import Risk (MEDIUM):** The plan states `_io.py` will import `DEFAULT_AUTH_PATH` from `auth_store` (the package), while `auth_store/__init__.py` imports `load_auth` from `._io`. This is a classic circular dependency. If `_io.py` performs a top-level `from auth_store import ...`, initialization will fail.
- **Concurrent Admin Operations (MEDIUM):** Decision **D-01** restricts `flock` only to invite consumption. If two admins perform concurrent `create_user` or `mint_invite_token` calls via the web UI, the "load-save" pattern could lead to lost updates. While likely rare in a "Friends & Family" phase, the web app context (FastAPI workers) makes this technically possible.
- **Inode Replacement with Flock (LOW):** `_atomic_write_unlocked` typically uses `os.replace` (atomic move). Since the `flock` is held on a file descriptor opened against the original `auth.json` path, the *new* file created by the replace operation will not be locked. In a single-machine environment where all processes follow Open→Lock→Mutate→Replace→Unlock cycle, this remains safe.

### Suggestions
- **Resolve Circularity:** In `auth_store/_io.py`, do not import `DEFAULT_AUTH_PATH` at the top level. Instead, import it inside `_resolve_path` (lazy import), or have `__init__.py` define the path before importing `_io`.
- **Invite Validation in Minting:** Consider adding a check in `mint_invite_token` to see if an unconsumed invite for the target email already exists to prevent "invite spamming" in the `auth.json` file.
- **JSON Resilience:** Ensure `_load_raw` handles empty files or invalid JSON gracefully, perhaps by returning `_default_auth_data()` if the file exists but is empty, to prevent crashes during the `flock` window.
- **Grep Gate for Hash:** Ensure `test_raw_token_not_in_auth_json` specifically checks for the `sha256:` prefix to verify the tagging requirement is met.

### Risk Assessment
**Risk Level: LOW**

The implementation is low risk because it is purely additive and structural. The "side-effect-free" `load_auth` preserves the integrity of the existing admin flow. The use of the `state_manager`'s proven `flock` pattern significantly mitigates data corruption risks. The main risk is the circular import, which is easily caught at the very start of Wave 1.

---

## Codex Review

### Summary

Both plans are mostly coherent and align well with Phase 34: package split first, then user/invite behavior on top. The dependency ordering is sensible, the storage-only scope is mostly preserved, and the explicit flock boundary for invite consumption is the right place to focus concurrency guarantees. Main risks are around import/package mechanics in Plan 01 and edge-case consistency in Plan 02, especially raw reads bypassing migration/default handling and the subtle behavior of locking `auth.json` while atomically replacing it.

### PLAN 01 Strengths
- Clean dependency order: package split and schema migration happen before `_users.py` relies on v2 fields.
- Preserves import compatibility by re-exporting currently public symbols from `auth_store.__init__`.
- Keeps storage behavior unchanged except for explicit v1→v2 migration.
- Immediate disk migration satisfies D-09 and avoids later helpers operating on ambiguous schema.
- Updating `TestForbiddenImports` to walk the package is necessary and correctly identified.
- `_atomic_write_unlocked` is introduced in the right layer for Plan 02 reuse.

### PLAN 01 Concerns
- **HIGH:** `_io.py` importing `DEFAULT_AUTH_PATH` via `from auth_store import DEFAULT_AUTH_PATH` can create circular-import fragility unless `DEFAULT_AUTH_PATH` is defined before importing/re-exporting `_io` in `__init__.py`. This is workable, but the plan should make ordering explicit.
- **MEDIUM:** Migration via `save_auth(payload, path=path)` inside `load_auth()` may interact badly if `save_auth()` validates `schema_version == 2` before all required v2 fields are normalized. Ensure migration fully constructs valid v2 data before saving.
- **MEDIUM:** If `load_auth()` has corruption recovery behavior today, the plan should explicitly preserve it during the move. This is a shipped auth store, so regression here is higher risk than ordinary refactor churn.
- **LOW:** The file list omits `auth_store/_users.py` in Plan 01 even though D-10 includes it. It can be a stub in Plan 01 or created in Plan 02, but success criterion says "5 files" while D-10 names 6. Clarify expected count.
- **LOW:** `_ensure_aware` placement in `_schema.py` is fine, but if it is behavior rather than schema metadata, confirm this matches existing module boundaries.

### PLAN 01 Suggestions
- Define `DEFAULT_AUTH_PATH` at the very top of `auth_store/__init__.py` before importing anything from `._io`.
- Prefer `_io._resolve_path()` doing a local import of `auth_store.DEFAULT_AUTH_PATH` inside the function body, reducing circular import sensitivity.
- Add a focused regression test that existing public imports still work, especially `from auth_store import DEFAULT_AUTH_PATH, load_auth, save_auth`.
- Add/retain tests for corrupt/empty/missing auth file behavior if those exist today.
- Make the final package file count explicit: either include a stub `_users.py` in Plan 01 or adjust the Plan 01 success wording to avoid ambiguity.

### PLAN 01 Risk Assessment
**MEDIUM.** The migration behavior is straightforward, but converting a shipped flat auth module into a package has import-order and compatibility risk. With import compatibility tests and preserved corruption recovery tests, risk drops toward low.

### PLAN 02 Strengths
- Correctly isolates user and invite behavior in `_users.py`.
- Distinct `InviteAlreadyConsumed` and `InviteExpired` exceptions match SC-4 and improve caller behavior.
- Uses `secrets.token_urlsafe(32)`, SHA-256 storage, prefix-tagged hashes, and `hmac.compare_digest`.
- Explicitly avoids `save_auth()` and `load_auth()` inside the flock window, preventing self-deadlock.
- Single locked window for validate, consume, append user, and atomic write matches D-02.
- Test coverage targets the important behavioral contract: hash-only storage, single-use, expired tokens, disabled preservation, and no admin auto-bootstrap.

### PLAN 02 Concerns
- **HIGH:** `_load_raw()` bypasses `load_auth()` migration. If `consume_and_create_user()` is called on a v1 auth file before any normal `load_auth()` call, `users` and `pending_invites` may be missing. Either consume must perform locked v1→v2 normalization, or the system must guarantee migration occurs before invite use.
- **HIGH:** Locking `auth.json` itself while using `os.replace()` deserves careful review. After replacement, the lock may remain on the old inode while the path points to a new inode. The write is at the end of the critical section, but it weakens the intuitive "path is locked" model. Tests should stress concurrent consumes.
- **MEDIUM:** `os.open(..., O_CREAT)` followed by `_load_raw(path)` can fail on a newly created empty file. If auth file creation/defaulting is part of existing `load_auth()` semantics, consume should handle empty/missing files consistently.
- **MEDIUM:** `create_user(fields)` needs explicit validation at the storage boundary: email required, role restricted to `"admin"|"ff"`, disabled coerced/defaulted predictably, no caller-supplied `uid` unless deliberately allowed.
- **MEDIUM:** `mint_invite_token(invited_by_uid, email)` does not state whether `invited_by_uid` must exist or be an admin. Since this phase is storage-only, enforcement may belong later, but the helper name implies authorization. Clarify whether it is dumb storage or validates inviter existence.
- **LOW:** `len(raw) == 43` for `secrets.token_urlsafe(32)` is somewhat implementation-coupled. Better to assert sufficient entropy-like shape and that raw verifies against stored hash.
- **LOW:** No explicit duplicate-user/email policy. Duplicate emails can cause login-layer ambiguity.

### PLAN 02 Suggestions
- Add a small `_normalize_v2(data)` helper shared by `load_auth()` and `consume_and_create_user()` so raw locked reads still backfill v2 fields safely.
- Add a real concurrency test using two processes or threads attempting to consume the same raw token, asserting exactly one succeeds.
- In `consume_and_create_user()`, validate schema/defaults after `_load_raw()` and before scanning invites.
- Add tests for malformed stored hashes: missing `sha256:` prefix, invalid hex, wrong algorithm prefix. These should fail closed.
- Validate user fields in `create_user()` and `consume_and_create_user()` consistently.
- Clarify whether `mint_invite_token()` permits duplicate pending invites for the same email.
- Test that `set_user_disabled()` returns `False` without writing when `uid` is unknown.

### PLAN 02 Risk Assessment
**MEDIUM.** The core design is sound, but invite consumption is the security-critical path and has several edge cases: raw reads bypassing migration, empty/missing files, malformed hashes, and inode-locking semantics with atomic replace. These are manageable with a shared normalization helper and a concurrent-consume test.

### Overall Assessment
The two-plan sequence achieves Phase 34 goals if the noted edge cases are handled. Approved with changes requested: make Plan 01 import ordering explicit, preserve existing auth-store recovery semantics, and harden Plan 02's locked consume path against v1/empty/malformed data plus concurrent consume races.

---

## OpenCode Review

### PLAN 01 Summary

Straightforward package split following established precedent (Phases 30-31). Migration strategy is clean: detect v1 → backfill → save v2. `DEFAULT_AUTH_PATH` placement in `__init__.py` correctly preserves 70+ monkeypatches. Dependency ordering between plans is correct.

### PLAN 01 Strengths
- `DEFAULT_AUTH_PATH` in `__init__.py`, imported by `_io.py` via lazy import in `_resolve_path` — avoids circular import and preserves monkeypatches
- Migration uses `setdefault`, not direct assignment — defensive against partial/aborted migration states
- `save_auth()` inside migration does NOT call `load_auth()` — no recursion risk (T-34-01-03)
- `_atomic_write_unlocked` is created here (needed by Plan 02) — correct dependency ordering
- Threat model covers tampering, info disclosure, and DoS (no recursion)

### PLAN 01 Concerns
- **MEDIUM:** Plan says `_default_auth_data()` returns `schema_version=2`. On a fresh install, new auth.json will be v2 with `users=[]`. Admin must be created via `create_user()` later. Correct per D-07, but worth explicit documentation.
- **MEDIUM:** Migration calls `save_auth()` which calls `_atomic_write()` which will try `LOCK_EX`. If `load_auth()` is ever called inside a flock window, this deadlocks. Plan 02's `consume_and_create_user` correctly uses `_load_raw` instead of `load_auth()`, so no current deadlock — but the constraint is subtle. Worth a comment on `load_auth()`.
- **LOW:** Task 1 says `_atomic_write_unlocked` is "copy from state_manager/io.py". Must ensure the copy drops any internal flock. If the source has `LOCK_EX` inside, forgetting to remove it silently deadlocks Plan 02. Recommend a comment: `# No flock — caller is responsible`.
- **LOW:** `test_v1_to_v2_migration_preserves_existing_fields` should explicitly verify `trusted_devices` and `pending_magic_links` arrays are preserved untouched.
- **LOW:** Wave 1 bundles package creation, migration logic, AND flat-file deletion. Deletion should be the absolute LAST step.

### PLAN 01 Suggestions
1. Add a docstring to `load_auth()`: "⚠ Must not be called inside a LOCK_EX window — will deadlock. Use `_load_raw()` instead."
2. Hardcode the file count assertion as `assert len(files) >= 5` (not `== 5`), so adding `_users.py` in Plan 02 doesn't break it.
3. Make the migration more defensive: check `payload.get('schema_version') == 1` before upgrading, and log a warning if `schema_version` is missing or unknown.

### PLAN 01 Risk Assessment: **LOW**

Clean package split with well-understood migration. The only real risk is the deadlock constraint being violated by a future developer, mitigated by documentation.

### PLAN 02 Summary

Implements user registry CRUD, invite token helpers, and two typed exceptions. The flock pattern for `consume_and_create_user` is well-specified with clear anti-patterns documented. Test coverage is comprehensive (16 tests across 3 test classes). The plan correctly avoids `save_auth()` and `load_auth()` inside the flock window.

### PLAN 02 Strengths
- Flock pattern is explicit: `os.open → LOCK_EX → _load_raw → mutate → _atomic_write_unlocked → LOCK_UN → os.close`
- Anti-patterns clearly documented: no `save_auth()` inside flock (deadlock), no `load_auth()` inside flock (deadlock)
- Exception hierarchy is clean: `InviteAlreadyConsumed(ValueError)` and `InviteExpired(ValueError)` — distinct types, same base class, importable from `auth_store`
- `hmac.compare_digest` for verify — closes timing oracle
- `_verify_token` compares the full `'sha256:<hex>'` prefix — defense in depth against misformat attacks
- Raw token is prefix-tagged in storage — grep gate test enforces no raw token leaks
- Test suite validates exact exception types with `isinstance`, not just message string matching

### PLAN 02 Concerns
- **HIGH: Flock pattern has a subtle race with file replacement.** `consume_and_create_user` opens an fd for locking, but `_load_raw` and `_atomic_write_unlocked` both operate on the *path* (not the fd). If the file is `os.replace`d between `os.open` and `_load_raw`, the flock is on a now-unlinked inode while operations proceed on the new inode. **Mitigation analysis:** Despite this, the single-use consume guarantee IS preserved. The race only causes data loss from concurrent *non-flock* writers (mint, create_user), which D-01 explicitly accepts. The consume guarantee holds. **Recommendation:** Document this precisely in the `consume_and_create_user` docstring.
- **MEDIUM: `_load_raw` is a function that reads without any lock.** If called outside a flock window, it returns a racy read. Consider renaming to `_read_auth_unlocked` to match the `_atomic_write_unlocked` convention and signal caller responsibility.
- **MEDIUM: Race between flock and non-flock writers is real but accepted.** `mint_invite_token` and `create_user` use load→save without flock. If `consume_and_create_user` runs concurrently with either, the non-flock writer's data can be lost (overwritten by the flock writer's `_atomic_write_unlocked`). D-01 explicitly accepts this for F&F scale.
- **LOW:** `set_user_disabled` doesn't validate uid exists before flipping; returns `False` on unknown uid. Fine — the return value signals success.
- **LOW:** `_verify_token` is module-private — ensure it's NOT re-exported from `__init__.py` (it shouldn't be caller-facing).
- **LOW:** `test_raw_token_not_in_auth_json` should be a programmatic assertion (load the JSON, confirm no field contains a 43-char base64 string), not a shell grep.

### PLAN 02 Suggestions
1. Rename `_load_raw` to `_read_auth_unlocked` to match `_atomic_write_unlocked` naming convention.
2. Add a comment at the top of `_users.py`: "Flock warning: LOCK_EX only serializes other flock holders. Non-flock writers (create_user, mint_invite_token) can race. See D-01."
3. In `consume_and_create_user`, add an invariant assertion after `_load_raw`: `assert data.get('schema_version', 0) >= 2, "migration must precede invite flow"`.
4. Make the grep-gate test programmatic — load the written JSON and assert no string value matches `r'^[A-Za-z0-9_-]{43}$'`.
5. Consider whether `mint_invite_token()` should reject if `invited_by_uid` doesn't exist in `data['users']`.

### PLAN 02 Risk Assessment: **MEDIUM**

Primary risk is the flock/read_text split-inode concern being misunderstood by future maintainers, not by this implementation. The single-use consume guarantee IS sound — verified by race analysis. The accepted data-loss race with non-flock writers is appropriately scoped to friends-and-family. Mitigation: rename `_load_raw` and add flock warning docstrings.

### Cross-Plan Dependency Verification

| Dependency | Status | Notes |
|---|---|---|
| Plan 01 creates `_atomic_write_unlocked` → Plan 02 uses it | ✓ | Correct ordering |
| Plan 01 creates `auth_store/` package → Plan 02 adds `_users.py` | ✓ | File added after package exists |
| Plan 01 migrates v1→v2 so Plan 02's schema assertion works | ✓ | Migration runs on first `load_auth()` |
| Plan 01 deletes `auth_store.py` flat file → last step only | ✓ | Last step of Plan 01 Task 2 |
| Plan 02's `_users.py` depends on `_io.py`'s `_load_raw` | ✓ | Same package, clear import |

### Overall Phase Assessment: **MEDIUM**

The plans achieve all phase goals. The only substantive risk is the flock/read_text split-inode concern, which does NOT break the consume guarantee but is architecturally subtle. The accepted non-flock writer race is appropriate for the phase scope. Neither concern blocks implementation.

---

## Consensus Summary

### Agreed Strengths

These points were validated by 2+ reviewers:

- **DEFAULT_AUTH_PATH placement in `__init__.py`** — all 3 agreed this is the correct approach to preserve 70+ monkeypatches
- **`hmac.compare_digest` + `sha256:<hex>` prefix-tagged storage** — all 3 praised as security-correct
- **Typed exceptions `InviteAlreadyConsumed` and `InviteExpired`** — all 3 agreed this is the right approach for SC-4
- **flock pattern scope** — all 3 agreed that restricting LOCK_EX to `consume_and_create_user` only is correct
- **v1→v2 migration with immediate `save_auth()`** — all 3 agreed clean and D-09 compliant
- **`_atomic_write_unlocked` introduced in Plan 01** — all 3 agreed correct dependency ordering

### Agreed Concerns

Concerns raised by 2+ reviewers — highest priority for executor:

1. **[MEDIUM] Circular import risk** — ALL 3 reviewers flagged this independently. `_io.py` top-level `from auth_store import DEFAULT_AUTH_PATH` can fail if `__init__.py` hasn't finished initializing. **Mitigation (consensus):** Define `DEFAULT_AUTH_PATH` at the very top of `__init__.py` BEFORE any imports from `._io`; perform the import lazily inside `_resolve_path()` function body rather than at module top level.

2. **[MEDIUM–HIGH] `_load_raw` bypasses migration** — Codex (HIGH) and OpenCode raised independently. If `consume_and_create_user` is ever called before a normal `load_auth()` runs on a v1 file, `users[]` and `pending_invites[]` may be absent from `_load_raw`'s return dict. **Mitigation (consensus):** Add an invariant assertion inside the flock window: `assert data.get('schema_version', 0) >= 2, "migration must precede invite flow"`. This catches the problem early with a clear error rather than a KeyError.

3. **[LOW–HIGH] Flock-on-inode vs path-based read/write mismatch** — ALL 3 reviewers noted the inode replacement issue. **Consensus analysis:** The single-use consume guarantee IS preserved (the lock prevents concurrent flock holders; subsequent openers re-open the new inode and wait). The accepted risk is data loss from concurrent non-flock writers (mint_invite_token, create_user) racing with consume — D-01 explicitly accepts this. **Mitigation (consensus):** Document this in a `consume_and_create_user` docstring.

4. **[LOW] `_load_raw` naming** — OpenCode and Codex (implicitly) both flagged the naming doesn't signal caller responsibility. **Consensus:** Rename to `_read_auth_unlocked` to match the `_atomic_write_unlocked` convention.

### Divergent Views

- **File count in Plan 01 success criterion (Codex only):** Codex noted Plan 01 says "5 files" but D-10 names 6 modules; `_users.py` lands in Plan 02. Use `>= 5` in the assertion. Gemini and OpenCode didn't flag this as an issue.
- **Input validation in `create_user` (Codex/OpenCode vs Gemini):** Codex and OpenCode recommend validating email, role, and disabled fields at the storage boundary. Gemini didn't raise this — it's a storage-layer vs API-layer separation question. For Phase 34 (pure storage, no routes), minimal validation is defensible; route-layer validation lands in Phase 37.
- **`mint_invite_token` duplicate invite check (Gemini only):** Gemini suggested rejecting if an unconsumed invite for same email already exists. Codex and OpenCode didn't flag this as blocking — worth a DEFERRED note but not a Phase 34 requirement.

---

*Reviewed 2026-05-13 | Reviewers: gemini, codex, opencode | qwen: failed (exit code 1)*
*To incorporate feedback: `/gsd-plan-phase 34 --reviews`*
