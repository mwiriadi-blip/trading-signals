# Phase 12: HTTPS + Domain Wiring — Context

**Gathered:** 2026-04-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Put `signals.<owned-domain>.com` on HTTPS via nginx reverse-proxy and Let's Encrypt, with HTTP→HTTPS redirect and HSTS, and switch Resend email sending to read the operator-owned domain from `SIGNALS_EMAIL_FROM` env var instead of a hardcoded sender.

**After this phase:** the site is publicly reachable over HTTPS but still open (no auth — that lands in Phase 13). `/healthz` is rate-limited at the nginx layer. Daily emails send from the env-configured sender or fail cleanly with a warning.

**Phase 12 requirements:** WEB-03 (nginx + Let's Encrypt + certbot.timer), WEB-04 (HTTP→HTTPS 301 + HSTS `max-age=31536000; includeSubDomains`), INFRA-01 (Resend domain verification + `SIGNALS_EMAIL_FROM` env var).

**Operator prerequisites:** domain purchased (operator task during SETUP-HTTPS.md execution); A-record pointing at droplet IP; Resend domain verification (SPF/DKIM/DMARC) already completed — operator confirmed `signals@carbonbookkeeping.com.au` is verified, so INFRA-01 is a pure code refactor from the code side.

</domain>

<decisions>
## Implementation Decisions

### Area 1 — Domain + DNS (pre-planning posture)

- **D-01: Use `<owned-domain>` as a literal placeholder in all committed config.** No domain is purchased yet; operator acquires + configures A-record + certbot run during SETUP-HTTPS.md execution. Nginx config uses `<owned-domain>` literally; plan tests assert the placeholder is present; SETUP-HTTPS.md tells the operator to `sed` it in post-clone.

- **D-02: Subdomain pattern: `signals.<owned-domain>.com` (per ROADMAP.md SC-1..4).** Single server block in nginx; single cert. Apex and other subdomains are out of scope for v1.1.

- **D-03: No Cloudflare / CDN proxy.** Direct DNS A-record to droplet IP. Keeps HTTP-01 challenge viable and simplifies nginx config (no `X-Forwarded-For` trust chain needed).

- **D-04: Resend domain verification is NOT a Phase 12 task — it's a prerequisite already done.** Operator has `signals@carbonbookkeeping.com.au` verified on Resend (SPF + DKIM records live). Phase 12's INFRA-01 work is purely a code refactor: move the already-working FROM address out of a hardcoded constant and into an env var. SETUP-HTTPS.md notes Resend verification as "confirm (should already be done)" not "do this now".

### Area 2 — nginx + certbot install

- **D-05: Commit nginx config to repo at `nginx/signals.conf`.** Mirrors the Phase 11 pattern (systemd/trading-signals-web.service committed to repo with `User=trader` hardcoded). File contains `<owned-domain>` placeholder; operator symlinks into `/etc/nginx/sites-enabled/` after substituting. Config drift visible in PRs; rollback via git revert; a pytest config-parser test can validate syntax.

- **D-06: HTTP-01 challenge via `certbot --nginx` plugin from apt.** Standard on Ubuntu 22.04+ droplets. Install: `apt install certbot python3-certbot-nginx`. Issuance: `certbot --nginx -d signals.<owned-domain>.com`. Certbot auto-injects cert paths + HTTP→HTTPS redirect into the nginx config. Operator re-runs if cert paths drift.

- **D-07: Auto-renewal via `certbot.timer` (Ubuntu default).** The apt package installs `/lib/systemd/system/certbot.timer` + `certbot.service` that run `certbot renew` twice daily. No custom cron. Renewal hook: `/etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh` with `systemctl reload nginx` — created during SETUP-HTTPS.md; no repo code change needed.

- **D-08: nginx config structure.** Single `server` block listening on 443 (ssl), proxying `/` to `http://127.0.0.1:8000` (FastAPI), preserving `Host`, `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto`. Separate `server` block listening on 80 with `return 301 https://$host$request_uri;` for the HTTP→HTTPS redirect. HSTS header set on the 443 block. See D-09 for security header details.

- **D-09: Renewal port-80 listener stays up.** The port-80 redirect server block keeps listening on port 80 so certbot's HTTP-01 renewal validation works. Cert renewal does NOT require nginx downtime. Certbot's `--nginx` plugin handles the ACME challenge response at `/.well-known/acme-challenge/*` via a temporary location block it auto-inserts during renewal.

### Area 3 — Security headers + rate limiting

- **D-10: Rate-limit `/healthz` at the nginx layer now (pre-auth).** Add `limit_req_zone $binary_remote_addr zone=healthz:10m rate=10r/m;` at http scope; apply `limit_req zone=healthz burst=10 nodelay;` to the `location = /healthz` block. Prevents probe amplification while keeping status-page integrations viable. Phase 13 auth (AUTH-01 shared-secret header) replaces this with proper access control; the rate-limit stays as defense-in-depth.

- **D-11: Security headers set at nginx (applied to 443 block):**
  - `Strict-Transport-Security: max-age=31536000; includeSubDomains` (WEB-04 spec — exact value, no `preload`)
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `Referrer-Policy: strict-origin-when-cross-origin`
  
  CSP is explicitly **deferred** — premature for /healthz (JSON only); revisit in Phase 13 when HTML dashboard lands (WEB-05).

- **D-12: No HSTS preload submission.** HSTS header is the exact value in WEB-04 — does NOT include the `preload` directive, not submitted to hstspreload.org. Keeps the "remove HSTS if needed" escape hatch open (max-age expires naturally after 1 year). Revisit when every subdomain of `<owned-domain>` is committed to HTTPS permanently.

- **D-13: No IP allowlist.** `/healthz` is rate-limited but publicly readable. Status-page services (UptimeRobot, etc.) can hit it. Phase 13 AUTH-01 adds the shared-secret header; until then, rate limit is sufficient for v1.1's threat surface.

### Area 4 — SIGNALS_EMAIL_FROM failure mode

- **D-14: Missing `SIGNALS_EMAIL_FROM` → log ERROR + append_warning + skip email + continue run.** Preserves the never-crash contract from Phase 6/8. `_send_email_never_crash` checks the env var **before** calling `_post_to_resend`. Behavior on missing/empty:
  1. `logger.error('[Email] SIGNALS_EMAIL_FROM not set — email skipped')`
  2. `state_manager.append_warning(state, source='notifier', message='SIGNALS_EMAIL_FROM env var missing — daily email skipped')`
  3. Return `SendStatus(ok=False, reason='missing_sender', attempts=0)` — does NOT call Resend, does NOT fall back to `onboarding@resend.dev`.
  4. Run continues normally; next email surfaces the warning via Phase 8 stale/warnings banner.
  
  This matches the existing `RESEND_API_KEY` missing handling pattern (notifier.py:9, 34) — log + degrade + continue.

- **D-15: Env var read happens per-send, inside `_post_to_resend` (or its caller).** `os.environ.get('SIGNALS_EMAIL_FROM')` called inside the helper that composes the Resend payload — NOT at module import. Testability: `monkeypatch.setenv(...)` works per-test without `importlib.reload(notifier)`. Matches how `RESEND_API_KEY` is read. Exact read location is Claude's discretion (planner picks between `_send_email_never_crash`, `_build_resend_payload`, or `_post_to_resend` entry) as long as a single read point is used.

- **D-16: Remove `_EMAIL_FROM = 'signals@carbonbookkeeping.com.au'` at notifier.py:99.** The hardcoded constant goes away entirely. `SIGNALS_EMAIL_FROM` env var is the ONLY source. Matches SC-4 intent: "never silently falls back". Tests use `monkeypatch.setenv('SIGNALS_EMAIL_FROM', 'signals@carbonbookkeeping.com.au')` in fixtures so golden-email tests stay stable.

- **D-17: Regression test `tests/test_notifier.py::TestEmailFromEnvVar` — 3 tests:**
  - `test_from_addr_reads_env_var` — setenv `SIGNALS_EMAIL_FROM=test@example.com`, spy on `_post_to_resend`, call `_send_email_never_crash(...)`, assert the Resend payload's `from` field equals `'test@example.com'` (per SC-4).
  - `test_missing_env_var_skips_email_with_warning` — delenv `SIGNALS_EMAIL_FROM`, call `_send_email_never_crash(...)`, assert `_post_to_resend` was NOT called, `'[Email] SIGNALS_EMAIL_FROM not set'` in caplog.text, `append_warning` received `source='notifier'` + `missing_sender`-like message (per D-14).
  - `test_empty_env_var_treated_as_missing` — setenv `SIGNALS_EMAIL_FROM=''` (empty string), assert same behavior as missing (same skip + log + warning path).

### Area 5 — Integration with existing Phase 11 infra

- **D-18: Add `SIGNALS_EMAIL_FROM` to the droplet `.env` file.** Phase 11 systemd units load `EnvironmentFile=-/etc/trading-signals/.env` (optional prefix `-` per D-12 Phase 11). Operator adds `SIGNALS_EMAIL_FROM=signals@carbonbookkeeping.com.au` (their verified sender) to that file. **No systemd unit file changes needed.**

- **D-19: Update Phase 11 golden-email tests to monkeypatch `SIGNALS_EMAIL_FROM`.** `tests/test_notifier.py::TestGoldenEmail` currently depends on the hardcoded `_EMAIL_FROM` being present. Phase 12 plan MUST update `TestGoldenEmail` (and any sibling tests that render a Resend payload) to `monkeypatch.setenv('SIGNALS_EMAIL_FROM', 'signals@carbonbookkeeping.com.au')` in a fixture (e.g., `@pytest.fixture(autouse=True)` on the class). Otherwise tests fail with the new "env var missing" path. These test updates land in the same commit as the notifier code change.

- **D-20: Update `deploy.sh` with an nginx config-test + reload hook** gated on nginx being installed. After the existing `sudo -n systemctl restart trading-signals` + `trading-signals-web` calls, add:
  ```bash
  if [ -f nginx/signals.conf ] && command -v nginx &>/dev/null; then
    sudo -n nginx -t && sudo -n systemctl reload nginx
  fi
  ```
  Gates on `test -f nginx/signals.conf && command -v nginx` so pre-Phase-12 droplets (no nginx installed yet) don't fail. Requires a sudoers entry for `trader` to run `/usr/sbin/nginx -t` and `/bin/systemctl reload nginx` — documented in SETUP-HTTPS.md. Test: `tests/test_deploy_sh.py` adds an ordering check for the reload step + a negative assertion that the reload is skipped when `nginx/signals.conf` is absent.

- **D-21: New operator runbook `.planning/phases/12-https-domain-wiring/SETUP-HTTPS.md`.** Analog to SETUP-DEPLOY-KEY.md (Phase 10) and SETUP-DROPLET.md (Phase 11). Sections:
  1. Prerequisites — domain purchased, A-record created, Resend domain verified (confirm, don't re-do)
  2. Install nginx + certbot (`apt install nginx certbot python3-certbot-nginx`)
  3. Copy `nginx/signals.conf` to `/etc/nginx/sites-available/`, substitute `<owned-domain>` with actual domain, symlink to `sites-enabled/`, `nginx -t` + `systemctl reload nginx`
  4. Run certbot: `sudo certbot --nginx -d signals.<owned-domain>.com` + interactive agreement steps
  5. Verify: `curl -sI https://signals.<owned-domain>.com/healthz` returns 200 with Let's Encrypt cert chain; `curl -sI http://signals.<owned-domain>.com/healthz` returns 301; HSTS header present
  6. Confirm `certbot.timer` is active: `systemctl list-timers | grep certbot` + dry-run: `sudo certbot renew --dry-run`
  7. Add `SIGNALS_EMAIL_FROM=signals@carbonbookkeeping.com.au` to `/etc/trading-signals/.env`; restart `trading-signals.service`; operator runs `python main.py --force-email` to confirm the next send uses the env-configured FROM address
  8. Extend sudoers entry to include `/usr/sbin/nginx -t` + `/bin/systemctl reload nginx` (so `deploy.sh` D-20 hook works)
  9. Troubleshooting: common issues (DNS propagation, rate limits at Let's Encrypt, port 80/443 firewall, nginx syntax errors, Resend quota)
  10. Rollback: how to disable the nginx config and revert to localhost-only serving (Phase 11 posture)

### Claude's Discretion

- **Exact nginx config body** — D-08 sketches it at a high level; planner writes the final `server { ... }` blocks with appropriate `ssl_protocols TLSv1.2 TLSv1.3` + `ssl_prefer_server_ciphers off` + modern Mozilla SSL config
- **sudoers entry exact form** — SETUP-HTTPS.md extends the Phase 11 sudoers pattern; planner decides whether to use a single sudoers file `/etc/sudoers.d/trading-signals` with all units/commands or split. Just has to scope to specific command paths (no NOPASSWD: ALL)
- **Env var read location inside notifier.py** — D-15 locks "per-send, not import time" but lets the planner pick which helper (`_send_email_never_crash` vs `_build_resend_payload` vs `_post_to_resend`) does the read
- **Renewal hook script path** — planner or SETUP-HTTPS.md decides between `/etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh` (standard) vs a one-liner in the certbot config

### Folded Todos

None — no pending todos cross-reference Phase 12 scope.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents (researcher, planner, executor) MUST read these before implementing.**

### Phase spec + scope
- `.planning/ROADMAP.md` §Phase 12 — goal, 4 success criteria, operator prerequisite line
- `.planning/REQUIREMENTS.md` — WEB-03 (nginx HTTPS + certbot timer), WEB-04 (HTTP→HTTPS + HSTS), INFRA-01 (Resend domain verification + SIGNALS_EMAIL_FROM env var)
- `.planning/PROJECT.md` §Deployment — DO droplet systemd primary; Phase 10 INFRA-02 deploy-key pushback; `.env` loaded by systemd EnvironmentFile=- optional prefix

### Prior-phase decisions that constrain Phase 12
- `.planning/phases/10-foundation-v1-0-cleanup-deploy-key/10-CONTEXT.md` — `_push_state_to_git` helper + SETUP-DEPLOY-KEY.md runbook pattern; operator-setup doc lives in phase directory
- `.planning/phases/11-web-skeleton-fastapi-uvicorn-systemd/11-CONTEXT.md` — `systemd/trading-signals-web.service` committed to repo; `EnvironmentFile=-/etc/trading-signals/.env` optional prefix; FastAPI runs on `127.0.0.1:8000` (nginx proxies INTO this)
- `.planning/phases/11-web-skeleton-fastapi-uvicorn-systemd/11-*-PLAN.md` — `deploy.sh` sequence + sudoers pattern (Phase 12 extends both); 6-pillar nginx/certbot not referenced yet — this phase adds them

### Source files touched by Phase 12
- `notifier.py` — read `SIGNALS_EMAIL_FROM` env var per-send (D-15); remove `_EMAIL_FROM` at line 99 (D-16); add fail-soft path for missing env var (D-14)
- `tests/test_notifier.py` — update `TestGoldenEmail` + sibling Resend-payload tests to `monkeypatch.setenv` (D-19); add new `TestEmailFromEnvVar` class with 3 tests (D-17)
- `deploy.sh` — add nginx config-test + reload hook, gated on nginx install + `nginx/signals.conf` existence (D-20)
- `tests/test_deploy_sh.py` — add ordering assertion for the new reload step + negative assertion for the "skip when no nginx" branch
- `nginx/signals.conf` — NEW file at repo root `nginx/` dir with `<owned-domain>` placeholder; single server block + HTTP-redirect block + HSTS + rate-limit + security headers (D-05, D-08, D-10, D-11)
- `.planning/phases/12-https-domain-wiring/SETUP-HTTPS.md` — NEW operator runbook (D-21)

### Architectural invariants (do not break)
- `CLAUDE.md` §Architecture — hex-lite: `notifier.py` stays I/O-narrow (HTTP + env-var read only; no subprocess, no git calls); `main.py` is sole orchestrator
- `CLAUDE.md` §Conventions — 2-space indent, single quotes, `[Email]` log prefix for notifier messages (new "SIGNALS_EMAIL_FROM not set" line uses `[Email]`)
- Phase 8 W3 two-saves-per-run invariant preserved — notifier failure path calls `append_warning` only; no third `save_state` added

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable assets
- `notifier._send_email_never_crash` (Phase 6/8) — already does the "log + skip on missing config" pattern for `RESEND_API_KEY`. Phase 12's SIGNALS_EMAIL_FROM missing-env handling is a direct mirror: check env var, if absent/empty → log + append_warning + return early.
- `state_manager.append_warning(state, source, message, now=None)` (Phase 3) — sole-writer API for `state['warnings']`. Phase 12 uses `source='notifier'` (not 'state_pusher') since the failure origin is the email path.
- `systemd/trading-signals-web.service` (Phase 11) — `EnvironmentFile=-/etc/trading-signals/.env` optional prefix means adding `SIGNALS_EMAIL_FROM` to `.env` requires ZERO unit-file changes.
- `deploy.sh` (Phase 11) — sudoers-gated `systemctl restart` pattern; Phase 12 extends this to include `nginx -t && systemctl reload nginx`.
- Phase 10 `SETUP-DEPLOY-KEY.md` structure — 6-step operator runbook with Prerequisites + Quickstart + numbered Steps + Pitfalls sections. Phase 12 `SETUP-HTTPS.md` mirrors this shape.

### Established patterns
- **Local imports inside never-crash wrappers** — `_send_email_never_crash` imports `notifier` locally; new env-var read uses `import os` at function body level if not already imported at module top (already imported per Phase 8).
- **Config committed to repo with placeholders** — `systemd/trading-signals-web.service` has `User=trader` hardcoded + `<owned-domain>` placeholder pattern not yet used; Phase 12 introduces the placeholder pattern via `<owned-domain>` in `nginx/signals.conf`.
- **Setup doc in phase directory** — Phase 10 + 11 precedent: operator runbook lives at `.planning/phases/<N-slug>/SETUP-*.md`. Phase 12 follows.
- **Grep-verifiable acceptance criteria** — every plan task has grep-checkable text (e.g., `grep -q 'Strict-Transport-Security: max-age=31536000' nginx/signals.conf`).

### Integration points
- `notifier._post_to_resend` payload construction at notifier.py:1302-1306 — `'from': from_addr` is where the env-var-read value arrives. `from_addr` param comes from the caller; Phase 12 changes the caller to read env var instead of module constant.
- `deploy.sh` lines after the second `sudo -n systemctl restart` call — inject the nginx reload hook there (D-20); existing retry-loop smoke test at `/healthz` (Phase 11 D-23 step 7) still uses `localhost:8000` pre-nginx but post-Phase-12 will go through nginx on port 443 (SETUP-HTTPS.md operator step).
- `tests/test_notifier.py::TestGoldenEmail` (Phase 6) — class-level or autouse fixture that sets SIGNALS_EMAIL_FROM is the cleanest way to keep existing golden-file assertions working post-refactor.

</code_context>

<specifics>
## Specific Ideas

- **Operator's verified domain is already `signals@carbonbookkeeping.com.au`.** INFRA-01 is a pure refactor, not a DNS/Resend-setup task. Every locked decision around env var + failure mode assumes the value `signals@carbonbookkeeping.com.au` will be set in `.env` (or the equivalent verified address if operator switches later).

- **Certbot auto-injects the HTTP→HTTPS redirect.** Don't hand-write the `return 301 https://$host$request_uri;` block — let `certbot --nginx` add it automatically (cleaner and it knows the exact server_name). Our committed `nginx/signals.conf` only needs the HTTPS (443) block pre-cert; certbot patches in the HTTP (80) redirect block on first run.

- **The Phase 11 `deploy.sh` smoke test hits `localhost:8000/healthz`** and will KEEP hitting localhost (not nginx) even post-Phase-12, because deploy.sh runs on the droplet as the trader user and the behavior is "confirm FastAPI process responds". External HTTPS verification is a SETUP-HTTPS.md operator step, not a deploy.sh concern.

- **Let's Encrypt rate limits are a real risk during setup.** 5 duplicate cert requests per week per registered domain. SETUP-HTTPS.md §Troubleshooting must mention: if initial `certbot --nginx` fails, use `--dry-run` before retrying; if still stuck, wait 168 hours before next attempt. Alternative: use Let's Encrypt staging (`--staging` flag) for first iteration.

- **No mTLS, no client certs.** v1.1 is single-operator; no fleet. Revisit in v1.2 if ever team-owned.

- **HSTS header duration is non-negotiable at 31536000 (1 year).** SC-2 specifies the exact value. Don't optimize to shorter during testing — Phase 12 UAT can use the Let's Encrypt staging cert to avoid production cert churn if needed.

</specifics>

<deferred>
## Deferred Ideas

- **Apex-domain (no subdomain) support.** v1.1 uses `signals.<owned-domain>.com`. Supporting `<owned-domain>.com/signals` or root would require path-prefix handling in FastAPI + different nginx routing. v1.2 candidate.

- **Cloudflare proxy / CDN in front.** v1.1 goes direct. Adding Cloudflare requires DNS-01 challenge, X-Forwarded-For trust, and real-IP extraction. v1.2+ if DDoS becomes a concern.

- **Full CSP header.** Deferred to Phase 13 when WEB-05 HTML dashboard lands. Premature on /healthz (JSON only).

- **HSTS preload submission.** Keeping the escape hatch open for v1.1. Revisit once all subdomains are committed to HTTPS forever.

- **IP allowlist on /healthz.** Deferred — rate-limit + Phase 13 AUTH-01 shared-secret header cover the threat surface. Revisit if probe traffic becomes noisy.

- **Status page integration (UptimeRobot, Healthchecks.io).** Deferred to v1.2 operational hardening. Phase 12 leaves /healthz public + rate-limited so operator can wire a status page later without code changes.

- **Let's Encrypt wildcard cert (`*.<owned-domain>.com`).** Requires DNS-01. Only useful if we ever have multiple subdomains (e.g., `api.<domain>`, `admin.<domain>`). Deferred to when we have >1 subdomain.

- **nginx caching of /healthz response.** Could reduce backend load; probably pointless given FastAPI reads state.json once-per-request already. Deferred.

- **SIGNALS_EMAIL_FROM rotation procedure.** How does operator switch to a different verified sender? Currently: edit `.env`, `systemctl restart trading-signals`. Documented in SETUP-HTTPS.md §Troubleshooting. No formal rotation policy for v1.1.

- **Email DMARC policy tightening (`p=reject`).** Operator already has DMARC set up per "Resend domain verification complete". Tightening policy from `p=none` to `p=reject` is an operator DNS task, not code. Deferred.

### Reviewed Todos (not folded)
None — `gsd-sdk query todo.match-phase 12` returned zero matches.

</deferred>

---

*Phase: 12-https-domain-wiring*
*Context gathered: 2026-04-24*
