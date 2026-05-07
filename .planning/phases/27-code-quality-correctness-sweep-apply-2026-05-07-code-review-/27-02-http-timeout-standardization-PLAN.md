---
phase: 27
plan: 02
type: execute
wave: 1
parallel: true
depends_on: []
files_modified:
  - system_params.py
  - notifier.py
  - data_fetcher.py
  - tests/test_http_timeouts.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "Every requests.* / urllib / httpx / yfinance HTTP call passes timeout= sourced from system_params.HTTP_TIMEOUT_S."
    - "system_params.HTTP_TIMEOUT_S = 30 (single value; both connect and read)."
    - "Grep gate: zero requests.(get|post|put|delete|head|patch) calls without timeout= argument in production code."
  artifacts:
    - path: system_params.py
      provides: "HTTP_TIMEOUT_S constant"
      contains: "HTTP_TIMEOUT_S"
    - path: tests/test_http_timeouts.py
      provides: "AST-walk test asserting every requests.* call site has timeout= kwarg"
      contains: "HTTP_TIMEOUT_S"
  key_links:
    - from: "notifier.requests.post"
      to: "system_params.HTTP_TIMEOUT_S"
      via: "timeout= kwarg"
      pattern: "timeout=HTTP_TIMEOUT_S"
---

<objective>
Standardize every outbound HTTP call's timeout. Add HTTP_TIMEOUT_S = 30 in system_params. Audit and patch notifier.py (Resend POST), data_fetcher.py (yfinance is itself a wrapper around requests; if its public API exposes timeout, pass it), and any other call sites.

Purpose: hung-network safety (review item #5). Without explicit timeout, requests blocks indefinitely on stuck sockets — daily run hangs and crash-email path is never reached.
Output: HTTP_TIMEOUT_S constant + AST-walk regression test + patched call sites.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@system_params.py
@notifier.py
@data_fetcher.py

<interfaces>
# system_params.py constants block — add HTTP_TIMEOUT_S near STRATEGY_VERSION (line 27).
#
# Known production HTTP call sites (from grep):
#   notifier.py:1367 — requests.post(...) to Resend API
#   data_fetcher.py — yfinance.Ticker.history() — yfinance does NOT expose timeout in 1.2.0 public API; document that gap.
#
# yfinance internally uses requests-cache; timeout knob in 1.2.0 is via the underlying session. Workaround:
# create a `requests.Session()` with `session.request = functools.partial(session.request, timeout=HTTP_TIMEOUT_S)`
# and pass via `yf.Ticker(symbol, session=session)`. If 1.2.0's Ticker doesn't accept session kwarg, document
# as "yfinance lib limitation — out of project scope; track in DEBT.md".
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: HTTP_TIMEOUT_S constant + audit + patch + grep gate</name>
  <read_first>
    - system_params.py (full)
    - notifier.py lines 1340-1410 (the existing requests.post block)
    - data_fetcher.py (full — 132 lines)
  </read_first>
  <behavior>
    - test_http_timeout_constant_present: HTTP_TIMEOUT_S == 30 (int).
    - test_no_bare_requests_call_in_prod: AST-walk every .py at repo root + auth_store.py + notifier.py + data_fetcher.py + dashboard.py + main.py + state_manager.py + web/ — every Call to requests.{get,post,put,delete,head,patch} must have a `timeout=` keyword. Tests dir excluded.
    - test_notifier_resend_post_uses_constant: grep for `timeout=HTTP_TIMEOUT_S` literal in notifier.py at the requests.post block.
  </behavior>
  <action>
1. **system_params.py:** add `HTTP_TIMEOUT_S: int = 30  # Phase 27 #5: single connect+read timeout for all outbound HTTP` near line 27.

2. **notifier.py line 1367:** the requests.post already exists; check the keyword args. If timeout is missing or hardcoded, replace with `timeout=HTTP_TIMEOUT_S` (import HTTP_TIMEOUT_S from system_params at top of notifier.py — check existing import block; system_params is already imported per `from system_params import (FALLBACK_CONTRACT_SPECS, ...)`).

3. **data_fetcher.py:** locate the yfinance fetch call (likely `yf.Ticker(symbol).history(...)` or `yf.download(...)`). Construct a `requests.Session()` with default timeout via:
   ```python
   import requests
   from system_params import HTTP_TIMEOUT_S
   _session = None
   def _get_session():
     global _session
     if _session is None:
       s = requests.Session()
       _orig = s.request
       def _patched(method, url, **kwargs):
         kwargs.setdefault('timeout', HTTP_TIMEOUT_S)
         return _orig(method, url, **kwargs)
       s.request = _patched
       _session = s
     return _session
   ```
   Pass `session=_get_session()` to `yf.Ticker(...)` IF the constructor accepts it (yfinance 1.2.0 — check signature; `inspect.signature(yf.Ticker.__init__).parameters` will say). If not: document as deferred limitation in 27-DEBT.md and rely on the OS-level socket timeout fallback. Either way the project has DONE the right thing on its side.

4. **tests/test_http_timeouts.py (NEW):** 3 tests per behavior block. The AST walker:
   ```python
   import ast, pathlib
   PROD_FILES = ['notifier.py', 'data_fetcher.py', 'dashboard.py', 'main.py', 'state_manager.py', 'auth_store.py']
   def _walk_module(path):
     tree = ast.parse(pathlib.Path(path).read_text())
     for node in ast.walk(tree):
       if isinstance(node, ast.Call):
         f = node.func
         # match requests.METHOD(...)
         if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == 'requests':
           if f.attr in {'get','post','put','delete','head','patch'}:
             kws = {kw.arg for kw in node.keywords}
             yield (path, node.lineno, f.attr, 'timeout' in kws)
   ```
   Test asserts every yielded tuple has `'timeout' in kws == True`.

5. Run `pytest tests/test_http_timeouts.py -x -v` and confirm green.

6. Grep verification:
   ```
   grep -rn 'requests\.\(get\|post\|put\|delete\|head\|patch\)' notifier.py data_fetcher.py dashboard.py main.py state_manager.py auth_store.py | grep -v 'timeout='
   # expected: zero matches (or only inside a string literal — visual review)
   ```
  </action>
  <verify>
    <automated>pytest tests/test_http_timeouts.py -x -v</automated>
  </verify>
  <done>
    - `grep -n 'HTTP_TIMEOUT_S' system_params.py` shows the constant.
    - `grep -n 'timeout=HTTP_TIMEOUT_S' notifier.py` shows at least one call.
    - test_http_timeouts.py 3 tests green.
    - AST walker: zero requests.* call sites in PROD_FILES without timeout kwarg.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| droplet → Resend API | Outbound HTTPS — could hang indefinitely on stuck socket without timeout |
| droplet → yfinance/Yahoo | Same |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation |
|-----------|----------|-----------|-------------|------------|
| T-27-02-01 | DoS (self-inflicted) | Daily run hangs forever on stuck network — crash-email never fires, operator silently loses signal delivery | mitigate | HTTP_TIMEOUT_S=30 forces TimeoutError → bubbles to crash-email path. AST walker prevents regression. |
| T-27-02-02 | Information disclosure | N/A — timeout doesn't change request payload | accept | — |
</threat_model>

<verification>
```
pytest tests/test_http_timeouts.py -x -v
grep -rn 'requests\.\(get\|post\|put\|delete\|head\|patch\)' notifier.py data_fetcher.py dashboard.py main.py state_manager.py auth_store.py | grep -v 'timeout='
# expected: zero matches in production code
```
</verification>

<success_criteria>
- HTTP_TIMEOUT_S = 30 in system_params.py.
- Every requests.* call in production .py files passes timeout=HTTP_TIMEOUT_S.
- yfinance call passes a session with timeout default OR limitation documented in 27-DEBT.md.
- AST regression test green.
</success_criteria>

<output>
Create `27-02-SUMMARY.md` with: list of patched call sites, yfinance session-injection outcome (worked / documented as deferred), AST walker output (0 violations).
</output>
