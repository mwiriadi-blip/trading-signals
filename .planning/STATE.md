# STATE — Trading Signals

**Last updated:** 2026-04-20 (roadmap created)

## Project Reference

- **Name:** Trading Signals — SPI 200 & AUD/USD Mechanical System
- **Core value:** Deliver an accurate, reproducible daily signal and actionable instruction to one email inbox every weekday at 08:00 AWST — with full state persistence so P&L, positions, and trade history survive restarts.
- **Operator:** Marc (Perth, AWST UTC+8 no DST)
- **Current focus:** Roadmap created; ready to plan Phase 1 (and optionally Phase 3 in parallel)

## Current Position

- **Milestone:** v1 — Mechanical Signal System
- **Phase:** — (pre-Phase 1, awaiting `/gsd-plan-phase 1`)
- **Plan:** —
- **Status:** Roadmap approved, not yet in planning
- **Progress:** 0/8 phases complete

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

## Accumulated Context

### Decisions

| Decision | Phase | Rationale |
|----------|-------|-----------|
| GitHub Actions is the PRIMARY deployment path (Replit documented as alternative) | 7 | Replit Autoscale doesn't guarantee filesystem persistence and kills `schedule` loops; GHA is free, stateless-by-design, and commits `state.json` back to the repo |
| `n_contracts == 0` skips the trade and warns (no `max(1, …)` floor) | 2 | A `max(1, …)` floor silently breaches the 1% risk budget on small accounts; skipping with a visible warning keeps risk discipline |
| LONG→FLAT (and SHORT→FLAT) closes the open position | 2 | Unambiguous semantics: FLAT means "no position", so any non-matching signal closes |
| Trailing stops use intraday HIGH/LOW for both peak updates and hit detection | 2 | Consistent intraday convention matches how the backtest was built; close-only convention would diverge from reconciliation data |

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

- **Last action:** Roadmap created with 8 phases (fine granularity); all 78 v1 requirements mapped; operator decisions baked into Phase 2 and Phase 7 goals.
- **Next action:** Run `/gsd-plan-phase 1` (Signal Engine Core — Indicators & Vote). Optionally run `/gsd-plan-phase 3` in parallel (State Persistence) — the two share no code.
- **Files ready for review:**
  - `.planning/ROADMAP.md` — full phase detail + success criteria
  - `.planning/REQUIREMENTS.md` — traceability table populated
  - `.planning/PROJECT.md` — unchanged
- **Research flags to revisit during phase planning:**
  - Phase 1: trailing-stop convention and contract multipliers need operator sign-off at plan-check
  - Phase 7: GHA-vs-Replit primary-path inversion needs operator confirmation (already baked in, but flag anyway)

---
*State initialised: 2026-04-20 at roadmap creation*
