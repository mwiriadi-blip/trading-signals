---
phase: 38
slug: news-integration
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-15
---

# Phase 38 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing — 2000+ tests) |
| **Config file** | `pytest.ini` or `pyproject.toml` |
| **Quick run command** | `.venv/bin/pytest -x --tb=short tests/test_news_filter.py tests/test_news_fetcher.py` |
| **Full suite command** | `.venv/bin/pytest -x --tb=short` |
| **Estimated runtime** | ~30–60 seconds (full suite) |

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/pytest -x --tb=short tests/test_news_filter.py tests/test_news_fetcher.py`
- **After every plan wave:** Run `.venv/bin/pytest -x --tb=short`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 38-??-01 | schema-normaliser | 1 | NEWS-03 | — | `<script>alert(1)</script>` headline renders as escaped text | unit | `.venv/bin/pytest -x tests/test_news_fetcher.py::test_both_shape_normalisation` | ❌ W0 | ⬜ pending |
| 38-??-02 | schema-normaliser | 1 | NEWS-03 | — | pre-0.2.55 flat fixture normalises to NewsItem | unit | `.venv/bin/pytest -x tests/test_news_fetcher.py::test_pre_schema` | ❌ W0 | ⬜ pending |
| 38-??-03 | schema-normaliser | 1 | NEWS-03 | — | post-0.2.55 nested fixture normalises to NewsItem | unit | `.venv/bin/pytest -x tests/test_news_fetcher.py::test_post_schema` | ❌ W0 | ⬜ pending |
| 38-??-04 | classifier | 1 | NEWS-02 | — | precision ≥0.7 and recall ≥0.9 on 30-headline fixture | unit | `.venv/bin/pytest -x tests/test_news_filter.py::test_classifier_precision_recall` | ❌ W0 | ⬜ pending |
| 38-??-05 | classifier | 1 | NEWS-02 | — | dampener allowlist suppresses false positives | unit | `.venv/bin/pytest -x tests/test_news_filter.py::test_dampener` | ❌ W0 | ⬜ pending |
| 38-??-06 | ast-boundary | 1 | NEWS-01 | — | `signal_engine` cannot import `news_fetcher` or `news_filter` | unit | `.venv/bin/pytest -x tests/test_signal_engine.py::TestDeterminism` | ✅ | ⬜ pending |
| 38-??-07 | ast-boundary | 1 | NEWS-01 | — | `news_filter.py` in `_HEX_PATHS_STDLIB_ONLY` | unit | `.venv/bin/pytest -x tests/test_signal_engine.py` | ✅ | ⬜ pending |
| 38-??-08 | dismiss | 2 | NEWS-04 | — | dismiss state is per-user isolated | unit | `.venv/bin/pytest -x tests/test_news_dismiss.py` | ❌ W0 | ⬜ pending |
| 38-??-09 | cache | 1 | NEWS-01 | — | cache file written atomically (tempfile + os.replace) | unit | `.venv/bin/pytest -x tests/test_news_fetcher.py::test_cache_atomic` | ❌ W0 | ⬜ pending |
| 38-??-10 | xss | 1 | NEWS-03 | — | Jinja2 autoescape renders `<script>` as `&lt;script&gt;` | integration | `.venv/bin/pytest -x tests/test_news_routes.py::test_xss_escape` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_news_fetcher.py` — stubs for NEWS-01, NEWS-03 (schema normalisation, cache, XSS)
- [ ] `tests/test_news_filter.py` — stubs for NEWS-02 (classifier precision/recall, dampener)
- [ ] `tests/test_news_dismiss.py` — stubs for NEWS-04 (dismiss isolation, per-user scoping)
- [ ] `tests/test_news_routes.py` — stubs for integration (route registration, XSS)
- [ ] `tests/fixtures/news_pre_schema.json` — hand-crafted pre-0.2.55 flat payload fixture
- [ ] `tests/fixtures/news_post_schema.json` — captured post-0.2.55 nested payload fixture
- [ ] `tests/fixtures/news_30_headlines.json` — labelled 30-headline fixture for classifier CI gate

*Existing infrastructure covers pytest; only new test files needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| News panel renders at bottom of `/markets/SPI200` | NEWS-01 | Browser render | Load dashboard, verify news panel below signal/calculator/drift panels |
| Panel collapses and state persists across reload | NEWS-01 | Browser HTMX | Click collapse, reload page, verify panel remains collapsed |
| Critical-event banner shows inside panel above headlines | NEWS-02 | Browser render | Trigger a keyword match, verify banner text "Possible market-moving news — operator review recommended" |
| Dismiss removes row immediately via HTMX | NEWS-04 | Browser HTMX | Click dismiss, verify row disappears without page reload |
| Dismissed headlines don't reappear after reload (same day) | NEWS-04 | Browser state | Dismiss a headline, reload page, verify it stays dismissed |
| Next-day dismissed items reset | NEWS-04 | Time-dependent | Manually change `news_dismissed.date` in state.json and reload |
| outbound links carry `rel="noopener noreferrer"` | NEWS-01 | Browser DOM | Inspect link elements in news panel |
| Admin dismiss does not affect F&F user's view | NEWS-04 | Multi-user | Log in as admin and F&F user in separate sessions, dismiss in one, check other |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
