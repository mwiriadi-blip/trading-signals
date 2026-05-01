---
phase: 23
slug: five-year-backtest-validation-gate
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-05-01
updated: 2026-05-01
---

# Phase 23 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Source: 23-RESEARCH.md §Validation Architecture. Per-task verification map populated by gsd-planner; nyquist_compliant flipped true once every task binds to an `<automated>` command or a Wave 0 dependency.

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

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 23-01-T1 | 23-01 | 0 | BACKTEST-01 | T-23-pyarrow | pyarrow pinned + binary wheel only | install | `pip show pyarrow \| grep -E '^Version: 24\.0\.0'` | ❌ W0 | ⬜ pending |
| 23-01-T2 | 23-01 | 0 | BACKTEST-01..04 | — | backtest/ skeleton importable | unit | `python -c "import backtest; from backtest import cli, simulator, metrics, render, data_fetcher; print('ok')"` | ❌ W0 | ⬜ pending |
| 23-01-T3 | 23-01 | 0 | BACKTEST-03..04 | — | web/routes/backtest.py registered in web/app.py | unit | `python -c "from web.app import create_app; app=create_app(); paths={r.path for r in app.routes}; assert '/backtest' in paths and '/backtest/run' in paths"` | ❌ W0 | ⬜ pending |
| 23-01-T4 | 23-01 | 0 | BACKTEST-01..03 (D-09 hex) | — | AST guard extends to backtest/{simulator,metrics,render}.py + bans pyarrow | unit | `pytest tests/test_signal_engine.py::TestDeterminism -x -q` | ✅ (extended) | ⬜ pending |
| 23-01-T5 | 23-01 | 0 | BACKTEST-02..03 | — | golden_report.json fixture validates D-05 schema | unit | `python -c "import json,pathlib; r=json.loads(pathlib.Path('tests/fixtures/backtest/golden_report.json').read_text()); assert set(r) == {'metadata','metrics','equity_curve','trades'}"` | ❌ W0 | ⬜ pending |
| 23-01-T6 | 23-01 | 0 | BACKTEST-01..04 | — | 6 test file skeletons collectible | unit | `pytest tests/test_backtest_*.py tests/test_web_backtest.py --collect-only -q` | ❌ W0 | ⬜ pending |
| 23-02-T1 | 23-02 | 1 | BACKTEST-01 | T-23-cache-tamper | data_fetcher cache + bail logic | unit | `python -c "from backtest.data_fetcher import fetch_ohlcv, ShortFrameError, DataFetchError, _cache_path; from pathlib import Path; assert _cache_path('^AXJO','2021-05-01','2026-05-01',Path('/tmp')).name == '^AXJO-2021-05-01-2026-05-01.parquet'"` | depends on 23-01-T2 | ⬜ pending |
| 23-02-T2 | 23-02 | 1 | BACKTEST-01 | T-23-cache-tamper | parquet schema-typed binary cache; cache hit/miss/refresh/short-bail | unit | `pytest tests/test_backtest_data_fetcher.py -x` | depends on 23-01-T6 | ⬜ pending |
| 23-03-T1 | 23-03 | 1 | BACKTEST-01 | — | simulator reuses signal_engine + sizing_engine; cost reconstruction | unit | `python -c "from backtest.simulator import simulate, SimResult; import dataclasses; assert dataclasses.is_dataclass(SimResult); fields={f.name for f in dataclasses.fields(SimResult)}; assert fields == {'trades','equity_curve','dates','final_account'}"` | depends on 23-01-T2 | ⬜ pending |
| 23-03-T2 | 23-03 | 1 | BACKTEST-01 | — | deterministic replay + cost-model reconstruction + exit reasons + NaN safety | unit | `pytest tests/test_backtest_simulator.py -x` | depends on 23-01-T6 | ⬜ pending |
| 23-04-T1 | 23-04 | 1 | BACKTEST-02 | — | metrics formulas + dual sharpe + pass criterion strict | unit | `python -c "from backtest.metrics import compute_metrics; m=compute_metrics([10000.0,22745.0],[]); assert m['cumulative_return_pct']>100.0; assert m['pass'] is True"` | depends on 23-01-T2 | ⬜ pending |
| 23-04-T2 | 23-04 | 1 | BACKTEST-02 | — | formulas + edge cases (zero/all-loss/all-win/sharpe-annualized/dd-cummax) | unit | `pytest tests/test_backtest_metrics.py -x` | depends on 23-01-T6 | ⬜ pending |
| 23-05-T1 | 23-05 | 2 | BACKTEST-03 | T-23-cdn | render_report has 3 tab containers + Chart.js SRI + override form | unit | `python -c "import json,pathlib; from backtest.render import render_report; r=json.loads(pathlib.Path('tests/fixtures/backtest/golden_report.json').read_text()); html=render_report(r); assert 'equityChartCombined' in html and 'sha384-MH1axGwz' in html"` | depends on 23-01-T2 + 23-01-T5 | ⬜ pending |
| 23-05-T2 | 23-05 | 2 | BACKTEST-03 | T-23-cdn | render structure + Chart.js SRI + JSON-injection defence + empty-state | unit | `pytest tests/test_backtest_render.py -x` | depends on 23-01-T6 + 23-04-T2 | ⬜ pending |
| 23-06-T1 | 23-06 | 2 | BACKTEST-04 | — | argparse surface + JSON write + STRATEGY_VERSION fresh access | unit | `python -c "from backtest.cli import main, run_backtest, _build_parser, RunArgs; ns=_build_parser().parse_args([]); assert ns.years == 5 and ns.initial_account_aud == 10000.0"` | depends on 23-02 + 23-03 + 23-04 | ⬜ pending |
| 23-06-T2 | 23-06 | 2 | BACKTEST-02..04 | — | D-05 schema serialised + exit-code mapping + log-line format + G-45 fresh access | unit | `pytest tests/test_backtest_cli.py -x` | depends on 23-01-T6 + 23-06-T1 | ⬜ pending |
| 23-07-T1 | 23-07 | 2 | BACKTEST-03..04 | T-23-traversal, T-23-input, T-23-auth | path-traversal defence + 303 redirect + Phase 16.1 auth gate | unit | `python -c "from web.routes.backtest import _resolve_safe_backtest_path; from pathlib import Path; import tempfile; tmp=Path(tempfile.mkdtemp()); (tmp/'good.json').write_text('{}'); assert _resolve_safe_backtest_path('good.json', tmp).name == 'good.json'"` | depends on 23-01-T3 + 23-05 + 23-06 | ⬜ pending |
| 23-07-T2 | 23-07 | 2 | BACKTEST-03..04 | T-23-traversal, T-23-input, T-23-auth | full route surface incl. ?run= + POST + cookie auth | integration | `pytest tests/test_web_backtest.py -x` | depends on 23-01-T6 + 23-05-T2 + 23-06-T2 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

### Coverage by Threat Reference

| Threat Ref | Tasks |
|------------|-------|
| T-23-pyarrow | 23-01-T1 |
| T-23-cache-tamper | 23-02-T1, 23-02-T2 |
| T-23-cdn | 23-05-T1, 23-05-T2 |
| T-23-traversal | 23-07-T1, 23-07-T2 |
| T-23-input | 23-07-T2 |
| T-23-auth | 23-07-T2 |

### Coverage by Requirement

| Requirement | Tasks |
|-------------|-------|
| BACKTEST-01 | 23-02-T1, 23-02-T2, 23-03-T1, 23-03-T2 |
| BACKTEST-02 | 23-04-T1, 23-04-T2, 23-06-T2 |
| BACKTEST-03 | 23-05-T1, 23-05-T2, 23-07-T1, 23-07-T2 |
| BACKTEST-04 | 23-06-T1, 23-06-T2, 23-07-T1, 23-07-T2 |
| D-09 (hex) | 23-01-T4 |

---

## Wave 0 Requirements (BLOCKING for Wave 1+)

- [ ] `tests/test_backtest_data_fetcher.py` — BACKTEST-01 data layer skeleton (filled by Plan 02)
- [ ] `tests/test_backtest_simulator.py` — BACKTEST-01 simulator skeleton (filled by Plan 03)
- [ ] `tests/test_backtest_metrics.py` — BACKTEST-02 metrics skeleton (filled by Plan 04)
- [ ] `tests/test_backtest_render.py` — BACKTEST-03 HTML skeleton (filled by Plan 05)
- [ ] `tests/test_backtest_cli.py` — BACKTEST-04 CLI skeleton (filled by Plan 06)
- [ ] `tests/test_web_backtest.py` — BACKTEST-03/04 routes skeleton (filled by Plan 07)
- [ ] `tests/fixtures/backtest/golden_report.json` — hand-authored reference report (Plan 01 Task 5)
- [ ] Extend `tests/test_signal_engine.py:480` AST guard with `BACKTEST_PATHS_PURE` (Plan 01 Task 4)
- [ ] Add `pyarrow==24.0.0` to `requirements.txt` (Plan 01 Task 1)
- [ ] Create `backtest/` package skeleton (Plan 01 Task 2)
- [ ] Create `web/routes/backtest.py` skeleton + mount in `web/app.py` (Plan 01 Task 3)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Three-tab visual layout renders correctly on mobile (≤375px) | BACKTEST-03 / D-04 | CSS responsiveness across viewports | After Wave 2 merge: open `/backtest` in Chrome devtools mobile emulation (iPhone SE), verify each tab is reachable and metrics row is readable without horizontal scroll |
| Chart.js equity curves render visually correct (line drawn, axes labelled) | BACKTEST-03 / D-04 | Chart.js draws to canvas — DOM tests confirm `<canvas>` exists but not pixel output | After Wave 2 merge: trigger a real backtest run, open `/backtest`, confirm three tabs each draw a line chart with non-trivial range |
| Operator override form: spinner appears during 30-60s simulation; submit button disables | BACKTEST-03 / D-14 | Browser-side UX (CSS animation + form submit handler) | After Wave 2 merge: open `/backtest`, change initial_account to 5000, click [Run with overrides], confirm spinner is visible and submit is disabled until redirect |
| 5y × 2 instruments runs <60s on droplet (1 vCPU) | D-18 / SC-1 | Performance budget on production hardware | Post-deploy: `time python -m backtest --years 5` on the droplet via SSH; assert wall time <60s |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies — every row in the Per-Task Verification Map binds to an executable command or to a Wave 0 task
- [x] Sampling continuity: no 3 consecutive tasks without automated verify — Wave 0 + Wave 1 + Wave 2 each have at least one runnable command per task
- [x] Wave 0 covers all MISSING references — Plan 01 Tasks 1-6 produce every dependency the later waves cite
- [x] No watch-mode flags — every command is one-shot pytest or python -c
- [x] Feedback latency < 30s (quick) / < 90s (full) — confirmed by RESEARCH §Validation Architecture
- [x] `nyquist_compliant: true` set in frontmatter — flipped 2026-05-01 once Plans 01..07 finalized

**Approval:** approved (2026-05-01, gsd-planner)
