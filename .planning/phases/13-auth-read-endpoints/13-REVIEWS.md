---
phase: 13
reviewers: [gemini, codex]
skipped_reviewers: [claude]
skip_reason: "Running inside Claude Code — claude CLI skipped for independence"
reviewed_at: 2026-04-25
plans_reviewed:
  - 13-01-PLAN.md
  - 13-02-PLAN.md
  - 13-03-PLAN.md
  - 13-04-PLAN.md
  - 13-05-PLAN.md
---

# Cross-AI Plan Review — Phase 13: Auth + Read Endpoints

## Gemini Review

### Summary
The five plans for Phase 13 are high-quality, technically robust, and ready for execution. The strategy follows a disciplined Wave 0/1/2 structure that prioritizes test-infrastructure readiness (Wave 0) before modifying the application factory (Wave 1), ensuring existing health checks don't break. The research-backed extension to suppress `/openapi.json` (D-22) is correctly captured, closing a common FastAPI security gap. The use of `os.utime` for deterministic mtime testing and the AST-guard for `hmac.compare_digest` demonstrate a senior engineering approach to security and reliability.

### Strengths
- **Fail-Closed Security:** Plan 13-02 (D-16/D-17) correctly implements startup-time validation for `WEB_AUTH_SECRET`, ensuring the service refuses to bind if misconfigured.
- **Robust Staleness Logic:** Plan 13-05 (D-08) uses `st_mtime_ns` for nanosecond-precision comparison and accounts for `FileNotFoundError` scenarios on both `state.json` and `dashboard.html`.
- **Comprehensive Testing:** Plans 13-03 through 13-05 include granular unit tests for audit logs (including XFF parsing and UA truncation), Cache-Control headers, and JSON compactness.
- **Infrastructure Alignment:** Plan 13-01 Task 3 correctly identifies the need to insert the auth secret setup step *before* the sudoers step in `SETUP-DROPLET.md`, aligning with systemd `EnvironmentFile` requirements.
- **Hex Boundary Enforcement:** The plans correctly handle the promotion of `dashboard` to an allowed import for the web layer while maintaining the local-import invariant (Phase 11 C-2).

### Concerns
- **LOW — UA Representation:** Plan 13-03 Task 2 (D-05) uses `%r` for User-Agent logging. While this escapes control characters, it wraps the string in quotes (e.g., `ua='curl/7.0'`). This is intentional and correct per the plan, but reviewers of the audit log should be aware that the `120` char limit applies to the inner string, and the total log field will be slightly longer due to the `ua='...'` template.
- **LOW — X-Forwarded-For Spoofing:** As noted in 13-RESEARCH Pitfall 3, taking the first entry of `X-Forwarded-For` assumes nginx is the only proxy. Since Phase 11 binds uvicorn to `127.0.0.1`, this is safe (direct-to-origin is blocked). If the bind address is ever changed to `0.0.0.0` for debugging, the audit log IP becomes spoofable. The plans handle this correctly for the current architecture.

### Suggestions
- **Nginx Rate-Limit Follow-up:** Phase 12 only rate-limited `/healthz`. Phase 13 CONTEXT §Claude's Discretion suggests adding rate-limiting for `/` and `/api/state` at the nginx layer. While deferred to Phase 16 hardening in the plan, it is recommended to add a TODO in the `13-05-SUMMARY.md` to ensure this defense-in-depth isn't forgotten during the Phase 16 docs-sweep.
- **Dashboard Empty State Body:** In Plan 13-05 Task 2 (TestFirstRun), ensure the 503 body assertion is byte-exact. The plan specifies `dashboard not ready`. Confirm this matches the stub in Plan 13-02 (Task 1 Step C) exactly. (Verified: both plans use the same string).

### Risk Assessment
**LOW** — Plans preserve existing `/healthz` behavior, rely on proven atomic-write semantics, use stdlib crypto, maintain single-writer invariant, and provide stale-fallback for dashboard regeneration failure. Dependency chain well-defined; Wave 2 parallelization safe (disjoint files).

---

## Codex Review

### Summary
The plans are mostly strong: the phase boundary is clear, D-22 (`openapi_url=None`) is correctly captured, the wave split is sane, and the web-layer AST guard is being changed in the right place (`tests/test_web_healthz.py`, not `tests/test_signal_engine.py`). Readiness is close, but not quite execution-safe: Wave 0 misses a real dependency break in the existing healthz tests once `web.app` starts fail-closing on missing `WEB_AUTH_SECRET`, and a couple of success criteria are only partially locked by tests rather than verbatim.

### Strengths
- 13-02 correctly captures the late-discovered FastAPI gotcha: `docs_url=None` + `redoc_url=None` is not enough; `openapi_url=None` is required for D-22.
- 13-01 updates the web hex-boundary guard in the correct test file (`tests/test_web_healthz.py:181`), not `tests/test_signal_engine.py`. Matches the adapter-tier boundary.
- 13-02 and 13-03 use middleware as the sole auth chokepoint (D-01) — right posture for future Phase 14/15 routes.
- 13-03's log-shape assertions are appropriately concrete: XFF first entry, 120-char UA truncation, `%r` escaping, no `WWW-Authenticate`.
- 13-04 keeps `/api/state` read-only and uses local `state_manager` import, consistent with Phase 10 D-15.
- 13-05's dashboard design is pragmatic: `os.stat(...).st_mtime_ns`, `FileResponse`, stale-on-render-failure, 503 on first run. No unnecessary locking or cache layer.
- Scope is disciplined. No JWT/session/OAuth/lockout creep.

### Concerns
- **HIGH — 13-01 fixture retrofit is insufficient.** Task 1 only retrofits the `app_instance` fixture, but the existing healthz file imports `create_app()` directly in many test bodies at `tests/test_web_healthz.py:62-178`. Once `web/app.py` keeps `app = create_app()` at module import, those tests will still explode before the fixture helps. **Verified:** 11 direct `create_app()` invocations exist at lines 70, 83, 90, 105, 115, 126, 133, 148, 159, 172. Affected: D-16, D-18.
- **MEDIUM — 13-04 does not fully prove ROADMAP SC-3 verbatim.** The planned tests check underscore stripping and some preserved keys, but they do not assert the full top-level key set expected from `/api/state`. A regression could silently drop `warnings`, `contracts`, or `equity_history` and still pass. Affected: 13-04 Task 2, WEB-06, SC-3.
- **MEDIUM — 13-05 proves regen call count, but not that the response body is the regenerated file bytes on the stale path.** If the handler regens and still serves the old file in the same request window, the current stale test could miss it. Affected: 13-05 Task 2, D-07/D-08, SC-2.
- **MEDIUM — SC-5 is only partially test-locked.** 13-03 validates Python log records with `caplog`, but not actual journald wiring or nginx `X-Forwarded-For` propagation. The code contract is tested, but the SC-5 text using `journalctl -u trading-signals-web ...` is not actually satisfied end-to-end. (VALIDATION.md does flag this as Manual-Only.) Affected: 13-03, AUTH-03, SC-5.
- **LOW — 13-03 omits a near-miss exemption test for D-02**, e.g. `/healthz/` or `/HEALTHZ` must not bypass auth. The threat model mentions this, but no explicit test method is planned. Affected: 13-03, D-02, T-13-03d.
- **LOW — 13-01 introduces `VALID_SECRET` in both `tests/conftest.py` and `tests/test_web_healthz.py`.** Harmless but drift-prone. Affected: 13-01 Task 1/2, D-17.

### Suggestions
- **Fix Wave 0 by making auth env setup global for web tests.** Add an autouse fixture in `tests/conftest.py`:
  ```python
  @pytest.fixture(autouse=True)
  def _set_web_auth_secret_for_web_tests(monkeypatch, request):
    if 'test_web_' in str(request.node.fspath):
      monkeypatch.setenv('WEB_AUTH_SECRET', VALID_SECRET)
  ```
  Or rewrite the direct-import healthz tests at lines 62-178 to accept `monkeypatch` and set env before `from web.app import create_app`.
- **Add one SC-3 exact-shape test in 13-04** that asserts `set(r.json().keys()) == {'schema_version', 'account', 'last_run', 'positions', 'signals', 'trade_log', 'equity_history', 'warnings', 'contracts'}`.
- **Tighten 13-05 stale-path verification** — assert served bytes after regen: `assert r.text == '<html>regenerated</html>'` AND `assert len(calls) == 1`.
- **Add a D-02 trailing-slash negative test in 13-03**: `r = client_with_auth.get('/healthz/', follow_redirects=False)` → `r.status_code in (401, 307)`.
- **Carry SC-5 operational verification into docs.** Manual check step: `curl -H 'X-Trading-Signals-Auth: wrong' -H 'X-Forwarded-For: 1.2.3.4' https://signals.<domain>/` then `journalctl -u trading-signals-web -n 20 --no-pager | grep 'auth failure'`.
- **Single source of truth for `VALID_SECRET`** — have `tests/test_web_healthz.py` import it from `tests/conftest.py` instead of redefining it.

### Risk Assessment
**MEDIUM** — Architecture and most contracts are well thought through, no obvious scope creep. Main issue is execution safety: 13-01 will not actually prevent pre-existing healthz test failures after D-16 lands, and a couple of success criteria are not fully locked verbatim by tests. Fixable before implementation, but reviewer would not execute the plans unchanged.

---

## Consensus Summary

### Agreed Strengths (mentioned by both reviewers)
- D-22 (`openapi_url=None` extension) correctly captured in Plan 13-02 — closes a common FastAPI security gap.
- Hex-boundary AST guard correctly updated in `tests/test_web_healthz.py` (web-tier), not `tests/test_signal_engine.py` (pure-math tier).
- D-01 middleware-as-sole-chokepoint is the right posture for Phase 14/15 future routes.
- Wave 2 parallelization is safe — disjoint files, no merge risk.
- Pragmatic dashboard regen design (mtime check, FileResponse, stale fallback, 503 first-run).

### Agreed Concerns

**HIGH severity (codex-only, but verified — gemini missed it):**
1. **Plan 13-01 fixture retrofit is insufficient.** 11 existing healthz tests import `create_app()` directly inside test bodies (lines 70, 83, 90, 105, 115, 126, 133, 148, 159, 172). After D-16 fail-closed lands, all 11 break. Fix: add an autouse `monkeypatch.setenv('WEB_AUTH_SECRET', VALID_SECRET)` fixture in `tests/conftest.py` scoped to `test_web_*` files.

**MEDIUM severity (codex):**
2. SC-3 not fully locked — Plan 13-04 tests don't assert full top-level key set verbatim; a regression could silently drop `warnings`/`contracts`/`equity_history`.
3. SC-2 stale-path body assertion missing — Plan 13-05 verifies regen count but not that the served response is the regenerated bytes.
4. SC-5 only partially test-locked — `caplog` covers Python log shape but not journald/nginx wiring (mitigated by VALIDATION.md Manual-Only entries; consider explicit doc step).

**LOW severity:**
5. 13-03 missing `/healthz/` (trailing slash) and `/HEALTHZ` (case) negative-exemption tests for D-02 (codex).
6. `VALID_SECRET` constant defined in two places (codex).
7. `%r` UA logging adds quote chars beyond the 120-char inner truncation — documentation-level note (gemini).
8. XFF first-entry parse is safe given uvicorn binds 127.0.0.1, but breaks if bind ever changes to 0.0.0.0 (gemini).

### Divergent Views
- **Risk level:** Gemini = LOW, Codex = MEDIUM. The divergence is driven by the HIGH finding (#1 above). Codex caught a real issue; Gemini's review was at a higher abstraction level and missed the line-count detail. **Trust codex's MEDIUM — the HIGH issue is real and verified.**

### Recommended Path Forward

The HIGH issue and three MEDIUMs are all addressable with targeted plan revisions, not a full replan. Two options:

**Option A — Edit plans inline** (fastest if comfortable with manual edits):
1. Plan 13-01 Task 1 — replace fixture-only retrofit with autouse-fixture pattern in conftest.py (codex's snippet).
2. Plan 13-04 Task 2 — add `test_full_top_level_key_set_preserved_except_runtime_keys` with `set(r.json().keys()) == {...}` assertion.
3. Plan 13-05 Task 2 — add bytes-equality assertion on stale-path regen test.
4. Plan 13-03 Task 2 — add `test_healthz_trailing_slash_is_not_exempt` and `test_healthz_uppercase_is_not_exempt`.
5. Optional: dedupe `VALID_SECRET` import.

**Option B — Replan with `--reviews` flag** (cleaner audit trail, longer):
```
/gsd-plan-phase 13 --reviews
```
This re-runs the planner with REVIEWS.md as input and lets it produce updated plan files automatically. Plan-checker will re-verify.

**Recommendation: Option B.** The HIGH issue alone justifies a planner pass — automated revisions are auditable and the planner can re-thread the autouse fixture into Plan 13-01's frontmatter `files_modified` correctly. Option A risks missing a downstream consequence.
