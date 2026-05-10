---
phase: 22
slug: strategy-versioning-audit-trail
status: verified
threats_open: 0
asvs_level: 1
created: 2026-05-10
---

# Phase 22 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Retroactively reconstructed from 22-01-PLAN.md, 22-01-SUMMARY.md, and 22-VERIFICATION.md (Plan 29-07 sweep).
> Phase 22 introduces: `STRATEGY_VERSION` constant, `STATE_SCHEMA_VERSION` bump 3→4, signal-row `strategy_version` field, v3→v4 state migration, dashboard version render.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| `system_params.STRATEGY_VERSION` (source constant) ↔ `state.json` (persisted signal rows) | Version string must round-trip without corruption; migration must stamp correct value | `strategy_version` string on every dict-shaped signal row |
| `state.json` existing rows ↔ v3→v4 migration | `_migrate_v3_to_v4` must be additive + idempotent; must not drop any field on existing rows | All pre-existing signal row keys (`signal`, `signal_as_of`, `as_of_run`, `last_close`, `last_scalars`) |
| `state.json` (loaded) ↔ migration chain contiguity | `MIGRATIONS` dict must have a contiguous integer key range; missing key raises at module load | Schema version integer, migration dispatch |
| `main.py` signal-row writer ↔ `dashboard.py` render layer | `STRATEGY_VERSION` must NOT cross the hex boundary as a module import; must flow as a primitive string via state dict | `strategy_version` string |
| `dashboard.py` ↔ rendered HTML | Version string is operator-controlled (not user-supplied); no injection surface | HTML fragment in footer `<code>` tag |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-22-01-01 | Tampering | `_migrate_v3_to_v4` drops an existing signal row field on migration | mitigate | `test_migrate_v3_to_v4_preserves_other_signal_fields` asserts all original keys + values round-trip exactly; migration only adds `strategy_version` key (no deletes, no mutations of existing keys) | closed |
| T-22-01-02 | Tampering | `_migrate_v3_to_v4` overwrites an existing `strategy_version` field (e.g., a row already stamped `'v1.2.0'` gets overwritten to `'v1.1.0'`) | mitigate | Idempotency guard: `if 'strategy_version' not in sig:`; `test_migrate_v3_to_v4_idempotent` + `test_migrate_v3_to_v4_skips_signal_rows_with_existing_field` | closed |
| T-22-01-03 | Tampering (self) | Future contributor adds `_migrate_vN_to_vN+1` but skips `MIGRATIONS` registration — contiguity break | mitigate | Cross-linked with Phase 27 T-27-07-01: `_assert_migration_chain_contiguous` in Phase 27 Plan 27-07 fails at module load AND `load_state` entry; the Phase 22 migration itself is registered at `MIGRATIONS[4]` and verified by `test_full_walk_v0_to_v4_then_load_state` | closed |
| T-22-02-01 | Tampering | `system_params.STRATEGY_VERSION` captured at import time via kwarg default in `main.py` signal-row writer — monkeypatch bump doesn't propagate | mitigate | Fresh attribute access `system_params.STRATEGY_VERSION` inside function body (not kwarg default); `test_apply_daily_run_strategy_version_matches_constant_after_constant_bump` monkeypatches `system_params.STRATEGY_VERSION='v9.9.9'` and asserts the written row carries `'v9.9.9'` | closed |
| T-22-03-01 | Tampering (hex-boundary) | `dashboard.py` imports `system_params.STRATEGY_VERSION` directly — violates hex-boundary rule; breaks singleton-module discipline | mitigate | `dashboard.py` does NOT import `STRATEGY_VERSION`; reads version off state dict via `_resolve_strategy_version(state)`; `test_dashboard_does_not_import_strategy_version_symbol` AST-walks dashboard.py and asserts `STRATEGY_VERSION` is NOT among imported names | closed |
| T-22-03-02 | Information Disclosure | `strategy_version` string in dashboard HTML leaks implementation detail | accept | Single-operator system; version string is intentionally visible to operator (that is the feature); no secret or PII | closed |
| T-22-04-01 | Tampering | Silent migration failure: `load_state` succeeds but signal rows are missing `strategy_version` (e.g., partial migration on exception mid-loop) | mitigate | Defensive-read helper `_read_signal_strategy_version` + `_resolve_strategy_version` in dashboard both emit `[State] WARN signal row missing strategy_version field — defaulting to v1.0.0`; `test_defensive_read_logs_WARN_on_missing_strategy_version` asserts WARN fires; operator sees in journalctl on next dashboard load | closed |
| T-22-05-01 | Repudiation | Audit-trail tampered: `state.json` signal rows manually edited to remove or alter `strategy_version` | accept | File-based state on single-operator droplet; no external auditor; operator retains git history as lineage; same risk class as any other `state.json` field. No chain-of-custody requirement for this system tier | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-22-01 | T-22-03-02 | `strategy_version` string in dashboard HTML is the intended feature for operator visibility; single-operator system. | operator | 2026-04-30 |
| AR-22-02 | T-22-05-01 | File-based state; no external auditor; git history is the audit trail. Manual edits are the operator's prerogative on a single-operator system. | operator | 2026-04-30 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-05-10 | 8 | 8 | 0 | Plan 29-07 retroactive sweep (register authored from 22-01-PLAN.md + 22-01-SUMMARY.md + 22-VERIFICATION.md) |

### 2026-05-10 — initial retroactive audit

- **Method:** Plan-29-07 mechanical retrofit. Threat surface identified from Phase 22 trust boundaries: `STRATEGY_VERSION` constant integrity, signal/trade row stamping via state migration, retroactive `v1.1.0` backfill on existing state, hex-boundary migration chain contiguity (cross-linked to Phase 27 T-27-07-01).
- **Migration chain contiguity (T-22-01-03):** mitigated by Phase 27 Plan 27-07 `_assert_migration_chain_contiguous` which guards the full chain including the Phase 22 `MIGRATIONS[4]` entry. Cross-link established.
- **Kwarg-default capture (T-22-02-01):** mitigated by fresh attribute access per global LEARNINGS 2026-04-29; regression test explicitly monkeypatches the constant and proves the writer reads at call time.
- **Hex-boundary (T-22-03-01):** mitigated by AST test; confirmed in 22-VERIFICATION.md §Hex-Boundary Check.
- **No new threats introduced** beyond those identified above; no auditor-spawn required.

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter
- [x] Cross-link to Phase 27 T-27-07-01 for migration-chain contiguity

**Approval:** verified 2026-05-10 (retroactive reconstruction; phase shipped and verified 2026-04-30 per 22-VERIFICATION.md PASS verdict)
