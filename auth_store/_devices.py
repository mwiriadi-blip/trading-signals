'''auth_store._devices — trusted-device CRUD helpers.

Phase 16.1 Plan 02 (F-01 + E-05 + E-06).

Each helper follows the load -> mutate -> save pattern; mutations are
idempotent (revoke-already-revoked is a no-op, update-last-seen on unknown
uuid is a no-op). Revoked rows are RETAINED in auth.json for audit per
E-06 — never deleted.

All helpers accept the path kwarg via _resolve_path to honour test
monkeypatching of DEFAULT_AUTH_PATH.
'''
import logging
import uuid as _uuid
from datetime import datetime, timezone
from pathlib import Path

from auth_store._io import load_auth, save_auth
from auth_store._schema import TrustedDevice

logger = logging.getLogger(__name__)


def add_trusted_device(label: str, path: Path | None = None) -> str:
  '''Append a new trusted-device row, return the uuid.

  Row shape (F-01 TrustedDevice):
    uuid, label, granted_at, last_seen (== granted_at on creation),
    revoked=False, revoked_at=None.
  '''
  new_uuid = _uuid.uuid4().hex
  now_iso = datetime.now(timezone.utc).isoformat()
  data = load_auth(path=path)
  data['trusted_devices'].append({
    'uuid': new_uuid,
    'label': label,
    'granted_at': now_iso,
    'last_seen': now_iso,
    'revoked': False,
    'revoked_at': None,
  })
  save_auth(data, path=path)
  logger.info('[Auth] trusted_device added: uuid=%s label=%s', new_uuid, label)
  return new_uuid


def revoke_device(uuid_value: str, path: Path | None = None) -> None:
  '''Flip revoked=True + stamp revoked_at on the matching uuid.

  Idempotent: unknown uuid is a no-op; already-revoked uuid is a no-op
  (preserves the original revoked_at timestamp).
  '''
  data = load_auth(path=path)
  changed = False
  for row in data['trusted_devices']:
    if row['uuid'] == uuid_value and not row['revoked']:
      row['revoked'] = True
      row['revoked_at'] = datetime.now(timezone.utc).isoformat()
      changed = True
      break
  if changed:
    save_auth(data, path=path)
    logger.info('[Auth] trusted_device revoked: uuid=%s', uuid_value)


def revoke_all_other_devices(
  except_uuid: str, path: Path | None = None,
) -> int:
  '''Flip revoked=True on every row whose uuid != except_uuid AND not already
  revoked. Returns count of rows newly flipped (excludes already-revoked rows).
  '''
  data = load_auth(path=path)
  now_iso = datetime.now(timezone.utc).isoformat()
  count = 0
  for row in data['trusted_devices']:
    if row['uuid'] != except_uuid and not row['revoked']:
      row['revoked'] = True
      row['revoked_at'] = now_iso
      count += 1
  if count:
    save_auth(data, path=path)
    logger.info(
      '[Auth] revoke_all_other_devices: count=%d except=%s', count, except_uuid,
    )
  return count


def get_trusted_device(
  uuid_value: str, path: Path | None = None,
) -> TrustedDevice | None:
  '''Return the row matching uuid OR None.'''
  data = load_auth(path=path)
  for row in data['trusted_devices']:
    if row['uuid'] == uuid_value:
      return row
  return None


def update_last_seen(uuid_value: str, path: Path | None = None) -> None:
  '''Bump the last_seen timestamp on the matching row.

  No-op if uuid not found (validation is the middleware's job — auth_store
  stays silent for unknown uuids per the same idempotency stance as
  revoke_device).
  '''
  data = load_auth(path=path)
  changed = False
  for row in data['trusted_devices']:
    if row['uuid'] == uuid_value:
      row['last_seen'] = datetime.now(timezone.utc).isoformat()
      changed = True
      break
  if changed:
    save_auth(data, path=path)


def is_uuid_active(uuid_value: str, path: Path | None = None) -> bool:
  '''True iff a row matches uuid AND row.revoked is False.

  Used by middleware._try_cookie to gate tsi_trusted cookie acceptance —
  signature alone is not sufficient; the uuid must still be unrevoked.
  '''
  data = load_auth(path=path)
  for row in data['trusted_devices']:
    if row['uuid'] == uuid_value:
      return row['revoked'] is False
  return False
