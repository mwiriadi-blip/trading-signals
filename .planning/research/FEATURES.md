# Feature Research — v1.3 Multi-Tenant Friends & Family

**Domain:** Invite-only multi-tenant trading-signal SaaS (single admin, ≤dozens of trusted F&F users; signal-only, no live trading; Python + FastAPI + HTMX + JSON state)
**Researched:** 2026-05-10
**Confidence:** HIGH on RBAC + tour + tooltip patterns, MEDIUM on yfinance news schema (no native importance flag — keyword fallback is mandatory), HIGH on the anti-feature list (constrained by existing v1.0 hard rules)

**Scope note:** This document is the **v1.3 delta only**. All v1.0/v1.1/v1.2 table-stakes features (signal compute, paper ledger, alerts, drift sentinels, trace panels, two-axis nav, auth UX) are already shipped — see `.planning/research/v1.0-archive/FEATURES.md` for that baseline. Do not re-litigate it here.

**Existing modules referenced (dependencies for new features):**

- `state_manager.py` — single `state.json`, atomic writes, schema chain v1→v9 (Decimal money). v1.3 adds v9→v10 (per-user namespace).
- `notifier/` package — Resend HTTPS dispatch, two-tier banners, `[!stop]` alert dedup. v1.3 adds per-user fan-out.
- `dashboard_legacy/` package — static HTML, two-axis market×function nav, cookie + URL persistence. v1.3 adds tooltip layer + tour.
- `auth/` (Phase 13 + 16.1) — cookie session, TOTP, trusted-device, magic-link. v1.3 adds invite-acceptance + admin user-list routes.
- `main.py` — sole orchestrator, daily 08:00 Sydney systemd cycle. v1.3 adds per-user loop after the shared signal compute.
- `backtest/` — pure compute, hex-boundary respected. **Unchanged in v1.3.**
- `signal_engine` / `sizing_engine` / `system_params` — pure-math, signals are SHARED & deterministic across all users. **Unchanged in v1.3.**

---

## Feature Landscape

### Table Stakes (Users Expect These)

These are the features any invited F&F user will assume work on day one. Missing any of these = they bounce or admin gets a phone call.

| # | Feature | Why Expected | Complexity | Existing modules touched | Notes |
|---|---------|--------------|------------|---------------------------|-------|
| **RBAC** ||||||
| 1 | Admin issues invite via dashboard form | Admin needs a one-click "invite Mum" path; manual SQL/JSON edits don't scale beyond 0 users | S | `auth/`, `dashboard_legacy/`, `state_manager` | Form: invitee email + display name. Generates token, returns shareable link. |
| 2 | Invite token: signed, single-use, time-bounded | Token in URL is the only thing standing between F&F and account creation; must not be guessable, replayable, or perpetual | S | `auth/` (new `invite.py`) | `itsdangerous.URLSafeTimedSerializer` + state-tracked redemption flag. **Don't roll your own JWT — use stdlib + signed-token lib.** Recommended: 7-day expiry, single-use (consumed on TOTP enrol), bound to invitee email so a stolen link still needs the right inbox. |
| 3 | Invite link delivers via email (not just copied link) | Out-of-band proof-of-email; admin stops being a manual copy/paste relay | S | `notifier/` | Reuse Resend transport. Subject: "You're invited to [app]". Body: link + 7-day expiry callout. |
| 4 | Invitee proves identity by clicking link + setting password + enrolling TOTP | F&F have no SSO; password + TOTP is the v1.1 pattern, must extend not replace | M | `auth/` | Existing TOTP enrol flow (Phase 16.1) reused with `invite_token` query param prefilling email. |
| 5 | Admin sees user list with status (active / disabled / pending invite) | Admin needs "did Mum accept the invite yet?" answer at a glance; otherwise admin ends up DMing each user | S | `dashboard_legacy/` (new admin route) | `/admin/users` HTMX panel. Columns: email, display name, status, invited_at, last_login_at, # paper trades. Admin-only middleware gate. |
| 6 | Admin can **disable** (reversible) and **delete** (terminal) users — distinct verbs | These are different operations with different audit semantics; conflating them is how data loss happens | S | `state_manager`, `auth/` | **Disable:** flips `status=disabled`, kills sessions, blocks future login, preserves user's paper-trade history & journal (so re-enable restores everything). **Delete:** purges user_id namespace from `state.json`; one-way; requires confirm-by-typing-email modal. **Recommend ship disable in v1.3 + ship delete behind feature flag** — disabling is enough for mistake-recovery; deletion is GDPR-right-to-erasure territory and easy to footgun. |
| 7 | Admin can revoke an unaccepted invite | Admin sent invite to wrong email; needs an undo before token expires | S | `state_manager` | Mark invite token as revoked in state; redemption check rejects revoked tokens before signature check (cheap, also avoids constant-time games). |
| 8 | F&F users **cannot** see admin or each other (privacy boundary) | Hard requirement from PROJECT.md; failure here = the whole tenancy story collapses | M | `state_manager`, all read routes | Every read path goes through `get_user_state(user_id)` — no `state.json` global reads survive. Admin's data lives under the admin namespace; F&F under per-user namespaces. **Admin user-list view never embeds F&F trade content** — only status metadata. |
| **Per-user state isolation** ||||||
| 9 | Per-user paper-trade ledger | Each F&F runs their own paper account; sharing trades would be confusing AND a privacy leak | M | `state_manager` (LEDGER schema), `dashboard_legacy/` | Existing `paper_trades` table becomes `paper_trades[user_id]`. Trade entry forms scope by `request.user.id`. |
| 10 | Per-user equity history & starting account | Marc may run $100k; Mum may want to see what $10k looks like; without per-user starting balance the dashboard is meaningless | M | `state_manager`, `dashboard_legacy/` | Per-user `starting_account`, `equity_history`. Default $100k; first-run modal lets user pick (see Tour Step 2). |
| 11 | Per-user stop-loss alert dedup state (`last_alert_state`) | Without per-user dedup, one user's "ALERT HIT" event would silence everyone else's alert; or worse, send N copies | S | `state_manager` (ALERT schema), `notifier/` | `last_alert_state[user_id][market]`. Existing CLEAR/APPROACHING/HIT state machine (Phase 20) re-keyed. |
| 12 | Per-user journal entries / position drift annotations | Journal is private notes; cross-user visibility is a privacy fail | S | `state_manager`, `dashboard_legacy/` | Existing trade-journal table re-keyed by user_id. |
| 13 | Per-user trusted-device cookie pool | TOTP trusted-device must not let user A skip 2FA on user B's account because cookies got mixed | S | `auth/` | Existing trusted-device cookie (Phase 16.1) already keyed to user; verify keying survives the multi-tenant refactor. **Greppable risk** — call this out in the Phase 28+ test plan. |
| 14 | **Shared** signal compute (one yfinance fetch, one signal calc per market per day) | Signals are deterministic and identical for every user — re-running for each user wastes API calls + invites determinism drift | S | `main.py`, `signal_engine` | Compute signal ONCE per market per day; fan out per-user state updates (alerts, equity, drift) downstream. **Critical:** keep the hex-boundary clean — signal_engine still pure, no user_id leaks into signal logic. |
| **Per-user email** ||||||
| 15 | Each user receives their own 08:00 Sydney email | The whole point of per-user state is per-user actionable output; sharing one email defeats the purpose | M | `notifier/`, `main.py` | Loop after shared signal compute: `for user in active_users: send_user_email(user, signal)`. **Subject still flags signal change** (existing two-tier banner from Phase 8). Per-user content: their alerts, their P&L, their open positions. Shared content: the signal itself, market news. |
| 16 | Email opt-out / pause (per user) | Some F&F will want to "watch the dashboard but stop the daily email"; without an opt-out they unsubscribe externally and break the engagement | S | `state_manager`, `notifier/` | Per-user `email_enabled: bool` + `paused_until: date` (for vacations). Dashboard toggle + "Pause until [date]" picker. Admin retains override. **Don't add CAN-SPAM unsubscribe footer** — these are transactional, US CAN-SPAM exempts them, and an unsubscribe footer would let users break the product without realising it. Use the dashboard toggle as the single explicit control. |
| 17 | Failed-delivery handling per user | Resend bounces on a user's address must NOT block the loop or break other users' emails | S | `notifier/`, `main.py` | Wrap each per-user send in try/except; log + warn admin via admin's email banner. **Anti-pattern:** crashing main.py because user 5's mailbox is full — every user must be independent. |
| **News integration** ||||||
| 18 | News panel per market on dashboard (SPI 200 + AUD/USD) | The brainstorm says "news context" is part of v1.3; it's the headline differentiator vs the v1.2 dashboard | M | `dashboard_legacy/`, new `news_fetcher.py` | `yfinance.Ticker.news` per ticker. Render top N headlines with publisher + relative-time. **Recommended N=5** — enough context, not enough to scroll-bury the signal panels. |
| 19 | Headline deduplication (same story across publishers) | yfinance returns the same Reuters story syndicated by 4 publishers; uncuratedlooks broken | S | `news_fetcher.py` | Dedup on normalised title (lowercase, strip punctuation) within last 24h. Keep most-recent timestamp. |
| 20 | Refresh cadence: piggyback on daily 08:00 cycle | News fetch is not free (yfinance unofficial endpoint, rate limits); a separate refresh loop is over-engineering | S | `main.py` | Fetch news in the same daily run, cache in `state.json` under `market_news[market]` with `fetched_at` timestamp. Dashboard renders from cache. **Decision:** stale news (>24h) shows "as of [time]" rather than hiding — operator sees the cache age. |
| 21 | Critical-event banner with **keyword-based** classifier | yfinance.Ticker.news has NO native importance/severity field (verified — schema is `uuid/title/publisher/link/providerPublishTime/type/thumbnail/relatedTickers`); without a heuristic, every story looks the same | M | `news_fetcher.py` | **Use a hand-curated keyword list per market** (FOMC, RBA, rate decision, NFP, CPI, war, crash, halt, suspended, intervention, …). Match case-insensitive against title. Banner: "Possible market-moving news — review before trading." **Be explicit in the banner that this is a heuristic** ("Keyword-flagged headline detected"), not a Reuters-grade severity score. |
| 22 | News panel does NOT influence signal compute | Hard constraint inherited from v1.0 anti-feature: "No news / sentiment / social signals" | — | `signal_engine` | AST-enforced forbidden-import (existing `TestDeterminism::test_forbidden_imports_absent`) extends to `news_fetcher` — `signal_engine` may not import it. Add to the AST blocklist as part of Phase 21 work. |
| **Guide UI** ||||||
| 23 | First-run walkthrough modal for new users | Without it, F&F see the unfamiliar dashboard and bounce; the tour is the activation event | M | `dashboard_legacy/`, `state_manager` | **3-step tour** (research: 3-step tours hit 72% completion vs 16% at 7 steps). Steps: (1) "Here's today's signal — read top to bottom", (2) "Set your starting paper account", (3) "Enable daily email or pause it from the toggle". `tour_completed: bool` per user; bypass on subsequent loads. |
| 24 | Inline tooltips on every panel | F&F don't know what ATR/ADX/Mom/RVol mean; without inline help, the trace panels (Phase 17 differentiator) are wasted on them | M | `dashboard_legacy/` | Pattern: small `?` icon adjacent to each panel header. Click/tap (mobile-safe — NOT hover-only). `role="tooltip"` + `aria-describedby` (per WAI-ARIA tooltip pattern). Content: 1-2 sentences max. Don't repeat what's visible; explain what the panel means. |
| 25 | Tour skip + replay-from-help | Power users (Marc, returning F&F) skip; new users mid-tour get interrupted — both must work | S | `dashboard_legacy/` | "Skip" button on every step. Help icon in header → "Restart tour". State: `tour_completed` + `tour_dismissed_at`. **Eloquent locality:** tour state lives in `state.json` per user (not localStorage) so it persists across devices — F&F user starts on phone, finishes on desktop. |
| 26 | Tooltip mobile UX: tap-to-toggle, tap-outside-to-close | F&F use phones; hover-only tooltips are invisible on touch | S | `dashboard_legacy/` | Same pattern as Phase 17 trace-panel toggle (which already shipped iOS Safari fix). Reuse, don't reinvent. |

---

### Differentiators (Quality-of-Life — Ship If Cheap)

Features that lift v1.3 from "works for F&F" to "F&F use it without prompting." Ship when LOC is small; defer otherwise.

| # | Feature | Value Proposition | Complexity | Existing modules touched | Notes |
|---|---------|-------------------|------------|---------------------------|-------|
| 27 | Per-user "starting account" wizard on first login | Lets F&F right-size paper trades to what feels real; default $100k is meaningless to someone with $5k savings | S | `dashboard_legacy/`, `state_manager` | Step 2 of the tour. Slider + presets: $10k / $50k / $100k / custom. Stored per user. |
| 28 | Admin user-list shows last-login + last-paper-trade timestamps | Admin's only governance signal: "is Mum still using it?" Without this, admin has no idea if F&F have churned | S | `state_manager`, `dashboard_legacy/` | Cheap: data already exists. New columns in admin user-list view. |
| 29 | Per-user email "pause until" (date-bounded) | Better than binary opt-out — "pause for 2 weeks while I'm camping" matches how people actually want to control inbox volume | S | `state_manager`, `notifier/` | Already noted in #16. Listed here separately because it's the **eloquent** form of opt-out (preserves intent to re-engage). |
| 30 | News panel: "View on Yahoo Finance" link per headline | Headline alone isn't actionable; one-click to full story is the obvious next step | S | `dashboard_legacy/` | yfinance returns `link` field. Open in new tab. **Add `rel="noopener noreferrer"`** to every news link — third-party content. |
| 31 | News critical-event banner appears in the daily email too | If the heuristic flags a critical story, the email subject should say so — F&F may not check the dashboard | S | `notifier/` | `[!news]` subject prefix on critical-event days, alongside existing `[!]` for stop-alerts. |
| 32 | Tooltip content shows "what to do with this" not just "what this is" | Users learn faster from "When ATR is high, the system trades smaller" than from "ATR = Average True Range, a volatility measure" | S | `dashboard_legacy/` | Content discipline, not engineering. **Eloquent:** ties tooltips to the trace-panel narrative — operator-facing transparency Phase 17 already established. |
| 33 | Admin sees aggregate "F&F email open rate / paused user count" | Future-proof: helps admin decide if v1.4 onboarding tweaks are working | S | `state_manager`, `notifier/` | **Defer if cheap-to-add later.** Resend doesn't expose open-rate without webhooks; the open-rate side is a v1.4+ webhook integration. Pause-count is trivial — show that now. |
| 34 | First-run tour highlights the **trace panel** specifically | The trace panel (Phase 17) is the v1.2 differentiator; F&F won't notice it without prompting | S | `dashboard_legacy/` | Extend tour Step 1 with "Tap to see exactly why the system says what it says." Sells the existing investment. |
| 35 | Per-user timezone for the daily-email send time | All users currently get 08:00 Sydney; international F&F may want their local 08:00 | M | `main.py`, `state_manager` | **Carry-forward from v1.4 candidate (Phase 23.5).** Listed here because multi-tenancy makes it newly relevant — but ship in v1.4 not v1.3. |

---

### Anti-Features (Explicitly NOT in v1.3)

Things F&F (or admin) might ask for that would break the product. Document so scope creep dies on contact.

| # | Anti-Feature | Why Requested | Why Problematic | Alternative |
|---|--------------|---------------|-----------------|-------------|
| 36 | **Public signup** | "Why can't I just send a Twitter link?" | Public signup turns a F&F tool into a SaaS with abuse-vector mitigation, CAPTCHAs, anti-spam, billing infrastructure, support load. Scope creep that swallows the product. | **Invite-only forever.** Admin issues invites by hand. Capacity ceiling is a feature, not a bug. |
| 37 | **Real-time chat / messaging between users** | "Wouldn't it be cool if Mum could ask me a question through the app?" | Adds websockets, notifications, moderation, retention/deletion compliance, and turns the app into a social product. Marc → Mum chat already works in WhatsApp. | **No in-app comms.** Use existing channels (text, email). Optional: per-user "admin notes" the admin can leave on a user's dashboard, NOT cross-user. |
| 38 | **Live trading / broker API** | "If we know the signal, why am I still placing trades manually?" | Inherited v1.0 hard constraint. Live exec → reconciliation, order-management, regulatory exposure. F&F amplifies this 10x — now there are N people whose accounts can blow up because of one bug. | **Signal-only. F&F inherit the same constraint.** Footer disclaimer remains: "Automated signal — not financial advice." |
| 39 | **News-driven signal influence** | "If the news is bad, the system should go FLAT, right?" | Mechanical system; news inputs break determinism + the backtested edge. AST-enforced forbidden-import already blocks `news_fetcher` from `signal_engine`. | News is **context only**. Banner says "review before trading," does not modify signal or sizing. Operator owns the discretionary override. |
| 40 | **Account funding / billing / subscriptions** | "If I'm offering this to F&F, should I charge a token amount?" | Adds Stripe, invoices, dunning, refunds, Aussie GST, financial-services regulatory questions ("are you taking deposits?"), and turns the product into a regulated entity. | **Free for F&F forever.** If commercialising ever becomes interesting, that's a v3 with a different legal structure (and probably not the same product). |
| 41 | **Third-party data brokering / sharing aggregated F&F data** | "Could we sell aggregate F&F trading patterns?" | Privacy boundary collapse + financial-data regulatory minefield (APRA, CDR). Anti-feature with regulatory teeth. | **Never.** Document as out-of-scope. Per-user data is sacrosanct. |
| 42 | **Exposing yfinance "API key" or any market-data credential to F&F** | "Let users plug in their own data feed" | yfinance has no API key (it's the unofficial Yahoo Finance scraper); but Resend, the droplet's deploy key, and any future paid feed do have credentials. F&F must never see them. | All credentials live in `.env` on the droplet. F&F see render output only. **Add to Phase 27's existing API-key redaction sweep**: confirm no env var ever reaches the dashboard render or email body. |
| 43 | **In-dashboard charting (candlesticks / TA overlays / drawing tools)** | "Can I see the SPI chart with my own MAs?" | Pulls in TradingView Lightweight Charts or full chart library. Tempts discretion. F&F who want charts use TradingView. | Dashboard remains equity-curve-only (existing v1.0 anti-feature, reaffirmed). |
| 44 | **Cross-user leaderboard / "best paper trader this week"** | "Could be fun!" | Gamification breaks the privacy boundary AND nudges F&F toward riskier paper-trading behaviour to "win." Anti-pattern for a tool whose whole point is risk discipline. | **No leaderboards.** Everyone sees their own equity curve only. |
| 45 | **Per-user signal customisation (different ATR window for different F&F)** | "What if I want a more aggressive setup?" | Breaks "one system, one signal" + breaks the shared-compute optimisation in #14 + invalidates the 5-year backtest gate (Phase 23) per user. | Signal is shared and immutable. F&F who want custom signals are running a different product. v1.4+ "what-if" calculator is acceptable; per-user *live* signal is not. |
| 46 | **Web push / browser notifications for stop-alerts** | "Email is slow when the market is moving" | Requires service worker, push subscription management, browser permissions UX, fallback paths. Marginal value over email. | Stop-alerts already use `[!stop]`-prefixed Resend emails (Phase 20). Subject + push notification on phone gets within seconds. Defer push to v2. |
| 47 | **F&F-visible drift sentinel for admin** | "Why does Marc's drift look different from mine?" | Admin's drift is per-admin; exposing it leaks Marc's actual position. Privacy boundary. | Drift is per-user. Admin's drift visible to admin only. Existing v1.1 sentinel architecture already supports this once the user-id keying is in place. |
| 48 | **Bulk-invite CSV upload for admin** | "I want to invite 20 people at once" | F&F target is "≤dozens"; bulk invite over-invests for ≤dozens. The form-per-invite friction is also a useful brake — it forces admin to think about each invite. | Single-invite form, ship in v1.3. If admin ever hits 30+ users, bulk is a v1.4 candidate. |

---

## Feature Dependencies

```
Multi-tenant refactor (state_manager v9→v10 schema)
    ├──blocks──> Per-user paper ledger (#9)
    ├──blocks──> Per-user equity history (#10)
    ├──blocks──> Per-user alert dedup (#11)
    ├──blocks──> Per-user journal (#12)
    ├──blocks──> Per-user email (#15)
    ├──blocks──> Per-user email opt-out (#16, #29)
    └──blocks──> Per-user tour state (#23, #25)

Invite token plumbing (#2)
    └──blocks──> Admin invite form (#1)
                     └──blocks──> Invite email send (#3)
                                      └──blocks──> Invitee acceptance flow (#4)
                                                       └──blocks──> Admin user-list (#5, #28)
                                                                        └──blocks──> Disable / delete (#6)
                                                                        └──blocks──> Revoke unaccepted invite (#7)

Shared signal compute refactor (#14)
    └──blocks──> Per-user email fan-out (#15)
    └──blocks──> Per-user alert evaluation (#11)

News fetcher (#18)
    ├──feeds──> Headline dedup (#19)
    ├──feeds──> Critical-event keyword classifier (#21)
    │              └──feeds──> Email banner (#31, differentiator)
    └──forbidden_import──< signal_engine (#22 — AST-enforced)

Tour state per user (#23)
    └──depends──> Multi-tenant refactor
    └──enhanced_by──> Trace-panel highlight (#34)
    └──orthogonal──> Tooltips (#24, #26) — tooltips work standalone

Tooltips (#24, #26)
    └──depends──> No new state; pure dashboard_legacy/ render layer

Privacy boundary (#8)
    ├──enforced_by──> get_user_state(user_id) wrapper (state_manager refactor)
    ├──enforced_by──> Admin route middleware (auth/)
    └──tested_by──> New test class — TestTenantIsolation
```

### Dependency Notes

- **Multi-tenant refactor is the v1.3 critical path.** Items #9–13, #15–17, #23, #25 all block on `state.json` schema v9→v10 with per-user namespaces. Phase ordering: refactor first, features second.
- **Shared-signal-compute optimisation (#14) is a refactor, not a feature.** It saves yfinance fetches and guarantees signal-determinism-across-users. Must land before per-user fan-out (#15) or the daily run hits Yahoo N times.
- **News module isolation is AST-enforced (#22).** `signal_engine` cannot import `news_fetcher`. Existing `TestDeterminism::test_forbidden_imports_absent` already walks the AST blocklist — extend it. **Eloquent locality:** the rule lives where it's owned (the test), not in human-review discipline.
- **Privacy boundary (#8) is a cross-cutting concern.** Add a `TestTenantIsolation` class that asserts: (a) `get_user_state(user_A)` never surfaces user_B's data, (b) admin routes refuse F&F sessions, (c) F&F routes never read the admin namespace. **This is the test that makes the multi-tenant refactor safe to ship.**
- **Tour replay state lives server-side (#25), not localStorage.** Persists across devices. Single source of truth. Anti-pattern: localStorage tour state because then the user finishes on phone, opens on desktop, sees the tour again — feels broken.
- **Tooltips have zero dependencies on the multi-tenant refactor.** They're a pure render-layer addition. Could ship in a hotfix v1.2.x if multi-tenant slips. **Suggests phasing:** Tooltip phase can run in parallel with multi-tenant phase.

---

## MVP Definition (v1.3 Scope)

### Launch With (v1.3) — Must Ship

Without these, v1.3 is not a credible "open it to F&F" milestone.

- [ ] **Multi-tenant `state.json` refactor (schema v9→v10)** — every read/write goes through `get_user_state(user_id)`; admin namespace preserved. Test: `TestTenantIsolation`. **Why essential:** prerequisite for everything else.
- [ ] **Invite token plumbing + admin invite form** (#1, #2, #3) — admin can issue invites without editing JSON.
- [ ] **Invitee acceptance flow** (#4) — clicks link, sets password, enrols TOTP, lands on dashboard with their own state.
- [ ] **Admin user-list with disable + revoke** (#5, #6 disable-only, #7) — admin can manage the user pool. **Defer #6 delete to v1.4** behind feature flag.
- [ ] **Privacy boundary tests** (#8) — F&F cannot see admin or each other; admin sees user list, not F&F trade content.
- [ ] **Per-user paper ledger / equity / alerts / journal** (#9–13) — per-user state isolation is the whole point of v1.3.
- [ ] **Shared signal compute** (#14) — one yfinance fetch, one signal calc per market per day.
- [ ] **Per-user 08:00 Sydney email** (#15) — each F&F user gets their own.
- [ ] **Failed-delivery isolation** (#17) — one bouncing user doesn't break the loop.
- [ ] **Per-user email enable/disable + pause-until** (#16, #29) — F&F can mute without admin involvement.
- [ ] **News panel + headline dedup + cached fetch** (#18, #19, #20) — daily news context per market.
- [ ] **Critical-event keyword classifier** (#21) — explicit-heuristic banner.
- [ ] **AST forbidden-import for news → signal_engine** (#22) — signal stays mechanical.
- [ ] **First-run tour: 3 steps + skip + replay** (#23, #25) — activation event for new F&F.
- [ ] **Inline tooltips on every panel, mobile-safe, WAI-ARIA** (#24, #26) — F&F learn the dashboard without phoning admin.
- [ ] **Phase 28 v1.2 UAT closure** — 8 deferred items (per PROJECT.md).
- [ ] **v1.2.1 retroactive patch wrap + retroactive validation sweep** — close v1.2 debt before opening v1.3 surface area.
- [ ] **`.planning/backtests` path bug fix** — project-root-anchored.

### Add After Validation (v1.3.x)

- [ ] **News critical-event banner in email subject (#31)** — trigger: first time admin notices a critical-event was on the dashboard but missed in the email.
- [ ] **Tour Step 1 highlights trace panel (#34)** — trigger: admin observes F&F never click the trace toggles.
- [ ] **Admin user-list shows last-login + last-paper-trade (#28)** — trigger: admin asks "who's still using this?"
- [ ] **Admin "delete user" with confirm-by-typing (#6 delete branch)** — trigger: GDPR-style erasure request OR a mistakenly-invited user wants a hard wipe.
- [ ] **Pause-count surfaced in admin view (#33 partial)** — trigger: trivial cost; only deferred because not blocking v1.3 ship.

### Future Consideration (v1.4+)

- [ ] **Per-user timezone (#35)** — defer because: international F&F is hypothetical until first international invite. Current users all in AU.
- [ ] **Resend webhook open-rate tracking (#33 full)** — defer because: webhooks need extra infra (HMAC verify, replay protection); only worth it if engagement is in question.
- [ ] **Web push for stop-alerts (#46)** — defer because: anti-feature unless email-latency complaints surface.
- [ ] **Bulk invite CSV (#48)** — defer because: F&F target is ≤dozens.
- [ ] **F1 full-chain integration test harness completion** — carried from v1.0/v1.1 known-deferred.

---

## Feature Prioritization Matrix

Prioritised by user-facing value and how much of v1.3's "open to F&F" promise depends on each.

| # | Feature | User Value | Implementation Cost | Priority |
|---|---------|------------|---------------------|----------|
| Multi-tenant refactor + privacy tests | HIGH | MEDIUM | **P1** |
| Invite plumbing + acceptance flow | HIGH | MEDIUM | **P1** |
| Admin user-list + disable + revoke | HIGH | LOW | **P1** |
| Per-user state isolation (#9–13) | HIGH | MEDIUM | **P1** |
| Shared signal compute (#14) | HIGH | LOW | **P1** |
| Per-user email + opt-out + failed-delivery isolation | HIGH | MEDIUM | **P1** |
| News panel + dedup + cached fetch | HIGH | MEDIUM | **P1** |
| Critical-event keyword banner | MEDIUM | LOW | **P1** |
| AST forbidden-import for news | HIGH | LOW | **P1** |
| First-run tour (3 steps) | HIGH | MEDIUM | **P1** |
| Inline tooltips, WAI-ARIA, mobile-safe | HIGH | MEDIUM | **P1** |
| Tour replay-from-help | MEDIUM | LOW | **P1** |
| Email "pause until [date]" | MEDIUM | LOW | **P1** |
| Phase 28 v1.2 UAT closure | HIGH | LOW | **P1** (debt) |
| v1.2.1 retroactive wrap + validation sweep | MEDIUM | LOW | **P1** (debt) |
| News critical-event email subject prefix | MEDIUM | LOW | **P2** |
| Tour highlights trace panel | MEDIUM | LOW | **P2** |
| Admin user-list timestamps | MEDIUM | LOW | **P2** |
| Admin delete user (terminal) | LOW | MEDIUM | **P2** |
| Per-user starting-account wizard | MEDIUM | LOW | **P2** (folds into tour Step 2) |
| News "View on Yahoo" link + rel=noopener | LOW | LOW | **P2** |
| Tooltip "what to do" content discipline | MEDIUM | LOW | **P2** (writing, not engineering) |
| Per-user timezone | LOW | MEDIUM | **P3** |
| Resend webhook open-rate | LOW | HIGH | **P3** |
| Web push notifications | LOW | HIGH | **never** (anti) |
| Bulk invite CSV | LOW | LOW | **P3** |
| Public signup | NEGATIVE | HIGH | **never** (anti) |
| Live trading | NEGATIVE | HIGH | **never** (anti, hard constraint) |
| News-driven signal influence | NEGATIVE | MEDIUM | **never** (anti, AST-enforced) |
| Cross-user leaderboard | NEGATIVE | MEDIUM | **never** (anti) |

**Priority key:**
- **P1** — must ship in v1.3; v1.3 is incomplete without it
- **P2** — ship in v1.3 if cheap (≤1 day each); else v1.3.x
- **P3** — defer to v1.4+ unless a concrete trigger fires
- **never** — anti-feature; document so it stays out

---

## Competitor / Adjacent-Tool Feature Analysis

Limited direct comparators (this is a personal F&F tool, not a product). Adjacent reference points for the v1.3-specific patterns:

| Feature | Auth0 / WorkOS multi-tenant | Resend transactional | TradingView paid signal services | yfinance retail tools (e.g. Yahoo Finance app) | **This app v1.3** |
|---------|-----------------------------|----------------------|----------------------------------|------------------------------------------------|-------------------|
| Invite token format | Signed JWT, 7-day expiry, single-use, email-bound | n/a | n/a | n/a | **`itsdangerous` signed token, 7-day expiry, single-use, email-bound** |
| Disable vs delete | Distinct, soft-delete + audit log | n/a | n/a | n/a | **Disable in v1.3, delete deferred to v1.3.x with confirm-by-typing** |
| Per-user email opt-out | Marketing/transactional split, granular categories | One-click List-Unsubscribe header, transactional exempt | Email + push + in-app, all per-user | App-level notification toggle | **Dashboard toggle + pause-until; transactional, no CAN-SPAM footer** |
| News with importance flag | n/a | n/a | Reuters / Bloomberg severity score (paid feed) | Editorial curation | **yfinance has NO importance field — keyword-heuristic fallback w/ explicit "heuristic" banner** |
| First-run tour | Embedded SDK (Auth0 Universal Login does its own) | n/a | Long product tours, drop-off at 5+ steps | Skip-by-default, learn-by-doing | **3-step tour, server-side state, skip + replay** |
| Inline tooltips | n/a | n/a | Hover-only desktop, none on mobile | None — assumes user already knows | **Click/tap, WAI-ARIA `role=tooltip`, mobile-safe** |

The v1.3 differentiation is still being **narrow on purpose**: invite-only (not public), per-user state (but shared signal), news as context (not signal input), tour because F&F are not Marc, tooltips because the trace panel is the v1.2 differentiator and F&F won't notice it without help.

---

## Sources

- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/.planning/PROJECT.md` — v1.3 target features, hard constraints, schema state
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/.planning/MILESTONES.md` — v1.0/v1.1/v1.2 shipped scope
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/.planning/research/v1.0-archive/FEATURES.md` — baseline single-operator features (do not re-research)
- [yfinance Ticker docs](https://ranaroussi.github.io/yfinance/reference/yfinance.ticker_tickers.html) — `news` field schema (no native importance flag confirmed)
- [yfinance/issues/1956](https://github.com/ranaroussi/yfinance/issues/1956) — community discussion of `get_news()` shape
- [W3C ARIA Authoring Practices: Tooltip Pattern](https://www.w3.org/WAI/ARIA/apg/patterns/tooltip/) — `role=tooltip` + `aria-describedby` keyboard/focus rules
- [MDN: ARIA tooltip role](https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Roles/tooltip_role) — mobile/touch caveats
- [Chameleon onboarding benchmark report](https://www.chameleon.io/benchmark-report) — 3-step tours: 72% completion; 7-step: 16%
- [Guideflow product tour best practices](https://www.guideflow.com/blog/product-tour-best-practices) — 3–5 step optimal range
- [Postmark transactional email best practices](https://postmarkapp.com/guides/transactional-email-best-practices) — per-user preference UX
- [Resend: unsubscribe links on transactional](https://resend.com/docs/dashboard/emails/add-unsubscribe-to-transactional-emails) — CAN-SPAM exempt; dashboard toggle preferred
- [Auth0 multi-tenant best practices](https://auth0.com/docs/get-started/auth0-overview/create-tenants/multi-tenant-apps-best-practices) — invite + tenant-scoped tokens
- [WorkOS developer guide to SaaS multi-tenant architecture](https://workos.com/blog/developers-guide-saas-multi-tenant-architecture) — invitation workflows + auth re-check at acceptance
- [itsdangerous PyPI](https://pypi.org/project/itsdangerous/) — signed-token primitive (timestamped, tamper-evident; pairs with state-tracked single-use redemption flag)
- Global patterns (`~/.claude/CLAUDE.md`) — atomic file writes, async/await discipline, Most-Eloquent labelling, post-milestone codemoot gate

---
*Feature research for: v1.3 Multi-Tenant Friends & Family — invite-only RBAC, per-user state isolation, per-user email, news context, guide UI*
*Researched: 2026-05-10*
