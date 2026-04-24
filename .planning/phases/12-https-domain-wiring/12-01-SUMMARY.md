---
phase: 12-https-domain-wiring
plan: 01
subsystem: infra
tags: [nginx, tls, hsts, rate-limit, acme, letsencrypt, reverse-proxy, mozilla-intermediate]

# Dependency graph
requires:
  - phase: 11-web-surface-scaffold
    provides: "FastAPI app bound to 127.0.0.1:8000 as systemd service (proxy_pass target)"
provides:
  - "nginx/signals.conf — committed 443-only server block template with Mozilla Intermediate TLS, HSTS, rate-limit on /healthz, ACME carve-out, and proxy to 127.0.0.1:8000"
  - "tests/test_nginx_signals_conf.py — 9 structural test classes / 34 grep-and-regex invariants guarding the committed nginx config against drift"
  - "Placeholder convention: <owned-domain> literal is sed-substituted by operator post-clone (D-01)"
affects:
  - "Plan 12-02 (TLS/HSTS certbot orchestration — consumes this config)"
  - "Plan 12-04 (SETUP-HTTPS.md operator runbook — cross-references directives from this file)"
  - "Future Phase 13+ auth/headers work — MUST NOT add `add_header` inside location blocks (would nuke server-scope HSTS per Pitfall 3)"

# Tech tracking
tech-stack:
  added:
    - "nginx (operator-managed on droplet; no Python dep)"
    - "Mozilla Intermediate TLS profile 2024 rev"
    - "Let's Encrypt + certbot (deployment-path tool; config-ready in this plan)"
  patterns:
    - "Committed-config-with-literal-placeholder: <owned-domain> is sed-substituted post-clone (D-01)"
    - "Certbot-managed cert directives: file contains NO ssl_certificate / ssl_certificate_key / listen 80 / return 301 — certbot injects these on first run"
    - "HSTS at server scope with `always` flag: avoids add_header replace-not-extend trap inside location blocks (T-12-06, Pitfall 3)"
    - "ACME carve-out via nested-location absence-of-limit_req: disables rate-limit inheritance per nginx docs (T-12-02)"
    - "Structural-test-only strategy: no nginx shell-out in CI; grep+regex asserts over committed text"

key-files:
  created:
    - "nginx/signals.conf (97 lines) — 443-only server block template"
    - "tests/test_nginx_signals_conf.py (264 lines) — structural drift guard"
    - ".planning/phases/12-https-domain-wiring/deferred-items.md — pre-existing failure log"
  modified: []

key-decisions:
  - "Committed <owned-domain> as a LITERAL placeholder in server_name (D-01); operator substitutes via sed at deployment"
  - "HSTS max-age=31536000; includeSubDomains WITHOUT preload — D-12 keeps rollback path open (no submission to HSTS-preload-list browser registry)"
  - "TLS cipher list validated via posture check (ECDHE- substring + non-empty + well-formed) rather than exact-string match — per 12-REVIEWS.md LOW, avoids breakage when Mozilla publishes minor cipher-reorder revisions"
  - "No `listen 80` / `ssl_certificate` / `return 301 https://` in committed file — certbot injects these on first --nginx run (Pitfall 1)"
  - "limit_req_zone declared at file top (valid at http scope via Ubuntu include semantics) rather than inside server{} — nginx requires http-context for zone allocation"
  - "Struct-test style matches Phase 11 tests/test_web_systemd_unit.py: scope='module' fixture reading file once, class-per-concern assertions"

patterns-established:
  - "nginx config structural-test contract: committed config is authoritative source; pytest guards drift via regex/substring only (no nginx binary dependency in dev/CI)"
  - "HSTS-scope safety: HSTS-not-inside-location test splits on `location ` tokens and scans each chunk; comments containing the word 'location ' are not allowed either (avoid false-negative escape hatches)"
  - "ACME carve-out correctness: location block extracted via regex + body-of-braces must contain zero `limit_req` — formalised as a test"

requirements-completed:
  - WEB-03
  - WEB-04

# Metrics
duration: 10min
completed: 2026-04-24
---

# Phase 12 Plan 01: nginx/signals.conf — 443-only TLS Edge Summary

**Committed nginx reverse-proxy config (97 lines) for the Trading Signals HTTPS edge — single 443 server block with Mozilla Intermediate TLS, HSTS (no preload), rate-limited /healthz, ACME carve-out, and proxy_pass to FastAPI at 127.0.0.1:8000. Guarded by 34 structural tests across 9 classes.**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-04-24T20:51:00Z
- **Completed:** 2026-04-24T21:00:31Z
- **Tasks:** 2 (Wave 0 RED + Wave 1 GREEN — TDD cycle)
- **Files created:** 2 code + 1 doc
- **Files modified:** 0

## Accomplishments

- **Wave 0 → Wave 1 TDD cycle completed cleanly** (test-first: 34 structural assertions failed on empty-config fixture; flipped GREEN once `nginx/signals.conf` was written)
- **Zero deviation from RESEARCH §Pattern 1 template** for the nginx directives themselves — all TLS, HSTS, rate-limit, ACME, proxy, and header directives are byte-for-byte identical to the authoritative pattern
- **Posture-level cipher-list test** (per 12-REVIEWS.md LOW) rather than exact-string pinning — validates ECDHE forward-secrecy requirement without breaking on Mozilla minor cipher reorderings
- **No regressions** — full pytest suite at 821 passed / 16 pre-existing failures (baseline: 787 passed / 16 failed; net delta exactly +34 new tests, all GREEN)

## Task Commits

Each task was committed atomically:

1. **Task 1: Wave 0 RED — write tests/test_nginx_signals_conf.py FIRST (must fail)** — `6226266` (test)
2. **Task 2: Create nginx/signals.conf** — `15b1c5b` (feat)
3. **Post-task logging: deferred-items.md for pre-existing failures** — `a6441dd` (chore)

_Task 1 is the RED step of the plan-level TDD cycle; Task 2 is GREEN. No REFACTOR step was needed — the config matched the tests on first write after a minor comment-wording adjustment (see Deviations)._

## Files Created/Modified

- `nginx/signals.conf` (97 lines) — Single 443 server block with file-top `limit_req_zone` at http scope; Mozilla Intermediate TLS (2024 rev); HSTS `max-age=31536000; includeSubDomains` with `always`; X-Content-Type-Options/X-Frame-Options/Referrer-Policy at server scope; ACME `/.well-known/acme-challenge/` carve-out; rate-limited `/healthz` with burst=10 nodelay + 429; catch-all `location /` — both proxy to `http://127.0.0.1:8000` with Host/X-Real-IP/X-Forwarded-For/X-Forwarded-Proto headers.
- `tests/test_nginx_signals_conf.py` (264 lines, 9 test classes, 34 tests) — grep-and-regex drift guard covering structure, placeholder, TLS tuning, security headers, HSTS-scope, rate-limit, ACME carve-out, proxy, and forbidden patterns. Fixture reads committed file once per module (scope='module'). No nginx binary dependency.
- `.planning/phases/12-https-domain-wiring/deferred-items.md` — log of 16 pre-existing `tests/test_main.py` failures (unrelated to Phase 12; weekend-skip logic firing on 2026-04-25 Saturday).

## Decisions Made

- **Comment-text refinement to avoid test-regex false positives** — see Deviations below. Two comment-line rewrites (carbonbookkeeping → `<your-domain>`; HSTS-preload description rephrased to omit the literal word "preload"; "location" in prose → "block/scope") were necessary so the plan-authored tests pass against the plan-authored config. Semantic intent preserved.
- **No `refactor` commit** — the GREEN config satisfied all tests after the comment-wording adjustments (which are still part of Task 2 since the config file is new).
- Otherwise followed plan exactly as specified.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Plan-authored comment text triggered plan-authored tests**
- **Found during:** Task 2 (first pytest run against the new config)
- **Issue:** Three of the 34 tests initially failed because the plan's verbatim comment block for `nginx/signals.conf` contained trigger strings that the plan's own tests flagged:
  - `test_no_hardcoded_production_domain` (assert `'carbonbookkeeping' not in conf_text`) — the sed-example comment had `carbonbookkeeping` as the sample substitution target.
  - `test_no_handwritten_http_to_https_redirect` (assert `return 301 https://` not in text) — the comment describing what certbot injects contained the literal phrase `return 301 https://$host$request_uri;`.
  - `test_hsts_not_inside_location` (splits on `'location '` then scans each chunk for `Strict-Transport-Security`) — the word "location" in a multi-line comment caused the split to divide the file before the server-scope HSTS directives, falsely placing HSTS "inside a location block".
- **Fix:** Rewrote the affected comment lines to preserve meaning while avoiding the literal trigger substrings:
  - `carbonbookkeeping` → `<your-domain>` (generic placeholder example)
  - `return 301 https://$host$request_uri;` → "performing the HTTP->HTTPS 301 redirect" (prose description)
  - Word `location` → `block` / `scope` / `nested scope` where it appeared in comment prose (kept inside `location /...` directives themselves)
  - Also removed the bare word `preload` from a comment per the plan's `grep -c "preload" = 0` acceptance criterion (retained semantic: "the HSTS browser-submission directive is intentionally omitted...")
- **Files modified:** `nginx/signals.conf` (5 comment lines)
- **Verification:** All 34 tests in `tests/test_nginx_signals_conf.py` pass; full suite no regressions.
- **Committed in:** `15b1c5b` (part of Task 2's first and only commit — the adjustments happened before the commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — bug / test-config consistency)
**Impact on plan:** No scope creep. Zero changes to the nginx directives themselves — only comment-text phrasing. Semantic intent preserved verbatim. Every must_have/acceptance-criterion from the plan is satisfied.

## Issues Encountered

- **Pre-existing failures in `tests/test_main.py` (16)** — observed at baseline commit `ca84315` before any Plan 01 work. Re-confirmed after Plan 01 GREEN: identical 16 failures, no new ones. Root cause appears to be weekend-skip logic firing on wall-clock 2026-04-25 (Saturday). Out-of-scope per SCOPE BOUNDARY; logged in `.planning/phases/12-https-domain-wiring/deferred-items.md` for a future bug-fix plan.

## User Setup Required

None for this plan — the operator runbook (SETUP-HTTPS.md) is authored in Plan 12-04 and will include the `sed -i 's|<owned-domain>|...|g'` substitution, `sudo nginx -t` validation, and `sudo certbot --nginx -d signals.<domain>` issuance steps.

## Next Phase Readiness

- **Plan 12-02 (TLS/HSTS certbot orchestration)** — ready to consume `nginx/signals.conf`. On first `certbot --nginx` run, certbot will inject the port-80 redirect block and `ssl_certificate` / `ssl_certificate_key` lines.
- **Plan 12-03 (DNS + A-record)** — blocked only on operator/registrar action; no code impact from this plan.
- **Plan 12-04 (SETUP-HTTPS.md)** — can now cross-reference every directive name in `nginx/signals.conf`; drift guard (`TestCrossArtifactDriftGuard` in plan 04) will assert the placeholder matches the runbook's sed command.
- No blockers.

## Threat Flags

None. All security-relevant surface introduced by this plan (TLS terminator on 443, rate-limit on /healthz, ACME webroot carve-out, HSTS header) is already covered by the plan's `<threat_model>` (T-12-01 accept, T-12-02 mitigate, T-12-06 mitigate) and by the committed test suite.

## TDD Gate Compliance

Plan 12-01 is `type: execute` (not plan-level `type: tdd`) but Task 1 carries `tdd="true"`, so the task-level RED/GREEN gates apply:
- RED gate: `test(12-01): add failing structural tests for nginx/signals.conf` — commit `6226266`. All 34 tests error on fixture (config file absent).
- GREEN gate: `feat(12-01): add nginx/signals.conf — 443-only TLS edge for signals app` — commit `15b1c5b`. All 34 tests pass.
- REFACTOR gate: not needed; minimal code was correct on first write.

Gate sequence: RED (6226266) → GREEN (15b1c5b) confirmed in git log.

## Self-Check: PASSED

- `test -f nginx/signals.conf` → FOUND
- `test -f tests/test_nginx_signals_conf.py` → FOUND
- `test -f .planning/phases/12-https-domain-wiring/deferred-items.md` → FOUND
- `git log --oneline -5 | grep 6226266` → FOUND (Task 1 RED)
- `git log --oneline -5 | grep 15b1c5b` → FOUND (Task 2 GREEN)
- `git log --oneline -5 | grep a6441dd` → FOUND (deferred-items log)
- `pytest tests/test_nginx_signals_conf.py -q` → 34 passed, 0 failed
- `pytest -q` → 821 passed, 16 failed (same 16 pre-existing failures; no regressions)

---
*Phase: 12-https-domain-wiring*
*Plan: 01*
*Completed: 2026-04-24*
