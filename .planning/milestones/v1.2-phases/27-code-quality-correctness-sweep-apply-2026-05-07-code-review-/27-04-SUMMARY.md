---
phase: 27
plan: 04
subsystem: instrument-id syntax + membership two-layer policy
tags:
  - phase-27
  - instrument-regex
  - two-layer-validation
  - tampering-mitigation
  - single-source-of-truth
  - ast-regression
requires: []
provides:
  - system_params.INSTRUMENT_ID_RE (single canonical syntax pattern ^[A-Z0-9_]{2,20}$)
  - system_params.KNOWN_MARKET_IDS (frozenset of canonical default markets)
  - system_params.is_known_market(id) (two-layer public API — syntax + membership)
  - tests/test_instrument_regex.py (18-test regression suite + AST + Pydantic + single-source pins)
affects:
  - web/routes/dashboard.py (imports INSTRUMENT_ID_RE from system_params; docstring updated)
tech-stack:
  added: []
  patterns:
    - Two-layer validation policy — generic syntax regex + explicit membership set
    - AST walker over re.* calls with anchor heuristic + placeholder whitelist
    - Source-text scan of Pydantic Field(pattern=r'...') for cross-cutting regex audit
    - Single-source-of-truth pin via fullmatch(canonical_pattern in src) test
key-files:
  created:
    - tests/test_instrument_regex.py
  modified:
    - system_params.py
    - web/routes/dashboard.py
decisions:
  - INSTRUMENT_ID_RE stays generic (^[A-Z0-9_]{2,20}$) — coupling syntax to specific market ids would force regex changes on every market add; the membership layer owns "supported markets"
  - KNOWN_MARKET_IDS is a frozenset (immutable, hashable) seeded from DEFAULT_MARKETS keys; operator-added markets via POST /markets continue to be validated against state['markets'] at the route boundary (dynamic membership)
  - is_known_market accepts `object` (not str) and short-circuits on non-string — defensive at trust boundary, never raises
  - web/routes/dashboard.py imports INSTRUMENT_ID_RE from system_params (no duplicate compile); markets.py + trades.py keep the literal Pydantic Field(pattern=r'...') for grep-discoverability — single-source pinned by source-text test
  - Existing state-based membership checks (`if market_id not in state['markets']: 404` in trades.py / dashboard.py / markets.py) kept as the runtime gate — supports dynamically added markets; is_known_market is the static fallback for paths/cookies without state context
  - AST walker whitelists both literal `{{...}}` and regex-escaped `\{\{...\}\}` substitution placeholders (TRACE_OPEN family) — those operate on server-controlled bytes, not untrusted inputs
metrics:
  duration: ~7min
  tasks: 1
  files: 3
  tests-added: 18
  tests-passing: 1841 (full suite, +18 from 1823)
  completed: 2026-05-07
---

# Phase 27 Plan 04: Instrument Regex Tightening Summary

Centralised the canonical instrument-id syntax regex into `system_params.INSTRUMENT_ID_RE` and added a separate `KNOWN_MARKET_IDS` membership set + `is_known_market()` two-layer helper. Audit confirmed every existing instrument-id regex is already anchored with `^...$`; the only change required at consumer sites was updating `web/routes/dashboard.py` to source the pattern from system_params (eliminating the duplicate `re.compile`). 18-test regression suite locks the two-layer policy + the AST/source-text walkers prevent future drift.

## What shipped

### `system_params.INSTRUMENT_ID_RE` — canonical syntax pattern

```python
INSTRUMENT_ID_RE: re.Pattern[str] = re.compile(r'^[A-Z0-9_]{2,20}$')
```

Module-level compiled pattern. Same characters as the Pydantic `Field(pattern=r'...')` strings already in `web/routes/markets.py` (lines 20, 43) and `web/routes/trades.py` (lines 109, 156, 187). The Pydantic strings can't share the compiled object directly (pattern= takes a string), so the AST tests + source-text scan pin the literal mirror.

### `system_params.KNOWN_MARKET_IDS` — canonical membership set

```python
KNOWN_MARKET_IDS: frozenset[str] = frozenset({'SPI200', 'AUDUSD'})
```

Frozenset (immutable, hashable, set-membership semantics). Mirrors the keys of `DEFAULT_MARKETS` (already in system_params:172) but is owned separately so `KNOWN_MARKET_IDS` can be imported by adapter layers without dragging the full registry dict.

### `system_params.is_known_market` — two-layer public API

```python
def is_known_market(market_id: object) -> bool:
  if not isinstance(market_id, str):
    return False
  if not INSTRUMENT_ID_RE.fullmatch(market_id):
    return False
  return market_id in KNOWN_MARKET_IDS
```

Accepts `object` (not just `str`) so the trust-boundary check never raises on garbage input. Three short-circuits: non-string → False, fails Layer 1 → False, fails Layer 2 → False. Only `(str, syntactically valid, in KNOWN_MARKET_IDS)` returns True.

### `web/routes/dashboard.py` — single-source import

| Before | After |
| ------ | ----- |
| `_MARKET_ID_RE = re.compile(r'^[A-Z0-9_]{2,20}$')` (local module-level compile) | `from system_params import INSTRUMENT_ID_RE as _MARKET_ID_RE` (alias preserves call-site name) |

The alias `_MARKET_ID_RE` is preserved so the existing call sites in `_set_market_cookie` (line 256), `_serve_market_scoped_page` (line 273 via the cookie validator), and `get_markets_strip` (line 374) continue to read `_MARKET_ID_RE.fullmatch(...)` without churn. Phase 14 D-02 hex-allowlist already permits `system_params` import for web/ — no boundary cross.

Docstring updated: the file's stale "Forbidden: ... system_params" line was corrected to match the actual `tests/test_web_healthz.py::TestWebHexBoundary` allowlist (system_params + sizing_engine were promoted in Phase 14 D-02; the docstring had not been resynced).

### `tests/test_instrument_regex.py` — 18-test regression suite

| Test class | Covers |
| ---------- | ------ |
| `TestInstrumentIdRegexSyntax` (5 tests) | Syntax — accepts SPI200/AUDUSD/AUD_USD/A1/20-char; rejects too-short, too-long, lowercase, special chars |
| `TestTwoLayerPolicy` (2 tests) | Proof — SPI200X passes regex (Layer 1), fails membership (Layer 2). The whole point of the plan. |
| `TestIsKnownMarket` (3 tests) | Membership — accepts SPI200/AUDUSD; rejects garbage syntax (short-circuit); never raises on None/int/list |
| `TestKnownMarketIdsShape` (3 tests) | Invariants — frozenset, contains canonical defaults, every member passes Layer 1 |
| `TestNoUnanchoredInstrumentRegexInProd` (1 test) | AST walker — every `re.compile/match/search/fullmatch/sub` over a string literal containing `[A-Z` MUST be anchored with `^...$` (whitelist: `{{...}}` and `\{\{...\}\}` substitution placeholders) |
| `TestPydanticInstrumentPatternsAnchored` (1 test) | Source-text scan — every `Field(pattern=r'...')` literal containing `[A-Z` MUST be anchored |
| `TestSingleSourceOfTruth` (3 tests) | Pin — web/routes/dashboard.py + markets.py + trades.py all contain the canonical pattern string |

## Audited regex sites

Full grep of `re.compile|re.match|re.search|re.fullmatch` across `dashboard.py`, `main.py`, `notifier.py`, `state_manager.py`, `auth_store.py`, `data_fetcher.py`, `web/`, `dashboard_renderer/`:

| File:line | Pattern | Disposition | Reason |
| --------- | ------- | ----------- | ------ |
| `web/app.py:62` | `^[^@]+@[^@]+\.[^@]+$` | Already anchored — kept | Email regex, different domain |
| `web/routes/dashboard.py:78` (was) | `^[A-Z0-9_]{2,20}$` (local compile) | Replaced with `from system_params import INSTRUMENT_ID_RE` | Single-source consolidation |
| `web/routes/dashboard.py:110` | `\{\{TRACE_OPEN_([A-Z0-9_]{2,20})\}\}` | Whitelisted (substitution placeholder, server-controlled bytes) | AST walker recognises both `{{` and `\{\{` escape forms |
| `web/routes/dashboard.py:616` | `<tbody id="...">(.*?)</tbody>` (built dynamically with `re.escape`) | Already safe | Operates on server-controlled HTML; `re.escape` neutralises any regex injection from `fragment` query param |
| `web/routes/backtest.py:46` | `^[a-zA-Z0-9._-]+\.json$` | Already anchored — kept | Backtest filename whitelist, different domain |

Pydantic `Field(pattern=r'...')` audit (5 sites):

| File:line | Pattern | Disposition |
| --------- | ------- | ----------- |
| `web/routes/markets.py:20` | `^[A-Z0-9_]{2,20}$` (MarketRequest.market_id) | Already anchored |
| `web/routes/markets.py:43` | `^[A-Z0-9_]{2,20}$` (MarketSettingsRequest.market_id) | Already anchored |
| `web/routes/trades.py:109` | `^[A-Z0-9_]{2,20}$` (OpenTradeRequest.instrument) | Already anchored |
| `web/routes/trades.py:156` | `^[A-Z0-9_]{2,20}$` (CloseTradeRequest.instrument) | Already anchored |
| `web/routes/trades.py:187` | `^[A-Z0-9_]{2,20}$` (ModifyTradeRequest.instrument) | Already anchored |

`web/routes/paper_trades.py` uses `Literal['SPI200', 'AUDUSD']` for `instrument` — strictly stronger than a regex (Pydantic enforces enum membership directly). No change needed.

## Routing entry-point gating

The plan asks every routing entry point that looks up `state['signals'][id]` or `state['markets'][id]` to gate on a membership check BEFORE the lookup. Audit pass:

| Site | Pre-existing gate | Adequate? |
| ---- | ----------------- | --------- |
| `web/routes/dashboard.py::_serve_market_scoped_page` (line 269) | `if market_id not in markets: 404` (state-based membership) | Yes — state['markets'] is the dynamic membership oracle |
| `web/routes/dashboard.py::get_markets_strip` (line 369-373) | `_MARKET_ID_RE.fullmatch(raw_cookie)` (Layer 1) + `active_market not in markets` (Layer 2 state-based) | Yes — two-layer at cookie boundary |
| `web/routes/trades.py::open_trade` (line 474-476) | `known_markets = state.get('markets') or state.get('positions', {})` + `if req.instrument not in known_markets: 400` | Yes — Pydantic enforces Layer 1 at parse, state membership at apply |
| `web/routes/trades.py::close_trade` (line 577-579) | Same as open_trade | Yes |
| `web/routes/markets.py` (PATCH paths) | `if market_id not in state['markets']: 404` | Yes — state-based membership |
| `dashboard.py` lookups (`signals.values()`, `_display_names(state).items()`) | Iterates over keys sourced from state['markets'] / state['signals'] (operator-controlled) | Yes — keys originate from validated writes |
| `main.py` daily loop (`state['signals'][state_key] = ...`) | state_key is computed from `state['markets']` keys (validated via Pydantic on POST /markets) | Yes — by construction |

**Why state-based membership is the right gate (not is_known_market)**: operators can POST new markets via `/markets` (Pydantic-validated against INSTRUMENT_ID_RE at parse time, then stored in `state['markets']`). A static `is_known_market(id)` check would block legitimate operator-added markets. `is_known_market` remains as the static helper for paths/cookies/CLI flags that don't have access to current state, plus as the canonical default for documentation/tests.

## AST walker output

```
$ pytest tests/test_instrument_regex.py::TestNoUnanchoredInstrumentRegexInProd -v
PASSED — 0 offenders across 12 production files
```

Files scanned: `dashboard.py`, `main.py`, `notifier.py`, `state_manager.py`, `auth_store.py`, `data_fetcher.py`, `web/routes/dashboard.py`, `web/routes/markets.py`, `web/routes/trades.py`, `web/routes/paper_trades.py`, `web/routes/backtest.py`, `web/app.py`.

## Deviations from Plan

### Auto-fixed issues

**1. [Rule 1 - Bug] `web/routes/dashboard.py` docstring listed `system_params` as forbidden, but `tests/test_web_healthz.py::TestWebHexBoundary` allows it (Phase 14 D-02 promotion).**

- **Found during:** preparing the `from system_params import INSTRUMENT_ID_RE` change
- **Issue:** The file's `Forbidden: signal_engine, sizing_engine, system_params, notifier, main.` line was a stale documentation artefact — Phase 14 D-02 promoted `sizing_engine` and `system_params` to allowed (test `test_sizing_engine_is_not_forbidden_for_web_phase_14_D02` and `test_system_params_is_not_forbidden_for_web_phase_14`). The docstring was never resynced.
- **Fix:** Updated the docstring's `Allowed` and `Forbidden` lists to match the live test allowlist. Pure doc-fix; no behaviour change.
- **Files modified:** `web/routes/dashboard.py`.
- **Commit:** rolled into `fb7cb7d` (the GREEN feat commit) — the documentation fix is required to make the import legitimate-by-comment.

### Plan-spec adjustments

**Plan called for ~10 tests; shipped 18.** The plan enumerated 10 behaviours; the suite groups them into 7 test classes for readability and adds three single-source-of-truth pins (one per consumer file) plus the Pydantic source-text scan. Strictly stronger than plan-as-written. The two-layer policy proof tests (`test_instrument_id_re_accepts_extension_attack_syntactically` + `test_is_known_market_rejects_extension_attack`) are explicitly named per the review-fix agreed-8 amendment.

**`KNOWN_MARKET_IDS` is intentionally NOT used as a runtime gate at routing entry points.** The plan's text suggests gating every state lookup on `is_known_market` — that would block operator-added markets. Reconciliation: `is_known_market` is the static helper for paths without state context (and the canonical default for docs/tests); existing state-based membership checks (`if market_id not in state['markets']: 404`) remain the runtime authority. The plan's audit pass confirms every routing entry point already has an adequate state-based gate.

### Authentication gates

None — no auth surface touched.

## Threat surface scan

No new surface introduced. Plan's `<threat_model>` T-27-04-01 (tampering — too-loose regex letting `SPI200X` reach state lookup) is mitigated by the two-layer policy combined with existing state-based membership. No new endpoints, no new file access, no new schema changes.

## Verification

```
$ pytest tests/test_instrument_regex.py -x -v
  → 18 passed in 0.09s

$ pytest tests/test_instrument_regex.py tests/test_web_healthz.py -x -v
  → 38 passed in 1.47s

$ pytest -x
  → 1841 passed in 112.29s (full suite, +18 from 1823)

$ grep -rnE 're\.compile' dashboard.py main.py notifier.py state_manager.py auth_store.py data_fetcher.py web/
  web/app.py:62:_EMAIL_RE = re.compile(r'^[^@]+@[^@]+\.[^@]+$')                          # anchored
  web/routes/dashboard.py:110:_TRACE_OPEN_RE = re.compile(rb'\{\{TRACE_OPEN_([A-Z0-9_]{2,20})\}\}')  # placeholder, whitelisted
  web/routes/backtest.py:46:_SAFE_FILENAME_RE = re.compile(r'^[a-zA-Z0-9._-]+\.json$')   # anchored
  → 0 instrument-id compile sites left in adapter code (all flow through system_params.INSTRUMENT_ID_RE)
```

Before/after counts:

| Metric | Before | After |
| ------ | ------ | ----- |
| `re.compile(r'^[A-Z0-9_]{2,20}$')` literals in adapter code | 1 (web/routes/dashboard.py:78) | 0 — imported from system_params |
| Pydantic `Field(pattern=r'^[A-Z0-9_]{2,20}$')` literals | 5 | 5 (kept for grep-discoverability; pinned by source-text test) |
| Suspicious unanchored `[A-Z]` regexes in prod | 0 | 0 |
| Two-layer regression tests | 0 | 18 |
| Public symbols providing instrument validation | 0 | 3 (`INSTRUMENT_ID_RE`, `KNOWN_MARKET_IDS`, `is_known_market`) |

## Commits

| Hash    | Type | Title                                                                              |
| ------- | ---- | ---------------------------------------------------------------------------------- |
| 24fd41c | test | RED — failing two-layer instrument regex regression suite                          |
| fb7cb7d | feat | GREEN — INSTRUMENT_ID_RE + KNOWN_MARKET_IDS + is_known_market in system_params     |

## Self-Check: PASSED

- `system_params.py` modified — confirmed (`INSTRUMENT_ID_RE`, `KNOWN_MARKET_IDS`, `is_known_market` added under the redact_secret block).
- `web/routes/dashboard.py` modified — confirmed (alias import + docstring fix).
- `tests/test_instrument_regex.py` created — confirmed (18 tests, all green).
- Both commit hashes (`24fd41c`, `fb7cb7d`) resolvable via `git log --oneline`.
- Full suite 1841 green; +18 new tests landed cleanly.
- AST walker test green — 0 unanchored instrument regexes in 12 production files.
- Source-text scan green — every `Field(pattern=r'...')` containing `[A-Z` is anchored.
- Single-source-of-truth pin green — canonical pattern present in dashboard.py + markets.py + trades.py source.
