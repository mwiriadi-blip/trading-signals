# Phase 31: Core Module Split - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-12
**Phase:** 31-Core Module Split
**Areas discussed:** state_manager public API layer, Warning & equity helpers, sizing_engine orphaned fns

---

## state_manager public API layer

| Option | Description | Selected |
|--------|-------------|----------|
| `__init__.py` owns public API | io.py stays as low-level kernel. load_state / save_state / reset_state / mutate_state in __init__.py compose io + migrations + validation. ~300 LOC. | ✓ |
| `io.py` full persistence layer | io.py absorbs load_state / save_state / mutate_state (~350 LOC). __init__.py is thin re-exports. Simpler __init__ but blurry io.py responsibility. | |

**User's choice:** `__init__.py` owns public API (Recommended)
**Notes:** User asked "What is eloquent?" — explained the Most Eloquent Option label. Eloquent = locality of behaviour + no contract changes + composes naturally. `__init__.py` as orchestrator is more eloquent because each daughter module does ONE thing; `io.py` absorbing domain logic would violate single responsibility.

| Option | Description | Selected |
|--------|-------------|----------|
| `io.py` for `_save_state_unlocked` | Natural peer of `_atomic_write_unlocked`. Two unlocked write primitives together. | ✓ |
| `__init__.py` alongside mutate_state | Next to only caller. Avoids cross-module call for private helper. | |

**User's choice:** `io.py` (Recommended)

| Option | Description | Selected |
|--------|-------------|----------|
| `validation.py` for datetime guards | `_assert_tz_aware` + `_coerce_legacy_naive_iso` alongside `_validate_trade` + `_validate_loaded_state`. Consistent with validation.py purpose. | ✓ |
| `__init__.py` near callers | Private helpers collocated with load_state / append_warning. | |

**User's choice:** `validation.py` (Recommended)

---

## Warning & equity helpers

| Option | Description | Selected |
|--------|-------------|----------|
| `trades.py` alongside `record_trade` | Same append-to-list pattern: append_warning / clear_warnings / clear_warnings_by_source / update_equity_history. ~165 LOC total. | ✓ |
| `__init__.py` scattered in package root | Collocated with mutate_state which calls some of them. Mixes orchestration with helper implementations. | |

**User's choice:** `trades.py` alongside `record_trade` (Recommended)

| Option | Description | Selected |
|--------|-------------|----------|
| Keep name `trades.py` | Roadmap specifies this name. Warning/equity helpers are part of trade ledger's supporting data. | ✓ |
| Rename to `mutations.py` or `records.py` | More accurate for expanded scope. Deviates from roadmap spec. | |

**User's choice:** Keep `trades.py` (Recommended)

---

## sizing_engine orphaned functions

| Option | Description | Selected |
|--------|-------------|----------|
| `_models.py` for dataclasses | Phase 30 precedent. All submodules import from _models. __init__.py re-exports. ~75 LOC. | ✓ |
| `__init__.py` for dataclasses | No new file. ~300 LOC __init__. Mixes public API with data definitions. | |
| Distributed across submodules | Data close to producer but circular-import risk. | |

**User's choice:** `_models.py` (Recommended)

| Option | Description | Selected |
|--------|-------------|----------|
| `__init__.py` for `step()` | step() IS the package entry point. Callers already do `from sizing_engine import step`. ~260 LOC total. | ✓ |
| `sizing.py` for `step()` | step() starts with calc_position_size but then orchestrates stops/pyramid/close — breaks single-responsibility. | |

**User's choice:** `__init__.py` (Recommended)

| Option | Description | Selected |
|--------|-------------|----------|
| `sizing.py` for pnl, `pyramid.py` for drift | compute_unrealised_pnl = position-value = sizing domain. detect_drift = position vs signal divergence = pyramid/exit trigger. | ✓ |
| Both in `__init__.py` | Simple but grows __init__ to ~370 LOC mixing orchestration with two distinct domain helpers. | |
| Both in `sizing.py` | ~280 LOC. detect_drift conceptually far from position sizing. | |

**User's choice:** `sizing.py` for pnl, `pyramid.py` for drift (Recommended)

---

## Claude's Discretion

- Import ordering within each daughter file (stdlib → third-party → local).
- `# noqa: F401` vs `__all__` for re-exports in `__init__.py` files.
- Exact placement of shared constants (`STATE_SCHEMA_VERSION`, `STATE_FILE`) — `__init__.py` top or `_constants.py` if needed by multiple daughters.
- Whether `_read_signal_strategy_version` moves to `validation.py` if `migrations.py` exceeds 500 LOC.

## Deferred Ideas

None.
