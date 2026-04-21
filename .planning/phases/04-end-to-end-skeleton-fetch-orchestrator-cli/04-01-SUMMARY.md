---
phase: 04-end-to-end-skeleton-fetch-orchestrator-cli
plan: 01
subsystem: infra
tags: [python, yfinance, argparse, scaffold, ast-blocklist, pytest-freezer, hex-lite]

requires:
  - phase: 01-signal-engine-core-indicators-vote
    provides: signal_engine public API (compute_indicators, get_signal, get_latest_indicators, LONG/SHORT/FLAT) — referenced by main.py imports stub block
  - phase: 02-signal-engine-sizing-exits-pyramiding
    provides: sizing_engine ClosedTrade dataclass + step() orchestrator — referenced by main.py import of ClosedTrade
  - phase: 03-state-persistence-with-recovery
    provides: state_manager public API (load_state, save_state, record_trade, etc.) — referenced by main.py + test_main.py imports
provides:
  - data_fetcher.py skeleton (DataFetchError, ShortFrameError, fetch_ohlcv stub) — fetch I/O hex module surface frozen for Wave 1
  - main.py skeleton (argparse 4-flag parser, _validate_flag_combo full body, AWST + SYMBOL_MAP constants, logging.basicConfig(force=True) bootstrap, stubs for _compute_run_date, _closed_trade_to_record, run_daily_check)
  - tests/test_data_fetcher.py + tests/test_main.py class skeletons (TestFetch, TestColumnShape, TestCLI, TestOrchestrator, TestLoggerConfig)
  - tests/regenerate_fetch_fixtures.py — offline-only yfinance regenerator with defensive ≥400-bar assert
  - tests/fixtures/fetch/axjo_400d.json (599 bars) + audusd_400d.json (595 bars) — committed recorded fixtures
  - Extended AST blocklist (FORBIDDEN_MODULES_DATA_FETCHER + C-5-tightened FORBIDDEN_MODULES_MAIN) + 2-space-indent guard covering 4 new paths
  - pytest-freezer==0.4.9 pin in requirements.txt (installed + plugin registered)
affects: [04-02, 04-03, 04-04, 05, 06, 07]

tech-stack:
  added: [pytest-freezer==0.4.9, freezegun (transitive)]
  patterns: [offline-fixture-regeneration via orient='split', hex-lite AST blocklist with per-module frozenset, logging.basicConfig(force=True) for pytest-safe logging bootstrap]

key-files:
  created:
    - data_fetcher.py
    - main.py
    - tests/test_data_fetcher.py
    - tests/test_main.py
    - tests/regenerate_fetch_fixtures.py
    - tests/fixtures/fetch/axjo_400d.json
    - tests/fixtures/fetch/audusd_400d.json
    - .planning/phases/04-end-to-end-skeleton-fetch-orchestrator-cli/04-01-SUMMARY.md
  modified:
    - tests/test_signal_engine.py (AST blocklist + 2-space indent guard extension)
    - requirements.txt (pytest-freezer==0.4.9 pin)

key-decisions:
  - "Rule 3 deviation: regenerator uses period='600d' not '400d' — yfinance treats period='Nd' as calendar days, so period='400d' returns ~399/395 trading bars. Over-fetching guarantees ≥400 bars without touching production fetch_ohlcv (Wave 1 keeps days=400 default)."
  - "C-5 revision applied: FORBIDDEN_MODULES_MAIN tightened from {numpy} to {numpy, yfinance, requests, pandas}. main.py is the orchestrator — it imports sibling hexes, never transport/data libs."
  - "C-10 revision applied via pytest -VV (not --version): pytest 8.3.3's --version does not list plugins; -VV is the correct CLI. Plugin registration confirmed via both -VV and --trace-config."
  - "G-3 revision applied: import time present in main.py's Wave 0 imports block (noqa F401 reason: Wave 2 perf-counter measurement)."
  - "C-9 follow-up note landed in regenerator module header: post-Wave 1 the script should import data_fetcher.fetch_ohlcv instead of calling yf.Ticker directly; owned by 04-02-PLAN.md Task 2."
  - "Task 4 (C-1) verified as no-op: .planning/REQUIREMENTS.md + .planning/ROADMAP.md were already amended in commit 8227235 (reviews-revision pass). No new commit for Task 4; verification checklist passes via case-insensitive grep (docs use capitalised 'Amended 2026-04-22' markers)."

patterns-established:
  - "Pattern: F401-noqa reason comments on every stub import ('# noqa: F401 — used in Wave N ...') — rules-compliant and documents executor intent for future waves."
  - "Pattern: Per-module FORBIDDEN_MODULES frozenset in tests/test_signal_engine.py::TestDeterminism — each hex module has a DIFFERENT legitimate allow-list; signal_engine's pure-math block vs state_manager's I/O block vs data_fetcher's fetch block vs main's orchestration block are explicit and separate."
  - "Pattern: Offline fixture format is df.to_json(orient='split', date_format='iso') — lossless round-trip for tz-aware DatetimeIndex (CSV drops tz, parquet adds binary dep)."
  - "Pattern: NotImplementedError('Wave N implements ... — see MM-NN-PLAN.md') as the sole deferred-scope signal; TODO/FIXME/HACK markers are FORBIDDEN."

requirements-completed: []  # Wave 0 scaffolds only; no requirements close here.

duration: 11min
completed: 2026-04-22
---

# Phase 04 Plan 01: Wave 0 Scaffold Summary

**Phase 4 Wave 0 scaffold landed: 11 files created/modified, 3 atomic task commits, 296 tests green, AST blocklist symmetric across signal_engine/state_manager/data_fetcher/main. Waves 1/2/3 now unblocked.**

## Performance

- **Duration:** 11 min
- **Started:** 2026-04-22T04:23:34+08:00 (post 8227235 reviews-revision)
- **Completed:** 2026-04-22T04:34:15+08:00 (Task 3 commit)
- **Tasks:** 3 executed + 1 verified-no-op (Task 4)
- **Files modified:** 11 total — 8 created + 2 modified + 1 summary (this file)

## Accomplishments

- **Fetch hex surface frozen.** `data_fetcher.py` exposes `DataFetchError`, `ShortFrameError`, and `fetch_ohlcv(...)` with the full Wave 1 docstring; body is a single `NotImplementedError` that references 04-02-PLAN.md.
- **Orchestrator surface frozen.** `main.py` argparse parser accepts all four CLI-01..CLI-05 flags, `_validate_flag_combo` enforces D-05 exclusivity as a full body (not a stub), `AWST = ZoneInfo('Australia/Perth')` + `SYMBOL_MAP` constants are module-level, and `main()` wires `logging.basicConfig(force=True)` before dispatching (Pitfall 4). Stubs for `_compute_run_date`, `_closed_trade_to_record`, `run_daily_check` carry their full Wave 2 docstrings including the gross_pnl CRITICAL PITFALL block (Pitfall 8) and the D-08 signals-dict upgrade branch (Pitfall 7).
- **Recorded fixtures committed.** `axjo_400d.json` (599 bars) and `audusd_400d.json` (595 bars) were generated from live yfinance, round-trip losslessly via `pd.read_json(orient='split')`, and preserve the exchange-local tz-aware DatetimeIndex (D-13).
- **AST blocklist extended symmetrically.** Two new parametrized methods (`test_data_fetcher_no_forbidden_imports`, `test_main_no_forbidden_imports`) plus two new frozensets (`FORBIDDEN_MODULES_DATA_FETCHER`, `FORBIDDEN_MODULES_MAIN` with C-5 tightening) lock the hex boundary for the new modules. The 2-space indent guard grew from 7 to 11 covered paths.
- **pytest-freezer pinned and registered.** `pytest-freezer==0.4.9` installed cleanly; plugin confirmed active via `pytest -VV` and `pytest --trace-config`; live fixture smoke-test in a throwaway file passes.
- **Upstream docs verified.** `.planning/REQUIREMENTS.md` + `.planning/ROADMAP.md` amendments (C-1) were already present from the 8227235 reviews-revision pass; Task 4 is a verified no-op.
- **Full suite green at 296 tests** (Phase 1/2/3 = 294 previously + 2 new parametrized AST methods). Ruff clean across the whole repo. Zero TODO/FIXME/HACK markers in new or modified files.

## Task Commits

Each task was committed atomically on branch `worktree-agent-a1b81859` (worktree-isolated):

1. **Task 1: Scaffold data_fetcher.py + main.py + pin pytest-freezer** — `fbd7a9d` (feat)
2. **Task 2: Scaffold test files + offline fixture regenerator + commit recorded JSON fixtures** — `2c4947a` (test)
3. **Task 3: Extend AST blocklist + 2-space indent guard; tighten FORBIDDEN_MODULES_MAIN per C-5** — `1caa70b` (test)
4. **Task 4: Upstream-doc amendments (C-1)** — **verified no-op** (amendments already present in `8227235`; see Deviations §1 below)

_No plan-metadata commit needed for this wave — the orchestrator owns STATE.md updates._

## Files Created/Modified

- `data_fetcher.py` — fetch I/O hex skeleton: docstring + imports + `DataFetchError` + `ShortFrameError` + `fetch_ohlcv` NotImplementedError stub. Imports `yfinance as yf`, `pandas as pd`, `requests.exceptions`, `YFRateLimitError`, `logging`, `time` — all allowed per `FORBIDDEN_MODULES_DATA_FETCHER`.
- `main.py` — orchestrator skeleton: docstring naming hex-lite boundary + C-5 tightening + D-13 run_date/signal_as_of separation; full-body `_build_parser` + `_validate_flag_combo` + `main` (bootstraps logging then dispatches); `NotImplementedError` stubs for `_compute_run_date`, `_closed_trade_to_record`, `run_daily_check`.
- `tests/test_data_fetcher.py` — `TestFetch` + `TestColumnShape` class skeletons + `_load_recorded_fixture` helper.
- `tests/test_main.py` — `TestCLI` + `TestOrchestrator` + `TestLoggerConfig` class skeletons.
- `tests/regenerate_fetch_fixtures.py` — offline yfinance→JSON fixture regenerator with defensive ≥400-bar assert + C-9 follow-up note (Wave 1 should switch to `data_fetcher.fetch_ohlcv`).
- `tests/fixtures/fetch/axjo_400d.json` — 599 bars of `^AXJO` daily OHLCV.
- `tests/fixtures/fetch/audusd_400d.json` — 595 bars of `AUDUSD=X` daily OHLCV.
- `tests/test_signal_engine.py` — MODIFIED: added 4 Phase 4 path constants, 2 new frozensets (FORBIDDEN_MODULES_DATA_FETCHER, FORBIDDEN_MODULES_MAIN per C-5), 2 new parametrized test methods, 4 new entries in `test_no_four_space_indent.covered_paths`.
- `requirements.txt` — MODIFIED: added `pytest-freezer==0.4.9` in alphabetical order.

## Live-Network Fixture Regeneration Caveat

Task 2 required a live yfinance fetch to generate the committed JSON fixtures. The probe `yfinance.Ticker('^AXJO').history(period='5d')` returned 4 bars (confirming connectivity) before running the regenerator. Both symbols delivered real data:

```
[regen] wrote axjo_400d.json (599 bars)
[regen] wrote audusd_400d.json (595 bars)
```

Neither symbol returned an empty frame (Pitfall 2 guard — `RuntimeError` on `< 400 bars` — did not fire). Fixtures committed as-is; no placeholder or empty JSON stubs written. Re-running the regenerator in the future will deterministically rewrite them with whatever yfinance currently serves for the preceding 600 calendar days.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] Task 2 regenerator `period='400d'` → `period='600d'`**
- **Found during:** Task 2 initial regenerator run.
- **Issue:** Plan text specified `period='400d'` in both the regenerator template and the `len(df) >= 400` assertion. Live yfinance returned 399 bars for `^AXJO` (`period='400d'`, `interval='1d'`) and 395 bars for `AUDUSD=X` — yfinance interprets `period='Nd'` as calendar days and daily bars exclude weekends/holidays, so `400d ≠ 400 bars`. The `len(df) >= 400` assertion fired and aborted the Task 2 regenerator on the first run, blocking fixture generation.
- **Fix:** Changed `period='400d'` → `period='600d'` in `tests/regenerate_fetch_fixtures.py::fetch_one` with an explicit docstring Note explaining the Rule 3 deviation. Production `data_fetcher.fetch_ohlcv(days=400)` (Wave 1) is untouched — it keeps the plan-specified `period='400d'` default and relies on DATA-04's `len < 300 → ShortFrameError` to catch truly short frames. The fixture file names (`axjo_400d.json`, `audusd_400d.json`) were NOT renamed — they match the plan's artifact list exactly. Over-fetching 599/595 bars is strictly more data for Wave 1 happy-path tests.
- **Files modified:** `tests/regenerate_fetch_fixtures.py`.
- **Commit:** `2c4947a`.

**2. [Rule 1 — Bug] Task 1 C-10 verify command `pytest --version` → `pytest -VV`**
- **Found during:** Task 1 verification.
- **Issue:** Plan specified `.venv/bin/pytest --version 2>&1 | grep -q freezer` to verify pytest-freezer plugin registration. Pytest 8.3.3's `--version` emits only `pytest 8.3.3` — no plugin list. The check would fail despite the plugin being installed and registered.
- **Fix:** Used `.venv/bin/pytest -VV 2>&1 | grep -q freezer` (which lists "registered third-party plugins") to satisfy the spirit of C-10's "verify via CLI, not direct import" guidance. Also cross-confirmed registration via `pytest --trace-config` (shows the plugin + fixture registered) and a throwaway `test_freezer_fixture_exists` that exercises `freezer.move_to(...)` and passes. Plan-text assumption that `pytest --version` lists plugins is incorrect for pytest 8.3.x — documenting for future plan authors.
- **Files modified:** None (verification-only deviation; plan action block unchanged).
- **Commit:** Documented in Task 1's commit message `fbd7a9d` and here.

**3. [No-op] Task 4 upstream docs already amended in `8227235`**
- **Found during:** Task 4 pre-flight verification per the orchestrator's `<upstream_docs_note>`.
- **Issue:** The orchestrator flagged that `.planning/REQUIREMENTS.md` + `.planning/ROADMAP.md` had ALREADY been amended in commit 8227235 (the reviews-revision pass). Running the plan's Task 4 action block again would have produced a no-op commit or, worse, duplicate amendment markers.
- **Fix:** Verified all six grep checks from the plan's `<verify>` block pass (modulo case-insensitivity — the markers read `**Amended:** 2026-04-22` with capital A; the plan's literal `grep -q "amended 2026-04-22"` doesn't match, but `grep -qi` does, and the semantic content is present). Skipped the Task 4 commit entirely per the orchestrator's guidance. No duplicate markers added.
- **Files modified:** None.
- **Commit:** None (intentional no-op).

### Authentication Gates

None. Task 2's yfinance call is unauthenticated public data; Resend (Phase 6) and GitHub Actions secrets (Phase 7) are out of scope.

### Out-of-Scope Discoveries

None. The `.venv` symlink at the worktree root is a session-level plumbing artefact for running `.venv/bin/python` commands and matches the main repo's `.venv` directory — it is NOT a new file to track. `.gitignore` already excludes `.venv/`.

## Verification Evidence

| Gate | Command | Result |
| --- | --- | --- |
| Full pytest suite | `.venv/bin/pytest tests/ -x` | **296 passed** (was 294; +2 new parametrized AST methods) |
| Ruff clean | `.venv/bin/ruff check .` | **All checks passed!** |
| Skeleton importable | `python -c "from data_fetcher import DataFetchError, ShortFrameError, fetch_ohlcv; from main import main, run_daily_check, _build_parser, _validate_flag_combo, _closed_trade_to_record, _compute_run_date, AWST, SYMBOL_MAP"` | `skeleton ok` |
| Fixtures round-trip | `pd.read_json(..., orient='split')` len ≥ 400 + exact columns | `fixtures ok: axjo=599, audusd=595` |
| TODO/FIXME/HACK | `grep -rn 'TODO\|FIXME\|HACK' <new files>` | zero matches |
| Pitfall 4 | `grep -c 'force=True' main.py` | 4 matches (main body + docstring cross-refs) |
| G-3 | `grep -c '^import time' main.py` | 1 |
| pytest-freezer pin | `grep -c 'pytest-freezer==0.4.9' requirements.txt` | 1 |
| C-10 plugin | `.venv/bin/pytest -VV 2>&1 \| grep -q freezer` | plugin registered |
| C-5 frozenset | `python -c "from tests.test_signal_engine import FORBIDDEN_MODULES_MAIN; assert {'numpy','yfinance','requests','pandas'}.issubset(FORBIDDEN_MODULES_MAIN)"` | subset check passes |
| C-1 amendments | `grep -qi "amended 2026-04-22" <both upstream docs>` + substantive greps | all six semantic checks pass |

## Revision Markers Applied

- **C-1** — Upstream REQUIREMENTS.md + ROADMAP.md amendments verified in place (no-op; already in 8227235).
- **C-5** — `FORBIDDEN_MODULES_MAIN = {numpy, yfinance, requests, pandas}` (all four blocked; previous version blocked only numpy).
- **C-9 follow-up note** — Header comment in `tests/regenerate_fetch_fixtures.py` documents the Wave 1 switchover to `data_fetcher.fetch_ohlcv`.
- **C-10** — pytest-freezer verification via CLI (`pytest -VV`), not direct `from pytest_freezer import freezer`.
- **G-3** — `import time` present in `main.py`'s Wave 0 imports block with F401-noqa reason comment for Wave 2 perf-counter use.

## Threat Flags

No new security-relevant surface was introduced in this wave. The yfinance fetch is public-data HTTPS owned by the `yfinance` library (not hand-rolled), `requests.exceptions` is imported only for narrow-catch tuple membership, and no env-var reads or Resend calls exist yet.

## Self-Check: PASSED

All 8 created files present on disk, both modified files in tracked status, all 3 task commit hashes resolvable via `git log --oneline --all`:

- Created: `data_fetcher.py`, `main.py`, `tests/test_data_fetcher.py`, `tests/test_main.py`, `tests/regenerate_fetch_fixtures.py`, `tests/fixtures/fetch/axjo_400d.json`, `tests/fixtures/fetch/audusd_400d.json`, this SUMMARY.
- Modified: `tests/test_signal_engine.py`, `requirements.txt`.
- Commits: `fbd7a9d` (Task 1), `2c4947a` (Task 2), `1caa70b` (Task 3).

---

**Wave 0 green — Waves 1/2/3 unblocked. 296 / 296 tests pass.**
