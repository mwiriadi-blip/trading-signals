'''Phase 38 Plan 04 — news panel renderer.

Python f-string component (NOT Jinja2 — this codebase never uses Jinja2;
see dashboard_renderer/components/trace.py for the established pattern).

Public API:
  render_news_panel(market_id, headlines, dismissed_hashes, collapsed) -> str

Security:
  - html.escape() applied to EVERY dynamic value before f-string interpolation
    (T-38-04-01 XSS mitigation — render-time escape, not fetch-time)
  - rel="noopener noreferrer" on every headline anchor (T-38-04-02)
  - dismissed hashes filtered BEFORE has_critical_event is called (T-38-04-11):
    if the user dismisses the only triggering headline, the banner disappears
'''
import html

from news_fetcher import NewsResult
from news_filter import has_critical_event


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _render_news_banner() -> str:
  '''Critical-event banner — locked copy per CONTEXT.md D-07 / ROADMAP.

  Do NOT rephrase. Contains em-dash U+2014.
  '''
  return (
    '<div class="news-banner">'
    '<p class="news-banner-heading">'
    'Possible market-moving news — operator review recommended'
    '</p></div>\n'
  )


def _render_headline_row(mkt_esc: str, item: dict) -> str:
  '''Render a single headline <tr>.

  All dynamic values are html.escape()'d before interpolation.
  rel="noopener noreferrer" is mandatory on the anchor (T-38-04-02).
  Dismiss button uses HTMX hx-post + hx-target + hx-swap.
  '''
  title_hash_esc = html.escape(item.get('title_hash', ''), quote=True)
  title_esc = html.escape(item.get('title', ''))
  url_esc = html.escape(item.get('url', ''), quote=True)
  publisher_esc = html.escape(item.get('publisher', ''))
  pub_date_esc = html.escape(item.get('pub_date', ''))
  return (
    f'<tr id="news-row-{title_hash_esc}">'
    f'<td class="news-link">'
    f'<a href="{url_esc}" target="_blank" rel="noopener noreferrer">{title_esc}</a>'
    f'</td>'
    f'<td class="news-meta">{publisher_esc} · {pub_date_esc}</td>'
    f'<td>'
    f'<button type="button" class="btn-news-dismiss"'
    f' hx-post="/news/{mkt_esc}/dismiss/{title_hash_esc}"'
    f' hx-target="#news-row-{title_hash_esc}"'
    f' hx-swap="outerHTML"'
    f' hx-trigger="click">'
    f'Dismiss Headline'
    f'</button>'
    f'</td>'
    f'</tr>\n'
  )


def _render_empty_state() -> str:
  return '<p class="subtle">No headlines today.</p>\n'


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_news_panel(
  market_id: str,
  headlines: list,
  dismissed_hashes: frozenset | set,
  collapsed: bool,
) -> str:
  '''Render the news panel <details> for a single market.

  Implementation order (critical — review HIGH #4):
  1. Filter dismissed BEFORE banner evaluation.
  2. has_critical_event evaluated on the FILTERED list.
  3. Build HTML with open_attr, banner, rows.

  All dynamic values passed through html.escape() (T-38-04-01).
  rel="noopener noreferrer" on every anchor (T-38-04-02).
  '''
  # Step 1 — filter dismissed hashes BEFORE banner check
  filtered = [h for h in headlines if h.get('title_hash') not in dismissed_hashes]

  # Step 2 — evaluate banner on POST-FILTER list (T-38-04-11).
  # Wrap filtered list into a NewsResult (error=None — headlines were already
  # successfully fetched by the caller; render-time wrapping preserves the
  # D-02 contract without requiring news.py to consume a NewsResult directly).
  _result_for_filter = NewsResult(items=filtered, error=None)
  _event = has_critical_event(_result_for_filter, market_id)
  has_critical = _event.triggered

  # Step 3 — build HTML
  open_attr = '' if collapsed else ' open'
  mkt_esc = html.escape(market_id, quote=True)

  banner_html = _render_news_banner() if has_critical else ''
  rows_html = (
    ''.join(_render_headline_row(mkt_esc, h) for h in filtered)
    if filtered else _render_empty_state()
  )

  return (
    f'<details class="news-panel-disclosure"{open_attr}'
    f' hx-post="/news/{mkt_esc}/toggle-collapse"'
    f' hx-trigger="toggle"'
    f' hx-swap="none">\n'
    f'<summary class="news-panel-summary">Market News</summary>\n'
    f'<div class="news-panel-inner">\n'
    f'{banner_html}'
    f'<table class="news-table">\n'
    f'<tbody>\n'
    f'{rows_html}'
    f'</tbody>\n'
    f'</table>\n'
    f'</div>\n'
    f'</details>\n'
  )
