# Phase 38: News Integration - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-15
**Phase:** 38-news-integration
**Areas discussed:** News panel UI, Cache storage tier, Keyword list location, Dismiss expiry

---

## News Panel UI

### Panel placement

| Option | Description | Selected |
|--------|-------------|----------|
| Bottom of page | Below existing signal/calculator/drift panels — supplementary context | ✓ |
| Top of page | Above signal panels — high visibility but banner could dominate | |
| Sidebar / aside | Right-side column — no existing 2-column pattern | |

**User's choice:** Bottom of page

### Panel collapsibility

| Option | Description | Selected |
|--------|-------------|----------|
| Collapsible, open by default | Matches trace panel pattern; collapse state server-side | ✓ |
| Always open | Simpler, no state needed; fine for short panel | |
| Collapsible, closed by default | Opt-in; risk of missing critical banner | |

**User's choice:** Collapsible, open by default

### Critical-event banner placement

| Option | Description | Selected |
|--------|-------------|----------|
| Inside news panel, above headlines | Contextually tied to triggering news | ✓ |
| Full-width page banner | High visibility; requires page-level layout injection | |
| You decide | Defer to planner | |

**User's choice:** Inside news panel, above headlines

---

## Cache Storage Tier

### Cache location

| Option | Description | Selected |
|--------|-------------|----------|
| Sidecar news_cache.json | Keeps state.json clean; no fcntl contention | ✓ |
| In state.json under state['news_cache'] | Uses existing atomic store; inflates state dict | |
| In-memory dict | Simplest; lost on restart | |

**User's choice:** Sidecar news_cache.json

### File structure

| Option | Description | Selected |
|--------|-------------|----------|
| Single news_cache.json (all markets) | Dict keyed by market_id + date | |
| Per-market files | news_cache_SPI200.json, news_cache_AUDUSD.json — cleaner isolation | ✓ |
| You decide | Defer to planner | |

**User's choice:** Per-market files

---

## Keyword List Location

### Storage location

| Option | Description | Selected |
|--------|-------------|----------|
| system_params.py | Single source of truth per CLAUDE.md; matches existing constants pattern | ✓ |
| Inline in news_filter.py | Self-contained; breaks convention | |
| External config file | Operator-editable; new file type, no precedent | |

**User's choice:** system_params.py

### Match threshold

| Option | Description | Selected |
|--------|-------------|----------|
| Any match fires banner | High recall; meets ≥0.9 target; simpler | ✓ |
| N-of-M threshold | Higher precision; risk of missing events; adds constant | |
| You decide | Defer to planner | |

**User's choice:** Any match fires banner

---

## Dismiss Expiry

### Expiry strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Auto-expire daily | Scoped to cache date; no state accumulation; matches daily-fetch rhythm | ✓ |
| Persist until un-dismissed | Permanent hide; unbounded state growth | |
| You decide | Defer to planner | |

**User's choice:** Auto-expire daily

### Dismiss UX

| Option | Description | Selected |
|--------|-------------|----------|
| HTMX removes row immediately | Empty-200 pattern from revoke-invite; clean and instant | ✓ |
| Row fades/strikethrough | Visual clutter; dismissed items still take space | |
| Reload whole news panel | More round-trips; simpler route handler | |

**User's choice:** HTMX removes row immediately

---

## Claude's Discretion

- Exact keyword content for NEWS_KEYWORDS_SPI200, NEWS_KEYWORDS_AUDUSD, NEWS_DAMPENER_ALLOWLIST (researcher validates against 30-headline fixture)
- `news_filter.py` function signature (single headline vs batch classifier)
- Collapse state field name in `state['users'][uid]`
- Whether sidecar cache files are written atomically or via simple json.dump
- yfinance fixture capture method for schema normalisation (plan-time verification flagged in ROADMAP)

## Deferred Ideas

None.
