'''Unit tests for scripts/check_backup_age.py stale-backup logic.

Tests mock subprocess.run (for rclone) and notifier.send_backup_stale_email
to exercise the pure stale-detection logic without real I/O.
'''
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add scripts/ to path so check_backup_age is importable
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

from check_backup_age import check_backup_age, get_last_backup_time, parse_rclone_lsl_line


class TestParseRcloneLslLine:
  def test_valid_line(self):
    line = '  12345 2026-05-12 14:30:00.000000000 state.json'
    result = parse_rclone_lsl_line(line)
    assert result == datetime(2026, 5, 12, 14, 30, 0, tzinfo=timezone.utc)

  def test_empty_line_returns_none(self):
    assert parse_rclone_lsl_line('') is None

  def test_short_line_returns_none(self):
    assert parse_rclone_lsl_line('12345 2026-05-12') is None

  def test_bad_date_returns_none(self):
    assert parse_rclone_lsl_line('12345 not-a-date 14:30:00.000 state.json') is None


class TestCheckBackupAge:
  _NOW = datetime(2026, 5, 13, 12, 0, 0, tzinfo=timezone.utc)

  def _make_lsl_output(self, dt: datetime) -> str:
    ts = dt.strftime('%Y-%m-%d %H:%M:%S.000000000')
    return f'  12345 {ts} state.json\n'

  def test_not_stale(self):
    from datetime import timedelta
    last_backup = self._NOW - timedelta(hours=24)
    lsl_output = self._make_lsl_output(last_backup)
    fake_result = MagicMock(stdout=lsl_output, returncode=0)
    with patch('subprocess.run', return_value=fake_result), \
         patch('notifier.send_backup_stale_email') as mock_alert:
      check_backup_age(threshold_hours=48, now=self._NOW, bucket='test-bucket')
    mock_alert.assert_not_called()

  def test_stale(self):
    last_backup = datetime(2026, 5, 11, 11, 0, 0, tzinfo=timezone.utc)  # 49h ago
    lsl_output = self._make_lsl_output(last_backup)
    fake_result = MagicMock(stdout=lsl_output, returncode=0)
    with patch('subprocess.run', return_value=fake_result), \
         patch('notifier.send_backup_stale_email') as mock_alert:
      check_backup_age(threshold_hours=48, now=self._NOW, bucket='test-bucket')
    mock_alert.assert_called_once()

  def test_exactly_48h_not_stale(self):
    # Exactly 48h — threshold is strictly >, so NOT stale
    last_backup = datetime(2026, 5, 11, 12, 0, 0, tzinfo=timezone.utc)  # exactly 48h
    lsl_output = self._make_lsl_output(last_backup)
    fake_result = MagicMock(stdout=lsl_output, returncode=0)
    with patch('subprocess.run', return_value=fake_result), \
         patch('notifier.send_backup_stale_email') as mock_alert:
      check_backup_age(threshold_hours=48, now=self._NOW, bucket='test-bucket')
    mock_alert.assert_not_called()

  def test_none_last_backup_triggers_alert(self):
    # rclone returns empty output → None → treated as stale
    fake_result = MagicMock(stdout='', returncode=0)
    with patch('subprocess.run', return_value=fake_result), \
         patch('notifier.send_backup_stale_email') as mock_alert:
      check_backup_age(threshold_hours=48, now=self._NOW, bucket='test-bucket')
    mock_alert.assert_called_once()
