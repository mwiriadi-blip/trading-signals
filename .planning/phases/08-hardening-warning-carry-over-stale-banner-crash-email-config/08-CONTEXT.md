# Phase 8: Hardening — Warning Carry-over, Stale Banner, Crash Email, Configurable Account — Context

**Gathered:** 2026-04-23
**Status:** Ready for planning

<domain>
## Phase Boundary

Close the "looks done but isn't" gap in production. Three distinct concerns:

1. **Warning pipeline hygiene** (NOTF-10, ERR-03, ERR-05) — warnings written in run N surface as a banner in run (N+1)'s email header; stale state and corrupt-reset get visually distinct banners.
2. **Crash handling** (ERR-02, ERR-04) — a Resend 5xx logs + state.warnings-tracks without crashing; an unhandled exception past the typed-exception boundary attempts one last crash email before exiting non-zero.
3. **Runtime-configurable scaling** (CONF-01, CONF-02) — operator configures `initial_account` + per-instrument contract preset at `--reset` time so the system works for real broker situations (not just SPI mini + $100k).

Scope is strictly the 7 success criteria in ROADMAP.md §Phase 8. No new capabilities; no UX re-design; no new telemetry. Whatever's already in state.json, in the email template, or in the sizing pipeline stays — we add the missing seams.

</domain>

<decisions>
## Implementation Decisions

### Area 1 — Warning banner UX + clear semantics

- **D-01: Two-tier banner layout in the email header.** Stale-state (ERR-05) and corrupt-reset (ERR-03) render as a visually prominent top banner (red/orange tone). Routine warnings (sizing=0, adx<25, Resend-send-failed from prior run) render as a single compact metadata row below the hero — `"N warnings from prior run — see details"` — with the list itself beneath as a small block. Critical banners are always top; routine warnings never dominate. Insertion point: `notifier.py::_render_header_email:455`.

- **D-02: Clear `state['warnings']` after `save_state` in `run_daily_check`; always write `last_email.html` every run.** Flow:
  1. `run_daily_check` builds the email payload reading `state['warnings']` as-of the START of this run.
  2. `save_state` is called with the cleared warnings list (or a new `clear_warnings(state)` helper in `state_manager` to preserve D-10 sole-writer invariant).
  3. `last_email.html` is written to disk every run (success AND failure), not just when RESEND_API_KEY is missing as in Phase 6. Operator can grep this file to recover the content of any missed email.
  4. Dispatch via `_send_email_never_crash` → Resend.
  5. On Resend 5xx, a new warning is appended (see D-08) for NEXT run to surface.

  **Trade-off:** if Resend 5xx on run N+1, warnings from run N are lost from the email but the `last_email.html` on disk captures them. Operator must choose to look. This is acceptable per the "if you're checking email daily, you'll notice the missing one and grep the file" model.

- **D-03: Notifier-side read filter: only warnings dated to the single prior run reach the email.** `_render_header_email` filters `state['warnings']` by `entry.date == prior_run_date` (derived from `state['last_run']` BEFORE this run's save). Older warnings stay in `state['warnings']` for state-inspection / forensic grep but don't clutter every email. Keeps `state_manager` as sole writer — notifier only reads.

- **D-04: Subject line prefix `[!]` ONLY for stale-state (ERR-05) or corrupt-reset (ERR-03) banners.** Routine warnings keep the normal subject format (`SPI LONG / AUDUSD FLAT — 2026-04-24`). Critical banners tell Gmail/inbox-scanners to pay attention; everyday "sized=0 contracts" warnings don't noise the subject.

### Area 2 — Error / crash contract

- **D-05: Layered catch model — two distinct layers, do NOT duplicate.**
  - **Layer A (Phase 7, unchanged):** `_run_daily_check_caught` at `main.py:175` keeps the schedule loop ticking on per-job errors (DataFetchError, ShortFrameError, catch-all Exception). Never kills the loop.
  - **Layer B (Phase 8, new):** An OUTER `except Exception` wraps BOTH the `--once` path AND the `_run_schedule_loop` call in `main()`. This catches catastrophic failures in the loop driver itself — UTC assertion fire, schedule library explosion, import failure inside the loop — that _run_daily_check_caught cannot catch because it's scoped to per-job errors. Layer B fires one crash email (see D-06, D-07), logs, exits non-zero.

  **Trade-off flagged:** Layer B will kill the schedule process if the loop driver crashes. This is a deliberate departure from Phase 7's "never-crash ticking" posture — accepted because a catastrophic loop-driver failure means we CAN'T recover inside the loop anyway. The crash email is the signal that the daemon died and needs operator intervention.

- **D-06: Crash email body = full traceback + last-known state summary.**
  - Subject: `[CRASH] Trading Signals — <ISO date>`
  - Format: text/plain (not HTML — crash is not the moment to worry about styling)
  - Body sections:
    1. Timestamp (ISO, AWST)
    2. Exception class + message
    3. Full `traceback.format_exc()` output
    4. Last-known state summary: current `signals` (both instruments), `account` value, open positions (symbol + direction + n_contracts + entry_price)
  - State summary is derived, NOT a full state.json dump (no `trade_log`, `equity_history`, or `warnings` dumped — keeps email size sane and avoids leaking thousands of lines of trade history in a crash mail).

- **D-07: Crash-email dispatch reuses Phase 6 `_post_to_resend` retry loop (3 retries with backoff).** Accepts the 30+s max hang before process exit for parity with regular sends. GHA default 6h timeout absorbs this comfortably; if IN-01 from 07-REVIEW.md (`timeout-minutes: 10` on the GHA job) lands in a follow-up, the 30s budget still fits within 10 min. Document this in the planner's Pitfalls section.

- **D-08: Resend 5xx → log + `append_warning` via state_manager.** Flow when `_send_email_never_crash` catches a Resend failure:
  1. Log at WARN with `[Email]` prefix: `"Resend POST failed (status=<code>, body=<first 200 chars>)"`.
  2. Return the failure info (status code + body excerpt) up to the caller (`run_daily_check`).
  3. `run_daily_check` calls `state_manager.append_warning(state, source='notifier', message='Previous email send failed (5xx): Resend returned <status>')` to preserve D-10 sole-writer invariant.
  4. NEXT run's email header banner surfaces the missed send.

  **Planner note:** do NOT have notifier write to state directly. Notifier returns a status tuple, orchestrator translates into `append_warning`.

### Area 3 — CLI `--reset` flag surface

- **D-09: `--reset` without new flags → interactive stdin Q&A for each missing value.** Prompts:
  - `"Starting account [$100,000]: "` — accepts blank (default), numeric value with optional `$`/commas, or `q` to abort.
  - `"SPI200 contract preset [<default-label>]: "` — shows the available labels inline.
  - `"AUDUSD contract preset [<default-label>]: "` — same.

  Operator UX: `python main.py --reset` is viable for interactive first-time setup without memorizing all three flags. Scripted invocations still work with explicit flags.

- **D-10: `--initial-account` accepts `float`, min $1,000, no ceiling.** `argparse` `type=float`. Validation: post-parse, if `args.initial_account < 1000`, `parser.error("--initial-account must be at least $1,000")`. Float allows broker-realistic balances like `$25,347.85`. Dashboard total-return formula + email equity reference already format via f-string — no upstream refactor needed for float/int divergence (confirm during planning).

- **D-11: Broker-native short labels for contract tiers (exact spellings deferred).** Direction locked: labels prefix the instrument (e.g., `spi-*`, `audusd-*`) rather than generic `mini/standard/full` so the CLI reads naturally (`--spi-contract spi-mini` is self-documenting vs `--spi-contract mini`). **Exact label strings are deferred to planning** — planner/researcher must confirm the precise label spellings against the operator's actual broker product names before execution. Baseline suggestion for the planner if the operator is unreachable: `SPI200 = {spi-mini, spi-standard, spi-full}`, `AUDUSD = {audusd-standard, audusd-mini}` matching ROADMAP SC-7 tier counts. Tier multiplier + cost values stay per Phase 2 D-11 (SPI mini=$5/$6; standard=$25/$30; full=$50/$50; AUDUSD standard=$10k/$5; mini=$1k/$0.50) unless the operator corrects during planning.

- **D-12: `--reset` confirmation shows a preview of the new values before the `YES` prompt.** Builds on Phase 3 D-04. New prompt shape:
  ```
  This will replace state.json. New values:
    initial_account: $50,000.00
    contracts:
      SPI200:  spi-mini
      AUDUSD:  audusd-standard
  Current state.json:
    initial_account: $100,000.00 (migrated default)
    last_run: 2026-04-22
    trades: 14
  Type YES to confirm, anything else to cancel:
  ```
  Operator sees the delta before committing. No behavior change for flag-less `--reset` (still prompts after Q&A).

- **D-13: Non-TTY behavior (GHA / piped / no stdin): error, require explicit flags.** `if not sys.stdin.isatty()` at the start of the reset flow's Q&A branch, and no other flags given → `parser.error("Non-interactive shell detected. Pass --initial-account <N> --spi-contract <label> --audusd-contract <label> explicitly.")`. Prevents a GHA job from hanging on `input()`.

### Area 4 — State schema + migration

- **D-14: state['contracts'] stores labels; runtime resolves into state['_resolved_contracts'] (runtime-only, excluded from save).**
  ```python
  # persisted in state.json:
  state['contracts'] = {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-standard'}

  # populated by load_state after _migrate, used by callers, excluded from save_state:
  state['_resolved_contracts'] = {
      'SPI200': {'multiplier': 5.0, 'cost_aud': 6.0},
      'AUDUSD': {'multiplier': 10000.0, 'cost_aud': 5.0},
  }
  ```
  Save-side: `save_state` must exclude any key starting with `_` (underscore prefix = runtime-only). Planner to verify the existing `ALLOWED_KEYS` whitelist / save whitelist in `state_manager.py` explicitly blocks `_resolved_contracts`. Source of truth for tier values = `system_params.SPI_CONTRACTS` / `AUDUSD_CONTRACTS` dicts. If tier table ever changes, `load_state` picks up the new values on next load.

- **D-15: `_migrate` fills CONF-01/CONF-02 defaults silently, no warning.** Pre-Phase-8 state.json missing `initial_account` and/or `contracts` → `_migrate` adds them with defaults (`100000` for initial_account; label defaults per D-11). No `append_warning` call. No stdout log. Operator running daily won't notice; operator who inspects state.json will see the defaults are now materialized. Matches ROADMAP SC-6 backward-compat intent.

- **D-16: Inline `state.get('initial_account', system_params.INITIAL_ACCOUNT)` at each call site (dashboard, email).** Not a helper. Three call sites duplicate the fallback:
  - `dashboard.py` total-return formula row
  - `notifier.py` email equity / P&L reference section
  - `sizing_engine.py` or `main.py` reporting lines (if any reference INITIAL_ACCOUNT for account-growth calculations)

  Given D-15 guarantees `_migrate` always backfills the key, the `.get(..., default)` fallback is defense-in-depth (redundant in steady state, safe if someone ever bypasses `_migrate`). Planner must `grep -n "INITIAL_ACCOUNT" <dashboard.py> <notifier.py>` to enumerate exact call sites before refactor.

- **D-17: Orchestrator resolves tier-to-values; sizing_engine receives explicit multiplier + cost_aud parameters (preserves Phase 2 D-17 hex-boundary).** Flow:
  1. `load_state` materializes `state['_resolved_contracts']` (D-14).
  2. `run_daily_check` reads `state['_resolved_contracts']['SPI200']` for the SPI branch and `['AUDUSD']` for the AUDUSD branch.
  3. Passes `multiplier=X, cost_aud_open=Y/2` explicitly to `sizing_engine.step()` (signature already accepts both per Phase 2 D-17).
  4. `sizing_engine` stays pure — no imports of `system_params.SPI_CONTRACTS`, no label vocabulary dependency.

  **Preserves the architectural invariant from Phase 2 deliberately.**

### Claude's Discretion

- Exact string/formatting for the banner HTML (colors, border weights, padding) — pick values consistent with Phase 5/6 visual vocabulary.
- Whether to use `<details>` for the collapsible warnings row (D-01) vs a plain stacked list — Gmail email client support for `<details>` is spotty; fall back to a plain list if the planner finds interop issues.
- Label-validation error messages (D-10, D-11) — pick concise, actionable phrasing.
- Test infrastructure: use the existing pytest + pytest-freezer pattern (Phase 7 TestDotenvLoading style) for crash-email tests; monkeypatch `_post_to_resend`.

### Folded Todos

None — CONF-01 and CONF-02 already folded into the roadmap on 2026-04-22 (per STATE.md §Todos Carried Forward, marked complete). `gsd-sdk query todo.match-phase 8` returned 0 matches.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents (researcher, planner, executor) MUST read these before implementing.**

### Phase spec + scope
- `.planning/ROADMAP.md` §Phase 8 (lines 146-159) — goal, 7 success criteria, requirement IDs, dependency on Phase 7
- `.planning/REQUIREMENTS.md` lines 109, 152-155, 160-161 — NOTF-10, ERR-02, ERR-03, ERR-04, ERR-05, CONF-01, CONF-02 full specs
- `.planning/PROJECT.md` — vision, non-negotiables, stack pin discipline

### Prior-phase decisions that constrain Phase 8
- `.planning/phases/03-state-persistence-with-recovery/03-CONTEXT.md` — D-09/D-10/D-11 warnings schema + MAX_WARNINGS=100 FIFO cap; `_migrate` hook as the canonical backfill point; state_manager is SOLE writer to state.warnings
- `.planning/phases/04-end-to-end-skeleton-fetch-orchestrator-cli/04-CONTEXT.md` — D-11 run_daily_check 4-tuple contract; typed-exception boundary in main(); D-05 --reset exclusivity rule (now relaxed for the new CONF flags — see D-09)
- `.planning/phases/06-email-notification/06-CONTEXT.md` — `_send_email_never_crash` pattern + `_post_to_resend` retry loop (Phase 8 reuses for crash email per D-07); last_email.html fallback (Phase 8 extends per D-02)
- `.planning/phases/07-scheduler-github-actions-deployment/07-CONTEXT.md` — D-01 loop driver + D-02 never-crash wrapper; UTC assertion via `_get_process_tzname()`; Layer A/B split (D-05 this phase) must NOT duplicate `_run_daily_check_caught`
- `.planning/phases/07-scheduler-github-actions-deployment/07-REVIEW.md` — IN-01 (GHA `timeout-minutes`) still deferred; Phase 8 crash-email retry budget (D-07) must fit within whatever timeout lands

### Source files that will be touched
- `state_manager.py` — `_migrate` (D-15), `append_warning` (D-08), `load_state` (D-14 `_resolved_contracts`), `save_state` (D-14 exclusion), possible new `clear_warnings` helper (D-02)
- `notifier.py` — `_render_header_email:455` (D-01 banner), age filter (D-03), subject-line prefix (D-04), always-write last_email.html (D-02), returns status tuple on Resend failure (D-08)
- `main.py` — argparse `_build_parser` + `_validate_flag_combo` (D-09, D-10, D-13), interactive reset Q&A (D-09, D-12), outer crash-email except wrapping both --once and _run_schedule_loop (D-05, D-06, D-07)
- `system_params.py` — new `SPI_CONTRACTS` + `AUDUSD_CONTRACTS` dicts (D-11 vocabulary TBD); `INITIAL_ACCOUNT` constant unchanged (still the fallback default)
- `dashboard.py` — total-return formula reads `state.get('initial_account', INITIAL_ACCOUNT)` (D-16)
- `sizing_engine.py` — unchanged signature, no new imports (D-17 preserves Phase 2 D-17)
- `tests/test_notifier.py`, `tests/test_state_manager.py`, `tests/test_main.py`, `tests/test_scheduler.py` — extended with Phase 8 coverage; planner to enumerate exact test-file deltas

### Architectural invariants (do not break)
- CLAUDE.md §Architecture — hex-lite boundary: signal_engine and state_manager must not import each other; main.py is the only orchestrator
- CLAUDE.md §Conventions — 2-space indent, single quotes, `[Sched] / [State] / [Email] / [Fetch]` log prefixes, atomic state writes via tempfile + fsync + os.replace
- tests/test_signal_engine.py::TestDeterminism — FORBIDDEN_MODULES_* AST blocklists (Phase 8 does NOT add new third-party deps; if planner wants one, flag it loudly)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable assets
- `state_manager.append_warning(state, source, message)` (line 372) — the single writer for `state['warnings']`, FIFO-trimmed at `MAX_WARNINGS=100`. Use verbatim for D-08 (notifier 5xx) and D-15 (no-warning on silent migration means DO NOT call this during _migrate).
- `state_manager._migrate(state)` (line 135) — canonical backfill point for CONF-01 + CONF-02 missing keys (D-15).
- `notifier._send_email_never_crash` + `notifier._post_to_resend` — 3-retry + backoff Resend dispatcher. Reuse wholesale for D-07 crash email (text/plain content with different subject + body).
- `notifier.last_email.html` write path (Phase 6) — extend to always-write per D-02.
- `main._run_daily_check_caught` (line 175) — Phase 7's per-job never-crash wrapper. DO NOT modify for ERR-04; the crash-email layer (D-05) lives OUTSIDE this function.
- `sizing_engine.step()` + `_closed_trade_to_record` — already accept explicit `multiplier` + `cost_aud_open` args (Phase 2 D-17). No change needed for CONF-02; orchestrator just passes the resolved values.

### Established patterns
- Phase 6 pattern: `_send_email_never_crash` wraps dispatch; returns/logs don't propagate. Phase 8 extends by making notifier return a status tuple so orchestrator can `append_warning` on failure (D-08).
- Phase 7 pattern: `_get_process_tzname()` thin wrapper for test-patchability. Consider similar wrapper for `input()` / `sys.stdin.isatty()` so tests can patch without monkey-patching stdin (note for planner).
- Phase 4 D-11 typed-exception boundary in `main()`: catches DataFetchError, ShortFrameError, KeyboardInterrupt → specific exit codes. Phase 8 D-05 adds a FINAL catch-all OUTSIDE this ladder that fires the crash email before exit.
- Phase 3 `_migrate` already handles schema_version bumps. CONF-01/CONF-02 backfill fits the existing pattern (no new migration subsystem needed).

### Integration points
- `main.py` default-mode dispatch (Phase 7) → wrap the existing `_run_daily_check_caught(run_daily_check, args) → _run_schedule_loop(run_daily_check, args)` sequence in `try / except Exception` for D-05 Layer B.
- `main.py` `--once` branch → same outer except wraps the `run_daily_check(args)` call for D-05 Layer B in one-shot mode.
- `main.py` `--reset` branch → insert the interactive Q&A (D-09) + preview (D-12) + non-TTY guard (D-13) before the confirmation prompt.
- `state_manager.load_state` → after `_migrate`, materialize `state['_resolved_contracts']` from the label lookups (D-14). `save_state` → filter out underscore-prefixed keys before JSON write.

</code_context>

<specifics>
## Specific Ideas

- **Broker-native label vocabulary direction locked (D-11); exact strings deferred.** Operator preferred instrument-prefixed labels (e.g., `spi-mini`, `audusd-standard`) over generic tier labels. Planner/researcher to confirm exact label strings with operator before execution — baseline above, but check if the operator's actual broker names them differently.

- **Two-tier banner semantics are specific:** stale-state + corrupt-reset are visually distinct from routine warnings. Keep "critical = top-of-email box with prefix `[!]` in subject", "routine = compact metadata line with a count + list". Don't merge them into one list.

- **Crash-email parity with regular emails:** full retry loop, not one-shot. Operator values "this better actually arrive" over "don't hang on exit".

- **`_resolved_contracts` runtime-only-field convention:** underscore prefix = transient, never persisted. New convention this phase; document in CLAUDE.md Conventions section during planning so future devs don't accidentally add it to `save_state` whitelist.

</specifics>

<deferred>
## Deferred Ideas

- **ERR-03 corrupt-state recovery ergonomics beyond the warning banner:** if corrupt-state detection becomes common, consider a "recover from last git-committed state.json" path. Out of scope for Phase 8 — CONF-01's backup-and-reinit is sufficient for v1.
- **Subject-line severity tiering beyond `[!]`:** e.g., `[CRITICAL]` vs `[!]` vs `[WARN]`. Single `[!]` flag keeps parsing simple for v1. Revisit if operator finds `[!]` too uniform.
- **Adding a "spi-micro" tier** (D-11 area 3 option b) — practice-account-scale for very-small accounts. Not requested now; trivially added later if the tier dict stays the source of truth.
- **IN-01 GHA `timeout-minutes` from 07-REVIEW.md** — still deferred. Phase 8 crash-email retry budget (30s max) fits within a 10-minute default, so adding `timeout-minutes: 10` to daily.yml is a safe follow-up post-Phase-8. Not blocking.
- **IN-02 README GHA badge literal `${{GITHUB_REPOSITORY}}` placeholder** — cosmetic, forker-only. Deferred from 07-REVIEW.md.
- **IN-03 TestWeekdayGate fake returning `None`** — test-quality polish. Deferred from 07-REVIEW.md.
- **IN-04 en-dash in `[Sched] scheduler entered` log line** — one-byte fix. Deferred from 07-REVIEW.md; operator may want to fold it into Phase 8 if the planner has bandwidth.
- **Dashboard re-render after `--reset` with new initial_account:** dashboard rendering is triggered on every run_daily_check, so the new values will surface in the next email naturally. No separate "reset also re-renders" hook needed for v1.

</deferred>

---

*Phase: 08-hardening-warning-carry-over-stale-banner-crash-email-config*
*Context gathered: 2026-04-23*
