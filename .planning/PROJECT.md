# Trading Signals — SPI 200 & AUD/USD Mechanical System

## What This Is

A **shipped** hosted Python web app (v1.1, 2026-04-30) running a mechanical trend-following trading system for two instruments — SPI 200 (`^AXJO`) and AUD/USD (`AUDUSD=X`). FastAPI + nginx + Let's Encrypt + uvicorn on a DigitalOcean droplet at `https://signals.mwiriadi.me`, fronted by cookie-session + TOTP 2FA + trusted-device cookies + magic-link reset. A systemd-managed daemon fetches daily OHLCV at 08:00 AWST weekdays, computes ATR/ADX/momentum-vote signals, sizes positions with trailing-stop + pyramiding, persists state atomically with corruption recovery, renders an HTML dashboard with live calculator + drift sentinels, emails the operator via Resend, and handles crashes with a last-ditch crash-email boundary. The operator records executed trades through HTMX forms; dashboard surfaces live stop-loss + pyramid thresholds and flags position-vs-signal drift. **Signal-only** — it never places live trades; it tells the operator what the system says they should be doing and tracks hypothetical P&L against a configurable starting account (default $100k).

## Shipped Milestones

- **v1.0 — Mechanical Signal System** (2026-04-24, [milestones/v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md)): Phases 1–9. Email-only daily signal CLI via GitHub Actions cron. 80/80 v1 requirements verified.
- **v1.1 — Interactive Trading Workstation** (2026-04-30, [milestones/v1.1-ROADMAP.md](milestones/v1.1-ROADMAP.md)): Phases 10–16 + 16.1. Hosted dashboard + trade journal + cookie/TOTP/trusted-device/magic-link auth UX + live calculator + drift sentinels. 40/40 v1.1 requirements verified.
- **v1.2 — Trader-Grade Transparency & Validation** (2026-05-10, [milestones/v1.2-ROADMAP.md](milestones/v1.2-ROADMAP.md)): Phases 17, 19, 20, 22, 23, 24, 25, 26, 27. Trace panels, paper-trade ledger, stop-loss alerts, strategy versioning, 5-year backtest gate, two-axis market×function nav, code-quality sweep (Decimal money, file-size hygiene, naive-datetime fail-closed). 22/22 v1.2 requirements verified.

## Current State

**Production:** `https://signals.mwiriadi.me` — HTTPS + auth gated, daily 08:00 Sydney (AEST/AEDT, DST-aware) signal cycle on droplet systemd, daily emails flowing through Resend, 1880+ tests green, dashboard shows reproducible signals + paper-trade ledger + 5-year backtest gate. Schema at v9 (Decimal AUD-quantized money). DigitalOcean droplet + systemd is the documented PRIMARY deploy path; GHA cron disabled (preserved as rollback insurance).

**Next:** v1.3 — Multi-Tenant Friends & Family — Phase 38 complete (news integration); Phase 39 (guide UI — tour + tooltips) next.

## Current Milestone: v1.3 Multi-Tenant Friends & Family

**Goal:** Open the system to invite-only friends-and-family with full per-user state isolation, per-user 08:00 Sydney emails, news context, and a guided UI — while closing v1.2 deferred UAT debt and retroactively wrapping the post-v1.2 polish commits as v1.2.1.

**Target features:**

- **v1.2 UAT closure (Phase 28)** — 8 deferred operator-facing scenarios across v1.2 Phases 17/23/26 (ATR hand-recalc, iOS Safari tap, cookie persistence, live yfinance CLI, `/backtest` browser smoke, cold-start, multi-tab walkthrough).
- **v1.2.1 retroactive patch wrap** — 5 ad-hoc post-ship polish commits formalised as a dedicated cleanup phase.
- **Multi-tenant refactor** — admin namespace separation; existing `state.json` migrates to a privileged admin namespace; F&F users live in a per-user pool. `state_manager` rewritten to scope read/write by `user_id`. Schema v9 → v10. Signals stay shared/deterministic; trades/alerts/journal/equity become per-user.
- **RBAC — invite-only** — admin (Marc) issues invite tokens; admin can disable/remove users; existing auth UX (cookie session + TOTP + trusted-device + magic-link) extended per-user.
- **Per-user 08:00 Sydney email** — each user receives their own daily email with their stop-loss alerts + paper P&L. Admin retains existing email; F&F opt in via dashboard.
- **News integration** — per-market dashboard panel from `yfinance.Ticker.news` + critical-event flag using yfinance importance hint with hand-curated keyword fallback.
- **Guide UI** — inline tooltips on every panel + one-time first-run walkthrough modal for new users.
- **Retroactive validation sweep** — backfill Nyquist `VALIDATION.md` + `SECURITY.md` for v1.2 Phases 17/19/20/22/23/24/25/26 (only 23 + 27 currently have one).
- **Bug fix** — `.planning/backtests` CWD-relative path → project-root-anchored.

**Key context:**

- Phase numbering continues from Phase 28.
- Hard constraint preserved: signal-only — no live trading. F&F inherit the same constraint.
- Privacy: F&F never see admin or each-other data; admin sees user list + invite/revoke only, never F&F trade content.
- Schema migration must preserve admin's live paper-trade history (no fresh start).

## Core Value

Deliver an accurate, reproducible daily signal and actionable instruction ("close LONG / open SHORT / hold") to one email inbox every weekday at 08:00 AWST — with full state persistence so P&L, positions, and trade history survive restarts. **Validated in v1.0.**

## Requirements

### Validated

All 80 v1.0 + 40 v1.1 + 22 v1.2 = **142 requirements** shipped.

**v1.0** (see [milestones/v1.0-REQUIREMENTS.md](milestones/v1.0-REQUIREMENTS.md)):
- ✓ DATA (6), SIG (8), SIZE (6), EXIT (9), PYRA (5), STATE (7), NOTF (10), DASH (9), SCHED (7), CLI (5), ERR (6), CONF (2) — v1.0

**v1.1** (see [milestones/v1.1-REQUIREMENTS.md](milestones/v1.1-REQUIREMENTS.md)):
- ✓ INFRA, WEB, AUTH (incl. AUTH-04..12 phone-friendly auth UX), TRADE, CALC, SENTINEL, UAT — 40/40 verified

**v1.2** (see [milestones/v1.2-REQUIREMENTS.md](milestones/v1.2-REQUIREMENTS.md)):
- ✓ **TRACE (5)** — per-signal Inputs/Indicators/Vote panels, hand-reproducible — v1.2
- ✓ **LEDGER (6)** — paper-trade ledger with mark-to-market P&L + aggregate stats — v1.2
- ✓ **ALERT (4)** — stop-loss CLEAR/APPROACHING/HIT state machine + dedup'd email alerts — v1.2
- ✓ **VERSION (3)** — `STRATEGY_VERSION` constant + signal/trade row tagging + retroactive migration — v1.2
- ✓ **BACKTEST (4)** — pure-compute `backtest/` module + 5y walk-forward + `/backtest` route + `>100%` cum-return pass criterion — v1.2

### Active (v1.3 — in flight)

Items pulled into v1.3 scope (see Current Milestone section above):

- [ ] **Phase 28 (v1.2 UAT closure)** — Phase 17 ATR hand-recalc + iOS Safari tap + cookie persistence; Phase 23 live yfinance CLI + `/backtest` browser smoke; Phase 26 cold-start + multi-tab market browser walkthrough (8 items total)
- [ ] **v1.2.1 retroactive patch wrap** — formalise 5 post-ship polish commits (scheduler tz, signal status ladder, v1.1 backtested defaults, trace vote_params, market tab refresh)
- [ ] **Multi-tenant refactor + RBAC** — admin namespace separation; invite-only F&F with per-user state isolation; admin user management
- [ ] **Per-user email pipeline** — each F&F user gets their own 08:00 Sydney email
- [ ] **News integration** — dashboard panel + critical-event flag (was Phase 21, now scoped narrower than original brief)
- [ ] **Guide UI** — inline tooltips + first-run tour modal
- [ ] **Retroactive validation sweep** — Nyquist `VALIDATION.md` + `SECURITY.md` for Phases 17/19/20/22/23/24/25/26
- [ ] `.planning/backtests` path CWD-relative — make project-root-anchored

### Active (v1.4+ candidates)

- [ ] **Phase 23.5** — Hygiene cleanup (backups, deliverability, per-user TZ — last item now relevant given multi-tenant)

Carried-forward from v1.0/v1.1:
- [ ] F1 full-chain integration test harness completion (Phase 15 added partial coverage; gaps remain)
- [ ] Holiday-calendar-aware staleness threshold
- [ ] Thread-safe `_LAST_LOADED_STATE` cache

### Out of Scope (v1.0 validated)

- Live order execution — signal-only; Marc places trades manually. **Hard constraint.**
- Any instruments beyond SPI 200 and AUD/USD — adding more is a v2+ milestone.
- Intraday data / tick-level signals — daily close only.
- Backtesting UI — the app only runs forward.
- ~~Multi-user accounts / auth — single-operator tool.~~ **Re-scoped in v1.3:** invite-only multi-tenant for friends-and-family with full per-user state isolation. Admin (Marc) is sole invite issuer; no public signup.
- React / Vue / any SPA framework — dashboard is a single static HTML file.
- Database — all state lives in one `state.json` file.
- Financial advice / regulatory disclosures — footer disclaimer only.

## Context

- **Shipped:** v1.0 on 2026-04-24 after 4 days of work (~5,800 source LOC Python, 662 tests, 250 commits, 9 phases).
- **User:** Marc (Perth, AWST UTC+8 year-round, no DST) — runs Carbon Bookkeeping, Resend configured with verified sender `signals@carbonbookkeeping.com.au`.
- **Architecture:** Hexagonal-lite. Pure-math modules (`signal_engine`, `sizing_engine`, `system_params`) with AST-enforced forbidden-imports blocklist. I/O adapters (`state_manager`, `notifier`, `dashboard`) with no cross-imports. `main.py` is the sole orchestrator.
- **Deployment:** DigitalOcean droplet systemd is the PRIMARY path (Phase 11 onwards). GitHub Actions cron is disabled (`.github/workflows/daily.yml.disabled`) per Phase 10 INFRA-03 to avoid duplicate signal emails; the disabled workflow retains `timeout-minutes: 10` as rollback insurance. Replit Always On is retired from active docs as of Phase 27-16 (preserved only in the v1.0 milestone archive at `.planning/milestones/v1.0-phases/07-scheduler-github-actions-deployment/`). Active runbooks: `SETUP-DROPLET.md` (one-time bring-up) + `docs/DEPLOY.md` (routine ops).
- **State persistence:** The droplet's daily run commits `state.json` back to `origin/main` via a GitHub deploy key (Phase 10 INFRA-02 / `_push_state_to_git` in `main.py`); Replit filesystem persists if Always On is active.
- **Testing:** 662 tests passing, 0 failing. `tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent` AST-walks hex modules to enforce boundary invariants.
- **Known deferred UAT:** 4 operator-facing visual checks (dashboard rendering, Gmail email rendering) recorded in STATE.md §Deferred Items — cannot be automated in GSD session.

## Constraints

- **Tech stack**: Python 3.11.8, `yfinance 1.2.0`, `pandas 2.3.3`, `numpy 2.0.2`, `requests`, `schedule`, `python-dotenv`, `pytz`, `pytest 8.3.3`, `pytest-freezer`, `ruff 0.6.9` — all version-pinned in `requirements.txt`.
- **Email transport**: Resend HTTPS API only. No SMTP.
- **Storage**: Single `state.json` file. No SQLite/Postgres/Redis.
- **Dashboard**: Single self-contained `dashboard.html` with inline CSS and CDN Chart.js 4.4.6 (SRI-pinned). No build step.
- **Email rendering**: Inline CSS only — email clients strip `<style>` blocks. Must render on mobile.
- **Determinism**: Daily signal output reproducible from `state.json` + Yahoo data for the same date.
- **Signal-only**: No hook or flag places a live trade. Hard constraint.
- **Secrets**: All credentials via `.env` locally or GitHub Secrets — never committed. `state.json` is gitignored locally, committed only by the GHA workflow.
- **Schedule**: 08:00 Perth time weekdays — `cron "0 0 * * 1-5"` UTC.
- **Error budget**: App must never crash silently. All errors caught, logged, and surfaced in the next email as a warning (except `DataFetchError`/`ShortFrameError` which log + exit rc=2 — deliberate, per ERR-01 Phase 9 amendment).

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Python + yfinance + Resend | User already on Resend; Python has mature TA libs; runs on Replit/GHA with no infra | ✓ Good |
| Single `state.json` file | Simplicity, portability across Replit and GitHub Actions | ✓ Good |
| Perth time (AWST) schedule, cron `0 0 * * 1-5` UTC | Marc is in Perth — no DST simplifies cron | ✓ Good |
| ATR + vol-target sizing, `n_contracts == 0` skips trade (no floor) | Matches the backtested system exactly; 0-floor silently breaches risk budget on small accounts | ✓ Good |
| Static `dashboard.html` with Chart.js CDN (SRI-pinned) | Zero build step, matches prior backtest aesthetic; SRI prevents CDN tampering | ✓ Good |
| Signal-only, no live trading | Explicit user directive — risk mitigation | ✓ Good |
| DO droplet systemd PRIMARY (v1.1); GHA cron disabled (rollback insurance); Replit retired from active docs (27-16) | Droplet gives HTTP-serving capability for FastAPI (v1.1 Phase 11+); GHA cron retired in Phase 10 INFRA-03 to avoid duplicate emails; state.json pushed back via deploy key per Phase 10 INFRA-02 | ✓ Good (v1.1) |
| Hexagonal-lite: signal_engine ↔ state_manager no cross-import; main sole orchestrator | Keeps pure-math modules testable in isolation; AST blocklist enforces at CI time | ✓ Good |
| Two-tier email banner (critical vs routine) + `[!]` subject prefix | Critical banners (stale-state, corrupt-recovery) always visible at top; routine warnings compact | ✓ Good (Phase 8) |
| `_LAST_LOADED_STATE` module cache for crash-email state summary | Gives crash email access to last-loaded state without threading state through the scheduler | ⚠️ Revisit if parallel runs appear (v2) |
| Underscore-prefix persistence rule (`_resolved_contracts`, `_stale_info`) | Runtime-only keys auto-stripped by `save_state`; new convention | ✓ Good (Phase 8 D-14) |
| ERR-01 data-fetch errors log + exit rc=2, no email | Transient yfinance/network errors are expected; emailing on every blip is noise | ✓ Good (Phase 9 spec amendment) |
| Trailing stops use intraday HIGH/LOW (peak updates + hit detection) | Consistent intraday convention matches how the backtest was built | ✓ Good |
| Skip Phase 18 multi-user through v1.2 (D-01) | Single-operator model from v1.1 sufficient; revisit if friends-and-family demand emerges | ✓ Good (v1.2) |
| Backtest pass criterion = `cumulative return > 100% over 5y` (D-04) | Strict ledger-style threshold per operator brainstorm; Sharpe / drawdown / win rate displayed but not gating | ✓ Good (v1.2) |
| `STRATEGY_VERSION` semver bumped on signal-logic change only (D-05) | Mom thresholds / ADX gate / sizing weights are the trigger; `v1.2.0` at v1.2 launch | ✓ Good (v1.2) |
| Two-axis nav `/markets/{MARKET}/{FN}` with cookie + URL persistence (D-06, Phase 25) | Lets trader switch market once and have every panel scope to it across navs and refreshes | ✓ Good (v1.2) |
| Money math uses `Decimal` quantized HALF_UP to AUD cents on save; indicators stay float64 (D-07, Phase 27) | Eliminates float drift on P&L while keeping signal compute fast; schema v8→v9 migrates existing rows on load | ✓ Good (v1.2) |
| Naive datetimes fail-closed at write paths; migration chain contiguity asserted at module load (D-08, Phase 27) | Catches tz-drift bugs at the boundary; prevents silently-skipped migrations from corrupting state | ✓ Good (v1.2) |
| Production source files capped at 500 LOC (D-09, Phase 27) | notifier/main/dashboard split into packages with byte-identical render parity (largest daughter 347 LOC) | ✓ Good (v1.2) |
| DigitalOcean droplet + systemd is documented PRIMARY (D-10, Phase 27-16); GHA cron disabled, preserved as rollback insurance | Replit retired from active docs (preserved only in v1.0 archive); `daily.yml.disabled` keeps the path back open without dual-emailing | ✓ Good (v1.2) |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each milestone** (via `/gsd-complete-milestone`):
1. Validated section: shipped requirements marked with v version reference
2. Active section: new candidates for next milestone
3. Out of Scope audit: reasons still valid?
4. Context: LOC, tech stack, user feedback themes, known issues
5. Key Decisions: outcomes updated (✓ Good, ⚠️ Revisit, — Pending)

---

*Last updated: 2026-05-13 — Phase 34 complete (User Registry + Invite-Token Storage). auth_store/ package split from 520-LOC monolith; User + PendingInvite TypedDicts; v1→v2 schema migration; invite token mint/consume with LOCK_EX single-use guarantee; InviteAlreadyConsumed + InviteExpired typed exceptions (SC-4); 2151 tests green. RBAC-03 storage half delivered; RBAC-04 disabled flag stored (enforcement in Phase 35/36).*

<details>
<summary>Historical: v1.1 Progress (archived)</summary>

- [x] **Phase 10**: Foundation — v1.0 Cleanup & Deploy Key (shipped 2026-04-24)
- [x] **Phase 11**: Web Skeleton — FastAPI + uvicorn + systemd (shipped 2026-04-24)
- [x] **Phase 12**: HTTPS + Domain Wiring (shipped 2026-04-24)
- [x] **Phase 13**: Auth + Read Endpoints (shipped 2026-04-25)
- [x] **Phase 14**: Trade Journal — Mutation Endpoints (shipped 2026-04-30)
- [x] **Phase 15**: Live Calculator + Sentinels (shipped 2026-04-30)
- [x] **Phase 16**: Hardening + UAT Completion (shipped 2026-04-30)
- [x] **Phase 16.1**: Phone-friendly auth UX (shipped 2026-04-29)

</details>
