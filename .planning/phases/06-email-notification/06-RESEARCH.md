# Phase 6: Email Notification — Research

**Researched:** 2026-04-22
**Domain:** Transactional HTML email (Resend HTTPS API) composed by a new hex-lite I/O adapter (`notifier.py`)
**Confidence:** HIGH on API shape, state schema, Phase 5 patterns; MEDIUM on Resend rate-limit nuances (docs shifted 2→5 rps in late 2024–2025); MEDIUM on Gmail web dark-mode inversion edge cases

---

## Summary

- **Resend API is stable and minimal** — `POST https://api.resend.com/emails` with `{from, to, subject, html}` JSON body and `Authorization: Bearer re_xxx`. `to` accepts either a single string or a `string[]` (max 50). Successful response is `200 OK` with `{"id": "<uuid>"}`. Error codes split cleanly into retryable (429, 500) vs fail-fast (400/401/403/422) — CONTEXT D-12's 3-retry-with-10s-backoff policy is correctly tuned; 429 needs special handling (it's a 4xx but IS retryable per Resend's own guidance).
- **Phase 5's golden-HTML snapshot pattern transfers directly to Phase 6.** `tests/test_dashboard.py` and `tests/regenerate_dashboard_golden.py` are the authoritative templates. `FROZEN_NOW = PERTH.localize(datetime(2026, 4, 22, 9, 0))` is already the project-wide freeze-time fixture; `pytest-freezer` is pinned at 0.4.9. Byte-stable renders depend on `newline='\n'`, `sort_keys=True` in any JSON payloads, and strict UTF-8 encoding at write time.
- **State schema for Phase 6 reads is fully locked by Phase 4 D-08 + G-2 + B-1 retrofits.** `state['signals'][key]` is a dict with `signal`, `signal_as_of`, `as_of_run`, `last_scalars`, `last_close`. Trade log has the 12-field shape (11 validated by `_validate_trade` + `net_pnl` appended by `record_trade` per D-20). `equity_history` is a list of `{date, equity}` dicts. All confirmed in source.
- **`run_daily_check` returns only `rc: int` today.** Phase 6 needs the post-compute `state` dict + `old_signals` dict without a second `load_state` call (because `--test` didn't persist). **Recommended refactor:** change return to `(rc, state, old_signals)`. Impact: ~3 lines in `main.py`, 2 test files touched (`tests/test_main.py` callers — all use `main(...)` not direct `run_daily_check`, so actual churn is minimal). Module-level `_last_run_context` is rejected — global mutable state creates flakiness in parallel test runs.
- **`_send_email_never_crash` is a verbatim mirror of Phase 5's `_render_dashboard_never_crash`** (main.py:94–112). Import-inside-try per C-2 pattern; catches `Exception`; logs `[Email] WARN`; never propagates. The pattern is already in the codebase — this is a copy-paste-rename operation.
- **`load_dotenv` is NOT called anywhere in the codebase today.** `os.environ.get('RESEND_API_KEY')` will return `None` locally unless the operator sets the env var at shell level or Phase 7 adds `load_dotenv()`. CONTEXT D-13 gracefully degrades to `last_email.html` fallback, which makes this non-blocking for Phase 6. No `.github/workflows/` directory exists yet (Phase 7 scope).

**Primary recommendation:** Build `notifier.py` as a self-contained hex mirroring `dashboard.py` structurally — duplicate `_atomic_write_html` rather than extracting to state_manager (zero coupling, ~25 lines is acceptable). Refactor `run_daily_check` to return `(rc, state, old_signals)`. Lean on Phase 5's golden-snapshot + regenerator pattern verbatim.

---

## User Constraints (from CONTEXT.md)

### Locked Decisions (D-01 … D-15)

- **D-01:** New `notifier.py` at repo root — fully isolated from `dashboard.py`. Public API: `compose_email_subject`, `compose_email_body`, `send_daily_email`, `_post_to_resend`. Forbidden imports: `signal_engine`, `sizing_engine`, `data_fetcher`, `main`, `dashboard`, `numpy`, `pandas`. AST blocklist extension in Wave 0 (`FORBIDDEN_MODULES_NOTIFIER`).
- **D-02:** Full duplication of formatters in `notifier.py` (`_fmt_currency_email`, `_fmt_percent_signed_email`, `_fmt_percent_unsigned_email`, `_fmt_pnl_with_colour_email`, `_fmt_em_dash_email`, `_fmt_last_updated_email`, `_fmt_instrument_display_email`). Small retrofit: palette constants (`_COLOR_BG`, `_COLOR_SURFACE`, etc.) move from `dashboard.py` to `system_params.py` as shared constants; `dashboard.py` + `notifier.py` both import from there.
- **D-03:** Waves: 0 scaffold → 1 render+format → 2 dispatch+integration (PHASE GATE).
- **D-04:** Subject template `{emoji} {YYYY-MM-DD} — SPI200 {SIG}, AUDUSD {SIG} — Equity ${X,XXX}`. 🔴 on change, 📊 on no-change. `[TEST]` prefix before emoji for `--test`. Equity rounded to whole dollar via `int(round(account))`.
- **D-05:** `old_signals` captured in `main.py` BEFORE `run_daily_check` mutates state; passed to `send_daily_email` as `{'^AXJO': int_or_none, 'AUDUSD=X': int_or_none}`. Backward-compat with both int and dict signal shapes.
- **D-06:** First-run / no-previous-signal = NO CHANGE. `any_signal_changed = any(old is not None and old != new for ...)`. First email shows 📊.
- **D-07:** Table-based layout, 600px-max wrapper, `role="presentation"` on layout tables, inline CSS only, belt-and-braces `bgcolor` attributes.
- **D-08:** Mobile via `max-width:600px;width:100%` (fluid-hybrid); NO `@media` query.
- **D-09:** MUST-render clients: Gmail web + iOS Mail. Nice-to-have: Gmail Android, Outlook desktop, Apple Mail macOS, ProtonMail.
- **D-10:** 7 body sections in order: Header → ACTION REQUIRED (conditional) → Signal status table → Open positions table (7 cols, no Pyramid) → Today's P&L + Running equity rollup → Last 5 closed trades (5 cols) → Footer.
- **D-11:** ACTION REQUIRED copy with `━━━ ACTION REQUIRED ━━━` headline, red left-border `border-left:4px solid #ef4444`, padding `12px 16px`, per-instrument diff paragraphs with `→` arrows.
- **D-12:** Retry policy: 3 retries, 10s backoff, 30s timeout. 4xx fail-fast (except 429 — see §1 below); 5xx + Timeout + ConnectionError retry.
- **D-13:** Missing `RESEND_API_KEY` → write `last_email.html` + log WARN + return 0. `_atomic_write_html` duplicated in notifier.py (researcher recommendation below).
- **D-14:** Config: `_EMAIL_FROM = 'signals@carbonbookkeeping.com.au'` hardcoded; `_EMAIL_TO_FALLBACK = 'marc@carbonbookkeeping.com.au'` (operator-confirmed placeholder); `SIGNALS_EMAIL_TO` env var overrides fallback.
- **D-15:** Dispatch wiring — `main.py` replaces Phase 4 stubs; `_send_email_never_crash` mirrors `_render_dashboard_never_crash`. `run_daily_check` refactored to return `(rc, state, old_signals)` — researcher concurs, details in §9.

### Claude's Discretion

- Class hierarchy for exceptions (`ResendError` surfaced; child classes nice-to-have).
- `_atomic_write_html` duplicate vs extract (recommendation in §7: duplicate).
- Test fixture shapes for `sample_state_with_change.json` / `sample_state_no_change.json` / `empty_state.json`.
- Whether `compose_email_body` takes pre-computed "today's change" param or derives inline (recommendation: derive inline).
- Full ACTION REQUIRED diff truth table copy (6 cases per instrument, locked in UI-SPEC §2).
- `.env.example` contents (at minimum `RESEND_API_KEY=re_xxx` and `SIGNALS_EMAIL_TO=marc@...`).
- Whether Wave 2 commits `last_email.html` as fixture or regenerates at test time (recommendation: regenerate).

### Deferred Ideas (OUT OF SCOPE)

- Signal-history sparkline
- Email preview URL in Resend dashboard
- Multi-recipient distribution list
- `color-scheme: dark` meta (belt-and-braces bgcolor is enough for v1 per CONTEXT D-09)
- Gmail Markup for Actions
- PDF attachment of dashboard
- Per-instrument email mute (v2 V2-DEL-02)
- Slack webhook fallback (v2 V2-DEL-01)

---

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| NOTF-01 | Email sends via Resend HTTPS API (`POST https://api.resend.com/emails`) with Bearer token | §1 Resend API shape verified via official docs |
| NOTF-02 | Subject shows signals + P&L + date, 🔴 on change and 📊 when unchanged | §2 emoji rendering OK for MUST-render clients; §6 state schema provides `signal`, `account`, `run_date` |
| NOTF-03 | HTML body uses inline CSS only (dark theme palette) | UI-SPEC + CONTEXT D-07/D-08 lock the layout; §2 client quirks documented |
| NOTF-04 | 7 body sections in locked order | §6 state schema confirms every field the body reads |
| NOTF-05 | ACTION REQUIRED block (red border) on signal change | §9 `old_signals` plumbing + §6 state['trade_log'][-1] source for closed-position details |
| NOTF-06 | Mobile-responsive at 375px viewport | §2 iOS Mail `max-width` + `<meta viewport>` verified |
| NOTF-07 | Resend API failure logs error, does NOT crash | §8 `_send_email_never_crash` mirror pattern + §1 retry policy |
| NOTF-08 | Missing `RESEND_API_KEY` degrades gracefully (writes `last_email.html`) | §3 env handling + §7 `_atomic_write_html` pattern |
| NOTF-09 | All user-visible values escaped | §12 `html.escape` discipline per Phase 5 D-15 |

Plus Phase 6 completion slices of CLI-01 (`--test` sends `[TEST]`-prefixed email, no state mutation) and CLI-03 (`--force-email` sends today's email immediately).

---

## 1. Resend API

**Endpoint.** `POST https://api.resend.com/emails` — verified against https://resend.com/docs/api-reference/emails/send-email `[CITED: Resend docs]`.

**Request body (minimal shape for HTML email):**

```json
{
  "from": "signals@carbonbookkeeping.com.au",
  "to": ["marc@carbonbookkeeping.com.au"],
  "subject": "🔴 2026-04-22 — SPI200 LONG, AUDUSD FLAT — Equity $101,234",
  "html": "<!DOCTYPE html>..."
}
```

- `to` accepts EITHER `"single@email.com"` (string) OR `["a@x.com", "b@x.com"]` (array, max 50) `[CITED]`. CONTEXT D-12's `{'to': [to_addr]}` (array-with-one-string) is the safer form — consistent shape regardless of recipient count if v2 adds cc/multi-recipient.
- `from` must be a verified Resend sender domain (PROJECT.md confirms `signals@carbonbookkeeping.com.au` is verified — skip DKIM/SPF work in Phase 6).
- `html` is the full inline-CSS HTML document.
- `text` is optional — CONTEXT does not specify a plain-text alternate. Gmail + iOS Mail both render the `html` field fine; skipping the `text` key is acceptable `[VERIFIED: Resend docs allow HTML-only]`.

**Headers:**

```
Authorization: Bearer re_xxxxxxxxx
Content-Type: application/json
```

- `Content-Type: application/json` is auto-set by `requests.post(..., json=payload)` — confirmed by Python `requests` library behavior. No explicit Content-Type header needed, but CONTEXT D-12's explicit `Content-Type: application/json` in the `headers` dict is safe and idiomatic `[VERIFIED: python-requests library]`.

**Success response.** `HTTP 200` with body `{"id": "<uuid>"}` (e.g. `{"id": "49a3999c-0ce1-4ea6-ab68-afcd6dc2e794"}`) `[CITED]`. **No 202.** Phase 6 does not need to parse the response body — discard it after checking status.

**Error codes (authoritative, verified against https://resend.com/docs/api-reference/errors):**

| Status | Code(s) | Retry? | Action |
|--------|---------|--------|--------|
| 400 | `invalid_idempotency_key`, `validation_error` | NO | Fail fast, log `[Email] WARN 400 <body>` |
| 401 | `missing_api_key`, `restricted_api_key` | NO | Fail fast — bad credential |
| 403 | `invalid_api_key`, `validation_error` (unverified domain) | NO | Fail fast |
| 404 | `not_found` | NO | Code bug (wrong endpoint) |
| 405 | `method_not_allowed` | NO | Code bug |
| 409 | `invalid_idempotent_request`, `concurrent_idempotent_requests` | NO | Phase 6 doesn't use idempotency keys |
| 422 | `invalid_from_address`, `invalid_parameter`, `missing_required_field` | NO | Fail fast |
| 429 | `rate_limit_exceeded`, `daily_quota_exceeded`, `monthly_quota_exceeded` | **YES** | Retry with backoff — CONTEXT D-12 must special-case 4xx-except-429 |
| 451 | `security_error` | NO | Fail fast |
| 500 | `application_error`, `internal_server_error` | YES | Retry with backoff |

`[CITED: resend.com/docs/api-reference/errors]`

**CRITICAL — 429 retry handling (downstream note from CONTEXT).** CONTEXT D-12's retry loop raises `ResendError` on any 4xx `(400 <= resp.status_code < 500)`. This fails-fast on 429 — but 429 IS retryable per Resend's own guidance. **Recommendation:** special-case 429 in the retry tuple:

```python
if 400 <= resp.status_code < 500 and resp.status_code != 429:
  raise ResendError(f'4xx from Resend: {resp.status_code} {resp.text[:200]}')
resp.raise_for_status()  # 429 + 5xx raise HTTPError → caught by retry tuple
```

Alternatively, explicitly treat 429 as transient:

```python
if resp.status_code == 429:
  raise requests.exceptions.HTTPError('429 rate-limit', response=resp)
if 400 <= resp.status_code < 500:
  raise ResendError(f'4xx from Resend: {resp.status_code} {resp.text[:200]}')
resp.raise_for_status()
```

Either form works; surface to planner as a must-address point.

**Rate limits.** `[MEDIUM confidence — docs state 5 rps "team-wide", older changelog mentions 2 rps per-customer]` Per https://resend.com/docs/api-reference/introduction the current default is "**5 requests per second per team**" across all API keys. An older changelog (November 2024) mentioned 2 rps per customer. Phase 6 sends at most 1 email per day per run, so rate-limit risk is near zero in normal operation. However, a developer testing `--force-email` in a tight loop could trip it — the retry loop's flat 10-second backoff is the safety net.

**`Retry-After` header.** Resend docs **do NOT document** a `Retry-After` header on 429 responses `[CITED]`. CONTEXT D-12's fixed 10-second backoff is acceptable; no need to parse the header.

**Idempotency keys.** Supported via `Idempotency-Key: <unique-per-request-string>` header. Keys expire after 24h; max 256 chars. **Phase 6 doesn't need this** — we send at most 1 email per daily run, and a 409 conflict on a duplicate key would fail-fast under CONTEXT D-12. Recommendation: do NOT set `Idempotency-Key` in Phase 6. Phase 8's crash-email ERR-04 may revisit if dedup is needed.

**UTF-8 / emoji encoding.** `requests.post(json=payload)` uses Python's `json.dumps(payload)` with **`ensure_ascii=True` by default** `[VERIFIED: json stdlib]`. This means 🔴 (U+1F534) and 📊 (U+1F4CA) are serialized as `\ud83d\udd34` and `\ud83d\udccA` JSON escape sequences in the wire body, NOT raw UTF-8 bytes. **This is fine** — JSON parsers (including Resend's) unescape these back to the correct Unicode code points per RFC 8259. Gmail and iOS Mail receive the emoji in the subject line and render them as color glyphs. `[ASSUMED]` that Resend correctly unescapes `\uXXXX` sequences — this is standard JSON behavior and would break every other client if not; not worth special-casing.

**If you want raw UTF-8 bytes on the wire** (e.g., for debugging with `tcpdump`), pass `data=json.dumps(payload, ensure_ascii=False).encode('utf-8')` + explicit `Content-Type: application/json; charset=utf-8` header. **NOT NEEDED for Phase 6** — default `json=payload` behavior works.

---

## 2. Gmail + iOS Mail Client Quirks

`[MEDIUM confidence — compiled from multiple sources including Resend docs, Can I Email, and community wisdom]`

**Gmail web (Chrome/Safari desktop).**

- **Table-based layout with `<table role="presentation">`.** Renders correctly. `role="presentation"` is necessary for screen readers to skip layout tables `[CITED: W3C ARIA spec]`.
- **`bgcolor="#0f1117"` attribute.** Gmail web respects `bgcolor` alongside inline `style="background:#0f1117"`. Belt-and-braces is the correct pattern `[VERIFIED: Gmail CSS reference]`.
- **Dark theme handling.** Gmail web auto-dark-mode (user setting, macOS system dark mode) may attempt to "lighten" our already-dark email. The `<meta name="color-scheme" content="dark only">` and `<meta name="supported-color-schemes" content="dark">` in `<head>` (UI-SPEC Color section Layer 2 + 3) signal "already dark, leave alone." Gmail web respects `color-scheme: dark` but NOT always `supported-color-schemes`. Residual risk: Gmail Android under system dark mode may slightly shift LONG green (`#22c55e`) to a darker hue — readable, not mis-signal. Documented in UI-SPEC as accepted limitation.
- **Emoji in subject.** Gmail web renders 🔴 and 📊 as color glyphs cross-platform (macOS native emoji font; Windows via Segoe UI Emoji). No known stripping of these specific code points on Gmail web in the last ~3 years `[ASSUMED based on widespread usage]`.
- **`<sub>` / `<sup>` tags.** Gmail web renders them; Outlook strips them inconsistently. UI-SPEC §3 locks "no `<sub>` in email" (dashboard uses `Mom<sub>1</sub>`; email uses a footnote `Mom reads as 21d · 63d · 252d`). This is the right call.

**iOS Mail (iPhone).**

- **`max-width:600px;width:100%` fluid-hybrid.** Respected. Content fluidly scales from 600px down to the viewport width (375px iPhone SE, 390px iPhone 14, etc.) `[VERIFIED: Can I Email / iOS Mail matrix]`.
- **`<meta name="x-apple-disable-message-reformatting">`.** Suppresses iOS Mail's auto-reformatting (which can break hand-tuned table layouts on narrow viewports) `[CITED: Apple Mail developer docs]`. **UI-SPEC does not currently include this** — recommend adding to `<head>` alongside the other meta tags. Small, zero downside, prevents a known pitfall.
- **`<meta name="viewport" content="width=device-width, initial-scale=1">`.** Required for iOS Mail to render at native scale. UI-SPEC §D-07 confirms this is in the template.
- **Auto-detection (phone numbers, addresses, dates).** iOS Mail auto-linkifies dates like `2026-04-22`, phone numbers, and addresses — underlines them in blue-ish tint. This would visually clash with our dark theme. **Mitigation:** wrap the date in a `<span>` with `color:inherit; text-decoration:none;` OR use the `<meta name="format-detection" content="telephone=no,date=no,address=no,email=no">` tag in `<head>`. **Recommend adding format-detection meta tag** to the email template. Zero-cost defense.
- **Dark mode gotchas.** iOS Mail respects `color-scheme: dark` meta. Apple Mail macOS respects `supported-color-schemes` meta. Both will leave an already-dark email alone if these tags are present `[CITED: Apple Mail developer docs]`.

**Emoji rendering on Gmail web.**

- 🔴 (U+1F534 RED CIRCLE): Color glyph on all modern Gmail web clients (macOS, Windows 10+, Linux via Noto Color Emoji). **No known tofu / strip.**
- 📊 (U+1F4CA BAR CHART): Same — widely supported since Unicode 6.0 (2010). No known rendering issue.
- **Windows Chrome on Windows 7/8** (legacy, <5% of Gmail web user base): may render as monochrome via Segoe UI Symbol. Still distinguishable. `[ASSUMED — legacy Windows is long out of scope for v1]`.

**Fluid-hybrid at 375px.**

- Gmail web renders below 600px by using its own responsive wrapper (fine, table fluidly inherits).
- iOS Mail at 375px: tested pattern is documented in Campaign Monitor guides. `max-width:600px` on the outer content table, `width="100%"` on inner section tables, all cell padding in absolute pixels (UI-SPEC Spacing Scale uses 4/8/12/16/20/24/32 — all fine). No horizontal scroll.

**Recommended `<head>` additions (beyond CONTEXT D-07's current spec):**

```html
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="dark only">
  <meta name="supported-color-schemes" content="dark">
  <meta name="x-apple-disable-message-reformatting">
  <meta name="format-detection" content="telephone=no,date=no,address=no,email=no">
  <title>Trading Signals — {date}</title>
</head>
```

The last two (x-apple-disable-message-reformatting, format-detection) are not explicitly called out in CONTEXT D-07 but are low-risk high-value additions. Surface to planner.

---

## 3. Environment Variables

**Does any module call `load_dotenv()` today?** `[VERIFIED: grep -rn 'load_dotenv\|dotenv' --include='*.py']` — **NO.** `python-dotenv` is not imported anywhere in `main.py`, `state_manager.py`, `notifier.py` (doesn't exist yet), or any existing module. The only references to `dotenv` are in the `FORBIDDEN_MODULES` lists in `tests/test_signal_engine.py` — blocking its import from Phase 1/2/3 hex modules.

**`python-dotenv` is NOT in `requirements.txt`** — only `numpy==2.0.2`, `pandas==2.3.3`, `pytest==8.3.3`, `pytest-freezer==0.4.9`, `yfinance==1.2.0`, `ruff==0.6.9`. **Phase 6 must not add new deps (CONTEXT scope boundary).** Phase 7 scope explicitly includes dotenv wiring + GitHub Actions secret handling (per ROADMAP §Phase 7 + SCHED-07).

**What happens when operator runs `python main.py --force-email` locally today?**

1. `os.environ.get('RESEND_API_KEY')` returns `None` unless the operator has exported it via `export RESEND_API_KEY=re_xxx` before running.
2. CONTEXT D-13 fallback triggers: write `last_email.html` + log `[Email] WARN RESEND_API_KEY missing — wrote last_email.html`.
3. Operator opens `last_email.html` in a browser to preview — graceful.

**Recommendation for Phase 6:** do NOT add `load_dotenv()` in Phase 6. Let the missing-key fallback handle the local-dev case. Phase 7 owns the dotenv wiring. Document the expectation in Phase 6's `.env.example` (Wave 0 scaffolds this file):

```
# .env.example
# Phase 6 reads RESEND_API_KEY from the process environment.
# Phase 7 will call load_dotenv() at startup to auto-load this file.
# For now, export manually before running:
#   export RESEND_API_KEY=re_xxx
#   export SIGNALS_EMAIL_TO=marc@example.com

RESEND_API_KEY=re_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
SIGNALS_EMAIL_TO=marc@example.com
```

**GitHub Actions secrets pattern.** `[VERIFIED: ls .github/ returns no directory]` — `.github/workflows/` doesn't exist yet. Phase 7 creates it. Standard GHA secrets pattern (for planner to surface to Phase 7, not Phase 6):

```yaml
# .github/workflows/daily.yml (Phase 7)
jobs:
  run:
    steps:
      - name: Run
        env:
          RESEND_API_KEY: ${{ secrets.RESEND_API_KEY }}
          SIGNALS_EMAIL_TO: ${{ secrets.SIGNALS_EMAIL_TO }}
        run: python main.py --once
```

Phase 6 is forward-compatible with this — no code changes needed when Phase 7 lands.

---

## 4. Golden-HTML Snapshot Stability

**Phase 5's exact pattern (authoritative template for Phase 6):**

- `tests/fixtures/dashboard/golden.html` + `golden_empty.html` — byte-equal comparison targets (committed to git).
- `tests/fixtures/dashboard/sample_state.json` + `empty_state.json` — input fixtures.
- `tests/regenerate_dashboard_golden.py` — NEVER invoked by CI; operator-only. Run manually when dashboard render intentionally changes.
- `tests/test_dashboard.py::TestGoldenSnapshot::test_golden_snapshot_matches_committed` — byte-equal assertion: `assert rendered_bytes == golden_bytes`.
- `FROZEN_NOW = PERTH.localize(datetime(2026, 4, 22, 9, 0))` — module-level in both `test_dashboard.py` and `regenerate_dashboard_golden.py`. C-1 reviews lock: **always** `PERTH.localize(dt)`, **never** `datetime(..., tzinfo=PERTH)` (pytz LMT offset bug).

**Phase 6 mirror structure:**

```
tests/
├── test_notifier.py                                    # 6 test classes (mirror Phase 5 D-13)
├── regenerate_notifier_golden.py                       # operator-only regenerator
└── fixtures/
    └── notifier/
        ├── sample_state_with_change.json               # SPI200 LONG→SHORT transition
        ├── sample_state_no_change.json                 # both instruments unchanged
        ├── empty_state.json                            # reset_state() output
        ├── golden_with_change.html                     # byte-equal snapshot
        ├── golden_no_change.html
        └── golden_empty.html
```

**Byte-stability drivers (all apply to Phase 6):**

| Concern | Mitigation | Source |
|---------|-----------|--------|
| Line endings | `newline='\n'` on tempfile (dashboard.py:1010) | `_atomic_write_html` |
| Dict iteration order | Python 3.7+ preserves insertion order; no explicit sorting needed | CPython semantics |
| Emoji byte sequence | 🔴 = `f0 9f 94 b4` (4 bytes UTF-8); 📊 = `f0 9f 93 8a`. Stable across Python versions. | Unicode/UTF-8 spec |
| `datetime.now()` drift | `FROZEN_NOW` module constant passed as `now=` parameter | dashboard.py:1054 defaults |
| JSON payload ordering (N/A to email body; email has no JSON) | `sort_keys=True` in state_manager.save_state | state_manager.py:368 |
| `f-string` locale dependence | Python f-strings do NOT apply locale; `f'{1234:,.2f}'` always produces `1,234.00` regardless of LANG/LC_ALL `[VERIFIED: Python f-string spec]` | stdlib |
| `html.escape` output | Deterministic — same input always produces same output | stdlib |
| Whitespace in multi-line templates | Explicit `\n` in f-strings; no trailing-whitespace on section dividers | Phase 5 dashboard.py:586–594 pattern |

**Emoji byte-stability on Python 3.11.** `[VERIFIED]` — `'🔴'.encode('utf-8')` produces `b'\xf0\x9f\x94\xb4'` deterministically. `'📊'.encode('utf-8')` produces `b'\xf0\x9f\x93\x8a'`. No source of drift.

**Freeze-time.** `pytest-freezer==0.4.9` is already pinned (`requirements.txt:4`). Phase 4 tests use `@pytest.mark.freeze_time('2026-04-21 09:00:03+08:00')` (per 04-03-SUMMARY.md). Phase 5 uses the simpler `now=FROZEN_NOW` parameter injection. Phase 6 **should use parameter injection** (Phase 5 approach) because `compose_email_body(state, old_signals, now)` is already planned with explicit `now` — no need for `pytest-freezer` decorator on body-composition tests. Dispatch tests (`TestSendDispatch`) may use `freeze_time` if they need to drive `datetime.now()` inside `send_daily_email` — unlikely, since `now` is also passed through.

**F-string locale.** `f'{1234:,.2f}'` always renders `1,234.00` in Python regardless of `LC_ALL` / `LANG` env vars. Python's format spec is locale-independent unless you explicitly use `'n'` format (e.g., `f'{1234:n}'`) which IS locale-aware. **Phase 6 uses `,` (comma-thousands) and `.` (decimal-point), which are locale-independent under `,.2f` spec.** `[VERIFIED: PEP 3101 format spec]`

**Regenerator script template (mirror `tests/regenerate_dashboard_golden.py:1–50`):**

```python
'''Offline email-HTML golden regenerator for Phase 6 tests.

Per CONTEXT D-09 (Phase 6 follows Phase 5 pattern): this script is
NEVER invoked by CI. Run manually when the email render
intentionally changes:

  .venv/bin/python tests/regenerate_notifier_golden.py
'''
import json, sys
from datetime import datetime
from pathlib import Path
import pytz

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from notifier import compose_email_body  # noqa: E402

FIXTURES_DIR = ROOT / 'tests' / 'fixtures' / 'notifier'
PERTH = pytz.timezone('Australia/Perth')
FROZEN_NOW = PERTH.localize(datetime(2026, 4, 22, 9, 0))

SCENARIOS = [
  ('sample_state_with_change.json', 'golden_with_change.html', {'^AXJO': 1, 'AUDUSD=X': -1}),
  ('sample_state_no_change.json', 'golden_no_change.html', {'^AXJO': 1, 'AUDUSD=X': 0}),
  ('empty_state.json', 'golden_empty.html', {'^AXJO': None, 'AUDUSD=X': None}),
]

for state_name, golden_name, old_signals in SCENARIOS:
  state = json.loads((FIXTURES_DIR / state_name).read_text())
  html = compose_email_body(state, old_signals, FROZEN_NOW)
  (FIXTURES_DIR / golden_name).write_text(html, encoding='utf-8', newline='\n')
  print(f'[regen] wrote {golden_name}')
```

**Double-run gate (operator-facing sanity check):** run the regenerator twice in a row and assert `git diff --exit-code tests/fixtures/notifier/`. Phase 5 uses this implicitly via the byte-equal test + commit discipline. No explicit "double-run" assertion in Phase 5 — it's an operator-trust pattern. Phase 6 follows.

---

## 5. `requests.post` Semantics

**`Content-Type` auto-set?** `[VERIFIED: python-requests source]` — YES. `requests.post(url, json=payload, ...)` sets `Content-Type: application/json` automatically. Explicit `Content-Type` in the `headers` dict (as CONTEXT D-12 does) is redundant but harmless — the explicit header wins over the auto-set one.

**`ensure_ascii` default?** `[VERIFIED: requests.models.PreparedRequest.prepare_body]` — `requests` calls `complexjson.dumps(payload)` where `complexjson` defaults to Python's stdlib `json`. `json.dumps()` defaults to `ensure_ascii=True`. So emoji in `subject` are wire-serialized as `\uXXXX` JSON escapes. Resend unescapes correctly on receipt (standard JSON parser behavior). **No practical impact on Phase 6.**

**`timeout=30` semantics.** `[VERIFIED: requests docs]`:

- `timeout=30` (single float) = **read timeout only**, with the connect timeout defaulting to None (effectively infinite, until OS-level TCP timeout kicks in at ~2 minutes on most Linux systems). Not ideal.
- `timeout=(connect_s, read_s)` (tuple) = both timeouts separately configured.
- **Recommendation:** change CONTEXT D-12's `timeout=30` to `timeout=(5, 30)` — 5s connect, 30s read. More robust against DNS / TCP handshake failures. Optional; the single-value form works but a slow DNS could hang the whole run for ~minutes.

**Alternative:** keep `timeout=30` as single value (simpler, matches `data_fetcher.py:101`'s `timeout=10` pattern). Planner's call.

**Total worst-case wait** under CONTEXT D-12's retry loop:

- `retries=3`, `backoff_s=10`, `timeout_s=30`.
- Worst case: 3 attempts × 30s timeout + 2 × 10s sleep = **110s**.
- Acceptable — daily run already takes 10–20s for yfinance fetches; an extra 1m40s on email path in degraded conditions is fine.

---

## 6. State Schema for Phase 6 Reads

**Authoritative sources (confirmed):**

- `state_manager.reset_state()` (state_manager.py:279–300) — initial shape.
- `run_daily_check` (main.py:550–556) — post-run dict shape for `state['signals'][key]` (G-2 + B-1 retrofits).
- `state_manager.record_trade` (state_manager.py:401–435) + `_validate_trade` (state_manager.py:174–241) — 12-field trade_log entry.
- `state_manager.update_equity_history` (state_manager.py:437–482) — `equity_history` shape.

### Top-level state shape

```python
{
  'schema_version': 1,                          # int
  'account': 101234.56,                         # float, always present
  'last_run': '2026-04-22',                     # ISO YYYY-MM-DD str | None (first run)
  'positions': {                                # dict[str, Position | None]
    'SPI200': <Position dict> | None,
    'AUDUSD': <Position dict> | None,
  },
  'signals': {                                  # dict[str, SignalEntry]
    'SPI200': <SignalEntry dict> | int (legacy),
    'AUDUSD': <SignalEntry dict> | int (legacy),
  },
  'trade_log': [<TradeRecord dict>, ...],       # list, newest appended at end
  'equity_history': [<EquityPoint dict>, ...],  # list, newest appended at end
  'warnings': [<Warning dict>, ...],            # list, FIFO bounded to MAX_WARNINGS=100
}
```

### `state['signals'][key]` — Phase 4 G-2 dict shape (authoritative)

```python
{
  'signal': 1,                                  # int: 1 (LONG), -1 (SHORT), 0 (FLAT)
  'signal_as_of': '2026-04-21',                 # ISO YYYY-MM-DD, last data-bar date
  'as_of_run': '2026-04-22',                    # ISO YYYY-MM-DD, run_date (AWST)
  'last_scalars': {                             # 8-key dict from get_latest_indicators
    'adx': 32.5,
    'atr': 50.0,
    'mom1': 0.031,                              # 21-day return as fraction
    'mom3': 0.048,                              # 63-day return
    'mom12': 0.092,                             # 252-day return
    'ndi': 12.4,                                # -DI
    'pdi': 28.1,                                # +DI
    'rvol': 1.12,                               # annualised √252 realised vol
  },
  'last_close': 8085.0,                         # float, Phase 5 B-1 retrofit
}
```

**Legacy int shape** (survives from Phase 3 `reset_state()`): `state['signals']['SPI200'] = 0` (bare int, no signal_as_of/last_scalars). Phase 6 must handle both per D-08 backward-compat read pattern (main.py:471–472 template).

### `state['positions'][key]` — Position TypedDict (system_params.py:84–105)

```python
{
  'direction': 'LONG',                          # Literal['LONG', 'SHORT']
  'entry_price': 8000.0,                        # float
  'entry_date': '2026-04-10',                   # ISO YYYY-MM-DD
  'n_contracts': 2,                             # int > 0
  'pyramid_level': 0,                           # int, 0..2
  'peak_price': 8100.0,                         # float | None (None for SHORT)
  'trough_price': None,                         # float | None (None for LONG)
  'atr_entry': 50.0,                            # float
}
```

### `state['trade_log']` — 12-field records

```python
{
  'instrument': 'SPI200',                       # Literal['SPI200', 'AUDUSD']
  'direction': 'LONG',                          # Literal['LONG', 'SHORT']
  'entry_date': '2026-02-01',                   # ISO YYYY-MM-DD
  'exit_date': '2026-02-08',                    # ISO YYYY-MM-DD
  'entry_price': 7850.0,                        # float
  'exit_price': 7920.0,                         # float
  'gross_pnl': 350.0,                           # float — raw price-delta P&L (Pitfall 8)
  'n_contracts': 1,                             # int > 0
  'exit_reason': 'stop_hit',                    # str (see _EXIT_REASON_DISPLAY in dashboard.py)
  'multiplier': 5.0,                            # float — contract multiplier
  'cost_aud': 6.0,                              # float — round-trip cost
  'net_pnl': 347.0,                             # float — state_manager D-20 appended key
}
```

**Phase 6 reads `net_pnl`** (not `gross_pnl`) for the P&L column — matches Phase 5 dashboard (dashboard.py:768 `_fmt_pnl_with_colour(trade.get('net_pnl', 0.0))`).

### `state['equity_history']` — time series

```python
[
  {'date': '2026-02-01', 'equity': 100000.0},
  {'date': '2026-02-02', 'equity': 100050.0},
  ...
]
```

**Phase 6 reads:**

- `equity = equity_history[-1]['equity']` → "Running equity" big number.
- `change = equity_history[-1]['equity'] - equity_history[-2]['equity']` → "Today's change" (when `len >= 2`; else em-dash).
- `since_inception = (equity - INITIAL_ACCOUNT) / INITIAL_ACCOUNT` → signed percent.

### Example sample_state_with_change.json (planner drafts exact values)

```json
{
  "schema_version": 1,
  "account": 101234.56,
  "last_run": "2026-04-22",
  "positions": {
    "SPI200": {
      "direction": "LONG", "entry_price": 8204.5, "entry_date": "2026-04-15",
      "n_contracts": 2, "pyramid_level": 0,
      "peak_price": 8300.0, "trough_price": null, "atr_entry": 45.0
    },
    "AUDUSD": null
  },
  "signals": {
    "SPI200": {
      "signal": 1, "signal_as_of": "2026-04-21", "as_of_run": "2026-04-22",
      "last_scalars": {"adx": 32.5, "atr": 50.0, "mom1": 0.031, "mom3": 0.048, "mom12": 0.092, "ndi": 12.4, "pdi": 28.1, "rvol": 1.12},
      "last_close": 8285.0
    },
    "AUDUSD": {
      "signal": 0, "signal_as_of": "2026-04-21", "as_of_run": "2026-04-22",
      "last_scalars": {"adx": 18.3, "atr": 0.0042, "mom1": -0.005, "mom3": 0.001, "mom12": 0.014, "ndi": 21.2, "pdi": 19.0, "rvol": 0.95},
      "last_close": 0.6502
    }
  },
  "trade_log": [<5 records, last one closed same day for ACTION REQUIRED diff lookup>],
  "equity_history": [<60 points, last diff from prev = +$234.56>],
  "warnings": []
}
```

**Paired `old_signals` for this fixture:** `{'^AXJO': -1, 'AUDUSD=X': 0}` → new SPI200 is LONG, old was SHORT → ACTION REQUIRED shows `SPI 200: SHORT → LONG` with close-position copy sourced from `trade_log[-1]`.

---

## 7. `_atomic_write` Decision

### Current state

- **`state_manager._atomic_write`** (state_manager.py:88–133) — takes `(data: str, path: Path) -> None`. Full D-17 durability sequence (tempfile + fsync + os.replace + parent-dir fsync on POSIX). Does NOT force `newline='\n'` on tempfile (relies on state JSON being ASCII-clean).
- **`dashboard._atomic_write_html`** (dashboard.py:987–1031) — takes `(data: str, path: Path) -> None`. Identical D-17 sequence, PLUS `newline='\n'` on tempfile (C-7 reviews fix — forces LF regardless of platform, critical for golden-HTML byte-stability on Windows).

### The choice

**CONTEXT D-13 leaves this as Claude's Discretion.** Two options:

**Option A — duplicate into `notifier.py`** (CONTEXT current recommendation).

- Pros: zero cross-hex coupling. Notifier has one extra ~25-line helper. Identical to `dashboard._atomic_write_html` byte-for-byte.
- Cons: 3 copies of the same logic (state_manager, dashboard, notifier).

**Option B — extract to `state_manager.py` as public helper.**

- Pros: single source of truth.
- Cons: notifier imports a state_manager helper for a non-state-management purpose. Hex fence rationale weakens: notifier was supposed to only import state_manager.load_state for the convenience CLI path. Adding `_atomic_write` as a second export dilutes that boundary.

**Option C — extract to `system_params.py` OR a new `_io_helpers.py` module.**

- Pros: shared utility belongs in a utility module.
- Cons: new module = Phase 6 scope creep. `system_params.py` is currently pure constants + TypedDict — adding I/O code violates its "no I/O" docstring lock.

### Researcher recommendation: **Option A (duplicate)** — matches CONTEXT current recommendation.

**Rationale:**
1. Existing precedent: `dashboard._atomic_write_html` already duplicates `state_manager._atomic_write`. Notifier doing the same is architectural consistency, not duplication smell.
2. Hex-lite principle: each I/O hex owns its own I/O primitives. `notifier.py` writing `last_email.html` is its own concern; it shouldn't depend on state_manager's internal helpers.
3. Test isolation: patching `notifier.os.replace` in tests is cleaner when the notifier has its own helper than when tests patch through `state_manager`.
4. The duplication is 25 lines of mechanical file-write plumbing. Risk of drift is minimal (the D-17 durability sequence is stable).

**Exact code (copy-paste from dashboard.py:987–1031, adjust docstring):**

```python
def _atomic_write_html(data: str, path: Path) -> None:
  '''Mirror of state_manager._atomic_write + dashboard._atomic_write_html.

  Same D-17 durability sequence. Tempfile `newline='\\n'` forces LF
  regardless of platform (C-7 reviews precedent — golden-byte-stability
  against Windows CRLF translation).
  '''
  parent = path.parent
  tmp_path_str = None
  try:
    with tempfile.NamedTemporaryFile(
      dir=parent, delete=False, mode='w', suffix='.tmp', encoding='utf-8',
      newline='\n',
    ) as tmp:
      tmp_path_str = tmp.name
      tmp.write(data)
      tmp.flush()
      os.fsync(tmp.fileno())
    os.replace(tmp_path_str, path)
    if os.name == 'posix':
      dir_fd = os.open(str(parent), os.O_RDONLY)
      try:
        os.fsync(dir_fd)
      finally:
        os.close(dir_fd)
    tmp_path_str = None
  finally:
    if tmp_path_str is not None:
      try:
        os.unlink(tmp_path_str)
      except FileNotFoundError:
        pass
```

---

## 8. `_send_email_never_crash` Pattern

### Existing Phase 5 mirror (main.py:94–112)

```python
def _render_dashboard_never_crash(state: dict, out_path: Path, now: datetime) -> None:
  '''D-06: dashboard render failure never crashes the run.

  C-2 reviews: `import dashboard` lives INSIDE the helper body (not at
  module top) so import-time errors in dashboard.py — syntax errors,
  bad sub-imports, circular-import bugs — are caught by the SAME
  `except Exception` that catches runtime render failures.
  '''
  try:
    import dashboard  # local import — C-2 isolates import-time failures
    dashboard.render_dashboard(state, out_path, now=now)
  except Exception as e:
    logger.warning('[Dashboard] render failed: %s: %s', type(e).__name__, e)
```

### Phase 6 verbatim mirror (planner produces this)

```python
def _send_email_never_crash(
  state: dict,
  old_signals: dict,
  run_date: datetime,
  is_test: bool = False,
) -> None:
  '''D-15 / Phase 5 C-2 precedent: email send failure never crashes the run.

  `import notifier` lives INSIDE the helper body (not at module top) so
  import-time errors in notifier.py — syntax errors, bad sub-imports,
  circular-import bugs — are caught by the SAME `except Exception` that
  catches runtime dispatch failures. Without this, an import-time
  notifier error takes down main.py at module load time, before the
  helper even runs.

  The ONLY place in this codebase where `except Exception:` is correct —
  email is a delivery artefact. State is already saved; dashboard already
  rendered. Never abort the run on an email failure.
  '''
  try:
    import notifier  # local import — C-2 isolates import-time failures
    notifier.send_daily_email(state, old_signals, run_date, is_test=is_test)
  except Exception as e:
    logger.warning('[Email] send failed: %s: %s', type(e).__name__, e)
```

**Where it's called from** (main.py `main()` function, replacing Phase 4's `_force_email_stub` path per CONTEXT D-15):

```python
# In main() after flag parsing + reset handling, in the dispatch ladder:
if args.force_email or args.test:
  rc, state, old_signals = run_daily_check(args)  # tuple return per §9 refactor
  if rc == 0:
    _send_email_never_crash(state, old_signals, run_date, is_test=args.test)
  return rc

# Default / --once path:
rc, _, _ = run_daily_check(args)
return rc
```

**Key details the planner must encode:**

1. `import notifier` MUST be inside the try/except (C-2 pattern) — not at module top.
2. `except Exception` is intentional here — CLAUDE.md's narrow-catch rule has an explicit exemption for never-crash invariants. Document this in the docstring.
3. Log prefix `[Email]` is locked (CLAUDE.md Conventions).
4. Returns `None`, not int — dispatch success/failure is already absorbed by `notifier.send_daily_email` which returns `0` on both success and graceful-degradation paths.

**Existing Phase 5 test pattern to mirror** (`tests/test_main.py` — planner reads exact test):

- `test_dashboard_render_never_crash_on_runtime_error` → `test_email_send_never_crash_on_runtime_error`
- `test_dashboard_render_never_crash_on_import_error` → `test_email_send_never_crash_on_import_error`

Monkeypatch `notifier.send_daily_email` to raise RuntimeError; assert `main(['--force-email'])` returns 0; assert `'[Email] send failed' in caplog.text`.

---

## 9. `run_daily_check` Return Refactor

### Current signature (main.py:351)

```python
def run_daily_check(args: argparse.Namespace) -> int:
```

Returns: `0` on success, raises `DataFetchError` / `ShortFrameError` on data failure, other exceptions propagate.

### Current call sites (grep `run_daily_check(`)

- `main.main()` (main.py:727, 730) — two call sites in the dispatch ladder.
- `tests/test_main.py` — no direct calls; all tests invoke `main.main([...])` which internally calls `run_daily_check`. `[VERIFIED]`

### Problem

CONTEXT D-15 + UI-SPEC §2 "Entry price" note: Phase 6 needs the POST-RUN `state` dict (reflects positions after reversal) and `old_signals` dict (captured BEFORE the run) — without calling `load_state` a second time, because `--test` did not persist to disk and a second load would return the PRE-RUN state.

### Option evaluation

**Option X1 — tuple return `(rc, state, old_signals)`.**

```python
def run_daily_check(args: argparse.Namespace) -> tuple[int, dict, dict[str, int | None]]:
  ...
  return 0, state, old_signals
```

- Pros: explicit, pure, no globals, test-friendly.
- Cons: touches 2 call sites in `main.py` + 1 line in every test that asserts on the return value. Actual churn: ~5 lines.

**Option X2 — module-level `_last_run_context: dict | None = None`.**

```python
# main.py module-level
_last_run_context: dict | None = None

def run_daily_check(args):
  global _last_run_context
  ...
  _last_run_context = {'state': state, 'old_signals': old_signals}
  return 0
```

- Pros: zero signature churn.
- Cons: global mutable state. Breaks pytest-xdist parallel test isolation. Non-obvious side-channel for a reader. Makes `run_daily_check` impure.

**Option X3 — re-run the compute path inside email dispatch.**

- Pros: zero refactor.
- Cons: doubles the yfinance fetch time (20s → 40s). Non-determinism if market data changed between the two calls. Terrible.

### Researcher recommendation: **Option X1 (tuple return).**

**Rationale:**
1. Purity: no globals, no side channels. Function signature tells the truth about what it produces.
2. Test-friendly: every existing test that invokes `main.main([...])` is unaffected (main() unpacks internally). Only `run_daily_check` direct callers need update — and there are zero direct test callers today.
3. Minimal churn: 2 `return 0` sites become `return 0, state, old_signals`; 1 early-return (`if args.test: return 0` at main.py:591) becomes `return 0, state, old_signals`. 3 `return` lines total.
4. `main.main()` unpack is 2 sites: `rc, state, old_signals = run_daily_check(args)`.
5. Precedent exists in the stdlib (`subprocess.run` returns a CompletedProcess object; `requests.get` returns a Response). Tuple returns are normal.

**Exact diff shape:**

```python
# main.py:351 — signature change
def run_daily_check(args: argparse.Namespace) -> tuple[int, dict, dict]:

# Capture old_signals AFTER load_state but BEFORE per-symbol loop
# (per CONTEXT D-05).
state = state_manager.load_state()
old_signals = {
  yf_symbol: (
    state['signals'].get(state_key, {}).get('signal')
    if isinstance(state['signals'].get(state_key), dict)
    else state['signals'].get(state_key)
  )
  for state_key, yf_symbol in SYMBOL_MAP.items()
}

# ... existing per-symbol loop and rollup ...

# Main.py:591 — --test early return (3 places become `return rc, state, old_signals`)
if args.test:
  ...
  return 0, state, old_signals

# Main.py:616 — happy-path return
return 0, state, old_signals
```

**Call site updates (main.main() body, 2 sites):**

```python
# Old:
return run_daily_check(args)

# New — when result unused:
rc, _, _ = run_daily_check(args)
return rc

# New — when result used for email dispatch:
rc, state, old_signals = run_daily_check(args)
if rc == 0 and (args.force_email or args.test):
  _send_email_never_crash(state, old_signals, run_date=???, is_test=args.test)
return rc
```

**Edge case — `run_date`.** The email helper needs the `run_date` datetime. Option: also return it in the tuple (`(rc, state, old_signals, run_date)` — 4-tuple). Cleaner alternative: re-call `_compute_run_date()` inside `_send_email_never_crash` since it's cheap (single `datetime.now(AWST)`). **Recommend:** return `run_date` in the tuple for purity — avoid a second clock read. Signature becomes `tuple[int, dict, dict, datetime]`. Planner decides.

---

## Validation Architecture

**Nyquist validation is enabled** (no explicit `workflow.nyquist_validation: false` in `.planning/config.json`; confirmed by looking at Phase 5's full validation architecture presence).

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.3.3 + pytest-freezer 0.4.9 |
| Config file | `pyproject.toml` (per Phase 1) |
| Quick run command | `.venv/bin/pytest tests/test_notifier.py -x` |
| Full suite command | `.venv/bin/pytest tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| NOTF-01 | Resend POST reaches `https://api.resend.com/emails` with Bearer auth | unit (mock requests) | `pytest tests/test_notifier.py::TestResendPost::test_post_url_and_auth_header -x` | ❌ Wave 0 |
| NOTF-02 | Subject has 🔴 on change, 📊 on no-change, `[TEST]` prefix for --test | unit | `pytest tests/test_notifier.py::TestComposeSubject -x` (6 cases) | ❌ Wave 0 |
| NOTF-03 | HTML body has inline CSS only, palette hexes present | unit (substring) | `pytest tests/test_notifier.py::TestComposeBody::test_body_has_palette_inline -x` | ❌ Wave 0 |
| NOTF-04 | 7 body sections render in order | unit (substring + order) | `pytest tests/test_notifier.py::TestComposeBody::test_body_sections_in_order -x` | ❌ Wave 0 |
| NOTF-05 | ACTION REQUIRED block present when signal changed | unit (golden snapshot w/change) | `pytest tests/test_notifier.py::TestComposeBody::test_action_required_when_changed -x` | ❌ Wave 0 |
| NOTF-06 | Mobile-responsive at 375px (no `@media`, `max-width:600px`) | unit (substring) | `pytest tests/test_notifier.py::TestComposeBody::test_mobile_responsive_markup -x` | ❌ Wave 0 |
| NOTF-07 | Resend 5xx logs error, `send_daily_email` returns 0 | unit (mock 500) | `pytest tests/test_notifier.py::TestSendDispatch::test_5xx_logs_and_returns_zero -x` | ❌ Wave 0 |
| NOTF-08 | Missing `RESEND_API_KEY` writes `last_email.html`, returns 0 | unit (env clear + tmp_path) | `pytest tests/test_notifier.py::TestSendDispatch::test_missing_api_key_writes_fallback -x` | ❌ Wave 0 |
| NOTF-09 | All state-derived values HTML-escaped; no unescaped `${...}` | unit (inject `<script>` into exit_reason, assert escaped) | `pytest tests/test_notifier.py::TestComposeBody::test_xss_escape_on_exit_reason -x` | ❌ Wave 0 |
| CLI-01 (Phase 6 slice) | `--test` sends `[TEST]`-prefixed email, state.json mtime unchanged | integration | `pytest tests/test_main.py::TestCLI::test_test_flag_sends_test_prefixed_email_no_state_mutation -x` | ❌ Wave 0 |
| CLI-03 (Phase 6 slice) | `--force-email` sends today's email with fresh state | integration | `pytest tests/test_main.py::TestCLI::test_force_email_sends_live_email -x` | ❌ Wave 0 |

Plus golden-snapshot tests (unit, byte-equal compare):

| Test | Command | Covers |
|------|---------|--------|
| `TestGoldenEmail::test_with_change_golden` | `pytest tests/test_notifier.py::TestGoldenEmail -x` | NOTF-04, NOTF-05, NOTF-09 (combined byte lock) |
| `TestGoldenEmail::test_no_change_golden` | " | NOTF-04 (combined) |
| `TestGoldenEmail::test_empty_golden` | " | First-run / no-previous-signal path |

Plus never-crash integration tests:

| Test | Command | Covers |
|------|---------|--------|
| `TestEmailNeverCrash::test_runtime_failure_isolated` | `pytest tests/test_main.py::TestEmailNeverCrash -x` | D-15 / NOTF-07 via main.py boundary |
| `TestEmailNeverCrash::test_import_time_failure_isolated` | " | C-2 import-inside-try pattern |

### Sampling Rate

- **Per task commit:** `.venv/bin/pytest tests/test_notifier.py tests/test_main.py -x` (fast — <5s)
- **Per wave merge:** `.venv/bin/pytest tests/ -x` (full suite, ~6–8s)
- **Phase gate:** Full suite green + ruff clean + `regenerate_notifier_golden.py` idempotent (double-run → zero git diff) before `/gsd-verify-work 6`.

### Wave 0 Gaps

- [ ] `tests/test_notifier.py` — 6-class skeleton (TestComposeSubject, TestComposeBody, TestFormatters, TestSendDispatch, TestResendPost, TestGoldenEmail) — covers NOTF-01..09
- [ ] `tests/fixtures/notifier/sample_state_with_change.json` — SPI200 LONG→SHORT transition with closed trade in trade_log[-1]
- [ ] `tests/fixtures/notifier/sample_state_no_change.json` — both unchanged; at least 2 equity_history points for Today's change
- [ ] `tests/fixtures/notifier/empty_state.json` — reset_state() output
- [ ] `tests/fixtures/notifier/golden_with_change.html` — byte-equal target (regenerated in Wave 2)
- [ ] `tests/fixtures/notifier/golden_no_change.html` — "
- [ ] `tests/fixtures/notifier/golden_empty.html` — "
- [ ] `tests/regenerate_notifier_golden.py` — operator-only regenerator script
- [ ] `.env.example` — at repo root, placeholder values only
- [ ] `.gitignore` — add `last_email.html` line (verify Phase 5 `dashboard.html` pattern in place)
- [ ] `tests/test_signal_engine.py` — add `FORBIDDEN_MODULES_NOTIFIER` frozenset + parametrize the AST blocklist test
- [ ] Palette retrofit: move `_COLOR_BG`, `_COLOR_SURFACE`, `_COLOR_BORDER`, `_COLOR_TEXT`, `_COLOR_TEXT_MUTED`, `_COLOR_TEXT_DIM`, `_COLOR_LONG`, `_COLOR_SHORT`, `_COLOR_FLAT` from `dashboard.py` to `system_params.py`; `dashboard.py` imports from there; verify all Phase 5 dashboard golden tests still pass after the retrofit.

Framework install: none needed — all deps already pinned.

---

## 11. Schema Push (N/A)

Trading-signals has **no ORM** and no database — state persists as flat JSON in `state.json` at the repo root (managed by `state_manager.py`). Schema migrations are handled by `state_manager._migrate()` walking `MIGRATIONS` forward against `state['schema_version']`. Phase 6 does NOT change the state schema — only reads from it. The Schema Push Detection Gate in `/gsd-plan-phase` will find no schema-relevant files and skip the `[BLOCKING]` injection. Noted for completeness.

---

## 12. Security Threat Model Inputs

**ASVS applicability:** this is a single-user CLI tool with one outbound HTTPS call. Traditional AuthN/AuthZ chapters (V2, V3, V4) don't apply. Relevant categories:

| ASVS Category | Applies | Standard Control |
|---------------|---------|------------------|
| V5 Input Validation | YES | `html.escape(value, quote=True)` at every leaf interpolation (Phase 5 D-15 posture) |
| V6 Cryptography | partial | TLS handled by `requests` / certifi — no hand-rolled crypto |
| V7 Error Handling | YES | Never log `RESEND_API_KEY`; truncate Resend error bodies in logs |
| V13 API/Web Services | YES | Outbound HTTPS to fixed endpoint (no SSRF — user-supplied URL path absent) |

**Known Threat Patterns for Phase 6:**

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| XSS via state-derived strings (exit_reason, instrument) | Tampering | `html.escape(value, quote=True)` at leaf interpolation — Phase 5 D-15 discipline extends verbatim |
| API key leakage via logs / error bodies | Information Disclosure | Never log the raw key. Truncate Resend 4xx body to ≤200 chars. |
| API key committed to git | Information Disclosure | `.env` in `.gitignore` (verified). `.env.example` has placeholder only. |
| Fallback recipient as GitHub footprint | Information Disclosure | `_EMAIL_TO_FALLBACK` commits a real email address (`marc@carbonbookkeeping.com.au`) to source code. Not technically sensitive (operator-owned) but visible in repo history. |
| HTML injection into subject line | Tampering | Subject is composed from (a) our own enum `LONG/SHORT/FLAT`, (b) ISO dates, (c) formatted currency. No state-derived free-text. Low risk — still audit the `compose_email_subject` output. |
| Sender domain impersonation | Spoofing | `signals@carbonbookkeeping.com.au` is Resend-verified (DKIM/SPF/DMARC). Verified per PROJECT.md. |
| TLS downgrade | Tampering / MitM | `requests` uses `urllib3` with certifi CA bundle; HTTPS-only endpoint. Automatic. |

### Specific items for planner to encode in PLAN.md `<threat_model>` blocks

**1. RESEND_API_KEY handling:**
- Never `logger.info('api_key=%s', key)` — and never interpolate `%s` with the key in any log line.
- When Resend returns 4xx/5xx, log `resp.status_code` and `resp.text[:200]` but VERIFY `resp.text` does not contain the key echoed back. `[ASSUMED]` — Resend's error bodies do NOT echo back the Authorization header; this is standard industry practice and no evidence to the contrary was found. Still, `resp.text[:200]` is defense-in-depth.
- `.env` is gitignored (verified: `.gitignore` line 4: `.env`).
- `.env.example` commits with placeholder `re_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` only.

**2. html.escape leaf discipline (Phase 5 D-15 posture):**
- Every state-derived string passes through `html.escape(value, quote=True)` at the LEAF interpolation site — never at intermediate concat.
- Specific surfaces:
  - Instrument display names (`SPI 200`, `AUD / USD`): our own constants, but escape anyway.
  - Signal labels (`LONG`, `SHORT`, `FLAT`, `—`): our own constants, escape anyway (belt-and-braces).
  - `signal_as_of` dates: ISO-format from our own fetch path; escape anyway.
  - `exit_reason`: free-text from sizing_engine (`'flat_signal'`, `'signal_reversal'`, `'stop_hit'`, `'adx_exit'`) — our own enum, but escape.
  - Currency formatted strings: `f'${value:,.2f}'` → produces ASCII only; escape anyway.
- **Test:** inject `<script>alert(1)</script>` as `exit_reason` in a fixture and assert the rendered HTML contains `&lt;script&gt;` and NOT `<script>` (mirror dashboard.py `TestRenderBlocks::test_xss_escape_on_exit_reason` pattern).

**3. Recipient fallback:**
- `_EMAIL_TO_FALLBACK` committed as `'marc@carbonbookkeeping.com.au'` (operator-confirmed) is acceptable — operator's own address, repo is not public (private GitHub repo per context).
- **Alternative hardening (optional):** use `'RECIPIENT_NOT_CONFIGURED@example.invalid'` as sentinel; if `os.environ.get('SIGNALS_EMAIL_TO')` returns None or the sentinel, log `[Email] WARN SIGNALS_EMAIL_TO not set; refusing to dispatch` and fall through to the `last_email.html` path. Cleaner in principle but adds complexity for a single-operator tool.
- **Researcher recommendation:** keep `_EMAIL_TO_FALLBACK = 'marc@carbonbookkeeping.com.au'` as per CONTEXT D-14. Document in `.env.example` that operator should set `SIGNALS_EMAIL_TO` to override for non-operator environments.

**4. Subject/body injection from state:**
- Our state-derived signal strings are enums (`LONG`/`SHORT`/`FLAT`) — no injection risk.
- `exit_reason` could theoretically contain HTML (state_manager's `_validate_trade` only checks `isinstance(value, str) and len(value) > 0`). `html.escape` at leaf is the mitigation.
- Confirm Phase 6's full test surface covers a "malicious `exit_reason`" case (mirror Phase 5's C-4 / C-5 pattern).

**5. No SSRF risk:**
- Outbound HTTPS to fixed Resend endpoint `https://api.resend.com/emails`. No user-supplied URL path. No redirects followed (requests defaults).

**6. Timing / log hygiene:**
- When Resend returns 401 with body `{"error": "invalid_api_key"}`, log `[Email] WARN Resend 401 invalid_api_key` — truncate at 200 chars.
- Do NOT log `resp.headers` — may contain request-ID or rate-limit metadata that's benign but noisy. If needed, log only `X-Request-Id` explicitly.
- Do NOT log the full `payload` in exception handlers (contains `html` which is multi-KB and pollutes logs).

---

## Open Questions for Planner

1. **Should `run_daily_check` return a 4-tuple `(rc, state, old_signals, run_date)` or 3-tuple `(rc, state, old_signals)`?** Researcher leans 4-tuple (zero additional clock reads) but 3-tuple is cleaner. Planner decides; either is safe.

2. **Should the `<head>` template include `<meta name="x-apple-disable-message-reformatting">` and `<meta name="format-detection" ...>` beyond CONTEXT D-07?** Researcher recommends YES (zero downside, prevents iOS-Mail auto-formatting / date auto-linkification). CONTEXT D-07 doesn't explicitly include them; surface as planner decision.

3. **Should 429 be retried inside `_post_to_resend`?** CONTEXT D-12's retry loop fails-fast on all 4xx. 429 is technically 4xx but Resend documents it as retryable. Researcher recommends special-casing: `if resp.status_code == 429: raise HTTPError(...)` (caught by retry tuple) OR treat explicitly. Planner must write this into the code.

4. **Should `timeout` be `30` (single-value, read-only) or `(5, 30)` (tuple, separate connect + read)?** Researcher recommends `(5, 30)`. Cosmetic — single value works.

5. **Should `last_email.html` be committed as a test fixture OR regenerated at test time?** Researcher recommends regenerate (it's a fallback artifact, not a golden). Planner picks — committing it locks the byte-stable shape but doubles fixture count.

6. **Should `notifier.py` expose a `python -m notifier` convenience CLI like `dashboard.py` does?** Researcher recommends YES — mirrors Phase 5. Runs `send_daily_email(load_state(), {}, datetime.now(AWST), is_test=False)` for operator ad-hoc testing. Use `old_signals={sym: None for sym in ...}` (treated as no-change per D-06).

7. **ACTION REQUIRED "Close existing {OLD_DIR} position (N contracts @ entry $X)" source.** UI-SPEC §2 recommends Option A (read from `state['trade_log'][-1]` when `trade_log[-1]['exit_date'] == run_date_iso AND trade_log[-1]['instrument'] == state_key`). Researcher concurs — the trade_log tail is deterministic post-run and avoids further `run_daily_check` signature churn. Planner writes the helper `_closed_position_for_instrument_on(state, state_key, run_date_iso)` inside notifier.py.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Resend unescapes `\uXXXX` JSON escape sequences in subject line to raw Unicode before forwarding to recipient MTA | §1 UTF-8/emoji | Emoji renders as literal `\uXXXX` text in recipient's subject line — visible but broken. Low probability; standard JSON parser behavior. Mitigate by testing one live send before Phase 6 ships. |
| A2 | Resend error bodies do NOT echo back the `Authorization: Bearer ...` header value | §12 Security | API key leaks into log files. `resp.text[:200]` truncation is defense-in-depth if this assumption is wrong. |
| A3 | 🔴 and 📊 render as color glyphs on Gmail web (Windows Chrome on old Windows is edge case) | §2 Gmail web quirks | Edge-case rendering on legacy Windows — documented as accepted limitation in UI-SPEC. |
| A4 | Python 3.11 f-strings are locale-independent under `,.2f` format spec | §4 golden-HTML stability | Different CI environments with different `LC_ALL` could produce different bytes. `[VERIFIED: PEP 3101]` — but confirming on the actual GHA runner during Phase 7 is prudent. |
| A5 | Emoji byte sequences are stable across Python 3.11.x patch versions | §4 golden-HTML stability | Low; Unicode encoding is part of the language spec. |
| A6 | Phase 5's `_render_dashboard_never_crash` pattern is the correct template for Phase 6's `_send_email_never_crash` | §8 never-crash pattern | None — pattern is already in the codebase and passes Phase 5 tests. |
| A7 | Gmail Android under system dark mode shifts `#22c55e` slightly but still reads as green | §2 dark-mode residual risk | UI-SPEC already documents as nice-to-have (not MUST-render); acceptable. |
| A8 | Resend's 5-rps rate limit is current as of April 2026 | §1 rate limits | Older docs say 2 rps; Phase 6 sends ≤1 email/day so either is fine. |

---

## Sources

### Primary (HIGH confidence)

- https://resend.com/docs/api-reference/emails/send-email — endpoint + request body + response shape
- https://resend.com/docs/api-reference/errors — full error code table
- https://resend.com/docs/api-reference/introduction — current rate limits (5 rps/team)
- Codebase: `main.py`, `state_manager.py`, `dashboard.py`, `system_params.py`, `tests/test_dashboard.py`, `tests/regenerate_dashboard_golden.py`, `requirements.txt`, `.gitignore`
- `.planning/phases/06-email-notification/06-CONTEXT.md` (15 locked decisions)
- `.planning/phases/06-email-notification/06-UI-SPEC.md` (full UI contract)
- `.planning/REQUIREMENTS.md` (NOTF-01..09 full text)
- `.planning/phases/04-end-to-end-skeleton-fetch-orchestrator-cli/04-03-SUMMARY.md` (run_daily_check + AC-1 + G-2/B-1 retrofits)

### Secondary (MEDIUM confidence)

- https://resend.com/changelog/api-rate-limit — historical rate limit context (2 rps → 5 rps)
- https://resend.com/docs/knowledge-base/account-quotas-and-limits — quota specifics
- Can I Email / Email Client Support Matrix — Gmail + iOS Mail rendering baselines

### Tertiary (LOW confidence — cited but not critical-path)

- Campaign Monitor / Email on Acid guides (implicit in §2 Gmail/iOS quirks) — community wisdom on fluid-hybrid layouts; cross-referenced with vendor docs where possible

## Metadata

**Confidence breakdown:**

- Resend API shape: **HIGH** — official docs, three doc pages cross-referenced
- State schema for Phase 6 reads: **HIGH** — source code verified line-by-line
- Phase 5 golden-snapshot pattern transfer: **HIGH** — direct code read of Phase 5 test + regenerator
- `_send_email_never_crash` pattern: **HIGH** — verbatim mirror of existing Phase 5 helper
- `run_daily_check` refactor impact: **HIGH** — call-site grep complete
- Gmail + iOS Mail client quirks: **MEDIUM** — docs + community wisdom, not exhaustively lab-tested
- Resend rate limit nuances: **MEDIUM** — docs shifted 2→5 rps over 2024–2025
- Emoji byte-stability: **HIGH** — Python / UTF-8 spec
- Security threat model: **HIGH** — standard practices; one `[ASSUMED]` on Resend not echoing auth header

**Research date:** 2026-04-22
**Valid until:** 2026-05-22 (30 days — stable domain)

## RESEARCH COMPLETE
