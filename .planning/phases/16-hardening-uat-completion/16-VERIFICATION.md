---
phase: 16-hardening-uat-completion
verified: 2026-04-29T10:38:00Z
status: partial
score: 4/4 must-haves verified; 2/3 operator-UAT scenarios verified, 1/3 pending per D-17
overrides_applied: 0
re_verifications:
  - date: 2026-04-26T12:30:00Z
    status: human_needed
    note: "Initial pass — all 3 UAT scenarios at `partial`; full verification pending operator walk-through"
  - date: 2026-04-29T10:38:00Z
    status: partial
    note: "UAT-16-A verified 2026-04-27 (Phase 12 HTTPS bring-up). UAT-16-B verified 2026-04-29 (operator inspected production email in Gmail mobile, all 5 D-10 criteria pass; closure unblocked by quick task 260429-sdp commit 879730d which fixed silent scheduler-loop email dispatch regression). UAT-16-C still pending per D-17 escape hatch — gated on organic drift weekday."
human_verification:
  - test: "Wait for organic drift on a real weekday run; open the resulting email in Gmail mobile app and confirm drift banner renders with red/amber border, subject carries [!] prefix, and dashboard shows a matching banner"
    expected: "Drift banner visible in Gmail mobile with correct color; [!] in subject; dashboard banner matches for same instrument"
    why_human: "Requires a live weekday trading day where positions are open and signal disagrees — cannot be synthesised without operator injecting a drifted state; real phone + real Gmail client required to verify Gmail CSS stripping behavior on v1.1 markup"
    blocking_milestone_archive: true
---

# Phase 16: Hardening + UAT Completion Verification Report

**Phase Goal:** Close the v1.0 tech-debt items that were deferred (CHORE-01: F1 full-chain integration test) and complete the Phase 6 HUMAN-UAT scenarios that are now verifiable via the hosted dashboard (CHORE-03). Final gate before v1.1 milestone archive.

**Verified:** 2026-04-26T12:30:00Z
**Status:** VERIFICATION PARTIAL — 4/4 SCs confirmed in code; UAT-16-C (drift banner in real weekday Gmail) explicitly deferred per D-17; all other SCs verified
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `test_full_chain_fetch_to_email` exercises the full chain with boundary-only mocks | VERIFIED | Test exists at `tests/test_integration_f1.py::test_full_chain_fetch_to_email`, passes in 0.92s; asserts `last_email.html`, `dashboard.html`, captured subject, state transitions, trade_log growth, W3 invariant (2 mutate_state calls) |
| 2 | F1 meta-test proves planted regression red-lights | VERIFIED | `test_f1_catches_planted_regression` patches `signal_engine.get_signal` via `patch.object` to return LONG(1); calls same `_assert_f1_outputs` helper under `pytest.raises(AssertionError)`; sanity-check re-run passes without patch; both tests pass |
| 3 | 16-HUMAN-UAT.md has all 3 scenarios marked at minimum `partial` | VERIFIED (partial) | UAT-16-A: partial/2026-04-26 (Mac-dev-proxy evidence); UAT-16-B: partial/2026-04-26 (Path C local-render proof); UAT-16-C: partial/2026-04-26 (structural parity via test_drift_banner_body_parity + D-17 escape hatch applied). Per D-17, `partial` is explicit acceptable closure |
| 4 | STATE.md `## Completed Items` exists with 3 migrated rows; 4 originally-deferred items handled correctly | VERIFIED | `## Completed Items` section present with 3 rows (uat_gap + 2 verification_gap), all stamped `partial` + `2026-04-26`; `## Deferred Items` contains only `quick_task 260421-723` (correct — not v1.1 scope); `uat_gap` and `verification_gap` rows absent from Deferred |

**Score:** 4/4 truths verified (all at `partial` per D-17)

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `tests/test_integration_f1.py` | F1 integration test + meta-test | VERIFIED | 280 lines; 2 test functions + `_setup_f1` scaffold + `_assert_f1_outputs` helper + `_inverted_signal` stub |
| `.planning/phases/16-hardening-uat-completion/16-HUMAN-UAT.md` | 3 UAT scenarios in D-10 5-field schema | VERIFIED | 140 lines; all 3 scenarios (UAT-16-A/B/C) with Scenario ID, archive ref, status=partial, operator date, operator notes |
| `.planning/STATE.md §Completed Items` | 3 migrated rows with ISO dates | VERIFIED | 3 rows present; no `pending` or `—` placeholders; blockquote prose explains partial rationale and D-17 disposition |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `test_full_chain_fetch_to_email` | `main.run_daily_check` | `main.main(['--force-email'])` | WIRED | Test calls `main.main` which invokes `run_daily_check` — no internal composition mocked |
| `_assert_f1_outputs` (shared helper) | Both happy-path and meta-test | Direct call + `pytest.raises(AssertionError)` wrapping | WIRED | Meta-test calls same helper under `pytest.raises`; proves identical invariants that pass normally will fail under planted regression |
| `test_f1_catches_planted_regression` | `signal_engine.get_signal` | `patch.object(signal_engine, 'get_signal', side_effect=_inverted_signal)` | WIRED | Patches at the module-attribute level (not bound import) — survives `import signal_engine` at top of `main.py` |
| STATE.md Completed Items | 16-HUMAN-UAT.md scenarios | Markdown anchor links per D-15 | WIRED | Three rows link to `16-HUMAN-UAT.md §UAT-16-A/B/C` with fragment anchors |

---

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|--------------------|--------|
| `test_full_chain_fetch_to_email` | `email_html` | `last_email.html` written by `notifier.send_daily_email` | Yes — full chain: yf.Ticker fixture → signal_engine → sizing_engine → state_manager.mutate_state → dashboard.render_dashboard → notifier.compose_email_body | FLOWING |
| `_assert_f1_outputs` (W3 invariant) | `mutate_calls` | Counter wrapper wrapping real `state_manager.mutate_state` (call-through, not replacement) | Yes — increments on real mutate_state calls; asserts exactly 2 | FLOWING |
| STATE.md §Completed Items | `partial/2026-04-26` dates | Read verbatim from `16-HUMAN-UAT.md` per REVIEWS H-3 | Yes — values copied directly from operator-updated UAT artifact | FLOWING |

---

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| F1 happy-path passes | `pytest tests/test_integration_f1.py -v` | 2 passed in 0.92s | PASS |
| F1 meta-test proves regression detection | Included above (same run) | `test_f1_catches_planted_regression` PASSED | PASS |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|---------|
| CHORE-01 | 16-02-PLAN.md | F1 full-chain integration test | SATISFIED | `tests/test_integration_f1.py` exists with 2 passing tests; both SC-1 and SC-2 closed per 16-02-SUMMARY.md |
| CHORE-03 | 16-03-PLAN.md / 16-04-PLAN.md | Phase 6 HUMAN-UAT completion + STATE.md cleanup | SATISFIED (partial) | `16-HUMAN-UAT.md` has all 3 scenarios with operator notes; STATE.md migrated 3 rows per D-14/D-15; `partial` per D-17 is explicit acceptable closure |

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None found | — | — | — | — |

Scanned `tests/test_integration_f1.py`: no TODO/FIXME/placeholder comments; no empty implementations; all assertions verify live runtime behavior per 16-02-SUMMARY.md "Known Stubs: None".

---

## Human Verification Required

### 1. UAT-16-C: Drift Banner in Real Weekday Gmail

**Test:** Wait for organic drift on a real weekday run (position open + signal disagrees). When the 08:00 AWST email arrives with a drift banner present:
- Open the email in Gmail mobile app (not web client)
- Confirm drift banner renders with expected red/amber border
- Confirm subject carries `[!]` critical prefix
- Open `https://signals.<owned-domain>.com/` — confirm matching banner for same instrument (lockstep parity check)
- Capture screenshots of BOTH email and dashboard for same drift event

**Expected:** Both email and dashboard show the drift banner with correct color tier; `[!]` in subject; text matches between the two views

**Why human:** Requires a live weekday trading day with real positions open and disagreeing signal — cannot be synthesised without operator injecting a drifted state (operator declined synthetic injection per CONTEXT Deferred Ideas). Real phone + real Gmail client needed to verify Gmail's CSS stripping on v1.1 markup.

**Per D-17:** This item does not gate Phase 16 closure. Phase 16 closes with `PARTIAL` status until UAT-16-C flips to `verified`. When the operator observes the drift event:
1. Update `16-HUMAN-UAT.md §UAT-16-C` → `verified` with the observation date and screenshots
2. Re-run `/gsd-verify-work 16` to close Phase 16 fully

---

## Detailed SC Verification

### SC-1: Full-chain test asserts correct things

`test_full_chain_fetch_to_email` was verified against all ROADMAP SC-1 requirements:

- **yfinance mocked at `data_fetcher.yf.Ticker`** — confirmed at line 73 of test file; this is the implementation-equivalent of ROADMAP's `requests.get` boundary (yfinance wraps requests internally; documented in module docstring and REVIEWS M-3 note)
- **`run_daily_check` invoked via `main.main(['--force-email'])`** — line 226; no internal composition mocked
- **`state_manager.save_state` runs live** — atomic write path exercised; W3 invariant asserts `mutate_state` called exactly twice (lines 210-213)
- **`dashboard.render_dashboard` exercised** — `dashboard.html` existence asserted (line 157); `sentinel-banner` CSS marker asserted (line 162); `id="heading-signals"` asserted (line 166)
- **`notifier.send_daily_email` dispatch stubbed at `_post_to_resend`** — confirmed at line 83; `last_email.html` written and assertions applied
- **`last_email.html` assertions cover signal + equity** — `FLAT` label (line 137), `SPI 200` display name (line 135), `AUD / USD` display name (line 136), `$` equity prefix (line 138), ISO date in subject (lines 176-178), `SPI200` in subject (line 179), `AUDUSD` in subject (line 180)
- **No internal composition mocked** — signal_engine, sizing_engine, state_manager, dashboard, notifier all run live

### SC-2: Meta-test proves planted regression red-lights

`test_f1_catches_planted_regression`:
- Patches `signal_engine.get_signal` via `patch.object` with `side_effect=_inverted_signal` which returns `1` (LONG) instead of canonical `0` (FLAT)
- With LONG signals, the chain skips FLAT-closure path → email shows LONG labels → `'FLAT' in email_html` assertion in `_assert_f1_outputs` fails
- `pytest.raises(AssertionError)` confirms the SAME helper that passes in SC-1 fails under the planted regression
- Sanity check: state re-seeded, patch lifted, same helper passes (proves F1 itself not broken)

### SC-3: 16-HUMAN-UAT.md has all 3 scenarios with documented closure

**2026-04-29 update — UAT-16-A and UAT-16-B both flipped to `verified`:**

| Scenario | Status | Operator Date | Operator Notes Present |
|----------|--------|--------------|----------------------|
| UAT-16-A: Mobile Dashboard | **verified** | 2026-04-27 | Yes — Phase 12 HTTPS bring-up verified curl-through-production proof on signals.mwiriadi.me |
| UAT-16-B: Mobile Gmail | **verified** | 2026-04-29 | Yes — operator inspected 2026-04-29 production email in Gmail mobile, all 5 D-10 criteria pass; pre-requisite fix shipped via quick task 260429-sdp (commit 879730d) which restored email dispatch on the scheduler-loop path |
| UAT-16-C: Drift Banner Weekday | **pending** | — | Yes — structural parity via Phase 15 test; awaiting organic drift on a real weekday per D-17 escape hatch |

Per D-17, UAT-16-C may stay `pending` past Plan 05 completion — verify-work returns PARTIAL until it flips. The phase is "closed with caveat" for UAT-16-C; v1.0 milestone archive blocks on UAT-16-C closure.

### SC-4: STATE.md deferred items correctly migrated

Verified by direct grep on STATE.md:

- `## Completed Items` section exists at line 213
- 3 rows present: `uat_gap` + `verification_gap` (Phase 05) + `verification_gap` (Phase 06)
- All stamped `partial` / `2026-04-26` — no `pending` or `—` placeholders
- `## Deferred Items` section at line 225 contains ONLY `quick_task 260421-723` — the 3 formerly-deferred UAT/verification items are absent from Deferred (confirmed by grep returning no output)
- Blockquote prose explains D-17 disposition for partial closure

---

## Gaps Summary

No blocking gaps for code-side or non-drift UAT. All 4 SCs are observable in the codebase and artifacts. UAT-16-A (mobile dashboard) and UAT-16-B (mobile Gmail email) are now `verified` as of 2026-04-29. The single open item (UAT-16-C real-weekday Gmail drift observation) is an explicit acceptable deferral per D-17 — documented with operator notes, a clear re-verification path, and no ambiguity about what "done" looks like when it triggers.

**Phase status: PARTIAL.** Closes when UAT-16-C flips `pending → verified` after the operator observes a drift banner in a real weekday email. v1.0 milestone archive blocked until then.

---

## 2026-04-29 Re-Verification Notes

The 2026-04-26 initial verification ran at a point where all 3 UAT scenarios were `partial`. Re-verification today (2026-04-29) confirms:

1. **UAT-16-A → verified** (closed 2026-04-27 via Phase 12 HTTPS bring-up; production curl-through-nginx-through-uvicorn proves the hosted dashboard renders the same byte-identical HTML inspected via Mac-dev-proxy on 2026-04-26)
2. **UAT-16-B → verified** (closed 2026-04-29 via real Gmail mobile inspection of the 2026-04-29 production email; all 5 D-10 acceptance criteria confirmed)
3. **UAT-16-C → pending** (unchanged; D-17 escape hatch active)

**Pre-requisite fix that unblocked UAT-16-B:** `_run_daily_check_caught` in main.py was discarding the 4-tuple from `run_daily_check(args)` and silently never invoking `_dispatch_email_and_maintain_warnings` since 2026-04-23 (commit 3279c312). Production droplet daemon ran clean compute pipelines but emitted zero `[Email] ...` log lines for ~7 days. Fixed in quick task `260429-sdp` (commit `879730d`) with regression-test coverage in `TestLoopHappyPathDispatch` (4 tests) + inverted Phase-4 fossil test (`test_default_mode_DOES_send_email_via_immediate_first_run`). Operator separately fixed droplet `.env` (replaced dev-test email config with `signals@mwiriadi.me` + properly scoped Resend API key for the verified `mwiriadi.me` domain).

Plan 16-04 (Wave 3 per REVIEWS H-3) reads operator-marked verification dates from `16-HUMAN-UAT.md` and writes the `STATE.md ## Completed Items` rows. With UAT-16-A and UAT-16-B now verified with real dates, Plan 04 can populate two of the three rows; the UAT-16-C row stays `pending` until that scenario flips.

---

_Initial verification: 2026-04-26T12:30:00Z_
_Re-verified: 2026-04-29T10:38:00Z_
_Verifier: Claude (gsd-verifier)_
