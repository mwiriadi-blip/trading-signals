'''Phase 38 Plan 04 — POST /news/{market}/dismiss/{title_hash}
                   + POST /news/{market}/toggle-collapse

Both routes are POST-only (GET must NOT mutate — T-38-04-07).
Auth-gated via Depends(current_user_id) (T-38-04-06).
Writes via mutate_user_state (T-38-04-03: per-user isolation).
D-08 auto-expiry implemented atomically inside the mutator callback.

register(app) pattern matches web/routes/healthz.py.
Local imports inside handlers preserve hex boundary (Phase 11 C-2).
'''
import re

from fastapi import Depends, FastAPI, HTTPException, Response

from system_params import KNOWN_MARKET_IDS as _VALID_MARKETS
from web.dependencies import current_user_id

# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

# Valid title_hash: exactly 16 lowercase hex chars (sha256[:16] from news_fetcher)
_HASH_RE = re.compile(r'^[0-9a-f]{16}$')


def _is_known_market(market: str) -> bool:
  '''Return True iff market is in the known-market allowlist.

  Uses the same frozenset as news_fetcher._VALID_MARKETS (T-38-04-04).
  '''
  return market in _VALID_MARKETS


# ---------------------------------------------------------------------------
# Route factory
# ---------------------------------------------------------------------------

def register(app: FastAPI) -> None:
  '''Register POST /news/{market}/dismiss/{title_hash}
             + POST /news/{market}/toggle-collapse.

  No GET methods are registered — GET must not mutate (T-38-04-07).
  '''

  @app.post('/news/{market}/dismiss/{title_hash}')
  def dismiss_headline(
    market: str,
    title_hash: str,
    uid: str = Depends(current_user_id),
  ) -> Response:
    '''Dismiss a headline for the current user + market.

    Validates market (404) and title_hash format (422), then writes
    into state['users'][uid]['news_dismissed'][market] via mutate_user_state.

    D-08 auto-expiry: if the stored date != today, hashes are reset to []
    and date updated INSIDE the mutator (atomic under per-user flock).

    Returns empty 200 text/html (HTMX outerHTML swap removes the row).
    '''
    if not _is_known_market(market):
      raise HTTPException(status_code=404, detail='unknown market')
    if not _HASH_RE.fullmatch(title_hash):
      raise HTTPException(status_code=422, detail='invalid title_hash')

    # Local imports (C-2 hex discipline)
    from datetime import date
    from state_manager import mutate_user_state

    today = date.today().isoformat()

    def _apply(state: dict) -> None:
      users = state.setdefault('users', {})
      user = users.setdefault(uid, {})
      nd_root = user.setdefault('news_dismissed', {})
      bucket = nd_root.setdefault(market, {'date': '', 'hashes': []})
      # D-08 atomic auto-expiry — inside the mutator for atomicity
      if bucket.get('date') != today:
        bucket['date'] = today
        bucket['hashes'] = []
      if title_hash not in bucket['hashes']:
        bucket['hashes'].append(title_hash)

    mutate_user_state(uid, _apply)
    return Response(content='', media_type='text/html')

  @app.post('/news/{market}/toggle-collapse')
  def toggle_collapse(
    market: str,
    uid: str = Depends(current_user_id),
  ) -> Response:
    '''Toggle the news panel collapsed state for the current user + market.

    POST verb is MANDATORY — GET must not mutate (T-38-04-07 / HTTP semantics).
    Flips state['users'][uid]['news_panel_collapsed'][market] bool.
    First-visit safe: setdefault chain initialises missing keys.

    Returns empty 200 text/html.
    '''
    if not _is_known_market(market):
      raise HTTPException(status_code=404, detail='unknown market')

    # Local imports (C-2 hex discipline)
    from state_manager import mutate_user_state

    def _apply(state: dict) -> None:
      users = state.setdefault('users', {})
      user = users.setdefault(uid, {})
      col_root = user.setdefault('news_panel_collapsed', {})
      col_root[market] = not col_root.get(market, False)

    mutate_user_state(uid, _apply)
    return Response(content='', media_type='text/html')
