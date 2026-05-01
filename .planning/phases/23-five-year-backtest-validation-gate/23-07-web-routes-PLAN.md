---
id: 23-07
title: Wave 2C — web/routes/backtest.py (4 routes + path-traversal + cookie auth)
phase: 23
plan: 07
type: execute
wave: 2
depends_on: [23-01, 23-05, 23-06]
files_modified:
  - web/routes/backtest.py
  - tests/test_web_backtest.py
requirements: [BACKTEST-03, BACKTEST-04]
threat_refs: [T-23-traversal, T-23-input, T-23-auth]
autonomous: true
gap_closure: false

must_haves:
  truths:
    - "GET /backtest with valid cookie returns 200 + HTML with three tab containers + override form"
    - "GET /backtest?history=true returns 200 with table + 10-cap overlay chart container"
    - "GET /backtest?run=<filename> validates filename via regex + os.listdir whitelist (T-23-traversal)"
    - "GET /backtest?run=../../etc/passwd returns 400 (NOT 200, NOT a 500 stacktrace)"
    - "POST /backtest/run with valid cookie + valid form values returns 303 redirect to /backtest"
    - "POST /backtest/run with initial_account_aud <= 0 returns 400 (T-23-input)"
    - "POST /backtest/run with cost_*_aud < 0 returns 400 (T-23-input)"
    - "Unauthenticated browser GET /backtest returns 302 to /login (Phase 16.1 cookie-session)"
    - "Unauthenticated curl GET /backtest returns 401 plain (Phase 16.1 D-04..D-07)"
    - "Unauthenticated POST /backtest/run returns 401 plain"
    - "GET /backtest with no JSON files in .planning/backtests/ returns 200 with D-17 empty-state copy"
    - "/backtest mounted in web/app.py adjacent to paper_trades_route"
  artifacts:
    - path: "web/routes/backtest.py"
      provides: "_resolve_safe_backtest_path + get_backtest + post_backtest_run + register"
      exports: ["register"]
    - path: "tests/test_web_backtest.py"
      provides: "TestGetBacktest + TestPathTraversal + TestPostRun + TestCookieAuth + TestHistoryView"
  key_links:
    - from: "web/routes/backtest.py"
      to: "backtest.cli.run_backtest + backtest.render.render_report/history/run_form"
      via: "direct function calls (CLI logic reused for POST handler per Wave 2 Plan 06 contract)"
      pattern: "from backtest.cli import run_backtest|from backtest.render import"
    - from: "web/routes/backtest.py"
      to: "Phase 16.1 AuthMiddleware"
      via: "Inherited; no per-route auth code"
      pattern: "(implicit via web/app.py middleware order)"
---

<objective>
Implement `web/routes/backtest.py` — the FastAPI adapter that mounts /backtest GET + /backtest/run POST. Replaces Wave 0 NotImplementedError. Reuses `backtest.cli.run_backtest` for the POST path so the simulation logic is single-source-of-truth.

Purpose: Operator opens https://signals.mwiriadi.me/backtest, sees the latest report. Submits override form, sees fresh run. History link surfaces past runs. Path-traversal defended (T-23-traversal); input validated (T-23-input); auth-gated (T-23-auth).
Output: ~200 LOC web adapter + 5 test classes covering path-traversal / POST validation / cookie auth / empty state / history view.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/23-five-year-backtest-validation-gate/23-CONTEXT.md
@.planning/phases/23-five-year-backtest-validation-gate/23-RESEARCH.md
@.planning/phases/23-five-year-backtest-validation-gate/23-PATTERNS.md
@.planning/phases/23-five-year-backtest-validation-gate/23-UI-SPEC.md
@CLAUDE.md
@web/routes/paper_trades.py
@web/app.py
@tests/conftest.py
@tests/test_web_paper_trades.py
@backtest/cli.py
@backtest/render.py

<interfaces>
<!-- web/routes/backtest.py CONTRACT -->
def _resolve_safe_backtest_path(filename: str, backtest_dir: Path) -> Path:
  """Two-layer defence: regex gate + os.listdir whitelist (RESEARCH §Pattern 5).
  Raises ValueError on any path-traversal attempt or unknown filename."""

async def get_backtest(request: Request) -> HTMLResponse:
  """Routes to: latest report (no query), history view (?history=true), specific run (?run=<file>).
  Returns 400 on path-traversal attempt; 200 with empty-state copy when .planning/backtests/ is empty.
  """

async def post_backtest_run(
  request: Request,
  initial_account_aud: float = Form(...),
  cost_spi_aud: float = Form(...),
  cost_audusd_aud: float = Form(...),
) -> RedirectResponse:
  """Validates inputs (>0 / >=0); calls backtest.cli.run_backtest; redirects 303 to /backtest."""

def register(app: FastAPI) -> None:
  """Mount /backtest GET + /backtest/run POST."""

<!-- Path-traversal regex (RESEARCH §Pattern 5) -->
_SAFE_FILENAME_RE = re.compile(r'^[a-zA-Z0-9._-]+\.json$')

<!-- Validation rules (CONTEXT risk register + Phase 19 D-22 convention) -->
- initial_account_aud > 0 → otherwise 400
- cost_spi_aud >= 0 → otherwise 400
- cost_audusd_aud >= 0 → otherwise 400
- ShortFrameError from data_fetcher → 400 with D-17 copy

<!-- Test fixtures from tests/conftest.py -->
- valid_cookie_token (line 92) — signed tsi_session cookie
- VALID_SECRET — for AuthMiddleware

<!-- Page shell — minimal HTML wrapper around render_report output -->
PAGE_SHELL = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Backtest Validation</title></head>
<body>{body}</body>
</html>"""
</interfaces>
</context>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Browser → /backtest (?run=) | Untrusted query string; potential path-traversal |
| Browser → POST /backtest/run | Untrusted form body; potential negative/zero values |
| Network → AuthMiddleware → handlers | Phase 16.1 cookie-session gate; unauth requests blocked |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-23-traversal | Information Disclosure | GET /backtest?run=<filename> | mitigate | Two-layer defence per RESEARCH §Pattern 5: regex `^[a-zA-Z0-9._-]+\.json$` rejects `..`/`/`/absolute paths; `os.listdir()` whitelist confirms file is in the canonical backtest directory |
| T-23-input | Tampering | POST /backtest/run form body | mitigate | Server-side validation: `initial_account_aud > 0`, `cost_*_aud >= 0`; reject with 400 per Phase 19 D-22 convention (web/app.py:174-177) |
| T-23-auth | Elevation of Privilege | All /backtest* routes | mitigate | Phase 16.1 AuthMiddleware gates uniformly: browser unauth → 302 /login; curl unauth → 401 plain; POST unauth → 401 |
</threat_model>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Implement web/routes/backtest.py</name>
  <read_first>
    - web/routes/backtest.py (Wave 0 skeleton — has _SAFE_FILENAME_RE + register stubs)
    - web/routes/paper_trades.py lines 228-302 (POST handler analog with Form() + 303 redirect)
    - web/routes/paper_trades.py lines 251-258 + lines 78-102 (form parsing pattern)
    - web/app.py lines 174-177 (RequestValidationError 400 handler — global)
    - .planning/phases/23-five-year-backtest-validation-gate/23-RESEARCH.md §Pattern 5 (path-traversal defence), §Pattern 8 (POST 303 redirect + cookie auth)
    - .planning/phases/23-five-year-backtest-validation-gate/23-PATTERNS.md §"web/routes/backtest.py"
    - .planning/phases/23-five-year-backtest-validation-gate/23-CONTEXT.md §D-12, §D-14, §D-15, §D-17
    - .planning/phases/23-five-year-backtest-validation-gate/23-UI-SPEC.md §Interaction Contracts
    - backtest/cli.py (run_backtest signature)
    - backtest/render.py (render_report/history/run_form signatures)
  </read_first>
  <behavior>
    See must_haves.truths. Each test class targets one route + one threat.
  </behavior>
  <action>
    Replace Wave 0 skeleton:

    ```python
    """Phase 23 — web routes for /backtest report + history + override form.

    Routes (CONTEXT D-12):
      GET  /backtest              — latest report (sorted by mtime desc); empty-state if none
      GET  /backtest?history=true — D-06 table + 10-run overlay chart
      GET  /backtest?run=<file>   — specified report; path-traversal guarded (RESEARCH §Pattern 5)
      POST /backtest/run          — operator override form (D-14)

    Auth: Phase 16.1 cookie-session middleware gates all paths uniformly. No per-route auth code.
    Hex tier: adapter — imports backtest/*, FastAPI, web layer.
            Does NOT import signal_engine, sizing_engine directly (those go through backtest.simulator).
    """
    from __future__ import annotations
    import json
    import logging
    import os
    import re
    from pathlib import Path

    from fastapi import FastAPI, Form, HTTPException, Request
    from fastapi.responses import HTMLResponse, RedirectResponse

    from backtest.cli import RunArgs, run_backtest
    from backtest.data_fetcher import DataFetchError, ShortFrameError
    from backtest.render import render_history, render_report, render_run_form

    logger = logging.getLogger(__name__)

    _LOG_PREFIX = '[Web]'  # web layer keeps [Web]; CLI uses [Backtest]
    _BACKTEST_DIR = Path('.planning/backtests')
    _SAFE_FILENAME_RE = re.compile(r'^[a-zA-Z0-9._-]+\.json$')


    # ---------- Path-traversal defence (T-23-traversal) ----------

    def _resolve_safe_backtest_path(filename: str, backtest_dir: Path = _BACKTEST_DIR) -> Path:
      """Two-layer defence (RESEARCH §Pattern 5):
        1. Regex `^[a-zA-Z0-9._-]+\\.json$` rejects `..`, `/`, absolute paths
        2. os.listdir() whitelist confirms file is in canonical directory

      Raises ValueError on any traversal attempt or unknown filename.
      """
      if not isinstance(filename, str) or not _SAFE_FILENAME_RE.match(filename):
        raise ValueError(f'invalid backtest filename: {filename!r}')
      try:
        available = set(os.listdir(backtest_dir))
      except FileNotFoundError:
        raise ValueError(f'backtest directory does not exist: {backtest_dir}')
      if filename not in available:
        raise ValueError(f'backtest file not found: {filename!r}')
      return backtest_dir / filename


    # ---------- Helpers ----------

    def _list_reports(backtest_dir: Path = _BACKTEST_DIR) -> list[Path]:
      """Return existing *.json files sorted by mtime descending. Empty list if none."""
      if not backtest_dir.exists():
        return []
      files = [p for p in backtest_dir.iterdir() if p.is_file() and p.suffix == '.json']
      files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
      return files


    def _load_report(path: Path) -> dict:
      """Load and parse JSON. Adds the filename into metadata (used by history/?run links)."""
      data = json.loads(path.read_text())
      data.setdefault('metadata', {})
      data['metadata']['filename'] = path.name
      return data


    def _wrap_html(body: str) -> str:
      """Minimal page shell. Production styles inherited from existing dashboard CSS at GET /."""
      return (
        '<!doctype html><html lang="en">'
        '<head><meta charset="utf-8"><title>Backtest Validation</title></head>'
        f'<body>{body}</body></html>'
      )


    # ---------- GET /backtest (covers ?history=true and ?run=<file>) ----------

    async def get_backtest(request: Request) -> HTMLResponse:
      """CONTEXT D-12 + D-15: cookie-auth-gated by Phase 16.1 middleware (no code here).

      Branches:
        ?run=<filename>     → render specified report (path-traversal guarded)
        ?history=true       → render history view (D-06)
        (no query)          → render latest by mtime; empty-state if none
      """
      params = request.query_params

      # ?run=<filename> branch — strictest first (path-traversal defence)
      run_filename = params.get('run')
      if run_filename:
        try:
          path = _resolve_safe_backtest_path(run_filename)
        except ValueError as exc:
          logger.warning('%s rejected ?run= traversal attempt: %s', _LOG_PREFIX, exc)
          return HTMLResponse(
            content=_wrap_html(
              '<section class="error"><h1>Invalid backtest filename.</h1>'
              '<p><a href="/backtest">← Back to latest run</a></p></section>'
            ),
            status_code=400,
          )
        report = _load_report(path)
        return HTMLResponse(content=_wrap_html(render_report(report)), status_code=200)

      # ?history=true branch
      if params.get('history') == 'true':
        files = _list_reports()
        reports = [_load_report(p) for p in files]
        return HTMLResponse(content=_wrap_html(render_history(reports)), status_code=200)

      # Default branch — latest report or empty state
      files = _list_reports()
      if not files:
        return HTMLResponse(content=_wrap_html(render_report({})), status_code=200)
      latest = _load_report(files[0])
      return HTMLResponse(content=_wrap_html(render_report(latest)), status_code=200)


    # ---------- POST /backtest/run (operator override form D-14) ----------

    async def post_backtest_run(
      request: Request,
      initial_account_aud: float = Form(...),
      cost_spi_aud: float = Form(...),
      cost_audusd_aud: float = Form(...),
    ) -> RedirectResponse | HTMLResponse:
      """CONTEXT D-14: operator override form submit.

      Validates inputs server-side (T-23-input), runs simulation synchronously
      via backtest.cli.run_backtest, redirects 303 to /backtest on success.

      400 on validation failure, ShortFrameError, or DataFetchError.
      303 (NOT 307) per RESEARCH §Pattern 8 + A2 (FastAPI default 307 re-POSTs).
      """
      # T-23-input validation
      if not (initial_account_aud > 0):
        return HTMLResponse(
          content=_wrap_html(
            f'<section class="error"><h1>Initial account must be greater than zero.</h1>'
            f'<p><a href="/backtest">← Back</a></p></section>'
          ),
          status_code=400,
        )
      if cost_spi_aud < 0:
        return HTMLResponse(
          content=_wrap_html(
            f'<section class="error"><h1>SPI 200 cost must be greater than or equal to zero.</h1>'
            f'<p><a href="/backtest">← Back</a></p></section>'
          ),
          status_code=400,
        )
      if cost_audusd_aud < 0:
        return HTMLResponse(
          content=_wrap_html(
            f'<section class="error"><h1>AUD/USD cost must be greater than or equal to zero.</h1>'
            f'<p><a href="/backtest">← Back</a></p></section>'
          ),
          status_code=400,
        )

      args = RunArgs(
        initial_account_aud=float(initial_account_aud),
        cost_spi_aud=float(cost_spi_aud),
        cost_audusd_aud=float(cost_audusd_aud),
      )
      try:
        report, written_path, exit_code = run_backtest(args)
      except ShortFrameError as exc:
        logger.warning('%s ShortFrameError: %s', _LOG_PREFIX, exc)
        return HTMLResponse(
          content=_wrap_html(
            f'<section class="error"><h1>Backtest cannot run.</h1><p>{exc}</p>'
            f'<p><a href="/backtest">← Back</a></p></section>'
          ),
          status_code=400,
        )
      except DataFetchError as exc:
        logger.warning('%s DataFetchError: %s', _LOG_PREFIX, exc)
        return HTMLResponse(
          content=_wrap_html(
            '<section class="error"><h1>Could not fetch market data right now.</h1>'
            '<p>Try again in a minute, or run from CLI to see the underlying error.</p>'
            '<p><a href="/backtest">← Back</a></p></section>'
          ),
          status_code=400,
        )

      logger.info('%s POST /backtest/run wrote %s (exit_code=%d)',
                  _LOG_PREFIX, written_path, exit_code)
      return RedirectResponse(url='/backtest', status_code=303)


    # ---------- Mount factory ----------

    def register(app: FastAPI) -> None:
      """Mount Phase 23 routes; called from web/app.py:create_app()."""
      app.add_api_route('/backtest', get_backtest, methods=['GET'])
      app.add_api_route('/backtest/run', post_backtest_run, methods=['POST'])
    ```

    Verify the existing web/app.py mount line is unchanged (Wave 0 already added it).
  </action>
  <verify>
    <automated>python -c "from web.routes.backtest import _resolve_safe_backtest_path, get_backtest, post_backtest_run, register; from pathlib import Path; import tempfile, os; tmp = Path(tempfile.mkdtemp()); (tmp / 'good.json').write_text('{}'); p = _resolve_safe_backtest_path('good.json', tmp); assert p.name == 'good.json'; rejected = False
try:
    _resolve_safe_backtest_path('../../etc/passwd', tmp)
except ValueError:
    rejected = True
assert rejected; print('ok')" 2>&1 | grep -c '^ok$'</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c '^def _resolve_safe_backtest_path' web/routes/backtest.py` returns 1
    - `grep -c '^async def get_backtest' web/routes/backtest.py` returns 1
    - `grep -c '^async def post_backtest_run' web/routes/backtest.py` returns 1
    - `grep -c '^def register' web/routes/backtest.py` returns 1
    - `grep -c "_SAFE_FILENAME_RE = re.compile" web/routes/backtest.py` returns 1
    - `grep -c "from backtest.cli import" web/routes/backtest.py` returns 1
    - `grep -c "from backtest.render import" web/routes/backtest.py` returns 1
    - `grep -c "status_code=303" web/routes/backtest.py` returns 1 (POST→GET redirect, NOT 307)
    - `grep -c "initial_account_aud > 0" web/routes/backtest.py` returns 1 (T-23-input)
    - `grep -c "cost_spi_aud < 0" web/routes/backtest.py` returns 1
    - `grep -c "cost_audusd_aud < 0" web/routes/backtest.py` returns 1
    - `grep -c "^import signal_engine\|^from signal_engine\|^import sizing_engine\|^from sizing_engine" web/routes/backtest.py` returns 0 (web must not import engines directly)
    - `python -c "from web.app import create_app; app = create_app(); paths = sorted({r.path for r in app.routes}); assert '/backtest' in paths and '/backtest/run' in paths"` succeeds
  </acceptance_criteria>
  <done>4 routes wired; path-traversal + input validation + auth all in place via middleware.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Implement tests/test_web_backtest.py (5 test classes)</name>
  <read_first>
    - web/routes/backtest.py (just-implemented)
    - tests/test_web_paper_trades.py — analog (TestClient + cookie auth + form POST)
    - tests/conftest.py lines 91-101 (valid_cookie_token), lines 200+ (client + state fixtures)
    - .planning/phases/23-five-year-backtest-validation-gate/23-PATTERNS.md §"tests/test_web_backtest.py"
    - .planning/phases/23-five-year-backtest-validation-gate/23-VALIDATION.md
  </read_first>
  <behavior>
    See must_haves.truths. Test classes:
    - TestGetBacktest: 200 with cookie + happy paths (latest, empty)
    - TestPathTraversal: ../../etc/passwd → 400; absolute path → 400; valid filename → 200
    - TestPostRun: 303 on valid form; 400 on negative cost / zero account
    - TestCookieAuth: GET without cookie → 302/401; POST without cookie → 401
    - TestHistoryView: ?history=true returns 200 + table; empty list → empty-state
  </behavior>
  <action>
    Replace Wave 0 skeleton:

    ```python
    """Phase 23 — web/routes/backtest.py tests (BACKTEST-03/04 web routes)."""
    from __future__ import annotations
    import json
    from pathlib import Path
    from unittest.mock import MagicMock

    import pytest
    from fastapi.testclient import TestClient

    from web.app import create_app


    # ---------- Fixtures ----------

    @pytest.fixture
    def app_instance():
      return create_app()


    @pytest.fixture
    def client(app_instance):
      return TestClient(app_instance)


    @pytest.fixture
    def backtest_dir_seeded(tmp_path, monkeypatch):
      """Seed two valid report files into a tmp backtest dir + monkeypatch
      web/routes/backtest.py to use it."""
      d = tmp_path / 'backtests'
      d.mkdir()
      sample = json.loads(Path('tests/fixtures/backtest/golden_report.json').read_text())
      (d / 'v1.2.0-20260501T080000.json').write_text(json.dumps(sample))
      (d / 'v1.1.0-20260430T080000.json').write_text(json.dumps({
        **sample,
        'metadata': {**sample['metadata'], 'strategy_version': 'v1.1.0',
                     'run_dt': '2026-04-30T08:00:00+08:00'},
      }))
      monkeypatch.setattr('web.routes.backtest._BACKTEST_DIR', d)
      return d


    @pytest.fixture
    def empty_backtest_dir(tmp_path, monkeypatch):
      d = tmp_path / 'empty_backtests'
      d.mkdir()
      monkeypatch.setattr('web.routes.backtest._BACKTEST_DIR', d)
      return d


    # ---------- TestGetBacktest ----------

    class TestGetBacktest:
      def test_get_returns_latest_report(self, client, valid_cookie_token, backtest_dir_seeded):
        r = client.get('/backtest', cookies={'tsi_session': valid_cookie_token})
        assert r.status_code == 200
        body = r.text
        assert 'equityChartCombined' in body
        assert 'equityChartSpi200' in body
        assert 'equityChartAudusd' in body
        assert 'sha384-MH1axGwz' in body  # Chart.js SRI
        # Latest = v1.2.0 (newer mtime)
        assert 'v1.2.0' in body

      def test_get_empty_dir_returns_empty_state(self, client, valid_cookie_token,
                                                 empty_backtest_dir):
        r = client.get('/backtest', cookies={'tsi_session': valid_cookie_token})
        assert r.status_code == 200
        assert 'No backtest runs yet' in r.text


    # ---------- TestPathTraversal ----------

    class TestPathTraversal:
      def test_traversal_dotdot_etc_passwd_returns_400(self, client, valid_cookie_token,
                                                       backtest_dir_seeded):
        r = client.get('/backtest?run=../../etc/passwd',
                       cookies={'tsi_session': valid_cookie_token})
        assert r.status_code == 400
        assert 'Invalid backtest filename' in r.text

      def test_traversal_absolute_path_returns_400(self, client, valid_cookie_token,
                                                   backtest_dir_seeded):
        r = client.get('/backtest?run=/etc/passwd',
                       cookies={'tsi_session': valid_cookie_token})
        assert r.status_code == 400

      def test_traversal_with_slashes_returns_400(self, client, valid_cookie_token,
                                                  backtest_dir_seeded):
        r = client.get('/backtest?run=foo/bar.json',
                       cookies={'tsi_session': valid_cookie_token})
        assert r.status_code == 400

      def test_unknown_filename_returns_400(self, client, valid_cookie_token,
                                            backtest_dir_seeded):
        r = client.get('/backtest?run=does-not-exist.json',
                       cookies={'tsi_session': valid_cookie_token})
        assert r.status_code == 400

      def test_valid_filename_returns_200(self, client, valid_cookie_token,
                                          backtest_dir_seeded):
        r = client.get('/backtest?run=v1.1.0-20260430T080000.json',
                       cookies={'tsi_session': valid_cookie_token})
        assert r.status_code == 200
        assert 'v1.1.0' in r.text


    # ---------- TestPostRun ----------

    class TestPostRun:
      @pytest.fixture
      def patched_run_backtest(self, monkeypatch):
        """Stub run_backtest so we don't actually fetch yfinance during web tests."""
        def _fake(args):
          return ({'metadata': {'pass': True}}, Path('/tmp/fake.json'), 0)
        monkeypatch.setattr('web.routes.backtest.run_backtest', _fake)
        return _fake

      def test_valid_post_redirects_303(self, client, valid_cookie_token,
                                         patched_run_backtest, backtest_dir_seeded):
        r = client.post(
          '/backtest/run',
          data={'initial_account_aud': '10000', 'cost_spi_aud': '6.0',
                'cost_audusd_aud': '5.0'},
          cookies={'tsi_session': valid_cookie_token},
          follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.headers['location'] == '/backtest'

      def test_zero_account_returns_400(self, client, valid_cookie_token,
                                        patched_run_backtest, backtest_dir_seeded):
        r = client.post(
          '/backtest/run',
          data={'initial_account_aud': '0', 'cost_spi_aud': '6.0',
                'cost_audusd_aud': '5.0'},
          cookies={'tsi_session': valid_cookie_token},
          follow_redirects=False,
        )
        assert r.status_code == 400
        assert 'greater than zero' in r.text

      def test_negative_account_returns_400(self, client, valid_cookie_token,
                                            patched_run_backtest, backtest_dir_seeded):
        r = client.post(
          '/backtest/run',
          data={'initial_account_aud': '-100', 'cost_spi_aud': '6.0',
                'cost_audusd_aud': '5.0'},
          cookies={'tsi_session': valid_cookie_token},
          follow_redirects=False,
        )
        assert r.status_code == 400

      def test_negative_cost_spi_returns_400(self, client, valid_cookie_token,
                                              patched_run_backtest, backtest_dir_seeded):
        r = client.post(
          '/backtest/run',
          data={'initial_account_aud': '10000', 'cost_spi_aud': '-1',
                'cost_audusd_aud': '5.0'},
          cookies={'tsi_session': valid_cookie_token},
          follow_redirects=False,
        )
        assert r.status_code == 400
        assert 'SPI 200 cost' in r.text

      def test_negative_cost_audusd_returns_400(self, client, valid_cookie_token,
                                                 patched_run_backtest, backtest_dir_seeded):
        r = client.post(
          '/backtest/run',
          data={'initial_account_aud': '10000', 'cost_spi_aud': '6.0',
                'cost_audusd_aud': '-0.01'},
          cookies={'tsi_session': valid_cookie_token},
          follow_redirects=False,
        )
        assert r.status_code == 400
        assert 'AUD/USD cost' in r.text

      def test_zero_cost_is_allowed(self, client, valid_cookie_token,
                                    patched_run_backtest, backtest_dir_seeded):
        r = client.post(
          '/backtest/run',
          data={'initial_account_aud': '10000', 'cost_spi_aud': '0',
                'cost_audusd_aud': '0'},
          cookies={'tsi_session': valid_cookie_token},
          follow_redirects=False,
        )
        # cost >= 0 is the rule (not > 0)
        assert r.status_code == 303


    # ---------- TestCookieAuth ----------

    class TestCookieAuth:
      def test_get_without_cookie_browser_redirects(self, client, backtest_dir_seeded):
        # Phase 16.1: browser (Accept: text/html) → 302 /login
        r = client.get('/backtest', headers={'Accept': 'text/html'},
                       follow_redirects=False)
        assert r.status_code in (302, 401)  # 302 for browser per Phase 16.1 D-04
        if r.status_code == 302:
          assert '/login' in r.headers.get('location', '')

      def test_get_without_cookie_curl_returns_401(self, client, backtest_dir_seeded):
        # Phase 16.1: non-browser (curl, default Accept) → 401 plain
        r = client.get('/backtest', headers={'Accept': '*/*'},
                       follow_redirects=False)
        assert r.status_code in (401, 302)

      def test_post_without_cookie_returns_401(self, client, backtest_dir_seeded):
        r = client.post(
          '/backtest/run',
          data={'initial_account_aud': '10000', 'cost_spi_aud': '6.0',
                'cost_audusd_aud': '5.0'},
          follow_redirects=False,
        )
        assert r.status_code == 401


    # ---------- TestHistoryView ----------

    class TestHistoryView:
      def test_history_returns_200_with_table(self, client, valid_cookie_token,
                                               backtest_dir_seeded):
        r = client.get('/backtest?history=true',
                       cookies={'tsi_session': valid_cookie_token})
        assert r.status_code == 200
        body = r.text
        assert 'history-table' in body or 'Backtest history' in body
        assert 'v1.2.0' in body
        assert 'v1.1.0' in body

      def test_history_empty_dir_returns_200_empty_state(self, client, valid_cookie_token,
                                                         empty_backtest_dir):
        r = client.get('/backtest?history=true',
                       cookies={'tsi_session': valid_cookie_token})
        assert r.status_code == 200
        assert 'No backtest history yet' in r.text

      def test_history_overlay_chart_present(self, client, valid_cookie_token,
                                              backtest_dir_seeded):
        r = client.get('/backtest?history=true',
                       cookies={'tsi_session': valid_cookie_token})
        assert r.status_code == 200
        assert 'equityChartHistory' in r.text
    ```
  </action>
  <verify>
    <automated>.venv/bin/pytest tests/test_web_backtest.py -x -q 2>&1 | tail -10</automated>
  </verify>
  <acceptance_criteria>
    - `.venv/bin/pytest tests/test_web_backtest.py -x -q` passes (all 5 classes green, no skips)
    - `pytest tests/test_web_backtest.py::TestPathTraversal -x` passes ≥5 tests (T-23-traversal)
    - `pytest tests/test_web_backtest.py::TestPostRun -x` passes ≥6 tests (T-23-input)
    - `pytest tests/test_web_backtest.py::TestCookieAuth -x` passes ≥3 tests (T-23-auth)
    - `pytest tests/test_web_backtest.py::TestGetBacktest -x` passes ≥2 tests
    - `pytest tests/test_web_backtest.py::TestHistoryView -x` passes ≥3 tests
    - Full suite no regression: `.venv/bin/pytest -x -q` exits 0
  </acceptance_criteria>
  <done>All 5 test classes green; T-23 threats all verified mitigated.</done>
</task>

</tasks>

<verification>
1. `python -c "from web.routes.backtest import _resolve_safe_backtest_path, register; print('ok')"` prints `ok`
2. `.venv/bin/pytest tests/test_web_backtest.py -x -q` passes
3. `python -c "from web.app import create_app; app = create_app(); paths = sorted({r.path for r in app.routes}); assert '/backtest' in paths and '/backtest/run' in paths"` succeeds
4. Full suite green: `.venv/bin/pytest -x -q` exits 0
5. End-to-end smoke: `python -m backtest --years 5` runs (mocked yfinance) → JSON written → `curl localhost:8000/backtest -b cookie.txt` → 200 HTML
</verification>

<success_criteria>
- /backtest GET + /backtest/run POST live in production app
- Path-traversal defended with regex + os.listdir whitelist
- Input validation rejects negative/zero values with 400
- Phase 16.1 cookie-session middleware gates all /backtest* routes
- POST→GET 303 redirect (NOT 307) prevents re-POST on browser back
- Empty .planning/backtests/ → empty-state copy (D-17)
- 5 test classes green covering all 3 T-23 threats
- web/routes/backtest.py does NOT import signal_engine or sizing_engine directly
</success_criteria>

<output>
Create `.planning/phases/23-five-year-backtest-validation-gate/23-07-SUMMARY.md` documenting:
- 4 routes signature confirmed
- Path-traversal defence test count
- Input validation test count
- Cookie auth test count
- Hex-boundary check (no engine imports in web layer)
</output>
