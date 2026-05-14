'''auth_store package — atomic JSON persistence for auth.json.

Phase 34 Plan 01: converts the flat auth_store.py monolith to a package.

CRITICAL import ordering (all three cross-AI reviewers flagged this):
  1. DEFAULT_AUTH_PATH defined BEFORE any daughter-module import.
  2. Daughter modules (_io, _devices, _magic_links) imported AFTER.
  3. _io._resolve_path imports DEFAULT_AUTH_PATH lazily inside the
     function body — NOT at module top level — to avoid circular-init.

This ordering keeps all 70+ monkeypatch.setattr(auth_store, 'DEFAULT_AUTH_PATH', ...)
calls working: tests rebind the attribute on THIS module; _resolve_path
re-reads it from auth_store at call time.
'''
import logging
from pathlib import Path

# DEFAULT_AUTH_PATH MUST be defined BEFORE any daughter-module import.
# _io._resolve_path does `from auth_store import DEFAULT_AUTH_PATH` inside
# its function body. That lazy import requires this name to be bound first.
DEFAULT_AUTH_PATH = Path('auth.json')

from auth_store._schema import (  # noqa: E402
  SCHEMA_VERSION,
  AuthData,
  PendingInvite,
  PendingMagicLink,
  TrustedDevice,
  User,
  _ensure_aware,
  _normalize_v2,
)

from auth_store._io import (  # noqa: E402
  _atomic_write,
  _atomic_write_unlocked,
  _default_auth_data,
  _quarantine_corrupt_auth_file,
  _resolve_path,
  load_auth,
  save_auth,
)

from auth_store._devices import (  # noqa: E402
  add_trusted_device,
  get_trusted_device,
  is_uuid_active,
  revoke_all_other_devices,
  revoke_device,
  update_last_seen,
)

from auth_store._magic_links import (  # noqa: E402
  add_magic_link,
  consume_magic_link,
  count_recent_magic_links,
  purge_expired_magic_links,
)

from auth_store._users import (  # noqa: E402
  InviteAlreadyConsumed,
  InviteExpired,
  create_user,
  consume_and_create_user,
  get_user,
  get_user_by_email,
  hash_password,
  list_users,
  mint_invite_token,
  set_user_disabled,
  verify_password,
)

logger = logging.getLogger(__name__)


def get_totp_secret(path: Path | None = None) -> str | None:
  '''F-01: read totp_secret. None if not yet enrolled.'''
  return load_auth(path=path)['totp_secret']


def set_totp_secret(secret: str, path: Path | None = None) -> None:
  '''F-01: write totp_secret AND reset enrolled=False.'''
  data = load_auth(path=path)
  data['totp_secret'] = secret
  data['totp_enrolled'] = False
  data['totp_enrolled_at'] = None
  save_auth(data, path=path)
  logger.info('[Auth] totp secret persisted (enrolled=False)')


def mark_enrolled(path: Path | None = None) -> None:
  '''F-01 E-03: flip totp_enrolled=True after successful TOTP code verification.'''
  from datetime import datetime, timezone
  data = load_auth(path=path)
  data['totp_enrolled'] = True
  data['totp_enrolled_at'] = datetime.now(timezone.utc).isoformat()
  save_auth(data, path=path)
  logger.info('[Auth] totp enrollment finalised at=%s', data['totp_enrolled_at'])


__all__ = [
  'DEFAULT_AUTH_PATH',
  'SCHEMA_VERSION',
  'AuthData',
  'TrustedDevice',
  'PendingMagicLink',
  'User',
  'PendingInvite',
  '_ensure_aware',
  '_normalize_v2',
  'load_auth',
  'save_auth',
  '_atomic_write',
  '_atomic_write_unlocked',
  '_resolve_path',
  '_quarantine_corrupt_auth_file',
  '_default_auth_data',
  'get_totp_secret',
  'set_totp_secret',
  'mark_enrolled',
  'add_trusted_device',
  'revoke_device',
  'revoke_all_other_devices',
  'get_trusted_device',
  'update_last_seen',
  'is_uuid_active',
  'add_magic_link',
  'consume_magic_link',
  'count_recent_magic_links',
  'purge_expired_magic_links',
  'InviteAlreadyConsumed',
  'InviteExpired',
  'create_user',
  'consume_and_create_user',
  'get_user',
  'get_user_by_email',
  'hash_password',
  'list_users',
  'mint_invite_token',
  'set_user_disabled',
  'verify_password',
]
