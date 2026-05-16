# Phase 41: data feed integration - IG REST API - Context

**Gathered:** 2026-05-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Integrates the IG REST API as the primary market data source for SPI200 and AUD/USD daily OHLCV, with yfinance retained as a silent fallback. Changes are confined to `data_fetcher.py` (IG fetch + normalisation branch) and `system_params.py` (IG EPIC codes + new env var constants). The signal engine, sizing engine, and orchestration layer are unchanged — they continue to receive a `pd.DataFrame` with `Open/High/Low/Close/Volume` columns, exactly as today.

Files touched: `data_fetcher.py`, `system_params.py`, `.env.example`, `tests/test_data_fetcher.py`.

</domain>

<decisions>
## Implementation Decisions

### yfinance vs IG

- **D-01:** IG is the **primary** data source; yfinance is the **silent fallback**. If IG fetch fails (network error, auth failure, rate limit, or any exception), `data_fetcher.py` retries IG up to 3× (matching existing retry policy), then falls back to yfinance.
- **D-02:** When the **fallback is used**, a `WARNING`-level log line is emitted **and a dashboard warning is appended** via `state_manager.append_warning()` so the operator sees which source was used for that run.
- **D-03:** The data source used is **not persisted in `state.json`** — log line only. No `data_source` field added to state schema.

### Auth & Credentials

- **D-04:** IG credentials supplied via **new env vars**: `IG_API_KEY`, `IG_USERNAME`, `IG_PASSWORD`, `IG_ACCOUNT_TYPE` (`demo` or `live`). Documented in `.env.example`.
- **D-05:** IG session tokens are **in-memory only** — no persistence. Session is created at the start of each daily fetch, used, and discarded. Re-auth on every run.
- **D-06:** Credential presence is **validated eagerly at daily run startup**: if `IG_API_KEY` is not set, emit a `WARNING` log (`[Fetch] IG credentials not configured — falling back to yfinance`). Run proceeds via yfinance. No RuntimeError — consistent with the fallback design.

### Live vs EOD Data

- **D-07:** Phase scope is **historical EOD OHLCV only** — daily candles, same window as yfinance (300 bars, `system_params.HISTORY_BARS`). No live streaming, no intraday candles.
- **D-08:** History window uses the **existing `system_params.HISTORY_BARS` constant** (300). No new config parameter.
- **D-09:** Default environment is **IG demo** (`IG_ACCOUNT_TYPE=demo`). Operator switches to live by setting `IG_ACCOUNT_TYPE=live` in `.env`. Consistent with env-var config pattern.

### Data Shape Mapping

- **D-10:** IG fetch lives **inside `data_fetcher.py`** as a new branch — no separate `ig_fetcher.py` module. `fetch_ohlcv(symbol)` tries IG first, normalises IG JSON response to `pd.DataFrame`, falls back to yfinance on failure. Single hex-boundary I/O adapter, unchanged entry point for all callers.
- **D-11:** IG EPIC codes are stored in **`system_params.py` alongside `DEFAULT_MARKETS`** — add an `ig_epic` field to each market config entry (e.g., `DEFAULT_MARKETS['SPI200']['ig_epic'] = 'IX.D.ASX.IFM.IP'`). Single source of truth.
- **D-12:** For price normalisation, IG bid/ask candles are converted to **mid price** (`(bid + ask) / 2`) for all OHLCV fields. Consistent with yfinance reporting convention. Applied to Open, High, Low, Close uniformly.

### Claude's Discretion

- Exact IG REST endpoint(s) for historical daily candles (researcher to verify from labs.ig.com docs — likely `GET /prices/{epic}` with `resolution=DAY&max=300`).
- IG session creation endpoint and request body shape (researcher to verify from labs.ig.com — likely `POST /session` with `X-IG-API-KEY` header + `identifier`/`password` JSON body).
- Whether the IG retry policy mirrors the existing `_retry_with_backoff` helper in `data_fetcher.py` or requires a separate session-refresh retry (if auth fails mid-fetch, re-auth once then retry the price call).
- Volume field handling — IG may not provide volume for spread-bet instruments. Researcher to confirm; if absent, use `0` or `NaN` (consistent with how yfinance handles volume for FX pairs today).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### IG REST API
- `https://labs.ig.com/` — IG Labs API reference (REST v2). Researcher must verify endpoints for session creation and historical price fetch before planning.

### Project Constraints
- `.planning/ROADMAP.md` §Phase 41 — Goal, success criteria, and DOMAIN-01..03 requirements
- `.planning/REQUIREMENTS.md` — Requirement IDs relevant to data sourcing
- `CLAUDE.md` §Architecture — Hex-lite import boundaries; `data_fetcher.py` is the sole network I/O adapter for market data
- `system_params.py` — `HISTORY_BARS`, `HTTP_TIMEOUT_S` constants to reuse; `DEFAULT_MARKETS` dict where `ig_epic` fields will be added

### Existing Implementation to Extend
- `data_fetcher.py` — `fetch_ohlcv(symbol)` entry point, `_retry_with_backoff` helper, `DataFetchError` / `ShortFrameError` exception hierarchy, `_get_yf()` lazy-import pattern
- `.env.example` — Template for new `IG_API_KEY`, `IG_USERNAME`, `IG_PASSWORD`, `IG_ACCOUNT_TYPE` vars
- `tests/test_data_fetcher.py` — Existing test patterns to extend for IG fetch path

### Related Prior Phase Context
- `.planning/phases/38-news-integration/38-CONTEXT.md` — Sidecar file pattern for I/O adapters (for reference, not for reuse here)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `data_fetcher._retry_with_backoff`: existing 3-attempt, 10s-backoff helper — reuse or mirror for IG fetch retries
- `data_fetcher._get_yf_session()`: memoized requests.Session with canonical timeout injection — same session pattern for IG HTTP calls
- `system_params.HTTP_TIMEOUT_S`: canonical 30s timeout — apply to IG REST calls
- `system_params.HISTORY_BARS`: 300-bar history window — pass directly to IG candle request
- `state_manager.append_warning()`: for D-02 dashboard warning when fallback is used

### Established Patterns
- **Lazy import**: `data_fetcher._get_yf()` deferred import pattern — apply same pattern to any IG-specific lib if one is introduced (prefer `requests` directly, no new SDK)
- **Hex boundary**: `data_fetcher.py` imports `requests`, `pandas`, `system_params` — no signal/sizing engine imports allowed
- **Typed exceptions**: `DataFetchError` raised on all data-layer failures; callers in `daily_run.py` catch this to return `rc=2`
- **Env-var validation**: `_resolve_email_to_or_skip` pattern (Phase 27 #9) — warn + fallback on missing env var, never hard-fail optional integrations

### Integration Points
- `data_fetcher.fetch_ohlcv(symbol: str) -> pd.DataFrame` — this is the ONLY entry point callers use; return type and column names (`Open`, `High`, `Low`, `Close`, `Volume`, DatetimeIndex) must be preserved
- `daily_run._run_daily_check_impl()` — calls `fetch_ohlcv`; no changes needed here if D-10 is followed
- `.env.example` — add new IG vars before deployment

</code_context>

<specifics>
## Specific Ideas

- Use `https://labs.ig.com/` (IG Labs REST API) — confirmed by user as the API reference.
- IG EPIC for SPI200 is approximately `IX.D.ASX.IFM.IP` (researcher to verify exact code).
- `IG_ACCOUNT_TYPE` controls demo vs live environment — researcher to confirm how this changes the API base URL (typically `https://api.ig.com` for live vs `https://demo-api.ig.com` for demo).

</specifics>

<deferred>
## Deferred Ideas

- **Live spot price for dashboard P&L** — using IG live prices for unrealised P&L display was discussed and excluded from this phase. Candidate for a follow-on phase.
- **Intraday candles / live streaming** — excluded from this phase (EOD only). Future phase if intraday signal tracking is needed.
- **Roadmap numbering conflict** — the v1.4 milestone already has a "Phase 41: Domain Models" entry in ROADMAP.md. This IG data feed phase was also assigned number 41 by gsd-phase. One of them should be renumbered (Domain Models → Phase 42). Operator to confirm before planning.

</deferred>

---

*Phase: 41-data-feed-integration-ig-rest-api*
*Context gathered: 2026-05-16*
