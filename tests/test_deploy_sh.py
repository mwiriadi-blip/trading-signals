'''Phase 11 INFRA-04 + D-20..D-25 — deploy.sh invariants guard.

2026-04-24 reconciled post-REVIEWS:
  - MEDIUM #7: `pip install --upgrade pip` DROPPED (negative assertion).
  - HIGH #4: combined restart FORBIDDEN; two `sudo -n` calls REQUIRED.
  - HIGH #3: `sleep 3` heuristic FORBIDDEN; retry loop REQUIRED.
'''
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

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


class TestDeployShStructure:
  def test_shebang_first_line(self, deploy_lines):
    assert deploy_lines[0] == '#!/usr/bin/env bash'

  def test_set_euo_pipefail_present(self, deploy_text):
    assert re.search(r'^set -euo pipefail$', deploy_text, re.MULTILINE)

  def test_file_is_executable(self):
    st = DEPLOY_SH.stat()
    assert st.st_mode & stat.S_IXUSR

  def test_bash_syntax_check_passes(self):
    bash = shutil.which('bash')
    if bash is None:
      pytest.skip('bash not available')
    result = subprocess.run([bash, '-n', str(DEPLOY_SH)], capture_output=True, text=True)
    assert result.returncode == 0

  def test_log_prefix_on_echoes(self, deploy_text):
    echo_lines = re.findall(r'^\s*echo .+$', deploy_text, re.MULTILINE)
    assert len(echo_lines) >= 8
    prefixed = [e for e in echo_lines if '[deploy]' in e]
    assert len(prefixed) >= 8


class TestDeployShBranchSafety:
  def test_branch_check_present(self, deploy_text):
    assert 'git rev-parse --abbrev-ref HEAD' in deploy_text

  def test_branch_compared_to_main(self, deploy_text):
    assert re.search(r'BRANCH.*!=.*main', deploy_text)

  def test_branch_check_exits_on_mismatch(self, deploy_text):
    assert "expected branch 'main'" in deploy_text
    assert 'exit 1' in deploy_text

  def test_branch_check_runs_before_fetch(self, deploy_lines):
    b = _line_index(deploy_lines, r'git rev-parse --abbrev-ref HEAD')
    f = _line_index(deploy_lines, r'git fetch origin main')
    assert b < f


class TestDeployShSequence:
  '''D-23 sequence — presence + cross-step ordering + post-REVIEWS.'''

  def test_step_2_fetch_present(self, deploy_text):
    assert re.search(r'^git fetch origin main$', deploy_text, re.MULTILINE)

  def test_step_3_pull_ff_only_present(self, deploy_text):
    assert re.search(r'^git pull --ff-only origin main$', deploy_text, re.MULTILINE)

  def test_step_4_pip_upgrade_is_DROPPED(self, deploy_text):
    '''REVIEWS MEDIUM #7: pip-upgrade removed.'''
    assert 'pip install --upgrade pip' not in deploy_text

  def test_step_5_pip_install_requirements_present(self, deploy_text):
    assert re.search(r'\.venv/bin/pip install -r requirements\.txt', deploy_text)

  def test_step_6_two_sudo_restart_calls(self, deploy_text):
    '''REVIEWS HIGH #4: each unit gets its own `sudo -n systemctl restart`.'''
    assert re.search(
      r'^sudo -n systemctl restart trading-signals$', deploy_text, re.MULTILINE,
    )
    assert re.search(
      r'^sudo -n systemctl restart trading-signals-web$', deploy_text, re.MULTILINE,
    )

  def test_step_6_combined_restart_is_FORBIDDEN(self, deploy_text):
    '''REVIEWS HIGH #4: combined form may not match sudoers rules.'''
    assert 'sudo systemctl restart trading-signals trading-signals-web' not in deploy_text

  def test_step_7_smoke_test_uses_retry_loop(self, deploy_text):
    '''REVIEWS HIGH #3: retry loop replaces `sleep 3 && curl`.'''
    assert re.search(r'for i in 1 2 3 4 5 6 7 8 9 10', deploy_text)
    assert 'curl -fsS --max-time 2 http://127.0.0.1:8000/healthz' in deploy_text

  def test_step_7_sleep_3_heuristic_is_FORBIDDEN(self, deploy_text):
    '''REVIEWS HIGH #3: standalone `sleep 3` forbidden.'''
    assert not re.search(r'^\s*sleep 3\s*$', deploy_text, re.MULTILINE)

  def test_step_8_commit_hash_echoed(self, deploy_text):
    assert 'git rev-parse --short HEAD' in deploy_text
    assert 'deploy complete' in deploy_text

  def test_order_fetch_before_pull(self, deploy_lines):
    f = _line_index(deploy_lines, r'git fetch origin main')
    p = _line_index(deploy_lines, r'git pull --ff-only origin main')
    assert f < p

  def test_order_pull_before_pip(self, deploy_lines):
    p = _line_index(deploy_lines, r'git pull --ff-only origin main')
    i = _line_index(deploy_lines, r'\.venv/bin/pip install -r requirements\.txt')
    assert p < i

  def test_order_pip_before_systemctl(self, deploy_lines):
    i = _line_index(deploy_lines, r'\.venv/bin/pip install -r requirements\.txt')
    s = _line_index(deploy_lines, r'^sudo -n systemctl restart trading-signals$')
    assert i < s

  def test_order_first_unit_before_second_unit(self, deploy_lines):
    a = _line_index(deploy_lines, r'^sudo -n systemctl restart trading-signals$')
    b = _line_index(deploy_lines, r'^sudo -n systemctl restart trading-signals-web$')
    assert a < b

  def test_order_systemctl_before_curl(self, deploy_lines):
    s = _line_index(deploy_lines, r'^sudo -n systemctl restart trading-signals-web$')
    c = _line_index(deploy_lines, r'curl -fsS --max-time 2 http://127\.0\.0\.1:8000/healthz')
    assert s < c

  def test_order_curl_before_commit_echo(self, deploy_lines):
    c = _line_index(deploy_lines, r'curl -fsS --max-time 2 http://127\.0\.0\.1:8000/healthz')
    h = _line_index(deploy_lines, r'git rev-parse --short HEAD')
    assert c < h


class TestDeployShSafety:
  '''D-25: no auto-revert.'''

  def test_no_git_revert(self, deploy_text):
    assert 'git revert' not in deploy_text

  def test_no_git_reset_hard(self, deploy_text):
    assert 'git reset --hard' not in deploy_text

  def test_no_rollback_keyword(self, deploy_text):
    assert re.search(r'\brollback\b', deploy_text, re.IGNORECASE) is None

  def test_smoke_test_uses_loopback_not_external_ip(self, deploy_text):
    assert '0.0.0.0' not in deploy_text
    urls = re.findall(r'http://[^\s/]+', deploy_text)
    for url in urls:
      assert '127.0.0.1' in url

  def test_errors_go_to_stderr(self, deploy_text):
    assert deploy_text.count('>&2') >= 2

  def test_two_exit_one_paths(self, deploy_text):
    exit_lines = [l for l in deploy_text.splitlines() if l.strip() == 'exit 1']
    assert len(exit_lines) >= 2

  def test_no_daemon_reload(self, deploy_text):
    assert 'daemon-reload' not in deploy_text


class TestNginxReloadHook:
  '''Phase 12 D-20 — conditional nginx config-test + reload hook.

  The hook is gated on BOTH `nginx/signals.conf` file presence AND
  `command -v nginx` — pre-Phase-12 droplets (nginx not installed)
  MUST skip the block silently, and repo checkouts without the
  Plan-01 config file MUST also skip.

  T-12-04 (sudoers privilege surface): deploy.sh calls `sudo -n` so
  a misconfigured sudoers rule fails fast (not hanging on password
  prompt). Absolute paths are pinned in the sudoers rule itself
  (SETUP-HTTPS.md Step 8), not inside deploy.sh.
  '''

  def test_gate_file_check_present(self, deploy_text):
    '''D-20: gate must check for nginx/signals.conf (Plan 01 artifact).'''
    assert '[ -f nginx/signals.conf ]' in deploy_text

  def test_gate_command_v_check_present(self, deploy_text):
    '''D-20: `command -v nginx &>/dev/null` is the new optional-feature
    gating idiom — first use in deploy.sh. Pre-Phase-12 droplets
    (no nginx installed) skip silently via this short-circuit.
    '''
    assert 'command -v nginx &>/dev/null' in deploy_text

  def test_gate_uses_logical_and(self, deploy_text):
    '''D-20: BOTH conditions required — `&&` not `||` or two ifs.'''
    # The full gate literal from RESEARCH §Example 4.
    assert (
      'if [ -f nginx/signals.conf ] && command -v nginx &>/dev/null; then'
    ) in deploy_text

  def test_nginx_config_test_call_inside_gate(self, deploy_text):
    '''D-20: `sudo -n nginx -t` (non-interactive config test).

    `-n` fails fast when sudoers path is wrong (Pitfall 7 —
    /usr/sbin/nginx vs /usr/bin/nginx typos).
    '''
    assert re.search(r'^\s*sudo -n nginx -t\s*$', deploy_text, re.MULTILINE)

  def test_nginx_reload_call_inside_gate(self, deploy_text):
    '''D-20: `sudo -n systemctl reload nginx` (non-interactive reload).'''
    assert re.search(
      r'^\s*sudo -n systemctl reload nginx\s*$',
      deploy_text,
      re.MULTILINE,
    )

  def test_no_absolute_nginx_path_in_deploy_sh(self, deploy_text):
    '''deploy.sh uses PATH-relative `nginx` — sudoers pins the
    absolute path (/usr/sbin/nginx). Putting `/usr/sbin/nginx -t`
    in deploy.sh would hardcode a distro-specific path into the
    repo (Pitfall 7 documents Ubuntu /usr/sbin; sudoers is the
    right place for that pinning).
    '''
    assert '/usr/sbin/nginx' not in deploy_text

  def test_order_after_healthz_smoke_test(self, deploy_lines):
    '''D-20 ordering: reload block lives AFTER Phase 11 retry-loop
    smoke test. RESEARCH Open Question 5 recommendation — if
    FastAPI restart fails, `set -e` aborts BEFORE we reload nginx.
    '''
    c = _line_index(
      deploy_lines,
      r'curl -fsS --max-time 2 http://127\.0\.0\.1:8000/healthz',
    )
    n = _line_index(deploy_lines, r'\[ -f nginx/signals\.conf \]')
    assert c < n, (
      f'nginx gate (line {n}) must come AFTER /healthz smoke test '
      f'(line {c})'
    )

  def test_order_before_commit_echo(self, deploy_lines):
    '''D-20 ordering: reload block lives BEFORE final commit-hash echo.'''
    n = _line_index(deploy_lines, r'^\s*sudo -n systemctl reload nginx\s*$')
    h = _line_index(deploy_lines, r'git rev-parse --short HEAD')
    assert n < h, (
      f'nginx reload (line {n}) must come BEFORE commit-hash echo '
      f'(line {h})'
    )

  def test_no_unconditional_nginx_reference_before_gate(self, deploy_text):
    '''Negative: NO nginx mention before the gate line.

    Pre-Phase-12 droplets (no nginx installed) must run deploy.sh
    cleanly. Any `nginx` token before the gate would either crash
    (unknown command) or succeed spuriously.
    '''
    gate_literal = 'if [ -f nginx/signals.conf ]'
    assert gate_literal in deploy_text, 'gate must exist'
    pre_gate = deploy_text.split(gate_literal, 1)[0]
    # Case-insensitive `nginx` scan — includes comments, strings, anything.
    assert 'nginx' not in pre_gate.lower(), (
      'nginx token found BEFORE the gate — pre-Phase-12 droplets '
      'would fail. Move all nginx references inside the gated block.'
    )

  def test_echo_messages_have_deploy_prefix(self, deploy_text):
    '''The new block's echoes follow the existing [deploy] prefix
    convention (Phase 11 test_log_prefix_on_echoes — every echo has it).
    '''
    # Match echo lines that mention nginx; confirm each has [deploy] prefix.
    nginx_echoes = re.findall(
      r'^\s*echo\s+["\'].*nginx.*["\'].*$',
      deploy_text,
      re.MULTILINE | re.IGNORECASE,
    )
    assert len(nginx_echoes) >= 1, 'expected at least 1 nginx-related echo'
    for e in nginx_echoes:
      assert '[deploy]' in e, f'missing [deploy] prefix in echo: {e!r}'
