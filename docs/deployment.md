# Production Deployment

## Backend (VPS/Cloud)

1. Build the production Docker image:
   ```bash
   make build-backend
   ```
2. The production image uses a non-root user, runs 4 Uvicorn workers, and includes a health check
3. Deploy with your `.env` file (or environment variables) pointing to your production databases
4. Run migrations against production Postgres:
   ```bash
   make migrate
   ```

## Frontend (Vercel or Docker)

**Vercel:**
- Set `NEXT_PUBLIC_API_URL` to your backend's public URL
- Deploy the `frontend/` directory

**Docker:**
```bash
make build-frontend
docker run -p 3000:3000 -e NEXT_PUBLIC_API_URL=https://your-api.com/api/v1 openrag-frontend
```

## Infrastructure Checklist

- [ ] PostgreSQL 17 with pgvector extension
- [ ] Neo4j 5 (Community Edition) with APOC plugin
- [ ] Redis 7
- [ ] Supabase project (for file storage) or alternative storage
- [ ] At least one LLM API key (Anthropic or OpenAI)
- [ ] `JWT_SECRET_KEY` set to a strong random value
- [ ] Database migrations applied (`make migrate`)
- [ ] Admin account created (`make seed` or register via API)
- [ ] Google Drive configured (if using base KG ingestion)
