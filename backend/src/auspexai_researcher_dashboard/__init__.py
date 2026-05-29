"""AuspexAI researcher dashboard — tenant-scoped, locally-run researcher view.

R-D0 (this milestone): scaffold the FastAPI backend + SvelteKit static
frontend; `auspexai-dashboard serve` starts a local HTTP server and opens
the browser. Serves a placeholder page + a health probe that also reports
coordinator connectivity and whether the researcher's SDK key is present.
No authenticated coordinator calls yet — RFC 9421 request signing (via the
tenant SDK) lands in R-D1/R-D2. See researcher_dashboard_design.md.
"""

from __future__ import annotations

__version__ = "0.1.0"
