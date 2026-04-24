---
phase: 12
slug: https-domain-wiring
status: verified
asvs_level: 1
threats_found: 6
threats_closed: 6
threats_open: 0
audit_date: 2026-04-25
created: 2026-04-25
---

# Phase 12 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail. Phase 12 lands HTTPS + domain wiring (nginx 443 edge, certbot/Let's Encrypt orchestration, deploy.sh nginx reload hook, SETUP-HTTPS.md operator runbook, INFRA-01 SIGNALS_EMAIL_FROM env-var refactor).

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Public Internet → nginx (port 443) | Untrusted client traffic crosses TLS boundary; nginx terminates and reverse-proxies to FastAPI | TLS-encrypted HTTP requests / responses |
| nginx → FastAPI (127.0.0.1:8000) | Intra-host proxy; FastAPI trusts Host / X-Forwarded-Proto headers from nginx | Plaintext HTTP on loopback |
| Let's Encrypt ACME → `/.well-known/acme-challenge/` | Periodic renewal traffic must reach nginx un-rate-limited | HTTP-01 challenge tokens |
| systemd `EnvironmentFile=-/home/trader/trading-signals/.env` → process env | Sender address arrives via dotenv; per-send `os.environ.get` read in notifier | `SIGNALS_EMAIL_FROM` env value |
| process env → notifier.py → Resend HTTPS API | Per-send read populates Resend payload `from` field | Sender address (not a credential) |
| trader-user `deploy.sh` → sudo (NOPASSWD, fixed-arg) | `sudo -n` invocations hit fixed sudoers rule; passwordless | 4 fixed-arg privileged commands only |
| Operator runbook (SETUP-HTTPS.md) ↔ committed code artifacts | Cross-artifact drift surface — doc must stay in sync with nginx/signals.conf, deploy.sh, notifier.py, systemd unit | Path / command / env-var literals |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-12-01 | Information Disclosure | TLS private key on disk (`/etc/letsencrypt/live/<domain>/privkey.pem`) | accept | OS-enforced mode 0600; committed `nginx/signals.conf` contains zero `ssl_certificate_key` references — certbot injects on first run. Regression gate: `tests/test_nginx_signals_conf.py::TestNginxConfForbiddenPatterns::test_no_ssl_certificate_key_line` (line 249). | closed |
| T-12-02 | Denial of Service | ACME renewal lockout via rate-limit | mitigate | `location /.well-known/acme-challenge/` carve-out with NO `limit_req` directive (`nginx/signals.conf:69-71`). nginx inheritance rule: child-level absence of `limit_req` disables rate-limit. Regression gate: `tests/test_nginx_signals_conf.py::TestNginxConfAcmeCarveout::test_acme_location_has_no_limit_req` (line 186). | closed |
| T-12-03 | Tampering / Information Disclosure | Silent fallback to `onboarding@resend.dev` if `SIGNALS_EMAIL_FROM` env var missing/empty | mitigate | D-14 implementation in `notifier.py:1411-1414` (`send_daily_email`) and `notifier.py:1525-1530` (`send_crash_email`): per-send `os.environ.get('SIGNALS_EMAIL_FROM', '').strip()`; missing/empty → `logger.error('[Email] SIGNALS_EMAIL_FROM not set …')` + `return SendStatus(ok=False, reason='missing_sender')` BEFORE `_post_to_resend` call. Empty string treated identically to missing via `.strip()`. D-16: hardcoded `_EMAIL_FROM` constant fully removed (`grep -E '_EMAIL_FROM\s*=' notifier.py` returns 0). Regression gate: `tests/test_notifier.py::TestEmailFromEnvVar::test_missing_env_var_skips_email_with_warning` (line 2138) asserts `requests.post` is NOT called. | closed |
| T-12-04 | Elevation of Privilege | Sudoers rule allowing `trader` user to run privileged commands | mitigate | Multi-layer mitigation: (1) `deploy.sh:84-85` uses `sudo -n nginx -t` + `sudo -n systemctl reload nginx` (PATH-relative; absolute paths pinned in sudoers, not deploy.sh — verified `grep -c '/usr/sbin/nginx' deploy.sh = 0`); (2) sudoers line in `SETUP-HTTPS.md` §8 uses absolute paths `/usr/sbin/nginx -t` and `/usr/bin/systemctl reload nginx` with fixed arguments (no wildcards, no `NOPASSWD: ALL`); (3) `sudo -n` non-interactive flag fails fast on path/arg mismatch (Pitfall 7); (4) gate `[ -f nginx/signals.conf ] && command -v nginx &>/dev/null` short-circuits on pre-Phase-12 droplets. Regression gate: `tests/test_deploy_sh.py::TestNginxReloadHook` (line 182, 10 tests) including `test_no_absolute_nginx_path_in_deploy_sh` (line 230); cross-artifact drift guard `tests/test_setup_https_doc.py::TestCrossArtifactDriftGuard::test_deploy_sh_reload_calls_match_sudoers_rule` (line 303) asserts the 4 `sudo -n` calls in deploy.sh match the 4-rule sudoers line in the runbook. | closed |
| T-12-05 | Information Disclosure | Operator runbook (`SETUP-HTTPS.md`) drifts from committed code artifacts → operator deploys misconfiguration | mitigate | `tests/test_setup_https_doc.py::TestCrossArtifactDriftGuard` (line 277) asserts 7 cross-artifact invariants reading `nginx/signals.conf` + `deploy.sh` + `notifier.py` + `systemd/trading-signals-web.service`: `test_owned_domain_placeholder_matches_nginx_conf` (line 293), `test_deploy_sh_reload_calls_match_sudoers_rule` (line 303), `test_sudoers_4_rule_line_present`, `test_signals_email_from_matches_notifier` (line 335), `test_no_hardcoded_email_from_in_notifier` (line 351 — D-16 regression gate using regex `(^\|[^A-Z_])_EMAIL_FROM\s*=` to avoid SIGNALS_EMAIL_FROM substring false-positive), `test_env_path_matches_systemd_unit` (line 370 — extracts `EnvironmentFile=-?([^\s]+)` from `systemd/trading-signals-web.service:11` `/home/trader/trading-signals/.env` and asserts the path appears in the runbook). Drift surfaces become test failures at commit time, not operator time. | closed |
| T-12-06 | Tampering | HSTS silently dropped via location-scope `add_header` (nginx replace-not-extend semantics) — present + future | mitigate (consolidated: Plan 01 structural + Plan 04 doc-level) | **Plan 01 structural:** All security headers (`Strict-Transport-Security`, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`) at server scope with `always` flag in `nginx/signals.conf:61-64`; HSTS exact value `max-age=31536000; includeSubDomains` (no `preload` per D-12 — keeps rollback escape hatch open). Regression gate: `tests/test_nginx_signals_conf.py::TestNginxConfHstsScope::test_hsts_not_inside_location` (line 145) splits config on `location ` tokens and scans each chunk for `Strict-Transport-Security` — fails if HSTS appears in any nested scope. **Plan 04 doc-level:** `SETUP-HTTPS.md` §3 (line 173) confirms HSTS server-scope placement; lines 37-42 carry an explicit T-12-06 banner warning Phase 13+ authors that nginx `add_header` directives are REPLACED (not extended) by nested `add_header` blocks; per-route headers must redeclare ALL security headers or use the third-party `headers-more-nginx-module`. | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-12-01 | T-12-01 | TLS private-key file is OS-enforced mode 0600 at `/etc/letsencrypt/live/<domain>/privkey.pem`; not in our code's responsibility surface. Committed `nginx/signals.conf` contains zero `ssl_certificate` / `ssl_certificate_key` references — certbot injects on first run, so cert paths never enter git history. Regression gate ensures we never reintroduce a key reference into the committed config. | gsd-security-auditor (Phase 12 audit) | 2026-04-25 |

*Accepted risks do not resurface in future audit runs.*

### Residual Risks (operationally accepted, not formal Accepted Risks)

These are noted but do not require formal acceptance entries — they are bounded by ASVS L1 scope or downstream operator action:

- `sudo -n nginx -t` exposure: a compromised `trader` account can run `nginx -t` (config-test only — no state change, no privilege escalation beyond config validation).
- `sudo -n systemctl reload nginx` exposure: a compromised `trader` can reload nginx (re-reads committed config). Worst case: DoS by repeatedly reloading — bounded by the same attack surface as Phase 11's `systemctl restart trading-signals` already-granted rule.
- `SIGNALS_EMAIL_FROM` is a sender address, NOT a credential — no key rotation policy needed. `RESEND_API_KEY` (the actual secret) path unchanged.
- `.env` file stays gitignored (Phase 11 convention preserved).
- systemd `EnvironmentFile=-` optional-prefix means a misconfigured droplet (missing .env) still starts the service; the first daily run surfaces "SIGNALS_EMAIL_FROM not set" in journald + next-day warning banner (intended fail-loud behavior per D-14).
- Pre-Phase-12 droplets: `command -v nginx &>/dev/null` returns non-zero, deploy.sh nginx reload block is skipped — no side effect.
- Operator misreads runbook or skips `--dry-run` → burns Let's Encrypt rate-limit slot. SETUP-HTTPS.md §9 Troubleshooting has explicit wait-168-hours + `--staging` mitigation; no further code-side prevention.
- HSTS `max-age=1y` is browser-cached; rollback requires browser cache clear (chrome://net-internals/#hsts) or natural expiry. This is WHY D-12 rejected `preload` — keeps the escape hatch open.

---

## Threat Flags from Implementation (SUMMARY.md)

All four plan SUMMARY.md files (`12-01-SUMMARY.md`, `12-02-SUMMARY.md`, `12-03-SUMMARY.md`, `12-04-SUMMARY.md`) report **`None`** under `## Threat Flags` — no new attack surface detected by executors during implementation beyond what is already enumerated in the threat register above.

No unregistered flags.

---

## Cross-Artifact Drift Status

Snapshot at audit time (2026-04-25) — `tests/test_setup_https_doc.py::TestCrossArtifactDriftGuard` passes:

| Drift Surface | Source A | Source B | Status |
|---------------|----------|----------|--------|
| `<owned-domain>` placeholder | `nginx/signals.conf` line 32 (`server_name signals.<owned-domain>.com;`) | `SETUP-HTTPS.md` §3 sed command + 18 doc references | PASS |
| 4 `sudo -n` commands | `deploy.sh` lines 50, 51, 84, 85 | `SETUP-HTTPS.md` §8 verbatim 4-rule sudoers line | PASS |
| `SIGNALS_EMAIL_FROM` env var | `notifier.py` lines 1411, 1525 (`os.environ.get(...)`) | `SETUP-HTTPS.md` §7 `.env` instruction | PASS |
| `.env` file path | `systemd/trading-signals-web.service:11` `EnvironmentFile=-/home/trader/trading-signals/.env` | `SETUP-HTTPS.md` §7 + 5 other refs | PASS |
| D-16: `_EMAIL_FROM = ...` removed | `notifier.py` (regex `(^\|[^A-Z_])_EMAIL_FROM\s*=`) | (negative assertion — Plan 02 D-16 regression gate) | PASS — zero matches |
| HSTS server-scope only | `nginx/signals.conf` lines 61-64 | `tests/test_nginx_signals_conf.py::TestNginxConfHstsScope` (Plan 01) | PASS |
| ACME carve-out has no `limit_req` | `nginx/signals.conf` lines 69-71 | `tests/test_nginx_signals_conf.py::TestNginxConfAcmeCarveout` (Plan 01) | PASS |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-04-25 | 6 | 6 | 0 | gsd-security-auditor (Opus 4.7) |

Audit notes (2026-04-25):
- All 6 threats verified by reading committed code, tests, and operator doc — no implementation modifications.
- T-12-06 consolidated across Plans 01 + 04 into a single unified register entry citing both co-mitigations.
- T-12-01 accepted with formal Accepted Risk entry AR-12-01 (OS-enforced key mode 0600; not our code's responsibility surface).
- All four Plan SUMMARY.md `## Threat Flags` sections report `None` — no unregistered surface introduced during execution.
- No new third-party Python deps introduced in Phase 12 — AST forbidden-imports guard unaffected.

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log (AR-12-01)
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-04-25 — gsd-security-auditor
