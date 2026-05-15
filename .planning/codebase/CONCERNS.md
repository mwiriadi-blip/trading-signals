# Codebase Concerns

**Analysis Date:** 2026-05-15

## Tech Debt

**Static market allowlist breaks on new market additions:**
- Issue: `_VALID_TRACE_INSTRUMENT_KEYS` in `web/routes/dashboard.py::_resolve_trace_open` and `_TRACE_OPEN_PLACEHOLDER` were hardcoded frozensets containing only `{'SPI200','AUDUSD'}`. Any market added after Phase 17 would silently fail trace-panel open/close persistence, even if per-market settings existed.
- Files: `web/routes/dashboard.py::_resolve_trace_open`, `dashboard_legacy/render_helpers.py`
- Impact: Multi-market support (Phase 25+) broke trace panel state on new markets. iOS Safari would reload with panels collapsed, desktop Chrome would show stale state. Users would lose market-specific trace preferences on every page reload.
- Fix approach: Replace static frozensets with regex-based validation (`_MARKET_ID_RE.fullmatch`). Replace `_TRACE_OPEN_PLACEHOLDER` dict with `_TraceOpenPlaceholderMap` that generates placeholders dynamically for any valid market ID. Bump cookie `Max-Age` from 90d to 1y. When adding a new market-scoped render path, run `pytest -k trace_details` to verify end-to-end.

**Trace panel hardcodes gate thresholds instead of reading resolved params:**
- Issue: `dashboard_legacy/render_helpers.py::_render_trace_panels` and vote-line renderer hardcoded `ADX_GATE_THRESHOLD = 25.0` and momentum-vote logic as `v > 0` instead of reading what the engine actually computed. When per-market overrides exist (e.g., `settings['adx_gate']: 20.0`), the trace panel would show the wrong gate value and signal decision.
- Files: `dashboard_legacy/render_helpers.py`, `signal_engine.py::get_signal`, `daily_run.py`
- Impact: Trace panel audits were unreliable. A trade with `adx_gate: 20.0` override would display "ADX 18.66 >= 25 FAIL" (lying about why the signal was generated). Same drift on Mom votes. The lie scaled with every per-market override added.
- Fix approach: `signal_engine.resolve_vote_params(settings)` returns the resolved 4-tuple (adx_gate, momentum_threshold, momentum_votes_required, direction_mode). `get_signal` calls it once; `daily_run.py` persists result as `sig['vote_params']`. Renderer reads from `vote_params`, not re-derives from defaults. Defensive fallback to 25.0/0.02 for old state.json rows. When a renderer audits an engine decision, it MUST read the recorded inputs+outputs, not re-derive.

**Mutual recursion risk: mutate_state is non-reentrant:**
- Issue: `state_manager.mutate_state` uses `fcntl.LOCK_EX` to serialize writes. If a function inside the closure calls `mutate_state` again (e.g., helper that reads state, takes external action, then writes), the same process tries to re-acquire the same lock and blocks forever (undefined behavior on non-reentrant POSIX locks).
- Files: `state_manager/__init__.py::mutate_state`, `state_manager/io.py`, `main.py::_apply_daily_run`, `per_user_fanout.py`
- Impact: Phase 20 RESEARCH discovered that calling `_evaluate_paper_trade_alerts` from inside `mutate_state` would deadlock. Any future orchestrator helper that needs (1) read state, (2) take external action (email, HTTP), (3) write conditional updates would silently deadlock.
- Fix approach: Two-phase commit: (1) main mutation inside `mutate_state`, (2) external action OUTSIDE the closure, (3) secondary `mutate_state` for any state changes after the external action. Insertion point for Phase 20+ is between `mutate_state` return at `main.py:1404` and `_render_dashboard_never_crash` at `main.py:1421`. Document the non-reentrancy contract at every `mutate_state` call site. When in doubt, grep: any `mutate_state` inside another closure is forbidden.

## Known Bugs

**HTMX form fallback to GET breaks invite-revoke:**
- Symptom: POST `/admin/invite/revoke/{token}` via HTMX was silently falling back to GET on iOS Safari, so revoke requests were ignored. Admin would click "revoke" and nothing would happen.
- Files: `web/routes/admin/invite.py`, `web/middleware/auth.py::_is_browser_navigation`
- Root cause: HTMX sends `HX-Request: true` header, but older iOS Safari doesn't recognize it. Middleware tries `Sec-Fetch-Mode: navigate` detection (Safari 16.4+), misses older versions, falls back to GET.
- Workaround: Middleware now checks `Accept: text/html` as secondary detection path (older Safari always sends it). Route adds `HX-Redirect` header on success so HTMX receives a redirect target and the row is removed client-side.
- Prevention: When a route changes from GET-safe to POST-required, test on actual iOS device or use BrowserStack. The Sec-Fetch fallback + Accept substring check handles Safari 14.1+ through current.

## Security Considerations

**Hex boundary violation risk: dashboard.py importing auth logic:**
- Risk: Phase 16.1 D-13 needs `dashboard.py::render_dashboard` to render auth-aware UI (sign-out button vs. "Signed in via Basic Auth" note). Naive option is to import cookie-validation logic into `dashboard.py`, violating the hex-lite boundary (dashboard is a top-level adapter, not web-layer).
- Files: `dashboard.py`, `web/middleware/auth.py`, `web/routes/dashboard.py`
- Current mitigation: `render_dashboard` accepts `is_cookie_session: bool` parameter. `web/routes/dashboard.py::get_dashboard` calls `_validate_cookie` to compute the bool, passes it in. No cookie-decoding inside dashboard.py; auth primitives stay in `web/`.
- Recommendations: Enforce via `tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent` AST walker. Any import of `web/middleware/`, `itsdangerous`, `hmac`, `hashlib`, `os.environ` into `dashboard.py` must fail the test. Extend the forbidden-imports list when new auth dependencies are added.

**XSS injection in trace-panel headers via market ID:**
- Risk: `_MARKET_ID_RE` validation gates trace-panel rendering and market-switcher dropdowns. If a market ID containing `<script>` passes the regex, it would render unescaped in HTML.
- Files: `web/routes/dashboard.py::_resolve_trace_open`, `dashboard_renderer/components/header.py`, `system_params.py`
- Current mitigation: Regex enforces alphanumeric + underscore only: `^[A-Z0-9_]+$`. Any character that isn't in the regex is rejected before rendering.
- Recommendations: Phase 27 #13 review confirmed regex tightness. If the regex is loosened to support new market identifiers (e.g., to allow `-` or `.`), the change must be flagged in code review. Run `pytest -k xss` to verify escaping on all market-name render paths.

## Performance Bottlenecks

**Trade log growth → dashboard HTML size → page load latency:**
- Problem: `state['trade_log']` grows unbounded. Dashboard embeds the entire log in the HTML (1 row per trade rendered as table rows). After ~1000+ trades, dashboard TTFB degrades noticeably.
- Files: `dashboard.py`, `dashboard_legacy/render_helpers.py::_render_trade_table`, `web/routes/dashboard/__init__.py`
- Cause: No pagination or truncation on embedded trade log. Dashboard rendering is single-pass HTML generation; no lazy-loading.
- Improvement path: (1) Embed only the last 200 trades in the dashboard by default. (2) Full log available as a separate `.jsonl` file (stored alongside `state.json`). (3) Optional `/trades/full` route for admin to download full history. Not urgent (app is single daily run + small F&F user base), but becomes critical at >500 trades.

**yfinance lazy import workaround adds complexity:**
- Problem: yfinance is heavy (~30+ submodules). `python main.py --version` was loading the library unnecessarily, adding 300ms+ to cold-start time.
- Files: `data_fetcher.py::_get_yf`, `data_fetcher.py::__getattr__`, `data_fetcher.py::_get_yf_rate_limit_error`
- Cause: Eager module-level import forced lazy-loading workaround with PEP 562 `__getattr__` + memoized `_yf` global + lazy resolver for `YFRateLimitError`.
- Current approach: Lazy import on first `fetch_ohlcv` call. Monkeypatch tests still work because `__getattr__` exposes `data_fetcher.yf`. Catch both module-level proxy exception AND real library exception via `_get_yf_rate_limit_error()`.
- Risk: If yfinance API changes (e.g., exceptions move to a different module), the lazy resolver breaks silently. Safeguard: run `pytest tests/test_data_fetcher.py -v` after any yfinance upgrade to catch exception-resolution mismatches.

## Fragile Areas

**Oracle determinism test locked to exact float64 bit-patterns:**
- Files: `tests/test_signal_engine.py::TestDeterminism`, `tests/oracle/wilder.py`, test fixtures
- Why fragile: Test compares serialized JSON float values byte-for-byte (not approximate equality). Any numpy/pandas upgrade that changes sorting order, rounding, or NaN handling will break the oracle.
- Safe modification: Before upgrading numpy or pandas, regenerate the oracle fixture (run `tests/oracle/regenerate.py`) and re-run determinism tests. If bits shift, it's a pandas/numpy version effect, not a code bug — update the golden fixture and commit. Document the fixture version in the README.
- Test coverage: `TestDeterminism::test_oracle_matches_production_signals` is the load-bearing check. If this passes, signal output is deterministic within the tested version range.

**Multi-phase state schema migrations with no contiguity check:**
- Files: `state_manager/migrations.py::MIGRATIONS`, `state_manager/__init__.py::_assert_migration_chain_contiguous`
- Why fragile: Schema version chain can have gaps (e.g., v5→v7 jump with v6 missing). If a gap exists and `STATE_SCHEMA_VERSION` is bumped to v7, old v5 state files will break during migration orchestration.
- Safe modification: `_assert_migration_chain_contiguous` fires at import time in both `migrations.py` and `__init__.py` (defense-in-depth). Any PR adding a new migration version must have a contiguous chain `vN → vN+1`. CI must enforce via `pytest tests/test_state_manager.py::TestMigrationChain`.
- Test coverage: Schema version monkeypatch tests exercise the chain. If you add v13, v14 must follow immediately — no jumps.

**yfinance 1.2.0 curl_cffi dependency breaks on older requests.Session:**
- Files: `data_fetcher.py`, `requirements.txt`, `tests/fixtures/audusd_400bar.README.md`
- Why fragile: yfinance 1.2.0 requires `curl_cffi` instead of `requests.Session`. Early code tried to reuse a session object; yfinance ignored it (curl_cffi doesn't accept session injection). Fixed by Phase 31 — no direct Session usage in data_fetcher now.
- Safe modification: Never construct `requests.Session()` inside yfinance data paths. yfinance manages its own HTTP lifecycle. If you need persistent HTTP behavior, test against the pinned yfinance version (1.2.0) and verify in CI.
- Test coverage: `pytest tests/test_data_fetcher.py::TestFetch` exercises real yfinance calls in test mode (mocked HTTP). If yfinance version changes, these tests will catch API breakage.

**Test fixtures depend on specific numpy/pandas versions:**
- Files: `tests/fixtures/audusd_400bar.README.md`, `tests/fixtures/axjo_400bar.README.md`, `tests/fixtures/phase2/README.md`
- Why fragile: Fixtures were generated with numpy 2.0.2 + pandas 2.3.3 (noted in README). Upgrading either library can shift float64 serialization, breaking determinism tests.
- Safe modification: Before upgrading, regenerate fixtures: `python tests/oracle/regenerate.py` (or fixture-specific regenerators in `tests/fixtures/phase2/`). Commit the new golden fixtures with a note on the version change in README.
- Test coverage: Determinism test catches fixture/oracle divergence. If bits don't match, the test fails fast — no silent wrongness.

## Scaling Limits

**State.json file-based persistence + flock serialization:**
- Current capacity: Single daily run per day + periodic web reads (dashboard, admin pages) + rare state writes (paper trades, warnings).
- Limit: File I/O + flock on every mutation is adequate for <20 F&F users. At >100 concurrent users fetching state frequently, POSIX flock contention becomes a bottleneck (lock waits block the entire process).
- Scaling path: (1) For F&F growth to ~50 users: keep file-based state, add in-memory cache + TTL (cache hits bypass flock). (2) For 100+ users or multi-process deployment: migrate to SQLite (still flock-based but indexed) or PostgreSQL (distributed locks via advisory locks or pessimistic row locking). Phase 37 fan-out design assumes file-based state; any scale-up requires schema rework.

**Per-user state files not yet implemented:**
- Current: All per-user data lives in a top-level `users: {}` dict in `state.json` (Phase 37 TENANT-03).
- Limit: At >50 users with >1000 trades each, `state.json` becomes unwieldy (megabyte-range file, slow serialization/deserialization).
- Scaling path: Split to per-user files `state/users/{uid}/state.json` with per-user `.gitignore` entries. Atomic writes still use flock, but each write is smaller. Web layer reads via user-scoped helper `load_user_state(uid)`.

**News fetch on every dashboard render:**
- Current: Dashboard rendering fetches `Ticker.news` from Yahoo on every page load (no cache).
- Limit: Rate-limit risk if >5 users load dashboard in the same hour (shares Yahoo API quota). Page load TTFB jumps from <100ms to ~1s per news fetch.
- Scaling path: Cache news to a `.json` file with 24h TTL. Refresh out-of-band (async task in `scheduler_driver.py` or `main.py` daily run). Dashboard reads from cache; if cache miss, serve stale or empty rather than blocking on HTTP.

## Dependencies at Risk

**yfinance 1.2.0 pinned (protobuf/curl_cffi risk):**
- Risk: yfinance bundles protobuf + curl_cffi. These are complex dependencies with their own security/stability concerns. yfinance 0.2.x → 1.x migration was a major version jump.
- Impact: If curl_cffi breaks or becomes unmaintained, yfinance 1.2.0 is stuck. Newer yfinance versions might drop Python 3.13 support or require updates to other deps.
- Migration plan: Before upgrading yfinance, check CHANGELOG for breaking changes. Run full test suite against new version (especially `tests/test_data_fetcher.py` and determinism tests). Regenerate oracle/fixtures if numpy/pandas versions change as a side effect.

**bcrypt 5.0.0 (auth critical path):**
- Risk: Password hashing at registration/login. bcrypt is stable, but if a vulnerability is found, upgrades may require password re-hashing (not backward compatible with old hashes).
- Impact: Users cannot sign in until they reset password via recovery email. Recovery email path itself might fail if Resend is down.
- Migration plan: Never auto-upgrade bcrypt in CI without testing the full login flow. If a breaking upgrade is required, plan a migration phase: (1) accept old hashes for login, (2) require password reset on next login, (3) migrate hashes.

**Resend API (email delivery — notification critical path):**
- Risk: External SaaS dependency. API rate limits, outages, pricing changes, account suspension (leaked keys, abuse).
- Impact: Email failures are logged but don't crash the app (graceful degradation: Phase 6 NOTF-07). Dashboard is still accessible. But daily digest emails are lost.
- Migration plan: None implemented yet. Workaround: last_email.html file written to disk on API failure (admin can manually inspect). Recovery: fix `RESEND_API_KEY` in `.env` and re-run `python main.py --force-email`.

## Missing Critical Features

**Multi-user state isolation (Phase 37 deferred):**
- Problem: Admin user's state leaks to other users in crash emails (Phase 37 SC-5 deferred). Crash-email body includes full state dict without per-user filtering.
- Blocks: Cannot safely invite F&F users until crash email redaction is implemented. Risk of confidential trade data leaking across users.
- Priority: HIGH — blocks user growth beyond dev team.

**Crash-email body redaction (Phase 37 deferred):**
- Problem: Crash emails are sent to `OPERATOR_RECOVERY_EMAIL` with the entire state dict. If a multi-user scenario crashes, all users' trade history is in the email body.
- Blocks: Same as above — unsafe for F&F deployment.
- Implementation: `RedactStateFilter` Pydantic model exists (Phase 37 TENANT-03) but crash-email template (`notifier/templates.py::render_crash_email`) does not apply it yet.
- Priority: HIGH.

**User B visibility filtering on shared pages (Phase 37 deferred):**
- Problem: Admin can view all users' dashboards via `/state/users/{uid}`. User B's dashboard/market page visibility filtering not yet implemented.
- Blocks: F&F user privacy — user A could theoretically discover user B's portfolio via brute-force UID enumeration (UIDs are 4-hex strings, ~65k entropy).
- Implementation: Route-level check in `web/routes/dashboard.py::get_user_dashboard` missing (xfail test stub exists).
- Priority: MEDIUM (depends on RBAC policy — are users allowed to see each other's trades?).

## Test Coverage Gaps

**Crash-email redaction assertions:**
- What's not tested: `render_crash_email` with multi-user state. Test scaffolded in `test_tenant_isolation.py::test_crash_email_body_redacts_other_users` but marked `@pytest.mark.skip`.
- Files: `tests/test_tenant_isolation.py::test_crash_email_body_redacts_other_users`, `notifier/templates.py::render_crash_email`
- Risk: Crash email could leak trade data across users undetected. The skip exists because `RedactStateFilter` wasn't wired at test time.
- Priority: HIGH — unblock by implementing redaction in `render_crash_email`, then remove skip marker.

**XSS test coverage lost after chart-gating change:**
- What's not tested: `test_chart_payload_escapes_script_close` stopped exercising its core assertion (Phase 25 D-11 hid the chart when <5 equity points).
- Files: `tests/test_dashboard.py::TestChartPayload::test_chart_payload_escapes_script_close`
- Risk: Chart-rendering XSS defense is never fired. A future attacker-controlled equity value could slip through without triggering the test.
- Priority: MEDIUM — Phase 25 fixed by seeding ≥5 equity points in fixture, but test should not rely on side effects. Assertion comment should note the gate condition.

**RBAC policy matrix not fully tested:**
- What's not tested: Admin can enable/disable users; disabled users are skipped in fan-out. Test stubs exist (xfail) for `/admin/users` GET and PATCH endpoints.
- Files: `tests/test_web_admin_users.py::test_admin_users_list`, `tests/test_web_admin_users.py::test_admin_disable_user`
- Risk: If disable logic is ever broken, the skip-rule in `per_user_fanout.py` fails silently (disabled user still gets email). No automated gate prevents this.
- Priority: LOW-MEDIUM — user management UI not yet completed, xfails track the gap.

**Legacy signal-shape handling in daily_run:**
- What's not tested: `get_latest_indicators` in `daily_run.py::325` comment notes "legacy key names pdi/ndi" (Phase 21 refactor). No explicit test of backward-compat path.
- Files: `daily_run.py::325`, `signal_engine.py::get_latest_indicators`
- Risk: If the refactor introduced a typo (pdi vs. PDI), old data silently reads as NaN. New runs would work; old signal rows would break.
- Priority: LOW — narrow code path, covered implicitly by determinism tests, but explicit test would be safer.

---

*Concerns audit: 2026-05-15*
