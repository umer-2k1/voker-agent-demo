# Voker Voice operational runbook

## Health and queue checks

`GET /health` verifies process liveness. `GET /health/ready` verifies database
reachability and returns the number of durable jobs waiting for processing.

Run a worker continuously in each environment:

```bash
source venv/bin/activate
while true; do voker-voice-api worker-once; sleep 2; done
```

Schedule `voker-voice-api expire-recordings` at the configured retention interval.
It revokes expired recording references while keeping sessions, transcripts, and
all other trace evidence intact.

For an available Cloudinary recording, the dashboard/API must request
`GET /api/projects/{project}/sessions/{session}/recordings/{recording}/playback`.
The API verifies that the recording belongs to that trace, then redirects to a
five-minute authenticated Cloudinary download URL. Do not store or expose that
signed URL as a persistent recording reference.

Jobs use database leases. A replacement worker automatically returns expired
leases to the retry queue; dead jobs retain their final error for investigation.

## Deployment and migrations

1. Back up PostgreSQL before applying a migration.
2. Run `alembic -c apps/api/alembic.ini upgrade head`.
3. Start API and worker processes, then check `/health/ready`.
4. Send a canonical fixture and verify its session, trace, and analysis jobs.

For a development rollback only, use `alembic -c apps/api/alembic.ini downgrade -1`
after confirming no later migration has stored production data.

## Incident handling

- Ingest unavailable: customers’ SDK exporters remain fail-open; restore the API,
  then inspect retry/dead jobs.
- Worker unavailable: raw traces continue to ingest; restart workers and allow
  durable queued analysis/webhook jobs to drain.
- Provider webhook failures: confirm the integration status, delivery token, and
  webhook receipt state before retrying through the provider.
- Recording unavailable: preserve the trace and expose recording state; never
  replace a missing recording with a public asset URL.
