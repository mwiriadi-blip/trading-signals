---
phase: 13
plan: 01
subsystem: web/test-infrastructure
tags: [auth, fastapi, test-infra, doc, wave-0]
requires: []
provides:
  - "tests/conftest.py autouse fixture (_set_web_auth_secret_for_web_tests)"
  - "VALID_SECRET + AUTH_HEADER_NAME single-source constants"
  - "Updated FORBIDDEN_FOR_WEB without 'dashboard' (D-07 hex extension)"
  - "Renamed AST guard test_web_adapter_imports_are_local_not_module_top covering 5 web/ files"
  - "4 skeleton test files (auth_middleware, dashboard, state, app_factory) with class declarations only"
  - "SETUP-DROPLET.md '## Configure auth secret' H2 section + 5 doc-completeness regression tests"
  - ".planning/phases/13-auth-read-endpoints/deferred-items.md (16 pre-existing test_main.py failures)"
affects:
  - tests/conftest.py
  - tests/test_web_healthz.py
  - tests/test_web_auth_middleware.py
  - tests/test_web_dashboard.py
  - tests/test_web_state.py
  - tests/test_web_app_factory.py
  - tests/test_setup_droplet_doc.py
  - SETUP-DROPLET.md
tech-stack:
  added: []
  patterns:
    - "pytest autouse fixture scoped by request.node.fspath filename match"
    - "AST-walk hex-boundary guard with absent-file skip-guard for Wave 0"
    - "Doc-completeness regression tests via re.search + substring assertions"
key-files:
  created:
    - tests/test_web_auth_middleware.py
    - tests/test_web_dashboard.py
    - tests/test_web_state.py
    - tests/test_web_app_factory.py
    - .planning/phases/13-auth-read-endpoints/deferred-items.md
  modified:
    - tests/conftest.py
    - tests/test_web_healthz.py
    - SETUP-DROPLET.md
    - tests/test_setup_droplet_doc.py
decisions:
  - "Autouse fixture in tests/conftest.py is the structural fix for the REVIEWS HIGH finding (11 direct create_app() invocations in test bodies); fixture-only retrofit was insufficient"
  - "VALID_SECRET = 'a' * 32 lives ONCE in tests/conftest.py per REVIEWS LOW #6; downstream test files import the name (no redefinition)"
  - "FORBIDDEN_FOR_WEB drops 'dashboard' (Phase 13 D-07 promotes dashboard to allowed adapter import for web/routes/dashboard.py)"
  - "Renamed test_web_app_does_not_import_state_manager_at_module_top → test_web_adapter_imports_are_local_not_module_top with absent-file skip-guard so Wave 0 commits don't fail before Wave 1 creates the new web/ files"
  - "SETUP-DROPLET.md '## Configure auth secret' section slotted between 'Install systemd unit' and 'Install sudoers entry for trader' (systemd unit's EnvironmentFile=- requires .env BEFORE Plan 13-02 D-16 fail-closed)"
metrics:
  duration: "~7m22s"
  tasks: 3
  files_created: 5
  files_modified: 4
  tests_added: 6  # 1 new healthz hex-boundary regression + 5 new doc-completeness tests in TestDocStructure
  tests_unchanged_but_now_pass_via_autouse: 17  # all of test_web_healthz.py
  completed: 2026-04-25
---

# Phase 13 Plan 01: Wave 0 Test Infrastructure + Auth-Secret Doc Summary

Shared test-infrastructure scaffolding (autouse `WEB_AUTH_SECRET` fixture, hex-boundary extension, 4 skeleton test files, SETUP-DROPLET.md operator section) — zero production code shipped; foundation for parallel Waves 1-2.

## What Was Done

This plan ships **only test infrastructure + operator documentation**. No `web/` source files were touched — production changes for Phase 13 are deferred to Plan 13-02 (factory), Plan 13-03 (auth middleware), Plan 13-04 (state route), and Plan 13-05 (dashboard route).

### Task 1 — Autouse fixture + hex-boundary extension (commit 56c185a)

- **`tests/conftest.py`** (was empty 0-byte file): populated with the autouse fixture `_set_web_auth_secret_for_web_tests`, `VALID_SECRET = 'a' * 32` constant, `AUTH_HEADER_NAME = 'X-Trading-Signals-Auth'` constant, and `valid_secret` + `auth_headers` helper fixtures. The autouse fixture activates only for tests whose file path matches `test_web_*` — precisely covering the existing Phase 11 healthz tests (which call `create_app()` directly in 11 test bodies at lines 70, 83, 90, 105, 115, 126, 133, 148, 159, 172) AND all four Phase 13 web test files. This is the **REVIEWS HIGH fix**: the previous fixture-only retrofit was insufficient because direct `create_app()` invocations in test bodies don't go through `app_instance`. Once Plan 13-02 lands D-16 fail-closed, all 11 direct calls would have raised `RuntimeError` — the autouse fixture pre-sets the env var and prevents the regression.
- **`tests/test_web_healthz.py`**: removed `'dashboard'` from `TestWebHexBoundary.FORBIDDEN_FOR_WEB` per Phase 13 D-07 (Phase 13 promotes `dashboard` to an allowed adapter import for `web/routes/dashboard.py`). Added regression test `test_dashboard_is_not_forbidden_for_web_phase_13_D07` to lock the change. Renamed `test_web_app_does_not_import_state_manager_at_module_top` → `test_web_adapter_imports_are_local_not_module_top` and extended its scan list to all 5 web/ Python files (`web/app.py`, `web/routes/healthz.py`, `web/routes/dashboard.py`, `web/routes/state.py`, `web/middleware/auth.py`) with an `if not py_path.exists(): continue` guard so the test passes during Wave 0 (before Wave 1 creates the new files). The `forbidden_module_top = frozenset({'state_manager', 'dashboard'})` set now covers both adapters at module-top. **No code changes to the 11 direct `create_app()` invocations in test bodies — the autouse fixture handles them.**
- **Test count**: tests/test_web_healthz.py went from 16 passing → 17 passing (one new regression test added).

### Task 2 — 4 skeleton test files for Waves 1-2 (commit c33e6be)

Created four importable Python modules that pytest can `--collect-only` cleanly — each ships only class declarations + module docstring + `pass` bodies. Wave 1+ plans (02..05) populate the test methods.

- **`tests/test_web_auth_middleware.py`** — 6 class skeletons (`TestAuthRequired`, `TestAuthPasses`, `TestExemption`, `TestUnauthorizedResponse`, `TestAuditLog`, `TestConstantTimeCompare`) for Plan 13-03.
- **`tests/test_web_dashboard.py`** — 4 class skeletons (`TestDashboardResponse`, `TestStaleness`, `TestRenderFailure`, `TestFirstRun`) for Plan 13-05.
- **`tests/test_web_state.py`** — 1 class skeleton (`TestStateResponse`) for Plan 13-04.
- **`tests/test_web_app_factory.py`** — 2 class skeletons (`TestSecretValidation`, `TestDocsDisabled`) for Plan 13-02.
- All 4 files match the Phase 11 `tests/test_web_healthz.py` pattern (triple-single-quote docstring, `from pathlib import Path`, `import pytest`, `from fastapi.testclient import TestClient`). None redefine `VALID_SECRET` (REVIEWS LOW #6 single-source invariant preserved).

### Task 3 — SETUP-DROPLET.md auth-secret section + regression tests (commit 0ac049d)

- **`SETUP-DROPLET.md`**: inserted new H2 section `## Configure auth secret (Phase 13 AUTH-01)` between `## Install systemd unit` and `## Install sudoers entry for trader` (slot rationale: the unit's `EnvironmentFile=-` requires `.env` to exist with `WEB_AUTH_SECRET` BEFORE Plan 13-02's fail-closed lock can boot the unit cleanly). Section content: `openssl rand -hex 16` (with `python3 secrets.token_hex` fallback) → `chmod 600 .env` → `sudo systemctl restart trading-signals-web` → `journalctl -u trading-signals-web -n 20` verify → curl auth-gate end-to-end test (401 without header, 200/503 with). Includes a forward-reference rotation note (deferred to v1.2 per CONTEXT.md D-20).
- **`SETUP-DROPLET.md`** (additional edits): added a forward-reference note in the prerequisites preamble pointing to the new section; removed the `Auth secret → Phase 13` bullet from `## What's NOT in this doc` (it IS in this doc now).
- **`tests/test_setup_droplet_doc.py`**: appended 5 new methods inside `TestDocStructure` — `test_section_configure_auth_secret`, `test_auth_secret_section_has_openssl_command`, `test_auth_secret_section_has_chmod_600`, `test_auth_secret_section_has_systemctl_restart`, `test_auth_secret_min_length_documented`. Suite went from 37 passing → 42 passing.

## Why This Matters

Wave 0 is the structural foundation that makes the four downstream Wave 1-2 plans (02..05) **independently parallelizable**. Without the autouse fixture in conftest.py, every Wave 1 plan would have to retrofit the same fixture wiring locally and risk drift. Without the hex-boundary update, Plan 13-05's `web/routes/dashboard.py` import of the `dashboard` module would fail `TestWebHexBoundary`. Without the skeleton files, Plans 02..05 would have to coordinate file creation order. Without the SETUP-DROPLET.md section, Phase 13 would ship code that requires operator action with no documented procedure.

The REVIEWS HIGH finding from cross-AI review (codex's catch — gemini missed it) was that the original Plan 13-01 retrofitted only the `app_instance` fixture, but `tests/test_web_healthz.py` has 11 direct `create_app()` invocations inside test bodies that don't use `app_instance`. The autouse-fixture-in-conftest.py pattern is the structural fix.

## Verification Results

- `pytest tests/test_web_healthz.py -x -q` → **17 passed in 0.20s**
- `pytest tests/test_setup_droplet_doc.py -x -q` → **42 passed in 0.03s**
- `pytest tests/test_web_systemd_unit.py -x -q` → **32 passed in 0.02s**
- `pytest tests/test_web_healthz.py tests/test_setup_droplet_doc.py tests/test_web_systemd_unit.py -x -q` → **91 passed in 0.30s**
- 5 web test files (`test_web_*.py`) collect 17 tests without ImportError under `pytest --collect-only` (4 skeleton files have no test methods yet — exit 5 means "no tests collected" for those, which is the intended Wave 0 behavior).
- `grep -rn "FORBIDDEN_FOR_WEB" tests/` returns one set definition in `tests/test_web_healthz.py` and that set does NOT contain `'dashboard'`.
- `grep -rc "VALID_SECRET = 'a' \* 32" tests/` returns exactly 1 (single source: `tests/conftest.py:1` reference — REVIEWS LOW #6 invariant preserved).
- `grep -c "autouse=True" tests/conftest.py` returns 1 (REVIEWS HIGH fix landed).

## Decisions Made

- **Autouse fixture scoping by filename match (`test_web_*.py`)** instead of by collection.modifyitems. Filename match is grep-able, declarative, and exactly mirrors the convention researchers already established (`test_web_<route>.py`).
- **Single source of truth for VALID_SECRET** in conftest.py per REVIEWS LOW #6. Wave 1+ test files will import `from .conftest import VALID_SECRET, AUTH_HEADER_NAME` (or via the `valid_secret` / `auth_headers` fixtures).
- **Renamed AST guard method** from `test_web_app_does_not_import_state_manager_at_module_top` to `test_web_adapter_imports_are_local_not_module_top` because the contract widened from "state_manager" to "any adapter (state_manager or dashboard)" per Phase 13 D-07. The new name reflects the actual contract.
- **Absent-file skip-guard** in the AST scan loop so Wave 0 doesn't fail before Wave 1 creates the new files. By Wave 2 close, all 5 web/ files exist and the guard is benign.
- **SETUP-DROPLET.md section slot** — placed between Install systemd unit and Install sudoers entry because `EnvironmentFile=-` requires `.env` to be in place BEFORE the unit can boot under Plan 13-02 D-16 fail-closed. Sudoers comes after.

## Deviations from Plan

### Auto-fixed issues

None of Rules 1-3 fired during execution. Plan was executed verbatim as written.

### Authentication gates

None. No external auth required for this plan (no API keys, no tokens, no OAuth).

### Pre-existing test failures (logged to deferred-items.md, not auto-fixed per scope-boundary rule)

`pytest -q` shows **16 pre-existing failures in `tests/test_main.py`** — verified pre-existing on parent commit `b1f9b8f` (the v1.0 cleanup head, before any 13-01 work) by checking out `tests/conftest.py` and `tests/test_web_healthz.py` from `b1f9b8f` and re-running. The first failing test (`test_fetch_failure_exits_nonzero_no_save_state`) reports `rc == 0` instead of expected `rc == 2` for `DataFetchError` — this is an ERR-01 contract drift between `main.py` and the tests, completely unrelated to Phase 13 (auth + read endpoints). Logged to `.planning/phases/13-auth-read-endpoints/deferred-items.md` for future investigation. **Not a 13-01 regression** — the failures pre-date Phase 13 entirely.

## Threat Surface

No new production code, no new endpoints, no new auth surfaces, no schema changes. Only tracked surface introduced by this plan:

- Sentinel `VALID_SECRET = 'a' * 32` in test fixtures (T-13-00b in plan threat model — accepted; tests-only, never reaches production).
- Example dummy `WEB_AUTH_SECRET` value `<paste-32-char-hex-here>` placeholder in SETUP-DROPLET.md (T-13-00 — accepted; explicit placeholder, operator must replace).

No threat-flag findings. Substantive Phase 13 threat models live in Plans 13-02..13-05.

## What Comes Next

Plans 13-02 through 13-05 (Waves 1 + 2) can now run **in parallel** without coordinating fixture changes. They will:

- **Plan 13-02** (Wave 1, sequential — depends on 13-01): extend `web/app.py::create_app()` with secret validation, middleware registration, `docs_url=None / redoc_url=None / openapi_url=None`, and route registration. Populates `tests/test_web_app_factory.py` test bodies.
- **Plans 13-03, 13-04, 13-05** (Wave 2, parallel — all depend on 13-02): implement the auth middleware, the `/api/state` route, and the `/` dashboard route + corresponding test bodies in the four skeleton files.

The Wave 1-2 plans inherit the autouse `WEB_AUTH_SECRET` fixture, the `auth_headers` fixture, and the relaxed hex-boundary set automatically.

## Self-Check: PASSED

**Files created (verified exist):**
- tests/test_web_auth_middleware.py ✓
- tests/test_web_dashboard.py ✓
- tests/test_web_state.py ✓
- tests/test_web_app_factory.py ✓
- .planning/phases/13-auth-read-endpoints/deferred-items.md ✓

**Files modified (verified diff vs b1f9b8f):**
- tests/conftest.py ✓ (now 67 lines; was 0)
- tests/test_web_healthz.py ✓ (FORBIDDEN_FOR_WEB updated, AST guard renamed/extended)
- SETUP-DROPLET.md ✓ ('## Configure auth secret' present at line 48)
- tests/test_setup_droplet_doc.py ✓ (5 new methods in TestDocStructure)

**Commits (verified in `git log --oneline`):**
- 56c185a test(13-01): add autouse WEB_AUTH_SECRET fixture + hex-boundary extension ✓
- c33e6be test(13-01): add skeleton test files for Waves 1-2 ✓
- 0ac049d docs(13-01): add Configure auth secret section to SETUP-DROPLET.md ✓
