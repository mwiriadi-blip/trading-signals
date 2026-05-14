'''Pydantic response models for web/routes/admin package.

Phase 36 D-07 through D-11:
  PublicUserSummary is an output-only model used with FastAPI
  response_model=list[PublicUserSummary] on GET /admin/users.
  FastAPI's response_model serialisation strips ALL fields NOT listed on
  this model at serialisation time — paper_trades, equity_history,
  entry_price, n_contracts, trade_log and any other per-user trade content
  can never appear in the response body (TENANT-03 / T-36-02).

  No model_config is set (output-only; not a request validator, so
  extra='forbid' is not applicable here).

Phase 37:
  PendingInviteSummary — summary of a pending invite for admin display.
  _compute_last_seen_date — helper to extract max last_seen from trusted devices.
'''
from pydantic import BaseModel


def _compute_last_seen_date(trusted_devices: list) -> str | None:
  '''Return the most-recent last_seen ISO date (YYYY-MM-DD) across all
  non-revoked trusted devices for a user. Returns None if no devices.

  Phase 37: populates PublicUserSummary.last_seen_date from auth.json
  trusted_devices rows (T-37-05-14 accepted — admin legitimately sees this).
  '''
  dates = []
  for dev in trusted_devices:
    ls = dev.get('last_seen', '')
    if ls:
      # last_seen is an ISO datetime string; take the date portion (first 10 chars)
      dates.append(ls[:10])
  if not dates:
    return None
  return max(dates)


class PendingInviteSummary(BaseModel):
  '''Minimal view of a pending invite for admin display.

  Phase 37: admin UI shows token_hash as the revoke key (D-09 — admin
  copy-pastes or clicks Revoke; raw token never shown again after issue).
  '''
  token_hash: str
  email: str
  invited_by: str
  created_at: str
  expires_at: str
  consumed: bool


class PublicUserSummary(BaseModel):
  '''Minimal public view of a registered user, safe for admin display.

  FastAPI response_model=list[PublicUserSummary] enforces redaction
  automatically — any key NOT declared here is stripped from the JSON
  response before it leaves the server.

  Fields:
    user_id           — uid from auth_store (uuid4().hex)
    display_name      — user email (D-08: admin already knows all emails)
    status            — "active" | "disabled" (D-09: derived from user.disabled)
    last_seen_date    — ISO YYYY-MM-DD or None; Phase 37: populated from
                        most-recent TrustedDevice.last_seen across user's devices
    has_active_position — True if any instrument position is non-None
                          in state['users'][uid]['positions'] (Q5)
  '''
  user_id: str
  display_name: str
  status: str
  last_seen_date: str | None
  has_active_position: bool
