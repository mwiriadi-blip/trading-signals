---
phase: 27
plan: 15
subsystem: comment-only fossil cleanup — stale `notifier.py` references in production source
tags:
  - phase-27
  - cleanup
  - comment-only
  - notifier-package
  - post-split-hygiene
dependency_graph:
  requires:
    - 27-12-notifier-split-PLAN.md  # CR-01 deleted notifier.py monolith
    - 27-14-dashboard-split-PLAN.md  # introduced dashboard_legacy/ peer
  provides:
    - "Bucket A scrubbed: zero `notifier.py` refs in production source comments describing CURRENT architecture."
    - "Bucket B preserved: history breadcrumbs (CR-01 fix markers, Plan 27-12 provenance, test path constants) intact."
completed: 2026-05-08
---

## Outcome

7 line-edits across 5 files. Zero behavioural diff. 2028/2028 full suite green.

## Files modified

| File | Line | Before | After |
|---|---|---|---|
| system_params.py | 264 | `dashboard.py and notifier.py when state['_resolved_contracts']` | `dashboard.py and the notifier package when state['_resolved_contracts']` |
| system_params.py | 336 | `notifier.py can import the same palette` | `the notifier package can import the same palette` |
| crash_boundary.py | 39 | `import-time errors in notifier.py` | `import-time errors in the notifier package` |
| web/app.py | 4 | `peer of notifier.py, dashboard.py` | `peer of notifier/, dashboard_legacy/, dashboard.py shim` |
| web/middleware/auth.py | 33 | `peer of web/routes/, notifier.py` | `peer of web/routes/, notifier/` |
| tests/test_setup_https_doc.py | 7 | `notifier.py (Plan 02) — SIGNALS_EMAIL_FROM env var name` | `notifier package (Plan 02 + 27-12 split) — SIGNALS_EMAIL_FROM env var name` |
| tests/test_setup_https_doc.py | 281 | `nginx/signals.conf (Plan 01), deploy.sh (Plan 03), or notifier.py` | `nginx/signals.conf (Plan 01), deploy.sh (Plan 03), or the notifier package` |

## Verification

```
$ grep -nE 'notifier\.py' system_params.py crash_boundary.py web/app.py web/middleware/auth.py tests/test_setup_https_doc.py
(zero output — Bucket A clean)

$ grep -c 'notifier\.py' notifier/__init__.py tests/test_notifier.py state_manager.py tests/test_crash_email_fallback.py
notifier/__init__.py:2
tests/test_notifier.py:6
state_manager.py:1
tests/test_crash_email_fallback.py:1
(Bucket B preserved as designed)

$ .venv/bin/pytest --tb=short
2028 passed in 161.74s
```

## Bucket B (intentionally preserved)

- `notifier/*.py` module headers: "Extracted from notifier.py in Plan 27-12 (notifier package split)" — historical provenance for git archaeology.
- `tests/test_*.py` "CR-01 fix:" / "WR-06 fix:" deletion-event markers — explain to future readers why each test scans `notifier/*.py` instead of one file.
- `TEST_NOTIFIER_PATH = Path('tests/test_notifier.py')` constants in `tests/test_notifier.py:60` and `tests/test_signal_engine.py:478` — point at the live test FILE, not the deleted module.
- `notifier/transport.py:7` — `notifier.requests.post` is a Python attribute path used by monkeypatch, not the deleted file.
- `tests/test_notifier_magic_link.py:89, 202` — descriptive style references ("notifier.py palette aesthetic", "notifier.py convention"); not architecturally misleading.
- `state_manager.py:494` — points at `tests/test_notifier.py::TestDetectSignalChanges::...` — test file path.

If a future reviewer wants to scrub these too, that's a separate phase.
