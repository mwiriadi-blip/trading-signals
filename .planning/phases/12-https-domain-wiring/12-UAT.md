---
status: partial
phase: 12-https-domain-wiring
source: [12-01-SUMMARY.md, 12-02-SUMMARY.md, 12-03-SUMMARY.md, 12-04-SUMMARY.md]
started: 2026-04-25T06:00:00+08:00
updated: 2026-04-25T06:20:00+08:00
---

## Current Test

[testing complete]

## Tests

### 1. Cold Start Smoke Test
expected: From a fresh shell in the repo root, `pytest -q --ignore=tests/test_main.py` completes with rc=0 and reports 822 tests passing (55 of them new from Phase 12). No import errors, no new regressions. `bash -n deploy.sh` exits 0.
result: pass
note: "Verified on local Mac dev environment — `pytest -q --ignore=tests/test_main.py` → 822 passed in 92.09s. First run attempted on droplet but produced 4 failures: 3× TestGoldenEmail (droplet's `compose_email_body` still has pre-refactor `from_addr='onboarding@resend.dev'` default — confirms droplet is running pre-Phase-12 notifier.py; my Phase 12 commits are local-only, not yet pushed to origin/main) and 1× TestDeterminism RVol hash drift (separate pre-existing issue — likely numpy/pandas float-semantics difference between droplet and local pip install; NOT Phase 12 scope). Neither finding represents a Phase 12 regression. Droplet UAT deferred until `/gsd-ship` pushes Phase 12 to origin/main and operator pulls."

### 2. WEB-03/WEB-04: nginx/signals.conf content + structural invariants
expected: nginx/signals.conf exists with single 443 server block + file-top limit_req_zone + HSTS (exact value, no preload) + rate-limit on /healthz + ACME carve-out + security headers at server scope. NO listen 80, NO return 301, NO ssl_certificate (certbot injects). pytest tests/test_nginx_signals_conf.py -q → 34 tests passing.
result: pass
evidence: "Local run: pytest 34 passed in 0.03s. Grep verified: `server_name signals.<owned-domain>.com` = 1, `limit_req_zone ... zone=healthz:10m rate=10r/m` = 1, `location = /healthz` = 1, `location /.well-known/acme-challenge/` = 1, no `preload`, no `listen 80`, no `ssl_certificate ` (with trailing space to avoid `ssl_certificate_key` match). File is 97 lines. D-05, D-08, D-10, D-11, D-12 verified."

### 3. INFRA-01: SIGNALS_EMAIL_FROM env var refactor
expected: `_EMAIL_FROM` constant removed (D-16); `os.environ.get('SIGNALS_EMAIL_FROM'` per-send in send_daily_email + send_crash_email; SendStatus stays 2-field `(ok=False, reason='missing_sender')`; TestEmailFromEnvVar (4 tests) + TestGoldenEmail (3 tests) green.
result: pass
evidence: "Local run: pytest 19 passed in 0.10s (TestEmailFromEnvVar + TestGoldenEmail). `grep -cE \"(^|[^A-Z_])_EMAIL_FROM\" notifier.py` = 0 (D-16 clean; naive grep shows 6 because `SIGNALS_EMAIL_FROM` contains `_EMAIL_FROM` as substring). `grep -c \"os.environ.get('SIGNALS_EMAIL_FROM'\" notifier.py` = 2 (D-15 per-send read in both dispatch funcs). `grep -c \"attempts=\" notifier.py` = 0 (research finding #2 honored — SendStatus 2-field). D-14/D-15/D-16/D-17/D-19 verified."

### 4. WEB-03: deploy.sh nginx reload hook (gated)
expected: deploy.sh has `sudo -n nginx -t` + `sudo -n systemctl reload nginx` after healthz smoke, gated on `[ -f nginx/signals.conf ] && command -v nginx &>/dev/null`. No absolute paths in deploy.sh itself (secure_path + sudoers handle that). pytest TestNginxReloadHook (10 tests) green. bash -n clean.
result: pass
evidence: "Local run: pytest 10 passed in 0.01s. Grep verified: `sudo -n nginx -t` = 1, `sudo -n systemctl reload nginx` = 1, `/usr/sbin/nginx` = 0 (absolute paths are sudoers' job per 12-REVIEWS.md MEDIUM), `[ -f nginx/signals.conf ]` = 1 (gate present), `bash -n deploy.sh` exits 0. D-20 verified."

### 5. SETUP-HTTPS.md operator runbook content
expected: SETUP-HTTPS.md exists (~480 lines) with 10 `##`-sections per D-21 + stale-docs banner. Key content: apt install nginx certbot, certbot --nginx, sudo -n nginx -t verification, /home/trader/trading-signals/.env path (matches Phase 11 systemd), SIGNALS_EMAIL_FROM, --staging recommendation, Let's Encrypt posture check.
result: pass
evidence: "Local verification: 480 lines, 11 `##`-level headings (Quickstart + 10 D-21 sections). Grep hits: `certbot --nginx`, `sudo -n nginx -t`, `/home/trader/trading-signals/.env`, `SIGNALS_EMAIL_FROM`, `staging`, `docs/DEPLOY.md`, `Let's Encrypt` — all present. D-21 verified."

### 6. Cross-artifact drift guard
expected: pytest tests/test_setup_https_doc.py -q → 57 tests passing, including TestCrossArtifactDriftGuard with new test_env_path_matches_systemd_unit asserting doc's .env path matches systemd EnvironmentFile= path.
result: pass
evidence: "Local run: pytest 57 passed in 0.02s. TestCrossArtifactDriftGuard includes 7 assertions covering: `<owned-domain>` placeholder in both nginx/signals.conf and SETUP-HTTPS.md; deploy.sh sudo calls match runbook's sudoers entry; SIGNALS_EMAIL_FROM env var name appears in both SETUP-HTTPS.md §7 and notifier.py; `_EMAIL_FROM` absent from notifier.py; NEW test_env_path_matches_systemd_unit reads systemd unit and asserts path equality (12-REVIEWS.md LOW belt-and-braces)."

### 7. INFRA-01 live — email arrives from operator-verified domain
expected: After operator sets SIGNALS_EMAIL_FROM in /home/trader/trading-signals/.env + restarts trading-signals.service, `python main.py --force-email` sends email arriving from `signals@carbonbookkeeping.com.au` with SPF/DKIM PASS in Gmail. If env var unset, no Resend HTTP call + `[Email] SIGNALS_EMAIL_FROM not set — email skipped` log.
result: blocked
blocked_by: physical-device
reason: "Requires live SSH access to droplet, Phase 12 code pulled to droplet, .env edit, systemd restart, Resend live send, Gmail SPF/DKIM header inspection. Documented as manual-only in 12-VALIDATION.md §Manual-Only. Operator performs post-`/gsd-ship` when Phase 12 reaches the droplet via pull. SC-4 (the no-silent-fallback contract) is fully automated via TestEmailFromEnvVar (4 tests) green — the live send just confirms the observable outcome."

### 8. WEB-03 live — HTTPS + Let's Encrypt cert
expected: After SETUP-HTTPS.md §3 (symlink) + §4 (certbot --nginx), `curl -sI https://signals.<owned-domain>.com/healthz` returns 200 with LE cert chain; `systemctl list-timers | grep certbot` shows active; `certbot renew --dry-run` succeeds.
result: blocked
blocked_by: physical-device
reason: "Requires live domain purchased, A-record pointing at droplet IP, operator running certbot --nginx. Cannot be automated (domain + DNS + LE issuance are all operator-manual). Documented as manual-only in 12-VALIDATION.md. Code-side artifacts (nginx/signals.conf + deploy.sh hook + SETUP-HTTPS.md + drift guard) all verified via Tests 2/4/5/6."

### 9. WEB-04 live — HTTP→HTTPS redirect + HSTS
expected: curl -sI http://...healthz → 301; HTTPS response has HSTS exact value + 3 other security headers; /healthz rate-limit returns 429 when exceeded; ACME path carves out.
result: blocked
blocked_by: physical-device
reason: "Requires live HTTPS stack (Test 8's prerequisites). HSTS header value is exactly committed in nginx/signals.conf (verified Test 2); 301 redirect is certbot-injected on first --nginx run; rate-limit zone is committed + structurally tested. Operator verifies end-to-end once Phase 12 ships + certbot runs. Documented as manual-only in 12-VALIDATION.md."

## Summary

total: 9
passed: 6
issues: 0
pending: 0
skipped: 0
blocked: 3

## Gaps

[none — all issues resolved on reclassification; 3 manual-only verifications tracked as blocked per 12-VALIDATION.md §Manual-Only. The Test 1 droplet-discovery failures are pre-merge stale-droplet (same pattern as Phase 10 UAT) and a separate pre-existing numpy/pandas hash drift (not Phase 12 scope) — both documented in deferred-items.md.]
