---
phase: 11-web-skeleton-fastapi-uvicorn-systemd
verified: 2026-04-24T00:00:00+08:00
status: human_needed
score: 4/4 must-haves verified (automated); 4 operator-manual items pending
overrides_applied: 0
human_verification:
  - test: "After running SETUP-DROPLET.md §Install systemd unit and rebooting: `systemctl status trading-signals-web`"
    expected: "Active: active (running) — unit auto-starts without operator login"
    why_human: "Requires live DigitalOcean droplet with systemd; cannot simulate reboot in dev"
  - test: "After boot persistence check: `ss -tlnp | grep 8000`"
    expected: "Shows 127.0.0.1:8000 only — no 0.0.0.0:8000 entry"
    why_human: "Requires real OS network stack and running uvicorn process"
  - test: "Run `bash deploy.sh` twice in a row on the droplet"
    expected: "Second run prints 'Already up to date', 'Requirement already satisfied', exit 0 both runs"
    why_human: "Requires git remote, droplet venv, and systemd (deploy.sh calls sudo systemctl restart)"
  - test: "Verify passwordless sudo works: `sudo -n systemctl restart trading-signals-web`"
    expected: "Silent success — no password prompt"
    why_human: "Requires /etc/sudoers.d/trading-signals-deploy installed on the droplet"
---

# Phase 11: Web Skeleton — FastAPI + uvicorn + systemd — Verification Report

**Phase Goal:** Stand up a FastAPI app on the droplet as a systemd unit, serving `/healthz` on `localhost:8000` via uvicorn, with an idempotent deploy script. No HTTPS, no auth, no dashboard yet — just proof that the web process survives reboots and deploys cleanly.
**Verified:** 2026-04-24
**Status:** human_needed — all 4 SCs verified in repo; 4 operator-manual items required for final close
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | systemd unit auto-starts on boot | VERIFIED (repo) + HUMAN NEEDED (droplet) | `systemd/trading-signals-web.service` has `WantedBy=multi-user.target`, `Restart=on-failure`, `RestartSec=10s`, all 5 hardening directives, `After=network.target`, `Wants=trading-signals.service`, `User=trader`, `Group=trader`; final validation requires droplet reboot |
| 2 | `/healthz` returns 200 with correct JSON body | VERIFIED | `web/routes/healthz.py` returns `{"status":"ok","last_run":<YYYY-MM-DD or null>,"stale":<bool>}`; uses `date.fromisoformat` (REVIEWS HIGH #1); D-19 never-crash; C-2 local import; 16 tests all green |
| 3 | `deploy.sh` is idempotent | VERIFIED (repo) + HUMAN NEEDED (droplet) | `deploy.sh` has `#!/usr/bin/env bash` + `set -euo pipefail`; branch check first; ff-only pull; two separate `sudo -n systemctl restart` calls; retry loop smoke test; no pip-upgrade, no sleep 3, no combined restart; 31 tests all green; final validation requires droplet double-run |
| 4 | uvicorn binds 127.0.0.1:8000 only, workers=1 | VERIFIED (repo) + HUMAN NEEDED (droplet) | Unit ExecStart has `--host 127.0.0.1 --workers 1`; `0.0.0.0` absent from unit file; `test_execstart_does_not_bind_all_interfaces` green; final validation requires `ss -tlnp` on droplet |

**Score:** 4/4 truths verified in repo artifacts and test suite. 4 truths additionally require operator-manual droplet verification (see Human Verification Required).

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `web/__init__.py` | Empty package marker | VERIFIED | Exists, 0 bytes (empty) |
| `web/app.py` | `create_app()` factory + module-level `app` | VERIFIED | Factory present, no `docs_url=None`/`redoc_url=None` kwargs (REVIEWS MEDIUM #6 applied), no state_manager at module top |
| `web/routes/__init__.py` | Empty package marker | VERIFIED | Exists |
| `web/routes/healthz.py` | `GET /healthz` handler with C-2 local import, D-19 never-crash, `date.fromisoformat` | VERIFIED | All three invariants confirmed in source |
| `systemd/trading-signals-web.service` | Complete unit file with hardening, loopback-only, workers=1 | VERIFIED | All 5 hardening directives, `EnvironmentFile=-` dash prefix, no `0.0.0.0` |
| `deploy.sh` | Idempotent script, executable, two `sudo -n` restarts, retry loop | VERIFIED | `chmod +x` confirmed by `test_file_is_executable`; all invariants confirmed |
| `SETUP-DROPLET.md` | 7-section operator runbook with sudoers verification step | VERIFIED | All 7 sections present; passwordless-sudo verification step included (REVIEWS HIGH #4) |
| `tests/test_web_healthz.py` | 5 classes, 16 tests | VERIFIED | 16 tests, all green |
| `tests/test_web_systemd_unit.py` | 6 classes, 32 tests | VERIFIED | 32 tests, all green |
| `tests/test_deploy_sh.py` | 4 classes, 31 tests | VERIFIED | 31 tests, all green; negative assertions for pip-upgrade (count=0), combined-restart (count=0), sleep 3 (count=0) |
| `tests/test_setup_droplet_doc.py` | 9 classes, 37 tests | VERIFIED | 37 tests, all green; drift guard + sudoers-form check present |
| `requirements.txt` | `fastapi==0.136.1`, `uvicorn[standard]==0.46.0`, `httpx==0.28.1` with `==` pins | VERIFIED | All three lines exact-pinned, no `>=` or `~=` |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `web/app.py::create_app()` | `web.routes.healthz.register(app)` | direct call | VERIFIED | `from web.routes import healthz as healthz_route; healthz_route.register(application)` on line 33 |
| `web/routes/healthz.py::healthz()` | `state_manager.load_state()` | local import inside handler body | VERIFIED | `from state_manager import load_state` at line 31 — inside function, not module top |
| `systemd/trading-signals-web.service::ExecStart` | `web.app:app` uvicorn entry point | `--workers 1 --host 127.0.0.1` | VERIFIED | ExecStart line confirmed by `test_execstart_references_web_app_module_exactly` |
| `deploy.sh` | `trading-signals` unit | `sudo -n systemctl restart trading-signals` | VERIFIED | Line 50: `sudo -n systemctl restart trading-signals` (exact match, separate line) |
| `deploy.sh` | `trading-signals-web` unit | `sudo -n systemctl restart trading-signals-web` | VERIFIED | Line 51: `sudo -n systemctl restart trading-signals-web` (exact match, separate line) |
| `deploy.sh` | `GET /healthz` smoke test | 10-attempt retry curl loop | VERIFIED | Lines 55-65: `for i in 1 2 3 4 5 6 7 8 9 10; do if curl -fsS --max-time 2 http://127.0.0.1:8000/healthz ...` |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `web/routes/healthz.py` | `last_run`, `stale` | `state_manager.load_state()` → `state.get('last_run')` | Yes — reads live `state.json` via `load_state()` on every request; no caching per D-18 | FLOWING |

Note: `load_state()` falls back to fresh state (last_run=None) when state.json is missing, which is correct behavior per D-15. Not a stub.

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| FastAPI app importable with correct entry point | `.venv/bin/python -c "from web.app import create_app, app; assert app is not None"` | Not run (import test covered by test suite) | SKIP (covered by test_web_healthz.py) |
| `deploy.sh` bash syntax valid | `bash -n deploy.sh` | Covered by `test_bash_syntax_check_passes` — 0 exit code | PASS (via test) |
| Unit file has no `0.0.0.0` | `grep 0.0.0.0 systemd/trading-signals-web.service` | No output — VERIFIED | PASS |
| Full test suite | `.venv/bin/pytest tests/ -q` | 797 passed in 93.85s | PASS |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| WEB-01 | 11-02, 11-04 | FastAPI app as separate systemd unit, starts on boot | VERIFIED (repo) + HUMAN (droplet) | `systemd/trading-signals-web.service` with `WantedBy=multi-user.target`; 32 unit-file tests green; SETUP-DROPLET.md §Verify boot persistence covers droplet-side |
| WEB-02 | 11-02, 11-04 | uvicorn on localhost:8000; nginx reverse-proxy (Phase 12) | VERIFIED (repo) + HUMAN (droplet) | ExecStart has `--host 127.0.0.1 --port 8000`; nginx deferred to Phase 12; `ss -tlnp` verification documented in SETUP-DROPLET.md |
| WEB-07 | 11-01 | GET /healthz returns 200 with JSON body | VERIFIED | Handler returns `{"status":"ok","last_run":..,"stale":..}`; 16 tests green; exempt from auth per D-17 |
| INFRA-04 | 11-03, 11-04 | deploy.sh idempotent script | VERIFIED (repo) + HUMAN (droplet) | deploy.sh implements D-23 sequence; 31 tests green; SETUP-DROPLET.md §Verify deploy.sh end-to-end covers droplet-side |

**Checkbox status in REQUIREMENTS.md:** WEB-01 `[x]`, WEB-02 `[x]`, WEB-07 `[x]`, INFRA-04 `[x]` — correctly marked complete in the checklist section.

**Traceability table discrepancy:** The traceability table in REQUIREMENTS.md still shows `Pending` for WEB-01, WEB-02, WEB-07, INFRA-04. This is a documentation-only gap — the checklist `[x]` values are the authoritative status. The traceability table was not updated by the executor. This does not affect code correctness.

---

### REVIEWS Fix Verification

| Item | Severity | Expected Fix | Verified in File | Pass/Fail |
|------|----------|-------------|-----------------|-----------|
| HIGH #1 — `last_run` is YYYY-MM-DD; use `date.fromisoformat` not `datetime.fromisoformat` | HIGH | Handler parses with `date.fromisoformat` | `web/routes/healthz.py` line 42: `last_dt = _date.fromisoformat(last_run)` | PASS |
| HIGH #2 — Test fixtures monkeypatch `state_manager.load_state` directly, not `STATE_FILE` | HIGH | All state tests use `monkeypatch.setattr(state_manager, 'load_state', ...)` | `tests/test_web_healthz.py` — all 6 monkeypatch calls target `load_state`; `STATE_FILE` not used as patch target | PASS |
| HIGH #3 — `sleep 3` replaced with retry loop (10 attempts @ 1s) | HIGH | `for i in 1..10; curl --max-time 2 ...; sleep 1` | `deploy.sh` lines 55-65; `test_step_7_sleep_3_heuristic_is_FORBIDDEN` green | PASS |
| HIGH #4 — TWO separate `sudo -n systemctl restart <unit>` calls + SETUP-DROPLET verification step | HIGH | Two separate lines; `sudo -n` on both; verification step in runbook | `deploy.sh` lines 50-51; `SETUP-DROPLET.md` §Install sudoers entry — verification block; `test_passwordless_sudo_verification_step` green | PASS |
| MEDIUM #5 — `EnvironmentFile=-` leading dash (optional) | MEDIUM | `EnvironmentFile=-/home/trader/trading-signals/.env` | `systemd/trading-signals-web.service` line 11; `test_environment_file_is_optional` green | PASS |
| MEDIUM #6 — No `docs_url=None`/`redoc_url=None` kwargs in `create_app()` | MEDIUM | `FastAPI(title=..., description=..., version=...)` only | `web/app.py` lines 28-32 — no `docs_url`/`redoc_url` kwargs | PASS |
| MEDIUM #7 — `pip install --upgrade pip` DROPPED from deploy.sh | MEDIUM | Absent from deploy.sh | `grep 'pip install --upgrade pip' deploy.sh` → no output; `test_step_4_pip_upgrade_is_DROPPED` green | PASS |
| LOW #8 — ExecStart references `web.app:app` exactly | LOW | `web.app:app` in ExecStart and unit text | `systemd/trading-signals-web.service` ExecStart line; `test_execstart_references_web_app_module_exactly` green | PASS |
| LOW #9 — Test brittleness/over-specification | LOW | Deferred to Phase 16 hardening | Noted in VALIDATION.md as deferred; cosmetic, not blocking | DEFERRED |

All HIGH and MEDIUM REVIEWS items are verified as landed in actual source code. LOW #9 is explicitly deferred per VALIDATION.md.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `web/routes/healthz.py` | 50 | `except Exception as exc:` broad catch | INFO | Intentional per D-19 never-crash design decision; documented with `# noqa: BLE001` and WARN log |
| None | — | No TODOs, FIXMEs, placeholder returns, hardcoded empty data, or stray `return null` found in Phase 11 artifacts | — | — |

No blocker or warning-level anti-patterns found. The broad exception catch is intentional and documented.

---

### Test Suite Summary

**Command:** `.venv/bin/pytest tests/ -q`
**Result:** 797 passed in 93.85s
**Phase 11 specific files:** 116 tests across 4 test files (all green)

| Test File | Tests | Classes | Status |
|-----------|-------|---------|--------|
| `tests/test_web_healthz.py` | 16 | 5 | PASS |
| `tests/test_web_systemd_unit.py` | 32 | 6 | PASS |
| `tests/test_deploy_sh.py` | 31 | 4 | PASS |
| `tests/test_setup_droplet_doc.py` | 37 | 9 | PASS |
| **Phase 11 total** | **116** | **24** | **ALL GREEN** |
| Prior phases (regression) | 681 | — | PASS |
| **Full suite** | **797** | — | **ALL GREEN** |

---

### Human Verification Required

The following items cannot be verified programmatically — they require a live DigitalOcean droplet with systemd. These are documented operator-manual steps, not code gaps.

#### 1. Boot Persistence (SC-1)

**Test:** Follow SETUP-DROPLET.md §Install systemd unit, then §Verify boot persistence. Run `sudo reboot`, reconnect after ~30s.
**Expected:** `systemctl status trading-signals-web` shows `Active: active (running)` with timestamp after reboot; no operator login required.
**Why human:** Requires live droplet with systemd; cannot simulate reboot in macOS dev environment.

#### 2. Port Binding Verification (SC-4)

**Test:** After starting the web unit: `ss -tlnp | grep 8000`
**Expected:** Output shows `127.0.0.1:8000` only. From external host: `curl --max-time 5 http://<DROPLET_IP>:8000/healthz` returns connection refused or timeout.
**Why human:** Requires real OS network stack and running uvicorn process; cannot verify without droplet.

#### 3. deploy.sh Idempotency (SC-3)

**Test:** On the droplet: `bash deploy.sh && bash deploy.sh`
**Expected:** Second run shows "Already up to date." from git, "Requirement already satisfied" from pip, restarts both services, smoke test passes; exit 0 both times.
**Why human:** Requires git remote access, droplet venv, and systemd (deploy.sh calls `sudo -n systemctl restart`).

#### 4. Passwordless Sudo Verification (REVIEWS HIGH #4)

**Test:** After installing /etc/sudoers.d/trading-signals-deploy: `sudo -n systemctl restart trading-signals-web`
**Expected:** Silent success (no password prompt). If it prompts, deploy.sh will fail on every run.
**Why human:** Requires /etc/sudoers.d/ on droplet with correct systemctl path matching `which systemctl`.

---

### Gaps Summary

No code gaps found. All 4 success criteria are verifiable in the repository. All REVIEWS HIGH and MEDIUM items are confirmed landed in source. The 797-test suite is fully green. The only outstanding items are operator-manual droplet verifications that cannot be automated against a local dev environment — these are expected per the VALIDATION.md §Manual-Only Verifications table and are fully documented in SETUP-DROPLET.md.

**Traceability table not updated:** REQUIREMENTS.md traceability table still shows `Pending` for WEB-01, WEB-02, WEB-07, INFRA-04 despite the checklist items being marked `[x]`. This is a documentation inconsistency that does not affect functionality. Recommend updating the table to `Complete` as part of phase close.

---

### Deferred Items

Items from REVIEWS LOW #9 explicitly deferred to Phase 16 per VALIDATION.md:

| # | Item | Addressed In | Evidence |
|---|------|-------------|----------|
| 1 | Test brittleness / over-specification (exact test class names, exact file contents, exact doc wording) | Phase 16 | VALIDATION.md notes: "Deferred notes in each plan; not reworked" |

---

### Operator-Manual Follow-Ups

These are not blockers for Phase 11 source-code close — they are one-time droplet operations:

1. Follow SETUP-DROPLET.md in full (systemd unit install → sudoers → port binding → deploy.sh → boot persistence)
2. Confirm `systemctl status trading-signals-web` shows `active (running)` post-reboot
3. Confirm `ss -tlnp | grep 8000` shows `127.0.0.1:8000` only
4. Confirm `bash deploy.sh && bash deploy.sh` both exit 0
5. Update ROADMAP.md progress table Phase 11 row from "Not started / 0/4" to "Complete / 4/4 / 2026-04-24"
6. Update REQUIREMENTS.md traceability table to show `Complete` for WEB-01, WEB-02, WEB-07, INFRA-04

---

*Verified: 2026-04-24*
*Verifier: Claude (gsd-verifier)*
