---
phase: 13
plan: 05
subsystem: web/dashboard
tags: [dashboard, file-response, mtime, regen, hex-boundary, wave-2]
requires:
  - "Plan 13-01 autouse WEB_AUTH_SECRET fixture (tests/conftest.py)"
  - "Plan 13-01 hex-boundary update (FORBIDDEN_FOR_WEB minus 'dashboard')"
  - "Plan 13-01 4 skeleton test files including tests/test_web_dashboard.py"
  - "Plan 13-02 web/app.py factory wiring (registers dashboard route + AuthMiddleware)"
  - "Plan 13-02 web/routes/dashboard.py stub (503 placeholder)"
provides:
  - "GET / serving dashboard.html via FileResponse with text/html; charset=utf-8 (D-07)"
  - "_is_stale() module-private helper using os.stat(...).st_mtime_ns strict-greater (D-08)"
  - "Lazy regen path: render_dashboard(load_state()) called only when state.json mtime > dashboard.html mtime (D-07/D-08)"
  - "D-10 never-crash: render exception → WARN [Web] log + serve stale 200; missing dashboard.html → 503 plain-text 'dashboard not ready'"
  - "Local imports of dashboard.render_dashboard + state_manager.load_state inside handler (Phase 11 C-2 + D-07 hex-boundary extension)"
  - "12 contract tests across 4 classes (TestDashboardResponse, TestStaleness, TestRenderFailure, TestFirstRun)"
  - "SC-2 bytes-equality lock: TestStaleness::test_stale_state_triggers_regen_and_serves_regenerated_bytes asserts response body == regenerated file bytes (REVIEWS MEDIUM #3)"
affects:
  - web/routes/dashboard.py
  - tests/test_web_dashboard.py
tech-stack:
  added: []
  patterns:
    - "FileResponse for cached file serving with auto ETag/Last-Modified/Content-Length/conditional-GET"
    - "os.stat(path).st_mtime_ns nanosecond mtime comparison with FileNotFoundError handling on both files"
    - "Local-import inside handler (Phase 11 C-2) extended to include `from dashboard import render_dashboard` per Phase 13 D-07 hex-boundary promotion"
    - "Test fixture `client_with_dashboard` uses tmp_path + monkeypatch.chdir + os.utime to control mtimes deterministically without mocking os.stat"
    - "Two-axis stale-path assertion (regen-call-count AND served-bytes-equality) — REVIEWS MEDIUM #3 SC-2 lock"
key-files:
  created: []
  modified:
    - web/routes/dashboard.py
    - tests/test_web_dashboard.py
decisions:
  - "Plan-as-written `from conftest import AUTH_HEADER_NAME, VALID_SECRET` fails because pytest's `testpaths=['tests']` does not put tests/ on sys.path (same root cause that bit Plan 13-02). Inlined the constants in tests/test_web_dashboard.py with comments pointing to tests/conftest.py as the conceptual single-source. The autouse fixture from conftest.py still runs because pytest's conftest discovery is path-walk based, not import based — so WEB_AUTH_SECRET is set before each test."
  - "Local fixture `auth_headers` in test_web_dashboard.py shadows the conftest-provided `auth_headers` fixture with identical behaviour. Keeps the test file self-documenting; both definitions resolve to `{AUTH_HEADER_NAME: VALID_SECRET}`."
  - "Stale-path test uses real wall-clock times (`time.time()` ± 60s) rather than fixed nanosecond constants. Rationale: any mtime_ns semantics bug in the handler still trips the staleness check at a 60-second separation; fixed-constant tests like the fresh-path use nanosecond constants because correctness is in mtime ordering, not absolute value."
  - "TestRenderFailure constructs its own client (not via client_with_dashboard fixture) so it can install an exploding render_dashboard before TestClient instantiation — cleaner than re-monkeypatching after fixture setup."
  - "Code comment `# regen (above) completes BEFORE this FileResponse is constructed` pinned at the FileResponse line, locking the SC-2 invariant against future refactors that might move regen into a background task."
metrics:
  duration: "~6m"
  tasks: 2
  files_created: 0
  files_modified: 2
  tests_added: 12
  completed: 2026-04-25
---

# Phase 13 Plan 05: GET / Dashboard Implementation Summary

Last production task of Phase 13. Replaces the Plan 13-02 503 stub at `web/routes/dashboard.py` with the full GET / handler implementing D-07..D-11, and populates `tests/test_web_dashboard.py` with 12 contract tests including the REVIEWS MEDIUM #3 SC-2 bytes-equality lock.

## What Was Done

### Task 1 — Real GET / handler (commit `40e154d`)

**`web/routes/dashboard.py` rewritten** (was 33-line stub returning 503 unconditionally; now ~110 lines including module docstring):

- **Module docstring** enumerates D-07..D-11 contract terms verbatim, plus the SC-2 lock paragraph and the architecture/hex-boundary block (web/ allowed imports + forbidden imports + local-import C-2 reminder).
- **`_is_stale()` module-private helper** (D-08):
  - `os.stat(_DASHBOARD_PATH).st_mtime_ns` and `os.stat(_STATE_PATH).st_mtime_ns` for nanosecond-precision compare
  - FileNotFoundError on dashboard.html → returns True (caller handles 503)
  - FileNotFoundError on state.json → returns False (no state → don't regen)
  - Strict `state_mtime > html_mtime` (not `>=`) — equal mtimes do NOT regen
- **`get_dashboard()` handler:**
  - Local imports: `from dashboard import render_dashboard` and `from state_manager import load_state` INSIDE the handler body (Phase 11 C-2 + D-07 hex extension)
  - Try/except wrapping `render_dashboard(load_state())` with `# noqa: BLE001 — D-10 never-crash`
  - WARN log on exception: `[Web] dashboard regen failed, serving stale: <ExcType>: <msg>`
  - 503 path: `os.path.exists(_DASHBOARD_PATH)` False → `PlainTextResponse(content='dashboard not ready', status_code=503, media_type='text/plain; charset=utf-8')`
  - 200 path: `FileResponse(_DASHBOARD_PATH, media_type='text/html; charset=utf-8')`
  - Inline comment `# SC-2: regen (above) completes BEFORE this FileResponse is constructed` pins the bytes-equality invariant against future refactors

### Task 2 — 12 contract tests (commit `863c289`)

**`tests/test_web_dashboard.py`** populated (was 4 empty class declarations; now 12 passing test methods across 4 classes):

**TestDashboardResponse (4 tests, D-07 + AUTH-01 inheritance):**
- `test_returns_200_with_auth_when_dashboard_exists` — valid auth + dashboard.html present → 200
- `test_content_type_is_html` — Content-Type is `text/html; charset=utf-8`
- `test_body_matches_dashboard_html_contents` — served body byte-equals on-disk dashboard.html
- `test_unauthenticated_returns_401` — no auth header → 401 (proves middleware is reached, not bypassed)

**TestStaleness (4 tests, D-08 + SC-2):**
- `test_fresh_dashboard_is_not_regenerated` — html mtime > state mtime → render_dashboard NOT called (zero invocations)
- **`test_stale_state_triggers_regen_and_serves_regenerated_bytes`** — REVIEWS MEDIUM #3 SC-2 lock: seeds dashboard.html with `<html>stale</html>`, marks state.json 60s ahead, asserts BOTH (a) `r.text == '<html>regenerated</html>'` AND (b) `len(calls) == 1`. Catches both regressions: skipped regen AND served-pre-regen-snapshot.
- `test_equal_mtime_does_not_trigger_regen` — strict `>` semantics: equal mtimes do NOT regen
- `test_state_missing_does_not_regen` — state.json absent → `_is_stale()` returns False → no regen attempt

**TestRenderFailure (1 test, D-10):**
- `test_render_exception_logs_warn_and_serves_stale` — render_dashboard raises RuntimeError → handler catches, logs WARN with `[Web]` + `regen failed` + `RuntimeError`, serves stale `<html>stale-but-served</html>` with 200

**TestFirstRun (3 tests, D-10):**
- `test_missing_dashboard_returns_503` — no dashboard.html on disk → 503
- `test_503_body_is_dashboard_not_ready` — body literal == `dashboard not ready`
- `test_503_content_type_is_text_plain` — Content-Type is `text/plain; charset=utf-8`

**Fixture infrastructure:**
- `client_with_dashboard` fixture uses `monkeypatch.chdir(tmp_path)` so the handler's relative paths (`'dashboard.html'`, `'state.json'`) resolve into the temporary directory rather than polluting the repo root
- `_track_render` writer captures regen invocations AND writes deterministic `<html>regenerated</html>` so bytes-equality assertions can verify served content matches regenerated content
- `_set_mtime_ns(path, mtime_ns)` helper centralizes `os.utime(path, ns=(mtime_ns, mtime_ns))` calls for deterministic mtime control

## Why This Matters

Plan 13-05 lands the last production task of Phase 13. With this plan complete:

1. **GET / is fully implemented end-to-end** — dashboard.html served behind auth, lazy regen on staleness, never-crash on render failure, 503 on first-run before any signal run has rendered.
2. **All five Phase 13 success criteria are programmatically verifiable** through the test suite:
   - SC-1 (401 without/wrong header) → TestAuthRequired in Plan 13-03
   - **SC-2 (regen on stale AND served bytes equal regen bytes)** → TestStaleness::test_stale_state_triggers_regen_and_serves_regenerated_bytes (this plan, REVIEWS MEDIUM #3)
   - SC-3 (state.json key set preserved verbatim) → TestStateResponse in Plan 13-04
   - SC-4 (/healthz exempt) → TestExemption in Plan 13-03
   - SC-5 (audit log shape) → TestAuditLog in Plan 13-03
3. **The bytes-equality assertion catches a class of subtle regressions** that the original plan-as-written test would have missed. A handler that regens but then constructs FileResponse from a pre-regen buffer (e.g., reads bytes once, writes file, returns the in-memory bytes) would pass the regen-call-count test but fail bytes-equality. Conversely, a handler that skips regen but happens to serve correct stale bytes would fail regen-call-count.
4. **Phase 14's HTMX mutations and Phase 15's calculator/sentinels** can land on a stable `GET /` contract — the regen invariant means any state mutation will reflect in the dashboard on the next request.

## Verification Results

- `pytest tests/test_web_dashboard.py -x -v` → **12 passed in 0.21s**
- `pytest tests/test_web_dashboard.py::TestDashboardResponse -x -q` → **4 passed**
- `pytest tests/test_web_dashboard.py::TestStaleness -x -q` → **4 passed** (including REVIEWS MEDIUM #3 bytes-equality lock)
- `pytest tests/test_web_dashboard.py::TestRenderFailure -x -q` → **1 passed**
- `pytest tests/test_web_dashboard.py::TestFirstRun -x -q` → **3 passed**
- `pytest tests/test_web_dashboard.py -x -k 'stale'` → **5 passed, 7 deselected** (REVIEWS MEDIUM #3 stale test passes specifically)
- `pytest tests/test_web_*.py -x -q` → **69 passed in 0.36s** (full Phase 11+13 web suite green; Plans 02..05 compose without conflict)
- `pytest tests/test_web_healthz.py::TestWebHexBoundary -x -q` → **3 passed** (`test_web_modules_do_not_import_hex_core`, `test_dashboard_is_not_forbidden_for_web_phase_13_D07`, `test_web_adapter_imports_are_local_not_module_top` all green — the AST guards approve dashboard.py local imports + dashboard no longer in FORBIDDEN_FOR_WEB)
- `pytest tests/test_signal_engine.py::TestDeterminism` → **44 passed** (hex boundary on pure-math hexes preserved — no regression from web layer touch)
- `python -c "from web.routes.dashboard import register, _is_stale; print('OK')"` → `OK` (clean module import)

**Acceptance grep checks all pass:**
- `grep -q "Served stale bytes after regen" tests/test_web_dashboard.py` → match (REVIEWS MEDIUM #3 assertion message present)
- `grep -q "test_stale_state_triggers_regen_and_serves_regenerated_bytes" tests/test_web_dashboard.py` → match
- `grep -q "st_mtime_ns" web/routes/dashboard.py` → 3 matches (one in `_is_stale` html branch, one in state branch, one in docstring)
- `grep -q "FileResponse" web/routes/dashboard.py` → match (import + invocation + docstring refs)
- `grep -q "dashboard not ready" web/routes/dashboard.py` → match (D-10 503 body literal)
- `grep -c "BLE001" web/routes/dashboard.py` → 1 (D-10 never-crash annotation)
- `grep -c "@app.get('/')" web/routes/dashboard.py` → 1
- `grep -c "os.utime" tests/test_web_dashboard.py` → 5 (in `_set_mtime_ns` helper + direct calls in stale and render-failure tests)

## Decisions Made

1. **Inlined `VALID_SECRET` + `AUTH_HEADER_NAME` constants in tests/test_web_dashboard.py** instead of `from conftest import` (Rule 1 deviation — see below). Same root cause as Plan 13-02: pytest's `testpaths=['tests']` does not put tests/ on sys.path, so `from conftest import ...` fails at test collection. The autouse fixture from conftest.py still runs because conftest discovery is path-walk based, so WEB_AUTH_SECRET is set before each test.

2. **Local `auth_headers` fixture in test file** shadows the conftest-provided `auth_headers` fixture with identical behaviour. Both definitions resolve to `{AUTH_HEADER_NAME: VALID_SECRET}`. Keeps the test file self-documenting; cost is one duplicate fixture definition.

3. **Stale-path bytes-equality test uses real wall-clock times** (`time.time()` ± 60 seconds) rather than fixed nanosecond constants. Rationale: a 60-second separation between mtimes is unambiguously stale regardless of any subtle mtime_ns semantics bug in the handler. The other staleness tests (fresh, equal, missing-state) use fixed nanosecond constants because they test mtime ORDERING (strict greater-than vs equal) where absolute values don't matter.

4. **TestRenderFailure builds its own client** (not via the `client_with_dashboard` fixture) so it can install an exploding `render_dashboard` BEFORE `create_app()` is invoked. Cleaner than re-monkeypatching after fixture setup; avoids any risk of the fixture's `_track_render` having been bound first.

5. **Code comment `# SC-2: regen (above) completes BEFORE this FileResponse is constructed`** pinned at the FileResponse line. Future contributors reading the handler will see the invariant explicitly. If anyone moves regen into a background task or reorders operations, code review will flag the comment becoming stale and the test will fire.

6. **`_track_render` fixture writer creates dashboard.html with deterministic content** (`<html>regenerated</html>`). Without this, the bytes-equality assertion would have nothing to assert against — the real `render_dashboard` produces different output every invocation (timestamps, etc.). The deterministic stub gives the test a precise byte-equal target.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `from conftest import` fails at test collection**
- **Found during:** Task 2 first `pytest` run (immediately after writing test bodies as plan-specified)
- **Issue:** Plan specified `from conftest import AUTH_HEADER_NAME, VALID_SECRET`. In this project, `pyproject.toml` has `testpaths = ['tests']` but does not configure `pythonpath` or `rootdir` to expose tests/ as an importable package. Result: `ModuleNotFoundError: No module named 'conftest'` at collection, blocking all 12 tests. Same root cause as Plan 13-02 deviation #1.
- **Fix:** Replaced `from conftest import AUTH_HEADER_NAME, VALID_SECRET` with local mirror constants:
  ```python
  VALID_SECRET = 'a' * 32  # D-17 minimum length
  AUTH_HEADER_NAME = 'X-Trading-Signals-Auth'  # AUTH-01 header
  ```
  Comment block points back to `tests/conftest.py` as the conceptual single-source. The autouse `_set_web_auth_secret_for_web_tests` fixture from conftest.py still runs (filename matches `test_web_*.py`), so WEB_AUTH_SECRET is still set before each test in this file. Pattern matches the same fix in `tests/test_web_app_factory.py:21-22` (Plan 13-02 deviation #1).
- **Files modified:** `tests/test_web_dashboard.py` (replaced `from conftest import ...` with mirror constants + commentary)
- **Commit:** `863c289`

### Authentication Gates

None. No external auth required for this plan (no API keys, no Resend calls, no GitHub deploy key interaction).

### Architectural Changes (Rule 4)

None. The plan-defined RESEARCH §Pattern 3 handler body and the 12 plan-specified test methods are fully scoped — no new tables, services, libraries, or auth approaches. No deviation from the locked D-07..D-11 contract.

## Threat Surface

Threats from `13-05-PLAN.md::<threat_model>` mitigated by this plan:

| Threat ID | Mitigation Acceptance |
|-----------|-----------------------|
| T-13-09 (Path canonicalization bypass — `/index`, `///`, `/?foo=bar`) | FastAPI/Starlette path canonicalization handled at middleware layer; TestDashboardResponse::test_unauthenticated_returns_401 verifies the handler is reached (not bypassed) on the canonical `/` path |
| T-13-10c (Tampering: disk-full mid-write produces partial dashboard.html) | dashboard.render_dashboard's existing tempfile + os.replace from Phase 5 is unchanged; FileResponse never streams a half-written file |
| **T-13-10e (Integrity: regen but serve pre-regen bytes)** | **MITIGATED BY THIS PLAN** — code comment pins regen-before-FileResponse ordering; TestStaleness::test_stale_state_triggers_regen_and_serves_regenerated_bytes asserts BOTH regen-call-count AND bytes-equality |

No new threat-flag findings. No new security surface introduced beyond what was scoped by `13-05-PLAN.md`.

## Follow-ups for Future Phases

Per Gemini reviewer suggestion in `13-REVIEWS.md`:
- **Phase 16 hardening:** Add nginx rate-limit zones for `/` and `/api/state` (currently only `/healthz` is rate-limited per Phase 12 D-10). Defense-in-depth against brute-forcing WEB_AUTH_SECRET. Tracked as a Phase 16 docs-sweep item.

## What Comes Next

Phase 13 is now production-complete:
- All 5 Phase 13 SCs (SC-1..SC-5) are programmatically test-locked.
- All 5 Phase 13 requirements (AUTH-01, AUTH-02, AUTH-03, WEB-05, WEB-06) have implementations + tests.
- Wave 2 plans (13-03, 13-04, 13-05) compose cleanly — full Phase 11 + 13 web suite is 69 tests green.

Ready for `/gsd-verify-work 13` to run the close-out review against ROADMAP §Phase 13 SCs and confirm Phase 13 closure. Phase 14 (HTMX mutations) and Phase 15 (calculator + sentinels) inherit a stable GET / contract.

## Self-Check: PASSED

**Files modified (verified content):**
- web/routes/dashboard.py — was 33-line stub, now ~110 lines with full handler body
  - `grep -c "_is_stale" web/routes/dashboard.py` → 2 (definition + invocation)
  - `grep -c "st_mtime_ns" web/routes/dashboard.py` → 3
  - `grep -c "FileResponse" web/routes/dashboard.py` → present (import + invocation + docstring refs)
  - `grep -c "BLE001" web/routes/dashboard.py` → 1
  - `grep -c "@app.get('/')" web/routes/dashboard.py` → 1
- tests/test_web_dashboard.py — was 4 empty class skeleton, now 12 test methods passing
  - `grep -c "  def test_" tests/test_web_dashboard.py` → 12
  - All 12 tests pass under pytest

**Commits (verified in `git log --oneline c7f5c76..HEAD`):**
- `40e154d` feat(13-05): replace GET / stub with real dashboard handler (D-07..D-11)
- `863c289` test(13-05): populate test_web_dashboard.py with 12 contract tests
