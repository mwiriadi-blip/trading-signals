---
phase: 11
plan: 01
subsystem: web
tags: [fastapi, uvicorn, healthz, hex-boundary, tdd]
dependency_graph:
  requires: []
  provides: [web/app.py, web/routes/healthz.py, GET /healthz, fastapi pinned]
  affects: [requirements.txt, tests/]
tech_stack:
  added: [fastapi==0.136.1, uvicorn[standard]==0.46.0, httpx==0.28.1]
  patterns: [create_app() factory, local-import C-2, D-19 never-crash, AST hex-boundary guard]
key_files:
  created:
    - web/__init__.py
    - web/app.py
    - web/routes/__init__.py
    - web/routes/healthz.py
    - tests/test_web_healthz.py
  modified:
    - requirements.txt
decisions:
  - "create_app() has no docs_url/redoc_url kwargs per REVIEWS MEDIUM #6 — Swagger defaults left for Phase 11"
  - "Handler uses date.fromisoformat (not datetime) per REVIEWS HIGH #1 — last_run is YYYY-MM-DD date string"
  - "Tests monkeypatch state_manager.load_state directly per REVIEWS HIGH #2 — STATE_FILE monkeypatch does not work (default arg bound at import time)"
  - "state_manager import is LOCAL inside healthz() handler body (C-2 pattern from main.py lines 111-129)"
metrics:
  duration: "432s (~7 min)"
  completed: "2026-04-24"
  tasks: 3
  files: 6
---

# Phase 11 Plan 01: Web Package Scaffold + /healthz Handler Summary

FastAPI package scaffold with pinned deps, /healthz handler using C-2 local-import and D-19 never-crash posture, 5-class test suite with monkeypatched load_state stubs.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Pin web deps + scaffold web/ package | e0ca550 | requirements.txt, web/__init__.py, web/routes/__init__.py |
| 2 | Implement web/app.py factory + web/routes/healthz.py | 448c956 | web/app.py, web/routes/healthz.py |
| 3 | Write tests/test_web_healthz.py (5 classes, 16 tests) | 3f6f73f | tests/test_web_healthz.py |

## Implementation Notes

### Pin versions (Task 1)

Three exact version pins appended to requirements.txt:

```
fastapi==0.136.1
uvicorn[standard]==0.46.0
httpx==0.28.1
```

Empty package markers created: `web/__init__.py` (0 bytes), `web/routes/__init__.py` (0 bytes).

### Fixture strategy: monkeypatch load_state directly (REVIEWS HIGH #2)

`load_state(path: Path = Path(STATE_FILE), now=None)` binds the default arg at function-definition time. Monkeypatching `state_manager.STATE_FILE` after import has no effect on the already-captured `Path` default. All tests use:

```python
monkeypatch.setattr(state_manager, 'load_state', _stub_load_state(...))
```

This replaces the function object itself so the handler's local import resolves to the patched version.

### No docs_url/redoc_url kwargs (REVIEWS MEDIUM #6)

`create_app()` uses FastAPI defaults for Swagger (`/docs`) and Redoc (`/redoc`). Phase 11 has no external HTTPS; disabling them is out-of-scope policy. Phase 13 or 16 can add this as a locked decision.

### date.fromisoformat (REVIEWS HIGH #1)

`state.json` stores `last_run` as a `YYYY-MM-DD` date string (written at `main.py:1042`). Handler uses `_date.fromisoformat(last_run)` to parse it for the D-16 staleness check — NOT `datetime.fromisoformat` which would raise on a date-only string in Python 3.10 and below.

### Hex boundary enforcement

- `web/app.py` has zero `state_manager` references (docstring cleaned up during Task 2)
- `web/routes/healthz.py` imports `state_manager` LOCALLY inside the handler body (C-2)
- `TestWebHexBoundary` AST guard walks all `*.py` files under `web/` checking for module-top imports of forbidden modules

## Test Run Output

```
tests/test_web_healthz.py ................  [100%]
16 passed in 0.17s

Full suite: 697 passed in 94.78s
```

### Test Classes (16 tests)

| Class | Tests | Covers |
|-------|-------|--------|
| TestHealthzHappyPath | 5 | D-13..D-15: 200, JSON, exact keys, status=ok, YYYY-MM-DD |
| TestHealthzMissingStatefile | 2 | D-15: missing state -> last_run=null, stale=false |
| TestHealthzStaleness | 4 | D-16: >2 days=stale, today=fresh, exactly 2 days=fresh, None=fresh |
| TestHealthzDegradedPath | 3 | D-19: 200 on exception, degraded body, WARN [Web] log |
| TestWebHexBoundary | 2 | AST guard: no hex-core imports, state_manager must be local |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Docstring in web/app.py contained 'state_manager' text triggering grep acceptance criterion**
- **Found during:** Task 2 verification
- **Issue:** Plan acceptance criterion `grep -c 'state_manager' web/app.py` = 0. The module docstring included the word `state_manager` in the allowed-imports note.
- **Fix:** Rephrased docstring line to `Allowed web imports: fastapi, stdlib, read-only state access via healthz handler.`
- **Files modified:** web/app.py
- **Commit:** 448c956

**2. [Rule 1 - Bug] Docstring in web/routes/healthz.py contained 'datetime.fromisoformat' triggering grep acceptance criterion**
- **Found during:** Task 2 verification
- **Issue:** Plan acceptance criterion `grep -c 'datetime.fromisoformat' web/routes/healthz.py` = 0. The D-16 docstring note included the phrase `NOT datetime.fromisoformat`.
- **Fix:** Rephrased to `date.fromisoformat (date-only, REVIEWS HIGH #1)`.
- **Files modified:** web/routes/healthz.py
- **Commit:** 448c956

**3. [Rule 1 - Bug] Same docstring created a second '_date.fromisoformat' occurrence**
- **Found during:** Task 2 verification (second grep pass)
- **Issue:** Plan acceptance criterion `grep -c '_date.fromisoformat' web/routes/healthz.py` = 1. After fix #2, the docstring still said `_date.fromisoformat` (count became 2 — docstring + actual code).
- **Fix:** Changed docstring wording to `date.fromisoformat (date-only, REVIEWS HIGH #1)` — no underscore prefix in the prose.
- **Files modified:** web/routes/healthz.py
- **Commit:** 448c956 (same commit, fixed before committing)

## Known Stubs

None — /healthz reads live state.json via load_state() with no hardcoded/placeholder data.

## Threat Flags

None. All new surface is within the T-11-01, T-11-05, T-11-07 threat register entries already declared in the plan.

## Self-Check: PASSED
