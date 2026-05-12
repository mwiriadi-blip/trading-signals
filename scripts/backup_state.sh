#!/usr/bin/env bash
# Backup state.json to Backblaze B2 via rclone.
# Invoked by trading-signals-backup.service (systemd oneshot).
# Requires: rclone installed + configured with a B2 remote.
# Environment (from .env or systemd EnvironmentFile):
#   RCLONE_REMOTE — rclone remote name (default: b2)
#   B2_BUCKET     — Backblaze B2 bucket name (required)
#   STATE_FILE    — path to state.json (default: state.json)
set -euo pipefail

RCLONE_REMOTE="${RCLONE_REMOTE:-b2}"
B2_BUCKET="${B2_BUCKET:?B2_BUCKET environment variable is required}"
STATE_FILE="${STATE_FILE:-state.json}"

rclone copy "${STATE_FILE}" "${RCLONE_REMOTE}:${B2_BUCKET}/trading-signals/" --log-level INFO
