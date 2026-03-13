# Ingestion Domain

Handles base Knowledge Graph ingestion from Google Drive via agent swarm.

## Responsibilities
- Google Drive OAuth2 (read-only, owner-only)
- File listing and downloading from Drive
- Agent swarm orchestration for parallel ingestion
- Progress tracking and failure handling
- Admin-only access (not user-facing)

## Key Files
- `interfaces.py` — `SourceConnector` ABC
- `drive_connector.py` — Google Drive connector (OAuth2, drive.readonly)
- `swarm.py` — Agent swarm orchestrator
- `models.py` — Ingestion job tracking models
- `schemas.py` — Pydantic request/response schemas
- `router.py` — Admin-only: trigger ingestion, check status
- `exceptions.py` — Typed ingestion errors

## Adding a New Source Connector
1. Create `your_source_connector.py`
2. Implement `YourSourceConnector(SourceConnector)`
3. Register in the swarm orchestrator
4. Write tests in `tests/`
