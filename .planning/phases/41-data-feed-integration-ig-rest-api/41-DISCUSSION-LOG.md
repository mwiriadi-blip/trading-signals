# Phase 41: data feed integration - IG REST API - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-16
**Phase:** 41-data-feed-integration-ig-rest-api
**Areas discussed:** yfinance vs IG, Auth & credentials, Live vs EOD data, Data shape mapping

---

## yfinance vs IG

| Option | Description | Selected |
|--------|-------------|----------|
| Replace yfinance entirely | data_fetcher.py talks to IG only | |
| IG primary, yfinance fallback | Try IG first; fall back to yfinance on failure | ✓ |
| Both run in parallel | Fetch from both, compare/validate | |

**User's choice:** IG primary, yfinance fallback

| Option | Description | Selected |
|--------|-------------|----------|
| Silent fallback — log WARNING, use yfinance transparently | DataFetchError only if both fail | |
| Explicit warning in dashboard — note which source was used | Append state warning if yfinance was used | ✓ |
| Hard fail on IG failure — raise DataFetchError immediately | No fallback | |

**User's choice:** Explicit warning in dashboard

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — record data_source per market per run | Adds field to state.json | |
| No — log only, not persisted | Source visible in journalctl only | ✓ |
| You decide | Claude picks approach | |

**User's choice:** No — log only, not persisted

---

## Auth & credentials

| Option | Description | Selected |
|--------|-------------|----------|
| New env vars | IG_API_KEY, IG_USERNAME, IG_PASSWORD, IG_ACCOUNT_TYPE | ✓ |
| Dedicated IG config file | Separate ig_config.json or ig.env | |
| Reuse WEB_AUTH_SECRET namespace | Prefix IG creds into existing namespace | |

**User's choice:** New env vars

| Option | Description | Selected |
|--------|-------------|----------|
| In-memory only, re-auth per daily run | Session created per run, discarded after | ✓ |
| Persisted in state.json with expiry timestamp | Token flows through state.json | |
| Persisted in separate ig_session.json sidecar | Token in sidecar, reused if valid | |

**User's choice:** In-memory only, re-auth per daily run

| Option | Description | Selected |
|--------|-------------|----------|
| Lazy — validate only on first fetch attempt | Fail silently to yfinance | |
| Eager — validate at startup, warn if missing | Log WARNING if IG_API_KEY unset | ✓ |
| Strict — fail-closed if IG creds are missing | RuntimeError at startup | |

**User's choice:** Eager — validate at startup, warn if missing

---

## Live vs EOD data

| Option | Description | Selected |
|--------|-------------|----------|
| Historical EOD OHLCV only | Replaces yfinance for daily 08:00 run | ✓ |
| EOD OHLCV + live spot price | EOD for signals + live mid-price for dashboard | |
| Live intraday candles | Real-time candles, streaming architecture | |

**User's choice:** Historical EOD OHLCV only

| Option | Description | Selected |
|--------|-------------|----------|
| Match existing HISTORY_BARS constant (300) | Reuse system_params.HISTORY_BARS | ✓ |
| Configurable per-source | Add IG_HISTORY_BARS env var | |

**User's choice:** Match existing HISTORY_BARS constant (300)

| Option | Description | Selected |
|--------|-------------|----------|
| Demo account first, configurable via IG_ACCOUNT_TYPE | Safe for dev/test | ✓ |
| Live account only | Always connects to live data | |
| You decide | Claude picks at plan time | |

**User's choice:** Demo account first, configurable via IG_ACCOUNT_TYPE

---

## Data shape mapping

| Option | Description | Selected |
|--------|-------------|----------|
| Inside data_fetcher.py — same adapter, new branch | fetch_ohlcv() tries IG, normalises, falls back | ✓ |
| New ig_fetcher.py I/O adapter, called from data_fetcher.py | IG logic in own module | |
| New ig_fetcher.py as drop-in peer | Orchestration layer picks between two fetchers | |

**User's choice:** Inside data_fetcher.py — same adapter, new branch

| Option | Description | Selected |
|--------|-------------|----------|
| system_params.py alongside existing DEFAULT_MARKETS | Add ig_epic field to each market config | ✓ |
| New IG_EPICS dict in system_params.py | Separate dict keyed by market symbol | |
| Env vars (IG_EPIC_SPI200, IG_EPIC_AUDUSD) | Operator sets EPICs at deploy time | |

**User's choice:** system_params.py alongside existing DEFAULT_MARKETS

| Option | Description | Selected |
|--------|-------------|----------|
| Mid price ((bid+ask)/2) | Standard convention, consistent with yfinance | ✓ |
| Bid price | Conservative exit modelling | |
| You decide | Claude picks after reviewing IG API docs | |

**User's choice:** Mid price ((bid+ask)/2)

---

## Claude's Discretion

- Exact IG REST endpoint(s) for historical daily candles
- IG session creation endpoint and request body shape
- Whether IG retry policy reuses existing `_retry_with_backoff` or needs session-refresh retry
- Volume field handling if IG doesn't provide volume for spread-bet instruments

## Deferred Ideas

- Live spot price for dashboard P&L display — excluded from this phase, candidate for follow-on
- Intraday candles / live streaming — excluded (EOD only)
- Roadmap numbering conflict (Phase 41 Domain Models vs Phase 41 IG data feed) — operator to resolve
