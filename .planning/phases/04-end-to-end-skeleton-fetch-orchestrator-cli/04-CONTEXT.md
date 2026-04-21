# Phase 4 — CONTEXT

**Phase:** 04 — End-to-End Skeleton — Fetch + Orchestrator + CLI
**Created:** 2026-04-21
**Discuss mode:** discuss
**Goal (from ROADMAP.md):** Wire signal_engine, sizing_engine, and state_manager behind a real yfinance fetch. `python main.py --once` reads Yahoo, computes signals for `^AXJO` and `AUDUSD=X`, updates state, prints a structured console summary. No email, no dashboard, no schedule loop yet.

**Requirements covered:** DATA-01, DATA-02, DATA-03, DATA-04, DATA-05, DATA-06, CLI-01, CLI-02, CLI-03, CLI-04, CLI-05, ERR-01, ERR-06 (13 requirements)
**Out of scope (later phases):** email notification (Phase 6), dashboard (Phase 5), schedule loop wiring (Phase 7), Resend failure handling (Phase 8 / ERR-02), corrupt-state surfacing to operator (Phase 8 / ERR-03), top-level crash-email (Phase 8 / ERR-04), stale-state banner (Phase 8 / ERR-05).

<canonical_refs>

External specs, ADRs, and prior CONTEXT docs that downstream agents must consult:

- **.planning/PROJECT.md** — Project-level constraints (stack, deployment targets, Perth timezone, tech allowlist).
- **.planning/REQUIREMENTS.md** — The 13 in-scope requirement IDs with full text; cross-phase coverage map.
- **.planning/ROADMAP.md** — Phase 4 goal, success criteria, requirement IDs, dependency on Phases 1/2/3.
- **CLAUDE.md** — 2-space indent, single quotes, PEP 8, log prefixes `[Signal] [State] [Email] [Sched] [Fetch]`, `--test` structurally read-only, `signal_as_of` vs `run_date` separation, hex-lite rules (signal_engine ↔ state_manager must not import each other).
- **SPEC.md** — Full functional specification including retry policies, data providers, timezone expectations. (Locked by Phase 2 D-11 on contract specs; Phase 4 does not amend SPEC.md unless a later cross-AI review surfaces something.)
- **.planning/phases/01-signal-engine-core-indicators-vote/01-CONTEXT.md** — D-05..D-08 public API of `signal_engine.py` (`compute_indicators`, `get_signal`, `get_latest_indicators`); D-09..D-12 NaN policies Phase 4 orchestrator must respect.
- **.planning/phases/02-signal-engine-sizing-exits-pyramiding/02-CONTEXT.md** — D-02 orchestrator uses `get_latest_indicators(df)` to extract scalars; D-07 hex-lite boundaries of `sizing_engine.py`; D-08 `Position` TypedDict; D-10 `step()` + `StepResult` shape; D-11 contract specs ($5/pt SPI, $10K AUDUSD notional); D-13 cost split half-on-open half-on-close; D-17 `step()` expanded signature.
- **.planning/phases/03-state-persistence-with-recovery/03-CONTEXT.md** + **03-01 through 03-04 SUMMARY.md** — `_atomic_write`, `save_state`, `load_state`, `reset_state`, `append_warning`, `record_trade` (D-13/D-14/D-15/D-19/D-20), `update_equity_history` (B-4), `_validate_loaded_state` (D-18), `_REQUIRED_STATE_KEYS` / `_REQUIRED_TRADE_FIELDS`, STATE_SCHEMA_VERSION=1 migration hook.
- **system_params.py** — Existing Phase 1–3 constants: `INITIAL_ACCOUNT`, `MAX_WARNINGS`, `STATE_SCHEMA_VERSION`, `STATE_FILE`, contract specs, `Position` TypedDict.

If no external doc exists for a decision below, that is stated explicitly ("no ref — new decision").

</canonical_refs>

<prior_decisions>

Decisions from earlier phases that apply to Phase 4 without re-asking:

- **Hex-lite boundaries** (Phase 1 + 2 + 3): `main.py` is the ONLY module that may import signal_engine + sizing_engine + state_manager + data_fetcher. Each engine module remains pure-math or I/O-isolated to its own concern. The AST blocklist guard in `tests/test_signal_engine.py::TestDeterminism` is extended to assert Phase 4 new modules respect the boundary.
- **Log prefixes** (CLAUDE.md): `[Signal] [State] [Email] [Sched] [Fetch]` are locked. Phase 4 uses these verbatim in every log line.
- **`--test` structurally read-only** (CLAUDE.md): Compute and persist are split such that `--test` code paths structurally cannot reach `save_state`. Not a runtime guard — an architectural one.
- **`signal_as_of` vs `run_date`** (CLAUDE.md): Both are logged on every run. Never substituted for each other. `signal_as_of` comes from the last OHLCV bar date. `run_date` comes from `datetime.now(Australia/Perth)` at the start of the run.
- **Tech stack constraint** (PROJECT.md): Python 3.11, pinned deps `yfinance`, `pandas`, `numpy`, `requests`, `schedule`, `python-dotenv`, `pytz`. No other frameworks. Phase 4 adds no new deps.
- **Style** (CLAUDE.md): 2-space indent, single quotes, PEP 8 via ruff. Snake_case for functions, UPPER_SNAKE for constants. Instrument keys `SPI200` / `AUDUSD` match state.json convention.
- **Contract specs** (Phase 2 D-11 / D-13): SPI 200 mini multiplier = $5/pt, $6 AUD round-trip (split $3 open / $3 close). AUDUSD notional = $10,000, $5 AUD round-trip ($2.50 / $2.50). Phase 4 orchestrator passes these to sizing functions from `system_params.py`.
- **Timezone** (CLAUDE.md / PROJECT.md): Perth (AWST, UTC+8, no DST) via `pytz.timezone('Australia/Perth')`. All user-facing timestamps use AWST.
- **Phase 1 D-08 contract**: Orchestrator consumes `get_latest_indicators(df) -> dict` for scalars. `df.iloc[-1]` indexing stays inside signal_engine.py — Phase 4 does not duplicate it.
- **Phase 2 D-02**: Sizing/exit functions take scalars, not DataFrames. Phase 4 orchestrator unpacks the dict from get_latest_indicators and hands scalars to `step()`.
- **State atomicity** (Phase 3 D-04): `save_state` is already atomic (tempfile + fsync + os.replace). Phase 4 calls it exactly once per run (or zero times for `--test`). No new atomicity requirements.
- **No `max(1, …)` floor** (operator decision): If `n_contracts == 0` from sizing, the trade is skipped with a visible warning. Phase 4 orchestrator surfaces the warning to console and via `append_warning`.

</prior_decisions>

<folded_todos>

No pending todos matched Phase 4 scope — scope is tightly constrained by ROADMAP.md requirement IDs.

</folded_todos>

<decisions>

## Fetch isolation & test strategy

- **D-01: New module `data_fetcher.py` at repo root owns all yfinance I/O.**
  Public API: `fetch_ohlcv(symbol: str, days: int = 400, retries: int = 3, backoff_s: float = 10.0) -> pd.DataFrame`. Returns a DataFrame with columns `[Open, High, Low, Close, Volume]` and a DatetimeIndex in Australia/Perth. Raises `DataFetchError` (custom exception) after retries exhaust.
  `data_fetcher.py` is the new I/O hex (analogous to `state_manager.py`). It imports `yfinance`, `requests` (for any bare HTTP fallback), `time` (for sleep), `pandas` (DataFrame), and `system_params` (constants). It MUST NOT import `signal_engine`, `sizing_engine`, `state_manager`, `main`, or `notifier`. The `TestDeterminism::test_forbidden_imports_absent` AST guard in `tests/test_signal_engine.py` gains a `FORBIDDEN_MODULES_DATA_FETCHER` entry covering this.
  Rationale: matches Phase 3 scaffolding pattern (state_manager.py has same hex-lite stance with its own allow-list). Keeps Phase 4 orchestrator imports clean and gives Phase 7 scheduler a pre-built fetch entry point.

- **D-02: Hybrid test strategy — recorded JSON fixtures + hand-built DataFrames.**
  Canonical happy-path fixture: one committed JSON per instrument at `tests/fixtures/fetch/{symbol_slug}_400d.json` (e.g. `axjo_400d.json`, `audusd_400d.json`) captured by a manually-run `tests/regenerate_fetch_fixtures.py` (mirror of Phase 1's `regenerate_goldens.py`). These are used by one integration-style happy-path test per instrument.
  Scenario/error tests use hand-built pandas DataFrames or monkeypatch `yfinance.download` to raise / return short frames / return empty frames — e.g. a test for DATA-04 (len < 300) builds a 299-row DataFrame; a test for 3×-retry-then-fail monkeypatches `yfinance.download` to always raise.
  Rationale: matches the Phase 1 fixture-pattern (canonical plus scenario). Recorded fixtures prove we still decode the real yfinance response shape; hand-built DataFrames cover edge paths without heavy dependencies like `vcrpy`.

- **D-03: Any instrument fetch failure after 3 retries hard-fails the whole run.**
  If SPI 200 succeeds but AUDUSD raises `DataFetchError` (or vice versa), the orchestrator logs `[Fetch] ERROR AUDUSD: retries exhausted — aborting run`, writes no state (neither instrument's signal), and exits non-zero (exit code 2 — see D-08).
  Rationale: matches DATA-04 posture (short frame is already hard-fail). Avoids the "half-stale state" problem where one instrument has a fresh signal and the other is a day behind — which would make Phase 6 email content ambiguous and Phase 7 retry logic harder. Operator preference ("never crash silently; fail loudly") confirmed in discuss-phase.
  Phase 8 extends this by adding a crash-email on top via ERR-04 top-level handler — Phase 4 only ensures exit is graceful (log + exit non-zero, no traceback noise).

## CLI parsing & flag semantics

- **D-04: stdlib `argparse` for CLI parsing.**
  No new dependency. Covers all 5 flags (`--test`, `--reset`, `--force-email`, `--once`, default) cleanly. Phase 6 may add `--email-preview` or similar without changing the parser strategy.
  Rationale: PROJECT.md Constraints explicitly limits the stack to `yfinance / pandas / numpy / requests / schedule / python-dotenv / pytz`. Adding `click` or `typer` would require operator amendment of the stack. argparse meets all functional needs.

- **D-05: Strict flag-combination validation.**
  - `--reset` is a mutually-exclusive group of its own (argparse `add_mutually_exclusive_group`) OR asserted early in `main()` — passing `--reset` with any other flag returns exit 2 with `error: --reset cannot be combined with other flags`.
  - `--test` + `--force-email` is ALLOWED (lets the operator preview "what the email would say right now" without mutating state; useful once Phase 6 lands).
  - `--once` and default-mode are mutually exclusive by construction — default in Phase 4 == `--once` (see D-07), so Phase 4 treats `--once` as a no-op alias. Phase 7 flips the default.
  - Invalid combos → argparse exit code 2 + clear error message.

- **D-06: `--force-email` is parsed in Phase 4 but logs "not wired until Phase 6" and returns exit 0.**
  argparse accepts `--force-email` from Phase 4 onward — the CLI surface is frozen now so integration tests can reference the flag. When passed in Phase 4, `main.py` emits `[Email] --force-email received; notifier wiring arrives in Phase 6` and exits 0 (or falls through to the normal run + stub log). Phase 6 replaces the stub with the real `notifier.send_daily_email()` call.
  Rationale: locks CLI contract now so Phase 4 integration tests and CI scripts can be written once. Avoids raising `NotImplementedError` (conflicts with "never crash silently").

- **D-07: Default `python main.py` in Phase 4 == single run + exit (same as `--once`).**
  The schedule library wiring (`schedule.every().day.at('00:00').do(...)`) is added in Phase 7 alongside the GHA cron configuration. Phase 4 keeps the CLI definition for CLI-05 but implements it as an alias for `--once` with a log line `[Sched] One-shot mode (scheduler wiring lands in Phase 7)`. Phase 7 flips this behavior to actually enter the loop.
  Rationale: keeps Phase 4 scope tight. Tests stay free of clock-loop noise (no pytest-freezer needed for schedule.every().do pattern). Phase 7 owns all scheduler concerns.

## Signal-as-of & stale-bar budget

- **D-08: `signal_as_of` stored per-instrument under `state['signals'][symbol]['signal_as_of']`.**
  Structure: `state['signals'] = {'SPI200': {'signal_as_of': 'YYYY-MM-DD', 'signal': <int>, ...}, 'AUDUSD': {...}}`. One field per instrument because `^AXJO` and `AUDUSD=X` can legitimately have different last-bar dates (ASX holiday, weekend-edge, forex 24/5 vs daily-close cadence). No `STATE_SCHEMA_VERSION` bump needed — this is a nested key inside the existing `signals` dict which `_validate_loaded_state` only checks at the top level. Backward-compatible: an older state file without the key is treated as "stale unknown" → warning logged, run continues.
  Rationale: keeps the schema migration door closed until a real breaking change warrants it. Matches the per-instrument-isolation posture of D-03.

- **D-09: Stale threshold = `>3 calendar days` for both instruments.**
  `(today_awst - signal_as_of).days > 3` triggers a DATA-05 warning. Same rule for both instruments.
  Handles the common cases: Mon run sees Fri bar (3 days — OK). Tue after Mon public holiday sees Fri bar (4 days — warning, usually the operator already knows why). Easter weekend edge cases trip the warning harmlessly. Multi-day Yahoo outages are caught early.
  Rationale: per-instrument thresholds are possible but add complexity (AUDUSD 24/5 has ~2-day weekend, `^AXJO` has weekend + holiday calendar). One rule is easier to audit. Edge cases resolve themselves inside the warning-without-fatal contract.

- **D-10: Stale warning path: console log + `state_manager.append_warning(...)`.**
  `data_fetcher` or orchestrator emits `[Fetch] WARN ^AXJO stale: signal_as_of=2026-04-15 is 6d old (threshold=3d)` to console (logging.WARNING level). Orchestrator then calls `state_manager.append_warning(state, {level: 'warn', code: 'stale_bar', symbol, signal_as_of, days_old, detected_at_run_date})` before `save_state`. Phase 6 email reads `state['warnings']` FIFO and renders the most recent N in the top banner; Phase 8 (stale-state banner ERR-05) builds on this same pipeline.
  Rationale: Phase 3 `append_warning` already handles FIFO bound (`MAX_WARNINGS`) and AWST date tagging — reuse, don't duplicate.

## Orchestrator sequence & logging

- **D-11: Single atomic `save_state` at end of `run_daily_check()`. `--test` path never calls it.**
  Sequence inside `run_daily_check(args)`:
  1. `run_date = datetime.now(Australia/Perth)` and log `[Sched] Run 2026-04-21 09:00:03 AWST mode={once|test|reset|force_email}`.
  2. `state = state_manager.load_state()` (or `reset_state()` for `--reset` branch, which hits `save_state(reset_state())` and exits).
  3. For each symbol `[^AXJO, AUDUSD=X]`:
     a. `df = data_fetcher.fetch_ohlcv(symbol, days=400, retries=3)` — raises `DataFetchError` → caught at top level of `run_daily_check`, logged, exit non-zero.
     b. `if len(df) < 300:` → raise a `ShortFrameError` (DATA-04 hard-fail).
     c. Stale check (D-09, D-10): if stale, log WARN + queue an `append_warning(state, ...)` call for the end-of-run batch.
     d. `df = signal_engine.compute_indicators(df)` → `scalars = signal_engine.get_latest_indicators(df)` → `new_signal = signal_engine.get_signal(df)`.
     e. `old_signal = state['signals'][symbol]['signal']` (with default 0/FLAT for first-run).
     f. `position = state['positions'].get(symbol)` (or None if flat).
     g. `bar = df.iloc[-1]` (Open/High/Low/Close/Volume) — passed to `sizing_engine.step()`.
     h. `result: StepResult = sizing_engine.step(position, bar, scalars, old_signal, new_signal)`.
     i. Log per-instrument block (see D-14 shape).
     j. In memory: update `state['positions'][symbol] = result.updated_position` (or `del` if now flat), update `state['signals'][symbol] = {signal: new_signal, signal_as_of: <last_bar_date>, as_of_run: run_date, last_scalars: scalars}`.
     k. For each closed trade in `result.closed_trades` (0 or 1 per step): `state_manager.record_trade(state, translate_closed_trade_to_dict(ct, symbol))` — see D-12.
  4. Compute total equity: `equity = state['account'] + sum(compute_unrealised_pnl(pos, current_price, mult, cost_open) for pos in state['positions'].values())`. Call `state_manager.update_equity_history(state, run_date_iso, equity)` (B-4 validation enforces shape).
  5. Flush queued warnings: for each pending `(level, code, symbol, ...)` call `state_manager.append_warning(state, ...)`.
  6. `state['last_run'] = run_date_iso` (matches Phase 3 state schema).
  7. If `args.test`: print run summary (see D-14) and RETURN without calling `save_state`. Structural guarantee: `--test` path never reaches step 8.
  8. `state_manager.save_state(state)` (atomic). Log `[State] state.json saved (account=$X, trades=N, positions=M)`.
  9. Print run summary footer (D-14).

  Rationale: one atomic save = all-or-nothing semantics. If anything raises between steps 1–6, state.json is never touched (matches --test read-only guarantee and the "never half-persist" rule). Aligns with Phase 3 D-04 atomicity posture. No new transactional machinery needed — the existing `save_state` call is the commit point.

- **D-12: `main.py` translates `StepResult.closed_trade` → `record_trade` dict. Neither engine imports the other.**
  `StepResult.closed_trades: list[ClosedTrade]` (dataclass from `sizing_engine.py` with fields: `entry_price, exit_price, entry_date, exit_date, direction, n_contracts, realised_pnl, atr_entry`). In `main.py` a thin helper `_closed_trade_to_record(ct: ClosedTrade, symbol: str, cost_close_aud: float, cost_open_aud: float) -> dict` constructs the 10-field dict required by Phase 3 `_validate_trade` (D-15 + D-19): `{symbol, entry_date, exit_date, direction, entry_price, exit_price, n_contracts, realised_pnl, atr_entry, pyramid_level_at_close}`. The helper lives in `main.py` because it crosses the hex boundary by design — it's the adapter between sizing_engine's dataclass and state_manager's dict contract.
  Rationale: preserves hex-lite boundaries (sizing_engine doesn't know state_manager's schema; state_manager doesn't know sizing_engine's dataclasses). Only the orchestrator sees both. Matches Phase 2 D-02 spirit: cross-module translation stays in main.py.

- **D-13: `signal_as_of` is derived from `df.index[-1]` (last-bar date) and stored as ISO `YYYY-MM-DD` string.**
  Source of truth: `df.index[-1].strftime('%Y-%m-%d')` where `df.index` is a pandas DatetimeIndex. No timezone conversion — use the date component of the last bar as-returned by yfinance. `run_date` is separately computed as `datetime.now(pytz.timezone('Australia/Perth'))`. Both are logged.
  Rationale: yfinance returns bar dates in exchange-local timezone by default; converting to AWST would shift some bar-dates across day boundaries (e.g. a 17:00 EDT Friday AUDUSD bar becomes Saturday in AWST). The bar date is a calendar identifier for the market day, not a timestamp — keep it as-is.

- **D-14: Per-instrument log block + run-summary footer, plain text with `[Prefix]` convention.**
  Per-instrument block (one per symbol, separated by blank line):
  ```
  [Fetch] ^AXJO ok: 400 bars, last_bar=2026-04-17, fetched_in=1.2s
  [Signal] ^AXJO signal=LONG signal_as_of=2026-04-17 (ADX=28.3, moms=+2/+3/+1, rvol=0.14)
  [State] ^AXJO position: LONG 2 contracts @ entry=8204.5, pyramid=0, trail_stop=8120.1, unrealised=+$850
  [State] ^AXJO no trades closed this run
  ```
  Run-summary footer:
  ```
  [Sched] Run 2026-04-21 09:00:03 AWST done in 2.1s — instruments=2, trades_recorded=0, warnings=0, state_saved=true
  ```
  For `--test` mode the footer reads `state_saved=false (--test)`.
  Rationale: matches CLAUDE.md prefix convention. Human-readable in Replit TTY and GHA raw-text output. grep-parseable for warnings. JSON Lines considered and rejected — existing convention wins, and the operator consumes these logs by eye.

- **D-15: Python `logging` module, configured once in `main.py`.**
  `logging.basicConfig(level=logging.INFO, format='%(message)s', stream=sys.stderr)` called at the top of `main()`. Each module uses `logger = logging.getLogger(__name__)`. Orchestrator emits pre-formatted `[Prefix] msg` strings through `logger.info(...)` / `logger.warning(...)`. `DataFetchError` and `ShortFrameError` log at `logger.error(...)` level before re-raising or exiting.
  Rationale: stdlib, zero deps, tunable. Phase 8 can add a `FileHandler` for disk-backed logs without touching callers. Tests can silence output via `caplog` or a configured test logger. Aligns with the "never reinvent stdlib" principle.

## Claude's Discretion

The following implementation details are left to the researcher/planner/executor — they are design consequences of the decisions above, not operator choices:

- Exact exception class hierarchy in `data_fetcher.py` (e.g. `DataFetchError`, `ShortFrameError`, `StaleFrameError` — or just one `DataFetchError` with an enum). Planner decides based on how tests want to pattern-match.
- Exact argparse subcommand vs flag structure (all-flags is the simpler baseline; researcher may recommend subcommands if it helps help-text clarity).
- Whether `data_fetcher.fetch_ohlcv` takes a start/end date or only `days=400`. Prefer `days` to match the roadmap; researcher may surface calendar-day vs trading-day ambiguity.
- Retry policy jitter — fixed 10s backoff per DATA-03 is the baseline; researcher may recommend jitter if yfinance has known rate-limit patterns.
- How `run_daily_check()` is organised internally (one function vs a thin class vs a small dispatch table). The `run_daily_check()` name is already locked by CLAUDE.md.
- How `_closed_trade_to_record` handles `pyramid_level_at_close` — source it from the closed trade's position state at close (sizing_engine owns `peak_price` + `pyramid_level`), or recompute in main.py from `StepResult`. Planner picks based on what sizing_engine already exposes.
- Test file organisation (one `tests/test_main.py`? `tests/test_data_fetcher.py` + `tests/test_main.py` split? Prior phases split by module — probably the same here).
- Whether the hybrid fetch-fixture regenerator (`tests/regenerate_fetch_fixtures.py`) is a single plan task or a scaffold task in Wave 0.
- Logging format-string exact whitespace and rounding (e.g. unrealised P&L to $0 vs $0.0 vs $0.00).

## Phase 4 Scope Boundaries (what NOT to do)

- No email sending. `--force-email` is a stub log in Phase 4; Phase 6 wires the notifier.
- No dashboard HTML generation. Phase 5 owns.
- No scheduler loop. Default mode in Phase 4 == `--once`. Phase 7 owns `schedule` library wiring + GHA cron config.
- No Resend failure handling beyond the stub. Phase 8 owns ERR-02.
- No corrupt-state banner surfacing to operator. Phase 3 already backs-up-and-resets; Phase 4 honours that; Phase 8 adds the email banner (ERR-03/ERR-05).
- No top-level crash-email (ERR-04). Phase 4 top-level `try/except Exception` logs and exits non-zero; Phase 8 upgrades to crash-email.
- No schema version bump. State v1 stays v1 (per D-08 — nested key under existing `signals` dict).
- No `pytz` date-arithmetic refactor in earlier phases. Phase 4 uses `pytz.timezone('Australia/Perth')` for `run_date` computation only.
- No performance optimisation of fetch (single-threaded, sequential per-instrument, fine at scale of 2).

</decisions>

<deferred>

Ideas raised in discussion that belong in later phases or future milestones:

- `--email-preview` or `--dry-run-email` CLI flag for Phase 6 — captured now, implement then.
- JSON-Lines structured log format for machine consumption — rejected for Phase 4, may revisit if Phase 7 scheduler logs need structured parsing.
- Per-instrument stale thresholds (^AXJO vs AUDUSD) — one threshold for Phase 4; split later if false-positive or false-negative rate warrants.
- Schema v2 with explicit typed `signal_as_of` field — deferred until a real breaking change forces the migration.
- `vcrpy` or record-replay HTTP testing — rejected as unnecessary dependency for Phase 4; hybrid strategy suffices.
- Dedicated `logger.py` wrapper — rejected, stdlib `logging` is enough.
- Retry jitter or exponential backoff beyond the DATA-03 flat 10s — can be added in Phase 7 if real-world yfinance behaviour warrants.
- Schedule-loop "already ran today" guard (idempotency check so a mid-day restart doesn't re-run). Phase 7.

</deferred>

<downstream_notes>

For the researcher (gsd-phase-researcher):
- Investigate yfinance API call signature (`yfinance.download(symbol, period, interval)` vs `Ticker(symbol).history(...)`), rate limits, and how to recognise retry-eligible failures (network timeout, 5xx, rate-limit) vs hard-stops (invalid symbol, auth failure).
- Check what yfinance returns on empty-response (DataFrame vs None vs raise).
- Check whether `yfinance` in requirements.txt is currently 1.2.0 (pinned) and whether that version has known issues relevant to 400-day daily downloads for `^AXJO` and `AUDUSD=X`.
- Survey argparse patterns for mutually-exclusive groups + subcommand-style usage lines.
- Check pytest patterns for monkeypatching `yfinance.download` (conftest.py fixture? per-test patch? session-scoped cassette?).
- Confirm Phase 3 `append_warning` signature matches the `{level, code, symbol, signal_as_of, days_old, detected_at_run_date}` shape assumed in D-10 — if not, D-10 needs adjusting (or append_warning takes a free-form dict already, per Phase 3 SUMMARY).
- Confirm `StepResult.closed_trades` dataclass field set matches D-12's assumption — re-read `.planning/phases/02-signal-engine-sizing-exits-pyramiding/02-CONTEXT.md` D-10 and the Phase 2 SUMMARY files.

For the planner (gsd-planner):
- Likely plan breakdown (researcher confirms):
  - **Wave 0 (scaffold):** data_fetcher.py stub + `DataFetchError` + AST blocklist extension + tests/test_data_fetcher.py skeleton + tests/regenerate_fetch_fixtures.py stub. CLI parser skeleton in main.py with argparse flag definitions (no behaviour). Recorded JSON fixtures committed.
  - **Wave 1 (data_fetcher implementation):** `fetch_ohlcv` with yfinance call, retry loop, stale detection, short-frame check. Tests populate TestFetch (happy path from recorded JSON + scenario tests).
  - **Wave 2 (orchestrator happy path):** `run_daily_check()` wiring steps 1–9 from D-11, stub for `--test` and `--reset`, log formatter (D-14), `_closed_trade_to_record` helper. Tests populate TestOrchestrator (golden end-to-end with recorded fixtures + frozen clock).
  - **Wave 3 (CLI + error boundary + stale-warning path):** argparse dispatch, flag mutex, top-level try/except, DATA-05 + ERR-01 paths, `--test` structural read-only proof test, signal_as_of/run_date separation test.
- The Phase 4 success criteria (5 items in ROADMAP.md) each want a named pytest class/method with clear evidence — similar to Phase 3's verification pattern.
- `pytest-freezer` becomes relevant in Phase 4 (Phase 1 D-15 noted it would) — pin it in requirements.txt in Wave 0.

For the reviewer (cross-AI review after plans written):
- Watch for silent-success on yfinance returning a DataFrame with wrong column names (the Yahoo API has shifted column naming before — "Adj Close" vs "Close").
- Watch for timezone conversion leaks between `signal_as_of` (market-local calendar day) and `run_date` (Australia/Perth wall-clock).
- Watch for race conditions in the Phase 3 `_atomic_write` when `save_state` is called in Phase 4's orchestrator end-of-run — no race expected but worth a sanity check.
- Watch for Phase 4 accidentally reaching into Phase 3 internals (`_atomic_write`, `_migrate`) rather than the public API (`save_state`, `load_state`, `reset_state`, `record_trade`, `update_equity_history`, `append_warning`).

</downstream_notes>

## Next Step

Run `/gsd-plan-phase 4` to produce `04-RESEARCH.md` and `04-01-PLAN.md` … `04-NN-PLAN.md` from this context.

If you want cross-AI peer review of the plans before execution, run `/gsd-review 4` after plans are drafted.
