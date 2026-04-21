---
phase: 4
reviewers: [gemini, codex]
reviewed_at: 2026-04-21T12:20:00+08:00
plans_reviewed:
  - 04-01-PLAN.md
  - 04-02-PLAN.md
  - 04-03-PLAN.md
  - 04-04-PLAN.md
skipped_reviewers:
  - claude (running inside Claude Code — self-review excluded)
  - opencode, qwen, cursor, coderabbit (not installed)
---

# Cross-AI Plan Review — Phase 4

Two external AI CLIs reviewed the full Phase 4 plan set (4 PLAN.md + CONTEXT + RESEARCH + PATTERNS + VALIDATION) after the internal `gsd-plan-checker` returned 8/8 PASS. Both reviewers found substantive issues the internal checker missed — validates the adversarial-review posture.

---

## Gemini Review

The following review identifies a critical state-corruption bug and several metadata omissions in the Phase 4 plans. While the integration strategy is technically sound and respects all hexagonal boundaries, the orchestration sequence in Wave 2 will inadvertently wipe new positions during signal reversals.

### Summary

The Phase 4 plans provide a robust framework for wiring the pure-math engines to live data and CLI orchestration. The strategy for isolating yfinance I/O, the structural enforcement of the `--test` read-only guarantee, and the hybrid test approach using recorded JSON fixtures are excellent. However, a **High Severity** flaw exists in the `run_daily_check` update sequence: the call to `state_manager.record_trade` will clobber new positions created during signal reversals because the orchestrator updates the state in the wrong order. Additionally, several metadata requirements from D-11 (like `last_scalars` persistence) are currently omitted from the plan.

### Strengths

- **Superior I/O Isolation:** `data_fetcher.py` correctly encapsulates yfinance quirks (like `Ticker.history` vs `download`) and implements a clean retry loop with narrow exception handling.
- **Robust Test Isolation:** Using `monkeypatch.chdir(tmp_path)` as the primary state-isolation mechanism is a clever and non-invasive way to test the orchestrator without modifying production function signatures.
- **Structural Safety:** The plan correctly identifies the need for `force=True` in `logging.basicConfig` to ensure logs aren't swallowed by existing pytest handlers.
- **Backward Compatibility:** The D-08 `isinstance(..., int)` check in `main.py` handles the Phase 3-to-Phase 4 schema transition seamlessly.

### Concerns

#### G-1. HIGH: State Corruption on Signal Reversals

In `04-03-PLAN.md` Task 1 (Behavior 3.m and 3.n), the orchestrator updates `state['positions'][symbol]` with the new entry *before* calling `state_manager.record_trade`.

- **The Issue:** `record_trade` explicitly sets `state['positions'][instrument] = None` to ensure the position is closed atomically with the trade record.
- **Impact:** On a LONG → SHORT reversal day, the orchestrator will correctly size the new SHORT position and save it to the state dict (step 3.m), but then immediately wipe it to `None` when recording the closed LONG trade (step 3.n). The system will be left in a FLAT state instead of SHORT.
- **Location:** `04-03-PLAN.md` Task 1, Behavior Step 3.m/n.

#### G-2. MEDIUM: Missing `last_scalars` Persistence

Decision D-11 (Step 3.j) and the roadmap requirements specify that the signal state should include the latest indicators for dashboard/email rendering.

- **The Issue:** The plan for updating `state['signals'][symbol]` omits the `last_scalars` field.
- **Impact:** Future Phase 5 (Dashboard) and Phase 6 (Email) will lack the metadata needed to display ADX/Momentum values for the current signal, requiring a corrective refactor.
- **Location:** `04-03-PLAN.md` Task 1, Behavior Step 3.m.

#### G-3. LOW: Missing `import time` for Performance Metrics

The plan requires measuring `fetch_elapsed` and total run duration using `time.perf_counter()`.

- **The Issue:** The imports block for `main.py` in Wave 0 and Wave 2 does not include `import time`.
- **Location:** `04-01-PLAN.md` Task 1 (main.py scaffold) and `04-03-PLAN.md` Task 1.

#### G-4. LOW: Sizing Warnings Not Surfaced to Console

Requirement SIZE-05 and Roadmap SC-1 emphasize surfacing "size=0" warnings.

- **The Issue:** While the plan correctly appends sizing warnings to a local list, it does not explicitly instruct `_format_per_instrument_log_block` to print them.
- **Location:** `04-03-PLAN.md` Task 1, Behavior 3.l.

### Suggestions

- **Fix Concern G-1:** Reorder the update logic in `run_daily_check`. Call `record_trade` (the closure) first, then update the position (the new entry).
  - *Planner Phrase:* "If `result.closed_trade` is not None, call `state_manager.record_trade` first; then, and only then, assign `result.position_after` to the state positions dict to ensure reversals aren't clobbered by the closure logic."
- **Fix Concern G-2:** Include `last_scalars` in the signal update.
  - *Planner Phrase:* "Update `state['signals'][state_key]` to include `last_scalars: scalars` per D-11."
- **Fix Concern G-4:** Update the log block emitter.
  - *Planner Phrase:* "Instruct `_format_per_instrument_log_block` to iterate and log any strings present in `result.warnings` (e.g., undersized skip-trade alerts) using the `[State]` prefix."

### Risk Assessment: MEDIUM

The overall risk is **MEDIUM**. While the architectural boundaries and CLI logic are very safe, the state-update ordering bug in the orchestrator is a high-impact logic error that would cause the system to fail to open new positions on reversal days. Fixing this ordering is trivial but critical for the system's mechanical integrity.

**Collective ROADMAP Compliance:**
The 4 plans collectively satisfy the 5 ROADMAP success criteria, provided the "order-of-operations" bug in the state mutation is resolved. The decision to defer the actual `schedule` loop to Phase 7 is technically a deviation from Roadmap SC-5, but it is well-documented in the CONTEXT.md and provides a cleaner testing path for Phase 4.

---

## Codex Review

### Summary

The plan set is strong on decomposition, test naming, and preserving the project's hex-lite boundaries, but it has a few important blind spots the internal checker appears to have missed. The biggest issues are not implementation trivia; they are spec/plan mismatches and one likely state-corruption bug in the orchestrator ordering. In particular, Phase 4 as planned does not actually satisfy all of the stated Phase 4 requirements/success criteria, and the `run_daily_check()` mutation order around `record_trade()` looks unsafe for reversal/same-bar reopen flows.

### Strengths

- The wave split is sensible. `04-01` scaffolds the interfaces and guardrails, `04-02` isolates yfinance risk, `04-03` wires the orchestrator, and `04-04` closes the safety net.
- The plan correctly treats `yf.Ticker(...).history()` as the safe yfinance 1.2.0 API and explicitly avoids `yf.download()`, which is the right call.
- The D-12 `gross_pnl` vs `realised_pnl` pitfall is explicitly documented and tested. That is exactly the kind of bug that often slips through.
- The D-08 backward-compat handling for `state['signals'][symbol]` being either `int` or `dict` is well identified and gets its own test.
- The AST guard extension is a good move. Locking `data_fetcher.py` as an I/O hex early is the right pattern.
- The state-path isolation decision via `monkeypatch.chdir(tmp_path)` is pragmatic and consistent with the existing relative `STATE_FILE` contract.

### Concerns

#### C-1. HIGH: The plans do not fully satisfy the stated Phase 4 requirements/success criteria

- `ROADMAP.md` success criterion 5 says default `python main.py` "runs immediately and enters the schedule loop."
- `04-CONTEXT.md` D-07 and `04-04-PLAN.md` explicitly defer the schedule loop to Phase 7 and make default mode an alias for `--once`.
- `REQUIREMENTS.md` / phase requirement text for `CLI-01` and `CLI-03` still says `--test` sends a `[TEST]` email and `--force-email` sends today's email. `04-CONTEXT.md` and `04-04-PLAN.md` deliberately stub these instead.

This is a planning-layer contradiction, not an implementation detail. If these plans execute as written, Phase 4 will be "green" against the narrowed context, but not against the original requirement text.

#### C-2. HIGH: `run_daily_check()` likely clobbers `position_after` on closed-trade paths

- In `04-03-PLAN.md`, Task 1 step `3.m` writes: `state['positions'][state_key] = result.position_after`
- Then step `3.n` calls: `state = state_manager.record_trade(state, trade_dict)`

Your own research/architecture notes imply `record_trade()` mutates state and clears the instrument position on close. If `sizing_engine.step()` returns both `closed_trade != None` and `position_after != None` for a reversal or same-bar reopen, then `record_trade()` can wipe the new position you just stored.

This is the highest-probability behavioral bug in the plan set. **(Duplicate of G-1.)**

#### C-3. HIGH: `data_fetcher` timezone contract is internally inconsistent

- `04-CONTEXT.md` D-01 says `fetch_ohlcv(...)` returns a `DatetimeIndex in Australia/Perth`.
- `04-RESEARCH.md` and `04-02-PLAN.md` both explicitly say to preserve exchange-local timezone and not convert, because D-13 treats `signal_as_of` as a market-day label.

Those two contracts cannot both be true. If implementation follows research, D-01 is false. If implementation follows D-01, D-13 is at risk.

#### C-4. MEDIUM: The `caplog` strategy around `logging.basicConfig(force=True)` is shaky

- `04-04-PLAN.md` acknowledges the problem but the proposed explanation is not reliable.
- Many tests in `04-03-PLAN.md` and `04-04-PLAN.md` assert on `caplog.text` after calling `main.main(...)`, which reconfigures root logging with `force=True`.

That can detach pytest's capture handler and make log assertions flaky or empty depending on ordering. The plan knows this is a pitfall but does not actually resolve it cleanly.

#### C-5. MEDIUM: `FORBIDDEN_MODULES_MAIN` is too permissive

- `04-01-PLAN.md` / `04-PATTERNS.md` only forbid `numpy` in `main.py`.
- That means `main.py` could import `yfinance`, `requests`, or `pandas` directly and still pass the AST guard.

Given the stated architecture, `main.py` should orchestrate modules, not reach into transport/data libraries directly.

#### C-6. MEDIUM: Missing explicit schema-validation path for Yahoo column drift

- The research correctly warns about Yahoo shape changes.
- The tests cover "extra columns stripped," but not "required columns missing."
- As planned, missing `Open/High/Low/Close/Volume` raises `KeyError`, which falls into the generic `Exception` path in `main()` and returns `1` as an unexpected crash, not a fetch/data failure.

That is graceful enough to avoid a silent crash, but it is not a cleanly classified Yahoo failure.

#### C-7. MEDIUM: The verification rule `grep -c 'state_manager.save_state' main.py == 1` becomes false in Wave 3

- `04-03-PLAN.md` verification item 6 expects exactly one `save_state` call.
- `04-04-PLAN.md` adds `_handle_reset()` that also calls `save_state()`.
- `04-04-PLAN.md` phase gate still says: `grep -c 'state_manager.save_state' main.py` — exactly 1

That gate is impossible once reset is implemented as planned.

#### C-8. MEDIUM: `--force-email` semantics are underspecified for Phase 6 compatibility

- In `04-04-PLAN.md`, `--force-email` without `--test` does not run `run_daily_check()` at all; it only logs a stub and exits.
- That may be fine for Phase 4 scope, but it bakes in a dispatch shape that may not match eventual real behavior, where "send today's email" likely needs fresh computed state.

Not a Phase 4 blocker, but it is a design seam worth fixing now.

#### C-9. LOW: `tests/regenerate_fetch_fixtures.py` bypasses production fetch logic

- Wave 0 uses raw `yf.Ticker(...).history(...)` in the regenerator because `fetch_ohlcv()` is still a stub.
- If left that way, your fixtures are generated by a different path than production.

That is survivable, but after Wave 1 the regenerator should probably switch to `data_fetcher.fetch_ohlcv()`.

#### C-10. LOW: `pytest-freezer` import/verification looks brittle

- `04-01-PLAN.md` uses `import pytest_freezer` / `from pytest_freezer import freezer`.
- Depending on packaging, the plugin may be installed and usable by pytest without those imports being valid.

This is minor, but the verification step may fail for the wrong reason.

### Suggestions

Use these as direct planner edits.

- Resolve the Phase 4 spec mismatch explicitly: "Amend `ROADMAP.md` / `REQUIREMENTS.md` for Phase 4 to state that `CLI-01` and `CLI-03` are parser-stable stubs only, and that the schedule loop is deferred to Phase 7. Do not leave the original requirement text unchanged if the implementation intentionally does less."
- Fix the reversal-position ordering bug: "In `run_daily_check()`, call `record_trade()` before the final `state['positions'][state_key] = result.position_after`, or refactor to apply `record_trade()` effects to account/trade log only and set `positions` last from `StepResult.position_after`."
- Make the timezone contract consistent: "Change D-01 wording from 'DatetimeIndex in Australia/Perth' to 'DatetimeIndex preserved as returned by yfinance (exchange-local tz); `signal_as_of` uses `strftime('%Y-%m-%d')` with no tz conversion.'"
- Tighten the main-module AST guard: "Expand `FORBIDDEN_MODULES_MAIN` to include `yfinance`, `requests`, and `pandas`; `main.py` may import cross-hex modules, but must not reach directly into transport/data libraries."
- Add a missing-column fetch test: "Add `test_missing_required_columns_raises_clear_fetch_error` in `tests/test_data_fetcher.py` using a DataFrame missing `Volume` or `Close`, and raise a domain-specific error instead of leaking `KeyError`."
- Fix the logging-test strategy: "For log-shape tests, call `run_daily_check()` directly after configuring capture, or monkeypatch `main.logging.basicConfig` in tests that assert on `caplog`. Do not rely on `caplog` surviving a `force=True` root reconfiguration."
- Fix the impossible `save_state` grep gate: "Replace repo-wide `grep -c 'state_manager.save_state' main.py == 1` with a function-scoped structural check that `run_daily_check()` contains exactly one `save_state` call and the `args.test` branch returns before it."
- Future-proof `--force-email`: "Document now that Phase 6 will make `--force-email` run the same compute path as `--once` before sending, even if Phase 4 only stubs the notifier."

### Risk Assessment: MEDIUM-HIGH

The decomposition and testing discipline are good, so this is not a weak plan set. But there are two material issues that can cause real trouble even if execution is otherwise competent: the Phase 4 spec mismatch, and the likely `record_trade()`/`position_after` ordering bug. Those are exactly the sort of issues that can let a phase appear green while still failing the intended contract or corrupting position state on reversals. If those are corrected, the remaining issues are manageable.

---

## Consensus Summary

### Agreed Strengths (both reviewers)

- Wave decomposition is sensible — scaffold → fetch → orchestrator → safety net, with sequential dependencies honoured by `files_modified` overlap.
- `data_fetcher.py` as I/O hex with `yf.Ticker(...).history()` (avoiding the `yf.download()` MultiIndex trap) is the right call.
- D-12 `gross_pnl` vs `realised_pnl` pitfall is documented and tested.
- D-08 per-instrument `state['signals'][symbol]` int-or-dict backward compatibility is identified and tested.
- `monkeypatch.chdir(tmp_path)` state-path isolation is pragmatic and matches Phase 3 precedent.
- AST blocklist extension for `data_fetcher.py` locks the hex-lite boundary.

### Agreed Concerns — HIGHEST PRIORITY (both reviewers raised these)

**AC-1 [HIGH] State corruption on signal reversal** — `run_daily_check` step 3.m (set `state['positions'] = result.position_after`) runs BEFORE step 3.n (`state_manager.record_trade`). On LONG→SHORT reversal the new SHORT position is clobbered because `record_trade` clears `state['positions'][instrument]` as part of the close. Affected files: `04-03-PLAN.md` Task 1. **Fix:** call `record_trade` first (for accounting/trade_log effects), then assign `result.position_after` last.

### Divergent / unique Concerns — worth investigating

**Codex-only HIGH:**

- **C-1 Plan vs ROADMAP/REQUIREMENTS mismatch:** ROADMAP SC-5 says default enters schedule loop (plan defers to Phase 7). REQUIREMENTS text for CLI-01 ("[TEST] email") and CLI-03 ("sends today's email") is unchanged but plan stubs both. Upstream specs should be amended to reflect the Phase 4 ↔ Phase 6/7 split rather than leaving contradictions in place.
- **C-3 Timezone contract internally inconsistent:** CONTEXT D-01 says DatetimeIndex in Australia/Perth; RESEARCH + D-13 say preserve exchange-local tz. Cannot both be true. **Fix:** amend D-01 to match RESEARCH (no tz conversion; `signal_as_of` is a market-day calendar label).

**Codex-only MEDIUM:**

- **C-4 caplog + basicConfig(force=True) flakiness** — `force=True` detaches pytest's capture handler. Tests asserting on `caplog.text` after `main.main(...)` may be flaky or empty depending on test ordering. **Fix:** call `run_daily_check()` directly (bypassing `main()`'s `basicConfig` call) in log-shape tests, OR monkeypatch `main.logging.basicConfig` to a no-op in those tests.
- **C-5 `FORBIDDEN_MODULES_MAIN` too permissive** — only blocks `numpy`. Should also block `yfinance`, `requests`, `pandas`. main.py must orchestrate, not reach into transport/data libs.
- **C-6 Missing "required columns missing" fetch test** — KeyError on missing OHLCV column leaks as generic Exception → exit 1 (unexpected crash). Should be domain-specific `DataFetchError` → exit 2.
- **C-7 `grep -c save_state == 1` gate impossible in Wave 3** — `_handle_reset()` adds a second `save_state` call. **Fix:** function-scoped structural check on `run_daily_check` body only.
- **C-8 `--force-email` future-proofing** — Phase 4 stub is fine; document now that Phase 6 will make `--force-email` run the same compute path before sending, so the dispatch shape is locked early.

**Codex-only LOW:**

- **C-9 regenerator bypasses production fetch** — after Wave 1 merges, `tests/regenerate_fetch_fixtures.py` should switch from raw `yf.Ticker()` to `data_fetcher.fetch_ohlcv()` so fixtures reflect production code path.
- **C-10 pytest-freezer import verification brittle** — `import pytest_freezer` may fail even when the plugin is installed and usable. Use `pytest --version | grep -q freezer` or similar.

**Gemini-only MEDIUM:**

- **G-2 Missing `last_scalars` persistence** — D-11 mentions including latest ADX/Momentum scalars in `state['signals'][symbol]` for Phase 5/6 rendering. Plan omits. **Fix:** include `last_scalars: scalars` in signal-state update at step 3.m.

**Gemini-only LOW:**

- **G-3 Missing `import time`** — `main.py` imports block omits `import time`. Perf measurement via `time.perf_counter()` would break.
- **G-4 Sizing warnings not surfaced** — plan appends `result.warnings` to local list but doesn't instruct `_format_per_instrument_log_block` to print them. **Fix:** explicit "log warnings with `[State]` prefix" instruction.

### Risk Assessment Consensus

| Reviewer | Verdict |
|----------|---------|
| Gemini | **MEDIUM** — ordering bug is trivial to fix but critical |
| Codex | **MEDIUM-HIGH** — ordering bug + spec mismatch + timezone inconsistency |

**Combined assessment: MEDIUM-HIGH.** The plan set is structurally sound (wave decomposition, hex-lite boundaries, test naming) but has three upstream-contract issues that affect correctness and downstream phase compatibility:

1. **AC-1 state-reversal ordering** (both agree — HIGHEST priority)
2. **C-1 spec mismatch** (amend ROADMAP.md / REQUIREMENTS.md CLI-01/CLI-03 or fold into Phase 6/7)
3. **C-3 timezone contract** (amend D-01)

The other MEDIUM findings (C-4, C-5, C-6, C-7, G-2) are localized fixes that the planner can apply in a single revision pass.

---

## Next Step

Incorporate feedback into planning:

```
/gsd-plan-phase 4 --reviews
```

This will re-spawn the planner with REVIEWS.md as input — it will read each concern, rewrite the affected plans to address it, and re-run the plan-checker. Expected changes (by file):

- `04-03-PLAN.md` Task 1 Behavior 3.m/n → reorder record_trade before position assignment (AC-1)
- `04-03-PLAN.md` Task 1 Behavior 3.m → add `last_scalars` to signal-state update (G-2)
- `04-CONTEXT.md` D-01 → amend timezone wording (C-3)
- `04-01-PLAN.md` → expand `FORBIDDEN_MODULES_MAIN` to include yfinance/requests/pandas; add `import time` to main.py scaffold (C-5, G-3)
- `04-02-PLAN.md` → add `test_missing_required_columns_raises_clear_fetch_error` (C-6)
- `04-03-PLAN.md` + `04-04-PLAN.md` → rewrite save_state grep verification as function-scoped structural check (C-7)
- `04-04-PLAN.md` → log-shape tests bypass `main()` or monkeypatch basicConfig (C-4)
- `04-03-PLAN.md` Behavior 3.l → `_format_per_instrument_log_block` emits `result.warnings` (G-4)

**Optional upstream amendments (not required for Phase 4 execution but recommended before closing Phase 4):**

- Amend `REQUIREMENTS.md` CLI-01 and CLI-03 to describe Phase 4 stubs vs Phase 6 wiring split (C-1)
- Amend `ROADMAP.md` SC-5 to note default mode == `--once` in Phase 4; schedule loop lands in Phase 7 (C-1)

Or, alternatively, execute as-is and accept the documented deviations — the decision is the user's call.
