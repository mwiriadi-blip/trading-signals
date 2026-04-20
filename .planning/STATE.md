---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
current_plan: 6
status: executing
last_updated: "2026-04-20T20:25:29.182Z"
progress:
  total_phases: 8
  completed_phases: 0
  total_plans: 6
  completed_plans: 5
  percent: 83
---

# STATE — Trading Signals

**Last updated:** 2026-04-20 (roadmap created)

## Project Reference

- **Name:** Trading Signals — SPI 200 & AUD/USD Mechanical System
- **Core value:** Deliver an accurate, reproducible daily signal and actionable instruction to one email inbox every weekday at 08:00 AWST — with full state persistence so P&L, positions, and trade history survive restarts.
- **Operator:** Marc (Perth, AWST UTC+8 no DST)
- **Current focus:** Phase --phase — 1

## Current Position

- **Milestone:** v1 — Mechanical Signal System
- **Phase:** 1 — Signal Engine Core — Indicators & Vote
- **Current Plan:** 6
- **Total Plans:** 6
- **Status:** Executing Phase 1
- **Progress:** [████████░░] 83%

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

### Todos Carried Forward

- [ ] Confirm SPI contract multiplier with operator's broker at Phase 2 kickoff ($25/pt full ASX 200 vs $5/pt SPI mini)
- [ ] Verify Resend sender domain (`signals@carbonbookkeeping.com.au`) SPF/DKIM/DMARC before Phase 6 first live send
- [ ] Pin exact yfinance version (not `>=`) in `requirements.txt` at Phase 4; bump deliberately
- [ ] Document Replit Reserved VM path in Phase 7 deployment guide alongside GHA

### Blockers

None.

### Warnings (roadmap-level)

- Requirements count reconciliation: prompt stated 67 v1 requirements; REQUIREMENTS.md contains 78 across 11 categories. All 78 are mapped. Verify at Phase 1 kickoff that the operator's intent matches.

## Session Continuity

- **Last action:** Executed Plan 01-05 — appended `get_signal(df) -> int` + `get_latest_indicators(df) -> dict` to `signal_engine.py` (193 → 254 lines) and appended TestVote (15 tests) + TestEdgeCases (10 tests) to `tests/test_signal_engine.py` (213 → 409 lines). 9 D-16 scenario fixtures all produce their filename-implied expected_signal; split-vote scenario verified FLAT end-to-end (REVIEWS MUST FIX closed). REVIEWS STRONGLY RECOMMENDED boundary tests pin ADX==25.0 opening gate and Mom==±0.02 abstaining. REVIEWS POLISH `get_latest_indicators` contract verified: every value `type(v) is float`, NaN preserved as `float('nan')` not None. 63/63 tests in tests/test_signal_engine.py pass; 80/80 full-suite green; ruff clean. Requirements SIG-05..SIG-08 marked complete. Commits: b0ebeb3 (feat Task 1), 675b713 (test Task 2).
- **Next action:** Execute Plan 01-06 (architectural guards + determinism SHA256 snapshot + lint guard). Run `/gsd-execute-phase 1` to continue.
- **Files ready for review:**
  - `.planning/ROADMAP.md` — full phase detail + success criteria
  - `.planning/REQUIREMENTS.md` — traceability table populated
  - `.planning/PROJECT.md` — unchanged
- **Research flags to revisit during phase planning:**
  - Phase 1: trailing-stop convention and contract multipliers need operator sign-off at plan-check
  - Phase 7: GHA-vs-Replit primary-path inversion needs operator confirmation (already baked in, but flag anyway)

---
*State initialised: 2026-04-20 at roadmap creation*

**Planned Phase:** 1 (Signal Engine Core — Indicators & Vote) — 6 plans — 2026-04-20T13:11:46.127Z

**Plan 01-02 completed:** 2026-04-20T19:49:00Z — 3 tasks, 3 files created (tests/oracle/wilder.py, tests/oracle/mom_rvol.py, tests/oracle/test_oracle_self_consistency.py), 17 self-consistency tests passing, requirements SIG-01..SIG-04 marked complete.

**Plan 01-03 completed:** 2026-04-20T20:01:00Z — 2 tasks, 28 files created: 2 canonical yfinance fixtures (^AXJO + AUDUSD=X) with provenance READMEs per R-03; 9 deterministic scenario fixtures + scenarios.README.md per D-16; tests/regenerate_goldens.py offline pipeline per D-04; 2 canonical golden CSVs + 9 scenario JSONs + SHA256 determinism snapshot per D-14. Split-vote scenario verified via Mom1=+0.058, Mom3=-0.043, Mom12=-0.003 ⇒ FLAT per SIG-08 (MUST FIX compliance). Requirements SIG-01..SIG-08 are now covered end-to-end by fixtures + goldens (pending Plan 04/05 production tests).

**Plan 01-04 completed:** 2026-04-20T20:13:24Z — 2 tasks, 2 files created (signal_engine.py 193 lines, tests/test_signal_engine.py 213 lines). Production compute_indicators matches oracle goldens to 5.7e-14 worst case across 8 indicators × 2 canonical fixtures (1e-9 plan tolerance). `_wilder_smooth` implements NaN-strict seed-window rule matching oracle bit-for-bit (REVIEWS MEDIUM). `_assert_index_aligned` helper fires before every `assert_allclose` (REVIEWS MEDIUM). 38 TestIndicators tests pass; 55/55 full suite green; ruff clean. Requirements SIG-01..SIG-04 marked complete. Commits: a0ab525 (feat Task 1), f75151a (test Task 2).

**Plan 01-05 completed:** 2026-04-20T20:22:46Z — 2 tasks, 2 files modified (signal_engine.py 193 → 254 lines; tests/test_signal_engine.py 213 → 409 lines). `get_signal(df) -> int` (D-06 bare int, NaN-abstaining 2-of-3 vote gated by ADX >= 25) and `get_latest_indicators(df) -> dict` (D-08 8-key lowercase dict, every value explicit `float()` cast per REVIEWS POLISH) appended after existing compute_indicators. TestVote (9 parametrized scenarios + 6 named SIG-05..08 shortcuts) + TestEdgeCases (D-09 NaN ADX, D-10 Mom12 NaN 2-of-2, D-11 flat-price NaN, D-12 RVol 0.0, 3 threshold-equality tests for ADX==25 and Mom==±0.02, 3 get_latest_indicators contract tests) cover SIG-05..08 + D-09..12 + REVIEWS STRONGLY RECOMMENDED + REVIEWS POLISH. Split-vote scenario verified FLAT end-to-end (REVIEWS MUST FIX closed). 63/63 tests in tests/test_signal_engine.py pass; 80/80 full-suite green; ruff clean. Requirements SIG-05..SIG-08 marked complete. Commits: b0ebeb3 (feat Task 1), 675b713 (test Task 2).
