'''CI gate: assert per-user state paths never enter git tracking.

Fails the test suite if any path under state/users/ is tracked by git
or if the gitignore pattern is missing / inactive — catches a mistaken
'git add -f state/users/...' before it reaches a PR.
'''
import os
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent


def test_state_users_not_tracked():
  result = subprocess.run(
    ['git', 'ls-files', '--', 'state/users/'],
    capture_output=True, text=True, cwd=_REPO_ROOT,
  )
  tracked = result.stdout.strip()
  assert tracked == '', (
    f'state/users/ files are tracked by git: {tracked}'
  )


def test_backup_files_not_tracked():
  result = subprocess.run(
    ['git', 'ls-files', '--', 'state/*.v11-backup-*'],
    capture_output=True, text=True, cwd=_REPO_ROOT,
  )
  tracked = result.stdout.strip()
  assert tracked == '', (
    f'state/*.v11-backup-* files are tracked by git: {tracked}'
  )


def test_state_users_gitignored():
  sentinel_dir = _REPO_ROOT / 'state' / 'users'
  sentinel_path = sentinel_dir / 'test_sentinel.json'
  created_dir = False

  try:
    if not sentinel_dir.exists():
      os.makedirs(sentinel_dir, exist_ok=True)
      created_dir = True
    sentinel_path.write_text('{}')

    result = subprocess.run(
      ['git', 'check-ignore', '-q', 'state/users/test_sentinel.json'],
      capture_output=True, cwd=_REPO_ROOT,
    )
    assert result.returncode == 0, (
      'state/users/test_sentinel.json is NOT gitignored — check .gitignore'
    )
  finally:
    if sentinel_path.exists():
      os.remove(sentinel_path)
    if created_dir:
      try:
        sentinel_dir.rmdir()
      except OSError:
        pass  # non-empty dir — leave it
