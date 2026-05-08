"""dashboard_legacy — page-body orchestration + operator-form renderers.

Extracted from dashboard.py (Plan 27-14, Strategy B). The dashboard_renderer/
package owns component-level rendering; this package owns the legacy
page-body orchestration + operator forms + paper-trade subsections + account
region + Phase 17 trace panels + Phase 15 calc rows.

Hex-boundary preserved: stdlib + pytz + dashboard_renderer + system_params.
No imports from signal_engine / data_fetcher / notifier / main / numpy /
pandas / yfinance / requests at module top. Local sizing_engine + pnl_engine
imports inside function bodies preserved (C-2).

Phase 27 IN-04: this module was previously a 150-line re-export shim that
duplicated every symbol from every sub-module under the package namespace.
The shim was redundant — `dashboard.py` imports directly from
`dashboard_legacy.<submodule>`, no caller relies on `from dashboard_legacy
import X`. Reducing to docstring-only cuts maintenance churn.
"""
