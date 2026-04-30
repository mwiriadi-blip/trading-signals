# Phase 23: 5-Year Backtest Validation Gate — Pattern Map

**Mapped:** 2026-05-01
**Files analyzed:** 19 (16 new files + 3 modifications)
**Analogs found:** 14 / 19 with strong analogs; 5 design-from-scratch (flagged below)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `backtest/__init__.py` | constants module | n/a | `system_params.py` (constants) | role-match |
| `backtest/data_fetcher.py` | I/O adapter | request-response (cache+fetch) | `data_fetcher.py` | exact |
| `backtest/simulator.py` | pure-math engine | batch transform | `pnl_engine.py`, `alert_engine.py` | role-match |
| `backtest/metrics.py` | pure-math engine | batch transform | `pnl_engine.py`, `alert_engine.py` | exact |
| `backtest/render.py` | pure render adapter | transform | `dashboard.py` `_render_*` family | role-match (closer than pure-math because needs `html`+`json`) |
| `backtest/cli.py` | CLI adapter | batch | `main.py` `_build_parser` + `main()` | role-match |
| `backtest/__main__.py` | dispatch shim | n/a | none in repo | DESIGN-FROM-SCRATCH |
| `web/routes/backtest.py` | web route adapter | request-response + form | `web/routes/paper_trades.py` | exact |
| `web/app.py` (mount) | web factory | n/a | `web/app.py:160` (paper_trades mount) | exact |
| `tests/test_backtest_data_fetcher.py` | test | n/a | `tests/test_data_fetcher.py` | exact |
| `tests/test_backtest_simulator.py` | test | n/a | `tests/test_pnl_engine.py` | role-match |
| `tests/test_backtest_metrics.py` | test | n/a | `tests/test_pnl_engine.py` | exact |
| `tests/test_backtest_render.py` | test | n/a | `tests/test_dashboard.py` (golden HTML) | role-match |
| `tests/test_backtest_cli.py` | test | n/a | `tests/test_main.py` (argparse) | role-match |
| `tests/test_web_backtest.py` | test | n/a | `tests/test_web_paper_trades.py` | exact |
| `tests/fixtures/backtest/golden_report.json` | fixture | n/a | `tests/fixtures/state_v6_with_paper_trades.json` | role-match |
| `tests/test_signal_engine.py` (extension) | test | n/a | existing `_HEX_PATHS_STDLIB_ONLY` (line 599) | exact |
| `requirements.txt` (pyarrow add) | config | n/a | existing pinned-deps lines | exact |
| `.gitignore` (cache dir) | config | n/a | n/a | DESIGN-FROM-SCRATCH (trivial) |

## Pattern Assignments

### `backtest/__init__.py` (constants)

**Closest analog:** `system_params.py:25-27, 73-78`
**Why this analog:** Same role — module-top constants for instrument multipliers/costs/strategy version. Current repo precedent for grep-discoverable, type-annotated `UPPER_SNAKE: float = ...` declarations.
**Pattern to copy:**
- Top docstring describes module role + grep convention
- One-line typed constants: `BACKTEST_INITIAL_ACCOUNT_AUD: float = 10_000.0`
- Comment trailers explaining unit + provenance ('# AUD round-trip per CLAUDE.md D-11')
- No imports beyond `__future__` if any
**Pattern to adapt:**
- New constants are backtest-scoped (`BACKTEST_*` prefix) — Phase 19/20 D-19 anti-coupling rule says caller-side adapters supply primitives, but Phase 23 backtest IS its own self-contained adapter so a defaults dict is acceptable
- Do NOT re-export `system_params.SPI_MULT` etc. — `simulator.py` imports `system_params` directly per D-09 hex map
**Hex-boundary check:** clean (stdlib + typing only)

---

### `backtest/data_fetcher.py` (I/O adapter — yfinance + parquet cache)

**Closest analog:** `data_fetcher.py:1-132` (existing top-level `fetch_ohlcv`)
**Why this analog:** Identical role (yfinance retry-loop wrapper). Repository's only existing yfinance I/O hex. Documents the I/O-allowed exception block at module top.
**Pattern to copy:**
- Module docstring lines 1-25: states "I/O hex" + "ONE module allowed to open HTTPS connections" + lists the AST blocklist exclusion explicitly
- Narrow-catch tuple `_RETRY_EXCEPTIONS = (YFRateLimitError, ReadTimeout, ConnectionError)` — never `except Exception`
- Custom typed exceptions (`DataFetchError`, `ShortFrameError`) raised on terminal conditions
- `_REQUIRED_COLUMNS` frozenset validated BEFORE returning (schema-drift defence)
- Logger prefix style: `logger.warning('[Fetch] %s attempt %d/%d failed: %s', ...)` (Phase 23 swaps to `[Backtest]` per CLAUDE.md log-prefix convention)
- Retry-loop params parameterised (`retries=3, backoff_s=10.0`) for test determinism — pass `backoff_s=0.01` in tests
**Pattern to adapt:**
- Add parquet-cache wrapper around the existing fetch idiom: `_is_cache_fresh(path, max_age_seconds=86400)` gate before calling yfinance
- New imports allowed in this file (per D-09 documented exception): `pyarrow` (engine), `pathlib`, `datetime` for cache mtime + 5y date math
- New custom exception (or reuse `ShortFrameError` semantics) for "<5y data" bail per D-17
- Filename format: `<symbol>-<start>-<end>.parquet` per D-01
**Hex-boundary check:** I/O exception (D-09 — DOCUMENTED in module docstring; explicitly EXCLUDED from `_HEX_PATHS_STDLIB_ONLY` AST list — NOT added to the new `BACKTEST_PATHS_PURE` list)

---

### `backtest/simulator.py` (pure bar-by-bar replay)

**Closest analog:** `pnl_engine.py:1-55` (pure-math hex tier) + structural reference to `sizing_engine.step` at `sizing_engine.py:515`
**Why this analog:** Same hex-tier (pure math, stdlib + minimal-imports). `pnl_engine.py` is the most recent hex-pure module added to `_HEX_PATHS_STDLIB_ONLY`. Phase 19 D-19 + Phase 20 D-11 are the directly-mirrored precedents.
**Pattern to copy:**
- Top docstring with explicit "Architecture (hexagonal-lite, CLAUDE.md): pure math ONLY" preamble (mirror `pnl_engine.py:1-9`)
- Forbidden-imports block in docstring listing the AST guard contract (mirror `pnl_engine.py:8-11` and `alert_engine.py:7-12`)
- Public functions take plain args, return plain dict/dataclass — no `datetime.now()`, no env reads
- NaN-safe arithmetic: `if any(math.isnan(v) for v in (...))` early-return CLEAR/FLAT (mirror `alert_engine.py:51`)
**Pattern to adapt:**
- This module imports `signal_engine` + `sizing_engine` + `pandas` + `numpy` (per D-09 explicit allowlist) — NOT pure stdlib like `pnl_engine`. The AST guard for `BACKTEST_PATHS_PURE` must allow these four; differs from `_HEX_PATHS_STDLIB_ONLY` allowlist
- Loop body: `result = sizing_engine.step(position, bar, inds, old_signal, new_signal, account, multiplier, cost_aud_open)` per RESEARCH §Pattern 1 (8-arg signature; CONTEXT D-10's 3-arg description is wrong)
- Wrap numpy/pandas scalars with `float(x)` before storing in trade dict (RESEARCH §Pitfall 6)
- Carry `position_after['entry_date']` alongside state — `ClosedTrade` doesn't expose it (RESEARCH §Pitfall 7)
**Hex-boundary check:** clean BUT requires AST guard extension — must add to `BACKTEST_PATHS_PURE` (new list) and pass with allowlist `{signal_engine, sizing_engine, pandas, numpy, math, typing, system_params}`. Do NOT add to existing `_HEX_PATHS_STDLIB_ONLY` (would break — pandas/numpy forbidden there).

---

### `backtest/metrics.py` (pure aggregation)

**Closest analog:** `pnl_engine.py:1-55`
**Why this analog:** Pure-math, single-purpose, parametrize-friendly. Same hex tier; same import discipline; same docstring shape.
**Pattern to copy:**
- Module docstring lists each public function with its formula (mirror `pnl_engine.py:11-16`)
- Pure functions returning a dict (the metrics block) — no I/O
- `compute_metrics(equity_curve, trades) -> dict` signature; primitives in, dict out
**Pattern to adapt:**
- Imports `pandas` for the canonical `cummax()` max-drawdown idiom (RESEARCH §Pattern 7) — same allowlist exception as `simulator.py`
- Sharpe formula needs both `sharpe_daily` (raw mean/std) AND `sharpe_annualized` (× sqrt(252)) per planner D-19 amendment to RESEARCH A1 — emit BOTH; CONTEXT D-05 only names `sharpe_daily` but both go in JSON
- `pass` field is `cumulative_return_pct > 100.0` strict (D-16)
**Hex-boundary check:** clean — same AST treatment as `simulator.py` (added to `BACKTEST_PATHS_PURE`)

---

### `backtest/render.py` (pure HTML render)

**Closest analog:** `dashboard.py:2611-2688` (`_render_equity_chart_container` — Chart.js IIFE + json-injection defence) AND `dashboard.py:2257-2305` (`_render_paper_trades_open_form` — pure form HTML)
**Why this analog:** Render-helper-per-section convention; established Chart.js IIFE + JSON-payload-injection-defence pattern.
**Pattern to copy:**
- One render helper per section (mirror `_render_paper_trades_open`, `_render_paper_trades_stats`, `_render_paper_trades_open_form`, `_render_close_form_section` family at `dashboard.py:2233-2535`)
- Composition pattern at `dashboard.py:2517-2535` (`_render_paper_trades_region` concatenates child fragments) — `render_report` does same
- Chart.js JSON injection at `dashboard.py:2635-2641`:
  ```python
  payload = json.dumps({...}, ensure_ascii=False, sort_keys=True, allow_nan=False).replace('</', '<\\/')
  ```
- Chart.js URL + SRI strings copied verbatim from `dashboard.py:113-116` — DO NOT import dashboard.py (D-07 explicit + RESEARCH §Pattern 3)
- Every operator-visible string passes through `html.escape(s, quote=True)` — mirror `dashboard.py:2602, 2324`
- IIFE pattern verbatim: `(function() { new Chart(...); })();` (`dashboard.py:2649-2685`)
**Pattern to adapt:**
- Three canvas IDs (`equityChartSpi200`, `equityChartAudusd`, `equityChartCombined`) in three `<div role="tabpanel">` containers — RESEARCH §Pattern 3 confirms Chart.js destroy/recreate is wrong; render all three at load and toggle `hidden`
- Tab-switching JS block (RESEARCH §Pattern 3 inline `<script>` — 15 lines vanilla) is NEW — repository's first tab UI; Phase 17 used `<details>` not tabs
- Override form HTML (D-14) mirrors `_render_paper_trades_open_form` shape with three `<input type="number">` fields posting to `/backtest/run`
- History-view render (`render_history`) is NEW pattern — table sorted desc + 10-run-cap overlay chart with distinct colors per line
- Empty-state copy hard-coded per D-17 ("No backtest runs yet. Use the form above or run `python -m backtest` from CLI.")
**Hex-boundary check:** clean for `BACKTEST_PATHS_PURE` AST list IF allowlist explicitly includes `html` + `json` (stdlib, no I/O). `dashboard.py:113-116` Chart.js constants must be DUPLICATED here (not imported) per D-07; verify after wiring with `grep -n "import dashboard" backtest/render.py` returning zero matches.

---

### `backtest/cli.py` (argparse adapter)

**Closest analog:** `main.py:725-786` (`_build_parser`) + `main.py:1820-1854` (`main()` dispatch + dotenv + logging.basicConfig)
**Why this analog:** Repo's only argparse CLI. `main.py` carries the established `prog=`, `description=`, `add_argument` style with `help=` strings explaining requirement IDs.
**Pattern to copy:**
- `_build_parser()` factory returning `argparse.ArgumentParser` — mirror `main.py:725-786`
- `parser.error('--reset cannot be combined with...')` for cross-flag validation — mirror `main.py:799-800` (exits with code 2)
- Top-level dispatch: `parser.parse_args(argv)` → validate → run → return exit code (mirror `main.py:1846-1854`)
- `logging.basicConfig(level=logging.INFO, format='%(message)s', stream=sys.stderr, force=True)` at boot — mirror `main.py:1849-1854`
- Log prefix `[Backtest]` (NEW per CLAUDE.md and CONTEXT D-11) — same format as `[Fetch]`/`[State]` precedents
**Pattern to adapt:**
- Six `add_argument` lines per D-11 surface (`--years`, `--end-date`, `--initial-account`, `--cost-spi`, `--cost-audusd`, `--refresh`, `--output`)
- Exit code: 0 on PASS, 1 on FAIL — different from main.py's 0/1/2 mapping; document explicitly
- Reads `system_params.STRATEGY_VERSION` via FRESH attribute access INSIDE function body (NOT as kwarg default) — mirror `web/routes/paper_trades.py:262, 316` (`from system_params import STRATEGY_VERSION  # noqa: PLC0415`)
**Hex-boundary check:** adapter — allowed: argparse, json, sys, pathlib, logging, all `backtest/*`, `system_params`. NOT in `BACKTEST_PATHS_PURE` AST list.

---

### `backtest/__main__.py` (module entry dispatch)

**Closest analog:** none in repo — DESIGN-FROM-SCRATCH
**Why this analog:** Repo has no `__main__.py` precedent (`main.py` is invoked as `python main.py`, not `python -m main`).
**Pattern to copy:** standard Python idiom (3 lines):
```python
'''Phase 23: enables `python -m backtest`. Dispatches to backtest.cli.main().'''
from backtest.cli import main
main()
```
**Pattern to adapt:** none — trivial
**Hex-boundary check:** trivial adapter; not in any AST list

---

### `web/routes/backtest.py` (FastAPI route handlers)

**Closest analog:** `web/routes/paper_trades.py:1-485`
**Why this analog:** Phase 19 — most recent web route adapter; same architectural tier; same Form-encoded handler pattern; cookie-auth via Phase 16.1 middleware (no per-route auth code); 400-on-validation convention; HTML fragment response pattern.
**Pattern to copy:**
- Module docstring shape `paper_trades.py:1-39` — describes routes, contract, hex layering, log prefix
- `_LOG_PREFIX = '[Web]'` (Phase 23 keeps `[Web]` for routes; CLI uses `[Backtest]`)
- `register(app: FastAPI) -> None` factory (`paper_trades.py:228`) — called from `web/app.py` per Phase 19 mount precedent at `web/app.py:160`
- Form-encoded body handler pattern at `paper_trades.py:251-302`:
  - `Form(...)` parameters per RESEARCH §Pattern 8 (`run_backtest(initial_account_aud: float = Form(...), cost_spi_aud: float = Form(...), cost_audusd_aud: float = Form(...))`)
  - Pydantic `Field(gt=0)` for positive-validation
  - `RedirectResponse(url='/backtest', status_code=303)` per RESEARCH §Pattern 8 + A2 (303 not 307)
- LOCAL imports inside handler bodies (Phase 11 C-2): `from system_params import STRATEGY_VERSION` re-read per call (`paper_trades.py:262, 316`)
- Auth: Phase 16.1 AuthMiddleware gates all routes uniformly — no per-route auth code (`paper_trades.py:35-36` docstring note)
- 400 on validation failures: re-uses global `RequestValidationError` handler at `web/app.py:174-179`
**Pattern to adapt:**
- Path-traversal guard for `?run=<filename>` is NEW in repo — RESEARCH §Pattern 5 specifies regex `^[a-zA-Z0-9._-]+\.json$` + `os.listdir('.planning/backtests/')` whitelist. No prior precedent — DESIGN-FROM-SCRATCH (use the RESEARCH excerpt verbatim)
- Filesystem read in `GET /backtest` (latest by mtime sort) — uses `pathlib.Path.iterdir()` + `sorted(...key=lambda p: p.stat().st_mtime, reverse=True)`. No direct repo precedent for this idiom; document in module docstring
- Synchronous `POST /backtest/run` calls `backtest.simulator.simulate(...)` directly (no mutate_state — backtests don't touch state.json per scope)
**Hex-boundary check:** adapter — allowed imports: FastAPI, system_params, web.middleware (transitively via auth), all `backtest/*`. NOT in any pure-AST list. Verify with grep that `signal_engine` / `sizing_engine` are NOT imported here (those go through `backtest.simulator`).

---

### `web/app.py` (mount line)

**Closest analog:** `web/app.py:160` — `paper_trades_route.register(application)` precedent
**Why this analog:** Exact same registration pattern; one-line addition.
**Pattern to copy:**
- Add `from web.routes import backtest as backtest_route` to import block at `web/app.py:40-48`
- Add `backtest_route.register(application)` line in `create_app()` adjacent to `paper_trades_route.register(application)` (`web/app.py:160`)
**Pattern to adapt:** none
**Hex-boundary check:** clean — `web/app.py` is the factory; allowed to register all route modules

---

### `tests/test_backtest_data_fetcher.py`

**Closest analog:** `tests/test_data_fetcher.py` (existing yfinance retry tests)
**Why this analog:** Exact role — adapter-tier test for yfinance + cache idiom.
**Pattern to copy:**
- Use `tmp_path` pytest fixture for filesystem isolation (cache tests write parquet under tmp_path; never under real `.planning/backtests/data/`)
- Monkeypatch `yfinance.Ticker` to return canned DataFrame — mirror existing data_fetcher tests
- `retries=3, backoff_s=0.01` for fast retry-path coverage (data_fetcher.py:74-75 contract)
**Pattern to adapt:**
- New cases: cache-hit (24h fresh) returns without yfinance call; cache-miss writes parquet; `--refresh` ignores cache; `<5y` data bail (per D-17)
- Parquet round-trip determinism: write → read → assert DataFrame equality with `pd.testing.assert_frame_equal`
**Hex-boundary check:** test-tier — clean

---

### `tests/test_backtest_simulator.py`

**Closest analog:** `tests/test_pnl_engine.py:1-100` (parametrize grid for pure-math hex)
**Why this analog:** Both target pure-math modules with deterministic input → deterministic output contract.
**Pattern to copy:**
- Parametrize-grid shape at `test_pnl_engine.py:26-44` — list of tuples `(case_id, *args, expected)` with `ids=[c[0] for c in CASES]`
- `abs(result - expected) < 1e-9` tolerance assertion (`test_pnl_engine.py:61-63`)
- NaN-safety test pattern (`test_pnl_engine.py:65-73`)
- Hex-boundary AST test class (`test_pnl_engine.py` `TestPnlEngineHexBoundary`) — extend equivalent for `BACKTEST_PATHS_PURE`
**Pattern to adapt:**
- Replay-determinism test: golden 50-bar fixture (hand-authored CSV with deterministic prices) → simulator → assert trade-list and equity-curve byte-stable across two runs (mirror Phase 1 SHA256 oracle approach in spirit, simpler in form)
- Exit-reason mapping verbatim per planner D-20: `flat_signal`, `signal_reversal`, `trailing_stop`, `adx_drop`, `manual_stop` — NOT D-05's `signal_change` (RESEARCH Open Question 4 resolved)
- `step()` 8-arg signature usage (RESEARCH §Pattern 1, NOT CONTEXT D-10's 3-arg)
- Cost-model reconstruction test: pass `cost_aud_open = 3.0` (half of SPI 6.0); assert `cost_aud = 6.0` in JSON output (RESEARCH §Pitfall 1)
**Hex-boundary check:** clean — test file imports allowed broadly

---

### `tests/test_backtest_metrics.py`

**Closest analog:** `tests/test_pnl_engine.py:46-80` (parametrize CRUD over formula matrix)
**Why this analog:** Same shape — deterministic formula tests with edge-case parametrize.
**Pattern to copy:**
- Parametrize edge cases: zero-trades, all-losses, all-wins, single-bar (`_UNREALISED_CASES` shape at `test_pnl_engine.py:26-44`)
- 1e-9 tolerance assertions for floating-point metrics
**Pattern to adapt:**
- Test BOTH `sharpe_daily` (raw mean/std) AND `sharpe_annualized` (× sqrt(252)) per planner D-19 — assert ratio is exactly `sqrt(252)` ≈ 15.874
- Max-drawdown pandas-cummax idiom (RESEARCH §Pattern 7) tested with non-monotonic equity series (peak-to-trough not min/max)
- `pass = cum_return > 100.0` strict — boundary test at exactly 100.0 → `pass=False`
**Hex-boundary check:** clean — pandas in tests is fine

---

### `tests/test_backtest_render.py`

**Closest analog:** `tests/test_dashboard.py` (golden HTML contains-string tests; not loaded here, structurally well-known)
**Why this analog:** HTML render tests — assert structural elements rather than exact string match.
**Pattern to copy:**
- Load `tests/fixtures/backtest/golden_report.json`, pass to `render_report`, assert resulting string contains key markers
- `assert '<canvas id="equityChartCombined"' in html`
- `assert 'role="tab"' in html` (three tab buttons per RESEARCH §Pattern 3)
- `assert _CHARTJS_SRI in html` (Chart.js SRI presence test — mirrors dashboard SRI verification)
- json.dumps injection-defence test: synthetic trade with `</script>` in `exit_reason` field → `json.dumps(...).replace('</', '<\\/')` produces `<\/script` in output (NOT raw `</script>`)
**Pattern to adapt:**
- Three-tab layout assertion is NEW (no prior precedent — repo's first tab UI)
- History view test: pass `[report1, report2, ...]` (10 entries) → `render_history` → assert table + 10 chart datasets
- Empty-state test: pass empty list → render returns the locked D-17 copy verbatim
- Override form test: assert three `<input type="number" name="initial_account_aud|cost_spi_aud|cost_audusd_aud">` fields
**Hex-boundary check:** clean

---

### `tests/test_backtest_cli.py`

**Closest analog:** `tests/test_main.py` (argparse-flag-combo + exit-code tests, structurally well-known)
**Why this analog:** Same role — argparse surface validation + exit-code mapping.
**Pattern to copy:**
- Subprocess invocation pattern: capture stdout/stderr/exit-code via `subprocess.run([sys.executable, '-m', 'backtest', ...], capture_output=True)`
- Or in-process: `cli.main(['--years', '5'])` → assert returned exit code
- Log-line format assertion: `'[Backtest] PASS' in stderr` (CONTEXT D-11 specifies exact format)
**Pattern to adapt:**
- Exit-code mapping 0=PASS, 1=FAIL (different from main.py's 0/1/2)
- Test JSON write path: `--output /tmp/...json` → file exists with all D-05 fields
- Monkeypatch `backtest.data_fetcher.fetch_ohlcv` to return canned 5y fixture (avoid yfinance network call in unit test)
**Hex-boundary check:** clean

---

### `tests/test_web_backtest.py`

**Closest analog:** `tests/test_web_paper_trades.py:1-100` + `tests/conftest.py` `valid_cookie_token` fixture
**Why this analog:** Exact role — FastAPI TestClient web-route tests with cookie auth.
**Pattern to copy:**
- Helpers `_now_awst_iso`, `_past_awst_iso` (`test_web_paper_trades.py:45-57`) — direct mirror
- `valid_cookie_token` fixture (`conftest.py:91-101`) — pass via `cookies={'tsi_session': valid_cookie_token}` on every request
- `client_with_state_v6` fixture (`conftest.py:311-362`) — mirror for backtest seed (state-stub + monkeypatch state_manager OR — since backtests don't touch state.json — use simpler tmp_path-based fixture)
- TestClient `follow_redirects=False` for redirect status assertion (RESEARCH §Pattern 8 example)
- 401 plain assertion for unauthenticated curl (`test_web_paper_trades.py` analog tests for AuthMiddleware behavior)
**Pattern to adapt:**
- Path-traversal test: `client.get('/backtest?run=../../etc/passwd')` → 400 (CONTEXT verification step 8)
- POST `/backtest/run` test: form-encoded body, 303 redirect to `/backtest`, new file written to test tmp_path
- Mock `os.listdir('.planning/backtests/')` via `monkeypatch.setattr` to return controlled filename whitelist
- New fixture for backtest report directory (tmp_path-backed)
**Hex-boundary check:** clean

---

### `tests/fixtures/backtest/golden_report.json`

**Closest analog:** `tests/fixtures/state_v6_with_paper_trades.json` (committed JSON fixture; ~25 lines)
**Why this analog:** Hand-authored, schema-driven, small-and-readable. Structural-test-only fixture pattern.
**Pattern to copy:**
- Hand-author per RESEARCH §Code Examples §"Golden report fixture"
- Match D-05 schema field-by-field (metadata block, metrics block w/ both `sharpe_daily` + `sharpe_annualized` per planner D-19, equity_curve, trades)
- Minimal: 2 equity points, 1 trade, all D-05 fields populated
- ~3-5 KB target — small enough to be obvious in git diff, large enough to exercise all render branches
**Pattern to adapt:**
- New directory `tests/fixtures/backtest/` (mkdir as part of Wave 0)
- Use realistic SPI200 prices (~7800) and AUDUSD prices (~0.65) so render branches exercise both instruments
- DESIGN-FROM-SCRATCH: planner authors the file; not generated by simulator (avoids fixture-network-dependence per RESEARCH)
**Hex-boundary check:** n/a (data file)

---

### `tests/test_signal_engine.py` extension (line 480, 593, 599)

**Closest analog:** Existing line 599 `_HEX_PATHS_STDLIB_ONLY = [SIZING_ENGINE_PATH, SYSTEM_PARAMS_PATH, PNL_ENGINE_PATH, ALERT_ENGINE_PATH]`
**Why this analog:** Direct precedent — Phase 19 added `pnl_engine.py`, Phase 20 added `alert_engine.py`. Phase 23 follows the same template, with one critical difference: pure-math allowlist must include `signal_engine`, `sizing_engine`, `pandas`, `numpy` (which `_HEX_PATHS_STDLIB_ONLY` forbids).
**Pattern to copy:**
- Path constants at line 480 area: `BACKTEST_SIMULATOR_PATH = Path('backtest/simulator.py')`, `BACKTEST_METRICS_PATH = Path('backtest/metrics.py')`, `BACKTEST_RENDER_PATH = Path('backtest/render.py')`
- Add to `_HEX_PATHS_ALL` at line 596 (so the broad `test_forbidden_imports_absent` test against `FORBIDDEN_MODULES` runs against them — `state_manager`, `notifier`, `dashboard`, `main`, `requests`, `os`, `datetime`, `yfinance`, `schedule` all forbidden)
- Phase 19/20 banner-comment style: `# Phase 23: backtest/{simulator,metrics,render}.py added — pure-math hex tier with pandas/numpy/signal_engine/sizing_engine ALLOWLIST exception`
**Pattern to adapt:**
- Do NOT add to `_HEX_PATHS_STDLIB_ONLY` (line 599) — pandas/numpy are required for these files (different from `pnl_engine`/`alert_engine` which are stdlib-only)
- New parametrize list `_BACKTEST_PATHS_PURE = [BACKTEST_SIMULATOR_PATH, BACKTEST_METRICS_PATH, BACKTEST_RENDER_PATH]` with new test method that walks them against `FORBIDDEN_MODULES` (excluding pandas/numpy from the forbidden set for these files)
- `backtest/data_fetcher.py` is EXPLICITLY excluded from any AST list — documented in test comment per D-09
**Hex-boundary check:** test-extension — exactly matches Phase 19/20 precedent shape

---

### `requirements.txt` (pyarrow add)

**Closest analog:** existing `pandas==2.3.3` line + project policy in CLAUDE.md "Exact version pins (no `>=`, no `~=`)"
**Why this analog:** Direct precedent — every dep is exact-pinned per CLAUDE.md and STATE.md §Todos Carried Forward.
**Pattern to copy:**
- Add line `pyarrow==24.0.0` (RESEARCH §Standard Stack — verified latest stable, Python 3.11 wheel available)
- Optionally add `python-dateutil==2.9.0.post0` (currently transitive via pandas; Assumption A4 — explicit pin per project policy)
**Pattern to adapt:** none
**Hex-boundary check:** n/a

---

### `.gitignore` (cache dir)

**Closest analog:** none directly — DESIGN-FROM-SCRATCH (trivial)
**Why this analog:** Trivial config addition.
**Pattern to copy:** add `.planning/backtests/data/` line per D-01 (parquet cache is per-machine, not committed)
**Pattern to adapt:** none

---

## Shared Patterns

### Hex-boundary preservation
**Source:** `tests/test_signal_engine.py:592-600` (`_HEX_PATHS_ALL`, `_HEX_PATHS_STDLIB_ONLY`)
**Apply to:** all new pure modules (`backtest/simulator.py`, `metrics.py`, `render.py`)
**Pattern:**
```python
# Phase 23: pure backtest hex modules — pandas/numpy/signal_engine/sizing_engine
# allowlist exception (different from STDLIB_ONLY tier)
BACKTEST_SIMULATOR_PATH = Path('backtest/simulator.py')
BACKTEST_METRICS_PATH   = Path('backtest/metrics.py')
BACKTEST_RENDER_PATH    = Path('backtest/render.py')
_BACKTEST_PATHS_PURE    = [BACKTEST_SIMULATOR_PATH, BACKTEST_METRICS_PATH, BACKTEST_RENDER_PATH]
# Test walks each path; forbids state_manager/notifier/dashboard/main/requests/
# os/datetime/yfinance/schedule but ALLOWS pandas/numpy/signal_engine/sizing_engine
```

### STRATEGY_VERSION fresh-attribute access (kwarg-default capture trap)
**Source:** `web/routes/paper_trades.py:262, 316` (`from system_params import STRATEGY_VERSION  # noqa: PLC0415`)
**Apply to:** `backtest/cli.py` (writing JSON metadata) and `web/routes/backtest.py` (POST handler)
**Pattern:**
```python
def _write_report(...) -> None:
  import system_params  # fresh — never as kwarg default
  report['metadata']['strategy_version'] = system_params.STRATEGY_VERSION
```
Per LEARNINGS 2026-04-29 + Phase 22 D-04 precedent.

### Form-encoded POST body handling
**Source:** `web/routes/paper_trades.py:78-102` (`_parse_form` helper) + `paper_trades.py:251-258` (route signature)
**Apply to:** `web/routes/backtest.py` POST `/backtest/run`
**Pattern:**
```python
@app.post('/backtest/run')
async def run_backtest(
  request: Request,
  initial_account_aud: float = Form(...),
  cost_spi_aud: float = Form(...),
  cost_audusd_aud: float = Form(...),
) -> RedirectResponse:
  # validate > 0; run sim; write JSON
  return RedirectResponse(url='/backtest', status_code=303)  # 303 not 307
```
Pydantic `Field(gt=0)` for positive validation; 400 on failure via global handler at `web/app.py:174-179`.

### Cookie-session auth gating
**Source:** `web/middleware/auth.py` (Phase 16.1) — gates all routes uniformly
**Apply to:** all `/backtest*` routes (no per-route auth code needed)
**Pattern:** AuthMiddleware sees the path, applies cookie-OR-redirect logic. Test fixture `valid_cookie_token` in `conftest.py:91-101` provides a signed cookie for happy-path tests.

### Chart.js + JSON-injection defence
**Source:** `dashboard.py:113-116` (CDN URL + SRI constants) + `dashboard.py:2635-2641` (json.dumps replace pattern)
**Apply to:** `backtest/render.py` (three Chart.js canvases — combined + spi200 + audusd)
**Pattern:**
```python
_CHARTJS_URL = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.js'
_CHARTJS_SRI = 'sha384-MH1axGwz/uQzfIcjFdjEfsM0xlf5mmWfAwwggaOh5IPFvgKFGbJ2PZ4VBbgSYBQN'
# DUPLICATE these — DO NOT import from dashboard.py per D-07.

payload = json.dumps(
  {'labels': labels, 'data': data},
  ensure_ascii=False, sort_keys=True, allow_nan=False,
).replace('</', '<\\/')
```

### `[Backtest]` log-prefix discipline
**Source:** CLAUDE.md log-prefix convention + CONTEXT D-11 specified format
**Apply to:** `backtest/cli.py` and `backtest/data_fetcher.py`
**Pattern:** `logger.info('[Backtest] Simulating SPI200: %d bars, %d trades', n_bars, n_trades)` — mirrors `[Fetch]`, `[State]`, `[Email]`, `[Sched]`, `[Web]` precedents.

### NaN-safe early-return in pure-math
**Source:** `alert_engine.py:51` (`if any(math.isnan(v) for v in (...)): return 'CLEAR'`)
**Apply to:** `backtest/simulator.py` and `backtest/metrics.py`
**Pattern:** Wrap NaN-prone inputs (warmup ATR, divide-by-zero std) with `math.isnan` early-return rather than letting NaN propagate silently.

---

## No Analog Found (DESIGN-FROM-SCRATCH)

| Symbol | Reason | Recommendation |
|---|---|---|
| Tab UI (`role="tab"` + `role="tabpanel"`) | First tab implementation in repo (Phase 17 used `<details>`, not tabs) | Use RESEARCH §Pattern 3 verbatim — 15-line vanilla JS, ARIA-compliant; no library |
| Path-traversal whitelist for `?run=<filename>` | First user-supplied-filename route in repo | Use RESEARCH §Pattern 5 two-layer defence (regex + `os.listdir` whitelist) |
| Golden report JSON fixture (hand-authored) | No existing render-test JSON-fixture pattern (existing fixtures are state.json snapshots, schema-different) | Hand-author per D-05 schema; ~3-5 KB; planner Wave 0 task |
| Dual-Sharpe formula (`sharpe_daily` raw + `sharpe_annualized` × √252) | RESEARCH A1 surfaced ambiguity; planner D-19 amendment emits BOTH | Implement both in `metrics.py`; test the √252 ratio explicitly |
| `backtest/__main__.py` dispatch | Repo has no `python -m <module>` precedent | Trivial 2-line dispatch — see entry above |

---

## Metadata

**Analog search scope:** repository root, `web/`, `tests/`, `tests/fixtures/`, `.planning/phases/`
**Files scanned:** `data_fetcher.py`, `pnl_engine.py`, `alert_engine.py`, `signal_engine.py`, `sizing_engine.py`, `system_params.py`, `main.py`, `dashboard.py`, `web/app.py`, `web/routes/paper_trades.py`, `web/routes/__init__.py`, `tests/test_signal_engine.py`, `tests/test_pnl_engine.py`, `tests/test_alert_engine.py`, `tests/test_web_paper_trades.py`, `tests/conftest.py`, `tests/fixtures/state_v6_with_paper_trades.json`
**Pattern extraction date:** 2026-05-01
**Hex-boundary risks surfaced:**
1. `backtest/simulator.py` + `metrics.py` + `render.py` need a NEW AST guard list (`_BACKTEST_PATHS_PURE`) — they are NOT a drop-in member of `_HEX_PATHS_STDLIB_ONLY` because they require pandas/numpy/signal_engine/sizing_engine/html/json (not stdlib-only)
2. `backtest/data_fetcher.py` is the documented I/O exception — DO NOT add to any pure AST list; document the exception in module-top docstring per `data_fetcher.py:1-11` precedent
3. `backtest/render.py` must DUPLICATE Chart.js URL+SRI constants (D-07 forbids importing dashboard.py) — verification grep `grep -n "import dashboard" backtest/render.py` must return zero matches
4. `web/routes/backtest.py` must NOT import `signal_engine` or `sizing_engine` directly — those go through `backtest.simulator`
