---
phase: 14
reviewed_at: 2026-04-25
depth: standard
status: issues_found
critical_count: 1
high_count: 3
medium_count: 7
low_count: 6
info_count: 10
ship_blocker: true
---

# Phase 14 Code Review — Trade Journal Mutation Endpoints

**Verdict:** BLOCK SHIP until CR-01 fixed. The HTMX dashboard forms are non-functional in browsers due to a content-type mismatch — every POST will 400.

## Critical (1) — ship-blocker

### CR-01: HTMX forms send form-encoded; FastAPI handlers expect JSON

**Files:**
- `dashboard.py:927-986` (open form)
- `web/routes/trades.py:320-365` (close-form / modify-form partials)
- `web/routes/trades.py:440-441, 528-529, 594-595` (handler signatures)

**Issue:** All three POST handlers declare the body as a Pydantic model parameter (`def open_trade(req: OpenTradeRequest):`). Without an explicit `Form(...)` annotation, FastAPI parses the body as JSON. The HTMX forms do NOT load the json-enc extension and do NOT set `hx-headers='{"Content-Type": "application/json"}'`. HTMX 1.9.12's default content-type is `application/x-www-form-urlencoded`. Result: every browser-originated POST fails Pydantic schema validation, gets remapped 422→400, and surfaces a generic field-required error to the operator.

**Why critical:** The entire TRADE-05 operator surface (the whole point of Phase 14) is non-functional out of the box on the deployed droplet. The 70 `tests/test_web_trades.py` tests pass because they all use `client.post(..., json=...)` — masking the production bug.

**Fix (recommended):** add HTMX json-enc extension to dashboard.py:
```html
<script src="https://cdn.jsdelivr.net/npm/htmx.org@1.9.12/dist/ext/json-enc.js"
        integrity="sha384-<verified-hash>" crossorigin="anonymous"></script>
```
+ `hx-ext="json-enc"` on each form. Add a regression test that posts form-encoded (NOT JSON) and asserts the handler succeeds.

## High (3)

### HR-01: Pydantic models silently drop unknown fields
`extra='ignore'` default → typoed `new_top` instead of `new_stop` returns 200 with no-op. Add `model_config = ConfigDict(extra='forbid')` to all three request models in `web/routes/trades.py:94-195`.

### HR-02: Lockstep parity broken when peak/trough = 0.0
`dashboard.py:742-744` uses `position.get('peak_price') or position['entry_price']` (truthiness — 0.0 falls through to entry_price). `sizing_engine.py:247-249` uses `is None`. Different stops shown vs computed when peak_price=0.0. Replace `or` with explicit `is None` check.

### HR-03: sizing_engine.step() builds positions without manual_stop
`sizing_engine.py:571-580` constructs new position dicts WITHOUT `manual_stop` key. Schema v3 says it's required. Self-healing on reload (defensive `.get()`), but contract is violated. Add `'manual_stop': None,` to the dict literal.

## Medium (7)

- **MR-01:** `_render_open_success_partial` returns wasted tbody bytes (form has `hx-swap="none"`); cleanest fix returns empty + HX-Trigger only, matching close-success
- **MR-02:** `web/routes/dashboard.py:150-162` regex-based fragment extraction is fragile to attribute order/whitespace drift; loosen regex or use HTML parser
- **MR-03:** `_render_modify_success_partial` returns `<tr> + <div oob>` — same topology REVIEWS HIGH #2 fixed for close-success; modify path retained inline `<div>`-as-tbody-child shape
- **MR-04:** D-15 divergence test missing — add regression that asserts `check_stop_hit` does NOT honor `manual_stop` (locks the intentional behavior)
- **MR-05:** `web/routes/dashboard.py:141` reads `WEB_AUTH_SECRET` from env at request time independently from `_read_auth_secret()` validated at startup — defense-in-depth gap if env mutated post-boot
- **MR-06:** `web/routes/trades.py:278-307` `_render_position_row_partial` renders 6 cells but dashboard's row has 9 — visible misalignment after `cancel-row` GET
- **MR-07:** `tests/conftest.py:_mutate_state_stub` semantically diverges from real `mutate_state` (in-memory mutation, no key-replay simulation); document the gap

## Low (6)

- **LR-01:** `instrument` URL params not validated to Literal['SPI200', 'AUDUSD'] in form/cancel routes
- **LR-02:** 404 from close-form/modify-form/cancel-row triggers `htmx:responseError` with no UI feedback
- **LR-03:** close-form input `min="0"` allows 0 client-side but Pydantic requires `gt=0` → mismatch
- **LR-04:** `OpenTradeRequest._coherence` imports MAX_PYRAMID_LEVEL inside validator body — style nit
- **LR-05:** `_format_pydantic_errors` returns literal `<root>` for completely-empty body errors — unhelpful UX
- **LR-06:** "Open Position" / "Open New Position" copy duplication

## Top 3 concerns

1. **CR-01:** Dashboard forms 400 in production (content-type mismatch). Ship-blocker. Single-line fix + regression test.
2. **HR-01:** Pydantic `extra='forbid'` missing — silently drops typoed fields.
3. **HR-03:** `sizing_engine.step()` violates v3 schema contract (manual_stop key missing on new positions).

## Recommendation

CR-01 must be fixed before milestone close. HR-01..03 are small (each <5 lines) and should be folded into the same fix pass. MR/LR items can go to Phase 16 hardening or v1.2.

Run:
```
/gsd-code-review-fix 14
```

OR apply inline:
1. Add htmx-ext-json-enc script with verified SRI hash + `hx-ext="json-enc"` on each form
2. Add `model_config = ConfigDict(extra='forbid')` to OpenTradeRequest, CloseTradeRequest, ModifyTradeRequest
3. Replace `or` truthiness with `is None` in dashboard.py:742-744
4. Add `'manual_stop': None,` to sizing_engine.py:571-580 position dict literal
5. Add a regression test that POSTs form-encoded data (or json-enc-converted) and asserts the handler accepts it
