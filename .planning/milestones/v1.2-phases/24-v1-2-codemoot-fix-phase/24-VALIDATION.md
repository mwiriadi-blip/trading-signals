---
phase: 24
slug: v1-2-codemoot-fix-phase
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-10
audited: 2026-05-10
---

# Phase 24 — Validation Strategy

> Reconstructed retroactively after phase execution (D-06: mechanical retrofit only).
> Phase 24 fixed 3 bugs and 5 cleanup items from post-milestone codemoot review.
> Automated test coverage exists for BUG-02, CR-01, and behavioral paths of CLEAN-04/CLEAN-06.
> Gaps surface as Deferred items below.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `.venv/bin/pytest tests/test_scheduler.py tests/test_auth_store.py tests/test_web_routes_totp.py tests/test_web_routes_reset.py tests/test_main.py -q` |
| **Full suite command** | `.venv/bin/pytest -q` |
| **Phase-24 subset command** | `.venv/bin/pytest tests/test_scheduler.py::TestScheduleLoop::test_non_utc_process_raises tests/test_main.py::TestMainOnce::test_once_flag_runs_single_check tests/test_main.py::TestWeekendGate::test_run_daily_check_does_not_push_on_weekend tests/test_web_routes_totp.py tests/test_web_routes_reset.py -q` |
| **Estimated runtime** | ~15 s (Phase-24 subset); ~3 min (full suite) |

---

## Sampling Rate

- **After every task commit:** Run task-scoped pytest file (~1–3 s)
- **After every plan wave:** Run full suite (`pytest -q`)
- **Before `/gsd-verify-work`:** Full suite must be green

---

## Per-Task Verification Map

| Task ID | Fix ID | File | Requirement / Behavior | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|--------|------|------------------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 24-BUG-02 | BUG-02 | main.py | UTC scheduler guard raises RuntimeError (not AssertionError, which is disabled by `python -O`) | T-24-02-01 | Scheduler never silently accepts wrong timezone | unit | `.venv/bin/pytest tests/test_scheduler.py::TestScheduleLoop::test_non_utc_process_raises -q` | ✅ | ✅ green |
| 24-CR-01 | CR-01 | main.py | `--once` path on weekend: `run_daily_check` returns None; code guards with `once_state is not None` — no AttributeError | T-24-03-01 | No crash on Saturday/Sunday GHA cron run | unit | `.venv/bin/pytest tests/test_main.py::TestWeekendGate::test_run_daily_check_does_not_push_on_weekend -q` | ✅ | ✅ green |
| 24-BUG-03 | BUG-03 | main.py | `--once` mode persists post-push warnings via `mutate_state` | T-24-03-02 | Warnings not silently discarded after single run | unit (behavioral) | `.venv/bin/pytest tests/test_main.py::TestMainOnce::test_once_flag_runs_single_check -q` | ✅ | partial |
| 24-CLEAN-04 | CLEAN-04 | web/routes/totp.py | `_is_safe_next` imported from `web.routes.login`; no local definition | — | Single source of truth for redirect safety check | unit (behavioral) | `.venv/bin/pytest tests/test_web_routes_totp.py -q` | ✅ | partial |
| 24-CLEAN-06 | CLEAN-06 | web/routes/reset.py | `_get_client_ip` imported from `web.middleware.auth`; no local definition | — | Single source of truth for client-IP extraction | unit (behavioral) | `.venv/bin/pytest tests/test_web_routes_reset.py -q` | ✅ | partial |
| 24-BUG-01 | BUG-01 | auth_store.py | `_ensure_aware()` coerces naive datetimes before comparison — no TypeError crash | T-24-01-01 | Auth never crashes on legacy tz-naive timestamps in auth.json | unit | Deferred — no test targets the naive-datetime code path | ⚠️ missing | deferred |
| 24-WR-01 | WR-01 | main.py | `--once` uses `mutate_state` (fcntl lock) not `save_state` | T-24-03-03 | Lock discipline enforced; no lost-update race vs web POST | unit (lock) | Deferred — no lock-discipline test | ⚠️ missing | deferred |
| 24-WR-02 | WR-02 | main.py | Dead `not args.test` guard documented or removed | — | No misleading dead code | style | Deferred — no test (dead guard, not behavioral) | n/a | deferred |
| 24-CLEAN-01 | CLEAN-01 | main.py | `_SYMBOL_CONTRACT_SPECS` removed | — | No dead code in hot path | none | Deferred — dead-code removal, no behavioral test needed | n/a | deferred |
| 24-CLEAN-02 | CLEAN-02 | main.py | Unused `import alert_engine` removed | — | No spurious import | none | Deferred — import cleanup, no behavioral test needed | n/a | deferred |
| 24-CLEAN-03 | CLEAN-03 | alert_engine.py | `AlertLevel` alias removed | — | No dead type alias | none | Deferred — dead alias removal, no behavioral test needed | n/a | deferred |
| 24-IN-01 | IN-01 | web/routes/totp.py | `error` param HTML-escaped in `_render_enroll_page` / `_render_verify_page` | T-24-04-01 | Defense-in-depth XSS prevention for future callers | unit | Deferred to Phase 27 — `test_html_xss_audit.py` covers the broader dashboard XSS surface (Phase 27 IN-01 carry-over) | ✅ (Phase 27) | deferred to Phase 27 |
| 24-IN-02 | IN-02 | main.py | Post-push warning persistence gap in scheduler daemon loop | — | Known design limitation | none | Deferred — acknowledged design gap; not blocking | n/a | deferred |

*Status: ⬜ pending · ✅ green · partial (behavior covered, structure not asserted) · deferred*

---

## Gaps (Deferred Items)

Items below are coverage gaps identified during this mechanical retrofit. They are NOT blockers for Phase 24 close (already shipped). Deferred for a future test-fill phase if the paths become higher-risk.

| Gap ID | Finding | Rationale | Suggested Test |
|--------|---------|-----------|----------------|
| G-24-01 | BUG-01 naive datetime | `test_auth_store.py` fixtures use tz-aware datetimes only; no test passes a naive ISO string through the auth.json round-trip path to exercise `_ensure_aware()` | Add `test_consume_magic_link_with_naive_expires_at_does_not_crash` using a fixture with `expires_at` lacking `+HH:MM` suffix |
| G-24-02 | WR-01 lock discipline | No test asserts that `mutate_state` is used (not `save_state`) in the `--once` path. The 24-VERIFICATION.md verifies via code inspection only | Add AST-walker or grep-gate test asserting `save_state` is not called in the `--once` branch |
| G-24-03 | CLEAN-04/CLEAN-06 import structure | `test_web_routes_totp.py` and `test_web_routes_reset.py` cover behavior; no test asserts the import structure (i.e., no local `def _is_safe_next` / `def _get_client_ip`) | Add `test_totp_dedup_no_local_is_safe_next` and `test_reset_dedup_no_local_get_client_ip` as AST/inspect checks |
| G-24-04 | BUG-03 state persistence | `test_once_flag_runs_single_check` verifies `--once` doesn't crash and returns 0; it does not assert that `state_manager.mutate_state` was called with the returned warnings | Extend test or add `test_once_mode_persists_warnings_via_mutate_state` with a spy on `mutate_state` |

---

## Wave 0 Requirements

No new test framework or fixtures required. Existing pytest 8.x suite covers all behavioral paths. Gap fills (if later scheduled) use the same `monkeypatch` + `isolated_auth_json` fixture patterns already established in `test_auth_store.py`.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| BUG-01 real-world legacy auth.json | Phase 24 BUG-01 | No production auth.json with naive timestamps available in test fixtures | On production droplet: rename `auth.json`, write a test entry with tz-naive `expires_at`, restart, confirm no crash on magic-link flow |
| CLEAN-04/CLEAN-06 naming convention (WR-03) | Phase 24 WR-03 | Name rename was NOT done (dedup only) | Future review: if underscore-prefix naming causes confusion in new importers, revisit per WR-03 recommendation |

All critical bugs (BUG-02, CR-01) have automated verification.

---

## Validation Sign-Off

- [x] Critical bugs (BUG-02, CR-01) have automated test coverage
- [x] Coverage gaps documented as Deferred items (G-24-01 through G-24-04)
- [x] Dead-code removals (CLEAN-01, CLEAN-02, CLEAN-03) have no behavior to test
- [x] IN-01 XSS path carried over to Phase 27 where it is covered
- [x] `nyquist_compliant: true` set in frontmatter (compliant for shipped behavioral fixes)

**Approval:** approved 2026-05-10 (retroactive reconstruction; full suite green per 24-VERIFICATION.md)

---

## Validation Audit 2026-05-10

| Metric | Count |
|--------|-------|
| Findings audited | 14 (6 primary: BUG-01..03, CR-01, WR-01..03; 5 CLEAN; 2 IN) |
| Covered | 2 (BUG-02, CR-01 — automated) |
| Partial | 3 (BUG-03, CLEAN-04, CLEAN-06 — behavioral but not structural) |
| Deferred | 9 (BUG-01, WR-01, WR-02, CLEAN-01..03, IN-01 via Phase 27, IN-02) |
| Phase-24 tests passing | Verified per 24-VERIFICATION.md (10/10 must-haves) |
| Total project tests at phase close | 1691 passed |

Reconstructed from PLAN.md, 24-REVIEW.md, SUMMARY.md, and 24-VERIFICATION.md artifacts.
