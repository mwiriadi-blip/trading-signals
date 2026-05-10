---
phase: 19-paper-trade-ledger
verified: 2026-04-30T00:00:00Z
status: passed
score: 7/7 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: passed
  previous_score: 7/7
  previous_warning: "enctype=application/json on open-trade form; browser would fall back to form-encoded while route expected JSON body"
  gaps_closed:
    - "dashboard.py open-trade form enctype changed to application/x-www-form-urlencoded"
    - "web/routes/paper_trades.py mutation handlers now read request.form() via _parse_form helper"
    - "tests/test_web_paper_trades.py mutation route calls converted from json={} to data={}"
    - "Golden HTML fixtures regenerated — no stale application/json enctype in fixtures"
  gaps_remaining: []
  regressions: []
---

# Phase 19: Paper-Trade Ledger Verification Report

**Phase Goal:** Operator records the trades they've actually placed, tracks open positions with live mark-to-market P&L, and sees a closed-trade history with realised P&L and aggregate stats.
**Verified:** 2026-04-30
**Status:** PASSED
**Re-verification:** Yes — after fix-forward commit f3179ab (WARNING closed)

---

## Goal Achievement

### Observable Truths (ROADMAP SC-1..7)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC-1 | POST /paper-trade/open validates server-side and appends to state.paper_trades | VERIFIED | TestOpenPaperTrade + TestOpenValidation (17 tests) all pass; D-04 rules enforced via Pydantic model_validator |
| SC-2 | POST /paper-trade/{id}/close computes realised P&L + flips status=closed | VERIFIED | TestClosePaperTrade (6 tests) pass; pnl_engine.compute_realised_pnl wired; exit_dt/exit_price/realised_pnl set |
| SC-3 | Closed rows immutable — server returns 405 to PATCH/DELETE | VERIFIED | TestImmutability (2 tests) pass; _method_not_allowed_405 helper returns 405 + Allow: GET per RFC 7231 |
| SC-4 | Open trades table renders with current price + unrealised P&L (mark-to-market) | VERIFIED | TestRenderPaperTradesOpenTable (11 tests) pass; NaN/None guards render "n/a (no close price yet)" |
| SC-5 | Closed trades table renders sortable by exit date desc | VERIFIED | TestRenderPaperTradesClosedTable (4 tests) pass; sorted by exit_dt desc confirmed |
| SC-6 | Aggregate stats line: realised, unrealised, win count, loss count, win rate | VERIFIED | TestRenderPaperTradesStats (8 tests) pass; zero-P&L excluded from wins/losses; em-dash when no closed rows |
| SC-7 | Atomic-write contract preserved — paper_trades writes via state_manager.mutate_state | VERIFIED | All four mutation routes call mutate_state(_apply); no direct load_state/save_state in _apply; Phase 14 flock kernel unchanged |

**Score:** 7/7 truths verified

---

## Context Verification Matrix (D-01..D-22, 17 items from CONTEXT + 6 planner-pinned)

| # | Decision | Check | Status | Evidence |
|---|----------|-------|--------|----------|
| D-01 | Composite ID SPI200-YYYYMMDD-NNN inside mutate_state lock | VERIFIED | TestCompositeIDGeneration (4 tests): 001/002/AUDUSD-001/overflow-400 all pass |
| D-02 | Half round-trip cost on entry (entry_cost_aud = round_trip/2) | VERIFIED | SPI200: _COST_AUD['SPI200']/2 = 3.0; AUDUSD: 2.5; row shape test confirmed |
| D-03 | Close form below open trades table (HTMX hx-get close-form route) | VERIFIED | GET /paper-trade/{id}/close-form route exists; TestCloseFormFragment (2 tests) pass |
| D-04 | Strict validation: future entry_dt, price<=0, contracts<=0, fractional SPI, wrong-side stop | VERIFIED | All 17 TestOpenValidation tests pass; 400 returned per D-22 amendment |
| D-05 | PATCH/DELETE allowed on open; closed rows return 405 immutable | VERIFIED | TestImmutability passes; strategy_version refreshed on PATCH |
| D-06 | Sticky aggregate stats bar, 5 badges, wins/losses count only >0/<0 | VERIFIED | test_stats_bar_uses_position_sticky_css PASS; test_aggregate_stats_zero_pnl_excluded PASS |
| D-07 | NaN/None last_close renders "n/a (no close price yet)" | VERIFIED | dashboard.py line 2343/2351; test_open_table_renders_na_when_last_close_missing/nan both PASS |
| D-08 | Schema bump 5→6; paper_trades[] top-level array | VERIFIED | STATE_SCHEMA_VERSION=6 in system_params.py; _migrate_v5_to_v6 in MIGRATIONS[6] |
| D-09 | 13-key row shape (id, instrument, side, entry_dt, entry_price, contracts, stop_price, entry_cost_aud, status, exit_dt, exit_price, realised_pnl, strategy_version) | VERIFIED | test_open_writes_full_d09_row_shape uses _D09_KEYS frozenset; extra='forbid' on Pydantic model |
| D-11 | P&L formulas: LONG=(last_close-entry)*contracts*mult-cost; SHORT=(entry-last_close)*... | VERIFIED | pnl_engine.py lines 33-37/52-55; 16 parametrized test cases in test_pnl_engine.py all PASS |
| D-13 | Single #trades-region HTMX swap target for every mutation | VERIFIED | All six routes return _render_paper_trades_region(state); region wraps div#trades-region |
| D-15 | All mutations via mutate_state; no direct load_state/save_state in _apply | VERIFIED | paper_trades.py: every _apply closure uses mutate_state; no state I/O inside closures |
| D-16 | Exact empty-state copy strings | VERIFIED | "No open paper trades. Use the form above to record a new entry." + "No closed trades yet..." confirmed in test_open_table_empty_state_copy + test_closed_table_empty_state_copy |
| D-17 | No hx-ext="json-enc" on paper-trade routes | VERIFIED | grep confirms hx-ext="json-enc" not present in paper_trades.py; form uses enctype="application/x-www-form-urlencoded" (fixed in f3179ab) |
| D-18 | Singular /paper-trade/{id} for individual; plural /paper-trades for GET list | VERIFIED | Route definitions confirmed: GET /paper-trades, POST /paper-trade/open, PATCH/DELETE /paper-trade/{id} |
| D-19 | pnl_engine.py imports only math + typing (no system_params) | VERIFIED | test_pnl_engine_module_imports_only_math_and_typing PASS; implementation passes caller-supplied constants (better than CONTEXT spec) |
| D-20 | Fixture tests/fixtures/state_v6_with_paper_trades.json exists with 2 open + 2 closed | VERIFIED | File exists; python parse: open=2, closed=2, schema_version=6 |
| D-21 | DELETE route has no body; hx-confirm drives operator confirmation | VERIFIED | delete_paper_trade handler takes only trade_id path param, no body model; test_delete_no_body PASS |
| D-22 | Validation failures return 400 (NOT 422); tests assert 400 | VERIFIED | All 16+ test assertions use == 400; Pydantic 422 remapped by global RequestValidationError handler |
| Phase 22 LEARNINGS: migration idempotent | VERIFIED | _migrate_v5_to_v6 checks `if 'paper_trades' not in s`; TestMigrateV5ToV6::test_migrate_v5_to_v6_idempotent* both PASS |
| Phase 22 LEARNINGS: kwarg-default capture trap honored | VERIFIED | `from system_params import STRATEGY_VERSION` inside both _apply closures (open + PATCH); monkeypatch test confirms fresh read picks up patched value |
| Hex-boundary primitives-only preserved | VERIFIED | pnl_engine.py: no forbidden imports (AST guard test passes, 4 parametrized); dashboard.py: no signal_engine import; pnl_engine LOCAL-imported inside function bodies |

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `pnl_engine.py` | Pure-math P&L module | VERIFIED | 56 lines; compute_unrealised_pnl + compute_realised_pnl; imports only math |
| `web/routes/paper_trades.py` | 6 FastAPI routes + _parse_form helper | VERIFIED | _parse_form async helper at line 78; reads request.form(), calls model_validate; three mutation handlers call it (lines 258, 314, 394) |
| `tests/test_pnl_engine.py` | P&L test coverage | VERIFIED | 19 tests: 8 unrealised + 8 realised parametrized + hex boundary tests; all PASS |
| `tests/test_web_paper_trades.py` | Route coverage using data={} | VERIFIED | 46 tests across 12 classes; all mutation calls use data={} (json={ count = 0) |
| `tests/fixtures/state_v6_with_paper_trades.json` | v6 fixture 2+2 | VERIFIED | schema_version=6, 2 open + 2 closed rows; no stale application/json enctype in any fixture |
| `system_params.py` STATE_SCHEMA_VERSION=6 | Schema bump | VERIFIED | Line 121 confirmed |
| `state_manager.py` _migrate_v5_to_v6 + MIGRATIONS[6] | Migration | VERIFIED | Lines 215-235 confirmed |
| `dashboard.py` paper-trade region | Render helpers + correct enctype | VERIFIED | enctype="application/x-www-form-urlencoded" at line 2269; _render_paper_trades_open/closed/stats/region + _compute_aggregate_stats all present |
| `web/app.py` paper_trades route mount | Router mount | VERIFIED | Lines 47 + 160 confirmed |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| dashboard.py | pnl_engine.compute_unrealised_pnl | LOCAL import inside _compute_aggregate_stats + _render_paper_trades_open | VERIFIED | Lines 926, 2314 — LOCAL import pattern preserved |
| web/routes/paper_trades.py | state_manager.mutate_state | LOCAL import inside every _apply closure | VERIFIED | Lines 253, 305, 334, 391 |
| web/routes/paper_trades.py | system_params.STRATEGY_VERSION | LOCAL import inside _apply (open+PATCH) | VERIFIED | Lines 225, 276 — kwarg trap honored |
| web/routes/paper_trades.py | pnl_engine.compute_realised_pnl | LOCAL import inside close _apply | VERIFIED | Line 353 |
| web/routes/paper_trades.py | _parse_form + request.form() | Three mutation handlers (open/edit/close) | VERIFIED | Lines 258, 314, 394 call _parse_form; form() read at line 91 |
| web/app.py | paper_trades_route.register | Direct call at app factory | VERIFIED | Line 160 |
| tests/test_signal_engine.py | pnl_engine.py | AST forbidden-imports guard extended | VERIFIED | 4 parametrized paths pass including pnl_engine |

---

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| dashboard _render_paper_trades_open | paper_trades (open rows) | state.get('paper_trades', []) + signals from state_manager.load_state | Yes — reads live state dict from caller-supplied state arg | FLOWING |
| dashboard _compute_aggregate_stats | realised_pnl, unrealised via pnl_engine | state.paper_trades[] + signals[instrument].last_close | Yes — real data from daily run's last_close | FLOWING |
| POST /paper-trade/open | rows appended | mutate_state writes to state.json atomically; form data parsed via _parse_form + request.form() | Yes — D-09 row shape fully populated from URL-encoded form body | FLOWING |

---

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| STATE_SCHEMA_VERSION = 6 | grep STATE_SCHEMA_VERSION system_params.py | 6 confirmed on line 121 | PASS |
| _migrate_v5_to_v6 registered in MIGRATIONS[6] | grep "6: _migrate_v5_to_v6" state_manager.py | Line 235 confirmed | PASS |
| All 74 targeted Phase 19 tests pass | pytest test_pnl_engine + TestMigrateV5ToV6 + test_web_paper_trades + TestDeterminism::test_forbidden_imports_absent | 74 passed in 1.54s | PASS |
| Full suite excluding pre-existing failures | pytest tests/ --ignore nginx/notifier/setup-https | 1243 passed in 12.04s | PASS |
| No json={ in mutation route tests | grep -c 'json={' tests/test_web_paper_trades.py | 0 | PASS |
| No enctype="application/json" in dashboard.py | grep -nE 'enctype="application/json"' dashboard.py | zero matches | PASS |
| enctype="application/x-www-form-urlencoded" present | grep -nE 'enctype=' dashboard.py | line 2269 confirmed | PASS |
| No stale enctype in fixtures | grep -r 'enctype="application/json"' tests/fixtures/ | zero matches | PASS |
| _parse_form helper exists + wired to three handlers | grep -n '_parse_form\|request.form' web/routes/paper_trades.py | lines 78, 91, 258, 314, 394 | PASS |
| Fixture: 2 open + 2 closed rows in v6 fixture | python3.11 JSON parse | open=2 closed=2 schema_version=6 | PASS |
| pnl_engine imports only math (no system_params) | AST test + grep imports | Only `import math` at module top | PASS |
| 405 + Allow: GET on closed-row mutation | TestImmutability x3 | All 405 assertions pass | PASS |
| Concurrent open produces unique IDs | TestConcurrentOpen::test_concurrent_open_does_not_collide | PASS (multiprocessing.Process) | PASS |
| STRATEGY_VERSION fresh read after monkeypatch | test_open_strategy_version_fresh_read_after_monkeypatch | PASS — picks up v9.9.9 | PASS |

---

## Requirements Coverage

| Requirement | Phase | Description | Status | Evidence |
|-------------|-------|-------------|--------|----------|
| LEDGER-01 | 19 | Web form for manual paper trade entry; validated server-side | Complete | REQUIREMENTS.md flipped; TestOpenValidation 17 tests pass |
| LEDGER-02 | 19 | Per-trade entry in state.paper_trades[] with all 13 fields including strategy_version | Complete | D-09 row shape test; strategy_version tagged on write |
| LEDGER-03 | 19 | Open trades table with mark-to-market unrealised P&L | Complete | TestRenderPaperTradesOpenTable 11 tests pass |
| LEDGER-04 | 19 | Closed trades table sorted by exit date desc; closed rows immutable | Complete | TestRenderPaperTradesClosedTable + TestImmutability |
| LEDGER-05 | 19 | Close form; server computes realised P&L; status flipped to closed | Complete | TestClosePaperTrade 6 tests pass |
| LEDGER-06 | 19 | Aggregate stats: realised, unrealised, wins, losses, win rate | Complete | TestRenderPaperTradesStats 8 tests pass |
| VERSION-03 | 22 | Every paper trade row tagged with strategy_version at write time | Complete | TestStrategyVersionTagging 3 tests pass including monkeypatch |

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None | — | — | — | All previously flagged anti-patterns resolved in f3179ab |

**Previously flagged (now resolved):** `dashboard.py` line 2269 had `enctype="application/json"` — a non-standard enctype that browsers do not recognise. Fixed to `enctype="application/x-www-form-urlencoded"`. Routes now read `request.form()` via `_parse_form` helper. Tests updated to use `data={}`. Golden fixtures regenerated.

---

### Human Verification Required

None. The previously required human browser test (to verify form submission worked) is now satisfied by the server-side fix: mutation routes accept `application/x-www-form-urlencoded` form bodies, which is what browsers and HTMX send by default. The WARNING is closed.

---

## Pre-Existing Failures (Unrelated to Phase 19)

12 failures confirmed pre-existing from Phase 10/11 (nginx conf was committed in a state that Phase 10 tests now flag):

- `tests/test_nginx_signals_conf.py` — 9 failures (nginx/signals.conf has SSL certs filled in; tests expect placeholders)
- `tests/test_notifier.py` — 2 failures (`ruff` not in PATH on this machine)
- `tests/test_setup_https_doc.py` — 1 failure (cross-artifact drift with nginx conf)

All pre-date Phase 19; confirmed by checking `git log -- tests/test_nginx_signals_conf.py` (last modified Phase 10/11).

---

## SUMMARY Honesty Check

**Claimed 1468 tests passing.** Actual: 1505 collected, 1493 passing (12 pre-existing failures). The SUMMARY was written mid-execution with an approximation. Not a concern for goal achievement.

**Claimed 93 tests in test_web_paper_trades.py.** Actual: 46 tests (confirmed with `--co`). The 93 figure likely includes helper functions, fixtures, and module-level code in the line count. All required behaviors are covered by the 46 actual test functions.

**Claimed all 17 CONTEXT verification items PASS.** Verified independently: all 17 pass, including the one deviation (pnl_engine.py does NOT import system_params — callers supply constants instead, which is architecturally superior and tested by the hex-boundary AST check).

---

## Gaps Summary

No gaps. All 7 ROADMAP success criteria verified. All 22 locked decisions verified. All 17 CONTEXT verification items verified. All 7 requirements (LEDGER-01..06 + VERSION-03) confirmed Complete. The enctype WARNING from the initial verification is closed by commit f3179ab.

---

## Re-verification (2026-04-30)

**Fix applied:** Commit f3179ab resolved the single WARNING from the initial verification.

**Changes verified:**
1. `grep -nE 'enctype="application/json"' dashboard.py` — zero matches (PASS). `enctype="application/x-www-form-urlencoded"` now at line 2269.
2. `grep -c 'json={' tests/test_web_paper_trades.py` — returns `0` (PASS). All mutation route tests use `data={}`.
3. `data={` confirmed as the standard pattern across all four mutation test classes (open, edit, close, delete).
4. `_parse_form` async helper at line 78 of `web/routes/paper_trades.py` reads `request.form()`, drops empty-string values, calls `model_validate`, re-raises `ValidationError` as `RequestValidationError`.
5. 74 in-scope tests pass; 1243 full-suite tests pass (excluding 12 pre-existing unrelated failures).
6. All 17 CONTEXT matrix items hold — D-17 note updated: form now uses `application/x-www-form-urlencoded` not the former `application/json` deviation.
7. All 7 ROADMAP SC-1..7 verified. All LEDGER-01..06 + VERSION-03 Complete. Hex-boundary AST guard (test_forbidden_imports_absent, 4 parametrized) passes.

**Previous verdict:** PASSED with WARNING (browser form encoding mismatch).
**New verdict:** PASSED — WARNING closed. No human verification required.

---

_Verified: 2026-04-30_
_Initial verification: 2026-04-30_
_Re-verification: 2026-04-30 (after fix-forward commit f3179ab)_
_Verifier: Claude (gsd-verifier)_
