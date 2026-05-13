'''auth_store._schema — TypedDicts and schema helpers.

SCHEMA_VERSION = 2 (bumped from v1 in Phase 34 Plan 01).
Provides _normalize_v2 as a pure in-memory migration helper
(no disk I/O) so Plan 02's flock window can call it safely.
'''
import logging
from datetime import datetime, timezone
from typing import TypedDict

logger = logging.getLogger(__name__)

# Phase 34 Plan 01 — bumped from 1 to 2 (adds users + pending_invites).
SCHEMA_VERSION = 2


def _ensure_aware(dt: datetime) -> datetime:
  '''Coerce naive datetime to UTC. All auth_store writes use UTC;
  naive values come from manual edits or pre-timezone-aware code.
  '''
  if dt.tzinfo is None:
    return dt.replace(tzinfo=timezone.utc)
  return dt


class TrustedDevice(TypedDict):
  '''F-01 trusted device row.'''

  uuid: str
  label: str
  granted_at: str
  last_seen: str
  revoked: bool
  revoked_at: str | None


class PendingMagicLink(TypedDict):
  '''F-01 magic-link row.'''

  token_hash: str
  email: str
  action: str
  created_at: str
  expires_at: str
  consumed: bool
  consumed_at: str | None


class User(TypedDict):
  '''Phase 34 D-05 user row.'''

  uid: str
  email: str
  role: str
  created_at: str
  disabled: bool


class PendingInvite(TypedDict):
  '''Phase 34 D-08 pending invite row.'''

  token_hash: str
  email: str
  invited_by: str
  created_at: str
  expires_at: str
  consumed: bool
  consumed_at: str | None


class AuthData(TypedDict):
  '''Top-level auth.json shape (v2).'''

  schema_version: int
  totp_secret: str | None
  totp_enrolled: bool
  totp_enrolled_at: str | None
  trusted_devices: list[TrustedDevice]
  pending_magic_links: list[PendingMagicLink]
  users: list[User]
  pending_invites: list[PendingInvite]


def _normalize_v2(data: dict) -> dict:
  '''Pure in-memory v1->v2 migration helper.

  Backfills users=[] and pending_invites=[] and sets schema_version=2.
  No disk I/O — safe to call inside a LOCK_EX window (Plan 02 reuse).

  Cases:
    - schema_version == 1: upgrade fields, bump version.
    - schema_version == 2: defensive backfill only (no version bump needed).
    - missing or unknown schema_version: emit warning, treat as v2.
  '''
  sv = data.get('schema_version')
  if sv == 1:
    data.setdefault('users', [])
    data.setdefault('pending_invites', [])
    data['schema_version'] = 2
    return data
  if sv == 2:
    data.setdefault('users', [])
    data.setdefault('pending_invites', [])
    return data
  # Missing or unknown schema_version
  logger.warning(
    '[Auth] unknown schema_version=%r in auth.json; treating as v2',
    sv,
  )
  data.setdefault('users', [])
  data.setdefault('pending_invites', [])
  data['schema_version'] = 2
  return data
