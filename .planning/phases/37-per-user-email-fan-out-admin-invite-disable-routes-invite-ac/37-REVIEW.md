---
phase: 37-sc5-gap-closure
reviewed: 2026-05-15T00:00:00Z
depth: standard
files_reviewed: 3
files_reviewed_list:
  - web/routes/dashboard/__init__.py
  - dashboard_renderer/components/account.py
  - tests/test_tenant_isolation.py
findings:
  critical: 2
  warning: 2
  info: 1
  total: 5
status: issues_found
---

# Phase 37 (SC-5 gap closure): Code Review Report

**Reviewed:** 2026-05-15T00:00:00Z
**Depth:** standard
**Files Reviewed:** 3
**Status:** issues_found

## Summary

Reviewed the SC-5 gap-closure implementation: per-user state scoping on `/account`
via `_serve_account_page_scoped`, the `_account_include_open_form` flag in
`account.py`, and the un-skipped tenant isolation test.

Two critical issues found. First, the tenant isolation test passes vacuously because
`paper_trades` is never rendered on the `/account` page — the route the test hits.
The isolation guarantee the test is meant to lock is untested. Second, `scoped_state`
leaks all top-level keys from `full_state` via `**full_state` spread, meaning
production-state fields like `positions` and `trade_log` are not scoped per-user.
Both issues are invisible to the test because the test's seeded state omits
top-level `positions` and `trade_log` keys that production state carries.

---

## Critical Issues

### CR-01: Tenant isolation test passes vacuously — paper_trades not rendered on /account

**File:** `tests/test_tenant_isolation.py:164`

**Issue:**
`test_other_user_dashboard_has_no_user_a_trade_content` asserts that user A's
`paper_trades` (with `entry_price`, `n_contracts`, `LONG` direction) do not appear
in user B's `/account` response. The test will always pass regardless of whether
isolation works, because `paper_trades` is never rendered on the `/account` page.

Call chain trace:
1. `/account` -> `_serve_account_page_scoped` -> `render_dashboard_as_str(scoped_state, active_function='account')`
2. `render_dashboard_as_str` -> `_render_single_page_dashboard(ctx, 'account')`
3. `_render_page_body(ctx, 'account')` -> `_account_body()`
4. `_account_body` -> `_render_account_management_region(state)` (`account.py:187`)
5. `_render_account_management_region` calls `render_positions_table` and
   `render_trades_table` — it does NOT call `render_paper_trades_region`

`render_paper_trades_region` (the only function that renders `paper_trades`) is
invoked exclusively from the `signals` page path (`shell.py:290`). The `/account`
route never renders `paper_trades` at all. User A's 5 paper trades with
`entry_price`/`n_contracts`/`LONG` would not appear in user B's `/account`
response even if `scoped_state` were `full_state` verbatim with all user data
merged.

The isolation guarantee SC-5 is meant to provide is untested. If
`render_paper_trades_region` is later wired into the account page (the natural
location for F&F paper-trade history), the isolation gate will be absent.

**Fix — option A (correct the test target):** The test must hit the endpoint that
actually renders `paper_trades`. If paper trades belong on `/account`, wire
`render_paper_trades_region` into `_render_account_management_region` and assert
isolation against `/account`. If they only render on `/signals`, the test must
GET `/signals` (or `/markets/{market_id}/signals`) authenticated as user B.

**Fix — option B (minimum viable sentinel):** Add a positive assertion that the
page rendered actual account content, so any future rendering change that causes
a vacuous pass is caught immediately:

```python
def test_other_user_dashboard_has_no_user_a_trade_content(self, two_user_client):
    client, uid_a, uid_b = two_user_client
    cookie_b = _build_session_cookie(uid_b)
    resp = client.get('/account', cookies={'tsi_session': cookie_b})
    body_text = resp.text

    # Positive sentinel: ensure the account page actually rendered content
    # so a vacuous-pass (empty or 503 response) is caught immediately.
    assert resp.status_code == 200, f'Expected 200, got {resp.status_code}'
    assert 'account-management-region' in body_text, (
        'Expected account-management-region in /account response — '
        'test may be passing vacuously if render path changed'
    )

    matches = TRADE_CONTENT_RE.findall(body_text)
    assert matches == [], (
        f'User A trade content leaked into user B dashboard: {matches}'
    )
```

---

### CR-02: scoped_state spreads full_state — top-level positions/trade_log leak per-user data

**File:** `web/routes/dashboard/__init__.py:214`

**Issue:**
`scoped_state` is constructed as:

```python
scoped_state = {
    **full_state,
    'paper_trades': user_bucket.get('paper_trades', []),
    'equity_history': user_bucket.get('equity_history', []),
    '_account_include_open_form': is_admin,
}
```

The `**full_state` spread copies ALL top-level keys verbatim into `scoped_state`.
In production schema v12, `full_state` contains top-level `positions`, `trade_log`,
`account`, `initial_account` and similar global/admin-scope fields. These are NOT
overridden by the subsequent per-user keys above.

Downstream renderers that read from `scoped_state`:
- `_compute_account_stat_values` (`account.py:104`) reads `state.get('trade_log', [])`
  and iterates `state.get('positions', {})` — both come from `full_state` unchanged
- `render_trades_table` reads `state.get('trade_log', [])` — same

If `full_state` carries global (admin) `trade_log` entries, they will appear in
every user's `/account` stats tile regardless of who is authenticated. If
`full_state` carries a top-level `positions` dict (global admin positions), every
user sees open-exposure figures derived from admin positions.

The test is blind to this because its `seeded_state` (test lines 84-117) has no
top-level `positions` or `trade_log` keys — those fields are only under
`state['users'][uid_*]`, which is not the production schema layout.

**Fix:** Explicitly override all per-user fields when building `scoped_state`:

```python
user_bucket = full_state.get('users', {}).get(uid, {}) or {}
is_admin = (uid == full_state.get('admin_user_id'))
scoped_state = {
    **full_state,
    # Explicit per-user overrides — never let full_state bleed through for these
    'paper_trades':    user_bucket.get('paper_trades', []),
    'equity_history':  user_bucket.get('equity_history', []),
    'trade_log':       user_bucket.get('trade_log', []),
    'positions':       user_bucket.get('positions', {}),
    'account':         user_bucket.get('account', full_state.get('account')),
    'initial_account': user_bucket.get('initial_account', full_state.get('initial_account')),
    '_account_include_open_form': is_admin,
}
```

---

## Warnings

### WR-01: No error handling in _serve_account_page_scoped — render failure returns unhandled 500

**File:** `web/routes/dashboard/__init__.py:184`

**Issue:**
The module docstring states the never-crash contract (D-10): render failures log
WARN and serve stale content, only falling back to 503 on first-run. Every other
render path (`_serve_dashboard_page`, `_serve_dashboard_root`) wraps the render
call in `try/except Exception` to honour this contract.

`_serve_account_page_scoped` has no such guard. Any exception from
`render_dashboard_as_str` or `_substitute` propagates as an unhandled 500. This
route is the most likely to encounter per-user state edge cases (malformed user
bucket, missing keys, None values) that trigger render exceptions.

**Fix:** Wrap the render + substitute block in a try/except matching the D-10
never-crash pattern used by `_serve_dashboard_page`:

```python
try:
    body = render_dashboard_as_str(
        scoped_state, now=None, active_function='account',
    )
    body_bytes = _substitute(body.encode('utf-8'), request)
except Exception as exc:
    logger.warning(
        '[Web] account page render failed uid=%s: %s: %s',
        uid, type(exc).__name__, exc,
    )
    return PlainTextResponse(
        content='dashboard not ready',
        status_code=503,
        media_type='text/plain; charset=utf-8',
    )
```

---

### WR-02: two_user_client seeded_state missing top-level production fields — test is blind to CR-02

**File:** `tests/test_tenant_isolation.py:84`

**Issue:**
The seeded_state fixture omits several top-level fields that production schema v12
carries (`positions`, `trade_log`, `account`, `initial_account`). These are absent
at the top level of `seeded_state` — they exist only inside `state['users'][uid_*]`.

As noted in CR-02, `_serve_account_page_scoped` spreads `full_state` and only
overrides `paper_trades` and `equity_history`. A test that populates production-
realistic top-level `positions` and `trade_log` in `seeded_state` would catch
cross-user leakage via the `**full_state` spread. With the current minimal seeded
state, `full_state.get('positions', {})` evaluates to `{}` and
`full_state.get('trade_log', [])` evaluates to `[]`, so contamination is invisible.

**Fix:** Add production-realistic top-level fields to `seeded_state` that
`_serve_account_page_scoped` must NOT bleed into user B's rendered page:

```python
seeded_state = {
    'schema_version': 12,
    'admin_user_id': uid_a,
    # Production-realistic top-level fields that must be scoped per-user:
    'trade_log': [
        {'net_pnl': 500.0, 'entry_price': 8000.0, 'n_contracts': 3,
         'direction': 'LONG', 'instrument': 'SPI200'},
    ],
    'positions': {
        'SPI200': {'n_contracts': 2, 'direction': 'LONG', 'entry_price': 8000.0},
    },
    ...
}
```

Then assert that user B's `/account` response does not contain `n_contracts` or
`entry_price` values from the admin's top-level positions and trade_log.

---

## Info

### IN-01: _account_include_open_form defaults to True — permissive default creates footgun

**File:** `dashboard_renderer/components/account.py:190`

**Issue:**
`_render_account_management_region` reads:

```python
include_open_form = state.get('_account_include_open_form', True)
```

The default is `True` (show position-open form). Only `_serve_account_page_scoped`
explicitly sets this flag. All other render paths (`render_dashboard_files`,
`render_dashboard_page`, the on-disk `dashboard-account.html`) never set it, so
they render with the admin form visible — which is intentional for the admin path.

The risk: any future code that calls `render_dashboard_as_str` for a non-admin user
without setting `_account_include_open_form` will silently show the admin form.
The safe default direction for a security-sensitive UI element is `False` (hidden),
with admin callers opting in explicitly.

**Fix:** Invert the default to `False` (restrictive) and update `_serve_account_page_scoped`
to pass `True` for the admin case only:

```python
# account.py:190 — default to False (safe/restrictive)
include_open_form = state.get('_account_include_open_form', False)
```

Then in `render_dashboard_files` / `render_dashboard_page` (the admin-only on-disk
path), pass the flag explicitly in state or accept that the on-disk path is
admin-only and document it. This makes the safe path the default and requires
explicit opt-in for the privileged form.

---

_Reviewed: 2026-05-15T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
