---
created: 2026-04-27T06:11:00+08:00
title: Phone-friendly auth UX for dashboard access
area: auth
priority: blocker
files:
  - web/middleware/auth.py:42
  - web/routes/dashboard.py
  - nginx/signals.conf
  - .planning/phases/13-auth-read-endpoints/
related:
  - .planning/phases/16-hardening-uat-completion/16-HUMAN-UAT.md (UAT-16-A)
---

## Problem

Visiting `https://signals.mwiriadi.me/` from a real iPhone returns the literal plain-text response `unauthorized` on a black background. The operator has no path to actually use the dashboard from their primary device.

This is the auth gate working **as designed** per Phase 13 D-04 (`AuthMiddleware` returns `401 unauthorized` plain text when the `X-Trading-Signals-Auth` header is missing or wrong) — but the design assumed the operator could inject headers via tooling. iOS Safari and iOS Chrome do not support extensions like ModHeader, and there is no other path for an iPhone user to attach a custom HTTP header to a navigation request.

Confirmed today (2026-04-27 UAT-16-A session):
- iPhone Safari → `signals.mwiriadi.me` → `unauthorized` plain text (no styling, no login form, no escape hatch)
- Desktop Chrome with mobile-emulation viewport + ModHeader works fine (this is what the operator actually used to verify the rendering)
- `curl -H "X-Trading-Signals-Auth: <secret>" https://signals.mwiriadi.me/` works fine (200 OK + 19,831 bytes of dashboard HTML)
- The gate is doing its job; the gap is the operator UX

The operator marked this a **blocker**. Strictly, milestone v1.1 close does not require phone access (Phase 16 verification chain works via curl-equivalence and the Mac-dev-proxy + production-curl evidence we shipped today). But:
- The project name "Trading Signals — Interactive Trading Workstation" implies operator-anywhere access
- Phone is the operator's primary device for checking signals during the trading day
- Currently the only way to read the dashboard from a phone is to SSH into the droplet and curl — defeating the point of having a hosted dashboard

So: **does not block milestone v1.1 archive** (the auth contract is verified; the rendering is verified via equivalence). **Does block daily operator usability of v1.1**, which is arguably worse.

Recommendation: bump this into v1.2 as a high-priority phase, OR insert a v1.1.1 patch milestone scoped specifically to fix this.

## Solution

TBD — four candidate paths, listed cheapest → heaviest:

1. **HTTP Basic Auth as a parallel allowed path.** Add a check: if `X-Trading-Signals-Auth` header missing, also accept `Authorization: Basic <base64(operator:secret)>`. iOS Safari has a built-in basic-auth dialog that prompts the user on first visit. Pro: trivial server-side change (one extra check in `AuthMiddleware.dispatch`); no new UX infra; works on any browser natively. Con: basic-auth credentials cached in browser keychain — fine for single-operator, but a logout flow would need a workaround. Browsers also display the username in the address bar (`https://operator@signals…`) which is mildly ugly.

2. **Login form + server-side session cookie.** Add a `GET /login` route that renders a small HTML form (single password field) and `POST /login` that sets a `Secure; HttpOnly; SameSite=Strict` session cookie containing a signed/HMAC'd token. Modify `AuthMiddleware` to also accept the cookie. Pro: cleanest UX — user visits the URL, sees a login form, types secret, gets in, session lasts X hours. Con: more code (cookie signing, session storage, expiry, CSRF protection if any state-mutating routes don't already have it).

3. **Cloudflare Access (Zero Trust).** Re-orange-cloud the DNS, enable Cloudflare Access on the hostname, configure access policy (Google OAuth restricted to your operator email). Cloudflare handles auth at the edge before the request reaches the droplet. Server-side change: trust the `Cf-Access-Authenticated-User-Email` header from Cloudflare instead of (or in addition to) the shared secret. Pro: industrial-strength SSO, MFA, audit log, no passwords. Con: ties auth to Cloudflare; re-orange-clouding the proxy means re-engineering the LE renewal path (would need DNS-01 challenge with `--dns-cloudflare` plugin). More moving parts.

4. **Magic link via Resend.** Operator hits `signals.mwiriadi.me/login` → enters their email → server emails a one-time signed token URL → clicking it sets a session cookie. Pro: passwordless, infrastructure already in place (Resend is wired up for the daily emails). Con: heaviest UX flow, slowest first-visit, requires Resend domain verification to be done.

**My lean: Option 1 (Basic Auth) for v1.1.1 patch as the unblock-now move. It's a 20-line change in `web/middleware/auth.py` plus a test, ships in a day, gives the operator an iPhone-usable dashboard immediately. Then Option 2 (login form + cookie) lands in v1.2 as the proper UX.**

Worth checking before any of this: does the existing dashboard JavaScript include a `hx-headers` HTMX pattern that would NOT carry over to cookie auth? Phase 14 wired up trade-mutation forms via HTMX with `hx-headers='{"X-Trading-Signals-Auth": "..."}'`. If we move to cookies, those forms either need to keep working with the header (parallel auth paths) or be rewritten to rely on the cookie. Cleanest design: parallel paths, no breaking changes for HTMX forms.

## Constraints to preserve

- **Auth strength must not weaken.** Whatever the new path is, operator-only access stays operator-only. Single shared secret is the floor; new paths are additions, not replacements.
- **`/healthz` stays exempt** (per Phase 13 D-02 EXEMPT_PATHS).
- **`hmac.compare_digest`** for the secret comparison stays (per D-03).
- **Failure response stays `401 unauthorized` plain text** for any unauthenticated request that didn't go through a login form — keeps the existing curl/script integration contract intact.
- **No password storage.** If we add basic-auth or cookie sessions, the secret stays in `.env` only; nothing in a database, nothing on disk.
