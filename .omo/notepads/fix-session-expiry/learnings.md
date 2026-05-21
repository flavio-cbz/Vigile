# Session Expiry Fix - Learnings

- HTMX fragment endpoints in `master/api/frontend.py` were returning empty HTML with 200 when JWT expired, causing silent blank panels.
- Fix: Replace `return HTMLResponse("")` with `return HTMLResponse(..., headers={"HX-Redirect": "/login?reason=expired"})` in all 4 fragment endpoints.
- HTMX intercepts the `HX-Redirect` response header for client-side navigation — no 302 redirect needed.
- Keep HTML body visible even with HX-Redirect header for graceful degradation.
- `HTMLResponse` is already imported (used in `response_class` decorators and existing returns).
