# notifier.py → notifier/ package — split manifest

**Plan:** 27-12 (Wave 3 sequential)
**Source:** `notifier.py` — 2195 LOC (post Plan 27-11)
**Target:** `notifier/` package — every file <500 LOC

## Confirmed: `_dispatch_email_and_maintain_warnings` stays in main.py

`grep -n '_dispatch_email_and_maintain_warnings' main.py notifier.py` confirms:
- main.py:1670 — function definition (`def _dispatch_email_and_maintain_warnings(...)`)
- main.py:118, 499, 644, 668, 672, 1294, 1758, 1986 — call sites + comments
- notifier.py:1641 — only a docstring mention (`Orchestrator (main._dispatch_email_and_maintain_warnings)`)

The function lives in main.py. It will move to `daily_loop.py` / `crash_boundary.py` in Plan 27-13. Per review-fix agreed-3, this plan does NOT touch it.

## Public templating entry points

The plan assumed `render_email_html`. Reality: that function does NOT exist. The actual public templating surface is:

- `compose_email_subject(state, old_signals, is_test=False, has_critical_banner=False) -> str`
- `compose_email_body(state, old_signals, now, *, from_addr) -> str`

Both are imported externally via `from notifier import compose_email_body, compose_email_subject` (see `tests/test_notifier.py:39-40`, `tests/test_html_xss_audit.py:40`, `tests/regenerate_notifier_golden.py:54`).

`__init__.py` re-exports both.

## Public API + monkeypatch-target manifest

Enumerated from `grep -nE 'notifier\.[a-zA-Z_]|from notifier import' tests/*.py`:

| Name | Used by | Status |
|---|---|---|
| `compose_email_subject` | tests/test_notifier.py, tests/test_html_xss_audit.py, tests/regenerate_notifier_golden.py | re-export from formatters |
| `compose_email_body` | tests/test_notifier.py, tests/test_html_xss_audit.py, tests/regenerate_notifier_golden.py | re-export from templates |
| `send_daily_email` | tests/test_notifier.py, tests/test_signals_email_to_required.py | re-export from dispatch |
| `send_crash_email` | tests/test_notifier.py, tests/test_signals_email_to_required.py, tests/test_main.py | re-export from dispatch |
| `send_magic_link_email` | tests/test_notifier_magic_link.py | re-export from dispatch |
| `send_stop_alert_email` | tests/test_notifier_stop_alert.py, main.py | re-export from dispatch |
| `SendStatus` | main.py (3 sites: line 196, plus tests) | re-export from transport |
| `ResendError` | tests/test_notifier.py | re-export from transport |
| `_post_to_resend` | tests/test_notifier.py (monkeypatch target — tests do `monkeypatch.setattr(notifier, '_post_to_resend', ...)`) | re-export from transport |
| `_atomic_write_html` | tests/test_notifier.py | re-export from transport |
| `_resolve_last_crash_path` | tests/test_crash_email_fallback.py | re-export from crash_path |
| `_write_last_crash` | tests/test_crash_email_fallback.py | re-export from crash_path |
| `_redact_secrets_in_text` | tests/test_crash_email_fallback.py | re-export from crash_path |
| `_build_last_crash_payload` | tests/test_crash_email_fallback.py | re-export from crash_path |
| `requests` | tests/test_notifier.py — `monkeypatch.setattr('notifier.requests.post', ...)` | re-export from transport |
| `os` | tests/test_notifier.py | re-export — module access via env-var monkeypatch context |
| `_RESEND_BACKOFF_S` | tests/test_notifier.py (used to dial backoff to 0 in retry-loop tests) | re-export from transport |
| `_has_critical_banner` | tests/test_notifier.py (`from notifier import _has_critical_banner`) | re-export from templates |
| `_render_header_email` | tests/test_notifier.py (`from notifier import _render_header_email`) | re-export from templates |
| `_detect_signal_changes` | tests/test_notifier.py | re-export from formatters |
| `_closed_position_for_instrument_on` | tests/test_notifier.py | re-export from formatters |
| `_compute_unrealised_pnl_email` | tests/test_notifier.py | re-export from formatters |
| `_fmt_currency_email` | tests/test_notifier.py | re-export from formatters |
| `_fmt_em_dash_email` | tests/test_notifier.py | re-export from formatters |
| `_fmt_instrument_display_email` | tests/test_notifier.py | re-export from formatters |
| `_fmt_last_updated_email` | tests/test_notifier.py | re-export from formatters |
| `_fmt_percent_signed_email` | tests/test_notifier.py | re-export from formatters |
| `_fmt_percent_unsigned_email` | tests/test_notifier.py | re-export from formatters |
| `_fmt_pnl_with_colour_email` | tests/test_notifier.py | re-export from formatters |

`enforce_fifo_bound` (new helper from this plan) is NOT used by existing code — main.py's bound enforcement currently lives in `state_manager.append_warning`. We expose it for the plan's `must_haves.artifacts` contract; it's an importable no-op-equivalent stub helper, callable but unused (callers may adopt later).

## Seam allocation (line-range → seam)

| Line range | Symbol | Seam |
|---|---|---|
| 1-89 | module docstring + imports + logger | __init__.py module docstring; imports redistributed per-seam |
| 91-99 | `class SendStatus(NamedTuple)` | transport.py |
| 113-153 | `_resolve_email_to_or_skip` | transport.py |
| 169-184 | `_resolve_last_crash_path` | crash_path.py |
| 187-204 | `_SECRET_PATTERNS_PHASE27_11` | crash_path.py |
| 207-219 | `_redact_secrets_in_text` | crash_path.py |
| 222-247 | `_build_last_crash_payload` | crash_path.py |
| 250-285 | `_write_last_crash` | crash_path.py |
| 295-306 | `_RESEND_RETRIES`, `_RESEND_BACKOFF_S`, `_RESEND_RETRY_EXCEPTIONS` | transport.py |
| 313-344 | display dicts (`_INSTRUMENT_DISPLAY_NAMES_EMAIL`, `_CONTRACT_SPECS_EMAIL`, `_STATE_KEY_TO_YF_SYMBOL`, `_SIGNAL_LABELS_EMAIL`, `_SIGNAL_COLOUR_EMAIL`, `_EXIT_REASON_DISPLAY_EMAIL`) | formatters.py |
| 351-357 | `class ResendError(Exception)` | transport.py |
| 370-453 | `_fmt_*` family | formatters.py |
| 460-482 | `_detect_signal_changes` | formatters.py |
| 485-564 | `compose_email_subject` | formatters.py |
| 567-595 | `_closed_position_for_instrument_on` | formatters.py |
| 602-628 | signal extractors (`_extract_signal_int`, `_extract_signal_as_of`, `_extract_last_close`) | formatters.py |
| 631-687 | `_compute_trail_stop_email`, `_compute_unrealised_pnl_email` | formatters.py |
| 690-738 | `_render_hero_card_email` | templates.py |
| 740-758 | `_has_critical_banner` | templates.py |
| 761-915 | `_render_header_email` | templates.py |
| 917-993 | `_render_action_required_email` | templates_sections.py |
| 995-1089 | `_render_signal_status_email` | templates_sections.py |
| 1091-1193 | `_render_positions_email` | templates_sections.py |
| 1195-1260 | `_render_todays_pnl_email` | templates_sections.py |
| 1262-1361 | `_render_closed_trades_email` | templates_sections.py |
| 1363-1384 | `_render_footer_email` | templates.py |
| 1387-1462 | `compose_email_body` | templates.py |
| 1465-1504 | `_atomic_write_html` | transport.py |
| 1507-1608 | `_post_to_resend` | transport.py |
| 1611-1713 | `send_daily_email` | dispatch.py |
| 1716-1817 | `send_crash_email` | dispatch.py |
| 1835-1911 | magic-link helpers (`_format_expires_awst`, `_render_magic_link_html`, `_render_magic_link_text`) | templates_alerts.py |
| 1914-1988 | `send_magic_link_email` | dispatch.py |
| 1995-2121 | stop-alert helpers (`_build_alert_subject`, `_render_alert_email_html`, `_render_alert_email_text`) | templates_alerts.py |
| 2124-2175 | `send_stop_alert_email` | dispatch.py |
| 2178-2195 | `if __name__ == '__main__'` CLI | __init__.py guard |

## Estimated final LOC per file (target: every file <500)

| File | Est LOC | Notes |
|---|---|---|
| `__init__.py` | ~90 | re-exports + CLI |
| `crash_path.py` | ~120 | line range 169-285 |
| `warnings_fifo.py` | ~30 | new helper |
| `formatters.py` | ~340 | line ranges 313-344, 370-687 |
| `templates.py` | ~280 | line ranges 690-758, 761-915, 1363-1462 |
| `templates_sections.py` | ~450 | line ranges 917-1361 |
| `templates_alerts.py` | ~270 | line ranges 1835-1911, 1995-2121 |
| `transport.py` | ~280 | line ranges 91-99, 113-153, 295-306, 351-357, 1465-1608 |
| `dispatch.py` | ~420 | line ranges 1611-1817, 1914-1988, 2124-2175 |

**Rule 3 deviation:** Plan enumerates 5 files (`__init__.py`, `templates.py`, `transport.py`, `warnings_fifo.py`, `crash_path.py`). I add 4 supplementary files (`formatters.py`, `templates_sections.py`, `templates_alerts.py`, `dispatch.py`) because cohesively-grouped code segments exceed 500 LOC. The plan's hard rule "every file <500 LOC" takes precedence; the artifact list is a minimum surface, not a maximum. Each new file maps to a clean cohesive cluster (formatters = pure-display helpers, sections = body sections, alerts = magic-link + stop-alert independent template families, dispatch = orchestrators). Documented in SUMMARY.md.

## Circular-import audit

- formatters → no notifier-internal imports (uses system_params, html, datetime, pytz)
- templates_sections → formatters (display dict + formatters); no transport/dispatch
- templates → templates_sections + formatters; no transport/dispatch
- templates_alerts → no notifier-internal imports
- crash_path → no notifier-internal imports (uses system_params, pathlib, os, json, re)
- warnings_fifo → no notifier-internal imports (uses system_params)
- transport → no notifier-internal imports (uses pnl_engine, state_manager, system_params)
- dispatch → templates, templates_alerts, transport, crash_path, formatters

No cycles. Dispatch is the leaf; formatters/crash_path/warnings_fifo/transport/templates_alerts are independent leaves; templates depends on templates_sections + formatters.

## Two-commit pattern

- **Task A:** create notifier/ package; KEEP notifier.py as re-export shim. All tests pass.
- **Task B:** grep for any remaining `notifier.py` file-form imports (Python imports almost never use `.py` suffix). If clean: delete shim. If non-zero: keep shim with rationale.
