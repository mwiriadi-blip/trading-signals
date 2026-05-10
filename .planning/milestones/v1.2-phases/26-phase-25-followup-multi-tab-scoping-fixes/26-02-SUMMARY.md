---
phase: 26
plan: 02
status: complete
date: 2026-05-07
---

# Plan 26-02 — Deploy test regex fix (B4)

## Sites updated

3 occurrences of `r'\.venv/bin/pip install -r requirements\.txt'` →
`r'\.venv/bin/(?:python -m )?pip install -r requirements\.txt'` in:

- `tests/test_deploy_sh.py:94` — `test_step_5_pip_install_requirements_present`
- `tests/test_deploy_sh.py:129` — `test_order_pull_before_pip`
- `tests/test_deploy_sh.py:133` — `test_order_pip_before_systemctl`

`grep -c` count: 3 (matches plan target).

## pytest

`.venv/bin/pytest tests/test_deploy_sh.py` → **41 passed in 0.19s**.

The 3 previously red tests are now green. No diff to `deploy.sh`.

## Files

- `tests/test_deploy_sh.py` (3 regex relaxations, single replace_all)
