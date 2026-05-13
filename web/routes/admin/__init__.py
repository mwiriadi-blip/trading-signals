'''Phase 35 D-08 / D-09 — admin sub-router.

All routes on this router require admin role via require_admin dependency
injected at mount time (D-08). New admin routes: register on `router`,
not on `application` directly. The gate is inherited automatically.

Anti-pattern note: if a future contributor adds a route to `application`
instead of `router`, the Plan 05 startup invariant test catches it (it walks
app.routes and checks require_admin in each /admin/* route's dependency list).
'''
from fastapi import APIRouter, Depends

from web.dependencies import require_admin

router = APIRouter(prefix='/admin', dependencies=[Depends(require_admin)])


@router.get('/ping')
def ping():
  '''D-09: non-vacuous startup invariant target. Returns 200 {"ok": true}.'''
  return {'ok': True}


__all__ = ['router']
