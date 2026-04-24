'''Phase 12 Plan 01 — structural invariants for nginx/signals.conf.

Grep-style + regex assertions over the committed nginx config text.
We DO NOT shell out to `nginx -t` — CI may not have nginx installed.
The real `nginx -t` run is an operator step documented in SETUP-HTTPS.md.

Covers:
  WEB-03: nginx reverse-proxy to 127.0.0.1:8000, rate-limit on /healthz,
          ACME challenge carve-out, TLS tuning (Mozilla Intermediate).
  WEB-04: HSTS `max-age=31536000; includeSubDomains` at server scope,
          `always` flag, no `preload` (D-12).
  T-12-01: cert material never referenced in committed file (certbot injects).
  T-12-02: ACME challenge path exempt from rate-limit.
  T-12-06: HSTS stays at server scope (never inside location — Pitfall 3).
'''

import re
from pathlib import Path

import pytest

CONF_PATH = Path('nginx/signals.conf')


@pytest.fixture(scope='module')
def conf_text() -> str:
  assert CONF_PATH.exists(), f'nginx config missing: {CONF_PATH}'
  return CONF_PATH.read_text()


class TestNginxConfStructure:
  '''D-08: single 443 server block; WEB-03 edge reverse-proxy.'''

  def test_listen_443_ssl(self, conf_text):
    assert re.search(r'^\s*listen\s+443\s+ssl\s*;', conf_text, re.MULTILINE)

  def test_listen_ipv6_443_ssl(self, conf_text):
    assert re.search(r'^\s*listen\s+\[::\]:443\s+ssl\s*;', conf_text, re.MULTILINE)

  def test_http2_on(self, conf_text):
    assert re.search(r'^\s*http2\s+on\s*;', conf_text, re.MULTILINE)

  def test_server_name_present(self, conf_text):
    assert re.search(r'^\s*server_name\s+signals\.<owned-domain>\.com\s*;',
                     conf_text, re.MULTILINE)


class TestNginxConfPlaceholder:
  '''D-01: committed placeholder `<owned-domain>`; operator seds at install.'''

  def test_owned_domain_placeholder_literal_present(self, conf_text):
    assert 'signals.<owned-domain>.com' in conf_text

  def test_no_hardcoded_production_domain(self, conf_text):
    # No leaked production domains. carbonbookkeeping is the intended target
    # but it MUST NOT appear in the committed file (operator subs it in).
    assert 'carbonbookkeeping' not in conf_text


class TestNginxConfTlsTuning:
  '''D-08 + RESEARCH Mozilla Intermediate profile (2024 rev).'''

  def test_ssl_protocols_tls12_13_only(self, conf_text):
    assert re.search(r'ssl_protocols\s+TLSv1\.2\s+TLSv1\.3\s*;', conf_text)

  def test_no_legacy_tls_protocols(self, conf_text):
    # IETF RFC 8996: TLS 1.0 / 1.1 deprecated.
    assert 'TLSv1 ' not in conf_text  # space prevents matching TLSv1.2/1.3
    assert 'TLSv1.1' not in conf_text

  def test_cipher_list_posture_format(self, conf_text):
    # 12-REVIEWS.md LOW — posture check, NOT exact-string match.
    # Assert ssl_ciphers directive is present, non-empty, well-formed.
    # Does NOT pin to a specific Mozilla Intermediate version (e.g., v5.6
    # vs v5.7 reorder ciphers). Refresh ssl_ciphers against current Mozilla
    # SSL Config Generator at deployment time (SETUP-HTTPS.md §3 note).
    m = re.search(r'^\s*ssl_ciphers\s+([A-Z0-9:\-]+)\s*;', conf_text, re.MULTILINE)
    assert m is not None, 'ssl_ciphers directive missing or malformed'
    assert len(m.group(1)) > 0, 'ssl_ciphers value must be non-empty'
    # Mozilla Intermediate requires ECDHE for forward secrecy — posture check
    assert 'ECDHE-' in m.group(1), 'ssl_ciphers must include ECDHE ciphers for FS'

  def test_ssl_prefer_server_ciphers_off(self, conf_text):
    assert re.search(r'ssl_prefer_server_ciphers\s+off\s*;', conf_text)

  def test_session_cache_shared_10m(self, conf_text):
    assert re.search(r'ssl_session_cache\s+shared:SSL:10m\s*;', conf_text)

  def test_session_timeout_1d(self, conf_text):
    assert re.search(r'ssl_session_timeout\s+1d\s*;', conf_text)

  def test_session_tickets_off(self, conf_text):
    # Mozilla 2024 — tickets off by default.
    assert re.search(r'ssl_session_tickets\s+off\s*;', conf_text)

  def test_ocsp_stapling_enabled(self, conf_text):
    assert re.search(r'ssl_stapling\s+on\s*;', conf_text)
    assert re.search(r'ssl_stapling_verify\s+on\s*;', conf_text)

  def test_resolver_present_for_stapling(self, conf_text):
    # OCSP needs a DNS resolver.
    assert re.search(r'resolver\s+1\.1\.1\.1\s+8\.8\.8\.8', conf_text)


class TestNginxConfSecurityHeaders:
  '''D-11 + WEB-04 + RESEARCH Pitfall 2: `always` flag + server scope.'''

  def test_hsts_exact_value_with_always(self, conf_text):
    # WEB-04 SC-2 exact string. Research Pitfall 2: `always` flag ensures
    # emission on 4xx/5xx too (not just 2xx).
    assert (
      "add_header Strict-Transport-Security "
      "'max-age=31536000; includeSubDomains' always;"
    ) in conf_text

  def test_hsts_no_preload(self, conf_text):
    '''D-12: NO preload submission; keep escape hatch open.'''
    # The HSTS header line must not contain `preload`.
    hsts_match = re.search(
      r'add_header\s+Strict-Transport-Security\s+[\'"]([^\'"]+)[\'"]',
      conf_text,
    )
    assert hsts_match is not None, 'HSTS header not found'
    assert 'preload' not in hsts_match.group(1)

  def test_x_content_type_options(self, conf_text):
    assert "add_header X-Content-Type-Options 'nosniff' always;" in conf_text

  def test_x_frame_options(self, conf_text):
    assert "add_header X-Frame-Options 'DENY' always;" in conf_text

  def test_referrer_policy(self, conf_text):
    assert (
      "add_header Referrer-Policy "
      "'strict-origin-when-cross-origin' always;"
    ) in conf_text


class TestNginxConfHstsScope:
  '''T-12-06 + RESEARCH Pitfall 3: HSTS must be at server scope, not inside
  any location block. `add_header` is replace-not-extend in nginx — a
  location-scope add_header nukes parent-scope headers.
  '''

  def test_hsts_not_inside_location(self, conf_text):
    # Split on `location ` tokens; the first chunk is server-scope + pre-location.
    # Subsequent chunks are each a location body.
    chunks = conf_text.split('location ')
    assert len(chunks) >= 2, 'expected at least one location block'
    # Every chunk AFTER the first must NOT contain the HSTS directive.
    for i, chunk in enumerate(chunks[1:], 1):
      assert 'Strict-Transport-Security' not in chunk, (
        f'HSTS found inside location block #{i}: nginx `add_header` is '
        f'replace-not-extend; this breaks parent-scope HSTS for this route.'
      )


class TestNginxConfRateLimit:
  '''D-10: rate-limit /healthz at nginx edge.'''

  def test_limit_req_zone_declared_at_http_scope(self, conf_text):
    # The zone must appear OUTSIDE any server block — operator includes
    # from /etc/nginx/conf.d/ or the committed file itself at top level.
    assert (
      'limit_req_zone $binary_remote_addr zone=healthz:10m rate=10r/m;'
    ) in conf_text

  def test_healthz_location_limits_requests(self, conf_text):
    assert 'limit_req zone=healthz burst=10 nodelay;' in conf_text

  def test_healthz_limit_req_status_429(self, conf_text):
    assert 'limit_req_status 429;' in conf_text


class TestNginxConfAcmeCarveout:
  '''T-12-02: ACME challenge must NOT be rate-limited.

  Research §Pitfall / Anti-Pattern: rate-limiting /.well-known/acme-challenge
  can break certbot renewal. nginx `limit_req` inheritance rule — declaring
  a nested location with no `limit_req` disables rate-limit for that path.
  '''

  def test_acme_location_present(self, conf_text):
    assert 'location /.well-known/acme-challenge/' in conf_text

  def test_acme_location_has_no_limit_req(self, conf_text):
    # Extract the acme-challenge location block body and confirm no limit_req.
    m = re.search(
      r'location\s+/\.well-known/acme-challenge/\s*\{([^}]*)\}',
      conf_text,
      re.DOTALL,
    )
    assert m is not None, 'ACME challenge location block not found'
    body = m.group(1)
    assert 'limit_req' not in body, (
      'ACME challenge location must NOT contain limit_req '
      '(would lock out certbot renewal)'
    )


class TestNginxConfProxy:
  '''D-08: reverse-proxy to FastAPI at 127.0.0.1:8000 (Phase 11).'''

  def test_healthz_proxy_pass_to_fastapi(self, conf_text):
    # /healthz location must proxy to 127.0.0.1:8000.
    m = re.search(
      r'location\s*=\s*/healthz\s*\{([^}]*)\}',
      conf_text,
      re.DOTALL,
    )
    assert m is not None, '/healthz location not found'
    assert 'proxy_pass http://127.0.0.1:8000' in m.group(1)

  def test_catchall_proxy_pass_to_fastapi(self, conf_text):
    # The catch-all `location /` — occurs after a closing-brace or at file
    # end; be lenient with the boundary but require 127.0.0.1:8000.
    # Count: at least 2 proxy_pass occurrences (one per location).
    occurrences = conf_text.count('proxy_pass http://127.0.0.1:8000')
    assert occurrences >= 2, (
      f'expected proxy_pass to 127.0.0.1:8000 in BOTH /healthz and / '
      f'locations; found {occurrences} occurrence(s)'
    )

  def test_proxy_headers_present(self, conf_text):
    for header in [
      'proxy_set_header Host $host',
      'proxy_set_header X-Real-IP $remote_addr',
      'proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for',
      'proxy_set_header X-Forwarded-Proto',
    ]:
      assert header in conf_text, f'missing proxy header: {header}'


class TestNginxConfForbiddenPatterns:
  '''Negative assertions: certbot owns these; pre-existing versions
  confuse certbot (Pitfall 1) or leak cert paths into git (T-12-01).
  '''

  def test_no_listen_80_directive(self, conf_text):
    '''Pitfall 1: certbot injects the 80-redirect block. A pre-existing
    listen 80 confuses certbot's "add HTTPS to this server" heuristic.
    '''
    assert not re.search(r'^\s*listen\s+80\b', conf_text, re.MULTILINE)

  def test_no_ssl_certificate_line(self, conf_text):
    '''T-12-01: certbot injects `ssl_certificate` on first run.'''
    assert not re.search(r'^\s*ssl_certificate\s+', conf_text, re.MULTILINE)

  def test_no_ssl_certificate_key_line(self, conf_text):
    '''T-12-01: certbot injects `ssl_certificate_key` on first run.'''
    assert not re.search(
      r'^\s*ssl_certificate_key\s+', conf_text, re.MULTILINE,
    )

  def test_no_bind_all_interfaces(self, conf_text):
    # Belt-and-braces — we never bind to 0.0.0.0 (proxy_pass target is
    # localhost; nginx itself listens on :443 per listen directives).
    assert '0.0.0.0' not in conf_text

  def test_no_handwritten_http_to_https_redirect(self, conf_text):
    '''Pitfall 1: certbot injects the 301 block; hand-writing it fights
    certbot's state machine and produces duplicate `return 301` directives.
    '''
    assert not re.search(r'return\s+301\s+https://', conf_text)
