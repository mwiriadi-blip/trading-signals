'''Phase 11 — SETUP-DROPLET.md operator runbook completeness guard.

2026-04-24 REVIEWS additions:
  - HIGH #4: new `test_passwordless_sudo_verification_step` +
    `test_sudoers_form_matches_deploy_sh_restart_calls` drift guard.
  - MEDIUM #5: new TestEnvFileOptional class.
'''
import re
from pathlib import Path

import pytest

DOC_PATH = Path('SETUP-DROPLET.md')


@pytest.fixture(scope='module')
def doc_text() -> str:
  assert DOC_PATH.exists(), f'doc missing: {DOC_PATH}'
  return DOC_PATH.read_text()


class TestDocStructure:
  def test_top_level_title_present(self, doc_text):
    assert re.search(r'^# SETUP-DROPLET.md', doc_text, re.MULTILINE)

  def test_section_install_systemd_unit(self, doc_text):
    assert re.search(r'^## Install systemd unit$', doc_text, re.MULTILINE)

  def test_section_install_sudoers(self, doc_text):
    assert re.search(r'^## Install sudoers entry for trader$', doc_text, re.MULTILINE)

  def test_section_verify_port_binding(self, doc_text):
    assert re.search(r'^## Verify port binding \(WEB-02 / SC-4\)$', doc_text, re.MULTILINE)

  def test_section_verify_deploy_sh(self, doc_text):
    assert re.search(r'^## Verify deploy.sh end-to-end \(INFRA-04 / SC-3\)$', doc_text, re.MULTILINE)

  def test_section_verify_boot_persistence(self, doc_text):
    assert re.search(r'^## Verify boot persistence \(WEB-01 / SC-1\)$', doc_text, re.MULTILINE)

  def test_section_troubleshooting(self, doc_text):
    assert re.search(r'^## Troubleshooting$', doc_text, re.MULTILINE)


class TestSystemdInstall:
  def test_copy_unit_file_command(self, doc_text):
    assert 'sudo cp /home/trader/trading-signals/systemd/trading-signals-web.service' in doc_text

  def test_daemon_reload_command(self, doc_text):
    assert 'sudo systemctl daemon-reload' in doc_text

  def test_enable_command(self, doc_text):
    assert 'sudo systemctl enable trading-signals-web' in doc_text

  def test_start_command(self, doc_text):
    assert 'sudo systemctl start trading-signals-web' in doc_text

  def test_status_check_command(self, doc_text):
    count = doc_text.count('systemctl status trading-signals-web')
    assert count >= 2

  def test_systemd_analyze_verify(self, doc_text):
    assert 'systemd-analyze verify' in doc_text


class TestSudoersInstall:
  '''D-21 + REVIEWS HIGH #4 passwordless-sudo verification step.'''

  def test_sudoers_path_referenced(self, doc_text):
    count = doc_text.count('/etc/sudoers.d/trading-signals-deploy')
    assert count >= 4

  def test_sudoers_entry_text_exact(self, doc_text):
    expected = 'trader ALL=(root) NOPASSWD: /usr/bin/systemctl restart trading-signals, /usr/bin/systemctl restart trading-signals-web'
    assert expected in doc_text

  def test_sudoers_entry_lists_both_units(self, doc_text):
    for line in doc_text.splitlines():
      if 'trader ALL=' in line and 'NOPASSWD' in line:
        assert 'trading-signals,' in line or 'trading-signals ' in line
        assert 'trading-signals-web' in line
        return
    raise AssertionError('no sudoers line found')

  def test_chmod_440(self, doc_text):
    assert 'sudo chmod 440' in doc_text

  def test_chown_root_root(self, doc_text):
    assert 'sudo chown root:root' in doc_text

  def test_visudo_validate_command(self, doc_text):
    assert 'sudo visudo -c -f' in doc_text

  def test_which_systemctl_check(self, doc_text):
    assert 'which systemctl' in doc_text

  def test_passwordless_sudo_verification_step(self, doc_text):
    '''REVIEWS HIGH #4: doc must include `sudo -n systemctl restart
    trading-signals-web` verification step BEFORE running deploy.sh.'''
    assert 'sudo -n systemctl restart trading-signals-web' in doc_text


class TestEnvFileOptional:
  '''REVIEWS MEDIUM #5: Phase 11 does NOT require .env.'''

  def test_env_file_optional_note_present(self, doc_text):
    assert 'EnvironmentFile=-' in doc_text

  def test_env_not_required_wording_present(self, doc_text):
    candidates = ['NOT required', 'not required', 'OPTIONAL', 'optional']
    assert any(c in doc_text for c in candidates)


class TestPortBindingVerify:
  def test_ss_tlnp_grep_8000(self, doc_text):
    assert 'ss -tlnp | grep 8000' in doc_text

  def test_loopback_address_referenced(self, doc_text):
    count = doc_text.count('127.0.0.1:8000')
    assert count >= 2

  def test_curl_healthz_loopback(self, doc_text):
    assert 'curl -fsS http://127.0.0.1:8000/healthz' in doc_text

  def test_external_reach_negative_check(self, doc_text):
    assert '<DROPLET_IP>' in doc_text
    assert 'connection refused or timeout' in doc_text


class TestDeployIdempotency:
  def test_idempotency_callout(self, doc_text):
    assert doc_text.count('bash deploy.sh') >= 2

  def test_already_up_to_date_expected(self, doc_text):
    count = doc_text.count('Already up to date')
    assert count >= 2

  def test_requirement_already_satisfied_expected(self, doc_text):
    assert 'Requirement already satisfied' in doc_text


class TestBootPersistence:
  def test_reboot_command(self, doc_text):
    assert 'sudo reboot' in doc_text


class TestAntiPatternWarnings:
  def test_warns_against_nopasswd_all(self, doc_text):
    assert 'NOPASSWD: ALL' in doc_text
    assert 'NEVER' in doc_text

  def test_warns_against_external_bind(self, doc_text):
    assert '0.0.0.0' in doc_text
    assert '0.0.0.0:8000' in doc_text

  def test_warns_against_visudo_workarounds(self, doc_text):
    assert 'visudo' in doc_text


class TestCrossArtifactDriftGuard:
  '''Prevent drift between doc and actual unit/script.'''

  def test_unit_name_matches_systemd_file(self, doc_text):
    unit_path = Path('systemd/trading-signals-web.service')
    assert unit_path.exists()
    assert 'trading-signals-web' in doc_text

  def test_smoke_test_url_matches_deploy_sh(self, doc_text):
    deploy_path = Path('deploy.sh')
    assert deploy_path.exists()
    deploy_text = deploy_path.read_text()
    assert '127.0.0.1:8000/healthz' in doc_text
    assert '127.0.0.1:8000/healthz' in deploy_text

  def test_sudoers_form_matches_deploy_sh_restart_calls(self, doc_text):
    '''REVIEWS HIGH #4 drift guard: doc's two-rule sudoers entry must
    match deploy.sh's two split `sudo -n` calls.'''
    deploy_path = Path('deploy.sh')
    assert deploy_path.exists()
    deploy_text = deploy_path.read_text()
    assert re.search(
      r'^sudo -n systemctl restart trading-signals$',
      deploy_text, re.MULTILINE,
    )
    assert re.search(
      r'^sudo -n systemctl restart trading-signals-web$',
      deploy_text, re.MULTILINE,
    )
    assert (
      '/usr/bin/systemctl restart trading-signals, '
      '/usr/bin/systemctl restart trading-signals-web'
    ) in doc_text
