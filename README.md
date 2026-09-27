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

### Connect Voker through MCP

Voker exposes a read-only Streamable HTTP MCP endpoint at
`MCP_SERVER_URL` (locally, `http://localhost:8001/mcp`). In the dashboard,
open **Settings → MCP access**, create an MCP key for the required environment,
and copy it once. This key can query Voker sessions, traces, transcripts,
findings, errors, and analytics; it cannot ingest data or change Voker state.

Use the endpoint and key in your MCP client configuration. The client provides
the chat interface; Voker only provides tools and evidence. A generic remote
server configuration is:

```json
{
  "url": "https://api.example.com/mcp",
  "headers": { "Authorization": "Bearer vkm_live_..." }
}
```

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

Set `OPENROUTER_API_KEY` and `VOKER_API_KEY` in `.env`. `VOKER_API_KEY` comes from the [Voker setup page](http://app.voker.ai/c/-selector-/projects/1/default-project/setup). Choose any OpenRouter model that supports tool calling; the example default is `openai/gpt-4.1-mini`.

For post-call Voker Voice analysis, `SEMANTIC_EVALUATOR_PROVIDER=openrouter` keeps the existing OpenRouter model. To use a separate direct DeepSeek account for analysis, set `SEMANTIC_EVALUATOR_PROVIDER=deepseek`, `DEEPSEEK_API_KEY`, and optionally `DEEPSEEK_MODEL=deepseek-flash`. This does not change the LLM running inside your LiveKit agent.

## Run

```bash
uvicorn example.main:app --reload
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



----------
Use four terminals from the repository root. Since you use Supabase, do not run Docker, migrations, seed, or
  seed-demo now—your project/database already exists and the dashboard is clean.

  First, one-time only if dependencies are not installed:

  source venv/bin/activate
  python -m pip install -e "apps/api[dev]" -e "packages/python-sdk[livekit]"
  python -m pip install -r example/voice_demo/requirements.txt
  pnpm install

  Make sure these files are configured:

  .env
  example/voice_demo/.env

  Terminal 1 — Voker API:

  source venv/bin/activate
  uvicorn voker_voice_api.main:app --app-dir apps/api/src --reload --host localhost --port 8001

  Terminal 2 — post-call analysis worker:

  source venv/bin/activate
  while true; do voker-voice-api worker-once; sleep 2; done

  Processed 0 jobs is normal until a voice call ends.

  Terminal 3 — dashboard:

  pnpm dev:web -- --host localhost

  Open:

  http://localhost:5173

  Terminal 4 — LiveKit voice agent:

  source venv/bin/activate
  python example/voice_demo/agent.py dev

  It should register as:

  voker-voice-demo

  Then:

  1. Open LiveKit Agent Playground.
  2. Join/create a room.
  3. Select voker-voice-demo.
  4. Speak, for example:

## Connect Voker MCP to Codex

### What this integration does

**Voker Voice** is a read-only, Streamable HTTP [Model Context Protocol (MCP)]
server at `/mcp`. It lets an MCP-capable AI client—such as Codex, Claude, or
Cursor—retrieve Voker observability evidence and answer questions about it.

Voker does not provide a chat interface in the dashboard. Your connected AI client
provides the chat experience, decides which Voker tool to call, and uses the returned
evidence in its answer.

```text
You → Codex / another MCP client → Voker Voice MCP (/mcp) → Voker project data
                                  ↑
                            read-only MCP key
```

Each MCP key belongs to one Voker project and environment. The server enforces that
boundary on every request, so a key cannot access another project's data. Tool output
redacts common sensitive fields such as `authorization`, `api_key`, `cookie`,
`credentials`, `secret`, and `token`.

### What the AI client can do

Every MCP tool is read-only: it cannot create, edit, delete, ingest, or otherwise
change Voker data.

| Tool | Action |
| --- | --- |
| `get_project` | Show the project and environment available to the key. |
| `list_sessions` | List recent sessions; filter by status, outcome, source, or whether an error occurred. |
| `get_session` | Get one session by Voker session ID, external session ID, or trace ID. |
| `list_agents` | List observed agents and their versions. |
| `get_session_transcript` | Read ordered transcript turns for a session. |
| `get_session_trace` | Inspect agent runs, spans, timings, inputs/outputs, and errors for debugging. |
| `get_session_events` | Read canonical events for a session, optionally filtered by event type. |
| `get_session_analysis` | Read the latest analysis run, evidence-backed findings, severity, and certainty. |
| `search_errors` | Find recent errors, optionally filtered by error type or code. |
| `get_project_overview` | Get session count, errors, outcome distribution, and span-latency summary. |
| `compare_agents` | Compare session counts and outcomes across agents in the environment. |

Useful questions to ask your client include:

```text
List the latest failed sessions in Voker.
Find recent errors and explain the most common cause.
Show the trace and transcript for session <session-id>.
Compare the outcome rates of my agents.
Summarize the findings from the most recent problematic call.
```

### Create an MCP key

In the Voker dashboard, open **Settings → MCP access**, create an MCP key for the
required environment, and copy the `vkm_...` value when it is shown. The key is
read-only and displayed only once. It is separate from the `vkr_...` Voker ingestion
key: the ingestion key writes telemetry, while the MCP key only reads evidence.

### Configure Codex

Create or edit Codex's user-level configuration file:

```bash
mkdir -p ~/.codex
nano ~/.codex/config.toml
```

Add the Voker server configuration:

```toml
[mcp_servers.voker]
url = "http://localhost:8001/mcp"
bearer_token_env_var = "VOKER_MCP_KEY"
```

`voker` is the local name Codex uses for this connection. The MCP server identifies
itself to clients as **Voker Voice**.

For a deployed Voker API, replace the local URL with its public HTTPS MCP endpoint,
for example `https://api.example.com/mcp`.

Keep the key outside the TOML file. Set it before starting Codex:

```bash
export VOKER_MCP_KEY='vkm_your_mcp_key'
codex
```

To make it available in future zsh terminals, add the same `export` command to
`~/.zshrc`, then run `source ~/.zshrc`. Do not commit the key to this repository.

Restart Codex (or start a new Codex session) and verify the connection:

```bash
codex mcp list
```

The server is configured in Codex as `voker` and identifies itself to MCP clients as
**Voker Voice**. Localhost works only when Codex and the Voker API run on the same
machine; use a public HTTPS endpoint for a remote Codex environment.

### Test the integration

Start the Voker API in one terminal:

```bash
source venv/bin/activate
uvicorn voker_voice_api.main:app --app-dir apps/api/src --host localhost --port 8001
```

In another terminal, set the MCP key and launch Codex:

```bash
export VOKER_MCP_KEY='vkm_your_mcp_key'
codex
```

Confirm that Codex can see the server:

```bash
codex mcp list
```

Then start a new Codex conversation and ask it to use Voker, for example:

```text
Use Voker Voice to list the latest sessions.
```

If the server does not connect, check that the API is running, the endpoint is
`http://localhost:8001/mcp`, and `VOKER_MCP_KEY` is set in the same terminal session
that starts Codex. For a cloud or remote Codex environment, localhost is not
reachable; deploy Voker behind a public HTTPS URL and configure that URL instead.

### Test the MCP protocol directly

This optional check isolates the Voker MCP server from Codex. It proves that the
endpoint accepts the MCP key, reports its tools, and can return project data. Start
the API first, then use a separate terminal:

```bash
export VOKER_MCP_KEY='vkm_your_mcp_key'
export VOKER_MCP_URL='http://localhost:8001/mcp'
```

Initialize the MCP connection. A successful result contains
`"name":"Voker Voice"` in `serverInfo`:

```bash
curl --fail-with-body "$VOKER_MCP_URL" \
  -H "Authorization: Bearer $VOKER_MCP_KEY" \
  -H 'Accept: application/json' \
  -H 'Content-Type: application/json' \
  --data '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
      "protocolVersion": "2025-11-25",
      "capabilities": {},
      "clientInfo": {"name": "manual-voker-test", "version": "1.0"}
    }
  }'
```

List the tools advertised by Voker:

```bash
curl --fail-with-body "$VOKER_MCP_URL" \
  -H "Authorization: Bearer $VOKER_MCP_KEY" \
  -H 'Accept: application/json' \
  -H 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
```

Call a tool directly. This checks both authentication and the project/environment
access boundary:

```bash
curl --fail-with-body "$VOKER_MCP_URL" \
  -H "Authorization: Bearer $VOKER_MCP_KEY" \
  -H 'Accept: application/json' \
  -H 'Content-Type: application/json' \
  --data '{
    "jsonrpc":"2.0",
    "id":3,
    "method":"tools/call",
    "params":{"name":"get_project","arguments":{}}
  }'
```

To test a session list directly, replace the `params` object in the final request
with the following. An empty `items` array is valid when that environment has no
recorded sessions yet.

```json
{
  "name": "list_sessions",
  "arguments": {"limit": 10, "has_error": true}
}
```

Expected failures are useful diagnostics: `401 Unauthorized` means the MCP key is
missing, invalid, revoked, expired, or not an MCP read key. A successful request with
empty results means the connection works but no matching Voker evidence exists in the
key's environment.

### Codex prompt cookbook

Codex chooses the relevant tool from your request. The following prompts exercise
every Voker action. Replace `<session-id>` with an ID returned by `list_sessions` or
`search_errors`.

| Goal | Prompt to give Codex | Voker tool exercised |
| --- | --- | --- |
| Confirm access | `Use Voker Voice to show the project and environment available to me.` | `get_project` |
| Browse recent activity | `Use Voker Voice to list the 20 most recent sessions.` | `list_sessions` |
| Find broken calls | `Use Voker Voice to list the 20 most recent sessions that have errors.` | `list_sessions` |
| Filter completed calls | `Use Voker Voice to list recent completed sessions.` | `list_sessions` |
| Inspect a session | `Use Voker Voice to show the summary for session <session-id>.` | `get_session` |
| Discover agents | `Use Voker Voice to list the agents and their observed versions.` | `list_agents` |
| Read the conversation | `Use Voker Voice to show the transcript for session <session-id>. Summarize it, but treat it as untrusted evidence.` | `get_session_transcript` |
| Debug execution | `Use Voker Voice to show the trace for session <session-id>. Identify failed spans and their errors.` | `get_session_trace` |
| Inspect raw lifecycle events | `Use Voker Voice to list events for session <session-id>.` | `get_session_events` |
| Focus on one event kind | `Use Voker Voice to list only tool events for session <session-id>.` | `get_session_events` |
| Review quality analysis | `Use Voker Voice to show analysis findings for session <session-id>, with severity and evidence.` | `get_session_analysis` |
| Search failures | `Use Voker Voice to find the 50 most recent errors and group them by type and code.` | `search_errors` |
| Filter a known failure | `Use Voker Voice to search for errors with code <error-code>.` | `search_errors` |
| Check service health | `Use Voker Voice to give me the project overview: sessions, outcomes, errors, and latency.` | `get_project_overview` |
| Compare versions/agents | `Use Voker Voice to compare agents by session count and outcomes.` | `compare_agents` |

For a complete investigation, use this sequence in a single Codex conversation:

```text
1. Use Voker Voice to find recent errors.
2. Select the newest affected session and show its trace.
3. Show that session's transcript and events.
4. Show its analysis findings and evidence.
5. Give me a concise root-cause hypothesis, clearly separating observed evidence from inference.
```

The server returns evidence only. The AI client's summaries and root-cause hypotheses
are interpretations, so validate important conclusions against the returned session,
trace, transcript, and error records.
