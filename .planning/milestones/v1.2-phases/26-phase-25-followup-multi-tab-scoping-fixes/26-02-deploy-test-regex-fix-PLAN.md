---
phase: 26
plan: 02
type: execute
wave: 1
parallel: true
depends_on: []
files_modified:
  - tests/test_deploy_sh.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "tests/test_deploy_sh.py accepts both `pip install -r requirements.txt` and `python -m pip install -r requirements.txt`"
    - "Three previously-red tests pass: test_step_5_pip_install_requirements_present, test_order_pull_before_pip, test_order_pip_before_systemctl"
    - "Full pytest suite green w.r.t. deploy_sh"
  artifacts:
    - path: tests/test_deploy_sh.py
      provides: "Deploy script regex verifier"
      contains: "python -m"
  key_links:
    - from: "tests/test_deploy_sh.py"
      to: "deploy.sh"
      via: "regex match"
      pattern: "\\.venv/bin/(?:python -m )?pip install"
---

<objective>
B4. Three deploy_sh tests red since commits 5716a60/d6f760b rewrote pip invocation to `python -m pip`. Relax regex.

Purpose: Unblock CI. Wave 1 ships parallel with Plan 03.
Output: 3 regex updates in one file, 3 tests green.
</objective>

<context>
@.planning/phases/26-phase-25-followup-multi-tab-scoping-fixes/26-CONTEXT.md
@.planning/phases/26-phase-25-followup-multi-tab-scoping-fixes/26-PATTERNS.md
@tests/test_deploy_sh.py
@deploy.sh

<interfaces>
# Current regex (3 sites): r'\.venv/bin/pip install -r requirements\.txt'
# Target regex          : r'\.venv/bin/(?:python -m )?pip install -r requirements\.txt'
# deploy.sh now ships: `.venv/bin/python -m pip install -r requirements.txt`
# Test sites: tests/test_deploy_sh.py:93, :129, :133 (per 26-PATTERNS.md §B4)
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Relax pip-install regex in 3 sites</name>
  <files>tests/test_deploy_sh.py</files>
  <action>
Replace every occurrence of:
```
r'\.venv/bin/pip install -r requirements\.txt'
```
with:
```
r'\.venv/bin/(?:python -m )?pip install -r requirements\.txt'
```
Three sites per 26-PATTERNS.md (lines 93, 129, 133). Use search-replace; verify count == 3 before commit.

No other changes. Do not touch deploy.sh.
  </action>
  <verify>
    <automated>grep -v '^#' tests/test_deploy_sh.py | grep -c 'python -m )?pip install -r requirements'</automated>
  </verify>
  <done>Grep returns 3. `pytest tests/test_deploy_sh.py -x` exits 0.</done>
</task>

</tasks>

<verification>
```
pytest tests/test_deploy_sh.py::TestDeployStepFive -x
pytest tests/test_deploy_sh.py::test_order_pull_before_pip -x
pytest tests/test_deploy_sh.py::test_order_pip_before_systemctl -x
```
All three green. Full suite: `pytest -x` no new reds.
</verification>

<success_criteria>
- 3 named tests pass.
- Regex count grep returns exactly 3.
- No diff to deploy.sh.
</success_criteria>

## Rollback

`git revert <plan-02-commit>`. Single-file change; no data migrations.

## Notes

Pattern map: 26-PATTERNS.md §B4. Regex literally specified in CONTEXT B4.

<output>
Create `26-02-SUMMARY.md` listing the 3 regex sites + pytest output.
</output>
