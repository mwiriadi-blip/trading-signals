---
phase: 26
plan: 04
subsystem: web/routes
tags: [substitute-helper, placeholder-resolution, hex-boundary, B2, B3]
requires:
  - 26-03-failing-test-scaffolding-PLAN.md   # adds the xfail tests this plan flips green
provides:
  - "_substitute(content: bytes, request: Request) -> bytes helper in web/routes/dashboard.py"
  - "Single locality for {{WEB_AUTH_SECRET}}, {{SIGNOUT_BUTTON}}, {{SESSION_NOTE}}, {{TRACE_OPEN_<MARKET>}} resolution"
  - "Generalised TRACE_OPEN regex covers any market id matching ^[A-Z0-9_]{2,20}$"
affects:
  - "_serve_dashboard_content (now delegates to _substitute)"
  - "_serve_market_scoped_page (now calls _substitute before constructing Response)"
tech-stack:
  added: []
  patterns:
    - "Helper extraction with closure access to _is_cookie_session / _resolve_trace_open"
    - "Bytes-regex generalisation of per-market placeholder substitution"
key-files:
  created: []
  modified:
    - web/routes/dashboard.py
    - tests/test_web_dashboard.py
decisions:
  - "Helper lives inside register() (closure scope) so it can call _is_cookie_session and _resolve_trace_open without restructuring the session-serializer construction."
  - "Generalised _TRACE_OPEN_RE accepts any ^[A-Z0-9_]{2,20}$ market id; allowlist comes from _resolve_trace_open's existing _VALID_TRACE_INSTRUMENT_KEYS frozenset, so unknown markets resolve to closed (empty) without trusting the regex alone."
  - "Legacy _TRACE_OPEN_PLACEHOLDER_SPI200 / _AUDUSD module constants kept as no-op leftovers (purely additive plan; cleanup deferred to avoid widening diff)."
metrics:
  duration: ~25 minutes (excluding rebase recovery)
  completed: 2026-05-07
---

# Phase 26 Plan 04: Template Substitute Helper Summary

Single `_substitute(content: bytes, request: Request) -> bytes` helper unifies placeholder resolution across the dashboard.html serve path and the market-scoped serve path. B2 (placeholder leak) and B3 (header session widget never resolves on multi-tab pages) collapse into one fix per 26-PATTERNS §B2 most-eloquent option (A) / §B3 dissolves into B2.

## Helper signature

```python
def _substitute(content: bytes, request: Request) -> bytes:
    # web/routes/dashboard.py: defined inside register() at module-internal scope.
    # Pure bytes -> bytes; no Response coupling.
    ...
```

Resolves five placeholder kinds:

| Placeholder | Source of truth | Resolution |
| --- | --- | --- |
| `{{WEB_AUTH_SECRET}}` | `os.environ.get('WEB_AUTH_SECRET', '')` | direct replace |
| `{{SIGNOUT_BUTTON}}` | `_is_cookie_session(request)` true | `dashboard._render_signout_button()` HTML; else empty |
| `{{SESSION_NOTE}}` | `_is_cookie_session(request)` false | `dashboard._render_session_note()` HTML; else empty |
| `{{TRACE_OPEN_<MARKET>}}` | `_resolve_trace_open(request)` allowlist | `' open'` if `<MARKET>` in set, else empty. Generalised over any market id matching `^[A-Z0-9_]{2,20}$` via `_TRACE_OPEN_RE`. |

## Call sites (exactly two, per success criterion)

| Caller | Line | Path it serves |
| --- | --- | --- |
| `_serve_dashboard_content` | line 584 | `/`, `/signals`, `/account`, `/settings`, `/market-test` (file-on-disk dashboard.html and siblings) |
| `_serve_market_scoped_page` | line 290 | `/markets/{M}/{signals,settings,market-test}` (in-memory `render_dashboard_as_str`) |

```bash
$ grep -n "_substitute(" web/routes/dashboard.py
290:    body_bytes = _substitute(body.encode('utf-8'), request)
584:    content = _substitute(content, request)
```

## Hex-boundary discipline

- Helper imports remain LOCAL inside the function body (`from dashboard import _render_session_note, _render_signout_button`), per Phase 11 C-2 / Phase 13 D-07 / `tests/test_web_healthz.py::TestWebHexBoundary`.
- Renderer (`dashboard_renderer/`) untouched. `header.py:64-69`'s `is_cookie_session is None` punt-to-web branch still works — the web layer now substitutes on BOTH serve paths, not just the canonical one.
- No new imports from `web/middleware/` into renderer code.

## Logging prefix

No new `[Web]` warn/info lines required — substitution is hot-path; failures (missing env var) degrade to empty-string replacement, which is the existing Phase 14 behaviour.

## Test outcomes

```
$ pytest tests/test_web_dashboard.py -k "Phase26 and not MarketScoping" -v
tests/test_web_dashboard.py::TestPhase26PlaceholderLeak::test_market_signals_has_no_placeholder_markers PASSED
tests/test_web_dashboard.py::TestPhase26PlaceholderLeak::test_market_settings_has_no_placeholder_markers PASSED
tests/test_web_dashboard.py::TestPhase26PlaceholderLeak::test_market_market_test_has_no_placeholder_markers PASSED
tests/test_web_dashboard.py::TestPhase26HeaderSessionWidget::test_no_cookie_session_renders_session_note PASSED
tests/test_web_dashboard.py::TestPhase26HeaderSessionWidget::test_with_valid_cookie_session_renders_signout_button PASSED
tests/test_web_dashboard.py::TestPhase26PanelPatchSurvives::test_patch_with_extracted_secret_does_not_401 PASSED
======================= 6 passed, 45 deselected in 0.96s =======================
```

```
$ pytest tests/test_web_dashboard.py::TestAuthSecretPlaceholderSubstitution -v
4 passed, 1 skipped (skip is the canonical "dashboard.html not present in repo" guard, unchanged)
```

```
$ pytest -x  # full suite
1790 passed, 4 xfailed in 112.69s
```

The 4 remaining xfails are `TestPhase26MarketScoping` in `test_web_app_factory.py` — Plan 26-05 (B1) owns those; this plan deliberately did not touch them.

## Before / after grep counts for `{{[A-Z_]+}}`

Both counts are inside `web/routes/dashboard.py` only — every match is in a Python comment, docstring, or bytes literal (the substitution targets), not in served HTML.

```bash
$ git show HEAD~2:web/routes/dashboard.py | grep -c '{{[A-Z_]\+}}'
8                                  # before plan 26-04 (post 26-03 baseline)

$ grep -c '{{[A-Z_]\+}}' web/routes/dashboard.py
12                                 # after plan 26-04
```

The +4 net additions are the new `_substitute` docstring (4 placeholders enumerated) and the new comment in `_serve_market_scoped_page` mentioning the four placeholder kinds. None reach a response body.

End-to-end leak grep on served bytes is now exercised by `TestPhase26PlaceholderLeak.test_market_*_has_no_placeholder_markers`, which assert `re.search(r'\{\{[A-Z_]+\}\}', resp.text)` is None on every market-scoped GET. All three pass.

## Atomic commits

| Hash | Message |
| --- | --- |
| `9a49d88` | phase-26-04 task 1: extract _substitute helper for placeholder resolution (B2/B3) |
| `4e5f844` | phase-26-04 task 2: remove xfail decorators from now-passing Phase 26 tests |

## Deviations from Plan

**[Rule 3 — Blocker]** The worktree was checked out at `9874b3c` (pre-Phase-26 baseline) but Plan 26-04 declares `depends_on: 26-03-failing-test-scaffolding-PLAN.md`. The xfail test classes the plan references (TestPhase26PlaceholderLeak / HeaderSessionWidget / PanelPatchSurvives) only exist on `chore/document-nginx-sudoers` after `7b318c3`. Resolved by `git pull --rebase . chore/document-nginx-sudoers` after stashing pending edits, then popping. No conflicts. This is a worktree-setup concern, not a plan defect.

**[Coordination — Path resolution]** Initial Edit calls used the canonical absolute path `/Users/.../trading-signals/web/routes/dashboard.py` instead of the worktree's `/Users/.../.claude/worktrees/agent-.../web/routes/dashboard.py`, landing the first round of changes in the wrong checkout. Reverted those, re-applied to the worktree path. Final commits land on `worktree-agent-aae5dde9cbac3d2e7` only; main repo working tree untouched.

No other deviations. No auth gates encountered. No threat surface added (T-26-04..T-26-06 dispositions held).

## Self-Check: PASSED

- `web/routes/dashboard.py:514` — `def _substitute(content: bytes, request: Request) -> bytes:` FOUND.
- `web/routes/dashboard.py:290` — `_serve_market_scoped_page` calls `_substitute(body.encode('utf-8'), request)` FOUND.
- `web/routes/dashboard.py:584` — `_serve_dashboard_content` calls `_substitute(content, request)` FOUND.
- Commit `9a49d88` — present in `git log --oneline` FOUND.
- Commit `4e5f844` — present in `git log --oneline` FOUND.
- `tests/test_web_dashboard.py` — zero `pytest.mark.xfail` decorators remaining for Phase 26 classes (`grep -n "pytest.mark.xfail" tests/test_web_dashboard.py` returns no output) FOUND.
- Full pytest suite — exit 0, 1790 passed FOUND.
