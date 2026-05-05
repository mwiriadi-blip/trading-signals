'''Paper trades component implementation.'''


def render_paper_trades_region(state: dict) -> str:
  import dashboard as d

  paper_trades = state.get('paper_trades', []) or []
  signals = state.get('signals', {})
  stats = d._compute_aggregate_stats(paper_trades, signals)

  # Phase 25 D-10: omit stats bar from DOM until at least one closed trade
  # exists (closed paper + closed live combined). Zero DOM — not display:none.
  closed_paper = sum(
    1 for t in paper_trades
    if isinstance(t, dict) and t.get('status') == 'closed'
  )
  closed_trades = state.get('closed_trades', []) or []
  closed_live = len(closed_trades)
  stats_html = d._render_paper_trades_stats(stats) if (closed_paper + closed_live) >= 1 else ''

  return (
    '<div id="trades-region">\n'
    + stats_html
    + d._render_paper_trades_open_form()
    + d._render_paper_trades_open(paper_trades, signals)
    + d._render_close_form_section()
    + d._render_paper_trades_closed(paper_trades)
    + '</div>\n'
  )
