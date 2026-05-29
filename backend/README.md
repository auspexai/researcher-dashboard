# auspexai-researcher-dashboard (backend)

Locally-run FastAPI backend for the AuspexAI researcher dashboard. Serves the
SvelteKit static bundle and signs tenant-scoped coordinator requests with the
researcher's tenant-SDK Ed25519 key (RFC 9421).

Single-tenant by construction: one key per instance, so one tenant's data per
instance. See `../README.md` and
`Documentation/AuspexAI/v0.1.0/researcher_dashboard_design.md`.

```bash
pip install -e ".[dev]"
auspexai-dashboard serve   # 127.0.0.1:4228, opens a browser
```
