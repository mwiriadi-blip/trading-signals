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
'''
from pydantic import BaseModel


class PublicUserSummary(BaseModel):
  '''Minimal public view of a registered user, safe for admin display.

  FastAPI response_model=list[PublicUserSummary] enforces redaction
  automatically — any key NOT declared here is stripped from the JSON
  response before it leaves the server.

  Fields:
    user_id           — uid from auth_store (uuid4().hex)
    display_name      — user email (D-08: admin already knows all emails)
    status            — "active" | "disabled" (D-09: derived from user.disabled)
    last_seen_date    — ISO YYYY-MM-DD or None; deferred to Phase 37
                        (no device-lookup wired yet — A1 assumption)
    has_active_position — True if any instrument position is non-None
                          in state['users'][uid]['positions'] (Q5)
  '''
  user_id: str
  display_name: str
  status: str
  last_seen_date: str | None
  has_active_position: bool
