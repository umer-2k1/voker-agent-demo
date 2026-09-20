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

## Run

```bash
source venv/bin/activate
uvicorn voker_voice_api.main:app --app-dir apps/api/src --reload --port 8001
pnpm dev:web
```

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
