---
phase: 04
slug: end-to-end-skeleton-fetch-orchestrator-cli
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-21
---

# Phase 04 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

Source: `04-RESEARCH.md` §Validation Architecture (runtime-verified against the installed `.venv/`).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.3.3 (+ pytest-freezer 0.4.9 Wave 0 add) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (`testpaths=['tests']`, `addopts='-ra --strict-markers'`) |
| **Quick run command** | `.venv/bin/pytest tests/test_data_fetcher.py tests/test_main.py -x` |
| **Full suite command** | `.venv/bin/pytest tests/ -x` |
| **Phase-gate command** | `.venv/bin/pytest tests/ -x && .venv/bin/ruff check .` |
| **Estimated runtime** | ~3 seconds (current 294 tests run in ~0.85s; Phase 4 adds ~40 tests → ~1.2s total) |

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/pytest tests/test_data_fetcher.py tests/test_main.py -x` (fast; new-phase tests only).
- **After every plan wave:** Run `.venv/bin/pytest tests/ -x` (full suite — Phase 1/2/3 regression).
- **Before `/gsd-verify-work`:** Full suite green + `.venv/bin/ruff check .` clean + `python tests/regenerate_goldens.py` produces zero diff against committed goldens (Phase 1 determinism snapshot preserved).
- **Max feedback latency:** ~3 seconds (full suite).

---

## Per-Task Verification Map

Each row below corresponds to a locked requirement ID from ROADMAP.md and names an authoritative test method. Threat Ref column is `—` because Phase 4 has no security-boundary work (no external user input, no auth, no crypto — all I/O is to yfinance and local filesystem which are trusted boundaries per PROJECT.md's "single-operator tool" constraint).

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 04-02-T1 | 02 | 1 | DATA-01 | — | N/A | integration (recorded fixture) | `.venv/bin/pytest tests/test_data_fetcher.py::TestFetch::test_happy_path_axjo_returns_400_bars -x` | ❌ W0 | ⬜ pending |
| 04-02-T1 | 02 | 1 | DATA-02 | — | N/A | integration (recorded fixture) | `.venv/bin/pytest tests/test_data_fetcher.py::TestFetch::test_happy_path_audusd_returns_400_bars -x` | ❌ W0 | ⬜ pending |
| 04-02-T2 | 02 | 1 | DATA-03 | — | N/A | unit (monkeypatch) | `.venv/bin/pytest tests/test_data_fetcher.py::TestFetch::test_retry_on_rate_limit_then_success -x` | ❌ W1 | ⬜ pending |
| 04-03-T2 | 03 | 2 | DATA-04 | — | N/A | unit (hand-built DataFrame) | `.venv/bin/pytest tests/test_main.py::TestOrchestrator::test_short_frame_raises_and_no_state_written -x` | ❌ W2 | ⬜ pending |
| 04-04-T2 | 04 | 3 | DATA-05 | — | N/A | unit (frozen clock + hand-built DataFrame) | `.venv/bin/pytest tests/test_main.py::TestOrchestrator::test_stale_bar_appends_warning -x` | ❌ W3 | ⬜ pending |
| 04-03-T2 | 03 | 2 | DATA-06 | — | N/A | unit (caplog + frozen clock) | `.venv/bin/pytest tests/test_main.py::TestOrchestrator::test_signal_as_of_and_run_date_logged_separately -x` | ❌ W2 | ⬜ pending |
| 04-04-T1 | 04 | 3 | CLI-01 | — | `--test` leaves `state.json` untouched (structural read-only proof) | integration (mtime assertion) | `.venv/bin/pytest tests/test_main.py::TestCLI::test_test_flag_leaves_state_json_mtime_unchanged -x` | ❌ W3 | ⬜ pending |
| 04-04-T1 | 04 | 3 | CLI-02 | — | `--reset` never writes without explicit operator confirmation | unit (monkeypatch input) | `.venv/bin/pytest tests/test_main.py::TestCLI::test_reset_with_confirmation_writes_fresh_state -x` | ❌ W3 | ⬜ pending |
| 04-04-T1 | 04 | 3 | CLI-03 | — | N/A (Phase 4 stub; Phase 6 wires) | unit (caplog) | `.venv/bin/pytest tests/test_main.py::TestCLI::test_force_email_logs_stub_and_exits_zero -x` | ❌ W3 | ⬜ pending |
| 04-03-T2 | 03 | 2 | CLI-04 | — | N/A | unit (smoke) | `.venv/bin/pytest tests/test_main.py::TestCLI::test_once_flag_runs_single_check -x` | ❌ W2 | ⬜ pending |
| 04-03-T2 | 03 | 2 | CLI-05 | — | N/A | unit (smoke) | `.venv/bin/pytest tests/test_main.py::TestCLI::test_default_mode_runs_once_and_logs_schedule_stub -x` | ❌ W2 | ⬜ pending |
| 04-04-T2 | 04 | 3 | ERR-01 | — | Fetch failure never corrupts `state.json` (no partial writes) | unit (monkeypatch) | `.venv/bin/pytest tests/test_main.py::TestOrchestrator::test_fetch_failure_exits_nonzero_no_save_state -x` | ❌ W3 | ⬜ pending |
| 04-03-T2 | 03 | 2 | ERR-06 | — | N/A | unit (caplog + regex) | `.venv/bin/pytest tests/test_main.py::TestOrchestrator::test_log_format_matches_d14_contract -x` | ❌ W2 | ⬜ pending |

*Status legend: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*
*W0/W1/W2/W3 = the wave in which the test file first comes into existence (Wave 0 scaffold vs Wave 1/2/3 implementation).*

Each plan's acceptance criteria MUST reference the test name listed above and the exact pytest command MUST be one of the automated commands quoted here — no paraphrase, no renaming. The checker enforces this at planning time; the executor enforces it at commit time.

---

## Wave 0 Requirements (files created by the scaffold plan 04-01)

- [ ] `tests/test_data_fetcher.py` — class skeletons: `TestFetch` (6 tests), `TestColumnShape` (1 test) — stubs for DATA-01/02/03.
- [ ] `tests/test_main.py` — class skeletons: `TestCLI` (5 tests for CLI-01..05), `TestOrchestrator` (8 tests for DATA-04/05/06 + ERR-01/06 + D-08 upgrade + D-12 translator), `TestLoggerConfig` (1 test asserting `logging.basicConfig(force=True)` applied).
- [ ] `tests/regenerate_fetch_fixtures.py` — offline regeneration script (mirrors `tests/regenerate_goldens.py` style) committed as scaffolded helper that prints usage + calls live yfinance, writes `tests/fixtures/fetch/{symbol_slug}_400d.json`. Script NEVER runs in CI.
- [ ] `tests/fixtures/fetch/axjo_400d.json` — committed recorded fixture (pandas `df.to_json(orient='split', date_format='iso')` round-trip lossless).
- [ ] `tests/fixtures/fetch/audusd_400d.json` — committed recorded fixture (same format).
- [ ] `data_fetcher.py` — module scaffold with `DataFetchError`, `ShortFrameError`, stub `fetch_ohlcv(...) -> pd.DataFrame`.
- [ ] `main.py` — module scaffold with `run_daily_check(args)` stub + argparse skeleton + `_closed_trade_to_record(...)` stub + `_compute_run_date()` stub.
- [ ] `tests/test_signal_engine.py::TestDeterminism` — AST blocklist extension: `DATA_FETCHER_PATH` + `FORBIDDEN_MODULES_DATA_FETCHER = frozenset({'signal_engine', 'sizing_engine', 'state_manager', 'notifier', 'dashboard', 'main', 'numpy'})`; and a `MAIN_PATH` + `FORBIDDEN_MODULES_MAIN = frozenset({'numpy'})` allow-list stance (main is the ONLY module allowed to import both sides of the hex).
- [ ] `requirements.txt` — add `pytest-freezer==0.4.9` (pinned per Phase 1 D-15 expectation).
- [ ] `pyproject.toml` — confirm `[tool.ruff]` includes `data_fetcher.py`, `main.py`, `tests/test_data_fetcher.py`, `tests/test_main.py`, `tests/regenerate_fetch_fixtures.py` in line-length / select/ignore scope (inherits from existing config; spot-check only).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `tests/regenerate_fetch_fixtures.py` correctness | DATA-01/02 | Script makes real network calls to yfinance; cannot run in CI or in automated tests without bypassing the network-isolation contract. | Run locally: `.venv/bin/python tests/regenerate_fetch_fixtures.py`. Expect `tests/fixtures/fetch/axjo_400d.json` and `tests/fixtures/fetch/audusd_400d.json` to be re-written. Inspect `git diff` — column names must be `['Open','High','Low','Close','Volume']` and row count MUST be ≥ 400. Commit only if the diff reflects a legitimate data refresh (new bars appended, no historical bars changed). |

All other phase behaviors have automated verification via the table above.

---

## Validation Sign-Off

- [ ] All 13 requirement IDs have a named automated test in the Per-Task Verification Map.
- [ ] Sampling continuity: every plan task either has an automated verify OR is a scaffold (Wave 0 stubs) with its verify landing in a later wave — no 3 consecutive tasks without automated verify.
- [ ] Wave 0 creates all test skeletons so Waves 1/2/3 can fill bodies without fighting missing-import issues.
- [ ] No watch-mode flags (pytest-watch is NOT in requirements; sample command is one-shot).
- [ ] Feedback latency < 3s for quick-run; < 5s for full suite.
- [ ] `nyquist_compliant: true` flipped in frontmatter after Wave 0 commits land.

**Approval:** pending (will be set to `approved YYYY-MM-DD` after Wave 0 merges and this file is re-audited).
