# SETUP-HTTPS.md — Trading Signals HTTPS + domain one-time setup

**Phase 12 / WEB-03 + WEB-04 + INFRA-01 operator runbook.** One-time
setup to put `signals.<owned-domain>.com` on HTTPS via nginx + Let's
Encrypt, with HTTP→HTTPS 301 redirect, HSTS, rate-limited `/healthz`,
and the `SIGNALS_EMAIL_FROM` env var wiring that finishes the Resend
domain refactor.

**Audience:** project operator (Marc).
**Where this runs:** the DigitalOcean droplet, as the `trader` user
that runs the `trading-signals` + `trading-signals-web` systemd units
(Phase 11+).
**Prerequisite:** Phase 11 SETUP-DROPLET.md complete — FastAPI healthy
on `127.0.0.1:8000`; sudoers entry already in place; deploy.sh runs
green.
**Cost:** free (Let's Encrypt + apt packages).

> **Read first: `docs/DEPLOY.md` is stale.** That file still describes
> GitHub Actions as the primary deployment path (v1.0 era). It has not
> been rewritten yet — rewrite is deferred to a post-Phase-12
> docs-sweep phase (see
> `.planning/phases/10-foundation-v1-0-cleanup-deploy-key/10-CONTEXT.md`
> §Deferred Ideas). For current v1.1 HTTPS / domain guidance, use
> THIS file (`SETUP-HTTPS.md`), `SETUP-DROPLET.md` (Phase 11
> systemd setup), `.planning/PROJECT.md` Deployment section, and
> `CLAUDE.md` §Stack.

> **Read first (operational):** this is a one-time runbook. After
> completion, all updates flow through `bash deploy.sh` (which now has
> a gated nginx reload hook — see Plan 12-03). The gate
> `[ -f nginx/signals.conf ] && command -v nginx &>/dev/null` checks
> (1) repo file presence and (2) the nginx binary is on PATH; it does
> NOT check whether the site is symlinked into `sites-enabled/` or
> whether certbot has run. Pre-Phase-12 droplets stay safe — the gate
> short-circuits before any sudo invocation.

> **Read first (T-12-06):** `add_header` directives in nginx are
> REPLACED (not extended) by any nested `add_header` block. Phase 13+
> authors who add per-route headers MUST either redeclare ALL security
> headers (Strict-Transport-Security, X-Content-Type-Options,
> X-Frame-Options, Referrer-Policy) inside that location, or use the
> third-party `headers-more-nginx-module`. Silent HSTS regression is
> the failure mode this callout exists to prevent.

***

## Quickstart

1. Verify prerequisites (DNS propagated, firewall, Resend already
   verified).
2. `apt install` nginx + certbot.
3. Copy `nginx/signals.conf` into nginx, sed `<owned-domain>`,
   symlink, `nginx -t` + `systemctl reload nginx`.
4. Run `certbot --nginx --dry-run` FIRST, then production issuance.
5. Verify HTTPS end-to-end with `curl -sI` + `openssl s_client`.
6. Confirm `certbot.timer` is active + create the renewal deploy
   hook so post-renewal nginx reloads happen automatically.
7. Add `SIGNALS_EMAIL_FROM=signals@carbonbookkeeping.com.au` to
   `/home/trader/trading-signals/.env`, restart, verify with
   `--force-email`.
8. Extend the sudoers file from 2 to 4 rules so `deploy.sh`'s gated
   nginx reload hook runs passwordlessly.
9. Use the troubleshooting table if anything sticks.
10. Rollback procedure documented at the bottom in case HTTPS has to
    be peeled back.

Each step is detailed below.

***

## 1 Prerequisites

Verify BEFORE starting the bash blocks below.

- Phase 11 SETUP-DROPLET.md completed — `systemctl status
  trading-signals-web` is `active`; FastAPI bound to `127.0.0.1:8000`;
  sudoers `/etc/sudoers.d/trading-signals-deploy` already has the
  Phase 11 2-rule line.
- Domain purchased at registrar of choice (e.g.,
  `carbonbookkeeping.com.au`).
- A-record `signals.<owned-domain>.com` points to droplet IP; TTL
  300s or lower while iterating.
- DNS propagated — verify from two resolvers:

  ```bash
  dig @1.1.1.1 +short signals.<owned-domain>.com
  dig @8.8.8.8 +short signals.<owned-domain>.com
  ```

  Both must return the droplet IP. If they don't match, wait for
  propagation BEFORE running certbot. Burning a Let's Encrypt
  rate-limit slot on a DNS stutter is a bad time (see §9
  Troubleshooting).

- Resend domain already verified — operator confirmed
  `signals@carbonbookkeeping.com.au` has SPF / DKIM / DMARC live. NO
  Resend action in this runbook (per D-04). If your verified sender
  differs, substitute it everywhere `signals@carbonbookkeeping.com.au`
  appears below.
- Droplet firewall allows inbound ports 80 + 443:

  ```bash
  sudo ufw status
  # Expect rows including:
  #   80/tcp   ALLOW
  #   443/tcp  ALLOW
  # If missing:
  #   sudo ufw allow 80/tcp
  #   sudo ufw allow 443/tcp
  ```

***

## 2 Install nginx + certbot

```bash
sudo apt update
sudo apt install -y nginx certbot python3-certbot-nginx

nginx -v
# Posture check: a version line is printed (e.g., nginx/1.x.y) — exact
# version varies by Ubuntu release (22.04 ships 1.18.x; 24.04 ships
# 1.24.x; future LTS ships newer). Exact match is NOT required.

certbot --version
# Posture check: certbot >= 1.21 prints a version line. Older versions
# pre-date the `--nginx` plugin's modern behaviour; if the apt repo
# resolves an older one, switch to the snap install (out of scope here).
```

***

## 3 Copy nginx config + substitute placeholder + symlink

Copy the committed `nginx/signals.conf` into nginx's
`sites-available` directory, substitute the `<owned-domain>`
placeholder, symlink into `sites-enabled`, then verify syntax with
`nginx -t`.

```bash
cd /home/trader/trading-signals
sudo cp nginx/signals.conf /etc/nginx/sites-available/signals.conf

# Substitute the placeholder. Example for carbonbookkeeping.com.au —
# the placeholder is `<owned-domain>` (literal angle brackets):
sudo sed -i 's|<owned-domain>|carbonbookkeeping|g' \
  /etc/nginx/sites-available/signals.conf

# Confirm zero placeholders remain:
grep '<owned-domain>' /etc/nginx/sites-available/signals.conf
# Expect: (empty output — no remaining placeholders)

# Symlink into sites-enabled
sudo ln -s /etc/nginx/sites-available/signals.conf \
  /etc/nginx/sites-enabled/signals.conf

# Verify syntax BEFORE running certbot
sudo nginx -t
sudo systemctl reload nginx
```

Notes:

- The committed `nginx/signals.conf` deliberately has NO `listen 80`
  block and NO `ssl_certificate` lines — certbot injects the port-80
  redirect block and the cert directives automatically on first run
  (Pitfall 1: pre-existing port-80 blocks confuse certbot's
  "add HTTPS to this server" heuristic, and committed cert paths leak
  hostnames into git history).
- The committed file's `nginx -t` acceptance gate is the real
  acceptance test — pytest text checks confirm the file shape but
  cannot reproduce nginx's actual parser.
- HSTS is present at server scope with the WEB-04 exact value
  `max-age=31536000; includeSubDomains`; `preload` is intentionally
  NOT used (D-12 keeps the escape hatch open in case TLS has to be
  rolled back).

***

## 4 Run certbot (HTTPS issuance)

**`--dry-run` FIRST, always.** Let's Encrypt rate-limits 5 duplicate
certificates per 168 hours per exact identifier set (Pitfall 4). A
misconfigured first production run can burn a whole week of retries.

```bash
# STEP 4a — dry-run uses Let's Encrypt staging; zero rate-limit cost.
sudo certbot --nginx --dry-run -d signals.<owned-domain>.com

# If the dry-run succeeds, proceed to production issuance:
sudo certbot --nginx -d signals.<owned-domain>.com
```

Interactive prompts certbot will ask:

- Email address for renewal notifications.
- Terms of Service agreement.
- EFF newsletter subscription? — answer N.
- Redirect HTTP → HTTPS? — **choose option 2 (redirect)**. Certbot
  will inject a new `server { listen 80; ... return 301 https://...; }`
  block into `/etc/nginx/sites-available/signals.conf` and reload
  nginx automatically.

After successful issuance, the installed config now contains
`# managed by Certbot` markers around the injected `ssl_certificate` /
`ssl_certificate_key` lines and the port-80 redirect block. Note —
certbot-managed edits modify the INSTALLED file at
`/etc/nginx/sites-available/signals.conf`, NOT the committed repo
artifact at `nginx/signals.conf`. The two files are intentionally
allowed to drift on a configured droplet (the committed file is the
pristine template; the installed file is the certbot-augmented live
copy).

***

## 5 Verify HTTPS end-to-end

From your laptop (NOT the droplet — external reachability is the
acceptance check):

```bash
# SC-1: HTTPS /healthz returns 200 with Let's Encrypt cert
curl -sI https://signals.<owned-domain>.com/healthz
# Expect headers including:
#   HTTP/2 200
#   Strict-Transport-Security: max-age=31536000; includeSubDomains
#   X-Content-Type-Options: nosniff
#   X-Frame-Options: DENY
#   Referrer-Policy: strict-origin-when-cross-origin

# SC-2: HTTP redirects to HTTPS
curl -sI http://signals.<owned-domain>.com/healthz
# Expect:
#   HTTP/1.1 301 Moved Permanently
#   Location: https://signals.<owned-domain>.com/healthz

# Cert chain inspection — Issuer must include "Let's Encrypt"
openssl s_client -connect signals.<owned-domain>.com:443 \
  -servername signals.<owned-domain>.com </dev/null 2>/dev/null \
  | openssl x509 -noout -issuer
# Expect: an Issuer line containing "Let's Encrypt". The exact
# intermediate CN (e.g. R10, R11, E5, E6) rotates over time as Let's
# Encrypt deploys new intermediate CAs. Posture check: grep "Let's
# Encrypt" — do NOT pin a specific CN.
```

***

## 6 Confirm certbot.timer + create renewal hook

Auto-renewal runs via the systemd timer that apt installed alongside
certbot. No cron required.

```bash
# Timer should be enabled and active
systemctl list-timers | grep certbot
# Expect a row similar to:
#   ... certbot.timer  certbot.service ... active ...

# Dry-run renewal — confirms the renewal path works end-to-end without
# requesting an actual cert.
sudo certbot renew --dry-run
# Expect: "Congratulations, all simulated renewals of an existing
# certificate have been performed."

# Create a renewal deploy hook that reloads nginx after each renewal
# so new cert material takes effect without manual intervention.
sudo tee /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh \
  > /dev/null <<'EOF'
#!/bin/sh
systemctl reload nginx
EOF
sudo chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh

# Confirm the hook is executable
ls -l /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
# Expect: -rwxr-xr-x ... reload-nginx.sh
```

***

## 7 Add SIGNALS_EMAIL_FROM to droplet .env (INFRA-01)

Phase 12 refactors `notifier.py` to read the sender address from the
`SIGNALS_EMAIL_FROM` env var — the hardcoded `_EMAIL_FROM` constant
is gone (D-16). The systemd unit already loads env vars from
`/home/trader/trading-signals/.env` via the `EnvironmentFile=-`
optional-prefix directive (Phase 11 D-12) — no unit-file change
needed.

```bash
# Append the env var to the droplet .env file. The .env path here
# matches systemd/trading-signals-web.service's EnvironmentFile=
# directive — drift between the two is asserted by
# tests/test_setup_https_doc.py::TestCrossArtifactDriftGuard
# ::test_env_path_matches_systemd_unit.
echo 'SIGNALS_EMAIL_FROM=signals@carbonbookkeeping.com.au' \
  | sudo tee -a /home/trader/trading-signals/.env

# Restart the signal service so it picks up the new env var. The web
# service does NOT consume this env var — no restart needed for it.
sudo systemctl restart trading-signals

# Verify by forcing an email send (does not mutate state.json)
cd /home/trader/trading-signals
.venv/bin/python main.py --force-email
# Expect: an email arrives in operator inbox FROM
# signals@carbonbookkeeping.com.au (NOT onboarding@resend.dev). The
# `From:` header in the received message confirms the env var made it
# end-to-end through Resend.
```

**Failure mode** (Phase 12 D-14): if `SIGNALS_EMAIL_FROM` is missing
or empty, notifier.py logs `[Email] SIGNALS_EMAIL_FROM not set —
email skipped` and returns `SendStatus(ok=False, reason='missing_sender')`.
The next daily run surfaces this as a stale/warnings banner. The
send is NEVER silently routed to `onboarding@resend.dev` — that
behaviour is intentional per SC-4 ("never silently falls back").

***

## 8 Extend sudoers for deploy.sh nginx reload hook

Phase 12 adds a gated nginx reload block to `deploy.sh` (Plan 03).
The block runs `sudo -n nginx -t` + `sudo -n systemctl reload nginx`,
which both require sudoers entries to run passwordlessly.

**Verify absolute paths BEFORE pasting the rule (Pitfall 7).** Ubuntu
ships `nginx` in `/usr/sbin/`, NOT `/usr/bin/` — sudoers paths must
be EXACT or sudo refuses passwordless mode and prompts for a
password (which `sudo -n` then fails on, breaking deploy.sh):

```bash
which nginx
# Expect: /usr/sbin/nginx  (Ubuntu admin binary location)

which systemctl
# Expect: /usr/bin/systemctl
```

If either returns a different path on your droplet (rare —
non-Debian-derivatives), substitute that path into the sudoers line
below before running `visudo`.

**Edit the existing sudoers file:**

```bash
sudo visudo -f /etc/sudoers.d/trading-signals-deploy
```

Replace the Phase 11 2-rule line with this 4-rule line. It MUST be a
single physical line, comma-separated:

```
trader ALL=(root) NOPASSWD: /usr/bin/systemctl restart trading-signals, /usr/bin/systemctl restart trading-signals-web, /usr/sbin/nginx -t, /usr/bin/systemctl reload nginx
```

Then fix permissions and validate:

```bash
sudo chmod 440 /etc/sudoers.d/trading-signals-deploy
sudo chown root:root /etc/sudoers.d/trading-signals-deploy
sudo visudo -c -f /etc/sudoers.d/trading-signals-deploy
# Expect: /etc/sudoers.d/trading-signals-deploy: parsed OK
```

**Passwordless verification** (Phase 11 HIGH #4 pattern, extended for
the new 2 commands). Run this BEFORE the next `bash deploy.sh` so
sudoers errors show up here, not in a deploy:

```bash
sudo -n nginx -t
# Expect: "nginx: configuration file /etc/nginx/nginx.conf syntax is
# ok" + silent success. MUST NOT prompt for a password.

sudo -n systemctl reload nginx
# Expect: silent success. MUST NOT prompt for a password.
```

If either command prints `sudo: a password is required`, the sudoers
path is wrong — go back, re-verify `which nginx` + `which systemctl`
output, and re-paste the line. Common causes: `/usr/bin/nginx` typo
(Ubuntu ships `/usr/sbin/nginx`), trailing whitespace inside the
quoted path, or a stray space after a comma.

**Anti-pattern WARNINGS** (carried forward from Phase 11 sudoers
hardening — Compass Security 2012 wildcard-sudo post + sudoers
manpage):

- NEVER use `NOPASSWD: ALL` — a compromised `trader` account becomes
  effectively root. Our 4-rule line uses absolute command paths and
  fixed arguments, scoping privilege to the exact actions deploy.sh
  needs and nothing more.
- NEVER use wildcards in command paths. `NOPASSWD: /usr/sbin/nginx *`
  lets `trader` run `nginx -s stop && rm -rf /` because `*` matches
  arbitrary arguments — including arguments the operator never
  intended. Compass Security's 2012 wildcard-sudo post is still the
  canonical reference; the 4-rule line above intentionally avoids
  any wildcard.
- Use absolute paths with fixed arguments. `nginx -t` and
  `systemctl reload nginx` are the only invocations the deploy hook
  actually uses, so those are the only invocations privileged by
  the rule. Adding more sudoable commands "just in case" expands the
  privilege surface without proportional benefit.

***

## 9 Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `dig +short signals.<owned-domain>.com` returns empty or wrong IP | DNS not propagated yet (Pitfall 6) | Wait 30 min; re-check from multiple resolvers. Do NOT run certbot until both `1.1.1.1` and `8.8.8.8` return the droplet IP. |
| `certbot --nginx` error: `too many certificates already issued for exact set of domains` | Let's Encrypt 5-certs-per-168h rate limit hit (Pitfall 4) | Wait 168 hours OR use `--staging` for iteration. ALWAYS `--dry-run` before production. **If you need >1-2 retries, switch to `--staging` immediately** — staging has no production rate limit; only switch to production once staging runs cleanly end-to-end (12-REVIEWS.md LOW — gemini). |
| `sudo -n nginx -t` → `sudo: a password is required` | sudoers path mismatch — `/usr/sbin/nginx` vs `/usr/bin/nginx` typo (Pitfall 7) | `which nginx` → paste exact path into sudoers via `visudo` → `visudo -c -f` to validate → re-verify `sudo -n nginx -t`. |
| `sudo certbot --nginx` → `Detail: Fetching http://signals.../.well-known/acme-challenge/... Timeout` | Port 80 blocked by ufw, or A-record wrong | `sudo ufw status` → ensure `80/tcp ALLOW`; `dig` again to verify A-record returns droplet IP. |
| nginx syntax error after sed | Forgot to substitute `<owned-domain>` placeholder | `grep '<owned-domain>' /etc/nginx/sites-available/signals.conf` — should be zero hits post-sed; re-run sed if any remain. |
| Daily email doesn't arrive | `SIGNALS_EMAIL_FROM` missing in `/home/trader/trading-signals/.env` | `journalctl -u trading-signals -n 50 \| grep '[Email] SIGNALS_EMAIL_FROM not set'` — confirms the missing_sender warning, then add the env var to `.env` and restart. |
| Resend quota exhausted (monthly send cap) | Free tier limit reached | Check Resend dashboard; upgrade plan or wait for monthly reset. |
| HSTS cached by browser after rollback | HSTS `max-age=1y` is client-persistent | User must clear browser HSTS cache (chrome://net-internals/#hsts) OR wait up to 1 year for natural expiry. This is WHY D-12 rejected the `preload` directive — preload would require an hstspreload.org removal request, with months of propagation. |

### SIGNALS_EMAIL_FROM rotation

To switch to a different verified Resend sender (no formal rotation
policy for v1.1 — operator DNS task; Resend domain verification
remains the operator's responsibility):

```bash
sudo sed -i 's|SIGNALS_EMAIL_FROM=.*|SIGNALS_EMAIL_FROM=signals@newdomain.com|' \
  /home/trader/trading-signals/.env
sudo systemctl restart trading-signals
.venv/bin/python main.py --force-email   # verify
```

***

## 10 Rollback

If HTTPS must be abandoned (domain issue, certbot regression,
unrecoverable nginx fault), revert to Phase 11 localhost-only
posture:

- Disable the nginx site:
  `sudo rm /etc/nginx/sites-enabled/signals.conf`
- Reload (or stop) nginx so the disabled site stops serving:
  `sudo systemctl reload nginx` (or `sudo systemctl stop nginx`
  entirely if you want to free ports 80 + 443).
- Revert sudoers extension:
  `sudo visudo -f /etc/sudoers.d/trading-signals-deploy` and remove
  the trailing two commands `/usr/sbin/nginx -t,
  /usr/bin/systemctl reload nginx` from the comma-separated rule,
  leaving only the Phase 11 2-rule line.
- Remove `SIGNALS_EMAIL_FROM` from
  `/home/trader/trading-signals/.env` — daily email will skip with a
  warning until the env var is re-added (D-14 failure mode is by
  design; this is not a regression).
- FastAPI remains on `127.0.0.1:8000`; `bash deploy.sh` continues to
  work — but note the deploy.sh nginx reload hook is gated on
  `[ -f nginx/signals.conf ] && command -v nginx &>/dev/null`, which
  checks (1) repo file presence and (2) nginx binary in PATH. The
  gate does NOT check whether the site is symlinked into
  `sites-enabled/` or whether certbot has run. A freshly-installed
  nginx with no enabled site will still trigger the reload (harmless
  but explicit — 12-REVIEWS.md LOW clarification). To fully disable
  the hook on rollback, either uninstall nginx entirely
  (`sudo apt purge nginx`) so `command -v nginx` fails, or remove the
  `nginx/signals.conf` file from the repo on a follow-up commit so
  the file-existence test fails.
- The committed `nginx/signals.conf` stays in git — rollback does NOT
  revert the commit. Future "re-enable HTTPS" path is to re-run this
  runbook from §3.

***

*Last updated: Phase 12 (HTTPS + Domain Wiring). 2026-04-24.*
*Run this runbook ONCE per droplet. Subsequent updates use `bash
deploy.sh` (nginx reload hook gated on `nginx/signals.conf`
presence + nginx binary on PATH).*
*Record completion date in STATE.md §Accumulated Context once §5
curl shows the Let's Encrypt cert chain and §7 `--force-email`
delivers from the env-configured FROM address.*
