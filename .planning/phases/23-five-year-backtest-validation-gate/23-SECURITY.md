# Security Audit — Phase 23: Five-Year Backtest Validation Gate

**Audit Date:** 2026-05-01
**Phase:** 23 — Five-Year Backtest Validation Gate
**ASVS Level:** 1
**Auditor:** gsd-secure-phase
**Threats Closed:** 8/8
**Threats Open:** 0/8

---

## Threat Verification

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-23-pyarrow | Tampering / Supply-chain | mitigate | CLOSED | `requirements.txt:20` — `pyarrow==24.0.0` exact pin (no `>=`, no `~=`) |
| T-23-cache-tamper | Tampering | mitigate | CLOSED | `.gitignore:13` — `.planning/backtests/data/` git-ignored; parquet binary format (no eval/code path on read); `_REQUIRED_COLUMNS` validated post-fetch (`data_fetcher.py:26,75-79`); `--refresh` recovery in `fetch_ohlcv` signature |
| T-23-cdn | Tampering (CDN compromise) | mitigate | CLOSED | `backtest/render.py:18` — `_CHARTJS_SRI = 'sha384-MH1axGwz/uQzfIcjFdjEfsM0xlf5mmWfAwwggaOh5IPFvgKFGbJ2PZ4VBbgSYBQN'`; emitted via `_render_chart_script_tag()` at `render.py:54-60` with `integrity=` + `crossorigin="anonymous"` |
| XSS via report fields | Tampering | mitigate | CLOSED | `backtest/render.py:35-37` — `_e(s) = html.escape(str(s), quote=True)` applied to every operator-visible string in trade rows (`render.py:172-183`), metadata header (`render.py:268-273`), history rows (`render.py:341-350`) |
| JSON injection in script | Tampering | mitigate | CLOSED | `backtest/render.py:46-51` — `_payload()` uses `json.dumps(..., allow_nan=False).replace('</', '<\\/')` applied to all Chart.js data blocks (equity curve panels + history overlay) |
| T-23-traversal | Information Disclosure | mitigate | CLOSED | `web/routes/backtest.py:47` — `_SAFE_FILENAME_RE = re.compile(r'^[a-zA-Z0-9._-]+\.json$')`; `web/routes/backtest.py:61,64` — regex gate applied first, then `os.listdir()` whitelist confirms file exists in canonical directory; `ValueError` on mismatch returned as HTTP 400 |
| T-23-input | Tampering | mitigate | CLOSED | `web/routes/backtest.py:174` — `if not (initial_account_aud > 0)` → 400; `web/routes/backtest.py:182` — `if cost_spi_aud < 0` → 400; `web/routes/backtest.py:190` — `if cost_audusd_aud < 0` → 400 |
| T-23-auth | Elevation of Privilege | mitigate | CLOSED | `web/app.py:162` — `backtest_route.register(application)` mounted before `AuthMiddleware`; `web/app.py:186` — `AuthMiddleware` registered last (runs first per Starlette reverse-order); `web/middleware/auth.py:66-69` — `PUBLIC_PATHS` does not include `/backtest` or `/backtest/run`; all /backtest* routes auth-gated uniformly |

---

## Mitigation Detail

### T-23-pyarrow
Exact pin `pyarrow==24.0.0` is present at `requirements.txt:20`. No range specifier. AST guard at `tests/test_signal_engine.py::TestDeterminism::test_backtest_pure_no_pyarrow_import` (parametrised × 3) blocks pyarrow from leaking into the pure-math modules (`simulator.py`, `metrics.py`, `render.py`). `data_fetcher.py` is the documented I/O exception per CONTEXT D-09.

### T-23-cache-tamper
Parquet is a schema-typed binary columnar format with no `eval`/`exec` code path on read. `_REQUIRED_COLUMNS` validation (`data_fetcher.py:75-79`) runs after every yfinance fetch (cache-miss path). Cache-hit path reads the parquet written by the validated path, so column validation is implicitly preserved. `.planning/backtests/data/` is git-ignored (`..gitignore:13`), preventing accidental commit of operator-local cache files. `refresh=True` in `fetch_ohlcv` provides recovery on any suspected tamper.

### T-23-cdn
`_render_chart_script_tag()` (`render.py:54-60`) emits:
```
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.js"
        integrity="sha384-MH1axGwz/uQzfIcjFdjEfsM0xlf5mmWfAwwggaOh5IPFvgKFGbJ2PZ4VBbgSYBQN"
        crossorigin="anonymous"></script>
```
Browser enforces SRI; mismatched CDN content is refused. `TestChartJsSri` (3 tests) verifies URL + hash + crossorigin attribute are present in rendered output.

### XSS via report fields
`_e()` helper (`render.py:35-37`) calls `html.escape(str(s), quote=True)`. Applied to: trade open/close dates, instrument, side, entry/exit prices, contracts, exit_reason, metadata strategy version, run_dt, initial account, costs, history rows (strategy version, run_dt, end_date, filename). `TestJsonInjectionDefence::test_html_escape_on_trade_table_fields` injects `<img src=x onerror=alert(1)>` into `exit_reason` and asserts `&lt;img` present / raw `<img` absent.

### JSON injection in script
`_payload()` (`render.py:40-51`) centralises all Chart.js JSON serialisation: `json.dumps(..., ensure_ascii=False, sort_keys=True, allow_nan=False).replace('</', '<\\/')`. Applied to per-instrument equity curve payloads (3 tab panels) and the history overlay dataset payload. `TestJsonInjectionDefence::test_script_close_in_payload_is_escaped` injects `</script><script>alert(1)</script>` into an equity-curve label and asserts `</script>alert` does not appear in output.

### T-23-traversal
Two-layer defence in `_resolve_safe_backtest_path()` (`web/routes/backtest.py:52-69`):
1. `_SAFE_FILENAME_RE.match(filename)` — regex `^[a-zA-Z0-9._-]+\.json$` rejects `..`, `/`, absolute paths, null bytes, and non-JSON extensions.
2. `set(os.listdir(backtest_dir))` — filename must appear in the canonical directory listing; path join is performed only after both checks pass.
`ValueError` propagates to the caller, which returns HTTP 400. `TestPathTraversal` (5 tests) covers: `../../etc/passwd`, `/etc/passwd`, `foo/bar.json`, unknown filename, and a valid filename returning 200.

### T-23-input
Server-side validation in `post_backtest_run()` (`web/routes/backtest.py:173-197`):
- `initial_account_aud > 0` — zero and negative values rejected with HTTP 400.
- `cost_spi_aud >= 0` — negative values rejected with HTTP 400; zero is allowed (operator may run cost-free simulation).
- `cost_audusd_aud >= 0` — same rule as SPI cost.
`ShortFrameError` and `DataFetchError` from the simulation layer are caught and returned as HTTP 400 (not 500). `TestPostRun` (7 tests) covers valid submit (303), zero account (400), negative account (400), negative SPI cost (400), negative AUD/USD cost (400), zero cost allowed (303).

### T-23-auth
`AuthMiddleware` is registered last in `create_app()` (`web/app.py:186`), which per Starlette's reverse-registration order means it runs first on every request. `PUBLIC_PATHS` (`web/middleware/auth.py:66-69`) contains only `/login`, `/logout`, `/enroll-totp`, `/verify-totp`, `/forgot-2fa`, `/reset-totp` — `/backtest` and `/backtest/run` are absent. Unauthenticated browser requests receive 302 → `/login`; unauthenticated API/curl requests receive 401. `TestCookieAuth` (3 tests) covers: browser GET → 302/401, curl GET → 401, POST without cookie → 401.

---

## Unregistered Flags

None. SUMMARY.md `## Threat Flags` sections for plans 23-01, 23-02, 23-05, and 23-07 all declare no new threat flags. No unregistered attack surface was observed during verification.

---

## Accepted Risks Log

None. All 8 threats are mitigated. No threats were accepted or transferred.

---

## Notes

- `backtest/data_fetcher.py` is the documented I/O exception per CONTEXT D-09. It is explicitly excluded from the `BACKTEST_PATHS_PURE` AST guard and permitted to import `yfinance` and `pyarrow`. This is an intentional architectural decision, not an oversight.
- The `render_history()` function constructs a `/backtest?run=<filename>` link using `_e(meta.get('filename', ''))` (`render.py:341,348`). The `filename` value is injected by `_load_report()` from `path.name` (`web/routes/backtest.py:93`), which is the filename component of a `Path` object already validated through `_resolve_safe_backtest_path()` or `_list_reports()`. No user-supplied data reaches this field.
- The history view link URL parameter `?run=<filename>` is HTML-attribute-escaped via `_e()` before insertion into the `href`, preventing attribute injection. When the link is followed, `_resolve_safe_backtest_path()` re-validates the filename on the server side (defence in depth).
