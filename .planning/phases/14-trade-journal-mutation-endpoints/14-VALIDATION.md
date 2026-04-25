---
phase: 14
slug: trade-journal-mutation-endpoints
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-25
---

# Phase 14 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.3.3 |
| **Config file** | `pytest.ini` (existing) |
| **Quick run command** | `pytest tests/test_web_trades.py tests/test_state_manager.py tests/test_sizing_engine.py -x -q` |
| **Full suite command** | `pytest -q` |
| **Estimated runtime** | Quick ~10s; full ~90s (mostly test_main.py date-sensitive baseline) |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_web_trades.py -x -q` (the new test file added in this phase)
- **After Wave 1 (state_manager + system_params + sizing_engine changes):** Run `pytest tests/test_state_manager.py tests/test_system_params.py tests/test_sizing_engine.py -x -q` — confirms v1.0 hex-core still green after schema migration + fcntl + manual_stop additions
- **After Wave 2 (web/routes/trades.py + dashboard.py modifications):** Run `pytest tests/test_web_*.py tests/test_dashboard.py -x -q`
- **Before `/gsd-verify-work`:** Full suite must be green (excluding the 16 pre-existing test_main.py weekend-skip failures documented in deferred-items.md)
- **Max feedback latency:** 90 seconds (full suite)

---

## Per-Task Verification Map

Populated by planner. Each Phase 14 task produces a test or extends an existing test class. The plan's task-level `<acceptance_criteria>` should state the exact pytest command that proves the task done. Skeleton:

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 14-XX-YY | XX | W | TRADE-01..06 | T-14-NN | See threat model in PLAN | unit / integration | `pytest tests/test_X.py::TestY::test_Z -x` | ✅ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Wave 0 creates test-infrastructure-only scaffolding so Wave 1 tasks have stable fixtures. No production code ships in Wave 0.

- [ ] `tests/test_web_trades.py` — file created with skeleton classes (`TestOpenEndpoint`, `TestOpenPyramidUp`, `TestCloseEndpoint`, `TestModifyEndpoint`, `TestErrorResponses`, `TestHTMXResponses`) — imports only, no test bodies yet
- [ ] `tests/conftest.py` — extend with helpers for: (a) state.json fixture with `manual_stop=None` on positions (v3 schema), (b) HTMX header injection (`HX-Request: true`), (c) auth header from `VALID_SECRET`
- [ ] `tests/fixtures/state_v2_no_manual_stop.json` — v2-schema fixture for migration round-trip test
- [ ] `tests/test_state_manager.py` — extend with `TestSchemaMigrationV2ToV3` skeleton class
- [ ] `tests/test_state_manager.py` — extend with `TestFcntlLock` skeleton class (lock contention, lock release on exception, cross-process safety verified via subprocess)
- [ ] `tests/test_sizing_engine.py` — extend with `TestManualStopOverride` skeleton class
- [ ] `tests/test_system_params.py` (new or extended) — `TestPositionTypedDict` confirms `manual_stop` field exists with `float | None` type
- [ ] `tests/test_dashboard.py` (new) — `TestRenderDashboardHTMXForms` skeleton (open form rendered, action buttons rendered, manual badge rendered when manual_stop set)
- [ ] HTMX 1.9.12 vendored locally OR documented CDN-pinned in dashboard.py with SRI hash `sha384-ujb1lZYygJmzgSwoxRggbCHcjc0rB2XoQrxeTUQyRjrOnlCoYta87iKBWq3EsdM2`

No new pytest deps needed; all covered by existing `pytest==8.3.3`, `pytest-freezer`, `httpx==0.28.1`.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| HTMX form swaps render correctly in real browsers (Chrome, Firefox, Safari) | TRADE-05 / SC-5 | Browser DOM diffing + HTMX runtime not exercisable in TestClient | On droplet: open `https://signals.<domain>/`, log in with auth header (browser ext or curl-style), submit Open form with valid + invalid input, verify error inline rendering and per-row swap. Repeat for Close (2-stage) and Modify. |
| fcntl lock cross-process correctness on the live droplet | D-13 | TestClient is single-process; cross-process collision requires real systemd processes | On droplet: trigger `python main.py --once &` (signal loop) then immediately POST /trades/open from laptop. Both should succeed (no torn writes, both mutations visible in state.json). Repeat 5x to surface intermittent races. |
| Schema migration v2→v3 lands cleanly on the live droplet | D-09 | Real droplet has a v2 state.json; first Phase 14 deploy must migrate without data loss | After `bash deploy.sh` lands Phase 14: `python -c "from state_manager import load_state; s = load_state(); print(s['schema_version'], list(s['positions'].keys()), all('manual_stop' in p for p in s['positions'].values() if p))"` — expect schema_version=3, all positions have manual_stop key. |
| Error responses render inline in HTMX without full-page reload | TRADE-02 / SC-5 | Browser-only behavior; TestClient sees JSON but not HTMX swap | In browser: submit Open with invalid entry_price=-1 → expect `<div class="error">` populated above form, NO page reload, NO URL change. |
| 2-stage destructive close UX feels intuitive | UI-SPEC §Decision 5 | Subjective UX evaluation | Operator submits Close on a real position, evaluates: (a) is the confirmation flow obvious? (b) is Cancel reachable? (c) does the confirmation panel show the right exit_price input? Adjust copy if needed. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 90s
- [ ] Schema migration round-trip test (v2 fixture → load → assert manual_stop=None on positions → save → reload → still v3) is in Wave 1 acceptance_criteria
- [ ] fcntl lock contention test (subprocess holds exclusive lock → save_state blocks → release → save_state completes) is in Wave 1 acceptance_criteria
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
