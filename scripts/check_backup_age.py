'''Check age of the off-droplet rclone-to-B2 backup and alert if stale.

Run directly (via systemd trading-signals-backup.timer):
  python scripts/check_backup_age.py

Or call check_backup_age() from any orchestration script.

Environment variables:
  RCLONE_REMOTE  — rclone remote name (default: 'b2')
  B2_BUCKET      — Backblaze B2 bucket name (required)
  BACKUP_THRESHOLD_HOURS — hours before alert fires (default: 48)
'''
import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


def parse_rclone_lsl_line(line: str) -> datetime | None:
  '''Parse one line of rclone lsl output into a UTC datetime.

  Expected format: "  <size> YYYY-MM-DD HH:MM:SS.nnnnnnnnn <path>"
  Returns None on any parse failure.
  '''
  parts = line.split()
  if len(parts) < 4:
    return None
  try:
    date_str = parts[1]
    time_str = parts[2][:8]  # trim nanoseconds
    return datetime.fromisoformat(f'{date_str} {time_str}').replace(
      tzinfo=timezone.utc,
    )
  except (ValueError, IndexError):
    return None


def get_last_backup_time(
  remote: str = 'b2',
  bucket: str = '',
  path: str = 'trading-signals/state.json',
) -> datetime | None:
  '''Run rclone lsl and return the last-modified UTC datetime, or None.'''
  if not bucket:
    logger.error('[Backup] B2_BUCKET not set — cannot check backup age')
    return None
  try:
    result = subprocess.run(
      ['rclone', 'lsl', f'{remote}:{bucket}/{path}'],
      capture_output=True, text=True,
    )
    if result.returncode != 0:
      logger.error('[Backup] rclone lsl exited %d: %s', result.returncode, result.stderr.strip())
      return None
    for line in result.stdout.splitlines():
      line = line.strip()
      if line:
        return parse_rclone_lsl_line(line)
  except FileNotFoundError:
    logger.error('[Backup] rclone not found — cannot check backup age')
  except Exception as e:  # noqa: BLE001
    logger.error('[Backup] rclone lsl failed: %s', e)
  return None


def check_backup_age(
  threshold_hours: int = 48,
  now: datetime | None = None,
  remote: str = 'b2',
  bucket: str = '',
) -> None:
  '''Alert via email if backup is older than threshold_hours.

  Treats None last_backup (rclone failure / no file) as stale.
  '''
  import notifier
  if now is None:
    now = datetime.now(timezone.utc)
  last_backup = get_last_backup_time(remote=remote, bucket=bucket)
  if last_backup is None or (now - last_backup) > timedelta(hours=threshold_hours):
    last_iso = last_backup.isoformat() if last_backup else 'unknown'
    logger.warning('[Backup] backup stale (last=%s) — sending alert', last_iso)
    notifier.send_backup_stale_email(last_iso, now=now)


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  _bucket = os.environ.get('B2_BUCKET', '').strip()
  if not _bucket:
    print('ERROR: B2_BUCKET environment variable is required', file=sys.stderr)
    sys.exit(1)
  _remote = os.environ.get('RCLONE_REMOTE', 'b2')
  _threshold = int(os.environ.get('BACKUP_THRESHOLD_HOURS', '48'))
  check_backup_age(threshold_hours=_threshold, remote=_remote, bucket=_bucket)
