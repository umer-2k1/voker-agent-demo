# Voker Voice multi-agent LiveKit demo

This is a real voice-agent test harness, not a dashboard. It runs three specialist
agents in a LiveKit room and sends their trace to the Voker Voice platform.

```text
caller → Intake Agent → Scheduling / Billing / Support Agent
                 │              │
                 └──── Voker Voice observes every LiveKit event ────→ dashboard
```

## Workflows to demonstrate

| Caller request | Expected trace |
| --- | --- |
| “Move my appointment to Tuesday at 2 PM.” | Intake → Scheduling handoff, calendar tools, successful outcome. |
| “Move it to Monday at 9 AM.” | Intake → Scheduling handoff, intentional calendar timeout, error evidence. |
| “Refund me $10.” | Intake → Billing handoff, successful refund tool call. |
| “Refund me $50.” | Intake → Billing handoff, intentional policy-denied tool call. |
| “I cannot log in.” | Intake → Support handoff, ticket tool call. |

The intentional failures are useful: they make tool errors, retries, handoffs, latency,
and the post-call analysis visible in Voker Voice.

## Setup

From the repository root:

```bash
source venv/bin/activate
python -m pip install -e "packages/python-sdk[livekit]"
python -m pip install -r example/voice_demo/requirements.txt
cp example/voice_demo/.env.example example/voice_demo/.env
```

Fill in `example/voice_demo/.env`:

- Create a LiveKit project and copy `LIVEKIT_URL`, `LIVEKIT_API_KEY`, and `LIVEKIT_API_SECRET`.
- Create a Deepgram API key for speech-to-text and text-to-speech.
- Create a direct DeepSeek API key for the live agent LLM.
- Start the Voker Voice API, then create a Voker Voice ingest key with
  `voker-voice-api create-ingest-key --label "LiveKit voice demo"`.

Keep all keys in the ignored `.env` file; do not add them to source control.

## Run the Voker Voice platform

In three terminals at the repository root:

```bash
docker compose up -d postgres
alembic -c apps/api/alembic.ini upgrade head
voker-voice-api seed
uvicorn voker_voice_api.main:app --app-dir apps/api/src --port 8001
```

```bash
while true; do voker-voice-api worker-once; sleep 2; done
```

```bash
pnpm dev:web
```

## Run the voice agent

```bash
source venv/bin/activate
python example/voice_demo/agent.py dev
```

The agent connects to LiveKit and serves its health endpoint at
`http://127.0.0.1:8080/`. Use LiveKit's Agent Playground, your existing LiveKit
frontend, or a LiveKit room client to join a room and speak to the agent.

After ending the call, open the Voker Voice dashboard. The worker processes the
deterministic and semantic analysis jobs; select a session to inspect its nested
trace, transcript, handoff, tools, errors, voice metrics, and evidence-linked
findings.

## Separating the two DeepSeek uses

`DEEPSEEK_API_KEY` in this demo powers the **live voice agent**. The Voker Voice
platform can independently use OpenRouter or direct DeepSeek for **post-call
analysis**. Configure that in the repository-root `.env` with:

```env
SEMANTIC_EVALUATOR_PROVIDER=deepseek
DEEPSEEK_API_KEY=...
DEEPSEEK_MODEL=deepseek-flash
```

If both processes run on the same machine, they may use the same DeepSeek key;
separate keys are recommended for clear cost and access control.
