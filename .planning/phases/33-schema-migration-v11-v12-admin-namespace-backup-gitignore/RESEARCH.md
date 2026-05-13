# Phase 33: Schema Migration v11→v12 + Admin Namespace + Backup + Gitignore — Research

**Researched:** 2026-05-13
**Domain:** state_manager schema migration, gitignore CI gate, off-droplet backup
**Confidence:** HIGH

---

## Summary

Schema version is confirmed v11 (not v9 as PROJECT.md may imply — codebase truth is `system_params.py`). The migration chain ends at key 11 in `MIGRATIONS`. Phase 33 adds `_migrate_v11_to_v12` and bumps `STATE_SCHEMA_VERSION` to 12. The migration rebuckets per-user state from top-level keys into `state['users']['u_admin_marc']` and stamps `state['admin_user_id'] = 'u_admin_marc'`. Shared state (signals, markets, strategy_settings, warnings, last_run) stays top-level.

The codebase has a mature migration pattern: each migrator is a pure dict→dict function, registered in the `MIGRATIONS` dict, with a contiguity assertion at both module-load and `load_state()` entry. The pattern is well-tested (123 passing tests). Adding v12 requires: write `_migrate_v11_to_v12`, register at key 12, bump `STATE_SCHEMA_VERSION = 12`, update `_REQUIRED_STATE_KEYS` in validation.py, update `reset_state()` to emit a v12-shaped dict.

No rclone or backup script exists in the codebase. The CI has only one workflow (`daily.yml.disabled`, a GitHub Actions daily run) — no test CI, no backup CI. Both must be built from scratch.

**Primary recommendation:** Follow the existing migration pattern exactly (dict→dict, idempotent, D-15 silent, no warnings/logs). Add a pre-save auto-backup call in `_migrate_v11_to_v12` or in `load_state()` before saving. Build rclone-to-B2 as a systemd timer on the droplet. Add a GitHub Actions CI step that runs `git ls-files | grep '^state/users/'` and fails on non-empty output.

---

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TENANT-01 | v11→v12 migration; admin data into `state['users']['admin_<uid>']`; auto-backup; round-trip fixtures; contiguity assert | Migration pattern verified; admin uid `u_admin_marc` locked in planning/research/ARCHITECTURE.md |
| TENANT-04 | `state/users/` gitignored; CI gate; rclone-to-B2 daily; 48h-stale alert email | No rclone/CI yet; notifier email infra exists; patterns verified |

---

## Schema Version Locked

**Source version (current codebase):** `STATE_SCHEMA_VERSION = 11` [VERIFIED: `system_params.py` line 281]

**Last migration key:** `11: _migrate_v10_to_v11` [VERIFIED: `state_manager/migrations.py` MIGRATIONS dict line 369]

**Target version (this phase):** `12`

**New migration function:** `_migrate_v11_to_v12(old: dict) -> dict`

**New MIGRATIONS entry:** `12: _migrate_v11_to_v12`

**`STATE_SCHEMA_VERSION` after phase:** `12`

The ROADMAP and planning/research/ARCHITECTURE.md noted this migration was originally spec'd as v9→v10, but codebase truth is v11→v12. Confirmed. [VERIFIED]

---

## Current v11 Structure

Live `state.json` on disk (schema_version=11) has these top-level keys [VERIFIED]:

### Shared (stay at top-level in v12)
| Key | Type | v12 fate |
|-----|------|----------|
| `schema_version` | int | stay (bumped to 12) |
| `last_run` | str (YYYY-MM-DD) or null | stay |
| `signals` | dict[market_id → signal_row] | stay (computed, shared) |
| `markets` | dict[market_id → market_spec] | stay (admin curates, shared) |
| `strategy_settings` | dict[market_id → settings] | stay (shared) |
| `warnings` | list | stay (system-level) |

### Per-user (move into `state['users']['u_admin_marc']`)
| Key | Type | v12 fate |
|-----|------|----------|
| `account` | float | move |
| `initial_account` | float | move |
| `contracts` | dict[market_id → label] | move |
| `positions` | dict[market_id → Position or null] | move |
| `trade_log` | list | move |
| `equity_history` | list | move |
| `paper_trades` | list | move |

### New keys added by v12
| Key | Type | Value |
|-----|------|-------|
| `admin_user_id` | str | `'u_admin_marc'` (locked in planning/research/ARCHITECTURE.md) |
| `users` | dict[user_id → user_state] | admin bucket created from moved keys |

**`_REQUIRED_STATE_KEYS` must be updated** in `state_manager/validation.py` to include `'admin_user_id'` and `'users'`, and remove `'account'`, `'initial_account'`, `'contracts'`, `'positions'`, `'trade_log'`, `'equity_history'`, `'paper_trades'` from the top-level required set (they now live under `users`). [ASSUMED — planner must decide exact new required-key set for v12 _validate_loaded_state]

---

## v12 Target Structure

```json
{
  "schema_version": 12,
  "admin_user_id": "u_admin_marc",
  "last_run": "2026-04-23",
  "signals": { "SPI200": {...}, "AUDUSD": {...} },
  "markets": { "SPI200": {...}, "AUDUSD": {...} },
  "strategy_settings": { "SPI200": {...}, "AUDUSD": {...} },
  "warnings": [],
  "users": {
    "u_admin_marc": {
      "account": 100000.0,
      "initial_account": 100000.0,
      "contracts": { "SPI200": "spi-mini", "AUDUSD": "audusd-standard" },
      "positions": { "SPI200": null, "AUDUSD": null },
      "trade_log": [],
      "equity_history": [...],
      "paper_trades": [],
      "ui_prefs": { "tour_completed": true }
    }
  }
}
```

**Admin uid is `'u_admin_marc'`** — locked in `planning/research/ARCHITECTURE.md` line 313 and line 134. [CITED: .planning/research/ARCHITECTURE.md]

**`ui_prefs`:** Initialized to `{"tour_completed": True}` for admin (existing user — no tour needed). [CITED: .planning/research/ARCHITECTURE.md line 319]

---

## Migration Pattern

### Existing pattern (verified) [VERIFIED: state_manager/migrations.py]

1. Each `_migrate_vN_to_vN+1(s: dict) -> dict` is a pure function.
2. D-15: silent migration — no `append_warning`, no log lines.
3. Idempotent: using `.get()` and defensive guards so re-running on already-migrated state is a no-op.
4. Registered in `MIGRATIONS: dict` as `{version_number: function}` where version_number is the OUTPUT version (e.g. `11: _migrate_v10_to_v11`).
5. `_migrate(state)` walks forward from `state.get('schema_version', 0)` to `STATE_SCHEMA_VERSION`.
6. `_assert_migration_chain_contiguous()` fires at:
   - Module import bottom of `state_manager/migrations.py`
   - Every `load_state()` entry in `state_manager/__init__.py`

### What _migrate_v11_to_v12 must do

```python
def _migrate_v11_to_v12(s: dict) -> dict:
    '''v12: bucket per-user state under state["users"]["u_admin_marc"].

    Moves: account, initial_account, contracts, positions, trade_log,
    equity_history, paper_trades into state["users"]["u_admin_marc"].
    Adds: admin_user_id = "u_admin_marc", users{} top-level.
    Leaves shared: signals, markets, strategy_settings, warnings,
    last_run, schema_version.
    Idempotent: if "users" already present, skips re-bucketing.
    D-15 silent migration: no append_warning, no log line.
    '''
    ADMIN_UID = 'u_admin_marc'
    out = dict(s)
    # Idempotency guard: if users already present, skip bucketing.
    if 'users' not in out:
        user_bucket = {
            'account':          out.pop('account', INITIAL_ACCOUNT),
            'initial_account':  out.pop('initial_account', INITIAL_ACCOUNT),
            'contracts':        out.pop('contracts', {...defaults...}),
            'positions':        out.pop('positions', {'SPI200': None, 'AUDUSD': None}),
            'trade_log':        out.pop('trade_log', []),
            'equity_history':   out.pop('equity_history', []),
            'paper_trades':     out.pop('paper_trades', []),
            'ui_prefs':         {'tour_completed': True},
        }
        out['users'] = {ADMIN_UID: user_bucket}
        out['admin_user_id'] = ADMIN_UID
    return out
```

**Note:** The success criteria says "builds a fresh dict, Pydantic-validates v12 shape, and only then saves." This means the migration function itself should NOT call save — the save+Pydantic-validate step sits in `load_state()` after `_migrate()` runs. The planner must decide whether to put the Pydantic validation inside `_migrate_v11_to_v12` or in the `load_state()` post-migrate step. Both are viable; post-migrate is more consistent with the existing validator placement (`_validate_loaded_state` runs after `_migrate`).

### Auto-backup before save

The success criteria requires `state.json.v11-backup-<isoformat>` written before the save. The ROADMAP phrasing "only then saves" implies: backup → validate → save. Existing `_backup_corrupt` in `io.py` renames the file (destructive). Phase 33 needs a **non-destructive copy** backup:

```python
# In load_state(), after detecting schema_version < 12 and before _migrate() output is saved:
# shutil.copy2(path, path.parent / f'state.json.v11-backup-{isoformat}')
```

This is a NEW function, not reuse of `_backup_corrupt`. [ASSUMED — exact placement in load_state() or in _migrate_v11_to_v12 itself to be decided by planner]

### Pydantic v12 shape validation

Pydantic 2.13.3 is installed [VERIFIED]. The codebase uses Pydantic `BaseModel` in `web/routes/` but NOT in `state_manager/`. The success criteria says "Pydantic-validates v12 shape." This means a new `StateV12(BaseModel)` or similar model must be written. It lives either in:
- `state_manager/validation.py` (most consistent with existing pattern)
- A new `state_manager/schemas.py`

**Hex boundary note:** `state_manager/` is the I/O hex; Pydantic is a pure-data library with no I/O — it is safe to import in `state_manager/`. [VERIFIED: Pydantic has no forbidden imports per the hex rule]

---

## Backup Pattern

### Existing backup behaviour [VERIFIED: state_manager/io.py]

`_backup_corrupt(path, now)` — renames corrupt file to `{path.name}.corrupt.<ts>`. This is DESTRUCTIVE (os.rename). Not suitable for pre-migration backup.

No other backup mechanism exists in the codebase. No scripts, no cron, no systemd timers for backup. [VERIFIED: searched scripts/, systemd/, .github/]

### What to add

**Pre-migration backup (auto before v12 save):**
- Use `shutil.copy2(path, backup_path)` — non-destructive copy.
- Backup path: `path.parent / f'{path.name}.v11-backup-{now.isoformat()}'`
- Only fires when migrating FROM v11 (check `old_version == 11` before copy).
- Idempotent: if backup file already exists, skip.

**Off-droplet backup (rclone-to-B2):**
- No rclone installed on dev machine [VERIFIED: `command -v rclone` returns exit 1].
- On droplet: rclone must be installed, configured with B2 credentials in `/etc/rclone.conf` or `~trader/.config/rclone/rclone.conf`.
- Systemd timer approach (consistent with existing `trading-signals-web.service`):
  - `trading-signals-backup.service` — runs `rclone copy /home/trader/trading-signals/state.json b2:bucket/trading-signals/state.json`
  - `trading-signals-backup.timer` — `OnCalendar=daily`, persisted timer.
- Alert on stale backup: a Python script (or extended `daily_run.py`) checks the B2 file's last-modified timestamp via `rclone lsl` or `rclone check`. If older than 48h, calls `notifier.send_crash_email()` or a new `send_backup_alert_email()`.

### Notifier email pattern [VERIFIED: notifier/__init__.py]

Existing `send_crash_email(exc, state_summary, now=None)` and `send_stop_alert_email(transitions, dashboard_url)` show the pattern. The 48h-stale alert is a new use case — planner should decide: reuse `send_crash_email` with a synthetic exception, or add a dedicated `send_backup_stale_email(last_backup_ts)` to the notifier. [ASSUMED — dedicated function is cleaner]

---

## Gitignore + CI Gate

### Current .gitignore [VERIFIED: .gitignore]

Does NOT contain `state/users/`. Must add.

### What to add to .gitignore

```gitignore
# Phase 33: per-user state files (never committed; off-droplet backup only)
state/users/
state/*.v11-backup-*
```

**Note:** The current `state.json` is listed in `.gitignore` but the daily workflow uses `add_options: '-f'` to force-add it. Phase 33 must ensure `state/users/` can NEVER be force-added by mistake — the CI gate catches this.

### CI gate

The `daily.yml.disabled` is the only GitHub Actions workflow. It is disabled and targets the cron daily run, not tests.

A new or extended CI workflow must:
1. Run `git ls-files | grep '^state/users/'`
2. Fail with non-zero exit if any output is produced.

Since there is NO test CI workflow currently [VERIFIED], the planner must decide: create a new `ci.yml` that runs the test suite + the git ls-files check, or add the check to a pytest conftest fixture. The test-suite approach is simpler and doesn't require a GitHub Actions secret setup:

```python
# tests/test_gitignore_gate.py
def test_state_users_not_tracked():
    import subprocess
    result = subprocess.run(
        ['git', 'ls-files', '--', 'state/users/'],
        capture_output=True, text=True
    )
    assert result.stdout.strip() == '', (
        f'state/users/ files are tracked by git: {result.stdout.strip()}'
    )
```

This can also be done as a GitHub Actions step in a new `ci.yml`. [ASSUMED — planner decides pytest-based vs GHA-based]

---

## rclone/B2

### What exists

Nothing. No rclone config, no B2 credentials, no backup script. [VERIFIED]

### What to build

| Component | Location | Notes |
|-----------|----------|-------|
| `trading-signals-backup.service` | `systemd/` | `ExecStart=rclone copy ...`; `User=trader` |
| `trading-signals-backup.timer` | `systemd/` | `OnCalendar=daily`; `Persistent=true` |
| `scripts/check_backup_age.py` | `scripts/` | Reads B2 last-modified via `rclone lsl`; sends alert if >48h |
| `.env` addition | droplet only | `RCLONE_B2_ACCOUNT`, `RCLONE_B2_KEY`, `B2_BUCKET` — never committed |

The check script can be invoked by a separate systemd timer or piggy-backed onto the daily run. Simplest: add a call to `check_backup_age()` at the end of `daily_run.py` (already runs daily, already has notifier wired). [ASSUMED — planner decides integration point]

**rclone version to target:** rclone is stable and widely used. Latest stable is v1.68+ as of 2026. [ASSUMED — verify on droplet at execution time]

---

## Open Questions

1. **Admin uid hardcoding vs discovery.** The planning/research/ARCHITECTURE.md locks `u_admin_marc` as the admin uid. But `auth.json` today has no `user_id` field — it's a single-admin store. Phase 33 must either: (a) hardcode `u_admin_marc` in the migrator (simplest, locks the uid before Phase 34 introduces user registry), or (b) generate a deterministic uid from the TOTP secret or email in `auth.json`. Option (a) is recommended for Phase 33; Phase 34 adds the user registry that will formally define the admin uid.

2. **Pydantic StateV12 model placement.** Does it live in `state_manager/validation.py` or a new `state_manager/schemas.py`? `validation.py` is at 234 LOC — adding a Pydantic model is ~30–50 lines, stays under 500 LOC limit. New file adds fragmentation. Recommend `validation.py`.

3. **`_REQUIRED_STATE_KEYS` post-v12.** Currently required at top level: `schema_version`, `account`, `last_run`, `positions`, `signals`, `trade_log`, `equity_history`, `warnings`, `initial_account`, `contracts`, `markets`, `strategy_settings`. After v12: `account`, `initial_account`, `contracts`, `positions`, `trade_log`, `equity_history` move under `users`. New top-level required: add `admin_user_id`, `users`. Remove the 6 moved keys from top-level required. Planner must specify exact set.

4. **Pre-migration backup call site.** Two options: (a) in `load_state()` — check old schema_version before calling `_migrate()`; if old version < 12, copy the file first; (b) inside `_migrate_v11_to_v12()` — call `shutil.copy2` before building the output dict (hex violation: migrations.py is pure-math, cannot do I/O). Option (a) is mandatory given the hex boundary: migrations.py must stay stdlib-only with no I/O. The backup copy call belongs in `load_state()` in `__init__.py`.

5. **Round-trip test "lossless v11→v12→v11'"** — the success criteria asks for a reverse(`v12`) → v11' such that v11 == v11'. This requires either: (a) a `_migrate_v12_to_v11` inverse function (not standard pattern — existing migrations are forward-only), or (b) a snapshot-compare: save the v11 dict before migration, run migration, then assert all v11 fields are present at the correct paths in v12. Option (b) is the practical interpretation — the planner should clarify "lossless" means field values are preserved, not that a mechanical inverse exists.

6. **`state/users/` directory.** The gitignore path implies files will live under `state/users/` on disk. But the current architecture uses a single `state.json` — there is no `state/` subdirectory. Per-user state files under `state/users/{uid}.json` were explicitly rejected in planning/research/ARCHITECTURE.md in favor of a single `state.json` with a `users{}` key. The gitignore pattern is forward-looking for Phase 36 when `mutate_user_state` may write separate per-user lock files (`state/users/{uid}.lock`). Phase 33 must create the gitignore entry and CI gate even before files in that path exist.

7. **B2 bucket name and credentials.** These are operator-supplied secrets; Phase 33 cannot commit them. The plan must include: (a) placeholders in `.env.example` or deploy docs, (b) the rclone config path on the droplet.

---

## Risk Flags

1. **`_REQUIRED_STATE_KEYS` mismatch.** If `validation.py::_validate_loaded_state` is not updated to reflect the v12 shape, every `load_state()` after migration will raise `ValueError` with "state missing required keys: ['account', ...]". The 6 moved keys will no longer be at top level. This is the highest-risk oversight.

2. **`reset_state()` must emit v12 shape.** Currently `reset_state()` returns a flat v11-shaped dict. After this phase, `reset_state()` must return a v12-shaped dict with `users{}` and `admin_user_id`. If not updated, corruption recovery will produce a v11 dict at the wrong schema_version. Tests explicitly check `reset_state()` output shape.

3. **Re-export list in `state_manager/__init__.py`.** After adding `_migrate_v11_to_v12` to `migrations.py`, it must be re-exported in `__init__.py` under `__all__` and the `from state_manager.migrations import (...)` block (lines 81–96). Forgetting this breaks any test that imports directly from `state_manager`.

4. **`save_state()` strips `_`-prefixed keys.** `_resolved_contracts` is already stripped. No new underscore keys are introduced by v12. No risk here.

5. **Fixture files.** Existing test fixtures (`state_v2_no_manual_stop.json`, `state_v6_with_paper_trades.json`, `state_v7_with_alerts.json`) are all pre-v11. They will walk through the full migration chain including v12. They should not break because `_migrate_v11_to_v12` treats missing keys with `.get()` defaults. Verify explicitly in round-trip tests.

6. **`mutate_state()` and the flock deadlock.** Phase 33 does NOT introduce `mutate_user_state` (that's Phase 36). The existing `mutate_state` path is unchanged. No flock risk in this phase.

7. **No test CI workflow exists.** If a new GitHub Actions `ci.yml` is added, it needs a valid Python environment. The `daily.yml.disabled` shows the pattern. The new CI workflow must NOT require secrets for the git ls-files check (it is a pure git command).

---

## Architecture Diagram

```
load_state()
    │
    ├─ schema_version < 12? ──YES──> copy state.json → state.json.v11-backup-<ts>
    │                                (shutil.copy2, in __init__.py, NOT migrations.py)
    │
    ├─ _migrate(state)
    │     └─ _migrate_v11_to_v12(s)  [pure dict→dict, no I/O]
    │           ├─ 'users' in s? → skip (idempotent)
    │           └─ pop per-user keys → build users['u_admin_marc']
    │
    ├─ Pydantic StateV12.model_validate(state)  [raises if shape wrong]
    │
    ├─ _validate_loaded_state(state)  [existing key-presence check, updated for v12]
    │
    └─ return state

rclone backup (systemd timer, daily):
    trading-signals-backup.timer
        └─ trading-signals-backup.service
              └─ rclone copy state.json b2:bucket/...

stale-backup alert (in daily_run.py or separate script):
    check_backup_age() → rclone lsl → parse mtime → if >48h → notifier.send_*_email()

CI gate (GitHub Actions or pytest):
    git ls-files | grep '^state/users/' → fail if non-empty
```

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| v11→v12 migration logic | state_manager/migrations.py (pure hex) | — | Pure dict transform, no I/O |
| Pre-migration file backup | state_manager/__init__.py (I/O hex) | io.py | File copy is I/O; migrations.py is IO-forbidden |
| Pydantic schema validation | state_manager/validation.py | — | Co-located with existing validators |
| gitignore entry | .gitignore | — | Git config |
| CI git ls-files gate | .github/workflows/ci.yml or tests/ | — | Either is valid |
| rclone backup execution | systemd/trading-signals-backup.{service,timer} | — | Droplet-side scheduled I/O |
| Stale backup alert | scripts/check_backup_age.py or daily_run.py | notifier/ | Uses existing email infra |

---

## Standard Stack

### Core (all already in project)
| Library | Version | Purpose |
|---------|---------|---------|
| pydantic | 2.13.3 | v12 schema validation (BaseModel) |
| shutil | stdlib | Pre-migration backup copy |
| json | stdlib | State persistence |
| fcntl | stdlib | Existing write lock (unchanged) |

### New tooling (droplet only)
| Tool | Purpose |
|------|---------|
| rclone | Off-droplet B2 backup |
| systemd timer | Schedule daily backup |

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.3.3 |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `.venv/bin/pytest tests/test_state_manager.py tests/test_migration_contiguity.py -x --tb=short` |
| Full suite command | `.venv/bin/pytest -x --tb=short` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TENANT-01 | `_migrate_v11_to_v12` moves per-user keys into `users['u_admin_marc']` | unit | `pytest tests/test_state_manager.py::TestMigrateV11ToV12 -x` | ❌ Wave 0 |
| TENANT-01 | Round-trip on 5 fixtures is lossless | unit | `pytest tests/test_state_manager.py::TestV12RoundTrip -x` | ❌ Wave 0 |
| TENANT-01 | Pydantic StateV12 validates output | unit | `pytest tests/test_state_manager.py::TestStateV12Schema -x` | ❌ Wave 0 |
| TENANT-01 | Contiguity assert passes for chain 1→12 | unit | `pytest tests/test_migration_contiguity.py -x` | ✅ (passes at 11; extend to 12) |
| TENANT-01 | Auto-backup file written before save | unit | `pytest tests/test_state_manager.py::TestV12AutoBackup -x` | ❌ Wave 0 |
| TENANT-04 | `state/users/` not tracked by git | unit (or CI) | `pytest tests/test_gitignore_gate.py -x` | ❌ Wave 0 |
| TENANT-04 | Stale backup alert (48h check) | unit | `pytest tests/test_backup_age.py -x` | ❌ Wave 0 |

### Wave 0 Gaps
- [ ] `tests/test_state_manager.py::TestMigrateV11ToV12` class — migration unit tests
- [ ] `tests/test_state_manager.py::TestV12RoundTrip` class — 5-fixture round-trip
- [ ] `tests/test_state_manager.py::TestStateV12Schema` class — Pydantic validation
- [ ] `tests/test_state_manager.py::TestV12AutoBackup` class — backup file written
- [ ] `tests/test_gitignore_gate.py` — new file for CI gate test
- [ ] `tests/test_backup_age.py` — stale-backup alert logic test
- [ ] `tests/fixtures/state_v11_empty.json` — empty v11 fixture
- [ ] `tests/fixtures/state_v11_max_trade_log.json` — max trade_log fixture
- [ ] `tests/fixtures/state_v11_mid_pyramid.json` — mid-pyramid position fixture
- [ ] `tests/fixtures/state_v11_mid_alert_approaching.json` — alert APPROACHING fixture
- [ ] `tests/fixtures/state_v11_naive_datetime.json` — naive-datetime legacy fixture

Existing contiguity tests in `tests/test_migration_contiguity.py` will continue to pass; the in-tree chain check is parametric on `STATE_SCHEMA_VERSION`.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Pydantic StateV12 validation belongs in `state_manager/validation.py` (not a new file) | Migration pattern | Minor: creates a new schemas.py instead; easy to adjust |
| A2 | Pre-migration backup call site is `load_state()` in `__init__.py` (not inside `_migrate_v11_to_v12`) | Backup pattern | Critical: if put in migrations.py it violates hex boundary and would fail the stdlib-only AST test |
| A3 | Admin uid is `'u_admin_marc'` (hardcoded in migrator) | v12 structure | Medium: if the uid is later decided differently, the migration is already baked into state.json of production. Confirm before writing the migrator. |
| A4 | "Lossless round-trip" in success criteria means field-value preservation, not a mechanical inverse function | Round-trip test | Medium: if a strict reverse is required, extra work needed |
| A5 | `state/users/` gitignore is forward-looking (no files there yet in Phase 33) | Gitignore | Low: gitignore patterns for non-existent paths are valid and harmless |
| A6 | Stale-backup check runs within `daily_run.py` (existing daily run) vs a separate systemd timer | rclone/B2 | Low: either works; piggybacking on daily_run avoids a third systemd unit |

---

## Sources

### Primary (HIGH confidence — verified by direct code read)
- `system_params.py` line 281 — `STATE_SCHEMA_VERSION = 11`
- `state_manager/migrations.py` — full MIGRATIONS dict, all migration functions
- `state_manager/__init__.py` — load_state, save_state, mutate_state, re-export list
- `state_manager/validation.py` — _REQUIRED_STATE_KEYS, _validate_loaded_state
- `state_manager/io.py` — _backup_corrupt, _atomic_write, _save_state_unlocked
- `state.json` — live v11 shape confirmed
- `auth.json` — no uid field; single-admin structure
- `.gitignore` — current patterns confirmed
- `requirements.txt` — dependency list (no rclone, pydantic is transitive via fastapi)
- `.venv` — pydantic 2.13.3 installed

### Secondary (HIGH confidence — verified from planning docs)
- `.planning/research/ARCHITECTURE.md` — admin uid `u_admin_marc`, v12 shape spec, per-user field split
- `.planning/REQUIREMENTS.md` — TENANT-01, TENANT-04 full acceptance criteria
- `.planning/ROADMAP.md` — Phase 33 success criteria verbatim
- `tests/test_migration_contiguity.py` — contiguity test pattern
- `tests/test_state_manager.py` — migration test class structure
- `tests/fixtures/` — existing v2, v6, v7 fixtures

### Tertiary (ASSUMED — not verified externally)
- rclone B2 integration approach (standard rclone pattern, widely used)
- systemd timer for daily backup (consistent with existing `.service` file pattern)
