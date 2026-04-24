---
phase: 12
slug: https-domain-wiring
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-24
---

# Phase 12 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x (+ pytest-freezer) — existing |
| **Config file** | `pytest.ini` (existing) |
| **Quick run command** | `pytest tests/test_notifier.py tests/test_deploy_sh.py tests/test_nginx_signals_conf.py tests/test_setup_https_doc.py -x -q` |
| **Full suite command** | `pytest -q` |
| **Estimated runtime** | ~10 seconds (Phase 12 slice) / ~95 seconds (full) |

Phase 12 does NOT add any new Python runtime dependencies. nginx, certbot, and certbot-nginx are system packages installed via apt on the droplet (operator action per SETUP-HTTPS.md). No `requirements.txt` changes.

---

## Sampling Rate

- **After every task commit:** Run quick run command (Phase 12 test slice only)
- **After every plan wave:** Run full suite command
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 95 seconds

---

## Per-Task Verification Map

Populated by planner. The tentative rows below reflect the Phase 12 scope per CONTEXT.md D-01..D-21 + research findings.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 12-01-01 | 01 | 1 | WEB-03 | T-12-01 (cert material on disk) | `nginx/signals.conf` present with `<owned-domain>` placeholder, HSTS, rate-limit, security headers, proxy_pass to 127.0.0.1:8000 | file check + nginx syntax | `pytest tests/test_nginx_signals_conf.py -q` | ❌ W0 | ⬜ pending |
| 12-01-02 | 01 | 1 | WEB-03 | — | nginx config parses cleanly via `nginx -t` (tests use a mock include path) | config parser | `pytest tests/test_nginx_signals_conf.py::TestNginxSyntax -q` | ❌ W0 | ⬜ pending |
| 12-01-03 | 01 | 1 | WEB-04 | — | HSTS header exact value matches ROADMAP SC-2 | grep | `grep -q "max-age=31536000; includeSubDomains" nginx/signals.conf && ! grep -q "preload" nginx/signals.conf` | ❌ W0 | ⬜ pending |
| 12-01-04 | 01 | 1 | WEB-03 | T-12-02 (ACME challenge lockout) | Rate-limit does NOT apply to `/.well-known/acme-challenge/*` path | config-parser | `pytest tests/test_nginx_signals_conf.py::TestAcmeChallengePath -q` | ❌ W0 | ⬜ pending |
| 12-02-01 | 02 | 1 | INFRA-01 | T-12-03 (fallback leak) | `_EMAIL_FROM` constant removed; env var read per-send | grep | `grep -q "def.*from_addr" notifier.py && ! grep -q "^_EMAIL_FROM =" notifier.py` | ❌ W0 | ⬜ pending |
| 12-02-02 | 02 | 1 | INFRA-01 | — | `SIGNALS_EMAIL_FROM` env var value reaches Resend payload | unit | `pytest tests/test_notifier.py::TestEmailFromEnvVar::test_from_addr_reads_env_var -q` | ❌ W0 | ⬜ pending |
| 12-02-03 | 02 | 1 | INFRA-01 | T-12-03 | Missing env var → skip email, log `[Email] SIGNALS_EMAIL_FROM not set`, append warning, continue run | unit | `pytest tests/test_notifier.py::TestEmailFromEnvVar::test_missing_env_var_skips_email_with_warning -q` | ❌ W0 | ⬜ pending |
| 12-02-04 | 02 | 1 | INFRA-01 | T-12-03 | Empty env var treated as missing (same path) | unit | `pytest tests/test_notifier.py::TestEmailFromEnvVar::test_empty_env_var_treated_as_missing -q` | ❌ W0 | ⬜ pending |
| 12-02-05 | 02 | 1 | INFRA-01 | — | Golden email tests regenerated / autouse fixture sets SIGNALS_EMAIL_FROM; TestGoldenEmail still green | unit | `pytest tests/test_notifier.py::TestGoldenEmail -q` | ✅ (exists; will be modified) | ⬜ pending |
| 12-02-06 | 02 | 1 | INFRA-01 | T-12-03 | Footer renderer accepts from_addr (_render_footer_email OR compose_email_body signature extended) per research finding #1 | unit | `pytest tests/test_notifier.py::TestFooterRenderer -q` (or equivalent per plan) | ❌ W0 | ⬜ pending |
| 12-03-01 | 03 | 1 | WEB-03 | T-12-04 (deploy.sh privilege surface) | deploy.sh runs `nginx -t` + `systemctl reload nginx` after FastAPI restart, gated on nginx install + `nginx/signals.conf` presence | bash-mock | `pytest tests/test_deploy_sh.py::TestNginxReloadHook -q` | ✅ (exists; will be extended) | ⬜ pending |
| 12-03-02 | 03 | 1 | WEB-03 | — | Reload step SKIPPED cleanly when nginx is not installed (negative assertion) | bash-mock | `pytest tests/test_deploy_sh.py::TestNginxReloadHook::test_skips_when_no_nginx -q` | ❌ W0 | ⬜ pending |
| 12-03-03 | 03 | 1 | WEB-03 | — | Ordering: reload happens AFTER successful FastAPI restart + /healthz smoke test | bash-mock | `pytest tests/test_deploy_sh.py::TestNginxReloadHook::test_order_after_healthz_smoke -q` | ❌ W0 | ⬜ pending |
| 12-04-01 | 04 | 2 | WEB-03 / WEB-04 / INFRA-01 | T-12-05 (operator runbook drift) | SETUP-HTTPS.md exists in phase dir with 10 required sections | file + grep | `test -f .planning/phases/12-https-domain-wiring/SETUP-HTTPS.md && grep -q "certbot --nginx" ... && grep -q "certbot.timer" ... && grep -q "SIGNALS_EMAIL_FROM" ...` | ❌ | ⬜ pending |
| 12-04-02 | 04 | 2 | WEB-03 | — | Runbook references the exact committed `nginx/signals.conf` path | grep | `grep -q "nginx/signals.conf" .planning/phases/12-https-domain-wiring/SETUP-HTTPS.md` | ❌ | ⬜ pending |
| 12-04-03 | 04 | 2 | WEB-03 | T-12-06 (cross-artifact drift) | TestCrossArtifactDriftGuard — sudoers entry form in SETUP-HTTPS.md matches what deploy.sh expects | cross-file | `pytest tests/test_setup_https_doc.py::TestCrossArtifactDriftGuard -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_nginx_signals_conf.py` — new test file; configparser-style tests for the committed nginx config (required directives, HSTS exact value, rate-limit zone, proxy_pass target, ACME-challenge exemption, no 0.0.0.0 bind, no hardcoded domain — placeholder `<owned-domain>` present). Mirrors Phase 11 `tests/test_web_systemd_unit.py` pattern.
- [ ] `tests/test_notifier.py::TestEmailFromEnvVar` — new test class (3 tests): env-var-read / missing-skips-with-warning / empty-treated-as-missing per 12-CONTEXT.md D-17.
- [ ] `tests/test_notifier.py::TestGoldenEmail` — MODIFIED: class-level `autouse=True` fixture that `monkeypatch.setenv('SIGNALS_EMAIL_FROM', 'signals@carbonbookkeeping.com.au')`. Golden HTML fixtures either regenerated with env-var value OR the fixture + explicit `from_addr=` param keeps them stable.
- [ ] `tests/test_notifier.py::TestFooterRenderer` (name TBD by planner) — new tests covering `_render_footer_email` with `from_addr` threaded through (addresses research finding #1 — line 1147 usage site).
- [ ] `tests/test_deploy_sh.py::TestNginxReloadHook` — new test class: 3 tests covering reload-happens, skips-when-no-nginx, ordering-after-healthz-smoke. Extends Phase 11 `test_deploy_sh.py` bash-mock pattern.
- [ ] `tests/test_setup_https_doc.py` — new test file; configparser-style coverage of SETUP-HTTPS.md sections, required command snippets, cross-artifact drift guard (references deploy.sh sudoers entry + nginx/signals.conf path). Mirrors Phase 11 `tests/test_setup_droplet_doc.py`.

All Wave 0 work is test-side only — no framework install needed. Pytest + pytest-freezer already pinned.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `curl -sI https://signals.<owned-domain>.com/healthz` returns 200 with Let's Encrypt cert chain | WEB-03 SC-1 | Requires live domain + A-record + certbot run | Operator follows SETUP-HTTPS.md §Step 4 (certbot --nginx); then `curl -sI https://<domain>/healthz` + `openssl s_client -connect <domain>:443` confirms Issuer = Let's Encrypt |
| `certbot.timer` is enabled and dry-run renewal succeeds | WEB-03 SC-1 | Requires live cert to dry-run against | Operator runs `systemctl list-timers \| grep certbot` + `sudo certbot renew --dry-run` per SETUP-HTTPS.md §Step 6 |
| `curl -sI http://signals.<owned-domain>.com/healthz` returns 301 redirect; HSTS header present on HTTPS response | WEB-04 SC-2 | Requires live domain | Operator runs both curls per SETUP-HTTPS.md §Step 5; confirms 301 + HSTS |
| Daily email arrives from `signals@<owned-domain>` with SPF/DKIM pass in Gmail | INFRA-01 SC-3 | Requires live Resend + verified domain + Gmail inbox | Operator runs `python main.py --force-email` post-`SIGNALS_EMAIL_FROM` env-var set; opens Gmail → Show Original; confirms SPF=PASS, DKIM=PASS, sender matches |
| Let's Encrypt issues a production cert (not --staging) | WEB-03 SC-1 | Rate-limited (5 duplicate certs per 168h); stage first per research pitfall #2 | Operator runs `certbot --nginx --dry-run` first; only on clean dry-run does operator run the production issuance. Documented in SETUP-HTTPS.md §Troubleshooting. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 95s
- [ ] `nyquist_compliant: true` set in frontmatter (after plans land + Wave 0 tests exist)

**Approval:** pending
