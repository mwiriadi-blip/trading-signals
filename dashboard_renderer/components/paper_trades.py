'''Paper trades component implementation.'''


def render_paper_trades_region(state: dict) -> str:
  import dashboard as d

  paper_trades = state.get('paper_trades', [])
  signals = state.get('signals', {})
  stats = d._compute_aggregate_stats(paper_trades, signals)
  return (
    '<div id="trades-region">\n'
    + d._render_paper_trades_stats(stats)
    + d._render_paper_trades_open_form()
    + d._render_paper_trades_open(paper_trades, signals)
    + d._render_close_form_section()
    + d._render_paper_trades_closed(paper_trades)
    + '</div>\n'
  )
