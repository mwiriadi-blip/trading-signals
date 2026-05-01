---
phase: 23
slug: five-year-backtest-validation-gate
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-01
---

# Phase 23 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Source: 23-RESEARCH.md §Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.3.3 |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `.venv/bin/pytest tests/test_backtest_*.py tests/test_web_backtest.py -x -q` |
| **Full suite command** | `.venv/bin/pytest -x -q` |
| **Estimated runtime** | ~30 seconds quick / ~90 seconds full |

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/pytest tests/test_backtest_*.py tests/test_web_backtest.py -x -q`
- **After every plan wave:** Run `.venv/bin/pytest -x -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~30 seconds

---

## Per-Task Verification Map

> Populated by gsd-planner after task IDs are assigned. Initial map mirrors RESEARCH §Validation Architecture requirement → test mapping. Plan-checker flips `nyquist_compliant: true` once all tasks bind to an `<automated>` verify command or to a Wave 0 dependency.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| {tbd-by-planner} | {tbd} | 0 | BACKTEST-01 | T-23-pyarrow | pyarrow pinned + binary wheel only | install | `pip show pyarrow \| grep -E '^Version: 24\\.0\\.0'` | ❌ W0 | ⬜ pending |
| {tbd-by-planner} | {tbd} | 1 | BACKTEST-01 | T-23-cache-tamper | parquet schema-typed binary cache (no eval/code paths on read) | unit | `pytest tests/test_backtest_data_fetcher.py -x` | ❌ W0 | ⬜ pending |
| {tbd-by-planner} | {tbd} | 1 | BACKTEST-01 | — | deterministic replay (same fixture → same trades) | unit | `pytest tests/test_backtest_simulator.py -x` | ❌ W0 | ⬜ pending |
| {tbd-by-planner} | {tbd} | 1 | BACKTEST-01 | — | step() cost reconstruction (gross/net/cost) | unit | `pytest tests/test_backtest_simulator.py::TestCostModel -x` | ❌ W0 | ⬜ pending |
| {tbd-by-planner} | {tbd} | 1 | BACKTEST-02 | — | metrics formulas (Sharpe daily, max_dd, win_rate, expectancy, cum_return) | unit | `pytest tests/test_backtest_metrics.py -x` | ❌ W0 | ⬜ pending |
| {tbd-by-planner} | {tbd} | 1 | BACKTEST-02 | — | JSON report schema completeness (D-05 fields) | unit | `pytest tests/test_backtest_cli.py::TestJsonSchema -x` | ❌ W0 | ⬜ pending |
| {tbd-by-planner} | {tbd} | 2 | BACKTEST-03 | — | render_report() HTML has 3 tab containers + metrics row | unit | `pytest tests/test_backtest_render.py -x` | ❌ W0 | ⬜ pending |
| {tbd-by-planner} | {tbd} | 2 | BACKTEST-03 | T-23-cdn | Chart.js 4.4.6 script tag with SRI hash | unit | `pytest tests/test_backtest_render.py::TestChartJsSri -x` | ❌ W0 | ⬜ pending |
| {tbd-by-planner} | {tbd} | 2 | BACKTEST-03 | T-23-auth | GET /backtest 200 with cookie auth, 401/302 without | integration | `pytest tests/test_web_backtest.py::TestGetBacktest -x` | ❌ W0 | ⬜ pending |
| {tbd-by-planner} | {tbd} | 2 | BACKTEST-03 | T-23-traversal | GET /backtest?run=../../etc/passwd returns 400 | integration | `pytest tests/test_web_backtest.py::TestPathTraversal -x` | ❌ W0 | ⬜ pending |
| {tbd-by-planner} | {tbd} | 2 | BACKTEST-04 | — | CLI exit 0 on PASS / 1 on FAIL | unit | `pytest tests/test_backtest_cli.py::TestExitCode -x` | ❌ W0 | ⬜ pending |
| {tbd-by-planner} | {tbd} | 2 | BACKTEST-04 | T-23-input | POST /backtest/run rejects negative cost / zero account with 400; PASS path 303 | integration | `pytest tests/test_web_backtest.py::TestPostRun -x` | ❌ W0 | ⬜ pending |
| {tbd-by-planner} | {tbd} | 2 | D-09 (hex) | — | AST guard: simulator.py/metrics.py/render.py have no forbidden imports | unit | `pytest tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent -x` | ✅ (extended) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_backtest_data_fetcher.py` — BACKTEST-01 data layer (cache hit/miss, --refresh, parquet round-trip, <5y bail)
- [ ] `tests/test_backtest_simulator.py` — BACKTEST-01 simulator (determinism, sizing reuse, exit reasons, NaN-safe)
- [ ] `tests/test_backtest_metrics.py` — BACKTEST-02 metrics formulas + edge cases (zero/all-loss/all-win)
- [ ] `tests/test_backtest_render.py` — BACKTEST-03 HTML structure + Chart.js SRI + override form + history
- [ ] `tests/test_backtest_cli.py` — BACKTEST-04 argparse + JSON write + exit codes + log format
- [ ] `tests/test_web_backtest.py` — BACKTEST-03/04 routes + path-traversal + cookie auth
- [ ] `tests/fixtures/backtest/golden_report.json` — hand-authored reference report (~50 KB)
- [ ] Extend `tests/test_signal_engine.py:480` AST guard with `BACKTEST_PATHS_PURE = ['backtest/simulator.py', 'backtest/metrics.py', 'backtest/render.py']`
- [ ] Add `pyarrow==24.0.0` to `requirements.txt` (binary wheel)
- [ ] Create `backtest/` package skeleton (`__init__.py`, `__main__.py` placeholders)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Three-tab visual layout renders correctly on mobile (≤375px) | BACKTEST-03 / D-04 | CSS responsiveness across viewports — automated DOM assertions confirm tab containers exist but not visual rendering | After Wave 2 merge: open `/backtest` in Chrome devtools mobile emulation (iPhone SE), verify each tab is reachable and metrics row is readable without horizontal scroll |
| Chart.js equity curves render visually correct (line drawn, axes labelled) | BACKTEST-03 / D-04 | Chart.js draws to canvas — DOM tests can confirm `<canvas>` exists but not pixel output | After Wave 2 merge: trigger a real backtest run, open `/backtest`, confirm three tabs each draw a line chart with non-trivial range |
| Operator override form: spinner appears during 30-60s simulation; submit button disables | BACKTEST-03 / D-14 | Browser-side UX (CSS animation + form submit handler) — server-side tests can't observe spinner visibility | After Wave 2 merge: open `/backtest`, change initial_account to 5000, click [Run with overrides], confirm spinner is visible and submit is disabled until redirect |
| 5y × 2 instruments runs <60s on droplet (1 vCPU) | D-18 / SC-1 | Performance budget on production hardware; local dev may not reflect droplet timing | Post-deploy: `time python -m backtest --years 5` on the droplet via SSH; assert wall time <60s |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s (quick) / < 90s (full)
- [ ] `nyquist_compliant: true` set in frontmatter (planner flips after task IDs bind)

**Approval:** pending
