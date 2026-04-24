# Phase 12: HTTPS + Domain Wiring — Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-24
**Phase:** 12-https-domain-wiring
**Areas discussed:** Domain + DNS plan, nginx + certbot install approach, Security headers + rate limiting, SIGNALS_EMAIL_FROM failure mode, Integration with existing infra

---

## Gray Area Selection

| Option | Description | Selected |
|--------|-------------|----------|
| Domain + DNS plan | Operator prereq; subdomain pattern; Cloudflare? Determines certbot challenge type + nginx shape. | ✓ |
| nginx + certbot install approach | HTTP-01 vs DNS-01; certbot-apt vs snap; config location; renewal hook. | ✓ |
| Security headers + rate limiting | HSTS locked; what else? Rate-limit /healthz pre-auth? HSTS preload? | ✓ |
| SIGNALS_EMAIL_FROM failure mode | Never-crash vs fail-loud on missing env var; where to read; remove hardcoded. | ✓ |

**User selected: all four** (plus integration tie-offs)

---

## Area 1 — Domain + DNS

### Q1: What's the domain situation?

| Option | Description | Selected |
|--------|-------------|----------|
| Real domain ready, use signals.<domain>.com (Recommended) | Domain purchased; A-record ready; plan uses subdomain + HTTP-01. | |
| Real domain ready, apex or different subdomain | Different subdomain or apex root; placeholder w/ operator substitution. | |
| No domain yet — placeholder only | Code changes land; operator acquires domain during SETUP-HTTPS.md. | ✓ |
| Domain behind Cloudflare proxy | Cloudflare CDN in front; forces DNS-01; X-Forwarded-For. | |

**User's choice:** No domain yet — placeholder only
**Notes:** Code lands with `<owned-domain>` placeholder; operator acquires + configures during runbook execution.

### Q2: Is Resend domain verification done?

| Option | Description | Selected |
|--------|-------------|----------|
| Already verified (Recommended if true) | `signals@carbonbookkeeping.com.au` already verified; INFRA-01 is pure refactor. | ✓ |
| Part of Phase 12 operator setup | SETUP-HTTPS.md includes Resend dashboard walkthrough. | |
| Different email provider | Not Resend; scope push-back. | |

**User's choice:** Already verified
**Notes:** INFRA-01 reduces to a code refactor — move `_EMAIL_FROM` hardcoded constant into an env var read. No new DNS/Resend work.

---

## Area 2 — nginx + certbot install

### Q1: Where does nginx config live?

| Option | Description | Selected |
|--------|-------------|----------|
| Committed to repo at nginx/signals.conf (Recommended) | Tracked in git with `<owned-domain>` placeholder; operator symlinks. Matches Phase 11 systemd pattern. | ✓ |
| Droplet-only (via SETUP-HTTPS.md copy-paste) | No repo file; docs-only. Simpler, lose history/tests. | |
| Template file + operator substitution | `nginx/signals.conf.template` with `__DOMAIN__`; sed/envsubst step. | |

**User's choice:** Committed to repo at nginx/signals.conf
**Notes:** Matches Phase 11 pattern (systemd unit committed to repo); enables a syntax-test via pytest.

### Q2: Certbot challenge type + install?

| Option | Description | Selected |
|--------|-------------|----------|
| HTTP-01 via certbot --nginx from apt (Recommended) | Standard on Ubuntu; auto-patches nginx config with cert + redirect + HSTS. | ✓ |
| HTTP-01 via certbot-auto standalone | Stop nginx → standalone → restart. Cleaner separation, brief downtime. | |
| DNS-01 via certbot-dns-<provider> | TXT-record validation; needs registrar API key. Only for CDN/blocked-80 cases. | |
| Custom nginx config (certbot only issues) | `certbot certonly --webroot`; we own nginx config entirely. More control, more surface. | |

**User's choice:** HTTP-01 via certbot --nginx plugin from apt
**Notes:** Industry standard; certbot handles the redirect injection automatically.

### Q3: Auto-renewal approach?

| Option | Description | Selected |
|--------|-------------|----------|
| certbot.timer systemd timer (Recommended) | Ubuntu default; runs twice daily; deploy-hook reloads nginx. Zero ops. | ✓ |
| Custom cron job | Manual cron entry equivalent to certbot.timer. | |
| Manual renewal | Operator runs `certbot renew` quarterly. Not recommended. | |

**User's choice:** certbot.timer default systemd timer
**Notes:** Ubuntu's apt package installs the timer automatically.

---

## Area 3 — Security headers + rate limiting

### Q1: Lock down /healthz at nginx now, or defer to Phase 13?

| Option | Description | Selected |
|--------|-------------|----------|
| Rate-limit /healthz at nginx now (Recommended) | `limit_req_zone` + burst=10 nodelay. Public but bounded. | ✓ |
| IP allowlist now, remove in Phase 13 | Home/office IP only; breaks status-page integrations; reverts later. | |
| Defer all access control to Phase 13 | Open /healthz until AUTH-01; 1-phase window of full public. | |

**User's choice:** Rate-limit /healthz at nginx now
**Notes:** Defense-in-depth before Phase 13 auth lands; keeps status-page integrations viable.

### Q2: Which security headers? (multi-select)

| Option | Description | Selected |
|--------|-------------|----------|
| X-Content-Type-Options: nosniff (Recommended) | Prevents MIME-sniffing attacks. | ✓ |
| X-Frame-Options: DENY (Recommended) | Clickjacking protection; future-proofs for dashboard in Phase 13. | ✓ |
| Referrer-Policy: strict-origin-when-cross-origin (Recommended) | Modern default; explicit is better. | ✓ |
| Content-Security-Policy (CSP) | Deferred — premature on JSON /healthz; revisit when Phase 13 HTML dashboard lands. | |

**User's choice:** All three recommended; CSP deferred
**Notes:** Three-header set is the standard modern baseline. CSP waits for WEB-05.

### Q3: HSTS preload?

| Option | Description | Selected |
|--------|-------------|----------|
| No preload; spec value as-is (Recommended) | Exact SC-2 value; no preload; reversible within 1-year max-age. | ✓ |
| Include preload + submit | Permanent commitment; removing requires Chrome team ask. | |

**User's choice:** No preload; spec value as-is
**Notes:** Keeps escape hatch open; revisit when every subdomain is HTTPS-committed forever.

---

## Area 4 — SIGNALS_EMAIL_FROM failure mode

### Q1: Behavior on missing/empty env var?

| Option | Description | Selected |
|--------|-------------|----------|
| Log ERROR + skip email + continue run (Recommended) | Never-crash contract preserved; mirrors RESEND_API_KEY handling. | ✓ |
| Fail the whole run (rc=2) | Hard config error; operator loses daily email; aggressive. | |
| Crash-email pattern with onboarding@resend.dev | Sends crash via test sender; violates SC-4 "never silently falls back" intent. | |

**User's choice:** Log ERROR + skip email + continue run
**Notes:** Appends warning via `state_manager.append_warning(source='notifier')`; next email surfaces the warning.

### Q2: Where does notifier.py read the env var?

| Option | Description | Selected |
|--------|-------------|----------|
| Per-send inside _build_resend_payload / _send_email_never_crash (Recommended) | `os.environ.get` per-call; testable via monkeypatch.setenv. | ✓ |
| Module-top constant (like current _EMAIL_FROM) | Read once at import; requires importlib.reload in tests. | |
| Constructor injection | Pass from_addr through call chain; over-engineered for 1 value. | |

**User's choice:** Per-send inside the helper
**Notes:** Matches how RESEND_API_KEY is read; enables per-test env isolation.

### Q3: Keep hardcoded signals@carbonbookkeeping.com.au?

| Option | Description | Selected |
|--------|-------------|----------|
| Remove hardcoded _EMAIL_FROM; env var mandatory (Recommended) | Delete line 99; env var is ONLY source; matches SC-4 intent. | ✓ |
| Keep as fixture default for tests only | _TEST_FALLBACK_FROM constant; dual-source confusion. | |
| Keep as production default | Contradicts SC-4. Don't pick. | |

**User's choice:** Remove hardcoded _EMAIL_FROM; env var mandatory
**Notes:** Tests use `monkeypatch.setenv` for golden-email fixture stability.

---

## Area 5 — Integration tie-offs (multi-select)

### Q1: Integration with existing Phase 11 infra

| Option | Description | Selected |
|--------|-------------|----------|
| Add SIGNALS_EMAIL_FROM to droplet .env file (Recommended) | EnvironmentFile=- already present; no systemd unit change. | ✓ |
| Update Phase 11 golden-email tests to monkeypatch SIGNALS_EMAIL_FROM (Recommended) | Required to avoid TestGoldenEmail failing with missing-env path; fixture pattern. | ✓ |
| deploy.sh needs nginx reload hook (Recommended) | `nginx -t && systemctl reload nginx` after systemctl restart; gated on nginx install. | ✓ |
| SETUP-HTTPS.md operator runbook (Recommended) | 10-section runbook analog to SETUP-DEPLOY-KEY.md + SETUP-DROPLET.md. | ✓ |

**User's choice:** All four
**Notes:** These are "small follow-on" items that keep Phase 11 infra in sync with Phase 12 changes.

---

## Claude's Discretion

- Exact nginx config body (ssl_protocols, cipher suites, Mozilla modern SSL)
- sudoers entry exact form (single file vs split; command path list)
- Which notifier helper reads the env var (D-15 locks "per-send" but not the exact function)
- Renewal hook script path

## Deferred Ideas

- Apex-domain support (v1.2)
- Cloudflare proxy / CDN (v1.2+)
- Full CSP header (Phase 13 with WEB-05 dashboard)
- HSTS preload submission (when all subdomains HTTPS-forever)
- IP allowlist on /healthz (rate-limit + auth covers v1.1)
- Status page integration (v1.2)
- Wildcard cert (when >1 subdomain)
- nginx caching of /healthz (low ROI)
- SIGNALS_EMAIL_FROM rotation procedure (docs-only)
- DMARC policy tightening (operator DNS task)
