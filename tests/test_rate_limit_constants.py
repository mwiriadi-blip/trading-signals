'''WR-04: assert rate-limit constants in auth.py match system_params values.

Drift guard: if a future commit bumps RATE_LIMIT_* in system_params without
updating web/middleware/auth.py (or vice versa), this test fails loudly.

The auth.py file deliberately shadows system_params constants (cannot import
system_params due to AST hex-boundary guard). This test enforces parity.
'''


def test_rate_limit_constants_not_drifted():
  from system_params import (
    RATE_LIMIT_LOGIN_PER_15M,
    RATE_LIMIT_FORGOT_PER_HOUR,
    RATE_LIMIT_RESET_PER_HOUR,
  )
  from web.middleware.auth import (
    RATE_LIMIT_LOGIN_PER_15M as AUTH_LOGIN,
    RATE_LIMIT_FORGOT_PER_HOUR as AUTH_FORGOT,
    RATE_LIMIT_RESET_PER_HOUR as AUTH_RESET,
  )
  assert AUTH_LOGIN == RATE_LIMIT_LOGIN_PER_15M, (
    f'auth.RATE_LIMIT_LOGIN_PER_15M={AUTH_LOGIN} != '
    f'system_params.RATE_LIMIT_LOGIN_PER_15M={RATE_LIMIT_LOGIN_PER_15M}'
  )
  assert AUTH_FORGOT == RATE_LIMIT_FORGOT_PER_HOUR, (
    f'auth.RATE_LIMIT_FORGOT_PER_HOUR={AUTH_FORGOT} != '
    f'system_params.RATE_LIMIT_FORGOT_PER_HOUR={RATE_LIMIT_FORGOT_PER_HOUR}'
  )
  assert AUTH_RESET == RATE_LIMIT_RESET_PER_HOUR, (
    f'auth.RATE_LIMIT_RESET_PER_HOUR={AUTH_RESET} != '
    f'system_params.RATE_LIMIT_RESET_PER_HOUR={RATE_LIMIT_RESET_PER_HOUR}'
  )
