---
phase: 08-hardening-warning-carry-over-stale-banner-crash-email-config
verified: 2026-04-23T11:00:00Z
status: passed
score: 7/7 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: none
  previous_score: null
  gaps_closed: []
  gaps_remaining: []
  regressions: []
---

# Phase 8: Hardening — Warning Carry-over, Stale Banner, Crash Email, Configurable Account — Verification Report

**Phase Goal:** Close the "looks done but isn't" gap — make sure warnings from any run surface in the next email, a dead scheduler is loudly visible, corrupt-state recovery is announced to the operator, any unhandled exception attempts one last crash email before exit, AND the operator can configure starting account + contract-size tiers at `--reset` time so the system works for real broker situations (not just SPI mini + $100k).

**Verified:** 2026-04-23T11:00:00Z (initial verification, post-execution)
**Status:** passed
**Test suite:** 653 passed / 0 failed (matches SUMMARY baseline)

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth (Success Criterion) | Status | Evidence |
|---|----|----|----|
| SC-1 | Warnings appended in run N surface as banner in run-(N+1) email, then cleared after dispatch | VERIFIED | `notifier._render_header_email` routine-row age filter at notifier.py:631-672; `main._dispatch_email_and_maintain_warnings` clears + appends + saves at main.py:270-336; `state_manager.clear_warnings` at state_manager.py:446-468. Behavioral spot-check: routine row rendered when `w['date']==prior_run_date`; `clear_warnings` empties list after happy-path dispatch. Test evidence: `TestWarningCarryOverFlow::test_dispatch_ok_clears_warnings_no_append` + `test_dispatch_failed_5xx_warning_B_present_after_clear` (both PASS). |
| SC-2 | `last_run` > 2 days old triggers stale banner + `[!]` subject prefix | VERIFIED | `main.STALENESS_DAYS_THRESHOLD=2` at main.py:93; `main._maybe_set_stale_info` at main.py:246-267 sets transient `state['_stale_info']`; `notifier._has_critical_banner` at notifier.py:532-548 reads `_stale_info`; `compose_email_subject` prepends `[!]` when `has_critical_banner=True` at notifier.py:375-376. Red-border banner (`border-left:4px solid {_COLOR_SHORT}`) at notifier.py:584-598. Behavioral spot-check: 5-day staleness renders "━━━ Stale state ━━━" + "5 days" + `[!]` in subject. Test: `TestWarningCarryOverFlow::test_stale_info_popped_before_save`. |
| SC-3 | Unhandled exception fires crash email with last-known state summary; exits non-zero | VERIFIED | `main._LAST_LOADED_STATE` module cache declared at main.py:102, written at main.py:829-830 immediately after `state_manager.load_state()`. Outer `except Exception` at main.py:1315-1338 calls `_send_crash_email(e, state=_LAST_LOADED_STATE)` (NOT `None`) and returns exit code 1. `_send_crash_email` wrapper at main.py:219-239; `_build_crash_state_summary` at main.py:173-216. Spot-check: summary includes `signals:`, `account:`, `positions:` lines; excludes `trade_log` and `warnings`. Nested try/except at main.py:1323-1337 prevents crash-email failure masking exit code. Test: `TestCrashEmailBoundary::test_crash_email_includes_last_loaded_state` + `test_crash_email_dispatch_failure_does_not_mask_exit_code` + `test_layer_b_once_mode_unexpected_exception_fires_crash_email`. |
| SC-4 | Corrupt state.json recovery surfaces a gold banner with backup filename | VERIFIED | `state_manager.load_state` JSONDecodeError branch at state_manager.py:354-375 appends `'recovered from corruption; backup at {backup_name}'` via `append_warning`. `notifier._has_critical_banner` at notifier.py:542-547 matches prefix `'recovered from corruption'` with age-filter BYPASS. Gold-border banner (`border-left:4px solid {_COLOR_FLAT}`) at notifier.py:611-625 with "━━━ State was reset ━━━" label. Behavioral spot-check: warning dated 5 days earlier than prior_run still classified critical and rendered. Test: `TestCorruptionRecovery` (unchanged, still green) + `TestHeaderBanner::test_corrupt_reset_banner_gold_border_age_bypass`. |
| SC-5 | Resend 5xx logs + continues, next-run surfaces notifier warning | VERIFIED | `notifier.send_daily_email` at notifier.py:1340-1418 returns `SendStatus(ok=False, reason=...)` on every failure path; never crashes. `_dispatch_email_and_maintain_warnings` at main.py:326-331 translates `status.ok=False` (when reason != 'no_api_key') into `state_manager.append_warning(source='notifier', message=f'Previous email send failed: {reason}')`. Behavioral spot-check: simulated 503 returned SendStatus(ok=False, reason contains '503'); orchestrator then appended `notifier`-sourced warning with correct message. Test: `TestSendDispatchStatusTuple::test_send_dispatch_5xx_returns_ok_false_with_500_in_reason` + `TestWarningCarryOverFlow::test_dispatch_failed_5xx_warning_B_present_after_clear`. |
| SC-6 | `--reset --initial-account N` persists to `state['initial_account']`; dashboard reads from state; missing key defaults via migration | VERIFIED | `main._handle_reset` at main.py:1065-1227 writes `state['initial_account'] = float(initial_account)` at line 1220 then saves. `dashboard._compute_total_return` at dashboard.py:487-499 uses `state.get('initial_account', INITIAL_ACCOUNT)` as the baseline. `state_manager.MIGRATIONS[2]` at state_manager.py:92-99 silently backfills via `s.get('initial_account', INITIAL_ACCOUNT)` (no `append_warning`, no log). T-08-12 `math.isfinite` guard at main.py:1127 (applies to argparse AND interactive paths — both flow through the single check at line 1127 after `initial_account` is assigned). Minimum-$1,000 at main.py:1134. Behavioral spot-check: `--reset --initial-account 50000 --spi-contract spi-standard --audusd-contract audusd-mini` produced `state.json` with `initial_account=50000.0`, `contracts={'SPI200':'spi-standard','AUDUSD':'audusd-mini'}`, `schema_version=2`. Migration spot-check: v1 state with no `initial_account`/`contracts` silently backfilled to defaults (warnings list remained empty). Tests: `TestResetFlags::test_reset_with_all_three_flags_writes_state` + `TestTotalReturnInitialAccount::test_custom_initial_account_50k_account_75k_returns_plus_50pct` + `TestMigrateV2Backfill::test_v1_state_gets_only_phase8_keys_backfilled` + `test_migrate_v2_appends_no_warning`. |
| SC-7 | `--reset --spi-contract ... --audusd-contract ...` persists tier labels; orchestrator resolves + passes multiplier/cost to sizing; hex-lite preserved | VERIFIED | `main._handle_reset` writes `state['contracts']` at main.py:1221. `state_manager.load_state` materialises runtime-only `state['_resolved_contracts']` at state_manager.py:383-386 via `SPI_CONTRACTS[label]` / `AUDUSD_CONTRACTS[label]` lookups. `state_manager.save_state` strips underscore-prefix keys at state_manager.py:412 — `_resolved_contracts` never written to disk. `main.run_daily_check` per-symbol loop at main.py:862-865 reads `state['_resolved_contracts'][state_key]` and passes `multiplier=multiplier, cost_aud_open=cost_aud_round_trip/2` to `sizing_engine.step()` at main.py:929-938. Equity rollup at main.py:999-1004 uses same resolution pattern. **Hex-lite D-17 invariant: `grep "SPI_CONTRACTS\|AUDUSD_CONTRACTS" sizing_engine.py` → 0 matches (confirmed).** Tier presets defined at `system_params.py` lines 79-88 (SPI_CONTRACTS + AUDUSD_CONTRACTS). Behavioral spot-check: spi-standard label resolved to multiplier=25.0, cost_aud=30.0; audusd-mini to multiplier=1000.0, cost_aud=0.5; save-and-reload preserves labels, strips `_resolved_contracts`. Tests: `TestLoadStateResolvesContracts::test_load_state_resolves_spi_standard_and_audusd_mini` + `TestSaveStateExcludesUnderscoreKeys::test_resolved_contracts_not_persisted` + `TestDeterminism::test_forbidden_imports_absent[module_path1]` (sizing_engine) PASS. |

**Score:** 7/7 success criteria verified.

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `system_params.py` | `SPI_CONTRACTS`, `AUDUSD_CONTRACTS`, `_DEFAULT_SPI_LABEL`, `_DEFAULT_AUDUSD_LABEL`, `STATE_SCHEMA_VERSION=2` | VERIFIED | Lines 79-92 (tier dicts + default labels) + line 100 (`STATE_SCHEMA_VERSION: int = 2`). Scalar constants `SPI_MULT`, `SPI_COST_AUD`, `AUDUSD_NOTIONAL`, `AUDUSD_COST_AUD` preserved (lines 63-68). |
| `state_manager.py` | `MIGRATIONS[2]` v2 backfill, `_REQUIRED_STATE_KEYS` extended, `load_state` materialises `_resolved_contracts`, `save_state` filters underscore keys, `clear_warnings` helper, corrupt-recovery prefix unchanged | VERIFIED | MIGRATIONS[2] lambda lines 92-99 (silent, no `append_warning`); `_REQUIRED_STATE_KEYS` includes `initial_account`+`contracts` at lines 75-80; load_state materialises `_resolved_contracts` at lines 379-386; save_state strips `_`-prefix keys at line 412; `clear_warnings` at lines 446-468; corrupt-recovery prefix `'recovered from corruption; backup at {backup_name}'` at line 371 (UNCHANGED per I1). |
| `notifier.py` | `SendStatus` NamedTuple, `_render_hero_card_email`, `_has_critical_banner`, two-tier `_render_header_email`, `compose_email_subject` with `has_critical_banner` kwarg, `send_daily_email` returns `SendStatus`, `send_crash_email` public, `_post_to_resend` supports `text_body` | VERIFIED | `class SendStatus(NamedTuple)` at line 87; `_render_hero_card_email` at line 482; `_has_critical_banner` at lines 532-548; new `_render_header_email` at lines 551-685 (composes critical banner + hero + routine); `compose_email_subject` with `has_critical_banner: bool = False` at line 304 + `[!]` prefix at lines 375-376; `send_daily_email -> SendStatus` at line 1340; always-writes `last_email.html` BEFORE api_key check at line 1386 (verified D-02 ordering); `send_crash_email -> SendStatus` at line 1421, `[CRASH] Trading Signals — {YYYY-MM-DD}` subject at line 1454, text/plain body at line 1464; `_post_to_resend` with `text_body: str | None = None` kwarg at line 1258 and ValueError when both None at line 1283. |
| `main.py` | `_LAST_LOADED_STATE` cache, `STALENESS_DAYS_THRESHOLD`, `_maybe_set_stale_info`, `_dispatch_email_and_maintain_warnings`, `_build_crash_state_summary`, `_send_crash_email`, `_stdin_isatty`, `_handle_reset` rewrite, argparse CONF flags, `_validate_flag_combo` relaxation | VERIFIED | `_LAST_LOADED_STATE: 'dict | None' = None` at line 102 (cache read 7× per grep); `STALENESS_DAYS_THRESHOLD: int = 2` at line 93; `_maybe_set_stale_info` at lines 246-267 (sets transient key, never appends warning — B3); `_dispatch_email_and_maintain_warnings` at lines 270-336 (B1 canonical order: dispatch → clear → maybe-append → pop → save); `_build_crash_state_summary` at lines 173-216 (excludes trade_log/equity_history/warnings per D-06); `_send_crash_email` wrapper at lines 219-239 (local `import notifier` per C-2); `_stdin_isatty` at lines 535-539; `_handle_reset(args)` wholesale rewrite lines 1065-1227 with Q&A + preview + non-TTY guard + `math.isfinite` + min-$1000; argparse flags `--initial-account` at line 477, `--spi-contract` at line 488, `--audusd-contract` at line 499 (both with `choices=list(system_params.*_CONTRACTS.keys())`); `_validate_flag_combo` relaxed at lines 521-532 (reset-companions allowed). |
| `dashboard.py` | `_compute_total_return` reads `state['initial_account']` | VERIFIED | Line 492: `initial = state.get('initial_account', INITIAL_ACCOUNT)` (D-16 baseline); fallback to `INITIAL_ACCOUNT` only when migration missed the key. Sole call site in dashboard. |

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `main.run_daily_check` | `state['_resolved_contracts']` | `state_manager.load_state()` materialisation | WIRED | main.py:822 loads state; state_manager.py:383-386 materialises `_resolved_contracts`; main.py:862-865 + 1004 read resolved dict; passes `multiplier`/`cost_aud_open` to `sizing_engine.step()` at main.py:929-938. |
| `main._dispatch_email_and_maintain_warnings` | `notifier.send_daily_email` | `_send_email_never_crash` wrapper | WIRED | main.py:304 calls `_send_email_never_crash(state, old_signals, now, is_test)`; wrapper at main.py:136-166 returns `SendStatus` (or None on import failure); `_dispatch_email_and_maintain_warnings` branches on `status is None` (R2) and `status.ok` (main.py:320-331). |
| `main._dispatch_email_and_maintain_warnings` | `state_manager.clear_warnings` / `append_warning` / `save_state` | direct imports | WIRED | Ordered sequence at main.py:313, 321-325, 327-331, 334, 336. B1 ordering verified by regex check + `test_happy_path_save_state_called_exactly_twice` + `test_stale_info_popped_before_save`. |
| `main.main()` outer except | `notifier.send_crash_email` | `_send_crash_email(_LAST_LOADED_STATE)` | WIRED | main.py:1315-1338: outer `except Exception` → logs → nested `try: _send_crash_email(e, state=_LAST_LOADED_STATE)` → `except Exception: logs 'crash-email dispatch also failed'` → `return 1`. `_LAST_LOADED_STATE` populated at main.py:829-830 after `load_state()`. R1 review fix verified: `state=_LAST_LOADED_STATE` NOT `state=None`. |
| `notifier._render_header_email` | `state['_stale_info']` | `state.get('_stale_info')` | WIRED | notifier.py:576 reads; main.py:264 writes; main.py:309 + 334 pop before save (belt-and-suspenders with D-14 underscore filter). |
| `notifier._has_critical_banner` | corrupt-recovery warning prefix | `state['warnings']` iteration | WIRED | notifier.py:542-547 checks `source='state_manager'` AND `message.startswith('recovered from corruption')`; matches state_manager.py:371 prefix verbatim. Age-filter bypass at notifier.py:604-625 renders banner regardless of warning date. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|---|---|---|---|---|
| `notifier._render_header_email` | `state['warnings']`, `state['_stale_info']` | `main._dispatch_email_and_maintain_warnings` consumes state that has `_stale_info` set by `_maybe_set_stale_info` and `warnings` populated by `append_warning` during prior-run failures | Yes — behavioral spot-checks confirmed both transient key + persisted warnings flow through to rendered HTML with expected banner colours, labels, and messages | FLOWING |
| `dashboard._compute_total_return` | `state['initial_account']`, `state['account']`, `state['equity_history']` | written by `main._handle_reset` (initial_account) + run_daily_check equity rollup (account, equity_history) | Yes — behavioral spot-check with custom initial_account=50000 produced correct +50% return formula evidence | FLOWING |
| `main._build_crash_state_summary` | `_LAST_LOADED_STATE.signals / .account / .positions` | populated at main.py:829-830 inside run_daily_check immediately after load_state | Yes — behavioral spot-check with fully populated state rendered signals+account+positions lines; with `state=None` rendered sentinel placeholder | FLOWING |
| `main.run_daily_check` tier pass-through | `state['_resolved_contracts'][state_key]['multiplier'/'cost_aud']` | `state_manager.load_state` materialisation at lines 383-386 | Yes — behavioral spot-check with spi-standard confirmed multiplier=25.0, cost_aud=30.0 resolved; audusd-mini resolved 1000.0/0.5 | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command / Scenario | Result | Status |
|---|---|---|---|
| Full test suite baseline | `python -m pytest tests/ -q` | 653 passed in 93.50s | PASS |
| Phase 8 test classes (104 tests) | `pytest tests/test_main.py::TestWarningCarryOverFlow [+18 more classes]` | 104 passed in 70.66s | PASS |
| SC-1 routine warning carry-over render | `_render_header_email` with warning dated `prior_run_date` | "warning from prior run" + message rendered; `_has_critical_banner=False` | PASS |
| SC-1 warnings cleared after happy dispatch | `_dispatch_email_and_maintain_warnings` with SendStatus(ok=True) | `state['warnings'] == []` post-call | PASS |
| SC-2 stale banner via `_stale_info` | `_stale_info={'days_stale':5,...}` | "━━━ Stale state ━━━" + "5 days" in HTML; `[!]` in subject; `_has_critical_banner=True` | PASS |
| SC-4 corrupt banner age-filter bypass | `warning(date=2026-04-18, prefix='recovered from corruption')` with `last_run=2026-04-22` | "━━━ State was reset ━━━" rendered; backup filename present; `_has_critical_banner=True` despite old date | PASS |
| SC-3 crash summary with state | `_build_crash_state_summary(state_with_position)` | Contains `signals: SPI200=LONG, AUDUSD=FLAT`, `account: $125,000.00`, `positions:` with `SPI200: LONG 3@7800.0`; excludes trade_log/warnings | PASS |
| SC-3 crash summary state=None | `_build_crash_state_summary(None)` | `(state not loaded — crash before load_state)` placeholder | PASS |
| SC-5 Resend 503 → SendStatus | `send_daily_email` with mocked 503 response | `SendStatus(ok=False, reason='Exception: HTTP 503')` | PASS |
| SC-5 orchestrator translation | `_dispatch_email_and_maintain_warnings` with ok=False | appended `source='notifier'`, message `'Previous email send failed: HTTP 503: retry later'` | PASS |
| SC-6 `--reset --initial-account 50000 --spi-contract spi-standard --audusd-contract audusd-mini` | `_handle_reset` with RESET_CONFIRM=YES | `state.json` written: `initial_account=50000.0`, `contracts={'SPI200':'spi-standard','AUDUSD':'audusd-mini'}`, `schema_version=2` | PASS |
| SC-7 tier resolution in load_state | `load_state` on state with `contracts={'SPI200':'spi-standard','AUDUSD':'audusd-mini'}` | `_resolved_contracts['SPI200']={'multiplier':25.0,'cost_aud':30.0}`, `['AUDUSD']={'multiplier':1000.0,'cost_aud':0.5}` | PASS |
| SC-7 underscore filter on save | `save_state(state_with_resolved)` then re-read JSON | `_resolved_contracts` absent from disk; `contracts` labels preserved | PASS |
| SC-7 silent v1→v2 migration | load v1-shaped state missing `initial_account` + `contracts` | Defaults backfilled; `warnings == []` (silent) | PASS |
| R1 crash handler passes `_LAST_LOADED_STATE` | Inspect main.py:1332 | `_send_crash_email(e, state=_LAST_LOADED_STATE)` (NOT None) | PASS |
| R2 `status is None` branch | `_dispatch_email_and_maintain_warnings` with mocked `_send_email_never_crash` returning None | appended warning contains `'import or runtime error'` | PASS |
| Hex-lite D-17: `sizing_engine` tier-free | `grep 'SPI_CONTRACTS\|AUDUSD_CONTRACTS' sizing_engine.py` | 0 matches | PASS |
| state_manager sole writer to `warnings` | `grep "state\['warnings'\]\s*=\|state\['warnings'\]\.append"` across prod code | Only state_manager.py:443 (append) + :467 (clear); zero in main.py/notifier.py/dashboard.py | PASS |
| Per-run save count = 2 | `grep "state_manager\.save_state" main.py` | 3 call sites (run_daily_check:1036, dispatch helper:336, _handle_reset:1222 separate) → per-run exactly 2 (W3) | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|---|---|---|---|---|
| **NOTF-10** | 08-02-PLAN | Warnings from previous run carry over into next email header | SATISFIED | SC-1 evidence above; `TestHeaderBanner` + `TestWarningCarryOverFlow` both green. REQUIREMENTS.md line 109 marked `[x]`. |
| **ERR-02** | 08-02-PLAN / 08-03-PLAN | Resend API failure logged + does not crash | SATISFIED | SC-5 evidence above; `send_daily_email` returns SendStatus on all paths; orchestrator appends warning on failure. REQUIREMENTS.md line 153 `[x]`. |
| **ERR-03** | 08-01-PLAN / 08-02-PLAN | Corrupt state.json backed up + reinitialised with next-email warning | SATISFIED | SC-4 evidence above; prefix `'recovered from corruption'` unchanged at state_manager.py:371; gold banner + age-bypass classifier in notifier. REQUIREMENTS.md line 155 `[x]`. |
| **ERR-04** | 08-02-PLAN / 08-03-PLAN | Top-level `except Exception` wraps run; attempts crash email then non-zero exit | SATISFIED | SC-3 evidence above; main.py:1315-1338 outer except + nested try for crash-email + return 1. REQUIREMENTS.md line 157 `[x]`. |
| **ERR-05** | 08-03-PLAN | `last_run > 2 days` → stale state banner | SATISFIED | SC-2 evidence above; `STALENESS_DAYS_THRESHOLD=2` + `_maybe_set_stale_info` + `_has_critical_banner` + red-border banner. REQUIREMENTS.md line 159 `[x]`. |
| **CONF-01** | 08-01-PLAN / 08-03-PLAN | `--initial-account` CLI flag persisted + read by dashboard + backward-compat migration | SATISFIED | SC-6 evidence above; `_handle_reset` writes, `_compute_total_return` reads, `MIGRATIONS[2]` silently backfills, `math.isfinite` + min-$1000 validation. REQUIREMENTS.md line 165 `[x]`. |
| **CONF-02** | 08-01-PLAN / 08-03-PLAN | `--spi-contract`/`--audusd-contract` persisted as tier labels, orchestrator resolves and passes multiplier+cost to sizing | SATISFIED | SC-7 evidence above; tier dicts in system_params; `_resolved_contracts` materialised by load_state, stripped by save_state; `sizing_engine.step` receives explicit multiplier/cost_aud_open (hex D-17 preserved). REQUIREMENTS.md line 167 `[x]`. |

No orphaned requirements — all 7 requirement IDs declared in plan frontmatter map to satisfied implementations.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|---|---|---|---|---|
| — | — | No TODO/FIXME/HACK/XXX in Phase 8 production code | — | Clean. |
| main.py | 180, 1330 | "placeholder" string literal | Info | Benign — text in docstring describing graceful-degradation sentinel for `state=None`, not a code stub. |
| notifier.py | 308, 352 | "X,XXX" / "XXXX.XX" template-like strings | Info | Benign — subject-line documentation comment, not rendered output. |
| dashboard.py | 667, 746, 879 | "placeholder" string | Info | Benign — empty-state UI placeholders (empty positions/trades/equity_history render placeholder rows per F-4/D-13). Not Phase 8 additions. |

No blockers, no warnings. No empty implementations (`return null`, `return {}`, empty handlers, only-`console.log` bodies) anywhere in Phase 8 code.

### Architectural Invariants

| Invariant | Check | Status |
|---|---|---|
| Hex-lite D-17: `sizing_engine` has no tier-dict imports | `grep "SPI_CONTRACTS\|AUDUSD_CONTRACTS" sizing_engine.py` → 0 matches | PASS |
| `signal_engine` ↔ `state_manager` no cross-import | Neither module imports the other | PASS |
| `state_manager` sole writer to `state['warnings']` | Only `append_warning` (line 443) and `clear_warnings` (line 467) write; main.py/notifier.py/dashboard.py have zero `state['warnings'] =` / `.append` | PASS |
| Atomic state writes preserved | `save_state` → `_atomic_write` (tempfile + fsync(file) + os.replace + fsync(dir)) at state_manager.py:106-151; D-14 underscore filter applied in-memory (no mutation of input state) at line 412 | PASS |
| Per-run `save_state` count = 2 (W3) | run_daily_check step 9 (main.py:1036) + `_dispatch_email_and_maintain_warnings` post-dispatch (main.py:336) = 2. `_handle_reset` at main.py:1222 is a separate CLI path (not daily run). | PASS |
| `_LAST_LOADED_STATE` cache populated + read | main.py:829-830 writes inside run_daily_check after load_state; main.py:1332 reads in outer except handler. Grep count = 7 | PASS |
| `notifier` module hex-boundary | `_render_header_email` reads `state['_stale_info']` + `state['warnings']` as dict contract only; does NOT call `state_manager.append_warning` / `clear_warnings`. Module-level `from state_manager import load_state` at line 60 scoped to `__main__` CLI preview only (line 1513). Production `send_daily_email` has no state_manager calls. | PASS |
| Schema v2 round-trip | `STATE_SCHEMA_VERSION=2` in system_params; `MIGRATIONS[2]` backfills v1→v2 silently; `_REQUIRED_STATE_KEYS` includes `initial_account`+`contracts`; save/load round-trips both keys | PASS |
| D-14 runtime-only keys stripped on save | `_resolved_contracts` + `_stale_info` + any `_`-prefixed key excluded from `json.dumps` via save_state filter at state_manager.py:412; in-memory dict NOT mutated | PASS |
| Corrupt-recovery prefix unchanged (I1) | state_manager.py:371: `'recovered from corruption; backup at {backup_name}'` — unchanged from Phase 3; Plan 02 classifier at notifier.py:545 matches this exact prefix. | PASS |

### Review-Driven Changes (R1 + R2)

| Review | Fix | Evidence |
|---|---|---|
| **R1** (Codex MEDIUM on SC-3): crash email should include last-known state summary, not None | `_LAST_LOADED_STATE` module cache added at main.py:102, written at main.py:829-830 inside `run_daily_check` after `load_state()`, read by outer except at main.py:1332 as `_send_crash_email(e, state=_LAST_LOADED_STATE)`. If crash occurs BEFORE `load_state()` returns, cache is still None and `_build_crash_state_summary` returns `'(state not loaded — crash before load_state)'` sentinel. | PASS — behavioral spot-check confirmed: crash summary with populated state renders signals/account/positions; with `None` renders sentinel placeholder. Test `TestCrashEmailBoundary::test_crash_email_includes_last_loaded_state` PASS. |
| **R2** (Codex MEDIUM): silent-skip `status is None` branch must append notifier warning so operator sees failure next run | `_dispatch_email_and_maintain_warnings` at main.py:320-325: `if status is None: state_manager.append_warning(state, source='notifier', message='Previous email dispatch failed to return status (import or runtime error)', now=now)`. Grep count: `status is None` → 1 match, `'import or runtime error'` → 1 match. | PASS — behavioral spot-check confirmed: patching `_send_email_never_crash` to return None results in single appended warning with source='notifier' and message containing 'import or runtime error'. Test `TestWarningCarryOverFlow::test_dispatch_status_none_appends_warning` PASS. |

### Human Verification Required

None. All 7 success criteria are independently testable with deterministic code; all behavioral spot-checks passed without requiring visual inspection of live emails, real Resend API calls, or manual operator interaction. The Phase 8 surface is 100% automatable because:

- Email content is rendered HTML (grep-able for banner markers, subject prefixes, escape patterns).
- Resend 5xx, timeouts, and HTTP failures are fully mocked via `patch('notifier.requests.post', return_value=...)`.
- Crash-email dispatch path is exercised via patched `notifier.send_crash_email`.
- CLI flag parsing + interactive Q&A paths exercised with `monkeypatch` on `input()` + `_stdin_isatty()`.
- Schema migration tested with fixture state dicts + `_migrate()` direct call.

No live end-to-end validation (send a real email and eyeball the banner) is required — the rendered HTML has been behaviorally verified and Phase 6 operator UAT remains valid for the unchanged parts of the email layout.

### Gaps Summary

**No gaps found.** Every ROADMAP success criterion maps to concrete code, tests are green, hex-lite architectural invariants are preserved, and the R1 + R2 review-driven amendments are both verifiably present in the delivered code.

The codebase delivers the Phase 8 goal: warning carry-over works and is cleared post-dispatch; stale state is visible via red banner + `[!]` subject; crash-email fires with last-known state summary on unhandled exception; corrupt-state recovery is classified as critical with age-filter bypass; Resend 5xx is logged + surfaces on the next run; `--initial-account` + contract-tier flags persist and flow through to dashboard + sizing with backward-compat migration.

---

_Verified: 2026-04-23T11:00:00Z_
_Verifier: Claude (gsd-verifier) — Phase 8 initial verification_
