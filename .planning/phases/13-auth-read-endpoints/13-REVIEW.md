---
status: clean
critical_count: 0
high_count: 0
medium_count: 0
low_count: 2
info_count: 5
reviewed_at: 2026-04-25
phase: 13
scope: source files changed c7f5c76..HEAD (web/, tests/test_web_*, tests/conftest.py, SETUP-DROPLET.md)
---

# Phase 13 Code Review — Auth + Read Endpoints

**Depth:** standard · **Files reviewed:** 13 · **Verdict:** clean — ship-ready.

## Security review (AUTH — top priority)

| Check | Status |
|-------|--------|
| S1: Timing attack — `hmac.compare_digest` with symmetric bytes | ✓ clean |
| S2: Secret leak in logs / error messages | ✓ clean |
| S3: X-Forwarded-For spoofing given Phase 12 direct-DNS + 127.0.0.1 bind | ✓ safe |
| S4: Path canonicalization for exemption (/healthz/, /HEALTHZ) | ✓ clean — tests lock |
| S5: /openapi.json leak — `openapi_url=None` (D-22) | ✓ closed |
| S6: Fail-open before auth check | ✓ clean (fail-closed) |
| S7: Fail-closed on missing/short `WEB_AUTH_SECRET` | ✓ clean — D-16/D-17 |

## Correctness review

| Check | Status |
|-------|--------|
| C1: Middleware registered LAST so runs FIRST (Starlette reverse) | ✓ clean |
| C2: Local imports inside handlers (hex-boundary C-2) | ✓ clean |
| C3: `st_mtime_ns` precision for staleness | ✓ clean — strict `>` locked by tests |
| C4: Regen completes BEFORE FileResponse (SC-2 bytes-equality) | ✓ clean |
| C5: 503 body `dashboard not ready` + `text/plain; charset=utf-8` | ✓ clean |
| C6: `/api/state` top-level `_*` strip only (D-12) | ✓ clean |
| C7: `Cache-Control: no-store` on `/api/state` (D-13) | ✓ clean |
| C8: `load_state()` direct call without try/except (D-14) | ✓ intentional |

## Quality + hex-boundary review

| Check | Status |
|-------|--------|
| Q1: 2-space indent, single quotes, snake_case | ✓ clean |
| Q2: `[Web]` log prefix | ✓ clean |
| Q3: Module docstrings with decision refs (Phase 11 style) | ✓ clean |
| Q4: No dead code / debug prints / TODO markers | ✓ clean |
| Hex: No forbidden imports in web/ | ✓ clean |
| Hex: TestWebHexBoundary.FORBIDDEN_FOR_WEB dashboard removal (D-07) | ✓ clean |

## Findings

### LOW-01 — `VALID_SECRET` mirrored across 4 test files

**Files:** `tests/conftest.py:29`, `tests/test_web_app_factory.py:21`, `tests/test_web_dashboard.py:29`, `tests/test_web_state.py:23`

REVIEWS LOW #6 flagged this at 2 files; now at 4. Each file redeclares `VALID_SECRET = 'a' * 32` and `AUTH_HEADER_NAME = 'X-Trading-Signals-Auth'` because pytest's `testpaths=['tests']` doesn't put `tests/` on `sys.path`, and each test file documents the drift intentionally. If the constant ever changes (e.g., `_MIN_SECRET_LEN` bumped), 4 files need updating.

**Fix (optional, low priority):** Add `tests/__init__.py` and use `from tests.conftest import ...`. Defer to v1.2 polish.

### LOW-02 — `_log_failure` could mask 401 with 500 on logger misconfig

**File:** `web/middleware/auth.py:69–84`

If stdlib logger handler raised (extremely unlikely), it would propagate through `dispatch()` and produce 500 instead of 401. Fail-CLOSED, so security preserved — but audit-log visibility lost for a misbehaving log handler.

**Fix (optional polish):** Wrap `_log_failure(request)` in try/except. Consider for v1.2 if structured logging / remote shipping is introduced.

### INFO

- **INFO-01:** `_log_failure` is `@staticmethod` — correctly doesn't receive `self`, avoids any risk of accidentally logging `self._secret_bytes`.
- **INFO-02:** 503 path can trigger if `render_dashboard` silently no-ops without raising (disk full + swallowed exception). Deliberate design — better to 503 than serve half-written file.
- **INFO-03:** Test regex `re.search(r"ua='(X+)'", m)` is greedy — fine for ASCII; Python `repr` is deterministic.
- **INFO-04:** `web/middleware/__init__.py` is empty (zero bytes) — matches Phase 11 convention for package markers.
- **INFO-05:** `web/app.py:101` has module-level `app = create_app()` for `uvicorn web.app:app` compatibility. Tests must `sys.modules.pop('web.app', None)` before re-importing for env-var failure path tests. Works, but `uvicorn --factory web.app:create_app` would remove the import-side-effect. v1.2 candidate.

## Top 3 concerns (all LOW)

1. LOW-01: `VALID_SECRET` mirroring — documented intentional, single-source via `tests/__init__.py` would be cleaner.
2. LOW-02: `_log_failure` could mask 401 with 500 on logger misconfig — unlikely in practice.
3. INFO-05: Module-level `create_app()` side-effect on import — tests workaround works, `--factory` flag would be cleaner for v1.2.

**Verdict:** Ship Phase 13 as-is. No critical/high/medium. LOW items can go to deferred-items.md or v1.2 polish backlog.
