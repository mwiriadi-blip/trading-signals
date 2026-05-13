# Requirements — v1.3 Multi-Tenant Friends & Family

**Milestone:** v1.3
**Goal:** Open the system to invite-only friends-and-family with full per-user state isolation, per-user 08:00 Sydney emails, news context, and a guided UI — while closing v1.2 deferred UAT debt and retroactively wrapping the post-v1.2 polish commits as v1.2.1.

**Status:** Drafted 2026-05-10 from research synthesis (see [research/SUMMARY.md](research/SUMMARY.md)).

**REQ-ID convention:** `[CATEGORY]-NN` continues numbering within each category from existing v1.0–v1.2 prefixes. New v1.3 categories use fresh prefixes.

---

## v1.3 Requirements

### DEBT — v1.2 closure (4 requirements)

- [x] **DEBT-01**: Operator can verify all 8 deferred v1.2 UAT scenarios — Phase 17 ATR(14) hand-recalc to 1e-6, Phase 17 iOS Safari tap-to-toggle trace panel, Phase 17 cookie persistence across reload, Phase 23 live yfinance CLI run (`python -m backtest --years 5`), Phase 23 `/backtest` browser visual smoke, Phase 26 cold-start smoke on production droplet, Phase 26 multi-tab market scoping browser walkthrough (UAT-2..6) — all signed off in `VERIFICATION.md`.
- [ ] **DEBT-02**: 5 ad-hoc post-ship polish commits from 2026-05-08..05-10 (scheduler tz fix, signal status ladder trigger, v1.1 backtested per-market defaults, trace vote_params, market tab strip refresh) are formalised as a v1.2.1 retroactive patch phase with tests + a single-commit `MILESTONES.md` note.
- [ ] **DEBT-03**: v1.2 Phases 17, 19, 20, 22, 24, 25, 26 each have a `VALIDATION.md` (Nyquist coverage matrix) backfilled retroactively to match the format of Phase 23 + 27.
- [ ] **DEBT-04**: v1.2 Phases 17, 19, 20, 22, 23, 24, 25, 26 each have a `SECURITY.md` (threat-model + mitigations) backfilled retroactively to match the format of Phase 27.

### OPS — refactor + ops hygiene (4 requirements)

- [x] **OPS-01**: Pre-existing 500-LOC violators (`web/routes/trades.py`, `web/routes/login.py`, `web/routes/totp.py`, `web/routes/dashboard.py`, `web/routes/paper_trades.py`) are split behaviour-preservingly under the v1.2 D-09 cap, with each daughter file ≤500 LOC and full route + template + test parity verified before any v1.3 multi-tenant change lands.
- [ ] **OPS-02**: `.planning/backtests/` path resolution is project-root-anchored (not CWD-relative), so `python -m backtest` and `/backtest` work identically regardless of caller's working directory.
- [ ] **OPS-03**: AST hex-boundary guard (`tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent`) is extended so `signal_engine`, `sizing_engine`, `system_params`, and `backtest/` cannot import any of `news_fetcher`, `news_filter`, `auth_store`, `web/*`, or other v1.3-introduced I/O modules.
- [ ] **OPS-04**: Operator runs codemoot + Nyquist gate at milestone close, verifies findings against current code (false-positive sweep), and records resolutions in `.planning/REVIEWS.md`. No critical findings remain unresolved at v1.3 close.

### TENANT — multi-tenant data isolation (4 requirements)

- [ ] **TENANT-01**: Schema migrates from `STATE_SCHEMA_VERSION = 11` (codebase truth) to v12 by build-then-validate-then-save: existing admin paper trades / journal / equity / alerts / preferences move into `state['users']['admin_<uid>']` namespace; auto-backup `state.json.v11-backup` is written before migration; round-trip test on 5 fixtures (lossless v11→v12→v11') passes; migration-chain contiguity assertion at module load passes.
- [ ] **TENANT-02**: User can have their own paper trades, journal, alerts, equity history, drift sentinels, UI preferences, and trusted-device cookies isolated from every other user, with `mutate_user_state(user_id, mutator)` preserving the existing single-writer atomic-write contract via per-user `fcntl.flock` advisory locks.
- [ ] **TENANT-03**: Operator can run the `TestTenantIsolation` test class (milestone-wide quality gate) and see green — fixture user holding 5 paper trades produces zero `entry_price | n_contracts | "direction":\s*"(LONG|SHORT)"` matches in admin user-list HTML, in any log line, in the crash-email body, or in any other user's served pages; `PublicUserSummary` Pydantic model + `RedactStateFilter` enforce the redaction.
- [ ] **TENANT-04**: Operator can verify `state/users/` is gitignored and never appears in `git ls-files`; CI gate fails the build if any per-user state path enters tracked files; off-droplet backup (e.g. rclone-to-B2 or equivalent) runs daily and admin gets an alert email if backup is older than 48h.

### RBAC — auth + invite-only + admin gate (4 requirements)

- [x] **RBAC-01**: Authenticated user has their `user_id` available declaratively via `Depends(current_user)` in every route; cookie session payload extends to include `uid`; admin remains the only user with no observable behaviour change at this stage; pre-v1.3 routes get scoped via the dependency, not per-route boilerplate.
- [x] **RBAC-02**: Admin-only routes live under `APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])` sub-router so the gate is set at mount time; a startup invariant test walks `app.routes` and asserts every `/admin/*` path has `require_admin` in its dependency chain.
- [x] **RBAC-03**: Admin can issue an invite token from `/admin/users` (`secrets.token_urlsafe(32)` raw; sha256 hash stored; `hmac.compare_digest` for verify; 7-day expiry; single-use guaranteed by `flock` on consume) and the invitee can accept the link, set a password, enrol TOTP, and confirm trusted device — joining as a non-admin F&F user.
- [x] **RBAC-04**: Admin can view `/admin/users` (user list with last-login + last-paper-trade timestamps + invite-pending status, no per-user trade content) and reversibly disable any non-admin user (disabled users cannot log in, but data is preserved); terminal delete is explicitly out of scope (deferred to v1.3.x).

### UMAIL — per-user email fan-out (4 requirements)

- [ ] **UMAIL-01**: F&F user receives their own 08:00 Sydney email each weekday with their stop-loss alerts, paper-trade P&L, and the shared signal block; admin retains the existing daily email; signal compute happens once per market per day (no extra yfinance fetches per user).
- [ ] **UMAIL-02**: Daily-cycle fan-out has a per-user `try/except` crash boundary so one user's broken state cannot abort the cycle for any other user; admin receives an end-of-cycle summary email listing successes + per-user failures; `/healthz/last-cycle` endpoint reports the cycle's user-level outcomes for monitoring.
- [ ] **UMAIL-03**: Per-user fan-out throttles outbound Resend calls via `asyncio.Semaphore(2)` (or equivalent under the documented rate limit ÷ 2); RFC 8058 `List-Unsubscribe` + `List-Unsubscribe-Post` headers are present on every per-user email; no session token, no invite token, and no other secret appears in the email body or URLs.
- [ ] **UMAIL-04**: User can enable / disable their daily email and set a `pause-until-YYYY-MM-DD` toggle from the dashboard; preference persists in their per-user state; fan-out skips paused / disabled users without burning a Resend quota; admin's email is unaffected by F&F preferences.

### NEWS — yfinance news + critical-event flag (4 requirements)

- [ ] **NEWS-01**: User can see the top 5 latest `yfinance.Ticker.news` headlines per market (SPI 200, AUD/USD) on the dashboard `/markets/{m}` route, deduplicated by title hash, cached daily (one fetch per market per day shared across users), Jinja2 `autoescape=True`, outbound links rel="noopener noreferrer".
- [ ] **NEWS-02**: User can see a critical-event banner per market when a hand-curated word-boundary regex classifier fires (per-market keyword list with allowlist dampener like "first-rate", "second-rate"); banner copy explicitly labels the heuristic ("Possible market-moving news — operator review recommended"); classifier achieves precision ≥0.7 and recall ≥0.9 against a 30-headline labelled fixture committed to the repo.
- [ ] **NEWS-03**: News-fetch adapter normalises both pre-0.2.55 flat-list yfinance shape and post-0.2.55 nested `content` envelope into one internal model; both-shape fixtures pass; an `<script>alert(1)</script>` headline renders as escaped text; SSRF risk on link rendering is closed by render-time-only escape (no server-side prefetch of headline links).
- [ ] **NEWS-04**: User can dismiss a headline from their dashboard; dismiss state persists in `state['users'][uid]['news_dismissed']` so the headline does not reappear for them; admin's dismiss does not affect any F&F user's view, and vice versa.

### GUIDE — UI tour + tooltips (4 requirements)

- [ ] **GUIDE-01**: User can hover or focus any panel header / control on the dashboard and see an inline tooltip (Microtip-based, pure-CSS, survives HTMX swaps with no JS rebind) with WAI-ARIA `role="tooltip"`, ≥16px font on mobile, unique `aria-describedby` ID; tooltip count adds zero new tab stops on inactive market panels and zero new axe-core violations vs the Phase 25 baseline.
- [ ] **GUIDE-02**: New F&F user sees a 3-step first-run tour on first dashboard load (Shepherd.js v14.5.1 CDN/SRI, license-verified at install or Driver.js MIT fallback) covering: Step 1 — dashboard navigation, Step 2 — Inputs/Indicators/Vote trace panel (the v1.2 differentiator), Step 3 — paper-trade entry; tour state is server-side per-user (`state['users'][uid]['tour_completed']`, NOT localStorage), tour DOM is portal-mounted at `<body>` level (NOT inside any HTMX swap target), tour survives `htmx:afterSwap` of `#main` via re-validation.
- [ ] **GUIDE-03**: User can press Esc to dismiss the tour, click "Skip tour", or complete the tour — all three paths set `tour_completed: true` in their per-user state; tour modal is `role="dialog"` with focus-trap; keyboard-only flow (Tab cycles through dialog buttons; Esc closes) verified by a Playwright keyboard-only test.
- [ ] **GUIDE-04**: User can click a persistent "Restart tour" link in the dashboard header (or `/help` route) to replay the tour from step 1; this clears `tour_completed` server-side and reruns the tour; second click after completion works idempotently (no stale Shepherd.js state).

---

## v1.3.x Future Requirements (deferred)

- Terminal user delete (with confirm-by-typing modal + per-user backup before delete) — DEBT against the v1.3 disable-only choice.
- Admin terminal delete UX — pairs with above.
- Bulk invite (CSV upload) — out of scope for ≤dozens of users.
- Per-user timezone override — current fan-out is single AEST/AEDT 08:00; multi-TZ becomes relevant once F&F lives outside Australia.
- Resend webhook open-rate tracking — non-essential for v1.3.
- Admin "view as user" mode — explicit privacy violation in v1.3; revisit only if support cases demand it (and only behind a logged audit trail).
- Web push notifications — outside v1.3 scope; email is sufficient.

## Out of Scope (explicit exclusions)

- **Public signup** — v1.3 is invite-only; admin is sole invite issuer. Any "register" route is a privilege-escalation surface and is not built.
- **Live trading / order execution** — hard constraint inherited from v1.0; F&F users get the same constraint. No `/api/orders` endpoint exists.
- **Real-time chat / messaging between users** — anti-feature; out of scope.
- **News-driven signal influence** — sentiment is read-only context; the mechanical signal vote does not consume news. Strategy stays deterministic + reproducible from `state.json` + Yahoo data alone (per v1.2 BACKTEST gate).
- **Billing / payments** — F&F is gratis; no paywall, no Stripe.
- **Third-party data brokering** — yfinance + Resend are the only external dependencies; no shipping user data anywhere else.
- **Cross-user leaderboard / social features** — privacy boundary is absolute; no aggregate F&F P&L view.
- **Per-user signal customisation** — every user gets the same SPI 200 + AUD/USD signals; per-user customisation would break "compute once" determinism.
- **In-dashboard charting beyond equity curve** — Chart.js stays single-purpose.
- **SQLite / Postgres / Redis** — file-based state remains the storage contract.
- **SPA framework** — HTMX-only.
- **SMTP** — Resend HTTPS API only.

## Traceability

| REQ-ID | Phase | Plan | Status |
|--------|-------|------|--------|
| DEBT-01 | Phase 28 | TBD | Mapped |
| DEBT-02 | Phase 29 | TBD | Mapped |
| DEBT-03 | Phase 29 | TBD | Mapped |
| DEBT-04 | Phase 29 | TBD | Mapped |
| OPS-01 | Phase 30 | TBD | Mapped |
| OPS-02 | Phase 29 | TBD | Mapped |
| OPS-03 | Phase 30 | TBD | Mapped |
| OPS-04 | Phase 38 | TBD | Mapped |
| TENANT-01 | Phase 31 | TBD | Mapped |
| TENANT-02 | Phase 34 | TBD | Mapped |
| TENANT-03 | Phase 34 | TBD | Mapped |
| TENANT-04 | Phase 31 | TBD | Mapped |
| RBAC-01 | Phase 33 | TBD | Mapped |
| RBAC-02 | Phase 33 | TBD | Mapped |
| RBAC-03 | Phase 32+35 | TBD | Mapped |
| RBAC-04 | Phase 34 | TBD | Mapped |
| UMAIL-01 | Phase 35 | TBD | Mapped |
| UMAIL-02 | Phase 35 | TBD | Mapped |
| UMAIL-03 | Phase 35 | TBD | Mapped |
| UMAIL-04 | Phase 35 | TBD | Mapped |
| NEWS-01 | Phase 36 | TBD | Mapped |
| NEWS-02 | Phase 36 | TBD | Mapped |
| NEWS-03 | Phase 36 | TBD | Mapped |
| NEWS-04 | Phase 36 | TBD | Mapped |
| GUIDE-01 | Phase 37 | TBD | Mapped |
| GUIDE-02 | Phase 37 | TBD | Mapped |
| GUIDE-03 | Phase 37 | TBD | Mapped |
| GUIDE-04 | Phase 37 | TBD | Mapped |

**Total: 28 requirements** across 7 categories (DEBT 4, OPS 4, TENANT 4, RBAC 4, UMAIL 4, NEWS 4, GUIDE 4).

---

*Last updated: 2026-05-10 (drafted from research synthesis).*
