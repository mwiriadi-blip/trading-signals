---
phase: 11
slug: web-skeleton-fastapi-uvicorn-systemd
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-24
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
| **Quick run command** | `pytest tests/test_web_healthz.py -x -q` |
| **Full suite command** | `pytest tests/ -q` |
| **Estimated runtime** | ~5 seconds (new file) / ~30-60 seconds (full suite, ~660+ existing tests) |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_web_healthz.py -x -q`
- **After every plan wave:** Run `pytest tests/ -q`
- **Before `/gsd-verify-work 11`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

> Plans populate the rows below in step 8. The planner derives Task IDs from PLAN.md frontmatter and per-task `<acceptance_criteria>` blocks. Map MUST cover every requirement (WEB-01, WEB-02, WEB-07, INFRA-04) and every locked decision (D-01..D-25).

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD-by-planner | TBD | TBD | WEB-07 | T-11-XX | `/healthz` returns 200 + JSON `{status:"ok",last_run:...,stale:bool}` | unit | `pytest tests/test_web_healthz.py::TestHealthz -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_web_healthz.py` — TestHealthz, TestHealthzMissingStatefile, TestHealthzStaleness, TestHealthzDegradedPath classes (covers WEB-07 + D-13..D-19)
- [ ] `tests/conftest.py` — confirm shared fixtures (existing) cover state.json monkeypatching; add `tmp_state_file` fixture if missing
- [ ] `requirements.txt` — pin `fastapi==0.136.1`, `uvicorn[standard]==0.46.0`, `httpx==0.28.1` (per RESEARCH.md §2)
- [ ] `web/__init__.py`, `web/app.py`, `web/routes/__init__.py`, `web/routes/healthz.py` — package + factory + handler scaffolding (per RESEARCH.md §4)
- [ ] `systemd/trading-signals-web.service` — unit file committed to repo (per RESEARCH.md §3)
- [ ] `deploy.sh` at repo root — idempotent script (per RESEARCH.md §7)

*pytest 8.3.3 + pytest-freezer 0.4.9 already installed — no framework install needed.*

---

## Manual-Only Verifications

Items that cannot be exercised from a developer laptop and require operator action on the droplet. Each maps to a ROADMAP success criterion.

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `systemctl status trading-signals-web` shows `active (running)` after droplet reboot (SC-1) | WEB-01 | Requires actual droplet + systemd; no CI parity | After install: `sudo reboot`; on reconnect: `systemctl status trading-signals-web` — expect `active (running)`. Document in SETUP-DROPLET.md. |
| `ss -tlnp \| grep 8000` shows `127.0.0.1:8000` only (NOT `0.0.0.0:8000`) (SC-4) | WEB-02 | Requires real OS network stack | On droplet: `ss -tlnp \| grep 8000` — output must be `LISTEN ... 127.0.0.1:8000 ...`. If `0.0.0.0:8000` appears, FAIL — uvicorn host arg is wrong. |
| `bash deploy.sh` is idempotent on no-op re-run (SC-3) | INFRA-04 | Requires git remote + droplet venv state | On droplet, in repo dir: `bash deploy.sh && bash deploy.sh`. Second invocation must show "Already up to date." from git, "Requirement already satisfied" from pip, exit 0. |
| `systemd-analyze verify trading-signals-web.service` passes | WEB-01 | systemd-analyze unavailable on macOS dev | On droplet: `sudo systemd-analyze verify /etc/systemd/system/trading-signals-web.service` — expect no warnings/errors. |
| sudoers entry parses cleanly | INFRA-04 | Requires `visudo` and `/etc/sudoers.d/` | On droplet: `sudo visudo -c -f /etc/sudoers.d/trading-signals-deploy` — expect "parsed OK". |
| `shellcheck deploy.sh` lints clean | INFRA-04 | shellcheck not pinned in requirements.txt; OS-level tool | On droplet (after `apt install shellcheck`) or local macOS (`brew install shellcheck`): `shellcheck deploy.sh` — expect zero findings. Optional but recommended. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies (planner fills the per-task map above)
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags (CI runs are bounded)
- [ ] Feedback latency < 60s
- [ ] Manual-only verifications captured in SETUP-DROPLET.md (Phase 11 deliverable)
- [ ] `nyquist_compliant: true` set in frontmatter once planner has filled the per-task map and acceptance criteria are grep-verifiable

**Approval:** pending
