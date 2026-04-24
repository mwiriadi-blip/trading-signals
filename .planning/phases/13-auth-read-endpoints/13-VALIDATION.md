---
phase: 13
slug: auth-read-endpoints
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-25
---

# Phase 13 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.3.3 |
| **Config file** | `pytest.ini` (existing) |
| **Quick run command** | `pytest tests/test_web_*.py -x -q` |
| **Full suite command** | `pytest -q` |
| **Estimated runtime** | Quick ~5s; full ~60s |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_web_*.py -x -q` (covers the 4 new test files plus existing test_web_healthz.py)
- **After every plan wave:** Run `pytest -q` (full suite — catches hex-boundary regressions in test_signal_engine.py::TestDeterminism)
- **Before `/gsd-verify-work`:** Full suite must be green, plus manual verification per §Manual-Only
- **Max feedback latency:** 60 seconds (full suite)

---

## Per-Task Verification Map

Populated by planner. Each Phase 13 task produces a test or extends an existing test class. The plan's task-level `<acceptance_criteria>` should state the exact pytest command that proves the task done. Skeleton:

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 13-XX-YY | XX | W | AUTH-01..03, WEB-05..06 | T-13-NN | See threat model in PLAN | unit / integration | `pytest tests/test_web_X.py::TestY::test_Z -x` | ✅ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Wave 0 creates test-infrastructure-only scaffolding so Wave 1 tasks have stable fixtures. No production code ships in Wave 0.

- [ ] `tests/test_web_auth_middleware.py` — file created with skeleton class `TestAuthMiddleware` (imports only, no tests yet)
- [ ] `tests/test_web_dashboard.py` — file created with skeleton class `TestGetRootDashboard`
- [ ] `tests/test_web_state.py` — file created with skeleton class `TestGetApiState`
- [ ] `tests/test_web_app_factory.py` — file created with skeleton class `TestCreateAppSecretValidation`
- [ ] `tests/conftest.py` — extend with `web_app_fixture` and `web_auth_header_fixture` helpers that set `WEB_AUTH_SECRET` before `create_app()` is called
- [ ] `tests/test_web_healthz.py::app_instance` fixture — update to setenv `WEB_AUTH_SECRET` BEFORE create_app() (Phase 11 test breaks after Phase 13 D-16 fail-closed lock, per RESEARCH §Test Infrastructure)
- [ ] `tests/test_signal_engine.py::TestDeterminism::FORBIDDEN_FOR_WEB` — remove `dashboard` from forbidden set (new allowed adapter-to-adapter import per D-07)

No new pytest deps needed; all covered by existing `pytest==8.3.3`, `pytest-freezer`, `httpx==0.28.1` from Phase 11 requirements.txt.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| nginx forwards `X-Forwarded-For` correctly to FastAPI | AUTH-03 / SC-5 | Requires live nginx+uvicorn+curl; automated XFF parse is stubbed at the middleware layer, not through real nginx | On droplet: `sudo journalctl -u trading-signals-web -f` + from laptop `curl -H 'X-Forwarded-For: 1.2.3.4' https://signals.<domain>/; confirm journald log shows `ip=1.2.3.4` (or the nginx-detected real client IP if nginx rewrites XFF) |
| dashboard.html regenerates on stale state in real droplet | WEB-05 / SC-2 | Requires live signal loop writing state.json atomically + browser refresh to observe | On droplet: `touch state.json` then refresh browser against `https://signals.<domain>/`; confirm dashboard shows fresh "Rendered at" timestamp |
| 401 WARN log line appears in journald with correct format | AUTH-03 / SC-5 | Requires live systemd journald + curl probe; automated test covers format but not the systemd integration | On droplet: `curl https://signals.<domain>/api/state` (no header) → `journalctl -u trading-signals-web --since '5 min ago' \| grep 'auth failure'` shows the log line |
| WEB_AUTH_SECRET missing at startup → systemd logs the cause | D-16 | Requires systemd Restart=on-failure loop + journald inspection | On droplet: `sudo sed -i '/WEB_AUTH_SECRET/d' ~/trading-signals/.env && sudo systemctl restart trading-signals-web && journalctl -u trading-signals-web -n 20`; confirm RuntimeError message visible. Restore .env after. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
