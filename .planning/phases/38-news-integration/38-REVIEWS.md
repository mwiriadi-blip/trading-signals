---
phase: 38
reviewers: [gemini, codex, opencode]
reviewed_at: 2026-05-16T00:00:00Z
plans_reviewed: [38-01-PLAN.md, 38-02-PLAN.md, 38-03-PLAN.md, 38-04-PLAN.md]
---

# Cross-AI Plan Review — Phase 38: News Integration

> Running inside Claude Code → claude skipped for independence.
> qwen returned empty output → excluded.
> 3 independent reviewers: Gemini, Codex, OpenCode.

---

## Gemini Review

### Summary

The overarching design accurately adheres to the project's hexagonal architecture and HTMX constraints. The division of labor across the four plans successfully separates pure logic (`news_filter`), I/O adapters (`news_fetcher`), and web routing/state mutations. The security posture regarding XSS, SSRF, and regex safety is excellent. However, there are critical gaps in data flow and type definitions — specifically missing fields in the `NewsItem` type, omitted state rotation logic for the daily expiration of dismissals, and missing filtering logic in the web route.

### Strengths

- Proactive AST guard tests (`_HEX_PATHS_STDLIB_ONLY` + `FORBIDDEN_MODULES_NEWS_FETCHER`) strictly enforce architectural boundary of the pure-math hexagon for `news_filter.py`.
- Good strategy to include specific pre-0.2.55 and post-0.2.55 schema fixtures.
- Strict adherence to `stdlib-only` constraint in Plan 02.
- Proactive ReDoS mitigation via `re.escape()` during `_build_pattern()`.
- Dampener suppression mechanism to reduce false positive alerts.
- Lazy yfinance import pattern ensures fast CLI/boot times.
- Atomic cache writes (`tempfile` → `fsync` → `os.replace`) prevent race conditions.
- Graceful network degradation keeps dashboard resilient.
- HTMX alignment (empty 200 response for element removal, partials).
- Strong security posture: Jinja `autoescape=True`, SSRF mitigation.

### Concerns

- **(LOW) Plan 01:** Ensure `news_classifier_30.json` has a robust mix of TPs, TNs, and edge cases.
- **(LOW) Plan 02:** `has_critical_event` signature uses `list[dict]` — loosely typed, disconnected from `NewsItem` TypedDict.
- **(HIGH) Plan 03:** `NewsItem` TypedDict is missing `title_hash: str`. Plan 03 uses it for dedup and Plan 04 routes dismiss by `{title_hash}`.
- **(MEDIUM) Plan 03:** Cache validation is ambiguous — D-04 suggests checking `mtime`, D-05 defines a `"date"` key in payload. mtime has timezone/server-restart edge cases.
- **(MEDIUM) Plan 03:** `_load_cache` must unpack `headlines` array from `{"date":..., "headlines":[...]}` envelope.
- **(HIGH) Plan 04:** Missing runtime filtering — `GET /news/{market}/panel` does not explicitly filter items in `state['users'][uid]['news_dismissed']` before passing to template.
- **(HIGH) Plan 04:** Missing dismissal auto-expiration — POST dismiss logic does not state it must check `date != today`, reset `hashes`, and update `date` before appending new hash (D-08).
- **(MEDIUM) Plan 04:** Banner (`has_critical_event`) must be applied to the *filtered* list. If user dismisses the triggering headline, banner should disappear.

### Suggestions

- Add `title_hash: str` to `NewsItem` TypedDict.
- Prefer validating cache TTL using the `"date"` field inside parsed JSON rather than filesystem `mtime`.
- Ensure `_load_cache` returns unpacked `headlines` list.
- Add filtering step in `GET /news/{market}/panel` to exclude `title_hash` values in user's active `news_dismissed`.
- Update `dismiss_news_headline` to implement the daily date-check and reset logic inside the atomic `mutate_state` block.
- Evaluate `has_critical_event` only *after* dismissed items are filtered out.

### Risk Assessment

**MEDIUM** — Architecture and security are very strong. Data-flow gaps (missing TypedDict fields, missing filter steps, omitted expiration logic) would cause functional bugs if implemented as written. Fixing requires only minor plan adjustments before execution.

---

## Codex Review

### Summary

The plans are generally well sequenced and cover the main Phase 38 goals: pure classifier first, yfinance adapter second, UI/state integration third, with explicit attention to XSS, SSRF, schema compatibility, per-user dismiss state, and AST isolation. The biggest risks are around mismatches between stated requirements and proposed contracts: `NewsItem` omits `title_hash`, collapse state is underspecified, the route plan may not integrate with `/markets/{m}` as required, and cache files at repo root are operationally fragile. Treat as medium risk unless contract gaps are tightened before implementation.

### Strengths

- Good layering: `news_filter.py` remains pure/stdlib-only, `news_fetcher.py` owns yfinance/cache/normalisation/degradation.
- Schema compatibility plan is explicit and testable for both yfinance shapes.
- Security posture sound: no server-side URL fetching, keyword escaping, AST guards.
- Shared daily per-market cache matches "one fetch, all users" requirement.
- Per-user dismiss state correctly placed under `state['users'][uid]`.
- Precision/recall fixture is a good measurable acceptance gate.
- Graceful degradation on fetch failures is appropriate.

### Concerns

- **(HIGH)** `NewsItem` missing `title_hash` — Plan 03 uses it for dedup; Plan 04 routes dismiss by `{title_hash}`.
- **(HIGH)** Plan 04 adds `GET /news/{market}/panel` but NEWS-01 requires headlines on `/markets/{m}`. Plan does not explicitly state how market dashboard embeds the panel.
- **(HIGH)** Dismiss state shape ambiguity: D-08 specifies `{"date":..., "hashes":[...]}` in `state['users'][uid]['news_dismissed']`, Plan 04 says `news_dismissed[market_id]`. Exact shape must be nailed down.
- **(MEDIUM)** Repo-root cache sidecar files are operational risk — may be read-only, differ by CWD under systemd, overwritten by deploys.
- **(MEDIUM)** `os.replace` prevents partial files but simultaneous cache misses can trigger duplicate yfinance fetches.
- **(MEDIUM)** URL validation not specified — rendering `javascript:`, `data:`, or malformed URLs into anchors is client-side safety issue.
- **(MEDIUM)** Banner with `has_critical_event` doesn't clarify whether dismissed headlines are excluded before classification.
- **(MEDIUM)** Dampener allowlist may reduce recall below ≥0.9 if not carefully tuned.
- **(LOW)** `GET /news/{market}/toggle-collapse` mutates state via GET — semantically wrong; prefetchers/crawlers can trigger it. Use POST.
- **(LOW)** `published_at: int` loses timezone detail. Tests should lock conversion behaviour.
- **(LOW)** Title hash needs normalisation rules — raw hashing treats whitespace/case variants as different headlines.
- **(LOW)** AST skip-missing guard acceptable during wave staging, but must not hide missing modules after Wave 2.

### Suggestions

- Add `title_hash: str` to `NewsItem`; make `_normalise_item()` responsible for stable title normalisation + hash generation.
- Define per-user state shape precisely and document it in plans:
  ```python
  state["users"][uid]["news_dismissed"][market_id] = {"date": "YYYY-MM-DD", "hashes": [...]}
  state["users"][uid]["news_panel_collapsed"][market_id] = bool
  ```
- Change collapse toggle to `POST /news/{market}/toggle-collapse`.
- Explicitly wire panel into `/markets/{m}` — either server-rendered or HTMX-loaded.
- Validate outbound URLs during normalisation — allow only `https://` (+ `http://`); reject `javascript:`, `data:`, relative paths.
- Evaluate critical banner against only non-dismissed headlines.
- Add tests for: malicious URL schemes rejected, unknown market cannot create arbitrary cache paths, cache path cannot path-traverse via `market_id`, daily expiry of dismissed hashes, corrupt cache returns `None`/`[]` and recovers.
- Market ID must be validated against allowlist before building cache paths.

### Risk Assessment

**MEDIUM** — Architecture is sound, phased breakdown is sensible. Priority fixes: add `title_hash` to normalised item model, pin state shape, validate market IDs and URLs, change collapse mutation to POST, explicitly wire panel into `/markets/{m}`.

---

## OpenCode Review

### Summary

Four plans cover the full news integration (foundation → classifier → fetch → UI). Wave ordering is logical. The classifier/stdlib discipline and AST guard patterns correctly follow hexagonal-lite conventions. However, **Plan 04 has a critical architecture mismatch**: the project does NOT use Jinja2 templates — all HTML is rendered via Python f-strings with explicit `html.escape()` — so `templates/partials/news_panel.html` and "Jinja2 autoescape=True" assumptions are incompatible with the actual codebase. Several other gaps exist across plans.

### Strengths

- Hex-lite boundary discipline: Wave 1 correctly puts keyword constants in `system_params.py` (pure stdlib), adds AST-paths + forbidden-module sets for new modules.
- Skip-missing guard pattern for Wave-0 deps correctly mirrors existing test patterns.
- `_build_pattern()` with `re.escape()` prevents regex DoS. Dampener list as override is clean.
- `_normalise_item` dual-branch dispatch correctly handles both yfinance schemas without crashing on unknown schemas.
- `tempfile → fsync → os.replace` mirrors `state_manager/io.py._atomic_write_unlocked` correctly.
- `state['users'][uid]['news_dismissed']` correctly isolates per-user dismiss state.
- SSRF closure: links render in HTML only (client-side clicks), no server-side fetch.
- `return []` on network/parse errors follows project's narrow-catch pattern.

### Concerns

- **(HIGH) Plan 04: Jinja2 assumption is WRONG for this codebase.** Project renders ALL HTML via Python f-strings with explicit `html.escape()` (see `devices.py`, `markets.py`, `dashboard_renderer/`). FastAPI is NOT configured with `Jinja2Templates`. A `templates/partials/news_panel.html` file would be dead code. The news panel must be rendered as an f-string function in Python (matching `dashboard_renderer/components/`), returned via `HTMLResponse(content=...)`.
- **(HIGH) Plan 04: Missing page integration step.** Plan creates `GET /news/{market}/panel` but does NOT mention:
  1. Adding `<div id="news-panel" hx-get="/news/{market_id}/panel" hx-trigger="load">` placeholder to `dashboard_renderer/shell.py:_render_page_body` after `_render_drift_banner`.
  2. Registering `news_route.register(app)` in `web/app.py:create_app()`.
  Without (1), news panel never appears on page load. Without (2), routes don't exist at runtime.
- **(MEDIUM) Plan 04: Missing collapsed-state initial value.** No default specified for first visit. `state['users'][uid].get('news_panel_collapsed', False)` is expected (open by default per D-02). If `state['users'][uid]` doesn't exist yet, route crashes. All existing patterns handle this with `.get()` defaults.
- **(MEDIUM) Plan 03: Cache path relative to CWD.** `_cache_path` returns `Path(f'news_cache_{market_id}.json')`. Works under systemd at repo root, but fragile if service is containerized or run from different directory. Unlike `STATE_FILE` which has an anchored path, news cache paths are fragile.
- **(MEDIUM) Plan 03: CWD cache file naming pollutes repo root.** `news_cache/SPI200.json` directory would be cleaner than flat CWD files.
- **(LOW) Plans 01/02: 30-headline fixture has wide confidence intervals.** ±15-20% at 95% confidence for 30 samples. Acceptable for a "sanity check heuristic" but should be documented as such.
- **(LOW) Plan 02: Unknown market returns False silently.** A `logger.warning` on unknown market_id would aid debuggability.
- **(LOW) Plan 04: Dismiss expiry check not explicit in task description** — plan says it updates `news_dismissed[market_id]` but doesn't state the panel renderer must check `date != today` and treat it as empty.

### Suggestions

1. **Rewrite Plan 04 rendering approach:** Replace `templates/partials/news_panel.html` with a Python rendering function in `dashboard_renderer/components/news.py`. Use `html.escape()` on every dynamic value. Match existing component patterns.
2. **Add page integration to Plan 04:** Add task to modify `dashboard_renderer/shell.py:_render_page_body` to include `<div id="news-panel" hx-get="/news/{active_market}/panel" hx-trigger="load">` after drift banner. Add task to register `news_route.register(app)` in `web/app.py`.
3. **Make collapsed-state and dismiss initialisation explicit in Plan 04:** Both dismiss handler and panel renderer should use: `state.setdefault('users', {}).setdefault(uid, {}).setdefault('news_dismissed', {}).setdefault(market_id, {'date': '', 'hashes': []})`. Panel renderer should check date equality and clear on mismatch before filtering.
4. **Optional: Use `news_cache/` directory** instead of flat CWD files to avoid CWD pollution.
5. **Plan 03: Document the `_get_yf` duplication** — extracting a shared `_yf_loader.py` was deferred to avoid premature abstraction; 6-line duplication is acceptable.

### Risk Assessment

**MEDIUM** — Plans 01-03 are well-structured. Primary risks in Plan 04: Jinja2 assumption (HIGH — template is dead code and route crashes with 500 if Jinja2Templates not configured), missing page integration (MEDIUM — panel never appears). Both are fixable in implementation; foundation (classifier, fetcher, cache, state isolation) is sound.

---

## Consensus Summary

### Agreed Strengths (2+ reviewers)

- **Hex-lite boundary discipline** — keyword constants in `system_params.py`, AST guard extensions for both new modules, `_HEX_PATHS_STDLIB_ONLY` + `FORBIDDEN_MODULES_NEWS_FETCHER` are correct and well-structured.
- **yfinance schema normalisation** — dual-branch dispatch (`uuid` in item → pre-0.2.55; `content` in item → post-0.2.55) is explicit, testable, and handles unknown schemas gracefully.
- **Atomic cache writes** — `tempfile → fsync → os.replace` mirrors the existing state_manager pattern correctly.
- **`re.escape()` in classifier** — prevents regex DoS; word-boundary matching is appropriate for single-keyword-threshold design.
- **Per-user dismiss state** — correctly scoped to `state['users'][uid]`; daily auto-expiry design is clean.
- **Graceful degradation** — `return []` on network/parse errors follows project's narrow-catch pattern.
- **SSRF closure** — no server-side URL prefetch; links only render in client HTML.

### Agreed Concerns (raised by 2+ reviewers)

1. **[HIGH] `title_hash: str` missing from `NewsItem` TypedDict** (Gemini + Codex) — Plan 03 uses it for dedup, Plan 04 routes dismiss by `{title_hash}`; must be part of the normalised item contract.

2. **[HIGH] Plan 04 missing page integration into `/markets/{m}`** (Codex + OpenCode) — Plan 04 creates the `/news/{market}/panel` route but doesn't state how it gets embedded in the market page. Either a server-rendered placeholder `<div hx-get="/news/{market_id}/panel" hx-trigger="load">` in `dashboard_renderer/shell.py` (OpenCode) or explicit documentation of the HTMX wiring (Codex). Without this, news panel never appears.

3. **[HIGH] Banner must evaluate only non-dismissed headlines** (Gemini + Codex) — if user dismisses the triggering headline, the banner must disappear. `has_critical_event` must run on the filtered list, not the full cached list.

4. **[MEDIUM] Cache TTL: mtime vs JSON `date` field ambiguity** (Gemini + Codex) — D-05 defines a `date` key in the cache JSON; this is more reliable than filesystem mtime (which has timezone/restart edge cases). Use the JSON `date` field as the authoritative TTL check.

5. **[MEDIUM] Collapse state toggle via GET** (Codex) — `GET /news/{market}/toggle-collapse` mutates server-side state. Must be POST.

6. **[MEDIUM] Dismiss auto-expiration logic not explicit in Plan 04** (Gemini + OpenCode) — when dismiss handler runs, it must: (a) check if `news_dismissed[market_id].date != today`; (b) if so, reset `hashes = []` and update `date`; (c) then append new hash. This is D-08 but it's implied, not stated as a task.

### Divergent Views

- **Rendering approach (Gemini vs OpenCode):** Gemini assumes Jinja2 templates are valid (project-level assumption). OpenCode reviewed the actual codebase and found it uses Python f-strings + `html.escape()`, not Jinja2Templates. **OpenCode's finding takes precedence** — Plan 04 must use the f-string rendering pattern, not template files.

- **Cache path fragility (Codex: operational risk, OpenCode: acceptable with caveat):** Codex flags repo-root sidecar files as risky for containerized deploys. OpenCode notes it follows the existing `state.json` / `auth.json` pattern so it's consistent. The CWD anchor is acceptable given systemd deploy path, but should be documented.

- **URL validation scope (Codex: validate during normalisation, OpenCode: render-time is sufficient):** Codex recommends validating URLs in `_normalise_item()` (reject `javascript:`, `data:`, etc.). OpenCode considers SSRF closed by render-only approach. Codex is correct for defence-in-depth; filtering at normalisation is low-cost and closes client-side risks.

---

## Action Items Before Execution

| # | Priority | Plan | Fix |
|---|----------|------|-----|
| 1 | HIGH | Plan 03 | Add `title_hash: str` to `NewsItem` TypedDict; `_normalise_item` computes it |
| 2 | HIGH | Plan 04 | Replace Jinja2 template approach with Python f-string rendering function (verify actual rendering pattern first) |
| 3 | HIGH | Plan 04 | Add task: wire HTMX placeholder into `dashboard_renderer/shell.py` and register route in `web/app.py` |
| 4 | HIGH | Plan 04 | Add task: filter dismissed headlines before passing to template AND before calling `has_critical_event` |
| 5 | HIGH | Plan 04 | Add task: implement D-08 dismiss auto-expiry (date check → reset hashes → append) inside `mutate_state` |
| 6 | MEDIUM | Plan 03 | Use JSON `"date"` field (not mtime) as authoritative TTL check |
| 7 | MEDIUM | Plan 03 | Validate market_id against allowlist before building cache path (path traversal) |
| 8 | MEDIUM | Plan 03 | Validate outbound URL scheme in `_normalise_item` (allow only `https://`, `http://`) |
| 9 | MEDIUM | Plan 04 | Change `GET /news/{market}/toggle-collapse` → `POST` |
| 10 | MEDIUM | Plan 04 | Add `.get()` defaults for `news_dismissed` and `news_panel_collapsed` on first visit |
| 11 | LOW | Plan 02 | Add `logger.warning` for unknown `market_id` in `classify_headline` |
| 12 | LOW | Plan 01/02 | Document 30-headline fixture as "sanity check, not statistically significant" |

To incorporate feedback into planning:

```
/gsd-plan-phase 38 --reviews
```
