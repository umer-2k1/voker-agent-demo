# Voker Voice development

The repository is a monorepo with a FastAPI API, React/Vite dashboard, Python SDK, and shared event schemas.

## Prerequisites

- Python 3.12+
- Existing local `venv`
- Node 22+
- `pnpm` 10.5+
- Docker Desktop for local PostgreSQL

## Bootstrap

```bash
source venv/bin/activate
python -m pip install -e "apps/api[dev]" -e "packages/python-sdk[dev]"
pnpm install
docker compose up -d postgres
```

The local database connection defaults to:

```text
postgresql+psycopg://voker:voker_dev@localhost:5432/voker_voice
```

Set a different `DATABASE_URL` only for an alternate local or hosted database. Do not put secrets into this document.

The ignored root `.env` is the active configuration source. When it provides `DATABASE_URL`, it takes precedence over the local Compose default. The configured development database is migrated and seeded with:

```bash
source venv/bin/activate
alembic -c apps/api/alembic.ini upgrade head
voker-voice-api seed
```

Create a local ingest key when testing the API manually. The command prints the raw key once; save it only in the ignored `.env` or your local shell session, never in source or logs:

```bash
voker-voice-api create-ingest-key --label "Local API testing"
```

## Run

```bash
source venv/bin/activate
uvicorn voker_voice_api.main:app --app-dir apps/api/src --reload --port 8001
pnpm dev:web
```

For authenticated live trace refresh in the local dashboard, set `VITE_INGEST_KEY`
in the ignored root `.env` to a locally created ingest key. It is optional: the
dashboard remains usable without it, but in-progress traces will refresh only on
manual navigation.

## Validate

```bash
source venv/bin/activate
python -m ruff check apps/api packages/python-sdk
python -m pytest
pnpm lint:web
pnpm test:web
pnpm build:web
```

Live integration tests read credentials from the ignored root `.env`. They must skip with an explicit reason when the relevant provider configuration is absent.

## Dashboard snapshots

With the API and Vite dashboard running locally, capture the current visual
states with:

```bash
node scripts/capture-dashboard-snapshots.mjs
```

Images are written to the ignored `artifacts/dashboard-snapshots/` folder. The
script captures the login page and the protected-route sign-in states; it does
not bypass Google OAuth to fabricate authenticated evidence.
