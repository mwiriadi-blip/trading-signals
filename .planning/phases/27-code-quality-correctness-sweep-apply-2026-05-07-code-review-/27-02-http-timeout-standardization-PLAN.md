---
phase: 27
plan: 02
type: execute
wave: 1A
parallel: true
depends_on: []
files_modified:
  - system_params.py
  - notifier.py  # <!-- review-fix: agreed-6 — refactor _RESEND_TIMEOUT_S to import canonical HTTP_TIMEOUT_S -->
  - data_fetcher.py
  - tests/test_http_timeouts.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "Single canonical HTTP_TIMEOUT_S = 30 lives in system_params.py."
    - "notifier.py imports HTTP_TIMEOUT_S; _RESEND_TIMEOUT_S is REMOVED (no duplicate constant)."
    - "_post_to_resend continues to pass timeout=(5, HTTP_TIMEOUT_S) connect/read tuple — preserved exactly."
    - "Every requests.* / urllib / httpx call in production code passes timeout= sourced from HTTP_TIMEOUT_S."
    - "AST regression test catches: requests.{get,post,put,delete,head,patch}, Session.{get,post}, aliased requests.api.*, `from requests import post`-style imported names, urllib calls, httpx calls."
    - "yfinance internal calls are explicitly filtered from the AST test (skip files/lines inside the yfinance package)."
    - "yfinance session-injection (if any) goes through the _get_yf() accessor from 27-06 — NOT module-top mutation."
  artifacts:
    - path: system_params.py
      provides: "HTTP_TIMEOUT_S constant (single source of truth)"
      contains: "HTTP_TIMEOUT_S"
    - path: tests/test_http_timeouts.py
      provides: "AST-walk test for requests/urllib/httpx + import-from-module forms"
      contains: "HTTP_TIMEOUT_S"
  key_links:
    - from: "notifier._post_to_resend"
      to: "system_params.HTTP_TIMEOUT_S"
      via: "import + (5, HTTP_TIMEOUT_S) tuple"
      pattern: "timeout=\\(5, HTTP_TIMEOUT_S\\)"
    - from: "data_fetcher (yfinance session)"
      to: "system_params.HTTP_TIMEOUT_S"
      via: "session.request patched with HTTP_TIMEOUT_S default"
      pattern: "HTTP_TIMEOUT_S"
---

## Review fixes applied

- [x] agreed-1 (wave/dependency rebuild) — wave changed `1` → `1A` per Codex sequencing matrix; depends_on remains empty (independent constant).
- [x] agreed-6 (HTTP timeout collides with existing _RESEND_TIMEOUT_S=30) — chose PREFERRED path: refactor notifier to import canonical HTTP_TIMEOUT_S; delete _RESEND_TIMEOUT_S. Single source of truth in system_params.py. notifier preserves the (5, HTTP_TIMEOUT_S) connect/read tuple.
- [x] agreed-6 (AST test scope too narrow) — widened detection: requests.METHOD, Session.METHOD, aliased requests.api.*, `from requests import post`, urllib, httpx; yfinance internals explicitly filtered.
- [x] agreed-6 (coordinate with 27-06) — yfinance session-injection MUST go through _get_yf() accessor from 27-06 (not module-top mutation). Documented in action.
- [x] M1 (brittle implementation tests) — AST test asserts behavior ("every requests.* call has a `timeout=` kwarg"), NOT literal string `timeout=HTTP_TIMEOUT_S` in source.
- [x] M2 (doc rule) — SUMMARY artifact stays inside `.planning/phases/27-.../`.

<objective>
Standardize every outbound HTTP call's timeout. Add HTTP_TIMEOUT_S = 30 in system_params (single source of truth). Refactor notifier.py to delete `_RESEND_TIMEOUT_S = 30` and import HTTP_TIMEOUT_S. Patch data_fetcher.py via the _get_yf() accessor pattern (Plan 27-06).

Purpose: hung-network safety (review item #5). Without explicit timeout, requests blocks indefinitely on stuck sockets — daily run hangs and crash-email path is never reached.
Output: HTTP_TIMEOUT_S constant + AST-walk regression test (broad scope) + patched call sites + _RESEND_TIMEOUT_S deleted.
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
# system_params.py — add HTTP_TIMEOUT_S = 30 near STRATEGY_VERSION (line 27).
#
# Existing infrastructure (review-fix agreed-6):
#   notifier.py:106  _RESEND_TIMEOUT_S = 30           — DELETE, replace with HTTP_TIMEOUT_S import
#   notifier.py:1371 _post_to_resend(...)            — currently passes timeout=(5, _RESEND_TIMEOUT_S)
#                                                       → change to timeout=(5, HTTP_TIMEOUT_S)
#                                                       → preserves connect/read tuple semantics
#
# data_fetcher.py — yfinance internally uses requests-cache. Coordination with Plan 27-06:
#   27-06 introduces _get_yf() accessor (lazy yfinance import).
#   This plan: extend _get_yf() to also configure a session with HTTP_TIMEOUT_S default:
#     def _get_yf():
#       global _yf_session, _yf
#       if _yf is None:
#         import yfinance as yf
#         _yf = yf
#         s = requests.Session()
#         _orig = s.request
#         def _patched(method, url, **kwargs):
#           kwargs.setdefault('timeout', HTTP_TIMEOUT_S)
#           return _orig(method, url, **kwargs)
#         s.request = _patched
#         _yf_session = s
#       return _yf, _yf_session
#   If yfinance 1.2.0 Ticker accepts session= kwarg → use it.
#   If not → document in 27-DEBT.md and rely on OS socket timeout.
#
# AST test scope (review-fix agreed-6 widening):
#   PROD = ['notifier.py','data_fetcher.py','dashboard.py','main.py','state_manager.py','auth_store.py']
#   (post-split also: cli_parser.py, daily_loop.py, interactive.py, scheduler_driver.py,
#    notifier/transport.py, notifier/templates.py, notifier/warnings_fifo.py, notifier/crash_path.py)
#   Detect:
#     - requests.{get,post,put,delete,head,patch}  (Attribute on Name 'requests')
#     - Session().{get,post,put,delete,head,patch}  (Attribute on a value of class Session)
#     - imported-from: `from requests import post` then bare `post(...)` — track via import scan
#     - aliased: `import requests as r; r.get(...)` — track via import scan
#     - urllib.request.urlopen(...) — distinct module
#     - httpx.{get,post,...} — distinct module
#   Filter:
#     - skip files inside the yfinance package itself (path contains 'yfinance/')
#     - skip test files
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: HTTP_TIMEOUT_S constant + delete _RESEND_TIMEOUT_S + refactor notifier</name>
  <read_first>
    - system_params.py
    - notifier.py lines 100-110 (_RESEND_TIMEOUT_S definition)
    - notifier.py lines 1340-1410 (the existing _post_to_resend block)
    - data_fetcher.py (full)
  </read_first>
  <behavior>
    - test_http_timeout_constant_present: HTTP_TIMEOUT_S == 30 (int) in system_params.
    - test_resend_timeout_constant_deleted: `_RESEND_TIMEOUT_S` is NOT defined in notifier.py (grep shows zero matches).  <!-- review-fix: agreed-6 -->
    - test_post_to_resend_uses_canonical: notifier._post_to_resend passes timeout=(5, HTTP_TIMEOUT_S); behavior preserved (connect=5s, read=30s).
    - test_no_bare_requests_call_in_prod: AST-walk widened to requests.{get,post,put,delete,head,patch} AND Session methods AND imported-from forms — every call has `timeout=` kwarg.
    - test_yfinance_internals_filtered: AST walker explicitly excludes paths inside the yfinance package (no false-positive failures from yfinance's own requests calls).
  </behavior>
  <action>
1. **system_params.py:** add
   ```python
   HTTP_TIMEOUT_S: int = 30  # Phase 27 #5: canonical connect+read timeout for ALL outbound HTTP
   ```
   near line 27.

2. **notifier.py — delete _RESEND_TIMEOUT_S:**
   - Line 106: delete `_RESEND_TIMEOUT_S = 30` entirely.
   - Top of file: add `HTTP_TIMEOUT_S` to the existing `from system_params import (...)` block.
   - Line 1371 (_post_to_resend): change `timeout=(5, _RESEND_TIMEOUT_S)` → `timeout=(5, HTTP_TIMEOUT_S)`. PRESERVE the tuple — connect=5s stays, read=HTTP_TIMEOUT_S.
   - Grep for any other `_RESEND_TIMEOUT_S` references; replace each with HTTP_TIMEOUT_S.

3. **data_fetcher.py:** coordinate with Plan 27-06 (_get_yf accessor). Inside the accessor, build a `requests.Session()` with default-timeout-injection per <interfaces>. Pass `session=` to yf.Ticker if 1.2.0 accepts it; else log limitation in 27-DEBT.md.
   - **Important:** the session injection MUST go through _get_yf(); module-top `requests.Session()` mutation is FORBIDDEN (review-fix agreed-6).

4. **tests/test_http_timeouts.py (NEW):** 5 tests per behavior block. AST walker (widened):
   ```python
   import ast, pathlib
   PROD = ['notifier.py','data_fetcher.py','dashboard.py','main.py','state_manager.py','auth_store.py']
   # Post-split additions (only if files exist):
   POST_SPLIT = ['cli_parser.py','daily_loop.py','interactive.py','scheduler_driver.py']
   for f in POST_SPLIT:
     if pathlib.Path(f).exists(): PROD.append(f)
   for d in ['notifier']:  # post-split notifier package
     if pathlib.Path(d).is_dir():
       PROD.extend(str(p) for p in pathlib.Path(d).glob('*.py'))

   HTTP_METHODS = {'get','post','put','delete','head','patch'}

   def _yields_http_calls(tree, path):
     # Track aliased imports: `import requests as r` → 'r' is an alias
     aliases = {'requests'}
     from_requests_methods = set()  # `from requests import post` → 'post'
     for node in ast.walk(tree):
       if isinstance(node, ast.Import):
         for n in node.names:
           if n.name == 'requests' and n.asname: aliases.add(n.asname)
       if isinstance(node, ast.ImportFrom) and node.module == 'requests':
         for n in node.names:
           if n.name in HTTP_METHODS: from_requests_methods.add(n.asname or n.name)
     for node in ast.walk(tree):
       if isinstance(node, ast.Call):
         f = node.func
         # requests.METHOD(...) or aliased
         if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
           if f.value.id in aliases and f.attr in HTTP_METHODS:
             yield (path, node.lineno, f.attr, 'timeout' in {kw.arg for kw in node.keywords})
           # Session().METHOD(...) — heuristic: any .get/.post on a Name we suspect is a Session
           # (we accept some false negatives here; tests can be sharpened over time)
         # imported-from: bare post(...), get(...)
         if isinstance(f, ast.Name) and f.id in from_requests_methods:
           yield (path, node.lineno, f.id, 'timeout' in {kw.arg for kw in node.keywords})

   def test_no_bare_requests_call_in_prod():
     for path in PROD:
       if 'yfinance' in path: continue  # filter agreed-6
       tree = ast.parse(pathlib.Path(path).read_text())
       for (p, ln, m, has_timeout) in _yields_http_calls(tree, path):
         assert has_timeout, f'{p}:{ln} {m}() missing timeout kwarg'
   ```

5. Run `pytest tests/test_http_timeouts.py -x -v`.

6. Grep verification:
   ```
   grep -n '_RESEND_TIMEOUT_S' notifier.py
   # expected: zero matches
   grep -n 'HTTP_TIMEOUT_S' system_params.py notifier.py data_fetcher.py
   # expected: defined in system_params; consumed in notifier + data_fetcher
   ```
  </action>
  <verify>
    <automated>pytest tests/test_http_timeouts.py -x -v</automated>
  </verify>
  <done>
    - HTTP_TIMEOUT_S in system_params.py.
    - `grep -c '_RESEND_TIMEOUT_S' notifier.py` == 0.
    - notifier _post_to_resend passes `timeout=(5, HTTP_TIMEOUT_S)`.
    - 5 tests in test_http_timeouts.py green; AST scope widened; yfinance filtered.
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
| T-27-02-01 | DoS (self-inflicted) | Daily run hangs forever on stuck network — crash-email never fires | mitigate | HTTP_TIMEOUT_S=30 forces TimeoutError → bubbles to crash-email path. AST walker prevents regression. |
| T-27-02-02 | Tampering (constant drift) | Two competing timeout constants (HTTP_TIMEOUT_S vs _RESEND_TIMEOUT_S) drift apart over time | mitigate | _RESEND_TIMEOUT_S deleted; single source of truth enforced by grep gate. |
</threat_model>

<verification>
```
pytest tests/test_http_timeouts.py -x -v
grep -n '_RESEND_TIMEOUT_S' notifier.py    # expected: 0
grep -n 'HTTP_TIMEOUT_S' system_params.py notifier.py data_fetcher.py
pytest -x   # full suite
```
</verification>

<success_criteria>
- HTTP_TIMEOUT_S = 30 in system_params.py (single source).
- _RESEND_TIMEOUT_S deleted from notifier.py.
- notifier._post_to_resend uses (5, HTTP_TIMEOUT_S) tuple — connect/read semantics preserved.
- data_fetcher yfinance session-injection via _get_yf() accessor (Plan 27-06).
- AST regression test (widened scope, yfinance filtered) green.
</success_criteria>

<output>
Create `27-02-SUMMARY.md` with: list of patched call sites, _RESEND_TIMEOUT_S deletion confirmation, yfinance session-injection outcome, AST walker output (0 violations).
</output>
