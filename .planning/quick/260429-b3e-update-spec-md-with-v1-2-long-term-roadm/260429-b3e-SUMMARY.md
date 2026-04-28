---
quick_id: 260429-b3e
type: quick
status: complete
completed: 2026-04-29
files_modified: [SPEC.md]
files_created: []
commits: [1eb8159]
requirements: [DOCS-V12-ROADMAP]
---

# Quick 260429-b3e: SPEC.md v1.2+ Long-Term Roadmap Append

Appended a reference-only `## v1.2+ Long-Term Roadmap (Reference)` section to SPEC.md verbatim from the operator brainstorm captured 2026-04-29. Pure docs append — zero code/behavior change, v1.1 in-flight work untouched.

## Files Modified

| File | Change | Lines |
|------|--------|-------|
| SPEC.md | Appended new section after DEPLOYMENT CHECKLIST block | 516 → 590 (+74) |

## Section Added

`## v1.2+ Long-Term Roadmap (Reference)` — placed after the existing closing ```` ``` ```` of the DEPLOYMENT CHECKLIST block, separated by `---` horizontal rule. Existing lines 1–516 byte-for-byte unchanged.

### Content captured

- **Vision** — friends-and-family multi-user paper-trade platform with calc transparency, journaling, stop-loss alerts, news, 5y backtest gate
- **Locked decisions table** — 11 rows (paper-only, friends-and-family, TOTP, web form entry, both approaching+hit alerts, yfinance.news, label-only stale policy, >100% 5y backtest gate, per-signal calc transparency, SPI+AUDUSD locked through v1.x, Python locked)
- **Planned phase sequence** — 8 phases (17 calc transparency, 18 multi-user, 19 paper ledger, 20 stop-loss alerts, 21 news, 22 strategy versioning, 23 5y backtest, 23.5 hygiene)
- **Architecture additions** — `auth/`, `ledger/`, `news/`, `backtest/` modules; hex-boundary rule extension; `STRATEGY_VERSION` constant; pyotp/qrcode/passlib deps; SQLite-vs-JSON deferred to Phase 18
- **Hard constraints** — signal-only (never broker API), daily cadence only, Python locked, DO droplet hosting
- **Out of scope through v1.x** — top-10-volume expansion, broker API, intraday/tick, SaaS multi-tenant, websocket, native mobile
- **Open questions** — 5 items deferred to `/gsd-new-milestone v1.2`

## Verification

- `grep -c "^## v1.2+ Long-Term Roadmap (Reference)" SPEC.md` → `1`
- `grep -c "Captured:.*2026-04-29" SPEC.md` → `1`
- `grep -q "Phase 17 — Per-signal calculation transparency" SPEC.md` → pass
- `grep -q "Phase 23 — 5-year backtest validation gate" SPEC.md` → pass
- `wc -l SPEC.md` → `590` (target ≥580)
- `git status --short` (excluding pre-existing macOS `*2*` duplicate-name artifacts unrelated to this task) → `M SPEC.md` only before commit

## Deviations from Plan

None — plan executed exactly as written.

## Commits

| # | Hash | Message |
|---|------|---------|
| 1 | 1eb8159 | docs(260429-b3e): append v1.2+ long-term roadmap reference to SPEC.md |

## v1.1 Impact

Zero. v1.1 in-flight Phases (14, 15, 16, 16.1) untouched. v1.2 work does NOT begin until v1.1 ships per captured note.

## Self-Check: PASSED

- SPEC.md exists at /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/SPEC.md → FOUND
- Commit 1eb8159 → FOUND in git log
- All grep verifications pass
- File line count 590 (≥580 target)
