---
gsd_state_version: 1.0
milestone: v1.2
milestone_name: - **Signal-only.** No broker API, ever
status: verifying
last_updated: "2026-05-07T23:27:37.282Z"
last_activity: 2026-05-07
progress:
  total_phases: 8
  completed_phases: 7
  total_plans: 45
  completed_plans: 41
  percent: 91
---

# STATE — Trading Signals

**Last updated:** 2026-04-24 (v1.1 roadmap created by /gsd-roadmapper)

## Project Reference

- **Name:** Trading Signals — SPI 200 & AUD/USD Mechanical System
- **Core value (v1.0, validated):** Deliver an accurate, reproducible daily signal and actionable instruction to one email inbox every weekday at 08:00 AWST — with full state persistence so P&L, positions, and trade history survive restarts.
- **Core value (v1.1, in progress):** Transform the email-only v1.0 CLI into a hosted, interactive trade journal at `signals.<owned-domain>.com` — a single URL viewable from any device, POST-able for recording executed trades, with live stop-loss + pyramid guidance and position-vs-signal drift sentinels.
- **Operator:** Marc (Perth, AWST UTC+8 no DST)
- **Current focus:** Phase 27 — code-quality-correctness-sweep

## Current Position

Phase: 27 (code-quality-correctness-sweep) — EXECUTING
Plan: 27-05 (Wave 1C) complete — 7 of 14 plans landed (27-07, 27-06, 27-02, 27-03, 27-04, 27-01, 27-05)
Plans: 3/3 executed + verified. All AUTH-04..AUTH-12 requirements green at code + test level. 17 plan commits + 3 SUMMARY.md + 1 VERIFICATION.md (5e77154). Phase code is shippable; only blocker is the 7-scenario operator UAT runbook in `.planning/phases/16.1-phone-friendly-auth-ux-for-dashboard-access/16.1-HUMAN-UAT.md` which requires a real iPhone (Safari + Chrome).

- **Milestone:** v1.1 — Interactive Trading Workstation
- **Status:** Phase complete — ready for verification
- **Last activity:** 2026-05-07
- **Progress:** [█████████░] 91%
- **v1.2 status:** PLANNING (REQUIREMENTS.md + ROADMAP.md created 2026-04-30; awaiting `/gsd-plan-phase 17` or `/gsd-plan-phase 22` to start Wave 1).

### Resume instructions for cloud Claude / fresh clone

```
git clone https://github.com/mwiriadi-blip/trading-signals.git
cd trading-signals

# Cloud Claude SessionStart hook auto-loads:

#   - global ~/.claude/LEARNINGS.md (cloud's own copy — separate sync mechanism)

#   - project-local .claude/LEARNINGS.md (5 trading-signals patterns from 2026-04-27)

#   - CLAUDE.md (project conventions)

#   - .planning/STATE.md (this file — current position)

/gsd-execute-phase 16.1
```

Wave 1 (autonomous) → Wave 2 (UAT checkpoint blocks until iPhone Safari + Chrome operator UAT confirmed).

```
[░░░░░░░░░░░░░░░░] 0% (v1.1 just started — Phase 10 ready to plan)
```

**v1.1 phase inventory:**

- Phase 10: Foundation — v1.0 Cleanup & Deploy Key (4 REQs) — ready to plan
- Phase 11: Web Skeleton — FastAPI + uvicorn + systemd (4 REQs) — parallelizable with 10
- Phase 12: HTTPS + Domain Wiring (3 REQs) — blocked on operator domain purchase
- Phase 13: Auth + Read Endpoints (5 REQs)
- Phase 14: Trade Journal — Mutation Endpoints (6 REQs)
- Phase 15: Live Calculator + Sentinels (7 REQs)
- Phase 16: Hardening + UAT Completion (2 REQs)

**Open prerequisites (operator-owned):**

- [ ] Domain purchased and A-record pointing at droplet IP (blocks Phase 12+)
- [ ] Droplet provisioned (DO, Ubuntu LTS, systemd, public IP) (blocks Phase 11+)
- [ ] Resend domain verification (SPF/DKIM/DMARC) on the new domain (blocks Phase 12 INFRA-01)

## Performance Metrics

| Metric | Value |
|--------|-------|
| v1.1 Phases defined | 7 (Phase 10..16) |
| v1.1 Requirements mapped | 31/31 |
| v1.1 Phases completed | 0 |
| v1.1 Phases in-flight | 0 |
| v1.0 Phases completed (archive) | 9/9 |
| v1.0 Requirements verified (archive) | 80/80 |
| Decisions logged | 4 (v1.0 baked in) + 8 (v1.1 baked in) |
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
| Phase 07 P01 | ~8min | 2 tasks tasks | 6 files files |
| Phase 07 P07-02 | ~20min | 3 tasks | 3 files |
| Phase 07 P03 | ~15min | 4 tasks | 5 files |
| Phase 8 P3 | 60 minutes | 3 tasks | 5 files |
| Phase 9 P1 | ~4min | 2 tasks | 3 files |
| Phase 11 P01 | 432s | 3 tasks | 6 files |
| Phase 11 P02 | 5min | 2 tasks | 2 files |
| Phase 11 P03 | 5min | 2 tasks | 2 files |
| Phase 11 P04 | 279 | 2 tasks | 2 files |
| Phase 13 P01 | 7m22s | 3 tasks | 9 files |
| Phase 13 P02 | 5m37s | 2 tasks | 6 files |
| Phase 14 P01 | 7min | 2 tasks | 7 files |
| Phase 14 P02 | 67min | 3 tasks | 5 files |
| Phase 14 P03 | 4m31s | 1 tasks | 2 files |
| Phase 16 P04 | 5min | 1 tasks | 1 files |
| Phase 22 P01 | 22min | 6 tasks | 10 files |
| Phase 17 P01 | 90 | 5 tasks | 12 files |
| Phase 19 P01 | 180 | 6 tasks | 18 files |
| Phase 20 P01 | 180 | 7 tasks | 16 files |
| Phase 27 P07 | 8m24s | 2 tasks | 2 files |
| Phase 27 P06 | ~25min | 2 tasks | 4 files |
| Phase 27 P02 | ~9min | 1 tasks | 5 files |
| Phase 27 P03 | ~25min | 1 tasks | 5 files |
| Phase 27 P04 | 7min | 1 tasks | 3 files |
| Phase 27 P01 | ~75min | 4 tasks | 9 files |
| Phase 27 P05 | ~25min | 2 tasks | 6 files |
| Phase 27 P08 | 30min | 2 tasks tasks | 2 files files |
| Phase 27 P10 | 75min | 3 tasks | 6 files |
| Phase 27 P09 | 30min | 2 tasks tasks | 9 files files |

## Accumulated Context

### Roadmap Evolution

- Phase 16.1 inserted after Phase 16: Phone-friendly auth UX for dashboard access (URGENT)
- Phase 27 added: Code quality & correctness sweep — apply 2026-05-07 code-review findings (Decimal money math, file-size splits, timeout/security/HTML-escape audits, etc.)

### Decisions

| Decision | Phase | Rationale |
|----------|-------|-----------|
| GitHub Actions is the PRIMARY deployment path (Replit documented as alternative) | 7 (v1.0) | Replit Autoscale doesn't guarantee filesystem persistence and kills `schedule` loops; GHA is free, stateless-by-design, and commits `state.json` back to the repo |
| `n_contracts == 0` skips the trade and warns (no `max(1, …)` floor) | 2 (v1.0) | A `max(1, …)` floor silently breaches the 1% risk budget on small accounts; skipping with a visible warning keeps risk discipline |
| LONG→FLAT (and SHORT→FLAT) closes the open position | 2 (v1.0) | Unambiguous semantics: FLAT means "no position", so any non-matching signal closes |
| Trailing stops use intraday HIGH/LOW for both peak updates and hit detection | 2 (v1.0) | Consistent intraday convention matches how the backtest was built; close-only convention would diverge from reconciliation data |
| DO droplet = runtime (systemd); GitHub = source + state history via deploy-key push-back | 10–16 (v1.1) | Inverts v1.0 GHA-primary model — droplet gives HTTP serving capability for FastAPI; GHA cron retired to avoid duplicate-email risk |
| FastAPI + uvicorn + nginx + Let's Encrypt on `signals.<owned-domain>.com` | 11–12 (v1.1) | Standard Python async web stack; reverse-proxy pattern plays well with certbot renewal and isolates the app from public bind |
| HTMX or vanilla JS (no React / SPA framework) | 14 (v1.1) | Matches project's no-build-step convention from v1.0 static dashboard; avoids bundle + asset-version management overhead |
| Shared-secret header auth (not OAuth / sessions / cookies) | 13 (v1.1) | Single-operator tool; session cookies would require CSRF + storage without benefit; header auth is grep-auditable and composable with curl |
| uvicorn `workers=1` — preserves v1.0 single-threaded `_LAST_LOADED_STATE` cache | 11 (v1.1) | Multi-worker would require thread-safe state cache + file-lock coordination; deferred to v1.2 |
| Domain + Resend verification are operator prerequisites, not code work | Pre-12 (v1.1) | Can't be done by a GSD session — blocks Phase 12 entry until resolved |
| GHA cron retired once droplet systemd runs reliably | 10 (v1.1) | Running both means duplicate signal emails and competing `state.json` writes — must be a clean handover |
| v1.0 carry-over tech debt (BUG-01 + ruff + F1 integration + HUMAN-UAT) folded into v1.1 | 10 + 16 (v1.1) | Phase 10 = cheap polish; Phase 16 = HUMAN-UAT is now verifiable via hosted dashboard (blocked in v1.0 by no-public-URL) |

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
- Phase 7 Wave 0: PyYAML pinned even though only Wave 2 consumes, per 07-REVIEWS.md Consensus MEDIUM — avoids transitive-dep reliance in Wave 2 static-YAML acceptance test
- Phase 7 Wave 0: _get_process_tzname wrapper in main.py instead of monkeypatching time.tzname, per 07-REVIEWS.md Codex MEDIUM — platform-portable test-patchability
- Phase 7 Wave 0: load_dotenv() shipped LIVE at top of main() (not stubbed) — idempotent and side-effect-neutral when .env absent
- Phase 7 Wave 0: Phase 4 '[Sched] One-shot mode' log line PRESERVED; Wave 1 deletes alongside tests/test_main.py:129,146 update in same plan (Pitfall 3 atomic-test-transition)
- Phase 7 Wave 0 deviation (Rule 1): plan's automated check used schedule.__version__/dotenv.__version__ attrs (not exposed); switched to importlib.metadata.version for verification
- Phase 7 Wave 1: main() dispatch amendment moved from Task 2 B3 into Task 1 GREEN so TestImmediateFirstRun could pass in Task 1 as planned (Rule 3)
- Phase 7 Wave 1: _FakeScheduler.day fixed to @property to match real schedule library .every().day access (Wave 0 scaffold bug — Rule 1)
- Phase 7 Wave 1: Monday weekday-gate test uses committed fetch fixtures rather than plan-specified None-recorder (main.py has no None-guard — Rule 1 plan design flaw)
- Phase 7 Wave 1: test_default_mode_does_NOT_send_email patched alongside the two plan-named test_main.py tests (Phase 7 default dispatch broke it too — Pitfall 3 sibling, Rule 3)
- Phase 7 Wave 2: GHA workflow ships cron '0 0 * * 1-5' + workflow_dispatch + permissions:contents:write + concurrency:trading-signals + git-auto-commit@v5 with add_options:'-f' (Pitfall 2 force-add of gitignored state.json)
- Phase 7 Wave 2 operator verification approved: workflow_dispatch ran green, state.json commit-back via github-actions[bot] confirmed, email arrived, README badge renders
- Phase 7 Wave 2: TestGHAWorkflow uses parsed.get('on') or parsed.get(True) fallback (Codex HIGH) and does NOT use importorskip (Consensus MEDIUM — PyYAML pinned in Wave 0)
- Plan 03: Module-level _LAST_LOADED_STATE cache in main.py single-threaded orchestrator enables crash-email SC-3 completeness without threading schedule-loop state through the scheduler driver
- Plan 03: _dispatch_email_and_maintain_warnings encapsulates B1 canonical ordering (dispatch -> clear -> maybe-append -> single save) in one place so --force-email, --test, and (future) scheduled runs all share the same invariant
- Plan 03: math.isfinite guard applied on BOTH argparse-flag and interactive-Q&A paths for --initial-account, closing T-08-12 regardless of invocation surface
- create_app() has no docs_url/redoc_url kwargs — Swagger defaults left for Phase 11 per REVIEWS MEDIUM #6
- Handler uses date.fromisoformat (not datetime) per REVIEWS HIGH #1 — last_run is YYYY-MM-DD date string from state.json
- Tests monkeypatch state_manager.load_state directly per REVIEWS HIGH #2 — STATE_FILE default arg is bound at import time
- REVIEWS MEDIUM #5: EnvironmentFile=- (leading dash) makes .env optional in Phase 11; no web env vars consumed until Phase 13
- REVIEWS LOW #8: web.app:app exact ExecStart reference guards cross-plan drift; configparser + raw text dual assertion strategy
- REVIEWS MEDIUM #7: pip install --upgrade pip dropped from deploy.sh D-23 sequence
- REVIEWS HIGH #4: two separate sudo -n systemctl restart calls in deploy.sh (one per unit, not combined)
- REVIEWS HIGH #3: curl retry loop (10 attempts @ 1s) replaces sleep 3 heuristic in deploy.sh
- Created SETUP-DROPLET.md as new sibling doc (not extending Phase 10) for cleaner per-phase separation
- Sudoers: two comma-separated rules matching deploy.sh split sudo -n calls; /usr/bin/systemctl path (verify with which systemctl)
- Passwordless sudo verification step added (REVIEWS HIGH #4) to catch sudoers miss before first deploy
- .env NOT required in Phase 11 (EnvironmentFile=- in unit file per REVIEWS MEDIUM #5)
- Plan 13-01 (Wave 0): autouse WEB_AUTH_SECRET fixture in tests/conftest.py is the structural fix for REVIEWS HIGH (codex finding) — covers the 11 direct create_app() invocations in tests/test_web_healthz.py test bodies that don't go through app_instance fixture
- Plan 13-01: VALID_SECRET = 'a' * 32 lives ONCE in tests/conftest.py per REVIEWS LOW #6 single-source invariant; downstream test files import the name (no redefinition)
- Plan 13-01: tests/test_web_healthz.py FORBIDDEN_FOR_WEB drops 'dashboard' (Phase 13 D-07 promotes dashboard to allowed adapter import for web/routes/dashboard.py); AST guard renamed test_web_adapter_imports_are_local_not_module_top with absent-file skip-guard for Wave 0
- Plan 13-02: from conftest import fails because pytest testpaths does not put tests/ on sys.path; inlined VALID_SECRET + AUTH_HEADER_NAME in tests/test_web_app_factory.py with comments pointing back to single-source conftest.py (Rule 1 deviation)
- Plan 13-02: AuthMiddleware ships full Pattern 1 body in this plan (not a stub) so the openapi_url=401-without-auth ordering test (D-06 proof) passes here; Plan 13-03 will own comprehensive middleware test classes
- Plan 13-02: route handlers ship as 503 stubs (deterministic content) rather than NotImplementedError so smoke tests + the import graph remain clean for parallel Wave 2 execution
- Phase 14 D-02 hex-boundary promotion: Option A (promote both sizing_engine + system_params) chosen — single-source-of-truth for MAX_PYRAMID_LEVEL preserved
- Phase 14 v2->v3 migration round-trip fixture: tests/fixtures/state_v2_no_manual_stop.json with two open Positions (LONG with peak, SHORT with trough) covers both branches of Phase 2 D-08 invariant
- Plan 14-02: mutate_state(mutator, path) holds fcntl.LOCK_EX across the FULL load -> mutate -> save critical section, closing the cross-process lost-update race (REVIEWS HIGH #1; T-14-01 -> FULLY MITIGATED). POSIX flock-on-different-fd is NOT reentrant within a single process — refactored into locked + unlocked I/O kernel pair (_atomic_write/_atomic_write_unlocked, save_state/_save_state_unlocked) to avoid the deadlock the plan-as-written would have shipped.
- Plan 14-02: STATE_SCHEMA_VERSION bumped 2 -> 3; Position TypedDict gains manual_stop: float | None field; _migrate_v2_to_v3 backfills manual_stop=None on every non-None Position dict (idempotent dict-spread; D-15 silent migration). Existing droplet v2 state.json files migrate transparently on first post-deploy load_state.
- Plan 14-02: main.py daily loop migrates 3 save_state call sites to mutate_state — run_daily_check step 9 (W3 #1), _dispatch_email_and_maintain_warnings (W3 #2), _handle_reset (outside W3). Mutator key-replay closure pattern: captured-snapshot mutator re-applies the run's accumulated mutations onto the fresh-loaded state under lock. W3 invariant (2 saves per run) preserved; W3 regression test migrated to count mutate_state calls.
- Phase 14 D-09: sizing_engine.get_trailing_stop honors position.manual_stop override (precedence: NaN guard > manual_stop > computed peak/trough); defensive .get() handles pre-migration position dicts
- Phase 14 D-15: check_stop_hit (daily-loop exit detection) intentionally does NOT honor manual_stop — display-only scope; Phase 15 candidate to align
- [Phase ?]: All 3 UAT scenarios partial on 2026-04-26: STATE.md ## Completed Items records partial/2026-04-26 per REVIEWS H-3; D-17 fallback applied
- [Phase ?]: Phase 22: STRATEGY_VERSION='v1.2.0' shipped on system_params; schema 3->4 with v3->v4 backfill of 'v1.1.0' on existing dict-shaped signal rows; dashboard footer renders the version via primitive str arg (no system_params.STRATEGY_VERSION import; LEARNINGS 2026-04-27 hex-boundary)
- [Phase ?]: Phase 27 Plan 27-08 (HTML escape audit) — added quote=True to 13 html.escape() sites in dashboard.py paper-trade rendering (lines 1394, 1544-1549, 1627-1632) closing attribute-context XSS for double-quote payloads. Reused Phase 6 D-10 direct html.escape pattern; no parallel _e helper. AST-based test gate proves quote=True on every Call node across 10 audited files. 23 new tests; 1903/1903 full suite green.
- [Phase ?]: Plan 27-10: MAX_WARNINGS 100 → 50 single-source-of-truth (no parallel WARNINGS_FIFO_MAX_LEN)
- [Phase ?]: Plan 27-10: locked in EOD signal-engine contract (today's bar feeds today's signal — correct for daily-cadence systems with next-day-open execution); locked meaningful no-look-ahead invariant (no future-bar leakage).
- [Phase ?]: Plan 27-10: canonical [Daily] run-date YYYY-MM-DD INFO log line at run_daily_check head — journalctl-grep operator marker.
- [Phase ?]: 27-09 dict-only signal shape

### Todos Carried Forward

- [ ] Confirm SPI contract multiplier with operator's broker at Phase 2 kickoff ($25/pt full ASX 200 vs $5/pt SPI mini)
- [ ] Verify Resend sender domain (`signals@carbonbookkeeping.com.au`) SPF/DKIM/DMARC before Phase 6 first live send
- [ ] Pin exact yfinance version (not `>=`) in `requirements.txt` at Phase 4; bump deliberately
- [ ] Document Replit Reserved VM path in Phase 7 deployment guide alongside GHA
- [x] **Configurable starting account + contract-size selection** — folded into Phase 8 Hardening on 2026-04-22 as CONF-01 (runtime-configurable starting account) + CONF-02 (per-instrument contract-size tiers). See [.planning/todos/completed/2026-04-22-configurable-starting-account-and-contract-sizes--folded-into-phase-8.md](./todos/completed/2026-04-22-configurable-starting-account-and-contract-sizes--folded-into-phase-8.md) and Phase 8 in ROADMAP.md
- [ ] **(v1.1) Operator purchases domain + points A-record at droplet IP** — blocks Phase 12+
- [ ] **(v1.1) Operator provisions DO droplet** (Ubuntu LTS, systemd, public IP) — blocks Phase 11+
- [ ] **(v1.1) Operator verifies new domain on Resend** (SPF/DKIM/DMARC) — blocks Phase 12 INFRA-01

### Pending Todos

| Created | Title | Area | Priority |
|---------|-------|------|----------|
| 2026-04-27 | [Phone-friendly auth UX for dashboard access](./todos/pending/2026-04-27-phone-friendly-auth-ux-for-dashboard-access.md) | auth | blocker |

### Blockers

None at the GSD-session level. Three operator-owned prerequisites (domain / droplet / Resend verification) gate Phases 11–12 but do NOT block Phase 10 planning or execution.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260421-723 | Phase 1 REVIEWS pass-2 follow-up: oracle-hash comment + test_compute_indicators_is_idempotent + tests/regenerate_scenarios.py | 2026-04-21 | 2ace992 | [260421-723-add-oracle-hash-comment-test-compute-ind](./quick/260421-723-add-oracle-hash-comment-test-compute-ind/) |
| 260425-91t | Document SIGNALS_EMAIL_FROM env-var contract in .env.example and PROJECT.md (no source change — Phase 12 D-16 already removed the hardcoded constant) | 2026-04-24 | _pending_ | [260425-91t-make-email-from-in-notifier-py-env-overr](./quick/260425-91t-make-email-from-in-notifier-py-env-overr/) |
| 260426-vcw | Phase 12 HTTPS reconcile — sync nginx/signals.conf comments with deployed state, add port-80 redirect, delete duplicate | 2026-04-26 | 70431c9 | [260426-vcw-phase-12-https-reconcile-sync-nginx-sign](./quick/260426-vcw-phase-12-https-reconcile-sync-nginx-sign/) |
| 260429-b3e | Append v1.2+ long-term roadmap reference to SPEC.md (paper-ledger, multi-user 2FA, calc transparency, news, audit, backtest gate) | 2026-04-29 | 1eb8159 | [260429-b3e-update-spec-md-with-v1-2-long-term-roadm](./quick/260429-b3e-update-spec-md-with-v1-2-long-term-roadm/) |
| 260429-sdp | HIGH-SEV bug fix — `_run_daily_check_caught` was discarding `run_daily_check`'s 4-tuple and silently never dispatching the daily 08:00 AWST email on the production droplet daemon. Restored dispatch + 4 regression tests + inverted Phase-4 fossil test that was enforcing the bug. Operator deploy: `git pull` + `sudo systemctl restart trading-signals` on droplet. | 2026-04-29 | 879730d | [260429-sdp-fix-scheduler-email-dispatch](./quick/260429-sdp-fix-scheduler-email-dispatch/) |

### Warnings (roadmap-level)

- (v1.0 retrospective) Requirements count reconciliation: prompt stated 67 v1 requirements; REQUIREMENTS.md contains 78 across 11 categories. All 78 are mapped. Verify at Phase 1 kickoff that the operator's intent matches. — **Resolved**: v1.0 closed at 80/80 after CONF-01/02 were folded in.
- (v1.1) REQUIREMENTS.md originally claimed 32 requirements in the namespace footer; actual count is 31 (WEB 7 + AUTH 3 + TRADE 6 + CALC 4 + SENTINEL 3 + BUG 1 + INFRA 4 + CHORE 3 = 31). Roadmap uses 31. Self-documented in REQUIREMENTS.md footer.

## Completed Items

Items deferred at v1.0 milestone close (2026-04-24) and verified closed via Phase 16 operator UAT (per D-14, D-15; migration runs after operator confirmation per REVIEWS H-3):

| Category | Item | Verified | Date | Artifact |
|----------|------|----------|------|----------|
| uat_gap | Phase 06 HUMAN-UAT (3 pending scenarios — Gmail rendering verification) | yes | 2026-04-30 | [16-HUMAN-UAT.md §UAT-16-A/B/C](./phases/16-hardening-uat-completion/16-HUMAN-UAT.md) |
| verification_gap | Phase 05 VERIFICATION (dashboard HTML visual check) | yes | 2026-04-27 | [16-HUMAN-UAT.md §UAT-16-A](./phases/16-hardening-uat-completion/16-HUMAN-UAT.md#uat-16-a-mobile-dashboard-rendering) |
| verification_gap | Phase 06 VERIFICATION (email rendering visual check) | yes | 2026-04-29 | [16-HUMAN-UAT.md §UAT-16-B](./phases/16-hardening-uat-completion/16-HUMAN-UAT.md#uat-16-b-mobile-gmail-email-rendering) |

> **Verification source:** Each row's `Verified` and `Date` columns are read from `.planning/phases/16-hardening-uat-completion/16-HUMAN-UAT.md` after Plan 16-05 closed (REVIEWS H-3). All three scenarios are now `verified`: UAT-16-A on 2026-04-27 (Phase 12 HTTPS bring-up + curl-through-production), UAT-16-B on 2026-04-29 (operator inspected production email in Gmail mobile, all 5 D-10 criteria pass; pre-requisite fix shipped via quick task `260429-sdp` commit `879730d` which restored email dispatch on the scheduler-loop path), UAT-16-C on 2026-04-30 (drift banner observed in 2026-04-30 daily email — red/amber border, `[!]` subject prefix, dashboard banner parity confirmed). The uat_gap row is `yes` because all three scenarios closed; v1.0 milestone archive is unblocked.

## Deferred Items

### Items deferred at v1.0 milestone close (2026-04-24)

| Category | Item | Status | v1.1 disposition |
|----------|------|--------|------------------|
| quick_task | 260421-723-add-oracle-hash-comment-test-compute-ind | missing | Still deferred (not v1.2 scope) |

The remaining `quick_task` item is not v1.2 scope. The 3 Phase 6 HUMAN-UAT and verification-gap items moved to `## Completed Items` above (closed via Phase 16 operator UAT — see [16-HUMAN-UAT.md](./phases/16-hardening-uat-completion/16-HUMAN-UAT.md)).

### Items acknowledged and deferred at v1.1 milestone close (2026-04-30)

Operator-driven UAT scenarios that require live droplet + browser/phone hands-on verification. Production system has been running cleanly through these phases (`signals.mwiriadi.me` live since Phase 12 bring-up, daily emails flowing since 2026-04-29, all auth UX shipped). These UATs document what should be re-verified opportunistically; none are blockers for shipping.

| Category | Item | Status | v1.2 disposition |
|----------|------|--------|------------------|
| uat_gap | Phase 13 HUMAN-UAT — 4 open scenarios (nginx X-Forwarded-For wiring, real curl-through-production auth checks) | partial | Defer to opportunistic operator runs; re-verify after any nginx/auth refactor |
| uat_gap | Phase 14 HUMAN-UAT — 5 open scenarios (HTMX trade form swaps in real browser, kernel POSIX flock cross-process semantics, first-deploy schema migration on live state.json) | partial | Defer; trade journal has been used in production daily without issue post-Phase 16-01 deploy |
| uat_gap | Phase 16.1 HUMAN-UAT — auth UX scenarios (login, TOTP enroll, trusted device, magic-link reset) | pending | Operator runs first time they exercise the full auth flow on phone; tracked separately as "v1.1 polish" |
| verification_gap | Phase 13 13-VERIFICATION.md — human_needed (auth-on-live-HTTPS verifications) | human_needed | Same droplet/curl constraint as Phase 13 UAT; same disposition |

**Acknowledgement rationale:** Each of these gaps is "verify in real-world environment after deploy" — that real-world environment is now stable production at `signals.mwiriadi.me` per Phase 12 bring-up + Phase 16 closure. No deferred functional or correctness gap remains at code level (1319-test suite green, all critical paths covered by automated tests). These UAT documents stay as runnable runbooks for the operator to use opportunistically.

**Stale todo cleaned up at close:** `2026-04-27-phone-friendly-auth-ux-for-dashboard-access.md` was promoted to Phase 16.1 (now verified 2026-04-29). The todo file is removed at v1.1 close.

## Session Continuity

- **Last action:** `/gsd-roadmapper` wrote `.planning/ROADMAP.md` (v1.1 — 7 phases 10..16, 31/31 REQs mapped, 0 orphans/duplicates) and updated `.planning/REQUIREMENTS.md` traceability table (TBD → Phase N for all 31 REQ-IDs).
- **Next action:** `/gsd-discuss-phase 10` to scope Phase 10 (Foundation — v1.0 Cleanup & Deploy Key). Phase 10 has no infrastructure prerequisites; operator can start immediately. Phase 11 can be discussed in parallel on a separate session (disjoint files: Phase 10 touches `state_manager.py`/`notifier.py`/`.github/workflows/`; Phase 11 creates `web/` + `systemd/` + `deploy.sh`).
- **Files ready for review:**
  - `.planning/ROADMAP.md` — v1.1 full phase detail + success criteria + coverage map + dependency graph
  - `.planning/REQUIREMENTS.md` — traceability table populated with Phase 10..16 assignments
  - `.planning/PROJECT.md` — unchanged (already reflects v1.1 direction)
  - `.planning/MILESTONES.md` — unchanged (v1.0 archived section; v1.1 section will be added at milestone close)
- **Research flags to revisit during phase planning:**
  - Phase 10: confirm BUG-01 interactive-Q&A path scope (is there a separate Q&A flow for reset, or does `--reset` alone cover both?)
  - Phase 11: confirm systemd unit ownership/user model (dedicated service user vs droplet root)
  - Phase 12: operator must complete domain purchase + Resend verification BEFORE plan kickoff; verify A-record resolves on Phase 12 entry
  - Phase 14: confirm with operator whether HTMX partial responses should hx-target the whole positions table or just the added row (UX decision)
  - Phase 15: forward-looking peak-stop math — confirm this should use today's live-but-incomplete bar (e.g. yfinance 15-min-delayed intraday) or only yesterday's close + today's range so far

---
*State initialised: 2026-04-20 at v1.0 roadmap creation*
*v1.0 archived: 2026-04-24 at milestone close (Phases 1–9 complete, 80/80 REQs verified)*
*v1.1 roadmap created: 2026-04-24 by /gsd-roadmapper (Phases 10–16, 31/31 REQs mapped)*

**Planned Phase:** 16 () — 0 plans — 2026-04-26T09:00:07.835Z

**Plan 09-01 completed:** 2026-04-23 — 2 tasks, 3 files modified (.planning/REQUIREMENTS.md +102/-101; .github/workflows/daily.yml +1 line; tests/test_scheduler.py +22 lines) + 2 files created (09-01-SUMMARY.md, deferred-items.md). Task 1: ERR-01 spec amended to match test-locked no-email behaviour (`except (DataFetchError, ShortFrameError): return 2` with no crash-email call); 37 `- [ ]` checkbox flips via single replace_all (DATA 6 + STATE 7 + NOTF 9 + DASH 9 + CLI 4 + ERR 2 = 37 → 80/80 checked); 59 `| Pending |` traceability rows flipped to `| Complete |` (ERR-01 and SIG-05..08 rows got richer Complete-with-evidence descriptors); coverage header updated to `Mapped to phases: 80/80, Verified: 80/80`; amendment footer dated 2026-04-23 appended. Task 2: `timeout-minutes: 10` added at job level in daily.yml between `runs-on: ubuntu-latest` and `steps:` (parses as int 10 via PyYAML); `test_daily_workflow_has_timeout_minutes` appended inside `TestGHAWorkflow` with two independent assertions (key existence + value equality) — TestGHAWorkflow went from 12 → 13 tests. Locked-behaviour guard `tests/test_main.py::TestCrashEmailBoundary::test_data_fetch_error_does_not_fire_crash_email` unchanged and green (git diff --exit-code returns 0). Full suite: 662 passed (was 661; +1 for new regression test). Pre-existing ruff F401 warnings in notifier.py (19 errors) logged to deferred-items.md as out-of-scope. One Rule-3 deviation (footer date 2026-04-23 instead of draft's 2026-04-24, matching today's actual execution date per executor context). Phase 9 complete; milestone v1.0 ready for archive. Commits: f3f6e3c (Task 1 REQUIREMENTS reconciliation), 2e3d314 (Task 2 GHA timeout + regression test).

**Plan 01-02 completed:** 2026-04-20T19:49:00Z — 3 tasks, 3 files created (tests/oracle/wilder.py, tests/oracle/mom_rvol.py, tests/oracle/test_oracle_self_consistency.py), 17 self-consistency tests passing, requirements SIG-01..SIG-04 marked complete.

**Plan 01-03 completed:** 2026-04-20T20:01:00Z — 2 tasks, 28 files created: 2 canonical yfinance fixtures (^AXJO + AUDUSD=X) with provenance READMEs per R-03; 9 deterministic scenario fixtures + scenarios.README.md per D-16; tests/regenerate_goldens.py offline pipeline per D-04; 2 canonical golden CSVs + 9 scenario JSONs + SHA256 determinism snapshot per D-14. Split-vote scenario verified via Mom1=+0.058, Mom3=-0.043, Mom12=-0.003 ⇒ FLAT per SIG-08 (MUST FIX compliance). Requirements SIG-01..SIG-08 are now covered end-to-end by fixtures + goldens (pending Plan 04/05 production tests).

**Plan 01-04 completed:** 2026-04-20T20:13:24Z — 2 tasks, 2 files created (signal_engine.py 193 lines, tests/test_signal_engine.py 213 lines). Production compute_indicators matches oracle goldens to 5.7e-14 worst case across 8 indicators × 2 canonical fixtures (1e-9 plan tolerance). `_wilder_smooth` implements NaN-strict seed-window rule matching oracle bit-for-bit (REVIEWS MEDIUM). `_assert_index_aligned` helper fires before every `assert_allclose` (REVIEWS MEDIUM). 38 TestIndicators tests pass; 55/55 full suite green; ruff clean. Requirements SIG-01..SIG-04 marked complete. Commits: a0ab525 (feat Task 1), f75151a (test Task 2).

**Plan 01-05 completed:** 2026-04-20T20:22:46Z — 2 tasks, 2 files modified (signal_engine.py 193 → 254 lines; tests/test_signal_engine.py 213 → 409 lines). `get_signal(df) -> int` (D-06 bare int, NaN-abstaining 2-of-3 vote gated by ADX >= 25) and `get_latest_indicators(df) -> dict` (D-08 8-key lowercase dict, every value explicit `float()` cast per REVIEWS POLISH) appended after existing compute_indicators. TestVote (9 parametrized scenarios + 6 named SIG-05..08 shortcuts) + TestEdgeCases (D-09 NaN ADX, D-10 Mom12 NaN 2-of-2, D-11 flat-price NaN, D-12 RVol 0.0, 3 threshold-equality tests for ADX==25 and Mom==±0.02, 3 get_latest_indicators contract tests) cover SIG-05..08 + D-09..12 + REVIEWS STRONGLY RECOMMENDED + REVIEWS POLISH. Split-vote scenario verified FLAT end-to-end (REVIEWS MUST FIX closed). 63/63 tests in tests/test_signal_engine.py pass; 80/80 full-suite green; ruff clean. Requirements SIG-05..SIG-08 marked complete. Commits: b0ebeb3 (feat Task 1), 675b713 (test Task 2).

**Plan 01-06 completed:** 2026-04-20T20:35:36Z — Final Phase 1 gate. 1 file modified (tests/test_signal_engine.py 409 → 649 lines; +240). Appended TestDeterminism class with 19 tests: 16 SHA256 snapshot regression (2 fixtures × 8 indicators, hashes ORACLE output per D-14 trust-anchor design — production has ~5e-14 drift below the 1e-9 tolerance gate); test_forbidden_imports_absent (AST blocklist per REVIEWS STRONGLY RECOMMENDED — FORBIDDEN_MODULES includes datetime/os/subprocess/socket/time/json/pathlib/requests/urllib/http/state_manager/notifier/dashboard/main/schedule/dotenv/pytz/yfinance); test_signal_engine_has_core_public_surface (hasattr contract for compute_indicators/get_signal/get_latest_indicators/LONG/SHORT/FLAT); test_no_four_space_indent (tokenize-aware 2-space-evidence check per REVIEWS POLISH). Two Rule-1 plan bugs fixed inline: (1) hash oracle not production because production has ~5e-14 drift from oracle snapshot; (2) indent check needed 2-space-presence evidence (not 4-space absence) since nested code legitimately has 4 leading spaces in 2-space style. 99/99 full suite green (0.60s); ruff clean; `python tests/regenerate_goldens.py` idempotent (zero git diff on oracle goldens + snapshot.json). Phase 1 SHIPPED — all 8 SIG requirements have named passing tests, determinism snapshot locked, hex boundary enforced. Commit: 14d3ecd (test Task 1; Task 2 verification-only under same commit).

**Plan 07-03 completed:** 2026-04-23T01:30:00Z — Wave 2 PHASE GATE (operator-verified). 3 files created (.github/workflows/daily.yml 45 lines, docs/DEPLOY.md 172 lines, README.md 49 lines) + 1 file extended (tests/test_scheduler.py 335 → 657 lines, +322). Workflow: cron `0 0 * * 1-5` + workflow_dispatch + permissions:contents:write + concurrency:trading-signals + actions/checkout@v4 + actions/setup-python@v5 (reads .python-version) + `python main.py --once` job step + stefanzweifel/git-auto-commit-action@v5 with add_options:'-f' (Pitfall 2 — force-add of gitignored state.json) + if:success() (D-11 — no commit on fail). 24 new tests (TestGHAWorkflow:12 + TestDeployDocs:12) including 2 dedicated review-fix tests (test_readme_has_gha_status_badge for Gemini LOW + test_deploy_md_local_dev_tz_note for Consensus LOW). 07-REVIEWS.md fixes pinned: Codex HIGH `parsed.get('on') or parsed.get(True)` fallback present; Consensus MEDIUM no `pytest.importorskip('yaml')` softener (PyYAML 6.0.2 pinned in Wave 0); Gemini LOW README badge present; Consensus LOW DEPLOY.md §Local-development TZ note present. ROADMAP SC-4 amended per D-12 (drop ANTHROPIC_API_KEY, name SIGNALS_EMAIL_TO). 552/552 tests pass; ruff clean. Operator verification (Task 3): workflow_dispatch ran green on github.com, state.json commit-back via github-actions[bot] confirmed, daily Resend email arrived in inbox, README.md GHA status badge renders as green "passing" indicator — outcome `approved`. SCHED-04..07 marked complete in REQUIREMENTS.md (SCHED-01..03 closed in Plan 07-02). Phase 7 ready for `/gsd-verify-work 7`. Two minor noise-only deviations (benign `importorskip.*yaml` substring matches in docstring narrative; ruff UP015 autofix). Commits: bbdc5e9 (Task 1 — workflow + TestGHAWorkflow + ROADMAP status check), 5b0a3b9 (Task 2 — DEPLOY.md + README.md + TestDeployDocs).

**v1.1 roadmap created:** 2026-04-24 — `/gsd-roadmapper` produced 7-phase v1.1 plan (Phases 10..16) with 100% coverage on 31 REQs. Phase 10 (Foundation — v1.0 Cleanup & Deploy Key) is the entry point — no infrastructure prerequisites. Phase 11 is parallelizable with Phase 10. Phases 12+ gated on operator purchasing a domain and verifying Resend. Files written: `.planning/ROADMAP.md` (new v1.1 version) + `.planning/REQUIREMENTS.md` (traceability table populated). Ready for `/gsd-discuss-phase 10`.

**Plan 27-07 completed:** 2026-05-07T19:38Z — 2 tasks, 2 files (state_manager.py +112/-1; tests/test_naive_datetime_fail_closed.py +122 NEW; tests/test_migration_contiguity.py +113 NEW). Task 1 (RED→GREEN): `_assert_tz_aware(dt, *, context)` raises `ValueError('naive datetime forbidden — must be tz-aware (context: …)')` at the head of `append_warning` (the sole state-write helper that takes a caller-supplied `now=` datetime); read-path `_coerce_legacy_naive_iso(state)` shim walks `equity_history` and emits one DeprecationWarning per load if any row carries a naive ISO datetime (legacy state files keep loading without nuking). Task 2 (RED→GREEN): `_assert_migration_chain_contiguous()` walks `range(2, STATE_SCHEMA_VERSION+1)` against MIGRATIONS and raises RuntimeError listing every missing key; called at module bottom (defensive — fails at import) AND at `load_state()` entry (review-fix M1 behavioral — fails on every load even if module-load was bypassed). 9/9 plan-tests green; 1803/1803 full suite green; one Rule-1 deviation (test fixture used wrong contract labels — fixed inline using `state_manager._DEFAULT_*_LABEL`). Commits: 1927992 (test RED Task 1), 46f7235 (feat GREEN Task 1), 1a04da0 (test RED Task 2), d2bd771 (feat GREEN Task 2). Plan blocks 27-01 (Wave 1B) — contiguity check will validate the v8→v9 schema bump on first import after 27-01 lands.

**Plan 27-02 completed:** 2026-05-07 — 1 task, 5 files (system_params.py +14; notifier.py +3/-2; data_fetcher.py +35/-3; tests/test_http_timeouts.py +211 NEW; tests/test_data_fetcher.py +9/-2; tests/test_integration_f1.py +1/-1). Task 1 (RED→GREEN, Phase 27 #5): added `system_params.HTTP_TIMEOUT_S = 30` (single canonical outbound HTTP timeout, threat T-27-02-01 hung-network DoS); deleted `_RESEND_TIMEOUT_S = 30` from notifier.py:106; updated `_post_to_resend.timeout_s: int = HTTP_TIMEOUT_S` default arg (call site `timeout=(5, timeout_s)` preserved — caller-override capability for crash-email path); imported HTTP_TIMEOUT_S into data_fetcher.py; added `_get_yf_session()` memoized requests.Session accessor whose patched `.request` does `kwargs.setdefault('timeout', HTTP_TIMEOUT_S)` (yfinance internals inherit canonical timeout via session= injection on `yf.Ticker(symbol, session=...)`); fetch_ohlcv `ticker.history()` timeout 10→HTTP_TIMEOUT_S (drift fixed). 5 new tests (constant present, _RESEND_TIMEOUT_S deleted, _post_to_resend canonical, AST walker for requests/urllib/httpx/from-imports/aliased, yfinance internals filter); 1816/1816 full suite green (+5 from 1811). One Rule-1 deviation: `tests/test_data_fetcher.py::_make_fake_ticker_factory` and `tests/test_integration_f1.py::_fake_ticker` did not accept `session=` kwarg — fixed inline (fakes accept-and-ignore the kwarg to match real yf.Ticker signature). One plan-spec adjustment: source-pattern check in test_post_to_resend_uses_canonical_timeout loosened from literal `(5, HTTP_TIMEOUT_S)` to `(5, HTTP_TIMEOUT_S|timeout_s)` to preserve caller-override; supplemented with stronger `inspect.signature` check on the default value resolution. Commits: 49445bd (test RED Task 1), 6aaadd7 (feat GREEN Task 1). SUMMARY at .planning/phases/27-…/27-02-SUMMARY.md.

**Plan 27-03 completed:** 2026-05-08 — 1 task, 5 files (system_params.py +33; notifier.py +13/-3; data_fetcher.py +6/-1; tests/test_secret_redaction.py +220 NEW; tests/test_notifier.py +14/-3). Task 1 (RED→GREEN, Phase 27 #13): added `system_params.redact_secret(s: str | None) -> str` (single canonical secret redactor — '[empty]' for None/'', '[short]' for ≤6 chars, `s[:6] + '...'` otherwise); wired `redact_secret(api_key)` prefix into both `notifier._post_to_resend` ResendError emission paths (4xx fail-fast at line 1394 + retries-exhausted at line 1410), preserving the existing defense-in-depth `body.replace(api_key, '[REDACTED]')` scrub — two layers: triage-prefix for ops + scrub-body for leak prevention; imported `redact_secret` into `data_fetcher.py` as a future-proof anchor (no call site today since yfinance does not consume an API key); auth_store.py audit confirmed clean (the existing line `[Auth] totp secret persisted (enrolled=False)` is schema-status text, not a secret-variable interpolation). 7 new tests (3× redact_secret unit, 2× notifier 4xx + retries-exhausted regress, 1× auth_store TOTP caplog scan, 1× structural grep gate over notifier/auth_store/data_fetcher source text); 1823/1823 full suite green (+7 from 1816). One Rule-3 deviation: 6 existing assertions in `tests/test_notifier.py` asserted the literal `'4xx from Resend: <status>'` substring; the new ResendError shape adds `(key=<prefix>...)` infix so the assertions were migrated to regex (`r'4xx from Resend \(key=[^)]+\): <status>'`) and `import re` was added — caused directly by the task's format change, not a pre-existing bug. Commits: 0fba96a (test RED), d7e5b5a (feat GREEN). SUMMARY at .planning/phases/27-…/27-03-SUMMARY.md.

**Plan 27-06 completed:** 2026-05-08 — 2 tasks, 4 files (data_fetcher.py +108/-4; main.py +31/-1; tests/test_deferred_yfinance_import.py +119 NEW; tests/test_version_flag.py +111 NEW). Task 1 (RED→GREEN, Phase 27 #14): removed module-top `import yfinance as yf` + `from yfinance.exceptions import YFRateLimitError` from data_fetcher.py; added `_get_yf()` memoized accessor + `_get_yf_rate_limit_error()` lazy resolver + PEP 562 module `__getattr__('yf')` that lazily binds the yfinance module on first attribute access (preserves `monkeypatch.setattr('data_fetcher.yf.Ticker', ...)` test contract); module-level `class YFRateLimitError(Exception)` proxy keeps `from data_fetcher import YFRateLimitError` working without forcing yfinance import (review-fix M4); `fetch_ohlcv` extends except tuple at call time with the real yfinance YFRateLimitError so production rate-limit errors stay retry-eligible. Task 2 (RED→GREEN, Phase 27 #17): added `--version` argparse flag + post-parse handler in `main(argv)` + early sys.argv hook at very top of `main.py` (before any heavy app-module imports — `import data_fetcher` etc. moved below the hook) so `python main.py --version` prints `STRATEGY_VERSION` and exits 0 with ONLY system_params imported (yfinance NOT in sys.modules — verified via subprocess assertion). 8 new tests (4 deferred-import + 4 version-flag, all subprocess-based for clean sys.modules); 1811/1811 full suite green (+8 from 1803). One Rule-3 adaptation: PEP 562 `__getattr__` was added beyond plan text to preserve existing test monkeypatch contract — plan's literal "delete `import yfinance as yf`" would have broken ~10 fetch tests without this. Plan 27-02 HTTP_TIMEOUT_S session config deferred to that plan (system_params.HTTP_TIMEOUT_S doesn't exist yet); `_get_yf()` is the documented hook point. Commits: 8003a68 (test RED Task 1), 5c72050 (feat GREEN Task 1), 3f6bb7e (test RED Task 2), 25cd522 (feat GREEN Task 2). SUMMARY at .planning/phases/27-…/27-06-SUMMARY.md.

**Plan 27-05 completed:** 2026-05-08 — Wave 1C (depends on 27-01). 2 tasks, 6 files (pnl_engine.py +35 entry_side_cost helper; notifier.py +50 _resolve_email_to_or_skip + 3 call site updates - 1 _EMAIL_TO_FALLBACK constant; main.py +13 import pnl_engine + 4 site replacements; .env.example +3/-1 SIGNALS_EMAIL_TO documented as REQUIRED; tests/test_entry_side_cost.py +108 NEW; tests/test_signals_email_to_required.py +303 NEW; tests/test_notifier.py +24/-7 autouse SIGNALS_EMAIL_TO pin + rewritten fallback test; tests/test_integration_f1.py +5 monkeypatch SIGNALS_EMAIL_TO cascade fix). Task 1 (RED→GREEN, Phase 27 #7): pnl_engine.entry_side_cost(rt_cost) -> Decimal AUD-quantized HALF_UP (symmetric-broker assumption documented inline); replaced 4 magic /2 sites — notifier:494 (cost_open in _compute_unrealised_pnl_email), main:1324 (cost_aud_open in daily-loop), main:1428 (closed_pnl_display close-half — beyond plan inventory but same symmetric-broker policy applies), main:1535 (review-fix M3 — equity rollup resolved['cost_aud']/2). Float() at consumption boundary preserves Decimal authority at pnl_engine. Task 2 (RED→GREEN, Phase 27 #9 + review-fix M3 option b): deleted _EMAIL_TO_FALLBACK = 'mwiriadi@gmail.com' constant; added _resolve_email_to_or_skip(state, *, context) helper that strips whitespace, on missing/blank logs ERROR + appends state['warnings'] marker via state_manager.append_warning (try/except wrapped — never-crash invariant); 3 call sites updated (send_daily_email passes state for marker visibility; send_crash_email + send_stop_alert_email pass state=None — operator visibility comes via next daily run's marker). Empty/whitespace env value treated identically to unset (deploy-typo defense). 17 new tests (8 entry_side_cost + 9 signals_email_to_required). Two Rule-1 cascade fixes: (1) tests/test_notifier.py — 10 tests across TestSendDispatch / TestSendDispatchStatusTuple / TestLastEmailAlwaysWritten / TestEmailFromEnvVar relied on the deleted fallback; added autouse `_pin_signals_email_to` fixture mirroring existing `_pin_signals_email_from` pattern; rewrote test_uses_fallback_recipient_when_signals_email_to_unset → test_skips_dispatch_when_signals_email_to_unset to assert the new fail-soft contract. (2) tests/test_integration_f1.py — F1 chain set RESEND_API_KEY + SIGNALS_EMAIL_FROM but not SIGNALS_EMAIL_TO; pre-Phase 27 #9 the fallback masked this; post-change two integration tests broke (captured['subject'] never set because send_daily_email short-circuited); added monkeypatch.setenv with phase-tagged comment. One plan-spec extension: main.py:1428 close-half site replaced beyond the plan's named inventory — same symmetric-broker policy, one helper now owns both half-cost computations. AST grep gate confirmed 0 hits for cost-shaped /2 BinOps across all 4 production files; grep gate confirmed 0 hits for _EMAIL_TO_FALLBACK + operator-shaped emails (mwiriadi@gmail) across notifier/main/pnl_engine/sizing_engine/state_manager. Hex boundary preserved: pnl_engine still imports only math/decimal/typing. 1880/1880 full suite green (+17 net new from 1863 baseline). Commits: 6d3de26 (test RED Task 1), 80c9847 (feat GREEN Task 1), e8d3602 (test RED Task 2), bc7d8f1 (feat GREEN Task 2). SUMMARY at .planning/phases/27-…/27-05-SUMMARY.md.

**Plan 27-01 completed:** 2026-05-08 — Wave 1B (depends on 27-07). 4 tasks, 9 files (system_params.py +61; pnl_engine.py rewritten +90; sizing_engine.py +37/-15; state_manager.py +98 v8→v9 migrator + save-path encoder; dashboard.py +8; dashboard_renderer/stats.py +9; web/routes/paper_trades.py +6; tests/test_decimal_money_math.py +378 NEW; tests/test_dashboard_decimal_serialization.py +152 NEW; tests/test_pnl_engine.py +12/-8; tests/test_state_manager.py +9/-7; tests/test_system_params.py +6/-4). Task 1 (RED→GREEN, Phase 27 #1 truths #1/#4/#5/#6/#7): added `system_params.AUD_QUANTIZE = Decimal('0.01')` + `AUD_ROUND = ROUND_HALF_UP` (NOT banker's rounding — agreed-7 review-fix) + `to_aud(x)` canonical coerce + `_decimal_default` json.dumps encoder; pnl_engine.compute_*_pnl now return Decimal AUD-quantized HALF_UP (inputs flow through `Decimal(str(x))` to strip float-binary noise; NaN propagates via `Decimal('NaN').is_nan()`); STATE_SCHEMA_VERSION 8→9 with `_migrate_v8_to_v9` quantize-on-save migrator covering account / initial_account / equity_history rows / paper_trades P&L+cost / trade_log gross/net/cost (idempotent, defensive, silent); save_state + _save_state_unlocked both run the migrator + pass `default=_decimal_default` to json.dumps. Task 2 (truth #2/#3, agreed-7): sizing_engine.compute_unrealised_pnl rewritten as a thin adapter that delegates to pnl_engine (eliminates duplicate cost_aud_open*n_contracts logic — review-fix MUST FIX); _close_position close_cost arithmetic uses to_aud(cost_aud_open) * to_aud(n_contracts) with float() at the ClosedTrade.realised_pnl boundary. Task 3 (truth #7): dashboard.py json.dumps site at line 1891 keeps existing float() pre-coerce of equity values + adds default=_decimal_default belt-and-suspenders; dashboard_renderer/stats.py + dashboard.py open-trades render path coerce via float() at the consumption boundary; web/routes/paper_trades.close_paper_trade row['realised_pnl'] = float(realised) at the persistence boundary. Task 4: cascade-fix Decimal-vs-float type mismatches in 3 sites (`realised += pnl` accumulators, persistence-boundary leaks); 5 schema-version-hardcoded test assertions cascaded v8→v9. 21 new tests (18 in test_decimal_money_math + 3 in test_dashboard_decimal_serialization), 1863/1863 full suite green (+21 net new from 1842 baseline). Three Rule-1 deviations: (1) hardcoded `STATE_SCHEMA_VERSION == 8` literals in 5 pre-existing test assertions cascaded v8→v9; (2) Decimal-vs-float `+=` mismatches at display-side accumulators (dashboard_renderer/stats.py, dashboard.py) coerced via float() at consumption; (3) close_paper_trade persistence-boundary leak fixed via float() before assignment to row['realised_pnl']. One plan-spec adjustment: in-memory state stays float (NOT Decimal end-to-end across orchestrator) — Decimal authority is pinned at pnl_engine return + state.json quantize-on-save; consumers float() at the display boundary. Eloquent compromise satisfies truths #1, #4, #5, #6, #7 without requiring a multi-plan refactor of main.py + UI layer (40+ call sites). Hex boundary preserved: signal_engine + sizing_engine indicator math (ATR/ADX/Mom/RVol on numpy/pandas) bit-for-bit float64; Decimal lives ONLY at money-math boundary. Commits: 3a08958 (RED), 8f030cd (GREEN T1), 961ac3b (GREEN T2), ab2e65e (GREEN T3), 1d1c8e0 (fix T4). SUMMARY at .planning/phases/27-…/27-01-SUMMARY.md.
