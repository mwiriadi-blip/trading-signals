---
phase: 11
slug: web-skeleton-fastapi-uvicorn-systemd
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-04-24
updated: 2026-04-24
---

# Phase 11 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source of truth: `.planning/phases/11-web-skeleton-fastapi-uvicorn-systemd/11-RESEARCH.md` §11 Validation Architecture (Nyquist).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.3.3 + pytest-freezer 0.4.9 (already installed; see requirements.txt) |
| **Config file** | none (pytest auto-discovers `tests/`) |
| **Quick run command** | `pytest tests/test_web_healthz.py tests/test_web_systemd_unit.py tests/test_deploy_sh.py tests/test_setup_droplet_doc.py -x -q` |
| **Full suite command** | `pytest tests/ -q` |
| **Estimated runtime** | ~10 seconds (4 new files) / ~30-60 seconds (full suite, ~660+ existing tests) |

---

## Sampling Rate

- **After every task commit:** Run the relevant test file (`pytest tests/test_<x>.py -x -q`)
- **After every plan wave:** Run `pytest tests/ -q` (full suite to detect cross-plan regressions)
- **Before `/gsd-verify-work 11`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

> Every task in every PLAN.md is captured below. Threat refs map to RESEARCH §10 STRIDE register.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 11-01 T1 | 11-01 | 0 | WEB-07 | T-11-07 | requirements.txt pins fastapi==0.136.1, uvicorn[standard]==0.46.0, httpx==0.28.1; web/, web/routes/ are importable packages | unit (import) | `.venv/bin/python -c "import fastapi, uvicorn, httpx, web, web.routes"` | ✅ exists (after Task 1) | ⬜ pending |
| 11-01 T2 | 11-01 | 0 | WEB-07 | T-11-01, T-11-05, T-11-07 | create_app() returns FastAPI; module-level app exposed; /healthz registered; state_manager imported LOCALLY (C-2); D-19 try/except wraps handler | unit | `.venv/bin/python -m pytest tests/test_web_healthz.py::TestHealthzHappyPath -x -q` | ✅ created in T2 | ⬜ pending |
| 11-01 T3 | 11-01 | 0 | WEB-07 | T-11-05, T-11-07 | 5 test classes cover D-13..D-19 + AST hex-boundary; happy path / missing state.json / staleness (3 sub-cases) / D-19 degraded path / hex boundary AST guard | unit | `.venv/bin/python -m pytest tests/test_web_healthz.py -x -q` | ✅ Wave 0 creates | ⬜ pending |
| 11-02 T1 | 11-02 | 1 | WEB-01, WEB-02 | T-11-01, T-11-06 | systemd unit file body matches RESEARCH §3 verbatim; --host 127.0.0.1 only; --workers 1; all 5 D-10 hardening directives present; no 0.0.0.0 anywhere | static lint | `grep -E '^(--host 127.0.0.1|--workers 1)' systemd/trading-signals-web.service` returns ≥2; `! grep 0.0.0.0 systemd/trading-signals-web.service` exits 0 | ❌ Wave 1 creates | ⬜ pending |
| 11-02 T2 | 11-02 | 1 | WEB-01, WEB-02 | T-11-01, T-11-06 | configparser parses unit file; 25+ tests across 6 classes assert every D-06..D-12 invariant; test_execstart_does_not_bind_all_interfaces is the critical loopback guard | unit | `.venv/bin/python -m pytest tests/test_web_systemd_unit.py -x -q` | ❌ Wave 1 creates | ⬜ pending |
| 11-03 T1 | 11-03 | 1 | INFRA-04 | T-11-03, T-11-04 | deploy.sh shebang + set -euo pipefail; D-22 branch check first; D-23 8-step sequence in order; restarts both units in one sudo invocation; smoke-tests /healthz at 127.0.0.1:8000; no auto-rollback (D-25); chmod +x applied | static lint | `bash -n deploy.sh && grep -q 'sudo systemctl restart trading-signals trading-signals-web' deploy.sh && grep -q 'curl -fsS --max-time 5 http://127.0.0.1:8000/healthz' deploy.sh && ! grep -qE '(git revert\|git reset --hard\|rollback)' deploy.sh` | ❌ Wave 1 creates | ⬜ pending |
| 11-03 T2 | 11-03 | 1 | INFRA-04 | T-11-03, T-11-04 | 25+ tests across 4 classes; sequence ordering enforced via _line_index helper (5 cross-step ordering checks); D-25 enforced by 3 separate negative tests | unit | `.venv/bin/python -m pytest tests/test_deploy_sh.py -x -q` | ❌ Wave 1 creates | ⬜ pending |
| 11-04 T1 | 11-04 | 2 | WEB-01, WEB-02, INFRA-04 | T-11-01, T-11-02, T-11-06 | SETUP-DROPLET.md has 7 sections (4 setup + boot persistence + Troubleshooting + What's NOT); EXACT sudoers entry text scoped to 2 unit names; SC-1/SC-3/SC-4 manual verifications documented; anti-pattern WARNING against NOPASSWD: ALL and 0.0.0.0 | static lint | `grep -q '^## Install systemd unit$' SETUP-DROPLET.md && grep -q 'trader ALL=(root) NOPASSWD: /usr/bin/systemctl restart trading-signals, /usr/bin/systemctl restart trading-signals-web' SETUP-DROPLET.md && grep -q 'NOPASSWD: ALL' SETUP-DROPLET.md` | ❌ Wave 2 creates | ⬜ pending |
| 11-04 T2 | 11-04 | 2 | WEB-01, WEB-02, INFRA-04 | T-11-02 | 25+ tests across 8 classes including TestCrossArtifactDriftGuard which verifies the doc references the same unit name as systemd/trading-signals-web.service AND the same /healthz URL as deploy.sh | unit | `.venv/bin/python -m pytest tests/test_setup_droplet_doc.py -x -q` | ❌ Wave 2 creates | ⬜ pending |

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
├── Plan 11-02 — systemd unit + tests
└── Plan 11-03 — deploy.sh + tests
       │              │
       └──────┬───────┘
              ▼
Wave 2 (sequential, single plan)
└── Plan 11-04 — SETUP-DROPLET.md + cross-artifact drift guard tests
```

**Wave 1 parallelism justification:** Plans 11-02 (systemd unit) and 11-03 (deploy.sh) modify disjoint files. Plan 11-02 touches `systemd/trading-signals-web.service` + `tests/test_web_systemd_unit.py`. Plan 11-03 touches `deploy.sh` + `tests/test_deploy_sh.py`. Both depend conceptually on Plan 11-01 (deploy.sh smoke-tests /healthz which Plan 11-01 provides; systemd unit ExecStart references the `web.app:app` module Plan 11-01 creates) but neither plan needs the other's output to execute.

**Wave 2 dependency:** Plan 11-04 documents how to install the artifacts from Plans 11-02 (unit file) and 11-03 (deploy.sh), AND its TestCrossArtifactDriftGuard reads both `systemd/trading-signals-web.service` and `deploy.sh` to verify name consistency. Therefore Plan 11-04 must run AFTER Plans 11-02 and 11-03 are complete.

---

## Wave 0 Requirements

- [ ] `tests/test_web_healthz.py` — TestHealthzHappyPath, TestHealthzMissingStatefile, TestHealthzStaleness, TestHealthzDegradedPath, TestWebHexBoundary classes (covers WEB-07 + D-13..D-19 + hex boundary)
- [ ] `requirements.txt` — pin `fastapi==0.136.1`, `uvicorn[standard]==0.46.0`, `httpx==0.28.1` (per RESEARCH §2)
- [ ] `web/__init__.py`, `web/app.py`, `web/routes/__init__.py`, `web/routes/healthz.py` — package + factory + handler scaffolding (per RESEARCH §4 + §5)

*pytest 8.3.3 + pytest-freezer 0.4.9 already installed — no framework install needed.*

---

## Manual-Only Verifications

Items that cannot be exercised from a developer laptop and require operator action on the droplet. Each maps to a ROADMAP success criterion. All are documented in SETUP-DROPLET.md (Plan 11-04).

| Behavior | Requirement | Why Manual | Test Instructions (in SETUP-DROPLET.md) |
|----------|-------------|------------|-------------------------------------------|
| `systemctl status trading-signals-web` shows `active (running)` after droplet reboot (SC-1) | WEB-01 | Requires actual droplet + systemd; no CI parity | `## Verify boot persistence (WEB-01 / SC-1)` section: `sudo reboot` then `systemctl status trading-signals-web` → expect `active (running)` |
| `ss -tlnp | grep 8000` shows `127.0.0.1:8000` only (NOT `0.0.0.0:8000`) (SC-4) | WEB-02 | Requires real OS network stack | `## Verify port binding (WEB-02 / SC-4)` section: `ss -tlnp | grep 8000` → must show `LISTEN ... 127.0.0.1:8000`. Plus external `curl <DROPLET_IP>:8000` → must FAIL |
| `bash deploy.sh` is idempotent on no-op re-run (SC-3) | INFRA-04 | Requires git remote + droplet venv state | `## Verify deploy.sh end-to-end (INFRA-04 / SC-3)` section: `bash deploy.sh && bash deploy.sh` — second invocation must show "Already up to date." from git, "Requirement already satisfied" from pip, exit 0 |
| `systemd-analyze verify trading-signals-web.service` passes | WEB-01 | systemd-analyze unavailable on macOS dev | `## Install systemd unit` section: `sudo systemd-analyze verify /etc/systemd/system/trading-signals-web.service` — expect no output (silence = success) |
| sudoers entry parses cleanly | INFRA-04 | Requires `visudo` and `/etc/sudoers.d/` | `## Install sudoers entry for trader` section: `sudo visudo -c -f /etc/sudoers.d/trading-signals-deploy` — expect "parsed OK" |
| `shellcheck deploy.sh` lints clean | INFRA-04 | shellcheck not pinned in requirements.txt; OS-level tool | `## Verify deploy.sh end-to-end` section (optional): `sudo apt install shellcheck && shellcheck deploy.sh` — expect zero findings |
| Passwordless `sudo -n systemctl restart trading-signals-web` succeeds | INFRA-04 | Requires droplet sudoers + systemd | `## Install sudoers entry for trader` section: `sudo -n systemctl restart trading-signals-web` — must NOT prompt for password |
| External `curl <DROPLET_IP>:8000/healthz` is unreachable | WEB-02 / T-11-01 | Requires external network access | `## Verify port binding` section: from laptop, `curl --max-time 5 http://<DROPLET_IP>:8000/healthz` — expect connection refused or timeout |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (planner filled the per-task map above)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify (every task has an automated check)
- [x] Wave 0 covers all MISSING references (Plan 11-01 creates web/, tests, deps before any other plan executes)
- [x] No watch-mode flags (CI runs are bounded — `-x -q` flags only)
- [x] Feedback latency < 60s (full suite runs in 30-60s; new file alone runs in ~10s)
- [x] Manual-only verifications captured in SETUP-DROPLET.md (Phase 11 deliverable, Plan 11-04)
- [x] `nyquist_compliant: true` set in frontmatter (planner has filled the per-task map and acceptance criteria are grep-verifiable)

**Approval:** planner-approved 2026-04-24; awaiting execution.
