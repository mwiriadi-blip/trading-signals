# Phase 12: HTTPS + Domain Wiring — Pattern Map

**Mapped:** 2026-04-24
**Files analyzed:** 10 (3 NEW, 7 modified/extended)
**Analogs found:** 8 / 10 (2 flagged as NEW — `nginx/signals.conf` + its tests; no prior nginx config or nginx-config test lives in the repo)

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `nginx/signals.conf` (NEW) | config (edge reverse-proxy + TLS + rate-limit template) | request-response (edge termination) | `systemd/trading-signals-web.service` — "committed config with hardcoded + placeholder operator values" shape | role-match (nginx has no prior codebase analog; systemd unit is structural sibling for the "committed config file" idiom) |
| `tests/test_nginx_signals_conf.py` (NEW) | test (structural invariants on a committed config file) | transform (file → parsed → asserted) | `tests/test_web_systemd_unit.py` — class-per-concern, fixture-scoped module-level text read, assertion style | role-match (configparser replaced by regex — nginx has no INI-style parser in stdlib; test SHAPE copies verbatim) |
| `notifier.py` (MODIFY — env-var refactor) | I/O adapter (email dispatch) | request-response (Resend POST) | current `notifier.py` itself — `RESEND_API_KEY` env-var read at `notifier.py:1417` (self-analog; mirror the read/degrade shape for `SIGNALS_EMAIL_FROM`) | exact (1:1 template from adjacent env-var read in same file) |
| `tests/test_notifier.py::TestEmailFromEnvVar` (NEW — 3 tests) | test (unit, env-var + mocked HTTP + caplog + warning spy) | request-response + event-driven | `tests/test_main.py::TestPushStateToGit::test_push_failure_logs_error_and_appends_warning` (lines 2085-2136) + `tests/test_notifier.py::TestSendDispatch` (lines 1056-1195) | exact (monkeypatch.setenv + caplog.set_level + `_fake_post` spy + SendStatus assertion) |
| `tests/test_notifier.py::TestGoldenEmail` (MODIFY — autouse fixture) | test (fixture injection into existing class) | N/A (setenv side-effect) | **NEW PATTERN in this file** — no `autouse=True` fixture exists in test_notifier.py today. Cross-file analog: RESEARCH.md §Example 2 (pattern sketch); `tests/conftest.py` is empty | partial-match (autouse-fixture-on-class idiom is standard pytest but not yet used in this repo for env-var pinning) |
| `tests/regenerate_notifier_golden.py` (MODIFY — inject env var before render) | script (offline golden regenerator) | transform | current `regenerate_notifier_golden.py` (self-analog) | exact (insert `os.environ['SIGNALS_EMAIL_FROM'] = ...` before `compose_email_body` call; OR pass `from_addr=` kwarg through) |
| `deploy.sh` (MODIFY — nginx reload hook) | operator script (bash) | event-driven (conditional reload on deploy) | current `deploy.sh` lines 48-51 — existing `sudo -n systemctl restart` pair (self-analog; append new gated block immediately after) | exact (same `sudo -n <path>` idiom; new `if [ -f ... ] && command -v ...` gate is a NEW IDIOM — Phase 11 deploy.sh uses no `command -v` gating today) |
| `tests/test_deploy_sh.py` (MODIFY — TestNginxReloadHook) | test (bash script text-assertions) | transform (file-read → regex) | current `tests/test_deploy_sh.py::TestDeployShSequence` lines 80-150 (self-analog; new class below, same `deploy_lines` fixture + `_line_index` helper) | exact (text-only assertion style; no bash mocks used anywhere in repo) |
| `.planning/phases/12-https-domain-wiring/SETUP-HTTPS.md` (NEW) | operator runbook (markdown) | N/A | Phase 11 `SETUP-DROPLET.md` (242 lines, 7 sections + Troubleshooting table) PRIMARY + Phase 10 `SETUP-DEPLOY-KEY.md` (234 lines, 6 Steps + Pitfalls bullets + stale-doc banner) SECONDARY | exact (merge both structural idioms — use Phase 11's troubleshooting-TABLE, use Phase 10's stale-doc-banner + Rollback section) |
| `tests/test_setup_https_doc.py` (NEW) | test (runbook structural + drift guard) | transform | `tests/test_setup_droplet_doc.py` (193 lines — class-per-section grep + `TestCrossArtifactDriftGuard`) | exact (copy class shape; drift guards cross-reference `deploy.sh` + `nginx/signals.conf`) |

---

## Pattern Assignments

### `nginx/signals.conf` (NEW — config template)

**Structural analog:** `systemd/trading-signals-web.service` (Phase 11, 31 lines). The common shape is "file committed to repo with a mix of hardcoded values (`User=trader`) and operator-owned ones consumed via EnvironmentFile, plus a comment header". `nginx/signals.conf` inherits this shape: hardcoded TLS directives + committed placeholder `<owned-domain>` that the operator `sed`s at install time.

**NEW PATTERN FLAG:** there is no prior nginx config in the repo. All directives come from RESEARCH.md §Pattern 1 (authoritative) — planner uses RESEARCH.md 12-RESEARCH.md:290-383 as the literal template.

**Committed-file-with-placeholder idiom** — template from Phase 11 unit file:

```ini
# Source: systemd/trading-signals-web.service (lines 1-31)
[Unit]
Description=Trading Signals — FastAPI web process
After=network.target
Wants=trading-signals.service

[Service]
Type=simple
User=trader                                            # HARDCODED value
WorkingDirectory=/home/trader/trading-signals          # HARDCODED absolute path
EnvironmentFile=-/home/trader/trading-signals/.env     # optional (-) operator-owned file
ExecStart=/home/trader/trading-signals/.venv/bin/uvicorn web.app:app \
          --host 127.0.0.1 \
          --port 8000 \
          ...
```

**Apply to `nginx/signals.conf`:**
- hardcoded: TLS protocols, ciphers, security-header values, rate-limit zone, proxy_pass target `127.0.0.1:8000`, `resolver 1.1.1.1 8.8.8.8`
- operator-substituted placeholder: `server_name signals.<owned-domain>.com` (literally `<owned-domain>` until `sed`)
- **NO** `listen 80` block (certbot injects; per RESEARCH.md §Pitfall 1 a dual-listen confuses certbot)
- **NO** `ssl_certificate` / `ssl_certificate_key` lines (certbot injects on first run)
- HSTS `add_header` at `server` scope only, never inside `location` (RESEARCH.md §Pitfall 3: `add_header` in child location nukes parent-scope headers)
- every security header uses the `always` flag (emits on 4xx/5xx too — RESEARCH.md §Pitfall 2)

**Authoritative body to copy verbatim:** 12-RESEARCH.md lines 290-383 (full 443-only server block with TLS tuning + HSTS + carve-out for `/.well-known/acme-challenge/` + `location = /healthz { limit_req ... }` + catch-all `location /`).

**Mandatory directive checklist (extracted from RESEARCH.md §3 + §Pattern 1):**

```nginx
# Source: 12-RESEARCH.md:306-382 [authoritative]
limit_req_zone $binary_remote_addr zone=healthz:10m rate=10r/m;   # at http{} scope

server {
  listen 443 ssl;
  listen [::]:443 ssl;
  http2 on;
  server_name signals.<owned-domain>.com;

  # TLS — Mozilla Intermediate (2024 rev)
  ssl_protocols TLSv1.2 TLSv1.3;
  ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:...;
  ssl_prefer_server_ciphers off;
  ssl_session_cache shared:SSL:10m;
  ssl_session_timeout 1d;
  ssl_session_tickets off;

  # OCSP
  ssl_stapling on;
  ssl_stapling_verify on;
  resolver 1.1.1.1 8.8.8.8 valid=300s;
  resolver_timeout 5s;

  # Security headers — ALL `always` flag, ALL at server scope
  add_header Strict-Transport-Security 'max-age=31536000; includeSubDomains' always;
  add_header X-Content-Type-Options 'nosniff' always;
  add_header X-Frame-Options 'DENY' always;
  add_header Referrer-Policy 'strict-origin-when-cross-origin' always;

  # ACME carve-out (NO limit_req)
  location /.well-known/acme-challenge/ {
    try_files $uri =404;
  }

  # Rate-limited /healthz
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

**Header-comment pattern** (from `systemd/trading-signals-web.service` and research):
```nginx
# nginx/signals.conf — Phase 12
# Committed with <owned-domain> as literal placeholder (D-01).
# Operator substitutes during SETUP-HTTPS.md Step 3:
#   sudo sed -i 's|<owned-domain>|carbonbookkeeping|g' /etc/nginx/sites-available/signals.conf
# On first `certbot --nginx` run, certbot injects:
#   (a) ssl_certificate + ssl_certificate_key lines (marked `# managed by Certbot`)
#   (b) a new `server { listen 80; ... return 301 https://$host$request_uri; }` block
#   (c) temporary location for /.well-known/acme-challenge/ during renewal
```

**Pitfalls flagged for planner:**
- Never hand-write the port-80 redirect block (Pitfall 1 — certbot fights it).
- HSTS must stay at `server` scope, not inside any `location` (Pitfall 3 — `add_header` is replace-not-extend).
- Never rate-limit `/.well-known/acme-challenge/` — nested location carve-out required (Anti-Pattern §3).
- Certbot rate limit is 5 duplicate certs / 168h — always `--dry-run` first (Pitfall 4).

---

### `tests/test_nginx_signals_conf.py` (NEW — config structural test)

**Analog:** `tests/test_web_systemd_unit.py` (Phase 11, 146 lines). Same idiom applies — module-level Path, scope='module' fixture to read file once, class-per-concern.

**NEW PATTERN FLAG:** `configparser` does NOT parse nginx syntax — nginx is not INI-style. Replace with regex-based parsing (stdlib `re`) OR grep-style text assertions via `in`. No new dependency added (research says ZERO new Python deps in Phase 12).

**Fixture pattern** (copy verbatim from `tests/test_web_systemd_unit.py:12-26`):

```python
# Source: tests/test_web_systemd_unit.py:12-26 [VERIFIED]
import re
from pathlib import Path

import pytest

CONF_PATH = Path('nginx/signals.conf')


@pytest.fixture(scope='module')
def conf_text() -> str:
  assert CONF_PATH.exists(), f'nginx config missing: {CONF_PATH}'
  return CONF_PATH.read_text()
```

**Class-per-concern pattern** (adapt `tests/test_web_systemd_unit.py:29-145` class boundaries to nginx concerns):

```python
class TestNginxConfStructure:          # listen 443 ssl, http2 on, server_name present
class TestNginxConfPlaceholder:         # <owned-domain> present; operator-owned sub note
class TestNginxConfTlsTuning:           # Mozilla Intermediate: ssl_protocols, ciphers, off, session_*
class TestNginxConfSecurityHeaders:     # HSTS exact string + XCTO + XFO + RP; `always` flag; server-scope only
class TestNginxConfRateLimit:           # limit_req_zone at http scope; limit_req on /healthz
class TestNginxConfAcmeCarveout:        # /.well-known/acme-challenge/ present; NO limit_req inside
class TestNginxConfProxy:               # proxy_pass http://127.0.0.1:8000 at BOTH /healthz and /
class TestNginxConfForbiddenPatterns:   # NO listen 80; NO ssl_certificate lines; NO 0.0.0.0
```

**Assertion style** (copy text-regex idiom from `tests/test_web_systemd_unit.py:109-111`):

```python
# Source: tests/test_web_systemd_unit.py:109-111 [VERIFIED] — negative check
def test_execstart_does_not_bind_all_interfaces(self, unit_text):
  '''CRITICAL: 0.0.0.0 must NOT appear anywhere.'''
  assert '0.0.0.0' not in unit_text
```

**Apply to nginx:**
```python
# HSTS exact value + always flag (D-11 + WEB-04 SC-2 exact)
def test_hsts_exact_value_with_always(self, conf_text):
  assert "add_header Strict-Transport-Security 'max-age=31536000; includeSubDomains' always;" in conf_text

# Placeholder present, operator-substituted later (D-01)
def test_owned_domain_placeholder_literal(self, conf_text):
  assert 'signals.<owned-domain>.com' in conf_text

# Certbot owns the 80-block (Pitfall 1)
def test_no_listen_80_directive(self, conf_text):
  assert not re.search(r'^\s*listen\s+80\b', conf_text, re.MULTILINE)

# Certbot injects cert paths (RESEARCH §Pattern 1)
def test_no_ssl_certificate_lines_pre_certbot(self, conf_text):
  assert 'ssl_certificate ' not in conf_text
  assert 'ssl_certificate_key ' not in conf_text
```

**Pitfalls flagged for planner:**
- Don't shell out to `nginx -t` in the test — nginx may not be installed in CI (research confirmed). Use `in` / `re.search` / regex against file text only.
- Don't over-specify cipher list as a single-line string match — cipher order may churn. Assert `'ECDHE-' in conf_text` + `'ssl_prefer_server_ciphers off;' in conf_text` instead.

---

### `notifier.py` (MODIFY — `SIGNALS_EMAIL_FROM` env-var refactor)

**Analog:** current `notifier.py` itself — `RESEND_API_KEY` read at `notifier.py:1417-1423` is a direct 1:1 template for the new `SIGNALS_EMAIL_FROM` read.

**Exact lines that touch `_EMAIL_FROM`** (verified via Grep):
- `notifier.py:99` — module-top definition `_EMAIL_FROM = 'signals@carbonbookkeeping.com.au'` — **delete entirely** (D-16)
- `notifier.py:1135` — `def _render_footer_email(state: dict, now: datetime) -> str:` — **extend signature with `from_addr: str`** (research flag: body renderer is the 3rd site, NOT just the 2 D-14/D-15 suggest)
- `notifier.py:1147` — `f'{html.escape(_EMAIL_FROM, quote=True)}</p>'` — **replace `_EMAIL_FROM` with `from_addr` param**
- `notifier.py:1154-1158` — `def compose_email_body(state, old_signals, now) -> str:` — **extend signature with `from_addr: str`** (thread through to `_render_footer_email`)
- `notifier.py:1188` — `+ _render_footer_email(state, now)` — **add `from_addr=from_addr`**
- `notifier.py:1394` — `html_body = compose_email_body(state, old_signals, now)` — **add `from_addr=from_addr`**
- `notifier.py:1427` — `_post_to_resend(api_key, _EMAIL_FROM, to_addr, subject, html_body)` — **replace `_EMAIL_FROM` with `from_addr`**
- `notifier.py:1506` — `from_addr=_EMAIL_FROM,` (inside `send_crash_email`) — **replace with `from_addr` local read**

**Env-var read template** (copy verbatim pattern from `notifier.py:1417-1423` — the `RESEND_API_KEY` read):

```python
# Source: notifier.py:1417-1423 [VERIFIED] — RESEND_API_KEY mirror
api_key = os.environ.get('RESEND_API_KEY')
if not api_key:
  logger.warning(
    '[Email] WARN RESEND_API_KEY missing — wrote %s (fallback)',
    last_email_path,
  )
  return SendStatus(ok=True, reason='no_api_key')
```

**Adapt for `SIGNALS_EMAIL_FROM`** (top of `send_daily_email` body, before `compose_email_subject`, per D-14/D-15):

```python
# D-15: per-send env read; D-14: missing → log ERROR + SendStatus fail, NO Resend call
from_addr = os.environ.get('SIGNALS_EMAIL_FROM', '').strip()
if not from_addr:
  logger.error('[Email] SIGNALS_EMAIL_FROM not set — email skipped')
  return SendStatus(ok=False, reason='missing_sender')
```

**Key differences vs RESEND_API_KEY pattern** (flagged for planner):

| Aspect | RESEND_API_KEY (existing) | SIGNALS_EMAIL_FROM (new) |
|---|---|---|
| Log level | `logger.warning` | **`logger.error`** (D-14 exact — "log ERROR") |
| Return on missing | `SendStatus(ok=True, reason='no_api_key')` (degrade-but-ok) | **`SendStatus(ok=False, reason='missing_sender')`** (fail-loud; orchestrator `_dispatch_email_and_maintain_warnings` appends warning) |
| Fallback disk write | `last_email.html` written pre-check | NONE — `return` before any `compose_email_body` call |
| Empty vs missing | only checks truthy (`if not api_key`) | same — `.strip()` + `if not from_addr` treats `''` same as missing (D-17 test #3) |

**SendStatus shape issue** (RESEARCH §Example 1 line 606, flagged as planner-confirm):

The current `SendStatus` at `notifier.py:84-92` is a **2-field NamedTuple** `(ok: bool, reason: str | None)`. D-14 CONTEXT mentions `attempts=0` which implies a 3rd field. **Recommendation:** stay 2-field. Use `SendStatus(ok=False, reason='missing_sender')` verbatim. Do NOT extend SendStatus — touching it cascades into `main.py::_dispatch_email_and_maintain_warnings` (main.py:533 per context) and every Phase 8 test. Research §Example 1 line 606 logs this as `[ASSUMED]` — planner should confirm with operator but default to 2-field.

**Full signature changes** (authoritative):

```python
# notifier.py:1135 — BEFORE
def _render_footer_email(state: dict, now: datetime) -> str:  # noqa: ARG001

# notifier.py:1135 — AFTER (Phase 12 D-16)
def _render_footer_email(state: dict, now: datetime, from_addr: str) -> str:  # noqa: ARG001

# notifier.py:1154-1158 — BEFORE
def compose_email_body(
  state: dict,
  old_signals: dict,
  now: datetime,
) -> str:

# notifier.py:1154-1158 — AFTER (Phase 12 D-16) — RESEARCH §Pattern 2 recommends KEYWORD-ONLY NO-DEFAULT
def compose_email_body(
  state: dict,
  old_signals: dict,
  now: datetime,
  *,
  from_addr: str,
) -> str:
```

**RESEARCH recommendation:** make `from_addr` keyword-only with NO default (RESEARCH line 442). This fails loudly on signature drift rather than silently using a stale default.

**Log-prefix convention** (CLAUDE.md §Conventions): `[Email]` for all notifier messages. The new `logger.error('[Email] SIGNALS_EMAIL_FROM not set — email skipped')` matches the existing `[Email]` prefix idiom at `notifier.py:1419, 1428, 1432, 1438, 1491, 1498, 1512, 1515, 1518`.

---

### `tests/test_notifier.py::TestEmailFromEnvVar` (NEW — 3 tests per D-17)

**Analog 1 (structural — class shape + SendStatus asserts):** `tests/test_notifier.py::TestSendDispatch` (lines 1056-1195). Same file; same imports; same `FROZEN_NOW`, `SAMPLE_STATE_NO_CHANGE_PATH`, `_FakeResp` helpers available.

**Analog 2 (caplog + warning-spy idiom):** `tests/test_main.py::TestPushStateToGit::test_push_failure_logs_error_and_appends_warning` (lines 2085-2136) — the canonical "log at ERROR + monkeypatch-spy `append_warning` + assert dict-capture" pattern.

**Shared fixture + import pattern** (lines 1062-1076 — exactly the pattern new tests copy):

```python
# Source: tests/test_notifier.py:1062-1076 [VERIFIED]
def test_missing_api_key_writes_last_email_html(
    self, tmp_path, monkeypatch) -> None:
  '''NOTF-08: missing RESEND_API_KEY → write last_email.html + return
  SendStatus(ok=True, reason='no_api_key') — graceful degradation is not
  a failure (Phase 8 D-02).
  '''
  monkeypatch.chdir(tmp_path)
  monkeypatch.delenv('RESEND_API_KEY', raising=False)
  state = json.loads(SAMPLE_STATE_NO_CHANGE_PATH.read_text())
  result = send_daily_email(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
  assert result.ok is True
  assert result.reason == 'no_api_key'
```

**Spy-on-fake-post pattern** (lines 1163-1177 — the captured-dict idiom for asserting payload fields):

```python
# Source: tests/test_notifier.py:1163-1177 [VERIFIED] — adapt for `from` field assert
def test_respects_signals_email_to_env_override(
    self, tmp_path, monkeypatch) -> None:
  monkeypatch.chdir(tmp_path)
  monkeypatch.setenv('RESEND_API_KEY', 'k')
  monkeypatch.setenv('SIGNALS_EMAIL_TO', 'custom@example.com')
  captured: list[dict] = []

  def _fake_post(url, **kw):
    captured.append({'url': url, **kw})
    return _FakeResp(200)

  monkeypatch.setattr('notifier.requests.post', _fake_post)
  state = json.loads(SAMPLE_STATE_NO_CHANGE_PATH.read_text())
  send_daily_email(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
  assert captured[0]['json']['to'] == ['custom@example.com']
```

**Apply shape to `TestEmailFromEnvVar::test_from_addr_reads_env_var`** — same shape, assert `captured[0]['json']['from'] == 'test@example.com'`.

**"Not-called" assertion pattern** (caplog.set_level(logging.ERROR) + zero-call counter) — combine Phase 10 `TestPushStateToGit` spy idiom with Phase 6 `TestSendDispatch.test_unexpected_exception_swallowed` (lines 1127-1144):

```python
# Source: tests/test_main.py:2112-2126 [VERIFIED] — append_warning spy idiom
warnings_captured: list = []

def _fake_append_warning(state, source, message, now=None):
  warnings_captured.append({
    'source': source, 'message': message, 'now': now,
  })
  return state

monkeypatch.setattr(subprocess, 'run', _fake_run)
monkeypatch.setattr(
  'main.state_manager.append_warning', _fake_append_warning,
)
caplog.set_level(logging.ERROR)
# ... exercise ...
assert '[State] git push failed' in caplog.text
assert len(warnings_captured) == 1
assert warnings_captured[0]['source'] == 'state_pusher'
```

**Planner note:** D-14 says `append_warning` is called by the **orchestrator** (`main._dispatch_email_and_maintain_warnings`), not by `notifier.send_daily_email` directly. So `TestEmailFromEnvVar` in `test_notifier.py` should ONLY assert the `SendStatus(ok=False, reason='missing_sender')` return + caplog ERROR line + zero `requests.post` calls. The downstream orchestrator-side warning-append behavior is an orthogonal Phase 8 test path.

**RESEARCH §Example 3 authoritative 3-test body:** 12-RESEARCH.md lines 646-720 — copy verbatim with project's 2-space indent and single quotes.

---

### `tests/test_notifier.py::TestGoldenEmail` (MODIFY — autouse fixture)

**NEW PATTERN IN THIS FILE:** grep confirmed `autouse=True` appears zero times in `tests/test_notifier.py` today. The `@pytest.fixture(autouse=True)` class-scoped env-setenv idiom must be introduced fresh. Standard pytest pattern (documented widely), so no cross-repo analog needed.

**Authoritative body:** 12-RESEARCH.md §Example 2 lines 613-635. Place immediately after the class docstring at `tests/test_notifier.py:1237-1243`.

**Insertion site** (after line 1243, before `test_golden_with_change_matches_committed` at line 1244):

```python
# INSERT at tests/test_notifier.py:~1243.5 (after class docstring, before first test)
@pytest.fixture(autouse=True)
def _stable_from_addr(self, monkeypatch):
  '''Phase 12 D-19: pin SIGNALS_EMAIL_FROM to the golden-committed sender
  so TestGoldenEmail stays byte-equal across env configurations.
  autouse=True applies to every test in this class; function-scope means
  each test gets a fresh env mutation (matches pytest default).'''
  monkeypatch.setenv('SIGNALS_EMAIL_FROM', 'signals@carbonbookkeeping.com.au')
```

**Also update every compose_email_body call** in the class to pass `from_addr` kwarg explicitly (belt-and-braces — RESEARCH §Example 2 line 638):

```python
# BEFORE (tests/test_notifier.py:1247)
rendered = compose_email_body(state, old_signals, FROZEN_NOW)

# AFTER (Phase 12)
rendered = compose_email_body(
  state, old_signals, FROZEN_NOW,
  from_addr='signals@carbonbookkeeping.com.au',  # pinned to committed golden value
)
```

**Also update sibling tests** (per D-19: "any sibling Resend-payload tests"). Grep confirmed **44** `compose_email_body(...)` call sites in `tests/test_notifier.py` (lines 231, 237, 258, 264, 269, 274, 279, 284, 289, 297, 305, 311, 317, 322, 334, 342, 352, 357, 363, 373, 380, 387, 397, 402, 407, 412, 423, 428, 433, 447, 453, 467, 484, 504, 526, + TestGoldenEmail's 3 + TestSendDispatch's 8). All 44 need the `from_addr=` kwarg once compose signature changes.

**Cleanest refactor strategy** (planner decides, two viable options):

**Option A — module-level autouse fixture** (covers ALL tests in file; does NOT require updating 44 call sites' signatures if `compose_email_body` preserves a default arg):

```python
# tests/test_notifier.py — insert at module scope after imports
@pytest.fixture(autouse=True)
def _pin_signals_email_from(monkeypatch):
  '''Phase 12: pin SIGNALS_EMAIL_FROM for every test in this module so
  golden renders, payload assertions, and compose_* paths stay deterministic.'''
  monkeypatch.setenv('SIGNALS_EMAIL_FROM', 'signals@carbonbookkeeping.com.au')
```

**Option B — class-level autouse on TestGoldenEmail only + explicit kwarg everywhere.** RESEARCH recommends this (lines 442, 617-623) but it requires 44 call-site edits. Sharper fail signals if someone reintroduces a default.

**Recommended:** Option A (module-level autouse) + explicitly override in `TestEmailFromEnvVar` where test #2 needs `delenv` and test #3 needs `setenv('')`. Pytest's last-setenv-wins inside a single test.

---

### `tests/regenerate_notifier_golden.py` (MODIFY — inject env var)

**Analog:** current `tests/regenerate_notifier_golden.py` (self-analog, 92 lines). Insert one line before `main()` calls `regenerate_one`.

**Insertion site** (line ~51, after `FROZEN_NOW = PERTH.localize(datetime(2026, 4, 22, 9, 0))`):

```python
# Source: tests/regenerate_notifier_golden.py:49-51 [VERIFIED] — current
PERTH = pytz.timezone('Australia/Perth')
FROZEN_NOW = PERTH.localize(datetime(2026, 4, 22, 9, 0))

# Phase 12 D-16: _EMAIL_FROM is gone; regenerator must set SIGNALS_EMAIL_FROM
# so goldens render with the stable operator-verified sender (matching the
# committed HTMLs' existing `signals@carbonbookkeeping.com.au` footer).
import os
os.environ['SIGNALS_EMAIL_FROM'] = 'signals@carbonbookkeeping.com.au'
```

**Alternative (if planner chose keyword-only `from_addr` with NO default in `compose_email_body`):** pass explicit kwarg into `regenerate_one`:

```python
# tests/regenerate_notifier_golden.py:71 — BEFORE
html = compose_email_body(state, old_signals, FROZEN_NOW)

# AFTER
html = compose_email_body(
  state, old_signals, FROZEN_NOW,
  from_addr='signals@carbonbookkeeping.com.au',
)
```

**Double-run idempotency is the acceptance gate** (research line 480): after running regenerator twice with the fixture env value, `git diff tests/fixtures/notifier/` must show zero bytes. RESEARCH Pitfall 9 (lines 545-549) flags this as the intentional drift-check surface.

**Verification step for plan:**
```bash
grep -l 'carbonbookkeeping' tests/fixtures/notifier/*.html  # expect all 3 files
```

---

### `deploy.sh` (MODIFY — nginx reload hook)

**Analog:** current `deploy.sh` lines 48-51 (self-analog). The Phase 11 `sudo -n systemctl restart <unit>` pattern is the direct template for the new `sudo -n nginx -t` + `sudo -n systemctl reload nginx` pair.

**Current insertion site** (`deploy.sh:48-65` — after the two restart calls, after the smoke-test retry loop, before the final commit echo):

```bash
# Source: deploy.sh:48-69 [VERIFIED]
# D-23 step 6: restart BOTH units via TWO `sudo -n` calls (REVIEWS HIGH #4)
echo "[deploy] restarting services..."
sudo -n systemctl restart trading-signals
sudo -n systemctl restart trading-signals-web

# D-23 step 7: smoke test — retry loop (REVIEWS HIGH #3)
echo "[deploy] smoke testing /healthz..."
for i in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS --max-time 2 http://127.0.0.1:8000/healthz > /dev/null 2>&1; then
    echo "[deploy] /healthz OK after ${i} attempt(s)"
    break
  fi
  ...
done

# <-- INSERT D-20 nginx reload hook HERE -->

# D-23 step 8: success
COMMIT=$(git rev-parse --short HEAD)
echo "[deploy] deploy complete. commit=${COMMIT}"
```

**New D-20 block** (authoritative, from 12-RESEARCH.md:728-735):

```bash
# D-20 (Phase 12): nginx config test + reload hook, gated.
# Pre-Phase-12 droplets (no nginx installed) skip this silently.
if [ -f nginx/signals.conf ] && command -v nginx &>/dev/null; then
  echo "[deploy] nginx config detected — testing + reloading..."
  sudo -n nginx -t
  sudo -n systemctl reload nginx
  echo "[deploy] nginx reloaded"
fi
```

**NEW IDIOM FLAG:** `command -v nginx &>/dev/null` is **not used anywhere in deploy.sh today**. Grep confirmed zero prior occurrences in `deploy.sh` or any project bash script. This is a new idiom Phase 12 introduces; the plan should call it out as "new guard-pattern for optional-feature hooks".

**sudoers extension pattern** (Phase 11 analog at `SETUP-DROPLET.md:70`):

```
# Phase 11 — current
trader ALL=(root) NOPASSWD: /usr/bin/systemctl restart trading-signals, /usr/bin/systemctl restart trading-signals-web

# Phase 12 — extend to four comma-separated rules (one line, per RESEARCH §Example 5)
trader ALL=(root) NOPASSWD: /usr/bin/systemctl restart trading-signals, /usr/bin/systemctl restart trading-signals-web, /usr/sbin/nginx -t, /usr/bin/systemctl reload nginx
```

**`which nginx` path verification** (Phase 11 `SETUP-DROPLET.md:50-55` analog):
```bash
# Phase 11 template — use verbatim shape for Phase 12
which systemctl
# Expected: /usr/bin/systemctl

# Phase 12 extension
which nginx
# Expected: /usr/sbin/nginx (Ubuntu 22.04/24.04 default — nginx is admin tool, NOT /usr/bin)
```

**Pitfalls flagged for planner:**
- Ubuntu installs nginx to `/usr/sbin/nginx`, NOT `/usr/bin/nginx` (RESEARCH §Pitfall 7). If operator typos the sudoers entry, `sudo -n nginx -t` fails fast with "sudo: a password is required" — every subsequent deploy fails.
- Absolute paths only in sudoers. NEVER `NOPASSWD: /usr/sbin/nginx *` (wildcard) — RESEARCH Anti-Pattern §4 cites Compass Security wildcard-sudo escalation.
- `command -v nginx &>/dev/null` gate ensures pre-Phase-12 droplets (no nginx installed) don't fail deploy.sh. Tested by the new `TestNginxReloadHook` negative assertion.

---

### `tests/test_deploy_sh.py::TestNginxReloadHook` (MODIFY — add test class)

**Analog:** current `tests/test_deploy_sh.py::TestDeployShSequence` (lines 80-150). Same file, same `deploy_text` and `deploy_lines` fixtures, same `_line_index()` helper. Text-assertion style — zero bash execution in tests (except the one `bash -n` syntax check).

**CONFIRMED PATTERN:** `tests/test_deploy_sh.py` has NO bash mocks of `sudo`/`systemctl`/`nginx`. The test style is **"committed-script-as-data, asserted via `re.search` and `in` against file text"**. This is the correct pattern for Phase 12 — no fake-PATH scripts, no mock command directories.

**Verified by Grep:** single `subprocess.run` in the file (line 53 — `bash -n` syntax check only).

**Fixture reuse** (lines 16-36 — already provides everything Phase 12 needs):

```python
# Source: tests/test_deploy_sh.py:16-36 [VERIFIED]
DEPLOY_SH = Path('deploy.sh')

@pytest.fixture(scope='module')
def deploy_text() -> str:
  assert DEPLOY_SH.exists(), f'deploy.sh missing: {DEPLOY_SH}'
  return DEPLOY_SH.read_text()

@pytest.fixture(scope='module')
def deploy_lines(deploy_text: str) -> list:
  return deploy_text.splitlines()

def _line_index(lines: list, pattern: str) -> int:
  regex = re.compile(pattern)
  for i, line in enumerate(lines):
    if regex.search(line):
      return i
  raise AssertionError(f'no line matched pattern: {pattern!r}')
```

**Ordering-assertion pattern** (lines 122-150 — copy verbatim):

```python
# Source: tests/test_deploy_sh.py:122-150 [VERIFIED] — 5 cross-step ordering tests
def test_order_fetch_before_pull(self, deploy_lines):
  f = _line_index(deploy_lines, r'git fetch origin main')
  p = _line_index(deploy_lines, r'git pull --ff-only origin main')
  assert f < p
```

**Apply to Phase 12 — TestNginxReloadHook (new class body):**

```python
class TestNginxReloadHook:
  '''Phase 12 D-20: conditional nginx -t + reload nginx hook.'''

  def test_nginx_gated_if_present(self, deploy_text):
    '''D-20: gate `[ -f nginx/signals.conf ] && command -v nginx` before reload.'''
    assert re.search(
      r'if \[ -f nginx/signals\.conf \] && command -v nginx',
      deploy_text,
    )

  def test_nginx_config_test_call(self, deploy_text):
    '''D-20: `sudo -n nginx -t` must appear inside the gate.'''
    assert re.search(r'sudo -n nginx -t', deploy_text)

  def test_nginx_reload_call(self, deploy_text):
    '''D-20: `sudo -n systemctl reload nginx` must appear inside the gate.'''
    assert re.search(r'sudo -n systemctl reload nginx', deploy_text)

  def test_nginx_hook_after_smoke_test(self, deploy_lines):
    '''D-20 ordering: reload block lives AFTER /healthz retry loop.'''
    c = _line_index(deploy_lines, r'curl -fsS --max-time 2 http://127\.0\.0\.1:8000/healthz')
    n = _line_index(deploy_lines, r'if \[ -f nginx/signals\.conf \]')
    assert c < n

  def test_nginx_hook_before_commit_echo(self, deploy_lines):
    '''D-20 ordering: reload block lives BEFORE final commit-hash echo.'''
    n = _line_index(deploy_lines, r'sudo -n systemctl reload nginx')
    h = _line_index(deploy_lines, r'git rev-parse --short HEAD')
    assert n < h

  def test_nginx_no_unconditional_reload(self, deploy_text):
    '''Negative: reload MUST NOT be called outside the gate (pre-Phase-12 droplets skip).'''
    # Split on the gate-start line; lines before the gate must not contain `nginx`.
    pre_gate = deploy_text.split('if [ -f nginx/signals.conf ]')[0]
    assert 'nginx' not in pre_gate.lower(), (
      'nginx reference found BEFORE the gate — pre-Phase-12 droplets would fail'
    )

  def test_nginx_hook_skipped_sentinel(self, deploy_text):
    '''`command -v nginx` gate skips silently if nginx not installed.'''
    assert 'command -v nginx' in deploy_text
```

**Pitfalls flagged for planner:**
- `_line_index` raises `AssertionError` if pattern not found — tests for absence use `assert pattern not in text` form, NOT `_line_index`.
- Don't try to execute the gated block — the CI runner may not have nginx installed; the test only asserts TEXT presence/ordering.

---

### `.planning/phases/12-https-domain-wiring/SETUP-HTTPS.md` (NEW — operator runbook)

**PRIMARY analog:** `SETUP-DROPLET.md` (Phase 11, 242 lines, REPO ROOT). Use its section structure + troubleshooting-as-table format.

**SECONDARY analog:** `.planning/phases/10-foundation-v1-0-cleanup-deploy-key/SETUP-DEPLOY-KEY.md` (234 lines). Use its stale-doc banner at top + Pitfalls-as-bullets + Rollback bullets.

**Phase 11 section skeleton to copy** (`SETUP-DROPLET.md` top → bottom):

```markdown
# Source: SETUP-DROPLET.md [VERIFIED structure]

# SETUP-DROPLET.md — Trading Signals web-layer one-time setup

**Phase:** 11 (Web Skeleton — FastAPI + uvicorn + systemd)
**Audience:** Operator (Marc), running once on the DigitalOcean droplet.
**Prerequisites:**
- Droplet provisioned (Ubuntu LTS 22.04 or 24.04, systemd, public IP)
- Repo cloned to `/home/trader/trading-signals` with `.venv` populated
- Logged in as `trader` (or able to `sudo -u trader`) on the droplet
...

This runbook is run ONCE per droplet. After completion, all updates flow through `bash deploy.sh`.

---

## Install systemd unit
## Install sudoers entry for trader
## Verify port binding (WEB-02 / SC-4)
## Verify deploy.sh end-to-end (INFRA-04 / SC-3)
## Verify boot persistence (WEB-01 / SC-1)
## Troubleshooting      # TABLE with Symptom | Likely cause | Fix
## What's NOT in this doc

*Last updated: Phase 11 (Web Skeleton). 2026-04-24 post-cross-AI-review.*
```

**Phase 10 patterns to borrow** (`SETUP-DEPLOY-KEY.md:18-23` — stale-doc banner):

```markdown
# Source: SETUP-DEPLOY-KEY.md:18-23 [VERIFIED]
> **Read first: `docs/DEPLOY.md` is stale.** That file still
> describes GitHub Actions as the primary deployment path (v1.0 era).
> It has not been rewritten yet — rewrite is deferred to a post-
> Phase-12 docs-sweep phase ...
```

**Phase 10 Pitfalls + Rollback sections** (`SETUP-DEPLOY-KEY.md:190-230` — bullet list format, verbatim structure):

```markdown
## Pitfalls

- **systemd WorkingDirectory.** ...explanation...

- **Clock drift.** ...explanation...

- **Rollback.** If the droplet path must be abandoned, reverse... via
  `git mv ...` and re-enable...
```

**Phase 12-specific 10-section structure (per D-21 + RESEARCH §Example 6):**

| § | Section | Template source |
|---|---------|----------------|
| 1 | Prerequisites (domain, A-record, Resend verified, firewall ports) | Phase 11 `SETUP-DROPLET.md` §Prerequisites |
| 2 | Install nginx + certbot (`apt install`) | Phase 11 `SETUP-DROPLET.md` §Install systemd unit (bash block + expected output) |
| 3 | Copy `nginx/signals.conf` + `sed` placeholder + symlink | Phase 11 (sudoers file install pattern) |
| 4 | Run certbot (with `--dry-run` first per Pitfall 4) | NEW (no analog — use RESEARCH §Example 6) |
| 5 | Verify HTTPS + HSTS (curl + openssl s_client) | Phase 11 `SETUP-DROPLET.md` §Verify port binding |
| 6 | Confirm `certbot.timer` active + `--dry-run` renewal | NEW (use `systemctl list-timers` pattern) |
| 7 | Add `SIGNALS_EMAIL_FROM` to `.env` + restart + verify | Phase 11 pattern + `python main.py --force-email` |
| 8 | Extend sudoers (`/usr/sbin/nginx -t` + `/bin/systemctl reload nginx`) | Phase 11 `SETUP-DROPLET.md` §Install sudoers — EXTEND existing line |
| 9 | Troubleshooting TABLE | Phase 11 `SETUP-DROPLET.md:218-228` — same 3-column markdown table |
| 10 | Rollback | Phase 10 `SETUP-DEPLOY-KEY.md:208-214` — bullet-list "disable nginx config + revert to Phase 11 localhost-only" |

**Troubleshooting table entries Phase 12 MUST include** (from RESEARCH.md §Pitfalls):
- DNS not propagated (Pitfall 6)
- Let's Encrypt rate limit 5/168h (Pitfall 4)
- `sudo -n nginx -t` prompts for password → sudoers path mismatch (Pitfall 7)
- nginx syntax error after `sed` (forgot placeholder substitution)
- port 80/443 not open in ufw
- Resend quota / domain unverified (direct to Resend dashboard)
- SIGNALS_EMAIL_FROM missing in `.env` → email skipped with warning (D-14)

**Rollback section content** (Phase 10 structural template + Phase-12 specifics):

```markdown
## Rollback

If HTTPS must be abandoned (domain issue, certbot regression, etc.), revert to
Phase 11 localhost-only posture:

- Disable the nginx site: `sudo rm /etc/nginx/sites-enabled/signals.conf`
- `sudo systemctl reload nginx` (or `sudo systemctl stop nginx` entirely)
- Revert sudoers extension: `sudo visudo -f /etc/sudoers.d/trading-signals-deploy`
  and remove `/usr/sbin/nginx -t, /usr/bin/systemctl reload nginx` from the line
- Remove `SIGNALS_EMAIL_FROM` from `/etc/trading-signals/.env` (daily email will
  skip with warning until restored per D-14)
- FastAPI remains on `127.0.0.1:8000`; `deploy.sh` still works (gate `[ -f nginx/signals.conf ]`
  is false once the file is symlinked out, so reload hook self-skips)
- The `nginx/signals.conf` file stays in git — rollback does NOT revert the commit
```

**Footer pattern** (copy from `SETUP-DROPLET.md:239-242` + Phase 10's STATE.md note):

```markdown
*Last updated: Phase 12 (HTTPS + Domain Wiring). 2026-04-24.*
*Run this runbook ONCE per droplet. Subsequent updates use `bash deploy.sh` (nginx reload hook gated on file presence).*
*Record completion date in STATE.md §Accumulated Context once Step 5 curl shows the Let's Encrypt cert chain.*
```

---

### `tests/test_setup_https_doc.py` (NEW — runbook structural test)

**Analog:** `tests/test_setup_droplet_doc.py` (Phase 11, 193 lines). Same file-read pattern, same `Path(...)` module constant, same class-per-section structure. Almost-verbatim template.

**Fixture pattern** (lines 11-19 — copy verbatim):

```python
# Source: tests/test_setup_droplet_doc.py:11-19 [VERIFIED]
import re
from pathlib import Path

import pytest

DOC_PATH = Path('.planning/phases/12-https-domain-wiring/SETUP-HTTPS.md')

@pytest.fixture(scope='module')
def doc_text() -> str:
  assert DOC_PATH.exists(), f'doc missing: {DOC_PATH}'
  return DOC_PATH.read_text()
```

**Class-per-section pattern** (lines 22-44 — model exactly):

```python
# Source: tests/test_setup_droplet_doc.py:22-43 [VERIFIED]
class TestDocStructure:
  def test_top_level_title_present(self, doc_text):
    assert re.search(r'^# SETUP-DROPLET.md', doc_text, re.MULTILINE)

  def test_section_install_systemd_unit(self, doc_text):
    assert re.search(r'^## Install systemd unit$', doc_text, re.MULTILINE)
  ...
```

**Apply to Phase 12 — one class per runbook section:**

```python
class TestDocStructure:
  def test_top_level_title_present(self, doc_text):
    assert re.search(r'^# SETUP-HTTPS.md', doc_text, re.MULTILINE)

  def test_section_prerequisites(self, doc_text):
    assert re.search(r'^## (1[.)]?\s*)?Prerequisites', doc_text, re.MULTILINE)

  def test_section_install_nginx_certbot(self, doc_text):
    assert re.search(r'^## (2[.)]?\s*)?Install nginx', doc_text, re.MULTILINE)

  def test_section_substitute_and_symlink(self, doc_text): ...
  def test_section_run_certbot(self, doc_text): ...
  def test_section_verify_https(self, doc_text): ...
  def test_section_confirm_certbot_timer(self, doc_text): ...
  def test_section_add_env_var(self, doc_text): ...
  def test_section_extend_sudoers(self, doc_text): ...
  def test_section_troubleshooting(self, doc_text): ...
  def test_section_rollback(self, doc_text): ...

class TestNginxInstallSteps:
  def test_apt_install_command(self, doc_text):
    assert 'apt install -y nginx certbot python3-certbot-nginx' in doc_text

  def test_nginx_version_check(self, doc_text):
    assert 'nginx -v' in doc_text

  def test_certbot_version_check(self, doc_text):
    assert 'certbot --version' in doc_text

class TestCertbotInvocation:
  def test_dry_run_before_production(self, doc_text):
    '''Pitfall 4: must run --dry-run first to avoid rate limit.'''
    assert '--dry-run' in doc_text
    assert 'certbot --nginx' in doc_text

  def test_rate_limit_warning_present(self, doc_text):
    '''Pitfall 4: doc must warn about 5/168h limit.'''
    assert re.search(r'5.*(per week|168|duplicate)', doc_text)

class TestSudoersExtension:
  def test_four_rule_entry(self, doc_text):
    '''D-20: sudoers now has 4 comma-separated rules.'''
    expected = (
      'trader ALL=(root) NOPASSWD: '
      '/usr/bin/systemctl restart trading-signals, '
      '/usr/bin/systemctl restart trading-signals-web, '
      '/usr/sbin/nginx -t, '
      '/usr/bin/systemctl reload nginx'
    )
    assert expected in doc_text

  def test_which_nginx_check(self, doc_text):
    '''Pitfall 7: operator must `which nginx` to verify /usr/sbin/nginx.'''
    assert 'which nginx' in doc_text

  def test_passwordless_nginx_verification(self, doc_text):
    '''Phase 11 HIGH #4 drift: Phase 12 must verify `sudo -n nginx -t` works
    BEFORE the first deploy.'''
    assert 'sudo -n nginx -t' in doc_text

class TestHttpsVerification:
  def test_curl_https_healthz(self, doc_text):
    assert 'curl' in doc_text
    assert 'https://signals.<owned-domain>.com' in doc_text

  def test_http_redirect_check(self, doc_text):
    assert 'http://signals.<owned-domain>.com' in doc_text
    assert '301' in doc_text

  def test_hsts_header_present(self, doc_text):
    assert 'Strict-Transport-Security' in doc_text
    assert 'max-age=31536000' in doc_text

class TestEnvVarStep:
  def test_signals_email_from_env(self, doc_text):
    assert 'SIGNALS_EMAIL_FROM=signals@carbonbookkeeping.com.au' in doc_text

  def test_restart_command(self, doc_text):
    assert 'sudo systemctl restart trading-signals' in doc_text

class TestAntiPatternWarnings:
  '''Phase 11 HIGH #4 drift + RESEARCH Anti-Patterns.'''

  def test_warns_against_nopasswd_all(self, doc_text):
    '''Same as Phase 11 — wildcard sudoers anti-pattern.'''
    assert 'NOPASSWD: ALL' in doc_text or 'NOPASSWD.*\\*' in doc_text

  def test_warns_against_listen_80_hand_written(self, doc_text):
    '''Pitfall 1: committed config must NOT have `listen 80` block.'''
    assert re.search(r'(certbot.*injects|certbot.*manages).*80', doc_text, re.IGNORECASE)

  def test_warns_against_hsts_preload(self, doc_text):
    '''D-12: NO preload submission.'''
    assert 'preload' in doc_text.lower()  # must be mentioned (as anti-pattern)
```

**Cross-artifact drift guard** (lines 160-193 — THE critical pattern for Phase 12):

```python
# Source: tests/test_setup_droplet_doc.py:160-193 [VERIFIED] — class shape to copy
class TestCrossArtifactDriftGuard:
  '''Prevent drift between doc and actual unit/script.'''

  def test_unit_name_matches_systemd_file(self, doc_text):
    unit_path = Path('systemd/trading-signals-web.service')
    assert unit_path.exists()
    assert 'trading-signals-web' in doc_text

  def test_sudoers_form_matches_deploy_sh_restart_calls(self, doc_text):
    '''REVIEWS HIGH #4 drift guard: doc's sudoers entry must match deploy.sh.'''
    deploy_path = Path('deploy.sh')
    deploy_text = deploy_path.read_text()
    ...
```

**Apply to Phase 12:**

```python
class TestCrossArtifactDriftGuard:
  '''Phase 12: prevent drift between SETUP-HTTPS.md and deploy.sh + nginx/signals.conf.'''

  def test_nginx_conf_exists(self, doc_text):
    '''Doc references nginx/signals.conf — file must actually exist.'''
    conf_path = Path('nginx/signals.conf')
    assert conf_path.exists()
    assert 'nginx/signals.conf' in doc_text

  def test_deploy_sh_reload_hook_present(self, doc_text):
    '''Doc's sudoers extension must line up with deploy.sh's reload block.'''
    deploy_path = Path('deploy.sh')
    assert deploy_path.exists()
    deploy_text = deploy_path.read_text()
    # deploy.sh must reference both commands that doc extends sudoers for
    assert 'sudo -n nginx -t' in deploy_text
    assert 'sudo -n systemctl reload nginx' in deploy_text
    # Doc must use EXACT same invocation names
    assert 'sudo -n nginx -t' in doc_text
    assert 'sudo -n systemctl reload nginx' in doc_text

  def test_sudoers_four_rule_form_matches_deploy_sh_calls(self, doc_text):
    '''Drift: sudoers 4-rule line in doc must enumerate exactly deploy.sh's 4 sudo -n calls.'''
    deploy_text = Path('deploy.sh').read_text()
    # Extract 4 `sudo -n` calls from deploy.sh
    for cmd in [
      'sudo -n systemctl restart trading-signals\\b',   # word-boundary to exclude -web
      'sudo -n systemctl restart trading-signals-web',
      'sudo -n nginx -t',
      'sudo -n systemctl reload nginx',
    ]:
      assert re.search(cmd, deploy_text), f'deploy.sh missing: {cmd}'
    # Doc's 4-rule sudoers line
    assert (
      '/usr/bin/systemctl restart trading-signals, '
      '/usr/bin/systemctl restart trading-signals-web, '
      '/usr/sbin/nginx -t, '
      '/usr/bin/systemctl reload nginx'
    ) in doc_text

  def test_placeholder_matches_nginx_conf(self, doc_text):
    '''<owned-domain> placeholder must match between nginx config and doc.'''
    conf_text = Path('nginx/signals.conf').read_text()
    assert '<owned-domain>' in conf_text
    assert '<owned-domain>' in doc_text
    # sed command in doc must target the exact placeholder
    assert re.search(r"sed.*<owned-domain>", doc_text)

  def test_signals_email_from_matches_notifier(self, doc_text):
    '''INFRA-01 drift: doc's env var name must match notifier.py's os.environ.get.'''
    notifier_text = Path('notifier.py').read_text()
    assert 'SIGNALS_EMAIL_FROM' in notifier_text, (
      'notifier.py must read SIGNALS_EMAIL_FROM (Phase 12 D-15)'
    )
    assert "os.environ.get('SIGNALS_EMAIL_FROM'" in notifier_text
    assert 'SIGNALS_EMAIL_FROM' in doc_text
```

**NEW drift guard specific to Phase 12:** the `test_signals_email_from_matches_notifier` guard (last one above) — Phase 11 had no env-var code-doc drift surface; Phase 12 introduces one. This is a NEW drift-pattern flag.

---

## Shared Patterns

### Config-as-committed-file with `<placeholder>` + operator `sed`
**Source:** `systemd/trading-signals-web.service` (User= hardcoded, EnvironmentFile= points at operator-owned .env)
**Apply to:** `nginx/signals.conf` — placeholder `<owned-domain>` + operator `sed` step
**Enforcement:** structural test + SETUP-HTTPS.md step explicitly telling operator to `sed`. `<owned-domain>` remains in git forever — operator substitutes the file-on-disk copy at `/etc/nginx/sites-available/signals.conf`, NOT the git tree.

### Env-var-read-at-use-point (per-send / per-request)
**Source:** `notifier.py:1417` (`RESEND_API_KEY`) + `notifier.py:1425` (`SIGNALS_EMAIL_TO`)
**Apply to:** `notifier.py` new `SIGNALS_EMAIL_FROM` read inside `send_daily_email` body (D-15)
```python
api_key = os.environ.get('RESEND_API_KEY')
if not api_key:
  logger.warning('[Email] WARN RESEND_API_KEY missing — wrote %s (fallback)', last_email_path)
  return SendStatus(ok=True, reason='no_api_key')
```
**Variation for SIGNALS_EMAIL_FROM:** `logger.error` not `.warning`; `ok=False` not `ok=True`; `reason='missing_sender'` literal (D-14).

### SendStatus NamedTuple return contract
**Source:** `notifier.py:84-92` — 2-field `(ok: bool, reason: str | None)`
**Apply to:** every new fail-path in `send_daily_email` / `send_crash_email`
**Flag:** D-14 mentions `attempts=0` — stay 2-field; do not extend.

### `[Email]` log prefix
**Source:** CLAUDE.md §Conventions + notifier.py existing usage
**Apply to:** every new notifier log line (`logger.error('[Email] SIGNALS_EMAIL_FROM not set...')`)

### Sudoers extension with absolute paths + comma-separated rules
**Source:** `SETUP-DROPLET.md:70` (2-rule form) + RESEARCH §Example 5 (4-rule extension)
**Apply to:** SETUP-HTTPS.md §Step 8 — extend to 4 rules on ONE line, absolute paths only, no wildcards
**Verification:** `sudo -n <cmd>` pre-deploy check (Phase 11 HIGH #4 pattern) — Phase 12 adds same check for `nginx -t` and `systemctl reload nginx`

### `sudo -n <cmd>` non-interactive deploy-time call
**Source:** `deploy.sh:50-51` (existing two `sudo -n systemctl restart` calls)
**Apply to:** new `sudo -n nginx -t` + `sudo -n systemctl reload nginx` inside the gate
**Idiom:** `-n` fails fast instead of hanging on password prompt when sudoers is misconfigured

### Gated optional-feature hook in bash
**Source:** NEW PATTERN — no prior use in `deploy.sh`
**Apply to:** nginx reload block in `deploy.sh` — `if [ -f nginx/signals.conf ] && command -v nginx &>/dev/null; then ... fi`
**Flag:** first introduction of `command -v` gating in a deploy script in this repo. Planner should note it as a new idiom future phases may adopt for other optional features.

### Text-assertion test style for config files
**Source:** `tests/test_deploy_sh.py`, `tests/test_web_systemd_unit.py`, `tests/test_setup_droplet_doc.py`
**Apply to:** `tests/test_nginx_signals_conf.py`, `tests/test_setup_https_doc.py`, `tests/test_deploy_sh.py::TestNginxReloadHook`
**Idiom:** read file once via `@pytest.fixture(scope='module')`, assert presence/absence with `in` or `re.search`. NEVER shell out to the tool (nginx, systemctl, etc.). Tests must run in CI where these tools may not exist.

### Runbook structural pattern: prose top + numbered bash-block steps + troubleshooting table + rollback bullets
**Source:** Phase 11 `SETUP-DROPLET.md` (table) + Phase 10 `SETUP-DEPLOY-KEY.md` (bullets)
**Apply to:** `SETUP-HTTPS.md` (merge both — table-form Troubleshooting + bullet-form Rollback)
**Verification:** `tests/test_setup_https_doc.py` class-per-section + drift guard

### Cross-artifact drift guard
**Source:** `tests/test_setup_droplet_doc.py::TestCrossArtifactDriftGuard` (lines 160-193)
**Apply to:** `tests/test_setup_https_doc.py::TestCrossArtifactDriftGuard` — assertion that doc's sudoers line matches deploy.sh's `sudo -n` calls AND nginx conf placeholder matches doc's `sed` command
**NEW for Phase 12:** also assert `notifier.py` reads `SIGNALS_EMAIL_FROM` env var (new code-doc drift surface introduced by INFRA-01)

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `nginx/signals.conf` | edge config | request-response (edge termination) | No nginx config has ever existed in this repo. `systemd/trading-signals-web.service` provides the "committed-config-with-placeholders" STRUCTURAL idiom, but nginx directive syntax is fresh. Use RESEARCH.md §Pattern 1 (lines 290-383) as authoritative body. |
| `tests/test_nginx_signals_conf.py` | structural test | transform | `tests/test_web_systemd_unit.py` gives the FIXTURE + class-per-concern shape, but `configparser` does not parse nginx. Use regex (`re.search`) and substring (`in`) assertions. Zero new deps. |

---

## Phase 12 Specific Pitfalls (consolidated for planner)

1. **3 sites of `_EMAIL_FROM`, not 2** (RESEARCH Pitfall 8 + code-verified): `notifier.py:99` (definition), `notifier.py:1147` (`_render_footer_email` body), `notifier.py:1427` (`send_daily_email` → `_post_to_resend`), `notifier.py:1506` (`send_crash_email` → `_post_to_resend`). Plan must include a grep verification task: `grep -n '_EMAIL_FROM' notifier.py` must return 0 after edits.

2. **SendStatus is 2-field, not 3-field.** D-14 CONTEXT line about `attempts=0` is aspirational; planner defaults to `SendStatus(ok=False, reason='missing_sender')` unless operator explicitly asks to extend.

3. **`command -v nginx &>/dev/null` is a NEW idiom** in `deploy.sh`. Document it as Phase 12's first use of optional-feature gating in bash.

4. **Golden-file regeneration is REQUIRED in the same commit as notifier.py refactor** (RESEARCH Pitfall 9). Running `tests/regenerate_notifier_golden.py` with `SIGNALS_EMAIL_FROM=signals@carbonbookkeeping.com.au` exported should produce byte-equal goldens (zero git diff). Any diff is a red flag — investigate before committing.

5. **`nginx/signals.conf` must NOT contain `listen 80`, `ssl_certificate`, or `ssl_certificate_key`** — certbot injects all three on first run. A pre-existing `listen 80` block confuses certbot's "add HTTPS to this server" heuristic (Pitfall 1). A pre-existing cert path makes the file non-idempotent on re-run.

6. **`add_header` inheritance is replace-not-extend.** All security headers (HSTS, XCTO, XFO, Referrer-Policy) go at `server` scope. Any future `add_header` in a `location` block nukes parent-scope headers for that route — flag this for Phase 13 when HTML dashboard + auth headers land.

7. **`/.well-known/acme-challenge/` must NOT be rate-limited.** Nested `location /.well-known/acme-challenge/` with no `limit_req` carves it out of the parent's rate limit (nginx rule: `limit_req` only inherits when no child-level `limit_req` exists).

8. **`--dry-run` before production certbot ALWAYS.** Let's Encrypt rate limit is 5 duplicate certs per exact identifier set per 168 hours. A misconfigured first run can burn a week. SETUP-HTTPS.md §4 must show `--dry-run` before production issuance.

9. **Ubuntu nginx path is `/usr/sbin/nginx`, NOT `/usr/bin/nginx`** (Pitfall 7). `which nginx` verification step is mandatory in SETUP-HTTPS.md §8 before pasting the sudoers line.

10. **Doc drift between SETUP-HTTPS.md + deploy.sh + nginx/signals.conf + notifier.py** — Phase 12 introduces THREE cross-artifact drift surfaces (doc-vs-deploy, doc-vs-conf, doc-vs-notifier). `tests/test_setup_https_doc.py::TestCrossArtifactDriftGuard` asserts all three. Plan must enumerate all three drift guards.

---

## Metadata

**Analog search scope:** repo root (`.py`, `.sh`), `systemd/`, `tests/`, `.planning/phases/10-foundation-v1-0-cleanup-deploy-key/`, `.planning/phases/11-web-skeleton-fastapi-uvicorn-systemd/`
**Files scanned:**
- `systemd/trading-signals-web.service` (all 31 lines)
- `tests/test_web_systemd_unit.py` (all 146 lines)
- `tests/test_setup_droplet_doc.py` (all 193 lines)
- `tests/test_deploy_sh.py` (all 180 lines)
- `tests/test_notifier.py` (lines 1-80, 1056-1300 — class skeletons + TestSendDispatch + TestGoldenEmail)
- `tests/test_main.py` (lines 2015-2230 — TestPushStateToGit spy patterns)
- `tests/regenerate_notifier_golden.py` (all 92 lines)
- `deploy.sh` (all 70 lines)
- `notifier.py` (lines 80-200, 1130-1225, 1360-1525 — env reads + footer renderer + send_daily_email + send_crash_email)
- `SETUP-DROPLET.md` (all 242 lines)
- `.planning/phases/10-foundation-v1-0-cleanup-deploy-key/SETUP-DEPLOY-KEY.md` (all 234 lines)
- `.planning/phases/10-foundation-v1-0-cleanup-deploy-key/10-PATTERNS.md` (first 200 lines — shape reference)
- `.planning/phases/11-web-skeleton-fastapi-uvicorn-systemd/11-PATTERNS.md` (all 524 lines — shape reference)
- `.planning/phases/12-https-domain-wiring/12-CONTEXT.md` (full — D-01..D-21)
- `.planning/phases/12-https-domain-wiring/12-RESEARCH.md` (lines 1-800 — patterns + anti-patterns + examples)

**Pattern extraction date:** 2026-04-24
