# Phase 28: v1.2 UAT Closure - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-10
**Phase:** 28-v1-2-uat-closure
**Areas discussed:** Phase 26 sign-off basis, VERIFICATION.md format, Helper artefacts, Failure handling

---

## Phase 26 sign-off basis

### Q1 — How should the 6 Phase 26 UATs be signed off in VERIFICATION.md?

| Option | Description | Selected |
|--------|-------------|----------|
| Re-run all 6 in browser | Operator opens prod droplet on Chrome (and iPhone Safari for relevant ones), walks through each, records observed behaviour + screenshot. Slow but produces fresh operator evidence. Honours the literal text of DEBT-01. | ✓ |
| Sign off on automated coverage | VERIFICATION.md cites the xfail-flipped-green pytest cases per 26-UAT.md as evidence chain. Fast. Risk: only operator-eye check is informal use. | |
| Hybrid — mandatory subset only | Browser-run the 2-3 scenarios where pytest can NOT cover user-visible behaviour, sign off the rest on automated coverage. | |
| You decide | Use judgment to balance audit integrity vs effort. | |

**User's choice:** Re-run all 6 in browser
**Notes:** Locks D-01 in CONTEXT.md.

### Q2 — Which client environment(s) for the Phase 26 browser re-run?

| Option | Description | Selected |
|--------|-------------|----------|
| Desktop Chrome only | All 6 scenarios on macOS Chrome. Simplest. Phase 26 was originally designed for desktop multi-tab. | |
| Desktop Chrome + iPhone Safari | Both desktop and mobile. Heavier but produces evidence multi-tab nav doesn't break on mobile Safari. | ✓ |
| Desktop Chrome + Firefox | Cross-browser desktop, no mobile. | |

**User's choice:** Desktop Chrome + iPhone Safari, with Chrome driven via MCP
**Notes:** User explicitly added "Run Chrome, Iphone Safari in MCP" — material shift: Claude drives Chrome via MCP for desktop scenarios, operator does iPhone Safari manually. This locked D-02 / D-03.

### Q3 — How should the operator-observed evidence be recorded per scenario?

| Option | Description | Selected |
|--------|-------------|----------|
| Text PASS/FAIL + 1-line note | Each scenario gets a row with status + one-line observed-behaviour. No screenshots. Lowest friction. | ✓ |
| Text + screenshot path per scenario | PASS/FAIL + screenshot saved under .planning/phases/28-*/screenshots/ and referenced inline. Higher audit value. | |
| Text + screenshot only on visual scenarios | Pragmatic middle: screenshots for visually-verified scenarios, text-only for behavioural. | |

**User's choice:** Text PASS/FAIL + 1-line note
**Notes:** Locks D-06.

### Q4 — Which MCP browser server should drive the Chrome scenarios?

| Option | Description | Selected |
|--------|-------------|----------|
| chrome-devtools-mcp | Real Chrome via DevTools protocol. Strongest for visual verification. lighthouse_audit + take_screenshot. | |
| Claude_in_Chrome (extension) | Drives user's actual Chrome via Claude extension. Useful if user wants to watch live. | |
| playwright MCP | Headless / scripted; cleanest for automated regressions. Less suited for true visual smoke. Good for cookie-persistence + audit-grep scenarios. | ✓ |
| You decide | Per-scenario judgment. | |

**User's choice:** playwright MCP
**Notes:** Symmetric with the persisted `tests/uat/` Playwright specs (Q on Helper artefacts). Locks D-02.

### Q5 — Which non-Phase-26 UATs (Phase 17 + Phase 23) should also be MCP-driven on Chrome?

| Option | Description | Selected |
|--------|-------------|----------|
| Phase 17 cookie persistence (across reload) | Easy to MCP-drive: load /dashboard, click trace toggle, assert cookie set, reload, assert toggle preserved. | ✓ |
| Phase 17 ATR(14) hand-recalc to 1e-6 | MCP scrapes displayed OHLC; Claude recalculates in Python; asserts 1e-6 match. Fully automatable. | ✓ |
| Phase 23 /backtest browser visual smoke | MCP loads /backtest, screenshots, asserts no template-leak artefacts. Visual regression style. | ✓ |
| Phase 23 live yfinance CLI run | Not a browser test — runs via Bash, not MCP. | ✓ (acknowledged as Bash, not MCP) |

**User's choice:** All four (with Q23 CLI run as Bash, not MCP)
**Notes:** This collapses the operator-manual scope to just Phase 17 iOS Safari tap-to-toggle. Locks D-03 / D-04 / D-05.

---

## VERIFICATION.md format

### Q1 — Top-level structure: how should the 8 scenarios be grouped?

| Option | Description | Selected |
|--------|-------------|----------|
| Grouped by source phase | Three sections: ## Phase 17, ## Phase 23, ## Phase 26. Mirrors DEBT-01 enumeration. | ✓ |
| Flat list of 8 scenarios | Single section, source phase as a column. Easier to scan; loses visual tie-back. | |
| Grouped by execution mode | ## MCP-Automated / ## Operator-Manual / ## CLI. Mirrors run plan. | |

**User's choice:** Grouped by source phase
**Notes:** Locks D-07.

### Q2 — Phase 27 frontmatter: keep, simplify, or extend?

| Option | Description | Selected |
|--------|-------------|----------|
| Match Phase 27 verbatim | phase / verified / status / score / overrides_applied / test_suite / notes. score = 8/8 scenarios verified. | ✓ |
| Extend with run-mode breakdown | Phase 27 fields PLUS automated_count / manual_count / mcp_screenshots_dir. | |
| Simplify (drop score/overrides) | Just phase / verified / status / notes. Loses at-a-glance count and test-suite gate audit. | |

**User's choice:** Match Phase 27 verbatim
**Notes:** Locks D-08.

### Q3 — Per-scenario row: what columns?

| Option | Description | Selected |
|--------|-------------|----------|
| Scenario / Source / Mode / Status / Evidence | 5 columns, fits in markdown without horizontal scroll. | ✓ |
| Add 'Verified at' timestamp column | 6 columns including UTC timestamp. Redundant with frontmatter `verified` if done in one sitting. | |
| Add 'Acceptance criterion' column | 6 columns including expected outcome. Replaces detailed-evidence section. Heavier rows. | |

**User's choice:** Scenario / Source / Mode / Status / Evidence
**Notes:** Locks D-09.

### Q4 — Detailed evidence sections: keep Phase 27 deep-dive blocks, or drop?

| Option | Description | Selected |
|--------|-------------|----------|
| Drop the deep-dive sections | Table-only document. ~80-120 lines total. | ✓ |
| Keep deep-dive only on FAIL/anomaly | Table for all 8; only FAIL/PASS-with-caveat get a `### Scenario N — Detail` block. | |
| Keep deep-dive on every scenario | Phase 27-style: every scenario gets a full evidence dump. ~300+ lines. | |

**User's choice:** Drop the deep-dive sections
**Notes:** Locks D-10. Deliberate departure from Phase 27 precedent because Phase 28 is 8 manual scenarios, not 14 plans of code.

---

## Helper artefacts

### Q1 — Are Playwright MCP runs one-shot or persisted as reusable scripts?

| Option | Description | Selected |
|--------|-------------|----------|
| One-shot transient | Claude drives MCP live; no scripts saved. Cheapest. | |
| Save as Playwright spec file under tests/ | Each MCP-driven scenario lands as a tests/uat/ spec runnable headless via pytest. | ✓ |
| Save as a markdown UAT runbook only | No code persisted; markdown doc lists exact MCP/CLI commands. | |

**User's choice:** Save as Playwright spec file under tests/
**Notes:** Locks D-12 / D-13.

### Q2 — What scaffolding for the iPhone Safari operator-manual scenario?

| Option | Description | Selected |
|--------|-------------|----------|
| Inline checklist in VERIFICATION.md only | One row in the table with an Acceptance note. No separate doc. | ✓ |
| Separate 28-OPERATOR-CHECKLIST.md | Standalone doc with detailed steps; signed-off rows pasted back into VERIFICATION.md. | |
| Pre-recorded video + checklist | Operator records screen-cap video, links from VERIFICATION.md. | |

**User's choice:** Inline checklist in VERIFICATION.md only
**Notes:** Locks D-14.

### Q3 — Where exactly should the persisted Playwright specs live?

| Option | Description | Selected |
|--------|-------------|----------|
| tests/uat/ + pytest-playwright | New tests/uat/*.py using pytest-playwright. Default pytest skips them; `pytest -m uat` runs. Same toolchain as existing 2006 tests. | ✓ |
| tests/playwright/ + standalone runner | Separate Playwright TypeScript or Python via `npx playwright test`. Isolated from pytest. New toolchain. | |
| tests/integration/uat_v1_2/ + pytest + httpx | Skip Playwright entirely — use httpx + BeautifulSoup. Loses true browser semantics. | |

**User's choice:** tests/uat/ + pytest-playwright
**Notes:** Locks D-12.

### Q4 — Phase 23 live yfinance CLI run: how do we capture it?

| Option | Description | Selected |
|--------|-------------|----------|
| Run live + paste rc + tail output into VERIFICATION.md | Live run during Phase 28; rc + last 10 stdout lines as Evidence. No persisted test. | ✓ |
| Run live AND save as tests/uat/test_backtest_live.py @pytest.mark.live | Live run produces evidence; same flow lands as slow-marked pytest test. | |
| Reference the most recent prod backtest log | Don't re-run; cite last successful prod scheduler-driven backtest. Cheapest, weakest. | |

**User's choice:** Run live + paste rc + tail output into VERIFICATION.md
**Notes:** Locks D-15. Conscious decision NOT to persist live-yfinance as a pytest test (would couple test suite to live network availability).

---

## Failure handling

### Q1 — If a UAT scenario fails during Phase 28 — what's the policy?

| Option | Description | Selected |
|--------|-------------|----------|
| Halt + open v1.2.x patch immediately | First failing scenario halts Phase 28. VERIFICATION.md only ever closes with status: passed. | |
| Aggregate all + roll into Phase 29 | All 8 scenarios run regardless of intermediate FAILs. Phase 29 absorbs fixes. | ✓ |
| Aggregate, then auto-spawn fix tasks at end | Run all 8. At end, if FAILs, create hotfix tasks under Phase 28. | |

**User's choice:** Aggregate all + roll into Phase 29
**Notes:** Locks D-16. Phase 29 is already the patch-wrap phase by design.

### Q2 — What's the threshold for genuine FAIL vs flake?

| Option | Description | Selected |
|--------|-------------|----------|
| Re-run twice; still failing = real fail | 3 attempts max. Standard flake-tolerance. | ✓ |
| Re-run once; still failing = real fail | 2 attempts max. Faster; risks classifying transient blips. | |
| No retries | First attempt canonical. Strictest. Likely too strict for live-network UATs. | |

**User's choice:** Re-run twice; still failing = real fail
**Notes:** Locks D-17.

### Q3 — When Phase 28 closes with FAILs, what `status` value?

| Option | Description | Selected |
|--------|-------------|----------|
| passed-with-deferrals | Mirrors v1.2 retroactive-close pattern. Conveys: phase done, fixes in Phase 29. | |
| failed | Strict. Signals v1.2 didn't close cleanly. Forces explicit decision before v1.3 substance. | |
| partial | Compromise; doesn't match Phase 27 precedent (only used `passed`). | ✓ |

**User's choice:** partial
**Notes:** Locks D-18. Intentional vocabulary extension; planner notes this in frontmatter `notes:`.

### Q4 — Minimum extra info per FAIL Evidence cell?

| Option | Description | Selected |
|--------|-------------|----------|
| 1-line symptom only | Phase 29 re-investigates from scratch. | |
| Symptom + suspected layer + reproduction command | Phase 29 starts with a real lead. Modest extra effort. | ✓ |
| Full mini-debug entry | Heaviest. Risks turning Phase 28 into Phase 29 ahead of schedule. | |

**User's choice:** Symptom + suspected layer + reproduction command
**Notes:** Locks D-19.

---

## Claude's Discretion

- Exact wording of each iPhone Safari acceptance note in the table.
- Whether Phase 26 UAT-2..6 multi-tab scenarios render as 5 rows or 1 row-group (planner default lean: 5 rows per D-11).
- Exact Playwright assertion shape per scenario.
- Where Playwright traces / screenshots get written if a run fails (default `tests/uat/_traces/` gitignored).

## Deferred Ideas

- Cross-browser desktop check (Firefox) — no Chrome-specific suspicion on record.
- Per-scenario screenshot evidence in VERIFICATION.md — D-06 locks text-only.
- Pre-recorded video of the iPhone Safari run — D-14 keeps inline-checklist-only.
- Separate `28-OPERATOR-CHECKLIST.md` doc — D-14 keeps inline.
- Halt-on-first-FAIL with same-phase hotfix — D-16 routes to Phase 29.
- `status: failed` on FAIL — D-18 uses `partial` instead.
