# Knowledge Seeding Guide

DriveRAG has a two-tier knowledge architecture. This guide covers how to populate both tiers.

## Tier 1: Base Knowledge Graph (from Google Drive)

The base KG is permanent knowledge ingested from a Google Drive folder. Files are processed by an agent swarm that extracts entities, relationships, and embeddings.

### Step 1: Set Up Google Drive Access

You have two authentication options:

**Option A: Service Account (recommended for production)**

1. Go to [Google Cloud Console](https://console.cloud.google.com/) and create a project
2. Enable the **Google Drive API** (APIs & Services > Library)
3. Create a Service Account (IAM & Admin > Service Accounts)
4. Click **Keys > Add Key > Create new key > JSON** -- downloads a key file
5. Share your Drive folder with the Service Account email (found in the JSON as `client_email`) as **Viewer**
6. Set in `.env`:
   ```
   GOOGLE_SERVICE_ACCOUNT_FILE=/path/to/service-account.json
   ```
   Or for Docker/CI, paste the JSON inline:
   ```
   GOOGLE_SERVICE_ACCOUNT_JSON='{"type":"service_account",...}'
   ```

**Option B: OAuth2 with your personal Google account (no folder sharing needed)**

1. Go to [Google Cloud Console](https://console.cloud.google.com/) > APIs & Services > OAuth consent screen
2. Select **External**, fill in app name and emails, add yourself as a test user
3. Go to **Credentials** > Create Credentials > **OAuth client ID** > Application type: **Desktop app**
4. Copy the Client ID and Client Secret into `.env`:
   ```
   GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=GOCSPX-your-secret
   ```
5. Run the helper script to get a refresh token:
   ```bash
   cd backend && uv run python -m app.scripts.google_auth
   ```
   This opens your browser for Google login. Paste the printed token into `.env`:
   ```
   GOOGLE_REFRESH_TOKEN=1//0eXXXXXXXXXXXXX
   ```

Optionally set `GOOGLE_DRIVE_FOLDER_ID` in `.env` to restrict ingestion to a specific folder (the folder ID is the last segment of its Drive URL).

### Step 2: Trigger Ingestion

**From the UI (recommended):**

1. Log in as the admin account (`admin@dingdong.dev`)
2. Navigate to the Admin panel in the sidebar
3. Click **Trigger Ingestion**
4. The swarm scans the Drive folder, downloads PDF/DOCX/Google Docs files, extracts entities and relationships, and builds the knowledge graph

**From the API:**

```bash
curl -X POST http://localhost:8000/api/v1/ingestion/trigger \
  -H "Authorization: Bearer <admin-access-token>" \
  -H "Content-Type: application/json" \
  -d '{"folder_id": "optional-specific-folder-id", "force": false}'
```

Set `"force": true` to re-ingest files that were already processed.

The ingestion pipeline:
1. Authenticates with Google Drive
2. Scans for PDF, DOCX, and Google Docs files
3. Filters out already-ingested files (deduplication by Drive file ID)
4. Downloads and processes files in parallel (5 concurrent workers)
5. Extracts text, chunks documents, generates embeddings
6. Builds the knowledge graph (entities + relationships in Neo4j + PostgreSQL)
7. Detects updated files (by `modifiedTime`) and re-processes them automatically

### Step 3: Export the Graph (Optional)

Once your knowledge graph is built, you can export it to versioned JSONL seed files. This lets you ship a pre-built graph with the repo so others can self-host without needing Google Drive access.

```bash
make graph-export
```

This creates files in `backend/graph_seed/`:
```
graph_seed/
├── manifest.json                     # Version, checksums, file listing
├── schema/
│   └── constraints.cypher            # Neo4j indexes and constraints
├── entities/
│   ├── Person.jsonl                  # One JSONL file per entity type
│   ├── Organization.jsonl
│   └── ...
└── relationships/
    ├── WORKS_AT.jsonl                # One JSONL file per relationship type
    ├── RELATED_TO.jsonl
    └── ...
```

Files larger than 40MB are automatically sharded (e.g., `Person_001.jsonl`, `Person_002.jsonl`).

## Tier 1 (alternative): Seed from Local Files

If the repo already has exported graph seed files in `backend/graph_seed/`, you can populate the knowledge graph without Google Drive:

**Auto-seed on startup:**

The backend automatically seeds the graph from local files when Neo4j is empty and `graph_seed/manifest.json` exists. Just start the app -- it happens automatically during the lifespan startup.

**Manual seed:**

```bash
# Idempotent merge/upsert (safe to run multiple times)
make graph-seed

# Or wipe and re-import from scratch
make graph-seed-clean
```

**Apply schema only (indexes and constraints):**

```bash
make graph-schema
```

## Tier 2: User Uploads

Users can upload PDF and DOCX files through the web UI. These are:
- Stored in Supabase Storage (or local if not configured) with a **7-day TTL**
- Processed into text chunks and embeddings
- Added to the knowledge graph with source metadata
- Automatically cleaned up when they expire

No additional setup needed beyond the base configuration. Users upload files from the Documents page in the dashboard.

## Commands Reference

```bash
make graph-schema       # Apply Neo4j indexes and constraints (idempotent)
make graph-seed         # Import from local JSONL files (idempotent merge)
make graph-seed-clean   # Wipe graph + re-import from local files
make graph-export       # Export current graph to versioned JSONL files
```
