# Requirements — Trading Signals v1.1

**Milestone:** v1.1 Interactive Trading Workstation
**Defined:** 2026-04-24 (Phase 16.1 AUTH-04..AUTH-07 inserted 2026-04-27; AUTH-08..AUTH-12 added 2026-04-29 per `/gsd-discuss-phase 16.1` TOTP fold-in — see `.planning/phases/16.1-phone-friendly-auth-ux-for-dashboard-access/16.1-CONTEXT.md` Areas E + F)
**Total:** 40 requirements across 8 categories (was 35 before 2026-04-29)
**Mapped to phases:** 40/40
**Coverage:** 100% (0 orphans, 0 duplicates)

---

## WEB — Hosted web layer

- [x] **WEB-01**: FastAPI app runs as a separate systemd unit (`trading-signals-web`) on the droplet and starts on boot
- [x] **WEB-02**: uvicorn serves the app on `localhost:8000`; nginx reverse-proxies from port 443 → 8000
- [ ] **WEB-03**: nginx serves HTTPS via Let's Encrypt cert for `signals.<owned-domain>.com`; auto-renew via certbot timer
- [ ] **WEB-04**: HTTP (port 80) redirects to HTTPS; HSTS header set (`Strict-Transport-Security: max-age=31536000; includeSubDomains`)
- [x] **WEB-05**: `GET /` returns the current `dashboard.html` content; refresh triggers regeneration if state changed since last render
- [x] **WEB-06**: `GET /api/state` returns the full `state.json` as `application/json` (for CLI/mobile consumers)
- [x] **WEB-07**: `GET /healthz` returns 200 with `{"status": "ok", "last_run": "..."}` for liveness checks; exempt from auth

## AUTH — Single-operator access control

- [x] **AUTH-01
**: All non-`/healthz` endpoints require a shared-secret header `X-Trading-Signals-Auth`; value stored in droplet `.env` as `WEB_AUTH_SECRET`
- [x] **AUTH-02**: Missing or wrong auth header returns 401 with a plain-text `unauthorized` body (no leaked info; no hints)
- [x] **AUTH-03
**: Auth failures log at WARN with source IP and truncated user-agent to journald for audit trail
- [ ] **AUTH-04**: Operator can authenticate to the dashboard from iOS Safari and iOS Chrome using only browser-native UI (no extension installed) — visiting `https://signals.<owned-domain>.com/` from a real iPhone yields a usable rendered dashboard, not the plain-text `unauthorized` response. Concrete mechanism (HTTP Basic Auth, login form + cookie session, Cloudflare Access, magic link) chosen during `/gsd-discuss-phase 16.1`.
- [ ] **AUTH-05**: New auth path is **additive**, not replacing — the existing `X-Trading-Signals-Auth` header still authenticates a request. Phase 14 HTMX forms in the dashboard (which carry `hx-headers='{"X-Trading-Signals-Auth": "..."}'`) keep working unchanged; `curl -H "X-Trading-Signals-Auth: <secret>" https://signals.<owned-domain>.com/` still returns 200.
- [ ] **AUTH-06**: Auth strength does not weaken — single-operator scope preserved; `WEB_AUTH_SECRET` stays in droplet `.env` only (no database, no on-disk credential store); `hmac.compare_digest` stays for constant-time comparison; no new HTTP method, header, or path opens an unauthenticated route.
- [ ] **AUTH-07**: `/healthz` stays exempt from the new auth path (per Phase 13 D-02 EXEMPT_PATHS); for any unauthenticated request that did NOT come through the new operator-UX path (e.g. raw `curl` without header), the failure response stays `401 unauthorized` plain text — the existing curl/script integration contract is preserved verbatim.
- [ ] **AUTH-08**: First-login web flow enrolls TOTP — when operator visits `/login` with valid username + password and no `auth.json.totp_secret` exists, server generates a fresh TOTP secret (`pyotp.random_base32()`), redirects to `/enroll-totp` with a 10-minute `tsi_enroll` cookie, renders QR code (issuer `Trading Signals`, account `<username>@signals.mwiriadi.me`) plus manual-entry fallback string and a 6-digit verify field; valid code finalises enrollment (auth.json: `totp_enrolled=True`) and issues `tsi_session`. Phase 16.1 16.1-CONTEXT E-03.
- [ ] **AUTH-09**: TOTP verified on every cookie-session start UNLESS a valid `tsi_trusted` cookie matches an unrevoked uuid in `auth.json.trusted_devices` — when valid creds + enrolled state, server sets a 10-minute `tsi_pending` cookie, redirects to `/verify-totp`; valid 6-digit code (via `pyotp.TOTP(secret).verify(code, valid_window=1)`) issues `tsi_session`; invalid code re-renders generic error. Phase 16.1 16.1-CONTEXT E-04.
- [ ] **AUTH-10**: Trusted-device cookie + per-device revocation — operator can opt to "trust this device for 30 days" on `/verify-totp`; server issues `tsi_trusted=<itsdangerous-signed-uuid>` (30d, Secure, HttpOnly, SameSite=Strict) and records `{uuid, label, granted_at, last_seen, revoked, revoked_at}` in `auth.json.trusted_devices`. `/devices` route renders revocable list (cookie-session only — header path returns 403); `POST /devices/revoke` and `POST /devices/revoke-all` flip the revoked flag. Revoked uuids retained for audit. Phase 16.1 16.1-CONTEXT E-05, E-06.
- [ ] **AUTH-11**: Magic-link email reset to `OPERATOR_RECOVERY_EMAIL` (default `mwiriadi@gmail.com`) — `/login` page exposes "Lost 2FA?" form requiring username + password; on match, server stores SHA256-hashed `URLSafeTimedSerializer(WEB_AUTH_SECRET, salt='magic-link')` token in `auth.json.pending_magic_links` with 1h `expires_at`, sends Resend email via existing `notifier.py` adapter. Click link → `GET /reset-totp?token=<...>` validates signature + expiry + not-consumed → marks consumed → issues one-time `tsi_session` → redirects to `/enroll-totp?reset=1` (operator chooses "keep current" or "set up new"). `/forgot-2fa` always returns the same generic "Check your email" page regardless of credential validity. Rate limited per 16.1-CONTEXT F-08. Phase 16.1 16.1-CONTEXT E-07, F-02, F-03, F-06.
- [ ] **AUTH-12**: Basic Auth path REMOVED — `Authorization: Basic <b64>` no longer accepted by `AuthMiddleware`. Browser navigation without auth always returns `302 → /login`. Cookie+TOTP becomes the sole browser-friendly path. Header path (`X-Trading-Signals-Auth`) unchanged (AUTH-05 preserved verbatim — used by curl/scripts/HTMX forms). Phase 16.1 16.1-CONTEXT E-01 (supersedes D-01, D-06, parts of D-07).

## TRADE — Interactive trade journal

- [ ] **TRADE-01**: `POST /trades/open` accepts `{instrument, direction, entry_price, contracts, executed_at?}` and appends an open position to `state.positions`
- [ ] **TRADE-02**: Request validation: `instrument ∈ {SPI200, AUDUSD}`, `direction ∈ {LONG, SHORT}`, `entry_price > 0` and finite, `contracts ≥ 1` integer; returns 400 with field-level errors on violation
- [ ] **TRADE-03**: `POST /trades/close` accepts `{instrument, exit_price, executed_at?}` and appends to `state.trade_log` with realised P&L + updates `state.account`
- [x] **TRADE-04
**: `POST /trades/modify` accepts `{instrument, new_stop?, new_contracts?}` to manually adjust a position's trailing stop or size
- [ ] **TRADE-05**: Dashboard at `GET /` includes HTMX-powered forms for open/close/modify (no full page reload; POSTs return partial HTML fragments)
- [x] **TRADE-06**: Every mutation endpoint goes through `state_manager.save_state()`; endpoints never touch `state['warnings']` directly (sole-writer invariant from v1.0 respected)

## CALC — Live stop-loss + pyramid calculator

- [ ] **CALC-01**: Dashboard per-instrument row shows: current trailing stop price, distance-to-stop in $ and %, next pyramid trigger price
- [ ] **CALC-02**: When `signal = LONG` and no position: dashboard shows "entry target: next daily close ≥ X; suggested contracts: N; initial stop: Y" derived from `sizing_engine`
- [ ] **CALC-03**: When position is open: dashboard shows "at current bar high Z, stop would rise to W" (forward-looking peak calculation)
- [ ] **CALC-04**: Pyramid section: "level N active; add 1 contract at +Y per current ATR entry anchor; new stop after add: Z"

## SENTINEL — Position-vs-signal drift warnings

- [ ] **SENTINEL-01**: When `state.positions` has an open position but today's signal for that instrument is FLAT, dashboard shows an amber "drift" banner: "You hold LONG SPI200 but today's signal is FLAT — consider closing"
- [ ] **SENTINEL-02**: When `state.positions` has a LONG but signal flipped to SHORT (or vice versa), dashboard shows a red "reversal" banner: "Signal reversed — close LONG and open SHORT"
- [ ] **SENTINEL-03**: Drift/reversal banners also surface in the daily email as a top-tier critical banner (reuses Phase 8 `_has_critical_banner` classifier via a new source `'drift'`)

## BUG — Carry-over from v1.0

- [ ] **BUG-01**: `reset_state()` sets `state['account'] = state['initial_account']` so they start equal; regression test asserts equality immediately post-reset; covers both CLI-flag and interactive-Q&A paths

## INFRA — Prerequisites + deploy automation

- [ ] **INFRA-01**: Operator-supplied domain verified on Resend (replaces `onboarding@resend.dev` test sender); `SIGNALS_EMAIL_FROM` env var reads the verified sender so code doesn't hardcode the domain
- [ ] **INFRA-02**: Droplet has a GitHub deploy key with write access; nightly cron pushes `state.json` commits to `origin/main` so git holds state history
- [ ] **INFRA-03**: `daily.yml.disabled` — GHA cron workflow removed/renamed; droplet systemd is the sole runner (no duplicate email risk)
- [x] **INFRA-04**: Deployment script (`deploy.sh` on droplet) does: `git pull && pip install -r requirements.txt && systemctl restart trading-signals trading-signals-web` — idempotent; callable from a post-push webhook or manual run

## CHORE — v1.0 tech debt (selected)

- [ ] **CHORE-01**: F1 full-chain integration test — one test exercising fetch (mocked yfinance) → signals → sizing → dashboard render → email render without mocking internal composition; catches cross-module regressions
- [ ] **CHORE-02**: ruff F401 cleanup in `notifier.py` (19 pre-existing unused-import warnings); regression test asserts zero ruff warnings at CI time
- [x] **CHORE-03**: Phase 6 HUMAN-UAT scenarios (3 pending) — now verifiable via hosted dashboard; update `06-HUMAN-UAT.md` status to `complete` after operator confirms

---

## Future Requirements (deferred to v1.2+)

- Thread-safe `_LAST_LOADED_STATE` cache (only matters with multi-process uvicorn workers; v1.1 uses `workers=1`)
- Holiday-calendar-aware staleness threshold (avoid red banner after Monday public holidays)
- Phase 7 IN-02 README badge `${{GITHUB_REPOSITORY}}` literal placeholder fix (cosmetic, forker-only)
- Phase 7 IN-03 TestWeekdayGate fake returning None (test-quality polish)
- Per-trade notes field (free-text annotations on open/close)
- Audit log UI (view of all mutations with timestamps)
- Backup/restore state.json via UI
- Mobile-responsive dashboard layout refinements
- Multi-instrument beyond SPI 200 and AUD/USD

## Out of Scope (v1.1 — validated or hard constraint)

- Live order execution — **signal-only**, hard constraint carried from v1.0
- Intraday data / tick-level signals — daily close only
- React / Vue / SPA framework — HTMX or vanilla JS only (matches project's no-build-step convention)
- Database (SQLite/Postgres/Redis) — state stays in `state.json` file; simple, portable
- Multi-user accounts / OAuth — single-operator app; shared-secret auth is sufficient
- Backtesting UI — app runs forward only
- Trade execution broker integration — out of scope; operator manually places trades

---

## Traceability

Each REQ-ID is mapped to exactly one v1.1 phase (Phases 10–16). 31/31 mapped, 0 orphans, 0 duplicates.

| REQ-ID | Description | Phase | Status |
|--------|-------------|-------|--------|
| BUG-01 | reset_state account sync | 10 | Pending |
| CHORE-02 | ruff F401 cleanup | 10 | Pending |
| INFRA-02 | Deploy key + nightly push | 10 | Pending |
| INFRA-03 | Disable GHA cron | 10 | Pending |
| WEB-01 | FastAPI systemd unit | 11 | Complete |
| WEB-02 | uvicorn + nginx reverse proxy | 11 | Complete (Phase 11 half — unit binds 127.0.0.1; nginx half lands in Phase 12) |
| WEB-07 | GET /healthz | 11 | Complete |
| INFRA-04 | deploy.sh idempotent script | 11 | Complete |
| WEB-03 | Let's Encrypt HTTPS | 12 | Pending |
| WEB-04 | HTTP→HTTPS redirect + HSTS | 12 | Pending |
| INFRA-01 | Resend domain verification | 12 | Pending |
| AUTH-01 | Shared-secret header | 13 | Complete |
| AUTH-02 | 401 on auth failure | 13 | Complete |
| AUTH-03 | Audit log | 13 | Complete |
| AUTH-04 | iOS-native operator auth UX (no extension) | 16.1 | Pending |
| AUTH-05 | New path additive — header path unchanged | 16.1 | Pending |
| AUTH-06 | Auth strength preserved (constant-time, env-only secret) | 16.1 | Pending |
| AUTH-07 | `/healthz` exempt; curl 401 contract unchanged | 16.1 | Pending |
| WEB-05 | GET / dashboard | 13 | Pending |
| WEB-06 | GET /api/state | 13 | Pending |
| TRADE-01 | POST /trades/open | 14 | Pending |
| TRADE-02 | Request validation | 14 | Pending |
| TRADE-03 | POST /trades/close | 14 | Pending |
| TRADE-04 | POST /trades/modify | 14 | Pending |
| TRADE-05 | HTMX form UI | 14 | Pending |
| TRADE-06 | save_state invariants | 14 | Pending |
| CALC-01 | Per-instrument stop + pyramid display | 15 | Pending |
| CALC-02 | Entry target for FLAT→signal | 15 | Pending |
| CALC-03 | Forward-looking peak stop | 15 | Pending |
| CALC-04 | Pyramid level + add target | 15 | Pending |
| SENTINEL-01 | Position+FLAT drift warning | 15 | Pending |
| SENTINEL-02 | Signal reversal warning | 15 | Pending |
| SENTINEL-03 | Drift banners in email | 15 | Pending |
| CHORE-01 | F1 integration test | 16 | Pending |
| CHORE-03 | Phase 6 HUMAN-UAT completion | 16 | Pending |

### Per-phase counts

| Phase | # of REQs | REQ-IDs |
|-------|-----------|---------|
| 10 — Foundation + v1.0 Cleanup | 4 | BUG-01, CHORE-02, INFRA-02, INFRA-03 |
| 11 — Web Skeleton | 4 | WEB-01, WEB-02, WEB-07, INFRA-04 |
| 12 — HTTPS + Domain | 3 | WEB-03, WEB-04, INFRA-01 |
| 13 — Auth + Read Endpoints | 5 | AUTH-01, AUTH-02, AUTH-03, WEB-05, WEB-06 |
| 14 — Trade Journal | 6 | TRADE-01..06 |
| 15 — Calculator + Sentinels | 7 | CALC-01..04, SENTINEL-01..03 |
| 16 — Hardening + UAT | 2 | CHORE-01, CHORE-03 |
| 16.1 — Phone-friendly auth UX (URGENT, inserted 2026-04-27) | 4 | AUTH-04, AUTH-05, AUTH-06, AUTH-07 |
| **Total** | **35** | (4+4+3+5+6+7+2+4 = 35 ✓) |

---

*REQ-ID namespaces: WEB (7), AUTH (7), TRADE (6), CALC (4), SENTINEL (3), BUG (1), INFRA (4), CHORE (3) = 35*

---

*Defined by /gsd-new-milestone on 2026-04-24*
*Phase mapping by /gsd-roadmapper on 2026-04-24*
