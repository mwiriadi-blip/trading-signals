'''Phase 28 / DEBT-01 / UAT-23-2: /backtest renders without template-leak artefacts.

Sourced from .planning/milestones/v1.2-phases/23-.../23-HUMAN-UAT.md UAT-2.

NOT in this file: Phase 23 UAT-1 (live yfinance CLI run). Per
CONTEXT.md D-15, that scenario is run-once via Bash by plan 06 and
is NOT persisted under tests/uat/ -- coupling the test suite to
live network availability is undesirable.

Deviation note (plan 28-04 -> Rule 1, captured in 28-04-SUMMARY.md):
the project does NOT use an external static-asset mount. `web/routes/
backtest.py::_wrap_html` returns a minimal shell with no <link
rel="stylesheet"> at all, and no FastAPI StaticFiles mount exists.
The missing-CSS regression marker has therefore been adapted from
'<link rel="stylesheet" href="/static/..."> present' to 'inline
<style> OR same-origin stylesheet <link> present' -- which honours
the asset-pipeline-regression failure mode CONTEXT.md specifics
calls out without producing a permanent false FAIL on a correct render.
'''
from __future__ import annotations

import re

import pytest

pytestmark = pytest.mark.uat

BACKTEST_PATH = '/backtest'

# Artefact set is fixed by 28-CONTEXT.md specifics block. Each entry is
# a distinct failure mode the smoke test must catch.
FORBIDDEN_LITERALS = (
  '{{',         # Jinja unrendered open
  '}}',         # Jinja unrendered close
  'Undefined',  # jinja2 Undefined str-repr leak
  'None None',  # Python None tuple/format str-repr leak
)

# Missing-CSS marker: at least one of (a) inline <style> block, or
# (b) same-origin stylesheet <link>. Zero of either => template / asset
# pipeline regression (page rendering as bare unstyled HTML).
INLINE_STYLE_RE = re.compile(r'<style\b[^>]*>', re.IGNORECASE)
EXTERNAL_STYLESHEET_RE = re.compile(
  r'<link[^>]+rel=["\']stylesheet["\']',
  re.IGNORECASE,
)


def test_backtest_page_has_no_template_leak_artefacts(page, base_url):
  response = page.goto(f'{base_url}{BACKTEST_PATH}')
  assert response is not None and response.ok, (
    f'GET {BACKTEST_PATH} failed: '
    f'status={response.status if response else "no-response"}'
  )

  html = page.content()

  # Each forbidden literal gets its own assertion so plan 06 root-cause
  # has a single named failure mode per FAIL line.
  assert '{{' not in html, (
    'Template-leak: unrendered Jinja open delimiter "{{" found in /backtest HTML. '
    'Suspected layer: backtest report Jinja template render or context dict.'
  )
  assert '}}' not in html, (
    'Template-leak: unrendered Jinja close delimiter "}}" found in /backtest HTML. '
    'Suspected layer: backtest report Jinja template render or context dict.'
  )
  assert 'Undefined' not in html, (
    'Template-leak: jinja2 Undefined str-repr leaked into /backtest HTML. '
    'Suspected layer: missing context key or undefined-strict mode disabled.'
  )
  assert 'None None' not in html, (
    'Template-leak: Python "None None" str-repr leaked into /backtest HTML. '
    'Suspected layer: tuple/format render of unset values upstream of template.'
  )

  has_inline = bool(INLINE_STYLE_RE.search(html))
  has_external = bool(EXTERNAL_STYLESHEET_RE.search(html))
  assert has_inline or has_external, (
    'Missing-CSS regression: /backtest HTML has neither inline <style> nor '
    '<link rel="stylesheet">. Suspected layer: _wrap_html in '
    'web/routes/backtest.py or asset pipeline.'
  )
