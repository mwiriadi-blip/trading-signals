---
phase: 12-https-domain-wiring
reviewed: 2026-04-25T00:00:00Z
depth: standard
files_reviewed: 8
files_reviewed_list:
  - deploy.sh
  - nginx/signals.conf
  - notifier.py
  - tests/regenerate_notifier_golden.py
  - tests/test_deploy_sh.py
  - tests/test_nginx_signals_conf.py
  - tests/test_notifier.py
  - tests/test_setup_https_doc.py
findings:
  critical: 0
  warning: 0
  info: 4
  total: 4
status: issues_found
diff_base: ca8431502225437807bbcdbf86286f4b22783b90
---

# Phase 12 Code Review

**Depth:** standard
**Files Reviewed:** 8

## Summary

Phase 12 is **clean** at the correctness + security level. The changes are small, well-documented, and consistently applied:

- `notifier.py` correctly removes the `_EMAIL_FROM` constant, threads `from_addr` as a keyword-only arg through `compose_email_body` → `_render_footer_email`, and adds early-return `missing_sender` paths in both `send_daily_email` (line 1411-1414) and `send_crash_email` (line 1525-1530) BEFORE any disk write or Resend call. `SendStatus` discipline is preserved (2-field, no `attempts=0`). All 38+ test call sites updated with explicit `from_addr=` kwargs; the autouse fixture pins the env var module-wide.
- `nginx/signals.conf` correctly omits `listen 80`, `ssl_certificate*`, and `0.0.0.0` (per certbot ownership rationale). HSTS is at server scope only, with the exact WEB-04 value, no `preload`. ACME carve-out has no `limit_req`. TLS posture is Mozilla Intermediate. All security headers carry `always`.
- `deploy.sh` gates the nginx reload on both `[ -f nginx/signals.conf ]` AND `command -v nginx &>/dev/null`, places the block after the `/healthz` smoke test and before the commit-hash echo, and uses `sudo -n` (PATH-relative; secure_path resolves).
- `tests/regenerate_notifier_golden.py` correctly uses `setdefault` for operator override and threads the explicit kwarg.
- The 4 new test files (test_nginx_signals_conf, test_setup_https_doc, TestNginxReloadHook + TestEmailFromEnvVar classes) all carry sensible assertions, including drift guards across 4 cross-file pairs.

Tests confirmed by orchestrator: 293 passed (Phase 12 slice) + 822 passed (full suite excluding pre-existing weekend-clock failures in `test_main.py`, documented in `deferred-items.md`).

Critical security/correctness paths intact: `html.escape` at leaf preserved; `api_key` redaction untouched; `from_addr` escaped in `_render_footer_email:1151`.

**0 critical · 0 warning · 4 info.** All findings are optional polish — none reflect a correctness, security, or quality defect that warrants a fix before phase close.

---

## Info

### IN-01 — Comment-stripping in `test_no_unconditional_nginx_reference_before_gate` is line-prefix-only

**File:** `tests/test_deploy_sh.py:275-280`

**Issue:** The pre-gate scan filters lines via `line.lstrip().startswith('#')`, which removes whole-line comments but does not strip inline trailing comments like `some_cmd  # nginx note`. There are no such lines in the current `deploy.sh`, so the test passes correctly today — but a future maintainer adding a trailing inline comment containing the word `nginx` would silently get a false positive.

**Fix (optional robustness):**
```python
pre_gate_code = '\n'.join(
  line.split('#', 1)[0]  # also strip inline trailing comments
  for line in pre_gate.splitlines()
  if not line.lstrip().startswith('#')
)
```
Or leave as-is and add a comment noting "whole-line comments only — no inline-trailing-`#` handling."

### IN-02 — `_render_footer_email` and `compose_email_body` have asymmetric `from_addr` arity

**File:** `notifier.py:1134-1136` and `notifier.py:1158-1164`

**Issue:** `compose_email_body` declares `from_addr` as **keyword-only** (after `*,`) per the deliberate fail-loud-on-drift rationale (line 1180: "no default is deliberate"). But `_render_footer_email` accepts `from_addr` as a **positional third arg**. The two-call internal arity is legitimate (private helper, exactly one caller), but the asymmetry could mislead a future contributor extending the formatter chain into thinking positional is the convention.

**Fix (optional consistency):**
```python
def _render_footer_email(
  state: dict, now: datetime, *, from_addr: str,
) -> str:
```
And update the single internal call at `notifier.py:1200` to pass `from_addr=from_addr`. Zero behavior change.

### IN-03 — ACME location regex `[^}]*` would break if nested braces are added

**File:** `tests/test_nginx_signals_conf.py:188-198`

**Issue:** `test_acme_location_has_no_limit_req` uses `r'location\s+/\.well-known/acme-challenge/\s*\{([^}]*)\}'` which works today because the body `try_files $uri =404;` contains no `}`. If a future maintainer adds an `if (...) { ... }` block inside the ACME location, the regex stops at the inner `}` and the test silently checks only the leading fragment — could miss a `limit_req` outside the inner block.

**Fix (optional defensive):**
```python
m = re.search(
  r'location\s+/\.well-known/acme-challenge/\s*\{([^}]*)\}',
  conf_text, re.DOTALL,
)
assert m is not None, 'ACME challenge location block not found'
body = m.group(1)
assert '{' not in body, 'nested braces not handled by this regex — extend test'
assert 'limit_req' not in body, ...
```

### IN-04 — HSTS scope guard splits on `'location '` with trailing space

**File:** `tests/test_nginx_signals_conf.py:148-155`

**Issue:** `test_hsts_not_inside_location` splits on the literal token `'location '` (with trailing space). Works for the committed file but would miss `location\t/...` (tab) or any future formatting tweak with non-space whitespace.

**Fix (optional robustness):**
```python
chunks = re.split(r'\blocation\s+', conf_text)
```
Handles tabs and multi-space delimiters.

---

## Items Confirmed Clean

- **`_EMAIL_FROM` constant removal (D-16):** `grep -cE "(^|[^A-Z_])_EMAIL_FROM\s*=" notifier.py` → 0. All 38+ test call sites pass explicit `from_addr=` kwarg.
- **`SendStatus` 2-field discipline:** `grep -c "attempts=" notifier.py` → 0.
- **Missing-sender early return placement:** BEFORE `_post_to_resend` call AND before any disk write. Tests assert `requests.post` not called AND `last_email.html` not created.
- **HSTS exact value + no preload:** grep-verified in `nginx/signals.conf`; `preload` absent.
- **ACME carve-out has NO `limit_req`:** regex-verified; structural test in place.
- **Security headers at server scope with `always` flag:** all four (HSTS, X-Content-Type-Options, X-Frame-Options, Referrer-Policy) confirmed.
- **`deploy.sh` gate:** both `[ -f nginx/signals.conf ]` AND `command -v nginx &>/dev/null` checked; `sudo -n` fail-fast; no absolute paths in deploy.sh itself.
- **Cross-artifact drift guard (7 assertions)** including NEW `test_env_path_matches_systemd_unit` (12-REVIEWS.md LOW) validated against `systemd/trading-signals-web.service`'s `EnvironmentFile=-/home/trader/trading-signals/.env`.
- **Regenerator idempotency:** `setdefault` pattern keeps operator override viable; explicit `from_addr=` kwarg threaded.

---

## Audit Trail

- **2026-04-25** — Standard-depth review across 8 files (deploy.sh, nginx/signals.conf, notifier.py, 5 test files). Diff base: `ca84315` (pre-Phase-12 baseline). 0 critical · 0 warning · 4 info (all optional polish: test-regex robustness, signature-arity consistency, comment-strip granularity).
