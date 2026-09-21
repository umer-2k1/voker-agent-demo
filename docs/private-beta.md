# Private beta checklist

## Supported runtime

- Python 3.12 or 3.13 for the API and Python SDK.
- PostgreSQL 16+ with the migrations at `apps/api/migrations` applied.
- Node 22+ and pnpm 10+ for the React/Vite dashboard.
- Google OAuth redirect URLs must be registered for every deployed API origin.

## Backup and restore

Before every migration or deployment, create a database backup:

```bash
pg_dump --format=custom --file=voker-voice-$(date +%F).dump "$DATABASE_URL"
```

Restore only into an empty, isolated database after stopping API and worker processes:

```bash
pg_restore --clean --if-exists --no-owner --dbname="$DATABASE_URL" voker-voice-YYYY-MM-DD.dump
alembic -c apps/api/alembic.ini upgrade head
```

Verify `/health/ready`, one signed-in dashboard request, and a canonical ingest
fixture before allowing traffic. Do not store OAuth secrets, ingest keys, or
Cloudinary credentials in backups that are shared outside the approved recovery
location.

## Known beta limits

- Ingestion load and restart/partition exercises have not yet been run against a
  hosted beta environment.
- Hosted LiveKit end-to-end acceptance requires a running test agent.
- Vapi real-call acceptance is intentionally skipped until a test call can be connected.
- Retell acceptance requires an agent in the configured Retell account.
