---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
current_plan: 1
status: executing
last_updated: "2026-04-22T23:09:50.132Z"
progress:
  total_phases: 8
  completed_phases: 6
  total_plans: 29
  completed_plans: 26
  percent: 90
---

# STATE — Trading Signals

**Last updated:** 2026-04-20 (roadmap created)

## Project Reference

- **Name:** Trading Signals — SPI 200 & AUD/USD Mechanical System
- **Core value:** Deliver an accurate, reproducible daily signal and actionable instruction to one email inbox every weekday at 08:00 AWST — with full state persistence so P&L, positions, and trade history survive restarts.
- **Operator:** Marc (Perth, AWST UTC+8 no DST)
- **Current focus:** Phase 06 — email-notification

## Current Position

Phase: 06 (email-notification) — EXECUTING
Plan: 1 of 3

- **Milestone:** v1 — Mechanical Signal System
- **Phase:** 5 (complete) → next 6 (Email Notification)
- **Current Plan:** 1
- **Total Plans:** 3
- **Status:** Executing Phase 06
- **Progress:** [██████████] 100%

```
[░░░░░░░░] 0% (0/8 phases)
```

## Performance Metrics

| Metric | Value |
|--------|-------|
| Phases defined | 8 |
| Requirements mapped | 78/78 |
| Phases completed | 0 |
| Phases in-flight | 0 |
| Decisions logged | 4 (operator decisions baked into roadmap) |
| Phase 01 P01 | 9 | 3 tasks | 10 files |
| Phase 01 P02 | 5 | 3 tasks | 3 files |
| Phase 01 P03 | 10 | 2 tasks | 28 files |
| Phase 01 P04 | 4min | 2 tasks | 2 files |
| Phase 01 P05 | 4m18s | 2 tasks | 2 files |
| Phase 01 P06 | 7m6s | 2 tasks | 1 files |
| Phase 02 P01 | 9m58s | 3 tasks | 7 files |
| Phase 02 P02 | 6m34s | 2 tasks | 2 files |
| Phase 02 P03 | 460s | 2 tasks | 2 files |
| Phase 02 P04 | 64m | 2 tasks | 19 files |
| Phase 02 P05 | 14 | 3 tasks | 20 files |

## Accumulated Context

### Decisions

| Decision | Phase | Rationale |
|----------|-------|-----------|
| GitHub Actions is the PRIMARY deployment path (Replit documented as alternative) | 7 | Replit Autoscale doesn't guarantee filesystem persistence and kills `schedule` loops; GHA is free, stateless-by-design, and commits `state.json` back to the repo |
| `n_contracts == 0` skips the trade and warns (no `max(1, …)` floor) | 2 | A `max(1, …)` floor silently breaches the 1% risk budget on small accounts; skipping with a visible warning keeps risk discipline |
| LONG→FLAT (and SHORT→FLAT) closes the open position | 2 | Unambiguous semantics: FLAT means "no position", so any non-matching signal closes |
| Trailing stops use intraday HIGH/LOW for both peak updates and hit detection | 2 | Consistent intraday convention matches how the backtest was built; close-only convention would diverge from reconciliation data |

- Python 3.11.8 installed via pyenv (Homebrew-installed); 5 Phase 1 deps pinned to bit-locked versions in requirements.txt (numpy==2.0.2, pandas==2.3.3, pytest==8.3.3, yfinance==1.2.0, ruff==0.6.9); later-phase deps deferred to their phase scaffolds
- ruff format NOT used in Phase 1 — ruff 0.6.9 lacks indent-width knob (would reflow to 4-space). Using ruff check only, with .editorconfig + reviewer discipline + Plan 06 lint guard for 2-space enforcement (R-05)
- Pyenv preflight remediated by brew install pyenv (was not installed); REVIEWS.md Gemini preflight guidance satisfied. Future GHA setup-python will pick up .python-version=3.11.8
- Plan 01-02 Task 1 AC #10 contradicted documented seed-window NaN rule and Task 3's explicit test; implemented rule-per-documented-intent (Rule 1 deviation logged)
- `_wilder_smooth` pure-loop oracle now trust anchor for ATR/ADX; D-11 flat-price NaN propagation and D-12 bit-exact 0 RVol both verified at 17-test level
- Plan 01-03: %.17g format renders 100.0 as '100' (C %g behaviour); AC grep pattern assumed '100.0' text — prioritised Pitfall 4 bit-roundtrip correctness (Rule 1 deviation)
- Plan 01-03: Split-vote scenario uses 1 up / 1 down / 1 abstain (per REVIEWS MUST FIX); Mom1=+0.058, Mom3=-0.043, Mom12=-0.003 produces FLAT per SIG-08
- Plan 01-03: Scenario generator is inline (not committed as script); only regenerate_goldens.py is committed per D-04. scenarios.README.md documents exact segment endpoints.
- Plan 01-04: production _wilder_smooth uses explicit numpy loop (not pandas .ewm) to enforce oracle's NaN-strict seed-window rule bit-for-bit (REVIEWS MEDIUM)
- Plan 01-04: every indicator column assignment uses explicit .astype('float64') (12 casts) to defend against numpy 2.0 float32 leaks (Pitfall 5)
- Plan 01-04: _assert_index_aligned(computed, golden) helper called BEFORE every assert_allclose so date-index drift fails with clear message (REVIEWS MEDIUM)
- Plan 01-05: get_signal uses list-comprehension NaN-abstaining vote pattern (RESEARCH Example 4); get_latest_indicators wraps every scalar with float() to strip numpy.float64 (REVIEWS POLISH); threshold-equality boundary tests for ADX==25, Mom==+/-0.02 pin < vs <= semantics
- Plan 01-05: _make_single_bar_df helper lets threshold-equality tests bypass compute_indicators — tests isolate vote semantics without coupling to indicator math
- Plan 01-05: per-function imports inside each test (mirror Plan 04 style) + ruff --fix I001 autofix applied as Rule-3 formatting-only deviation
- Plan 01-06 closed Phase 1: TestDeterminism (19 tests) with oracle-anchored SHA256 (D-14), AST blocklist hex guard (REVIEWS STRONGLY RECOMMENDED), and tokenize-aware 2-space indent evidence check (REVIEWS POLISH). Two Rule-1 plan bugs fixed inline: (1) hash oracle not production because production has ~5e-14 drift from oracle snapshot; (2) indent check needed 2-space-presence evidence (not 4-space absence) since 2-level nesting legitimately has 4 leading spaces in 2-space style.
- D-11 SPI mini $5/pt, $6 AUD RT propagated to SPEC.md, CLAUDE.md, system_params.py (operator confirmed)
- system_params.py introduces FORBIDDEN_MODULES_STDLIB_ONLY to block numpy/pandas in Phase 2 pure-math hex (sizing_engine.py, system_params.py)
- D-17 enforced: compute_unrealised_pnl takes explicit cost_aud_open (no multiplier-lookup coupling)
- SIZE-05 no-floor confirmed: int() truncation returns 0 with size=0: warning when undersized
- D-15 enforced via del atr in get_trailing_stop + check_stop_hit: stop distance uses position['atr_entry'] (entry-ATR anchor), not the atr argument
- D-12 stateless invariant: check_pyramid evaluates only (level+1)*atr_entry threshold — add_contracts is always 0 or 1 (gap-day cap proven by TestPyramid gap tests)
- B-1 NaN policy: get_trailing_stop NaN atr_entry->nan; check_stop_hit NaN high/low/atr_entry->False; check_pyramid NaN->hold level (D-03 generalisation)
- B-4 dual-maintenance accepted for phase2 fixtures: regenerate_phase2_fixtures.py reimplements sizing math inline without importing sizing_engine.py so production bugs surface as fixture mismatches
- D-15 entry-ATR anchor: fixture helpers pass prev[atr_entry] not today's ATR to trailing stop and stop-hit math
- D-12 pyramid stateless invariant hardcoded in regenerator: inline assert add_contracts==1 inside pyramid_gap fixture builder catches recipe bugs at generation time
- D-16: peak/trough update via shallow copy BEFORE exit logic in step() so stop level uses bar's updated high/low
- D-18: pyramid application uses dict spread pattern for grep-auditable AC compliance
- A2: is_forced_exit flag prevents new sizing on ADX-drop or stop-hit days
- B-4: regenerator oracle reimplements step() inline without importing sizing_engine (dual-maintenance by design)

### Todos Carried Forward

- [ ] Confirm SPI contract multiplier with operator's broker at Phase 2 kickoff ($25/pt full ASX 200 vs $5/pt SPI mini)
- [ ] Verify Resend sender domain (`signals@carbonbookkeeping.com.au`) SPF/DKIM/DMARC before Phase 6 first live send
- [ ] Pin exact yfinance version (not `>=`) in `requirements.txt` at Phase 4; bump deliberately
- [ ] Document Replit Reserved VM path in Phase 7 deployment guide alongside GHA
- [x] **Configurable starting account + contract-size selection** — folded into Phase 8 Hardening on 2026-04-22 as CONF-01 (runtime-configurable starting account) + CONF-02 (per-instrument contract-size tiers). See [.planning/todos/completed/2026-04-22-configurable-starting-account-and-contract-sizes--folded-into-phase-8.md](./todos/completed/2026-04-22-configurable-starting-account-and-contract-sizes--folded-into-phase-8.md) and Phase 8 in ROADMAP.md

### Blockers

None.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260421-723 | Phase 1 REVIEWS pass-2 follow-up: oracle-hash comment + test_compute_indicators_is_idempotent + tests/regenerate_scenarios.py | 2026-04-21 | 2ace992 | [260421-723-add-oracle-hash-comment-test-compute-ind](./quick/260421-723-add-oracle-hash-comment-test-compute-ind/) |

### Warnings (roadmap-level)

- Requirements count reconciliation: prompt stated 67 v1 requirements; REQUIREMENTS.md contains 78 across 11 categories. All 78 are mapped. Verify at Phase 1 kickoff that the operator's intent matches.

## Session Continuity

- **Last action:** Executed Plan 01-06 (final gate) — appended TestDeterminism class (19 tests) to `tests/test_signal_engine.py` (409 → 649 lines). 16 SHA256 snapshot tests lock the oracle bit-level trust anchor (D-14) against committed snapshot.json; test_forbidden_imports_absent AST-walks signal_engine.py against the FORBIDDEN_MODULES blocklist (REVIEWS STRONGLY RECOMMENDED); test_no_four_space_indent uses tokenize-aware 2-space-evidence check (REVIEWS POLISH / Gemini). Two Rule-1 plan bugs fixed inline: (1) hash oracle not production because production has ~5e-14 drift from oracle snapshot; (2) indent check needed 2-space-presence evidence (not 4-space absence) since nested code legitimately has 4 leading spaces in 2-space style. 99/99 full suite green; ruff clean; regenerate_goldens.py idempotent. Requirements SIG-01..SIG-08 all marked complete. Commit: 14d3ecd (test Task 1, Task 2 verification-only).
- **Next action:** Run `/gsd-verify-work 1` to run the phase verifier. Phase 1 has shipped; if verifier exits clean, phase closes and Phase 2 (Sizing & Exits) planning can commence via `/gsd-discuss-phase 2`.
- **Files ready for review:**
  - `.planning/ROADMAP.md` — full phase detail + success criteria
  - `.planning/REQUIREMENTS.md` — traceability table populated
  - `.planning/PROJECT.md` — unchanged
- **Research flags to revisit during phase planning:**
  - Phase 1: trailing-stop convention and contract multipliers need operator sign-off at plan-check
  - Phase 7: GHA-vs-Replit primary-path inversion needs operator confirmation (already baked in, but flag anyway)

---
*State initialised: 2026-04-20 at roadmap creation*

**Planned Phase:** 7 (Scheduler + GitHub Actions Deployment) — 3 plans — 2026-04-22T23:09:50.124Z

**Plan 01-02 completed:** 2026-04-20T19:49:00Z — 3 tasks, 3 files created (tests/oracle/wilder.py, tests/oracle/mom_rvol.py, tests/oracle/test_oracle_self_consistency.py), 17 self-consistency tests passing, requirements SIG-01..SIG-04 marked complete.

**Plan 01-03 completed:** 2026-04-20T20:01:00Z — 2 tasks, 28 files created: 2 canonical yfinance fixtures (^AXJO + AUDUSD=X) with provenance READMEs per R-03; 9 deterministic scenario fixtures + scenarios.README.md per D-16; tests/regenerate_goldens.py offline pipeline per D-04; 2 canonical golden CSVs + 9 scenario JSONs + SHA256 determinism snapshot per D-14. Split-vote scenario verified via Mom1=+0.058, Mom3=-0.043, Mom12=-0.003 ⇒ FLAT per SIG-08 (MUST FIX compliance). Requirements SIG-01..SIG-08 are now covered end-to-end by fixtures + goldens (pending Plan 04/05 production tests).

**Plan 01-04 completed:** 2026-04-20T20:13:24Z — 2 tasks, 2 files created (signal_engine.py 193 lines, tests/test_signal_engine.py 213 lines). Production compute_indicators matches oracle goldens to 5.7e-14 worst case across 8 indicators × 2 canonical fixtures (1e-9 plan tolerance). `_wilder_smooth` implements NaN-strict seed-window rule matching oracle bit-for-bit (REVIEWS MEDIUM). `_assert_index_aligned` helper fires before every `assert_allclose` (REVIEWS MEDIUM). 38 TestIndicators tests pass; 55/55 full suite green; ruff clean. Requirements SIG-01..SIG-04 marked complete. Commits: a0ab525 (feat Task 1), f75151a (test Task 2).

**Plan 01-05 completed:** 2026-04-20T20:22:46Z — 2 tasks, 2 files modified (signal_engine.py 193 → 254 lines; tests/test_signal_engine.py 213 → 409 lines). `get_signal(df) -> int` (D-06 bare int, NaN-abstaining 2-of-3 vote gated by ADX >= 25) and `get_latest_indicators(df) -> dict` (D-08 8-key lowercase dict, every value explicit `float()` cast per REVIEWS POLISH) appended after existing compute_indicators. TestVote (9 parametrized scenarios + 6 named SIG-05..08 shortcuts) + TestEdgeCases (D-09 NaN ADX, D-10 Mom12 NaN 2-of-2, D-11 flat-price NaN, D-12 RVol 0.0, 3 threshold-equality tests for ADX==25 and Mom==±0.02, 3 get_latest_indicators contract tests) cover SIG-05..08 + D-09..12 + REVIEWS STRONGLY RECOMMENDED + REVIEWS POLISH. Split-vote scenario verified FLAT end-to-end (REVIEWS MUST FIX closed). 63/63 tests in tests/test_signal_engine.py pass; 80/80 full-suite green; ruff clean. Requirements SIG-05..SIG-08 marked complete. Commits: b0ebeb3 (feat Task 1), 675b713 (test Task 2).

**Plan 01-06 completed:** 2026-04-20T20:35:36Z — Final Phase 1 gate. 1 file modified (tests/test_signal_engine.py 409 → 649 lines; +240). Appended TestDeterminism class with 19 tests: 16 SHA256 snapshot regression (2 fixtures × 8 indicators, hashes ORACLE output per D-14 trust-anchor design — production has ~5e-14 drift below the 1e-9 tolerance gate); test_forbidden_imports_absent (AST blocklist per REVIEWS STRONGLY RECOMMENDED — FORBIDDEN_MODULES includes datetime/os/subprocess/socket/time/json/pathlib/requests/urllib/http/state_manager/notifier/dashboard/main/schedule/dotenv/pytz/yfinance); test_signal_engine_has_core_public_surface (hasattr contract for compute_indicators/get_signal/get_latest_indicators/LONG/SHORT/FLAT); test_no_four_space_indent (tokenize-aware 2-space-evidence check per REVIEWS POLISH). Two Rule-1 plan bugs fixed inline: (1) hash oracle not production because production has ~5e-14 drift from oracle snapshot; (2) indent check needed 2-space-presence evidence (not 4-space absence) since nested code legitimately has 4 leading spaces in 2-space style. 99/99 full suite green (0.60s); ruff clean; `python tests/regenerate_goldens.py` idempotent (zero git diff on oracle goldens + snapshot.json). Phase 1 SHIPPED — all 8 SIG requirements have named passing tests, determinism snapshot locked, hex boundary enforced. Commit: 14d3ecd (test Task 1; Task 2 verification-only under same commit).
