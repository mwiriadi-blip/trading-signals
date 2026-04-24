'''Phase 11 WEB-01 + WEB-02 + D-06..D-12 — systemd unit invariants.

2026-04-24 REVIEWS adjustments:
  - MEDIUM #5: EnvironmentFile=- (leading dash, optional).
  - LOW #8: ExecStart references `web.app:app` exactly.
'''
import configparser
from pathlib import Path

import pytest

UNIT_PATH = Path('systemd/trading-signals-web.service')


@pytest.fixture(scope='module')
def unit_text() -> str:
  assert UNIT_PATH.exists(), f'unit file missing: {UNIT_PATH}'
  return UNIT_PATH.read_text()


@pytest.fixture(scope='module')
def unit_cfg(unit_text: str) -> configparser.ConfigParser:
  cfg = configparser.ConfigParser(interpolation=None, strict=True)
  cfg.optionxform = str
  cfg.read_string(unit_text)
  return cfg


class TestSystemdUnitSections:
  def test_unit_section_present(self, unit_cfg):
    assert 'Unit' in unit_cfg.sections()

  def test_service_section_present(self, unit_cfg):
    assert 'Service' in unit_cfg.sections()

  def test_install_section_present(self, unit_cfg):
    assert 'Install' in unit_cfg.sections()


class TestSystemdUnitMetadata:
  def test_description(self, unit_cfg):
    assert unit_cfg['Unit']['Description'] == 'Trading Signals \u2014 FastAPI web process'

  def test_after_network_target(self, unit_cfg):
    assert unit_cfg['Unit']['After'] == 'network.target'

  def test_wants_signal_unit_soft_dep(self, unit_cfg):
    assert unit_cfg['Unit']['Wants'] == 'trading-signals.service'

  def test_no_requires_directive(self, unit_cfg):
    assert 'Requires' not in unit_cfg['Unit']


class TestSystemdServiceCore:
  def test_type_simple(self, unit_cfg):
    assert unit_cfg['Service']['Type'] == 'simple'

  def test_user_trader(self, unit_cfg):
    assert unit_cfg['Service']['User'] == 'trader'

  def test_group_trader(self, unit_cfg):
    assert unit_cfg['Service']['Group'] == 'trader'

  def test_working_directory(self, unit_cfg):
    assert unit_cfg['Service']['WorkingDirectory'] == '/home/trader/trading-signals'

  def test_environment_file_is_optional(self, unit_cfg, unit_text):
    '''REVIEWS MEDIUM #5: `-` prefix makes .env optional.'''
    value = unit_cfg['Service']['EnvironmentFile']
    assert value == '-/home/trader/trading-signals/.env', value
    assert '\nEnvironmentFile=-/home/trader/trading-signals/.env\n' in (
      '\n' + unit_text + '\n'
    )

  def test_environment_file_is_not_required_form(self, unit_text):
    '''Reject non-dash form that would make .env mandatory.'''
    assert 'EnvironmentFile=/home/trader/trading-signals/.env' not in unit_text

  def test_restart_on_failure(self, unit_cfg):
    assert unit_cfg['Service']['Restart'] == 'on-failure'

  def test_restart_sec_10s(self, unit_cfg):
    assert unit_cfg['Service']['RestartSec'] == '10s'

  def test_syslog_identifier(self, unit_cfg):
    assert unit_cfg['Service']['SyslogIdentifier'] == 'trading-signals-web'

  def test_standard_output_journal(self, unit_cfg):
    assert unit_cfg['Service']['StandardOutput'] == 'journal'

  def test_standard_error_journal(self, unit_cfg):
    assert unit_cfg['Service']['StandardError'] == 'journal'


class TestSystemdExecStartBinding:
  def test_execstart_uses_venv_uvicorn(self, unit_cfg):
    exec_start = unit_cfg['Service']['ExecStart']
    assert '/home/trader/trading-signals/.venv/bin/uvicorn' in exec_start

  def test_execstart_references_web_app_module_exactly(self, unit_cfg, unit_text):
    '''REVIEWS LOW #8: ExecStart references Plan 01 `web.app:app` entry.'''
    exec_start = unit_cfg['Service']['ExecStart']
    assert 'web.app:app' in exec_start
    assert 'web.app:app' in unit_text

  def test_execstart_binds_localhost(self, unit_cfg):
    assert '--host 127.0.0.1' in unit_cfg['Service']['ExecStart']

  def test_execstart_does_not_bind_all_interfaces(self, unit_text):
    '''CRITICAL: 0.0.0.0 must NOT appear anywhere.'''
    assert '0.0.0.0' not in unit_text

  def test_execstart_uses_port_8000(self, unit_cfg):
    assert '--port 8000' in unit_cfg['Service']['ExecStart']

  def test_execstart_workers_one(self, unit_cfg):
    assert '--workers 1' in unit_cfg['Service']['ExecStart']

  def test_execstart_log_level_info(self, unit_cfg):
    assert '--log-level info' in unit_cfg['Service']['ExecStart']

  def test_execstart_no_reload_flag(self, unit_text):
    assert '--reload' not in unit_text


class TestSystemdHardening:
  def test_no_new_privileges(self, unit_cfg):
    assert unit_cfg['Service']['NoNewPrivileges'] == 'true'

  def test_private_tmp(self, unit_cfg):
    assert unit_cfg['Service']['PrivateTmp'] == 'true'

  def test_protect_system_strict(self, unit_cfg):
    assert unit_cfg['Service']['ProtectSystem'] == 'strict'

  def test_read_write_paths_repo_only(self, unit_cfg):
    assert unit_cfg['Service']['ReadWritePaths'] == '/home/trader/trading-signals'

  def test_protect_home_read_only(self, unit_cfg):
    assert unit_cfg['Service']['ProtectHome'] == 'read-only'


class TestSystemdInstall:
  def test_wanted_by_multi_user_target(self, unit_cfg):
    assert unit_cfg['Install']['WantedBy'] == 'multi-user.target'
