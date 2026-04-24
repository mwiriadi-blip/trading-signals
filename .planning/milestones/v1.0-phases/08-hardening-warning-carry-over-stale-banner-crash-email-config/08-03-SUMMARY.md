---
phase: 08
plan: 03
subsystem: orchestrator-cli-crash-boundary
tags: [phase-8, main, dashboard, sendstatus-consumer, stale-info, crash-email, conf-flags, interactive-reset, layer-b]
requires:
  - state_manager.clear_warnings (Plan 01)
  - state_manager.append_warning (Plan 01 — unchanged)
  - state_manager.load_state with _resolved_contracts materialisation (Plan 01)
  - system_params.SPI_CONTRACTS, AUDUSD_CONTRACTS, INITIAL_ACCOUNT (Plan 01)
  - system_params._DEFAULT_SPI_LABEL, _DEFAULT_AUDUSD_LABEL (Plan 01)
  - notifier.SendStatus NamedTuple (Plan 02)
  - notifier.send_daily_email returning SendStatus (Plan 02)
  - notifier.send_crash_email (Plan 02)
  - existing 'recovered from corruption' warning prefix in state_manager (Plan 01, unchanged)
provides:
  - main._LAST_LOADED_STATE module-level cache (review R1 — SC-3 completeness)
  - main._maybe_set_stale_info (B3 transient key setter)
  - main._dispatch_email_and_maintain_warnings (B1 canonical ordering helper)
  - main._build_crash_state_summary (D-06 bounded text/plain state snapshot)
  - main._send_crash_email (wrapper around notifier.send_crash_email)
  - main._stdin_isatty (D-13 test-patchable wrapper)
  - main._handle_reset rewritten with Q&A + preview + non-TTY guard + isfinite
  - main.STALENESS_DAYS_THRESHOLD constant
  - argparse CONF flags: --initial-account, --spi-contract, --audusd-contract
  - dashboard._compute_total_return reads state['initial_account'] (D-16)
affects:
  - tests/test_main.py — 39 new tests + 4 Phase 6 fakes migrated to SendStatus
  - tests/test_scheduler.py — 2 new TestCrashEmailLayerB tests + 1 _handle_reset signature update
  - tests/test_dashboard.py — 3 new TestTotalReturnInitialAccount tests
tech-stack:
  added: []
  patterns:
    - module-level mutable cache written inside orchestrator + read by crash handler (single-threaded safety)
    - Transient state keys popped by the setter-adjacent helper + D-14 underscore filter belt-and-suspenders
    - Argparse `choices=` whitelist for enum-like string flags (spi-mini/spi-standard/spi-full)
    - Non-TTY guard via test-patchable wrapper mirroring Phase 7 `_get_process_tzname`
    - Nested try/except around secondary-network I/O to preserve primary exit code
key-files:
  created:
    - .planning/phases/08-hardening-warning-carry-over-stale-banner-crash-email-config/08-03-SUMMARY.md
  modified:
    - main.py (921 → 1342, +421)
    - dashboard.py (_compute_total_return body rewritten, +4 net lines)
    - tests/test_main.py (1161 → 1922, +761)
    - tests/test_scheduler.py (659 → 716, +57)
    - tests/test_dashboard.py (971 → 1011, +40)
decisions:
  - "Module-level _LAST_LOADED_STATE cache chosen over passing state through the scheduler loop — simpler + proven safe for single-threaded GHA/Replit paths (review R1)"
  - "_dispatch_email_and_maintain_warnings owns the dispatch+clear+append+save sequence so B1 ordering is enforced in one place; main() and --force-email path both go through it"
  - "--test path still enters _dispatch_email_and_maintain_warnings so operator sees preview mail, but persist=False skips save_state + warning mutation (CLI-01 structural read-only preserved)"
  - "math.isfinite guard applied on BOTH argparse-flag and interactive-Q&A paths so T-08-12 is closed regardless of invocation surface"
  - "Interactive Q&A accepts 'q' at any prompt; EOFError on input() treated as implicit 'q' (matches Phase 4 _handle_reset cancel semantics)"
  - "Preview block includes CURRENT state.json (when readable) alongside new values so operator can catch accidental destructive resets"
  - "Crash-email nested try/except ensures a failing secondary dispatch does not mask the original exit code (always rc=1)"
metrics:
  tasks: 3
  commits: 3
  test-suite-before: 609
  test-suite-after: 653
  new-tests: 44  # 20 Task 2 + 24 Task 3 + 0 Task 1 (smoke only)
  updated-existing-tests: 6  # 4 Phase-6 fakes + 1 _handle_reset signature + 1 reset-flags
  duration-minutes: ~60
  completed: 2026-04-23
---

# Phase 8 Plan 03: Orchestrator + CLI + Crash-Email Wiring — Summary

One-liner: wires `main.py` + `dashboard.py` to consume Plan 01's state_manager interfaces and Plan 02's `SendStatus`/`send_crash_email`, closing all 7 Phase 8 ROADMAP success criteria via transient `_stale_info`, B1 canonical dispatch ordering, tier-resolution pass-through, CONF CLI flags with interactive Q&A, and a crash-email boundary that carries the last-loaded state.

## Task 1 — Orchestrator SendStatus consumer + staleness via `_stale_info` + B1 canonical dispatch + tier resolution + dashboard D-16 (commit `e936b49`)

### `main.py` delta (+126 lines)

- **Added `STALENESS_DAYS_THRESHOLD: int = 2` constant** (near `_STALE_THRESHOLD_DAYS`, pre-`logger = logging.getLogger(__name__)`).
- **Added `_LAST_LOADED_STATE: 'dict | None' = None` module-level cache** (review R1, Codex MEDIUM on SC-3). Populated inside `run_daily_check` immediately after `load_state()` via `global _LAST_LOADED_STATE; _LAST_LOADED_STATE = state`. Consumed by Task 3's outer except.
- **Rewrote `_send_email_never_crash`** (line 136): now returns the notifier `SendStatus` verbatim (or `None` on import-time/pre-status failure) so the caller can translate.
- **Added `_maybe_set_stale_info(state, run_date)`** (line 173 area): parses `state['last_run']` ISO date, computes `(run_date.date() - last_dt.date()).days`; when `> STALENESS_DAYS_THRESHOLD`, sets the TRANSIENT `state['_stale_info'] = {'days_stale': N, 'last_run_date': iso}`. Never calls `append_warning` (B3 revision — prevents age-filter drop at render).
- **Added `_dispatch_email_and_maintain_warnings(state, old_signals, now, is_test, persist)`** (line 197): B1 canonical ordering enforcer — dispatch → `clear_warnings` → (if `status is None` OR `not status.ok` and reason != 'no_api_key') `append_warning(source='notifier', ...)` → `state.pop('_stale_info', None)` → `save_state`. On `persist=False` (`--test`), short-circuits to just `state.pop('_stale_info', None)` (CLI-01 structural read-only).
- **`run_daily_check` body changes:**
  - After `state = state_manager.load_state()`: `global _LAST_LOADED_STATE; _LAST_LOADED_STATE = state` + `_maybe_set_stale_info(state, run_date)`.
  - Per-symbol loop: scalar imports replaced with `resolved = state['_resolved_contracts'][state_key]; multiplier = resolved['multiplier']; cost_aud_round_trip = resolved['cost_aud']; cost_aud_open = cost_aud_round_trip / 2`. `_SYMBOL_CONTRACT_SPECS` no longer referenced in the loop body.
  - Step 4 equity rollup: replaced `spec = _SYMBOL_CONTRACT_SPECS[sk]` with `resolved = state['_resolved_contracts'][sk]` for both multiplier + cost_aud.
- **`main()` dispatch ladder** now calls `_dispatch_email_and_maintain_warnings(state, old_signals, run_date, is_test=args.test, persist=not args.test)` (instead of bare `_send_email_never_crash(...)`).

### `dashboard.py` delta

`_compute_total_return` (line 487) rewritten per D-16:
```python
initial = state.get('initial_account', INITIAL_ACCOUNT)
# ... currents fall through to initial baseline ...
total_return = (current - initial) / initial
```

**Call-site audit:** only one call site in `dashboard.py` (line 494 — rewritten). Other `INITIAL_ACCOUNT` references in `dashboard.py` are import + comment only. `notifier.py` was NOT touched in Plan 03 (scope locked).

### State_manager confirmation (B2 revision)

`state_manager.py` was NOT modified by Plan 03. The existing corrupt-recovery append at line 371 (`'recovered from corruption; backup at {backup_name}'`) remains as-is; Plan 02's classifier matches this prefix directly via age-filter bypass. Grep:
```
$ grep -n "'recovered from corruption; backup at '" state_manager.py
371:      f'recovered from corruption; backup at {backup_name}',
```

### Task 1 tests

Existing `TestOrchestrator` (12 tests) passed unchanged. 4 Phase-6 `_fake_send` helpers migrated from `return 0` to `return notifier.SendStatus(ok=True, reason=None)`.

## Task 2 — argparse CONF flags + `_validate_flag_combo` relaxation + `_handle_reset` Q&A + preview + non-TTY guard + T-08-12 isfinite (commit `73f611c`)

### `main.py` delta

- **New `_stdin_isatty()` wrapper** (after `_validate_flag_combo`). Mirrors Phase 7 `_get_process_tzname` precedent for test-patchability.
- **3 new argparse flags** (`_build_parser`, appended before `return p`):
  - `--initial-account` (type=float, default=None)
  - `--spi-contract` (choices=list(system_params.SPI_CONTRACTS.keys()))
  - `--audusd-contract` (choices=list(system_params.AUDUSD_CONTRACTS.keys()))
- **`_validate_flag_combo`** relaxed: `--reset` exclusivity narrowed to `{--test, --force-email, --once}` (CONF companions allowed); new check: CONF flags require `--reset` (exit 2 + `"require --reset"`).
- **`_handle_reset(args)` wholesale rewrite** (~line 992). 150-line body replacing the 30-line Phase 4 body. Flow:
  1. D-13 non-TTY guard (first — exit 2 if non-TTY AND any CONF flag missing).
  2. D-09 Q&A for each absent flag; accepts 'q' (case-insensitive) and EOFError to cancel (exit 1).
  3. `$`/comma stripping on initial_account input.
  4. T-08-12 `math.isfinite` guard applied to both argparse-flag AND interactive paths (exit 1 + stderr "finite").
  5. D-10 min $1,000 check.
  6. D-11 label whitelist validation on interactive path (argparse already handles the flag path).
  7. D-12 preview block: `New values:` + `Current state.json:` (on readable state).
  8. RESET_CONFIRM env override preserved.
  9. Build state + `state['initial_account'] = float(initial_account)` + `state['contracts'] = {...}` + save.
- **`main()`**: `if args.reset: return _handle_reset()` → `return _handle_reset(args)`.

### `tests/test_main.py` delta

- **Existing `test_reset_with_confirmation_writes_fresh_state`**: updated to pass explicit `--initial-account 100000 --spi-contract spi-mini --audusd-contract audusd-standard` (D-13 non-TTY guard requires flags in pytest environment).
- **Existing `test_reset_without_confirmation_does_not_write`**: monkeypatches `_stdin_isatty=True` + passes explicit flags + simulates 'no' at YES prompt.
- **4 new test classes (20 new tests):**
  - `TestResetFlags` (10 tests): all-flags happy path, min-$1000 rejection, spi/audusd choices rejection, flag-combo relaxation + strictness, NaN/inf rejection on CLI path.
  - `TestResetInteractive` (7 tests): TTY happy path, 'q' cancel, blank defaults, $/comma stripping, invalid float, below-min, NaN rejection on interactive path.
  - `TestResetPreview` (1 test): capsys asserts `New values:` + `Current state.json:` + `$50,000.00` + `SPI200:  spi-standard`.
  - `TestResetNonTTY` (2 tests): non-TTY + no flags → exit 2 + stderr; non-TTY + explicit flags + YES → exit 0.

### `tests/test_scheduler.py` delta

1 lambda updated: `_handle_reset = lambda: 1` → `lambda args: 1` (signature change).

## Task 3 — outer crash-email boundary + `_send_crash_email` + `_build_crash_state_summary` + Layer-B + warning-carry-over-flow tests (commit `065d016`)

### `main.py` delta

- **New `_build_crash_state_summary(state)`** (line 168 area): bounded text/plain summary containing `signals:` + `account:` + `positions:` lines. Explicitly excludes trade_log / equity_history / warnings (D-06 bound on body size). `state is None` returns sentinel `'(state not loaded — crash before load_state)'`. Signals keyed by yfinance symbol (`^AXJO` / `AUDUSD=X`) with fallback to state_key (`SPI200` / `AUDUSD`) to handle both shapes.
- **New `_send_crash_email(exc, state, now)`** (line ~218): local `import notifier` (C-2), builds summary via `_build_crash_state_summary(state)`, delegates to `notifier.send_crash_email(exc, summary, now=now)`. Nested try/except logs `[Email] ERROR: crash-email dispatch wrapper failed: ...` and returns None instead of raising.
- **`main()` outer `except Exception` extended** (line 1315 area): now includes a nested try/except around `_send_crash_email(e, state=_LAST_LOADED_STATE)`. If the crash-email dispatch itself raises, logs `[Email] ERROR: crash-email dispatch also failed: ...` without changing the return code. DataFetchError / ShortFrameError path untouched (still exit 2, no crash mail).
- **No second outer try/except added.** The existing `except Exception` body was extended in place. Grep: `grep -c "unexpected crash" main.py` → 1 match.

### `tests/test_main.py` delta (+19 tests)

- **`TestCrashEmailBoundary` (12 tests):**
  - `test_build_crash_state_summary_contains_core_sections` (bounded content)
  - `test_build_crash_state_summary_state_none_returns_placeholder`
  - `test_build_crash_state_summary_renders_open_positions`
  - `test_send_crash_email_wrapper_calls_notifier`
  - `test_send_crash_email_wrapper_swallows_errors`
  - `test_layer_b_once_mode_unexpected_exception_fires_crash_email`
  - `test_layer_b_default_mode_assertion_error_fires_crash_email`
  - `test_data_fetch_error_does_not_fire_crash_email` (typed branch preserved)
  - `test_short_frame_error_does_not_fire_crash_email`
  - `test_crash_email_dispatch_failure_does_not_mask_exit_code`
  - `test_layer_a_per_job_error_does_not_fire_crash_email`
  - `test_crash_email_includes_last_loaded_state` (review R1 SC-3 completeness)
- **`TestWarningCarryOverFlow` (7 tests):**
  - `test_dispatch_ok_clears_warnings_no_append`
  - `test_dispatch_failed_5xx_warning_B_present_after_clear` (B1 named evidence)
  - `test_dispatch_no_api_key_does_not_append_notifier_warning`
  - `test_dispatch_persist_false_skips_mutation`
  - `test_happy_path_save_state_called_exactly_twice` (W3 named evidence)
  - `test_stale_info_popped_before_save` (B3 named evidence)
  - `test_dispatch_status_none_appends_warning` (review R2 named evidence)

### `tests/test_scheduler.py` delta (+2 tests)

- **`TestCrashEmailLayerB` (2 tests):**
  - `test_assertion_error_in_loop_driver_propagates_to_main_catch_all`
  - `test_layer_a_per_job_error_does_not_fire_crash_email`

### `tests/test_dashboard.py` delta (+3 tests)

- **`TestTotalReturnInitialAccount` (3 tests):**
  - `test_custom_initial_account_50k_account_75k_returns_plus_50pct`
  - `test_custom_initial_account_100k_account_50k_returns_minus_50pct`
  - `test_missing_initial_account_falls_back_to_INITIAL_ACCOUNT`

## Full pytest output

```
$ python -m pytest tests/ -q
.........................................................................
.........................................................................
.........................................................................
.........................................................................
.........................................................................
.........................................................................
.........................................................................
.........................................................................
.........................................................................
653 passed in 93.53s (0:01:33)
```

Plan 02 finished with 609 tests; Plan 03 adds 44 new tests → 653 passing. Zero failures. `TestDeterminism::test_forbidden_imports_absent` (AST hex-boundary guard) passes — `sizing_engine.py` remains clean of `SPI_CONTRACTS` / `AUDUSD_CONTRACTS` references.

## Deviations from Plan

None — plan executed exactly as written. Minor adaptations:
1. **Phase 6 fake-send migration (scope-aligned):** 4 existing `test_force_email_*` and `test_test_flag_*` tests used `return 0` (int) from their `_fake_send` monkeypatches. Task 1's SendStatus consumer expects a NamedTuple. Updated each fake to `return notifier.SendStatus(ok=True, reason=None)`. This is the back-to-back-wave intermediate-state restoration the `<execution_note>` header block names explicitly — not a deviation, but documented here for reviewer visibility.
2. **Existing `test_reset_*` tests (scope-aligned):** `_handle_reset(args)` signature change + D-13 non-TTY guard required passing explicit flags or monkeypatching `_stdin_isatty`. Preserved test names for git-blame continuity, as the plan instructs.

## Phase 8 closure checklist — 7 ROADMAP success criteria

| SC | Requirement | File:line / Test evidence |
|----|-------------|---------------------------|
| SC-1 | Warnings appended in run N surface as banner in run-(N+1) email (NOTF-10) | `main._dispatch_email_and_maintain_warnings` at main.py:197 (B1 clear→maybe-append→save). Notifier age-filter routine row in `notifier._render_header_email` (Plan 02). Test: `tests/test_main.py::TestWarningCarryOverFlow::test_dispatch_failed_5xx_warning_B_present_after_clear`. |
| SC-2 | `last_run > 2 days` → stale banner + `[!]` subject prefix (ERR-05) | `main._maybe_set_stale_info` at main.py:173; `STALENESS_DAYS_THRESHOLD = 2` at main.py:89. `notifier._has_critical_banner` reads `_stale_info` (Plan 02). Tests: Task 1 inline smoke + `TestWarningCarryOverFlow::test_stale_info_popped_before_save`. |
| SC-3 | Unhandled exception → crash email with last-known state summary (ERR-04) | `main._build_crash_state_summary` at main.py:168; `_send_crash_email` at main.py:218; outer except reads `_LAST_LOADED_STATE` at main.py:1315 area. `_LAST_LOADED_STATE` populated inside `run_daily_check` at main.py:717 area. Test: `TestCrashEmailBoundary::test_crash_email_includes_last_loaded_state`. |
| SC-4 | Corrupt-state backup → gold-border critical banner (ERR-03) | `state_manager.load_state` at state_manager.py:371 appends `'recovered from corruption; backup at ...'` (Plan 01, UNCHANGED in Plan 03). `notifier._has_critical_banner` matches prefix with age-bypass (Plan 02). |
| SC-5 | Resend 5xx → next-run routine warning (ERR-02) | `notifier.send_daily_email` returns `SendStatus(ok=False, reason=...)` on 5xx (Plan 02). `_dispatch_email_and_maintain_warnings` translates to `append_warning(source='notifier', ...)` AFTER `clear_warnings` (B1 order) at main.py:240-258. Test: `TestWarningCarryOverFlow::test_dispatch_failed_5xx_warning_B_present_after_clear`. |
| SC-6 | `--reset --initial-account N` → state.initial_account=N, dashboard reads from state (CONF-01) | `main._handle_reset` at main.py:992 writes `state['initial_account']`; `dashboard._compute_total_return` at dashboard.py:487 reads `state.get('initial_account', INITIAL_ACCOUNT)`. CLI validation (min $1k, isfinite) at main.py:1091-1116. Tests: `TestResetFlags::test_reset_with_all_three_flags_writes_state` + `TestTotalReturnInitialAccount::test_custom_initial_account_50k_account_75k_returns_plus_50pct`. |
| SC-7 | `--reset --spi-contract ... --audusd-contract ...` → state.contracts labels + load_state materialises `_resolved_contracts` + run_daily_check passes multiplier/cost_aud to sizing_engine (CONF-02) | `main.run_daily_check` uses `state['_resolved_contracts'][state_key]['multiplier']` at main.py:740 area. Plan 01 materialises `_resolved_contracts` in `load_state`. Plan 03 AST guard ensures `sizing_engine` still imports no contract dicts — `tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent` passes. |

## Revision blocker evidence — B1/B2/B3/B4/B5/W2/W3/I1/I2

| Blocker | Evidence |
|---------|----------|
| **B1 ordering (dispatch → clear → maybe-append → single save)** | Python regex check: `m_clear.start() < m_append_notifier.start() < m_save.start()` over main.py source returns pass. Named test: `TestWarningCarryOverFlow::test_dispatch_failed_5xx_warning_B_present_after_clear`. |
| **B2 (corrupt-recovery flow unchanged)** | `grep -c "_corrupt_recovery" main.py` → 0. `grep -c "_corrupt_recovery" state_manager.py` → 0. `grep -c "'recovered from corruption; backup at '" state_manager.py` → 1 (line 371 unchanged). Plan 03 made NO edits to `state_manager.py`. |
| **B3 (transient _stale_info)** | `grep -c "_stale_info" main.py` → 11. `state.pop('_stale_info', None)` appears in 2 places (dispatch helper + test-mode short-circuit). Named test: `test_stale_info_popped_before_save`. |
| **B4 (hero placeholder)** | Plan 02 scope — Plan 03 didn't touch notifier.py. See `08-02-SUMMARY.md`. |
| **B5 (non-automatable acceptance)** | Plan 02 scope — Plan 03's acceptance checks are all deterministic greps / pytest assertions. |
| **W2 (heredoc `$` escapes)** | Task 1 inline smoke used `python3 << 'PYEOF' ... PYEOF` (single-quoted). Zero `\$` remain in the executed verify block. |
| **W3 (per-run save count = 2)** | Named test: `TestWarningCarryOverFlow::test_happy_path_save_state_called_exactly_twice` passes. `run_daily_check` saves once at step 9; `_dispatch_email_and_maintain_warnings` saves once post-dispatch. |
| **I1 (sizing_engine hex clean)** | `grep -c "SPI_CONTRACTS\|AUDUSD_CONTRACTS" sizing_engine.py` → 0 (verified by `tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent` passing). |
| **I2 (heredoc escape regression)** | Same fix as W2 — single-quoted heredoc. Verified by Task 1 smoke running cleanly. |
| **R1 (crash email state completeness)** | `_LAST_LOADED_STATE` declared at main.py:95 area, written inside `run_daily_check`, read by outer except. `grep -c "_LAST_LOADED_STATE" main.py` → 7 (declaration + global + assignment + docstrings + crash handler read). Named test: `test_crash_email_includes_last_loaded_state`. |
| **R2 (silent-skip `status is None` branch)** | `grep -c "if status is None" main.py` → 1 (inside `_dispatch_email_and_maintain_warnings`). `grep -c "import or runtime error" main.py` → 1. Named test: `test_dispatch_status_none_appends_warning`. |

## Self-Check: PASSED

Verification of all files and commits listed above:

### Created files
- `.planning/phases/08-hardening-warning-carry-over-stale-banner-crash-email-config/08-03-SUMMARY.md`: present (this file).

### Commits
- `e936b49` feat(08-03): SendStatus consumer + _stale_info transient + B1 canonical dispatch order + tier resolution + dashboard D-16
- `73f611c` feat(08-03): CLI CONF flags + _handle_reset Q&A + preview + non-TTY guard + T-08-12 isfinite
- `065d016` feat(08-03): outer crash-email boundary + _build_crash_state_summary + Layer-B tests + warning-carry-over-flow tests

### Final metrics
- Test suite: 653 passed / 0 failed (up from 609 baseline, +44 new).
- AST hex-boundary guard: `TestDeterminism::test_forbidden_imports_absent` → PASS.
- `python -m pytest tests/ -x -q` → PASS (zero failures).
- Phase 8 gate closed.
