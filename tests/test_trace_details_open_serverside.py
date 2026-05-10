'''Phase 29 Plan 12 — UAT-17-2 server-side <details open> integration tests.

Tests that the server-side `{{TRACE_OPEN_<KEY>}}` placeholder substitution
fires correctly on the dashboard routes so iOS Safari reload preserves trace
panel open state without client-side JS dependency.

Two test layers:
  1. TestTraceDetailsOpenServerSide — direct _substitute() path via the
     root dashboard route (GET /), using a synthetic dashboard.html containing
     the {{TRACE_OPEN_SPI200}} placeholder. Mirrors the TestTraceCookieAllowlist
     pattern from test_web_dashboard.py.
  2. TestTraceDetailsOpenMarketScoped — market-scoped route
     (GET /markets/SPI200/signals), which uses render_dashboard_as_str +
     _substitute() via _serve_market_scoped_page. Covers the iOS Safari
     reload path: state renders with placeholder; _substitute reads
     tsi_trace_open cookie → emits <details ... open> in the response.
'''
import re
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Auth constants — mirrors test_web_dashboard.py mirror convention.
VALID_SECRET = 'a' * 32
AUTH_HEADER_NAME = 'X-Trading-Signals-Auth'


def _request_with_cookies(client, method, url, **kwargs):
    '''Helper to inject cookies into TestClient request headers.'''
    cookies = kwargs.pop('cookies', None)
    if cookies:
        headers = dict(kwargs.pop('headers', {}) or {})
        cookie_parts = [f'{name}={value}' for name, value in cookies.items()]
        existing = headers.get('cookie') or headers.get('Cookie')
        if existing:
            cookie_parts.insert(0, existing)
        headers['cookie'] = '; '.join(cookie_parts)
        kwargs['headers'] = headers
    return client.request(method, url, **kwargs)


def _make_trace_html(path: Path) -> None:
    '''Write a synthetic dashboard.html with SPI200 and AUDUSD trace placeholders.'''
    path.write_text(
        '<html><body>'
        '<details class="trace-disclosure" data-instrument="SPI200"{{TRACE_OPEN_SPI200}}>'
        'SPI200 content</details>'
        '<details class="trace-disclosure" data-instrument="AUDUSD"{{TRACE_OPEN_AUDUSD}}>'
        'AUDUSD content</details>'
        '</body></html>',
        encoding='utf-8',
    )


def _make_client(monkeypatch, tmp_path):
    '''Shared setup: chdir tmp_path, set env vars, return TestClient.'''
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('WEB_AUTH_SECRET', VALID_SECRET)
    monkeypatch.setenv('WEB_AUTH_USERNAME', 'marc')
    import state_manager
    monkeypatch.setattr(
        state_manager, 'load_state',
        lambda *_a, **_kw: {'schema_version': 1, 'last_run': '2026-04-25'},
    )
    sys.modules.pop('web.app', None)
    from web.app import create_app
    return TestClient(create_app())


class TestTraceDetailsOpenServerSide:
    '''Phase 29 Plan 12 UAT-17-2: server-side <details open> from cookie.

    All four tests exercise the _substitute() path via GET / with a synthetic
    dashboard.html containing {{TRACE_OPEN_SPI200}} and {{TRACE_OPEN_AUDUSD}}
    placeholders. The server must substitute ' open' or '' based on the
    tsi_trace_open cookie value — iOS Safari reload depends on this being
    server-rendered, not JS-injected.
    '''

    def test_details_open_when_cookie_includes_instrument(
        self, monkeypatch, tmp_path,
    ):
        '''Cookie tsi_trace_open=SPI200 → <details ... open> for SPI200,
        NOT for AUDUSD. No literal {{TRACE_OPEN_SPI200}} placeholder in response.

        UAT-17-2 root assertion: server renders open attribute from cookie so
        iOS Safari reload preserves panel state without client-side JS.
        '''
        client = _make_client(monkeypatch, tmp_path)
        _make_trace_html(tmp_path / 'dashboard.html')
        resp = _request_with_cookies(
            client, 'GET', '/',
            headers={AUTH_HEADER_NAME: VALID_SECRET},
            cookies={'tsi_trace_open': 'SPI200'},
        )
        assert resp.status_code == 200, f'Unexpected status {resp.status_code}'
        # SPI200 in cookie → <details ... open>
        assert re.search(
            r'<details[^>]+data-instrument="SPI200"[^>]*\bopen\b',
            resp.text,
        ), 'SPI200 in cookie → <details open> must render (server-side substitution)'
        # AUDUSD NOT in cookie → no open attribute
        assert not re.search(
            r'<details[^>]+data-instrument="AUDUSD"[^>]*\bopen\b',
            resp.text,
        ), 'AUDUSD not in cookie → must NOT be open'
        # No placeholder leak
        assert '{{TRACE_OPEN_SPI200}}' not in resp.text, (
            'Server must substitute placeholder — no literal {{TRACE_OPEN_SPI200}} in response'
        )
        assert '{{TRACE_OPEN_AUDUSD}}' not in resp.text, (
            'Server must substitute placeholder — no literal {{TRACE_OPEN_AUDUSD}} in response'
        )

    def test_details_closed_when_cookie_excludes_instrument(
        self, monkeypatch, tmp_path,
    ):
        '''Cookie tsi_trace_open= (empty) → neither instrument gets open attribute.

        Reload with no cookie value should render all panels closed.
        '''
        client = _make_client(monkeypatch, tmp_path)
        _make_trace_html(tmp_path / 'dashboard.html')
        resp = _request_with_cookies(
            client, 'GET', '/',
            headers={AUTH_HEADER_NAME: VALID_SECRET},
            cookies={'tsi_trace_open': ''},
        )
        assert resp.status_code == 200
        assert not re.search(
            r'<details[^>]+data-instrument="SPI200"[^>]*\bopen\b',
            resp.text,
        ), 'Empty cookie → SPI200 must NOT be open'
        assert not re.search(
            r'<details[^>]+data-instrument="AUDUSD"[^>]*\bopen\b',
            resp.text,
        ), 'Empty cookie → AUDUSD must NOT be open'
        # Placeholders still consumed (substituted to empty string)
        assert '{{TRACE_OPEN_SPI200}}' not in resp.text
        assert '{{TRACE_OPEN_AUDUSD}}' not in resp.text

    def test_no_cookie_renders_closed(self, monkeypatch, tmp_path):
        '''No tsi_trace_open cookie at all → all panels closed.

        First-visit scenario: no prior toggle, no cookie sent. Server must
        render all panels closed (the default).
        '''
        client = _make_client(monkeypatch, tmp_path)
        _make_trace_html(tmp_path / 'dashboard.html')
        # No cookies kwarg → no tsi_trace_open header
        resp = client.get('/', headers={AUTH_HEADER_NAME: VALID_SECRET})
        assert resp.status_code == 200
        assert not re.search(
            r'<details[^>]+data-instrument="SPI200"[^>]*\bopen\b',
            resp.text,
        ), 'No cookie → SPI200 must NOT be open'
        assert not re.search(
            r'<details[^>]+data-instrument="AUDUSD"[^>]*\bopen\b',
            resp.text,
        ), 'No cookie → AUDUSD must NOT be open'
        # Placeholders substituted to empty string (not leaked)
        assert '{{TRACE_OPEN_SPI200}}' not in resp.text
        assert '{{TRACE_OPEN_AUDUSD}}' not in resp.text

    def test_unknown_instrument_in_cookie_ignored(self, monkeypatch, tmp_path):
        '''Cookie tsi_trace_open=EVIL_INJECT → no crash, no unexpected open attribute.

        Phase 29 Plan 12 T-29-12-01: tampered cookie values not matching
        ^[A-Z0-9_]{2,20}$ must be silently discarded. No injection surface.
        '''
        client = _make_client(monkeypatch, tmp_path)
        _make_trace_html(tmp_path / 'dashboard.html')
        resp = _request_with_cookies(
            client, 'GET', '/',
            headers={AUTH_HEADER_NAME: VALID_SECRET},
            cookies={'tsi_trace_open': 'EVIL_INJECT'},
        )
        assert resp.status_code == 200, (
            'Unknown cookie value must not crash server'
        )
        # EVIL_INJECT is a valid-format ID but not in state → no <details open>
        assert not re.search(
            r'<details[^>]+data-instrument="SPI200"[^>]*\bopen\b',
            resp.text,
        ), 'Unknown cookie key must not open SPI200'
        assert not re.search(
            r'<details[^>]+data-instrument="AUDUSD"[^>]*\bopen\b',
            resp.text,
        ), 'Unknown cookie key must not open AUDUSD'
        # No literal injection of EVIL_INJECT into the HTML
        assert 'EVIL_INJECT' not in resp.text, (
            'Tampered cookie key must not appear in rendered HTML'
        )
        # Placeholders consumed
        assert '{{TRACE_OPEN_SPI200}}' not in resp.text
        assert '{{TRACE_OPEN_AUDUSD}}' not in resp.text


class TestTraceDetailsOpenMarketScoped:
    '''Phase 29 Plan 12 UAT-17-2 market-scoped path.

    The iOS Safari failure was on /markets/SPI200/signals (the new multi-market
    route). This class tests the _serve_market_scoped_page path, which uses
    render_dashboard_as_str() + _substitute() in-memory (no on-disk file).
    The rendered HTML must contain the {{TRACE_OPEN_SPI200}} placeholder emitted
    by signals.py, and _substitute() must resolve it from the cookie.
    '''

    def _make_full_state_client(self, monkeypatch, tmp_path):
        '''Setup with a real state containing SPI200 + AUDUSD signals.'''
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv('WEB_AUTH_SECRET', VALID_SECRET)
        monkeypatch.setenv('WEB_AUTH_USERNAME', 'marc')
        import state_manager
        state = {
            'schema_version': 7,
            'account': 100_000.0,
            'last_run': '2026-04-25',
            'markets': {
                'SPI200': {
                    'display_name': 'SPI 200', 'symbol': '^AXJO', 'currency': 'AUD',
                    'multiplier': 5.0, 'cost_aud': 6.0, 'enabled': True, 'sort_order': 10,
                },
                'AUDUSD': {
                    'display_name': 'AUD / USD', 'symbol': 'AUDUSD=X', 'currency': 'AUD',
                    'multiplier': 10000.0, 'cost_aud': 5.0, 'enabled': True, 'sort_order': 20,
                },
            },
            'positions': {'SPI200': None, 'AUDUSD': None},
            'signals': {
                'SPI200': {
                    'signal': 1, 'last_close': 7820.0,
                    'indicator_scalars': {'adx': 30.0, 'mom1': 0.05},
                    'ohlc_window': [], 'vote_params': None,
                },
                'AUDUSD': {
                    'signal': 0, 'last_close': 0.6520,
                    'indicator_scalars': {'adx': 20.0, 'mom1': -0.01},
                    'ohlc_window': [], 'vote_params': None,
                },
            },
            'strategy_settings': {'SPI200': {}, 'AUDUSD': {}},
            'trade_log': [], 'equity_history': [], 'warnings': [],
            'paper_trades': [], 'closed_trades': [],
            'initial_account': 100_000.0,
            'contracts': {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-mini'},
            '_resolved_contracts': {
                'SPI200': {'multiplier': 5.0, 'cost_aud': 6.0},
                'AUDUSD': {'multiplier': 10000.0, 'cost_aud': 5.0},
            },
        }
        monkeypatch.setattr(state_manager, 'load_state', lambda *_a, **_kw: state)
        sys.modules.pop('web.app', None)
        from web.app import create_app
        return TestClient(create_app())

    def test_details_open_when_cookie_includes_instrument(
        self, monkeypatch, tmp_path,
    ):
        '''GET /markets/SPI200/signals with tsi_trace_open=SPI200 cookie →
        rendered HTML contains <details ... open> for SPI200.

        This is the exact iOS Safari reload path: operator taps "Show
        calculations", cookie is written, pull-to-refresh sends cookie →
        server must render panel open in initial HTML.
        '''
        client = self._make_full_state_client(monkeypatch, tmp_path)
        resp = _request_with_cookies(
            client, 'GET', '/markets/SPI200/signals',
            headers={AUTH_HEADER_NAME: VALID_SECRET},
            cookies={'tsi_trace_open': 'SPI200'},
        )
        assert resp.status_code == 200, f'Unexpected status {resp.status_code}'
        assert re.search(
            r'<details[^>]+data-instrument="SPI200"[^>]*\bopen\b',
            resp.text,
        ), (
            'UAT-17-2: /markets/SPI200/signals with tsi_trace_open=SPI200 '
            'must render <details open> server-side'
        )
        assert '{{TRACE_OPEN_SPI200}}' not in resp.text, (
            'No {{TRACE_OPEN_SPI200}} placeholder leak on /markets/SPI200/signals'
        )

    def test_details_closed_without_cookie(self, monkeypatch, tmp_path):
        '''GET /markets/SPI200/signals with no tsi_trace_open cookie →
        <details> renders without open attribute (panel collapsed on load).
        '''
        client = self._make_full_state_client(monkeypatch, tmp_path)
        resp = client.get(
            '/markets/SPI200/signals',
            headers={AUTH_HEADER_NAME: VALID_SECRET},
        )
        assert resp.status_code == 200
        assert not re.search(
            r'<details[^>]+data-instrument="SPI200"[^>]*\bopen\b',
            resp.text,
        ), 'No cookie → SPI200 details must NOT have open attribute'
        assert '{{TRACE_OPEN_SPI200}}' not in resp.text

    def test_dynamic_market_gets_placeholder_in_html(self, monkeypatch, tmp_path):
        '''Phase 29 Plan 12: _TraceOpenPlaceholderMap covers markets not in the
        legacy 2-entry dict. A market added after Phase 17 (e.g. ESM) must have
        its {{TRACE_OPEN_ESM}} placeholder emitted by the renderer so the
        server-side substitution can fire.

        Verifies the _TraceOpenPlaceholderMap fix: .get(key, '') now returns
        {{TRACE_OPEN_<KEY>}} for any valid market ID, not just SPI200/AUDUSD.
        '''
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv('WEB_AUTH_SECRET', VALID_SECRET)
        monkeypatch.setenv('WEB_AUTH_USERNAME', 'marc')
        import state_manager
        state = {
            'schema_version': 7,
            'account': 100_000.0,
            'last_run': '2026-04-25',
            'markets': {
                'ESM': {
                    'display_name': 'ES Mini', 'symbol': 'ES=F', 'currency': 'USD',
                    'multiplier': 50.0, 'cost_aud': 4.0, 'enabled': True, 'sort_order': 10,
                },
            },
            'positions': {'ESM': None},
            'signals': {
                'ESM': {
                    'signal': 0, 'last_close': 5200.0,
                    'indicator_scalars': {'adx': 18.0, 'mom1': 0.0},
                    'ohlc_window': [], 'vote_params': None,
                },
            },
            'strategy_settings': {'ESM': {}},
            'trade_log': [], 'equity_history': [], 'warnings': [],
            'paper_trades': [], 'closed_trades': [],
            'initial_account': 100_000.0,
            'contracts': {'ESM': 'es-mini'},
            '_resolved_contracts': {'ESM': {'multiplier': 50.0, 'cost_aud': 4.0}},
        }
        monkeypatch.setattr(state_manager, 'load_state', lambda *_a, **_kw: state)
        sys.modules.pop('web.app', None)
        from web.app import create_app
        client = TestClient(create_app())

        # First confirm placeholder is emitted (no cookie — should be blank)
        resp_no_cookie = client.get(
            '/markets/ESM/signals',
            headers={AUTH_HEADER_NAME: VALID_SECRET},
        )
        assert resp_no_cookie.status_code == 200
        # No placeholder leak
        assert '{{TRACE_OPEN_ESM}}' not in resp_no_cookie.text, (
            '_TraceOpenPlaceholderMap must emit and _substitute must consume '
            '{{TRACE_OPEN_ESM}} placeholder — must not leak to client'
        )

        # With cookie → open attribute emitted
        resp_with_cookie = _request_with_cookies(
            client, 'GET', '/markets/ESM/signals',
            headers={AUTH_HEADER_NAME: VALID_SECRET},
            cookies={'tsi_trace_open': 'ESM'},
        )
        assert resp_with_cookie.status_code == 200
        assert re.search(
            r'<details[^>]+data-instrument="ESM"[^>]*\bopen\b',
            resp_with_cookie.text,
        ), (
            'Dynamic market ESM with cookie tsi_trace_open=ESM must render '
            '<details open> server-side (_TraceOpenPlaceholderMap fix)'
        )
