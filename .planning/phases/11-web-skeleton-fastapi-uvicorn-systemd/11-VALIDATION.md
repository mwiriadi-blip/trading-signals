---
phase: 11
slug: web-skeleton-fastapi-uvicorn-systemd
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-04-24
updated: 2026-04-24 post-cross-AI review (REVIEWS.md HIGH #1/#2/#3/#4 + MEDIUM #5/#6/#7 + LOW #8)
---

# Phase 11 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source of truth: `.planning/phases/11-web-skeleton-fastapi-uvicorn-systemd/11-RESEARCH.md` §11 Validation Architecture (Nyquist).
> Refreshed 2026-04-24 after `/gsd-plan-phase 11 --reviews` applied the cross-AI review feedback.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.3.3 + pytest-freezer 0.4.9 |
| **Config file** | none (pytest auto-discovers `tests/`) |
| **Quick run command** | `pytest tests/test_web_healthz.py tests/test_web_systemd_unit.py tests/test_deploy_sh.py tests/test_setup_droplet_doc.py -x -q` |
| **Full suite command** | `pytest tests/ -q` |
| **Estimated runtime** | ~10 seconds (4 new files) / ~30-60 seconds (full suite) |

---

## Sampling Rate

- After every task commit: relevant test file (`pytest tests/test_<x>.py -x -q`)
- After every plan wave: full suite (`pytest tests/ -q`)
- Before `/gsd-verify-work 11`: full suite must be green
- Max feedback latency: 60 seconds

---

## Post-REVIEWS Changes Summary (2026-04-24)

| Review item | Severity | Landed in | Test-level impact |
|-------------|----------|-----------|-------------------|
| #1 `last_run` format `YYYY-MM-DD` | HIGH | Plan 11-01 | Handler uses `date.fromisoformat`; tests use YYYY-MM-DD fixtures |
| #2 Fixture uses `monkeypatch.setattr(state_manager, 'load_state', ...)` not STATE_FILE | HIGH | Plan 11-01 | All state-redirect tests use `load_state` stub; `_stub_load_state` helper |
| #3 `deploy.sh` smoke test uses retry loop | HIGH | Plan 11-03 | New `test_step_7_smoke_test_uses_retry_loop` + `test_step_7_sleep_3_heuristic_is_FORBIDDEN` |
| #4 Two `sudo -n systemctl restart <unit>` calls + SETUP-DROPLET verification step | HIGH | Plan 11-03 + Plan 11-04 | New `test_step_6_two_sudo_restart_calls` + `test_step_6_combined_restart_is_FORBIDDEN`; new `test_passwordless_sudo_verification_step` + `test_sudoers_form_matches_deploy_sh_restart_calls` |
| #5 `EnvironmentFile=-` optional prefix | MEDIUM | Plan 11-02 + Plan 11-04 | New `test_environment_file_is_optional` + `test_environment_file_is_not_required_form`; new TestEnvFileOptional class |
| #6 Drop docs_url/redoc_url kwargs from create_app() | MEDIUM | Plan 11-01 | Acceptance criteria inverted — `grep -c 'docs_url=None'` now returns `0` |
| #7 Drop `pip install --upgrade pip` | MEDIUM | Plan 11-03 | New `test_step_4_pip_upgrade_is_DROPPED` negative assertion |
| #8 Cross-integration assertion `web.app:app` | LOW | Plan 11-02 | New `test_execstart_references_web_app_module_exactly` |
| #9 Test brittleness (cosmetic) | LOW | all plans (deferred) | Deferral notes in each plan; not reworked |

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|--------|
| 11-01 T1 | 11-01 | 0 | WEB-07 | T-11-07 | requirements.txt pins + web/ packages importable | unit (import) | `.venv/bin/python -c "import fastapi, uvicorn, httpx, web, web.routes"` | ⬜ pending |
| 11-01 T2 | 11-01 | 0 | WEB-07 | T-11-01, T-11-05, T-11-07 | create_app() returns FastAPI (NO docs_url/redoc_url per MEDIUM #6); handler uses `date.fromisoformat` (HIGH #1); C-2 local import | unit | `.venv/bin/python -m pytest tests/test_web_healthz.py::TestHealthzHappyPath -x -q` | ⬜ pending |
| 11-01 T3 | 11-01 | 0 | WEB-07 | T-11-05, T-11-07 | 5 test classes; fixture uses `monkeypatch.setattr(state_manager, 'load_state', ...)` (HIGH #2); last_run fixtures YYYY-MM-DD (HIGH #1) | unit | `.venv/bin/python -m pytest tests/test_web_healthz.py -x -q` | ⬜ pending |
| 11-02 T1 | 11-02 | 1 | WEB-01, WEB-02 | T-11-01, T-11-06 | Unit file D-06..D-12 + `EnvironmentFile=-` (MEDIUM #5) + `web.app:app` exact (LOW #8); no 0.0.0.0 | static lint | `grep -c '^EnvironmentFile=-/' systemd/trading-signals-web.service` = 1; `grep -q 'web\.app:app' systemd/trading-signals-web.service`; `! grep 0.0.0.0 systemd/trading-signals-web.service` | ⬜ pending |
| 11-02 T2 | 11-02 | 1 | WEB-01, WEB-02 | T-11-01, T-11-06 | configparser; 27+ tests; new `test_environment_file_is_optional` + `test_environment_file_is_not_required_form` (MEDIUM #5); new `test_execstart_references_web_app_module_exactly` (LOW #8) | unit | `.venv/bin/python -m pytest tests/test_web_systemd_unit.py -x -q` | ⬜ pending |
| 11-03 T1 | 11-03 | 1 | INFRA-04 | T-11-03, T-11-04 | deploy.sh with 2026-04-24 adjustments: pip-upgrade DROPPED (MEDIUM #7), TWO `sudo -n systemctl restart <unit>` (HIGH #4), curl retry loop (HIGH #3); no auto-rollback (D-25) | static lint | `bash -n deploy.sh && grep -q '^sudo -n systemctl restart trading-signals$' deploy.sh && grep -q '^sudo -n systemctl restart trading-signals-web$' deploy.sh && ! grep -q 'sudo systemctl restart trading-signals trading-signals-web' deploy.sh && ! grep -q 'pip install --upgrade pip' deploy.sh && grep -q 'for i in 1 2 3 4 5 6 7 8 9 10' deploy.sh && grep -q 'curl -fsS --max-time 2 http://127.0.0.1:8000/healthz' deploy.sh` | ⬜ pending |
| 11-03 T2 | 11-03 | 1 | INFRA-04 | T-11-03, T-11-04 | 30+ tests; 6 cross-step ordering checks; 3 new REVIEWS-driven negative assertions | unit | `.venv/bin/python -m pytest tests/test_deploy_sh.py -x -q` | ⬜ pending |
| 11-04 T1 | 11-04 | 2 | WEB-01, WEB-02, INFRA-04 | T-11-01, T-11-02, T-11-06 | SETUP-DROPLET.md 7 sections; two-rule sudoers; 2026-04-24 additions: `.env` optional note (MEDIUM #5) + `sudo -n systemctl restart trading-signals-web` verification step (HIGH #4) | static lint | `grep -q '^## Install systemd unit$' SETUP-DROPLET.md && grep -q 'trader ALL=(root) NOPASSWD: /usr/bin/systemctl restart trading-signals, /usr/bin/systemctl restart trading-signals-web' SETUP-DROPLET.md && grep -q 'sudo -n systemctl restart trading-signals-web' SETUP-DROPLET.md && grep -q 'EnvironmentFile=-' SETUP-DROPLET.md && grep -q 'NOPASSWD: ALL' SETUP-DROPLET.md` | ⬜ pending |
| 11-04 T2 | 11-04 | 2 | WEB-01, WEB-02, INFRA-04 | T-11-02 | 28+ tests, 9 classes; TestEnvFileOptional (MEDIUM #5); TestCrossArtifactDriftGuard with sudoers-form check (HIGH #4); new `test_passwordless_sudo_verification_step` (HIGH #4) | unit | `.venv/bin/python -m pytest tests/test_setup_droplet_doc.py -x -q` | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave Dependency Graph

```
Wave 0 (sequential, single plan)
└── Plan 11-01 — Python deps + web/ package + /healthz handler + tests
       │
       ├──────────────┬─────────────────┐
       ▼              ▼                 ▼
Wave 1 (parallel — disjoint files)
├── Plan 11-02 — systemd unit + tests (EnvironmentFile=- optional; web.app:app exact)
└── Plan 11-03 — deploy.sh + tests (two sudo -n; retry loop; no pip-upgrade)
       │              │
       └──────┬───────┘
              ▼
Wave 2 (sequential, single plan)
└── Plan 11-04 — SETUP-DROPLET.md + cross-artifact drift guard tests
                  (+ passwordless-sudo verification step; .env optional note)
```

---

## Wave 0 Requirements

- [ ] `tests/test_web_healthz.py` — 5 test classes
  - Fixture: `monkeypatch.setattr(state_manager, 'load_state', ...)` per REVIEWS HIGH #2
  - `last_run` assertions use YYYY-MM-DD per REVIEWS HIGH #1
- [ ] `requirements.txt` — `fastapi==0.136.1`, `uvicorn[standard]==0.46.0`, `httpx==0.28.1`
- [ ] `web/` package: `__init__.py`, `app.py`, `routes/__init__.py`, `routes/healthz.py`
  - `create_app()` no `docs_url=None`/`redoc_url=None` per REVIEWS MEDIUM #6
  - Handler uses `date.fromisoformat` per REVIEWS HIGH #1

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `systemctl status trading-signals-web` active after reboot (SC-1) | WEB-01 | Requires droplet + systemd | SETUP-DROPLET.md §Verify boot persistence |
| `ss -tlnp | grep 8000` shows `127.0.0.1:8000` only (SC-4) | WEB-02 | Requires real OS network stack | SETUP-DROPLET.md §Verify port binding |
| `bash deploy.sh && bash deploy.sh` idempotent (SC-3) | INFRA-04 | Requires git remote + droplet venv | SETUP-DROPLET.md §Verify deploy.sh end-to-end |
| `systemd-analyze verify` passes | WEB-01 | Tool unavailable on macOS dev | SETUP-DROPLET.md §Install systemd unit |
| `sudo visudo -c -f` parses sudoers | INFRA-04 | Requires visudo + /etc/sudoers.d/ | SETUP-DROPLET.md §Install sudoers entry |
| **`sudo -n systemctl restart trading-signals-web` succeeds (REVIEWS HIGH #4 — NEW 2026-04-24)** | INFRA-04 | Requires droplet sudoers + systemd | SETUP-DROPLET.md §Install sudoers entry — verification step |
| External `curl <DROPLET_IP>:8000/healthz` unreachable | WEB-02 / T-11-01 | Requires external network | SETUP-DROPLET.md §Verify port binding |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] Manual-only verifications captured in SETUP-DROPLET.md (Plan 11-04) — **including new REVIEWS HIGH #4 passwordless-sudo verification step**
- [x] `nyquist_compliant: true`
- [x] 2026-04-24 post-REVIEWS refresh applied — per-task automated commands updated to reflect new assertions

**Approval:** planner-refreshed 2026-04-24 post-cross-AI review. Awaiting execution.
