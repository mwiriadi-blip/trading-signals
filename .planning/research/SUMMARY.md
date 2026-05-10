# Project Research Summary

**Project:** trading-signals — v1.3 Multi-Tenant Friends & Family
**Domain:** Multi-tenant retrofit of an existing single-operator FastAPI + HTMX + JSON-state trading-signal app (Python 3.11, yfinance, Resend, no DB, no SPA)
**Researched:** 2026-05-10
**Confidence:** HIGH on stack/architecture/pitfalls; MEDIUM on yfinance news schema (library churn) and on the per-user state-layout decision (two credible options — see Gaps).

This SUMMARY is the **synthesis** of four parallel research files. Each detail-level claim lives in:

- [STACK.md](./STACK.md) — zero-new-runtime-deps thesis; Shepherd.js + Microtip CDN-only frontend; Resend tier math.
- [FEATURES.md](./FEATURES.md) — table-stakes vs differentiators vs anti-features for v1.3.
- [ARCHITECTURE.md](./ARCHITECTURE.md) — component-level integration shape; AST-hex preservation; daily-cycle fan-out batching.
- [PITFALLS.md](./PITFALLS.md) — 16 new pitfalls (#21–#36) on top of the v1.0-archive baseline; "Looks Done But Isn't" checklist.

---

## Executive Summary

v1.3 is a **multi-tenant retrofit**, not a green-field. The single-operator file-state app already runs in production at `https://signals.mwiriadi.me` with 1880+ tests green; v1.3 layers invite-only F&F access, per-user state isolation, per-user 08:00 Sydney email fan-out, yfinance news context, and a guided UI on top — without breaking the v1.0 hex-lite AST guard, the atomic-write contract, or the determinism contract that says signals are computed once per market per day. **Zero new runtime Python dependencies; two CDN-only frontend additions (Shepherd.js, Microtip), both single-file and SRI-pinnable.** The hard constraints (no DB, no SPA, signal-only, file-based persistence) survive untouched.

The recommended approach has three structural moves. **First**, schema migration that buckets every per-user-shaped key (positions, paper_trades, equity_history, alerts, journal, ui_prefs) under `state['users'][user_id]` while keeping shared/computed keys (signals, markets, strategy_settings) at the top level — preserving "compute once, distribute many" determinism. **Second**, FastAPI `Depends(current_user)` injected at the router level (NOT per-route) so every authenticated route receives a user identity declaratively, and a sibling `APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])` so a future admin route cannot forget the gate. **Third**, daily-cycle fan-out batches per-user alert updates into a single terminal `mutate_state` call so the W3 invariant (exactly two saves per cycle) survives, and per-user crash boundaries ensure one bad user never aborts the cycle for the rest.

The dominant risks are **cross-tenant data leak** (IDOR via bolt-on `user_id`, admin-list templates leaking trade content, crash-email leaking the wrong user's state, logs dumping per-user state) and **partial fan-out failure** (one user's broken state silently aborts the cycle for users 14..N while users 1..13 see normal output and admin doesn't notice). Both are systemic-gap risks, not bug risks — they're prevented architecturally (centralized `load_X_for_user()` loader; sub-router admin gate; `PublicUserSummary` model; per-user crash boundary with summary email to admin) rather than caught case-by-case. The privacy boundary is elevated to a **milestone-wide quality gate** via a dedicated `TestTenantIsolation` test class that every per-user phase must pass before merge.

---

## Key Findings

### Recommended Stack

**Zero new runtime deps; two CDN-only frontend additions.** Every new capability rides existing libraries (`fastapi`, `secrets`, `pathlib`, `json`, `re`, `yfinance`, `pytz`, `httpx`/`requests`) plus pure-CSS Microtip and battle-tested Shepherd.js for the tour. **Schema bumps from the actual codebase truth** — `STATE_SCHEMA_VERSION = 11` per `system_params.py` (NOT v9 as PROJECT.md and Phase 27 docs say) — to v12 with the multi-tenant restructure. **This is a plan-time verification item:** Stack research assumed v9→v10; Architecture research caught v11 in the codebase; the roadmap must use the codebase truth.

**Core technologies (deltas only):**

- **`secrets.token_urlsafe(32)`** — invite-token entropy (256 bits); store sha256 hash, never the raw token; verify via `hmac.compare_digest`.
- **`fastapi.Depends(current_user)` + `APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])`** — declarative auth/RBAC at the routing layer; one chokepoint; sub-router pattern means a future admin route cannot forget the gate.
- **`fcntl.flock`** (stdlib) — per-user advisory lock files to serialize HTMX writes against the daily fan-out.
- **`re` + hand-curated keyword list** — critical-event news classifier with word-boundary regex, multi-keyword threshold, and a dampener allowlist (`first-rate`, `second-rate`). **`yfinance.Ticker.news` has NO native importance/severity field** — confirmed across Stack/Features/Pitfalls research; keyword regex is mandatory, not optional.
- **Shepherd.js v14.5.1** (CDN, UMD, SRI-pinned) — first-run tour. Verify license at install time (was AGPL through some 2024 versions); MIT path via Driver.js if license-blocked.
- **Microtip 0.2.2** (CDN, pure CSS) — inline tooltips. Survives every HTMX swap with no JS rebind.
- **Resend HTTPS API (existing)** — same code path; per-user fan-out throttled to documented rate-limit ÷ 2.

**Mandatory stdlib-only mitigations (no new deps):**
- `secrets.token_urlsafe(32)` + sha256 storage for invite tokens
- `fcntl.flock` for per-user write serialization
- `email.utils.formataddr` for Unicode display names
- `Referrer-Policy: no-referrer` header on signup pages
- `List-Unsubscribe` + `List-Unsubscribe-Post` headers (RFC 8058) on per-user emails
- Jinja2 default `autoescape=True` on news rendering (NEVER `|safe` on third-party headlines)

### Expected Features

Detail in FEATURES.md. The v1.3 scope is **deliberately narrow** — invite-only F&F (≤dozens of users), shared signal compute, per-user state isolation. Anything that turns it into a SaaS (public signup, billing, leaderboards, real-time chat) is an explicit anti-feature.

**Must have (table stakes):**

- Multi-tenant `state.json` refactor with admin namespace preserved.
- Invite token plumbing + admin invite form + email-delivered acceptance link + TOTP enrol.
- Admin user-list with **disable** (reversible); terminal **delete** deferred to v1.3.x.
- Privacy boundary: F&F never see admin or each other; admin sees user-list metadata only. Enforced by `PublicUserSummary` Pydantic model + `RedactStateFilter` on logs.
- Per-user paper ledger / equity / alerts / journal / ui_prefs / trusted-device cookie pool.
- Shared signal compute (one yfinance fetch + one signal calc per market per day).
- Per-user 08:00 Sydney email with per-user crash boundary + admin summary email on partial failure.
- Per-user email enable/disable + pause-until.
- News panel per market (top 5 headlines, dedup'd, daily cache TTL) + critical-event keyword classifier with explicit "heuristic" banner copy.
- AST forbidden-import enforces `signal_engine` cannot import `news_*`.
- First-run 3-step tour (server-side per-user state, NOT localStorage) + skip + replay-from-help.
- Inline tooltips, mobile-safe, WAI-ARIA `role="tooltip"`.
- **Phase 28 v1.2 UAT closure** + **v1.2.1 retroactive patch wrap** + **`.planning/backtests` path bug fix**.

**Should have (differentiators — ship if cheap):**
- Critical-event email subject prefix (`[!news]`).
- Tour Step 1 explicitly highlights v1.2 trace panel.
- Admin user-list shows last-login + last-paper-trade timestamps.
- "View on Yahoo Finance" link per news headline with `rel="noopener noreferrer"`.

**Defer (v1.4+):**
- Per-user timezone, Resend webhook open-rate, web push, bulk invite CSV, admin terminal delete.

**Anti-features (never):**
Public signup, real-time chat, live trading, news-driven signal influence, billing, third-party data brokering, cross-user leaderboard, per-user signal customization, in-dashboard charting beyond equity curve.

### Architecture Approach

Detail in ARCHITECTURE.md. The hex-lite layering is preserved — pure-math modules are AST-guarded against I/O imports; v1.3 adds peers, never breaks the hex.

**Major components (v1.3 deltas):**

1. **`state_manager.py`** — gains `mutate_user_state(user_id, mutator)` thin wrapper; `load_user_view(user_id)`; `iter_user_ids()`. New migration step `_migrate_v11_to_v12`.
2. **`auth_store.py`** — gains `users[]` and `pending_invites[]` arrays alongside `trusted_devices[]`. **Co-located on purpose** — adding a user and revoking their devices on delete are one transaction.
3. **`web/dependencies.py`** (NEW) — `Depends(current_user_id)` and `Depends(require_admin)` factories.
4. **`web/middleware/auth.py`** — cookie payload extends to `{"uid": "..."}`; sets `request.state.user_id`.
5. **`web/routes/admin/`** (NEW package) — admin sub-router with the gate baked in at mount time.
6. **`per_user_fanout.py`** (NEW top-level orchestrator seam) — fan-out lives outside `daily_run.py` because `daily_run.py` is already at 530 LOC. Builds an in-memory `updates` dict and applies all per-user alert updates in a SINGLE terminal `mutate_state` call so the W3 invariant survives.
7. **`news_fetcher.py`** (NEW I/O peer) + **`news_filter.py`** (NEW pure module, joins AST hex stdlib-only set).
8. **`web/routes/tour.py`** (NEW) + **`dashboard_legacy/tour_panel.py`** + **`tooltip_data.py`** (NEW).

**File-size pre-split (Phase-0 work, NOT optional polish):** Architecture research found these files **already exceed the v1.2 D-09 500-LOC cap before v1.3 additions:** `web/routes/trades.py` (746), `web/routes/dashboard.py` (644), `web/routes/totp.py` (614), `web/routes/login.py` (608), `web/routes/paper_trades.py` (493). v1.3 must split these BEFORE adding `user_id` scoping — splitting an over-cap file while changing its semantics simultaneously courts merge-conflict pain. This is a real first phase, not surprise debt.

### State Layout — Decision Recommendation

The two parallel researchers proposed credibly different shapes:

| Option | Shape | Concurrency | Migration | Researcher |
|--------|-------|-------------|-----------|------------|
| **A. Sharded directory** | `state/users/{uid}.json` + registry + `state/signals/{market}.json` | Per-user lock natural | Multiple new files | Stack |
| **B. Single state.json with `users{}` map** | Shared keys top-level; per-user under `state['users'][uid]`; `auth.json` co-locates `users[]` + `pending_invites[]` | Existing `mutate_state` chokepoint serializes; needs added per-user flock | Single in-place migration step | Architecture |

> **Most eloquent: Option B (single-file `users{}` map).** It preserves the existing `mutate_state(mutator)` chokepoint verbatim — no second atomic-write contract to maintain, no per-user backup story to evolve, no directory-scan in the daily fan-out. Locality wins: the rule "we save once per cycle" stays in `state_manager`. The `mutate_user_state(user_id, mutator)` wrapper is six lines; it composes naturally with `mutate_state` rather than splitting the contract. **However**, Pitfalls research flags a real logical race even with atomic `os.replace`: the daily admin-fan-out and a live HTMX write from a wakeful F&F user at 08:00:03 can clobber each other's logical updates (Pitfall 25). Option B mitigates with `flock` on `state/users/{uid}.lock` held across the read-modify-write window. Option A naturally has per-user locks because each user is a separate file.

**Recommendation to roadmapper:** start with Option B (single-file `users{}` map + per-user flock). Reasons: (a) one atomic-write contract, (b) one backup story, (c) Architecture research read the existing code end-to-end, (d) file size at 20 users is ~1MB with sub-millisecond parse. **Plan-phase verification:** confirm the flock-across-read-modify-write pattern works under existing `mutate_state` semantics before locking the choice; if friction-laden, fall back to Option A. Either way, the per-user flock is non-negotiable (Pitfall 25).

### Critical Pitfalls

Top five from PITFALLS.md (full list is 16 pitfalls #21–#36):

1. **IDOR via bolt-on `user_id`** (Pitfall 21) — every entity-ID route is privilege escalation if lookup uses raw ID. **Avoid:** centralized `load_X_for_user()` loader; per-route `test_<route>_returns_404_for_other_users_entity`.
2. **Admin-vs-user boundary missing on one new route** (Pitfall 22) — copy-pasted `Depends(require_admin)` lines mean someone forgets one. **Avoid:** `APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])` sub-router; startup invariant test walks `app.routes`.
3. **Schema migration crashes mid-flight** (Pitfall 27) — atomic-write covers the file but not the migration logic. **Avoid:** build new state in fresh dict, validate via Pydantic, save once with new schema_version stamped. Auto-backup before migrate. Round-trip test on 5 fixtures mandatory.
4. **Per-user fan-out partial failure** (Pitfall 24) — user #14's broken state aborts users #14..N silently. **Avoid:** per-user `try/except` crash boundary; admin gets end-of-cycle summary email; `/healthz/last-cycle` endpoint.
5. **Crash-email + `_LAST_LOADED_STATE` cache leaks the wrong user's state** (Pitfall 26) — v1.0 D-08 explicitly flagged "revisit if parallel runs appear (v2)"; multi-tenant fan-out IS that revisit. **Avoid:** drop the cache OR scope via `contextvars.ContextVar`; crash email body is `PublicUserSummary` only — never trade content.

**Honourable mentions:** Pitfall 25 (concurrent write race — solved by per-user flock), Pitfall 28 (invite token weaknesses), Pitfall 29 (yfinance schema drift / XSS / SSRF), Pitfall 31 (Resend per-user burst → 429), Pitfall 34 (state.json git push-back → F&F trade content in git history forever).

---

## Implications for Roadmap

The three downstream researchers (Features, Architecture, Pitfalls) **independently converged** on essentially the same phase order. The roadmapper should treat this as the converged recommendation.

### Suggested Phase Sequence

| # | Phase | Rationale | Pitfalls Addressed |
|---|-------|-----------|--------------------|
| 28 | **v1.2 UAT closure** | 8 deferred items (Phase 17/23/26). No new surface area. | — (debt) |
| 28.x | **v1.2.1 retroactive patch wrap** | 5 ad-hoc commits formalised + retroactive `VALIDATION.md`/`SECURITY.md` for v1.2 Phases 17/19/20/22/23/24/25/26 + `.planning/backtests` path fix. | — (debt) |
| 29 | **File-size pre-split (Phase 0 of v1.3)** | Behaviour-preserving splits of `trades.py`/`login.py`/`totp.py`/`dashboard.py` BEFORE multi-tenant changes. | Sets up 21, 22 (cleaner diff for `user_id` injection) |
| 30 | **Schema migration v11 → v12 + admin namespace + atomic-build-then-save + backup** | Foundational. Round-trip test on 5 fixtures. Auto-backup. `state/users/` gitignore + CI gate + rclone-to-B2 backup. | **27** (mid-flight crash), **34** (git push-back) |
| 31 | **User registry + invite-token storage in `auth.json`** | `secrets.token_urlsafe(32)` + sha256 + `hmac.compare_digest` + flock on consume + 7-day expiry. Storage layer only. | **28** (token vulnerabilities) |
| 32 | **Cookie + `Depends(current_user)` + sub-router admin gate** | Cookie payload `{"uid": "..."}`; sub-router pattern locked Day 1; CSRF refresh shim (HTMX `HX-Refresh: true` on stale 403). Admin still only user — observable behaviour identical. | **22** (admin gate), **35** (auth-after-body), **36** (CSRF stale) |
| 33 | **Per-route user_id scoping + privacy boundary tests + flock helper** | Centralized `load_X_for_user()`; `PublicUserSummary` model; `RedactStateFilter` on logs; **`TestTenantIsolation` quality gate (milestone-wide)**; per-user flock; pyramid/exit semantics shift to fan-out. | **21** (IDOR), **23** (privacy regression), **25** (write race), **26** (crash-email leak) |
| 34 | **Per-user email fan-out + admin invite/disable/revoke routes + invite-acceptance flow** | `per_user_fanout.py`. Per-user crash boundary. Admin summary email. `asyncio.Semaphore(2)` Resend throttle. `List-Unsubscribe` (RFC 8058). No session token in email body. `formataddr` for Unicode names. | **24** (partial fan-out), **31** (Resend / unsubscribe / forwarding) |
| 35 | **News integration (parallel-safe — could ship anywhere after Phase 30)** | Adapter normalises both pre-0.2.55 and post-0.2.55 yfinance schemas. Single fetch per market per cycle, shared cache. Word-boundary regex with multi-keyword threshold and dampener allowlist. 30-headline labelled fixture: precision ≥0.7, recall ≥0.9. Per-user dismiss state. `autoescape=True`; XSS test. **No native importance hint exists** — keyword regex is the entire signal. AST blocklist extended. | **29** (schema drift / XSS / SSRF), **30** (false +/-, dismiss) |
| 36 | **Guide UI (Tour + Tooltips — comes last because it depends on stable UI)** | Shepherd.js v14.5.1 (license-verified) + Microtip 0.2.2, both CDN/SRI. Tour DOM portaled at `<body>` level (NOT inside HTMX swap target). Tour state per-user in `state.json` (NOT localStorage). Stable anchors. `htmx:afterSwap` re-validation. `role="dialog"` + Esc-closes + focus-trap. Tooltips inherit `tabindex`, ≥16px font, unique `aria-describedby` IDs. axe-core sweep zero new violations vs Phase 25 baseline. | **32** (HTMX swap kills tour), **33** (tooltip a11y regression of Phase 25) |
| 37 | **Milestone close audit (Codemoot + Nyquist gate)** | Per CLAUDE.md mandatory milestone gate. Backfill VALIDATION/SECURITY for any v1.3 phase missing one. Verify findings against current code (codemoot ~40-50% false-positive rate). | All — final sweep |

### Phase Ordering Rationale

The convergence is not coincidence — it falls out of dependency structure:

- **Schema before routes** — routes need `state['users'][uid]` to exist.
- **Auth-store users before middleware** — middleware looks up role; lookup needs the store.
- **Middleware before RBAC routes** — admin gate is a `Depends` chained on `current_user`.
- **RBAC + scoping before fan-out** — fan-out reads `state['users']`.
- **News and Guide UI last** — additive, not tangled with auth/state changes.
- **File-size pre-split BEFORE schema** — splits are behaviour-preserving and shrink the merge surface for every later phase.
- **v1.2 closure BEFORE v1.3 substance** — PROJECT.md scopes Phase 28 + v1.2.1 into v1.3.

### Quality Gates (lift "Looks Done But Isn't" into per-phase success criteria)

PITFALLS.md provides a 24-item checklist. Selected highlights:

- **Schema phase:** migration round-trip test (5 fixtures, lossless v9→v12→v9'); backup file present after migrate; `git ls-files | grep '^state/users/'` returns nothing.
- **RBAC phase:** startup invariant test walks `app.routes`, every `/admin/*` path has `require_admin` in dependency chain; `invites.json` contains only sha256 hashes; two parallel `consume(token)` → exactly one wins.
- **Per-user scoping phase:** `TestTenantIsolation` class green; every entity-ID route has `test_<route>_returns_404_for_other_users_entity`; admin user-list HTML rendered with fixture user holding 5 trades contains zero `(entry_price|n_contracts|"direction":\s*"(LONG|SHORT)")` matches; crash-email body with same fixture also zero matches.
- **Per-user email phase:** fan-out with 50 mocked users completes within 30s, throttled, no 429s; `List-Unsubscribe` header present; no session token URL in body; `Müller` round-trip via RFC 2047.
- **News phase:** yfinance pinned; both-schema fixtures green; `<script>alert(1)</script>` headline renders as `&lt;script&gt;`; classifier precision ≥0.7, recall ≥0.9; per-user dismiss isolated.
- **Guide UI phase:** tour overlay survives `htmx:afterSwap` of `#main`; "Restart tour" works on second click; keyboard-only flow (Tab/Esc); axe-core zero new violations; tooltip count adds zero new tab stops on inactive market panels.
- **Cross-cutting:** `RedactStateFilter` installed at startup; per-user state mtime advances for all users in cycle; `git status` after fan-out is clean for `state/users/`.

### Research Flags

| Phase | Need deeper research? | Reason |
|-------|----------------------|--------|
| 28, 28.x, 29 | NO | Mechanical / behaviour-preserving / debt closure. |
| 30 (schema migration) | **YES** | Confirm codebase is at `STATE_SCHEMA_VERSION = 11` (Architecture's finding) vs v9 (PROJECT.md assumption). Re-read `system_params.py` migration chain. |
| 31 (registry + invites) | NO | stdlib-stable patterns; Pitfalls research locked the shape. |
| 32 (cookie + Depends + admin) | NO | FastAPI patterns canonical. |
| 33 (per-user scoping + flock) | **YES** | Confirm `flock(LOCK_EX)` interacts cleanly with existing `mutate_state` semantics under simulated 50-thread stress. Fall back to sharded directory if friction-laden. |
| 34 (per-user email fan-out) | **YES (light)** | Re-verify Resend's current rate limits at plan time (threshold has changed historically). Confirm batch-send API availability. |
| 35 (news integration) | **YES** | yfinance schema drift across 0.2.40 → 0.2.55 → 1.x is real; capture fresh fixtures from pinned version at plan time. |
| 36 (guide UI) | NO | Patterns documented. License re-verification of Shepherd at install is a one-line check. |
| 37 (milestone close) | NO | Process step. |

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Zero new runtime deps; CDN libraries verified active 2025/2026; Resend tier math verified; one license-verification action item. |
| Features | HIGH | Constrained by existing v1.0 hard rules; anti-feature list well-grounded. |
| Architecture | HIGH | Read every existing seam at file level (state_manager, auth_store, web/middleware, daily_run, web/routes); ONE plan-time verification (state schema is v11 not v9). |
| Pitfalls | HIGH | 13/16 HIGH-confidence (project-local + universal LEARNINGS + v1.0-archive validated in production). 3 MEDIUM (yfinance schema, Resend rate limit, tour/HTMX) — prevention via plan-time re-verification. |

**Overall confidence: HIGH** for the multi-tenant scoping and the privacy/concurrency/migration patterns; **MEDIUM** for two scoped items: (a) per-user state-layout choice, (b) external-API drift. Both MEDIUMs have prevention via plan-time re-verification, not architectural change.

### Gaps to Address (Plan-Time Verification Items)

1. **Schema version mismatch.** PROJECT.md says v9; codebase is at `STATE_SCHEMA_VERSION = 11`. Roadmap should use codebase truth (v11→v12). Re-read `system_params.py` and `state_manager.py` migration chain in plan-phase before locking the migration phase.
2. **State layout final choice.** Single-file `users{}` map (Architecture, more eloquent) vs sharded directory (Stack, naturally per-user lock). Recommend Option B with per-user flock; verify flock interaction in plan-phase.
3. **Resend rate-limit current threshold.** Re-verify at plan time before locking throttle constant.
4. **yfinance news schema fresh fixtures.** Capture at plan time from pinned version.
5. **Shepherd.js license at install.** Verify before merge of Phase 36; switch to Driver.js (MIT) if AGPL-blocked.
6. **Pre-existing 500-LOC violations.** `trades.py` (746), `login.py` (608), `totp.py` (614), `dashboard.py` route (644), `paper_trades.py` (493). Phase-0 split work in v1.3 — NOT optional, NOT surprise debt.

---

## Sources

### Primary research files (HIGH confidence — internal)
- `.planning/research/STACK.md`, `FEATURES.md`, `ARCHITECTURE.md`, `PITFALLS.md`
- `.planning/research/v1.0-archive/` (still in force; v1.3 is incremental)

### Project-internal (HIGH confidence)
- `.planning/PROJECT.md` (v1.3 scope, hard constraints — see Gap #1)
- `.planning/MILESTONES.md` (Phase 27 D-09 cap, deploy-key history)
- Codebase: `state_manager.py`, `auth_store.py`, `web/middleware/auth.py`, `web/routes/*`, `daily_run.py`, `daily_loop.py`, `tests/test_signal_engine.py::TestDeterminism`, `system_params.py`
- `~/.claude/LEARNINGS.md` G-20 (tenant filter), G-23 (header tenant trust), G-36 (defensive-read partial migrations), G-46 (schema-version assertions stale), G-51 (FastAPI route ordering), G-53 (regex + allowlist), CSRF-after-session-regen, SSRF protection

### External (MIXED confidence)
- yfinance Ticker.news API + issue #1956 (HIGH — importance hint absent)
- Shepherd.js npm + jsDelivr (HIGH)
- Microtip GitHub (HIGH)
- Resend account quotas (HIGH — verify at plan time, threshold has changed)
- FastAPI dependency-injection RBAC (MEDIUM — vendor blog, cross-checked)
- W3C ARIA Tooltip + Dialog Patterns (HIGH)
- Chameleon onboarding benchmark (MEDIUM) — 3-step tours: 72% completion vs 16% at 7 steps
- RFC 8058 — One-Click Unsubscribe (HIGH)
- OWASP CWE-639 — Authorization Bypass Through User-Controlled Key (HIGH)

---

*Research synthesis completed: 2026-05-10*
*Ready for roadmap: yes*
*Plan-time verification items: schema version (v11 not v9), state-layout flock interaction, Resend rate limit, yfinance news fixtures, Shepherd license, pre-existing 500-LOC violations as Phase-0 work.*
