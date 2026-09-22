# Voker imperfect-agent playground

A small FastAPI service for generating useful Voker observability data. It runs a LangGraph ReAct agent through OpenRouter, gives it three local tools and three tools dynamically loaded from a local stdio MCP server, and records model, tool, MCP, and graph failures to Voker.

## Run the Voker Voice dashboard locally

### Prerequisites

- Python 3.12+
- Node.js 22+
- pnpm 10.5+
- Docker Desktop

### First-time setup

From the repository root:

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install -U pip
python -m pip install -e "apps/api[dev]" -e "packages/python-sdk[dev]"
pnpm install
docker compose up -d postgres
cp .env.example .env
alembic -c apps/api/alembic.ini upgrade head
voker-voice-api seed
```

To add realistic local-only dashboard data for UI review:

```bash
voker-voice-api seed-demo --count 40
```

The demo seed is idempotent and only creates missing `demo-call-*` records.

### Start the backend

Open a terminal in the repository root:

```bash
source venv/bin/activate
uvicorn voker_voice_api.main:app --app-dir apps/api/src --reload --host localhost --port 8001
```

Backend URLs:

- API: <http://localhost:8001>
- OpenAPI documentation: <http://localhost:8001/docs>
- Health check: <http://localhost:8001/health>

### Start the frontend

Open a second terminal in the repository root:

```bash
pnpm dev:web -- --host localhost
```

Open the dashboard at <http://localhost:5173>.

Use the same host name for both services. Do not mix `localhost` and
`127.0.0.1`, because browser session cookies are host-specific. Local Google
sign-in also requires `SESSION_SECRET`, `GOOGLE_CLIENT_ID`, and
`GOOGLE_CLIENT_SECRET` in the ignored root `.env`; configure the Google callback
as `http://localhost:8001/auth/google/callback`.

For additional environment, ingest-key, validation, and snapshot instructions,
see [`docs/development.md`](docs/development.md).

## Legacy imperfect-agent demo setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -U pip
pip install -r requirements.txt
cp .env.example .env
```

Set `OPENROUTER_API_KEY` and `VOKER_API_KEY` in `.env`. `VOKER_API_KEY` comes from the [Voker setup page](http://app.voker.ai/c/-selector-/projects/1/default-project/setup). Choose any OpenRouter model that supports tool calling; the default is `openai/gpt-4.1-mini`.

## Run

```bash
uvicorn app.main:app --reload
```

Then open <http://127.0.0.1:8000/docs>, or run:

```bash
curl -X POST http://127.0.0.1:8000/agent/run \
  -H 'content-type: application/json' \
  -d '{"message":"Check WIDGET-1 inventory, then use MCP to get our refund policy."}'
```

Reuse the returned `session_id` in subsequent requests to keep an entire conversation grouped under one Voker session.

## Intentional failure recipes

These are designed to give Voker useful error traces. An LLM decides which tool calls to make, so make the request explicit.

| Prompt | Expected trace |
| --- | --- |
| `Look up inventory for OUTAGE-500.` | Local tool `RuntimeError` (planned 503) |
| `Apply a 50% discount for a gold customer.` | Local tool `PermissionError` |
| `Use the MCP policy tool for explode.` | MCP tool error returned to the agent |
| `Add a customer note to FAIL-42 saying hello.` | MCP CRM tool error returned to the agent |
| `Calculate shipping for -2 kg to Paris.` | Local validation `ValueError` |

The agent is intentionally instructed to use tools and to recover once from errors. It never silently turns a tool error into a success. All Voker calls use the generic `VokerClient.events.create()` pathway for an OpenAI-compatible OpenRouter request: Voker’s provider wrapper does not list OpenRouter as a supported provider.

## What gets sent to Voker

- `llm` events for the OpenRouter-compatible chat-completions input and output.
- `tool` events for normal local and MCP tool calls.
- `error` events for model, tool, MCP-returned-tool, and unhandled LangGraph failures.

If `VOKER_API_KEY` is absent, the service still runs but emits no Voker events; `/health` shows both configuration states.
