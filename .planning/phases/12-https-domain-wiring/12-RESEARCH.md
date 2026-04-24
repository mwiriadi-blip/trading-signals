# Phase 12: HTTPS + Domain Wiring — Research

**Researched:** 2026-04-24
**Domain:** nginx reverse-proxy + Let's Encrypt HTTPS + Resend env-var refactor on Ubuntu 22.04/24.04 droplet
**Confidence:** HIGH on nginx config + HSTS (multiple corroborating sources, Mozilla generator locked); HIGH on notifier.py code topology (direct read); MEDIUM on certbot exact-patch behavior (doc-level, not source-verified end-to-end)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Area 1 — Domain + DNS (pre-planning posture)**
- **D-01:** Use `<owned-domain>` as a literal placeholder in all committed config. Nginx config uses `<owned-domain>` literally; plan tests assert the placeholder is present; SETUP-HTTPS.md tells the operator to `sed` it in post-clone.
- **D-02:** Subdomain pattern `signals.<owned-domain>.com`. Single server block, single cert. Apex and other subdomains out of scope for v1.1.
- **D-03:** No Cloudflare / CDN proxy. Direct DNS A-record to droplet IP. Keeps HTTP-01 challenge viable and simplifies nginx config (no `X-Forwarded-For` trust chain needed).
- **D-04:** Resend domain verification is NOT a Phase 12 task — operator has `signals@carbonbookkeeping.com.au` verified. INFRA-01 is a pure code refactor.

**Area 2 — nginx + certbot install**
- **D-05:** Commit nginx config to repo at `nginx/signals.conf`. File contains `<owned-domain>` placeholder; operator symlinks into `/etc/nginx/sites-enabled/` after substituting.
- **D-06:** HTTP-01 challenge via `certbot --nginx` plugin from apt (`apt install certbot python3-certbot-nginx`); issuance via `certbot --nginx -d signals.<owned-domain>.com`.
- **D-07:** Auto-renewal via `certbot.timer` (Ubuntu default). Renewal hook: `/etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh` with `systemctl reload nginx`. Created during SETUP-HTTPS.md; no repo code change.
- **D-08:** nginx config structure — single `server` block listening on 443 (ssl), proxy to `http://127.0.0.1:8000`, preserve `Host`, `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto`. Separate `server` block on 80 with `return 301 https://$host$request_uri;`. HSTS on 443 block.
- **D-09:** Renewal port-80 listener stays up for HTTP-01 renewal validation.

**Area 3 — Security headers + rate limiting**
- **D-10:** Rate-limit `/healthz` at nginx layer — `limit_req_zone $binary_remote_addr zone=healthz:10m rate=10r/m;` at http scope + `limit_req zone=healthz burst=10 nodelay;` on `location = /healthz`.
- **D-11:** Security headers on 443 block:
  - `Strict-Transport-Security: max-age=31536000; includeSubDomains` (WEB-04 exact; NO preload)
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `Referrer-Policy: strict-origin-when-cross-origin`
  - CSP deferred to Phase 13.
- **D-12:** No HSTS preload submission.
- **D-13:** No IP allowlist.

**Area 4 — SIGNALS_EMAIL_FROM failure mode**
- **D-14:** Missing `SIGNALS_EMAIL_FROM` → `logger.error('[Email] SIGNALS_EMAIL_FROM not set — email skipped')` + `state_manager.append_warning(state, source='notifier', message='SIGNALS_EMAIL_FROM env var missing — daily email skipped')` + return `SendStatus(ok=False, reason='missing_sender', attempts=0)`. Does NOT fall back to `onboarding@resend.dev`. Run continues normally.
- **D-15:** Env var read per-send inside `_post_to_resend` or its caller — NOT at module import. `os.environ.get('SIGNALS_EMAIL_FROM')`.
- **D-16:** Remove `_EMAIL_FROM = 'signals@carbonbookkeeping.com.au'` at notifier.py:99. Env var is ONLY source.
- **D-17:** Regression test `tests/test_notifier.py::TestEmailFromEnvVar` — 3 tests: `test_from_addr_reads_env_var`, `test_missing_env_var_skips_email_with_warning`, `test_empty_env_var_treated_as_missing`.

**Area 5 — Integration with Phase 11 infra**
- **D-18:** Add `SIGNALS_EMAIL_FROM` to droplet `.env` file. No systemd unit file changes.
- **D-19:** Update `TestGoldenEmail` (and any sibling Resend-payload tests) to `monkeypatch.setenv('SIGNALS_EMAIL_FROM', 'signals@carbonbookkeeping.com.au')` in a fixture (e.g., `@pytest.fixture(autouse=True)` on the class). Test updates land in same commit as notifier code change.
- **D-20:** Update `deploy.sh` with nginx `-t` + reload hook gated on nginx being installed AND `nginx/signals.conf` existing:
  ```bash
  if [ -f nginx/signals.conf ] && command -v nginx &>/dev/null; then
    sudo -n nginx -t && sudo -n systemctl reload nginx
  fi
  ```
  Requires sudoers entry for `trader` to run `/usr/sbin/nginx -t` and `/bin/systemctl reload nginx`. Test: `tests/test_deploy_sh.py` adds ordering check + negative assertion.
- **D-21:** New operator runbook at `.planning/phases/12-https-domain-wiring/SETUP-HTTPS.md` with 10 sections (Prerequisites, Install nginx+certbot, Copy+substitute+symlink+nginx -t, Run certbot, Verify, Confirm certbot.timer, Add env var + restart + verify, Extend sudoers, Troubleshooting, Rollback).

### Claude's Discretion
- **Exact nginx config body** — planner writes final `server { ... }` blocks with `ssl_protocols TLSv1.2 TLSv1.3` + `ssl_prefer_server_ciphers off` + modern Mozilla SSL config.
- **sudoers entry exact form** — planner decides split vs single file under `/etc/sudoers.d/`. Must scope to specific absolute command paths (no NOPASSWD: ALL).
- **Env var read location inside notifier.py** — planner picks between `_send_email_never_crash` (main.py wrapper), `_build_resend_payload`, or `_post_to_resend` entry. Must be single read point.
- **Renewal hook script path** — `/etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh` (standard) vs alternative.

### Deferred Ideas (OUT OF SCOPE)
- Apex-domain (no subdomain) support — v1.2
- Cloudflare proxy / CDN — v1.2+
- Full CSP header — Phase 13 (WEB-05)
- HSTS preload submission — v1.1 keeps escape hatch
- IP allowlist on /healthz — Phase 13 AUTH-01 shared-secret covers
- Status page integration (UptimeRobot etc.) — v1.2
- Let's Encrypt wildcard cert — only needed with >1 subdomain
- nginx caching of /healthz response — deferred
- SIGNALS_EMAIL_FROM rotation procedure — documented in Troubleshooting only
- DMARC policy tightening (`p=reject`) — operator DNS task, deferred
- mTLS / client certs — v1.2
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| WEB-03 | nginx serves HTTPS via Let's Encrypt cert for `signals.<owned-domain>.com`; auto-renew via certbot timer | §3 (nginx config template), §4 (certbot --nginx behavior), §5 (certbot.timer auto-enable) |
| WEB-04 | HTTP (port 80) redirects to HTTPS; HSTS `Strict-Transport-Security: max-age=31536000; includeSubDomains` | §3 (nginx HSTS directive with `always` flag), §4 (certbot auto-inserts 301 redirect block) |
| INFRA-01 | `SIGNALS_EMAIL_FROM` env var replaces hardcoded `_EMAIL_FROM`; Resend domain verified | §6 (notifier.py call-chain analysis, 3 sites touched), §7 (TestGoldenEmail fixture pattern) |
</phase_requirements>

## Summary

Phase 12 has three distinct workstreams with independent risk profiles:

1. **nginx reverse-proxy + Let's Encrypt (WEB-03/04)** — well-trodden Ubuntu 22.04/24.04 path. The committed `nginx/signals.conf` should contain ONLY the port-443 server block with full TLS + HSTS + proxy + rate-limit wiring; `certbot --nginx` injects the port-80 redirect server block + the `ssl_certificate`/`ssl_certificate_key` lines automatically on first run. Committing the port-80 block ourselves fights certbot and makes re-runs non-idempotent. HSTS MUST use the `always` flag so it emits on error responses. `/.well-known/acme-challenge/` MUST be carved out of the rate-limit scope via a nested location block — nginx inherits `limit_req` only when no sibling `limit_req` exists at the child level, per [nginx ngx_http_limit_req_module docs](http://nginx.org/en/docs/http/ngx_http_limit_req_module.html).

2. **SIGNALS_EMAIL_FROM refactor (INFRA-01)** — looks trivial but is NOT a one-line deletion. The hardcoded `_EMAIL_FROM` constant has **THREE** usage sites in the current notifier.py (not the two D-14/D-15 suggest): line 1147 inside `_render_footer_email` (rendered into email body HTML, covered by 3 committed golden files), line 1427 inside `send_daily_email`, line 1506 inside `send_crash_email`. The refactor must thread a resolved-sender string into the body renderer OR the golden files must be regenerated with a stable test-fixture env value. The cleanest architecture reads the env var ONCE at the top of `send_daily_email` / `send_crash_email` and passes the resolved value as an argument into `compose_email_body` (which forwards it into `_render_footer_email`). This preserves the pure-function contract of the composer and keeps TestGoldenEmail deterministic via `monkeypatch.setenv` before render.

3. **deploy.sh extension (D-20)** — two sudoers entries need extending: `/usr/sbin/nginx -t` and `/bin/systemctl reload nginx`. Absolute paths are mandatory (wildcard sudo entries are a documented privilege-escalation vector per [Compass Security](https://blog.compass-security.com/2012/10/dangerous-sudoers-entries-part-4-wildcards/)). The existing sudoers rule format is comma-separated on one line; Phase 12 appends two more comma-separated commands. Gate the reload hook on `[ -f nginx/signals.conf ] && command -v nginx` so pre-Phase-12 droplets don't fail on run.

**Primary recommendation:** Commit a complete 443-only server block with TLS tuning, HSTS, security headers, rate-limit zone (at http scope), `limit_req` on `location = /healthz`, and a no-limit nested `location /.well-known/acme-challenge/ { ... }` block. Let certbot inject the 80-block + cert paths. Read `SIGNALS_EMAIL_FROM` exactly once per dispatch at the top of `send_daily_email` and `send_crash_email`, thread into `compose_email_body` → `_render_footer_email`, regenerate goldens with a stable fixture value, and put an `@pytest.fixture(autouse=True)` `monkeypatch.setenv` at module or class level in `tests/test_notifier.py`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| TLS termination + cert management | CDN / Static (nginx + Let's Encrypt) | — | External-facing HTTPS is ALWAYS the edge proxy's job; app should never handle TLS |
| HTTP→HTTPS 301 redirect | CDN / Static (nginx port-80 block) | — | Redirect before app layer; certbot auto-injects |
| Security headers (HSTS, XCTO, XFO, Referrer-Policy) | CDN / Static (nginx) | — | Apply once at edge; backend doesn't need to know about HTTPS |
| /healthz rate limiting (pre-auth) | CDN / Static (nginx `limit_req`) | — | Cheaper at edge than FastAPI middleware; preserves app process for real work |
| FastAPI app (`/healthz` handler) | API / Backend (127.0.0.1:8000) | — | Phase 11 already locked; nginx proxies INTO this |
| State read for `/healthz` | API / Backend (Phase 11 `state_manager.load_state`) | — | Unchanged by Phase 12 |
| Email dispatch (Resend HTTPS) | API / Backend (`notifier.py`) | — | I/O hex; no change to tier |
| Env var resolution (`SIGNALS_EMAIL_FROM`) | API / Backend (read at dispatch time) | — | Env vars injected via systemd `EnvironmentFile=-`; process-local |
| Cert renewal | OS / Systemd (`certbot.timer`) | CDN / Static (renewal deploy hook reloads nginx) | Scheduled job, not an app concern |
| Deploy orchestration | CI / Scripts (`deploy.sh`) | OS / Systemd (triggers systemctl reload) | Same tier as Phase 11 deploy flow |

## Standard Stack

### Core (system packages — NOT Python deps)

| Package | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| nginx | Ubuntu 22.04 stock (1.18+); 24.04 stock (1.24+) | TLS termination + reverse proxy + rate limit | Default web server for Ubuntu LTS; `python3-certbot-nginx` depends on it; first-class support from certbot's `--nginx` plugin. `[VERIFIED: apt-cache on Ubuntu 22.04/24.04]` |
| certbot | apt repo latest (Ubuntu 22.04 default: 1.21 series; 24.04: 2.9 series) | ACME client — obtains + renews Let's Encrypt certs | Standard EFF client; maintained; installs `certbot.timer` automatically. `[VERIFIED: certbot.eff.org instructions]` |
| python3-certbot-nginx | apt repo latest (ships paired with certbot) | Certbot nginx plugin — HTTP-01 challenge + auto-patch nginx config | D-06 locks this; auto-inserts cert paths + redirect block. `[CITED: https://eff-certbot.readthedocs.io/en/stable/using.html#nginx]` |

### Supporting

| Package | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| openssl | Ubuntu 22.04 default (3.0.2); 24.04 default (3.0.x) | Manual cert inspection / debugging | Troubleshooting section of SETUP-HTTPS.md — `openssl s_client -connect signals.<owned-domain>.com:443` (SC-1) |
| curl | any recent | Manual verification from operator laptop | SC-1/SC-2 `curl -sI https://... /healthz` verification step |

### Python runtime dependencies

**ZERO new Python deps in Phase 12.** The refactor to `SIGNALS_EMAIL_FROM` uses `os.environ.get` (stdlib, already imported at notifier.py:50). Tests use pytest's built-in `monkeypatch` fixture. `requirements.txt` is unchanged.

### Alternatives Considered

| Instead of | Could Use | Tradeoff | Verdict |
|------------|-----------|----------|---------|
| certbot via apt | certbot via snap | Snap auto-updates; apt is static version per LTS | D-06 locks apt. Apt is enough; snap adds snapd dependency not otherwise needed. |
| certbot.timer | cron job | Timer is systemd-native; auto-enabled by apt | D-07 locks timer. No reason to hand-roll cron. |
| `certbot --nginx` | `certbot certonly --webroot` | webroot requires pre-configured static path; --nginx auto-patches | D-06 locks --nginx. Simpler for single-host single-cert. |
| Hand-written `server { }` with hardcoded cert paths | Let certbot inject cert paths | Hand-rolled needs manual renewal + reload wiring | Commit 443 block, let certbot patch in cert + 80-block on first run. |
| Mozilla "modern" SSL profile (TLSv1.3 only) | Mozilla "intermediate" (TLSv1.2+1.3) | Modern drops 1.2 — can lock out older clients | Intermediate is operator-safe. [CITED: ssl-config.mozilla.org, 2024 revision] |

**Installation (operator runs during SETUP-HTTPS.md, not automated):**
```bash
sudo apt update
sudo apt install -y nginx certbot python3-certbot-nginx
```

**Version verification (operator confirms during setup):**
```bash
nginx -v       # expect nginx/1.18.x (22.04) or 1.24.x (24.04)
certbot --version  # expect >= 1.21
```

No registry-level version pin because these are distro packages — the planner documents the MINIMUM acceptable versions (nginx 1.18+ for `limit_req` + `ssl_stapling_verify`; certbot 1.21+ for the `--nginx` plugin behavior documented in D-06). `[ASSUMED — Ubuntu 22.04/24.04 stock versions meet minima]` — verified indirectly by certbot's own EFF instructions listing 22.04/24.04 as supported targets.

## Architecture Patterns

### System Architecture Diagram

```
                    Public Internet
                           │
                           │ (port 443 TLS, port 80 → 301)
                           ▼
                ┌──────────────────────┐
                │      nginx           │
                │  /etc/nginx/sites-   │
                │  enabled/signals.conf│
                │                      │
                │  ┌────────────────┐  │
                │  │ server { 443 } │  │
                │  │  TLS (certbot- │  │
                │  │   issued cert) │  │
                │  │  HSTS + XCTO + │  │
                │  │   XFO + RP     │  │
                │  │                │  │
                │  │  location =    │  │
                │  │   /healthz {   │  │
                │  │  limit_req  ───┼──┼──┐
                │  │  proxy_pass ───┼──┼──┼──┐
                │  │  }             │  │  │  │
                │  │                │  │  │  │
                │  │  location /.well-known/acme-challenge/ {  │
                │  │   NO limit_req (carved out)               │
                │  │  }             │  │  │  │
                │  └────────────────┘  │  │  │
                │                      │  │  │
                │  ┌────────────────┐  │  │  │
                │  │ server { 80 }  │  │  │  │
                │  │ [certbot       │  │  │  │
                │  │  injected]     │  │  │  │
                │  │ return 301 https  │  │  │
                │  │  $host$uri     │  │  │  │
                │  └────────────────┘  │  │  │
                └──────────────────────┘  │  │
                                          │  │
                       limit_req zone     ◄┘  │  (rate-limit: 10r/min, burst=10, nodelay)
                       (10MB shared mem)      │
                                              │
                                              ▼
                                   ┌──────────────────────┐
                                   │  FastAPI (Phase 11)  │
                                   │  127.0.0.1:8000      │
                                   │  uvicorn --workers 1 │
                                   │  /healthz handler    │
                                   │    reads state.json  │
                                   └──────────────────────┘

                   ┌──────────────────────────────────┐
                   │  certbot.timer (systemd)         │
                   │  runs twice daily                │
                   │    └─> certbot renew             │
                   │         └─> /etc/letsencrypt/    │
                   │             renewal-hooks/deploy/│
                   │             reload-nginx.sh      │
                   │             (systemctl reload)   │
                   └──────────────────────────────────┘

                    Daily email path (INFRA-01 refactor):
                    ┌──────────────────────┐
                    │  main.run_daily_check│
                    │   │                  │
                    │   └─> _send_email_   │
                    │        never_crash   │
                    │        │             │
                    │        └─> notifier. │
                    │            send_     │
                    │            daily_    │
                    │            email    ◄┼── reads os.environ.get(
                    │                      │      'SIGNALS_EMAIL_FROM')
                    │                      │      ONCE per dispatch
                    │                      │      (D-15 per-send read)
                    │                      │
                    │            missing → │
                    │            log ERROR │
                    │            + append_ │
                    │            warning   │
                    │            + return  │
                    │            SendStatus│
                    │            ok=False  │
                    │            reason=   │
                    │            'missing_ │
                    │            sender'   │
                    │                      │
                    │            present → │
                    │            build     │
                    │            payload + │
                    │            thread    │
                    │            into      │
                    │            compose_  │
                    │            email_    │
                    │            body +    │
                    │            _post_to_ │
                    │            resend    │
                    └──────────────────────┘
```

### Recommended Project Structure (Phase 12 additions)

```
nginx/
└── signals.conf          # NEW: committed nginx server block template
                          #      with <owned-domain> placeholder

.planning/phases/12-https-domain-wiring/
└── SETUP-HTTPS.md        # NEW: 10-section operator runbook (D-21)

tests/
└── test_nginx_signals_conf.py   # NEW: grep-style invariants on nginx config
                                 #      (no shell-out to nginx)
```

Unchanged (Phase 12 modifies but doesn't create):
- `notifier.py` — remove line 99 `_EMAIL_FROM`, thread env var through 3 sites
- `tests/test_notifier.py` — add `TestEmailFromEnvVar` (3 tests per D-17) + autouse fixture patch on `TestGoldenEmail`
- `deploy.sh` — append guarded nginx reload hook after Phase 11 sequence
- `tests/test_deploy_sh.py` — add ordering check + negative assertion
- `tests/fixtures/notifier/golden_*.html` — regenerate via `tests/regenerate_notifier_golden.py` with monkeypatched env var

### Pattern 1: Commit 443-only block, let certbot inject rest

**What:** The committed `nginx/signals.conf` contains ONLY the `server { listen 443 ssl; ... }` block, with the SSL tuning, security headers, rate-limit, and proxy_pass wired. Certbot's `--nginx` plugin injects: (a) the `ssl_certificate` + `ssl_certificate_key` lines, (b) an entirely NEW `server { listen 80; ... return 301 https://$host$request_uri; }` block, and (c) a temporary `location /.well-known/acme-challenge/ { ... }` during renewal handshake.

**When to use:** Ubuntu stock certbot nginx plugin flow, single-host single-cert.

**Why:** Hand-writing the port-80 block forces us to maintain syntactic compatibility with certbot's re-edit pass; certbot may not recognize a hand-written redirect block as "already handling this" and may duplicate-add. Letting certbot own the 80-block means its state machine stays consistent. `[CITED: https://community.letsencrypt.org/t/certbot-nginx-clarifications/195019 and DigitalOcean Ubuntu Let's Encrypt tutorial]`

**Example (`nginx/signals.conf` — 443 block only, PRE-certbot run):**

```nginx
# nginx/signals.conf — Phase 12
# Committed with <owned-domain> as literal placeholder (D-01).
# Operator substitutes during SETUP-HTTPS.md Step 3:
#   sed -i 's|<owned-domain>|carbonbookkeeping|g' /etc/nginx/sites-available/signals.conf
# On first `certbot --nginx` run, certbot injects:
#   (a) ssl_certificate + ssl_certificate_key lines
#   (b) a new `server { listen 80; ... return 301 https://$host$request_uri; }` block
#   (c) temporary location for /.well-known/acme-challenge/ during renewal

# D-10: rate-limit zone at http{} scope. Operator includes this file
# from /etc/nginx/conf.d/ OR moves the `limit_req_zone` line to
# /etc/nginx/nginx.conf http{} — single-zone usage doesn't matter which.
# [VERIFIED: nginx limit_req module docs]
limit_req_zone $binary_remote_addr zone=healthz:10m rate=10r/m;

server {
  listen 443 ssl;
  listen [::]:443 ssl;
  http2 on;

  server_name signals.<owned-domain>.com;

  # --- TLS tuning — Mozilla Intermediate profile (guideline 5.7, 2024 rev) ---
  # [CITED: https://ssl-config.mozilla.org/ — Mozilla SSL Configuration Generator]
  # [CITED: https://letsecure.me/nginx-ssl-hardening-checklist-2026/]
  ssl_protocols TLSv1.2 TLSv1.3;
  ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384:DHE-RSA-CHACHA20-POLY1305;
  ssl_prefer_server_ciphers off;
  ssl_session_cache shared:SSL:10m;
  ssl_session_timeout 1d;
  ssl_session_tickets off;

  # OCSP stapling — requires resolver (certbot does NOT auto-add this)
  # [CITED: nginx SSL hardening checklist 2026]
  ssl_stapling on;
  ssl_stapling_verify on;
  resolver 1.1.1.1 8.8.8.8 valid=300s;
  resolver_timeout 5s;
  # ssl_trusted_certificate is injected by certbot post-issuance

  # NOTE: ssl_certificate + ssl_certificate_key lines are NOT in this file.
  # Certbot injects them on first run. After first certbot, this file will
  # contain (appended by certbot, marked with `# managed by Certbot`):
  #   ssl_certificate /etc/letsencrypt/live/signals.<owned-domain>.com/fullchain.pem;
  #   ssl_certificate_key /etc/letsencrypt/live/signals.<owned-domain>.com/privkey.pem;

  # --- Security headers (D-11) ---
  # HSTS: exact WEB-04 value; `always` flag ensures emission on 4xx/5xx too.
  # [CITED: https://www.getpagespeed.com/server-setup/security/nginx-hsts]
  add_header Strict-Transport-Security 'max-age=31536000; includeSubDomains' always;
  add_header X-Content-Type-Options 'nosniff' always;
  add_header X-Frame-Options 'DENY' always;
  add_header Referrer-Policy 'strict-origin-when-cross-origin' always;

  # --- Let's Encrypt ACME challenge carve-out (D-09) ---
  # nginx inherits limit_req into nested locations ONLY when no limit_req
  # directive exists at the child level. Declaring this block with no
  # limit_req disables rate limiting for ACME challenges during renewal.
  # [CITED: http://nginx.org/en/docs/http/ngx_http_limit_req_module.html]
  location /.well-known/acme-challenge/ {
    # No limit_req here — ACME challenge must not be rate-limited.
    # certbot serves files from a temp webroot during renewal.
    try_files $uri =404;
  }

  # --- /healthz — rate-limited (D-10) ---
  location = /healthz {
    limit_req zone=healthz burst=10 nodelay;
    limit_req_status 429;

    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 5s;
    proxy_connect_timeout 2s;
  }

  # --- Everything else — no rate limit, Phase 13 adds auth ---
  location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 30s;
    proxy_connect_timeout 5s;
  }
}
```

After `certbot --nginx -d signals.<owned-domain>.com` runs, the file will have extra lines injected (marked `# managed by Certbot`), and a second `server { listen 80; ... }` block will be present.

### Pattern 2: Single-point env-var read at dispatch entry

**What:** `send_daily_email(state, old_signals, now, is_test)` reads `os.environ.get('SIGNALS_EMAIL_FROM')` ONCE at the top of the function body, before any payload construction. Pass the resolved value into `compose_email_body` (which threads it into `_render_footer_email`) AND into `_post_to_resend(api_key, from_addr, ...)`. This preserves:
- Pure-function contract of `compose_email_body` (no env reads inside the composer)
- TestGoldenEmail determinism via `monkeypatch.setenv` before render
- Single read point = single test surface

**When to use:** INFRA-01 refactor. Applies to `send_daily_email` AND `send_crash_email` (both currently use `_EMAIL_FROM`).

**Example pattern (pseudocode for planner):**

```python
# notifier.py — new signature (Phase 12)

def send_daily_email(
  state: dict,
  old_signals: dict,
  now: datetime,
  is_test: bool = False,
) -> SendStatus:
  '''...Phase 12: reads SIGNALS_EMAIL_FROM per-send (D-15).'''
  from_addr = os.environ.get('SIGNALS_EMAIL_FROM', '').strip()
  if not from_addr:
    # D-14: log ERROR + append_warning + return early. NO Resend call.
    logger.error('[Email] SIGNALS_EMAIL_FROM not set — email skipped')
    # append_warning needs to land in state; caller (main._dispatch_email_...)
    # translates ok=False → append_warning per Phase 8 D-08. We just return.
    return SendStatus(ok=False, reason='missing_sender')  # D-14

  # ... existing flow, with from_addr threaded into compose_email_body
  #     and _post_to_resend
  html_body = compose_email_body(state, old_signals, now, from_addr=from_addr)
  # ... _post_to_resend(api_key, from_addr, to_addr, subject, html_body)


def compose_email_body(
  state: dict,
  old_signals: dict,
  now: datetime,
  from_addr: str = 'signals@example.invalid',  # default for unit tests
) -> str:
  '''...new from_addr param threaded into _render_footer_email.'''
  # ...
  footer = _render_footer_email(state, now, from_addr=from_addr)
  # ...


def _render_footer_email(state, now, from_addr: str) -> str:
  '''Section 7: footer disclaimer + sender + run-date.
  Phase 12: from_addr param replaces module-level _EMAIL_FROM.'''
  # ... use html.escape(from_addr, quote=True) ...
```

**Alternative considered (rejected):** Read env var inside `_render_footer_email` directly. Rejected because it (a) couples a pure renderer to the environment, (b) makes TestGoldenEmail harder to reason about (env read hidden deep in call tree), and (c) D-15 says the read goes in `_post_to_resend` or its caller — `_render_footer_email` is NOT a caller of `_post_to_resend`.

**Which `TestGoldenEmail` tests change shape:** Currently `compose_email_body(state, old_signals, FROZEN_NOW)` — after refactor: `compose_email_body(state, old_signals, FROZEN_NOW, from_addr='signals@carbonbookkeeping.com.au')` (explicit param) OR use a default arg that matches the golden-embedded string. **Recommend: make `from_addr` a KEYWORD-ONLY arg with NO default** and update all three TestGoldenEmail tests to pass the fixture value explicitly. This makes the contract loud and prevents silent default-drift if the golden is regenerated with a different sender.

### Anti-Patterns to Avoid

- **Hand-writing the port-80 redirect block in `nginx/signals.conf`.** Certbot's `--nginx` plugin expects to inject this. A pre-existing port-80 block leads to "Certbot: The existing server block should not have a redirect" prompts or duplicate `return 301` directives. Let certbot own it.

- **Applying HSTS `add_header` inside a location block.** nginx's inheritance rule for `add_header` is "replace, not extend" — a single `add_header` in a `location` block nukes ALL parent-context `add_header` lines. Put HSTS + security headers at the `server` scope only. `[CITED: getpagespeed.com nginx-hsts]`

- **Rate-limiting `/.well-known/acme-challenge/`.** 10 r/m would break ACME renewal on a server with >10 challenges/minute (unlikely but possible during multi-domain setups). Carve out with a no-`limit_req` nested location. Even for a single cert, belt-and-braces prevents future headache.

- **Running `sudo certbot` on production before `--dry-run`.** Let's Encrypt's rate limit is **5 duplicate certificates per exact identifier set per 7 days** — not "5 attempts", FIVE ISSUANCES. A misconfigured first run can burn a week of retries. Always `certbot --nginx --dry-run -d signals.<owned-domain>.com` first. `[CITED: https://letsencrypt.org/docs/rate-limits/]`

- **Wildcards in sudoers paths.** `NOPASSWD: /usr/sbin/nginx *` lets `trader` run `nginx -s stop && rm -rf /`. Use absolute paths with fixed arguments only. Phase 11 already does this correctly for `/usr/bin/systemctl restart trading-signals[-web]`. Phase 12 extends with the same discipline. `[CITED: https://blog.compass-security.com/2012/10/dangerous-sudoers-entries-part-4-wildcards/]`

- **Reading `SIGNALS_EMAIL_FROM` at module import time.** Tests using `monkeypatch.setenv` AFTER import won't see the new value if the read happens at import. D-15 locks per-send read. This is the same pattern notifier.py:1417 already uses for `RESEND_API_KEY`.

- **Leaving `_EMAIL_FROM = '...'` commented-out.** D-16 says remove entirely. Commented-out constants drift — future refactors may re-enable or grep-confuse.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| TLS termination | Python SSL context in uvicorn | nginx + Let's Encrypt | uvicorn's SSL mode works but has NO cert renewal, NO OCSP stapling, NO modern cipher curation. Every production Python-web setup terminates TLS at the reverse proxy. |
| HTTPS certificate issuance | Hand-rolled ACME client | certbot | EFF-maintained, handles renewal, rate-limit-aware, auto-enabled systemd timer |
| HTTP→HTTPS redirect | FastAPI middleware | nginx 80-block with `return 301 https://$host$request_uri;` | Cheaper (no Python request cycle), handles before app bootstraps |
| HSTS header | FastAPI middleware response header | nginx `add_header Strict-Transport-Security ... always;` | Same response path for ALL endpoints (including errors); survives FastAPI crashes |
| /healthz rate limit | FastAPI `slowapi` or custom counter | nginx `limit_req_zone` + `limit_req` | Edge-level = cheaper + faster; Python rate limiters need shared state across workers |
| Cert renewal cron | Hand-rolled crontab + shell script | certbot.timer + `/etc/letsencrypt/renewal-hooks/deploy/*.sh` | certbot manages renewal window, retries, rate-limit backoff, and logging |
| Env-var-missing warning propagation | Module-global warning list | `state_manager.append_warning` (Phase 3 sole-writer API) | D-14 explicitly routes through existing Phase 8 warning-plumbing |

**Key insight:** Every anti-pattern item in the "Don't Build" column is a path that looks shorter but has zero ecosystem backing. In a signal-only app with one operator, the cost of reinventing TLS rotation or ACME is not just time — it's the debugging cost the first time it fails and there's nobody to turn to but you.

## Runtime State Inventory

*This is a refactor/wiring phase — includes rename of `_EMAIL_FROM` hardcoded string to env-var-driven read. Inventory applies.*

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | **tests/fixtures/notifier/golden_with_change.html**, **golden_no_change.html**, **golden_empty.html** all contain the literal string `signals@carbonbookkeeping.com.au` rendered into the email footer (by `_render_footer_email`). Verified via `grep -l 'carbonbookkeeping' tests/fixtures/notifier/*.html`. | **Data migration (regeneration)** required AFTER refactor lands. Plan must include a task to run `.venv/bin/python tests/regenerate_notifier_golden.py` with `SIGNALS_EMAIL_FROM=signals@carbonbookkeeping.com.au` exported (or set via fixture), THEN git-add the regenerated HTMLs in the same commit as the notifier code change. Goldens must stay byte-equal to committed after regeneration (D-03 Phase 6 byte-stability gate). |
| Live service config | **Droplet `/etc/trading-signals/.env`** (or wherever Phase 11 systemd unit reads) — NEW var `SIGNALS_EMAIL_FROM=signals@carbonbookkeeping.com.au` must be added. Currently ABSENT — the refactor + the `.env` line must land in the same operator deploy window, else `_dispatch_email_and_maintain_warnings` will produce a "missing_sender" warning on first post-Phase-12 run. **Resend service config (DNS records)** — operator-confirmed ALREADY DONE per D-04; no action. | Operator adds one line to droplet `.env` during SETUP-HTTPS.md Step 7. Documented in runbook. |
| OS-registered state | **certbot.timer** — becomes active on the droplet after `apt install certbot`. Auto-enabled by Ubuntu packaging. `[CITED: https://certbot.eff.org/instructions]` **nginx systemd unit** — installed by `apt install nginx`; starts automatically. **No renaming of existing OS-registered items** — Phase 12 adds NEW OS-state (nginx + certbot.timer), doesn't rename Phase 10/11 state. | Operator runs `systemctl enable --now certbot.timer` defensively in SETUP-HTTPS.md Step 6 even though Ubuntu's packaging enables it at install time (belt-and-braces for edge cases where the enable lookup fails during first-install race). |
| Secrets/env vars | `SIGNALS_EMAIL_FROM` is a new env var name; code only reads it from `os.environ`. No key rotation — it's a sender address, not a credential. `RESEND_API_KEY` unchanged. `SIGNALS_EMAIL_TO` + `_EMAIL_TO_FALLBACK` unchanged (Phase 6 D-14 recipient logic stays). | None — new env var is read by code via standard `os.environ.get`. Rename of `_EMAIL_FROM` (module constant) to `SIGNALS_EMAIL_FROM` (env var) is a code change, not a credential rotation. |
| Build artifacts | None — Phase 12 does not add or rename installed Python packages. No `pip install -e .` artifacts to refresh. No compiled binaries. nginx and certbot are managed by apt. | None. |

**Canonical verification question:** *After the refactor commits and the nginx/signals.conf lands, what runtime systems still reference `signals@carbonbookkeeping.com.au` as a literal string?*

Answer:
- The 3 golden HTMLs (code path: `_render_footer_email` rendered it). **MUST be regenerated with the fixture env value in the same commit as the code change.**
- The droplet `.env` file (as the value of `SIGNALS_EMAIL_FROM=...`). **Operator-owned, not in git.**
- Resend dashboard's verified senders list — unchanged; operator keeps the verified sender the same value.

Nothing else. `grep -r 'carbonbookkeeping' --include='*.py' --include='*.conf' --include='*.md' --include='*.txt'` should return ZERO hits (except this RESEARCH.md, the CONTEXT.md, and other docs) after the refactor. Plan can include an optional verification step for this.

## Common Pitfalls

### Pitfall 1: certbot auto-inserts redirect when server block looks HTTP-only
**What goes wrong:** If the committed `nginx/signals.conf` has `listen 80` in the 443 block (accidental dual-listen), certbot misreads it as an HTTP-only server and offers to "add HTTPS to this server". Output is a tangled config with duplicate ssl_certificate lines.
**Why it happens:** Certbot's nginx plugin heuristic keys on `listen` directives to decide "is this the HTTP or HTTPS server". A block with both `listen 80` and `listen 443 ssl` confuses it.
**How to avoid:** Commit the 443 block with ONLY `listen 443 ssl;` + `listen [::]:443 ssl;`. No `listen 80` line. Certbot handles the 80-block itself.
**Warning signs:** `nginx -t` after certbot warns "conflicting server name" or "duplicate listen options"; or the file has two `ssl_certificate` lines after one certbot run.

### Pitfall 2: HSTS emitted on HTTP before redirect happens
**What goes wrong:** If HSTS is configured in a shared context that applies to port 80, browsers receive the HSTS header over plaintext HTTP. Browsers actually ignore HSTS from HTTP (per RFC 6797), but intermediate proxies or misconfigured CDNs may cache it, leading to "upgrade to HTTPS" persistence even from non-secure origins.
**Why it happens:** Operators put `add_header Strict-Transport-Security ...` at `http { }` scope or inside the port-80 server block.
**How to avoid:** HSTS `add_header` lives ONLY inside the `server { listen 443 ssl; }` block. Port-80 block has NO HSTS — it just redirects.
**Warning signs:** `curl -I http://signals.<owned-domain>.com/healthz` returns a Strict-Transport-Security header (it should NOT — only the HTTPS response should).

### Pitfall 3: `add_header` child-location clobbers parent HSTS
**What goes wrong:** Adding ANY `add_header` in a `location` block silently removes all parent-scope `add_header` directives (HSTS, XCTO, etc.) for requests handled by that location.
**Why it happens:** nginx's `add_header` inheritance is "replace, not merge" — documented behavior. If a future plan adds `add_header Cache-Control 'no-store'` to `location = /api/state`, HSTS vanishes from that path.
**How to avoid:** Either (a) keep all `add_header` at `server` scope and never add any in `location` blocks, OR (b) when a location block needs its own header, redeclare ALL security headers inside it, OR (c) use the third-party `headers-more-nginx-module` (`more_set_headers` has additive semantics). `[CITED: getpagespeed.com nginx-hsts]`
**Warning signs:** Response from `/healthz` (which does have a location block in our config) lacks HSTS. Since Phase 12's location blocks don't add response headers themselves, we're safe BY DEFAULT — but Phase 13+ plans must be briefed on this trap.

### Pitfall 4: Let's Encrypt duplicate-cert rate limit burns a whole week
**What goes wrong:** Operator runs `certbot --nginx` five times in rapid succession during setup troubleshooting. Each successful run issues a fresh cert; the 6th hits the "5 duplicate certificates per exact set of identifiers per 168 hours" limit. Operator must wait 168 hours or switch domains.
**Why it happens:** Typos in `-d` flag, DNS propagation stuttering, nginx config errors between attempts, re-runs after `systemctl restart nginx` weirdness.
**How to avoid:** (a) Run `certbot --nginx --dry-run` first — uses staging API, counts zero against production limit. (b) If production fails, fix root cause BEFORE re-running production. (c) For extended iteration, use `--staging` flag; staging certs are invalid but cert issuance path is testable. `[CITED: https://letsencrypt.org/docs/rate-limits/]`
**Warning signs:** `certbot --nginx` reports "too many certificates already issued for exact set of domains". SETUP-HTTPS.md §Troubleshooting MUST call this out.

### Pitfall 5: nginx rate-limit zone full → 503 instead of serving request
**What goes wrong:** The `zone=healthz:10m` zone fills (unlikely at 10MB ≈ 80,000 IPs at 128 bytes each on 64-bit; needs a botnet or DDoS), and nginx starts evicting LRU entries. If eviction can't complete fast enough, new requests fail with 503 `limit_req_status`.
**Why it happens:** Under real DDoS or misconfigured `$binary_remote_addr` behind a proxy that hides client IPs (all requests collapse to one key).
**How to avoid:** 10MB is ~80,000 IP states on 64-bit per [nginx docs](http://nginx.org/en/docs/http/ngx_http_limit_req_module.html) — vast overkill for a single-operator v1.1 app. Single-operator + a handful of status-page pollers should see <50 unique IPs. No action needed; this is documented for future reference when Phase 14+ considers mutation endpoints.
**Warning signs:** nginx error log entries like `limiting requests, excess: 10.000 by zone "healthz"`. Routine at real load; alarming at development-time load.

### Pitfall 6: `certbot --nginx` without proper DNS resolves to wrong IP
**What goes wrong:** Operator purchases domain, points A-record at droplet IP, but DNS hasn't propagated yet when running certbot. HTTP-01 challenge reaches the wrong server (or nobody), issuance fails, burns a rate-limit slot.
**Why it happens:** DNS TTLs, registrar lag, resolver cache.
**How to avoid:** SETUP-HTTPS.md §Prerequisites tells operator to verify `dig +short signals.<owned-domain>.com` returns droplet IP from multiple resolvers (e.g., `dig @1.1.1.1 ...; dig @8.8.8.8 ...`) BEFORE running certbot. Use `--dry-run` as belt-and-braces.
**Warning signs:** certbot error "DNS problem: NXDOMAIN looking up A for signals..." or "Detail: Fetching http://signals.../.well-known/acme-challenge/... Timeout during connect".

### Pitfall 7: sudoers miss → deploy.sh fails every deploy
**What goes wrong:** Operator extends sudoers per D-20 but typos the path (e.g., `/usr/bin/nginx -t` when Ubuntu ships at `/usr/sbin/nginx -t`). `sudo -n nginx -t` fails fast with "sudo: a password is required". deploy.sh exits non-zero on every run.
**Why it happens:** Debian/Ubuntu installs nginx to `/usr/sbin` (admin binary); operator assumes `/usr/bin` by habit.
**How to avoid:** SETUP-HTTPS.md §Step 8 says `which nginx` FIRST, then paste the exact path into the sudoers rule. Also document a verification step `sudo -n nginx -t` BEFORE running deploy.sh — same pattern as Phase 11 D-21 HIGH #4 for systemctl.
**Warning signs:** `sudo -n nginx -t` prints "sudo: a password is required" or `sudo: a terminal is required to read the password`.

### Pitfall 8: Removing `_EMAIL_FROM` breaks `_render_footer_email`
**What goes wrong:** Plan drops line 99 per D-16, but doesn't update line 1147 (`html.escape(_EMAIL_FROM, quote=True)` inside `_render_footer_email`). ImportError at module load time because `_EMAIL_FROM` is referenced but not defined. Tests crash.
**Why it happens:** D-14/D-15 only mentions line 1427 and the `_post_to_resend` caller — line 1147 in the HTML body renderer is EASY TO MISS. Verified in §6 code-context scan: the constant has THREE usage sites, not two.
**How to avoid:** Plan explicitly includes a task step "grep `_EMAIL_FROM` in notifier.py after edit — must return 0 hits" as a verification gate. Thread `from_addr` through `compose_email_body` into `_render_footer_email` (see Pattern 2 above).
**Warning signs:** `pytest tests/test_notifier.py -x` fails at collection time with `NameError: name '_EMAIL_FROM' is not defined`.

### Pitfall 9: TestGoldenEmail doesn't fail at D-19 fixture setup, but golden content drifts
**What goes wrong:** Plan adds `@pytest.fixture(autouse=True)` that sets `SIGNALS_EMAIL_FROM=signals@carbonbookkeeping.com.au` — golden tests PASS on the first run. But the underlying HTML content has drifted because `_render_footer_email` now interpolates the env-var value instead of the constant. If the goldens weren't regenerated, they'll still compare equal ONLY IF the fixture env-var value exactly matches what was hardcoded before. Any fixture-value typo silently fails.
**Why it happens:** Goldens and fixtures are parallel truths; drift between them is not caught until one side changes.
**How to avoid:** Plan task sequence — (1) refactor notifier.py, (2) run `tests/regenerate_notifier_golden.py` with fixture-value env set, (3) diff the goldens (should show ZERO changes — because the refactored renderer with the fixture value should produce the SAME bytes as the old hardcoded renderer), (4) commit goldens (possibly unchanged) with the code change. If the diff is non-zero, it means either (a) the renderer has a logic change (planner investigates) or (b) the fixture env-value drifted from the committed golden's hardcoded value.
**Warning signs:** `git diff tests/fixtures/notifier/` shows changed HTML after regeneration. Planner must investigate WHY — this is a signal of either an intentional behavior change (escape it via plan acceptance criteria) or a bug.

## Code Examples

### Example 1: Reading SIGNALS_EMAIL_FROM with early exit

```python
# notifier.py send_daily_email (INFRA-01 refactor) — pseudocode for planner
# Source: adaptation of notifier.py:1417 RESEND_API_KEY pattern + D-14 spec

def send_daily_email(
  state: dict,
  old_signals: dict,
  now: datetime,
  is_test: bool = False,
) -> SendStatus:
  '''...'''
  # D-15: per-send read (NOT at import time) — enables monkeypatch testing
  from_addr = os.environ.get('SIGNALS_EMAIL_FROM', '').strip()
  if not from_addr:
    # D-14: log + return early; orchestrator translates ok=False into
    # state_manager.append_warning per Phase 8 D-08.
    logger.error('[Email] SIGNALS_EMAIL_FROM not set — email skipped')
    return SendStatus(ok=False, reason='missing_sender')

  has_critical = _has_critical_banner(state)
  subject = compose_email_subject(
    state, old_signals,
    is_test=is_test, has_critical_banner=has_critical,
  )
  try:
    html_body = compose_email_body(
      state, old_signals, now, from_addr=from_addr,  # NEW kwarg
    )
  except Exception as e:
    logger.warning(
      '[Email] WARN compose_email_body failed: %s: %s',
      type(e).__name__, e,
    )
    return SendStatus(
      ok=False,
      reason=f'compose_body_failed: {type(e).__name__}: {e}'[:200],
    )

  # ... last_email.html write + RESEND_API_KEY check unchanged ...

  to_addr = os.environ.get('SIGNALS_EMAIL_TO', _EMAIL_TO_FALLBACK)
  try:
    _post_to_resend(api_key, from_addr, to_addr, subject, html_body)
    # ^^ third arg goes from _EMAIL_FROM → from_addr (parameter)
    logger.info('[Email] sent to %s subject=%r', to_addr, subject)
    return SendStatus(ok=True, reason=None)
  # ... except ResendError / Exception blocks unchanged ...
```

**Note for planner:** D-14 locks `reason='missing_sender'` (verbatim); do NOT drift to `'no_from_addr'` or similar. The `SendStatus.reason` field is consumed by the orchestrator's `_dispatch_email_and_maintain_warnings` (main.py:533) to build the warning message string.

**D-14 locks `attempts=0` in the `SendStatus` return.** Current `SendStatus` NamedTuple at notifier.py:84 is `(ok, reason)` — only 2 fields; no `attempts` field exists. Either (a) D-14's `attempts=0` is wishful (planner should use `SendStatus(ok=False, reason='missing_sender')` as the 2-field tuple) OR (b) the refactor extends SendStatus to a 3-tuple. Recommend (a) — extending a NamedTuple used across Phase 8 orchestrator code is scope-creep; D-14 can be interpreted as "zero Resend attempts happened" which is inherent in the return path. **PLANNER: confirm with operator or default to 2-field SendStatus.** `[ASSUMED]`

### Example 2: autouse class-scoped fixture for TestGoldenEmail

```python
# tests/test_notifier.py — class-scoped autouse fixture pattern (D-19)
# Source: pytest monkeypatch docs + project convention (tests/test_notifier.py)

class TestGoldenEmail:
  '''...existing docstring...'''

  @pytest.fixture(autouse=True)
  def _stable_from_addr(self, monkeypatch):
    '''Phase 12 D-19: pin SIGNALS_EMAIL_FROM to the golden-committed sender
    so TestGoldenEmail stays byte-equal across env configurations.
    autouse=True applies to every test in this class; function-scope means
    each test gets a fresh env mutation (matches pytest default).'''
    monkeypatch.setenv('SIGNALS_EMAIL_FROM', 'signals@carbonbookkeeping.com.au')

  def test_golden_with_change_matches_committed(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    old_signals = {'^AXJO': 1, 'AUDUSD=X': 0}
    # compose_email_body now reads from_addr kwarg; pass it explicitly
    # OR rely on default if planner chose a default path.
    rendered = compose_email_body(
      state, old_signals, FROZEN_NOW,
      from_addr='signals@carbonbookkeeping.com.au',  # explicit — matches env
    )
    golden = GOLDEN_WITH_CHANGE_PATH.read_text(encoding='utf-8')
    assert rendered == golden, ...
```

**Why autouse + explicit pass:** Belt-and-braces. The autouse fixture guards against any code path that does read `os.environ.get('SIGNALS_EMAIL_FROM')` inside the composer (if planner takes a different refactor shape). The explicit kwarg makes the test intent obvious and fails LOUDLY on signature drift.

### Example 3: TestEmailFromEnvVar class (D-17) — 3 tests

```python
# tests/test_notifier.py — new test class (D-17)
# Source: mirror of TestSendDispatch patterns at tests/test_notifier.py:1056+

class TestEmailFromEnvVar:
  '''Phase 12 INFRA-01 + D-17 — SIGNALS_EMAIL_FROM env-var contract.

  D-14: missing/empty → log ERROR + return SendStatus(ok=False,
        reason='missing_sender'); NO Resend POST.
  D-15: per-send read inside send_daily_email (or its wrapper).
  D-16: _EMAIL_FROM module constant removed.
  '''

  def test_from_addr_reads_env_var(self, tmp_path, monkeypatch) -> None:
    '''SIGNALS_EMAIL_FROM present → Resend payload `from` field matches.'''
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('SIGNALS_EMAIL_FROM', 'test@example.com')
    monkeypatch.setenv('RESEND_API_KEY', 'test_key')

    captured_payload: dict = {}
    def _fake_post(url, **kwargs):
      captured_payload.update(kwargs.get('json', {}))
      class _R:
        status_code = 200
        text = '{"id":"abc"}'
        def raise_for_status(self): pass
      return _R()
    monkeypatch.setattr('notifier.requests.post', _fake_post)

    state = _build_phase8_base_state()  # existing helper at test_notifier.py:1351
    old_signals = {'^AXJO': 0, 'AUDUSD=X': 0}
    status = send_daily_email(state, old_signals, FROZEN_NOW)
    assert status.ok is True
    assert captured_payload.get('from') == 'test@example.com'

  def test_missing_env_var_skips_email_with_warning(
      self, tmp_path, monkeypatch, caplog) -> None:
    '''SIGNALS_EMAIL_FROM unset → log ERROR + SendStatus(ok=False,
    reason='missing_sender'); Resend.post NOT called.'''
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('SIGNALS_EMAIL_FROM', raising=False)
    monkeypatch.setenv('RESEND_API_KEY', 'test_key')  # ensure it's not the RESEND path

    called = {'n': 0}
    def _fake_post(*a, **kw):
      called['n'] += 1
      raise AssertionError('should not be called when SIGNALS_EMAIL_FROM missing')
    monkeypatch.setattr('notifier.requests.post', _fake_post)

    state = _build_phase8_base_state()
    old_signals = {'^AXJO': 0, 'AUDUSD=X': 0}
    with caplog.at_level(logging.ERROR, logger='notifier'):
      status = send_daily_email(state, old_signals, FROZEN_NOW)
    assert status.ok is False
    assert status.reason == 'missing_sender'
    assert called['n'] == 0
    assert '[Email] SIGNALS_EMAIL_FROM not set' in caplog.text

  def test_empty_env_var_treated_as_missing(
      self, tmp_path, monkeypatch, caplog) -> None:
    '''SIGNALS_EMAIL_FROM='' (empty string) → same path as missing.'''
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('SIGNALS_EMAIL_FROM', '')
    monkeypatch.setenv('RESEND_API_KEY', 'test_key')

    called = {'n': 0}
    def _fake_post(*a, **kw):
      called['n'] += 1
    monkeypatch.setattr('notifier.requests.post', _fake_post)

    state = _build_phase8_base_state()
    old_signals = {'^AXJO': 0, 'AUDUSD=X': 0}
    with caplog.at_level(logging.ERROR, logger='notifier'):
      status = send_daily_email(state, old_signals, FROZEN_NOW)
    assert status.ok is False
    assert status.reason == 'missing_sender'
    assert called['n'] == 0
    assert '[Email] SIGNALS_EMAIL_FROM not set' in caplog.text
```

### Example 4: deploy.sh nginx reload hook (D-20)

```bash
# deploy.sh — append AFTER existing Phase 11 retry-loop smoke test,
# BEFORE the final success echo. Gated on nginx install + signals.conf presence.

# D-20 (Phase 12): nginx config test + reload hook, gated.
# Pre-Phase-12 droplets (no nginx installed) skip this silently.
if [ -f nginx/signals.conf ] && command -v nginx &>/dev/null; then
  echo "[deploy] nginx config detected — testing + reloading..."
  sudo -n nginx -t
  sudo -n systemctl reload nginx
  echo "[deploy] nginx reloaded"
fi

# D-23 step 8: success (unchanged)
COMMIT=$(git rev-parse --short HEAD)
echo "[deploy] deploy complete. commit=${COMMIT}"
```

### Example 5: Sudoers entry extension (SETUP-HTTPS.md Step 8)

Phase 11 has this in `/etc/sudoers.d/trading-signals-deploy`:
```
trader ALL=(root) NOPASSWD: /usr/bin/systemctl restart trading-signals, /usr/bin/systemctl restart trading-signals-web
```

Phase 12 extends to (single line, four comma-separated commands):
```
trader ALL=(root) NOPASSWD: /usr/bin/systemctl restart trading-signals, /usr/bin/systemctl restart trading-signals-web, /usr/sbin/nginx -t, /usr/bin/systemctl reload nginx
```

**Absolute-path verification during SETUP-HTTPS.md Step 8:**
```bash
which nginx            # EXPECT: /usr/sbin/nginx (Ubuntu default)
which systemctl        # EXPECT: /usr/bin/systemctl
```

If either returns a different path, substitute in the sudoers line BEFORE `visudo -c -f`.

**Verification step (post sudoers save):**
```bash
sudo -n nginx -t
# Expected: silent success (0 exit code) OR 'nginx: the configuration ...
# is successful' on stderr. Must NOT prompt for password.

sudo -n systemctl reload nginx
# Expected: silent success OR 'Job for nginx.service failed' if syntax error.
# Must NOT prompt for password.
```

**Anti-pattern WARNING (mirrors Phase 11 D-21):** NEVER use `NOPASSWD: ALL` or `NOPASSWD: /usr/sbin/nginx *` (wildcard). Wildcards in sudo paths are a documented privilege-escalation vector. `[CITED: Compass Security blog 2012, still the canonical reference]`

### Example 6: SETUP-HTTPS.md section skeleton (D-21)

```markdown
# SETUP-HTTPS.md — Trading Signals HTTPS + domain one-time setup

**Phase:** 12 (HTTPS + Domain Wiring)
**Audience:** Operator (Marc), running once on the DigitalOcean droplet.
**Prerequisites (operator-owned, verify BEFORE starting):**
- Phase 11 SETUP-DROPLET.md completed (FastAPI on 127.0.0.1:8000)
- Domain purchased at registrar of choice (e.g., `carbonbookkeeping.com.au`)
- A-record `signals.<owned-domain>.com` → droplet IP, TTL 300s or lower
- DNS propagated — `dig @1.1.1.1 +short signals.<owned-domain>.com` and
  `dig @8.8.8.8 +short signals.<owned-domain>.com` both return droplet IP
- Resend domain already verified (operator confirmed — SPF/DKIM/DMARC live
  for `signals@<owned-domain>.com`). No Resend action in this runbook.
- Droplet firewall allows ports 80 + 443 inbound (`ufw status` shows both)

## 1 — Install nginx + certbot (one-time)
```bash
sudo apt update
sudo apt install -y nginx certbot python3-certbot-nginx
nginx -v
certbot --version
```

## 2 — Copy committed nginx config
```bash
sudo cp /home/trader/trading-signals/nginx/signals.conf \
        /etc/nginx/sites-available/signals.conf
```

## 3 — Substitute `<owned-domain>` placeholder
```bash
# Replace the literal <owned-domain> placeholder with your actual domain.
# Example for carbonbookkeeping.com.au:
sudo sed -i 's|<owned-domain>|carbonbookkeeping|g' \
  /etc/nginx/sites-available/signals.conf

# Symlink into sites-enabled
sudo ln -s /etc/nginx/sites-available/signals.conf /etc/nginx/sites-enabled/

# Verify syntax BEFORE certbot
sudo nginx -t
sudo systemctl reload nginx
```

## 4 — Run certbot (HTTPS issuance + auto-patch)
```bash
# Dry-run FIRST to verify everything works without burning rate-limit slots
sudo certbot --nginx --dry-run -d signals.<owned-domain>.com

# Real issuance
sudo certbot --nginx -d signals.<owned-domain>.com
# Answer interactive prompts:
#   - email for renewal notifications
#   - Terms of Service agreement
#   - EFF newsletter? (N)
#   - Redirect HTTP → HTTPS? (choose option 2: redirect)
```

## 5 — Verify HTTPS end-to-end (SC-1, SC-2)
```bash
# From your laptop:
curl -sI https://signals.<owned-domain>.com/healthz
# Expected: HTTP/2 200, Strict-Transport-Security: max-age=31536000; includeSubDomains

curl -sI http://signals.<owned-domain>.com/healthz
# Expected: HTTP/1.1 301 Moved Permanently, Location: https://...

# Verify cert chain
openssl s_client -connect signals.<owned-domain>.com:443 -servername signals.<owned-domain>.com </dev/null 2>/dev/null | openssl x509 -noout -issuer
# Expected: issuer=C = US, O = Let's Encrypt, CN = R10 (or similar)
```

## 6 — Confirm certbot.timer (auto-renewal)
```bash
systemctl list-timers | grep certbot
# Expected: certbot.timer   active   ...

sudo certbot renew --dry-run
# Expected: Congratulations, all simulated renewals succeeded

# Create renewal deploy hook (reload nginx after successful renew)
sudo tee /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh > /dev/null <<'EOF'
#!/bin/sh
systemctl reload nginx
EOF
sudo chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
```

## 7 — Add SIGNALS_EMAIL_FROM to droplet .env (INFRA-01)
```bash
# Append (or create) the line:
echo 'SIGNALS_EMAIL_FROM=signals@carbonbookkeeping.com.au' | sudo tee -a /home/trader/trading-signals/.env

# Restart the signal service to pick up new env var
# (web service doesn't consume this env var — no restart needed)
sudo systemctl restart trading-signals

# Verify: force an email send
cd /home/trader/trading-signals
.venv/bin/python main.py --force-email
# Expected: email arrives from signals@carbonbookkeeping.com.au
```

## 8 — Extend sudoers for deploy.sh nginx reload (D-20)
```bash
which nginx      # Expect: /usr/sbin/nginx
which systemctl  # Expect: /usr/bin/systemctl

sudo visudo -f /etc/sudoers.d/trading-signals-deploy
# Paste the exact extended line (4 comma-separated rules).
# See RESEARCH §Example 5 for exact line.

sudo chmod 440 /etc/sudoers.d/trading-signals-deploy
sudo chown root:root /etc/sudoers.d/trading-signals-deploy
sudo visudo -c -f /etc/sudoers.d/trading-signals-deploy
# Expected: parsed OK

# Verify passwordless
sudo -n nginx -t
sudo -n systemctl reload nginx
```

## 9 — Troubleshooting
(DNS propagation check with dig; Let's Encrypt rate-limit 5/week — use --dry-run and --staging; port 80 firewall blocks challenge — check ufw; nginx syntax errors; Resend quota; SIGNALS_EMAIL_FROM typo detection via log grep `[Email] SIGNALS_EMAIL_FROM not set`)

## 10 — Rollback
(Disable nginx config: `sudo rm /etc/nginx/sites-enabled/signals.conf; sudo systemctl reload nginx`; revert to Phase 11 localhost-only serving; SIGNALS_EMAIL_FROM unset reverts code to log+skip behavior)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Apache + mod_ssl | nginx + Let's Encrypt | Ubiquitous since ~2015 | nginx is the reverse-proxy default for Python/Go/Rust backends |
| Self-signed certs with long expiry | 90-day Let's Encrypt certs + auto-renewal | Let's Encrypt GA 2016 | Short-lived certs are now the security norm |
| Custom cron for cert renewal | `certbot.timer` | Ubuntu 20.04+ | No hand-rolled cron; packaging handles it |
| `ssl_protocols TLSv1 TLSv1.1 TLSv1.2` | `ssl_protocols TLSv1.2 TLSv1.3` | 2019-2020 industry-wide | TLS 1.0/1.1 formally deprecated by IETF RFC 8996 (March 2021) |
| `ssl_prefer_server_ciphers on` | `ssl_prefer_server_ciphers off` | Mozilla Intermediate 2021+ | TLS 1.3 ciphers are equally-strong-by-spec; client picks; off matches Mozilla guidance |
| Manual cron for systemd services | systemd timers (`.timer` units) | Systemd became Ubuntu default 15.04 | Native; journald integration |
| HSTS `max-age` 6 months | HSTS `max-age` 1-2 years | Best-practice drift 2020+ | 1 year = HSTS preload eligibility threshold; 31536000s in WEB-04 spec |

**Deprecated/outdated:**
- TLS 1.0, TLS 1.1 — do NOT include in `ssl_protocols`. IETF-deprecated.
- `ssl_session_tickets on` — session tickets are legacy; modern guidance is `off` per Mozilla.
- `ssl_prefer_server_ciphers on` with TLS 1.3 — no effect in TLS 1.3 (client picks); off is standard.
- DHE cipher suites without a custom `ssl_dhparam` — modern nginx (1.11+) uses secure built-in group; the GetPageSpeed 2026 hardening guide drops DHE entirely from its cipher list. Mozilla Intermediate keeps DHE for compat.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Ubuntu 22.04/24.04 ships nginx ≥ 1.18 and certbot ≥ 1.21 — meets Phase 12 minima | §Standard Stack | LOW — both are in Ubuntu stock; upgrade path is `apt upgrade` if a minor-version bug surfaces. Operator can check `nginx -v` and `certbot --version` during Step 1 of SETUP-HTTPS.md. |
| A2 | Certbot `--nginx` plugin behavior (inject cert paths, add 80-block, preserve HSTS) is stable between 1.21 (22.04) and 2.9 (24.04) | §Pattern 1 | MEDIUM — the EFF docs describe 2.x behavior. 1.21 plugin is older but still widely deployed. Mitigation: `certbot --dry-run` on 22.04 BEFORE production issuance. |
| A3 | D-14's `SendStatus(ok=False, reason='missing_sender', attempts=0)` — the `attempts=0` field does NOT match the current 2-field SendStatus NamedTuple at notifier.py:84. Planner should use 2-field SendStatus; extending the NamedTuple is scope-creep that touches Phase 8 orchestrator code. | §Code Examples Ex 1 | MEDIUM — plan will either (a) use 2-field SendStatus (reason string only, no attempts) or (b) extend SendStatus. Needs operator/planner decision. Flagged for `/gsd-discuss-phase` follow-up if operator cares about 3-field precision. |
| A4 | Goldens regenerated with `SIGNALS_EMAIL_FROM=signals@carbonbookkeeping.com.au` will be byte-equal to committed goldens (since the old code rendered the same string from `_EMAIL_FROM`) | §Runtime State Inventory / Pitfall 9 | LOW — only fails if the refactored `_render_footer_email` introduces other changes (e.g., call-site drift). Plan includes diff-check gate. |
| A5 | Operator's DNS registrar TTL allows A-record propagation within 30 min (acceptable SETUP-HTTPS.md window) | §Pitfall 6 | LOW — SETUP-HTTPS.md Prerequisites step requires `dig` verification before running certbot. Worst case: operator waits longer. |
| A6 | certbot.timer is enabled automatically on `apt install certbot`; running `systemctl enable --now certbot.timer` is belt-and-braces | §Standard Stack / Runtime Inventory | LOW — verified via EFF instructions + Let's Encrypt community threads. Defensive enable is idempotent. |
| A7 | `ssl_stapling_verify on` + `resolver 1.1.1.1 8.8.8.8 valid=300s;` is safe to put in the 443 block even before certbot injects the cert — nginx will silently fail-soft stapling until cert exists | §Pattern 1 | LOW — `ssl_stapling` is a soft feature; missing trusted cert just disables stapling, doesn't crash nginx. certbot injects `ssl_trusted_certificate` automatically. |

**Impact on planning:** Assumptions A3 is the highest-priority item for the planner/discuss-phase to verify with the operator. A1, A2, A6 are low-risk and operator-verifiable during SETUP-HTTPS.md. A4 is a plan-level gate. A5, A7 are documented pitfalls.

## Open Questions

1. **Should nginx OCSP stapling be enabled in Phase 12, or deferred?**
   - What we know: Mozilla Intermediate + current 2026 hardening guides recommend `ssl_stapling on; ssl_stapling_verify on; resolver ...` for performance + privacy (fewer client-initiated OCSP requests).
   - What's unclear: Adds complexity (resolver directive, cert chain requirements). Phase 12 is minimal viable HTTPS.
   - Recommendation: Include stapling in the committed config (operator gets "secure by default"). Troubleshooting note if stapling silently fails (nginx logs "ssl_stapling ignored"). Cheap to remove if it turns out to hurt.

2. **Should the renewal deploy hook be committed to git (as `nginx/reload-nginx.sh`) or created per-droplet?**
   - What we know: D-21 Step 6 says operator creates it during setup. Canonical-refs says "no repo code change needed".
   - What's unclear: Committing it in-repo would give drift-guard via a test; per-droplet creation means one more operator copy-paste step.
   - Recommendation: Leave it in SETUP-HTTPS.md (operator creates) per D-07. Script is 2 lines and has zero parameterization — drift risk is near-zero. Revisit if Phase 12+ adds complexity.

3. **Do we need a separate `nginx/options-ssl.conf` include, or put all TLS tuning in `signals.conf`?**
   - What we know: certbot often uses `include /etc/letsencrypt/options-ssl-nginx.conf;` pattern for portable SSL options.
   - What's unclear: Committing all TLS tuning in `nginx/signals.conf` (one file, one place) is cleaner for a single-cert single-domain setup.
   - Recommendation: One file. Phase 12 is single-cert; split-file adds complexity without benefit. Certbot's `options-ssl-nginx.conf` is a convenience for multi-cert deployments.

4. **What's the exact `SendStatus` shape after D-14?**
   - See Assumption A3. Planner/operator must confirm: does `SendStatus(ok=False, reason='missing_sender')` (2-field) suffice, or does D-14 really want a new `attempts` field?
   - Recommendation: Use 2-field unless operator explicitly wants to extend. Extending a NamedTuple used across Phase 8 `_dispatch_email_and_maintain_warnings` touches main.py and 2+ other tests — scope creep.

5. **Should `deploy.sh`'s nginx reload hook run BEFORE or AFTER the systemctl restart of FastAPI?**
   - What we know: D-20 places it after the existing restarts but before the commit echo. Order doesn't functionally matter (nginx + FastAPI are independent), but conceptually nginx-reload AFTER app-restart means "new code is already live, then new routing".
   - What's unclear: No fault either way.
   - Recommendation: Place nginx reload AFTER the FastAPI restart + smoke test pass (gated on smoke-test success via `set -euo pipefail`). Reason: if FastAPI restart fails, we've already aborted via `set -e`; no point reloading nginx.

## Environment Availability

| Dependency | Required By | Available (local dev) | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11 | notifier.py refactor tests | ✓ | 3.11.8 (pyenv) | — |
| fastapi, uvicorn, httpx, pytest | Phase 11 test suite (inherited) | ✓ | 0.136.1 / 0.46.0 / 0.28.1 | — |
| pytest-freezer | TDD time freezing | ✓ (installed) | — | — |
| bash | deploy.sh + tests/test_deploy_sh.py | ✓ (macOS) | 3.2.57 / 5.x | — |
| **nginx** | Phase 12 `nginx/signals.conf` config-test | ✗ (local dev — macOS) | — | Config validation via grep-style `tests/test_nginx_signals_conf.py` (pattern match, no shell-out). REAL `nginx -t` runs on droplet during SETUP-HTTPS.md Step 3. |
| **certbot** | Phase 12 cert issuance | ✗ (local dev) | — | Operator task on droplet; no local simulation. |
| **Ubuntu 22.04/24.04 droplet** | SC-1/SC-2/SC-3 operator verification | ✓ (operator-owned) | 22.04 or 24.04 LTS | — |
| **DNS propagation for `signals.<owned-domain>.com`** | HTTP-01 challenge | BLOCKED — operator hasn't purchased domain yet | — | Operator acquires during SETUP-HTTPS.md Prerequisites. Until then, Phase 12 code refactor work (INFRA-01) can proceed; SC-1/SC-2 verification is operator-gated. |
| **Resend API + verified domain** | INFRA-01 verification | ✓ (already done per D-04) | — | Operator confirmed `signals@carbonbookkeeping.com.au` verified. |

**Missing dependencies with no fallback:** None — nginx and certbot are droplet-side tools; local tests use grep-style config validation.

**Missing dependencies with fallback:** nginx config validation on local dev uses text-pattern matching in `tests/test_nginx_signals_conf.py` (mirror of Phase 11's `tests/test_deploy_sh.py` pattern). Real `nginx -t` is a droplet-side operator verification step documented in SETUP-HTTPS.md.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.3.3 (inherited from Phase 1 pin) |
| Config file | `pytest.ini` or `pyproject.toml` (no framework change this phase) |
| Quick run command | `.venv/bin/python -m pytest tests/test_notifier.py tests/test_deploy_sh.py tests/test_nginx_signals_conf.py -x -q` |
| Full suite command | `.venv/bin/python -m pytest tests/ -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| WEB-03 | nginx config contains ssl_protocols, ssl_ciphers, listen 443 ssl, proxy_pass to 127.0.0.1:8000 | unit (grep-style) | `pytest tests/test_nginx_signals_conf.py::TestNginxSignalsConfStructure -x` | ❌ Wave 0 (new file) |
| WEB-03 | nginx config contains `limit_req_zone ... zone=healthz:10m rate=10r/m` | unit (grep-style) | `pytest tests/test_nginx_signals_conf.py::TestRateLimit -x` | ❌ Wave 0 |
| WEB-03 | nginx config has `/.well-known/acme-challenge/` carve-out (no limit_req nested) | unit (grep-style) | `pytest tests/test_nginx_signals_conf.py::TestAcmeChallengeCarveOut -x` | ❌ Wave 0 |
| WEB-03 | certbot.timer enabled; cert renewable (dry-run) | manual (operator) | SETUP-HTTPS.md Step 6 `sudo certbot renew --dry-run` | N/A (operator) |
| WEB-04 | HSTS header exact value `max-age=31536000; includeSubDomains` in committed config | unit (grep-style) | `pytest tests/test_nginx_signals_conf.py::TestHSTS -x` | ❌ Wave 0 |
| WEB-04 | Port-80 redirect block is NOT in committed config (certbot-injected) — negative assertion | unit (grep-style) | `pytest tests/test_nginx_signals_conf.py::TestPortEightyBlockAbsent -x` | ❌ Wave 0 |
| WEB-04 | From droplet: HTTP → 301 to HTTPS; HTTPS response carries HSTS | manual (operator) | SETUP-HTTPS.md Step 5 `curl -sI` | N/A (operator) |
| INFRA-01 | SIGNALS_EMAIL_FROM set → Resend payload `from` field equals env value | unit (monkeypatch) | `pytest tests/test_notifier.py::TestEmailFromEnvVar::test_from_addr_reads_env_var -x` | ❌ Wave 1 (new class in existing file) |
| INFRA-01 | SIGNALS_EMAIL_FROM missing → log ERROR + SendStatus(ok=False, reason='missing_sender') + no Resend POST | unit (monkeypatch + caplog) | `pytest tests/test_notifier.py::TestEmailFromEnvVar::test_missing_env_var_skips_email_with_warning -x` | ❌ Wave 1 |
| INFRA-01 | SIGNALS_EMAIL_FROM='' (empty) → treated as missing | unit | `pytest tests/test_notifier.py::TestEmailFromEnvVar::test_empty_env_var_treated_as_missing -x` | ❌ Wave 1 |
| INFRA-01 | notifier.py has NO `_EMAIL_FROM = ` line (D-16 removed) | unit (grep) | `pytest tests/test_notifier.py::TestNotifierStructure::test_email_from_constant_removed -x` | ❌ Wave 1 (new or added to existing structure class) |
| INFRA-01 | Golden emails still byte-equal after refactor | unit (existing) | `pytest tests/test_notifier.py::TestGoldenEmail -x` | ✓ exists — autouse fixture added in D-19 |
| INFRA-01 | End-to-end email send with env var set uses verified domain sender | manual (operator) | SETUP-HTTPS.md Step 7 `python main.py --force-email` + Gmail "show original" | N/A (operator) |
| WEB-03 + INFRA-04 | deploy.sh has nginx reload hook AFTER systemctl restart AND gated on nginx presence | unit (grep-style + ordering) | `pytest tests/test_deploy_sh.py::TestDeployShSequence::test_nginx_reload_hook_present_and_gated -x` | ✓ exists (Phase 11 file) — extend with 2 new tests |
| WEB-03 | deploy.sh skips nginx reload when nginx/signals.conf absent (negative) | unit (text-pattern) | `pytest tests/test_deploy_sh.py::TestDeployShSequence::test_nginx_reload_is_gated_on_config_exists -x` | ✓ exists — extend |
| WEB-03 + INFRA-04 | SETUP-HTTPS.md has all 10 sections from D-21 | unit (file text) | `pytest tests/test_setup_https_doc.py::TestDocStructure -x` | ❌ Wave 2 (new file) |
| WEB-03 + INFRA-04 | SETUP-HTTPS.md sudoers line matches deploy.sh D-20 form (drift guard) | unit (cross-artifact) | `pytest tests/test_setup_https_doc.py::TestCrossArtifactDriftGuard::test_sudoers_form_matches_deploy_sh -x` | ❌ Wave 2 |

### Sampling Rate

- **Per task commit:** `.venv/bin/python -m pytest tests/test_notifier.py tests/test_deploy_sh.py tests/test_nginx_signals_conf.py tests/test_setup_https_doc.py -x -q` (only Phase 12 test files)
- **Per wave merge:** `.venv/bin/python -m pytest tests/ -q` (full suite; catches cross-phase regressions)
- **Phase gate (before /gsd-verify-work):** Full suite green + manual operator verification of SC-1/SC-2/SC-3 via SETUP-HTTPS.md curl steps

### Wave 0 Gaps

- [ ] `tests/test_nginx_signals_conf.py` — NEW test module covering:
  - TestNginxSignalsConfStructure (file exists, single `server` block listening 443 ssl, server_name contains `signals.<owned-domain>.com` literal)
  - TestTLSConfig (ssl_protocols TLSv1.2 TLSv1.3, ssl_prefer_server_ciphers off, ssl_session_cache shared:SSL:10m)
  - TestSecurityHeaders (HSTS exact value, XCTO nosniff, XFO DENY, Referrer-Policy strict-origin-when-cross-origin, all with `always` flag)
  - TestRateLimit (limit_req_zone healthz:10m rate=10r/m; limit_req zone=healthz burst=10 nodelay on /healthz location)
  - TestAcmeChallengeCarveOut (nested location /.well-known/acme-challenge/ with NO limit_req directive)
  - TestProxyPass (proxy_pass http://127.0.0.1:8000; Host, X-Real-IP, X-Forwarded-For, X-Forwarded-Proto headers)
  - TestPortEightyBlockAbsent (no `listen 80` in committed config — negative assertion)
  - TestOwnedDomainPlaceholder (`<owned-domain>` appears exactly N times as placeholder per D-01)

- [ ] `tests/test_setup_https_doc.py` — NEW test module covering (mirror of Phase 11 `tests/test_setup_droplet_doc.py`):
  - TestDocStructure (10 section headings present per D-21)
  - TestNginxInstall, TestCertbotInstall, TestOwnedDomainSubstitution, TestCertbotDryRun
  - TestSudoersExtension (4-rule sudoers line, absolute paths)
  - TestSignalsEmailFromEnvVar (echoed line with `SIGNALS_EMAIL_FROM=...`)
  - TestRenewalHook (/etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh content)
  - TestAntiPatternWarnings (no NOPASSWD: ALL, no wildcard paths)
  - TestCrossArtifactDriftGuard — sudoers line matches deploy.sh D-20 path strings; owned-domain placeholder matches nginx/signals.conf

- [ ] `tests/test_notifier.py::TestEmailFromEnvVar` — NEW class (3 tests per D-17)
- [ ] `tests/test_notifier.py::TestGoldenEmail` — add `@pytest.fixture(autouse=True)` per D-19
- [ ] `tests/test_deploy_sh.py` — extend TestDeployShSequence with 2 new tests:
  - `test_nginx_reload_hook_present_and_gated` (hook exists + `command -v nginx` gate)
  - `test_nginx_reload_is_gated_on_config_exists` (`[ -f nginx/signals.conf ]` gate)
  - `test_nginx_reload_after_systemctl_restart` (ordering — hook comes after Phase 11 restart block, before final success echo)

Framework install: none — pytest + monkeypatch already in place.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V1 Architecture | yes | Hex-lite boundary; notifier.py stays I/O-narrow (no subprocess, no git calls) |
| V2 Authentication | no | Phase 13 AUTH-01 introduces shared-secret; Phase 12 is pre-auth |
| V3 Session Management | no | No sessions in Phase 12 |
| V4 Access Control | **partial** | nginx `limit_req` on /healthz is the only access control (rate-limit, not authZ); Phase 13 adds real authZ |
| V5 Input Validation | no | /healthz takes no input; nginx config has no user-supplied data |
| V6 Cryptography | yes | TLS termination at nginx; Let's Encrypt cert management (never hand-roll certs) |
| V7 Error Handling | yes | `set -euo pipefail` in deploy.sh; never-crash notifier contract preserved |
| V8 Data Protection | partial | HSTS `includeSubDomains` protects subdomain cookies in future phases |
| V9 Communication | yes | HTTPS-only enforcement via HTTP→HTTPS redirect + HSTS |
| V10 Malicious Code | no | No external code execution paths introduced |
| V12 File & Resources | yes | nginx ProtectSystem-like isolation; sudoers tight-scoped paths |
| V14 Configuration | yes | Config committed to repo (`nginx/signals.conf`); drift tracked via PRs + tests |

### Known Threat Patterns for nginx + Let's Encrypt + Ubuntu stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| TLS downgrade attack (POODLE, BEAST) | Tampering | `ssl_protocols TLSv1.2 TLSv1.3;` excludes vulnerable protocols |
| Cipher downgrade | Tampering | Mozilla Intermediate cipher list; ECDHE-only (forward secrecy) |
| MITM on HTTP before HSTS | Tampering | HTTP→HTTPS 301 + HSTS on HTTPS response; first-visit TOFU gap is accepted (no preload per D-12) |
| DNS hijack → wrong cert issued | Tampering | Let's Encrypt HTTP-01 requires control of `signals.<owned-domain>.com`; A-record must be correct. Operator verifies via `dig` before certbot. |
| OCSP soft-fail leak | Info Disclosure | `ssl_stapling on; ssl_stapling_verify on;` — staple via server, no client OCSP leak |
| Let's Encrypt rate-limit burn | DoS | `--dry-run` staging first; pitfall called out in SETUP-HTTPS.md §Troubleshooting |
| DDoS on /healthz | DoS | `limit_req zone=healthz burst=10 nodelay` at nginx edge (cheaper than FastAPI middleware) |
| ACME challenge rate-limited → renewal fail | DoS (self) | Nested `location /.well-known/acme-challenge/` with NO limit_req |
| Sudo wildcard escalation | Elevation of Privilege | Absolute paths only in sudoers; no `*` or `NOPASSWD: ALL`; `visudo -c -f` validation |
| nginx `add_header` silent override | Info Disclosure | All security headers at server-scope; no location-scope `add_header` in Phase 12 (Phase 13 planners must be briefed) |
| HSTS over HTTP cached by intermediate | Tampering | HSTS directive ONLY in 443 server block; port-80 redirect block has no HSTS |
| env var `SIGNALS_EMAIL_FROM` spoofed by local attacker | Tampering | systemd `EnvironmentFile=-` scopes env to unit process; requires shell access as `trader` to modify; same threat model as Phase 11 |
| Resend API key leak via error body echo | Info Disclosure | Existing notifier.py Fix 1 redacts `api_key` via `.replace(api_key, '[REDACTED]')` — Phase 12 changes don't affect this |

**Phase 12 adds NO new secrets or tokens.** `SIGNALS_EMAIL_FROM` is a sender address, not a credential. The only new file containing secrets-adjacent data is `/home/trader/trading-signals/.env` (already Phase 11 convention) with `.env` remaining gitignored.

## Project Constraints (from CLAUDE.md)

Extracted actionable directives:

- **Code conventions**: 2-space indent, single quotes, snake_case functions, UPPER_SNAKE for constants
- **Log prefixes**: `[Email]` for notifier messages (INCLUDES the new `[Email] SIGNALS_EMAIL_FROM not set` line per D-14)
- **Architecture**: hex-lite — notifier.py stays I/O-narrow (HTTP + env-var read only; no subprocess, no git calls). AST blocklist enforced via `tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent`. Phase 12 adds NO new forbidden-module imports to notifier.py (os and requests already allowed); no guard update needed.
- **Dates**: ISO `YYYY-MM-DD`; times always AWST in user-facing output (SETUP-HTTPS.md verification `curl` examples note AWST where applicable)
- **Atomic writes**: state.json writes use tempfile+fsync+os.replace; unchanged by Phase 12 (no state.json mutation from email path)
- **Email never-crash**: sends NEVER crash the workflow — Resend failure is logged and skipped. D-14's new missing-env-var path PRESERVES this contract (log + SendStatus(ok=False) + return, no exception).
- **GSD workflow**: All code changes flow through a GSD phase — Phase 12 planning → execute-phase → verify → codemoot gate
- **Sender value**: `signals@carbonbookkeeping.com.au` is the operator's verified Resend sender — canonical value for `SIGNALS_EMAIL_FROM` in production and for golden-test fixtures

**Invariants preserved** (per CLAUDE.md + canonical-refs):
- Phase 8 W3 two-saves-per-run invariant — Phase 12's `append_warning` call for missing env var is the second save (orchestrator-managed), not a third
- notifier.py AST-forbidden imports unchanged
- 2-space indent enforced by tokenize-aware guard in `test_signal_engine.py::test_no_four_space_indent`
- Phase 11 `test_web_healthz.py` validates /healthz contract — nginx is TRANSPARENT to this test (test hits FastAPI directly in-process via TestClient)
- Phase 12 does NOT touch `systemd/trading-signals-web.service` (D-18 locks this)

## Sources

### Primary (HIGH confidence)
- [nginx `ngx_http_limit_req_module` official docs](http://nginx.org/en/docs/http/ngx_http_limit_req_module.html) — rate-limit zone memory cost (128 bytes/state on 64-bit), LRU eviction, burst/nodelay semantics, nested-location inheritance, `rate=10r/m` interpretation
- [Mozilla SSL Configuration Generator](https://ssl-config.mozilla.org/) — Intermediate profile TLS directives, cipher list, `ssl_prefer_server_ciphers off` rationale
- [EFF Certbot documentation for nginx](https://eff-certbot.readthedocs.io/en/stable/using.html#nginx) — `--nginx` plugin behavior, `--dry-run`, deploy-hooks directory
- [Let's Encrypt rate limits](https://letsencrypt.org/docs/rate-limits/) — 5 duplicate certs per 168 hours, staging environment
- **notifier.py** (direct code read, lines 48-100, 1135-1160, 1266-1522) — verified 3 usage sites for `_EMAIL_FROM`; confirmed the footer renderer (line 1147) is not covered by D-14/D-15 but IS covered by the data migration in §Runtime State Inventory
- **tests/test_notifier.py** (direct code read, lines 1-80, 1237-1345) — verified no existing `_EMAIL_FROM`/`from_addr`/`SIGNALS_EMAIL_FROM` references; `TestGoldenEmail` tests `compose_email_body` directly; `@pytest.fixture(autouse=True)` pattern feasible at class scope
- **tests/fixtures/notifier/golden_*.html** (grep `carbonbookkeeping`) — confirmed all 3 goldens embed the literal sender string; regeneration required
- **Phase 11 artifacts** (`11-CONTEXT.md`, `11-03-PLAN.md`, `11-04-PLAN.md`, `deploy.sh`, `SETUP-DROPLET.md`, `systemd/trading-signals-web.service`) — verified sudoers pattern, deploy.sh structure, `EnvironmentFile=-` optional prefix
- [Ubuntu packaging — certbot.timer auto-enable](https://certbot.eff.org/instructions?ws=other&os=ubuntufocal) — timer installed + enabled by apt package

### Secondary (MEDIUM confidence)
- [GetPageSpeed NGINX HSTS Complete Guide 2026](https://www.getpagespeed.com/server-setup/security/nginx-hsts) — `always` flag semantics, location-scope `add_header` inheritance pitfall, max-age progression
- [Let's Secure Me — NGINX SSL Hardening Checklist 2026](https://letsecure.me/nginx-ssl-hardening-checklist-2026/) — OCSP stapling resolver requirement, modern cipher list alignment with Mozilla Intermediate
- [GetPageSpeed NGINX Rate Limiting 2026](https://www.getpagespeed.com/server-setup/nginx/nginx-rate-limiting) — memory cost calculation for `$binary_remote_addr` zones
- [DigitalOcean: How To Secure Nginx with Let's Encrypt on Ubuntu 20.04](https://www.digitalocean.com/community/tutorials/how-to-secure-nginx-with-let-s-encrypt-on-ubuntu-20-04) — canonical workflow for `certbot --nginx` on Ubuntu
- [Compass Security: Dangerous Sudoers Entries Part 4 — Wildcards](https://blog.compass-security.com/2012/10/dangerous-sudoers-entries-part-4-wildcards/) — absolute path requirement for sudoers
- [Let's Encrypt Community — certbot/nginx clarifications](https://community.letsencrypt.org/t/certbot-nginx-clarifications/195019) — certbot plugin behavior on existing server blocks

### Tertiary (LOW confidence — flagged for operator validation during SETUP-HTTPS.md dry-run)
- Exact text of certbot's auto-injected port-80 redirect block (no definitive pre-2026 spec — behavior verified empirically by dry-run during operator setup)
- Exact certbot ≥ 2.x behavior diff vs 1.21 — rely on `--dry-run` for validation

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — nginx, certbot, python3-certbot-nginx all verified in Ubuntu package manifests; Python stack unchanged from Phase 11 (no new deps)
- Architecture: HIGH — hex-lite boundary unchanged; Phase 12 is additive (nginx edge) + refactor (notifier.py env var); no architectural shift
- Pitfalls: HIGH — 9 pitfalls all either directly verified by doc citation or derived from direct code reading (notifier.py 3-site `_EMAIL_FROM` usage; goldens embed string)
- TLS config: HIGH — Mozilla Intermediate + 2026 hardening guides corroborate
- certbot patch behavior: MEDIUM — documented broadly; exact line-level behavior flagged as A2 assumption, validatable via `--dry-run`
- SendStatus shape (D-14): MEDIUM — A3 assumption, requires operator/planner confirmation

**Research date:** 2026-04-24
**Valid until:** 2026-05-24 (nginx/certbot/Ubuntu stack is stable; Let's Encrypt rate limits are historically stable. TLS recommendations rev annually. Re-check if phase planning slips beyond 30 days.)
