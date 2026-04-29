# Deferred Items — Phase 16.1

Out-of-scope discoveries logged during 16.1-01 execution. NOT caused by this plan; pre-existing failures confirmed via `git stash` baseline run on `2e5d9aa`.

## Pre-existing test failures (do NOT block 16.1-01 closure)

1. `tests/test_nginx_signals_conf.py::TestNginxConfStructure::test_listen_443_ssl`
   — Expects `listen 443 ssl;` in `nginx/signals.conf` but file uses `listen 443 ssl http2;` (post-quick-260426-vcw drift). Unrelated to auth.

2. `tests/test_setup_https_doc.py::TestCrossArtifactDriftGuard::test_owned_domain_placeholder_matches_nginx_conf`
   — Expects `<owned-domain>` placeholder; live conf has hardcoded `signals.mwiriadi.me`. Same root cause as #1.

3. `tests/test_notifier.py::test_ruff_clean_notifier`
4. `tests/test_notifier.py::test_ruff_clean_notifier_detects_f401_regression`
   — Both fail with `FileNotFoundError` (likely `ruff` binary not on PATH in test env). Local-tool issue, not source-of-truth.

All four failures reproduce on the parent commit `2e5d9aa` BEFORE any 16.1-01 Task 5 staged changes are applied. Tracked here for a future `/gsd-debug` or `/gsd-quick` cleanup pass.

— Date: 2026-04-29
