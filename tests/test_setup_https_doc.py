'''Phase 12 Plan 04 — structural + cross-artifact drift guards for SETUP-HTTPS.md.

Mirrors tests/test_setup_droplet_doc.py structural pattern + extends with
TestCrossArtifactDriftGuard which asserts the runbook stays in sync with:
  - nginx/signals.conf (Plan 01) — `<owned-domain>` placeholder
  - deploy.sh (Plan 03) — 4 `sudo -n` commands documented in sudoers rule
  - notifier.py (Plan 02) — SIGNALS_EMAIL_FROM env var name
  - systemd/trading-signals-web.service (Phase 11) — EnvironmentFile= path
    matches the .env path documented in SETUP-HTTPS.md §7
    (12-REVIEWS.md LOW belt-and-braces drift guard).

T-12-05: runbook drift -> silent deploy regressions. Drift guard raises
         the alarm at test-time, not operator-time.
T-12-06: future HSTS regressions — doc callout flags the nginx add_header
         replace-not-extend trap for Phase 13+ authors.
'''

import re
from pathlib import Path

import pytest

DOC_PATH = Path('.planning/phases/12-https-domain-wiring/SETUP-HTTPS.md')


@pytest.fixture(scope='module')
def doc_text() -> str:
  assert DOC_PATH.exists(), f'doc missing: {DOC_PATH}'
  return DOC_PATH.read_text()


class TestDocStructure:
  '''D-21: 10 sections + top-level title.'''

  def test_top_level_title_present(self, doc_text):
    assert re.search(r'^# SETUP-HTTPS\.md', doc_text, re.MULTILINE)

  def test_section_prerequisites(self, doc_text):
    assert re.search(r'^##\s+.*[Pp]rerequisites', doc_text, re.MULTILINE)

  def test_section_install_nginx_certbot(self, doc_text):
    assert re.search(r'^##\s+.*[Ii]nstall.*nginx.*certbot', doc_text, re.MULTILINE)

  def test_section_copy_sed_symlink(self, doc_text):
    # Section 3 — any wording that references Copy/Config/Symlink work.
    assert re.search(r'^##\s+.*([Cc]opy|[Cc]onfig|[Ss]ymlink)', doc_text, re.MULTILINE)

  def test_section_run_certbot(self, doc_text):
    assert re.search(r'^##\s+.*[Cc]ertbot', doc_text, re.MULTILINE)

  def test_section_verify_https(self, doc_text):
    assert re.search(r'^##\s+.*[Vv]erify', doc_text, re.MULTILINE)

  def test_section_confirm_timer(self, doc_text):
    assert re.search(r'^##\s+.*([Tt]imer|renewal)', doc_text, re.MULTILINE)

  def test_section_env_var(self, doc_text):
    assert re.search(r'^##\s+.*SIGNALS_EMAIL_FROM', doc_text, re.MULTILINE)

  def test_section_sudoers(self, doc_text):
    assert re.search(r'^##\s+.*[Ss]udoers', doc_text, re.MULTILINE)

  def test_section_troubleshooting(self, doc_text):
    assert re.search(r'^##\s+.*[Tt]roubleshooting', doc_text, re.MULTILINE)

  def test_section_rollback(self, doc_text):
    assert re.search(r'^##\s+.*[Rr]ollback', doc_text, re.MULTILINE)


class TestNginxInstallSteps:
  def test_apt_install_command(self, doc_text):
    assert 'apt install -y nginx certbot python3-certbot-nginx' in doc_text

  def test_nginx_version_check(self, doc_text):
    assert 'nginx -v' in doc_text

  def test_certbot_version_check(self, doc_text):
    assert 'certbot --version' in doc_text


class TestConfigSubstitution:
  def test_copy_committed_config(self, doc_text):
    assert 'nginx/signals.conf' in doc_text
    # Must reference copying into sites-available
    assert '/etc/nginx/sites-available/signals.conf' in doc_text

  def test_sed_substitution_instruction(self, doc_text):
    # Operator must sed the placeholder.
    assert re.search(r'sed.*<owned-domain>', doc_text)

  def test_symlink_to_sites_enabled(self, doc_text):
    assert '/etc/nginx/sites-enabled' in doc_text
    assert re.search(r'ln -s', doc_text)

  def test_nginx_config_test_before_certbot(self, doc_text):
    # After sed + symlink, operator runs `nginx -t` before certbot.
    assert 'sudo nginx -t' in doc_text


class TestCertbotInvocation:
  def test_dry_run_before_production(self, doc_text):
    '''Pitfall 4: Let's Encrypt rate limit is 5 duplicate certs per 168h.
    Operator MUST --dry-run first.'''
    assert '--dry-run' in doc_text
    assert 'certbot --nginx' in doc_text

  def test_rate_limit_warning(self, doc_text):
    '''Doc must warn about the 5/168h rate limit.'''
    # Looser match: any mention of 168 hours OR "5 duplicate" OR "rate limit".
    assert re.search(
      r'(168|5\s*(duplicate|per\s*week)|rate\s*limit)',
      doc_text,
      re.IGNORECASE,
    )

  def test_production_issuance_command(self, doc_text):
    assert 'certbot --nginx -d signals.<owned-domain>.com' in doc_text


class TestHttpsVerification:
  '''SC-1 + SC-2 operator-verified via curl + openssl.'''

  def test_curl_https_healthz(self, doc_text):
    assert 'curl -sI https://signals.<owned-domain>.com/healthz' in doc_text

  def test_curl_http_redirect(self, doc_text):
    assert 'curl -sI http://signals.<owned-domain>.com/healthz' in doc_text
    assert '301' in doc_text

  def test_hsts_exact_value_referenced(self, doc_text):
    '''WEB-04 SC-2 — exact value surfaces in verification step.'''
    assert 'Strict-Transport-Security' in doc_text
    assert 'max-age=31536000' in doc_text

  def test_openssl_cert_chain_inspection(self, doc_text):
    assert 'openssl s_client' in doc_text
    # Letsencrypt issuer expected.
    assert "Let's Encrypt" in doc_text


class TestCertbotTimer:
  def test_list_timers_command(self, doc_text):
    assert re.search(r'systemctl list-timers.*certbot', doc_text)

  def test_renew_dry_run(self, doc_text):
    assert 'certbot renew --dry-run' in doc_text

  def test_renewal_hook_path(self, doc_text):
    assert '/etc/letsencrypt/renewal-hooks/deploy' in doc_text

  def test_renewal_hook_reloads_nginx(self, doc_text):
    assert re.search(r'systemctl reload nginx', doc_text)


class TestEnvVarStep:
  '''INFRA-01: operator-facing env-var wiring.'''

  def test_env_var_name_exact(self, doc_text):
    assert 'SIGNALS_EMAIL_FROM=signals@carbonbookkeeping.com.au' in doc_text

  def test_env_file_path(self, doc_text):
    assert '/home/trader/trading-signals/.env' in doc_text

  def test_restart_trading_signals(self, doc_text):
    # Only the signal service needs restart (web doesn't consume this var).
    assert 'sudo systemctl restart trading-signals' in doc_text

  def test_force_email_verification(self, doc_text):
    assert 'python main.py --force-email' in doc_text


class TestSudoersExtension:
  '''Sudoers now has 4 comma-separated rules (2 Phase 11 + 2 Phase 12).'''

  def test_four_rule_entry_exact(self, doc_text):
    expected = (
      'trader ALL=(root) NOPASSWD: '
      '/usr/bin/systemctl restart trading-signals, '
      '/usr/bin/systemctl restart trading-signals-web, '
      '/usr/sbin/nginx -t, '
      '/usr/bin/systemctl reload nginx'
    )
    assert expected in doc_text

  def test_which_nginx_verification(self, doc_text):
    '''Pitfall 7: Ubuntu ships /usr/sbin/nginx (not /usr/bin). Operator
    must verify with `which nginx` before pasting the sudoers line.'''
    assert 'which nginx' in doc_text

  def test_which_systemctl_verification(self, doc_text):
    assert 'which systemctl' in doc_text

  def test_sudoers_path(self, doc_text):
    assert '/etc/sudoers.d/trading-signals-deploy' in doc_text

  def test_visudo_validation(self, doc_text):
    assert re.search(r'visudo -c -f', doc_text)

  def test_passwordless_nginx_verification(self, doc_text):
    '''Pitfall 7 + Phase 11 HIGH #4 drift: operator verifies
    `sudo -n nginx -t` BEFORE the first deploy.'''
    assert 'sudo -n nginx -t' in doc_text
    assert 'sudo -n systemctl reload nginx' in doc_text


class TestAntiPatternWarnings:
  def test_warns_against_nopasswd_all(self, doc_text):
    # Must WARN against NOPASSWD: ALL (either as a negative example
    # or an explicit "do not do this" note).
    assert 'NOPASSWD: ALL' in doc_text or re.search(
      r'(do not|never|avoid).*NOPASSWD',
      doc_text,
      re.IGNORECASE,
    )

  def test_warns_against_wildcard_sudoers(self, doc_text):
    assert re.search(r'wildcard|/usr/sbin/nginx\s*\*', doc_text)

  def test_no_hsts_preload(self, doc_text):
    '''D-12: doc must explicitly note preload is NOT used.'''
    assert 'preload' in doc_text.lower()

  def test_port_80_injected_by_certbot_note(self, doc_text):
    '''Pitfall 1: committed config has no port-80 block; certbot injects it.'''
    assert re.search(
      r'certbot.*(injects?|auto-|adds?).*(80|redirect)',
      doc_text,
      re.IGNORECASE,
    )

  def test_dry_run_before_production_warning(self, doc_text):
    '''Pitfall 4: must warn to --dry-run before production issuance.'''
    assert re.search(
      r'--dry-run.*(first|before|production)',
      doc_text,
      re.IGNORECASE,
    )


class TestTroubleshootingContent:
  '''Section 9 TABLE — symptom / cause / fix. RESEARCH §Pitfalls 4, 6, 7.'''

  def test_dns_propagation_item(self, doc_text):
    assert re.search(r'(dig|DNS|propagat)', doc_text)

  def test_rate_limit_item(self, doc_text):
    # Already covered in TestCertbotInvocation but re-assert in troubleshooting context.
    assert re.search(r'(rate|168|duplicate)', doc_text, re.IGNORECASE)

  def test_sudoers_path_mismatch_item(self, doc_text):
    '''Pitfall 7: sudoers typo -> "password required".'''
    assert re.search(
      r'(password\s+is\s+required|password\s+required|sudoers.*path)',
      doc_text,
      re.IGNORECASE,
    )

  def test_signals_email_from_missing_item(self, doc_text):
    '''D-14 failure path surfaces as troubleshooting entry.'''
    assert '[Email] SIGNALS_EMAIL_FROM not set' in doc_text


class TestRollback:
  def test_rollback_disables_nginx_site(self, doc_text):
    assert re.search(
      r'rm\s+/etc/nginx/sites-enabled/signals\.conf',
      doc_text,
    )

  def test_rollback_removes_env_var(self, doc_text):
    assert re.search(
      r'[Rr]emove.*SIGNALS_EMAIL_FROM',
      doc_text,
    )


class TestCrossArtifactDriftGuard:
  '''T-12-05 + T-12-06: doc stays in sync with code artifacts.

  THIS IS THE CRITICAL CLASS — when the runbook diverges from
  nginx/signals.conf (Plan 01), deploy.sh (Plan 03), or notifier.py
  (Plan 02), these assertions fail at test-time rather than at
  operator-time.
  '''

  def test_nginx_conf_exists_and_referenced(self, doc_text):
    conf_path = Path('nginx/signals.conf')
    assert conf_path.exists(), (
      'Plan 01 artifact missing — SETUP-HTTPS.md is useless without it'
    )
    assert 'nginx/signals.conf' in doc_text

  def test_owned_domain_placeholder_matches_nginx_conf(self, doc_text):
    '''Doc's sed command must target the exact placeholder in nginx/signals.conf.'''
    conf_text = Path('nginx/signals.conf').read_text()
    assert '<owned-domain>' in conf_text, (
      'nginx/signals.conf missing <owned-domain> placeholder (D-01)'
    )
    assert '<owned-domain>' in doc_text
    # sed command in doc targets the placeholder.
    assert re.search(r'sed.*<owned-domain>', doc_text)

  def test_deploy_sh_reload_calls_match_sudoers_rule(self, doc_text):
    '''Drift guard: doc's sudoers extension must enumerate exactly
    the 4 `sudo -n` calls deploy.sh makes (Plan 03 + Phase 11).
    '''
    deploy_path = Path('deploy.sh')
    assert deploy_path.exists()
    deploy_text = deploy_path.read_text()
    # All 4 commands must exist in deploy.sh
    for cmd in [
      r'^sudo -n systemctl restart trading-signals\s*$',
      r'^sudo -n systemctl restart trading-signals-web\s*$',
      r'^\s*sudo -n nginx -t\s*$',
      r'^\s*sudo -n systemctl reload nginx\s*$',
    ]:
      assert re.search(cmd, deploy_text, re.MULTILINE), (
        f'deploy.sh missing command matching: {cmd!r}'
      )
    # Doc must document the passwordless verification for the new 2.
    assert 'sudo -n nginx -t' in doc_text
    assert 'sudo -n systemctl reload nginx' in doc_text

  def test_sudoers_4_rule_line_present(self, doc_text):
    '''Exact 4-rule sudoers line matches what deploy.sh requires.'''
    expected = (
      'trader ALL=(root) NOPASSWD: '
      '/usr/bin/systemctl restart trading-signals, '
      '/usr/bin/systemctl restart trading-signals-web, '
      '/usr/sbin/nginx -t, '
      '/usr/bin/systemctl reload nginx'
    )
    assert expected in doc_text

  def test_signals_email_from_matches_notifier(self, doc_text):
    '''INFRA-01 drift guard: doc's env-var instruction must name the
    same env var that notifier.py reads.
    '''
    notifier_text = Path('notifier.py').read_text()
    # notifier.py reads SIGNALS_EMAIL_FROM (Plan 02 artifact).
    assert 'SIGNALS_EMAIL_FROM' in notifier_text, (
      'notifier.py must read SIGNALS_EMAIL_FROM (Plan 02 INFRA-01)'
    )
    assert re.search(
      r"os\.environ\.get\(\s*['\"]SIGNALS_EMAIL_FROM['\"]",
      notifier_text,
    )
    # Doc must reference the same env var.
    assert 'SIGNALS_EMAIL_FROM' in doc_text

  def test_no_hardcoded_email_from_in_notifier(self, doc_text):
    '''D-16 drift guard: the module-level `_EMAIL_FROM = '...'` constant
    has been removed. Cannot use a bare `'_EMAIL_FROM' not in
    notifier_text` check because `SIGNALS_EMAIL_FROM` contains
    `_EMAIL_FROM` as a substring — match the assignment form instead.
    '''
    notifier_text = Path('notifier.py').read_text()
    # Look for any module-level (or function-level) assignment of the
    # form `_EMAIL_FROM = ...` — the original D-16-target constant.
    # Allowed false-negatives: SIGNALS_EMAIL_FROM appears in `os.environ
    # .get('SIGNALS_EMAIL_FROM', ...)` and in log messages — those do
    # not match `^[ \t]*_EMAIL_FROM\s*=` because they have `SIGNALS`
    # prefix and/or are inside string literals.
    assert not re.search(
      r'(^|[^A-Z_])_EMAIL_FROM\s*=',
      notifier_text,
      re.MULTILINE,
    ), 'notifier.py still has `_EMAIL_FROM = ...` — Plan 02 D-16 incomplete'

  def test_env_path_matches_systemd_unit(self, doc_text):
    '''12-REVIEWS.md LOW (belt-and-braces) — doc's .env path must match
    systemd EnvironmentFile= path. Prevents future drift if systemd unit
    is edited without updating runbook.
    '''
    unit_path = Path('systemd/trading-signals-web.service')
    assert unit_path.exists(), 'Phase 11 systemd unit missing'
    unit_text = unit_path.read_text()
    m = re.search(r'EnvironmentFile=-?([^\s]+)', unit_text)
    assert m is not None, 'systemd unit has no EnvironmentFile= directive'
    env_file_path = m.group(1)
    assert env_file_path in doc_text, (
      f'SETUP-HTTPS.md §7 references a different .env path than '
      f'systemd/trading-signals-web.service EnvironmentFile= '
      f'(expected {env_file_path!r})'
    )
