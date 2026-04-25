---
phase: 14-trade-journal-mutation-endpoints
verified: 2026-04-25T11:30:00Z
status: human_needed
score: 6/6 must-haves verified
overrides_applied: 0
human_verification:
  - test: 'HTMX form swaps render correctly in real browsers (Chrome, Firefox, Safari)'
    expected: 'Open form submits and receives empty body + HX-Trigger event; per-tbody listener refreshes positions; close-form 2-stage flow shows confirmation row; modify form swaps inline; 4xx errors surface in `.error` region without full-page reload'
    why_human: 'Browser DOM diffing + HTMX runtime cannot be exercised in TestClient. JSON body parsing requires the json-enc extension to load and intercept htmx:configRequest. Server-side tests confirm markup + endpoints; only a real browser exercises the runtime.'
  - test: 'fcntl lock cross-process correctness on the live droplet'
    expected: 'Concurrent `python main.py --once` and POST /trades/open both succeed without torn writes; both mutations visible in state.json; repeat 5x to surface intermittent races'
    why_human: 'TestClient runs single-process; cross-process collision requires real systemd processes on the droplet. In-process subprocess tests cover the Python-level reentrancy contract but not the kernel-level POSIX flock semantics on the deployed Linux filesystem.'
  - test: 'Schema migration v2->v3 lands cleanly on the live droplet'
    expected: 'After deploy.sh lands Phase 14 on droplet, `python -c "from state_manager import load_state; s=load_state(); print(s[\"schema_version\"], all(\"manual_stop\" in p for p in s[\"positions\"].values() if p))"` prints `3 True`'
    why_human: 'Real droplet has a v2 state.json on disk; first Phase 14 deploy must migrate without data loss. Local fixture covers the round-trip but cannot prove the live disk file migrates cleanly.'
  - test: '4xx error responses render inline in HTMX without full-page reload'
    expected: 'Submit Open form with `entry_price=-1` -> `<div class="error">` populated above form, NO page reload, NO URL change'
    why_human: 'Browser-only behavior; TestClient sees the JSON 400 body but does not exercise the HTMX hx-on::after-request handler that wires the error into the inline `.error` slot.'
  - test: '2-stage destructive close UX feels intuitive'
    expected: 'Operator submits Close on a real position; confirmation flow obvious, Cancel reachable, confirmation panel shows correct exit_price input'
    why_human: 'Subjective UX evaluation; copy and visual treatment cannot be programmatically scored.'
---

# Phase 14: Trade Journal — Mutation Endpoints — Verification Report

**Phase Goal:** Let the operator record executed trades through the web UI — open, close, and modify positions via HTMX forms that POST to validated JSON endpoints. Every mutation flows through `state_manager.mutate_state()` (Phase 14 D-13) so the v1.0 sole-writer invariant for warnings holds.
**Verified:** 2026-04-25T11:30:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths (ROADMAP SC-1..SC-6)

| # | Truth (Success Criterion) | Status | Evidence |
|---|---|---|---|
| SC-1 | POST /trades/open with valid `{instrument, direction, entry_price, contracts}` appends a new position to `state.positions`, saves via `state_manager` (mutate_state per D-13), returns HTMX partial re-rendering positions table | VERIFIED | `web/routes/trades.py:462-548` open_trade handler uses `mutate_state(_apply)`; returns `_render_open_success_partial` with HX-Trigger + tbody partial. Tests `TestOpenTradeEndpoint::test_open_long_happy_path`, `test_open_short_happy_path`, `test_open_returns_html_partial_with_hx_trigger`, `TestHTMXResponses::test_open_response_contains_positions_tbody_partial` all pass (76/76 in test_web_trades.py) |
| SC-2 | POST /trades/open with invalid field (BTC instrument, contracts=0, entry_price=-1, NaN) returns HTTP 400 with JSON body listing each offending field; no state mutation | VERIFIED | Manual smoke confirms: BTC -> 400 `{"errors":[{"field":"instrument","reason":"Input should be 'SPI200' or 'AUDUSD'"}]}`; contracts=0 -> 400 with field=contracts; entry_price=-1 -> 400 with field=entry_price; NaN rejected at JSON-encoder layer (httpx refuses to send) and by the `_coherence` `math.isfinite` validator (`TestOpenAdvancedFields::test_entry_price_nan_returns_400` passes). `TestSaveStateInvariant::test_invalid_request_does_not_call_save_state` confirms no mutation. HR-01 `extra='forbid'` adds typo-field validation (`TestExtraFieldsForbidden` 3/3 pass) |
| SC-3 | POST /trades/close records via `state_manager.record_trade` — trade_log grows by one, state.account updates by realised P&L (D-13 half-on-close cost-split respected), state.positions loses closed position; LONG and SHORT P&L matches manual math | VERIFIED | `web/routes/trades.py:550-614` close_trade handler computes `gross_pnl` inline (D-05 anti-pitfall: `compute_unrealised_pnl` literal absent from source — `grep -c` returns 0); uses `record_trade` inside `mutate_state(_apply)`. `TestCloseTradePnLMath::test_close_long_pnl_math_matches_inline_formula` proves: 2 contracts * 5 mult * (7900-7800) = 1000 gross, -6.0 closing-half cost = 994 net, account=100994. SHORT path: 1 contract * 10000 mult * (0.6450-0.6420) = 30 gross, -2.5 closing-half = 27.5 net (pytest.approx). `test_close_does_not_call_unrealised_pnl_helper` AST-locks the anti-pitfall |
| SC-4 | POST /trades/modify can update trailing stop or contract count independently; new_contracts=0 or non-finite new_stop returns 400 | VERIFIED | `web/routes/trades.py:616-649` modify_trade uses Pydantic v2 `model_fields_set` for absent-vs-null PATCH semantics (D-12). REVIEWS LOW #9 / D-10: `pos['pyramid_level'] = 0` fires OUTSIDE the `if 'new_contracts' in model_fields_set` block — verified by `test_modify_only_new_stop_resets_pyramid_level`. `_new_contracts_floor` validator rejects new_contracts<1; `_new_stop_finite` validator rejects NaN/+/-inf. Tests `TestModifyTradeEndpoint` (10 tests) + `TestModifyAbsentVsNull` (3 tests) all pass |
| SC-5 | Dashboard GET / includes 3 HTMX forms (open/close/modify) that POST to endpoints and swap server-returned partial without full page reload; HTMX response asserted to be a fragment, not full HTML doc | VERIFIED | `dashboard.py:_render_open_form` (lines 923+) emits open form with `hx-post="/trades/open"` + `hx-ext="json-enc"` + `hx-swap="none"`. Per-row Close/Modify buttons in `_render_positions_table` emit `hx-get="/trades/close-form"`/`/trades/modify-form` with `hx-target="#position-group-{instrument}"` + `hx-swap="innerHTML"`. HTMX 1.9.12 SRI-pinned in `_render_html_shell` (line 1414): `sha384-ujb1lZYygJmzgSwoxRggbCHcjc0rB2XoQrxeTUQyRjrOnlCoYta87iKBWq3EsdM2`. CR-01 fix: json-enc extension also SRI-pinned (line 1419-1420) so form-encoded body becomes JSON for FastAPI/Pydantic. `TestHTMXResponses` confirms responses are partials (no `<html>` doc); `TestRenderDashboardHTMXVendorPin` (6 tests) + `TestRenderPositionsTableHTMXForm` (8 tests) all pass |
| SC-6 | No mutation endpoint writes `state['warnings']` directly — AST regression test asserts no `state['warnings'] =` or `.append` in web/routes/trades.py | VERIFIED | `tests/test_web_trades.py::TestSoleWriterInvariant` walks the AST of `web/routes/trades.py` for THREE branches: `Assign` (subscript), `Call` (.append/.extend/.insert), AND `AugAssign` (`+=`, `-=`) per REVIEWS LOW #8. Positive-control test `test_aug_assign_walker_fires_on_warnings_target` synthesizes a violation source to prove the walker is real (not tautological). `grep -c "state\\['warnings'\\]" web/routes/trades.py` returns 0; `grep -c "warnings.*\\.append"` returns 0. All 4 sole-writer tests pass |

**Score:** 6/6 truths verified.

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `web/routes/trades.py` | NEW: 3 POST + 3 GET endpoints, 3 Pydantic v2 models, 422->400 handler, _OpenConflict sentinel, mutator-closure shape | VERIFIED | 698 lines (plan min 280); 3 POST + 3 GET registered; 3 Pydantic models with `extra='forbid'` (HR-01); `_OpenConflict` private exception present; `_validation_exception_handler` exposed for app.py; 16 occurrences of `mutate_state` (vs 1 of `save_state`, in a comment); zero `compute_unrealised_pnl` mentions (D-05 anti-pitfall) |
| `web/app.py` | Registers trades route + RequestValidationError handler; module docstring extended for D-13/D-14 | VERIFIED | 121 lines; `trades_route.register(application)` on line 102; `application.add_exception_handler(RequestValidationError, trades_route._validation_exception_handler)` on lines 107-109; Phase 14 D-13/D-14 paragraph in module docstring (lines 20-29) |
| `web/routes/dashboard.py` | Substitutes `{{WEB_AUTH_SECRET}}` placeholder at request time; ?fragment= partial GET for per-tbody refresh | VERIFIED | 167 lines; `_PLACEHOLDER = b'{{WEB_AUTH_SECRET}}'` (line 76); GET / handler reads bytes + replaces placeholder with env value (lines 140-142); ?fragment= regex-extracts matching `<tbody>...</tbody>` with `re.escape` to block regex injection (lines 144-162) |
| `state_manager.py` | fcntl.LOCK_EX wrap on `_atomic_write` (D-13); NEW `mutate_state(mutator, path)` helper (REVIEWS HIGH #1); `_migrate_v2_to_v3` in MIGRATIONS dict (D-09); MIGRATIONS dict gains key 3 | VERIFIED | 726 lines; `import fcntl` line 56; `def _atomic_write` line 218 with `fcntl.flock(lock_fd, fcntl.LOCK_EX)` line 249; `def mutate_state` line 550 with `fcntl.flock(fd, fcntl.LOCK_EX)` line 580; `_migrate_v2_to_v3` defined line 127, registered as `MIGRATIONS[3]` line 157 |
| `system_params.py` | STATE_SCHEMA_VERSION=3; Position TypedDict gains `manual_stop: float \| None` | VERIFIED | 172 lines; `STATE_SCHEMA_VERSION: int = 3` line 111 (was 2); `manual_stop: float \| None` field on Position TypedDict line 162 (after atr_entry); docstring extended (line 150) |
| `sizing_engine.py` | get_trailing_stop reads `position.get('manual_stop')` AFTER NaN guard, BEFORE direction switch | VERIFIED | 688 lines; `manual = position.get('manual_stop')` line 243 (between NaN guard at line 240 and LONG/SHORT switch); `if manual is not None: return manual` precedence; HR-03 `step()` v3 schema includes `'manual_stop': None` in Position dict construction (line 580-582); `check_stop_hit` docstring documents D-15 intentional non-honoring (line 292-299) |
| `main.py` | Daily loop save sites migrated from save_state to mutate_state (W3 invariant: 2 mutate_state calls per run) | VERIFIED | `state_manager.mutate_state(_apply_daily_run)` line 1310; `state_manager.mutate_state(_apply_warning_flush)` line 589; W3 regression test in test_main.py covers count |
| `dashboard.py` | HTMX 1.9.12 SRI pinned; per-tbody grouping; 3 forms; manual badge; parity helper using `is None` (HR-02); confirmation banner slot; CR-01 json-enc | VERIFIED | 1531 lines; HTMX SRI hash `sha384-ujb1lZYygJmzgSwoxRggbCHcjc0rB2XoQrxeTUQyRjrOnlCoYta87iKBWq3EsdM2` (line 123); json-enc extension URL+SRI (lines 134-135); `_compute_trail_stop_display` uses `if manual is not None: return manual` (line 751, HR-02 parity with sizing_engine); `_render_open_form` (line 923+); per-tbody grouping `id="position-group-{X}"` (10 occurrences); 3 manual badge usages; `<div id="confirmation-banner">` slot (line 1428) |
| `tests/fixtures/state_v2_no_manual_stop.json` | v2-schema fixture with no manual_stop key on positions | VERIFIED | schema_version=2; `manual_stop` absent on both SPI200 and AUDUSD positions; `initial_account` + `contracts` keys present (Phase 8 v2 invariants) |
| `tests/test_web_trades.py` | 13+ test classes with 70+ tests covering D-01..D-13, REVIEWS HIGH #1/2/3 + LOW #8/9/10 | VERIFIED | 1269 lines (plan min 600); 16 test classes; 76 tests; 76/76 pass (was target 13 skeletons in Wave 0, fully populated in Wave 2) |
| `tests/test_dashboard.py` | TestRenderDashboardHTMXVendorPin + TestRenderPositionsTableHTMXForm + TestRenderManualStopBadge + TestAuthHeaderPlaceholder populated | VERIFIED | 1641 lines (plan min 1180); 24/24 Phase 14 tests pass (TestRenderDashboardHTMXVendorPin 6 + TestRenderPositionsTableHTMXForm 8 + TestRenderManualStopBadge 6 + TestAuthHeaderPlaceholder 3 + 1 extra HTMX test) |
| `tests/test_state_manager.py` | TestFcntlLock + TestMutateState + TestSchemaMigrationV2ToV3 populated | VERIFIED | 15/15 Phase 14 tests pass (TestFcntlLock 4 + TestMutateState 5 + TestSchemaMigrationV2ToV3 6 — including idempotency, round-trip, preserves-existing, none-position-stays-none) |
| `tests/test_sizing_engine.py` | TestManualStopOverride populated | VERIFIED | All sizing_engine tests pass; manual_stop precedence + NaN passthrough + missing-key + LONG/SHORT independence all locked |

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `web/app.py::create_app` | `web.routes.trades.register` | module-top import + register() call | VERIFIED | `from web.routes import trades as trades_route` (line 42); `trades_route.register(application)` (line 102) |
| `web/app.py::create_app` | `RequestValidationError` handler | `application.add_exception_handler` | VERIFIED | Lines 106-109 register `_validation_exception_handler` for the 422->400 remap |
| `web/routes/trades.py::open_trade` | `sizing_engine.check_pyramid` | local import inside handler | VERIFIED | `from sizing_engine import check_pyramid` line 467 (LOCAL inside handler per Phase 11 C-2) |
| `web/routes/trades.py::close_trade` | `state_manager.record_trade` | local import + record_trade(state, trade) | VERIFIED | `from state_manager import mutate_state, record_trade` line 553; `record_trade(state, trade)` called inside `_apply` mutator (line 596) |
| `state_manager._atomic_write` | state.json on disk | fcntl.flock(fd, fcntl.LOCK_EX) | VERIFIED | line 249 acquires; line 253 releases LOCK_UN |
| `state_manager.mutate_state` | load + save | lock around full read-modify-write | VERIFIED | line 550 def; lines 580/587 acquire/release flock spans the load->mutator->save critical section (REVIEWS HIGH #1) |
| `main.run_daily_check` | `state_manager.mutate_state` | daily loop save sites migrated | VERIFIED | Line 1310 `state_manager.mutate_state(_apply_daily_run)`; line 589 `state_manager.mutate_state(_apply_warning_flush)` |
| `state_manager._migrate` | `_migrate_v2_to_v3` | MIGRATIONS[3] dispatch | VERIFIED | Line 157: `3: _migrate_v2_to_v3` registered in MIGRATIONS dict |
| `system_params.Position` | state.json positions[*] dicts | TypedDict structural shape; backfilled by _migrate_v2_to_v3 on load | VERIFIED | Line 162 `manual_stop: float \| None` field; backfill verified by TestSchemaMigrationV2ToV3 round-trip |
| `sizing_engine.get_trailing_stop` | `system_params.Position.manual_stop` | `position.get('manual_stop')` defensive subscript | VERIFIED | Line 243; defensive .get() handles pre-migration positions |
| `dashboard._compute_trail_stop_display` | `sizing_engine.get_trailing_stop` precedence | identical position.get(manual_stop) precedence block | VERIFIED | Line 751; bit-identical to sizing_engine ordering (NaN guard -> manual override -> LONG/SHORT switch) per CLAUDE.md hex-lite lockstep rule |
| `dashboard._render_html_shell` | HTMX 1.9.12 CDN | `<script src=...htmx@1.9.12 integrity=sha384-ujb1lZ...>` | VERIFIED | Lines 1414-1415; SRI hash matches plan + summary verbatim |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|---|---|---|---|---|
| `web/routes/trades.py::open_trade` | `state['positions'][instrument]` | `_build_position_dict` from validated request + `state['signals'][inst]['last_scalars']['atr']` | Yes | FLOWING — verified by `test_open_long_happy_path` mutating real fixture state |
| `web/routes/trades.py::close_trade` | `state['trade_log']`, `state['account']`, `state['positions'][inst]=None` | `record_trade(state, trade)` from real `state_manager` | Yes | FLOWING — `TestCloseTradePnLMath` proves trade_log grows by 1, account moves by net_pnl |
| `web/routes/trades.py::modify_trade` | `pos['manual_stop']`, `pos['n_contracts']`, `pos['pyramid_level']` | Pydantic-validated request + `model_fields_set` for absent-vs-null | Yes | FLOWING — `TestModifyTradeEndpoint::test_modify_sets_manual_stop` confirms write to position dict |
| `dashboard._render_positions_table` | per-position rows with manual_stop badge | `state['positions']` + `_compute_trail_stop_display(pos)` | Yes | FLOWING — `TestRenderManualStopBadge::test_displayed_value_equals_manual_stop_not_computed` proves operator override surfaces (e.g. $7,700 NOT $7,950 computed) |
| `web/routes/dashboard.py::get_dashboard` | placeholder-substituted dashboard.html bytes | `Path(_DASHBOARD_PATH).read_bytes().replace(_PLACEHOLDER, secret)` | Yes | FLOWING — `TestAuthSecretPlaceholderSubstitution` (5 tests) proves on-disk has placeholder + served bytes have real secret |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Phase 14 test suites all green | `pytest tests/test_web_trades.py tests/test_state_manager.py tests/test_sizing_engine.py tests/test_dashboard.py tests/test_web_dashboard.py tests/test_web_healthz.py -q` | 430 passed in 1.84s | PASS |
| Full test suite green except documented baseline | `pytest -q` | 1074 passed, 16 failed in 94.93s | PASS — 16 failures are pre-existing test_main.py weekend-skip baseline (Apr 26 = Sunday, weekday=6); documented in deferred-items.md |
| TRADE-06 sole-writer grep | `grep -c "state\['warnings'\]" web/routes/trades.py` | 0 | PASS |
| D-05 anti-pitfall grep | `grep -c "compute_unrealised_pnl" web/routes/trades.py` | 0 | PASS |
| HTMX SRI hash present | `grep -c "sha384-ujb1lZYygJmzgSwoxRggbCHcjc0rB2XoQrxeTUQyRjrOnlCoYta87iKBWq3EsdM2" dashboard.py` | 1 | PASS |
| json-enc extension wired | `grep -c "json-enc" dashboard.py` | 6 | PASS |
| Per-tbody grouping | `grep -c "position-group-" dashboard.py` | 10 | PASS |
| Confirmation banner slot | `grep -c "id=\"confirmation-banner\"" dashboard.py` | 2 | PASS |
| Pydantic extra='forbid' on all 3 models | `grep -c "ConfigDict(extra='forbid')" web/routes/trades.py` | 3 | PASS (HR-01) |
| Live POST validation smoke | `client.post('/trades/open', json={'instrument':'BTC',...})` | 400 with `{"errors":[{"field":"instrument","reason":"..."}]}` | PASS |

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|---|---|---|---|---|
| TRADE-01 | 14-01, 14-04 | POST /trades/open accepts `{instrument, direction, entry_price, contracts, executed_at?}` and appends an open position to state.positions | SATISFIED | `web/routes/trades.py:462-548` open_trade; `TestOpenTradeEndpoint` (6 tests) + `TestOpenPyramidUp` (5) + `TestOpenAdvancedFields` (8) all pass |
| TRADE-02 | 14-01, 14-04 | Request validation: `instrument ∈ {SPI200, AUDUSD}`, `direction ∈ {LONG, SHORT}`, `entry_price > 0` and finite, `contracts ≥ 1` integer; returns 400 with field-level errors on violation | SATISFIED | Pydantic v2 Literal enums + Field constraints + `_coherence` validator + 422->400 remap; `TestErrorResponses` (4) + `TestExtraFieldsForbidden` (3) + `TestRequestValidationErrorRemap` (2) all pass |
| TRADE-03 | 14-01, 14-04 | POST /trades/close accepts `{instrument, exit_price, executed_at?}` and appends to state.trade_log with realised P&L + updates state.account | SATISFIED | `web/routes/trades.py:550-614` close_trade calls record_trade; `TestCloseTradeEndpoint` (5) + `TestCloseTradePnLMath` (3) all pass — including the AST guard that forbids `compute_unrealised_pnl` (D-05 anti-pitfall) |
| TRADE-04 | 14-01, 14-03, 14-04 | POST /trades/modify accepts `{instrument, new_stop?, new_contracts?}` to manually adjust trailing stop or size | SATISFIED | `web/routes/trades.py:616-649` modify_trade with Pydantic v2 model_fields_set; sizing_engine.get_trailing_stop honors manual_stop precedence; dashboard.py mirrors precedence in lockstep; `TestModifyTradeEndpoint` (10) + `TestModifyAbsentVsNull` (3) + `TestManualStopOverride` (sizing_engine) all pass |
| TRADE-05 | 14-01, 14-05 | Dashboard at GET / includes HTMX-powered forms for open/close/modify (no full page reload; POSTs return partial HTML fragments) | SATISFIED | `dashboard.py:_render_open_form` + per-row Close/Modify buttons; HTMX 1.9.12 SRI-pinned; json-enc extension SRI-pinned (CR-01); per-tbody grouping (REVIEWS HIGH #3); 24 dashboard tests + 7 HTMX response tests all pass |
| TRADE-06 | 14-01, 14-02, 14-04 | Every mutation endpoint goes through `state_manager.save_state()` (now `mutate_state` per D-13); endpoints never touch `state['warnings']` directly | SATISFIED | All 3 POST handlers use `mutate_state(_apply)` (16 mentions in trades.py source); `TestSoleWriterInvariant` AST walks Assign + Call + AugAssign branches with positive-control test; `TestSaveStateInvariant` confirms exactly-one-mutation discipline (D-11 atomic) |

**Coverage:** 6/6 requirements satisfied. No orphaned requirements (all TRADE-XX claimed by plans 14-01..14-05).

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|---|---|---|---|---|
| (none found) | — | — | — | Source files for Phase 14 (web/routes/trades.py, dashboard.py, state_manager.py, sizing_engine.py, system_params.py, main.py, web/app.py, web/routes/dashboard.py) scanned for TODO/FIXME/PLACEHOLDER/empty-handler/static-empty-return patterns. Zero blocker findings. The 13 MEDIUM/LOW codemoot/REVIEWS findings are intentionally deferred to Phase 16 hardening per workflow defaults (documented in 14-REVIEWS.md). All 4 critical+high findings (CR-01 HTMX json-enc, HR-01 extra='forbid', HR-02 is None parity, HR-03 step() v3 schema) are FIXED in source as verified above. |

### Human Verification Required

See `human_verification:` frontmatter (5 items) — all are real-browser HTMX behavior, real-droplet fcntl cross-process semantics, real-droplet schema migration on deployed v2 state.json, real-browser inline error rendering, and operator UX evaluation of the 2-stage destructive close flow. None are blockers for closing Phase 14; all are operator-facing acceptance tests for the live droplet rollout per VALIDATION.md §Manual-Only Verifications.

### Gaps Summary

No gaps blocking phase goal achievement. All 6 ROADMAP success criteria verified by direct code inspection + endpoint smoke + 430 passing automated tests across 6 Phase 14 suites. The full pytest suite reports 1074 passing tests + 16 baseline failures (pre-existing test_main.py weekend-skip on Apr 26 Sunday — documented in STATE.md Deferred Items, out of Phase 14 scope).

Phase 14 is structurally complete. The 5 human-verification items are operator-facing acceptance tests that cannot be exercised in TestClient (real browser HTMX runtime, real cross-process flock on the droplet, real disk-resident v2 state.json migration, real browser inline error rendering, and subjective UX evaluation). They are documented in `14-VALIDATION.md` Manual-Only section as the expected hand-off for the deploy stage; they do not block closing the phase.

---

_Verified: 2026-04-25T11:30:00Z_
_Verifier: Claude (gsd-verifier)_
