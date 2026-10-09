"""FastAPI backend for the TRAX dashboard.

Entry point: `uvicorn api.main:app --port 8788`.

This replaces nothing. The existing `service/trigger_server.py` keeps
serving n8n at 8787; this is an additional surface that gives the browser
and the local AI client a modern typed API without disturbing the Phase 9
pipeline. The two can run side-by-side.
"""
