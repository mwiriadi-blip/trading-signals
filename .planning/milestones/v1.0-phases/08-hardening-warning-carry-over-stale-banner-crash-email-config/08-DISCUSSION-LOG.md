# Phase 8: Hardening — Warning Carry-over, Stale Banner, Crash Email, Configurable Account — Discussion Log

> **Audit trail only.** Not consumed by planner/researcher/executor — decisions live in `08-CONTEXT.md`. This log preserves alternatives considered and rationale.

**Date:** 2026-04-23
**Phase:** 08-hardening-warning-carry-over-stale-banner-crash-email-config
**Areas discussed:** Warning banner UX + clear semantics, Error / crash contract, CLI --reset flag surface, State schema + migration

---

## Area 1 — Warning banner UX + clear semantics

### Q1: Banner layout when multiple warning types are active

| Option | Description | Selected |
|--------|-------------|----------|
| One combined banner, all warnings listed | Single prominent box with bulleted list — simplest, loses severity distinction | |
| Separate banners by type (stale → corrupt-reset → warnings) | Three stacked sections with distinct visual weight — more template code | |
| Stale + corrupt top banner; routine warnings fold into compact metadata row | Critical = top; routine = compact 'N warnings — see details' indicator | ✓ |

**Maps to:** D-01.

### Q2: When is state['warnings'] cleared?

| Option | Description | Selected |
|--------|-------------|----------|
| Clear after save_state in run_daily_check (before dispatch) | Embedded in email at build time; lost if Resend fails | |
| Clear only after Resend 2xx (inside notifier) | Persists across failed sends; breaks D-10 sole-writer invariant | |
| Clear after save_state; always write last_email.html as recovery | Compromise: disk artifact recovers missed content; cleared state is simple | ✓ |

**Maps to:** D-02. Operator chose disk-artifact recovery over stateful-resilience — lower complexity, lower risk of breaking Phase 3 D-10 invariant.

### Q3: Warning age filter in email

| Option | Description | Selected |
|--------|-------------|----------|
| Carry all up to MAX_WARNINGS (100) | Simplest; no date filtering | |
| Carry only warnings from single prior run | Notifier-side filter by entry.date == prior run date | ✓ |
| Window-based since last successful send | Needs extra state key + careful window logic | |

**Maps to:** D-03.

### Q4: Subject line change when banner is active

| Option | Description | Selected |
|--------|-------------|----------|
| Prefix [!] for any warning | Uniform; may over-flag | |
| Prefix [!] only for critical (stale + corrupt) | Nuanced; routine warnings don't noise subject | ✓ |
| No subject change — body banner only | Least intrusive | |

**Maps to:** D-04.

---

## Area 2 — Error / crash contract

### Q1: Where does ERR-04 top-level except live?

| Option | Description | Selected |
|--------|-------------|----------|
| --once path only (wrap run_daily_check in main()) | Most surgical; loop uses _run_daily_check_caught | |
| Both --once AND schedule-loop (outside _run_daily_check_caught, around _run_schedule_loop) | Catches catastrophic loop-driver failures too | ✓ |
| Make _run_daily_check_caught fire crash email on catch-all | Minimal new code; risks email storms on repeated crashes | |

**Maps to:** D-05. Trade-off accepted: loop-driver crash now kills the scheduler after crash email (departs from Phase 7's "never-crash ticking" posture for catastrophic failures specifically).

### Q2: Crash email body contents

| Option | Description | Selected |
|--------|-------------|----------|
| Timestamp + exception + last 50 lines of traceback | Minimal, log-style | |
| Full traceback + last-known state summary (signals, account, positions) | More debugging context | ✓ |
| Minimal notification: subject + 'check GHA logs' | Smallest surface; less self-contained | |

**Maps to:** D-06. Operator prefers self-contained debugging info in the crash email itself over having to pull up GHA Actions logs.

### Q3: Crash-email retry policy

| Option | Description | Selected |
|--------|-------------|----------|
| One-shot, best effort | Minimal blocking; system already dying | |
| Reuse Phase 6 retry loop (3 retries + backoff) | Parity with normal sends; up to ~30s hang | ✓ |
| One-shot with 5s timeout | Middle ground | |

**Maps to:** D-07.

### Q4: Resend 5xx — log + state.warnings, or log only?

| Option | Description | Selected |
|--------|-------------|----------|
| Log + append_warning so NEXT email mentions it | Operator sees missed send in next email banner | ✓ |
| Log only (GHA Actions log is the trace) | Simpler architecture; requires operator to watch GHA | |
| Log + dedicated last_send_failure.json file | Separate artifact; another file to manage | |

**Maps to:** D-08. Planner note: notifier must NOT write to state directly — return status tuple to orchestrator, orchestrator calls append_warning (preserves D-10 sole-writer).

---

## Area 3 — CLI --reset flag surface

### Q1: --reset without new flags behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Fall back to current defaults ($100k, mini/standard) | Backward-compatible; no friction | |
| Interactive prompt for each missing value | Friendlier first-run UX; requires TTY | ✓ |
| Require --initial-account explicitly | Forces explicit choice every time | |

**Maps to:** D-09.

### Q2: Validation for --initial-account

| Option | Description | Selected |
|--------|-------------|----------|
| int only, min $1k, no ceiling | Simplest | |
| int only, min $1k, max $100M | Catches obvious typo | |
| float allowed, min $1k, no ceiling | Matches real broker balances | ✓ |

**Maps to:** D-10.

### Q3: Tier label naming

| Option | Description | Selected |
|--------|-------------|----------|
| Keep spec as-is: SPI={mini,standard,full}, AUDUSD={standard,mini} | ROADMAP SC-7 literal; simple CLI | |
| Add 'micro' to both tier tables | Broker-realistic for very-small accounts | |
| Broker-native labels (CFD-mini, Futures-SPI, Spot-FX style) | Product-type + size-class in label | ✓ (direction) |

**Maps to:** D-11. Exact label strings deferred — operator chose "I'd rather type exact names" then said "Continue". Planner to confirm specifics against operator's actual broker. Baseline: instrument-prefixed short labels (spi-mini, spi-standard, spi-full; audusd-standard, audusd-mini).

### Q4: --reset + state.json exists — confirmation flow

| Option | Description | Selected |
|--------|-------------|----------|
| Still prompt YES; reset with new values | Current Phase 3 D-04 flow unchanged | |
| Skip YES if all new flags present | Faster for scripts; riskier | |
| Prompt YES + show preview of new values | Safety gate + diff visibility | ✓ |

**Maps to:** D-12.

### Q5 (follow-up): Non-TTY behavior for --reset without flags

| Option | Description | Selected |
|--------|-------------|----------|
| Detect non-TTY → error requiring explicit flags | Safest; prevents GHA hang | ✓ |
| Detect non-TTY → fall back to current defaults silently | Simpler; silent surprise | |
| Always try stdin; EOF → defaults | Uniform but can hang | |

**Maps to:** D-13.

### Q6 (follow-up): Exact tier label spellings

Operator: "I'd rather type exact names — ask me." When asked in plain text, operator replied "Continue."

**Resolution:** Captured in D-11 as "direction locked, exact strings deferred to planning." Baseline recommendation for planner: instrument-prefixed short labels per SC-7 tier counts. Planner must confirm with operator before execution.

---

## Area 4 — State schema + migration

### Q1: Shape of state['contracts']

| Option | Description | Selected |
|--------|-------------|----------|
| Label-only: {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-standard'} | Single source of truth in system_params; clean | |
| Inlined tier dict: {'SPI200': {'label': ..., 'multiplier': 5, 'cost_aud': 6}} | Reproducibility if tier table changes; state clutter | |
| Label + runtime-only _resolved_contracts (excluded from save) | Hybrid: persist label, resolve on load | ✓ |

**Maps to:** D-14. Introduces new "underscore = runtime-only" convention.

### Q2: _migrate on existing state.json without new keys

| Option | Description | Selected |
|--------|-------------|----------|
| Silently fill defaults (no warning) | Seamless upgrade; operator unaware | ✓ |
| Fill defaults + append warning for next email | Self-documenting upgrade; noise | |
| Fill defaults + log to stdout (no state.warnings) | Middle ground — visible in Actions log | |

**Maps to:** D-15. Matches ROADMAP SC-6 backward-compat intent.

### Q3: CONF-01 propagation — helper vs inline

| Option | Description | Selected |
|--------|-------------|----------|
| Helper _get_initial_account(state) in state_manager | One function, one source of truth | |
| Inline state.get('initial_account', INITIAL_ACCOUNT) at each site | Three call sites duplicate fallback | ✓ |
| After _migrate always has key; unconditional read | Simplest call sites; relies on _migrate invariant | |

**Maps to:** D-16. Defense-in-depth: fallback is redundant after D-15 but safe.

### Q4: CONF-02 wiring — sizing label-aware or value-only?

| Option | Description | Selected |
|--------|-------------|----------|
| Orchestrator resolves; sizing gets explicit multiplier + cost_aud | Preserves Phase 2 D-17 hex-boundary | ✓ |
| sizing_engine.step accepts label, resolves internally | Simpler call site; breaks decoupling | |
| state_manager.resolve_contract helper | Neat but out-of-module | |

**Maps to:** D-17.

---

## Claude's Discretion

- Banner HTML specifics (colors, borders, padding) — pick values consistent with Phase 5/6 visual vocabulary
- `<details>` vs plain list for collapsible warnings (D-01) — fall back to plain list if Gmail interop is spotty
- Error message phrasing for validation failures (D-10, D-11) — concise and actionable
- Test infrastructure: existing pytest + pytest-freezer pattern; monkeypatch `_post_to_resend` for crash-email tests

## Deferred Ideas

- Corrupt-state recovery ergonomics beyond warning banner (ERR-03 extension)
- Subject-line severity tiering beyond single `[!]` flag
- `spi-micro` tier — trivially added if tier dict stays source of truth
- IN-01 through IN-04 from 07-REVIEW.md — still advisory debt from Phase 7 (en-dash fix might fold into Phase 8 if planner has bandwidth)
- Dashboard re-render hook on --reset — natural next-run re-render covers it

---

*Phase: 08-hardening-warning-carry-over-stale-banner-crash-email-config*
*Discussion logged: 2026-04-23*
