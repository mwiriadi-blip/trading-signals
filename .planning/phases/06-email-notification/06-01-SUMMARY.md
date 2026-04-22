---
phase: 6
plan: 1
subsystem: email-notification
tags: [email, resend, scaffold, palette-retrofit, hex-boundary]

requires:
  - phase 5 (dashboard hex landed)
  - CLAUDE.md [Email] log prefix locked
  - PROJECT.md: signals@carbonbookkeeping.com.au verified Resend sender
provides:
  - notifier.py hex skeleton (3 public + 2 private stubs, ResendError class, config constants)
  - _COLOR_* palette constants in system_params.py (shared by dashboard + notifier)
  - tests/test_notifier.py 6-class skeleton + 3 JSON fixtures + 3 placeholder goldens
  - tests/regenerate_notifier_golden.py operator-only regenerator stub
  - AST blocklist FORBIDDEN_MODULES_NOTIFIER (hex boundary enforced structurally)
  - .env.example + .gitignore for secrets/artifact discipline
affects:
  - dashboard.py (palette import widened; 9 inline _COLOR_* definitions deleted)
  - tests/test_signal_engine.py (FORBIDDEN_MODULES_NOTIFIER + test_notifier_no_forbidden_imports added)

tech-stack:
  added: []
  patterns:
    - Hex-lite I/O module (notifier peer of dashboard / state_manager / data_fetcher)
    - Shared palette constants in system_params (breaks dashboard/notifier mutual coupling)
    - AST blocklist parametrized per-hex (symmetric boundary enforcement)
    - Nyquist Dimension 8 placeholder tests (pytest.raises(NotImplementedError) + pytest.xfail)

key-files:
  created:
    - notifier.py
    - tests/test_notifier.py
    - tests/regenerate_notifier_golden.py
    - tests/fixtures/notifier/sample_state_with_change.json
    - tests/fixtures/notifier/sample_state_no_change.json
    - tests/fixtures/notifier/empty_state.json
    - tests/fixtures/notifier/golden_with_change.html
    - tests/fixtures/notifier/golden_no_change.html
    - tests/fixtures/notifier/golden_empty.html
    - .env.example
  modified:
    - system_params.py
    - dashboard.py
    - tests/test_signal_engine.py
    - .gitignore

decisions:
  - D-01: notifier.py is a new I/O hex peer; must NOT import signal_engine, sizing_engine, data_fetcher, dashboard, main, numpy, pandas, yfinance
  - D-02: Palette constants migrated from dashboard.py module-level to system_params.py (single shared source for dashboard + notifier)
  - D-14: _EMAIL_FROM='signals@carbonbookkeeping.com.au' hardcoded (verified Resend sender); _EMAIL_TO_FALLBACK='mwiriadi@gmail.com' (operator-confirmed Option C per REVIEWS.md)
  - Ruff isort order applied (underscore-prefix names sorted first) — deviation from plan's alphabetical prescription; required by pyproject.toml ruff config
  - Placeholder test docstrings trimmed to line-length=100 (ruff E501) — deviation from plan prescription

metrics:
  duration: ~20 minutes
  completed: 2026-04-22
  tasks_total: 3
  tasks_completed: 3
  files_created: 10
  files_modified: 4
  commits: 3
  tests_passing: 399
  tests_xfailed: 2
---

# Phase 6 Plan 1: Wave 0 Scaffold Summary

**One-liner:** Phase 6 Wave 0 scaffold — palette retrofit to system_params, notifier.py hex skeleton with 5 NotImplementedError stubs + ResendError, AST blocklist FORBIDDEN_MODULES_NOTIFIER, tests/test_notifier.py 6-class Nyquist D-8 skeleton, 3 JSON fixtures + 3 placeholder goldens + regenerator, .env.example secrets placeholder, .gitignore last_email.html.

## Completed Tasks

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Palette retrofit — move _COLOR_* to system_params.py; dashboard.py imports widen | `6cfb440` | system_params.py, dashboard.py |
| 2 | notifier.py skeleton + AST blocklist + .env.example + .gitignore | `bb6b26e` | notifier.py, tests/test_signal_engine.py, .env.example, .gitignore |
| 3 | tests/test_notifier.py 6-class skeleton + 3 JSON fixtures + 3 placeholder goldens + regenerator | `454f39a` | tests/test_notifier.py, tests/regenerate_notifier_golden.py, tests/fixtures/notifier/ (6 files) |

## Key Artifacts

### Palette Constants in system_params.py (9 hex values)

Landed verbatim from dashboard.py; zero hex drift confirmed by Phase 5 golden byte-equal check:

```python
_COLOR_BG: str = '#0f1117'
_COLOR_SURFACE: str = '#161a24'
_COLOR_BORDER: str = '#252a36'
_COLOR_TEXT: str = '#e5e7eb'
_COLOR_TEXT_MUTED: str = '#cbd5e1'
_COLOR_TEXT_DIM: str = '#64748b'
_COLOR_LONG: str = '#22c55e'
_COLOR_SHORT: str = '#ef4444'
_COLOR_FLAT: str = '#eab308'
```

### notifier.py (192 lines)

Five NotImplementedError stubs with Wave annotations:

| Function | Wave | Message |
|----------|------|---------|
| `compose_email_subject` | Wave 1 | `Wave 1 (06-02): compose_email_subject per D-04` |
| `compose_email_body` | Wave 1 | `Wave 1 (06-02): compose_email_body per D-07/D-10` |
| `send_daily_email` | Wave 2 | `Wave 2 (06-03): send_daily_email per D-13` |
| `_post_to_resend` | Wave 2 | `Wave 2 (06-03): _post_to_resend retry loop` |
| `_atomic_write_html` | Wave 2 | `Wave 2 (06-03): _atomic_write_html (dashboard mirror)` |

Plus: `ResendError(Exception)` class, `_EMAIL_FROM` / `_EMAIL_TO_FALLBACK` / retry constants / `_INSTRUMENT_DISPLAY_NAMES_EMAIL` / `_CONTRACT_SPECS_EMAIL`.

### AST Blocklist (Hex Boundary)

`FORBIDDEN_MODULES_NOTIFIER = frozenset({'signal_engine', 'sizing_engine', 'data_fetcher', 'dashboard', 'main', 'numpy', 'pandas', 'yfinance'})` — 8 forbidden modules. `test_notifier_no_forbidden_imports` passes green.

### Test Skeleton (6 classes × 1 placeholder = 6 collected tests)

| Class | Placeholder Method | Pass Mechanism |
|-------|-------------------|----------------|
| TestComposeSubject | test_scaffold_placeholder_compose_subject | pytest.raises(NotImplementedError, match='Wave 1') |
| TestComposeBody | test_scaffold_placeholder_compose_body | pytest.raises(NotImplementedError, match='Wave 1') |
| TestFormatters | test_scaffold_placeholder_formatters | pytest.xfail('Wave 1 fills …') |
| TestSendDispatch | test_scaffold_placeholder_send_dispatch | pytest.raises(NotImplementedError, match='Wave 2') |
| TestResendPost | test_scaffold_placeholder_resend_post | pytest.raises(NotImplementedError, match='Wave 2') |
| TestGoldenEmail | test_scaffold_placeholder_golden_with_change | pytest.xfail('Wave 2 fills …') |

## Verification Results

| Check | Result |
|-------|--------|
| Full suite `pytest tests/ -x` | **399 passed, 2 xfailed** |
| Ruff clean `ruff check .` | **All checks passed** |
| AST hex boundary `test_notifier_no_forbidden_imports` | **green** |
| Phase 5 dashboard golden byte-identical | **70/70 green, zero drift** |
| `import notifier` + all 6 public/private symbols present | **stub OK** |
| 3 JSON fixtures + 3 HTML goldens under tests/fixtures/notifier/ | **6 files present** |
| Skeleton collects 6 placeholder tests | **6** |
| `.env.example` starts with `RESEND_API_KEY=re_xxx` (placeholder) | **OK** |
| `.gitignore` contains `last_email.html` on line 3 | **OK** |
| Palette count system_params.py / dashboard.py | **9 / 0** |
| `tests/regenerate_notifier_golden.py` raises NotImplementedError | **OK (Wave 1 fills)** |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Ruff isort order (I001) — applied ruff-fix to notifier.py, dashboard.py, tests/test_notifier.py**
- **Found during:** Tasks 2 + 3 (after verify step)
- **Issue:** Plan prescribed alphabetical `from system_params import (...)` order with underscore names at bottom. Ruff's isort enforces underscore-prefix names FIRST (case-insensitive sort with underscore < letter).
- **Fix:** Ran `ruff check --fix` which reordered imports automatically. Required because success criteria includes "ruff check passes clean" as a gate.
- **Files modified:** notifier.py (7 lines reordered), dashboard.py (16 lines reordered), tests/test_notifier.py (1 import block expanded)
- **Commits:** `bb6b26e` (Task 2), `454f39a` (Task 3)

**2. [Rule 3 - Blocking] E501 line-too-long in placeholder docstrings**
- **Found during:** Task 3 ruff check post-write
- **Issue:** Plan prescribed verbose single-line docstrings for placeholder tests ("Nyquist Dimension 8: one placeholder test per requirement (NOTF-XX) — passes via pytest.raises(NotImplementedError)."). These exceed the project's `line-length=100` in pyproject.toml.
- **Fix:** Split docstrings across multiple lines while preserving semantic content (NOTF-XX references + Wave annotations intact).
- **Files modified:** tests/test_notifier.py (5 docstrings reformatted)
- **Commit:** `454f39a`

### Architectural Decisions (no deviation)

None. Plan executed exactly as written for architectural structure: 3-task split, file paths, function signatures, fixture shapes, hex values, AST blocklist contents, palette constants, and exception class structure all landed as specified.

## Hex Boundary Confirmation

notifier.py imports only:
- stdlib: html, json, logging, os, tempfile, time, datetime, pathlib
- Third-party: pytz, requests
- Project: state_manager.load_state, system_params (palette + contract specs)

All 7 forbidden sibling imports (signal_engine, sizing_engine, data_fetcher, dashboard, main, numpy, pandas, yfinance) are absent. Structurally enforced by `tests/test_signal_engine.py::TestDeterminism::test_notifier_no_forbidden_imports`.

## Next Wave

**Wave 1 (06-02):** Fill `compose_email_subject` (D-04 — 6 subject-template cases), `compose_email_body` (D-07/D-08/D-10/D-11 — 7-section body + ACTION REQUIRED conditional + XSS escape), all formatters (_fmt_currency_email, _fmt_percent_*_email, _fmt_pnl_with_colour_email, _fmt_em_dash_email, _fmt_last_updated_email, _fmt_instrument_display_email), `_detect_signal_changes` helper. Populate TestComposeSubject, TestComposeBody, TestFormatters.

**Wave 2 (06-03) PHASE GATE:** Fill `_post_to_resend` (D-12 + 429 special-case), `send_daily_email` (D-13 + D-14 + never-crash), `_atomic_write_html` (dashboard mirror). Main.py dispatch wiring for --force-email + --test. Regenerate goldens + byte-equal assertions. Populate TestSendDispatch, TestResendPost, TestGoldenEmail.

## Threat Model Coverage

| Threat ID | Mitigation Status |
|-----------|-------------------|
| T-06-01 Tampering: notifier.py hex boundary | **mitigated** — FORBIDDEN_MODULES_NOTIFIER + test_notifier_no_forbidden_imports (Task 2) |
| T-06-02 Info Disclosure: RESEND_API_KEY in .env.example | **mitigated** — literal `re_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` placeholder (40 'x' chars); no entropy (Task 2) |
| T-06-03 Info Disclosure: last_email.html commit leak | **mitigated** — `.gitignore` line 3 `last_email.html` (Task 2) |
| T-06-04 Tampering: Phase 5 dashboard regression | **mitigated** — TestGoldenSnapshot byte-equal confirmed post-retrofit; 70/70 tests green (Task 1) |

No threat flags introduced (no new network/auth/file-access/schema surface in Wave 0 — it's pure scaffold).

## Self-Check: PASSED

- [x] notifier.py exists and imports cleanly
- [x] tests/test_notifier.py 6-class skeleton collects 6 tests, all pass (4 raises + 2 xfail)
- [x] 3 JSON fixtures + 3 HTML goldens present under tests/fixtures/notifier/
- [x] tests/regenerate_notifier_golden.py exists and raises NotImplementedError as expected
- [x] .env.example + .gitignore landed with correct contents
- [x] FORBIDDEN_MODULES_NOTIFIER + test_notifier_no_forbidden_imports in tests/test_signal_engine.py
- [x] Palette constants migrated to system_params.py (9 _COLOR_* names); dashboard.py has 0 inline
- [x] Full suite 399 passed + 2 xfailed; ruff clean
- [x] 3 commits on this worktree (6cfb440, bb6b26e, 454f39a) verified via git log
