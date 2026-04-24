---
phase: 12
slug: https-domain-wiring
status: green
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-24
audited: 2026-04-25
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
| 12-01-01 | 01 | 1 | WEB-03 | T-12-01 (cert material on disk) | `nginx/signals.conf` present with `<owned-domain>` placeholder, HSTS, rate-limit, security headers, proxy_pass to 127.0.0.1:8000 | file check + structural | `pytest tests/test_nginx_signals_conf.py -q` (34 tests across 9 classes) | ✅ | ✅ green |
| 12-01-02 | 01 | 1 | WEB-03 | — | nginx config structurally valid (text-level invariants — `nginx -t` runs as operator step per SETUP-HTTPS.md §3) | structural | `pytest tests/test_nginx_signals_conf.py::TestNginxConfStructure -q` | ✅ | ✅ green |
| 12-01-03 | 01 | 1 | WEB-04 | — | HSTS header exact value matches ROADMAP SC-2 | grep | `grep -q "max-age=31536000; includeSubDomains" nginx/signals.conf && ! grep -q "preload" nginx/signals.conf` | ✅ | ✅ green |
| 12-01-04 | 01 | 1 | WEB-03 | T-12-02 (ACME challenge lockout) | Rate-limit does NOT apply to `/.well-known/acme-challenge/*` path | structural | `pytest tests/test_nginx_signals_conf.py::TestNginxConfAcmeCarveout -q` | ✅ | ✅ green |
| 12-02-01 | 02 | 1 | INFRA-01 | T-12-03 (fallback leak) | `_EMAIL_FROM` constant removed (D-16); env var read per-send | grep | `grep -cE "(^\|[^A-Z_])_EMAIL_FROM\\s*=" notifier.py` → 0 | ✅ | ✅ green |
| 12-02-02 | 02 | 1 | INFRA-01 | — | `SIGNALS_EMAIL_FROM` env var value reaches Resend payload | unit | `pytest tests/test_notifier.py::TestEmailFromEnvVar::test_from_addr_reads_env_var -q` | ✅ | ✅ green |
| 12-02-03 | 02 | 1 | INFRA-01 | T-12-03 | Missing env var → skip email, log `[Email] SIGNALS_EMAIL_FROM not set`, append warning (via main orchestrator), continue run | unit | `pytest tests/test_notifier.py::TestEmailFromEnvVar::test_missing_env_var_skips_email_with_warning -q` | ✅ | ✅ green |
| 12-02-04 | 02 | 1 | INFRA-01 | T-12-03 | Empty env var treated as missing (same path) | unit | `pytest tests/test_notifier.py::TestEmailFromEnvVar::test_empty_env_var_treated_as_missing -q` | ✅ | ✅ green |
| 12-02-05 | 02 | 1 | INFRA-01 | — | Golden email tests regenerated / autouse fixture sets SIGNALS_EMAIL_FROM; TestGoldenEmail still green | unit | `pytest tests/test_notifier.py::TestGoldenEmail -q` | ✅ | ✅ green |
| 12-02-06 | 02 | 1 | INFRA-01 | T-12-03 | Footer renderer accepts from_addr (signature extended); `compose_email_body` keyword-only `from_addr`; covered via TestEmailFromEnvVar (Resend `from` capture) + TestGoldenEmail byte-equality. No standalone TestFooterRenderer class needed — covered by autouse fixture + composer call sites. | unit | `pytest tests/test_notifier.py::TestEmailFromEnvVar tests/test_notifier.py::TestGoldenEmail -q` | ✅ | ✅ green |
| 12-03-01 | 03 | 1 | WEB-03 | T-12-04 (deploy.sh privilege surface) | deploy.sh runs `nginx -t` + `systemctl reload nginx` after FastAPI restart, gated on nginx install + `nginx/signals.conf` presence | bash text-assertion | `pytest tests/test_deploy_sh.py::TestNginxReloadHook -q` (10 tests) | ✅ | ✅ green |
| 12-03-02 | 03 | 1 | WEB-03 | — | Reload step skips silently when nginx absent — gate `[ -f nginx/signals.conf ] && command -v nginx &>/dev/null` (test name: `test_gate_command_v_check_present`) | bash text-assertion | `pytest tests/test_deploy_sh.py::TestNginxReloadHook::test_gate_command_v_check_present -q` | ✅ | ✅ green |
| 12-03-03 | 03 | 1 | WEB-03 | — | Ordering: reload happens AFTER successful FastAPI restart + /healthz smoke test | bash text-assertion | `pytest tests/test_deploy_sh.py::TestNginxReloadHook::test_order_after_healthz_smoke_test -q` | ✅ | ✅ green |
| 12-04-01 | 04 | 2 | WEB-03 / WEB-04 / INFRA-01 | T-12-05 (operator runbook drift) | SETUP-HTTPS.md exists in phase dir with 10 required sections | structural | `pytest tests/test_setup_https_doc.py::TestDocStructure -q` (11 section assertions) | ✅ | ✅ green |
| 12-04-02 | 04 | 2 | WEB-03 | — | Runbook references the exact committed `nginx/signals.conf` path | grep | `grep -q "nginx/signals.conf" .planning/phases/12-https-domain-wiring/SETUP-HTTPS.md` | ✅ | ✅ green |
| 12-04-03 | 04 | 2 | WEB-03 | T-12-06 (cross-artifact drift) | TestCrossArtifactDriftGuard — sudoers entry, nginx placeholder, env-var name, env path all match across SETUP-HTTPS.md ↔ nginx/signals.conf ↔ deploy.sh ↔ notifier.py ↔ systemd unit (7 drift assertions) | cross-file | `pytest tests/test_setup_https_doc.py::TestCrossArtifactDriftGuard -q` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/test_nginx_signals_conf.py` — 9 classes / 34 tests over the committed nginx config (required directives, HSTS exact value, rate-limit zone, proxy_pass target, ACME-challenge exemption, no 0.0.0.0 bind, no hardcoded domain — placeholder `<owned-domain>` present). Mirrors Phase 11 `tests/test_web_systemd_unit.py` pattern. **Verified 2026-04-25: 34 passed in 0.02s.**
- [x] `tests/test_notifier.py::TestEmailFromEnvVar` — 4 tests (deviation from plan's 3): env-var-read / missing-skips-with-warning / empty-treated-as-missing / send_crash_email parity per 12-CONTEXT.md D-17 + 12-REVIEWS.md LOW. **Verified 2026-04-25.**
- [x] `tests/test_notifier.py::TestGoldenEmail` — MODIFIED: module-level `@pytest.fixture(autouse=True)` `_pin_signals_email_from` that `monkeypatch.setenv('SIGNALS_EMAIL_FROM', 'signals@carbonbookkeeping.com.au')` AND every `compose_email_body(...)` call site updated to pass `from_addr='signals@carbonbookkeeping.com.au'` explicitly (38 sites). Goldens regenerated byte-equal. **Verified 2026-04-25.**
- [x] **TestFooterRenderer was NOT created as a separate class** — per plan deviation logged in 12-02-SUMMARY: footer-renderer signature extension (`_render_footer_email(state, now, from_addr)`) is exercised end-to-end via `TestEmailFromEnvVar::test_from_addr_reads_env_var` (Resend `from` field capture proves footer interpolation) + `TestGoldenEmail` (byte-equal HTML proves footer text matches expected addr). Research finding #1 line 1147 usage site is covered by these two suites in combination. **No coverage gap.**
- [x] `tests/test_deploy_sh.py::TestNginxReloadHook` — new test class with **10 tests** (deviation from plan's 3): gate-file-check, gate-command-v, gate-uses-logical-and, sudo-n-nginx-t, sudo-n-systemctl-reload, no-absolute-paths-in-deploy-sh, order-after-healthz-smoke, order-before-commit-echo, no-unconditional-nginx-reference-before-gate, echo-messages-have-deploy-prefix. Extends Phase 11 `test_deploy_sh.py` text-assertion pattern. **Verified 2026-04-25: 10 passed in 0.01s.**
- [x] `tests/test_setup_https_doc.py` — 12 classes / 57 tests covering SETUP-HTTPS.md sections, required command snippets, cross-artifact drift guard (7 assertions across nginx/signals.conf, deploy.sh, notifier.py, systemd/trading-signals-web.service). Includes `test_env_path_matches_systemd_unit` belt-and-braces gate added per 12-REVIEWS.md LOW. Mirrors Phase 11 `tests/test_setup_droplet_doc.py`. **Verified 2026-04-25: 57 passed in 0.02s.**

All Wave 0 work was test-side only — no framework install needed. Pytest + pytest-freezer pinned (no requirements.txt changes for Phase 12).

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

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify (every row has either pytest invocation or single-grep)
- [x] Wave 0 covers all MISSING references — 4 net-new test files / classes; deviations from plan logged inline above
- [x] No watch-mode flags
- [x] Feedback latency < 95s — Phase 12 slice runs in ~10s; full suite (excluding pre-existing `tests/test_main.py` weekend-clock failures) runs in 90.52s
- [x] `nyquist_compliant: true` set in frontmatter — flipped during 2026-04-25 retro audit

**Approval:** ✅ green (retro-audited 2026-04-25)

---

## Audit Trail

| Date | Auditor | Gaps Found | Resolved | Escalated | nyquist_compliant | Notes |
|------|---------|-----------|----------|-----------|-------------------|-------|
| 2026-04-25 | gsd-nyquist-auditor (retro pass) | 0 | 17 automated rows flipped ⬜ → ✅ green | 0 | true | Retro audit on completed phase. All 4 Phase 12 test files run green (`tests/test_nginx_signals_conf.py` 34/34, `tests/test_notifier.py::TestEmailFromEnvVar`+`TestGoldenEmail` 19/19, `tests/test_deploy_sh.py::TestNginxReloadHook` 10/10, `tests/test_setup_https_doc.py` 57/57); Phase 12 quick-run slice 293/293; full suite 822 passed (excluding pre-existing `tests/test_main.py` weekend-clock failures tracked in `deferred-items.md`). All file-existence + grep invariants confirmed (HSTS exact value, no preload, D-16 `_EMAIL_FROM` zero matches, `os.environ.get('SIGNALS_EMAIL_FROM')` 2× sites, `SendStatus(ok=False, reason='missing_sender')` 4× sites, `sudo -n nginx -t` + `sudo -n systemctl reload nginx` each 1× in deploy.sh, doc cross-refs to nginx/signals.conf + sudo + env-path + env-var + staging all present). Two row-level fixes applied: (a) row 12-02-06 commands now point at `TestEmailFromEnvVar`+`TestGoldenEmail` (no separate `TestFooterRenderer` class — coverage threaded via the autouse fixture + 38 explicit `from_addr=` call-site updates per 12-02-SUMMARY); (b) rows 12-03-02/12-03-03 commands now point at the actual method names (`test_gate_command_v_check_present`, `test_order_after_healthz_smoke_test`) — the plan-pseudo-names `test_skips_when_no_nginx` and `test_order_after_healthz_smoke` were renamed during execution. 5 Manual-Only rows confirmed legitimately manual (live domain DNS, live Let's Encrypt cert issuance, live certbot.timer, live HTTP→HTTPS curl, live Gmail SPF/DKIM via `python main.py --force-email` — all require operator-side resources unavailable in CI). |
