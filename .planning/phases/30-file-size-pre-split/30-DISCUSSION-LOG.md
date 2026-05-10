# Phase 30: File-Size Pre-Split - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-10
**Phase:** 30-file-size-pre-split
**Areas discussed:** Split shape, Daughter file boundaries, paper_trades.py (493), AST blocklist scope

---

## Split shape

| Option | Description | Selected |
|--------|-------------|----------|
| Package per route | web/routes/trades/__init__.py exports register(). Sub-modules: trades/models.py, trades/renderers.py. Caller imports unchanged. Matches D-09 precedent. | ✓ |
| Flat parallel files | Keep trades.py as main entry, extract to trades_helpers.py or trades_models.py siblings. Simpler, no __init__.py. | |
| You decide | Claude picks the most consistent approach. | |

**User's choice:** Package per route (Recommended)
**Notes:** register() lives in __init__.py. Import surface preserved — __init__.py re-exports everything so callers and tests need zero import path changes.

---

## Daughter file boundaries

| Option | Description | Selected |
|--------|-------------|----------|
| By concept: models + renderers + init | _models.py (Pydantic models + exceptions), _renderers.py (render helpers), __init__.py (register + glue). | ✓ |
| By operation: open + close + modify | trades/_open.py, trades/_close.py, trades/_modify.py grouped by lifecycle. | |
| Minimal: just extract helpers | trades/_helpers.py (all private helpers), __init__.py (models + register). | |

**User's choice:** By concept: models + renderers + init
**Notes:**
- For login/totp (no Pydantic models): `_renderers.py` + `__init__.py` pattern.
- For dashboard.py (650 LOC, register() is ~500 lines): extract HTML-building sub-functions into `_renderers.py`; register() stays in `__init__.py` and calls them.
- User chose `_renderers.py` (not `_helpers.py`) as the naming convention for files containing render helpers.

---

## paper_trades.py (493)

| Option | Description | Selected |
|--------|-------------|----------|
| Split now | Preemptive split before Phase 31 injects user_id. OPS-01 explicitly lists it. Same pattern: _models.py + _renderers.py + __init__.py. | ✓ |
| Skip — it's under cap | Leave it. Split only if Phase 31 pushes it over 500. | |
| Split now but simpler | _models.py only, register() stays in __init__.py. Minimal surgery. | |

**User's choice:** Split now (Recommended)
**Notes:** 493 LOC is 7 lines under the 500-LOC cap, but OPS-01 explicitly scopes it and Phase 31 multi-tenant user_id injection will push it over. Full package pattern applied.

---

## AST blocklist scope

| Option | Description | Selected |
|--------|-------------|----------|
| Both: 'web' + exact names | Add 'web' (full web.* block), 'news_fetcher', 'news_filter', 'auth_store'. Most complete forward-looking guard. | ✓ |
| Exact names only | Add 'news_fetcher', 'news_filter', 'auth_store' only. Skip 'web' as redundant. | |
| 'web' only | Add 'web' as umbrella. news_fetcher/news_filter/auth_store are top-level so still need separate entries. | |

**User's choice:** Both: 'web' + exact names (Recommended)
**Notes:** _top_level_imports() extracts root module names, so 'web' catches all from web.routes.* imports. Extend FORBIDDEN_MODULES in place; FORBIDDEN_MODULES_BACKTEST_PURE is defined as `FORBIDDEN_MODULES | frozenset({'pyarrow'})` so the base set extension flows through automatically — no separate change to the backtest constant needed.

---

## Claude's Discretion

None — all areas had explicit user choices.

## Deferred Ideas

None — discussion stayed within phase scope.
