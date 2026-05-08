'''Phase 27 #5: HTTP timeout standardization regression tests.

Locks in:
  - HTTP_TIMEOUT_S = 30 lives ONCE in system_params.py.
  - notifier._RESEND_TIMEOUT_S is DELETED (no duplicate constant).
  - notifier._post_to_resend uses timeout=(5, HTTP_TIMEOUT_S).
  - Every requests.* / from-requests-import / urllib / httpx call in
    production code passes a `timeout=` kwarg.
  - yfinance internals are filtered (its own requests calls are not in
    scope; we control its session timeout via the _get_yf() accessor in
    Plan 27-06 + future session config).

Threat model: T-27-02-01 (DoS, hung-network) — without explicit timeout
the daily run blocks indefinitely and the crash-email path never fires.
T-27-02-02 (constant drift) — two competing timeout constants would
silently diverge over time; AST regression keeps the single source.
'''
import ast
import pathlib
import re

# Files that participate in production HTTP I/O. Pre-split + post-split
# (the post-split set is best-effort; the existence guard below skips
# files that haven't been created yet).
_PROD_BASE = [
  # CR-01 fix: notifier.py monolith deleted; package files picked up via
  # _POST_SPLIT_PACKAGES = ['notifier'] below.
  'data_fetcher.py',
  'dashboard.py',
  'main.py',
  'state_manager.py',
  'auth_store.py',
]
_POST_SPLIT_OPTIONAL = [
  'cli_parser.py',
  'daily_loop.py',
  'interactive.py',
  'scheduler_driver.py',
]
_POST_SPLIT_PACKAGES = [
  'notifier',  # post-split notifier package (transport.py, templates.py, ...)
]


def _resolve_prod_files() -> list[str]:
  '''Return the live set of production files to scan.

  Skips files that don't exist (post-split files only land in later plans).
  Skips files inside the yfinance package (review-fix agreed-6 filter).
  '''
  out: list[str] = []
  for f in _PROD_BASE:
    if pathlib.Path(f).is_file():
      out.append(f)
  for f in _POST_SPLIT_OPTIONAL:
    if pathlib.Path(f).is_file():
      out.append(f)
  for d in _POST_SPLIT_PACKAGES:
    p = pathlib.Path(d)
    if p.is_dir():
      out.extend(str(child) for child in p.glob('*.py'))
  # Filter: skip anything inside yfinance package (defensive — yfinance
  # is installed under .venv/, not in repo root, so this should never
  # match, but the filter is documented in the plan).
  return [f for f in out if 'yfinance' not in f]


_HTTP_METHODS = frozenset({'get', 'post', 'put', 'delete', 'head', 'patch'})


def _scan_http_calls(tree: ast.Module):
  '''Walk an AST and yield (lineno, qualifier, has_timeout) tuples for
  every outbound HTTP call we want to guard.

  Detects:
    - `requests.METHOD(...)` and aliased `r.METHOD(...)` after
      `import requests as r`.
    - bare `METHOD(...)` after `from requests import METHOD`.
    - `urllib.request.urlopen(...)`.
    - `httpx.METHOD(...)`.
  Heuristic: Session().METHOD(...) is hard to detect statically without
  a type system; we accept some false negatives there. The widened scope
  closes the agreed-6 review concern for the import-shape vectors that
  are common in this codebase.
  '''
  # First pass: collect import aliases.
  requests_aliases: set[str] = {'requests'}
  httpx_aliases: set[str] = {'httpx'}
  from_requests_methods: set[str] = set()
  for node in ast.walk(tree):
    if isinstance(node, ast.Import):
      for n in node.names:
        if n.name == 'requests' and n.asname:
          requests_aliases.add(n.asname)
        if n.name == 'httpx' and n.asname:
          httpx_aliases.add(n.asname)
    if isinstance(node, ast.ImportFrom) and node.module == 'requests':
      for n in node.names:
        if n.name in _HTTP_METHODS:
          from_requests_methods.add(n.asname or n.name)
  # Second pass: scan calls.
  for node in ast.walk(tree):
    if not isinstance(node, ast.Call):
      continue
    f = node.func
    has_timeout = 'timeout' in {kw.arg for kw in node.keywords}
    # requests.METHOD(...) / aliased / httpx.METHOD(...)
    if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
      base = f.value.id
      if base in requests_aliases and f.attr in _HTTP_METHODS:
        yield (node.lineno, f'{base}.{f.attr}', has_timeout)
      if base in httpx_aliases and f.attr in _HTTP_METHODS:
        yield (node.lineno, f'{base}.{f.attr}', has_timeout)
    # urllib.request.urlopen(module.module.attr)
    if (
      isinstance(f, ast.Attribute) and f.attr == 'urlopen'
      and isinstance(f.value, ast.Attribute) and f.value.attr == 'request'
      and isinstance(f.value.value, ast.Name) and f.value.value.id == 'urllib'
    ):
      yield (node.lineno, 'urllib.request.urlopen', has_timeout)
    # bare METHOD(...) after `from requests import METHOD`
    if isinstance(f, ast.Name) and f.id in from_requests_methods:
      yield (node.lineno, f'requests.{f.id}', has_timeout)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_http_timeout_constant_present():
  '''system_params.HTTP_TIMEOUT_S exists, is an int, equals 30.'''
  import system_params
  assert hasattr(system_params, 'HTTP_TIMEOUT_S'), (
    'HTTP_TIMEOUT_S missing from system_params (single source of truth)'
  )
  assert isinstance(system_params.HTTP_TIMEOUT_S, int)
  assert system_params.HTTP_TIMEOUT_S == 30


def test_resend_timeout_constant_deleted():
  '''notifier package must NOT define _RESEND_TIMEOUT_S anywhere (review-fix agreed-6).

  Single-source rule: HTTP_TIMEOUT_S in system_params.py is the only timeout
  constant. _RESEND_TIMEOUT_S used to live at notifier.py:106 — must be gone
  from every package file (CR-01 fix: notifier.py monolith deleted).
  '''
  pattern = re.compile(r'^\s*_RESEND_TIMEOUT_S\s*(:\s*\w+\s*)?=', re.MULTILINE)
  for p in pathlib.Path('notifier').glob('*.py'):
    src = p.read_text()
    matches = pattern.findall(src)
    assert not matches, (
      f'_RESEND_TIMEOUT_S still defined in {p} — '
      f'delete it and import HTTP_TIMEOUT_S from system_params instead. '
      f'Found {len(matches)} assignment(s).'
    )


def test_post_to_resend_uses_canonical_timeout():
  '''_post_to_resend default timeout_s parameter resolves to HTTP_TIMEOUT_S
  and the requests.post call passes timeout=(5, HTTP_TIMEOUT_S).

  The (5, HTTP_TIMEOUT_S) tuple is the connect/read split (Fix 2 from
  the original notifier review): 5s connect-phase + 30s read-phase. Both
  semantics must be preserved.
  '''
  import inspect
  import notifier
  import system_params
  # Default arg of _post_to_resend.timeout_s must equal HTTP_TIMEOUT_S.
  sig = inspect.signature(notifier._post_to_resend)
  default = sig.parameters['timeout_s'].default
  assert default == system_params.HTTP_TIMEOUT_S, (
    f'_post_to_resend.timeout_s default ({default}) must equal '
    f'system_params.HTTP_TIMEOUT_S ({system_params.HTTP_TIMEOUT_S})'
  )
  # Source-level: the requests.post call passes timeout=(5, X) where X
  # resolves to HTTP_TIMEOUT_S — either the literal name OR the parameter
  # `timeout_s` whose default is HTTP_TIMEOUT_S (caller override preserved
  # for crash-email path). Both shapes preserve the connect=5s / read=30s
  # split semantics required by the original notifier review Fix 2.
  # CR-01 fix: notifier.py monolith deleted; transport lives in
  # notifier/transport.py post-Plan 27-12 split.
  src = pathlib.Path('notifier/transport.py').read_text()
  assert re.search(r'timeout=\(5,\s*(HTTP_TIMEOUT_S|timeout_s)\)', src), (
    'notifier/transport.py must call requests.post(..., timeout=(5, HTTP_TIMEOUT_S)) '
    'or (5, timeout_s) where timeout_s defaults to HTTP_TIMEOUT_S '
    '— preserves connect=5s / read=HTTP_TIMEOUT_S split semantics.'
  )


def test_no_bare_requests_call_in_prod():
  '''Every requests/urllib/httpx call in production code passes a `timeout=` kwarg.

  Behavioral test (review-fix M1): asserts that timeout is present, NOT
  that it equals the literal string `HTTP_TIMEOUT_S`. Allows callers to
  pass tuples, computed values, or aliased names.
  '''
  violations: list[str] = []
  for path in _resolve_prod_files():
    src = pathlib.Path(path).read_text()
    tree = ast.parse(src, filename=path)
    for (lineno, qual, has_timeout) in _scan_http_calls(tree):
      if not has_timeout:
        violations.append(f'{path}:{lineno} {qual}() missing timeout= kwarg')
  assert not violations, (
    'HTTP calls without explicit timeout — review item #5 regression:\n'
    + '\n'.join(violations)
  )


def test_yfinance_internals_filtered():
  '''The AST walker explicitly filters yfinance package paths.

  Documents the agreed-6 filter behavior: yfinance's own internal requests
  calls (inside its history(), download(), etc.) are not in scope for
  this regression. We control yfinance's outbound timeout via the session
  injection through the Plan 27-06 _get_yf() accessor.
  '''
  files = _resolve_prod_files()
  # No file in the resolved set should live inside the yfinance package.
  for f in files:
    assert 'yfinance' not in f, (
      f'PROD scan unexpectedly included yfinance internal path: {f}'
    )
  # The resolved set must be non-empty (otherwise the filter could be
  # silently vacuous).
  assert files, 'No production files resolved — _resolve_prod_files() is broken.'
